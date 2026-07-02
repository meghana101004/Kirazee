from datetime import datetime, timedelta, date
from collections import defaultdict
from decimal import Decimal

from django.conf import settings
from django.core.cache import cache
from django.db.models import Sum, Count, F, Value, DecimalField, IntegerField
from django.db.models.functions import TruncDate, Coalesce
from rest_framework.decorators import api_view
from rest_framework.response import Response
from drf_yasg.utils import swagger_auto_schema
from rest_framework import status

from kirazee_app.models import Business, BusinessMapping, Registration
from consumer.models import Orders, OrderItems
from business.models import BusinessCounterOrders, MenuItems, productItems
from management.models import Inventory, Expenses


CACHE_TTL_SHORT = 60
CACHE_TTL_VERY_SHORT = 30


def calculate_business_health_for_business(business_ids, revenue, expenses, month_str):
    """
    Calculate business health status for individual business dashboard
    Returns health status and metrics objects
    """
    try:
        from django.db.models import Count
        from dateutil.relativedelta import relativedelta
        
        profit = revenue - expenses
        profit_margin = (profit / revenue * 100) if revenue > 0 else 0
        
        # Calculate current month start and end
        y, m = month_str.split('-')
        y, m = int(y), int(m)
        start = datetime(y, m, 1)
        if m == 12:
            end = datetime(y + 1, 1, 1)
        else:
            end = datetime(y, m + 1, 1)
        
        # Calculate trends by comparing with previous month
        try:
            current_date = start
            previous_month = current_date - relativedelta(months=1)
            
            # Get previous month's data
            prev_start = datetime(previous_month.year, previous_month.month, 1)
            prev_end = current_date
            
            prev_online = Orders.objects.filter(
                business_id__in=business_ids, 
                created_at__gte=prev_start, 
                created_at__lt=prev_end
            ).aggregate(
                total=Coalesce(
                    Sum('final_amount'),
                    Value(Decimal('0.00'), output_field=DecimalField(max_digits=12, decimal_places=2))
                )
            )['total']
            
            prev_pos = BusinessCounterOrders.objects.filter(
                business_id__in=business_ids,
                created_at__gte=prev_start, 
                created_at__lt=prev_end
            ).aggregate(
                total=Coalesce(
                    Sum('total_amount'),
                    Value(Decimal('0.00'), output_field=DecimalField(max_digits=12, decimal_places=2))
                )
            )['total']
            
            prev_expenses = Expenses.objects.filter(
                business_id__in=business_ids,
                expense_date__gte=prev_start.date(),
                expense_date__lt=prev_end.date()
            ).aggregate(
                total=Coalesce(
                    Sum('amount'),
                    Value(Decimal('0.00'), output_field=DecimalField(max_digits=12, decimal_places=2))
                )
            )['total']
            
            prev_revenue = Decimal(prev_online) + Decimal(prev_pos)
            prev_profit = prev_revenue - Decimal(prev_expenses)
            
            # Calculate trends
            revenue_trend = "0%"
            expense_trend = "0%"  
            profit_trend = "0%"
            
            if prev_revenue > 0:
                revenue_trend = f"{((revenue - prev_revenue) / prev_revenue * 100):+.1f}%"
            if prev_expenses > 0:
                expense_trend = f"{((expenses - prev_expenses) / prev_expenses * 100):+.1f}%"
            if prev_profit != 0:
                profit_trend = f"{((profit - prev_profit) / abs(prev_profit) * 100):+.1f}%"
                
        except Exception:
            revenue_trend = "0%"
            expense_trend = "0%"  
            profit_trend = "0%"
        
        # Get order counts for scoring
        total_orders = Orders.objects.filter(
            business_id__in=business_ids, 
            created_at__gte=start, 
            created_at__lt=end
        ).count()
        
        total_orders += BusinessCounterOrders.objects.filter(
            business_id__in=business_ids,
            created_at__gte=start, 
            created_at__lt=end
        ).count()
        
        # Calculate health score (0-100)
        health_score = 0
        status = "needs_attention"
        recommendations = []
        
        # Revenue-based scoring
        if revenue > 10000:  # Good revenue
            health_score += 30
        elif revenue > 5000:  # Moderate revenue
            health_score += 20
        elif revenue > 1000:  # Low revenue
            health_score += 10
            
        # Profit margin scoring
        if profit_margin > 30:  # Excellent margin
            health_score += 40
            status = "optimized"
        elif profit_margin > 20:  # Good margin
            health_score += 30
            status = "healthy"
        elif profit_margin > 10:  # Acceptable margin
            health_score += 20
        elif profit_margin > 0:  # Low margin
            health_score += 10
        else:  # Loss
            health_score -= 20
            status = "critical"
            
        # Order volume scoring
        if total_orders > 100:
            health_score += 20
        elif total_orders > 50:
            health_score += 15
        elif total_orders > 20:
            health_score += 10
        elif total_orders > 0:
            health_score += 5
            
        # Cap score at 100
        health_score = min(100, max(0, health_score))
        
        # Generate recommendations
        if profit_margin <= 0:
            recommendations.append("Business is operating at loss. Review pricing and costs immediately.")
        elif profit_margin < 10:
            recommendations.append("Profit margin is very low. Consider cost optimization strategies.")
        elif profit_margin < 20:
            recommendations.append("Profit margin needs improvement. Focus on operational efficiency.")
            
        if revenue < 1000:
            recommendations.append("Revenue is very low. Implement marketing and sales strategies.")
        elif revenue < 5000:
            recommendations.append("Consider expanding product offerings or customer base.")
            
        if total_orders < 20:
            recommendations.append("Order volume is low. Analyze customer acquisition channels.")
            
        # Determine final status
        if health_score >= 80:
            status = "optimized"
        elif health_score >= 60:
            status = "healthy"
        elif health_score >= 40:
            status = "needs_attention"
        else:
            status = "critical"
            
        health_status = {
            'status': status,
            'score': round(health_score, 1),
            'profit_margin': round(profit_margin, 1),
            'recommendations': recommendations
        }
        
        metrics = {
            'revenue_trend': revenue_trend,
            'expense_trend': expense_trend,
            'profit_trend': profit_trend
        }
        
        return health_status, metrics
        
    except Exception as e:
        print(f"Error calculating business health: {str(e)}")
        return {
            'status': 'error',
            'score': 0,
            'profit_margin': 0,
            'recommendations': ['Unable to calculate health metrics']
        }, {
            'revenue_trend': '0%',
            'expense_trend': '0%',
            'profit_trend': '0%'
        }


