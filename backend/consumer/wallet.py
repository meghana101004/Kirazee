import traceback
from django.conf import settings
from django.db import transaction, models, connection
from django.db.models import Count
from django.utils import timezone
from datetime import datetime, timedelta
from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework import status
from django.http import JsonResponse
from django.core.paginator import Paginator
from django.shortcuts import get_object_or_404
from drf_yasg.utils import swagger_auto_schema
from decimal import Decimal
import json

from .models import WalletPoints, Coupons, CouponRules, CouponRedemptions, PointsConfiguration, CouponApplicableItems, Orders
from .serializers import WalletPointsSerializer, CouponSerializer
from kirazee_app.models import Registration, Business


def get_wallet_balance_raw_sql(user_id):
    """
    Get wallet balance using raw SQL to avoid decimal/float conflicts
    """
    with connection.cursor() as cursor:
        # Get current balance from latest transaction
        cursor.execute("""
            SELECT CAST(balance_after AS DECIMAL(10,2)) as current_balance
            FROM wallet_points 
            WHERE user_id = %s 
            ORDER BY created_at DESC 
            LIMIT 1
        """, [user_id])
        
        result = cursor.fetchone()
        return Decimal(str(result[0])) if result else Decimal('0.00')

def get_expiring_points_raw_sql(user_id):
    """
    Get expiring points using raw SQL
    """
    with connection.cursor() as cursor:
        cursor.execute("""
            SELECT COALESCE(SUM(CAST(points AS DECIMAL(10,2))), 0) as expiring_total
            FROM wallet_points 
            WHERE user_id = %s 
            AND transaction_type = 'EARNED'
            AND is_expired = 0
            AND expires_at <= DATE_ADD(NOW(), INTERVAL 30 DAY)
            AND expires_at > NOW()
        """, [user_id])
        
        result = cursor.fetchone()
        return Decimal(str(result[0])) if result else Decimal('0.00')

def get_recent_transactions_raw_sql(user_id, limit=10):
    """
    Get recent transactions using raw SQL
    """
    with connection.cursor() as cursor:
        cursor.execute("""
            SELECT 
                wallet_id,
                transaction_type,
                CAST(points AS DECIMAL(10,2)) as points,
                CAST(balance_after AS DECIMAL(10,2)) as balance_after,
                description,
                created_at,
                is_expired
            FROM wallet_points 
            WHERE user_id = %s 
            ORDER BY created_at DESC 
            LIMIT %s
        """, [user_id, limit])
        
        columns = [col[0] for col in cursor.description]
        return [dict(zip(columns, row)) for row in cursor.fetchall()]

