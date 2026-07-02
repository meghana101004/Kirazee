from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.decorators import api_view
from rest_framework import status
from django.db import connection
from django.db.models import F, Q
from django.shortcuts import get_object_or_404
from drf_yasg.utils import swagger_auto_schema
from drf_yasg import openapi
from .gro_models import GroceriesCategories, GroceriesProducts, GroceriesProductVariants, GroceryPartner, GroceryDeliverDetails, GroceriesOrders, GroceriesRatingHistory, BusinessFeedback
from .gro_serializers import (
    GroceriesCategoriesSerializer,
    GroceriesProductsSerializer,
    GroceriesProductVariantsSerializer,
    GroceriesProductWithPricingSerializer,
    GroceriesCartSerializer,
    GroceriesOrdersSerializer, 
    GroceriesOrderItemsSerializer,
    CreateOrderSerializer,
    OrderItemRequestSerializer,
    GroceriesPaymentsSerializer,
    GroceryPartnerSerializer, 
    GroceryPartnerRegistrationSerializer,
    GroceryDeliverDetailsSerializer, 
    AssignOrderToPartnerSerializer,
    BusinessOrdersSerializer, 
    UpdateOrderStatusSerializer, 
    VerifyDeliveryOTPSerializer,
    DeliveryPartnerDetailsSerializer,
    RazorpayPaymentVerificationSerializer,
    CancelPaymentSerializer,
    CreateOrderSerializer,
    GeneratePickupOTPSerializer,
    VerifyPickupOTPSerializer,
    BulkGroceriesUploadSerializer,
    ServiceAvailabilitySerializer,
    ServiceAvailabilityUpdateSerializer,
    GroceriesRatingHistorySerializer,
    CreateRatingHistorySerializer,
    BusinessFeedbackSerializer,
    BusinessFeedbackCreateSerializer,
)
from .gro_models import GroceriesCart, GroceriesOrders, GroceriesOrderItems, GroceriesPayments
from kirazee_app.models import Registration, Business, BusinessMapping, UserAddress
from django.db import transaction
import razorpay
from decimal import Decimal, InvalidOperation
import logging
import math
from datetime import date
from django.core.mail import send_mail
from django.conf import settings
import csv
import io
import json
from django.http import HttpResponse
from datetime import datetime
from rest_framework.parsers import MultiPartParser, FormParser
from django.utils import timezone
from .utils.interakt import (
    send_order_summary_message,
    send_out_for_delivery_message,
    send_pickup_ready_message,
    send_pickup_otp_message,
)

logger = logging.getLogger(__name__)

# Default store coordinates (delivery start point)
DEFAULT_STORE_LAT = 13.6029732
DEFAULT_STORE_LNG = 79.9296724

# Haversine distance in kilometers
def haversine_km(lat1, lon1, lat2, lon2):
    R = 6371.0  # Earth radius in KM
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return R * c

