from django.db import connection, transaction
from django.utils import timezone
from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework import status
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from drf_yasg.utils import swagger_auto_schema
from decimal import Decimal
import json
import logging
from datetime import datetime
import pytz

logger = logging.getLogger(__name__)

from .models import Orders, Rating
from kirazee_app.models import Registration, Business
from consumer.image_utils import build_s3_file_url


def _safe_int(value, default=None):
    try:
        if value is None:
            return default
        if isinstance(value, bool):
            return default
        s = str(value).strip()
        if s == '' or s.lower() == 'null':
            return default
        return int(s)
    except Exception:
        return default


def _resolve_review_target(item_id):
    iid = _safe_int(item_id)
    if not iid:
        return None

    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT business_id, item_name FROM menuItems WHERE item_id = %s LIMIT 1",
            [iid],
        )
        row = cursor.fetchone()
        if row:
            return {
                'canonical_id': iid,
                'business_id': row[0],
                'item_name': row[1],
                'source': 'menu',
                'input_id': iid,
                'resolved_product_id': None,
                'resolved_variant_id': None,
            }

        cursor.execute(
            "SELECT business_id, item_name FROM GroceryItems WHERE item_id = %s LIMIT 1",
            [iid],
        )
        row = cursor.fetchone()
        if row:
            return {
                'canonical_id': iid,
                'business_id': row[0],
                'item_name': row[1],
                'source': 'grocery_item',
                'input_id': iid,
                'resolved_product_id': None,
                'resolved_variant_id': None,
            }

        cursor.execute(
            "SELECT business_id, product_name FROM Groceries_Products WHERE product_id = %s LIMIT 1",
            [iid],
        )
        row = cursor.fetchone()
        if row:
            return {
                'canonical_id': iid,
                'business_id': row[0],
                'item_name': row[1],
                'source': 'grocery_product',
                'input_id': iid,
                'resolved_product_id': iid,
                'resolved_variant_id': None,
            }

        cursor.execute(
            "SELECT business_id, name FROM fashion_products WHERE product_id = %s LIMIT 1",
            [iid],
        )
        row = cursor.fetchone()
        if row:
            return {
                'canonical_id': iid,
                'business_id': row[0],
                'item_name': row[1],
                'source': 'fashion_product',
                'input_id': iid,
                'resolved_product_id': iid,
                'resolved_variant_id': None,
            }

        cursor.execute(
            """
            SELECT gp.business_id, gp.product_name, gpv.product_id
            FROM Groceries_ProductVariants_1 gpv
            JOIN Groceries_Products gp ON gp.product_id = gpv.product_id
            WHERE gpv.variant_id = %s
            LIMIT 1
            """,
            [iid],
        )
        row = cursor.fetchone()
        if row:
            biz_id, product_name, product_id = row
            canon = _safe_int(product_id)
            if not canon:
                canon = iid
            return {
                'canonical_id': canon,
                'business_id': biz_id,
                'item_name': product_name,
                'source': 'grocery_variant',
                'input_id': iid,
                'resolved_product_id': canon,
                'resolved_variant_id': iid,
            }

        cursor.execute(
            """
            SELECT fp.business_id, fp.name, fp.product_id
            FROM fashion_product_variants fpv
            JOIN fashion_products fp ON fp.product_id = fpv.product_id
            WHERE fpv.variant_id = %s
            LIMIT 1
            """,
            [iid],
        )
        row = cursor.fetchone()
        if row:
            biz_id, product_name, product_id = row
            canon = _safe_int(product_id)
            if not canon:
                canon = iid
            return {
                'canonical_id': canon,
                'business_id': biz_id,
                'item_name': product_name,
                'source': 'fashion_variant',
                'input_id': iid,
                'resolved_product_id': canon,
                'resolved_variant_id': iid,
            }

    return None


