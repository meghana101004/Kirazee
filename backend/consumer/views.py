from django.db import connection
from rest_framework.decorators import api_view
from rest_framework.response import Response
from django.http import JsonResponse
import datetime, json
from rest_framework import status
from django.utils.timezone import now
from drf_yasg.utils import swagger_auto_schema
from .serializers import (BusinessSerializer, MenuItemsSerializer, productItemsSerializer, 
                         BusinessnearbySerializer, SearchResultSerializer, BusinessSearchSerializer, 
                         MenuItemSearchSerializer, ProductItemSearchSerializer)
from kirazee_app.models import Business
from business.models import MenuItems, productItems, FashionProductVariant, FashionProduct
from .gro_models import GroceriesProducts, GroceriesProductVariants, GroceriesOrderItems
from .models import Orders, OrderItems
from django.db.models import Sum, Count, Max, Min
from django.db.models import Q, Case, When, IntegerField
from django.db.models import Exists, OuterRef, F, Value
from django.db.models.functions import Lower
from .models import MenuCart
from geopy.distance import geodesic
import requests
import re
from django.db import models
from .combine import _build_media_response, _categorize_media_files, _process_sub_images
from consumer.image_utils import build_s3_file_url
from decimal import Decimal, ROUND_HALF_UP

def build_variant_groups(variants, source):
    """
    Build variant groups from variants attributes for frontend display.
    
    Args:
        variants: List of variant dictionaries
        source: Source type ('grocery', 'fashion', 'menu')
    
    Returns:
        List of variant groups with name and options
    """
    variant_groups_map = {}

    for v in variants:
        attrs = v.get('attributes') or {}

        for key, val in attrs.items():
            if not val:
                continue

            # Extract actual value - handle both simple values and JSON objects
            if isinstance(val, dict):
                actual_value = val.get("value")
            elif isinstance(val, str) and val.startswith("{'value':"):
                # Handle string representation of dict
                try:
                    import ast
                    parsed = ast.literal_eval(val)
                    actual_value = parsed.get("value")
                except Exception:
                    actual_value = val
            else:
                actual_value = val

            if not actual_value:
                continue

            if key not in variant_groups_map:
                variant_groups_map[key] = set()

            variant_groups_map[key].add(str(actual_value))

    # 🎯 CATEGORY PRIORITY
    if source == "fashion":
        priority = ["Size", "Color"]
    elif source == "grocery":
        priority = ["Weight", "Pack", "Size"]
    elif source == "menu":
        priority = ["Portion", "Size"]
    else:
        priority = []

    # ✅ FILTER: show all attributes (including single values) for product specifications
    filtered_groups = {}
    for key, values in variant_groups_map.items():
        if len(values) >= 1:  # 🔥 Show all attributes including single values
            filtered_groups[key] = values

    # Sort based on priority and limit to 2 groups
    sorted_keys = sorted(filtered_groups.keys(), key=lambda x: priority.index(x) if x in priority else 999)
    limited_keys = sorted_keys[:2]

    variant_groups = []
    for key in limited_keys:
        variant_groups.append({
            "name": key,
            "display_type": "text",
            "options": sorted(list(filtered_groups[key]))
        })

    return variant_groups

