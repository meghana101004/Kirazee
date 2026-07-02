from rest_framework.decorators import api_view
from django.http import JsonResponse
from django.db import connection
from datetime import datetime
from .utils import parse_json_input
from .cart_services import CartService
from consumer.image_utils import build_s3_file_url

@api_view(['POST'])
def AddToCartViewOptimized(request):
    """
    Optimized Add to Cart view using Service Layer pattern.
    Supports all business types (R01, R02, R08) with unified logic.
    """
    # 1. Extraction & Validation
    user_id = request.GET.get("user_id")
    business_id = request.GET.get("business_id")
    item_id = request.data.get("item_id")
    quantity = int(request.data.get("quantity", 1))
    customizations = parse_json_input(request.data.get("customizations"), [])
    
    if not all([user_id, business_id, item_id]):
        return JsonResponse({"error": "Missing required parameters: user_id, business_id, item_id"}, status=400)
    
    try:
        user_id = int(user_id)
        item_id = int(item_id)
    except (ValueError, TypeError):
        return JsonResponse({"error": "Invalid ID format"}, status=400)
    
    # 2. Identify Business Type
    biz_type = CartService.get_business_type(business_id)
    if not biz_type:
        return JsonResponse({"error": "Business not found"}, status=404)
    
    # 3. Get Item Details and Check Availability
    try:
        item_details = CartService.get_item_details(biz_type, item_id, business_id)
        if not item_details:
            return JsonResponse({"error": "Item not found or inactive"}, status=404)
        
        # Check availability (skip for R08 as it doesn't have availability_timings)
        if biz_type != "R08":
            availability_timings = item_details[4]
            if not CartService.check_item_availability(biz_type, availability_timings):
                error_msg = "Item is not available at this time"
                if biz_type == "R01":
                    error_msg = "This grocery item is not available at this time"
                return JsonResponse({"error": error_msg}, status=400)
        
    except Exception as e:
        return JsonResponse({"error": f"Failed to fetch item details: {str(e)}"}, status=500)
    
    # 4. Route to specific cart logic
    try:
        msg, final_qty = CartService.upsert_cart(
            biz_type, user_id, business_id, item_id, quantity, customizations
        )
    except Exception as e:
        return JsonResponse({"error": f"Failed to update cart: {str(e)}"}, status=500)
    
    # 5. Build item details response
    item_response = {
        "item_id": item_id,
        "item_name": item_details[1],
        "description": item_details[2],
        "selling_price": str(item_details[3]),
        "quantity": final_qty,
    }
    
    # 6. Fetch and return all cart items for the business
    try:
        cart_rows = CartService.get_cart_items(biz_type, user_id)
        
        # Filter by business_id and transform data
        business_items = {}
        for r in cart_rows:
            if str(r[7]) == business_id:  # r[7] is business_id
                biz_id = str(r[7])
                if biz_id not in business_items:
                    business_items[biz_id] = {
                        "business_name": r[8],
                        "items": []
                    }
                
                business_items[biz_id]["items"].append({
                    "cart_id": r[0],
                    "item_id": r[1],
                    "quantity": r[2],
                    "item_name": r[3],
                    "description": r[4],
                    "selling_price": str(r[5]),
                    "image": build_s3_file_url(r[6]),
                    "customizations": parse_json_input(r[9], [])
                })
        
        cart_details = list(business_items.values()) if business_items else []
        
    except Exception as e:
        return JsonResponse({
            "message": msg,
            "item_details": item_response,
            "error": f"Failed to fetch cart items: {str(e)}"
        }, status=500)
    
    return JsonResponse({
        "message": msg,
        "item_details": item_response,
        "cart_details": cart_details
    }, status=200)


