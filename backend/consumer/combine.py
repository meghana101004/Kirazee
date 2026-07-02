from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework import status
from drf_yasg.utils import swagger_auto_schema
from business.models import MenuItems, productItems
from consumer.serializers import BusinessSerializer, MenuItemsSerializer, productItemsSerializer
from rest_framework.pagination import PageNumberPagination
from django.db import connection
from django.db.models import F, ExpressionWrapper, DecimalField
from rest_framework.response import Response
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.conf import settings
import datetime, json, traceback, os
from .models import MenuCart
from .gro_models import GroceriesCart
from consumer.image_utils import build_s3_file_url
from consumer.availability_services import (
    get_item_availability_status,
    get_business_availability,
    add_availability_to_item,
    get_stock_message,
    is_business_open,
    is_item_available
)


def get_availability_context(business, item, current_dt=None):
    """
    Calculate the 'Global' availability context for the parent item.
    This determines the ceiling for all variants.
    
    Returns dict with:
    - can_add: bool - whether parent context allows adding to cart
    - status: str - availability status code
    - is_open: bool - whether business is currently open
    - message: str - user-facing message
    """
    from django.utils import timezone
    
    if current_dt is None:
        current_dt = timezone.now()
    
    # Normalize business status: 0=off, 1=active, 2=hidden
    # Handle both boolean and integer representations
    raw_status = getattr(business, 'status', 1)
    if isinstance(raw_status, bool):
        b_status = 1 if raw_status else 0
    else:
        b_status = int(raw_status)
    
    # Normalize item flags
    item_is_active = getattr(item, 'is_active', True)
    if isinstance(item_is_active, bool):
        item_is_active = 1 if item_is_active else 0
    item_is_active = int(item_is_active)
    
    # Also check item status field if present
    item_status = getattr(item, 'status', True)
    if isinstance(item_status, bool):
        item_status = 1 if item_status else 0
    item_status = int(item_status)
    
    # Combined item active check
    item_active = item_is_active and item_status
    
    # Check timing first - this tells us if it's just "closed for the night"
    business_open = is_business_open(business, current_dt)
    item_in_time = is_item_available(item, current_dt)
    
    # 1. HIDDEN: Business status 2 = Hidden completely (owner wants to hide)
    if b_status == 2:
        return {"can_add": False, "status": "HIDDEN", "is_open": False, "message": None}
    
    # 2. MANUAL DISABLE: Business status 0 AND not within hours (owner turned off)
    # Only treat as TEMPORARY_UNAVAILABLE if explicitly disabled AND outside hours
    # OR if item itself is disabled
    if not item_active:
        return {
            "can_add": False, 
            "status": "TEMPORARY_UNAVAILABLE", 
            "is_open": business_open,
            "message": "Temporarily unavailable"
        }
    
    # 3. SCHEDULE ORDER: Business not open for orders but visible (closed for night)
    # This covers: status=0/FALSE but hours say closed, OR status=1 but outside hours
    if not business_open:
        return {
            "can_add": True,  # ALLOW - can schedule for later
            "status": "SCHEDULE_ORDER", 
            "is_open": False,
            "message": "Store closed. Schedule for later."
        }
    
    # 4. BUSINESS OPEN but ITEM OUTSIDE TIMING: Show but don't allow add
    if not item_in_time:
        return {
            "can_add": False,
            "status": "NOT_IN_TIMING",
            "is_open": True,
            "message": "Available during specific hours only"
        }
    
    # 5. AVAILABLE: Everything OK
    return {
        "can_add": True,
        "status": "AVAILABLE",
        "is_open": True,
        "message": None
    }


def calculate_variant_availability(variant, parent_context, business_type=None):
    """
    Calculate specific variant availability based on parent context.
    Variant can only be addable if parent context allows it AND variant has stock/is_active.
    
    CRITICAL: For SCHEDULE_ORDER, variants should ALSO return SCHEDULE_ORDER if they have stock,
    because the user can schedule the order for later delivery.
    
    Args:
        variant: dict or object with variant data
        parent_context: dict from get_availability_context()
        business_type: 'R01', 'R02', or 'R08'
    
    Returns:
        dict with variant availability fields
    """
    parent_status = parent_context["status"]
    parent_can_add = parent_context["can_add"]
    parent_message = parent_context["message"]
    
    # HIDDEN parent: variant is hidden too
    if parent_status == "HIDDEN":
        return {
            "can_add_to_cart": False,
            "availability_status": "HIDDEN",
            "availability_message": None
        }
    
    # TEMPORARY_UNAVAILABLE parent: variant inherits this
    if parent_status == "TEMPORARY_UNAVAILABLE":
        return {
            "can_add_to_cart": False,
            "availability_status": "TEMPORARY_UNAVAILABLE",
            "availability_message": parent_message
        }
    
    # NOT_IN_TIMING parent: variant inherits this (business open, item outside timing)
    if parent_status == "NOT_IN_TIMING":
        return {
            "can_add_to_cart": False,
            "availability_status": "NOT_IN_TIMING",
            "availability_message": parent_message
        }
    
    # Get variant-specific flags
    variant_active = variant.get('is_active', True) if isinstance(variant, dict) else getattr(variant, 'is_active', True)
    if isinstance(variant_active, bool):
        variant_active = 1 if variant_active else 0
    
    # Get stock based on business type field names
    if business_type == 'R01':
        stock = variant.get('stock', 0) if isinstance(variant, dict) else getattr(variant, 'stock', 0)
    elif business_type in ['R02', 'R08']:
        stock = variant.get('stock_qty', 0) if isinstance(variant, dict) else getattr(variant, 'stock_qty', 0)
        if stock == 0:
            stock = variant.get('stock', 0) if isinstance(variant, dict) else getattr(variant, 'stock', 0)
    else:
        stock = variant.get('stock', 0) if isinstance(variant, dict) else getattr(variant, 'stock', 0)
        if stock == 0:
            stock = variant.get('stock_qty', 0) if isinstance(variant, dict) else getattr(variant, 'stock_qty', 0)
    
    try:
        stock = int(stock or 0)
    except (ValueError, TypeError):
        stock = 0
    
    # Variant disabled: TEMPORARY_UNAVAILABLE
    if not variant_active:
        return {
            "can_add_to_cart": False,
            "availability_status": "TEMPORARY_UNAVAILABLE",
            "availability_message": "Temporarily unavailable"
        }
    
    # Out of stock
    if stock <= 0:
        return {
            "can_add_to_cart": False,
            "availability_status": "OUT_OF_STOCK",
            "availability_message": "Out of stock"
        }
    
    # Parent is SCHEDULE_ORDER and variant has stock: allow scheduling
    if parent_status == "SCHEDULE_ORDER":
        return {
            "can_add_to_cart": True,  # Can schedule for later
            "availability_status": "SCHEDULE_ORDER",
            "availability_message": parent_message
        }
    
    # AVAILABLE: Everything OK
    return {
        "can_add_to_cart": True,
        "availability_status": "AVAILABLE",
        "availability_message": None
    }


def _abs_media_url(request, raw_path):
    """Build S3 URL for media path."""
    if not raw_path:
        return None
    
    # Convert ImageFieldFile to string if needed
    if hasattr(raw_path, 'name'):
        raw_path = raw_path.name
    else:
        raw_path = str(raw_path)
    
    # If it's already a complete URL, return as is
    if raw_path.startswith('http://') or raw_path.startswith('https://'):
        # If it's an old base URL format, convert it to S3
        if 'kirazee.com/kirazee/media/' in raw_path:
            # Extract the file path from the old URL
            file_path = raw_path.split('kirazee.com/kirazee/media/')[-1]
            return build_s3_file_url(f"media/{file_path}")
        elif 'kirazee/media/' in raw_path:
            # Extract the file path from the old URL
            file_path = raw_path.split('kirazee/media/')[-1]
            return build_s3_file_url(f"media/{file_path}")
        else:
            return raw_path
    
    return build_s3_file_url(raw_path)


def _process_sub_images(request, sub_images):
    """Return (sub_images_dict_or_list, sub_images_url_list) with absolute URLs."""
    if not sub_images:
        return {}, []

    # MySQL may return JSONField as str
    if isinstance(sub_images, str):
        try:
            sub_images = json.loads(sub_images)
        except Exception:
            return {}, []

    if isinstance(sub_images, dict):
        updated = {}
        urls = []
        for k, v in sub_images.items():
            u = _abs_media_url(request, v)
            if not u:
                continue
            updated[k] = u
            urls.append(u)
        return updated, urls

    if isinstance(sub_images, list):
        urls = []
        for v in sub_images:
            u = _abs_media_url(request, v)
            if u:
                urls.append(u)
        return urls, urls

    return {}, []


def _categorize_media_files(urls):
    """
    Categorize media URLs into images and videos based on file extension.
    Returns dict with 'images' and 'videos' lists.
    """
    image_extensions = {'.jpg', '.jpeg', '.png', '.gif', '.webp', '.bmp', '.svg', '.ico', '.tiff', '.tif'}
    video_extensions = {'.mp4', '.avi', '.mov', '.mkv', '.flv', '.wmv', '.webm', '.m4v', '.3gp', '.ogv', '.ogg'}
    
    images = []
    videos = []
    
    for url in urls:
        if not url:
            continue
        # Extract file extension from URL (handle query params)
        url_path = url.split('?')[0]  # Remove query parameters
        ext = os.path.splitext(url_path)[-1].lower()
        
        if ext in video_extensions:
            videos.append(url)
        else:
            # Default to image if unknown extension or matches image extensions
            images.append(url)
    
    return {
        'images': images,
        'videos': videos
    }


def _build_media_response(request, item_image, sub_images):
    """
    Build the new media response format with categorized images and videos.
    Returns media_dict with 'images' and 'videos' arrays.
    """
    # Process main item image
    main_image_url = None
    if item_image:
        main_image_url = _abs_media_url(request, item_image)
    
    # Process sub images/media
    processed_sub, sub_urls = _process_sub_images(request, sub_images)
    
    # Combine all media URLs (main image first, then sub images)
    all_media_urls = []
    if main_image_url:
        all_media_urls.append(main_image_url)
    all_media_urls.extend(sub_urls)
    
    # Categorize into images and videos
    categorized = _categorize_media_files(all_media_urls)
    
    # Build response
    media_response = {
        'images': categorized['images'],
        'videos': categorized['videos']
    }
    
    return media_response


def calculate_business_rating(business_id):
    """Calculate average rating for a business from its menu items"""
    from django.db import connection
    with connection.cursor() as cursor:
        cursor.execute("""
            SELECT AVG(rating) as avg_rating, COUNT(*) as rating_count 
            FROM menuItems 
            WHERE business_id = %s AND rating IS NOT NULL
        """, [business_id])
        result = cursor.fetchone()
        
        if result and result[0]:
            return {
                'ratings': float(result[0]),
                'rating_count': result[1] or 0
            }
    return {
        'ratings': 4.0,  # Default rating if no ratings exist
        'rating_count': 0
    }


def _parse_items_query_params(request):
    return {
        'search': request.query_params.get('search', ''),
        'category': request.query_params.get('category'),
        'category_id': request.query_params.get('category_id'),
        'sub_category_id': request.query_params.get('sub_category_id'),
        'min_price': request.query_params.get('min_price'),
        'max_price': request.query_params.get('max_price'),
        'ordering': request.query_params.get('ordering', 'item_name'),
        'page': request.query_params.get('page', 1),
        'page_size': request.query_params.get('page_size', 10),
    }


def _is_page_all(page_value):
    try:
        return str(page_value).strip().lower() == 'all'
    except Exception:
        return False


def _get_business_context(request, business_id):
    from kirazee_app.models import Business

    if not business_id:
        raise ValueError('business_id is required')

    business = Business.objects.get(business_id=business_id)
    business_data = BusinessSerializer(business, context={'request': request}).data

    business_availability = get_business_availability(business)
    business_data['is_visible'] = business_availability['is_visible']
    business_data['can_order'] = business_availability['can_order']
    business_data['availability_status'] = business_availability['availability_status']
    business_data['availability_message'] = business_availability['availability_message']
    business_data['is_business_open'] = business_availability['is_business_open']

    rating_data = calculate_business_rating(business_id)
    business_data.update(rating_data)
    return business, business_data


def _apply_offer_metadata(target, selling_price, original_cost):
    try:
        oc = Decimal(str(original_cost or '0'))
        sp = Decimal(str(selling_price or '0'))
    except Exception:
        oc = Decimal('0')
        sp = Decimal('0')

    if oc > 0:
        diff = oc - sp
        if diff > 0:
            percent = (diff / oc * Decimal(100))
            percent_display = int(percent.quantize(Decimal('1'), rounding=ROUND_HALF_UP))
            diff_display = int(diff.quantize(Decimal('1'), rounding=ROUND_HALF_UP))
            target['diff_amount'] = f"{diff.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP):.2f}"
            target['percent'] = f"{percent.quantize(Decimal('0.1'), rounding=ROUND_HALF_UP):.1f}"
            target['percent_display'] = percent_display
            target['diff_display'] = diff_display
            target['is_featured_offer'] = False
            target['discount_percentage'] = percent_display
            return

    target['diff_amount'] = "0.00"
    target['percent'] = "0.0"
    target['percent_display'] = 0
    target['diff_display'] = 0
    target['is_featured_offer'] = False
    target['discount_percentage'] = 0


def _build_item_badges(*, discount_percentage=0, is_featured_offer=False, is_bestseller=False, is_new=False, is_trending=False, is_limited=False, max_badges=2):
    badges = []

    try:
        dp = int(discount_percentage or 0)
    except Exception:
        dp = 0

    if dp > 0:
        badges.append({'badge_text': f"{dp}% OFF", 'badge_type': 'discount', 'priority': 1})
    if is_featured_offer:
        badges.append({'badge_text': 'Featured', 'badge_type': 'featured', 'priority': 2})
    if is_bestseller:
        badges.append({'badge_text': 'Bestseller', 'badge_type': 'bestseller', 'priority': 3})
    if is_new:
        badges.append({'badge_text': 'New', 'badge_type': 'new', 'priority': 4})
    if is_limited:
        badges.append({'badge_text': 'Limited', 'badge_type': 'limited', 'priority': 5})
    if is_trending:
        badges.append({'badge_text': 'Trending', 'badge_type': 'trending', 'priority': 6})

    badges.sort(key=lambda b: b.get('priority', 999))
    badges = badges[: (max_badges or 2)]

    for b in badges:
        b.pop('priority', None)
    return badges


def _is_item_new_debug(created_at, days=30):
    """
    Debug version of _is_item_new that returns (bool, reason).
    """
    if not created_at:
        return False, "null"
    try:
        from django.utils import timezone
        from datetime import datetime
        now = timezone.now()
        if isinstance(created_at, str):
            created_at_dt = datetime.fromisoformat(created_at.replace('Z', '+00:00'))
        else:
            created_at_dt = created_at
        diff = (now.date() - created_at_dt.date()).days
        is_new = diff >= 0 and diff <= days
        return is_new, f"diff={diff}, now={now.date()}, created={created_at_dt.date()}"
    except Exception as e:
        return False, f"err={e}"