# Top N most-ordered items for a user (optionally by business)
@swagger_auto_schema(methods=['GET'], tags=['Consumer'])
@api_view(['GET'])
def most_ordered_items(request):
    """
    List top N most ordered items for a user, optionally filtered by business_id.

    URL patterns:
    - GET /kirazee/consumer/most-ordered-items/?user_id=U123&business_id=B456&limit=10
    - GET /kirazee/consumer/most-ordered-items/?user_id=U123&limit=10

    Returns combined items across menu (R02), restaurant products (productItems), and groceries
    (Groceries_Products + Groceries_ProductVariants_1) with absolute image URLs and pricing.
    """
    user_id = request.query_params.get('user_id')
    business_id = request.query_params.get('business_id')
    try:
        limit = int(request.query_params.get('limit', 10))
    except Exception:
        limit = 10
    if limit > 50:
        limit = 50

    if not user_id:
        return Response({
            'error': 'user_id is required as query parameter'
        }, status=status.HTTP_400_BAD_REQUEST)

    def build_image_url(raw_path: str):
        try:
            if not raw_path:
                return None
            s = str(raw_path).strip()
            if s.startswith('http://') or s.startswith('https://'):
                return s
            
            # Clean up path
            clean_path = s.lstrip('/')
            if clean_path.startswith('kirazee/'):
                clean_path = clean_path[8:]
            if clean_path.startswith('media/'):
                clean_path = clean_path[6:]
            
            # Use default_storage if available, else fallback to manual join
            from django.core.files.storage import default_storage
            try:
                url = default_storage.url(clean_path)
                if url.startswith('/'):
                    return build_s3_file_url(url).replace(' ', '%20')
                return build_s3_file_url(url).replace(' ', '%20')
            except Exception:
                # Fallback to S3 URL
                return build_s3_file_url(clean_path).replace(' ', '%20')
        except Exception:
            return None

    try:
        results = []
        with connection.cursor() as cursor:
            params = [user_id]
            where = "WHERE o.user_id = %s AND (o.status IS NULL OR o.status NOT IN ('cancelled','failed'))"
            if business_id:
                where += " AND o.business_id = %s"
                params.append(business_id)

            # Aggregate by canonical item id and include detail fields via MAX() to satisfy ONLY_FULL_GROUP_BY
            query = f"""
                SELECT 
                  bb.businessType AS business_type,
                  CASE 
                    WHEN oi.menu_item_id IS NOT NULL THEN 'menu'
                    WHEN bb.businessType = 'R01' THEN 'grocery'
                    WHEN bb.businessType = 'R08' THEN 'fashion'
                    ELSE 'product'
                  END AS item_kind,
                  CASE 
                    WHEN oi.menu_item_id IS NOT NULL THEN oi.menu_item_id
                    WHEN bb.businessType = 'R01' THEN COALESCE(gpv.product_id, oi.product_item_id)
                    WHEN bb.businessType = 'R08' THEN oi.product_item_id
                    ELSE oi.product_item_id
                  END AS canon_item_id,
                  o.business_id,
                  bb.businessName AS business_name,
                  COUNT(*) AS order_count,
                  SUM(oi.quantity) AS total_quantity,
                  MAX(o.created_at) AS last_ordered_at,
                  MAX(oi.item_name_snapshot) AS snap_name,
                  MAX(oi.unit_price_snapshot) AS snap_price,
                  -- menu details
                  MAX(m.item_name) AS menu_name,
                  MAX(m.item_image) AS menu_image,
                  MAX(m.item_category) AS menu_category,
                  MAX(m.item_type) AS menu_type,
                  MAX(m.selling_price) AS menu_price,
                  MAX(m.original_cost) AS menu_original_cost,
                 -- product-like items (restaurant products) - table may not exist; use placeholders
                 NULL AS prod_name,
                 NULL AS prod_image,
                 NULL AS prod_category,
                 NULL AS prod_type,
                 NULL AS prod_price,
                 NULL AS prod_original_cost,
                 -- groceries
                 MAX(COALESCE(gp.product_name, gp2.product_name)) AS gro_name,
                 MAX(COALESCE(gp.main_image, gp2.main_image)) AS gro_image,
                 MAX(COALESCE(gp.sub_category, gp2.sub_category)) AS gro_category,
                 MAX(COALESCE(gp.is_organic, gp2.is_organic)) AS gro_is_organic,
                 MAX(COALESCE(gp.rating, gp2.rating)) AS gro_rating,
                 MAX(gpv.selling_price) AS gro_price,
                 MAX(fp.name) AS fash_name,
                 MAX(fp.main_image) AS fash_image,
                 MAX(ucf.category_name) AS fash_category,
                 MAX(fpv.selling_price) AS fash_price,
                 MAX(fpv.variant_id) AS fash_variant_id,
                 MAX(fp.product_id) AS fash_product_id
                 FROM order_items oi
                 JOIN orders o ON o.order_id = oi.order_id
                 JOIN businesses bb ON bb.business_id = o.business_id
                 LEFT JOIN Groceries_ProductVariants_1 gpv ON bb.businessType = 'R01' AND gpv.variant_id = oi.product_item_id
                 LEFT JOIN Groceries_Products gp ON bb.businessType = 'R01' AND gp.product_id = gpv.product_id
                 LEFT JOIN Groceries_Products gp2 ON bb.businessType = 'R01' AND gp2.product_id = oi.product_item_id
                 LEFT JOIN fashion_product_variants fpv ON bb.businessType = 'R08' AND fpv.variant_id = oi.product_item_id AND fpv.is_active = 1
                 LEFT JOIN fashion_products fp ON bb.businessType = 'R08' AND fp.product_id = fpv.product_id AND fp.is_active = 1
                 LEFT JOIN universal_Categories ucf ON bb.businessType = 'R08' AND ucf.category_id = fp.category_id
                 LEFT JOIN menuItems m ON m.item_id = oi.menu_item_id
                 {where}
                 GROUP BY bb.businessType, item_kind, canon_item_id, o.business_id, bb.businessName
                 ORDER BY order_count DESC, total_quantity DESC, last_ordered_at DESC
                 LIMIT %s
            """
            params.append(limit)
            cursor.execute(query, params)
            rows = cursor.fetchall()

        rank = 0
        for row in rows:
            (
                business_type, item_kind, canon_item_id, row_business_id, business_name, order_count, total_qty, last_ordered_at,
                snap_name, snap_price,
                menu_name, menu_image, menu_category, menu_type, menu_price, menu_original_cost,
                prod_name, prod_image, prod_category, prod_type, prod_price, prod_original_cost,
                gro_name, gro_image, gro_category, gro_is_organic, gro_rating, gro_price,
                fash_name, fash_image, fash_category, fash_price, fash_variant_id, fash_product_id
            ) = row

            variant_id_out = None
            product_id_out = None
            if item_kind == 'menu' or menu_name:
                source = 'menu'
                item_name = menu_name or snap_name
                image_url = build_image_url(menu_image)
                selling_price = (
                    float(menu_price) if menu_price is not None else (
                        float(snap_price) if snap_price is not None else 0.0
                    )
                )
                original_cost = float(menu_original_cost) if menu_original_cost is not None else None
                category = menu_category
                type_label = menu_type
            elif item_kind == 'fashion' or fash_name:
                source = 'fashion'
                item_name = fash_name or snap_name
                image_url = build_image_url(fash_image)
                selling_price = (
                    float(fash_price) if fash_price is not None else (
                        float(snap_price) if snap_price is not None else 0.0
                    )
                )
                original_cost = None
                category = fash_category
                type_label = None
                try:
                    variant_id_out = int(canon_item_id) if canon_item_id is not None else None
                except Exception:
                    variant_id_out = None
                try:
                    product_id_out = int(fash_product_id) if fash_product_id is not None else None
                except Exception:
                    product_id_out = None
                # Format profile URL using S3
                profile_url_full = build_s3_file_url(profile_url)
            elif gro_name:
                source = 'grocery'
                item_name = gro_name or snap_name
                image_url = build_image_url(gro_image)
                selling_price = (
                    float(gro_price) if gro_price is not None else (
                        float(snap_price) if snap_price is not None else 0.0
                    )
                )
                original_cost = None
                category = gro_category
                type_label = None
            else:
                source = 'product'
                item_name = prod_name or snap_name
                image_url = build_image_url(prod_image) if prod_image else None
                selling_price = (
                    float(prod_price) if prod_price is not None else (
                        float(snap_price) if snap_price is not None else 0.0
                    )
                )
                original_cost = float(prod_original_cost) if prod_original_cost is not None else None
                category = prod_category
                type_label = prod_type

            rank += 1
            results.append({
                'rank': rank,
                'item_id': int(canon_item_id) if canon_item_id is not None else None,
                'variant_id': variant_id_out,
                'product_id': product_id_out,
                'business_id': row_business_id,
                'business_name': business_name,
                'source': source,  # menu | product | grocery
                'item_name': item_name,
                'image_url': image_url,
                'category': category,
                'type': type_label,
                'selling_price': selling_price,
                'original_cost': original_cost,
                'is_organic': bool(gro_is_organic) if gro_is_organic is not None else None,
                'rating': float(gro_rating) if gro_rating is not None else None,
                'order_count': int(order_count) if order_count is not None else 0,
                'total_quantity': int(total_qty) if total_qty is not None else 0,
                'last_ordered_at': (last_ordered_at.isoformat() if hasattr(last_ordered_at, 'isoformat') and last_ordered_at else None)
            })

        return Response({
            'success': True,
            'user_id': user_id,
            'business_id': business_id,
            'limit': limit,
            'items': results,
            'total_items': len(results),
            'message': f"Found top {len(results)} most ordered items for user {user_id}{' at business ' + business_id if business_id else ''}"
        }, status=status.HTTP_200_OK)

    except Exception as e:
        return Response({
            'error': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

#get near by businesses
@swagger_auto_schema(methods=['GET'], tags=['Consumer'])
@api_view(['GET'])
def nearby_businesses(request):
    """
    Get businesses within a specified radius of given coordinates, with sub-branches nested under their master branch
    """
    business_type = request.query_params.get('business_type')
    lat = request.query_params.get('lat')
    lng = request.query_params.get('lng')
    radius_km = float(request.query_params.get('radius', 5))  # Default 5km radius
    
    # Validate coordinates
    try:
        if not lat or not lng:
            return Response(
                {'error': 'Missing required parameters: lat and lng are required'},
                status=status.HTTP_400_BAD_REQUEST
            )
            
        user_lat = float(lat)
        user_lng = float(lng)
        user_location = (user_lat, user_lng)
        
    except (ValueError, TypeError) as e:
        return Response(
            {'error': 'Invalid coordinates', 'details': str(e)},
            status=status.HTTP_400_BAD_REQUEST
        )
    
    try:
        # Get businesses with valid coordinates (include inactive for greyed-out cards)
        businesses = Business.objects.filter(
            paymentstatus=True,
            latitude__isnull=False,
            longitude__isnull=False,
            status__in=[0, 1]
        ).order_by('-created_at')
        
        if business_type:
            businesses = businesses.filter(businessType=business_type)
        
        # Filter for master branches or standalone businesses (no master)
        master_businesses = businesses.filter(
            models.Q(level='Master Level') | models.Q(master__isnull=True) | models.Q(master='')
        )
        
        # Calculate distance for each master business and filter by radius
        nearby_masters = []
        for business in master_businesses:
            try:
                business_lat = float(business.latitude)
                business_lng = float(business.longitude)
                business_location = (business_lat, business_lng)                                                       
                distance = geodesic(user_location, business_location).kilometers
                
                # Debug log
                print(f"Business: {business.businessName}, Distance: {distance}km, Coordinates: ({business_lat}, {business_lng})")
                
                if distance <= radius_km:
                    business.distance_km = round(distance, 2)
                    nearby_masters.append(business)
            except (TypeError, ValueError) as e:
                # Skip businesses with invalid coordinates
                print(f"Skipping business {business.business_id} due to invalid coordinates")
                continue
        
        # Sort by latest created
        nearby_masters.sort(key=lambda x: x.created_at, reverse=True)
        
        # Debug log
        print(f"Found {len(nearby_masters)} businesses within {radius_km}km radius")
        
        # Serialize the master branches with their sub-branches
        serializer = BusinessnearbySerializer(
            nearby_masters, 
            many=True, 
            context={'request': request}
        )
        
        return Response(serializer.data)
        
    except Exception as e:
        import traceback
        print(f"Error in nearby_businesses: {str(e)}\n{traceback.format_exc()}")
        return Response(
            {'error': 'An error occurred while processing your request'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )

@swagger_auto_schema(methods=['GET'], tags=['Consumer'])
@api_view(['GET'])
def search(request):
    """
    Comprehensive search endpoint for businesses, menu items, and product items
    
    Query Parameters:
    - keyword: Search keyword (required)
    - type: Filter by type ('business', 'menu_item', 'product_item', 'all')
    - business_type: Filter by business type (R01, R02, etc.)
    - business_id: Filter by specific business ID
    - category: Filter by category
    - lat, lng: User location for distance calculation
    - radius: Search radius in km (default: 10)
    - min_price, max_price: Price range filter
    - sort_by: Sort results ('relevance', 'distance', 'price', 'rating')
    - limit: Maximum results per type (default: 20)
    """
    try:
        # Get query parameters
        keyword = request.query_params.get('keyword', '').strip()
        search_type = request.query_params.get('type', 'all').lower()
        business_type = request.query_params.get('business_type')
        business_id = request.query_params.get('business_id')
        category = request.query_params.get('category')
        latitude = request.query_params.get('lat')
        longitude = request.query_params.get('lng')
        radius_km = float(request.query_params.get('radius', 10))
        min_price = request.query_params.get('min_price')
        max_price = request.query_params.get('max_price')
        sort_by = request.query_params.get('sort_by', 'relevance')
        limit = int(request.query_params.get('limit', 20))
        
        if not keyword:
            return Response({
                'error': 'keyword parameter is required'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Prepare user location for distance calculation
        user_location = None
        if latitude and longitude:
            try:
                user_location = (float(latitude), float(longitude))
            except (ValueError, TypeError):
                pass
        
        results = []
        
        # Search businesses
        if search_type in ['all', 'business']:
            businesses = search_businesses(keyword, business_type, category, user_location, radius_km, min_price, max_price, limit, business_id)
            for business in businesses:
                results.append({
                    'result_type': 'business',
                    'id': business.business_id,
                    'name': business.businessName,
                    'description': business.description or '',
                    'image_url': get_logo_url(business, request),
                    'business_id': business.business_id,
                    'business_name': business.businessName,
                    'business_type': business.businessType,
                    'category': business.businessCategory,
                    'price': None,
                    'rating': 4.0,
                    'distance_km': getattr(business, 'distance_km', None),
                    'is_available': business.status and business.is_verified,
                    'location': f"{business.city}, {business.state}" if business.city else business.address,
                    'relevance_score': getattr(business, 'relevance_score', 0)
                })
        
        # Search menu items
        if search_type in ['all', 'menu_item']:
            menu_items = search_menu_items(keyword, business_type, category, user_location, radius_km, min_price, max_price, limit, business_id)
            for item in menu_items:
                results.append({
                    'result_type': 'menu_item',
                    'id': str(item.item_id),
                    'name': item.item_name,
                    'description': item.description or '',
                    'image_url': get_item_image_url(item, request),
                    'business_id': item.business_id.business_id,
                    'business_name': item.business_id.businessName,
                    'business_type': item.business_id.businessType,
                    'category': item.item_category,
                    'item_type': item.item_type,
                    'size_label': item.size_label,
                    'sku': item.sku,
                    'preparation_time': item.preparation_time,
                    'price': float(item.selling_price) if item.selling_price else None,
                    'rating': float(item.rating) if hasattr(item, 'rating') and item.rating else 4.0,
                    'distance_km': getattr(item, 'distance_km', None),
                    'is_available': item.is_active and item.status,
                    'location': f"{item.business_id.city}, {item.business_id.state}" if item.business_id.city else item.business_id.address,
                    'relevance_score': getattr(item, 'relevance_score', 0)
                })
        
        # Search product items
        if search_type in ['all', 'product_item']:
            product_items = search_product_items(keyword, business_type, category, user_location, radius_km, min_price, max_price, limit, business_id)
            for item in product_items:
                # Handle R01 (Grocery) products differently
                if business_type == 'R01':
                    # For R01, item is a GroceriesProducts object
                    results.append({
                        'result_type': 'product_item',
                        'id': str(item.product_id),
                        'name': item.product_name,
                        'description': item.description or '',
                        'image_url': build_s3_file_url(item.main_image),
                        'business_id': item.business.business_id,
                        'business_name': item.business.businessName,
                        'business_type': business_type,
                        'category': item.category.category_name if item.category else None,
                        'sub_category': item.sub_category,
                        'brand_name': item.brand_name,
                        'is_organic': item.is_organic,
                        'is_customizable': item.is_customizable,
                        'price': None,  # Price comes from variants
                        'rating': float(item.rating) if hasattr(item, 'rating') and item.rating else 4.0,
                        'distance_km': getattr(item, 'distance_km', None),
                        'is_available': item.is_visible,
                        'location': f"{item.business.city}, {item.business.state}" if item.business.city else item.business.address,
                        'relevance_score': getattr(item, 'relevance_score', 0)
                    })
                else:
                    # For other business types, item is a productItems object
                    results.append({
                        'result_type': 'product_item',
                        'id': str(item.item_id),
                        'name': item.item_name,
                        'description': item.description or '',
                        'image_url': get_item_image_url(item, request),
                        'business_id': item.business_id.business_id,
                        'business_name': item.business_id.businessName,
                        'business_type': item.business_id.businessType,
                        'category': item.item_category,
                        'material': item.material,
                        'color': item.color,
                        'size': item.size,
                        'weight': item.weight,
                        'unit': item.unit,
                        'stock': item.stock,
                        'price': float(item.selling_price) if item.selling_price else None,
                        'rating': float(item.rating) if hasattr(item, 'rating') and item.rating else 4.0,
                        'distance_km': getattr(item, 'distance_km', None),
                        'is_available': item.is_active and item.status and (item.stock > 0 if item.stock is not None else True),
                        'location': f"{item.business_id.city}, {item.business_id.state}" if item.business_id.city else item.business_id.address,
                        'relevance_score': getattr(item, 'relevance_score', 0)
                    })

        if search_type in ['all', 'fashion_item', 'product_item']:
            fashion_items = search_fashion_items(keyword, business_type, category, user_location, radius_km, min_price, max_price, limit, business_id)
            for v in fashion_items:
                product = getattr(v, 'product', None)
                business_obj = getattr(v, 'business_id', None)
                results.append({
                    'result_type': 'fashion_item',
                    'id': str(getattr(v, 'variant_id', None)),
                    'name': getattr(product, 'name', None),
                    'description': getattr(product, 'description', '') or '',
                    'image_url': build_s3_file_url(getattr(product, 'main_image', None)),
                    'business_id': getattr(business_obj, 'business_id', None),
                    'business_name': getattr(business_obj, 'businessName', None),
                    'business_type': getattr(business_obj, 'businessType', None),
                    'category': getattr(getattr(product, 'category', None), 'category_name', None),
                    'price': float(getattr(v, 'selling_price', 0) or 0),
                    'rating': float(getattr(product, 'rating', 4.0) or 4.0),
                    'distance_km': getattr(v, 'distance_km', None),
                    'is_available': bool(getattr(v, 'is_active', True)) and (int(getattr(v, 'stock', 0) or 0) > 0 or int(getattr(v, 'stock_qty', 0) or 0) > 0),
                    'location': f"{getattr(business_obj, 'city', None)}, {getattr(business_obj, 'state', None)}" if getattr(business_obj, 'city', None) else getattr(business_obj, 'address', None),
                    'product_id': getattr(product, 'product_id', None),
                    'variant_id': getattr(v, 'variant_id', None),
                    'size': getattr(v, 'size', None),
                    'color': getattr(v, 'color', None),
                    'material': getattr(v, 'material', None),
                    'gender': getattr(v, 'gender', None),
                    'sku': getattr(v, 'sku', None),
                    'barcode': getattr(v, 'barcode', None),
                    'net_weight': getattr(v, 'net_weight', None),
                    'net_weight_unit': getattr(v, 'net_weight_unit', None),
                    'brand': getattr(product, 'brand', None),
                    'hsn_code': getattr(product, 'hsn_code', None),
                    'relevance_score': getattr(v, 'relevance_score', 0)
                })
        
        # Sort results
        results = sort_search_results(results, sort_by)
        
        # Prepare response
        response_data = {
            'keyword': keyword,
            'total_results': len(results),
            'search_type': search_type,
            'results': results[:100],  # Limit total results to 100
            'filters_applied': {
                'business_type': business_type,
                'category': category,
                'location_based': user_location is not None,
                'price_range': {
                    'min': min_price,
                    'max': max_price
                } if min_price or max_price else None
            },
            'sort_by': sort_by
        }
        
        return Response(response_data, status=status.HTTP_200_OK)
        
    except Exception as e:
        return Response({
            'error': 'Search failed',
            'details': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

@swagger_auto_schema(methods=['GET'],tags=['Consumer'])
@api_view(['GET'])
def business_search(request):
    try:
        keyword = (request.query_params.get('keyword') or '').strip()
        if not keyword:
            return Response({'error': 'keyword parameter is required'}, status=status.HTTP_400_BAD_REQUEST)

        business_type = request.query_params.get('business_type')
        latitude = request.query_params.get('lat')
        longitude = request.query_params.get('lng')
        try:
            radius_km = float(request.query_params.get('radius', 10))
        except Exception:
            radius_km = 10.0
        try:
            limit = int(request.query_params.get('limit', 20))
        except Exception:
            limit = 20
        try:
            offset = int(request.query_params.get('offset', 0))
        except Exception:
            offset = 0

        user_location = None
        if latitude and longitude:
            try:
                user_location = (float(latitude), float(longitude))
            except (TypeError, ValueError):
                user_location = None

        menu_name_sq = MenuItems.objects.filter(
            business_id=OuterRef('business_id'),
            is_active=True,
            status=True,
            item_name__icontains=keyword
        )
        menu_cat_sq = MenuItems.objects.filter(
            business_id=OuterRef('business_id'),
            is_active=True,
            status=True,
            item_category__icontains=keyword
        )
        groc_name_sq = GroceriesProducts.objects.filter(
            business_id=OuterRef('business_id'),
            product_name__icontains=keyword
        )
        groc_cat_sq = GroceriesProducts.objects.filter(
            business_id=OuterRef('business_id'),
            category__category_name__icontains=keyword
        )

        fashion_name_sq = FashionProduct.objects.filter(
            business_id=OuterRef('business_id'),
            is_active=True,
            name__icontains=keyword
        )
        fashion_cat_sq = FashionProduct.objects.filter(
            business_id=OuterRef('business_id'),
            is_active=True,
            category__category_name__icontains=keyword
        )

        businesses = Business.objects.filter(status=True)
        if business_type:
            businesses = businesses.filter(businessType=business_type)

        businesses = businesses.annotate(
            has_menu_name=Exists(menu_name_sq),
            has_menu_category=Exists(menu_cat_sq),
            has_groc_product=Exists(groc_name_sq),
            has_groc_category=Exists(groc_cat_sq),
            has_fashion_product=Exists(fashion_name_sq),
            has_fashion_category=Exists(fashion_cat_sq),
            name_exact=Case(
                When(businessName__iexact=keyword, then=Value(1)),
                default=Value(0),
                output_field=IntegerField()
            ),
            name_like=Case(
                When(businessName__iexact=keyword, then=Value(0)),
                When(businessName__icontains=keyword, then=Value(1)),
                default=Value(0),
                output_field=IntegerField()
            ),
            desc_like=Case(
                When(description__icontains=keyword, then=Value(1)),
                default=Value(0),
                output_field=IntegerField()
            ),
        ).filter(
            Q(name_exact=1) |
            Q(name_like=1) |
            Q(desc_like=1) |
            Q(has_menu_name=True) |
            Q(has_menu_category=True) |
            Q(has_groc_product=True) |
            Q(has_groc_category=True) |
            Q(has_fashion_product=True) |
            Q(has_fashion_category=True)
        )

        results = []
        for b in businesses:
            score = (
                10 * int(getattr(b, 'name_exact', 0) or 0) +
                5 * int(getattr(b, 'name_like', 0) or 0) +
                4 * (1 if getattr(b, 'has_menu_name', False) else 0) +
                3 * (1 if getattr(b, 'has_menu_category', False) else 0) +
                3 * (1 if getattr(b, 'has_groc_product', False) else 0) +
                2 * (1 if getattr(b, 'has_groc_category', False) else 0) +
                3 * (1 if getattr(b, 'has_fashion_product', False) else 0) +
                2 * (1 if getattr(b, 'has_fashion_category', False) else 0) +
                1 * int(getattr(b, 'desc_like', 0) or 0)
            )

            distance_km = None
            if user_location and b.latitude is not None and b.longitude is not None:
                try:
                    business_location = (float(b.latitude), float(b.longitude))
                    distance_km = geodesic(user_location, business_location).kilometers
                except Exception:
                    distance_km = None

            results.append({
                'business_id': b.business_id,
                'business_name': b.businessName,
                'business_type': b.businessType,
                'category': b.businessCategory,
                'image_url': get_logo_url(b, request),
                'distance_km': round(distance_km, 2) if isinstance(distance_km, (int, float)) else None,
                'relevance_score': int(score),
                'matches': [
                    m for m, ok in [
                        ('business_name', bool(getattr(b, 'name_exact', 0) or getattr(b, 'name_like', 0))),
                        ('business_description', bool(getattr(b, 'desc_like', 0))),
                        ('menu_item_name', bool(getattr(b, 'has_menu_name', False))),
                        ('menu_item_category', bool(getattr(b, 'has_menu_category', False))),
                        ('grocery_product_name', bool(getattr(b, 'has_groc_product', False))),
                        ('grocery_category_name', bool(getattr(b, 'has_groc_category', False))),
                        ('fashion_product_name', bool(getattr(b, 'has_fashion_product', False))),
                        ('fashion_category_name', bool(getattr(b, 'has_fashion_category', False))),
                    ] if ok
                ],
            })

        if user_location:
            results = [r for r in results if r.get('distance_km') is not None and r['distance_km'] <= radius_km]
            results.sort(key=lambda x: (x['distance_km'], -x['relevance_score'], x['business_name']))
        else:
            results.sort(key=lambda x: (-x['relevance_score'], x['business_name']))

        total = len(results)
        sliced = results[offset:offset + limit]

        return Response({
            'success': True,
            'keyword': keyword,
            'total': total,
            'offset': offset,
            'limit': limit,
            'results': sliced
        }, status=status.HTTP_200_OK)

    except Exception as e:
        return Response({
            'error': 'Business search failed',
            'details': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

def search_businesses(keyword, business_type, category, user_location, radius_km, min_price, max_price, limit, business_id=None):
    """Search businesses with comprehensive keyword matching and filters"""
    # Build comprehensive search query with enhanced relevance scoring
    businesses = Business.objects.filter(
        Q(businessName__icontains=keyword) |
        Q(description__icontains=keyword) |
        Q(businessCategory__icontains=keyword) |
        Q(address__icontains=keyword) |
        Q(city__icontains=keyword) |
        Q(state__icontains=keyword) |
        Q(pincode__icontains=keyword)
    ).annotate(
        relevance_score=Case(
            When(businessName__iexact=keyword, then=10),
            When(businessName__icontains=keyword, then=8),
            When(businessCategory__iexact=keyword, then=7),
            When(businessCategory__icontains=keyword, then=6),
            When(description__iexact=keyword, then=5),
            When(description__icontains=keyword, then=4),
            When(city__iexact=keyword, then=5),
            When(city__icontains=keyword, then=4),
            When(address__iexact=keyword, then=3),
            When(address__icontains=keyword, then=2),
            When(state__iexact=keyword, then=3),
            When(state__icontains=keyword, then=2),
            When(pincode__iexact=keyword, then=3),
            When(pincode__icontains=keyword, then=2),
            default=0,
            output_field=IntegerField()
        )
    ).filter(status=True)
    
    # Apply filters
    if business_type:
        businesses = businesses.filter(businessType=business_type)
    
    # Apply business_id filter if provided
    if business_id:
        businesses = businesses.filter(business_id=business_id)
    
    if category:
        businesses = businesses.filter(businessCategory__icontains=category)
    
    # Apply location-based filtering
    if user_location:
        businesses = businesses.exclude(latitude__isnull=True, longitude__isnull=True)
        nearby_businesses = []
        for business in businesses:
            if business.latitude and business.longitude:
                business_location = (business.latitude, business.longitude)
                distance = geodesic(user_location, business_location).kilometers
                if distance <= radius_km:
                    business.distance_km = round(distance, 2)
                    nearby_businesses.append(business)
        businesses = nearby_businesses
    else:
        businesses = list(businesses)
    
    # Sort by relevance and limit
    if hasattr(businesses[0] if businesses else None, 'relevance_score'):
        businesses.sort(key=lambda x: x.relevance_score, reverse=True)
    
    return businesses[:limit]

def search_menu_items(keyword, business_type, category, user_location, radius_km, min_price, max_price, limit, business_id=None):
    """Search menu items with keyword matching and filters"""
    # Build comprehensive search query across all relevant fields
    menu_items = MenuItems.objects.select_related('business_id').filter(
        Q(item_name__icontains=keyword) |
        Q(description__icontains=keyword) |
        Q(item_category__icontains=keyword) |
        Q(item_type__icontains=keyword) |
        Q(size_label__icontains=keyword) |
        Q(sku__icontains=keyword) |
        Q(preparation_time__icontains=keyword) |
        Q(business_id__businessName__icontains=keyword) |
        Q(business_id__businessCategory__icontains=keyword) |
        Q(business_id__address__icontains=keyword) |
        Q(business_id__city__icontains=keyword)
    ).annotate(
        relevance_score=Case(
            When(item_name__iexact=keyword, then=10),
            When(item_name__icontains=keyword, then=8),
            When(item_category__iexact=keyword, then=7),
            When(item_category__icontains=keyword, then=6),
            When(item_type__iexact=keyword, then=5),
            When(item_type__icontains=keyword, then=4),
            When(description__iexact=keyword, then=3),
            When(description__icontains=keyword, then=2),
            When(sku__iexact=keyword, then=3),
            When(sku__icontains=keyword, then=2),
            When(business_id__businessName__iexact=keyword, then=2),
            When(business_id__businessName__icontains=keyword, then=1),
            default=0,
            output_field=IntegerField()
        )
    ).filter(is_active=True, status=True, business_id__status=True)
    
    # Apply business_id filter if provided
    if business_id:
        menu_items = menu_items.filter(business_id__business_id=business_id)
    
    # Apply filters
    if business_type:
        menu_items = menu_items.filter(business_id__businessType=business_type)
    
    if category:
        menu_items = menu_items.filter(item_category__icontains=category)
    
    if min_price:
        menu_items = menu_items.filter(selling_price__gte=float(min_price))
    
    if max_price:
        menu_items = menu_items.filter(selling_price__lte=float(max_price))
    
    # Apply location-based filtering
    if user_location:
        menu_items = menu_items.exclude(business_id__latitude__isnull=True, business_id__longitude__isnull=True)
        nearby_items = []
        for item in menu_items:
            if item.business_id.latitude and item.business_id.longitude:
                business_location = (item.business_id.latitude, item.business_id.longitude)
                distance = geodesic(user_location, business_location).kilometers
                if distance <= radius_km:
                    item.distance_km = round(distance, 2)
                    nearby_items.append(item)
        menu_items = nearby_items
    else:
        menu_items = list(menu_items)
    
    # Sort by relevance and limit
    if hasattr(menu_items[0] if menu_items else None, 'relevance_score'):
        menu_items.sort(key=lambda x: x.relevance_score, reverse=True)
    
    return menu_items[:limit]

def search_product_items(keyword, business_type, category, user_location, radius_km, min_price, max_price, limit, business_id=None):
    """Search product items with keyword matching and filters"""
    
    # For R01 (Grocery) businesses, use GroceriesProducts and GroceriesProductVariants
    if business_type == 'R01':
        # Search GroceriesProducts (main products)
        products = GroceriesProducts.objects.select_related('business', 'category').filter(
            Q(product_name__icontains=keyword) |
            Q(description__icontains=keyword) |
            Q(category__category_name__icontains=keyword) |
            Q(sub_category__icontains=keyword) |
            Q(brand_name__icontains=keyword) |
            Q(business__businessName__icontains=keyword) |
            Q(business__businessCategory__icontains=keyword) |
            Q(business__address__icontains=keyword) |
            Q(business__city__icontains=keyword)
        ).annotate(
            relevance_score=Case(
                When(product_name__iexact=keyword, then=10),
                When(product_name__icontains=keyword, then=8),
                When(category__category_name__iexact=keyword, then=7),
                When(category__category_name__icontains=keyword, then=6),
                When(brand_name__iexact=keyword, then=5),
                When(brand_name__icontains=keyword, then=4),
                When(description__iexact=keyword, then=3),
                When(description__icontains=keyword, then=2),
                When(business__businessName__iexact=keyword, then=2),
                When(business__businessName__icontains=keyword, then=1),
                default=0,
                output_field=IntegerField()
            )
        ).filter(is_visible=True, business__status=True)
        
        # Apply business_id filter if provided
        if business_id:
            products = products.filter(business__business_id=business_id)
        
        # Apply category filter
        if category:
            products = products.filter(category__category_name__icontains=category)
        
        # Apply price filter using variants
        if min_price or max_price:
            variant_subquery = GroceriesProductVariants.objects.filter(
                product_id=OuterRef('product_id')
            ).order_by('selling_price')
            
            if min_price:
                variant_subquery = variant_subquery.filter(selling_price__gte=float(min_price))
            if max_price:
                variant_subquery = variant_subquery.filter(selling_price__lte=float(max_price))
            
            products = products.annotate(
                has_price_variant=Exists(variant_subquery)
            ).filter(has_price_variant=True)
        
        # Apply location-based filtering
        if user_location:
            products = products.exclude(business__latitude__isnull=True, business__longitude__isnull=True)
            nearby_products = []
            for product in products:
                if product.business.latitude and product.business.longitude:
                    business_location = (product.business.latitude, product.business.longitude)
                    distance = geodesic(user_location, business_location).kilometers
                    if distance <= radius_km:
                        product.distance_km = round(distance, 2)
                        nearby_products.append(product)
            products = nearby_products
        else:
            products = list(products)
        
        # Sort by relevance and limit
        if hasattr(products[0] if products else None, 'relevance_score'):
            products.sort(key=lambda x: x.relevance_score, reverse=True)
        
        return products[:limit]
    
    # For other business types, use productItems model
    else:
        product_items = productItems.objects.select_related('business_id').filter(
            Q(item_name__icontains=keyword) |
            Q(description__icontains=keyword) |
            Q(item_category__icontains=keyword) |
            Q(material__icontains=keyword) |
            Q(color__icontains=keyword) |
            Q(size__icontains=keyword) |
            Q(weight__icontains=keyword) |
            Q(unit__icontains=keyword) |
            Q(business_id__businessName__icontains=keyword) |
            Q(business_id__businessCategory__icontains=keyword) |
            Q(business_id__address__icontains=keyword) |
            Q(business_id__city__icontains=keyword)
        ).annotate(
            relevance_score=Case(
                When(item_name__iexact=keyword, then=10),
                When(item_name__icontains=keyword, then=8),
                When(item_category__iexact=keyword, then=7),
                When(item_category__icontains=keyword, then=6),
                When(material__iexact=keyword, then=5),
                When(material__icontains=keyword, then=4),
                When(color__iexact=keyword, then=5),
                When(color__icontains=keyword, then=4),
                When(size__iexact=keyword, then=5),
                When(size__icontains=keyword, then=4),
                When(description__iexact=keyword, then=3),
                When(description__icontains=keyword, then=2),
                When(business_id__businessName__iexact=keyword, then=2),
                When(business_id__businessName__icontains=keyword, then=1),
                default=0,
                output_field=IntegerField()
            )
        ).filter(is_active=True, status=True, business_id__status=True)
        
        # Apply business_id filter if provided
        if business_id:
            product_items = product_items.filter(business_id__business_id=business_id)
        
        # Apply filters
        if business_type:
            product_items = product_items.filter(business_id__businessType=business_type)
        
        if category:
            product_items = product_items.filter(item_category__icontains=category)
        
        if min_price:
            product_items = product_items.filter(selling_price__gte=float(min_price))
        
        if max_price:
            product_items = product_items.filter(selling_price__lte=float(max_price))
        
        # Apply location-based filtering
        if user_location:
            product_items = product_items.exclude(business_id__latitude__isnull=True, business_id__longitude__isnull=True)
            nearby_items = []
            for item in product_items:
                if item.business_id.latitude and item.business_id.longitude:
                    business_location = (item.business_id.latitude, item.business_id.longitude)
                    distance = geodesic(user_location, business_location).kilometers
                    if distance <= radius_km:
                        item.distance_km = round(distance, 2)
                        nearby_items.append(item)
            product_items = nearby_items
        else:
            product_items = list(product_items)
        
        # Sort by relevance and limit
        if hasattr(product_items[0] if product_items else None, 'relevance_score'):
            product_items.sort(key=lambda x: x.relevance_score, reverse=True)
        
        return product_items[:limit]

def search_fashion_items(keyword, business_type, category, user_location, radius_km, min_price, max_price, limit, business_id=None):
    """Search fashion items with comprehensive keyword matching and filters"""
    items = FashionProductVariant.objects.select_related('product', 'business_id', 'product__category').filter(
        Q(product__name__icontains=keyword) |
        Q(product__description__icontains=keyword) |
        Q(product__category__category_name__icontains=keyword) |
        Q(size__icontains=keyword) |
        Q(color__icontains=keyword) |
        Q(material__icontains=keyword) |
        Q(gender__icontains=keyword) |
        Q(sku__icontains=keyword) |
        Q(barcode__icontains=keyword) |
        Q(net_weight__icontains=keyword) |
        Q(net_weight_unit__icontains=keyword) |
        Q(product__brand__icontains=keyword) |
        Q(product__hsn_code__icontains=keyword) |
        Q(business_id__businessName__icontains=keyword) |
        Q(business_id__businessCategory__icontains=keyword) |
        Q(business_id__address__icontains=keyword) |
        Q(business_id__city__icontains=keyword)
    ).filter(is_active=True, product__is_active=True, business_id__status=True)

    # Apply business_id filter if provided
    if business_id:
        items = items.filter(business_id__business_id=business_id)

    # Add relevance scoring
    items = items.annotate(
        relevance_score=Case(
            When(product__name__iexact=keyword, then=10),
            When(product__name__icontains=keyword, then=8),
            When(product__category__category_name__iexact=keyword, then=7),
            When(product__category__category_name__icontains=keyword, then=6),
            When(size__iexact=keyword, then=5),
            When(size__icontains=keyword, then=4),
            When(color__iexact=keyword, then=5),
            When(color__icontains=keyword, then=4),
            When(material__iexact=keyword, then=5),
            When(material__icontains=keyword, then=4),
            When(gender__iexact=keyword, then=5),
            When(gender__icontains=keyword, then=4),
            When(sku__iexact=keyword, then=3),
            When(sku__icontains=keyword, then=2),
            When(product__description__iexact=keyword, then=3),
            When(product__description__icontains=keyword, then=2),
            When(product__brand__iexact=keyword, then=3),
            When(product__brand__icontains=keyword, then=2),
            When(business_id__businessName__iexact=keyword, then=2),
            When(business_id__businessName__icontains=keyword, then=1),
            default=0,
            output_field=IntegerField()
        )
    )

    if business_type:
        items = items.filter(business_id__businessType=business_type)

    if category:
        items = items.filter(product__category__category_name__icontains=category)

    if min_price:
        items = items.filter(selling_price__gte=float(min_price))

    if max_price:
        items = items.filter(selling_price__lte=float(max_price))

    items = list(items)
    if user_location:
        items = [i for i in items if getattr(getattr(i, 'business_id', None), 'latitude', None) is not None and getattr(getattr(i, 'business_id', None), 'longitude', None) is not None]
        nearby = []
        for it in items:
            try:
                b = getattr(it, 'business_id', None)
                business_location = (float(b.latitude), float(b.longitude))
                distance = geodesic(user_location, business_location).kilometers
                if distance <= radius_km:
                    it.distance_km = round(distance, 2)
                    nearby.append(it)
            except Exception:
                continue
        items = nearby

    return items[:limit]

def sort_search_results(results, sort_by):
    """Sort search results based on specified criteria"""
    if sort_by == 'distance' and any(r.get('distance_km') for r in results):
        # Sort by distance (closest first), then by relevance
        results.sort(key=lambda x: (x.get('distance_km') or float('inf'), -x.get('relevance_score', 0)))
    elif sort_by == 'price':
        # Sort by price (lowest first)
        results.sort(key=lambda x: x.get('price') or float('inf'))
    elif sort_by == 'rating':
        # Sort by rating (highest first)
        results.sort(key=lambda x: x.get('rating') or 0, reverse=True)
    else:  # relevance (default)
        # Sort by result type priority and relevance
        type_priority = {'business': 1, 'menu_item': 2, 'product_item': 3, 'fashion_item': 3}
        results.sort(key=lambda x: (type_priority.get(x.get('result_type'), 4), -x.get('relevance_score', 0)))
    
    return results

def get_logo_url(business, request=None):
    """Helper function to get business logo URL - returns S3 URL"""
    return build_s3_file_url(business.logo)

def get_item_image_url(item, request=None):
    """Helper function to get item image URL - returns S3 URL"""
    return build_s3_file_url(item.item_image)

def build_absolute_media_url(request, path):
    """Build S3 URL for a stored media path or return as-is if already absolute."""
    return build_s3_file_url(path)

def _apply_offer_metadata(item_dict, selling_price, original_cost):
    """Apply offer metadata to item dictionary."""
    try:
        sp = Decimal(str(selling_price or '0'))
        oc = Decimal(str(original_cost or '0'))
        
        if oc > 0 and sp < oc:
            diff = oc - sp
            if diff > 0:
                percent = (diff / oc * Decimal(100))
                percent_display = int(percent.quantize(Decimal('1'), rounding=ROUND_HALF_UP))
                diff_display = int(diff.quantize(Decimal('1'), rounding=ROUND_HALF_UP))
                
                item_dict.update({
                    'diff_amount': str(diff.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)),
                    'percent': str(percent.quantize(Decimal('0.1'), rounding=ROUND_HALF_UP)),
                    'percent_display': percent_display,
                    'diff_display': diff_display,
                    'discount_percentage': percent_display,
                })
        else:
            item_dict.update({
                'diff_amount': "0.00",
                'percent': "0.0",
                'percent_display': 0,
                'diff_display': 0,
                'discount_percentage': 0,
            })
    except Exception:
        item_dict.update({
            'diff_amount': "0.00",
            'percent': "0.0",
            'percent_display': 0,
            'diff_display': 0,
            'discount_percentage': 0,
        })

def _is_item_new(created_at):
    """Check if item is considered new (created within last 30 days)."""
    if not created_at:
        return False
    try:
        from django.utils import timezone
        now = timezone.now()
        if isinstance(created_at, str):
            from datetime import datetime
            created_at = datetime.fromisoformat(created_at.replace('Z', '+00:00'))
        return (now - created_at).days <= 30
    except Exception:
        return False

def _is_item_bestseller(item_id, business_id, business_type):
    """Check if item is a bestseller based on order history."""
    try:
        if not item_id or not business_id:
            return False
            
        # Simple bestseller logic: more than 10 orders
        if business_type == 'R02':
            from .models import OrderItems, Orders
            count = OrderItems.objects.filter(
                menu_item_id=item_id,
                order_id__business_id=business_id
            ).exclude(order_id__status=Orders.OrderStatus.CANCELLED).count()
        elif business_type == 'R01':
            from .gro_models import GroceriesOrderItems
            count = GroceriesOrderItems.objects.filter(
                product_id=item_id,
                order__business_id=business_id
            ).exclude(order__order_status='cancelled').count()
        elif business_type == 'R08':
            from .models import OrderItems, Orders
            count = OrderItems.objects.filter(
                product_item_id=item_id,
                order_id__business_id=business_id
            ).exclude(order_id__status=Orders.OrderStatus.CANCELLED).count()
        else:
            return False
            
        return count > 10
    except Exception:
        return False

def _attach_badges_from_offer_fields(item_data):
    """Attach badges array based on offer fields."""
    badges = []
    
    # New badge
    if item_data.get('is_new', False):
        badges.append({'type': 'new', 'text': 'New'})
    
    # Bestseller badge
    if item_data.get('is_bestseller', False):
        badges.append({'type': 'bestseller', 'text': 'Bestseller'})
    
    # Featured offer badge
    if item_data.get('is_featured_offer', False):
        badges.append({'type': 'featured', 'text': 'Featured'})
    
    # Discount badge
    if item_data.get('percent_display', 0) > 0:
        badges.append({
            'type': 'discount', 
            'text': f"{item_data['percent_display']}% OFF"
        })
    
    item_data['badges'] = badges

@swagger_auto_schema(methods=['GET'],tags=['Consumer'])
@api_view(['GET'])
def item_detail(request):
    """
    Item detail view for MenuItems (R02), GroceriesProducts (R01), and FashionProducts (R08).

    Query params:
    - type: 'R01', 'R02', or 'R08' (business type)
    - menu_item_id: MenuItems.item_id (for R02)
    - product_id: Product ID (for R01 and R08)
    - variant_id: Optional variant ID (for R01 and R08)
    
    Returns:
    - item: basic info + media
    - order_stats: total_orders, total_quantity_sold, last_ordered_at
    """
    try:
        # Import service functions from combine.py
        from .combine import (
            _service_item_detail_r02, 
            _service_item_detail_r01, 
            _service_item_detail_r08
        )
        
        business_type = (request.query_params.get('type') or request.query_params.get('business_type') or '').strip().upper()
        
        if business_type not in ['R01', 'R02', 'R08']:
            return Response({
                'success': False, 
                'error': "Provide 'type' as 'R01', 'R02', or 'R08' with appropriate IDs"
            }, status=status.HTTP_400_BAD_REQUEST)

        # Dispatch to appropriate service based on business type
        if business_type == 'R02':
            # Restaurant/Menu item details
            item_id = (
                request.query_params.get('menu_item_id')
                or request.query_params.get('item_id')
                or request.query_params.get('product_id')
                or request.query_params.get('product_item_id')
            )
            
            result, status_code = _service_item_detail_r02(request, business_type, item_id)
            return Response(result, status=status_code)

        elif business_type == 'R01':
            # Grocery product details
            product_id = request.query_params.get('product_id') or request.query_params.get('product_item_id')
            variant_id = request.query_params.get('variant_id')
            
            result, status_code = _service_item_detail_r01(request, business_type, product_id, variant_id)
            return Response(result, status=status_code)

        elif business_type == 'R08':
            # Fashion product details
            product_id = request.query_params.get('product_id')
            variant_id = request.query_params.get('variant_id')
            
            result, status_code = _service_item_detail_r08(request, business_type, product_id, variant_id)
            return Response(result, status=status_code)

    except Exception as e:
        return Response({'success': False, 'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

#get busiensses
@swagger_auto_schema(methods=['POST'],tags=['Consumer'])
@api_view(['POST'])
def business(request):
    business_type = request.query_params.get('type', None)
    business_id = request.query_params.get('business_id', None)

    # If business_id is provided, filter by it (with optional type filter)
    if business_id:
        if business_type:
            query = "SELECT * FROM businesses WHERE business_id = %s AND businessType = %s AND status != 2 AND is_visible = 1 AND is_verified = 1 ORDER BY created_at DESC"
            businesses = Business.objects.raw(query, [business_id, business_type])
        else:
            query = "SELECT * FROM businesses WHERE business_id = %s AND status != 2 AND is_visible = 1 AND is_verified = 1 ORDER BY created_at DESC"
            businesses = Business.objects.raw(query, [business_id])
    elif business_type:
        query = "SELECT * FROM businesses WHERE businessType = %s AND status != 2 AND is_visible = 1 AND is_verified = 1 ORDER BY created_at DESC"
        businesses = Business.objects.raw(query, [business_type])
    else:
        query = "SELECT * FROM businesses WHERE status != 2 AND is_visible = 1 AND is_verified = 1 ORDER BY created_at DESC"
        businesses = Business.objects.raw(query)

    serializer = BusinessSerializer(businesses, many=True, context={'request': request})
    return Response(serializer.data, status=status.HTTP_200_OK)


#get menu items
@swagger_auto_schema(methods=['POST'],tags=['Consumer'])
@api_view(['POST'])
def MenuItemsView(request):
    if request.method == 'POST':
        business_id = request.query_params.get("business_id", None)
        
        if business_id:
            query = "SELECT * FROM menuItems WHERE business_id = %s"
            menu_items = MenuItems.objects.raw(query, [business_id])
        else:
            query = "SELECT * FROM menuItems"
            menu_items = MenuItems.objects.raw(query)

        serializer = MenuItemsSerializer(menu_items, many=True, context={'request': request})
        return Response(serializer.data, status=status.HTTP_200_OK)

#get product items
@swagger_auto_schema(methods=['POST'],tags=['Consumer'])
@api_view(['POST'])
def productItemsView(request):
    if request.method == 'POST':
        business_id = request.query_params.get("business_id", None)
        
        if business_id:
            query = "SELECT * FROM Groceries WHERE business_id = %s"
            product_items = productItems.objects.raw(query, [business_id])
        else:
            query = "SELECT * FROM Groceries"
            product_items = productItems.objects.raw(query)

        serializer = productItemsSerializer(product_items, many=True, context={'request': request})
        return Response(serializer.data, status=status.HTTP_200_OK)

#add to cart for restaurants
@swagger_auto_schema(methods=['POST'],tags=['Consumer'])
@api_view(['POST'])
def AddToCartViewRES(request):
    """
    Restaurant add to cart using optimized service layer.
    This is a wrapper around the optimized cart service for backward compatibility.
    """
    from .cart_services import CartService
    from .utils import parse_json_input, build_absolute_url
    
    # 1. Extraction & Validation
    user_id = request.GET.get("user_id")
    business_id = request.GET.get("business_id")
    item_id = request.data.get("item_id")
    quantity = int(request.data.get("quantity", 1))
    
    if not all([user_id, business_id, item_id]):
        return JsonResponse({"error": "user_id and business_id are required in URL params"}, status=400)
    
    try:
        user_id = int(user_id)
        item_id = int(item_id)
    except (ValueError, TypeError) as e:
        return JsonResponse({"error": "Invalid ID format", "details": str(e)}, status=400)
    
    # 2. Get Item Details and Check Availability
    try:
        item_details = CartService.get_item_details("R02", item_id, business_id)
        if not item_details:
            return JsonResponse({"error": "Menu item not found or inactive"}, status=404)
        
        availability_timings = item_details[4]
        if not CartService.check_item_availability("R02", availability_timings):
            return JsonResponse({"error": "Item is not available in this moment"}, status=400)
            
    except Exception as e:
        return JsonResponse({"error": f"Failed to fetch item details: {str(e)}"}, status=500)
    
    # 3. Update Cart
    try:
        msg, final_qty = CartService.upsert_cart("R02", user_id, business_id, item_id, quantity)
    except Exception as e:
        return JsonResponse({"error": f"Failed to update cart: {str(e)}"}, status=500)
    
    # 4. Build Response (maintaining original format for backward compatibility)
    item_response = {
        "item_id": item_id,
        "item_name": item_details[1],
        "description": item_details[2],
        "selling_price": str(item_details[3]),
        "quantity": final_qty,
    }
    
    # 5. Fetch cart items (original format)
    try:
        cart_rows = CartService.get_cart_items("R02", user_id)
        # Filter by business_id and format for legacy response
        menu_details = [
            {
                "cart_id": r[0],
                "item_id": r[1],
                "quantity": r[2],
                "item_name": r[3],
                "description": r[4],
                "selling_price": str(r[5]),
            }
            for r in cart_rows if str(r[7]) == business_id  # r[7] is business_id
        ]
    except Exception as e:
        return JsonResponse({
            "message": msg,
            "item_details": item_response,
            "error": f"Failed to fetch cart items: {str(e)}"
        }, status=500)
    
    return JsonResponse({
        "message": msg,
        "item_details": item_response,
        "menu_details": menu_details
    }, status=200)

#add to cart for grocery
@swagger_auto_schema(methods=['POST'],tags=['Consumer'])
@api_view(['POST'])
def AddToCartViewGROCERY(request):
    """
    Grocery add to cart using optimized service layer.
    This is a wrapper around the optimized cart service for backward compatibility.
    """
    from .cart_services import CartService
    from .utils import parse_json_input, build_absolute_url
    
    # 1. Extraction & Validation
    user_id = request.GET.get("user_id")
    business_id = request.GET.get("business_id")
    item_id = request.data.get("item_id")
    quantity = int(request.data.get("quantity", 1))
    
    if not all([user_id, business_id, item_id]):
        return JsonResponse({"error": "user_id and business_id are required in URL params"}, status=400)
    
    try:
        user_id = int(user_id)
        item_id = int(item_id)
    except (ValueError, TypeError) as e:
        return JsonResponse({"error": "Invalid ID format", "details": str(e)}, status=400)
    
    # 2. Get Item Details and Check Availability
    try:
        item_details = CartService.get_item_details("R01", item_id, business_id)
        if not item_details:
            return JsonResponse({"error": "Menu item not found or inactive"}, status=404)
        
        availability_timings = item_details[4]
        if not CartService.check_item_availability("R01", availability_timings):
            return JsonResponse({"error": "This grocery item is not available at this time"}, status=400)
            
    except Exception as e:
        return JsonResponse({"error": f"Failed to fetch item details: {str(e)}"}, status=500)
    
    # 3. Update Cart
    try:
        msg, final_qty = CartService.upsert_cart("R01", user_id, business_id, item_id, quantity)
    except Exception as e:
        return JsonResponse({"error": f"Failed to update cart: {str(e)}"}, status=500)
    
    # 4. Build Response (maintaining original format for backward compatibility)
    item_response = {
        "item_id": item_id,
        "item_name": item_details[1],
        "description": item_details[2],
        "selling_price": str(item_details[3]),
        "quantity": final_qty,
    }
    
    # 5. Fetch cart items (original format)
    try:
        cart_rows = CartService.get_cart_items("R01", user_id)
        # Filter by business_id and format for legacy response
        menu_details = [
            {
                "cart_id": r[0],
                "item_id": r[1],
                "quantity": r[2],
                "item_name": r[3],
                "description": r[4],
                "selling_price": str(r[5]),
            }
            for r in cart_rows if str(r[7]) == business_id  # r[7] is business_id
        ]
    except Exception as e:
        return JsonResponse({
            "message": msg,
            "item_details": item_response,
            "error": f"Failed to fetch cart items: {str(e)}"
        }, status=500)
    
    return JsonResponse({
        "message": msg,
        "item_details": item_response,
        "menu_details": menu_details
    }, status=200)
