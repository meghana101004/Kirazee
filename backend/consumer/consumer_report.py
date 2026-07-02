from datetime import datetime, timedelta, date
from decimal import Decimal
from django.utils import timezone
from django.db.models import Sum, Count, Exists, OuterRef
from django.db.models.functions import TruncDay, TruncWeek, TruncMonth
from django.core.cache import cache
from django.conf import settings
from rest_framework import serializers, status
from rest_framework.response import Response
from rest_framework.decorators import api_view
from rest_framework.pagination import PageNumberPagination
from drf_yasg.utils import swagger_auto_schema
from .models import Orders, OrderItems, Payments
from .gro_models import GroceriesProductVariants
from .serializers import OrderItemSerializer
from django.conf import settings
from kirazee_app.models import Business, Registration
from business.models import BusinessCounterOrders, BusinessCounterItems


class ReportOrderItemSerializer(serializers.ModelSerializer):
    product_name = serializers.SerializerMethodField()
    variant = serializers.SerializerMethodField()
    product_id = serializers.SerializerMethodField()
    variant_id = serializers.SerializerMethodField()
    gst_amount = serializers.SerializerMethodField()
    other_charges = serializers.SerializerMethodField()
    unit_price_with_gst = serializers.SerializerMethodField()

    class Meta:
        model = OrderItems
        fields = [
            'item_id', 'menu_item_id', 'product_item_id', 'product_id', 'variant_id',
            'product_name', 'variant', 'quantity', 'unit_price_snapshot', 'total_price',
            'gst_amount', 'other_charges', 'unit_price_with_gst'
        ]

    def _details(self, obj):
        try:
            helper = OrderItemSerializer(context=self.context)
            return helper.get_enhanced_product_details(obj)
        except Exception:
            return None

    def get_product_id(self, obj):
        d = self._details(obj)
        return d.get('product_id') if isinstance(d, dict) else None

    def get_variant_id(self, obj):
        d = self._details(obj)
        return d.get('variant_id') if isinstance(d, dict) else None

    def get_product_name(self, obj):
        d = self._details(obj)
        if isinstance(d, dict) and d.get('product_name'):
            return d.get('product_name')
        return obj.item_name_snapshot

    def get_variant(self, obj):
        d = self._details(obj)
        vid = d.get('variant_id') if isinstance(d, dict) else None
        if not vid:
            return None
        # Cache variant lookup to avoid repeated queries
        if not hasattr(self, '_variant_cache'):
            self._variant_cache = {}
        if vid not in self._variant_cache:
            self._variant_cache[vid] = GroceriesProductVariants.objects.filter(
                variant_id=vid
            ).values('net_weight', 'net_weight_unit', 'size').first()
        v = self._variant_cache[vid]
        if not v:
            return None
        if v.get('size'):
            return str(v['size'])
        if v.get('net_weight') and v.get('net_weight_unit'):
            return f"{v['net_weight']} {v['net_weight_unit']}"
        return None

    def get_gst_amount(self, obj):
        """Calculate GST amount for this item"""
        # For online orders, GST might be included in the total_price
        # Try to get GST from product details or calculate if available
        d = self._details(obj)
        if isinstance(d, dict):
            # Try to get GST from product details
            gst_percentage = d.get('gst_percentage') or d.get('gst')
            if gst_percentage:
                try:
                    unit_price = Decimal(str(obj.unit_price_snapshot or 0))
                    gst_amount = (unit_price * Decimal(str(gst_percentage))) / 100
                    return float(gst_amount * obj.quantity)
                except (ValueError, TypeError):
                    pass
        # Fallback: estimate GST as 18% if no data available
        try:
            unit_price = Decimal(str(obj.unit_price_snapshot or 0))
            estimated_gst = (unit_price * Decimal('0.18')) * obj.quantity
            return float(estimated_gst)
        except (ValueError, TypeError):
            return 0.00

    def get_other_charges(self, obj):
        """Calculate other charges for this item"""
        # For online orders, other charges might include delivery fees, packaging, etc.
        # This would typically come from the order level, but we'll estimate per item
        d = self._details(obj)
        if isinstance(d, dict):
            # Try to get other charges from product details
            other_charges = d.get('other_charges') or d.get('charges')
            if other_charges:
                try:
                    return float(other_charges * obj.quantity)
                except (ValueError, TypeError):
                    pass
        # Fallback: no additional charges
        return 0.00

    def get_unit_price_with_gst(self, obj):
        """Calculate unit price including GST"""
        try:
            unit_price = Decimal(str(obj.unit_price_snapshot or 0))
            gst_amount = Decimal(str(self.get_gst_amount(obj))) / obj.quantity if obj.quantity > 0 else Decimal('0')
            return float(unit_price + gst_amount)
        except (ValueError, TypeError, ZeroDivisionError):
            return float(obj.unit_price_snapshot or 0)