@swagger_auto_schema(methods=['POST'],tags=['Consumer'])
@api_view(['POST'])
def add_reviews(request):
    """
    Submit a review and rating for an order/product
    
    URL: POST /kirazee/consumer/add-reviews?user_id=[value]
    Note: If user_id is not provided, defaults to "00000" (anonymous user)
    
    Body (Either order_id OR product_id OR both must be provided):
    {
        "order_id": "1001",           // Optional - for order-level reviews
        "product_id": "12345",        // Optional - for product-specific reviews (can be empty string)
        "variant_id": "67890",        // Optional - for variant-specific reviews
        "rating": 4.5,                // Required - 1 to 5 stars
        "review": "Good quality, fast delivery! 😊👍"  // Optional - text with emoji support
    }
    
    Use Cases:
    1. Order-level review (rates ALL items in order): {"order_id": "1001", "product_id": "", "rating": 4, "review": "Great service!"}
    2. Product-specific review: {"order_id": "", "product_id": "12345", "rating": 5, "review": "Loved this item!"}
    3. Variant-specific review: {"product_id": "12345", "variant_id": "67890", "rating": 5, "review": "Loved this variant!"}
    4. Order + Product review: {"order_id": "1001", "product_id": "12345", "rating": 4, "review": "Good item in this order"}
    5. Anonymous review: POST /add-reviews (without user_id) - defaults to anonymous user "00000"
    
    Note: When only order_id is provided (no product_id), the system automatically creates individual 
    ratings for ALL items in that order with the same rating and review text.
    
    Update Behavior: If a review already exists, it will be UPDATED with the new rating and review text
    instead of being blocked. This allows users to modify their reviews anytime.
    """
    try:
        user_id = request.query_params.get('user_id', '00000')  # Default to anonymous user
        if not user_id:
            user_id = '00000'  # Fallback to anonymous user
        
        data = request.data
        order_id = data.get('order_id')
        product_id = data.get('product_id')
        if not product_id:
            product_id = data.get('item_id')
        variant_id = data.get('variant_id')
        rating_value = data.get('rating')
        review_text = data.get('review', '')
        
        resolved_item = None
        canonical_product_id = None
        canonical_variant_id = None

        if product_id == '' or product_id == 'null':
            product_id = None
        elif product_id is not None:
            product_id_int = _safe_int(product_id)
            if not product_id_int:
                return JsonResponse({
                    "message": "product_id/item_id must be a valid number or empty"
                }, status=400)
            resolved_item = _resolve_review_target(product_id_int)
            if not resolved_item:
                return JsonResponse({
                    "message": "Product not found"
                }, status=404)
            canonical_product_id = resolved_item['canonical_id']
            product_id = product_id_int
        
        # Handle variant_id - can be provided directly or resolved from product
        if variant_id == '' or variant_id == 'null':
            variant_id = None
        elif variant_id is not None:
            variant_id_int = _safe_int(variant_id)
            if not variant_id_int:
                return JsonResponse({
                    "message": "variant_id must be a valid number or empty"
                }, status=400)
            canonical_variant_id = variant_id_int
            variant_id = variant_id_int
        elif resolved_item and resolved_item.get('resolved_variant_id'):
            # Auto-resolve variant from the product lookup
            canonical_variant_id = resolved_item['resolved_variant_id']
        
        # Validate required fields - either order_id OR product_id must be provided
        if not rating_value:
            return JsonResponse({
                "message": "rating is required"
            }, status=400)
        
        if not order_id and not product_id:
            return JsonResponse({
                "message": "Either order_id or product_id must be provided"
            }, status=400)
        
        # Validate rating range
        if not (1 <= float(rating_value) <= 5):
            return JsonResponse({
                "message": "Rating must be between 1 and 5"
            }, status=400)
        
        # Validate user exists (handle anonymous user)
        if user_id == '00000':
            # Anonymous user - create a dummy user object or handle specially
            user = None
            anonymous_user = True
        else:
            try:
                user = Registration.objects.get(user_id=user_id)
                anonymous_user = False
            except Registration.DoesNotExist:
                return JsonResponse({
                    "message": "User not found. Review will be submitted as anonymous."
                }, status=404)
        
        # Initialize order and business_id variables
        order = None
        business_id = None
        
        # If order_id is provided, validate the order
        if order_id:
            try:
                if anonymous_user:
                    # For anonymous users, just check if order exists (no user validation)
                    order = Orders.objects.get(order_id=order_id)
                else:
                    # For registered users, validate order belongs to them
                    order = Orders.objects.get(order_id=order_id, user_id=user)
                
                # Check if order is completed/delivered
                if order.status not in ['delivered', 'completed']:
                    return JsonResponse({
                        "message": "You can only review completed or delivered orders"
                    }, status=400)
                
                # Get business_id from order
                business_id = order.business_id.business_id
                
            except Orders.DoesNotExist:
                return JsonResponse({
                    "message": "Order not found" + ("" if anonymous_user else " or doesn't belong to this user")
                }, status=404)
        
        # If product_id is provided but no order_id, we need to get business_id from the product
        elif product_id:
            if not resolved_item:
                resolved_item = _resolve_review_target(product_id)
            if not resolved_item:
                return JsonResponse({
                    "message": "Product not found"
                }, status=404)
            business_id = resolved_item['business_id']
            canonical_product_id = resolved_item['canonical_id']
        
        # Check if review already exists for this combination (skip for anonymous users)
        # Instead of blocking, we'll update existing reviews
        update_mode = False
        existing_reviews_to_update = []
        
        if not anonymous_user:
            # Build the filter dynamically based on what's provided
            review_filter = {'user_id': user}

            if business_id:
                review_filter['business_id_id'] = business_id
            
            effective_product_id = canonical_product_id if canonical_product_id else product_id

            if order and effective_product_id:
                # Both order and product provided - check for exact match (include variant_id if available)
                review_filter.update({'order_id': order, 'product_id': effective_product_id})
                if canonical_variant_id:
                    review_filter['variant_id'] = canonical_variant_id
                existing_reviews_to_update = list(Rating.objects.filter(**review_filter))
            elif order:
                # Only order provided - check if user already reviewed this order
                # We'll update all existing item reviews for this order
                review_filter.update({'order_id': order})
                existing_reviews_to_update = list(Rating.objects.filter(**review_filter))
            elif effective_product_id:
                # Only product provided - check if user already reviewed this product (without specific order)
                # Include variant_id in filter if available
                review_filter.update({'product_id': effective_product_id, 'order_id__isnull': True})
                if canonical_variant_id:
                    review_filter['variant_id'] = canonical_variant_id
                existing_reviews_to_update = list(Rating.objects.filter(**review_filter))
            
            if existing_reviews_to_update:
                update_mode = True
        
        # Create or update the review(s)
        with transaction.atomic():
            if order and not product_id:
                # Order-level review: Create/Update ratings for all items in the order
                from .models import OrderItems
                
                if update_mode and existing_reviews_to_update:
                    # Update existing reviews
                    updated_reviews = []
                    for existing_review in existing_reviews_to_update:
                        existing_review.rating = int(float(rating_value))
                        existing_review.review = review_text
                        if canonical_variant_id and not existing_review.variant_id:
                            existing_review.variant_id = canonical_variant_id
                        existing_review.save()  # This will trigger update_item_rating()
                        
                        updated_reviews.append({
                            "product_id": existing_review.product_id,
                            "variant_id": existing_review.variant_id,
                            "item_name": f"Item {existing_review.product_id}",  # We'll get the name from DB if needed
                            "rating": int(float(rating_value)),
                            "action": "updated"
                        })
                    
                    return JsonResponse({
                        "status": "success",
                        "message": f"Thank you..! Review updated for {len(updated_reviews)} items successfully." + (" (Anonymous review)" if anonymous_user else ""),
                        "items_reviewed": updated_reviews
                    }, status=200)
                
                else:
                    # Create new reviews
                    # Get all items from this order
                    order_items = OrderItems.objects.filter(order_id=order)
                    
                    if not order_items.exists():
                        return JsonResponse({
                            "message": "No items found in this order"
                        }, status=404)
                    
                    created_reviews = []
                    for order_item in order_items:
                        # Determine the product_id based on order item type
                        item_product_id = None
                        item_variant_id = None
                        if order_item.menu_item_id:
                            item_product_id = order_item.menu_item_id
                        elif order_item.product_item_id:
                            item_product_id = order_item.product_item_id
                        
                        # Check for variant_id in order_item (if available)
                        if hasattr(order_item, 'variant_id') and order_item.variant_id:
                            item_variant_id = order_item.variant_id
                        
                        if item_product_id:
                            target = _resolve_review_target(item_product_id)
                            item_review_id = target['canonical_id'] if target and target.get('canonical_id') else item_product_id
                            item_review_variant_id = item_variant_id if item_variant_id else (target.get('resolved_variant_id') if target else None)
                            
                            # Create review for this item
                            item_review = Rating.objects.create(
                                product_id=item_review_id,
                                variant_id=item_review_variant_id,
                                user_id=user,
                                rating=int(float(rating_value)),
                                review=review_text,
                                business_id_id=business_id,
                                order_id=order
                            )
                            created_reviews.append({
                                "product_id": item_review_id,
                                "variant_id": item_review_variant_id,
                                "item_name": order_item.item_name_snapshot or f"Item {item_product_id}",
                                "rating": int(float(rating_value)),
                                "action": "created"
                            })
                    
                    return JsonResponse({
                        "status": "success",
                        "message": f"Thank you..! Review submitted for {len(created_reviews)} items successfully." + (" (Anonymous review)" if anonymous_user else ""),
                        "items_reviewed": created_reviews
                    }, status=200)
                
            else:
                # Single product review or order+product review
                effective_product_id = canonical_product_id if canonical_product_id else product_id
                if update_mode and existing_reviews_to_update:
                    # Update existing review
                    existing_review = existing_reviews_to_update[0]  # Should be only one for single product
                    existing_review.rating = int(float(rating_value))
                    existing_review.review = review_text
                    existing_review.save()  # This will trigger update_item_rating()
                    
                    return JsonResponse({
                        "status": "success",
                        "message": "Thank you..! Review updated successfully." + (" (Anonymous review)" if anonymous_user else ""),
                        "action": "updated"
                    }, status=200)
                else:
                    # Create new review
                    review = Rating.objects.create(
                        product_id=effective_product_id,
                        variant_id=canonical_variant_id,
                        user_id=user,
                        rating=int(float(rating_value)),
                        review=review_text,
                        business_id_id=business_id,  # Use business_id_id for ForeignKey
                        order_id=order  # This can be None if only product_id was provided
                    )
                    
                    return JsonResponse({
                        "status": "success",
                        "message": "Thank you..! Review submitted successfully." + (" (Anonymous review)" if anonymous_user else ""),
                        "action": "created",
                        "product_id": effective_product_id,
                        "variant_id": canonical_variant_id
                    }, status=200)
        
    except Exception as e:
        logger.error(f"Error in add_reviews: {str(e)}")
        return JsonResponse({
            "message": f"Failed to submit review: {str(e)}"
        }, status=500)


