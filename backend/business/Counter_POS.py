from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.response import Response
from django.db import transaction
from drf_yasg.utils import swagger_auto_schema
from django.shortcuts import get_object_or_404
from django.conf import settings
from django.core.mail import send_mail
from kirazee_app.models import Business, Registration
from .models import (
    BusinessCounterOrders, 
    BusinessCounterItems, 
    BusinessCounterLogs,
    MenuItems,
    productItems,
    MenuItemVariant,
    FashionProductVariant,
    FashionProduct
)
from consumer.gro_models import GroceriesProductVariants, GroceriesProducts, GroceriesCategories
from management.models import BusinessTaxInvoice
from .serializers import (
    BusinessCounterOrdersSerializer,
    BusinessCounterItemsSerializer,
    BusinessCounterLogsSerializer
)
from management.serializers import BusinessTaxInvoiceSerializer
import json
from decimal import Decimal, ROUND_HALF_UP
from django.db.models import Sum, Case, When, F, Value, CharField, DecimalField
from django.db.models.functions import TruncDate
from datetime import datetime
from django.utils import timezone

_TWO_PLACES = Decimal('0.01')

def _q2(value):
    try:
        if value is None:
            value = Decimal('0')
        return Decimal(value).quantize(_TWO_PLACES, rounding=ROUND_HALF_UP)
    except Exception:
        return value
def get_client_ip(request):
    """Get client IP address from request"""
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')

    if x_forwarded_for:

        ip = x_forwarded_for.split(',')[0]

    else:

        ip = request.META.get('REMOTE_ADDR')

    return ip

def get_user_agent(request):

    """Get user agent from request"""

    return request.META.get('HTTP_USER_AGENT', '')[:255]

def send_counter_order_email(order):

    try:

        if not order.customer_email:

            return False

        from_email = getattr(settings, 'DEFAULT_FROM_EMAIL', None) or 'no-reply@kirazee.local'

        business_name = getattr(order.business_id, 'businessName', None) or 'Kirazee'

        subject = f"Order #{order.token_number} at {business_name}"

        created_at = order.created_at

        created_at_str = created_at.strftime('%d-%m-%Y %H:%M') if created_at else ''

        lines = []

        lines.append(f"Thank you for your order at {business_name}.")

        if created_at_str:

            lines.append(f"Date: {created_at_str}")

        lines.append("")

        lines.append("Order details:")

        for item in order.items.all():

            lines.append(f"- {item.item_name} x {item.quantity} @ {item.unit_price} = {item.line_total}")

        lines.append("")

        lines.append(f"Subtotal: {order.subtotal}")

        lines.append(f"GST: {order.gst_total}")

        lines.append(f"Discount: {order.discount_amount}")

        lines.append(f"Total amount: {order.total_amount}")

        lines.append(f"Paid: {order.paid_amount}")

        lines.append(f"Remaining: {order.remaining_amount}")

        body = "\n".join([str(x) for x in lines])

        html = "<br>".join([str(x) for x in lines])

        send_mail(subject, body, from_email, [order.customer_email], fail_silently=False, html_message=html)

        return True

    except Exception as e:

        print(f"Error sending counter order email: {str(e)}")

        return False

def send_counter_order_cancel_email(order, cancellation_reason):

    try:

        if not order.customer_email:

            return False

        from_email = getattr(settings, 'DEFAULT_FROM_EMAIL', None) or 'no-reply@kirazee.local'

        business_name = getattr(order.business_id, 'businessName', None) or 'Kirazee'

        subject = f"Order #{order.token_number} at {business_name} cancelled"

        created_at = order.created_at

        created_at_str = created_at.strftime('%d-%m-%Y %H:%M') if created_at else ''

        lines = []

        lines.append(f"Your order #{order.token_number} at {business_name} has been cancelled.")

        if created_at_str:

            lines.append(f"Order date: {created_at_str}")

        lines.append("")

        lines.append(f"Total amount: {order.total_amount}")

        lines.append("")

        if cancellation_reason:

            lines.append("Cancellation reason:")

            lines.append(str(cancellation_reason))

        body = "\n".join([str(x) for x in lines])

        html = "<br>".join([str(x) for x in lines])

        send_mail(subject, body, from_email, [order.customer_email], fail_silently=False, html_message=html)

        return True

    except Exception as e:

        print(f"Error sending counter order cancellation email: {str(e)}")

        return False

def create_log(business_id, user_id, action_type, reference_id=None, 

               old_data=None, new_data=None, description=None, 

               ip_address=None, user_agent=None, reason=None):

    """Helper function to create log entries"""

    try:

        # Ensure we pass actual model instances to FK fields

        if business_id is not None and not isinstance(business_id, Business):

            try:

                business_id = Business.objects.get(business_id=business_id)

            except Business.DoesNotExist:

                business_id = None



        if user_id is not None and not isinstance(user_id, Registration):

            try:

                user_id = Registration.objects.get(user_id=user_id)

            except Registration.DoesNotExist:

                user_id = None



        log = BusinessCounterLogs.objects.create(

            business_id=business_id,

            user_id=user_id,

            action_type=action_type,

            reference_id=reference_id,

            old_data=old_data,

            new_data=new_data,

            description=description,

            ip_address=ip_address,

            user_agent=user_agent,

            reason=reason

        )

        return log

    except Exception as e:

        # Log the error but don't fail the main operation

        print(f"Error creating log: {str(e)}")

        return None


def _as_int(value, default=None):
    if value is None or value == '':
        return default
    try:
        return int(value)
    except Exception:
        return default


def _ensure_both_ids_r02(*, item, business_id_str, quantity):
    menu_item_id = item.get('menu_item_id')
    product_id = item.get('product_id')
    variant_id = item.get('variant_id')
    if product_id:
        return Response(
            {'error': 'R02 (Restaurant) businesses cannot use product_id. Please use menu_item_id and/or variant_id.'},
            status=status.HTTP_400_BAD_REQUEST
        ), None

    mv = None
    if variant_id:
        try:
            mv = MenuItemVariant.objects.select_for_update().select_related('item').get(variant_id=variant_id, is_active=True)
        except MenuItemVariant.DoesNotExist:
            return Response({'error': f'Menu variant with ID {variant_id} not found'}, status=status.HTTP_404_NOT_FOUND), None

        if str(getattr(mv.item, 'business_id_id', None)) != str(business_id_str):
            return Response({'error': 'Menu variant does not belong to this business'}, status=status.HTTP_400_BAD_REQUEST), None

        if menu_item_id and str(mv.item.item_id) != str(menu_item_id):
            return Response({'error': f'Menu variant {variant_id} does not belong to item {menu_item_id}'}, status=status.HTTP_400_BAD_REQUEST), None

        item['menu_item_id'] = mv.item.item_id
        item['variant_id'] = mv.variant_id

    elif menu_item_id:
        try:
            mi = MenuItems.objects.select_for_update().get(item_id=menu_item_id)
        except MenuItems.DoesNotExist:
            return Response({'error': f'Menu item with ID {menu_item_id} not found'}, status=status.HTTP_404_NOT_FOUND), None

        mv = (
            MenuItemVariant.objects.select_for_update().filter(item_id=mi.item_id, is_active=True).order_by('variant_id').first()
        )
        if not mv:
            return Response({'error': f'No active variant found for menu item {menu_item_id}'}, status=status.HTTP_404_NOT_FOUND), None

        item['menu_item_id'] = mi.item_id
        item['variant_id'] = mv.variant_id

    else:
        return Response({'error': 'menu_item_id and/or variant_id is required for R02 items'}, status=status.HTTP_400_BAD_REQUEST), None

    if mv.stock_qty is not None and mv.stock_qty < quantity:
        return Response(
            {'error': f'Insufficient stock for variant {mv.variant_id}. Available: {mv.stock_qty}, Requested: {quantity}'},
            status=status.HTTP_400_BAD_REQUEST
        ), None

    item.pop('product_id', None)
    return None, {
        'type': 'menu_variant',
        'instance': mv,
        'quantity': quantity,
        'item_name': getattr(getattr(mv, 'item', None), 'item_name', str(mv.variant_id))
    }


def _ensure_both_ids_r08(*, item, business_id_str, quantity):
    menu_item_id = item.get('menu_item_id')
    product_id = item.get('product_id')
    variant_id = item.get('variant_id')
    if menu_item_id:
        return Response(
            {'error': 'R08 (Fashion) businesses cannot use menu_item_id. Please use product_id and/or variant_id.'},
            status=status.HTTP_400_BAD_REQUEST
        ), None

    fv = None
    if variant_id:
        try:
            fv = FashionProductVariant.objects.select_for_update().select_related('product').get(variant_id=variant_id, is_active=True)
        except FashionProductVariant.DoesNotExist:
            return Response({'error': f'Fashion variant with ID {variant_id} not found'}, status=status.HTTP_404_NOT_FOUND), None

        if str(getattr(fv, 'business_id_id', None)) != str(business_id_str):
            return Response({'error': 'Fashion variant does not belong to this business'}, status=status.HTTP_400_BAD_REQUEST), None

        resolved_product_id = getattr(getattr(fv, 'product', None), 'product_id', None)
        if product_id and str(product_id) != str(resolved_product_id):
            return Response({'error': f'Fashion variant {variant_id} does not belong to product {product_id}'}, status=status.HTTP_400_BAD_REQUEST), None

        item['variant_id'] = fv.variant_id
        item['product_id'] = resolved_product_id

    elif product_id:
        try:
            fp = FashionProduct.objects.select_for_update().get(product_id=product_id, business_id=business_id_str, is_active=True)
        except FashionProduct.DoesNotExist:
            return Response({'error': f'Fashion product with ID {product_id} not found'}, status=status.HTTP_404_NOT_FOUND), None

        resolved_variant_id = getattr(fp, 'variant_id', None)
        if resolved_variant_id:
            try:
                fv = FashionProductVariant.objects.select_for_update().select_related('product').get(variant_id=resolved_variant_id, is_active=True)
            except FashionProductVariant.DoesNotExist:
                return Response({'error': f'Fashion variant with ID {resolved_variant_id} not found'}, status=status.HTTP_404_NOT_FOUND), None
        else:
            fv = (
                FashionProductVariant.objects.select_for_update().select_related('product')
                .filter(product_id=product_id, is_active=True)
                .order_by('variant_id')
                .first()
            )
            if not fv:
                return Response({'error': f'No active variant found for fashion product {product_id}'}, status=status.HTTP_404_NOT_FOUND), None

        item['product_id'] = fp.product_id
        item['variant_id'] = fv.variant_id

    else:
        return Response({'error': 'product_id and/or variant_id is required for R08 items'}, status=status.HTTP_400_BAD_REQUEST), None

    if fv.stock is not None and fv.stock < quantity:
        return Response(
            {'error': f'Insufficient stock for variant {getattr(fv, "sku", fv.variant_id)}. Available: {fv.stock}, Requested: {quantity}'},
            status=status.HTTP_400_BAD_REQUEST
        ), None

    item.pop('menu_item_id', None)
    return None, {
        'type': 'fashion_variant',
        'instance': fv,
        'quantity': quantity,
        'item_name': getattr(fv, 'sku', str(fv.variant_id))
    }

