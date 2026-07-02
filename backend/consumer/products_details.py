from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework import status
from django.shortcuts import render
from drf_yasg.utils import swagger_auto_schema

from consumer.image_utils import build_s3_file_url
from business.models import MenuItems, FashionProduct, FashionProductVariant
from .gro_models import GroceriesProducts, GroceriesProductVariants


def _absolute_media_url(request, path):
    """Build S3 URL for media path."""
    return build_s3_file_url(path)


def _process_sub_images(request, sub_images):
    """Process sub_images JSON field and return array of S3 URLs"""
    if not sub_images:
        return []
    
    if isinstance(sub_images, str):
        try:
            import json
            sub_images = json.loads(sub_images)
        except (json.JSONDecodeError, ValueError):
            return []
    
    if not isinstance(sub_images, list):
        return []
    
    urls = []
    for img_path in sub_images:
        if img_path:
            urls.append(build_s3_file_url(img_path))
    
    return urls


@swagger_auto_schema(methods=['GET'],tags=['Consumer'])
@api_view(["GET"])
def product_details(request):
    """
    Unified product details API.

    Accepts any of:
    - item_id (MenuItems.item_id)
    - product_id (Groceries_Products.product_id)
    - variant_id (Groceries_ProductVariants_1.variant_id)

    Returns item details with image, description, pricing, and business info.
    """
    item_id = request.query_params.get('item_id')
    product_id = request.query_params.get('product_id')
    variant_id = request.query_params.get('variant_id')

    # Try MenuItems if item_id provided
    if item_id:
        try:
            mid = int(item_id)
        except (TypeError, ValueError):
            return Response({
                'success': False,
                'error': 'item_id must be an integer'
            }, status=status.HTTP_400_BAD_REQUEST)

        menu = MenuItems.objects.select_related('business_id').filter(
            item_id=mid, is_active=True, status=True
        ).first()

        if menu:
            variants_qs = MenuItemVariant.objects.filter(item=menu, is_active=True).order_by('variant_id')
            return Response({
                'success': True,
                'source': 'menu',
                'item': {
                    'item_id': menu.item_id,
                    'name': menu.item_name,
                    'description': menu.description or '',
                    'category': menu.item_category,
                    'type': menu.item_type,
                    'image_url': _absolute_media_url(request, getattr(menu, 'item_image', None)),
                    'business_id': getattr(menu.business_id, 'business_id', None),
                    'business_name': getattr(menu.business_id, 'businessName', None),
                    'variants': [
                        {
                            'variant_id': v.variant_id,
                            'size_label': v.size_label,
                            'selling_price': float(v.selling_price) if v.selling_price is not None else None,
                            'original_cost': float(v.original_cost) if v.original_cost is not None else None,
                            'gst_percentage': float(v.gst) if v.gst is not None else None,
                            'stock': v.stock_qty,
                        }
                        for v in variants_qs
                    ]
                }
            }, status=status.HTTP_200_OK)

    # Try Groceries by product_id or variant_id
    pid = None
    vid = None
    try:
        if product_id:
            pid = int(product_id)
        if variant_id:
            vid = int(variant_id)
    except (TypeError, ValueError):
        return Response({
            'success': False,
            'error': 'product_id and variant_id must be integers'
        }, status=status.HTTP_400_BAD_REQUEST)

    product = None
    if pid:
        product = GroceriesProducts.objects.select_related('business', 'category').filter(product_id=pid).first()
    elif vid:
        variant = GroceriesProductVariants.objects.select_related('product__business', 'product__category').filter(
            variant_id=vid, is_active=True
        ).first()
        product = getattr(variant, 'product', None) if variant else None

    if product:
        variants_qs = GroceriesProductVariants.objects.filter(product=product, is_active=True).order_by('variant_id')
        price_values = [
            float(v.price_override if v.price_override and v.price_override > 0 else v.selling_price)
            for v in variants_qs
            if (v.price_override if v.price_override and v.price_override > 0 else v.selling_price) is not None
        ]
        price_min = min(price_values) if price_values else None
        price_max = max(price_values) if price_values else None

        return Response({
            'success': True,
            'source': 'grocery',
            'item': {
                'product_id': product.product_id,
                'name': product.product_name,
                'brand_name': product.brand_name,
                'description': product.description or '',
                'category': getattr(getattr(product, 'category', None), 'category_name', None),
                'sub_category': getattr(product, 'sub_category', None),
                'is_organic': bool(getattr(product, 'is_organic', False)),
                'is_featured': bool(getattr(product, 'is_featured', False)),
                'rating': float(product.rating) if getattr(product, 'rating', None) is not None else None,
                'price_min': price_min,
                'price_max': price_max,
                'image_url': _absolute_media_url(request, getattr(product, 'main_image', None)),
                'sub_images': _process_sub_images(request, getattr(product, 'sub_images', None)),
                'business_id': getattr(getattr(product, 'business', None), 'business_id', None),
                'business_name': getattr(getattr(product, 'business', None), 'businessName', None),
                'variants': [
                    {
                        'variant_id': v.variant_id,
                        'sku': v.sku,
                        'size': v.size,
                        'net_weight': v.net_weight,
                        'net_weight_unit': v.net_weight_unit,
                        'selling_price': float(v.price_override if v.price_override and v.price_override > 0 else v.selling_price) if (v.price_override if v.price_override and v.price_override > 0 else v.selling_price) is not None else None,
                        'stock': v.stock,
                    }
                    for v in variants_qs
                ]
            }
        }, status=status.HTTP_200_OK)

    # Try Fashion (R08) by product_id or variant_id
    fashion_product = None
    if pid:
        fashion_product = FashionProduct.objects.select_related('business_id', 'category').filter(
            product_id=pid,
            is_active=True,
        ).first()
    elif vid:
        fashion_variant = FashionProductVariant.objects.select_related('product', 'business_id', 'product__category').filter(
            variant_id=vid,
            is_active=True,
        ).first()
        fashion_product = getattr(fashion_variant, 'product', None) if fashion_variant else None

    if fashion_product:
        variants_qs = FashionProductVariant.objects.filter(product=fashion_product, is_active=True).order_by('variant_id')
        price_values = [float(v.selling_price) for v in variants_qs if v.selling_price is not None]
        price_min = min(price_values) if price_values else None
        price_max = max(price_values) if price_values else None

        business_obj = getattr(fashion_product, 'business_id', None)
        category_obj = getattr(fashion_product, 'category', None)

        return Response({
            'success': True,
            'source': 'fashion',
            'item': {
                'product_id': fashion_product.product_id,
                'name': getattr(fashion_product, 'name', None),
                'brand_name': getattr(fashion_product, 'brand', None),
                'description': getattr(fashion_product, 'description', '') or '',
                'category': getattr(category_obj, 'category_name', None),
                'subcategory': getattr(fashion_product, 'subcategory', None),
                'is_featured': bool(getattr(fashion_product, 'is_featured', False)),
                'rating': float(fashion_product.rating) if getattr(fashion_product, 'rating', None) is not None else None,
                'price_min': price_min,
                'price_max': price_max,
                'main_image': _absolute_media_url(request, getattr(fashion_product, 'main_image', None)),
                'sub_images': _process_sub_images(request, getattr(fashion_product, 'sub_images', None)),
                'business_id': getattr(business_obj, 'business_id', None),
                'business_name': getattr(business_obj, 'businessName', None),
                'variants': [
                    {
                        'variant_id': v.variant_id,
                        'sku': v.sku,
                        'size': v.size,
                        'color': v.color,
                        'material': v.material,
                        'gender': v.gender,
                        'selling_price': float(v.selling_price) if v.selling_price is not None else None,
                        'original_cost': float(v.original_cost) if v.original_cost is not None else None,
                        'stock': int(v.stock) if v.stock is not None else 0,
                        'stock_qty': int(v.stock_qty) if v.stock_qty is not None else 0,
                    }
                    for v in variants_qs
                ]
            }
        }, status=status.HTTP_200_OK)

    return Response({
        'success': False,
        'error': 'No item found for given identifiers'
    }, status=status.HTTP_404_NOT_FOUND)