@swagger_auto_schema(methods=['GET'],tags=['Consumer'])
@api_view(['GET'])
def display_reviews(request):
    """
    Fetch all reviews for a specific item
    
    URL: GET /kirazee/consumer/display-reviews?item_id=[value]
    """
    try:
        item_id = request.query_params.get('item_id')
        if not item_id:
            return JsonResponse({"message": "item_id parameter is required"}, status=400)

        resolved_item = _resolve_review_target(item_id)
        if not resolved_item:
            return JsonResponse({"message": "Item not found"}, status=404)
        canonical_id = resolved_item['canonical_id']
        business_id = resolved_item.get('business_id')
        
        with connection.cursor() as cursor:
            # Get all reviews for this item with user details (including variant_id)
            cursor.execute("""
                SELECT 
                    r.rating,
                    r.review,
                    r.created_at,
                    r.username,
                    r.variant_id,
                    reg.firstName,
                    reg.lastName,
                    reg.profileUrl
                FROM rating r
                LEFT JOIN registrations reg ON r.user_id = reg.user_id
                WHERE r.product_id = %s AND r.business_id = %s
                ORDER BY r.created_at DESC
            """, [canonical_id, business_id])
            
            reviews_data = cursor.fetchall()
            
            # Calculate average rating and total count
            cursor.execute("""
                SELECT AVG(rating), COUNT(*) 
                FROM rating 
                WHERE product_id = %s AND business_id = %s
            """, [canonical_id, business_id])
            
            avg_rating, total_reviews = cursor.fetchone()
            avg_rating = round(float(avg_rating), 1) if avg_rating else 0.0
            total_reviews = total_reviews or 0
        
        # Format reviews data with item information
        reviews = []
        ist = pytz.timezone('Asia/Kolkata')
        
        item_name = resolved_item.get('item_name')
        
        for review_row in reviews_data:
            rating_val, review_text, created_at, username, variant_id, first_name, last_name, profile_url = review_row
            
            # Format display name
            if first_name and last_name:
                display_name = f"{first_name} {last_name}"
            elif username:
                display_name = username
            else:
                display_name = "Anonymous User"
            
            # Format profile URL
            profile_url_full = build_s3_file_url(profile_url)
            
            # Convert to IST
            if created_at:
                if timezone.is_aware(created_at):
                    ist_time = created_at.astimezone(ist)
                else:
                    ist_time = timezone.make_aware(created_at, ist)
                formatted_date = ist_time.strftime('%Y-%m-%d %H:%M:%S IST')
            else:
                formatted_date = "Unknown"
            
            reviews.append({
                "display_name": display_name,
                "profile_url": profile_url_full,
                "rating": rating_val,
                "review": review_text or "",
                "variant_id": variant_id,
                "date": formatted_date
            })
        
        return JsonResponse({
            "item_id": int(resolved_item.get('input_id') or item_id),
            "resolved_product_id": int(canonical_id) if canonical_id is not None else None,
            "resolved_variant_id": int(resolved_item.get('resolved_variant_id')) if resolved_item.get('resolved_variant_id') is not None else None,
            "item_name": item_name or f"Item {item_id}",
            "average_rating": avg_rating,
            "total_reviews": total_reviews,
            "reviews": reviews
        }, status=200)
        
    except Exception as e:
        logger.error(f"Error in display_reviews: {str(e)}")
        return JsonResponse({
            "message": f"Failed to fetch reviews: {str(e)}"
        }, status=500)