def _now():
    if getattr(settings, 'USE_TZ', False):
        from django.utils import timezone
        return timezone.now()
    return datetime.now()


def _today_range_local():
    now = _now()
    start = datetime(now.year, now.month, now.day)
    end = start + timedelta(days=1)
    return start, end


def _get_dashboard_business_ids(business: Business):
    """
    Get all business IDs relevant for the dashboard.
    If the provided business is a master business, include all its sub-businesses.
    """
    ids = [business.business_id]
    # If this is a master business (master is None or empty), fetch all its sub-businesses
    if not business.master:
        sub_ids = Business.objects.filter(master=business.business_id).values_list('business_id', flat=True)
        ids.extend(list(sub_ids))
    return ids


def _month_range_local(month_str):
    try:
        y, m = month_str.split('-')
        y, m = int(y), int(m)
        start = datetime(y, m, 1)
        if m == 12:
            end = datetime(y + 1, 1, 1)
        else:
            end = datetime(y, m + 1, 1)
        return start, end
    except Exception:
        now = _now()
        start = datetime(now.year, now.month, 1)
        if now.month == 12:
            end = datetime(now.year + 1, 1, 1)
        else:
            end = datetime(now.year, now.month + 1, 1)
        return start, end


def _ensure_owner(request, business: Business):
    user_id = request.query_params.get('userID')
    if not user_id:
        return False
    try:
        return BusinessMapping.objects.filter(user__user_id=user_id, business=business, status=True).exists()
    except Exception:
        return False