@swagger_auto_schema(methods=['GET'],tags=['Consumer'])
@api_view(['GET'])
def get_wallet_balance(request, user_id):
    """
    Get user's current wallet points balance and recent transactions using raw SQL
    """
    try:
        user = get_object_or_404(Registration, user_id=user_id)
        
        # Get current balance using raw SQL
        current_balance = get_wallet_balance_raw_sql(user_id)
        
        # Get expiring points using raw SQL
        expiring_soon = get_expiring_points_raw_sql(user_id)
        
        # Get recent transactions using raw SQL
        recent_transactions = get_recent_transactions_raw_sql(user_id, 10)
        
        # Calculate rupee value safely
        balance_in_rupees = current_balance * Decimal('0.10')
        
        return Response({
            'success': True,
            'data': {
                'user_id': user_id,
                'current_balance': str(current_balance),
                'expiring_soon': str(expiring_soon),
                'recent_transactions': recent_transactions,
                'balance_in_rupees': str(balance_in_rupees)
            }
        }, status=status.HTTP_200_OK)
        
    except Exception as e:
        return Response({
            'success': False,
            'error': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@swagger_auto_schema(methods=['GET'],tags=['Consumer'])
@api_view(['GET'])
def get_wallet_transactions(request, user_id):
    """
    Get paginated wallet transaction history with filtering using raw SQL
    Query Parameters:
    - transaction_type: Filter by transaction type (EARNED, SPENT, REFUNDED, etc.)
    - date_from: Filter transactions from this date (YYYY-MM-DD)
    - date_to: Filter transactions until this date (YYYY-MM-DD)
    - page: Page number (default: 1)
    - page_size: Number of transactions per page (default: 20)
    """
    try:
        # Get query parameters with defaults
        transaction_type = request.query_params.get('transaction_type')
        date_from = request.query_params.get('date_from')
        date_to = request.query_params.get('date_to')
        page = max(1, int(request.query_params.get('page', 1)))
        page_size = max(1, min(100, int(request.query_params.get('page_size', 20))))
        offset = (page - 1) * page_size

        # Update the SQL query to match your table structure
        sql = """
        WITH filtered_transactions AS (
            SELECT 
                wp.wallet_id,
                wp.points,
                wp.transaction_type,
                wp.description,
                wp.balance_after,
                wp.created_at,
                wp.related_order_id,
                wp.related_coupon_purchase_id,
                wp.expires_at,
                wp.is_expired,
                COUNT(*) OVER() AS total_count
            FROM 
                wallet_points wp
            WHERE 
                wp.user_id = %s  # Changed from user_id_id to user_id
                {transaction_type_filter}
                {date_from_filter}
                {date_to_filter}
            ORDER BY 
                wp.created_at DESC
            LIMIT %s OFFSET %s
        )
        SELECT 
            wallet_id,
            points,
            transaction_type,
            description,
            balance_after,
            created_at,
            related_order_id,
            related_coupon_purchase_id,
            expires_at,
            is_expired,
            total_count
        FROM 
            filtered_transactions
        """
        
        # Build filter conditions
        filters = {
            'transaction_type_filter': "AND wp.transaction_type = %s" if transaction_type else "",
            'date_from_filter': "AND DATE(wp.created_at) >= %s" if date_from else "",
            'date_to_filter': "AND DATE(wp.created_at) <= %s" if date_to else ""
        }
        
        # Prepare parameters
        params = [user_id]
        
        if transaction_type:
            params.append(transaction_type)
        if date_from:
            params.append(date_from)
        if date_to:
            params.append(date_to)
            
        # Add pagination parameters
        params.extend([page_size, offset])
        
        # Format SQL with filters
        sql = sql.format(**filters)
        
        # Execute query
        with connection.cursor() as cursor:
            cursor.execute(sql, params)
            columns = [col[0] for col in cursor.description]
            rows = cursor.fetchall()
        
        # Process results
        transactions = []
        total_count = 0
        
        if rows:
            # Convert rows to dictionaries
            transactions = [dict(zip(columns, row)) for row in rows]
            # Get total count from first row (since we used window function)
            total_count = transactions[0].pop('total_count', 0)
            
            # Format response data
            for txn in transactions:
                txn['created_at'] = txn['created_at'].isoformat() if txn['created_at'] else None
                txn['points'] = float(txn['points'])
                txn['balance_after'] = float(txn['balance_after']) if txn['balance_after'] is not None else 0.0
        
        # Calculate pagination
        total_pages = (total_count + page_size - 1) // page_size if total_count else 1
        
        # Build response
        response_data = {
            'success': True,
            'data': {
                'count': total_count,
                'page': page,
                'page_size': page_size,
                'total_pages': total_pages,
                'next': f'/consumer/wallet/{user_id}/transactions/?page={page + 1}' if page < total_pages else None,
                'previous': f'/consumer/wallet/{user_id}/transactions/?page={page - 1}' if page > 1 else None,
                'results': transactions
            }
        }
        
        return Response(response_data, status=status.HTTP_200_OK)
        
    except Exception as e:
        return Response({
            'success': False,
            'error': str(e),
            'traceback': traceback.format_exc() if settings.DEBUG else None
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@swagger_auto_schema(methods=['POST'],tags=['Consumer'])
@api_view(['POST'])
def spend_wallet_points(request):
    """
    Spend wallet points (used internally by order system)
    """
    try:
        data = request.data
        user_id = data.get('user_id')
        points_to_spend = Decimal(str(data.get('points', 0)))
        description = data.get('description', 'Points spent')
        order_id = data.get('order_id')
        
        if not user_id or points_to_spend <= 0:
            return Response({
                'success': False,
                'error': 'Invalid user_id or points amount'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        user = get_object_or_404(Registration, user_id=user_id)
        
        # Check balance
        current_balance = WalletPoints.get_user_balance(user_id)
        if current_balance < points_to_spend:
            return Response({
                'success': False,
                'error': f'Insufficient balance. Available: {current_balance}, Requested: {points_to_spend}'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Process transaction
        transaction = WalletPoints.atomic_transaction(
            user_id=user,
            points=points_to_spend,
            transaction_type=WalletPoints.TransactionType.SPENT,
            description=description,
            related_order_id=order_id
        )
        
        return Response({
            'success': True,
            'message': 'Points spent successfully',
            'data': {
                'transaction_id': transaction.wallet_id,
                'points_spent': float(points_to_spend),
                'remaining_balance': float(transaction.balance_after),
                'rupee_value': float(points_to_spend * Decimal('0.10'))
            }
        }, status=status.HTTP_200_OK)
        
    except Exception as e:
        return Response({
            'success': False,
            'error': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@swagger_auto_schema(methods=['GET'],tags=['Consumer'])
@api_view(['GET'])
def list_available_coupons(request):
    """
    Get list of all available coupons with user-specific validation
    Query Params (all optional):
    - user_id: If provided, includes user-specific validation
    - business_id: Filter by specific business
    - cart_value: For validating minimum order requirements
    - debug: Set to true to include SQL and debug info
    """
    try:
        user_id = request.query_params.get('user_id')
        business_id = request.query_params.get('business_id')
        cart_value = Decimal(request.query_params.get('cart_value', 0))
        order_type = request.query_params.get('order_type')
        debug_mode = request.query_params.get('debug', '').lower() == 'true'

        user_email_domain = None
        user_mapped_tag = None
        if user_id:
            try:
                user_obj = Registration.objects.only('emailID').get(user_id=user_id)
                user_email = (user_obj.emailID or '').strip().lower()
                if '@' in user_email:
                    user_email_domain = user_email.split('@', 1)[1]
                    try:
                        from .models import DomainTagMapping
                        
                        # Try business-specific mapping first, then fallback to global
                        business_id = coupon.business_id if coupon else None
                        user_mapped_tag = None
                        
                        # First try business-specific mapping
                        if business_id:
                            user_mapped_tag = DomainTagMapping.objects.filter(
                                domain=user_email_domain.lower(),
                                business_id=business_id,
                                is_active=True
                            ).values_list('tag', flat=True).first()
                        
                        # Fallback to global mapping if no business-specific match
                        if not user_mapped_tag:
                            user_mapped_tag = DomainTagMapping.objects.filter(
                                domain=user_email_domain.lower(),
                                business_id__isnull=True,
                                is_active=True
                            ).values_list('tag', flat=True).first()
                        
                        if user_mapped_tag:
                            user_mapped_tag = str(user_mapped_tag).strip().lower()
                    except Exception:
                        user_mapped_tag = None
            except Exception:
                user_email_domain = None
                user_mapped_tag = None
        
        # Debug info
        debug_info = {}
        if debug_mode:
            debug_info['query_params'] = dict(request.query_params)
        
        # Base query for active coupons with raw SQL
        if getattr(settings, 'USE_TZ', False):
            current_time = timezone.now().strftime('%Y-%m-%d %H:%M:%S')
        else:
            current_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        sql = """
        SELECT 
            c.coupon_id, c.coupon_code, c.discount_type, c.discount_value,
            c.created_by, c.business_id, c.valid_from, c.valid_to, c.is_active,
            c.max_total_redemptions, c.max_redemptions_per_user, c.current_usage_count,
            c.visibility_type, c.coupon_scope, c.free_delivery, c.free_packaging,
            c.created_at, c.updated_at,
            c.description, c.terms_and_conditions,
            b.business_id as business_identifier,
            b.businessName,
            cr.rule_id,
            cr.rule_type,
            cr.rule_value,
            cr.is_active as rule_active
        FROM 
            coupons c
        LEFT JOIN 
            businesses b ON c.business_id = b.business_id
        LEFT JOIN
            coupon_rules cr ON c.coupon_id = cr.coupon_id
        WHERE 
            c.is_active = TRUE
        """

        params = []
        
        # Add visibility filtering
        if user_id:
            sql += """
            AND (
                c.visibility_type = 'PUBLIC'
                OR c.visibility_type = 'PRIVATE'
            )
            """
        else:
            # For non-authenticated users, only show PUBLIC coupons
            sql += " AND c.visibility_type = 'PUBLIC'"
        
        # Exclude HIDDEN coupons from listing
        sql += " AND c.visibility_type != 'HIDDEN'"
        
        # Add business scope filtering
        if business_id:
            sql += " AND (c.coupon_scope = 'PLATFORM' OR (c.coupon_scope != 'PLATFORM' AND c.business_id = %s))"
            params.append(business_id)
        
        # Add ordering
        sql += " ORDER BY c.created_at DESC"
        
        if debug_mode:
            debug_info['sql_query'] = sql
            debug_info['sql_params'] = params
        
        # Execute raw SQL
        with connection.cursor() as cursor:
            cursor.execute(sql, params)
            columns = [col[0] for col in cursor.description]
            raw_coupons = [dict(zip(columns, row)) for row in cursor.fetchall()]
        
        if debug_mode:
            debug_info['raw_coupons_count'] = len(raw_coupons)
            debug_info['raw_coupons_sample'] = raw_coupons[:1] if raw_coupons else []
        
        # Group coupons and their rules
        coupons_dict = {}
        for row in raw_coupons:
            coupon_id = row['coupon_id']
            if coupon_id not in coupons_dict:
                coupons_dict[coupon_id] = {
                    'coupon_id': coupon_id,
                    'coupon_code': row['coupon_code'],
                    'discount_type': row['discount_type'],
                    'discount_value': float(row['discount_value']),
                    'description': row.get('description') or f"{row['discount_value']}{' OFF' if row['discount_type'] == 'percentage' else ' OFF'}",
                    'terms_and_conditions': row.get('terms_and_conditions'),
                    'valid_from': row['valid_from'].isoformat() if row.get('valid_from') else None,
                    'valid_to': row['valid_to'].isoformat() if row.get('valid_to') else None,
                    'visibility_type': row['visibility_type'],
                    'coupon_scope': row['coupon_scope'],
                    'free_delivery': bool(row['free_delivery']),
                    'free_packaging': bool(row['free_packaging']),
                    'max_total_redemptions': row['max_total_redemptions'],
                    'max_redemptions_per_user': row['max_redemptions_per_user'],
                    'current_usage_count': row['current_usage_count'],
                    'business_specific': bool(row['business_id']),
                    'business_id': row['business_identifier'],
                    'businessName': row['businessName'],
                    'rules': [],
                    'min_cart_value': None
                }
            
            # Add rule if exists
            if row['rule_id']:
                rv = row['rule_value']
                try:
                    if rv is not None and not isinstance(rv, (dict, list)):
                        rv = json.loads(rv)
                except Exception:
                    pass
                coupons_dict[coupon_id]['rules'].append({
                    'rule_id': row['rule_id'],
                    'rule_type': row['rule_type'],
                    'rule_value': rv,
                    'is_active': row['rule_active']
                })
        
        coupons = list(coupons_dict.values())

        # Determine item-specific mappings in bulk
        try:
            if coupons:
                coupon_ids = [c['coupon_id'] for c in coupons]
                # Fetch counts from coupon_applicable_items for these coupons
                with connection.cursor() as cursor:
                    in_clause = ','.join(['%s'] * len(coupon_ids))
                    cursor.execute(f"""
                        SELECT coupon_id, COUNT(*) as cnt
                        FROM coupon_applicable_items
                        WHERE coupon_id IN ({in_clause})
                        GROUP BY coupon_id
                    """, coupon_ids)
                    counts = cursor.fetchall()
                    count_map = {int(row[0]): int(row[1]) for row in counts}
                for c in coupons:
                    cnt = count_map.get(int(c['coupon_id']), 0)
                    c['is_item_specific'] = cnt > 0
                    c['applicable_item_count'] = cnt
        except Exception:
            # Non-fatal; just skip if table missing
            for c in coupons:
                c['is_item_specific'] = False
                c['applicable_item_count'] = 0

        # Pre-compute per-user redemption usage if user_id provided
        user_usage_map = {}
        if user_id and coupons:
            try:
                coupon_ids = [c['coupon_id'] for c in coupons]
                with connection.cursor() as cursor:
                    in_clause = ','.join(['%s'] * len(coupon_ids))
                    cursor.execute(f"""
                        SELECT coupon_id, COUNT(*) as cnt
                        FROM coupon_redemptions
                        WHERE user_id = %s AND coupon_id IN ({in_clause})
                        GROUP BY coupon_id
                    """, [user_id, *coupon_ids])
                    for cid, cnt in cursor.fetchall():
                        user_usage_map[int(cid)] = int(cnt)
            except Exception:
                user_usage_map = {}
        
        # Get user's wallet balance if user_id provided
        user_wallet_balance = 0
        if user_id:
            try:
                user_wallet_balance = WalletPoints.get_user_balance(user_id)
            except Exception as e:
                if debug_mode:
                    debug_info['wallet_balance_error'] = str(e)
        
        # Process each coupon for eligibility
        response_data = []
        # Current time for validity checks
        now_dt = timezone.now() if getattr(settings, 'USE_TZ', False) else datetime.now()
        for coupon in coupons:
            # Default values
            is_valid = True
            validation_messages = []
            reason_codes = []

            # Filter out allowed_user coupons unless this user is explicitly allowed
            allowed_user_ids = None
            for rule in coupon.get('rules', []):
                if not rule['is_active']:
                    continue
                rtype_norm = str(rule.get('rule_type') or '').upper()
                if rtype_norm == 'ALLOWED_USER':
                    rv = rule.get('rule_value') or {}
                    try:
                        if isinstance(rv, dict):
                            if 'user_ids' in rv:
                                allowed_user_ids = set([int(x) for x in rv.get('user_ids') or []])
                            elif 'user_id' in rv:
                                allowed_user_ids = {int(rv.get('user_id'))}
                    except Exception:
                        allowed_user_ids = set()
                    break
            if allowed_user_ids is not None:
                if not user_id or int(user_id) not in allowed_user_ids:
                    # Skip this coupon entirely for non-allowed users
                    continue

            # Check coupon rules
            for rule in coupon.get('rules', []):
                if not rule['is_active']:
                    continue
                # Normalize rule type and read min_value safely
                rtype = str(rule.get('rule_type') or '').lower()
                if rtype == 'min_cart_value' and cart_value > 0:
                    rv = rule.get('rule_value')
                    try:
                        if isinstance(rv, (dict,)):
                            min_value = Decimal(str(rv.get('min_value', 0)))
                        else:
                            min_value = Decimal(str(rv))
                    except Exception:
                        min_value = Decimal('0')
                    coupon['min_cart_value'] = float(min_value)
                    if cart_value < min_value:
                        is_valid = False
                        # Compute shortfall message per shared criteria
                        try:
                            shortfall = (min_value - cart_value)
                            short_txt = f"Add ₹{shortfall} more to avail this offer" if shortfall > 0 else f"Minimum order value of ₹{min_value} required"
                        except Exception:
                            short_txt = f"Minimum order value of ₹{min_value} required"
                        validation_messages.append(short_txt)
                        reason_codes.append('min_cart_value')
                elif rtype == 'delivery_only':
                    if order_type and str(order_type).lower() != 'delivery':
                        is_valid = False
                        validation_messages.append('Coupon not applicable.delivery_only')
                        reason_codes.append('delivery_only')
                elif rtype == 'order_type':
                    try:
                        rv = rule.get('rule_value') or {}
                        allowed = rv.get('allowed_types') or rv.get('order_types') or rv.get('allowed_order_types') or []
                        if isinstance(allowed, list) and order_type:
                            incoming = str(order_type).lower().replace('-', '_')
                            if incoming == 'dinein':
                                incoming = 'dine_in'
                            norm_allowed = [str(x).lower().replace('-', '_') for x in allowed]
                            norm_allowed = ['dine_in' if a == 'dinein' else a for a in norm_allowed]
                            if norm_allowed and incoming not in norm_allowed:
                                is_valid = False
                                validation_messages.append('Not applicable for this order type')
                                reason_codes.append('order_type')
                    except Exception:
                        pass
                elif rtype == 'email_domain':
                    try:
                        rv = rule.get('rule_value') or {}
                        allowed_domains = rv.get('allowed_domains') or []
                        allowed_domains = [str(d).lower().lstrip('@') for d in allowed_domains if d]
                        if allowed_domains:
                            if not user_email_domain or user_email_domain.lower() not in allowed_domains:
                                is_valid = False
                                validation_messages.append('Not eligible for this coupon')
                                reason_codes.append('email_domain')
                    except Exception:
                        pass
                elif rtype == 'user_tag':
                    try:
                        rv = rule.get('rule_value') or {}
                        allowed_tags = rv.get('allowed_tags') or []
                        allowed_tags = [str(t).strip().lower() for t in allowed_tags if t]
                        if allowed_tags:
                            if not user_mapped_tag or user_mapped_tag not in allowed_tags:
                                is_valid = False
                                validation_messages.append('Not eligible for this coupon')
                                reason_codes.append('user_tag')
                    except Exception:
                        pass
                elif rtype == 'first_order_only':
                    try:
                        if user_id:
                            has_any_order = Orders.objects.filter(user_id=user_id, status=Orders.OrderStatus.DELIVERED).exists()
                            if has_any_order:
                                is_valid = False
                                validation_messages.append('Valid only on your first order')
                                reason_codes.append('first_order_only')
                    except Exception:
                        pass
                elif rtype == 'first_order_at_business':
                    try:
                        if user_id and business_id:
                            has_at_biz = Orders.objects.filter(user_id=user_id, business_id=business_id, status=Orders.OrderStatus.DELIVERED).exists()
                            if has_at_biz:
                                is_valid = False
                                validation_messages.append('Valid only on your first order at this business')
                                reason_codes.append('first_order_at_business')
                    except Exception:
                        pass
                elif rtype == 'allowed_business':
                    try:
                        rv = rule.get('rule_value') or {}
                        allowed_biz = set([str(x) for x in (rv.get('business_ids') or [])])
                        if business_id and allowed_biz and str(business_id) not in allowed_biz:
                            is_valid = False
                            validation_messages.append('Coupon not valid for this business')
                            reason_codes.append('allowed_business')
                    except Exception:
                        pass

            # User-specific validations
            if user_id:
                # Per-user usage limit
                try:
                    used_cnt = user_usage_map.get(int(coupon['coupon_id']), 0)
                    mupu = int(coupon.get('max_redemptions_per_user') or 0)
                    if mupu and used_cnt >= mupu:
                        is_valid = False
                        validation_messages.append('Usage limit exceeded for your account')
                        reason_codes.append('usage_limit_per_user')
                except Exception:
                    pass

            # Global usage limit
            try:
                mut = int(coupon.get('max_total_redemptions') or 0)
                cuc = int(coupon.get('current_usage_count') or 0)
                if mut and cuc >= mut:
                    is_valid = False
                    validation_messages.append('Usage limit exceeded')
                    reason_codes.append('usage_limit_total')
            except Exception:
                pass

            # Validity window checks
            try:
                vf = datetime.fromisoformat(coupon['valid_from']) if coupon.get('valid_from') else None
                vt = datetime.fromisoformat(coupon['valid_to']) if coupon.get('valid_to') else None
                
                # Handle timezone-aware vs naive datetime comparisons
                if vf and vf.tzinfo is not None and now_dt.tzinfo is None:
                    vf = vf.replace(tzinfo=None)
                elif vf and vf.tzinfo is None and now_dt.tzinfo is not None:
                    vf = vf.replace(tzinfo=now_dt.tzinfo)
                    
                if vt and vt.tzinfo is not None and now_dt.tzinfo is None:
                    vt = vt.replace(tzinfo=None)
                elif vt and vt.tzinfo is None and now_dt.tzinfo is not None:
                    vt = vt.replace(tzinfo=now_dt.tzinfo)
                
                if vf and now_dt < vf:
                    is_valid = False
                    validation_messages.append(f"Starts on {vf.isoformat()}")
                    reason_codes.append('starts_at')
                if vt and now_dt > vt:
                    is_valid = False
                    validation_messages.append(f"Coupon expired on {vt.date().isoformat()}")
                    reason_codes.append('expired')
                    # Skip vouchers (VCHR-*) that expired more than 48 hours ago
                    try:
                        hours_since_expiry = (now_dt - vt).total_seconds() / 3600
                        if hours_since_expiry > 48 and str(coupon.get('coupon_code', '')).startswith('VCHR-'):
                            continue  # Skip this coupon entirely
                    except Exception as e:
                        logger.warning(f"Error calculating expiry hours for coupon {coupon.get('coupon_code')}: {str(e)}")
            except Exception:
                pass

            # Add to response with validation info
            response_coupon = {
                **coupon,
                'is_eligible': is_valid,
                'validation_messages': validation_messages if not is_valid else None,
                'reason_codes': reason_codes if reason_codes else None,
                'min_cart_value': coupon.get('min_cart_value'),
                'code': coupon.get('coupon_code')
            }
            # Provide primary reason code/message for FE
            if not is_valid and reason_codes:
                rc = reason_codes[0]
                if rc == 'min_cart_value':
                    try:
                        min_val = Decimal(str(coupon.get('min_cart_value') or 0))
                        shortfall = (min_val - cart_value)
                        primary_msg = f"Add ₹{shortfall} more to avail this offer" if shortfall > 0 else f"Minimum order value of ₹{min_val} required"
                    except Exception:
                        primary_msg = 'Minimum cart value not met'
                    response_coupon['reason_code'] = 'MIN_CART_NOT_MET'
                    response_coupon['validation_message'] = primary_msg
                elif rc in ['delivery_only', 'order_type']:
                    response_coupon['reason_code'] = 'ORDER_TYPE_NOT_ALLOWED'
                    response_coupon['validation_message'] = 'Not applicable for this order type'
                elif rc == 'first_order_only':
                    response_coupon['reason_code'] = 'FIRST_ORDER_ONLY'
                    response_coupon['validation_message'] = 'Valid only on your first order'
                elif rc == 'first_order_at_business':
                    response_coupon['reason_code'] = 'FIRST_ORDER_AT_BUSINESS'
                    response_coupon['validation_message'] = 'Valid only on your first order at this business'
                elif rc == 'allowed_business':
                    response_coupon['reason_code'] = 'BUSINESS_NOT_ALLOWED'
                    response_coupon['validation_message'] = 'Coupon not valid for this business'
                elif rc == 'usage_limit_per_user':
                    response_coupon['reason_code'] = 'USAGE_LIMIT_PER_USER'
                    response_coupon['validation_message'] = 'Usage limit exceeded for your account'
                elif rc == 'usage_limit_total':
                    response_coupon['reason_code'] = 'USAGE_LIMIT_TOTAL'
                    response_coupon['validation_message'] = 'Usage limit exceeded'
                elif rc == 'expired':
                    response_coupon['reason_code'] = 'EXPIRED'
                    response_coupon['validation_message'] = 'Coupon expired'
                elif rc == 'starts_at':
                    response_coupon['reason_code'] = 'NOT_STARTED'
                    response_coupon['validation_message'] = 'Coupon not started yet'
                elif rc == 'insufficient_points':
                    response_coupon['reason_code'] = 'INSUFFICIENT_POINTS'
                    response_coupon['validation_message'] = 'Insufficient points to purchase'
                else:
                    response_coupon['reason_code'] = str(rc).upper()
                    response_coupon['validation_message'] = (validation_messages[0] if validation_messages else 'Not eligible')
            
            # Remove rules from main response (unless in debug mode)
            if not debug_mode:
                response_coupon.pop('rules', None)
            
            response_data.append(response_coupon)
        
        # Prepare response
        response = {
            'success': True,
            'data': {
                'user_wallet_balance': float(user_wallet_balance) if user_id else None,
                'available_coupons': response_data,
                'total_available': len(response_data)
            }
        }
        
        # Add debug info if requested
        if debug_mode:
            response['debug'] = debug_info
        
        return Response(response, status=status.HTTP_200_OK)
        
    except Exception as e:
        error_response = {
            'success': False,
            'error': str(e),
            'traceback': traceback.format_exc() if debug_mode else None
        }
        return Response(error_response, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

@swagger_auto_schema(methods=['POST'],tags=['Consumer'])
@api_view(['POST'])
def validate_coupon(request):
    """
    Validate coupon code for specific order context
    """
    try:
        data = request.data
        coupon_code = data.get('coupon_code')
        user_id = data.get('user_id')
        business_id = data.get('business_id')
        cart_value = Decimal(str(data.get('cart_value', 0)))
        order_type = data.get('order_type', 'delivery')
        items = data.get('items', [])
        
        if not all([coupon_code, user_id]):
            return Response({
                'success': False,
                'error': 'coupon_code and user_id are required'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        user = get_object_or_404(Registration, user_id=user_id)
        
        try:
            coupon = Coupons.objects.get(coupon_code=coupon_code, is_active=True)
        except Coupons.DoesNotExist:
            return Response({
                'success': False,
                'error': 'Invalid coupon code'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Enforce business scoping if coupon is business-specific
        if coupon.coupon_scope != 'PLATFORM' and coupon.business_id_id:
            if not business_id or str(coupon.business_id_id) != str(business_id):
                return Response({
                    'success': False,
                    'error': 'Coupon not valid for this business'
                }, status=status.HTTP_400_BAD_REQUEST)
        
        # Check visibility for PRIVATE coupons
        if coupon.visibility_type == 'PRIVATE':
            from .models import CouponUserMapping
            has_mapping_access = CouponUserMapping.objects.filter(
                coupon_id=coupon,
                user_id=user,
                expires_at__gt=timezone.now()
            ).exists()

            if not has_mapping_access:
                # Allow access if targeted by rules (email_domain / allowed_user)
                user_email_domain = None
                try:
                    user_email = (getattr(user, 'emailID', None) or '').strip().lower()
                    if '@' in user_email:
                        user_email_domain = user_email.split('@', 1)[1]
                except Exception:
                    user_email_domain = None

                allow_by_targeting = False
                for r in coupon.rules.filter(is_active=True):
                    try:
                        rtype = str(r.rule_type or '').upper()
                        rv = r.rule_value
                        if rv is not None and not isinstance(rv, (dict, list, bool, int, float)):
                            try:
                                rv = json.loads(rv)
                            except Exception:
                                pass

                        if rtype == 'EMAIL_DOMAIN':
                            allowed_domains = []
                            if isinstance(rv, dict):
                                allowed_domains = rv.get('allowed_domains') or []
                            allowed_domains = [str(d).lower().lstrip('@') for d in allowed_domains if d]
                            if allowed_domains and user_email_domain and user_email_domain.lower() in allowed_domains:
                                allow_by_targeting = True
                                break

                        if rtype == 'ALLOWED_USER':
                            allowed_ids = None
                            if isinstance(rv, dict):
                                if 'user_ids' in rv:
                                    allowed_ids = set([int(x) for x in rv.get('user_ids') or []])
                                elif 'user_id' in rv:
                                    allowed_ids = {int(rv.get('user_id'))}
                            if allowed_ids is not None and int(user_id) in allowed_ids:
                                allow_by_targeting = True
                                break

                        if rtype == 'USER_TAG':
                            allowed_tags = []
                            if isinstance(rv, dict):
                                allowed_tags = rv.get('allowed_tags') or []
                            allowed_tags = [str(t).strip().lower() for t in allowed_tags if t]
                            if allowed_tags:
                                try:
                                    from .models import DomainTagMapping
                                    user_email = (getattr(user, 'emailID', None) or '').strip().lower()
                                    user_domain = user_email.split('@', 1)[1] if '@' in user_email else None
                                    user_tags_set = set()
                                    try:
                                        from .models import UserTags
                                        user_tags_set.update([str(t).strip().lower() for t in UserTags.objects.filter(user_id=user).values_list('tag', flat=True)])
                                    except Exception:
                                        pass
                                    if user_domain:
                                        # Try business-specific mapping first, then fallback to global
                                        business_id = coupon.business_id if coupon else None
                                        mapped_tag = None
                                        
                                        if business_id:
                                            mapped_tag = DomainTagMapping.objects.filter(
                                                domain=user_domain.lower(),
                                                business_id=business_id,
                                                is_active=True
                                            ).values_list('tag', flat=True).first()
                                        
                                        # Fallback to global mapping
                                        if not mapped_tag:
                                            mapped_tag = DomainTagMapping.objects.filter(
                                                domain=user_domain.lower(),
                                                business_id__isnull=True,
                                                is_active=True
                                            ).values_list('tag', flat=True).first()
                                            
                                        mapped_tag = str(mapped_tag).strip().lower() if mapped_tag else None
                                        if mapped_tag:
                                            user_tags_set.add(mapped_tag)

                                    if user_tags_set.intersection(set(allowed_tags)):
                                            allow_by_targeting = True
                                            break
                                except Exception:
                                    pass
                    except Exception:
                        continue

                if not allow_by_targeting:
                    return Response({
                        'success': False,
                        'error': 'Coupon not accessible to this user'
                    }, status=status.HTTP_400_BAD_REQUEST)
        
        # Check redemption limits using new fields
        if coupon.max_total_redemptions:
            total_used = CouponRedemptions.objects.filter(coupon_id=coupon).count()
            if total_used >= coupon.max_total_redemptions:
                return Response({
                    'success': False,
                    'error': 'Coupon has reached maximum usage limit'
                }, status=status.HTTP_400_BAD_REQUEST)
        
        # Check per-user limit
        user_used = CouponRedemptions.objects.filter(coupon_id=coupon, user_id=user).count()
        if user_used >= coupon.max_redemptions_per_user:
            return Response({
                'success': False,
                'error': 'You have reached maximum usage limit for this coupon'
            }, status=status.HTTP_400_BAD_REQUEST)

        # Validate coupon for user
        is_valid, message = coupon.is_valid_for_user(user_id)
        if not is_valid:
            return Response({
                'success': False,
                'error': message
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Evaluate coupon rules
        order_context = {
            'cart_value': float(cart_value),
            'business_id': business_id,
            'order_type': order_type,
            'user_id': user_id
        }

        user_email_domain = None
        try:
            user_email = (getattr(user, 'emailID', None) or '').strip().lower()
            if '@' in user_email:
                user_email_domain = user_email.split('@', 1)[1]
        except Exception:
            user_email_domain = None
        
        rules_satisfied = True
        failed_rules = []
        
        for rule in coupon.rules.filter(is_active=True):
            try:
                rtype = str(rule.rule_type or '').lower()
                rv = rule.rule_value
                if rv is not None and not isinstance(rv, (dict, list, bool, int, float)):
                    try:
                        rv = json.loads(rv)
                    except Exception:
                        pass

                if rtype == 'email_domain':
                    allowed_domains = []
                    if isinstance(rv, dict):
                        allowed_domains = rv.get('allowed_domains') or []
                    allowed_domains = [str(d).lower().lstrip('@') for d in allowed_domains if d]
                    if allowed_domains and (not user_email_domain or user_email_domain.lower() not in allowed_domains):
                        rules_satisfied = False
                        failed_rules.append('email_domain')
                        continue
                    continue

                if rtype == 'order_type':
                    allowed_types = []
                    if isinstance(rv, dict):
                        allowed_types = rv.get('allowed_types') or rv.get('order_types') or rv.get('allowed_order_types') or []
                    if isinstance(allowed_types, list) and allowed_types:
                        incoming = str(order_type or '').lower().replace('-', '_')
                        if incoming == 'dinein':
                            incoming = 'dine_in'
                        norm_allowed = [str(x).lower().replace('-', '_') for x in allowed_types]
                        norm_allowed = ['dine_in' if a == 'dinein' else a for a in norm_allowed]
                        if incoming and incoming not in norm_allowed:
                            rules_satisfied = False
                            failed_rules.append('order_type')
                            continue
                    continue

                if rtype == 'user_tag':
                    allowed_tags = []
                    if isinstance(rv, dict):
                        allowed_tags = rv.get('allowed_tags') or []
                    allowed_tags = [str(t).strip().lower() for t in allowed_tags if t]
                    if allowed_tags:
                        try:
                            from .models import DomainTagMapping
                            user_email = (getattr(user, 'emailID', None) or '').strip().lower()
                            user_domain = user_email.split('@', 1)[1] if '@' in user_email else None
                            user_tags_set = set()
                            try:
                                from .models import UserTags
                                user_tags_set.update([str(t).strip().lower() for t in UserTags.objects.filter(user_id=user).values_list('tag', flat=True)])
                            except Exception:
                                pass

                            mapped_tag = None
                            if user_domain:
                                # Try business-specific mapping first, then fallback to global
                                business_id = coupon.business_id if coupon else None
                                
                                if business_id:
                                    mapped_tag = DomainTagMapping.objects.filter(
                                        domain=user_domain.lower(),
                                        business_id=business_id,
                                        is_active=True
                                    ).values_list('tag', flat=True).first()
                                
                                # Fallback to global mapping
                                if not mapped_tag:
                                    mapped_tag = DomainTagMapping.objects.filter(
                                        domain=user_domain.lower(),
                                        business_id__isnull=True,
                                        is_active=True
                                    ).values_list('tag', flat=True).first()
                                    
                            mapped_tag = str(mapped_tag).strip().lower() if mapped_tag else None
                            if mapped_tag:
                                user_tags_set.add(mapped_tag)
                            if not user_tags_set.intersection(set(allowed_tags)):
                                rules_satisfied = False
                                failed_rules.append('user_tag')
                                continue
                        except Exception:
                            rules_satisfied = False
                            failed_rules.append('user_tag')
                            continue
                    continue

                if not rule.evaluate_rule(order_context):
                    rules_satisfied = False
                    failed_rules.append(rule.rule_type)
            except Exception:
                if not rule.evaluate_rule(order_context):
                    rules_satisfied = False
                    failed_rules.append(rule.rule_type)
        
        if not rules_satisfied:
            return Response({
                'success': False,
                'error': f'Coupon not applicable.{", ".join(failed_rules)}'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Calculate discount amount (supports item-specific coupons)
        discount_amount = Decimal('0.00')
        # Determine if coupon has applicable items
        has_applicable = CouponApplicableItems.objects.filter(coupon=coupon).exists()
        eligible_subtotal = cart_value
        # If items provided and coupon is item-specific, compute eligible subtotal from items
        if has_applicable and items:
            # Load business to determine type for product table mapping
            business = None
            if business_id:
                try:
                    business = Business.objects.get(business_id=business_id)
                except Exception:
                    business = None
            business_type = getattr(business, 'businessType', None)
            # Build mapping set for quick lookup
            app_set = set(CouponApplicableItems.objects.filter(coupon=coupon)
                          .values_list('reference_table', 'reference_id'))
            eligible_subtotal = Decimal('0.00')
            for item in items:
                try:
                    qty = Decimal(str(item.get('quantity', 1)))
                    unit_price = None
                    ref_table = None
                    ref_id = None
                    if 'menu_item_id' in item:
                        ref_table = 'menuItems'
                        ref_id = int(item['menu_item_id'])
                        from business.models import MenuItems as _MI
                        mi = _MI.objects.get(item_id=ref_id)
                        unit_price = Decimal(str(mi.selling_price))
                    elif 'product_item_id' in item:
                        pid = int(item['product_item_id'])
                        if str(business_type).upper() == 'R01':
                            ref_table = 'Groceries_ProductVariants'
                            ref_id = pid
                            from consumer.gro_models import GroceriesProductVariants as _GPV
                            var = _GPV.objects.get(variant_id=pid)
                            unit_price = Decimal(str(var.selling_price or 0))
                        else:
                            ref_table = 'productItems'
                            ref_id = pid
                            from business.models import productItems as _PI
                            pi = _PI.objects.get(item_id=pid)
                            unit_price = Decimal(str(pi.selling_price))
                    if unit_price is not None and (ref_table, ref_id) in app_set:
                        eligible_subtotal += (unit_price * qty)
                except Exception:
                    continue
            if eligible_subtotal <= 0:
                return Response({
                    'success': False,
                    'error': 'Coupon not applicable to selected items'
                }, status=status.HTTP_400_BAD_REQUEST)

        # Compute discount based on eligible_subtotal (or cart_value fallback)
        base_amount = eligible_subtotal
        if coupon.discount_type == 'percentage':
            discount_amount = (base_amount * Decimal(str(coupon.discount_value))) / Decimal('100')
            if discount_amount > base_amount:
                discount_amount = base_amount
        elif coupon.discount_type == 'fixed_amount':
            discount_amount = Decimal(str(coupon.discount_value))
            if discount_amount > base_amount:
                discount_amount = base_amount
        elif coupon.discount_type == 'free_delivery':
            discount_amount = Decimal('30.00')  # Default delivery charge
        elif coupon.discount_type == 'bogo':
            # BOGO: require at least 2 eligible units in cart; discount equals cheapest eligible unit price
            if not items or not isinstance(items, list):
                return Response({
                    'success': False,
                    'error': 'Cart items are required to apply BOGO coupon'
                }, status=status.HTTP_400_BAD_REQUEST)
            # Determine business and mapping
            biz = None
            try:
                if business_id:
                    biz = Business.objects.get(business_id=business_id)
            except Exception:
                biz = None
            biz_type = getattr(biz, 'businessType', None)
            app_set = set()
            if has_applicable:
                try:
                    app_set = set(CouponApplicableItems.objects.filter(coupon=coupon).values_list('reference_table', 'reference_id'))
                except Exception:
                    app_set = set()
            eligible_units = 0
            cheapest = None
            for item in items:
                try:
                    qty = int(item.get('quantity', 1))
                    unit_price = None
                    ref_table = None
                    ref_id = None
                    if 'menu_item_id' in item:
                        ref_table = 'menuItems'
                        ref_id = int(item['menu_item_id'])
                        from business.models import MenuItems as _MI
                        mi = _MI.objects.get(item_id=ref_id)
                        unit_price = Decimal(str(mi.selling_price))
                    elif 'product_item_id' in item:
                        pid = int(item['product_item_id'])
                        if str(biz_type).upper() == 'R01':
                            ref_table = 'Groceries_ProductVariants'
                            ref_id = pid
                            from consumer.gro_models import GroceriesProductVariants as _GPV
                            var = _GPV.objects.get(variant_id=pid)
                            unit_price = Decimal(str(var.selling_price or 0))
                        else:
                            ref_table = 'productItems'
                            ref_id = pid
                            from business.models import productItems as _PI
                            pi = _PI.objects.get(item_id=pid)
                            unit_price = Decimal(str(pi.selling_price))
                    # Eligibility check
                    eligible = True
                    if has_applicable:
                        eligible = (ref_table, ref_id) in app_set
                    if unit_price is not None and eligible:
                        eligible_units += qty
                        if cheapest is None or unit_price < cheapest:
                            cheapest = unit_price
                except Exception:
                    continue
            if eligible_units < 2 or cheapest is None:
                return Response({
                    'success': False,
                    'error': 'BOGO requires at least 2 eligible items in cart'
                }, status=status.HTTP_400_BAD_REQUEST)
            discount_amount = cheapest
        
        return Response({
            'success': True,
            'message': 'Coupon is valid',
            'data': {
                'coupon_id': coupon.coupon_id,
                'coupon_code': coupon.coupon_code,
                'discount_type': coupon.discount_type,
                'discount_value': float(coupon.discount_value),
                'calculated_discount': float(discount_amount),
                'free_delivery': coupon.free_delivery,
                'free_packaging': coupon.free_packaging,
                'valid_until': coupon.valid_to.isoformat()
            }
        }, status=status.HTTP_200_OK)
        
    except Exception as e:
        return Response({
            'success': False,
            'error': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@swagger_auto_schema(methods=['POST'],tags=['Consumer'])
@api_view(['POST'])
def add_wallet_points(request):
    """
    Add points to user's wallet (admin/system use)
    """
    try:
        data = request.data
        user_id = data.get('user_id')
        points_to_add = Decimal(str(data.get('points', 0)))
        transaction_type = data.get('transaction_type', WalletPoints.TransactionType.EARNED)
        description = data.get('description', 'Points added')
        expires_days = int(data.get('expires_days', 365))  # Default 1 year expiry
        
        if not user_id or points_to_add <= 0:
            return Response({
                'success': False,
                'error': 'Invalid user_id or points amount'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        user = get_object_or_404(Registration, user_id=user_id)
        
        # Set expiry date for earned points
        expires_at = None
        if transaction_type == WalletPoints.TransactionType.EARNED:
            if getattr(settings, 'USE_TZ', False):
                expires_at = timezone.now() + timedelta(days=expires_days)
            else:
                expires_at = datetime.now() + timedelta(days=expires_days)
        
        # Add points
        transaction = WalletPoints.atomic_transaction(
            user_id=user,
            points=points_to_add,
            transaction_type=transaction_type,
            description=description,
            expires_at=expires_at
        )
        
        return Response({
            'success': True,
            'message': 'Points added successfully',
            'data': {
                'transaction_id': transaction.wallet_id,
                'points_added': float(points_to_add),
                'new_balance': float(transaction.balance_after),
                'expires_at': expires_at.isoformat() if expires_at else None
            }
        }, status=status.HTTP_201_CREATED)
        
    except Exception as e:
        return Response({
            'success': False,
            'error': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