@swagger_auto_schema(methods=['GET'],tags=['Consumer'])
@api_view(['GET'])
def business_reviews(request):
    """
    Calculate and display average rating for all items from a business
    
    URL: GET /kirazee/consumer/reviews?business_id=[value]
    
    Returns business-wide rating analytics including:
    - Average rating and total reviews
    - Rating distribution (1-5 stars)
    - Recent reviews with user profiles and item details
    """
    try:
        business_id = request.query_params.get('business_id')
        if not business_id:
            return JsonResponse({"message": "business_id parameter is required"}, status=400)
        
        # Validate business exists
        business = get_object_or_404(Business, business_id=business_id)
        
        with connection.cursor() as cursor:
            # Get average rating and total reviews for this business
            cursor.execute("""
                SELECT 
                    AVG(r.rating) as avg_rating,
                    COUNT(r.id) as total_reviews,
                    COUNT(DISTINCT r.product_id) as total_items_reviewed
                FROM rating r
                WHERE r.business_id = %s
            """, [business_id])
            
            result = cursor.fetchone()
            avg_rating, total_reviews, total_items_reviewed = result
            
            avg_rating = round(float(avg_rating), 1) if avg_rating else 0.0
            total_reviews = total_reviews or 0
            total_items_reviewed = total_items_reviewed or 0
            
            # Get rating distribution
            cursor.execute("""
                SELECT 
                    rating,
                    COUNT(*) as count
                FROM rating 
                WHERE business_id = %s
                GROUP BY rating
                ORDER BY rating DESC
            """, [business_id])
            
            rating_distribution = {}
            for rating_val, count in cursor.fetchall():
                rating_distribution[f"{rating_val}_star"] = count
            
            # Get recent reviews (last 10) with variant_id
            cursor.execute("""
                SELECT 
                    r.rating,
                    r.review,
                    r.created_at,
                    r.username,
                    r.product_id,
                    r.variant_id,
                    COALESCE(m.item_name, g.item_name, gp.product_name, fp.name) as item_name,
                    reg.firstName,
                    reg.lastName,
                    reg.profileUrl
                FROM rating r
                LEFT JOIN menuItems m ON r.product_id = m.item_id
                LEFT JOIN GroceryItems g ON r.product_id = g.item_id
                LEFT JOIN Groceries_Products gp ON r.product_id = gp.product_id
                LEFT JOIN fashion_products fp ON r.product_id = fp.product_id
                LEFT JOIN registrations reg ON r.user_id = reg.user_id
                WHERE r.business_id = %s
                ORDER BY r.created_at DESC
                LIMIT 10
            """, [business_id])
            
            recent_reviews = []
            ist = pytz.timezone('Asia/Kolkata')
            
            for review_row in cursor.fetchall():
                rating_val, review_text, created_at, username, product_id, variant_id, item_name, first_name, last_name, profile_url = review_row
                
                # Format display name
                if first_name and last_name:
                    display_name = f"{first_name} {last_name}"
                elif username:
                    display_name = username
                else:
                    display_name = "Anonymous User"
                
                # Format profile URL using S3
                profile_url_full = build_s3_file_url(profile_url)
                
                # Convert to IST
                if created_at:
                    if timezone.is_aware(created_at):
                        ist_time = created_at.astimezone(ist)
                    else:
                        ist_time = timezone.make_aware(created_at, ist)
                    formatted_date = ist_time.strftime('%Y-%m-%d %H:%M:%S IST')
                else:
                    formatted_date = "Unknown"
                
                recent_reviews.append({
                    "username": display_name,
                    "profile_url": profile_url_full,
                    "rating": rating_val,
                    "review": review_text or "",
                    "item_name": item_name or f"Item {product_id}",
                    "product_id": product_id,
                    "variant_id": variant_id,
                    "date": formatted_date
                })
        
        return JsonResponse({
            "business_id": business_id,
            "business_name": business.businessName if hasattr(business, 'businessName') else "Unknown Business",
            "average_rating": avg_rating,
            "total_reviews": total_reviews,
            "total_items_reviewed": total_items_reviewed,
            "rating_distribution": rating_distribution,
            "recent_reviews": recent_reviews
        }, status=200)
        
    except Exception as e:
        logger.error(f"Error in business_reviews: {str(e)}")
        return JsonResponse({
            "message": f"Failed to fetch business reviews: {str(e)}"
        }, status=500)