@swagger_auto_schema(methods=['GET'], tags=['Business'])
@api_view(['GET'])
def dashboard_today_snapshot(request, business_id: str):
    try:
        business = Business.objects.get(business_id=business_id)
    except Business.DoesNotExist:
        return Response({"error": "Business not found"}, status=status.HTTP_404_NOT_FOUND)

    if not _ensure_owner(request, business):
        return Response({"error": "Forbidden"}, status=status.HTTP_403_FORBIDDEN)

    cache_key = f"dash:today:{business_id}"
    cached = cache.get(cache_key)
    if cached:
        return Response(cached)

    start, end = _today_range_local()
    business_ids = _get_dashboard_business_ids(business)

    online_qs = Orders.objects.filter(business_id__in=business_ids, created_at__gte=start, created_at__lt=end)
    pos_qs = BusinessCounterOrders.objects.filter(business_id__in=business_ids, created_at__gte=start, created_at__lt=end)

    online_sales = online_qs.aggregate(
        total=Coalesce(
            Sum('final_amount'),
            Value(Decimal('0.00'), output_field=DecimalField(max_digits=12, decimal_places=2))
        ),
        cnt=Count('order_id')
    )
    pos_sales = pos_qs.aggregate(
        total=Coalesce(
            Sum('total_amount'),
            Value(Decimal('0.00'), output_field=DecimalField(max_digits=12, decimal_places=2))
        ),
        cnt=Count('order_id')
    )

    pending_online = online_qs.filter(status=Orders.OrderStatus.PENDING).count()
    pending_pos = pos_qs.filter(status='pending').count()

    total_sales = Decimal(online_sales['total']) + Decimal(pos_sales['total'])
    payload = {
        'date': start.date().isoformat(),
        'total_sales': float(total_sales),
        'total_orders': int(online_sales['cnt']) + int(pos_sales['cnt']),
        'online_orders': int(online_sales['cnt']),
        'counter_orders': int(pos_sales['cnt']),
        'pending_orders': int(pending_online) + int(pending_pos),
        'last_updated': _now().isoformat(),
    }

    cache.set(cache_key, payload, CACHE_TTL_VERY_SHORT)
    return Response(payload)


@swagger_auto_schema(methods=['GET'], tags=['Business'])
@api_view(['GET'])
def dashboard_daily_sales(request, business_id: str):
    try:
        business = Business.objects.get(business_id=business_id)
    except Business.DoesNotExist:
        return Response({"error": "Business not found"}, status=status.HTTP_404_NOT_FOUND)

    if not _ensure_owner(request, business):
        return Response({"error": "Forbidden"}, status=status.HTTP_403_FORBIDDEN)

    try:
        days = int(request.query_params.get('days', '7'))
    except Exception:
        days = 7
    days = 7 if days not in (7, 30) else days

    cache_key = f"dash:daily:{business_id}:{days}"
    cached = cache.get(cache_key)
    if cached:
        return Response(cached)

    end = _now()
    start = end - timedelta(days=days - 1)
    start_day = datetime(start.year, start.month, start.day)
    end_day = datetime(end.year, end.month, end.day) + timedelta(days=1)

    business_ids = _get_dashboard_business_ids(business)

    online = (
        Orders.objects
        .filter(business_id__in=business_ids, created_at__gte=start_day, created_at__lt=end_day)
        .annotate(day=TruncDate('created_at'))
        .values('day')
        .annotate(
            total_sales=Coalesce(
                Sum('final_amount'),
                Value(Decimal('0.00'), output_field=DecimalField(max_digits=12, decimal_places=2))
            ),
            orders_count=Count('order_id')
        )
    )
    pos = (
        BusinessCounterOrders.objects
        .filter(business_id__in=business_ids, created_at__gte=start_day, created_at__lt=end_day)
        .annotate(day=TruncDate('created_at'))
        .values('day')
        .annotate(
            total_sales=Coalesce(
                Sum('total_amount'),
                Value(Decimal('0.00'), output_field=DecimalField(max_digits=12, decimal_places=2))
            ),
            orders_count=Count('order_id')
        )
    )

    by_day = defaultdict(lambda: {'total_sales': Decimal('0.00'), 'orders_count': 0})
    for r in online:
        d = r['day'].isoformat()
        by_day[d]['total_sales'] += Decimal(r['total_sales'])
        by_day[d]['orders_count'] += int(r['orders_count'])
    for r in pos:
        d = r['day'].isoformat()
        by_day[d]['total_sales'] += Decimal(r['total_sales'])
        by_day[d]['orders_count'] += int(r['orders_count'])

    result = []
    cursor = start_day
    for i in range(days):
        d = (cursor + timedelta(days=i)).date().isoformat()
        entry = by_day[d]
        result.append({
            'date': d,
            'sales': float(entry['total_sales']),
        })

    payload = {
        'range': days,
        'data': result,
    }

    cache.set(cache_key, payload, CACHE_TTL_SHORT)
    return Response(payload)


