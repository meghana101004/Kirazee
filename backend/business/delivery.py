from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework import status
from django.db import transaction, connection
from consumer.models import DeliveryCharges, BusinessOrderTypes
from consumer.serializers import DeliveryChargesSerializer
from kirazee_app.models import BusinessMapping
from drf_yasg.utils import swagger_auto_schema
from drf_yasg import openapi
import json
import logging

logger = logging.getLogger(__name__)

# delivery_partner/views.py
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework_simplejwt.authentication import JWTAuthentication
from geopy.distance import geodesic
from django.db import connection, transaction
from datetime import datetime, timedelta

from consumer.models import Orders, Payments, create_status_log
from consumer.gro_models import GroceriesOrders
from kirazee_app.models import Business, Registration
from delivery.models import DeliveryPartner, OrderOTP
from delivery.views import GroceryOrdersService

from delivery.serializers import (
    DeliveryPartnerSerializer, 
    LocationSerializer,
    NearbyOrdersSerializer,
    OrderAssignmentSerializer,
    UserProfileSerializer,
    DeliveryPartnerProfileSerializer,
    CombinedProfileSerializer,
    ActiveDeliveryPartnerSerializer,
    OrderAssignmentSerializer,
    DeliveryOrderSerializer, DeliveryPartnerRegistrationSerializer
)
from django.conf import settings
from django.core.mail import send_mail
from django.core.cache import cache
from django.utils import timezone
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync
from urllib.parse import urljoin
from business.image_utils import build_s3_file_url
from types import SimpleNamespace
from django.urls import get_script_prefix
from decimal import Decimal
from dateutil import parser as date_parser
import json
import re
import logging

logger = logging.getLogger(__name__)
from notifications.hooks import on_order_status, on_otp_sent

