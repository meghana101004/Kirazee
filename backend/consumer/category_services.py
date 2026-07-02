from django.db import connection
from datetime import date, datetime
from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework import status
from django.conf import settings
from drf_yasg.utils import swagger_auto_schema
from .serializers import MenuItemsSerializer, productItemsSerializer
from kirazee_app.models import Business
from business.models import MenuItems, productItems
from .availability_services import (
    get_item_availability_status,
    get_business_availability,
    get_stock_message
)
from .combine import (
    get_availability_context,
    calculate_variant_availability,
    _build_media_response
)
from consumer.image_utils import build_s3_file_url


def _parse_int(value, default=None):
    try:
        return int(value)
    except Exception:
        return default


def _dt_to_iso(value):
    if value is None:
        return None
    if isinstance(value, datetime):
        try:
            return value.isoformat()
        except Exception:
            return str(value)
    if isinstance(value, date):
        try:
            return value.isoformat()
        except Exception:
            return str(value)
    return str(value)


from django.core.files.storage import default_storage

def _get_category_image_with_fallback(request, category_id, business_id, business_type, include_business_ids):
    """
    Get category image with fallback logic:
    1. Use category image from universal_Categories if available and valid
    2. Fallback to first item image in the category
    3. Return None if no image found (no default image fallback)
    """
    
    with connection.cursor() as cursor:
        # First try to get category image from universal_Categories
        cursor.execute("""
            SELECT uc.category_image
            FROM universal_Categories uc
            WHERE uc.category_id = %s
        """, [category_id])
        result = cursor.fetchone()
        
        if result and result[0]:
            print(f"DEBUG: Raw category_image from DB: {result[0]}")
            category_image = _abs_item_image(request, result[0])
            print(f"DEBUG: Processed category_image: {category_image}")
            if category_image:
                return category_image
        
        # Fallback to first item image in the category
        if business_type == 'R02':  # Restaurant
            biz_placeholders = ','.join(['%s'] * len(include_business_ids))
            cursor.execute(f"""
                SELECT mi.item_image
                FROM menuItems mi
                WHERE mi.business_id IN ({biz_placeholders})
                AND mi.item_category_id = %s
                AND mi.item_image IS NOT NULL
                AND mi.item_image != ''
                ORDER BY mi.item_id ASC
                LIMIT 1
            """, include_business_ids + [category_id])
            result = cursor.fetchone()
            
            if result and result[0]:
                print(f"DEBUG: Raw item_image from DB (R02): {result[0]}")
                item_image = _abs_item_image(request, result[0])
                print(f"DEBUG: Processed item_image (R02): {item_image}")
                if item_image:
                    return item_image
            
        elif business_type == 'R01':  # Grocery
            biz_placeholders = ','.join(['%s'] * len(include_business_ids))
            cursor.execute(f"""
                SELECT gp.main_image
                FROM Groceries_Products gp
                WHERE gp.business_id IN ({biz_placeholders})
                AND gp.category_id = %s
                AND gp.main_image IS NOT NULL
                AND gp.main_image != ''
                ORDER BY gp.product_id ASC
                LIMIT 1
            """, include_business_ids + [category_id])
            
        elif business_type == 'R08':  # Fashion
            biz_placeholders = ','.join(['%s'] * len(include_business_ids))
            cursor.execute(f"""
                SELECT fp.primary_image
                FROM fashion_products fp
                WHERE fp.business_id IN ({biz_placeholders})
                AND fp.category_id = %s
                AND fp.primary_image IS NOT NULL
                AND fp.primary_image != ''
                ORDER BY fp.product_id ASC
                LIMIT 1
            """, include_business_ids + [category_id])
        
        item_result = cursor.fetchone()
        if item_result and item_result[0]:
            item_image = _abs_item_image(request, item_result[0])
            if item_image:
                return item_image
        
        # No image found - return None instead of default image
        return None


def _get_category_item_count(category_id, business_type, include_business_ids):
    """
    Get the count of items in a category (including subcategories for parent categories)
    """
    with connection.cursor() as cursor:
        if business_type == 'R02':  # Restaurant
            biz_placeholders = ','.join(['%s'] * len(include_business_ids))
            
            # Get direct items for this category
            cursor.execute(f"""
                SELECT COUNT(DISTINCT mi.item_id)
                FROM menuItems mi
                WHERE mi.business_id IN ({biz_placeholders})
                AND mi.item_category_id = %s
                AND mi.is_active = 1
            """, include_business_ids + [category_id])
            direct_count = cursor.fetchone()[0] or 0
            
            # Get items from subcategories (for parent categories)
            cursor.execute(f"""
                SELECT COUNT(DISTINCT mi.item_id)
                FROM menuItems mi
                WHERE mi.business_id IN ({biz_placeholders})
                AND mi.sub_category_id = %s
                AND mi.is_active = 1
            """, include_business_ids + [category_id])
            subcategory_count = cursor.fetchone()[0] or 0
            
            total_count = direct_count + subcategory_count
            
            # Debug: Let's also get some sample items for this category
            if category_id in [46, 23, 501]:  # Debug specific categories
                cursor.execute(f"""
                    SELECT mi.item_id, mi.item_name, mi.item_category_id
                    FROM menuItems mi
                    WHERE mi.business_id IN ({biz_placeholders})
                    AND mi.item_category_id = %s
                    AND mi.is_active = 1
                    LIMIT 3
                """, include_business_ids + [category_id])
                sample_items = cursor.fetchall()
                print(f"DEBUG: Category {category_id} has {total_count} items (direct: {direct_count}, subcat: {subcategory_count}), samples: {sample_items}")
            
            return total_count
            
        elif business_type == 'R01':  # Grocery
            biz_placeholders = ','.join(['%s'] * len(include_business_ids))
            
            # Get direct items for this category
            cursor.execute(f"""
                SELECT COUNT(DISTINCT gp.product_id)
                FROM Groceries_Products gp
                WHERE gp.business_id IN ({biz_placeholders})
                AND gp.category_id = %s
                AND gp.is_visible = 1
            """, include_business_ids + [category_id])
            direct_count = cursor.fetchone()[0] or 0
            
            # Get items from subcategories (for parent categories)
            cursor.execute(f"""
                SELECT COUNT(DISTINCT gp.product_id)
                FROM Groceries_Products gp
                WHERE gp.business_id IN ({biz_placeholders})
                AND gp.sub_category_id = %s
                AND gp.is_visible = 1
            """, include_business_ids + [category_id])
            subcategory_count = cursor.fetchone()[0] or 0
            
            total_count = direct_count + subcategory_count
            
            return total_count
            
        elif business_type == 'R08':  # Fashion
            biz_placeholders = ','.join(['%s'] * len(include_business_ids))
            
            # Get direct items for this category
            cursor.execute(f"""
                SELECT COUNT(DISTINCT fp.product_id)
                FROM fashion_products fp
                WHERE fp.business_id IN ({biz_placeholders})
                AND fp.category_id = %s
                AND fp.is_active = 1
            """, include_business_ids + [category_id])
            direct_count = cursor.fetchone()[0] or 0
            
            # Get items from subcategories (for parent categories)
            cursor.execute(f"""
                SELECT COUNT(DISTINCT fp.product_id)
                FROM fashion_products fp
                WHERE fp.business_id IN ({biz_placeholders})
                AND fp.sub_category_id = %s
                AND fp.is_active = 1
            """, include_business_ids + [category_id])
            subcategory_count = cursor.fetchone()[0] or 0
            
            total_count = direct_count + subcategory_count
            
            return total_count
        
        return 0


def _get_category_total_count_with_children(category_id, business_type, include_business_ids):
    """
    Get the count of items in a category including all child categories
    """
    with connection.cursor() as cursor:
        if business_type == 'R02':  # Restaurant
            biz_placeholders = ','.join(['%s'] * len(include_business_ids))
            
            # Get items from this category and all child categories
            cursor.execute(f"""
                SELECT COUNT(DISTINCT mi.item_id)
                FROM menuItems mi
                WHERE mi.business_id IN ({biz_placeholders})
                AND (
                    mi.item_category_id = %s
                    OR mi.item_category_id IN (
                        WITH RECURSIVE category_tree AS (
                            SELECT category_id FROM universal_Categories WHERE parent_category_id = %s
                            UNION ALL
                            SELECT uc.category_id 
                            FROM universal_Categories uc
                            INNER JOIN category_tree ct ON uc.parent_category_id = ct.category_id
                        )
                        SELECT category_id FROM category_tree
                    )
                )
                AND mi.is_active = 1
            """, include_business_ids + [category_id, category_id])
            total_count = cursor.fetchone()[0] or 0
            
            return total_count
            
        elif business_type == 'R01':  # Grocery
            biz_placeholders = ','.join(['%s'] * len(include_business_ids))
            
            # Get items from this category and all child categories
            cursor.execute(f"""
                SELECT COUNT(DISTINCT gp.product_id)
                FROM Groceries_Products gp
                WHERE gp.business_id IN ({biz_placeholders})
                AND (
                    gp.category_id = %s
                    OR gp.category_id IN (
                        WITH RECURSIVE category_tree AS (
                            SELECT category_id FROM universal_Categories WHERE parent_category_id = %s
                            UNION ALL
                            SELECT uc.category_id 
                            FROM universal_Categories uc
                            INNER JOIN category_tree ct ON uc.parent_category_id = ct.category_id
                        )
                        SELECT category_id FROM category_tree
                    )
                )
                AND gp.is_visible = 1
            """, include_business_ids + [category_id, category_id])
            total_count = cursor.fetchone()[0] or 0
            
            return total_count
            
        elif business_type == 'R08':  # Fashion
            biz_placeholders = ','.join(['%s'] * len(include_business_ids))
            
            # Get items from this category and all child categories
            cursor.execute(f"""
                SELECT COUNT(DISTINCT fp.product_id)
                FROM fashion_products fp
                WHERE fp.business_id IN ({biz_placeholders})
                AND (
                    fp.category_id = %s
                    OR fp.category_id IN (
                        WITH RECURSIVE category_tree AS (
                            SELECT category_id FROM universal_Categories WHERE parent_category_id = %s
                            UNION ALL
                            SELECT uc.category_id 
                            FROM universal_Categories uc
                            INNER JOIN category_tree ct ON uc.parent_category_id = ct.category_id
                        )
                        SELECT category_id FROM category_tree
                    )
                )
                AND fp.is_active = 1
            """, include_business_ids + [category_id, category_id])
            total_count = cursor.fetchone()[0] or 0
            
            return total_count
        
        return 0


def _distribute_items_to_children(parent_category_id, child_categories, business_type, include_business_ids):
    """
    Distribute items from parent category to children based on sub_category_id
    """
    with connection.cursor() as cursor:
        if business_type == 'R02':  # Restaurant
            biz_placeholders = ','.join(['%s'] * len(include_business_ids))
            
            # Get all items from parent category with their sub_category_id
            cursor.execute(f"""
                SELECT mi.item_id, mi.item_name, mi.item_category_id, mi.sub_category_id, mi.business_id
                FROM menuItems mi
                WHERE mi.business_id IN ({biz_placeholders})
                AND mi.item_category_id = %s
                AND mi.is_active = 1
            """, include_business_ids + [parent_category_id])
            parent_items = cursor.fetchall()
            
            print(f"DEBUG: Parent {parent_category_id} has {len(parent_items)} total items from businesses {include_business_ids}")
            
            # Debug: Count items by sub_category_id
            sub_cat_counts = {}
            for item_id, item_name, item_category_id, sub_category_id, business_id in parent_items:
                if sub_category_id not in sub_cat_counts:
                    sub_cat_counts[sub_category_id] = 0
                sub_cat_counts[sub_category_id] += 1
            print(f"DEBUG: Items by sub_category_id: {sub_cat_counts}")
            
            # Debug: Compare with direct query
            cursor.execute(f"""
                SELECT COUNT(*) 
                FROM menuItems mi
                WHERE mi.business_id IN ({biz_placeholders})
                AND mi.item_category_id = %s
                AND mi.sub_category_id = %s
                AND mi.is_active = 1
            """, include_business_ids + [parent_category_id, 46])
            direct_count = cursor.fetchone()[0]
            print(f"DEBUG: Direct count for sub_category_id 46: {direct_count}")
            
            # Debug: Check specific business
            cursor.execute("""
                SELECT COUNT(*) 
                FROM menuItems mi
                WHERE mi.business_id = %s
                AND mi.item_category_id = %s
                AND mi.sub_category_id = %s
                AND mi.is_active = 1
            """, ['KIR1478820251021185505', parent_category_id, 46])
            specific_count = cursor.fetchone()[0]
            print(f"DEBUG: Specific business count for sub_category_id 46: {specific_count}")
            
            # Create child category mapping based on sub_category_id
            child_mapping = {}
            for child_id, child_name in child_categories:
                child_mapping[child_id] = []
                
                # Assign items to child based on sub_category_id
                for item_id, item_name, item_category_id, sub_category_id, business_id in parent_items:
                    if sub_category_id == child_id:
                        child_mapping[child_id].append(item_id)
            
            print(f"DEBUG: Child mapping: {[(k, len(v)) for k, v in child_mapping.items()]}")
            
            return child_mapping
            
        elif business_type == 'R01':  # Grocery
            biz_placeholders = ','.join(['%s'] * len(include_business_ids))
            
            # Get all items from parent category with their sub_category_id
            cursor.execute(f"""
                SELECT gp.product_id, gp.product_name, gp.category_id, gp.sub_category_id, gp.business_id
                FROM Groceries_Products gp
                WHERE gp.business_id IN ({biz_placeholders})
                AND gp.category_id = %s
                AND gp.is_visible = 1
            """, include_business_ids + [parent_category_id])
            parent_items = cursor.fetchall()
            
            print(f"DEBUG: R01 Parent {parent_category_id} has {len(parent_items)} total items from businesses {include_business_ids}")
            
            # Debug: Count items by sub_category_id
            sub_cat_counts = {}
            for product_id, product_name, category_id, sub_category_id, business_id in parent_items:
                if sub_category_id not in sub_cat_counts:
                    sub_cat_counts[sub_category_id] = 0
                sub_cat_counts[sub_category_id] += 1
            print(f"DEBUG: R01 Items by sub_category_id: {sub_cat_counts}")
            
            # Create child category mapping based on sub_category_id
            child_mapping = {}
            for child_id, child_name in child_categories:
                child_mapping[child_id] = []
                
                # Assign items to child based on sub_category_id
                for product_id, product_name, category_id, sub_category_id, business_id in parent_items:
                    if sub_category_id == child_id:
                        child_mapping[child_id].append(product_id)
            
            print(f"DEBUG: R01 Child mapping: {[(k, len(v)) for k, v in child_mapping.items()]}")
            
            return child_mapping
            
        return {}


