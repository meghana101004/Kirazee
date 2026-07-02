from datetime import datetime, timedelta
from django.db import connection
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from django.http import HttpResponse
import csv
import logging
from io import StringIO
import calendar
from dateutil.relativedelta import relativedelta


logger = logging.getLogger(__name__)


def _parse_bool(val, default=False):
    if val is None:
        return default
    if isinstance(val, bool):
        return val
    s = str(val).strip().lower()
    return s in {"1", "true", "yes", "y", "on"}


def _get_date_range(period_type, from_date=None, to_date=None):
    """
    Calculate date range based on period type
    period_type: daily, weekly, monthly, quarterly, half_yearly, yearly, custom
    """
    now = datetime.now()
    
    if period_type == 'custom' and from_date and to_date:
        start = datetime.strptime(from_date, '%Y-%m-%d').replace(hour=0, minute=0, second=0, microsecond=0)
        end = datetime.strptime(to_date, '%Y-%m-%d').replace(hour=23, minute=59, second=59, microsecond=999999)
        return start, end
    
    if period_type == 'daily':
        start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        end = now.replace(hour=23, minute=59, second=59, microsecond=999999)
    
    elif period_type == 'weekly':
        start = now - timedelta(days=now.weekday())
        start = start.replace(hour=0, minute=0, second=0, microsecond=0)
        end = start + timedelta(days=7) - timedelta(microseconds=1)
    
    elif period_type == 'monthly':
        # For monthly, get the entire month data
        start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        last_day = calendar.monthrange(start.year, start.month)[1]
        end = start.replace(day=last_day, hour=23, minute=59, second=59, microsecond=999999)
    
    elif period_type == 'quarterly':
        quarter = (now.month - 1) // 3 + 1
        start_month = (quarter - 1) * 3 + 1
        start = now.replace(month=start_month, day=1, hour=0, minute=0, second=0, microsecond=0)
        end = start + relativedelta(months=3) - timedelta(microseconds=1)
    
    elif period_type == 'half_yearly':
        half_year = 1 if now.month <= 6 else 2
        start_month = 1 if half_year == 1 else 7
        start = now.replace(month=start_month, day=1, hour=0, minute=0, second=0, microsecond=0)
        end = start + relativedelta(months=6) - timedelta(microseconds=1)
    
    elif period_type == 'yearly':
        start = now.replace(month=1, day=1, hour=0, minute=0, second=0, microsecond=0)
        end = start.replace(month=12, day=31, hour=23, minute=59, second=59, microsecond=999999)
    
    else:
        # Default to today
        start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        end = start + timedelta(days=1) - timedelta(microseconds=1)
    
    return start, end