def _ensure_both_ids_r01(*, item, quantity):
    menu_item_id = item.get('menu_item_id')
    product_id = item.get('product_id')
    variant_id = item.get('variant_id')
    if menu_item_id:
        return Response(
            {'error': f'R01 (Grocery) businesses cannot sell menu items. Item ID {menu_item_id} is a menu item. Please use grocery products with product_id and/or variant_id.'},
            status=status.HTTP_400_BAD_REQUEST
        ), None

    variant = None
    if variant_id:
        try:
            variant = GroceriesProductVariants.objects.select_for_update().get(variant_id=variant_id)
        except GroceriesProductVariants.DoesNotExist:
            return Response({'error': f'Product variant with ID {variant_id} not found'}, status=status.HTTP_404_NOT_FOUND), None

        resolved_product_id = getattr(variant, 'product_id', None)
        if product_id and str(product_id) != str(resolved_product_id):
            return Response({'error': f'Variant {variant_id} does not belong to product {product_id}'}, status=status.HTTP_400_BAD_REQUEST), None

        item['variant_id'] = variant.variant_id
        item['product_id'] = resolved_product_id

    elif product_id:
        try:
            variant = GroceriesProductVariants.objects.select_for_update().get(variant_id=product_id)
            item['variant_id'] = variant.variant_id
            item['product_id'] = variant.product_id
        except GroceriesProductVariants.DoesNotExist:
            try:
                grocery_product = GroceriesProducts.objects.select_for_update().get(product_id=product_id)
            except GroceriesProducts.DoesNotExist:
                try:
                    product_item = productItems.objects.select_for_update().get(item_id=product_id)
                    return Response(
                        {
                            'error': f'Product item with ID {product_id} is a legacy productItem. For R01 businesses, please use GroceriesProducts/GroceriesProductVariants. Item: {product_item.item_name}'
                        },
                        status=status.HTTP_400_BAD_REQUEST
                    ), None
                except productItems.DoesNotExist:
                    return Response(
                        {'error': f'Product item with ID {product_id} not found in variants or grocery products. Please verify the item ID is correct.'},
                        status=status.HTTP_404_NOT_FOUND
                    ), None

            variant = (
                GroceriesProductVariants.objects.select_for_update()
                .filter(product_id=product_id, is_active=True)
                .order_by('variant_id')
                .first()
            )
            if not variant:
                return Response({'error': f'No active variant found for grocery product {grocery_product.product_name}'}, status=status.HTTP_404_NOT_FOUND), None
            item['variant_id'] = variant.variant_id
            item['product_id'] = product_id

    else:
        return Response({'error': 'product_id and/or variant_id is required for R01 items'}, status=status.HTTP_400_BAD_REQUEST), None

    if variant.stock is not None and variant.stock < quantity:
        return Response(
            {'error': f'Insufficient stock for variant {getattr(variant, "sku", variant.variant_id)}. Available: {variant.stock}, Requested: {quantity}'},
            status=status.HTTP_400_BAD_REQUEST
        ), None

    item.pop('menu_item_id', None)
    return None, {
        'type': 'variant',
        'instance': variant,
        'quantity': quantity,
        'item_name': getattr(variant, 'sku', str(variant.variant_id))
    }

def _apply_stock_updates(stock_updates):
    for stock_update in stock_updates:
        if stock_update['type'] == 'menu_item':
            menu_item = stock_update['instance']
            menu_item.quantity = (menu_item.quantity or 0) - stock_update['quantity']
            menu_item.save(update_fields=['quantity'])
        elif stock_update['type'] == 'variant':
            variant = stock_update['instance']
            variant.stock = (variant.stock or 0) - stock_update['quantity']
            variant.save(update_fields=['stock'])
        elif stock_update['type'] == 'menu_variant':
            mv = stock_update['instance']
            mv.stock_qty = (mv.stock_qty or 0) - stock_update['quantity']
            mv.save(update_fields=['stock_qty'])
        elif stock_update['type'] == 'fashion_variant':
            fv = stock_update['instance']
            fv.stock = (fv.stock or 0) - stock_update['quantity']
            fv.save(update_fields=['stock'])

