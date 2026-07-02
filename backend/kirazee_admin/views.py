from django.shortcuts import render
from django.http import JsonResponse
from django.db import connection
from django.db import models
from django.utils import timezone
from rest_framework.views import APIView
from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework import status
from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.utils.html import strip_tags
from django.conf import settings
import json
import logging
import math
from .models import BusinessContactUs, BusinessProfile, BusinessCompliance, BusinessAlert, BusinessPerformanceMetrics, BusinessOwnerDetails
from kirazee_app.models import Business, Registration
from datetime import date, timedelta
from decimal import Decimal

logger = logging.getLogger(__name__)
# Global defaults to avoid NameError in UNION queries across mixed collations
# Keep lowercase names to match usage inside f-strings
pair_charset = 'utf8'
pair_collation = 'utf8_general_ci'

def calculate_distance(lat1, lon1, lat2, lon2):
    """
    Calculate the great circle distance between two points 
    on the earth (specified in decimal degrees) using Haversine formula
    Returns distance in kilometers
    """
    if not all([lat1, lon1, lat2, lon2]):
        return 0.0
    
    # Convert decimal degrees to radians
    lat1, lon1, lat2, lon2 = map(math.radians, [lat1, lon1, lat2, lon2])
    
    # Haversine formula
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = math.sin(dlat/2)**2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon/2)**2
    c = 2 * math.asin(math.sqrt(a))
    
    # Radius of earth in kilometers
    r = 6371
    
    return c * r

# ============================================================================
# ADMIN BUSINESS MANAGEMENT SERVICE
# =========================================================================