@swagger_auto_schema(tags=['Consumer'])
class GroceriesByBusinessView(APIView):
    """
    API view to fetch grocery products by business ID.
    """
    def get(self, request, *args, **kwargs):
        """
        Handles GET requests to fetch grocery products for a given business ID from query parameters.
        """
        business_id = request.query_params.get('business_id')
        category_id = request.query_params.get('category_id')
        if not business_id:
            return Response({"error": "business_id parameter is required."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            # Base queryset: products for this business
            products = GroceriesProducts.objects.select_related(
                'category', 'business'
            ).filter(
                business_id=business_id
            )

            # Optional filter: treat category_id as a parent category id
            # so that all sub categories under this parent are included.
            if category_id:
                products = products.filter(
                    Q(category_id=category_id) |
                    Q(category__parent_category=category_id)
                )

            # Ensure category belongs to the same business when category.business_id is set
            products = products.filter(
                Q(category__business_id__isnull=True) | Q(category__business_id=business_id)
            ).order_by('product_name')

            if not products.exists():
                return Response({"message": "No products found for this business."}, status=status.HTTP_404_NOT_FOUND)

            serializer = GroceriesProductsSerializer(products, many=True, context={'request': request})
            return Response(serializer.data, status=status.HTTP_200_OK)

        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

@swagger_auto_schema(tags=['Consumer'])
class UserTopItemsView(APIView):
    """
    API view to fetch the top-N items a user buys most for a given business.
    If user_id is not provided, it first identifies the top buyer (by total quantity) for that business
    and then returns that user's top items.

    GET params:
      - business_id: required
      - user_id: optional; if omitted, selects top buyer for the business
      - limit: optional; default 10
      - sort_by: optional; 'quantity' (default) or 'revenue'
    Only includes orders with payment_status = 'paid'.
    """
    def get(self, request, *args, **kwargs):
        business_id = request.query_params.get('business_id')
        user_id = request.query_params.get('user_id')
        limit = int(request.query_params.get('limit', 10))
        sort_by = (request.query_params.get('sort_by') or 'quantity').strip().lower()
        if sort_by not in ('quantity', 'revenue'):
            sort_by = 'quantity'

        if not business_id:
            return Response({"error": "business_id parameter is required."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            target_user_id = user_id
            # If user_id not provided, find the top buyer for this business
            if not target_user_id:
                with connection.cursor() as cursor:
                    cursor.execute(
                        """
                        SELECT go.user_id,
                               COALESCE(SUM(goi.quantity), 0) AS total_quantity_sold,
                               COALESCE(SUM(goi.total_price), 0) AS total_revenue
                        FROM Groceries_order_items goi
                        INNER JOIN Groceries_orders go ON go.order_id = goi.order_id
                        WHERE go.business_id = %s
                          AND LOWER(go.payment_status) = 'paid'
                        GROUP BY go.user_id
                        ORDER BY total_quantity_sold DESC
                        LIMIT 1
                        """,
                        [business_id]
                    )
                    row = cursor.fetchone()
                    if not row:
                        return Response({
                            "message": "No paid orders found for this business. Cannot determine top user.",
                            "business_id": business_id,
                            "results": []
                        }, status=status.HTTP_200_OK)
                    target_user_id = str(row[0])

            # Aggregate top items for the target user
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT goi.product_id,
                           COALESCE(SUM(goi.quantity), 0) AS total_quantity_sold,
                           COALESCE(SUM(goi.total_price), 0) AS total_revenue
                    FROM Groceries_order_items goi
                    INNER JOIN Groceries_orders go ON go.order_id = goi.order_id
                    WHERE go.business_id = %s
                      AND go.user_id = %s
                      AND LOWER(go.payment_status) = 'paid'
                    GROUP BY goi.product_id
                    """,
                    [business_id, target_user_id]
                )
                cols = [c[0] for c in cursor.description]
                rows = [dict(zip(cols, r)) for r in cursor.fetchall()]

            # Sort and limit
            if sort_by == 'revenue':
                rows.sort(key=lambda r: float(r.get('total_revenue') or 0.0), reverse=True)
            else:
                rows.sort(key=lambda r: int(r.get('total_quantity_sold') or 0), reverse=True)
            top_rows = rows[:limit]

            # Fetch full item details using the serializer for consistency
            item_details_map = {}
            if top_rows:
                product_ids = [r['product_id'] for r in top_rows]
                products = GroceriesProducts.objects.filter(product_id__in=product_ids, business_id=business_id).prefetch_related('groceriesproductvariants_set')
                serializer = GroceriesProductWithPricingSerializer(products, many=True, context={'request': request})
                item_details_map = {item['product_id']: item for item in serializer.data}

            # Optionally fetch user details
            user_details = None
            try:
                user = Registration.objects.filter(user_id=target_user_id).values(
                    'user_id', 'firstName', 'lastName', 'mobileNumber', 'emailID'
                ).first()
                if user:
                    user_details = {
                        'user_id': user.get('user_id'),
                        'name': f"{user.get('firstName', '')} {user.get('lastName', '')}".strip(),
                        'phone': user.get('mobileNumber'),
                        'email': user.get('emailID'),
                    }
            except Exception:
                user_details = None

            # Build response
            results = []
            for r in top_rows:
                product_id = r['product_id']
                results.append({
                    'product_id': product_id,
                    'total_quantity_sold': int(r.get('total_quantity_sold') or 0),
                    'total_revenue': float(r.get('total_revenue') or 0.0),
                    'product': item_details_map.get(product_id, {})
                })

            return Response({
                'business_id': business_id,
                'user_id': str(target_user_id),
                'limit': limit,
                'sort_by': sort_by,
                'total_items': len(results),
                'user_details': user_details,
                'results': results
            }, status=status.HTTP_200_OK)

        except Exception as e:
            logger.error(f"Error fetching user's top items: {str(e)}")
            return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@swagger_auto_schema(tags=['Consumer'])
class GroceriesBulkTemplateView(APIView):
    """
    Downloadable CSV template for bulk upload to Categories, Products, and Variants.
    """
    def get(self, request, *args, **kwargs):
        headers = [
            # Category fields
            'category_name', 'parent_category_name', 'gst_rate',
            # Product fields
            'product_name', 'brand_name', 'sub_category', 'sub_category_id', 'description',
            'main_image', 'base_price', 'is_organic', 'is_visible', 'rating',
            # Core variant fields
            'sku', 'barcode', 'net_weight', 'net_weight_unit', 'size',
            'original_cost', 'selling_price', 'price_override', 'charges', 'stock',
            'mfg_date', 'expiry_date', 'is_active',
            # Attribute variant fields
            'color', 'gender', 'age', 'min_age', 'max_age', 'material', 'attributes', 'pack',
            'is_visible_counter',
        ]

        sample_row = {
            'category_name': 'Dairy',
            'parent_category_name': '',
            'gst_rate': '5',
            'product_name': 'Toned Milk',
            'brand_name': 'BrandX',
            'sub_category': 'Milk & Cream',
            'sub_category_id': '',
            'description': 'Fresh toned milk',
            'main_image': 'https://example.com/images/milk.jpg',
            'base_price': '60.00',
            'is_organic': 'no',
            'is_visible': 'yes',
            'rating': '4.5',
            'sku': 'MILK-TONED-1L',
            'barcode': '',
            'net_weight': '1',
            'net_weight_unit': 'l',
            'size': '1L',
            'original_cost': '65.00',
            'selling_price': '60.00',
            'price_override': '',
            'charges': '0.00',
            'stock': '100',
            'mfg_date': '2025-01-01',
            'expiry_date': '2025-01-10',
            'is_active': 'yes',
            # Attribute fields (leave blank if not applicable)
            'color': '',
            'gender': '',
            'age': '',
            'min_age': '',
            'max_age': '',
            'material': '',
            'attributes': '',
            'pack': '',
            'is_visible_counter': 'yes',
        }

        output = io.StringIO()
        writer = csv.DictWriter(output, fieldnames=headers)
        writer.writeheader()
        writer.writerow(sample_row)

        response = HttpResponse(output.getvalue(), content_type='text/csv')
        response['Content-Disposition'] = 'attachment; filename="groceries_bulk_template.csv"'
        return response


@swagger_auto_schema(tags=['Consumer'])
class GroceriesBulkUploadView(APIView):
    """
    Bulk CSV upload that populates GroceriesCategories, GroceriesProducts, and GroceriesProductVariants.
    - Requires business_id as query param (applied to all products in the file)
    - Accepts flags in the body via serializer: dry_run, all_or_nothing, update_existing, create_missing_categories, encoding
    CSV columns supported (header names are case-insensitive):
      category_name, parent_category_name, gst_rate,
      product_name, brand_name, sub_category, description, main_image, is_organic, is_visible, rating,
      sku, net_weight, net_weight_unit, size, original_cost, selling_price, charges, stock, mfg_date, expiry_date, is_active
    """
    # Accept file uploads via multipart/form-data
    parser_classes = (MultiPartParser, FormParser)

    def post(self, request, *args, **kwargs):
        business_id = request.query_params.get('business_id')
        if not business_id:
            return Response({"error": "business_id query parameter is required."}, status=status.HTTP_400_BAD_REQUEST)

        # Validate business exists
        try:
            Business.objects.get(business_id=business_id)
        except Business.DoesNotExist:
            return Response({"error": "Business not found."}, status=status.HTTP_404_NOT_FOUND)

        serializer = BulkGroceriesUploadSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        upload = serializer.validated_data['file']
        dry_run = serializer.validated_data.get('dry_run', False)
        all_or_nothing = serializer.validated_data.get('all_or_nothing', False)
        update_existing = serializer.validated_data.get('update_existing', True)
        create_missing_categories = serializer.validated_data.get('create_missing_categories', True)
        encoding = serializer.validated_data.get('encoding', 'utf-8')

        # Helpers
        def to_bool(val):
            if val is None:
                return False
            s = str(val).strip().lower()
            return s in ('1', 'true', 'yes', 'y')

        def to_decimal(val, default='0.00'):
            try:
                if val is None or str(val).strip() == '':
                    return Decimal(default)
                return Decimal(str(val).strip())
            except Exception:
                return Decimal(default)

        def to_int(val, default=0):
            try:
                if val is None or str(val).strip() == '':
                    return default
                return int(float(str(val).strip()))
            except Exception:
                return default

        def to_date(val):
            try:
                if not val or str(val).strip() == '':
                    return None
                return datetime.strptime(str(val).strip(), '%Y-%m-%d').date()
            except Exception:
                return None

        def normalize_unit(unit):
            """Normalize common weight/volume/unit aliases to model choices.
            Examples: ltr->l, liters->l, gm->g, kgs->kg, pcs./piece->pcs, pkt/packet->pack
            """
            try:
                if unit is None:
                    return None
                raw = str(unit).strip().lower()
                if raw == '':
                    return raw
                # Remove punctuation and spaces to make matching robust
                normalized = raw.replace('.', '').replace('-', '').replace('_', '').replace(' ', '')
                aliases = {
                    # liters
                    'ltr': 'l', 'ltrs': 'l', 'liter': 'l', 'liters': 'l', 'litre': 'l', 'litres': 'l',
                    # milliliters
                    'mls': 'ml', 'milliliter': 'ml', 'milliliters': 'ml', 'millilitre': 'ml', 'millilitres': 'ml',
                    # grams
                    'gm': 'g', 'gms': 'g', 'gram': 'g', 'grams': 'g',
                    # kilograms
                    'kgs': 'kg', 'kilogram': 'kg', 'kilograms': 'kg',
                    # pieces
                    'pc': 'pcs', 'piece': 'pcs', 'pieces': 'pcs', 'no': 'pcs', 'nos': 'pcs', 'unit': 'pcs', 'units': 'pcs',
                    'wipe': 'pcs', 'wipes': 'pcs',
                    # packs (map common synonyms to 'Packet'; keep 'pack' as-is when provided)
                    'packet': 'Packet', 'packets': 'Packet', 'pkt': 'Packet', 'pkts': 'Packet', 'pckt': 'Packet',
                    'packs': 'pack',
                    # Retail packaging singular/plural to proper-cased labels present in choices
                    'bag': 'Bag', 'bags': 'Bag',
                    'bottle': 'Bottle', 'bottles': 'Bottle',
                    'box': 'Box', 'boxes': 'Box',
                    'can': 'Can', 'cans': 'Can',
                    'dozen': 'Dozen', 'dozens': 'Dozen',
                    'jar': 'Jar', 'jars': 'Jar',
                    'roll': 'Roll', 'rolls': 'Roll',
                    'tray': 'Tray', 'trays': 'Tray',
                    'other': 'Other', 'others': 'Other',
                    # Apparel
                    'pant': 'Pants', 'pants': 'Pants', 'pantes': 'Pants', 'pnt': 'Pants',
                    'shirt': 'Shirts', 'shirts': 'Shirts',
                    # Misc free-text often seen
                    'month': 'Other', 'months': 'Other',
                }
                return aliases.get(normalized, normalized)
            except Exception:
                return str(unit).strip().lower()

        # Read CSV
        try:
            raw = upload.read()
            if isinstance(raw, bytes):
                # Try multiple encodings to handle files saved from Excel/Windows
                enc_candidates = []
                if encoding:
                    enc_candidates.append(encoding or 'utf-8')
                for e in ['utf-8-sig', 'utf-8', 'cp1252', 'latin1']:
                    if e not in enc_candidates:
                        enc_candidates.append(e)
                last_exc = None
                text = None
                used_encoding = None
                for enc in enc_candidates:
                    try:
                        text = raw.decode(enc)
                        used_encoding = enc
                        break
                    except UnicodeDecodeError as ue:
                        last_exc = ue
                if text is None:
                    return Response({
                        "error": "Failed to read CSV: could not decode file with supported encodings.",
                        "details": str(last_exc) if last_exc else "Unknown decode error",
                        "suggestion": "Save the CSV as UTF-8 (with BOM) or try selecting encoding=cp1252/latin1."
                    }, status=status.HTTP_400_BAD_REQUEST)
            else:
                text = str(raw)
                used_encoding = 'unicode'
            reader = csv.DictReader(io.StringIO(text))
        except Exception as e:
            return Response({"error": f"Failed to read CSV: {str(e)}"}, status=status.HTTP_400_BAD_REQUEST)

        # Normalize header keys mapping (case-insensitive)
        field_map = {k.lower().strip(): k for k in reader.fieldnames or []}
        # Support common header synonyms (e.g., 'is active' -> 'is_active')
        synonyms = {
            'is_active': ['is active', 'isactive'],
            'is_visible': ['is visible', 'isvisible', 'visible'],
            'is_visible_counter': ['is visible counter', 'isvisiblecounter', 'visible_counter'],
            'gst_rate': ['gst rate'],
            'main_image': ['main image'],
            'net_weight_unit': ['net weight unit'],
            'net_weight': ['net weight'],
            'selling_price': ['selling price', 'sale_price'],
            'original_cost': ['original cost', 'mrp', 'cost_price'],
            'mfg_date': ['mfg date', 'manufacture_date'],
            'expiry_date': ['expiry date', 'exp_date'],
            'sub_category': ['sub category', 'subcategory'],
            'sub_category_id': ['sub category id', 'subcategoryid', 'sub_category_id'],
        }
        for canonical, alts in synonyms.items():
            if canonical not in field_map:
                for alt in alts:
                    if alt in field_map:
                        field_map[canonical] = field_map[alt]
                        break

        required_fields = ['category_name', 'product_name', 'sku', 'selling_price']
        missing = [rf for rf in required_fields if rf not in field_map]
        if missing:
            return Response({
                "error": "Missing required columns in CSV",
                "missing_columns": missing
            }, status=status.HTTP_400_BAD_REQUEST)

        # Caches
        category_cache = {}
        product_cache = {}

        results = {
            'rows_processed': 0,
            'categories_created': 0,
            'categories_updated': 0,
            'products_created': 0,
            'products_updated': 0,
            'variants_created': 0,
            'variants_updated': 0,
            'errors': []
        }

        weight_unit_choices = set([c[0] for c in GroceriesProductVariants.WEIGHT_UNIT_CHOICES])

        def process_row(row_idx, row):
            # Extract with case-insensitive keys
            def get(col):
                key = field_map.get(col)
                return row.get(key) if key else None
            # Track whether CSV provided a sub_category column at all
            has_sub_category_col = 'sub_category' in field_map
            has_is_customizable_col = 'is_customizable' in field_map

            category_name = (get('category_name') or '').strip()
            parent_category_name = (get('parent_category_name') or '').strip()
            gst_rate_val = get('gst_rate')

            product_name = (get('product_name') or '').strip()
            brand_name = (get('brand_name') or '').strip() or None
            sub_category = (get('sub_category') or '').strip() or None
            description = get('description')
            main_image = get('main_image')
            is_customizable_raw = get('is_customizable')
            is_organic = to_bool(get('is_organic'))
            is_visible_val = get('is_visible')
            if is_visible_val is None or str(is_visible_val).strip() == '':
                is_visible = True
            else:
                is_visible = to_bool(is_visible_val)
            rating_val = get('rating')

            is_customizable = None
            if has_is_customizable_col and is_customizable_raw is not None and str(is_customizable_raw).strip() != '':
                is_customizable = to_bool(is_customizable_raw)

            sku = (get('sku') or '').strip()
            barcode = (get('barcode') or '').strip() or None
            net_weight = to_int(get('net_weight'), default=0)
            net_weight_unit = normalize_unit(get('net_weight_unit') or 'pcs')
            # size: stored as JSON in DB; accept plain string from CSV and wrap it
            size_raw = (get('size') or '').strip() or None
            if size_raw:
                # If it looks like a JSON object already, parse it; else wrap as {"value": "..."}
                try:
                    size = json.loads(size_raw) if size_raw.startswith('{') else {'value': size_raw}
                except Exception:
                    size = {'value': size_raw}
            else:
                size = None
            original_cost = to_decimal(get('original_cost'))
            selling_price = to_decimal(get('selling_price'))
            charges = to_decimal(get('charges'))
            stock = to_int(get('stock'), default=0)
            mfg_date = to_date(get('mfg_date'))
            expiry_date = to_date(get('expiry_date'))
            is_active = to_bool(get('is_active')) if get('is_active') is not None else True
            # New attribute columns
            color = (get('color') or '').strip() or None
            gender = (get('gender') or '').strip() or None
            age = (get('age') or '').strip() or None
            material = (get('material') or '').strip() or None
            pack = (get('pack') or '').strip() or None
            is_visible_counter_raw = get('is_visible_counter')
            is_visible_counter = to_bool(is_visible_counter_raw) if is_visible_counter_raw is not None and str(is_visible_counter_raw).strip() != '' else True
            # attributes: accept JSON string from CSV
            attributes_raw = (get('attributes') or '').strip() or None
            if attributes_raw:
                try:
                    attributes = json.loads(attributes_raw)
                except Exception:
                    attributes = {'raw': attributes_raw}
            else:
                attributes = None
            # sub_category_id: integer FK
            sub_category_id_raw = get('sub_category_id')
            try:
                sub_category_id = int(sub_category_id_raw) if sub_category_id_raw and str(sub_category_id_raw).strip() else None
            except (ValueError, TypeError):
                sub_category_id = None

            # base_price: product-level decimal (default 0.00)
            base_price = to_decimal(get('base_price')) or 0

            # price_override: variant-level nullable decimal
            price_override = to_decimal(get('price_override'))  # None if blank

            # min_age / max_age: nullable integers for the age-range slider
            try:
                min_age_raw = get('min_age')
                min_age = int(min_age_raw) if min_age_raw and str(min_age_raw).strip() else None
            except (ValueError, TypeError):
                min_age = None
            try:
                max_age_raw = get('max_age')
                max_age = int(max_age_raw) if max_age_raw and str(max_age_raw).strip() else None
            except (ValueError, TypeError):
                max_age = None

            # Validate
            if not category_name:
                results['errors'].append({
                    'row': row_idx,
                    'error': 'category_name is required'
                })
                return

            if not product_name:
                results['errors'].append({
                    'row': row_idx,
                    'error': 'product_name is required'
                })
                return

            if not sku:
                results['errors'].append({
                    'row': row_idx,
                    'error': 'sku is required'
                })
                return

            if net_weight_unit and net_weight_unit not in weight_unit_choices:
                results['errors'].append({
                    'row': row_idx,
                    'error': f"Invalid net_weight_unit '{net_weight_unit}'. Allowed: {sorted(weight_unit_choices)}"
                })
                return

            # Categories: get or create
            category_key = (category_name.lower(), (parent_category_name or '').lower())
            category_obj = category_cache.get(category_key)
            if not category_obj:
                try:
                    # Try to find parent (by name)
                    parent = None
                    if parent_category_name:
                        parent = GroceriesCategories.objects.filter(category_name__iexact=parent_category_name).first()

                    category_obj = GroceriesCategories.objects.filter(category_name__iexact=category_name).first()
                    if category_obj:
                        # Update GST or parent if requested
                        updated = False
                        if update_existing:
                            try:
                                gst_rate = to_decimal(gst_rate_val, default=str(category_obj.gst_rate or '0.00'))
                                if category_obj.gst_rate != gst_rate:
                                    category_obj.gst_rate = gst_rate
                                    updated = True
                                if parent and category_obj.parent_category_id != parent.category_id:
                                    category_obj.parent_category = parent
                                    updated = True
                                if updated and not dry_run:
                                    category_obj.save()
                                if updated:
                                    results['categories_updated'] += 1
                            except Exception:
                                pass
                    else:
                        if not create_missing_categories:
                            results['errors'].append({'row': row_idx, 'error': f"Category '{category_name}' not found and create_missing_categories=False"})
                            return
                        # Create new category
                        gst_rate = to_decimal(gst_rate_val)
                        if not dry_run:
                            category_obj = GroceriesCategories.objects.create(
                                category_name=category_name,
                                parent_category=parent,
                                gst_rate=gst_rate
                            )
                        else:
                            # Simulate object with minimal attributes
                            category_obj = GroceriesCategories(category_name=category_name, parent_category=parent, gst_rate=gst_rate)
                        results['categories_created'] += 1

                    category_cache[category_key] = category_obj
                except Exception as e:
                    results['errors'].append({'row': row_idx, 'error': f"Category error: {str(e)}"})
                    return

            # Products: find by business + product_name + brand_name (case-insensitive)
            product_key = (product_name.lower(), (brand_name or '').lower())
            product_obj = product_cache.get(product_key)
            if not product_obj:
                try:
                    product_qs = GroceriesProducts.objects.filter(
                        business_id=business_id,
                        product_name__iexact=product_name
                    )
                    if brand_name:
                        product_qs = product_qs.filter(brand_name__iexact=brand_name)
                    product_obj = product_qs.first()

                    # Rating handling (<= 9.9 with 1 decimal)
                    try:
                        rating = None
                        if rating_val is not None and str(rating_val).strip() != '':
                            rating = Decimal(str(rating_val)).quantize(Decimal('0.1'))
                            if rating > Decimal('9.9'):
                                rating = Decimal('9.9')
                    except Exception:
                        rating = None

                    if product_obj:
                        if update_existing:
                            # Update fields
                            product_obj.category = category_obj
                            # Only update sub_category if the CSV had that column
                            if has_sub_category_col and sub_category is not None:
                                product_obj.sub_category = sub_category
                            # Update sub_category_id if provided
                            if sub_category_id is not None:
                                product_obj.sub_category_id = sub_category_id
                            if description is not None:
                                product_obj.description = description
                            if main_image is not None:
                                product_obj.main_image = main_image
                            if has_is_customizable_col and is_customizable is not None:
                                product_obj.is_customizable = is_customizable
                            product_obj.is_organic = is_organic
                            product_obj.is_visible = is_visible
                            product_obj.base_price = base_price
                            product_obj.brand_name = brand_name
                            if rating is not None:
                                product_obj.rating = rating
                            if not dry_run:
                                product_obj.save()
                            results['products_updated'] += 1
                    else:
                        # Create product
                        if not dry_run:
                            product_obj = GroceriesProducts.objects.create(
                                business_id=business_id,
                                product_name=product_name,
                                brand_name=brand_name,
                                category=category_obj,
                                sub_category=sub_category,
                                sub_category_id=sub_category_id,
                                description=description or '',
                                main_image=main_image or '',
                                is_customizable=is_customizable if is_customizable is not None else False,
                                is_organic=is_organic,
                                is_visible=is_visible,
                                base_price=base_price,
                                rating=rating
                            )
                        else:
                            product_obj = GroceriesProducts(
                                business=Business(business_id=business_id),
                                product_name=product_name,
                                brand_name=brand_name,
                                category=category_obj,
                                sub_category=sub_category,
                                sub_category_id=sub_category_id,
                                description=description or '',
                                main_image=main_image or '',
                                is_customizable=is_customizable if is_customizable is not None else False,
                                is_organic=is_organic,
                                is_visible=is_visible,
                                base_price=base_price,
                                rating=rating
                            )
                        results['products_created'] += 1

                    product_cache[product_key] = product_obj
                except Exception as e:
                    results['errors'].append({'row': row_idx, 'error': f"Product error: {str(e)}"})
                    return

            # Variants: unique by sku
            try:
                existing_variant = GroceriesProductVariants.objects.filter(sku=sku).first()
                if existing_variant:
                    if update_existing:
                        # Update existing
                        if net_weight is not None:
                            existing_variant.net_weight = net_weight
                        if net_weight_unit:
                            existing_variant.net_weight_unit = net_weight_unit
                        existing_variant.size = size
                        existing_variant.original_cost = original_cost
                        existing_variant.selling_price = selling_price
                        existing_variant.charges = charges
                        existing_variant.stock = stock
                        existing_variant.mfg_date = mfg_date
                        existing_variant.expiry_date = expiry_date
                        existing_variant.is_active = is_active
                        # Update new attribute columns only if the CSV column was present
                        if barcode is not None:
                            existing_variant.barcode = barcode
                        if color is not None:
                            existing_variant.color = color
                        if gender is not None:
                            existing_variant.gender = gender
                        if age is not None:
                            existing_variant.age = age
                        if material is not None:
                            existing_variant.material = material
                        if attributes is not None:
                            existing_variant.attributes = attributes
                        if pack is not None:
                            existing_variant.pack = pack
                        existing_variant.is_visible_counter = is_visible_counter
                        if price_override is not None:
                            existing_variant.price_override = price_override
                        if min_age is not None:
                            existing_variant.min_age = min_age
                        if max_age is not None:
                            existing_variant.max_age = max_age
                        if not dry_run:
                            existing_variant.save()
                        results['variants_updated'] += 1
                    else:
                        results['errors'].append({'row': row_idx, 'error': f"Variant with sku '{sku}' already exists and update_existing=False"})
                        return
                else:
                    # Create new variant
                    if not dry_run:
                        GroceriesProductVariants.objects.create(
                            product=product_obj,
                            sku=sku,
                            barcode=barcode,
                            net_weight=net_weight,
                            net_weight_unit=net_weight_unit or 'pcs',
                            size=size,
                            original_cost=original_cost,
                            selling_price=selling_price,
                            charges=charges,
                            stock=stock,
                            mfg_date=mfg_date,
                            expiry_date=expiry_date,
                            is_active=is_active,
                            color=color,
                            gender=gender,
                            age=age,
                            min_age=min_age,
                            max_age=max_age,
                            material=material,
                            attributes=attributes,
                            pack=pack,
                            is_visible_counter=is_visible_counter,
                            price_override=price_override,
                        )
                    results['variants_created'] += 1
            except Exception as e:
                results['errors'].append({'row': row_idx, 'error': f"Variant error: {str(e)}"})
                return

        # Process rows
        try:
            if all_or_nothing and not dry_run:
                with transaction.atomic():
                    for idx, row in enumerate(reader, start=2):  # start=2 (1-based + header)
                        results['rows_processed'] += 1
                        process_row(idx, row)
                        if results['errors']:
                            # Raise to trigger rollback
                            raise Exception('Errors encountered; rolling back due to all_or_nothing=True')
            else:
                for idx, row in enumerate(reader, start=2):
                    results['rows_processed'] += 1
                    process_row(idx, row)
        except Exception as e:
            if all_or_nothing and not dry_run:
                # Transaction already rolled back
                results['rollback'] = True
            results['fatal_error'] = str(e)

        return Response({
            'message': 'Dry run completed.' if dry_run else 'Bulk upload processed.',
            'business_id': business_id,
            'summary': results
        }, status=status.HTTP_200_OK)

@swagger_auto_schema(tags=['Consumer'])
class GroceryCategoriesByBusinessView(APIView):
    """
    API view to fetch distinct grocery categories by business ID.
    """
    def get(self, request, *args, **kwargs):
        """
        Handles GET requests to fetch categories for a given business ID.
        """
        business_id = request.query_params.get('business_id')
        if not business_id:
            return Response({"error": "business_id parameter is required."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            # First, try categories explicitly linked to this business via business_id column
            categories = GroceriesCategories.objects.filter(
                business_id=business_id
            ).distinct().order_by('category_name')

            # Backward-compatible fallback: if no categories have business_id set,
            # derive categories from products for this business
            if not categories.exists():
                categories = GroceriesCategories.objects.filter(
                    groceriesproducts__business_id=business_id
                ).distinct().order_by('category_name')

            if not categories.exists():
                return Response({"message": "No categories found for this business."}, status=status.HTTP_404_NOT_FOUND)

            serializer = GroceriesCategoriesSerializer(categories, many=True)
            return Response(serializer.data, status=status.HTTP_200_OK)

        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@swagger_auto_schema(tags=['Consumer'])
class ServiceAvailabilityView(APIView):
    """Get delivery/pickup availability for a business.
    Response: { delivery_enabled: bool, pickup_enabled: bool }
    """
    def get(self, request, *args, **kwargs):
        business_id = request.query_params.get('business_id')
        if not business_id:
            return Response({"error": "business_id parameter is required."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            business = Business.objects.get(business_id=business_id)
            # Normalize business_features to a dict
            raw_cfg = getattr(business, 'business_features', None)
            cfg = {}
            if isinstance(raw_cfg, dict):
                cfg = raw_cfg
            elif isinstance(raw_cfg, str) and raw_cfg.strip():
                try:
                    parsed = json.loads(raw_cfg)
                    cfg = parsed if isinstance(parsed, dict) else {}
                except Exception:
                    cfg = {}

            def to_bool(v, default=True):
                try:
                    if isinstance(v, bool):
                        return v
                    s = str(v).strip().lower()
                    if s == '':
                        return default
                    return s in ('1', 'true', 'yes', 'y', 'on')
                except Exception:
                    return default

            resp = {
                'delivery_enabled': to_bool((cfg or {}).get('delivery_enabled', True), True),
                'pickup_enabled': to_bool((cfg or {}).get('pickup_enabled', True), True),
            }
            return Response(resp, status=status.HTTP_200_OK)
        except Business.DoesNotExist:
            return Response({"error": "Business not found."}, status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@swagger_auto_schema(tags=['Consumer'])
class UpdateServiceAvailabilityView(APIView):
    """Admin endpoint to update delivery/pickup availability for a business.
    Requires query params: user_id, business_id and body with one or both flags.
    """
    def post(self, request, *args, **kwargs):
        user_id = request.query_params.get('user_id')
        business_id = request.query_params.get('business_id')
        if not all([user_id, business_id]):
            return Response({"error": "user_id and business_id are required."}, status=status.HTTP_400_BAD_REQUEST)

        # AuthZ: user must be retail_business and mapped to the business
        try:
            user = Registration.objects.get(user_id=user_id)
            if str(user.user_mode).lower() not in ('retail_business', 'admin', 'business_admin'):
                return Response({"error": "Not authorized to update service availability."}, status=status.HTTP_403_FORBIDDEN)
        except Registration.DoesNotExist:
            return Response({"error": "User not found."}, status=status.HTTP_404_NOT_FOUND)

        try:
            business = Business.objects.get(business_id=business_id)
        except Business.DoesNotExist:
            return Response({"error": "Business not found."}, status=status.HTTP_404_NOT_FOUND)

        # Verify mapping if table exists
        try:
            if not BusinessMapping.objects.filter(user__user_id=user_id, business__business_id=business_id, status=True).exists():
                return Response({"error": "User is not associated with this business."}, status=status.HTTP_403_FORBIDDEN)
        except Exception:
            # If mapping table isn't available, proceed based on user_mode check above
            pass

        serializer = ServiceAvailabilityUpdateSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        try:
            # Normalize business_features to a dict
            raw_cfg = getattr(business, 'business_features', None)
            cfg = {}
            if isinstance(raw_cfg, dict):
                cfg = raw_cfg
            elif isinstance(raw_cfg, str) and raw_cfg.strip():
                try:
                    parsed = json.loads(raw_cfg)
                    cfg = parsed if isinstance(parsed, dict) else {}
                except Exception:
                    cfg = {}
            if 'delivery_enabled' in serializer.validated_data:
                cfg['delivery_enabled'] = bool(serializer.validated_data['delivery_enabled'])
            if 'pickup_enabled' in serializer.validated_data:
                cfg['pickup_enabled'] = bool(serializer.validated_data['pickup_enabled'])
            business.business_features = cfg
            business.save()

            # Return current state
            resp = {
                'delivery_enabled': bool(cfg.get('delivery_enabled', True)),
                'pickup_enabled': bool(cfg.get('pickup_enabled', True)),
            }
            return Response(resp, status=status.HTTP_200_OK)
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

@swagger_auto_schema(tags=['Consumer'])
class GroceriesByCategoryView(APIView):
    """
    API view to fetch grocery products grouped by category for a given business ID.
    OPTIMIZED: Single query with prefetch_related for 10x faster performance.
    Grouping logic:
      - If a category has a parent_category, group products under the parent.
      - Otherwise, group under the category itself.
    This way all sub categories (e.g., Baby Care_5, Baby Care_10) appear under
    their parent category (e.g., Baby Care) in the response, while GST and
    other details still come from the actual product category rows.
    """
    def get(self, request, *args, **kwargs):
        business_id = request.query_params.get('business_id')
        if not business_id:
            return Response({"error": "business_id parameter is required."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            # OPTIMIZATION: Fetch ALL products in a SINGLE query with prefetch_related
            # This eliminates the N+1 query problem (1 query instead of N queries)
            products = GroceriesProducts.objects.select_related(
                'category', 'business'
            ).prefetch_related(
                'groceriesproductvariants_set'
            ).filter(
                business_id=business_id
            ).order_by('category__category_name', 'product_name')
            
            if not products.exists():
                return Response({"message": "No products found for this business."}, status=status.HTTP_404_NOT_FOUND)
            
            # Group products by EFFECTIVE category (parent if present, else self)
            from collections import defaultdict
            category_map = defaultdict(list)
            
            for product in products:
                category = product.category
                if not category:
                    continue
                # Use parent category when available, else the category itself
                parent_name = (category.parent_category or '').strip()
                effective_name = parent_name or category.category_name
                category_map[effective_name].append(product)
            
            # Serialize once per category
            response_data = []
            for category_name, product_list in category_map.items():
                if product_list:
                    # All products in this list share the same effective (parent) category
                    # computed above; use it for display.
                    category = product_list[0].category
                    serializer = GroceriesProductWithPricingSerializer(product_list, many=True, context={'request': request})
                    response_data.append({
                        "category": category_name,
                        "category_id": getattr(category, 'category_id', None),
                        "products": serializer.data
                    })
            
            # Sort by category name
            response_data.sort(key=lambda x: x['category'])

            return Response(response_data, status=status.HTTP_200_OK)

        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@swagger_auto_schema(tags=['Consumer'])
class CreateOrderView(APIView):
    """
    API view to create an order directly from a list of items.
    """
    def post(self, request, *args, **kwargs):
        user_id = request.query_params.get('user_id')
        business_id = request.query_params.get('business_id')

        if not all([user_id, business_id]):
            return Response({"error": "user_id and business_id are required."}, status=status.HTTP_400_BAD_REQUEST)

        serializer = CreateOrderSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        # Enforce service availability (delivery/pickup) per business
        order_type = str(serializer.validated_data.get('order_type', '')).strip().lower()
        try:
            business = Business.objects.get(business_id=business_id)
            # Normalize business_features to a dict
            raw_cfg = getattr(business, 'business_features', None)
            cfg = {}
            if isinstance(raw_cfg, dict):
                cfg = raw_cfg
            elif isinstance(raw_cfg, str) and raw_cfg.strip():
                try:
                    parsed = json.loads(raw_cfg)
                    cfg = parsed if isinstance(parsed, dict) else {}
                except Exception:
                    cfg = {}

            def to_bool(v, default=True):
                try:
                    if isinstance(v, bool):
                        return v
                    s = str(v).strip().lower()
                    if s == '':
                        return default
                    return s in ('1', 'true', 'yes', 'y', 'on')
                except Exception:
                    return default

            delivery_enabled = to_bool(cfg.get('delivery_enabled', True), True)
            pickup_enabled = to_bool(cfg.get('pickup_enabled', True), True)

            if order_type == 'delivery' and not delivery_enabled:
                return Response({
                    "error": "Delivery is currently unavailable. Please select pickup.",
                    "delivery_enabled": False,
                    "pickup_enabled": pickup_enabled,
                }, status=status.HTTP_400_BAD_REQUEST)
            if order_type == 'pickup' and not pickup_enabled:
                return Response({
                    "error": "Pickup is currently unavailable. Please select delivery.",
                    "delivery_enabled": delivery_enabled,
                    "pickup_enabled": False,
                }, status=status.HTTP_400_BAD_REQUEST)
        except Business.DoesNotExist:
            return Response({"error": "Business not found."}, status=status.HTTP_404_NOT_FOUND)

        items_data = serializer.validated_data['items']
        delivery_charge = Decimal(serializer.validated_data.get('delivery_charge', '0.00'))
        discount = Decimal(serializer.validated_data.get('discount', '0.00'))
        # New optional fields for delivery scheduling and instructions
        delivery_time = serializer.validated_data.get('delivery_time')
        delivery_instructions = serializer.validated_data.get('delivery_instructions')
        # Extract delivery location coordinates
        delivery_latitude = serializer.validated_data.get('delivery_latitude')
        delivery_longitude = serializer.validated_data.get('delivery_longitude')

        try:
            with transaction.atomic():
                total_amount = Decimal('0.00')
                gst_amount = Decimal('0.00')
                order_items_to_create = []

                for item_data in items_data:
                    try:
                        product = GroceriesProducts.objects.select_related('category').get(
                            product_id=item_data['product_id'], 
                            business_id=business_id
                        )
                    except GroceriesProducts.DoesNotExist:
                        return Response({"error": f"Product with id {item_data['product_id']} not found for this business."}, status=status.HTTP_404_NOT_FOUND)

                    # Use provided variant_id if present; otherwise fallback to the cheapest active variant
                    try:
                        variant = None
                        variant_id = item_data.get('variant_id')
                        if variant_id is not None:
                            variant = GroceriesProductVariants.objects.filter(
                                variant_id=variant_id,
                                product=product,
                                is_active=True
                            ).first()
                            if not variant:
                                return Response({
                                    "error": f"Variant {variant_id} not found or inactive for product {product.product_name}."
                                }, status=status.HTTP_404_NOT_FOUND)
                        else:
                            variant = GroceriesProductVariants.objects.filter(
                                product=product,
                                is_active=True
                            ).order_by('selling_price').first()
                            if not variant:
                                return Response({
                                    "error": f"No active variants found for product {product.product_name}."
                                }, status=status.HTTP_404_NOT_FOUND)
                    except Exception:
                        return Response({
                            "error": f"Error fetching variants for product {product.product_name}."
                        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

                    quantity = item_data['quantity']
                    selling_price = variant.selling_price or Decimal('0.00')
                    # Get GST from variant (new field), fallback to category if not set
                    gst = variant.gst if variant.gst is not None else (product.category.gst_rate if product.category else Decimal('0'))

                    total_price_for_item = selling_price * quantity
                    gst_for_item = (gst * total_price_for_item) / Decimal('100')

                    total_amount += total_price_for_item
                    gst_amount += gst_for_item

                # Ensure all values are Decimal before calculation
                delivery_charge_decimal = Decimal(str(delivery_charge))
                discount_decimal = Decimal(str(discount))
                
                # Calculate final amount with proper decimal arithmetic
                final_amount = (total_amount + gst_amount + delivery_charge_decimal - discount_decimal).quantize(Decimal('0.00'))
                
                # Round all amounts to whole numbers before saving (JavaScript Math.round() behavior: 12.50→13, 12.55→13)
                total_amount = math.floor(total_amount + Decimal('0.5'))
                gst_amount = math.floor(gst_amount + Decimal('0.5'))
                delivery_charge = math.floor(delivery_charge_decimal + Decimal('0.5'))
                discount = math.floor(discount_decimal + Decimal('0.5'))
                final_amount = math.floor(final_amount + Decimal('0.5'))

                # Create the order first
                order = GroceriesOrders.objects.create(
                    user_id=user_id,
                    business_id=business_id,
                    order_type=order_type,
                    delivery_address=serializer.validated_data.get('delivery_address', ''),
                    delivery_latitude=delivery_latitude,
                    delivery_longitude=delivery_longitude,
                    delivery_time=delivery_time,
                    delivery_instructions=delivery_instructions,
                    pickup_time=serializer.validated_data.get('pickup_time'),
                    total_amount=total_amount,
                    gst_amount=gst_amount,
                    delivery_charge=delivery_charge,
                    discount=discount,
                    final_amount=final_amount,
                )

                # Now create order items with the order reference
                for item_data in items_data:
                    try:
                        product = GroceriesProducts.objects.select_related('category').get(
                            product_id=item_data['product_id'], 
                            business_id=business_id
                        )
                        # Resolve variant as above
                        variant = None
                        variant_id = item_data.get('variant_id')
                        if variant_id is not None:
                            variant = GroceriesProductVariants.objects.filter(
                                variant_id=variant_id,
                                product=product,
                                is_active=True
                            ).first()
                        else:
                            variant = GroceriesProductVariants.objects.filter(
                                product=product, 
                                is_active=True
                            ).order_by('selling_price').first()
                        
                        if not variant:
                            continue  # Skip if no active variant found
                            
                        quantity = item_data['quantity']
                        selling_price = variant.selling_price or Decimal('0.00')
                        # Get GST from variant (new field), fallback to category if not set
                        gst = variant.gst if variant.gst is not None else (product.category.gst_rate if product.category else Decimal('0'))
                        total_price_for_item = selling_price * quantity
                        
                        GroceriesOrderItems.objects.create(
                            order=order,
                            product=product,
                            quantity=quantity,
                            unit_price=selling_price,
                            gst=gst,
                            total_price=total_price_for_item
                        )
                    except Exception as e:
                        # Log the error but continue with other items
                        print(f"Error creating order item: {str(e)}")
                        continue

            order_serializer = GroceriesOrdersSerializer(order)
            return Response({
                "message": "Order created successfully.",
                "order": order_serializer.data
            }, status=status.HTTP_201_CREATED)

        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@swagger_auto_schema(tags=['Consumer'])
class GroceriesCartView(APIView):
    """
    API view for managing the user's grocery cart using query parameters.
    Supports adding, viewing, updating, and deleting cart items.
    """
    
    @swagger_auto_schema(
        tags=['grocery'],
        manual_parameters=[
            openapi.Parameter(
                'user_id',
                openapi.IN_QUERY,
                description='User ID to retrieve cart items',
                type=openapi.TYPE_STRING,
                required=True
            ),
            openapi.Parameter(
                'business_id',
                openapi.IN_QUERY,
                description='Business ID to retrieve cart items',
                type=openapi.TYPE_STRING,
                required=True
            ),
        ],
        responses={
            200: openapi.Response(
                description='Cart items retrieved successfully',
                examples={
                    'application/json': [
                        {
                            'cart_id': 'string',
                            'user_id': 'string',
                            'business_id': 'string',
                            'product_id': 'string',
                            'variant_id': 'string',
                            'quantity': 'integer',
                            'added_at': 'datetime'
                        }
                    ]
                }
            ),
            400: openapi.Response(
                description='Bad request - missing parameters',
                examples={
                    'application/json': {
                        'error': 'user_id and business_id are required.'
                    }
                }
            )
        }
    )
    def get(self, request, *args, **kwargs):
        user_id = request.query_params.get('user_id')
        business_id = request.query_params.get('business_id')
        if not all([user_id, business_id]):
            return Response({"error": "user_id and business_id are required."}, status=status.HTTP_400_BAD_REQUEST)

        cart_items = GroceriesCart.objects.filter(user_id=user_id, business_id=business_id).order_by('-added_at')
        serializer = GroceriesCartSerializer(cart_items, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)

    @swagger_auto_schema(
        tags=['grocery'],
        manual_parameters=[
            openapi.Parameter(
                'user_id',
                openapi.IN_QUERY,
                description='User ID adding item to cart',
                type=openapi.TYPE_STRING,
                required=True
            ),
            openapi.Parameter(
                'business_id',
                openapi.IN_QUERY,
                description='Business ID for the cart item',
                type=openapi.TYPE_STRING,
                required=True
            ),
        ],
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            properties={
                'product_id': openapi.Schema(type=openapi.TYPE_STRING, description='Product ID to add to cart'),
                'variant_id': openapi.Schema(type=openapi.TYPE_STRING, description='Product variant ID (optional)'),
                'quantity': openapi.Schema(type=openapi.TYPE_INTEGER, description='Quantity to add', default=1),
            },
            required=['product_id']
        ),
        responses={
            201: openapi.Response(
                description='Item added to cart successfully',
                examples={
                    'application/json': {
                        'message': 'Item added to cart successfully',
                        'cart_id': 'string',
                        'quantity': 'integer'
                    }
                }
            ),
            400: openapi.Response(
                description='Bad request - missing parameters or invalid data',
                examples={
                    'application/json': {
                        'error': 'user_id and business_id are required.'
                    }
                }
            ),
            404: openapi.Response(
                description='Product not found',
                examples={
                    'application/json': {
                        'error': 'Product not found'
                    }
                }
            )
        }
    )
    def post(self, request, *args, **kwargs):
        user_id = request.query_params.get('user_id')
        business_id = request.query_params.get('business_id')
        product_id = request.data.get('product_id')
        quantity = int(request.data.get('quantity', 1))

        if not all([user_id, business_id, product_id]):
            return Response({"error": "user_id, business_id, and product_id are required."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            cart_item, created = GroceriesCart.objects.get_or_create(
                user_id=user_id, business_id=business_id, product_id=product_id,
                defaults={'quantity': quantity}
            )
            if not created:
                cart_item.quantity += quantity
                cart_item.save()
            
            message = f"'{cart_item.product.product_name}' has been added to your cart." if created else f"'{cart_item.product.product_name}' quantity has been updated."
            serializer = GroceriesCartSerializer(cart_item)
            response_data = {
                "message": message,
                "data": serializer.data
            }
            return Response(response_data, status=status.HTTP_201_CREATED if created else status.HTTP_200_OK)
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    @swagger_auto_schema(
        tags=['grocery'],
        manual_parameters=[
            openapi.Parameter(
                'user_id',
                openapi.IN_QUERY,
                description='User ID updating cart item',
                type=openapi.TYPE_STRING,
                required=True
            ),
            openapi.Parameter(
                'business_id',
                openapi.IN_QUERY,
                description='Business ID for the cart item',
                type=openapi.TYPE_STRING,
                required=True
            ),
            openapi.Parameter(
                'product_id',
                openapi.IN_QUERY,
                description='Product ID to update in cart',
                type=openapi.TYPE_STRING,
                required=True
            ),
        ],
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            properties={
                'action': openapi.Schema(type=openapi.TYPE_STRING, description='Action to perform: increase or decrease', enum=['increase', 'decrease']),
            },
            required=['action']
        ),
        responses={
            200: openapi.Response(
                description='Cart item updated successfully',
                examples={
                    'application/json': {
                        'message': 'Item quantity updated',
                        'data': {
                            'cart_id': 'string',
                            'quantity': 'integer'
                        }
                    }
                }
            ),
            400: openapi.Response(
                description='Bad request - missing parameters or invalid action',
                examples={
                    'application/json': {
                        'error': 'user_id, business_id, product_id, and action are required.'
                    }
                }
            ),
            404: openapi.Response(
                description='Product not found in cart',
                examples={
                    'application/json': {
                        'error': 'Product not found in cart.'
                    }
                }
            )
        }
    )
    def patch(self, request, *args, **kwargs):
        user_id = request.query_params.get('user_id')
        business_id = request.query_params.get('business_id')
        product_id = request.query_params.get('product_id')
        action = request.data.get('action')

        if not all([user_id, business_id, product_id, action]):
            return Response({"error": "user_id, business_id, product_id, and action are required."}, status=status.HTTP_400_BAD_REQUEST)

        if action not in ['increase', 'decrease']:
            return Response({"error": "Invalid action. Must be 'increase' or 'decrease'."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            cart_item = GroceriesCart.objects.get(user_id=user_id, business_id=business_id, product_id=product_id)
            product_name = cart_item.product.product_name
            if action == 'increase':
                cart_item.quantity += 1
                cart_item.save()
                message = f"'{product_name}' quantity increased to {cart_item.quantity}."
            elif action == 'decrease':
                if cart_item.quantity > 1:
                    cart_item.quantity -= 1
                    cart_item.save()
                    message = f"'{product_name}' quantity decreased to {cart_item.quantity}."
                else:
                    cart_item.delete()
                    return Response({"message": f"'{product_name}' has been removed from your cart."}, status=status.HTTP_200_OK)
            
            serializer = GroceriesCartSerializer(cart_item)
            response_data = {
                "message": message,
                "data": serializer.data
            }
            return Response(response_data, status=status.HTTP_200_OK)
        except GroceriesCart.DoesNotExist:
            return Response({"error": "Product not found in cart."}, status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    @swagger_auto_schema(
        tags=['grocery'],
        manual_parameters=[
            openapi.Parameter(
                'user_id',
                openapi.IN_QUERY,
                description='User ID deleting cart item',
                type=openapi.TYPE_STRING,
                required=True
            ),
            openapi.Parameter(
                'business_id',
                openapi.IN_QUERY,
                description='Business ID for the cart item',
                type=openapi.TYPE_STRING,
                required=True
            ),
            openapi.Parameter(
                'product_id',
                openapi.IN_QUERY,
                description='Product ID to remove from cart',
                type=openapi.TYPE_STRING,
                required=True
            ),
        ],
        responses={
            200: openapi.Response(
                description='Cart item removed successfully',
                examples={
                    'application/json': {
                        'message': 'Product has been removed from your cart.'
                    }
                }
            ),
            400: openapi.Response(
                description='Bad request - missing parameters',
                examples={
                    'application/json': {
                        'error': 'user_id, business_id, and product_id are required.'
                    }
                }
            ),
            404: openapi.Response(
                description='Product not found in cart',
                examples={
                    'application/json': {
                        'error': 'Product not found in cart.'
                    }
                }
            )
        }
    )
    def delete(self, request, *args, **kwargs):
        user_id = request.query_params.get('user_id')
        business_id = request.query_params.get('business_id')
        product_id = request.query_params.get('product_id')

        if not all([user_id, business_id, product_id]):
            return Response({"error": "user_id, business_id, and product_id are required."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            cart_item = GroceriesCart.objects.get(user_id=user_id, business_id=business_id, product_id=product_id)
            product_name = cart_item.product.product_name
            cart_item.delete()
            return Response({"message": f"'{product_name}' has been removed from your cart."}, status=status.HTTP_200_OK)
        except GroceriesCart.DoesNotExist:
            return Response({"error": "Product not found in cart."}, status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@swagger_auto_schema(tags=['Consumer'])
class CreatePaymentView(APIView):
    """
    API view to create a Razorpay order for a grocery payment.
    """
    @swagger_auto_schema(
        tags=['grocery'],
        manual_parameters=[
            openapi.Parameter(
                'user_id',
                openapi.IN_QUERY,
                description='User ID creating the payment',
                type=openapi.TYPE_STRING,
                required=True
            ),
            openapi.Parameter(
                'business_id',
                openapi.IN_QUERY,
                description='Business ID for the payment',
                type=openapi.TYPE_STRING,
                required=True
            ),
        ],
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            properties={
                'order_id': openapi.Schema(type=openapi.TYPE_STRING, description='Order ID to create payment for'),
            },
            required=['order_id']
        ),
        responses={
            201: openapi.Response(
                description='Razorpay order created successfully',
                examples={
                    'application/json': {
                        'message': 'Razorpay order created successfully.',
                        'razorpay_order_id': 'string',
                        'amount': 'integer',
                        'currency': 'string'
                    }
                }
            ),
            400: openapi.Response(
                description='Bad request - missing parameters or order already paid',
                examples={
                    'application/json': {
                        'error': 'user_id and business_id are required in query parameters.'
                    }
                }
            ),
            404: openapi.Response(
                description='Order not found',
                examples={
                    'application/json': {
                        'error': 'Order not found.'
                    }
                }
            )
        }
    )
    def post(self, request, *args, **kwargs):
        user_id = request.query_params.get('user_id')
        business_id = request.query_params.get('business_id')

        if not all([user_id, business_id]):
            return Response({"error": "user_id and business_id are required in query parameters."}, status=status.HTTP_400_BAD_REQUEST)

        order_id = request.data.get('order_id')
        if not order_id:
            return Response({"error": "order_id is required."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            order = GroceriesOrders.objects.get(order_id=order_id, user_id=user_id, business_id=business_id)
        except GroceriesOrders.DoesNotExist:
            return Response({"error": "Order not found."}, status=status.HTTP_404_NOT_FOUND)

        if order.payment_status == 'paid':
            return Response({"message": "This order has already been paid."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            client = razorpay.Client(auth=(settings.RKSUPERMARKET_RAZORPAY_KEY_ID, settings.RKSUPERMARKET_RAZORPAY_KEY_SECRET))
            # Round the amount before converting to paise to ensure whole number (JavaScript Math.round() behavior: 12.50→13, 12.55→13)
            rounded_amount = math.floor(float(order.final_amount) + 0.5)
            razorpay_order = client.order.create({
                "amount": int(rounded_amount * 100),  # Amount in paise (rounded)
                "currency": "INR",
                "receipt": f"order_rcptid_{order.order_id}",
                "payment_capture": 1
            })


            response_data = {
                "message": "Razorpay order created successfully.",
                "razorpay_order_id": razorpay_order['id'],
                "amount": razorpay_order['amount'],
                "currency": razorpay_order['currency']
            }
            return Response(response_data, status=status.HTTP_201_CREATED)

        except Exception as e:
            logger.error(f"Error creating Razorpay order: {str(e)}")
            return Response({"error": f"Failed to create payment order: {str(e)}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@swagger_auto_schema(tags=['Consumer'])
class VerifyPaymentView(APIView):
    """
    API view to verify a Razorpay payment.
    """
    def post(self, request, *args, **kwargs):
        # Get user_id and business_id from query params
        user_id = request.query_params.get('user_id')
        business_id = request.query_params.get('business_id')
        
        if not all([user_id, business_id]):
            return Response(
                {"error": "Both user_id and business_id are required in query parameters"}, 
                status=status.HTTP_400_BAD_REQUEST
            )
            
        serializer = RazorpayPaymentVerificationSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        data = serializer.validated_data
        razorpay_order_id = data['razorpay_order_id']
        razorpay_payment_id = data['razorpay_payment_id']
        razorpay_signature = data['razorpay_signature']
        order_id = data.get('order_id')

        if not order_id:
            return Response(
                {"error": "order_id is required in the request data"}, 
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            order = GroceriesOrders.objects.get(
                order_id=order_id,
                user_id=user_id,
                business_id=business_id
            )
        except GroceriesOrders.DoesNotExist:
            return Response({"error": "Order not found."}, status=status.HTTP_404_NOT_FOUND)

        # Prevent verifying a cancelled or already paid order
        if str(order.payment_status).lower() == 'cancelled':
            return Response({
                "error": "This order's payment was cancelled. Please create a new order to pay again."
            }, status=status.HTTP_400_BAD_REQUEST)
        if str(order.payment_status).lower() == 'paid':
            return Response({
                "error": "Payment already completed for this order."
            }, status=status.HTTP_400_BAD_REQUEST)

        client = razorpay.Client(auth=(settings.RKSUPERMARKET_RAZORPAY_KEY_ID, settings.RKSUPERMARKET_RAZORPAY_KEY_SECRET))

        try:
            client.utility.verify_payment_signature({
                'razorpay_order_id': razorpay_order_id,
                'razorpay_payment_id': razorpay_payment_id,
                'razorpay_signature': razorpay_signature
            })

            with transaction.atomic():
                payment = GroceriesPayments.objects.create(
                    order=order,
                    user_id=order.user_id,
                    amount=order.final_amount,
                    payment_method='razorpay',
                    payment_status='completed',
                    transaction_id=razorpay_payment_id
                )
                order.payment_status = 'paid'
                order.save()

            # After successful payment, send WhatsApp order summary (best-effort)
            whatsapp_summary = None
            try:
                # Allow frontend to pass fallback phone to ensure delivery
                phone_override = None
                try:
                    req_data = request.data if isinstance(request.data, dict) else {}
                    ph = (req_data.get('phone_number') or req_data.get('phone') or '').strip()
                    cc = (req_data.get('country_code') or '+91').strip() if ph else None
                    customer_name = (req_data.get('customer_name') or '').strip() or None
                    # Optional responsive layout hints from frontend
                    wh_layout = (req_data.get('wh_summary_layout') or '').strip().lower() or None
                    wh_max_items = req_data.get('wh_summary_max_items')
                    try:
                        wh_max_items = int(wh_max_items) if wh_max_items not in (None, '', []) else None
                    except Exception:
                        wh_max_items = None
                    # If no explicit layout, infer from screen width if provided
                    if not wh_layout:
                        try:
                            sw = req_data.get('screen_width')
                            sw = int(sw) if sw not in (None, '', []) else 0
                        except Exception:
                            sw = 0
                        if 320 <= sw <= 430:
                            wh_layout = 'list'
                            if wh_max_items is None:
                                wh_max_items = 2 if sw < 360 else 3
                    if ph:
                        phone_override = {"countryCode": cc, "phoneNumber": ph}
                except Exception:
                    phone_override = None

                whatsapp_summary = send_order_summary_message(
                    order,
                    override_contact=phone_override,
                    override_customer_name=customer_name,
                    override_layout_mode=wh_layout,
                    override_max_items=wh_max_items,
                )
            except Exception as wa_err:
                logger.error(f"Failed to send WhatsApp order summary after payment for order {order.order_id}: {wa_err}")

            return Response({
                "message": "Payment verified and completed successfully.",
                "whatsapp_notification": {"order_summary": whatsapp_summary}
            }, status=status.HTTP_200_OK)

        except razorpay.errors.SignatureVerificationError as e:
            logger.error(f"Razorpay signature verification failed: {e}")
            return Response({"error": "Payment verification failed."}, status=status.HTTP_400_BAD_REQUEST)


@swagger_auto_schema(tags=['Consumer'])
class CancelPaymentView(APIView):
    """API view to cancel a payment attempt and update order/payment status to cancelled."""
    def post(self, request, *args, **kwargs):
        # Query params for context
        user_id = request.query_params.get('user_id')
        business_id = request.query_params.get('business_id')

        if not all([user_id, business_id]):
            return Response(
                {"error": "Both user_id and business_id are required in query parameters"},
                status=status.HTTP_400_BAD_REQUEST
            )

        serializer = CancelPaymentSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        order_id = serializer.validated_data['order_id']
        payment_method = serializer.validated_data.get('payment_method', 'razorpay')
        reason = serializer.validated_data.get('reason', '')

        try:
            order = GroceriesOrders.objects.get(
                order_id=order_id,
                user_id=user_id,
                business_id=business_id
            )
        except GroceriesOrders.DoesNotExist:
            return Response({"error": "Order not found."}, status=status.HTTP_404_NOT_FOUND)

        # If already paid, do not allow cancellation
        if str(order.payment_status).lower() == 'paid':
            return Response(
                {"error": "Payment already completed for this order and cannot be cancelled."},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            with transaction.atomic():
                # Force update existing non-completed payments for this order
                updated_count = (
                    GroceriesPayments.objects
                    .filter(order=order, user_id=order.user_id)
                    .exclude(payment_status='completed')
                    .update(payment_status='cancelled', payment_method=payment_method)
                )

                # If no existing records were updated, create a cancellation record for traceability
                if updated_count == 0:
                    GroceriesPayments.objects.create(
                        order=order,
                        user_id=order.user_id,
                        amount=order.final_amount,
                        payment_method=payment_method,
                        payment_status='cancelled',
                        transaction_id=(f"cancelled:{reason[:230]}" if reason else None),
                    )
                else:
                    # Optionally add reason to empty transaction_id entries
                    if reason:
                        GroceriesPayments.objects.filter(
                            order=order,
                            user_id=order.user_id,
                            transaction_id__isnull=True
                        ).exclude(payment_status='completed').update(
                            transaction_id=f"cancelled:{reason[:230]}"
                        )

                # Update order payment status to cancelled (idempotent)
                order.payment_status = 'cancelled'
                order.save(update_fields=['payment_status'])

            return Response({
                "message": "Payment cancelled successfully.",
                "order_id": order.order_id,
                "payment_status": "cancelled"
            }, status=status.HTTP_200_OK)

        except Exception as e:
            logger.error(f"Error cancelling payment for order {order_id}: {str(e)}")
            return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

@swagger_auto_schema(tags=['Consumer'])
class OrderDetailsView(APIView):
    """
    API view to fetch order details based on user_id and business_id.
    Optionally filters by order_type if provided.
    """
    def get(self, request, *args, **kwargs):
        user_id = request.query_params.get('user_id')
        business_id = request.query_params.get('business_id')
        order_type = request.query_params.get('order_type')

        if not all([user_id, business_id]):
            return Response({"error": "user_id and business_id are required."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            filters = {
                'user_id': user_id,
                'business_id': business_id
            }
            if order_type:
                filters['order_type'] = order_type

            # Optimize query with prefetch_related to avoid N+1 queries for order items and product variants
            orders = GroceriesOrders.objects.filter(**filters).prefetch_related(
                'groceriesorderitems_set__product__groceriesproductvariants_set',
                'groceriesorderitems_set__product__category',
                'groceriesorderitems_set__product__business',
                'groceriespayments_set'
            ).order_by('-created_at')

            if not orders.exists():
                return Response({"message": "No orders found for the given criteria."}, status=status.HTTP_404_NOT_FOUND)

            serializer = GroceriesOrdersSerializer(orders, many=True)
            return Response(serializer.data, status=status.HTTP_200_OK)

        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@swagger_auto_schema(tags=['Consumer'])
class HighRatedProductsView(APIView):
    """
    API view to fetch products with rating greater than 3.
    Uses GET method with business_id as query parameter.
    """
    def get(self, request, *args, **kwargs):
        """
        Handles GET requests to fetch products with rating > 3 for a given business ID.
        """
        business_id = request.query_params.get('business_id')
        if not business_id:
            return Response({"error": "business_id parameter is required."}, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            # Fetch products with rating > 3 using the new model structure with pricing from variants
            products = GroceriesProducts.objects.select_related('category', 'business').prefetch_related(
                'groceriesproductvariants_set'
            ).filter(
                business_id=business_id,
                rating__gt=3.0
            ).order_by('-rating', 'product_name')[:10]
            
            if not products.exists():
                return Response({
                    "message": "No products found with rating greater than 3 for this business.",
                    "business_id": business_id,
                    "products": []
                }, status=status.HTTP_200_OK)
            
            serializer = GroceriesProductWithPricingSerializer(products, many=True, context={'request': request})
            
            return Response({
                "message": "High-rated products fetched successfully.",
                "business_id": business_id,
                "total_products": len(serializer.data),
                "products": serializer.data
            }, status=status.HTTP_200_OK)
            
        except Exception as e:
            logger.error(f"Error fetching high-rated products: {str(e)}")
            return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@swagger_auto_schema(tags=['Consumer'])
class DiscountedProductsView(APIView):
    """
    API view to fetch products that have at least one active variant discounted between
    min_discount and max_discount percent (inclusive). Defaults to 10–14% off.

    Query params:
      - business_id: required
      - min_discount: optional (default 10)
      - max_discount: optional (default 14)
      - limit: optional (default 20)
      - offset: optional (default 0)
    """
    def get(self, request, *args, **kwargs):
        business_id = request.query_params.get('business_id')
        if not business_id:
            return Response({"error": "business_id parameter is required."}, status=status.HTTP_400_BAD_REQUEST)

        # Parse and validate discount bounds
        try:
            min_discount = request.query_params.get('min_discount', '10')
            max_discount = request.query_params.get('max_discount', '14')
            min_discount = Decimal(str(min_discount))
            max_discount = Decimal(str(max_discount))
            if min_discount < 0 or max_discount > 100 or min_discount > max_discount:
                raise ValueError
        except (InvalidOperation, ValueError):
            return Response({
                "error": "Invalid min_discount/max_discount. Provide numbers 0-100 with min <= max."
            }, status=status.HTTP_400_BAD_REQUEST)

        # Pagination
        try:
            limit = int(request.query_params.get('limit', 20))
            offset = int(request.query_params.get('offset', 0))
            if limit < 1:
                limit = 20
            if offset < 0:
                offset = 0
        except ValueError:
            return Response({"error": "Invalid limit/offset."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            # Compute selling price range using ratios to avoid division in the DB
            # discount% = (original - selling)/original * 100
            # -> selling/original in [1 - max/100, 1 - min/100]
            one = Decimal('1')
            lower_ratio = one - (max_discount / Decimal('100'))  # selling >= original * lower_ratio
            upper_ratio = one - (min_discount / Decimal('100'))  # selling <= original * upper_ratio

            # Find variants that match the discount range
            matching_variants = GroceriesProductVariants.objects.filter(
                product__business_id=business_id,
                is_active=True,
                original_cost__gt=0,
                selling_price__gt=0,
                selling_price__gte=F('original_cost') * lower_ratio,
                selling_price__lte=F('original_cost') * upper_ratio,
            ).values_list('product_id', 'variant_id')

            product_to_variants = {}
            for pid, vid in matching_variants:
                product_to_variants.setdefault(pid, []).append(vid)

            if not product_to_variants:
                return Response({
                    "message": "No products found in the requested discount range.",
                    "business_id": business_id,
                    "min_discount": float(min_discount),
                    "max_discount": float(max_discount),
                    "total_products": 0,
                    "products": []
                }, status=status.HTTP_200_OK)

            product_ids = list(product_to_variants.keys())

            # Fetch products and serialize with pricing/variants
            products_qs = GroceriesProducts.objects.select_related('category', 'business').prefetch_related(
                'groceriesproductvariants_set'
            ).filter(
                business_id=business_id,
                product_id__in=product_ids
            ).order_by('product_name')

            total_count = products_qs.count()
            products_qs = products_qs[offset:offset + limit]

            serializer = GroceriesProductWithPricingSerializer(products_qs, many=True, context={'request': request})
            data = serializer.data

            # Enrich with matching variant IDs and compute an offer percent per product
            # Offer percent is computed as the maximum discount among the matching variants
            for item in data:
                pid = item.get('product_id')
                matching_ids = set(product_to_variants.get(pid, []))
                item['matching_variant_ids'] = list(matching_ids)

                # Compute per-variant discount fields for display
                for v in item.get('variants', []) or []:
                    try:
                        oc = v.get('original_cost')
                        sp = v.get('selling_price')
                        if oc is not None and sp is not None and float(oc) > 0:
                            disc = (float(oc) - float(sp)) / float(oc) * 100.0
                            v['discount_percent'] = round(disc, 2)
                            v['discount_text'] = f"{math.floor(disc)}% OFF"
                        else:
                            v['discount_percent'] = 0.0
                            v['discount_text'] = None
                    except Exception:
                        v['discount_percent'] = None
                        v['discount_text'] = None

                best_discount = None
                for v in item.get('variants', []) or []:
                    try:
                        if v.get('variant_id') in matching_ids:
                            oc = v.get('original_cost')
                            sp = v.get('selling_price')
                            if oc and sp and float(oc) > 0:
                                d = (float(oc) - float(sp)) / float(oc) * 100.0
                                best_discount = d if best_discount is None else max(best_discount, d)
                    except Exception:
                        # Skip malformed variant entries gracefully
                        continue

                if best_discount is not None:
                    # Keep precise percent and a human-friendly text (floor to avoid over-promising)
                    item['offer_percent'] = round(float(best_discount), 2)
                    try:
                        item['offer_text'] = f"{math.floor(best_discount)}% OFF"
                    except Exception:
                        item['offer_text'] = f"{int(best_discount)}% OFF"

            return Response({
                "message": "Discounted products fetched successfully.",
                "business_id": business_id,
                "min_discount": float(min_discount),
                "max_discount": float(max_discount),
                "limit": limit,
                "offset": offset,
                "total_products": total_count,
                "products": data
            }, status=status.HTTP_200_OK)

        except Exception as e:
            logger.error(f"Error fetching discounted products: {str(e)}")
            return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@swagger_auto_schema(tags=['Consumer'])
class TopSellingItemsByCategoryView(APIView):
    """
    API view to fetch top-selling products by quantity for each category.
    GET params:
      - business_id: required
      - limit: optional, top-N per category (default: 5)
    Only includes orders with payment_status = 'paid'.
    """
    def get(self, request, *args, **kwargs):
        business_id = request.query_params.get('business_id')
        per_category_limit = int(request.query_params.get('limit', 5))

        if not business_id:
            return Response({"error": "business_id parameter is required."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            # 1) Aggregate sales per product by category (paid orders only)
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT 
                        gc.category_name AS category,
                        gp.product_id,
                        COALESCE(SUM(goi.quantity), 0) AS total_quantity_sold,
                        COALESCE(SUM(goi.total_price), 0) AS total_revenue
                    FROM Groceries_order_items goi
                    INNER JOIN Groceries_orders go ON go.order_id = goi.order_id
                    INNER JOIN Groceries_Products gp ON gp.product_id = goi.product_id
                    INNER JOIN Groceries_Categories gc ON gc.category_id = gp.category_id
                    WHERE go.business_id = %s
                      AND gp.business_id = %s
                      AND LOWER(go.payment_status) = 'paid'
                    GROUP BY gc.category_name, gp.product_id
                    ORDER BY gc.category_name ASC, total_quantity_sold DESC
                    """,
                    [business_id, business_id]
                )

                columns = [col[0] for col in cursor.description]
                rows = [dict(zip(columns, row)) for row in cursor.fetchall()]

            # 2) Group rows by category, slice top-N, and collect product_ids to fetch details
            grouped = {}
            for r in rows:
                cat = r.get('category') or 'Uncategorized'
                grouped.setdefault(cat, []).append(r)

            # Build per-category limited lists and collect product_ids
            limited_by_category = {}
            top_product_ids = []
            for cat, product_rows in grouped.items():
                top_rows = product_rows[:per_category_limit]
                limited_by_category[cat] = top_rows
                top_product_ids.extend([r['product_id'] for r in top_rows])

            # 3) Fetch full product details for the selected product_ids with pricing from variants
            product_details_map = {}
            if top_product_ids:
                products = GroceriesProducts.objects.select_related('category', 'business').prefetch_related(
                    'groceriesproductvariants_set'
                ).filter(
                    product_id__in=top_product_ids,
                    business_id=business_id
                )
                serializer = GroceriesProductWithPricingSerializer(products, many=True, context={'request': request})
                for product_data in serializer.data:
                    product_details_map[product_data['product_id']] = product_data

            # 4) Build final response merging aggregates + full details
            results = []
            for cat, top_rows in limited_by_category.items():
                items_out = []
                for r in top_rows:
                    product_id = r['product_id']
                    details = product_details_map.get(product_id, {})
                    items_out.append({
                        "product_id": product_id,
                        "total_quantity_sold": int(r.get('total_quantity_sold') or 0),
                        "total_revenue": float(r.get('total_revenue') or 0.0),
                        "product": details  # Full product details
                    })
                results.append({
                    "category": cat,
                    "top_items": items_out,
                    "total_items_with_sales": len(grouped.get(cat, []))
                })

            return Response({
                "business_id": business_id,
                "per_category_limit": per_category_limit,
                "total_categories": len(results),
                "results": results
            }, status=status.HTTP_200_OK)

        except Exception as e:
            logger.error(f"Error fetching top-selling items by category: {str(e)}")
            return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@swagger_auto_schema(tags=['Consumer'])
class TopSellingOverallView(APIView):
    """
    API view to fetch overall top-selling products (not grouped by category).
    GET params:
      - business_id: required
      - limit: optional, top-N overall (default: 10)
      - sort_by: optional, 'quantity' (default) or 'revenue'
    Only includes orders with payment_status = 'paid'.
    """
    def get(self, request, *args, **kwargs):
        business_id = request.query_params.get('business_id')
        limit = int(request.query_params.get('limit', 10))
        sort_by = (request.query_params.get('sort_by') or 'quantity').strip().lower()
        if sort_by not in ('quantity', 'revenue'):
            sort_by = 'quantity'

        if not business_id:
            return Response({"error": "business_id parameter is required."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            # 1) Aggregate sales per product across all categories (paid orders only)
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT 
                        gp.product_id,
                        COALESCE(SUM(goi.quantity), 0) AS total_quantity_sold,
                        COALESCE(SUM(goi.total_price), 0) AS total_revenue
                    FROM Groceries_order_items goi
                    INNER JOIN Groceries_orders go ON go.order_id = goi.order_id
                    INNER JOIN Groceries_Products gp ON gp.product_id = goi.product_id
                    WHERE go.business_id = %s
                      AND gp.business_id = %s
                      AND LOWER(go.payment_status) = 'paid'
                    GROUP BY gp.product_id
                    """,
                    [business_id, business_id]
                )

                cols = [c[0] for c in cursor.description]
                rows = [dict(zip(cols, row)) for row in cursor.fetchall()]

            # 2) Sort rows in Python to safely apply limit without injecting into SQL
            if sort_by == 'revenue':
                rows.sort(key=lambda r: float(r.get('total_revenue') or 0.0), reverse=True)
            else:
                rows.sort(key=lambda r: int(r.get('total_quantity_sold') or 0), reverse=True)

            top_rows = rows[:limit]

            # 3) Fetch full product details for these product_ids with pricing from variants
            product_details_map = {}
            if top_rows:
                top_product_ids = [r['product_id'] for r in top_rows]
                products = GroceriesProducts.objects.select_related('category', 'business').prefetch_related(
                    'groceriesproductvariants_set'
                ).filter(
                    product_id__in=top_product_ids,
                    business_id=business_id
                )
                serializer = GroceriesProductWithPricingSerializer(products, many=True, context={'request': request})
                for product_data in serializer.data:
                    product_details_map[product_data['product_id']] = product_data

            # 4) Build final response
            results = []
            for r in top_rows:
                product_id = r['product_id']
                results.append({
                    "product_id": product_id,
                    "total_quantity_sold": int(r.get('total_quantity_sold') or 0),
                    "total_revenue": float(r.get('total_revenue') or 0.0),
                    "product": product_details_map.get(product_id, {})
                })

            return Response({
                "business_id": business_id,
                "limit": limit,
                "sort_by": sort_by,
                "total_items": len(results),
                "results": results
            }, status=status.HTTP_200_OK)

        except Exception as e:
            logger.error(f"Error fetching overall top-selling items: {str(e)}")
            return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

@swagger_auto_schema(tags=['Consumer'])
class GroceryPartnerRegistrationView(APIView):
    """
    API view for grocery partner registration.
    Handles partner registration with user_id and business_id from URL parameters.
    """
    
    def get(self, request, *args, **kwargs):
        """
        Get partner details if already registered, or return form structure.
        """
        user_id = request.query_params.get('user_id')
        business_id = request.query_params.get('business_id')
        
        if not all([user_id, business_id]):
            return Response({
                "error": "user_id and business_id are required parameters."
            }, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            # Check if user exists
            user = Registration.objects.get(user_id=user_id)
            business = Business.objects.get(business_id=business_id)
            
            # Check if partner already exists
            try:
                partner = GroceryPartner.objects.get(user_id=user_id)
                serializer = GroceryPartnerSerializer(partner)
                return Response({
                    "message": "Partner already registered.",
                    "partner_data": serializer.data,
                    "is_registered": True
                }, status=status.HTTP_200_OK)
            except GroceryPartner.DoesNotExist:
                # Return form structure for new registration
                return Response({
                    "message": "Partner not registered. Please fill the registration form.",
                    "is_registered": False,
                    "user_info": {
                        "user_id": user.user_id,
                        "name": f"{user.firstName} {user.lastName}",
                        "email": user.email,
                        "phone": user.phone_number
                    },
                    "business_info": {
                        "business_id": business.business_id,
                        "business_name": business.business_name
                    },
                    "form_fields": {
                        "vehicle_number": {"type": "text", "required": True, "max_length": 20},
                        "vehicle_type": {
                            "type": "select", 
                            "required": True,
                            "choices": [
                                {"value": "bike", "label": "Bike"},
                                {"value": "scooter", "label": "Scooter"},
                                {"value": "car", "label": "Car"},
                                {"value": "van", "label": "Van"},
                                {"value": "truck", "label": "Truck"},
                                {"value": "bicycle", "label": "Bicycle"},
                                {"value": "auto", "label": "Auto Rickshaw"}
                            ]
                        },
                        "driving_license_number": {"type": "text", "required": True, "max_length": 20},
                        "aadhar_card_number": {"type": "text", "required": True, "max_length": 12},
                        "bank_account_number": {"type": "text", "required": False, "max_length": 20},
                        "bank_ifsc_code": {"type": "text", "required": False, "max_length": 11},
                        "bank_account_holder_name": {"type": "text", "required": False, "max_length": 100},
                        "emergency_contact_name": {"type": "text", "required": False, "max_length": 100},
                        "emergency_contact_phone": {"type": "text", "required": False, "max_length": 15},
                        "delivery_zones": {"type": "array", "required": False, "description": "List of delivery area codes"}
                    }
                }, status=status.HTTP_200_OK)
                
        except Registration.DoesNotExist:
            return Response({
                "error": "User not found."
            }, status=status.HTTP_404_NOT_FOUND)
        except Business.DoesNotExist:
            return Response({
                "error": "Business not found."
            }, status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            logger.error(f"Error in partner registration GET: {str(e)}")
            return Response({
                "error": str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    
    def post(self, request, *args, **kwargs):
        """
        Register a new grocery partner.
        """
        user_id = request.query_params.get('user_id')
        business_id = request.query_params.get('business_id')
        
        if not all([user_id, business_id]):
            return Response({
                "error": "user_id and business_id are required parameters."
            }, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            # Validate user and business exist
            user = Registration.objects.get(user_id=user_id)
            business = Business.objects.get(business_id=business_id)
            
            # Check if partner already exists
            if GroceryPartner.objects.filter(user_id=user_id).exists():
                return Response({
                    "error": "Partner already registered for this user."
                }, status=status.HTTP_400_BAD_REQUEST)
            
            # Validate form data
            serializer = GroceryPartnerRegistrationSerializer(data=request.data)
            if not serializer.is_valid():
                return Response({
                    "error": "Validation failed.",
                    "details": serializer.errors
                }, status=status.HTTP_400_BAD_REQUEST)
            
            # Create partner with atomic transaction
            with transaction.atomic():
                partner_data = serializer.validated_data
                
                # Debug: Log the business object
                logger.info(f"Business object: {business}, Business ID: {business.business_id}")
                
                partner = GroceryPartner(
                    user=user,
                    business=business,
                    vehicle_number=partner_data['vehicle_number'],
                    vehicle_type=partner_data['vehicle_type'],
                    driving_license_number=partner_data['driving_license_number'],
                    aadhar_card_number=partner_data['aadhar_card_number'],
                    bank_account_number=partner_data.get('bank_account_number'),
                    bank_ifsc_code=partner_data.get('bank_ifsc_code'),
                    bank_account_holder_name=partner_data.get('bank_account_holder_name'),
                    emergency_contact_name=partner_data.get('emergency_contact_name'),
                    emergency_contact_phone=partner_data.get('emergency_contact_phone'),
                    delivery_zones=partner_data.get('delivery_zones'),
                    joined_date=date.today(),
                    is_active=True,
                    availability_status='offline'
                )
                partner.save()
                
                # Debug: Check if business_id was saved
                logger.info(f"Saved partner business: {partner.business}, Business ID: {partner.business.business_id if partner.business else 'None'}")
                
                # Debug: Check the actual database value with raw SQL
                with connection.cursor() as cursor:
                    cursor.execute("SELECT business_id FROM Grocery_partner WHERE user_id = %s", [partner.user_id])
                    result = cursor.fetchone()
                    logger.info(f"Raw database business_id value: {result[0] if result else 'None'}")
                    
                    # If business_id is still null/0, try direct SQL update
                    if not result[0] or result[0] == 0:
                        logger.info(f"Attempting direct SQL update with business_id: {business.business_id}")
                        cursor.execute(
                            "UPDATE Grocery_partner SET business_id = %s WHERE user_id = %s", 
                            [business.business_id, partner.user_id]
                        )
                        # Verify the update
                        cursor.execute("SELECT business_id FROM Grocery_partner WHERE user_id = %s", [partner.user_id])
                        updated_result = cursor.fetchone()
                        logger.info(f"After direct SQL update - business_id: {updated_result[0] if updated_result else 'None'}")
                
                # Return success response
                response_serializer = GroceryPartnerSerializer(partner)
                return Response({
                    "message": "Partner registered successfully! Your application is under review.",
                    "partner_data": response_serializer.data,
                    "next_steps": [
                        "Your registration is under review by the admin.",
                        "You will be notified once your account is verified.",
                        "After verification, you can start accepting delivery orders."
                    ]
                }, status=status.HTTP_201_CREATED)
                
        except Registration.DoesNotExist:
            return Response({
                "error": "User not found."
            }, status=status.HTTP_404_NOT_FOUND)
        except Business.DoesNotExist:
            return Response({
                "error": "Business not found."
            }, status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            logger.error(f"Error in partner registration POST: {str(e)}")
            return Response({
                "error": str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    
    def put(self, request, *args, **kwargs):
        """
        Update existing partner details.
        """
        user_id = request.query_params.get('user_id')
        business_id = request.query_params.get('business_id')
        
        if not all([user_id, business_id]):
            return Response({
                "error": "user_id and business_id are required parameters."
            }, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            partner = GroceryPartner.objects.get(user_id=user_id, business_id=business_id)
            
            # Validate updated data
            serializer = GroceryPartnerRegistrationSerializer(
                partner, 
                data=request.data, 
                partial=True
            )
            if not serializer.is_valid():
                return Response({
                    "error": "Validation failed.",
                    "details": serializer.errors
                }, status=status.HTTP_400_BAD_REQUEST)
            
            # Update partner
            serializer.save()
            
            # Return updated data
            response_serializer = GroceryPartnerSerializer(partner)
            return Response({
                "message": "Partner details updated successfully.",
                "partner_data": response_serializer.data
            }, status=status.HTTP_200_OK)
            
        except GroceryPartner.DoesNotExist:
            return Response({
                "error": "Partner not found."
            }, status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            logger.error(f"Error in partner registration PUT: {str(e)}")
            return Response({
                "error": str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@swagger_auto_schema(tags=['Consumer'])
class BusinessOrdersView(APIView):
    """
    API view to get orders by business ID and order type with detailed order items.
    Supports filtering by order_type, order_status, and date range.
    Always returns only paid orders (payment_status='paid') checked on the orders table.
    """
    
    def get(self, request, *args, **kwargs):
        """
        Get orders for a specific business with optional filtering.
        Query parameters:
        - business_id (required): Business ID to filter orders
        - order_type (optional): Filter by order type (pickup/delivery)
        - order_status (optional): Filter by order status
        - start_date (optional): Filter orders from this date (YYYY-MM-DD)
        - end_date (optional): Filter orders until this date (YYYY-MM-DD)
        - limit (optional): Number of orders to return (default: 50)
        - offset (optional): Number of orders to skip (default: 0)
        - Note: Only paid orders are returned (payment_status='paid').
        """
        business_id = request.query_params.get('business_id')
        if not business_id:
            return Response({
                "error": "business_id parameter is required."
            }, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            # Validate business exists
            try:
                Business.objects.get(business_id=business_id)
            except Business.DoesNotExist:
                return Response({
                    "error": "Business not found."
                }, status=status.HTTP_404_NOT_FOUND)
            
            # Build filters
            filters = {'business_id': business_id}
            
            # Add mandatory filter for paid orders only
            filters['payment_status'] = 'paid'
            
            # Optional filters
            order_type = request.query_params.get('order_type')
            if order_type:
                if order_type not in ['pickup', 'delivery']:
                    return Response({
                        "error": "Invalid order_type. Must be 'pickup' or 'delivery'."
                    }, status=status.HTTP_400_BAD_REQUEST)
                filters['order_type'] = order_type
            
            order_status = request.query_params.get('order_status')
            if order_status:
                valid_statuses = ['pending', 'confirmed', 'shipped', 'delivered', 'cancelled']
                if order_status not in valid_statuses:
                    return Response({
                        "error": f"Invalid order_status. Must be one of: {', '.join(valid_statuses)}"
                    }, status=status.HTTP_400_BAD_REQUEST)
                filters['order_status'] = order_status
            
            # Only paid orders are returned (enforced via filters['payment_status']
            # and WHERE clause "o.payment_status = 'paid'" on the orders table)
            
            # Date range filtering
            start_date = request.query_params.get('start_date')
            end_date = request.query_params.get('end_date')
            
            if start_date:
                try:
                    from datetime import datetime
                    start_date_obj = datetime.strptime(start_date, '%Y-%m-%d').date()
                    filters['created_at__date__gte'] = start_date_obj
                except ValueError:
                    return Response({
                        "error": "Invalid start_date format. Use YYYY-MM-DD."
                    }, status=status.HTTP_400_BAD_REQUEST)
            
            if end_date:
                try:
                    from datetime import datetime
                    end_date_obj = datetime.strptime(end_date, '%Y-%m-%d').date()
                    filters['created_at__date__lte'] = end_date_obj
                except ValueError:
                    return Response({
                        "error": "Invalid end_date format. Use YYYY-MM-DD."
                    }, status=status.HTTP_400_BAD_REQUEST)
            
            # Pagination parameters
            try:
                limit = int(request.query_params.get('limit', 50))
                offset = int(request.query_params.get('offset', 0))
                if limit < 1 or limit > 100:
                    limit = 50
                if offset < 0:
                    offset = 0
            except ValueError:
                return Response({
                    "error": "Invalid limit or offset values. Must be integers."
                }, status=status.HTTP_400_BAD_REQUEST)
            
            # Use raw SQL to get orders with all details
            with connection.cursor() as cursor:
                # Build WHERE clause dynamically
                where_conditions = ["o.business_id = %s", "o.payment_status = 'paid'"]
                params = [business_id]
                
                if order_type:
                    where_conditions.append("o.order_type = %s")
                    params.append(order_type)
                
                if order_status:
                    where_conditions.append("o.order_status = %s")
                    params.append(order_status)
                
                # Check if user wants today's orders specifically
                today_only = request.query_params.get('today')
                if today_only and today_only.lower() in ['true', '1', 'yes']:
                    from datetime import date
                    today = date.today()
                    where_conditions.append("DATE(o.created_at) = %s")
                    params.append(today)
                else:
                    # Apply date range filters only if not filtering for today
                    if start_date:
                        where_conditions.append("DATE(o.created_at) >= %s")
                        params.append(start_date)
                    
                    if end_date:
                        where_conditions.append("DATE(o.created_at) <= %s")
                        params.append(end_date)
                
                where_clause = " AND ".join(where_conditions)
                
                # Count query
                count_sql = f"""
                    SELECT COUNT(*) 
                    FROM Groceries_orders o 
                    WHERE {where_clause}
                """
                cursor.execute(count_sql, params)
                total_count = cursor.fetchone()[0]
                
                # Main query with pagination
                main_sql = f"""
                    SELECT 
                        o.order_id, o.user_id, o.business_id, o.order_type, o.order_status,
                        o.payment_status, o.total_amount, o.gst_amount, o.delivery_charge,
                        o.discount, o.final_amount, o.delivery_address, o.pickup_time,
                        o.created_at, o.updated_at,
                        u.firstName, u.lastName, u.emailID, u.mobileNumber
                    FROM Groceries_orders o
                    LEFT JOIN registrations u ON o.user_id = u.user_id
                    WHERE {where_clause}
                    ORDER BY o.created_at DESC
                    LIMIT %s OFFSET %s
                """
                
                cursor.execute(main_sql, params + [limit, offset])
                orders_data = cursor.fetchall()
                
                # Get order items for each order
                orders_with_items = []
                for order_row in orders_data:
                    order_id = order_row[0]
                    
                    # Get order items with new product structure
                    items_sql = """
                        SELECT 
                            oi.order_item_id, oi.product_id, oi.quantity, oi.unit_price, 
                            oi.gst, oi.total_price,
                            gp.product_name, gp.main_image, gc.category_name, gp.description,
                            gp.brand_name, gp.is_organic, gp.rating
                        FROM Groceries_order_items oi
                        LEFT JOIN Groceries_Products gp ON oi.product_id = gp.product_id
                        LEFT JOIN Groceries_Categories gc ON gp.category_id = gc.category_id
                        WHERE oi.order_id = %s
                    """
                    cursor.execute(items_sql, [order_id])
                    items_data = cursor.fetchall()
                    
                    # Build order object
                    order_obj = {
                        'order_id': order_row[0],
                        'user': order_row[1],
                        'business': order_row[2],
                        'order_type': order_row[3],
                        'order_status': order_row[4],
                        'payment_status': order_row[5],
                        'total_amount': str(order_row[6]),
                        'gst_amount': str(order_row[7]),
                        'delivery_charge': str(order_row[8]),
                        'discount': str(order_row[9]),
                        'final_amount': str(order_row[10]),
                        'delivery_address': order_row[11],
                        'pickup_time': order_row[12].isoformat() if order_row[12] else None,
                        'created_at': order_row[13].isoformat() if order_row[13] else None,
                        'updated_at': order_row[14].isoformat() if order_row[14] else None,
                        'user_details': {
                            'user_id': order_row[1],
                            'first_name': order_row[15],
                            'last_name': order_row[16],
                            'email': order_row[17],
                            'phone_number': order_row[18]
                        } if order_row[15] else None,
                        'order_items': []
                    }
                    
                    # Add order items
                    for item_row in items_data:
                        item_obj = {
                            'item': {
                                'product_id': item_row[1],
                                'product_name': item_row[6],
                                'product_image': item_row[7],
                                'category_name': item_row[8],
                                'description': item_row[9],
                                'brand_name': item_row[10],
                                'is_organic': item_row[11],
                                'rating': str(item_row[12]) if item_row[12] else None
                            },
                            'quantity': item_row[2],
                            'unit_price': str(item_row[3]),
                            'gst': str(item_row[4]),
                            'total_price': str(item_row[5])
                        }
                        order_obj['order_items'].append(item_obj)
                    
                    orders_with_items.append(order_obj)
            
            orders = orders_with_items
            
            if not orders:
                return Response({
                    "message": "No orders found for the given criteria.",
                    "data": {
                        "orders": [],
                        "pagination": {
                            "total_count": total_count,
                            "limit": limit,
                            "offset": offset,
                            "has_next": False,
                            "has_previous": False
                        }
                    },
                    "debug_info": {
                        "total_orders_for_business": total_count,
                        "applied_filters": filters,
                        "raw_sql_used": True
                    }
                }, status=status.HTTP_200_OK)

            # Prepare pagination info
            has_next = (offset + limit) < total_count
            has_previous = offset > 0
            
            return Response({
                "message": f"Found {len(orders)} orders for business ID {business_id}.",
                "data": {
                    "orders": orders,
                    "pagination": {
                        "total_count": total_count,
                        "limit": limit,
                        "offset": offset,
                        "has_next": has_next,
                        "has_previous": has_previous
                    }
                },
                "filters_applied": {
                    "business_id": business_id,
                    "order_type": order_type,
                    "order_status": order_status,
                    "payment_status": "paid",  # enforced (orders table only)
                    "start_date": start_date,
                    "end_date": end_date
                },
                "debug_info": {
                    "orders_returned": len(orders),
                    "raw_sql_used": True,
                    "first_order_items_count": len(orders[0]["order_items"]) if orders else 0
                }
            }, status=status.HTTP_200_OK)

        except Exception as e:
            logger.error(f"Error in BusinessOrdersView: {str(e)}")
            return Response({
                "error": str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@swagger_auto_schema(tags=['Consumer'])
class UpdateOrderStatusView(APIView):
    """
    Single API view to update order status with business_id, order_id, and status parameters.
    """
    
    def post(self, request, *args, **kwargs):
        """
        Update order status using URL parameters: business_id, order_id, status
        """
        # Get parameters from URL query params
        business_id = request.query_params.get('business_id')
        order_id = request.query_params.get('order_id')
        new_status = request.query_params.get('status')
        
        # Validate required parameters
        if not all([business_id, order_id, new_status]):
            return Response({
                "error": "business_id, order_id, and status are required parameters."
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Validate status value
        valid_statuses = ['pending', 'confirmed', 'packed', 'out of delivery', 'delivered', 'cancelled']
        if new_status not in valid_statuses:
            return Response({
                "error": f"Invalid status. Must be one of: {', '.join(valid_statuses)}"
            }, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            # Get the order
            order = GroceriesOrders.objects.get(
                order_id=order_id, 
                business_id=business_id
            )
            
            previous_status = order.order_status
            
            # Check if status is actually changing
            if previous_status == new_status:
                return Response({
                    "message": f"Order is already in {new_status} status.",
                    "order_id": order.order_id,
                    "current_status": new_status
                }, status=status.HTTP_200_OK)
            
            # Update status
            order.order_status = new_status
            order.save(update_fields=['order_status', 'updated_at'])

            # If business marks order as 'out of delivery', notify customer on WhatsApp and send OTP to customer
            wa = {}
            if new_status == 'out of delivery':
                try:
                    delivery_detail = GroceryDeliverDetails.objects.select_related('order', 'partner__user').get(order__order_id=order_id)
                    try:
                        wa['out_for_delivery'] = send_out_for_delivery_message(delivery_detail)
                    except Exception as e1:
                        logger.error(f"Failed to send out-for-delivery WhatsApp for order {order_id}: {e1}")
                    # Delivery OTP WhatsApp sending disabled
                    wa['delivery_otp'] = {"ok": False, "disabled": True, "message": "Delivery OTP WhatsApp sending is disabled"}
                except GroceryDeliverDetails.DoesNotExist:
                    logger.warning(f"No delivery assignment found for order {order_id} when marking 'out of delivery'; skipping WhatsApp notifications.")
            
            # Create appropriate success message based on status change
            status_messages = {
                'confirmed': 'Order confirmed successfully.',
                'packed': 'Order marked as ready/packed successfully.',
                'shipped': 'Order marked as shipped successfully.',
                'delivered': 'Order marked as delivered successfully.',
                'cancelled': 'Order cancelled successfully.'
            }
            
            message = status_messages.get(new_status, f'Order status updated to {new_status} successfully.')
            
            return Response({
                "message": message,
                "order_id": order.order_id,
                "business_id": business_id,
                "previous_status": previous_status,
                "current_status": new_status,
                "updated_at": order.updated_at.isoformat(),
                "whatsapp": wa
            }, status=status.HTTP_200_OK)
            
        except GroceriesOrders.DoesNotExist:
            return Response({
                "error": "Order not found for the specified business."
            }, status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            logger.error(f"Error in UpdateOrderStatusView: {str(e)}")
            return Response({
                "error": str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@swagger_auto_schema(tags=['Consumer'])
class DeliveryPartnerCheckView(APIView):
    """
    API view to check if user is a delivery partner and get their details.
    """
    
    def get(self, request, *args, **kwargs):
        """
        Get all delivery partners for a specific business based on user_mode.
        """
        user_mode = request.query_params.get('user_mode')
        business_id = request.query_params.get('business_id')
        
        if not all([user_mode, business_id]):
            return Response({
                "error": "user_mode and business_id are required."
            }, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            # Check if user_mode is delivery_partner
            if user_mode != 'delivery_partner':
                return Response({
                    "is_delivery_partner": False,
                    "user_mode": user_mode,
                    "delivery_partners": [],
                    "count": 0,
                    "message": f"Requested user_mode '{user_mode}' is not delivery_partner."
                }, status=status.HTTP_200_OK)
            
            # Get all delivery partners for the specific business with delivery_partner user_mode
            
            partners = GroceryPartner.objects.select_related('user', 'business').filter(
                business_id=business_id,
                user__user_mode='delivery_partner'
            )
            
            if not partners.exists():
                return Response({
                    "is_delivery_partner": True,
                    "user_mode": user_mode,
                    "delivery_partners": [],
                    "count": 0,
                    "message": "No delivery partners found for this business."
                }, status=status.HTTP_200_OK)
            
            # Serialize all delivery partners
            serializer = DeliveryPartnerDetailsSerializer(partners, many=True)
            
            return Response({
                "is_delivery_partner": True,
                "user_mode": user_mode,
                "business_id": business_id,
                "delivery_partners": serializer.data,
                "count": partners.count(),
                "message": f"Found {partners.count()} delivery partner(s) for this business."
            }, status=status.HTTP_200_OK)
            
        except Exception as e:
            logger.error(f"Error in DeliveryPartnerCheckView: {str(e)}")
    
    def get(self, request, *args, **kwargs):
        """
        Get all available delivery partners for a business.
        """
        business_id = request.query_params.get('business_id')
        
        if not business_id:
            return Response({
                "error": "business_id parameter is required."
            }, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            # Get all partners for the business with delivery_partner user_mode
            all_partners = GroceryPartner.objects.filter(
                business_id=business_id,
                user__user_mode='delivery_partner'
            ).select_related('user')
            
            # Get available partners
            available_partners = all_partners.filter(
                is_active=True,
                is_verified=True,
                availability_status='available'
            )
            
            # Get partners ready for assignment (active and verified, any status)
            ready_partners = all_partners.filter(
                is_active=True,
                is_verified=True
            )
            
            response_data = {
                "business_id": business_id,
                "total_partners": all_partners.count(),
                "available_for_assignment": available_partners.count(),
                "ready_partners": ready_partners.count(),
                "partners": []
            }
            
            for partner in all_partners:
                partner_info = {
                    "user_id": partner.user.user_id,
                    "name": f"{partner.user.firstName} {partner.user.lastName}",
                    "vehicle": f"{partner.vehicle_type} - {partner.vehicle_number}",
                    "user_mode": partner.user.user_mode,
                    "is_active": partner.is_active,
                    "is_verified": partner.is_verified,
                    "availability_status": partner.availability_status,
                    "can_be_assigned": partner.is_active and partner.is_verified and partner.availability_status == 'available' and partner.user.user_mode == 'delivery_partner'
                }
                response_data["partners"].append(partner_info)
            
            return Response(response_data, status=status.HTTP_200_OK)
            
        except Exception as e:
            logger.error(f"Error in AvailablePartnersView: {str(e)}")
            return Response({
                "error": str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@swagger_auto_schema(tags=['Consumer'])
class UpdatePartnerStatusView(APIView):
    """
    API view to update partner availability status.
    URL: /update-partner-status/?partner_id=<partner_id>&status=<status>
    """
    
    def post(self, request, *args, **kwargs):
        """
        Update partner availability status.
        """
        # Get URL parameters
        user_id = request.query_params.get('user_id')
        business_id = request.query_params.get('business_id')
        
        if not all([user_id, business_id]):
            return Response({
                "error": "user_id and business_id are required parameters."
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Get request body data
        partner_id = request.data.get('partner_id')
        new_status = request.data.get('new_status')
        
        if not all([partner_id, new_status]):
            return Response({
                "error": "partner_id and new_status are required in request body."
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Validate user and business
        try:
            user = Registration.objects.get(user_id=user_id, is_active=True)
            business = Business.objects.get(business_id=business_id)
        except (Registration.DoesNotExist, Business.DoesNotExist):
            return Response({
                "error": "Invalid user or business."
            }, status=status.HTTP_404_NOT_FOUND)
        
        # Validate status
        valid_statuses = ['available', 'busy', 'offline', 'break']
        if new_status not in valid_statuses:
            return Response({
                "error": f"Invalid status. Must be one of: {', '.join(valid_statuses)}"
            }, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            partner = GroceryPartner.objects.select_related('user').get(user_id=partner_id)
            
            # Check if user has delivery_partner mode
            if partner.user.user_mode != 'delivery_partner':
                return Response({
                    "error": f"Partner with user_id {partner_id} is not registered as delivery_partner. Current user_mode: {partner.user.user_mode}"
                }, status=status.HTTP_400_BAD_REQUEST)
            
            old_status = partner.availability_status
            partner.availability_status = new_status
            partner.save(update_fields=['availability_status'])
            
            # Get partner name safely
            if partner.user:
                partner_name = f"{partner.user.firstName} {partner.user.lastName}"
            else:
                partner_name = f"Partner {partner.user_id}"
            
            return Response({
                "message": f"Partner with user_id {partner_id} status updated successfully.",
                "partner_id": partner_id,
                "partner_name": partner_name,
                "previous_status": old_status,
                "current_status": new_status,
                "is_active": partner.is_active,
                "is_verified": partner.is_verified,
                "can_be_assigned": partner.is_active and partner.is_verified and new_status == 'available'
            }, status=status.HTTP_200_OK)
            
        except GroceryPartner.DoesNotExist:
            return Response({
                "error": f"Partner with user_id {partner_id} does not exist."
            }, status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            logger.error(f"Error in UpdatePartnerStatusView: {str(e)}")
            return Response({
                "error": str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@swagger_auto_schema(tags=['Consumer'])
class AssignOrderToPartnerView(APIView):
    """
    API view to assign delivery orders to partners.
    URL: /assign-order/?user_id=<retail_business_user_id>&business_id=<business_id>
    JSON: {"partner_id": <partner_id>, "order_id": <order_id>}
    """
    
    def post(self, request, *args, **kwargs):
        """
        Assign an order to a delivery partner.
        """
        # Get URL parameters
        user_id = request.query_params.get('user_id')
        business_id = request.query_params.get('business_id')
        
        if not all([user_id, business_id]):
            return Response({
                "error": "user_id and business_id are required parameters."
            }, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            # Validate that the business exists
            try:
                business = Business.objects.get(business_id=business_id)
            except Business.DoesNotExist:
                return Response({
                    "error": "Business not found."
                }, status=status.HTTP_404_NOT_FOUND)
            
            # Try to get user, but don't fail if not found
            try:
                assigned_by_user = Registration.objects.get(user_id=user_id, is_active=True)
            except Registration.DoesNotExist:
                # Create a dummy user object for assignment tracking
                assigned_by_user = None
            
            # Validate JSON data
            serializer = AssignOrderToPartnerSerializer(
                data=request.data,
                context={'assigned_by_user': assigned_by_user}
            )
            
            if not serializer.is_valid():
                return Response({
                    "error": "Validation failed.",
                    "details": serializer.errors
                }, status=status.HTTP_400_BAD_REQUEST)
            
            # Create delivery assignment with OTP
            delivery_detail = serializer.save()
            
            # Get customer details first to ensure we have contact info
            customer = {}
            customer_phone = None
            order_items = []
            try:
                # Initialize variables to avoid UnboundLocalError
                delivery_address = 'Not specified'
                customer_phone = None
                
                # Get order_id from delivery_detail
                order_id = delivery_detail.order.order_id
                
                # Use comprehensive raw SQL to get all data in one query
                from django.db import connection
                with connection.cursor() as cursor:
                    # First, let's debug what's in the order table
                    cursor.execute("""
                        SELECT order_id, user_id, delivery_address 
                        FROM Groceries_orders 
                        WHERE order_id = %s
                    """, [order_id])
                    order_debug = cursor.fetchone()
                    logger.info(f"Order debug for {order_id}: {order_debug}")
                    
                    # Check if user exists in registrations table
                    if order_debug:
                        order_user_id = order_debug[1]
                        cursor.execute("""
                            SELECT id, user_id, firstName, lastName, mobileNumber, emailID, countryCode 
                            FROM registrations 
                            WHERE id = %s OR user_id = %s
                        """, [order_user_id, order_user_id])
                        user_debug = cursor.fetchall()
                        logger.info(f"User debug for user_id {order_user_id}: {user_debug}")
                    
                    # Now run the comprehensive query
                    cursor.execute("""
                        SELECT 
                            go.order_id,
                            go.user_id as order_user_id,
                            go.delivery_address as order_delivery_address,
                            r.user_id as reg_user_id,
                            r.firstName,
                            r.lastName,
                            r.mobileNumber,
                            r.emailID,
                            r.countryCode,
                            ua.address as user_address,
                            gdd.delivery_detail_id,
                            gdd.partner_id,
                            gdd.assignment_status
                        FROM Groceries_orders go
                        LEFT JOIN registrations r ON go.user_id = r.user_id
                        LEFT JOIN user_address ua ON r.user_id = ua.user_id AND ua.is_default = 1 AND ua.status = 1
                        LEFT JOIN Grocery_deliver_details gdd ON go.order_id = gdd.order_id
                        WHERE go.order_id = %s
                        LIMIT 1
                    """, [order_id])
                    
                    result = cursor.fetchone()
                
                if not result:
                    logger.error(f"No data found for order_id {order_id}")
                    customer = {
                        "error": "Order not found",
                        "order_id": order_id,
                        "message": "No order data found in database"
                    }
                else:
                    # Extract all data from the comprehensive query
                    (order_id_db, order_user_id, order_delivery_address, 
                     reg_user_id, first_name, last_name, mobile_number, email_id, country_code,
                     user_address, delivery_detail_id, partner_id, assignment_status) = result
                    
                    logger.info(f"Comprehensive query result for order {order_id}:")
                    logger.info(f"  Order: order_id={order_id_db}, user_id={order_user_id}, delivery_address={order_delivery_address}")
                    logger.info(f"  Registration: user_id={reg_user_id}, name={first_name} {last_name}, mobile={mobile_number}, email={email_id}")
                    logger.info(f"  Address: {user_address}")
                    logger.info(f"  Delivery: detail_id={delivery_detail_id}, partner_id={partner_id}, status={assignment_status}")
                    
                    # Process delivery address
                    delivery_address = 'Not specified'
                    if user_address:
                        try:
                            # If address is stored as JSON string, parse it
                            import json
                            if isinstance(user_address, str):
                                try:
                                    addr = json.loads(user_address)
                                except json.JSONDecodeError:
                                    addr = {'address': user_address}
                            else:
                                addr = user_address
                            
                            if isinstance(addr, dict):
                                delivery_address = ", ".join(filter(None, [
                                    addr.get('address_line1', ''),
                                    addr.get('landmark', ''),
                                    addr.get('city', ''),
                                    addr.get('state', ''),
                                    addr.get('pincode', '')
                                ]))
                            else:
                                delivery_address = str(addr)
                        except Exception:
                            delivery_address = str(user_address) if user_address else 'Not specified'
                    
                    # Fall back to order's delivery address if user address not available
                    if not delivery_address or delivery_address == 'Not specified':
                        delivery_address = order_delivery_address or 'Not specified'
                    
                    # Process country code
                    processed_country_code = country_code or '+91'
                    if processed_country_code:
                        processed_country_code = str(processed_country_code).strip()
                        if not processed_country_code.startswith('+'):
                            processed_country_code = f"+{processed_country_code}"
                    else:
                        processed_country_code = '+91'
                    
                    # Process mobile number
                    processed_mobile = ''
                    if mobile_number:
                        processed_mobile = str(mobile_number).strip()
                        if processed_mobile.isdigit() and len(processed_mobile) >= 10:
                            # Format with country code for WhatsApp
                            customer_phone = f"{processed_country_code}{processed_mobile[-10:]}"
                    
                    # Check if user was found in registration table
                    if not reg_user_id:
                        logger.warning(f"User not found in Registration table for order {order_id} (order.user_id={order_user_id})")
                        customer = {
                            "user_id": order_user_id,
                            "name": "Customer (User not found in Registration)",
                            "mobile": "Not available",
                            "country_code": "+91",
                            "email": "Not available",
                            "address": delivery_address,
                            "debug_info": f"Order exists but user_id {order_user_id} not found in registrations table"
                        }
                    else:
                        # Prepare customer details using comprehensive query data
                        customer = {
                            "user_id": reg_user_id or order_user_id,
                            "name": ' '.join(filter(None, [
                                first_name or '',
                                last_name or ''
                            ])).strip() or 'Customer',
                            "mobile": processed_mobile or 'Not available',
                            "country_code": processed_country_code,
                            "email": email_id or 'Not available',
                            "address": delivery_address
                        }
                    
                    # Log the final customer details
                    logger.info(f"Final customer details for order {order_id}: {customer}")
                
                # Get order items/products for this order
                order_items = []
                try:
                    with connection.cursor() as cursor:
                        cursor.execute("""
                            SELECT 
                                goi.order_item_id,
                                goi.quantity,
                                goi.unit_price,
                                goi.gst,
                                goi.total_price,
                                gp.product_name,
                                gp.brand_name,
                                gp.main_image,
                                gp.description,
                                gp.is_organic,
                                gp.rating,
                                gc.category_name
                            FROM Groceries_order_items goi
                            LEFT JOIN Groceries_Products gp ON goi.product_id = gp.product_id
                            LEFT JOIN Groceries_Categories gc ON gp.category_id = gc.category_id
                            WHERE goi.order_id = %s
                            ORDER BY goi.order_item_id
                        """, [order_id])
                        
                        items_result = cursor.fetchall()
                        
                        for item_row in items_result:
                            (order_item_id, quantity, unit_price, gst, total_price, 
                             product_name, brand_name, main_image, description,
                             is_organic, rating, category_name) = item_row
                            
                            order_items.append({
                                "order_item_id": order_item_id,
                                "product_name": product_name or "Unknown Product",
                                "brand_name": brand_name or "",
                                "category": category_name or "",
                                "description": description or "",
                                "is_organic": bool(is_organic) if is_organic is not None else False,
                                "rating": float(rating) if rating else 0.0,
                                "quantity": quantity,
                                "unit_price": float(unit_price) if unit_price else 0.0,
                                "gst": float(gst) if gst else 0.0,
                                "total_price": float(total_price) if total_price else 0.0,
                                "main_image": main_image or ""
                            })
                        
                        logger.info(f"Found {len(order_items)} items for order {order_id}")
                        
                except Exception as items_err:
                    logger.error(f"Error fetching order items: {items_err}", exc_info=True)
                    order_items = [{"error": "Could not fetch order items", "details": str(items_err)}]
                
            except Exception as cust_err:
                logger.error(f"Error fetching customer details: {cust_err}", exc_info=True)
                # Even if customer details fail, we still want to send the OTP
                customer = {
                    "error": "Could not fetch customer details",
                    "debug_info": str(cust_err)
                }
            
            # Send OTP to customer
            try:
                otp_result = delivery_detail.send_otp_to_customer()
                # Update otp_result with customer phone if available
                if customer_phone and 'customer_phone' not in otp_result:
                    otp_result['customer_phone'] = customer_phone
            except Exception as otp_err:
                logger.error(f"Error sending OTP: {otp_err}", exc_info=True)
                otp_result = {
                    "otp_sent": False,
                    "error": str(otp_err),
                    "customer_phone": customer_phone or 'Not available',
                    "customer_email": customer.get('email', 'Not available')
                }
            
            # Additionally send via WhatsApp (best-effort)
            wa_delivery_otp = None
            wa_out_for_delivery = None
            
            # Only attempt WhatsApp if we have a valid phone number
            if customer_phone:
                try:
                    # Prepare contact override with customer phone
                    contact_override = {
                        'phoneNumber': customer_phone,
                        'countryCode': '+91'  # Default country code
                    }
                    
                    # Delivery OTP WhatsApp sending disabled by request
                    wa_delivery_otp = {"ok": False, "disabled": True, "message": "Delivery OTP WhatsApp sending is disabled"}
                    
                    # Send out-for-delivery notification if we have a valid phone
                    try:
                        wa_out_for_delivery = send_out_for_delivery_message(delivery_detail)
                    except Exception as wa2_err:
                        logger.error(f"Failed to send WhatsApp out-for-delivery: {wa2_err}")
                        wa_out_for_delivery = {"ok": False, "error": str(wa2_err)}
                        
                except Exception as wa_err:
                    logger.error(f"Failed to send WhatsApp notifications: {wa_err}")
                    wa_delivery_otp = {"ok": False, "error": str(wa_err)}
            else:
                logger.warning("Skipping WhatsApp notifications - no valid customer phone number")
            
            # Prepare response data with customer details and order items
            response_data = {
                "message": "Order assigned to delivery partner successfully.",
                "otp": delivery_detail.delivery_otp,
                "customer": customer,
                "order_items": order_items,
                "assignment_info": {
                    "delivery_detail_id": delivery_detail.delivery_detail_id,
                    "order_id": delivery_detail.order.order_id,
                    "partner_id": delivery_detail.partner.user_id,
                    "partner_name": f"{delivery_detail.partner.user.firstName} {delivery_detail.partner.user.lastName}" if hasattr(delivery_detail.partner, 'user') and delivery_detail.partner.user else f"Partner {delivery_detail.partner.user_id}",
                    "partner_vehicle": f"{getattr(delivery_detail.partner, 'vehicle_type', '')} - {getattr(delivery_detail.partner, 'vehicle_number', '')}",
                    "assigned_by": f"{assigned_by_user.firstName} {assigned_by_user.lastName}" if assigned_by_user else f"User {user_id}",
                    "assigned_at": delivery_detail.assigned_at.isoformat(),
                    "status": delivery_detail.assignment_status
                },
                "otp_notification": otp_result,
                "whatsapp": {
                    "delivery_otp": wa_delivery_otp,
                    "out_for_delivery": wa_out_for_delivery
                }
            }
            
            return Response(response_data, status=status.HTTP_201_CREATED)
            
        except Exception as e:
            logger.error(f"Error in AssignOrderToPartnerView: {str(e)}", exc_info=True)
            return Response({
                "error": "An error occurred while processing your request.",
                "details": str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@swagger_auto_schema(tags=['Consumer'])
class PartnerDeliveryDetailsView(APIView):
    """API view to get delivery details by partner user_id"""
    
    def get(self, request, *args, **kwargs):
        """Get delivery details for a specific partner"""
        # Get URL parameters
        partner_user_id = request.query_params.get('partner_user_id')
        business_id = request.query_params.get('business_id')
        
        if not partner_user_id:
            return Response({
                "error": "partner_user_id is required parameter."
            }, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            # Validate that the partner exists
            try:
                partner = GroceryPartner.objects.select_related('user').get(user_id=partner_user_id)
                
                # Check if user has delivery_partner mode
                if partner.user.user_mode != 'delivery_partner':
                    return Response({
                        "error": f"Partner with user_id {partner_user_id} is not registered as delivery_partner. Current user_mode: {partner.user.user_mode}"
                    }, status=status.HTTP_400_BAD_REQUEST)
                
            except GroceryPartner.DoesNotExist:
                return Response({
                    "error": f"Partner with user_id {partner_user_id} does not exist."
                }, status=status.HTTP_404_NOT_FOUND)
            
            # Build query filters
            filters = {
                'partner__user_id': partner_user_id
                # Get all orders for this partner (assigned, in_progress, delivered, etc.)
            }
            
            # Add business filter if provided
            if business_id:
                filters['order__business__business_id'] = business_id
            
            # Get delivery details with related data
            delivery_details = GroceryDeliverDetails.objects.select_related(
                'order', 'partner__user', 'assigned_by_user'
            ).prefetch_related(
                'order__groceriesorderitems_set__product'
            ).filter(**filters).order_by('-assigned_at')
            
            # Serialize the data and enhance with customer details using raw SQL
            serializer = GroceryDeliverDetailsSerializer(delivery_details, many=True)
            enhanced_delivery_details = []
            
            # Use raw SQL to get customer details for each order
            from django.db import connection
            for delivery_data in serializer.data:
                order_id = delivery_data.get('order')
                customer_details = {}
                
                try:
                    with connection.cursor() as cursor:
                        # Comprehensive query to get customer details
                        cursor.execute("""
                            SELECT 
                                go.order_id,
                                go.user_id as order_user_id,
                                go.delivery_address as order_delivery_address,
                                r.user_id as reg_user_id,
                                r.firstName,
                                r.lastName,
                                r.mobileNumber,
                                r.emailID,
                                r.countryCode,
                                ua.address as user_address
                            FROM Groceries_orders go
                            LEFT JOIN registrations r ON go.user_id = r.user_id
                            LEFT JOIN user_address ua ON r.user_id = ua.user_id AND ua.is_default = 1 AND ua.status = 1
                            WHERE go.order_id = %s
                            LIMIT 1
                        """, [order_id])
                        
                        result = cursor.fetchone()
                except Exception as e:
                    logger.error(f"Failed to fetch customer details for order {order_id}: {e}")
                    result = None
                
                if not result:
                    logger.error(f"No data found for order_id {order_id}")
                    customer = {
                        "error": "Order not found",
                        "order_id": order_id,
                        "message": "No order data found in database"
                    }
                else:
                    # Extract all data from the comprehensive query
                    (order_id_db, order_user_id, order_delivery_address, 
                     reg_user_id, first_name, last_name, mobile_number, email_id, country_code,
                     user_address) = result
                    
                    logger.info(f"Comprehensive query result for order {order_id}:")
                    logger.info(f"  Order: order_id={order_id_db}, user_id={order_user_id}, delivery_address={order_delivery_address}")
                    logger.info(f"  Registration: user_id={reg_user_id}, name={first_name} {last_name}, mobile={mobile_number}, email={email_id}")
                    logger.info(f"  Address: {user_address}")
                    
                    # Process delivery address
                    delivery_address = 'Not specified'
                    if user_address:
                        try:
                            # If address is stored as JSON string, parse it
                            import json
                            if isinstance(user_address, str):
                                try:
                                    addr = json.loads(user_address)
                                except json.JSONDecodeError:
                                    addr = {'address': user_address}
                            else:
                                addr = user_address
                            
                            if isinstance(addr, dict):
                                delivery_address = ", ".join(filter(None, [
                                    addr.get('address_line1', ''),
                                    addr.get('landmark', ''),
                                    addr.get('city', ''),
                                    addr.get('state', ''),
                                    addr.get('pincode', '')
                                ]))
                            else:
                                delivery_address = str(addr)
                        except Exception:
                            delivery_address = str(user_address) if user_address else 'Not specified'
                    
                    # Fall back to order's delivery address if user address not available
                    if not delivery_address or delivery_address == 'Not specified':
                        delivery_address = order_delivery_address or 'Not specified'
                    
                    # Process country code
                    processed_country_code = country_code or '+91'
                    if processed_country_code:
                        processed_country_code = str(processed_country_code).strip()
                        if not processed_country_code.startswith('+'):
                            processed_country_code = f"+{processed_country_code}"
                    else:
                        processed_country_code = '+91'
                    
                    # Process mobile number
                    processed_mobile = ''
                    if mobile_number:
                        processed_mobile = str(mobile_number).strip()
                    
                    # Check if user was found in registration table
                    if not reg_user_id:
                        logger.warning(f"User not found in Registration table for order {order_id} (order.user_id={order_user_id})")
                        customer = {
                            "user_id": order_user_id,
                            "name": "Customer (User not found in Registration)",
                            "mobile": "Not available",
                            "country_code": "+91",
                            "email": "Not available",
                            "address": delivery_address,
                            "debug_info": f"Order exists but user_id {order_user_id} not found in registrations table"
                        }
                    else:
                        # Prepare customer details using comprehensive query data
                        customer = {
                            "user_id": reg_user_id or order_user_id,
                            "name": ' '.join(filter(None, [
                                first_name or '',
                                last_name or ''
                            ])).strip() or 'Customer',
                            "mobile": processed_mobile or 'Not available',
                            "country_code": processed_country_code,
                            "email": email_id or 'Not available',
                            "address": delivery_address
                        }
                    
                    # Log the final customer details
                    logger.info(f"Final customer details for order {order_id}: {customer}")
                
                # Add customer details to delivery data
                delivery_data['customer_details'] = customer
                enhanced_delivery_details.append(delivery_data)
            
            # Get partner info
            partner_info = {
                "partner_user_id": partner.user_id,
                "partner_name": f"{partner.user.firstName} {partner.user.lastName}",
                "vehicle": f"{partner.vehicle_type} - {partner.vehicle_number}",
                "availability_status": partner.availability_status,
                "is_active": partner.is_active,
                "is_verified": partner.is_verified,
                "total_deliveries": partner.total_deliveries,
                "rating_average": float(partner.rating_average)
            }
            
            return Response({
                "partner_info": partner_info,
                "total_assignments": delivery_details.count(),
                "delivery_details": enhanced_delivery_details
            }, status=status.HTTP_200_OK)
            
        except Exception as e:
            logger.error(f"Error in PartnerDeliveryDetailsView: {str(e)}")
            return Response({
                "error": str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@swagger_auto_schema(tags=['Consumer'])
class DeliveryDetailsByOrderView(APIView):
    """
    API view to fetch delivery details and partner information by order ID.
    URL: /api/delivery-details/?order_id=<order_id>
    """
    def get(self, request, *args, **kwargs):
        order_id = request.query_params.get('order_id')
        
        if not order_id:
            return Response(
                {"error": "order_id parameter is required"}, 
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            # Get the delivery details with related partner and order information
            delivery_details = GroceryDeliverDetails.objects.select_related(
                'order',
                'partner',
                'partner__user',
                'assigned_by_user'
            ).get(
                order_id=order_id,
                is_active=True
            )
            
            # Create custom response with delivery, partner, and order details
            response_data = {
                "delivery_detail_id": delivery_details.delivery_detail_id,
                "order_id": delivery_details.order_id,
                "assignment_status": delivery_details.assignment_status,
                "assigned_at": delivery_details.assigned_at.isoformat() if delivery_details.assigned_at else None,
                "delivered_at": delivery_details.delivered_at.isoformat() if delivery_details.delivered_at else None,
                "delivery_otp": delivery_details.delivery_otp,
                "otp_verified_at": delivery_details.otp_verified_at.isoformat() if delivery_details.otp_verified_at else None,
                "is_active": delivery_details.is_active,
                "order_details": {
                    "order_id": delivery_details.order.order_id,
                    "order_status": delivery_details.order.order_status,
                    "order_type": delivery_details.order.order_type,
                    "delivery_address": delivery_details.order.delivery_address,
                    "total_amount": float(delivery_details.order.total_amount),
                    "final_amount": float(delivery_details.order.final_amount),
                    "payment_status": delivery_details.order.payment_status,
                    "delivery_charge": float(delivery_details.order.delivery_charge),
                    "discount": float(delivery_details.order.discount),
                    "gst_amount": float(delivery_details.order.gst_amount),
                    "created_at": delivery_details.order.created_at.isoformat() if delivery_details.order.created_at else None,
                    "updated_at": delivery_details.order.updated_at.isoformat() if delivery_details.order.updated_at else None
                },
                "partner_details": {
                    "partner_user_id": delivery_details.partner.user_id,
                    "partner_name": f"{delivery_details.partner.user.firstName} {delivery_details.partner.user.lastName}",
                    "emergency_contact_phone": delivery_details.partner.emergency_contact_phone,
                    "vehicle_type": delivery_details.partner.vehicle_type,
                    "vehicle_number": delivery_details.partner.vehicle_number,
                    "availability_status": delivery_details.partner.availability_status,
                    "is_active": delivery_details.partner.is_active,
                    "is_verified": delivery_details.partner.is_verified,
                    "total_deliveries": delivery_details.partner.total_deliveries,
                    "rating_average": float(delivery_details.partner.rating_average)
                },
                "assigned_by": {
                    "user_id": delivery_details.assigned_by_user.user_id if delivery_details.assigned_by_user else None,
                    "name": f"{delivery_details.assigned_by_user.firstName} {delivery_details.assigned_by_user.lastName}" if delivery_details.assigned_by_user else None
                } if delivery_details.assigned_by_user else None
            }
            
            return Response({
                "success": True,
                "data": response_data
            })
            
        except GroceryDeliverDetails.DoesNotExist:
            # Check if the order exists but has no delivery details
            if GroceriesOrders.objects.filter(order_id=order_id).exists():
                return Response({
                    "success": True,
                    "data": {
                        "message": "No delivery details found for this order",
                        "has_delivery": False
                    }
                })
            return Response(
                {"error": "Order not found"}, 
                status=status.HTTP_404_NOT_FOUND
            )
        except Exception as e:
            logger.error(f"Error fetching delivery details: {str(e)}", exc_info=True)
            return Response(
                {"error": "An error occurred while fetching delivery details"}, 
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


@swagger_auto_schema(tags=['Consumer'])
class UpdateDeliveryStatusView(APIView):
    """
    API view to update delivery assignment status for an order.
    Triggers WhatsApp notifications when status becomes 'in_transit' (out for delivery).
    URL: /update-delivery-status/
    Method: POST
    Body: { "order_id": 123, "new_status": "in_transit" }
    Optional query/body: partner_user_id for validation
    """
    def post(self, request, *args, **kwargs):
        order_id = request.data.get('order_id') or request.query_params.get('order_id')
        new_status = (request.data.get('new_status') or '').strip()
        partner_user_id = request.data.get('partner_user_id') or request.query_params.get('partner_user_id')

        if not order_id or not new_status:
            return Response({"error": "order_id and new_status are required"}, status=status.HTTP_400_BAD_REQUEST)

        valid_statuses = ['assigned', 'accepted', 'picked_up', 'in_transit', 'delivered', 'cancelled']
        if new_status not in valid_statuses:
            return Response({"error": f"Invalid status. Must be one of: {', '.join(valid_statuses)}"}, status=status.HTTP_400_BAD_REQUEST)

        # Enforce that 'delivered' should be done via VerifyDeliveryOTPView
        if new_status == 'delivered':
            return Response({
                "error": "Use /verify-delivery-otp/ to mark an order delivered after OTP verification."
            }, status=status.HTTP_400_BAD_REQUEST)

        try:
            delivery_detail = GroceryDeliverDetails.objects.select_related('order', 'partner__user').get(order__order_id=order_id)
        except GroceryDeliverDetails.DoesNotExist:
            return Response({"error": f"No delivery assignment found for order {order_id}."}, status=status.HTTP_404_NOT_FOUND)

        # Validate partner if provided
        if partner_user_id and str(delivery_detail.partner.user_id) != str(partner_user_id):
            return Response({"error": "Partner is not assigned to this order."}, status=status.HTTP_403_FORBIDDEN)

        # Validate allowed transition
        if not delivery_detail.can_update_status(new_status):
            return Response({
                "error": f"Cannot change status from {delivery_detail.assignment_status} to {new_status}"
            }, status=status.HTTP_400_BAD_REQUEST)

        try:
            with transaction.atomic():
                prev_status = delivery_detail.assignment_status
                delivery_detail.assignment_status = new_status
                delivery_detail.save(update_fields=['assignment_status', 'updated_at'])

                wa = {}
                # Keep the GroceriesOrders.order_status in sync when partner starts progress
                try:
                    order_obj = delivery_detail.order
                    if new_status in ('accepted', 'picked_up', 'in_transit'):
                        if getattr(order_obj, 'order_status', '').strip().lower() != 'out of delivery':
                            order_obj.order_status = 'out of delivery'
                            order_obj.save(update_fields=['order_status', 'updated_at'])
                except Exception as _sync_err:
                    logger.error(f"Failed to sync order_status to 'out of delivery' for order {order_id}: {_sync_err}")
                # Optional: allow overriding customer phone for WhatsApp OTP (debug/fallback)
                try:
                    req_data = request.data if isinstance(request.data, dict) else {}
                except Exception:
                    req_data = {}
                ph = (req_data.get('phone_number') or request.query_params.get('phone_number') or '').strip()
                cc = ((req_data.get('country_code') or request.query_params.get('country_code') or '+91').strip() if ph else None)
                override_contact = {"countryCode": cc, "phoneNumber": ph} if ph else None
                # Optional WhatsApp template overrides to support OTP-only templates
                wa_template_name = (req_data.get('wa_template_name') or request.query_params.get('wa_template_name'))
                wa_language_code = (req_data.get('wa_language_code') or request.query_params.get('wa_language_code'))
                wa_body_mode = (req_data.get('wa_body_mode') or request.query_params.get('wa_body_mode'))
                wa_button_value = (req_data.get('wa_button_value') or request.query_params.get('wa_button_value'))
                # When partner accepts the order, send the delivery OTP to the customer
                if new_status == 'accepted':
                    try:
                        from .utils.interakt import send_delivery_otp_message
                        wa['delivery_otp'] = send_delivery_otp_message(
                            delivery_detail,
                            override_contact=override_contact,
                            template_name_override=wa_template_name,
                            language_override=wa_language_code,
                            body_mode_override=wa_body_mode,
                            button_value_override=wa_button_value
                        )
                        logger.info(f"Sent delivery OTP WhatsApp for accepted order {order_id}: {wa['delivery_otp']}")
                        
                        # If WhatsApp fails, try SMS/Email fallback
                        if not wa['delivery_otp'].get('ok', False):
                            logger.warning(f"WhatsApp delivery OTP failed for order {order_id}, trying SMS/Email fallback")
                            try:
                                # Send OTP via SMS/Email as fallback
                                sms_result = delivery_detail.send_otp_to_customer()
                                wa['delivery_otp']['sms_fallback'] = {
                                    "attempted": True,
                                    "result": sms_result,
                                    "message": "WhatsApp failed, sent via SMS/Email instead"
                                }
                                logger.info(f"SMS/Email fallback for order {order_id}: {sms_result}")
                            except Exception as sms_err:
                                logger.error(f"SMS/Email fallback also failed for order {order_id}: {sms_err}")
                                wa['delivery_otp']['sms_fallback'] = {
                                    "attempted": True,
                                    "error": str(sms_err)
                                }
                                
                    except Exception as e1:
                        logger.error(f"Failed to send delivery OTP WhatsApp for accepted order {order_id}: {e1}")
                        wa['delivery_otp'] = {"ok": False, "error": str(e1)}
                # When the delivery is out for delivery, notify and send OTP via WhatsApp
                if new_status == 'in_transit':
                    try:
                        from .utils.interakt import send_out_for_delivery_message, send_delivery_otp_message
                        wa['out_for_delivery'] = send_out_for_delivery_message(delivery_detail)
                        wa['delivery_otp'] = send_delivery_otp_message(
                            delivery_detail,
                            override_contact=override_contact,
                            template_name_override=wa_template_name,
                            language_override=wa_language_code,
                            body_mode_override=wa_body_mode
                        )
                        logger.info(f"Sent out-for-delivery and delivery OTP WhatsApp for order {order_id}")
                    except Exception as e1:
                        logger.error(f"Failed to send WhatsApp notifications for in_transit order {order_id}: {e1}")
                        wa['out_for_delivery'] = {"ok": False, "error": str(e1)}
                        wa['delivery_otp'] = {"ok": False, "error": str(e1)}

                return Response({
                    "success": True,
                    "message": f"Delivery status updated from {prev_status} to {new_status}",
                    "order_id": order_id,
                    "status": new_status,
                    "whatsapp": wa
                }, status=status.HTTP_200_OK)
        except Exception as e:
            logger.error(f"Error updating delivery status for order {order_id}: {str(e)}", exc_info=True)
            return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@swagger_auto_schema(tags=['Consumer'])
class VerifyDeliveryOTPView(APIView):
    """
    API view for delivery partners to verify OTP and mark order as delivered.
    This will update both the delivery status and the order status in GroceriesOrders.
    
    Query Parameters:
    - partner_user_id: ID of the delivery partner (required)
    - order_id: ID of the order (required)
    
    Request Body:
    {
        "otp": "123456"
    }
    
    Response:
    {
        "success": true,
        "message": "OTP verified and order marked as delivered",
        "delivery_status": "delivered",
        "order_status": "delivered"
    }
    """
    def post(self, request, *args, **kwargs):
        # Get query parameters
        partner_user_id = request.query_params.get('partner_user_id')
        order_id = request.query_params.get('order_id')
        
        if not partner_user_id or not order_id:
            return Response(
                {"error": "Both partner_user_id and order_id query parameters are required"}, 
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Validate that user exists and is a delivery partner
        try:
            user = Registration.objects.get(user_id=partner_user_id, is_active=True)
            if user.user_mode != 'delivery_partner':
                return Response({
                    "error": "Only delivery partners can verify delivery OTP."
                }, status=status.HTTP_403_FORBIDDEN)
                
        except Registration.DoesNotExist:
            return Response(
                {"error": "Invalid delivery partner"}, 
                status=status.HTTP_404_NOT_FOUND
            )
        
        # Initialize serializer with order_id from URL
        serializer = VerifyDeliveryOTPSerializer(
            data=request.data,
            context={'request': request},
            order_id=order_id
        )
        
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        
        # Get the validated delivery details from serializer
        delivery_details = serializer.validated_data['delivery_detail']
        
        # Verify the partner is assigned to this delivery
        if str(delivery_details.partner.user_id) != partner_user_id:
            return Response(
                {"error": "You are not assigned to deliver this order"}, 
                status=status.HTTP_403_FORBIDDEN
            )
        
        try:
            # Mark as delivered
            with transaction.atomic():
                # Mark OTP as verified using the model method
                delivery_details.verify_otp(serializer.validated_data['otp'])
                
                # Update delivery status
                delivery_details.mark_delivered()
                
                # Update partner availability back to available
                partner = delivery_details.partner
                partner.availability_status = 'available'
                partner.save(update_fields=['availability_status'])
                
                # Update order status
                order = delivery_details.order
                order.order_status = 'delivered'
                order.save(update_fields=['order_status', 'updated_at'])
                
                logger.info(f"Order {order_id} marked as delivered by partner {partner_user_id}")
                
                return Response({
                    "success": True,
                    "message": "OTP verified and order marked as delivered",
                    "delivery_status": delivery_details.assignment_status,
                    "order_status": order.order_status,
                    "delivery_info": {
                        "order_id": order_id,
                        "partner_id": partner_user_id,
                        "partner_name": f"{partner.user.firstName} {partner.user.lastName}",
                        "delivered_at": delivery_details.delivered_at.isoformat() if delivery_details.delivered_at else None,
                        "otp_verified_at": delivery_details.otp_verified_at.isoformat() if delivery_details.otp_verified_at else None,
                        "assignment_status": delivery_details.assignment_status,
                        "order_status": order.order_status
                    }
                }, status=status.HTTP_200_OK)
                
        except Exception as e:
            logger.error(f"Error in VerifyDeliveryOTPView: {str(e)}", exc_info=True)
            return Response(
                {"error": "An error occurred while verifying OTP"}, 
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


@swagger_auto_schema(tags=['Consumer'])
class GeneratePickupOTPView(APIView):
    """
    API view to generate OTP for pickup orders and send to customer email.
    Used by retail business to generate OTP when customer arrives for pickup.
    
    URL: /generate-pickup-otp/
    Method: POST
    Query Parameters:
    - business_id: ID of the retail business
    
    Request Body:
    {
        "order_id": 123
    }
    
    Response:
    {
        "success": true,
        "message": "OTP generated and sent to customer email",
        "order_id": 123,
        "customer_email": "customer@example.com",
        "otp_generated_at": "2023-12-07T10:30:00Z"
    }
    """
    def post(self, request, *args, **kwargs):
        business_id = request.query_params.get('business_id')
        
        if not business_id:
            return Response(
                {"error": "business_id query parameter is required"}, 
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Validate that business exists
        try:
            business = Business.objects.get(business_id=business_id)
        except Business.DoesNotExist:
            return Response(
                {"error": "Business not found"}, 
                status=status.HTTP_404_NOT_FOUND
            )
        
        # Validate request data
        serializer = GeneratePickupOTPSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        
        # Get the validated order from serializer
        order = serializer.validated_data['order']
        
        # Verify order belongs to this business
        # The order.business_id is an integer, but business.business_id is a string
        # We need to compare them properly
        if str(order.business_id) != str(business.business_id):
            print(f"DEBUG: Business mismatch - Order business_id: {order.business_id}, Request business_id: {business.business_id}")
            return Response(
                {"error": "Order does not belong to this business"}, 
                status=status.HTTP_403_FORBIDDEN
            )
        
        try:
            with transaction.atomic():
                # Generate OTP
                otp = order.generate_pickup_otp()
                
                # Send OTP to customer email - handle missing user relationship
                try:
                    customer_email = order.user.emailID
                    customer_name = f"{order.user.firstName} {order.user.lastName}"
                except Exception as user_error:
                    print(f"DEBUG: User relationship error: {user_error}")
                    # Fallback: get user info using raw SQL
                    from django.db import connection
                    with connection.cursor() as cursor:
                        cursor.execute(
                            "SELECT emailID, firstName, lastName FROM registrations WHERE user_id = %s",
                            [order.user_id]
                        )
                        user_result = cursor.fetchone()
                        if user_result:
                            customer_email = user_result[0]
                            customer_name = f"{user_result[1]} {user_result[2]}"
                        else:
                            # If user not found, use placeholder values
                            customer_email = "customer@example.com"  # This should be replaced with actual email
                            customer_name = "Customer"
                            print(f"DEBUG: User {order.user_id} not found in Registration table")
                
                try:
                    business_name = order.business.business_name
                except Exception as business_error:
                    print(f"DEBUG: Business relationship error: {business_error}")
                    # Fallback: get business name using raw SQL
                    from django.db import connection
                    with connection.cursor() as cursor:
                        cursor.execute(
                            "SELECT businessName FROM businesses WHERE business_id = %s",
                            [order.business_id]
                        )
                        business_result = cursor.fetchone()
                        business_name = business_result[0] if business_result else "Business"
                
                # Email content
                subject = f"Pickup OTP for Order #{order.order_id} - {business_name}"
                message = f"""
Dear {customer_name},

Your order #{order.order_id} is ready for pickup at {business_name}.

Your pickup verification OTP is: {otp}

Please share this OTP with the store staff to collect your order.

Order Details:
- Order ID: {order.order_id}
- Total Amount: ₹{order.final_amount}
- Business: {business_name}

This OTP is valid for 30 minutes.

Thank you for your order!

Best regards,
Kirazee Team
"""
                
                # Try to send email (skip if no valid email)
                email_sent = False
                if customer_email and customer_email != "customer@example.com":
                    try:
                        send_mail(
                            subject,
                            message,
                            settings.DEFAULT_FROM_EMAIL,
                            [customer_email],
                            fail_silently=False,
                        )
                        email_sent = True
                    except Exception as email_error:
                        print(f"Email sending failed: {email_error}")
                        email_sent = False
                else:
                    print(f"DEBUG: Skipping email send - no valid customer email found")
                
                logger.info(f"Pickup OTP {otp} generated and sent to {customer_email} for order {order.order_id}")
                
                # Send WhatsApp notifications: pickup ready + pickup OTP (best-effort)
                wa_pickup_ready = None
                wa_pickup_otp = None
                try:
                    wa_pickup_ready = send_pickup_ready_message(order)
                except Exception as wa_ready_err:
                    logger.error(f"Failed to send WhatsApp pickup ready for order {order.order_id}: {wa_ready_err}")
                try:
                    wa_pickup_otp = send_pickup_otp_message(order, otp)
                except Exception as wa_otp_err:
                    logger.error(f"Failed to send WhatsApp pickup OTP for order {order.order_id}: {wa_otp_err}")

                return Response({
                    "success": True,
                    "message": "OTP generated successfully" + (" and sent to customer email" if email_sent else " but email sending failed"),
                    "order_id": order.order_id,
                    "customer_email": customer_email,
                    "customer_name": customer_name,
                    "otp": otp if not email_sent else None,  # Include OTP in response if email fails
                    "email_sent": email_sent,
                    "expires_in_minutes": 30,
                    "whatsapp": {
                        "pickup_ready": wa_pickup_ready,
                        "pickup_otp": wa_pickup_otp
                    }
                }, status=status.HTTP_200_OK)
                
        except Exception as e:
            import traceback
            error_details = traceback.format_exc()
            print(f"DETAILED ERROR in GeneratePickupOTPView: {str(e)}")
            print(f"FULL TRACEBACK: {error_details}")
            logger.error(f"Error in GeneratePickupOTPView: {str(e)}", exc_info=True)
            return Response(
                {
                    "error": "An error occurred while generating OTP",
                    "details": str(e),
                    "debug_info": "Check server logs for full traceback"
                }, 
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


@swagger_auto_schema(tags=['Consumer'])
class VerifyPickupOTPView(APIView):
    """
    API view to verify pickup OTP and mark order as delivered.
    Used by retail business to verify customer's OTP at the counter.
    
    URL: /verify-pickup-otp/
    Method: POST
    Query Parameters:
    - business_id: ID of the retail business
    
    Request Body:
    {
        "order_id": 123,
        "otp": "123456"
    }
    
    Response:
    {
        "success": true,
        "message": "OTP verified and order marked as delivered",
        "order_id": 123,
        "order_status": "delivered",
        "verified_at": "2023-12-07T10:35:00Z"
    }
    """
    def post(self, request, *args, **kwargs):
        business_id = request.query_params.get('business_id')
        
        if not business_id:
            return Response(
                {"error": "business_id query parameter is required"}, 
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Validate that business exists
        try:
            business = Business.objects.get(business_id=business_id)
        except Business.DoesNotExist:
            return Response(
                {"error": "Business not found"}, 
                status=status.HTTP_404_NOT_FOUND
            )
        
        # Validate request data
        serializer = VerifyPickupOTPSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        
        # Get the validated order from serializer
        order = serializer.validated_data['order']
        otp = serializer.validated_data['otp']
        
        # Verify order belongs to this business
        # The order.business_id is an integer, but business.business_id is a string
        if str(order.business_id) != str(business.business_id):
            return Response(
                {"error": "Order does not belong to this business"}, 
                status=status.HTTP_403_FORBIDDEN
            )
        
        # Check if OTP is still valid (not expired)
        if not order.is_pickup_otp_valid():
            return Response(
                {"error": "OTP has expired. Please generate a new OTP."}, 
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            with transaction.atomic():
                # Verify OTP
                if order.verify_pickup_otp(otp):
                    # Mark order as delivered
                    order.order_status = 'delivered'
                    order.save(update_fields=['order_status', 'updated_at'])
                    
                    logger.info(f"Pickup OTP verified and order {order.order_id} marked as delivered")
                    
                    # Get customer name with fallback handling
                    try:
                        customer_name = f"{order.user.firstName} {order.user.lastName}"
                    except Exception as user_error:
                        print(f"DEBUG: User relationship error in verify: {user_error}")
                        # Fallback: get user info using raw SQL
                        from django.db import connection
                        with connection.cursor() as cursor:
                            cursor.execute(
                                "SELECT firstName, lastName FROM registrations WHERE user_id = %s",
                                [order.user_id]
                            )
                            user_result = cursor.fetchone()
                            if user_result:
                                customer_name = f"{user_result[0]} {user_result[1]}"
                            else:
                                customer_name = "Customer"
                    
                    # Get verified_at timestamp with fallback handling
                    try:
                        verified_at = order.pickup_otp_verified_at
                    except:
                        # If field doesn't exist, get from raw SQL
                        from django.db import connection
                        with connection.cursor() as cursor:
                            cursor.execute(
                                "SELECT pickup_otp_verified_at FROM Groceries_orders WHERE order_id = %s",
                                [order.order_id]
                            )
                            result = cursor.fetchone()
                            verified_at = result[0] if result else None
                    
                    return Response({
                        "success": True,
                        "message": "OTP verified and order marked as delivered",
                        "order_id": order.order_id,
                        "order_status": order.order_status,
                        "customer_name": customer_name,
                        "verified_at": verified_at.isoformat() if verified_at else None,
                        "order_details": {
                            "total_amount": str(order.final_amount),
                            "payment_status": order.payment_status,
                            "order_type": order.order_type
                        }
                    }, status=status.HTTP_200_OK)
                else:
                    return Response(
                        {"error": "Invalid OTP provided"}, 
                        status=status.HTTP_400_BAD_REQUEST
                    )
                
        except Exception as e:
            import traceback
            error_details = traceback.format_exc()
            print(f"DETAILED ERROR in VerifyPickupOTPView: {str(e)}")
            print(f"FULL TRACEBACK: {error_details}")
            logger.error(f"Error in VerifyPickupOTPView: {str(e)}", exc_info=True)
            return Response(
                {
                    "error": "An error occurred while verifying OTP",
                    "details": str(e),
                    "debug_info": "Check server logs for full traceback"
                }, 
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

@swagger_auto_schema(tags=['Consumer'])
class CalculateDeliveryChargeView(APIView):
    """
    Calculate distance (KM) between store and user, and compute delivery charge.

    - Accepts either (user_lat, user_lng) or address_id referencing `UserAddress`.
    - Optional overrides via params/body: base_lat, base_lng, per_km, base_fee, free_km, max_km
    - Defaults: base_lat/base_lng from constants; per_km=5.0; base_fee=0; free_km=0; no max_km limit

    GET/POST params:
      user_lat, user_lng (float) OR address_id
      base_lat?, base_lng?
      per_km? (float), base_fee? (float), free_km? (float), max_km? (float)
    """

    def _get_float(self, params, key, default=None):
        val = params.get(key)
        if val is None or val == "":
            return default
        try:
            return float(val)
        except Exception:
            return default

    def _compute_charge(self, distance_km, per_km, base_fee, free_km):
        billable_km = max(0.0, float(distance_km) - float(free_km or 0.0))
        charge = float(base_fee or 0.0) + billable_km * float(per_km or 0.0)
        return round(charge, 2), billable_km

    def get(self, request, *args, **kwargs):
        return self._handle(request)

    def post(self, request, *args, **kwargs):
        return self._handle(request)

    def _handle(self, request):
        params = request.query_params if request.method == 'GET' else request.data

        base_lat = self._get_float(params, 'base_lat', DEFAULT_STORE_LAT)
        base_lng = self._get_float(params, 'base_lng', DEFAULT_STORE_LNG)

        user_lat = self._get_float(params, 'user_lat')
        user_lng = self._get_float(params, 'user_lng')
        address_id = params.get('address_id')

        per_km = self._get_float(params, 'per_km', 10.0)
        base_fee = self._get_float(params, 'base_fee', 0.0)
        free_km = self._get_float(params, 'free_km', 0.0)
        max_km = self._get_float(params, 'max_km', None)

        # If coordinates not provided, try to resolve from address_id
        if (user_lat is None or user_lng is None) and address_id:
            try:
                addr = UserAddress.objects.get(address_id=address_id)
                user_lat = getattr(addr, 'latitude', None)
                user_lng = getattr(addr, 'longitude', None)
                if user_lat is None or user_lng is None:
                    return Response({
                        "error": "Selected address does not have latitude/longitude saved."
                    }, status=status.HTTP_400_BAD_REQUEST)
            except UserAddress.DoesNotExist:
                return Response({'error': 'Address not found.'}, status=status.HTTP_404_NOT_FOUND)

        if user_lat is None or user_lng is None:
            return Response({'error': 'Provide user_lat and user_lng or a valid address_id.'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            distance_km = haversine_km(float(base_lat), float(base_lng), float(user_lat), float(user_lng))
        except Exception as e:
            return Response({'error': 'Invalid coordinates', 'details': str(e)}, status=status.HTTP_400_BAD_REQUEST)

        serviceable = True
        if max_km is not None and distance_km > float(max_km):
            serviceable = False

        charge, billable_km = self._compute_charge(distance_km, per_km, base_fee, free_km)

        return Response({
            'base': {'lat': float(base_lat), 'lng': float(base_lng)},
            'user': {'lat': float(user_lat), 'lng': float(user_lng), 'address_id': address_id},
            'distance_km': round(float(distance_km), 3),
            'free_km': float(free_km or 0.0),
            'billable_km': round(float(billable_km), 3),
            'per_km': float(per_km or 0.0),
            'base_fee': float(base_fee or 0.0),
            'charge': round(float(charge), 2),
            'serviceable': serviceable,
            'max_km': float(max_km) if max_km is not None else None,
        }, status=status.HTTP_200_OK)

class BusinessFeedbackView(APIView):
    """
    POST: Create multiple feedback entries for a business and user.
      - URL params: business_id (required), user_id (required)
      - Body: { user_name?, email?, additional_comments?, items: [{question, rating}, ...] }

    GET: List feedback entries, filtered by business_id (required) and optional user_id.
      - URL params: business_id (required), user_id (optional)
    """
    @swagger_auto_schema(tags=['Consumer'], request_body=BusinessFeedbackCreateSerializer)
    def post(self, request, *args, **kwargs):
        business_id = request.query_params.get('business_id')
        user_id = request.query_params.get('user_id')
        if not business_id or not user_id:
            return Response({
                'error': "business_id and user_id query parameters are required."
            }, status=status.HTTP_400_BAD_REQUEST)

        # Validate business and user
        try:
            business = Business.objects.get(business_id=business_id)
        except Business.DoesNotExist:
            return Response({'error': 'Business not found.'}, status=status.HTTP_404_NOT_FOUND)

        try:
            user = Registration.objects.get(user_id=user_id)
        except Registration.DoesNotExist:
            return Response({'error': 'User not found.'}, status=status.HTTP_404_NOT_FOUND)

        ser = BusinessFeedbackCreateSerializer(data=request.data)
        if not ser.is_valid():
            return Response(ser.errors, status=status.HTTP_400_BAD_REQUEST)

        data = ser.validated_data
        user_name = (data.get('user_name') or f"{user.firstName} {user.lastName}").strip()
        email = data.get('email') or user.emailID
        additional_comments = (data.get('additional_comments') or '').strip() or None

        created_items = []
        now = timezone.now()
        for item in data['items']:
            try:
                fb = BusinessFeedback.objects.create(
                    business=business,
                    user=user,
                    user_name=user_name,
                    email=email,
                    question=(item.get('question') or '')[:255],
                    rating=int(item.get('rating') or 0),
                    additional_comments=additional_comments,
                    created_at=now,
                    updated_at=now,
                )
                created_items.append(fb)
            except Exception as e:
                logger.error(f"Failed to create feedback item: {e}")

        out = BusinessFeedbackSerializer(created_items, many=True)
        return Response({
            'message': 'Feedback submitted',
            'created_count': len(created_items),
            'business_id': business_id,
            'user_id': str(user_id),
            'items': out.data,
        }, status=status.HTTP_201_CREATED)

    @swagger_auto_schema(tags=['Consumer'])
    def get(self, request, *args, **kwargs):
        business_id = request.query_params.get('business_id')
        if not business_id:
            return Response({'error': 'business_id parameter is required.'}, status=status.HTTP_400_BAD_REQUEST)

        qs = BusinessFeedback.objects.filter(business_id=business_id).order_by('-created_at')
        user_id = request.query_params.get('user_id')
        if user_id:
            qs = qs.filter(user_id=user_id)

        # Optional: group averages by question
        try:
            from django.db.models import Avg, Count
            agg = (
                qs.values('question')
                  .annotate(avg_rating=Avg('rating'), responses=Count('feedback_id'))
                  .order_by('question')
            )
            summary = [
                {
                    'question': row['question'],
                    'avg_rating': round(float(row['avg_rating'] or 0.0), 2),
                    'responses': int(row['responses'] or 0),
                }
                for row in agg
            ]
        except Exception:
            summary = []

        data = BusinessFeedbackSerializer(qs[:500], many=True).data  # limit to 500 for safety
        return Response({
            'business_id': business_id,
            'user_id': user_id,
            'total': qs.count(),
            'summary': summary,
            'results': data,
        }, status=status.HTTP_200_OK)