def _distribute_parent_items_to_children(category_node, business_type, include_business_ids):
    """
    Distribute items from parent category to children based on sub_category_id
    Updates child counts but keeps parent count as total including direct items
    """
    if not category_node or not category_node.get('children'):
        return
    
    children = category_node.get('children', [])
    if not children:
        return
    
    # Get child categories info
    child_categories = [(child['category_id'], child['category_name']) for child in children]
    
    # Get distributed items mapping
    parent_category_id = category_node['category_id']
    child_mapping = _distribute_items_to_children(parent_category_id, child_categories, business_type, include_business_ids)
    
    # Update child counts based on distributed items
    for child in children:
        child_id = child['category_id']
        distributed_items = child_mapping.get(child_id, [])
        child['item_count'] = len(distributed_items)
        
        print(f"DEBUG: Distributed {len(distributed_items)} items to child {child_id} ({child['category_name']})")
    
    # Parent category keeps its original count (includes direct items + items distributed to children)
    # We don't modify the parent count here - it should show the total


def _update_category_count_with_children(category_node, business_type, include_business_ids):
    """
    Recursively update parent category counts to include children counts
    """
    if not category_node:
        return
    
    # Start with direct count (this should be the total for parent categories)
    total_count = category_node.get('item_count', 0)
    
    # For parent categories with children, the item_count should already be the total
    # We don't need to add children counts since they're already distributed from parent
    children = category_node.get('children', [])
    if children:
        # Only update children recursively, don't modify parent count
        for child in children:
            _update_category_count_with_children(child, business_type, include_business_ids)
    else:
        # For leaf categories, keep their direct count
        pass


def _abs_item_image(request, raw_path):
    """Build S3 URL for item image path."""
    return build_s3_file_url(raw_path)


def _process_sub_images_list(request, sub_images):
    """Process sub_images JSON field and return array of absolute URLs"""
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
            urls.append(_abs_item_image(request, img_path))
    
    return urls