@swagger_auto_schema(methods=['GET'], tags=['Business'])
@api_view(['GET'])
def dashboard_inventory_alerts(request, business_id: str):
    try:
        business = Business.objects.get(business_id=business_id)
    except Business.DoesNotExist:
        return Response({"error": "Business not found"}, status=status.HTTP_404_NOT_FOUND)

    if not _ensure_owner(request, business):
        return Response({"error": "Forbidden"}, status=status.HTTP_403_FORBIDDEN)

    threshold = 5
    business_ids = _get_dashboard_business_ids(business)
    items = Inventory.objects.filter(business_id__in=business_ids)

    low_stock = []
    out_of_stock = []

    for it in items.values('reference_id', 'item_name', 'current_stock'):
        stock = int(it.get('current_stock') or 0)
        row = {
            'product_id': it['reference_id'],
            'name': it['item_name'],
            'stock_qty': stock,
            'reorder_level': None,
        }
        if stock <= 0:
            out_of_stock.append(row)
        elif stock <= threshold:
            low_stock.append(row)
    inventory_payload = {
        'low_stock': len(low_stock),
        'out_of_stock': len(out_of_stock),
        'low_stock_items': low_stock,
        'out_of_stock_items': out_of_stock,
    }

    alerts_summary = []

    if inventory_payload['out_of_stock'] > 0:
        alerts_summary.append({
            'level': 'critical',
            'code': 'inventory_out_of_stock',
            'message': f"{inventory_payload['out_of_stock']} items out of stock",
        })

    if inventory_payload['low_stock'] > 0:
        alerts_summary.append({
            'level': 'warning',
            'code': 'inventory_low_stock',
            'message': f"{inventory_payload['low_stock']} items low on stock",
        })

    # Orders overview (today)
    orders_data = None
    try:
        start, end = _today_range_local()
        business_ids = _get_dashboard_business_ids(business)
        online_qs = Orders.objects.filter(business_id__in=business_ids, created_at__gte=start, created_at__lt=end)
        pos_qs = BusinessCounterOrders.objects.filter(business_id__in=business_ids, created_at__gte=start, created_at__lt=end)

        pending_online = online_qs.filter(status=Orders.OrderStatus.PENDING).count()
        pending_pos = pos_qs.filter(status='pending').count()

        orders_data = {
            'date': start.date().isoformat(),
            'pending_orders': int(pending_online) + int(pending_pos),
        }

        if orders_data['pending_orders'] > 0:
            alerts_summary.append({
                'level': 'warning',
                'code': 'orders_pending',
                'message': f"{orders_data['pending_orders']} pending orders",
            })
    except Exception:
        orders_data = None

    # Finance overview (current or requested month)
    finance_data = None
    try:
        month_str = request.query_params.get('month')
        start, end = _month_range_local(month_str) if month_str else _month_range_local(_now().strftime('%Y-%m'))
        business_ids = _get_dashboard_business_ids(business)

        online = Orders.objects.filter(business_id__in=business_ids, created_at__gte=start, created_at__lt=end)
        pos = BusinessCounterOrders.objects.filter(business_id__in=business_ids, created_at__gte=start, created_at__lt=end)

        online_total = online.aggregate(
            total=Coalesce(
                Sum('final_amount'),
                Value(Decimal('0.00'), output_field=DecimalField(max_digits=12, decimal_places=2))
            )
        )['total']
        pos_total = pos.aggregate(
            total=Coalesce(
                Sum('total_amount'),
                Value(Decimal('0.00'), output_field=DecimalField(max_digits=12, decimal_places=2))
            )
        )['total']

        expenses_total = Expenses.objects.filter(
            business_id__in=business_ids,
            expense_date__gte=start.date(),
            expense_date__lt=end.date()
        ).aggregate(
            total=Coalesce(
                Sum('amount'),
                Value(Decimal('0.00'), output_field=DecimalField(max_digits=12, decimal_places=2))
            )
        )['total']

        revenue = Decimal(online_total) + Decimal(pos_total)
        expenses_amt = Decimal(expenses_total)
        profit = revenue - expenses_amt

        finance_data = {
            'month': start.strftime('%Y-%m'),
            'revenue': float(revenue),
            'expenses': float(expenses_amt),
            'profit': float(profit),
        }

        if profit < Decimal('0'):
            alerts_summary.append({
                'level': 'critical',
                'code': 'business_in_loss',
                'message': 'Business is currently in loss for the selected period',
            })
        elif revenue > 0:
            margin = profit / revenue
            if margin < Decimal('0.10'):
                alerts_summary.append({
                    'level': 'warning',
                    'code': 'low_profit_margin',
                    'message': 'Low profit margin for the selected period',
                })
    except Exception:
        finance_data = None

    return Response({
        **inventory_payload,
        'orders_overview': orders_data,
        'finance_overview': finance_data,
        'alerts_summary': alerts_summary,
    })