class ReportCounterOrderItemSerializer(serializers.ModelSerializer):
    item_name = serializers.CharField(read_only=True)
    gst_amount = serializers.SerializerMethodField()
    other_charges = serializers.SerializerMethodField()
    unit_price_with_gst = serializers.SerializerMethodField()
    
    class Meta:
        model = BusinessCounterItems
        fields = [
            'id', 'sku', 'item_name', 'size_label', 'quantity', 'unit_price', 
            'gst', 'line_total', 'gst_amount', 'other_charges', 'unit_price_with_gst',
            'is_customized', 'customization_details', 'notes'
        ]
    
    def get_gst_amount(self, obj):
        """Calculate GST amount for this counter order item"""
        try:
            # GST is stored as a decimal amount in the gst field
            gst_per_item = Decimal(str(obj.gst or 0))
            return float(gst_per_item * obj.quantity)
        except (ValueError, TypeError):
            return 0.00
    
    def get_other_charges(self, obj):
        """Calculate other charges for this counter order item"""
        # For counter orders, other charges might be minimal (service charges, etc.)
        # This could be enhanced based on business requirements
        try:
            # Check if there are any additional charges beyond GST
            line_total = Decimal(str(obj.line_total or 0))
            expected_total = (Decimal(str(obj.unit_price or 0)) + Decimal(str(obj.gst or 0))) * obj.quantity
            other_charges = line_total - expected_total
            return float(max(other_charges, Decimal('0')))  # Ensure non-negative
        except (ValueError, TypeError):
            return 0.00
    
    def get_unit_price_with_gst(self, obj):
        """Calculate unit price including GST"""
        try:
            unit_price = Decimal(str(obj.unit_price or 0))
            gst_per_item = Decimal(str(obj.gst or 0))
            return float(unit_price + gst_per_item)
        except (ValueError, TypeError):
            return float(obj.unit_price or 0)


class ReportCounterOrderSerializer(serializers.ModelSerializer):
    order_date = serializers.SerializerMethodField()
    user = serializers.SerializerMethodField()
    order_total = serializers.DecimalField(source='total_amount', max_digits=10, decimal_places=2, read_only=True)
    items = ReportCounterOrderItemSerializer(many=True, read_only=True)
    
    class Meta:
        model = BusinessCounterOrders
        fields = ['order_id', 'token_number', 'order_date', 'user', 'username', 'order_total', 'items', 'service_mode', 'payment_method']
    
    def get_order_date(self, obj):
        dt = obj.created_at
        try:
            return dt.isoformat()
        except Exception:
            return None
    
    def get_user(self, obj):
        u = getattr(obj, 'user_id', None)
        if not u:
            return None
        # For counter orders, use the username field from business_counter_orders table
        # Use customer_email and customer_mobile directly from the order, not from staff user
        user_id = getattr(u, 'user_id', None)
        customer_email = getattr(obj, 'customer_email', None)
        customer_mobile = getattr(obj, 'customer_mobile', None)
        
        # Mask email - show first 2 chars and domain
        masked_email = None
        if customer_email and '@' in customer_email:
            local, domain = customer_email.split('@', 1)
            if len(local) > 2:
                masked_email = f"{local[:2]}***@{domain}"
            else:
                masked_email = f"{local[0]}***@{domain}"
        
        # Mask mobile - show first 2 and last 2 digits
        masked_mobile = None
        if customer_mobile and len(customer_mobile) >= 4:
            masked_mobile = f"{customer_mobile[:2]}***{customer_mobile[-2:]}"
        
        return {
            'user_id': user_id,
            'username': getattr(obj, 'username', 'skipped'),  # Use username from business_counter_orders table
            'email': masked_email,  # Use customer_email from order
            'mobile': masked_mobile,  # Use customer_mobile from order
        }


