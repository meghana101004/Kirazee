# delivery_partner/views.py
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework_simplejwt.authentication import JWTAuthentication
from geopy.distance import geodesic
from django.db import connection, transaction
from datetime import datetime, timedelta
from drf_yasg.utils import swagger_auto_schema

from consumer.models import Orders, Payments, create_status_log
from consumer.gro_models import GroceriesOrders
from kirazee_app.models import Business, Registration
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
    DeliveryOrderSerializer, DeliveryPartnerRegistrationSerializer
)
from django.conf import settings
from django.core.mail import send_mail
from django.core.cache import cache
from django.utils import timezone
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync
from urllib.parse import urljoin
from types import SimpleNamespace
from django.urls import get_script_prefix
from decimal import Decimal
from dateutil import parser as date_parser
import json
import re
import logging
from delivery.image_utils import build_s3_file_url

logger = logging.getLogger(__name__)
from notifications.hooks import on_order_status, on_otp_sent
from notifications.service import send_order_notification

def calculate_distance(lat1, lon1, lat2, lon2):
    """
    Calculate the great circle distance between two points 
    on the earth (specified in decimal degrees) using Haversine formula
    Returns distance in kilometers
    """
    if not all([lat1, lon1, lat2, lon2]):
        return 0.0
    
    import math
    
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

class DeliveryPartnerMixin:
    def get_delivery_partner(self, user):
        # Check if user is authenticated
        if not user.is_authenticated:
            return None
        try:
            return DeliveryPartner.objects.get(user=user)
        except DeliveryPartner.DoesNotExist:
            return None


class GroceryOrdersService:
    """
    Service class to handle order operations across multiple tables using raw SQL
    """

    @staticmethod
    def _get_order_items_sql(business_type):
        if business_type == 'R02':
            return """
                SELECT
                    i.item_id                       AS item_id,
                    i.menu_item_id                  AS product_id,
                    COALESCE(mi.item_name, i.item_name_snapshot)           AS item_name,
                    i.quantity                      AS quantity,
                    i.unit_price_snapshot           AS unit_price,
                    i.total_price                   AS total_price,
                    mi.item_image                   AS item_image,
                    mi.description                  AS description,
                    mi.item_category                AS item_category,
                    mi.item_type                    AS item_type,
                    mi.gst                          AS gst,
                    mi.charges                      AS charges,
                    i.customizations                AS customizations
                FROM order_items i
                LEFT JOIN menuItems mi ON i.menu_item_id = mi.item_id
                WHERE i.order_id = %s
            """

        if business_type == 'R01':
            return """
                SELECT
                    i.item_id                       AS item_id,
                    i.product_item_id               AS product_id,
                    COALESCE(gi.item_name, i.item_name_snapshot)          AS item_name,
                    i.quantity                      AS quantity,
                    i.unit_price_snapshot           AS unit_price,
                    i.total_price                   AS total_price,
                    gi.item_image                   AS item_image,
                    gi.description                  AS description,
                    gi.item_category                AS item_category,
                    gi.item_type                    AS item_type,
                    gi.gst                          AS gst,
                    gi.charges                      AS charges,
                    i.customizations                AS customizations
                FROM order_items i
                LEFT JOIN GroceryItems gi ON i.product_item_id = gi.item_id
                WHERE i.order_id = %s
            """

        if business_type == 'R08':
            return """
                SELECT
                    i.item_id                                           AS item_id,
                    i.product_item_id                                   AS product_id,
                    i.product_item_id                                   AS variant_id,
                    fp.product_id                                       AS fashion_product_id,
                    COALESCE(fp.name, i.item_name_snapshot)             AS item_name,
                    i.quantity                                          AS quantity,
                    i.unit_price_snapshot                               AS unit_price,
                    i.total_price                                       AS total_price,
                    fp.main_image                                       AS item_image,
                    fp.description                                      AS description,
                    uc.category_name                                    AS item_category,
                    fp.subcategory_id                                   AS sub_category,
                    'fashion'                                           AS item_type,
                    fp.gst_rate_default                                 AS gst,
                    fpv.charges                                         AS charges,
                    fp.brand                                            AS brand_name,
                    fp.rating                                           AS rating,
                    0                                                   AS is_organic,
                    i.customizations                                    AS customizations
                FROM order_items i
                LEFT JOIN fashion_product_variants fpv ON i.product_item_id = fpv.variant_id
                LEFT JOIN fashion_products fp ON fpv.product_id = fp.product_id
                LEFT JOIN universal_Categories uc ON fp.category_id = uc.category_id
                WHERE i.order_id = %s
            """

        return """
            SELECT
                i.item_id                                                                      AS item_id,
                COALESCE(i.menu_item_id, i.product_item_id)                                    AS product_id,
                i.product_item_id                                                               AS variant_id,
                fp.product_id                                                                   AS fashion_product_id,
                COALESCE(mi.item_name, gi.item_name, fp.name, i.item_name_snapshot)             AS item_name,
                i.quantity                                                                     AS quantity,
                i.unit_price_snapshot                                                          AS unit_price,
                i.total_price                                                                  AS total_price,
                COALESCE(mi.item_image, gi.item_image, fp.main_image)                           AS item_image,
                COALESCE(mi.description, gi.description, fp.description)                         AS description,
                COALESCE(mi.item_category, gi.item_category, uc.category_name)                  AS item_category,
                COALESCE(mi.item_type, gi.item_type, 'fashion')                                 AS item_type,
                COALESCE(mi.gst, gi.gst, fp.gst_rate_default)                                    AS gst,
                COALESCE(mi.charges, gi.charges, fpv.charges)                                    AS charges,
                fp.subcategory_id                                                               AS sub_category,
                fp.brand                                                                        AS brand_name,
                fp.rating                                                                       AS rating,
                0                                                                               AS is_organic,
                i.customizations                                                                AS customizations
            FROM order_items i
            LEFT JOIN menuItems mi   ON i.menu_item_id    = mi.item_id
            LEFT JOIN GroceryItems gi ON i.product_item_id = gi.item_id
            LEFT JOIN fashion_product_variants fpv ON i.product_item_id = fpv.variant_id
            LEFT JOIN fashion_products fp ON fpv.product_id = fp.product_id
            LEFT JOIN universal_Categories uc ON fp.category_id = uc.category_id
            WHERE i.order_id = %s
        """

    @staticmethod
    def attach_items_preview_to_standard_orders(orders, max_items=3):
        if not orders:
            return

        order_ids = [o.get('order_id') for o in orders if o.get('order_id') is not None]
        if not order_ids:
            return

        placeholders = ','.join(['%s'] * len(order_ids))
        sql = f"""
            SELECT
                i.order_id AS order_id,
                COALESCE(mi.item_name, gi.item_name, fp.name, i.item_name_snapshot) AS item_name,
                COALESCE(mi.item_image, gi.item_image, fp.main_image) AS item_image,
                i.quantity AS quantity,
                COALESCE(mi.item_type, gi.item_type, 'fashion') AS item_type
            FROM order_items i
            LEFT JOIN menuItems mi ON i.menu_item_id = mi.item_id
            LEFT JOIN GroceryItems gi ON i.product_item_id = gi.item_id
            LEFT JOIN fashion_product_variants fpv ON i.product_item_id = fpv.variant_id
            LEFT JOIN fashion_products fp ON fpv.product_id = fp.product_id
            WHERE i.order_id IN ({placeholders})
            ORDER BY i.order_id, i.item_id
        """

        preview_map = {}
        try:
            with connection.cursor() as cursor:
                cursor.execute(sql, order_ids)
                for oid, name, image, qty, item_type in cursor.fetchall():
                    bucket = preview_map.setdefault(oid, [])
                    if len(bucket) >= max_items:
                        continue
                    bucket.append({
                        'name': name,
                        'image': image,
                        'quantity': int(qty) if qty is not None else None,
                        'item_type': item_type,
                    })
        except Exception as exc:
            logger.error(f"Failed to fetch standard order items preview: {exc}")
            return

        for o in orders:
            o['items_preview'] = preview_map.get(o.get('order_id'), [])

    @staticmethod
    def attach_items_preview_to_grocery_orders(orders, max_items=3):
        if not orders:
            return

        order_ids = [o.get('order_id') for o in orders if o.get('order_id') is not None]
        if not order_ids:
            return

        placeholders = ','.join(['%s'] * len(order_ids))
        sql = f"""
            SELECT
                oi.order_id AS order_id,
                p.product_name AS item_name,
                p.main_image AS item_image,
                oi.quantity AS quantity
            FROM Groceries_order_items oi
            LEFT JOIN Groceries_Products p ON oi.product_id = p.product_id
            WHERE oi.order_id IN ({placeholders})
            ORDER BY oi.order_id, oi.order_item_id
        """

        preview_map = {}
        try:
            with connection.cursor() as cursor:
                cursor.execute(sql, order_ids)
                for oid, name, image, qty in cursor.fetchall():
                    bucket = preview_map.setdefault(oid, [])
                    if len(bucket) >= max_items:
                        continue
                    bucket.append({
                        'name': name,
                        'image': image,
                        'quantity': int(qty) if qty is not None else None,
                        'item_type': 'grocery',
                    })
        except Exception as exc:
            logger.error(f"Failed to fetch grocery order items preview: {exc}")
            return

        for o in orders:
            o['items_preview'] = preview_map.get(o.get('order_id'), [])

    @staticmethod
    def get_order_details_with_user(order_id):
        """
        Fetch order details along with user information using raw SQL.
        First checks `orders`, then falls back to `Groceries_orders`.
        Returns None when the order is not found in either table.
        """
        with connection.cursor() as cursor:
            # ------------------------------------------------------------------
            # Step 1: Try fetching from `orders`
            # ------------------------------------------------------------------
            standard_order_sql = """
                SELECT
                    o.order_id                          AS order_id,
                    o.order_number                      AS order_number,
                    o.user_id                           AS user_id,
                    o.business_id                       AS business_id,
                    o.total_amount                      AS total_amount,
                    o.final_amount                      AS final_amount,
                    o.status                            AS status,
                    'pending'                           AS payment_status,
                    o.created_at                        AS created_at,
                    o.updated_at                        AS updated_at,
                    o.scheduled_time                    AS scheduled_time,
                    JSON_UNQUOTE(JSON_EXTRACT(o.delivery_address_snapshot, '$.address'))      AS delivery_address,
                    COALESCE(CAST(o.delivery_instruction AS CHAR), JSON_UNQUOTE(JSON_EXTRACT(o.delivery_address_snapshot, '$.instructions'))) AS delivery_instructions,
                    o.delivery_charges                  AS delivery_charges,
                    o.parcel_charges                    AS parcel_charges,
                    o.discount_amount                   AS discount,
                    o.estimated_delivery_time           AS estimated_delivery_time,
                    o.order_type                        AS order_type,
                    b.businessName                      AS business_name,
                    b.businessType                      AS business_type,
                    b.address                           AS business_address,
                    b.location                          AS business_location,
                    b.landmark                          AS business_landmark,
                    b.city                              AS business_city,
                    b.state                             AS business_state,
                    b.pincode                           AS business_pincode,
                    b.latitude                          AS business_latitude,
                    b.longitude                         AS business_longitude,
                    b.businessNumber                    AS business_phone,
                    b.contact_mobile                    AS business_contact_mobile,
                    b.contact_support                   AS business_contact_support,
                    b.businessWhatsapp                  AS business_whatsapp,
                    b.business_hours                    AS business_hours_json,
                    b.status                            AS business_status,
                    o.token_num                         AS token_num,
                    r.firstName                         AS first_name,
                    r.lastName                          AS last_name,
                    r.displayName                       AS display_name,
                    r.mobileNumber                      AS phone_number,
                    r.emailID                           AS email,
                    r.profileUrl                        AS profile_image,
                    'orders'                            AS source_table,
                    -- Company/B2B Details
                    o.order_customer_type,
                    o.company_id,
                    o.ordered_by_employee,
                    o.approval_status,
                    o.company_notes,
                    o.company_department,
                    o.company_purchase_order,
                    o.is_bulk_order,
                    o.bulk_order_reference,
                    cr.company_name,
                    cr.gst_number
                FROM orders o
                LEFT JOIN businesses b   ON o.business_id = b.business_id
                LEFT JOIN registrations r ON o.user_id     = r.user_id
                LEFT JOIN user_address ua ON o.delivery_address_id = ua.id
                LEFT JOIN company_registrations cr ON o.company_id = cr.company_id
                WHERE o.order_id = %s
                LIMIT 1
            """

            cursor.execute(standard_order_sql, [order_id])
            standard_row = cursor.fetchone()

            if standard_row:
                standard_columns = [col[0] for col in cursor.description]
                order = dict(zip(standard_columns, standard_row))

                try:
                    # Default payment method when not available
                    order['payment_method'] = 'N/A'
                    cursor.execute(
                        """
                        SELECT p.status, p.payment_method
                        FROM payments p
                        WHERE p.order_id = %s
                        ORDER BY p.created_at DESC, p.id DESC
                        LIMIT 1
                        """,
                        [order_id]
                    )
                    pay = cursor.fetchone()
                    if pay:
                        if pay[0]:
                            order['payment_status'] = pay[0]
                        if len(pay) > 1 and pay[1]:
                            order['payment_method'] = pay[1]
                except Exception:
                    # If anything goes wrong, keep existing value (defaults to 'pending')
                    pass

                items_sql = GroceryOrdersService._get_order_items_sql(order.get('business_type'))
                cursor.execute(items_sql, [order_id])
                item_columns = [col[0] for col in cursor.description]
                order['items'] = [dict(zip(item_columns, item_row)) for item_row in cursor.fetchall()]

                return order

            # ------------------------------------------------------------------
            # Step 2: Try fetching from `Groceries_orders`
            # ------------------------------------------------------------------
            grocery_order_sql = """
                SELECT
                    go.order_id                        AS order_id,
                    CONCAT('GROC-', go.order_id)       AS order_number,
                    go.user_id                         AS user_id,
                    go.business_id                     AS business_id,
                    go.total_amount                    AS total_amount,
                    go.final_amount                    AS final_amount,
                    go.order_status                    AS status,
                    go.payment_status                  AS payment_status,
                    go.gst_amount                      AS gst_amount,
                    go.created_at                      AS created_at,
                    go.updated_at                      AS updated_at,
                    go.delivery_address                AS delivery_address,
                    COALESCE(go.delivery_instructions, '') AS delivery_instructions,
                    go.delivery_charge                 AS delivery_charges,
                    go.discount                        AS discount,
                    0.00                               AS parcel_charges,
                    go.delivery_time                   AS estimated_delivery_time,
                    go.order_type                      AS order_type,
                    b.businessName                     AS business_name,
                    b.businessType                     AS business_type,
                    b.address                          AS business_address,
                    b.location                         AS business_location,
                    b.landmark                         AS business_landmark,
                    b.city                             AS business_city,
                    b.state                            AS business_state,
                    b.pincode                          AS business_pincode,
                    b.latitude                         AS business_latitude,
                    b.longitude                        AS business_longitude,
                    b.businessNumber                   AS business_phone,
                    b.contact_mobile                   AS business_contact_mobile,
                    b.contact_support                  AS business_contact_support,
                    b.businessWhatsapp                 AS business_whatsapp,
                    b.business_hours                   AS business_hours_json,
                    b.status                           AS business_status,
                    r.firstName                        AS first_name,
                    r.lastName                         AS last_name,
                    r.displayName                      AS display_name,
                    r.mobileNumber                     AS phone_number,
                    r.emailID                          AS email,
                    r.profileUrl                       AS profile_image,
                    'groceries'                        AS source_table,
                    -- Company/B2B Details
                    go.order_customer_type,
                    go.company_id,
                    go.ordered_by_employee,
                    go.approval_status,
                    go.company_notes,
                    go.company_department,
                    go.company_purchase_order,
                    go.is_bulk_order,
                    ''                                 AS bulk_order_reference,
                    cr.company_name,
                    cr.gst_number
                FROM Groceries_orders go
                LEFT JOIN businesses b   ON go.business_id = b.business_id
                LEFT JOIN registrations r ON go.user_id     = r.user_id
                LEFT JOIN user_address ua ON ua.user_id = r.user_id AND ua.is_default = 1
                LEFT JOIN company_registrations cr ON go.company_id = cr.company_id
                WHERE go.order_id = %s
                LIMIT 1
            """

            cursor.execute(grocery_order_sql, [order_id])
            grocery_row = cursor.fetchone()

            if not grocery_row:
                return None

            grocery_columns = [col[0] for col in cursor.description]
            order = dict(zip(grocery_columns, grocery_row))

            try:
                # Default payment method for grocery when not available
                order['payment_method'] = 'N/A'
                cursor.execute(
                    """
                    SELECT gp.payment_status, gp.payment_method
                    FROM Groceries_payments gp
                    WHERE gp.order_id = %s
                    ORDER BY gp.payment_date DESC, gp.payment_id DESC
                    LIMIT 1
                    """,
                    [order_id]
                )
                gpay = cursor.fetchone()
                if gpay:
                    if gpay[0]:
                        order['payment_status'] = gpay[0]
                    if len(gpay) > 1 and gpay[1]:
                        order['payment_method'] = gpay[1]
            except Exception:
                pass

            grocery_items_sql = """
                SELECT
                    i.order_item_id                 AS item_id,
                    i.product_id                    AS product_id,
                    p.product_name                  AS item_name,
                    p.brand_name                    AS brand_name,
                    i.quantity                      AS quantity,
                    i.unit_price                    AS unit_price,
                    i.total_price                   AS total_price,
                    i.gst                           AS gst,
                    p.main_image                    AS item_image,
                    p.description                   AS description,
                    p.sub_category                  AS item_category,
                    p.is_organic                    AS is_organic,
                    p.rating                        AS rating
                FROM Groceries_order_items i
                LEFT JOIN Groceries_Products p ON i.product_id = p.product_id
                WHERE i.order_id = %s
            """

            cursor.execute(grocery_items_sql, [order_id])
            grocery_item_columns = [col[0] for col in cursor.description]
            order['items'] = [dict(zip(grocery_item_columns, item_row)) for item_row in cursor.fetchall()]

            return order

    @staticmethod
    def check_grocery_orders_exist():
        """Return total count of grocery orders using raw SQL."""
        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT COUNT(*) FROM Groceries_orders")
                result = cursor.fetchone()
                return result[0] if result else 0
        except Exception as exc:
            logger.error(f"Failed to check grocery orders count: {exc}")
            return 0

    @staticmethod
    def get_nearby_grocery_orders(user_lat, user_lng, radius_km):
        """Fetch nearby grocery orders filtered by delivery type using raw SQL."""
        sql = """
            SELECT
                go.order_id,
                go.order_status,
                go.payment_status,
                go.total_amount,
                go.gst_amount,
                go.delivery_charge,
                go.discount,
                go.final_amount,
                go.delivery_address,
                go.delivery_instructions,
                go.delivery_time,
                go.pickup_time,
                go.created_at,
                go.order_type,
                go.user_id,
                r.firstName,
                r.lastName,
                r.displayName,
                r.mobileNumber,
                b.business_id,
                b.businessName,
                b.address,
                b.latitude,
                b.longitude,
                (6371 * acos(cos(radians(%s)) * cos(radians(b.latitude)) *
                    cos(radians(b.longitude) - radians(%s)) +
                    sin(radians(%s)) * sin(radians(b.latitude)))) AS distance_km
            FROM Groceries_orders go
            JOIN businesses b ON go.business_id = b.business_id
            JOIN registrations r ON go.user_id = r.user_id
            WHERE go.order_status IN ('pending', 'confirmed', 'packed', 'ready', 'dispatch')
              AND go.order_type = 'delivery'
              AND b.latitude IS NOT NULL
              AND b.longitude IS NOT NULL
            HAVING distance_km <= %s
            ORDER BY distance_km, go.created_at
        """

        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    sql,
                    [user_lat, user_lng, user_lat, radius_km]
                )
                columns = [col[0] for col in cursor.description]
                return [dict(zip(columns, row)) for row in cursor.fetchall()]
        except Exception as exc:
            logger.error(f"Error fetching nearby grocery orders: {exc}")
            return []

    @staticmethod
    def format_grocery_order_data(order_row):
        """Format raw grocery order row into API response structure."""
        if not order_row:
            return None

        try:
            distance = order_row.get('distance_km')
            formatted_distance = round(float(distance), 2) if distance is not None else None

            customer_name = order_row.get('displayName')
            if not customer_name:
                first = order_row.get('firstName') or ''
                last = order_row.get('lastName') or ''
                customer_name = f"{first} {last}".strip()

            normalized_type = (order_row.get('order_type') or '').lower()
            if normalized_type == 'grocery':
                normalized_type = 'delivery'

            return {
                "order_id": order_row.get('order_id'),
                "order_type": normalized_type,
                "order_status": order_row.get('order_status'),
                "payment_status": order_row.get('payment_status'),
                "total_amount": str(order_row.get('total_amount') or 0),
                "gst_amount": str(order_row.get('gst_amount') or 0),
                "delivery_charge": str(order_row.get('delivery_charge') or 0),
                "discount": str(order_row.get('discount') or 0),
                "final_amount": str(order_row.get('final_amount') or 0),
                "delivery_address": order_row.get('delivery_address'),
                "delivery_instructions": order_row.get('delivery_instructions'),
                "delivery_time": order_row.get('delivery_time'),
                "pickup_time": order_row.get('pickup_time'),
                "created_at": order_row.get('created_at').isoformat() if order_row.get('created_at') else None,
                "customer": {
                    "user_id": order_row.get('user_id'),
                    "name": customer_name,
                    "phone": order_row.get('mobileNumber')
                },
                "business": {
                    "business_id": order_row.get('business_id'),
                    "name": order_row.get('businessName'),
                    "address": order_row.get('address'),
                    "distance_km": formatted_distance
                }
            }
        except Exception as exc:
            logger.error(f"Failed to format grocery order row: {exc}")
            return None

    @staticmethod
    def get_assigned_standard_orders(partner_user_id, status_filter=None):
        """Fetch assigned standard orders for a delivery partner with optional status filter."""
        
        # First, get all business IDs that this partner should see orders from
        # This includes master businesses and their sub-businesses
        with connection.cursor() as cursor:
            # Get all businesses where this partner has orders assigned
            cursor.execute("""
                SELECT DISTINCT o.business_id 
                FROM orders o 
                WHERE (
                    o.delivery_partner_id IN (
                        SELECT id FROM delivery_partner WHERE user_id = %s
                    ) OR o.delivery_partner_id = %s
                )
            """, [partner_user_id, partner_user_id])
            
            assigned_business_ids = [row[0] for row in cursor.fetchall()]
            
            if not assigned_business_ids:
                return []
            
            # For each business, check if it's a master and get all related businesses
            all_business_ids = set(assigned_business_ids)
            
            for business_id in assigned_business_ids:
                # Check if this business is a master business
                cursor.execute("""
                    SELECT business_id, level 
                    FROM businesses 
                    WHERE business_id = %s AND status = 1
                """, [business_id])
                
                business_info = cursor.fetchone()
                if business_info and business_info[1] == 'master':
                    # Get all sub-businesses
                    cursor.execute("""
                        SELECT business_id 
                        FROM businesses 
                        WHERE master = %s AND status = 1
                    """, [business_id])
                    
                    sub_businesses = cursor.fetchall()
                    for sub_business in sub_businesses:
                        all_business_ids.add(sub_business[0])
            
            # Convert to list for SQL IN clause
            business_ids_list = list(all_business_ids)
            business_placeholders = ','.join(['%s'] * len(business_ids_list))
        
                # Base SQL query with business hierarchy support
        sql = f"""
            SELECT
                o.order_id,
                o.order_number,
                o.token_num AS token_num,
                o.status,
                o.total_amount,
                o.delivery_charges,
                o.final_amount,
                o.order_type,
                o.created_at,
                o.updated_at,
                o.delivery_partner_id,
                o.estimated_delivery_time,
                o.actual_delivery_time,
                b.business_id,
                b.businessName,
                b.businessType AS business_type,
                b.address,
                b.landmark,
                b.city,
                b.state,
                b.pincode,
                b.latitude AS latitude,
                b.longitude AS longitude,
                r.user_id AS customer_id,
                r.firstName,
                r.lastName,
                r.displayName,
                r.mobileNumber,
                r.emailID,
                r.profileUrl,
                CONCAT_WS(', ',
                    CONCAT('Door No: ', JSON_UNQUOTE(JSON_EXTRACT(ua.address, '$."Door no"'))),
                    JSON_UNQUOTE(JSON_EXTRACT(ua.address, '$.street')),
                    JSON_UNQUOTE(JSON_EXTRACT(ua.address, '$."city/town"')),
                    JSON_UNQUOTE(JSON_EXTRACT(ua.address, '$.state')),
                    CONCAT('Pincode: ', JSON_UNQUOTE(JSON_EXTRACT(ua.address, '$.pincode')))
                ) AS delivery_address,
                CONCAT_WS(', ',
                    CONCAT('Landmark: ', JSON_UNQUOTE(JSON_EXTRACT(ua.address, '$.landmark'))),
                    CONCAT('Contact: ', r.mobileNumber)
                ) AS delivery_instructions,
                COALESCE(
                    JSON_UNQUOTE(JSON_EXTRACT(ua.address, '$.latitude')),
                    JSON_UNQUOTE(JSON_EXTRACT(ua.address, '$.lat'))
                ) AS consumer_latitude,
                COALESCE(
                    JSON_UNQUOTE(JSON_EXTRACT(ua.address, '$.longitude')),
                    JSON_UNQUOTE(JSON_EXTRACT(ua.address, '$.lng'))
                ) AS consumer_longitude
            FROM orders o
            JOIN businesses b ON o.business_id = b.business_id
            LEFT JOIN registrations r ON o.user_id = r.user_id
            LEFT JOIN user_address ua ON o.delivery_address_id = ua.id
            WHERE (
                o.delivery_partner_id IN (
                    SELECT id FROM delivery_partner WHERE user_id = %s
                ) OR o.delivery_partner_id = %s
            )
        """
        
        # Parameters for the query
        params = [partner_user_id, partner_user_id]
        
        # Add status filter if provided
        if status_filter:
            # Handle multiple statuses separated by comma or 'or'
            statuses = [s.strip().lower() for s in status_filter.replace(' or ', ',').replace('(or)', ',').split(',')]
            if statuses:
                placeholders = ','.join(['%s'] * len(statuses))
                sql += f" AND LOWER(o.status) IN ({placeholders})"
                params.extend(statuses)
        else:
            # Default status filter if no specific filter provided - show only active assigned orders
            sql += " AND o.status = 'assigned'"
        
        sql += " ORDER BY o.updated_at DESC"

        try:
            with connection.cursor() as cursor:
                cursor.execute(sql, params)
                columns = [col[0] for col in cursor.description]
                return [dict(zip(columns, row)) for row in cursor.fetchall()]
        except Exception as exc:
            logger.error(f"Error fetching assigned standard orders: {exc}")
            return []

    @staticmethod
    def get_assigned_grocery_orders(partner_user_id, assignment_status_filter=None):
        """Fetch grocery orders assigned to a partner via delivery details with optional assignment status filter."""
        
        # First, get all business IDs that this partner should see orders from
        # This includes master businesses and their sub-businesses
        with connection.cursor() as cursor:
            # Get all businesses where this partner has grocery orders assigned
            cursor.execute("""
                SELECT DISTINCT go.business_id 
                FROM Grocery_deliver_details gdd
                JOIN Groceries_orders go ON gdd.order_id = go.order_id
                WHERE gdd.partner_id = %s AND gdd.is_active = 1
            """, [partner_user_id])
            
            assigned_business_ids = [row[0] for row in cursor.fetchall()]
            
            if not assigned_business_ids:
                return []
            
            # For each business, check if it's a master and get all related businesses
            all_business_ids = set(assigned_business_ids)
            
            for business_id in assigned_business_ids:
                # Check if this business is a master business
                cursor.execute("""
                    SELECT business_id, level 
                    FROM businesses 
                    WHERE business_id = %s AND status = 1
                """, [business_id])
                
                business_info = cursor.fetchone()
                if business_info and business_info[1] == 'master':
                    # Get all sub-businesses
                    cursor.execute("""
                        SELECT business_id 
                        FROM businesses 
                        WHERE master = %s AND status = 1
                    """, [business_id])
                    
                    sub_businesses = cursor.fetchall()
                    for sub_business in sub_businesses:
                        all_business_ids.add(sub_business[0])
            
            # Convert to list for SQL IN clause
            business_ids_list = list(all_business_ids)
            business_placeholders = ','.join(['%s'] * len(business_ids_list))
        
        # Base SQL query with business hierarchy support
        sql = """
            SELECT
                go.order_id,
                go.order_status,
                go.payment_status,
                go.total_amount,
                go.gst_amount,
                go.delivery_charge,
                go.discount,
                go.final_amount,
                go.delivery_address,
                go.delivery_instructions,
                go.delivery_time,
                go.pickup_time,
                go.created_at,
                go.order_type,
                gdd.assigned_at,
                gdd.assignment_status,
                gdd.delivery_otp,
                gdd.otp_verified_at,
                gdd.delivered_at,
                b.business_id,
                b.businessName,
                b.businessType AS business_type,
                b.address,
                b.latitude AS latitude,
                b.longitude AS longitude,
                r.user_id AS customer_id,
                r.firstName,
                r.lastName,
                r.displayName,
                r.mobileNumber,
                r.emailID,
                r.profileUrl,
                COALESCE(
                    JSON_UNQUOTE(JSON_EXTRACT(ua.address, '$.latitude')),
                    JSON_UNQUOTE(JSON_EXTRACT(ua.address, '$.lat'))
                ) AS consumer_latitude,
                COALESCE(
                    JSON_UNQUOTE(JSON_EXTRACT(ua.address, '$.longitude')),
                    JSON_UNQUOTE(JSON_EXTRACT(ua.address, '$.lng'))
                ) AS consumer_longitude
            FROM Grocery_deliver_details gdd
            JOIN Groceries_orders go ON gdd.order_id = go.order_id
            JOIN businesses b ON go.business_id = b.business_id
            JOIN registrations r ON go.user_id = r.user_id
            LEFT JOIN user_address ua ON ua.user_id = r.user_id AND ua.is_default = 1
            WHERE gdd.partner_id = %s
              AND gdd.is_active = 1
        """
        
        # Parameters for the query
        params = [partner_user_id]
        
        # Add assignment status filter if provided
        if assignment_status_filter:
            # Handle multiple statuses separated by comma or 'or'
            statuses = [s.strip().lower() for s in assignment_status_filter.replace(' or ', ',').replace('(or)', ',').split(',')]
            if statuses:
                placeholders = ','.join(['%s'] * len(statuses))
                sql += f" AND LOWER(gdd.assignment_status) IN ({placeholders})"
                params.extend(statuses)
        else:
            # Default status filter if no specific filter provided - show only active assigned grocery orders
            sql += " AND gdd.assignment_status = 'assigned'"
            sql += " AND go.order_status = 'assigned'"
        
        sql += " ORDER BY gdd.assigned_at DESC"

        try:
            with connection.cursor() as cursor:
                cursor.execute(sql, params)
                columns = [col[0] for col in cursor.description]
                return [dict(zip(columns, row)) for row in cursor.fetchall()]
        except Exception as exc:
            logger.error(f"Error fetching assigned grocery orders: {exc}")
            return []
            