@swagger_auto_schema(methods=['GET'], tags=['Business'])
@api_view(['GET'])
def dashboard_recent_orders(request, business_id: str):
    try:
        business = Business.objects.get(business_id=business_id)
    except Business.DoesNotExist:
        return Response({"error": "Business not found"}, status=status.HTTP_404_NOT_FOUND)

    if not _ensure_owner(request, business):
        return Response({"error": "Forbidden"}, status=status.HTTP_403_FORBIDDEN)

    try:
        limit = int(request.query_params.get('limit', '10'))
    except Exception:
        limit = 10
    limit = max(1, min(limit, 50))

    business_ids = _get_dashboard_business_ids(business)

    on = list(
        Orders.objects.filter(business_id__in=business_ids)
        .order_by('-created_at')
        .select_related('user_id')
        .values('order_number', 'final_amount', 'created_at', 'user_id__firstName', 'user_id__lastName', 'user_id__emailID')[:limit]
    )

    pos = list(
        BusinessCounterOrders.objects.filter(business_id__in=business_ids)
        .order_by('-created_at')
        .values('token_number', 'customer_email', 'total_amount', 'created_at', 'service_mode')[:limit]
    )

    merged = []
    for r in on:
        name = ((r.get('user_id__firstName') or '') + ' ' + (r.get('user_id__lastName') or '')).strip()
        if not name:
            name = r.get('user_id__emailID') or 'Guest'
        merged.append({
            'order_number': str(r['order_number']),
            'customer_name': name,
            'total_amount': str(r['final_amount'] or Decimal('0.00')),
            'created_at': r['created_at'].isoformat() if r['created_at'] else None,
            'channel': 'online',
        })

    for r in pos:
        merged.append({
            'order_number': r.get('token_number') or '',
            'customer_name': r.get('customer_email') if r.get('customer_email') else r.get('service_mode'),
            'total_amount': str(r['total_amount'] or Decimal('0.00')),
            'created_at': r['created_at'].isoformat() if r['created_at'] else None,
            'channel': 'counter',
        })

    merged.sort(key=lambda x: x.get('created_at') or '', reverse=True)
    merged = merged[:limit]

    recent = [
        {
            'name': m.get('customer_name') or 'Customer',
            'time': m.get('created_at'),
            'source': m.get('channel') or 'unknown',
        }
        for m in merged
    ]

    return Response({'recent_orders': recent})


