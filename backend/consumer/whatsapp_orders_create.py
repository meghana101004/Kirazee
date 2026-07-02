from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework import status
from django.db import transaction, models
from django.utils import timezone
from django.conf import settings
from drf_yasg.utils import swagger_auto_schema
from datetime import datetime
from decimal import Decimal
from kirazee_app.models import Registration, Business, UserAddress, generate_user_id
from .models import Orders, OrderItems, Payments
from .serializers_whatsapp_orders import WhatsAppOrderCreateSerializer, WhatsAppItemSearchSerializer
from business.models import MenuItems, productItems
from .gro_models import GroceriesProducts, GroceriesProductVariants
import logging

logger = logging.getLogger(__name__)


@swagger_auto_schema(methods=['POST'],tags=['Consumer'])
@api_view(['POST'])
def create_whatsapp_order(request, business_id):
    ser = WhatsAppOrderCreateSerializer(data=request.data)
    if not ser.is_valid():
        return Response({'success': False, 'errors': ser.errors}, status=status.HTTP_400_BAD_REQUEST)

    data = ser.validated_data
    customer = data['customer']
    items = data['items']

    try:
        business = Business.objects.filter(business_id=business_id).first()
        if not business:
            return Response({'success': False, 'error': 'Invalid business_id'}, status=status.HTTP_400_BAD_REQUEST)

        with transaction.atomic():
            mobile = customer['mobileNumber']
            email = customer['emailID']

            user = Registration.objects.filter(mobileNumber=mobile).first()
            if not user:
                user = Registration.objects.filter(emailID=email).first()

            if user:
                user.firstName = customer['firstName']
                user.lastName = customer.get('lastName') or ''
                user.countryCode = customer['countryCode']
                if email and not Registration.objects.filter(emailID=email).exclude(pk=user.pk).exists():
                    user.emailID = email
                if mobile and not Registration.objects.filter(mobileNumber=mobile).exclude(pk=user.pk).exists():
                    user.mobileNumber = mobile
                user.is_verified = True
                user.is_active = True
                user.save()
            else:
                user = Registration.objects.create(
                    user_id=generate_user_id(),
                    firstName=customer['firstName'],
                    lastName=customer.get('lastName') or '',
                    countryCode=customer['countryCode'],
                    mobileNumber=mobile,
                    emailID=email,
                    is_verified=True,
                    is_active=True,
                )

            address_obj = None
            delivery_address_input = data.get('delivery_address')
            if delivery_address_input:
                # Check if address has meaningful data (not just empty fields)
                address_data = delivery_address_input
                has_address_data = False
                
                if isinstance(address_data, dict):
                    # Check if any address field has meaningful content
                    address_fields = ['state', 'street', 'Door no', 'door_no', 'country', 'pincode', 'city/town', 'city']
                    has_address_data = any(address_data.get(field, '').strip() for field in address_fields)
                elif isinstance(address_data, str) and address_data.strip():
                    has_address_data = True
                
                if has_address_data:
                    # Create UserAddress entry for this delivery address
                    address_obj = UserAddress.objects.create(
                        user=user,
                        address_type='other',
                        tag='WhatsApp Order',
                        is_default=False,
                        address=delivery_address_input,
                        status=True
                    )

            subtotal = Decimal('0.00')
            gst_total = Decimal('0.00')
            for it in items:
                qty = int(it.get('quantity') or 1)
                unit = Decimal(str(it.get('unit_price') or '0.00'))

                
                menu_id_in = it.get('menu_item_id')
                prod_id_in = it.get('product_item_id')
                gst_rate = Decimal('0.00')
                try:
                    if menu_id_in:
                        m = (MenuItems.objects
                             .filter(item_id=menu_id_in)
                             .values('gst', 'selling_price')
                             .first())
                        if m:
                            
                            provided_unit = Decimal(str(it.get('unit_price') or '0.00'))
                            if provided_unit == Decimal('0.00') and m.get('selling_price') is not None:
                                unit = Decimal(str(m['selling_price']))
                            gst_rate = Decimal(str(m.get('gst') if m.get('gst') is not None else '0.00'))
                    elif prod_id_in:
                        
                        var = (GroceriesProductVariants.objects
                               .filter(variant_id=prod_id_in)
                               .select_related('product__category')
                               .values('selling_price', 'product__category__gst_rate')
                               .first())
                        if var:
                            provided_unit = Decimal(str(it.get('unit_price') or '0.00'))
                            if provided_unit == Decimal('0.00') and var.get('selling_price') is not None:
                                unit = Decimal(str(var['selling_price']))
                            gst_rate = Decimal(str(var.get('product__category__gst_rate') or '0.00'))
                        else:
                            
                            prod = (GroceriesProducts.objects
                                    .filter(product_id=prod_id_in)
                                    .select_related('category')
                                    .values('category__gst_rate')
                                    .first())
                            if prod:
                                gst_rate = Decimal(str(prod.get('category__gst_rate') or '0.00'))
                except Exception:
                    gst_rate = Decimal('0.00')

                
                subtotal += unit * qty
                per_unit_gst = (unit * gst_rate / Decimal('100')).quantize(Decimal('0.01'))
                gst_total += per_unit_gst * qty

            discount = Decimal(str(data.get('discount_amount') or '0.00'))
            deliv = Decimal(str(data.get('delivery_charges') or '0.00'))
            parcel = Decimal(str(data.get('parcel_charges') or '0.00'))

            total_amount = Decimal(str(data.get('total_amount'))) if data.get('total_amount') is not None else subtotal
            computed_final = (total_amount - discount + deliv + parcel + gst_total)
            
            final_amount = computed_final

            if getattr(settings, 'USE_TZ', False):
                today_start = timezone.now().replace(hour=0, minute=0, second=0, microsecond=0)
            else:
                today_start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)

            last_order_for_token = (
                Orders.objects
                .select_for_update()
                .filter(
                    business_id=business,
                    token_num__isnull=False,
                    created_at__gte=today_start
                )
                .order_by('-token_num')
                .first()
            )

            if last_order_for_token and last_order_for_token.token_num:
                next_token_num = last_order_for_token.token_num + 1
            else:
                next_token_num = 101

            existing_token_today = Orders.objects.filter(
                business_id=business,
                token_num=next_token_num,
                created_at__gte=today_start
            ).exists()

            if existing_token_today:
                max_token_today = Orders.objects.filter(
                    business_id=business,
                    token_num__isnull=False,
                    created_at__gte=today_start
                ).aggregate(models.Max('token_num'))['token_num__max']

                if max_token_today:
                    next_token_num = max_token_today + 1
                else:
                    next_token_num = 101

            order = Orders.objects.create(
                user_id=user,
                business_id=business,
                order_type=data['order_type'],
                status=Orders.OrderStatus.PENDING,
                token_num=next_token_num,
                total_amount=total_amount,
                discount_amount=discount,
                delivery_charges=deliv,
                parcel_charges=parcel,
                final_amount=final_amount,
                coupon_code=(data.get('coupon_code') or '').strip() or None,
                delivery_address=address_obj,
            )

            if address_obj:
                try:
                    snapshot = order._create_address_snapshot(address_obj)
                    order.delivery_address_snapshot = snapshot
                    order.save(update_fields=['delivery_address_snapshot'])
                except Exception:
                    pass

            business_type = getattr(business, 'businessType', None)
            for it in items:
                qty = int(it.get('quantity') or 1)
                unit = Decimal(str(it.get('unit_price') or '0.00'))
                menu_id_in = it.get('menu_item_id')
                prod_id_in = it.get('product_item_id')

                if menu_id_in:
                    mi = MenuItems.objects.select_for_update().get(item_id=menu_id_in)
                    if mi.quantity is not None:
                        if mi.quantity < qty:
                            return Response({'success': False, 'error': f'Insufficient stock for {mi.item_name}'}, status=status.HTTP_400_BAD_REQUEST)
                        mi.quantity = mi.quantity - qty
                        mi.save(update_fields=['quantity'])
                elif prod_id_in:
                    if business_type == 'R01':
                        try:
                            var = GroceriesProductVariants.objects.select_for_update().get(variant_id=prod_id_in)
                        except GroceriesProductVariants.DoesNotExist:
                            return Response({'success': False, 'error': 'Grocery variant not found for stock update'}, status=status.HTTP_400_BAD_REQUEST)
                        if var.stock is not None:
                            if var.stock < qty:
                                return Response({'success': False, 'error': f'Insufficient stock for {var.sku}'}, status=status.HTTP_400_BAD_REQUEST)
                            var.stock = var.stock - qty
                            var.save(update_fields=['stock'])
                    elif business_type == 'R02':
                        pi = productItems.objects.select_for_update().get(item_id=prod_id_in)
                        if pi.stock is not None:
                            if pi.stock < qty:
                                return Response({'success': False, 'error': f'Insufficient stock for {pi.item_name}'}, status=status.HTTP_400_BAD_REQUEST)
                            pi.stock = pi.stock - qty
                            pi.save(update_fields=['stock'])

                OrderItems.objects.create(
                    order_id=order,
                    menu_item_id=menu_id_in if menu_id_in else None,
                    product_item_id=prod_id_in if prod_id_in else None,
                    item_name_snapshot=it.get('item_name') or '',
                    quantity=qty,
                    unit_price_snapshot=unit,
                    item_details_snapshot={
                        'type': 'manual',
                        'source': 'whatsapp',
                        'item_name': it.get('item_name') or '',
                        'menu_item_id': menu_id_in,
                        'product_item_id': prod_id_in,
                    },
                    customizations=it.get('customizations') or [],
                )

            try:
                Payments.objects.create(
                    user=user,
                    business=business,
                    amount=order.final_amount,
                    payment_method=Payments.Method.COD,
                    status=Payments.Status.COD,
                    order_id=order.order_id,
                    payment_source='whatsapp_order'
                )
            except Exception as e:
                logger.error(f"Failed to create COD payment for WhatsApp order {order.order_id}: {e}")

        return Response({
            'success': True,
            'message': 'Order created',
            'order_id': order.order_id,
            'order_number': str(order.order_number),
            'token_num': order.token_num,
            'user_id': user.user_id,
        }, status=status.HTTP_201_CREATED)

    except Exception as e:
        return Response({'success': False, 'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@swagger_auto_schema(methods=['GET'],tags=['Consumer'])
@api_view(['GET'])
def search_whatsapp_items(request, business_id):
    """
    Search items by name for a given business across:
    - MenuItems (restaurant)
    - Groceries_Products (grocery products)
    - Groceries_ProductVariants_1 (grocery variants)
    Returns a flat list with type and ids.
    """
    serializer = WhatsAppItemSearchSerializer(data=request.query_params)
    if not serializer.is_valid():
        return Response({'success': False, 'errors': serializer.errors}, status=status.HTTP_400_BAD_REQUEST)

    q = serializer.validated_data['q']
    limit = serializer.validated_data['limit']
    q_str = str(q).strip()

    try:
        # Resolve business list: always include sub-level businesses of the given business_id
        try:
            Business.objects.get(business_id=business_id)
        except Business.DoesNotExist:
            return Response({'success': False, 'error': 'Business not found'}, status=status.HTTP_404_NOT_FOUND)

        business_ids = [business_id]
        sub_businesses = Business.objects.filter(master=business_id).values_list('business_id', flat=True)
        business_ids.extend(list(sub_businesses))

        results = []

        # Menu items
        menu_qs = (MenuItems.objects
                   .filter(business_id__business_id__in=business_ids, status=True, is_active=True, item_name__icontains=q_str)
                   .values('item_id', 'item_name', 'item_category', 'selling_price')
                   .order_by('item_name')[:limit])
        for r in menu_qs:
            results.append({
                'type': 'menu',
                'item_id': int(r['item_id']),
                'name': r['item_name'] or '',
                'category': r.get('item_category') or None,
                'selling_price': float(r['selling_price']) if r.get('selling_price') is not None else None,
            })

        # Grocery products (annotate with min active variant price as selling_price)
        prod_qs = (GroceriesProducts.objects
                   .filter(business__business_id__in=business_ids, product_name__icontains=q_str)
                   .annotate(min_price=models.Min('groceriesproductvariants__selling_price'))
                   .values('product_id', 'product_name', 'category__category_name', 'min_price')
                   .order_by('product_name')[:limit])
        for r in prod_qs:
            results.append({
                'type': 'grocery_product',
                'product_id': int(r['product_id']),
                'name': r['product_name'] or '',
                'category': r.get('category__category_name') or None,
                'selling_price': float(r['min_price']) if r.get('min_price') is not None else None,
            })

        # Grocery variants (include product context)
        # Build variant search across product name, SKU, size, and numeric net_weight
        variant_text_q = (
            models.Q(product__product_name__icontains=q_str) |
            models.Q(sku__icontains=q_str) |
            models.Q(size__icontains=q_str)
        )
        if q_str.isdigit():
            try:
                variant_text_q = variant_text_q | models.Q(net_weight=int(q_str))
            except Exception:
                pass

        var_qs = (GroceriesProductVariants.objects
                  .filter(
                      models.Q(product__business__business_id__in=business_ids) & variant_text_q
                  )
                  .select_related('product')
                  .values('variant_id', 'product_id', 'product__product_name', 'product__category__category_name', 'sku', 'size', 'net_weight', 'net_weight_unit', 'selling_price')
                  .order_by('product__product_name', 'variant_id')[:limit])
        for r in var_qs:
            # Build a friendly label
            parts = [r.get('product__product_name') or '']
            sku = r.get('sku')
            size = r.get('size')
            nw = r.get('net_weight')
            nwu = r.get('net_weight_unit')
            if size:
                parts.append(str(size))
            elif nw and nwu:
                parts.append(f"{nw}{nwu}")
            elif sku:
                parts.append(str(sku))
            name = ' - '.join([p for p in parts if p])

            results.append({
                'type': 'grocery_variant',
                'variant_id': int(r['variant_id']),
                'product_id': int(r['product_id']),
                'name': name,
                'category': r.get('product__category__category_name') or None,
                'selling_price': float(r['selling_price']) if r.get('selling_price') is not None else None,
            })

        # Sort and clamp overall results by name
        results.sort(key=lambda x: (x.get('name') or '').lower())
        if len(results) > limit:
            results = results[:limit]

        return Response({'success': True, 'results': results, 'count': len(results)}, status=status.HTTP_200_OK)
    except Exception as e:
        return Response({'success': False, 'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@swagger_auto_schema(methods=['GET'],tags=['Consumer'])
@api_view(['GET'])
def get_user_by_mobile(request):
    mobile = request.query_params.get('mobile') or request.query_params.get('mobileNumber')
    if not mobile:
        return Response({'success': False, 'error': 'mobile is required'}, status=status.HTTP_400_BAD_REQUEST)

    user = (Registration.objects
            .filter(mobileNumber=mobile)
            .values(
                'user_id', 'firstName', 'lastName', 'countryCode', 'mobileNumber', 'emailID', 'dob',
                'is_verified', 'is_active', 'user_mode', 'profileUrl', 'tokenID', 'uuid', 'os',
                'status', 'whichapp', 'created_at', 'updated_at'
            )
            .first())

    if not user:
        return Response({'success': False, 'error': 'User not found'}, status=status.HTTP_404_NOT_FOUND)

    # Fetch user's addresses (linked via Registration.user_id)
    try:
        addresses = list(
            UserAddress.objects
            .filter(user__user_id=user['user_id'], status=True)
            .values('id', 'address_type', 'tag', 'is_default', 'address', 'status', 'created_at', 'updated_at')
            .order_by('-is_default', '-updated_at')
        )
    except Exception:
        addresses = []

    return Response({'success': True, 'user': user, 'addresses': addresses}, status=status.HTTP_200_OK)