@swagger_auto_schema(methods=['POST'], tags=['Business'])
@api_view(['POST'])
def create_counter_order(request):
    """
    Create a new counter order with items
    Expected payload:
    {
        "business_id": "KIR123...",
        "user_id": 12345,
        "order_type": "menu",  # or "grocery" or "mixed"
        "payment_method": "cash",  # or "card", "upi", etc.
        "delivery_charges": 50.00,  # optional delivery charges
        "discount_amount": 0.00,
        "status": "paid",  # or "pending", "cancelled"
        "customer_mobile": "9999999999",
        "customer_email": "customer@example.com",
        "remarks": "Optional remarks",
        "items": [
            {
                "menu_item_id": 182250,  # or product_id for grocery
                "item_name": "Item Name",
                "sku": "item123",
                "quantity": 2,
                "unit_price": 100.00,
                "gst": 18.00,
                "is_customized": false,
                "customization_details": {},
                "notes": "Optional notes"
            }
        ]
    }
    """
    try:
        # Extract data from request
        business_id_str = request.data.get('business_id')
        user_id_int = request.data.get('user_id')
        if not business_id_str or not user_id_int:
            return Response(
                {'error': 'business_id and user_id are required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        # Validate business and user exist
        try:
            business = Business.objects.get(business_id=business_id_str)
        except Business.DoesNotExist:
            return Response(
                {'error': 'Invalid business_id'},
                status=status.HTTP_404_NOT_FOUND
            )
        # Business type validation
        business_type = getattr(business, 'businessType', None)
        if not business_type:
            return Response(
                {'error': 'Business type is not configured. Please contact support.'},
                status=status.HTTP_400_BAD_REQUEST
            )
        try:
            user = Registration.objects.get(user_id=user_id_int)
        except Registration.DoesNotExist:
            return Response(
                {'error': 'Invalid user_id'},
                status=status.HTTP_404_NOT_FOUND
            )
        # Extract items and calculate totals
        items_data = request.data.get('items', [])
        if not items_data:
            return Response(
                {'error': 'At least one item is required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        # Calculate order totals
        subtotal = Decimal('0.00')
        gst_total = Decimal('0.00')
        for item in items_data:
            quantity = Decimal(str(item.get('quantity', 1)))
            unit_price = Decimal(str(item.get('unit_price', 0)))
            gst_percent = Decimal(str(item.get('gst', 0)))
            item_total = _q2(unit_price * quantity)
            gst_amount = _q2((item_total * gst_percent) / Decimal('100'))
            # Store calculated values back to item data ensuring Decimals
            item['gst_amount'] = gst_amount
            item['unit_price'] = unit_price
            subtotal += item_total
            gst_total += gst_amount
        subtotal = _q2(subtotal)
        gst_total = _q2(gst_total)
        discount_amount = _q2(Decimal(str(request.data.get('discount_amount', 0))))
        discount_percentage = _q2(Decimal(str(request.data.get('discount_percentage', 0))))
        discount_type = request.data.get('discount_type', 'fixed')
        discount_reason = request.data.get('discount_reason', '')
        delivery_charges = _q2(Decimal(str(request.data.get('delivery_charges', 0))))
        # Calculate customization_charges based on customized items (10 per customized item)
        customization_count = sum(1 for item in items_data if item.get('is_customized', False))
        customization_charges = _q2(Decimal('10') * customization_count)
        total_amount = _q2(subtotal + gst_total + delivery_charges + customization_charges - discount_amount)
        # Prepare order data
        order_data = {
            'business_id': business_id_str,
            'user_id': user_id_int,
            'username': request.data.get('username', 'skipped'),
            'order_type': request.data.get('order_type', 'menu'),
            'service_mode': request.data.get('service_mode'),
            'payment_method': request.data.get('payment_method', 'cash'),
            'subtotal': str(subtotal),
            'gst_total': str(gst_total),
            'total_amount': str(total_amount),
            'delivery_charges': str(delivery_charges),
            'customization_charges': str(customization_charges),
            'discount_amount': str(discount_amount),
            'discount_percentage': str(discount_percentage),
            'discount_type': discount_type,
            'discount_reason': discount_reason,
            'status': request.data.get('status', 'pending'),
            'remarks': request.data.get('remarks', 'Counter order'),
            'customer_mobile': request.data.get('customer_mobile', 'skipped'),
            'customer_email': request.data.get('customer_email', 'skipped'),
            'offline_token_no': request.data.get('offline_token_no'),
            'items': items_data
        }
        # Initialize payment tracking fields
        if request.data.get('status', 'pending') == 'paid':
            order_data['paid_amount'] = str(total_amount)
            order_data['remaining_amount'] = str(Decimal('0.00'))
        else:
            order_data['paid_amount'] = str(Decimal('0.00'))
            order_data['remaining_amount'] = str(total_amount)
        order = None
        with transaction.atomic():
            stock_updates = []
            for idx, item in enumerate(items_data):
                quantity = _as_int(item.get('quantity', 1), default=1) or 1
                print(
                    f"DEBUG: Processing item {idx}: menu_item_id={item.get('menu_item_id')}, "
                    f"product_id={item.get('product_id')}, variant_id={item.get('variant_id')}, quantity={quantity}"
                )
                if business_type == 'R02':
                    resp, stock_update = _ensure_both_ids_r02(item=item, business_id_str=business_id_str, quantity=quantity)
                elif business_type == 'R08':
                    resp, stock_update = _ensure_both_ids_r08(item=item, business_id_str=business_id_str, quantity=quantity)
                else:
                    resp, stock_update = _ensure_both_ids_r01(item=item, quantity=quantity)

                if resp is not None:
                    return resp
                stock_updates.append(stock_update)

            order_data_without_items = order_data.copy()
            order_data_without_items.pop('items', None)
            serializer = BusinessCounterOrdersSerializer(data=order_data_without_items)
            if not serializer.is_valid():
                errors = serializer.errors
                if 'user_id' in errors:
                    return Response(
                        {'error': f'Invalid user_id: {errors["user_id"]}. Please ensure the user exists in the system.'},
                        status=status.HTTP_400_BAD_REQUEST
                    )
                return Response({'error': serializer.errors}, status=status.HTTP_400_BAD_REQUEST)

            order = serializer.save()
            _apply_stock_updates(stock_updates)

            for item_data in items_data:
                menu_item_id = item_data.get('menu_item_id')
                menu_item_instance = None
                if menu_item_id:
                    try:
                        menu_item_instance = MenuItems.objects.get(item_id=menu_item_id)
                    except MenuItems.DoesNotExist:
                        return Response(
                            {'error': f'Menu item with ID {menu_item_id} not found'},
                            status=status.HTTP_404_NOT_FOUND
                        )

                # Save product_id and variant_id for R01 (Grocery), R02 (Restaurant), and R08 (Fashion) businesses
                # R02 can use menu_item_id and variant_id for menu variants
                if business_type in ['R01', 'R02', 'R08']:
                    product_id_to_save = item_data.get('product_id') if business_type in ['R01', 'R08'] else None
                    variant_id_to_save = item_data.get('variant_id')
                else:
                    product_id_to_save = None
                    variant_id_to_save = None

                BusinessCounterItems.objects.create(
                    order_id=order,
                    business_id=order.business_id,
                    menu_item_id=menu_item_instance,
                    product_id=product_id_to_save,
                    variant_id=variant_id_to_save,
                    sku=item_data.get('sku', ''),
                    item_name=item_data.get('item_name', ''),
                    size_label=item_data.get('size_label', ''),
                    quantity=item_data.get('quantity', 1),
                    unit_price=item_data.get('unit_price', 0),
                    gst=item_data.get('gst_amount', 0),
                    line_total=item_data.get('line_total', 0),
                    is_customized=item_data.get('is_customized', False),
                    customization_details=item_data.get('customization_details', {}),
                    notes=item_data.get('notes', '')
                )

        if order and order.customer_email and order.customer_email != 'skipped':
            if send_counter_order_email(order) and not order.email_sent:
                order.email_sent = True
                order.save(update_fields=['email_sent'])

        if order:
            ip_address = get_client_ip(request)
            user_agent = get_user_agent(request)
            create_log(
                business_id=business,
                user_id=user.user_id,
                action_type='order_created',
                reference_id=str(order.order_id),
                new_data={
                    'order_id': order.order_id,
                    'token_number': order.token_number,
                    'order_type': order.order_type,
                    'service_mode': order.service_mode,
                    'payment_method': order.payment_method,
                    'total_amount': float(order.total_amount),
                    'status': order.status,
                    'items_count': len(items_data),
                    'stock_reduced': True
                },
                description=f"Counter order created with token #{order.token_number} and stock reduced",
                ip_address=ip_address,
                user_agent=user_agent
            )
            response_serializer = BusinessCounterOrdersSerializer(order)
            return Response(
                {
                    'success': True,
                    'message': f'Order created successfully with token #{order.token_number}',
                    'data': response_serializer.data
                },
                status=status.HTTP_201_CREATED
            )

    

    except Exception as e:

        return Response(

            {'error': f'An error occurred: {str(e)}'},

            status=status.HTTP_500_INTERNAL_SERVER_ERROR

        )

@swagger_auto_schema(methods=['GET'], tags=['Business'])
@api_view(['GET'])
def get_counter_orders(request, business_id):

    """

    Get counter orders for a business

    Query parameters:

    - Default (no params): Today's orders only
    - pages=all: Show all orders without date restriction
    - status: filter by order status
    - order_type: filter by order type
    - from_date: filter orders from this date (YYYY-MM-DD format)
    - to_date: filter orders to this date (YYYY-MM-DD format)
    - page: page number (default: 1)
    - page_size: number of orders per page (default: 50, max: 100)

    """

    try:

        # Validate business exists

        try:

            business = Business.objects.get(business_id=business_id)

        except Business.DoesNotExist:

            return Response(

                {'error': 'Invalid business_id'},

                status=status.HTTP_404_NOT_FOUND

            )

        

        # Get all business IDs for hierarchy (master + sub-levels)

        business_ids = [business_id]

        if business.level == 'master':

            # Add sub-level business IDs

            sub_ids = list(Business.objects.filter(master=business_id).values_list('business_id', flat=True))

            business_ids.extend(sub_ids)

        

        # Get all orders for this business hierarchy with optimized queries

        orders = BusinessCounterOrders.objects.filter(

            business_id__in=business_ids

        ).select_related(

            'user_id'

        ).prefetch_related(

            'items'

        )

        

        # Apply filters if provided

        order_status = request.GET.get('status')

        if order_status:

            orders = orders.filter(status=order_status)

        

        order_type = request.GET.get('order_type')

        if order_type:

            orders = orders.filter(order_type=order_type)

        

        # Handle date filters and default behavior
        from_date_str = request.GET.get('from_date')
        to_date_str = request.GET.get('to_date')
        pages_param = request.GET.get('pages')
        show_all_orders = pages_param == 'all'
        
        # Default behavior: show today's orders only (no date filters and not pages=all)
        if not from_date_str and not to_date_str and not show_all_orders:
            today = datetime.now().date()
            today_start = datetime.combine(today, datetime.min.time())
            today_end = datetime.combine(today, datetime.max.time())
            orders = orders.filter(created_at__gte=today_start, created_at__lte=today_end)
        
        # Apply explicit date filters if provided
        if from_date_str:
            try:
                from_date = datetime.strptime(from_date_str, '%Y-%m-%d').date()
                # Convert to datetime for filtering (start of day)
                from_datetime = datetime.combine(from_date, datetime.min.time())
                orders = orders.filter(created_at__gte=from_datetime)
            except ValueError:
                return Response(
                    {'error': 'Invalid from_date format. Use YYYY-MM-DD format.'},
                    status=status.HTTP_400_BAD_REQUEST
                )
        
        if to_date_str:
            try:
                to_date = datetime.strptime(to_date_str, '%Y-%m-%d').date()
                # Convert to datetime for filtering (end of day)
                to_datetime = datetime.combine(to_date, datetime.max.time())
                orders = orders.filter(created_at__lte=to_datetime)
            except ValueError:
                return Response(
                    {'error': 'Invalid to_date format. Use YYYY-MM-DD format.'},
                    status=status.HTTP_400_BAD_REQUEST
                )

        

        # Order by most recent first

        orders = orders.order_by('-created_at')

        

        # Get total count before pagination

        total_count = orders.count()

        

        # Add pagination for performance (default 50 orders per page)
        # Skip pagination if pages=all
        if show_all_orders:
            page = 1
            page_size = total_count  # Show all results
            start_offset = 0
            orders = orders[start_offset:]  # Get all orders
        else:
            try:
                page_size = int(request.GET.get('page_size', 50))
                page = int(request.GET.get('page', 1))
            except (ValueError, TypeError):
                page_size = 50
                page = 1
            
            # Ensure positive values
            page_size = max(1, min(page_size, 100))
            page = max(1, page)
            
            # Calculate total pages and validate requested page
            total_pages = max(1, (total_count + page_size - 1) // page_size)
            
            # If requested page exceeds total pages, return empty result
            if page > total_pages:
                return Response(
                    {
                        'success': True,
                        'count': total_count,
                        'pagination': {
                            'current_page': page,
                            'next_page': None,
                            'total_pages': total_pages,
                            'page_size': page_size,
                            'has_next': False,
                            'has_previous': page > 1,
                            'showing_all': False,
                            'page_exceeds_total': True
                        },
                        'filters_applied': {
                            'status': order_status,
                            'order_type': order_type,
                            'from_date': from_date_str if from_date_str else None,
                            'to_date': to_date_str if to_date_str else None,
                            'default_today_only': not from_date_str and not to_date_str and not show_all_orders
                        },
                        'data': []
                    },
                    status=status.HTTP_200_OK
                )
            
            # Apply pagination
            start_offset = (page - 1) * page_size
            orders = orders[start_offset:start_offset + page_size]

        

        # Optimize serializer to reduce database queries

        serializer = BusinessCounterOrdersSerializer(orders, many=True)

        

        # Calculate pagination info for normal response
        if not show_all_orders:
            total_pages = max(1, (total_count + page_size - 1) // page_size)
            next_page = page + 1 if page * page_size < total_count else None
        else:
            total_pages = 1
            next_page = None
        
        return Response(
            {
                'success': True,
                'count': total_count,
                'pagination': {
                    'current_page': page,
                    'next_page': next_page,
                    'total_pages': total_pages,
                    'page_size': page_size,
                    'has_next': page * page_size < total_count and not show_all_orders,
                    'has_previous': page > 1 and not show_all_orders,
                    'showing_all': show_all_orders
                },
                'filters_applied': {
                    'status': order_status,
                    'order_type': order_type,
                    'from_date': from_date_str if from_date_str else None,
                    'to_date': to_date_str if to_date_str else None,
                    'default_today_only': not from_date_str and not to_date_str and not show_all_orders
                },
                'data': serializer.data
            },
            status=status.HTTP_200_OK
        )

    

    except Exception as e:

        return Response(

            {'error': f'An error occurred: {str(e)}'},

            status=status.HTTP_500_INTERNAL_SERVER_ERROR

        )

@swagger_auto_schema(methods=['GET'], tags=['Business'])
@api_view(['GET'])
def get_counter_order_detail(request, business_id, order_id):

    """Get a specific counter order by ID"""

    try:

        # Get the order

        order = get_object_or_404(

            BusinessCounterOrders,

            order_id=order_id,

            business_id=business_id

        )

        

        # Serialize and return

        serializer = BusinessCounterOrdersSerializer(order)

        

        return Response(

            {

                'success': True,

                'data': serializer.data

            },

            status=status.HTTP_200_OK

        )

    

    except Exception as e:

        return Response(

            {'error': f'An error occurred: {str(e)}'},

            status=status.HTTP_500_INTERNAL_SERVER_ERROR

        )

@swagger_auto_schema(methods=['PUT', 'PATCH'], tags=['Business'])
@api_view(['PUT', 'PATCH'])
def update_counter_order(request, business_id, order_id):

    """

    Update a counter order

    Can update: status, payment_method, remarks, items

    """

    try:

        # Get the order

        order = get_object_or_404(

            BusinessCounterOrders,

            order_id=order_id,

            business_id=business_id

        )

        

        # Store old data for logging

        old_data = {

            'order_id': order.order_id,

            'token_number': order.token_number,

            'username': order.username,

            'status': order.status,

            'payment_method': order.payment_method,

            'total_amount': float(order.total_amount),

            'items_count': order.items.count()

        }

        

        # Update the order

        with transaction.atomic():

            # If items are being updated, recalculate totals

            if 'items' in request.data:

                items_data = request.data.get('items', [])

                

                subtotal = Decimal('0.00')

                gst_total = Decimal('0.00')

                

                for item in items_data:

                    quantity = Decimal(str(item.get('quantity', 1)))

                    unit_price = Decimal(str(item.get('unit_price', 0)))

                    gst_percent = Decimal(str(item.get('gst', 0)))

                    

                    item_total = _q2(unit_price * quantity)

                    gst_amount = _q2((item_total * gst_percent) / Decimal('100'))

                    item['gst'] = gst_amount  # Update for serializer to save as amount

                    item['unit_price'] = unit_price

                    subtotal += item_total

                    gst_total += gst_amount

                

                subtotal = _q2(subtotal)

                gst_total = _q2(gst_total)



                discount_amount = _q2(Decimal(str(request.data.get('discount_amount', order.discount_amount))))

                discount_percentage = Decimal(str(request.data.get('discount_percentage', order.discount_percentage)))

                discount_type = request.data.get('discount_type', order.discount_type)

                discount_reason = request.data.get('discount_reason', order.discount_reason)

                customization_charges = _q2(Decimal(str(request.data.get('customization_charges', order.customization_charges))))

                delivery_charges = _q2(Decimal(str(request.data.get('delivery_charges', order.delivery_charges))))

                total_amount = _q2(subtotal + gst_total + delivery_charges + customization_charges - discount_amount)

                

                request.data['subtotal'] = str(subtotal)

                request.data['gst_total'] = str(gst_total)

                request.data['total_amount'] = str(total_amount)

            

            serializer = BusinessCounterOrdersSerializer(

                order,

                data=request.data,

                partial=True

            )

            

            if serializer.is_valid():

                updated_order = serializer.save()

                

                # Create log entry for order update

                ip_address = get_client_ip(request)

                user_agent = get_user_agent(request)

                

                new_data = {

                    'order_id': updated_order.order_id,

                    'token_number': updated_order.token_number,

                    'username': updated_order.username,

                    'status': updated_order.status,

                    'payment_method': updated_order.payment_method,

                    'total_amount': float(updated_order.total_amount),

                    'items_count': updated_order.items.count()

                }

                

                create_log(

                    business_id=updated_order.business_id,

                    user_id=updated_order.user_id,

                    action_type='order_updated',

                    reference_id=str(updated_order.order_id),

                    old_data=old_data,

                    new_data=new_data,

                    description=f"Counter order #{updated_order.token_number} updated",

                    ip_address=ip_address,

                    user_agent=user_agent

                )

                

                # Return the updated order

                response_serializer = BusinessCounterOrdersSerializer(updated_order)

                return Response(

                    {

                        'success': True,

                        'message': 'Order updated successfully',

                        'data': response_serializer.data

                    },

                    status=status.HTTP_200_OK

                )

            else:

                return Response(

                    {'error': serializer.errors},

                    status=status.HTTP_400_BAD_REQUEST

                )

    

    except Exception as e:

        return Response(

            {'error': f'An error occurred: {str(e)}'},

            status=status.HTTP_500_INTERNAL_SERVER_ERROR

        )

@swagger_auto_schema(methods=['POST'], tags=['Business'])
@api_view(['POST'])
def cancel_counter_order(request, business_id, order_id):

    """Cancel a counter order (soft delete - updates status to 'cancelled')"""

    try:

        # Get the order

        order = get_object_or_404(

            BusinessCounterOrders,

            order_id=order_id,

            business_id=business_id

        )

        

        # Get business for type validation

        try:

            business = Business.objects.get(business_id=business_id)

        except Business.DoesNotExist:

            return Response(

                {'error': 'Invalid business_id'},

                status=status.HTTP_404_NOT_FOUND

            )

        

        # Business type validation

        business_type = getattr(business, 'businessType', None)

        

        # Store old data for logging

        old_data = {

            'order_id': order.order_id,

            'token_number': order.token_number,

            'status': order.status,

            'total_amount': float(order.total_amount)

        }

        

        # Update status to cancelled

        cancellation_reason = request.data.get('cancellation_reason')

        if not cancellation_reason:

            return Response(

                {'error': 'Cancellation reason is required'},

                status=status.HTTP_400_BAD_REQUEST

            )

        

        order.status = 'cancelled'

        order.cancellation_reason = cancellation_reason

        order.cancelled_at = datetime.now()

        order.save(update_fields=['status', 'cancellation_reason', 'cancelled_at'])

        

        # Restore stock for cancelled order items

        stock_restored = []

        try:

            with transaction.atomic():

                # Get all items for this order

                order_items = BusinessCounterItems.objects.filter(order_id=order)

                

                for item in order_items:

                    restored = False

                    

                    # Business type-specific stock restoration

                    if business_type == 'R02':

                        # R02 (Restaurant) businesses only use menu items

                        if item.menu_item_id:

                            try:

                                menu_item = MenuItems.objects.select_for_update().get(

                                    menu_item_id=item.menu_item_id,

                                    business_id=business_id

                                )

                                if menu_item.quantity is not None:

                                    menu_item.quantity = (menu_item.quantity or 0) + item.quantity

                                    menu_item.save(update_fields=['quantity'])

                                    stock_restored.append({

                                        'type': 'menu_item',

                                        'item_id': item.menu_item_id,

                                        'item_name': item.item_name,

                                        'quantity_restored': item.quantity

                                    })

                                    restored = True

                            except MenuItems.DoesNotExist:

                                pass

                        else:

                            # R02 business should not have grocery items, but log if found

                            stock_restored.append({

                                'type': 'invalid_for_business_type',

                                'item_name': item.item_name,

                                'sku': item.sku,

                                'quantity_restored': 0,

                                'note': f'R02 business should not have grocery items: {item.sku}'

                            })

                    

                    elif business_type == 'R01':

                        # R01 (Grocery) businesses only use grocery variants

                        if item.variant_id:

                            try:

                                variant = GroceriesProductVariants.objects.select_for_update().get(variant_id=item.variant_id)

                                if variant.stock is not None:

                                    variant.stock = (variant.stock or 0) + item.quantity

                                    variant.save(update_fields=['stock'])

                                    stock_restored.append({

                                        'type': 'variant',

                                        'item_id': variant.variant_id,

                                        'item_name': item.item_name,

                                        'sku': item.sku,

                                        'quantity_restored': item.quantity

                                    })

                                    restored = True

                            except GroceriesProductVariants.DoesNotExist:

                                pass

                        elif item.product_id:

                            # Try to find variant by product_id

                            try:

                                variant = GroceriesProductVariants.objects.select_for_update().get(product_id=item.product_id)

                                if variant.stock is not None:

                                    variant.stock = (variant.stock or 0) + item.quantity

                                    variant.save(update_fields=['stock'])

                                    stock_restored.append({

                                        'type': 'variant',

                                        'item_id': variant.variant_id,

                                        'item_name': item.item_name,

                                        'sku': item.sku,

                                        'quantity_restored': item.quantity

                                    })

                                    restored = True

                            except GroceriesProductVariants.DoesNotExist:

                                pass

                        elif item.sku:

                            # Try to find variant by SKU

                            try:

                                variant = GroceriesProductVariants.objects.select_for_update().get(sku=item.sku)

                                if variant.stock is not None:

                                    variant.stock = (variant.stock or 0) + item.quantity

                                    variant.save(update_fields=['stock'])

                                    stock_restored.append({

                                        'type': 'variant',

                                        'item_id': variant.variant_id,

                                        'item_name': item.item_name,

                                        'sku': item.sku,

                                        'quantity_restored': item.quantity

                                    })

                                    restored = True

                            except GroceriesProductVariants.DoesNotExist:

                                pass

                        else:

                            # R01 business should not have menu items, but log if found

                            stock_restored.append({

                                'type': 'invalid_for_business_type',

                                'item_name': item.item_name,

                                'quantity_restored': 0,

                                'note': f'R01 business should not have menu items: {item.item_name}'

                            })

                    

                    else:

                        # Fallback to original logic for unknown business types

                        # Handle menu items (from MenuItems model)

                        if item.menu_item_id:

                            try:

                                menu_item = MenuItems.objects.select_for_update().get(

                                    menu_item_id=item.menu_item_id,

                                    business_id=business_id

                                )

                                if menu_item.quantity is not None:

                                    menu_item.quantity = (menu_item.quantity or 0) + item.quantity

                                    menu_item.save(update_fields=['quantity'])

                                    stock_restored.append({

                                        'type': 'menu_item',

                                        'item_id': item.menu_item_id,

                                        'item_name': item.item_name,

                                        'quantity_restored': item.quantity

                                    })

                                    restored = True

                            except MenuItems.DoesNotExist:

                                pass

                        

                        # Handle grocery variants (from GroceriesProductVariants model)

                        elif item.sku and item.sku.startswith('GR-'):

                            try:

                                variant = GroceriesProductVariants.objects.select_for_update().get(sku=item.sku)

                                if variant.stock is not None:

                                    variant.stock = (variant.stock or 0) + item.quantity

                                    variant.save(update_fields=['stock'])

                                    stock_restored.append({

                                        'type': 'variant',

                                        'item_id': variant.variant_id,

                                        'item_name': item.item_name,

                                        'sku': item.sku,

                                        'quantity_restored': item.quantity

                                    })

                                    restored = True

                            except GroceriesProductVariants.DoesNotExist:

                                pass

                        

                        # Handle product items (from ProductItems model)

                        elif item.sku and not item.sku.startswith('GR-'):

                            try:

                                product_item = ProductItems.objects.select_for_update().get(sku=item.sku)

                                if product_item.stock is not None:

                                    product_item.stock = (product_item.stock or 0) + item.quantity

                                    product_item.save(update_fields=['stock'])

                                    stock_restored.append({

                                        'type': 'product_item',

                                        'item_id': product_item.item_id,

                                        'item_name': item.item_name,

                                        'sku': item.sku,

                                        'quantity_restored': item.quantity

                                    })

                                    restored = True

                            except ProductItems.DoesNotExist:

                                pass

                    

                    if not restored:

                        stock_restored.append({

                            'type': 'unknown',

                            'item_name': item.item_name,

                            'sku': item.sku,

                            'quantity_restored': 0,

                            'note': 'Could not restore stock - item type not recognized'

                        })

                        

        except Exception as stock_error:

            # Log stock restoration error but don't fail the cancellation

            logger.error(f"Stock restoration error for order {order_id}: {str(stock_error)}")

            stock_restored.append({

                'error': f'Stock restoration failed: {str(stock_error)}'

            })

        

        if order.customer_email and order.customer_email != 'skipped':

            send_counter_order_cancel_email(order, cancellation_reason)

        

        # Create log entry

        ip_address = get_client_ip(request)

        user_agent = get_user_agent(request)

        

        create_log(

            business_id=business,  # Pass Business instance, not string

            user_id=order.user_id,

            action_type='order_cancelled',

            reference_id=str(order.order_id),

            old_data=old_data,

            new_data={

                'status': 'cancelled', 

                'cancellation_reason': cancellation_reason,

                'stock_restored': stock_restored

            },

            reason=cancellation_reason,

            description=f"Counter order #{order.token_number} cancelled and stock restored",

            ip_address=ip_address,

            user_agent=user_agent

        )

        

        return Response(

            {

                'success': True,

                'message': f'Order #{order.token_number} cancelled successfully',

                'stock_restored': stock_restored

            },

            status=status.HTTP_200_OK

        )

    

    except Exception as e:

        return Response(

            {'error': f'An error occurred: {str(e)}'},

            status=status.HTTP_500_INTERNAL_SERVER_ERROR

        )





@swagger_auto_schema(methods=['GET'], tags=['Business'])
@api_view(['GET'])
def get_counter_logs(request, business_id):

    """

    Get logs for a business

    Optional query params:

    - action_type: filter by action type

    - reference_id: filter by reference ID

    - from_date: filter logs from this date

    - to_date: filter logs to this date

    - limit: number of logs to return (default: 100)

    """

    try:

        # Validate business exists

        try:

            business = Business.objects.get(business_id=business_id)

        except Business.DoesNotExist:

            return Response(

                {'error': 'Invalid business_id'},

                status=status.HTTP_404_NOT_FOUND

            )

        

        # Get all logs for this business

        logs = BusinessCounterLogs.objects.filter(business_id=business_id)

        

        # Apply filters

        action_type = request.GET.get('action_type')

        if action_type:

            logs = logs.filter(action_type=action_type)

        

        reference_id = request.GET.get('reference_id')

        if reference_id:

            logs = logs.filter(reference_id=reference_id)

        

        from_date = request.GET.get('from_date')

        if from_date:

            logs = logs.filter(created_at__gte=from_date)

        

        to_date = request.GET.get('to_date')

        if to_date:

            logs = logs.filter(created_at__lte=to_date)

        

        # Limit results

        limit = int(request.GET.get('limit', 100))

        logs = logs[:limit]

        

        # Serialize and return

        serializer = BusinessCounterLogsSerializer(logs, many=True)

        

        return Response(

            {

                'success': True,

                'count': len(serializer.data),

                'data': serializer.data

            },

            status=status.HTTP_200_OK

        )

    

    except Exception as e:

        return Response(

            {'error': f'An error occurred: {str(e)}'},

            status=status.HTTP_500_INTERNAL_SERVER_ERROR

        )





@swagger_auto_schema(methods=['GET'], tags=['Business'])
@api_view(['GET'])
def get_payment_collections(request, business_id):

    """

    Get payment collections summary by payment method

    

    Optional query params:

    - from_date: filter from this date (YYYY-MM-DD)

    - to_date: filter to this date (YYYY-MM-DD)

    - status: filter by order status (default: 'paid')

    - order_type: filter by order type (menu/grocery/mixed)

    

    Returns:

    - Collection summary by payment method

    - Total collection amount

    - Order counts by payment method

    """

    try:

        # Validate business exists

        try:

            business = Business.objects.get(business_id=business_id)

        except Business.DoesNotExist:

            return Response(

                {'error': 'Invalid business_id'},

                status=status.HTTP_404_NOT_FOUND

            )

        

        # Get all orders for this business

        orders = BusinessCounterOrders.objects.filter(business_id=business_id)

        

        # Apply filters

        order_status = request.GET.get('status', 'paid')

        if order_status:

            orders = orders.filter(status=order_status)

        

        order_type = request.GET.get('order_type')

        if order_type:

            orders = orders.filter(order_type=order_type)

        

        from_date = request.GET.get('from_date')

        if from_date:

            orders = orders.filter(created_at__gte=from_date)

        

        to_date = request.GET.get('to_date')

        if to_date:

            # Include the entire day

            from datetime import datetime, timedelta

            try:

                to_date_obj = datetime.strptime(to_date, '%Y-%m-%d')

                to_date_end = to_date_obj + timedelta(days=1)

                orders = orders.filter(created_at__lt=to_date_end)

            except ValueError:

                orders = orders.filter(created_at__lte=to_date)

        

        # Calculate collections by payment method

        payment_methods = {}

        total_collection = Decimal('0.00')

        total_orders = 0

        

        for order in orders:

            payment_method = (order.payment_method or 'other').lower()

            amount = order.total_amount or Decimal('0.00')

            

            if payment_method not in payment_methods:

                payment_methods[payment_method] = {

                    'payment_method': payment_method,

                    'total_amount': Decimal('0.00'),

                    'order_count': 0,

                    'orders': []

                }

            

            payment_methods[payment_method]['total_amount'] += amount

            payment_methods[payment_method]['order_count'] += 1

            payment_methods[payment_method]['orders'].append({

                'order_id': order.order_id,

                'token_number': order.token_number,

                'amount': float(amount),

                'created_at': order.created_at.isoformat()

            })

            

            total_collection += amount

            total_orders += 1

        

        # Convert to list and format amounts

        collections = []

        for method, data in payment_methods.items():

            collections.append({

                'payment_method': data['payment_method'],

                'total_amount': float(data['total_amount']),

                'order_count': data['order_count'],

                'orders': data['orders']

            })

        

        # Sort by total_amount (highest first)

        collections.sort(key=lambda x: x['total_amount'], reverse=True)

        

        return Response(

            {

                'success': True,

                'business_id': business_id,

                'filters': {

                    'status': order_status,

                    'order_type': order_type or 'all',

                    'from_date': from_date or 'all',

                    'to_date': to_date or 'all'

                },

                'summary': {

                    'total_collection': float(total_collection),

                    'total_orders': total_orders,

                    'payment_methods_count': len(payment_methods)

                },

                'collections': collections

            },

            status=status.HTTP_200_OK

        )

    

    except Exception as e:

        return Response(

            {'error': f'An error occurred: {str(e)}'},

            status=status.HTTP_500_INTERNAL_SERVER_ERROR

        )





@swagger_auto_schema(methods=['GET'], tags=['Business'])
@api_view(['GET'])
def get_daily_collection_summary(request, business_id):

    """

    Get simplified daily collection summary (without order details)

    

    Optional query params:

    - date: specific date (YYYY-MM-DD), default: today

    - status: filter by order status (default: 'paid')

    

    Returns compact summary by payment method

    """

    try:

        from datetime import datetime, timedelta

        

        # Validate business exists

        try:

            business = Business.objects.get(business_id=business_id)

        except Business.DoesNotExist:

            return Response(

                {'error': 'Invalid business_id'},

                status=status.HTTP_404_NOT_FOUND

            )

        

        # Get date parameter or use today

        date_str = request.GET.get('date')

        if date_str:

            try:

                target_date = datetime.strptime(date_str, '%Y-%m-%d')

            except ValueError:

                return Response(

                    {'error': 'Invalid date format. Use YYYY-MM-DD'},

                    status=status.HTTP_400_BAD_REQUEST

                )

        else:

            target_date = datetime.now()

        

        # Set date range for the entire day

        start_date = target_date.replace(hour=0, minute=0, second=0, microsecond=0)

        end_date = start_date + timedelta(days=1)

        

        # Get orders for the date

        orders = BusinessCounterOrders.objects.filter(

            business_id=business_id,

            created_at__gte=start_date,

            created_at__lt=end_date

        )

        

        # Apply status filter

        order_status = request.GET.get('status', 'paid')

        if order_status:

            orders = orders.filter(status=order_status)

        

        # Calculate collections

        cash_total = Decimal('0.00')

        cash_count = 0

        upi_total = Decimal('0.00')

        upi_count = 0

        card_total = Decimal('0.00')

        card_count = 0

        other_total = Decimal('0.00')

        other_count = 0

        total_discount = Decimal('0.00')

        

        for order in orders:

            payment_method = (order.payment_method or 'other').lower()

            amount = order.total_amount or Decimal('0.00')

            discount = order.discount_amount or Decimal('0.00')

            

            # Add to discount total

            total_discount += discount

            

            if payment_method == 'cash':

                cash_total += amount

                cash_count += 1

            elif payment_method == 'upi':

                upi_total += amount

                upi_count += 1

            elif payment_method == 'card':

                card_total += amount

                card_count += 1

            else:

                other_total += amount

                other_count += 1

        

        total_collection = cash_total + upi_total + card_total + other_total

        total_orders = cash_count + upi_count + card_count + other_count

        

        return Response(

            {

                'success': True,

                'business_id': business_id,

                'date': start_date.strftime('%Y-%m-%d'),

                'status_filter': order_status,

                'summary': {

                    'total_collection': float(total_collection),

                    'total_orders': total_orders,

                    'total_discount': float(total_discount),

                    'gross_amount': float(total_collection + total_discount)

                },

                'by_payment_method': {

                    'cash': {

                        'total_amount': float(cash_total),

                        'order_count': cash_count,

                        'percentage': round((float(cash_total) / float(total_collection) * 100), 2) if total_collection > 0 else 0

                    },

                    'upi': {

                        'total_amount': float(upi_total),

                        'order_count': upi_count,

                        'percentage': round((float(upi_total) / float(total_collection) * 100), 2) if total_collection > 0 else 0

                    },

                    'card': {

                        'total_amount': float(card_total),

                        'order_count': card_count,

                        'percentage': round((float(card_total) / float(total_collection) * 100), 2) if total_collection > 0 else 0

                    },

                    'other': {

                        'total_amount': float(other_total),

                        'order_count': other_count,

                        'percentage': round((float(other_total) / float(total_collection) * 100), 2) if total_collection > 0 else 0

                    }

                }

            },

            status=status.HTTP_200_OK

        )

    

    except Exception as e:

        return Response(

            {'error': f'An error occurred: {str(e)}'},

            status=status.HTTP_500_INTERNAL_SERVER_ERROR

        )





@swagger_auto_schema(methods=['POST'], tags=['Business'])
@api_view(['POST'])
def apply_payment_reduction(request, business_id, order_id):

    """

    Apply payment reduction to an existing order

    

    Expected payload:

    {

        "payment_amount": 100.00,

        "payment_method": "cash",  # optional, defaults to original payment method

        "notes": "Partial payment received"  # optional

    }

    """

    try:

        # Get the order

        order = get_object_or_404(

            BusinessCounterOrders,

            order_id=order_id,

            business_id=business_id

        )

        

        # Extract payment data

        payment_amount = Decimal(str(request.data.get('payment_amount', 0)))

        payment_method = request.data.get('payment_method', order.payment_method)

        notes = request.data.get('notes', '')

        

        if payment_amount <= 0:

            return Response(

                {'error': 'Payment amount must be greater than 0'},

                status=status.HTTP_400_BAD_REQUEST

            )

        

        # Store old data for logging

        old_data = {

            'order_id': order.order_id,

            'total_amount': float(order.total_amount),

            'paid_amount': float(getattr(order, 'paid_amount', 0)),

            'remaining_amount': float(getattr(order, 'remaining_amount', order.total_amount)),

            'status': order.status

        }

        

        # Calculate new amounts

        current_paid = getattr(order, 'paid_amount', Decimal('0.00'))

        new_paid_amount = current_paid + payment_amount

        new_remaining_amount = order.total_amount - new_paid_amount

        

        # Update order with payment reduction

        with transaction.atomic():

            # Add paid_amount and remaining_amount fields if they don't exist

            if not hasattr(order, 'paid_amount'):

                # Add the fields dynamically (you might want to add these to your model)

                order.paid_amount = Decimal('0.00')

                order.remaining_amount = order.total_amount

            

            order.paid_amount = new_paid_amount

            order.remaining_amount = max(Decimal('0.00'), new_remaining_amount)

            

            # Update status based on payment

            if new_remaining_amount <= 0:

                order.status = 'paid'

            elif new_paid_amount > 0:

                order.status = 'partially_paid'

            

            # Add payment notes to remarks

            if notes:

                existing_remarks = order.remarks or ''

                payment_note = f"Payment: ₹{payment_amount} via {payment_method} - {notes}"

                order.remarks = f"{existing_remarks}\n{payment_note}".strip()

            

            order.save()

            

            # Create log entry for payment reduction

            ip_address = get_client_ip(request)

            user_agent = get_user_agent(request)

            

            new_data = {

                'order_id': order.order_id,

                'payment_amount': float(payment_amount),

                'payment_method': payment_method,

                'total_amount': float(order.total_amount),

                'paid_amount': float(order.paid_amount),

                'remaining_amount': float(order.remaining_amount),

                'status': order.status,

                'notes': notes

            }

            

            create_log(

                business_id=order.business_id,

                user_id=order.user_id,

                action_type='payment_applied',

                reference_id=str(order.order_id),

                old_data=old_data,

                new_data=new_data,

                description=f"Payment of ₹{payment_amount} applied to order #{order.token_number}",

                ip_address=ip_address,

                user_agent=user_agent

            )

            

            # Return updated order data

            response_data = {

                'order_id': order.order_id,

                'token_number': order.token_number,

                'total_amount': float(order.total_amount),

                'paid_amount': float(order.paid_amount),

                'remaining_amount': float(order.remaining_amount),

                'status': order.status,

                'payment_applied': float(payment_amount),

                'payment_method': payment_method,

                'is_fully_paid': order.remaining_amount <= 0

            }

            

            return Response(

                {

                    'success': True,

                    'message': f'Payment of ₹{payment_amount} applied successfully',

                    'data': response_data

                },

                status=status.HTTP_200_OK

            )

    

    except Exception as e:

        return Response(

            {'error': f'An error occurred: {str(e)}'},

            status=status.HTTP_500_INTERNAL_SERVER_ERROR

        )





@swagger_auto_schema(methods=['GET'], tags=['Business'])
@api_view(['GET'])
def get_collection_history(request, business_id):

    """

    Get historical collection data grouped by date and payment method.

    """

    try:

        business = get_object_or_404(Business, business_id=business_id)



        # Aggregate data from the database

        history = BusinessCounterOrders.objects.filter(

            business_id=business_id,

            status='paid'

        ).annotate(

            date=TruncDate('created_at')

        ).values('date').annotate(

            cash=Sum(Case(When(payment_method__iexact='cash', then=F('total_amount')), default=Value(Decimal('0.0'))), output_field=DecimalField()),

            upi=Sum(Case(When(payment_method__iexact='upi', then=F('total_amount')), default=Value(Decimal('0.0'))), output_field=DecimalField()),

            card=Sum(Case(When(payment_method__iexact='card', then=F('total_amount')), default=Value(Decimal('0.0'))), output_field=DecimalField()),

            total=Sum('total_amount', output_field=DecimalField())

        ).order_by('-date')



        # Format the response

        response_data = [

            {

                'date': item['date'].strftime('%Y-%m-%d'),

                'cash': float(item['cash'] or 0),

                'upi': float(item['upi'] or 0),

                'card': float(item['card'] or 0),

                'total': float(item['total'] or 0),

            }

            for item in history

        ]



        return Response({

            'success': True,

            'business_id': business_id,

            'history': response_data

        }, status=status.HTTP_200_OK)



    except Exception as e:

        return Response(

            {'error': f'An error occurred: {str(e)}'},

            status=status.HTTP_500_INTERNAL_SERVER_ERROR

        )





@swagger_auto_schema(methods=['POST'], tags=['Business'])
@api_view(['POST'])
def create_manual_log(request):

    """

    Create a manual log entry (for menu control panel changes, etc.)

    

    Expected payload:

    {

        "business_id": "KIR123...",

        "user_id": 12345,

        "action_type": "menu_item_updated",

        "reference_id": "182250",

        "old_data": {...},

        "new_data": {...},

        "description": "Updated menu item price"

    }

    """

    try:

        business_id_str = request.data.get('business_id')

        user_id_int = request.data.get('user_id')

        

        if not business_id_str or not user_id_int:

            return Response(

                {'error': 'business_id and user_id are required'},

                status=status.HTTP_400_BAD_REQUEST

            )

        

        # Validate business and user exist

        try:

            business = Business.objects.get(business_id=business_id_str)

        except Business.DoesNotExist:

            return Response(

                {'error': 'Invalid business_id'},

                status=status.HTTP_404_NOT_FOUND

            )

        

        try:

            user = Registration.objects.get(user_id=user_id_int)

        except Registration.DoesNotExist:

            return Response(

                {'error': 'Invalid user_id'},

                status=status.HTTP_404_NOT_FOUND

            )

        

        # Get client info

        ip_address = get_client_ip(request)

        user_agent = get_user_agent(request)

        

        # Create the log

        log = create_log(

            business_id=business.business_id,

            user_id=user.user_id,

            action_type=request.data.get('action_type'),

            reference_id=request.data.get('reference_id'),

            old_data=request.data.get('old_data'),

            new_data=request.data.get('new_data'),

            description=request.data.get('description'),

            ip_address=ip_address,

            user_agent=user_agent

        )

        

        if log:

            serializer = BusinessCounterLogsSerializer(log)

            return Response(

                {

                    'success': True,

                    'message': 'Log created successfully',

                    'data': serializer.data

                },

                status=status.HTTP_201_CREATED

            )

        else:

            return Response(

                {'error': 'Failed to create log'},

                status=status.HTTP_500_INTERNAL_SERVER_ERROR

            )

    

    except Exception as e:

        return Response(

            {'error': f'An error occurred: {str(e)}'},

            status=status.HTTP_500_INTERNAL_SERVER_ERROR

        )





@swagger_auto_schema(methods=['GET'], tags=['Business'])
@api_view(['GET'])
def get_pos_grocery_categories(request, business_id):

    """Get grocery categories for a given business for POS dropdowns."""

    try:

        # Validate business exists

        try:

            Business.objects.get(business_id=business_id)

        except Business.DoesNotExist:

            return Response(

                {'error': 'Invalid business_id'},

                status=status.HTTP_404_NOT_FOUND

            )



        # Primary: categories explicitly linked to this business via GroceriesCategories.business

        categories = GroceriesCategories.objects.filter(

            business_id=business_id

        ).order_by('category_name').distinct()



        # Fallback: derive categories from grocery products for this business

        if not categories.exists():

            categories = GroceriesCategories.objects.filter(

                groceriesproducts__business_id=business_id

            ).order_by('category_name').distinct()



        data = []

        for c in categories:

            try:

                gst = float(c.gst_rate) if c.gst_rate is not None else 0.0

            except Exception:

                gst = 0.0

            data.append({

                'category_id': c.category_id,

                'category_name': c.category_name,

                'gst_rate': gst,

            })



        return Response(

            {

                'success': True,

                'business_id': business_id,

                'count': len(data),

                'categories': data

            },

            status=status.HTTP_200_OK

        )

    except Exception as e:

        return Response(

            {'error': f'An error occurred: {str(e)}'},

            status=status.HTTP_500_INTERNAL_SERVER_ERROR

        )





@swagger_auto_schema(methods=['POST'], tags=['Business'])
@api_view(['POST'])
def create_counter_order_with_invoice(request):

    """

    Create a new counter order with tax invoice integration

    

    Expected payload:

    {

        "business_id": "KIR123...",

        "user_id": 12345,

        "order_type": "menu",  # or "grocery" or "mixed"

        "payment_method": "cash",  # or "card", "upi", etc.

        "delivery_charges": 50.00,  # optional delivery charges

        "discount_amount": 0.00,

        "status": "paid",  # or "pending", "cancelled"

        "customer_mobile": "9999999999",

        "customer_email": "customer@example.com",

        "remarks": "Optional remarks",

        "create_invoice": true,  # whether to create tax invoice

        "invoice_source": "POS_original_invoice",  # POS_sample_invoice, POS_original_invoice, RBO_original_invoice, RBO_sample_invoice

        "customer_details": "Customer details for invoice",  # optional

        "billing_address": "Billing address",  # optional

        "shipping_address": "Shipping address",  # optional

        "place_of_supply": "Karnataka",  # optional

        "items": [

            {

                "menu_item_id": 182250,  # or product_id for grocery

                "item_name": "Item Name",

                "sku": "item123",

                "quantity": 2,

                "unit_price": 100.00,

                "gst": 18.00,

                "is_customized": false,

                "customization_details": {},

                "notes": "Optional notes"

            }

        ]

    }

    """

    try:

        # Extract data from request

        business_id_str = request.data.get('business_id')

        user_id_int = request.data.get('user_id')

        create_invoice = request.data.get('create_invoice', False)

        invoice_source = request.data.get('invoice_source', 'POS_original_invoice')

        

        if not business_id_str or not user_id_int:

            return Response(

                {'error': 'business_id and user_id are required'},

                status=status.HTTP_400_BAD_REQUEST

            )

        

        # Validate business and user exist

        try:

            business = Business.objects.get(business_id=business_id_str)

        except Business.DoesNotExist:

            return Response(

                {'error': 'Invalid business_id'},

                status=status.HTTP_404_NOT_FOUND

            )

        

        # Business type validation

        business_type = getattr(business, 'businessType', None)

        if not business_type:

            return Response(

                {'error': 'Business type is not configured. Please contact support.'},

                status=status.HTTP_400_BAD_REQUEST

            )

        

        try:

            user = Registration.objects.get(user_id=user_id_int)

        except Registration.DoesNotExist:

            return Response(

                {'error': 'Invalid user_id'},

                status=status.HTTP_404_NOT_FOUND

            )

        

        # Extract items and calculate totals

        items_data = request.data.get('items', [])

        

        if not items_data:

            return Response(

                {'error': 'At least one item is required'},

                status=status.HTTP_400_BAD_REQUEST

            )

        

        # Calculate order totals

        subtotal = Decimal('0.00')

        gst_total = Decimal('0.00')

        

        for item in items_data:

            quantity = Decimal(str(item.get('quantity', 1)))

            unit_price = Decimal(str(item.get('unit_price', 0)))

            gst_percent = Decimal(str(item.get('gst', 0)))

            

            item_total = _q2(unit_price * quantity)

            gst_amount = _q2((item_total * gst_percent) / Decimal('100'))

            subtotal += item_total

            gst_total += gst_amount

        

        subtotal = _q2(subtotal)

        gst_total = _q2(gst_total)



        discount_amount = _q2(Decimal(str(request.data.get('discount_amount', 0))))

        discount_percentage = _q2(Decimal(str(request.data.get('discount_percentage', 0))))

        discount_type = request.data.get('discount_type', 'fixed')

        discount_reason = request.data.get('discount_reason', '')

        delivery_charges = _q2(Decimal(str(request.data.get('delivery_charges', 0))))

        total_amount = _q2(subtotal + gst_total + delivery_charges - discount_amount)

        

        # ==================== CONDITION CHECKING FUNCTIONALITY ====================

        # Handle sample invoice case - create only invoice (no order/stock changes)

        if create_invoice and invoice_source == 'POS_sample_invoice':

            return create_sample_invoice_only(request, business, user, items_data, subtotal, gst_total, total_amount, discount_amount, delivery_charges, invoice_source)

        

        # Handle original invoice case - create both order and invoice

        elif create_invoice and invoice_source == 'POS_original_invoice':

            return create_counter_order_with_invoice_helper(request, business, user, items_data, subtotal, gst_total, total_amount, discount_amount, delivery_charges, invoice_source)

        

        # Handle normal order case - create only order (no invoice)

        else:

            return create_counter_order_only(request, business, user, items_data, subtotal, gst_total, total_amount, discount_amount, delivery_charges)

    

    except Exception as e:

        return Response(

            {'error': f'An error occurred: {str(e)}'},

            status=status.HTTP_500_INTERNAL_SERVER_ERROR

        )





from django.views.decorators.csrf import csrf_exempt





@csrf_exempt
def create_sample_invoice_only(request, business, user, items_data, subtotal, gst_total, total_amount, discount_amount, delivery_charges, invoice_source):

    """Create only tax invoice (no order/stock changes)"""

    from datetime import date

    from decimal import Decimal

    import json

    

    # Prepare invoice items data

    invoice_items = []

    for item in items_data:

        invoice_items.append({

            "name": item.get('item_name', ''),

            "qty": item.get('quantity', 1),

            "rate": float(item.get('unit_price', 0)),

            "gst": float(item.get('gst', 0)),

            "hsn_sac_code": item.get('hsn_sac_code', ''),

            "discount": item.get('discount', 0),

            "taxable_value": float(item.get('unit_price', 0)) * item.get('quantity', 1)

        })



    # Generate a sample invoice number (not tied to order_id)

    today = date.today()

    now = timezone.now()

    sample_invoice_number = f"POS-SAMPLE-{today.strftime('%Y%m%d')}-{user.user_id}-{now.strftime('%H%M%S')}"



    # Prepare customer_details as string (store JSON string if object provided)

    customer_details_raw = request.data.get('customer_details', '')

    if isinstance(customer_details_raw, str):

        customer_details_str = customer_details_raw

    else:

        try:

            customer_details_str = json.dumps(customer_details_raw)

        except TypeError:

            customer_details_str = ''



    # Calculate tax breakdown (simplified - assumes intra-state)

    cgst_amount = Decimal('0.00')

    sgst_amount = Decimal('0.00')

    igst_amount = Decimal('0.00')

    cgst_amount = gst_total / 2

    sgst_amount = gst_total / 2



    # Generate amount in words

    try:

        from num2words import num2words

        amount_in_words = num2words(total_amount, to='currency', lang='en_IN').title()

    except ImportError:

        amount_in_words = f"Rupees {total_amount:.2f} Only"



    # Prepare invoice data for sample invoice

    invoice_data = {

        'business_id': business.business_id,

        'business_name': getattr(business, 'businessName', ''),

        'business_address': getattr(business, 'business_address', ''),

        'customer_details': customer_details_str,

        'invoice_number': sample_invoice_number,

        'invoice_date': today.strftime('%Y-%m-%d'),

        'due_date': request.data.get('due_date', ''),

        'billing_address': request.data.get('billing_address', ''),

        'shipping_address': request.data.get('shipping_address', ''),

        'place_of_supply': request.data.get('place_of_supply', ''),

        'items': invoice_items,

        'total_taxable_value': float(subtotal),

        'total_amount': float(total_amount),

        'reverse_charge': request.data.get('reverse_charge', 'No'),

        'state_code': request.data.get('state_code', ''),

        'cgst_amount': float(cgst_amount),

        'sgst_amount': float(sgst_amount),

        'igst_amount': float(igst_amount),

        'amount_in_words': amount_in_words,

        'declaration_text': request.data.get('declaration_text', 

            'We declare that this invoice shows the actual price of the goods/services described and that all particulars are true and correct.'),

        'source': invoice_source,

        'bank_name': request.data.get('bank_name', ''),

        'bank_account_holder': request.data.get('bank_account_holder', ''),

        'bank_account_number': request.data.get('bank_account_number', ''),

        'bank_ifsc': request.data.get('bank_ifsc', ''),

        'bank_branch': request.data.get('bank_branch', '')

    }



    invoice_serializer = BusinessTaxInvoiceSerializer(data=invoice_data)

    if invoice_serializer.is_valid():

        tax_invoice = invoice_serializer.save()

        return Response(

            {

                'success': True,

                'message': f'Sample invoice created successfully with number {tax_invoice.invoice_number}',

                'data': None,

                'invoice': BusinessTaxInvoiceSerializer(tax_invoice).data

            },

            status=status.HTTP_201_CREATED

        )

    else:

        return Response(

            {

                'error': 'Failed to create sample invoice',

                'details': invoice_serializer.errors

            },

            status=status.HTTP_400_BAD_REQUEST

        )



@csrf_exempt
def create_counter_order_only(request, business, user, items_data, subtotal, gst_total, total_amount, discount_amount, delivery_charges):

    """Create counter order only (no invoice)"""

    subtotal = _q2(subtotal)

    gst_total = _q2(gst_total)

    total_amount = _q2(total_amount)

    discount_amount = _q2(discount_amount)

    delivery_charges = _q2(delivery_charges)



    # Prepare order data

    order_data = {

        'business_id': business.business_id,

        'user_id': user.user_id,

        'username': request.data.get('username', 'skipped'),

        'order_type': request.data.get('order_type', 'menu'),

        'service_mode': request.data.get('service_mode'),

        'payment_method': request.data.get('payment_method', 'cash'),

        'subtotal': str(subtotal),

        'gst_total': str(gst_total),

        'total_amount': str(total_amount),

        'delivery_charges': str(delivery_charges),

        'discount_amount': str(discount_amount),

        'discount_percentage': str(_q2(Decimal(str(request.data.get('discount_percentage', 0))))),

        'discount_type': request.data.get('discount_type', 'fixed'),

        'discount_reason': request.data.get('discount_reason', ''),

        'status': request.data.get('status', 'pending'),

        'remarks': request.data.get('remarks', 'Counter order'),

        'customer_mobile': request.data.get('customer_mobile', 'skipped'),

        'customer_email': request.data.get('customer_email', 'skipped'),

        'offline_token_no': request.data.get('offline_token_no'),

    }

    

    # Initialize payment tracking fields

    if request.data.get('status', 'pending') == 'paid':

        order_data['paid_amount'] = str(total_amount)

        order_data['remaining_amount'] = str(Decimal('0.00'))

    else:

        order_data['paid_amount'] = str(Decimal('0.00'))

        order_data['remaining_amount'] = str(total_amount)

    

    # Use transaction to ensure atomicity

    with transaction.atomic():

        # Check stock availability and prepare stock reduction data

        # Also update items_data with correct IDs for database constraints

        stock_updates = []  # Store items that need stock reduction

        

        for idx, item in enumerate(items_data):

            menu_item_id = item.get('menu_item_id')

            product_id = item.get('product_id')

            variant_id = item.get('variant_id')

            quantity = int(item.get('quantity', 1))

            

            # Business type validation for item types

            business_type = getattr(business, 'businessType', None)

            if business_type == 'R01':

                # R01 (Grocery) businesses can only use grocery products/variants

                if menu_item_id:

                    return Response(

                        {'error': f'R01 (Grocery) businesses cannot sell menu items. Item ID {menu_item_id} is a menu item. Please use grocery products with product_id or variant_id.'},

                        status=status.HTTP_400_BAD_REQUEST

                    )

            elif business_type == 'R02':

                # R02 (Restaurant) businesses can only use menu items

                if product_id or variant_id:

                    return Response(

                        {'error': f'R02 (Restaurant) businesses can only sell menu items. Please use menu_item_id instead of product_id or variant_id.'},

                        status=status.HTTP_400_BAD_REQUEST

                    )

            

            if menu_item_id:

                # Check and reduce MenuItems quantity

                try:

                    menu_item = MenuItems.objects.select_for_update().get(item_id=menu_item_id)

                    if menu_item.quantity is not None:

                        if menu_item.quantity < quantity:

                            return Response(

                                {'error': f'Insufficient stock for {menu_item.item_name}. Available: {menu_item.quantity}, Requested: {quantity}'},

                                status=status.HTTP_400_BAD_REQUEST

                            )

                        stock_updates.append({

                            'type': 'menu_item',

                            'instance': menu_item,

                            'quantity': quantity,

                            'item_name': menu_item.item_name

                        })

                        # Ensure menu_item_id is set and product_id/variant_id are cleared

                        items_data[idx]['menu_item_id'] = menu_item_id

                        items_data[idx].pop('product_id', None)

                        items_data[idx].pop('variant_id', None)

                except MenuItems.DoesNotExist:

                    return Response(

                        {'error': f'Menu item with ID {menu_item_id} not found'},

                        status=status.HTTP_404_NOT_FOUND

                    )

            

            elif variant_id:

                # Check and reduce GroceriesProductVariants stock (for grocery items)

                try:

                    variant = GroceriesProductVariants.objects.select_for_update().get(variant_id=variant_id)

                    if variant.stock is not None:

                        if variant.stock < quantity:

                            return Response(

                                {'error': f'Insufficient stock for variant {variant.sku}. Available: {variant.stock}, Requested: {quantity}'},

                                status=status.HTTP_400_BAD_REQUEST

                            )

                        stock_updates.append({

                            'type': 'variant',

                            'instance': variant,

                            'quantity': quantity,

                            'item_name': variant.sku

                        })

                        # Set variant_id and parent product_id, clear menu_item_id

                        items_data[idx]['variant_id'] = variant_id

                        items_data[idx]['product_id'] = variant.product_id  # Set parent product_id

                        items_data[idx].pop('menu_item_id', None)

                except GroceriesProductVariants.DoesNotExist:

                    return Response(

                        {'error': f'Product variant with ID {variant_id} not found'},

                        status=status.HTTP_404_NOT_FOUND

                    )

            

            elif product_id:

                # First, try as variant_id (for grocery variants)

                variant_found = False

                try:

                    variant = GroceriesProductVariants.objects.select_for_update().get(variant_id=product_id)

                    variant_found = True

                    if variant.stock is not None:

                        if variant.stock < quantity:

                            return Response(

                                {'error': f'Insufficient stock for variant {variant.sku}. Available: {variant.stock}, Requested: {quantity}'},

                                status=status.HTTP_400_BAD_REQUEST

                            )

                        stock_updates.append({

                            'type': 'variant',

                            'instance': variant,

                            'quantity': quantity,

                            'item_name': variant.sku

                        })

                        # Update items_data: it's actually a variant, so set variant_id and parent product_id

                        items_data[idx]['variant_id'] = variant.variant_id

                        items_data[idx]['product_id'] = variant.product_id  # Set parent product_id

                        items_data[idx].pop('menu_item_id', None)

                except GroceriesProductVariants.DoesNotExist:

                    pass

                

                # If not a variant, try as GroceriesProducts product_id (for R01 grocery products)

                if not variant_found:

                    try:

                        grocery_product = GroceriesProducts.objects.select_for_update().get(product_id=product_id)

                        # For GroceriesProducts, check stock from variants

                        variants = GroceriesProductVariants.objects.filter(

                            product_id=product_id,

                            is_active=True

                        ).order_by('variant_id')

                        

                        if variants.exists():

                            # Use first variant's stock or sum all variant stocks

                            total_stock = sum(v.stock for v in variants if v.stock is not None)

                            if total_stock < quantity:

                                return Response(

                                    {'error': f'Insufficient stock for {grocery_product.product_name}. Available: {total_stock}, Requested: {quantity}'},

                                    status=status.HTTP_400_BAD_REQUEST

                                )

                            # Use first variant for stock reduction

                            variant = variants.first()

                            stock_updates.append({

                                'type': 'variant',

                                'instance': variant,

                                'quantity': quantity,

                                'item_name': grocery_product.product_name

                            })

                            # Update items_data: set variant_id and product_id

                            items_data[idx]['variant_id'] = variant.variant_id

                            items_data[idx]['product_id'] = product_id

                            items_data[idx].pop('menu_item_id', None)

                        else:

                            # No variants, but product exists - allow order (stock might be managed elsewhere)

                            stock_updates.append({

                                'type': 'grocery_product',

                                'instance': grocery_product,

                                'quantity': quantity,

                                'item_name': grocery_product.product_name

                            })

                            # Update items_data: set product_id, clear variant_id and menu_item_id

                            items_data[idx]['product_id'] = product_id

                            items_data[idx].pop('variant_id', None)

                            items_data[idx].pop('menu_item_id', None)

                    except GroceriesProducts.DoesNotExist:

                        # Finally, try as productItems (legacy/other products)

                        try:

                            product_item = productItems.objects.select_for_update().get(item_id=product_id)

                            return Response(

                                {

                                    'error': f'Product item with ID {product_id} is a legacy productItem. For R01 businesses, please use GroceriesProducts/GroceriesProductVariants. Item: {product_item.item_name}'

                                },

                                status=status.HTTP_400_BAD_REQUEST

                            )

                        except productItems.DoesNotExist:

                            return Response(

                                {'error': f'Product item with ID {product_id} not found in variants or grocery products. Please verify the item ID is correct.'},

                                status=status.HTTP_404_NOT_FOUND

                            )

        

        # Create the order using serializer (without items first)

        order_data_without_items = order_data.copy()

        order_data_without_items.pop('items', None)  # Remove items from initial order creation

        

        serializer = BusinessCounterOrdersSerializer(data=order_data_without_items)

        

        if serializer.is_valid():

            order = serializer.save()

            

            # Reduce stock/quantity for all items

            for stock_update in stock_updates:

                if stock_update['type'] == 'menu_item':

                    menu_item = stock_update['instance']

                    menu_item.quantity = (menu_item.quantity or 0) - stock_update['quantity']

                    menu_item.save(update_fields=['quantity'])

                elif stock_update['type'] == 'variant':

                    variant = stock_update['instance']

                    variant.stock = (variant.stock or 0) - stock_update['quantity']

                    variant.save(update_fields=['stock'])

                elif stock_update['type'] == 'grocery_product':

                    # For GroceriesProducts without variants, stock is managed at variant level

                    pass

                elif stock_update['type'] == 'product_item':

                    product_item = stock_update['instance']

                    product_item.stock = (product_item.stock or 0) - stock_update['quantity']

                    product_item.save(update_fields=['stock'])

            

            # Send email if needed

            if order.customer_email and order.customer_email != 'skipped':

                if send_counter_order_email(order):

                    if not order.email_sent:

                        order.email_sent = True

                        order.save(update_fields=['email_sent'])

        else:

            # Provide more detailed error information

            errors = serializer.errors

            if 'user_id' in errors:

                return Response(

                    {'error': f'Invalid user_id: {errors["user_id"]}. Please ensure the user exists in the system.'},

                    status=status.HTTP_400_BAD_REQUEST

                )

            return Response(

                {'error': serializer.errors},

                status=status.HTTP_400_BAD_REQUEST

            )

    

    # Outside the transaction - create order items and perform logging

    if order:

        # Create order items manually

        for item_data in items_data:

            menu_item_id = item_data.get('menu_item_id')

            menu_item_instance = None

            if menu_item_id:

                try:

                    menu_item_instance = MenuItems.objects.get(item_id=menu_item_id)

                except MenuItems.DoesNotExist:

                    return Response(

                        {'error': f'Menu item with ID {menu_item_id} not found'},

                        status=status.HTTP_404_NOT_FOUND

                    )

            

            BusinessCounterItems.objects.create(

                order_id=order,

                business_id=order.business_id,

                menu_item_id=menu_item_instance,

                product_id=item_data.get('product_id'),

                variant_id=item_data.get('variant_id'),

                sku=item_data.get('sku', ''),

                item_name=item_data.get('item_name', ''),

                size_label=item_data.get('size_label', ''),

                quantity=item_data.get('quantity', 1),

                unit_price=item_data.get('unit_price', 0),

                gst=item_data.get('gst', 0),

                line_total=item_data.get('line_total', 0),

                is_customized=item_data.get('is_customized', False),

                customization_details=item_data.get('customization_details', {}),

                notes=item_data.get('notes', '')

            )

        

        # Create log entry for order creation (moved outside transaction)

        ip_address = get_client_ip(request)

        user_agent = get_user_agent(request)

        

        create_log(

            business_id=business,  # Pass Business instance, not string

            user_id=user.user_id,

            action_type='order_created',

            reference_id=str(order.order_id),

            new_data={

                'order_id': order.order_id,

                'token_number': order.token_number,

                'order_type': order.order_type,

                'service_mode': order.service_mode,

                'payment_method': order.payment_method,

                'total_amount': float(order.total_amount),

                'delivery_charges': float(order.delivery_charges or 0),

                'status': order.status,

                'items_count': len(items_data),

                'stock_reduced': True,

                'invoice_created': False,

                'invoice_id': None,

                'invoice_source': None

            },

            description=f"Counter order created with token #{order.token_number} and stock reduced",

            ip_address=ip_address,

            user_agent=user_agent

        )

        

        # Return the created order

        response_serializer = BusinessCounterOrdersSerializer(order)

        return Response(

            {

                'success': True,

                'message': f'Order created successfully with token #{order.token_number}',

                'data': response_serializer.data,

                'invoice': None

            },

            status=status.HTTP_201_CREATED

        )



@csrf_exempt
def create_counter_order_with_invoice_helper(request, business, user, items_data, subtotal, gst_total, total_amount, discount_amount, delivery_charges, invoice_source):

    """Create counter order with tax invoice integration"""

    from datetime import date

    import json



    subtotal = _q2(subtotal)

    gst_total = _q2(gst_total)

    total_amount = _q2(total_amount)

    discount_amount = _q2(discount_amount)

    delivery_charges = _q2(delivery_charges)

    

    # Prepare order data

    order_data = {

        'business_id': business.business_id,

        'user_id': user.user_id,

        'username': request.data.get('username', 'skipped'),

        'order_type': request.data.get('order_type', 'menu'),

        'service_mode': request.data.get('service_mode'),

        'payment_method': request.data.get('payment_method', 'cash'),

        'subtotal': str(subtotal),

        'gst_total': str(gst_total),

        'total_amount': str(total_amount),

        'delivery_charges': str(delivery_charges),

        'discount_amount': str(discount_amount),

        'discount_percentage': str(_q2(Decimal(str(request.data.get('discount_percentage', 0))))),

        'discount_type': request.data.get('discount_type', 'fixed'),

        'discount_reason': request.data.get('discount_reason', ''),

        'status': request.data.get('status', 'pending'),

        'remarks': request.data.get('remarks', 'Counter order with invoice'),

        'customer_mobile': request.data.get('customer_mobile', 'skipped'),

        'customer_email': request.data.get('customer_email', 'skipped'),

        'offline_token_no': request.data.get('offline_token_no'),

    }

    

    # Initialize payment tracking fields

    if request.data.get('status', 'pending') == 'paid':

        order_data['paid_amount'] = str(total_amount)

        order_data['remaining_amount'] = str(Decimal('0.00'))

    else:

        order_data['paid_amount'] = str(Decimal('0.00'))

        order_data['remaining_amount'] = str(total_amount)

    

    # Use transaction to ensure atomicity

    with transaction.atomic():

        # Check stock availability and prepare stock reduction data

        # Also update items_data with correct IDs for database constraints

        stock_updates = []  # Store items that need stock reduction

        

        for idx, item in enumerate(items_data):

            menu_item_id = item.get('menu_item_id')

            product_id = item.get('product_id')

            variant_id = item.get('variant_id')

            quantity = int(item.get('quantity', 1))

            

            # Business type validation for item types

            business_type = getattr(business, 'businessType', None)

            if business_type == 'R01':

                # R01 (Grocery) businesses can only use grocery products/variants

                if menu_item_id:

                    return Response(

                        {'error': f'R01 (Grocery) businesses cannot sell menu items. Item ID {menu_item_id} is a menu item. Please use grocery products with product_id or variant_id.'},

                        status=status.HTTP_400_BAD_REQUEST

                    )

            elif business_type == 'R02':

                # R02 (Restaurant) businesses can only use menu items

                if product_id or variant_id:

                    return Response(

                        {'error': f'R02 (Restaurant) businesses can only sell menu items. Please use menu_item_id instead of product_id or variant_id.'},

                        status=status.HTTP_400_BAD_REQUEST

                    )

            

            if menu_item_id:

                # Check and reduce MenuItems quantity

                try:

                    menu_item = MenuItems.objects.select_for_update().get(item_id=menu_item_id)

                    if menu_item.quantity is not None:

                        if menu_item.quantity < quantity:

                            return Response(

                                {'error': f'Insufficient stock for {menu_item.item_name}. Available: {menu_item.quantity}, Requested: {quantity}'},

                                status=status.HTTP_400_BAD_REQUEST

                            )

                        stock_updates.append({

                            'type': 'menu_item',

                            'instance': menu_item,

                            'quantity': quantity,

                            'item_name': menu_item.item_name

                        })

                        # Ensure menu_item_id is set and product_id/variant_id are cleared

                        items_data[idx]['menu_item_id'] = menu_item_id

                        items_data[idx].pop('product_id', None)

                        items_data[idx].pop('variant_id', None)

                except MenuItems.DoesNotExist:

                    return Response(

                        {'error': f'Menu item with ID {menu_item_id} not found'},

                        status=status.HTTP_404_NOT_FOUND

                    )

            

            elif variant_id:

                # Check and reduce GroceriesProductVariants stock (for grocery items)

                try:

                    variant = GroceriesProductVariants.objects.select_for_update().get(variant_id=variant_id)

                    if variant.stock is not None:

                        if variant.stock < quantity:

                            return Response(

                                {'error': f'Insufficient stock for variant {variant.sku}. Available: {variant.stock}, Requested: {quantity}'},

                                status=status.HTTP_400_BAD_REQUEST

                            )

                        stock_updates.append({

                            'type': 'variant',

                            'instance': variant,

                            'quantity': quantity,

                            'item_name': variant.sku

                        })

                        # Set variant_id and parent product_id, clear menu_item_id

                        items_data[idx]['variant_id'] = variant_id

                        items_data[idx]['product_id'] = variant.product_id  # Set parent product_id

                        items_data[idx].pop('menu_item_id', None)

                except GroceriesProductVariants.DoesNotExist:

                    return Response(

                        {'error': f'Product variant with ID {variant_id} not found'},

                        status=status.HTTP_404_NOT_FOUND

                    )

            

            elif product_id:

                # First, try as variant_id (for grocery variants)

                variant_found = False

                try:

                    variant = GroceriesProductVariants.objects.select_for_update().get(variant_id=product_id)

                    variant_found = True

                    if variant.stock is not None:

                        if variant.stock < quantity:

                            return Response(

                                {'error': f'Insufficient stock for variant {variant.sku}. Available: {variant.stock}, Requested: {quantity}'},

                                status=status.HTTP_400_BAD_REQUEST

                            )

                        stock_updates.append({

                            'type': 'variant',

                            'instance': variant,

                            'quantity': quantity,

                            'item_name': variant.sku

                        })

                        # Update items_data: it's actually a variant, so set variant_id and parent product_id

                        items_data[idx]['variant_id'] = variant.variant_id

                        items_data[idx]['product_id'] = variant.product_id  # Set parent product_id

                        items_data[idx].pop('menu_item_id', None)

                except GroceriesProductVariants.DoesNotExist:

                    pass

                

                # If not a variant, try as GroceriesProducts product_id (for R01 grocery products)

                if not variant_found:

                    try:

                        grocery_product = GroceriesProducts.objects.select_for_update().get(product_id=product_id)

                        # For GroceriesProducts, check stock from variants

                        variants = GroceriesProductVariants.objects.filter(

                            product_id=product_id,

                            is_active=True

                        ).order_by('variant_id')

                        

                        if variants.exists():

                            # Use first variant's stock or sum all variant stocks

                            total_stock = sum(v.stock for v in variants if v.stock is not None)

                            if total_stock < quantity:

                                return Response(

                                    {'error': f'Insufficient stock for {grocery_product.product_name}. Available: {total_stock}, Requested: {quantity}'},

                                    status=status.HTTP_400_BAD_REQUEST

                                )

                            # Use first variant for stock reduction

                            variant = variants.first()

                            stock_updates.append({

                                'type': 'variant',

                                'instance': variant,

                                'quantity': quantity,

                                'item_name': grocery_product.product_name

                            })

                            # Update items_data: set variant_id and product_id

                            items_data[idx]['variant_id'] = variant.variant_id

                            items_data[idx]['product_id'] = product_id

                            items_data[idx].pop('menu_item_id', None)

                        else:

                            # No variants, but product exists - allow order (stock might be managed elsewhere)

                            stock_updates.append({

                                'type': 'grocery_product',

                                'instance': grocery_product,

                                'quantity': quantity,

                                'item_name': grocery_product.product_name

                            })

                            # Update items_data: set product_id, clear variant_id and menu_item_id

                            items_data[idx]['product_id'] = product_id

                            items_data[idx].pop('variant_id', None)

                            items_data[idx].pop('menu_item_id', None)

                    except GroceriesProducts.DoesNotExist:

                        # Finally, try as productItems (legacy/other products)

                        try:

                            product_item = productItems.objects.select_for_update().get(item_id=product_id)

                            return Response(

                                {

                                    'error': f'Product item with ID {product_id} is a legacy productItem. For R01 businesses, please use GroceriesProducts/GroceriesProductVariants. Item: {product_item.item_name}'

                                },

                                status=status.HTTP_400_BAD_REQUEST

                            )

                        except productItems.DoesNotExist:

                            return Response(

                                {'error': f'Product item with ID {product_id} not found in variants or grocery products. Please verify the item ID is correct.'},

                                status=status.HTTP_404_NOT_FOUND

                            )

        

        # Create the order using serializer (without items first)

        order_data_without_items = order_data.copy()

        order_data_without_items.pop('items', None)  # Remove items from initial order creation

        

        serializer = BusinessCounterOrdersSerializer(data=order_data_without_items)

        

        if serializer.is_valid():

            order = serializer.save()

            

            # Reduce stock/quantity for all items

            for stock_update in stock_updates:

                if stock_update['type'] == 'menu_item':

                    menu_item = stock_update['instance']

                    menu_item.quantity = (menu_item.quantity or 0) - stock_update['quantity']

                    menu_item.save(update_fields=['quantity'])

                elif stock_update['type'] == 'variant':

                    variant = stock_update['instance']

                    variant.stock = (variant.stock or 0) - stock_update['quantity']

                    variant.save(update_fields=['stock'])

                elif stock_update['type'] == 'grocery_product':

                    # For GroceriesProducts without variants, stock is managed at variant level

                    pass

                elif stock_update['type'] == 'product_item':

                    product_item = stock_update['instance']

                    product_item.stock = (product_item.stock or 0) - stock_update['quantity']

                    product_item.save(update_fields=['stock'])

            

            # Create tax invoice

            tax_invoice = None

            # Prepare invoice items data

            invoice_items = []

            for item in items_data:

                invoice_items.append({

                    "name": item.get('item_name', ''),

                    "qty": item.get('quantity', 1),

                    "rate": float(item.get('unit_price', 0)),

                    "gst": float(item.get('gst', 0)),

                    "hsn_sac_code": item.get('hsn_sac_code', ''),

                    "discount": item.get('discount', 0),

                    "taxable_value": float(item.get('unit_price', 0)) * item.get('quantity', 1)

                })

            

            # Generate invoice number

            today = date.today()

            invoice_number = f"POS-{today.strftime('%Y%m%d')}-{order.order_id}"

            

            # Prepare customer_details as string (store JSON string if object provided)

            customer_details_raw = request.data.get('customer_details', '')

            if isinstance(customer_details_raw, str):

                customer_details_str = customer_details_raw

            else:

                try:

                    customer_details_str = json.dumps(customer_details_raw)

                except TypeError:

                    customer_details_str = ''

            

            # Calculate tax breakdown (simplified - assumes intra-state for now)

            cgst_amount = Decimal('0.00')

            sgst_amount = Decimal('0.00')

            igst_amount = Decimal('0.00')

            cgst_amount = gst_total / 2

            sgst_amount = gst_total / 2

            

            # Generate amount in words (basic implementation)

            try:

                from num2words import num2words

                amount_in_words = num2words(total_amount, to='currency', lang='en_IN').title()

            except ImportError:

                amount_in_words = f"Rupees {total_amount:.2f} Only"

            

            # Prepare invoice data

            invoice_data = {

                'business_id': business.business_id,

                'business_name': getattr(business, 'businessName', ''),

                'business_address': getattr(business, 'business_address', ''),

                'customer_details': customer_details_str,

                'invoice_number': invoice_number,

                'invoice_date': today.strftime('%Y-%m-%d'),

                'due_date': request.data.get('due_date', ''),

                'billing_address': request.data.get('billing_address', ''),

                'shipping_address': request.data.get('shipping_address', ''),

                'place_of_supply': request.data.get('place_of_supply', ''),

                'items': invoice_items,

                'total_taxable_value': float(subtotal),

                'total_amount': float(total_amount),

                'reverse_charge': request.data.get('reverse_charge', 'No'),

                'state_code': request.data.get('state_code', ''),

                'cgst_amount': float(cgst_amount),

                'sgst_amount': float(sgst_amount),

                'igst_amount': float(igst_amount),

                'amount_in_words': amount_in_words,

                'declaration_text': request.data.get('declaration_text', 

                    'We declare that this invoice shows the actual price of the goods/services described and that all particulars are true and correct.'),

                'source': invoice_source,

                'bank_name': request.data.get('bank_name', ''),

                'bank_account_holder': request.data.get('bank_account_holder', ''),

                'bank_account_number': request.data.get('bank_account_number', ''),

                'bank_ifsc': request.data.get('bank_ifsc', ''),

                'bank_branch': request.data.get('bank_branch', '')

            }

            

            # Create tax invoice

            invoice_serializer = BusinessTaxInvoiceSerializer(data=invoice_data)

            if invoice_serializer.is_valid():

                tax_invoice = invoice_serializer.save()

                # Update order with invoice_id

                order.invoice_id = tax_invoice.invoice_id

                order.save(update_fields=['invoice_id'])

            else:

                # Log error but don't fail order creation

                print(f"Error creating tax invoice: {invoice_serializer.errors}")

            

            # Send email if needed

            if order.customer_email and order.customer_email != 'skipped':

                if send_counter_order_email(order):

                    if not order.email_sent:

                        order.email_sent = True

                        order.save(update_fields=['email_sent'])

        else:

            # Provide more detailed error information

            errors = serializer.errors

            if 'user_id' in errors:

                return Response(

                    {'error': f'Invalid user_id: {errors["user_id"]}. Please ensure the user exists in the system.'},

                    status=status.HTTP_400_BAD_REQUEST

                )

            return Response(

                {'error': serializer.errors},

                status=status.HTTP_400_BAD_REQUEST

            )

    

    # Outside the transaction - create order items and perform logging

    if order:

        # Create order items manually

        for item_data in items_data:

            menu_item_id = item_data.get('menu_item_id')

            menu_item_instance = None

            if menu_item_id:

                try:

                    menu_item_instance = MenuItems.objects.get(item_id=menu_item_id)

                except MenuItems.DoesNotExist:

                    return Response(

                        {'error': f'Menu item with ID {menu_item_id} not found'},

                        status=status.HTTP_404_NOT_FOUND

                    )

            

            BusinessCounterItems.objects.create(

                order_id=order,

                business_id=order.business_id,

                menu_item_id=menu_item_instance,

                product_id=item_data.get('product_id'),

                variant_id=item_data.get('variant_id'),

                sku=item_data.get('sku', ''),

                item_name=item_data.get('item_name', ''),

                size_label=item_data.get('size_label', ''),

                quantity=item_data.get('quantity', 1),

                unit_price=item_data.get('unit_price', 0),

                gst=item_data.get('gst', 0),

                line_total=item_data.get('line_total', 0),

                is_customized=item_data.get('is_customized', False),

                customization_details=item_data.get('customization_details', {}),

                notes=item_data.get('notes', '')

            )

        

        # Create log entry for order creation (moved outside transaction)

        ip_address = get_client_ip(request)

        user_agent = get_user_agent(request)

        

        create_log(

            business_id=business,  # Pass Business instance, not string

            user_id=user.user_id,

            action_type='order_created_with_invoice',

            reference_id=str(order.order_id),

            new_data={

                'order_id': order.order_id,

                'token_number': order.token_number,

                'order_type': order.order_type,

                'service_mode': order.service_mode,

                'payment_method': order.payment_method,

                'total_amount': float(order.total_amount),

                'delivery_charges': float(order.delivery_charges or 0),

                'status': order.status,

                'items_count': len(items_data),

                'stock_reduced': True,

                'invoice_created': tax_invoice is not None,

                'invoice_id': tax_invoice.invoice_id if tax_invoice else None,

                'invoice_source': invoice_source if tax_invoice else None

            },

            description=f"Counter order created with token #{order.token_number}, stock reduced, and invoice created" if tax_invoice else f"Counter order created with token #{order.token_number} and stock reduced",

            ip_address=ip_address,

            user_agent=user_agent

        )

        

        # Return the created order

        response_serializer = BusinessCounterOrdersSerializer(order)

        return Response(

            {

                'success': True,

                'message': f'Order created successfully with token #{order.token_number}' + (f' and invoice #{tax_invoice.invoice_number}' if tax_invoice else ''),

                'data': response_serializer.data,

                'invoice': BusinessTaxInvoiceSerializer(tax_invoice).data if tax_invoice else None

            },

            status=status.HTTP_201_CREATED

        )



