from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework import status
from django.db import connection
from consumer.models import DeliveryCharges
from consumer.serializers import DeliveryChargesSerializer
from kirazee_app.models import BusinessMapping
from drf_yasg.utils import swagger_auto_schema
import logging

logger = logging.getLogger(__name__)

@swagger_auto_schema(methods=['DELETE'], tags=['Business'])
@api_view(['DELETE'])
def delete_delivery_configuration(request):
    """
    Delete delivery configuration for business
    DELETE /business/delivery-config/?user_id=123&business_id=KIR147712008250306
    """
    try:
        user_id = request.GET.get('user_id')
        business_id = request.GET.get('business_id')
        
        # business_id is required for delete operation
        if not business_id:
            return Response({
                'success': False,
                'message': 'business_id is required'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Verify business exists and is active (simplified validation)
        with connection.cursor() as cursor:
            cursor.execute("""
                SELECT business_id, businessName, level, master, status
                FROM businesses 
                WHERE business_id = %s AND status = 1
            """, [business_id])
            
            business = cursor.fetchone()
            if not business:
                return Response({
                    'success': False,
                    'message': 'Business not found or inactive'
                }, status=status.HTTP_404_NOT_FOUND)

        # Delete delivery configuration
        try:
            delivery_config = DeliveryCharges.objects.get(business_id=business_id)
            delivery_config.delete()
            
            return Response({
                'success': True,
                'message': 'Delivery configuration deleted successfully'
            }, status=status.HTTP_200_OK)
            
        except DeliveryCharges.DoesNotExist:
            return Response({
                'success': False,
                'message': 'No delivery configuration found for this business'
            }, status=status.HTTP_404_NOT_FOUND)

    except Exception as e:
        logger.error(f"Error deleting delivery configuration: {str(e)}")
        return Response({
            'success': False,
            'message': f'Error deleting delivery configuration: {str(e)}'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@swagger_auto_schema(methods=['GET'], tags=['Business'])
@api_view(['GET'])
def list_all_delivery_configurations(request):
    """
    List all delivery configurations with pagination and filtering
    GET /business/delivery-configs/?page=1&limit=20&business_id=KIR123&is_active=true
    """
    try:
        page = int(request.GET.get('page', 1))
        limit = min(int(request.GET.get('limit', 20)), 100)
        offset = (page - 1) * limit
        
        business_id_filter = request.GET.get('business_id')
        is_active_filter = request.GET.get('is_active')
        
        # Build query filters
        filters = {}
        if business_id_filter:
            filters['business_id'] = business_id_filter
        if is_active_filter is not None:
            filters['is_active'] = is_active_filter.lower() == 'true'
        
        # Get total count
        total_count = DeliveryCharges.objects.filter(**filters).count()
        
        # Get paginated results
        delivery_configs = DeliveryCharges.objects.filter(**filters).order_by('-created_at')[offset:offset+limit]
        
        # Serialize data
        serializer = DeliveryChargesSerializer(delivery_configs, many=True)
        
        # Calculate pagination info
        total_pages = (total_count + limit - 1) // limit
        has_next = page < total_pages
        has_prev = page > 1
        
        return Response({
            'success': True,
            'message': f'Retrieved {len(serializer.data)} delivery configurations',
            'pagination': {
                'total_configurations': total_count,
                'current_page': page,
                'per_page': limit,
                'total_pages': total_pages,
                'has_next_page': has_next,
                'has_prev_page': has_prev
            },
            'data': serializer.data
        }, status=status.HTTP_200_OK)
        
    except Exception as e:
        logger.error(f"Error listing delivery configurations: {str(e)}")
        return Response({
            'success': False,
            'message': f'Error listing delivery configurations: {str(e)}'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@swagger_auto_schema(methods=['PUT'], tags=['Business'])
@api_view(['PUT'])
def update_delivery_configuration(request, delivery_id):
    """
    Update specific delivery configuration by ID
    PUT /business/delivery-config/{delivery_id}/
    """
    try:
        # Get delivery configuration
        try:
            delivery_config = DeliveryCharges.objects.get(delivery_id=delivery_id)
        except DeliveryCharges.DoesNotExist:
            return Response({
                'success': False,
                'message': 'Delivery configuration not found'
            }, status=status.HTTP_404_NOT_FOUND)
        
        # Verify business exists and is active (simplified validation)
        business_id = delivery_config.business_id
        with connection.cursor() as cursor:
            cursor.execute("""
                SELECT business_id, businessName, level, master, status
                FROM businesses 
                WHERE business_id = %s AND status = 1
            """, [business_id])
            
            business = cursor.fetchone()
            if not business:
                return Response({
                    'success': False,
                    'message': 'Business not found or inactive'
                }, status=status.HTTP_404_NOT_FOUND)
        
        # Update configuration
        serializer = DeliveryChargesSerializer(delivery_config, data=request.data, partial=True)
        
        if serializer.is_valid():
            serializer.save()
            return Response({
                'success': True,
                'message': 'Delivery configuration updated successfully',
                'data': serializer.data
            }, status=status.HTTP_200_OK)
        else:
            return Response({
                'success': False,
                'message': 'Invalid delivery configuration data',
                'errors': serializer.errors
            }, status=status.HTTP_400_BAD_REQUEST)
            
    except Exception as e:
        logger.error(f"Error updating delivery configuration: {str(e)}")
        return Response({
            'success': False,
            'message': f'Error updating delivery configuration: {str(e)}'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
