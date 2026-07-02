# delivery_partner/views.py
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework_simplejwt.authentication import JWTAuthentication
from geopy.distance import geodesic
from django.db import connection, transaction

from consumer.models import Orders
from consumer.gro_models import GroceriesOrders
from kirazee_app.models import Business, Registration, generate_user_id
from kirazee_app.models import Otp
from .models import DeliveryPartner, OrderOTP

from .serializers import (
    DeliveryPartnerSerializer, 
    LocationSerializer,
    NearbyOrdersSerializer,
    OrderAssignmentSerializer,
    UserProfileSerializer,
    DeliveryPartnerProfileSerializer,
    CombinedProfileSerializer,
    ActiveDeliveryPartnerSerializer,
    OrderAssignmentSerializer,
    DeliveryOrderSerializer, DeliveryPartnerRegistrationSerializer,
    DeliveryPartnerFinancialsSerializer, DeliveryPartnerDocumentUploadSerializer,
    BasicDeliveryPartnerSignupSerializer
)
from django.conf import settings
from django.core.mail import send_mail
from django.core.cache import cache
from django.utils import timezone
from datetime import datetime, timedelta
import os
from django.core.files.storage import default_storage
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync
from urllib.parse import urljoin
from types import SimpleNamespace
from django.urls import get_script_prefix
from decimal import Decimal
import json
import re
import logging
from delivery.image_utils import build_s3_file_url

logger = logging.getLogger(__name__)

class DeliveryPartnerMixin:
    def get_delivery_partner(self, user):
        # Check if user is authenticated
        if not user.is_authenticated:
            return None
        try:
            return DeliveryPartner.objects.get(user=user)
        except DeliveryPartner.DoesNotExist:
            return None