class PaymentDetailReportView(APIView):
    """
    Comprehensive sale report with detailed order-wise breakdown including GST, charges, and deductions
    
    GET /api/v1/management/reports/payment-details/
    
    Query Parameters:
    - business_id: required
    - period_type: daily|weekly|monthly|quarterly|half_yearly|yearly|custom
    - from_date: YYYY-MM-DD (required for custom period)
    - to_date: YYYY-MM-DD (required for custom period)
    - include_branches: true/false (default: true for master businesses)
    - view_mode: basic|detailed (default: detailed)
    
    Response Modes:
    - basic: Clean columns for UI (sale_date, order_id, source, item_name, quantity, unit_price, 
            item_subtotal, gst_percent, gst_amount, discount_applied, total_order_amount, 
            payment_method, payment_status, order_type)
    - detailed: All columns including charges breakdown (for Excel export/audit)
    
    Response includes:
    - Item-wise sale details with GST calculations
    - Delivery, parcel, and customization charges
    - Discount applied and final order totals
    - Payment method and status breakdown
    - Customer mobile and service type information
    """
    
    permission_classes = []
    
    def get(self, request):
        try:
            # Get query parameters
            business_id = request.query_params.get('business_id')
            period_type = request.query_params.get('period_type', 'daily')
            from_date = request.query_params.get('from_date')
            to_date = request.query_params.get('to_date')
            include_branches_param = request.query_params.get('include_branches')
            view_mode = request.query_params.get('view_mode', 'detailed').lower()
            export_format = request.query_params.get('export_format', 'json').lower()
            
            if not business_id:
                return Response({
                    'success': False,
                    'message': 'business_id is required'
                }, status=status.HTTP_400_BAD_REQUEST)
            
            if period_type == 'custom' and (not from_date or not to_date):
                return Response({
                    'success': False,
                    'message': 'from_date and to_date are required for custom period'
                }, status=status.HTTP_400_BAD_REQUEST)
            
            if view_mode not in ['basic', 'detailed']:
                return Response({
                    'success': False,
                    'message': 'view_mode must be basic or detailed'
                }, status=status.HTTP_400_BAD_REQUEST)
            
            # Get date range
            start_date, end_date = _get_date_range(period_type, from_date, to_date)
            
            with connection.cursor() as cursor:
                # Get business scope
                cursor.execute("""
                    SELECT business_id, businessName, level, master 
                    FROM businesses 
                    WHERE business_id = %s
                    LIMIT 1
                """, [business_id])
                
                business_row = cursor.fetchone()
                if not business_row:
                    return Response({
                        'success': False,
                        'message': f'Business {business_id} not found'
                    }, status=status.HTTP_404_NOT_FOUND)
                
                base_business_id, base_business_name, base_level, base_master = business_row
                is_master = str(base_level).strip().lower() == "master"
                
                # Get included business IDs
                included_business_ids = [base_business_id]
                include_branches = _parse_bool(include_branches_param, default=is_master)
                
                if include_branches:
                    cursor.execute("""
                        SELECT business_id 
                        FROM businesses 
                        WHERE master = %s
                    """, [base_business_id])
                    branch_rows = cursor.fetchall() or []
                    included_business_ids.extend([r[0] for r in branch_rows])
                
                ids_sql, ids_params = self._build_in_clause(included_business_ids)
                
                # Get payment details from all sources
                payment_details = self._get_payment_details(cursor, ids_sql, ids_params, start_date, end_date)
                
                # Generate summary
                summary = self._generate_summary(payment_details)
                
                # Filter payment details based on view_mode
                if view_mode == 'basic':
                    payment_details = self._filter_basic_view(payment_details)
                
                # Prepare response data
                response_data = {
                    'success': True,
                    'message': 'Payment detail report retrieved successfully',
                    'metadata': {
                        'business_id': business_id,
                        'business_name': base_business_name,
                        'period_type': period_type,
                        'start_date': start_date.strftime('%d %b %Y'),
                        'end_date': end_date.strftime('%d %b %Y'),
                        'included_business_ids': included_business_ids,
                        'view_mode': view_mode,
                    'total_orders': len(payment_details)
                    },
                    'summary': summary,
                    'payment_details': payment_details
                }
                
                # Handle export
                if export_format == 'csv':
                    return self._export_csv(response_data, f'payment_details_{business_id}_{period_type}.csv')
                
                return Response(response_data, status=status.HTTP_200_OK)
                
        except Exception as e:
            logger.error(f"Error in payment detail report: {str(e)}")
            return Response({
                'success': False,
                'message': f'Error generating report: {str(e)}'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    
    def _build_in_clause(self, values):
        """Return a tuple: (placeholders_sql, params_list). Ensures at least one placeholder."""
        if not values:
            return "%s", ["__NONE__"]
        return ",".join(["%s"] * len(values)), list(values)
    
    def _get_payment_details(self, cursor, ids_sql, ids_params, start_date, end_date):
        """Get comprehensive item-wise sale report details using unified SQL query"""
        payment_details = []  # Initialize immediately
        
        try:
            # Build business IDs string for IN clause safely
            business_ids_str = ','.join([f"'{bid}'" for bid in ids_params])
            
            # 1. ONLINE ORDERS
            online_query = f"""
                SELECT
                    o.created_at as sale_date,
                    o.order_id,
                    COALESCE(o.order_number, '') as token_id,
                    'ONLINE' as source,
                    oi.item_name_snapshot as item_name,
                    oi.unit_price_snapshot as unit_price,
                    oi.quantity as quantity,
                    ROUND(oi.unit_price_snapshot * oi.quantity, 2) as item_subtotal,
                    CONCAT(ROUND((oi.gst_amount / NULLIF((oi.total_price - oi.gst_amount), 0)) * 100), '%%') as gst_percent,
                    oi.gst_amount as gst_amount,
                    COALESCE(o.delivery_charges, 0.00) as delivery_charges,
                    COALESCE(o.parcel_charges, 0.00) as parcel_charges,
                    0.00 as customization_charges,
                    COALESCE(o.discount_amount, 0.00) as discount_applied,
                    o.final_amount as total_order_amount,
                    COALESCE(p.payment_method, 'ONLINE') as payment_method,
                    COALESCE(p.payment_source, 'other') as platform,
                    o.status as payment_status,
                    IFNULL(r.mobileNumber, 'skipped') as customer_mobile,
                    CONCAT(r.firstName, ' ', r.lastName) as customer_name,
                    r.emailID as customer_email,
                    o.order_type as raw_order_type
                FROM orders o
                JOIN order_items oi ON o.order_id = oi.order_id
                LEFT JOIN registrations r ON r.user_id = o.user_id
                LEFT JOIN payments p ON p.order_id = o.order_id
                WHERE o.business_id IN ({business_ids_str})
                  AND o.status NOT IN ('cancelled', 'rejected', 'pending')
                  AND o.created_at BETWEEN %s AND %s
                ORDER BY o.created_at DESC
            """
            
            cursor.execute(online_query, [start_date, end_date])
            online_rows = cursor.fetchall()
            
            # 2. COUNTER ORDERS
            counter_query = f"""
                SELECT
                    bco.created_at as sale_date,
                    bco.order_id,
                    COALESCE(bco.token_number, '') as token_id,
                    'COUNTER' as source,
                    bci.item_name as item_name,
                    bci.unit_price as unit_price,
                    bci.quantity as quantity,
                    ROUND(bci.unit_price * bci.quantity, 2) as item_subtotal,
                    CONCAT(ROUND((bci.gst / NULLIF((bci.line_total - bci.gst), 0)) * 100), '%%') as gst_percent,
                    bci.gst as gst_amount,
                    COALESCE(bco.delivery_charges, 0.00) as delivery_charges,
                    0.00 as parcel_charges,
                    COALESCE(bco.customization_charges, 0.00) as customization_charges,
                    COALESCE(bco.discount_amount, 0.00) as discount_applied,
                    bco.total_amount as total_order_amount,
                    COALESCE(p.payment_method, COALESCE(bco.payment_method, 'other')) as payment_method,
                    'POS' as platform,
                    bco.status as payment_status,
                    IFNULL(bco.customer_mobile, 'skipped') as customer_mobile,
                    bco.username as customer_name,
                    bco.customer_email as customer_email,
                    bco.service_mode as raw_order_type
                FROM business_counter_orders bco
                JOIN business_counter_items bci ON bco.order_id = bci.order_id
                LEFT JOIN payments p ON p.order_id = bco.order_id
                WHERE bco.business_id IN ({business_ids_str})
                  AND bco.status NOT IN ('cancelled', 'pending')
                  AND bco.created_at BETWEEN %s AND %s
                ORDER BY bco.created_at DESC
            """
            
            cursor.execute(counter_query, [start_date, end_date])
            counter_rows = cursor.fetchall()
            
            # Combine all rows
            all_rows = list(online_rows) + list(counter_rows)
            
            # Sort by date (first column) descending
            all_rows.sort(key=lambda x: x[0] if x[0] else '', reverse=True)
            
            # Map rows to payment_details structure with all required fields
            for row in all_rows:
                # Ensure row has enough columns
                if len(row) < 22:
                    logger.warning(f"Row has insufficient columns: {len(row)}, expected 22. Skipping row.")
                    continue
                    
                raw_order_type = row[21]
                payment_details.append({
                    # Core sale report fields
                    'sale_date': row[0].strftime('%Y-%m-%d %H:%M:%S') if row[0] else None,
                    'order_id': row[1],
                    'token_id': row[2] if row[2] else '',
                    'source': row[3],
                    'item_name': row[4],
                    'unit_price': float(row[5]) if row[5] else 0.0,
                    'quantity': int(row[6]) if row[6] else 0,
                    'item_subtotal': float(row[7]) if row[7] else 0.0,
                    'gst_percent': row[8],
                    'gst_amount': float(row[9]) if row[9] else 0.0,
                    'delivery_charges': float(row[10]) if row[10] else 0.0,
                    'parcel_charges': float(row[11]) if row[11] else 0.0,
                    'customization_charges': float(row[12]) if row[12] else 0.0,
                    'discount_applied': float(row[13]) if row[13] else 0.0,
                    'total_order_amount': float(row[14]) if row[14] else 0.0,
                    'payment_method': self._normalize_payment_method(row[15]),
                    'platform': self._normalize_platform(row[16]),
                    'payment_status': row[17],
                    'customer_mobile': row[18],
                    'customer_name': row[19] if row[19] else '',
                    'customer_email': row[20] if row[20] else '',
                    'order_type': self._normalize_order_type(raw_order_type),
                })
            
            return payment_details
            
        except Exception as e:
            logger.error(f"Error in _get_payment_details: {str(e)}")
            # Return empty list on error to prevent further issues
            return payment_details
    
    def _normalize_payment_method(self, payment_method):
        """Normalize payment method to standard values"""
        if not payment_method:
            return 'other'
        method = str(payment_method).lower().strip()
        # Map to standard values
        if method in ['upi']:
            return 'upi'
        elif method in ['cash', 'cod']:
            return 'cash'
        elif method in ['wallet']:
            return 'wallet'
        elif method in ['razorpay', 'razorpay_online', 'online_razorpay', 'online']:
            return 'razorpay'
        elif method in ['icici']:
            return 'icici'
        else:
            return 'other'
    
    def _normalize_platform(self, platform):
        """Normalize platform to standard values"""
        if not platform:
            return 'other'
        plat = str(platform).lower().strip()
        if plat in ['web', 'website']:
            return 'web'
        elif plat in ['android', 'android app']:
            return 'android app'
        elif plat in ['ios', 'ios app', 'iphone']:
            return 'ios app'
        elif plat in ['app']:
            return 'app'
        else:
            return 'other'
    
    def _normalize_order_type(self, order_type):
        """Normalize order type to standard values"""
        if not order_type:
            return 'other'
        ot = str(order_type).lower().strip().replace('_', '-').replace(' ', '-')
        # Map to standard values
        if ot in ['dine-in', 'dinein', 'dine_in', 'dining', 'eat-in']:
            return 'Dine-In'
        elif ot in ['takeaway', 'take-away', 'take_out', 'takeout']:
            return 'Takeaway'
        elif ot in ['pick-up', 'pickup', 'pick_up', 'pick']:
            return 'Pick up'
        elif ot in ['delivery', 'home-delivery', 'home_delivery', 'shipping']:
            return 'Delivery'
        elif ot in ['counter', 'pos']:
            return 'Dine-In'  # Counter orders default to Dine-In
        else:
            return 'Other'
    
    def _categorize_payment_method(self, payment_method, source_type):
        """Categorize payment method for summary bucketing (internal use)"""
        if not payment_method:
            return 'Other'
        
        method = str(payment_method).lower().strip()
        
        if source_type == 'counter':
            # Counter orders: cash, upi, card
            if method in ['cash']:
                return 'cash'
            elif method in ['upi']:
                return 'upi'
            elif method in ['card', 'credit_card', 'debit_card']:
                return 'card'
            elif method in ['razorpay', 'razorpay_online']:
                return 'online_razorpay'
            else:
                return 'other'
        else:
            # Online orders: online_razorpay, wallet
            if method in ['razorpay', 'razorpay_online', 'online_razorpay']:
                return 'online_razorpay'
            elif method in ['wallet']:
                return 'wallet'
            elif method in ['cash', 'cod']:
                return 'cash'
            elif method in ['upi']:
                return 'upi'
            elif method in ['card', 'credit_card', 'debit_card']:
                return 'card'
            else:
                return 'other'
    
    def _filter_basic_view(self, payment_details):
        """Filter payment details to show only essential columns for clean UI"""
        basic_fields = [
            'sale_date', 'order_id', 'source', 'item_name', 'quantity',
            'unit_price', 'item_subtotal', 'gst_percent', 'gst_amount',
            'discount_applied', 'total_order_amount', 'payment_method',
            'payment_status', 'order_type', 'customer_name', 'customer_email'
        ]
        filtered = []
        for payment in payment_details:
            filtered.append({k: payment.get(k) for k in basic_fields})
        return filtered
    
    def _generate_summary(self, payment_details):
        """Generate summary statistics"""
        summary = {
            'grand_total': 0.0,
            'total_orders': len(payment_details),
            'payment_methods_breakdown': {},
            'source_breakdown': {
                'counter_orders': {'count': 0, 'amount': 0.0},
                'online_orders': {'count': 0, 'amount': 0.0}
            },
            'platform_breakdown': {},
            'status_breakdown': {
                'success': {'count': 0, 'amount': 0.0},
                'pending': {'count': 0, 'amount': 0.0},
                'failed': {'count': 0, 'amount': 0.0},
                'cancelled': {'count': 0, 'amount': 0.0},
                'paid': {'count': 0, 'amount': 0.0},
                'other': {'count': 0, 'amount': 0.0}
            }
        }
        
        for payment in payment_details:
            amount = payment['total_order_amount']
            method = payment.get('source_category', 'other')
            status = payment['payment_status']
            platform = payment['platform']
            source = payment['source']
            
            # Grand total
            summary['grand_total'] += amount
            
            # Payment method breakdown (use normalized payment_method for summary)
            normalized_method = payment.get('payment_method', 'other')
            if normalized_method not in summary['payment_methods_breakdown']:
                summary['payment_methods_breakdown'][normalized_method] = {'count': 0, 'amount': 0.0}
            summary['payment_methods_breakdown'][normalized_method]['count'] += 1
            summary['payment_methods_breakdown'][normalized_method]['amount'] += amount
            
            # Source breakdown (counter vs online)
            if source == 'COUNTER':
                summary['source_breakdown']['counter_orders']['count'] += 1
                summary['source_breakdown']['counter_orders']['amount'] += amount
            else:
                summary['source_breakdown']['online_orders']['count'] += 1
                summary['source_breakdown']['online_orders']['amount'] += amount
            
            # Platform breakdown
            if platform not in summary['platform_breakdown']:
                summary['platform_breakdown'][platform] = {'count': 0, 'amount': 0.0}
            summary['platform_breakdown'][platform]['count'] += 1
            summary['platform_breakdown'][platform]['amount'] += amount
            
            # Status breakdown
            status_key = status.lower() if status else 'unknown'
            if status_key not in summary['status_breakdown']:
                status_key = 'other'
            summary['status_breakdown'][status_key]['count'] += 1
            summary['status_breakdown'][status_key]['amount'] += amount
        
        return summary
    
    def _export_csv(self, data, filename):
        """Export data to CSV format with professional formatting"""
        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = f'attachment; filename="{filename}"'
        
        writer = csv.writer(response)
        
        # Add BOM for proper UTF-8 encoding in Excel
        response.write('\ufeff')
        
        # Write main title with emphasis
        writer.writerow(['PAYMENT DETAIL REPORT'])
        writer.writerow(['ORDER-WISE BREAKDOWN'])
        writer.writerow([])
        
        # Business information with emphasized headers
        writer.writerow(['BUSINESS INFORMATION'])
        writer.writerow(['Business Name:', data['metadata']['business_name']])
        writer.writerow(['Period:', data['metadata']['period_type'].upper()])
        writer.writerow(['Date Range:', f"{data['metadata']['start_date']} to {data['metadata']['end_date']}"])
        writer.writerow(['Total Orders:', data['metadata']['total_orders']])
        writer.writerow(['Grand Total:', f"{data['summary']['grand_total']:,.2f}"])
        writer.writerow([])
        
        # Payment methods summary with emphasized headers
        writer.writerow(['PAYMENT METHODS SUMMARY'])
        writer.writerow(['Payment Method', 'Order Count', 'Total Amount', 'Percentage'])
        for method, stats in data['summary']['payment_methods_breakdown'].items():
            if stats['count'] > 0:
                percentage = (stats['amount'] / data['summary']['grand_total'] * 100) if data['summary']['grand_total'] > 0 else 0
                writer.writerow([method.title(), stats['count'], f"{stats['amount']:,.2f}", f"{percentage:.1f}%"])
        writer.writerow([])
        
        # Source breakdown with emphasized headers
        writer.writerow(['SOURCE BREAKDOWN'])
        writer.writerow(['Source', 'Order Count', 'Total Amount'])
        for source, stats in data['summary']['source_breakdown'].items():
            if stats['count'] > 0:
                writer.writerow([source.replace('_', ' ').title(), stats['count'], f"{stats['amount']:,.2f}"])
        writer.writerow([])
        
        # Platform breakdown with emphasized headers
        writer.writerow(['PLATFORM BREAKDOWN'])
        writer.writerow(['Platform', 'Order Count', 'Total Amount'])
        for platform, stats in data['summary']['platform_breakdown'].items():
            if stats['count'] > 0:
                writer.writerow([platform, stats['count'], f"{stats['amount']:,.2f}"])
        writer.writerow([])
        
        # Order-wise details with emphasized headers - adapt to view_mode
        view_mode = data['metadata'].get('view_mode', 'detailed')
        
        if view_mode == 'basic':
            writer.writerow(['SALE REPORT - BASIC VIEW'])
            writer.writerow([
                'Sale Date', 'Order ID', 'Source', 'Item Name', 'Unit Price', 'Quantity', 
                'Item Subtotal (Excl. Tax)', 'GST %', 'GST Amount', 'Discount Applied', 
                'Total Order Amount', 'Payment Method', 'Payment Status', 'Order Type',
                'Customer Name', 'Customer Email'
            ])
            
            # Write each order details - basic columns only
            for payment in data['payment_details']:
                writer.writerow([
                    payment.get('sale_date', ''),
                    payment['order_id'],
                    payment.get('source', ''),
                    payment.get('item_name', ''),
                    f"{payment.get('unit_price', 0):,.2f}",
                    payment.get('quantity', 0),
                    f"{payment.get('item_subtotal', 0):,.2f}",
                    payment.get('gst_percent', ''),
                    f"{payment.get('gst_amount', 0):,.2f}",
                    f"{payment.get('discount_applied', 0):,.2f}",
                    f"{payment.get('total_order_amount', 0):,.2f}",
                    payment.get('payment_method', ''),
                    payment.get('payment_status', ''),
                    payment.get('order_type', ''),
                    payment.get('customer_name', ''),
                    payment.get('customer_email', '')
                ])
        else:
            writer.writerow(['SALE REPORT - DETAILED VIEW'])
            writer.writerow([
                'Sale Date', 'Order ID', 'Token ID', 'Source', 'Item Name', 'Unit Price', 'Quantity', 
                'Item Subtotal (Excl. Tax)', 'GST %', 'GST Amount', 'Delivery Charges', 
                'Parcel Charges', 'Customization Charges', 'Discount Applied', 
                'Total Order Amount', 'Payment Method', 'Platform', 'Payment Status', 
                'Customer Mobile', 'Customer Name', 'Customer Email', 'Order Type'
            ])
            
            # Write each order details - all columns
            for payment in data['payment_details']:
                writer.writerow([
                    payment.get('sale_date', ''),
                    payment['order_id'],
                    payment.get('token_id', ''),
                    payment.get('source', ''),
                    payment.get('item_name', ''),
                    f"{payment.get('unit_price', 0):,.2f}",
                    payment.get('quantity', 0),
                    f"{payment.get('item_subtotal', 0):,.2f}",
                    payment.get('gst_percent', ''),
                    f"{payment.get('gst_amount', 0):,.2f}",
                    f"{payment.get('delivery_charges', 0):,.2f}",
                    f"{payment.get('parcel_charges', 0):,.2f}",
                    f"{payment.get('customization_charges', 0):,.2f}",
                    f"{payment.get('discount_applied', 0):,.2f}",
                    f"{payment.get('total_order_amount', 0):,.2f}",
                    payment.get('payment_method', ''),
                    payment.get('platform', ''),
                    payment.get('payment_status', ''),
                    payment.get('customer_mobile', ''),
                    payment.get('customer_name', ''),
                    payment.get('customer_email', ''),
                    payment.get('order_type', '')
                ])
        
        return response