@swagger_auto_schema(methods=['GET'],tags=['Consumer'])
@api_view(['GET'])
def order_reviews(request):
    """
    Get all reviews for items in a specific order
    
    URL: GET /kirazee/consumer/order-reviews?order_id=[value]
    """
    try:
        order_id = request.query_params.get('order_id')
        if not order_id:
            return JsonResponse({"message": "order_id parameter is required"}, status=400)
        
        with connection.cursor() as cursor:
            # Get all reviews for items in this order with item details (including variant_id)
            cursor.execute("""
                SELECT 
                    r.product_id,
                    r.variant_id,
                    r.rating,
                    r.review,
                    r.created_at,
                    r.username,
                    reg.firstName,
                    reg.lastName,
                    reg.profileUrl,
                    COALESCE(m.item_name, g.item_name, gp.product_name, fp.name) as item_name,
                    COALESCE(m.item_image, g.item_image, gp.main_image, fp.main_image) as item_image
                FROM rating r
                LEFT JOIN registrations reg ON r.user_id = reg.user_id
                LEFT JOIN menuItems m ON r.product_id = m.item_id
                LEFT JOIN GroceryItems g ON r.product_id = g.item_id
                LEFT JOIN Groceries_Products gp ON r.product_id = gp.product_id
                LEFT JOIN fashion_products fp ON r.product_id = fp.product_id
                WHERE r.order_id = %s
                ORDER BY r.product_id, r.created_at DESC
            """, [order_id])
            
            reviews_data = cursor.fetchall()
            
            if not reviews_data:
                return JsonResponse({
                    "message": "No reviews found for this order",
                    "order_id": order_id,
                    "items_reviewed": []
                }, status=200)
        
        # Group reviews by product_id
        items_reviews = {}
        ist = pytz.timezone('Asia/Kolkata')
        
        for review_row in reviews_data:
            (product_id, variant_id, rating_val, review_text, created_at, username, 
             first_name, last_name, profile_url, item_name, item_image) = review_row
            
            if product_id not in items_reviews:
                items_reviews[product_id] = {
                    "product_id": product_id,
                    "variant_id": variant_id,
                    "item_name": item_name or f"Item {product_id}",
                    "item_image": build_s3_file_url(item_image),
                    "reviews": [],
                    "average_rating": 0.0,
                    "total_reviews": 0
                }
            
            # Format display name
            if first_name and last_name:
                display_name = f"{first_name} {last_name}"
            elif username:
                display_name = username
            else:
                display_name = "Anonymous User"
            
            # Format profile URL
            profile_url_full = build_s3_file_url(profile_url)
            
            # Convert to IST
            if created_at:
                if timezone.is_aware(created_at):
                    ist_time = created_at.astimezone(ist)
                else:
                    ist_time = timezone.make_aware(created_at, ist)
                formatted_date = ist_time.strftime('%Y-%m-%d %H:%M:%S IST')
            else:
                formatted_date = "Unknown"
            
            items_reviews[product_id]["reviews"].append({
                "display_name": display_name,
                "profile_url": profile_url_full,
                "rating": rating_val,
                "review": review_text or "",
                "date": formatted_date
            })
        
        # Calculate average ratings for each item
        for product_id in items_reviews:
            reviews_list = items_reviews[product_id]["reviews"]
            if reviews_list:
                avg_rating = sum(r["rating"] for r in reviews_list) / len(reviews_list)
                items_reviews[product_id]["average_rating"] = round(avg_rating, 1)
                items_reviews[product_id]["total_reviews"] = len(reviews_list)
        
        return JsonResponse({
            "order_id": order_id,
            "total_items_reviewed": len(items_reviews),
            "items_reviewed": list(items_reviews.values())
        }, status=200)
        
    except Exception as e:
        logger.error(f"Error in order_reviews: {str(e)}")
        return JsonResponse({
            "message": f"Failed to fetch order reviews: {str(e)}"
        }, status=500)


