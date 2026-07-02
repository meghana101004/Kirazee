from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from django.http import HttpResponse
from django.utils import timezone
from django.db import connection
from datetime import datetime, timedelta
import csv
import logging
from io import StringIO

# Optional pandas import for Excel export
try:
    import pandas as pd
    PANDAS_AVAILABLE = True
except ImportError:
    PANDAS_AVAILABLE = False
    pd = None

logger = logging.getLogger(__name__)

class OrderExportView(APIView):
    """
    Export orders data to Excel/CSV format
    GET /api/v1/admin/export/orders/
    Query parameters:
    - start_date: YYYY-MM-DD (default: 30 days ago)
    - end_date: YYYY-MM-DD (default: today)
    - format: csv or excel (default: csv)
    - status: filter by order status (optional)
    - business_id: filter by business (optional)
    """
    permission_classes = []  # Remove authentication for testing
    
    def get(self, request):
        """Export orders data"""
        try:
            # Get query parameters
            start_date_str = request.query_params.get('start_date')
            end_date_str = request.query_params.get('end_date')
            export_format = request.query_params.get('format', 'csv').lower()
            order_status = request.query_params.get('status')
            business_id = request.query_params.get('business_id')
            
            # Validate format
            if export_format not in ['csv', 'excel']:
                return Response({
                    'success': False,
                    'message': 'Invalid format. Use csv or excel',
                    'data': None
                }, status=status.HTTP_400_BAD_REQUEST)
            
            # Parse dates
            if start_date_str:
                try:
                    start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date()
                except ValueError:
                    return Response({
                        'success': False,
                        'message': 'Invalid start_date format. Use YYYY-MM-DD',
                        'data': None
                    }, status=status.HTTP_400_BAD_REQUEST)
            else:
                start_date = (timezone.now() - timedelta(days=30)).date()
            
            if end_date_str:
                try:
                    end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date()
                except ValueError:
                    return Response({
                        'success': False,
                        'message': 'Invalid end_date format. Use YYYY-MM-DD',
                        'data': None
                    }, status=status.HTTP_400_BAD_REQUEST)
            else:
                end_date = timezone.now().date()
            
            # Validate date range
            if start_date > end_date:
                return Response({
                    'success': False,
                    'message': 'start_date must be before end_date',
                    'data': None
                }, status=status.HTTP_400_BAD_REQUEST)
            
            # Limit date range to prevent memory issues
            if (end_date - start_date).days > 365:
                return Response({
                    'success': False,
                    'message': 'Date range cannot exceed 365 days',
                    'data': None
                }, status=status.HTTP_400_BAD_REQUEST)
            
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
                
                # Build WHERE conditions
                where_conditions = [
                    f"DATE(o.created_at) >= '{start_date}'",
                    f"DATE(o.created_at) <= '{end_date}'"
                ]
                
                if order_status:
                    where_conditions.append(f"o.status = '{order_status}'")
                
                if business_id:
                    where_conditions.append(f"o.business_id = '{business_id}'")
                
                where_clause = " AND ".join(where_conditions)
                
                # Query orders data
                cursor.execute(f"""
                    SELECT 
                        o.order_id,
                        o.order_number,
                        o.business_id,
                        COALESCE(b.businessName, 'Unknown') as business_name,
                        o.user_id,
                        COALESCE(CONCAT(r.firstName, ' ', COALESCE(r.lastName, '')), 'Unknown') as customer_name,
                        COALESCE(r.emailID, '') as customer_email,
                        COALESCE(r.mobileNumber, '') as customer_phone,
                        o.order_type,
                        o.status,
                        o.total_amount,
                        o.final_amount,
                        o.payment_method,
                        o.payment_status,
                        o.delivery_address,
                        o.created_at,
                        o.updated_at,
                        CASE 
                            WHEN o.status IN ('delivered', 'completed') THEN o.updated_at
                            WHEN o.status = 'cancelled' THEN o.updated_at
                            ELSE NULL
                        END as completed_at,
                        COALESCE(dp.id, NULL) as assigned_driver_id,
                        COALESCE(CONCAT(dp.firstName, ' ', COALESCE(dp.lastName, '')), 'Unassigned') as driver_name
                    FROM orders o
                    LEFT JOIN businesses b ON CONVERT(o.business_id USING {detected_charset}) COLLATE {detected_collation} = CONVERT(b.business_id USING {detected_charset}) COLLATE {detected_collation}
                    LEFT JOIN registrations r ON o.user_id = r.user_id
                    LEFT JOIN delivery_partners dp ON o.assigned_driver_id = dp.id
                    WHERE {where_clause}
                    ORDER BY o.created_at DESC
                    LIMIT 10000
                """)
                
                results = cursor.fetchall()
                
                if not results:
                    return Response({
                        'success': False,
                        'message': 'No orders found for the specified criteria',
                        'data': None
                    }, status=status.HTTP_404_NOT_FOUND)
                
                # Prepare data for export
                headers = [
                    'Order ID', 'Order Number', 'Business ID', 'Business Name',
                    'Customer ID', 'Customer Name', 'Customer Email', 'Customer Phone',
                    'Order Type', 'Status', 'Total Amount', 'Final Amount',
                    'Payment Method', 'Payment Status', 'Delivery Address',
                    'Created At', 'Updated At', 'Completed At',
                    'Driver ID', 'Driver Name'
                ]
                
                # Format data rows
                data_rows = []
                for row in results:
                    formatted_row = [
                        row[0],  # Order ID
                        row[1],  # Order Number
                        row[2],  # Business ID
                        row[3],  # Business Name
                        row[4],  # Customer ID
                        row[5],  # Customer Name
                        row[6],  # Customer Email
                        row[7],  # Customer Phone
                        row[8],  # Order Type
                        row[9],  # Status
                        float(row[10]) if row[10] else 0,  # Total Amount
                        float(row[11]) if row[11] else 0,  # Final Amount
                        row[12],  # Payment Method
                        row[13],  # Payment Status
                        row[14],  # Delivery Address
                        row[15].strftime('%Y-%m-%d %H:%M:%S') if row[15] else '',  # Created At
                        row[16].strftime('%Y-%m-%d %H:%M:%S') if row[16] else '',  # Updated At
                        row[17].strftime('%Y-%m-%d %H:%M:%S') if row[17] else '',  # Completed At
                        row[18],  # Driver ID
                        row[19],  # Driver Name
                    ]
                    data_rows.append(formatted_row)
                
                # Generate filename
                filename = f"orders_export_{start_date}_to_{end_date}"
                
                if export_format == 'excel' and PANDAS_AVAILABLE:
                    return self._generate_excel_export(headers, data_rows, filename)
                else:
                    if export_format == 'excel' and not PANDAS_AVAILABLE:
                        logger.warning("pandas not available, falling back to CSV")
                    return self._generate_csv_export(headers, data_rows, filename)
                
        except Exception as e:
            logger.error(f"Error exporting orders: {str(e)}")
            return Response({
                'success': False,
                'message': f'Error exporting orders: {str(e)}',
                'data': None
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    
    def _generate_csv_export(self, headers, data_rows, filename):
        """Generate CSV export"""
        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = f'attachment; filename="{filename}.csv"'
        
        writer = csv.writer(response)
        writer.writerow(headers)
        writer.writerows(data_rows)
        
        return response
    
    def _generate_excel_export(self, headers, data_rows, filename):
        """Generate Excel export using pandas"""
        if not PANDAS_AVAILABLE:
            return self._generate_csv_export(headers, data_rows, filename)
            
        try:
            # Create DataFrame
            df = pd.DataFrame(data_rows, columns=headers)
            
            # Create Excel file in memory
            output = StringIO()
            with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                df.to_excel(writer, sheet_name='Orders', index=False)
                
                # Get workbook and worksheet for formatting
                workbook = writer.book
                worksheet = writer.sheets['Orders']
                
                # Add formatting
                header_format = workbook.add_format({
                    'bold': True,
                    'text_wrap': True,
                    'valign': 'top',
                    'fg_color': '#D7E4BC',
                    'border': 1
                })
                
                # Apply header formatting
                for col_num, value in enumerate(df.columns.values):
                    worksheet.write(0, col_num, value, header_format)
                
                # Auto-adjust column widths
                for i, col in enumerate(df.columns):
                    max_len = max(
                        df[col].astype(str).map(len).max(),
                        len(str(col))
                    )
                    worksheet.set_column(i, i, min(max_len + 2, 50))
            
            # Prepare response
            response = HttpResponse(
                output.getvalue(),
                content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
            )
            response['Content-Disposition'] = f'attachment; filename="{filename}.xlsx"'
            
            return response
            
        except ImportError:
            # Fallback to CSV if pandas/openpyxl not available
            logger.warning("pandas or xlsxwriter not available, falling back to CSV")
            return self._generate_csv_export(headers, data_rows, filename)


class BusinessExportView(APIView):
    """
    Export business performance data to Excel/CSV format
    GET /api/v1/admin/export/businesses/
    """
    permission_classes = []
    
    def get(self, request):
        """Export business performance data"""
        try:
            # Get query parameters
            export_format = request.query_params.get('format', 'csv').lower()
            
            if export_format not in ['csv', 'excel']:
                return Response({
                    'success': False,
                    'message': 'Invalid format. Use csv or excel',
                    'data': None
                }, status=status.HTTP_400_BAD_REQUEST)
            
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
                
                # Query business performance data
                cursor.execute(f"""
                    SELECT 
                        b.business_id,
                        b.businessName,
                        b.businessCategory,
                        b.businessType,
                        b.status,
                        b.paymentstatus,
                        b.city,
                        b.state,
                        COUNT(DISTINCT o.order_id) as total_orders,
                        COALESCE(SUM(o.final_amount), 0) as total_revenue,
                        COALESCE(AVG(o.final_amount), 0) as avg_order_value,
                        COUNT(DISTINCT CASE WHEN o.status IN ('delivered', 'completed') THEN o.order_id END) as completed_orders,
                        COUNT(DISTINCT CASE WHEN o.status = 'cancelled' THEN o.order_id END) as cancelled_orders,
                        CASE 
                            WHEN COUNT(DISTINCT o.order_id) > 0 
                            THEN ROUND(COUNT(DISTINCT CASE WHEN o.status IN ('delivered', 'completed') THEN o.order_id END) * 100.0 / COUNT(DISTINCT o.order_id), 2)
                            ELSE 0 
                        END as completion_rate,
                        b.created_at as business_created_at
                    FROM businesses b
                    LEFT JOIN orders o ON CONVERT(b.business_id USING {detected_charset}) COLLATE {detected_collation} = CONVERT(o.business_id USING {detected_charset}) COLLATE {detected_collation}
                    GROUP BY b.business_id, b.businessName, b.businessCategory, b.businessType, b.status, b.paymentstatus, b.city, b.state, b.created_at
                    ORDER BY total_revenue DESC
                """)
                
                results = cursor.fetchall()
                
                # Prepare data for export
                headers = [
                    'Business ID', 'Business Name', 'Category', 'Business Type',
                    'Status', 'Payment Status', 'City', 'State',
                    'Total Orders', 'Total Revenue', 'Average Order Value',
                    'Completed Orders', 'Cancelled Orders', 'Completion Rate (%)',
                    'Business Created At'
                ]
                
                data_rows = []
                for row in results:
                    formatted_row = [
                        row[0],  # Business ID
                        row[1],  # Business Name
                        row[2],  # Category
                        row[3],  # Business Type
                        'Active' if row[4] == 1 else 'Inactive',  # Status
                        'Paid' if row[5] == 1 else 'Unpaid',  # Payment Status
                        row[6],  # City
                        row[7],  # State
                        row[8],  # Total Orders
                        float(row[9]) if row[9] else 0,  # Total Revenue
                        float(row[10]) if row[10] else 0,  # Average Order Value
                        row[11],  # Completed Orders
                        row[12],  # Cancelled Orders
                        float(row[13]) if row[13] else 0,  # Completion Rate
                        row[14].strftime('%Y-%m-%d %H:%M:%S') if row[14] else '',  # Business Created At
                    ]
                    data_rows.append(formatted_row)
                
                # Generate filename
                filename = f"business_performance_export_{timezone.now().strftime('%Y-%m-%d')}"
                
                if export_format == 'excel' and PANDAS_AVAILABLE:
                    return OrderExportView._generate_excel_export(None, headers, data_rows, filename)
                else:
                    if export_format == 'excel' and not PANDAS_AVAILABLE:
                        logger.warning("pandas not available, falling back to CSV")
                    return OrderExportView._generate_csv_export(None, headers, data_rows, filename)
                
        except Exception as e:
            logger.error(f"Error exporting businesses: {str(e)}")
            return Response({
                'success': False,
                'message': f'Error exporting businesses: {str(e)}',
                'data': None
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class DeliveryFleetExportView(APIView):
    """
    Comprehensive delivery fleet data export to CSV format
    Extracts exact fields matching the Excel metrics structure
    GET /api/v1/admin/export/delivery-fleet/
    Query parameters:
    - include_history: true/false (default: false) - include location history
    - performance_days: number of days for performance data (default: 30)
    - status: filter by driver status (available/on_delivery/offline/all, default: all)
    - vehicle_type: filter by vehicle type (bike/scooter/car/bicycle, optional)
    """
    permission_classes = []
    
    def get(self, request):
        """Export comprehensive delivery fleet data with exact Excel field structure"""
        try:
            # Get query parameters
            include_history = request.query_params.get('include_history', 'false').lower() == 'true'
            performance_days = int(request.query_params.get('performance_days', 30))
            driver_status = request.query_params.get('status', 'all')
            vehicle_type = request.query_params.get('vehicle_type')
            
            # Validate parameters
            if performance_days > 365:
                return Response({
                    'success': False,
                    'message': 'performance_days cannot exceed 365',
                    'data': None
                }, status=status.HTTP_400_BAD_REQUEST)
            
            if driver_status not in ['available', 'on_delivery', 'offline', 'all']:
                driver_status = 'all'
            
            if vehicle_type and vehicle_type not in ['bike', 'scooter', 'car', 'bicycle']:
                vehicle_type = None
            
            with connection.cursor() as cursor:
                # First, check if there are any delivery partners at all
                cursor.execute("SELECT COUNT(*) FROM delivery_partner")
                total_partners = cursor.fetchone()[0]
                
                if total_partners == 0:
                    return Response({
                        'success': False,
                        'message': 'No delivery partners found in the database',
                        'data': None
                    }, status=status.HTTP_404_NOT_FOUND)
                
                # Build WHERE conditions
                where_conditions = []
                params = []
                
                if driver_status != 'all':
                    where_conditions.append("dp.status = %s")
                    params.append(driver_status)
                
                if vehicle_type:
                    where_conditions.append("dp.vehicle_type = %s")
                    params.append(vehicle_type)
                
                where_clause = "WHERE " + " AND ".join(where_conditions) if where_conditions else ""
                
                # Debug: Check how many partners match the filter
                cursor.execute(f"SELECT COUNT(*) FROM delivery_partner dp {where_clause}", params)
                filtered_partners = cursor.fetchone()[0]
                
                if filtered_partners == 0:
                    return Response({
                        'success': False,
                        'message': f'No delivery partners found matching the filters (status: {driver_status}, vehicle_type: {vehicle_type})',
                        'data': {
                            'total_partners': total_partners,
                            'filters_applied': {
                                'status': driver_status,
                                'vehicle_type': vehicle_type
                            }
                        }
                    }, status=status.HTTP_404_NOT_FOUND)
                
                # 1. Driver Profile Data with complete information
                cursor.execute(f"""
                    SELECT 
                        dp.id as driver_id,
                        dp.user_id,
                        CONCAT(COALESCE(r.firstName, ''), ' ', COALESCE(r.lastName, '')) as driver_name,
                        r.mobileNumber as phone,
                        r.emailID as email,
                        dp.vehicle_type,
                        dp.vehicle_number,
                        dp.status as driver_status,
                        dp.is_available,
                        dp.rating,
                        dp.total_deliveries,
                        dp.phone_number as contact_number,
                        dp.is_verified,
                        dp.business_id,
                        dp.latitude,
                        dp.longitude,
                        COALESCE(MAX(dlh.timestamp), dp.updated_at) as last_location_update,
                        dp.created_at as registration_date,
                        dp.updated_at as last_updated,
                        CASE 
                            WHEN COALESCE(MAX(dlh.timestamp), dp.updated_at) >= DATE_SUB(NOW(), INTERVAL 5 MINUTE) THEN 'realtime'
                            WHEN COALESCE(MAX(dlh.timestamp), dp.updated_at) >= DATE_SUB(NOW(), INTERVAL 15 MINUTE) THEN 'fresh'
                            WHEN COALESCE(MAX(dlh.timestamp), dp.updated_at) >= DATE_SUB(NOW(), INTERVAL 60 MINUTE) THEN 'stale'
                            ELSE 'offline'
                        END as location_freshness,
                        -- Business information
                        COALESCE(b.businessName, '') as assigned_business_name,
                        COALESCE(b.businessType, '') as assigned_business_type,
                        COALESCE(b.city, '') as business_city,
                        COALESCE(b.state, '') as business_state
                    FROM delivery_partner dp
                    LEFT JOIN registrations r ON dp.user_id = r.user_id
                    LEFT JOIN deliverylocationhistory dlh ON dp.id = dlh.delivery_partner_id
                    LEFT JOIN businesses b ON dp.business_id = b.business_id
                    {where_clause}
                    GROUP BY dp.id, r.firstName, r.lastName, r.mobileNumber, r.emailID, dp.vehicle_type, 
                             dp.vehicle_number, dp.status, dp.is_available, dp.rating, dp.total_deliveries, 
                             dp.phone_number, dp.is_verified, dp.business_id, dp.latitude, dp.longitude,
                             dp.created_at, dp.updated_at, b.businessName, b.businessType, b.city, b.state
                    ORDER BY dp.id
                """, params)
                
                driver_results = cursor.fetchall()
                
                if not driver_results:
                    return Response({
                        'success': False,
                        'message': f'Driver profile query returned no results. Found {filtered_partners} partners but query failed.',
                        'data': {
                            'total_partners': total_partners,
                            'filtered_partners': filtered_partners,
                            'where_clause': where_clause,
                            'params': params
                        }
                    }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
                
                # 2. Performance Data (last N days) with detailed metrics
                performance_cutoff = timezone.now() - timedelta(days=performance_days)
                cursor.execute(f"""
                    SELECT 
                        dp.id as driver_id,
                        COUNT(o.order_id) as orders_in_period,
                        COUNT(CASE WHEN o.status = 'delivered' THEN 1 END) as completed_orders,
                        COUNT(CASE WHEN o.status = 'cancelled' THEN 1 END) as cancelled_orders,
                        COALESCE(SUM(CASE WHEN o.status = 'delivered' THEN o.final_amount END), 0) as revenue_in_period,
                        AVG(CASE WHEN o.status = 'delivered' 
                            THEN TIMESTAMPDIFF(MINUTE, o.created_at, o.updated_at) 
                            END) as avg_delivery_time_minutes,
                        COUNT(CASE WHEN DATE(o.created_at) = CURDATE() THEN 1 END) as orders_today,
                        COUNT(CASE WHEN DATE(o.created_at) = CURDATE() AND o.status = 'delivered' THEN 1 END) as delivered_today,
                        COALESCE(MAX(o.created_at), NULL) as last_order_time,
                        COUNT(CASE WHEN o.created_at >= %s AND o.status IN ('confirmed', 'preparing', 'out_for_delivery', 'travelling') THEN 1 END) as active_orders_now,
                        -- Grocery orders performance (using Grocery_deliver_details)
                        COUNT(DISTINCT gdd.order_id) as grocery_orders_in_period,
                        COUNT(DISTINCT CASE WHEN gdd.assignment_status = 'delivered' THEN gdd.order_id END) as grocery_completed_orders,
                        COALESCE(SUM(CASE WHEN gdd.assignment_status = 'delivered' THEN go.final_amount END), 0) as grocery_revenue_in_period,
                        -- Order types breakdown
                        COUNT(CASE WHEN o.order_type = 'delivery' THEN 1 END) as delivery_orders,
                        COUNT(CASE WHEN o.order_type = 'pickup' THEN 1 END) as pickup_orders,
                        COUNT(CASE WHEN o.order_type = 'dine_in' THEN 1 END) as dine_in_orders,
                        COUNT(CASE WHEN o.order_type = 'takeaway' THEN 1 END) as takeaway_orders
                    FROM delivery_partner dp
                    LEFT JOIN orders o ON o.delivery_partner_id = dp.user_id AND o.created_at >= %s
                    LEFT JOIN Grocery_deliver_details gdd ON gdd.partner_id = dp.user_id AND gdd.created_at >= %s
                    LEFT JOIN Groceries_orders go ON gdd.order_id = go.order_id
                    {where_clause}
                    GROUP BY dp.id
                """, params + [performance_cutoff, performance_cutoff, performance_cutoff])
                
                performance_results = cursor.fetchall()
                performance_dict = {row[0]: row[1:] for row in performance_results}
                
                # 3. Location History (if requested)
                location_history_dict = {}
                if include_history:
                    cursor.execute(f"""
                        SELECT 
                            dlh.delivery_partner_id,
                            COUNT(*) as location_updates,
                            MIN(dlh.timestamp) as first_location,
                            MAX(dlh.timestamp) as last_location,
                            AVG(TIMESTAMPDIFF(MINUTE, 
                                LAG(dlh.timestamp) OVER (PARTITION BY dlh.delivery_partner_id ORDER BY dlh.timestamp),
                                dlh.timestamp
                            )) as avg_update_interval_minutes,
                            COUNT(CASE WHEN dlh.timestamp >= DATE_SUB(NOW(), INTERVAL 1 HOUR) THEN 1 END) as updates_last_hour,
                            COUNT(CASE WHEN dlh.timestamp >= DATE_SUB(NOW(), INTERVAL 24 HOUR) THEN 1 END) as updates_last_24h,
                            -- Distance calculation (approximate)
                            COUNT(*) as total_points_tracked
                        FROM deliverylocationhistory dlh
                        INNER JOIN delivery_partner dp ON dlh.delivery_partner_id = dp.id
                        WHERE dlh.timestamp >= %s
                        {where_clause.replace('dp.', 'dlh.').replace('WHERE', 'AND')}
                        GROUP BY dlh.delivery_partner_id
                    """, [performance_cutoff] + params)
                    
                    history_results = cursor.fetchall()
                    location_history_dict = {row[0]: row[1:] for row in history_results}
                
                # 4. Fleet Summary Statistics with comprehensive metrics
                cursor.execute(f"""
                    SELECT 
                        COUNT(*) as total_drivers,
                        COUNT(CASE WHEN dp.status = 'available' THEN 1 END) as available_drivers,
                        COUNT(CASE WHEN dp.status = 'on_delivery' THEN 1 END) as busy_drivers,
                        COUNT(CASE WHEN dp.status = 'offline' THEN 1 END) as offline_drivers,
                        COUNT(CASE WHEN dp.is_available = 1 THEN 1 END) as available_for_orders,
                        COUNT(CASE WHEN dp.latitude IS NOT NULL AND dp.longitude IS NOT NULL THEN 1 END) as drivers_with_location,
                        AVG(dp.rating) as average_rating,
                        SUM(dp.total_deliveries) as total_deliveries_all_time,
                        COUNT(CASE WHEN dp.is_verified = 1 THEN 1 END) as verified_drivers,
                        COUNT(CASE WHEN dp.business_id IS NOT NULL AND dp.business_id != '' THEN 1 END) as drivers_with_business,
                        -- Vehicle type breakdown
                        COUNT(CASE WHEN dp.vehicle_type = 'bike' THEN 1 END) as bike_count,
                        COUNT(CASE WHEN dp.vehicle_type = 'scooter' THEN 1 END) as scooter_count,
                        COUNT(CASE WHEN dp.vehicle_type = 'car' THEN 1 END) as car_count,
                        COUNT(CASE WHEN dp.vehicle_type = 'bicycle' THEN 1 END) as bicycle_count
                    FROM delivery_partner dp
                    {where_clause}
                """, params)
                
                fleet_summary = cursor.fetchone()
                
                # Prepare comprehensive data for export matching Excel structure
                headers = [
                    'Driver ID', 'User ID', 'Driver Name', 'Phone', 'Email',
                    'Vehicle Type', 'Vehicle Number', 'Driver Status', 'Available',
                    'Rating', 'Total Deliveries', 'Contact Number', 'Verified',
                    'Business ID', 'Assigned Business Name', 'Business Type', 'Business City', 'Business State',
                    'Current Latitude', 'Current Longitude', 'Last Location Update', 'Registration Date', 'Last Updated',
                    'Location Freshness', 'Orders (Last {0} Days)'.format(performance_days),
                    'Completed Orders (Last {0} Days)'.format(performance_days),
                    'Cancelled Orders (Last {0} Days)'.format(performance_days),
                    'Revenue (Last {0} Days)'.format(performance_days),
                    'Avg Delivery Time (Minutes)', 'Orders Today', 'Delivered Today',
                    'Last Order Time', 'Active Orders Now',
                    'Grocery Orders (Last {0} Days)'.format(performance_days),
                    'Grocery Completed Orders', 'Grocery Revenue',
                    'Delivery Orders', 'Pickup Orders', 'Dine In Orders', 'Takeaway Orders'
                ]
                
                if include_history:
                    headers.extend([
                        'Location Updates (Last {0} Days)'.format(performance_days),
                        'First Location', 'Last Location', 'Avg Update Interval (Minutes)',
                        'Updates Last Hour', 'Updates Last 24h', 'Total Points Tracked'
                    ])
                
                data_rows = []
                for row in driver_results:
                    driver_id = row[0]
                    performance_data = performance_dict.get(driver_id, [0, 0, 0, 0, None, 0, 0, None, 0, 0, 0, 0, 0, 0, 0, 0]) if len(performance_dict.get(driver_id, [])) >= 16 else [0, 0, 0, 0, None, 0, 0, None, 0, 0, 0, 0, 0, 0, 0, 0]
                    history_data = location_history_dict.get(driver_id, [0, None, None, None, 0, 0, 0]) if include_history else []
                    
                    formatted_row = [
                        driver_id,  # Driver ID
                        row[1],  # User ID
                        row[2] or '',  # Driver Name
                        row[3] or '',  # Phone
                        row[4] or '',  # Email
                        row[5],  # Vehicle Type
                        row[6] or '',  # Vehicle Number
                        row[7],  # Driver Status
                        'Yes' if row[8] else 'No',  # Available
                        float(row[9]) if row[9] else 0,  # Rating
                        row[10] or 0,  # Total Deliveries
                        row[11] or '',  # Contact Number
                        'Yes' if row[12] else 'No',  # Verified
                        row[13] or '',  # Business ID
                        row[20] or '',  # Assigned Business Name
                        row[21] or '',  # Business Type
                        row[22] or '',  # Business City
                        row[23] or '',  # Business State
                        float(row[14]) if row[14] else None,  # Current Latitude
                        float(row[15]) if row[15] else None,  # Current Longitude
                        row[16].strftime('%Y-%m-%d %H:%M:%S') if row[16] else '',  # Last Location Update
                        row[17].strftime('%Y-%m-%d %H:%M:%S') if row[17] else '',  # Registration Date
                        row[18].strftime('%Y-%m-%d %H:%M:%S') if row[18] else '',  # Last Updated
                        row[19],  # Location Freshness
                        performance_data[0],  # Orders in period
                        performance_data[1],  # Completed orders
                        performance_data[2],  # Cancelled orders
                        float(performance_data[3]) if performance_data[3] else 0,  # Revenue
                        float(performance_data[4]) if performance_data[4] else 0,  # Avg delivery time
                        performance_data[5],  # Orders today
                        performance_data[6],  # Delivered today
                        performance_data[7].strftime('%Y-%m-%d %H:%M:%S') if performance_data[7] else '',  # Last order time
                        performance_data[8],  # Active orders now
                        performance_data[9],  # Grocery orders in period
                        performance_data[10],  # Grocery completed orders
                        float(performance_data[11]) if performance_data[11] else 0,  # Grocery revenue
                        performance_data[12],  # Delivery orders
                        performance_data[13],  # Pickup orders
                        performance_data[14],  # Dine in orders
                        performance_data[15],  # Takeaway orders
                    ]
                    
                    if include_history:
                        formatted_row.extend([
                            history_data[0],  # Location updates
                            history_data[1].strftime('%Y-%m-%d %H:%M:%S') if history_data[1] else '',  # First location
                            history_data[2].strftime('%Y-%m-%d %H:%M:%S') if history_data[2] else '',  # Last location
                            float(history_data[3]) if history_data[3] else 0,  # Avg update interval
                            history_data[4],  # Updates last hour
                            history_data[5],  # Updates last 24h
                            history_data[6]  # Total points tracked
                        ])
                    
                    data_rows.append(formatted_row)
                
                # Add comprehensive summary rows at the end
                data_rows.append(['FLEET SUMMARY'] + [''] * (len(headers) - 1))
                data_rows.append([
                    'Total Drivers', fleet_summary[0], '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', ''
                ] + ([''] * 7 if include_history else []))
                data_rows.append([
                    'Available Drivers', fleet_summary[1], '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', ''
                ] + ([''] * 7 if include_history else []))
                data_rows.append([
                    'Busy Drivers (On Delivery)', fleet_summary[2], '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', ''
                ] + ([''] * 7 if include_history else []))
                data_rows.append([
                    'Offline Drivers', fleet_summary[3], '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', ''
                ] + ([''] * 7 if include_history else []))
                data_rows.append([
                    'Available for Orders', fleet_summary[4], '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', ''
                ] + ([''] * 7 if include_history else []))
                data_rows.append([
                    'Drivers with Location', fleet_summary[5], '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', ''
                ] + ([''] * 7 if include_history else []))
                data_rows.append([
                    'Average Rating', f"{fleet_summary[6]:.2f}" if fleet_summary[6] else '0', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', ''
                ] + ([''] * 7 if include_history else []))
                data_rows.append([
                    'Total Deliveries (All Time)', fleet_summary[7], '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', ''
                ] + ([''] * 7 if include_history else []))
                data_rows.append([
                    'Verified Drivers', fleet_summary[8], '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', ''
                ] + ([''] * 7 if include_history else []))
                data_rows.append([
                    'Drivers with Business', fleet_summary[9], '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', ''
                ] + ([''] * 7 if include_history else []))
                data_rows.append([
                    'Vehicle Breakdown', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', ''
                ] + ([''] * 7 if include_history else []))
                data_rows.append([
                    'Bikes', fleet_summary[10], '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', ''
                ] + ([''] * 7 if include_history else []))
                data_rows.append([
                    'Scooters', fleet_summary[11], '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', ''
                ] + ([''] * 7 if include_history else []))
                data_rows.append([
                    'Cars', fleet_summary[12], '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', ''
                ] + ([''] * 7 if include_history else []))
                data_rows.append([
                    'Bicycles', fleet_summary[13], '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', ''
                ] + ([''] * 7 if include_history else []))
                
                # Generate filename
                status_suffix = f"_{driver_status}" if driver_status != 'all' else ''
                vehicle_suffix = f"_{vehicle_type}" if vehicle_type else ""
                filename = f"delivery_fleet_export{status_suffix}{vehicle_suffix}_{timezone.now().strftime('%Y-%m-%d')}"
                
                return self._generate_csv_export(headers, data_rows, filename)
                
        except Exception as e:
            logger.error(f"Error exporting delivery fleet: {str(e)}")
            return Response({
                'success': False,
                'message': f'Error exporting delivery fleet: {str(e)}',
                'data': None
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    
    def _generate_csv_export(self, headers, data_rows, filename):
        """Generate CSV export with proper formatting"""
        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = f'attachment; filename="{filename}.csv"'
        
        # Add BOM for proper UTF-8 encoding in Excel
        response.write('\ufeff')
        
        writer = csv.writer(response)
        
        # Write metadata section
        writer.writerow(['DELIVERY FLEET DATA EXPORT'])
        writer.writerow([f'Generated on: {timezone.now().strftime("%Y-%m-%d %H:%M:%S")}'])
        writer.writerow([f'Total Records: {len([row for row in data_rows if not str(row[0]).startswith(("FLEET", "Total", "Available", "Busy", "Offline", "Drivers", "Verified", "Vehicle"))])}'])
        writer.writerow([])
        
        # Write headers
        writer.writerow(headers)
        
        # Write data rows
        writer.writerows(data_rows)
        
        return response