@api_view(['GET'])
def get_cart_items_optimized(request):
    """
    Optimized Get Cart Items view using Service Layer.
    Returns cart items grouped by business with detailed variant metadata.
    
    Query Parameters:
    - user_id (required): User ID
    - type (optional): Business type filter (R01, R02, R08)
    """
    from django.db import connection
    
    user_id = request.GET.get("user_id")
    cart_type = request.GET.get("type")  # R01, R02, R08 (optional)
    
    if not user_id:
        return JsonResponse({"error": "user_id is required"}, status=400)
    
    try:
        user_id = int(user_id)
    except (ValueError, TypeError):
        return JsonResponse({"error": "Invalid user_id format"}, status=400)
    
    # 1. Fetch Cart Rows across all requested types
    cart_rows = []
    types_to_fetch = [cart_type] if cart_type in ["R01", "R02", "R08"] else ["R01", "R02", "R08"]
    
    try:
        for b_type in types_to_fetch:
            rows = CartService.get_cart_items(b_type, user_id)
            # Add business type to each row for later processing
            cart_rows.extend([list(r) + [b_type] for r in rows])
    except Exception as e:
        return JsonResponse({"error": f"Failed to fetch cart items: {str(e)}"}, status=500)

    if not cart_rows:
        return JsonResponse({"message": "Cart is Empty"}, status=200)

    # 2. Extract Variant IDs for Bulk Metadata Fetching
    variant_ids_map = {"R01": [], "R02": [], "R08": []}
    for r in cart_rows:
        v_id = r[10]  # variant_id index
        b_type = r[11]  # The type we added above
        if v_id:
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
                # Use mrp if available, otherwise fallback to original_cost
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

    # 4. Group Items by Business and Attach Metadata
    from kirazee_app.models import Business
    business_ids = list(set(row[7] for row in cart_rows))
    business_logos = {}
    if business_ids:
        business_logos = {str(b.business_id): build_s3_file_url(b.logo) 
                         for b in Business.objects.filter(business_id__in=business_ids)}

    business_items = {}
    for row in cart_rows:
        business_id = str(row[7])
        b_type = row[11]
        v_id = row[10]
        
        if business_id not in business_items:
            business_items[business_id] = {
                'business_id': business_id,
                'business_name': row[8],
                'logo_url': business_logos.get(business_id, ''),
                'items': []
            }
        
        # Get specific variant details
        v_details = variant_metadata.get(f"{b_type}_{v_id}", {})
        
        item_data = {
            'cart_id': row[0],
            'item_id': int(row[1]),
            'variant_id': v_id,
            'quantity': row[2],
            'item_name': row[3] or "",
            'description': row[4] or "",
            'selling_price': str(row[5] or 0),
            'image_url': build_s3_file_url(row[6]),
            'customizations': parse_json_input(row[9], []),
            'variant_details': v_details  # Contains detailed metadata
        }
        
        business_items[business_id]['items'].append(item_data)

    return JsonResponse({"cart_details": list(business_items.values())}, status=200)


