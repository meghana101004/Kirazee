from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from django.db import transaction
from drf_yasg.utils import swagger_auto_schema
import logging

from .gro_models import GroceriesRatingHistory
from .gro_serializers import (
    CreateRatingHistorySerializer,
    GroceriesRatingHistorySerializer,
)
from kirazee_app.models import Registration, Business

logger = logging.getLogger(__name__)


@swagger_auto_schema(tags=['Consumer'])
class CreateRatingHistoryView(APIView):
    """
    Create a new product rating entry.

    URL: /rating-history/create/?user_id=<uid>&business_id=<bid>
    Method: POST
    Body:
    {
      "product_id": <int>,
      "order_id": <int optional>,
      "rating": 1-5,
      "review_title": "...",
      "review_text": "..."
    }
    """
    def post(self, request, *args, **kwargs):
        user_id = request.query_params.get('user_id')
        business_id = request.query_params.get('business_id')
        if not user_id or not business_id:
            return Response({"error": "user_id and business_id query parameters are required"}, status=status.HTTP_400_BAD_REQUEST)

        # Optional: Validate existence of Registration and Business for clearer errors
        try:
            Registration.objects.get(user_id=user_id)
        except Registration.DoesNotExist:
            return Response({"error": "User not found"}, status=status.HTTP_404_NOT_FOUND)
        try:
            Business.objects.get(business_id=business_id)
        except Business.DoesNotExist:
            return Response({"error": "Business not found"}, status=status.HTTP_404_NOT_FOUND)

        serializer = CreateRatingHistorySerializer(
            data=request.data,
            context={"user_id": user_id, "business_id": business_id, "request": request}
        )
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        try:
            instance = serializer.save()
        except Exception as e:
            logger.error(f"Failed to create rating history: {e}")
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

        out = GroceriesRatingHistorySerializer(instance)
        return Response(out.data, status=status.HTTP_201_CREATED)


@swagger_auto_schema(tags=['Consumer'])
class GetRatingHistoryView(APIView):
    """
    List rating history entries with filters and simple pagination.

    URL: /rating-history/?business_id=<bid>&user_id=<optional>&product_id=<optional>&order_id=<optional>&min_rating=<opt>&max_rating=<opt>&is_active=true&limit=20&offset=0
    """
    def get(self, request, *args, **kwargs):
        business_id = request.query_params.get('business_id')
        if not business_id:
            return Response({"error": "business_id query parameter is required"}, status=status.HTTP_400_BAD_REQUEST)

        # Filters
        user_id = request.query_params.get('user_id')
        product_id = request.query_params.get('product_id')
        order_id = request.query_params.get('order_id')
        min_rating = request.query_params.get('min_rating')
        max_rating = request.query_params.get('max_rating')
        is_active = request.query_params.get('is_active', 'true')
        limit = int(request.query_params.get('limit', 20))
        offset = int(request.query_params.get('offset', 0))

        try:
            qs = GroceriesRatingHistory.objects.select_related('user', 'product', 'business').filter(business_id=business_id)
            # Default to active ratings unless explicitly set otherwise
            if str(is_active).lower() in ('true', '1', 'yes', 'y'):
                qs = qs.filter(is_active=True)

            if user_id:
                qs = qs.filter(user_id=user_id)
            if product_id:
                qs = qs.filter(product_id=product_id)
            if order_id:
                qs = qs.filter(order_id=order_id)
            if min_rating:
                qs = qs.filter(rating__gte=int(min_rating))
            if max_rating:
                qs = qs.filter(rating__lte=int(max_rating))

            total = qs.count()
            items = qs.order_by('-created_at')[offset:offset+limit]
            data = GroceriesRatingHistorySerializer(items, many=True).data

            return Response({
                'business_id': str(business_id),
                'count': total,
                'limit': limit,
                'offset': offset,
                'results': data,
            }, status=status.HTTP_200_OK)
        except Exception as e:
            logger.error(f"Error fetching rating history: {e}")
            return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
