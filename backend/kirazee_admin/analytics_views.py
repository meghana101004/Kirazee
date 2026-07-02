from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from django.db.models import Sum, Count, Q, F, FloatField, Avg, Max
from django.db.models.functions import TruncDate, TruncDay, TruncWeek, TruncMonth
from django.utils import timezone
from django.db import connection
import logging

logger = logging.getLogger(__name__)

class RevenueTrendView(APIView):
    """
    Enhanced revenue trend analytics with comprehensive business statistics
    GET /api/v1/admin/analytics/revenue-trend/
    Supports daily, weekly, monthly aggregation
    Includes complete order status, order type, and business-level analytics
    """
    permission_classes = []
    
    def get(self, request):
        """Get comprehensive revenue trend data with business analytics"""
        try:
            # Get query parameters
            period = request.query_params.get('period', 'daily')  # daily, weekly, monthly
            days = int(request.query_params.get('days', 30))  # Default last 30 days
            include_business_details = request.query_params.get('include_business_details', 'true').lower() == 'true'
            
            # Validate period
            if period not in ['daily', 'weekly', 'monthly']:
                return Response({
                    'success': False,
                    'message': 'Invalid period. Use daily, weekly, or monthly',
                    'data': None
                }, status=status.HTTP_400_BAD_REQUEST)
            
            # Validate days
            if days > 365:
                days = 365  # Limit to 1 year max
            
            # Calculate start date
            start_date = timezone.now() - timezone.timedelta(days=days)
            
            # Determine truncation function based on period
            if period == 'daily':
                date_trunc = 'DATE(o.created_at)'
                date_format = '%Y-%m-%d'
            elif period == 'weekly':
                date_trunc = 'DATE_FORMAT(o.created_at, "%Y-%u")'  # Year-Week format
                date_format = '%Y-W%U'
            else:  # monthly
                date_trunc = 'DATE_FORMAT(o.created_at, "%Y-%m")'  # Year-Month format
                date_format = '%Y-%m'
            
            with connection.cursor() as cursor:
                # Build comprehensive revenue trend query
                cursor.execute(f"""
                    SELECT 
                        {date_trunc} as period_date,
                        COALESCE(SUM(o.final_amount), 0) as revenue,
                        COUNT(DISTINCT o.order_id) as orders,
                        COUNT(DISTINCT o.user_id) as unique_customers,
                        COALESCE(AVG(o.final_amount), 0) as avg_order_value,
                        COUNT(DISTINCT CASE WHEN o.status = 'pending' THEN o.order_id END) as pending_orders,
                        COUNT(DISTINCT CASE WHEN o.status = 'confirmed' THEN o.order_id END) as confirmed_orders,
                        COUNT(DISTINCT CASE WHEN o.status = 'preparing' THEN o.order_id END) as preparing_orders,
                        COUNT(DISTINCT CASE WHEN o.status = 'ready' THEN o.order_id END) as ready_orders,
                        COUNT(DISTINCT CASE WHEN o.status = 'assigned' THEN o.order_id END) as assigned_orders,
                        COUNT(DISTINCT CASE WHEN o.status = 'out_for_delivery' THEN o.order_id END) as out_for_delivery_orders,
                        COUNT(DISTINCT CASE WHEN o.status = 'delivered' THEN o.order_id END) as delivered_orders,
                        COUNT(DISTINCT CASE WHEN o.status = 'completed' THEN o.order_id END) as completed_orders,
                        COUNT(DISTINCT CASE WHEN o.status = 'cancelled' THEN o.order_id END) as cancelled_orders,
                        COALESCE(SUM(CASE WHEN o.status IN ('delivered', 'completed') THEN o.final_amount ELSE 0 END), 0) as actual_revenue
                    FROM orders o
                    WHERE o.created_at >= DATE_SUB(CURDATE(), INTERVAL {days} DAY)
                    GROUP BY {date_trunc}
                    ORDER BY period_date ASC
                """)
                
                results = cursor.fetchall()
                
                # Format trend data
                trend_data = []
                total_revenue = 0
                total_orders = 0
                total_actual_revenue = 0
                
                for row in results:
                    (period_date, revenue, orders, unique_customers, avg_order_value,
                     pending_orders, confirmed_orders, preparing_orders, ready_orders, assigned_orders,
                     out_for_delivery_orders, delivered_orders, completed_orders, cancelled_orders,
                     actual_revenue) = row
                    
                    trend_data.append({
                        'period': period_date,
                        'revenue': float(revenue),
                        'orders': orders,
                        'unique_customers': unique_customers,
                        'avg_order_value': float(avg_order_value) if avg_order_value else 0,
                        'order_status_breakdown': {
                            'pending': pending_orders,
                            'confirmed': confirmed_orders,
                            'preparing': preparing_orders,
                            'ready': ready_orders,
                            'assigned': assigned_orders,
                            'out_for_delivery': out_for_delivery_orders,
                            'delivered': delivered_orders,
                            'completed': completed_orders,
                            'cancelled': cancelled_orders
                        },
                        'revenue_breakdown': {
                            'total_revenue': float(revenue),
                            'actual_revenue': float(actual_revenue)
                        }
                    })
                    
                    total_revenue += float(revenue)
                    total_orders += orders
                    total_actual_revenue += float(actual_revenue)
                
                # Get business-level details if requested
                business_details = []
                if include_business_details:
                    cursor.execute(f"""
                        SELECT 
                            b.business_id,
                            b.businessName,
                            b.businessCategory,
                            b.businessType,
                            COALESCE(SUM(o.final_amount), 0) as total_revenue,
                            COUNT(DISTINCT o.order_id) as total_orders,
                            COUNT(DISTINCT o.user_id) as unique_customers,
                            COALESCE(AVG(o.final_amount), 0) as avg_order_value,
                            COUNT(DISTINCT CASE WHEN o.status = 'pending' THEN o.order_id END) as pending_orders,
                            COUNT(DISTINCT CASE WHEN o.status = 'confirmed' THEN o.order_id END) as confirmed_orders,
                            COUNT(DISTINCT CASE WHEN o.status = 'preparing' THEN o.order_id END) as preparing_orders,
                            COUNT(DISTINCT CASE WHEN o.status = 'ready' THEN o.order_id END) as ready_orders,
                            COUNT(DISTINCT CASE WHEN o.status = 'assigned' THEN o.order_id END) as assigned_orders,
                            COUNT(DISTINCT CASE WHEN o.status = 'out_for_delivery' THEN o.order_id END) as out_for_delivery_orders,
                            COUNT(DISTINCT CASE WHEN o.status = 'delivered' THEN o.order_id END) as delivered_orders,
                            COUNT(DISTINCT CASE WHEN o.status = 'completed' THEN o.order_id END) as completed_orders,
                            COUNT(DISTINCT CASE WHEN o.status = 'cancelled' THEN o.order_id END) as cancelled_orders,
                            COALESCE(SUM(CASE WHEN o.status IN ('delivered', 'completed') THEN o.final_amount ELSE 0 END), 0) as actual_revenue
                        FROM businesses b
                        LEFT JOIN orders o ON b.business_id = o.business_id
                        WHERE (o.created_at >= DATE_SUB(CURDATE(), INTERVAL {days} DAY) OR o.created_at IS NULL)
                        GROUP BY b.business_id, b.businessName, b.businessCategory, b.businessType
                        HAVING total_orders > 0 OR total_revenue > 0
                        ORDER BY total_revenue DESC
                        LIMIT 20
                    """)
                    
                    business_results = cursor.fetchall()
                    
                    for row in business_results:
                        (business_id, business_name, business_category, business_type, total_revenue, total_orders,
                         unique_customers, avg_order_value, pending_orders, confirmed_orders, preparing_orders,
                         ready_orders, assigned_orders, out_for_delivery_orders, delivered_orders, completed_orders,
                         cancelled_orders, actual_revenue) = row
                        
                        business_details.append({
                            'business_id': business_id,
                            'business_name': business_name,
                            'business_category': business_category,
                            'business_type': business_type,
                            'total_revenue': float(total_revenue),
                            'actual_revenue': float(actual_revenue),
                            'total_orders': total_orders,
                            'unique_customers': unique_customers,
                            'avg_order_value': float(avg_order_value) if avg_order_value else 0,
                            'order_status_breakdown': {
                                'pending': pending_orders,
                                'confirmed': confirmed_orders,
                                'preparing': preparing_orders,
                                'ready': ready_orders,
                                'assigned': assigned_orders,
                                'out_for_delivery': out_for_delivery_orders,
                                'delivered': delivered_orders,
                                'completed': completed_orders,
                                'cancelled': cancelled_orders
                            }
                        })
                
                # Calculate growth metrics
                if len(trend_data) >= 2:
                    latest_revenue = trend_data[-1]['revenue_breakdown']['actual_revenue']
                    previous_revenue = trend_data[-2]['revenue_breakdown']['actual_revenue']
                    revenue_growth = ((latest_revenue - previous_revenue) / previous_revenue * 100) if previous_revenue > 0 else 0
                else:
                    revenue_growth = 0
                
                # Get comparison data (previous period)
                comparison_days = min(days, 30)
                cursor.execute(f"""
                    SELECT 
                        COALESCE(SUM(o.final_amount), 0) as revenue,
                        COUNT(DISTINCT o.order_id) as orders
                    FROM orders o
                    WHERE o.created_at >= DATE_SUB(DATE_SUB(CURDATE(), INTERVAL {days} DAY), INTERVAL {comparison_days} DAY)
                    AND o.created_at < DATE_SUB(CURDATE(), INTERVAL {days} DAY)
                """)
                
                comparison_data = cursor.fetchone()
                comparison_revenue, comparison_orders = comparison_data
                
                return Response({
                    'success': True,
                    'message': 'Comprehensive revenue trend data retrieved successfully',
                    'metadata': {
                        'period': period,
                        'days_analyzed': days,
                        'data_points': len(trend_data),
                        'total_revenue': total_revenue,
                        'total_actual_revenue': total_actual_revenue,
                        'total_orders': total_orders,
                        'revenue_growth_percent': round(revenue_growth, 2),
                        'comparison_period_revenue': float(comparison_revenue) if comparison_revenue else 0,
                        'comparison_period_orders': comparison_orders or 0,
                        'business_analytics_included': include_business_details,
                        'total_businesses_analyzed': len(business_details)
                    },
                    'data': trend_data,
                    'business_details': business_details if include_business_details else None
                }, status=status.HTTP_200_OK)
                
        except Exception as e:
            logger.error(f"Error retrieving comprehensive revenue trend: {str(e)}")
            return Response({
                'success': False,
                'message': f'Error retrieving revenue trend: {str(e)}',
                'data': None
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class CategoryMixView(APIView):
    """
    Category mix analytics for pie/donut charts
    GET /api/v1/admin/analytics/category-mix/
    Shows order distribution by business category
    """
    permission_classes = []
    
    def get(self, request):
        """Get category mix data"""
        try:
            # Get query parameters
            days = int(request.query_params.get('days', 30))
            metric = request.query_params.get('metric', 'orders')  # orders, revenue
            
            # Validate metric
            if metric not in ['orders', 'revenue']:
                return Response({
                    'success': False,
                    'message': 'Invalid metric. Use orders or revenue',
                    'data': None
                }, status=status.HTTP_400_BAD_REQUEST)
            
            # Limit days to reasonable range
            days = min(days, 365)
            
            with connection.cursor() as cursor:
                # Determine connection collation for safe JOINs
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
                
                # Query category mix data
                if metric == 'revenue':
                    cursor.execute(f"""
                        SELECT 
                            COALESCE(b.businessCategory, 'Uncategorized') as category,
                            COALESCE(SUM(o.final_amount), 0) as value,
                            COUNT(DISTINCT o.order_id) as orders,
                            COUNT(DISTINCT b.business_id) as business_count
                        FROM orders o
                        LEFT JOIN businesses b ON CONVERT(o.business_id USING {detected_charset}) COLLATE {detected_collation} = CONVERT(b.business_id USING {detected_charset}) COLLATE {detected_collation}
                        WHERE o.created_at >= DATE_SUB(CURDATE(), INTERVAL {days} DAY)
                        AND o.status NOT IN ('cancelled', 'grocery_cancelled')
                        GROUP BY b.businessCategory
                        ORDER BY value DESC
                    """)
                else:  # orders
                    cursor.execute(f"""
                        SELECT 
                            COALESCE(b.businessCategory, 'Uncategorized') as category,
                            COUNT(DISTINCT o.order_id) as value,
                            COALESCE(SUM(o.final_amount), 0) as revenue,
                            COUNT(DISTINCT b.business_id) as business_count
                        FROM orders o
                        LEFT JOIN businesses b ON CONVERT(o.business_id USING {detected_charset}) COLLATE {detected_collation} = CONVERT(b.business_id USING {detected_charset}) COLLATE {detected_collation}
                        WHERE o.created_at >= DATE_SUB(CURDATE(), INTERVAL {days} DAY)
                        AND o.status NOT IN ('cancelled', 'grocery_cancelled')
                        GROUP BY b.businessCategory
                        ORDER BY value DESC
                    """)
                
                results = cursor.fetchall()
                
                # Format data for charts
                category_data = []
                total_value = 0
                
                for row in results:
                    if metric == 'revenue':
                        category, value, orders, business_count = row
                    else:
                        category, value, revenue, business_count = row
                    
                    category_data.append({
                        'category': category or 'Uncategorized',
                        'value': float(value) if metric == 'revenue' else value,
                        'orders': orders if metric == 'revenue' else value,
                        'revenue': float(value) if metric == 'revenue' else float(revenue),
                        'business_count': business_count,
                        'percentage': 0  # Will be calculated below
                    })
                    
                    total_value += float(value) if metric == 'revenue' else value
                
                # Calculate percentages
                for item in category_data:
                    item['percentage'] = round((item['value'] / total_value * 100), 2) if total_value > 0 else 0
                
                # Sort by value descending
                category_data.sort(key=lambda x: x['value'], reverse=True)
                
                return Response({
                    'success': True,
                    'message': 'Category mix data retrieved successfully',
                    'metadata': {
                        'metric': metric,
                        'days_analyzed': days,
                        'total_categories': len(category_data),
                        'total_value': total_value,
                        'top_category': category_data[0]['category'] if category_data else None
                    },
                    'data': category_data
                }, status=status.HTTP_200_OK)
                
        except Exception as e:
            logger.error(f"Error retrieving category mix: {str(e)}")
            return Response({
                'success': False,
                'message': f'Error retrieving category mix: {str(e)}',
                'data': None
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class BusinessOffersAndCouponsView(APIView):
    """
    Get offers and coupons for a specific business
    GET /api/v1/admin/analytics/business-offers-coupons/
    Query params: business_id (required)
    """
    permission_classes = []
    
    def get(self, request):
        """Get offers and coupons for a business"""
        try:
            # Get business_id from query params
            business_id = request.query_params.get('business_id')
            
            if not business_id:
                return Response({
                    'success': False,
                    'message': 'business_id is required',
                    'data': None
                }, status=status.HTTP_400_BAD_REQUEST)
            
            # Verify business exists
            from kirazee_app.models import Business
            try:
                business = Business.objects.get(business_id=business_id)
            except Business.DoesNotExist:
                return Response({
                    'success': False,
                    'message': 'Business not found',
                    'data': None
                }, status=status.HTTP_404_NOT_FOUND)
            
            # Determine scope (include sub-branches if master)
            scope_ids = [business_id]
            if (business.level or '').strip().lower() in ['master', 'master level']:
                sub_branches = Business.objects.filter(master=business_id).values_list('business_id', flat=True)
                scope_ids.extend(list(sub_branches))
            
            with connection.cursor() as cursor:
                # Fetch promotional offers
                placeholders = ','.join(['%s'] * len(scope_ids))
                
                cursor.execute(
                    f"""
                    SELECT 
                        promo_id, business_id, offer_type, reference_id, title, description,
                        discount_percentage, discount_amount, original_price, offer_price,
                        valid_from, valid_to, is_active, is_approved, priority,
                        max_views, current_views, created_at, updated_at
                    FROM promotional_offers
                    WHERE business_id IN ({placeholders})
                    ORDER BY created_at DESC
                    """,
                    scope_ids
                )
                
                offers = []
                for row in cursor.fetchall():
                    offers.append({
                        'promo_id': row[0],
                        'business_id': row[1],
                        'offer_type': row[2],
                        'reference_id': row[3],
                        'title': row[4],
                        'description': row[5],
                        'discount_percentage': float(row[6]) if row[6] is not None else None,
                        'discount_amount': float(row[7]) if row[7] is not None else None,
                        'original_price': float(row[8]) if row[8] is not None else None,
                        'offer_price': float(row[9]) if row[9] is not None else None,
                        'valid_from': row[10].isoformat() if row[10] else None,
                        'valid_to': row[11].isoformat() if row[11] else None,
                        'is_active': bool(row[12]),
                        'is_approved': bool(row[13]),
                        'priority': row[14],
                        'max_views': row[15],
                        'current_views': row[16],
                        'created_at': row[17].isoformat() if row[17] else None,
                        'updated_at': row[18].isoformat() if row[18] else None,
                        'status': 'active' if row[12] and row[13] else 'inactive'
                    })
                
                # Fetch coupons from consumer_coupons table
                from consumer.models import Coupons
                
                coupons_qs = Coupons.objects.filter(
                    business_id__in=scope_ids
                ).order_by('-created_at')
                
                coupons = []
                for coupon in coupons_qs:
                    # Get redemption count
                    from consumer.models import CouponRedemptions
                    redemption_count = CouponRedemptions.objects.filter(
                        coupon_id=coupon.coupon_id
                    ).count()
                    
                    coupons.append({
                        'coupon_id': coupon.coupon_id,
                        'business_id': coupon.business_id_id if hasattr(coupon, 'business_id_id') else coupon.business_id,
                        'coupon_code': coupon.coupon_code,
                        'coupon_name': coupon.name,
                        'description': coupon.description,
                        'discount_type': coupon.discount_type,
                        'discount_value': float(coupon.discount_value) if coupon.discount_value else None,
                        'valid_from': coupon.valid_from.isoformat() if coupon.valid_from else None,
                        'valid_to': coupon.valid_to.isoformat() if coupon.valid_to else None,
                        'usage_limit_per_user': coupon.max_redemptions_per_user if hasattr(coupon, 'max_redemptions_per_user') else 1,
                        'total_usage_limit': coupon.max_total_redemptions if hasattr(coupon, 'max_total_redemptions') else None,
                        'current_usage_count': redemption_count,
                        'is_active': coupon.is_active,
                        'created_by': coupon.created_by,
                        'created_at': coupon.created_at.isoformat() if coupon.created_at else None,
                        'updated_at': coupon.updated_at.isoformat() if coupon.updated_at else None,
                        'status': 'active' if coupon.is_active else 'inactive'
                    })
                
                # Calculate statistics
                active_offers = sum(1 for o in offers if o['is_active'] and o['is_approved'])
                active_coupons = sum(1 for c in coupons if c['is_active'])
                total_coupon_redemptions = sum(c['current_usage_count'] for c in coupons)
                
                return Response({
                    'success': True,
                    'message': 'Offers and coupons retrieved successfully',
                    'metadata': {
                        'business_id': business_id,
                        'business_name': business.businessName,
                        'scope_business_ids': scope_ids,
                        'total_offers': len(offers),
                        'active_offers': active_offers,
                        'total_coupons': len(coupons),
                        'active_coupons': active_coupons,
                        'total_coupon_redemptions': total_coupon_redemptions
                    },
                    'data': {
                        'offers': offers,
                        'coupons': coupons
                    }
                }, status=status.HTTP_200_OK)
                
        except Exception as e:
            logger.error(f"Error retrieving offers and coupons: {str(e)}")
            return Response({
                'success': False,
                'message': f'Error retrieving offers and coupons: {str(e)}',
                'data': None
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)



class BusinessPerformanceMetricsView(APIView):
    """
    Get comprehensive performance metrics for a specific business
    GET /api/v1/admin/analytics/business-performance/{business_id}/
    Query params: days (default: 30)
    """
    permission_classes = []
    
    def get(self, request, business_id):
        """Get performance metrics for a business"""
        try:
            days = int(request.query_params.get('days', 30))
            days = min(days, 365)  # Limit to 1 year
            
            with connection.cursor() as cursor:
                # 1. FINANCIAL PERFORMANCE
                cursor.execute("""
                    SELECT 
                        COALESCE(SUM(total_amount), 0) as gmv,
                        COALESCE(AVG(final_amount), 0) as aov,
                        COUNT(*) as total_orders,
                        COALESCE(SUM(CASE WHEN status IN ('delivered', 'completed') THEN final_amount ELSE 0 END), 0) as actual_revenue
                    FROM orders
                    WHERE business_id = %s
                    AND created_at >= DATE_SUB(NOW(), INTERVAL %s DAY)
                    AND status NOT IN ('cancelled')
                """, [business_id, days])
                
                financial = cursor.fetchone()
                gmv, aov, total_orders, actual_revenue = financial
                
                # 2. OPERATIONAL EFFICIENCY
                cursor.execute("""
                    SELECT 
                        COUNT(*) as total_orders,
                        COUNT(CASE WHEN status NOT IN ('cancelled') THEN 1 END) as accepted_orders,
                        COUNT(CASE WHEN status = 'cancelled' THEN 1 END) as cancelled_orders,
                        (COUNT(CASE WHEN status NOT IN ('cancelled') THEN 1 END) * 100.0 / COUNT(*)) as fulfillment_rate,
                        (COUNT(CASE WHEN status = 'cancelled' THEN 1 END) * 100.0 / COUNT(*)) as cancellation_rate
                    FROM orders
                    WHERE business_id = %s
                    AND created_at >= DATE_SUB(NOW(), INTERVAL %s DAY)
                """, [business_id, days])
                
                operational = cursor.fetchone()
                op_total, op_accepted, op_cancelled, fulfillment_rate, cancellation_rate = operational
                
                # 3. CUSTOMER & QUALITY METRICS
                cursor.execute("""
                    SELECT 
                        COALESCE(AVG(rating), 0) as avg_rating,
                        COUNT(*) as total_ratings,
                        COUNT(CASE WHEN rating = 5 THEN 1 END) as rating_5,
                        COUNT(CASE WHEN rating = 4 THEN 1 END) as rating_4,
                        COUNT(CASE WHEN rating = 3 THEN 1 END) as rating_3,
                        COUNT(CASE WHEN rating = 2 THEN 1 END) as rating_2,
                        COUNT(CASE WHEN rating = 1 THEN 1 END) as rating_1
                    FROM rating
                    WHERE business_id = %s
                    AND created_at >= DATE_SUB(NOW(), INTERVAL %s DAY)
                """, [business_id, days])
                
                quality = cursor.fetchone()
                avg_rating, total_ratings, r5, r4, r3, r2, r1 = quality
                
                # 4. REPEAT CUSTOMER RATE
                cursor.execute("""
                    WITH customer_orders AS (
                        SELECT 
                            user_id,
                            COUNT(*) as order_count
                        FROM orders
                        WHERE business_id = %s
                        AND created_at >= DATE_SUB(NOW(), INTERVAL %s DAY)
                        AND status IN ('delivered', 'completed')
                        GROUP BY user_id
                    )
                    SELECT 
                        COUNT(*) as total_customers,
                        COUNT(CASE WHEN order_count > 1 THEN 1 END) as repeat_customers,
                        (COUNT(CASE WHEN order_count > 1 THEN 1 END) * 100.0 / COUNT(*)) as repeat_rate
                    FROM customer_orders
                """, [business_id, days])
                
                repeat = cursor.fetchone()
                total_customers, repeat_customers, repeat_rate = repeat
                
                # 5. TREND DATA (Last 7 days for histogram)
                cursor.execute("""
                    SELECT 
                        DATE(created_at) as date,
                        COALESCE(SUM(final_amount), 0) as revenue,
                        COUNT(*) as orders
                    FROM orders
                    WHERE business_id = %s
                    AND created_at >= DATE_SUB(NOW(), INTERVAL 7 DAY)
                    AND status NOT IN ('cancelled')
                    GROUP BY DATE(created_at)
                    ORDER BY date ASC
                """, [business_id])
                
                trend_data = cursor.fetchall()
                
                # Format response
                return Response({
                    'success': True,
                    'business_id': business_id,
                    'period_days': days,
                    'data': {
                        'financial': {
                            'gmv': float(gmv) if gmv else 0,
                            'aov': float(aov) if aov else 0,
                            'actual_revenue': float(actual_revenue) if actual_revenue else 0,
                            'total_orders': total_orders or 0
                        },
                        'operational': {
                            'fulfillment_rate': float(fulfillment_rate) if fulfillment_rate else 0,
                            'cancellation_rate': float(cancellation_rate) if cancellation_rate else 0,
                            'total_orders': op_total or 0,
                            'accepted_orders': op_accepted or 0,
                            'cancelled_orders': op_cancelled or 0
                        },
                        'quality': {
                            'average_rating': float(avg_rating) if avg_rating else 0,
                            'total_ratings': total_ratings or 0,
                            'rating_distribution': {
                                '5': r5 or 0,
                                '4': r4 or 0,
                                '3': r3 or 0,
                                '2': r2 or 0,
                                '1': r1 or 0
                            }
                        },
                        'customers': {
                            'total_customers': total_customers or 0,
                            'repeat_customers': repeat_customers or 0,
                            'repeat_rate': float(repeat_rate) if repeat_rate else 0
                        },
                        'trends': {
                            'daily_revenue': [
                                {
                                    'date': str(row[0]),
                                    'revenue': float(row[1]) if row[1] else 0,
                                    'orders': row[2] or 0
                                }
                                for row in trend_data
                            ]
                        }
                    }
                }, status=status.HTTP_200_OK)
                
        except Exception as e:
            logger.error(f"Error retrieving business performance metrics: {str(e)}")
            return Response({
                'success': False,
                'message': f'Error retrieving performance metrics: {str(e)}',
                'data': None
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class BestSellingItemsView(APIView):
    """
    Get best-selling items for a specific business
    GET /api/v1/admin/analytics/best-selling-items/{business_id}/
    Query params: 
    - days (default: 30) - Time period to analyze
    - limit (default: 10) - Number of top items to return
    """
    permission_classes = []
    
    def get(self, request, business_id):
        """Get best-selling items for a business"""
        try:
            days = int(request.query_params.get('days', 30))
            limit = int(request.query_params.get('limit', 10))
            
            # Limit constraints
            days = min(days, 365)
            limit = min(limit, 50)
            
            # Calculate date threshold
            from datetime import timedelta
            date_threshold = timezone.now() - timedelta(days=days)
            
            # Use Django ORM - get all orders for this business first
            from consumer.models import OrderItems, Orders
            
            # Get all order IDs for this business in the time period
            business_orders = Orders.objects.filter(
                business_id=business_id,
                created_at__gte=date_threshold
            ).exclude(
                status='cancelled'
            ).values_list('order_id', flat=True)
            
            # Now get items from those orders
            items_data = OrderItems.objects.filter(
                order_id__in=business_orders
            ).values(
                'item_name_snapshot'
            ).annotate(
                order_count=Count('order_id', distinct=True),
                total_quantity_sold=Sum('quantity'),
                total_revenue=Sum('total_price'),
                avg_price=Avg('unit_price_snapshot')
            ).order_by('-total_quantity_sold')[:limit]
            
            items = []
            for item in items_data:
                items.append({
                    'item_name': item['item_name_snapshot'],
                    'order_count': item['order_count'],
                    'total_quantity_sold': item['total_quantity_sold'],
                    'total_revenue': float(item['total_revenue']) if item['total_revenue'] else 0,
                    'avg_price': float(item['avg_price']) if item['avg_price'] else 0
                })
            
            return Response({
                'success': True,
                'business_id': business_id,
                'period_days': days,
                'data': {
                    'items': items,
                    'total_items': len(items)
                }
            }, status=status.HTTP_200_OK)
                
        except Exception as e:
            logger.error(f"Error retrieving best-selling items: {str(e)}")
            return Response({
                'success': False,
                'message': f'Error retrieving best-selling items: {str(e)}',
                'data': None
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class FrequentUsersView(APIView):
    """
    Get frequent users for a specific business
    GET /api/v1/admin/analytics/frequent-users/{business_id}/
    Query params: 
    - days (default: 90) - Time period to analyze
    - limit (default: 10) - Number of top users to return
    """
    permission_classes = []
    
    def get(self, request, business_id):
        """Get frequent users for a business"""
        try:
            days = int(request.query_params.get('days', 90))
            limit = int(request.query_params.get('limit', 10))
            
            # Limit constraints
            days = min(days, 365)
            limit = min(limit, 50)
            
            # Calculate date threshold
            from datetime import timedelta
            date_threshold = timezone.now() - timedelta(days=days)
            
            # Use Django ORM to get frequent users
            from consumer.models import Orders
            from kirazee_app.models import Registration
            
            # Get user order statistics
            user_stats = Orders.objects.filter(
                business_id=business_id,
                created_at__gte=date_threshold,
                user_id__isnull=False
            ).exclude(
                status='cancelled'
            ).values(
                'user_id'
            ).annotate(
                order_count=Count('order_id'),
                total_spent=Sum('final_amount'),
                avg_order_value=Avg('final_amount'),
                last_order_date=Max('created_at')
            ).order_by('-order_count')[:limit]
            
            # Get user details
            users = []
            for stat in user_stats:
                try:
                    user = Registration.objects.get(user_id=stat['user_id'])
                    users.append({
                        'user_id': user.user_id,
                        'name': f"{user.firstName} {user.lastName}",
                        'phone': user.mobileNumber,
                        'email': user.emailID,
                        'profile_url': user.profileUrl,
                        'order_count': stat['order_count'],
                        'total_spent': float(stat['total_spent']) if stat['total_spent'] else 0,
                        'avg_order_value': float(stat['avg_order_value']) if stat['avg_order_value'] else 0,
                        'last_order_date': stat['last_order_date'].isoformat() if stat['last_order_date'] else None
                    })
                except Registration.DoesNotExist:
                    continue
            
            return Response({
                'success': True,
                'business_id': business_id,
                'period_days': days,
                'data': {
                    'users': users,
                    'total_users': len(users)
                }
            }, status=status.HTTP_200_OK)
                
        except Exception as e:
            logger.error(f"Error retrieving frequent users: {str(e)}")
            return Response({
                'success': False,
                'message': f'Error retrieving frequent users: {str(e)}',
                'data': None
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