def _resolve_scope(request, business_id, business_type):
    include_business_ids = None
    display_name = None
    resolved_type = business_type

    if business_id:
        business = Business.objects.filter(business_id=business_id).first()
        if not business:
            return None, None, None, Response({"error": f"Business with ID {business_id} not found"}, status=status.HTTP_404_NOT_FOUND)

        resolved_type = business.businessType
        display_name = business.businessName
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT b.business_id
                FROM businesses b
                WHERE b.master = %s
                """,
                [business_id]
            )
            sub_rows = cursor.fetchall()
        include_business_ids = [business_id] + [r[0] for r in sub_rows if r and r[0]]
        return resolved_type, display_name, include_business_ids, None

    if not resolved_type:
        return None, None, None, Response({"error": "business_type (or type) is required when business_id is not provided"}, status=status.HTTP_400_BAD_REQUEST)

    # When business_id is not provided, show items from all businesses of this type
    business_type_names = {
        'R01': 'Grocery',
        'R02': 'Restaurant', 
        'R08': 'Fashion'
    }
    type_display = business_type_names.get(resolved_type, resolved_type)
    display_name = f"All {type_display} Businesses"
    return resolved_type, display_name, None, None


def standardize_category_name(category):
    """
    Standardize category names by:
    1. Trimming whitespace
    2. Converting to Title Case
    3. Handling special cases
    """
    if not category:
        return category
    
    # Trim whitespace and convert to title case
    standardized = category.strip().title()
    print(f"DEBUG - Standardizing '{category}' -> '{standardized}'")
    
    # Handle special cases and corrections
    category_mappings = {
        'Fast Food': 'Fast Food',
        'Fastfood': 'Fast Food',
        'Non/Veg': 'Non-Veg',
        'Non/veg': 'Non-Veg',
        'Nonveg': 'Non-Veg',
        'Veg': 'Veg',
        'Vegetarian': 'Veg',
        'Non-Vegetarian': 'Non-Veg',
        'Bakers': 'Bakery',
        'Baker': 'Bakery',
        'Bakeries': 'Bakery',
        'Sweets': 'Sweets',
        'Sweet': 'Sweets',
        'Desserts': 'Sweets',
        'Dessert': 'Sweets'
    }
    
    result = category_mappings.get(standardized, standardized)
    print(f"DEBUG - Final result: '{result}'")
    return result


@swagger_auto_schema(methods=['GET', 'POST'],tags=['Consumer'])
@api_view(['GET', 'POST'])
def fetch_categories(request):
    """
    Fetch unique categories for a specific business based on business type
    URL: POST /consumer/fetch-categories?business_id=[value]
    
    1. Check whether it is R01 or R02
    2. If it is R02 then check the menu Items, if it is R01 then check the GroceryItems tables
    3. Fetch the items categories and display list of categories (avoid duplicates) of that only business
    """
    business_id = request.query_params.get('business_id')
    
    if not business_id:
        return Response({
            "error": "business_id is required as query parameter"
        }, status=status.HTTP_400_BAD_REQUEST)
    
    try:
        # Get business details (include closed businesses)
        business = Business.objects.get(business_id=business_id)
        business_type = business.businessType
        
        categories = []
        categories_details = []
        total_categories = 0
        
        if business_type == 'R02':  # Restaurant
            # For R02, fetch categories (and their hierarchy) from category_mapping like R01.
            # Sub-categories list is derived from menuItems.sub_category_id.
            with connection.cursor() as cursor:
                cursor.execute("""
                    SELECT DISTINCT uc.category_id, TRIM(uc.category_name) as category_name, uc.parent_category_id, uc.category_image
                    FROM category_mapping cm
                    JOIN universal_Categories uc ON cm.category_id = uc.category_id
                    WHERE cm.business_id = %s
                    AND cm.is_active = 1
                    AND uc.category_name IS NOT NULL
                    AND TRIM(uc.category_name) != ''
                """, [business_id])
                parent_rows = cursor.fetchall()

                cursor.execute("""
                    SELECT DISTINCT uc.category_id, TRIM(uc.category_name) as category_name, uc.parent_category_id, uc.category_image
                    FROM category_mapping cm
                    JOIN universal_Categories uc ON cm.category_id = uc.category_id
                    JOIN businesses b ON cm.business_id = b.business_id
                    WHERE b.master = %s
                    AND cm.is_active = 1
                    AND uc.category_name IS NOT NULL
                    AND TRIM(uc.category_name) != ''
                """, [business_id])
                sub_rows = cursor.fetchall()

                all_rows = parent_rows + sub_rows

                # Get include_business_ids for image and count queries
                cursor.execute("""
                    SELECT b.business_id
                    FROM businesses b
                    WHERE b.master = %s
                """, [business_id])
                sub_biz_rows = cursor.fetchall()
                include_business_ids = [business_id] + [r[0] for r in sub_biz_rows if r and r[0]]

                # Debug: Check what categories actually have items
                biz_placeholders = ','.join(['%s'] * len(include_business_ids))
                cursor.execute(f"""
                    SELECT mi.item_category_id, COUNT(*) as item_count
                    FROM menuItems mi
                    WHERE mi.business_id IN ({biz_placeholders})
                    AND mi.is_active = 1
                    AND mi.item_category_id IN (46, 23, 501)
                    GROUP BY mi.item_category_id
                    ORDER BY mi.item_category_id
                """, include_business_ids)
                category_counts = cursor.fetchall()
                print(f"DEBUG: Category item counts: {category_counts}")

                by_id = {}
                mapped_category_ids = set()
                for row in all_rows:
                    if not row or row[0] is None:
                        continue
                    category_id = int(row[0])
                    category_name = row[1]
                    parent_category_id = row[2] if len(row) > 2 else None
                    category_image = row[3] if len(row) > 3 else None
                    if not category_name:
                        continue
                    mapped_category_ids.add(category_id)
                    
                    # Get item count for this category (direct items only)
                    item_count = _get_category_item_count(category_id, business_type, include_business_ids)
                    
                    # Get category image with fallback logic
                    final_category_image = _get_category_image_with_fallback(request, category_id, business_id, business_type, include_business_ids)
                    
                    by_id[category_id] = {
                        "category_id": category_id,
                        "category_name": category_name.strip(),
                        "parent_category_id": parent_category_id,
                        "category_image": final_category_image,
                        "item_count": item_count,
                        "sub_categories": []
                    }

                missing_parent_ids = set()
                for entry in by_id.values():
                    pid = entry.get('parent_category_id')
                    if pid in (None, ''):
                        continue
                    try:
                        pid_int = int(pid)
                    except Exception:
                        continue
                    if pid_int not in by_id:
                        missing_parent_ids.add(pid_int)

                while missing_parent_ids:
                    placeholders = ','.join(['%s'] * len(missing_parent_ids))
                    cursor.execute(f"""
                        SELECT uc.category_id, TRIM(uc.category_name) as category_name, uc.parent_category_id, uc.category_image
                        FROM universal_Categories uc
                        WHERE uc.category_id IN ({placeholders})
                        AND uc.category_name IS NOT NULL
                        AND TRIM(uc.category_name) != ''
                    """, list(missing_parent_ids))
                    p_rows = cursor.fetchall()
                    if not p_rows:
                        break

                    for row in p_rows:
                        if not row or row[0] is None:
                            continue
                        cid = int(row[0])
                        cname = row[1]
                        cpid = row[2] if len(row) > 2 else None
                        cimage = row[3] if len(row) > 3 else None
                        if not cname:
                            continue
                        if cid not in by_id:
                            # Get item count for this missing parent category
                            item_count = _get_category_item_count(cid, business_type, include_business_ids)
                            
                            # Get category image with fallback logic
                            final_category_image = _get_category_image_with_fallback(request, cid, business_id, business_type, include_business_ids)
                            
                            by_id[cid] = {
                                "category_id": cid,
                                "category_name": cname.strip(),
                                "parent_category_id": cpid,
                                "category_image": final_category_image,
                                "item_count": item_count,
                                "sub_categories": []
                            }

                    next_missing = set()
                    for entry in by_id.values():
                        pid = entry.get('parent_category_id')
                        if pid in (None, ''):
                            continue
                        try:
                            pid_int = int(pid)
                        except Exception:
                            continue
                        if pid_int not in by_id:
                            next_missing.add(pid_int)
                    missing_parent_ids = next_missing

                # Attach sub-categories by looking at menuItems.sub_category_id
                if by_id and mapped_category_ids:
                    cursor.execute("""
                        SELECT b.business_id
                        FROM businesses b
                        WHERE b.master = %s
                    """, [business_id])
                    sub_biz_rows = cursor.fetchall()
                    include_business_ids = [business_id] + [r[0] for r in sub_biz_rows if r and r[0]]

                    biz_placeholders = ','.join(['%s'] * len(include_business_ids))
                    cat_placeholders = ','.join(['%s'] * len(mapped_category_ids))

                    cursor.execute(f"""
                        SELECT mi.item_category_id, mi.sub_category_id, uc.category_name as sub_category_name
                        FROM menuItems mi
                        LEFT JOIN universal_Categories uc ON uc.category_id = mi.sub_category_id
                        WHERE mi.business_id IN ({biz_placeholders})
                        AND mi.item_category_id IN ({cat_placeholders})
                        AND mi.sub_category_id IS NOT NULL
                        AND mi.sub_category_id > 0
                        GROUP BY mi.item_category_id, mi.sub_category_id, uc.category_name
                    """, include_business_ids + list(mapped_category_ids))

                    subcat_rows = cursor.fetchall()
                    for cat_id, sub_cat_id, sub_cat_name in subcat_rows:
                        try:
                            cat_id_int = int(cat_id)
                        except Exception:
                            continue
                        entry = by_id.get(cat_id_int)
                        if entry is None:
                            continue
                        if sub_cat_name and str(sub_cat_name).strip():
                            entry["sub_categories"].append(str(sub_cat_name).strip())

                    for entry in by_id.values():
                        entry["sub_categories"] = sorted(list(set([sc.strip() for sc in entry["sub_categories"] if sc and sc.strip()])))

                for entry in by_id.values():
                    entry["children"] = []

                roots = []
                for entry in by_id.values():
                    pid = entry.get('parent_category_id')
                    parent = None
                    if pid not in (None, ''):
                        try:
                            parent = by_id.get(int(pid))
                        except Exception:
                            parent = None

                    if parent is None:
                        roots.append(entry)
                    else:
                        parent["children"].append(entry)

                def _sort_tree(nodes):
                    nodes.sort(key=lambda x: x.get('category_name') or '')
                    for n in nodes:
                        children = n.get('children') or []
                        _sort_tree(children)

                _sort_tree(roots)

                # Post-process to distribute parent items to children and update counts
                for root in roots:
                    _distribute_parent_items_to_children(root, business_type, include_business_ids)
                    _update_category_count_with_children(root, business_type, include_business_ids)

                categories = roots
                total_categories = len(mapped_category_ids)
                
        elif business_type == 'R01':  # Grocery
            # Fetch categories from both parent business AND all sub-level businesses
            with connection.cursor() as cursor:
                cursor.execute("""
                    SELECT DISTINCT uc.category_id, TRIM(uc.category_name) as category_name, uc.parent_category_id, uc.category_image
                    FROM category_mapping cm
                    JOIN universal_Categories uc ON cm.category_id = uc.category_id
                    WHERE cm.business_id = %s
                    AND cm.is_active = 1
                    AND uc.category_name IS NOT NULL
                    AND TRIM(uc.category_name) != ''
                """, [business_id])
                parent_rows = cursor.fetchall()

                cursor.execute("""
                    SELECT DISTINCT uc.category_id, TRIM(uc.category_name) as category_name, uc.parent_category_id, uc.category_image
                    FROM category_mapping cm
                    JOIN universal_Categories uc ON cm.category_id = uc.category_id
                    JOIN businesses b ON cm.business_id = b.business_id
                    WHERE b.master = %s
                    AND cm.is_active = 1
                    AND uc.category_name IS NOT NULL
                    AND TRIM(uc.category_name) != ''
                """, [business_id])
                sub_rows = cursor.fetchall()

                all_rows = parent_rows + sub_rows

                # Get include_business_ids for image and count queries
                cursor.execute("""
                    SELECT b.business_id
                    FROM businesses b
                    WHERE b.master = %s
                """, [business_id])
                sub_biz_rows = cursor.fetchall()
                include_business_ids = [business_id] + [r[0] for r in sub_biz_rows if r and r[0]]

                by_id = {}
                mapped_category_ids = set()
                for row in all_rows:
                    if not row or row[0] is None:
                        continue
                    category_id = int(row[0])
                    category_name = row[1]
                    parent_category_id = row[2] if len(row) > 2 else None
                    category_image = row[3] if len(row) > 3 else None
                    if not category_name:
                        continue
                    mapped_category_ids.add(category_id)
                    
                    # Get item count for this category
                    item_count = _get_category_item_count(category_id, business_type, include_business_ids)
                    
                    # Get category image with fallback logic
                    final_category_image = _get_category_image_with_fallback(request, category_id, business_id, business_type, include_business_ids)
                    
                    by_id[category_id] = {
                        "category_id": category_id,
                        "category_name": standardize_category_name(category_name),
                        "parent_category_id": parent_category_id,
                        "category_image": final_category_image,
                        "item_count": item_count,
                        "sub_categories": []
                    }

                missing_parent_ids = set()
                for entry in by_id.values():
                    pid = entry.get('parent_category_id')
                    if pid in (None, ''):
                        continue
                    try:
                        pid_int = int(pid)
                    except Exception:
                        continue
                    if pid_int not in by_id:
                        missing_parent_ids.add(pid_int)

                while missing_parent_ids:
                    placeholders = ','.join(['%s'] * len(missing_parent_ids))
                    cursor.execute(f"""
                        SELECT uc.category_id, TRIM(uc.category_name) as category_name, uc.parent_category_id, uc.category_image
                        FROM universal_Categories uc
                        WHERE uc.category_id IN ({placeholders})
                        AND uc.category_name IS NOT NULL
                        AND TRIM(uc.category_name) != ''
                    """, list(missing_parent_ids))
                    parent_rows = cursor.fetchall()
                    if not parent_rows:
                        break

                    for row in parent_rows:
                        if not row or row[0] is None:
                            continue
                        cid = int(row[0])
                        cname = row[1]
                        cpid = row[2] if len(row) > 2 else None
                        cimage = row[3] if len(row) > 3 else None
                        if not cname:
                            continue
                        if cid not in by_id:
                            # Get item count for this missing parent category
                            item_count = _get_category_item_count(cid, business_type, include_business_ids)
                            
                            # Get category image with fallback logic
                            final_category_image = _get_category_image_with_fallback(request, cid, business_id, business_type, include_business_ids)
                            
                            by_id[cid] = {
                                "category_id": cid,
                                "category_name": standardize_category_name(cname),
                                "parent_category_id": cpid,
                                "category_image": final_category_image,
                                "item_count": item_count,
                                "sub_categories": []
                            }

                    next_missing = set()
                    for entry in by_id.values():
                        pid = entry.get('parent_category_id')
                        if pid in (None, ''):
                            continue
                        try:
                            pid_int = int(pid)
                        except Exception:
                            continue
                        if pid_int not in by_id:
                            next_missing.add(pid_int)
                    missing_parent_ids = next_missing

                if by_id and mapped_category_ids:
                    cursor.execute("""
                        SELECT b.business_id
                        FROM businesses b
                        WHERE b.master = %s
                    """, [business_id])
                    sub_biz_rows = cursor.fetchall()
                    include_business_ids = [business_id] + [r[0] for r in sub_biz_rows]

                    biz_placeholders = ','.join(['%s'] * len(include_business_ids))
                    cat_placeholders = ','.join(['%s'] * len(mapped_category_ids))

                    cursor.execute(f"""
                        SELECT gp.category_id, gp.sub_category_id, uc.category_name as sub_category_name
                        FROM Groceries_Products gp
                        LEFT JOIN universal_Categories uc ON uc.category_id = gp.sub_category_id
                        WHERE gp.business_id IN ({biz_placeholders})
                        AND gp.category_id IN ({cat_placeholders})
                        AND gp.sub_category_id IS NOT NULL
                        AND gp.sub_category_id > 0
                        GROUP BY gp.category_id, gp.sub_category_id, uc.category_name
                    """, include_business_ids + list(mapped_category_ids))
                    subcat_rows = cursor.fetchall()

                    for cat_id, sub_cat_id, sub_cat_name in subcat_rows:
                        try:
                            cat_id_int = int(cat_id)
                        except Exception:
                            continue
                        entry = by_id.get(cat_id_int)
                        if entry is None:
                            continue
                        if sub_cat_name and sub_cat_name.strip():
                            entry["sub_categories"].append(sub_cat_name.strip())

                    for entry in by_id.values():
                        entry["sub_categories"] = sorted(list(set([sc.strip() for sc in entry["sub_categories"] if sc and sc.strip()])))

                for entry in by_id.values():
                    entry["children"] = []

                roots = []
                for entry in by_id.values():
                    pid = entry.get('parent_category_id')
                    parent = None
                    if pid not in (None, ''):
                        try:
                            parent = by_id.get(int(pid))
                        except Exception:
                            parent = None

                    if parent is None:
                        roots.append(entry)
                    else:
                        parent["children"].append(entry)

                def _sort_tree(nodes):
                    nodes.sort(key=lambda x: x.get('category_name') or '')
                    for n in nodes:
                        children = n.get('children') or []
                        _sort_tree(children)

                _sort_tree(roots)

                # Post-process to update parent category counts with total including children
                for root in roots:
                    _update_category_count_with_children(root, business_type, include_business_ids)

                categories = roots
                total_categories = len(mapped_category_ids)
        elif business_type == 'R08':  # Fashion
            # Fetch categories from both parent business AND all sub-level businesses
            with connection.cursor() as cursor:
                # Get include_business_ids for image and count queries
                cursor.execute("""
                    SELECT b.business_id
                    FROM businesses b
                    WHERE b.master = %s
                """, [business_id])
                sub_biz_rows = cursor.fetchall()
                include_business_ids = [business_id] + [r[0] for r in sub_biz_rows if r and r[0]]
                
                # Get categories from parent business
                cursor.execute("""
                    SELECT DISTINCT uc.category_id, TRIM(uc.category_name) as category_name, uc.category_image
                    FROM fashion_products fp
                    LEFT JOIN universal_Categories uc ON fp.category_id = uc.category_id
                    WHERE fp.business_id = %s 
                    AND uc.category_name IS NOT NULL 
                    AND TRIM(uc.category_name) != ''
                """, [business_id])
                
                parent_rows = cursor.fetchall()
                
                # Get categories from all sub-level businesses
                cursor.execute("""
                    SELECT DISTINCT uc.category_id, TRIM(uc.category_name) as category_name, uc.category_image
                    FROM fashion_products fp
                    LEFT JOIN universal_Categories uc ON fp.category_id = uc.category_id
                    JOIN businesses b ON fp.business_id = b.business_id
                    WHERE b.master = %s 
                    AND uc.category_name IS NOT NULL 
                    AND TRIM(uc.category_name) != ''
                """, [business_id])
                
                sub_rows = cursor.fetchall()
                
                # Combine both parent and sub-level categories
                all_rows = parent_rows + sub_rows
                
                by_id = {}
                mapped_category_ids = set()
                for row in all_rows:
                    if not row or row[0] is None:
                        continue
                    category_id = int(row[0])
                    category_name = row[1]
                    category_image = row[2] if len(row) > 2 else None
                    if not category_name:
                        continue
                    mapped_category_ids.add(category_id)
                    
                    # Get item count for this category
                    item_count = _get_category_item_count(category_id, business_type, include_business_ids)
                    
                    # Get category image with fallback logic
                    final_category_image = _get_category_image_with_fallback(request, category_id, business_id, business_type, include_business_ids)
                    
                    by_id[category_id] = {
                        "category_id": category_id,
                        "category_name": category_name.strip(),
                        "category_image": final_category_image,
                        "item_count": item_count
                    }
                
                # Convert to list format for R08
                categories = list(by_id.values())
                total_categories = len(categories)
        else:
            return Response({
                "error": f"Unsupported business type: {business_type}. Expected R01 (Grocery), R02 (Restaurant), or R08 (Fashion)"
            }, status=status.HTTP_400_BAD_REQUEST)
        # Determine the source of categories
        with connection.cursor() as cursor:
            if business_type == 'R02':
                cursor.execute("""
                    SELECT COUNT(DISTINCT cm.category_id)
                    FROM category_mapping cm
                    JOIN universal_Categories uc ON cm.category_id = uc.category_id
                    WHERE cm.business_id = %s
                    AND cm.is_active = 1
                    AND uc.category_name IS NOT NULL
                    AND TRIM(uc.category_name) != ''
                """, [business_id])
                parent_count = cursor.fetchone()[0]

                cursor.execute("""
                    SELECT COUNT(DISTINCT cm.category_id)
                    FROM category_mapping cm
                    JOIN universal_Categories uc ON cm.category_id = uc.category_id
                    JOIN businesses b ON cm.business_id = b.business_id
                    WHERE b.master = %s
                    AND cm.is_active = 1
                    AND uc.category_name IS NOT NULL
                    AND TRIM(uc.category_name) != ''
                """, [business_id])
                sub_count = cursor.fetchone()[0]
            elif business_type == 'R01':
                cursor.execute("""
                    SELECT COUNT(DISTINCT cm.category_id)
                    FROM category_mapping cm
                    JOIN universal_Categories uc ON cm.category_id = uc.category_id
                    WHERE cm.business_id = %s
                    AND cm.is_active = 1
                    AND uc.category_name IS NOT NULL
                    AND TRIM(uc.category_name) != ''
                """, [business_id])
                parent_count = cursor.fetchone()[0]

                cursor.execute("""
                    SELECT COUNT(DISTINCT cm.category_id)
                    FROM category_mapping cm
                    JOIN universal_Categories uc ON cm.category_id = uc.category_id
                    JOIN businesses b ON cm.business_id = b.business_id
                    WHERE b.master = %s
                    AND cm.is_active = 1
                    AND uc.category_name IS NOT NULL
                    AND TRIM(uc.category_name) != ''
                """, [business_id])
                sub_count = cursor.fetchone()[0]
            elif business_type == 'R08':  # Fashion
               # Count parent categories
               cursor.execute("""
                   SELECT COUNT(DISTINCT TRIM(uc.category_name)) 
                   FROM fashion_products fp
                   LEFT JOIN universal_Categories uc ON fp.category_id = uc.category_id
                   WHERE fp.business_id = %s 
                   AND uc.category_name IS NOT NULL 
                   AND TRIM(uc.category_name) != ''
               """, [business_id])
               parent_count = cursor.fetchone()[0]
               
               # Count sub-level categories
               cursor.execute("""
                   SELECT COUNT(DISTINCT TRIM(uc.category_name)) 
                   FROM fashion_products fp
                   LEFT JOIN universal_Categories uc ON fp.category_id = uc.category_id
                   JOIN businesses b ON fp.business_id = b.business_id
                   WHERE b.master = %s 
                   AND uc.category_name IS NOT NULL 
                   AND TRIM(uc.category_name) != ''
               """, [business_id])
               sub_count = cursor.fetchone()[0]
            
            # Determine source based on what we found
            if parent_count > 0 and sub_count > 0:
                source_info = "parent_and_sub_businesses"
            elif parent_count > 0:
                source_info = "parent_business"
            elif sub_count > 0:
                source_info = "sub_level_businesses"
            else:
                source_info = "no_categories_found"
        
        # Sort categories alphabetically after standardization
        if business_type == 'R08':
            categories = sorted(categories)
        elif business_type in ('R01', 'R02'):
            categories = sorted(categories, key=lambda x: x.get('category_name') or '')
        
        if total_categories == 0:
            total_categories = len(categories)

        message = f"Found {total_categories} unique categories"
        if source_info == "sub_level_businesses":
            message += f" from sub-level businesses under {business.businessName}"
        elif source_info == "parent_and_sub_businesses":
            message += f" from {business.businessName} and its sub-level businesses"
        elif source_info == "parent_business":
            message += f" from {business.businessName}"
        elif source_info == "no_categories_found":
            message = f"No categories found for {business.businessName}"
        
        return Response({
            "success": True,
            "business_id": business_id,
            "business_type": business_type,
            "business_name": business.businessName,
            "is_business_open": bool(business.status),
            "categories": categories,
            "total_categories": total_categories,
            "source": source_info,
            "message": message
        }, status=status.HTTP_200_OK)
        
    except Business.DoesNotExist:
        return Response({
            "error": f"Business with ID {business_id} not found or inactive"
        }, status=status.HTTP_404_NOT_FOUND)
    except Exception as e:
        return Response({
            "error": str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@swagger_auto_schema(methods=['GET'],tags=['Consumer'])
@api_view(['GET'])
def popular_items(request):
    """
    Fetch top N most popular items across ALL businesses of given type (R01 / R02),
    including both master and sublevel.
    """
    business_type = request.query_params.get('business_type')
    business_id = request.query_params.get('business_id')
    limit = int(request.query_params.get('limit', 10))  # Default = 10
    
    if not business_type and not business_id:
        return Response({
            "error": "business_type or business_id is required as query parameter"
        }, status=status.HTTP_400_BAD_REQUEST)
    
    if limit > 50:
        limit = 50
    
    try:
        popular_items_list = []

        # When business_id is provided, derive business_type and restrict to that business + its sub-levels
        business = None
        if business_id:
            try:
                business = Business.objects.get(business_id=business_id)
                if business.status == 0:
                    return Response({"error": "Business is currently closed"}, status=status.HTTP_400_BAD_REQUEST)
            except Business.DoesNotExist:
                return Response({
                    "error": f"Business with ID {business_id} not found"
                }, status=status.HTTP_404_NOT_FOUND)

            business_type = business.businessType
            display_name = business.businessName

            with connection.cursor() as cursor:
                # Collect active sub-level business IDs
                cursor.execute("""
                    SELECT b.business_id
                    FROM businesses b
                    WHERE b.master = %s AND b.status != 0
                """, [business_id])
                sub_rows = cursor.fetchall()

                include_business_ids = [business_id] + [row[0] for row in sub_rows]
                placeholders = ','.join(['%s'] * len(include_business_ids))

                if business_type == 'R02':  # Restaurants for this business and its sub-levels
                    cursor.execute(f"""
                        SELECT 
                            m.item_id,
                            m.business_id,
                            m.item_name,
                            m.item_image,
                            m.item_category,
                            m.item_type,
                            m.original_cost,
                            m.selling_price,
                            COALESCE(m.rating, 4.0) as rating,
                            COUNT(oi.item_id) as order_count,
                            b.businessName as business_name,
                            b.level as business_level
                        FROM menuItems m
                        LEFT JOIN order_items oi ON m.item_id = oi.item_id
                        LEFT JOIN orders o ON oi.order_id = o.order_id
                        JOIN businesses b ON m.business_id = b.business_id
                        WHERE b.business_id IN ({placeholders})
                          AND b.status != 0
                          AND (o.status IS NULL OR o.status NOT IN ('cancelled','failed'))
                        GROUP BY m.item_id, m.business_id, m.item_name, m.item_image, 
                                 m.item_category, m.item_type, 
                                 m.original_cost, m.selling_price, m.rating, b.businessName, b.level
                        ORDER BY order_count DESC, m.item_name ASC
                        LIMIT %s
                    """, include_business_ids + [limit])
                elif business_type == 'R01':  # Grocery for this business and its sub-levels
                    cursor.execute(f"""
                        SELECT 
                            gpv.variant_id AS item_id,
                            gp.business_id,
                            gp.product_name AS item_name,
                            gp.main_image AS item_image,
                            gc.category_name AS item_category,
                            gp.sub_category AS item_type,
                            gpv.original_cost,
                            gpv.selling_price,
                            COALESCE(gp.rating, 4.0) as rating,
                            COUNT(oi.product_item_id) AS order_count,
                            b.businessName AS business_name,
                            b.level AS business_level,
                            CONCAT(
                              gp.product_name,
                              CASE 
                                WHEN gpv.net_weight IS NOT NULL AND gpv.net_weight_unit IS NOT NULL 
                                  THEN CONCAT(' - ', gpv.net_weight, ' ', gpv.net_weight_unit)
                                WHEN gpv.size IS NOT NULL AND gpv.size != '' 
                                  THEN CONCAT(' - ', gpv.size)
                                ELSE ''
                              END
                            ) AS full_name
                        FROM Groceries_ProductVariants_1 gpv
                        JOIN Groceries_Products gp ON gpv.product_id = gp.product_id
                        LEFT JOIN Groceries_Categories gc ON gp.category_id = gc.category_id
                        LEFT JOIN order_items oi ON oi.product_item_id = gpv.variant_id
                        LEFT JOIN orders o ON oi.order_id = o.order_id
                        JOIN businesses b ON gp.business_id = b.business_id
                        WHERE b.business_id IN ({placeholders})
                          AND b.status != 0
                          AND gpv.is_active = 1
                          AND (o.status IS NULL OR o.status NOT IN ('cancelled','failed'))
                        GROUP BY gpv.variant_id, gp.business_id, gp.product_name, gp.main_image, 
                                 gc.category_name, gp.sub_category, 
                                 gpv.original_cost, gpv.selling_price, gp.rating, b.businessName, b.level
                        ORDER BY order_count DESC, item_name ASC
                        LIMIT %s
                    """, include_business_ids + [limit])
                elif business_type == 'R08':  # Fashion for this business and its sub-levels
                    cursor.execute(f"""
                        SELECT 
                            fpv.variant_id AS item_id,
                            fp.business_id,
                            fp.name AS item_name,
                            fp.main_image AS item_image,
                            uc.category_name AS item_category,
                            fp.subcategory_id AS item_type,
                            fpv.original_cost,
                            fpv.selling_price,
                            COALESCE(fp.rating, 4.0) as rating,
                            COUNT(oi.product_item_id) as order_count,
                            b.businessName as business_name,
                            b.level as business_level,
                            CONCAT(
                              fp.name,
                              CASE 
                                WHEN fpv.size IS NOT NULL AND fpv.size != '' 
                                  THEN CONCAT(' - ', fpv.size)
                                WHEN fpv.color IS NOT NULL AND fpv.color != '' 
                                  THEN CONCAT(' - ', fpv.color)
                                ELSE ''
                              END
                            ) AS full_name
                        FROM fashion_product_variants fpv
                        JOIN fashion_products fp ON fpv.product_id = fp.product_id
                        LEFT JOIN universal_Categories uc ON fp.category_id = uc.category_id
                        LEFT JOIN order_items oi ON oi.product_item_id = fpv.variant_id
                        LEFT JOIN orders o ON oi.order_id = o.order_id
                        JOIN businesses b ON fp.business_id = b.business_id
                        WHERE b.business_id IN ({placeholders})
                          AND b.status != 0
                          AND fp.is_active = 1
                          AND (o.status IS NULL OR o.status NOT IN ('cancelled','failed'))
                        GROUP BY fpv.variant_id, fp.business_id, fp.name, fp.main_image, 
                                 uc.category_name, fp.subcategory_id, 
                                 fpv.original_cost, fpv.selling_price, fp.rating, b.businessName, b.level
                        ORDER BY order_count DESC, item_name ASC
                        LIMIT %s
                    """, include_business_ids + [limit])
                else:
                    return Response({
                        "error": f"Unsupported business type derived from business_id: {business_type}. Expected R01 (Grocery), R02 (Restaurant), or R08 (Fashion)"
                    }, status=status.HTTP_400_BAD_REQUEST)

                results = cursor.fetchall()

        else:
            # Existing behavior: across ALL businesses of a given type
            # Pick master (for display name) but include both master + sublevel in results
            master_business = Business.objects.filter(
                businessType=business_type, level='master'
            ).first()

            display_name = master_business.businessName if master_business else f"Type {business_type}"

            with connection.cursor() as cursor:
                if business_type == 'R02':  # Restaurants
                    cursor.execute("""
                        SELECT 
                            m.item_id,
                            m.business_id,
                            m.item_name,
                            m.item_image,
                            m.item_category,
                            m.item_type,
                            m.original_cost,
                            m.selling_price,
                            COALESCE(m.rating, 4.0) as rating,
                            COUNT(oi.item_id) as order_count,
                            b.businessName as business_name,
                            b.level as business_level
                        FROM menuItems m
                        LEFT JOIN order_items oi ON m.item_id = oi.item_id
                        LEFT JOIN orders o ON oi.order_id = o.order_id
                        JOIN businesses b ON m.business_id = b.business_id
                        WHERE b.businessType = %s
                          AND b.level IN ('master','sublevel')
                          AND b.status != 0
                          AND (o.status IS NULL OR o.status NOT IN ('cancelled','failed'))
                        GROUP BY m.item_id, m.business_id, m.item_name, m.item_image, 
                                 m.item_category, m.item_type, 
                                 m.original_cost, m.selling_price, m.rating, b.businessName, b.level
                        ORDER BY order_count DESC, m.item_name ASC
                        LIMIT %s
                    """, [business_type, limit])
                
                elif business_type == 'R01':  # Grocery
                    cursor.execute("""
                        SELECT 
                            gpv.variant_id AS item_id,
                            gp.business_id,
                            gp.product_name AS item_name,
                            gp.main_image AS item_image,
                            gc.category_name AS item_category,
                            gp.sub_category AS item_type,
                            gpv.original_cost,
                            gpv.selling_price,
                            COALESCE(gp.rating, 4.0) as rating,
                            COUNT(oi.product_item_id) AS order_count,
                            b.businessName AS business_name,
                            b.level AS business_level,
                            CONCAT(
                              gp.product_name,
                              CASE 
                                WHEN gpv.net_weight IS NOT NULL AND gpv.net_weight_unit IS NOT NULL 
                                  THEN CONCAT(' - ', gpv.net_weight, ' ', gpv.net_weight_unit)
                                WHEN gpv.size IS NOT NULL AND gpv.size != '' 
                                  THEN CONCAT(' - ', gpv.size)
                                ELSE ''
                              END
                            ) AS full_name
                        FROM Groceries_ProductVariants_1 gpv
                        JOIN Groceries_Products gp ON gpv.product_id = gp.product_id
                        LEFT JOIN Groceries_Categories gc ON gp.category_id = gc.category_id
                        LEFT JOIN order_items oi ON oi.product_item_id = gpv.variant_id
                        LEFT JOIN orders o ON oi.order_id = o.order_id
                        JOIN businesses b ON gp.business_id = b.business_id
                        WHERE b.businessType = %s
                          AND b.level IN ('master','sublevel')
                          AND b.status != 0
                          AND gpv.is_active = 1
                          AND (o.status IS NULL OR o.status NOT IN ('cancelled','failed'))
                        GROUP BY gpv.variant_id, gp.business_id, gp.product_name, gp.main_image, 
                                 gc.category_name, gp.sub_category, 
                                 gpv.original_cost, gpv.selling_price, gp.rating, b.businessName, b.level
                        ORDER BY order_count DESC, item_name ASC
                        LIMIT %s
                    """, [business_type, limit])
                
                elif business_type == 'R08':  # Fashion
                    cursor.execute("""
                        SELECT 
                            fpv.variant_id AS item_id,
                            fp.business_id,
                            fp.name AS item_name,
                            fp.main_image AS item_image,
                            uc.category_name AS item_category,
                            fp.subcategory_id AS item_type,
                            fpv.original_cost,
                            fpv.selling_price,
                            COALESCE(fp.rating, 4.0) as rating,
                            COUNT(oi.product_item_id) as order_count,
                            b.businessName as business_name,
                            b.level as business_level,
                            CONCAT(
                              fp.name,
                              CASE 
                                WHEN fpv.size IS NOT NULL AND fpv.size != '' 
                                  THEN CONCAT(' - ', fpv.size)
                                WHEN fpv.color IS NOT NULL AND fpv.color != '' 
                                  THEN CONCAT(' - ', fpv.color)
                                ELSE ''
                              END
                            ) AS full_name
                        FROM fashion_product_variants fpv
                        JOIN fashion_products fp ON fpv.product_id = fp.product_id
                        LEFT JOIN universal_Categories uc ON fp.category_id = uc.category_id
                        LEFT JOIN order_items oi ON oi.product_item_id = fpv.variant_id
                        LEFT JOIN orders o ON oi.order_id = o.order_id
                        JOIN businesses b ON fp.business_id = b.business_id
                        WHERE b.businessType = %s
                          AND b.level IN ('master','sublevel')
                          AND b.status != 0
                          AND fp.is_active = 1
                          AND (o.status IS NULL OR o.status NOT IN ('cancelled','failed'))
                        GROUP BY fpv.variant_id, fp.business_id, fp.name, fp.main_image, 
                                 uc.category_name, fp.subcategory_id, 
                                 fpv.original_cost, fpv.selling_price, fp.rating, b.businessName, b.level
                        ORDER BY order_count DESC, item_name ASC
                        LIMIT %s
                    """, [business_type, limit])
                
                else:
                    return Response({
                        "error": f"Unsupported business type: {business_type}. Expected R01 (Grocery), R02 (Restaurant), or R08 (Fashion)"
                    }, status=status.HTTP_400_BAD_REQUEST)

                results = cursor.fetchall()

        # Build base URL once
        base_url = f"{request.scheme}://{request.get_host()}"

        for row in results:
            image_url = _abs_item_image(request, row[3] if len(row) > 3 else None)

            item_data = {
                "item_id": row[0],
                "business_id": row[1],
                "item_name": row[2],
                "item_image": image_url,
                "item_category": standardize_category_name(row[4]) if row[4] else None,
                "item_type": row[5],
                "original_cost": float(row[6]) if row[6] else 0.0,
                "selling_price": float(row[7]) if row[7] else 0.0,
                "rating": float(row[8]) if row[8] else 4.0,
                "order_count": row[9],
                "business_name": row[10],
                "business_level": row[11],
                "full_name": (row[12] if len(row) > 12 else row[2]),
                "popularity_rank": len(popular_items_list) + 1
            }
            popular_items_list.append(item_data)
    
        total_items = len(popular_items_list)
        items_with_orders = len([i for i in popular_items_list if i['order_count'] > 0])
        items_without_orders = total_items - items_with_orders
        
        response_payload = {
            "success": True,
            "business_type": business_type,
            "business_name": display_name,
            "popular_items": popular_items_list,
            "total_items": total_items,
            "items_with_orders": items_with_orders,
            "items_without_orders": items_without_orders,
            "limit_requested": limit,
            "message": f"Found {total_items} popular items for {display_name}"
        }
        if business:
            response_payload["is_business_open"] = bool(getattr(business, 'status', True))
        return Response(response_payload, status=status.HTTP_200_OK)
    
    except Exception as e:
        return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@swagger_auto_schema(methods=['GET'],tags=['Consumer'])
@api_view(['GET'])
def new_arrivals(request):
    business_type = (request.query_params.get('business_type') or request.query_params.get('type') or '').strip() or None
    business_id = request.query_params.get('business_id')
    limit = min(_parse_int(request.query_params.get('limit', 20), 20) or 20, 50)
    offset = max(_parse_int(request.query_params.get('offset', 0), 0) or 0, 0)
    days = _parse_int(request.query_params.get('days'), None)

    if not business_id and not business_type:
        resolved_type = 'ALL'
        display_name = 'All Businesses'
        include_business_ids = None
    else:
        resolved_type, display_name, include_business_ids, err = _resolve_scope(request, business_id, business_type)
        if err:
            return err

    try:
        params = []
        if include_business_ids:
            biz_ph = ','.join(['%s'] * len(include_business_ids))
            params.extend(include_business_ids)

        if resolved_type == 'ALL':
            params = []

            sql_r02 = """
                SELECT
                    m.item_id,
                    m.business_id,
                    m.item_name,
                    m.item_image,
                    m.item_category,
                    m.item_type,
                    m.original_cost,
                    m.selling_price,
                    COALESCE(m.updated_at, m.created_at) as sort_dt,
                    'R02' as business_type
                FROM menuItems m
                WHERE COALESCE(m.status, 1) = 1
                  AND COALESCE(m.is_active, 1) = 1
            """
            if days is not None:
                sql_r02 += " AND COALESCE(m.updated_at, m.created_at) >= (NOW() - INTERVAL %s DAY) "
                params.append(days)

            sql_r01 = """
                SELECT
                    gp.product_id,
                    gp.business_id,
                    gp.product_name,
                    gp.main_image,
                    uc.category_name,
                    gp.sub_category,
                    COALESCE(gpv.original_cost, 0),
                    COALESCE(gpv.selling_price, 0),
                    COALESCE(gp.updated_at, gp.created_at) as sort_dt,
                    'R01' as business_type
                FROM Groceries_Products gp
                LEFT JOIN universal_Categories uc ON gp.category_id = uc.category_id
                LEFT JOIN Groceries_ProductVariants_1 gpv ON gp.product_id = gpv.product_id AND COALESCE(gpv.is_active, 1) = 1
                WHERE COALESCE(gp.is_visible, 1) = 1
            """
            if days is not None:
                sql_r01 += " AND COALESCE(gp.updated_at, gp.created_at) >= (NOW() - INTERVAL %s DAY) "
                params.append(days)

            sql_r08 = """
                SELECT
                    fp.product_id,
                    fp.business_id,
                    fp.name,
                    fp.main_image,
                    uc.category_name,
                    fp.subcategory_id,
                    COALESCE(fpv.original_cost, 0),
                    COALESCE(fpv.selling_price, 0),
                    COALESCE(fp.created_at, fp.updated_at, fpv.created_at, fpv.updated_at) as sort_dt,
                    'R08' as business_type
                FROM fashion_products fp
                LEFT JOIN universal_Categories uc ON fp.category_id = uc.category_id
                LEFT JOIN fashion_product_variants fpv ON fpv.product_id = fp.product_id AND COALESCE(fpv.is_active, 1) = 1
                WHERE COALESCE(fp.is_active, 1) = 1
            """
            if days is not None:
                sql_r08 += " AND COALESCE(fp.created_at, fp.updated_at, fpv.created_at, fpv.updated_at) >= (NOW() - INTERVAL %s DAY) "
                params.append(days)

            sql_final = f"""
                SELECT
                    item_id,
                    business_id,
                    item_name,
                    item_image,
                    item_category,
                    item_type,
                    original_cost,
                    selling_price,
                    sort_dt,
                    business_type
                FROM (
                    {sql_r02}
                    UNION ALL
                    {sql_r01}
                    UNION ALL
                    {sql_r08}
                ) u
                ORDER BY sort_dt DESC, item_id DESC
                LIMIT %s OFFSET %s
            """
            params.extend([limit, offset])

        elif resolved_type == 'R02':
            sql = """
                SELECT
                    m.item_id,
                    m.business_id,
                    m.item_name,
                    m.item_image,
                    m.item_category,
                    m.item_type,
                    m.original_cost,
                    m.selling_price,
                    COALESCE(m.updated_at, m.created_at),
                    b.businessName as business_name
                FROM menuItems m
                LEFT JOIN businesses b ON m.business_id = b.business_id
            """
            where = " WHERE COALESCE(m.status, 1) = 1 AND COALESCE(m.is_active, 1) = 1 "
            if include_business_ids:
                where += f" AND m.business_id IN ({biz_ph}) "
            else:
                where += " AND EXISTS (SELECT 1 FROM businesses b2 WHERE b2.business_id = m.business_id AND b2.businessType = %s) "
                params.append(resolved_type)
            if days is not None:
                where += " AND COALESCE(m.updated_at, m.created_at) >= (NOW() - INTERVAL %s DAY) "
                params.append(days)
            order = " ORDER BY COALESCE(m.updated_at, m.created_at) DESC, m.item_id DESC "
            sql_final = sql + where + order + " LIMIT %s OFFSET %s "
            params.extend([limit, offset])
        elif resolved_type == 'R01':
            sql = """
                SELECT
                    gp.product_id,
                    gp.business_id,
                    gp.product_name,
                    gp.main_image,
                    uc.category_name,
                    gp.sub_category,
                    COALESCE(gpv.original_cost, 0),
                    COALESCE(gpv.selling_price, 0),
                    COALESCE(gp.updated_at, gp.created_at),
                    b.businessName as business_name
                FROM Groceries_Products gp
                LEFT JOIN universal_Categories uc ON gp.category_id = uc.category_id
                LEFT JOIN Groceries_ProductVariants_1 gpv ON gp.product_id = gpv.product_id AND COALESCE(gpv.is_active, 1) = 1
                LEFT JOIN businesses b ON gp.business_id = b.business_id
            """
            where = " WHERE COALESCE(gp.is_visible, 1) = 1 "
            if include_business_ids:
                where += f" AND gp.business_id IN ({biz_ph}) "
            else:
                where += " AND EXISTS (SELECT 1 FROM businesses b2 WHERE b2.business_id = gp.business_id AND b2.businessType = %s) "
                params.append(resolved_type)
            if days is not None:
                where += " AND COALESCE(gp.updated_at, gp.created_at) >= (NOW() - INTERVAL %s DAY) "
                params.append(days)
            order = " ORDER BY COALESCE(gp.updated_at, gp.created_at) DESC, gp.product_id DESC "
            sql_final = sql + where + order + " LIMIT %s OFFSET %s "
            params.extend([limit, offset])
        elif resolved_type == 'R08':
            sql = """
                SELECT
                    fp.product_id,
                    fp.business_id,
                    fp.name,
                    fp.main_image,
                    uc.category_name,
                    fp.subcategory_id,
                    COALESCE(fpv.original_cost, 0),
                    COALESCE(fpv.selling_price, 0),
                    COALESCE(fp.created_at, fp.updated_at, fpv.created_at, fpv.updated_at),
                    b.businessName as business_name
                FROM fashion_products fp
                LEFT JOIN universal_Categories uc ON fp.category_id = uc.category_id
                LEFT JOIN fashion_product_variants fpv ON fpv.product_id = fp.product_id AND COALESCE(fpv.is_active, 1) = 1
                LEFT JOIN businesses b ON fp.business_id = b.business_id
            """
            if include_business_ids:
                sql += f" AND fp.business_id IN ({biz_ph}) "
            else:
                sql += " AND EXISTS (SELECT 1 FROM businesses b WHERE b.business_id = fp.business_id AND b.businessType = %s) "
                params.append(resolved_type)
            if days is not None:
                sql += " AND COALESCE(fp.created_at, fp.updated_at, fpv.created_at, fpv.updated_at) >= (NOW() - INTERVAL %s DAY) "
                params.append(days)
            sql_final = sql + " ORDER BY COALESCE(fp.created_at, fp.updated_at, fpv.created_at, fpv.updated_at) DESC, fp.product_id DESC LIMIT %s OFFSET %s "
            params.extend([limit, offset])
        else:
            return Response({"error": f"Unsupported business type: {resolved_type}. Expected R01, R02, or R08"}, status=status.HTTP_400_BAD_REQUEST)

        with connection.cursor() as cursor:
            cursor.execute(sql_final, params)
            rows = cursor.fetchall()

        items = []
        for r in rows:
            original_cost = float(r[6]) if r[6] is not None else 0.0
            selling_price = float(r[7]) if r[7] is not None else 0.0
            diff_amount = max(0.0, original_cost - selling_price)
            percent_display = 0
            if original_cost and diff_amount > 0:
                try:
                    percent_display = int(round((diff_amount / original_cost) * 100))
                except Exception:
                    percent_display = 0

            created_at = _dt_to_iso(r[8])

            biz_type_for_item = resolved_type
            if resolved_type == 'ALL' and len(r) > 9:
                biz_type_for_item = r[9]

            items.append({
                'item_id': r[0],
                'business_id': r[1],
                'business_name': r[9] if len(r) > 9 else None,
                'item_name': r[2],
                'item_image': _abs_item_image(request, r[3]),
                'item_category': standardize_category_name(r[4]) if r[4] else None,
                'item_type': r[5],
                'business_type': biz_type_for_item,
                'original_cost': original_cost,
                'selling_price': selling_price,
                'created_at': created_at,
                'diff_amount': f"{diff_amount:.2f}",
                'percent_display': percent_display,
                'discount_percentage': percent_display,
            })

        return Response({
            'success': True,
            'business_type': resolved_type,
            'business_name': display_name,
            'limit': limit,
            'offset': offset,
            'count': len(items),
            'items': items,
        }, status=status.HTTP_200_OK)

    except Exception as e:
        return Response({"success": False, "message": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@swagger_auto_schema(methods=['GET'],tags=['Consumer'])
@api_view(['GET'])
def on_sale_items(request):
    business_type = (request.query_params.get('business_type') or request.query_params.get('type') or '').strip() or None
    business_id = request.query_params.get('business_id')
    limit = min(_parse_int(request.query_params.get('limit', 20), 20) or 20, 50)
    offset = max(_parse_int(request.query_params.get('offset', 0), 0) or 0, 0)

    if not business_id and not business_type:
        resolved_type = 'ALL'
        display_name = 'All Businesses'
        include_business_ids = None
    else:
        resolved_type, display_name, include_business_ids, err = _resolve_scope(request, business_id, business_type)
        if err:
            return err

    try:
        params = []
        if include_business_ids:
            biz_ph = ','.join(['%s'] * len(include_business_ids))
            params.extend(include_business_ids)

        if resolved_type == 'ALL':
            params = []

            sql_r02 = """
                SELECT
                    m.item_id AS item_id,
                    m.business_id AS business_id,
                    m.item_name AS item_name,
                    m.item_image AS item_image,
                    m.item_category AS item_category,
                    m.item_type AS item_type,
                    COALESCE(m.original_cost, 0) AS original_cost,
                    COALESCE(m.selling_price, 0) AS selling_price,
                    COALESCE(m.updated_at, m.created_at) AS sort_dt,
                    'R02' AS business_type,
                    ((COALESCE(m.original_cost,0) - COALESCE(m.selling_price,0)) / NULLIF(COALESCE(m.original_cost,0),0)) AS discount_ratio
                FROM menuItems m
                WHERE COALESCE(m.status, 1) = 1
                  AND COALESCE(m.is_active, 1) = 1
                  AND COALESCE(m.original_cost, 0) > 0
                  AND COALESCE(m.original_cost, 0) > COALESCE(m.selling_price, 0)
            """

            sql_r01 = """
                SELECT
                    gp.product_id AS item_id,
                    gp.business_id AS business_id,
                    gp.product_name AS item_name,
                    gp.main_image AS item_image,
                    uc.category_name AS item_category,
                    gp.sub_category AS item_type,
                    COALESCE(gpv.original_cost, 0) AS original_cost,
                    COALESCE(gpv.selling_price, 0) AS selling_price,
                    COALESCE(gp.updated_at, gp.created_at) AS sort_dt,
                    'R01' AS business_type,
                    ((COALESCE(gpv.original_cost,0) - COALESCE(gpv.selling_price,0)) / NULLIF(COALESCE(gpv.original_cost,0),0)) AS discount_ratio
                FROM Groceries_Products gp
                LEFT JOIN universal_Categories uc ON gp.category_id = uc.category_id
                JOIN Groceries_ProductVariants_1 gpv ON gp.product_id = gpv.product_id AND COALESCE(gpv.is_active, 1) = 1
                WHERE COALESCE(gp.is_visible, 1) = 1
                  AND COALESCE(gpv.original_cost, 0) > 0
                  AND COALESCE(gpv.original_cost, 0) > COALESCE(gpv.selling_price, 0)
            """

            sql_r08 = """
                SELECT
                    fp.product_id AS item_id,
                    fp.business_id AS business_id,
                    fp.name AS item_name,
                    fp.main_image AS item_image,
                    uc.category_name AS item_category,
                    fp.subcategory_id AS item_type,
                    COALESCE(fpv.original_cost, 0) AS original_cost,
                    COALESCE(fpv.selling_price, 0) AS selling_price,
                    COALESCE(fp.created_at, fp.updated_at, fpv.created_at, fpv.updated_at) AS sort_dt,
                    'R08' AS business_type,
                    ((COALESCE(fpv.original_cost,0) - COALESCE(fpv.selling_price,0)) / NULLIF(COALESCE(fpv.original_cost,0),0)) AS discount_ratio
                FROM fashion_products fp
                LEFT JOIN universal_Categories uc ON fp.category_id = uc.category_id
                JOIN fashion_product_variants fpv ON fpv.product_id = fp.product_id AND COALESCE(fpv.is_active, 1) = 1
                WHERE COALESCE(fp.is_active, 1) = 1
                  AND COALESCE(fpv.original_cost, 0) > 0
                  AND COALESCE(fpv.original_cost, 0) > COALESCE(fpv.selling_price, 0)
            """

            sql = f"""
                SELECT
                    item_id,
                    business_id,
                    item_name,
                    item_image,
                    item_category,
                    item_type,
                    original_cost,
                    selling_price,
                    sort_dt,
                    business_type,
                    discount_ratio
                FROM (
                    {sql_r02}
                    UNION ALL
                    {sql_r01}
                    UNION ALL
                    {sql_r08}
                ) u
                ORDER BY discount_ratio DESC, sort_dt DESC
                LIMIT %s OFFSET %s
            """
            params.extend([limit, offset])

        elif resolved_type == 'R02':
            sql = """
                SELECT
                    m.item_id,
                    m.business_id,
                    m.item_name,
                    m.item_image,
                    m.item_category,
                    m.item_type,
                    COALESCE(m.original_cost, 0),
                    COALESCE(m.selling_price, 0),
                    COALESCE(m.updated_at, m.created_at),
                    b.businessName as business_name
                FROM menuItems m
                LEFT JOIN businesses b ON m.business_id = b.business_id
                WHERE COALESCE(m.status, 1) = 1
                  AND COALESCE(m.is_active, 1) = 1
                  AND COALESCE(m.original_cost, 0) > 0
                  AND COALESCE(m.original_cost, 0) > COALESCE(m.selling_price, 0)
            """
            if include_business_ids:
                sql += f" AND m.business_id IN ({biz_ph}) "
            else:
                sql += " AND EXISTS (SELECT 1 FROM businesses b2 WHERE b2.business_id = m.business_id AND b2.businessType = %s) "
                params.append(resolved_type)
            sql += " ORDER BY ((COALESCE(m.original_cost,0) - COALESCE(m.selling_price,0)) / NULLIF(COALESCE(m.original_cost,0),0)) DESC, COALESCE(m.updated_at, m.created_at) DESC "
            sql += " LIMIT %s OFFSET %s "
            params.extend([limit, offset])

        elif resolved_type == 'R01':
            sql = """
                SELECT
                    gp.product_id,
                    gp.business_id,
                    gp.product_name,
                    gp.main_image,
                    uc.category_name,
                    gp.sub_category,
                    COALESCE(gpv.original_cost, 0),
                    COALESCE(gpv.selling_price, 0),
                    COALESCE(gp.updated_at, gp.created_at),
                    b.businessName as business_name
                FROM Groceries_Products gp
                LEFT JOIN universal_Categories uc ON gp.category_id = uc.category_id
                JOIN Groceries_ProductVariants_1 gpv ON gp.product_id = gpv.product_id AND COALESCE(gpv.is_active, 1) = 1
                LEFT JOIN businesses b ON gp.business_id = b.business_id
                WHERE COALESCE(gp.is_visible, 1) = 1
                  AND COALESCE(gpv.original_cost, 0) > 0
                  AND COALESCE(gpv.original_cost, 0) > COALESCE(gpv.selling_price, 0)
            """
            if include_business_ids:
                sql += f" AND gp.business_id IN ({biz_ph}) "
            else:
                sql += " AND EXISTS (SELECT 1 FROM businesses b2 WHERE b2.business_id = gp.business_id AND b2.businessType = %s) "
                params.append(resolved_type)
            sql += " ORDER BY ((COALESCE(gpv.original_cost,0) - COALESCE(gpv.selling_price,0)) / NULLIF(COALESCE(gpv.original_cost,0),0)) DESC, COALESCE(gp.updated_at, gp.created_at) DESC "
            sql += " LIMIT %s OFFSET %s "
            params.extend([limit, offset])

        elif resolved_type == 'R08':
            sql = """
                SELECT
                    fp.product_id,
                    fp.business_id,
                    fp.name,
                    fp.main_image,
                    uc.category_name,
                    fp.subcategory_id,
                    COALESCE(fpv.original_cost, 0),
                    COALESCE(fpv.selling_price, 0),
                    COALESCE(fp.created_at, fp.updated_at, fpv.created_at, fpv.updated_at),
                    b.businessName as business_name
                FROM fashion_products fp
                LEFT JOIN universal_Categories uc ON fp.category_id = uc.category_id
                JOIN fashion_product_variants fpv ON fpv.product_id = fp.product_id AND COALESCE(fpv.is_active, 1) = 1
                LEFT JOIN businesses b ON fp.business_id = b.business_id
                WHERE COALESCE(fp.is_active, 1) = 1
                  AND COALESCE(fpv.original_cost, 0) > 0
                  AND COALESCE(fpv.original_cost, 0) > COALESCE(fpv.selling_price, 0)
            """
            if include_business_ids:
                sql += f" AND fp.business_id IN ({biz_ph}) "
            else:
                sql += " AND EXISTS (SELECT 1 FROM businesses b2 WHERE b2.business_id = fp.business_id AND b2.businessType = %s) "
                params.append(resolved_type)
            sql += " ORDER BY ((COALESCE(fpv.original_cost,0) - COALESCE(fpv.selling_price,0)) / NULLIF(COALESCE(fpv.original_cost,0),0)) DESC, COALESCE(fp.created_at, fp.updated_at, fpv.created_at, fpv.updated_at) DESC "
            sql += " LIMIT %s OFFSET %s "
            params.extend([limit, offset])
        else:
            return Response({"error": f"Unsupported business type: {resolved_type}. Expected R01, R02, or R08"}, status=status.HTTP_400_BAD_REQUEST)

        with connection.cursor() as cursor:
            cursor.execute(sql, params)
            rows = cursor.fetchall()

        items = []
        for r in rows:
            original_cost = float(r[6]) if r[6] is not None else 0.0
            selling_price = float(r[7]) if r[7] is not None else 0.0
            diff_amount = max(0.0, original_cost - selling_price)
            percent_display = 0
            if original_cost and diff_amount > 0:
                try:
                    percent_display = int(round((diff_amount / original_cost) * 100))
                except Exception:
                    percent_display = 0

            created_at = _dt_to_iso(r[8])

            biz_type_for_item = resolved_type
            if resolved_type == 'ALL' and len(r) > 9:
                biz_type_for_item = r[9]

            items.append({
                'item_id': r[0],
                'business_id': r[1],
                'business_name': r[9] if len(r) > 9 else None,
                'item_name': r[2],
                'item_image': _abs_item_image(request, r[3]),
                'item_category': standardize_category_name(r[4]) if r[4] else None,
                'item_type': r[5],
                'business_type': biz_type_for_item,
                'original_cost': original_cost,
                'selling_price': selling_price,
                'created_at': created_at,
                'diff_amount': f"{diff_amount:.2f}",
                'percent_display': percent_display,
                'discount_percentage': percent_display,
                'badge_text': (f"{percent_display}% off" if percent_display > 10 else (f"₹{int(round(diff_amount))} off" if diff_amount > 0 else None)),
            })

        return Response({
            'success': True,
            'business_type': resolved_type,
            'business_name': display_name,
            'limit': limit,
            'offset': offset,
            'count': len(items),
            'items': items,
        }, status=status.HTTP_200_OK)

    except Exception as e:
        return Response({"success": False, "message": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@swagger_auto_schema(methods=['GET'],tags=['Consumer'])
@api_view(['GET'])
def featured_products(request):
    business_type = (request.query_params.get('business_type') or request.query_params.get('type') or '').strip() or None
    business_id = request.query_params.get('business_id')
    limit = min(_parse_int(request.query_params.get('limit', 20), 20) or 20, 50)
    offset = max(_parse_int(request.query_params.get('offset', 0), 0) or 0, 0)
    min_rating = request.query_params.get('min_rating')
    try:
        min_rating = float(min_rating) if min_rating is not None and str(min_rating).strip() != '' else None
    except Exception:
        min_rating = None

    if not business_id and not business_type:
        resolved_type = 'ALL'
        display_name = 'All Businesses'
        include_business_ids = None
    else:
        resolved_type, display_name, include_business_ids, err = _resolve_scope(request, business_id, business_type)
        if err:
            return err

    try:
        params = []
        if include_business_ids:
            biz_ph = ','.join(['%s'] * len(include_business_ids))
            params.extend(include_business_ids)

        if resolved_type == 'ALL':
            params = []

            sql_r02 = """
                SELECT
                    m.item_id AS item_id,
                    m.business_id AS business_id,
                    m.item_name AS item_name,
                    m.item_image AS item_image,
                    NULL AS sub_images,
                    m.is_featured AS is_featured,
                    m.item_category AS item_category,
                    m.item_type AS item_type,
                    COALESCE(m.original_cost, 0) AS original_cost,
                    COALESCE(m.selling_price, 0) AS selling_price,
                    COALESCE(m.rating, 4.0) AS rating,
                    COALESCE(m.updated_at, m.created_at) AS sort_dt,
                    'R02' AS business_type
                FROM menuItems m
                WHERE COALESCE(m.status, 1) = 1
                  AND COALESCE(m.is_active, 1) = 1
            """
            if min_rating is not None:
                sql_r02 += " AND COALESCE(m.rating, 0) >= %s "
                params.append(min_rating)

            sql_r01 = """
                SELECT
                    gp.product_id AS item_id,
                    gp.business_id AS business_id,
                    gp.product_name AS item_name,
                    gp.main_image AS item_image,
                    gp.sub_images AS sub_images,
                    gp.is_featured AS is_featured,
                    uc.category_name AS item_category,
                    gp.sub_category AS item_type,
                    COALESCE(gpv.original_cost, 0) AS original_cost,
                    COALESCE(gpv.selling_price, 0) AS selling_price,
                    COALESCE(gp.rating, 4.0) AS rating,
                    COALESCE(gp.updated_at, gp.created_at) AS sort_dt,
                    'R01' AS business_type
                FROM Groceries_Products gp
                LEFT JOIN universal_Categories uc ON gp.category_id = uc.category_id
                LEFT JOIN Groceries_ProductVariants_1 gpv ON gp.product_id = gpv.product_id AND COALESCE(gpv.is_active, 1) = 1
                WHERE COALESCE(gp.is_visible, 1) = 1
            """
            if min_rating is not None:
                sql_r01 += " AND COALESCE(gp.rating, 0) >= %s "
                params.append(min_rating)

            sql_r08 = """
                SELECT
                    fp.product_id AS item_id,
                    fp.business_id AS business_id,
                    fp.name AS item_name,
                    fp.main_image AS item_image,
                    fp.sub_images AS sub_images,
                    fp.is_featured AS is_featured,
                    uc.category_name AS item_category,
                    fp.subcategory_id AS item_type,
                    COALESCE(fpv.original_cost, 0) AS original_cost,
                    COALESCE(fpv.selling_price, 0) AS selling_price,
                    COALESCE(fp.rating, 4.0) AS rating,
                    COALESCE(fp.created_at, fp.updated_at, fpv.created_at, fpv.updated_at) AS sort_dt,
                    'R08' AS business_type
                FROM fashion_products fp
                LEFT JOIN universal_Categories uc ON fp.category_id = uc.category_id
                LEFT JOIN fashion_product_variants fpv ON fpv.product_id = fp.product_id AND COALESCE(fpv.is_active, 1) = 1
                WHERE COALESCE(fp.is_active, 1) = 1
            """
            if min_rating is not None:
                sql_r08 += " AND COALESCE(fp.rating, 0) >= %s "
                params.append(min_rating)

            sql = f"""
                SELECT
                    item_id,
                    business_id,
                    item_name,
                    item_image,
                    sub_images,
                    is_featured,
                    item_category,
                    item_type,
                    original_cost,
                    selling_price,
                    rating,
                    sort_dt,
                    business_type
                FROM (
                    {sql_r02}
                    UNION ALL
                    {sql_r01}
                    UNION ALL
                    {sql_r08}
                ) u
                ORDER BY rating DESC, sort_dt DESC
                LIMIT %s OFFSET %s
            """
            params.extend([limit, offset])

        elif resolved_type == 'R02':
            sql = """
                SELECT
                    m.item_id,
                    m.business_id,
                    m.item_name,
                    m.item_image,
                    m.item_category,
                    m.item_type,
                    COALESCE(m.original_cost, 0),
                    COALESCE(m.selling_price, 0),
                    COALESCE(m.rating, 4.0) as rating,
                    m.is_featured,
                    COALESCE(m.updated_at, m.created_at),
                    b.businessName as business_name
                FROM menuItems m
                LEFT JOIN businesses b ON m.business_id = b.business_id
                WHERE COALESCE(m.status, 1) = 1
                  AND COALESCE(m.is_active, 1) = 1
            """
            if include_business_ids:
                sql += f" AND m.business_id IN ({biz_ph}) "
            else:
                sql += " AND EXISTS (SELECT 1 FROM businesses b2 WHERE b2.business_id = m.business_id AND b2.businessType = %s) "
                params.append(resolved_type)
            if min_rating is not None:
                sql += " AND COALESCE(m.rating, 0) >= %s "
                params.append(min_rating)
            sql += " ORDER BY COALESCE(m.rating, 0) DESC, COALESCE(m.updated_at, m.created_at) DESC "
            sql += " LIMIT %s OFFSET %s "
            params.extend([limit, offset])

        elif resolved_type == 'R01':
            sql = """
                SELECT
                    gp.product_id,
                    gp.business_id,
                    gp.product_name,
                    gp.main_image,
                    gp.sub_images,
                    gp.is_featured,
                    uc.category_name,
                    gp.sub_category,
                    COALESCE(gpv.original_cost, 0),
                    COALESCE(gpv.selling_price, 0),
                    COALESCE(gp.rating, 4.0) as rating,
                    COALESCE(gp.updated_at, gp.created_at),
                    b.businessName as business_name
                FROM Groceries_Products gp
                LEFT JOIN universal_Categories uc ON gp.category_id = uc.category_id
                LEFT JOIN Groceries_ProductVariants_1 gpv ON gp.product_id = gpv.product_id AND COALESCE(gpv.is_active, 1) = 1
                LEFT JOIN businesses b ON gp.business_id = b.business_id
                WHERE COALESCE(gp.is_visible, 1) = 1
            """
            if include_business_ids:
                sql += f" AND gp.business_id IN ({biz_ph}) "
            else:
                sql += " AND EXISTS (SELECT 1 FROM businesses b2 WHERE b2.business_id = gp.business_id AND b2.businessType = %s) "
                params.append(resolved_type)
            if min_rating is not None:
                sql += " AND COALESCE(gp.rating, 0) >= %s "
                params.append(min_rating)
            sql += " ORDER BY COALESCE(gp.rating, 0) DESC, COALESCE(gp.updated_at, gp.created_at) DESC "
            sql += " LIMIT %s OFFSET %s "
            params.extend([limit, offset])

        elif resolved_type == 'R08':
            sql = """
                SELECT
                    fp.product_id,
                    fp.business_id,
                    fp.name,
                    fp.main_image,
                    fp.sub_images,
                    fp.is_featured,
                    uc.category_name,
                    fp.subcategory_id,
                    COALESCE(fpv.original_cost, 0),
                    COALESCE(fpv.selling_price, 0),
                    COALESCE(fp.rating, 4.0) as rating,
                    COALESCE(fp.created_at, fp.updated_at, fpv.created_at, fpv.updated_at),
                    b.businessName as business_name
                FROM fashion_products fp
                LEFT JOIN universal_Categories uc ON fp.category_id = uc.category_id
                LEFT JOIN fashion_product_variants fpv ON fpv.product_id = fp.product_id AND COALESCE(fpv.is_active, 1) = 1
                LEFT JOIN businesses b ON fp.business_id = b.business_id
                WHERE COALESCE(fp.is_active, 1) = 1
            """
            if include_business_ids:
                sql += f" AND fp.business_id IN ({biz_ph}) "
            else:
                sql += " AND EXISTS (SELECT 1 FROM businesses b2 WHERE b2.business_id = fp.business_id AND b2.businessType = %s) "
                params.append(resolved_type)
            if min_rating is not None:
                sql += " AND COALESCE(fp.rating, 0) >= %s "
                params.append(min_rating)
            sql += " ORDER BY COALESCE(fp.rating, 0) DESC, COALESCE(fp.created_at, fp.updated_at, fpv.created_at, fpv.updated_at) DESC "
            sql += " LIMIT %s OFFSET %s "
            params.extend([limit, offset])
        else:
            return Response({"error": f"Unsupported business type: {resolved_type}. Expected R01, R02, or R08"}, status=status.HTTP_400_BAD_REQUEST)

        with connection.cursor() as cursor:
            cursor.execute(sql, params)
            rows = cursor.fetchall()

        items = []
        for r in rows:
            original_cost = float(r[6]) if r[6] is not None else 0.0
            selling_price = float(r[7]) if r[7] is not None else 0.0
            rating = float(r[8]) if r[8] is not None else 0.0
            diff_amount = max(0.0, original_cost - selling_price)
            percent_display = 0
            if original_cost and diff_amount > 0:
                try:
                    percent_display = int(round((diff_amount / original_cost) * 100))
                except Exception:
                    percent_display = 0

            created_at = _dt_to_iso(r[9])

            items.append({
                'item_id': r[0],
                'business_id': r[1],
                'business_name': r[12] if len(r) > 12 else None,
                'item_name': r[2],
                'item_image': _abs_item_image(request, r[3]),
                'sub_images': _process_sub_images_list(request, r[4] if len(r) > 10 else None),
                'is_featured': bool(r[5] if len(r) > 10 else r[9] if len(r) > 9 else False),
                'item_category': standardize_category_name(r[6] if len(r) > 10 else r[4]) if (r[6] if len(r) > 10 else r[4]) else None,
                'item_type': r[7] if len(r) > 10 else r[5],
                'business_type': (r[12] if (resolved_type == 'ALL' and len(r) > 12) else resolved_type),
                'original_cost': original_cost,
                'selling_price': selling_price,
                'rating': rating,
                'created_at': created_at,
                'diff_amount': f"{diff_amount:.2f}",
                'percent_display': percent_display,
                'discount_percentage': percent_display,
            })

        return Response({
            'success': True,
            'business_type': resolved_type,
            'business_name': display_name,
            'limit': limit,
            'offset': offset,
            'count': len(items),
            'items': items,
        }, status=status.HTTP_200_OK)

    except Exception as e:
        return Response({"success": False, "message": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@swagger_auto_schema(methods=['GET', 'POST'],tags=['Consumer'])
@api_view(['GET', 'POST'])
def menu_items_by_category(request):
    """
    Fetch items by category with business-type awareness
    URL: POST /consumer/menu-items?category=[value]&business_id=[value]&category_id=[value]&sub_category_id=[value]

    Behavior:
    - If business_id is R02 (Restaurant): return menuItems matching category (existing behavior)
    - If business_id is R01 (Grocery): resolve category -> category_id from Groceries_Categories,
      then return products from Groceries_Products for that category (parent + sub-businesses)
    """
    # Handle both GET and POST requests
    if request.method == 'GET':
        business_id = request.GET.get("business_id", None)
        category = request.GET.get("category", None)
        category_id = request.GET.get("category_id", None)
        sub_category_id = request.GET.get("sub_category_id", None)
    else:  # POST
        # Try to get from POST data first, fallback to GET parameters
        if request.data:
            business_id = request.data.get("business_id", None)
            category = request.data.get("category", None)
            category_id = request.data.get("category_id", None)
            sub_category_id = request.data.get("sub_category_id", None)
        else:
            # Fallback to GET parameters for POST requests with URL params
            business_id = request.GET.get("business_id", None)
            category = request.GET.get("category", None)
            category_id = request.GET.get("category_id", None)
            sub_category_id = request.GET.get("sub_category_id", None)
    
    # Validate that at least one filtering parameter is provided
    if not category and not category_id and not sub_category_id:
        return Response({
            "error": "Either category, category_id, or sub_category_id is required as query parameter"
        }, status=status.HTTP_400_BAD_REQUEST)
    
    try:
        if business_id:
            # Determine business type (include closed businesses for display)
            try:
                business = Business.objects.get(business_id=business_id)
            except Business.DoesNotExist:
                return Response({
                    "error": f"Business with ID {business_id} not found"
                }, status=status.HTTP_404_NOT_FOUND)

            if business.businessType == 'R08':
                from .combine import _service_items_r08_raw_sql, _parse_items_query_params
                
                # Create query parameters for the R08 service
                qp = {
                    'category_id': category_id,
                    'category': category,
                    'sub_category_id': sub_category_id,
                    'page': request.GET.get('page', 1),
                    'page_size': request.GET.get('page_size', 10),
                    'ordering': 'item_name'
                }
                
                # Use the R08 service to get grocery-style response with variants
                response = _service_items_r08_raw_sql(request, business, business_id, qp)
                
                # Update the response message to reflect the actual category
                if response.data.get('success'):
                    filter_display = category_id if category_id else category
                    filter_type = "category_id" if category_id else "category"
                    response.data['message'] = f"Found {response.data.get('total_items', 0)} fashion items in {filter_type} '{filter_display}'"
                    response.data['filters'] = {"business_id": business_id, filter_type: filter_display}
                
                return response

            if business.businessType == 'R01':
                from .combine import _service_items_r01, _parse_items_query_params
                
                # Create query parameters for the R01 service
                qp = {
                    'category_id': category_id,
                    'category': category,
                    'sub_category_id': sub_category_id,
                    'page': request.GET.get('page', 1),
                    'page_size': request.GET.get('page_size', 10),
                    'ordering': 'item_name'
                }
                
                # Use the R01 service to get grocery-style response with variants
                response = _service_items_r01(request, business, business_id, qp)
                
                # Update the response message to reflect the actual category
                if response.data.get('success'):
                    filter_display = category_id if category_id else category
                    filter_type = "category_id" if category_id else "category"
                    response.data['message'] = f"Found {response.data.get('total_items', 0)} grocery items in {filter_type} '{filter_display}'"
                    response.data['filters'] = {"business_id": business_id, filter_type: filter_display}
                
                return response

            # R02 (Restaurant) - Convert menu items to grocery-style format with variants
            # First, get the menu items using existing logic
            cat_conditions = []
            cat_params = []
            
            if category_id:
                # Direct category ID filtering - using item_category_id column for main categories
                try:
                    cat_id_int = int(str(category_id).strip())
                    cat_conditions.append("mi.item_category_id = %s")
                    cat_params.append(cat_id_int)
                except Exception:
                    return Response({
                        "error": f"Invalid category_id: {category_id}"
                    }, status=status.HTTP_400_BAD_REQUEST)
            elif sub_category_id:
                # Direct sub-category ID filtering - using sub_category_id column
                try:
                    sub_cat_id_int = int(str(sub_category_id).strip())
                    cat_conditions.append("mi.sub_category_id = %s")
                    cat_params.append(sub_cat_id_int)
                except Exception:
                    return Response({
                        "error": f"Invalid sub_category_id: {sub_category_id}"
                    }, status=status.HTTP_400_BAD_REQUEST)
            elif category:
                # Category name filtering (existing logic)
                cat_conditions.append("TRIM(mi.item_category) = TRIM(%s)")
                cat_params.append(category)
            
            cat_where = " AND ".join(cat_conditions) if cat_conditions else "1=1"
            
            # Get menu items from parent business and sub-businesses
            with connection.cursor() as cursor:
                cursor.execute("""
                    SELECT b.business_id
                    FROM businesses b
                    WHERE b.master = %s
                """, [business_id])
                sub_rows = cursor.fetchall()

            include_business_ids = [business_id] + [row[0] for row in sub_rows]
            biz_ph = ','.join(['%s'] * len(include_business_ids))
            
            # Get menu items with all required fields
            with connection.cursor() as cursor:
                cursor.execute(f"""
                    SELECT 
                        mi.item_id,
                        mi.item_name,
                        mi.description,
                        mi.item_image,
                        mi.item_category,
                        mi.item_type,
                        mi.selling_price,
                        mi.original_cost,
                        mi.gst,
                        mi.charges,
                        mi.size_label,
                        mi.quantity,
                        mi.status,
                        mi.is_active,
                        mi.created_at,
                        mi.updated_at,
                        mi.item_category_id,
                        mi.sub_category_id,
                        mi.business_id,
                        mi.rating,
                        uc.category_name as category_name,
                        uc_sub.category_name as sub_category_name,
                        uc.parent_category_id,
                        uc_parent.category_name as parent_category_name
                    FROM menuItems mi
                    LEFT JOIN universal_Categories uc ON mi.item_category_id = uc.category_id
                    LEFT JOIN universal_Categories uc_sub ON mi.sub_category_id = uc_sub.category_id
                    LEFT JOIN universal_Categories uc_parent ON uc.parent_category_id = uc_parent.category_id
                    WHERE mi.business_id IN ({biz_ph}) 
                      AND {cat_where}
                      AND mi.status = 1
                    ORDER BY mi.item_name
                """, include_business_ids + cat_params)
                rows = cursor.fetchall()

            # Convert menu items to grocery-style format with variants
            items = []
            
            # Get business-level availability context for response metadata
            # Create a default pseudo-item for business-level context
            class DefaultPseudoItem:
                pass
            default_pseudo_item = DefaultPseudoItem()
            default_pseudo_item.is_active = True
            default_pseudo_item.status = True
            default_pseudo_item.is_visible = 1
            default_pseudo_item.item_timings = None
            
            business_context = get_availability_context(business, default_pseudo_item)
            
            for r in rows:
                item_id = r[0]
                
                # Setup Parent Context for availability (Requirements 2, 3, 4, 6)
                # Create a pseudo-object to pass into the context checker
                class PseudoItem:
                    pass
                pseudo_item = PseudoItem()
                pseudo_item.is_active = bool(r[15])  # is_active index
                pseudo_item.status = bool(r[14]) if r[14] is not None else True  # status index
                pseudo_item.is_visible = 1
                pseudo_item.item_timings = None  # menu items don't have item-level timings
                
                parent_context = get_availability_context(business, pseudo_item)
                
                # Requirement 4: Hide Item completely if parent context is HIDDEN
                if parent_context['status'] == "HIDDEN":
                    continue
                
                # Fetch real variants from menu_item_variants table
                variants = []
                with connection.cursor() as cursor:
                    cursor.execute("""
                        SELECT 
                            variant_id,
                            size_label,
                            selling_price,
                            original_cost,
                            gst,
                            charges,
                            is_active,
                            created_at,
                            updated_at,
                            stock_qty,
                            sku,
                            rating,
                            rating_count
                        FROM menu_item_variants
                        WHERE item_id = %s
                        ORDER BY variant_id
                    """, [item_id])
                    variant_rows = cursor.fetchall()
                
                processed_variants = []
                for vr in variant_rows:
                    v_data = {
                        "variant_id": vr[0],
                        "size_label": vr[1],
                        "selling_price": float(vr[2]) if vr[2] else 0.0,
                        "original_cost": float(vr[3]) if vr[3] else 0.0,
                        "gst": float(vr[4]) if vr[4] else 0.0,
                        "charges": float(vr[5]) if vr[5] else 0.0,
                        "is_active": bool(vr[6]),
                        "created_at": vr[7].isoformat() if vr[7] and hasattr(vr[7], 'isoformat') else None,
                        "updated_at": vr[8].isoformat() if vr[8] and hasattr(vr[8], 'isoformat') else None,
                        "stock_qty": vr[9] if vr[9] is not None else 0,
                        "sku": vr[10] if vr[10] else f"{item_id}_{vr[1]}",
                        "rating": float(vr[11]) if vr[11] else 4.0,
                        "rating_count": int(vr[12]) if vr[12] else 0
                    }
                    
                    # Apply variant-level availability using Requirements 1, 3, 5, 6
                    v_avail = calculate_variant_availability(v_data, parent_context, business_type='R02')
                    v_data.update(v_avail)
                    
                    # Add stock message using availability_services
                    s_msg = get_stock_message(v_data['stock_qty'])
                    v_data['stock_message'] = s_msg['stock_message']
                    v_data['stock_status'] = s_msg['stock_status']
                    
                    processed_variants.append(v_data)
                
                # If no variants found, create one from parent item data as fallback
                if not processed_variants:
                    parent_is_active = bool(r[15])
                    v_data = {
                        "variant_id": item_id,
                        "sku": f"{item_id}_{r[11]}",
                        "selling_price": float(r[6]) if r[6] else 0.0,
                        "original_cost": float(r[7]) if r[7] else 0.0,
                        "charges": float(r[9]) if r[9] else 0.0,
                        "gst": float(r[8]) if r[8] else 0.0,
                        "is_active": parent_is_active,
                        "created_at": r[16].isoformat() if r[16] and hasattr(r[16], 'isoformat') else None,
                        "updated_at": r[17].isoformat() if r[17] and hasattr(r[17], 'isoformat') else None,
                        "size_label": r[11],
                        "stock_qty": r[12] if r[12] is not None else 0,
                        "mrp": float(r[7]) if r[7] else 0.0,
                        "rating": float(r[19]) if r[19] else 4.0,
                        "rating_count": 0
                    }
                    
                    # Apply variant-level availability for fallback variant
                    v_avail = calculate_variant_availability(v_data, parent_context, business_type='R02')
                    v_data.update(v_avail)
                    
                    # Add stock message
                    s_msg = get_stock_message(v_data['stock_qty'])
                    v_data['stock_message'] = s_msg['stock_message']
                    v_data['stock_status'] = s_msg['stock_status']
                    
                    processed_variants.append(v_data)
                
                # Calculate discount using first variant's prices
                first_variant = processed_variants[0] if processed_variants else None
                original_cost = first_variant['original_cost'] if first_variant else 0.0
                selling_price = first_variant['selling_price'] if first_variant else 0.0
                diff_amount = "0.00"
                percent = "0.0"
                percent_display = 0
                diff_display = 0
                discount_percentage = 0
                
                if original_cost > 0 and selling_price > 0:
                    diff = original_cost - selling_price
                    if diff > 0:
                        from decimal import Decimal, ROUND_HALF_UP
                        oc = Decimal(str(original_cost))
                        sp = Decimal(str(selling_price))
                        diff = oc - sp
                        percent = (diff / oc * Decimal(100))
                        percent_display = int(percent.quantize(Decimal('1'), rounding=ROUND_HALF_UP))
                        diff_display = int(diff.quantize(Decimal('1'), rounding=ROUND_HALF_UP))
                        diff_amount = str(diff.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP))
                        percent = str(percent.quantize(Decimal('0.1'), rounding=ROUND_HALF_UP))
                        discount_percentage = percent_display

                # Build item in grocery format with availability from parent context
                item_dict = {
                    "item_id": r[0],
                    "item_name": r[1],
                    "description": r[2],
                    "media": _build_media_response(request, r[3], []),
                    "item_category": r[4],
                    "parent_category_id": r[22],
                    "parent_category_name": r[23],
                    "item_type": r[5],
                    "selling_price": float(r[6]) if r[6] else 0.0,
                    "original_cost": float(r[7]) if r[7] else 0.0,
                    "gst": str(r[8]) if r[8] else "0",
                    "charges": float(r[9]) if r[9] else 0,
                    "stock": r[12] if r[12] is not None else 0,
                    "is_active": bool(r[15]),
                    "status": bool(r[14]) if r[14] is not None else True,
                    "rating": float(r[19]) if r[19] else 4.0,
                    "item_placed_at": "",
                    "rating_count": 0,
                    "variants": processed_variants,
                    "diff_amount": diff_amount,
                    "percent": percent,
                    "percent_display": percent_display,
                    "diff_display": diff_display,
                    "badge_text": None,
                    "badge_type": None,
                    "is_featured_offer": False,
                    "discount_percentage": discount_percentage,
                    # Requirement 3: Inherit Scheduling/Availability from context
                    "can_add_to_cart": parent_context['can_add'] if any(v.get('can_add_to_cart', False) for v in processed_variants) else False,
                    "availability_status": parent_context['status'],
                    "availability_message": parent_context['message'],
                    "is_business_open": parent_context['is_open']
                }
                
                items.append(item_dict)

            # Apply pagination
            page = int(request.GET.get('page', 1))
            page_size = int(request.GET.get('page_size', 10))
            start = (page - 1) * page_size
            end = start + page_size
            paginated_items = items[start:end]

            filter_display = category_id if category_id else category
            filter_type = "category_id" if category_id else "category"

            return Response({
                "success": True,
                "items": paginated_items,
                "total_items": len(items),
                "filters": {"business_id": business_id, filter_type: filter_display},
                "is_business_open": business_context['is_open'],
                "availability_status": business_context['status'],
                "availability_message": business_context['message'],
                "can_add_to_cart": business_context['can_add'],
                "message": f"Found {len(items)} menu items in {filter_type} '{filter_display}'"
            }, status=status.HTTP_200_OK)

        # No business_id provided: keep existing behavior (R02/global)
            # Build category filtering logic for global R02 query
            cat_conditions = []
            cat_params = []
            
            if category_id:
                # Direct category ID filtering - using item_category_id column for main categories
                try:
                    cat_id_int = int(str(category_id).strip())
                    cat_conditions.append("item_category_id = %s")
                    cat_params.append(cat_id_int)
                except Exception:
                    return Response({
                        "error": f"Invalid category_id: {category_id}"
                    }, status=status.HTTP_400_BAD_REQUEST)
            elif sub_category_id:
                # Direct sub-category ID filtering - using sub_category_id column
                try:
                    sub_cat_id_int = int(str(sub_category_id).strip())
                    cat_conditions.append("sub_category_id = %s")
                    cat_params.append(sub_cat_id_int)
                except Exception:
                    return Response({
                        "error": f"Invalid sub_category_id: {sub_category_id}"
                    }, status=status.HTTP_400_BAD_REQUEST)
            elif category:
                # Category name filtering (existing logic)
                cat_conditions.append("TRIM(item_category) = TRIM(%s)")
                cat_params.append(category)
            
            cat_where = " AND ".join(cat_conditions) if cat_conditions else "1=1"
            
            query = f"""
                SELECT * FROM menuItems 
                WHERE {cat_where} AND status = 1
                ORDER BY item_name
            """
            menu_items = list(MenuItems.objects.raw(query, cat_params))

            # Determine which filter was applied for response message
            filter_display = category_id if category_id else category
            filter_type = "category_id" if category_id else "category"

            serializer = MenuItemsSerializer(menu_items, many=True, context={'request': request})
            return Response({
                "success": True,
                "items": serializer.data,
                "total_items": len(serializer.data),
                "filters": {"business_id": business_id, filter_type: filter_display},
                "is_business_open": True,  # Default to True for global queries
                "message": f"Found {len(serializer.data)} menu items in {filter_type} '{filter_display}'"
            }, status=status.HTTP_200_OK)
        
    except Exception as e:
        return Response({
            "error": "An error occurred while fetching menu items",
            "details": str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@swagger_auto_schema(methods=['GET'],tags=['Consumer'])
@api_view(['GET'])
def product_items_by_category(request):
    """
    Fetch product items with category filtering
    URL: GET /consumer/product-items?category=[value]&business_id=[value]&category_id=[value]&sub_category_id=[value]
    
    When user mentions category, display the items accordingly
    Supports both category name (category) and category ID (category_id) filtering
    Also supports sub_category_id for subcategory filtering
    """
    # Simplified parameter extraction - just use request.GET since it's a GET request
    business_id = request.GET.get("business_id")
    category = request.GET.get("category") 
    category_id = request.GET.get("category_id")
    sub_category_id = request.GET.get("sub_category_id")
    
    # Validate that at least one filtering parameter is provided
    if not category and not category_id and not sub_category_id:
        return Response({
            "error": "At least one of category, category_id, or sub_category_id is required as query parameter"
        }, status=status.HTTP_400_BAD_REQUEST)
    
    try:
        business = None
        business_type = None
        if business_id:
            business = Business.objects.filter(business_id=business_id).first()
            business_type = getattr(business, 'businessType', None) if business else None

        if business_id and business is None:
            return Response({
                "error": f"Business with ID {business_id} not found"
            }, status=status.HTTP_404_NOT_FOUND)

        if business_type == 'R01':
            # Use the same grocery-style format with variants as menu_items_by_category
            from .combine import _service_items_r01, _parse_items_query_params
            
            # Create query parameters for the R01 service
            qp = {
                'category_id': category_id,
                'category': category,
                'sub_category_id': sub_category_id,
                'page': request.GET.get('page', 1),
                'page_size': request.GET.get('page_size', 10),
                'ordering': 'item_name'
            }
            
            # Use the R01 service to get grocery-style response with variants
            response = _service_items_r01(request, business, business_id, qp)
            
            # Update the response message to reflect the actual category
            if response.data.get('success'):
                filter_display = category_id if category_id else category
                filter_type = "category_id" if category_id else "category"
                response.data['message'] = f"Found {response.data.get('total_items', 0)} products in {filter_type} '{filter_display}'"
                response.data['filters'] = {"business_id": business_id, filter_type: filter_display}
            
            return response

        if business_type == 'R08':
            # Use the same grocery-style format with variants as menu_items_by_category
            from .combine import _service_items_r08_raw_sql, _parse_items_query_params
            
            # Create query parameters for the R08 service
            qp = {
                'category_id': category_id,
                'category': category,
                'sub_category_id': sub_category_id,
                'page': request.GET.get('page', 1),
                'page_size': request.GET.get('page_size', 10),
                'ordering': 'item_name'
            }
            
            # Use the R08 service to get grocery-style response with variants
            response = _service_items_r08_raw_sql(request, business, business_id, qp)
            
            # Update the response message to reflect the actual category
            if response.data.get('success'):
                filter_display = category_id if category_id else category
                filter_type = "category_id" if category_id else "category"
                response.data['message'] = f"Found {response.data.get('total_items', 0)} fashion items in {filter_type} '{filter_display}'"
                response.data['filters'] = {"business_id": business_id, filter_type: filter_display}
            
            return response

        if business_id and category:
            # First, try to get items from the parent business
            query = """
                SELECT * FROM GroceryItems 
                WHERE business_id = %s AND item_category = %s AND status = 1
                ORDER BY item_name
            """
            product_items = list(productItems.objects.raw(query, [business_id, category]))
            
            # If no items found in parent business, check sub-level businesses
            if not product_items:
                query = """
                    SELECT g.* FROM GroceryItems g
                    JOIN businesses b ON g.business_id = b.business_id
                    WHERE b.master = %s AND g.item_category = %s 
                    AND g.status = 1 AND b.status = 1
                    ORDER BY g.item_name
                """
                product_items = list(productItems.objects.raw(query, [business_id, category]))
                
        elif category:
            # Filter by category only (all businesses)
            query = """
                SELECT * FROM GroceryItems 
                WHERE item_category = %s AND status = 1
                ORDER BY item_name
            """
            product_items = list(productItems.objects.raw(query, [category]))
        else:
            return Response({
                "error": "Invalid parameters"
            }, status=status.HTTP_400_BAD_REQUEST)

        serializer = productItemsSerializer(product_items, many=True, context={'request': request})
        
        response_data = {
            "success": True,
            "items": serializer.data,
            "total_items": len(serializer.data),
            "filters": {
                "business_id": business_id,
                "category": category
            },
            "message": f"Found {len(serializer.data)} product items in category '{category}'"
        }
        
        return Response(response_data, status=status.HTTP_200_OK)
        
    except Exception as e:
        return Response({
            "error": "An error occurred while fetching product items",
            "details": str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@swagger_auto_schema(methods=['GET'],tags=['Consumer'])
@api_view(['GET'])
def item_designs(request):
    """
    List active customizable designs for a grocery product (R01).
    URL: GET /consumer/item-designs/?item_id=<product_id>&business_id=<business_id>

    Returns designs only when the product exists and is marked is_customizable=1.
    """
    product_id = request.query_params.get('item_id')
    business_id = request.query_params.get('business_id')

    if not product_id or not business_id:
        return Response({
            "success": False,
            "error": "item_id and business_id are required as query parameters"
        }, status=status.HTTP_400_BAD_REQUEST)

    try:
        # Verify product exists and is customizable
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT gp.product_id, gp.is_customizable
                FROM Groceries_Products gp
                WHERE gp.product_id = %s AND gp.business_id = %s
                LIMIT 1
                """,
                [product_id, business_id]
            )
            row = cursor.fetchone()

        if not row:
            return Response({
                "success": False,
                "error": "Product not found for the given business_id"
            }, status=status.HTTP_404_NOT_FOUND)

        is_customizable = bool(row[1]) if row[1] is not None else False
        if not is_customizable:
            return Response({
                "success": True,
                "product_id": int(row[0]),
                "is_customizable": False,
                "designs": [],
                "message": "This product is not customizable"
            }, status=status.HTTP_200_OK)

        # Fetch active designs
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT 
                    id, name, design_type, price_delta, asset_url,
                    max_chars, per_char_price, flat_price, base_price,
                    is_active, position
                FROM Groceries_CustomDesigns
                WHERE product_id = %s AND business_id = %s AND is_active = 1
                ORDER BY position ASC, id ASC
                """,
                [product_id, business_id]
            )
            rows = cursor.fetchall()

        designs = []
        for r in rows:
            designs.append({
                "id": int(r[0]),
                "name": r[1],
                "design_type": r[2],
                "price_delta": float(r[3]) if r[3] is not None else 0.0,
                "asset_url": r[4],
                "max_chars": int(r[5]) if r[5] is not None else None,
                "per_char_price": float(r[6]) if r[6] is not None else None,
                "flat_price": float(r[7]) if r[7] is not None else None,
                "base_price": float(r[8]) if r[8] is not None else None,
                "is_active": bool(r[9]) if r[9] is not None else True,
                "position": int(r[10]) if r[10] is not None else 0,
            })

        return Response({
            "success": True,
            "product_id": int(product_id),
            "business_id": str(business_id),
            "is_customizable": True,
            "designs": designs,
            "total": len(designs)
        }, status=status.HTTP_200_OK)

    except Exception as e:
        return Response({
            "success": False,
            "error": str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
