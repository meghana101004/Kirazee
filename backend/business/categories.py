# categories.py
# views.py
from requests import api
from rest_framework.decorators import api_view, parser_classes, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework import status
from rest_framework.response import Response
from rest_framework.parsers import MultiPartParser, FormParser, JSONParser
from rest_framework.views import APIView
from drf_yasg.utils import swagger_auto_schema
from kirazee_app.models import BusinessType, BusinessFeature, Business, BusinessMapping, Registration, BusinessOwnerDetails, BusinessFinancial
from .serializers import (
    BusinessTypeSerializer, BusinessFeatureSerializer, 
    Businesssection1serializers, Businesssection2Serializer, 
    Businesssection3Serializer, BusinessFinancialDetailSerializer,
    MenuItemsSerializer, BOMSerializer, productItemsSerializer,
    GroceriesCategorySerializer, CountryandStatesSerializer,
    )
from consumer.gro_serializers import (
    GroceriesProductsSerializer,
    GroceriesProductVariantsSerializer,
    GroceriesProductWithPricingSerializer,
)
from consumer.gro_models import (
    GroceriesProducts,
    GroceriesCategories,
    GroceriesProductVariants,
)
from .models import MenuItems, BOM, BillOfMaterialsLog, productItems, BusinessApplication, ApplicationStep, CountryandStates
import json
import re
from .google_maps import parse_google_maps_url
from PIL import Image
from io import BytesIO
from django.core.files import File
from django.conf import settings
import os
import time
import csv
import io
from decimal import Decimal
from django.db import connection
from django.db.models import Q
from django.db import transaction
from consumer.gro_views import GroceriesBulkUploadView
from business.image_utils import build_s3_file_url, upload_image_to_s3
from django.db.models import Count, Value
from django.db.models.functions import Coalesce

_UC_BUSINESS_TYPE_COL = None

def _uc_business_type_column():
    global _UC_BUSINESS_TYPE_COL
    if _UC_BUSINESS_TYPE_COL is not None:
        return _UC_BUSINESS_TYPE_COL
    candidates = [
        'business_type',
        'business_type_code',
        'businessType',
        'type_code',
        'category_type',
        'category_type_code',
    ]
    try:
        with connection.cursor() as cursor:
            cursor.execute("SHOW COLUMNS FROM universal_Categories")
            cols = [r[0] for r in cursor.fetchall()]
        for c in candidates:
            if c in cols:
                _UC_BUSINESS_TYPE_COL = c
                return _UC_BUSINESS_TYPE_COL
        _UC_BUSINESS_TYPE_COL = ''
        return None
    except Exception:
        _UC_BUSINESS_TYPE_COL = ''
        return None

def _uc_category_cols():
    cols = ["category_id", "category_name", "category_image", "parent_category_id"]
    bt_col = _uc_business_type_column()
    if bt_col:
        cols.append('business_type')
    return cols

def _uc_select_sql():
    bt_col = _uc_business_type_column()
    cols = ["category_id", "category_name", "category_image", "parent_category_id"]
    safe_cols = []
    for c in cols:
        if not re.match(r'^[A-Za-z0-9_]+$', str(c)):
            continue
        safe_cols.append(f"`{c}`")
    if bt_col and re.match(r'^[A-Za-z0-9_]+$', str(bt_col)):
        safe_cols.append(f"`{bt_col}` AS `business_type`")
    return "SELECT " + ", ".join(safe_cols)

def _uc_apply_business_type_filter(base, params, business_type):
    if not business_type:
        return None
    bt_col = _uc_business_type_column()
    if not bt_col or not re.match(r'^[A-Za-z0-9_]+$', str(bt_col)):
        return {"error": "business_type filtering is not configured"}

    bt_val = str(business_type).strip().upper()
    base.append(f"AND (`{bt_col}` = %s OR FIND_IN_SET(%s, REPLACE(`{bt_col}`, ' ', '')) > 0)")
    params.extend([bt_val, bt_val])
    return None

