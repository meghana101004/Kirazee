from django.conf import settings
from django.utils import timezone
from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework import status
from rest_framework.views import APIView
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.db.models import Avg, Count
from drf_yasg.utils import swagger_auto_schema
from django.db import connection
import logging

from business.models import MenuItems
from consumer.gro_models import GroceriesProducts, GroceriesProductVariants
from kirazee_app.models import Business
from .models import Feedback, Wishlist
from kirazee_app.models import Registration

logger = logging.getLogger(__name__)

# Import BusinessFeedback model from gro_models
from .gro_models import BusinessFeedback

# Serializers for BusinessFeedback
class BusinessFeedbackCreateSerializer:
    def __init__(self, data):
        self.data = data
        self.errors = {}
        
    def is_valid(self):
        items = self.data.get('items', [])
        if not items:
            self.errors['items'] = 'At least one feedback item is required'
            return False
        
        for item in items:
            if 'rating' not in item or not isinstance(item['rating'], int) or item['rating'] < 1 or item['rating'] > 5:
                self.errors['items'] = 'Each item must have a rating between 1 and 5'
                return False
        
        return True
    
    @property
    def validated_data(self):
        return self.data

class BusinessFeedbackSerializer:
    def __init__(self, instance, many=False):
        self.instance = instance
        self.many = many
        
    @property
    def data(self):
        if self.many:
            return [self._serialize_item(item) for item in self.instance]
        return self._serialize_item(self.instance)
    
    def _serialize_item(self, item):
        return {
            'feedback_id': item.feedback_id,
            'business_id': item.business.business_id,
            'user_id': item.user.user_id,
            'user_name': item.user_name,
            'email': item.email,
            'question': item.question,
            'rating': item.rating,
            'additional_comments': item.additional_comments,
            'created_at': item.created_at.isoformat() if item.created_at else None,
        }

class BusinessFeedbackView(APIView):
    """
    POST: Create multiple feedback entries for a business and user.
      - URL params: business_id (required), user_id (required)
      - Body: { user_name?, email?, additional_comments?, items: [{question, rating}, ...] }

    GET: List feedback entries, filtered by business_id (required) and optional user_id.
      - URL params: business_id (required), user_id (optional)
    """
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
                    user_name=user_name or '',
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

    def get(self, request, *args, **kwargs):
        business_id = request.query_params.get('business_id')
        if not business_id:
            return Response({'error': 'business_id parameter is required.'}, status=status.HTTP_400_BAD_REQUEST)

        included_business_ids = _resolve_included_business_ids(business_id)

        qs = BusinessFeedback.objects.filter(business_id__in=included_business_ids).order_by('-created_at')
        user_id = request.query_params.get('user_id')
        if user_id:
            qs = qs.filter(user_id=user_id)

        # Optional: group averages by question
        try:
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