@swagger_auto_schema(methods=['POST'], tags=['Business'])
@api_view(['POST'])
def configure_delivery_charges(request):
    """
    Configure delivery charges for business
    POST /business/configure-delivery/
    Body: {
        "user_id": 14774,  // Optional
        "business_id": "KIR147712008250306",  // Required
        "base_charge": 30.00,
        "distance_slabs": [...],
        "free_delivery_above": 500.00,
        ...
    }
    """
    try:
        user_id = request.data.get('user_id')  # Optional
        business_id = request.data.get('business_id')
        
        # If business_id not provided, try to get it from business mapping (if user_id provided)
        if not business_id:
            if user_id:
                try:
                    business_mapping = BusinessMapping.objects.get(user_id=user_id)
                    business_id = business_mapping.business_id
                except BusinessMapping.DoesNotExist:
                    return Response({
                        'success': False,
                        'message': 'Business not found for this user'
                    }, status=status.HTTP_404_NOT_FOUND)
            else:
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

        # Prepare delivery data
        delivery_data = request.data.copy()
        delivery_data['business_id'] = business_id

        # Check if configuration already exists
        existing_config = DeliveryCharges.objects.filter(business_id=business_id).first()
        
        if existing_config:
            # Update existing configuration
            serializer = DeliveryChargesSerializer(existing_config, data=delivery_data, partial=True)
        else:
            # Create new configuration
            serializer = DeliveryChargesSerializer(data=delivery_data)

        if serializer.is_valid():
            delivery_config = serializer.save()
            return Response({
                'success': True,
                'message': 'Delivery charges configured successfully',
                'data': serializer.data
            }, status=status.HTTP_200_OK if existing_config else status.HTTP_201_CREATED)
        else:
            return Response({
                'success': False,
                'message': 'Invalid delivery configuration data',
                'errors': serializer.errors
            }, status=status.HTTP_400_BAD_REQUEST)

    except Exception as e:
        return Response({
            'success': False,
            'message': f'Error configuring delivery charges: {str(e)}'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@swagger_auto_schema(methods=['GET'], tags=['Business'])
@api_view(['GET'])
def get_delivery_configuration(request):
    """
    Get delivery configuration for business
    GET /business/delivery-config/?business_id=KIR147712008250306
    Optional: user_id for additional validation if needed
    """
    try:
        user_id = request.GET.get('user_id')  # Optional
        business_id = request.GET.get('business_id')
        
        if not business_id:
            return Response({
                'success': False,
                'message': 'business_id is required'
            }, status=status.HTTP_400_BAD_REQUEST)

        # Verify business exists and is active
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

        # Get delivery configuration
        try:
            delivery_config = DeliveryCharges.objects.get(business_id=business_id, is_active=True)
            serializer = DeliveryChargesSerializer(delivery_config)
            
            return Response({
                'success': True,
                'message': 'Delivery configuration retrieved successfully',
                'data': serializer.data
            }, status=status.HTTP_200_OK)
            
        except DeliveryCharges.DoesNotExist:
            return Response({
                'success': False,
                'message': 'No delivery configuration found for this business'
            }, status=status.HTTP_404_NOT_FOUND)

    except Exception as e:
        return Response({
            'success': False,
            'message': f'Error retrieving delivery configuration: {str(e)}'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@swagger_auto_schema(methods=['POST'], tags=['Business'])
@api_view(['POST'])
def configure_points_system(request):
    """
    Configure points earning system for business
    POST /business/configure-points/
    Body: {
        "user_id": 14774,
        "business_id": "KIR147712008250306",  // Optional - if not provided, derived from user_id
        "points_per_rupee_spent": 2.00,
        "points_per_rupee_value": 0.10,
        ...
    }
    """
    try:
        user_id = request.data.get('user_id')
        business_id = request.data.get('business_id')
        
        if not user_id:
            return Response({
                'success': False,
                'message': 'user_id is required'
            }, status=status.HTTP_400_BAD_REQUEST)

        # If business_id not provided, get it from business mapping
        if not business_id:
            try:
                business_mapping = BusinessMapping.objects.get(user_id=user_id)
                business_id = business_mapping.business_id
            except BusinessMapping.DoesNotExist:
                return Response({
                    'success': False,
                    'message': 'Business not found for this user'
                }, status=status.HTTP_404_NOT_FOUND)
        else:
            # Verify user has access to the specified business_id (including sublevel businesses)
            from django.db import connection
            with connection.cursor() as cursor:
                cursor.execute("""
                    SELECT COUNT(*) FROM (
                        -- Direct business ownership
                        SELECT b.business_id
                        FROM business_mapping bm
                        INNER JOIN businesses b ON bm.business_id = b.business_id
                        WHERE bm.user_id = %s AND bm.status = 1 AND b.business_id = %s
                        
                        UNION
                        
                        -- Sublevel businesses owned by user's master business
                        SELECT sb.business_id
                        FROM business_mapping bm
                        INNER JOIN businesses mb ON bm.business_id = mb.business_id
                        INNER JOIN businesses sb ON mb.business_id = sb.master
                        WHERE bm.user_id = %s AND bm.status = 1 AND sb.business_id = %s AND sb.status = 1
                    ) AS accessible_businesses
                """, [user_id, business_id, user_id, business_id])
                
                has_access = cursor.fetchone()[0] > 0
                if not has_access:
                    return Response({
                        'success': False,
                        'message': 'User does not have access to this business'
                    }, status=status.HTTP_403_FORBIDDEN)

        from consumer.models import PointsConfiguration
        from consumer.serializers import PointsConfigurationSerializer

        # Prepare points data
        points_data = request.data.copy()
        points_data['business_id'] = business_id

        # Check if configuration already exists
        existing_config = PointsConfiguration.objects.filter(business_id=business_id).first()
        
        if existing_config:
            # Update existing configuration
            serializer = PointsConfigurationSerializer(existing_config, data=points_data, partial=True)
        else:
            # Create new configuration
            serializer = PointsConfigurationSerializer(data=points_data)

        if serializer.is_valid():
            points_config = serializer.save()
            return Response({
                'success': True,
                'message': 'Points system configured successfully',
                'data': serializer.data
            }, status=status.HTTP_200_OK if existing_config else status.HTTP_201_CREATED)
        else:
            return Response({
                'success': False,
                'message': 'Invalid points configuration data',
                'errors': serializer.errors
            }, status=status.HTTP_400_BAD_REQUEST)

    except Exception as e:
        return Response({
            'success': False,
            'message': f'Error configuring points system: {str(e)}'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@swagger_auto_schema(methods=['GET'], tags=['Business'])
@api_view(['GET'])
def get_points_configuration(request):
    """
    Get points configuration for business
    GET /business/points-config/?user_id=123&business_id=KIR147712008250306
    """
    try:
        user_id = request.GET.get('user_id')
        business_id = request.GET.get('business_id')
        
        if not user_id:
            return Response({
                'success': False,
                'message': 'user_id is required'
            }, status=status.HTTP_400_BAD_REQUEST)

        # If business_id not provided, get it from business mapping
        if not business_id:
            try:
                business_mapping = BusinessMapping.objects.get(user_id=user_id)
                business_id = business_mapping.business_id
            except BusinessMapping.DoesNotExist:
                return Response({
                    'success': False,
                    'message': 'Business not found for this user'
                }, status=status.HTTP_404_NOT_FOUND)
        else:
            # Verify user has access to the specified business_id (including sublevel businesses)
            from django.db import connection
            with connection.cursor() as cursor:
                cursor.execute("""
                    SELECT COUNT(*) FROM (
                        -- Direct business ownership
                        SELECT b.business_id
                        FROM business_mapping bm
                        INNER JOIN businesses b ON bm.business_id = b.business_id
                        WHERE bm.user_id = %s AND bm.status = 1 AND b.business_id = %s
                        
                        UNION
                        
                        -- Sublevel businesses owned by user's master business
                        SELECT sb.business_id
                        FROM business_mapping bm
                        INNER JOIN businesses mb ON bm.business_id = mb.business_id
                        INNER JOIN businesses sb ON mb.business_id = sb.master
                        WHERE bm.user_id = %s AND bm.status = 1 AND sb.business_id = %s AND sb.status = 1
                    ) AS accessible_businesses
                """, [user_id, business_id, user_id, business_id])
                
                has_access = cursor.fetchone()[0] > 0
                if not has_access:
                    return Response({
                        'success': False,
                        'message': 'User does not have access to this business'
                    }, status=status.HTTP_403_FORBIDDEN)

        from consumer.models import PointsConfiguration
        from consumer.serializers import PointsConfigurationSerializer

        # Get points configuration
        try:
            points_config = PointsConfiguration.objects.get(business_id=business_id, is_active=True)
            serializer = PointsConfigurationSerializer(points_config)
            
            return Response({
                'success': True,
                'message': 'Points configuration retrieved successfully',
                'data': serializer.data
            }, status=status.HTTP_200_OK)
            
        except PointsConfiguration.DoesNotExist:
            return Response({
                'success': False,
                'message': 'No points configuration found for this business'
            }, status=status.HTTP_404_NOT_FOUND)

    except Exception as e:
        return Response({
            'success': False,
            'message': f'Error retrieving points configuration: {str(e)}'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@swagger_auto_schema(methods=['POST'], tags=['Business'])
@api_view(['POST'])
def configure_order_types(request):
    """
    Configure allowed order types for a business
    POST /business/order-types/configure/
    Body: {
        "user_id": 14774,               # Optional (used to resolve business_id)
        "business_id": "KIR...",      # Optional if user_id is provided
        "order_types": ["delivery", "takeaway"],  # Allowed values
        "is_cod_available": true      # Optional: Whether COD is available (default: false)
    }
    """
    try:
        user_id = request.data.get('user_id')
        business_id = request.data.get('business_id')
        order_types = request.data.get('order_types') or []
        is_cod_available = request.data.get('is_cod_available', False)

        # Resolve business_id from user_id if needed
        if not business_id:
            if user_id:
                try:
                    mapping = BusinessMapping.objects.get(user_id=user_id)
                    business_id = mapping.business_id
                except BusinessMapping.DoesNotExist:
                    return Response({'success': False, 'message': 'Business not found for this user'}, status=status.HTTP_404_NOT_FOUND)
            else:
                return Response({'success': False, 'message': 'business_id or user_id is required'}, status=status.HTTP_400_BAD_REQUEST)

        # Validate business exists and active
        with connection.cursor() as cursor:
            cursor.execute("""
                SELECT business_id, businessType, status
                FROM businesses
                WHERE business_id = %s AND status = 1
            """, [business_id])
            row = cursor.fetchone()
            if not row:
                return Response({'success': False, 'message': 'Business not found or inactive'}, status=status.HTTP_404_NOT_FOUND)
            business_type = row[1]

        # Normalize and validate order types
        if not isinstance(order_types, list):
            return Response({'success': False, 'message': 'order_types must be a list'}, status=status.HTTP_400_BAD_REQUEST)
        normalized = [str(t).lower().replace('-', '_') for t in order_types]
        valid = {'delivery', 'pickup', 'takeaway', 'dine_in', 'pick_up', 'pick-up'}
        for t in normalized:
            if t not in valid:
                return Response({'success': False, 'message': f"Invalid order type '{t}'. Allowed: {sorted(list(valid))}"}, status=status.HTTP_400_BAD_REQUEST)

        # Upsert configuration
        from kirazee_app.models import Business as Biz
        biz = Biz.objects.get(business_id=business_id)
        existing = BusinessOrderTypes.objects.filter(business=biz).first()
        if existing:
            existing.order_types = normalized
            existing.is_cod_available = bool(is_cod_available)
            existing.is_active = True
            existing.save(update_fields=['order_types', 'is_cod_available', 'is_active', 'updated_at'])
            obj = existing
            created = False
        else:
            obj = BusinessOrderTypes.objects.create(
                business=biz, 
                order_types=normalized, 
                is_cod_available=bool(is_cod_available),
                is_active=True
            )
            created = True

        return Response({
            'success': True,
            'message': 'Order types configured successfully' if created else 'Order types updated successfully',
            'data': {
                'business_id': business_id,
                'business_type': business_type,
                'order_types': obj.order_types,
                'is_cod_available': obj.is_cod_available
            }
        }, status=status.HTTP_201_CREATED if created else status.HTTP_200_OK)

    except Exception as e:
        return Response({'success': False, 'message': f'Error configuring order types: {str(e)}'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@swagger_auto_schema(methods=['GET'], tags=['Business'])
@api_view(['GET'])
def get_order_types(request):
    """
    Get allowed order types for a business or all businesses by type
    GET /business/order-types/?business_id=KIR... (single business)
    GET /business/order-types/?business_type=R01/R02/R08 (all businesses of type)
    Optional: user_id to resolve business_id when not provided
    """
    try:
        user_id = request.GET.get('user_id')
        business_id = request.GET.get('business_id')
        business_type = request.GET.get('business_type')

        from kirazee_app.models import Business as Biz

        # Check if business_type is provided - return all businesses of that type
        if business_type and not business_id:
            # Validate business_type
            if business_type not in ['R01', 'R02', 'R08']:
                return Response({'success': False, 'message': 'Invalid business_type. Must be R01, R02, or R08'}, status=status.HTTP_400_BAD_REQUEST)

            # Get all businesses of the specified type
            businesses = Biz.objects.filter(businessType=business_type, status=True).values('business_id', 'businessName', 'businessType')
            
            if not businesses:
                return Response({'success': False, 'message': f'No businesses found for type {business_type}'}, status=status.HTTP_404_NOT_FOUND)

            # Get order types for all businesses
            result = []
            for business in businesses:
                biz_id = business['business_id']
                biz_name = business['businessName']
                
                try:
                    biz_obj = Biz.objects.get(business_id=biz_id)
                    configured = BusinessOrderTypes.objects.filter(business=biz_obj, is_active=True).first()
                    
                    if configured and configured.order_types:
                        types = [str(t).lower().replace('-', '_') for t in configured.order_types]
                        cod_available = configured.is_cod_available
                        source = 'configured'
                    else:
                        types = BusinessOrderTypes.default_for_business_type(biz_obj.businessType)
                        cod_available = False  # Default to False for unconfigured businesses
                        source = 'default'

                    result.append({
                        'business_id': biz_id,
                        'business_name': biz_name,
                        'business_type': business['businessType'],
                        'allowed_order_types': types,
                        'cod': cod_available,
                        'source': source
                    })
                except Exception as e:
                    # Skip businesses with errors but continue processing others
                    continue

            return Response({
                'success': True,
                'data': {
                    'business_type': business_type,
                    'businesses': result,
                    'total_count': len(result)
                }
            }, status=status.HTTP_200_OK)

        # Original logic for single business
        if not business_id:
            if user_id:
                try:
                    mapping = BusinessMapping.objects.get(user_id=user_id)
                    business_id = mapping.business_id
                except BusinessMapping.DoesNotExist:
                    return Response({'success': False, 'message': 'Business not found for this user'}, status=status.HTTP_404_NOT_FOUND)
            else:
                # If neither business_id nor business_type is provided, return all businesses with their order types
                all_businesses = Biz.objects.filter(status=True).values('business_id', 'businessName', 'businessType')
                result = []
                for business in all_businesses:
                    biz_id = business['business_id']
                    biz_name = business['businessName']
                    try:
                        biz_obj = Biz.objects.get(business_id=biz_id)
                        configured = BusinessOrderTypes.objects.filter(business=biz_obj, is_active=True).first()
                        
                        if configured and configured.order_types:
                            types = [str(t).lower().replace('-', '_') for t in configured.order_types]
                            cod_available = configured.is_cod_available
                            source = 'configured'
                        else:
                            types = BusinessOrderTypes.default_for_business_type(biz_obj.businessType)
                            cod_available = False
                            source = 'default'

                        result.append({
                            'business_id': biz_id,
                            'business_name': biz_name,
                            'business_type': business['businessType'],
                            'allowed_order_types': types,
                            'cod': cod_available,
                            'source': source
                        })
                    except Exception as e:
                        continue

                return Response({
                    'success': True,
                    'data': {
                        'businesses': result,
                        'total_count': len(result)
                    }
                }, status=status.HTTP_200_OK)

        try:
            biz = Biz.objects.get(business_id=business_id)
        except Biz.DoesNotExist:
            return Response({'success': False, 'message': 'Business not found'}, status=status.HTTP_404_NOT_FOUND)

        configured = BusinessOrderTypes.objects.filter(business=biz, is_active=True).first()
        if configured and configured.order_types:
            types = [str(t).lower().replace('-', '_') for t in configured.order_types]
            cod_available = configured.is_cod_available
            source = 'configured'
        else:
            types = BusinessOrderTypes.default_for_business_type(biz.businessType)
            cod_available = False  # Default to False for unconfigured businesses
            source = 'default'

        return Response({
            'success': True,
            'data': {
                'business_id': business_id,
                'business_type': biz.businessType,
                'allowed_order_types': types,
                'cod': cod_available,
                'source': source
            }
        }, status=status.HTTP_200_OK)

    except Exception as e:
        return Response({'success': False, 'message': f'Error retrieving order types: {str(e)}'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

@swagger_auto_schema(methods=['GET'], tags=['Business'])
@api_view(['GET'])
def order_online_history(request):
    """
    Get comprehensive order history for business owners
    GET /business/order-online-history/?business_id=[value]&status=[optional]&limit=[optional]&offset=[optional]
    
    Shows orders from both standard orders and grocery orders tables
    Status categories: pending, confirmed, picked_up, travelling, ready, dispatched, out_for_delivery, delivered, completed, cancelled
    """
    try:
        business_id = request.GET.get('business_id')
        status_filter = request.GET.get('status')  # Optional status filter
        limit_param = request.GET.get('limit')
        per_page_param = request.GET.get('per_page')
        if limit_param is not None:
            if str(limit_param).lower() == 'all':
                per_page = None
            else:
                per_page = int(limit_param)
        elif per_page_param is not None:
            if str(per_page_param).lower() == 'all':
                per_page = None
            else:
                per_page = int(per_page_param)
        else:
            per_page = 1000
        offset = int(request.GET.get('offset', 0))  # Default offset 0
        if per_page is None:
            offset = 0
        
        if not business_id:
            return Response({
                'success': False,
                'message': 'business_id parameter is required'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Validate per_page
        per_page = per_page
            
        with connection.cursor() as cursor:
            # Check if this business is a master business and get all related business IDs
            cursor.execute("""
                SELECT business_id, businessName, level 
                FROM businesses 
                WHERE business_id = %s
            """, [business_id])
            
            main_business = cursor.fetchone()
            if not main_business:
                return Response({
                    'success': False,
                    'message': 'Business not found'
                }, status=status.HTTP_404_NOT_FOUND)
            
            business_ids = [business_id]
            business_names = {business_id: main_business[1]}
            is_master = main_business[2] == 'master'
            
            # If this is a master business, get all sub-businesses
            if is_master:
                cursor.execute("""
                    SELECT business_id, businessName 
                    FROM businesses 
                    WHERE master = %s
                """, [business_id])
                
                sub_businesses = cursor.fetchall()
                for sub_business in sub_businesses:
                    business_ids.append(sub_business[0])
                    business_names[sub_business[0]] = sub_business[1]
            
            # Build business ID filter condition
            business_placeholders = ','.join(['%s'] * len(business_ids))
            business_condition_standard = f"AND o.business_id IN ({business_placeholders})"
            business_condition_grocery = f"AND go.business_id IN ({business_placeholders})"
            
            # Build status filter condition
            status_condition_standard = ""
            status_condition_grocery = ""
            status_params = []
            if status_filter:
                status_condition_standard = "AND o.status = %s"
                status_condition_grocery = "AND go.order_status = %s"
                status_params.append(status_filter)
            
            # Query for standard orders (restaurant orders)
            standard_orders_query = f"""
                SELECT 
                    o.order_id,
                    CAST(o.order_number AS CHAR(255)) COLLATE utf8mb4_0900_ai_ci as order_number,
                    CAST(o.status AS CHAR(50)) COLLATE utf8mb4_0900_ai_ci as status,
                    CAST(o.order_type AS CHAR(50)) COLLATE utf8mb4_0900_ai_ci as order_type,
                    o.total_amount,
                    o.delivery_charges,
                    CAST(COALESCE(p.payment_method, 'N/A') AS CHAR(50)) COLLATE utf8mb4_0900_ai_ci as payment_method,
                    CAST(COALESCE(p.status, 'pending') AS CHAR(50)) COLLATE utf8mb4_0900_ai_ci as payment_status,
                    o.created_at,
                    o.updated_at,
                    o.delivery_partner_id,
                    o.estimated_delivery_time,
                    o.actual_delivery_time,
                    CAST(r.displayName AS CHAR(255)) COLLATE utf8mb4_0900_ai_ci as customer_name,
                    CAST(r.mobileNumber AS CHAR(50)) COLLATE utf8mb4_0900_ai_ci as customer_phone,
                    CAST(dp.phone_number AS CHAR(50)) COLLATE utf8mb4_0900_ai_ci as delivery_partner_phone,
                    CAST(dp_reg.displayName AS CHAR(255)) COLLATE utf8mb4_0900_ai_ci as delivery_partner_name,
                    CAST('standard' AS CHAR(20)) COLLATE utf8mb4_0900_ai_ci as order_system,
                    COALESCE(oi_count.item_count, 0) as total_items,
                    o.delivery_address_snapshot,
                    CAST(o.delivery_instruction AS CHAR) COLLATE utf8mb4_0900_ai_ci as delivery_instructions,
                    CAST(o.order_instruction AS CHAR) COLLATE utf8mb4_0900_ai_ci as order_instructions,
                    CAST(CASE 
                        WHEN o.status = 'pending' THEN 'Pending'
                        WHEN o.status = 'confirmed' THEN 'Confirmed'
                        WHEN o.status = 'preparing' THEN 'Preparing'
                        WHEN o.status = 'ready' THEN 'Ready'
                        WHEN o.status = 'assigned' THEN 'Assigned'
                        WHEN o.status = 'picked_up' THEN 'Picked Up'
                        WHEN o.status = 'travelling' THEN 'Travelling'
                        WHEN o.status = 'dispatch' THEN 'Dispatched'
                        WHEN o.status = 'out_for_delivery' THEN 'Out for Delivery'
                        WHEN o.status = 'delivered' THEN 'Delivered'
                        WHEN o.status = 'completed' THEN 'Completed'
                        WHEN o.status = 'cancelled' THEN 'Cancelled'
                        ELSE CONCAT(UPPER(SUBSTRING(o.status, 1, 1)), LOWER(SUBSTRING(o.status, 2)))
                    END AS CHAR(50)) COLLATE utf8mb4_0900_ai_ci as status_display,
                    CAST(o.business_id AS CHAR(64)) COLLATE utf8mb4_0900_ai_ci as business_id,
                    CAST(b.businessName AS CHAR(255)) COLLATE utf8mb4_0900_ai_ci as businessName,
                    o.token_num as token_num
                FROM orders o
                LEFT JOIN businesses b ON o.business_id = b.business_id
                LEFT JOIN registrations r ON o.user_id = r.user_id
                LEFT JOIN delivery_partner dp ON o.delivery_partner_id = dp.user_id
                LEFT JOIN registrations dp_reg ON dp.user_id = dp_reg.user_id
                LEFT JOIN (
                    SELECT p1.order_id, p1.payment_method, p1.status
                    FROM payments p1
                    INNER JOIN (
                        SELECT order_id, MAX(created_at) as max_created_at
                        FROM payments
                        GROUP BY order_id
                    ) p2 ON p1.order_id = p2.order_id AND p1.created_at = p2.max_created_at
                ) p ON o.order_id = p.order_id
                LEFT JOIN (
                    SELECT order_id, COUNT(*) as item_count 
                    FROM order_items 
                    GROUP BY order_id
                ) oi_count ON o.order_id = oi_count.order_id
                WHERE 1=1 {business_condition_standard} {status_condition_standard}
            """
            
            # Query for grocery orders
            grocery_orders_query = f"""
                SELECT 
                    go.order_id,
                    CAST(CONCAT('GRO-', go.order_id) AS CHAR(255)) COLLATE utf8mb4_0900_ai_ci as order_number,
                    CAST(go.order_status AS CHAR(50)) COLLATE utf8mb4_0900_ai_ci as status,
                    CAST(go.order_type AS CHAR(50)) COLLATE utf8mb4_0900_ai_ci as order_type,
                    go.total_amount,
                    0.0 as delivery_charges,
                    CAST(COALESCE(gp_pay.payment_method, 'N/A') AS CHAR(50)) COLLATE utf8mb4_0900_ai_ci as payment_method,
                    CAST(COALESCE(gp_pay.status, 'pending') AS CHAR(50)) COLLATE utf8mb4_0900_ai_ci as payment_status,
                    go.created_at,
                    go.updated_at,
                    gdd.partner_id as delivery_partner_id,
                    NULL as estimated_delivery_time,
                    gdd.delivered_at as actual_delivery_time,
                    CAST(r.displayName AS CHAR(255)) COLLATE utf8mb4_0900_ai_ci as customer_name,
                    CAST(r.mobileNumber AS CHAR(50)) COLLATE utf8mb4_0900_ai_ci as customer_phone,
                    CAST(dp.phone_number AS CHAR(50)) COLLATE utf8mb4_0900_ai_ci as delivery_partner_phone,
                    CAST(dp_reg.displayName AS CHAR(255)) COLLATE utf8mb4_0900_ai_ci as delivery_partner_name,
                    CAST('grocery' AS CHAR(20)) COLLATE utf8mb4_0900_ai_ci as order_system,
                    COALESCE(goi_count.item_count, 0) as total_items,
                    NULL as delivery_address_snapshot,
                    CAST(COALESCE(go.delivery_instructions, '') AS CHAR) COLLATE utf8mb4_0900_ai_ci as delivery_instructions,
                    CAST(NULL AS CHAR) COLLATE utf8mb4_0900_ai_ci as order_instructions,
                    CAST(CASE 
                        WHEN go.order_status = 'pending' THEN 'Pending'
                        WHEN go.order_status = 'confirmed' THEN 'Confirmed'
                        WHEN go.order_status = 'packed' THEN 'Packed'
                        WHEN go.order_status = 'ready' THEN 'Ready'
                        WHEN go.order_status = 'assigned' THEN 'Assigned'
                        WHEN go.order_status = 'picked_up' THEN 'Picked Up'
                        WHEN go.order_status = 'in_transit' THEN 'In Transit'
                        WHEN go.order_status = 'out_for_delivery' THEN 'Out for Delivery'
                        WHEN go.order_status = 'delivered' THEN 'Delivered'
                        WHEN go.order_status = 'completed' THEN 'Completed'
                        WHEN go.order_status = 'cancelled' THEN 'Cancelled'
                        ELSE CONCAT(UPPER(SUBSTRING(go.order_status, 1, 1)), LOWER(SUBSTRING(go.order_status, 2)))
                    END AS CHAR(50)) COLLATE utf8mb4_0900_ai_ci as status_display,
                    CAST(go.business_id AS CHAR(64)) COLLATE utf8mb4_0900_ai_ci as business_id,
                    CAST(b.businessName AS CHAR(255)) COLLATE utf8mb4_0900_ai_ci as businessName,
                    NULL as token_num
                FROM Groceries_orders go
                LEFT JOIN businesses b ON go.business_id = b.business_id
                LEFT JOIN registrations r ON go.user_id = r.user_id
                LEFT JOIN Grocery_deliver_details gdd ON go.order_id = gdd.order_id AND gdd.is_active = 1
                LEFT JOIN delivery_partner dp ON gdd.partner_id = dp.user_id
                LEFT JOIN registrations dp_reg ON dp.user_id = dp_reg.user_id
                LEFT JOIN (
                    SELECT gp1.order_id, gp1.payment_method, gp1.status
                    FROM payments gp1
                    INNER JOIN (
                        SELECT order_id, MAX(created_at) as max_created_at
                        FROM payments
                        GROUP BY order_id
                    ) gp2 ON gp1.order_id = gp2.order_id AND gp1.created_at = gp2.max_created_at
                ) gp_pay ON go.order_id = gp_pay.order_id
                LEFT JOIN (
                    SELECT order_id, COUNT(*) as item_count 
                    FROM Groceries_order_items 
                    GROUP BY order_id
                ) goi_count ON go.order_id = goi_count.order_id
                WHERE 1=1 {business_condition_grocery} {status_condition_grocery}
            """
            
            # Combine both queries with UNION ALL and add ordering and pagination
            if per_page is None:
                combined_query = f"""
                    SELECT * FROM (
                        {standard_orders_query}
                        UNION ALL
                        {grocery_orders_query}
                    ) combined_orders
                    ORDER BY created_at DESC
                """
                query_params = business_ids + status_params + business_ids + status_params
            else:
                combined_query = f"""
                    SELECT * FROM (
                        {standard_orders_query}
                        UNION ALL
                        {grocery_orders_query}
                    ) combined_orders
                    ORDER BY created_at DESC
                    LIMIT %s OFFSET %s
                """
                query_params = business_ids + status_params + business_ids + status_params + [per_page, offset]

            # Execute the combined query
            cursor.execute(combined_query, query_params)
            
            orders = cursor.fetchall()
            
            # Get total count for pagination
            count_query = f"""
                SELECT COUNT(*) FROM (
                    SELECT o.order_id FROM orders o WHERE 1=1 {business_condition_standard} {status_condition_standard}
                    UNION ALL
                    SELECT go.order_id FROM Groceries_orders go WHERE 1=1 {business_condition_grocery} {status_condition_grocery}
                ) total_orders
            """
            
            count_params = business_ids + status_params + business_ids + status_params
            cursor.execute(count_query, count_params)
            total_count = cursor.fetchone()[0]
            
            # Get status-wise counts
            status_counts_query = f"""
                SELECT 
                    status_category,
                    COUNT(*) as count
                FROM (
                    SELECT 
                        CASE 
                            WHEN o.status IN ('pending') THEN 'pending'
                            WHEN o.status IN ('confirmed', 'preparing') THEN 'confirmed'
                            WHEN o.status IN ('ready', 'assigned') THEN 'ready'
                            WHEN o.status IN ('picked_up', 'travelling', 'dispatch') THEN 'picked_up'
                            WHEN o.status IN ('out_for_delivery') THEN 'out_for_delivery'
                            WHEN o.status IN ('delivered', 'completed') THEN 'delivered'
                            WHEN o.status IN ('cancelled') THEN 'cancelled'
                            ELSE 'other'
                        END as status_category
                    FROM orders o WHERE o.business_id IN ({business_placeholders})
                    
                    UNION ALL
                    
                    SELECT 
                        CASE 
                            WHEN go.order_status IN ('pending') THEN 'pending'
                            WHEN go.order_status IN ('confirmed', 'packed') THEN 'confirmed'
                            WHEN go.order_status IN ('ready', 'assigned') THEN 'ready'
                            WHEN go.order_status IN ('picked_up', 'in_transit') THEN 'picked_up'
                            WHEN go.order_status IN ('out_for_delivery') THEN 'out_for_delivery'
                            WHEN go.order_status IN ('delivered', 'completed') THEN 'delivered'
                            WHEN go.order_status IN ('cancelled') THEN 'cancelled'
                            ELSE 'other'
                        END as status_category
                    FROM Groceries_orders go WHERE go.business_id IN ({business_placeholders})
                ) all_orders
                GROUP BY status_category
            """
            
            cursor.execute(status_counts_query, business_ids + business_ids)
            status_counts_raw = cursor.fetchall()
            
            # Convert status counts to dictionary
            status_counts = {}
            for status_cat, count in status_counts_raw:
                status_counts[status_cat] = count
            
            # Format orders data
            orders_data = []
            for order in orders:
                # Parse delivery address if it exists
                delivery_address = None
                if order[19]:  # delivery_address_snapshot
                    try:
                        delivery_address = json.loads(order[19]) if isinstance(order[19], str) else order[19]
                    except (json.JSONDecodeError, TypeError):
                        delivery_address = None
                
                order_data = {
                    'order_id': order[0],
                    'order_number': order[1],
                    'status': order[2],
                    'status_display': order[22],
                    'order_type': order[3],
                    'order_system': order[17],  # 'standard' or 'grocery'
                    'total_amount': float(order[4]) if order[4] else 0.0,
                    'delivery_charges': float(order[5]) if order[5] else 0.0,
                    'payment_method': order[6],
                    'payment_status': order[7],
                    'total_items': order[18],
                    'created_at': order[8].isoformat() if order[8] else None,
                    'updated_at': order[9].isoformat() if order[9] else None,
                    'estimated_delivery_time': order[11].isoformat() if order[11] else None,
                    'actual_delivery_time': order[12].isoformat() if order[12] else None,
                    'delivery_instructions': order[20],
                    'order_instructions': order[21],
                    'token_num': order[25] if order[17] == 'standard' else None,
                    'business': {
                        'business_id': order[23],  # business_id from query
                        'business_name': order[24]  # businessName from query
                    },
                    'customer': {
                        'name': order[13],
                        'phone': order[14]
                    },
                    'delivery_partner': {
                        'user_id': order[10],
                        'name': order[16],
                        'phone': order[15]
                    } if order[10] else None,
                    'delivery_address': delivery_address
                }
                orders_data.append(order_data)

            # Attach items and customizations
            try:
                with connection.cursor() as c2:
                    # Standard orders items
                    reg_ids = [o['order_id'] for o in orders_data if o.get('order_system') == 'standard']
                    if reg_ids:
                        ph = ','.join(['%s'] * len(reg_ids))
                        c2.execute(f"""
                            SELECT order_id, item_name_snapshot, quantity, customizations
                            FROM order_items
                            WHERE order_id IN ({ph})
                        """, reg_ids)
                        rows = c2.fetchall()
                        reg_map = {}
                        for oid, name, qty, custom in rows:
                            try:
                                parsed = json.loads(custom) if isinstance(custom, str) else custom
                            except Exception:
                                parsed = custom
                            reg_map.setdefault(oid, []).append({
                                'name': name,
                                'quantity': int(qty) if qty is not None else None,
                                'customizations': parsed if parsed is not None else []
                            })
                    else:
                        reg_map = {}

                    # Grocery orders items (no customizations supported)
                    gro_ids = [o['order_id'] for o in orders_data if o.get('order_system') == 'grocery']
                    if gro_ids:
                        ph = ','.join(['%s'] * len(gro_ids))
                        c2.execute(f"""
                            SELECT oi.order_id, p.product_name, oi.quantity
                            FROM Groceries_order_items oi
                            LEFT JOIN Groceries_Products p ON oi.product_id = p.product_id
                            WHERE oi.order_id IN ({ph})
                        """, gro_ids)
                        rows = c2.fetchall()
                        gro_map = {}
                        for oid, name, qty in rows:
                            gro_map.setdefault(oid, []).append({
                                'name': name,
                                'quantity': int(qty) if qty is not None else None,
                                'customizations': []
                            })
                    else:
                        gro_map = {}

                # Attach to each order
                for od in orders_data:
                    if od.get('order_system') == 'standard':
                        od['items'] = reg_map.get(od['order_id'], [])
                    else:
                        od['items'] = gro_map.get(od['order_id'], [])
            except Exception as e:
                logger.error(f"Failed to attach items/customizations in order_online_history: {e}")
            
            # Calculate pagination info
            if per_page is None:
                per_page_val = total_count
                total_pages = 1
                current_page = 1
                has_next = False
                has_prev = False
                next_offset = None
                prev_offset = None
            else:
                per_page_val = per_page
                total_pages = (total_count + per_page - 1) // per_page
                current_page = (offset // per_page) + 1
                has_next = offset + per_page < total_count
                has_prev = offset > 0
                next_offset = offset + per_page if has_next else None
                prev_offset = offset - per_page if has_prev else None
            
            return Response({
                'success': True,
                'message': f'Found {len(orders_data)} orders (showing {offset + 1}-{offset + len(orders_data)} of {total_count})',
                'business_id': business_id,
                'is_master_business': is_master,
                'businesses_included': [
                    {'business_id': bid, 'business_name': business_names[bid]} 
                    for bid in business_ids
                ],
                'pagination': {
                    'total_orders': total_count,
                    'current_page': current_page,
                    'per_page': per_page_val,
                    'total_pages': total_pages,
                    'has_next_page': has_next,
                    'has_prev_page': has_prev,
                    'next_offset': next_offset,
                    'prev_offset': prev_offset
                },
                'status_counts': {
                    'pending': status_counts.get('pending', 0),
                    'confirmed': status_counts.get('confirmed', 0),
                    'ready': status_counts.get('ready', 0),
                    'picked_up': status_counts.get('picked_up', 0),
                    'out_for_delivery': status_counts.get('out_for_delivery', 0),
                    'delivered': status_counts.get('delivered', 0),
                    'cancelled': status_counts.get('cancelled', 0),
                    'other': status_counts.get('other', 0),
                    'total': total_count
                },
                'orders': orders_data
            }, status=status.HTTP_200_OK)
            
    except ValueError as e:
        return Response({
            'success': False,
            'message': f'Invalid parameter value: {str(e)}'
        }, status=status.HTTP_400_BAD_REQUEST)
    except Exception as e:
        logger.error(f"Error retrieving order history for business {business_id}: {str(e)}")
        return Response({
            'success': False,
            'message': f'Error retrieving order history: {str(e)}'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@swagger_auto_schema(tags=['Business'])
class RBOPendingOrdersView(APIView):
    """
    GET /business/pending-orders/
    Fetch all pending orders from both orders and Groceries_orders tables with payment status
    
    Query Parameters:
    - business_id (optional): Filter by specific business
    - limit (optional): Limit number of results (default: 50, max: 100)
    - offset (optional): Offset for pagination (default: 0)
    - debug (optional): Enable debug mode to show item count details
    """
    
    @swagger_auto_schema(
        tags=['Business'],
        operation_summary='Get pending orders for business',
        operation_description='Fetch all pending orders from both orders and Groceries_orders tables with payment status',
        manual_parameters=[
            openapi.Parameter(
                'business_id',
                openapi.IN_QUERY,
                description='Filter by specific business',
                type=openapi.TYPE_STRING,
                required=False
            ),
            openapi.Parameter(
                'limit',
                openapi.IN_QUERY,
                description='Limit number of results (default: 50, max: 100)',
                type=openapi.TYPE_INTEGER,
                required=False
            ),
            openapi.Parameter(
                'offset',
                openapi.IN_QUERY,
                description='Offset for pagination (default: 0)',
                type=openapi.TYPE_INTEGER,
                required=False
            ),
            openapi.Parameter(
                'debug',
                openapi.IN_QUERY,
                description='Enable debug mode to show item count details',
                type=openapi.TYPE_BOOLEAN,
                required=False
            ),
        ],
        responses={
            200: openapi.Response(
                description='Pending orders retrieved successfully',
                examples={
                    'application/json': {
                        'success': True,
                        'message': 'Found X orders',
                        'orders': []
                    }
                }
            ),
            500: openapi.Response(
                description='Server error',
                examples={
                    'application/json': {
                        'success': False,
                        'message': 'Error fetching orders'
                    }
                }
            )
        }
    )
    def get(self, request):
        try:
            # Get query parameters
            business_id = request.query_params.get('business_id')
            limit = min(int(request.query_params.get('limit', 50)), 100)
            offset = int(request.query_params.get('offset', 0))
            
            regular_orders = []
            grocery_orders = []
            
            with connection.cursor() as cursor:
                # Get all business IDs to include (master + sub-businesses if applicable)
                business_ids_to_include = []
                business_names = {}
                is_master = False
                if business_id:
                    # Get main business info
                    cursor.execute("""
                        SELECT business_id, businessName, level 
                        FROM businesses 
                        WHERE business_id = %s AND status = 1
                    """, [business_id])
                    
                    business_info = cursor.fetchone()
                    if business_info:
                        business_ids_to_include.append(business_info[0])
                        business_names[business_info[0]] = business_info[1]
                        is_master = business_info[2] == 'master'
                        
                        # If this is a master business, get all sub-businesses
                        if is_master:
                            cursor.execute("""
                                SELECT business_id, businessName
                                FROM businesses 
                                WHERE master = %s AND status = 1
                            """, [business_id])
                            
                            sub_businesses = cursor.fetchall()
                            for sub_business in sub_businesses:
                                business_ids_to_include.append(sub_business[0])
                                business_names[sub_business[0]] = sub_business[1]
                
                # Fetch pending orders from regular orders table
                regular_query = """
                    SELECT 
                        o.order_id,
                        o.order_number,
                        o.order_type,
                        o.status as order_status,
                        COALESCE(latest_payment.status, 'pending') as payment_status,
                        o.total_amount,
                        o.final_amount,
                        o.delivery_charges as delivery_charge,
                        o.discount_amount as discount,
                        COALESCE(oi_count.total_gst, 0.00) as gst_amount,
                        
                        -- Customer details
                        o.user_id as customer_id,
                        CONCAT(COALESCE(r.firstName, ''), ' ', COALESCE(r.lastName, '')) as customer_name,
                        r.mobileNumber as customer_phone,
                        r.emailID as customer_email,
                        
                        -- Business details
                        o.business_id,
                        b.businessName as business_name,
                        bt.type as business_type,
                        
                        -- Address and delivery
                        CASE 
                            WHEN o.delivery_address_snapshot IS NOT NULL THEN 
                                CONCAT_WS(', ',
                                    NULLIF(CONCAT('Door No: ', JSON_UNQUOTE(JSON_EXTRACT(o.delivery_address_snapshot, '$."Door no"'))), 'Door No: '),
                                    NULLIF(JSON_UNQUOTE(JSON_EXTRACT(o.delivery_address_snapshot, '$.street')), ''),
                                    NULLIF(CONCAT('Near ', JSON_UNQUOTE(JSON_EXTRACT(o.delivery_address_snapshot, '$.landmark'))), 'Near '),
                                    NULLIF(JSON_UNQUOTE(JSON_EXTRACT(o.delivery_address_snapshot, '$."city/town"')), ''),
                                    NULLIF(JSON_UNQUOTE(JSON_EXTRACT(o.delivery_address_snapshot, '$.state')), ''),
                                    NULLIF(CONCAT('Pincode: ', JSON_UNQUOTE(JSON_EXTRACT(o.delivery_address_snapshot, '$.pincode'))), 'Pincode: ')
                                )
                            ELSE ua.address
                        END as delivery_address,
                        CAST(o.delivery_instruction AS CHAR) as delivery_instructions,
                        CAST(o.order_instruction AS CHAR) as order_instructions,
                        o.estimated_delivery_time as delivery_time,
                        o.scheduled_time as scheduled_time,
                        NULL as pickup_time,
                        
                        -- Order items count (using LEFT JOIN for better performance)
                        COALESCE(oi_count.item_count, 0) as items_count,
                        
                        -- Timestamps
                        o.created_at,
                        o.updated_at,
                        o.token_num as token_num,
                        
                        -- Company/B2B Details
                        o.order_customer_type,
                        o.company_id,
                        o.ordered_by_employee,
                        o.approval_status,
                        o.company_notes,
                        o.company_department,
                        o.company_purchase_order,
                        o.is_bulk_order,
                        cr.company_name,
                        cr.gst_number
                        
                    FROM orders o
                    LEFT JOIN registrations r ON o.user_id = r.user_id
                    LEFT JOIN businesses b ON o.business_id = b.business_id
                    LEFT JOIN business_types bt ON b.businessType = bt.code
                    LEFT JOIN user_address ua ON o.delivery_address_id = ua.id
                    LEFT JOIN company_registrations cr ON o.company_id = cr.company_id
                    LEFT JOIN (
                        SELECT p1.order_id, p1.status, p1.payment_method
                        FROM payments p1
                        INNER JOIN (
                            SELECT order_id, MAX(created_at) as max_created_at
                            FROM payments
                            GROUP BY order_id
                        ) p2 ON p1.order_id = p2.order_id AND p1.created_at = p2.max_created_at
                    ) latest_payment ON latest_payment.order_id = o.order_id
                    LEFT JOIN (
                        SELECT order_id, COUNT(*) as item_count, SUM(gst_amount) as total_gst
                        FROM order_items 
                        GROUP BY order_id
                    ) oi_count ON o.order_id = oi_count.order_id
                    WHERE 1=1
                """
                
                # Add business filter if provided
                regular_params = []
                if business_ids_to_include:
                    business_placeholders = ','.join(['%s'] * len(business_ids_to_include))
                    regular_query += f" AND o.business_id IN ({business_placeholders})"
                    regular_params.extend(business_ids_to_include)
                
                # Payment filter: include only successful payments OR COD
                regular_query += " AND (COALESCE(latest_payment.status, 'pending') = 'success' OR LOWER(COALESCE(latest_payment.payment_method, '')) = 'cod')"

                regular_query += " ORDER BY o.created_at DESC LIMIT %s OFFSET %s"
                regular_params.extend([limit, offset])
                
                cursor.execute(regular_query, regular_params)
                regular_results = cursor.fetchall()
                
                # Process regular orders
                for row in regular_results:
                    regular_orders.append({
                        'order_id': row[0],
                        'order_number': str(row[1]) if row[1] else None,
                        'order_type': row[2],
                        'order_status': row[3],
                        'payment_status': row[4],
                        'total_amount': float(row[5]) if row[5] else 0.0,
                        'final_amount': float(row[6]) if row[6] else 0.0,
                        'delivery_charge': float(row[7]) if row[7] else 0.0,
                        'discount': float(row[8]) if row[8] else 0.0,
                        'gst_amount': float(row[9]) if row[9] else 0.0,
                        'customer_id': row[10],
                        'customer_name': row[11].strip() if row[11] else 'Unknown Customer',
                        'customer_phone': row[12],
                        'customer_email': row[13],
                        'business_id': row[14],
                        'business_name': row[15],
                        'business_type': row[16],
                        'delivery_address': row[17],
                        'delivery_instructions': row[18],
                        'order_instructions': row[19],
                        'delivery_time': row[20],
                        'scheduled_time': row[21],
                        'pickup_time': row[22],
                        'items_count': row[23],
                        'created_at': row[24],
                        'updated_at': row[25],
                        'token_num': row[26],
                        'order_system': 'regular',
                        
                        # Company/B2B Information
                        'company_details': {
                            'company_name': row[35],
                            'gst_number': row[36],
                            'customer_type': row[27],
                            'company_id': row[28],
                            'employee_id': row[29],
                            'approval_status': row[30],
                            'company_notes': row[31],
                            'department': row[32],
                            'purchase_order': row[33],
                            'is_bulk_order': bool(row[34]),
                        } if row[28] else None
                    })
                
                # Fetch pending orders from Groceries_orders table
                grocery_query = """
                    SELECT 
                        go.order_id,
                        NULL as order_number,
                        go.order_type,
                        go.order_status,
                        go.payment_status,
                        go.total_amount,
                        go.final_amount,
                        go.delivery_charge,
                        go.discount,
                        go.gst_amount,
                        
                        -- Customer details
                        go.user_id as customer_id,
                        CONCAT(COALESCE(r.firstName, ''), ' ', COALESCE(r.lastName, '')) as customer_name,
                        r.mobileNumber as customer_phone,
                        r.emailID as customer_email,
                        
                        -- Business details
                        go.business_id,
                        b.businessName as business_name,
                        bt.type as business_type,
                        
                        -- Address and delivery
                        go.delivery_address,
                        go.delivery_instructions,
                        NULL as order_instructions,
                        go.delivery_time,
                        go.pickup_time,
                        
                        -- Order items count (using LEFT JOIN for better performance)
                        COALESCE(goi_count.item_count, 0) as items_count,
                        
                        -- Timestamps
                        go.created_at,
                        go.updated_at,
                        
                        -- Company/B2B Details
                        go.order_customer_type,
                        go.company_id,
                        go.ordered_by_employee,
                        go.approval_status,
                        go.company_notes,
                        go.company_department,
                        go.company_purchase_order,
                        go.is_bulk_order,
                        cr.company_name,
                        cr.gst_number
                        
                    FROM Groceries_orders go
                    LEFT JOIN registrations r ON go.user_id = r.user_id
                    LEFT JOIN businesses b ON go.business_id = b.business_id
                    LEFT JOIN business_types bt ON b.businessType = bt.code
                    LEFT JOIN company_registrations cr ON go.company_id = cr.company_id
                    LEFT JOIN (
                        SELECT gp1.order_id, gp1.payment_status, gp1.payment_method
                        FROM Groceries_payments gp1
                        INNER JOIN (
                            SELECT order_id, MAX(payment_date) as max_payment_date
                            FROM Groceries_payments
                            GROUP BY order_id
                        ) gp2 ON gp1.order_id = gp2.order_id AND gp1.payment_date = gp2.max_payment_date
                    ) latest_gpay ON latest_gpay.order_id = go.order_id
                    LEFT JOIN (
                        SELECT order_id, COUNT(*) as item_count 
                        FROM Groceries_order_items 
                        GROUP BY order_id
                    ) goi_count ON go.order_id = goi_count.order_id
                    WHERE 1=1
                """
                
                # Add business filter if provided
                grocery_params = []
                if business_ids_to_include:
                    business_placeholders = ','.join(['%s'] * len(business_ids_to_include))
                    grocery_query += f" AND go.business_id IN ({business_placeholders})"
                    grocery_params.extend(business_ids_to_include)
                
                # Payment filter: include only paid orders OR cash (COD)
                grocery_query += " AND (LOWER(go.payment_status) = 'paid' OR LOWER(COALESCE(latest_gpay.payment_method, '')) = 'cash')"

                grocery_query += " ORDER BY go.created_at DESC LIMIT %s OFFSET %s"
                grocery_params.extend([limit, offset])
                
                cursor.execute(grocery_query, grocery_params)
                grocery_results = cursor.fetchall()
                
                # Process grocery orders
                for row in grocery_results:
                    grocery_orders.append({
                        'order_id': row[0],
                        'order_number': row[1],
                        'order_type': row[2],
                        'order_status': row[3],
                        'payment_status': row[4],
                        'total_amount': float(row[5]) if row[5] else 0.0,
                        'final_amount': float(row[6]) if row[6] else 0.0,
                        'delivery_charge': float(row[7]) if row[7] else 0.0,
                        'discount': float(row[8]) if row[8] else 0.0,
                        'gst_amount': float(row[9]) if row[9] else 0.0,
                        'customer_id': row[10],
                        'customer_name': row[11].strip() if row[11] else 'Unknown Customer',
                        'customer_phone': row[12],
                        'customer_email': row[13],
                        'business_id': row[14],
                        'business_name': row[15],
                        'business_type': row[16],
                        'delivery_address': row[17],
                        'delivery_instructions': row[18],
                        'order_instructions': row[19],
                        'delivery_time': row[20],
                        'scheduled_time': None,
                        'pickup_time': row[21],
                        'items_count': row[22],
                        'created_at': row[23],
                        'updated_at': row[24],
                        'order_system': 'grocery',
                        
                        # Company/B2B Information
                        'company_details': {
                            'company_name': row[33],
                            'gst_number': row[34],
                            'customer_type': row[25],
                            'company_id': row[26],
                            'employee_id': row[27],
                            'approval_status': row[28],
                            'company_notes': row[29],
                            'department': row[30],
                            'purchase_order': row[31],
                            'is_bulk_order': bool(row[32]),
                        } if row[26] else None
                    })
            
            # Attach items and customizations to orders
            try:
                with connection.cursor() as cursor:
                    # Regular orders: fetch item customizations
                    if regular_orders:
                        reg_ids = [o['order_id'] for o in regular_orders]
                        placeholders = ','.join(['%s'] * len(reg_ids))
                        cursor.execute(f"""
                            SELECT order_id, item_name_snapshot, quantity, customizations
                            FROM order_items
                            WHERE order_id IN ({placeholders})
                        """, reg_ids)
                        rows = cursor.fetchall()
                        reg_items_map = {}
                        for oid, name, qty, custom in rows:
                            try:
                                if isinstance(custom, str):
                                    parsed = json.loads(custom)
                                else:
                                    parsed = custom
                            except Exception:
                                parsed = custom
                            reg_items_map.setdefault(oid, []).append({
                                'name': name,
                                'quantity': int(qty) if qty is not None else None,
                                'customizations': parsed
                            })
                        for o in regular_orders:
                            o['items'] = reg_items_map.get(o['order_id'], [])

                    # Grocery orders: fetch items (no customizations field)
                    if grocery_orders:
                        gro_ids = [o['order_id'] for o in grocery_orders]
                        placeholders = ','.join(['%s'] * len(gro_ids))
                        cursor.execute(f"""
                            SELECT oi.order_id, p.product_name, oi.quantity, oi.gst
                            FROM Groceries_order_items oi
                            LEFT JOIN Groceries_Products p ON oi.product_id = p.product_id
                            WHERE oi.order_id IN ({placeholders})
                        """, gro_ids)
                        rows = cursor.fetchall()
                        gro_items_map = {}
                        for oid, name, qty, gst in rows:
                            gro_items_map.setdefault(oid, []).append({
                                'name': name,
                                'quantity': int(qty) if qty is not None else None,
                                'gst': float(gst) if gst else 0.0,
                                'customizations': []
                            })
                        for o in grocery_orders:
                            o['items'] = gro_items_map.get(o['order_id'], [])
            except Exception as e:
                logger.error(f"Failed to fetch items/customizations for pending orders: {e}")
            
            # Get total counts for pagination info
            with connection.cursor() as cursor:
                # Count total regular orders
                regular_count_query = """
                    SELECT COUNT(*) FROM orders o
                    LEFT JOIN businesses b ON o.business_id = b.business_id
                    LEFT JOIN (
                        SELECT p1.order_id, p1.status, p1.payment_method
                        FROM payments p1
                        INNER JOIN (
                            SELECT order_id, MAX(created_at) as max_created_at
                            FROM payments
                            GROUP BY order_id
                        ) p2 ON p1.order_id = p2.order_id AND p1.created_at = p2.max_created_at
                    ) latest_payment ON latest_payment.order_id = o.order_id
                    WHERE 1=1
                """
                count_params = []
                if business_ids_to_include:
                    business_placeholders = ','.join(['%s'] * len(business_ids_to_include))
                    regular_count_query += f" AND o.business_id IN ({business_placeholders})"
                    count_params.extend(business_ids_to_include)
                # Same payment filter as data query
                regular_count_query += " AND (COALESCE(latest_payment.status, 'pending') = 'success' OR LOWER(COALESCE(latest_payment.payment_method, '')) = 'cod')"
        
                cursor.execute(regular_count_query, count_params)
                total_regular_orders = cursor.fetchone()[0]
        
                # Count total grocery orders
                grocery_count_query = """
                    SELECT COUNT(*) FROM Groceries_orders go
                    LEFT JOIN businesses b ON go.business_id = b.business_id
                    LEFT JOIN (
                        SELECT gp1.order_id, gp1.payment_status, gp1.payment_method
                        FROM Groceries_payments gp1
                        INNER JOIN (
                            SELECT order_id, MAX(payment_date) as max_payment_date
                            FROM Groceries_payments
                            GROUP BY order_id
                        ) gp2 ON gp1.order_id = gp2.order_id AND gp1.payment_date = gp2.max_payment_date
                    ) latest_gpay ON latest_gpay.order_id = go.order_id
                    WHERE 1=1
                """
                if business_ids_to_include:
                    business_placeholders = ','.join(['%s'] * len(business_ids_to_include))
                    grocery_count_query += f" AND go.business_id IN ({business_placeholders})"
                
                # Same payment filter as data query
                grocery_count_query += " AND (LOWER(go.payment_status) = 'paid' OR LOWER(COALESCE(latest_gpay.payment_method, '')) = 'cash')"
                
                cursor.execute(grocery_count_query, count_params)
                total_grocery_orders = cursor.fetchone()[0]
            
            # Combine and sort all orders by created_at
            all_orders = regular_orders + grocery_orders
            all_orders.sort(key=lambda x: x['created_at'], reverse=True)
            
            # Apply limit to combined results
            all_orders = all_orders[:limit]
            
            total_orders = total_regular_orders + total_grocery_orders
            has_next_page = (offset + limit) < total_orders
            has_prev_page = offset > 0
            
            # Prepare response
            response_data = {
                'success': True,
                'message': f'Found {len(all_orders)} orders (showing {offset + 1}-{offset + len(all_orders)} of {total_orders})',
                'pagination': {
                    'total_orders': total_orders,
                    'current_page': (offset // limit) + 1,
                    'per_page': limit,
                    'total_pages': (total_orders + limit - 1) // limit,
                    'has_next_page': (offset + limit) < total_orders,
                    'has_prev_page': offset > 0,
                    'next_offset': offset + limit if (offset + limit) < total_orders else None,
                    'prev_offset': max(0, offset - limit) if offset > 0 else None
                },
                'counts': {
                    'total_orders': total_orders,
                    'regular_orders_count': total_regular_orders,
                    'grocery_orders_count': total_grocery_orders,
                    'current_batch_count': len(all_orders)
                },
                'orders': all_orders
            }
            
            # Add business hierarchy info if business_id was provided
            if business_id and business_ids_to_include:
                response_data.update({
                    'business_id': business_id,
                    'is_master_business': is_master,
                    'businesses_included': [
                        {'business_id': bid, 'business_name': business_names.get(bid, '')} 
                        for bid in business_ids_to_include
                    ]
                })
            
            # PERFORMANCE FIX: Direct response return to prevent Gunicorn OOM/Timeout on AWS
            # The manual serialization below is significantly more memory-efficient than 
            # passing the entire block through a full Rest Framework serializer validation
            return Response(response_data, status=status.HTTP_200_OK)
            
        except Exception as e:
            logger.error(f"Error fetching orders: {str(e)}")
            return Response({
                'success': False,
                'message': f'Error fetching orders: {str(e)}',
                'pagination': {
                    'total_orders': 0,
                    'current_page': 1,
                    'per_page': limit,
                    'total_pages': 0,
                    'has_next_page': False,
                    'has_prev_page': False,
                    'next_offset': None,
                    'prev_offset': None
                },
                'counts': {
                    'total_orders': 0,
                    'regular_orders_count': 0,
                    'grocery_orders_count': 0,
                    'current_batch_count': 0
                },
                'orders': []
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@swagger_auto_schema(tags=['Business'])
class RBOOrderDetailsView(APIView):
    """
    API endpoint to get order details with user information
    GET /api/orders/<int:order_id>/
    """
    
    @swagger_auto_schema(
        tags=['Business'],
        operation_summary='Get order details',
        operation_description='Get detailed order information including items, customer, and delivery details',
        manual_parameters=[
            openapi.Parameter(
                'order_id',
                openapi.IN_PATH,
                description='Order ID to retrieve details for',
                type=openapi.TYPE_INTEGER,
                required=True
            ),
        ],
        responses={
            200: openapi.Response(
                description='Order details retrieved successfully',
                examples={
                    'application/json': {
                        'success': True,
                        'data': {
                            'order': {
                                'id': 123,
                                'status': 'pending',
                                'items': []
                            }
                        }
                    }
                }
            ),
            404: openapi.Response(
                description='Order not found',
                examples={
                    'application/json': {
                        'success': False,
                        'error': {
                            'code': 'ORDER_NOT_FOUND',
                            'message': 'Order with ID 123 not found'
                        }
                    }
                }
            ),
            500: openapi.Response(
                description='Server error',
                examples={
                    'application/json': {
                        'success': False,
                        'error': {
                            'code': 'SERVER_ERROR',
                            'message': 'Failed to fetch order details'
                        }
                    }
                }
            )
        }
    )
    def get(self, request, order_id):
        """
        Get order details by ID
        
        Parameters:
        - order_id (int): The ID of the order to retrieve
        
        Returns:
        - 200: Order details with items
        - 404: Order not found
        - 500: Server error
        """
        try:
            order = GroceryOrdersService.get_order_details_with_user(order_id)

            if not order:
                return Response(
                    {
                        "success": False,
                        "error": {
                            "code": "ORDER_NOT_FOUND",
                            "message": f"Order with ID {order_id} not found"
                        }
                    },
                    status=status.HTTP_404_NOT_FOUND
                )
            
            # Prepare helpers for media URLs - returns S3 URLs directly
            def to_absolute_url(path: str):
                return build_s3_file_url(path)

            # Parse business hours JSON to extract opening/closing times
            business_hours_json = order.get("business_hours_json")
            opening_time = None
            closing_time = None
            
            if business_hours_json:
                try:
                    import json
                    business_hours = json.loads(business_hours_json) if isinstance(business_hours_json, str) else business_hours_json
                    # Extract general opening/closing times (you can customize this logic based on your JSON structure)
                    if isinstance(business_hours, dict):
                        # Try to get today's hours or general hours
                        for day_key in ['monday', 'mon', 'general', 'default']:
                            if day_key in business_hours:
                                day_hours = business_hours[day_key]
                                if isinstance(day_hours, dict):
                                    opening_time = day_hours.get('open') or day_hours.get('opening')
                                    closing_time = day_hours.get('close') or day_hours.get('closing')
                                    break
                                elif isinstance(day_hours, list) and len(day_hours) > 0:
                                    first_slot = day_hours[0]
                                    if isinstance(first_slot, dict):
                                        opening_time = first_slot.get('open') or first_slot.get('opening')
                                        closing_time = first_slot.get('close') or first_slot.get('closing')
                                    break
                except (json.JSONDecodeError, TypeError, AttributeError):
                    # If JSON parsing fails, keep opening_time and closing_time as None
                    pass

            # Normalise monetary values and item details using Decimal for precision
            items = order.get("items", [])
            formatted_items = []
            subtotal_dec = Decimal('0.00')
            tax_total_dec = Decimal('0.00')

            for item in items:
                # Best-effort enrichment for missing item fields using (product_id, variant_id) or (menu_item_id, variant_id)
                # Service payloads vary by business type; keep backward compatibility.
                bt_val = (order.get('business_type') or order.get('businessType') or order.get('businessType'.lower()))
                bt_val = str(bt_val).upper() if bt_val is not None else None

                item_product_id = item.get('product_id')
                item_variant_id = item.get('variant_id')
                item_menu_item_id = item.get('menu_item_id')

                # If variant_id is missing in service payload for online orders, try to backfill from order_items table
                # using the order item primary key (item_id)
                if not item_variant_id:
                    try:
                        from django.db import connection
                        item_row_id = item.get('item_id') or item.get('id')
                        if item_row_id:
                            with connection.cursor() as cursor:
                                cursor.execute(
                                    """
                                    SELECT oi.variant_id, oi.product_item_id, oi.menu_item_id
                                    FROM order_items oi
                                    WHERE oi.item_id = %s
                                    LIMIT 1
                                    """,
                                    [item_row_id],
                                )
                                oi_row = cursor.fetchone()
                                if oi_row:
                                    item_variant_id = oi_row[0]
                                    # In older data, product_id might be sent but we also keep product_item_id as fallback
                                    if not item_product_id and oi_row[1] is not None:
                                        item_product_id = oi_row[1]
                                    if not item_menu_item_id and oi_row[2] is not None:
                                        item_menu_item_id = oi_row[2]
                    except Exception:
                        pass

                enriched = {
                    'description': item.get('description'),
                    'category': item.get('item_category') or item.get('sub_category'),
                    'type': item.get('item_type'),
                    'brand_name': item.get('brand_name'),
                    'rating': item.get('rating'),
                    'is_organic': item.get('is_organic', 0),
                    'image_path': item.get('item_image') or item.get('image_url'),
                    'product_id': item_product_id,
                    'variant_id': item_variant_id,
                    'menu_item_id': item_menu_item_id,
                }

                variant_details = None
                if item_variant_id:
                    try:
                        from django.db import connection

                        def _json_safe(v):
                            try:
                                from decimal import Decimal as _D
                                if isinstance(v, _D):
                                    return float(v)
                            except Exception:
                                pass
                            try:
                                import datetime as _dt
                                if isinstance(v, (_dt.datetime, _dt.date, _dt.time)):
                                    return v.isoformat()
                            except Exception:
                                pass
                            return v

                        def _fetch_row_as_dict(table_name, id_col, id_val):
                            with connection.cursor() as cursor:
                                cursor.execute(
                                    f"SELECT * FROM {table_name} WHERE {id_col} = %s LIMIT 1",
                                    [id_val],
                                )
                                row = cursor.fetchone()
                                if not row:
                                    return None
                                cols = [c[0] for c in cursor.description] if cursor.description else []
                                if not cols:
                                    return None
                                return {cols[i]: _json_safe(row[i]) for i in range(min(len(cols), len(row)))}

                        if bt_val == 'R01':
                            variant_details = _fetch_row_as_dict('Groceries_ProductVariants_1', 'variant_id', item_variant_id)
                        elif bt_val == 'R02':
                            variant_details = _fetch_row_as_dict('menu_item_variants', 'variant_id', item_variant_id)
                        elif bt_val == 'R08':
                            variant_details = _fetch_row_as_dict('fashion_product_variants', 'variant_id', item_variant_id)
                    except Exception:
                        variant_details = None

                try:
                    from django.db import connection
                    with connection.cursor() as cursor:
                        # Groceries (R01): resolve using variant_id -> product_id, then fetch product details
                        if bt_val == 'R01':
                            if item_variant_id:
                                cursor.execute(
                                    """
                                    SELECT p.product_id, p.product_name, p.brand_name, p.description, p.main_image,
                                           p.sub_category, p.is_organic, p.rating
                                    FROM Groceries_ProductVariants_1 v
                                    JOIN Groceries_Products p ON p.product_id = v.product_id
                                    WHERE v.variant_id = %s
                                    LIMIT 1
                                    """,
                                    [item_variant_id],
                                )
                                row = cursor.fetchone()
                                if row:
                                    enriched['product_id'] = row[0]
                                    enriched['brand_name'] = enriched['brand_name'] or row[2]
                                    enriched['description'] = enriched['description'] or row[3]
                                    enriched['image_path'] = enriched['image_path'] or row[4]
                                    enriched['category'] = enriched['category'] or row[5]
                                    enriched['is_organic'] = enriched['is_organic'] if enriched['is_organic'] not in [None, ''] else row[6]
                                    enriched['rating'] = enriched['rating'] if enriched['rating'] not in [None, ''] else row[7]
                            # Fallback: direct product lookup when only product_id is present
                            if enriched.get('product_id') and not (enriched.get('description') or enriched.get('image_path') or enriched.get('category') or enriched.get('brand_name')):
                                cursor.execute(
                                    """
                                    SELECT p.product_id, p.product_name, p.brand_name, p.description, p.main_image,
                                           p.sub_category, p.is_organic, p.rating
                                    FROM Groceries_Products p
                                    WHERE p.product_id = %s
                                    LIMIT 1
                                    """,
                                    [enriched.get('product_id')],
                                )
                                row2 = cursor.fetchone()
                                if row2:
                                    enriched['brand_name'] = enriched['brand_name'] or row2[2]
                                    enriched['description'] = enriched['description'] or row2[3]
                                    enriched['image_path'] = enriched['image_path'] or row2[4]
                                    enriched['category'] = enriched['category'] or row2[5]
                                    enriched['is_organic'] = enriched['is_organic'] if enriched['is_organic'] not in [None, ''] else row2[6]
                                    enriched['rating'] = enriched['rating'] if enriched['rating'] not in [None, ''] else row2[7]
                except Exception:
                    # Never break order details due to enrichment failures
                    pass

                unit_price_dec = Decimal(str(item.get("unit_price", item.get("price", 0)) or 0))
                total_price_dec = Decimal(str(item.get("total_price", 0) or 0))
                gst_value = item.get("gst")
                tax_amount_dec = Decimal(str(item.get("tax_amount", 0) or 0))

                # Compute tax if not already provided
                if (tax_amount_dec == 0) and (gst_value is not None):
                    try:
                        tax_amount_dec = (unit_price_dec * Decimal(str(gst_value)) / Decimal('100')).quantize(Decimal('0.01'))
                    except Exception:
                        tax_amount_dec = Decimal('0.00')

                subtotal_dec += total_price_dec
                tax_total_dec += tax_amount_dec

                image_path = enriched.get('image_path') or item.get("item_image") or item.get("image_url")

                # Parse item customizations if available
                custom = item.get("customizations")
                try:
                    if isinstance(custom, str):
                        custom_parsed = json.loads(custom)
                    else:
                        custom_parsed = custom
                except Exception:
                    custom_parsed = custom
                if custom_parsed is None:
                    custom_parsed = []

                formatted_items.append({
                    "item_id": item.get("item_id") or item.get("id"),
                    "product_id": enriched.get('product_id'),
                    "variant_id": enriched.get('variant_id'),
                    "variant_details": variant_details,
                    "menu_item_id": enriched.get('menu_item_id'),
                    "name": item.get("item_name") or item.get("name"),
                    "quantity": item.get("quantity"),
                    "unit_price": float(unit_price_dec),
                    "total_price": float(total_price_dec),
                    "gst": float(gst_value) if gst_value is not None else None,
                    "tax_amount": float(tax_amount_dec),
                    "image": to_absolute_url(image_path),
                    "description": enriched.get('description'),
                    "category": enriched.get('category'),
                    "type": enriched.get('type'),
                    "brand_name": enriched.get('brand_name'),
                    "rating": float(enriched.get('rating')) if enriched.get('rating') is not None else None,
                    "is_organic": bool(enriched.get('is_organic', 0)),
                    "customizations": custom_parsed
                })

            # Charges and discounts
            delivery_charges_dec = Decimal(str(order.get("delivery_charges") or 0))
            parcel_charges_dec = Decimal(str(order.get("parcel_charges") or 0))
            discount_dec = Decimal(str(order.get("discount") or order.get("discount_amount") or 0))

            # Prefer DB-provided totals when available
            if order.get("total_amount") is not None:
                try:
                    subtotal_dec = Decimal(str(order.get("total_amount")))
                except Exception:
                    pass
            if order.get("gst_amount") is not None:
                try:
                    tax_total_dec = Decimal(str(order.get("gst_amount")))
                except Exception:
                    pass

            if order.get("final_amount") is not None:
                try:
                    total_amount_dec = Decimal(str(order.get("final_amount")))
                except Exception:
                    total_amount_dec = subtotal_dec + delivery_charges_dec + parcel_charges_dec + tax_total_dec - discount_dec
            else:
                total_amount_dec = subtotal_dec + delivery_charges_dec + parcel_charges_dec + tax_total_dec - discount_dec

            # Format the response

            # Compute customer address/coordinates from user_address

            def _get_customer_address_info(order):

                try:

                    from django.db import connection

                    with connection.cursor() as cursor:

                        if order.get('source_table') == 'orders':

                            cursor.execute("""

                                SELECT ua.address

                                FROM orders o

                                LEFT JOIN user_address ua ON o.delivery_address_id = ua.id

                                WHERE o.order_id = %s

                            """, [order.get('order_id')])

                        else:

                            cursor.execute("""

                                SELECT ua.address

                                FROM user_address ua

                                WHERE ua.user_id = %s AND ua.is_default = 1

                                ORDER BY ua.is_default DESC, ua.updated_at DESC

                                LIMIT 1

                            """, [order.get('user_id')])

                        row = cursor.fetchone()

                        if row and row[0]:

                            try:

                                import json

                                addr = json.loads(row[0]) if isinstance(row[0], str) else row[0]

                            except Exception:

                                addr = {}

                            door_no = addr.get('Door no') or addr.get('door_no') or addr.get('doorNo')

                            street = addr.get('street')

                            city = addr.get('city/town') or addr.get('city')

                            state = addr.get('state')

                            pincode = addr.get('pincode')

                            parts = []

                            if door_no: parts.append('Door No: ' + str(door_no))

                            if street: parts.append(str(street))

                            if city: parts.append(str(city))

                            if state: parts.append(str(state))

                            if pincode: parts.append('Pincode: ' + str(pincode))

                            address_text = ', '.join([p for p in parts if p])

                            location_text = addr.get('landmark') or city

                            lat = addr.get('latitude') or addr.get('lat')

                            lng = addr.get('longitude') or addr.get('lng')

                            return address_text or None, location_text or None, lat, lng
                        
                        # If no address found, return None values
                        return None, None, None, None

                except Exception:

                    return None, None, None, None


            def _get_delivery_partner_details(order):
                """Fetch delivery partner details for the given order across systems."""
                try:
                    with connection.cursor() as cursor:
                        if order.get('source_table') == 'orders':
                            # Standard orders: join orders -> delivery_partner (by user_id)
                            cursor.execute(
                                """
                                SELECT 
                                    dp.id,
                                    dp.user_id,
                                    dp.business_id,
                                    dp.vehicle_type,
                                    dp.vehicle_number,
                                    dp.latitude,
                                    dp.longitude,
                                    dp.status,
                                    dp.is_available,
                                    dp.rating,
                                    dp.total_deliveries,
                                    dp.phone_number,
                                    dp.is_verified,
                                    dp.created_at,
                                    dp.updated_at,
                                    r.firstName,
                                    r.lastName,
                                    r.displayName,
                                    r.profileUrl
                                FROM orders o
                                LEFT JOIN delivery_partner dp ON dp.user_id = o.delivery_partner_id
                                LEFT JOIN registrations r ON r.user_id = dp.user_id
                                WHERE o.order_id = %s
                                LIMIT 1
                                """,
                                [order.get('order_id')]
                            )
                            row = cursor.fetchone()
                            # No assignment or no delivery partner record
                            if not row or row[1] is None:
                                return None

                            name = row[17] or f"{row[15] or ''} {row[16] or ''}".strip()

                            return {
                                "id": row[0],
                                "user_id": row[1],
                                "name": name,
                                "profile_image": to_absolute_url(row[18]) if row[18] else None,
                                "phone": row[11],
                                "vehicle_type": row[3],
                                "vehicle_number": row[4],
                                "latitude": float(row[5]) if row[5] is not None else None,
                                "longitude": float(row[6]) if row[6] is not None else None,
                                "status": row[7],
                                "is_available": bool(row[8]),
                                "rating": float(row[9]) if row[9] is not None else 0.0,
                                "total_deliveries": int(row[10]) if row[10] is not None else 0,
                                "is_verified": bool(row[12]),
                            }
                        else:
                            # Grocery orders: join Grocery_deliver_details -> delivery_partner (by partner_id=user_id)
                            cursor.execute(
                                """
                                SELECT 
                                    gdd.delivery_detail_id,
                                    gdd.partner_id,
                                    gdd.assignment_status,
                                    gdd.assigned_at,
                                    gdd.delivered_at,
                                    gdd.otp_verified_at,
                                    dp.id,
                                    dp.business_id,
                                    dp.vehicle_type,
                                    dp.vehicle_number,
                                    dp.latitude,
                                    dp.longitude,
                                    dp.status,
                                    dp.is_available,
                                    dp.rating,
                                    dp.total_deliveries,
                                    dp.phone_number,
                                    dp.is_verified,
                                    dp.created_at,
                                    dp.updated_at,
                                    r.firstName,
                                    r.lastName,
                                    r.displayName,
                                    r.profileUrl
                                FROM Grocery_deliver_details gdd
                                LEFT JOIN delivery_partner dp ON dp.user_id = gdd.partner_id
                                LEFT JOIN registrations r ON r.user_id = gdd.partner_id
                                WHERE gdd.order_id = %s AND gdd.is_active = 1
                                LIMIT 1
                                """,
                                [order.get('order_id')]
                            )
                            row = cursor.fetchone()
                            if not row or row[1] is None:
                                return None

                            name = row[22] or f"{row[20] or ''} {row[21] or ''}".strip()

                            return {
                                "id": row[6],
                                "user_id": row[1],
                                "name": name,
                                "profile_image": to_absolute_url(row[23]) if row[23] else None,
                                "phone": row[16],
                                "vehicle_type": row[8],
                                "vehicle_number": row[9],
                                "latitude": float(row[10]) if row[10] is not None else None,
                                "longitude": float(row[11]) if row[11] is not None else None,
                                "status": row[12],
                                "is_available": bool(row[13]),
                                "rating": float(row[14]) if row[14] is not None else 0.0,
                                "total_deliveries": int(row[15]) if row[15] is not None else 0,
                                "is_verified": bool(row[17]),
                                "assignment_status": row[2],
                                "assigned_at": row[3].isoformat() if row[3] else None,
                                "delivered_at": row[4].isoformat() if row[4] else None
                            }
                except Exception:
                    return None

            cust_address, cust_location, cust_lat, cust_lng = _get_customer_address_info(order)
            dp_details = _get_delivery_partner_details(order)

            response = {
                "success": True,
                "data": {
                    "order": {
                        "id": order.get("order_id"),
                        "order_number": order.get("order_number"),
                        "token_num": order.get("token_num"),
                        "status": order.get("status"),
                        "payment_status": order.get("payment_status"),
                        "created_at": order.get("created_at").isoformat() if order.get("created_at") else None,
                        "updated_at": order.get("updated_at").isoformat() if order.get("updated_at") else None,
                        "delivery_address": order.get("delivery_address"),
                        "delivery_instructions": order.get("delivery_instructions"),
                        "order_instructions": order.get("order_instructions"),
                        "scheduled_time": order.get("scheduled_time"),
                        "estimated_delivery_time": order.get("estimated_delivery_time"),
                        "order_type": order.get("order_type"),
                        "parcel_charges": float(parcel_charges_dec),
                        "business_details": {
                            "business_id": order.get("business_id"),
                            "business_name": order.get("business_name"),
                            "business_type": order.get("business_type"),
                            "address": self._format_business_address(order),
                            "location": order.get("business_location"),
                            "landmark": order.get("business_landmark"),
                            "city": order.get("business_city"),
                            "state": order.get("business_state"),
                            "pincode": order.get("business_pincode"),
                            "business_number": order.get("business_phone"),
                            "contact_mobile": order.get("business_contact_mobile"),
                            "contact_support": order.get("business_contact_support"),
                            "business_whatsapp": order.get("business_whatsapp"),
                            "latitude": float(order.get("business_latitude")) if order.get("business_latitude") else None,
                            "longitude": float(order.get("business_longitude")) if order.get("business_longitude") else None,
                            "opening_time": opening_time,
                            "closing_time": closing_time,
                            "business_status": order.get("business_status")
                        },
                        "customer": {
                            "id": order.get("user_id"),
                            "first_name": order.get("first_name"),
                            "last_name": order.get("last_name"),
                            "display_name": order.get("display_name"),
                            "phone": order.get("phone_number"),
                            "email": order.get("email"),
                            "profile_image": to_absolute_url(order.get("profile_image")),
                            "address": cust_address or order.get("delivery_address"),
                            "location": cust_location,
                            "lat": float(cust_lat) if cust_lat not in (None, "") else None,
                            "lng": float(cust_lng) if cust_lng not in (None, "") else None,

                        },
                        "delivery_partner": dp_details,
                        "items": formatted_items,
                        "company_details": {
                            "company_name": order.get("company_name"),
                            "gst_number": order.get("gst_number"),
                            "customer_type": order.get("order_customer_type"),
                            "company_id": order.get("company_id"),
                            "employee_id": order.get("ordered_by_employee"),
                            "approval_status": order.get("approval_status"),
                            "company_notes": order.get("company_notes"),
                            "department": order.get("company_department"),
                            "purchase_order": order.get("company_purchase_order"),
                            "is_bulk_order": bool(order.get("is_bulk_order")),
                            "bulk_order_reference": order.get("bulk_order_reference"),
                        } if order.get("company_id") else None,
                        "summary": {
                            "subtotal": float(subtotal_dec),
                            "delivery_charges": float(delivery_charges_dec),
                            "parcel_charges": float(parcel_charges_dec),
                            "tax": float(tax_total_dec),
                            "total": float(total_amount_dec),
                        },
                        "business_contact": {
                            "business_number": order.get("business_phone"),
                            "contact_mobile": order.get("business_contact_mobile"),
                            "contact_support": order.get("business_contact_support")
                        }
                    }
                }
            }
            
            return Response(response)
            
        except Exception as e:
            logger.error(f"Error fetching order {order_id}: {str(e)}")
            logger.exception(e)
            return Response(
                {
                    "success": False,
                    "error": {
                        "code": "SERVER_ERROR",
                        "message": "Failed to fetch order details",
                        "details": str(e)
                    }
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    def _format_business_address(self, order):
        """
        Format business address with landmark, city, state, and pincode
        """
        business_address_parts = []
        
        # Add main address
        if order.get('business_address'):
            business_address_parts.append(order.get('business_address'))
        
        # Add landmark
        if order.get('business_landmark'):
            business_address_parts.append(f"Landmark: {order.get('business_landmark')}")
        
        # Add city
        if order.get('business_city'):
            business_address_parts.append(order.get('business_city'))
        
        # Add state
        if order.get('business_state'):
            business_address_parts.append(order.get('business_state'))
        
        # Add pincode
        if order.get('business_pincode'):
            business_address_parts.append(f"Pincode: {order.get('business_pincode')}")
        
        # Join all parts with commas
        return ', '.join(business_address_parts) if business_address_parts else 'Address not available'