def _is_item_new(created_at, days=30):
    if not created_at:
        return False
    try:
        from django.utils import timezone
        from datetime import datetime
        now = timezone.now()
        if isinstance(created_at, str):
            created_at_dt = datetime.fromisoformat(created_at.replace('Z', '+00:00'))
        else:
            created_at_dt = created_at
        diff = (now.date() - created_at_dt.date()).days
        return diff >= 0 and diff <= days
    except Exception:
        # If parsing fails, treat as new if string contains today's date
        if isinstance(created_at, str) and now.strftime('%Y-%m-%d') in created_at:
            return True
        return False


def _is_item_bestseller(item_id, business_id, business_type, threshold=5):
    """
    Return True if the item has been ordered at least `threshold` times for the given business.
    Works for R02 (menuItems), R01 (Groceries_Products), and R08 (fashion_products).
    """
    if not item_id or not business_id or not business_type:
        return False
    try:
        with connection.cursor() as cursor:
            if business_type == 'R02':
                query = """
                    SELECT COUNT(*) AS cnt
                    FROM order_items oi
                    JOIN orders o ON o.order_id = oi.order_id
                    WHERE oi.menu_item_id = %s
                      AND o.business_id = %s
                      AND (o.status IS NULL OR o.status NOT IN ('cancelled','failed'))
                """
                params = [item_id, business_id]
            elif business_type == 'R01':
                query = """
                    SELECT COUNT(*) AS cnt
                    FROM order_items oi
                    JOIN orders o ON o.order_id = oi.order_id
                    WHERE oi.product_item_id = %s
                      AND o.business_id = %s
                      AND (o.status IS NULL OR o.status NOT IN ('cancelled','failed'))
                """
                params = [item_id, business_id]
            elif business_type == 'R08':
                query = """
                    SELECT COUNT(*) AS cnt
                    FROM order_items oi
                    JOIN orders o ON o.order_id = oi.order_id
                    WHERE oi.product_item_id = %s
                      AND o.business_id = %s
                      AND (o.status IS NULL OR o.status NOT IN ('cancelled','failed'))
                """
                params = [item_id, business_id]
            else:
                return False
            cursor.execute(query, params)
            row = cursor.fetchone()
            return (row and row[0] and row[0] >= threshold)
    except Exception:
        return False


def _attach_badges_from_offer_fields(target):
    target['badges'] = _build_item_badges(
        discount_percentage=target.get('discount_percentage') or target.get('percent_display') or 0,
        is_featured_offer=bool(target.get('is_featured_offer', False)),
        is_bestseller=bool(target.get('is_bestseller', False)),
        is_new=bool(target.get('is_new', False)),
        max_badges=2,
    )


def _paginate_list(items, *, page, page_size):
    """Manual pagination for list-based results (used by raw-SQL services)."""
    if _is_page_all(page):
        total_items = len(items)
        return {
            'page': 1,
            'page_size': total_items,
            'items': items,
            'total_items': total_items,
            'total_pages': 1,
            'next': None,
            'previous': None,
        }

    try:
        page_int = int(page)
        if page_int < 1:
            page_int = 1
    except (ValueError, TypeError):
        page_int = 1

    try:
        page_size_int = int(page_size)
        if page_size_int < 1:
            page_size_int = 10
    except (ValueError, TypeError):
        page_size_int = 10

    start_index = (page_int - 1) * page_size_int
    end_index = start_index + page_size_int
    total_items = len(items)
    total_pages = (total_items + page_size_int - 1) // page_size_int

    return {
        'page': page_int,
        'page_size': page_size_int,
        'items': items[start_index:end_index],
        'total_items': total_items,
        'total_pages': total_pages,
        'next': page_int + 1 if page_int < total_pages else None,
        'previous': page_int - 1 if page_int > 1 else None,
    }


def get_mapped_category_query_filter(*, table_alias, business_ids, category_id=None, category=None):
    """
    Returns (sql_fragment, params) to filter items by mapped categories.

    This centralizes the duplicated category resolution logic currently present in the R01 and R08 raw-SQL blocks.
    - table_alias: SQL alias used in the query (e.g. 'gp' or 'fp')
    - business_ids: list of business_ids included in the mapping (master + subs)
    """
    if not business_ids:
        return " AND 1=0", []

    biz_placeholders = ','.join(['%s'] * len(business_ids))

    mapped_category_ids = set()
    with connection.cursor() as cursor:
        cursor.execute(
            f"""
                SELECT DISTINCT cm.category_id
                FROM category_mapping cm
                WHERE cm.business_id IN ({biz_placeholders})
                AND cm.is_active = 1
            """,
            business_ids,
        )
        mapped_category_ids = set([int(r[0]) for r in cursor.fetchall() if r and r[0] is not None])

    resolved_id = None
    resolved_name = None
    resolved_parent_id = None

    with connection.cursor() as cursor:
        if category_id:
            try:
                cat_id_int = int(str(category_id).strip())
                cursor.execute(
                    """
                        SELECT uc.category_id, TRIM(uc.category_name) as category_name, uc.parent_category_id
                        FROM universal_Categories uc
                        WHERE uc.category_id = %s
                        LIMIT 1
                    """,
                    [cat_id_int],
                )
                row = cursor.fetchone()
                if row:
                    resolved_id = int(row[0])
                    resolved_name = row[1]
                    resolved_parent_id = row[2]
            except Exception:
                pass
        elif str(category or '').strip().isdigit():
            resolved_id = int(str(category).strip())
            cursor.execute(
                """
                    SELECT uc.category_id, TRIM(uc.category_name) as category_name, uc.parent_category_id
                    FROM universal_Categories uc
                    WHERE uc.category_id = %s
                    LIMIT 1
                """,
                [resolved_id],
            )
        else:
            cursor.execute(
                """
                    SELECT uc.category_id, TRIM(uc.category_name) as category_name, uc.parent_category_id
                    FROM universal_Categories uc
                    WHERE LOWER(TRIM(uc.category_name)) = LOWER(TRIM(%s))
                    LIMIT 1
                """,
                [category],
            )

        if not category_id:
            row = cursor.fetchone()
            if row and row[0] is not None:
                resolved_id = int(row[0])
                resolved_name = row[1]
                resolved_parent_id = row[2]

    if resolved_id is None or not mapped_category_ids:
        return " AND 1=0", []

    params = []
    # If the resolved category has a parent, treat it like a leaf/subcategory selection.
    if resolved_parent_id not in (None, ''):
        if resolved_id not in mapped_category_ids:
            return " AND 1=0", []

        try:
            parent_id_int = int(resolved_parent_id)
        except Exception:
            parent_id_int = None

        if parent_id_int is None:
            params.append(resolved_id)
            return f" AND {table_alias}.category_id = %s", params

        params.extend([resolved_id, parent_id_int, resolved_name or str(category)])
        # Use different column names based on table_alias (fp for fashion, gp for grocery)
        sub_category_col = "subcategory_id" if table_alias == "fp" else "sub_category"
        return (
            f" AND ({table_alias}.category_id = %s OR ({table_alias}.category_id = %s AND {table_alias}.{sub_category_col} = %s))",
            params,
        )

    # Parent category selected - include all descendants, then intersect with mapped ids.
    all_ids = set([resolved_id])
    frontier = set([resolved_id])
    while frontier:
        ph = ','.join(['%s'] * len(frontier))
        with connection.cursor() as cursor:
            cursor.execute(
                f"""
                    SELECT uc.category_id
                    FROM universal_Categories uc
                    WHERE uc.parent_category_id IN ({ph})
                """,
                list(frontier),
            )
            child_ids = set([int(r[0]) for r in cursor.fetchall() if r and r[0] is not None])
        new_ids = child_ids - all_ids
        all_ids |= new_ids
        frontier = new_ids

    mapped_subtree_ids = sorted(list(all_ids.intersection(mapped_category_ids)))
    if not mapped_subtree_ids:
        return " AND 1=0", []

    cat_ph = ','.join(['%s'] * len(mapped_subtree_ids))
    fragment = f" AND ({table_alias}.category_id IN ({cat_ph})"
    params.extend(mapped_subtree_ids)

    mapped_child_ids = [cid for cid in mapped_subtree_ids if cid != resolved_id]
    if mapped_child_ids:
        names_ph = ','.join(['%s'] * len(mapped_child_ids))
        with connection.cursor() as cursor:
            cursor.execute(
                f"""
                    SELECT TRIM(uc.category_name) as category_name
                    FROM universal_Categories uc
                    WHERE uc.category_id IN ({names_ph})
                """,
                mapped_child_ids,
            )
            mapped_child_names = [r[0] for r in cursor.fetchall() if r and r[0]]

        mapped_child_names = [n for n in mapped_child_names if n]
        if mapped_child_names:
            sub_ph = ','.join(['%s'] * len(mapped_child_names))
            # Use different column names based on table_alias (fp for fashion, gp for grocery)
            sub_category_col = "subcategory_id" if table_alias == "fp" else "sub_category"
            fragment += f" OR ({table_alias}.category_id = %s AND {table_alias}.{sub_category_col} IN ({sub_ph}))"
            params.append(resolved_id)
            params.extend(mapped_child_names)

    fragment += ")"
    return fragment, params


def _include_business_ids(business_id):
    """Return a list of the given business_id plus any sub-businesses where master=business_id."""
    include_business_ids = [business_id]
    with connection.cursor() as cursor:
        cursor.execute(
            """
                SELECT b.business_id
                FROM businesses b
                WHERE b.master = %s
            """,
            [business_id],
        )
        sub_rows = cursor.fetchall()
    include_business_ids.extend([r[0] for r in sub_rows if r and r[0]])
    return include_business_ids


def _fetch_variants_for_products(product_ids, *, business_type):
    """
    Fetch variants for given product_ids based on business_type.
    Returns dict {product_id: [variant_dict, ...]}.
    """
    if not product_ids:
        return {}
    placeholders = ','.join(['%s'] * len(product_ids))
    import json as _json
    variants_data = {}
    if business_type == 'R08':
        query = f"""
            SELECT
                fpv.product_id,
                fpv.variant_id,
                fpv.sku,
                fpv.barcode,
                fpv.selling_price,
                fpv.mrp,
                fpv.stock_qty,
                fpv.net_weight,
                fpv.net_weight_unit,
                fpv.original_cost,
                fpv.charges,
                fpv.stock,
                fpv.mfg_date,
                fpv.expiry_date,
                fpv.size,
                fpv.color,
                fpv.material,
                fpv.gender,
                fpv.min_age,
                fpv.max_age,
                fpv.pack,
                fpv.attributes,
                fpv.dimension,
                fpv.is_active,
                fpv.created_at,
                fpv.updated_at,
                fpv.rating,
                fpv.rating_count
            FROM fashion_product_variants fpv
            WHERE fpv.product_id IN ({placeholders})
              AND COALESCE(fpv.is_active, 1) = 1
            ORDER BY fpv.product_id, fpv.variant_id
        """
    elif business_type == 'R01':
        query = f"""
            SELECT 
                gpv.product_id,
                gpv.variant_id,
                gpv.sku,
                gpv.net_weight,
                gpv.net_weight_unit,
                gpv.size,
                gpv.original_cost,
                gpv.selling_price,
                gpv.price_override,
                gpv.charges,
                gpv.gst,
                gpv.stock,
                gpv.mfg_date,
                gpv.expiry_date,
                gpv.is_active,
                gpv.created_at,
                gpv.updated_at,
                gpv.color,
                gpv.gender,
                gpv.age,
                gpv.material,
                gpv.attributes,
                gpv.pack,
                gpv.is_visible_counter,
                gpv.min_age,
                gpv.max_age,
                gpv.dimension,
                gpv.rating,
                gpv.rating_count
            FROM Groceries_ProductVariants_1 gpv
            WHERE gpv.product_id IN ({placeholders})
              AND COALESCE(gpv.is_active, 1) = 1
            ORDER BY gpv.product_id, gpv.variant_id
        """
    else:
        return {}
    with connection.cursor() as cursor:
        cursor.execute(query, product_ids)
        rows = cursor.fetchall()
    for row in rows:
        pid = row[0]
        if pid not in variants_data:
            variants_data[pid] = []
        if business_type == 'R08':
            variant_dict = {
                'variant_id': row[1],
                'sku': row[2],
                'barcode': row[3],
                'selling_price': f"{round(float(row[4]) if row[4] is not None else 0):.2f}",
                'mrp': f"{round(float(row[5]) if row[5] is not None else 0):.2f}",
                'stock_qty': row[6] or 0,
                'net_weight': float(row[7]) if row[7] is not None else None,
                'net_weight_unit': row[8],
                'original_cost': f"{round(float(row[9]) if row[9] is not None else 0):.2f}",
                'charges': f"{round(float(row[10]) if row[10] is not None else 0):.2f}",
                'stock': row[11] or 0,
                'mfg_date': row[12].isoformat() if row[12] else None,
                'expiry_date': row[13].isoformat() if row[13] else None,
                'size': row[14],
                'color': row[15],
                'material': row[16],
                'gender': row[17],
                'min_age': row[18],
                'max_age': row[19],
                'pack': row[20],
                'attributes': _json.loads(row[21]) if row[21] and isinstance(row[21], str) else row[21],
                'dimension': _json.loads(row[22]) if row[22] and isinstance(row[22], str) else row[22],
                'is_active': bool(row[23]),
                'created_at': row[24].isoformat() if row[24] else None,
                'updated_at': row[25].isoformat() if row[25] else None,
                # New Rating Logic
                'rating': float(row[26]) if row[26] is not None else 4.0,
                'rating_count': int(row[27]) if row[27] is not None else 0,
            }
        elif business_type == 'R01':
            variant_dict = {
                'variant_id': row[1],
                'sku': row[2],
                'net_weight': float(row[3]) if row[3] is not None else None,
                'net_weight_unit': row[4],
                'size': _json.loads(row[5]) if row[5] and isinstance(row[5], str) else row[5],
                'original_cost': f"{round(float(row[6]) if row[6] is not None else 0):.2f}",
                'selling_price': f"{round(float(row[7]) if row[7] is not None else 0):.2f}",
                'price_override': f"{round(float(row[8]) if row[8] is not None else 0):.2f}",
                'charges': f"{round(float(row[9]) if row[9] is not None else 0):.2f}",
                'gst': f"{round(float(row[10]) if row[10] is not None else 0):.2f}",
                'stock': row[11] or 0,
                'mfg_date': row[12].isoformat() if row[12] else None,
                'expiry_date': row[13].isoformat() if row[13] else None,
                'is_active': bool(row[14]),
                'created_at': row[15].isoformat() if row[15] else None,
                'updated_at': row[16].isoformat() if row[16] else None,
                'color': row[17],
                'gender': row[18],
                'age': row[19],
                'material': row[20],
                'attributes': _json.loads(row[21]) if row[21] and isinstance(row[21], str) else row[21],
                'pack': row[22],
                'is_visible_counter': bool(row[23]) if row[23] is not None else True,
                'min_age': row[24],
                'max_age': row[25],
                'dimension': _json.loads(row[26]) if row[26] and isinstance(row[26], str) else row[26],
                # New Rating Logic
                'rating': float(row[27]) if row[27] is not None else 4.0,
                'rating_count': int(row[28]) if row[28] is not None else 0,
            }
        variants_data[pid].append(variant_dict)
    return variants_data