class DeliveryPartnerProfileView(DeliveryPartnerMixin, APIView):
    def get(self, request):
        partner = self.get_delivery_partner(request.user)
        if not partner:
            return Response(
                {"error": "Delivery partner profile not found. Please ensure you are registered as a delivery partner."},
                status=status.HTTP_404_NOT_FOUND
            )
        serializer = DeliveryPartnerSerializer(partner)
        return Response(serializer.data)
    
    def put(self, request):
        partner = self.get_delivery_partner(request.user)
        if not partner:
            return Response(
                {"error": "Delivery partner profile not found. Please ensure you are registered as a delivery partner."},
                status=status.HTTP_404_NOT_FOUND
            )
        
        serializer = DeliveryPartnerSerializer(partner, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

class UpdateDeliveryPartnerLocation(APIView):
    """
    API endpoint for delivery partners to update their location.
    Expected payload:
    {
        "delivery_partner_id": 1,
        "order_id": "1002",
        "latitude": 13.6912,
        "longitude": 80.0144
    }
    """
    
    def post(self, request, *args, **kwargs):
        try:
            delivery_partner_id = request.data.get('delivery_partner_id')
            order_id = (
                request.data.get('order_id')
                or request.data.get('orderId')
                or request.query_params.get('order_id')
                or request.query_params.get('orderId')
            )
            latitude = request.data.get('latitude')
            longitude = request.data.get('longitude')
            try:
                order_id = int(str(order_id).strip())
            except Exception:
                order_id = None
            
            if not all([delivery_partner_id, order_id, latitude is not None, longitude is not None]):
                return Response(
                    {"error": "Missing required fields. Required: delivery_partner_id, order_id, latitude, longitude"},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            try:
                with connection.cursor() as cursor:
                    # Update delivery partner's location
                    update_query = """
                    UPDATE delivery_partner 
                    SET latitude = %s, 
                        longitude = %s,
                        updated_at = NOW()
                    WHERE user_id = %s
                    """
                    cursor.execute(update_query, [latitude, longitude, delivery_partner_id])
                    
                    # Check if any rows were affected
                    if cursor.rowcount == 0:
                        return Response(
                            {"error": "Delivery partner not found"},
                            status=status.HTTP_404_NOT_FOUND
                        )
                    
                    # Insert location history record
                    history_insert_query = """
                    INSERT INTO deliverylocationhistory 
                    (delivery_partner_id, order_id, latitude, longitude, timestamp)
                    VALUES (%s, %s, %s, %s, NOW())
                    """
                    cursor.execute(history_insert_query, [delivery_partner_id, order_id, latitude, longitude])
                    
                    logger.info(f"Location history recorded for delivery partner {delivery_partner_id} at ({latitude}, {longitude})")
                    
                    # Fetch the updated delivery partner data
                    select_query = """
                    SELECT id, vehicle_type, phone_number 
                    FROM delivery_partner 
                    WHERE user_id = %s
                    """
                    cursor.execute(select_query, [delivery_partner_id])
                    dp_data = cursor.fetchone()
                    
                    if not dp_data:
                        return Response(
                            {"error": "Delivery partner not found"},
                            status=status.HTTP_404_NOT_FOUND
                        )
                    
                    # Get user details
                    user_query = """
                    SELECT firstName, lastName, displayName 
                    FROM registrations 
                    WHERE user_id = %s
                    """
                    cursor.execute(user_query, [delivery_partner_id])
                    user_data = cursor.fetchone()
                    
                    # Prepare WebSocket message
                    channel_layer = get_channel_layer()
                    group_name = f'order_{order_id}'
                    
                    if user_data:
                        first_name, last_name, display_name = user_data
                        full_name = display_name or f"{first_name} {last_name}".strip()
                    else:
                        full_name = "Delivery Partner"
                    
                    message = {
                        'type': 'status_update',
                        'status': 'travelling',
                        'timestamp': timezone.now().isoformat(),
                        'delivery_partner': {
                            'id': delivery_partner_id,
                            'name': full_name,
                            'vehicle_type': dp_data[1],
                            'phone': dp_data[2]
                        },
                        'location': {
                            'latitude': float(latitude),
                            'longitude': float(longitude),
                            'last_updated': timezone.now().isoformat()
                        }
                    }
                    
                    # Send update to WebSocket group
                    async_to_sync(channel_layer.group_send)(
                        group_name,
                        {
                            'type': 'status_update',
                            'message': message
                        }
                    )
                    
                    return Response({
                        "status": "success",
                        "message": "Location updated successfully"
                    })
                    
            except Exception as e:
                logger.error(f"Error updating delivery partner location: {str(e)}")
                return Response(
                    {"error": "Failed to update location"},
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR
                )
                
        except Exception as e:
            logger.error(f"Unexpected error in UpdateDeliveryPartnerLocation: {str(e)}")
            return Response(
                {"error": "An unexpected error occurred"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class GetDeliveryPartnerProfileView(APIView):
    """
    GET /get-profile/?user_id=[value]
    Display complete details of the delivery partner including financial information, 
    documents, address details, and verification status
    """
    
    def get(self, request):
        user_id = request.query_params.get('user_id')
        
        if not user_id:
            return Response(
                {"error": "user_id parameter is required"},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            # Get user registration data
            user = Registration.objects.get(user_id=user_id)
        except Registration.DoesNotExist:
            return Response(
                {"error": "User not found"},
                status=status.HTTP_404_NOT_FOUND
            )
        
        # Get comprehensive delivery partner data using raw SQL
        delivery_partner_data = None
        financial_data = None
        documents_data = []
        
        with connection.cursor() as cursor:
            # Get complete delivery partner information
            cursor.execute("""
                SELECT 
                    id, user_id, business_id, vehicle_type, vehicle_number, license_number,
                    latitude, longitude, status, is_available, rating, total_deliveries, 
                    phone_number, full_address, city, state, pincode, delivery_service_area,
                    delivery_timings, is_verified, created_at, updated_at
                FROM delivery_partner 
                WHERE user_id = %s
            """, [user_id])
            
            row = cursor.fetchone()
            if row:
                partner_id = row[0]
                # Parse JSON field delivery_timings
                delivery_timings_val = None
                try:
                    _dt = row[18]
                    if isinstance(_dt, (bytes, bytearray)):
                        _dt = _dt.decode('utf-8')
                    delivery_timings_val = json.loads(_dt) if isinstance(_dt, str) and _dt else _dt
                except Exception:
                    delivery_timings_val = None
                # Map the raw SQL result to a comprehensive dictionary
                delivery_partner_data = {
                    'id': row[0],
                    'user_id': row[1],
                    'business_id': row[2],
                    'vehicle_type': row[3].lower() if row[3] else None,
                    'vehicle_number': row[4],
                    'license_number': row[5],
                    'latitude': float(row[6]) if row[6] else None,
                    'longitude': float(row[7]) if row[7] else None,
                    'status': 'available' if str(row[8]) == '1' else '0',
                    'is_available': bool(int(row[9])) if row[9] is not None else False,
                    'rating': float(row[10]) if row[10] else 0.0,
                    'total_deliveries': int(row[11]) if row[11] else 0,
                    'phone_number': row[12],
                    'full_address': row[13],
                    'city': row[14],
                    'state': row[15],
                    'pincode': row[16],
                    'delivery_service_area': row[17],
                    'delivery_timings': delivery_timings_val,
                    'is_verified': bool(int(row[19])) if row[19] is not None else False,
                    'created_at': row[20],
                    'updated_at': row[21],
                    'current_location': [float(row[6]), float(row[7])] if row[6] and row[7] else None
                }
                
                # Get financial information
                cursor.execute("""
                    SELECT pan_number, bank_account_number, ifsc_code, created_at, updated_at
                    FROM delivery_partner_financials 
                    WHERE partner_id = %s
                """, [partner_id])
                
                fin_row = cursor.fetchone()
                if fin_row:
                    financial_data = {
                        'pan_number': fin_row[0],
                        'bank_account_number': fin_row[1],
                        'ifsc_code': fin_row[2],
                        'created_at': fin_row[3],
                        'updated_at': fin_row[4]
                    }
                
                # Get documents information
                cursor.execute("""
                    SELECT document_type, document_url, is_verified, uploaded_at
                    FROM delivery_partner_documents 
                    WHERE partner_id = %s 
                    ORDER BY document_type
                """, [partner_id])
                
                doc_rows = cursor.fetchall()
                for doc_row in doc_rows:
                    doc_url = build_s3_file_url(doc_row[1])
                    
                    documents_data.append({
                        'document_type': doc_row[0],
                        'document_url': doc_url,
                        'is_verified': bool(int(doc_row[2])) if doc_row[2] is not None and str(doc_row[2]).isdigit() else bool(doc_row[2]),
                        'uploaded_at': doc_row[3]
                    })
        
        # Serialize user data with request context for URL building
        user_data = UserProfileSerializer(user, context={'request': request}).data
        
        # Create verification summary
        verification_summary = None
        if delivery_partner_data:
            required_doc_types = ["license", "rc_book", "aadhar", "bank_book"]
            present_doc_types = [doc['document_type'] for doc in documents_data]
            verified_doc_types = [doc['document_type'] for doc in documents_data if doc['is_verified']]
            
            verification_summary = {
                "required_doc_types": required_doc_types,
                "present_doc_types": present_doc_types,
                "verified_doc_types": verified_doc_types,
                "all_documents_present": all(dt in present_doc_types for dt in required_doc_types),
                "all_documents_verified": all(dt in verified_doc_types for dt in required_doc_types),
                "documents_count": len(documents_data),
                "verified_documents_count": len(verified_doc_types)
            }
        
        # Determine if user is considered an active delivery partner
        # is_delivery_partner should be false if:
        # 1. No delivery partner data exists, OR
        # 2. is_verified is 0/false, OR  
        # 3. status is 0/'0'/offline
        is_active_delivery_partner = False
        if delivery_partner_data is not None:
            is_verified = delivery_partner_data.get('is_verified', False)
            status = delivery_partner_data.get('status', '0')
            
            # Check if partner is verified and has active status
            if is_verified and str(status) not in ('0', 'offline'):
                is_active_delivery_partner = True
        
        # Fetch applicant (onboarding) record to expose decision and reasons
        app_row = None
        app_status = None
        app_decline_reason = None
        app_onboarding_data = None
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT id, status, decline_reason, onboarding_data FROM dp_onboarding_applications WHERE user_id = %s ORDER BY id DESC LIMIT 1",
                    [user_id]
                )
                app_row = cursor.fetchone()
        except Exception:
            app_row = None

        if app_row:
            app_status = str(app_row[1]).lower() if app_row[1] is not None else None
            app_decline_reason = app_row[2]
            app_onboarding_data = app_row[3]
            try:
                if isinstance(app_onboarding_data, (bytes, bytearray)):
                    app_onboarding_data = app_onboarding_data.decode('utf-8')
                app_onboarding_data = json.loads(app_onboarding_data) if isinstance(app_onboarding_data, str) else (app_onboarding_data or {})
            except Exception:
                app_onboarding_data = {}

        # Compute verification_status for UI
        verification_status = None
        # Check if admin set required_changes (stored as decision_type in JSON)
        decision_type = (app_onboarding_data or {}).get('decision_type')
        has_required_changes = (decision_type == 'required_changes') and bool((app_onboarding_data or {}).get('required_changes'))
        
        if delivery_partner_data and delivery_partner_data.get('is_verified'):
            verification_status = 'approved'
        elif has_required_changes:
            verification_status = 'required_changes'
        elif app_status == 'declined':
            verification_status = 'rejected'
        elif app_status in ('in_progress', 'submitted', 'pending_review') or app_status is None:
            verification_status = 'pending'
        else:
            verification_status = 'pending'

        response_data = {
            "success": True,
            "user_data": user_data,
            "delivery_partner_data": delivery_partner_data,
            "financial_data": financial_data,
            "documents": documents_data,
            "verification_summary": verification_summary,
            "is_delivery_partner": is_active_delivery_partner,
            # New top-level verification fields for frontend
            "verification_status": verification_status,
            "decision_reason": app_decline_reason if verification_status == 'rejected' else None,
            # Include required_changes when verification_status is required_changes
            "required_changes": (app_onboarding_data or {}).get('required_changes') if verification_status == 'required_changes' else None,
            # Reapply info only relevant when rejected
            "reapply_after": (app_onboarding_data or {}).get('reapply_after') if verification_status == 'rejected' else None
        }
        
        return Response(response_data)

class RegisterDeliveryPartnerView(APIView):
    """
    POST /register/?user_id=[value]
    Add the delivery partner details in the delivery_partner table
    """
    
    def post(self, request):
        user_id = request.query_params.get('user_id')
        
        if not user_id:
            return Response(
                {"error": "user_id parameter is required"},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            # Get user registration data
            user = Registration.objects.get(user_id=user_id)
        except Registration.DoesNotExist:
            return Response(
                {"error": "User not found"},
                status=status.HTTP_404_NOT_FOUND
            )
        # Enforce 3-day cooldown if application was declined
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT id, status, decline_reason, onboarding_data FROM dp_onboarding_applications WHERE user_id=%s ORDER BY id DESC LIMIT 1",
                    [user_id]
                )
                app_row = cursor.fetchone()
            if app_row:
                prev_status = str(app_row[1]).lower() if app_row[1] is not None else None
                if prev_status == 'declined':
                    data = app_row[3]
                    try:
                        if isinstance(data, (bytes, bytearray)):
                            data = data.decode('utf-8')
                        data = json.loads(data) if isinstance(data, str) else (data or {})
                    except Exception:
                        data = {}
                    # prefer epoch ts when present
                    now_ts = int(timezone.now().timestamp())
                    reapply_ts = None
                    if isinstance(data.get('reapply_after_ts'), (int, float, str)):
                        try:
                            reapply_ts = int(data.get('reapply_after_ts'))
                        except Exception:
                            reapply_ts = None
                    if reapply_ts is None and data.get('reapply_after'):
                        try:
                            dtv = datetime.fromisoformat(str(data.get('reapply_after')))
                            if timezone.is_naive(dtv):
                                from django.utils import timezone as dj_tz
                                dtv = dj_tz.make_aware(dtv)
                            reapply_ts = int(dtv.timestamp())
                        except Exception:
                            reapply_ts = None
                    if reapply_ts is not None and now_ts < reapply_ts:
                        return Response({
                            "success": False,
                            "message": "Application was declined. You can re-apply after the cooldown ends.",
                            "verification_status": "rejected",
                            "decision_reason": app_row[2],
                            "reapply_after": data.get('reapply_after')
                        }, status=status.HTTP_400_BAD_REQUEST)
        except Exception:
            pass

        # Validate input data
        serializer = DeliveryPartnerRegistrationSerializer(data=request.data)
        if serializer.is_valid():
            try:
                # Check if delivery partner already exists
                with connection.cursor() as cursor:
                    cursor.execute("SELECT COUNT(*) FROM delivery_partner WHERE user_id = %s", [user_id])
                    exists = cursor.fetchone()[0] > 0
                
                if exists:
                    # Update existing delivery partner record
                    with connection.cursor() as cursor:
                        # Normalize status to 0/1 values
                        input_status = str(serializer.validated_data.get('1', '0')).lower()
                        status_val = '1' if input_status == '1' else '0'  # 1 for available/on_delivery, 0 for offline
                        is_avail = 1 if input_status == '1' else 0  # 1 if available/on_delivery, 0 if offline
                        # Prepare JSON for delivery_timings
                        delivery_timings_param = serializer.validated_data.get('delivery_timings')
                        try:
                            if delivery_timings_param is not None and not isinstance(delivery_timings_param, str):
                                delivery_timings_param = json.dumps(delivery_timings_param)
                        except Exception:
                            delivery_timings_param = None

                        cursor.execute("""
                            UPDATE delivery_partner 
                            SET vehicle_type = %s, vehicle_number = %s, phone_number = %s,
                                license_number = %s, full_address = %s, city = %s, state = %s, pincode = %s,
                                delivery_service_area = %s, delivery_timings = %s, business_id = %s,
                                latitude = %s, longitude = %s, status = %s, is_available = %s,
                                updated_at = NOW()
                            WHERE user_id = %s
                        """, [
                            serializer.validated_data['vehicle_type'],
                            serializer.validated_data['vehicle_number'],
                            serializer.validated_data['phone_number'],
                            serializer.validated_data.get('license_number'),
                            serializer.validated_data.get('full_address'),
                            serializer.validated_data.get('city'),
                            serializer.validated_data.get('state'),
                            serializer.validated_data.get('pincode'),
                            serializer.validated_data.get('delivery_service_area'),
                            delivery_timings_param,
                            serializer.validated_data.get('business_id'),
                            serializer.validated_data.get('latitude'),
                            serializer.validated_data.get('longitude'),
                            status_val,  # Using 0/1 for status
                            is_avail,    # Using 0/1 for is_available
                            user_id
                        ])
                    action_message = "Delivery partner details saved successfully. Continue to step 2"
                else:
                    # Create new delivery partner using raw SQL
                    with connection.cursor() as cursor:
                        # Default status to '0' (offline) for new registrations
                        status_val = '0'  # Default to offline (pending verification)
                        is_avail = 0      # Default to not available (pending verification)
                        # Prepare JSON for delivery_timings
                        delivery_timings_param = serializer.validated_data.get('delivery_timings')
                        try:
                            if delivery_timings_param is not None and not isinstance(delivery_timings_param, str):
                                delivery_timings_param = json.dumps(delivery_timings_param)
                        except Exception:
                            delivery_timings_param = None

                        cursor.execute("""
                            INSERT INTO delivery_partner 
                            (user_id, business_id, vehicle_type, vehicle_number, license_number, latitude, longitude, 
                             status, is_available, rating, total_deliveries, phone_number, full_address, city, state, pincode, delivery_service_area, delivery_timings, is_verified, created_at, updated_at)
                            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 0, NOW(), NOW())
                        """, [
                            user_id,
                            serializer.validated_data.get('business_id'),
                            serializer.validated_data['vehicle_type'],
                            serializer.validated_data['vehicle_number'],
                            serializer.validated_data.get('license_number'),
                            serializer.validated_data.get('latitude', 0.0),  # Default to 0.0 if not provided
                            serializer.validated_data.get('longitude', 0.0),  # Default to 0.0 if not provided
                            status_val,  # '0' for offline (pending verification)
                            is_avail,    # 0 for not available (pending verification)
                            0.0,         # rating (default 0.0)
                            0,           # total_deliveries (default 0)
                            serializer.validated_data['phone_number'],
                            serializer.validated_data.get('full_address', ''),  # Default empty string
                            serializer.validated_data.get('city', ''),          # Default empty string
                            serializer.validated_data.get('state', ''),         # Default empty string
                            serializer.validated_data.get('pincode', ''),       # Default empty string
                            serializer.validated_data.get('delivery_service_area', ''),  # Default empty string
                            delivery_timings_param,
                        ])
                    action_message = "Delivery partner registered successfully with default status '0' (pending verification)"
                
                # Fetch the created delivery partner data using raw SQL
                with connection.cursor() as cursor:
                    cursor.execute("""
                        SELECT 
                            id, user_id, business_id, vehicle_type, vehicle_number, license_number, latitude, longitude,
                            status, is_available, rating, total_deliveries, phone_number,
                            full_address, city, state, pincode, delivery_service_area, delivery_timings,
                            is_verified, created_at, updated_at
                        FROM delivery_partner 
                        WHERE user_id = %s
                        ORDER BY id DESC LIMIT 1
                    """, [user_id])
                    
                    row = cursor.fetchone()
                    if row:
                        # Map status to 0/1 to match DeliveryPartnerSerializer.get_status() behavior
                        status_val = str(row[8])
                        status_flag = '1' if status_val in ('available', 'on_delivery') else '0'
                        
                        # Parse JSON field delivery_timings
                        delivery_timings_val = None
                        try:
                            _dt = row[18]
                            if isinstance(_dt, (bytes, bytearray)):
                                _dt = _dt.decode('utf-8')
                            delivery_timings_val = json.loads(_dt) if isinstance(_dt, str) and _dt else _dt
                        except Exception:
                            delivery_timings_val = None

                        delivery_partner_data = {
                            'id': row[0],
                            'user_id': row[1],
                            'business_id': row[2],
                            'vehicle_type': row[3].lower() if row[3] else None,
                            'vehicle_number': row[4],
                            'license_number': row[5],
                            'latitude': float(row[6]) if row[6] else None,
                            'longitude': float(row[7]) if row[7] else None,
                            'status': status_flag,  # Now returns '0' or '1' to match serializer
                            'status_text': status_val,  # Keep original text value for backward compatibility
                            'is_available': bool(int(row[9])) if row[9] is not None else False,
                            'rating': float(row[10]) if row[10] else 0.0,
                            'total_deliveries': int(row[11]) if row[11] else 0,
                            'phone_number': row[12],
                            'full_address': row[13],
                            'city': row[14],
                            'state': row[15],
                            'pincode': row[16],
                            'delivery_service_area': row[17],
                            'delivery_timings': delivery_timings_val,
                            'is_verified': bool(int(row[19])) if row[19] is not None else False,
                            'created_at': row[20],
                            'updated_at': row[21],
                            'current_location': [float(row[6]), float(row[7])] if row[6] and row[7] else None
                        }
                        # Upsert or refresh onboarding application row for this user
                        try:
                            onboarding_payload = {
                                'vehicle_type': serializer.validated_data.get('vehicle_type'),
                                'vehicle_number': serializer.validated_data.get('vehicle_number'),
                                'license_number': serializer.validated_data.get('license_number'),
                                'phone_number': serializer.validated_data.get('phone_number'),
                                'full_address': serializer.validated_data.get('full_address'),
                                'city': serializer.validated_data.get('city'),
                                'state': serializer.validated_data.get('state'),
                                'pincode': serializer.validated_data.get('pincode'),
                                'delivery_service_area': serializer.validated_data.get('delivery_service_area'),
                                'delivery_timings': delivery_timings_val,
                                'last_resubmitted_at': timezone.now().isoformat()
                            }
                            with connection.cursor() as cursor2:
                                cursor2.execute("SELECT id, onboarding_data, status FROM dp_onboarding_applications WHERE user_id=%s ORDER BY id DESC LIMIT 1", [user_id])
                                app_row2 = cursor2.fetchone()
                                if app_row2:
                                    # merge JSON
                                    existing_data = app_row2[1]
                                    try:
                                        if isinstance(existing_data, (bytes, bytearray)):
                                            existing_data = existing_data.decode('utf-8')
                                        existing_data = json.loads(existing_data) if isinstance(existing_data, str) else (existing_data or {})
                                    except Exception:
                                        existing_data = {}
                                    existing_data.update({k: v for k, v in onboarding_payload.items() if v is not None})
                                    # Clear decision-related fields on resubmission to reset verification status
                                    for field in ['decision_type', 'required_changes', 'reapply_after', 'reapply_after_ts']:
                                        existing_data.pop(field, None)
                                    new_json = json.dumps(existing_data)
                                    new_status = 'in_progress' if str(app_row2[2]).lower() != 'approved' else str(app_row2[2]).lower()
                                    # clear decline_reason if previously declined
                                    clear_decline = (str(app_row2[2]).lower() == 'declined')
                                    if clear_decline:
                                        cursor2.execute(
                                            "UPDATE dp_onboarding_applications SET status=%s, decline_reason=NULL, onboarding_data=%s, updated_at=NOW() WHERE id=%s",
                                            [new_status, new_json, app_row2[0]]
                                        )
                                    else:
                                        cursor2.execute(
                                            "UPDATE dp_onboarding_applications SET status=%s, onboarding_data=%s, updated_at=NOW() WHERE id=%s",
                                            [new_status, new_json, app_row2[0]]
                                        )
                                else:
                                    # For new applications, ensure no decision data is included
                                    clean_payload = {k: v for k, v in onboarding_payload.items() if v is not None}
                                    cursor2.execute(
                                        "INSERT INTO dp_onboarding_applications (user_id, status, onboarding_data, created_at, updated_at) VALUES (%s, %s, %s, NOW(), NOW())",
                                        [user_id, 'in_progress', json.dumps(clean_payload)]
                                    )
                        except Exception:
                            pass

                        return Response({
                            "success": True,
                            "message": action_message,
                            "delivery_partner_data": delivery_partner_data,
                            "verification_status": "pending" if not delivery_partner_data.get('is_verified') else "approved"
                        }, status=status.HTTP_200_OK if exists else status.HTTP_201_CREATED)
                    else:
                        return Response(
                            {"error": "Failed to retrieve created delivery partner"},
                            status=status.HTTP_500_INTERNAL_SERVER_ERROR
                        )
                
            except Exception as e:
                logger.error(f"Error creating delivery partner: {str(e)}")
                return Response(
                    {"error": f"Failed to create delivery partner profile: {str(e)}"},
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR
                )
        else:
            return Response(
                {"error": "Validation failed", "details": serializer.errors},
                status=status.HTTP_400_BAD_REQUEST
            )


class UpdateDeliveryPartnerDetailsView(APIView):
    def patch(self, request):
        try:
            partner_id = request.query_params.get('partner_id')
            user_id = request.query_params.get('user_id')
            if not partner_id and not user_id:
                return Response({"message": "partner_id or user_id is required"}, status=status.HTTP_400_BAD_REQUEST)

            allowed = {
                'business_id': 'business_id',
                'vehicle_type': 'vehicle_type',
                'vehicle_number': 'vehicle_number',
                'license_number': 'license_number',
                'status': 'status',
                'is_available': 'is_available',
                'phone_number': 'phone_number',
                'full_address': 'full_address',
                'city': 'city',
                'state': 'state',
                'pincode': 'pincode',
                'delivery_service_area': 'delivery_service_area',
                'delivery_timings': 'delivery_timings',
            }

            updates = {}
            for key, col in allowed.items():
                if key in request.data:
                    updates[col] = request.data.get(key)

            if not updates:
                return Response({"message": "No editable fields provided"}, status=status.HTTP_400_BAD_REQUEST)

            if 'is_available' in updates:
                try:
                    v = int(updates['is_available'])
                    if v not in (0, 1):
                        raise Exception()
                    updates['is_available'] = v
                except Exception:
                    return Response({"message": "is_available must be 0 or 1"}, status=status.HTTP_400_BAD_REQUEST)

            if 'status' in updates and updates['status'] is not None:
                s = str(updates['status']).strip().lower()
                if s in ('1', 'online', 'available'):
                    updates['status'] = 'available'
                elif s in ('0', 'offline'):
                    updates['status'] = 'offline'
                elif s in ('on_delivery', 'ondelivery', 'busy'):
                    updates['status'] = 'on_delivery'
                else:
                    updates['status'] = s

            if 'delivery_timings' in updates:
                try:
                    dt = updates['delivery_timings']
                    if dt is not None and not isinstance(dt, str):
                        updates['delivery_timings'] = json.dumps(dt)
                except Exception:
                    updates['delivery_timings'] = None

            # Enforce 3-day cooldown if previously declined
            # Resolve user_id from partner_id when necessary
            if not user_id and partner_id:
                with connection.cursor() as cursor:
                    cursor.execute("SELECT user_id FROM delivery_partner WHERE id=%s LIMIT 1", [partner_id])
                    row_uid = cursor.fetchone()
                    user_id = row_uid[0] if row_uid else None

            try:
                if user_id:
                    with connection.cursor() as cursor:
                        cursor.execute(
                            "SELECT id, status, decline_reason, onboarding_data FROM dp_onboarding_applications WHERE user_id=%s ORDER BY id DESC LIMIT 1",
                            [user_id]
                        )
                        app_row = cursor.fetchone()
                    if app_row and str(app_row[1]).lower() == 'declined':
                        data = app_row[3]
                        try:
                            if isinstance(data, (bytes, bytearray)):
                                data = data.decode('utf-8')
                            data = json.loads(data) if isinstance(data, str) else (data or {})
                        except Exception:
                            data = {}
                        now_ts = int(timezone.now().timestamp())
                        reapply_ts = None
                        if isinstance(data.get('reapply_after_ts'), (int, float, str)):
                            try:
                                reapply_ts = int(data.get('reapply_after_ts'))
                            except Exception:
                                reapply_ts = None
                        if reapply_ts is None and data.get('reapply_after'):
                            try:
                                dtv = datetime.fromisoformat(str(data.get('reapply_after')))
                                if timezone.is_naive(dtv):
                                    from django.utils import timezone as dj_tz
                                    dtv = dj_tz.make_aware(dtv)
                                reapply_ts = int(dtv.timestamp())
                            except Exception:
                                reapply_ts = None
                        if reapply_ts is not None and now_ts < reapply_ts:
                            return Response({
                                "success": False,
                                "message": "Application was declined. You can re-apply after the cooldown ends.",
                                "verification_status": "rejected",
                                "decision_reason": app_row[2],
                                "reapply_after": data.get('reapply_after')
                            }, status=status.HTTP_400_BAD_REQUEST)
            except Exception:
                pass

            set_parts = []
            params = []
            for col, val in updates.items():
                set_parts.append(f"{col} = %s")
                params.append(val)
            set_parts.append("updated_at = NOW()")
            set_sql = ", ".join(set_parts)

            where_sql = "id = %s" if partner_id else "user_id = %s"
            params.append(partner_id if partner_id else user_id)

            with connection.cursor() as cursor:
                cursor.execute(f"UPDATE delivery_partner SET {set_sql} WHERE {where_sql}", params)
                if cursor.rowcount == 0:
                    return Response({"message": "Delivery partner not found"}, status=status.HTTP_404_NOT_FOUND)

                id_where = "id = %s" if partner_id else "user_id = %s"
                cursor.execute(
                    f"""
                    SELECT id, user_id, business_id, vehicle_type, vehicle_number, license_number,
                           status, is_available, phone_number, full_address, city, state, pincode,
                           delivery_service_area, delivery_timings, is_verified, created_at, updated_at
                    FROM delivery_partner WHERE {id_where} LIMIT 1
                    """,
                    [partner_id if partner_id else user_id]
                )
                row = cursor.fetchone()
                cols = [
                    'id','user_id','business_id','vehicle_type','vehicle_number','license_number',
                    'status','is_available','phone_number','full_address','city','state','pincode',
                    'delivery_service_area','delivery_timings','is_verified','created_at','updated_at'
                ]
                obj = dict(zip(cols, row)) if row else None

                if obj and 'delivery_timings' in obj:
                    try:
                        _dt = obj['delivery_timings']
                        if isinstance(_dt, (bytes, bytearray)):
                            _dt = _dt.decode('utf-8')
                        obj['delivery_timings'] = json.loads(_dt) if isinstance(_dt, str) and _dt else _dt
                    except Exception:
                        obj['delivery_timings'] = None

                # Upsert onboarding application with latest updates and reset status to in_progress
                try:
                    if user_id:
                        onboarding_payload = {k: updates.get(k) for k in ['business_id','vehicle_type','vehicle_number','license_number','phone_number','full_address','city','state','pincode','delivery_service_area','delivery_timings']}
                        with connection.cursor() as cursor2:
                            cursor2.execute("SELECT id, onboarding_data, status FROM dp_onboarding_applications WHERE user_id=%s ORDER BY id DESC LIMIT 1", [user_id])
                            app_row2 = cursor2.fetchone()
                            if app_row2:
                                existing_data = app_row2[1]
                                try:
                                    if isinstance(existing_data, (bytes, bytearray)):
                                        existing_data = existing_data.decode('utf-8')
                                    existing_data = json.loads(existing_data) if isinstance(existing_data, str) else (existing_data or {})
                                except Exception:
                                    existing_data = {}
                                # Merge only provided fields
                                for k, v in onboarding_payload.items():
                                    if v is not None:
                                        existing_data[k] = v
                                existing_data['last_resubmitted_at'] = timezone.now().isoformat()
                                new_json = json.dumps(existing_data)
                                new_status = 'in_progress' if str(app_row2[2]).lower() != 'approved' else str(app_row2[2]).lower()
                                # Clear decline_reason when moving away from declined
                                clear_decline = (str(app_row2[2]).lower() == 'declined')
                                if clear_decline:
                                    cursor2.execute(
                                        "UPDATE dp_onboarding_applications SET status=%s, decline_reason=NULL, onboarding_data=%s, updated_at=NOW() WHERE id=%s",
                                        [new_status, new_json, app_row2[0]]
                                    )
                                else:
                                    cursor2.execute(
                                        "UPDATE dp_onboarding_applications SET status=%s, onboarding_data=%s, updated_at=NOW() WHERE id=%s",
                                        [new_status, new_json, app_row2[0]]
                                    )
                            else:
                                cursor2.execute(
                                    "INSERT INTO dp_onboarding_applications (user_id, status, onboarding_data, created_at, updated_at) VALUES (%s, %s, %s, NOW(), NOW())",
                                    [user_id, 'in_progress', json.dumps(onboarding_payload)]
                                )
                except Exception:
                    pass

            return Response({
                "success": True,
                "message": "Delivery partner updated successfully",
                "delivery_partner": obj
            }, status=status.HTTP_200_OK)
        except Exception as e:
            logger.error(f"UpdateDeliveryPartnerDetailsView error: {e}")
            return Response({"message": "Failed to update delivery partner"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class StartOrResumeOnboardingSessionView(APIView):
    def post(self, request):
        mobile = request.data.get('mobileNumber')
        otp_code = request.data.get('otp')

        if not mobile or not otp_code:
            return Response({"message": "mobileNumber and otp are required"}, status=status.HTTP_400_BAD_REQUEST)

        # Verify OTP using existing logic
        try:
            user = Registration.objects.filter(mobileNumber=mobile).first()

            if otp_code == "252025":
                # Dev override
                if user and not user.is_verified:
                    user.is_verified = True
                    user.save(update_fields=['is_verified'])
            else:
                if not user:
                    return Response({"message": f"User with mobile number {mobile} not found."}, status=status.HTTP_404_NOT_FOUND)

                latest_otp = Otp.objects.filter(mobileNumber=user, status=False).order_by('-created_at').first()
                if not latest_otp:
                    return Response({"message": "Invalid OTP or it has already been used."}, status=status.HTTP_400_BAD_REQUEST)

                if timezone.now() - latest_otp.updated_at > timedelta(minutes=3):
                    return Response({"message": "OTP has expired. Please request a new one."}, status=status.HTTP_400_BAD_REQUEST)

                if latest_otp.code != otp_code:
                    return Response({"message": "Invalid OTP. Please try again."}, status=status.HTTP_400_BAD_REQUEST)

                # Mark verified
                if not user.is_verified:
                    user.is_verified = True
                    user.save(update_fields=['is_verified'])
                latest_otp.status = True
                latest_otp.save(update_fields=['status', 'updated_at'])

            # Ensure user exists (create minimal if needed)
            if not user:
                from kirazee_app.models import generate_user_id
                new_id = generate_user_id()
                user = Registration.objects.create(
                    user_id=new_id,
                    firstName="",
                    lastName="",
                    countryCode="+91",
                    mobileNumber=mobile,
                    emailID=f"{mobile}@kirazee.local",
                    is_verified=True,
                    is_active=True,
                    user_mode='delivery_partner',
                    whichapp='Kirazee'
                )
            else:
                # Align mode
                if user.user_mode != 'delivery_partner':
                    user.user_mode = 'delivery_partner'
                    user.save(update_fields=['user_mode'])

            # Upsert application and fetch state
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO dp_onboarding_applications (user_id, status, onboarding_data, created_at, updated_at)
                    VALUES (%s, 'in_progress', NULL, NOW(), NOW())
                    ON DUPLICATE KEY UPDATE updated_at = NOW()
                    """,
                    [user.user_id]
                )

                cursor.execute(
                    "SELECT id, status, onboarding_data FROM dp_onboarding_applications WHERE user_id = %s LIMIT 1",
                    [user.user_id]
                )
                app_row = cursor.fetchone()
                if not app_row:
                    return Response({"message": "Failed to create onboarding application"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

                application_id = app_row[0]
                app_status = app_row[1]
                onboarding_data = app_row[2]

                # Fetch documents
                cursor.execute(
                    """
                    SELECT id, document_type, file_url, file_name, uploaded_at
                    FROM dp_onboarding_documents
                    WHERE application_id = %s ORDER BY id
                    """,
                    [application_id]
                )
                doc_columns = [col[0] for col in cursor.description]
                documents = [dict(zip(doc_columns, r)) for r in cursor.fetchall()]

                # Log action
                details = json.dumps({"mobileNumber": mobile})
                cursor.execute(
                    """
                    INSERT INTO dp_action_logs (actor_user_id, target_application_id, action_type, details, created_at)
                    VALUES (%s, %s, 'START_SESSION', %s, NOW())
                    """,
                    [user.user_id, application_id, details]
                )

            # Normalize onboarding_data
            try:
                if isinstance(onboarding_data, (bytes, bytearray)):
                    onboarding_data = onboarding_data.decode('utf-8')
                onboarding_data = json.loads(onboarding_data) if isinstance(onboarding_data, str) else onboarding_data
            except Exception:
                onboarding_data = None

            return Response({
                "application_id": application_id,
                "status": app_status,
                "onboarding_data": onboarding_data,
                "documents": documents
            }, status=status.HTTP_200_OK)

        except Exception as e:
            logger.error(f"StartOrResumeOnboardingSessionView error: {e}")
            return Response({"message": "Failed to start session"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class ApplicantDecisionView(APIView):
    def post(self, request, application_id: int):
        decision = (request.data.get('decision') or '').strip().lower()
        business_id = request.data.get('business_id')
        decline_reason = request.data.get('decline_reason')
        required_changes = request.data.get('required_changes')
        # cooldown days for re-apply; default 3
        try:
            cooldown_days = int(request.data.get('cooldown_days') or request.data.get('reapply_after_days') or 3)
        except Exception:
            cooldown_days = 3
        # Resolve admin actor id if available
        admin_user_id = None
        try:
            admin_user_id = getattr(request.user, 'user_id', None)
        except Exception:
            admin_user_id = None
        if not admin_user_id:
            admin_user_id = request.query_params.get('actor_user_id')

        if decision not in {"approved", "declined", "required_changes"}:
            return Response({"message": "decision must be 'approved', 'declined' or 'required_changes'"}, status=status.HTTP_400_BAD_REQUEST)

        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT id, user_id, status, onboarding_data FROM dp_onboarding_applications WHERE id = %s LIMIT 1",
                    [application_id]
                )
                row = cursor.fetchone()
                if not row:
                    return Response({"message": "Application not found"}, status=status.HTTP_404_NOT_FOUND)

                app_id, user_id, app_status, onboarding_data = row

            if decision == 'approved':
                if not business_id:
                    return Response({"message": "business_id required for approval"}, status=status.HTTP_400_BAD_REQUEST)

                try:
                    if isinstance(onboarding_data, (bytes, bytearray)):
                        onboarding_data = onboarding_data.decode('utf-8')
                    data = json.loads(onboarding_data) if isinstance(onboarding_data, str) else (onboarding_data or {})
                except Exception:
                    data = {}

                vehicle_type = data.get('vehicle_type')
                vehicle_number = data.get('vehicle_number')
                license_number = data.get('license_number')
                phone_number = data.get('phone_number')
                full_address = data.get('full_address')
                city = data.get('city')
                state_name = data.get('state')
                pincode = data.get('pincode')

                pan_number = data.get('pan_number')
                bank_account_number = data.get('bank_account_number')
                ifsc_code = data.get('ifsc_code')

                with transaction.atomic():
                    with connection.cursor() as cursor:
                        # Upsert delivery_partner
                        cursor.execute(
                            """
                            INSERT INTO delivery_partner 
                                (user_id, business_id, vehicle_type, vehicle_number, license_number, latitude, longitude, status, is_available, rating, total_deliveries, phone_number, full_address, city, state, pincode, is_verified, created_at, updated_at)
                            VALUES
                                (%s, %s, %s, %s, %s, NULL, NULL, '1', 0, 0.0, 0, %s, %s, %s, %s, %s, 1, NOW(), NOW())
                            ON DUPLICATE KEY UPDATE 
                                business_id=VALUES(business_id), vehicle_type=VALUES(vehicle_type), vehicle_number=VALUES(vehicle_number),
                                license_number=VALUES(license_number), phone_number=VALUES(phone_number), full_address=VALUES(full_address),
                                city=VALUES(city), state=VALUES(state), pincode=VALUES(pincode), is_verified=1, updated_at=NOW()
                            """,
                            [user_id, business_id, vehicle_type, vehicle_number, license_number, phone_number, full_address, city, state_name, pincode]
                        )

                        # Get partner_id
                        cursor.execute("SELECT id FROM delivery_partner WHERE user_id=%s LIMIT 1", [user_id])
                        dp_row = cursor.fetchone()
                        if not dp_row:
                            raise Exception("Failed to upsert delivery_partner")
                        partner_id = dp_row[0]

                        # Upsert financials
                        cursor.execute(
                            """
                            INSERT INTO delivery_partner_financials (partner_id, pan_number, bank_account_number, ifsc_code, created_at, updated_at)
                            VALUES (%s, %s, %s, %s, NOW(), NOW())
                            ON DUPLICATE KEY UPDATE pan_number=VALUES(pan_number), bank_account_number=VALUES(bank_account_number), ifsc_code=VALUES(ifsc_code), updated_at=NOW()
                            """,
                            [partner_id, pan_number, bank_account_number, ifsc_code]
                        )

                        # Copy documents if permanent table exists
                        try:
                            cursor.execute("SHOW TABLES LIKE 'delivery_partner_documents'")
                            if cursor.fetchone():
                                cursor.execute("SELECT document_type, file_url FROM dp_onboarding_documents WHERE application_id = %s", [application_id])
                                for doc_type, file_url in cursor.fetchall():
                                    cursor.execute(
                                        """
                                        INSERT INTO delivery_partner_documents (partner_id, document_type, document_url, is_verified, uploaded_at)
                                        VALUES (%s, %s, %s, 1, NOW())
                                        ON DUPLICATE KEY UPDATE document_url=VALUES(document_url), is_verified=1, uploaded_at=NOW()
                                        """,
                                        [partner_id, doc_type, file_url]
                                    )
                        except Exception:
                            pass

                        # Approve application
                        cursor.execute("UPDATE dp_onboarding_applications SET status='approved', updated_at=NOW() WHERE id=%s", [application_id])

                        # Log action
                        details = json.dumps({"decision": "approved", "business_id": business_id})
                        cursor.execute(
                            """
                            INSERT INTO dp_action_logs (actor_user_id, target_partner_id, target_application_id, action_type, details, created_at)
                            VALUES (%s, %s, %s, 'APPROVE_APPLICATION', %s, NOW())
                            """,
                            [admin_user_id, partner_id, application_id, details]
                        )

                return Response({"success": True, "message": "Application approved and migrated."}, status=status.HTTP_200_OK)

            elif decision == 'required_changes':
                # Set status to pending_review and store required_changes + reapply_after metadata
                reapply_dt = timezone.now() + timedelta(days=cooldown_days)
                reapply_after_iso = reapply_dt.isoformat()
                reapply_after_ts = int(reapply_dt.timestamp())
                with connection.cursor() as cursor:
                    # merge into onboarding_data JSON
                    cursor.execute("SELECT onboarding_data FROM dp_onboarding_applications WHERE id=%s LIMIT 1", [application_id])
                    row = cursor.fetchone()
                    existing = row[0] if row else None
                    try:
                        if isinstance(existing, (bytes, bytearray)):
                            existing = existing.decode('utf-8')
                        existing = json.loads(existing) if isinstance(existing, str) else (existing or {})
                    except Exception:
                        existing = {}
                    existing['required_changes'] = required_changes
                    existing['reapply_after'] = reapply_after_iso
                    existing['reapply_after_ts'] = reapply_after_ts
                    existing['decision_type'] = 'required_changes'  # Store actual decision type
                    new_json = json.dumps(existing)
                    cursor.execute(
                        "UPDATE dp_onboarding_applications SET status='pending_review', onboarding_data=%s, updated_at=NOW() WHERE id=%s",
                        [new_json, application_id]
                    )

                    details = json.dumps({"decision": "required_changes", "required_changes": required_changes, "reapply_after": reapply_after_iso})
                    cursor.execute(
                        """
                        INSERT INTO dp_action_logs (actor_user_id, target_application_id, action_type, details, created_at)
                        VALUES (%s, %s, 'REQUIRE_CHANGES', %s, NOW())
                        """,
                        [admin_user_id, application_id, details]
                    )

                return Response({"success": True, "message": "Application marked as required changes.", "reapply_after": reapply_after_iso}, status=status.HTTP_200_OK)
            else:  # declined
                # Decline and set reapply_after metadata
                reapply_dt = timezone.now() + timedelta(days=cooldown_days)
                reapply_after_iso = reapply_dt.isoformat()
                reapply_after_ts = int(reapply_dt.timestamp())
                with connection.cursor() as cursor:
                    # update status and decline_reason
                    cursor.execute(
                        "UPDATE dp_onboarding_applications SET status='declined', decline_reason=%s, updated_at=NOW() WHERE id=%s",
                        [decline_reason, application_id]
                    )
                    # also merge reapply_after fields into onboarding_data
                    cursor.execute("SELECT onboarding_data FROM dp_onboarding_applications WHERE id=%s LIMIT 1", [application_id])
                    row = cursor.fetchone()
                    existing = row[0] if row else None
                    try:
                        if isinstance(existing, (bytes, bytearray)):
                            existing = existing.decode('utf-8')
                        existing = json.loads(existing) if isinstance(existing, str) else (existing or {})
                    except Exception:
                        existing = {}
                    existing['reapply_after'] = reapply_after_iso
                    existing['reapply_after_ts'] = reapply_after_ts
                    new_json = json.dumps(existing)
                    cursor.execute(
                        "UPDATE dp_onboarding_applications SET onboarding_data=%s WHERE id=%s",
                        [new_json, application_id]
                    )
                    # Remove temp docs
                    cursor.execute("DELETE FROM dp_onboarding_documents WHERE application_id=%s", [application_id])

                    details = json.dumps({"decision": "declined", "reason": decline_reason, "reapply_after": reapply_after_iso})
                    cursor.execute(
                        """
                        INSERT INTO dp_action_logs (actor_user_id, target_application_id, action_type, details, created_at)
                        VALUES (%s, %s, 'DECLINE_APPLICATION', %s, NOW())
                        """,
                        [admin_user_id, application_id, details]
                    )

                return Response({"success": True, "message": "Application declined and temporary data cleared.", "reapply_after": reapply_after_iso}, status=status.HTTP_200_OK)

        except Exception as e:
            logger.error(f"ApplicantDecisionView error: {e}")
            return Response({"message": "Decision processing failed"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class AdminApplicantListView(APIView):
    def get(self, request):
        try:
            status_param = (request.query_params.get('status') or 'all').strip().lower()
            mapping = {'pending': 'in_progress', 'approved': 'approved', 'rejected': 'declined'}
            backend_status = mapping.get(status_param)
            vehicle_type = (request.query_params.get('vehicle_type') or '').strip().lower()
            q = (request.query_params.get('q') or request.query_params.get('search') or request.query_params.get('searchText') or '').strip().lower()
            city = (request.query_params.get('city') or '').strip().lower()
            state_name = (request.query_params.get('state') or '').strip().lower()
            date_from = request.query_params.get('date_from')
            date_to = request.query_params.get('date_to')
            try:
                page = max(int(request.query_params.get('page', 1)), 1)
            except Exception:
                page = 1
            try:
                limit = min(max(int(request.query_params.get('limit', 10)), 1), 100)
            except Exception:
                limit = 10
            offset = (page - 1) * limit

            wheres = []
            params = []
            if backend_status and status_param != 'all':
                wheres.append("a.status = %s")
                params.append(backend_status)
            if date_from:
                wheres.append("a.created_at >= %s")
                params.append(date_from)
            if date_to:
                wheres.append("a.created_at <= %s")
                params.append(date_to)
            if q:
                wheres.append("("
                              "LOWER(COALESCE(r.firstName,'')) LIKE %s OR "
                              "LOWER(COALESCE(r.lastName,'')) LIKE %s OR "
                              "LOWER(COALESCE(r.mobileNumber,'')) LIKE %s OR "
                              "LOWER(JSON_UNQUOTE(JSON_EXTRACT(a.onboarding_data, '$.license_number'))) LIKE %s OR "
                              "LOWER(JSON_UNQUOTE(JSON_EXTRACT(a.onboarding_data, '$.vehicle_number'))) LIKE %s OR "
                              "LOWER(JSON_UNQUOTE(JSON_EXTRACT(a.onboarding_data, '$.phone_number'))) LIKE %s"
                              ")")
                like_q = f"%{q}%"
                params.extend([like_q, like_q, like_q, like_q, like_q, like_q])
            if city:
                wheres.append("LOWER(JSON_UNQUOTE(JSON_EXTRACT(a.onboarding_data, '$.city'))) LIKE %s")
                params.append(f"%{city}%")
            if state_name:
                wheres.append("LOWER(JSON_UNQUOTE(JSON_EXTRACT(a.onboarding_data, '$.state'))) LIKE %s")
                params.append(f"%{state_name}%")
            if vehicle_type and vehicle_type != 'all':
                wheres.append("LOWER(JSON_UNQUOTE(JSON_EXTRACT(a.onboarding_data, '$.vehicle_type'))) = %s")
                params.append(vehicle_type)

            where_clause = f"WHERE {' AND '.join(wheres)}" if wheres else ""

            select_sql = f"""
                SELECT 
                    a.id, a.user_id, a.status, a.onboarding_data, a.created_at,
                    r.firstName, r.lastName, r.mobileNumber,
                    (SELECT COUNT(*) FROM dp_onboarding_documents d WHERE d.application_id = a.id) AS documents_count
                FROM dp_onboarding_applications a
                LEFT JOIN registrations r ON r.user_id = a.user_id
                {where_clause}
                ORDER BY a.created_at DESC
                LIMIT %s OFFSET %s
            """
            count_sql = f"""
                SELECT COUNT(*)
                FROM dp_onboarding_applications a
                LEFT JOIN registrations r ON r.user_id = a.user_id
                {where_clause}
            """

            with connection.cursor() as cursor:
                cursor.execute(count_sql, params)
                total = cursor.fetchone()[0] if cursor.rowcount != -1 else 0

                cursor.execute(select_sql, params + [limit, offset])
                rows = cursor.fetchall()

            status_map_ui = {'in_progress': 'Pending Review', 'approved': 'Approved', 'declined': 'Rejected'}
            applicants = []
            for row in rows:
                app_id, user_id, db_status, onboarding_data, created_at, first_name, last_name, mobile, documents_count = row
                try:
                    if isinstance(onboarding_data, (bytes, bytearray)):
                        onboarding_data = onboarding_data.decode('utf-8')
                    data = json.loads(onboarding_data) if isinstance(onboarding_data, str) else (onboarding_data or {})
                except Exception:
                    data = {}

                applicants.append({
                    "application_id": int(app_id),
                    "user_id": int(user_id) if user_id is not None else None,
                    "full_name": first_name or data.get('full_name') or "",
                    "last_name": last_name or data.get('last_name') or "",
                    "mobile_number": mobile or data.get('phone_number') or "",
                    "license_number": data.get('license_number'),
                    "vehicle_type": (data.get('vehicle_type') or "") or None,
                    "vehicle_number": data.get('vehicle_number'),
                    "status": status_map_ui.get(str(db_status), str(db_status)),
                    "city": data.get('city'),
                    "state": data.get('state'),
                    "delivery_service_area": data.get('delivery_service_area'),
                    "pincode": data.get('pincode'),
                    "submission_date": created_at,
                    "documents_count": int(documents_count or 0),
                })

            total_pages = (total + limit - 1) // limit if limit else 1
            return Response({
                "success": True,
                "filters": {
                    "status": status_param,
                    "vehicle_type": vehicle_type or "all",
                    "q": q,
                    "city": city,
                    "state": state_name,
                    "date_from": date_from,
                    "date_to": date_to,
                    "page": page,
                    "limit": limit
                },
                "pagination": {
                    "total": int(total),
                    "current_page": page,
                    "per_page": limit,
                    "total_pages": int(total_pages),
                    "has_next_page": page < total_pages,
                    "has_prev_page": page > 1
                },
                "applicants": applicants
            }, status=status.HTTP_200_OK)
        except Exception as e:
            logger.error(f"AdminApplicantListView error: {e}")
            return Response({"message": "Failed to list applicants"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class AdminApplicantDetailView(APIView):
    def get(self, request, application_id: int):
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT a.id, a.user_id, a.status, a.onboarding_data, a.created_at, a.updated_at,
                           r.firstName, r.lastName, r.mobileNumber
                    FROM dp_onboarding_applications a
                    LEFT JOIN registrations r ON r.user_id = a.user_id
                    WHERE a.id = %s LIMIT 1
                    """,
                    [application_id]
                )
                row = cursor.fetchone()
                if not row:
                    return Response({"message": "Application not found"}, status=status.HTTP_404_NOT_FOUND)

                app_id, user_id, db_status, onboarding_data, created_at, updated_at, first_name, last_name, mobile = row

                cursor.execute(
                    """
                    SELECT id, document_type, file_url, file_name, uploaded_at
                    FROM dp_onboarding_documents
                    WHERE application_id = %s ORDER BY id
                    """,
                    [application_id]
                )
                doc_rows = cursor.fetchall()

            try:
                if isinstance(onboarding_data, (bytes, bytearray)):
                    onboarding_data = onboarding_data.decode('utf-8')
                data = json.loads(onboarding_data) if isinstance(onboarding_data, str) else (onboarding_data or {})
            except Exception:
                data = {}

            def _abs_url(path: str) -> str:
                """Build S3 URL for document path."""
                return build_s3_file_url(path)

            documents = []
            for d in doc_rows:
                did, dtype, file_url, file_name, uploaded_at = d
                documents.append({
                    "id": int(did),
                    "document_type": dtype,
                    "document_name": file_name,
                    "document_url": _abs_url(file_url),
                    "uploaded_at": uploaded_at
                })

            status_map_ui = {'in_progress': 'Pending Review', 'approved': 'Approved', 'declined': 'Rejected', 'required_changes': 'Required Changes'}

            return Response({
                "success": True,
                "application": {
                    "application_id": int(app_id),
                    "user_id": int(user_id) if user_id is not None else None,
                    "status": status_map_ui.get(str(db_status), str(db_status)),
                    "submission_date": created_at,
                    "updated_at": updated_at,
                    "onboarding_data": {
                        "full_name": first_name or data.get('full_name'),
                        "last_name": last_name or data.get('last_name'),
                        "mobile_number": mobile or data.get('phone_number'),
                        "vehicle_type": data.get('vehicle_type'),
                        "vehicle_number": data.get('vehicle_number'),
                        "license_number": data.get('license_number'),
                        "full_address": data.get('full_address'),
                        "current_address": data.get('current_address'),
                        "city": data.get('city'),
                        "state": data.get('state'),
                        "pincode": data.get('pincode'),
                        "delivery_service_area": data.get('delivery_service_area'),
                        "pan_number": data.get('pan_number'),
                        "bank_account_number": data.get('bank_account_number'),
                        "ifsc_code": data.get('ifsc_code'),
                        "required_changes": data.get('required_changes'),
                        "reapply_after": data.get('reapply_after')
                    },
                    "documents": documents
                }
            }, status=status.HTTP_200_OK)
        except Exception as e:
            logger.error(f"AdminApplicantDetailView error: {e}")
            return Response({"message": "Failed to load applicant"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class AdminApplicantStatusUpdateView(APIView):
    def patch(self, request, application_id: int):
        try:
            new_status = (request.data.get('status') or '').strip().lower()
            if new_status in ('pending', 'in_progress'):
                backend_status = 'in_progress'
            else:
                return Response({"message": "status must be 'pending' or 'in_progress'"}, status=status.HTTP_400_BAD_REQUEST)

            with connection.cursor() as cursor:
                cursor.execute(
                    "UPDATE dp_onboarding_applications SET status=%s, updated_at=NOW() WHERE id=%s",
                    [backend_status, application_id]
                )
                if cursor.rowcount == 0:
                    return Response({"message": "Application not found"}, status=status.HTTP_404_NOT_FOUND)

            return Response({
                "success": True,
                "message": "Status updated.",
                "status": backend_status
            }, status=status.HTTP_200_OK)
        except Exception as e:
            logger.error(f"AdminApplicantStatusUpdateView error: {e}")
            return Response({"message": "Failed to update status"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class AdminUnverifiedPartnersListView(APIView):
    def get(self, request):
        try:
            vehicle_type = (request.query_params.get('vehicle_type') or '').strip().lower()
            q = (request.query_params.get('q') or request.query_params.get('search') or request.query_params.get('searchText') or '').strip().lower()
            city = (request.query_params.get('city') or '').strip().lower()
            state_name = (request.query_params.get('state') or '').strip().lower()
            date_from = request.query_params.get('date_from')
            date_to = request.query_params.get('date_to')
            try:
                page = max(int(request.query_params.get('page', 1)), 1)
            except Exception:
                page = 1
            try:
                limit = min(max(int(request.query_params.get('limit', 10)), 1), 100)
            except Exception:
                limit = 10
            offset = (page - 1) * limit

            # Check if delivery_partner_documents exists for doc counts
            docs_table_exists = False
            try:
                with connection.cursor() as cursor:
                    cursor.execute("SHOW TABLES LIKE 'delivery_partner_documents'")
                    docs_table_exists = bool(cursor.fetchone())
            except Exception:
                docs_table_exists = False

            wheres = [
                "(dp.is_verified = 0 OR dp.is_verified = '0')",
                "(dp.status = 0 OR dp.status = '0' OR LOWER(COALESCE(dp.status,'')) = 'offline')"
            ]
            params = []

            if date_from:
                wheres.append("dp.created_at >= %s")
                params.append(date_from)
            if date_to:
                wheres.append("dp.created_at <= %s")
                params.append(date_to)
            if q:
                wheres.append("("
                              "LOWER(COALESCE(r.firstName,'')) LIKE %s OR "
                              "LOWER(COALESCE(r.lastName,'')) LIKE %s OR "
                              "LOWER(COALESCE(r.mobileNumber,'')) LIKE %s OR "
                              "LOWER(COALESCE(dp.phone_number,'')) LIKE %s OR "
                              "LOWER(COALESCE(dp.license_number,'')) LIKE %s OR "
                              "LOWER(COALESCE(dp.vehicle_number,'')) LIKE %s"
                              ")")
                like_q = f"%{q}%"
                params.extend([like_q, like_q, like_q, like_q, like_q, like_q])
            if city:
                wheres.append("LOWER(COALESCE(dp.city,'')) LIKE %s")
                params.append(f"%{city}%")
            if state_name:
                wheres.append("LOWER(COALESCE(dp.state,'')) LIKE %s")
                params.append(f"%{state_name}%")
            if vehicle_type and vehicle_type != 'all':
                wheres.append("LOWER(COALESCE(dp.vehicle_type,'')) = %s")
                params.append(vehicle_type)

            where_clause = f"WHERE {' AND '.join(wheres)}" if wheres else ""

            doc_count_expr = "(SELECT COUNT(*) FROM delivery_partner_documents dd WHERE dd.partner_id = dp.id)" if docs_table_exists else "0"

            select_sql = f"""
                SELECT 
                    dp.id, dp.user_id, dp.status, dp.is_verified, dp.vehicle_type, dp.vehicle_number,
                    dp.license_number, dp.full_address, dp.city, dp.state, dp.pincode, dp.delivery_service_area,
                    dp.phone_number, dp.created_at, dp.updated_at,
                    r.firstName, r.lastName, r.mobileNumber,
                    {doc_count_expr} AS documents_count,
                    app.status AS application_status
                FROM delivery_partner dp
                LEFT JOIN registrations r ON r.user_id = dp.user_id
                LEFT JOIN dp_onboarding_applications app ON app.user_id = dp.user_id
                {where_clause}
                ORDER BY dp.created_at DESC
                LIMIT %s OFFSET %s
            """
            count_sql = f"""
                SELECT COUNT(*)
                FROM delivery_partner dp
                LEFT JOIN registrations r ON r.user_id = dp.user_id
                LEFT JOIN dp_onboarding_applications app ON app.user_id = dp.user_id
                {where_clause}
            """

            with connection.cursor() as cursor:
                cursor.execute(count_sql, params)
                total = cursor.fetchone()[0] if cursor.rowcount != -1 else 0

                cursor.execute(select_sql, params + [limit, offset])
                rows = cursor.fetchall()

            partners = []
            for row in rows:
                (dp_id, user_id, dp_status, is_verified, vehicle_type_val, vehicle_number, license_number, full_address,
                 city_val, state_val, pincode, service_area, phone_number, created_at, updated_at,
                 first_name, last_name, mobile, documents_count, application_status) = row

                # Normalize status for UI based on application status
                if application_status:
                    app_status_lower = str(application_status).lower()
                    if app_status_lower == 'approved':
                        ui_status = 'approved'
                    elif app_status_lower == 'declined':
                        ui_status = 'declined'
                    else:
                        ui_status = 'in_progress'
                else:
                    ui_status = 'in_progress'

                partners.append({
                    "partner_id": int(dp_id),
                    "user_id": int(user_id) if user_id is not None else None,
                    "full_name": first_name or "",
                    "last_name": last_name or "",
                    "mobile_number": mobile or phone_number or "",
                    "license_number": license_number,
                    "vehicle_type": (vehicle_type_val or "").lower() if vehicle_type_val else None,
                    "vehicle_number": vehicle_number,
                    "status": ui_status,
                    "full_address": full_address,
                    "city": city_val,
                    "state": state_val,
                    "pincode": pincode,
                    "delivery_service_area": service_area,
                    "is_verified": bool(int(is_verified)) if is_verified is not None and str(is_verified).isdigit() else False,
                    "submission_date": created_at,
                    "documents_count": int(documents_count or 0)
                })

            total_pages = (total + limit - 1) // limit if limit else 1
            return Response({
                "success": True,
                "filters": {
                    "vehicle_type": vehicle_type or "all",
                    "q": q,
                    "city": city,
                    "state": state_name,
                    "date_from": date_from,
                    "date_to": date_to,
                    "page": page,
                    "limit": limit
                },
                "pagination": {
                    "total": int(total),
                    "current_page": page,
                    "per_page": limit,
                    "total_pages": int(total_pages),
                    "has_next_page": page < total_pages,
                    "has_prev_page": page > 1
                },
                "partners": partners
            }, status=status.HTTP_200_OK)
        except Exception as e:
            logger.error(f"AdminUnverifiedPartnersListView error: {e}")
            return Response({"message": "Failed to list unverified partners"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class AdminPartnerDetailView(APIView):
    def get(self, request, partner_id: int):
        try:
            with connection.cursor() as cursor:
                # Partner + user basics
                cursor.execute(
                    """
                    SELECT 
                        dp.id, dp.user_id, dp.status, dp.is_verified, dp.vehicle_type, dp.vehicle_number,
                        dp.license_number, dp.full_address, dp.city, dp.state, dp.pincode, dp.delivery_service_area,
                        dp.phone_number, dp.created_at, dp.updated_at,
                        r.firstName, r.lastName, r.mobileNumber
                    FROM delivery_partner dp
                    LEFT JOIN registrations r ON r.user_id = dp.user_id
                    WHERE dp.id = %s LIMIT 1
                    """,
                    [partner_id]
                )
                row = cursor.fetchone()
                if not row:
                    return Response({"message": "Delivery partner not found"}, status=status.HTTP_404_NOT_FOUND)

                (dp_id, user_id, dp_status, is_verified, vehicle_type_val, vehicle_number, license_number, full_address,
                 city_val, state_val, pincode, service_area, phone_number, created_at, updated_at,
                 first_name, last_name, mobile) = row

                # Documents
                cursor.execute(
                    """
                    SELECT document_type, document_url, is_verified, uploaded_at
                    FROM delivery_partner_documents
                    WHERE partner_id = %s ORDER BY id
                    """,
                    [partner_id]
                )
                doc_rows = cursor.fetchall()

                # Financials
                cursor.execute(
                    """
                    SELECT pan_number, bank_account_number, ifsc_code
                    FROM delivery_partner_financials
                    WHERE partner_id = %s LIMIT 1
                    """,
                    [partner_id]
                )
                fin_row = cursor.fetchone()

            def _abs_url(path: str) -> str:
                """Build S3 URL for document path."""
                return build_s3_file_url(path)

            documents = []
            present_types = set()
            verified_types = set()
            for d in doc_rows:
                dtype, file_url, d_verified, uploaded_at = d
                documents.append({
                    "document_type": dtype,
                    "document_url": _abs_url(file_url),
                    "is_verified": bool(int(d_verified)) if d_verified is not None and str(d_verified).isdigit() else bool(d_verified),
                    "uploaded_at": uploaded_at
                })
                present_types.add(dtype)
                if (str(d_verified).isdigit() and int(d_verified) == 1) or (str(d_verified).lower() in ("true", "1")):
                    verified_types.add(dtype)

            financials = None
            if fin_row:
                financials = {
                    "pan_number": fin_row[0],
                    "bank_account_number": fin_row[1],
                    "ifsc_code": fin_row[2]
                }

            required_doc_types = ["license", "rc_book", "aadhar", "bank_book"]
            verification_summary = {
                "required_doc_types": required_doc_types,
                "present_doc_types": sorted(list(present_types)),
                "verified_doc_types": sorted(list(verified_types)),
                "all_documents_present": all(dt in present_types for dt in required_doc_types),
                "all_documents_verified": all(dt in verified_types for dt in required_doc_types),
            }

            ui_status = str(dp_status)
            partner = {
                "partner_id": int(dp_id),
                "user_id": int(user_id) if user_id is not None else None,
                "full_name": first_name or "",
                "last_name": last_name or "",
                "mobile_number": mobile or phone_number or "",
                "license_number": license_number,
                "vehicle_type": (vehicle_type_val or "").lower() if vehicle_type_val else None,
                "vehicle_number": vehicle_number,
                "status": ui_status,
                "full_address": full_address,
                "city": city_val,
                "state": state_val,
                "pincode": pincode,
                "delivery_service_area": service_area,
                "is_verified": bool(int(is_verified)) if is_verified is not None and str(is_verified).isdigit() else bool(is_verified),
                "created_at": created_at,
                "updated_at": updated_at
            }

            return Response({
                "success": True,
                "partner": partner,
                "documents": documents,
                "financials": financials,
                "verification_summary": verification_summary
            }, status=status.HTTP_200_OK)
        except Exception as e:
            logger.error(f"AdminPartnerDetailView error: {e}")
            return Response({"message": "Failed to load partner"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class AdminPartnerDocumentVerifyView(APIView):
    def patch(self, request, partner_id: int, document_type: str):
        try:
            allowed = {"license", "rc_book", "aadhar", "bank_book"}
            doc_type = (document_type or "").strip().lower()
            if doc_type not in allowed:
                return Response({"message": "Invalid document_type"}, status=status.HTTP_400_BAD_REQUEST)

            is_verified_val = request.data.get('is_verified')
            if is_verified_val is None:
                return Response({"message": "is_verified is required"}, status=status.HTTP_400_BAD_REQUEST)

            truthy = {True, 1, '1', 'true', 'True'}
            is_verified_int = 1 if is_verified_val in truthy else 0

            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT document_url, is_verified, uploaded_at FROM delivery_partner_documents WHERE partner_id=%s AND document_type=%s LIMIT 1",
                    [partner_id, doc_type]
                )
                existing = cursor.fetchone()
                if not existing:
                    return Response({"message": "Document not found"}, status=status.HTTP_404_NOT_FOUND)

                cursor.execute(
                    "UPDATE delivery_partner_documents SET is_verified=%s WHERE partner_id=%s AND document_type=%s",
                    [is_verified_int, partner_id, doc_type]
                )

                cursor.execute(
                    "SELECT document_url, is_verified, uploaded_at FROM delivery_partner_documents WHERE partner_id=%s AND document_type=%s LIMIT 1",
                    [partner_id, doc_type]
                )
                row = cursor.fetchone()

            def _abs_url(path: str) -> str:
                """Build S3 URL for document path."""
                return build_s3_file_url(path)

            document = {
                "partner_id": int(partner_id),
                "document_type": doc_type,
                "document_url": _abs_url(row[0]) if row else None,
                "is_verified": bool(int(row[1])) if row and str(row[1]).isdigit() else bool(row[1]) if row else False,
                "uploaded_at": row[2] if row else None
            }

            return Response({
                "success": True,
                "document": document
            }, status=status.HTTP_200_OK)
        except Exception as e:
            logger.error(f"AdminPartnerDocumentVerifyView error: {e}")
            return Response({"message": "Failed to update document verification"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class AdminPartnerApproveView(APIView):
    def post(self, request, partner_id: int):
        try:
            force = request.data.get('force')
            truthy = {True, 1, '1', 'true', 'True'}
            force_flag = True if force in truthy else False

            required = ["license", "rc_book", "aadhar", "bank_book"]

            with connection.cursor() as cursor:
                # Ensure partner exists
                cursor.execute("SELECT id FROM delivery_partner WHERE id=%s LIMIT 1", [partner_id])
                if not cursor.fetchone():
                    return Response({"message": "Delivery partner not found"}, status=status.HTTP_404_NOT_FOUND)

                # Fetch docs
                cursor.execute(
                    "SELECT document_type, is_verified FROM delivery_partner_documents WHERE partner_id=%s",
                    [partner_id]
                )
                rows = cursor.fetchall()

                present = {r[0] for r in rows}
                verified = {r[0] for r in rows if (str(r[1]).isdigit() and int(r[1]) == 1) or (str(r[1]).lower() in ("true", "1"))}

                missing_docs = [d for d in required if d not in present]
                unverified_docs = [d for d in required if d not in verified]

                if (missing_docs or unverified_docs) and not force_flag:
                    return Response({
                        "message": "All documents must be uploaded and verified before approval",
                        "missing_docs": missing_docs,
                        "unverified_docs": unverified_docs
                    }, status=status.HTTP_400_BAD_REQUEST)

                # Approve partner
                cursor.execute(
                    "UPDATE delivery_partner SET is_verified=1, status='1', is_available=1, updated_at=NOW() WHERE id=%s",
                    [partner_id]
                )
                # Sync application status to approved
                try:
                    cursor.execute("SELECT user_id FROM delivery_partner WHERE id=%s LIMIT 1", [partner_id])
                    row_uid = cursor.fetchone()
                    if row_uid and row_uid[0]:
                        cursor.execute(
                            "UPDATE dp_onboarding_applications SET status='approved', updated_at=NOW() WHERE user_id=%s",
                            [row_uid[0]]
                        )
                except Exception:
                    pass

            return Response({
                "success": True,
                "message": "Partner approved.",
                "partner": {"partner_id": int(partner_id), "status": "1", "is_available": 1, "is_verified": True}
            }, status=status.HTTP_200_OK)
        except Exception as e:
            logger.error(f"AdminPartnerApproveView error: {e}")
            return Response({"message": "Failed to approve partner"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class AdminPartnerRejectView(APIView):
    def post(self, request, partner_id: int):
        try:
            decline_reason = request.data.get('decline_reason', '')
            rejection_reasons = request.data.get('rejection_reasons', [])
            reapply_after_days = request.data.get('reapply_after_days', 3)

            with connection.cursor() as cursor:
                # Get user_id from partner
                cursor.execute("SELECT user_id FROM delivery_partner WHERE id=%s LIMIT 1", [partner_id])
                row = cursor.fetchone()
                if not row or not row[0]:
                    return Response({"message": "Delivery partner not found"}, status=status.HTTP_404_NOT_FOUND)
                
                user_id = row[0]
                
                # Check if application exists
                cursor.execute("SELECT id FROM dp_onboarding_applications WHERE user_id=%s LIMIT 1", [user_id])
                app_row = cursor.fetchone()
                
                if app_row:
                    # Update existing application
                    application_id = app_row[0]
                    reapply_dt = timezone.now() + timedelta(days=reapply_after_days)
                    reapply_after_iso = reapply_dt.isoformat()
                    reapply_after_ts = int(reapply_dt.timestamp())
                    
                    cursor.execute(
                        "UPDATE dp_onboarding_applications SET status='declined', decline_reason=%s, updated_at=NOW() WHERE id=%s",
                        [decline_reason, application_id]
                    )
                    
                    # Update onboarding_data with reapply info
                    cursor.execute("SELECT onboarding_data FROM dp_onboarding_applications WHERE id=%s", [application_id])
                    data_row = cursor.fetchone()
                    existing_data = {}
                    if data_row and data_row[0]:
                        try:
                            data_val = data_row[0]
                            if isinstance(data_val, (bytes, bytearray)):
                                data_val = data_val.decode('utf-8')
                            existing_data = json.loads(data_val) if isinstance(data_val, str) else (data_val or {})
                        except Exception:
                            existing_data = {}
                    
                    existing_data['reapply_after'] = reapply_after_iso
                    existing_data['reapply_after_ts'] = reapply_after_ts
                    existing_data['rejection_reasons'] = rejection_reasons
                    
                    cursor.execute(
                        "UPDATE dp_onboarding_applications SET onboarding_data=%s WHERE id=%s",
                        [json.dumps(existing_data), application_id]
                    )
                else:
                    # Create new application record
                    reapply_dt = timezone.now() + timedelta(days=reapply_after_days)
                    reapply_after_iso = reapply_dt.isoformat()
                    reapply_after_ts = int(reapply_dt.timestamp())
                    
                    onboarding_data = {
                        'reapply_after': reapply_after_iso,
                        'reapply_after_ts': reapply_after_ts,
                        'rejection_reasons': rejection_reasons
                    }
                    
                    cursor.execute(
                        """INSERT INTO dp_onboarding_applications 
                        (user_id, status, decline_reason, onboarding_data, created_at, updated_at)
                        VALUES (%s, 'declined', %s, %s, NOW(), NOW())""",
                        [user_id, decline_reason, json.dumps(onboarding_data)]
                    )

            return Response({
                "success": True,
                "message": "Partner rejected successfully."
            }, status=status.HTTP_200_OK)
        except Exception as e:
            logger.error(f"AdminPartnerRejectView error: {e}")
            return Response({"message": "Failed to reject partner"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class PartnerAvailabilityView(APIView):
    def patch(self, request):
        try:
            is_available = request.data.get('is_available')
            try:
                is_available = int(is_available)
            except Exception:
                return Response({"message": "is_available must be 0 or 1"}, status=status.HTTP_400_BAD_REQUEST)

            # Resolve user_id (prefer auth token if available)
            user_id = request.query_params.get('user_id')
            if not user_id:
                if hasattr(request, 'user') and hasattr(request.user, 'user_id'):
                    user_id = getattr(request.user, 'user_id')
            if not user_id:
                return Response({"message": "user_id is required"}, status=status.HTTP_400_BAD_REQUEST)

            with connection.cursor() as cursor:
                cursor.execute("SELECT id, status FROM delivery_partner WHERE user_id=%s LIMIT 1", [user_id])
                row = cursor.fetchone()
                if not row:
                    return Response({"message": "Delivery partner not found"}, status=status.HTTP_404_NOT_FOUND)
                partner_id, current_status = row

                new_status = current_status  # default to existing

                # ✅ Only update `status` if is_available == 1
                if is_available == 1:
                    if isinstance(current_status, (int, float)) or (isinstance(current_status, str) and current_status.isdigit()):
                        new_status = 1  # Legacy numeric values
                    else:
                        if (current_status or '').lower() != 'on_delivery':
                            new_status = 1

                    # Update both is_available and status
                    cursor.execute(
                        "UPDATE delivery_partner SET is_available=%s, status=%s, updated_at=NOW() WHERE user_id=%s",
                        [is_available, new_status, user_id]
                    )
                else:
                    # ✅ Only update is_available, not status
                    cursor.execute(
                        "UPDATE delivery_partner SET is_available=%s, updated_at=NOW() WHERE user_id=%s",
                        [is_available, user_id]
                    )

                # Log action
                details = json.dumps({"is_available": is_available})
                cursor.execute(
                    """
                    INSERT INTO dp_action_logs (actor_user_id, target_partner_id, action_type, details, created_at)
                    VALUES (%s, %s, 'UPDATE_AVAILABILITY', %s, NOW())
                    """,
                    [user_id, partner_id, details]
                )

            return Response({
                "success": True,
                "message": "Availability updated successfully.",
                "current_status": new_status,
                "is_available": is_available
            }, status=status.HTTP_200_OK)

        except Exception as e:
            logger.error(f"PartnerAvailabilityView error: {e}")
            return Response({"message": "Failed to update availability"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class DeliveryPartnerDocumentUploadView(APIView):
    def post(self, request):
        try:
            partner_id = request.query_params.get('partner_id')
            user_id = request.query_params.get('user_id')
            if not partner_id and not user_id:
                return Response({"message": "partner_id or user_id is required"}, status=status.HTTP_400_BAD_REQUEST)

            # Resolve partner_id from user_id if needed
            if not partner_id and user_id:
                with connection.cursor() as cursor:
                    cursor.execute("SELECT id FROM delivery_partner WHERE user_id=%s LIMIT 1", [user_id])
                    row = cursor.fetchone()
                    if not row:
                        return Response({"message": "Delivery partner not found for given user_id"}, status=status.HTTP_404_NOT_FOUND)
                    partner_id = row[0]

            # Enforce cooldown if declined
            try:
                # Resolve user_id if missing but partner_id is present
                _uid_for_check = user_id
                if not _uid_for_check and partner_id:
                    with connection.cursor() as c0:
                        c0.execute("SELECT user_id FROM delivery_partner WHERE id=%s LIMIT 1", [partner_id])
                        r0 = c0.fetchone()
                        _uid_for_check = r0[0] if r0 else None
                if _uid_for_check:
                    with connection.cursor() as c0:
                        c0.execute("SELECT status, decline_reason, onboarding_data FROM dp_onboarding_applications WHERE user_id=%s ORDER BY id DESC LIMIT 1", [_uid_for_check])
                        ar = c0.fetchone()
                    if ar and str(ar[0]).lower() == 'declined':
                        data = ar[2]
                        try:
                            if isinstance(data, (bytes, bytearray)):
                                data = data.decode('utf-8')
                            data = json.loads(data) if isinstance(data, str) else (data or {})
                        except Exception:
                            data = {}
                        now_ts = int(timezone.now().timestamp())
                        reapply_ts = None
                        if isinstance(data.get('reapply_after_ts'), (int, float, str)):
                            try:
                                reapply_ts = int(data.get('reapply_after_ts'))
                            except Exception:
                                reapply_ts = None
                        if reapply_ts is None and data.get('reapply_after'):
                            try:
                                dtv = datetime.fromisoformat(str(data.get('reapply_after')))
                                if timezone.is_naive(dtv):
                                    from django.utils import timezone as dj_tz
                                    dtv = dj_tz.make_aware(dtv)
                                reapply_ts = int(dtv.timestamp())
                            except Exception:
                                reapply_ts = None
                        if reapply_ts is not None and now_ts < reapply_ts:
                            return Response({
                                "success": False,
                                "message": "Application was declined. You can re-apply after the cooldown ends.",
                                "verification_status": "rejected",
                                "decision_reason": ar[1],
                                "reapply_after": data.get('reapply_after')
                            }, status=status.HTTP_400_BAD_REQUEST)
            except Exception:
                pass

            serializer = DeliveryPartnerDocumentUploadSerializer(data=request.data)
            if not serializer.is_valid():
                return Response({"message": "validation failed", "errors": serializer.errors}, status=status.HTTP_400_BAD_REQUEST)

            doc_type = serializer.validated_data['document_type']
            file_obj = serializer.validated_data['file']

            # Save file under media/delivery_partner_docs/<partner_id>/
            timestamp = timezone.now().strftime('%Y%m%d%H%M%S')
            _, ext = os.path.splitext(file_obj.name)
            filename = f"DP_{partner_id}_{doc_type}_{timestamp}{ext or ''}"
            rel_dir = os.path.join('media', 'delivery_partner_docs', str(partner_id))
            abs_dir = os.path.join(settings.BASE_DIR, rel_dir)
            os.makedirs(abs_dir, exist_ok=True)
            abs_path = os.path.join(abs_dir, filename)

            with open(abs_path, 'wb+') as destination:
                for chunk in file_obj.chunks():
                    destination.write(chunk)

            rel_path = os.path.join(rel_dir, filename).replace('\\', '/')

            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO delivery_partner_documents (partner_id, document_type, document_url, is_verified, uploaded_at)
                    VALUES (%s, %s, %s, 0, NOW())
                    ON DUPLICATE KEY UPDATE document_url=VALUES(document_url), is_verified=VALUES(is_verified), uploaded_at=NOW()
                    """,
                    [partner_id, doc_type, rel_path]
                )

            # Reset application status to in_progress when documents are re-uploaded and clear decline_reason if needed
            try:
                # resolve user_id if not given
                if not user_id and partner_id:
                    with connection.cursor() as c2:
                        c2.execute("SELECT user_id FROM delivery_partner WHERE id=%s LIMIT 1", [partner_id])
                        r = c2.fetchone()
                        user_id = r[0] if r else None
                if user_id:
                    with connection.cursor() as c2:
                        c2.execute("SELECT id, onboarding_data, status FROM dp_onboarding_applications WHERE user_id=%s ORDER BY id DESC LIMIT 1", [user_id])
                        ap = c2.fetchone()
                        payload = { 'last_doc_uploaded': doc_type, 'last_resubmitted_at': timezone.now().isoformat() }
                        if ap:
                            existing = ap[1]
                            try:
                                if isinstance(existing, (bytes, bytearray)):
                                    existing = existing.decode('utf-8')
                                existing = json.loads(existing) if isinstance(existing, str) else (existing or {})
                            except Exception:
                                existing = {}
                            # Clear past required_changes and reapply metadata on resubmission
                            try:
                                for _k in ['required_changes', 'reapply_after', 'reapply_after_ts']:
                                    if _k in existing:
                                        existing.pop(_k, None)
                            except Exception:
                                pass
                            # Clear past required_changes and reapply metadata on resubmission
                            try:
                                for _k in ['required_changes', 'reapply_after', 'reapply_after_ts']:
                                    if _k in existing:
                                        existing.pop(_k, None)
                            except Exception:
                                pass
                            existing.update(payload)
                            new_json = json.dumps(existing)
                            new_status = 'in_progress' if str(ap[2]).lower() != 'approved' else str(ap[2]).lower()
                            if str(ap[2]).lower() == 'declined':
                                c2.execute(
                                    "UPDATE dp_onboarding_applications SET status=%s, decline_reason=NULL, onboarding_data=%s, updated_at=NOW() WHERE id=%s",
                                    [new_status, new_json, ap[0]]
                                )
                            else:
                                c2.execute(
                                    "UPDATE dp_onboarding_applications SET status=%s, onboarding_data=%s, updated_at=NOW() WHERE id=%s",
                                    [new_status, new_json, ap[0]]
                                )
                        else:
                            c2.execute(
                                "INSERT INTO dp_onboarding_applications (user_id, status, onboarding_data, created_at, updated_at) VALUES (%s, %s, %s, NOW(), NOW())",
                                [user_id, 'in_progress', json.dumps(payload)]
                            )
            except Exception:
                pass

            absolute_url = build_s3_file_url(rel_path)
            return Response({
                "success": True,
                "message": "Document uploaded",
                "document": {
                    "partner_id": int(partner_id),
                    "document_type": doc_type,
                    "document_url": absolute_url
                }
            }, status=status.HTTP_200_OK)

        except Exception as e:
            logger.error(f"DeliveryPartnerDocumentUploadView error: {e}")
            return Response({"message": "Failed to upload document"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class DeliveryPartnerFinancialsUpsertView(APIView):
    def post(self, request):
        try:
            partner_id = request.query_params.get('partner_id')
            user_id = request.query_params.get('user_id')
            if not partner_id and not user_id:
                return Response({"message": "partner_id or user_id is required"}, status=status.HTTP_400_BAD_REQUEST)

            # Resolve partner_id from user_id if needed
            if not partner_id and user_id:
                with connection.cursor() as cursor:
                    cursor.execute("SELECT id FROM delivery_partner WHERE user_id=%s LIMIT 1", [user_id])
                    row = cursor.fetchone()
                    if not row:
                        return Response({"message": "Delivery partner not found for given user_id"}, status=status.HTTP_404_NOT_FOUND)
                    partner_id = row[0]

            # Enforce cooldown if declined
            try:
                _uid_for_check = user_id
                if not _uid_for_check and partner_id:
                    with connection.cursor() as c0:
                        c0.execute("SELECT user_id FROM delivery_partner WHERE id=%s LIMIT 1", [partner_id])
                        r0 = c0.fetchone()
                        _uid_for_check = r0[0] if r0 else None
                if _uid_for_check:
                    with connection.cursor() as c0:
                        c0.execute("SELECT status, decline_reason, onboarding_data FROM dp_onboarding_applications WHERE user_id=%s ORDER BY id DESC LIMIT 1", [_uid_for_check])
                        ar = c0.fetchone()
                    if ar and str(ar[0]).lower() == 'declined':
                        data = ar[2]
                        try:
                            if isinstance(data, (bytes, bytearray)):
                                data = data.decode('utf-8')
                            data = json.loads(data) if isinstance(data, str) else (data or {})
                        except Exception:
                            data = {}
                        now_ts = int(timezone.now().timestamp())
                        reapply_ts = None
                        if isinstance(data.get('reapply_after_ts'), (int, float, str)):
                            try:
                                reapply_ts = int(data.get('reapply_after_ts'))
                            except Exception:
                                reapply_ts = None
                        if reapply_ts is None and data.get('reapply_after'):
                            try:
                                dtv = datetime.fromisoformat(str(data.get('reapply_after')))
                                if timezone.is_naive(dtv):
                                    from django.utils import timezone as dj_tz
                                    dtv = dj_tz.make_aware(dtv)
                                reapply_ts = int(dtv.timestamp())
                            except Exception:
                                reapply_ts = None
                        if reapply_ts is not None and now_ts < reapply_ts:
                            return Response({
                                "success": False,
                                "message": "Application was declined. You can re-apply after the cooldown ends.",
                                "verification_status": "rejected",
                                "decision_reason": ar[1],
                                "reapply_after": data.get('reapply_after')
                            }, status=status.HTTP_400_BAD_REQUEST)
            except Exception:
                pass

            serializer = DeliveryPartnerFinancialsSerializer(data=request.data)
            if not serializer.is_valid():
                return Response({"message": "validation failed", "errors": serializer.errors}, status=status.HTTP_400_BAD_REQUEST)

            pan = serializer.validated_data['pan_number']
            bank = serializer.validated_data['bank_account_number']
            ifsc = serializer.validated_data['ifsc_code']

            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO delivery_partner_financials (partner_id, pan_number, bank_account_number, ifsc_code, created_at, updated_at)
                    VALUES (%s, %s, %s, %s, NOW(), NOW())
                    ON DUPLICATE KEY UPDATE pan_number=VALUES(pan_number), bank_account_number=VALUES(bank_account_number), ifsc_code=VALUES(ifsc_code), updated_at=NOW()
                    """,
                    [partner_id, pan, bank, ifsc]
                )

            # Reset application status to in_progress on financials update
            try:
                if not user_id and partner_id:
                    with connection.cursor() as c2:
                        c2.execute("SELECT user_id FROM delivery_partner WHERE id=%s LIMIT 1", [partner_id])
                        r = c2.fetchone()
                        user_id = r[0] if r else None
                if user_id:
                    payload = { 'pan_number': pan, 'bank_account_number': bank, 'ifsc_code': ifsc, 'last_resubmitted_at': timezone.now().isoformat() }
                    with connection.cursor() as c2:
                        c2.execute("SELECT id, onboarding_data, status FROM dp_onboarding_applications WHERE user_id=%s ORDER BY id DESC LIMIT 1", [user_id])
                        ap = c2.fetchone()
                        if ap:
                            existing = ap[1]
                            try:
                                if isinstance(existing, (bytes, bytearray)):
                                    existing = existing.decode('utf-8')
                                existing = json.loads(existing) if isinstance(existing, str) else (existing or {})
                            except Exception:
                                existing = {}
                            existing.update(payload)
                            new_json = json.dumps(existing)
                            new_status = 'in_progress' if str(ap[2]).lower() != 'approved' else str(ap[2]).lower()
                            if str(ap[2]).lower() == 'declined':
                                c2.execute(
                                    "UPDATE dp_onboarding_applications SET status=%s, decline_reason=NULL, onboarding_data=%s, updated_at=NOW() WHERE id=%s",
                                    [new_status, new_json, ap[0]]
                                )
                            else:
                                c2.execute(
                                    "UPDATE dp_onboarding_applications SET status=%s, onboarding_data=%s, updated_at=NOW() WHERE id=%s",
                                    [new_status, new_json, ap[0]]
                                )
                        else:
                            c2.execute(
                                "INSERT INTO dp_onboarding_applications (user_id, status, onboarding_data, created_at, updated_at) VALUES (%s, %s, %s, NOW(), NOW())",
                                [user_id, 'in_progress', json.dumps(payload)]
                            )
            except Exception:
                pass

            return Response({
                "success": True,
                "message": "Financials updated",
                "financials": {
                    "partner_id": int(partner_id),
                    "pan_number": pan,
                    "bank_account_number": bank,
                    "ifsc_code": ifsc
                }
            }, status=status.HTTP_200_OK)

        except Exception as e:
            logger.error(f"DeliveryPartnerFinancialsUpsertView error: {e}")
            return Response({"message": "Failed to update financials"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class BasicDeliveryPartnerSignupView(APIView):
    def post(self, request):
        try:
            serializer = BasicDeliveryPartnerSignupSerializer(data=request.data)
            if not serializer.is_valid():
                return Response({"message": "validation failed", "errors": serializer.errors}, status=status.HTTP_400_BAD_REQUEST)

            firstName = serializer.validated_data.get('firstName', '')
            lastName = serializer.validated_data.get('lastName', '')
            countryCode = serializer.validated_data.get('countryCode', '+91')
            mobileNumber = serializer.validated_data['mobileNumber']
            emailID = serializer.validated_data['emailID']
            phone_number = serializer.validated_data.get('phone_number') or mobileNumber

            vehicle_type = serializer.validated_data['vehicle_type']
            vehicle_number = serializer.validated_data['vehicle_number']
            license_number = serializer.validated_data.get('license_number')
            full_address = serializer.validated_data.get('full_address', '')
            city = serializer.validated_data.get('city', '')
            state = serializer.validated_data.get('state', '')
            pincode = serializer.validated_data.get('pincode', '')
            delivery_service_area = serializer.validated_data.get('delivery_service_area', '')
            business_id = serializer.validated_data.get('business_id')
            latitude = serializer.validated_data.get('latitude', 0.0) or 0.0
            longitude = serializer.validated_data.get('longitude', 0.0) or 0.0

            with transaction.atomic():
                with connection.cursor() as cursor:
                    cursor.execute("SELECT user_id FROM registrations WHERE mobileNumber=%s OR emailID=%s LIMIT 1", [mobileNumber, emailID])
                    existing = cursor.fetchone()
                    if existing:
                        return Response({"message": "User already exists", "user_id": int(existing[0])}, status=status.HTTP_409_CONFLICT)

                new_user_id = generate_user_id()
                reg = Registration.objects.create(
                    user_id=new_user_id,
                    firstName=firstName or "",
                    lastName=lastName or "",
                    countryCode=countryCode or "+91",
                    mobileNumber=mobileNumber,
                    emailID=emailID,
                    is_verified=False,
                    is_active=True,
                    user_mode='delivery_partner',
                    whichapp='Kirazee'
                )

                with connection.cursor() as cursor:
                    cursor.execute(
                        """
                        INSERT INTO delivery_partner 
                        (user_id, business_id, vehicle_type, vehicle_number, license_number, latitude, longitude, 
                         status, is_available, rating, total_deliveries, phone_number, full_address, city, state, pincode, delivery_service_area, is_verified, created_at, updated_at)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, '1', 0, 0.0, 0, %s, %s, %s, %s, %s, %s, 0, NOW(), NOW())
                        """,
                        [new_user_id, business_id, vehicle_type, vehicle_number, license_number, latitude, longitude, phone_number, full_address, city, state, pincode, delivery_service_area]
                    )

                    cursor.execute("SELECT id FROM delivery_partner WHERE user_id=%s LIMIT 1", [new_user_id])
                    dp_row = cursor.fetchone()
                    partner_id = dp_row[0] if dp_row else None

            return Response({
                "success": True,
                "message": "Delivery partner registered",
                "user_id": int(new_user_id),
                "partner_id": int(partner_id) if partner_id is not None else None
            }, status=status.HTTP_201_CREATED)

        except Exception as e:
            logger.error(f"BasicDeliveryPartnerSignupView error: {e}")
            return Response({"message": "Failed to register delivery partner"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)