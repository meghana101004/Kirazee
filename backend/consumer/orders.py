from django.db import transaction, models, connection
from django.utils import timezone
from django.conf import settings
from datetime import datetime, timedelta
from dateutil import parser as date_parser
from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework import status
from django.http import JsonResponse
from django.core.paginator import Paginator
from django.shortcuts import get_object_or_404
from drf_yasg.utils import swagger_auto_schema
from decimal import Decimal
import uuid
import json
import logging
from django.db import connection
from django.db.models.functions import Lower

logger = logging.getLogger(__name__)

from .models import Orders, OrderItems, WalletPoints, Coupons, CouponRedemptions, CouponRules, DeliveryCharges, Payments, OrderStatusLog, create_status_log, BusinessOrderTypes, CouponApplicableItems
from .gro_models import GroceriesOrders, GroceriesProductVariants, GroceriesProducts, GroceriesPayments
from .customization_utils import apply_customizations_pricing_r01
from .serializers import OrderSerializer, OrderItemSerializer, OrderDetailSerializer, OrderListSerializer, CouponSerializer
from consumer.image_utils import build_s3_file_url
from kirazee_app.models import Registration, UserAddress, Business, BusinessMapping
from business.models import MenuItems, productItems, MenuItemVariant
from delivery.models import DeliveryPartner
from notifications.service import send_order_notification, send_email_notification
from management.models import Inventory
from management.utils import get_ist_now


def _normalize_json_value(value):
    """Normalize possibly JSON-encoded strings into Python objects.
    - If value is a JSON string, parse it safely
    - If value is plain string, return as-is
    - Pass-through dict/list/primitive/None
    """
    try:
        if value is None or isinstance(value, (dict, list, int, float, bool)):
            return value
        if isinstance(value, str):
            try:
                return json.loads(value)
            except Exception:
                return value
        return value
    except Exception:
        return value

def _parse_hhmm_to_time(s):
    try:
        s_str = str(s).strip()
        if s_str in ("24:00", "24:00:00", "24"):
            return datetime.strptime("23:59:59", "%H:%M:%S").time()
        for fmt in ("%H:%M", "%H:%M:%S"):
            try:
                return datetime.strptime(s_str, fmt).time()
            except Exception:
                pass
        return None
    except Exception:
        return None

def _time_in_window(check_t, open_t, close_t):
    try:
        if open_t <= close_t:
            return open_t <= check_t <= close_t
        # window wraps past midnight
        return check_t >= open_t or check_t <= close_t
    except Exception:
        return False

def _extract_windows(val):
    """Convert various structures to a list of {'open': 'HH:MM', 'close': 'HH:MM'} dicts."""
    try:
        if not val:
            return []
        if isinstance(val, str):
            parts = [p.strip() for p in val.split(',') if p.strip()]
            windows = []
            for p in parts:
                seg = [x.strip() for x in p.split('-')]
                if len(seg) == 2:
                    windows.append({'open': seg[0], 'close': seg[1]})
            return windows
        if isinstance(val, dict):
            return [val]
        if isinstance(val, list):
            return val
        return []
    except Exception:
        return []

def _current_time_from_dt(dt):
    try:
        if getattr(settings, 'USE_TZ', False):
            return dt.astimezone(timezone.get_current_timezone()).time()
        return dt.time()
    except Exception:
        return datetime.now().time()

def _is_business_open(business, check_dt):
    hours = getattr(business, 'business_hours', None)
    if not hours:
        return True
    try:
        cfg = hours if isinstance(hours, dict) else json.loads(hours)
    except Exception:
        cfg = None
    if not isinstance(cfg, dict):
        return True
    day_abbr = check_dt.strftime('%a').lower()[:3]
    day_full = check_dt.strftime('%A').lower()
    val = cfg.get(day_abbr) or cfg.get(day_full) or cfg.get('general') or cfg.get('default')
    windows = _extract_windows(val)
    ct = _current_time_from_dt(check_dt)
    parsed_any = False
    for w in windows:
        o = _parse_hhmm_to_time(w.get('open') or w.get('opening') or w.get('start'))
        c = _parse_hhmm_to_time(w.get('close') or w.get('closing') or w.get('end'))
        if o and c:
            parsed_any = True
            if _time_in_window(ct, o, c):
                return True
    if not windows:
        return True
    return True if not parsed_any else False

def _is_menu_item_available(menu_item, check_dt):
    availability = getattr(menu_item, 'availability_timings', None)
    if not availability:
        return True
    try:
        cfg = availability if isinstance(availability, dict) else json.loads(availability)
    except Exception:
        cfg = None
    if not isinstance(cfg, dict):
        return True
    day_abbr = check_dt.strftime('%a').lower()[:3]
    day_full = check_dt.strftime('%A').lower()
    val = cfg.get(day_abbr) or cfg.get(day_full) or cfg.get('general') or cfg.get('default')
    windows = _extract_windows(val)
    ct = _current_time_from_dt(check_dt)
    available = False
    for w in windows:
        o = _parse_hhmm_to_time(w.get('open') or w.get('opening') or w.get('start'))
        c = _parse_hhmm_to_time(w.get('close') or w.get('closing') or w.get('end'))
        if o and c and _time_in_window(ct, o, c):
            available = True
            break
    # If windows list is empty, consider item available
    return available if windows else True

def _is_product_item_available(product_item, check_dt):
    try:
        start_t = getattr(product_item, 'availability_timings', None)
        if not start_t:
            return True
        ct = _current_time_from_dt(check_dt)
        return ct >= start_t
    except Exception:
        return True

def _update_inventory_sold_stock(
    business,
    user,
    sku,
    reference_table,
    reference_id,
    item_name,
    quantity,
    parent_reference_table=None,
    parent_reference_id=None,
    business_type=None,  # NEW PARAMETER
):
    """
    Update inventory sold_stock when an item is ordered.
    Only updates if the item already exists in inventory (has SKU).
    If not found in inventory, order proceeds without inventory tracking.
    For R02 (Restaurant) business type, inventory reduction is skipped.  # NEW DOC
    """
    try:
        # NEW CODE - Skip inventory reduction for R02 (Restaurant) business type
        if business_type == 'R02':
            logger.info(f"🍽️ R02 Restaurant order - skipping inventory reduction for {item_name} | Business: {business.business_id}")
            return True  # Return success but don't update inventory
        
        # Try to find existing inventory record by SKU first (most accurate)
        inventory = None
        
        logger.info(f"🔍 Searching inventory for: {item_name} | SKU: {sku} | Ref: {reference_table}:{reference_id} | Business: {business.business_id}")
        
        if sku:
            # Search by SKU within the same business
            sku_norm = str(sku).strip()
            if sku_norm:
                inventory = (
                    Inventory.objects.select_for_update()
                    .filter(
                        business_id=business,
                        sku__iexact=sku_norm,
                    )
                    .order_by('-inventory_id')
                    .first()
                )
            if inventory:
                logger.info(f"  ✓ Found by SKU: {sku}")
        
        # If not found by SKU, try by reference_table and reference_id
        if not inventory:
            ref_lower = (reference_table or '').lower()
            if 'groceries_productvariants' in ref_lower or 'productvariants' in ref_lower:
                candidates = ['groceries_productvariants', 'groceriesproductvariants', 'productvariants']
            elif 'menu' in ref_lower:
                candidates = ['menuitems', 'menu_items', 'menu']
            else:
                # product items (restaurant) and possible older grocery naming
                candidates = ['productitems', 'groceryitems', 'grocery_items', 'products', 'product']

            inventory = (
                Inventory.objects.select_for_update()
                .annotate(ref_lower=Lower('reference_table'))
                .filter(
                    business_id=business,
                    reference_id=reference_id,
                    ref_lower__in=candidates,
                )
                .order_by('-inventory_id')
                .first()
            )
            if inventory:
                logger.info(
                    f"  ✓ Found by reference_id with synonyms: {reference_id} in {candidates}"
                )

        # 3b) If still not found and we have a parent reference (e.g., product for a variant), try that
        if not inventory and parent_reference_table and parent_reference_id:
            parent_lower = (parent_reference_table or '').lower()
            if (
                'groceries_products' in parent_lower
                or 'groceriesproducts' in parent_lower
                or 'products' in parent_lower
                or 'groceryitems' in parent_lower
                or 'grocery_items' in parent_lower
            ):
                parent_candidates = [
                    'groceries_products',
                    'groceriesproducts',
                    'products',
                    'product',
                    'groceryitems',
                    'grocery_items',
                ]
            else:
                parent_candidates = [parent_lower]

            inventory = (
                Inventory.objects.select_for_update()
                .annotate(ref_lower=Lower('reference_table'))
                .filter(
                    business_id=business,
                    reference_id=parent_reference_id,
                    ref_lower__in=parent_candidates,
                )
                .order_by('-inventory_id')
                .first()
            )
            if inventory:
                logger.info(
                    f"  ✓ Found by PARENT reference_id: {parent_reference_id} in {parent_candidates}"
                )
        
        if inventory:
            # Log before update
            old_sold_stock = inventory.sold_stock or 0
            old_current_stock = inventory.current_stock or 0
            
            # Update existing inventory - increment sold_stock using raw SQL
            with connection.cursor() as cursor:
                cursor.execute("""
                    UPDATE Inventory 
                    SET sold_stock = sold_stock + %s, 
                        last_updated = CONVERT_TZ(NOW(), 'UTC', 'Asia/Kolkata')
                    WHERE inventory_id = %s
                """, [quantity, inventory.inventory_id])
                
                # Fetch updated values to verify
                cursor.execute("""
                    SELECT sold_stock, current_stock 
                    FROM Inventory 
                    WHERE inventory_id = %s
                """, [inventory.inventory_id])
                result = cursor.fetchone()
                new_sold_stock, new_current_stock = result if result else (old_sold_stock, old_current_stock)
            
            logger.info(f"✓ Inventory updated for {item_name} (SKU: {sku}, ID: {inventory.inventory_id})")
            logger.info(f"  - sold_stock: {old_sold_stock} → {new_sold_stock} (+{quantity})")
            logger.info(f"  - current_stock: {old_current_stock} → {new_current_stock} (should decrease by {quantity})")
            return True
        else:
            # No inventory record found - skip inventory tracking, just process the order
            logger.info(f"⊘ No inventory record found for {item_name} (SKU: {sku}) - order created without inventory tracking")
            return False
    except Exception as e:
        logger.error(f"Failed to update inventory for {item_name}: {str(e)}")
        # Don't raise exception - inventory tracking is supplementary to order processing
        return False