def _enrich_item_with_media_and_availability(request, business, item, *, business_type, item_id_field='item_id'):
    """
    Attach media, availability, and per-variant stock messages.
    Uses top-down availability: variants inherit parent (business/item) restrictions.
    Mutates `item` dict in-place.
    """
    from django.utils import timezone
    
    # Media
    media_data = _build_media_response(
        request,
        item.get('item_image'),
        item.get('sub_images')
    )
    item['media'] = media_data
    for k in ('item_image', 'sub_images', 'sub_images_url'):
        item.pop(k, None)

    # Create pseudo-item for parent context calculation
    class PseudoItem:
        pass
    pseudo_item = PseudoItem()
    pseudo_item.status = 1
    pseudo_item.is_active = True
    pseudo_item.is_visible = 1
    pseudo_item.stock = None
    pseudo_item.item_timings = None

    variants = item.get('variants', [])
    
    # TOP-DOWN AVAILABILITY: Calculate parent context first
    parent_context = get_availability_context(business, pseudo_item, timezone.now())
    
    # If parent is hidden, skip this item entirely
    if parent_context['status'] == 'HIDDEN':
        return False  # signal to skip hidden item
    
    # Set parent-level availability fields
    item['can_add_to_cart'] = parent_context['can_add']
    item['availability_status'] = parent_context['status']
    item['availability_message'] = parent_context['message']
    item['is_business_open'] = parent_context['is_open']
    
    if variants:
        # Calculate per-variant availability (inherits parent context)
        any_variant_available = False
        for variant in variants:
            variant_avail = calculate_variant_availability(variant, parent_context, business_type)
            variant['can_add_to_cart'] = variant_avail['can_add_to_cart']
            variant['availability_status'] = variant_avail['availability_status']
            variant['availability_message'] = variant_avail['availability_message']
            
            # Set variant stock messages
            if business_type == 'R01':
                variant_stock = variant.get('stock', 0)
            else:
                variant_stock = variant.get('stock_qty', 0) or variant.get('stock', 0)
            variant_stock_info = get_stock_message(variant_stock)
            variant['stock_message'] = variant_stock_info['stock_message']
            variant['stock_status'] = variant_stock_info['stock_status']
            
            if variant_avail['can_add_to_cart']:
                any_variant_available = True
        
        # If no variants are available, update parent status
        if not any_variant_available and parent_context['can_add']:
            item['can_add_to_cart'] = False
            item['availability_status'] = 'OUT_OF_STOCK'
            item['availability_message'] = 'All variants are out of stock'
        
        # Set parent stock fields from first variant
        first_variant = variants[0]
        if business_type == 'R01':
            parent_stock = first_variant.get('stock', 0)
        else:
            parent_stock = first_variant.get('stock_qty', 0) or first_variant.get('stock', 0)
        parent_stock_info = get_stock_message(parent_stock)
        item['stock_message'] = parent_stock_info['stock_message']
        item['stock_status'] = parent_stock_info['stock_status']
    else:
        # No variants - set default stock fields
        item['stock_message'] = None
        item['stock_status'] = 'available'

    return True


def _make_items_response(business_data, business, paginated_items, paged, top_offers):
    """
    Build the common response wrapper used by raw-SQL services.
    """
    # Get proper availability context for the business
    from django.utils import timezone
    
    class DefaultPseudoItem:
        pass
    default_pseudo_item = DefaultPseudoItem()
    default_pseudo_item.is_active = True
    default_pseudo_item.status = True
    default_pseudo_item.is_visible = 1
    default_pseudo_item.item_timings = None
    
    business_context = get_availability_context(business, default_pseudo_item, timezone.now())
    
    return Response({
        'business': business_data,
        'is_business_open': business_context['is_open'],
        'availability_status': business_context['status'],
        'availability_message': business_context['message'],
        'can_add_to_cart': business_context['can_add'],
        'top_offers': top_offers,
        'items': paginated_items,
        'total_items': paged['total_items'],
        'total_pages': paged['total_pages'],
        'current_page': paged['page'],
        'page_size': paged['page_size']
    }, status=status.HTTP_200_OK)


def _service_items_r08_raw_sql(request, business, business_id, qp):
    """Service function for R08 (Fashion) items using raw SQL approach."""
    include_business_ids = _include_business_ids(business_id)
    biz_placeholders = ','.join(['%s'] * len(include_business_ids))
    search = qp.get('search', '')
    category_id = qp.get('category_id')
    category = qp.get('category')
    sub_category_id = qp.get('sub_category_id')
    ordering = qp.get('ordering', 'item_name')

    base_query = """
        SELECT DISTINCT
            fp.product_id as item_id,
            fp.name as item_name,
            fp.description,
            fp.main_image as item_image,
            COALESCE(fp.is_featured, 0) as is_featured,
            COALESCE(uc_sub.category_id, uc_by_id.category_id) as category_id,
            COALESCE(NULLIF(TRIM(fp.subcategory_id), ''), uc_by_id.category_name, uc_sub.category_name) as item_category,
            COALESCE(uc_sub.parent_category_id, uc_by_id.parent_category_id) as parent_category_id,
            uc_parent.category_name as parent_category_name,
            fp.subcategory_id as item_type,
            fp.rating,
            fp.created_at,
            fp.updated_at,
            fp.is_customizable,
            COALESCE(fp.subcategory_id, 0) as sub_category_id,
            fp.subcategory_id as sub_category_name
        FROM fashion_products fp
        LEFT JOIN businesses b0 ON b0.business_id = fp.business_id
        LEFT JOIN universal_Categories uc_by_id
            ON uc_by_id.category_id = fp.category_id
            AND EXISTS (
                SELECT 1
                FROM category_mapping cm
                WHERE cm.is_active = 1
                  AND cm.category_id = uc_by_id.category_id
                  AND (cm.business_id = fp.business_id OR cm.business_id = b0.master)
            )
        LEFT JOIN universal_Categories uc_sub
            ON fp.subcategory_id IS NOT NULL
            AND TRIM(fp.subcategory_id) != ''
            AND LOWER(
                CONVERT(REPLACE(REPLACE(REPLACE(REPLACE(TRIM(uc_sub.category_name), '&', ''), ' ', ''), '-', ''), '_', '') USING utf8mb4)
            ) = LOWER(
                CONVERT(REPLACE(REPLACE(REPLACE(REPLACE(TRIM(fp.subcategory_id), '&', ''), ' ', ''), '-', ''), '_', '') USING utf8mb4)
            )
            AND EXISTS (
                SELECT 1
                FROM category_mapping cm
                WHERE cm.is_active = 1
                  AND cm.category_id = uc_sub.category_id
                  AND (cm.business_id = fp.business_id OR cm.business_id = b0.master)
            )
        LEFT JOIN universal_Categories uc_parent ON uc_parent.category_id = COALESCE(uc_sub.parent_category_id, uc_by_id.parent_category_id)
        WHERE 1=1
    """
    params = []
    base_query += " AND COALESCE(fp.is_visible, 1) = 1"
    base_query += f" AND fp.business_id IN ({biz_placeholders})"
    params.extend(include_business_ids)

    if search:
        base_query += " AND fp.name LIKE %s"
        params.append(f"%{search}%")

    # Only apply category mapping if category_id or category is provided
    # Don't apply it for sub_category_id only filtering
    if category_id or category:
        frag, frag_params = get_mapped_category_query_filter(
            table_alias='fp',
            business_ids=include_business_ids,
            category_id=category_id,
            category=category,
        )
        base_query += frag
        params.extend(frag_params)
    elif sub_category_id:
        # For subcategory-only filtering, just check if the subcategory is mapped
        try:
            sub_cat_id_int = int(str(sub_category_id).strip())
            # Check if this subcategory is mapped for the business
            with connection.cursor() as cursor:
                cursor.execute("""
                    SELECT COUNT(*) 
                    FROM category_mapping cm
                    WHERE cm.business_id IN (%s)
                      AND cm.category_id = %s
                      AND cm.is_active = 1
                """ % (','.join(['%s'] * len(include_business_ids)), '%s'), 
                include_business_ids + [sub_cat_id_int])
                is_mapped = cursor.fetchone()[0] > 0
            
            if not is_mapped:
                base_query += " AND 1=0"  # Subcategory not mapped
        except Exception:
            base_query += " AND 1=0"

    if sub_category_id:
        try:
            sub_cat_id_int = int(str(sub_category_id).strip())
            base_query += " AND fp.subcategory_id = %s"
            params.append(sub_cat_id_int)
        except Exception:
            base_query += " AND 1=0"

    ordering_map = {'item_name': 'item_name', 'created_at': 'created_at'}
    order_field = ordering_map.get(ordering.lstrip('-'), 'item_name')
    base_query += f" ORDER BY {order_field}{' DESC' if ordering.startswith('-') else ' ASC'}"

    with connection.cursor() as cursor:
        cursor.execute(base_query, params)
        product_rows = cursor.fetchall()

    product_ids = [row[0] for row in product_rows]
    variants_data = _fetch_variants_for_products(product_ids, business_type='R08')

    items_data = []
    for row in product_rows:
        item_dict = {
            'item_id': row[0],
            'item_name': row[1],
            'description': row[2],
            'item_image': row[3],
            'is_featured_offer': bool(row[4] or 0),
            'is_new': _is_item_new(row[12]),
            'category_id': row[5],
            'item_category': row[6],
            'parent_category_id': row[7],
            'parent_category_name': row[8],
            'sub_category_id': row[13],
            'sub_category_name': row[14],
            'rating': float(row[10]) if row[10] else 4.0,
            'item_placed_at': row[12],
            'is_customizable': bool(row[11]) if row[11] is not None else False,
            'rating_count': 0,
            'variants': variants_data.get(row[0], [])
        }
        items_data.append(item_dict)

    top_offers = []
    paginator = PageNumberPagination()
    paginator.page_size = int(qp.get('page_size') or 10)
    paged = _paginate_list(items_data, page=qp.get('page', 1), page_size=paginator.page_size)
    paginated_items = paged['items']

    for item in paginated_items:
        if not _enrich_item_with_media_and_availability(request, business, item, business_type='R08'):
            continue
        # Basic offer fields (can be expanded later)
        item['diff_amount'] = "0.00"
        item['percent'] = "0.0"
        item['percent_display'] = 0
        item['diff_display'] = 0
        item['discount_percentage'] = 0
        item['is_new'] = _is_item_new(item.get('created_at'))
        is_new_main, _ = _is_item_new_debug(item.get('created_at'))
        for v in item.get('variants', []):
            is_new_var, _ = _is_item_new_debug(v.get('created_at'))
            if is_new_var:
                item['is_new'] = True
                break
        item['is_bestseller'] = _is_item_bestseller(item.get('item_id'), business_id, 'R08')
        _attach_badges_from_offer_fields(item)

    return _make_items_response(business_data=None, business=business, paginated_items=paginated_items, paged=paged, top_offers=top_offers)


