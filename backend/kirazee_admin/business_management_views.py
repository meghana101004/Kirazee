"""
Business Management Views for SuperAdmin
Provides detailed business information with tabs
"""
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from django.db import connection
from django.utils import timezone
import logging
import json

logger = logging.getLogger(__name__)


class BusinessDetailedView(APIView):
    """
    Get comprehensive business details for SuperAdmin
    GET /api/v1/admin/business-management/{business_id}/detailed/
    """
    permission_classes = []
    
    def get(self, request, business_id):
        """Get detailed business information with all tabs data"""
        try:
            # Get period parameter from query string (default: 7days)
            period = request.GET.get('period', '7days')  # Options: 'today', '7days'
            
            with connection.cursor() as cursor:
                # 1. OVERVIEW TAB - Business Info
                cursor.execute("""
                    SELECT 
                        b.business_id,
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
                        b.gst_num,
                        b.address,
                        b.landmark,
                        b.city,
                        b.state,
                        b.pincode,
                        b.latitude,
                        b.longitude,
                        b.is_verified,
                        b.status,
                        b.paymentstatus,
                        b.business_hours,
                        b.created_at,
                        bf.fssai_certification_number,
                        bf.gstin,
                        bf.owner_pan,
                        bf.account_number,
                        bf.ifsc_code,
                        r.firstName,
                        r.lastName,
                        r.emailID,
                        r.mobileNumber
                    FROM businesses b
                    LEFT JOIN business_types bt ON b.businessType = bt.code
                    LEFT JOIN business_financials bf ON b.business_id = bf.business_id
                    LEFT JOIN business_mapping bm ON b.business_id = bm.business_id
                    LEFT JOIN registrations r ON bm.user_id = r.user_id
                    WHERE b.business_id = %s
                    LIMIT 1
                """, [business_id])
                
                business_row = cursor.fetchone()
                if not business_row:
                    return Response({
                        'success': False,
                        'message': 'Business not found'
                    }, status=status.HTTP_404_NOT_FOUND)
                
                # Construct owner name
                owner_first = business_row[29] or ''
                owner_last = business_row[30] or ''
                owner_name = f"{owner_first} {owner_last}".strip() or 'N/A'
                
                business_info = {
                    'business_id': business_row[0],
                    'business_name': business_row[1],
                    'business_type': business_row[2],
                    'business_type_name': business_row[3],
                    'business_category': business_row[4],
                    'email': business_row[5],
                    'phone': business_row[6],
                    'whatsapp': business_row[7],
                    'description': business_row[8],
                    'logo': business_row[9],
                    'banner': business_row[10],
                    'gst_number': business_row[11],
                    'address': business_row[12],
                    'landmark': business_row[13],
                    'city': business_row[14],
                    'state': business_row[15],
                    'pincode': business_row[16],
                    'latitude': float(business_row[17]) if business_row[17] else None,
                    'longitude': float(business_row[18]) if business_row[18] else None,
                    'is_verified': business_row[19],
                    'status': business_row[20],
                    'payment_status': business_row[21],
                    'business_hours': business_row[22],
                    'created_at': business_row[23].isoformat() if business_row[23] else None,
                    'fssai_number': business_row[24],
                    'gstin': business_row[25],
                    'owner_pan': business_row[26],
                    'account_number': business_row[27],
                    'ifsc_code': business_row[28],
                    'owner_first_name': owner_first,
                    'owner_last_name': owner_last,
                    'owner_name': owner_name,
                    'owner_email': business_row[31],
                    'owner_mobile': business_row[32]
                }
                
                # 2. PERFORMANCE SUMMARY - Dynamic Period (Today or Last 7 Days)
                # Debug: Check what business_id we're looking for
                logger.info(f"Fetching performance for business_id: {business_id}, period: {period}")
                
                # Calculate date ranges based on period
                from datetime import datetime, timedelta
                today = timezone.now().date()
                
                if period == 'today':
                    start_date = today
                    period_label = 'Today'
                    date_range = f"{today}"
                else:  # Default to 7days
                    start_date = today - timedelta(days=7)
                    period_label = 'Last 7 Days (including today)'
                    date_range = f"{start_date} to {today}"
                
                logger.info(f"Date range: {start_date} to {today}")
                
                # Check if there are any orders for this business in orders table
                cursor.execute("""
                    SELECT COUNT(*) FROM orders WHERE business_id = %s
                """, [business_id])
                total_orders_check = cursor.fetchone()[0]
                logger.info(f"Total orders in 'orders' table: {total_orders_check}")
                
                # Check if Groceries_orders table exists and has orders
                try:
                    cursor.execute("""
                        SELECT COUNT(*) FROM Groceries_orders WHERE business_id = %s
                    """, [business_id])
                    grocery_orders_check = cursor.fetchone()[0]
                    logger.info(f"Total orders in 'Groceries_orders' table: {grocery_orders_check}")
                    has_grocery_table = True
                except Exception as e:
                    logger.warning(f"Groceries_orders table not accessible: {e}")
                    grocery_orders_check = 0
                    has_grocery_table = False
                
                # Build dynamic query based on period
                if period == 'today':
                    # Today only
                    date_condition = "DATE(o.created_at) = %s"
                    date_params = [today]
                else:
                    # Last 7 days
                    date_condition = "DATE(o.created_at) >= %s"
                    date_params = [start_date]
                
                # Get performance from regular orders table
                cursor.execute(f"""
                    SELECT 
                        COUNT(DISTINCT o.order_id) as total_orders,
                        COALESCE(SUM(CASE WHEN o.status IN ('delivered', 'completed') THEN o.final_amount ELSE 0 END), 0) as total_revenue,
                        COUNT(DISTINCT CASE WHEN o.status IN ('delivered', 'completed') THEN o.order_id END) as completed_orders,
                        COALESCE(AVG(CASE WHEN o.status IN ('delivered', 'completed') THEN o.final_amount ELSE NULL END), 0) as avg_order_value
                    FROM orders o
                    WHERE o.business_id = %s AND {date_condition}
                """, [business_id] + date_params)
                
                perf_row = cursor.fetchone()
                logger.info(f"Orders performance: {perf_row}")
                
                # Get performance from grocery orders if table exists
                grocery_perf_row = (0, 0, 0, 0)
                if has_grocery_table:
                    try:
                        cursor.execute(f"""
                            SELECT 
                                COUNT(DISTINCT go.order_id) as total_orders,
                                COALESCE(SUM(CASE WHEN go.order_status IN ('delivered', 'completed', 'grocery_delivered', 'grocery_picked_up') THEN go.total_amount ELSE 0 END), 0) as total_revenue,
                                COUNT(DISTINCT CASE WHEN go.order_status IN ('delivered', 'completed', 'grocery_delivered', 'grocery_picked_up') THEN go.order_id END) as completed_orders,
                                COALESCE(AVG(CASE WHEN go.order_status IN ('delivered', 'completed', 'grocery_delivered', 'grocery_picked_up') THEN go.total_amount ELSE NULL END), 0) as avg_order_value
                            FROM Groceries_orders go
                            WHERE go.business_id = %s AND {date_condition.replace('o.', 'go.')}
                        """, [business_id] + date_params)
                        
                        grocery_perf_row = cursor.fetchone()
                        logger.info(f"Grocery orders performance: {grocery_perf_row}")
                    except Exception as e:
                        logger.error(f"Error querying Groceries_orders: {e}")
                        grocery_perf_row = (0, 0, 0, 0)
                
                # Combine both order types
                total_orders = (perf_row[0] if perf_row else 0) + (grocery_perf_row[0] if grocery_perf_row else 0)
                total_revenue = (float(perf_row[1]) if perf_row and perf_row[1] else 0) + (float(grocery_perf_row[1]) if grocery_perf_row and grocery_perf_row[1] else 0)
                completed_orders = (perf_row[2] if perf_row else 0) + (grocery_perf_row[2] if grocery_perf_row else 0)
                
                # Calculate combined average order value
                if total_orders > 0:
                    avg_order_value = total_revenue / total_orders
                else:
                    avg_order_value = 0
                
                performance = {
                    'total_orders': total_orders,
                    'total_revenue': total_revenue,
                    'completed_orders': completed_orders,
                    'avg_order_value': avg_order_value,
                    'completion_rate': (completed_orders / total_orders * 100) if total_orders > 0 else 0,
                    'period': period_label,
                    'date_range': date_range,
                    'period_filter': period
                }
                
                # 3. AVERAGE RATING - Use rating table for business ratings
                cursor.execute("""
                    SELECT 
                        COALESCE(AVG(rating), 0) as avg_rating,
                        COUNT(*) as total_ratings,
                        MIN(rating) as min_rating,
                        MAX(rating) as max_rating
                    FROM rating
                    WHERE business_id = %s
                """, [business_id])
                
                rating_row = cursor.fetchone()
                logger.info(f"Rating query result for business {business_id}: {rating_row}")
                
                performance['avg_rating'] = float(rating_row[0]) if rating_row and rating_row[0] else 0
                performance['total_ratings'] = rating_row[1] if rating_row else 0
                
                # Debug: Check if there are any ratings at all
                cursor.execute("""
                    SELECT COUNT(*) FROM rating
                """)
                total_rating_count = cursor.fetchone()[0]
                logger.info(f"Total rating records in database: {total_rating_count}")
                
                # Debug: Check business_id format in rating table
                if total_rating_count > 0:
                    cursor.execute("""
                        SELECT DISTINCT business_id FROM rating LIMIT 5
                    """)
                    sample_business_ids = [row[0] for row in cursor.fetchall()]
                    logger.info(f"Sample business_ids in rating table: {sample_business_ids}")
                
                # 4. MENU ITEMS COUNT
                cursor.execute("""
                    SELECT COUNT(*) FROM menuItems WHERE business_id = %s
                """, [business_id])
                menu_count = cursor.fetchone()[0]
                
                # 5. RECENT ORDERS (for Orders tab) - Combine both order types if Groceries_orders exists
                orders_query = """
                    SELECT 
                        o.order_id,
                        o.order_number,
                        CONCAT(r.firstName, ' ', r.lastName) as customer_name,
                        o.final_amount,
                        o.status,
                        o.created_at,
                        'restaurant' as order_type,
                        'Paid' as payment_status,
                        o.delivery_charges,
                        CONCAT(dp.firstName, ' ', dp.lastName) as delivery_partner_name,
                        o.discount_amount,
                        o.total_amount,
                        TIME(o.created_at) as order_time,
                        o.order_type as db_order_type
                    FROM orders o
                    LEFT JOIN registrations r ON o.user_id = r.user_id
                    LEFT JOIN registrations dp ON o.delivery_partner_id = dp.user_id
                    WHERE o.business_id = %s
                """
                
                # Add grocery orders if table exists
                if has_grocery_table:
                    try:
                        orders_query += """
                            UNION ALL
                            
                            SELECT 
                                go.order_id,
                                CONCAT('GRO-', go.order_id) as order_number,
                                CONCAT(r.firstName, ' ', r.lastName) as customer_name,
                                go.total_amount as final_amount,
                                go.order_status as status,
                                go.created_at,
                                'grocery' as order_type,
                                go.payment_status,
                                go.delivery_charge as delivery_charges,
                                'N/A' as delivery_partner_name,
                                go.discount,
                                go.total_amount,
                                TIME(go.created_at) as order_time,
                                go.order_type as db_order_type
                            FROM Groceries_orders go
                            LEFT JOIN registrations r ON go.user_id = r.user_id
                            WHERE go.business_id = %s
                        """
                        cursor.execute(orders_query + " ORDER BY created_at DESC LIMIT 50", [business_id, business_id])
                    except Exception as e:
                        logger.error(f"Error querying grocery orders: {e}")
                        # Fall back to regular orders only query
                        regular_orders_query = """
                            SELECT 
                                o.order_id,
                                o.order_number,
                                CONCAT(r.firstName, ' ', r.lastName) as customer_name,
                                o.final_amount,
                                o.status,
                                o.created_at,
                                'restaurant' as order_type,
                                'Paid' as payment_status,
                                o.delivery_charges,
                                CONCAT(dp.firstName, ' ', dp.lastName) as delivery_partner_name,
                                o.discount_amount,
                                o.total_amount,
                                TIME(o.created_at) as order_time,
                                o.order_type as db_order_type
                            FROM orders o
                            LEFT JOIN registrations r ON o.user_id = r.user_id
                            LEFT JOIN registrations dp ON o.delivery_partner_id = dp.user_id
                            WHERE o.business_id = %s
                            ORDER BY created_at DESC LIMIT 50
                        """
                        cursor.execute(regular_orders_query, [business_id])
                else:
                    cursor.execute(orders_query + " ORDER BY created_at DESC LIMIT 50", [business_id])
                
                orders = []
                for row in cursor.fetchall():
                    orders.append({
                        'order_id': row[0],
                        'order_number': str(row[1]),
                        'customer_name': row[2],
                        'amount': float(row[3]) if row[3] else 0,
                        'status': row[4],
                        'date': row[5].isoformat() if row[5] else None,
                        'order_type': row[6],
                        'payment_status': row[7] if len(row) > 7 else 'N/A',
                        'delivery_charges': float(row[8]) if len(row) > 8 and row[8] else 0,
                        'delivery_partner': row[9] if len(row) > 9 and row[9] else 'Unassigned',
                        'discount': float(row[10]) if len(row) > 10 and row[10] else 0,
                        'subtotal': float(row[11]) if len(row) > 11 and row[11] else 0,
                        'order_time': str(row[12]) if len(row) > 12 and row[12] else '',
                        'db_order_type': row[13] if len(row) > 13 and row[13] else 'N/A'
                    })
                
                # 6. REVIEWS (for Reviews tab) - Use rating table
                cursor.execute("""
                    SELECT 
                        r.id,
                        r.username,
                        r.rating,
                        r.review,
                        r.created_at,
                        COALESCE(m.item_name, g.item_name, gp.product_name) as item_name,
                        r.product_id,
                        r.order_id
                    FROM rating r
                    LEFT JOIN menuItems m ON r.product_id = m.item_id
                    LEFT JOIN GroceryItems g ON r.product_id = g.item_id
                    LEFT JOIN Groceries_Products gp ON r.product_id = gp.product_id
                    WHERE r.business_id = %s
                    ORDER BY r.created_at DESC
                    LIMIT 50
                """, [business_id])
                
                reviews = []
                for row in cursor.fetchall():
                    reviews.append({
                        'rating_id': row[0],
                        'customer_name': row[1] or 'Anonymous',
                        'rating': row[2],
                        'review': row[3],
                        'date': row[4].isoformat() if row[4] else None,
                        'item_name': row[5],
                        'product_id': row[6],
                        'order_id': row[7]
                    })
                
                # 7. COUPONS (for Coupons tab)
                cursor.execute("""
                    SELECT 
                        coupon_id,
                        coupon_code,
                        discount_type,
                        discount_value,
                        is_active,
                        valid_from,
                        valid_to,
                        max_usage_total,
                        current_usage_count
                    FROM coupons
                    WHERE business_id = %s
                    ORDER BY created_at DESC
                """, [business_id])
                
                coupons = []
                for row in cursor.fetchall():
                    coupons.append({
                        'coupon_id': row[0],
                        'code': row[1],
                        'type': row[2],
                        'value': float(row[3]) if row[3] else 0,
                        'is_active': row[4],
                        'valid_from': row[5].isoformat() if row[5] else None,
                        'valid_to': row[6].isoformat() if row[6] else None,
                        'max_usage': row[7],
                        'current_usage': row[8]
                    })
                
                # 8. OFFERS (for Offers tab)
                cursor.execute("""
                    SELECT 
                        promo_id,
                        offer_type,
                        title,
                        description,
                        discount_percentage,
                        discount_amount,
                        original_price,
                        offer_price,
                        valid_from,
                        valid_to,
                        is_active,
                        is_approved,
                        priority,
                        max_views,
                        current_views
                    FROM promotional_offers
                    WHERE business_id = %s
                    ORDER BY created_at DESC
                """, [business_id])
                
                offers = []
                for row in cursor.fetchall():
                    offers.append({
                        'offer_id': row[0],  # promo_id mapped to offer_id for frontend
                        'offer_type': row[1],
                        'title': row[2],
                        'description': row[3],
                        'discount_percentage': float(row[4]) if row[4] else None,
                        'discount_amount': float(row[5]) if row[5] else None,
                        'original_price': float(row[6]) if row[6] else None,
                        'offer_price': float(row[7]) if row[7] else None,
                        'valid_from': row[8].isoformat() if row[8] else None,
                        'valid_to': row[9].isoformat() if row[9] else None,
                        'is_active': row[10],
                        'is_approved': row[11],
                        'priority': row[12],
                        'max_views': row[13],
                        'current_views': row[14]
                    })
                
                return Response({
                    'success': True,
                    'data': {
                        'business_info': business_info,
                        'performance': performance,
                        'menu_items_count': menu_count,
                        'orders': orders,
                        'reviews': reviews,
                        'coupons': coupons,
                        'offers': offers
                    }
                }, status=status.HTTP_200_OK)
                
        except Exception as e:
            logger.error(f"Error retrieving business details: {str(e)}")
            return Response({
                'success': False,
                'message': f'Error retrieving business details: {str(e)}'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class BusinessMenuItemsView(APIView):
    """
    Get menu items for a business based on business type
    GET /api/v1/admin/business-management/{business_id}/menu/
    POST /api/v1/admin/business-management/{business_id}/menu/ - Create new item
    """
    permission_classes = []
    
    def get(self, request, business_id):
        """Get all menu items for a business based on business type"""
        try:
            logger.info(f"=== MENU ITEMS REQUEST for business_id: {business_id} ===")
            
            with connection.cursor() as cursor:
                # First, get the business type
                cursor.execute("""
                    SELECT businessType, businessName FROM businesses WHERE business_id = %s
                """, [business_id])
                
                business_type_row = cursor.fetchone()
                if not business_type_row:
                    logger.error(f"Business not found: {business_id}")
                    return Response({
                        'success': False,
                        'message': 'Business not found'
                    }, status=status.HTTP_404_NOT_FOUND)
                
                business_type = business_type_row[0]
                business_name = business_type_row[1]
                logger.info(f"Business: {business_name}, Type: {business_type}")
                
                items = []
                
                # Try menuItems table first (for restaurants/food businesses)
                logger.info(f"Querying menuItems table for business_id: {business_id}")
                cursor.execute("""
                    SELECT 
                        item_id,
                        item_name,
                        item_category,
                        size_label,
                        sku,
                        original_cost,
                        selling_price,
                        gst,
                        charges,
                        quantity,
                        is_active,
                        status,
                        item_image,
                        description,
                        availability_timings,
                        item_type,
                        preparation_time
                    FROM menuItems
                    WHERE business_id = %s
                    ORDER BY item_category, item_name
                """, [business_id])
                
                rows = cursor.fetchall()
                logger.info(f"Found {len(rows)} items in menuItems table")
                
                for row in rows:
                    # Determine status - item is active if both is_active and status are 1
                    is_active_val = row[10]  # is_active
                    status_val = row[11]     # status
                    display_status = 'active' if (is_active_val == 1 and status_val == 1) else 'inactive'
                    
                    # Build full image URL
                    image_path = row[12]  # item_image
                    if image_path:
                        # If it's a relative path, prepend the media URL
                        if not image_path.startswith('http'):
                            # Remove 'media/' prefix if it exists
                            if image_path.startswith('media/'):
                                image_path = image_path[6:]
                            image_url = f"http://localhost:8000/kirazee/media/{image_path}"
                        else:
                            image_url = image_path
                    else:
                        image_url = None
                    
                    items.append({
                        'item_id': row[0],
                        'name': row[1],
                        'category': row[2] or 'Uncategorized',
                        'size_label': row[3],
                        'sku': row[4],
                        'original_cost': float(row[5]) if row[5] else 0,
                        'price': float(row[6]) if row[6] else 0,  # selling_price
                        'gst': float(row[7]) if row[7] else 0,
                        'charges': float(row[8]) if row[8] else 0,
                        'quantity': row[9] if row[9] else 0,
                        'is_active': is_active_val,
                        'status': display_status,  # For display - 'active' or 'inactive'
                        'db_status': status_val,   # Actual DB value
                        'image': image_url,
                        'description': row[13],
                        'availability': row[14],
                        'food_type': row[15],  # Veg/Non-Veg from database
                        'preparation_time': row[16],
                        'item_type': 'restaurant'  # Table type for frontend
                    })
                
                # If no items in menuItems, try groceries_productvariants_1 (for supermarkets)
                if len(items) == 0:
                    logger.info(f"Querying groceries_productvariants_1 table for business_id: {business_id}")
                    
                    try:
                        # Query groceries_productvariants_1 with JOIN to get product details
                        cursor.execute("""
                            SELECT 
                                gpv.variant_id,
                                gp.product_name,
                                gp.sub_category,
                                gpv.selling_price,
                                gpv.is_active,
                                gp.main_image,
                                gp.description,
                                gpv.net_weight_unit as unit,
                                gpv.stock,
                                gp.product_id,
                                gpv.sku,
                                gpv.net_weight,
                                gpv.size
                            FROM Groceries_ProductVariants_1 gpv
                            JOIN Groceries_Products gp ON gpv.product_id = gp.product_id
                            WHERE gp.business_id = %s AND gpv.is_active = 1
                            ORDER BY gp.sub_category, gp.product_name
                        """, [business_id])
                        
                        rows = cursor.fetchall()
                        logger.info(f"Found {len(rows)} active variants in groceries_productvariants_1")
                        
                        if len(rows) > 0:
                            logger.info(f"Sample variant: variant_id={rows[0][0]}, name={rows[0][1]}, price={rows[0][3]}")
                        
                        for row in rows:
                            # Build display name with size/weight info
                            display_name = row[1]  # product_name
                            if row[11]:  # net_weight
                                display_name += f" ({row[11]}{row[7]})"  # net_weight + unit
                            elif row[12]:  # size
                                display_name += f" ({row[12]})"
                            
                            # Build full image URL
                            image_path = row[5]  # main_image
                            if image_path:
                                # If it's a relative path, prepend the media URL
                                if not image_path.startswith('http'):
                                    # Remove 'media/' prefix if it exists
                                    if image_path.startswith('media/'):
                                        image_path = image_path[6:]
                                    image_url = f"http://localhost:8000/kirazee/media/{image_path}"
                                else:
                                    image_url = image_path
                            else:
                                image_url = None
                            
                            items.append({
                                'item_id': row[0],  # variant_id
                                'name': display_name,
                                'category': row[2] or 'Uncategorized',  # sub_category
                                'price': float(row[3]) if row[3] else 0,  # selling_price
                                'status': 'active' if row[4] == 1 else 'inactive',  # is_active
                                'image': image_url,  # main_image with full URL
                                'description': row[6],  # description
                                'unit': row[7],  # net_weight_unit
                                'stock': row[8] if row[8] else 0,  # stock
                                'product_id': row[9],  # product_id
                                'sku': row[10],  # sku
                                'item_type': 'grocery'
                            })
                        
                        logger.info(f"Successfully added {len(items)} grocery items to response")
                        
                    except Exception as e:
                        logger.error(f"Error querying groceries_productvariants_1: {str(e)}")
                        import traceback
                        logger.error(f"Traceback: {traceback.format_exc()}")
                
                # If still no items, try fashion_products table (for mall/fashion businesses)
                if len(items) == 0:
                    logger.info(f"Querying fashion_products table for business_id: {business_id}")
                    
                    try:
                        cursor.execute("""
                            SELECT 
                                fp.product_id,
                                fp.name,
                                fp.subcategory_id,
                                fp.base_price,
                                1 as is_active,
                                fp.main_image,
                                fp.description,
                                0 as stock,
                                fp.brand,
                                NULL as size,
                                NULL as color
                            FROM fashion_products fp
                            WHERE fp.business_id = %s
                            ORDER BY fp.subcategory_id, fp.name
                        """, [business_id])
                        
                        rows = cursor.fetchall()
                        logger.info(f"Found {len(rows)} items in fashion_products table")
                        
                        for row in rows:
                            # Build full image URL
                            image_path = row[5]  # main_image
                            if image_path:
                                if not image_path.startswith('http'):
                                    # For fashion images, the path already includes 'media/' prefix
                                    # Just prepend the base URL
                                    image_url = f"http://localhost:8000/kirazee/{image_path}"
                                else:
                                    image_url = image_path
                            else:
                                image_url = None
                            
                            items.append({
                                'item_id': row[0],  # product_id
                                'name': row[1],  # name
                                'category': str(row[2]) if row[2] else 'Uncategorized',  # subcategory_id
                                'price': float(row[3]) if row[3] else 0,  # base_price
                                'status': 'active',  # Always active for now
                                'image': image_url,
                                'description': row[6],
                                'stock': row[7] if row[7] else 0,
                                'quantity': 0,  # Not available in this table
                                'brand': row[8],
                                'size': row[9],
                                'color': row[10],
                                'food_type': None,  # Not applicable for fashion
                                'original_cost': 0,  # Not available
                                'item_type': 'fashion'
                            })
                        
                        logger.info(f"Successfully added {len(items)} fashion items to response")
                        
                    except Exception as e:
                        logger.error(f"Error querying fashion_products: {str(e)}")
                        import traceback
                        logger.error(f"Traceback: {traceback.format_exc()}")
                
                logger.info(f"Returning {len(items)} total items")
                
                # Debug: If no items found, check if ANY items exist in either table
                if len(items) == 0:
                    logger.warning(f"No items found for business {business_id}")
                    
                    cursor.execute("""
                        SELECT 'menuItems' as table_name,
                               COUNT(*) as total, 
                               COUNT(DISTINCT business_id) as business_count
                        FROM menuItems 
                        UNION ALL
                        SELECT 'Groceries_Products' as table_name,
                               COUNT(*) as total,
                               COUNT(DISTINCT business_id) as business_count
                        FROM Groceries_Products
                    """)
                    debug_rows = cursor.fetchall()
                    for debug_row in debug_rows:
                        logger.info(f"Table {debug_row[0]}: {debug_row[1]} total items, {debug_row[2]} businesses")
                
                return Response({
                    'success': True,
                    'data': {
                        'items': items,
                        'total': len(items),
                        'business_type': business_type,
                        'business_name': business_name
                    }
                }, status=status.HTTP_200_OK)
                
        except Exception as e:
            logger.error(f"Error retrieving menu items: {str(e)}")
            return Response({
                'success': False,
                'message': f'Error retrieving menu items: {str(e)}'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    
    def post(self, request, business_id):
        """Create a new menu item"""
        try:
            data = request.data
            item_type = data.get('item_type', 'restaurant')
            
            logger.info(f"=== CREATE NEW ITEM ===")
            logger.info(f"Business ID: {business_id}")
            logger.info(f"Item Type: {item_type}")
            logger.info(f"Full data received: {data}")
            
            # Convert boolean status to 1/0 if needed
            status_value = data.get('status')
            if isinstance(status_value, bool):
                status_value = 1 if status_value else 0
            elif status_value == 'active':
                status_value = 1
            elif status_value == 'inactive':
                status_value = 0
            else:
                status_value = 1  # Default to active
            
            is_active_value = data.get('is_active')
            if isinstance(is_active_value, bool):
                is_active_value = 1 if is_active_value else 0
            else:
                is_active_value = 1  # Default to active
            
            logger.info(f"Converted status: {status_value}, is_active: {is_active_value}")
            
            with connection.cursor() as cursor:
                if item_type == 'restaurant':
                    # Handle availability_timings - set to NULL if empty
                    availability = data.get('availability', '')
                    if not availability or availability == '':
                        availability = None
                    
                    # Handle SKU - set to NULL if empty
                    sku = data.get('sku', '').strip()
                    if not sku or sku == '':
                        sku = None
                        logger.info(f"SKU is empty, setting to NULL")
                    
                    # Handle size_label - set to NULL if empty
                    size_label = data.get('size_label', '').strip()
                    if not size_label or size_label == '':
                        size_label = None
                    
                    # Handle item_type field (Veg/Non-Veg) - set to NULL if empty
                    food_type = data.get('food_type', '').strip()
                    if not food_type or food_type == '':
                        food_type = None
                    
                    # Handle preparation_time - set to NULL if empty
                    prep_time = data.get('preparation_time', '').strip()
                    if not prep_time or prep_time == '':
                        prep_time = None
                    
                    params = [
                        business_id,
                        data.get('name'),
                        data.get('category'),
                        size_label,  # NULL if empty
                        sku,  # NULL if empty
                        data.get('original_cost', 0),
                        data.get('price', 0),  # selling_price
                        data.get('gst', 0),
                        data.get('charges', 0),
                        data.get('quantity', 0),
                        is_active_value,
                        status_value,
                        data.get('image') or None,
                        data.get('description') or None,
                        availability,
                        food_type,  # NULL if empty (Veg/Non-Veg)
                        prep_time  # NULL if empty
                    ]
                    
                    logger.info(f"Inserting into menuItems with params: {params}")
                    
                    cursor.execute("""
                        INSERT INTO menuItems (
                            business_id, item_name, item_category, size_label, sku,
                            original_cost, selling_price, gst, charges, quantity,
                            is_active, status, item_image, description, availability_timings,
                            item_type, preparation_time
                        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """, params)
                    
                    new_item_id = cursor.lastrowid
                    logger.info(f"Item created successfully with item_id: {new_item_id}")
                    
                elif item_type == 'grocery':
                    # Handle SKU - set to NULL if empty
                    sku = data.get('sku', '').strip()
                    if not sku or sku == '':
                        sku = None
                        logger.info(f"Grocery SKU is empty, setting to NULL")
                    
                    # First, create or get the product in Groceries_Products
                    product_params = [
                        business_id,
                        data.get('name'),
                        data.get('category', 'Uncategorized'),
                        data.get('description', ''),
                        data.get('image', '')
                    ]
                    logger.info(f"Inserting into Groceries_Products with params: {product_params}")
                    
                    cursor.execute("""
                        INSERT INTO Groceries_Products (
                            business_id, product_name, sub_category, description, main_image, is_visible
                        ) VALUES (%s, %s, %s, %s, %s, 1)
                    """, product_params)
                    
                    # Get the newly created product_id
                    product_id = cursor.lastrowid
                    logger.info(f"Product created with product_id: {product_id}")
                    
                    # Now create the variant in Groceries_ProductVariants_1
                    variant_params = [
                        product_id,
                        sku,  # NULL if empty
                        data.get('price', 0),
                        data.get('stock', 0),
                        data.get('net_weight', 1),
                        data.get('unit', 'kg'),
                        1 if data.get('status', 'active') == 'active' else 0
                    ]
                    logger.info(f"Inserting into Groceries_ProductVariants_1 with params: {variant_params}")
                    
                    cursor.execute("""
                        INSERT INTO Groceries_ProductVariants_1 (
                            product_id, sku, selling_price, stock, net_weight, net_weight_unit, is_active
                        ) VALUES (%s, %s, %s, %s, %s, %s, %s)
                    """, variant_params)
                    
                    new_variant_id = cursor.lastrowid
                    logger.info(f"Variant created successfully with variant_id: {new_variant_id}")
                    
                elif item_type == 'fashion':
                    cursor.execute("""
                        INSERT INTO fashion_products (
                            business_id, name, description, main_image, is_active
                        ) VALUES (%s, %s, %s, %s, %s)
                    """, [
                        business_id,
                        data.get('name'),
                        data.get('description', ''),
                        data.get('image', ''),
                        1 if data.get('status', 'active') == 'active' else 0
                    ])
                
                logger.info(f"Item created successfully")
                return Response({
                    'success': True,
                    'message': 'Item created successfully'
                }, status=status.HTTP_201_CREATED)
                
        except Exception as e:
            logger.error(f"Error creating menu item: {str(e)}")
            import traceback
            logger.error(f"Traceback: {traceback.format_exc()}")
            return Response({
                'success': False,
                'message': f'Error creating menu item: {str(e)}'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    
    def put(self, request, business_id):
        """Update a menu item"""
        try:
            data = request.data
            item_id = data.get('item_id')
            item_type = data.get('item_type', 'restaurant')
            
            logger.info(f"=== UPDATE ITEM REQUEST ===")
            logger.info(f"Business ID: {business_id}")
            logger.info(f"Item ID: {item_id}")
            logger.info(f"Item Type: {item_type}")
            logger.info(f"Full data received: {data}")
            
            if not item_id:
                return Response({
                    'success': False,
                    'message': 'item_id is required'
                }, status=status.HTTP_400_BAD_REQUEST)
            
            # Convert status to 1/0
            status_value = data.get('status')
            if isinstance(status_value, bool):
                status_value = 1 if status_value else 0
            elif status_value == 'active':
                status_value = 1
            elif status_value == 'inactive':
                status_value = 0
            else:
                status_value = 1  # Default to active
            
            is_active_value = data.get('is_active')
            if isinstance(is_active_value, bool):
                is_active_value = 1 if is_active_value else 0
            else:
                is_active_value = 1  # Default to active
            
            logger.info(f"Converted status: {status_value}, is_active: {is_active_value}")
            
            with connection.cursor() as cursor:
                if item_type == 'restaurant':
                    update_query = """
                        UPDATE menuItems SET
                            item_name = %s,
                            item_category = %s,
                            size_label = %s,
                            sku = %s,
                            original_cost = %s,
                            selling_price = %s,
                            gst = %s,
                            charges = %s,
                            quantity = %s,
                            is_active = %s,
                            status = %s,
                            item_image = %s,
                            description = %s,
                            availability_timings = %s,
                            item_type = %s,
                            preparation_time = %s
                        WHERE item_id = %s AND business_id = %s
                    """
                    # Handle availability_timings - set to NULL if empty
                    availability = data.get('availability', '')
                    if not availability or availability == '':
                        availability = None
                    
                    # Handle SKU - set to NULL if empty
                    sku = data.get('sku', '').strip() if data.get('sku') else ''
                    if not sku or sku == '':
                        sku = None
                    
                    # Handle size_label - set to NULL if empty
                    size_label = data.get('size_label', '').strip() if data.get('size_label') else ''
                    if not size_label or size_label == '':
                        size_label = None
                    
                    # Handle food_type - set to NULL if empty
                    food_type = data.get('food_type', '').strip() if data.get('food_type') else ''
                    if not food_type or food_type == '':
                        food_type = None
                    
                    # Handle preparation_time - set to NULL if empty
                    prep_time = data.get('preparation_time', '').strip() if data.get('preparation_time') else ''
                    if not prep_time or prep_time == '':
                        prep_time = None
                    
                    params = [
                        data.get('name'),
                        data.get('category'),
                        size_label,
                        sku,
                        data.get('original_cost', 0),
                        data.get('price', 0),  # selling_price
                        data.get('gst', 0),
                        data.get('charges', 0),
                        data.get('quantity', 0),
                        is_active_value,
                        status_value,
                        data.get('image') or None,
                        data.get('description') or None,
                        availability,
                        food_type,
                        prep_time,
                        item_id,
                        business_id
                    ]
                    logger.info(f"Executing UPDATE query: {update_query}")
                    logger.info(f"Parameters: {params}")
                    cursor.execute(update_query, params)
                    logger.info(f"Rows affected: {cursor.rowcount}")
                    
                elif item_type == 'grocery':
                    # Update the variant in Groceries_ProductVariants_1
                    cursor.execute("""
                        UPDATE Groceries_ProductVariants_1 SET
                            selling_price = %s,
                            stock = %s,
                            net_weight = %s,
                            net_weight_unit = %s,
                            is_active = %s
                        WHERE variant_id = %s
                    """, [
                        data.get('price', 0),
                        data.get('stock', 0),
                        data.get('net_weight', 1),
                        data.get('unit', 'kg'),
                        1 if data.get('status') == 'active' else 0,
                        item_id
                    ])
                    
                    # Also update the product details in Groceries_Products
                    product_id = data.get('product_id')
                    if product_id:
                        cursor.execute("""
                            UPDATE Groceries_Products SET
                                product_name = %s,
                                sub_category = %s,
                                description = %s,
                                main_image = %s
                            WHERE product_id = %s AND business_id = %s
                        """, [
                            data.get('name'),
                            data.get('category'),
                            data.get('description', ''),
                            data.get('image', ''),
                            product_id,
                            business_id
                        ])
                    
                elif item_type == 'fashion':
                    cursor.execute("""
                        UPDATE fashion_products SET
                            name = %s,
                            description = %s,
                            main_image = %s,
                            is_active = %s
                        WHERE product_id = %s AND business_id = %s
                    """, [
                        data.get('name'),
                        data.get('description', ''),
                        data.get('image', ''),
                        1 if data.get('status') == 'active' else 0,
                        item_id,
                        business_id
                    ])
                
                logger.info(f"Item updated successfully, rows affected: {cursor.rowcount}")
                return Response({
                    'success': True,
                    'message': 'Item updated successfully'
                }, status=status.HTTP_200_OK)
                
        except Exception as e:
            logger.error(f"Error updating menu item: {str(e)}")
            import traceback
            logger.error(f"Traceback: {traceback.format_exc()}")
            return Response({
                'success': False,
                'message': f'Error updating menu item: {str(e)}'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    
    def delete(self, request, business_id):
        """Delete a menu item"""
        try:
            item_id = request.query_params.get('item_id')
            item_type = request.query_params.get('item_type', 'restaurant')
            
            logger.info(f"Deleting item {item_id} for business {business_id}, type: {item_type}")
            
            if not item_id:
                return Response({
                    'success': False,
                    'message': 'item_id is required'
                }, status=status.HTTP_400_BAD_REQUEST)
            
            with connection.cursor() as cursor:
                if item_type == 'restaurant':
                    cursor.execute("""
                        DELETE FROM menuItems 
                        WHERE item_id = %s AND business_id = %s
                    """, [item_id, business_id])
                    
                elif item_type == 'grocery':
                    # Delete the variant from Groceries_ProductVariants_1
                    cursor.execute("""
                        DELETE FROM Groceries_ProductVariants_1
                        WHERE variant_id = %s
                    """, [item_id])
                    
                elif item_type == 'fashion':
                    cursor.execute("""
                        DELETE FROM fashion_products
                        WHERE product_id = %s AND business_id = %s
                    """, [item_id, business_id])
                
                logger.info(f"Item deleted successfully, rows affected: {cursor.rowcount}")
                return Response({
                    'success': True,
                    'message': 'Item deleted successfully'
                }, status=status.HTTP_200_OK)
                
        except Exception as e:
            logger.error(f"Error deleting menu item: {str(e)}")
            import traceback
            logger.error(f"Traceback: {traceback.format_exc()}")
            return Response({
                'success': False,
                'message': f'Error deleting menu item: {str(e)}'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class BusinessOrdersView(APIView):
    """
    Manage orders for a specific business
    GET /api/v1/admin/business-management/{business_id}/orders/
    PUT /api/v1/admin/business-management/{business_id}/orders/
    DELETE /api/v1/admin/business-management/{business_id}/orders/
    """
    permission_classes = []

    def put(self, request, business_id):
        """Update an order"""
        try:
            order_id = request.data.get('order_id')
            order_type = request.data.get('order_type', 'restaurant')
            
            logger.info(f"=== ORDER UPDATE REQUEST ===")
            logger.info(f"Business ID from URL: {business_id}")
            logger.info(f"Order ID from request: {order_id}")
            logger.info(f"Order Type: {order_type}")
            logger.info(f"Request data: {request.data}")

            if not order_id:
                return Response({
                    'success': False,
                    'message': 'order_id is required'
                }, status=status.HTTP_400_BAD_REQUEST)

            with connection.cursor() as cursor:
                # First, check if the order exists
                if order_type == 'grocery':
                    cursor.execute("""
                        SELECT order_id, business_id FROM Groceries_orders 
                        WHERE order_id = %s
                    """, [order_id])
                else:
                    cursor.execute("""
                        SELECT order_id, business_id FROM orders 
                        WHERE order_id = %s
                    """, [order_id])
                
                existing_order = cursor.fetchone()
                logger.info(f"Existing order found: {existing_order}")
                
                if not existing_order:
                    return Response({
                        'success': False,
                        'message': f'Order {order_id} not found in database'
                    }, status=status.HTTP_404_NOT_FOUND)
                
                if order_type == 'grocery':
                    # Update Groceries_orders table
                    update_fields = []
                    params = []

                    if 'status' in request.data:
                        update_fields.append('order_status = %s')
                        params.append(request.data['status'])

                    if 'total_amount' in request.data:
                        update_fields.append('total_amount = %s')
                        params.append(request.data['total_amount'])

                    if 'delivery_charge' in request.data:
                        update_fields.append('delivery_charge = %s')
                        params.append(request.data['delivery_charge'])

                    if 'discount' in request.data:
                        update_fields.append('discount = %s')
                        params.append(request.data['discount'])

                    if 'final_amount' in request.data:
                        update_fields.append('final_amount = %s')
                        params.append(request.data['final_amount'])

                    if 'delivery_instructions' in request.data:
                        update_fields.append('delivery_instructions = %s')
                        params.append(request.data['delivery_instructions'])

                    if not update_fields:
                        return Response({
                            'success': False,
                            'message': 'No fields to update'
                        }, status=status.HTTP_400_BAD_REQUEST)

                    update_fields.append('updated_at = NOW()')
                    params.extend([order_id, business_id])

                    query = f"""
                        UPDATE Groceries_orders
                        SET {', '.join(update_fields)}
                        WHERE order_id = %s AND business_id = %s
                    """

                    cursor.execute(query, params)
                    
                    logger.info(f"Grocery order update query: {query}")
                    logger.info(f"Query params: {params}")
                    logger.info(f"Rows affected: {cursor.rowcount}")

                else:
                    # Update orders table (restaurant)
                    update_fields = []
                    params = []

                    if 'status' in request.data:
                        update_fields.append('status = %s')
                        params.append(request.data['status'])

                    if 'total_amount' in request.data:
                        update_fields.append('total_amount = %s')
                        params.append(request.data['total_amount'])

                    if 'delivery_charges' in request.data:
                        update_fields.append('delivery_charges = %s')
                        params.append(request.data['delivery_charges'])

                    if 'discount_amount' in request.data:
                        update_fields.append('discount_amount = %s')
                        params.append(request.data['discount_amount'])

                    if 'final_amount' in request.data:
                        update_fields.append('final_amount = %s')
                        params.append(request.data['final_amount'])

                    if 'delivery_instruction' in request.data or 'delivery_instructions' in request.data:
                        delivery_inst = request.data.get('delivery_instruction') or request.data.get('delivery_instructions')
                        if delivery_inst:
                            # If it's already a dict/list, use it; otherwise wrap in dict
                            if isinstance(delivery_inst, (dict, list)):
                                update_fields.append('delivery_instruction = %s')
                                params.append(json.dumps(delivery_inst))
                            else:
                                update_fields.append('delivery_instruction = %s')
                                params.append(json.dumps({'instructions': str(delivery_inst)}))
                        else:
                            update_fields.append('delivery_instruction = NULL')

                    if not update_fields:
                        return Response({
                            'success': False,
                            'message': 'No fields to update'
                        }, status=status.HTTP_400_BAD_REQUEST)

                    update_fields.append('updated_at = NOW()')
                    params.extend([order_id, business_id])

                    query = f"""
                        UPDATE orders
                        SET {', '.join(update_fields)}
                        WHERE order_id = %s AND business_id = %s
                    """

                    cursor.execute(query, params)
                    
                    logger.info(f"Restaurant order update query: {query}")
                    logger.info(f"Query params: {params}")
                    logger.info(f"Rows affected: {cursor.rowcount}")

                if cursor.rowcount == 0:
                    return Response({
                        'success': False,
                        'message': 'Order not found or no changes made'
                    }, status=status.HTTP_404_NOT_FOUND)

                return Response({
                    'success': True,
                    'message': 'Order updated successfully'
                }, status=status.HTTP_200_OK)

        except Exception as e:
            logger.error(f"Error updating order: {str(e)}")
            return Response({
                'success': False,
                'message': f'Error updating order: {str(e)}'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    def delete(self, request, business_id):
        """Delete an order"""
        try:
            order_id = request.GET.get('order_id')
            order_type = request.GET.get('order_type', 'restaurant')

            if not order_id:
                return Response({
                    'success': False,
                    'message': 'order_id is required'
                }, status=status.HTTP_400_BAD_REQUEST)

            with connection.cursor() as cursor:
                if order_type == 'grocery':
                    # Delete from Groceries_orders table
                    cursor.execute("""
                        DELETE FROM Groceries_orders
                        WHERE order_id = %s AND business_id = %s
                    """, [order_id, business_id])
                else:
                    # Delete from orders table (restaurant)
                    cursor.execute("""
                        DELETE FROM orders
                        WHERE order_id = %s AND business_id = %s
                    """, [order_id, business_id])

                if cursor.rowcount == 0:
                    return Response({
                        'success': False,
                        'message': 'Order not found'
                    }, status=status.HTTP_404_NOT_FOUND)

                return Response({
                    'success': True,
                    'message': 'Order deleted successfully'
                }, status=status.HTTP_200_OK)

        except Exception as e:
            logger.error(f"Error deleting order: {str(e)}")
            return Response({
                'success': False,
                'message': f'Error deleting order: {str(e)}'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)



class BusinessCouponsView(APIView):
    """
    Manage coupons for a specific business
    POST /api/v1/admin/business-management/{business_id}/coupons/ - Create coupon
    PUT /api/v1/admin/business-management/{business_id}/coupons/ - Update coupon
    DELETE /api/v1/admin/business-management/{business_id}/coupons/ - Delete coupon
    """
    permission_classes = []

    def post(self, request, business_id):
        """Create a new coupon"""
        try:
            data = request.data
            
            logger.info(f"=== CREATE NEW COUPON ===")
            logger.info(f"Business ID: {business_id}")
            logger.info(f"Full data received: {data}")
            
            with connection.cursor() as cursor:
                # Convert is_active to 1/0
                is_active = 1 if data.get('is_active', True) else 0
                
                params = [
                    business_id,
                    data.get('coupon_code'),
                    data.get('discount_type', 'percentage'),
                    data.get('discount_value', 0),
                    data.get('max_usage_total', None),
                    data.get('valid_from', None),
                    data.get('valid_to', None),
                    is_active
                ]
                
                logger.info(f"Inserting into coupons with params: {params}")
                
                cursor.execute("""
                    INSERT INTO coupons (
                        business_id, coupon_code, discount_type, discount_value,
                        max_usage_total, valid_from, valid_to, is_active, 
                        current_usage_count, created_by, created_at, updated_at
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 0, 'kirazee_admin', NOW(), NOW())
                """, params)
                
                new_coupon_id = cursor.lastrowid
                logger.info(f"Coupon created successfully with coupon_id: {new_coupon_id}")
                
                return Response({
                    'success': True,
                    'message': 'Coupon created successfully',
                    'coupon_id': new_coupon_id
                }, status=status.HTTP_201_CREATED)
                
        except Exception as e:
            logger.error(f"Error creating coupon: {str(e)}")
            import traceback
            logger.error(f"Traceback: {traceback.format_exc()}")
            return Response({
                'success': False,
                'message': f'Error creating coupon: {str(e)}'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    def put(self, request, business_id):
        """Update a coupon"""
        try:
            data = request.data
            coupon_id = data.get('coupon_id')
            
            logger.info(f"=== UPDATE COUPON REQUEST ===")
            logger.info(f"Business ID: {business_id}")
            logger.info(f"Coupon ID: {coupon_id}")
            logger.info(f"Full data received: {data}")
            
            if not coupon_id:
                return Response({
                    'success': False,
                    'message': 'coupon_id is required'
                }, status=status.HTTP_400_BAD_REQUEST)
            
            with connection.cursor() as cursor:
                # Convert is_active to 1/0
                is_active = 1 if data.get('is_active', True) else 0
                
                update_fields = []
                params = []
                
                if 'coupon_code' in data:
                    update_fields.append('coupon_code = %s')
                    params.append(data['coupon_code'])
                
                if 'discount_type' in data:
                    update_fields.append('discount_type = %s')
                    params.append(data['discount_type'])
                
                if 'discount_value' in data:
                    update_fields.append('discount_value = %s')
                    params.append(data['discount_value'])
                
                if 'max_usage_total' in data:
                    update_fields.append('max_usage_total = %s')
                    params.append(data['max_usage_total'])
                
                if 'valid_from' in data:
                    update_fields.append('valid_from = %s')
                    params.append(data['valid_from'])
                
                if 'valid_to' in data:
                    update_fields.append('valid_to = %s')
                    params.append(data['valid_to'])
                
                if 'is_active' in data:
                    update_fields.append('is_active = %s')
                    params.append(is_active)
                
                if not update_fields:
                    return Response({
                        'success': False,
                        'message': 'No fields to update'
                    }, status=status.HTTP_400_BAD_REQUEST)
                
                update_fields.append('updated_at = NOW()')
                params.extend([coupon_id, business_id])
                
                query = f"""
                    UPDATE coupons
                    SET {', '.join(update_fields)}
                    WHERE coupon_id = %s AND business_id = %s
                """
                
                logger.info(f"Executing UPDATE query: {query}")
                logger.info(f"Parameters: {params}")
                cursor.execute(query, params)
                logger.info(f"Rows affected: {cursor.rowcount}")
                
                if cursor.rowcount == 0:
                    return Response({
                        'success': False,
                        'message': 'Coupon not found or no changes made'
                    }, status=status.HTTP_404_NOT_FOUND)
                
                return Response({
                    'success': True,
                    'message': 'Coupon updated successfully'
                }, status=status.HTTP_200_OK)
                
        except Exception as e:
            logger.error(f"Error updating coupon: {str(e)}")
            import traceback
            logger.error(f"Traceback: {traceback.format_exc()}")
            return Response({
                'success': False,
                'message': f'Error updating coupon: {str(e)}'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    def delete(self, request, business_id):
        """Delete a coupon"""
        try:
            coupon_id = request.query_params.get('coupon_id')
            
            logger.info(f"Deleting coupon {coupon_id} for business {business_id}")
            
            if not coupon_id:
                return Response({
                    'success': False,
                    'message': 'coupon_id is required'
                }, status=status.HTTP_400_BAD_REQUEST)
            
            with connection.cursor() as cursor:
                cursor.execute("""
                    DELETE FROM coupons 
                    WHERE coupon_id = %s AND business_id = %s
                """, [coupon_id, business_id])
                
                logger.info(f"Coupon deleted successfully, rows affected: {cursor.rowcount}")
                
                if cursor.rowcount == 0:
                    return Response({
                        'success': False,
                        'message': 'Coupon not found'
                    }, status=status.HTTP_404_NOT_FOUND)
                
                return Response({
                    'success': True,
                    'message': 'Coupon deleted successfully'
                }, status=status.HTTP_200_OK)
                
        except Exception as e:
            logger.error(f"Error deleting coupon: {str(e)}")
            import traceback
            logger.error(f"Traceback: {traceback.format_exc()}")
            return Response({
                'success': False,
                'message': f'Error deleting coupon: {str(e)}'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class BusinessOffersView(APIView):
    """
    Manage promotional offers for a specific business
    POST /api/v1/admin/business-management/{business_id}/offers/ - Create offer
    PUT /api/v1/admin/business-management/{business_id}/offers/ - Update offer
    DELETE /api/v1/admin/business-management/{business_id}/offers/ - Delete offer
    """
    permission_classes = []

    def post(self, request, business_id):
        """Create a new promotional offer"""
        try:
            data = request.data
            
            logger.info(f"=== CREATE NEW OFFER ===")
            logger.info(f"Business ID: {business_id}")
            logger.info(f"Full data received: {data}")
            
            with connection.cursor() as cursor:
                # Convert is_active to 1/0
                is_active = 1 if data.get('is_active', True) else 0
                is_approved = 1 if data.get('is_approved', True) else 0
                
                params = [
                    business_id,
                    data.get('offer_type', 'general'),
                    data.get('reference_id', None),
                    data.get('title'),
                    data.get('description', ''),
                    data.get('discount_percentage', None),
                    data.get('discount_amount', None),
                    data.get('original_price', None),
                    data.get('offer_price', None),
                    data.get('valid_from', None),
                    data.get('valid_to', None),
                    is_active,
                    is_approved,
                    data.get('priority', 0),
                    data.get('max_views', None)
                ]
                
                logger.info(f"Inserting into promotional_offers with params: {params}")
                
                cursor.execute("""
                    INSERT INTO promotional_offers (
                        business_id, offer_type, reference_id, title, description,
                        discount_percentage, discount_amount, original_price, offer_price,
                        valid_from, valid_to, is_active, is_approved, priority, max_views,
                        current_views, created_at, updated_at
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 0, NOW(), NOW())
                """, params)
                
                new_promo_id = cursor.lastrowid
                logger.info(f"Offer created successfully with promo_id: {new_promo_id}")
                
                return Response({
                    'success': True,
                    'message': 'Offer created successfully',
                    'offer_id': new_promo_id
                }, status=status.HTTP_201_CREATED)
                
        except Exception as e:
            logger.error(f"Error creating offer: {str(e)}")
            import traceback
            logger.error(f"Traceback: {traceback.format_exc()}")
            return Response({
                'success': False,
                'message': f'Error creating offer: {str(e)}'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    def put(self, request, business_id):
        """Update a promotional offer"""
        try:
            data = request.data
            offer_id = data.get('offer_id')  # Frontend sends offer_id, we map it to promo_id
            
            logger.info(f"=== UPDATE OFFER REQUEST ===")
            logger.info(f"Business ID: {business_id}")
            logger.info(f"Offer ID (promo_id): {offer_id}")
            logger.info(f"Full data received: {data}")
            
            if not offer_id:
                return Response({
                    'success': False,
                    'message': 'offer_id is required'
                }, status=status.HTTP_400_BAD_REQUEST)
            
            with connection.cursor() as cursor:
                # Convert is_active to 1/0
                is_active = 1 if data.get('is_active', True) else 0
                is_approved = 1 if data.get('is_approved', True) else 0
                
                update_fields = []
                params = []
                
                if 'offer_type' in data:
                    update_fields.append('offer_type = %s')
                    params.append(data['offer_type'])
                
                if 'title' in data:
                    update_fields.append('title = %s')
                    params.append(data['title'])
                
                if 'description' in data:
                    update_fields.append('description = %s')
                    params.append(data['description'])
                
                if 'discount_percentage' in data:
                    update_fields.append('discount_percentage = %s')
                    params.append(data['discount_percentage'])
                
                if 'discount_amount' in data:
                    update_fields.append('discount_amount = %s')
                    params.append(data['discount_amount'])
                
                if 'original_price' in data:
                    update_fields.append('original_price = %s')
                    params.append(data['original_price'])
                
                if 'offer_price' in data:
                    update_fields.append('offer_price = %s')
                    params.append(data['offer_price'])
                
                if 'valid_from' in data:
                    update_fields.append('valid_from = %s')
                    params.append(data['valid_from'])
                
                if 'valid_to' in data:
                    update_fields.append('valid_to = %s')
                    params.append(data['valid_to'])
                
                if 'is_active' in data:
                    update_fields.append('is_active = %s')
                    params.append(is_active)
                
                if 'is_approved' in data:
                    update_fields.append('is_approved = %s')
                    params.append(is_approved)
                
                if 'priority' in data:
                    update_fields.append('priority = %s')
                    params.append(data['priority'])
                
                if not update_fields:
                    return Response({
                        'success': False,
                        'message': 'No fields to update'
                    }, status=status.HTTP_400_BAD_REQUEST)
                
                update_fields.append('updated_at = NOW()')
                params.extend([offer_id, business_id])
                
                query = f"""
                    UPDATE promotional_offers
                    SET {', '.join(update_fields)}
                    WHERE promo_id = %s AND business_id = %s
                """
                
                logger.info(f"Executing UPDATE query: {query}")
                logger.info(f"Parameters: {params}")
                cursor.execute(query, params)
                logger.info(f"Rows affected: {cursor.rowcount}")
                
                if cursor.rowcount == 0:
                    return Response({
                        'success': False,
                        'message': 'Offer not found or no changes made'
                    }, status=status.HTTP_404_NOT_FOUND)
                
                return Response({
                    'success': True,
                    'message': 'Offer updated successfully'
                }, status=status.HTTP_200_OK)
                
        except Exception as e:
            logger.error(f"Error updating offer: {str(e)}")
            import traceback
            logger.error(f"Traceback: {traceback.format_exc()}")
            return Response({
                'success': False,
                'message': f'Error updating offer: {str(e)}'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    def delete(self, request, business_id):
        """Delete a promotional offer"""
        try:
            offer_id = request.query_params.get('offer_id')  # Frontend sends offer_id, we map it to promo_id
            
            logger.info(f"Deleting offer (promo_id) {offer_id} for business {business_id}")
            
            if not offer_id:
                return Response({
                    'success': False,
                    'message': 'offer_id is required'
                }, status=status.HTTP_400_BAD_REQUEST)
            
            with connection.cursor() as cursor:
                cursor.execute("""
                    DELETE FROM promotional_offers 
                    WHERE promo_id = %s AND business_id = %s
                """, [offer_id, business_id])
                
                logger.info(f"Offer deleted successfully, rows affected: {cursor.rowcount}")
                
                if cursor.rowcount == 0:
                    return Response({
                        'success': False,
                        'message': 'Offer not found'
                    }, status=status.HTTP_404_NOT_FOUND)
                
                return Response({
                    'success': True,
                    'message': 'Offer deleted successfully'
                }, status=status.HTTP_200_OK)
                
        except Exception as e:
            logger.error(f"Error deleting offer: {str(e)}")
            import traceback
            logger.error(f"Traceback: {traceback.format_exc()}")
            return Response({
                'success': False,
                'message': f'Error deleting offer: {str(e)}'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
class BusinessPeakHoursView(APIView):
    """
    Get business peak hours histogram data with period filtering
    GET /api/v1/admin/business-management/{business_id}/peak-hours/?period=today|7days|month|year
    
    Supports dynamic period filtering:
    - today: Today's peak hours only
    - 7days: Last 7 days peak hours
    - month: Last 30 days peak hours  
    - year: Last 365 days peak hours
    """
    permission_classes = []

    def get(self, request, business_id):
        """Get histogram data for peak hours based on selected period"""
        try:
            # Get period parameter from query string (default: 7days)
            period = request.GET.get('period', '7days')  # Options: 'today', '7days', 'month', 'year'
            
            with connection.cursor() as cursor:
                # Get business type for proper filtering
                cursor.execute(
                    "SELECT businessType FROM businesses WHERE business_id = %s",
                    [business_id]
                )
                business_row = cursor.fetchone()
                if not business_row:
                    return Response({
                        'success': False,
                        'message': 'Business not found'
                    }, status=status.HTTP_404_NOT_FOUND)
                
                business_type = str(business_row[0] or "").strip().upper()
                
                # Get histogram data for the specified period
                histogram_data = self._get_hourly_histogram(cursor, business_id, business_type, period)
                
                return Response({
                    'success': True,
                    'data': histogram_data,
                    'period': period
                }, status=status.HTTP_200_OK)
                    
        except Exception as e:
            logger.error(f"Error retrieving peak hours histogram for business {business_id}: {str(e)}")
            return Response({
                'success': False,
                'message': f'Error retrieving peak hours histogram: {str(e)}'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    
    def _get_hourly_histogram(self, cursor, business_id, business_type=None, period='7days'):
        """Get complete histogram for all 24 hours for the specified period"""
        
        # Calculate date range based on period
        from datetime import datetime, timedelta
        today = timezone.now().date()
        
        if period == 'today':
            start_date = today
            date_condition = "DATE(created_at) = %s"
            date_params = [start_date]
        elif period == '7days':
            start_date = today - timedelta(days=7)
            date_condition = "DATE(created_at) >= %s"
            date_params = [start_date]
        elif period == 'month':
            start_date = today - timedelta(days=30)
            date_condition = "DATE(created_at) >= %s"
            date_params = [start_date]
        elif period == 'year':
            start_date = today - timedelta(days=365)
            date_condition = "DATE(created_at) >= %s"
            date_params = [start_date]
        else:
            # Default to 7 days
            start_date = today - timedelta(days=7)
            date_condition = "DATE(created_at) >= %s"
            date_params = [start_date]
        
        # Initialize histogram with all 24 hours
        histogram = {}
        for hour in range(24):
            histogram[hour] = 0
        
        # Get orders from regular orders table with date filtering
        cursor.execute(f"""
            SELECT HOUR(created_at) as hour, COUNT(*) as order_count 
            FROM orders 
            WHERE business_id = %s AND status IN ('delivered','completed') AND {date_condition}
            GROUP BY HOUR(created_at)
        """, [business_id] + date_params)
        
        for row in cursor.fetchall():
            hour = row[0]
            count = int(row[1])
            histogram[hour] += count
        
        # Get orders from grocery orders if table exists and business type allows
        if (business_type or '').upper() in ('', 'R01'):
            try:
                cursor.execute(f"""
                    SELECT HOUR(created_at) as hour, COUNT(*) as order_count 
                    FROM Groceries_orders 
                    WHERE business_id = %s AND order_status IN ('delivered', 'completed', 'grocery_delivered', 'grocery_picked_up') AND {date_condition}
                    GROUP BY HOUR(created_at)
                """, [business_id] + date_params)
                
                for row in cursor.fetchall():
                    hour = row[0]
                    count = int(row[1])
                    histogram[hour] += count
            except Exception as e:
                logger.warning(f"Could not query Groceries_orders: {e}")
        
        # Get orders from counter orders with date filtering
        try:
            cursor.execute(f"""
                SELECT HOUR(created_at) as hour, COUNT(*) as order_count 
                FROM business_counter_orders 
                WHERE business_id = %s AND status = 'paid' AND {date_condition}
                GROUP BY HOUR(created_at)
            """, [business_id] + date_params)
            
            for row in cursor.fetchall():
                hour = row[0]
                count = int(row[1])
                histogram[hour] += count
        except Exception as e:
            logger.warning(f"Could not query business_counter_orders: {e}")
        
        # Return complete histogram for all 24 hours
        complete_histogram = []
        for hour in range(24):
            # Convert 24-hour format to 12-hour format with AM/PM
            if hour == 0:
                time_label = '12AM'
            elif hour < 12:
                time_label = f'{hour}AM'
            elif hour == 12:
                time_label = '12PM'
            else:
                time_label = f'{hour-12}PM'
            
            complete_histogram.append({
                'hour': hour,
                'time_label': time_label,
                'orders': histogram[hour]
            })
        
        return complete_histogram


class BusinessOrderStatusView(APIView):
    """
    Get business order status distribution
    GET /api/v1/admin/business-management/{business_id}/order-status/
    """
    permission_classes = []

    def get(self, request, business_id):
        """Get order status distribution for a specific business (Dynamic Period)"""
        try:
            # Get period parameter from query string (default: 7days)
            period = request.GET.get('period', '7days')  # Options: 'today', '7days'
            
            # Calculate date range based on period
            from datetime import datetime, timedelta
            today = timezone.now().date()
            
            if period == 'today':
                start_date = today
                period_label = 'Today'
                date_range = f"{today}"
                date_condition = "DATE(created_at) = %s"
            else:  # Default to 7days
                start_date = today - timedelta(days=7)
                period_label = 'Last 7 Days'
                date_range = f"{start_date} to {today}"
                date_condition = "DATE(created_at) >= %s"
            
            with connection.cursor() as cursor:
                # Get order status counts from regular orders
                cursor.execute(f"""
                    SELECT
                        status,
                        COUNT(*) as count
                    FROM orders
                    WHERE business_id = %s AND {date_condition}
                    GROUP BY status
                """, [business_id, start_date])

                regular_orders = cursor.fetchall()

                # Get order status counts from grocery orders if table exists
                grocery_orders = []
                try:
                    cursor.execute(f"""
                        SELECT
                            order_status as status,
                            COUNT(*) as count
                        FROM Groceries_orders
                        WHERE business_id = %s AND {date_condition}
                        GROUP BY order_status
                    """, [business_id, start_date])
                    grocery_orders = cursor.fetchall()
                except Exception:
                    pass  # Table might not exist

                # Combine and normalize status counts
                status_counts = {}

                # Process regular orders
                for status_name, count in regular_orders:
                    normalized_status = self.normalize_status(status_name)
                    status_counts[normalized_status] = status_counts.get(normalized_status, 0) + count

                # Process grocery orders
                for status_name, count in grocery_orders:
                    normalized_status = self.normalize_status(status_name)
                    status_counts[normalized_status] = status_counts.get(normalized_status, 0) + count

                # Format for frontend
                formatted_data = {
                    'completed_orders': status_counts.get('completed', 0),
                    'pending_orders': status_counts.get('pending', 0),
                    'cancelled_orders': status_counts.get('cancelled', 0),
                    'processing_orders': status_counts.get('processing', 0),
                    'period': period_label,
                    'date_range': date_range,
                    'period_filter': period
                }

                return Response({
                    'success': True,
                    'data': formatted_data
                }, status=status.HTTP_200_OK)

        except Exception as e:
            logger.error(f"Error retrieving order status for business {business_id}: {str(e)}")
            return Response({
                'success': False,
                'message': f'Error retrieving order status: {str(e)}'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    def normalize_status(self, status):
        """Normalize different status names to standard categories"""
        status = status.lower() if status else ''

        if status in ['delivered', 'completed', 'grocery_delivered', 'grocery_picked_up']:
            return 'completed'
        elif status in ['pending', 'confirmed', 'preparing', 'ready']:
            return 'pending'
        elif status in ['cancelled', 'rejected', 'failed']:
            return 'cancelled'
        elif status in ['processing', 'accepted', 'in_progress']:
            return 'processing'
        else:
            return 'pending'  # Default fallback