class ReportOrderSerializer(serializers.ModelSerializer):
    order_date = serializers.SerializerMethodField()
    user = serializers.SerializerMethodField()
    order_total = serializers.DecimalField(source='final_amount', max_digits=10, decimal_places=2, read_only=True)
    items = ReportOrderItemSerializer(many=True, read_only=True)

    class Meta:
        model = Orders
        fields = ['order_id', 'order_number', 'order_date', 'user', 'order_total', 'items']

    def get_order_date(self, obj):
        dt = obj.created_at
        try:
            return dt.isoformat()
        except Exception:
            return None

    def get_user(self, obj):
        u = getattr(obj, 'user_id', None)
        if not u:
            return None
        # For online orders, use displayName from registrations table
        # Also mask user details for privacy
        user_id = getattr(u, 'user_id', None)
        email = getattr(u, 'emailID', None)
        mobile = getattr(u, 'mobileNumber', None)
        
        # Mask email - show first 2 chars and domain
        masked_email = None
        if email and '@' in email:
            local, domain = email.split('@', 1)
            if len(local) > 2:
                masked_email = f"{local[:2]}***@{domain}"
            else:
                masked_email = f"{local[0]}***@{domain}"
        
        # Mask mobile - show first 2 and last 2 digits
        masked_mobile = None
        if mobile and len(mobile) >= 4:
            masked_mobile = f"{mobile[:2]}***{mobile[-2:]}"
        
        return {
            'user_id': user_id,
            'username': getattr(u, 'displayName', None),  # Use displayName from registrations table
            'email': masked_email,
            'mobile': masked_mobile,
        }


class ReportsPagination(PageNumberPagination):
    page_size = 20
    page_size_query_param = 'page_size'
    max_page_size = 200


def _parse_date(val):
    try:
        return datetime.strptime(val, '%Y-%m-%d').date()
    except Exception:
        return None


def _default_range(period):
    now = timezone.now() if getattr(settings, 'USE_TZ', False) else datetime.now()
    today = now.date()
    if period == 'daily':
        start_d = today
        end_d = today
    elif period == 'weekly':
        start_d = today - timedelta(days=today.weekday())
        end_d = start_d + timedelta(days=6)
    else:
        start_d = today.replace(day=1)
        if start_d.month == 12:
            next_month = start_d.replace(year=start_d.year + 1, month=1, day=1)
        else:
            next_month = start_d.replace(month=start_d.month + 1, day=1)
        end_d = next_month - timedelta(days=1)
    start_dt = datetime.combine(start_d, datetime.min.time())
    end_dt = datetime.combine(end_d, datetime.max.time())
    if getattr(settings, 'USE_TZ', False):
        if timezone.is_naive(start_dt):
            start_dt = timezone.make_aware(start_dt)
        if timezone.is_naive(end_dt):
            end_dt = timezone.make_aware(end_dt)
    return start_dt, end_dt


def _compute_period_func(period):
    if period == 'daily':
        return TruncDay
    if period == 'weekly':
        return TruncWeek
    return TruncMonth


def _build_summary_by_period(orders_qs, period):
    func = _compute_period_func(period)
    agg_orders = orders_qs.annotate(period=func('created_at')).values('period').annotate(
        order_count=Count('order_id'),
        revenue=Sum('final_amount')
    )
    items_qs = OrderItems.objects.filter(order_id__in=orders_qs.values('order_id')).annotate(period=func('order_id__created_at')).values('period').annotate(
        items_sold=Sum('quantity')
    )
    items_map = {x['period']: x.get('items_sold') or 0 for x in items_qs}
    out = []
    for row in agg_orders:
        period_dt = row['period']
        period_str = None
        try:
            period_str = period_dt.date().isoformat()
        except Exception:
            try:
                period_str = str(period_dt)
            except Exception:
                period_str = None
        out.append({
            'period': period_str,
            'order_count': row.get('order_count') or 0,
            'items_sold': items_map.get(row['period'], 0),
            'revenue': row.get('revenue') or Decimal('0.00')
        })
    return out


def _date_bounds(request, period):
    s = request.query_params.get('start_date') if hasattr(request, 'query_params') else request.GET.get('start_date')
    e = request.query_params.get('end_date') if hasattr(request, 'query_params') else request.GET.get('end_date')
    if s or e:
        sd = _parse_date(s) if s else None
        ed = _parse_date(e) if e else None
        if not sd or not ed:
            return None, None, Response({'detail': 'Invalid date format. Use YYYY-MM-DD.'}, status=status.HTTP_400_BAD_REQUEST)
        if ed < sd:
            return None, None, Response({'detail': 'end_date must be on or after start_date.'}, status=status.HTTP_400_BAD_REQUEST)
        start_dt = datetime.combine(sd, datetime.min.time())
        end_dt = datetime.combine(ed, datetime.max.time())
        if getattr(settings, 'USE_TZ', False):
            if timezone.is_naive(start_dt):
                start_dt = timezone.make_aware(start_dt)
            if timezone.is_naive(end_dt):
                end_dt = timezone.make_aware(end_dt)
        return start_dt, end_dt, None
    return *_default_range(period), None