def _service_items_r01(request, business, business_id, qp):
    """Service function for R01 (Grocery) items using raw SQL approach."""
    include_business_ids = _include_business_ids(business_id)
    biz_placeholders = ','.join(['%s'] * len(include_business_ids))
    search = qp.get('search', '')
    category_id = qp.get('category_id')
    category = qp.get('category')
    sub_category_id = qp.get('sub_category_id')
    min_price = qp.get('min_price')
    max_price = qp.get('max_price')
    ordering = qp.get('ordering', 'item_name')

    if min_price or max_price:
        return Response({"error": "Price filtering not supported for grocery products"}, status=status.HTTP_400_BAD_REQUEST)

    base_query = """
        SELECT DISTINCT
            gp.product_id as item_id,
            gp.product_name as item_name,
            gp.description,
            gp.main_image as item_image,
            gp.sub_images as sub_images,
            COALESCE(gp.is_featured, 0) as is_featured,
            COALESCE(uc_mapped.category_id, uc_by_id.category_id) as category_id,
            COALESCE(NULLIF(TRIM(gp.sub_category), ''), uc_mapped.category_name, uc_by_id.category_name) as item_category,
            COALESCE(uc_mapped.parent_category_id, uc_by_id.parent_category_id) as parent_category_id,
            uc_parent.category_name as parent_category_name,
            gp.sub_category as item_type,
            gp.rating,
            gp.created_at,
            gp.item_placed_at,
            gp.is_customizable,
            COALESCE(gp.sub_category_id, 0) as sub_category_id,
            gp.sub_category as sub_category_name,
            gp.base_price
        FROM Groceries_Products gp
        LEFT JOIN businesses b0 ON b0.business_id = gp.business_id
        -- First try: join by category_id if mapped
        LEFT JOIN universal_Categories uc_by_id
            ON uc_by_id.category_id = gp.category_id
            AND EXISTS (
                SELECT 1
                FROM category_mapping cm
                WHERE cm.is_active = 1
                  AND cm.category_id = uc_by_id.category_id
                  AND (cm.business_id = gp.business_id OR cm.business_id = b0.master)
            )
        -- Second try: match by sub_category text only if category_id join failed
        LEFT JOIN universal_Categories uc_mapped
            ON (uc_by_id.category_id IS NULL OR NOT EXISTS (
                SELECT 1 FROM category_mapping cm2 
                WHERE cm2.is_active = 1 
                AND cm2.category_id = gp.category_id
                AND (cm2.business_id = gp.business_id OR cm2.business_id = b0.master)
            ))
            AND gp.sub_category IS NOT NULL
            AND TRIM(gp.sub_category) != ''
            AND LOWER(
                REPLACE(REPLACE(REPLACE(REPLACE(TRIM(uc_mapped.category_name), '&', ''), ' ', ''), '-', ''), '_', '')
            ) = LOWER(
                REPLACE(REPLACE(REPLACE(REPLACE(TRIM(gp.sub_category), '&', ''), ' ', ''), '-', ''), '_', '')
            )
            AND EXISTS (
                SELECT 1
                FROM category_mapping cm
                WHERE cm.is_active = 1
                  AND cm.category_id = uc_mapped.category_id
                  AND (cm.business_id = gp.business_id OR cm.business_id = b0.master)
            )
        LEFT JOIN universal_Categories uc_parent ON uc_parent.category_id = COALESCE(uc_mapped.parent_category_id, uc_by_id.parent_category_id)
        WHERE 1=1
    """
    params = []
    base_query += " AND COALESCE(gp.is_visible, 1) = 1"
    base_query += f" AND gp.business_id IN ({biz_placeholders})"
    params.extend(include_business_ids)

    if search:
        base_query += " AND gp.product_name LIKE %s"
        params.append(f"%{search}%")

    # Only apply category mapping if category_id or category is provided
    # Don't apply it for sub_category_id only filtering
    if category_id or category:
        frag, frag_params = get_mapped_category_query_filter(
            table_alias='gp',
            business_ids=include_business_ids,
            category_id=category_id,
            category=category,
        )
        base_query += frag
        params.extend(frag_params)
    elif sub_category_id:
        # For subcategory-only filtering, just check if the subcategory is mapped
        try:
            sub_cat_id_int = int(str(sub_category_id).strip())
            # Check if this subcategory is mapped for the business
            with connection.cursor() as cursor:
                cursor.execute("""
                    SELECT COUNT(*) 
                    FROM category_mapping cm
                    WHERE cm.business_id IN (%s)
                      AND cm.category_id = %s
                      AND cm.is_active = 1
                """ % (','.join(['%s'] * len(include_business_ids)), '%s'), 
                include_business_ids + [sub_cat_id_int])
                is_mapped = cursor.fetchone()[0] > 0
            
            if not is_mapped:
                base_query += " AND 1=0"  # Subcategory not mapped
        except Exception:
            base_query += " AND 1=0"

    if sub_category_id:
        try:
            sub_cat_id_int = int(str(sub_category_id).strip())
            base_query += " AND gp.sub_category_id = %s"
            params.append(sub_cat_id_int)
        except Exception:
            base_query += " AND 1=0"

    ordering_map = {'product_name': 'item_name', 'selling_price': 'selling_price', 'created_at': 'created_at'}
    order_field = ordering_map.get(ordering.lstrip('-'), 'item_name')
    base_query += f" ORDER BY {order_field}{' DESC' if ordering.startswith('-') else ' ASC'}"

    with connection.cursor() as cursor:
        cursor.execute(base_query, params)
        product_rows = cursor.fetchall()

    product_ids = [row[0] for row in product_rows]
    variants_data = _fetch_variants_for_products(product_ids, business_type='R01')

    items_data = []
    for row in product_rows:
        item_dict = {
            'item_id': row[0],
            'item_name': row[1],
            'description': row[2],
            'item_image': row[3],
            'sub_images': row[4],
            'is_featured_offer': bool(row[5] or 0),
            'is_new': _is_item_new(row[12]),
            'category_id': row[6],
            'item_category': row[7],
            'parent_category_id': row[8],
            'parent_category_name': row[9],
            'item_type': row[10],
            'sub_category_id': row[15],
            'sub_category_name': row[16],
            'rating': 4.0,
            'item_placed_at': row[13],
            'is_customizable': bool(row[14]) if row[14] is not None else False,
            'base_price': None,
            'rating_count': 0,
            'variants': variants_data.get(row[0], [])
        }
        try:
            item_dict['rating'] = float(row[11]) if row[11] not in (None, '') else 4.0
        except Exception:
            pass
        try:
            item_dict['base_price'] = float(row[17]) if row[17] not in (None, '') else None
        except Exception:
            pass
        items_data.append(item_dict)

    top_offers = []
    paginator = PageNumberPagination()
    paginator.page_size = int(qp.get('page_size') or 10)
    paged = _paginate_list(items_data, page=qp.get('page', 1), page_size=paginator.page_size)
    paginated_items = paged['items']

    for item in paginated_items:
        if not _enrich_item_with_media_and_availability(request, business, item, business_type='R01'):
            continue
        # Offer/discount from first variant (as per existing inline logic)
        variants = item.get('variants', [])
        oc = Decimal('0')
        sp = Decimal('0')
        if variants:
            first_variant = variants[0]
            oc = Decimal(str(first_variant.get('original_cost') or '0'))
            sp = Decimal(str(first_variant.get('selling_price') or '0'))
        if oc > 0:
            diff = oc - sp
            if diff > 0:
                percent = (diff / oc * Decimal(100))
                percent_display = int(percent.quantize(Decimal('1'), rounding=ROUND_HALF_UP))
                diff_display = int(diff.quantize(Decimal('1'), rounding=ROUND_HALF_UP))
                item['diff_amount'] = str(diff.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP))
                item['percent'] = str(percent.quantize(Decimal('0.1'), rounding=ROUND_HALF_UP))
                item['percent_display'] = percent_display
                item['diff_display'] = diff_display
                item['discount_percentage'] = percent_display
            else:
                item['diff_amount'] = "0.00"
                item['percent'] = "0.0"
                item['percent_display'] = 0
                item['diff_display'] = 0
                item['discount_percentage'] = 0
        else:
            item['diff_amount'] = "0.00"
            item['percent'] = "0.0"
            item['percent_display'] = 0
            item['diff_display'] = 0
            item['discount_percentage'] = 0
        item['is_new'] = _is_item_new(item.get('created_at'))
        is_new_main, _ = _is_item_new_debug(item.get('created_at'))
        for v in item.get('variants', []):
            is_new_var, _ = _is_item_new_debug(v.get('created_at'))
            if is_new_var:
                item['is_new'] = True
                break
        item['is_bestseller'] = _is_item_bestseller(item.get('item_id'), business_id, 'R01')
        _attach_badges_from_offer_fields(item)
        item.pop('badge_text', None)
        item.pop('badge_type', None)

    return _make_items_response(business_data=None, business=business, paginated_items=paginated_items, paged=paged, top_offers=top_offers)


def _service_items_r08_django(request, business, business_id, qp):
    """Service function for R08 (Fashion) items using Django ORM approach."""
    from django.db.models import Prefetch
    from business.models import FashionProduct, FashionProductVariant
    from business.serializers import FashionProductSerializer, FashionProductVariantSerializer, FashionProductWithVariantsSerializer

    search = qp.get('search', '')
    category = qp.get('category')
    category_id = qp.get('category_id')
    sub_category_id = qp.get('sub_category_id')
    min_price = qp.get('min_price')
    max_price = qp.get('max_price')
    ordering = qp.get('ordering') or 'item_name'

    # Start with base queryset
    items = FashionProduct.objects.filter(is_active=True)
    if business_id:
        items = items.filter(business_id=business_id)

    # Apply filters
    if search:
        items = items.filter(name__icontains=search)
    if category:
        items = items.filter(category__category_name=category)
    if min_price:
        items = items.filter(base_price__gte=min_price)
    if max_price:
        items = items.filter(base_price__lte=max_price)

    # Apply ordering
    # Map common ordering names to actual model fields for R08
    order_map = {
        'item_name': 'name',
        'selling_price': 'base_price',
    }
    order_field = order_map.get(ordering.lstrip('-'), ordering.lstrip('-'))
    order_prefix = '-' if ordering.startswith('-') else ''
    items = items.order_by(f'{order_prefix}{order_field}')

    # Prefetch variants for performance
    items = items.prefetch_related(
        Prefetch('variants', queryset=FashionProductVariant.objects.filter(is_active=True))
    )

    # Paginate the queryset
    paginator = PageNumberPagination()
    paginator.page_size = int(qp.get('page_size') or 10)
    paginated_items = paginator.paginate_queryset(items, request)

    # Serialize items with variants
    items_data = []
    for item in paginated_items:
        item_data = FashionProductWithVariantsSerializer(item, context={'request': request}).data
        # Resolve subcategory name if stored as ID
        if isinstance(item_data.get('subcategory'), (int, str)) and str(item_data['subcategory']).isdigit():
            with connection.cursor() as cur:
                cur.execute("SELECT category_name FROM universal_Categories WHERE category_id = %s", [int(item_data['subcategory'])])
                row = cur.fetchone()
                if row:
                    item_data['subcategory'] = row[0]
        # Add default rating if not present
        item_data['rating'] = 4.0
        item_data['rating_count'] = 0
        # Add GST as separate field
        item_data['gst'] = str(item_data.get('gst_rate_default', '0.00'))
        item_data['is_featured_offer'] = bool(item_data.get('is_featured') or 0)
        item_data['is_new'] = _is_item_new(item_data.get('created_at'))
        is_new_main, reason_main = _is_item_new_debug(item_data.get('created_at'))
        print(f"[R08 DEBUG] product_id={item_data.get('product_id')} is_new_main={is_new_main} reason={reason_main}")
        # Also check variants for newer created_at
        variants = item_data.get('variants', [])
        if variants:
            for i, v in enumerate(variants):
                is_new_var, reason_var = _is_item_new_debug(v.get('created_at'))
                print(f"[R08 DEBUG] variant[{i}] created_at={v.get('created_at')} is_new={is_new_var} reason={reason_var}")
                if is_new_var:
                    item_data['is_new'] = True
                    print(f"[R08 DEBUG] set is_new=True due to variant[{i}]")
                    break
        item_data['is_bestseller'] = _is_item_bestseller(item_data.get('product_id'), business_id, 'R08')
        
        # Build new media response with categorized images and videos
        # Use main_image as primary and sub_images as additional media
        media_data = _build_media_response(
            request,
            item_data.get('main_image'),
            item_data.get('sub_images', [])
        )
        item_data['media'] = media_data

        # Add offer metadata based on original_cost and selling_price (use first variant)
        variants = item_data.get('variants', [])
        if variants:
            first_variant = variants[0]
            try:
                oc = Decimal(str(first_variant.get('original_cost') or '0'))
                sp = Decimal(str(first_variant.get('selling_price') or '0'))
            except Exception:
                oc = Decimal('0')
                sp = Decimal('0')

            if oc > 0:
                diff = oc - sp
                if diff > 0:
                    percent = (diff / oc * Decimal(100))
                    percent_display = int(percent.quantize(Decimal('1'), rounding=ROUND_HALF_UP))
                    diff_display = int(diff.quantize(Decimal('1'), rounding=ROUND_HALF_UP))
                    item_data['diff_amount'] = str(diff.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP))
                    item_data['percent'] = str(percent.quantize(Decimal('0.1'), rounding=ROUND_HALF_UP))
                    item_data['percent_display'] = percent_display
                    item_data['diff_display'] = diff_display
                    # Preserve featured flag derived from is_featured
                    item_data['is_featured_offer'] = bool(item_data.get('is_featured_offer', False))
                    item_data['discount_percentage'] = percent_display
                else:
                    item_data['diff_amount'] = "0.00"
                    item_data['percent'] = "0.0"
                    item_data['percent_display'] = 0
                    item_data['diff_display'] = 0
                    item_data['is_featured_offer'] = bool(item_data.get('is_featured_offer', False))
                    item_data['discount_percentage'] = 0
            else:
                item_data['diff_amount'] = "0.00"
                item_data['percent'] = "0.0"
                item_data['percent_display'] = 0
                item_data['diff_display'] = 0
                item_data['is_featured_offer'] = bool(item_data.get('is_featured_offer', False))
                item_data['discount_percentage'] = 0
        else:
            item_data['diff_amount'] = "0.00"
            item_data['percent'] = "0.0"
            item_data['percent_display'] = 0
            item_data['diff_display'] = 0
            item_data['is_featured_offer'] = bool(item_data.get('is_featured_offer', False))
            item_data['discount_percentage'] = 0

        items_data.append(item_data)

    for _it in items_data:
        if isinstance(_it, dict):
            if 'discount_percentage' in _it or 'percent_display' in _it:
                _attach_badges_from_offer_fields(_it)
            _it.pop('badge_text', None)
            _it.pop('badge_type', None)

    # Return paginated response
    return paginator.get_paginated_response({
        'business': None,  # Will be set by main view
        'is_business_open': bool(getattr(business, 'status', True)),
        'top_offers': [],  # No top offers for fashion yet
        'items': items_data,
        'total_items': items.count(),
        'total_pages': paginator.page.paginator.num_pages,
        'current_page': paginator.page.number,
        'page_size': paginator.page_size
    })