@swagger_auto_schema(methods=['POST'],tags=['Consumer'])
@api_view(['POST'])
def create_order(request):
    """
    Create new order with address snapshots, delivery charges, coupon and wallet points
    """
    try:
        data = request.data
        user_id = data.get('user_id')
        business_id = data.get('business_id')
        order_type = data.get('order_type')
        delivery_address_id = data.get('delivery_address_id')
        items = data.get('items', [])
        coupon_code = data.get('coupon_code')
        wallet_points_to_use = Decimal(str(data.get('wallet_points_to_use', 0)))
        estimated_delivery_time = data.get('estimated_delivery_time')
        # Optional scheduled time for pre-ordering
        scheduled_time_input = data.get('scheduled_time')
        scheduled_dt = None
        if scheduled_time_input:
            try:
                parsed = date_parser.parse(str(scheduled_time_input))
                if getattr(settings, 'USE_TZ', False):
                    # Ensure timezone-aware datetime
                    if parsed.tzinfo is None:
                        parsed = timezone.make_aware(parsed, timezone.get_current_timezone())
                else:
                    # Ensure naive datetime
                    if parsed.tzinfo is not None:
                        parsed = parsed.astimezone(timezone.get_current_timezone()).replace(tzinfo=None)
                scheduled_dt = parsed
            except Exception:
                return Response({'success': False, 'error': 'Invalid scheduled_time format'}, status=status.HTTP_400_BAD_REQUEST)
        # Pay Later flag: if true, skip online payment and create a pending COD payment entry
        pay_later = bool(data.get('pay_later', False))
        
        # Get parcel_charges from DB later
        # parcel_charges = Decimal(str(data.get('parcel_charges', 0)))

        # Determine the time to check availability against (scheduled time or now)
        check_dt = scheduled_dt if scheduled_dt else (
            timezone.now() if getattr(settings, 'USE_TZ', False) else get_ist_now()
        )

        # Validate required fields - delivery_charges mandatory only for delivery
        required_fields = [user_id, business_id, order_type, items]
        if order_type in ['delivery', 'pickup']:
            if 'delivery_charges' not in data:
                return Response({
                    'success': False,
                    'error': 'Missing required fields: delivery_charges is mandatory for delivery orders'
                }, status=status.HTTP_400_BAD_REQUEST)
            if not delivery_address_id:
                return Response({
                    'success': False,
                    'error': 'Missing required fields: delivery_address_id is mandatory for delivery orders'
                }, status=status.HTTP_400_BAD_REQUEST)
        
        if not all(required_fields):
            return Response({
                'success': False,
                'error': 'Missing required fields: user_id, business_id, order_type, items'
            }, status=status.HTTP_400_BAD_REQUEST)
            
        # Validate user exists
        user = get_object_or_404(Registration, user_id=user_id)
        business = get_object_or_404(Business, business_id=business_id)
        
        # Determine business type for item lookup
        business_type = business.businessType

        # Validate order_type against allowed types for this business
        order_type_normalized = str(order_type).lower().replace('-', '_') if order_type else None
        allowed_types = BusinessOrderTypes.get_allowed_for_business(business)
        if order_type_normalized not in allowed_types:
            return Response({
                'success': False,
                'error': 'Order type not allowed for this business',
                'allowed_order_types': allowed_types
            }, status=status.HTTP_400_BAD_REQUEST)
        # ensure we use normalized value downstream
        order_type = order_type_normalized

        # Optional instruction fields (normalize JSON strings or accept plain text)
        delivery_instruction = _normalize_json_value(data.get('delivery_instruction'))
        order_instruction = _normalize_json_value(data.get('order_instruction'))

        # Use parcel_charges from request payload
        parcel_charges = Decimal(str(data.get('parcel_charges', 0)))
        order_type_lower = order_type.lower()

        # Calculate items total and GST total (parcel_charges from request payload)
        items_total = Decimal('0.00')  # Sum of unit prices only
        items_base_total = Decimal('0.00')  # Sum of unit prices without customization extras
        customizations_total = Decimal('0.00')  # Sum of customization extras (before GST)
        total_gst = Decimal('0.00')    # Sum of all GST amounts
        items_mrp_total = Decimal('0.00')  # Sum of original (MRP) prices only
        order_items_data = []

        # DEBUG: Log incoming items to identify duplicates
        logger.info(f"🔍 ORDER DEBUG - Processing {len(items)} items for user {user_id}, business {business_id}")
        for idx, item in enumerate(items):
            logger.info(f"  Item {idx + 1}: {item}")

        for item in items:
            if 'menu_item_id' in item:
                menu_item = get_object_or_404(MenuItems, item_id=item['menu_item_id'])
                variant_id_input = item.get('variant_id')
                # Enforce time-based availability for menu items
                if not _is_menu_item_available(menu_item, check_dt):
                    return Response({
                        'success': False,
                        'error': f"'{menu_item.item_name}' is not available at this time"
                    }, status=status.HTTP_400_BAD_REQUEST)
                # Variant-aware pricing for restaurant menu items
                if variant_id_input is not None:
                    try:
                        from business.models import MenuItemVariant
                        mv = MenuItemVariant.objects.get(variant_id=variant_id_input, is_active=True)
                        if str(getattr(mv, 'item_id', None) or getattr(getattr(mv, 'item', None), 'item_id', None)) != str(menu_item.item_id):
                            return Response({
                                'success': False,
                                'error': f'Menu variant {variant_id_input} does not belong to menu item {menu_item.item_id}'
                            }, status=status.HTTP_400_BAD_REQUEST)
                        item_price = Decimal(str(mv.selling_price))
                        original_cost = Decimal(str(mv.original_cost)) if getattr(mv, 'original_cost', None) else Decimal('0')
                        gst_percent = Decimal(str(mv.gst)) if getattr(mv, 'gst', None) else (Decimal(str(menu_item.gst)) if menu_item.gst else Decimal('0'))
                    except MenuItemVariant.DoesNotExist:
                        return Response({
                            'success': False,
                            'error': f'Menu variant {variant_id_input} not found or inactive'
                        }, status=status.HTTP_404_NOT_FOUND)
                else:
                    item_price = Decimal(str(menu_item.selling_price))
                    original_cost = Decimal(str(menu_item.original_cost)) if menu_item.original_cost else Decimal('0')
                    gst_percent = Decimal(str(menu_item.gst)) if menu_item.gst else Decimal('0')
                item_name = menu_item.item_name

                # Calculate GST amount with proper rounding
                gst_amount = (item_price * gst_percent / Decimal('100')).quantize(Decimal('0.01'))
                
                # Item total price = (unit_price + GST) * quantity
                item_total_price = (item_price + gst_amount) * Decimal(str(item['quantity']))
                
                base_unit_price = item_price
                customization_extra_unit = Decimal('0.00')
                item_total_before_tax = (item_price * Decimal(str(item['quantity']))).quantize(Decimal('0.01'))
                item_total_after_tax = item_total_price.quantize(Decimal('0.01'))
                
                item_details = {
                    'description': menu_item.description,
                    'category': menu_item.item_category,
                    'type': menu_item.item_type,
                    'gst_percentage': float(gst_percent),
                    'gst_amount': float(gst_amount),
                    'original_cost': float(menu_item.original_cost) if menu_item.original_cost else 0,
                    'selling_price': float(item_price)
                }
                order_items_data.append({
                    'menu_item_id': menu_item.item_id,
                    'product_item_id': None,
                    'variant_id': int(variant_id_input) if variant_id_input is not None else None,
                    'item_name': item_name,
                    'quantity': item['quantity'],
                    'base_unit_price': float(base_unit_price),
                    'customization_extra_unit': float(customization_extra_unit),
                    'customization_extra_total': float(customization_extra_unit * Decimal(str(item['quantity']))),
                    'unit_price': float(item_price),
                    'total_price': float(item_total_price),
                    'item_details': item_details,
                    'customizations': _normalize_json_value(item.get('customizations', []))
                })
                
                # Add to totals: items_total = sum of unit prices, total_gst = sum of GST amounts
                items_total += item_price * Decimal(str(item['quantity']))
                items_base_total += base_unit_price * Decimal(str(item['quantity']))
                customizations_total += customization_extra_unit * Decimal(str(item['quantity']))
                total_gst += gst_amount * Decimal(str(item['quantity']))
                items_mrp_total += original_cost * Decimal(str(item['quantity']))
                
            elif 'product_item_id' in item:
                variant_id_input = item.get('variant_id')
                # Handle based on business type
                if business_type == 'R01':
                    # Grocery business - lookup in Groceries_ProductVariants
                    from .gro_models import GroceriesProductVariants, GroceriesProducts
                    
                    # Variant-aware: if variant_id provided, use that variant. Otherwise, fallback to legacy behavior.
                    try:
                        if variant_id_input is not None:
                            grocery_variant = GroceriesProductVariants.objects.get(
                                variant_id=variant_id_input,
                                is_active=True,
                            )
                            grocery_product = grocery_variant.product
                            if str(grocery_product.business_id) != str(business_id):
                                return Response({
                                    'success': False,
                                    'error': f'Grocery variant {variant_id_input} does not belong to business {business_id}'
                                }, status=status.HTTP_400_BAD_REQUEST)

                            if item.get('product_item_id') is not None and str(grocery_product.product_id) != str(item.get('product_item_id')):
                                return Response({
                                    'success': False,
                                    'error': f'Grocery variant {variant_id_input} does not belong to product {item.get("product_item_id")}'
                                }, status=status.HTTP_400_BAD_REQUEST)
                        else:
                            # Legacy: treat product_item_id as product_id and choose cheapest active variant
                            grocery_product = GroceriesProducts.objects.get(product_id=item['product_item_id'], business_id=business_id)
                            grocery_variant = (
                                GroceriesProductVariants.objects
                                .filter(product=grocery_product, is_active=True)
                                .order_by('selling_price', 'variant_id')
                                .first()
                            )
                            if not grocery_variant:
                                raise GroceriesProductVariants.DoesNotExist()

                        item_price = Decimal(str(grocery_variant.selling_price)) if grocery_variant.selling_price else Decimal('0')
                        item_name = grocery_product.product_name
                        original_cost = Decimal(str(grocery_variant.original_cost)) if grocery_variant.original_cost else Decimal('0')
                        gst_percent = grocery_variant.gst if grocery_variant.gst is not None else (
                            Decimal(str(getattr(grocery_product.category, 'gst_rate', None) or 0))
                            if grocery_product.category else Decimal('0')
                        )
                        # Resolve category name for item_details
                        grocery_category_name = None
                        try:
                            cat = grocery_product.category
                            grocery_category_name = getattr(cat, 'category_name', None)
                        except Exception:
                            grocery_category_name = None
                        if not grocery_category_name:
                            try:
                                from business.models import UniversalCategory
                                uc = UniversalCategory.objects.filter(category_id=grocery_product.category_id).first()
                                grocery_category_name = uc.category_name if uc else None
                            except Exception:
                                grocery_category_name = None
                        
                    except (GroceriesProducts.DoesNotExist, GroceriesProductVariants.DoesNotExist):
                        # Fallback: treat as variant_id
                        try:
                            grocery_variant = GroceriesProductVariants.objects.get(
                                variant_id=item['product_item_id'], 
                                is_active=True
                            )
                            # Validate it belongs to the same business
                            if grocery_variant.product.business_id != business_id:
                                return Response({
                                    'success': False,
                                    'error': f'Grocery variant {item["product_item_id"]} does not belong to business {business_id}'
                                }, status=status.HTTP_400_BAD_REQUEST)
                            
                            grocery_product = grocery_variant.product
                            item_price = Decimal(str(grocery_variant.selling_price)) if grocery_variant.selling_price else Decimal('0')
                            item_name = grocery_product.product_name
                            original_cost = Decimal(str(grocery_variant.original_cost)) if grocery_variant.original_cost else Decimal('0')
                            # Get GST from variant (new field), fallback to category if not set
                            gst_percent = grocery_variant.gst if grocery_variant.gst is not None else (
                                Decimal(str(getattr(grocery_product.category, 'gst_rate', None) or 0))
                                if grocery_product.category else Decimal('0')
                            )
                            # Resolve category name for item_details
                            grocery_category_name = None
                            try:
                                cat = grocery_product.category
                                grocery_category_name = getattr(cat, 'category_name', None)
                            except Exception:
                                grocery_category_name = None
                            if not grocery_category_name:
                                try:
                                    from business.models import UniversalCategory
                                    uc = UniversalCategory.objects.filter(category_id=grocery_product.category_id).first()
                                    grocery_category_name = uc.category_name if uc else None
                                except Exception:
                                    grocery_category_name = None
                            
                        except GroceriesProductVariants.DoesNotExist:
                            return Response({
                                'success': False,
                                'error': f'Grocery item with ID {item["product_item_id"]} not found or inactive'
                            }, status=status.HTTP_404_NOT_FOUND)
                        
                elif business_type == 'R02':
                    # Restaurant business - lookup in productItems (base) and optionally menu_item_variants (variant)
                    if variant_id_input is not None:
                        from business.models import MenuItemVariant

                        mv = get_object_or_404(MenuItemVariant, variant_id=variant_id_input, is_active=True)
                        base_menu_item = mv.item
                        if str(base_menu_item.business_id_id) != str(business_id):
                            return Response({
                                'success': False,
                                'error': f'Menu variant {variant_id_input} does not belong to business {business_id}'
                            }, status=status.HTTP_400_BAD_REQUEST)
                        if item.get('product_item_id') is not None and str(base_menu_item.item_id) != str(item.get('product_item_id')):
                            return Response({
                                'success': False,
                                'error': f'Menu variant {variant_id_input} does not belong to item {item.get("product_item_id")}'
                            }, status=status.HTTP_400_BAD_REQUEST)

                        # Availability check uses base item
                        if not _is_product_item_available(base_menu_item, check_dt):
                            return Response({
                                'success': False,
                                'error': f"'{base_menu_item.item_name}' is not available at this time"
                            }, status=status.HTTP_400_BAD_REQUEST)

                        product_item = base_menu_item
                        item_price = Decimal(str(mv.selling_price))
                        item_name = base_menu_item.item_name
                        original_cost = Decimal(str(mv.original_cost)) if mv.original_cost else Decimal('0')
                        gst_percent = Decimal(str(mv.gst)) if mv.gst else (Decimal(str(base_menu_item.gst)) if base_menu_item.gst else Decimal('0'))
                    else:
                        product_item = get_object_or_404(productItems, item_id=item['product_item_id'])
                        # Enforce time-based availability for product items
                        if not _is_product_item_available(product_item, check_dt):
                            return Response({
                                'success': False,
                                'error': f"'{product_item.item_name}' is not available at this time"
                            }, status=status.HTTP_400_BAD_REQUEST)
                        item_price = Decimal(str(product_item.selling_price))
                        item_name = product_item.item_name
                        original_cost = Decimal(str(product_item.original_cost)) if getattr(product_item, 'original_cost', None) else Decimal('0')
                        gst_percent = Decimal(str(product_item.gst)) if product_item.gst else Decimal('0')
                elif business_type == 'R08':
                    from business.models import FashionProductVariant, FashionProduct
                    # Try variant_id first; if not found, treat as product_id and use default variant
                    fashion_variant = None
                    try:
                        vid = variant_id_input if variant_id_input is not None else item['product_item_id']
                        fashion_variant = FashionProductVariant.objects.select_related('product', 'product__category').get(
                            variant_id=vid,
                            is_active=True,
                        )
                    except FashionProductVariant.DoesNotExist:
                        # Fallback: treat as product_id and use default variant
                        try:
                            from business.models import FashionProduct
                            fashion_product = FashionProduct.objects.get(
                                product_id=item['product_item_id'],
                                business_id=business_id,
                                is_active=True
                            )
                            if not getattr(fashion_product, 'variant_id', None):
                                return Response({
                                    'success': False,
                                    'error': f'Fashion product {item["product_item_id"]} has no default variant set'
                                }, status=status.HTTP_404_NOT_FOUND)
                            fashion_variant = FashionProductVariant.objects.select_related('product', 'product__category').get(
                                variant_id=fashion_product.variant_id,
                                is_active=True,
                            )
                        except (FashionProduct.DoesNotExist, FashionProductVariant.DoesNotExist):
                            return Response({
                                'success': False,
                                'error': f'Fashion variant with ID {item["product_item_id"]} not found or inactive (tried as variant_id and product_id)'
                            }, status=status.HTTP_404_NOT_FOUND)

                    fashion_product = getattr(fashion_variant, 'product', None)

                    if str(getattr(fashion_variant, 'business_id_id', None)) != str(business_id):
                        return Response({'success': False, 'error': 'Fashion variant does not belong to this business'}, status=status.HTTP_400_BAD_REQUEST)
                    if variant_id_input is not None and item.get('product_item_id') is not None and fashion_product is not None:
                        if str(fashion_product.product_id) != str(item.get('product_item_id')):
                            return Response({'success': False, 'error': f'Fashion variant {variant_id_input} does not belong to product {item.get("product_item_id")}'}, status=status.HTTP_400_BAD_REQUEST)

                    item_price = Decimal(str(fashion_variant.selling_price)) if fashion_variant.selling_price is not None else Decimal('0')
                    item_name = fashion_product.name if fashion_product else 'Fashion Item'
                    original_cost = Decimal(str(fashion_variant.original_cost)) if fashion_variant.original_cost is not None else Decimal('0')
                    gst_percent = Decimal(str(getattr(fashion_product, 'gst_rate_default', None))) if getattr(fashion_product, 'gst_rate_default', None) else Decimal('0')
                
                # Calculate GST amount with proper rounding
                base_unit_price = item_price
                customization_extra_unit = Decimal('0.00')
                if business_type == 'R01':
                    selections = _normalize_json_value(item.get('customizations', []))
                    try:
                        if getattr(settings, 'DEBUG', False):
                            print('[create_order][R01] base_price', str(item_price), 'product_id', str(grocery_product.product_id), 'customizations', selections)
                        simple_extra = Decimal('0.00')
                        try:
                            if isinstance(selections, list) and selections and all(isinstance(s, dict) for s in selections):
                                has_design_ids = any(s.get('design_id') is not None for s in selections)
                                if not has_design_ids:
                                    for s in selections:
                                        p = s.get('price')
                                        if p is None:
                                            continue
                                        try:
                                            simple_extra += Decimal(str(p))
                                        except Exception:
                                            continue
                        except Exception:
                            simple_extra = Decimal('0.00')

                        if simple_extra > 0:
                            item_price = (item_price or Decimal('0')) + simple_extra
                        else:
                            item_price = apply_customizations_pricing_r01(business_id, grocery_product.product_id, selections, item_price)
                        if getattr(settings, 'DEBUG', False):
                            print('[create_order][R01] priced_unit', str(item_price))
                        customization_extra_unit = (item_price - base_unit_price)
                        if customization_extra_unit < 0:
                            customization_extra_unit = Decimal('0.00')
                    except ValueError as ve:
                        return Response({'success': False, 'error': str(ve)}, status=status.HTTP_400_BAD_REQUEST)
                gst_amount = (item_price * gst_percent / Decimal('100')).quantize(Decimal('0.01'))
                
                # Item total price = (unit_price + GST) * quantity
                item_total_price = (item_price + gst_amount) * Decimal(str(item['quantity']))
                
                if business_type == 'R01':
                    item_details = {
                        'description': grocery_product.description,
                        'category': grocery_category_name,
                        'type': grocery_product.sub_category,
                        'product_id': int(grocery_product.product_id) if getattr(grocery_product, 'product_id', None) is not None else None,
                        'variant_id': int(grocery_variant.variant_id) if getattr(grocery_variant, 'variant_id', None) is not None else None,
                        'gst_percentage': float(gst_percent),
                        'gst_amount': float(gst_amount),
                        'original_cost': float(grocery_variant.original_cost) if grocery_variant.original_cost else 0,
                        'selling_price': float(item_price)
                    }
                    order_items_data.append({
                        'menu_item_id': None,
                        'product_item_id': grocery_product.product_id,
                        'variant_id': grocery_variant.variant_id,
                        'base_product_id': grocery_product.product_id,
                        'item_name': item_name,
                        'quantity': item['quantity'],
                        'base_unit_price': float(base_unit_price),
                        'customization_extra_unit': float(customization_extra_unit),
                        'customization_extra_total': float(customization_extra_unit * Decimal(str(item['quantity']))),
                        'unit_price': float(item_price),
                        'total_price': float(item_total_price),
                        'item_details': item_details,
                        'customizations': _normalize_json_value(item.get('customizations', []))
                    })
                elif business_type == 'R02':
                    item_details = {
                        'description': product_item.description,
                        'category': product_item.item_category,
                        'type': product_item.item_type,
                        'variant_id': int(variant_id_input) if variant_id_input is not None else None,
                        'base_item_id': int(product_item.item_id) if getattr(product_item, 'item_id', None) is not None else None,
                        'gst_percentage': float(gst_percent),
                        'gst_amount': float(gst_amount),
                        'original_cost': float(product_item.original_cost) if getattr(product_item, 'original_cost', None) else 0,
                        'selling_price': float(item_price)
                    }
                    order_items_data.append({
                        'menu_item_id': None,
                        'product_item_id': product_item.item_id,
                        'variant_id': int(variant_id_input) if variant_id_input is not None else None,
                        'item_name': item_name,
                        'quantity': item['quantity'],
                        'base_unit_price': float(base_unit_price),
                        'customization_extra_unit': float(customization_extra_unit),
                        'customization_extra_total': float(customization_extra_unit * Decimal(str(item['quantity']))),
                        'unit_price': float(item_price),
                        'total_price': float(item_total_price),
                        'item_details': item_details,
                        'customizations': _normalize_json_value(item.get('customizations', []))
                    })
                elif business_type == 'R08':
                    item_details = {
                        'product_id': int(getattr(fashion_product, 'product_id', None)) if getattr(fashion_product, 'product_id', None) is not None else None,
                        'variant_id': int(fashion_variant.variant_id) if getattr(fashion_variant, 'variant_id', None) is not None else None,
                        'description': getattr(fashion_product, 'description', None) if fashion_product else None,
                        'category': fashion_product.category.category_name if getattr(fashion_product, 'category', None) else None,
                        'type': getattr(fashion_product, 'subcategory', None) or getattr(fashion_product, 'subcategory_id', None),
                        'gst_percentage': float(gst_percent),
                        'gst_amount': float(gst_amount),
                        'original_cost': float(fashion_variant.original_cost) if fashion_variant.original_cost is not None else 0,
                        'selling_price': float(item_price),
                        'size': getattr(fashion_variant, 'size', None),
                        'color': getattr(fashion_variant, 'color', None)
                    }
                    order_items_data.append({
                        'menu_item_id': None,
                        'product_item_id': int(getattr(fashion_product, 'product_id', None)) if getattr(fashion_product, 'product_id', None) is not None else None,
                        'variant_id': int(fashion_variant.variant_id) if getattr(fashion_variant, 'variant_id', None) is not None else None,
                        'base_product_id': int(getattr(fashion_product, 'product_id', None)) if getattr(fashion_product, 'product_id', None) is not None else None,
                        'item_name': item_name,
                        'quantity': item['quantity'],
                        'base_unit_price': float(base_unit_price),
                        'customization_extra_unit': float(customization_extra_unit),
                        'customization_extra_total': float(customization_extra_unit * Decimal(str(item['quantity']))),
                        'unit_price': float(item_price),
                        'total_price': float(item_total_price),
                        'item_details': item_details,
                        'customizations': _normalize_json_value(item.get('customizations', []))
                    })
                
                # Add to totals: items_total = sum of unit prices, total_gst = sum of GST amounts
                items_total += item_price * Decimal(str(item['quantity']))
                items_base_total += base_unit_price * Decimal(str(item['quantity']))
                customizations_total += customization_extra_unit * Decimal(str(item['quantity']))
                total_gst += gst_amount * Decimal(str(item['quantity']))
                items_mrp_total += original_cost * Decimal(str(item['quantity']))

        # Apply coupon if provided
        discount_amount = Decimal('0.00')
        coupon_applied = None
        
        if coupon_code:
            try:
                coupon = Coupons.objects.get(coupon_code=coupon_code, is_active=True)
                
                # Enforce business scoping if coupon is business-specific
                if coupon.business_id_id and str(coupon.business_id_id) != str(business_id):
                    return Response({'success': False, 'error': 'Coupon not valid for this business'}, status=status.HTTP_400_BAD_REQUEST)

                
                # Validate coupon generally
                is_valid, message = coupon.is_valid_for_user(user_id)
                if not is_valid:
                    return Response({'success': False, 'error': f'Coupon validation failed: {message}'}, status=status.HTTP_400_BAD_REQUEST)

                # Determine base amount for discount: item-specific eligible subtotal or full items_total
                base_amount = items_total
                try:
                    has_applicable = CouponApplicableItems.objects.filter(coupon=coupon).exists()
                except Exception:
                    has_applicable = False

                if has_applicable:
                    # Build mapping set
                    app_set = set()
                    try:
                        app_set = set(CouponApplicableItems.objects.filter(coupon=coupon).values_list('reference_table', 'reference_id'))
                    except Exception:
                        app_set = set()
                    eligible_items_total = Decimal('0.00')
                    eligible_gst = Decimal('0.00')
                    for oi in order_items_data:
                        qty = Decimal(str(oi.get('quantity', 1)))
                        unit_price = Decimal(str(oi.get('unit_price', 0)))
                        ref_table = None
                        ref_id = None
                        if oi.get('menu_item_id'):
                            ref_table = 'menuItems'
                            ref_id = int(oi['menu_item_id'])
                        elif oi.get('product_item_id'):
                            pid = int(oi['product_item_id'])
                            bt_upper = str(business_type).upper()
                            if bt_upper == 'R01':
                                ref_table = 'Groceries_ProductVariants'
                            elif bt_upper == 'R08':
                                ref_table = 'fashion_product_variants'
                            else:
                                ref_table = 'productItems'
                            ref_id = pid
                        if ref_table and (ref_table, ref_id) in app_set:
                            eligible_items_total += (unit_price * qty)
                            # Add proportional GST for eligible items
                            gst_percent = Decimal(str(oi.get('item_details', {}).get('gst_percentage', 0)))
                            gst_amount = (unit_price * gst_percent / Decimal('100')).quantize(Decimal('0.01'))
                            eligible_gst += (gst_amount * qty)
                    
                    # For eligible items, include their GST in the base amount
                    eligible_subtotal = (eligible_items_total + eligible_gst).quantize(Decimal('1'))
                    if eligible_subtotal <= 0:
                        return Response({'success': False, 'error': 'Coupon not applicable to selected items'}, status=status.HTTP_400_BAD_REQUEST)
                    base_amount = eligible_subtotal

                # Calculate discount against base_amount
                if coupon.discount_type == 'percentage':
                    discount_amount = (base_amount * Decimal(str(coupon.discount_value))) / Decimal('100')
                    if discount_amount > base_amount:
                        discount_amount = base_amount
                elif coupon.discount_type == 'fixed_amount':
                    discount_amount = Decimal(str(coupon.discount_value))
                    if discount_amount > base_amount:
                        discount_amount = base_amount
                elif coupon.discount_type == 'free_delivery':
                    discount_amount = Decimal(str(data.get('delivery_charges')))
                    data['delivery_charges'] = '0'
                elif coupon.discount_type == 'bogo':
                    # BOGO: require at least 2 eligible units in cart; discount equals cheapest eligible unit price
                    eligible_units = Decimal('0')
                    cheapest = None
                    app_set = set()
                    if has_applicable:
                        try:
                            app_set = set(CouponApplicableItems.objects.filter(coupon=coupon).values_list('reference_table', 'reference_id'))
                        except Exception:
                            app_set = set()
                    for oi in order_items_data:
                        try:
                            qty = Decimal(str(oi.get('quantity', 1)))
                            unit_price = Decimal(str(oi.get('unit_price', 0)))
                            ref_table = None
                            ref_id = None
                            if oi.get('menu_item_id'):
                                ref_table = 'menuItems'
                                ref_id = int(oi['menu_item_id'])
                            elif oi.get('product_item_id'):
                                bt_upper = str(business_type).upper()
                                if bt_upper == 'R01':
                                    ref_table = 'Groceries_ProductVariants'
                                elif bt_upper == 'R08':
                                    ref_table = 'fashion_product_variants'
                                else:
                                    ref_table = 'productItems'
                                ref_id = int(oi['product_item_id'])
                            eligible = True
                            if has_applicable:
                                eligible = (ref_table, ref_id) in app_set
                            if unit_price is not None and eligible:
                                eligible_units += qty
                                if cheapest is None or unit_price < cheapest:
                                    cheapest = unit_price
                        except Exception:
                            continue
                    if eligible_units < 2 or cheapest is None:
                        return Response({'success': False, 'error': 'BOGO requires at least 2 eligible items in cart'}, status=status.HTTP_400_BAD_REQUEST)
                    discount_amount = cheapest
                
                coupon_applied = coupon
                
            except Coupons.DoesNotExist:
                return Response({'success': False, 'error': 'Invalid coupon code'}, status=status.HTTP_400_BAD_REQUEST)

        # Calculate final amount with proper rounding - internal values to 2 decimal places
        delivery_charges = Decimal(str(data.get('delivery_charges', 0))).quantize(Decimal('0.01'))
        
        # Round all calculated values to 2 decimal places (preserve precision for GST etc)
        items_total = items_total.quantize(Decimal('0.01'))
        items_base_total = items_base_total.quantize(Decimal('0.01'))
        customizations_total = customizations_total.quantize(Decimal('0.01'))
        total_gst = total_gst.quantize(Decimal('0.01'))
        parcel_charges = parcel_charges.quantize(Decimal('0.01'))
        discount_amount = discount_amount.quantize(Decimal('0.01'))
        
        # Calculate subtotal (items + GST + delivery + parcel)
        subtotal = (items_total + total_gst + delivery_charges + parcel_charges).quantize(Decimal('0.01'))
        
        # Apply coupon discount to subtotal
        after_coupon = (subtotal - discount_amount).quantize(Decimal('0.01'))
        
        # Ensure after_coupon is not negative
        if after_coupon < Decimal('0'):
            after_coupon = Decimal('0')
        
        items_mrp_total = items_mrp_total.quantize(Decimal('0.01'))
        items_discount = (items_mrp_total - items_total)
        if items_discount < 0:
            items_discount = Decimal('0')
        you_saved = (items_discount + discount_amount).quantize(Decimal('0.01'))
        
        # Apply wallet points
        wallet_points_value = wallet_points_to_use.quantize(Decimal('0.01'))
        
        # Round final_amount to nearest whole number (Round Figure)
        final_amount = (after_coupon - wallet_points_value).quantize(Decimal('1'))

        with transaction.atomic():
            # Generate business-specific token number (resets daily at 101)
            # Get current date (timezone-aware or naive based on settings)
            if getattr(settings, 'USE_TZ', False):
                today_start = timezone.now().replace(hour=0, minute=0, second=0, microsecond=0)
            else:
                today_start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
            
            # Get the last order for this business TODAY using select_for_update to prevent race conditions
            last_order_for_token = (
                Orders.objects
                .select_for_update()
                .filter(
                    business_id=business, 
                    token_num__isnull=False,
                    created_at__gte=today_start  # Only orders from today
                )
                .order_by('-token_num')
                .first()
            )
            
            if last_order_for_token and last_order_for_token.token_num:
                # Increment the last token number from today
                next_token_num = last_order_for_token.token_num + 1
            else:
                # First order for this business today starts at 101
                next_token_num = 101
            
            # Safety check: Verify token number doesn't already exist for today
            # (Double-check to prevent race conditions)
            existing_token_today = Orders.objects.filter(
                business_id=business,
                token_num=next_token_num,
                created_at__gte=today_start
            ).exists()
            
            if existing_token_today:
                # If token exists (unlikely but possible), find the next available
                max_token_today = Orders.objects.filter(
                    business_id=business,
                    token_num__isnull=False,
                    created_at__gte=today_start
                ).aggregate(models.Max('token_num'))['token_num__max']
                
                if max_token_today:
                    next_token_num = max_token_today + 1
                else:
                    next_token_num = 101
            
            # Create order with business-specific token number
            order = Orders.objects.create(
                user_id=user,
                business_id=business,
                order_type=order_type,
                token_num=next_token_num,
                total_amount=items_total,
                discount_amount=discount_amount,
                delivery_charges=delivery_charges,
                parcel_charges=parcel_charges,
                final_amount=final_amount,
                delivery_address_id=delivery_address_id,
                coupon_code=coupon_code,
                wallet_points_used=wallet_points_to_use,
                estimated_delivery_time=estimated_delivery_time,
                scheduled_time=scheduled_dt,
                delivery_instruction=delivery_instruction,
                order_instruction=order_instruction
            )

            # Create address snapshot if delivery
            logger.info(f"🔍 Address Snapshot Debug - order_type: '{order_type}', delivery_address_id: {delivery_address_id}")
            if order_type == 'delivery' and delivery_address_id:
                logger.info(f"✓ Creating address snapshot for delivery order")
                delivery_address = UserAddress.objects.get(id=delivery_address_id)
                order.delivery_address_snapshot = order._create_address_snapshot(delivery_address)
                order.save(update_fields=['delivery_address_snapshot'])
            else:
                logger.info(f"✗ Skipping address snapshot - not a delivery order or no delivery_address_id")

            # Create order items with inventory decrement
            created_items = []
            for item_data in order_items_data:
                qty = int(item_data['quantity']) if item_data.get('quantity') is not None else 0
                menu_id = item_data.get('menu_item_id')
                prod_id = item_data.get('product_item_id')
                variant_id_col = item_data.get('variant_id')

                if menu_id:
                    # For R02 (Restaurant), check variant stock if variant_id is provided, otherwise check menu item stock
                    variant_for_stock = variant_id_col
                    if variant_for_stock:
                        try:
                            variant = MenuItemVariant.objects.select_for_update().get(variant_id=variant_for_stock, is_active=True)
                            if variant.stock_qty is not None:
                                if variant.stock_qty < qty:
                                    return Response({'success': False, 'error': f'Insufficient stock for {variant.size_label} variant of {item_data.get("item_name", "menu item")}'}, status=status.HTTP_400_BAD_REQUEST)
                                variant.stock_qty = variant.stock_qty - qty
                                variant.save(update_fields=['stock_qty'])
                        except MenuItemVariant.DoesNotExist:
                            return Response({'success': False, 'error': 'Menu item variant not found'}, status=status.HTTP_400_BAD_REQUEST)
                    else:
                        # Fallback to checking parent menu item stock if no variant specified
                        mi = MenuItems.objects.select_for_update().get(item_id=menu_id)
                        if mi.quantity is not None:
                            if mi.quantity < qty:
                                return Response({'success': False, 'error': f'Insufficient stock for {mi.item_name}'}, status=status.HTTP_400_BAD_REQUEST)
                            mi.quantity = mi.quantity - qty
                            mi.save(update_fields=['quantity'])
                    
                    # Update inventory sold_stock
                    if variant_for_stock:
                        # Use variant SKU if available
                        variant = MenuItemVariant.objects.get(variant_id=variant_for_stock)
                        sku = variant.sku
                    else:
                        # Use menu item SKU
                        mi = MenuItems.objects.get(item_id=menu_id)
                        sku = mi.sku
                    
                    _update_inventory_sold_stock(
                        business=business,
                        user=user,
                        sku=sku,
                        reference_table='menu_item_variants' if variant_for_stock else 'menuItems',
                        reference_id=variant_for_stock if variant_for_stock else menu_id,
                        item_name=item_data.get('item_name'),
                        quantity=qty,
                        business_type=business_type  # NEW PARAMETER
                    )
                elif prod_id:
                    if business_type == 'R01':
                        # For R01, prod_id is base product; use variant_id_col for variant stock update
                        variant_for_stock = variant_id_col
                        if not variant_for_stock:
                            return Response({'success': False, 'error': 'Variant ID required for stock update in R01'}, status=status.HTTP_400_BAD_REQUEST)
                        try:
                            var = GroceriesProductVariants.objects.select_for_update().get(variant_id=variant_for_stock)
                        except GroceriesProductVariants.DoesNotExist:
                            return Response({'success': False, 'error': 'Grocery variant not found for stock update'}, status=status.HTTP_400_BAD_REQUEST)
                        if var.stock is not None:
                            if var.stock < qty:
                                return Response({'success': False, 'error': f'Insufficient stock for {var.sku}'}, status=status.HTTP_400_BAD_REQUEST)
                            var.stock = var.stock - qty
                            var.save(update_fields=['stock'])
                        
                        # Update inventory sold_stock for grocery variant
                        _update_inventory_sold_stock(
                            business=business,
                            user=user,
                            sku=var.sku,
                            reference_table='Groceries_ProductVariants',
                            reference_id=variant_for_stock,
                            item_name=var.product.product_name if hasattr(var, 'product') else item_data['item_name'],
                            quantity=qty,
                            parent_reference_table='Groceries_Products' if hasattr(var, 'product') else None,  # NEW
                            parent_reference_id=var.product.product_id if hasattr(var, 'product') else None,  # NEW
                            business_type=business_type  # NEW PARAMETER
                        )
                    elif business_type == 'R02':
                        pi = productItems.objects.select_for_update().get(item_id=prod_id)
                        if pi.stock is not None:
                            if pi.stock < qty:
                                return Response({'success': False, 'error': f'Insufficient stock for {pi.item_name}'}, status=status.HTTP_400_BAD_REQUEST)
                            pi.stock = pi.stock - qty
                            pi.save(update_fields=['stock'])
                        
                        # Update inventory sold_stock for product item
                        _update_inventory_sold_stock(
                            business=business,
                            user=user,
                            sku=None,  # productItems doesn't have SKU field
                            reference_table='productItems',
                            reference_id=prod_id,
                            item_name=pi.item_name,
                            quantity=qty,
                            business_type=business_type  # NEW PARAMETER - This will trigger the R02 skip logic
                        )
                    elif business_type == 'R08':
                        from business.models import FashionProductVariant
                        # For R08, prod_id is base product; use variant_id_col for variant stock update
                        variant_for_stock = variant_id_col
                        if not variant_for_stock:
                            return Response({'success': False, 'error': 'Variant ID required for stock update in R08'}, status=status.HTTP_400_BAD_REQUEST)
                        try:
                            var = FashionProductVariant.objects.select_for_update().get(variant_id=variant_for_stock, is_active=True)
                        except FashionProductVariant.DoesNotExist:
                            return Response({'success': False, 'error': 'Fashion variant not found for stock update'}, status=status.HTTP_400_BAD_REQUEST)
                        if str(var.business_id_id) != str(business_id):
                            return Response({'success': False, 'error': 'Fashion variant does not belong to this business'}, status=status.HTTP_400_BAD_REQUEST)
                        # Check stock_qty field (primary) and fallback to stock field
                        stock_to_check = var.stock_qty if var.stock_qty is not None else var.stock
                        if stock_to_check is not None:
                            if stock_to_check < qty:
                                return Response({'success': False, 'error': f'Insufficient stock for {var.sku}'}, status=status.HTTP_400_BAD_REQUEST)
                            # Update primary stock_qty field and keep stock in sync
                            var.stock_qty = stock_to_check - qty
                            var.stock = var.stock_qty  # Keep stock field synchronized
                            var.save(update_fields=['stock_qty', 'stock'])

                        _update_inventory_sold_stock(
                            business=business,
                            user=user,
                            sku=var.sku,
                            reference_table='fashion_product_variants',
                            reference_id=variant_for_stock,
                            item_name=var.product.name if getattr(var, 'product', None) else item_data.get('item_name'),
                            quantity=qty,
                            parent_reference_table='fashion_products' if getattr(var, 'product', None) else None,  # NEW
                            parent_reference_id=var.product.product_id if getattr(var, 'product', None) else None,  # NEW
                            business_type=business_type  # NEW PARAMETER
                        )

                order_item = OrderItems.objects.create(
                    order_id=order,
                    menu_item_id=menu_id,
                    product_item_id=prod_id,
                    variant_id=variant_id_col,
                    item_name_snapshot=item_data['item_name'],
                    quantity=qty,
                    unit_price_snapshot=item_data['unit_price'],
                    total_price=item_data['total_price'],
                    item_details_snapshot={
                        **(item_data.get('item_details') or {}),
                        'requested_product_item_id': item_data.get('base_product_id') or item_data.get('base_item_id'),
                        'requested_variant_id': item_data.get('variant_id'),
                        'customizations': item_data.get('customizations', []),
                        'order_context': {
                            'delivery_charges': float(delivery_charges),
                            'delivery_address_id': delivery_address_id,
                            'parcel_charges': float(parcel_charges),
                            'coupon_code': coupon_code or '',
                            'wallet_points_to_use': float(wallet_points_to_use),
                            'delivery_instruction': delivery_instruction,
                            'order_instruction': order_instruction,
                        }
                    },
                    gst=item_data['item_details'].get('gst_percentage'),
                    gst_amount=item_data['item_details'].get('gst_amount', 0),
                    customizations=item_data.get('customizations', [])
                )
                created_items.append(order_item)

            # Process wallet points transaction
            if wallet_points_to_use > 0:
                WalletPoints.atomic_transaction(
                    user_id=user,
                    points=wallet_points_to_use,
                    transaction_type=WalletPoints.TransactionType.SPENT,
                    description=f'Points spent on order #{order.order_number}',
                    related_order=order
                )

            

            # If Pay Later selected, create a pending COD payment record linked to this order
            if pay_later:
                try:
                    Payments.objects.create(
                        user=user,
                        business=business,
                        amount=order.final_amount,
                        payment_method=Payments.Method.COD,
                        status=Payments.Status.COD,
                        order_id=order.order_id,
                        payment_source='pay_later'
                    )
                except Exception as e:
                    logger.error(f"Failed to create pending payment for pay_later order {order.order_id}: {e}")

        # Prepare response
        # Fetch latest payment (if any) to expose status/method in response
        latest_payment = None
        try:
            latest_payment = Payments.objects.filter(order_id=order.order_id).order_by('-created_at').first()
        except Exception:
            latest_payment = None

        response_data = {
            'success': True,
            'message': 'Order created successfully',
            'data': {
                'order_id': order.order_id,
                'order_number': str(order.order_number),
                'token_num': order.token_num,
                'status': order.status,
                'payment_status': getattr(latest_payment, 'status', None),
                'payment_method': getattr(latest_payment, 'payment_method', None),
                'order_summary': {
                    'parcel_charges': float(parcel_charges),
                    'items_total': float(items_total),
                    'items_base_total': float(items_base_total),
                    'customizations_total': float(customizations_total),
                    'delivery_charges': float(delivery_charges),
                    'total_gst': float(total_gst),
                    'subtotal': float(subtotal),
                    'coupon_discount': float(discount_amount),
                    'after_coupon': float(after_coupon),
                    'wallet_points_used': float(wallet_points_to_use),
                    'wallet_points_value': float(wallet_points_value),
                    'final_amount': float(final_amount)
                },
                'items': order_items_data,
                'created_at': order.created_at.isoformat(),
                'estimated_delivery_time': order.estimated_delivery_time.isoformat() if order.estimated_delivery_time else None,
                'scheduled_time': order.scheduled_time.isoformat() if order.scheduled_time else None
            }
        }

        return Response(response_data, status=status.HTTP_201_CREATED)

    except Exception as e:
        return Response({
            'success': False,
            'error': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@swagger_auto_schema(methods=['POST'],tags=['Consumer'])
@api_view(['POST'])
def re_order(request):
    """
    Reorder service: Add items from a past grocery (R01) order back into the user's cart.

    URL: POST /kirazee/consumer/order/re-order?order_id=123

    Behavior:
    - Fetch order by order_id
    - Validate business type is R01 (grocery)
    - For each product_item in the order items, insert/update GroceryCart for the same user and business
    - Return a response similar to AddToCart (groceries) including groceries_details for that user and business
    """
    try:
        order_id = request.query_params.get('order_id')
        if not order_id:
            return JsonResponse({"message": "order_id parameter is required"}, status=400)

        # Fetch order and basic info
        order = get_object_or_404(Orders, order_id=order_id)
        user_id = order.user_id.user_id if order.user_id else None
        business_id = order.business_id.business_id

        if not user_id:
            return JsonResponse({"message": "Order has no associated user"}, status=400)

        # Determine business type
        business_type = order.business_id.businessType if hasattr(order.business_id, 'businessType') else None
        if business_type not in ['R01', 'R02', 'R08']:
            return JsonResponse({"message": "Re-order currently supports only R01 (Groceries), R02 (Restaurants), and R08 (Fashion)"}, status=400)

        # Get order items based on business type
        if business_type == 'R01':
            # Get grocery items (product_item_id is not null)
            items = OrderItems.objects.filter(order_id=order, product_item_id__isnull=False)
            if not items:
                return JsonResponse({"message": "No grocery items found in this order"}, status=404)
        elif business_type == 'R08':
            items = OrderItems.objects.filter(order_id=order, product_item_id__isnull=False)
            if not items:
                return JsonResponse({"message": "No fashion items found in this order"}, status=404)
        else:  # R02
            # Get menu items (menu_item_id is not null)
            items = OrderItems.objects.filter(order_id=order, menu_item_id__isnull=False)
            if not items:
                # Get debug info about what items exist in this order
                all_items = OrderItems.objects.filter(order_id=order)
                debug_items = []
                for item in all_items:
                    debug_items.append({
                        "menu_item_id": item.menu_item_id,
                        "product_item_id": item.product_item_id,
                        "item_name": item.item_name_snapshot
                    })
                
                return JsonResponse({
                    "message": "No menu items found in this order",
                    "debug_info": {
                        "order_id": order_id,
                        "business_type": business_type,
                        "total_order_items": len(all_items),
                        "items_in_order": debug_items
                    }
                }, status=404)

        last_item_details = None

        # Process items based on business type
        with connection.cursor() as cursor:
            if business_type == 'R01':
    # Get grocery items (product_item_id is not null)
                items = OrderItems.objects.filter(order_id=order, product_item_id__isnull=False)
                if not items:
                    return JsonResponse({"message": "No grocery items found in this order"}, status=404)

                items_processed = 0
                items_skipped = 0
                final_business_id = business_id
                
                for itm in items:
                    product_item_id = int(itm.product_item_id)
                    qty = int(itm.quantity)

                    # Check if product exists in Groceries_Products system (new system only)
                    cursor.execute(
                        """
                        SELECT gp.product_id, gp.product_name, gp.description, 
                               COALESCE(gpv.selling_price, 0) as selling_price, 
                               1 as is_active, gp.business_id
                        FROM Groceries_Products gp
                        LEFT JOIN Groceries_ProductVariants gpv ON gp.product_id = gpv.product_id AND gpv.is_active = 1
                        WHERE gp.product_id = %s AND gp.business_id = %s
                        ORDER BY gpv.variant_id ASC
                        LIMIT 1
                        """,
                        [product_item_id, business_id]
                    )
                    check_row = cursor.fetchone()
                    
                    # If not found with original business_id, try finding the item with any business_id
                    if not check_row:
                        cursor.execute(
                            """
                            SELECT gp.product_id, gp.product_name, gp.description, 
                                   COALESCE(gpv.selling_price, 0) as selling_price, 
                                   1 as is_active, gp.business_id
                            FROM Groceries_Products gp
                            LEFT JOIN Groceries_ProductVariants gpv ON gp.product_id = gpv.product_id AND gpv.is_active = 1
                            WHERE gp.product_id = %s
                            ORDER BY gpv.variant_id ASC
                            LIMIT 1
                            """,
                            [product_item_id]
                        )
                        check_row = cursor.fetchone()
                        
                        if check_row:
                            # Update business_id to the current one for this item
                            current_business_id = check_row[5]
                            final_business_id = current_business_id
                        else:
                            items_skipped += 1
                            continue
                    else:
                        current_business_id = business_id
                    
                    # Item exists and is active in new system
                    product_id, product_name, description, selling_price, is_active, item_business_id = check_row
                    description = description or ""
                    selling_price = selling_price or 0
                    
                    cust_data = itm.customizations

                    # Check if already in Groceries_cart (new system cart)
                    cursor.execute(
                        "SELECT id, quantity, customizations FROM Groceries_cart WHERE user_id = %s AND business_id = %s AND product_id = %s",
                        [user_id, current_business_id, product_id]
                    )
                    existing_rows = cursor.fetchall()
                    found_match = None
                    
                    for r in existing_rows:
                        rc_id, rc_qty, rc_cust = r
                        c1 = cust_data if cust_data is not None else []
                        c2 = rc_cust
                        if isinstance(c2, str):
                            try: c2 = json.loads(c2)
                            except: c2 = []
                        if c2 is None: c2 = []
                        if c1 == c2:
                            found_match = (rc_id, rc_qty)
                            break
                    
                    if found_match:
                        cart_id, existing_qty = found_match
                        new_qty = int(existing_qty) + qty
                        cursor.execute(
                            "UPDATE Groceries_cart SET quantity = %s, updated_at = NOW() WHERE id = %s",
                            [new_qty, cart_id]
                        )
                    else:
                        cursor.execute("SELECT COALESCE(MAX(id), 1100) + 1 FROM Groceries_cart")
                        new_id = cursor.fetchone()[0]
                        cust_json = json.dumps(cust_data if cust_data else [])
                        cursor.execute(
                            """
                            INSERT INTO Groceries_cart (id, user_id, product_id, quantity, business_id, customizations, added_at, updated_at)
                            VALUES (%s, %s, %s, %s, %s, %s, NOW(), NOW())
                            """,
                            [new_id, user_id, product_id, qty, current_business_id, cust_json]
                        )
                        cart_id = new_id
                        new_qty = qty

                    # Track last item details for response
                    last_item_details = {
                        "item_id": int(product_id),
                        "item_name": product_name,
                        "description": description,
                        "selling_price": str(selling_price),
                        "quantity": new_qty
                    }
                    items_processed += 1
                
                # If no items were processed, return error
                if items_processed == 0:
                    return JsonResponse({
                        "message": "No valid grocery items could be added to cart",
                        "debug": {
                            "order_id": order_id,
                            "business_id": business_id,
                            "user_id": user_id,
                            "items_attempted": len(items),
                            "items_skipped": items_skipped,
                            "system": "Using Groceries_Products system only",
                            "note": "Items may not exist in Groceries_Products table or may be inactive"
                        }
                    }, status=400)

            elif business_type == 'R08':
                items = OrderItems.objects.filter(order_id=order, product_item_id__isnull=False)
                if not items:
                    return JsonResponse({"message": "No fashion items found in this order"}, status=404)

                items_processed = 0
                items_skipped = 0
                final_business_id = business_id

                for itm in items:
                    variant_id = int(itm.product_item_id)
                    qty = int(itm.quantity)

                    cursor.execute(
                        """
                        SELECT fpv.variant_id, fpv.selling_price, fp.name, fp.description, fp.main_image, fpv.stock, fpv.business_id
                        FROM fashion_product_variants fpv
                        JOIN fashion_products fp ON fpv.product_id = fp.product_id
                        WHERE fpv.variant_id=%s AND fpv.business_id=%s AND fpv.is_active=1
                        LIMIT 1
                        """,
                        [variant_id, business_id]
                    )
                    check_row = cursor.fetchone()

                    if not check_row:
                        cursor.execute(
                            """
                            SELECT fpv.variant_id, fpv.selling_price, fp.name, fp.description, fp.main_image, fpv.stock, fpv.business_id
                            FROM fashion_product_variants fpv
                            JOIN fashion_products fp ON fpv.product_id = fp.product_id
                            WHERE fpv.variant_id=%s AND fpv.is_active=1
                            LIMIT 1
                            """,
                            [variant_id]
                        )
                        check_row = cursor.fetchone()

                        if check_row:
                            current_business_id = check_row[6]
                            final_business_id = current_business_id
                        else:
                            items_skipped += 1
                            continue
                    else:
                        current_business_id = business_id

                    db_variant_id, selling_price, item_name, description, main_image, stock, item_business_id = check_row
                    description = description or ""
                    selling_price = selling_price or 0
                    
                    cust_data = itm.customizations

                    cursor.execute(
                        "SELECT id, quantity, customizations FROM fashion_cart WHERE user_id=%s AND business_id=%s AND variant_id=%s",
                        [user_id, current_business_id, db_variant_id]
                    )
                    existing_rows = cursor.fetchall()
                    found_match = None
                    
                    for r in existing_rows:
                        rc_id, rc_qty, rc_cust = r
                        c1 = cust_data if cust_data is not None else []
                        c2 = rc_cust
                        if isinstance(c2, str):
                            try: c2 = json.loads(c2)
                            except: c2 = []
                        if c2 is None: c2 = []
                        if c1 == c2:
                            found_match = (rc_id, rc_qty)
                            break

                    if found_match:
                        cart_id, existing_qty = found_match
                        new_qty = int(existing_qty) + qty
                        cursor.execute(
                            "UPDATE fashion_cart SET quantity=%s, updated_at=NOW() WHERE id=%s",
                            [new_qty, cart_id]
                        )
                    else:
                        cursor.execute("SELECT COALESCE(MAX(id), 1100) + 1 FROM fashion_cart")
                        new_id = cursor.fetchone()[0]
                        cust_json = json.dumps(cust_data if cust_data else [])
                        cursor.execute(
                            """
                            INSERT INTO fashion_cart (id, user_id, variant_id, quantity, business_id, customizations, added_at, updated_at)
                            VALUES (%s, %s, %s, %s, %s, %s, NOW(), NOW())
                            """,
                            [new_id, user_id, db_variant_id, qty, current_business_id, cust_json]
                        )
                        cart_id = new_id
                        new_qty = qty

                    last_item_details = {
                        "item_id": int(db_variant_id),
                        "item_name": item_name,
                        "description": description,
                        "selling_price": str(selling_price),
                        "quantity": new_qty
                    }
                    items_processed += 1

                if items_processed == 0:
                    return JsonResponse({
                        "message": "No valid fashion items could be added to cart",
                        "debug_info": {
                            "total_items_in_order": len(items),
                            "items_skipped": items_skipped,
                            "business_id": business_id,
                            "user_id": user_id
                        }
                    }, status=400)
            
            else:  # R02 - Handle restaurant menu items
                items_processed = 0
                items_skipped = 0
                final_business_id = business_id  # Track the business_id to use for cart fetching
                for itm in items:
                    menu_item_id = int(itm.menu_item_id)
                    qty = int(itm.quantity)

                    # First try with the original business_id
                    cursor.execute(
                        """
                        SELECT item_id, item_name, description, selling_price, is_active, status, business_id
                        FROM menuItems
                        WHERE item_id=%s AND business_id=%s AND is_active=1 AND status=1
                        """,
                        [menu_item_id, business_id]
                    )
                    check_row = cursor.fetchone()
                    
                    # If not found with original business_id, try finding the item with any business_id
                    if not check_row:
                        cursor.execute(
                            """
                            SELECT item_id, item_name, description, selling_price, is_active, status, business_id
                            FROM menuItems
                            WHERE item_id=%s AND is_active=1 AND status=1
                            """,
                            [menu_item_id]
                        )
                        check_row = cursor.fetchone()
                        
                        if check_row:
                            # Update business_id to the current one for this item
                            current_business_id = check_row[6]
                            final_business_id = current_business_id  # Update final business_id
                        else:
                            # Item doesn't exist or is inactive
                            items_skipped += 1
                            continue
                    else:
                        current_business_id = business_id
                    
                    # Item exists and is active
                    row = check_row

                    db_item_id, item_name, description, selling_price, is_active, status, item_business_id = row
                    description = description or ""
                    selling_price = selling_price or 0

                    cust_data = itm.customizations
                    
                    # Check if already in menu cart with SAME customizations
                    cursor.execute(
                        "SELECT id, quantity, customizations FROM menuCart WHERE user_id=%s AND business_id=%s AND menu_id=%s",
                        [user_id, current_business_id, db_item_id]
                    )
                    existing_rows = cursor.fetchall()
                    found_match = None
                    
                    for r in existing_rows:
                        rc_id, rc_qty, rc_cust = r
                        c1 = cust_data if cust_data is not None else []
                        c2 = rc_cust
                        if isinstance(c2, str):
                            try: c2 = json.loads(c2)
                            except: c2 = []
                        if c2 is None: c2 = []
                        if c1 == c2:
                            found_match = (rc_id, rc_qty)
                            break

                    if found_match:
                        cart_id, existing_qty = found_match
                        new_qty = int(existing_qty) + qty
                        cursor.execute(
                            "UPDATE menuCart SET quantity=%s, updated_at=NOW() WHERE id=%s",
                            [new_qty, cart_id]
                        )
                    else:
                        cursor.execute("SELECT COALESCE(MAX(id), 1100) + 1 FROM menuCart")
                        new_id = cursor.fetchone()[0]
                        cust_json = json.dumps(cust_data if cust_data else [])
                        cursor.execute(
                            """
                            INSERT INTO menuCart (id, user_id, menu_id, quantity, business_id, customizations, added_at, updated_at)
                            VALUES (%s, %s, %s, %s, %s, %s, NOW(), NOW())
                            """,
                            [new_id, user_id, db_item_id, qty, current_business_id, cust_json]
                        )
                        cart_id = new_id
                        new_qty = qty

                    # Track last item details for response
                    last_item_details = {
                        "item_id": int(db_item_id),
                        "item_name": item_name,
                        "description": description,
                        "selling_price": str(selling_price),
                        "quantity": new_qty
                    }
                    items_processed += 1
                
                # If no items were processed, return detailed debug info
                if items_processed == 0:
                    # Get details about what items we were looking for
                    debug_items = []
                    for itm in items:
                        menu_item_id = int(itm.menu_item_id)
                        
                        # Check what exists in menuItems table for this item
                        cursor.execute(
                            """
                            SELECT item_id, item_name, is_active, status, business_id
                            FROM menuItems
                            WHERE item_id=%s
                            """,
                            [menu_item_id]
                        )
                        menu_check = cursor.fetchone()
                        
                        debug_items.append({
                            "order_menu_item_id": menu_item_id,
                            "order_item_name": itm.item_name_snapshot,
                            "exists_in_menu_table": menu_check is not None,
                            "menu_item_details": {
                                "item_id": menu_check[0] if menu_check else None,
                                "item_name": menu_check[1] if menu_check else None,
                                "is_active": menu_check[2] if menu_check else None,
                                "status": menu_check[3] if menu_check else None,
                                "business_id": menu_check[4] if menu_check else None
                            } if menu_check else None
                        })
                    
                    return JsonResponse({
                        "message": "No valid menu items could be added to cart",
                        "debug_info": {
                            "total_items_in_order": len(items),
                            "items_skipped": items_skipped,
                            "business_id": business_id,
                            "user_id": user_id,
                            "items_analysis": debug_items
                        }
                    }, status=400)

        # Build cart details based on business type
        with connection.cursor() as cursor:
            if business_type == 'R01':
                # Get grocery cart details (use final_business_id which may have been updated)
                cursor.execute(
                    """
                    SELECT c.id, c.product_id, c.quantity, 
                           gp.product_name, gp.description, 
                           COALESCE(gpv.selling_price, 0) as selling_price, 
                           gp.main_image, c.customizations
                    FROM Groceries_cart c
                    JOIN Groceries_Products gp ON c.product_id = gp.product_id
                    LEFT JOIN Groceries_ProductVariants gpv ON gp.product_id = gpv.product_id AND gpv.is_active = 1
                    WHERE c.user_id = %s AND c.business_id = %s
                    ORDER BY c.id, gpv.variant_id ASC
                    """,
                    [user_id, final_business_id]
                )
                cart_rows = cursor.fetchall()
                
                # Group by cart item to handle multiple variants (take first variant only)
                cart_items_dict = {}
                for r in cart_rows:
                    cart_id = r[0]
                    if cart_id not in cart_items_dict:
                        image_url = build_s3_file_url(r[6])

                        cust = r[7]
                        if isinstance(cust, (bytes, bytearray)):
                            try: cust = cust.decode('utf-8')
                            except: cust = None
                        try: cust_json = json.loads(cust) if cust else []
                        except: cust_json = []

                        cart_items_dict[cart_id] = {
                            "cart_id": r[0],
                            "item_id": int(r[1]),
                            "quantity": r[2],
                            "item_name": r[3] or "",
                            "description": r[4] or "",
                            "selling_price": str(r[5] or 0),
                            "image_url": image_url,
                            "customizations": cust_json
                        }
                
                cart_details = list(cart_items_dict.values())

                return JsonResponse({
                    "message": "Grocery item added to cart successfully",
                    "item_details": last_item_details,
                    "groceries_details": cart_details
                }, status=200)

            elif business_type == 'R08':
                cursor.execute(
                    """
                    SELECT c.id, c.variant_id, c.quantity, fp.name, fp.description, fpv.selling_price, fp.main_image, c.customizations
                    FROM fashion_cart c
                    JOIN fashion_product_variants fpv ON c.variant_id = fpv.variant_id
                    JOIN fashion_products fp ON fpv.product_id = fp.product_id
                    WHERE c.user_id=%s AND c.business_id=%s AND fpv.is_active=1
                    ORDER BY c.id, fpv.variant_id
                    """,
                    [user_id, final_business_id]
                )
                cart_rows = cursor.fetchall()

                cart_details = []
                for r in cart_rows:
                    image_url = build_s3_file_url(r[6])

                    cust = r[7] if len(r) > 7 else None
                    if isinstance(cust, (bytes, bytearray)):
                        try:
                            cust = cust.decode('utf-8')
                        except Exception:
                            cust = None
                    try:
                        cust_json = json.loads(cust) if cust else []
                    except Exception:
                        cust_json = []

                    cart_details.append({
                        "cart_id": r[0],
                        "item_id": r[1],
                        "quantity": r[2],
                        "item_name": r[3],
                        "description": r[4],
                        "selling_price": str(r[5]),
                        "image_url": image_url,
                        "customizations": cust_json
                    })

                return JsonResponse({
                    "message": "Fashion item added to cart successfully",
                    "item_details": last_item_details,
                    "fashion_details": cart_details
                }, status=200)
                
            else:  # R02 - Restaurant menu cart
                # Get menu cart details (use final_business_id which may have been updated)
                cursor.execute(
                    """
                    SELECT c.id, c.menu_id, c.quantity, m.item_name, m.description, m.selling_price, m.item_image, c.customizations
                    FROM menuCart c
                    JOIN menuItems m ON c.menu_id = m.item_id
                    WHERE c.user_id=%s AND c.business_id=%s
                    """,
                    [user_id, final_business_id]
                )
                cart_rows = cursor.fetchall()
                
                cart_details = []
                for r in cart_rows:
                    image_url = build_s3_file_url(r[6])
                    
                    cust = r[7]
                    if isinstance(cust, (bytes, bytearray)):
                        try: cust = cust.decode('utf-8')
                        except: cust = None
                    try: cust_json = json.loads(cust) if cust else []
                    except: cust_json = []

                    cart_details.append({
                        "cart_id": r[0],
                        "item_id": int(r[1]),
                        "quantity": r[2],
                        "item_name": r[3] or "",
                        "description": r[4] or "",
                        "selling_price": str(r[5] or 0),
                        "image_url": image_url,
                        "customizations": cust_json
                    })

                return JsonResponse({
                    "message": "Menu item added to cart successfully",
                    "item_details": last_item_details,
                    "menu_details": cart_details,
                    "debug_info": {
                        "cart_rows_found": len(cart_rows),
                        "business_id": business_id,
                        "user_id": user_id,
                        "business_type": business_type
                    }
                }, status=200)

    except Exception as e:
        import traceback
        return JsonResponse({
            "message": f"Failed to re-order: {str(e)}", 
            "debug": traceback.format_exc()
        }, status=500)


@swagger_auto_schema(methods=['PUT'],tags=['Consumer'])
@api_view(['PUT'])
def update_order_status(request, order_id):
    """
    Update order status for both standard Orders and GroceriesOrders
    Supports dual order system with automatic detection
    """
    try:
        # Get data from request - support both old and new payload formats
        action = request.data.get('action')
        user_id = request.data.get('user_id')
        business_id = request.data.get('business_id')
        notes = request.data.get('notes', '')
        estimated_delivery_time = request.data.get('estimated_delivery_time')
        # Accept alternative keys and query params for robustness
        if not user_id:
            user_id = request.query_params.get('userID') or request.query_params.get('user_id')
        # Normalize business_id from body or query
        if not business_id:
            business_id = (
                request.data.get('businessID') or request.data.get('businessId') or
                request.query_params.get('business_id') or request.query_params.get('businessID') or request.query_params.get('businessId')
            )
        
        # Check for alternative payload formats that frontend might send
        if not action:
            # Try common alternative field names
            action = request.data.get('status') or request.data.get('new_status') or request.data.get('order_status')
            
        # Special handling for frontend that might send empty request body but expects confirm action
        if not action and not request.data:
            # If no data is sent, default to confirm_order for backward compatibility
            action = 'confirm_order'
            logger.info(f"No data received, defaulting to confirm_order for order {order_id}")
            
        # Handle case where frontend sends action as part of URL or different structure
        if not action and hasattr(request, 'resolver_match'):
            # Check if action might be in URL kwargs or other places
            url_kwargs = getattr(request.resolver_match, 'kwargs', {})
            action = url_kwargs.get('action')
        
        # Debug logging
        logger.info(f"update_order_status called with order_id={order_id}")
        logger.info(f"Request method: {request.method}")
        logger.info(f"Request data: {request.data}")
        logger.info(f"Content type: {request.content_type}")
        logger.info(f"Determined action: {action}")

        # If still no action found, try to infer from context or use default
        if not action:
            # For standard orders, if no action specified, assume it's a confirm action
            # This maintains backward compatibility with frontend
            action = 'confirm_order'
            logger.warning(f"No action specified for order {order_id}, defaulting to confirm_order")
        
        # Final validation - this should never happen now, but keeping for safety
        if not action:
            return Response({
                'success': False,
                'error': 'Unable to determine action from request',
                'received_data': request.data,
                'request_method': request.method,
                'content_type': request.content_type,
                'expected_fields': ['action', 'status', 'new_status', 'order_status']
            }, status=status.HTTP_400_BAD_REQUEST)

        # First, try to find the order in standard Orders table
        standard_order = None
        grocery_order = None
        order_system = None
        
        try:
            standard_order = Orders.objects.get(order_id=order_id)
            order_system = 'standard'
        except Orders.DoesNotExist:
            pass
        
        # If not found in standard orders, check grocery orders
        if not standard_order:
            try:
                grocery_order = GroceriesOrders.objects.get(order_id=order_id)
                order_system = 'grocery'
            except GroceriesOrders.DoesNotExist:
                pass
        
        # If order not found in either system
        if not standard_order and not grocery_order:
            return Response({
                'success': False,
                'error': 'No Orders matches the given query.',
                'debug_info': {
                    'order_id': order_id,
                    'searched_in': ['orders', 'Groceries_orders'],
                    'message': 'Order not found in either standard or grocery order systems'
                }
            }, status=status.HTTP_404_NOT_FOUND)
        
        # Handle standard orders
        if order_system == 'standard':
            order = standard_order
            
            # Validate business ownership
            if business_id and order.business_id.business_id != business_id:
                return Response({
                    'success': False,
                    'error': 'Unauthorized: Order does not belong to this business'
                }, status=status.HTTP_403_FORBIDDEN)

            # Direct status update for standard orders (no FSM restrictions)
            try:
                prev_status = order.status
                action = action.lower()  # Make case-insensitive
                cancelled_by = str(request.data.get('cancelled_by', '')).lower()
                changed_by_id = (
                    request.data.get('changed_by_id') or request.data.get('changedById') or
                    request.query_params.get('changed_by_id') or request.query_params.get('changedById')
                )
                # Infer merchant-side cancellation without relying on DB schema
                allowed_cancel_sources = ['business', 'merchant', 'chef']
                is_merchant_side = False
                try:
                    if business_id and str(order.business_id.business_id) == str(business_id):
                        is_merchant_side = True
                except Exception:
                    pass
                # If actor user_id is provided and differs from the order's customer, treat as merchant-side
                try:
                    order_customer_id = str(getattr(order.user_id, 'user_id', '') or '')
                    actor_user_id = str(user_id) if user_id is not None else ''
                    if actor_user_id and order_customer_id and actor_user_id != order_customer_id:
                        is_merchant_side = True
                except Exception:
                    pass
                # If actor is mapped to this business, treat as merchant-side
                try:
                    if user_id and BusinessMapping.objects.filter(user__user_id=user_id, business=order.business_id).exists():
                        is_merchant_side = True
                except Exception:
                    pass
                effective_cancelled_by = (
                    cancelled_by if cancelled_by in allowed_cancel_sources else (
                        'business' if is_merchant_side or changed_by_id else ''
                    )
                )
                success_message = 'Order status updated successfully'
                status_metadata = {'estimated_delivery_time': estimated_delivery_time}
                response_extra = {}
                
                # Map common status names and actions to actual status values
                status_mapping = {
                    # Action names to status
                    'confirm_order': 'confirmed',
                    'notify_order': 'notified',
                    'start_preparing': 'preparing',
                    'mark_ready': 'ready',
                    'dispatch_for_delivery': 'dispatched',
                    'start_travelling': 'travelling',
                    'out_for_delivery': 'out_for_delivery',
                    'complete_order': 'delivered',
                    'cancel_order': 'cancelled',
                    # Status names directly
                    'pending': 'pending',
                    'confirmed': 'confirmed',
                    'notified': 'notified',
                    'preparing': 'preparing',
                    'ready': 'ready',
                    'assigned': 'assigned',
                    'picked_up': 'picked_up',
                    'dispatched': 'dispatched',
                    'travelling': 'travelling',
                    'out_for_delivery': 'out_for_delivery',
                    'delivered': 'delivered',
                    'cancelled': 'cancelled'
                }
                
                if action not in status_mapping:
                    return Response({
                        'success': False,
                        'error': f'Invalid action/status: {action}. Valid options are: {list(status_mapping.keys())}',
                        'received_action': request.data.get('action'),
                        'received_status': request.data.get('status')
                    }, status=status.HTTP_400_BAD_REQUEST)

                # Get the target status
                new_status = status_mapping[action]
                # If cancelling and no actor inferred, default to business (merchant-side)
                try:
                    if new_status == 'cancelled' and effective_cancelled_by not in allowed_cancel_sources:
                        effective_cancelled_by = 'business'
                except Exception:
                    pass
                
                # Update the order status directly (no FSM validation)
                order.status = new_status
                
                # Special handling for cancelled status - also cancel the payment
                if new_status == 'cancelled':
                    from .models import Payments
                    # Update any pending payments for this order to cancelled
                    cancelled_payments = Payments.objects.filter(
                        order_id=order_id, 
                        status__in=['pending', 'initiated']
                    ).update(status='cancelled')
                    if cancelled_payments > 0:
                        logger.info(f"Cancelled {cancelled_payments} pending payment(s) for order {order_id}")
                    if prev_status != 'cancelled':
                        with transaction.atomic():
                            for oi in OrderItems.objects.select_for_update().filter(order_id=order):
                                qty = int(oi.quantity) if oi.quantity is not None else 0
                                if oi.menu_item_id:
                                    try:
                                        mi = MenuItems.objects.select_for_update().get(item_id=oi.menu_item_id)
                                        if mi.quantity is not None:
                                            mi.quantity = mi.quantity + qty
                                            mi.save(update_fields=['quantity'])
                                    except MenuItems.DoesNotExist:
                                        pass
                                elif oi.product_item_id:
                                    try:
                                        if order.business_id.businessType == 'R01':
                                            try:
                                                var = GroceriesProductVariants.objects.select_for_update().get(variant_id=oi.product_item_id)
                                                if var.stock is not None:
                                                    var.stock = var.stock + qty
                                                    var.save(update_fields=['stock'])
                                            except GroceriesProductVariants.DoesNotExist:
                                                pass
                                        elif order.business_id.businessType == 'R02':
                                            try:
                                                pi = productItems.objects.select_for_update().get(item_id=oi.product_item_id)
                                                if pi.stock is not None:
                                                    pi.stock = pi.stock + qty
                                                    pi.save(update_fields=['stock'])
                                            except productItems.DoesNotExist:
                                                pass
                                    except Exception:
                                        pass
                    
                    # Merchant-cancel compensation for standard orders
                    # Check if payment was successful
                    paid_success = False
                    try:
                        latest_payment = Payments.objects.filter(order_id=order.order_id).order_by('-created_at').first()
                        if latest_payment:
                            payment_status = str(latest_payment.status).lower()
                            if payment_status in ['success', 'completed', 'paid', 'successful']:
                                paid_success = True
                                logger.info(f"Order {order.order_id} has successful payment: {latest_payment.status}")
                            else:
                                logger.info(f"Order {order.order_id} payment status: {latest_payment.status} (not considered successful)")
                    except Exception as e:
                        logger.error(f"Error checking payment status for order {order.order_id}: {str(e)}")
                        paid_success = False
                    
                    # Process compensation if cancelled by merchant and payment was successful
                    if effective_cancelled_by in ['business', 'merchant', 'chef'] and paid_success:
                        try:
                            with transaction.atomic():
                                locked_order = Orders.objects.select_for_update().get(order_id=order.order_id)
                                voucher_name = f"COMP-STD-{locked_order.order_id}"
                                coupon_code_target = f"VCHR-STD-{locked_order.order_id}"
                                existing_coupon = (
                                    Coupons.objects.filter(coupon_code=coupon_code_target).first()
                                    or Coupons.objects.filter(name=voucher_name).first()
                                )
                                if existing_coupon:
                                    success_message = 'Order cancelled by restaurant; voucher already issued.'
                                    status_metadata.update({
                                        'compensation': 'voucher',
                                        'voucher_code': existing_coupon.coupon_code,
                                        'voucher_value': float(existing_coupon.discount_value),
                                        'cancelled_by': effective_cancelled_by
                                    })
                                    response_extra['voucher'] = {
                                        'coupon_code': existing_coupon.coupon_code,
                                        'discount_value': float(existing_coupon.discount_value),
                                        'valid_to': existing_coupon.valid_to.isoformat() if existing_coupon.valid_to else None,
                                        'max_redemptions_per_user': existing_coupon.max_redemptions_per_user
                                    }
                                    try:
                                        CouponRules.objects.get_or_create(
                                            coupon_id=existing_coupon,
                                            rule_type=CouponRules.RuleType.ALLOWED_USER,
                                            defaults={'rule_value': {'user_id': int(locked_order.user_id.user_id)}}
                                        )
                                    except Exception:
                                        pass
                                else:
                                    now_ts = timezone.now() if getattr(settings, 'USE_TZ', False) else datetime.now()
                                    valid_to_ts = now_ts + timedelta(days=30)
                                    coupon_payload = {
                                        'coupon_code': coupon_code_target,
                                        'name': voucher_name,
                                        'discount_type': 'fixed_amount',
                                        'discount_value': str(locked_order.final_amount),
                                        'created_by': 'business_owner',
                                        'business_id': locked_order.business_id.business_id,
                                        'valid_from': now_ts.isoformat(),
                                        'valid_to': valid_to_ts.isoformat(),
                                        'is_active': True,
                                        'max_usage_total': 1,
                                        'max_redemptions_per_user': 1,
                                        'points_required': 0
                                    }
                                    cserializer = CouponSerializer(data=coupon_payload)
                                    if cserializer.is_valid():
                                        created_coupon = cserializer.save()
                                        try:
                                            CouponRules.objects.get_or_create(
                                                coupon_id=created_coupon,
                                                rule_type=CouponRules.RuleType.ALLOWED_USER,
                                                defaults={'rule_value': {'user_id': int(locked_order.user_id.user_id)}}
                                            )
                                        except Exception:
                                            pass
                                        success_message = 'Order cancelled by restaurant; voucher issued.'
                                        status_metadata.update({
                                            'compensation': 'voucher',
                                            'voucher_code': created_coupon.coupon_code,
                                            'voucher_value': float(created_coupon.discount_value),
                                            'cancelled_by': effective_cancelled_by
                                        })
                                        response_extra['voucher'] = {
                                            'coupon_code': created_coupon.coupon_code,
                                            'discount_value': float(created_coupon.discount_value),
                                            'valid_to': created_coupon.valid_to.isoformat() if created_coupon.valid_to else None,
                                            'max_redemptions_per_user': created_coupon.max_redemptions_per_user
                                        }
                                        try:
                                            if getattr(locked_order.user_id, 'user_id', None):
                                                user_id_int = int(locked_order.user_id.user_id)
                                                notif_result = send_order_notification(
                                                    user_id_int,
                                                    "We're sorry — voucher issued",
                                                    f"Order #{locked_order.order_id} was cancelled. Voucher {created_coupon.coupon_code} issued.",
                                                    {
                                                        'type': 'VOUCHER_ISSUED',
                                                        'order_id': str(locked_order.order_id),
                                                        'coupon_code': created_coupon.coupon_code,
                                                        'discount_value': str(created_coupon.discount_value),
                                                        'valid_to': created_coupon.valid_to.isoformat() if created_coupon.valid_to else ''
                                                    }
                                                )
                                                email_result = send_email_notification(
                                                    user_id_int,
                                                    f"Voucher issued for cancelled order #{locked_order.order_id}",
                                                    f"Order #{locked_order.order_id} was cancelled. Voucher {created_coupon.coupon_code} worth ₹{created_coupon.discount_value} has been issued. Valid until {created_coupon.valid_to.isoformat() if created_coupon.valid_to else ''}.",
                                                    {
                                                        'type': 'VOUCHER_ISSUED',
                                                        'order_id': str(locked_order.order_id),
                                                        'coupon_code': created_coupon.coupon_code,
                                                        'discount_value': str(created_coupon.discount_value),
                                                        'valid_to': created_coupon.valid_to.isoformat() if created_coupon.valid_to else '',
                                                        'body': (
                                                            "We regret to inform you that your recent order has been cancelled due to unforeseen circumstances. "
                                                            "As a gesture of goodwill, we've issued a voucher for you to place a new order at your convenience. "
                                                            "Please use this voucher during your next purchase to enjoy a seamless experience. "
                                                            "Thank you for your understanding and continued support."
                                                        )
                                                    }
                                                )
                                                logger.info(f"Voucher notification sent for order {locked_order.order_id}: push={notif_result is not None}, email={email_result}")
                                        except Exception as e:
                                            logger.error(f"Failed to send voucher notification for order {locked_order.order_id}: {str(e)}", exc_info=True)
                                    else:
                                        try:
                                            points_to_credit = (locked_order.final_amount * Decimal('10'))
                                            txn = WalletPoints.atomic_transaction(
                                                user_id=locked_order.user_id,
                                                points=points_to_credit,
                                                transaction_type=WalletPoints.TransactionType.REFUNDED,
                                                description=f'Compensation for cancelled order #{locked_order.order_number}',
                                                related_order=locked_order
                                            )
                                            success_message = 'Order cancelled; amount credited to wallet as compensation.'
                                            status_metadata.update({
                                                'compensation': 'wallet',
                                                'credited_amount': float(locked_order.final_amount),
                                                'cancelled_by': effective_cancelled_by
                                            })
                                            response_extra['wallet_credit'] = {
                                                'credited_amount': float(locked_order.final_amount),
                                                'wallet_balance': float(txn.balance_after * Decimal('0.10'))
                                            }
                                            try:
                                                if getattr(locked_order.user_id, 'user_id', None):
                                                    user_id_int = int(locked_order.user_id.user_id)
                                                    notif_result = send_order_notification(
                                                        user_id_int,
                                                        'Order cancelled — wallet credited',
                                                        f"Order #{locked_order.order_id} was cancelled. Amount credited to wallet.",
                                                        {
                                                            'type': 'WALLET_CREDITED',
                                                            'order_id': str(locked_order.order_id),
                                                            'credited_amount': str(locked_order.final_amount)
                                                        }
                                                    )
                                                    email_result = send_email_notification(
                                                        user_id_int,
                                                        f"Wallet credited for cancelled order #{locked_order.order_id}",
                                                        f"Order #{locked_order.order_id} was cancelled. ₹{locked_order.final_amount} has been credited to your wallet.",
                                                        {
                                                            'type': 'WALLET_CREDITED',
                                                            'order_id': str(locked_order.order_id),
                                                            'credited_amount': str(locked_order.final_amount)
                                                        }
                                                    )
                                                    logger.info(f"Wallet credit notification sent for order {locked_order.order_id}: push={notif_result is not None}, email={email_result}")
                                            except Exception as e:
                                                logger.error(f"Failed to send wallet credit notification for order {locked_order.order_id}: {str(e)}", exc_info=True)
                                        except Exception:
                                            pass

                        except Exception as e:
                            logger.error(f"Error processing compensation for cancelled order: {str(e)}")

                # Handle special cases for delivered status
                if new_status == 'delivered':
                    # Use timezone-aware or naive datetime based on Django settings
                    if getattr(settings, 'USE_TZ', False):
                        order.actual_delivery_time = timezone.now()
                    else:
                        order.actual_delivery_time = datetime.now()
                
                # Update estimated delivery time if provided
                if estimated_delivery_time:
                    # Parse and handle timezone-aware datetime strings
                    if isinstance(estimated_delivery_time, str):
                        parsed_dt = date_parser.parse(estimated_delivery_time)
                        # Convert to naive datetime if USE_TZ is False
                        if not getattr(settings, 'USE_TZ', False) and parsed_dt.tzinfo is not None:
                            order.estimated_delivery_time = parsed_dt.replace(tzinfo=None)
                        else:
                            order.estimated_delivery_time = parsed_dt
                    else:
                        order.estimated_delivery_time = estimated_delivery_time
                
                order.save()
                try:
                    create_status_log(
                        'standard',
                        order.order_id,
                        prev_status,
                        new_status,
                        user_id=user_id,
                        role='business',
                        notes=notes,
                        source='consumer.update_order_status',
                        metadata=status_metadata
                    )
                except Exception:
                    pass
                
                # Send feedback request email when order is delivered or completed
                if new_status in ['delivered', 'completed']:
                    try:
                        from .feedback_notifications import trigger_feedback_request
                        trigger_feedback_request(order.order_id, 'standard')
                    except Exception as e:
                        logger.error(f"Failed to trigger feedback request for standard order {order.order_id}: {e}")
                    
                    # Assign behavior-based tags when order is delivered
                    if new_status == 'delivered':
                        try:
                            from .tag_assignment_service import TagAssignmentService
                            TagAssignmentService.assign_behavior_tags_on_order_completion(order.user_id.user_id)
                        except Exception as e:
                            logger.error(f"Failed to assign behavior tags for user {order.user_id.user_id}: {e}")
                
                # Return all possible next statuses (no restrictions)
                all_possible_statuses = [
                    'pending', 'confirmed', 'notified', 'preparing', 'ready', 
                    'assigned', 'picked_up', 'dispatched', 'travelling', 
                    'out_for_delivery', 'delivered', 'cancelled'
                ]
                
                available_transitions = []
                for status_option in all_possible_statuses:
                    if status_option != new_status:  # Don't include current status
                        available_transitions.append({
                            'action': status_option,
                            'target_status': status_option,
                            'description': status_option.replace('_', ' ').title()
                        })

                return Response({
                    'success': True,
                    'message': success_message,
                    'order_system': 'standard',
                    'action_performed': action,
                    'data': {
                        'order_id': order.order_id,
                        'order_number': str(order.order_number),
                        'current_status': order.status,
                        'available_transitions': available_transitions,
                        'updated_at': order.updated_at.isoformat()
                    },
                    **response_extra
                }, status=status.HTTP_200_OK)

            except Exception as update_error:
                return Response({
                    'success': False,
                    'error': f'Status update failed: {str(update_error)}'
                }, status=status.HTTP_400_BAD_REQUEST)
        
        # Handle grocery orders
        elif order_system == 'grocery':
            order = grocery_order
            
            # Validate business ownership
            if business_id and order.business.business_id != business_id:
                return Response({
                    'success': False,
                    'error': 'Unauthorized: Order does not belong to this business'
                }, status=status.HTTP_403_FORBIDDEN)
            
            # Direct status update for grocery orders (no validation restrictions)
            action = action.lower()  # Make case-insensitive
            
            # Map common status names and actions to actual status values
            grocery_status_mapping = {
                # Action names to status
                'confirm_order': 'confirmed',
                'notify_order': 'notified',
                'start_preparing': 'preparing', 
                'start_packing': 'packing',
                'mark_ready': 'ready',
                'assign_order': 'assigned',
                'pickup_order': 'picked_up',
                'dispatch_for_delivery': 'dispatched',
                'start_travelling': 'travelling',
                'out_for_delivery': 'out_for_delivery',
                'complete_order': 'delivered',
                'cancel_order': 'cancelled',
                # Status names directly
                'pending': 'pending',
                'confirmed': 'confirmed',
                'notified': 'notified',
                'preparing': 'preparing',
                'packing': 'packing',
                'ready': 'ready',
                'assigned': 'assigned',
                'picked_up': 'picked_up',
                'dispatched': 'dispatched',
                'travelling': 'travelling',
                'out_for_delivery': 'out_for_delivery',
                'delivered': 'delivered',
                'cancelled': 'cancelled'
            }
            
            if action not in grocery_status_mapping:
                return Response({
                    'success': False,
                    'error': f'Invalid action/status: {action}. Valid options are: {list(grocery_status_mapping.keys())}',
                    'received_action': request.data.get('action'),
                    'received_status': request.data.get('status')
                }, status=status.HTTP_400_BAD_REQUEST)
            
            # Get the new status
            new_status = grocery_status_mapping[action]
            # If cancelling and no actor inferred, default to business (merchant-side)
            try:
                # effective_cancelled_by is computed below in cancel branch; this default will apply after computation
                pass
            except Exception:
                pass
            prev_status = order.order_status
            # Defaults for metadata/response to avoid NameError on non-cancel paths
            success_message = 'Grocery order status updated successfully'
            status_metadata = {'estimated_delivery_time': estimated_delivery_time}
            response_extra = {}
            
            # Update the order status directly (no validation)
            order.order_status = new_status
            
            # Special handling for cancelled status - also cancel the payment
            if new_status == 'cancelled':
                from .models import Payments
                # Update any pending payments for this order to cancelled
                cancelled_payments = Payments.objects.filter(
                    order_id=order_id, 
                    status__in=['pending', 'initiated']
                ).update(status='cancelled')
                if cancelled_payments > 0:
                    logger.info(f"Cancelled {cancelled_payments} pending payment(s) for grocery order {order_id}")
                cancelled_by = str(request.data.get('cancelled_by', '')).lower()
                changed_by_id = request.data.get('changed_by_id')
                # Infer merchant-side cancellation without DB columns
                allowed_cancel_sources = ['business', 'merchant', 'chef']
                is_merchant_side = False
                try:
                    # order.business may be FK; access business_id depending on model
                    gro_bus_id = getattr(order.business, 'business_id', None) if hasattr(order, 'business') else None
                    if business_id and str(gro_bus_id) == str(business_id):
                        is_merchant_side = True
                except Exception:
                    pass
                # Actor-based inference: different from customer or mapped to business
                try:
                    order_customer_id = str(getattr(order.user, 'user_id', '') or '')
                    actor_user_id = str(user_id) if user_id is not None else ''
                    if actor_user_id and order_customer_id and actor_user_id != order_customer_id:
                        is_merchant_side = True
                except Exception:
                    pass
                try:
                    if user_id and BusinessMapping.objects.filter(user__user_id=user_id, business=order.business).exists():
                        is_merchant_side = True
                except Exception:
                    pass
                effective_cancelled_by = (
                    cancelled_by if cancelled_by in allowed_cancel_sources else (
                        'business' if is_merchant_side or changed_by_id else 'customer'
                    )
                )
                logger.info(f"Grocery order {order_id} cancellation: effective_cancelled_by={effective_cancelled_by}, is_merchant_side={is_merchant_side}")
                paid_success = False
                try:
                    gp = GroceriesPayments.objects.filter(order=order).order_by('-payment_date').first()
                    if gp:
                        payment_status = str(gp.payment_status).lower()
                        if payment_status in ['completed', 'success', 'paid', 'successful']:
                            paid_success = True
                            logger.info(f"Grocery order {order_id} has successful payment: {gp.payment_status}")
                        else:
                            logger.info(f"Grocery order {order_id} payment status: {gp.payment_status} (not considered successful)")
                except Exception as e:
                    logger.error(f"Error checking grocery payment status for order {order_id}: {str(e)}")
                    paid_success = False
                if effective_cancelled_by in ['business', 'merchant', 'chef'] and paid_success:
                    try:
                        with transaction.atomic():
                            voucher_name = f"COMP-GROC-{order.order_id}"
                            coupon_code_target = f"VCHR-GROC-{order.order_id}"
                            existing_coupon = (
                                Coupons.objects.filter(coupon_code=coupon_code_target).first()
                                or Coupons.objects.filter(name=voucher_name).first()
                            )
                            if existing_coupon:
                                success_message = 'Order cancelled by restaurant; voucher already issued.'
                                status_metadata.update({
                                    'compensation': 'voucher',
                                    'voucher_code': existing_coupon.coupon_code,
                                    'voucher_value': float(existing_coupon.discount_value),
                                    'cancelled_by': effective_cancelled_by
                                })
                                response_extra['voucher'] = {
                                    'coupon_code': existing_coupon.coupon_code,
                                    'discount_value': float(existing_coupon.discount_value),
                                    'valid_to': existing_coupon.valid_to.isoformat() if existing_coupon.valid_to else None,
                                    'max_redemptions_per_user': existing_coupon.max_redemptions_per_user
                                }
                                try:
                                    CouponRules.objects.get_or_create(
                                        coupon_id=existing_coupon,
                                        rule_type=CouponRules.RuleType.ALLOWED_USER,
                                        defaults={'rule_value': {'user_id': int(order.user.user_id)}}
                                    )
                                except Exception:
                                    pass
                            else:
                                now_ts = timezone.now() if getattr(settings, 'USE_TZ', False) else datetime.now()
                                valid_to_ts = now_ts + timedelta(days=30)
                                coupon_payload = {
                                    'coupon_code': coupon_code_target,
                                    'name': voucher_name,
                                    'discount_type': 'fixed_amount',
                                    'discount_value': str(order.final_amount),
                                    'created_by': 'business_owner',
                                    'business_id': order.business.business_id,
                                    'valid_from': now_ts.isoformat(),
                                    'valid_to': valid_to_ts.isoformat(),
                                    'is_active': True,
                                    'max_usage_total': 1,
                                    'max_redemptions_per_user': 1,
                                    'points_required': 0
                                }
                                cserializer = CouponSerializer(data=coupon_payload)
                                if cserializer.is_valid():
                                    created_coupon = cserializer.save()
                                    try:
                                        CouponRules.objects.get_or_create(
                                            coupon_id=created_coupon,
                                            rule_type=CouponRules.RuleType.ALLOWED_USER,
                                            defaults={'rule_value': {'user_id': int(order.user.user_id)}}
                                        )
                                    except Exception:
                                        pass
                                    success_message = 'Order cancelled by restaurant; voucher issued.'
                                    status_metadata.update({
                                        'compensation': 'voucher',
                                        'voucher_code': created_coupon.coupon_code,
                                        'voucher_value': float(created_coupon.discount_value),
                                        'cancelled_by': effective_cancelled_by
                                    })
                                    response_extra['voucher'] = {
                                        'coupon_code': created_coupon.coupon_code,
                                        'discount_value': float(created_coupon.discount_value),
                                        'valid_to': created_coupon.valid_to.isoformat() if created_coupon.valid_to else None,
                                        'max_redemptions_per_user': created_coupon.max_redemptions_per_user
                                    }
                                    try:
                                        if getattr(order.user, 'user_id', None):
                                            user_id_int = int(order.user.user_id)
                                            notif_result = send_order_notification(
                                                user_id_int,
                                                "We're sorry — voucher issued",
                                                f"Order #{order.order_id} was cancelled. Voucher {created_coupon.coupon_code} issued.",
                                                {
                                                    'type': 'VOUCHER_ISSUED',
                                                    'order_id': str(order.order_id),
                                                    'coupon_code': created_coupon.coupon_code,
                                                    'discount_value': str(created_coupon.discount_value),
                                                    'valid_to': created_coupon.valid_to.isoformat() if created_coupon.valid_to else ''
                                                }
                                            )
                                            email_result = send_email_notification(
                                                user_id_int,
                                                f"Voucher issued for cancelled order #{order.order_id}",
                                                f"Order #{order.order_id} was cancelled. Voucher {created_coupon.coupon_code} worth ₹{created_coupon.discount_value} has been issued. Valid until {created_coupon.valid_to.isoformat() if created_coupon.valid_to else ''}.",
                                                {
                                                    'type': 'VOUCHER_ISSUED',
                                                    'order_id': str(order.order_id),
                                                    'coupon_code': created_coupon.coupon_code,
                                                    'discount_value': str(created_coupon.discount_value),
                                                    'valid_to': created_coupon.valid_to.isoformat() if created_coupon.valid_to else '',
                                                    'body': (
                                                        "We regret to inform you that your recent order has been cancelled due to unforeseen circumstances. "
                                                        "As a gesture of goodwill, we've issued a voucher for you to place a new order at your convenience. "
                                                        "Please use this voucher during your next purchase to enjoy a seamless experience. "
                                                        "Thank you for your understanding and continued support."
                                                    )
                                                }
                                            )
                                            logger.info(f"Grocery voucher notification sent for order {order.order_id}: push={notif_result is not None}, email={email_result}")
                                    except Exception as e:
                                        logger.error(f"Failed to send grocery voucher notification for order {order.order_id}: {str(e)}", exc_info=True)
                                else:
                                    try:
                                        points_to_credit = (order.final_amount * Decimal('10'))
                                        txn = WalletPoints.atomic_transaction(
                                            user_id=order.user,
                                            points=points_to_credit,
                                            transaction_type=WalletPoints.TransactionType.REFUNDED,
                                            description=f'Compensation for cancelled order #{order.order_id}',
                                            related_order=None
                                        )
                                        success_message = 'Order cancelled; amount credited to wallet as compensation.'
                                        status_metadata.update({
                                            'compensation': 'wallet',
                                            'credited_amount': float(order.final_amount),
                                            'cancelled_by': effective_cancelled_by
                                        })
                                        response_extra['wallet_credit'] = {
                                            'credited_amount': float(order.final_amount),
                                            'wallet_balance': float(txn.balance_after * Decimal('0.10'))
                                        }
                                        try:
                                            if getattr(order.user, 'user_id', None):
                                                user_id_int = int(order.user.user_id)
                                                notif_result = send_order_notification(
                                                    user_id_int,
                                                    'Order cancelled — wallet credited',
                                                    f"Order #{order.order_id} was cancelled. Amount credited to wallet.",
                                                    {
                                                        'type': 'WALLET_CREDITED',
                                                        'order_id': str(order.order_id),
                                                        'credited_amount': str(order.final_amount)
                                                    }
                                                )
                                                email_result = send_email_notification(
                                                    user_id_int,
                                                    f"Wallet credited for cancelled order #{order.order_id}",
                                                    f"Order #{order.order_id} was cancelled. ₹{order.final_amount} has been credited to your wallet.",
                                                    {
                                                        'type': 'WALLET_CREDITED',
                                                        'order_id': str(order.order_id),
                                                        'credited_amount': str(order.final_amount)
                                                    }
                                                )
                                                logger.info(f"Grocery wallet credit notification sent for order {order.order_id}: push={notif_result is not None}, email={email_result}")
                                        except Exception as e:
                                            logger.error(f"Failed to send grocery wallet credit notification for order {order.order_id}: {str(e)}", exc_info=True)
                                    except Exception:
                                        pass
                    except Exception as e:
                        logger.error(f"Error processing compensation for cancelled order: {str(e)}")
            
            # Handle special cases for delivered status
            if new_status == 'delivered':
                # Use timezone-aware or naive datetime based on Django settings
                if getattr(settings, 'USE_TZ', False):
                    order.delivery_time = timezone.now()
                else:
                    order.delivery_time = datetime.now()
            
            # Update delivery time if provided
            if estimated_delivery_time:
                # Parse and handle timezone-aware datetime strings
                if isinstance(estimated_delivery_time, str):
                    parsed_dt = date_parser.parse(estimated_delivery_time)
                    # Convert to naive datetime if USE_TZ is False
                    if not getattr(settings, 'USE_TZ', False) and parsed_dt.tzinfo is not None:
                        order.delivery_time = parsed_dt.replace(tzinfo=None)
                    else:
                        order.delivery_time = parsed_dt
                else:
                    order.delivery_time = estimated_delivery_time
            
            order.save()
            try:
                create_status_log(
                    'grocery',
                    order.order_id,
                    prev_status,
                    new_status,
                    user_id=user_id,
                    role='business',
                    notes=notes,
                    source='consumer.update_order_status',
                    metadata=status_metadata
                )
            except Exception:
                pass
            
            # Send feedback request email when grocery order is delivered or completed
            if new_status in ['delivered', 'completed']:
                try:
                    from .feedback_notifications import trigger_feedback_request
                    trigger_feedback_request(order.order_id, 'grocery')
                except Exception as e:
                    logger.error(f"Failed to trigger feedback request for grocery order {order.order_id}: {e}")
                
                # Assign behavior-based tags when grocery order is delivered
                if new_status == 'delivered':
                    try:
                        from .tag_assignment_service import TagAssignmentService
                        TagAssignmentService.assign_behavior_tags_on_order_completion(order.user.user_id)
                    except Exception as e:
                        logger.error(f"Failed to assign behavior tags for grocery user {order.user.user_id}: {e}")
            # Return all possible next statuses (no restrictions)
            all_possible_statuses = [
                'pending', 'confirmed', 'notified', 'preparing', 'packing', 'ready', 
                'assigned', 'picked_up', 'dispatched', 'travelling', 
                'out_for_delivery', 'delivered', 'cancelled'
            ]
            
            available_transitions = []
            for status_option in all_possible_statuses:
                if status_option != new_status:  # Don't include current status
                    available_transitions.append({
                        'action': status_option,
                        'target_status': status_option,
                        'description': status_option.replace('_', ' ').title()
                    })
            
            return Response({
                'success': True,
                'message': success_message,
                'order_system': 'grocery',
                'action_performed': action,
                'data': {
                    'order_id': order.order_id,
                    'current_status': order.order_status,
                    'available_transitions': available_transitions,
                    'updated_at': order.updated_at.isoformat()
                },
                **response_extra
            }, status=status.HTTP_200_OK)

    except Exception as e:
        logger.error(f"Error in update_order_status: {str(e)}", exc_info=True)
        return Response({
            'success': False,
            'error': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@swagger_auto_schema(methods=['GET'],tags=['Consumer'])
@api_view(['GET'])
def get_order_details(request, order_id):
    """
    Get complete order details with historical data
    """
    try:
        order = get_object_or_404(Orders, order_id=order_id)
        include_items = request.query_params.get('include_items', 'true').lower() == 'true'
        include_history = request.query_params.get('include_history', 'false').lower() == 'true'

        # Serialize order details
        serializer = OrderDetailSerializer(order, context={'request': request})
        order_data = serializer.data
        if getattr(order, 'scheduled_time', None):
            try:
                order_data['scheduled_time'] = order.scheduled_time.isoformat()
            except Exception:
                order_data['scheduled_time'] = str(order.scheduled_time)

        # Add order items if requested
        if include_items:
            order_items = OrderItems.objects.filter(order_id=order)
            items_serializer = OrderItemSerializer(order_items, many=True, context={'request': request})
            order_data['items'] = items_serializer.data

         # Add delivery partner details if available
        order_data['delivery_partner'] = None
        if hasattr(order, 'delivery_partner_id') and order.delivery_partner_id:
            try:
                try:
                    # Get the delivery partner using the user_id
                    delivery_partner = DeliveryPartner.objects.get(user_id=order.delivery_partner_id)
                    
                    # Initialize with default values
                    name = 'Delivery Partner'
                    phone = ''
                    
                    # Get user details from Registration table
                    try:
                        from kirazee_app.models import Registration
                        user = Registration.objects.get(user_id=order.delivery_partner_id)
                        first_name = getattr(user, 'firstName', '')
                        last_name = getattr(user, 'lastName', '')
                        if first_name or last_name:
                            name = f"{first_name} {last_name}".strip()
                        phone = getattr(user, 'mobileNumber', '')
                    except Registration.DoesNotExist:
                        logger.warning(f"User not found in registrations for user_id: {order.delivery_partner_id}")
                    except Exception as e:
                        logger.error(f"Error fetching user details: {str(e)}")
                    
                    # Build the delivery partner data with fallbacks
                    order_data['delivery_partner'] = {
                        'id': delivery_partner.id,
                        'name': name,
                        'vehicle_type': getattr(delivery_partner, 'vehicle_type', 'Bike'),
                        'vehicle_number': getattr(delivery_partner, 'vehicle_number', ''),
                        'rating': float(getattr(delivery_partner, 'rating', 4.0)),
                        'phone': phone or getattr(delivery_partner, 'phone_number', '')
                    }
                except DeliveryPartner.DoesNotExist:
                    logger.warning(f"Delivery partner with user_id {order.delivery_partner_id} not found")
                except Exception as e:
                    logger.error(f"Unexpected error processing delivery partner: {str(e)}")
                    order_data['delivery_partner'] = None
            except Exception as e:
                logger.error(f"Error getting delivery partner details: {str(e)}", exc_info=True)

        # Add business contact details
        order_data['business_contact'] = {
            'business_number': order.business_id.businessNumber if hasattr(order.business_id, 'businessNumber') else None,
            'business_whatsapp': order.business_id.businessWhatsapp if hasattr(order.business_id, 'businessWhatsapp') else None,
            'contact_mobile': order.business_id.contact_mobile if hasattr(order.business_id, 'contact_mobile') else None,
            'contact_support': order.business_id.contact_support if hasattr(order.business_id, 'contact_support') else None
        }

        return Response({
            'success': True,
            'data': order_data
        }, status=status.HTTP_200_OK)

    except Exception as e:
        return Response({
            'success': False,
            'error': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@swagger_auto_schema(methods=['GET'],tags=['Consumer'])
@api_view(['GET'])
def list_user_orders(request, user_id):
    """
    Get paginated list of user's orders with filtering
    Supports business type filtering via 'type' parameter:
    - No type parameter: Returns all orders
    - type=R01: Returns only grocery orders
    - type=R02: Returns only restaurant orders
    """
    try:
        # Validate user exists
        user = get_object_or_404(Registration, user_id=user_id)

        # Get query parameters for filtering
        status_filter = request.query_params.get('status')
        business_id_filter = request.query_params.get('business_id')
        order_type_filter = request.query_params.get('order_type')
        business_type_filter = request.query_params.get('type')  # New parameter for R01/R02
        date_from = request.query_params.get('date_from')
        date_to = request.query_params.get('date_to')
        page = int(request.query_params.get('page', 1))
        page_size = int(request.query_params.get('page_size', 20))

        # Build query
        orders = Orders.objects.filter(user_id=user).order_by('-created_at')

        # Apply filters
        if status_filter:
            orders = orders.filter(status=status_filter)
        if business_id_filter:
            orders = orders.filter(business_id__business_id=business_id_filter)
        if order_type_filter:
            orders = orders.filter(order_type=order_type_filter)
        if business_type_filter:
            # Filter by business type (R01 for Grocery, R02 for Restaurant)
            if business_type_filter.upper() in ['R01', 'R02', 'R08']:
                orders = orders.filter(business_id__businessType=business_type_filter.upper())
        if date_from:
            orders = orders.filter(created_at__date__gte=date_from)
        if date_to:
            orders = orders.filter(created_at__date__lte=date_to)

        # Paginate results
        paginator = Paginator(orders, page_size)
        page_obj = paginator.get_page(page)

        # Serialize orders
        serializer = OrderListSerializer(page_obj.object_list, many=True, context={'request': request})

        # Build pagination URLs with existing query parameters
        query_params = request.GET.copy()
        
        # Build next URL
        next_url = None
        if page_obj.has_next():
            query_params['page'] = page + 1
            next_url = f'/consumer/orders/user/{user_id}/?{query_params.urlencode()}'
        
        # Build previous URL
        previous_url = None
        if page_obj.has_previous():
            query_params['page'] = page - 1
            previous_url = f'/consumer/orders/user/{user_id}/?{query_params.urlencode()}'

        # Prepare response data
        response_data = {
            'count': paginator.count,
            'next': next_url,
            'previous': previous_url,
            'results': serializer.data
        }

        # Add business type information if filtered
        if business_type_filter:
            business_type_upper = business_type_filter.upper()
            if business_type_upper == 'R01':
                response_data['business_type'] = 'R01'
                response_data['business_category'] = 'Grocery'
            elif business_type_upper == 'R02':
                response_data['business_type'] = 'R02'
                response_data['business_category'] = 'Restaurant'
            elif business_type_upper == 'R08':
                response_data['business_type'] = 'R08'
                response_data['business_category'] = 'Fashion'

        return Response({
            'success': True,
            'data': response_data
        }, status=status.HTTP_200_OK)

    except Exception as e:
        return Response({
            'success': False,
            'error': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@swagger_auto_schema(methods=['GET'],tags=['Consumer'])
@api_view(['GET'])
def get_order_analytics(request):
    """
    Get order statistics and insights
    """
    try:
        user_id = request.query_params.get('user_id')
        business_id = request.query_params.get('business_id')
        date_from = request.query_params.get('date_from')
        date_to = request.query_params.get('date_to')

        # Build base query
        orders = Orders.objects.all()

        if user_id:
            orders = orders.filter(user_id__user_id=user_id)
        if business_id:
            orders = orders.filter(business_id__business_id=business_id)
        if date_from:
            orders = orders.filter(created_at__date__gte=date_from)
        if date_to:
            orders = orders.filter(created_at__date__lte=date_to)

        # Calculate summary statistics
        total_orders = orders.count()
        total_spent = orders.aggregate(total=models.Sum('final_amount'))['total'] or 0
        average_order_value = total_spent / total_orders if total_orders > 0 else 0
        total_savings = orders.aggregate(total=models.Sum('discount_amount'))['total'] or 0

        # Status breakdown
        status_breakdown = {}
        for status_choice in Orders.OrderStatus.choices:
            count = orders.filter(status=status_choice[0]).count()
            status_breakdown[status_choice[1]] = count

        # Order type breakdown
        type_breakdown = {}
        order_types = ['delivery', 'pickup', 'dine_in', 'takeaway']
        for order_type in order_types:
            count = orders.filter(order_type=order_type).count()
            type_breakdown[order_type] = count

        return Response({
            'success': True,
            'data': {
                'summary': {
                    'total_orders': total_orders,
                    'total_spent': float(total_spent),
                    'average_order_value': float(average_order_value),
                    'total_savings': float(total_savings)
                },
                'order_status_breakdown': status_breakdown,
                'order_type_breakdown': type_breakdown
            }
        }, status=status.HTTP_200_OK)

    except Exception as e:
        return Response({
            'success': False,
            'error': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


def _cart_preview_validate_request(data):
    user_id = data.get('user_id')
    business_id = data.get('business_id')
    order_type = data.get('order_type')
    delivery_address_id = data.get('delivery_address_id')
    items = data.get('items', [])

    if not all([user_id, business_id, order_type, items]):
        return Response(
            {
                'success': False,
                'error': 'Missing required fields: user_id, business_id, order_type, items'
            },
            status=status.HTTP_400_BAD_REQUEST,
        )

    if order_type == 'delivery':
        if 'delivery_charges' not in data:
            return Response(
                {
                    'success': False,
                    'error': 'Missing required field: delivery_charges for delivery orders'
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        if not delivery_address_id:
            return Response(
                {
                    'success': False,
                    'error': 'Missing required field: delivery_address_id for delivery orders'
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

    return None


def _cart_preview_get_parcel_charges(business_id):
    parcel_charges = Decimal('0.00')
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT parcel_charges
                FROM delivery_charges
                WHERE business_id = %s AND is_active = 1
                LIMIT 1
                """,
                [business_id],
            )
            result = cursor.fetchone()
            parcel_charges = Decimal(str(result[0])) if result else Decimal('0.00')
    except Exception as e:
        logger.warning(f"Could not fetch parcel charges for business {business_id}: {str(e)}")
        parcel_charges = Decimal('0.00')
    return parcel_charges


def _cart_preview_process_items(items, business_type, business_id, business, check_dt):
    items_total = Decimal('0.00')
    items_base_total = Decimal('0.00')
    customizations_total = Decimal('0.00')
    total_gst = Decimal('0.00')
    items_mrp_total = Decimal('0.00')
    order_items_data = []

    for item in items:
        if 'menu_item_id' in item:
            menu_item = get_object_or_404(MenuItems, item_id=item['menu_item_id'])
            item_price = Decimal(str(menu_item.selling_price))
            item_name = menu_item.item_name
            original_cost = Decimal(str(menu_item.original_cost)) if menu_item.original_cost else Decimal('0')

            gst_percent = Decimal(str(menu_item.gst)) if menu_item.gst else Decimal('0')
            gst_amount = (item_price * gst_percent / Decimal('100')).quantize(Decimal('0.01'))
            item_total_price = (item_price + gst_amount) * Decimal(str(item['quantity']))

            base_unit_price = item_price
            customization_extra_unit = Decimal('0.00')
            item_total_before_tax = (item_price * Decimal(str(item['quantity']))).quantize(Decimal('0.01'))
            item_total_after_tax = item_total_price.quantize(Decimal('0.01'))

            item_details = {
                'description': menu_item.description,
                'category': menu_item.item_category,
                'type': menu_item.item_type,
                'gst_percentage': float(gst_percent),
                'gst_amount': float(gst_amount),
                'original_cost': float(menu_item.original_cost) if menu_item.original_cost else 0,
                'selling_price': float(item_price)
            }
            order_items_data.append({
                'menu_item_id': menu_item.item_id,
                'product_item_id': None,
                'item_name': item_name,
                'quantity': item['quantity'],
                'base_unit_price': float(base_unit_price),
                'customization_extra_unit': float(customization_extra_unit),
                'customization_extra_total': float(customization_extra_unit * Decimal(str(item['quantity']))),
                'unit_price': float(item_price),
                'gst_amount': float(gst_amount),
                'item_total_before_tax': float(item_total_before_tax),
                'item_total_after_tax': float(item_total_after_tax),
                'total_price': float(item_total_price),
                'item_details': item_details,
                'customizations': _normalize_json_value(item.get('customizations', []))
            })

            items_total += item_price * Decimal(str(item['quantity']))
            items_base_total += base_unit_price * Decimal(str(item['quantity']))
            customizations_total += customization_extra_unit * Decimal(str(item['quantity']))
            total_gst += gst_amount * Decimal(str(item['quantity']))
            items_mrp_total += original_cost * Decimal(str(item['quantity']))
            continue

        # Backward compatibility: accept product_id as alias for product_item_id
        if 'product_item_id' not in item and 'product_id' in item:
            item = dict(item)
            item['product_item_id'] = item.get('product_id')

        variant_id_input = item.get('variant_id')

        if 'product_item_id' not in item:
            continue

        if business_type == 'R01':
            from .gro_models import GroceriesProductVariants, GroceriesProducts

            try:
                # Variant-aware: if variant_id provided, price using that variant.
                # Otherwise, keep backward-compatible behavior:
                # - try product_id and choose cheapest active variant
                # - fallback treat product_item_id as variant_id

                if variant_id_input is not None:
                    grocery_variant = GroceriesProductVariants.objects.get(
                        variant_id=variant_id_input,
                        is_active=True,
                    )
                    grocery_product = grocery_variant.product
                    if str(grocery_product.business_id) != str(business_id):
                        return Response(
                            {
                                'success': False,
                                'error': f'Grocery variant {variant_id_input} does not belong to business {business_id}'
                            },
                            status=status.HTTP_400_BAD_REQUEST,
                        )

                    # If product_id was sent, validate it matches variant's product
                    if item.get('product_item_id') is not None and str(grocery_product.product_id) != str(item.get('product_item_id')):
                        return Response(
                            {
                                'success': False,
                                'error': f'Grocery variant {variant_id_input} does not belong to product {item.get("product_item_id")}'
                            },
                            status=status.HTTP_400_BAD_REQUEST,
                        )

                else:
                    grocery_product = GroceriesProducts.objects.get(
                        product_id=item['product_item_id'],
                        business_id=business_id,
                    )
                    grocery_variant = (
                        GroceriesProductVariants.objects
                        .filter(product=grocery_product, is_active=True)
                        .order_by('selling_price', 'variant_id')
                        .first()
                    )
                    if not grocery_variant:
                        raise GroceriesProductVariants.DoesNotExist()

                item_price = Decimal(str(grocery_variant.selling_price)) if grocery_variant.selling_price else Decimal('0')
                item_name = grocery_product.product_name
                original_cost = Decimal(str(grocery_variant.original_cost)) if grocery_variant.original_cost else Decimal('0')
                gst_percent = grocery_variant.gst if grocery_variant.gst is not None else (
                    Decimal(str(getattr(grocery_product.category, 'gst_rate', None) or 0))
                    if grocery_product.category else Decimal('0')
                )

                grocery_category_name = None
                try:
                    cat = grocery_product.category
                    grocery_category_name = getattr(cat, 'category_name', None)
                except Exception:
                    grocery_category_name = None
                if not grocery_category_name:
                    try:
                        from business.models import UniversalCategory
                        uc = UniversalCategory.objects.filter(category_id=grocery_product.category_id).first()
                        grocery_category_name = uc.category_name if uc else None
                    except Exception:
                        grocery_category_name = None

            except (GroceriesProducts.DoesNotExist, GroceriesProductVariants.DoesNotExist):
                try:
                    grocery_variant = GroceriesProductVariants.objects.get(
                        variant_id=item['product_item_id'],
                        is_active=True,
                    )
                    if grocery_variant.product.business_id != business_id:
                        return Response(
                            {
                                'success': False,
                                'error': f'Grocery variant {item["product_item_id"]} does not belong to business {business_id}'
                            },
                            status=status.HTTP_400_BAD_REQUEST,
                        )

                    grocery_product = grocery_variant.product
                    item_price = Decimal(str(grocery_variant.selling_price)) if grocery_variant.selling_price else Decimal('0')
                    item_name = grocery_product.product_name
                    original_cost = Decimal(str(grocery_variant.original_cost)) if grocery_variant.original_cost else Decimal('0')
                    gst_percent = grocery_variant.gst if grocery_variant.gst is not None else (
                        Decimal(str(getattr(grocery_product.category, 'gst_rate', None) or 0))
                        if grocery_product.category else Decimal('0')
                    )

                    grocery_category_name = None
                    try:
                        cat = grocery_product.category
                        grocery_category_name = getattr(cat, 'category_name', None)
                    except Exception:
                        grocery_category_name = None
                    if not grocery_category_name:
                        try:
                            from business.models import UniversalCategory
                            uc = UniversalCategory.objects.filter(category_id=grocery_product.category_id).first()
                            grocery_category_name = uc.category_name if uc else None
                        except Exception:
                            grocery_category_name = None

                except GroceriesProductVariants.DoesNotExist:
                    return Response(
                        {
                            'success': False,
                            'error': f'Grocery item with ID {item["product_item_id"]} not found or inactive'
                        },
                        status=status.HTTP_404_NOT_FOUND,
                    )

        elif business_type == 'R02':
            # Variant-aware support: if variant_id is provided, use menu_item_variants pricing
            if variant_id_input is not None:
                from business.models import MenuItemVariant

                mv = get_object_or_404(MenuItemVariant, variant_id=variant_id_input, is_active=True)
                base_menu_item = mv.item
                if str(base_menu_item.business_id_id) != str(business_id):
                    return Response(
                        {
                            'success': False,
                            'error': f'Menu variant {variant_id_input} does not belong to business {business_id}'
                        },
                        status=status.HTTP_400_BAD_REQUEST,
                    )

                # If menu item id was sent, validate it matches variant's base item
                if item.get('product_item_id') is not None and str(base_menu_item.item_id) != str(item.get('product_item_id')):
                    return Response(
                        {
                            'success': False,
                            'error': f'Menu variant {variant_id_input} does not belong to item {item.get("product_item_id")}'
                        },
                        status=status.HTTP_400_BAD_REQUEST,
                    )

                item_price = Decimal(str(mv.selling_price))
                item_name = base_menu_item.item_name
                original_cost = Decimal(str(mv.original_cost)) if mv.original_cost else Decimal('0')
                gst_percent = Decimal(str(mv.gst)) if mv.gst else (Decimal(str(base_menu_item.gst)) if base_menu_item.gst else Decimal('0'))

                item_details = {
                    'description': base_menu_item.description,
                    'category': base_menu_item.item_category,
                    'type': base_menu_item.item_type,
                    'gst_percentage': float(gst_percent),
                    'gst_amount': 0,
                    'original_cost': float(mv.original_cost) if mv.original_cost else 0,
                    'selling_price': float(item_price)
                }
            else:
                product_item = get_object_or_404(productItems, item_id=item['product_item_id'])
                if not _is_product_item_available(product_item, check_dt):
                    return Response(
                        {
                            'success': False,
                            'error': f"'{product_item.item_name}' is not available at this time"
                        },
                        status=status.HTTP_400_BAD_REQUEST,
                    )
                item_price = Decimal(str(product_item.selling_price))
                item_name = product_item.item_name
                original_cost = Decimal(str(product_item.original_cost)) if getattr(product_item, 'original_cost', None) else Decimal('0')
                gst_percent = Decimal(str(product_item.gst)) if product_item.gst else Decimal('0')
                item_details = {
                    'description': product_item.description,
                    'category': product_item.item_category,
                    'type': product_item.item_type,
                    'gst_percentage': float(gst_percent),
                    'gst_amount': 0,
                    'original_cost': float(product_item.original_cost) if product_item.original_cost else 0,
                    'selling_price': float(item_price)
                }

        elif business_type == 'R08':
            from business.models import FashionProductVariant, FashionProduct

            fashion_variant = None
            try:
                if variant_id_input is not None:
                    fashion_variant = FashionProductVariant.objects.select_related('product', 'product__category').get(
                        variant_id=variant_id_input,
                        is_active=True,
                    )
                else:
                    fashion_variant = FashionProductVariant.objects.select_related('product', 'product__category').get(
                        variant_id=item['product_item_id'],
                        is_active=True,
                    )
            except FashionProductVariant.DoesNotExist:
                try:
                    fashion_product = FashionProduct.objects.get(
                        product_id=item['product_item_id'],
                        business_id=business_id,
                        is_active=True,
                    )
                    if not getattr(fashion_product, 'variant_id', None):
                        return Response(
                            {
                                'success': False,
                                'error': f'Fashion product {item["product_item_id"]} has no default variant set'
                            },
                            status=status.HTTP_404_NOT_FOUND,
                        )
                    fashion_variant = FashionProductVariant.objects.select_related('product', 'product__category').get(
                        variant_id=fashion_product.variant_id,
                        is_active=True,
                    )
                except (FashionProduct.DoesNotExist, FashionProductVariant.DoesNotExist):
                    tried_id = variant_id_input if variant_id_input is not None else item.get('product_item_id')
                    return Response(
                        {
                            'success': False,
                            'error': f'Fashion variant with ID {tried_id} not found or inactive (tried as variant_id and product_id). Detected business_type={business_type}; ensure you are passing the correct business_id for this item/variant.'
                        },
                        status=status.HTTP_404_NOT_FOUND,
                    )

            fashion_product = getattr(fashion_variant, 'product', None)
            item_price = Decimal(str(fashion_variant.selling_price))
            item_name = fashion_product.name if fashion_product else 'Fashion Item'
            original_cost = Decimal(str(fashion_variant.original_cost)) if fashion_variant.original_cost else Decimal('0')
            gst_percent = Decimal(str(getattr(fashion_product, 'gst_rate_default', None))) if getattr(fashion_product, 'gst_rate_default', None) else Decimal('0')
            item_details = {
                'description': getattr(fashion_product, 'description', '') if fashion_product else '',
                'category': fashion_product.category.category_name if getattr(fashion_product, 'category', None) else '',
                'type': getattr(fashion_product, 'subcategory', '') if fashion_product else '',
                'gst_percentage': float(gst_percent),
                'gst_amount': 0,
                'original_cost': float(fashion_variant.original_cost) if fashion_variant.original_cost else 0,
                'selling_price': float(item_price)
            }
        else:
            return Response(
                {'success': False, 'error': f'Unsupported business type: {business_type}'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        gst_amount = (item_price * gst_percent / Decimal('100')).quantize(Decimal('0.01'))
        base_unit_price = item_price
        customization_extra_unit = Decimal('0.00')

        if business_type == 'R01':
            selections = _normalize_json_value(item.get('customizations', []))
            try:
                if getattr(settings, 'DEBUG', False):
                    print('[cart_summary_preview][R01] base_price', str(item_price), 'product_id', str(grocery_product.product_id), 'customizations', selections)
                simple_extra = Decimal('0.00')
                try:
                    if isinstance(selections, list) and selections and all(isinstance(s, dict) for s in selections):
                        has_design_ids = any(s.get('design_id') is not None for s in selections)
                        if not has_design_ids:
                            for s in selections:
                                p = s.get('price')
                                if p is None:
                                    continue
                                try:
                                    simple_extra += Decimal(str(p))
                                except Exception:
                                    continue
                except Exception:
                    simple_extra = Decimal('0.00')

                if simple_extra > 0:
                    item_price = (item_price or Decimal('0')) + simple_extra
                else:
                    item_price = apply_customizations_pricing_r01(business_id, grocery_product.product_id, selections, item_price)
                if getattr(settings, 'DEBUG', False):
                    print('[cart_summary_preview][R01] priced_unit', str(item_price))
                customization_extra_unit = (item_price - base_unit_price)
                if customization_extra_unit < 0:
                    customization_extra_unit = Decimal('0.00')
                # Recalculate GST after customizations are applied
                gst_amount = (item_price * gst_percent / Decimal('100')).quantize(Decimal('0.01'))
            except ValueError as ve:
                return Response({'success': False, 'error': str(ve)}, status=status.HTTP_400_BAD_REQUEST)

        item_total_price = (item_price + gst_amount) * Decimal(str(item['quantity']))
        item_total_before_tax = (item_price * Decimal(str(item['quantity']))).quantize(Decimal('0.01'))
        item_total_after_tax = item_total_price.quantize(Decimal('0.01'))

        if business_type == 'R01':
            item_details = {
                'description': grocery_product.description,
                'category': grocery_category_name,
                'type': grocery_product.sub_category,
                'gst_percentage': float(gst_percent),
                'gst_amount': float(gst_amount),
                'original_cost': float(grocery_variant.original_cost) if grocery_variant.original_cost else 0,
                'selling_price': float(item_price)
            }
            order_items_data.append({
                'menu_item_id': None,
                'product_item_id': item.get('product_item_id'),
                'variant_id': grocery_variant.variant_id,
                'item_name': item_name,
                'quantity': item['quantity'],
                'base_unit_price': float(base_unit_price),
                'customization_extra_unit': float(customization_extra_unit),
                'customization_extra_total': float(customization_extra_unit * Decimal(str(item['quantity']))),
                'unit_price': float(item_price),
                'gst_amount': float(gst_amount),
                'item_total_before_tax': float(item_total_before_tax),
                'item_total_after_tax': float(item_total_after_tax),
                'total_price': float(item_total_price),
                'item_details': item_details,
                'customizations': _normalize_json_value(item.get('customizations', []))
            })
        else:
            item_details['gst_amount'] = float(gst_amount)
            ref_id = product_item.item_id if business_type == 'R02' and variant_id_input is None else (
                int(variant_id_input) if business_type == 'R02' and variant_id_input is not None else fashion_variant.variant_id
            )
            order_items_data.append({
                'menu_item_id': None,
                'product_item_id': ref_id,
                'variant_id': int(variant_id_input) if business_type == 'R02' and variant_id_input is not None else (fashion_variant.variant_id if business_type == 'R08' else None),
                'item_name': item_name,
                'quantity': item['quantity'],
                'base_unit_price': float(base_unit_price),
                'customization_extra_unit': float(customization_extra_unit),
                'customization_extra_total': float(customization_extra_unit * Decimal(str(item['quantity']))),
                'unit_price': float(item_price),
                'gst_amount': float(gst_amount),
                'item_total_before_tax': float(item_total_before_tax),
                'item_total_after_tax': float(item_total_after_tax),
                'total_price': float(item_total_price),
                'item_details': item_details,
                'customizations': _normalize_json_value(item.get('customizations', []))
            })

        items_total += item_price * Decimal(str(item['quantity']))
        items_base_total += base_unit_price * Decimal(str(item['quantity']))
        customizations_total += customization_extra_unit * Decimal(str(item['quantity']))
        total_gst += gst_amount * Decimal(str(item['quantity']))
        items_mrp_total += original_cost * Decimal(str(item['quantity']))

    return {
        'items_total': items_total,
        'items_base_total': items_base_total,
        'customizations_total': customizations_total,
        'total_gst': total_gst,
        'items_mrp_total': items_mrp_total,
        'order_items_data': order_items_data,
    }


def _cart_preview_apply_coupon(data, coupon_code, user_id, business_id, business_type, items_total, order_items_data):
    discount_amount = Decimal('0.00')
    coupon_applied = None

    if not coupon_code:
        return {'discount_amount': discount_amount, 'coupon_applied': coupon_applied}

    try:
        coupon = Coupons.objects.get(coupon_code=coupon_code, is_active=True)

        if coupon.business_id_id and str(coupon.business_id_id) != str(business_id):
            return Response({'success': False, 'error': 'Coupon not valid for this business'}, status=status.HTTP_400_BAD_REQUEST)

        is_valid, message = coupon.is_valid_for_user(user_id)
        if not is_valid:
            return Response({'success': False, 'error': f'Coupon validation failed: {message}'}, status=status.HTTP_400_BAD_REQUEST)

        base_amount = items_total

        try:
            has_applicable = CouponApplicableItems.objects.filter(coupon=coupon).exists()
        except Exception:
            has_applicable = False

        if has_applicable:
            app_set = set()
            try:
                app_set = set(CouponApplicableItems.objects.filter(coupon=coupon).values_list('reference_table', 'reference_id'))
            except Exception:
                app_set = set()

            eligible_items_total = Decimal('0.00')
            eligible_gst = Decimal('0.00')
            for oi in order_items_data:
                qty = Decimal(str(oi.get('quantity', 1)))
                unit_price = Decimal(str(oi.get('unit_price', 0)))
                ref_table = None
                ref_id = None
                if oi.get('menu_item_id'):
                    ref_table = 'menuItems'
                    ref_id = int(oi['menu_item_id'])
                elif oi.get('product_item_id'):
                    pid = int(oi['product_item_id'])
                    bt_upper = str(business_type).upper()
                    if bt_upper == 'R01':
                        ref_table = 'Groceries_ProductVariants'
                    elif bt_upper == 'R08':
                        ref_table = 'fashion_product_variants'
                    else:
                        ref_table = 'productItems'
                    ref_id = pid

                if ref_table and (ref_table, ref_id) in app_set:
                    eligible_items_total += (unit_price * qty)
                    gst_percent = Decimal(str(oi.get('item_details', {}).get('gst_percentage', 0)))
                    gst_amount = (unit_price * gst_percent / Decimal('100')).quantize(Decimal('0.01'))
                    eligible_gst += (gst_amount * qty)

            eligible_subtotal = (eligible_items_total + eligible_gst).quantize(Decimal('1'))
            if eligible_subtotal <= 0:
                return Response({'success': False, 'error': 'Coupon not applicable to selected items'}, status=status.HTTP_400_BAD_REQUEST)
            base_amount = eligible_subtotal

        if coupon.discount_type == 'percentage':
            discount_amount = (base_amount * Decimal(str(coupon.discount_value))) / Decimal('100')
            if discount_amount > base_amount:
                discount_amount = base_amount
        elif coupon.discount_type == 'fixed_amount':
            discount_amount = Decimal(str(coupon.discount_value))
            if discount_amount > base_amount:
                discount_amount = base_amount
        elif coupon.discount_type == 'free_delivery':
            discount_amount = Decimal(str(data.get('delivery_charges')))
            data['delivery_charges'] = '0'
        elif coupon.discount_type == 'bogo':
            eligible_units = Decimal('0')
            cheapest = None
            app_set = set()
            if has_applicable:
                try:
                    app_set = set(CouponApplicableItems.objects.filter(coupon=coupon).values_list('reference_table', 'reference_id'))
                except Exception:
                    app_set = set()
            for oi in order_items_data:
                try:
                    qty = Decimal(str(oi.get('quantity', 1)))
                    unit_price = Decimal(str(oi.get('unit_price', 0)))
                    ref_table = None
                    ref_id = None
                    if oi.get('menu_item_id'):
                        ref_table = 'menuItems'
                        ref_id = int(oi['menu_item_id'])
                    elif oi.get('product_item_id'):
                        bt_upper = str(business_type).upper()
                        if bt_upper == 'R01':
                            ref_table = 'Groceries_ProductVariants'
                        elif bt_upper == 'R08':
                            ref_table = 'fashion_product_variants'
                        else:
                            ref_table = 'productItems'
                        ref_id = int(oi['product_item_id'])
                    eligible = True
                    if has_applicable:
                        eligible = (ref_table, ref_id) in app_set
                    if unit_price is not None and eligible:
                        eligible_units += qty
                        if cheapest is None or unit_price < cheapest:
                            cheapest = unit_price
                except Exception:
                    continue
            if eligible_units < 2 or cheapest is None:
                return Response({'success': False, 'error': 'BOGO requires at least 2 eligible items in cart'}, status=status.HTTP_400_BAD_REQUEST)
            discount_amount = cheapest

        coupon_applied = coupon

    except Coupons.DoesNotExist:
        return Response({'success': False, 'error': 'Invalid coupon code'}, status=status.HTTP_400_BAD_REQUEST)

    return {'discount_amount': discount_amount, 'coupon_applied': coupon_applied}


def _cart_preview_calculate_summary(
    *,
    items_total,
    items_base_total,
    customizations_total,
    total_gst,
    items_mrp_total,
    parcel_charges,
    delivery_charges,
    discount_amount,
    wallet_points_to_use,
):
    delivery_charges = Decimal(str(delivery_charges or 0)).quantize(Decimal('0.01'))

    items_total = Decimal(str(items_total or 0)).quantize(Decimal('0.01'))
    items_base_total = Decimal(str(items_base_total or 0)).quantize(Decimal('0.01'))
    customizations_total = Decimal(str(customizations_total or 0)).quantize(Decimal('0.01'))
    total_gst = Decimal(str(total_gst or 0)).quantize(Decimal('0.01'))
    parcel_charges = Decimal(str(parcel_charges or 0)).quantize(Decimal('0.01'))
    discount_amount = Decimal(str(discount_amount or 0)).quantize(Decimal('0.01'))

    subtotal = (items_total + total_gst + delivery_charges + parcel_charges).quantize(Decimal('0.01'))
    after_coupon = (subtotal - discount_amount).quantize(Decimal('0.01'))
    if after_coupon < Decimal('0'):
        after_coupon = Decimal('0')

    items_mrp_total = Decimal(str(items_mrp_total or 0)).quantize(Decimal('0.01'))
    items_discount = (items_mrp_total - items_total)
    if items_discount < 0:
        items_discount = Decimal('0')
    you_saved = (items_discount + discount_amount).quantize(Decimal('0.01'))

    wallet_points_value = Decimal(str(wallet_points_to_use or 0)).quantize(Decimal('0.01'))
    final_amount = (after_coupon - wallet_points_value).quantize(Decimal('1'))

    # Backward compatible response uses `subtotal` as gross_total (items + tax + delivery + parcel)
    # Add clearer breakdown fields without removing existing keys.
    items_subtotal = items_total
    charges_total = (delivery_charges + parcel_charges).quantize(Decimal('0.01'))
    gross_total = subtotal

    return {
        'parcel_charges': parcel_charges,
        'items_total': items_total,
        'items_base_total': items_base_total,
        'customizations_total': customizations_total,
        'items_subtotal': items_subtotal,
        'delivery_charges': delivery_charges,
        'charges_total': charges_total,
        'total_gst': total_gst,
        'subtotal': subtotal,
        'gross_total': gross_total,
        'coupon_discount': discount_amount,
        'after_coupon': after_coupon,
        'wallet_points_used': Decimal(str(wallet_points_to_use or 0)),
        'wallet_points_value': wallet_points_value,
        'final_amount': final_amount,
        'you_saved': you_saved,
    }


@swagger_auto_schema(methods=['POST'],tags=['Consumer'])
@api_view(['POST'])
def cart_summary_preview(request):
    """
    Preview order summary with address snapshots, delivery charges, coupon and wallet points
    without saving any data to database
    """
    try:
        data = request.data
        validation_error = _cart_preview_validate_request(data)
        if validation_error is not None:
            return validation_error

        user_id = data.get('user_id')
        business_id = data.get('business_id')
        order_type = data.get('order_type')
        items = data.get('items', [])
        coupon_code = data.get('coupon_code')
        wallet_points_to_use = Decimal(str(data.get('wallet_points_to_use', 0)))

        delivery_charges = (
            Decimal(str(data.get('delivery_charges', 0))) if order_type == 'delivery' else Decimal('0')
        )

        get_object_or_404(Registration, user_id=user_id)
        business = get_object_or_404(Business, business_id=business_id)
        business_type = business.businessType

        check_dt = get_ist_now()
        # Use parcel_charges from request payload
        parcel_charges = Decimal(str(data.get('parcel_charges', 0)))

        processed = _cart_preview_process_items(items, business_type, business_id, business, check_dt)
        if isinstance(processed, Response):
            return processed

        coupon_result = _cart_preview_apply_coupon(
            data,
            coupon_code,
            user_id,
            business_id,
            business_type,
            processed['items_total'],
            processed['order_items_data'],
        )
        if isinstance(coupon_result, Response):
            return coupon_result

        delivery_charges = Decimal(str(data.get('delivery_charges', delivery_charges)))

        summary = _cart_preview_calculate_summary(
            items_total=processed['items_total'],
            items_base_total=processed['items_base_total'],
            customizations_total=processed['customizations_total'],
            total_gst=processed['total_gst'],
            items_mrp_total=processed['items_mrp_total'],
            parcel_charges=parcel_charges,
            delivery_charges=delivery_charges,
            discount_amount=coupon_result['discount_amount'],
            wallet_points_to_use=wallet_points_to_use,
        )

        response_data = {
            'success': True,
            'message': 'Order preview calculated successfully',
            'data': {
                'order_summary': {
                    'items_base_total': float(summary['items_base_total']),
                    'customizations_total': float(summary['customizations_total']),
                    'items_total': float(summary['items_total']),
                    'items_subtotal': float(summary.get('items_subtotal', summary['items_total'])),

                    'total_gst': float(summary['total_gst']),

                    'delivery_charges': float(summary['delivery_charges']),
                    'parcel_charges': float(summary['parcel_charges']),
                    'charges_total': float(summary.get('charges_total', (summary['delivery_charges'] + summary['parcel_charges']))),

                    'subtotal': float(summary['subtotal']),
                    'gross_total': float(summary.get('gross_total', summary['subtotal'])),

                    'coupon_discount': float(summary['coupon_discount']),
                    'after_coupon': float(summary['after_coupon']),

                    'wallet_points_used': float(summary['wallet_points_used']),
                    'wallet_points_value': float(summary['wallet_points_value']),

                    'final_amount': float(summary['final_amount']),
                    'you_saved': float(summary['you_saved']),
                },
                'items': processed['order_items_data'],
            },
        }

        return Response(response_data, status=status.HTTP_200_OK)


    except Exception as e:
        return Response({
            'success': False,
            'error': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@swagger_auto_schema(methods=['POST'],tags=['Consumer'])
@api_view(['POST'])
def order_timeline(request):
    """
    Get detailed order timeline with progress line based on business type and order type
    """
    try:
        # Get parameters from query params
        order_id = request.query_params.get('order_id')
        user_id = request.query_params.get('user_id')

        if not order_id or not user_id:
            return Response({
                'error': 'order_id and user_id are required query parameters'
            }, status=status.HTTP_400_BAD_REQUEST)

        # Fetch order and validate ownership
        order = get_object_or_404(Orders, order_id=order_id, user_id=user_id)

        # Get business type and order type
        business_type = order.business_id.businessType
        order_type = order.order_type

        # Define timeline mappings as per business rules
        # Ensure R01 shows 'Packing' stage and R02 shows 'Preparing' stage among progress stages
        timeline_rules = {
            'R01_delivery': {  # Retail Business - Delivery
                'pending': 'Order Placed',
                'confirmed': 'Order Confirmed',
                'packing': 'Packing',
                'preparing': 'Packing',
                'ready': 'Packing',
                'accepted': 'Packing',
                'assigned': 'Packing',
                'picked_up': 'Picked Up',
                'notified': 'Picked Up',
                'travelling': 'Out for Delivery',
                'out_for_delivery': 'Out for Delivery',
                'delivered': 'Delivered',
                'cancelled': 'Cancelled'
            },
            'R01_takeaway': {  # Retail Business - Pickup
                'pending': 'Order Placed',
                'confirmed': 'Order Confirmed',
                'packing': 'Packing',
                'preparing': 'Packing',
                'ready': 'Ready for Pick-up',
                'delivered': 'Picked-up',
                'cancelled': 'Cancelled'
            },
            'R02_delivery': {  # Restaurants - Delivery
                'pending': 'Order Placed',
                'confirmed': 'Order Confirmed',
                'packing': 'Preparing',
                'preparing': 'Preparing',
                'ready': 'Preparing',
                'assigned': 'Preparing',
                'accepted': 'Preparing',
                'picked_up': 'Picked Up',
                'notified': 'Picked Up',
                'travelling': 'Out for Delivery',
                'out_for_delivery': 'Out for Delivery',
                'delivered': 'Delivered',
                'cancelled': 'Cancelled'
            },
            'R02_takeaway': {  # Restaurants - Pickup
                'pending': 'Order Placed',
                'confirmed': 'Order Confirmed',
                'packing': 'Preparing',
                'preparing': 'Preparing',
                'ready': 'Ready for Pick-up',
                'delivered': 'Picked-up',
                'cancelled': 'Cancelled'
            },
            'R02_dine_in': {  # Restaurants - Dine-in
                'pending': 'Order Placed',
                'confirmed': 'Order Confirmed',
                'packing': 'Preparing',
                'preparing': 'Preparing',
                'ready': 'Ready to Serve',
                'delivered': 'Completed',
                'cancelled': 'Cancelled'
            }
        }

        # Determine the timeline key
        if business_type == 'R01':
            if order_type == 'delivery':
                timeline_key = 'R01_delivery'
            else:  # takeaway, dine_in
                timeline_key = 'R01_takeaway'
        elif business_type == 'R02':
            if order_type == 'delivery':
                timeline_key = 'R02_delivery'
            else:  # takeaway, dine_in
                timeline_key = 'R02_takeaway' if order_type == 'takeaway' else 'R02_dine_in'
        else:
            # Default to R01_takeaway if unknown business type
            timeline_key = 'R01_takeaway'

        # Get the status mapping
        status_mapping = timeline_rules.get(timeline_key, {})

        # Map current status to user-friendly stage
        current_status = order.status
        if current_status == 'cancelled' or current_status == 'rejected':
            # Special case for cancelled orders
            current_stage = 'Rejected'
            previous_stages = []
            upcoming_stages = []
        else:
            current_stage = status_mapping.get(current_status, 'Order Placed')  # Default fallback

            # Get all stages in order, excluding Rejected (special case)
            all_stages = list(dict.fromkeys([stage for status, stage in status_mapping.items() if status != 'cancelled']))

            # Find current stage index
            try:
                current_index = all_stages.index(current_stage)
            except ValueError:
                current_index = 0  # Default to first stage

            # Build progress line
            previous_stages = all_stages[:current_index]
            upcoming_stages = all_stages[current_index + 1:]

        # Prepare order details with rounded amounts
        order_details = {
            'token_num': order.token_num,
            'order_number': str(order.order_number),
            'final_amount': float(round(Decimal(str(order.final_amount)))),  # Round to nearest integer
            'business_name': order.business_id.businessName,
            'items_total': float(round(Decimal(str(order.total_amount)))),    # Round to nearest integer
            'created_at': order.created_at.isoformat(),
            'updated_at': order.updated_at.isoformat()
        }

        # Prepare response
        response_data = {
            'order_id': order.order_id,
            'business_type': business_type,
            'order_details': order_details,
            'progress_line': {
                'previous_stages': previous_stages,
                'current_stage': current_stage,
                'upcoming_stages': upcoming_stages
            }
        }

        return Response(response_data, status=status.HTTP_200_OK)

    except Exception as e:
        logger.error(f"Error in order_timeline: {str(e)}", exc_info=True)
        return Response({
            'error': 'An error occurred while fetching order timeline'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@swagger_auto_schema(methods=['GET'],tags=['Consumer'])
@api_view(['GET'])
def get_order_status_logs(request, order_id):
    try:
        order_system = request.query_params.get('order_system')
        changed_by_user_id = request.query_params.get('changed_by_user_id')
        changed_by_role = request.query_params.get('changed_by_role')
        to_status = request.query_params.get('to_status')
        from_status = request.query_params.get('from_status')
        try:
            limit = int(request.query_params.get('limit', 50))
        except Exception:
            limit = 50
        try:
            offset = int(request.query_params.get('offset', 0))
        except Exception:
            offset = 0

        qs = OrderStatusLog.objects.filter(order_id=order_id)
        if order_system in ('standard', 'grocery'):
            qs = qs.filter(order_system=order_system)
        if changed_by_user_id:
            qs = qs.filter(changed_by_user_id=changed_by_user_id)
        if changed_by_role:
            qs = qs.filter(changed_by_role=changed_by_role)
        if to_status:
            qs = qs.filter(to_status=to_status)
        if from_status:
            qs = qs.filter(from_status=from_status)

        qs = qs.order_by('-created_at')
        total = qs.count()
        limit = max(1, min(limit, 200))
        offset = max(0, offset)
        logs = qs[offset:offset + limit]

        reg_map = {}
        try:
            user_ids = list({int(l.changed_by_user_id) for l in logs if l.changed_by_user_id is not None})
            if user_ids:
                reg_map = {r.user_id: r for r in Registration.objects.filter(user_id__in=user_ids)}
        except Exception:
            reg_map = {}

        results = []
        for log in logs:
            reg = None
            try:
                if log.changed_by_user_id is not None:
                    reg = reg_map.get(int(log.changed_by_user_id))
            except Exception:
                reg = None
            profile_image = build_s3_file_url(getattr(reg, 'profileUrl', None))
            results.append({
                'log_id': log.log_id,
                'order_system': log.order_system,
                'order_id': int(log.order_id),
                'from_status': log.from_status,
                'to_status': log.to_status,
                'changed_by_user_id': log.changed_by_user_id,
                'changed_by_user': (
                    {
                        'user_id': getattr(reg, 'user_id', None),
                        'first_name': getattr(reg, 'firstName', None),
                        'last_name': getattr(reg, 'lastName', None),
                        'display_name': getattr(reg, 'displayName', None),
                        'mobile_number': getattr(reg, 'mobileNumber', None),
                        'email': getattr(reg, 'emailID', None),
                        'profile_image': profile_image,
                    } if reg else None
                ),
                'changed_by_role': log.changed_by_role,
                'source': log.source,
                'notes': log.notes,
                'metadata': log.metadata,
                'created_at': log.created_at.isoformat() if getattr(log, 'created_at', None) else None,
            })

        return Response({'success': True, 'count': total, 'results': results}, status=status.HTTP_200_OK)
    except Exception as e:
        return Response({'success': False, 'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@swagger_auto_schema(methods=['GET'],tags=['Consumer'])
@api_view(['GET'])
def list_order_status_logs(request):
    try:
        order_system = request.query_params.get('order_system')
        order_id = request.query_params.get('order_id')
        changed_by_user_id = request.query_params.get('changed_by_user_id')
        changed_by_role = request.query_params.get('changed_by_role')
        to_status = request.query_params.get('to_status')
        from_status = request.query_params.get('from_status')
        ts_from = request.query_params.get('from')
        ts_to = request.query_params.get('to')

        try:
            limit = int(request.query_params.get('limit', 50))
        except Exception:
            limit = 50
        try:
            offset = int(request.query_params.get('offset', 0))
        except Exception:
            offset = 0

        qs = OrderStatusLog.objects.all()
        if order_system:
            qs = qs.filter(order_system=order_system)
        if order_id:
            try:
                qs = qs.filter(order_id=int(order_id))
            except Exception:
                qs = qs.none()
        if changed_by_user_id:
            qs = qs.filter(changed_by_user_id=changed_by_user_id)
        if changed_by_role:
            qs = qs.filter(changed_by_role=changed_by_role)
        if to_status:
            qs = qs.filter(to_status=to_status)
        if from_status:
            qs = qs.filter(from_status=from_status)

        if ts_from:
            try:
                dt_from = date_parser.parse(str(ts_from))
                qs = qs.filter(created_at__gte=dt_from)
            except Exception:
                pass
        if ts_to:
            try:
                dt_to = date_parser.parse(str(ts_to))
                qs = qs.filter(created_at__lte=dt_to)
            except Exception:
                pass

        qs = qs.order_by('-created_at')
        total = qs.count()
        limit = max(1, min(limit, 200))
        offset = max(0, offset)
        logs = qs[offset:offset + limit]

        reg_map = {}
        try:
            user_ids = list({int(l.changed_by_user_id) for l in logs if l.changed_by_user_id is not None})
            if user_ids:
                reg_map = {r.user_id: r for r in Registration.objects.filter(user_id__in=user_ids)}
        except Exception:
            reg_map = {}

        results = []
        for log in logs:
            reg = None
            try:
                if log.changed_by_user_id is not None:
                    reg = reg_map.get(int(log.changed_by_user_id))
            except Exception:
                reg = None
            profile_image = build_s3_file_url(getattr(reg, 'profileUrl', None))
            results.append({
                'log_id': log.log_id,
                'order_system': log.order_system,
                'order_id': int(log.order_id),
                'from_status': log.from_status,
                'to_status': log.to_status,
                'changed_by_user_id': log.changed_by_user_id,
                'changed_by_user': (
                    {
                        'user_id': getattr(reg, 'user_id', None),
                        'first_name': getattr(reg, 'firstName', None),
                        'last_name': getattr(reg, 'lastName', None),
                        'display_name': getattr(reg, 'displayName', None),
                        'mobile_number': getattr(reg, 'mobileNumber', None),
                        'email': getattr(reg, 'emailID', None),
                        'profile_image': profile_image,
                    } if reg else None
                ),
                'changed_by_role': log.changed_by_role,
                'source': log.source,
                'notes': log.notes,
                'metadata': log.metadata,
                'created_at': log.created_at.isoformat() if getattr(log, 'created_at', None) else None,
            })

        return Response({'success': True, 'count': total, 'results': results}, status=status.HTTP_200_OK)
    except Exception as e:
        return Response({'success': False, 'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