@swagger_auto_schema(methods=['GET'], tags=['Business'])
@api_view(['GET'])
def list_universal_categories(request):
    """
    List universal categories for selection by business owners.
    Query params:
      - search (optional): substring match on category_name
      - parent_category_id (optional): filter by parent id
      - business_type (optional): filter categories by BusinessType.categories (ids or names)
      - limit (optional, default=100)
      - offset (optional, default=0)
    """
    try:
        search = request.query_params.get('search')
        parent_id = request.query_params.get('parent_category_id') or request.query_params.get('parent_id')
        business_type = request.query_params.get('business_type')
        try:
            limit = int(request.query_params.get('limit', 100))
            offset = int(request.query_params.get('offset', 0))
        except ValueError:
            return Response({"error": "Invalid limit or offset"}, status=status.HTTP_400_BAD_REQUEST)

        base = [
            _uc_select_sql(),
            "FROM universal_Categories",
            "WHERE 1=1",
        ]
        params = []

        # Optional filter by configured BusinessType categories
        filter_err = _uc_apply_business_type_filter(base, params, business_type)
        if filter_err:
            return Response(filter_err, status=status.HTTP_400_BAD_REQUEST)

        if search:
            base.append("AND category_name LIKE %s")
            params.append(f"%{search}%")
        if parent_id not in (None, ""):
            base.append("AND parent_category_id = %s")
            params.append(parent_id)

        base.append("ORDER BY category_name ASC")
        base.append("LIMIT %s OFFSET %s")
        params.extend([limit, offset])

        query = "\n".join(base)
        with connection.cursor() as cursor:
            cursor.execute(query, params)
            rows = cursor.fetchall()
            cols = _uc_category_cols()
            categories = [dict(zip(cols, r)) for r in rows]

        return Response({
            "categories": categories,
            "count": len(categories)
        }, status=status.HTTP_200_OK)
    except Exception as e:
        return Response({"error": "Failed to list universal categories", "details": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

@swagger_auto_schema(methods=['GET'], tags=['Business'])
@api_view(['GET'])
def list_universal_categories_tree(request):
    try:
        search = request.query_params.get('search')
        business_type = request.query_params.get('business_type')

        base = [
            _uc_select_sql(),
            "FROM universal_Categories",
            "WHERE 1=1",
        ]
        params = []

        filter_err = _uc_apply_business_type_filter(base, params, business_type)
        if filter_err:
            return Response(filter_err, status=status.HTTP_400_BAD_REQUEST)

        if search:
            base.append("AND category_name LIKE %s")
            params.append(f"%{search}%")

        base.append("ORDER BY category_name ASC")
        query = "\n".join(base)

        with connection.cursor() as cursor:
            cursor.execute(query, params)
            rows = cursor.fetchall()

        cols = _uc_category_cols()
        nodes = [dict(zip(cols, r)) for r in rows]

        by_id = {}
        for n in nodes:
            n['subcategories'] = []
            by_id[int(n['category_id'])] = n

        roots = []
        for n in nodes:
            pid = n.get('parent_category_id')
            if pid is None:
                roots.append(n)
                continue
            parent = by_id.get(int(pid)) if str(pid).isdigit() else None
            if parent is None:
                roots.append(n)
            else:
                parent['subcategories'].append(n)

        return Response({
            'categories': roots,
            'count': len(roots),
        }, status=status.HTTP_200_OK)
    except Exception as e:
        return Response({"error": "Failed to list universal categories", "details": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

@swagger_auto_schema(methods=['POST'], tags=['Business'])
@api_view(['POST'])
@parser_classes([MultiPartParser, FormParser, JSONParser])
@permission_classes([AllowAny])
def create_universal_category(request):
    try:
        # DEBUG: Log incoming files
        print(f"[DEBUG] request.FILES: {request.FILES}")
        print(f"[DEBUG] request.data keys: {list(request.data.keys())}")
        
        # Create a mutable copy of request data, excluding file objects
        from django.http import QueryDict
        if isinstance(request.data, QueryDict):
            # Manual copy to avoid pickle issues with file uploads
            data = QueryDict(mutable=True)
            for key, value_list in request.data.lists():
                if not hasattr(value_list[0] if value_list else None, 'read'):  # Exclude file fields
                    data.setlist(key, value_list)
        else:
            # For non-QueryDict, filter out file objects
            data = {}
            for key, value in request.data.items():
                if not hasattr(value, 'read'):  # Exclude file objects
                    data[key] = value
        data['_request'] = request  # Store request reference for later use
        name = (data.get('category_name') or '').strip()
        image = data.get('category_image')
        parent_raw = data.get('parent_category_id')
        bt_val = data.get('business_type')

        print(f"[DEBUG] category_name: {name}")
        print(f"[DEBUG] image type: {type(image)}")
        print(f"[DEBUG] image has read: {hasattr(image, 'read') if image else 'None'}")

        if not name:
            return Response({"error": "category_name is required"}, status=status.HTTP_400_BAD_REQUEST)

        # Handle image file upload
        if image and hasattr(image, 'read'):
            try:
                # Use UUID for secure filename generation
                print(f"[DEBUG] Original filename: {getattr(image, 'name', 'unknown')}")
                
                # Upload to S3 using helper with UUID
                saved_path = upload_image_to_s3(
                    image,
                    folder='category_images',
                    compress=True,
                    use_uuid=True  # Generates secure UUID filename
                )
                
                if saved_path:
                    image = build_s3_file_url(saved_path)
                    print(f"[DEBUG] S3 saved path: {saved_path}")
                    print(f"[DEBUG] S3 URL: {image}")
                else:
                    return Response({"error": "Failed to upload image to S3"}, status=status.HTTP_400_BAD_REQUEST)
                
            except Exception as e:
                return Response({"error": f"Failed to save image: {str(e)}"}, status=status.HTTP_400_BAD_REQUEST)

        parent_id = None
        if parent_raw not in (None, ''):
            try:
                parent_id = int(parent_raw)
            except Exception:
                return Response({"error": "parent_category_id must be an integer"}, status=status.HTTP_400_BAD_REQUEST)

        if parent_id is not None:
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1 FROM universal_Categories WHERE category_id = %s", [parent_id])
                if cursor.fetchone() is None:
                    return Response({"error": "parent_category_id not found"}, status=status.HTTP_400_BAD_REQUEST)

        bt_col = _uc_business_type_column()
        if bt_val in (None, ''):
            bt_val = None
        if bt_val is not None and not bt_col:
            return Response({"error": "business_type column not found in universal_Categories"}, status=status.HTTP_400_BAD_REQUEST)

        insert_cols = ["category_name", "category_image", "parent_category_id"]
        insert_params = [name, image, parent_id]
        if bt_col and bt_val is not None and re.match(r'^[A-Za-z0-9_]+$', str(bt_col)):
            insert_cols.append(bt_col)
            insert_params.append(str(bt_val).strip().upper())

        placeholders = ", ".join(["%s"] * len(insert_cols))
        col_sql = ", ".join([f"`{c}`" for c in insert_cols])
        with connection.cursor() as cursor:
            cursor.execute(
                f"INSERT INTO universal_Categories ({col_sql}, `created_at`, `updated_at`) VALUES ({placeholders}, NOW(), NOW())",
                insert_params
            )
            cursor.execute("SELECT LAST_INSERT_ID()")
            new_id = cursor.fetchone()[0]

        # If we uploaded a file with temporary name, rename it to use the actual category ID
        original_request = data.get('_request')  # Store request reference if available
        if image and isinstance(image, str) and "category_temp_" in image:
            try:
                # Extract the temporary filename
                temp_filename = image.split("/")[-1]
                file_extension = os.path.splitext(temp_filename)[1]
                new_filename = f"category_{new_id}{file_extension}"
                
                # Rename the file
                old_path = os.path.join(settings.MEDIA_ROOT, 'category_images', temp_filename)
                new_path = os.path.join(settings.MEDIA_ROOT, 'category_images', new_filename)
                
                if os.path.exists(old_path):
                    os.rename(old_path, new_path)
                    
                    # Update the database with the new filename using S3 URL
                    if original_request:
                        new_image_url = build_s3_file_url(f"category_images/{new_filename}")
                    else:
                        new_image_url = build_s3_file_url(f"category_images/{new_filename}")
                    
                    with connection.cursor() as cursor:
                        cursor.execute("UPDATE universal_Categories SET category_image = %s WHERE category_id = %s", 
                                     [new_image_url, new_id])
                    
            except Exception as e:
                # If renaming fails, continue with the temporary filename
                pass

        category = _uc_fetch_category(int(new_id))
        if not category:
            return Response({"error": "Failed to fetch created category"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        return Response({"category": category}, status=status.HTTP_201_CREATED)
    except Exception as e:
        return Response({"error": "Failed to create category", "details": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


def _uc_fetch_category(category_id: int):
    with connection.cursor() as cursor:
        cursor.execute(
            _uc_select_sql() + " FROM universal_Categories WHERE category_id = %s LIMIT 1",
            [category_id]
        )
        row = cursor.fetchone()
    if not row:
        return None
    cols = _uc_category_cols()
    return dict(zip(cols, row))

@swagger_auto_schema(method='GET', tags=['Business'])
@api_view(['GET'])
def universal_category_detail(request, category_id: int):
    try:
        category = _uc_fetch_category(int(category_id))
        if not category:
            return Response({"error": "Category not found"}, status=status.HTTP_404_NOT_FOUND)

        return Response({"category": category}, status=status.HTTP_200_OK)
    except Exception as e:
        return Response({"error": "Failed to fetch category", "details": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

@swagger_auto_schema(methods=['PUT', 'PATCH'], tags=['Business'])
@api_view(['PUT', 'PATCH'])
@parser_classes([MultiPartParser, FormParser, JSONParser])
@permission_classes([AllowAny])
def update_universal_category(request, category_id: int):
    try:
        # DEBUG: Log incoming files
        print(f"[DEBUG] request.FILES: {request.FILES}")
        print(f"[DEBUG] request.data keys: {list(request.data.keys())}")
        
        data = request.data or {}
        fields = []
        params = []

        if 'category_name' in data:
            name = (data.get('category_name') or '').strip()
            if not name:
                return Response({"error": "category_name cannot be empty"}, status=status.HTTP_400_BAD_REQUEST)
            fields.append("category_name = %s")
            params.append(name)

        if 'category_image' in data:
            image_file = data.get('category_image')
            if image_file and hasattr(image_file, 'read'):
                # Handle file upload
                try:
                    print(f"[DEBUG] Update - Original filename: {getattr(image_file, 'name', 'unknown')}")
                    
                    # Upload to S3 using helper with UUID
                    saved_path = upload_image_to_s3(
                        image_file,
                        folder='category_images',
                        compress=True,
                        use_uuid=True  # Generates secure UUID filename
                    )
                    
                    if saved_path:
                        image_url = build_s3_file_url(saved_path)
                        fields.append("category_image = %s")
                        params.append(image_url)
                        print(f"[DEBUG] Update - S3 saved path: {saved_path}")
                        print(f"[DEBUG] Update - S3 URL: {image_url}")
                    else:
                        return Response({"error": "Failed to upload image to S3"}, status=status.HTTP_400_BAD_REQUEST)
                    
                except Exception as e:
                    return Response({"error": f"Failed to save image: {str(e)}"}, status=status.HTTP_400_BAD_REQUEST)
            else:
                # Handle URL string or null
                fields.append("category_image = %s")
                params.append(image_file)

        if 'parent_category_id' in data:
            parent_raw = data.get('parent_category_id')
            parent_id = None
            if parent_raw not in (None, ''):
                try:
                    parent_id = int(parent_raw)
                except Exception:
                    return Response({"error": "parent_category_id must be an integer"}, status=status.HTTP_400_BAD_REQUEST)

            if parent_id == category_id:
                return Response({"error": "parent_category_id cannot equal category_id"}, status=status.HTTP_400_BAD_REQUEST)

            if parent_id is not None:
                with connection.cursor() as cursor:
                    cursor.execute("SELECT 1 FROM universal_Categories WHERE category_id = %s", [parent_id])
                    if cursor.fetchone() is None:
                        return Response({"error": "parent_category_id not found"}, status=status.HTTP_400_BAD_REQUEST)

            fields.append("parent_category_id = %s")
            params.append(parent_id)

        if 'business_type' in data:
            bt_col = _uc_business_type_column()
            if not bt_col:
                return Response({"error": "business_type column not found in universal_Categories"}, status=status.HTTP_400_BAD_REQUEST)
            bt_val = data.get('business_type')
            if bt_val in (None, ''):
                bt_val = None
            fields.append(f"`{bt_col}` = %s")
            params.append(None if bt_val is None else str(bt_val).strip().upper())

        if not fields:
            return Response({"error": "No fields provided for update"}, status=status.HTTP_400_BAD_REQUEST)

        with connection.cursor() as cursor:
            cursor.execute("SELECT 1 FROM universal_Categories WHERE category_id = %s", [category_id])
            if cursor.fetchone() is None:
                return Response({"error": "Category not found"}, status=status.HTTP_404_NOT_FOUND)

            q = "UPDATE universal_Categories SET " + ", ".join(fields) + ", updated_at = NOW() WHERE category_id = %s"
            cursor.execute(q, params + [category_id])

        category = _uc_fetch_category(int(category_id))
        if not category:
            return Response({"error": "Failed to fetch updated category"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        return Response({"category": category}, status=status.HTTP_200_OK)
    except Exception as e:
        return Response({"error": "Failed to update category", "details": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

@swagger_auto_schema(method='DELETE', tags=['Business'])
@api_view(['DELETE'])
def delete_universal_category(request, category_id: int):
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1 FROM universal_Categories WHERE category_id = %s", [category_id])
            if cursor.fetchone() is None:
                return Response({"error": "Category not found"}, status=status.HTTP_404_NOT_FOUND)

            cursor.execute("SELECT COUNT(1) FROM universal_Categories WHERE parent_category_id = %s", [category_id])
            child_count = cursor.fetchone()[0] or 0
            if int(child_count) > 0:
                return Response({"error": "Cannot delete category with subcategories"}, status=status.HTTP_400_BAD_REQUEST)

            cursor.execute("DELETE FROM universal_Categories WHERE category_id = %s", [category_id])

        return Response({"message": "Category deleted successfully", "category_id": int(category_id)}, status=status.HTTP_200_OK)
    except Exception as e:
        return Response({"error": "Failed to delete category", "details": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

@swagger_auto_schema(method='GET', tags=['Business'])
@api_view(['GET'])
def fetch_category_with_children(category_id: int):
    """Helper: fetch a category and its immediate subcategories."""
    with connection.cursor() as cursor:
        cursor.execute(
            _uc_select_sql() + " FROM universal_Categories WHERE category_id = %s LIMIT 1",
            [category_id]
        )
        row = cursor.fetchone()
        if not row:
            return None
        cols = _uc_category_cols()
        category = dict(zip(cols, row))

        cursor.execute(
            _uc_select_sql() + " FROM universal_Categories WHERE parent_category_id = %s ORDER BY category_name ASC",
            [category_id]
        )
        children_rows = cursor.fetchall()
        category['subcategories'] = [dict(zip(cols, r)) for r in children_rows]
        return category

@swagger_auto_schema(method='GET', tags=['Business'])
@api_view(['GET'])
def search_universal_category(request):
    """
    Search for a category by name or ID and return it with its subcategories.
    Query params:
      - q (required): search term (name substring) or exact integer ID
      - business_type (optional): filter by BusinessType.categories
    """
    try:
        q = request.query_params.get('q')
        if not q:
            return Response({"error": "Query parameter 'q' is required"}, status=status.HTTP_400_BAD_REQUEST)

        business_type = request.query_params.get('business_type')
        base = [
            _uc_select_sql(),
            "FROM universal_Categories",
            "WHERE 1=1",
        ]
        params = []

        filter_err = _uc_apply_business_type_filter(base, params, business_type)
        if filter_err:
            return Response(filter_err, status=status.HTTP_400_BAD_REQUEST)

        # If q looks like an integer, treat as exact ID search; otherwise name substring
        if q.strip().isdigit():
            base.append("AND category_id = %s")
            params.append(int(q.strip()))
        else:
            base.append("AND category_name LIKE %s")
            params.append(f"%{q.strip()}%")

        base.append("ORDER BY category_name ASC LIMIT 50")
        query = "\n".join(base)

        with connection.cursor() as cursor:
            cursor.execute(query, params)
            rows = cursor.fetchall()
            cols = _uc_category_cols()
            matches = [dict(zip(cols, r)) for r in rows]

        if not matches:
            return Response({"error": "No categories found", "query": q}, status=status.HTTP_404_NOT_FOUND)

        # For each match, fetch its immediate subcategories
        results = []
        for m in matches:
            with_children = _fetch_category_with_children(int(m['category_id']))
            if with_children:
                results.append(with_children)

        return Response({
            "query": q,
            "results": results,
            "count": len(results),
        }, status=status.HTTP_200_OK)
    except Exception as e:
        return Response({"error": "Failed to search categories", "details": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

@swagger_auto_schema(method='POST', tags=['Business'])
@api_view(['POST'])
@permission_classes([AllowAny])
def add_category_mapping(request):
    """
    Create mappings between a business and one or more universal categories.
    Query params: ?userID=<user_id>&business_id=<business_id>
    Body JSON:
      - category_id (single) OR category_ids (list)
      - is_active (optional, default 1)
    Enforces user access via BusinessMapping.
    """
    try:
        user_id = request.query_params.get('userID')
        business_id = request.query_params.get('business_id')
        if not user_id or not business_id:
            return Response({"error": "userID and business_id are required"}, status=status.HTTP_400_BAD_REQUEST)

        # Validate business exists and user has access
        try:
            business = Business.objects.get(business_id=business_id, status=True)
        except Business.DoesNotExist:
            return Response({"error": "Invalid business_id"}, status=status.HTTP_404_NOT_FOUND)

        # Authentication removed - endpoint now open

        data = request.data or {}
        is_active = data.get('is_active', 1)

        # Collect category IDs from payload
        category_ids = []
        if 'category_ids' in data and isinstance(data.get('category_ids'), list):
            category_ids = data.get('category_ids')
        elif 'category_id' in data:
            category_ids = [data.get('category_id')]
        else:
            return Response({"error": "Provide category_id or category_ids"}, status=status.HTTP_400_BAD_REQUEST)

        # Normalize and validate ints
        try:
            category_ids = [int(cid) for cid in category_ids]
            is_active_val = 1 if str(is_active) in {"1", "true", "True"} else 0
        except Exception:
            return Response({"error": "category_ids and is_active must be numeric/boolean"}, status=status.HTTP_400_BAD_REQUEST)

        created = []
        with connection.cursor() as cursor:
            for cid in category_ids:
                # Validate category existence
                cursor.execute("SELECT 1 FROM universal_Categories WHERE category_id = %s", [cid])
                if cursor.fetchone() is None:
                    return Response({"error": f"Invalid category_id: {cid}"}, status=status.HTTP_400_BAD_REQUEST)

                # Insert or update mapping (upsert)
                cursor.execute(
                    """
                    INSERT INTO category_mapping (business_id, category_id, is_active, created_at, updated_at)
                    VALUES (%s, %s, %s, NOW(), NOW())
                    ON DUPLICATE KEY UPDATE is_active = VALUES(is_active), updated_at = NOW()
                    """,
                    [business.business_id, cid, is_active_val]
                )

                # Fetch mapping row
                cursor.execute(
                    "SELECT mapping_id, business_id, category_id, is_active, created_at, updated_at FROM category_mapping WHERE business_id = %s AND category_id = %s",
                    [business.business_id, cid]
                )
                row = cursor.fetchone()
                if row:
                    cols = ["mapping_id", "business_id", "category_id", "is_active", "created_at", "updated_at"]
                    obj = dict(zip(cols, row))
                    # JSON serialize timestamps
                    for key in ("created_at", "updated_at"):
                        if obj.get(key) and hasattr(obj[key], 'isoformat'):
                            obj[key] = obj[key].isoformat()
                    created.append(obj)

        return Response({
            "message": "Category mapping(s) added/updated successfully",
            "mappings": created
        }, status=status.HTTP_201_CREATED)
    except Exception as e:
        return Response({"error": "Failed to add category mapping", "details": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

@swagger_auto_schema(methods=['PUT', 'PATCH'],tags=['Business'])
@api_view(['PUT', 'PATCH'])
@permission_classes([AllowAny])
def update_category_mapping(request, mapping_id: int):
    """
    Update a category mapping (currently supports toggling is_active).
    Query params: ?userID=<user_id>&business_id=<business_id>
    Body JSON: { is_active: 0|1 }
    """
    try:
        user_id = request.query_params.get('userID')
        business_id = request.query_params.get('business_id')
        if not user_id or not business_id:
            return Response({"error": "userID and business_id are required"}, status=status.HTTP_400_BAD_REQUEST)

        # Validate access
        # Authentication removed - endpoint now open

        data = request.data or {}
        if 'is_active' not in data:
            return Response({"error": "is_active is required for update"}, status=status.HTTP_400_BAD_REQUEST)

        is_active_raw = data.get('is_active')
        is_active_val = 1 if str(is_active_raw) in {"1", "true", "True"} else 0

        with connection.cursor() as cursor:
            # Ensure mapping belongs to the business
            cursor.execute("SELECT mapping_id FROM category_mapping WHERE mapping_id = %s AND business_id = %s", [mapping_id, business_id])
            if cursor.fetchone() is None:
                return Response({"error": "Mapping not found for this business"}, status=status.HTTP_404_NOT_FOUND)

            cursor.execute(
                "UPDATE category_mapping SET is_active = %s, updated_at = NOW() WHERE mapping_id = %s AND business_id = %s",
                [is_active_val, mapping_id, business_id]
            )

            cursor.execute(
                """
                SELECT cm.mapping_id, cm.business_id, cm.category_id, cm.is_active, uc.category_name, uc.category_image, uc.parent_category_id, cm.updated_at
                FROM category_mapping cm
                JOIN universal_Categories uc ON uc.category_id = cm.category_id
                WHERE cm.mapping_id = %s
                """,
                [mapping_id]
            )
            row = cursor.fetchone()
            if not row:
                return Response({"error": "Failed to load updated mapping"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
            cols = ["mapping_id", "business_id", "category_id", "is_active", "category_name", "category_image", "parent_category_id", "updated_at"]
            obj = dict(zip(cols, row))
            if obj.get("updated_at") and hasattr(obj["updated_at"], 'isoformat'):
                obj["updated_at"] = obj["updated_at"].isoformat()

        return Response({"message": "Mapping updated successfully", "mapping": obj}, status=status.HTTP_200_OK)
    except Exception as e:
        return Response({"error": "Failed to update category mapping", "details": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

@swagger_auto_schema(method='DELETE',tags=['Business'])
@api_view(['DELETE'])
@permission_classes([AllowAny])
def delete_category_mapping(request, mapping_id: int):
    """
    Delete a category mapping.
    Query params: ?userID=<user_id>&business_id=<business_id>
    """
    try:
        user_id = request.query_params.get('userID')
        business_id = request.query_params.get('business_id')
        if not user_id or not business_id:
            return Response({"error": "userID and business_id are required"}, status=status.HTTP_400_BAD_REQUEST)

        # Authentication removed - endpoint now open

        with connection.cursor() as cursor:
            cursor.execute("DELETE FROM category_mapping WHERE mapping_id = %s AND business_id = %s", [mapping_id, business_id])
            if cursor.rowcount == 0:
                return Response({"error": "Mapping not found for this business"}, status=status.HTTP_404_NOT_FOUND)

        return Response({"message": "Mapping deleted successfully", "mapping_id": mapping_id}, status=status.HTTP_200_OK)
    except Exception as e:
        return Response({"error": "Failed to delete category mapping", "details": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

@swagger_auto_schema(method='GET',tags=['Business'])
@api_view(['GET'])
def selected_categories_for_business(request):
    """
    List selected (mapped) categories for a business.
    Query params:
      - business_id (required)
      - only_active (optional, default=true)
    """
    try:
        business_id = request.query_params.get('business_id')
        if not business_id:
            return Response({"error": "business_id is required"}, status=status.HTTP_400_BAD_REQUEST)

        only_active = request.query_params.get('only_active', 'true')
        only_active_flag = str(only_active).lower() == 'true'

        try:
            business = Business.objects.get(business_id=business_id)
        except Business.DoesNotExist:
            return Response({"error": "Invalid business_id"}, status=status.HTTP_404_NOT_FOUND)

        level_val = (business.level or '').strip().lower()
        allowed_ids = [business.business_id]
        if 'master' in level_val:
            child_ids = list(Business.objects.filter(master=business.business_id).values_list('business_id', flat=True))
            allowed_ids.extend(child_ids)



        placeholders = ','.join(['%s'] * len(allowed_ids))
        base = [
            "SELECT cm.mapping_id, cm.business_id, cm.category_id, cm.is_active,",
            "       uc.category_name, uc.category_image, uc.parent_category_id,",
            "       b.businessName AS business_name, b.logo AS business_image",
            "FROM category_mapping cm",
            "JOIN universal_Categories uc ON uc.category_id = cm.category_id",
            "JOIN businesses b ON b.business_id = cm.business_id",
            f"WHERE cm.business_id IN ({placeholders})",
        ]
        params = list(allowed_ids)
        if only_active_flag:
            base.append("AND cm.is_active = 1")
        base.append("ORDER BY uc.category_name ASC")

        query = "\n".join(base)
        with connection.cursor() as cursor:
            cursor.execute(query, params)
            rows = cursor.fetchall()
            cols = [
                "mapping_id",
                "business_id",
                "category_id",
                "is_active",
                "category_name",
                "category_image",
                "parent_category_id",
                "business_name",
                "business_image",
            ]
            data = [dict(zip(cols, r)) for r in rows]

        # For R08 businesses, add subcategory information from products
        business_type = getattr(business, 'businessType', None)
        if business_type == 'R08' and data:
            # Get category IDs that are mapped
            mapped_category_ids = [row['category_id'] for row in data]
            if mapped_category_ids:
                # Fetch subcategories from fashion products using subcategory_id
                cat_placeholders = ','.join(['%s'] * len(mapped_category_ids))
                biz_placeholders = ','.join(['%s'] * len(allowed_ids))
                
                with connection.cursor() as cursor:
                    cursor.execute(f"""
                        SELECT fp.category_id, fp.subcategory_id, uc.category_name as subcategory_name
                        FROM fashion_products fp
                        LEFT JOIN universal_Categories uc ON uc.category_id = fp.subcategory_id
                        WHERE fp.business_id IN ({biz_placeholders})
                        AND fp.category_id IN ({cat_placeholders})
                        AND fp.subcategory_id IS NOT NULL
                        AND fp.subcategory_id > 0
                        GROUP BY fp.category_id, fp.subcategory_id, uc.category_name
                    """, allowed_ids + mapped_category_ids)
                    subcat_rows = cursor.fetchall()
                
                # Group subcategories by category_id
                subcats_by_category = {}
                for cat_id, subcat_id, subcat_name in subcat_rows:
                    if cat_id not in subcats_by_category:
                        subcats_by_category[cat_id] = []
                    if subcat_name and subcat_name.strip():
                        subcats_by_category[cat_id].append(subcat_name.strip())
                
                # Add subcategories to the response data
                for row in data:
                    category_id = row['category_id']
                    subcategories = subcats_by_category.get(category_id, [])
                    row['sub_categories'] = sorted(list(set(subcategories)))

        for row in data:
            img = row.get("business_image")
            row["business_image"] = build_s3_file_url(img)

        return Response({"categories": data, "count": len(data)}, status=status.HTTP_200_OK)
    except Exception as e:
        return Response({"error": "Failed to fetch selected categories", "details": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

@swagger_auto_schema(method='POST',tags=['Business'])
@api_view(['POST'])
def groceries_ensure_category(request):
    """
    Ensure a GroceriesCategories row exists for a given universal category.
    Body JSON:
      - universal_category_id (preferred) OR category_name
    Returns 201 with { category_id, category_name, parent_category_id? }
    """
    try:
        data = request.data or {}
        universal_category_id = data.get('universal_category_id')
        category_name = data.get('category_name')

        if not universal_category_id and not category_name:
            return Response({"error": "Provide universal_category_id or category_name"}, status=status.HTTP_400_BAD_REQUEST)

        # Fetch universal category row
        row = None
        with connection.cursor() as cursor:
            if universal_category_id:
                cursor.execute(
                    "SELECT category_id, category_name, parent_category_id FROM universal_Categories WHERE category_id = %s LIMIT 1",
                    [universal_category_id]
                )
            else:
                cursor.execute(
                    "SELECT category_id, category_name, parent_category_id FROM universal_Categories WHERE category_name = %s ORDER BY category_id LIMIT 1",
                    [category_name]
                )
            fetched = cursor.fetchone()
            if fetched:
                row = {
                    'category_id': fetched[0],
                    'category_name': fetched[1],
                    'parent_category_id': fetched[2]
                }

        if not row and category_name:
            # Proceed with provided name even if not found in universal table
            row = {'category_id': None, 'category_name': str(category_name).strip(), 'parent_category_id': None}
        if not row:
            return Response({"error": "Universal category not found"}, status=status.HTTP_404_NOT_FOUND)

        name = str(row['category_name']).strip()
        parent_univ_id = row.get('parent_category_id')

        # Ensure parent category in groceries if applicable
        parent_obj = None
        if parent_univ_id:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT category_name FROM universal_Categories WHERE category_id = %s LIMIT 1",
                    [parent_univ_id]
                )
                p = cursor.fetchone()
                parent_name = p[0] if p else None
            if parent_name:
                parent_obj = GroceriesCategories.objects.filter(category_name__iexact=parent_name).first()
                if not parent_obj:
                    parent_obj = GroceriesCategories.objects.create(
                        category_name=parent_name,
                        parent_category=None,
                        gst_rate=Decimal('0.00')
                    )

        # Ensure category
        cat = GroceriesCategories.objects.filter(category_name__iexact=name).first()
        if not cat:
            cat = GroceriesCategories.objects.create(
                category_name=name,
                parent_category=parent_obj,
                gst_rate=Decimal('0.00')
            )

        return Response({
            "message": "Groceries category ensured",
            "category_id": cat.category_id,
            "category_name": cat.category_name,
            "parent_category_id": getattr(cat.parent_category, 'category_id', None)
        }, status=status.HTTP_201_CREATED)
    except Exception as e:
        return Response({"error": "Failed to ensure groceries category", "details": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

@swagger_auto_schema(methods=['GET', 'POST'],tags=['Business'])
@api_view(['GET', 'POST'])
def groceries_categories(request):
    """List or create grocery categories for a specific business.

    Query params:
      - business_id (required)

    GET: returns categories for the business.
    POST: creates a new category for the business.
    """
    business_id = request.query_params.get('business_id') or request.data.get('business_id')
    if not business_id:
        return Response({"error": "business_id is required"}, status=status.HTTP_400_BAD_REQUEST)

    try:
        business = Business.objects.get(business_id=business_id, status=True)
    except Business.DoesNotExist:
        return Response({"error": "Invalid business_id"}, status=status.HTTP_404_NOT_FOUND)

    if request.method == 'GET':
        qs = GroceriesCategories.objects.filter(business=business).order_by('category_name')
        search = request.query_params.get('search')
        if search:
            qs = qs.filter(category_name__icontains=search)
        serializer = GroceriesCategorySerializer(qs, many=True)
        return Response({
            "business_id": business.business_id,
            "count": qs.count(),
            "categories": serializer.data,
        }, status=status.HTTP_200_OK)

    # Create a mutable copy of request data, excluding file objects
    data = {k: v for k, v in request.data.items() if not hasattr(v, 'read')}
    data['business_id'] = business.business_id
    serializer = GroceriesCategorySerializer(data=data)
    if serializer.is_valid():
        category = serializer.save()
        return Response(serializer.data, status=status.HTTP_201_CREATED)
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

@swagger_auto_schema(methods=['GET', 'PUT', 'DELETE'],tags=['Business'])
@api_view(['GET', 'PUT', 'DELETE'])
def groceries_category_detail(request, category_id: int):
    """Retrieve, update, or delete a single grocery category for a business.

    Query params:
      - business_id (required)
    """
    business_id = request.query_params.get('business_id') or request.data.get('business_id')
    if not business_id:
        return Response({"error": "business_id is required"}, status=status.HTTP_400_BAD_REQUEST)

    try:
        business = Business.objects.get(business_id=business_id, status=True)
    except Business.DoesNotExist:
        return Response({"error": "Invalid business_id"}, status=status.HTTP_404_NOT_FOUND)

    try:
        category = GroceriesCategories.objects.get(category_id=category_id, business=business)
    except GroceriesCategories.DoesNotExist:
        return Response({"error": "Category not found for this business"}, status=status.HTTP_404_NOT_FOUND)

    if request.method == 'GET':
        serializer = GroceriesCategorySerializer(category)
        return Response(serializer.data, status=status.HTTP_200_OK)

    if request.method == 'PUT':
        # Create a mutable copy of request data, excluding file objects
        data = {k: v for k, v in request.data.items() if not hasattr(v, 'read')}
        data['business_id'] = business.business_id
        serializer = GroceriesCategorySerializer(category, data=data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_200_OK)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    # DELETE
    name = category.category_name
    cid = category.category_id
    category.delete()
    return Response({
        "message": "Category deleted successfully",
        "category_id": cid,
        "category_name": name,
    }, status=status.HTTP_200_OK)