@swagger_auto_schema(methods=['GET'], tags=['Business'])
@api_view(['GET'])
def dashboard_health(request, business_id: str):
    try:
        business = Business.objects.get(business_id=business_id)
    except Business.DoesNotExist:
        return Response({"error": "Business not found"}, status=status.HTTP_404_NOT_FOUND)

    if not _ensure_owner(request, business):
        return Response({"error": "Forbidden"}, status=status.HTTP_403_FORBIDDEN)

    month_str = request.query_params.get('month')
    start, end = _month_range_local(month_str) if month_str else _month_range_local(_now().strftime('%Y-%m'))

    business_ids = _get_dashboard_business_ids(business)

    online = Orders.objects.filter(business_id__in=business_ids, created_at__gte=start, created_at__lt=end)
    pos = BusinessCounterOrders.objects.filter(business_id__in=business_ids, created_at__gte=start, created_at__lt=end)

    online_total = online.aggregate(
        total=Coalesce(
            Sum('final_amount'),
            Value(Decimal('0.00'), output_field=DecimalField(max_digits=12, decimal_places=2))
        )
    )['total']
    pos_total = pos.aggregate(
        total=Coalesce(
            Sum('total_amount'),
            Value(Decimal('0.00'), output_field=DecimalField(max_digits=12, decimal_places=2))
        )
    )['total']

    expenses_total = Expenses.objects.filter(
        business_id__in=business_ids,
        expense_date__gte=start.date(),
        expense_date__lt=end.date()
    ).aggregate(
        total=Coalesce(
            Sum('amount'),
            Value(Decimal('0.00'), output_field=DecimalField(max_digits=12, decimal_places=2))
        )
    )['total']

    revenue = Decimal(online_total) + Decimal(pos_total)
    expenses_amt = Decimal(expenses_total)
    profit = revenue - expenses_amt

    items = (
        OrderItems.objects
        .filter(order_id__business_id__in=business_ids, order_id__created_at__gte=start, order_id__created_at__lt=end)
        .values('item_name_snapshot')
        .annotate(
            qty=Coalesce(Sum('quantity'), Value(0, output_field=IntegerField())),
            revenue=Coalesce(
                Sum('total_price'),
                Value(Decimal('0.00'), output_field=DecimalField(max_digits=12, decimal_places=2))
            )
        )
        .order_by('-qty')
    )
    best_selling_products = [
        {
            'name': r['item_name_snapshot'],
            'qty_sold': int(r['qty']),
            'revenue': str(Decimal(r['revenue'])),
        }
        for r in list(items)[:5]
    ]

    cat_map = defaultdict(lambda: {'qty': 0, 'revenue': Decimal('0.00')})
    raw_items = (
        OrderItems.objects
        .filter(order_id__business_id__in=business_ids, order_id__created_at__gte=start, order_id__created_at__lt=end)
        .select_related(
            'order_id'
        )
        .values('item_details_snapshot', 'quantity', 'total_price', 'menu_item_id', 'product_item_id')[:5000]
    )
    
    # Collect all menu_item_id and product_item_id for batch lookup
    menu_item_ids = {r['menu_item_id'] for r in raw_items if r['menu_item_id']}
    product_item_ids = {r['product_item_id'] for r in raw_items if r['product_item_id']}
    
    # Batch fetch categories
    menu_categories = {}
    product_categories = {}
    
    if menu_item_ids:
        menu_items = MenuItems.objects.filter(item_id__in=menu_item_ids).values('item_id', 'item_category')
        menu_categories = {item['item_id']: item['item_category'] for item in menu_items}
    
    if product_item_ids:
        product_items = productItems.objects.filter(item_id__in=product_item_ids).values('item_id', 'item_category')
        product_categories = {item['item_id']: item['item_category'] for item in product_items}
    
    for r in raw_items:
        category = None
        
        # First try to get category from related models
        if r['menu_item_id'] and r['menu_item_id'] in menu_categories:
            category = menu_categories[r['menu_item_id']]
        elif r['product_item_id'] and r['product_item_id'] in product_categories:
            category = product_categories[r['product_item_id']]
        
        # Fallback to item_details_snapshot
        if not category:
            details = r.get('item_details_snapshot') or {}
            category = details.get('item_category') or details.get('category')
        
        # Final fallback to Unknown
        if not category:
            category = 'Unknown'
            
        q = int(r.get('quantity') or 0)
        rev = Decimal(r.get('total_price') or 0)
        cat_map[category]['qty'] += q
        cat_map[category]['revenue'] += rev
    best_selling_categories = [
        {'category': k, 'qty_sold': v['qty'], 'revenue': str(v['revenue'])}
        for k, v in sorted(cat_map.items(), key=lambda x: (-x[1]['qty'], x[0]))[:5]
    ]

    best_product_name = best_selling_products[0]['name'] if best_selling_products else None
    best_category_name = best_selling_categories[0]['category'] if best_selling_categories else None

    month_str = request.query_params.get('month', _month_range_local(None)[0].strftime('%Y-%m'))
    health_status, metrics = calculate_business_health_for_business(business_ids, revenue, expenses_amt, month_str)

    payload = {
        'month': start.strftime('%Y-%m'),
        'revenue': float(revenue),
        'expenses': float(expenses_amt),
        'profit': float(profit),
        'net_worth': float(profit),
        'best_selling_product': best_product_name,
        'best_selling_category': best_category_name,
        'health_status': health_status,
        'metrics': metrics
    }

    return Response(payload)