def _service_item_detail_r02(request, business_type, item_id):
    """Service function for R02 (Menu) item details."""
    from .models import OrderItems, Orders  # Import from correct module
    from django.db.models import Count, Sum, Max  # Import missing aggregation functions
    from business.models import MenuItemVariant  # Import MenuItemVariant model
    
    try:
        mid = int(item_id)
    except (TypeError, ValueError):
        return {'success': False, 'error': 'menu_item_id must be provided as integer'}, status.HTTP_400_BAD_REQUEST

    item = MenuItems.objects.select_related('business_id').filter(item_id=mid, is_active=True, status=True).first()
    if not item:
        return {'success': False, 'error': 'Menu item not found'}, status.HTTP_404_NOT_FOUND

    # Build new media response with categorized images and videos
    media_data = _build_media_response(
        request,
        getattr(item, 'item_image', None),
        []  # No sub_images for R02
    )
    
    qs = OrderItems.objects.filter(menu_item_id=mid).exclude(order_id__status=Orders.OrderStatus.CANCELLED)
    agg = qs.aggregate(
        total_orders=Count('order_id', distinct=True),
        total_quantity_sold=Sum('quantity'),
        last_ordered_at=Max('created_at')
    )

    # Calculate discount fields using the same logic as list view
    item_dict = {
        'selling_price': item.selling_price,
        'original_cost': item.original_cost
    }
    _apply_offer_metadata(item_dict, item.selling_price, item.original_cost)
    
    # Build item data with all required fields
    # Get variants for this item
    variants = MenuItemVariant.objects.filter(item_id=item.item_id, is_active=True).order_by('selling_price')
    variants_data = []
    
    for variant in variants:
        variant_data = {
            'variant_id': variant.variant_id,
            'size_label': variant.size_label,
            'sku': variant.sku,
            'selling_price': f"{round(float(variant.selling_price)):.2f}" if variant.selling_price is not None else None,
            'mrp': f"{round(float(variant.mrp)):.2f}" if variant.mrp is not None else None,
            'original_cost': f"{round(float(variant.original_cost)):.2f}" if variant.original_cost is not None else None,
            'stock_qty': variant.stock_qty if variant.stock_qty is not None else 0,
            'gst_percentage': f"{round(float(variant.gst)):.2f}" if variant.gst is not None else None,
            'charges': f"{round(float(variant.charges)):.2f}" if variant.charges is not None else None,
            'rating': float(variant.rating) if variant.rating else 4.0,
            'rating_count': int(variant.rating_count) if variant.rating_count else 0,
            'attributes': {
                "Portion": variant.size_label
            }
        }
        variants_data.append(variant_data)
    
    item_data = {
        'item_id': item.item_id,
        'name': item.item_name,
        'description': item.description or '',
        'category': item.item_category,
        'type': item.item_type,
        'is_variable': getattr(item, 'is_variable', False),
        'variants': variants_data,
        'selling_price': float(item.selling_price) if item.selling_price is not None else None,
        'original_cost': float(item.original_cost) if item.original_cost is not None else None,
        'gst_percentage': float(item.gst) if item.gst is not None else None,
        'gst': str(item.gst) if item.gst else "0.00",
        'charges': float(item.charges) if item.charges is not None else None,
        'quantity': item.quantity if item.quantity is not None else 0,
        'media': media_data,
        'business_id': item.business_id.business_id,
        'business_name': item.business_id.businessName,
        # Restaurant-specific fields
        'preparation_time': getattr(item, 'preparation_time', None),
        'availability_timings': getattr(item, 'availability_timings', None),
        'size_label': getattr(item, 'size_label', None),
        'business_features': getattr(item, 'business_features', []),  # Assuming this is a JSON field or related
        # Status fields
        'is_active': bool(getattr(item, 'is_active', True)),
        'status': bool(getattr(item, 'status', True)),
        'is_visible': bool(getattr(item, 'is_visible', True)),
        # Badge and promotional fields
        'is_featured_offer': bool(getattr(item, 'is_featured', 0)),
        'is_new': _is_item_new(getattr(item, 'created_at', None)),
        'is_bestseller': _is_item_bestseller(getattr(item, 'item_id', None), item.business_id.business_id, 'R02'),
        'rating': float(item.rating) if item.rating else 4.0,
        'rating_count': 0,  # Or calculate from variants if needed
        # Discount fields (calculated by _apply_offer_metadata)
        'diff_amount': item_dict.get('diff_amount', "0.00"),
        'percent': item_dict.get('percent', "0.0"),
        'percent_display': item_dict.get('percent_display', 0),
        'diff_display': item_dict.get('diff_display', 0),
        'discount_percentage': item_dict.get('discount_percentage', 0),
    }
    
    # Add variant groups for frontend
    from .views import build_variant_groups
    variant_groups = build_variant_groups(variants_data, 'menu')
    item_data['variant_groups'] = variant_groups

    # Apply badges
    _attach_badges_from_offer_fields(item_data)
    # Remove internal badge fields (keep only badges array)
    item_data.pop('badge_text', None)
    item_data.pop('badge_type', None)

    # Add availability logic using the same approach as list view
    from .availability_services import get_item_availability_status, get_stock_message
    
    # Add can_add_to_cart to each variant
    for variant in variants_data:
        variant_is_active = variant.get('is_active', True)
        variant_stock = variant.get('stock_qty', 0)
        # Can add to cart only if variant is active AND has stock > 0
        variant['can_add_to_cart'] = variant_is_active and variant_stock > 0
        
        # Set variant stock messages
        variant_stock_info = get_stock_message(variant_stock)
        variant['stock_message'] = variant_stock_info['stock_message']
        variant['stock_status'] = variant_stock_info['stock_status']
    
    # Set main item availability based on first variant or business logic
    if variants_data:
        # Use first variant for stock-based availability
        first_variant_stock = variants_data[0].get('stock_qty', 0)
        pseudo_item = type('PseudoItem', (), {
            'status': item.status,
            'is_active': item.is_active,
            'is_visible': getattr(item, 'is_visible', 1),
            'stock': first_variant_stock,
            'item_timings': getattr(item, 'availability_timings', None)
        })()
        
        availability = get_item_availability_status(item.business_id, pseudo_item)
        if availability is not None:
            item_data['can_add_to_cart'] = availability['can_add_to_cart']
            item_data['availability_status'] = availability['availability_status']
            item_data['availability_message'] = availability['availability_message']
            item_data['stock_message'] = availability['stock_message']
            item_data['stock_status'] = availability['stock_status']
            item_data['is_business_open'] = availability['is_business_open']
        else:
            # Default if availability check fails
            item_data['can_add_to_cart'] = False
            item_data['availability_status'] = 'unavailable'
            item_data['availability_message'] = 'Item unavailable'
    
    # Check if all variants are inactive
    if variants_data:
        all_variants_inactive = all(not variant.get('can_add_to_cart', True) for variant in variants_data)
        if all_variants_inactive:
            item_data['can_add_to_cart'] = False
            item_data['availability_status'] = 'disabled'
            item_data['availability_message'] = 'All variants are currently unavailable'

    data = {
        'success': True,
        'type': 'R02',
        'source': 'menu',
        'item': item_data,
        'order_stats': {
            'total_orders': int(agg.get('total_orders') or 0),
            'total_quantity_sold': int(agg.get('total_quantity_sold') or 0),
            'last_ordered_at': agg.get('last_ordered_at').isoformat() if agg.get('last_ordered_at') else None
        }
    }
    return data, status.HTTP_200_OK


def _service_item_detail_r01(request, business_type, product_id=None, variant_id=None):
    """Service function for R01 (Grocery) item details."""
    from .models import OrderItems, Orders  # Import from correct module
    from .gro_models import GroceriesProducts, GroceriesProductVariants, GroceriesOrderItems  # Import grocery models
    from django.db.models import Count, Sum, Max, Min  # Import missing aggregation functions
    
    pid = None
    vid = None
    try:
        if product_id:
            pid = int(product_id)
        if variant_id:
            vid = int(variant_id)
    except (TypeError, ValueError):
        return {'success': False, 'error': 'product_id/variant_id must be integers'}, status.HTTP_400_BAD_REQUEST

    if not pid and not vid:
        return {'success': False, 'error': 'Provide product_id (or variant_id) for grocery source'}, status.HTTP_400_BAD_REQUEST

    product = None
    if pid:
        product = GroceriesProducts.objects.filter(product_id=pid).first()
        if not product:
            return {'success': False, 'error': 'Grocery product not found'}, status.HTTP_404_NOT_FOUND
    elif vid:
        variant = GroceriesProductVariants.objects.select_related('product').filter(variant_id=vid, is_active=True).first()
        if not variant:
            return {'success': False, 'error': 'Grocery variant not found'}, status.HTTP_404_NOT_FOUND
        product = variant.product

    variants_qs = GroceriesProductVariants.objects.filter(product=product, is_active=True)
    variant_ids = list(variants_qs.values_list('variant_id', flat=True))
    min_price = variants_qs.aggregate(mp=Min('selling_price')).get('mp') if variants_qs.exists() else None
    max_price = variants_qs.aggregate(Max('selling_price')).get('M') if variants_qs.exists() else None

    category_name = None
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT category_name FROM universal_Categories WHERE category_id = %s LIMIT 1",
                [int(getattr(product, 'category_id', None) or 0)]
            )
            r = cursor.fetchone()
            if r and r[0] is not None:
                category_name = r[0]
    except Exception:
        category_name = None

    business_name = None
    try:
        from kirazee_app.models import Business
        biz = Business.objects.filter(business_id=getattr(product, 'business_id', None)).first()
        business_name = getattr(biz, 'businessName', None) if biz else None
    except Exception:
        business_name = None

    std_qs = OrderItems.objects.filter(product_item_id__in=variant_ids)
    std_qs = std_qs.exclude(order_id__status=Orders.OrderStatus.CANCELLED)
    std_agg = std_qs.aggregate(
        total_orders=Count('order_id', distinct=True),
        total_quantity_sold=Sum('quantity'),
        last_ordered_at=Max('created_at')
    )

    gro_qs = GroceriesOrderItems.objects.filter(product=product)
    gro_qs = gro_qs.exclude(order__order_status='cancelled')
    gro_agg = gro_qs.aggregate(
        total_orders=Count('order', distinct=True),
        total_quantity_sold=Sum('quantity'),
        last_ordered_at=Max('order__updated_at')
    )

    def _max_dt(a, b):
        if a and b:
            return a if a >= b else b
        return a or b

    total_orders = int((std_agg.get('total_orders') or 0) + (gro_agg.get('total_orders') or 0))
    total_qty = int((std_agg.get('total_quantity_sold') or 0) + (gro_agg.get('total_quantity_sold') or 0))
    last_dt = _max_dt(std_agg.get('last_ordered_at'), gro_agg.get('last_ordered_at'))

    # Build new media response with categorized images and videos
    media_data = _build_media_response(
        request,
        getattr(product, 'main_image', None),
        getattr(product, 'sub_images', None)
    )

    # Calculate discount fields from first variant (same logic as list view)
    first_variant = variants_qs.first() if variants_qs.exists() else None
    discount_fields = {
        'diff_amount': "0.00",
        'percent': "0.0",
        'percent_display': 0,
        'diff_display': 0,
        'discount_percentage': 0,
    }
    
    if first_variant:
        try:
            oc = Decimal(str(first_variant.original_cost or '0'))
            sp = Decimal(str(first_variant.selling_price or '0'))
            if oc > 0:
                diff = oc - sp
                if diff > 0:
                    percent = (diff / oc * Decimal(100))
                    percent_display = int(percent.quantize(Decimal('1'), rounding=ROUND_HALF_UP))
                    diff_display = int(diff.quantize(Decimal('1'), rounding=ROUND_HALF_UP))
                    discount_fields = {
                        'diff_amount': str(diff.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)),
                        'percent': str(percent.quantize(Decimal('0.1'), rounding=ROUND_HALF_UP)),
                        'percent_display': percent_display,
                        'diff_display': diff_display,
                        'discount_percentage': percent_display,
                    }
        except Exception:
            pass

    # Build item data with all required fields
    item_data = {
        'product_id': product.product_id,
        'name': product.product_name,
        'brand_name': getattr(product, 'brand_name', None),
        'description': getattr(product, 'description', '') or '',
        'category': category_name,
        'category_id': getattr(product, 'category_id', None),
        'sub_category': getattr(product, 'sub_category', None),
        'is_organic': bool(getattr(product, 'is_organic', False)),
        'is_visible': bool(getattr(product, 'is_visible', True)),
        'is_customizable': bool(getattr(product, 'is_customizable', False)),
        'rating': float(product.rating) if getattr(product, 'rating', None) is not None else 4.0,
        'rating_count': 0,  # Or calculate from variants if needed
        'price_min': float(min_price) if min_price is not None else None,
        'price_max': float(max_price) if max_price is not None else None,
        'media': media_data,
        'item_placed_at': getattr(product, 'item_placed_at', None),
        'created_at': product.created_at.isoformat() if getattr(product, 'created_at', None) else None,
        'updated_at': product.updated_at.isoformat() if getattr(product, 'updated_at', None) else None,
        'business_id': getattr(product, 'business_id', None),
        'business_name': business_name,
        # Grocery-specific fields
        'quantity': sum(v.stock for v in variants_qs if v.stock is not None),  # Total stock across variants
        'base_price': float(getattr(product, 'base_price', 0)) if getattr(product, 'base_price', None) is not None else None,
        # Status fields
        'is_active': bool(getattr(product, 'is_visible', True)),  # Using is_visible as is_active for products
        'status': bool(getattr(product, 'is_visible', True)),
        # Badge and promotional fields
        'is_featured_offer': bool(getattr(product, 'is_featured', 0)),
        'is_new': _is_item_new(getattr(product, 'created_at', None)),
        'is_bestseller': _is_item_bestseller(getattr(product, 'product_id', None), getattr(product, 'business_id', None), 'R01'),
        # Discount fields
        **discount_fields,
        'variants': [
            {
                'variant_id': v.variant_id,
                'sku': v.sku,
                'size': v.size,
                'net_weight': v.net_weight,
                'net_weight_unit': v.net_weight_unit,
                'selling_price': f"{round(float(v.selling_price)):.2f}" if v.selling_price is not None else None,
                'original_cost': f"{round(float(v.original_cost)):.2f}" if getattr(v, 'original_cost', None) is not None else None,
                'gst': str(v.gst) if getattr(v, 'gst', None) is not None else "0.00",
                'charges': f"{round(float(v.charges)):.2f}" if getattr(v, 'charges', None) is not None else None,
                'stock': v.stock,
                'is_active': bool(getattr(v, 'is_active', True)),
                'rating': float(v.rating) if v.rating else 4.0,
                'rating_count': int(v.rating_count) if v.rating_count else 0,
                'attributes': getattr(v, 'attributes', {}) or {}
            } for v in variants_qs
        ]
    }
    
    # Add variant groups for frontend
    from .views import build_variant_groups
    variant_groups = build_variant_groups(item_data['variants'], 'grocery')
    item_data['variant_groups'] = variant_groups

    # Apply badges
    _attach_badges_from_offer_fields(item_data)
    # Remove internal badge fields (keep only badges array)
    item_data.pop('badge_text', None)
    item_data.pop('badge_type', None)

    # Add availability logic using same approach as list view
    from .availability_services import get_item_availability_status, get_stock_message
    
    # Add can_add_to_cart to each variant
    for variant in item_data['variants']:
        variant_is_active = variant.get('is_active', True)
        variant_stock = variant.get('stock', 0)
        # Can add to cart only if variant is active AND has stock > 0
        variant['can_add_to_cart'] = variant_is_active and variant_stock > 0
        
        # Set variant stock messages
        variant_stock_info = get_stock_message(variant_stock)
        variant['stock_message'] = variant_stock_info['stock_message']
        variant['stock_status'] = variant_stock_info['stock_status']
    
    # Set main item availability based on business logic
    pseudo_item = type('PseudoItem', (), {
        'status': item_data.get('status', True),
        'is_active': item_data.get('is_active', True),
        'is_visible': item_data.get('is_visible', True),
        'stock': item_data.get('quantity', 0),
        'item_timings': None  # Grocery products typically don't have timing restrictions
    })()
    
    # Get business object for availability check
    try:
        from kirazee_app.models import Business
        business = Business.objects.filter(business_id=item_data.get('business_id')).first()
        if business:
            availability = get_item_availability_status(business, pseudo_item)
            if availability is not None:
                item_data['can_add_to_cart'] = availability['can_add_to_cart']
                item_data['availability_status'] = availability['availability_status']
                item_data['availability_message'] = availability['availability_message']
                item_data['stock_message'] = availability['stock_message']
                item_data['stock_status'] = availability['stock_status']
                item_data['is_business_open'] = availability['is_business_open']
            else:
                # Default if availability check fails
                item_data['can_add_to_cart'] = False
                item_data['availability_status'] = 'unavailable'
                item_data['availability_message'] = 'Item unavailable'
        else:
            # Default if business not found
            item_data['can_add_to_cart'] = False
            item_data['availability_status'] = 'unavailable'
            item_data['availability_message'] = 'Business not found'
    except Exception:
        # Default if error occurs
        item_data['can_add_to_cart'] = False
        item_data['availability_status'] = 'unavailable'
        item_data['availability_message'] = 'Availability check failed'
    
    # Check if all variants are inactive
    if item_data['variants']:
        all_variants_inactive = all(not variant.get('can_add_to_cart', True) for variant in item_data['variants'])
        if all_variants_inactive:
            item_data['can_add_to_cart'] = False
            item_data['availability_status'] = 'disabled'
            item_data['availability_message'] = 'All variants are currently unavailable'

    data = {
        'success': True,
        'type': 'R01',
        'source': 'grocery',
        'item': item_data,
        'order_stats': {
            'total_orders': total_orders,
            'total_quantity_sold': total_qty,
            'last_ordered_at': last_dt.isoformat() if last_dt else None,
            'breakdown': {
                'standard_orders': {
                    'orders': int(std_agg.get('total_orders') or 0),
                    'quantity': int(std_agg.get('total_quantity_sold') or 0)
                },
                'grocery_orders': {
                    'orders': int(gro_agg.get('total_orders') or 0),
                    'quantity': int(gro_agg.get('total_quantity_sold') or 0)
                }
            }
        }
    }
    return data, status.HTTP_200_OK