def _build_counter_summary_by_period(counter_orders_qs, period):
    func = _compute_period_func(period)
    agg_orders = counter_orders_qs.annotate(period=func('created_at')).values('period').annotate(
        order_count=Count('order_id'),
        revenue=Sum('total_amount')
    )
    items_qs = BusinessCounterItems.objects.filter(order_id__in=counter_orders_qs.values('order_id')).annotate(period=func('order_id__created_at')).values('period').annotate(
        items_sold=Sum('quantity')
    )
    items_map = {x['period']: x.get('items_sold') or 0 for x in items_qs}
    out = []
    for row in agg_orders:
        period_dt = row['period']
        period_str = None
        try:
            period_str = period_dt.date().isoformat()
        except Exception:
            try:
                period_str = str(period_dt)
            except Exception:
                period_str = None
        out.append({
            'period': period_str,
            'order_count': row.get('order_count') or 0,
            'items_sold': items_map.get(row['period'], 0),
            'revenue': row.get('revenue') or Decimal('0.00')
        })
    return out


def _get_cache_key(period, request):
    """Generate cache key for reports based on parameters"""
    bid = request.query_params.get('business_id', '')
    bt = request.query_params.get('business_type', '')
    start_date = request.query_params.get('start_date', '')
    end_date = request.query_params.get('end_date', '')
    page = request.query_params.get('page', '1')
    page_size = request.query_params.get('page_size', '20')
    
    return f"reports:{period}:{bid}:{bt}:{start_date}:{end_date}:{page}:{page_size}"