@swagger_auto_schema(tags=['Delivery'])
class NearbyOrdersView(APIView):
    """
    Enhanced view to display nearby orders from both orders and Groceries_orders tables
    """
    
    def get(self, request, *args, **kwargs):
        try:
            # Get query parameters
            lat = request.query_params.get('lat')
            lng = request.query_params.get('lng')
            radius_km = float(request.query_params.get('radius', 5))  # Default 5km radius
            include_items_preview = request.query_params.get('include_items_preview')

            # Validate coordinates
            if not lat or not lng:
                return Response(
                    {'error': 'Missing required parameters: lat and lng are required'},
                    status=status.HTTP_400_BAD_REQUEST
                )

            try:
                user_lat = float(lat)
                user_lng = float(lng)
            except (ValueError, TypeError) as e:
                return Response(
                    {'error': 'Invalid coordinates', 'details': str(e)},
                    status=status.HTTP_400_BAD_REQUEST
                )

            # Check if grocery orders exist in database
            grocery_count = GroceryOrdersService.check_grocery_orders_exist()
            logger.info(f"Starting nearby orders search - Grocery orders in DB: {grocery_count}")
            
            # Get regular orders from orders table
            regular_orders = self._get_regular_orders(user_lat, user_lng, radius_km)
            
            # Get grocery orders from Groceries_orders table using the service class
            grocery_orders_raw = GroceryOrdersService.get_nearby_grocery_orders(user_lat, user_lng, radius_km)
            
            # Process regular orders
            upcoming_orders = []
            ready_orders = []

            for order in regular_orders:
                try:
                    if order.get('order_type') != 'delivery':
                        continue
                    if order.get('status') == 'assigned':
                        continue
                    order_data = {
                        'order_id': order['order_id'],
                        'order_number': order['order_number'],
                        'order_type': 'delivery',  # Identify as delivery order
                        'status': order['status'],
                        'total_amount': str(order['total_amount']),
                        'created_at': order['created_at'].isoformat() if order['created_at'] else None,
                        'business': {
                            'business_id': order['business_id'],
                            'name': order['businessName'],
                            'address': order['address'],
                            'distance_km': round(float(order['distance_km']), 2)
                        }
                    }

                    # Categorize the order
                    if order['status'] in ['pending', 'confirmed', 'preparing']:
                        upcoming_orders.append(order_data)
                    elif order['status'] in ['ready', 'dispatch']:
                        ready_orders.append(order_data)

                except Exception as e:
                    logger.error(f"Error processing regular order {order.get('order_id', 'unknown')}: {str(e)}")
                    continue
            
            # Process grocery orders
            external_source_orders = []
            for grocery_order in grocery_orders_raw:
                formatted_order = GroceryOrdersService.format_grocery_order_data(grocery_order)
                if formatted_order:
                    if formatted_order.get('order_status') == 'assigned':
                        continue
                    if formatted_order.get('order_type') != 'delivery':
                        continue
                    external_source_orders.append(formatted_order)

            try:
                if include_items_preview and str(include_items_preview).strip().lower() in ('1', 'true', 'yes'):
                    GroceryOrdersService.attach_items_preview_to_standard_orders(upcoming_orders + ready_orders)
                    GroceryOrdersService.attach_items_preview_to_grocery_orders(external_source_orders)
            except Exception as exc:
                logger.error(f"Failed to attach items preview in NearbyOrdersView: {exc}")

            return Response({
                "success": True,
                "search_location": {
                    "latitude": user_lat,
                    "longitude": user_lng,
                    "radius_km": radius_km
                },
                "summary": {
                    "total_regular_orders": len(upcoming_orders) + len(ready_orders),
                    "total_grocery_orders": len(external_source_orders),
                    "upcoming_orders_count": len(upcoming_orders),
                    "ready_orders_count": len(ready_orders)
                },
                "upcoming_orders": upcoming_orders,  # Regular orders from orders table
                "ready_for_delivery": ready_orders,  # Regular orders ready for delivery
                "external_source_orders": external_source_orders  # Grocery orders from Groceries_orders table
            })

        except Exception as e:
            logger.exception("Error in NearbyOrdersView")
            return Response(
                {"error": "An error occurred while fetching nearby orders"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    def _get_regular_orders(self, user_lat, user_lng, radius_km):
        """
        Get regular orders from orders table using raw SQL
        """
        try:
            # Raw SQL to get nearby orders with business details from orders table
            sql = """
            SELECT 
                o.order_id,
                o.order_number,
                o.status,
                o.total_amount,
                o.created_at,
                o.order_type,
                b.business_id,
                b.businessName,
                b.address,
                b.latitude,
                b.longitude,
                (6371 * acos(cos(radians(%s)) * cos(radians(b.latitude)) * 
                cos(radians(b.longitude) - radians(%s)) + 
                sin(radians(%s)) * sin(radians(b.latitude)))) AS distance_km
            FROM 
                orders o
            JOIN 
                businesses b ON o.business_id = b.business_id
            WHERE 
                o.status IN ('pending', 'confirmed', 'preparing', 'ready', 'dispatch')
                AND o.order_type = 'delivery'
                AND o.delivery_partner_id IS NULL
                AND b.status = 1
                AND b.latitude IS NOT NULL
                AND b.longitude IS NOT NULL
                AND (6371 * acos(cos(radians(%s)) * cos(radians(b.latitude)) * 
                    cos(radians(b.longitude) - radians(%s)) + 
                    sin(radians(%s)) * sin(radians(b.latitude)))) <= %s
            ORDER BY 
                distance_km, o.created_at
            """

            with connection.cursor() as cursor:
                cursor.execute(sql, [user_lat, user_lng, user_lat, user_lat, user_lng, user_lat, radius_km])
                columns = [col[0] for col in cursor.description]
                results = [
                    dict(zip(columns, row))
                    for row in cursor.fetchall()
                ]
            
            return results
            
        except Exception as e:
            logger.error(f"Error fetching regular orders: {str(e)}")
            return []

@swagger_auto_schema(tags=['Delivery'])
class AssignedOrdersView(APIView):
    """API to list orders currently assigned to a delivery partner."""

    def get(self, request):
        user_id = request.query_params.get('user_id')
        status_filter = request.query_params.get('status')
        assignment_status_filter = request.query_params.get('assignment_status')
        include_items_preview = request.query_params.get('include_items_preview')

        # If assignment_status is provided but status is not, use assignment_status for both
        # This makes the API more intuitive - one filter applies to both order types
        if assignment_status_filter and not status_filter:
            status_filter = assignment_status_filter

        if not user_id:
            return Response(
                {"error": "user_id parameter is required"},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            partner_user_id = int(user_id)
        except (TypeError, ValueError):
            return Response(
                {"error": "user_id must be a valid integer"},
                status=status.HTTP_400_BAD_REQUEST
            )

        def to_absolute_url(path):
            """Build S3 URL for media path."""
            return build_s3_file_url(path)

        def _safe_float(v):
            if v is None:
                return None
            if isinstance(v, str) and v.strip().lower() in ('', 'null', 'none'):
                return None
            try:
                return float(v)
            except Exception:
                return None

        def estimate_delivery_time(b_lat, b_lng, c_lat, c_lng, business_type, order_type='delivery'):
            try:
                if business_type == 'R02':
                    base_prep = 30
                elif business_type == 'R01':
                    base_prep = 15
                elif business_type == 'R08':
                    base_prep = 20
                else:
                    base_prep = 20

                travel_minutes = 0
                if order_type == 'delivery':
                    try:
                        b_lat_f = _safe_float(b_lat)
                        b_lng_f = _safe_float(b_lng)
                        c_lat_f = _safe_float(c_lat)
                        c_lng_f = _safe_float(c_lng)
                        if b_lat_f is not None and b_lng_f is not None and c_lat_f is not None and c_lng_f is not None:
                            distance_km = geodesic((b_lat_f, b_lng_f), (c_lat_f, c_lng_f)).kilometers
                            travel_minutes = max(10, int((distance_km / 20.0) * 60))
                    except Exception:
                        travel_minutes = 0

                total_minutes = int(base_prep + travel_minutes)
                est_dt = timezone.now() + timezone.timedelta(minutes=total_minutes)
                return est_dt.isoformat()
            except Exception:
                return (timezone.now() + timezone.timedelta(minutes=30)).isoformat()

        standard_rows = GroceryOrdersService.get_assigned_standard_orders(partner_user_id, status_filter)
        grocery_rows = GroceryOrdersService.get_assigned_grocery_orders(partner_user_id, status_filter or assignment_status_filter)

        standard_orders = []
        for row in standard_rows:
            try:
                customer_name = row.get('displayName') or f"{row.get('firstName') or ''} {row.get('lastName') or ''}".strip()
                computed_delivery_time = estimate_delivery_time(
                    row.get('latitude'), row.get('longitude'),
                    row.get('consumer_latitude'), row.get('consumer_longitude'),
                    row.get('business_type'), row.get('order_type') or 'delivery'
                )

                # Format business address with landmark, city, state, pincode
                business_address_parts = []
                if row.get('address'):
                    business_address_parts.append(row.get('address'))
                if row.get('landmark'):
                    business_address_parts.append(f"Landmark: {row.get('landmark')}")
                if row.get('city'):
                    business_address_parts.append(row.get('city'))
                if row.get('state'):
                    business_address_parts.append(row.get('state'))
                if row.get('pincode'):
                    business_address_parts.append(f"Pincode: {row.get('pincode')}")
                
                formatted_business_address = ', '.join(business_address_parts) if business_address_parts else row.get('address', 'Address not available')

                standard_orders.append({
                    "order_id": row.get('order_id'),
                    "order_number": row.get('order_number'),
                    "token_num": row.get('token_num'),
                    "order_type": row.get('order_type') or 'delivery',
                    "status": row.get('status'),
                    "total_amount": str(row.get('total_amount') or 0),
                    "delivery_charges": str(row.get('delivery_charges') or 0),
                    "final_amount": str(row.get('final_amount') or 0),
                    "created_at": row.get('created_at').isoformat() if row.get('created_at') else None,
                    "updated_at": row.get('updated_at').isoformat() if row.get('updated_at') else None,
                    "estimated_delivery_time": row.get('estimated_delivery_time').isoformat() if row.get('estimated_delivery_time') else None,
                    "actual_delivery_time": row.get('actual_delivery_time').isoformat() if row.get('actual_delivery_time') else None,
                    "delivery_instructions": row.get('delivery_instructions'),
                    "delivery_time": computed_delivery_time,
                    # Explicit address/coordinates
                    "business_address": formatted_business_address,
                    "business_lat": _safe_float(row.get('latitude')),
                    "business_lng": _safe_float(row.get('longitude')),
                    "consumer_address": row.get('delivery_address'),
                    "consumer_lat": _safe_float(row.get('consumer_latitude')),
                    "consumer_lon": _safe_float(row.get('consumer_longitude')),
                    "business": {
                        "business_id": row.get('business_id'),
                        "name": row.get('businessName'),
                        "address": formatted_business_address,
                    },
                    "customer": {
                        "id": row.get('customer_id'),
                        "name": customer_name if customer_name else None,
                        "phone": row.get('mobileNumber'),
                        "email": row.get('emailID'),
                        "profile_image": to_absolute_url(row.get('profileUrl')),
                    }
                })
            except Exception as exc:
                logger.error(f"Failed to format assigned standard order {row.get('order_id')}: {exc}")
                continue

        grocery_orders = []
        for row in grocery_rows:
            try:
                normalized_type = (row.get('order_type') or '').lower()
                if normalized_type == 'grocery':
                    normalized_type = 'delivery'

                customer_name = row.get('displayName') or f"{row.get('firstName') or ''} {row.get('lastName') or ''}".strip()

                computed_delivery_time = estimate_delivery_time(
                    row.get('latitude'), row.get('longitude'),
                    row.get('consumer_latitude'), row.get('consumer_longitude'),
                    row.get('business_type'), normalized_type or 'delivery'
                )

                # Format business address with landmark, city, state, pincode for grocery orders
                business_address_parts = []
                if row.get('address'):
                    business_address_parts.append(row.get('address'))
                if row.get('landmark'):
                    business_address_parts.append(f"Landmark: {row.get('landmark')}")
                if row.get('city'):
                    business_address_parts.append(row.get('city'))
                if row.get('state'):
                    business_address_parts.append(row.get('state'))
                if row.get('pincode'):
                    business_address_parts.append(f"Pincode: {row.get('pincode')}")
                
                formatted_business_address = ', '.join(business_address_parts) if business_address_parts else row.get('address', 'Address not available')

                grocery_orders.append({
                    "order_id": row.get('order_id'),
                    "order_type": normalized_type or 'delivery',
                    "order_status": row.get('order_status'),
                    "status": row.get('assignment_status'),
                    "payment_status": row.get('payment_status'),
                    "total_amount": str(row.get('total_amount') or 0),
                    "gst_amount": str(row.get('gst_amount') or 0),
                    "delivery_charge": str(row.get('delivery_charge') or 0),
                    "discount": str(row.get('discount') or 0),
                    "final_amount": str(row.get('final_amount') or 0),
                    "delivery_instructions": row.get('delivery_instructions'),
                    "delivery_time": row.get('delivery_time').isoformat() if row.get('delivery_time') else computed_delivery_time,
                    "pickup_time": row.get('pickup_time').isoformat() if row.get('pickup_time') else None,
                    "created_at": row.get('created_at').isoformat() if row.get('created_at') else None,
                    "assigned_at": row.get('assigned_at').isoformat() if row.get('assigned_at') else None,
                    "delivered_at": row.get('delivered_at').isoformat() if row.get('delivered_at') else None,
                    "otp_verified_at": row.get('otp_verified_at').isoformat() if row.get('otp_verified_at') else None,
                    "delivery_otp": row.get('delivery_otp'),
                    # Explicit address/coordinates
                    "business_address": formatted_business_address,
                    "business_lat": float(row.get('latitude')) if row.get('latitude') is not None else None,
                    "business_lng": float(row.get('longitude')) if row.get('longitude') is not None else None,
                    "consumer_address": row.get('delivery_address'),
                    "consumer_lat": float(row.get('consumer_latitude')) if row.get('consumer_latitude') not in (None, '') else None,
                    "consumer_lon": float(row.get('consumer_longitude')) if row.get('consumer_longitude') not in (None, '') else None,
                    "business": {
                        "business_id": row.get('business_id'),
                        "name": row.get('businessName'),
                        "address": formatted_business_address,
                    },
                    "customer": {
                        "id": row.get('customer_id'),
                        "name": customer_name if customer_name else None,
                        "phone": row.get('mobileNumber'),
                        "email": row.get('emailID'),
                        "profile_image": to_absolute_url(row.get('profileUrl')),
                    }
                })
            except Exception as exc:
                logger.error(f"Failed to format assigned grocery order {row.get('order_id')}: {exc}")
                continue

        # Show the effective filter that was applied to both order types
        effective_filter = status_filter or assignment_status_filter
        
        response = {
            "success": True,
            "partner_id": partner_user_id,
            "filters_applied": {
                "status_filter": effective_filter,
                "original_params": {
                    "status": request.query_params.get('status'),
                    "assignment_status": request.query_params.get('assignment_status')
                }
            },
            "summary": {
                "total_standard_orders": len(standard_orders),
                "total_grocery_orders": len(grocery_orders),
                "total_orders": len(standard_orders) + len(grocery_orders)
            },
            "standard_orders": standard_orders,
            "grocery_orders": grocery_orders
        }

        try:
            if include_items_preview and str(include_items_preview).strip().lower() in ('1', 'true', 'yes'):
                GroceryOrdersService.attach_items_preview_to_standard_orders(response.get('standard_orders') or [])
                GroceryOrdersService.attach_items_preview_to_grocery_orders(response.get('grocery_orders') or [])
        except Exception as exc:
            logger.error(f"Failed to attach items preview in AssignedOrdersView: {exc}")

        return Response(response, status=status.HTTP_200_OK)

@swagger_auto_schema(tags=['Delivery'])
class OrderAcceptView(APIView):
    """
    POST /orders/<int:order_id>/accept/
    Accept an order from either standard orders table or grocery orders table
    Automatically detects which system to use based on order_id
    """
    
    def detect_order_type(self, order_id):
        """
        Detect which order system the order belongs to
        Returns: 'standard', 'grocery', or None
        """
        try:
            with connection.cursor() as cursor:
                # Check if order exists in standard orders table
                cursor.execute("SELECT order_id FROM orders WHERE order_id = %s", [order_id])
                if cursor.fetchone():
                    return 'standard'
                
                # Check if order exists in grocery orders table
                cursor.execute("SELECT order_id FROM Groceries_orders WHERE order_id = %s", [order_id])
                if cursor.fetchone():
                    return 'grocery'
                
                return None
        except Exception as e:
            logger.error(f"Error detecting order type: {str(e)}")
            return None
    
    def post(self, request, order_id):
        user_id = request.data.get('user_id') or request.query_params.get('user_id')
        
        if not user_id:
            return Response(
                {"error": "user_id is required"},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Detect which order system to use
        order_type = self.detect_order_type(order_id)
        
        if not order_type:
            return Response(
                {"error": "Order not found in any system"},
                status=status.HTTP_404_NOT_FOUND
            )
        
        try:
            if order_type == 'standard':
                return self._accept_standard_order(order_id, user_id)
            elif order_type == 'grocery':
                return self._accept_grocery_order(order_id, user_id)
                
        except Exception as e:
            logger.error(f"Error accepting order {order_id}: {str(e)}")
            return Response(
                {"error": f"Failed to accept order: {str(e)}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    def _accept_standard_order(self, order_id, user_id):
        """Accept order from standard orders table"""
        try:
            with connection.cursor() as cursor:
                # First check if user exists in registrations table
                cursor.execute("SELECT user_id, displayName FROM registrations WHERE user_id = %s", [user_id])
                user_row = cursor.fetchone()
                if not user_row:
                    return Response(
                        {"error": "User not found in system"},
                        status=status.HTTP_404_NOT_FOUND
                    )
                
                # Check if delivery partner exists and is available
                cursor.execute("""
                    SELECT id, is_available, status 
                    FROM delivery_partner 
                    WHERE user_id = %s
                """, [user_id])
                
                partner_row = cursor.fetchone()
                if not partner_row:
                    return Response(
                        {
                            "error": "Delivery partner profile not found",
                            "message": f"User '{user_row[1]}' (ID: {user_id}) exists but is not registered as a delivery partner. Please complete delivery partner registration first.",
                            "user_exists": True,
                            "delivery_partner_exists": False
                        },
                        status=status.HTTP_404_NOT_FOUND
                    )
                
                if not bool(int(partner_row[1])):  # is_available
                    return Response(
                        {"error": "You are not available for deliveries"},
                        status=status.HTTP_400_BAD_REQUEST
                    )
                
                # Check if order is available for acceptance
                cursor.execute("""
                    SELECT order_id, status, delivery_partner_id 
                    FROM orders 
                    WHERE order_id = %s
                """, [order_id])
                
                order_row = cursor.fetchone()
                if not order_row:
                    return Response(
                        {"error": "Order not found"},
                        status=status.HTTP_404_NOT_FOUND
                    )
                # Case 1: Order is already assigned - delivery partner wants to accept it (change to accepted)
                if order_row[2]:  # delivery_partner_id already exists
                    # Update order status to 'accepted' (delivery partner accepted the order)
                    cursor.execute("""
                        UPDATE orders 
                        SET status = 'accepted', 
                            updated_at = NOW()
                        WHERE order_id = %s AND delivery_partner_id = %s
                    """, [order_id, user_id])
                    
                    # Update delivery partner status
                    cursor.execute("""
                        UPDATE delivery_partner 
                        SET is_available = 1, 
                            status = 1, 
                            updated_at = NOW()
                        WHERE user_id = %s
                    """, [user_id])
                    try:
                        cursor.execute("SELECT user_id FROM orders WHERE order_id = %s", [order_id])
                        row = cursor.fetchone()
                        if row and row[0]:
                            on_order_status(int(row[0]), order_id, 'accepted')
                    except Exception:
                        pass
                    try:
                        prev_status = order_row[1]
                        create_status_log('standard', order_id, prev_status, 'accepted', user_id=user_id, role='delivery', source='delivery.accept')
                    except Exception:
                        pass

                    return Response({
                        "success": True,
                        "message": "Standard order accepted successfully - status changed to accepted",
                        "order_id": order_id,
                        "order_type": "standard",
                        "delivery_system": "standard",
                        "order_status": "accepted"
                    })
                # Case 2: Not assigned (leave behavior for existing flow)
                return Response(
                    {"error": "Order is not yet assigned to this partner"},
                    status=status.HTTP_400_BAD_REQUEST
                )
        except Exception as e:
            logger.error(f"Error accepting standard order: {str(e)}")
            raise e

    def _accept_grocery_order(self, order_id, user_id):
        """Accept order for groceries using raw SQL with minimal safe logic."""
        try:
            with connection.cursor() as cursor:
                # Check if an active assignment exists
                cursor.execute(
                    """
                    SELECT gdd.delivery_detail_id, gdd.assignment_status, go.order_status, gdd.delivery_otp, gdd.partner_id
                    FROM Grocery_deliver_details gdd
                    JOIN Groceries_orders go ON go.order_id = gdd.order_id
                    WHERE gdd.order_id = %s AND gdd.is_active = 1
                    LIMIT 1
                    """,
                    [order_id]
                )
                row = cursor.fetchone()
                if row:
                    delivery_detail_id, assignment_status, order_status, delivery_otp, partner_id = row
                    if str(partner_id) != str(user_id):
                        return Response({"error": "This order is assigned to a different delivery partner"}, status=status.HTTP_403_FORBIDDEN)
                    # Mark accepted if currently assigned
                    if assignment_status == 'assigned':
                        cursor.execute(
                            "UPDATE Grocery_deliver_details SET assignment_status = 'accepted', updated_at = NOW() WHERE delivery_detail_id = %s",
                            [delivery_detail_id]
                        )
                    try:
                        cursor.execute("SELECT user_id FROM Groceries_orders WHERE order_id = %s", [order_id])
                        r = cursor.fetchone()
                        if r and r[0]:
                            on_order_status(int(r[0]), order_id, 'accepted')
                    except Exception:
                        pass
                    try:
                        create_status_log('grocery', int(order_id), order_status, 'accepted', user_id=int(user_id), role='delivery', source='delivery.accept')
                    except Exception:
                        pass
                    return Response({
                        "success": True,
                        "message": "Grocery order accepted successfully - status changed to pickedup",
                        "order_id": order_id,
                        "order_type": "grocery",
                        "delivery_system": "grocery",
                        "delivery_otp": delivery_otp,
                        "assignment_status": "accepted",
                        "order_status": "accepted"
                    })

                # No existing assignment; reject for now to avoid unintended assignment changes
                return Response({"error": "Grocery order is not yet assigned"}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            logger.error(f"Error accepting grocery order: {str(e)}")
            raise e

@swagger_auto_schema(tags=['Delivery'])
class OrderStatusUpdateView(DeliveryPartnerMixin, APIView):
    
    def post(self, request, order_id):
        partner = None
        partner_user_id = None

        # Prefer authenticated user if available, otherwise fall back to user_id query param
        if request.user and request.user.is_authenticated:
            partner = self.get_delivery_partner(request.user)
            partner_user_id = getattr(getattr(request.user, 'user_id', None), 'user_id', None) or getattr(request.user, 'user_id', None)

        if not partner:
            user_id = request.query_params.get('user_id')
            if not user_id:
                return Response(
                    {"error": "Delivery partner profile not found"},
                    status=status.HTTP_404_NOT_FOUND
                )

            try:
                partner_user_id = int(user_id)
            except (TypeError, ValueError):
                return Response(
                    {"error": "user_id must be a valid integer"},
                    status=status.HTTP_400_BAD_REQUEST
                )

            partner = DeliveryPartner.objects.select_related('user').filter(user__user_id=partner_user_id).first()

        if not partner_user_id and partner:
            partner_user_id = partner.user.user_id

        if not partner_user_id:
            return Response(
                {"error": "Delivery partner profile not found"},
                status=status.HTTP_404_NOT_FOUND
            )

        new_status = (request.data.get('status') or '').strip().lower()

        if not new_status:
            return Response(
                {"error": "status is required"},
                status=status.HTTP_400_BAD_REQUEST
            )

        # First, check if a standard order exists with this ID
        standard_order = Orders.objects.filter(order_id=order_id).first()
        
        if standard_order:
            # Check assignment using raw SQL since delivery_partner_id stores user_id, not partner.id
            from django.db import connection
            with connection.cursor() as cursor:
                cursor.execute("""
                    SELECT delivery_partner_id 
                    FROM orders 
                    WHERE order_id = %s
                """, [order_id])
                result = cursor.fetchone()
                assigned_user_id = result[0] if result else None
            
            # Ensure the order is assigned to the requesting partner
            if assigned_user_id and str(assigned_user_id) == str(partner_user_id):
                return self._handle_standard_order_status(standard_order, partner, new_status)
            else:
                return Response(
                    {"error": "This order is not assigned to you."},
                    status=status.HTTP_403_FORBIDDEN
                )

        # Handle grocery orders via raw SQL since they live outside ORM mappings
        try:
            return self._handle_grocery_order_status(order_id, partner_user_id, new_status, partner)
        except ValueError as exc:
            return Response({"error": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as exc:
            logger.error(f"Error updating grocery order status for order {order_id}: {exc}")
            return Response({"error": "Failed to update grocery order status"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    def _handle_standard_order_status(self, order, partner, new_status):
        # Map of new_status -> (db_status, message)
        status_map = {
            'picked_up': ('picked_up', "Order picked up successfully"),
            'out_for_delivery': ('out_for_delivery', "Order is out for delivery"),
            'delivered': ('delivered', "Order delivered successfully"),
            'notified': ('notified', "Order notification sent successfully"),
        }

        if new_status not in status_map:
            return Response(
                {"error": f"Invalid status: {new_status}"},
                status=status.HTTP_400_BAD_REQUEST
            )

        db_status, message = status_map[new_status]

        try:
            prev_status = getattr(order, 'status', None)
            # Directly update the status without FSM validation
            order.status = db_status
            
            # Set delivery time for delivered orders
            if new_status == 'delivered':
                from django.utils import timezone
                order.actual_delivery_time = timezone.now()

            # Update partner status only if partner object exists
            if new_status == 'delivered' and partner:
                partner.status = '1'
                partner.is_available = True
                partner.total_deliveries = (partner.total_deliveries or 0) + 1
                partner.save(update_fields=['status', 'is_available', 'total_deliveries', 'updated_at'])

            order.save()
            
            # Send feedback request email when order is delivered or completed
            if new_status in ['delivered', 'completed']:
                try:
                    from consumer.feedback_notifications import trigger_feedback_request
                    trigger_feedback_request(order.order_id, 'standard')
                except Exception as e:
                    logger.error(f"Failed to trigger feedback request for standard order {order.order_id}: {e}")

            from .consumers import send_order_update
            send_order_update(order)

            try:
                if getattr(order, 'user_id', None):
                    on_order_status(int(order.user_id.user_id), int(order.order_id), new_status)
            except Exception:
                pass
            try:
                create_status_log('standard', int(order.order_id), prev_status, db_status, user_id=(partner.user.user_id if partner else None), role='delivery', source='delivery.status_update')
            except Exception:
                pass

            return Response({
                "success": True,
                "message": message,
                "order_status": order.status
            })

        except Exception as exc:
            logger.error(f"Error updating standard order status for order {order.order_id}: {exc}")
            return Response({"error": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

    def _handle_grocery_order_status(self, order_id, partner_user_id, new_status, partner=None):
        valid_transitions = {
            'assigned': ['accepted', 'picked_up', 'out_for_delivery', 'delivered', 'cancelled'],
            'accepted': ['picked_up', 'out_for_delivery', 'delivered', 'cancelled'],
            'picked_up': ['out_for_delivery', 'in_transit', 'delivered', 'cancelled'],
            'in_transit': ['delivered', 'cancelled'],
        }

        grocery_status_map = {
            'accepted': {
                'order_status': 'assigned',
                'assignment_status': 'accepted',
                'orders_status': 'assigned'
            },
            'picked_up': {
                'order_status': 'picked_up',
                'assignment_status': 'picked_up',
                'orders_status': 'picked_up'
            },
            'out_for_delivery': {
                'order_status': 'out_for_delivery',
                'assignment_status': 'in_transit',
                'orders_status': 'out_for_delivery'
            },
            'in_transit': {
                'order_status': 'out_for_delivery',
                'assignment_status': 'in_transit',
                'orders_status': 'out_for_delivery'
            },
            'delivered': {
                'order_status': 'delivered',
                'assignment_status': 'delivered',
                'orders_status': 'delivered'
            },
            'cancelled': {
                'order_status': 'cancelled',
                'assignment_status': 'cancelled',
                'orders_status': 'cancelled'
            },
        }

        if new_status not in grocery_status_map:
            raise ValueError("Invalid status for grocery order")

        with connection.cursor() as cursor:
            cursor.execute("""
                SELECT 
                    gdd.delivery_detail_id,
                    gdd.assignment_status,
                    gdd.partner_id,
                    go.order_status
                FROM Grocery_deliver_details gdd
                JOIN Groceries_orders go ON go.order_id = gdd.order_id
                WHERE gdd.order_id = %s
                  AND gdd.is_active = 1
            """, [order_id])

            row = cursor.fetchone()
            if not row:
                raise ValueError("Grocery order not found")

            delivery_detail_id, current_assignment_status, partner_id, current_order_status = row

            if str(partner_id) != str(partner_user_id):
                raise ValueError("Order not assigned to this partner")

            allowed_next_statuses = valid_transitions.get(current_assignment_status, [])
            if new_status not in allowed_next_statuses and new_status != current_assignment_status:
                raise ValueError(f"Cannot transition from {current_assignment_status} to {new_status}")

            status_config = grocery_status_map[new_status]
            order_status_value = status_config['order_status']
            assignment_status_value = status_config['assignment_status']
            orders_status_value = status_config['orders_status']

            cursor.execute("""
                UPDATE Groceries_orders
                SET order_status = %s,
                    updated_at = NOW()
                WHERE order_id = %s
            """, [order_status_value, order_id])

            cursor.execute("""
                UPDATE Grocery_deliver_details
                SET assignment_status = %s,
                    updated_at = NOW()
                WHERE delivery_detail_id = %s
            """, [assignment_status_value, delivery_detail_id])

            if orders_status_value:
                extra_updates = []
                params = [orders_status_value]
                if new_status == 'delivered':
                    extra_updates.append("actual_delivery_time = NOW()")
                set_clause = "status = %s"
                if extra_updates:
                    set_clause += ", " + ", ".join(extra_updates)

                cursor.execute(f"""
                    UPDATE orders
                    SET {set_clause},
                        updated_at = NOW()
                    WHERE order_id = %s
                """, params + [order_id])

        if new_status == 'delivered' and partner:
            partner.status = '1'
            partner.is_available = True
            partner.total_deliveries = (partner.total_deliveries or 0) + 1
            partner.save(update_fields=['status', 'is_available', 'total_deliveries', 'updated_at'])
        
        # Send feedback request email when grocery order is delivered or completed
        if new_status in ['delivered', 'completed']:
            try:
                from consumer.feedback_notifications import trigger_feedback_request
                trigger_feedback_request(order_id, 'grocery')
            except Exception as e:
                logger.error(f"Failed to trigger feedback request for grocery order {order_id}: {e}")

        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT user_id FROM Groceries_orders WHERE order_id = %s", [order_id])
                row = cursor.fetchone()
                if row and row[0]:
                    on_order_status(int(row[0]), order_id, new_status)
        except Exception:
            pass
        try:
            create_status_log('grocery', int(order_id), current_order_status, order_status_value, user_id=int(partner_user_id) if partner_user_id else None, role='delivery', source='delivery.status_update')
        except Exception:
            pass

        message_map = {
            'picked_up': "Grocery order picked up successfully",
            'out_for_delivery': "Grocery order is out for delivery",
            'in_transit': "Grocery order is out for delivery",
            'delivered': "Grocery order delivered successfully",
            'accepted': "Grocery order accepted",
            'cancelled': "Grocery order cancelled",
        }

        return Response({
            "success": True,
            "message": message_map.get(new_status, "Status updated"),
            "assignment_status": assignment_status_value,
            "order_status": order_status_value
        })


class OrderOTPMixin:
    otp_expiry_minutes = 10

    def _extract_order(self, order_id):
        try:
            order = Orders.objects.select_related('user_id').get(order_id=order_id)
            user = order.user_id
            return {
                'order_obj': order,
                'user': user,
                'email': getattr(user, 'emailID', None),
                'name': (
                    f"{getattr(user, 'firstName', '')} {getattr(user, 'lastName', '')}".strip()
                    or getattr(user, 'displayName', 'Customer')
                ),
                'phone_number': getattr(user, 'mobileNumber', None),
                'is_grocery': False
            }
        except Orders.DoesNotExist:
            pass

        try:
            order = GroceriesOrders.objects.select_related('user').get(order_id=order_id)
            user = order.user
            return {
                'order_obj': order,
                'user': user,
                'email': getattr(user, 'emailID', None),
                'name': (
                    f"{getattr(user, 'firstName', '')} {getattr(user, 'lastName', '')}".strip()
                    or getattr(user, 'displayName', 'Customer')
                ),
                'phone_number': getattr(user, 'mobileNumber', None),
                'is_grocery': True
            }
        except GroceriesOrders.DoesNotExist:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT 
                        go.order_id,
                        go.pickup_otp,
                        r.firstName,
                        r.lastName,
                        r.displayName,
                        r.emailID,
                        r.mobileNumber
                    FROM Groceries_orders go
                    LEFT JOIN registrations r ON go.user_id = r.user_id
                    WHERE go.order_id = %s
                    LIMIT 1
                    """,
                    [order_id]
                )
                row = cursor.fetchone()
                if not row:
                    return None

                _, pickup_otp, first_name, last_name, display_name, email, phone = row
                name_parts = [part for part in [display_name, first_name, last_name] if part]
                name = name_parts[0] if name_parts else 'Customer'

                order_stub = SimpleNamespace(pickup_otp=pickup_otp)

                return {
                    'order_obj': order_stub,
                    'user': None,
                    'email': email,
                    'name': name,
                    'phone_number': phone,
                    'is_grocery': True
                }

    def _send_email(self, to_email, subject, message):
        # Reset meta
        self._email_throttled = False
        self._email_last_error_code = None
        self._email_last_error_message = None

        if not to_email:
            logger.warning("OTP email skipped due to missing recipient address")
            return False

        # Per-recipient cooldown to avoid provider throttling (e.g., Gmail 4.2.1 ReceivingRate)
        cooldown_key = f"otp_email_cooldown:{to_email}"
        if cache.get(cooldown_key):
            self._email_throttled = True
            self._email_last_error_message = "Recipient is in cooldown window due to previous provider throttling"
            logger.warning(f"Skipping OTP email to {to_email}: cooldown active")
            return False

        try:
            send_mail(subject, message, getattr(settings, 'DEFAULT_FROM_EMAIL', None), [to_email], fail_silently=False)
            return True
        except Exception as exc:
            # Parse common transient throttling signals
            msg = str(exc)
            code_match = re.search(r"\b(4\d{2}|4\.\d\.\d)\b", msg)
            code = code_match.group(1) if code_match else None
            transient = any(token in msg for token in [
                "ReceivingRate",  # Gmail specific
                "4.2.1",
                "450",
                "421",
                "try again later",
                "temporar",
            ])

            self._email_last_error_code = code
            self._email_last_error_message = msg

            if transient:
                # Apply a cooldown (10 minutes) to avoid hammering the recipient inbox
                cache.set(cooldown_key, True, timeout=10 * 60)
                self._email_throttled = True
                logger.warning(f"Transient email failure to {to_email} (code={code}). Cooldown applied. Error: {msg}")
            else:
                logger.error(f"Failed to send OTP email to {to_email}: {msg}")
            return False

    def _lookup_phone_by_order_id(self, order_id: int):
        try:
            with connection.cursor() as cursor:
                # Try standard orders
                cursor.execute(
                    """
                    SELECT r.mobileNumber
                    FROM orders o
                    JOIN registrations r ON o.user_id = r.user_id
                    WHERE o.order_id = %s
                    LIMIT 1
                    """,
                    [order_id]
                )
                row = cursor.fetchone()
                if row and row[0]:
                    return row[0]

                # Try grocery orders
                cursor.execute(
                    """
                    SELECT r.mobileNumber
                    FROM Groceries_orders go
                    JOIN registrations r ON go.user_id = r.user_id
                    WHERE go.order_id = %s
                    LIMIT 1
                    """,
                    [order_id]
                )
                row = cursor.fetchone()
                if row and row[0]:
                    return row[0]
        except Exception as exc:
            logger.error(f"Failed to lookup phone for order {order_id}: {exc}")
        return None

    def send_whatsapp_otp(self, phone_number: str, otp_code: str, template_type: str = "login") -> dict:
        """
        Send OTP via WhatsApp using Interakt API with smart template detection.
        Returns the Interakt response dict with keys like {'ok': bool, 'response': {...}}.
        """
        # Reset WhatsApp meta
        self._whatsapp_throttled = False
        self._whatsapp_last_error_code = None
        self._whatsapp_last_error_message = None

        try:
            from consumer.utils.interakt import InteraktClient

            if not phone_number:
                self._whatsapp_last_error_message = "Missing recipient phone number"
                return {"ok": False, "error": "Missing recipient phone number"}

            # Normalize digits only
            phone_number = ''.join(filter(str.isdigit, str(phone_number)))

            # Per-recipient cooldown
            cooldown_key = f"otp_whatsapp_cooldown:{phone_number}"
            if cache.get(cooldown_key):
                self._whatsapp_throttled = True
                self._whatsapp_last_error_message = "Recipient is in WhatsApp cooldown window due to previous throttling"
                return {"ok": False, "error": "WhatsApp cooldown active"}

            client = InteraktClient()

            template_configs = [
                {
                    "name": "delivery_otp_customer",
                    "language": "en_US" if template_type.lower() == "login" else "en",
                    "body_values": [otp_code],
                    "button_values": {"0": [otp_code]}
                },
                {
                    "name": "pickup_otp_for_collection",
                    "language": "en_US" if template_type.lower() == "login" else "en",
                    "body_values": ["ORDER001", otp_code, "Kirazee"],
                    "button_values": None
                }
            ]

            last_error = None
            for config in template_configs:
                try:
                    kwargs = {
                        "country_code": "+91",
                        "phone_number": phone_number,
                        "template_name": config["name"],
                        "language_code": config["language"],
                        "body_values": config["body_values"],
                        "callback_data": f"type={template_type}_otp"
                    }
                    if config["button_values"]:
                        kwargs["button_values"] = config["button_values"]

                    result = client.send_template(**kwargs)
                    if result.get('ok', False):
                        return result
                    else:
                        # Detect transient/rate errors to apply cooldown
                        msg = str(result.get('response', {}).get('message', 'Unknown error'))
                        last_error = msg
                        if any(t in msg.lower() for t in ['rate', 'quota', '429', 'too many', 'throttle', 'temporar']):
                            cache.set(cooldown_key, True, timeout=10 * 60)
                            self._whatsapp_throttled = True
                            self._whatsapp_last_error_message = msg
                            self._whatsapp_last_error_code = '429'
                except Exception as e:
                    last_error = str(e)
                    cache.set(cooldown_key, True, timeout=5 * 60)
                    self._whatsapp_throttled = True
                    self._whatsapp_last_error_message = str(e)
                    self._whatsapp_last_error_code = None

            return {
                "ok": False,
                "error": last_error or "No working WhatsApp templates found. Please create and approve OTP templates in your Interakt dashboard.",
                "suggestion": "Create a template named 'kirazee_login_otp' with body: 'Your Kirazee login OTP is {{1}}' and approve it."
            }

        except ImportError:
            return {"ok": False, "error": "InteraktClient not available"}
        except Exception as e:
            return {"ok": False, "error": str(e)}

@swagger_auto_schema(tags=['Delivery'])
class SendOrderOTPView(OrderOTPMixin, APIView):
    def post(self, request):
        order_id = request.query_params.get('order_id')
        if not order_id:
            return Response({"error": "order_id parameter is required"}, status=status.HTTP_400_BAD_REQUEST)

        try:
            order_id = int(order_id)
        except (TypeError, ValueError):
            return Response({"error": "order_id must be an integer"}, status=status.HTTP_400_BAD_REQUEST)

        context = self._extract_order(order_id)
        if not context:
            return Response({"error": "Order not found"}, status=status.HTTP_404_NOT_FOUND)

        otp_instance = OrderOTP.generate_otp(order_id, self.otp_expiry_minutes)

        subject = f"Your Kirazee order OTP #{order_id}"
        email_message = (
            f"Hi {context['name']},\n\n"
            f"Your one-time password for order {order_id} is {otp_instance.otp}."
            f" It will expire in {self.otp_expiry_minutes} minutes.\n\n"
            "Thank you for using Kirazee!"
        )
        email_sent = self._send_email(context['email'], subject, email_message)
        phone_number = context.get('phone_number') or self._lookup_phone_by_order_id(order_id)
        whatsapp_sent = self.send_whatsapp_otp(phone_number, otp_instance.otp)

        try:
            user_obj = context.get('user')
            if user_obj and getattr(user_obj, 'user_id', None):
                on_otp_sent(int(user_obj.user_id), order_id, otp_instance.otp)
        except Exception:
            pass

        return Response({
            "success": True,
            "message": "OTP generated successfully",
            "email_sent": email_sent,
            "whatsapp_sent": whatsapp_sent,
            "email_throttled": getattr(self, '_email_throttled', False),
            "email_error_code": getattr(self, '_email_last_error_code', None),
            "email_error": getattr(self, '_email_last_error_message', None),
            "order_id": order_id,
            "otp": otp_instance.otp,
            "whatsapp_throttled": getattr(self, '_whatsapp_throttled', False),
            "whatsapp_error_code": getattr(self, '_whatsapp_last_error_code', None),
            "whatsapp_error": getattr(self, '_whatsapp_last_error_message', None)
        })

@swagger_auto_schema(tags=['Delivery'])
class VerifyOrderOTPView(OrderOTPMixin, APIView):
    def post(self, request):
        order_id = request.query_params.get('order_id')
        user_otp = (request.data.get('otp') or '').strip()

        if not order_id:
            return Response({"error": "order_id parameter is required"}, status=status.HTTP_400_BAD_REQUEST)
        if not user_otp:
            return Response({"error": "otp is required"}, status=status.HTTP_400_BAD_REQUEST)

        try:
            order_id = int(order_id)
        except (TypeError, ValueError):
            return Response({"error": "order_id must be an integer"}, status=status.HTTP_400_BAD_REQUEST)

        context = self._extract_order(order_id)
        if not context:
            return Response({"error": "Order not found"}, status=status.HTTP_404_NOT_FOUND)

        otp_record = OrderOTP.objects.filter(order_id=order_id).order_by('-created_at').first()

        if otp_record and not otp_record.is_expired() and otp_record.otp == user_otp:
            otp_record.mark_verified()

            # If this is a regular order (not groceries) and type is delivery,
            # and there is a pending COD (pay-later) payment, mark it as SUCCESS.
            payment_updated = False
            order_confirmed = False
            try:
                if not context.get('is_grocery', False):
                    order_obj = context.get('order_obj')
                    if order_obj and str(order_obj.order_type) == Orders.OrderType.DELIVERY:
                        p = Payments.objects.filter(
                            order_id=order_id,
                            status=Payments.Status.PENDING,
                            payment_method=Payments.Method.COD
                        ).order_by('-created_at').first()
                        if p:
                            p.status = Payments.Status.SUCCESS
                            p.payment_source = 'delivery_partner_otp'
                            p.save()
                            payment_updated = True
                            if order_obj.status == Orders.OrderStatus.PENDING:
                                order_obj.confirm_order()
                                order_obj.save()
                                order_confirmed = True
            except Exception as _e:
                # don't fail OTP flow if payment update fails
                pass

            return Response({
                "success": True,
                "message": "OTP verified successfully",
                "payment_updated": payment_updated,
                "order_confirmed": order_confirmed
            })

        if context['is_grocery']:
            pickup_otp = getattr(context['order_obj'], 'pickup_otp', None)
            if pickup_otp and str(pickup_otp).strip() == user_otp:
                OrderOTP.objects.create(
                    order_id=order_id,
                    otp=user_otp,
                    is_verified=True,
                    expires_at=None
                )
                return Response({"success": True, "message": "Pickup OTP verified successfully"})

        return Response({"error": "Invalid or expired OTP"}, status=status.HTTP_400_BAD_REQUEST)

@swagger_auto_schema(tags=['Delivery'])
class ResendOrderOTPView(OrderOTPMixin, APIView):
    def post(self, request):
        order_id = request.query_params.get('order_id')
        if not order_id:
            return Response({"error": "order_id parameter is required"}, status=status.HTTP_400_BAD_REQUEST)

        try:
            order_id = int(order_id)
        except (TypeError, ValueError):
            return Response({"error": "order_id must be an integer"}, status=status.HTTP_400_BAD_REQUEST)

        context = self._extract_order(order_id)
        if not context:
            return Response({"error": "Order not found"}, status=status.HTTP_404_NOT_FOUND)

        otp_instance = OrderOTP.objects.filter(order_id=order_id).order_by('-created_at').first()

        if otp_instance and not otp_instance.is_verified:
            otp_code = otp_instance.refresh_otp(self.otp_expiry_minutes)
        else:
            otp_instance = OrderOTP.generate_otp(order_id, self.otp_expiry_minutes)
            otp_code = otp_instance.otp

        subject = f"Your Kirazee order OTP #{order_id}"
        email_message = (
            f"Hi {context['name']},\n\n"
            f"Your new one-time password for order {order_id} is {otp_code}."
            f" It will expire in {self.otp_expiry_minutes} minutes.\n\n"
            "Thank you for using Kirazee!"
        )
        email_sent = self._send_email(context['email'], subject, email_message)

        return Response({
            "success": True,
            "message": "OTP resent successfully",
            "email_sent": email_sent,
            "email_throttled": getattr(self, '_email_throttled', False),
            "email_error_code": getattr(self, '_email_last_error_code', None),
            "email_error": getattr(self, '_email_last_error_message', None),
            "order_id": order_id,
            "otp": otp_instance.otp
        })

@swagger_auto_schema(tags=['Delivery'])
class DeliveryPartnerListView(APIView):
    """
    GET /boys/
    Display delivery partners filtered by business and include summary stats.
    """
    
    def _get_partner_order_statistics(self, cursor, partner_id, business_id=None, dp_user_id=None):
        """Get order statistics for a delivery partner"""
        try:
            # In 'orders' table, delivery_partner_id stores Registration.user_id in our system.
            r_partner_id = dp_user_id or partner_id
            # Debug: Check what delivery partner IDs exist in orders table
            cursor.execute("SELECT DISTINCT delivery_partner_id FROM orders WHERE delivery_partner_id IS NOT NULL LIMIT 10")
            existing_partner_ids = cursor.fetchall()
            logger.info(f"Existing delivery_partner_ids in orders: {existing_partner_ids}")
            
            # Debug: Check if there's a delivery_partner column
            cursor.execute("SHOW COLUMNS FROM orders LIKE '%delivery%'")
            delivery_columns = cursor.fetchall()
            logger.info(f"Delivery columns in orders table: {delivery_columns}")
            
            # Debug: Check total orders count
            cursor.execute("SELECT COUNT(*) FROM orders")
            total_orders_count = cursor.fetchone()[0]
            logger.info(f"Total orders in database: {total_orders_count}")
            
            # Debug: Check if this partner has any orders at all (by dp.id and by user_id)
            cursor.execute("SELECT COUNT(*) FROM orders WHERE delivery_partner_id = %s", [partner_id])
            orders_by_dp_id = cursor.fetchone()[0]
            cursor.execute("SELECT COUNT(*) FROM orders WHERE delivery_partner_id = %s", [r_partner_id])
            orders_by_user_id = cursor.fetchone()[0]
            logger.info(f"Orders for partner_id={partner_id}: {orders_by_dp_id}, by user_id={r_partner_id}: {orders_by_user_id}")
            # Base query for regular orders - aggregate by all partner rows for this user_id
            regular_orders_query = """
                SELECT 
                    COUNT(*) as total_regular,
                    SUM(CASE WHEN status = 'delivered' THEN 1 ELSE 0 END) as completed_regular,
                    SUM(CASE WHEN status IN ('dispatched', 'travelling', 'out_for_delivery', 'assigned', 'picked_up', 'in_transit') THEN 1 ELSE 0 END) as pending_regular,
                    SUM(CASE WHEN status = 'cancelled' THEN 1 ELSE 0 END) as cancelled_regular
                FROM orders 
                WHERE (
                    delivery_partner_id IN (
                        SELECT id FROM delivery_partner WHERE user_id = %s
                    )
                    OR delivery_partner_id = %s
                )
            """
            
            params = [r_partner_id, r_partner_id]
            
            # Add business filter if provided
            if business_id:
                if isinstance(business_id, (list, tuple)):
                    placeholders = ','.join(['%s'] * len(business_id))
                    regular_orders_query += f" AND business_id IN ({placeholders})"
                    params.extend(list(business_id))
                else:
                    regular_orders_query += " AND business_id = %s"
                    params.append(business_id)
            
            cursor.execute(regular_orders_query, params)
            _reg = cursor.fetchone()
            # Coalesce to ints to avoid None/Decimal mixing
            if not _reg:
                regular_stats = (0, 0, 0, 0)
            else:
                regular_stats = (
                    int(_reg[0] or 0),
                    int(_reg[1] or 0),
                    int(_reg[2] or 0),
                    int(_reg[3] or 0),
                )
            
            # Get recent regular order IDs
            recent_regular_orders_query = """
                SELECT order_id, order_number, status, total_amount, created_at
                FROM orders 
                WHERE (
                    delivery_partner_id IN (
                        SELECT id FROM delivery_partner WHERE user_id = %s
                    )
                    OR delivery_partner_id = %s
                )
            """
            
            recent_params = [r_partner_id, r_partner_id]
            if business_id:
                if isinstance(business_id, (list, tuple)):
                    placeholders = ','.join(['%s'] * len(business_id))
                    recent_regular_orders_query += f" AND business_id IN ({placeholders})"
                    recent_params.extend(list(business_id))
                else:
                    recent_regular_orders_query += " AND business_id = %s"
                    recent_params.append(business_id)
            
            recent_regular_orders_query += " ORDER BY created_at DESC LIMIT 10"
            
            cursor.execute(recent_regular_orders_query, recent_params)
            recent_regular_orders = cursor.fetchall()
            
            # Query for grocery orders
            grocery_orders_query = """
                SELECT 
                    COUNT(*) as total_grocery,
                    SUM(CASE WHEN gdd.assignment_status = 'delivered' THEN 1 ELSE 0 END) as completed_grocery,
                    SUM(CASE WHEN gdd.assignment_status IN ('assigned', 'accepted', 'picked_up', 'in_transit') THEN 1 ELSE 0 END) as pending_grocery,
                    SUM(CASE WHEN gdd.assignment_status = 'cancelled' THEN 1 ELSE 0 END) as cancelled_grocery
                FROM Grocery_deliver_details gdd
                JOIN Groceries_orders go ON gdd.order_id = go.order_id
                WHERE gdd.partner_id = %s
            """
            
            # Grocery_deliver_details.partner_id stores Registration.user_id
            g_partner_id = dp_user_id or partner_id
            grocery_params = [g_partner_id]
            
            # Add business filter if provided
            if business_id:
                if isinstance(business_id, (list, tuple)):
                    placeholders = ','.join(['%s'] * len(business_id))
                    grocery_orders_query += f" AND go.business_id IN ({placeholders})"
                    grocery_params.extend(list(business_id))
                else:
                    grocery_orders_query += " AND go.business_id = %s"
                    grocery_params.append(business_id)
            
            cursor.execute(grocery_orders_query, grocery_params)
            _gro = cursor.fetchone()
            # Coalesce to ints to avoid None/Decimal mixing
            if not _gro:
                grocery_stats = (0, 0, 0, 0)
            else:
                grocery_stats = (
                    int(_gro[0] or 0),
                    int(_gro[1] or 0),
                    int(_gro[2] or 0),
                    int(_gro[3] or 0),
                )
            
            # Get recent grocery order IDs
            recent_grocery_orders_query = """
                SELECT go.order_id, CONCAT('GROC-', go.order_id) as order_number, gdd.assignment_status as status, go.final_amount, go.created_at
                FROM Grocery_deliver_details gdd
                JOIN Groceries_orders go ON gdd.order_id = go.order_id
                WHERE gdd.partner_id = %s
            """
            
            if business_id:
                if isinstance(business_id, (list, tuple)):
                    placeholders = ','.join(['%s'] * len(business_id))
                    recent_grocery_orders_query += f" AND go.business_id IN ({placeholders})"
                    # grocery_params already extended above for IN clause
                else:
                    recent_grocery_orders_query += " AND go.business_id = %s"
            
            recent_grocery_orders_query += " ORDER BY go.created_at DESC LIMIT 10"
            
            cursor.execute(recent_grocery_orders_query, grocery_params)
            recent_grocery_orders = cursor.fetchall()
            
            # Format recent orders
            recent_orders = []
            
            # Add regular orders
            for order in recent_regular_orders:
                recent_orders.append({
                    "order_id": str(order[0]),
                    "order_number": str(order[1]),
                    "status": order[2],
                    "amount": float(order[3]) if order[3] else 0.0,
                    "order_type": "regular",
                    "created_at": order[4].isoformat() if order[4] else None
                })
            
            # Add grocery orders
            for order in recent_grocery_orders:
                recent_orders.append({
                    "order_id": str(order[0]),
                    "order_number": str(order[1]),
                    "status": order[2],
                    "amount": float(order[3]) if order[3] else 0.0,
                    "order_type": "grocery",
                    "created_at": order[4].isoformat() if order[4] else None
                })
            
            # Sort by created_at desc
            recent_orders.sort(key=lambda x: x['created_at'] or '', reverse=True)
            recent_orders = recent_orders[:10]  # Keep only top 10
            
            # Calculate totals
            total_orders = regular_stats[0] + grocery_stats[0]
            completed_orders = regular_stats[1] + grocery_stats[1]
            pending_orders = regular_stats[2] + grocery_stats[2]
            cancelled_orders = regular_stats[3] + grocery_stats[3]
            
            return {
                "total_orders": total_orders,
                "completed_orders": completed_orders,
                "pending_orders": pending_orders,
                "cancelled_orders": cancelled_orders,
                "regular_orders": {
                    "total": regular_stats[0],
                    "completed": regular_stats[1],
                    "pending": regular_stats[2],
                    "cancelled": regular_stats[3]
                },
                "grocery_orders": {
                    "total": grocery_stats[0],
                    "completed": grocery_stats[1],
                    "pending": grocery_stats[2],
                    "cancelled": grocery_stats[3]
                },
                "recent_orders": recent_orders
            }
        except Exception as e:
            logger.error(f"Error getting order statistics for partner {partner_id}: {e}")
            return {
                "total_orders": 0,
                "completed_orders": 0,
                "pending_orders": 0,
                "cancelled_orders": 0,
                "regular_orders": {"total": 0, "completed": 0, "pending": 0, "cancelled": 0},
                "grocery_orders": {"total": 0, "completed": 0, "pending": 0, "cancelled": 0},
                "recent_orders": []
            }

    def _get_current_delivery_details(self, cursor, partner_id, business_id=None, dp_user_id=None):
        """Get current active delivery details for a delivery partner"""
        try:
            # For 'orders' table, use Registration.user_id where assigned
            r_partner_id = dp_user_id or partner_id
            # Check for current regular order delivery
            regular_delivery_query = """
                SELECT 
                    o.order_id,
                    o.order_number,
                    o.status,
                    o.total_amount,
                    o.order_type,
                    o.estimated_delivery_time,
                    o.created_at,
                    b.businessName,
                    b.address as business_address,
                    r.firstName,
                    r.lastName,
                    r.displayName,
                    r.mobileNumber,
                    JSON_UNQUOTE(JSON_EXTRACT(o.delivery_address_snapshot, '$.address')) as delivery_address
                FROM orders o
                LEFT JOIN businesses b ON o.business_id = b.business_id
                LEFT JOIN registrations r ON o.user_id = r.user_id
                WHERE o.delivery_partner_id IN (%s, %s)
                AND o.status IN ('dispatched', 'travelling', 'out_for_delivery', 'assigned', 'picked_up', 'in_transit')
            """
            
            params = [partner_id, r_partner_id]
            
            if business_id:
                if isinstance(business_id, (list, tuple)):
                    placeholders = ','.join(['%s'] * len(business_id))
                    regular_delivery_query += f" AND o.business_id IN ({placeholders})"
                    params.extend(list(business_id))
                else:
                    regular_delivery_query += " AND o.business_id = %s"
                    params.append(business_id)
            
            regular_delivery_query += " ORDER BY o.updated_at DESC LIMIT 1"
            
            cursor.execute(regular_delivery_query, params)
            current_order = cursor.fetchone()
            
            if not current_order:
                # Check for current grocery order delivery
                grocery_delivery_query = """
                    SELECT 
                        go.order_id,
                        CONCAT('GROC-', go.order_id) as order_number,
                        go.order_status as status,
                        go.final_amount as total_amount,
                        go.order_type,
                        go.delivery_time as estimated_delivery_time,
                        go.created_at,
                        b.businessName,
                        b.address as business_address,
                        r.firstName,
                        r.lastName,
                        r.displayName,
                        r.mobileNumber,
                        go.delivery_address
                    FROM Grocery_deliver_details gdd
                    JOIN Groceries_orders go ON gdd.order_id = go.order_id
                    LEFT JOIN businesses b ON go.business_id = b.business_id
                    LEFT JOIN registrations r ON go.user_id = r.user_id
                    WHERE gdd.partner_id = %s 
                    AND gdd.is_active = 1
                    AND go.order_status IN ('dispatched', 'travelling', 'out_for_delivery', 'dispatch')
                """
                
                # Grocery_deliver_details.partner_id stores Registration.user_id
                g_partner_id = dp_user_id or partner_id
                grocery_params = [g_partner_id]
                
                if business_id:
                    grocery_delivery_query += " AND go.business_id = %s"
                    grocery_params.append(business_id)
                
                grocery_delivery_query += " ORDER BY gdd.updated_at DESC LIMIT 1"
                
                cursor.execute(grocery_delivery_query, grocery_params)
                current_order = cursor.fetchone()
            
            if current_order:
                customer_name = current_order[11] or f"{current_order[9]} {current_order[10]}".strip() or "Customer"
                return {
                    'order_id': str(current_order[0]),
                    'order_number': str(current_order[1]),
                    'customer_name': customer_name,
                    'customer_phone': current_order[12],
                    'delivery_address': current_order[13] or 'Address not available',
                    'total_amount': float(current_order[3]) if current_order[3] else 0.0,
                    'order_type': current_order[4] or 'delivery',
                    'status': current_order[2],
                    'estimated_delivery_time': current_order[5].isoformat() if current_order[5] else None,
                    'business_name': current_order[7],
                    'business_address': current_order[8],
                    'order_date': current_order[6].isoformat() if current_order[6] else None
                }
            
            return None
            
        except Exception as e:
            logger.error(f"Error getting current delivery details for partner {partner_id}: {e}")
            return None

    def get(self, request):
        business_id = request.query_params.get('business_id')
        include_unassigned = request.query_params.get('include_unassigned', 'false').lower() == 'true'
        page = max(int(request.query_params.get('page', 1)), 1)
        limit = min(max(int(request.query_params.get('limit', 25)), 1), 100)
        offset = (page - 1) * limit

        try:
            with connection.cursor() as cursor:
                filters = ["(dp.status = 'available' OR dp.status = '1' OR dp.status = 1)"]
                params = []

                is_null_param = (business_id is None) or (str(business_id).strip().lower() in ('null', ''))
                if is_null_param:
                    filters.append("(dp.business_id IS NULL OR dp.business_id = '')")
                    business_ids = None
                else:
                    cursor.execute(
                        """
                        SELECT business_id, level, master
                        FROM businesses
                        WHERE business_id = %s AND status = 1
                        """,
                        [business_id]
                    )
                    row = cursor.fetchone()
                    root_master_id = business_id
                    if row:
                        root_master_id = row[0] if row[1] == 'master' else (row[2] if row[2] else row[0])
                    cursor.execute(
                        """
                        SELECT business_id
                        FROM businesses
                        WHERE (business_id = %s OR master = %s) AND status = 1
                        """,
                        [root_master_id, root_master_id]
                    )
                    biz_rows = cursor.fetchall()
                    business_ids = [r[0] for r in biz_rows] if biz_rows else [business_id]
                    placeholders = ','.join(['%s'] * len(business_ids))
                    if include_unassigned:
                        filters.append(f"(dp.business_id IN ({placeholders}) OR dp.business_id IS NULL OR dp.business_id = '')")
                    else:
                        filters.append(f"dp.business_id IN ({placeholders})")
                    params.extend(business_ids)

                filter_clause = " AND ".join(filters)

                base_query = f"""
                    SELECT
                        dp.id,
                        dp.user_id,
                        dp.business_id,
                        dp.vehicle_type,
                        dp.vehicle_number,
                        dp.phone_number,
                        dp.status,
                        dp.is_available,
                        dp.rating,
                        dp.total_deliveries,
                        dp.latitude,
                        dp.longitude,
                        dp.is_verified,
                        dp.created_at,
                        dp.updated_at,
                        r.displayName,
                        r.firstName,
                        r.lastName,
                        r.emailID,
                        dp.delivery_timings
                    FROM delivery_partner dp
                    LEFT JOIN registrations r ON dp.user_id = r.user_id
                    WHERE {filter_clause}
                    ORDER BY dp.created_at DESC
                    LIMIT %s OFFSET %s
                """

                cursor.execute(base_query, params + [limit, offset])
                rows = cursor.fetchall()

                count_query = f"""
                    SELECT COUNT(*)
                    FROM delivery_partner dp
                    WHERE {filter_clause}
                """

                cursor.execute(count_query, params)
                total_partners = cursor.fetchone()[0] if cursor.rowcount != -1 else 0

                partner_list = []
                for row in rows:
                    (dp_id, user_id, partner_business_id, vehicle_type, vehicle_number, phone_number,
                     dp_status, is_available, rating, total_deliveries, latitude, longitude,
                     is_verified, created_at, updated_at, display_name, first_name, last_name, email,
                     delivery_timings_raw) = row

                    full_name = display_name or " ".join(filter(None, [first_name, last_name])).strip() or "Delivery Partner"

                    # Get order statistics for this delivery partner
                    order_stats = self._get_partner_order_statistics(cursor, dp_id, business_ids if not is_null_param else None, dp_user_id=user_id)
                    
                    # Get current delivery details if any
                    current_delivery = self._get_current_delivery_details(cursor, dp_id, business_ids if not is_null_param else None, dp_user_id=user_id)

                    # Calculate total kilometers traveled from location history
                    # Note: deliverylocationhistory.delivery_partner_id references delivery_partner.user_id
                    cursor.execute("""
                        SELECT latitude, longitude, timestamp
                        FROM deliverylocationhistory 
                        WHERE delivery_partner_id = %s 
                        ORDER BY timestamp ASC
                    """, [user_id])
                    
                    location_history = cursor.fetchall()
                    total_kilometers = 0.0
                    location_updates_count = len(location_history)
                    
                    # Calculate distance between consecutive location points
                    if location_updates_count > 1:
                        for i in range(1, location_updates_count):
                            prev_lat, prev_lon, prev_time = location_history[i-1]
                            curr_lat, curr_lon, curr_time = location_history[i]
                            
                            # Calculate distance between consecutive points
                            distance = calculate_distance(prev_lat, prev_lon, curr_lat, curr_lon)
                            total_kilometers += distance

                    # Parse JSON delivery_timings
                    delivery_timings = None
                    try:
                        _dt = delivery_timings_raw
                        if isinstance(_dt, (bytes, bytearray)):
                            _dt = _dt.decode('utf-8')
                        delivery_timings = json.loads(_dt) if isinstance(_dt, str) and _dt else _dt
                    except Exception:
                        delivery_timings = None

                    partner_list.append({
                        "id": dp_id,
                        "user_id": user_id,
                        "business_id": partner_business_id,
                        "name": full_name,
                        "email": email,
                        "phone_number": phone_number,
                        "vehicle_type": vehicle_type,
                        "vehicle_number": vehicle_number,
                        "status": dp_status,
                        "is_available": bool(is_available),
                        "rating": float(rating) if rating is not None else 0.0,
                        "total_deliveries": int(total_deliveries) if total_deliveries is not None else 0,
                        "current_location": [latitude, longitude] if latitude is not None and longitude is not None else None,
                        "is_verified": bool(is_verified),
                        "created_at": created_at,
                        "updated_at": updated_at,
                        "delivery_timings": delivery_timings,
                        # Order summary
                        "order_summary": order_stats,
                        "current_delivery": current_delivery,
                        # Distance tracking
                        "total_kilometers_traveled": round(total_kilometers, 2),
                        "location_updates_count": location_updates_count
                    })

                total_pages = (total_partners + limit - 1) // limit if limit else 1

                return Response({
                    "success": True,
                    "message": "Delivery partners retrieved successfully",
                    "filters": {
                        "business_id": business_id,
                        "include_unassigned": include_unassigned,
                        "defaulting_to_unassigned": business_id is None,
                        "page": page,
                        "limit": limit
                    },
                    "pagination": {
                        "total_partners": total_partners,
                        "current_page": page,
                        "per_page": limit,
                        "total_pages": total_pages,
                        "has_next_page": page < total_pages,
                        "has_prev_page": page > 1
                    },
                    "providers": partner_list
                }, status=status.HTTP_200_OK)

        except Exception as exc:
            logger.error(f"Error listing delivery partners: {exc}")
            return Response({
                "success": False,
                "message": f"Error retrieving delivery partners: {exc}"
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@swagger_auto_schema(tags=['Delivery'])
class ActiveDeliveryPartnersView(APIView):
    """
    GET /display/active-partners/
    Display the list of partners who are active for business owners to assign orders
    """
    
    def get(self, request):
        try:
            # Get location parameters for distance calculation
            business_lat = request.query_params.get('lat')
            business_lng = request.query_params.get('lng')
            radius_km = float(request.query_params.get('radius', 5))  # Default 5km radius
            
            # Validate required parameters
            if not business_lat or not business_lng:
                return Response(
                    {"error": "lat and lng parameters are required"},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            try:
                business_lat = float(business_lat)
                business_lng = float(business_lng)
            except ValueError:
                return Response(
                    {"error": "lat and lng must be valid numbers"},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            # Haversine formula for distance calculation
            def calculate_distance(lat1, lon1, lat2, lon2):
                """Calculate distance between two points using Haversine formula"""
                import math
                
                # Convert latitude and longitude from degrees to radians
                lat1, lon1, lat2, lon2 = map(math.radians, [lat1, lon1, lat2, lon2])
                
                # Haversine formula
                dlat = lat2 - lat1
                dlon = lon2 - lon1
                a = math.sin(dlat/2)**2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon/2)**2
                c = 2 * math.asin(math.sqrt(a))
                
                # Radius of earth in kilometers
                r = 6371
                return c * r
            
            # Raw SQL to fetch active delivery partners with location data
            with connection.cursor() as cursor:
                cursor.execute("""
                    SELECT 
                        dp.id, dp.user_id, dp.vehicle_type, dp.vehicle_number, 
                        dp.latitude, dp.longitude, dp.status, dp.is_available, 
                        dp.rating, dp.total_deliveries, dp.phone_number,
                        r.firstName, r.lastName
                    FROM delivery_partner dp
                    JOIN registrations r ON dp.user_id = r.user_id
                    WHERE dp.status = 1
                    AND dp.latitude IS NOT NULL AND dp.longitude IS NOT NULL
                    ORDER BY dp.rating DESC, dp.total_deliveries DESC
                """)
                
                partners = []
                partners_within_radius = []
                
                for row in cursor.fetchall():
                    partner_lat = float(row[4]) if row[4] else None
                    partner_lng = float(row[5]) if row[5] else None
                    
                    # Skip partners without location data
                    if partner_lat is None or partner_lng is None:
                        continue
                    
                    # Calculate distance using Haversine formula
                    distance = calculate_distance(business_lat, business_lng, partner_lat, partner_lng)
                    
                    partner_data = {
                        'id': row[0],
                        'user_id': row[1],
                        'name': f"{row[11]} {row[12]}",  # firstName + lastName
                        'phone_number': row[10],
                        'vehicle_type': row[2].lower() if row[2] else None,
                        'vehicle_number': row[3],
                        'rating': float(row[8]) if row[8] else 0.0,
                        'total_deliveries': int(row[9]) if row[9] else 0,
                        'current_location': [partner_lat, partner_lng],
                        'distance_km': round(distance, 2),
                        'is_available': bool(int(row[7])),
                        'status': '1' if str(row[6]) == '1' else '0',
                        'within_radius': distance <= radius_km
                    }
                    
                    # Add to all partners list
                    partners.append(partner_data)
                    
                    # Add to nearby partners if within radius
                    if distance <= radius_km:
                        partners_within_radius.append(partner_data)
                
                # Sort partners within radius by distance (closest first)
                partners_within_radius.sort(key=lambda x: x['distance_km'])
                
                # Sort all partners by distance for reference
                partners.sort(key=lambda x: x['distance_km'])
                
                return Response({
                    "success": True,
                    "search_location": {
                        "latitude": business_lat,
                        "longitude": business_lng,
                        "radius_km": radius_km
                    },
                    "total_active_partners": len(partners),
                    "partners_within_radius": len(partners_within_radius),
                    "nearby_partners": partners_within_radius,
                    "all_partners_sorted_by_distance": partners[:10]  # Show top 10 closest for reference
                })
                
        except Exception as e:
            logger.error(f"Error fetching active delivery partners: {str(e)}")
            return Response(
                {"error": f"Failed to fetch active delivery partners: {str(e)}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

@swagger_auto_schema(tags=['Delivery'])
class AssignOrderView(APIView):
    """
    POST /assign-order/
    Assign an order to a delivery partner from either standard orders or grocery orders
    Automatically detects which system to use based on order_id
    """
    
    def detect_order_type(self, order_id):
        """
        Detect which order system the order belongs to
        Returns: 'standard', 'grocery', or None
        """
        try:
            with connection.cursor() as cursor:
                # Check if order exists in standard orders table
                cursor.execute("SELECT order_id FROM orders WHERE order_id = %s", [order_id])
                if cursor.fetchone():
                    return 'standard'
                
                # Check if order exists in grocery orders table
                cursor.execute("SELECT order_id FROM Groceries_orders WHERE order_id = %s", [order_id])
                if cursor.fetchone():
                    return 'grocery'
                
                return None
        except Exception as e:
            logger.error(f"Error detecting order type: {str(e)}")
            return None
    
    def post(self, request):
        order_id = request.query_params.get('order_id')
        if not order_id:
            return Response(
                {"error": "order_id parameter is required"},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Standardized parameters for both systems
        delivery_partner_id = request.data.get('delivery_partner_id')
        assigned_by_user_id = request.data.get('assigned_by_user_id')
        
        if not delivery_partner_id:
            return Response(
                {"error": "delivery_partner_id is required"},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Detect which order system to use
        order_type = self.detect_order_type(order_id)
        
        if not order_type:
            return Response(
                {"error": "Order not found in any system"},
                status=status.HTTP_404_NOT_FOUND
            )
        
        try:
            if order_type == 'standard':
                return self._assign_standard_order(order_id, delivery_partner_id)
            elif order_type == 'grocery':
                return self._assign_grocery_order(order_id, delivery_partner_id, assigned_by_user_id)
                
        except Exception as e:
            logger.error(f"Error assigning order {order_id}: {str(e)}")
            return Response(
                {"error": f"Failed to assign order: {str(e)}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    def _assign_standard_order(self, order_id, delivery_partner_id):
        """Assign order from standard orders table using user_id"""
        if not delivery_partner_id:
            return Response(
                {"error": "delivery_partner_id is required for standard orders"},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            with connection.cursor() as cursor:
                # Check if order exists and is not already assigned
                cursor.execute("""
                    SELECT order_id, status, delivery_partner_id 
                    FROM orders 
                    WHERE order_id = %s
                """, [order_id])
                
                order_row = cursor.fetchone()
                if not order_row:
                    return Response(
                        {"error": "Standard order not found"},
                        status=status.HTTP_404_NOT_FOUND
                    )
                
                if order_row[2]:  # delivery_partner_id already exists
                    existing_partner_id = str(order_row[2])
                    if existing_partner_id == str(delivery_partner_id):
                        return Response({
                            "success": True,
                            "message": "Standard order already assigned to this delivery partner",
                            "order_id": order_id,
                            "order_type": "standard",
                            "delivery_system": "standard",
                            "delivery_partner_id": delivery_partner_id,
                            "partner_user_id": delivery_partner_id
                        })
                    return Response(
                        {"error": "Standard order is already assigned to a delivery partner"},
                        status=status.HTTP_400_BAD_REQUEST
                    )
                
                if order_row[1] not in ['confirmed', 'ready', 'dispatch', 'preparing']:
                    return Response(
                        {"error": f"Standard order status '{order_row[1]}' is not available for assignment"},
                        status=status.HTTP_400_BAD_REQUEST
                    )
                
                # Check if delivery partner is available using user_id
                cursor.execute("""
                    SELECT id, is_available, status, user_id 
                    FROM delivery_partner 
                    WHERE user_id = %s
                """, [delivery_partner_id])
                
                partner_row = cursor.fetchone()
                if not partner_row:
                    return Response(
                        {"error": "Delivery partner not found"},
                        status=status.HTTP_404_NOT_FOUND
                    )
                
                if not bool(int(partner_row[1])) or str(partner_row[2]) != '1':
                    return Response(
                        {"error": "Delivery partner is not available"},
                        status=status.HTTP_400_BAD_REQUEST
                    )
                
                # Use the user_id directly for assignment
                partner_user_id = delivery_partner_id
                delivery_partner_table_id = partner_row[0]
                
                # Assign order to delivery partner using user_id
                cursor.execute("""
                    UPDATE orders 
                    SET delivery_partner_id = %s, 
                        status = 'assigned', 
                        updated_at = NOW()
                    WHERE order_id = %s
                """, [partner_user_id, order_id])
                
                # Update delivery partner status using the table id
                cursor.execute("""
                    UPDATE delivery_partner 
                    SET is_available = 1, 
                        status = '1',
                        updated_at = NOW()
                    WHERE id = %s
                """, [delivery_partner_table_id])
                
                send_order_notification(
                    partner_user_id,
                    "New Delivery Assigned",
                    f"You have been assigned order #{order_id}.",
                    {"type": "DELIVERY_ORDER_ASSIGNED", "order_id": str(order_id), "order_type": "standard", "notification_for": "delivery_partner"}
                )

                return Response({
                    "success": True,
                    "message": "Standard order assigned to delivery partner successfully",
                    "order_id": order_id,
                    "order_type": "standard",
                    "delivery_system": "standard",
                    "delivery_partner_id": delivery_partner_id,
                    "partner_user_id": partner_user_id
                })
                
        except Exception as e:
            logger.error(f"Error assigning standard order: {str(e)}")
            raise e
    
    def _assign_grocery_order(self, order_id, delivery_partner_id, assigned_by_user_id):
        """Assign order from grocery orders table and create delivery assignment"""
        if not delivery_partner_id:
            return Response(
                {"error": "delivery_partner_id is required for grocery orders"},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        if not assigned_by_user_id:
            return Response(
                {"error": "assigned_by_user_id is required for grocery orders"},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            with connection.cursor() as cursor:
                # Check if grocery order is available for assignment
                cursor.execute("""
                    SELECT go.order_id, go.order_status, go.order_type, go.payment_status,
                           gdd.delivery_detail_id
                    FROM Groceries_orders go
                    LEFT JOIN Grocery_deliver_details gdd ON go.order_id = gdd.order_id AND gdd.is_active = 1
                    WHERE go.order_id = %s
                """, [order_id])
                
                order_row = cursor.fetchone()
                if not order_row:
                    return Response(
                        {"error": "Grocery order not found"},
                        status=status.HTTP_404_NOT_FOUND
                    )
                
                if order_row[4]:  # delivery_detail_id already exists
                    return Response(
                        {"error": "Grocery order is already assigned to another partner"},
                        status=status.HTTP_400_BAD_REQUEST
                    )
                
                if order_row[1] not in ['pending', 'confirmed', 'packed', 'preparing']:  # order_status
                    return Response(
                        {"error": f"Grocery order status '{order_row[1]}' is not available for assignment"},
                        status=status.HTTP_400_BAD_REQUEST
                    )
                
                if order_row[2] != 'delivery':  # order_type
                    return Response(
                        {"error": "Only delivery orders can be assigned to delivery partners"},
                        status=status.HTTP_400_BAD_REQUEST
                    )
                
                # Check if partner user exists and is a delivery partner
                cursor.execute("""
                    SELECT dp.id, dp.is_available, dp.status, r.user_id 
                    FROM delivery_partner dp
                    JOIN registrations r ON dp.user_id = r.user_id
                    WHERE dp.user_id = %s
                """, [delivery_partner_id])
                partner_row = cursor.fetchone()
                if not partner_row:
                    return Response(
                        {"error": "Partner user not found or not registered as delivery partner"},
                        status=status.HTTP_404_NOT_FOUND
                    )
                
                # Check if delivery partner is available
                if not bool(int(partner_row[1])) or str(partner_row[2]) != '1':
                    return Response(
                        {"error": "Delivery partner is not available"},
                        status=status.HTTP_400_BAD_REQUEST
                    )
                
                # Check if assigning user exists
                cursor.execute("SELECT user_id FROM registrations WHERE user_id = %s", [assigned_by_user_id])
                if not cursor.fetchone():
                    return Response(
                        {"error": "Assigning user not found"},
                        status=status.HTTP_404_NOT_FOUND
                    )
                
                # Generate OTP for grocery delivery
                import random
                delivery_otp = str(random.randint(100000, 999999))
                
                # Create delivery assignment in Grocery_deliver_details
                cursor.execute("""
                    INSERT INTO Grocery_deliver_details 
                    (order_id, partner_id, assigned_by_user_id, assignment_status, delivery_otp, assigned_at, is_active)
                    VALUES (%s, %s, %s, 'assigned', %s, NOW(), 1)
                """, [order_id, delivery_partner_id, assigned_by_user_id, delivery_otp])
                
                # Update grocery order status
                cursor.execute("""
                    UPDATE Groceries_orders 
                    SET order_status = 'assigned', 
                        updated_at = NOW()
                    WHERE order_id = %s
                """, [order_id])
                
                # Update delivery partner status to unavailable
                cursor.execute("""
                    UPDATE delivery_partner 
                    SET is_available = 1, 
                        status = '1',
                        updated_at = NOW()
                    WHERE user_id = %s
                """, [delivery_partner_id])
                
                send_order_notification(
                    delivery_partner_id,
                    "New Delivery Assigned",
                    f"You have been assigned grocery order #{order_id}.",
                    {"type": "DELIVERY_ORDER_ASSIGNED", "order_id": str(order_id), "order_type": "grocery", "notification_for": "delivery_partner"}
                )

                return Response({
                    "success": True,
                    "message": "Grocery order assigned to delivery partner successfully",
                    "order_id": order_id,
                    "order_type": "grocery",
                    "delivery_system": "grocery",
                    "delivery_partner_id": delivery_partner_id,
                    "assigned_by_user_id": assigned_by_user_id,
                    "delivery_otp": delivery_otp,
                    "assignment_status": "assigned"
                })
                
        except Exception as e:
            logger.error(f"Error assigning grocery order: {str(e)}")
            raise e

@swagger_auto_schema(tags=['Delivery'])
class DeliveryPartnerOrdersView(APIView):
    """
    GET /display-took-orders/?user_id=[value]
    Display the assigned and accepted orders for a delivery partner from both delivery systems
    """

    @staticmethod
    def safe_float(value):
        """Safely convert values that may be null or string 'null' to float."""
        if value is None:
            return None
        if isinstance(value, str) and value.strip().lower() in {"", "null", "none"}:
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return None
    
    def get(self, request):
        user_id = request.query_params.get('user_id')
        include_items_preview = request.query_params.get('include_items_preview')
        
        if not user_id:
            return Response(
                {"error": "user_id parameter is required"},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            with connection.cursor() as cursor:
                # Check if delivery partner exists for this user_id (standard delivery system)
                cursor.execute("SELECT id FROM delivery_partner WHERE user_id = %s", [user_id])
                standard_partner_row = cursor.fetchone()
                
                # Check if grocery delivery partner exists for this user_id
                cursor.execute("SELECT user_id FROM registrations WHERE user_id = %s", [user_id])
                user_exists = cursor.fetchone()
                
                if not standard_partner_row and not user_exists:
                    return Response(
                        {"error": "Delivery partner not found"},
                        status=status.HTTP_404_NOT_FOUND
                    )
                
                # Get all business IDs that this partner should see orders from (including sub-businesses)
                all_business_ids = set()
                if standard_partner_row:
                    # Get all businesses where this partner has orders assigned
                    cursor.execute("""
                        SELECT DISTINCT o.business_id 
                        FROM orders o 
                        WHERE o.delivery_partner_id = %s
                    """, [user_id])
                    
                    assigned_business_ids = [row[0] for row in cursor.fetchall()]
                    all_business_ids.update(assigned_business_ids)
                    
                    # For each business, check if it's a master and get all related businesses
                    for business_id in assigned_business_ids:
                        # Check if this business is a master business
                        cursor.execute("""
                            SELECT business_id, level 
                            FROM businesses 
                            WHERE business_id = %s AND status = 1
                        """, [business_id])
                        
                        business_info = cursor.fetchone()
                        if business_info and business_info[1] == 'master':
                            # Get all sub-businesses
                            cursor.execute("""
                                SELECT business_id 
                                FROM businesses 
                                WHERE master = %s AND status = 1
                            """, [business_id])
                            
                            sub_businesses = cursor.fetchall()
                            for sub_business in sub_businesses:
                                all_business_ids.add(sub_business[0])

                # Fetch standard delivery orders (from orders table)
                standard_orders = []
                if standard_partner_row:
                    cursor.execute(
                        """
                        SELECT 
                            o.order_id, o.order_number, o.status, o.final_amount, o.order_type,
                            o.created_at, o.updated_at, o.delivery_charges,
                            b.businessName, b.address as business_address,
                            r.firstName, r.lastName, r.mobileNumber,
                            CONCAT_WS(', ',
                                CONCAT('Door No: ', JSON_UNQUOTE(JSON_EXTRACT(ua.address, '$."Door no"'))),
                                JSON_UNQUOTE(JSON_EXTRACT(ua.address, '$.street')),
                                JSON_UNQUOTE(JSON_EXTRACT(ua.address, '$."city/town"')),
                                JSON_UNQUOTE(JSON_EXTRACT(ua.address, '$.state')),
                                CONCAT('Pincode: ', JSON_UNQUOTE(JSON_EXTRACT(ua.address, '$.pincode')))
                            ) AS delivery_address,
                            CONCAT_WS(', ',
                                CONCAT('Landmark: ', JSON_UNQUOTE(JSON_EXTRACT(ua.address, '$.landmark'))),
                                CONCAT('Contact: ', r.mobileNumber)
                            ) AS delivery_instructions,
                            o.business_id,
                            b.businessName as business_name_detail,
                            b.latitude AS business_latitude,
                            b.longitude AS business_longitude,
                            b.landmark AS business_landmark,
                            b.city AS business_city,
                            b.state AS business_state,
                            b.pincode AS business_pincode,
                            COALESCE(
                                JSON_UNQUOTE(JSON_EXTRACT(ua.address, '$.latitude')),
                                JSON_UNQUOTE(JSON_EXTRACT(ua.address, '$.lat'))
                            ) AS consumer_latitude,
                            COALESCE(
                                JSON_UNQUOTE(JSON_EXTRACT(ua.address, '$.longitude')),
                                JSON_UNQUOTE(JSON_EXTRACT(ua.address, '$.lng'))
                            ) AS consumer_longitude,
                            o.token_num AS token_num
                        FROM orders o
                        JOIN businesses b ON o.business_id = b.business_id
                        JOIN registrations r ON o.user_id = r.user_id
                        LEFT JOIN user_address ua ON o.delivery_address_id = ua.id
                        WHERE o.delivery_partner_id = %s
                        AND o.status IN ('picked_up', 'out_for_delivery', 'ready', 'mark_ready', 'accepted')
                        ORDER BY o.created_at DESC
                    """, [user_id])
                    
                    for row in cursor.fetchall():
                        # Format business address with landmark, city, state, pincode
                        business_address_parts = []
                        if row[9]:  # business_address (index 9)
                            business_address_parts.append(row[9])
                        if row[20]:  # business_landmark (index 20)
                            business_address_parts.append(f"Landmark: {row[20]}")
                        if row[21]:  # business_city (index 21)
                            business_address_parts.append(row[21])
                        if row[22]:  # business_state (index 22)
                            business_address_parts.append(row[22])
                        if row[23]:  # business_pincode (index 23)
                            business_address_parts.append(f"Pincode: {row[23]}")
                        
                        formatted_business_address = ', '.join(business_address_parts) if business_address_parts else row[9] or 'Address not available'

                        order_data = {
                            'order_id': row[0],
                            'order_number': row[1],
                            'token_num': row[25] if len(row) > 25 else None,
                            'business_id': row[15],  # business_id from query
                            'business_name': row[16],  # business_name_detail from query
                            'business_address': formatted_business_address,
                            'customer_name': f"{row[10]} {row[11]}",
                            'customer_phone': row[12],
                            'delivery_instructions': row[14] or "",  # delivery_instructions
                            'total_amount': float(row[3]) if row[3] else 0.0,
                            'status': row[2],
                            'order_type': 'standard',
                            'delivery_system': 'standard',
                            'created_at': row[5],
                            'updated_at': row[6],
                            'delivery_charges': float(row[7]) if row[7] else 0.0,
                            # New explicit fields
                            'business_address': formatted_business_address,
                            'business_lat': self.safe_float(row[17]),  # business_latitude
                            'business_lng': self.safe_float(row[18]),  # business_longitude
                            'consumer_address': row[13] or "Address not available",  # delivery_address
                            'consumer_lat': self.safe_float(row[23]),  # consumer_latitude
                            'consumer_lon': self.safe_float(row[24]),  # consumer_longitude
                            'estimated_delivery_time': "30-45 minutes"
                        }
                        standard_orders.append(order_data)
                
                # Fetch grocery delivery orders (from Grocery_deliver_details table)
                grocery_orders = []
                if user_exists:
                    cursor.execute("""
                        SELECT 
                            gdd.delivery_detail_id,
                            gdd.order_id,
                            gdd.assignment_status,
                            gdd.delivery_otp,
                            gdd.assigned_at,
                            gdd.delivered_at,
                            go.total_amount,
                            go.gst_amount,
                            go.delivery_charge,
                            go.discount,
                            go.final_amount,
                            go.order_status,
                            go.delivery_address,
                            go.delivery_instructions,
                            go.created_at,
                            go.updated_at,
                            b.business_id,
                            b.businessName,
                            b.address AS business_address,
                            b.latitude AS business_latitude,
                            b.longitude AS business_longitude,
                            b.landmark AS business_landmark,
                            b.city AS business_city,
                            b.state AS business_state,
                            b.pincode AS business_pincode,
                            r.firstName,
                            r.lastName,
                            r.mobileNumber,
                            COALESCE(
                                JSON_UNQUOTE(JSON_EXTRACT(ua.address, '$.latitude')),
                                JSON_UNQUOTE(JSON_EXTRACT(ua.address, '$.lat'))
                            ) AS consumer_latitude,
                            COALESCE(
                                JSON_UNQUOTE(JSON_EXTRACT(ua.address, '$.longitude')),
                                JSON_UNQUOTE(JSON_EXTRACT(ua.address, '$.lng'))
                            ) AS consumer_longitude
                        FROM Grocery_deliver_details gdd
                        JOIN Groceries_orders go ON gdd.order_id = go.order_id
                        JOIN businesses b ON go.business_id = b.business_id
                        JOIN registrations r ON go.user_id = r.user_id
                        LEFT JOIN user_address ua ON ua.user_id = go.user_id AND ua.is_default = 1
                        WHERE gdd.partner_id = %s
                        AND gdd.assignment_status IN ('assigned', 'accepted', 'out_for_delivery')
                        AND go.order_status IN ('picked_up', 'out_for_delivery', 'ready', 'mark_ready', 'accepted')
                        AND gdd.is_active = 1
                        ORDER BY gdd.assigned_at DESC
                    """, [user_id])

                    for row in cursor.fetchall():
                        # Format business address with landmark, city, state, pincode for grocery orders
                        business_address_parts = []
                        if row[17]:  # business_address
                            business_address_parts.append(row[17])
                        if row[21]:  # business_landmark
                            business_address_parts.append(f"Landmark: {row[21]}")
                        if row[22]:  # business_city
                            business_address_parts.append(row[22])
                        if row[23]:  # business_state
                            business_address_parts.append(row[23])
                        if row[24]:  # business_pincode
                            business_address_parts.append(f"Pincode: {row[24]}")
                        
                        formatted_business_address = ', '.join(business_address_parts) if business_address_parts else row[17] or 'Address not available'

                        order_data = {
                            'delivery_detail_id': row[0],
                            'order_id': row[1],
                            'assignment_status': row[2],
                            'delivery_otp': row[3],
                            'business_id': row[16],
                            'business_name': row[17],
                            'customer_name': f"{row[25]} {row[26]}",
                            'customer_phone': row[27],
                            'delivery_instructions': row[13] or "",
                            'total_amount': float(row[6]) if row[6] else 0.0,
                            'gst_amount': float(row[7]) if row[7] else 0.0,
                            'delivery_charge': float(row[8]) if row[8] else 0.0,
                            'discount': float(row[9]) if row[9] else 0.0,
                            'final_amount': float(row[10]) if row[10] else 0.0,
                            'order_type': 'grocery',
                            'delivery_system': 'grocery',
                            'assigned_at': row[4],
                            'delivered_at': row[5],
                            'created_at': row[14],
                            'updated_at': row[15],
                            'business_address': formatted_business_address,
                            'business_lat': self.safe_float(row[18]),
                            'business_lng': self.safe_float(row[19]),
                            'status': row[11],
                            'consumer_address': row[12] or "Address not available",
                            'consumer_lat': self.safe_float(row[28]),
                            'consumer_lon': self.safe_float(row[29]),
                            'estimated_delivery_time': "30-45 minutes"  # Grocery orders typically take longer
                        }
                        grocery_orders.append(order_data)
                
                response_data = {
                    "success": True,
                    "total_count": len(standard_orders) + len(grocery_orders),
                    "standard_delivery": {
                        "count": len(standard_orders),
                        "orders": standard_orders
                    },
                    "grocery_delivery": {
                        "count": len(grocery_orders),
                        "orders": grocery_orders
                    }
                }

                try:
                    if include_items_preview and str(include_items_preview).strip().lower() in ('1', 'true', 'yes'):
                        GroceryOrdersService.attach_items_preview_to_standard_orders(standard_orders)
                        GroceryOrdersService.attach_items_preview_to_grocery_orders(grocery_orders)
                except Exception as exc:
                    logger.error(f"Failed to attach items preview in DeliveryPartnerOrdersView: {exc}")

                return Response(response_data)
                
        except Exception as e:
            logger.error(f"Error fetching delivery partner orders: {str(e)}")
            return Response(
                {"error": f"Failed to fetch orders: {str(e)}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


@swagger_auto_schema(tags=['Delivery'])
class DeliveryOrderHistoryView(APIView):
    """
    GET /delivery-order-history/?user_id=[value]
    Display the list of delivered orders history for a delivery partner
    """
    
    def get(self, request):
        user_id = request.query_params.get('user_id')
        
        if not user_id:
            return Response(
                {"error": "user_id parameter is required"},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            with connection.cursor() as cursor:
                # Check if a delivery partner exists for this user_id
                cursor.execute("SELECT id FROM delivery_partner WHERE user_id = %s", [user_id])
                if not cursor.fetchone():
                    return Response(
                        {"error": "Delivery partner not found"},
                        status=status.HTTP_404_NOT_FOUND
                    )
                
                # Enhanced query to fetch history with better address information
                query = """
                    SELECT 
                        o.order_id, o.order_number, o.status, o.total_amount, o.order_type,
                        o.created_at, o.updated_at, o.delivery_charges,
                        b.businessName, b.address as business_address,
                        r.firstName, r.lastName, r.mobileNumber,
                        o.delivery_address_snapshot, o.billing_address_snapshot,
                        o.business_id, b.businessName as business_name_detail,
                        o.user_id
                    FROM orders o
                    JOIN businesses b ON o.business_id = b.business_id
                    JOIN registrations r ON o.user_id = r.user_id
                    WHERE o.delivery_partner_id = %s
                    AND o.status IN ('delivered', 'completed')
                    LIMIT 50
                """
                
                cursor.execute(query, [user_id])
                
                delivered_orders = []
                for row in cursor.fetchall():
                    # Enhanced address parsing with multiple fallbacks
                    delivery_address = "Address not available"
                    
                    # Try delivery_address_snapshot first
                    if row[13]:  # delivery_address_snapshot
                        try:
                            import json
                            address_data = json.loads(row[13])
                            
                            # Handle different JSON structures
                            if isinstance(address_data, dict):
                                # Try different possible field names
                                parts = []
                                
                                # Common field variations
                                door_no = address_data.get('door_no') or address_data.get('Door no') or address_data.get('doorNo')
                                street = address_data.get('street') or address_data.get('address_line_1') or address_data.get('address')
                                city = address_data.get('city') or address_data.get('city/town') or address_data.get('cityTown')
                                state = address_data.get('state')
                                pincode = address_data.get('pincode') or address_data.get('postal_code')
                                landmark = address_data.get('landmark')
                                
                                if door_no: parts.append(f"Door No: {door_no}")
                                if street: parts.append(str(street))
                                if landmark: parts.append(f"Near {landmark}")
                                if city: parts.append(str(city))
                                if state: parts.append(str(state))
                                if pincode: parts.append(f"Pincode: {pincode}")
                                
                                delivery_address = ', '.join(filter(None, parts)) or "Address not available"
                            else:
                                delivery_address = str(address_data)
                        except Exception as e:
                            # If JSON parsing fails, try billing_address_snapshot
                            if row[14]:  # billing_address_snapshot
                                try:
                                    billing_data = json.loads(row[14])
                                    if isinstance(billing_data, dict):
                                        parts = []
                                        door_no = billing_data.get('door_no') or billing_data.get('Door no')
                                        street = billing_data.get('street') or billing_data.get('address')
                                        city = billing_data.get('city') or billing_data.get('city/town')
                                        pincode = billing_data.get('pincode')
                                        
                                        if door_no: parts.append(f"Door No: {door_no}")
                                        if street: parts.append(str(street))
                                        if city: parts.append(str(city))
                                        if pincode: parts.append(f"Pincode: {pincode}")
                                        
                                        delivery_address = ', '.join(filter(None, parts)) or "Address not available"
                                except:
                                    pass
                    
                    # If still no address, try to get from user_address table
                    if delivery_address == "Address not available" and row[17]:  # user_id
                        try:
                            cursor.execute("""
                                SELECT address FROM user_address 
                                WHERE user_id = %s AND address_type = 'home' 
                                ORDER BY created_at DESC LIMIT 1
                            """, [row[17]])
                            
                            addr_row = cursor.fetchone()
                            if addr_row and addr_row[0]:
                                try:
                                    addr_data = json.loads(addr_row[0])
                                    if isinstance(addr_data, dict):
                                        parts = []
                                        door_no = addr_data.get('Door no') or addr_data.get('door_no')
                                        street = addr_data.get('street')
                                        city = addr_data.get('city/town') or addr_data.get('city')
                                        pincode = addr_data.get('pincode')
                                        
                                        if door_no: parts.append(f"Door No: {door_no}")
                                        if street: parts.append(str(street))
                                        if city: parts.append(str(city))
                                        if pincode: parts.append(f"Pincode: {pincode}")
                                        
                                        delivery_address = ', '.join(filter(None, parts)) or "Address not available"
                                except:
                                    delivery_address = str(addr_row[0])
                        except:
                            pass
                    
                    order_data = {
                        'order_id': row[0],
                        'order_number': row[1],
                        'business_id': row[15],  # Updated index
                        'business_name': row[16],  # Updated index
                        'business_address': row[9],
                        'customer_name': f"{row[10] or ''} {row[11] or ''}".strip(),
                        'customer_phone': row[12],
                        'delivery_address': delivery_address,
                        'total_amount': float(row[3]) if row[3] else 0.0,
                        'status': row[2],
                        'order_type': row[4],
                        'created_at': row[5].isoformat() if row[5] else None,
                        'updated_at': row[6].isoformat() if row[6] else None,
                        'delivery_charges': float(row[7]) if row[7] else 0.0,
                        'estimated_delivery_time': None
                    }
                    delivered_orders.append(order_data)

                # Also include grocery delivered orders for this partner
                cursor.execute(
                    """
                    SELECT 
                        gdd.order_id,
                        gdd.delivered_at,
                        go.order_status,
                        go.payment_status,
                        go.final_amount,
                        go.delivery_charge,
                        go.delivery_address,
                        go.created_at,
                        go.updated_at,
                        b.business_id,
                        b.businessName,
                        b.address AS business_address,
                        r.firstName,
                        r.lastName,
                        r.mobileNumber
                    FROM Grocery_deliver_details gdd
                    JOIN Groceries_orders go ON gdd.order_id = go.order_id
                    JOIN businesses b ON go.business_id = b.business_id
                    JOIN registrations r ON go.user_id = r.user_id
                    WHERE gdd.partner_id = %s
                      AND gdd.assignment_status = 'delivered'
                      AND go.order_status IN ('delivered', 'completed')
                    ORDER BY COALESCE(gdd.delivered_at, go.updated_at) DESC
                    LIMIT 100
                    """,
                    [user_id]
                )

                for grow in cursor.fetchall():
                    g_order = {
                        'order_id': grow[0],
                        'order_number': f"GROC-{grow[0]}",
                        'business_id': grow[9],
                        'business_name': grow[10],
                        'business_address': grow[11],
                        'customer_name': f"{grow[12] or ''} {grow[13] or ''}".strip(),
                        'customer_phone': grow[14],
                        'delivery_address': grow[6] or "Address not available",
                        'total_amount': float(grow[4]) if grow[4] else 0.0,
                        'status': grow[2],  # order_status
                        'order_type': 'grocery',
                        'created_at': grow[7].isoformat() if grow[7] else None,
                        'updated_at': grow[8].isoformat() if grow[8] else None,
                        'delivery_charges': float(grow[5]) if grow[5] else 0.0,
                        'estimated_delivery_time': None
                    }
                    delivered_orders.append(g_order)

                # Compute combined status counts for this partner (standard + grocery)
                cursor.execute(
                    """
                    SELECT status, COUNT(*) as count
                    FROM orders
                    WHERE delivery_partner_id = %s
                      AND status IN ('delivered', 'completed')
                    GROUP BY status
                    """,
                    [user_id]
                )
                status_info_orders = cursor.fetchall()

                cursor.execute(
                    """
                    SELECT go.order_status, COUNT(*) as count
                    FROM Grocery_deliver_details gdd
                    JOIN Groceries_orders go ON gdd.order_id = go.order_id
                    WHERE gdd.partner_id = %s
                      AND gdd.assignment_status = 'delivered'
                      AND go.order_status IN ('delivered', 'completed')
                    GROUP BY go.order_status
                    """,
                    [user_id]
                )
                status_info_grocery = cursor.fetchall()

                counts = {}
                for st, cnt in status_info_orders:
                    counts[st] = counts.get(st, 0) + cnt
                for st, cnt in status_info_grocery:
                    counts[st] = counts.get(st, 0) + cnt
                available_statuses = [{"status": k, "count": v} for k, v in counts.items()]

                return Response({
                    "success": True,
                    "total_orders": len(delivered_orders),
                    "delivered_count": len(delivered_orders),
                    "available_statuses": available_statuses,
                    "delivered_orders": delivered_orders
                })
                
        except Exception as e:
            logger.error(f"Error fetching delivery order history: {str(e)}")
            return Response(
                {"error": f"Failed to fetch order history: {str(e)}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

@swagger_auto_schema(tags=['Delivery'])
class OrderDetailsView(APIView):
    """
    API endpoint to get order details with user information
    GET /api/orders/<int:order_id>/
    """
    
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
            
            # Prepare helpers for media URLs - use S3
            def to_absolute_url(path: str):
                """Build S3 URL for media path."""
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

                image_path = item.get("item_image") or item.get("image_url")

                formatted_items.append({
                    "item_id": item.get("item_id") or item.get("id"),
                    "product_id": item.get("product_id"),
                    "name": item.get("item_name") or item.get("name"),
                    "quantity": item.get("quantity"),
                    "unit_price": float(unit_price_dec),
                    "total_price": float(total_price_dec),
                    "gst": float(gst_value) if gst_value is not None else None,
                    "tax_amount": float(tax_amount_dec),
                    "image": to_absolute_url(image_path),
                    "description": item.get("description"),
                    "category": item.get("item_category") or item.get("sub_category"),
                    "type": item.get("item_type"),
                    "brand_name": item.get("brand_name"),
                    "rating": float(item.get("rating")) if item.get("rating") is not None else None,
                    "is_organic": bool(item.get("is_organic", 0))
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
                        "payment_method": order.get("payment_method"),
                        "created_at": order.get("created_at").isoformat() if order.get("created_at") else None,
                        "updated_at": order.get("updated_at").isoformat() if order.get("updated_at") else None,
                        "delivery_address": order.get("delivery_address"),
                        "delivery_instructions": order.get("delivery_instructions"),
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
                            "customer_type": order.get("order_customer_type"),
                            "company_id": order.get("company_id"),
                            "employee_id": order.get("ordered_by_employee"),
                            "approval_status": order.get("approval_status"),
                            "company_notes": order.get("company_notes"),
                            "department": order.get("company_department"),
                            "purchase_order": order.get("company_purchase_order"),
                            "is_bulk_order": bool(order.get("is_bulk_order")),
                            "bulk_order_reference": order.get("bulk_order_reference"),
                            "company_name": order.get("company_name"),
                            "gst_number": order.get("gst_number")
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

@swagger_auto_schema(tags=['Delivery'])
class GroceryOrdersDebugView(APIView):
    """
    Debug view to check Groceries_orders table data
    """
    
    def get(self, request):
        try:
            # Check if table exists and has data
            with connection.cursor() as cursor:
                # Check table existence
                cursor.execute("SHOW TABLES LIKE 'Groceries_orders'")
                table_exists = cursor.fetchone()
                
                if not table_exists:
                    return Response({
                        "error": "Groceries_orders table does not exist",
                        "table_exists": False
                    })
                
                # Get total count
                cursor.execute("SELECT COUNT(*) FROM Groceries_orders")
                total_count = cursor.fetchone()[0]
                
                # Get sample data
                cursor.execute("""
                    SELECT order_id, order_status, order_type, payment_status, 
                           business_id, delivery_address, created_at 
                    FROM Groceries_orders 
                    ORDER BY created_at DESC 
                    LIMIT 10
                """)
                sample_orders = cursor.fetchall()
                
                # Get status distribution
                cursor.execute("""
                    SELECT order_status, COUNT(*) as count 
                    FROM Groceries_orders 
                    GROUP BY order_status
                """)
                status_distribution = cursor.fetchall()
                
                # Get order type distribution
                cursor.execute("""
                    SELECT order_type, COUNT(*) as count 
                    FROM Groceries_orders 
                    GROUP BY order_type
                """)
                type_distribution = cursor.fetchall()
                
                # Check business associations
                cursor.execute("""
                    SELECT COUNT(*) as total_orders,
                           COUNT(CASE WHEN b.business_id IS NOT NULL THEN 1 END) as with_business,
                           COUNT(CASE WHEN b.latitude IS NOT NULL AND b.longitude IS NOT NULL THEN 1 END) as with_coordinates
                    FROM Groceries_orders go
                    LEFT JOIN businesses b ON go.business_id = b.business_id
                """)
                business_stats = cursor.fetchone()
                
                return Response({
                    "success": True,
                    "table_exists": True,
                    "total_orders": total_count,
                    "business_stats": {
                        "total_orders": business_stats[0],
                        "with_business": business_stats[1],
                        "with_coordinates": business_stats[2]
                    },
                    "status_distribution": [{"status": row[0], "count": row[1]} for row in status_distribution],
                    "type_distribution": [{"type": row[0], "count": row[1]} for row in type_distribution],
                    "sample_orders": [
                        {
                            "order_id": row[0],
                            "order_status": row[1],
                            "order_type": row[2],
                            "payment_status": row[3],
                            "business_id": row[4],
                            "delivery_address": row[5][:100] if row[5] else None,
                            "created_at": row[6].isoformat() if row[6] else None
                        } for row in sample_orders
                    ]
                })
                
        except Exception as e:
            return Response({
                "error": f"Debug failed: {str(e)}",
                "success": False
            }, status=500)

@swagger_auto_schema(tags=['Delivery'])
class PendingOrdersView(APIView):
    """
    GET /delivery/pending-orders/
    Fetch all pending orders from both orders and Groceries_orders tables with payment status
    
    Query Parameters:
    - business_id (optional): Filter by specific business
    - limit (optional): Limit number of results (default: 50, max: 100)
    - offset (optional): Offset for pagination (default: 0)
    - debug (optional): Enable debug mode to show item count details
    """
    
    def get(self, request):
        try:
            # Get query parameters
            business_id = request.query_params.get('business_id')
            limit = min(int(request.query_params.get('limit', 50)), 100)
            offset = int(request.query_params.get('offset', 0))
            include_items_preview = request.query_params.get('include_items_preview')
            
            regular_orders = []
            grocery_orders = []
            
            with connection.cursor() as cursor:
                # Get all business IDs to include (master + sub-businesses if applicable)
                business_ids_to_include = []
                if business_id:
                    business_ids_to_include.append(business_id)
                    
                    # Check if this business is a master and get all sub-businesses
                    cursor.execute("""
                        SELECT business_id, level 
                        FROM businesses 
                        WHERE business_id = %s AND status = 1
                    """, [business_id])
                    
                    business_info = cursor.fetchone()
                    if business_info and business_info[1] == 'master':
                        # Get all sub-businesses
                        cursor.execute("""
                            SELECT business_id 
                            FROM businesses 
                            WHERE master = %s AND status = 1
                        """, [business_id])
                        
                        sub_businesses = cursor.fetchall()
                        for sub_business in sub_businesses:
                            business_ids_to_include.append(sub_business[0])
                
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
                        0.00 as gst_amount,
                        
                        -- Customer details
                        o.user_id as customer_id,
                        CONCAT(COALESCE(r.firstName, ''), ' ', COALESCE(r.lastName, '')) as customer_name,
                        r.mobileNumber as customer_phone,
                        r.emailID as customer_email,
                        
                        -- Business details
                        o.business_id,
                        b.businessName as business_name,
                        bt.type as business_type,
                        
                        -- Company details (if this is a company order)
                        o.order_customer_type,
                        o.company_id,
                        o.ordered_by_employee,
                        o.approval_status,
                        o.company_notes,
                        o.company_department,
                        o.company_purchase_order,
                        o.is_bulk_order,
                        cr.company_name,
                        cr.gst_number,
                        
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
                        o.estimated_delivery_time as delivery_time,
                        o.scheduled_time as scheduled_time,
                        NULL as pickup_time,
                        
                        -- Order items count (using LEFT JOIN for better performance)
                        COALESCE(oi_count.item_count, 0) as items_count,
                        
                        -- Timestamps
                        o.created_at,
                        o.updated_at,
                        o.token_num as token_num
                        
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
                        SELECT order_id, COUNT(*) as item_count 
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
                    order_data = {
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
                        'delivery_time': row[19],
                        'scheduled_time': row[20],
                        'pickup_time': row[21],
                        'items_count': row[22],
                        'created_at': row[23],
                        'updated_at': row[24],
                        'token_num': row[25],
                        'order_system': 'regular'
                    }
                    
                    # Add company details if this is a company order
                    if row[18]:  # company_id
                        order_data['company_details'] = {
                            'company_name': row[26],
                            'gst_number': row[27],
                            'customer_type': row[17],
                            'company_id': row[18],
                            'employee_id': row[19],
                            'approval_status': row[20],
                            'company_notes': row[21],
                            'department': row[22],
                            'purchase_order': row[23],
                            'is_bulk_order': bool(row[24])
                        }
                    
                    regular_orders.append(order_data)
                
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
                        
                        -- Company details
                        go.order_customer_type,
                        go.company_id,
                        go.ordered_by_employee,
                        go.approval_status,
                        go.company_notes,
                        go.company_department,
                        go.company_purchase_order,
                        go.is_bulk_order,
                        cr.company_name,
                        cr.gst_number,
                        
                        -- Business details
                        go.business_id,
                        b.businessName as business_name,
                        bt.type as business_type,
                        
                        -- Address and delivery
                        go.delivery_address,
                        go.delivery_instructions,
                        go.delivery_time,
                        go.pickup_time,
                        
                        -- Order items count (using LEFT JOIN for better performance)
                        COALESCE(goi_count.item_count, 0) as items_count,
                        
                        -- Timestamps
                        go.created_at,
                        go.updated_at
                        
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
                    order_data = {
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
                        'delivery_time': row[19],
                        'scheduled_time': None,
                        'pickup_time': row[20],
                        'items_count': row[21],
                        'created_at': row[22],
                        'updated_at': row[23],
                        'order_system': 'grocery'
                    }
                    
                    # Add company details if this is a company order
                    if row[18]:  # company_id
                        order_data['company_details'] = {
                            'company_name': row[25],
                            'gst_number': row[26],
                            'customer_type': row[17],
                            'company_id': row[18],
                            'employee_id': row[19],
                            'approval_status': row[20],
                            'company_notes': row[21],
                            'department': row[22],
                            'purchase_order': row[23],
                            'is_bulk_order': bool(row[24])
                        }
                    
                    grocery_orders.append(order_data)
            
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
                            SELECT oi.order_id, p.product_name, oi.quantity
                            FROM Groceries_order_items oi
                            LEFT JOIN Groceries_Products p ON oi.product_id = p.product_id
                            WHERE oi.order_id IN ({placeholders})
                        """, gro_ids)
                        rows = cursor.fetchall()
                        gro_items_map = {}
                        for oid, name, qty in rows:
                            gro_items_map.setdefault(oid, []).append({
                                'name': name,
                                'quantity': int(qty) if qty is not None else None,
                                'customizations': []
                            })
                        for o in grocery_orders:
                            o['items'] = gro_items_map.get(o['order_id'], [])
            except Exception as e:
                logger.error(f"Failed to fetch items/customizations for pending orders: {e}")

            try:
                if include_items_preview and str(include_items_preview).strip().lower() in ('1', 'true', 'yes'):
                    GroceryOrdersService.attach_items_preview_to_standard_orders(regular_orders)
                    GroceryOrdersService.attach_items_preview_to_grocery_orders(grocery_orders)
            except Exception as exc:
                logger.error(f"Failed to attach items preview in PendingOrdersView: {exc}")
            
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
                    'has_next_page': has_next_page,
                    'has_prev_page': has_prev_page,
                    'next_offset': offset + limit if has_next_page else None,
                    'prev_offset': max(0, offset - limit) if has_prev_page else None
                },
                'counts': {
                    'total_orders': total_orders,
                    'regular_orders_count': total_regular_orders,
                    'grocery_orders_count': total_grocery_orders,
                    'current_batch_count': len(all_orders)
                },
                'orders': all_orders
            }
            
            # Use serializer for validation and consistent response format
            from delivery.serializers import PendingOrdersResponseSerializer
            serializer = PendingOrdersResponseSerializer(data=response_data)
            
            if serializer.is_valid():
                return Response(serializer.validated_data, status=status.HTTP_200_OK)
            else:
                logger.error(f"Serializer validation failed: {serializer.errors}")
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

@swagger_auto_schema(tags=['Delivery'])
class DeliveryPartnerKilometerCalculationView(APIView):
    def get(self, request):
        try:
            order_id = request.query_params.get('order_id')
            partner_id = request.query_params.get('partner_id')
            date_key = request.query_params.get('date')
            from_param = request.query_params.get('from')
            to_param = request.query_params.get('to')

            def _compute_distance_km(points):
                total = 0.0
                if not points or len(points) < 2:
                    return 0.0
                prev = points[0]
                for curr in points[1:]:
                    lat1, lon1 = prev[0], prev[1]
                    lat2, lon2 = curr[0], curr[1]
                    if lat1 is not None and lon1 is not None and lat2 is not None and lon2 is not None:
                        total += float(calculate_distance(float(lat1), float(lon1), float(lat2), float(lon2)))
                    prev = curr
                return total

            if order_id:
                try:
                    order_id_int = int(str(order_id).strip())
                except Exception:
                    return Response({'success': False, 'error': 'Invalid order_id'}, status=status.HTTP_400_BAD_REQUEST)

                with connection.cursor() as cursor:
                    cursor.execute(
                        """
                        SELECT delivery_partner_id, latitude, longitude, timestamp
                        FROM deliverylocationhistory
                        WHERE order_id = %s
                        ORDER BY timestamp ASC
                        """,
                        [order_id_int]
                    )
                    rows = cursor.fetchall()

                points = [(r[1], r[2], r[3]) for r in rows]
                total_km = round(_compute_distance_km(points), 2)

                # Also compute net (straight-line) distance between first and last recorded points
                net_km = 0.0
                first_ts = None
                last_ts = None
                first_point = None
                last_point = None
                if len(points) >= 2:
                    first_point = points[0]
                    last_point = points[-1]
                    first_ts = first_point[2]
                    last_ts = last_point[2]
                    lat1, lon1 = first_point[0], first_point[1]
                    lat2, lon2 = last_point[0], last_point[1]
                    if lat1 is not None and lon1 is not None and lat2 is not None and lon2 is not None:
                        net_km = round(float(calculate_distance(float(lat1), float(lon1), float(lat2), float(lon2))), 2)

                current_location = {'latitude': None, 'longitude': None}
                dp_user_id = rows[-1][0] if rows else None
                if dp_user_id:
                    with connection.cursor() as cursor:
                        cursor.execute(
                            "SELECT latitude, longitude FROM delivery_partner WHERE user_id = %s LIMIT 1",
                            [dp_user_id]
                        )
                        loc = cursor.fetchone()
                        if loc:
                            current_location = {
                                'latitude': float(loc[0]) if loc[0] is not None else None,
                                'longitude': float(loc[1]) if loc[1] is not None else None,
                            }

                coords = [
                    {
                        'latitude': float(p[0]) if p[0] is not None else None,
                        'longitude': float(p[1]) if p[1] is not None else None,
                        'timestamp': (p[2].isoformat() if isinstance(p[2], datetime) else str(p[2]))
                    }
                    for p in points
                ]

                return Response({
                    'success': True,
                    'data': {
                        'order_id': order_id_int,
                        'total_kilometers': total_km,
                        'net_kilometers': net_km,
                        'first_timestamp': (first_ts.isoformat() if hasattr(first_ts, 'isoformat') and first_ts else None),
                        'last_timestamp': (last_ts.isoformat() if hasattr(last_ts, 'isoformat') and last_ts else None),
                        'points_count': len(points),
                        'points': coords,
                        'current_location': current_location,
                    }
                }, status=status.HTTP_200_OK)

            if not partner_id:
                return Response({'success': False, 'error': 'partner_id or order_id required'}, status=status.HTTP_400_BAD_REQUEST)

            try:
                partner_id_int = int(str(partner_id).strip())
            except Exception:
                return Response({'success': False, 'error': 'Invalid partner_id'}, status=status.HTTP_400_BAD_REQUEST)

            now = timezone.now()
            start_dt = None
            end_dt = None

            if from_param and to_param:
                try:
                    start_dt = date_parser.parse(from_param)
                    end_dt = date_parser.parse(to_param)
                except Exception:
                    return Response({'success': False, 'error': 'Invalid from/to timestamp'}, status=status.HTTP_400_BAD_REQUEST)
            else:
                key = (date_key or 'today').lower()
                if key == 'today':
                    start_dt = now.replace(hour=0, minute=0, second=0, microsecond=0)
                    end_dt = now
                elif key == 'week':
                    start_dt = now - timedelta(days=7)
                    end_dt = now
                elif key == 'month':
                    start_dt = now - timedelta(days=30)
                    end_dt = now
                elif key in ('half-year', 'half-yearly', 'halfyear', 'halfyearly'):
                    start_dt = now - timedelta(days=182)
                    end_dt = now
                elif key == 'year' or key == 'yearly':
                    start_dt = now - timedelta(days=365)
                    end_dt = now
                else:
                    start_dt = now - timedelta(days=7)
                    end_dt = now

            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT order_id, latitude, longitude, timestamp
                    FROM deliverylocationhistory
                    WHERE delivery_partner_id = %s AND timestamp BETWEEN %s AND %s
                    ORDER BY order_id ASC, timestamp ASC
                    """,
                    [partner_id_int, start_dt, end_dt]
                )
                rows = cursor.fetchall()

                cursor.execute(
                    "SELECT latitude, longitude FROM delivery_partner WHERE user_id = %s LIMIT 1",
                    [partner_id_int]
                )
                loc = cursor.fetchone()

            current_location = {
                'latitude': float(loc[0]) if loc and loc[0] is not None else None,
                'longitude': float(loc[1]) if loc and loc[1] is not None else None,
            }

            total_km = 0.0
            earliest_ts = None
            latest_ts = None

            by_order = {}
            for r in rows:
                oid = int(r[0]) if r[0] is not None else None
                pt = (r[1], r[2], r[3])
                if oid not in by_order:
                    by_order[oid] = []
                by_order[oid].append(pt)
                if r[3]:
                    if earliest_ts is None or r[3] < earliest_ts:
                        earliest_ts = r[3]
                    if latest_ts is None or r[3] > latest_ts:
                        latest_ts = r[3]

            for oid, pts in by_order.items():
                total_km += _compute_distance_km(pts)

            total_km = round(total_km, 2)
            recorded_hours = 0.0
            if earliest_ts and latest_ts and latest_ts > earliest_ts:
                delta = latest_ts - earliest_ts
                recorded_hours = round(delta.total_seconds() / 3600.0, 2)

            return Response({
                'success': True,
                'data': {
                    'partner_id': partner_id_int,
                    'from': start_dt.isoformat() if isinstance(start_dt, datetime) else str(start_dt),
                    'to': end_dt.isoformat() if isinstance(end_dt, datetime) else str(end_dt),
                    'total_kilometers': total_km,
                    'recorded_hours': recorded_hours,
                    'current_location': current_location,
                }
            }, status=status.HTTP_200_OK)
        except Exception as e:
            return Response({'success': False, 'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)



class SnapToRoadsView(APIView):
    """
    Get road-following route using Google Directions API
    More reliable than Snap to Roads and commonly enabled
    """
    def get(self, request):
        order_id = request.GET.get('order_id')
        
        if not order_id:
            return Response({'success': False, 'error': 'order_id required'}, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            import requests
            
            # Fetch GPS points from database
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT latitude, longitude, timestamp
                    FROM deliverylocationhistory
                    WHERE order_id = %s
                    ORDER BY timestamp ASC
                    """,
                    [order_id]
                )
                rows = cursor.fetchall()
            
            if not rows or len(rows) < 2:
                return Response({
                    'success': False,
                    'error': 'Not enough GPS points for this order'
                }, status=status.HTTP_404_NOT_FOUND)
            
            logger.info(f"Processing {len(rows)} GPS points for order {order_id}")
            
            # Store original first and last points for markers (before any filtering)
            original_start = {'latitude': float(rows[0][0]), 'longitude': float(rows[0][1])}
            original_end = {'latitude': float(rows[-1][0]), 'longitude': float(rows[-1][1])}
            logger.info(f"Original GPS start point: {original_start}")
            logger.info(f"Original GPS end point: {original_end}")
            
            # Clean data: remove duplicates, filter noise, and detect loops
            cleaned_points = []
            prev_point = None
            
            for row in rows:
                try:
                    lat, lng, ts = float(row[0]), float(row[1]), row[2]
                    
                    if lat < -90 or lat > 90 or lng < -180 or lng > 180:
                        continue
                    
                    if prev_point:
                        dist = calculate_distance(prev_point[0], prev_point[1], lat, lng)
                        if dist < 0.02 or dist > 0.3:  # Skip < 20m or > 300m
                            continue
                    
                    cleaned_points.append((lat, lng, ts))
                    prev_point = (lat, lng)
                    
                except (ValueError, TypeError):
                    continue
            
            if len(cleaned_points) < 2:
                return Response({
                    'success': False,
                    'error': 'Not enough valid GPS points after cleaning'
                }, status=status.HTTP_400_BAD_REQUEST)
            
            # Remove loops and backtracking
            def remove_loops(points):
                """Remove loops where delivery partner returns to same area"""
                if len(points) < 3:
                    return points
                
                result = [points[0]]
                
                for i in range(1, len(points)):
                    current = points[i]
                    
                    # Check if current point is close to any previous point (within 50m)
                    loop_detected = False
                    for j in range(len(result) - 1):
                        prev = result[j]
                        dist = calculate_distance(prev[0], prev[1], current[0], current[1])
                        
                        if dist < 0.05:  # Within 50 meters
                            # Loop detected - remove all points between j and current
                            logger.info(f"Loop detected: removing {len(result) - j - 1} points")
                            result = result[:j+1]
                            loop_detected = True
                            break
                    
                    if not loop_detected:
                        result.append(current)
                
                return result
            
            cleaned_points = remove_loops(cleaned_points)
            logger.info(f"After loop removal: {len(cleaned_points)} points")
            
            # Use Google Directions API for road-following route
            api_key = settings.GOOGLE_MAPS_API_KEY if hasattr(settings, 'GOOGLE_MAPS_API_KEY') else 'AIzaSyBwRQy7Fwqg218NcVmpQyOFLGy9RWdJT1s'
            
            # Smart waypoint filtering: Remove detours but keep main path
            def filter_detours(points, start_idx=0, end_idx=None):
                """
                Remove detours by checking if intermediate points deviate too far
                from the direct path between start and end
                """
                if end_idx is None:
                    end_idx = len(points) - 1
                
                if end_idx - start_idx <= 1:
                    return [points[start_idx], points[end_idx]]
                
                start = points[start_idx]
                end = points[end_idx]
                
                # Calculate direct distance between start and end
                direct_dist = calculate_distance(start[0], start[1], end[0], end[1])
                
                # Find the point that deviates most from the direct line
                max_deviation = 0
                max_idx = -1
                
                for i in range(start_idx + 1, end_idx):
                    point = points[i]
                    
                    # Calculate perpendicular distance from point to line (start -> end)
                    # Using cross product method
                    dist_to_start = calculate_distance(start[0], start[1], point[0], point[1])
                    dist_to_end = calculate_distance(point[0], point[1], end[0], end[1])
                    
                    # If point is on the path, dist_to_start + dist_to_end ≈ direct_dist
                    # If it's a detour, the sum will be significantly larger
                    path_ratio = (dist_to_start + dist_to_end) / direct_dist if direct_dist > 0 else 1
                    
                    # Also check perpendicular distance
                    # Using simplified perpendicular distance calculation
                    deviation = abs(dist_to_start + dist_to_end - direct_dist)
                    
                    if deviation > max_deviation:
                        max_deviation = deviation
                        max_idx = i
                
                # If max deviation is small (< 200m), this segment is straight - no detours
                if max_deviation < 0.2:  # 200 meters
                    return [start, end]
                
                # If deviation is large (> 500m), it's likely a detour - skip it
                if max_deviation > 0.5:  # 500 meters
                    logger.info(f"Detour detected: {max_deviation*1000:.0f}m deviation at point {max_idx}")
                    # Recursively process segments, skipping the detour point
                    left = filter_detours(points, start_idx, max_idx - 1) if max_idx > start_idx + 1 else [start]
                    right = filter_detours(points, max_idx + 1, end_idx) if max_idx < end_idx - 1 else [end]
                    return left + right
                
                # Otherwise, keep the point and recursively process both segments
                left = filter_detours(points, start_idx, max_idx)
                right = filter_detours(points, max_idx, end_idx)
                return left[:-1] + right  # Avoid duplicating the middle point
            
            # Apply detour filtering
            filtered_points = filter_detours(cleaned_points)
            logger.info(f"After detour filtering: {len(cleaned_points)} -> {len(filtered_points)} points")
            
            # Get start and end
            start = filtered_points[0]
            end = filtered_points[-1]
            
            # Use filtered waypoints (max 25 due to API limit)
            waypoints = []
            if len(filtered_points) > 2:
                # Sample waypoints evenly if too many
                max_waypoints = 25
                step = max(1, (len(filtered_points) - 2) // max_waypoints)
                waypoints = filtered_points[1:-1:step][:max_waypoints]
            
            try:
                # Call Google Directions API with filtered waypoints
                url = "https://maps.googleapis.com/maps/api/directions/json"
                params = {
                    'origin': f"{start[0]},{start[1]}",
                    'destination': f"{end[0]},{end[1]}",
                    'mode': 'driving',
                    'key': api_key
                }
                
                # Add waypoints if we have them
                if waypoints:
                    waypoints_str = '|'.join([f"{p[0]},{p[1]}" for p in waypoints])
                    params['waypoints'] = waypoints_str
                    logger.info(f"Using {len(waypoints)} filtered waypoints (detours removed)")
                else:
                    logger.info("Using direct route (no intermediate waypoints)")
                
                logger.info(f"Calling Directions API: origin={start[0]:.4f},{start[1]:.4f}, dest={end[0]:.4f},{end[1]:.4f}")
                response = requests.get(url, params=params, timeout=15)
                
                logger.info(f"Directions API response status: {response.status_code}")
                
                if response.status_code == 200:
                    data = response.json()
                    logger.info(f"Directions API status: {data.get('status')}")
                    
                    if data.get('status') == 'OK' and data.get('routes'):
                        # Extract polyline points from route
                        route = data['routes'][0]
                        
                        # Decode polyline to get all points along the route
                        encoded_polyline = route['overview_polyline']['points']
                        decoded_points = self.decode_polyline(encoded_polyline)
                        
                        # Remove duplicate consecutive points from decoded polyline
                        unique_points = [decoded_points[0]]
                        for point in decoded_points[1:]:
                            last = unique_points[-1]
                            # Only add if different from last point (> 5 meters)
                            dist = calculate_distance(last[0], last[1], point[0], point[1])
                            if dist > 0.005:  # 5 meters
                                unique_points.append(point)
                        
                        # Convert to our format
                        route_points = [
                            {'latitude': point[0], 'longitude': point[1]}
                            for point in unique_points
                        ]
                        
                        logger.info(f"✅ Directions API SUCCESS: {len(decoded_points)} decoded -> {len(route_points)} unique points on actual roads")
                        
                        return Response({
                            'success': True,
                            'data': {
                                'order_id': order_id,
                                'points': route_points,
                                'points_count': len(route_points),
                                'original_count': len(rows),
                                'cleaned_count': len(cleaned_points),
                                'snapped': True,
                                'method': 'directions_api',
                                'message': 'Route from Google Directions API (follows actual roads)',
                                'start_point': original_start,  # First GPS point for RED marker
                                'end_point': original_end  # Last GPS point for BLUE marker
                            }
                        }, status=status.HTTP_200_OK)
                    else:
                        error_msg = data.get('error_message', data.get('status', 'Unknown error'))
                        logger.error(f"Directions API error: {error_msg}")
                        
                else:
                    logger.error(f"Directions API HTTP error: {response.status_code} - {response.text[:200]}")
                    
            except requests.exceptions.Timeout:
                logger.error("Directions API timeout after 15 seconds")
            except Exception as e:
                logger.error(f"Directions API exception: {e}", exc_info=True)
            
            # Fallback to cleaned points
            logger.warning("Using cleaned GPS points as fallback")
            fallback_points = [{'latitude': p[0], 'longitude': p[1]} for p in cleaned_points]
            return Response({
                'success': True,
                'data': {
                    'order_id': order_id,
                    'points': fallback_points,
                    'points_count': len(fallback_points),
                    'original_count': len(rows),
                    'cleaned_count': len(cleaned_points),
                    'snapped': False,
                    'message': 'Using cleaned GPS points (Directions API unavailable)',
                    'start_point': original_start,  # First GPS point for RED marker
                    'end_point': original_end  # Last GPS point for BLUE marker
                }
            }, status=status.HTTP_200_OK)
            
        except Exception as e:
            logger.error(f"Error in SnapToRoadsView: {str(e)}", exc_info=True)
            return Response({
                'success': False,
                'error': f'Server error: {str(e)}'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    
    def decode_polyline(self, encoded):
        """Decode Google polyline to lat/lng coordinates"""
        points = []
        index = 0
        lat = 0
        lng = 0
        
        while index < len(encoded):
            b = 0
            shift = 0
            result = 0
            
            while True:
                b = ord(encoded[index]) - 63
                index += 1
                result |= (b & 0x1f) << shift
                shift += 5
                if b < 0x20:
                    break
            
            dlat = ~(result >> 1) if (result & 1) else (result >> 1)
            lat += dlat
            
            shift = 0
            result = 0
            
            while True:
                b = ord(encoded[index]) - 63
                index += 1
                result |= (b & 0x1f) << shift
                shift += 5
                if b < 0x20:
                    break
            
            dlng = ~(result >> 1) if (result & 1) else (result >> 1)
            lng += dlng
            
            points.append((lat / 1e5, lng / 1e5))
        
        return points