@api_view(['DELETE', 'POST'])
def update_cart_quantity_optimized(request):
    """
    Optimized cart quantity update/delete view.
    
    DELETE: Remove cart item or entire cart
    POST: Update quantity (increase/decrease)
    
    Parameters:
    - user_id (required): User ID
    - cart_id (optional for DELETE): Specific cart item to delete
    - type (optional): Business type (R01, R02, R08)
    """
    user_id = request.GET.get("user_id")
    cart_id = request.GET.get("cart_id")
    cart_type = request.GET.get("type")
    
    if not user_id:
        return JsonResponse({"error": "user_id is required"}, status=400)
    
    try:
        user_id = int(user_id)
    except (ValueError, TypeError):
        return JsonResponse({"error": "Invalid user_id format"}, status=400)
    
    if request.method == 'DELETE':
        # Delete specific item or entire cart
        if cart_id and cart_type:
            # Delete specific cart item
            try:
                deleted = CartService.delete_cart_item(cart_type, int(cart_id), user_id)
                if deleted:
                    return JsonResponse({"message": "Item removed from cart"}, status=200)
                else:
                    return JsonResponse({"error": "Item not found in cart"}, status=404)
            except ValueError as e:
                return JsonResponse({"error": str(e)}, status=400)
            except Exception as e:
                return JsonResponse({"error": f"Failed to delete item: {str(e)}"}, status=500)
        else:
            # Delete entire cart for user (all types)
            total_deleted = 0
            for biz_type in ["R01", "R02", "R08"]:
                try:
                    with connection.cursor() as cursor:
                        tables = {"R01": "Groceries_cart", "R02": "menuCart", "R08": "fashion_cart"}
                        cursor.execute(f"DELETE FROM {tables[biz_type]} WHERE user_id=%s", [user_id])
                        total_deleted += cursor.rowcount
                except Exception:
                    continue
            
            if total_deleted > 0:
                return JsonResponse({"message": f"Removed {total_deleted} items from cart"}, status=200)
            else:
                return JsonResponse({"message": "Your cart is already empty"}, status=200)
    
    elif request.method == 'POST':
        # Update quantity
        data = request.data
        item_id = data.get('item_id') or data.get('cart_id')
        action = data.get('action')  # 'inc', 'dec', or specific quantity
        quantity = data.get('quantity')
        cart_type = data.get('type')
        
        if not all([item_id is not None, cart_type, user_id]):
            return JsonResponse({"error": "Missing required parameters"}, status=400)
        
        try:
            item_id = int(item_id)
        except (ValueError, TypeError):
            return JsonResponse({"error": "Invalid item_id format"}, status=400)
        
        # Handle quantity update logic
        tables = {"R01": "Groceries_cart", "R02": "menuCart", "R08": "fashion_cart"}
        item_cols = {"R01": "product_id", "R02": "menu_id", "R08": "variant_id"}
        
        if cart_type not in tables:
            return JsonResponse({"error": "Invalid cart type"}, status=400)
        
        with connection.cursor() as cursor:
            if action == 'inc':
                cursor.execute(
                    f"UPDATE {tables[cart_type]} SET quantity=quantity+1, updated_at=NOW() "
                    f"WHERE {item_cols[cart_type]}=%s AND user_id=%s",
                    [item_id, user_id]
                )
                if cursor.rowcount == 0:
                    return JsonResponse({"error": "Item not found in cart"}, status=404)
                
                cursor.execute(
                    f"SELECT quantity FROM {tables[cart_type]} WHERE {item_cols[cart_type]}=%s AND user_id=%s",
                    [item_id, user_id]
                )
                new_qty = cursor.fetchone()[0]
                return JsonResponse({"message": "Quantity increased", "quantity": new_qty}, status=200)
                
            elif action == 'dec':
                cursor.execute(
                    f"SELECT quantity FROM {tables[cart_type]} WHERE {item_cols[cart_type]}=%s AND user_id=%s",
                    [item_id, user_id]
                )
                row = cursor.fetchone()
                if not row:
                    return JsonResponse({"error": "Item not found in cart"}, status=404)
                
                current_qty = row[0]
                if current_qty > 1:
                    cursor.execute(
                        f"UPDATE {tables[cart_type]} SET quantity=quantity-1, updated_at=NOW() "
                        f"WHERE {item_cols[cart_type]}=%s AND user_id=%s",
                        [item_id, user_id]
                    )
                    return JsonResponse({"message": "Quantity decreased", "quantity": current_qty - 1}, status=200)
                else:
                    # Remove item if quantity would be 0
                    cursor.execute(
                        f"DELETE FROM {tables[cart_type]} WHERE {item_cols[cart_type]}=%s AND user_id=%s",
                        [item_id, user_id]
                    )
                    return JsonResponse({"message": "Item removed from cart"}, status=200)
                    
            elif quantity is not None:
                try:
                    quantity = int(quantity)
                    if quantity <= 0:
                        # Remove item
                        cursor.execute(
                            f"DELETE FROM {tables[cart_type]} WHERE {item_cols[cart_type]}=%s AND user_id=%s",
                            [item_id, user_id]
                        )
                        return JsonResponse({"message": "Item removed from cart"}, status=200)
                    else:
                        # Update quantity
                        cursor.execute(
                            f"UPDATE {tables[cart_type]} SET quantity=%s, updated_at=NOW() "
                            f"WHERE {item_cols[cart_type]}=%s AND user_id=%s",
                            [quantity, item_id, user_id]
                        )
                        if cursor.rowcount == 0:
                            return JsonResponse({"error": "Item not found in cart"}, status=404)
                        return JsonResponse({"message": "Quantity updated", "quantity": quantity}, status=200)
                except (ValueError, TypeError):
                    return JsonResponse({"error": "Invalid quantity format"}, status=400)
            else:
                return JsonResponse({"error": "Invalid action or missing quantity"}, status=400)
    
    return JsonResponse({"error": "Method not allowed"}, status=405)