def _build_report(period, request):
    # Check cache first
    cache_key = _get_cache_key(period, request)
    cached_response = cache.get(cache_key)
    if cached_response:
        return Response(cached_response)
    
    start_dt, end_dt, err = _date_bounds(request, period)
    if err is not None:
        return err
    
    # Get business scope info once to avoid repeated queries
    bid = request.query_params.get('business_id') if hasattr(request, 'query_params') else request.GET.get('business_id')
    bt = request.query_params.get('business_type') if hasattr(request, 'query_params') else request.GET.get('business_type')
    
    scope_ids = None
    if bid:
        try:
            biz = Business.objects.select_related().get(business_id=bid)
            if (getattr(biz, 'level', None) == 'Master Level') or not getattr(biz, 'master', None):
                scope_ids = list(Business.objects.filter(master=bid, status=True).values_list('business_id', flat=True))
                scope_ids = [bid] + scope_ids
            else:
                scope_ids = [bid]
        except Business.DoesNotExist:
            return Response({'detail': 'Invalid business_id'}, status=status.HTTP_400_BAD_REQUEST)
    
    # Build base query with optimized filters - use proper datetime range filtering
    base_qs = Orders.objects.filter(
        created_at__gte=start_dt,
        created_at__lte=end_dt
    )
    if scope_ids:
        base_qs = base_qs.filter(business_id__business_id__in=scope_ids)
    if bt:
        types = [t.strip() for t in str(bt).split(',') if t and str(t).strip()]
        if types:
            base_qs = base_qs.filter(business_id__businessType__in=types)
    
    # Get online orders with optimized queries - limit fields to reduce memory
    success_exists = Payments.objects.filter(order_id=OuterRef('order_id'), status=Payments.Status.SUCCESS)
    online_orders_qs = base_qs.filter(Exists(success_exists)).select_related(
        'user_id', 'business_id'
    ).only(
        'order_id', 'order_number', 'created_at', 'final_amount', 'user_id', 'business_id'
    ).prefetch_related(
        'items'
    )
    
    # Get counter orders with same filters - optimize date filtering
    counter_orders_qs = BusinessCounterOrders.objects.filter(
        created_at__gte=start_dt,
        created_at__lte=end_dt
    )
    if scope_ids:
        counter_orders_qs = counter_orders_qs.filter(business_id__business_id__in=scope_ids)
    if bt:
        types = [t.strip() for t in str(bt).split(',') if t and str(t).strip()]
        if types:
            counter_orders_qs = counter_orders_qs.filter(business_id__businessType__in=types)
    
    counter_orders_qs = counter_orders_qs.select_related(
        'user_id', 'business_id'
    ).only(
        'order_id', 'token_number', 'created_at', 'total_amount', 'user_id', 'business_id'
    ).prefetch_related(
        'items'
    )
    
    # Optimized aggregations using single queries
    online_order_ids = online_orders_qs.values_list('order_id', flat=True)
    counter_order_ids = counter_orders_qs.values_list('order_id', flat=True)
    
    # Single query for all aggregations
    online_aggregates = online_orders_qs.aggregate(
        total_orders=Count('order_id'),
        total_revenue=Sum('final_amount')
    )
    counter_aggregates = counter_orders_qs.aggregate(
        total_orders=Count('order_id'),
        total_revenue=Sum('total_amount')
    )
    
    # Optimized item counts
    online_items_total = OrderItems.objects.filter(
        order_id__in=online_order_ids
    ).aggregate(total=Sum('quantity')).get('total') or 0
    
    counter_items_total = BusinessCounterItems.objects.filter(
        order_id__in=counter_order_ids
    ).aggregate(total=Sum('quantity')).get('total') or 0
    
    # Calculate totals
    total_online_orders = online_aggregates['total_orders'] or 0
    total_counter_orders = counter_aggregates['total_orders'] or 0
    total_orders = total_online_orders + total_counter_orders
    items_total = online_items_total + counter_items_total
    online_revenue_total = online_aggregates['total_revenue'] or Decimal('0.00')
    counter_revenue_total = counter_aggregates['total_revenue'] or Decimal('0.00')
    revenue_total = online_revenue_total + counter_revenue_total
    # Paginate online orders
    paginator = ReportsPagination()
    online_page_qs = paginator.paginate_queryset(online_orders_qs.order_by('-created_at'), request)
    online_orders_data = ReportOrderSerializer(online_page_qs, many=True, context={'request': request}).data
    
    # Paginate counter orders
    counter_paginator = ReportsPagination()
    counter_page_qs = counter_paginator.paginate_queryset(counter_orders_qs.order_by('-created_at'), request)
    counter_orders_data = ReportCounterOrderSerializer(counter_page_qs, many=True, context={'request': request}).data
    
    # Combine orders data
    orders_data = online_orders_data + counter_orders_data
    
    # Sort combined orders by date (most recent first)
    orders_data.sort(key=lambda x: x.get('order_date', ''), reverse=True)
    
    # Build summary for both order types
    online_summary = _build_summary_by_period(online_orders_qs, period)
    counter_summary = _build_counter_summary_by_period(counter_orders_qs, period)
    
    # Combine summaries
    combined_summary = []
    period_map = {}
    
    # Add online summary to map
    for item in online_summary:
        period_map[item['period']] = {
            'order_count': item['order_count'],
            'items_sold': item['items_sold'],
            'revenue': item['revenue']
        }
    
    # Add counter summary and combine
    for item in counter_summary:
        if item['period'] in period_map:
            period_map[item['period']]['order_count'] += item['order_count']
            period_map[item['period']]['items_sold'] += item['items_sold']
            period_map[item['period']]['revenue'] += item['revenue']
        else:
            period_map[item['period']] = {
                'order_count': item['order_count'],
                'items_sold': item['items_sold'],
                'revenue': item['revenue']
            }
    
    # Convert map back to list and sort
    combined_summary = [
        {
            'period': period,
            'order_count': data['order_count'],
            'items_sold': data['items_sold'],
            'revenue': data['revenue']
        }
        for period, data in period_map.items()
    ]
    combined_summary.sort(key=lambda x: x.get('period', ''))
    resp = {
        'report_type': period,
        'date_range': {
            'start_date': start_dt.date().isoformat(),
            'end_date': end_dt.date().isoformat(),
        },
        'totals': {
            'total_orders': total_orders,
            'online_orders': total_online_orders,
            'counter_orders': total_counter_orders,
            'total_items_sold': items_total,
            'online_items_sold': online_items_total,
            'counter_items_sold': counter_items_total,
            'total_revenue': revenue_total,
            'online_revenue': online_revenue_total,
            'counter_revenue': counter_revenue_total,
        },
        'summary_by_period': combined_summary,
        'orders': orders_data,
        'pagination': {
            'page': getattr(paginator.page, 'number', None),
            'page_size': getattr(paginator, 'page_size', None),
            'total_pages': getattr(getattr(paginator, 'page', None), 'paginator', None).num_pages if getattr(paginator, 'page', None) else None,
            'next': paginator.get_next_link(),
            'previous': paginator.get_previous_link(),
        }
    }
    
    # Cache the response for 15 minutes (900 seconds)
    cache.set(cache_key, resp, timeout=900)
    
    return Response(resp)

@swagger_auto_schema(methods=['GET'],tags=['Consumer'])
@api_view(['GET'])
def reports_daily(request):
    return _build_report('daily', request)

@swagger_auto_schema(methods=['GET'],tags=['Consumer'])
@api_view(['GET'])
def reports_weekly(request):
    return _build_report('weekly', request)

@swagger_auto_schema(methods=['GET'],tags=['Consumer'])
@api_view(['GET'])
def reports_monthly(request):
    return _build_report('monthly', request)