def _service_item_detail_r08(request, business_type, product_id=None, variant_id=None):
    """Service function for R08 (Fashion) item details."""
    from business.models import FashionProduct, FashionProductVariant
    from .models import OrderItems, Orders  # Import from correct module
    from django.db.models import Count, Sum, Max, Min  # Import missing aggregation functions

    pid = None
    vid = None
    try:
        if product_id:
            pid = int(product_id)
        if variant_id:
            vid = int(variant_id)
    except (TypeError, ValueError):
        return {'success': False, 'error': 'product_id/variant_id must be integers'}, status.HTTP_400_BAD_REQUEST

    if not pid and not vid:
        return {'success': False, 'error': 'Provide product_id (or variant_id) for fashion source'}, status.HTTP_400_BAD_REQUEST

    product = None
    if pid:
        product = FashionProduct.objects.filter(product_id=pid, is_active=True).first()
        if not product:
            return {'success': False, 'error': 'Fashion product not found'}, status.HTTP_404_NOT_FOUND
    elif vid:
        v = FashionProductVariant.objects.select_related('product').filter(variant_id=vid, is_active=True).first()
        if not v:
            return {'success': False, 'error': 'Fashion variant not found'}, status.HTTP_404_NOT_FOUND
        product = v.product

    variants_qs = FashionProductVariant.objects.filter(product=product, is_active=True)
    variant_ids = list(variants_qs.values_list('variant_id', flat=True))

    price_min = variants_qs.aggregate(mp=Min('selling_price')).get('mp') if variants_qs.exists() else None
    price_max = variants_qs.aggregate(Max('selling_price')).get('M') if variants_qs.exists() else None

    business_name = None
    try:
        business_name = getattr(getattr(product, 'business_id', None), 'businessName', None)
    except Exception:
        business_name = None

    std_qs = OrderItems.objects.filter(product_item_id__in=variant_ids)
    std_qs = std_qs.exclude(order_id__status=Orders.OrderStatus.CANCELLED)
    std_agg = std_qs.aggregate(
        total_orders=Count('order_id', distinct=True),
        total_quantity_sold=Sum('quantity'),
        last_ordered_at=Max('created_at')
    )

    # Build new media response with categorized images and videos
    sub_images_data = getattr(product, 'sub_images', None)
    media_data = _build_media_response(
        request,
        getattr(product, 'main_image', None),
        sub_images_data
    )

    # Calculate discount fields from first variant (same logic as list view)
    first_variant = variants_qs.first() if variants_qs.exists() else None
    discount_fields = {
        'diff_amount': "0.00",
        'percent': "0.0",
        'percent_display': 0,
        'diff_display': 0,
        'discount_percentage': 0,
    }
    
    if first_variant:
        try:
            oc = Decimal(str(first_variant.original_cost or '0'))
            sp = Decimal(str(first_variant.selling_price or '0'))
            if oc > 0:
                diff = oc - sp
                if diff > 0:
                    percent = (diff / oc * Decimal(100))
                    percent_display = int(percent.quantize(Decimal('1'), rounding=ROUND_HALF_UP))
                    diff_display = int(diff.quantize(Decimal('1'), rounding=ROUND_HALF_UP))
                    discount_fields = {
                        'diff_amount': str(diff.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)),
                        'percent': str(percent.quantize(Decimal('0.1'), rounding=ROUND_HALF_UP)),
                        'percent_display': percent_display,
                        'diff_display': diff_display,
                        'discount_percentage': percent_display,
                    }
        except Exception:
            pass

    # Build item data with all required fields
    item_data = {
        'product_id': product.product_id,
        'name': getattr(product, 'name', None),
        'brand': getattr(product, 'brand', None),
        'description': getattr(product, 'description', '') or '',
        'category_id': getattr(product, 'category_id', None),
        'subcategory': getattr(product, 'subcategory', None),
        'rating': float(product.rating) if getattr(product, 'rating', None) is not None else 4.0,
        'rating_count': 0,  # Or calculate from variants if needed
        'price_min': float(price_min) if price_min is not None else None,
        'price_max': float(price_max) if price_max is not None else None,
        'media': media_data,
        'business_id': getattr(getattr(product, 'business_id', None), 'business_id', None),
        'business_name': business_name,
        # Fashion-specific fields
        'quantity': sum(v.stock_qty for v in variants_qs if getattr(v, 'stock_qty', None) is not None),  # Total stock
        'base_price': float(getattr(product, 'base_price', 0)) if getattr(product, 'base_price', None) is not None else None,
        'gst_rate_default': str(getattr(product, 'gst_rate_default', '0.00')),
        'gst': str(getattr(product, 'gst_rate_default', '0.00')),
        # Status fields
        'is_active': bool(getattr(product, 'is_active', True)),
        'status': bool(getattr(product, 'is_active', True)),
        'is_visible': bool(getattr(product, 'is_visible', True)),
        # Badge and promotional fields
        'is_featured_offer': bool(getattr(product, 'is_featured', 0)),
        'is_new': _is_item_new(getattr(product, 'created_at', None)),
        'is_bestseller': _is_item_bestseller(getattr(product, 'product_id', None), getattr(getattr(product, 'business_id', None), 'business_id', None), 'R08'),
        # Discount fields
        **discount_fields,
        'variants': [
            {
                'variant_id': v.variant_id,
                'sku': v.sku,
                'selling_price': f"{round(float(v.selling_price)):.2f}" if v.selling_price is not None else None,
                'mrp': f"{round(float(v.mrp)):.2f}" if getattr(v, 'mrp', None) is not None else None,
                'original_cost': f"{round(float(getattr(v, 'original_cost', 0))) :.2f}" if getattr(v, 'original_cost', None) is not None else None,
                'stock_qty': int(getattr(v, 'stock_qty', 0) or 0),
                'stock': int(getattr(v, 'stock', 0) or 0),
                'size': getattr(v, 'size', None),
                'color': getattr(v, 'color', None),
                'material': getattr(v, 'material', None),
                'gender': getattr(v, 'gender', None),
                'rating': float(v.rating) if v.rating else 4.0,
                'rating_count': int(v.rating_count) if v.rating_count else 0,
                'attributes': {
                    'Size': getattr(v, 'size', None),
                    'Color': getattr(v, 'color', None),
                    'Material': getattr(v, 'material', None),
                    **(getattr(v, 'attributes', None) or {})
                },
                'is_active': bool(getattr(v, 'is_active', True)),
            } for v in variants_qs
        ]
    }
    
    # Add variant groups for frontend
    from .views import build_variant_groups
    variant_groups = build_variant_groups(item_data['variants'], 'fashion')
    item_data['variant_groups'] = variant_groups

    # Apply badges
    _attach_badges_from_offer_fields(item_data)
    # Remove internal badge fields (keep only badges array)
    item_data.pop('badge_text', None)
    item_data.pop('badge_type', None)

    # Add availability logic using same approach as list view
    from .availability_services import get_item_availability_status, get_stock_message
    
    # Add can_add_to_cart to each variant
    for variant in item_data['variants']:
        variant_is_active = variant.get('is_active', True)
        variant_stock = variant.get('stock', 0)
        # Can add to cart only if variant is active AND has stock > 0
        variant['can_add_to_cart'] = variant_is_active and variant_stock > 0
        
        # Set variant stock messages
        variant_stock_info = get_stock_message(variant_stock)
        variant['stock_message'] = variant_stock_info['stock_message']
        variant['stock_status'] = variant_stock_info['stock_status']
    
    # Set main item availability based on business logic
    pseudo_item = type('PseudoItem', (), {
        'status': item_data.get('status', True),
        'is_active': item_data.get('is_active', True),
        'is_visible': item_data.get('is_visible', True),
        'stock': item_data.get('quantity', 0),
        'item_timings': None  # Fashion products typically don't have timing restrictions
    })()
    
    # Get business object for availability check
    try:
        business_id = item_data.get('business_id')
        if business_id:
            from kirazee_app.models import Business
            business = Business.objects.filter(business_id=business_id).first()
            if business:
                availability = get_item_availability_status(business, pseudo_item)
                if availability is not None:
                    item_data['can_add_to_cart'] = availability['can_add_to_cart']
                    item_data['availability_status'] = availability['availability_status']
                    item_data['availability_message'] = availability['availability_message']
                    item_data['stock_message'] = availability['stock_message']
                    item_data['stock_status'] = availability['stock_status']
                    item_data['is_business_open'] = availability['is_business_open']
                else:
                    # Default if availability check fails
                    item_data['can_add_to_cart'] = False
                    item_data['availability_status'] = 'unavailable'
                    item_data['availability_message'] = 'Item unavailable'
            else:
                # Default if business not found
                item_data['can_add_to_cart'] = False
                item_data['availability_status'] = 'unavailable'
                item_data['availability_message'] = 'Business not found'
        else:
            # Default if no business_id
            item_data['can_add_to_cart'] = False
            item_data['availability_status'] = 'unavailable'
            item_data['availability_message'] = 'Business ID missing'
    except Exception:
        # Default if error occurs
        item_data['can_add_to_cart'] = False
        item_data['availability_status'] = 'unavailable'
        item_data['availability_message'] = 'Availability check failed'
    
    # Check if all variants are inactive
    if item_data['variants']:
        all_variants_inactive = all(not variant.get('can_add_to_cart', True) for variant in item_data['variants'])
        if all_variants_inactive:
            item_data['can_add_to_cart'] = False
            item_data['availability_status'] = 'disabled'
            item_data['availability_message'] = 'All variants are currently unavailable'

    data = {
        'success': True,
        'type': 'R08',
        'source': 'fashion',
        'item': item_data,
        'order_stats': {
            'total_orders': int(std_agg.get('total_orders') or 0),
            'total_quantity_sold': int(std_agg.get('total_quantity_sold') or 0),
            'last_ordered_at': std_agg.get('last_ordered_at').isoformat() if std_agg.get('last_ordered_at') else None
        }
    }
    return data, status.HTTP_200_OK