@swagger_auto_schema(methods=['GET'],tags=['Consumer'])
@api_view(['GET'])
def business_feedback_combined(request):
    business_id = request.query_params.get('business_id')
    if not business_id:
        return Response({'error': 'business_id parameter is required.'}, status=status.HTTP_400_BAD_REQUEST)

    try:
        business = Business.objects.get(business_id=business_id)
    except Business.DoesNotExist:
        return Response({'error': 'Business not found.'}, status=status.HTTP_404_NOT_FOUND)

    included_business_ids = _resolve_included_business_ids(business_id)
    ids_placeholder = ",".join(["%s"] * len(included_business_ids)) if included_business_ids else "%s"

    qs = BusinessFeedback.objects.filter(business_id__in=included_business_ids).order_by('-created_at')
    try:
        agg = (
            qs.values('question')
              .annotate(avg_rating=Avg('rating'), responses=Count('feedback_id'))
              .order_by('question')
        )
        bf_summary = [
            {
                'question': row['question'],
                'avg_rating': round(float(row['avg_rating'] or 0.0), 2),
                'responses': int(row['responses'] or 0),
            }
            for row in agg
        ]
    except Exception:
        bf_summary = []
    bf_results = BusinessFeedbackSerializer(qs[:500], many=True).data

    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT AVG(r.rating), COUNT(r.id)
            FROM rating r
            WHERE r.business_id IN (""" + ids_placeholder + ")\n            """,
            included_business_ids
        )
        row = cursor.fetchone() or (None, 0)
        avg_rating = round(float(row[0]), 2) if row and row[0] is not None else None
        total_ratings = int(row[1] or 0)

        cursor.execute(
            """
            SELECT r.rating, COUNT(*) 
            FROM rating r
            WHERE r.business_id IN (""" + ids_placeholder + ")\n            GROUP BY r.rating\n            ORDER BY r.rating DESC\n            """,
            included_business_ids
        )
        rating_distribution = {f"{int(rating)}_star": count for rating, count in cursor.fetchall()}

        cursor.execute(
            """
            SELECT r.rating, r.review, r.created_at, r.username, r.product_id,
                   COALESCE(
                       m.item_name, 
                       g.item_name,
                       fp.name,
                       gp.product_name,
                       vp.product_name,
                       oi.item_name_snapshot,
                       bci.item_name
                   ) AS item_name
            FROM rating r
            LEFT JOIN menuItems m ON r.product_id = m.item_id
            LEFT JOIN GroceryItems g ON r.product_id = g.item_id
            LEFT JOIN fashion_products fp ON r.product_id = fp.product_id
            LEFT JOIN Groceries_Products gp ON r.product_id = gp.product_id
            LEFT JOIN vendor_products vp ON r.product_id = vp.product_id
            LEFT JOIN order_items oi ON r.product_id = oi.product_item_id AND oi.item_name_snapshot IS NOT NULL
            LEFT JOIN business_counter_items bci ON r.product_id = bci.product_id AND bci.item_name IS NOT NULL
            WHERE r.business_id IN (""" + ids_placeholder + ")\n            ORDER BY r.created_at DESC\n            LIMIT 10\n            """,
            included_business_ids
        )
        recent_reviews = []
        for rating_val, review_text, created_at, username, product_id, item_name in cursor.fetchall():
            recent_reviews.append({
                "rating": int(rating_val) if rating_val is not None else None,
                "review": review_text or "",
                "date": created_at.isoformat() if hasattr(created_at, "isoformat") and created_at else None,
                "username": username or "Anonymous User",
                "product_id": product_id,
                "item_name": item_name or (f"Item {product_id}" if product_id else None),
            })

        cursor.execute(
            """
            SELECT r.product_id,
                   COALESCE(
                       m.item_name, 
                       g.item_name,
                       fp.name,
                       gp.product_name,
                       vp.product_name,
                       oi.item_name_snapshot,
                       bci.item_name
                   ) AS item_name,
                   AVG(r.rating) AS avg_rating,
                   COUNT(*) AS total_reviews
            FROM rating r 
            LEFT JOIN menuItems m ON r.product_id = m.item_id
            LEFT JOIN GroceryItems g ON r.product_id = g.item_id
            LEFT JOIN fashion_products fp ON r.product_id = fp.product_id
            LEFT JOIN Groceries_Products gp ON r.product_id = gp.product_id
            LEFT JOIN vendor_products vp ON r.product_id = vp.product_id
            LEFT JOIN order_items oi ON r.product_id = oi.product_item_id AND oi.item_name_snapshot IS NOT NULL
            LEFT JOIN business_counter_items bci ON r.product_id = bci.product_id AND bci.item_name IS NOT NULL
            WHERE r.business_id IN (""" + ids_placeholder + ") AND r.product_id IS NOT NULL\n            GROUP BY r.product_id, item_name\n            ORDER BY total_reviews DESC\n            LIMIT 200\n            """,
            included_business_ids
        )
        per_item_summary = []
        for product_id, item_name, avg_rt, cnt in cursor.fetchall():
            per_item_summary.append({
                "product_id": product_id,
                "item_name": item_name or f"Item {product_id}",
                "average_rating": round(float(avg_rt or 0.0), 2),
                "total_reviews": int(cnt or 0),
            })

        cursor.execute(
            """
            SELECT r.order_id,
                   AVG(r.rating) AS avg_rating,
                   COUNT(*) AS total_reviews,
                   MAX(r.created_at) AS last_review_at
            FROM rating r
            WHERE r.business_id IN (""" + ids_placeholder + ") AND r.order_id IS NOT NULL\n            GROUP BY r.order_id\n            ORDER BY last_review_at DESC\n            LIMIT 200\n            """,
            included_business_ids
        )
        order_reviews = []
        for oid, avg_rt, cnt, last_dt in cursor.fetchall():
            order_reviews.append({
                "order_id": int(oid),
                "average_rating": round(float(avg_rt or 0.0), 2),
                "total_reviews": int(cnt or 0),
                "last_review_at": last_dt.isoformat() if hasattr(last_dt, "isoformat") and last_dt else None,
            })

    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT f.feedback_id, f.user_id, f.username, f.rating, f.comments, f.created_at
            FROM feedback f
            WHERE EXISTS (
                SELECT 1 FROM orders o WHERE o.user_id = f.user_id AND o.business_id IN (""" + ids_placeholder + ")\n            )\n            ORDER BY f.created_at DESC\n            LIMIT 200\n            """,
            included_business_ids
        )
        website_feedback = []
        for feedback_id, uid, username, frating, comments, created_at in cursor.fetchall():
            website_feedback.append({
                "feedback_id": int(feedback_id),
                "user_id": uid,
                "username": username or "Anonymous User",
                "rating": int(frating) if frating is not None else None,
                "comments": comments or "",
                "created_at": created_at.isoformat() if hasattr(created_at, "isoformat") and created_at else None,
            })
        cursor.execute(
            """
            SELECT AVG(f.rating), COUNT(*)
            FROM feedback f 
            WHERE EXISTS (
                SELECT 1 FROM orders o WHERE o.user_id = f.user_id AND o.business_id IN (""" + ids_placeholder + ")\n            )\n            """,
            included_business_ids
        )
        row2 = cursor.fetchone() or (None, 0)
        website_feedback_avg = round(float(row2[0]), 2) if row2 and row2[0] is not None else None
        website_feedback_total = int(row2[1] or 0)

    return Response({
        'business_id': business_id,
        'business_name': getattr(business, 'businessName', None),
        'ratings': {
            'average_rating': avg_rating,
            'total_reviews': total_ratings,
            'rating_distribution': rating_distribution,
            'recent_reviews': recent_reviews,
            'per_item_summary': per_item_summary,
            'order_reviews': order_reviews,
        },
        'business_feedback': {
            'total': qs.count(),
            'summary': bf_summary,
            'results': bf_results,
        },
        'website_feedback': {
            'average_rating': website_feedback_avg,
            'total': website_feedback_total,
            'results': website_feedback,
        }
    }, status=status.HTTP_200_OK)

def _resolve_included_business_ids(base_business_id):
    try:
        b = Business.objects.get(business_id=base_business_id)
        level_text = (b.level or '').strip().lower()
    except Business.DoesNotExist:
        level_text = ''
    child_ids = list(Business.objects.filter(master=base_business_id).values_list('business_id', flat=True))
    is_master = ('master' in level_text) or bool(child_ids)
    included = [str(base_business_id)]
    if is_master and child_ids:
        included.extend([str(x) for x in child_ids])
    return included

@swagger_auto_schema(methods=['POST', 'GET'],tags=['Consumer'])
@api_view(['POST', 'GET'])
def feedback(request):
    """
    POST/GET website feedback with 1-5 rating and emoji-friendly comments.

    POST /kirazee/consumer/feedback/?user_id=[optional]
    Body:
    {
        "rating": 1-5,
        "comments": "text with emojis 😊👍"  # optional
    }

    GET /kirazee/consumer/feedback/?user_id=14771&rating=5&limit=20&offset=0
    - All filters optional. Returns paginated list.
    - user_id: Filter by user
    - rating: Filter by rating (1-5)
    - limit/offset: Pagination controls
    """
    try:
        if request.method == "POST":
            user_id_param = request.query_params.get("user_id")
            data = request.data or {}

            rating_val = data.get("rating")
            comments = data.get("comments", "")

            # Validate rating
            try:
                rating_int = int(float(rating_val))
                if rating_int < 1 or rating_int > 5:
                    return JsonResponse(
                        {"message": "Rating must be between 1 and 5"}, 
                        status=400
                    )
            except (TypeError, ValueError):
                return JsonResponse(
                    {"message": "Rating is required and must be a number between 1 and 5"}, 
                    status=400
                )

            # Resolve user (optional)
            user_obj = None
            display_name = "Anonymous"
            if user_id_param:
                try:
                    user_obj = Registration.objects.get(user_id=user_id_param)
                    display_name = f"{user_obj.firstName} {user_obj.lastName}".strip() or str(user_obj.user_id)
                except Registration.DoesNotExist:
                    # Continue as anonymous user if user not found
                    pass

            # Create feedback
            # In the POST handler where we create the feedback:
            fb = Feedback.objects.create(
                user_id=user_obj,  # Will be None if user not provided/not found
                rating=rating_int,
                comments=comments,
                username=display_name or "Anonymous"
            )

            return JsonResponse({
                "success": True,
                "message": "Feedback submitted successfully",
                "data": {
                    "feedback_id": fb.feedback_id,
                    "user_id": user_obj.user_id if user_obj else None,
                    "username": fb.username,
                    "rating": fb.rating,
                    "comments": fb.comments,
                    "created_at": fb.created_at.isoformat()
                }
            }, status=200)

        else:  # GET request
            user_id = request.query_params.get("user_id")
            rating_filter = request.query_params.get("rating")
            
            try:
                limit = min(int(request.query_params.get("limit", 20)), 100)
                offset = max(int(request.query_params.get("offset", 0)), 0)
            except (TypeError, ValueError):
                return JsonResponse(
                    {"message": "limit/offset must be integers"}, 
                    status=400
                )

            qs = Feedback.objects.all().order_by("-created_at")
            
            if user_id:
                qs = qs.filter(user_id__user_id=user_id)
            if rating_filter:
                try:
                    qs = qs.filter(rating=int(float(rating_filter)))
                except (TypeError, ValueError):
                    return JsonResponse(
                        {"message": "rating filter must be a number"}, 
                        status=400
                    )

            total = qs.count()
            items = list(qs[offset:offset + limit])

            data = []
            for fb in items:
                data.append({
                    "feedback_id": fb.feedback_id,
                    "user_id": fb.user_id.user_id if fb.user_id else None,
                    "username": fb.username,
                    "rating": fb.rating,
                    "comments": fb.comments or "",
                    "created_at": fb.created_at.isoformat(),
                })

            # Calculate average rating
            try:
                avg_rating = qs.aggregate(avg=Avg("rating")).get("avg")
                avg_rating = round(float(avg_rating), 2) if avg_rating is not None else None
            except Exception:
                avg_rating = None

            return JsonResponse({
                "success": True,
                "count": len(data),
                "total": total,
                "average_rating": avg_rating,
                "pagination": {
                    "limit": limit,
                    "offset": offset,
                    "has_next": (offset + limit) < total,
                    "next_offset": (offset + limit) if (offset + limit) < total else None,
                    "prev_offset": max(offset - limit, 0) if offset > 0 else None
                },
                "data": data
            }, status=200)

    except Exception as e:
        return JsonResponse({
            "success": False,
            "message": f"Failed to process feedback: {str(e)}"
        }, status=500)

@swagger_auto_schema(methods=['POST', 'GET', 'DELETE'],tags=['Consumer'])
@api_view(['POST', 'GET', 'DELETE'])
def wishlist_operations(request):
    """
    Wishlist Operations
    
    POST /kirazee/consumer/wishlist/?user_id=<user_id>
    {
        "item_id": 123,
        "business_id": "BUS123",
        "item_type": "menu"  # or "grocery"
    }
    
    GET /kirazee/consumer/wishlist/?user_id=<user_id>&business_type=<business_type>&business_id=<business_id>&limit=10&offset=0
    
    DELETE /kirazee/consumer/wishlist/?user_id=<user_id>&item_id=123&item_type=menu
    
    DELETE /kirazee/consumer/wishlist/clear/?user_id=<user_id>
    """
    try:
        user_id = request.query_params.get('user_id')
        if not user_id:
            return Response(
                {"success": False, "message": "user_id is required"},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Get or validate user
        try:
            user = Registration.objects.get(user_id=user_id)
        except Registration.DoesNotExist:
            return Response(
                {"success": False, "message": "User not found"},
                status=status.HTTP_404_NOT_FOUND
            )

        # Support clear-all via query param
        clear_param = request.query_params.get('clear') or request.query_params.get('clear_all')
        if clear_param and clear_param.lower() in ('1', 'true', 'yes'):
            return clear_all_wishlist(request, user)

        if request.method == 'POST':
            return add_to_wishlist(request, user)
        elif request.method == 'GET':
            return get_wishlist(request, user)
        elif request.method == 'DELETE':
            return remove_from_wishlist(request, user)

    except Exception as e:
        return Response(
            {"success": False, "message": f"Error: {str(e)}"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )

def add_to_wishlist(request, user):
    data = request.data
    item_id = data.get('item_id')
    variant_id = data.get('variant_id')
    business_id = data.get('business_id')
    item_type_raw = data.get('item_type')
    item_type = (item_type_raw or '').lower()

    if not business_id:
        return Response(
            {"success": False, "message": "business_id is required"},
            status=status.HTTP_400_BAD_REQUEST
        )

    if not item_id and not variant_id:
        return Response(
            {"success": False, "message": "item_id or variant_id is required"},
            status=status.HTTP_400_BAD_REQUEST
        )

    if item_type and item_type not in ['menu', 'grocery']:
        return Response(
            {"success": False, "message": "item_type must be either 'menu' or 'grocery'"},
            status=status.HTTP_400_BAD_REQUEST
        )

    try:
        business = Business.objects.get(business_id=business_id)

        try:
            user_obj = Registration.objects.get(user_id=user.user_id)
        except Registration.DoesNotExist:
            return Response(
                {"success": False, "message": "User not found"},
                status=status.HTTP_404_NOT_FOUND
            )

        resolved_item_type = None
        resolved_item_id = None

        if item_type == 'menu':
            if not item_id:
                return Response(
                    {"success": False, "message": "item_id is required for menu items"},
                    status=status.HTTP_400_BAD_REQUEST
                )
            MenuItems.objects.get(item_id=item_id, business_id=business_id)
            resolved_item_type = 'menu'
            resolved_item_id = item_id
        else:
            if variant_id:
                variant = GroceriesProductVariants.objects.select_related('product').get(variant_id=variant_id)
                product = variant.product
                prod_business_id = getattr(product, 'business_id', None) or getattr(getattr(product, 'business', None), 'business_id', None)
                if str(prod_business_id) != str(business_id):
                    return Response(
                        {"success": False, "message": "Business or item not found"},
                        status=status.HTTP_404_NOT_FOUND
                    )
                resolved_item_type = 'grocery'
                resolved_item_id = product.product_id
            else:
                try:
                    product_obj = GroceriesProducts.objects.get(product_id=item_id, business_id=business_id)
                    resolved_item_type = 'grocery'
                    resolved_item_id = product_obj.product_id
                except GroceriesProducts.DoesNotExist:
                    # Fallback: treat provided item_id as a grocery variant_id
                    variant = GroceriesProductVariants.objects.select_related('product').get(variant_id=item_id)
                    product = variant.product
                    prod_business_id = getattr(product, 'business_id', None) or getattr(getattr(product, 'business', None), 'business_id', None)
                    if str(prod_business_id) != str(business_id):
                        return Response(
                            {"success": False, "message": "Business or item not found"},
                            status=status.HTTP_404_NOT_FOUND
                        )
                    resolved_item_type = 'grocery'
                    resolved_item_id = product.product_id

        wishlist_item, created = Wishlist.objects.get_or_create(
            user=user_obj,
            item_id=resolved_item_id,
            business=business,
            item_type=resolved_item_type,
            defaults={'created_at': timezone.now()}
        )

        if not created:
            return Response(
                {"success": False, "message": "Item already in wishlist"},
                status=status.HTTP_400_BAD_REQUEST
            )

        return Response({
            "success": True,
            "message": "Item added to wishlist",
            "wishlist_id": wishlist_item.wishlist_id
        }, status=status.HTTP_201_CREATED)

    except (Business.DoesNotExist, MenuItems.DoesNotExist, GroceriesProducts.DoesNotExist, GroceriesProductVariants.DoesNotExist) as e:
        return Response(
            {"success": False, "message": "Business or item not found"},
            status=status.HTTP_404_NOT_FOUND
        )
    except Exception as e:
        return Response(
            {"success": False, "message": f"Failed to add to wishlist: {str(e)}"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )

def get_wishlist(request, user):
    try:
        business_type = request.query_params.get('business_type')
        business_id = request.query_params.get('business_id')
        limit = int(request.query_params.get('limit', 10))
        offset = int(request.query_params.get('offset', 0))
        
        # Base query
        wishlist_items = Wishlist.objects.filter(user=user).select_related('business').order_by('-created_at')
        
        # Filter by business type if provided
        if business_type:
            wishlist_items = wishlist_items.filter(
                business__businessType__iexact=business_type
            )
            
        # Filter by business_id if provided
        if business_id:
            wishlist_items = wishlist_items.filter(
                business__business_id=business_id
            )

        total_items = wishlist_items.count()
        paginated_items = wishlist_items[offset:offset + limit]

        # Prepare response data
        items = []
        for item in paginated_items:
            item_data = {
                "wishlist_id": item.wishlist_id,
                "item_id": item.item_id,
                "item_type": item.item_type,
                "business_id": item.business.business_id,
                "business_name": item.business.businessName,
                "business_type": item.business.businessType,
                "added_date": item.created_at.isoformat(),
            }

            # Get item details based on type
            if item.item_type == 'menu':
                menu_item = MenuItems.objects.filter(
                    item_id=item.item_id,
                    business_id=item.business_id
                ).first()
                if menu_item:
                    # Build image URL if image exists
                    image_url = None
                    if menu_item.item_image:
                        from consumer.image_utils import build_s3_file_url
                        image_url = build_s3_file_url(menu_item.item_image)
                    
                    item_data.update({
                        "name": menu_item.item_name,
                        "image": image_url,
                        "price": str(menu_item.selling_price) if hasattr(menu_item, 'selling_price') else None,
                        "description": menu_item.description
                    })
            else:  # grocery
                grocery_item = GroceriesProducts.objects.filter(
                    product_id=item.item_id,
                    business_id=item.business_id
                ).first()
                if grocery_item:
                    # Handle image URL with base URL
                    image_url = None
                    if grocery_item.main_image:
                        from consumer.image_utils import build_s3_file_url
                        image_url = build_s3_file_url(grocery_item.main_image)
                    
                    variant = (GroceriesProductVariants.objects
                               .filter(product_id=grocery_item.product_id, is_active=True)
                               .exclude(selling_price__isnull=True)
                               .order_by('selling_price')
                               .first())
                    derived_price = str(variant.selling_price) if variant and variant.selling_price is not None else None
                    item_data.update({
                        "name": grocery_item.product_name,
                        "image": image_url,
                        "price": derived_price,
                        "description": grocery_item.description
                    })

            items.append(item_data)

        return Response({
            "success": True,
            "total_items": total_items,
            "count": len(items),
            "offset": offset,
            "limit": limit,
            "data": items
        })

    except Exception as e:
        return Response(
            {"success": False, "message": f"Failed to fetch wishlist: {str(e)}"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )

def remove_from_wishlist(request, user):
    item_id = request.query_params.get('item_id')
    item_type = request.query_params.get('item_type', 'menu').lower()

    if not item_id:
        return Response(
            {"success": False, "message": "item_id is required"},
            status=status.HTTP_400_BAD_REQUEST
        )

    try:
        deleted_count, _ = Wishlist.objects.filter(
            user=user,
            item_id=item_id,
            item_type=item_type
        ).delete()

        if deleted_count == 0:
            return Response(
                {"success": False, "message": "Item not found in wishlist"},
                status=status.HTTP_404_NOT_FOUND
            )

        return Response({
            "success": True,
            "message": "Item removed from wishlist"
        })

    except Exception as e:
        return Response(
            {"success": False, "message": f"Failed to remove item: {str(e)}"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )

def clear_all_wishlist(request, user):
    """
    Remove all items from the user's wishlist.
    Expected query param: clear=1 or clear_all=true
    """
    try:
        deleted_count, _ = Wishlist.objects.filter(user=user).delete()

        return Response({
            "success": True,
            "message": f"All {deleted_count} items removed from wishlist",
            "deleted_count": deleted_count
        })

    except Exception as e:
        return Response(
            {"success": False, "message": f"Failed to clear wishlist: {str(e)}"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )

@swagger_auto_schema(methods=['GET'],tags=['Consumer'])
@api_view(['GET'])
def feedback_form_page(request):
    """
    Serve a simple HTML feedback form page that integrates with BusinessFeedbackView API
    URL: /consumer/feedback-form/?business_id=123&user_id=456&order_id=789&order_type=restaurant
    """
    business_id = request.GET.get('business_id')
    user_id = request.GET.get('user_id') 
    order_id = request.GET.get('order_id')
    order_type = request.GET.get('order_type', 'restaurant')
    
    # Get business name for display
    business_name = "Business"
    if business_id:
        try:
            business = Business.objects.get(business_id=business_id)
            business_name = business.businessName
        except Business.DoesNotExist:
            pass
    
    # HTML feedback form
    html_content = f"""
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Feedback - {business_name} | Kirazee</title>
        <style>
            body {{
                font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
                max-width: 600px;
                margin: 20px auto;
                padding: 20px;
                min-height: 100vh;
            }}
            .feedback-container {{
                background: white;
                padding: 30px;
                border-radius: 15px;
                box-shadow: 0 10px 30px rgba(0,0,0,0.2);
            }}
            .header {{
                text-align: center;
                margin-bottom: 30px;
                color: #333;
            }}
            .header h1 {{
                color: #667eea;
                margin-bottom: 10px;
            }}
            .order-info {{
                background: #f8f9fa;
                padding: 20px;
                border-radius: 10px;
                margin-bottom: 25px;
                border-left: 4px solid #667eea;
            }}
            .rating-section {{
                margin: 25px 0;
                padding: 20px;
                border: 1px solid #eee;
                border-radius: 10px;
                background: #fafafa;
            }}
            .stars {{
                font-size: 35px;
                color: #ddd;
                cursor: pointer;
                text-align: center;
                margin: 10px 0;
            }}
            .stars .star.active {{
                color: #ffc107;
            }}
            .stars .star:hover {{
                color: #ffc107;
            }}
            .form-group {{
                margin: 20px 0;
            }}
            label {{
                display: block;
                margin-bottom: 8px;
                font-weight: 600;
                color: #333;
            }}
            input, textarea {{
                width: 100%;
                padding: 12px;
                border: 2px solid #ddd;
                border-radius: 8px;
                font-size: 14px;
                transition: border-color 0.3s;
                box-sizing: border-box;
            }}
            input:focus, textarea:focus {{
                outline: none;
                border-color: #667eea;
            }}
            textarea {{
                height: 100px;
                resize: vertical;
            }}
            .submit-btn {{
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                color: white;
                padding: 15px 40px;
                border: none;
                border-radius: 8px;
                cursor: pointer;
                font-size: 16px;
                font-weight: 600;
                width: 100%;
                transition: transform 0.2s;
            }}
            .submit-btn:hover {{
                transform: translateY(-2px);
            }}
            .submit-btn:disabled {{
                opacity: 0.6;
                cursor: not-allowed;
                transform: none;
            }}
            .success-message {{
                background: #d4edda;
                color: #155724;
                padding: 15px;
                border-radius: 8px;
                margin: 20px 0;
                display: none;
            }}
            .error-message {{
                background: #f8d7da;
                color: #721c24;
                padding: 15px;
                border-radius: 8px;
                margin: 20px 0;
                display: none;
            }}
        </style>
    </head>
    <body>
        <div class="feedback-container">
            <div class="header">
                <h1>Share Your Feedback</h1>
                <p>Help us improve by sharing your experience with <strong>{business_name}</strong></p>
            </div>
            <div class="success-message" id="successMessage">
                ✅ Thank you for your feedback! Your response has been submitted successfully.
            </div>
            
            <div class="error-message" id="errorMessage">
                ❌ <span id="errorText">Error submitting feedback. Please try again.</span>
            </div>

            <form id="feedbackForm">
                <div class="rating-section">
                    <label>Rate your order</label>
                    <div class="stars" data-question="How would you rate the food quality?">
                        <span class="star" data-rating="1">★</span>
                        <span class="star" data-rating="2">★</span>
                        <span class="star" data-rating="3">★</span>
                        <span class="star" data-rating="4">★</span>
                        <span class="star" data-rating="5">★</span>
                    </div>
                </div>

                <div class="form-group">
                    <label for="additionalComments">Write a review</label>
                    <textarea id="additionalComments" name="additional_comments" placeholder="Share your experience with this order ..."></textarea>
                </div>

                <button type="submit" class="submit-btn" id="submitBtn">Submit Feedback</button>
            </form>
        </div>

        <script>
            const businessId = '{business_id}';
            const userId = '{user_id}';
            const orderId = '{order_id}';
            
            // Star rating functionality
            const starGroups = document.querySelectorAll('.stars');
            const ratings = {{}};

            starGroups.forEach(group => {{
                const stars = group.querySelectorAll('.star');
                const question = group.dataset.question;
                
                stars.forEach((star, index) => {{
                    star.addEventListener('click', () => {{
                        const rating = parseInt(star.dataset.rating);
                        ratings[question] = rating;
                        
                        // Update visual state
                        stars.forEach((s, i) => {{
                            if (i < rating) {{
                                s.classList.add('active');
                            }} else {{
                                s.classList.remove('active');
                            }}
                        }});
                    }});
                    
                    star.addEventListener('mouseover', () => {{
                        const rating = parseInt(star.dataset.rating);
                        stars.forEach((s, i) => {{
                            if (i < rating) {{
                                s.style.color = '#ffc107';
                            }} else {{
                                s.style.color = '#ddd';
                            }}
                        }});
                    }});
                }});
                
                group.addEventListener('mouseleave', () => {{
                    const currentRating = ratings[question] || 0;
                    stars.forEach((s, i) => {{
                        if (i < currentRating) {{
                            s.style.color = '#ffc107';
                        }} else {{
                            s.style.color = '#ddd';
                        }}
                    }});
                }});
            }});

            // Form submission
            document.getElementById('feedbackForm').addEventListener('submit', async (e) => {{
                e.preventDefault();
                
                const submitBtn = document.getElementById('submitBtn');
                const successMsg = document.getElementById('successMessage');
                const errorMsg = document.getElementById('errorMessage');
                const errorText = document.getElementById('errorText');
                
                // Hide messages
                successMsg.style.display = 'none';
                errorMsg.style.display = 'none';
                
                const formData = new FormData(e.target);
                const additionalComments = formData.get('additional_comments');
                
                // Prepare feedback items
                const items = [];
                Object.keys(ratings).forEach(question => {{
                    items.push({{
                        question: question,
                        rating: ratings[question]
                    }});
                }});
                
                if (items.length === 0) {{
                    errorText.textContent = 'Please provide at least one rating before submitting.';
                    errorMsg.style.display = 'block';
                    return;
                }}
                
                const feedbackData = {{
                    additional_comments: additionalComments,
                    items: items
                }};
                
                submitBtn.disabled = true;
                submitBtn.textContent = 'Submitting...';
                
                try {{
                    const response = await fetch(`/kirazee/consumer/business-feedback/?business_id=${{businessId}}&user_id=${{userId}}`, {{
                        method: 'POST',
                        headers: {{
                            'Content-Type': 'application/json',
                            'X-CSRFToken': getCookie('csrftoken')
                        }},
                        body: JSON.stringify(feedbackData)
                    }});
                    
                    if (response.ok) {{
                        const result = await response.json();
                        successMsg.style.display = 'block';
                        document.getElementById('feedbackForm').style.display = 'none';
                        
                        // Scroll to success message
                        successMsg.scrollIntoView({{ behavior: 'smooth' }});
                    }} else {{
                        const error = await response.json();
                        errorText.textContent = 'Error: ' + (error.error || 'Unknown error occurred');
                        errorMsg.style.display = 'block';
                    }}
                }} catch (error) {{
                    console.error('Error:', error);
                    errorText.textContent = 'Network error. Please check your connection and try again.';
                    errorMsg.style.display = 'block';
                }} finally {{
                    submitBtn.disabled = false;
                    submitBtn.textContent = 'Submit Feedback';
                }}
            }});
            
            // Get CSRF token
            function getCookie(name) {{
                let cookieValue = null;
                if (document.cookie && document.cookie !== '') {{
                    const cookies = document.cookie.split(';');
                    for (let i = 0; i < cookies.length; i++) {{
                        const cookie = cookies[i].trim();
                        if (cookie.substring(0, name.length + 1) === (name + '=')) {{
                            cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
                            break;
                        }}
                    }}
                }}
                return cookieValue;
            }}
        </script>
    </body>
    </html>
    """
    
    from django.http import HttpResponse
    return HttpResponse(html_content, content_type='text/html')