class AdminBusinessManagementView(APIView):
    """
    Admin service for managing all businesses on the platform
    GET /api/v1/admin/businesses - List all businesses with pagination and filtering
    """
    permission_classes = []  # Remove authentication requirement
    
    def get(self, request):
        """Retrieve all businesses with filtering and pagination"""
        try:
            # Get query parameters
            page = int(request.query_params.get('page', 1))
            limit = min(int(request.query_params.get('limit', 20)), 100)
            offset = (page - 1) * limit
            
            status_filter = request.query_params.get('status')
            business_type_filter = request.query_params.get('business_type')
            search_query = request.query_params.get('search')
            
            with connection.cursor() as cursor:
                # Determine connection collation/charset for safe JOIN comparisons
                detected_collation = 'utf8_general_ci'
                detected_charset = 'utf8'
                try:
                    cursor.execute("SELECT @@collation_connection")
                    row = cursor.fetchone()
                    if row and isinstance(row[0], str):
                        val = row[0]
                        if val.lower().startswith(('utf8', 'utf8mb4')):
                            detected_collation = val
                            detected_charset = 'utf8mb4' if val.lower().startswith('utf8mb4') else 'utf8'
                except Exception:
                    pass

                # Build the main query
                base_query = f"""
                    SELECT 
                        b.business_id,
                        b.level,
                        b.master,
                        b.businessName,
                        b.businessType,
                        bt.type as business_type_name,
                        b.businessCategory,
                        b.businessEmail,
                        b.businessNumber,
                        b.businessWhatsapp,
                        b.description,
                        b.logo,
                        b.banner,
                        b.business_licence,
                        b.business_features,
                        b.business_hours,
                        b.gst_num,
                        b.currency,
                        b.location,
                        b.address,
                        b.landmark,
                        b.city,
                        b.state,
                        b.pincode,
                        b.contact_support,
                        b.contact_mobile,
                        b.website_url,
                        CASE WHEN b.is_verified = 1 THEN 'Verified' ELSE 'Not Verified' END as verification_status,
                        CASE WHEN b.status = 1 THEN 'Active' ELSE 'Inactive' END as status,
                        CASE WHEN b.paymentstatus = 1 THEN 'Paid' ELSE 'Pending' END as payment_status,
                        b.latitude,
                        b.longitude,
                        b.created_at,
                        b.updated_at,
                        -- Owner Details
                        r.firstName as owner_first_name,
                        r.lastName as owner_last_name,
                        r.displayName as owner_display_name,
                        r.mobileNumber as owner_mobile,
                        r.emailID as owner_email,
                        r.dob as owner_dob,
                        r.user_mode,
                        r.profileUrl as owner_profile_url,
                        bod.pan as owner_pan,
                        bod.aadhaar as owner_aadhaar,
                        bod.per_mobile_number as owner_personal_mobile,
                        -- Financial Details
                        bf.owner_pan as business_owner_pan,
                        bf.gstin,
                        bf.ifsc_code,
                        bf.account_number,
                        bf.razor_pay_key_id,
                        bf.fssai_certification_number,
                        -- Business Statistics
                        COALESCE(order_stats.total_orders, 0) as total_orders,
                        COALESCE(order_stats.total_revenue, 0) as total_revenue,
                        COALESCE(order_stats.completed_orders, 0) as completed_orders,
                        COALESCE(order_stats.cancelled_orders, 0) as cancelled_orders,
                        COALESCE(payment_stats.total_payments, 0) as total_payments_received,
                        COALESCE(payment_stats.successful_payments, 0) as successful_payments
                    FROM businesses b
                    LEFT JOIN business_types bt ON CONVERT(b.businessType USING {detected_charset}) COLLATE {detected_collation} = CONVERT(bt.code USING {detected_charset}) COLLATE {detected_collation}
                    LEFT JOIN business_mapping bm ON CONVERT(b.business_id USING {detected_charset}) COLLATE {detected_collation} = CONVERT(bm.business_id USING {detected_charset}) COLLATE {detected_collation}
                    LEFT JOIN registrations r ON bm.user_id = r.user_id
                    LEFT JOIN business_owner_details bod ON bm.user_id = bod.user_id
                    LEFT JOIN business_financials bf ON CONVERT(b.business_id USING {detected_charset}) COLLATE {detected_collation} = CONVERT(bf.business_id USING {detected_charset}) COLLATE {detected_collation}
                    LEFT JOIN (
                        SELECT 
                            business_id,
                            COUNT(*) as total_orders,
                            SUM(total_amount) as total_revenue,
                            SUM(CASE WHEN status IN ('delivered', 'completed') THEN 1 ELSE 0 END) as completed_orders,
                            SUM(CASE WHEN status = 'cancelled' THEN 1 ELSE 0 END) as cancelled_orders
                        FROM orders 
                        GROUP BY business_id
                    ) order_stats ON CONVERT(b.business_id USING {detected_charset}) COLLATE {detected_collation} = CONVERT(order_stats.business_id USING {detected_charset}) COLLATE {detected_collation}
                    LEFT JOIN (
                        SELECT 
                            business_id,
                            COUNT(*) as total_payments,
                            SUM(CASE WHEN status = 'success' THEN 1 ELSE 0 END) as successful_payments
                        FROM business_payments
                        GROUP BY business_id
                    ) payment_stats ON CONVERT(b.business_id USING {detected_charset}) COLLATE {detected_collation} = CONVERT(payment_stats.business_id USING {detected_charset}) COLLATE {detected_collation}
                    WHERE 1=1
                """
                
                # Build filter conditions
                params = []
                
                if status_filter:
                    if status_filter.lower() == 'active':
                        base_query += " AND b.status = 1"
                    elif status_filter.lower() == 'inactive':
                        base_query += " AND b.status = 0"
                
                if business_type_filter:
                    base_query += " AND b.businessType = %s"
                    params.append(business_type_filter)
                
                if search_query:
                    base_query += " AND b.businessName LIKE %s"
                    params.append(f"%{search_query}%")
                
                # Get total count - simplified to avoid complex subquery issues
                count_query = "SELECT COUNT(*) FROM businesses b WHERE 1=1"
                count_params = []
                
                if status_filter:
                    if status_filter.lower() == 'active':
                        count_query += " AND b.status = 1"
                    elif status_filter.lower() == 'inactive':
                        count_query += " AND b.status = 0"
                
                if business_type_filter:
                    count_query += " AND b.businessType = %s"
                    count_params.append(business_type_filter)
                
                if search_query:
                    count_query += " AND b.businessName LIKE %s"
                    count_params.append(f"%{search_query}%")
                
                cursor.execute(count_query, count_params)
                total_businesses = cursor.fetchone()[0]
                
                # Add pagination
                base_query += " ORDER BY b.created_at DESC LIMIT %s OFFSET %s"
                params.extend([limit, offset])
                
                cursor.execute(base_query, params)
                businesses = cursor.fetchall()
                
                # Format response
                business_list = []
                for row in businesses:
                    business_list.append({
                        # Basic Business Information
                        'business_id': row[0],
                        'level': row[1],
                        'master': row[2],
                        'businessName': row[3],
                        'businessType': row[4],
                        'business_type_name': row[5],
                        'businessCategory': row[6],
                        'businessEmail': row[7],
                        'businessNumber': row[8],
                        'businessWhatsapp': row[9],
                        'description': row[10],
                        'logo': row[11],
                        'banner': row[12],
                        'business_licence': row[13],
                        'business_features': row[14],
                        'business_hours': row[15],
                        'gst_num': row[16],
                        'currency': row[17],
                        'location': row[18],
                        'address': row[19],
                        'landmark': row[20],
                        'city': row[21],
                        'state': row[22],
                        'pincode': row[23],
                        'contact_support': row[24],
                        'contact_mobile': row[25],
                        'website_url': row[26],
                        'verification_status': row[27],
                        'status': row[28],
                        'payment_status': row[29],
                        'latitude': float(row[30]) if row[30] else None,
                        'longitude': float(row[31]) if row[31] else None,
                        'created_at': row[32],
                        'updated_at': row[33],
                        
                        # Owner Information with KYC Details
                        'owner_details': {
                            'first_name': row[34],
                            'last_name': row[35],
                            'display_name': row[36],
                            'mobile': row[37],
                            'email': row[38],
                            'date_of_birth': row[39],
                            'user_mode': row[40],
                            'profile_url': row[41],
                            'pan': row[42],
                            'aadhaar': row[43],
                            'personal_mobile': row[44],
                            # KYC fields - default to 'pending' since extended table doesn't exist yet
                            'kyc_status': 'pending',
                            'pan_number': row[42],  # Use existing pan field
                            'pan_status': 'pending' if row[42] else 'incomplete',
                            'bank_name': None,
                            'account_number': row[49] if len(row) > 49 else None,  # From business_financials
                            'ifsc_code': row[48] if len(row) > 48 else None,  # From business_financials
                            'bank_status': 'pending' if (len(row) > 49 and row[49]) else 'incomplete',
                            'kyc_completed_at': None,
                            'kyc_verified_by': None,
                            'owner_name': f"{row[34] or ''} {row[35] or ''}".strip() or 'N/A',
                            'owner_email': row[38],
                            'owner_phone': row[37]
                        },
                        
                        # Financial Information
                        'financial_details': {
                            'business_owner_pan': row[45],
                            'gstin': row[46],
                            'ifsc_code': row[47],
                            'account_number': row[48],
                            'razor_pay_key_id': row[49],
                            'fssai_certification_number': row[50]
                        },
                        
                        # Business Analytics
                        'analytics': {
                            'total_orders': row[51],
                            'total_revenue': float(row[52]) if row[52] else 0.0,
                            'completed_orders': row[53],
                            'cancelled_orders': row[54],
                            'total_payments_received': row[55],
                            'successful_payments': row[56],
                            'completion_rate': round((row[53] / row[51] * 100) if row[51] > 0 else 0, 2),
                            'cancellation_rate': round((row[54] / row[51] * 100) if row[51] > 0 else 0, 2),
                            'payment_success_rate': round((row[56] / row[55] * 100) if row[55] > 0 else 0, 2)
                        }
                    })
                
                # Calculate pagination metadata
                total_pages = (total_businesses + limit - 1) // limit
                
                return Response({
                    'success': True,
                    'message': 'Business data retrieved successfully',
                    'pagination': {
                        'total_businesses': total_businesses,
                        'current_page': page,
                        'per_page': limit,
                        'total_pages': total_pages,
                        'has_next_page': page < total_pages,
                        'has_prev_page': page > 1
                    },
                    'businesses': business_list
                }, status=status.HTTP_200_OK)
                
        except Exception as e:
            logger.error(f"Error retrieving businesses: {str(e)}")
            return Response({
                'success': False,
                'message': f'Error retrieving businesses: {str(e)}'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class AdminBusinessStatusView(APIView):
    """Update business operational status"""
    permission_classes = []  # Remove authentication requirement
    
    def patch(self, request, business_id):
        try:
            data = json.loads(request.body)
            raw_status = data.get('new_status') or data.get('status') or data.get('action')

            # Normalize and map to status codes: 1=Active, 0=Inactive, 2=Deactivated
            status_value = None
            status_label = None
            val = raw_status
            if isinstance(val, str):
                s = val.strip().lower()
                if s in ['activate', 'active', '1', 'true', 'yes', 'on']:
                    status_value = 1
                    status_label = 'Active'
                elif s in ['deactivate', 'deactivated', '2']:
                    status_value = 2
                    status_label = 'Deactivated'
                elif s in ['inactive', '0', 'false', 'off']:
                    status_value = 0
                    status_label = 'Inactive'
            elif isinstance(val, (int, bool)):
                if val == 1 or val is True:
                    status_value = 1
                    status_label = 'Active'
                elif val == 2:
                    status_value = 2
                    status_label = 'Deactivated'
                elif val == 0 or val is False:
                    status_value = 0
                    status_label = 'Inactive'

            if status_value is None:
                return Response({
                    'success': False,
                    'message': 'Invalid status. Use one of: Activate, Deactivate, Active, Inactive, 1, 0, 2'
                }, status=status.HTTP_400_BAD_REQUEST)
            
            with connection.cursor() as cursor:
                cursor.execute("SELECT business_id, businessName FROM businesses WHERE business_id = %s", [business_id])
                business = cursor.fetchone()
                
                if not business:
                    return Response({
                        'success': False,
                        'message': 'Business not found'
                    }, status=status.HTTP_404_NOT_FOUND)
                
                cursor.execute("""
                    UPDATE businesses 
                    SET status = %s, updated_at = NOW() 
                    WHERE business_id = %s
                """, [status_value, business_id])
                
                return Response({
                    'success': True,
                    'message': 'Business status updated successfully',
                    'business_id': business_id,
                    'business_name': business[1],
                    'current_status': status_label,
                    'current_status_code': status_value
                }, status=status.HTTP_200_OK)
                
        except Exception as e:
            logger.error(f"Error updating business status: {str(e)}")
            return Response({
                'success': False,
                'message': f'Error updating business status: {str(e)}'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class AdminBusinessPaymentStatusView(APIView):
    """Update business payment status"""
    permission_classes = []  # Remove authentication requirement
    
    def patch(self, request, business_id):
        try:
            data = json.loads(request.body)
            new_payment_status = data.get('new_payment_status')
            
            if new_payment_status not in ['Paid', 'Pending']:
                return Response({
                    'success': False,
                    'message': 'Invalid payment status. Must be "Paid" or "Pending"'
                }, status=status.HTTP_400_BAD_REQUEST)
            
            # Convert to boolean for database
            payment_status_value = 1 if new_payment_status == 'Paid' else 0
            
            with connection.cursor() as cursor:
                cursor.execute("SELECT business_id, businessName FROM businesses WHERE business_id = %s", [business_id])
                business = cursor.fetchone()
                
                if not business:
                    return Response({
                        'success': False,
                        'message': 'Business not found'
                    }, status=status.HTTP_404_NOT_FOUND)
                
                cursor.execute("""
                    UPDATE businesses 
                    SET paymentstatus = %s, updated_at = NOW() 
                    WHERE business_id = %s
                """, [payment_status_value, business_id])
                
                return Response({
                    'success': True,
                    'message': 'Payment status updated successfully',
                    'business_id': business_id,
                    'business_name': business[1],
                    'current_payment_status': new_payment_status
                }, status=status.HTTP_200_OK)
                
        except Exception as e:
            logger.error(f"Error updating payment status: {str(e)}")
            return Response({
                'success': False,
                'message': f'Error updating payment status: {str(e)}'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class AdminBusinessDeleteView(APIView):
    """Soft delete (deactivate) a business"""
    permission_classes = []  # Remove authentication requirement
    
    def delete(self, request, business_id):
        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT business_id, businessName, status FROM businesses WHERE business_id = %s", [business_id])
                business = cursor.fetchone()
                
                if not business:
                    return Response({
                        'success': False,
                        'message': 'Business not found'
                    }, status=status.HTTP_404_NOT_FOUND)
                
                if business[2] == 0:
                    return Response({
                        'success': False,
                        'message': 'Business is already deactivated'
                    }, status=status.HTTP_400_BAD_REQUEST)
                
                cursor.execute("""
                    UPDATE businesses 
                    SET status = 0, updated_at = NOW() 
                    WHERE business_id = %s
                """, [business_id])
                
                return Response({
                    'success': True,
                    'message': 'Business deactivated successfully',
                    'business_id': business_id,
                    'business_name': business[1]
                }, status=status.HTTP_200_OK)
                
        except Exception as e:
            logger.error(f"Error deactivating business: {str(e)}")
            return Response({
                'success': False,
                'message': f'Error deactivating business: {str(e)}'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


# ============================================================================
# ADMIN ORDER MANAGEMENT SERVICE
# ============================================================================

class AdminOrderManagementView(APIView):
    """Admin service for managing all orders across the platform"""
    permission_classes = []  # Remove authentication requirement
    
    def get(self, request):
        """Retrieve all orders with comprehensive filtering"""
        try:
            page = int(request.query_params.get('page', 1))
            limit = min(int(request.query_params.get('limit', 20)), 100)
            offset = (page - 1) * limit
            
            status_filter = request.query_params.get('status')
            order_type_filter = request.query_params.get('order_type')
            business_id_filter = request.query_params.get('business_id')
            payment_status_filter = request.query_params.get('payment_status')
            payment_type_filter = request.query_params.get('payment_type')
            
            with connection.cursor() as cursor:
                # Determine a compatible collation to use in JOIN comparisons and UNION result sets
                # Falls back safely to 'utf8_general_ci' and 'utf8' if detection fails
                detected_collation = 'utf8_general_ci'
                detected_charset = 'utf8'
                try:
                    cursor.execute("SELECT @@collation_connection")
                    row = cursor.fetchone()
                    if row and isinstance(row[0], str):
                        val = row[0]
                        # Allow only expected utf8 family collations to avoid injection
                        if val.lower().startswith(('utf8', 'utf8mb4')):
                            detected_collation = val
                            detected_charset = 'utf8mb4' if val.lower().startswith('utf8mb4') else 'utf8'
                except Exception:
                    pass

                # Pick a target charset/collation for this service (force utf8mb4 with safe fallback)
                target_charset = 'utf8mb4'
                try:
                    cursor.execute("SHOW COLLATION LIKE 'utf8mb4_0900_ai_ci'")
                    target_collation = 'utf8mb4_0900_ai_ci' if cursor.fetchone() else 'utf8mb4_general_ci'
                except Exception:
                    target_collation = 'utf8mb4_general_ci'

                # Choose a safe charset/collation pair to use everywhere in this view
                # Force utf8/utf8_general_ci to avoid 1253 in mixed environments (utf8mb3 vs utf8mb4)
                pair_charset = 'utf8'
                pair_collation = 'utf8_general_ci'

                # Build combined query with separate placeholders for filters and dynamic collation
                # IMPORTANT: Filter by payment status and payment type if provided
                base_query_template = """
                    (SELECT 
                        CAST('standard' AS CHAR CHARACTER SET {CHARSET}) COLLATE {COLL} AS order_system,
                        o.order_id,
                        CONVERT(o.order_number USING {CHARSET}) COLLATE {COLL} AS order_number,
                        CONVERT(o.status USING {CHARSET}) COLLATE {COLL} AS status,
                        CONVERT(o.order_type USING {CHARSET}) COLLATE {COLL} AS order_type,
                        o.total_amount,
                        o.created_at,
                        CONVERT(o.business_id USING {CHARSET}) COLLATE {COLL} AS business_id,
                        CONVERT(b.businessName USING {CHARSET}) COLLATE {COLL} AS businessName,
                        CONVERT(CONCAT(r.firstName, ' ', r.lastName) USING {CHARSET}) COLLATE {COLL} AS customer_name,
                        CONVERT(r.mobileNumber USING {CHARSET}) COLLATE {COLL} AS mobileNumber,
                        CONVERT(dp_reg.displayName USING {CHARSET}) COLLATE {COLL} AS delivery_partner_name,
                        o.user_id,
                        o.final_amount,
                        CONVERT(p.status USING {CHARSET}) COLLATE {COLL} AS payment_status,
                        CONVERT(p.payment_type USING {CHARSET}) COLLATE {COLL} AS payment_type
                    FROM orders o
                    INNER JOIN payments p ON o.order_id = p.order_id {payment_join_condition}
                    LEFT JOIN businesses b ON CONVERT(o.business_id USING {CHARSET}) COLLATE {COLL} = CONVERT(b.business_id USING {CHARSET}) COLLATE {COLL}
                    LEFT JOIN registrations r ON o.user_id = r.user_id
                    LEFT JOIN registrations dp_reg ON o.delivery_partner_id = dp_reg.user_id
                    WHERE 1=1 {standard_filters})
                    UNION ALL
                    (SELECT 
                        CAST('grocery' AS CHAR CHARACTER SET {CHARSET}) COLLATE {COLL} AS order_system,
                        go.order_id,
                        CONVERT(CONCAT('GRO-', go.order_id) USING {CHARSET}) COLLATE {COLL} AS order_number,
                        CONVERT(go.order_status USING {CHARSET}) COLLATE {COLL} AS status,
                        CONVERT(go.order_type USING {CHARSET}) COLLATE {COLL} AS order_type,
                        go.total_amount,
                        go.created_at,
                        CONVERT(go.business_id USING {CHARSET}) COLLATE {COLL} AS business_id,
                        CONVERT(b.businessName USING {CHARSET}) COLLATE {COLL} AS businessName,
                        CONVERT(CONCAT(r.firstName, ' ', r.lastName) USING {CHARSET}) COLLATE {COLL} AS customer_name,
                        CONVERT(r.mobileNumber USING {CHARSET}) COLLATE {COLL} AS mobileNumber,
                        CONVERT(dp_reg.displayName USING {CHARSET}) COLLATE {COLL} AS delivery_partner_name,
                        go.user_id,
                        go.total_amount AS final_amount,
                        CONVERT(p.status USING {CHARSET}) COLLATE {COLL} AS payment_status,
                        CONVERT(p.payment_type USING {CHARSET}) COLLATE {COLL} AS payment_type
                    FROM Groceries_orders go
                    INNER JOIN payments p ON go.order_id = p.order_id {grocery_payment_join_condition}
                    LEFT JOIN businesses b ON CONVERT(go.business_id USING {CHARSET}) COLLATE {COLL} = CONVERT(b.business_id USING {CHARSET}) COLLATE {COLL}
                    LEFT JOIN registrations r ON go.user_id = r.user_id
                    LEFT JOIN Grocery_deliver_details gdd ON go.order_id = gdd.order_id AND gdd.is_active = 1
                    LEFT JOIN registrations dp_reg ON gdd.partner_id = dp_reg.user_id
                    WHERE 1=1 {grocery_filters})
                """

                # Build separate, unambiguous filter strings
                params = []
                standard_filters = ""
                grocery_filters = ""

                # Build payment join conditions based on payment filters
                payment_join_condition = "AND p.status NOT IN ('pending', 'failed')"
                grocery_payment_join_condition = "AND p.status NOT IN ('pending', 'failed')"
                
                if payment_status_filter:
                    payment_join_condition += f" AND CONVERT(p.status USING {target_charset}) COLLATE {target_collation} = (CAST(%s AS CHAR CHARACTER SET {target_charset}) COLLATE {target_collation})"
                    grocery_payment_join_condition += f" AND CONVERT(p.status USING {target_charset}) COLLATE {target_collation} = (CAST(%s AS CHAR CHARACTER SET {target_charset}) COLLATE {target_collation})"
                    params.append(payment_status_filter)
                
                if payment_type_filter:
                    payment_join_condition += f" AND CONVERT(p.payment_type USING {target_charset}) COLLATE {target_collation} = (CAST(%s AS CHAR CHARACTER SET {target_charset}) COLLATE {target_collation})"
                    grocery_payment_join_condition += f" AND CONVERT(p.payment_type USING {target_charset}) COLLATE {target_collation} = (CAST(%s AS CHAR CHARACTER SET {target_charset}) COLLATE {target_collation})"
                    params.append(payment_type_filter)

                if status_filter:
                    standard_filters += f" AND CONVERT(o.status USING {target_charset}) COLLATE {target_collation} = (CAST(%s AS CHAR CHARACTER SET {target_charset}) COLLATE {target_collation})"
                    grocery_filters += f" AND CONVERT(go.order_status USING {target_charset}) COLLATE {target_collation} = (CAST(%s AS CHAR CHARACTER SET {target_charset}) COLLATE {target_collation})"
                    params.append(status_filter)

                if order_type_filter:
                    standard_filters += f" AND CONVERT(o.order_type USING {target_charset}) COLLATE {target_collation} = (CAST(%s AS CHAR CHARACTER SET {target_charset}) COLLATE {target_collation})"
                    grocery_filters += f" AND CONVERT(go.order_type USING {target_charset}) COLLATE {target_collation} = (CAST(%s AS CHAR CHARACTER SET {target_charset}) COLLATE {target_collation})"
                    params.append(order_type_filter)

                if business_id_filter:
                    standard_filters += f" AND CONVERT(o.business_id USING {target_charset}) COLLATE {target_collation} = (CAST(%s AS CHAR CHARACTER SET {target_charset}) COLLATE {target_collation})"
                    grocery_filters += f" AND CONVERT(go.business_id USING {target_charset}) COLLATE {target_collation} = (CAST(%s AS CHAR CHARACTER SET {target_charset}) COLLATE {target_collation})"
                    params.append(business_id_filter)

                # Apply filters and use target utf8mb4 charset/collation across UNION
                final_base_query = base_query_template.format(
                    COLL=target_collation,
                    CHARSET=target_charset,
                    payment_join_condition=payment_join_condition,
                    grocery_payment_join_condition=grocery_payment_join_condition,
                    standard_filters=standard_filters,
                    grocery_filters=grocery_filters
                )
                
                # Wrap in subquery for pagination and ordering
                final_query = f"""
                    SELECT * FROM ({final_base_query}) combined_orders
                    ORDER BY created_at DESC
                    LIMIT %s OFFSET %s
                """
                
                # Build parameter lists per SELECT for clarity
                std_params = []
                if status_filter:
                    std_params.append(status_filter)
                if order_type_filter:
                    std_params.append(order_type_filter)
                if business_id_filter:
                    std_params.append(business_id_filter)
                if payment_status_filter:
                    std_params.append(payment_status_filter)
                if payment_type_filter:
                    std_params.append(payment_type_filter)

                groc_params = []
                if status_filter:
                    groc_params.append(status_filter)
                if order_type_filter:
                    groc_params.append(order_type_filter)
                if business_id_filter:
                    groc_params.append(business_id_filter)
                if payment_status_filter:
                    groc_params.append(payment_status_filter)
                if payment_type_filter:
                    groc_params.append(payment_type_filter)

                # Duplicate params for both UNION parts, then add pagination params
                all_params = std_params + groc_params + [limit, offset]
                
                cursor.execute(final_query, all_params)
                orders = cursor.fetchall()
                
                # Get total count
                count_query = f"SELECT COUNT(*) FROM ({final_base_query}) as count_table"
                cursor.execute(count_query, std_params + groc_params)
                total_orders = cursor.fetchone()[0]

                # Fallback: If UNION produced zero rows but base tables have data, merge separately
                if total_orders == 0:
                    # Compute counts per table with same filters - only count orders with valid payment (not pending or failed)
                    cursor.execute(
                        f"SELECT COUNT(*) FROM orders o INNER JOIN payments p ON o.order_id = p.order_id AND p.status NOT IN ('pending', 'failed') WHERE 1=1{standard_filters}",
                        std_params,
                    )
                    std_count = cursor.fetchone()[0]

                    cursor.execute(
                        f"SELECT COUNT(*) FROM Groceries_orders go INNER JOIN payments p ON go.order_id = p.order_id AND p.status NOT IN ('pending', 'failed') WHERE 1=1{grocery_filters}",
                        groc_params,
                    )
                    groc_count = cursor.fetchone()[0]

                    combined_count = (std_count or 0) + (groc_count or 0)

                    if combined_count > 0:
                        # Fetch more than needed from each side, then merge and paginate in Python
                        fetch_n = limit + offset
                        # Standard orders fetch - only orders with valid payment (not pending or failed)
                        cursor.execute(
                            f"""
                            SELECT 
                                'standard' as order_system, o.order_id, o.order_number, o.status, o.order_type,
                                o.total_amount, o.created_at, o.business_id, b.businessName,
                                CONCAT(r.firstName, ' ', r.lastName) as customer_name,
                                r.mobileNumber, dp_reg.displayName as delivery_partner_name, o.user_id, o.final_amount,
                                p.status as payment_status, p.payment_type as payment_type
                            FROM orders o
                            INNER JOIN payments p ON o.order_id = p.order_id AND p.status NOT IN ('pending', 'failed')
                            LEFT JOIN businesses b ON CONVERT(o.business_id USING {target_charset}) COLLATE {target_collation} = CONVERT(b.business_id USING {target_charset}) COLLATE {target_collation}
                            LEFT JOIN registrations r ON o.user_id = r.user_id
                            LEFT JOIN registrations dp_reg ON o.delivery_partner_id = dp_reg.user_id
                            WHERE 1=1{standard_filters}
                            ORDER BY o.created_at DESC
                            LIMIT %s OFFSET %s
                            """,
                            std_params + [fetch_n, 0],
                        )
                        std_rows = cursor.fetchall()

                        # Grocery orders fetch - only orders with valid payment (not pending or failed)
                        cursor.execute(
                            f"""
                            SELECT 
                                'grocery' as order_system, go.order_id, CONCAT('GRO-', go.order_id) as order_number,
                                go.order_status as status, go.order_type, go.total_amount, go.created_at,
                                go.business_id, b.businessName,
                                CONCAT(r.firstName, ' ', r.lastName) as customer_name,
                                r.mobileNumber, dp_reg.displayName as delivery_partner_name, go.user_id, go.total_amount,
                                p.status as payment_status, p.payment_type as payment_type
                            FROM Groceries_orders go
                            INNER JOIN payments p ON go.order_id = p.order_id AND p.status NOT IN ('pending', 'failed')
                            LEFT JOIN businesses b ON CONVERT(go.business_id USING {target_charset}) COLLATE {target_collation} = CONVERT(b.business_id USING {target_charset}) COLLATE {target_collation}
                            LEFT JOIN registrations r ON go.user_id = r.user_id
                            LEFT JOIN Grocery_deliver_details gdd ON go.order_id = gdd.order_id AND gdd.is_active = 1
                            LEFT JOIN registrations dp_reg ON gdd.partner_id = dp_reg.user_id
                            WHERE 1=1{grocery_filters}
                            ORDER BY go.created_at DESC
                            LIMIT %s OFFSET %s
                            """,
                            groc_params + [fetch_n, 0],
                        )
                        groc_rows = cursor.fetchall()

                        # Merge and paginate in Python
                        all_rows = list(std_rows) + list(groc_rows)
                        all_rows.sort(key=lambda r: r[6], reverse=True)  # index 6 is created_at
                        orders = all_rows[offset: offset + limit]
                        total_orders = combined_count
                
                # Format response
                order_list = []
                for row in orders:
                    order_list.append({
                        'order_system': row[0],
                        'order_id': row[1],
                        'order_number': row[2],
                        'status': row[3],
                        'order_type': row[4],
                        'total_amount': float(row[5]) if row[5] else 0.0,
                        'created_at': row[6],
                        'business_id': row[7],
                        'business_name': row[8],
                        'customer_name': row[9],
                        'customer_phone': row[10],
                        'delivery_partner_name': row[11],
                        'user_id': row[12],
                        'final_amount': float(row[13]) if row[13] else 0.0,
                        'payment_status': row[14],
                        'payment_type': row[15]
                    })
                
                total_pages = (total_orders + limit - 1) // limit
                
                # Build pagination URLs
                request_url = request.build_absolute_uri()
                base_url = request_url.split('?')[0] if '?' in request_url else request_url
                
                # Build query parameters for pagination URLs
                query_params = request.query_params.copy()
                query_params.pop('page', None)  # Remove page parameter for base URL
                
                # Build base query string
                base_query = '&'.join([f"{k}={v}" for k, v in query_params.items()])
                base_query_string = f"?{base_query}" if base_query else ""
                
                # Build next and previous page URLs
                next_page_url = None
                prev_page_url = None
                
                if page < total_pages:
                    next_page_url = f"{base_url}{base_query_string}&page={page + 1}" if base_query_string else f"{base_url}?page={page + 1}"
                
                if page > 1:
                    prev_page_url = f"{base_url}{base_query_string}&page={page - 1}" if base_query_string else f"{base_url}?page={page - 1}"
                
                # Build page range info
                start_item = (page - 1) * limit + 1 if total_orders > 0 else 0
                end_item = min(page * limit, total_orders)
                
                return Response({
                    'success': True,
                    'message': 'Orders retrieved successfully',
                    'pagination': {
                        'total_orders': total_orders,
                        'current_page': page,
                        'per_page': limit,
                        'total_pages': total_pages,
                        'has_next_page': page < total_pages,
                        'has_prev_page': page > 1,
                        'next_page_url': next_page_url,
                        'prev_page_url': prev_page_url,
                        'first_page_url': f"{base_url}{base_query_string}&page=1" if base_query_string else f"{base_url}?page=1",
                        'last_page_url': f"{base_url}{base_query_string}&page={total_pages}" if base_query_string else f"{base_url}?page={total_pages}",
                        'items_on_page': len(order_list),
                        'items_range': f"{start_item}-{end_item}" if total_orders > 0 else "0-0",
                        'showing_from': start_item,
                        'showing_to': end_item,
                        'remaining_items': max(0, total_orders - end_item)
                    },
                    'orders': order_list
                }, status=status.HTTP_200_OK)
                
        except Exception as e:
            logger.error(f"Error retrieving orders: {str(e)}")
            return Response({
                'success': False,
                'message': f'Error retrieving orders: {str(e)}'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class AdminOrderStatusView(APIView):
    """Update order status with admin privileges"""
    permission_classes = []  # Remove authentication requirement
    
    def patch(self, request, order_id):
        try:
            data = json.loads(request.body)
            new_status = data.get('new_status')
            order_system = data.get('order_system', 'standard')
            
            valid_statuses = [
                'pending', 'confirmed', 'preparing', 'ready', 'assigned', 
                'picked_up', 'travelling', 'out_for_delivery', 'delivered', 
                'completed', 'cancelled'
            ]
            
            if new_status not in valid_statuses:
                return Response({
                    'success': False,
                    'message': f'Invalid status. Must be one of: {", ".join(valid_statuses)}'
                }, status=status.HTTP_400_BAD_REQUEST)
            
            with connection.cursor() as cursor:
                if order_system == 'grocery':
                    cursor.execute("""
                        SELECT order_id, order_status, business_id 
                        FROM Groceries_orders 
                        WHERE order_id = %s
                    """, [order_id])
                    
                    order = cursor.fetchone()
                    if not order:
                        return Response({
                            'success': False,
                            'message': 'Grocery order not found'
                        }, status=status.HTTP_404_NOT_FOUND)
                    
                    cursor.execute("""
                        UPDATE Groceries_orders 
                        SET order_status = %s, updated_at = NOW() 
                        WHERE order_id = %s
                    """, [new_status, order_id])
                    
                else:
                    cursor.execute("""
                        SELECT order_id, status, business_id 
                        FROM orders 
                        WHERE order_id = %s
                    """, [order_id])
                    
                    order = cursor.fetchone()
                    if not order:
                        return Response({
                            'success': False,
                            'message': 'Standard order not found'
                        }, status=status.HTTP_404_NOT_FOUND)
                    
                    cursor.execute("""
                        UPDATE orders 
                        SET status = %s, updated_at = NOW() 
                        WHERE order_id = %s
                    """, [new_status, order_id])
                
                return Response({
                    'success': True,
                    'message': 'Order status updated successfully',
                    'order_id': order_id,
                    'order_system': order_system,
                    'previous_status': order[1],
                    'current_status': new_status
                }, status=status.HTTP_200_OK)
                
        except Exception as e:
            logger.error(f"Error updating order status: {str(e)}")
            return Response({
                'success': False,
                'message': f'Error updating order status: {str(e)}'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class AdminOrderDetailsView(APIView):
    """Get detailed order information including items"""
    permission_classes = []  # Remove authentication requirement
    
    def get(self, request, order_id):
        """Retrieve order details with items"""
        try:
            order_system = request.query_params.get('order_system', 'standard')

            # Prepare helpers for media URLs - returns S3 URLs directly
            def to_absolute_url(path: str):
                if not path:
                    return None
                # Strip leading 'media/' if already present to avoid duplication
                if path.startswith('media/'):
                    path = path[6:]
                return f"https://kirazee-bucket.s3.ap-south-1.amazonaws.com/prod/media/{path}" if not path.startswith('http') else path

            # Safe float conversion helper
            def safe_float(value):
                if value is None:
                    return 0.0
                try:
                    # If it's already a number, return it
                    if isinstance(value, (int, float)):
                        return float(value)
                    # If it's a string, check if it's numeric
                    if isinstance(value, str):
                        # Skip JSON strings
                        if value.startswith('{') or value.startswith('['):
                            return 0.0
                        # Try to convert to float
                        return float(value) if value.strip() else 0.0
                    return 0.0
                except (ValueError, TypeError):
                    return 0.0

            with connection.cursor() as cursor:
                if order_system == 'grocery':
                    # Fetch grocery order details
                    cursor.execute("""
                        SELECT 
                            go.order_id, go.order_status as status, go.order_type,
                            go.total_amount, go.created_at, go.business_id,
                            b.businessName, go.user_id,
                            r.firstName, r.lastName, r.mobileNumber, r.emailID,
                            p.status as payment_status, p.payment_type as payment_type,
                            go.delivery_address, go.delivery_instructions, go.order_instructions,
                            go.scheduled_time, go.estimated_delivery_time, go.pickup_time,
                            go.final_amount, go.delivery_charge, go.discount, go.gst_amount,
                            b.businessType, b.address, b.location, b.landmark,
                            b.city, b.state, b.pincode, b.businessNumber,
                            b.contact_mobile, b.contact_support, b.businessWhatsapp,
                            b.latitude, b.longitude, b.business_hours, b.status as business_status,
                            r.profileUrl
                        FROM Groceries_orders go
                        LEFT JOIN businesses b ON go.business_id = b.business_id
                        LEFT JOIN registrations r ON go.user_id = r.user_id
                        LEFT JOIN payments p ON go.order_id = p.order_id
                        WHERE go.order_id = %s
                    """, [order_id])
                    
                    order_row = cursor.fetchone()
                    if not order_row:
                        return Response({
                            'success': False,
                            'message': 'Order not found'
                        }, status=status.HTTP_404_NOT_FOUND)
                    
                    # Create order dictionary similar to reference code
                    order = {
                        'order_id': order_row[0],
                        'status': order_row[1],
                        'order_type': order_row[2],
                        'total_amount': order_row[3],
                        'created_at': order_row[4],
                        'business_id': order_row[5],
                        'business_name': order_row[6],
                        'user_id': order_row[7],
                        'first_name': order_row[8],
                        'last_name': order_row[9],
                        'phone_number': order_row[10],
                        'email': order_row[11],
                        'payment_status': order_row[12],
                        'payment_type': order_row[13],
                        'delivery_address': order_row[14],
                        'delivery_instructions': order_row[15],
                        'order_instructions': order_row[16],
                        'scheduled_time': order_row[17],
                        'estimated_delivery_time': order_row[18],
                        'pickup_time': order_row[19],
                        'final_amount': order_row[20],
                        'delivery_charges': order_row[21],
                        'discount': order_row[22],
                        'gst_amount': order_row[23],
                        'business_type': order_row[24],
                        'business_address': order_row[25],
                        'business_location': order_row[26],
                        'business_landmark': order_row[27],
                        'business_city': order_row[28],
                        'business_state': order_row[29],
                        'business_pincode': order_row[30],
                        'business_phone': order_row[31],
                        'business_contact_mobile': order_row[32],
                        'business_contact_support': order_row[33],
                        'business_whatsapp': order_row[34],
                        'business_latitude': order_row[35],
                        'business_longitude': order_row[36],
                        'business_hours_json': order_row[37],
                        'business_status': order_row[38],
                        'profile_image': order_row[39],
                        'source_table': 'groceries_orders'
                    }
                    
                    # Fetch grocery order items
                    cursor.execute("""
                        SELECT 
                            goi.item_id, goi.product_id, goi.item_name_snapshot as item_name,
                            goi.quantity, goi.unit_price_snapshot as unit_price,
                            goi.total_price, gp.main_image as item_image, goi.customizations,
                            goi.variant_id, goi.gst, goi.gst_amount, goi.item_details_snapshot,
                            gpv.sku, gpv.selling_price as variant_price, gpv.barcode,
                            gpv.net_weight, gpv.net_weight_unit, gpv.size,
                            gpv.original_cost, gpv.charges, gpv.stock,
                            gpv.mfg_date, gpv.expiry_date, gpv.is_active,
                            gpv.created_at as variant_created_at, gpv.updated_at as variant_updated_at,
                            gpv.gst as variant_gst, gpv.color, gpv.gender, gpv.age,
                            gpv.min_age, gpv.max_age, gpv.material, gpv.attributes,
                            gpv.pack, gpv.is_visible_counter, gpv.dimension,
                            gpv.rating as variant_rating, gpv.rating_count,
                            gp.description, gp.brand_name, gp.rating as product_rating,
                            gp.is_organic, gp.sub_category
                        FROM Groceries_order_items goi
                        LEFT JOIN Groceries_products gp ON goi.product_id = gp.product_id
                        LEFT JOIN Groceries_ProductVariants_1 gpv ON goi.variant_id = gpv.variant_id
                        WHERE goi.order_id = %s
                    """, [order_id])

                    items = []
                    for item_row in cursor.fetchall():
                        items.append({
                            'item_id': item_row[0],
                            'product_id': item_row[1],
                            'variant_id': item_row[8],
                            'item_name': item_row[2],
                            'quantity': item_row[3],
                            'unit_price': item_row[4],
                            'total_price': item_row[5],
                            'item_image': item_row[6],
                            'customizations': item_row[7],
                            'gst': item_row[9],
                            'tax_amount': item_row[10],
                            'item_details_snapshot': item_row[11],
                            'sku': item_row[12],
                            'variant_price': item_row[13],
                            'barcode': item_row[14],
                            'net_weight': item_row[15],
                            'net_weight_unit': item_row[16],
                            'size': item_row[17],
                            'original_cost': item_row[18],
                            'charges': item_row[19],
                            'stock': item_row[20],
                            'mfg_date': item_row[21],
                            'expiry_date': item_row[22],
                            'is_active': item_row[23],
                            'variant_created_at': item_row[24],
                            'variant_updated_at': item_row[25],
                            'variant_gst': item_row[26],
                            'color': item_row[27],
                            'gender': item_row[28],
                            'age': item_row[29],
                            'min_age': item_row[30],
                            'max_age': item_row[31],
                            'material': item_row[32],
                            'attributes': item_row[33],
                            'pack': item_row[34],
                            'is_visible_counter': item_row[35],
                            'dimension': item_row[36],
                            'variant_rating': item_row[37],
                            'rating_count': item_row[38],
                            'description': item_row[39],
                            'brand_name': item_row[40],
                            'product_rating': item_row[41],
                            'is_organic': item_row[42],
                            'sub_category': item_row[43]
                        })
                    
                    order['items'] = items
                    
                else:
                    # Fetch standard order details
                    cursor.execute("""
                        SELECT 
                            o.order_id, o.status, o.order_type, o.total_amount,
                            o.created_at, o.business_id, b.businessName, o.user_id,
                            r.firstName, r.lastName, r.mobileNumber, r.emailID,
                            o.final_amount, p.status as payment_status, p.payment_type as payment_type,
                            o.delivery_address_id, o.scheduled_time, o.estimated_delivery_time, o.delivery_partner_id,
                            b.businessType, b.address, b.location, b.landmark,
                            b.city, b.state, b.pincode, b.businessNumber,
                            b.contact_mobile, b.contact_support, b.businessWhatsapp,
                            b.latitude, b.longitude, b.business_hours, b.status as business_status,
                            o.order_number, o.token_num, o.delivery_address_snapshot, o.billing_address_snapshot,
                            o.delivery_instruction, o.order_instruction, o.discount_amount, o.delivery_charges,
                            o.parcel_charges, o.wallet_points_used, o.actual_delivery_time,
                            r.profileUrl
                        FROM orders o
                        LEFT JOIN businesses b ON o.business_id = b.business_id
                        LEFT JOIN registrations r ON o.user_id = r.user_id
                        LEFT JOIN payments p ON o.order_id = p.order_id
                        WHERE o.order_id = %s
                    """, [order_id])
                    
                    order_row = cursor.fetchone()
                    if not order_row:
                        return Response({
                            'success': False,
                            'message': 'Order not found'
                        }, status=status.HTTP_404_NOT_FOUND)
                    
                    # Create order dictionary similar to reference code
                    order = {
                        'order_id': order_row[0],
                        'status': order_row[1],
                        'order_type': order_row[2],
                        'total_amount': order_row[3],
                        'created_at': order_row[4],
                        'business_id': order_row[5],
                        'business_name': order_row[6],
                        'user_id': order_row[7],
                        'first_name': order_row[8],
                        'last_name': order_row[9],
                        'phone_number': order_row[10],
                        'email': order_row[11],
                        'final_amount': order_row[12],
                        'payment_status': order_row[13],
                        'payment_type': order_row[14],
                        'delivery_address_id': order_row[15],
                        'scheduled_time': order_row[16],
                        'estimated_delivery_time': order_row[17],
                        'delivery_partner_id': order_row[18],
                        'business_type': order_row[19],
                        'business_address': order_row[20],
                        'business_location': order_row[21],
                        'business_landmark': order_row[22],
                        'business_city': order_row[23],
                        'business_state': order_row[24],
                        'business_pincode': order_row[25],
                        'business_phone': order_row[26],
                        'business_contact_mobile': order_row[27],
                        'business_contact_support': order_row[28],
                        'business_whatsapp': order_row[29],
                        'business_latitude': order_row[30],
                        'business_longitude': order_row[31],
                        'business_hours_json': order_row[32],
                        'business_status': order_row[33],
                        'order_number': order_row[34],
                        'token_num': order_row[35],
                        'delivery_address_snapshot': order_row[36],
                        'billing_address_snapshot': order_row[37],
                        'delivery_instruction': order_row[38],
                        'order_instruction': order_row[39],
                        'discount_amount': order_row[40],
                        'delivery_charges': order_row[41],
                        'parcel_charges': order_row[42],
                        'wallet_points_used': order_row[43],
                        'actual_delivery_time': order_row[44],
                        'profile_image': order_row[45],
                        'source_table': 'orders'
                    }
                    
                    # Fetch items based on business type
                    items = []
                    business_type = order_row[19]
                    
                    if business_type == 'R01':
                        # Grocery items for standard orders
                        cursor.execute("""
                            SELECT 
                                oi.item_id, oi.product_item_id as product_id, oi.item_name_snapshot as item_name,
                                oi.quantity, oi.unit_price_snapshot as unit_price,
                                oi.total_price, gp.main_image as item_image, oi.customizations,
                                oi.variant_id, oi.gst, oi.gst_amount, oi.item_details_snapshot,
                                gpv.sku, gpv.selling_price as variant_price, gpv.barcode,
                                gpv.net_weight, gpv.net_weight_unit, gpv.size,
                                gpv.original_cost, gpv.charges, gpv.stock,
                                gpv.mfg_date, gpv.expiry_date, gpv.is_active,
                                gpv.created_at as variant_created_at, gpv.updated_at as variant_updated_at,
                                gpv.gst as variant_gst, gpv.color, gpv.gender, gpv.age,
                                gpv.min_age, gpv.max_age, gpv.material, gpv.attributes,
                                gpv.pack, gpv.is_visible_counter, gpv.dimension,
                                gpv.rating as variant_rating, gpv.rating_count,
                                gp.description, gp.brand_name, gp.rating as product_rating,
                                gp.is_organic, gp.sub_category
                            FROM order_items oi
                            LEFT JOIN Groceries_Products gp ON oi.product_item_id = gp.product_id
                            LEFT JOIN Groceries_ProductVariants_1 gpv ON oi.variant_id = gpv.variant_id
                            WHERE oi.order_id = %s
                        """, [order_id])
                        
                        for item_row in cursor.fetchall():
                            items.append({
                                'item_id': item_row[0],
                                'product_id': item_row[1],
                                'variant_id': item_row[8],
                                'item_name': item_row[2],
                                'quantity': item_row[3],
                                'unit_price': item_row[4],
                                'total_price': item_row[5],
                                'item_image': item_row[6],
                                'customizations': item_row[7],
                                'gst': item_row[9],
                                'tax_amount': item_row[10],
                                'item_details_snapshot': item_row[11],
                                'sku': item_row[12],
                                'variant_price': item_row[13],
                                'barcode': item_row[14],
                                'net_weight': item_row[15],
                                'net_weight_unit': item_row[16],
                                'size': item_row[17],
                                'original_cost': item_row[18],
                                'charges': item_row[19],
                                'stock': item_row[20],
                                'mfg_date': item_row[21],
                                'expiry_date': item_row[22],
                                'is_active': item_row[23],
                                'variant_created_at': item_row[24],
                                'variant_updated_at': item_row[25],
                                'variant_gst': item_row[26],
                                'color': item_row[27],
                                'gender': item_row[28],
                                'age': item_row[29],
                                'min_age': item_row[30],
                                'max_age': item_row[31],
                                'material': item_row[32],
                                'attributes': item_row[33],
                                'pack': item_row[34],
                                'is_visible_counter': item_row[35],
                                'dimension': item_row[36],
                                'variant_rating': item_row[37],
                                'rating_count': item_row[38],
                                'description': item_row[39],
                                'brand_name': item_row[40],
                                'product_rating': item_row[41],
                                'is_organic': item_row[42],
                                'sub_category': item_row[43]
                            })
                    
                    elif business_type == 'R02':
                        # Restaurant items
                        cursor.execute("""
                            SELECT 
                                oi.item_id, oi.menu_item_id as item_id_ref, oi.item_name_snapshot as item_name,
                                oi.quantity, oi.unit_price_snapshot as unit_price,
                                oi.total_price, mi.item_image as item_image, oi.customizations,
                                oi.variant_id, oi.gst, oi.gst_amount, oi.item_details_snapshot,
                                miv.sku, miv.selling_price as variant_price, miv.mrp,
                                miv.original_cost, miv.charges, miv.stock_qty,
                                miv.is_active, miv.created_at as variant_created_at, 
                                miv.updated_at as variant_updated_at, miv.gst as variant_gst,
                                miv.rating as variant_rating, miv.rating_count,
                                mi.description, mi.item_category, mi.rating as product_rating
                            FROM order_items oi
                            LEFT JOIN menuItems mi ON oi.menu_item_id = mi.item_id
                            LEFT JOIN menu_item_variants miv ON oi.variant_id = miv.variant_id
                            WHERE oi.order_id = %s
                        """, [order_id])
                        
                        for item_row in cursor.fetchall():
                            items.append({
                                'item_id': item_row[0],
                                'menu_item_id': item_row[1],
                                'item_name': item_row[2],
                                'quantity': item_row[3],
                                'unit_price': item_row[4],
                                'total_price': item_row[5],
                                'item_image': item_row[6],
                                'customizations': item_row[7],
                                'variant_id': item_row[8],
                                'gst': item_row[9],
                                'tax_amount': item_row[10],
                                'item_details_snapshot': item_row[11],
                                'sku': item_row[12],
                                'variant_price': item_row[13],
                                'mrp': item_row[14],
                                'original_cost': item_row[15],
                                'charges': item_row[16],
                                'stock_qty': item_row[17],
                                'is_active': item_row[18],
                                'variant_created_at': item_row[19],
                                'variant_updated_at': item_row[20],
                                'variant_gst': item_row[21],
                                'variant_rating': item_row[22],
                                'rating_count': item_row[23],
                                'description': item_row[24],
                                'item_category': item_row[25],
                                'product_rating': item_row[26]
                            })
                    
                    elif business_type == 'R08':
                        # Fashion items
                        cursor.execute("""
                            SELECT 
                                oi.item_id, oi.product_item_id as product_id, oi.item_name_snapshot as item_name,
                                oi.quantity, oi.unit_price_snapshot as unit_price,
                                oi.total_price, fp.main_image as item_image, oi.customizations,
                                oi.variant_id, oi.gst, oi.gst_amount, oi.item_details_snapshot,
                                fpv.sku, fpv.selling_price as variant_price, fpv.mrp,
                                fpv.original_cost, fpv.charges, fpv.stock,
                                fpv.net_weight, fpv.net_weight_unit, fpv.size,
                                fpv.color, fpv.material, fpv.gender, fpv.min_age, fpv.max_age,
                                fpv.is_active, fpv.created_at as variant_created_at,
                                fpv.updated_at as variant_updated_at, fpv.rating as variant_rating,
                                fpv.rating_count, fp.description, fp.brand_name, fp.rating as product_rating
                            FROM order_items oi
                            LEFT JOIN fashion_products fp ON oi.product_item_id = fp.product_id
                            LEFT JOIN fashion_product_variants fpv ON oi.variant_id = fpv.variant_id
                            WHERE oi.order_id = %s
                        """, [order_id])
                        
                        for item_row in cursor.fetchall():
                            items.append({
                                'item_id': item_row[0],
                                'product_id': item_row[1],
                                'item_name': item_row[2],
                                'quantity': item_row[3],
                                'unit_price': item_row[4],
                                'total_price': item_row[5],
                                'item_image': item_row[6],
                                'customizations': item_row[7],
                                'variant_id': item_row[8],
                                'gst': item_row[9],
                                'tax_amount': item_row[10],
                                'item_details_snapshot': item_row[11],
                                'sku': item_row[12],
                                'variant_price': item_row[13],
                                'mrp': item_row[14],
                                'original_cost': item_row[15],
                                'charges': item_row[16],
                                'stock': item_row[17],
                                'net_weight': item_row[18],
                                'net_weight_unit': item_row[19],
                                'size': item_row[20],
                                'color': item_row[21],
                                'material': item_row[22],
                                'gender': item_row[23],
                                'min_age': item_row[24],
                                'max_age': item_row[25],
                                'is_active': item_row[26],
                                'variant_created_at': item_row[27],
                                'variant_updated_at': item_row[28],
                                'variant_rating': item_row[29],
                                'rating_count': item_row[30],
                                'description': item_row[31],
                                'brand_name': item_row[32],
                                'product_rating': item_row[33]
                            })
                    
                    else:
                        # Default fallback for unknown business types
                        cursor.execute("""
                            SELECT 
                                oi.item_id, oi.menu_item_id, oi.item_name_snapshot as item_name,
                                oi.quantity, oi.unit_price_snapshot as unit_price,
                                oi.total_price, oi.customizations, oi.gst, oi.gst_amount
                            FROM order_items oi
                            WHERE oi.order_id = %s
                        """, [order_id])
                        
                        for item_row in cursor.fetchall():
                            items.append({
                                'item_id': item_row[0],
                                'menu_item_id': item_row[1],
                                'item_name': item_row[2],
                                'quantity': item_row[3],
                                'unit_price': item_row[4],
                                'total_price': item_row[5],
                                'customizations': item_row[6],
                                'gst': item_row[7],
                                'tax_amount': item_row[8]
                            })
                    
                    order['items'] = items

            # Now build the response using the reference code structure
            # Parse business hours JSON to extract opening/closing times
            business_hours_json = order.get("business_hours_json")
            opening_time = None
            closing_time = None
            
            if business_hours_json:
                try:
                    import json
                    business_hours = json.loads(business_hours_json) if isinstance(business_hours_json, str) else business_hours_json
                    # Extract general opening/closing times
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
                    pass

            # Normalise monetary values and item details using Decimal for precision
            items = order.get("items", [])
            formatted_items = []
            subtotal_dec = Decimal('0.00')
            tax_total_dec = Decimal('0.00')

            for item in items:
                # Best-effort enrichment for missing item fields
                bt_val = (order.get('business_type') or order.get('businessType') or order.get('businessType'.lower()))
                bt_val = str(bt_val).upper() if bt_val is not None else None

                item_product_id = item.get('product_id')
                item_variant_id = item.get('variant_id')
                item_menu_item_id = item.get('menu_item_id')

                # If variant_id is missing, try to backfill from order_items table
                if not item_variant_id:
                    try:
                        item_row_id = item.get('item_id') or item.get('id')
                        if item_row_id:
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

            # Get customer address info
            def _get_customer_address_info(order):
                try:
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
                    
                    return None, None, None, None
                except Exception:
                    return None, None, None, None

            def _get_delivery_partner_details(order):
                """Fetch delivery partner details for the given order across systems."""
                try:
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

            # Format business address
            def _format_business_address(order):
                business_address_parts = []
                
                if order.get('business_address'):
                    business_address_parts.append(order.get('business_address'))
                
                if order.get('business_landmark'):
                    business_address_parts.append(f"Landmark: {order.get('business_landmark')}")
                
                if order.get('business_city'):
                    business_address_parts.append(order.get('business_city'))
                
                if order.get('business_state'):
                    business_address_parts.append(order.get('business_state'))
                
                if order.get('business_pincode'):
                    business_address_parts.append(f"Pincode: {order.get('business_pincode')}")
                
                return ', '.join(business_address_parts) if business_address_parts else 'Address not available'

            # Build the final response
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
                        "updated_at": order.get("created_at").isoformat() if order.get("created_at") else None,
                        "delivery_address": cust_address or order.get("delivery_address"),
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
                            "address": _format_business_address(order),
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
                            "display_name": f"{order.get('first_name', '')} {order.get('last_name', '')}".strip(),
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
                        "company_details": None,
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
            logger.error(f"Error retrieving order details: {str(e)}")
            return Response({
                'success': False,
                'message': f'Error retrieving order details: {str(e)}'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class AdminOrderAssignDeliveryView(APIView):
    """Assign delivery partner to order"""
    permission_classes = []  # Remove authentication requirement
    
    def post(self, request, order_id):
        try:
            data = json.loads(request.body)
            delivery_partner_id = data.get('delivery_partner_id')
            order_system = data.get('order_system', 'standard')
            
            if not delivery_partner_id:
                return Response({
                    'success': False,
                    'message': 'delivery_partner_id is required'
                }, status=status.HTTP_400_BAD_REQUEST)
            
            with connection.cursor() as cursor:
                # Verify delivery partner exists
                cursor.execute("""
                    SELECT user_id, displayName 
                    FROM registrations 
                    WHERE user_id = %s
                """, [delivery_partner_id])
                
                partner = cursor.fetchone()
                if not partner:
                    return Response({
                        'success': False,
                        'message': 'Delivery partner not found'
                    }, status=status.HTTP_404_NOT_FOUND)
                
                if order_system == 'grocery':
                    # Handle grocery order assignment
                    cursor.execute("""
                        INSERT INTO Grocery_deliver_details 
                        (order_id, partner_id, assignment_status, assigned_at, is_active)
                        VALUES (%s, %s, 'assigned', NOW(), 1)
                        ON DUPLICATE KEY UPDATE
                        partner_id = %s, assignment_status = 'assigned', assigned_at = NOW()
                    """, [order_id, delivery_partner_id, delivery_partner_id])
                    
                    cursor.execute("""
                        UPDATE Groceries_orders 
                        SET order_status = 'assigned', updated_at = NOW()
                        WHERE order_id = %s
                    """, [order_id])
                    
                else:
                    # Handle standard order assignment
                    cursor.execute("""
                        UPDATE orders 
                        SET delivery_partner_id = %s, status = 'assigned', updated_at = NOW()
                        WHERE order_id = %s
                    """, [delivery_partner_id, order_id])
                
                return Response({
                    'success': True,
                    'message': 'Delivery partner assigned successfully',
                    'order_id': order_id,
                    'order_system': order_system,
                    'delivery_partner_id': delivery_partner_id,
                    'delivery_partner_name': partner[1],
                    'order_status': 'assigned'
                }, status=status.HTTP_200_OK)
                
        except Exception as e:
            logger.error(f"Error assigning delivery partner: {str(e)}")
            return Response({
                'success': False,
                'message': f'Error assigning delivery partner: {str(e)}'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


# ============================================================================
# ADMIN DELIVERY PROVIDER MANAGEMENT SERVICE  
# ============================================================================

class AdminDeliveryFleetManagementView(APIView):
    """Comprehensive Delivery Fleet Management System"""
    permission_classes = []  # Remove authentication requirement
    
    def get(self, request):
        """Get comprehensive delivery fleet data with all requested features"""
        try:
            page = int(request.query_params.get('page', 1))
            limit = min(int(request.query_params.get('limit', 20)), 100)
            offset = (page - 1) * limit
            
            # Distance filter parameters
            distance_period = request.query_params.get('distance_period', 'all')  # day, week, month, half-year, yearly, custom
            date_from = request.query_params.get('date_from')
            date_to = request.query_params.get('date_to')
            
            with connection.cursor() as cursor:
                # Main query with all delivery partner data
                base_query = """
                    SELECT 
                        r.user_id,
                        r.displayName,
                        r.mobileNumber,
                        r.emailID,
                        dp.id as delivery_partner_id,
                        dp.phone_number,
                        dp.vehicle_type,
                        dp.latitude,
                        dp.longitude,
                        dp.rating,
                        dp.status as dp_status,
                        dp.is_available,
                        dp.is_verified,
                        dp.created_at as registered_at,
                        COALESCE(order_stats.total_deliveries, 0) as total_deliveries,
                        COALESCE(order_stats.completed_deliveries, 0) as completed_deliveries,
                        COALESCE(active_orders.active_count, 0) as active_orders_count,
                        -- Order status breakdowns
                        COALESCE(delivered_orders.count, 0) as delivered_orders_count,
                        COALESCE(out_for_delivery_orders.count, 0) as out_for_delivery_orders_count,
                        COALESCE(picked_up_orders.count, 0) as picked_up_orders_count,
                        COALESCE(ready_orders.count, 0) as ready_orders_count
                    FROM registrations r
                    INNER JOIN delivery_partner dp ON r.user_id = dp.user_id
                    LEFT JOIN (
                        SELECT 
                            delivery_partner_id,
                            COUNT(*) as total_deliveries,
                            SUM(CASE WHEN status IN ('delivered', 'completed') THEN 1 ELSE 0 END) as completed_deliveries
                        FROM orders 
                        WHERE delivery_partner_id IS NOT NULL
                        GROUP BY delivery_partner_id
                    ) order_stats ON r.user_id = order_stats.delivery_partner_id
                    LEFT JOIN (
                        SELECT 
                            delivery_partner_id,
                            COUNT(*) as active_count
                        FROM orders 
                        WHERE delivery_partner_id IS NOT NULL 
                        AND status IN ('assigned', 'picked_up', 'travelling', 'out_for_delivery')
                        GROUP BY delivery_partner_id
                    ) active_orders ON r.user_id = active_orders.delivery_partner_id
                    LEFT JOIN (
                        SELECT delivery_partner_id, COUNT(*) as count
                        FROM orders 
                        WHERE delivery_partner_id IS NOT NULL AND status = 'delivered'
                        GROUP BY delivery_partner_id
                    ) delivered_orders ON r.user_id = delivered_orders.delivery_partner_id
                    LEFT JOIN (
                        SELECT delivery_partner_id, COUNT(*) as count
                        FROM orders 
                        WHERE delivery_partner_id IS NOT NULL AND status = 'out_for_delivery'
                        GROUP BY delivery_partner_id
                    ) out_for_delivery_orders ON r.user_id = out_for_delivery_orders.delivery_partner_id
                    LEFT JOIN (
                        SELECT delivery_partner_id, COUNT(*) as count
                        FROM orders 
                        WHERE delivery_partner_id IS NOT NULL AND status = 'picked_up'
                        GROUP BY delivery_partner_id
                    ) picked_up_orders ON r.user_id = picked_up_orders.delivery_partner_id
                    LEFT JOIN (
                        SELECT delivery_partner_id, COUNT(*) as count
                        FROM orders 
                        WHERE delivery_partner_id IS NOT NULL AND status = 'ready'
                        GROUP BY delivery_partner_id
                    ) ready_orders ON r.user_id = ready_orders.delivery_partner_id
                    WHERE NOT (dp.status = 0 AND dp.is_available = 0 AND dp.is_verified = 0)
                    ORDER BY 
                        CASE 
                            WHEN dp.status = 'available' AND dp.is_available = 1 THEN 1
                            WHEN dp.status = 'on_delivery' AND dp.is_available = 0 THEN 2
                            ELSE 3
                        END,
                        r.created_at DESC
                    LIMIT %s OFFSET %s
                """
                
                cursor.execute(base_query, [limit, offset])
                providers = cursor.fetchall()
                
                # Get total count (excluding inactive partners)
                cursor.execute("""
                    SELECT COUNT(*) 
                    FROM registrations r
                    INNER JOIN delivery_partner dp ON r.user_id = dp.user_id
                    WHERE NOT (dp.status = 0 AND dp.is_available = 0 AND dp.is_verified = 0)
                """)
                total_providers = cursor.fetchone()[0]
                
                # Process each provider with detailed information
                provider_list = []
                for row in providers:
                    (user_id, display_name, mobile_number, email_id, delivery_partner_id, 
                     phone_number, vehicle_type, latitude, longitude, rating, dp_status, 
                     is_available, is_verified, registered_at, total_deliveries, 
                     completed_deliveries, active_orders_count, delivered_orders_count,
                     out_for_delivery_orders_count, picked_up_orders_count, ready_orders_count) = row
                    
                    # Determine status according to requirements
                    if dp_status == 'available' and is_available == 1:
                        current_status = 'available'
                    elif dp_status == 'on_delivery' or (dp_status == 'available' and is_available == 0):
                        current_status = 'busy'
                    else:
                        current_status = 'offline'
                    
                    # Get distance traveled based on filter
                    distance_data = self._get_distance_traveled(cursor, delivery_partner_id, distance_period, date_from, date_to)
                    
                    # Get current location
                    current_location = None
                    if latitude is not None and longitude is not None:
                        current_location = {
                            'latitude': float(latitude),
                            'longitude': float(longitude),
                            'last_updated': None  # Will be updated with latest location timestamp
                        }
                        # Get latest location update time
                        cursor.execute("""
                            SELECT timestamp 
                            FROM deliverylocationhistory 
                            WHERE delivery_partner_id = %s 
                            ORDER BY timestamp DESC 
                            LIMIT 1
                        """, [delivery_partner_id])
                        latest_location = cursor.fetchone()
                        if latest_location:
                            current_location['last_updated'] = latest_location[0]
                    
                    # Get recent orders with details
                    recent_orders = self._get_recent_orders(cursor, user_id)
                    
                    provider_list.append({
                        'provider_id': user_id,
                        'delivery_partner_id': delivery_partner_id,
                        'name': display_name,
                        'phone': mobile_number,
                        'email': email_id,
                        'delivery_phone': phone_number,
                        'vehicle_type': vehicle_type.title() if vehicle_type else 'Unknown',
                        'registered_at': registered_at,
                        'rating': float(rating) if rating else 0.0,
                        'status': current_status.title(),
                        'is_verified': bool(is_verified),
                        'current_location': current_location,
                        
                        # Order statistics
                        'total_deliveries': int(total_deliveries),
                        'completed_deliveries': int(completed_deliveries),
                        'active_orders_count': int(active_orders_count),
                        
                        # Order status breakdowns
                        'order_breakdown': {
                            'delivered': {
                                'count': int(delivered_orders_count),
                                'orders': [order for order in recent_orders if order['status'] == 'delivered']
                            },
                            'out_for_delivery': {
                                'count': int(out_for_delivery_orders_count),
                                'orders': [order for order in recent_orders if order['status'] == 'out_for_delivery']
                            },
                            'picked_up': {
                                'count': int(picked_up_orders_count),
                                'orders': [order for order in recent_orders if order['status'] == 'picked_up']
                            },
                            'ready': {
                                'count': int(ready_orders_count),
                                'orders': [order for order in recent_orders if order['status'] == 'ready']
                            }
                        },
                        
                        # Distance metrics
                        'distance_metrics': distance_data,
                        
                        # Recent orders with distance
                        'recent_orders': recent_orders
                    })
                
                # Calculate overall KPI metrics
                kpi_metrics = self._calculate_kpi_metrics(cursor)
                
                total_pages = (total_providers + limit - 1) // limit
                
                return Response({
                    'success': True,
                    'message': 'Delivery fleet data retrieved successfully',
                    'filters': {
                        'distance_period': distance_period,
                        'date_from': date_from,
                        'date_to': date_to,
                        'page': page,
                        'limit': limit
                    },
                    'pagination': {
                        'total_providers': total_providers,
                        'current_page': page,
                        'per_page': limit,
                        'total_pages': total_pages,
                        'has_next_page': page < total_pages,
                        'has_prev_page': page > 1
                    },
                    'kpi_metrics': kpi_metrics,
                    'providers': provider_list
                }, status=status.HTTP_200_OK)
                
        except Exception as e:
            logger.error(f"Error retrieving delivery fleet data: {str(e)}")
            return Response({
                'success': False,
                'message': f'Error retrieving delivery fleet data: {str(e)}'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    
    def _get_distance_traveled(self, cursor, delivery_partner_id, period, date_from=None, date_to=None):
        """Get distance traveled by delivery partner based on time period"""
        try:
            # Build date filter
            date_condition = ""
            params = [delivery_partner_id]
            
            if period == 'day':
                date_condition = "AND timestamp >= DATE_SUB(NOW(), INTERVAL 1 DAY)"
            elif period == 'week':
                date_condition = "AND timestamp >= DATE_SUB(NOW(), INTERVAL 1 WEEK)"
            elif period == 'month':
                date_condition = "AND timestamp >= DATE_SUB(NOW(), INTERVAL 1 MONTH)"
            elif period == 'half-year':
                date_condition = "AND timestamp >= DATE_SUB(NOW(), INTERVAL 6 MONTH)"
            elif period == 'yearly':
                date_condition = "AND timestamp >= DATE_SUB(NOW(), INTERVAL 1 YEAR)"
            elif period == 'custom' and date_from and date_to:
                date_condition = "AND timestamp BETWEEN %s AND %s"
                params.extend([date_from, date_to])
            
            cursor.execute(f"""
                SELECT latitude, longitude, timestamp
                FROM deliverylocationhistory 
                WHERE delivery_partner_id = %s {date_condition}
                ORDER BY timestamp ASC
            """, params)
            
            location_history = cursor.fetchall()
            
            if len(location_history) < 2:
                return {
                    'total_distance_km': 0.0,
                    'period': period,
                    'location_points': len(location_history)
                }
            
            # Calculate total distance
            total_distance = 0.0
            for i in range(1, len(location_history)):
                prev_lat, prev_lon, prev_time = location_history[i-1]
                curr_lat, curr_lon, curr_time = location_history[i]
                
                # Calculate distance between consecutive points
                distance = calculate_distance(prev_lat, prev_lon, curr_lat, curr_lon)
                total_distance += distance
            
            return {
                'total_distance_km': round(total_distance, 2),
                'period': period,
                'location_points': len(location_history),
                'start_time': location_history[0][2] if location_history else None,
                'end_time': location_history[-1][2] if location_history else None
            }
            
        except Exception as e:
            logger.error(f"Error calculating distance for partner {delivery_partner_id}: {e}")
            return {
                'total_distance_km': 0.0,
                'period': period,
                'location_points': 0,
                'error': str(e)
            }
    
    def _get_recent_orders(self, cursor, user_id, limit=10):
        """Get recent orders for a delivery partner with distance information"""
        try:
            cursor.execute("""
                SELECT 
                    o.order_id as order_id,
                    o.order_id as order_number,
                    o.status,
                    o.created_at,
                    o.updated_at,
                    o.total_amount,
                    o.delivery_address,
                    r.firstName as customer_first_name,
                    r.lastName as customer_last_name,
                    r.mobileNumber as customer_phone,
                    -- Simple distance calculation (placeholder)
                    0 as order_distance_km
                FROM orders o
                LEFT JOIN registrations r ON o.user_id = r.user_id
                WHERE o.delivery_partner_id = %s
                ORDER BY o.updated_at DESC
                LIMIT %s
            """, [user_id, limit])
            
            orders = []
            for row in cursor.fetchall():
                (order_id, order_number, status, created_at, updated_at, total_amount,
                 delivery_address, customer_first_name, customer_last_name,
                 customer_phone, order_distance_km) = row
                
                orders.append({
                    'order_id': order_id,
                    'order_number': order_number,
                    'status': status,
                    'created_at': created_at,
                    'updated_at': updated_at,
                    'total_amount': float(total_amount) if total_amount else 0.0,
                    'delivery_address': delivery_address,
                    'pickup_address': None,  # Field may not exist
                    'customer_name': f"{customer_first_name or ''} {customer_last_name or ''}".strip(),
                    'customer_phone': customer_phone,
                    'distance_km': float(order_distance_km) if order_distance_km else 0.0
                })
            
            return orders
            
        except Exception as e:
            logger.error(f"Error fetching recent orders for user {user_id}: {e}")
            return []
    
    def _calculate_kpi_metrics(self, cursor):
        """Calculate overall KPI metrics for the delivery fleet"""
        try:
            # Total partners by status
            cursor.execute("""
                SELECT 
                    COUNT(*) as total_partners,
                    SUM(CASE WHEN dp.status = 'available' AND dp.is_available = 1 THEN 1 ELSE 0 END) as available_partners,
                    SUM(CASE WHEN dp.status = 'on_delivery' OR (dp.status = 'available' AND dp.is_available = 0) THEN 1 ELSE 0 END) as busy_partners,
                    SUM(CASE WHEN dp.is_verified = 1 THEN 1 ELSE 0 END) as verified_partners,
                    AVG(dp.rating) as average_rating,
                    SUM(dp.total_deliveries) as total_deliveries,
                    COUNT(DISTINCT o.order_id) as total_orders
                FROM delivery_partner dp
                LEFT JOIN orders o ON o.delivery_partner_id = dp.user_id
                WHERE NOT (dp.status = 0 AND dp.is_available = 0 AND dp.is_verified = 0)
            """)
            
            kpi_data = cursor.fetchone()
            (total_partners, available_partners, busy_partners, verified_partners,
             average_rating, total_deliveries, total_orders) = kpi_data
            
            # Order status breakdown
            cursor.execute("""
                SELECT 
                    o.status,
                    COUNT(*) as count
                FROM orders o
                WHERE o.delivery_partner_id IS NOT NULL
                GROUP BY o.status
            """)
            
            order_status_breakdown = dict(cursor.fetchall())
            
            # Distance metrics (today) - simplified version
            cursor.execute("""
                SELECT 
                    COUNT(*) as total_location_updates_today
                FROM deliverylocationhistory 
                WHERE timestamp >= DATE_SUB(NOW(), INTERVAL 1 DAY)
            """)
            
            location_data = cursor.fetchone()
            total_location_updates = location_data[0]
            
            # Calculate total distance today (simplified approach)
            cursor.execute("""
                SELECT 
                    COUNT(*) as total_location_updates,
                    COUNT(DISTINCT delivery_partner_id) as active_partners_today
                FROM deliverylocationhistory 
                WHERE timestamp >= DATE_SUB(NOW(), INTERVAL 1 DAY)
            """)
            
            distance_data = cursor.fetchone()
            (total_location_updates, active_partners_today) = distance_data
            
            # Estimate distance based on location updates (rough calculation)
            estimated_distance_today = total_location_updates * 0.5  # Rough estimate: 0.5km per update
            
            return {
                'total_partners': int(total_partners or 0),
                'available_partners': int(available_partners or 0),
                'busy_partners': int(busy_partners or 0),
                'verified_partners': int(verified_partners or 0),
                'average_rating': float(average_rating or 0.0),
                'total_deliveries': int(total_deliveries or 0),
                'total_orders': int(total_orders or 0),
                'order_status_breakdown': order_status_breakdown,
                'total_location_updates_today': int(total_location_updates or 0),
                'total_distance_today_km': round(estimated_distance_today, 2),
                'fleet_utilization_rate': round((int(busy_partners or 0) / max(int(total_partners or 1), 1)) * 100, 2),
                'active_partners_today': int(active_partners_today or 0)
            }
            
        except Exception as e:
            logger.error(f"Error calculating KPI metrics: {e}")
            return {
                'error': str(e),
                'total_partners': 0,
                'available_partners': 0,
                'busy_partners': 0,
                'verified_partners': 0
            }


class AdminDeliveryFleetDetailView(APIView):
    """Detailed view for individual delivery partner in fleet management"""
    permission_classes = []  # Remove authentication requirement
    
    def get(self, request, provider_id):
        """Get comprehensive details for a specific delivery partner"""
        try:
            # Distance filter parameters
            distance_period = request.query_params.get('distance_period', 'all')
            date_from = request.query_params.get('date_from')
            date_to = request.query_params.get('date_to')
            order_period = request.query_params.get('order_period', 'all')  # day, week, month, all
            
            with connection.cursor() as cursor:
                # Get delivery partner basic details
                cursor.execute("""
                    SELECT 
                        r.user_id,
                        r.displayName,
                        r.mobileNumber,
                        r.emailID,
                        r.firstName,
                        r.lastName,
                        dp.id as delivery_partner_id,
                        dp.phone_number,
                        dp.vehicle_type,
                        dp.vehicle_number,
                        dp.latitude,
                        dp.longitude,
                        dp.rating,
                        dp.status as dp_status,
                        dp.is_available,
                        dp.is_verified,
                        dp.created_at as registered_at,
                        dp.updated_at as last_updated
                    FROM registrations r
                    INNER JOIN delivery_partner dp ON r.user_id = dp.user_id
                    WHERE r.user_id = %s
                    LIMIT 1
                """, [provider_id])
                
                partner_data = cursor.fetchone()
                if not partner_data:
                    return Response({
                        'success': False,
                        'message': 'Delivery partner not found'
                    }, status=status.HTTP_404_NOT_FOUND)
                
                (user_id, display_name, mobile_number, email_id, first_name, last_name,
                 delivery_partner_id, phone_number, vehicle_type, vehicle_number, latitude,
                 longitude, rating, dp_status, is_available, is_verified, registered_at,
                 last_updated) = partner_data
                
                # Determine status according to requirements
                if dp_status == 'available' and is_available == 1:
                    current_status = 'available'
                elif dp_status == 'on_delivery' or (dp_status == 'available' and is_available == 0):
                    current_status = 'busy'
                else:
                    current_status = 'offline'
                
                # Get comprehensive order statistics
                order_stats = self._get_detailed_order_stats(cursor, user_id, order_period)
                
                # Get distance metrics
                distance_data = self._get_distance_traveled(cursor, delivery_partner_id, distance_period, date_from, date_to)
                
                # Get current location with recent location history
                current_location, location_history = self._get_current_location_with_history(cursor, delivery_partner_id, limit=50)
                
                # Get detailed order history
                detailed_orders = self._get_detailed_order_history(cursor, user_id, limit=20)
                
                # Get performance metrics
                performance_metrics = self._calculate_performance_metrics(cursor, user_id)
                
                # Get earnings data (if available)
                earnings_data = self._get_earnings_data(cursor, user_id, distance_period, date_from, date_to)
                
                partner_details = {
                    'provider_id': user_id,
                    'delivery_partner_id': delivery_partner_id,
                    'name': display_name,
                    'first_name': first_name,
                    'last_name': last_name,
                    'phone': mobile_number,
                    'email': email_id,
                    'delivery_phone': phone_number,
                    'vehicle_type': vehicle_type.title() if vehicle_type else 'Unknown',
                    'vehicle_number': vehicle_number,
                    'rating': float(rating) if rating else 0.0,
                    'status': current_status.title(),
                    'is_verified': bool(is_verified),
                    'is_available': bool(is_available),
                    'registered_at': registered_at,
                    'last_updated': last_updated,
                    'current_location': current_location,
                    
                    # Comprehensive statistics
                    'order_statistics': order_stats,
                    'distance_metrics': distance_data,
                    'performance_metrics': performance_metrics,
                    'earnings_data': earnings_data,
                    
                    # Detailed data
                    'location_history': location_history,
                    'recent_orders': detailed_orders
                }
                
                return Response({
                    'success': True,
                    'message': 'Delivery partner details retrieved successfully',
                    'filters': {
                        'distance_period': distance_period,
                        'date_from': date_from,
                        'date_to': date_to,
                        'order_period': order_period
                    },
                    'partner': partner_details
                }, status=status.HTTP_200_OK)
                
        except Exception as e:
            logger.error(f"Error retrieving delivery partner details: {str(e)}")
            return Response({
                'success': False,
                'message': f'Error retrieving delivery partner details: {str(e)}'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    
    def _get_detailed_order_stats(self, cursor, user_id, period='all'):
        """Get detailed order statistics for a delivery partner"""
        try:
            date_condition = ""
            params = [user_id]
            
            if period == 'day':
                date_condition = "AND o.created_at >= DATE_SUB(NOW(), INTERVAL 1 DAY)"
            elif period == 'week':
                date_condition = "AND o.created_at >= DATE_SUB(NOW(), INTERVAL 1 WEEK)"
            elif period == 'month':
                date_condition = "AND o.created_at >= DATE_SUB(NOW(), INTERVAL 1 MONTH)"
            
            cursor.execute(f"""
                SELECT 
                    COUNT(*) as total_orders,
                    SUM(CASE WHEN o.status IN ('delivered', 'completed') THEN 1 ELSE 0 END) as completed_orders,
                    SUM(CASE WHEN o.status = 'delivered' THEN 1 ELSE 0 END) as delivered_orders,
                    SUM(CASE WHEN o.status = 'out_for_delivery' THEN 1 ELSE 0 END) as out_for_delivery_orders,
                    SUM(CASE WHEN o.status = 'picked_up' THEN 1 ELSE 0 END) as picked_up_orders,
                    SUM(CASE WHEN o.status = 'ready' THEN 1 ELSE 0 END) as ready_orders,
                    SUM(CASE WHEN o.status = 'assigned' THEN 1 ELSE 0 END) as assigned_orders,
                    SUM(CASE WHEN o.status = 'cancelled' THEN 1 ELSE 0 END) as cancelled_orders,
                    AVG(o.total_amount) as average_order_value,
                    SUM(o.total_amount) as total_revenue,
                    AVG(TIMESTAMPDIFF(MINUTE, o.created_at, COALESCE(o.updated_at, NOW()))) as avg_completion_time_minutes
                FROM orders o
                WHERE o.delivery_partner_id = %s {date_condition}
            """, params)
            
            stats = cursor.fetchone()
            (total_orders, completed_orders, delivered_orders, out_for_delivery_orders,
             picked_up_orders, ready_orders, assigned_orders, cancelled_orders,
             average_order_value, total_revenue, avg_completion_time) = stats
            
            # Get order status breakdown with details
            cursor.execute(f"""
                SELECT 
                    o.status,
                    COUNT(*) as count,
                    SUM(o.total_amount) as total_value,
                    AVG(TIMESTAMPDIFF(MINUTE, o.created_at, COALESCE(o.updated_at, NOW()))) as avg_time_minutes
                FROM orders o
                WHERE o.delivery_partner_id = %s {date_condition}
                GROUP BY o.status
                ORDER BY count DESC
            """, params)
            
            status_breakdown = []
            for row in cursor.fetchall():
                status, count, total_value, avg_time = row
                status_breakdown.append({
                    'status': status,
                    'count': int(count),
                    'total_value': float(total_value) if total_value else 0.0,
                    'avg_time_minutes': float(avg_time) if avg_time else 0.0
                })
            
            return {
                'total_orders': int(total_orders),
                'completed_orders': int(completed_orders),
                'delivered_orders': int(delivered_orders),
                'out_for_delivery_orders': int(out_for_delivery_orders),
                'picked_up_orders': int(picked_up_orders),
                'ready_orders': int(ready_orders),
                'assigned_orders': int(assigned_orders),
                'cancelled_orders': int(cancelled_orders),
                'average_order_value': float(average_order_value) if average_order_value else 0.0,
                'total_revenue': float(total_revenue) if total_revenue else 0.0,
                'average_completion_time_minutes': float(avg_completion_time) if avg_completion_time else 0.0,
                'completion_rate': round((int(completed_orders) / max(int(total_orders), 1)) * 100, 2),
                'status_breakdown': status_breakdown
            }
            
        except Exception as e:
            logger.error(f"Error getting detailed order stats: {e}")
            return {'error': str(e)}
    
    def _get_current_location_with_history(self, cursor, delivery_partner_id, limit=50):
        """Get current location and recent location history"""
        try:
            cursor.execute("""
                SELECT latitude, longitude, timestamp
                FROM deliverylocationhistory 
                WHERE delivery_partner_id = %s 
                ORDER BY timestamp DESC 
                LIMIT %s
            """, [delivery_partner_id, limit])
            
            location_data = cursor.fetchall()
            
            if not location_data:
                return None, []
            
            current_location = {
                'latitude': float(location_data[0][0]),
                'longitude': float(location_data[0][1]),
                'last_updated': location_data[0][2]
            }
            
            location_history = []
            for lat, lon, timestamp in location_data:
                location_history.append({
                    'latitude': float(lat),
                    'longitude': float(lon),
                    'timestamp': timestamp
                })
            
            return current_location, location_history
            
        except Exception as e:
            logger.error(f"Error getting location data: {e}")
            return None, []
    
    def _get_detailed_order_history(self, cursor, user_id, limit=20):
        """Get detailed order history with distance and customer info"""
        try:
            cursor.execute("""
                SELECT 
                    o.order_id as order_id,
                    o.order_id as order_number,
                    o.status,
                    o.created_at,
                    o.updated_at,
                    o.total_amount,
                    o.delivery_address,
                    r.firstName as customer_first_name,
                    r.lastName as customer_last_name,
                    r.mobileNumber as customer_phone,
                    -- Simple distance calculation (placeholder)
                    0 as order_distance_km,
                    -- Calculate delivery time
                    TIMESTAMPDIFF(MINUTE, o.created_at, COALESCE(o.updated_at, NOW())) as delivery_time_minutes
                FROM orders o
                LEFT JOIN registrations r ON o.user_id = r.user_id
                WHERE o.delivery_partner_id = %s
                ORDER BY o.updated_at DESC
                LIMIT %s
            """, [user_id, limit])
            
            orders = []
            for row in cursor.fetchall():
                (order_id, order_number, status, created_at, updated_at, total_amount,
                 delivery_address, customer_first_name, customer_last_name, customer_phone,
                 order_distance_km, delivery_time_minutes) = row
                
                orders.append({
                    'order_id': order_id,
                    'order_number': order_number,
                    'status': status,
                    'created_at': created_at,
                    'updated_at': updated_at,
                    'total_amount': float(total_amount) if total_amount else 0.0,
                    'delivery_address': delivery_address,
                    'pickup_address': None,  # Field may not exist
                    'delivery_notes': None,  # Field may not exist
                    'customer_name': f"{customer_first_name or ''} {customer_last_name or ''}".strip(),
                    'customer_phone': customer_phone,
                    'business_name': None,  # Will be populated if needed
                    'distance_km': float(order_distance_km) if order_distance_km else 0.0,
                    'delivery_time_minutes': int(delivery_time_minutes) if delivery_time_minutes else 0
                })
            
            return orders
            
        except Exception as e:
            logger.error(f"Error getting detailed order history: {e}")
            return []
    
    def _calculate_performance_metrics(self, cursor, user_id):
        """Calculate performance metrics for the delivery partner"""
        try:
            cursor.execute("""
                SELECT 
                    COUNT(*) as total_deliveries,
                    AVG(TIMESTAMPDIFF(MINUTE, o.created_at, o.updated_at)) as avg_delivery_time,
                    SUM(o.total_amount) as total_earnings,
                    AVG(o.total_amount) as avg_earning_per_order,
                    COUNT(DISTINCT DATE(o.created_at)) as active_days,
                    MIN(o.created_at) as first_delivery,
                    MAX(o.created_at) as last_delivery
                FROM orders o
                WHERE o.delivery_partner_id = %s 
                AND o.status IN ('delivered', 'completed')
            """, [user_id])
            
            perf_data = cursor.fetchone()
            (total_deliveries, avg_delivery_time, total_earnings, avg_earning_per_order,
             active_days, first_delivery, last_delivery) = perf_data
            
            # Calculate daily average
            if active_days and active_days > 0:
                daily_avg_deliveries = total_deliveries / active_days
                daily_avg_earnings = float(total_earnings) / active_days
            else:
                daily_avg_deliveries = 0
                daily_avg_earnings = 0.0
            
            return {
                'total_deliveries': int(total_deliveries or 0),
                'average_delivery_time_minutes': float(avg_delivery_time) if avg_delivery_time else 0.0,
                'total_earnings': float(total_earnings) if total_earnings else 0.0,
                'average_earning_per_order': float(avg_earning_per_order) if avg_earning_per_order else 0.0,
                'active_delivery_days': int(active_days or 0),
                'daily_average_deliveries': round(daily_avg_deliveries, 2),
                'daily_average_earnings': round(daily_avg_earnings, 2),
                'first_delivery_date': first_delivery,
                'last_delivery_date': last_delivery
            }
            
        except Exception as e:
            logger.error(f"Error calculating performance metrics: {e}")
            return {'error': str(e)}
    
    def _get_earnings_data(self, cursor, user_id, period='all', date_from=None, date_to=None):
        """Get earnings data for the delivery partner"""
        try:
            date_condition = ""
            params = [user_id]
            
            if period == 'day':
                date_condition = "AND DATE(o.created_at) = CURDATE()"
            elif period == 'week':
                date_condition = "AND o.created_at >= DATE_SUB(NOW(), INTERVAL 1 WEEK)"
            elif period == 'month':
                date_condition = "AND o.created_at >= DATE_SUB(NOW(), INTERVAL 1 MONTH)"
            elif period == 'custom' and date_from and date_to:
                date_condition = "AND DATE(o.created_at) BETWEEN %s AND %s"
                params.extend([date_from, date_to])
            
            cursor.execute(f"""
                SELECT 
                    DATE(o.created_at) as earnings_date,
                    COUNT(*) as order_count,
                    SUM(o.total_amount) as daily_earnings,
                    AVG(o.total_amount) as avg_order_value
                FROM orders o
                WHERE o.delivery_partner_id = %s 
                AND o.status IN ('delivered', 'completed')
                {date_condition}
                GROUP BY DATE(o.created_at)
                ORDER BY earnings_date DESC
                LIMIT 30
            """, params)
            
            daily_earnings = []
            for row in cursor.fetchall():
                earnings_date, order_count, daily_earnings_amount, avg_order_value = row
                daily_earnings.append({
                    'date': earnings_date,
                    'order_count': int(order_count),
                    'daily_earnings': float(daily_earnings_amount) if daily_earnings_amount else 0.0,
                    'average_order_value': float(avg_order_value) if avg_order_value else 0.0
                })
            
            return {
                'daily_earnings': daily_earnings,
                'period': period
            }
            
        except Exception as e:
            logger.error(f"Error getting earnings data: {e}")
            return {'error': str(e)}


class AdminDeliveryProviderManagementView(APIView):
    """Admin service for managing delivery providers"""
    permission_classes = []  # Remove authentication requirement
    
    def get(self, request):
        """List all delivery providers with their statistics"""
        try:
            page = int(request.query_params.get('page', 1))
            limit = min(int(request.query_params.get('limit', 20)), 100)
            offset = (page - 1) * limit
            
            with connection.cursor() as cursor:
                base_query = """
                    SELECT 
                        r.user_id,
                        r.displayName,
                        r.mobileNumber,
                        r.emailID,
                        dp.phone_number,
                        dp.vehicle_type,
                        dp.created_at as registered_at,
                        COALESCE(order_stats.total_deliveries, 0) as total_deliveries,
                        COALESCE(order_stats.completed_deliveries, 0) as completed_deliveries,
                        CASE 
                            WHEN dp.is_available = 0 THEN 'Busy'
                            WHEN dp.is_available = 1 THEN 'Available'
                            ELSE 'Offline'
                        END as current_status
                    FROM registrations r
                    INNER JOIN delivery_partner dp ON r.user_id = dp.user_id
                    LEFT JOIN (
                        SELECT 
                            delivery_partner_id,
                            COUNT(*) as total_deliveries,
                            SUM(CASE WHEN status IN ('delivered', 'completed') THEN 1 ELSE 0 END) as completed_deliveries
                        FROM orders 
                        WHERE delivery_partner_id IS NOT NULL
                        GROUP BY delivery_partner_id
                    ) order_stats ON r.user_id = order_stats.delivery_partner_id
                    LEFT JOIN (
                        SELECT 
                            delivery_partner_id,
                            COUNT(*) as active_count
                        FROM orders 
                        WHERE delivery_partner_id IS NOT NULL 
                        AND status IN ('assigned', 'picked_up', 'travelling', 'out_for_delivery')
                        GROUP BY delivery_partner_id
                    ) active_orders ON r.user_id = active_orders.delivery_partner_id
                    ORDER BY r.created_at DESC
                    LIMIT %s OFFSET %s
                """
                
                cursor.execute(base_query, [limit, offset])
                providers = cursor.fetchall()
                
                # Get total count
                cursor.execute("""
                    SELECT COUNT(*) 
                    FROM registrations r
                    INNER JOIN delivery_partner dp ON r.user_id = dp.user_id
                """)
                total_providers = cursor.fetchone()[0]
                
                # Format response with kilometers calculation
                provider_list = []
                for row in providers:
                    provider_id = row[0]
                    
                    # Get delivery partner ID for location history
                    cursor.execute("SELECT id FROM delivery_partner WHERE user_id = %s", [provider_id])
                    dp_result = cursor.fetchone()
                    
                    total_kilometers = 0.0
                    location_updates_count = 0
                    
                    if dp_result:
                        delivery_partner_id = dp_result[0]
                        
                        # Get location history for distance calculation
                        cursor.execute("""
                            SELECT latitude, longitude, timestamp
                            FROM deliverylocationhistory 
                            WHERE delivery_partner_id = %s 
                            ORDER BY timestamp ASC
                        """, [provider_id])
                        
                        location_history = cursor.fetchall()
                        location_updates_count = len(location_history)
                        
                        # Calculate total distance
                        if location_updates_count > 1:
                            for i in range(1, location_updates_count):
                                prev_lat, prev_lon, prev_time = location_history[i-1]
                                curr_lat, curr_lon, curr_time = location_history[i]
                                
                                # Calculate distance between consecutive points
                                distance = calculate_distance(prev_lat, prev_lon, curr_lat, curr_lon)
                                total_kilometers += distance
                    
                    provider_list.append({
                        'provider_id': provider_id,
                        'name': row[1],
                        'phone': row[2],
                        'email': row[3],
                        'delivery_phone': row[4],
                        'vehicle_type': row[5],
                        'registered_at': row[6],
                        'total_deliveries': row[7],
                        'completed_deliveries': row[8],
                        'status': row[9],
                        'total_kilometers_traveled': round(total_kilometers, 2),
                        'location_updates_count': location_updates_count
                    })
                
                total_pages = (total_providers + limit - 1) // limit
                
                return Response({
                    'success': True,
                    'message': 'Delivery providers retrieved successfully',
                    'pagination': {
                        'total_providers': total_providers,
                        'current_page': page,
                        'per_page': limit,
                        'total_pages': total_pages,
                        'has_next_page': page < total_pages,
                        'has_prev_page': page > 1
                    },
                    'providers': provider_list
                }, status=status.HTTP_200_OK)
                
        except Exception as e:
            logger.error(f"Error retrieving delivery providers: {str(e)}")
            return Response({
                'success': False,
                'message': f'Error retrieving delivery providers: {str(e)}'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class AdminDeliveryProviderDetailView(APIView):
    """Manage individual delivery provider details"""
    permission_classes = []  # Remove authentication requirement
    
    def get(self, request, provider_id):
        """Get detailed information about a specific delivery provider"""
        try:
            with connection.cursor() as cursor:
                # Get delivery partner basic details
                cursor.execute("""
                    SELECT 
                        r.user_id,
                        r.displayName,
                        r.firstName,
                        r.lastName,
                        r.mobileNumber,
                        r.emailID,
                        dp.phone_number,
                        dp.vehicle_type,
                        dp.license_number,
                        dp.status,
                        dp.created_at,
                        dp.updated_at,
                        dp.id as delivery_partner_id
                    FROM registrations r
                    INNER JOIN delivery_partner dp ON r.user_id = dp.user_id
                    WHERE r.user_id = %s
                """, [provider_id])
                
                provider = cursor.fetchone()
                if not provider:
                    return Response({
                        'success': False,
                        'message': 'Delivery provider not found'
                    }, status=status.HTTP_404_NOT_FOUND)
                
                delivery_partner_id = provider[12]
                
                # Calculate total kilometers traveled from location history
                # Note: deliverylocationhistory.delivery_partner_id references delivery_partner.user_id
                cursor.execute("""
                    SELECT latitude, longitude, timestamp
                    FROM deliverylocationhistory 
                    WHERE delivery_partner_id = %s 
                    ORDER BY timestamp ASC
                """, [provider_id])
                
                location_history = cursor.fetchall()
                total_kilometers = 0.0
                location_count = len(location_history)
                
                # Calculate distance between consecutive location points
                if location_count > 1:
                    for i in range(1, location_count):
                        prev_lat, prev_lon, prev_time = location_history[i-1]
                        curr_lat, curr_lon, curr_time = location_history[i]
                        
                        # Calculate distance between consecutive points
                        distance = calculate_distance(prev_lat, prev_lon, curr_lat, curr_lon)
                        total_kilometers += distance
                
                # Get additional statistics
                cursor.execute("""
                    SELECT 
                        COUNT(*) as total_location_updates,
                        MIN(timestamp) as first_location_update,
                        MAX(timestamp) as last_location_update
                    FROM deliverylocationhistory 
                    WHERE delivery_partner_id = %s
                """, [provider_id])
                
                location_stats = cursor.fetchone()
                
                return Response({
                    'success': True,
                    'message': 'Delivery provider details retrieved successfully',
                    'provider': {
                        'provider_id': provider[0],
                        'display_name': provider[1],
                        'first_name': provider[2],
                        'last_name': provider[3],
                        'mobile_number': provider[4],
                        'email': provider[5],
                        'delivery_phone': provider[6],
                        'vehicle_type': provider[7],
                        'license_number': provider[8],
                        'status': 'Active' if provider[9] == 1 else 'Inactive',
                        'created_at': provider[10],
                        'updated_at': provider[11],
                        'total_kilometers_traveled': round(total_kilometers, 2),
                        'location_tracking_stats': {
                            'total_location_updates': location_stats[0] if location_stats else 0,
                            'first_location_update': location_stats[1].isoformat() if location_stats and location_stats[1] else None,
                            'last_location_update': location_stats[2].isoformat() if location_stats and location_stats[2] else None,
                            'tracking_period_days': (location_stats[2] - location_stats[1]).days if location_stats and location_stats[1] and location_stats[2] else 0
                        }
                    }
                }, status=status.HTTP_200_OK)
                
        except Exception as e:
            logger.error(f"Error retrieving delivery provider details: {str(e)}")
            return Response({
                'success': False,
                'message': f'Error retrieving delivery provider details: {str(e)}'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


# ============================================================================
# ADMIN ANALYTICS & REPORTING SERVICE
# ============================================================================

class AdminBusinessAnalyticsView(APIView):
    """
    Enhanced comprehensive business analytics for Power BI integration
    GET /api/v1/admin/analytics/businesses - Business performance analytics
    Includes complete order status, order type, and business-level analytics
    """
    permission_classes = []  # Remove authentication requirement
    
    def get(self, request):
        """Generate comprehensive business analytics with complete statistics"""
        try:
            date_from = request.query_params.get('date_from')
            date_to = request.query_params.get('date_to')
            business_type = request.query_params.get('business_type')
            include_grocery = request.query_params.get('include_grocery', 'true').lower() == 'true'
            
            with connection.cursor() as cursor:
                # Build date filter for regular orders
                date_filter_orders = ""
                date_filter_grocery = ""
                orders_date_params = []
                grocery_date_params = []
                
                if date_from and date_to:
                    date_filter_orders = "AND o.created_at BETWEEN %s AND %s"
                    date_filter_grocery = "AND go.created_at BETWEEN %s AND %s"
                    orders_date_params = [date_from, date_to]
                    grocery_date_params = [date_from, date_to]
                
                # Business type filter
                type_filter = ""
                type_params = []
                if business_type:
                    type_filter = "AND b.businessType = %s"
                    type_params = [business_type]
                
                # 1. Enhanced Sales & Revenue Performance Analytics
                cursor.execute(f"""
                    SELECT 
                        b.business_id,
                        b.businessName,
                        b.businessType,
                        bt.type as business_type_name,
                        b.businessCategory,
                        b.level,
                        b.master,
                        b.city,
                        b.state,
                        -- Revenue Metrics (Regular Orders)
                        COUNT(DISTINCT o.order_id) as total_orders,
                        COALESCE(SUM(CASE WHEN o.status != 'cancelled' THEN o.total_amount ELSE 0 END), 0) as gross_merchandise_value,
                        COALESCE(SUM(CASE WHEN o.status IN ('delivered', 'completed') THEN o.final_amount ELSE 0 END), 0) as total_revenue,
                        COALESCE(AVG(CASE WHEN o.status IN ('delivered', 'completed') THEN o.final_amount ELSE NULL END), 0) as average_order_value,
                        COALESCE(SUM(CASE WHEN o.status != 'cancelled' THEN o.discount_amount ELSE 0 END), 0) as total_discounts,
                        COALESCE(SUM(CASE WHEN o.status != 'cancelled' THEN o.wallet_points_used ELSE 0 END), 0) as total_wallet_savings,
                        -- Complete Order Status Breakdown (Regular Orders)
                        COUNT(DISTINCT CASE WHEN o.status = 'pending' THEN o.order_id END) as pending_orders,
                        COUNT(DISTINCT CASE WHEN o.status = 'confirmed' THEN o.order_id END) as confirmed_orders,
                        COUNT(DISTINCT CASE WHEN o.status = 'preparing' THEN o.order_id END) as preparing_orders,
                        COUNT(DISTINCT CASE WHEN o.status = 'ready' THEN o.order_id END) as ready_orders,
                        COUNT(DISTINCT CASE WHEN o.status = 'assigned' THEN o.order_id END) as assigned_orders,
                        COUNT(DISTINCT CASE WHEN o.status = 'out_for_delivery' THEN o.order_id END) as out_for_delivery_orders,
                        COUNT(DISTINCT CASE WHEN o.status = 'delivered' THEN o.order_id END) as delivered_orders,
                        COUNT(DISTINCT CASE WHEN o.status = 'completed' THEN o.order_id END) as completed_orders,
                        COUNT(DISTINCT CASE WHEN o.status = 'cancelled' THEN o.order_id END) as cancelled_orders,
                        COUNT(DISTINCT CASE WHEN o.status = 'notified' THEN o.order_id END) as notified_orders,
                        COUNT(DISTINCT CASE WHEN o.status = 'dispatched' THEN o.order_id END) as dispatched_orders,
                        COUNT(DISTINCT CASE WHEN o.status = 'travelling' THEN o.order_id END) as travelling_orders,
                        -- Order Type Breakdown (Regular Orders)
                        COUNT(DISTINCT CASE WHEN o.order_type = 'delivery' THEN o.order_id END) as delivery_orders,
                        COUNT(DISTINCT CASE WHEN o.order_type = 'pickup' THEN o.order_id END) as pickup_orders,
                        COUNT(DISTINCT CASE WHEN o.order_type = 'dine_in' THEN o.order_id END) as dine_in_orders,
                        COUNT(DISTINCT CASE WHEN o.order_type = 'takeaway' THEN o.order_id END) as takeaway_orders,
                        -- Revenue from completed orders only
                        COALESCE(SUM(CASE WHEN o.status IN ('delivered', 'completed') THEN o.final_amount ELSE 0 END), 0) as actual_revenue,
                        -- Performance Metrics
                        ROUND(
                            (COUNT(DISTINCT CASE WHEN o.status IN ('delivered', 'completed') THEN o.order_id END) / 
                             NULLIF(COUNT(DISTINCT o.order_id), 0) * 100), 2
                        ) as completion_rate,
                        ROUND(
                            (COUNT(DISTINCT CASE WHEN o.status = 'cancelled' THEN o.order_id END) / 
                             NULLIF(COUNT(DISTINCT o.order_id), 0) * 100), 2
                        ) as cancellation_rate,
                        b.created_at as business_registration_date,
                        CASE WHEN b.status = 1 THEN 'Active' ELSE 'Inactive' END as business_status,
                        CASE WHEN b.paymentstatus = 1 THEN 'Paid' ELSE 'Pending' END as payment_status
                    FROM businesses b
                    LEFT JOIN business_types bt ON b.businessType = bt.code
                    LEFT JOIN orders o ON b.business_id = o.business_id {date_filter_orders}
                    WHERE 1=1 {type_filter}
                    GROUP BY b.business_id, b.businessName, b.businessType, bt.type, b.businessCategory, 
                             b.level, b.master, b.city, b.state, b.created_at, b.status, b.paymentstatus
                    ORDER BY total_revenue DESC
                """, orders_date_params + type_params)
                
                business_analytics = cursor.fetchall()
                
                # 2. Grocery Orders Analytics (if included)
                grocery_analytics = []
                if include_grocery:
                    cursor.execute(f"""
                        SELECT 
                            b.business_id,
                            b.businessName,
                            b.businessType,
                            bt.type as business_type_name,
                            b.businessCategory,
                            -- Grocery Revenue Metrics
                            COUNT(DISTINCT go.order_id) as grocery_total_orders,
                            COALESCE(SUM(CASE WHEN go.order_status NOT IN ('cancelled', 'grocery_cancelled') THEN go.total_amount ELSE 0 END), 0) as grocery_gross_merchandise_value,
                            COALESCE(SUM(CASE WHEN go.order_status IN ('delivered', 'completed', 'grocery_delivered', 'grocery_picked_up') THEN go.final_amount ELSE 0 END), 0) as grocery_total_revenue,
                            COALESCE(AVG(CASE WHEN go.order_status IN ('delivered', 'completed', 'grocery_delivered', 'grocery_picked_up') THEN go.final_amount ELSE NULL END), 0) as grocery_average_order_value,
                            COALESCE(SUM(CASE WHEN go.order_status NOT IN ('cancelled', 'grocery_cancelled') THEN go.discount ELSE 0 END), 0) as grocery_total_discounts,
                            -- Complete Grocery Order Status Breakdown
                            COUNT(DISTINCT CASE WHEN go.order_status = 'pending' THEN go.order_id END) as grocery_pending_orders,
                            COUNT(DISTINCT CASE WHEN go.order_status = 'confirmed' THEN go.order_id END) as grocery_confirmed_orders,
                            COUNT(DISTINCT CASE WHEN go.order_status = 'preparing' THEN go.order_id END) as grocery_preparing_orders,
                            COUNT(DISTINCT CASE WHEN go.order_status = 'ready' THEN go.order_id END) as grocery_ready_orders,
                            COUNT(DISTINCT CASE WHEN go.order_status = 'assigned' THEN go.order_id END) as grocery_assigned_orders,
                            COUNT(DISTINCT CASE WHEN go.order_status = 'out_for_delivery' THEN go.order_id END) as grocery_out_for_delivery_orders,
                            COUNT(DISTINCT CASE WHEN go.order_status = 'delivered' THEN go.order_id END) as grocery_delivered_orders,
                            COUNT(DISTINCT CASE WHEN go.order_status = 'completed' THEN go.order_id END) as grocery_completed_orders,
                            COUNT(DISTINCT CASE WHEN go.order_status = 'cancelled' THEN go.order_id END) as grocery_cancelled_orders,
                            COUNT(DISTINCT CASE WHEN go.order_status = 'grocery_delivered' THEN go.order_id END) as grocery_status_delivered_orders,
                            COUNT(DISTINCT CASE WHEN go.order_status = 'grocery_picked_up' THEN go.order_id END) as grocery_picked_up_orders,
                            COUNT(DISTINCT CASE WHEN go.order_status = 'grocery_cancelled' THEN go.order_id END) as grocery_status_cancelled_orders,
                            -- Grocery Order Type Breakdown
                            COUNT(DISTINCT CASE WHEN go.order_type = 'delivery' THEN go.order_id END) as grocery_delivery_orders,
                            COUNT(DISTINCT CASE WHEN go.order_type = 'pickup' THEN go.order_id END) as grocery_pickup_orders,
                            -- Grocery Revenue from completed orders only
                            COALESCE(SUM(CASE WHEN go.order_status IN ('delivered', 'completed', 'grocery_delivered', 'grocery_picked_up') THEN go.final_amount ELSE 0 END), 0) as grocery_actual_revenue,
                            -- Grocery Performance Metrics
                            ROUND(
                                (COUNT(DISTINCT CASE WHEN go.order_status IN ('delivered', 'completed', 'grocery_delivered', 'grocery_picked_up') THEN go.order_id END) / 
                                 NULLIF(COUNT(DISTINCT go.order_id), 0) * 100), 2
                            ) as grocery_completion_rate,
                            ROUND(
                                (COUNT(DISTINCT CASE WHEN go.order_status IN ('cancelled', 'grocery_cancelled') THEN go.order_id END) / 
                                 NULLIF(COUNT(DISTINCT go.order_id), 0) * 100), 2
                            ) as grocery_cancellation_rate
                        FROM businesses b
                        LEFT JOIN business_types bt ON b.businessType = bt.code
                        LEFT JOIN Groceries_orders go ON b.business_id = go.business_id {date_filter_grocery}
                        WHERE 1=1 {type_filter}
                        GROUP BY b.business_id, b.businessName, b.businessType, bt.type, b.businessCategory
                        HAVING grocery_total_orders > 0
                        ORDER BY grocery_total_revenue DESC
                    """, grocery_date_params + type_params)
                    
                    grocery_analytics = cursor.fetchall()
                
                # 3. Enhanced Item Performance Analytics (Simplified)
                cursor.execute(f"""
                    SELECT 
                        menu_item_id,
                        item_name,
                        category,
                        price,
                        business_id,
                        business_name,
                        business_type,
                        total_quantity_sold,
                        total_orders_with_item,
                        total_item_revenue,
                        average_selling_price,
                        RANK() OVER (ORDER BY total_quantity_sold DESC) AS overall_rank,
                        RANK() OVER (PARTITION BY business_type ORDER BY total_quantity_sold DESC) AS rank_in_category
                    FROM (
                        -- Standard restaurant items from order_items
                        SELECT 
                            COALESCE(oi.menu_item_id, oi.product_item_id) AS menu_item_id,
                            COALESCE(CAST(mi.item_name AS CHAR), CAST(gi.item_name AS CHAR), CAST(gp.product_name AS CHAR)) AS item_name,
                            COALESCE(CAST(mi.item_category AS CHAR), CAST(gi.item_category AS CHAR), CAST(gc.category_name AS CHAR), CAST(gp.sub_category AS CHAR)) AS category,
                            COALESCE(mi.selling_price, gi.selling_price, oi.unit_price_snapshot) AS price,
                            b.business_id,
                            b.businessName AS business_name,
                            b.businessType AS business_type,
                            SUM(oi.quantity) AS total_quantity_sold,
                            COUNT(DISTINCT oi.order_id) AS total_orders_with_item,
                            SUM(oi.quantity * COALESCE(mi.selling_price, gi.selling_price, oi.unit_price_snapshot)) AS total_item_revenue,
                            AVG(COALESCE(mi.selling_price, gi.selling_price, oi.unit_price_snapshot)) AS average_selling_price
                        FROM order_items oi
                        INNER JOIN orders o ON oi.order_id = o.order_id
                        INNER JOIN businesses b ON o.business_id = b.business_id
                        LEFT JOIN menuItems mi ON oi.menu_item_id = mi.item_id
                        LEFT JOIN GroceryItems gi ON oi.product_item_id = gi.item_id
                        LEFT JOIN Groceries_Products gp ON oi.product_item_id = gp.product_id
                        LEFT JOIN Groceries_Categories gc ON gp.category_id = gc.category_id
                        WHERE o.status IN ('delivered', 'completed') {date_filter_orders} {type_filter}
                        GROUP BY COALESCE(oi.menu_item_id, oi.product_item_id), COALESCE(CAST(mi.item_name AS CHAR), CAST(gi.item_name AS CHAR), CAST(gp.product_name AS CHAR)), COALESCE(CAST(mi.item_category AS CHAR), CAST(gi.item_category AS CHAR), CAST(gc.category_name AS CHAR), CAST(gp.sub_category AS CHAR)),
                                 mi.selling_price, gi.selling_price, oi.unit_price_snapshot, b.business_id, b.businessName, b.businessType
                        
                        UNION ALL
                        
                        -- Grocery items from Groceries_order_items
                        SELECT 
                            goi.product_id AS menu_item_id,
                            CAST(gp.product_name AS CHAR) AS item_name,
                            COALESCE(CAST(gc.category_name AS CHAR), CAST(gp.sub_category AS CHAR)) AS category,
                            goi.unit_price AS price,
                            b.business_id,
                            b.businessName AS business_name,
                            b.businessType AS business_type,
                            SUM(goi.quantity) AS total_quantity_sold,
                            COUNT(DISTINCT goi.order_id) AS total_orders_with_item,
                            SUM(goi.total_price) AS total_item_revenue,
                            AVG(goi.unit_price) AS average_selling_price
                        FROM Groceries_order_items goi
                        INNER JOIN Groceries_orders go ON goi.order_id = go.order_id
                        INNER JOIN businesses b ON go.business_id = b.business_id
                        LEFT JOIN Groceries_Products gp ON goi.product_id = gp.product_id
                        LEFT JOIN Groceries_Categories gc ON gp.category_id = gc.category_id
                        WHERE go.order_status IN ('delivered', 'completed', 'grocery_delivered', 'grocery_picked_up') {date_filter_grocery} {type_filter}
                        GROUP BY goi.product_id, CAST(gp.product_name AS CHAR), COALESCE(CAST(gc.category_name AS CHAR), CAST(gp.sub_category AS CHAR)), goi.unit_price, b.business_id, b.businessName, b.businessType
                    ) AS item_base
                    ORDER BY total_quantity_sold DESC
                    LIMIT 15
                """, orders_date_params + type_params + grocery_date_params + type_params)
                
                item_analytics = cursor.fetchall()
                
                # 4. Enhanced Platform Summary Statistics
                cursor.execute(f"""
                    SELECT 
                        COUNT(DISTINCT b.business_id) as total_businesses,
                        COUNT(DISTINCT CASE WHEN b.status = 1 THEN b.business_id END) as active_businesses,
                        COUNT(DISTINCT CASE WHEN b.paymentstatus = 1 THEN b.business_id END) as paid_businesses,
                        -- Regular Orders Summary
                        COUNT(DISTINCT o.order_id) as total_orders,
                        COALESCE(SUM(CASE WHEN o.status != 'cancelled' THEN o.total_amount ELSE 0 END), 0) as total_gmv,
                        COALESCE(SUM(CASE WHEN o.status IN ('delivered', 'completed') THEN o.final_amount ELSE 0 END), 0) as total_revenue,
                        COALESCE(SUM(CASE WHEN o.status IN ('delivered', 'completed') THEN o.final_amount ELSE 0 END), 0) as actual_revenue,
                        COALESCE(AVG(CASE WHEN o.status IN ('delivered', 'completed') THEN o.final_amount ELSE NULL END), 0) as platform_aov,
                        COUNT(DISTINCT o.user_id) as unique_customers,
                        -- Order Status Summary
                        COUNT(DISTINCT CASE WHEN o.status = 'pending' THEN o.order_id END) as pending_count,
                        COUNT(DISTINCT CASE WHEN o.status = 'delivered' THEN o.order_id END) as delivered_count,
                        COUNT(DISTINCT CASE WHEN o.status = 'completed' THEN o.order_id END) as completed_count,
                        COUNT(DISTINCT CASE WHEN o.status = 'cancelled' THEN o.order_id END) as cancelled_count
                    FROM businesses b
                    LEFT JOIN orders o ON b.business_id = o.business_id {date_filter_orders}
                    WHERE 1=1 {type_filter}
                """, orders_date_params + type_params)
                
                platform_summary = cursor.fetchone()
                
                # 5. Grocery Platform Summary (if included)
                grocery_platform_summary = None
                if include_grocery:
                    cursor.execute(f"""
                        SELECT 
                            COUNT(DISTINCT go.order_id) as grocery_total_orders,
                            COALESCE(SUM(CASE WHEN go.order_status NOT IN ('cancelled', 'grocery_cancelled') THEN go.total_amount ELSE 0 END), 0) as grocery_total_gmv,
                            COALESCE(SUM(CASE WHEN go.order_status IN ('delivered', 'completed', 'grocery_delivered', 'grocery_picked_up') THEN go.final_amount ELSE 0 END), 0) as grocery_total_revenue,
                            COALESCE(SUM(CASE WHEN go.order_status IN ('delivered', 'completed', 'grocery_delivered', 'grocery_picked_up') THEN go.final_amount ELSE 0 END), 0) as grocery_actual_revenue,
                            COALESCE(AVG(CASE WHEN go.order_status IN ('delivered', 'completed', 'grocery_delivered', 'grocery_picked_up') THEN go.final_amount ELSE NULL END), 0) as grocery_platform_aov,
                            COUNT(DISTINCT go.user_id) as grocery_unique_customers
                        FROM businesses b
                        LEFT JOIN Groceries_orders go ON b.business_id = go.business_id {date_filter_grocery}
                        WHERE 1=1 {type_filter}
                    """, grocery_date_params + type_params)
                    
                    grocery_platform_summary = cursor.fetchone()
                
                # 6. Create grocery analytics mapping
                grocery_data_by_business = {}
                for row in grocery_analytics:
                    business_id = row[0]
                    grocery_data_by_business[business_id] = {
                        'grocery_revenue_metrics': {
                            'total_orders': row[5],
                            'gross_merchandise_value': float(row[6]) if row[6] else 0.0,
                            'total_revenue': float(row[7]) if row[7] else 0.0,
                            'average_order_value': float(row[8]) if row[8] else 0.0,
                            'total_discounts': float(row[9]) if row[9] else 0.0,
                            'actual_revenue': float(row[22]) if row[22] else 0.0
                        },
                        'grocery_order_status_breakdown': {
                            'pending': row[10],
                            'confirmed': row[11],
                            'preparing': row[12],
                            'ready': row[13],
                            'assigned': row[14],
                            'out_for_delivery': row[15],
                            'delivered': row[16],
                            'completed': row[17],
                            'cancelled': row[18],
                            'grocery_delivered': row[19],
                            'grocery_picked_up': row[20],
                            'grocery_cancelled': row[21]
                        },
                        'grocery_order_type_breakdown': {
                            'delivery': row[22],
                            'pickup': row[23]
                        },
                        'grocery_performance_metrics': {
                            'completion_rate': float(row[25]) if row[25] else 0.0,
                            'cancellation_rate': float(row[26]) if row[26] else 0.0
                        }
                    }
                
                # Format enhanced response
                business_performance = []
                for row in business_analytics:
                    business_id = row[0]
                    business_data = {
                        'business_id': business_id,
                        'business_name': row[1],
                        'business_type': row[2],
                        'business_type_name': row[3],
                        'business_category': row[4],
                        'level': row[5],
                        'master': row[6],
                        'city': row[7],
                        'state': row[8],
                        'revenue_metrics': {
                            'total_orders': row[9],
                            'gross_merchandise_value': float(row[10]) if row[10] else 0.0,
                            'total_revenue': float(row[11]) if row[11] else 0.0,
                            'average_order_value': float(row[12]) if row[12] else 0.0,
                            'total_discounts': float(row[13]) if row[13] else 0.0,
                            'total_wallet_savings': float(row[14]) if row[14] else 0.0,
                            'actual_revenue': float(row[31]) if row[31] else 0.0
                        },
                        'order_status_breakdown': {
                            'pending': row[15],
                            'confirmed': row[16],
                            'preparing': row[17],
                            'ready': row[18],
                            'assigned': row[19],
                            'out_for_delivery': row[20],
                            'delivered': row[21],
                            'completed': row[22],
                            'cancelled': row[23],
                            'notified': row[24],
                            'dispatched': row[25],
                            'travelling': row[26]
                        },
                        'order_type_breakdown': {
                            'delivery': row[27],
                            'pickup': row[28],
                            'dine_in': row[29],
                            'takeaway': row[30]
                        },
                        'performance_metrics': {
                            'completion_rate': float(row[32]) if row[32] else 0.0,
                            'cancellation_rate': float(row[33]) if row[33] else 0.0
                        },
                        'business_registration_date': row[34],
                        'business_status': row[35],
                        'payment_status': row[36]
                    }
                    
                    # Add grocery data if available
                    if business_id in grocery_data_by_business:
                        business_data.update(grocery_data_by_business[business_id])
                        
                        # Calculate combined metrics (using actual_revenue for completed orders only)
                        regular_revenue = business_data['revenue_metrics']['actual_revenue']
                        grocery_revenue = business_data['grocery_revenue_metrics']['actual_revenue']
                        business_data['combined_revenue_metrics'] = {
                            'total_revenue': regular_revenue + grocery_revenue,  # This is now actual_revenue (completed orders only)
                            'actual_revenue': regular_revenue + grocery_revenue,
                            'regular_revenue': regular_revenue,
                            'grocery_revenue': grocery_revenue
                        }
                        
                        regular_orders = business_data['revenue_metrics']['total_orders']
                        grocery_orders = business_data['grocery_revenue_metrics']['total_orders']
                        business_data['combined_order_metrics'] = {
                            'total_orders': regular_orders + grocery_orders,
                            'regular_orders': regular_orders,
                            'grocery_orders': grocery_orders
                        }
                    
                    business_performance.append(business_data)
                
                # Enhanced platform summary
                enhanced_platform_summary = {
                    'total_businesses': platform_summary[0],
                    'active_businesses': platform_summary[1],
                    'paid_businesses': platform_summary[2],
                    'regular_orders': {
                        'total_orders': platform_summary[3],
                        'total_gmv': float(platform_summary[4]) if platform_summary[4] else 0.0,
                        'total_revenue': float(platform_summary[5]) if platform_summary[5] else 0.0,
                        'actual_revenue': float(platform_summary[6]) if platform_summary[6] else 0.0,
                        'platform_aov': float(platform_summary[7]) if platform_summary[7] else 0.0,
                        'unique_customers': platform_summary[8],
                        'order_status_summary': {
                            'pending': platform_summary[9],
                            'delivered': platform_summary[10],
                            'completed': platform_summary[11],
                            'cancelled': platform_summary[12]
                        }
                    }
                }
                
                # Add grocery platform summary if included
                if include_grocery and grocery_platform_summary:
                    enhanced_platform_summary['grocery_orders'] = {
                        'total_orders': grocery_platform_summary[0],
                        'total_gmv': float(grocery_platform_summary[1]) if grocery_platform_summary[1] else 0.0,
                        'total_revenue': float(grocery_platform_summary[2]) if grocery_platform_summary[2] else 0.0,
                        'actual_revenue': float(grocery_platform_summary[3]) if grocery_platform_summary[3] else 0.0,
                        'platform_aov': float(grocery_platform_summary[4]) if grocery_platform_summary[4] else 0.0,
                        'unique_customers': grocery_platform_summary[5]
                    }
                    
                    # Combined metrics (using actual_revenue for completed orders only)
                    combined_total_revenue = enhanced_platform_summary['regular_orders']['actual_revenue'] + enhanced_platform_summary['grocery_orders']['actual_revenue']
                    combined_actual_revenue = enhanced_platform_summary['regular_orders']['actual_revenue'] + enhanced_platform_summary['grocery_orders']['actual_revenue']
                    combined_total_orders = enhanced_platform_summary['regular_orders']['total_orders'] + enhanced_platform_summary['grocery_orders']['total_orders']
                    
                    enhanced_platform_summary['combined_metrics'] = {
                        'total_revenue': combined_total_revenue,  # This is now actual_revenue (completed orders only)
                        'actual_revenue': combined_actual_revenue,
                        'total_orders': combined_total_orders,
                        'regular_revenue': enhanced_platform_summary['regular_orders']['actual_revenue'],
                        'grocery_revenue': enhanced_platform_summary['grocery_orders']['actual_revenue']
                    }
                
                return Response({
                    'success': True,
                    'message': 'Enhanced business analytics retrieved successfully',
                    'analytics_period': {
                        'date_from': date_from,
                        'date_to': date_to,
                        'business_type_filter': business_type,
                        'grocery_included': include_grocery
                    },
                    'platform_summary': enhanced_platform_summary,
                    'business_performance': business_performance,
                    'item_performance': [
                        {
                            'menu_item_id': row[0],
                            'item_name': row[1],
                            'category': row[2],
                            'price': float(row[3]) if row[3] else 0.0,
                            'business_id': row[4],
                            'business_name': row[5],
                            'business_type': row[6],
                            'sales_metrics': {
                                'total_quantity_sold': row[7],
                                'total_orders_with_item': row[8],
                                'total_item_revenue': float(row[9]) if row[9] else 0.0,
                                'average_selling_price': float(row[10]) if row[10] else 0.0,
                                'overall_rank': row[11],
                                'rank_in_category': row[12]
                            }
                        } for row in item_analytics
                    ]
                }, status=status.HTTP_200_OK)
                
        except Exception as e:
            logger.error(f"Error retrieving business analytics: {str(e)}")
            return Response({
                'success': False,
                'message': f'Error retrieving business analytics: {str(e)}'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class AdminTestView(APIView):
    """Simple test endpoint to verify admin routes are working"""
    
    def get(self, request):
        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT COUNT(*) FROM businesses")
                count = cursor.fetchone()[0]
                
                return Response({
                    'success': True,
                    'message': 'Admin test endpoint working',
                    'total_businesses': count
                }, status=status.HTTP_200_OK)
                
        except Exception as e:
            logger.error(f"Error in test endpoint: {str(e)}")
            return Response({
                'success': False,
                'message': f'Error in test endpoint: {str(e)}'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class AdminBusinessSimpleView(APIView):
    """Simplified business view with revenue, order statistics, and financial details"""
    
    def get(self, request):
        try:
            page = int(request.GET.get('page', 1))
            limit = min(int(request.GET.get('limit', 20)), 100)
            offset = (page - 1) * limit
            
            # Get filter parameters
            status_filter = request.GET.get('status', '').strip()
            business_type_filter = request.GET.get('business_type', '').strip()
            search_filter = request.GET.get('search', '').strip()
            
            with connection.cursor() as cursor:
                # Build WHERE clause based on filters
                where_clauses = ["b.paymentstatus = 1"]
                params = []
                
                # Status filter
                if status_filter:
                    if status_filter == 'Active':
                        where_clauses.append("b.status = 1")
                    elif status_filter == 'Inactive':
                        where_clauses.append("b.status = 0")
                    elif status_filter == 'Deactivated':
                        where_clauses.append("b.status = 2")
                
                # Business type filter
                if business_type_filter:
                    where_clauses.append("b.businessType = %s")
                    params.append(business_type_filter)
                
                # Search filter (search in business name, email, phone, city)
                if search_filter:
                    where_clauses.append("""(
                        b.businessName LIKE %s OR 
                        b.businessEmail LIKE %s OR 
                        b.businessNumber LIKE %s OR 
                        b.city LIKE %s OR
                        b.business_id LIKE %s
                    )""")
                    search_param = f"%{search_filter}%"
                    params.extend([search_param, search_param, search_param, search_param, search_param])
                
                where_clause = " AND ".join(where_clauses)
                
                # Get all businesses with pagination and filters
                query = f"""
                    SELECT 
                        b.business_id,
                        b.businessName,
                        b.businessType,
                        b.businessCategory,
                        b.businessEmail,
                        b.businessNumber,
                        b.address,
                        b.city,
                        b.state,
                        CASE WHEN b.status = 1 THEN 'Active' WHEN b.status = 2 THEN 'Deactivated' ELSE 'Inactive' END as business_status,
                        CASE WHEN b.paymentstatus = 1 THEN 'Paid' ELSE 'Pending' END as payment_status,
                        b.created_at,
                        b.level,
                        b.master,
                        b.status as status_code
                    FROM businesses b
                    WHERE {where_clause}
                    ORDER BY b.created_at DESC
                    LIMIT %s OFFSET %s
                """
                
                params.extend([limit, offset])
                cursor.execute(query, params)
                
                businesses = cursor.fetchall()
                
                # Get total count with filters
                count_query = f"SELECT COUNT(*) FROM businesses b WHERE {where_clause}"
                cursor.execute(count_query, params[:-2])  # Exclude limit and offset
                total_businesses = cursor.fetchone()[0]
                
                # Get all business IDs for this page
                business_ids = [str(row[0]) for row in businesses]
                
                # Get all master businesses from this page (both 'master' and 'main' levels)
                master_businesses = [row[0] for row in businesses if row[12] in ['master', 'main']]
                
                # Get all sub-businesses for master businesses
                sub_businesses = {}
                if master_businesses:
                    cursor.execute("""
                        SELECT master, GROUP_CONCAT(business_id) as sub_businesses
                        FROM businesses 
                        WHERE master IN %s
                        GROUP BY master
                    """, [tuple(master_businesses)])
                    
                    for master, subs in cursor.fetchall():
                        if subs:
                            sub_businesses[master] = subs.split(',')
                
                # Get financial details for all businesses
                financial_details = {}
                if business_ids:
                    cursor.execute("""
                        SELECT 
                            business_id,
                            owner_pan,
                            gstin,
                            ifsc_code,
                            account_number,
                            razor_pay_key_id,
                            razor_pay_key_code,
                            razor_webhook_secret,
                            fssai_certification_number,
                            created_at,
                            updated_at
                        FROM business_financials
                        WHERE business_id IN %s
                    """, [tuple(business_ids)])
                    
                    for row in cursor.fetchall():
                        financial_details[row[0]] = {
                            'owner_pan': row[1],
                            'gstin': row[2],
                            'ifsc_code': row[3],
                            'account_number': row[4],
                            'razor_pay_key_id': row[5],
                            'razor_pay_key_code': row[6],
                            'razor_webhook_secret': row[7],
                            'fssai_certification_number': row[8],
                            'financial_created_at': row[9],
                            'financial_updated_at': row[10],
                            'has_financial_data': True
                        }
                
                # Get all business IDs for order stats (include sub-businesses)
                all_business_ids = set(business_ids)
                for subs in sub_businesses.values():
                    all_business_ids.update(subs)
                
                # Get standard orders revenue and count by status
                order_stats = {}
                revenue_by_status = {}
                if all_business_ids:
                    # Check if orders table exists
                    cursor.execute("""
                        SELECT 
                            business_id,
                            status,
                            COUNT(*) as order_count,
                            COALESCE(SUM(CASE WHEN status IN ('delivered', 'completed') THEN final_amount ELSE final_amount END), 0) as revenue,
                            COALESCE(SUM(final_amount), 0) as total_amount
                        FROM orders
                        WHERE business_id IN %s
                        GROUP BY business_id, status
                    """, [tuple(all_business_ids)])
                    
                    for biz_id, order_status, count, revenue, total_amount in cursor.fetchall():
                        # Initialize business stats if not exists
                        if biz_id not in order_stats:
                            order_stats[biz_id] = {
                                'order_count': 0,
                                'total_revenue': 0.0,
                                'revenue_by_status': {}
                            }
                        
                        # Update order stats (only count delivered/completed for total_revenue)
                        order_stats[biz_id]['order_count'] += int(count) if count else 0
                        # Only add delivered/completed orders to total_revenue
                        if order_status in ('delivered', 'completed'):
                            order_stats[biz_id]['total_revenue'] += float(revenue) if revenue else 0.0
                        
                        # Track revenue by status
                        if order_status not in order_stats[biz_id]['revenue_by_status']:
                            order_stats[biz_id]['revenue_by_status'][order_status] = {
                                'order_count': 0,
                                'revenue': 0.0,
                                'total_amount': 0.0
                            }
                        
                        order_stats[biz_id]['revenue_by_status'][order_status]['order_count'] += int(count) if count else 0
                        order_stats[biz_id]['revenue_by_status'][order_status]['revenue'] += float(revenue) if revenue else 0.0
                        order_stats[biz_id]['revenue_by_status'][order_status]['total_amount'] += float(total_amount) if total_amount else 0.0
                
                # Get counter orders revenue and count by status
                if all_business_ids:
                    # Check if business_counter_orders table exists
                    cursor.execute("""
                        SELECT 
                            business_id,
                            status,
                            COUNT(*) as order_count,
                            COALESCE(SUM(CASE WHEN status = 'paid' THEN total_amount ELSE total_amount END), 0) as revenue,
                            COALESCE(SUM(total_amount), 0) as total_amount
                        FROM business_counter_orders
                        WHERE business_id IN %s
                        GROUP BY business_id, status
                    """, [tuple(all_business_ids)])
                    
                    for biz_id, counter_status, count, revenue, total_amount in cursor.fetchall():
                        # Initialize business stats if not exists
                        if biz_id not in order_stats:
                            order_stats[biz_id] = {
                                'order_count': 0,
                                'total_revenue': 0.0,
                                'revenue_by_status': {}
                            }
                        
                        # Update order stats (only count paid orders for total_revenue)
                        order_stats[biz_id]['order_count'] += int(count) if count else 0
                        # Only add paid orders to total_revenue
                        if counter_status == 'paid':
                            order_stats[biz_id]['total_revenue'] += float(revenue) if revenue else 0.0
                        
                        # Track revenue by status
                        if counter_status not in order_stats[biz_id]['revenue_by_status']:
                            order_stats[biz_id]['revenue_by_status'][counter_status] = {
                                'order_count': 0,
                                'revenue': 0.0,
                                'total_amount': 0.0
                            }
                        
                        order_stats[biz_id]['revenue_by_status'][counter_status]['order_count'] += int(count) if count else 0
                        order_stats[biz_id]['revenue_by_status'][counter_status]['revenue'] += float(revenue) if revenue else 0.0
                        order_stats[biz_id]['revenue_by_status'][counter_status]['total_amount'] += float(total_amount) if total_amount else 0.0
                
                # Format response with aggregated data
                business_list = []
                for row in businesses:
                    business_id = row[0]
                    is_master = row[12] in ['master', 'main']  # Check both 'master' and 'main' levels
                    
                    # Initialize stats
                    total_orders = 0
                    total_revenue = 0.0
                    
                    # Initialize revenue_by_status for this specific business
                    business_revenue_by_status = {}
                    
                    # Add the business's own revenue_by_status
                    if business_id in order_stats and 'revenue_by_status' in order_stats[business_id]:
                        business_revenue_by_status = order_stats[business_id]['revenue_by_status'].copy()
                    
                    # For master businesses, include sub-business stats in orders and revenue_by_status only
                    if is_master and business_id in sub_businesses:
                        for sub_id in sub_businesses[business_id]:
                            if sub_id in order_stats:
                                total_orders += order_stats[sub_id]['order_count']
                                # Don't add sub-business revenue to master's total_revenue
                                # total_revenue += order_stats[sub_id]['total_revenue']  # REMOVED THIS LINE
                                
                                # Merge sub-business revenue_by_status
                                if 'revenue_by_status' in order_stats[sub_id]:
                                    for status_name, stats in order_stats[sub_id]['revenue_by_status'].items():
                                        if status_name not in business_revenue_by_status:
                                            business_revenue_by_status[status_name] = {
                                                'order_count': 0,
                                                'revenue': 0.0,
                                                'total_amount': 0.0
                                            }
                                        business_revenue_by_status[status_name]['order_count'] += stats['order_count']
                                        business_revenue_by_status[status_name]['revenue'] += stats['revenue']
                                        business_revenue_by_status[status_name]['total_amount'] += stats['total_amount']
                    
                    # Add the business's own stats (not sub-businesses for master)
                    if business_id in order_stats:
                        total_orders += order_stats[business_id]['order_count']
                        # For master businesses, only add their own revenue, not sub-businesses
                        if is_master:
                            # Master businesses only add their own delivered/completed/paid revenue
                            if 'revenue_by_status' in order_stats[business_id]:
                                master_revenue = 0.0
                                for status_name, stats in order_stats[business_id]['revenue_by_status'].items():
                                    if status_name in ('delivered', 'completed', 'paid'):
                                        master_revenue += stats['revenue']
                                total_revenue += master_revenue
                        else:
                            # Sub-businesses add their own revenue
                            total_revenue += order_stats[business_id]['total_revenue']
                    
                    # Get financial details for this business
                    financial_data = financial_details.get(business_id, {
                        'owner_pan': None,
                        'gstin': None,
                        'ifsc_code': None,
                        'account_number': None,
                        'razor_pay_key_id': None,
                        'razor_pay_key_code': None,
                        'razor_webhook_secret': None,
                        'fssai_certification_number': None,
                        'financial_created_at': None,
                        'financial_updated_at': None,
                        'has_financial_data': False
                    })
                    
                    business_list.append({
                        'business_id': business_id,
                        'businessName': row[1],
                        'businessType': row[2],
                        'businessCategory': row[3],
                        'businessEmail': row[4],
                        'businessNumber': row[5],
                        'address': row[6],
                        'city': row[7],
                        'state': row[8],
                        'status': row[9],
                        'payment_status': row[10],
                        'created_at': row[11],
                        'level': row[12],
                        'master': row[13],
                        'status_code': row[14],
                        'total_orders': total_orders,
                        'total_revenue': round(total_revenue, 2),
                        'revenue_by_status': dict(business_revenue_by_status) if business_revenue_by_status else {},
                        'is_master': is_master,
                        'has_subs': business_id in sub_businesses,
                        'financial_details': financial_data
                    })
                
                total_pages = (total_businesses + limit - 1) // limit
                
                return Response({
                    'success': True,
                    'message': 'Business data retrieved successfully',
                    'pagination': {
                        'total_businesses': total_businesses,
                        'current_page': page,
                        'per_page': limit,
                        'total_pages': total_pages,
                        'has_next_page': page < total_pages,
                        'has_prev_page': page > 1
                    },
                    'businesses': business_list
                }, status=status.HTTP_200_OK)
                
        except Exception as e:
            logger.error(f"Error retrieving businesses: {str(e)}", exc_info=True)
            return Response({
                'success': False,
                'message': f'Error retrieving businesses: {str(e)}'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


# ============================================================================
# CONTACT US SERVICE
# ============================================================================

class ContactUsView(APIView):
    """
    Contact Us service for handling customer inquiries
    POST /api/v1/admin/contact-us - Submit contact form
    """
    permission_classes = []  # Public endpoint
    
    def post(self, request):
        """Submit contact us form"""
        try:
            data = request.data
            
            # Validate required fields
            required_fields = ['firstName', 'lastName', 'emailID', 'phoneNumber', 'subject', 'message']
            missing_fields = [field for field in required_fields if not data.get(field)]
            
            if missing_fields:
                return Response({
                    'success': False,
                    'error': f'Missing required fields: {", ".join(missing_fields)}'
                }, status=status.HTTP_400_BAD_REQUEST)
            
            # Validate email format
            email = data.get('emailID', '').strip()
            if '@' not in email or '.' not in email:
                return Response({
                    'success': False,
                    'error': 'Invalid email format'
                }, status=status.HTTP_400_BAD_REQUEST)
            
            # Create contact us record
            contact_us = BusinessContactUs.objects.create(
                firstName=data.get('firstName', '').strip(),
                lastName=data.get('lastName', '').strip(),
                emailID=email,
                phoneNumber=data.get('phoneNumber', '').strip(),
                subject=data.get('subject', '').strip(),
                message=data.get('message', '').strip()
            )
            
            # Send email notification to admin
            try:
                self._send_admin_notification(contact_us)
                email_sent = True
            except Exception as e:
                logger.error(f"Failed to send admin notification email: {str(e)}")
                email_sent = False
            
            # Send confirmation email to user
            try:
                self._send_user_confirmation(contact_us)
                user_email_sent = True
            except Exception as e:
                logger.error(f"Failed to send user confirmation email: {str(e)}")
                user_email_sent = False
            
            return Response({
                'success': True,
                'message': 'Contact form submitted successfully',
                'data': {
                    'contact_id': contact_us.id,
                    'submitted_at': contact_us.created_at.isoformat(),
                    'admin_email_sent': email_sent,
                    'confirmation_email_sent': user_email_sent
                }
            }, status=status.HTTP_201_CREATED)
            
        except Exception as e:
            logger.error(f"Error submitting contact form: {str(e)}")
            return Response({
                'success': False,
                'error': 'Failed to submit contact form. Please try again.'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    
    def _send_admin_notification(self, contact_us):
        """Send email notification to admin"""
        subject = f"New Contact Us Inquiry - {contact_us.subject}"
        
        # HTML email template
        html_message = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8">
            <style>
                body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
                .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
                .header {{ background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; padding: 20px; text-align: center; border-radius: 8px 8px 0 0; }}
                .content {{ background: #f9f9f9; padding: 30px; border-radius: 0 0 8px 8px; }}
                .field {{ margin-bottom: 15px; }}
                .label {{ font-weight: bold; color: #555; }}
                .value {{ margin-top: 5px; padding: 10px; background: white; border-left: 4px solid #667eea; }}
                .message-box {{ background: white; padding: 15px; border-radius: 5px; border: 1px solid #ddd; }}
                .footer {{ text-align: center; margin-top: 20px; color: #666; font-size: 12px; }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h1>🔔 New Contact Us Inquiry</h1>
                    <p>Kirazee Customer Support</p>
                </div>
                <div class="content">
                    <div class="field">
                        <div class="label">👤 Customer Name:</div>
                        <div class="value">{contact_us.full_name}</div>
                    </div>
                    
                    <div class="field">
                        <div class="label">📧 Email Address:</div>
                        <div class="value">{contact_us.emailID}</div>
                    </div>
                    
                    <div class="field">
                        <div class="label">📱 Phone Number:</div>
                        <div class="value">{contact_us.phoneNumber}</div>
                    </div>
                    
                    <div class="field">
                        <div class="label">📋 Subject:</div>
                        <div class="value">{contact_us.subject}</div>
                    </div>
                    
                    <div class="field">
                        <div class="label">💬 Message:</div>
                        <div class="message-box">{contact_us.message}</div>
                    </div>
                    
                    <div class="field">
                        <div class="label">🕒 Submitted At:</div>
                        <div class="value">{contact_us.created_at.strftime('%B %d, %Y at %I:%M %p')}</div>
                    </div>
                </div>
                <div class="footer">
                    <p>This inquiry was submitted through the Kirazee contact form.</p>
                    <p>Please respond promptly to maintain customer satisfaction.</p>
                </div>
            </div>
        </body>
        </html>
        """
        
        # Plain text version
        plain_message = f"""
        New Contact Us Inquiry - Kirazee
        
        Customer Name: {contact_us.full_name}
        Email: {contact_us.emailID}
        Phone: {contact_us.phoneNumber}
        Subject: {contact_us.subject}
        
        Message:
        {contact_us.message}
        
        Submitted At: {contact_us.created_at.strftime('%B %d, %Y at %I:%M %p')}
        """
        
        # send_mail(
        #     subject=subject,
        #     message=plain_message,
        #     from_email=getattr(settings, 'EMAIL_HOST_USER', 'kirazee@zdotapps.com'),
        #     recipient_list=['kirazee@zdotapps.com'],
        #     html_message=html_message,
        #     fail_silently=False
        # )
    
    def _send_user_confirmation(self, contact_us):
        """Send confirmation email to user"""
        subject = "Thank you for contacting Kirazee - We've received your inquiry"
        
        # HTML confirmation email
        html_message = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8">
            <style>
                body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
                .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
                .header {{ background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; padding: 20px; text-align: center; border-radius: 8px 8px 0 0; }}
                .content {{ background: #f9f9f9; padding: 30px; border-radius: 0 0 8px 8px; }}
                .highlight {{ background: white; padding: 15px; border-radius: 5px; border-left: 4px solid #667eea; margin: 15px 0; }}
                .footer {{ text-align: center; margin-top: 20px; color: #666; font-size: 12px; }}
                .button {{ display: inline-block; padding: 12px 24px; background: #667eea; color: white; text-decoration: none; border-radius: 5px; margin: 10px 0; }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h1>Thank You for Contacting Us!</h1>
                    <p>Kirazee Support Team</p>
                </div>
                <div class="content">
                    <p>Dear {contact_us.firstName},</p>
                    
                    <p>Thank you for reaching out to Kirazee! We have successfully received your inquiry and our team will review it shortly.</p>
                    
                    <div class="highlight">
                        <strong>📋 Your Inquiry Details:</strong><br>
                        <strong>Subject:</strong> {contact_us.subject}<br>
                        <strong>Submitted:</strong> {contact_us.created_at.strftime('%B %d, %Y at %I:%M %p')}<br>
                        <strong>Reference ID:</strong> #{contact_us.id}
                    </div>
                    
                    <p>🕒 <strong>Response Time:</strong> We typically respond within 24-48 hours during business days.</p>
                    
                    <p>📧 <strong>Next Steps:</strong> Our support team will review your message and get back to you at {contact_us.emailID} with a detailed response.</p>
                    
                    <p>If you have any urgent concerns, please don't hesitate to call our support line.</p>
                    
                    <p>Thank you for choosing Kirazee!</p>
                    
                    <p>Best regards,<br>
                    <strong>The Kirazee Team</strong></p>
                </div>
                <div class="footer">
                    <p>This is an automated confirmation email.</p>
                    <p>© 2024 Kirazee. All rights reserved.</p>
                </div>
            </div>
        </body>
        </html>
        """
        
        # Plain text version
        plain_message = f"""
        Thank you for contacting Kirazee!
        
        Dear {contact_us.firstName},
        
        We have successfully received your inquiry about "{contact_us.subject}".
        
        Reference ID: #{contact_us.id}
        Submitted: {contact_us.created_at.strftime('%B %d, %Y at %I:%M %p')}
        
        Our team will review your message and respond within 24-48 hours during business days.
        
        Thank you for choosing Kirazee!
        
        Best regards,
        The Kirazee Team
        """
        
        send_mail(
            subject=subject,
            message=plain_message,
            from_email=getattr(settings, 'EMAIL_HOST_USER', 'teamkirazee@gmail.com'),
            recipient_list=[contact_us.emailID],
            html_message=html_message,
            fail_silently=False
        )


class ContactUsManagementView(APIView):
    """
    Admin service for managing contact us requests
    GET /api/v1/admin/contact-us/manage - List all contact requests with filtering
    """
    permission_classes = []  # Add authentication as needed
    
    def get(self, request):
        """List all contact us requests with filtering and pagination"""
        try:
            # Get query parameters
            page = int(request.query_params.get('page', 1))
            limit = min(int(request.query_params.get('limit', 20)), 100)
            offset = (page - 1) * limit
            
            # Filter parameters
            status_filter = request.query_params.get('status')  # 'resolved', 'pending'
            search_query = request.query_params.get('search')
            date_from = request.query_params.get('date_from')
            date_to = request.query_params.get('date_to')
            
            # Build queryset
            queryset = BusinessContactUs.objects.all()
            
            # Apply filters
            if status_filter == 'resolved':
                queryset = queryset.filter(is_resolved=True)
            elif status_filter == 'pending':
                queryset = queryset.filter(is_resolved=False)
            
            if search_query:
                queryset = queryset.filter(
                    models.Q(firstName__icontains=search_query) |
                    models.Q(lastName__icontains=search_query) |
                    models.Q(emailID__icontains=search_query) |
                    models.Q(subject__icontains=search_query) |
                    models.Q(message__icontains=search_query)
                )
            
            if date_from:
                from datetime import datetime
                date_from_obj = datetime.strptime(date_from, '%Y-%m-%d')
                queryset = queryset.filter(created_at__gte=date_from_obj)
            
            if date_to:
                from datetime import datetime
                date_to_obj = datetime.strptime(date_to, '%Y-%m-%d')
                queryset = queryset.filter(created_at__lte=date_to_obj)
            
            # Get total count
            total_count = queryset.count()
            total_pages = (total_count + limit - 1) // limit
            
            # Apply pagination
            contact_requests = queryset[offset:offset + limit]
            
            # Serialize data
            requests_data = []
            for contact in contact_requests:
                requests_data.append({
                    'id': contact.id,
                    'firstName': contact.firstName,
                    'lastName': contact.lastName,
                    'full_name': contact.full_name,
                    'emailID': contact.emailID,
                    'phoneNumber': contact.phoneNumber,
                    'subject': contact.subject,
                    'message': contact.message,
                    'created_at': contact.created_at.isoformat(),
                    'is_resolved': contact.is_resolved,
                    'admin_notes': contact.admin_notes,
                    'days_ago': (timezone.now() - contact.created_at).days
                })
            
            return Response({
                'success': True,
                'data': {
                    'pagination': {
                        'current_page': page,
                        'total_count': total_count,
                        'total_pages': total_pages,
                        'has_next_page': page < total_pages,
                        'has_prev_page': page > 1,
                        'limit': limit
                    },
                    'filters': {
                        'status': status_filter,
                        'search': search_query,
                        'date_from': date_from,
                        'date_to': date_to
                    },
                    'summary': {
                        'total_requests': BusinessContactUs.objects.count(),
                        'pending_requests': BusinessContactUs.objects.filter(is_resolved=False).count(),
                        'resolved_requests': BusinessContactUs.objects.filter(is_resolved=True).count()
                    },
                    'requests': requests_data
                }
            }, status=status.HTTP_200_OK)
            
        except Exception as e:
            logger.error(f"Error retrieving contact requests: {str(e)}")
            return Response({
                'success': False,
                'error': 'Failed to retrieve contact requests'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class ContactUsReplyView(APIView):
    """
    Admin service for replying to contact us requests
    POST /api/v1/admin/contact-us/<int:contact_id>/reply - Reply to a contact request
    """
    permission_classes = []  # Add authentication as needed
    
    def post(self, request, contact_id):
        """Reply to a contact us request with admin notes"""
        try:
            # Get the contact request
            try:
                contact_us = BusinessContactUs.objects.get(id=contact_id)
            except BusinessContactUs.DoesNotExist:
                return Response({
                    'success': False,
                    'error': 'Contact request not found'
                }, status=status.HTTP_404_NOT_FOUND)
            
            data = request.data
            admin_notes = data.get('admin_notes', '').strip()
            
            if not admin_notes:
                return Response({
                    'success': False,
                    'error': 'Admin notes are required'
                }, status=status.HTTP_400_BAD_REQUEST)
            
            # Update the contact request
            contact_us.admin_notes = admin_notes
            contact_us.is_resolved = True
            contact_us.save()
            
            # Send reply email to user
            try:
                self._send_admin_reply_email(contact_us, admin_notes)
                email_sent = True
            except Exception as e:
                logger.error(f"Failed to send admin reply email: {str(e)}")
                email_sent = False
            
            return Response({
                'success': True,
                'message': 'Reply sent successfully',
                'data': {
                    'contact_id': contact_us.id,
                    'is_resolved': contact_us.is_resolved,
                    'admin_notes': contact_us.admin_notes,
                    'email_sent': email_sent,
                    'replied_at': timezone.now().isoformat()
                }
            }, status=status.HTTP_200_OK)
            
        except Exception as e:
            logger.error(f"Error sending reply: {str(e)}")
            return Response({
                'success': False,
                'error': 'Failed to send reply'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    
    def _send_admin_reply_email(self, contact_us, admin_notes):
        """Send admin reply email to user"""
        subject = f"Re: {contact_us.subject} - Response from Kirazee Support"
        
        # HTML reply email template
        html_message = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8">
            <style>
                body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
                .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
                .header {{ background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; padding: 20px; text-align: center; border-radius: 8px 8px 0 0; }}
                .content {{ background: #f9f9f9; padding: 30px; border-radius: 0 0 8px 8px; }}
                .original-inquiry {{ background: #e8f4f8; padding: 15px; border-radius: 5px; border-left: 4px solid #17a2b8; margin: 15px 0; }}
                .admin-response {{ background: white; padding: 20px; border-radius: 5px; border-left: 4px solid #28a745; margin: 15px 0; }}
                .footer {{ text-align: center; margin-top: 20px; color: #666; font-size: 12px; }}
                .highlight {{ background: #fff3cd; padding: 10px; border-radius: 5px; border-left: 4px solid #ffc107; margin: 10px 0; }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h1>📧 Response from Kirazee Support</h1>
                    <p>Your inquiry has been resolved</p>
                </div>
                <div class="content">
                    <p>Dear {contact_us.firstName},</p>
                    
                    <p>Thank you for your patience. We have reviewed your inquiry and are pleased to provide you with a response.</p>
                    
                    <div class="original-inquiry">
                        <strong>📋 Your Original Inquiry:</strong><br>
                        <strong>Subject:</strong> {contact_us.subject}<br>
                        <strong>Submitted:</strong> {contact_us.created_at.strftime('%B %d, %Y at %I:%M %p')}<br>
                        <strong>Reference ID:</strong> #{contact_us.id}<br><br>
                        <strong>Your Message:</strong><br>
                        <em>"{contact_us.message}"</em>
                    </div>
                    
                    <div class="admin-response">
                        <strong>✅ Our Response:</strong><br><br>
                        {admin_notes.replace(chr(10), '<br>')}
                    </div>
                    
                    <div class="highlight">
                        <strong>🎯 Status:</strong> Your inquiry has been marked as <strong>RESOLVED</strong>
                    </div>
                    
                    <p>If you have any follow-up questions or need further assistance, please don't hesitate to contact us again.</p>
                    
                    <p>Thank you for choosing Kirazee!</p>
                    
                    <p>Best regards,<br>
                    <strong>The Kirazee Support Team</strong></p>
                </div>
                <div class="footer">
                    <p>This response was sent by the Kirazee support team.</p>
                    <p>© 2024 Kirazee. All rights reserved.</p>
                </div>
            </div>
        </body>
        </html>
        """
        
        # Plain text version
        plain_message = f"""
        Response from Kirazee Support
        
        Dear {contact_us.firstName},
        
        Thank you for your patience. We have reviewed your inquiry and are pleased to provide you with a response.
        
        Your Original Inquiry:
        Subject: {contact_us.subject}
        Submitted: {contact_us.created_at.strftime('%B %d, %Y at %I:%M %p')}
        Reference ID: #{contact_us.id}
        
        Your Message:
        "{contact_us.message}"
        
        Our Response:
        {admin_notes}
        
        Status: Your inquiry has been marked as RESOLVED
        
        If you have any follow-up questions or need further assistance, please don't hesitate to contact us again.
        
        Thank you for choosing Kirazee!
        
        Best regards,
        The Kirazee Support Team
        """
        
        send_mail(
            subject=subject,
            message=plain_message,
            from_email=getattr(settings, 'EMAIL_HOST_USER', 'teamkirazee@gmail.com'),
            recipient_list=[contact_us.emailID],
            html_message=html_message,
            fail_silently=False
        )