def _service_items_r02(request, business, business_id, qp):
    """Service function for R02 (Menu) items using Django ORM approach."""
    paginator = PageNumberPagination()
    try:
        paginator.page_size = int(qp.get('page_size') or 10)
    except Exception:
        paginator.page_size = 10

    items = MenuItems.objects.filter(status=True, is_visible=1)
    items = items.filter(business_id=business_id)

    search = qp.get('search')
    category = qp.get('category')
    category_id = qp.get('category_id')
    sub_category_id = qp.get('sub_category_id')
    min_price = qp.get('min_price')
    max_price = qp.get('max_price')
    ordering = qp.get('ordering') or 'item_name'

    if search:
        items = items.filter(item_name__icontains=search)
    if category_id:
        try:
            items = items.filter(item_category_id=int(str(category_id).strip()))
        except Exception:
            items = items.none()
    if sub_category_id:
        try:
            items = items.filter(sub_category_id=int(str(sub_category_id).strip()))
        except Exception:
            items = items.none()
    if category:
        items = items.filter(item_category=category)
    if min_price:
        items = items.filter(selling_price__gte=min_price)
    if max_price:
        items = items.filter(selling_price__lte=max_price)

    items = items.order_by(ordering)
    page_all = _is_page_all(qp.get('page'))
    if page_all:
        paginated_items = list(items)
        paged = {
            'page': 1,
            'page_size': len(paginated_items),
            'items': paginated_items,
            'total_items': len(paginated_items),
            'total_pages': 1,
            'next': None,
            'previous': None,
        }
    else:
        paginated_items = paginator.paginate_queryset(items, request)

    items_data = []
    for item in paginated_items:
        item_data = MenuItemsSerializer(item, context={'request': request}).data
        
        # Requirement 1 & 2: Dynamic parent rating with 4.0 fallback
        item_data['rating'] = float(item.rating) if item.rating else 4.0
        
        # Optional: Calculate aggregate rating count if you want it on list view
        # item_data['rating_count'] = MenuItemVariant.objects.filter(item_id=item.item_id).aggregate(Sum('rating_count'))['rating_count__sum'] or 0
        item_data['rating_count'] = 0 # Or set logic to pull from parent if column exists
        item_data['gst'] = str(item.gst) if item.gst else "0.00"
        item_data['is_featured_offer'] = bool(getattr(item, 'is_featured', 0))
        item_data['is_new'] = _is_item_new(getattr(item, 'created_at', None))
        is_new_main, reason_main = _is_item_new_debug(getattr(item, 'created_at', None))
        item_data['is_bestseller'] = _is_item_bestseller(getattr(item, 'item_id', None), business_id, 'R02')

        media_data = _build_media_response(
            request,
            item_data.get('item_image'),
            []
        )
        item_data['media'] = media_data
        item_data.pop('item_image', None)

        # Round all price fields in variants to 2 decimal places
        variants = item_data.get('variants', [])
        if variants:
            for variant in variants:
                if 'selling_price' in variant:
                    variant['selling_price'] = f"{round(float(variant['selling_price'] or 0)):.2f}"
                if 'original_cost' in variant:
                    variant['original_cost'] = f"{round(float(variant['original_cost'] or 0)):.2f}"
        
        # TOP-DOWN AVAILABILITY: Calculate parent context first
        parent_context = get_availability_context(business, item)
        
        # If parent is hidden, skip this item entirely
        if parent_context['status'] == 'HIDDEN':
            continue
        
        # Set parent-level availability fields
        item_data['can_add_to_cart'] = parent_context['can_add']
        item_data['availability_status'] = parent_context['status']
        item_data['availability_message'] = parent_context['message']
        item_data['is_business_open'] = parent_context['is_open']
        
        # Calculate per-variant availability (inherits parent context)
        if variants:
            any_variant_available = False
            for variant in variants:
                variant_avail = calculate_variant_availability(variant, parent_context, business_type='R02')
                variant['can_add_to_cart'] = variant_avail['can_add_to_cart']
                variant['availability_status'] = variant_avail['availability_status']
                variant['availability_message'] = variant_avail['availability_message']
                
                # Set variant stock messages
                variant_stock = variant.get('stock_qty', 0) or variant.get('stock', 0)
                variant_stock_info = get_stock_message(variant_stock)
                variant['stock_message'] = variant_stock_info['stock_message']
                variant['stock_status'] = variant_stock_info['stock_status']
                
                if variant_avail['can_add_to_cart']:
                    any_variant_available = True
            
            # If no variants are available, update parent status
            if not any_variant_available and parent_context['can_add']:
                item_data['can_add_to_cart'] = False
                item_data['availability_status'] = 'OUT_OF_STOCK'
                item_data['availability_message'] = 'All variants are out of stock'
            
            # Get stock info for parent from first variant
            first_variant = variants[0]
            selling_price = Decimal(str(first_variant.get('selling_price', 0)))
            original_cost = Decimal(str(first_variant.get('original_cost', 0)))
            _apply_offer_metadata(item_data, selling_price, original_cost)
            
            # Set parent stock fields from first variant
            parent_stock = first_variant.get('stock_qty', 0) or first_variant.get('stock', 0)
            parent_stock_info = get_stock_message(parent_stock)
            item_data['stock_message'] = parent_stock_info['stock_message']
            item_data['stock_status'] = parent_stock_info['stock_status']
        else:
            # No variants - use parent item stock if any
            parent_stock = getattr(item, 'stock_qty', None) or getattr(item, 'stock', None)
            parent_stock_info = get_stock_message(parent_stock)
            item_data['stock_message'] = parent_stock_info['stock_message']
            item_data['stock_status'] = parent_stock_info['stock_status']
            _apply_offer_metadata(item_data, None, None)
        _attach_badges_from_offer_fields(item_data)
        item_data.pop('badge_text', None)
        item_data.pop('badge_type', None)
        items_data.append(item_data)

    LIMIT_OFFERS = 6
    offer_qs = (
        MenuItems.objects.filter(
            status=True,
            business_id=business_id,
            original_cost__isnull=False,
            selling_price__isnull=False,
            original_cost__gt=0,
        )
        .annotate(
            diff_amount=ExpressionWrapper(
                F('original_cost') - F('selling_price'),
                output_field=DecimalField(max_digits=10, decimal_places=2),
            )
        )
        .filter(diff_amount__gt=0)
    )
    candidates = list(
        offer_qs.values(
            'item_id', 'item_name', 'description', 'item_image', 'item_category', 'category_id', 'sub_category_id', 'sub_category',
            'item_type', 'selling_price', 'original_cost', 'gst', 'charges', 'quantity', 'is_featured'
        )[:200]
    )

    category_ids = set()
    sub_category_ids = set()
    for cand in candidates:
        if cand.get('category_id'):
            category_ids.add(cand.get('category_id'))
        if cand.get('sub_category_id'):
            sub_category_ids.add(cand.get('sub_category_id'))

    cat_name_map = {}
    sub_cat_name_map = {}
    if category_ids:
        with connection.cursor() as cursor:
            format_strings = ','.join(['%s'] * len(category_ids))
            cursor.execute(
                f"SELECT category_id, category_name FROM universal_Categories WHERE category_id IN ({format_strings})",
                list(category_ids),
            )
            for row in cursor.fetchall():
                cat_name_map[row[0]] = row[1]

    if sub_category_ids:
        with connection.cursor() as cursor:
            format_strings = ','.join(['%s'] * len(sub_category_ids))
            cursor.execute(
                f"SELECT category_id, category_name FROM universal_Categories WHERE category_id IN ({format_strings})",
                list(sub_category_ids),
            )
            for row in cursor.fetchall():
                sub_cat_name_map[row[0]] = row[1]

    processed = []
    for it in candidates:
        try:
            oc = Decimal(str(it.get('original_cost') or '0'))
            sp = Decimal(str(it.get('selling_price') or '0'))
        except InvalidOperation:
            continue
        if oc <= 0:
            continue
        diff = oc - sp
        if diff <= 0:
            continue

        percent = (diff / oc * Decimal(100))
        percent_display = int(percent.quantize(Decimal('1'), rounding=ROUND_HALF_UP))
        diff_display = int(diff.quantize(Decimal('1'), rounding=ROUND_HALF_UP))
        media_data = _build_media_response(request, it.get('item_image'), [])

        row_out = {
            'item_id': it.get('item_id'),
            'item_name': it.get('item_name'),
            'selling_price': f"{round(float(sp)):.2f}",
            'original_cost': f"{round(float(oc)):.2f}",
            'item_category': it.get('item_category'),
            'category_id': it.get('category_id'),
            'category_name': cat_name_map.get(it.get('category_id')) or it.get('item_category'),
            'sub_Category_id': it.get('sub_category_id'),
            'sub_category_name': sub_cat_name_map.get(it.get('sub_category_id')) or it.get('sub_category'),
            'sub_category': it.get('sub_category'),
            'diff_amount': f"{diff.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP):.2f}",
            'percent': f"{percent.quantize(Decimal('0.1'), rounding=ROUND_HALF_UP):.1f}",
            'percent_display': percent_display,
            'diff_display': diff_display,
            'is_featured_offer': bool(it.get('is_featured') or 0),
            'is_new': False,  # Top offers typically not new; adjust if needed
            'is_bestseller': _is_item_bestseller(it.get('item_id'), business_id, 'R02'),
            'media': media_data,
        }
        row_out['discount_percentage'] = percent_display
        _attach_badges_from_offer_fields(row_out)
        row_out.pop('badge_text', None)
        row_out.pop('badge_type', None)
        processed.append(row_out)

    processed.sort(key=lambda x: (-float(x['percent']), float(x['selling_price']) if x['selling_price'] else 0))
    top_offers = processed[:LIMIT_OFFERS]

    if page_all:
        # Keep the same response shape as R01/R08 raw-SQL services when page=all
        paged['total_items'] = len(items_data)
        paged['page_size'] = len(items_data)
        return _make_items_response(business_data=None, business=business, paginated_items=items_data, paged=paged, top_offers=top_offers)

    return paginator.get_paginated_response({
        'top_offers': top_offers,
        'items': items_data,
        'total_items': items.count(),
        'total_pages': paginator.page.paginator.num_pages,
        'current_page': paginator.page.number,
        'page_size': paginator.page_size
    })


