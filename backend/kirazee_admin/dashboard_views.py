"""
Kirazee Admin Dashboard Summary Service

This module provides the comprehensive dashboard summary endpoint
that delivers all KPIs and operational metrics in a single API call.
"""

import logging
from django.db import connection
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from django.db.models import Count, Sum, Q

logger = logging.getLogger(__name__)


class AdminDashboardSummaryView(APIView):
    """
    Comprehensive admin dashboard summary endpoint
    
    GET /api/v1/admin/dashboard/summary - All KPIs and operational metrics in one call
    
    Provides:
    - Key Performance Indicators (KPIs)
    - Business Statistics
    - Delivery Fleet Statistics  
    - Recent Orders (Top 10)
    - User Analytics
    
    Optimized for main dashboard view with all essential metrics.
    """
    permission_classes = []  # Remove authentication requirement for development
    
    def _format_number(self, value):
        """Format number according to Indian numbering system"""
        if not isinstance(value, (int, float)):
            return str(value)
            
        value = float(value)
        
        if value >= 10000000:  # 1 Crore or more
            return f"{value/10000000:.1f}Cr"
        elif value >= 100000:  # 1 Lac or more
            return f"{value/100000:.1f}Lac"
        elif value >= 1000:  # 1k or more
            return f"{value/1000:.1f}k"
        else:
            return str(int(value)) if value == int(value) else f"{value:.2f}"
    
    def get(self, request):
        """Retrieve comprehensive dashboard summary with all KPIs and operational metrics"""
        try:
            with connection.cursor() as cursor:
                # Detect connection collation/charset for safe JOINs and UNION text outputs
                detected_collation = 'utf8mb4_0900_ai_ci'
                detected_charset = 'utf8mb4'
                try:
                    cursor.execute("SELECT @@collation_connection")
                    row = cursor.fetchone()
                    if row and isinstance(row[0], str):
                        val = row[0]
                        detected_collation = val
                        if val.lower().startswith('utf8mb4'):
                            detected_charset = 'utf8mb4'
                        else:
                            detected_charset = 'utf8'
                except Exception:
                    pass
                
                # =================== KPI METRICS ===================
                
                # 1. Revenue by Business (from orders and business_counter_orders tables)
                cursor.execute("""
                    SELECT 
                        b.business_id,
                        b.businessName,
                        COALESCE(SUM(CASE WHEN o.status IN ('delivered', 'completed') THEN o.final_amount ELSE 0 END), 0) as revenue,
                        COUNT(CASE WHEN o.status IN ('delivered', 'completed') THEN 1 END) as order_count
                    FROM businesses b
                    LEFT JOIN orders o ON b.business_id = o.business_id
                    WHERE b.paymentstatus = 1
                    GROUP BY b.business_id, b.businessName
                """)
                
                revenue_results = cursor.fetchall()
                
                # Get counter orders revenue
                cursor.execute("""
                    SELECT 
                        b.business_id,
                        b.businessName,
                        COALESCE(SUM(CASE WHEN bco.status = 'paid' THEN bco.total_amount ELSE 0 END), 0) as counter_revenue,
                        COUNT(CASE WHEN bco.status = 'paid' THEN 1 END) as counter_order_count
                    FROM businesses b
                    LEFT JOIN business_counter_orders bco ON b.business_id = bco.business_id
                    WHERE b.paymentstatus = 1
                    GROUP BY b.business_id, b.businessName
                """)
                
                counter_results = cursor.fetchall()
                
                # Combine orders and counter orders revenue
                combined_revenue = {}
                for business_id, business_name, revenue, order_count in revenue_results:
                    combined_revenue[business_id] = {
                        'business_name': business_name,
                        'revenue': float(revenue),
                        'orders': int(order_count)
                    }
                
                # Add counter revenue and orders
                for business_id, business_name, counter_revenue, counter_order_count in counter_results:
                    if business_id in combined_revenue:
                        combined_revenue[business_id]['revenue'] += float(counter_revenue)
                        combined_revenue[business_id]['orders'] += int(counter_order_count)
                    else:
                        combined_revenue[business_id] = {
                            'business_name': business_name,
                            'revenue': float(counter_revenue),
                            'orders': int(counter_order_count)
                        }
                
                # Convert to list and sort by revenue
                business_revenue_list = [
                    {
                        'business_id': business_id,
                        'business_name': data['business_name'],
                        'revenue': self._format_number(data['revenue']),
                        'raw_revenue': data['revenue'],
                        'orders': data['orders']
                    }
                    for business_id, data in combined_revenue.items()
                ]
                business_revenue_list.sort(key=lambda x: x['raw_revenue'], reverse=True)
                
                # Calculate total revenue
                total_revenue = sum(data['raw_revenue'] for data in business_revenue_list)
                
                # Debug: Status breakdown for orders table only (revenue calculation)
                cursor.execute(f"""
                    SELECT CONVERT(status USING {detected_charset}) COLLATE {detected_collation} as status, COUNT(*) as count, COALESCE(SUM(final_amount), 0) as total_amount
                    FROM orders 
                    WHERE final_amount > 0
                    GROUP BY status
                    ORDER BY status
                """)
                status_breakdown = cursor.fetchall()
                
                # Debug: Revenue breakdown by status (delivered/completed vs others)
                cursor.execute(f"""
                    SELECT 
                        CASE 
                            WHEN status IN ('delivered', 'completed') THEN 'Revenue_Generating'
                            ELSE 'Non_Revenue_Generating'
                        END as revenue_category,
                        COUNT(*) as count, 
                        COALESCE(SUM(final_amount), 0) as total_amount
                    FROM orders 
                    WHERE final_amount > 0
                    GROUP BY revenue_category
                """)
                revenue_breakdown = cursor.fetchall()
                
                # 2. Orders by Business - separated into online and counter orders
                # Online orders from orders table
                cursor.execute(f"""
                    SELECT 
                        b.business_id,
                        b.businessName,
                        COUNT(o.order_id) as online_order_count
                    FROM businesses b
                    LEFT JOIN orders o ON CONVERT(b.business_id USING {detected_charset}) COLLATE {detected_collation} = CONVERT(o.business_id USING {detected_charset}) COLLATE {detected_collation}
                    GROUP BY b.business_id, b.businessName
                """)
                online_order_results = cursor.fetchall()
                
                # Counter orders from business_counter_orders table
                cursor.execute(f"""
                    SELECT 
                        b.business_id,
                        b.businessName,
                        COUNT(bco.order_id) as counter_order_count
                    FROM businesses b
                    LEFT JOIN business_counter_orders bco ON CONVERT(b.business_id USING {detected_charset}) COLLATE {detected_collation} = CONVERT(bco.business_id USING {detected_charset}) COLLATE {detected_collation}
                    GROUP BY b.business_id, b.businessName
                """)
                counter_order_results = cursor.fetchall()
                
                # Process business-wise order counts
                business_orders = {}
                
                # Process online orders
                for business_id, business_name, online_order_count in online_order_results:
                    if not business_id:
                        continue
                    business_orders[business_id] = {
                        'business_name': business_name or f'Business {business_id}',
                        'online_orders': int(online_order_count or 0),
                        'counter_orders': 0,
                        'total_orders': int(online_order_count or 0),
                        'recent_order_id': None
                    }
                
                # Add counter orders
                for business_id, business_name, counter_order_count in counter_order_results:
                    if not business_id:
                        continue
                    if business_id in business_orders:
                        business_orders[business_id]['counter_orders'] = int(counter_order_count or 0)
                        business_orders[business_id]['total_orders'] += int(counter_order_count or 0)
                    else:
                        business_orders[business_id] = {
                            'business_name': business_name or f'Business {business_id}',
                            'online_orders': 0,
                            'counter_orders': int(counter_order_count or 0),
                            'total_orders': int(counter_order_count or 0),
                            'recent_order_id': None
                        }
                
                # Get most recent order ID for each business (from both tables)
                # Use separate queries to avoid UNION issues
                cursor.execute(f"""
                    SELECT 
                        business_id, 
                        order_id, 
                        created_at,
                        CONVERT('online' USING {detected_charset}) COLLATE {detected_collation} as order_type,
                        ROW_NUMBER() OVER (PARTITION BY business_id ORDER BY created_at DESC) as rn
                    FROM orders
                """)
                online_recent_orders = cursor.fetchall()
                
                cursor.execute(f"""
                    SELECT 
                        business_id, 
                        order_id, 
                        created_at,
                        CONVERT('counter' USING {detected_charset}) COLLATE {detected_collation} as order_type,
                        ROW_NUMBER() OVER (PARTITION BY business_id ORDER BY created_at DESC) as rn
                    FROM business_counter_orders
                """)
                counter_recent_orders = cursor.fetchall()
                
                # Combine the results
                recent_orders = online_recent_orders + counter_recent_orders
                
                for business_id, order_id, _, order_type, rn in recent_orders:
                    if rn == 1 and business_id in business_orders:
                        business_orders[business_id]['recent_order_id'] = str(order_id)
                        business_orders[business_id]['recent_order_type'] = order_type
                
                # Convert to list and sort by total orders
                business_order_list = [
                    {
                        'business_name': data['business_name'],
                        'online_orders': data['online_orders'],
                        'counter_orders': data['counter_orders'],
                        'total_orders': data['total_orders'],
                        'recent_order_id': data['recent_order_id'],
                        'recent_order_type': data.get('recent_order_type', 'online')
                    }
                    for business_id, data in business_orders.items()
                ]
                business_order_list.sort(key=lambda x: x['total_orders'], reverse=True)
                
                # Calculate total orders
                total_online_orders = sum(business['online_orders'] for business in business_order_list)
                total_counter_orders = sum(business['counter_orders'] for business in business_order_list)
                total_orders = total_online_orders + total_counter_orders
                
                # 3. Get all businesses with their status
                cursor.execute("""
                    SELECT 
                        business_id,
                        businessName,
                        status,
                        CASE 
                            WHEN status = 1 THEN 'Active'
                            ELSE 'Inactive'
                        END as status_text
                    FROM businesses
                    ORDER BY businessName
                """)
                all_businesses = [
                    {
                        'id': row[0],
                        'name': row[1] or f'Business {row[0]}',
                        'status': row[3]
                    }
                    for row in cursor.fetchall()
                ]
                
                active_businesses = sum(1 for b in all_businesses if b['status'] == 'Active')
                
                # 4. Unique Customers - count all customers who have placed any orders
                cursor.execute("""
                    SELECT COUNT(DISTINCT o.user_id) as unique_customers_count
                    FROM orders o
                    WHERE o.user_id IS NOT NULL
                """)
                unique_customers_count_result = cursor.fetchone()
                unique_customers = unique_customers_count_result[0] if unique_customers_count_result else 0
                
                # Get detailed customer list for display (limit to 50 for performance)
                cursor.execute(f"""
                    SELECT DISTINCT 
                        r.user_id,
                        r.firstName,
                        r.lastName,
                        COALESCE(r.emailID, '') as email,
                        COALESCE(r.mobileNumber, '') as mobile,
                        r.is_active,
                        MAX(o.created_at) as last_order_date
                    FROM registrations r
                    INNER JOIN orders o ON r.user_id = o.user_id
                    GROUP BY r.user_id, r.firstName, r.lastName, r.emailID, r.mobileNumber, r.is_active
                    ORDER BY last_order_date DESC
                    LIMIT 50
                """)
                customer_results = cursor.fetchall()
                
                # Format customer data
                unique_customers_list = []
                for row in customer_results:
                    user_id, first_name, last_name, email, mobile, is_active, last_order_date = row
                    
                    # Format name
                    name_parts = []
                    if first_name and first_name.strip():
                        name_parts.append(first_name.strip())
                    if last_name and last_name.strip():
                        name_parts.append(last_name.strip())
                    full_name = ' '.join(name_parts) if name_parts else 'Unknown'
                    
                    # Format mobile (mask for privacy)
                    mobile_display = mobile if mobile else 'Not Provided'
                    if mobile and len(mobile) >= 10:
                        mobile_display = f"******{mobile[-4:]}" if len(mobile) > 4 else mobile
                    
                    # Format email (mask for privacy)
                    email_display = email if email else 'Not Provided'
                    if email and '@' in email:
                        local, domain = email.split('@', 1)
                        if len(local) > 2:
                            email_display = f"{local[:2]}***@{domain}"
                    
                    unique_customers_list.append({
                        'user_id': user_id,
                        'name': full_name,
                        'email': email_display,
                        'mobile': mobile_display,
                        'is_active': 'Active' if is_active == 1 else 'Inactive',
                        'last_order_date': last_order_date.strftime('%Y-%m-%d %H:%M:%S') if last_order_date else None
                    })
                
                # Use the count from the separate query
                unique_customers_list = []
                
                # 4.1. Recent Customers (registered this week)
                cursor.execute(f"""
                    SELECT 
                        r.user_id,
                        r.firstName,
                        r.lastName,
                        COALESCE(r.emailID, '') as email,
                        COALESCE(r.mobileNumber, '') as mobile,
                        r.is_active,
                        r.created_at as registration_date
                    FROM registrations r
                    WHERE r.created_at >= DATE_SUB(CURDATE(), INTERVAL 7 DAY)
                    ORDER BY r.created_at DESC
                """)
                recent_customers_results = cursor.fetchall()
                
                # Format recent customer data
                recent_customers_list = []
                for row in recent_customers_results:
                    user_id, first_name, last_name, email, mobile, is_active, registration_date = row
                    
                    # Format name
                    name_parts = []
                    if first_name and first_name.strip():
                        name_parts.append(first_name.strip())
                    if last_name and last_name.strip():
                        name_parts.append(last_name.strip())
                    full_name = ' '.join(name_parts) if name_parts else 'Unknown'
                    
                    # Format mobile (mask for privacy)
                    mobile_display = mobile if mobile else 'Not Provided'
                    if mobile and len(mobile) >= 10:
                        mobile_display = f"******{mobile[-4:]}" if len(mobile) > 4 else mobile
                    
                    # Format email (mask for privacy)
                    email_display = email if email else 'Not Provided'
                    if email and '@' in email:
                        local, domain = email.split('@', 1)
                        if len(local) > 2:
                            email_display = f"{local[:2]}***@{domain}"
                    
                    recent_customers_list.append({
                        'user_id': user_id,
                        'name': full_name,
                        'email': email_display,
                        'mobile': mobile_display,
                        'is_active': 'Active' if is_active == 1 else 'Inactive',
                        'registration_date': registration_date.strftime('%Y-%m-%d %H:%M:%S') if registration_date else None
                    })
                
                recent_customers_count = len(recent_customers_list)
                
                # 5. Average Order Value - calculate from delivered/completed orders only
                # Count only revenue-generating orders for AOV calculation
                total_revenue_orders = sum(1 for data in business_revenue_list if data['raw_revenue'] > 0)
                average_order_value = (total_revenue / total_revenue_orders) if total_revenue_orders > 0 else 0
                
                # 6. Delivery Partners with detailed stats
                cursor.execute(f"""
                    SELECT 
                        dp.id,
                        CONCAT(r.firstName, ' ', COALESCE(r.lastName, '')) as name,
                        dp.is_available,
                        dp.rating,
                        (
                            SELECT COUNT(*) 
                            FROM orders o 
                            WHERE o.delivery_partner_id = dp.id 
                            AND o.status = 'delivered'
                        ) as completed_orders,
                        (
                            SELECT COUNT(*)
                            FROM orders o
                            WHERE o.delivery_partner_id = dp.id
                            AND o.status IN ('picked_up', 'out_for_delivery')
                        ) as current_orders
                    FROM delivery_partner dp
                    LEFT JOIN registrations r ON dp.user_id = r.user_id
                """)
                delivery_partners = [
                    {
                        'id': row[0],
                        'name': row[1].strip() if row[1] else f'Partner {row[0]}',
                        'status': 'Available' if row[2] == 1 else 'Unavailable',
                        'current_orders_in_hand': row[5] or 0,
                        'total_completed_orders': self._format_number(row[4] or 0),
                        'average_rating': float(row[3] or 0)
                    }
                    for row in cursor.fetchall()
                ]
                
                active_delivery_partners = sum(1 for dp in delivery_partners if dp['status'] == 'Available')
                
                # =================== BUSINESS STATISTICS ===================
                
                # 1. Total businesses count
                cursor.execute("SELECT COUNT(*) as total_businesses FROM businesses")
                total_business_count = cursor.fetchone()[0]
                
                # 2. Non-verified businesses count
                cursor.execute("""
                    SELECT COUNT(*) as non_verified_count 
                    FROM businesses 
                    WHERE is_verified = 0
                """)
                non_verified_count = cursor.fetchone()[0]
                
                # 3. Payment pending businesses count
                cursor.execute("""
                    SELECT COUNT(*) as payment_pending_count 
                    FROM businesses 
                    WHERE paymentstatus = 0
                """)
                payment_pending_count = cursor.fetchone()[0]
                
                # =================== DELIVERY FLEET STATISTICS ===================
                
                # 1. In Transit orders count (picked_up status)
                cursor.execute("""
                    SELECT COUNT(*) as in_transit_count
                    FROM orders
                    WHERE status IN ('picked_up', 'travelling', 'out_for_delivery') 
                    AND order_type = 'delivery'
                """)
                in_transit_orders_count = cursor.fetchone()[0]
                
                # 2. Completed Today orders
                cursor.execute("""
                    SELECT COUNT(*) as completed_today_count
                    FROM orders
                    WHERE status IN ('delivered', 'completed', 'cod')
                    AND order_type = 'delivery'
                    AND DATE(created_at) = CURDATE()
                """)
                completed_today_count = cursor.fetchone()[0]
                
                # =================== RECENT ORDERS ===================
                
                # 7. Recent Orders (from both orders and business_counter_orders tables)
                # Get recent orders separately to avoid UNION with LIMIT issues
                cursor.execute(f"""
                    SELECT 
                        CONVERT('online' USING {detected_charset}) COLLATE {detected_collation} as order_system,
                        o.order_id,
                        o.order_number,
                        b.businessName as business_name,
                        o.order_type,
                        o.status,
                        o.final_amount,
                        o.created_at
                    FROM orders o
                    LEFT JOIN businesses b ON CONVERT(o.business_id USING {detected_charset}) COLLATE {detected_collation} = CONVERT(b.business_id USING {detected_charset}) COLLATE {detected_collation}
                    ORDER BY o.created_at DESC
                    LIMIT 5
                """)
                online_orders = cursor.fetchall()
                
                cursor.execute(f"""
                    SELECT 
                        CONVERT('counter' USING {detected_charset}) COLLATE {detected_collation} as order_system,
                        bco.order_id,
                        bco.order_id as order_number,
                        b.businessName as business_name,
                        bco.order_type,
                        bco.status,
                        bco.total_amount as final_amount,
                        bco.created_at
                    FROM business_counter_orders bco
                    LEFT JOIN businesses b ON CONVERT(bco.business_id USING {detected_charset}) COLLATE {detected_collation} = CONVERT(b.business_id USING {detected_charset}) COLLATE {detected_collation}
                    ORDER BY bco.created_at DESC
                    LIMIT 5
                """)
                counter_orders = cursor.fetchall()
                
                # Combine and sort by created_at
                recent_orders_data = list(online_orders) + list(counter_orders)
                recent_orders_data.sort(key=lambda x: x[7], reverse=True)  # Sort by created_at
                recent_orders_data = recent_orders_data[:10]  # Limit to 10 results
                
                # Format recent orders
                formatted_recent_orders = []
                for order in recent_orders_data:
                    formatted_recent_orders.append({
                        'order_system': order[0],
                        'order_id': order[1],
                        'order_number': order[2],
                        'business_name': order[3] if order[3] else 'Unknown Business',
                        'order_type': order[4],
                        'status': order[5],
                        'final_amount': float(order[6]) if order[6] else 0,
                        'created_at': order[7].strftime('%Y-%m-%d %H:%M:%S') if order[7] else None
                    })
                
                # =================== USER ANALYTICS ===================
                cursor.execute("""
                    SELECT 
                        COUNT(CASE WHEN is_active = 1 THEN 1 END) as active_users,
                        COUNT(CASE WHEN is_active = 0 OR is_active IS NULL THEN 1 END) as inactive_users,
                        COUNT(*) as total_users
                    FROM registrations
                """)
                user_stats = cursor.fetchone()
                
                # =================== COMPILE DASHBOARD RESPONSE ===================
                
                dashboard_summary = {
                    'success': True,
                    'message': 'Dashboard summary retrieved successfully',
                    'revenue_metrics': {
                        'formatted_total_revenue': self._format_number(total_revenue),
                        'raw_total_revenue': float(total_revenue),
                        'business_revenue_list': business_revenue_list
                    },
                    'order_metrics': {
                        'formatted_total_orders': self._format_number(total_orders),
                        'total_online_orders': total_online_orders,
                        'total_counter_orders': total_counter_orders,
                        'business_order_breakdown': business_order_list
                    },
                    'business_list_metrics': {
                        'total_count': len(all_businesses)
                    },
                    'delivery_partner_metrics': {
                        'formatted_active_count': self._format_number(active_delivery_partners),
                        'partners_list': delivery_partners
                    },
                    'user_analytics': {
                        'active_users': user_stats[0],
                        'inactive_users': user_stats[1],
                        'total_users': self._format_number(user_stats[2]),
                        'unique_customers_details': unique_customers_list[:50],  # Limit to 50 most recent customers
                        'recent_customers_details': recent_customers_list[:20]  # Limit to 20 most recent registrations
                    },
                    'kpi_metrics': {
                        'total_revenue': float(total_revenue),
                        'total_orders': total_orders,
                        'total_online_orders': total_online_orders,
                        'total_counter_orders': total_counter_orders,
                        'active_businesses': active_businesses,
                        'unique_customers': unique_customers,
                        'recent_customers': recent_customers_count,
                        'average_order_value': float(average_order_value),
                        'active_delivery_partners': active_delivery_partners
                    },
                    'recent_orders': formatted_recent_orders,
                    'debug_info': {
                        'status_breakdown': [
                            {
                                'status': row[0],
                                'count': row[1],
                                'total_amount': float(row[2])
                            } for row in status_breakdown
                        ],
                        'revenue_breakdown': [
                            {
                                'revenue_category': row[0],
                                'count': row[1],
                                'total_amount': float(row[2])
                            } for row in revenue_breakdown
                        ]
                    }
                }
                
                return Response(dashboard_summary, status=status.HTTP_200_OK)
                
        except Exception as e:
            logger.error(f"Error retrieving dashboard summary: {str(e)}")
            return Response({
                'success': False,
                'message': f'Error retrieving dashboard summary: {str(e)}'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
