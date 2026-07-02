from django.shortcuts import render
from django.http import JsonResponse
from django.db import connection
from django.db.utils import ProgrammingError, OperationalError
from django.utils import timezone
from django.db import models
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
import json
import logging
from types import SimpleNamespace
from .models import BusinessProfile, BusinessAlert, BusinessPerformanceMetrics, BusinessOwnerDetails
from kirazee_app.models import Business, Registration, BusinessFinancial
from business.models import MenuItems, BOM, FashionProduct, FashionProductVariant
from consumer.gro_models import GroceriesProducts, GroceriesProductVariants, BusinessFeedback
from delivery.models import DeliveryPartner
from consumer.models import Payments, DeliveryCharges, PointsConfiguration, BusinessOrderTypes, Rating
from datetime import date, timedelta

logger = logging.getLogger(__name__)


# ============================================================================
# COMPREHENSIVE BUSINESS DETAILS API
# ============================================================================

class BusinessDetailsView(APIView):
    """
    Get comprehensive business details for Swiggy-style admin panel
    GET /api/v1/admin/businesses/{business_id}/details/
    """
    permission_classes = []
    
    def get(self, request, business_id):
        logger.info(f"=== BusinessDetailsView GET called for business_id={business_id} ===")
        try:
            # Get basic business information
            try:
                business = Business.objects.get(business_id=business_id)
                logger.info(f"Business found: {business.businessName}")
                logger.info(f"Business level: '{business.level}'")
                logger.info(f"Business master: '{business.master}'")
            except Business.DoesNotExist:
                return Response({
                    'success': False,
                    'message': 'Business not found'
                }, status=status.HTTP_404_NOT_FOUND)
            
            # Get or create related profiles
            try:
                profile, created = BusinessProfile.objects.get_or_create(
                    business=business,
                    defaults={
                        'outlet_code': f'OUT{business_id.zfill(6)}',
                        'outlet_name': business.businessName,
                        'business_category_detailed': business.businessCategory,
                    }
                )
            except Exception as e:
                logger.error(f"BusinessProfile table missing or error: {e}")
                profile = SimpleNamespace(
                    outlet_code=f'OUT{business_id.zfill(6)}',
                    outlet_name=business.businessName,
                    business_category_detailed=business.businessCategory,
                    business_type_detailed=None,
                    kitchen_type=None,
                    operational_status='active',
                    closure_reason=None,
                    closure_notes=None,
                    hygiene_rating=None,
                    quality_score=None,
                    reliability_score=None,
                    max_orders_per_hour=None,
                    avg_prep_time_minutes=None,
                    kitchen_capacity=None,
                )

            #modified
            # Get owner details - For master businesses directly, for sublevel from their master
            # Follow table relation: businesses (level='master') → business_mapping (user_id) → registrations
            owner_details = None
            business_level = (business.level or '').strip().lower()
            master_business_id = None
            
            if business_level == 'master' or business_level == 'master level':
                # For master business, get owner details directly
                master_business_id = business.business_id
                try:
                    from kirazee_app.models import BusinessMapping
                    
                    business_mapping = BusinessMapping.objects.filter(
                        business_id=business.business_id,
                        status=True
                    ).first()
                    
                    if business_mapping:
                        registration = business_mapping.user
                        
                        if registration:
                            owner_details = {
                                'owner_name': f"{registration.firstName} {registration.lastName}",
                                'owner_email': registration.emailID,
                                'owner_phone': registration.mobileNumber,
                                'owner_country_code': registration.countryCode,
                                'user_id': registration.user_id,
                                'is_verified': registration.is_verified,
                                'user_mode': registration.user_mode,
                                'created_at': registration.created_at.isoformat() if registration.created_at else None,
                                'inherited_from_master': False,
                            }
                            logger.info(f"Owner details retrieved for master business {business.business_id}: {owner_details['owner_name']}")
                        else:
                            logger.warning(f"No registration found for business_mapping user_id for business {business.business_id}")
                    else:
                        logger.warning(f"No business_mapping found for master business {business.business_id}")
                        
                except Exception as e:
                    logger.error(f"Error fetching owner details for master business {business.business_id}: {e}")
            
            elif business.master:
                # For sublevel business, get owner details from master business
                master_business_id = business.master
                try:
                    from kirazee_app.models import BusinessMapping
                    
                    # Get master business's owner details
                    master_mapping = BusinessMapping.objects.filter(
                        business_id=business.master,
                        status=True
                    ).first()
                    
                    if master_mapping:
                        registration = master_mapping.user
                        
                        if registration:
                            owner_details = {
                                'owner_name': f"{registration.firstName} {registration.lastName}",
                                'owner_email': registration.emailID,
                                'owner_phone': registration.mobileNumber,
                                'owner_country_code': registration.countryCode,
                                'user_id': registration.user_id,
                                'is_verified': registration.is_verified,
                                'user_mode': registration.user_mode,
                                'created_at': registration.created_at.isoformat() if registration.created_at else None,
                                'inherited_from_master': True,
                                'master_business_id': business.master,
                            }
                            logger.info(f"Owner details inherited from master {business.master} for sublevel business {business.business_id}")
                        else:
                            logger.warning(f"No registration found for master business {business.master}")
                    else:
                        logger.warning(f"No business_mapping found for master business {business.master}")
                        
                except Exception as e:
                    logger.error(f"Error fetching owner details from master for sublevel business {business.business_id}: {e}")
            else:
                logger.info(f"No owner details for business {business.business_id} (level: {business.level}, master: {business.master})")
            
            # Get active alerts
            alerts = []
            try:
                alerts = list(
                    BusinessAlert.objects.filter(
                        business=business,
                        is_active=True,
                        is_resolved=False
                    ).order_by('-created_at')
                )
            except Exception as e:
                logger.error(f"Error fetching alerts: {e}")
            
            # Get performance metrics (ALL TIME - not limited to 30 days)
            performance_metrics = []
            try:
                performance_metrics = list(
                    BusinessPerformanceMetrics.objects.filter(
                        business=business
                    ).order_by('-date')
                )
            except Exception as e:
                logger.error(f"Error fetching performance metrics: {e}")
            
            # Calculate aggregated metrics from BusinessPerformanceMetrics if available (ALL TIME)
            total_orders = sum(m.total_orders for m in performance_metrics)
            total_revenue = sum(m.gross_revenue for m in performance_metrics)
            avg_completion_rate = sum(m.completion_rate for m in performance_metrics) / len(performance_metrics) if performance_metrics else 0
            valid_ratings = [m.customer_rating for m in performance_metrics if m.customer_rating]
            avg_rating = sum(valid_ratings) / len(valid_ratings) if valid_ratings else 0
            
            # Determine scope (include sub-branches)
            scope_ids = [business.business_id]
            branches = []
            try:
                if (business.level or '').strip().lower() == 'master':
                    branches = Business.objects.filter(master=business.business_id).values(
                        'business_id', 'businessName', 'city', 'state', 'status'
                    )
                    scope_ids.extend([b['business_id'] for b in branches])
            except Exception:
                pass
            
            logger.info(f"Business ID: {business.business_id}, Scope IDs: {scope_ids}")
            logger.info(f"DEBUG: performance_metrics={len(performance_metrics)}, total_orders={total_orders}, avg_completion_rate={avg_completion_rate}")
            
            # If no performance metrics data, calculate directly from orders tables (ALL TIME)
            if not performance_metrics or total_orders == 0:
                logger.info(f"=== CALCULATING METRICS FROM ORDERS TABLES (performance_metrics empty or no orders) ===")
                try:
                    with connection.cursor() as cursor:
                        # Calculate from orders table (restaurant/food orders) - ALL TIME
                        placeholders = ','.join(['%s'] * len(scope_ids))
                        
                        # Get total orders and revenue from orders table (ALL TIME - no date filter)
                        cursor.execute(
                            f"""
                            SELECT 
                                COUNT(*) as total_orders,
                                COALESCE(SUM(total_amount), 0) as total_revenue,
                                COALESCE(AVG(total_amount), 0) as avg_order_value,
                                SUM(CASE WHEN status = 'delivered' THEN 1 ELSE 0 END) as completed_orders,
                                SUM(CASE WHEN status = 'cancelled' THEN 1 ELSE 0 END) as cancelled_orders
                            FROM orders
                            WHERE business_id IN ({placeholders})
                            """,
                            scope_ids
                        )
                        orders_data = cursor.fetchone()
                        
                        logger.info(f"Orders query result (ALL TIME): {orders_data}, scope_ids: {scope_ids}")
                        
                        # Get total orders and revenue from Groceries_orders table (ALL TIME - no date filter)
                        cursor.execute(
                            f"""
                            SELECT 
                                COUNT(*) as total_orders,
                                COALESCE(SUM(total_amount), 0) as total_revenue,
                                COALESCE(AVG(total_amount), 0) as avg_order_value,
                                SUM(CASE WHEN order_status IN ('delivered', 'completed') THEN 1 ELSE 0 END) as completed_orders,
                                SUM(CASE WHEN order_status = 'cancelled' THEN 1 ELSE 0 END) as cancelled_orders
                            FROM Groceries_orders
                            WHERE business_id IN ({placeholders})
                            """,
                            scope_ids
                        )
                        grocery_data = cursor.fetchone()
                        
                        logger.info(f"Groceries query result (ALL TIME): {grocery_data}")
                        
                        # Combine both order types
                        total_orders = int(orders_data[0] or 0) + int(grocery_data[0] or 0)
                        total_revenue = float(orders_data[1] or 0) + float(grocery_data[1] or 0)
                        completed_orders_count = int(orders_data[3] or 0) + int(grocery_data[3] or 0)
                        cancelled_orders_count = int(orders_data[4] or 0) + int(grocery_data[4] or 0)
                        
                        # Calculate completion rate: (delivered + completed) / (total - cancelled) * 100
                        valid_orders = total_orders - cancelled_orders_count
                        avg_completion_rate = (completed_orders_count / valid_orders) if valid_orders > 0 else 0
                        
                        logger.info(f"Completion Rate Calculation: completed={completed_orders_count}, cancelled={cancelled_orders_count}, total={total_orders}, valid={valid_orders}, rate={avg_completion_rate}")
                        logger.info(f"Orders table: total={orders_data[0]}, completed={orders_data[3]}, cancelled={orders_data[4]}")
                        logger.info(f"Groceries table: total={grocery_data[0]}, completed={grocery_data[3]}, cancelled={grocery_data[4]}")
                        logger.info(f"Calculated from orders tables (ALL TIME): total_orders={total_orders}, total_revenue={total_revenue}, completion_rate={avg_completion_rate}")
                        
                except Exception as e:
                    logger.error(f"Error calculating metrics from orders tables: {e}")
                    # Keep the zero values if calculation fails
            
            # Get recent orders (ALL orders, not just last 10)
            recent_orders = []
            try:
                with connection.cursor() as cursor:
                    cursor.execute("""
                        SELECT order_id, status, total_amount, created_at, user_id
                        FROM orders 
                        WHERE business_id = %s 
                        ORDER BY created_at DESC
                    """, [business_id])
                    orders_data = cursor.fetchall()
                    
                    logger.info(f"Recent orders query for business_id={business_id}: found {len(orders_data)} orders")
                    
                    for order in orders_data:
                        recent_orders.append({
                            'order_id': order[0],
                            'status': order[1],
                            'amount': float(order[2]) if order[2] else 0,
                            'created_at': order[3].isoformat() if order[3] else None,
                            'user_id': order[4]
                        })
            except Exception as e:
                logger.error(f"Error fetching recent orders: {e}")
            
            # Menu Management: full lists
            menu_items_count = 0
            menu_items = []
            grocery_products = []
            fashion_products = []
            
            logger.info(f"Starting menu items fetch for business_id={business_id}, scope_ids={scope_ids}")
            print(f"\n{'='*80}")
            print(f"MENU ITEMS DEBUG - Business ID: {business_id}")
            print(f"Scope IDs: {scope_ids}")
            print(f"{'='*80}\n")
            
            try:
                from django.conf import settings
                print(f"MEDIA_URL from settings: {settings.MEDIA_URL}")
                
                # Get the request to build absolute URLs
                request_obj = request
                
                menu_qs = MenuItems.objects.filter(business_id__business_id__in=scope_ids, status=True)
                menu_items_count = menu_qs.count()
                
                logger.info(f"Found {menu_items_count} menu items for scope_ids={scope_ids}")
                print(f"Found {menu_items_count} menu items")
                
                for m in menu_qs.only('item_id', 'item_name', 'item_category', 'size_label', 'selling_price', 'is_active', 'status', 'item_image', 'updated_at', 'business_id'):
                    # Construct proper image URL
                    image_url = None
                    if m.item_image:
                        image_path = str(m.item_image)
                        if image_path:
                            # Remove 'media/' prefix if it exists (avoid double media/)
                            if image_path.startswith('media/'):
                                image_path = image_path[6:]  # Remove 'media/' prefix
                            
                            # Decode URL-encoded characters (e.g., %20 to space)
                            from urllib.parse import unquote
                            image_path = unquote(image_path)
                            
                            # Build absolute URL with backend host
                            if not image_path.startswith('http'):
                                # Get the backend host from the request
                                backend_host = request_obj.build_absolute_uri('/')[:-1]  # Remove trailing slash
                                image_url = f"{backend_host}{settings.MEDIA_URL}{image_path}"
                            else:
                                image_url = image_path
                    
                    item_data = {
                        'item_id': m.item_id,
                        'business_id': getattr(getattr(m, 'business_id', None), 'business_id', None),
                        'name': m.item_name,
                        'category': m.item_category,
                        'size_label': m.size_label,
                        'price': float(m.selling_price) if m.selling_price is not None else None,
                        'is_active': bool(m.is_active),
                        'status': bool(m.status),
                        'image': image_url,
                        'updated_at': m.updated_at.isoformat() if m.updated_at else None,
                    }
                    menu_items.append(item_data)
                    logger.info(f"Menu item {m.item_id}: image_path={str(m.item_image) if m.item_image else None}, image_url={image_url}")
                    print(f"  Item: {m.item_name}")
                    print(f"    - Raw image field: {str(m.item_image) if m.item_image else 'None'}")
                    print(f"    - Constructed URL: {image_url}")
                    print()
            except Exception as e:
                logger.error(f"Error fetching menu items: {e}")

            try:
                gp_qs = GroceriesProducts.objects.filter(business__business_id__in=scope_ids)
                product_ids = list(gp_qs.values_list('product_id', flat=True))
                variants_map = {}
                if product_ids:
                    for v in GroceriesProductVariants.objects.filter(product_id__in=product_ids):
                        variants_map.setdefault(v.product_id, []).append({
                            'variant_id': v.variant_id,
                            'sku': v.sku,
                            'size': v.size,
                            'net_weight': v.net_weight,
                            'net_weight_unit': v.net_weight_unit,
                            'price': float(v.selling_price) if v.selling_price is not None else None,
                            'stock': v.stock,
                            'is_active': bool(v.is_active),
                        })
                
                # Check if this is one of the three grocery businesses (case-insensitive)
                business_name_lower = business.businessName.lower() if business.businessName else ''
                is_grocery_business = any(name in business_name_lower for name in ['ecomall', 'rk supermarket', 'sv mart'])
                
                for p in gp_qs:
                    # Construct proper image URL for grocery products
                    image_url = None
                    if p.main_image:
                        image_path = str(p.main_image).strip()
                        if image_path:
                            # Remove 'media/' prefix if it exists
                            if image_path.startswith('media/'):
                                image_path = image_path[6:]
                            
                            # Decode URL-encoded characters (e.g., %20 to space)
                            from urllib.parse import unquote
                            image_path = unquote(image_path)
                            
                            # Build absolute URL with backend host
                            if not image_path.startswith('http'):
                                backend_host = request.build_absolute_uri('/')[:-1]
                                image_url = f"{backend_host}{settings.MEDIA_URL}{image_path}"
                            else:
                                image_url = image_path
                    
                    # Get subcategory name for the three grocery businesses
                    subcategory_name = None
                    if is_grocery_business:
                        subcategory_name = p.sub_category if hasattr(p, 'sub_category') else None
                    
                    # Get price from first variant for the three grocery businesses
                    price = None
                    if is_grocery_business:
                        variants = variants_map.get(p.product_id, [])
                        if variants and len(variants) > 0:
                            price = variants[0].get('price')
                    
                    grocery_products.append({
                        'product_id': p.product_id,
                        'business_id': getattr(getattr(p, 'business', None), 'business_id', None),
                        'name': p.product_name,
                        'category_id': getattr(p, 'category_id', None),
                        'subcategory': subcategory_name,  # Added subcategory name
                        'price': price,  # Added price from variants
                        'updated_at': p.updated_at.isoformat() if hasattr(p, 'updated_at') and p.updated_at else None,  # Added updated_at
                        'image': image_url,
                        'variants': variants_map.get(p.product_id, []),
                    })
            except Exception as e:
                logger.error(f"Error fetching grocery products: {e}")

            try:
                fp_qs = FashionProduct.objects.filter(business_id__business_id__in=scope_ids, is_active=True).select_related('category')
                product_ids = list(fp_qs.values_list('product_id', flat=True))
                variants_map = {}
                if product_ids:
                    for v in FashionProductVariant.objects.filter(product_id__in=product_ids):
                        variants_map.setdefault(v.product_id, []).append({
                            'variant_id': v.variant_id,
                            'sku': v.sku,
                            'size': v.size,
                            'color': v.color,
                            'material': v.material,
                            'gender': v.gender,
                            'price': float(v.selling_price) if v.selling_price is not None else None,
                            'mrp': float(v.mrp) if getattr(v, 'mrp', None) is not None else None,
                            'stock': v.stock,
                            'stock_qty': v.stock_qty,
                            'is_active': bool(v.is_active),
                        })
                for p in fp_qs.only('product_id', 'name', 'category', 'subcategory', 'main_image', 'business_id'):
                    fashion_products.append({
                        'product_id': p.product_id,
                        'business_id': getattr(getattr(p, 'business_id', None), 'business_id', None),
                        'name': p.name,
                        'category_id': getattr(p, 'category_id', None),
                        'category_name': getattr(getattr(p, 'category', None), 'category_name', None),
                        'subcategory_id': getattr(p, 'subcategory', None),
                        'image': p.main_image,
                        'variants': variants_map.get(p.product_id, []),
                    })
            except Exception as e:
                logger.error(f"Error fetching fashion products: {e}")

            # Delivery fleet information
            delivery_fleet = {
                'total_partners': 0,
                'available': 0,
                'on_delivery': 0,
                'offline': 0,
                'partners': []
            }
            try:
                partners = DeliveryPartner.objects.filter(business_id__in=scope_ids)
                delivery_fleet['total_partners'] = partners.count()
                delivery_fleet['available'] = partners.filter(status='available').count()
                delivery_fleet['on_delivery'] = partners.filter(status='on_delivery').count()
                delivery_fleet['offline'] = partners.filter(status='offline').count()
                for p in partners.only('user', 'vehicle_type', 'vehicle_number', 'phone_number', 'status', 'latitude', 'longitude'):
                    delivery_fleet['partners'].append({
                        'user_id': getattr(getattr(p, 'user', None), 'user_id', None),
                        'vehicle_type': p.vehicle_type,
                        'vehicle_number': p.vehicle_number,
                        'phone_number': p.phone_number,
                        'status': p.status,
                        'location': {'lat': p.latitude, 'lng': p.longitude} if (p.latitude is not None and p.longitude is not None) else None,
                    })
            except Exception as e:
                logger.error(f"Error fetching delivery fleet: {e}")

            # Offers & promotions (minimal)
            offers = []
            try:
                if scope_ids:
                    placeholders = ','.join(['%s'] * len(scope_ids))
                    with connection.cursor() as cursor:
                        cursor.execute(
                            f"""
                            SELECT promo_id, business_id, offer_type, title, description, discount_percentage, discount_amount,
                                   original_price, offer_price, valid_from, valid_to, is_active, is_approved
                            FROM promotional_offers
                            WHERE business_id IN ({placeholders})
                            ORDER BY valid_from DESC
                            LIMIT 50
                            """,
                            scope_ids
                        )
                        for r in cursor.fetchall():
                            offers.append({
                                'promo_id': r[0], 'business_id': r[1], 'offer_type': r[2], 'title': r[3], 'description': r[4],
                                'discount_percentage': float(r[5]) if r[5] is not None else None,
                                'discount_amount': float(r[6]) if r[6] is not None else None,
                                'original_price': float(r[7]) if r[7] is not None else None,
                                'offer_price': float(r[8]) if r[8] is not None else None,
                                'valid_from': r[9].isoformat() if r[9] else None,
                                'valid_to': r[10].isoformat() if r[10] else None,
                                'is_active': bool(r[11]), 'is_approved': bool(r[12])
                            })
            except Exception as e:
                logger.error(f"Error fetching offers: {e}")

            # Inventory & stock
            inventory = {
                'bom_items': [],
                'low_stock_variants': []
            }
            try:
                for b in BOM.objects.filter(business_id__business_id__in=scope_ids).only('bom_id', 'product_id', 'ingredients', 'quantity', 'unit', 'cost', 'status'):
                    inventory['bom_items'].append({
                        'bom_id': b.bom_id,
                        'menu_item_id': getattr(getattr(b, 'product_id', None), 'item_id', None),
                        'ingredients': b.ingredients,
                        'quantity': float(b.quantity) if b.quantity is not None else None,
                        'unit': b.unit,
                        'cost': float(b.cost) if b.cost is not None else None,
                        'status': bool(b.status)
                    })
            except Exception as e:
                logger.error(f"Error fetching BOM: {e}")
            try:
                low_variants = GroceriesProductVariants.objects.filter(product__business__business_id__in=scope_ids, stock__lte=5).only('variant_id', 'product', 'sku', 'stock')
                for v in low_variants:
                    inventory['low_stock_variants'].append({
                        'variant_id': v.variant_id,
                        'product_id': getattr(getattr(v, 'product', None), 'product_id', None),
                        'sku': v.sku,
                        'stock': v.stock,
                    })
            except Exception as e:
                logger.error(f"Error fetching low stock variants: {e}")

            try:
                low_fashion_variants = FashionProductVariant.objects.filter(product__business_id__business_id__in=scope_ids, stock__lte=5).only('variant_id', 'product', 'sku', 'stock')
                for v in low_fashion_variants:
                    inventory['low_stock_variants'].append({
                        'variant_id': v.variant_id,
                        'product_id': getattr(getattr(v, 'product', None), 'product_id', None),
                        'sku': v.sku,
                        'stock': v.stock,
                    })
            except Exception as e:
                logger.error(f"Error fetching low stock fashion variants: {e}")

            # Category breakdown for all businesses
            category_breakdown = []
            try:
                with connection.cursor() as cursor:
                    # Check business type to determine which logic to use
                    placeholders = ','.join(['%s'] * len(scope_ids))
                    cursor.execute(
                        f"""
                        SELECT businessCategory, businessType
                        FROM businesses 
                        WHERE business_id IN ({placeholders})
                        LIMIT 1
                        """,
                        scope_ids
                    )
                    business_info = cursor.fetchone()
                    
                    if business_info:
                        business_category = business_info[0]
                        business_type = business_info[1]
                        logger.info(f"Business category: {business_category}, type: {business_type}")
                        
                        # Restaurants (R02) and Food businesses should use menuitems
                        if business_type == 'R02' or business_category in ['Restaurant', 'Food', 'Food & Beverage']:
                            logger.info("Using menuitems logic for restaurant/food business")
                            cursor.execute(
                                f"""
                                SELECT 
                                    item_category,
                                    COUNT(*) as item_count
                                FROM menuitems
                                WHERE business_id IN ({placeholders}) 
                                AND status = 1
                                AND item_category IS NOT NULL
                                AND item_category != ''
                                GROUP BY item_category
                                ORDER BY item_count DESC
                                """,
                                scope_ids
                            )
                            for row in cursor.fetchall():
                                category_breakdown.append({
                                    'category': row[0],
                                    'count': int(row[1])
                                })
                            logger.info(f"Category breakdown from menuitems: {category_breakdown}")
                        else:
                            # Supermarkets and other businesses use category_mapping
                            logger.info("Using category_mapping logic for supermarket/business")
                            cursor.execute(
                                f"""
                                SELECT 
                                    uc.category_name,
                                    COUNT(DISTINCT cm.category_id) as category_count
                                FROM category_mapping cm
                                JOIN universal_Categories uc ON cm.category_id = uc.category_id
                                WHERE cm.business_id IN ({placeholders}) 
                                AND cm.is_active = 1
                                GROUP BY uc.category_name
                                ORDER BY category_count DESC
                                """,
                                scope_ids
                            )
                            for row in cursor.fetchall():
                                category_breakdown.append({
                                    'category': row[0],
                                    'count': int(row[1])
                                })
                            logger.info(f"Category breakdown from category_mapping: {category_breakdown}")
                    else:
                        # Fallback to original logic if business info not found
                        logger.warning("Business info not found, using fallback logic")
                        cursor.execute(
                            f"""
                            SELECT COUNT(*) 
                            FROM category_mapping 
                            WHERE business_id IN ({placeholders}) AND is_active = 1
                            """,
                            scope_ids
                        )
                        has_category_mapping = cursor.fetchone()[0] > 0
                        
                        if has_category_mapping:
                            cursor.execute(
                                f"""
                                SELECT 
                                    uc.category_name,
                                    COUNT(DISTINCT cm.category_id) as category_count
                                FROM category_mapping cm
                                JOIN universal_Categories uc ON cm.category_id = uc.category_id
                                WHERE cm.business_id IN ({placeholders}) 
                                AND cm.is_active = 1
                                GROUP BY uc.category_name
                                ORDER BY category_count DESC
                                """,
                                scope_ids
                            )
                            for row in cursor.fetchall():
                                category_breakdown.append({
                                    'category': row[0],
                                    'count': int(row[1])
                                })
                            logger.info(f"Category breakdown from category_mapping (fallback): {category_breakdown}")
                        else:
                            cursor.execute(
                                f"""
                                SELECT 
                                    item_category,
                                    COUNT(*) as item_count
                                FROM menuitems
                                WHERE business_id IN ({placeholders}) 
                                AND status = 1
                                AND item_category IS NOT NULL
                                AND item_category != ''
                                GROUP BY item_category
                                ORDER BY item_count DESC
                                """,
                                scope_ids
                            )
                            for row in cursor.fetchall():
                                category_breakdown.append({
                                    'category': row[0],
                                    'count': int(row[1])
                                })
                            logger.info(f"Category breakdown from menuitems (fallback): {category_breakdown}")
            except Exception as e:
                logger.error(f"Error fetching category breakdown: {e}")

            # Payments & settlements (summary + ALL payments)- modified 
            payments_settlements = {
                'totals': {
                    'success_amount': 0.0,
                    'pending_amount': 0.0,
                    'failed_amount': 0.0,
                    'count_success': 0,
                    'count_pending': 0,
                    'count_failed': 0,
                },
                'recent_payments': []
            }
            try:
                pay_qs = Payments.objects.filter(business__business_id__in=scope_ids)
                payments_settlements['totals']['count_success'] = pay_qs.filter(status=Payments.Status.SUCCESS).count()
                payments_settlements['totals']['count_pending'] = pay_qs.filter(status=Payments.Status.PENDING).count()
                payments_settlements['totals']['count_failed'] = pay_qs.filter(status=Payments.Status.FAILED).count()
                # Aggregate amounts
                from django.db.models import Sum
                payments_settlements['totals']['success_amount'] = float(pay_qs.filter(status=Payments.Status.SUCCESS).aggregate(total=Sum('amount')).get('total') or 0)
                payments_settlements['totals']['pending_amount'] = float(pay_qs.filter(status=Payments.Status.PENDING).aggregate(total=Sum('amount')).get('total') or 0)
                payments_settlements['totals']['failed_amount'] = float(pay_qs.filter(status=Payments.Status.FAILED).aggregate(total=Sum('amount')).get('total') or 0)
                # ALL payments (removed limit to show all records)
                for p in pay_qs.order_by('-created_at'):
                    payments_settlements['recent_payments'].append({
                        'id': p.id,
                        'order_id': p.order_id,
                        'amount': float(p.amount),
                        'status': p.status,
                        'method': p.payment_method,
                        'created_at': p.created_at.isoformat() if p.created_at else None,
                    })
            except Exception as e:
                logger.error(f"Error fetching payments: {e}")

            # Consumer report (ALL TIME, high level)
            consumer_report = {
                'period_days': 'all_time',  # Changed from 30 to indicate all time data
                'total_orders': 0,
                'total_revenue': 0.0
            }
            try:
                with connection.cursor() as cursor:
                    placeholders = ','.join(['%s'] * len(scope_ids))
                    # Get ALL orders from orders table (no date filter)
                    cursor.execute(
                        f"""
                        SELECT COUNT(*), COALESCE(SUM(final_amount),0)
                        FROM orders
                        WHERE business_id IN ({placeholders})
                        """,
                        scope_ids
                    )
                    row1 = cursor.fetchone() or (0, 0)
                    # Get ALL orders from Groceries_orders table (no date filter)
                    cursor.execute(
                        f"""
                        SELECT COUNT(*), COALESCE(SUM(total_amount),0)
                        FROM Groceries_orders
                        WHERE business_id IN ({placeholders})
                        """,
                        scope_ids
                    )
                    row2 = cursor.fetchone() or (0, 0)
                    consumer_report['total_orders'] = int(row1[0] or 0) + int(row2[0] or 0)
                    consumer_report['total_revenue'] = float(row1[1] or 0) + float(row2[1] or 0)
            except Exception as e:
                logger.error(f"Error computing consumer report: {e}")

            # Business settings/configurations
            business_settings = {
                'delivery_charges': None,
                'points_configuration': None,
                'order_types': None
            }
            try:
                dc = DeliveryCharges.objects.filter(business_id__business_id=business.business_id).first()
                if dc:
                    business_settings['delivery_charges'] = {
                        'delivery_id': dc.delivery_id,
                        'base_charge': float(getattr(dc, 'base_charge', 0) or 0),
                        'free_delivery_above': float(getattr(dc, 'free_delivery_above', 0) or 0),
                        'distance_slabs': getattr(dc, 'distance_slabs', None),
                        'is_active': bool(getattr(dc, 'is_active', True)),
                    }
            except Exception as e:
                logger.error(f"Error fetching delivery charges: {e}")
            try:
                pc = PointsConfiguration.objects.filter(business_id__business_id=business.business_id, is_active=True).first()
                if pc:
                    business_settings['points_configuration'] = {
                        'points_per_rupee_spent': float(getattr(pc, 'points_per_rupee_spent', 0) or 0),
                        'points_per_rupee_value': float(getattr(pc, 'points_per_rupee_value', 0) or 0),
                        'min_order_amount': float(getattr(pc, 'min_order_amount', 0) or 0),
                        'max_points_per_order': getattr(pc, 'max_points_per_order', None),
                    }
            except Exception as e:
                logger.error(f"Error fetching points configuration: {e}")
            try:
                bot = BusinessOrderTypes.objects.filter(business__business_id=business.business_id, is_active=True).first()
                if bot:
                    business_settings['order_types'] = getattr(bot, 'order_types', None)
            except Exception as e:
                logger.error(f"Error fetching order types: {e}")

            # Financials - For sublevel businesses, inherit from master
            financials = None
            financials_inherited = False
            
            try:
                # If sublevel, fetch from master business
                if business_level != 'master' and business_level != 'master level' and business.master:
                    # Fetch financials using the master's business_id
                    bf = BusinessFinancial.objects.filter(business__business_id=business.master).first()
                    financials_inherited = True
                    logger.info(f"Fetching financials from master {business.master} for sublevel business {business.business_id}")
                else:
                    # Fetch financials for the current business
                    bf = BusinessFinancial.objects.filter(business__business_id=business.business_id).first()
                    financials_inherited = False
                
                if bf:
                    financials = {
                        'owner_pan': bf.owner_pan,
                        'gstin': bf.gstin,
                        'ifsc_code': bf.ifsc_code,
                        'account_number': bf.account_number,
                        'razor_pay_key_id': bf.razor_pay_key_id,
                        'razor_pay_key_code': bf.razor_pay_key_code,
                        'razor_webhook_secret': bf.razor_webhook_secret,
                        'fssai_certification_number': bf.fssai_certification_number,
                        'updated_at': bf.updated_at.isoformat() if bf.updated_at else None,
                        'inherited_from_master': financials_inherited,
                    }
                    if financials_inherited:
                        financials['master_business_id'] = business.master
                    logger.info(f"Financials retrieved successfully for business {business.business_id}, inherited: {financials_inherited}")
                else:
                    logger.warning(f"No BusinessFinancial record found for business {business.business_id if not financials_inherited else business.master}")
            except Exception as e:
                logger.error(f"Error fetching business financials: {e}")
                import traceback
                logger.error(traceback.format_exc())
            
            # Calculate ratings from different sources
            # 1. Business Rating - from business_feedback table
            business_rating_avg = BusinessFeedback.objects.filter(
                business__business_id__in=scope_ids
            ).aggregate(avg_rating=models.Avg('rating'))['avg_rating'] or 0
            
            business_rating_count = BusinessFeedback.objects.filter(
                business__business_id__in=scope_ids
            ).count()
            
            # 2. Order Rating - from rating table where order_id is not null
            order_rating_avg = Rating.objects.filter(
                business_id__business_id__in=scope_ids,
                order_id__isnull=False
            ).aggregate(avg_rating=models.Avg('rating'))['avg_rating'] or 0
            
            order_rating_count = Rating.objects.filter(
                business_id__business_id__in=scope_ids,
                order_id__isnull=False
            ).count()
            
            # 3. Product Rating - from rating table where product_id is not null
            product_rating_avg = Rating.objects.filter(
                business_id__business_id__in=scope_ids,
                product_id__isnull=False
            ).aggregate(avg_rating=models.Avg('rating'))['avg_rating'] or 0
            
            product_rating_count = Rating.objects.filter(
                business_id__business_id__in=scope_ids,
                product_id__isnull=False
            ).count()
            
            # Compile comprehensive response
            response_data = {
                'success': True,
                'business_details': {
                    # 1. Basic Business Information
                    'basic_info': {
                        'business_id': business.business_id,
                        'business_name': business.businessName,
                        'level': business.level,
                        'master': business.master,
                        'outlet_code': profile.outlet_code,
                        'outlet_name': profile.outlet_name,
                        'business_category': business.businessCategory,
                        'business_category_detailed': profile.business_category_detailed,
                        'business_type': business.businessType,
                        'business_type_detailed': profile.business_type_detailed,
                        'kitchen_type': profile.kitchen_type,
                        'email': business.businessEmail,
                        'phone': business.businessNumber,
                        'whatsapp': business.businessWhatsapp,
                        'address': business.address,
                        'city': business.city,
                        'state': business.state,
                        'pincode': business.pincode,
                        'latitude': float(business.latitude) if business.latitude else None,
                        'longitude': float(business.longitude) if business.longitude else None,
                        'created_at': business.created_at.isoformat(),
                        'is_verified': business.is_verified,
                        'payment_status': business.paymentstatus,
                    },
                    
                    # 2. Status Indicators
                    'status_info': {
                        'operational_status': profile.operational_status,
                        'closure_reason': profile.closure_reason,
                        'closure_notes': profile.closure_notes,
                        'is_active': business.status,
                        'hygiene_rating': float(profile.hygiene_rating) if profile.hygiene_rating else None,
                        'quality_score': float(profile.quality_score) if profile.quality_score else None,
                        'reliability_score': float(profile.reliability_score) if profile.reliability_score else None,
                    },
                    
                    # 3. Owner & Admin Details (only for master businesses)
                    'owner_details': owner_details if owner_details else None,
                    
                    # 4. Financials (from business_financials)
                    'financials': financials,
                    
                    # 5. Order & Sales Analytics (ALL TIME)
                    'analytics': {
                        'period_days': 'all_time',  # Changed from 30 to indicate all time data
                        'total_orders': total_orders,
                        'total_revenue': float(total_revenue),
                        'average_order_value': float(total_revenue / total_orders) if total_orders > 0 else 0,
                        'completion_rate': float(avg_completion_rate),
                        'customer_rating': float(avg_rating),
                        'menu_items_count': menu_items_count,
                        'max_orders_per_hour': profile.max_orders_per_hour,
                        'avg_prep_time_minutes': profile.avg_prep_time_minutes,
                        'kitchen_capacity': profile.kitchen_capacity,
                        # New rating breakdown
                        'ratings': {
                            'business_rating': {
                                'average': float(business_rating_avg),
                                'count': business_rating_count
                            },
                            'order_rating': {
                                'average': float(order_rating_avg),
                                'count': order_rating_count
                            },
                            'product_rating': {
                                'average': float(product_rating_avg),
                                'count': product_rating_count
                            }
                        }
                    },
                    
                    # 6. Menu Management (full data)
                    'menu_management': {
                        'menu_items': menu_items,
                        'grocery_products': grocery_products,
                        'fashion_products': fashion_products,
                        'category_breakdown': category_breakdown  # Added for ecomall businesses
                    },
                    
                    # 7. System Flags & Alerts
                    'alerts': [
                        {
                            'id': alert.id,
                            'alert_type': alert.alert_type,
                            'severity': alert.severity,
                            'title': alert.title,
                            'message': alert.message,
                            'created_at': alert.created_at.isoformat(),
                            'alert_data': alert.alert_data,
                        }
                        for alert in alerts
                    ],
                    
                    # 8. Recent Orders
                    'recent_orders': recent_orders,
                    
                    # 9. Branch Information and scope
                    'branches': list(branches),
                    'scope_business_ids': scope_ids,

                    # 10. Delivery Fleet
                    'delivery_fleet': delivery_fleet,

                    # 11. Offers & Promotions
                    'offers': offers,

                    # 12. Inventory & Stock
                    'inventory': inventory,

                    # 13. Payments & Settlements
                    'payments_settlements': payments_settlements,

                    # 14. Consumer Report (last 30 days)
                    'consumer_report': consumer_report,

                    # 15. Business Settings / Configurations
                    'business_settings': business_settings,
                }
            }
            
            return Response(response_data, status=status.HTTP_200_OK)
            
        except Exception as e:
            logger.error(f"Error fetching business details: {str(e)}")
            return Response({
                'success': False,
                'message': f'Error fetching business details: {str(e)}'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class BusinessAlertsView(APIView):
    """
    Manage business alerts
    GET /api/v1/admin/businesses/{business_id}/alerts/
    POST /api/v1/admin/businesses/{business_id}/alerts/
    """
    permission_classes = []
    
    def get(self, request, business_id):
        try:
            alerts_data = []
            try:
                alerts = list(
                    BusinessAlert.objects.filter(
                        business_id=business_id
                    ).order_by('-created_at')
                )
            except Exception as e:
                logger.error(f"Error fetching business alerts (likely missing table): {str(e)}")
                alerts = []

            for alert in alerts:
                alerts_data.append({
                    'id': alert.id,
                    'alert_type': alert.alert_type,
                    'severity': alert.severity,
                    'title': alert.title,
                    'message': alert.message,
                    'is_active': alert.is_active,
                    'is_resolved': alert.is_resolved,
                    'resolved_at': alert.resolved_at.isoformat() if alert.resolved_at else None,
                    'resolved_by': alert.resolved_by,
                    'resolution_notes': alert.resolution_notes,
                    'alert_data': alert.alert_data,
                    'auto_generated': alert.auto_generated,
                    'created_at': alert.created_at.isoformat(),
                })
            
            return Response({
                'success': True,
                'alerts': alerts_data
            }, status=status.HTTP_200_OK)
            
        except Exception as e:
            logger.error(f"Error fetching business alerts: {str(e)}")
            return Response({
                'success': False,
                'message': f'Error fetching alerts: {str(e)}'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    
    def post(self, request, business_id):
        try:
            data = request.data
            
            # Validate required fields
            required_fields = ['alert_type', 'severity', 'title', 'message']
            for field in required_fields:
                if not data.get(field):
                    return Response({
                        'success': False,
                        'message': f'Field "{field}" is required'
                    }, status=status.HTTP_400_BAD_REQUEST)
            
            # Create alert
            try:
                alert = BusinessAlert.objects.create(
                    business_id=business_id,
                    alert_type=data['alert_type'],
                    severity=data['severity'],
                    title=data['title'],
                    message=data['message'],
                    alert_data=data.get('alert_data'),
                    auto_generated=data.get('auto_generated', False)
                )
            except Exception as e:
                logger.error(f"Error creating business alert (likely missing table): {str(e)}")
                return Response({
                    'success': False,
                    'message': 'Alerts storage unavailable'
                }, status=status.HTTP_503_SERVICE_UNAVAILABLE)
            
            return Response({
                'success': True,
                'message': 'Alert created successfully',
                'alert_id': alert.id
            }, status=status.HTTP_201_CREATED)
            
        except Exception as e:
            logger.error(f"Error creating business alert: {str(e)}")
            return Response({
                'success': False,
                'message': f'Error creating alert: {str(e)}'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class BusinessAlertResolveView(APIView):
    """
    Resolve a business alert
    PATCH /api/v1/admin/businesses/{business_id}/alerts/{alert_id}/resolve/
    """
    permission_classes = []
    
    def patch(self, request, business_id, alert_id):
        try:
            data = request.data
            
            try:
                alert = BusinessAlert.objects.get(
                    id=alert_id,
                    business_id=business_id
                )
            except BusinessAlert.DoesNotExist:
                return Response({
                    'success': False,
                    'message': 'Alert not found'
                }, status=status.HTTP_404_NOT_FOUND)
            except Exception as e:
                logger.error(f"Error accessing business alerts (likely missing table): {str(e)}")
                return Response({
                    'success': False,
                    'message': 'Alerts storage unavailable'
                }, status=status.HTTP_503_SERVICE_UNAVAILABLE)
            
            # Update alert resolution
            alert.is_resolved = True
            alert.is_active = False
            alert.resolved_at = timezone.now()
            alert.resolved_by = data.get('resolved_by', 'admin')
            alert.resolution_notes = data.get('resolution_notes', '')
            try:
                alert.save()
            except Exception as e:
                logger.error(f"Error saving alert resolution (likely missing table): {str(e)}")
                return Response({
                    'success': False,
                    'message': 'Alerts storage unavailable'
                }, status=status.HTTP_503_SERVICE_UNAVAILABLE)
            
            return Response({
                'success': True,
                'message': 'Alert resolved successfully'
            }, status=status.HTTP_200_OK)
            
        except Exception as e:
            logger.error(f"Error resolving business alert: {str(e)}")
            return Response({
                'success': False,
                'message': f'Error resolving alert: {str(e)}'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