#Display Menu Items
@swagger_auto_schema(methods=['GET', 'POST'], tags=['Consumer'])
@api_view(['GET', 'POST'])
def ItemsViewBasedonBusinessID(request):
    """Main view function that dispatches to appropriate service based on business type."""
    if request.method in ['GET', 'POST']:
        business_id = request.query_params.get("business_id", None)
        # Accept both 'type' and 'businessType' parameters for flexibility
        business_type = request.query_params.get("type", None) or request.query_params.get("businessType", None)

        if not business_type:
            return Response({"error": "businessType is required"}, status=status.HTTP_400_BAD_REQUEST)

        try:
            business, business_data = _get_business_context(request, business_id)
            qp = _parse_items_query_params(request)

            # Dispatch to appropriate service based on business type
            if business_type == 'R02':
                # Restaurant/Menu items
                resp = _service_items_r02(request, business, business_id, qp)
                payload = resp.data
                payload['business'] = business_data
                payload['is_business_open'] = bool(getattr(business, 'status', True))
                return Response(payload, status=resp.status_code)

            elif business_type == 'R08':
                # Fashion products - using raw SQL approach (can switch to Django ORM if needed)
                try:
                    resp = _service_items_r08_raw_sql(request, business, business_id, qp)
                    payload = resp.data
                    payload['business'] = business_data
                    return Response(payload, status=resp.status_code)
                except Exception as e:
                    print(f"[ERROR] R08 processing failed: {str(e)}")
                    return Response({"error": f"Failed to fetch fashion items: {str(e)}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

            elif business_type == 'R01':
                # Grocery products
                try:
                    resp = _service_items_r01(request, business, business_id, qp)
                    payload = resp.data
                    payload['business'] = business_data
                    return Response(payload, status=resp.status_code)
                except Exception as e:
                    error_trace = traceback.format_exc()
                    error_response = {
                        "error": "An error occurred while processing your request",
                        "details": str(e)
                    }
                    if settings.DEBUG:
                        error_response["trace"] = error_trace
                    return Response(error_response, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

            else:
                return Response({"error": "Invalid businessType"}, status=status.HTTP_400_BAD_REQUEST)

        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

#Add to Cart
@swagger_auto_schema(method='POST', tags=['Consumer'])
@api_view(['POST'])
def AddToCartViewBasedonBusinessID(request):
    """
    Universal add to cart endpoint using optimized service layer.
    Handles all business types (R01, R02, R08) with automatic business type detection.
    """
    from .cart_services import CartService
    from .utils import parse_json_input
    from consumer.image_utils import build_s3_file_url
    
    # 1. Extraction & Validation
    user_id = request.GET.get("user_id")
    business_id = request.GET.get("business_id")
    item_id = request.data.get("item_id")
    variant_id = request.data.get("variant_id")
    quantity = int(request.data.get("quantity", 1))
    customizations_input = request.data.get("customizations")

    if getattr(settings, 'DEBUG', False):
        print("[AddToCart] incoming", {
            "user_id": user_id,
            "business_id": business_id,
            "item_id": item_id,
            "variant_id": variant_id,
            "quantity": quantity,
            "customizations_type": type(customizations_input).__name__,
            "customizations": customizations_input,
        })

    if not user_id or not business_id:
        return JsonResponse({"error": "user_id and business_id are required in URL params"}, status=400)

    try:
        user_id = int(user_id)
        item_id = int(item_id)
        if variant_id is not None and variant_id != "":
            variant_id = int(variant_id)
        else:
            variant_id = None
    except (ValueError, TypeError) as e:
        return JsonResponse({"error": "Invalid ID format", "details": str(e)}, status=400)

    # 2. Get Business Type
    business_type = CartService.get_business_type(business_id)
    if not business_type:
        return JsonResponse({"error": "Invalid business ID"}, status=400)
    
    # Apply business restrictions
    if business_type in ["R01", "R02", "R08"]:
        # Check if business_id is in restricted list
        restricted_business_ids = []  # Add business IDs here if you want to restrict them to single item
        if business_id in restricted_business_ids:
            # Check if cart is empty for this business
            existing_cart_items = CartService.get_cart_items(business_type, user_id)
            business_cart_items = [item for item in existing_cart_items if item[7] == business_id]
            
            if not business_cart_items:
                # Cart is empty for this business - allow adding
                pass
            else:
                # Cart has items for this business - check if this exact item line already exists
                # Parse customizations for hash calculation
                customizations_obj = parse_json_input(customizations_input, [])
                cust_hash = CartService._customizations_hash(customizations_obj)
                
                # Resolve variant_id if not provided
                if business_type == "R08":
                    resolved_variant_id = variant_id or item_id
                    resolved_item_id = item_id
                else:
                    # For R01/R02, variant_id should be resolved
                    if variant_id is None:
                        details = CartService.get_item_details(business_type, item_id, business_id)
                        if not details:
                            raise ValueError("Item not found")
                        resolved_variant_id = details[0]
                    else:
                        resolved_variant_id = variant_id
                    resolved_item_id = item_id
                
                # Check if exact line exists
                line_exists = False
                with connection.cursor() as cursor:
                    table_name = {
                        "R01": "Groceries_cart",
                        "R02": "menuCart", 
                        "R08": "fashion_cart"
                    }.get(business_type)
                    
                    where_parts = ["user_id=%s", "business_id=%s"]
                    where_vals = [user_id, business_id]
                    
                    if CartService._has_column(table_name, "variant_id"):
                        where_parts.append("variant_id=%s")
                        where_vals.append(resolved_variant_id)
                    else:
                        where_parts.append("product_id=%s" if business_type == "R01" else "menu_id=%s")
                        where_vals.append(resolved_item_id)
                    
                    if CartService._has_column(table_name, "customizations_hash"):
                        where_parts.append("customizations_hash=%s")
                        where_vals.append(cust_hash)
                    
                    cursor.execute(
                        f"SELECT 1 FROM {table_name} WHERE " + " AND ".join(where_parts) + " LIMIT 1",
                        where_vals,
                    )
                    line_exists = cursor.fetchone() is not None
                
                if not line_exists:
                    # Different item - block adding more to this business
                    return JsonResponse({
                        "error": f"Cannot add items to this business. Cart already contains items from {business_id}. Please clear cart first."
                    }, status=400)
                # If line exists, allow the upsert (which will update quantity)
    
    # If we reach here, either no restrictions or line exists - continue with normal flow
    
    # If we reach here, either no restrictions or cart was empty - continue with normal flow
    # Get item details (variant-aware)
    item_details = CartService.get_item_details(business_type, item_id, business_id, variant_id=variant_id)
    if not item_details:
        return JsonResponse({"error": "Item not found or inactive"}, status=404)
    
    try:
        availability_timings = item_details[4]
        if not CartService.check_item_availability(business_type, availability_timings):
            if business_type == "R02":
                return JsonResponse({"error": "Item is not available at this moment"}, status=400)
            elif business_type == "R01":
                return JsonResponse({"error": "This grocery item is not available at this time"}, status=400)
    except Exception as e:
        return JsonResponse({"error": f"Failed to fetch item details: {str(e)}"}, status=500)

    # 4. Parse Customizations
    customizations_obj = parse_json_input(customizations_input, [])

    # 5. Update Cart using Service Layer
    try:
        msg, final_qty = CartService.upsert_cart(
            business_type, user_id, business_id, item_id, quantity, customizations_obj, variant_id=variant_id
        )
    except Exception as e:
        return JsonResponse({"error": f"Failed to update cart: {str(e)}"}, status=500)

    # 6. Build Response (maintaining original format for backward compatibility)
    response_item_id = variant_id if variant_id is not None else item_id

    variant_details = {}
    try:
        if business_type == "R01":
            # item_details: (variant_id, product_name, description, selling_price, stock, is_active, product_id)
            variant_details = {
                "variant_id": item_details[0],
                "product_id": item_details[6],
                "stock": item_details[4],
                "is_active": item_details[5],
            }
        elif business_type == "R02":
            # When variant_id is used: (variant_id, item_name, description, selling_price, availability_timings, stock_qty, is_active, item_id)
            if len(item_details) >= 8:
                variant_details = {
                    "variant_id": item_details[0],
                    "item_id": item_details[7],
                    "stock": item_details[5],
                    "is_active": item_details[6],
                }
        elif business_type == "R08":
            # Fashion is variant-first; keep minimal fields if shape differs
            if len(item_details) >= 5:
                variant_details = {
                    "variant_id": item_details[0],
                    "stock": item_details[4],
                }
    except Exception:
        variant_details = {}

    item_response = {
        "item_id": response_item_id,
        "item_name": item_details[1],
        "description": item_details[2],
        "selling_price": str(item_details[3]),
        "quantity": final_qty,
        "customizations": customizations_obj,
        "variant_details": variant_details,
    }

    # 7. Fetch cart items (original format - business specific)
    try:
        cart_rows = CartService.get_cart_items(business_type, user_id)
        # Filter by business_id and format for legacy response
        if business_type == "R02":
            menu_details = [
                {
                    "cart_id": r[0],
                    "item_id": r[1],
                    "quantity": r[2],
                    "item_name": r[3],
                    "description": r[4],
                    "selling_price": str(r[5]),
                    "customizations": parse_json_input(r[9] if len(r) > 9 else None, [])
                }
                for r in cart_rows if str(r[7]) == business_id  # r[7] is business_id
            ]
            return JsonResponse({"message": msg, "item_details": item_response, "menu_details": menu_details}, status=200)
        
        elif business_type == "R01":
            grocery_details = []
            for r in cart_rows:
                if str(r[7]) == business_id:  # r[7] is business_id
                    # Build image URL using S3
                    image_url = build_s3_file_url(r[6])
                    grocery_details.append({
                        "cart_id": r[0],
                        "item_id": r[1],
                        "quantity": r[2],
                        "item_name": r[3],
                        "description": r[4],
                        "selling_price": str(r[5]),
                        "item_image": image_url,
                        "customizations": parse_json_input(r[9] if len(r) > 9 else None, [])
                    })
            return JsonResponse({"message": msg, "item_details": item_response, "grocery_details": grocery_details}, status=200)
        
        elif business_type == "R08":
            fashion_details = []
            for r in cart_rows:
                if str(r[7]) == business_id:  # r[7] is business_id
                    # Build image URL using S3
                    image_url = build_s3_file_url(r[6])
                    fashion_details.append({
                        "cart_id": r[0],
                        "item_id": r[1],
                        "quantity": r[2],
                        "item_name": r[3],
                        "description": r[4],
                        "selling_price": str(r[5]),
                        "item_image": image_url,
                        "customizations": parse_json_input(r[9] if len(r) > 9 else None, [])
                    })
            return JsonResponse({"message": msg, "item_details": item_response, "fashion_details": fashion_details}, status=200)
            
    except Exception as e:
        return JsonResponse({
            "message": msg,
            "item_details": item_response,
            "error": f"Failed to fetch cart items: {str(e)}"
        }, status=500)

    return JsonResponse({"error": "Unsupported business type for cart operation"}, status=400)

#Get Cart Items
@csrf_exempt
def get_cart_items(request):
    """
    View cart items using optimized service layer.
    Supports filtering by business type or returns all items.
    Includes detailed variant metadata (SKU, size, color, stock, MRP) for each item.
    """
    from .cart_services import CartService
    from .utils import parse_json_input
    from consumer.image_utils import build_s3_file_url
    from django.db import connection
    
    if request.method != "POST":
        return JsonResponse({"message": "Invalid request method. Use POST"}, status=405)

    user_id = request.GET.get("user_id")
    cart_type = request.GET.get("type")  # Optional: R01 / R02 / R08

    if not user_id:
        return JsonResponse({"message": "user_id parameter is required"}, status=400)

    try:
        user_id = int(user_id)
    except (ValueError, TypeError):
        return JsonResponse({"message": "Invalid user_id format"}, status=400)

    # 1. Fetch Cart Rows across all requested types
    cart_rows = []
    types_to_fetch = [cart_type] if cart_type in ["R01", "R02", "R08"] else ["R01", "R02", "R08"]
    
    try:
        for b_type in types_to_fetch:
            rows = CartService.get_cart_items(b_type, user_id)
            # Add business type to each row for later processing (as last element)
            cart_rows.extend([list(r) + [b_type] for r in rows])
    except Exception as e:
        return JsonResponse({"error": f"Failed to fetch cart items: {str(e)}"}, status=500)

    if not cart_rows:
        return JsonResponse({"message": "Cart is Empty please add the items in the cart"}, status=200)

    # 2. Extract Variant IDs for Bulk Metadata Fetching
    variant_ids_map = {"R01": [], "R02": [], "R08": []}
    for r in cart_rows:
        v_id = r[10] if len(r) > 10 and r[10] is not None else None  # variant_id index
        b_type = r[12] if len(r) > 12 else r[11]  # The type we added above (could be index 11 or 12)
        if v_id and b_type in variant_ids_map:
            variant_ids_map[b_type].append(v_id)

    # 3. Bulk Fetch Variant Metadata
    variant_metadata = {}
    with connection.cursor() as cursor:
        # R01: Groceries
        if variant_ids_map["R01"]:
            v_ids = variant_ids_map["R01"]
            placeholders = ','.join(['%s'] * len(v_ids))
            cursor.execute(f"""
                SELECT variant_id, sku, net_weight, net_weight_unit, size, stock, original_cost, color 
                FROM Groceries_ProductVariants_1 WHERE variant_id IN ({placeholders})
            """, v_ids)
            for v in cursor.fetchall():
                variant_metadata[f"R01_{v[0]}"] = {
                    "sku": v[1], 
                    "weight": f"{v[2]} {v[3]}" if v[2] else None,
                    "size": parse_json_input(v[4], v[4]), 
                    "stock": v[5], 
                    "mrp": str(v[6]) if v[6] else None, 
                    "color": v[7]
                }
        
        # R02: Restaurants
        if variant_ids_map["R02"]:
            v_ids = variant_ids_map["R02"]
            placeholders = ','.join(['%s'] * len(v_ids))
            cursor.execute(f"""
                SELECT variant_id, size_label, sku, stock_qty, mrp, original_cost 
                FROM menu_item_variants WHERE variant_id IN ({placeholders})
            """, v_ids)
            for v in cursor.fetchall():
                mrp_val = v[4] if v[4] is not None else v[5]
                variant_metadata[f"R02_{v[0]}"] = {
                    "size_label": v[1], 
                    "sku": v[2], 
                    "stock": v[3], 
                    "mrp": str(mrp_val) if mrp_val else None
                }

        # R08: Fashion
        if variant_ids_map["R08"]:
            v_ids = variant_ids_map["R08"]
            placeholders = ','.join(['%s'] * len(v_ids))
            cursor.execute(f"""
                SELECT variant_id, sku, size, color, material, stock_qty, mrp 
                FROM fashion_product_variants WHERE variant_id IN ({placeholders})
            """, v_ids)
            for v in cursor.fetchall():
                variant_metadata[f"R08_{v[0]}"] = {
                    "sku": v[1], 
                    "size": v[2], 
                    "color": v[3], 
                    "material": v[4], 
                    "stock": v[5], 
                    "mrp": str(v[6]) if v[6] else None
                }

    # 4. Fetch all business logos in one query
    from django.conf import settings
    from kirazee_app.models import Business
    
    business_ids = list(set(row[7] for row in cart_rows))
    business_logos = {}
    if business_ids:
        businesses = Business.objects.filter(business_id__in=business_ids).only('business_id', 'logo')
        for business in businesses:
            if business.logo:
                business_logos[str(business.business_id)] = build_s3_file_url(business.logo)

    # 5. Group Items by Business and Attach Metadata
    business_items = {}
    for row in cart_rows:
        business_id = str(row[7])
        item_image = row[6]
        business_name = row[8]
        b_type = row[12] if len(row) > 12 else (row[11] if len(row) > 11 else None)
        v_id = row[10] if len(row) > 10 and row[10] is not None else None
        
        if business_id not in business_items:
            business_items[business_id] = {
                'business_id': business_id,
                'business_name': business_name,
                'logo_url': business_logos.get(business_id, ''),
                'items': []
            }
        
        # Build the image URL using S3
        image_url = build_s3_file_url(item_image)
        
        # Parse customizations safely
        customizations_data = row[9] if len(row) > 9 else None
        customizations = parse_json_input(customizations_data, [])

        # Get variant_id (fallback to item_id if not present)
        variant_id = None
        if v_id is not None:
            try:
                variant_id = int(v_id)
            except (ValueError, TypeError):
                variant_id = None
        
        if variant_id is None:
            variant_id = int(row[1])
        
        # Get specific variant details
        v_details = variant_metadata.get(f"{b_type}_{variant_id}", {}) if b_type else {}

        item_data = {
            'cart_id': row[0],
            'item_id': int(row[1]),
            'variant_id': variant_id,
            'quantity': row[2],
            'item_name': row[3] or "",
            'description': row[4] or "",
            'selling_price': str(row[5] or 0),
            'image_url': image_url,
            'customizations': customizations,
            'variant_details': v_details  # Contains detailed metadata
        }
        
        business_items[business_id]['items'].append(item_data)

    return JsonResponse({
        "cart_details": list(business_items.values())
    }, status=200, safe=False)

@csrf_exempt
@swagger_auto_schema(methods=['POST', 'DELETE'], tags=['Consumer'])
@api_view(['POST', 'DELETE'])
def update_cart_quantity(request):
    """
    Update quantity of cart items or delete items using optimized service layer.
    
    POST /update-cart-quantity?id={cart_id}&type=R01&action=inc/dec
    DELETE /update-cart-quantity?user_id=123&item_id=456&type=R01
    DELETE /update-cart-quantity?user_id=123  # Deletes entire cart
    """
    from .cart_services import CartService
    
    if request.method == 'DELETE':
        # Handle DELETE request
        user_id = request.GET.get("user_id")
        item_id = request.GET.get("cart_id")
        cart_type = request.GET.get("type")  # R01 -> groceries, R02 -> menu, R08 -> fashion
        
        if not user_id:
            return JsonResponse({"message": "user_id is required"}, status=400)
            
        try:
            user_id = int(user_id)
        except (ValueError, TypeError):
            return JsonResponse({"message": "Invalid user_id format"}, status=400)
            
        try:
            if item_id and cart_type:
                # Delete specific item using service layer
                if cart_type in ["R01", "R02", "R08"]:
                    deleted = CartService.delete_cart_item(cart_type, item_id, user_id)
                    if deleted > 0:
                        return JsonResponse({"message": "Item removed from cart"}, status=200)
                    else:
                        return JsonResponse({"message": "Item not found in your cart"}, status=404)
                else:
                    return JsonResponse({"message": "Invalid type. Use R01, R02, or R08"}, status=400)
            else:
                # Delete entire cart for user across all business types
                total_deleted = 0
                for business_type in ["R01", "R02", "R08"]:
                    deleted = CartService.delete_user_cart(business_type, user_id)
                    total_deleted += deleted
                
                if total_deleted > 0:
                    return JsonResponse({"message": f"Removed {total_deleted} items from cart"}, status=200)
                else:
                    return JsonResponse({"message": "Your cart is already empty"}, status=200)
                    
        except Exception as e:
            return JsonResponse({"message": f"Error processing request: {str(e)}"}, status=500)
    
    # Handle POST request (existing functionality)
    # Legacy mode: query params for R01/R02/R08
    cart_id = request.GET.get("id")
    cart_type = request.GET.get("type")  # R01 -> groceries, R02 -> menu, R08 -> fashion
    action = request.GET.get("action")   # "inc" or "dec"

    if cart_id and cart_type and action:
        # Legacy mode - handle query params
        try:
            cart_id = int(cart_id)
        except (ValueError, TypeError):
            return JsonResponse({"message": "Invalid cart_id format"}, status=400)

        try:
            if cart_type not in ["R01", "R02", "R08"]:
                return JsonResponse({"message": "Invalid type. Use R01, R02, or R08"}, status=400)

            # For legacy mode, user_id may or may not be present. If missing, infer it from cart_id.
            user_id = request.GET.get("user_id")
            if user_id:
                try:
                    user_id = int(user_id)
                except (ValueError, TypeError):
                    return JsonResponse({"message": "Invalid user_id format"}, status=400)
                cart_line = CartService.get_cart_line_by_id(cart_type, cart_id, user_id)
                if not cart_line:
                    return JsonResponse({"message": "Cart item not found"}, status=404)
                current_qty = int(cart_line[3])
            else:
                # Backward compatible fallback: lookup user_id + current quantity from DB using cart_id.
                table_map = {
                    "R01": "Groceries_cart",
                    "R02": "menuCart",
                    "R08": "fashion_cart",
                }
                table_name = table_map.get(cart_type)
                if not table_name:
                    return JsonResponse({"message": "Invalid type. Use R01, R02, or R08"}, status=400)

                with connection.cursor() as cursor:
                    cursor.execute(
                        f"SELECT user_id, quantity FROM {table_name} WHERE id=%s",
                        [cart_id],
                    )
                    row = cursor.fetchone()

                if not row:
                    return JsonResponse({"message": "Cart item not found"}, status=404)

                user_id = int(row[0])
                current_qty = int(row[1])
            if action == "inc":
                new_qty = current_qty + 1
                msg, qty = CartService.set_cart_line_quantity(cart_type, cart_id, user_id, new_qty)
                if qty is None:
                    return JsonResponse({"message": msg}, status=404)
                return JsonResponse({"message": "Quantity increased", "quantity": qty}, status=200)

            if action == "dec":
                new_qty = current_qty - 1
                msg, qty = CartService.set_cart_line_quantity(cart_type, cart_id, user_id, new_qty)
                if qty is None:
                    return JsonResponse({"message": msg}, status=404)
                if qty == 0:
                    return JsonResponse({"message": "Item removed from cart"}, status=200)
                return JsonResponse({"message": "Quantity decreased", "quantity": qty}, status=200)

            return JsonResponse({"message": "Invalid action. Use inc or dec"}, status=400)
        except Exception as e:
            return JsonResponse({"message": f"Error processing request: {str(e)}"}, status=500)
    
    # New mode: JSON payload with item_id and quantity (useful for R08)
    if request.content_type == 'application/json':
        data = request.data
        item_id = data.get('item_id')
        quantity = data.get('quantity')
        cart_type = data.get('type')  # Required for R08
        user_id_from_body = data.get('user_id')
        user_id = user_id_from_body or request.GET.get('user_id')

        if not all([item_id is not None, quantity is not None, cart_type, user_id]):
            return JsonResponse({"message": "item_id, quantity, type, and user_id are required in JSON payload"}, status=400)

        try:
            user_id = int(user_id)
            quantity = int(quantity)
        except (ValueError, TypeError):
            return JsonResponse({"message": "user_id and quantity must be integers"}, status=400)

        if cart_type == "R08":
            # Update fashion_cart directly using service layer
            try:
                # Get business_id from the cart item first
                cart_items = CartService.get_cart_items("R08", user_id)
                business_id = None
                for item in cart_items:
                    if item[1] == item_id:  # variant_id matches
                        business_id = item[7]
                        break
                
                if not business_id:
                    return JsonResponse({"message": "Fashion item not found in cart"}, status=404)
                
                if quantity > 0:
                    msg, qty = CartService.upsert_cart("R08", user_id, business_id, item_id, quantity, [])
                    return JsonResponse({"message": "Quantity updated", "quantity": qty}, status=200)
                else:
                    deleted = CartService.delete_cart_item("R08", item_id, user_id)
                    if deleted > 0:
                        return JsonResponse({"message": "Item removed from cart"}, status=200)
                    else:
                        return JsonResponse({"message": "Fashion item not found in cart"}, status=404)
            except Exception as e:
                return JsonResponse({"message": f"Error updating fashion item: {str(e)}"}, status=500)
        else:
            return JsonResponse({"message": "JSON payload mode currently supports R08 only"}, status=400)

    # If we reach here, it's an invalid request
    return JsonResponse({"message": "Invalid request. Use either legacy query params (id, type, action) or JSON payload (item_id, quantity, type, user_id)"}, status=400)