@swagger_auto_schema(methods=['GET', 'PUT', 'DELETE'],tags=['Consumer'])
@api_view(['GET', 'PUT', 'DELETE'])
def item_review(request):
    try:
        user_id = request.query_params.get('user_id')
        user = None
        if user_id is not None and str(user_id).strip() not in ('', '00000', 'null'):
            try:
                user = Registration.objects.get(user_id=user_id)
            except Registration.DoesNotExist:
                return JsonResponse({"message": "User not found"}, status=404)

        incoming_item_id = request.query_params.get('item_id')
        if incoming_item_id is None:
            incoming_item_id = request.data.get('item_id')
        if incoming_item_id is None:
            incoming_item_id = request.data.get('product_id')
        if incoming_item_id is None:
            return JsonResponse({"message": "item_id is required"}, status=400)

        resolved_item = _resolve_review_target(incoming_item_id)
        if not resolved_item:
            return JsonResponse({"message": "Item not found"}, status=404)

        canonical_id = resolved_item['canonical_id']
        business_id = resolved_item.get('business_id')
        order_id = request.query_params.get('order_id')
        if order_id is None:
            order_id = request.data.get('order_id')

        qs = Rating.objects.filter(product_id=canonical_id)
        if user is not None:
            qs = qs.filter(user_id=user)
        if business_id is not None:
            qs = qs.filter(business_id_id=business_id)

        order_id_int = _safe_int(order_id)
        if order_id is not None and str(order_id).strip() not in ('', 'null'):
            if not order_id_int:
                return JsonResponse({"message": "order_id must be a valid number"}, status=400)
            qs = qs.filter(order_id_id=order_id_int)

        if request.method == 'GET':
            # Get ALL reviews for the item
            all_reviews_qs = Rating.objects.filter(product_id=canonical_id)
            if business_id is not None:
                all_reviews_qs = all_reviews_qs.filter(business_id_id=business_id)
            
            order_id_int = _safe_int(order_id)
            if order_id is not None and str(order_id).strip() not in ('', 'null'):
                if not order_id_int:
                    return JsonResponse({"message": "order_id must be a valid number"}, status=400)
                all_reviews_qs = all_reviews_qs.filter(order_id_id=order_id_int)
            
            all_reviews = all_reviews_qs.order_by('-created_at')
            
            # Get current user's review specifically
            user_review = all_reviews.filter(user_id=user).first() if user is not None else None

            include_current_user_fields = user_id is not None and str(user_id).strip() not in ('', '00000', 'null')
            
            reviews_list = []
            for review in all_reviews:
                review_user_id = getattr(review.user_id, 'user_id', None)
                review_out = {
                    "rating_id": review.id,
                    "user_id": review_user_id,
                    "rating": review.rating,
                    "review": review.review or "",
                    "variant_id": review.variant_id,
                    "order_id": getattr(review.order_id, 'order_id', None),
                    "created_at": review.created_at.isoformat() if getattr(review, 'created_at', None) else None,
                }
                if include_current_user_fields:
                    review_out["is_current_user"] = (review_user_id == int(user_id)) if (review_user_id is not None) else False
                reviews_list.append(review_out)

            response_data = {
                "item_id": int(resolved_item.get('input_id') or incoming_item_id),
                "all_reviews": reviews_list,
                "total_reviews": len(reviews_list),
                "average_rating": sum(r.rating for r in all_reviews) / len(all_reviews) if all_reviews else 0
            }

            if include_current_user_fields:
                response_data["current_user_review"] = {
                    "rating_id": user_review.id,
                    "rating": user_review.rating,
                    "review": user_review.review or "",
                    "variant_id": user_review.variant_id,
                    "order_id": getattr(user_review.order_id, 'order_id', None),
                    "created_at": user_review.created_at.isoformat() if getattr(user_review, 'created_at', None) else None,
                } if user_review else None
            
            return JsonResponse(response_data, status=200)

        if request.method == 'PUT':
            if user is None:
                return JsonResponse({"message": "user_id is required"}, status=400)
            rating_value = request.data.get('rating')
            review_text = request.data.get('review', '')
            if rating_value is None or str(rating_value).strip() == '':
                return JsonResponse({"message": "rating is required"}, status=400)
            if not (1 <= float(rating_value) <= 5):
                return JsonResponse({"message": "Rating must be between 1 and 5"}, status=400)
            r = qs.order_by('-created_at').first()
            if not r:
                return JsonResponse({"message": "Review not found"}, status=404)
            r.rating = int(float(rating_value))
            r.review = review_text
            r.save()
            return JsonResponse({
                "status": "success",
                "message": "Review updated successfully",
                "rating_id": r.id,
            }, status=200)

        if request.method == 'DELETE':
            if user is None:
                return JsonResponse({"message": "user_id is required"}, status=400)
            ids = list(qs.values_list('id', flat=True))
            deleted_count = qs.count()
            if deleted_count == 0:
                return JsonResponse({"message": "Review not found"}, status=404)
            qs.delete()
            try:
                Rating(product_id=canonical_id, business_id_id=business_id, rating=1).update_item_rating()
            except Exception:
                pass
            return JsonResponse({
                "status": "success",
                "message": "Review deleted successfully",
                "deleted_count": deleted_count,
                "deleted_ids": ids,
            }, status=200)

        return JsonResponse({"message": "Method not allowed"}, status=405)

    except Exception as e:
        logger.error(f"Error in item_review: {str(e)}")
        return JsonResponse({
            "message": f"Failed to process item review: {str(e)}"
        }, status=500)

        