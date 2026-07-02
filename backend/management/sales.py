from datetime import datetime, timedelta, date
from django.db import connection
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
import logging


logger = logging.getLogger(__name__)

# Calculation Rules Configuration
CALCULATION_RULES = {
    "net_income_excludes_gst": True,
    "sales_includes_gst": True,
    "delivery_charges_included": True,
    "parcel_charges_included": True
}


def _parse_bool(val, default=False):
    """Parse boolean value from string or return default."""
    if isinstance(val, bool):
        return val
    if val is None:
        return default
    s = str(val).strip().lower()
    return s in {"1", "true", "yes", "y", "on"}


def _format_indian_currency(value):
    """Format large numbers in Indian notation (K, Lac, Cr)"""
    if value is None:
        return "0"
    
    try:
        num = float(value)
        is_negative = num < 0
        abs_num = abs(num)
        
        if abs_num >= 10000000:  # 1 Crore or more
            formatted = f"{abs_num/10000000:.2f} Cr"
        elif abs_num >= 100000:  # 1 Lakh or more
            formatted = f"{abs_num/100000:.2f} Lac"
        elif abs_num >= 1000:  # 1 Thousand or more
            formatted = f"{abs_num/1000:.2f} K"
        else:
            formatted = f"{abs_num:.2f}"
        
        return f"-{formatted}" if is_negative else formatted
    except (ValueError, TypeError):
        return "0"


def _build_in_clause(values):
    """Return a tuple: (placeholders_sql, params_list). Ensures at least one placeholder."""
    if not values:
        # Ensure SQL stays valid; use impossible value
        return "%s", ["__NONE__"]
    return ",".join(["%s"] * len(values)), list(values)


def _date_filters(date_from, date_to, column_name):
    """Build SQL and params for an optional BETWEEN filter on the given column."""
    if date_from and date_to:
        return f" AND {column_name} BETWEEN %s AND %s ", [date_from, date_to]
    if date_from:
        return f" AND {column_name} >= %s ", [date_from]
    if date_to:
        return f" AND {column_name} <= %s ", [date_to]
    return "", []


def _normalize_date_bounds(date_from, date_to):
    """Normalize date-only strings to full-day datetime bounds for MySQL DATETIME columns."""
    df = str(date_from).strip() if date_from is not None else None
    dt = str(date_to).strip() if date_to is not None else None

    if df and len(df) == 10:
        # YYYY-MM-DD
        df = f"{df} 00:00:00"
    if dt and len(dt) == 10:
        # YYYY-MM-DD
        dt = f"{dt} 23:59:59"
    return df, dt


class BusinessSalesView(APIView):
    """
    Sales summary API across multiple sources for a business (and its branches if master):
    - Counter orders: business_counter_orders and business_counter_items
    - Restaurant orders/payments: orders + payments
    - Groceries orders/payments: Groceries_orders + Groceries_payments

    Query params:
    - business_id: required
    - date_from, date_to: optional (YYYY-MM-DD or full datetime supported by MySQL)
    - include_branches: optional (true/false). If omitted and business is master, branches are included by default.

    Response includes:
    - collections by payment method: cash, upi, card, online_razorpay, wallet (from all sources including counter)
    - pickup vs delivered counts and amounts
    - charges and discounts breakdown
    - per-source breakdown (counter_orders)
    """

    permission_classes = []

    def _get_financial_breakdown(self, cursor, business_ids, date_from=None, date_to=None, business_type=None):
        """
        Get comprehensive financial breakdown for the given business(es)
        Returns a dictionary with all financial metrics according to business requirements
        """
        date_from, date_to = _normalize_date_bounds(date_from, date_to)
        logger.info(f"[DEBUG] _get_financial_breakdown called with business_ids: {business_ids}, date_from: {date_from}, date_to: {date_to}")
        
        ids_sql, ids_params = _build_in_clause(business_ids)
        
        # Use the same date filtering approach as the main API
        co_date_sql, co_date_params = _date_filters(date_from, date_to, "created_at")  # For counter orders
        ord_date_sql, ord_date_params = _date_filters(date_from, date_to, "created_at")  # For orders
        gro_date_sql, gro_date_params = _date_filters(date_from, date_to, "created_at")  # For Groceries_orders
        
        logger.info(f"[DEBUG] Date filters - Counter: '{co_date_sql}' with params: {co_date_params}")
        logger.info(f"[DEBUG] Date filters - Orders: '{ord_date_sql}' with params: {ord_date_params}")
        logger.info(f"[DEBUG] Date filters - Groceries: '{gro_date_sql}' with params: {gro_date_params}")
        
        # 1. Get sales data from all sources with proper date filtering
        # First, get counter orders using same query as main API
        counter_query = """
            SELECT 
                COALESCE(SUM(paid_amount), 0) as counter_sales,
                COALESCE(SUM(discount_amount), 0) as counter_discount,
                COALESCE(SUM(gst_total), 0) as counter_gst,
                0 as counter_delivery,
                0 as counter_parcel
            FROM business_counter_orders
            WHERE business_id IN ({}) AND status='paid' {}
        """.format(ids_sql, co_date_sql)
        
        counter_params = ids_params + co_date_params
        logger.info(f"[DEBUG] Counter orders query: {counter_query}")
        logger.info(f"[DEBUG] Counter orders params: {counter_params}")
        
        try:
            cursor.execute(counter_query, counter_params)
            counter_result = cursor.fetchone()
            logger.info(f"[DEBUG] Counter orders result: {counter_result}")
        except Exception as e:
            logger.error(f"[ERROR] Error in counter orders query: {e}")
            raise
        
        # Then get other orders
        # Build the query with proper parameter placeholders
        other_orders_query = """
            SELECT 
                COALESCE(SUM(final_amount), 0) as other_sales,
                COALESCE(SUM(gst_amount), 0) as other_gst,
                COALESCE(SUM(discount), 0) as other_discount,
                COALESCE(SUM(delivery_charge), 0) as other_delivery,
                COALESCE(SUM(parcel_charge), 0) as other_parcel
            FROM (
                -- Restaurant orders - calculate GST from order_items
                SELECT 
                    o.final_amount, 
                    COALESCE((SELECT SUM(oi.gst_amount) FROM order_items oi WHERE oi.order_id = o.order_id), 0) as gst_amount,
                    o.discount_amount as discount, 
                    o.delivery_charges as delivery_charge, 
                    o.parcel_charges as parcel_charge
                FROM orders o
                WHERE o.business_id IN ({}) AND o.status IN ('delivered','completed') {}
                UNION ALL
                -- Groceries orders  
                SELECT final_amount, gst_amount, discount, delivery_charge, 0 as parcel_charge
                FROM Groceries_orders
                WHERE business_id IN ({}) AND order_status='delivered' {}
            ) other_orders
        """.format(ids_sql, ord_date_sql, ids_sql, gro_date_sql)
        
        # Combine all parameters in the correct order
        other_orders_params = ids_params + ord_date_params + ids_params + gro_date_params
        
        logger.info("[DEBUG] Other orders query: {}".format(other_orders_query))
        logger.info("[DEBUG] Other orders params: {}".format(other_orders_params))
        
        try:
            cursor.execute(other_orders_query, other_orders_params)
            other_result = cursor.fetchone()
            logger.info("[DEBUG] Other orders result: {}".format(other_result))
        except Exception as e:
            logger.error("[ERROR] Error in other orders query: {}".format(e))
            raise
        
        # Combine results
        if counter_result and other_result:
            # Sales total = sum of paid_amount (counter) + final_amount (orders + groceries)
            total_sales_with_gst = float(counter_result[0] or 0) + float(other_result[0] or 0)
            # Total GST = sum of gst_total (counter) + calculated GST (orders) + gst_amount (groceries)
            total_gst = float(counter_result[2] or 0) + float(other_result[1] or 0)
            total_discount = float(counter_result[1] or 0) + float(other_result[2] or 0)
            total_delivery = float(other_result[3] or 0)
            total_parcel = float(other_result[4] or 0)
        else:
            total_sales_with_gst = 0.0
            total_gst = 0.0
            total_discount = 0.0
            total_delivery = 0.0
            total_parcel = 0.0
        
        # 2. Calculate Net Income: EXCLUDING GST (do NOT add delivery/parcel again; final_amount already includes them)
        net_income = (total_sales_with_gst - total_gst)
        
        # 3. Calculate Sales total: INCLUDING GST (do NOT add delivery/parcel again; final_amount already includes them)
        sales = total_sales_with_gst
        
        # 4. Get expenses from expenses table
        expense_query = """
            SELECT COALESCE(SUM(amount), 0) as total_expenses
            FROM Expenses
            WHERE business_id IN ({}) AND expense_date BETWEEN %s AND %s
        """.format(ids_sql)
        
        expense_params = ids_params + [date_from or '2020-01-01', date_to or '2030-12-31']
        cursor.execute(expense_query, expense_params)
        expenses_row = cursor.fetchone()
        expenses_without_salary = float(expenses_row[0] or 0)
        
        # 5. Get staff salaries
        sal_date_sql, sal_date_params = _date_filters(date_from, date_to, "created_at")
        salary_query = """
            SELECT COALESCE(SUM(salary_paid), 0) as total_salaries
            FROM business_staff_salary_payments
            WHERE business_id IN ({}) {}
        """.format(ids_sql, sal_date_sql)
        
        salary_params = ids_params + sal_date_params
        cursor.execute(salary_query, salary_params)
        salaries_row = cursor.fetchone()
        salaries_total = float(salaries_row[0] or 0)
        
        # 6. Total expenses (expenses + salary)
        expenses = expenses_without_salary + salaries_total
        
        # 7. Get purchases from Purchases table
        purchase_query = """
            SELECT COALESCE(SUM(total_amount), 0) as total_purchases
            FROM Purchases
            WHERE business_id IN ({}) AND purchase_date BETWEEN %s AND %s
        """.format(ids_sql)
        
        purchase_params = ids_params + [date_from or '2020-01-01', date_to or '2030-12-31']
        cursor.execute(purchase_query, purchase_params)
        purchases_row = cursor.fetchone()
        purchases = float(purchases_row[0] or 0)
        
        # 8. Calculate Revenue = Sales - Expenses - Purchases
        revenue = sales - expenses - purchases
        
        # 9. P&L calculation with carryover from previous 6 months
        pnl_carryover = 0.0
        prev_months = []
        
        try:
            # Handle date parsing with time suffix
            if date_from and len(date_from) > 10:
                curr_from = datetime.strptime(date_from.split(' ')[0], '%Y-%m-%d').date()
            else:
                curr_from = datetime.strptime(date_from, '%Y-%m-%d').date() if date_from else None
                
            if date_to and len(date_to) > 10:
                curr_to = datetime.strptime(date_to.split(' ')[0], '%Y-%m-%d').date()
            else:
                curr_to = datetime.strptime(date_to, '%Y-%m-%d').date() if date_to else None
        except Exception:
            curr_from = None
            curr_to = None
            
        if curr_from and curr_to:
            # Calculate P&L for previous 6 months using single optimized query
            # Calculate date range for 6 months before current period
            prev_from = curr_from - timedelta(days=180)  # Approximate 6 months back
            prev_to = curr_from - timedelta(days=1)  # Day before current period starts
            
            # Single query to get monthly P&L data for all 6 months
            monthly_query = """
                SELECT 
                    DATE_FORMAT(month_period, '%%Y-%%m') as month,
                    COALESCE(SUM(month_sales), 0) as sales,
                    COALESCE(SUM(month_expenses), 0) as expenses,
                    COALESCE(SUM(month_purchases), 0) as purchases
                FROM (
                    SELECT 
                        DATE_FORMAT(created_at, '%%Y-%%m-01') as month_period,
                        final_amount as month_sales,
                        0 as month_expenses,
                        0 as month_purchases
                    FROM orders 
                    WHERE business_id IN ({}) AND status IN ('delivered','completed') 
                      AND created_at BETWEEN %s AND %s
                    
                    UNION ALL
                    
                    SELECT 
                        DATE_FORMAT(created_at, '%%Y-%%m-01') as month_period,
                        final_amount as month_sales,
                        0 as month_expenses,
                        0 as month_purchases
                    FROM Groceries_orders 
                    WHERE business_id IN ({}) AND order_status='delivered' 
                      AND created_at BETWEEN %s AND %s
                    
                    UNION ALL
                    
                    SELECT 
                        DATE_FORMAT(created_at, '%%Y-%%m-01') as month_period,
                        total_amount as month_sales,
                        0 as month_expenses,
                        0 as month_purchases
                    FROM business_counter_orders 
                    WHERE business_id IN ({}) AND status='paid' 
                      AND created_at BETWEEN %s AND %s
                    
                    UNION ALL
                    
                    SELECT 
                        DATE_FORMAT(expense_date, '%%Y-%%m-01') as month_period,
                        0 as month_sales,
                        amount as month_expenses,
                        0 as month_purchases
                    FROM Expenses
                    WHERE business_id IN ({}) 
                      AND expense_date BETWEEN %s AND %s
                    
                    UNION ALL
                    
                    SELECT 
                        DATE_FORMAT(purchase_date, '%%Y-%%m-01') as month_period,
                        0 as month_sales,
                        0 as month_expenses,
                        total_amount as month_purchases
                    FROM Purchases
                    WHERE business_id IN ({}) 
                      AND purchase_date BETWEEN %s AND %s
                ) all_data
                GROUP BY month_period
                ORDER BY month_period DESC
                LIMIT 6
            """.format(ids_sql, ids_sql, ids_sql, ids_sql, ids_sql)
            
            # Prepare parameters for all 5 subqueries
            monthly_params = []
            for _ in range(5):
                monthly_params.extend(ids_params)  # business_id IN (%s) for each subquery
                monthly_params.extend([prev_from, prev_to])  # date range for each subquery
            
            logger.info("[DEBUG] Optimized monthly P&L query: %s", monthly_query)
            logger.info("[DEBUG] Optimized monthly P&L params: %s", monthly_params)
            
            # Create dictionary to store results by month
            monthly_results_dict = {}
            
            try:
                cursor.execute(monthly_query, monthly_params)
                monthly_results = cursor.fetchall() or []
                logger.info("[DEBUG] Optimized monthly P&L results: %s", monthly_results)
                
                # Process results and store in dictionary
                for month, sales, expenses, purchases in monthly_results:
                    month_sales = float(sales or 0)
                    month_expenses = float(expenses or 0)
                    month_purchases = float(purchases or 0)
                    month_revenue = month_sales - month_expenses - month_purchases
                    pnl_carryover += month_revenue
                    monthly_results_dict[month] = float(month_revenue)
                    
            except Exception as e:
                logger.error("[ERROR] Error in optimized monthly P&L calculation: %s", str(e))
                logger.error("[ERROR] Query: %s", monthly_query)
                logger.error("[ERROR] Params: %s", monthly_params)
                # Fall back to empty array if query fails
            
            # Generate complete 12-month trend with actual data where available
            for i in range(12, 0, -1):  # 12 months ago to 1 month ago
                trend_date = curr_from - timedelta(days=30 * i)
                month_key = trend_date.strftime('%Y-%m')
                month_revenue = monthly_results_dict.get(month_key, 0.0)
                pnl_carryover += month_revenue
                prev_months.append({
                    "month": month_key,
                    "revenue": float(month_revenue),
                    "revenue_formatted": _format_indian_currency(month_revenue)
                })
        else:
            # If no date range provided, generate last 12 months with zero data
            today = date.today()
            for i in range(12, 0, -1):
                trend_date = today - timedelta(days=30 * i)
                prev_months.append({
                    "month": trend_date.strftime('%Y-%m'),
                    "revenue": 0.0,
                    "revenue_formatted": "0"
                })
        
        # 10. Final P&L calculation
        current_month_revenue = revenue
        adjusted_pnl = current_month_revenue + pnl_carryover
        
        # Build response with Indian currency formatting
        return {
            "calculation_rules": {
                "net_income_excludes_gst": True,
                "sales_includes_gst": True,
                "delivery_charges_included": True,
                "parcel_charges_included": True
            },
            "sales": {
                "total": float(sales),
                "total_formatted": _format_indian_currency(sales),
                "gross_sales": float(total_sales_with_gst),
                "gross_sales_formatted": _format_indian_currency(total_sales_with_gst),
                "breakdown": {
                    "subtotal": float(total_sales_with_gst - total_gst),
                    "subtotal_formatted": _format_indian_currency(total_sales_with_gst - total_gst),
                    "gst": float(total_gst),
                    "gst_formatted": _format_indian_currency(total_gst),
                    "gst_breakdown": {
                        "counter_gst": float(counter_result[2] or 0),
                        "counter_gst_formatted": _format_indian_currency(float(counter_result[2] or 0)),
                        "restaurant_gst": float(other_result[1] or 0),
                        "restaurant_gst_formatted": _format_indian_currency(float(other_result[1] or 0)),
                        "grocery_gst": float(gro_gst if 'gro_gst' in locals() else 0),
                        "grocery_gst_formatted": _format_indian_currency(float(gro_gst if 'gro_gst' in locals() else 0))
                    },
                    "discount": float(total_discount),
                    "discount_formatted": _format_indian_currency(total_discount),
                    "delivery": float(total_delivery),
                    "delivery_formatted": _format_indian_currency(total_delivery),
                    "parcel": float(total_parcel),
                    "parcel_formatted": _format_indian_currency(total_parcel)
                }
            },
            "expenses": {
                "total": float(expenses),
                "total_formatted": _format_indian_currency(expenses),
                "operational_expenses": float(expenses_without_salary),
                "operational_expenses_formatted": _format_indian_currency(expenses_without_salary),
                "salary_expenses": float(salaries_total),
                "salary_expenses_formatted": _format_indian_currency(salaries_total)
            },
            "purchases": {
                "total": float(purchases),
                "total_formatted": _format_indian_currency(purchases),
                "note": "GST and other charges not available in Purchases table structure"
            },
            "net_income": float(net_income),
            "net_income_formatted": _format_indian_currency(net_income),
            "revenue": float(revenue),
            "revenue_formatted": _format_indian_currency(revenue),
            "p_and_l": {
                "current_month": {
                    "revenue": float(current_month_revenue),
                    "revenue_formatted": _format_indian_currency(current_month_revenue),
                    "expenses": float(expenses),
                    "expenses_formatted": _format_indian_currency(expenses),
                    "purchases": float(purchases),
                    "purchases_formatted": _format_indian_currency(purchases),
                    "net": float(current_month_revenue),
                    "net_formatted": _format_indian_currency(current_month_revenue)
                },
                "carryover_analysis": {
                    "past_months": prev_months,
                    "total_carryover": float(pnl_carryover),
                    "total_carryover_formatted": _format_indian_currency(pnl_carryover),
                    "adjusted_p_and_l": float(adjusted_pnl),
                    "adjusted_p_and_l_formatted": _format_indian_currency(adjusted_pnl)
                }
            }
        }

    def get(self, request):
        business_id = request.query_params.get("business_id")
        date_from = request.query_params.get("date_from")
        date_to = request.query_params.get("date_to")
        include_branches_param = request.query_params.get("include_branches")
        
        # Financial trend parameters
        trend_from = request.query_params.get("trend_from")
        trend_to = request.query_params.get("trend_to")
        trend_months = request.query_params.get("trend_months")

        try:
            with connection.cursor() as cursor:
                print("DEBUG: Starting API execution")
                
                # Initialize variables to avoid undefined variable errors
                top_counter_orders_items = []
                cursor.execute(
                    """
                    SELECT business_id, businessName, level, master, businessType 
                    FROM businesses 
                    WHERE business_id = %s
                    LIMIT 1
                    """,
                    [business_id]
                )
                row = cursor.fetchone()
                if not row:
                    return Response({
                        "success": False,
                        "message": f"Business {business_id} not found"
                    }, status=status.HTTP_404_NOT_FOUND)

                base_business_id, base_business_name, base_level, base_master, base_business_type = row
                is_master = str(base_level).strip().lower() == "master"
                business_type = str(base_business_type or "").strip().upper()

                included_business_ids = [base_business_id]

                include_branches = _parse_bool(include_branches_param, default=is_master)
                if include_branches:
                    cursor.execute(
                        """
                        SELECT business_id 
                        FROM businesses 
                        WHERE master = %s
                        """,
                        [base_business_id]
                    )
                    branch_rows = cursor.fetchall() or []
                    included_business_ids.extend([r[0] for r in branch_rows])

                ids_sql, ids_params = _build_in_clause(included_business_ids)
                print(f"DEBUG: Business scope resolved, IDs: {included_business_ids}")

                # Prepare date filters per table
                print("DEBUG: Creating date filters")
                co_date_sql, co_date_params = _date_filters(date_from, date_to, "created_at")  # For single table queries
                co_date_sql_join, co_date_params_join = _date_filters(date_from, date_to, "bco.created_at")  # For JOIN queries
                ord_date_sql, ord_date_params = _date_filters(date_from, date_to, "o.created_at")
                pay_date_sql, pay_date_params = _date_filters(date_from, date_to, "p.created_at")
                gro_ord_date_sql, gro_ord_date_params = _date_filters(date_from, date_to, "created_at")  # For single table queries
                gro_ord_date_sql_join, gro_ord_date_params_join = _date_filters(date_from, date_to, "go.created_at")  # For JOIN queries
                gro_pay_date_sql, gro_pay_date_params = _date_filters(date_from, date_to, "gp.payment_date")
                print("DEBUG: Date filters created successfully")

                # Test each query section to find the ambiguous column error
                try:
                    cursor.execute(
                        f"""
                        SELECT COUNT(*) as test_count
                        FROM business_counter_orders
                        WHERE business_id IN ({ids_sql}) {co_date_sql}
                        """,
                        ids_params + co_date_params
                    )
                    print("Counter orders query OK")
                except Exception as e:
                    print(f"Counter orders query failed: {e}")
                    raise

                # 3) Groceries orders aggregates (Groceries_orders and Groceries_payments)
                cursor.execute(
                    f"""
                    SELECT
                        COUNT(*) as order_count,
                        COUNT(CASE WHEN order_status='delivered' THEN 1 END) as delivered_order_count,
                        COUNT(CASE WHEN order_type='pickup' THEN 1 END) as pickup_order_count,
                        COUNT(CASE WHEN order_type='delivery' THEN 1 END) as delivery_order_count,
                        COALESCE(SUM(final_amount), 0) as gross_total,
                        COALESCE(SUM(gst_amount), 0) as gst_total,
                        COALESCE(SUM(discount), 0) as discount_total
                    FROM Groceries_orders
                    WHERE business_id IN ({ids_sql}) {gro_ord_date_sql}
                    """,
                    ids_params + gro_ord_date_params
                )
                gro = cursor.fetchone() or (0, 0, 0, 0, 0, 0, 0)

                # 2) Counter orders aggregates (business_counter_orders)
                cursor.execute(
                    f"""
                    SELECT
                        COUNT(*) as order_count,
                        COUNT(CASE WHEN status='paid' THEN 1 END) as paid_order_count,
                        COUNT(CASE WHEN status='pending' THEN 1 END) as pending_order_count,
                        COUNT(CASE WHEN status='cancelled' THEN 1 END) as cancelled_order_count,
                        COALESCE(SUM(CASE WHEN payment_method='cash' AND status='paid' THEN total_amount ELSE 0 END), 0) as cash_total,
                        COALESCE(SUM(CASE WHEN payment_method='upi' AND status='paid' THEN total_amount ELSE 0 END), 0) as upi_total,
                        COALESCE(SUM(CASE WHEN payment_method='card' AND status='paid' THEN total_amount ELSE 0 END), 0) as card_total,
                        COALESCE(SUM(CASE WHEN payment_method='razorpay' AND status='paid' THEN total_amount ELSE 0 END), 0) as razorpay_total,
                        COALESCE(SUM(CASE WHEN payment_method='other' AND status='paid' THEN total_amount ELSE 0 END), 0) as other_total,
                        COALESCE(SUM(total_amount), 0) as gross_total,
                        COALESCE(SUM(subtotal), 0) as subtotal,
                        COALESCE(SUM(discount_amount), 0) as total_discount,
                        COALESCE(SUM(gst_total), 0) as total_gst
                    FROM business_counter_orders
                    WHERE business_id IN ({ids_sql}) {co_date_sql}
                    """,
                    ids_params + co_date_params
                )
                co = cursor.fetchone() or (0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0)
                (
                    co_order_count,
                    co_paid_count,
                    co_pending_count,
                    co_cancelled_count,
                    co_cash,
                    co_upi,
                    co_card,
                    co_razorpay,
                    co_other,
                    co_gross,
                    co_subtotal,
                    co_discount,
                    co_gst
                ) = co

                # 2c) Counter orders items aggregates (business_counter_items)
                try:
                    cursor.execute(
                        f"""
                        SELECT COUNT(*) as test_count
                        FROM business_counter_items bci
                        INNER JOIN business_counter_orders bco ON bco.order_id = bci.order_id
                        WHERE bci.business_id IN ({ids_sql}) {co_date_sql_join}
                        """,
                        ids_params + co_date_params_join
                    )
                    print("Counter items query OK")
                except Exception as e:
                    print(f"Counter items query failed: {e}")
                    raise

                cursor.execute(
                    f"""
                    SELECT
                        COUNT(*) as total_items_sold,
                        SUM(bci.quantity) as total_quantity_sold,
                        COALESCE(SUM(bci.line_total), 0) as total_items_revenue
                    FROM business_counter_items bci
                    INNER JOIN business_counter_orders bco ON bco.order_id = bci.order_id
                    WHERE bci.business_id IN ({ids_sql}) {co_date_sql_join}
                      AND bco.status = 'paid'
                    """,
                    ids_params + co_date_params_join
                )
                co_items_row = cursor.fetchone() or (0, 0, 0)
                (
                    co_total_items_sold,
                    co_total_quantity_sold,
                    co_total_items_revenue
                ) = co_items_row

                # 3) Restaurant orders summary (orders)
                cursor.execute(
                    f"""
                    SELECT
                        COALESCE(SUM(CASE WHEN o.status IN ('delivered','completed') THEN 1 ELSE 0 END), 0) as delivered_count,
                        COALESCE(SUM(CASE WHEN o.order_type IN ('pickup','takeaway') AND o.status IN ('delivered','completed') THEN 1 ELSE 0 END), 0) as pickup_delivered_count,
                        COALESCE(SUM(CASE WHEN o.status IN ('delivered','completed') THEN o.final_amount ELSE 0 END), 0) as delivered_revenue,
                        COALESCE(SUM(CASE WHEN o.order_type IN ('pickup','takeaway') AND o.status IN ('delivered','completed') THEN o.final_amount ELSE 0 END), 0) as pickup_revenue,
                        COALESCE(SUM(o.delivery_charges), 0) as delivery_charges_total,
                        COALESCE(SUM(o.parcel_charges), 0) as parcel_charges_total,
                        COALESCE(SUM(o.discount_amount), 0) as discount_total
                    FROM orders o
                    WHERE o.business_id IN ({ids_sql}) {ord_date_sql}
                    """,
                    ids_params + ord_date_params
                )
                ord = cursor.fetchone() or (0, 0, 0, 0, 0, 0, 0)
                (
                    ord_delivered_count,
                    ord_pickup_delivered_count,
                    ord_delivered_revenue,
                    ord_pickup_revenue,
                    ord_delivery_charges,
                    ord_parcel_charges,
                    ord_discount
                ) = ord

                # 4) Payments (restaurant orders): payments
                cursor.execute(
                    f"""
                    SELECT
                        COALESCE(SUM(CASE WHEN p.payment_method IN ('cash','cod') AND p.status='success' THEN p.amount ELSE 0 END), 0) as cash_amount,
                        COALESCE(SUM(CASE WHEN p.payment_method='upi' AND p.status='success' THEN p.amount ELSE 0 END), 0) as upi_amount,
                        COALESCE(SUM(CASE WHEN p.payment_method='card' AND p.status='success' THEN p.amount ELSE 0 END), 0) as card_amount,
                        COALESCE(SUM(CASE WHEN p.payment_method='razorpay' AND p.status='success' THEN p.amount ELSE 0 END), 0) as razorpay_amount,
                        COALESCE(SUM(CASE WHEN p.payment_method='wallet' AND p.status='success' THEN p.amount ELSE 0 END), 0) as wallet_amount,
                        COALESCE(SUM(CASE WHEN o.order_type IN ('pickup','takeaway') AND p.status='success' THEN p.amount ELSE 0 END), 0) as pickup_collection,
                        COALESCE(SUM(CASE WHEN (o.order_type NOT IN ('pickup','takeaway') OR o.order_type IS NULL) AND p.status='success' THEN p.amount ELSE 0 END), 0) as delivery_collection
                    FROM payments p
                    INNER JOIN orders o ON o.order_id = p.order_id
                    WHERE o.business_id IN ({ids_sql})
                      AND o.status IN ('delivered','completed')
                      {pay_date_sql}
                    """,
                    ids_params + pay_date_params
                )
                pay = cursor.fetchone() or (0, 0, 0, 0, 0, 0, 0)
                (
                    pay_cash,
                    pay_upi,
                    pay_card,
                    pay_razorpay,
                    pay_wallet,
                    pay_pickup_total,
                    pay_delivery_total
                ) = pay

                # 5) Groceries orders summary (only for R01)
                if business_type == 'R01':
                    cursor.execute(
                        f"""
                        SELECT
                            COALESCE(SUM(CASE WHEN order_status='delivered' THEN 1 ELSE 0 END), 0) as delivered_count,
                            COALESCE(SUM(CASE WHEN order_type IN ('pickup','takeaway') AND order_status='delivered' THEN 1 ELSE 0 END), 0) as pickup_delivered_count,
                            COALESCE(SUM(CASE WHEN order_status='delivered' THEN final_amount ELSE 0 END), 0) as delivered_revenue,
                            COALESCE(SUM(CASE WHEN order_type IN ('pickup','takeaway') AND order_status='delivered' THEN final_amount ELSE 0 END), 0) as pickup_revenue,
                            COALESCE(SUM(delivery_charge), 0) as delivery_charge_total,
                            COALESCE(SUM(gst_amount), 0) as gst_total,
                            COALESCE(SUM(discount), 0) as discount_total
                        FROM Groceries_orders
                        WHERE business_id IN ({ids_sql}) {gro_ord_date_sql}
                        """,
                        ids_params + gro_ord_date_params
                    )
                    gro = cursor.fetchone() or (0, 0, 0, 0, 0, 0, 0)
                    (
                        gro_delivered_count,
                        gro_pickup_delivered_count,
                        gro_delivered_revenue,
                        gro_pickup_revenue,
                        gro_delivery_charge,
                        gro_gst,
                        gro_discount
                    ) = gro
                else:
                    gro_delivered_count = 0
                    gro_pickup_delivered_count = 0
                    gro_delivered_revenue = 0.0
                    gro_pickup_revenue = 0.0
                    gro_delivery_charge = 0.0
                    gro_gst = 0.0
                    gro_discount = 0.0

                # 5b) Groceries paid sales total from orders table (payment_status='paid')
                if business_type == 'R01':
                    cursor.execute(
                        f"""
                        SELECT COALESCE(SUM(final_amount), 0)
                        FROM Groceries_orders
                        WHERE business_id IN ({ids_sql}) {gro_ord_date_sql}
                          AND payment_status='paid'
                        """,
                        ids_params + gro_ord_date_params
                    )
                    row_paid = cursor.fetchone()
                    gro_paid_sales_total = float(row_paid[0] or 0)
                else:
                    gro_paid_sales_total = 0.0

                # 6) Groceries payments (join to limit business scope, filter by completed) - only R01
                if business_type == 'R01':
                    cursor.execute(
                        f"""
                        SELECT
                            COALESCE(SUM(CASE WHEN gp.payment_method='cash' AND gp.payment_status='completed' THEN gp.amount ELSE 0 END), 0) as cash_amount,
                            COALESCE(SUM(CASE WHEN gp.payment_method='upi' AND gp.payment_status='completed' THEN gp.amount ELSE 0 END), 0) as upi_amount,
                            COALESCE(SUM(CASE WHEN gp.payment_method='card' AND gp.payment_status='completed' THEN gp.amount ELSE 0 END), 0) as card_amount,
                            COALESCE(SUM(CASE WHEN gp.payment_method='razorpay' AND gp.payment_status='completed' THEN gp.amount ELSE 0 END), 0) as razorpay_amount,
                            COALESCE(SUM(CASE WHEN gp.payment_method='wallet' AND gp.payment_status='completed' THEN gp.amount ELSE 0 END), 0) as wallet_amount,
                            COALESCE(SUM(CASE WHEN go.order_type IN ('pickup','takeaway') AND gp.payment_status='completed' THEN gp.amount ELSE 0 END), 0) as pickup_collection,
                            COALESCE(SUM(CASE WHEN (go.order_type NOT IN ('pickup','takeaway') OR go.order_type IS NULL) AND gp.payment_status='completed' THEN gp.amount ELSE 0 END), 0) as delivery_collection
                        FROM Groceries_payments gp
                        INNER JOIN Groceries_orders go ON go.order_id = gp.order_id
                        WHERE go.business_id IN ({ids_sql}) {gro_pay_date_sql}
                          AND go.order_status='delivered'
                        """,
                        ids_params + gro_pay_date_params
                    )
                    gpay = cursor.fetchone() or (0, 0, 0, 0, 0, 0, 0)
                    (
                        gpay_cash,
                        gpay_upi,
                        gpay_card,
                        gpay_razorpay,
                        gpay_wallet,
                        gpay_pickup_total,
                        gpay_delivery_total
                    ) = gpay
                else:
                    gpay_cash = gpay_upi = gpay_card = gpay_razorpay = gpay_wallet = 0.0
                    gpay_pickup_total = gpay_delivery_total = 0.0

                # Combine collections across sources (counter_orders + payments)
                collections = {
                    "cash": {
                        "amount": float(co_cash) + float(gpay_cash) + float(pay_cash),
                        "amount_formatted": _format_indian_currency(float(co_cash) + float(gpay_cash) + float(pay_cash))
                    },
                    "upi": {
                        "amount": float(co_upi) + float(gpay_upi) + float(pay_upi),
                        "amount_formatted": _format_indian_currency(float(co_upi) + float(gpay_upi) + float(pay_upi))
                    },
                    "card": {
                        "amount": float(co_card) + float(gpay_card) + float(pay_card),
                        "amount_formatted": _format_indian_currency(float(co_card) + float(gpay_card) + float(pay_card))
                    },
                    "online_razorpay": {
                        "amount": float(co_razorpay) + float(gpay_razorpay) + float(pay_razorpay),
                        "amount_formatted": _format_indian_currency(float(co_razorpay) + float(gpay_razorpay) + float(pay_razorpay))
                    },
                    "wallet": {
                        "amount": float(gpay_wallet) + float(pay_wallet),
                        "amount_formatted": _format_indian_currency(float(gpay_wallet) + float(pay_wallet))
                    },
                }
                collections["total_collections"] = sum(collections[key]["amount"] for key in collections if key != "total_collections")
                collections["total_collections_formatted"] = _format_indian_currency(collections["total_collections"])

                # Financial rollups and added analytics
                # Gross sales across channels (includes GST and charges where applicable)
                sales_gross_total = float(co_gross) + float(ord_delivered_revenue) + float(gro_delivered_revenue)

                # Net Income (exclude GST where available, include delivery & parcel charges)
                # Counter orders: subtotal - discount (GST excluded)
                cursor.execute(
                    f"""
                    SELECT COALESCE(SUM(CASE WHEN status='paid' THEN (subtotal - discount_amount) ELSE 0 END), 0)
                    FROM business_counter_orders
                    WHERE business_id IN ({ids_sql}) {co_date_sql}
                    """,
                    ids_params + co_date_params
                )
                net_counter_income = float(cursor.fetchone()[0] or 0)

                # Restaurant orders: no GST column available, use final_amount (includes delivery/parcel if present)
                net_restaurant_income = float(ord_delivered_revenue)

                # Groceries: final_amount - gst_amount (retain delivery charges and other charges)
                if business_type == 'R01':
                    cursor.execute(
                        f"""
                        SELECT COALESCE(SUM(CASE WHEN order_status='delivered' THEN (final_amount - gst_amount) ELSE 0 END), 0)
                        FROM Groceries_orders
                        WHERE business_id IN ({ids_sql}) {gro_ord_date_sql}
                        """,
                        ids_params + gro_ord_date_params
                    )
                    net_grocery_income = float(cursor.fetchone()[0] or 0)
                else:
                    net_grocery_income = 0.0

                net_income_total = net_counter_income + net_restaurant_income + net_grocery_income

                # Purchases and Expenses (including staff salaries)
                purchase_date_sql, purchase_date_params = _date_filters(date_from, date_to, "purchase_date")
                expense_date_sql, expense_date_params = _date_filters(date_from, date_to, "expense_date")

                cursor.execute(
                    f"""
                    SELECT COALESCE(SUM(total_amount), 0)
                    FROM Purchases
                    WHERE business_id IN ({ids_sql}) {purchase_date_sql}
                    """,
                    ids_params + purchase_date_params
                )
                purchases_total = float(cursor.fetchone()[0] or 0)

                cursor.execute(
                    f"""
                    SELECT COALESCE(SUM(amount), 0)
                    FROM Expenses
                    WHERE business_id IN ({ids_sql}) {expense_date_sql}
                    """,
                    ids_params + expense_date_params
                )
                expenses_total_only = float(cursor.fetchone()[0] or 0)

                sal_date_sql, sal_date_params = _date_filters(date_from, date_to, "created_at")
                # Try to filter by year/month for better accuracy, fallback to created_at
                try:
                    if date_from and date_to:
                        # Extract year and month from date strings
                        from_year = int(date_from.split('-')[0]) if len(date_from) >= 4 else datetime.now().year
                        from_month = int(date_from.split('-')[1]) if len(date_from.split('-')) >= 2 else 1
                        to_year = int(date_to.split('-')[0]) if len(date_to) >= 4 else datetime.now().year
                        to_month = int(date_to.split('-')[1]) if len(date_to.split('-')) >= 2 else 12
                        
                        cursor.execute(
                            f"""
                            SELECT COALESCE(SUM(salary_paid), 0)
                            FROM business_staff_salary_payments
                            WHERE business_id IN ({ids_sql}) 
                              AND ((year = %s AND month >= %s) OR (year > %s AND year < %s) OR (year = %s AND month <= %s))
                            """,
                            ids_params + [from_year, from_month, from_year, to_year, to_year, to_month]
                        )
                    else:
                        # Fallback to created_at filter
                        cursor.execute(
                            f"""
                            SELECT COALESCE(SUM(salary_paid), 0)
                            FROM business_staff_salary_payments
                            WHERE business_id IN ({ids_sql}) {sal_date_sql}
                            """,
                            ids_params + sal_date_params
                        )
                except Exception:
                    # Fallback to created_at filter if year/month parsing fails
                    cursor.execute(
                        f"""
                        SELECT COALESCE(SUM(salary_paid), 0)
                        FROM business_staff_salary_payments
                        WHERE business_id IN ({ids_sql}) {sal_date_sql}
                        """,
                        ids_params + sal_date_params
                    )
                salaries_total = float(cursor.fetchone()[0] or 0)

                expenses_total = expenses_total_only + salaries_total

                # Net revenue/profit for period
                revenue_net = sales_gross_total - expenses_total - purchases_total
                
                # Operational Profit: Net income after deducting operational expenses only (excluding salaries)
                operational_profit = net_income_total - expenses_total_only
                
                # Average Transaction Value: Total revenue ÷ Total orders across all sources
                total_orders = int(co_paid_count) + int(ord_delivered_count) + int(gro_delivered_count)
                avg_transaction_value = sales_gross_total / total_orders if total_orders > 0 else 0.0

                # P&L carryover from previous 6 months
                try:
                    curr_from = datetime.strptime(date_from, '%Y-%m-%d').date() if date_from else None
                    curr_to = datetime.strptime(date_to, '%Y-%m-%d').date() if date_to else None
                except Exception:
                    curr_from = None
                    curr_to = None
                if not curr_from or not curr_to:
                    today = datetime.now().date()
                    prev_month_end = (today.replace(day=1) - timedelta(days=1))
                    prev_month_start = prev_month_end.replace(day=1)
                    curr_from, curr_to = prev_month_start, prev_month_end

                prev_months = []
                bound = curr_from.replace(day=1) - timedelta(days=1)
                for _ in range(6):
                    start = bound.replace(day=1)
                    end = bound
                    prev_months.append((start, end))
                    bound = start - timedelta(days=1)

                pnl_carryover = 0.0
                for m_start, m_end in prev_months:
                    dm_sql, dm_params = _date_filters(m_start, m_end, "created_at")
                    do_sql, do_params = _date_filters(m_start, m_end, "o.created_at")
                    dg_sql, dg_params = _date_filters(m_start, m_end, "created_at")

                    cursor.execute(
                        f"SELECT COALESCE(SUM(total_amount),0) FROM business_counter_orders WHERE business_id IN ({ids_sql}) AND status='paid' {dm_sql}",
                        ids_params + dm_params
                    )
                    m_co = float(cursor.fetchone()[0] or 0)
                    cursor.execute(
                        f"SELECT COALESCE(SUM(CASE WHEN o.status IN ('delivered','completed') THEN o.final_amount ELSE 0 END),0) FROM orders o WHERE o.business_id IN ({ids_sql}) {do_sql}",
                        ids_params + do_params
                    )
                    m_ord = float(cursor.fetchone()[0] or 0)
                    if business_type == 'R01':
                        cursor.execute(
                            f"SELECT COALESCE(SUM(CASE WHEN order_status='delivered' THEN final_amount ELSE 0 END),0) FROM Groceries_orders WHERE business_id IN ({ids_sql}) {dg_sql}",
                            ids_params + dg_params
                        )
                        m_gro = float(cursor.fetchone()[0] or 0)
                    else:
                        m_gro = 0.0
                    m_sales = m_co + m_ord + m_gro

                    mp_sql, mp_params = _date_filters(m_start, m_end, "purchase_date")
                    me_sql, me_params = _date_filters(m_start, m_end, "expense_date")
                    ms_sql, ms_params = _date_filters(m_start, m_end, "created_at")
                    cursor.execute(
                        f"SELECT COALESCE(SUM(total_amount),0) FROM Purchases WHERE business_id IN ({ids_sql}) {mp_sql}",
                        ids_params + mp_params
                    )
                    m_pur = float(cursor.fetchone()[0] or 0)
                    cursor.execute(
                        f"SELECT COALESCE(SUM(amount),0) FROM Expenses WHERE business_id IN ({ids_sql}) {me_sql}",
                        ids_params + me_params
                    )
                    m_exp = float(cursor.fetchone()[0] or 0)
                    cursor.execute(
                        f"SELECT COALESCE(SUM(salary_paid),0) FROM business_staff_salary_payments WHERE business_id IN ({ids_sql}) {ms_sql}",
                        ids_params + ms_params
                    )
                    m_sal = float(cursor.fetchone()[0] or 0)
                    pnl_carryover += (m_sales - (m_pur + m_exp + m_sal))

                pnl_adjusted = revenue_net + pnl_carryover

                # Channel performance (share of gross sales)
                channel_performance = {
                    "counter": {
                        "revenue": float(co_gross),
                        "revenue_formatted": _format_indian_currency(float(co_gross)),
                        "share_percent": (float(co_gross) / sales_gross_total * 100) if sales_gross_total > 0 else 0.0,
                    },
                    "App/Web Kirazee": {
                        "revenue": float(ord_delivered_revenue),
                        "revenue_formatted": _format_indian_currency(float(ord_delivered_revenue)),
                        "share_percent": (float(ord_delivered_revenue) / sales_gross_total * 100) if sales_gross_total > 0 else 0.0,
                    },
                    "Custom Site": {
                        "revenue": float(gro_delivered_revenue),
                        "revenue_formatted": _format_indian_currency(float(gro_delivered_revenue)),
                        "share_percent": (float(gro_delivered_revenue) / sales_gross_total * 100) if sales_gross_total > 0 else 0.0,
                    },
                }

                # Inventory valuation (exclude GroceryItems table) - route by business type
                mi_mrp = mi_cost = gv_mrp = gv_cost = fv_mrp = fv_cost = 0.0
                if business_type == 'R02':
                    # Restaurant: Use MenuItems table
                    cursor.execute(
                        f"""
                        SELECT 
                            COALESCE(SUM(i.current_stock * COALESCE(m.selling_price, 0)), 0) AS mrp_value,
                            COALESCE(SUM(i.current_stock * COALESCE(m.original_cost, 0)), 0) AS cost_value
                        FROM Inventory i
                        LEFT JOIN menuItems m ON m.item_id = i.reference_id
                        WHERE i.business_id IN ({ids_sql}) 
                          AND i.reference_table IN ('menuitems', 'menu_items')
                          AND i.current_stock > 0
                        """,
                        ids_params
                    )
                    row_mi = cursor.fetchone() or (0, 0)
                    mi_mrp, mi_cost = float(row_mi[0] or 0), float(row_mi[1] or 0)
                elif business_type == 'R01':
                    # Grocery: Use Groceries_ProductVariants_1 table
                    cursor.execute(
                        f"""
                        SELECT 
                            COALESCE(SUM(i.current_stock * COALESCE(v.selling_price, 0)), 0) AS mrp_value,
                            COALESCE(SUM(i.current_stock * COALESCE(v.original_cost, 0)), 0) AS cost_value
                        FROM Inventory i
                        LEFT JOIN Groceries_ProductVariants_1 v ON v.variant_id = i.reference_id
                        WHERE i.business_id IN ({ids_sql}) 
                          AND i.reference_table IN ('groceries_productvariants', 'groceriesproductvariants')
                          AND i.current_stock > 0
                        """,
                        ids_params
                    )
                    row_gv = cursor.fetchone() or (0, 0)
                    gv_mrp, gv_cost = float(row_gv[0] or 0), float(row_gv[1] or 0)
                elif business_type == 'R08':
                    # Fashion: Use fashion_product_variants table
                    cursor.execute(
                        f"""
                        SELECT 
                            COALESCE(SUM(COALESCE(i.current_stock, 0) * COALESCE(fpv.selling_price, 0)), 0) AS mrp_value,
                            COALESCE(SUM(COALESCE(i.current_stock, 0) * COALESCE(fpv.original_cost, 0)), 0) AS cost_value
                        FROM Inventory i
                        LEFT JOIN fashion_product_variants fpv ON fpv.variant_id = i.reference_id
                        WHERE i.business_id IN ({ids_sql}) 
                          AND i.reference_table IN ('fashion_product_variants', 'fashionproductvariants')
                          AND i.current_stock > 0
                        """,
                        ids_params
                    )
                    row_fv = cursor.fetchone() or (0, 0)
                    fv_mrp, fv_cost = float(row_fv[0] or 0), float(row_fv[1] or 0)
                else:
                    # Unknown/mixed: compute all types
                    # Restaurant items
                    cursor.execute(
                        f"""
                        SELECT 
                            COALESCE(SUM(i.current_stock * COALESCE(m.selling_price, 0)), 0) AS mrp_value,
                            COALESCE(SUM(i.current_stock * COALESCE(m.original_cost, 0)), 0) AS cost_value
                        FROM Inventory i
                        LEFT JOIN menuItems m ON m.item_id = i.reference_id
                        WHERE i.business_id IN ({ids_sql}) 
                          AND i.reference_table IN ('menuitems', 'menu_items')
                          AND i.current_stock > 0
                        """,
                        ids_params
                    )
                    row_mi = cursor.fetchone() or (0, 0)
                    mi_mrp, mi_cost = float(row_mi[0] or 0), float(row_mi[1] or 0)
                    
                    # Grocery items
                    cursor.execute(
                        f"""
                        SELECT 
                            COALESCE(SUM(i.current_stock * COALESCE(v.selling_price, 0)), 0) AS mrp_value,
                            COALESCE(SUM(i.current_stock * COALESCE(v.original_cost, 0)), 0) AS cost_value
                        FROM Inventory i
                        LEFT JOIN Groceries_ProductVariants_1 v ON v.variant_id = i.reference_id
                        WHERE i.business_id IN ({ids_sql}) 
                          AND i.reference_table IN ('groceries_productvariants', 'groceriesproductvariants')
                          AND i.current_stock > 0
                        """,
                        ids_params
                    )
                    row_gv = cursor.fetchone() or (0, 0)
                    gv_mrp, gv_cost = float(row_gv[0] or 0), float(row_gv[1] or 0)

                    # Fashion items
                    cursor.execute(
                        f"""
                        SELECT 
                            COALESCE(SUM(COALESCE(i.current_stock, 0) * COALESCE(fpv.selling_price, 0)), 0) AS mrp_value,
                            COALESCE(SUM(COALESCE(i.current_stock, 0) * COALESCE(fpv.original_cost, 0)), 0) AS cost_value
                        FROM Inventory i
                        LEFT JOIN fashion_product_variants fpv ON fpv.variant_id = i.reference_id
                        WHERE i.business_id IN ({ids_sql}) 
                          AND i.reference_table IN ('fashion_product_variants', 'fashionproductvariants')
                          AND i.current_stock > 0
                        """,
                        ids_params
                    )
                    row_fv = cursor.fetchone() or (0, 0)
                    fv_mrp, fv_cost = float(row_fv[0] or 0), float(row_fv[1] or 0)

                total_stock_value_at_mrp = mi_mrp + gv_mrp + fv_mrp
                total_stock_value_at_cost = mi_cost + gv_cost + fv_cost
                potential_profit = total_stock_value_at_mrp - total_stock_value_at_cost

                # Previous period comparison (same length as current period)
                try:
                    period_days = (curr_to - curr_from).days + 1 if curr_from and curr_to else 30
                    prev_to = curr_from - timedelta(days=1)
                    prev_from = prev_to - timedelta(days=period_days - 1)
                    p_co_sql, p_co_params = _date_filters(prev_from, prev_to, "created_at")
                    p_ord_sql, p_ord_params = _date_filters(prev_from, prev_to, "o.created_at")
                    if business_type == 'R01':
                        p_gro_sql, p_gro_params = _date_filters(prev_from, prev_to, "created_at")

                    cursor.execute(
                        f"SELECT COALESCE(SUM(total_amount),0), COUNT(*) FROM business_counter_orders WHERE business_id IN ({ids_sql}) AND status='paid' {p_co_sql}",
                        ids_params + p_co_params
                    )
                    pr = cursor.fetchone() or (0, 0)
                    p_co_amt, p_co_tx = float(pr[0] or 0), int(pr[1] or 0)
                    cursor.execute(
                        f"SELECT COALESCE(SUM(CASE WHEN o.status IN ('delivered','completed') THEN o.final_amount ELSE 0 END),0), COUNT(CASE WHEN o.status IN ('delivered','completed') THEN 1 END) FROM orders o WHERE o.business_id IN ({ids_sql}) {p_ord_sql}",
                        ids_params + p_ord_params
                    )
                    p_ord = cursor.fetchone() or (0, 0)
                    p_ord_amt, p_ord_tx = float(p_ord[0] or 0), int(p_ord[1] or 0)
                    if business_type == 'R01':
                        cursor.execute(
                            f"SELECT COALESCE(SUM(CASE WHEN order_status='delivered' THEN final_amount ELSE 0 END),0), COUNT(CASE WHEN order_status='delivered' THEN 1 END) FROM Groceries_orders WHERE business_id IN ({ids_sql}) {p_gro_sql}",
                            ids_params + p_gro_params
                        )
                        p_gro = cursor.fetchone() or (0, 0)
                        p_gro_amt, p_gro_tx = float(p_gro[0] or 0), int(p_gro[1] or 0)
                    else:
                        p_gro_amt, p_gro_tx = 0.0, 0
                    p_total_revenue = p_co_amt + p_ord_amt + p_gro_amt
                    p_total_transactions = p_co_tx + p_ord_tx + p_gro_tx
                except Exception as e:
                    logger.error(f"[ERROR] Error calculating comparison metrics: {e}")
                    p_total_revenue = 0.0
                    p_total_transactions = 0

                comparison_metrics = {
                    "previous_period": {
                        "date_from": prev_from.isoformat() if prev_from else None,
                        "date_to": prev_to.isoformat() if prev_to else None,
                        "total_revenue": p_total_revenue,
                        "total_revenue_formatted": _format_indian_currency(p_total_revenue),
                        "total_transactions": p_total_transactions
                    },
                    "growth": {
                        "revenue_growth_percent": ((sales_gross_total - p_total_revenue) / p_total_revenue * 100) if p_total_revenue > 0 else 0.0,
                        "transaction_growth_percent": ((total_orders - p_total_transactions) / p_total_transactions * 100) if p_total_transactions > 0 else 0.0
                    }
                }

                # Channel performance (share of gross sales)
                channel_performance = {
                    "counter": {
                        "revenue": float(co_gross or 0),
                        "revenue_formatted": _format_indian_currency(float(co_gross or 0)),
                        "share_percent": (float(co_gross or 0) / max(float(sales_gross_total or 1), 1) * 100) if (sales_gross_total or 0) > 0 else 0.0,
                    },
                    "App/Web Kirazee": {
                        "revenue": float(ord_delivered_revenue or 0),
                        "revenue_formatted": _format_indian_currency(float(ord_delivered_revenue or 0)),
                        "share_percent": (float(ord_delivered_revenue or 0) / max(float(sales_gross_total or 1), 1) * 100) if (sales_gross_total or 0) > 0 else 0.0,
                    },
                    "Custom Site": {
                        "revenue": float(gro_delivered_revenue or 0),
                        "revenue_formatted": _format_indian_currency(float(gro_delivered_revenue or 0)),
                        "share_percent": (float(gro_delivered_revenue or 0) / max(float(sales_gross_total or 1), 1) * 100) if (sales_gross_total or 0) > 0 else 0.0,
                    },
                }

                # Calculate average order value
                co_avg_order_value = float(co_gross) / int(co_paid_count) if int(co_paid_count) > 0 else 0.0
                co_avg_items_per_order = float(co_total_items_sold or 0) / int(co_paid_count) if int(co_paid_count) > 0 else 0.0

                # Top selling products (optional: limit via query param top_limit)
                top_limit_param = request.query_params.get("top_limit")
                try:
                    top_limit = max(1, min(20, int(top_limit_param))) if top_limit_param else 5
                except Exception:
                    top_limit = 5

                # Kirazee (restaurant) top items by quantity (then revenue)
                cursor.execute(
                    f"""
                    SELECT
                        oi.item_name_snapshot AS name,
                        SUM(oi.quantity) AS total_qty,
                        COALESCE(SUM(oi.total_price), 0) AS total_revenue
                    FROM order_items oi
                    INNER JOIN orders o ON o.order_id = oi.order_id
                    WHERE o.business_id IN ({ids_sql}) {ord_date_sql}
                      AND o.status IN ('delivered','completed')
                    GROUP BY oi.item_name_snapshot
                    ORDER BY total_qty DESC, total_revenue DESC
                    LIMIT {top_limit}
                    """,
                    ids_params + ord_date_params
                )
                rows_k = cursor.fetchall() or []
                top_kirazee = [
                    {"name": r[0], "quantity": int(r[1] or 0), "revenue": float(r[2] or 0.0), "revenue_formatted": _format_indian_currency(float(r[2] or 0.0))} for r in rows_k
                ]

                # RK Supermarket (groceries) top items
                if business_type == 'R01':
                    cursor.execute(
                        f"""
                        SELECT
                            p.product_name AS name,
                            SUM(goi.quantity) AS total_qty,
                            COALESCE(SUM(goi.total_price), 0) AS total_revenue
                        FROM Groceries_order_items goi
                        INNER JOIN Groceries_orders go ON go.order_id = goi.order_id
                        INNER JOIN Groceries_Products p ON p.product_id = goi.product_id
                        WHERE go.business_id IN ({ids_sql}) {gro_ord_date_sql_join}
                          AND go.order_status = 'delivered'
                        GROUP BY p.product_name
                        ORDER BY total_qty DESC, total_revenue DESC
                        LIMIT {top_limit}
                        """,
                        ids_params + gro_ord_date_params_join
                    )
                    rows_rk = cursor.fetchall() or []
                    top_rk = [
                        {"name": r[0], "quantity": int(r[1] or 0), "revenue": float(r[2] or 0.0), "revenue_formatted": _format_indian_currency(float(r[2] or 0.0))} for r in rows_rk
                    ]
                else:
                    top_rk = []

                # Counter orders items top items
                cursor.execute(
                    f"""
                    SELECT
                        bci.item_name AS name,
                        SUM(bci.quantity) AS total_qty,
                        COALESCE(SUM(bci.line_total), 0) AS total_revenue
                    FROM business_counter_items bci
                    INNER JOIN business_counter_orders bco ON bco.order_id = bci.order_id
                    WHERE bci.business_id IN ({ids_sql}) {co_date_sql_join}
                      AND bco.status = 'paid'
                    GROUP BY bci.item_name
                    ORDER BY total_qty DESC, total_revenue DESC
                    LIMIT {top_limit}
                    """,
                    ids_params + co_date_params_join
                )
                rows_co_items = cursor.fetchall() or []
                top_counter_orders_items = [
                    {"name": r[0], "quantity": int(r[1] or 0), "revenue": float(r[2] or 0.0), "revenue_formatted": _format_indian_currency(float(r[2] or 0.0))} for r in rows_co_items
                ]

                # Combined top items across all sources (by name)
                # Build combined top items conditionally (include groceries only for R01)
                union_parts = [
                    f"""
                    SELECT CONVERT(oi.item_name_snapshot USING utf8mb4) COLLATE utf8mb4_general_ci AS name,
                           SUM(oi.quantity) AS total_qty,
                           COALESCE(SUM(oi.total_price), 0) AS total_revenue
                    FROM order_items oi
                    INNER JOIN orders o ON o.order_id = oi.order_id
                    WHERE o.business_id IN ({ids_sql}) {ord_date_sql}
                      AND o.status IN ('delivered','completed')
                    GROUP BY CONVERT(oi.item_name_snapshot USING utf8mb4) COLLATE utf8mb4_general_ci
                    """
                ]
                union_params = ids_params + ord_date_params
                if business_type == 'R01':
                    union_parts.append(
                        f"""
                        SELECT CONVERT(p.product_name USING utf8mb4) COLLATE utf8mb4_general_ci AS name,
                               SUM(goi.quantity) AS total_qty,
                               COALESCE(SUM(goi.total_price), 0) AS total_revenue
                        FROM Groceries_order_items goi
                        INNER JOIN Groceries_orders go ON go.order_id = goi.order_id
                        INNER JOIN Groceries_Products p ON p.product_id = goi.product_id
                        WHERE go.business_id IN ({ids_sql}) {gro_ord_date_sql_join}
                          AND go.order_status = 'delivered'
                        GROUP BY CONVERT(p.product_name USING utf8mb4) COLLATE utf8mb4_general_ci
                        """
                    )
                    union_params = union_params + ids_params + gro_ord_date_params_join
                union_parts.append(
                    f"""
                    SELECT CONVERT(bci.item_name USING utf8mb4) COLLATE utf8mb4_general_ci AS name,
                           SUM(bci.quantity) AS total_qty,
                           COALESCE(SUM(bci.line_total), 0) AS total_revenue
                    FROM business_counter_items bci
                    INNER JOIN business_counter_orders bco ON bco.order_id = bci.order_id
                    WHERE bci.business_id IN ({ids_sql}) {co_date_sql_join}
                      AND bco.status = 'paid'
                    GROUP BY CONVERT(bci.item_name USING utf8mb4) COLLATE utf8mb4_general_ci
                    """
                )
                union_params = union_params + ids_params + co_date_params_join
                union_sql = " UNION ALL ".join(union_parts)
                final_sql = f"""
                    SELECT name, SUM(total_qty) AS total_qty, SUM(total_revenue) AS total_revenue
                    FROM (
                        {union_sql}
                    ) t
                    GROUP BY name
                    ORDER BY total_qty DESC, total_revenue DESC
                    LIMIT {top_limit}
                """
                cursor.execute(final_sql, union_params)
                rows_combined = cursor.fetchall() or []
                top_combined = [
                    {"name": r[0], "quantity": int(r[1] or 0), "revenue": float(r[2] or 0.0), "revenue_formatted": _format_indian_currency(float(r[2] or 0.0))} for r in rows_combined
                ]

                top_selling = {
                    "kirazee": top_kirazee,
                    "my_order_online": top_rk,
                    "counter_orders": top_counter_orders_items,
                    "combined": top_combined,
                    "limit": top_limit,
                }

                # Comprehensive Counter Summary from business_counter_orders and business_counter_items
                counter_summary = {
                    "summary": {
                        "total_orders": int(co_order_count),
                        "paid_orders": int(co_paid_count),
                        "pending_orders": int(co_pending_count),
                        "cancelled_orders": int(co_cancelled_count),
                        "gross_total": float(co_gross),
                        "gross_total_formatted": _format_indian_currency(float(co_gross)),
                        "subtotal": float(co_subtotal),
                        "subtotal_formatted": _format_indian_currency(float(co_subtotal)),
                        "average_order_value": float(co_avg_order_value),
                        "average_order_value_formatted": _format_indian_currency(float(co_avg_order_value))
                    },
                    "items_statistics": {
                        "total_items_sold": int(co_total_items_sold or 0),
                        "total_quantity_sold": int(co_total_quantity_sold or 0),
                        "total_items_revenue": float(co_total_items_revenue or 0),
                        "total_items_revenue_formatted": _format_indian_currency(float(co_total_items_revenue or 0)),
                        "average_items_per_order": round(co_avg_items_per_order, 2)
                    },
                    "collections": {
                        "cash": {
                            "amount": float(co_cash),
                            "amount_formatted": _format_indian_currency(float(co_cash)),
                            "count": 0,  # Will be updated below
                        },
                        "upi": {
                            "amount": float(co_upi),
                            "amount_formatted": _format_indian_currency(float(co_upi)),
                            "count": 0,  # Will be updated below
                        },
                        "card": {
                            "amount": float(co_card),
                            "amount_formatted": _format_indian_currency(float(co_card)),
                            "count": 0,  # Will be updated below
                        },
                        "razorpay": {
                            "amount": float(co_razorpay),
                            "amount_formatted": _format_indian_currency(float(co_razorpay)),
                            "count": 0,  # Will be updated below
                        },
                        "total_collections": float(co_cash) + float(co_upi) + float(co_card) + float(co_razorpay),
                        "total_collections_formatted": _format_indian_currency(float(co_cash) + float(co_upi) + float(co_card) + float(co_razorpay))
                    },
                    "charges_and_taxes": {
                        "subtotal": float(co_subtotal),
                        "subtotal_formatted": _format_indian_currency(float(co_subtotal)),
                        "discount": float(co_discount),
                        "discount_formatted": _format_indian_currency(float(co_discount)),
                        "gst_total": float(co_gst),
                        "gst_total_formatted": _format_indian_currency(float(co_gst)),
                        "total_amount": float(co_gross),
                        "total_amount_formatted": _format_indian_currency(float(co_gross))
                    },
                    "order_type_breakdown": {
                        "menu_orders": 0,  # Will be updated below
                        "grocery_orders": 0,  # Will be updated below
                    },
                    "status_breakdown": {
                        "paid": {
                            "count": int(co_paid_count),
                            "amount": float(co_gross),
                            "amount_formatted": _format_indian_currency(float(co_gross))
                        },
                        "pending": {
                            "count": int(co_pending_count),
                            "amount": 0.0,  # Can be calculated if needed
                            "amount_formatted": "0.00"
                        },
                        "cancelled": {
                            "count": int(co_cancelled_count),
                            "amount": 0.0,  # Can be calculated if needed
                            "amount_formatted": "0.00"
                        },
                    },
                }

                # Get order type breakdown
                cursor.execute(
                    f"""
                    SELECT
                        COALESCE(order_type, 'unknown') as order_type,
                        COUNT(*) as order_count,
                        COALESCE(SUM(CASE WHEN status='paid' THEN total_amount ELSE 0 END), 0) as total_amount
                    FROM business_counter_orders
                    WHERE business_id IN ({ids_sql}) {co_date_sql}
                      AND status = 'paid'
                    GROUP BY order_type
                    """,
                    ids_params + co_date_params
                )
                order_type_rows = cursor.fetchall() or []
                for row in order_type_rows:
                    order_type = str(row[0]).lower() if row[0] else "unknown"
                    count = int(row[1] or 0)
                    amount = float(row[2] or 0)
                    if order_type == "menu":
                        counter_summary["order_type_breakdown"]["menu_orders"] = count
                    elif order_type == "grocery":
                        counter_summary["order_type_breakdown"]["grocery_orders"] = count

                # Get payment method counts
                cursor.execute(
                    f"""
                    SELECT
                        payment_method,
                        COUNT(*) as order_count,
                        COALESCE(SUM(total_amount), 0) as total_amount
                    FROM business_counter_orders
                    WHERE business_id IN ({ids_sql}) {co_date_sql}
                      AND status = 'paid'
                    GROUP BY payment_method
                    """,
                    ids_params + co_date_params
                )
                payment_method_rows = cursor.fetchall() or []
                for row in payment_method_rows:
                    payment_method = str(row[0]).lower() if row[0] else ""
                    count = int(row[1] or 0)
                    amount = float(row[2] or 0)
                    # Update payment method breakdown
                    if payment_method == "cash" and "cash" in counter_summary["collections"]:
                        counter_summary["collections"]["cash"]["count"] = count
                        counter_summary["collections"]["cash"]["amount"] = amount
                    elif payment_method == "upi" and "upi" in counter_summary["collections"]:
                        counter_summary["collections"]["upi"]["count"] = count
                        counter_summary["collections"]["upi"]["amount"] = amount
                    elif payment_method == "card" and "card" in counter_summary["collections"]:
                        counter_summary["collections"]["card"]["count"] = count
                        counter_summary["collections"]["card"]["amount"] = amount
                    elif payment_method == "razorpay" and "razorpay" in counter_summary["collections"]:
                        counter_summary["collections"]["razorpay"]["count"] = count
                        counter_summary["collections"]["razorpay"]["amount"] = amount

                # Get pending and cancelled order amounts if needed
                cursor.execute(
                    f"""
                    SELECT
                        COALESCE(SUM(CASE WHEN status='pending' THEN total_amount ELSE 0 END), 0) as pending_amount,
                        COALESCE(SUM(CASE WHEN status='cancelled' THEN total_amount ELSE 0 END), 0) as cancelled_amount
                    FROM business_counter_orders
                    WHERE business_id IN ({ids_sql}) {co_date_sql}
                    """,
                    ids_params + co_date_params
                )
                status_amount_row = cursor.fetchone() or (0, 0)
                counter_summary["status_breakdown"]["pending"]["amount"] = float(status_amount_row[0] or 0)
                counter_summary["status_breakdown"]["cancelled"]["amount"] = float(status_amount_row[1] or 0)

                # Update total collections
                counter_summary["collections"]["total_collections"] = (
                    counter_summary["collections"]["cash"]["amount"]
                    + counter_summary["collections"]["upi"]["amount"]
                    + counter_summary["collections"]["card"]["amount"]
                    + counter_summary["collections"]["razorpay"]["amount"]
                )

                # Get financial breakdown data
                financials = self._get_financial_breakdown(
                    cursor, included_business_ids, date_from, date_to, business_type
                )

                # Calculate order summary variables
                pickup_orders_count = int(ord_pickup_delivered_count) + int(gro_pickup_delivered_count)
                pickup_orders_amount = float(ord_pickup_revenue) + float(gro_pickup_revenue)
                pickup_orders_collections = float(pay_pickup_total) + float(gpay_pickup_total)
                
                delivered_orders_count = int(ord_delivered_count) + int(gro_delivered_count)
                delivered_orders_amount = float(ord_delivered_revenue) + float(gro_delivered_revenue)
                delivered_orders_collections = float(pay_delivery_total) + float(gpay_delivery_total)
                
                kirazee_delivery_count = int(ord_delivered_count) - int(ord_pickup_delivered_count)
                kirazee_delivery_amount = float(ord_delivered_revenue) - float(ord_pickup_revenue)
                rk_delivery_count = int(gro_delivered_count) - int(gro_pickup_delivered_count)
                rk_delivery_amount = float(gro_delivered_revenue) - float(gro_pickup_revenue)

                # Charges and discounts summary
                charges_and_discounts = {
                    "total_delivery_charges": float(ord_delivery_charges) + float(gro_delivery_charge),
                    "total_delivery_charges_formatted": _format_indian_currency(float(ord_delivery_charges) + float(gro_delivery_charge)),
                    "total_parcel_charges": float(ord_parcel_charges),
                    "total_parcel_charges_formatted": _format_indian_currency(float(ord_parcel_charges)),
                    "total_discounts": float(ord_discount) + float(gro_discount) + float(co_discount),
                    "total_discounts_formatted": _format_indian_currency(float(ord_discount) + float(gro_discount) + float(co_discount)),
                    "total_charges": float(ord_delivery_charges) + float(ord_parcel_charges) + float(gro_delivery_charge),
                    "total_charges_formatted": _format_indian_currency(float(ord_delivery_charges) + float(ord_parcel_charges) + float(gro_delivery_charge))
                }

                # Top selling products (optional: limit via query param top_limit)
                top_limit_param = request.query_params.get("top_limit")
                try:
                    top_limit = max(1, min(20, int(top_limit_param))) if top_limit_param else 5
                except Exception:
                    top_limit = 5

                # Kirazee (restaurant) top items by quantity (then revenue)
                cursor.execute(
                    f"""
                    SELECT
                        oi.item_name_snapshot AS name,
                        SUM(oi.quantity) AS total_qty,
                        COALESCE(SUM(oi.total_price), 0) AS total_revenue
                    FROM order_items oi
                    INNER JOIN orders o ON o.order_id = oi.order_id
                    WHERE o.business_id IN ({ids_sql}) {ord_date_sql}
                      AND o.status IN ('delivered','completed')
                    GROUP BY oi.item_name_snapshot
                    ORDER BY total_qty DESC, total_revenue DESC
                    LIMIT {top_limit}
                    """,
                    ids_params + ord_date_params
                )
                rows_k = cursor.fetchall() or []
                top_kirazee = [
                    {"name": r[0], "quantity": int(r[1] or 0), "revenue": float(r[2] or 0.0), "revenue_formatted": _format_indian_currency(float(r[2] or 0.0))} for r in rows_k
                ]

                # RK Supermarket (groceries) top items
                if business_type == 'R01':
                    cursor.execute(
                        f"""
                        SELECT
                            p.product_name AS name,
                            SUM(goi.quantity) AS total_qty,
                            COALESCE(SUM(goi.total_price), 0) AS total_revenue
                        FROM Groceries_order_items goi
                        INNER JOIN Groceries_orders go ON go.order_id = goi.order_id
                        INNER JOIN Groceries_Products p ON p.product_id = goi.product_id
                        WHERE go.business_id IN ({ids_sql}) {gro_ord_date_sql_join}
                          AND go.order_status = 'delivered'
                        GROUP BY p.product_name
                        ORDER BY total_qty DESC, total_revenue DESC
                        LIMIT {top_limit}
                        """,
                        ids_params + gro_ord_date_params_join
                    )
                    rows_rk = cursor.fetchall() or []
                    top_rk = [
                        {"name": r[0], "quantity": int(r[1] or 0), "revenue": float(r[2] or 0.0), "revenue_formatted": _format_indian_currency(float(r[2] or 0.0))} for r in rows_rk
                    ]
                else:
                    top_rk = []

                # Counter orders items top items
                cursor.execute(
                    f"""
                    SELECT
                        bci.item_name AS name,
                        SUM(bci.quantity) AS total_qty,
                        COALESCE(SUM(bci.line_total), 0) AS total_revenue
                    FROM business_counter_items bci
                    INNER JOIN business_counter_orders bco ON bco.order_id = bci.order_id
                    WHERE bci.business_id IN ({ids_sql}) {co_date_sql_join}
                      AND bco.status = 'paid'
                    GROUP BY bci.item_name
                    ORDER BY total_qty DESC, total_revenue DESC
                    LIMIT {top_limit}
                    """,
                    ids_params + co_date_params_join
                )
                rows_co_items = cursor.fetchall() or []
                top_counter_orders_items = [
                    {"name": r[0], "quantity": int(r[1] or 0), "revenue": float(r[2] or 0.0), "revenue_formatted": _format_indian_currency(float(r[2] or 0.0))} for r in rows_co_items
                ]

                # Combined top items across all sources (by name)
                # Build combined top items conditionally (include groceries only for R01)
                union_parts = [
                    f"""
                    SELECT CONVERT(oi.item_name_snapshot USING utf8mb4) COLLATE utf8mb4_general_ci AS name,
                           SUM(oi.quantity) AS total_qty,
                           COALESCE(SUM(oi.total_price), 0) AS total_revenue
                    FROM order_items oi
                    INNER JOIN orders o ON o.order_id = oi.order_id
                    WHERE o.business_id IN ({ids_sql}) {ord_date_sql}
                      AND o.status IN ('delivered','completed')
                    GROUP BY CONVERT(oi.item_name_snapshot USING utf8mb4) COLLATE utf8mb4_general_ci
                    """
                ]
                union_params = ids_params + ord_date_params
                if business_type == 'R01':
                    union_parts.append(
                        f"""
                        SELECT CONVERT(p.product_name USING utf8mb4) COLLATE utf8mb4_general_ci AS name,
                               SUM(goi.quantity) AS total_qty,
                               COALESCE(SUM(goi.total_price), 0) AS total_revenue
                        FROM Groceries_order_items goi
                        INNER JOIN Groceries_orders go ON go.order_id = goi.order_id
                        INNER JOIN Groceries_Products p ON p.product_id = goi.product_id
                        WHERE go.business_id IN ({ids_sql}) {gro_ord_date_sql_join}
                          AND go.order_status = 'delivered'
                        GROUP BY CONVERT(p.product_name USING utf8mb4) COLLATE utf8mb4_general_ci
                        """
                    )
                    union_params = union_params + ids_params + gro_ord_date_params_join
                union_parts.append(
                    f"""
                    SELECT CONVERT(bci.item_name USING utf8mb4) COLLATE utf8mb4_general_ci AS name,
                           SUM(bci.quantity) AS total_qty,
                           COALESCE(SUM(bci.line_total), 0) AS total_revenue
                    FROM business_counter_items bci
                    INNER JOIN business_counter_orders bco ON bco.order_id = bci.order_id
                    WHERE bci.business_id IN ({ids_sql}) {co_date_sql_join}
                      AND bco.status = 'paid'
                    GROUP BY CONVERT(bci.item_name USING utf8mb4) COLLATE utf8mb4_general_ci
                    """
                )
                union_params = union_params + ids_params + co_date_params_join
                union_sql = " UNION ALL ".join(union_parts)
                final_sql = f"""
                    SELECT name, SUM(total_qty) AS total_qty, SUM(total_revenue) AS total_revenue
                    FROM (
                        {union_sql}
                    ) t
                    GROUP BY name
                    ORDER BY total_qty DESC, total_revenue DESC
                    LIMIT {top_limit}
                """
                cursor.execute(final_sql, union_params)
                rows_combined = cursor.fetchall() or []
                top_combined = [
                    {"name": r[0], "quantity": int(r[1] or 0), "revenue": float(r[2] or 0.0), "revenue_formatted": _format_indian_currency(float(r[2] or 0.0))} for r in rows_combined
                ]

                top_selling = {
                    "kirazee": top_kirazee,
                    "my_order_online": top_rk,
                    "counter_orders": top_counter_orders_items,
                    "combined": top_combined,
                    "limit": top_limit,
                }
                
                inventory_status = self._get_inventory_status(
                    cursor, ids_sql, ids_params, co_date_sql_join, co_date_params_join, 
                    ord_date_sql, ord_date_params, gro_ord_date_sql_join, gro_ord_date_params_join, 
                    business_type=business_type
                )

                # Get financial trend data - use main date range if trend parameters not provided
                if not trend_from and not trend_to and not trend_months:
                    # Use main date range for trend if no specific trend parameters provided
                    trend_from = date_from
                    trend_to = date_to
                
                financial_trend = self._get_financial_trend(
                    cursor, included_business_ids, trend_from, trend_to, trend_months, business_type
                )

                return Response({
                    "success": True,
                    "message": "Sales summary retrieved successfully",
                    "inputs": {
                        "business_id": base_business_id,
                        "date_from": date_from,
                        "date_to": date_to,
                        "include_branches": include_branches,
                    },
                    "scope": {
                        "is_master": is_master,
                        "base_business_name": base_business_name,
                        "included_business_ids": included_business_ids,
                    },
                    "financials": financials,
                    "financial_trend": financial_trend,
                    "collections": collections,
                    "orders_summary": {
                        "pickup_orders": {
                            "count": pickup_orders_count,
                            "amount": pickup_orders_amount,
                            "amount_formatted": _format_indian_currency(pickup_orders_amount),
                            "collections": pickup_orders_collections,
                            "collections_formatted": _format_indian_currency(pickup_orders_collections),
                            "sources": {
                                "kirazee": {
                                    "count": int(ord_pickup_delivered_count),
                                    "amount": float(ord_pickup_revenue),
                                    "amount_formatted": _format_indian_currency(float(ord_pickup_revenue)),
                                    "collections": float(pay_pickup_total),
                                    "collections_formatted": _format_indian_currency(float(pay_pickup_total))
                                },
                                "my_order_online": {
                                    "count": int(gro_pickup_delivered_count),
                                    "amount": float(gro_pickup_revenue),
                                    "amount_formatted": _format_indian_currency(float(gro_pickup_revenue)),
                                    "collections": float(gpay_pickup_total),
                                    "collections_formatted": _format_indian_currency(float(gpay_pickup_total))
                                }
                            }
                        },
                        "delivered_orders": {
                            "count": delivered_orders_count,
                            "amount": delivered_orders_amount,
                            "amount_formatted": _format_indian_currency(delivered_orders_amount),
                            "collections": delivered_orders_collections,
                            "collections_formatted": _format_indian_currency(delivered_orders_collections),
                            "sources": {
                                "kirazee": {
                                    "count": kirazee_delivery_count,
                                    "amount": kirazee_delivery_amount,
                                    "amount_formatted": _format_indian_currency(kirazee_delivery_amount),
                                    "collections": float(pay_delivery_total),
                                    "collections_formatted": _format_indian_currency(float(pay_delivery_total))
                                },
                                "my_order_online": {
                                    "count": rk_delivery_count,
                                    "amount": rk_delivery_amount,
                                    "amount_formatted": _format_indian_currency(rk_delivery_amount),
                                    "collections": float(gpay_delivery_total),
                                    "collections_formatted": _format_indian_currency(float(gpay_delivery_total))
                                }
                            }
                        },
                    },
                    "charges_and_discounts": charges_and_discounts,
                    "counter_summary": counter_summary,
                    "channel_performance": channel_performance,
                    "inventory_valuation": {
                        "total_stock_value_at_cost": total_stock_value_at_cost,
                        "total_stock_value_at_cost_formatted": _format_indian_currency(total_stock_value_at_cost),
                        "total_stock_value_at_mrp": total_stock_value_at_mrp,
                        "total_stock_value_at_mrp_formatted": _format_indian_currency(total_stock_value_at_mrp),
                        "potential_profit": potential_profit,
                        "potential_profit_formatted": _format_indian_currency(potential_profit)
                    },
                    "operational_profit": float(operational_profit),
                    "operational_profit_formatted": _format_indian_currency(operational_profit),
                    "avg_transaction_value": float(avg_transaction_value),
                    "avg_transaction_value_formatted": _format_indian_currency(avg_transaction_value),
                    "comparison_metrics": comparison_metrics,
                    "top_selling": top_selling,
                    "inventory_status": inventory_status,
                }, status=status.HTTP_200_OK)

        except Exception as e:
            logger.exception("Error retrieving sales summary")
            return Response({
                "success": False,
                "message": f"Error retrieving sales summary: {str(e)}"
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    def _get_financial_trend(self, cursor, business_ids, trend_from=None, trend_to=None, trend_months=None, business_type=None):
        """
        Get configurable financial performance trend for the given business(es)
        Returns a dictionary with monthly trend data based on URL parameters
        """
        # Parse date strings to date objects
        parsed_trend_from = None
        parsed_trend_to = None
        
        if trend_from:
            try:
                # Handle both YYYY-MM-DD and full datetime formats
                if len(trend_from) > 10:
                    parsed_trend_from = datetime.strptime(trend_from.split(' ')[0], '%Y-%m-%d').date()
                else:
                    parsed_trend_from = datetime.strptime(trend_from, '%Y-%m-%d').date()
            except (ValueError, TypeError):
                parsed_trend_from = None
                
        if trend_to:
            try:
                # Handle both YYYY-MM-DD and full datetime formats
                if len(trend_to) > 10:
                    parsed_trend_to = datetime.strptime(trend_to.split(' ')[0], '%Y-%m-%d').date()
                else:
                    parsed_trend_to = datetime.strptime(trend_to, '%Y-%m-%d').date()
            except (ValueError, TypeError):
                parsed_trend_to = None
        
        # Set default trend period if not provided
        if not parsed_trend_from or not parsed_trend_to:
            if trend_months:
                try:
                    months_back = int(trend_months)
                except (ValueError, TypeError):
                    months_back = 12
            else:
                months_back = 12
            
            # Default to last N months from today
            today = date.today()
            parsed_trend_to = today
            parsed_trend_from = today.replace(day=1) - timedelta(days=30 * (months_back - 1))
            parsed_trend_from = parsed_trend_from.replace(day=1)
        
        logger.info(f"[DEBUG] _get_financial_trend called with trend_from: {parsed_trend_from}, trend_to: {parsed_trend_to}, trend_months: {trend_months}")
        
        ids_sql, ids_params = _build_in_clause(business_ids)
        
        # Generate monthly trend data using raw string to avoid format character issues
        monthly_query = r"""
            SELECT 
                DATE_FORMAT(month_period, '%%Y-%%m') as month,
                COALESCE(SUM(month_sales), 0) as sales,
                COALESCE(SUM(month_expenses), 0) as expenses,
                COALESCE(SUM(month_purchases), 0) as purchases,
                COALESCE(SUM(month_sales), 0) - COALESCE(SUM(month_expenses), 0) - COALESCE(SUM(month_purchases), 0) as revenue
            FROM (
                -- Restaurant orders
                SELECT 
                    DATE_FORMAT(created_at, '%%Y-%%m-01') as month_period,
                    final_amount as month_sales,
                    0 as month_expenses,
                    0 as month_purchases
                FROM orders 
                WHERE business_id IN ({}) AND status IN ('delivered','completed') 
                  AND created_at BETWEEN %s AND %s
                
                UNION ALL
                
                -- Grocery orders  
                SELECT 
                    DATE_FORMAT(created_at, '%%Y-%%m-01') as month_period,
                    final_amount as month_sales,
                    0 as month_expenses,
                    0 as month_purchases
                FROM Groceries_orders 
                WHERE business_id IN ({}) AND order_status='delivered' 
                  AND created_at BETWEEN %s AND %s
                
                UNION ALL
                
                -- Counter orders
                SELECT 
                    DATE_FORMAT(created_at, '%%Y-%%m-01') as month_period,
                    total_amount as month_sales,
                    0 as month_expenses,
                    0 as month_purchases
                FROM business_counter_orders 
                WHERE business_id IN ({}) AND status='paid' 
                  AND created_at BETWEEN %s AND %s
                
                UNION ALL
                
                -- Expenses
                SELECT 
                    DATE_FORMAT(expense_date, '%%Y-%%m-01') as month_period,
                    0 as month_sales,
                    amount as month_expenses,
                    0 as month_purchases
                FROM Expenses
                WHERE business_id IN ({}) 
                  AND expense_date BETWEEN %s AND %s
                
                UNION ALL
                
                -- Purchases
                SELECT 
                    DATE_FORMAT(purchase_date, '%%Y-%%m-01') as month_period,
                    0 as month_sales,
                    0 as month_expenses,
                    total_amount as month_purchases
                FROM Purchases
                WHERE business_id IN ({}) 
                  AND purchase_date BETWEEN %s AND %s
            ) all_data
            GROUP BY month_period
            ORDER BY month_period DESC
        """.format(ids_sql, ids_sql, ids_sql, ids_sql, ids_sql)
        
        # Prepare parameters for all 5 subqueries
        monthly_params = []
        for _ in range(5):
            monthly_params.extend(ids_params)  # business_id IN (%s) for each subquery
            monthly_params.extend([parsed_trend_from, parsed_trend_to])  # date range for each subquery
        
        logger.info("[DEBUG] Financial trend query: %s", monthly_query)
        logger.info("[DEBUG] Financial trend params: %s", monthly_params)
        
        try:
            cursor.execute(monthly_query, monthly_params)
            monthly_results = cursor.fetchall() or []
            logger.info("[DEBUG] Financial trend results: %s", monthly_results)
        except Exception as e:
            logger.error("[ERROR] Error in financial trend calculation: %s", str(e))
            logger.error("[ERROR] Query: %s", monthly_query)
            logger.error("[ERROR] Params: %s", monthly_params)
            return {"trend": [], "summary": {"total_months": 0, "total_revenue": 0}}
        
        # Process results
        trend_data = []
        total_revenue = 0.0
        
        for month, sales, expenses, purchases, revenue in monthly_results:
            month_revenue = float(revenue or 0)
            total_revenue += month_revenue
            
            trend_data.append({
                "month": month,
                "sales": float(sales or 0),
                "sales_formatted": _format_indian_currency(float(sales or 0)),
                "expenses": float(expenses or 0),
                "expenses_formatted": _format_indian_currency(float(expenses or 0)),
                "purchases": float(purchases or 0),
                "purchases_formatted": _format_indian_currency(float(purchases or 0)),
                "revenue": month_revenue,
                "revenue_formatted": _format_indian_currency(month_revenue)
            })
        
        return {
            "trend": trend_data,
            "summary": {
                "total_months": len(trend_data),
                "total_revenue": total_revenue,
                "total_revenue_formatted": _format_indian_currency(total_revenue),
                "average_monthly_revenue": total_revenue / len(trend_data) if trend_data else 0,
                "average_monthly_revenue_formatted": _format_indian_currency(total_revenue / len(trend_data) if trend_data else 0)
            },
            "parameters": {
                "trend_from": trend_from,
                "trend_to": trend_to,
                "trend_months": trend_months
            }
        }


    def _get_inventory_status(self, cursor, ids_sql, ids_params, co_date_sql, co_date_params, ord_date_sql, ord_date_params, gro_ord_date_sql, gro_ord_date_params, business_type=None):
        """
        Calculate inventory status metrics.
        Note: co_date_sql and gro_ord_date_sql must use table aliases (bco.created_at, go.created_at) 
        as they are used in JOIN queries.
        """
        total_items_sold = 0
        categories_count = 0

        # 1. Total Items Sold
        try:
            # From counter orders
            cursor.execute(f"""
                SELECT SUM(bci.quantity)
                FROM business_counter_items bci
                INNER JOIN business_counter_orders bco ON bco.order_id = bci.order_id
                WHERE bci.business_id IN ({ids_sql}) {co_date_sql}
                  AND bco.status = 'paid'
            """, ids_params + co_date_params)
            row = cursor.fetchone()
            if row and row[0]:
                total_items_sold += int(row[0])
                
            # From Kirazee/Unified online orders
            cursor.execute(f"""
                SELECT SUM(oi.quantity)
                FROM order_items oi
                INNER JOIN orders o ON o.order_id = oi.order_id
                WHERE o.business_id IN ({ids_sql}) {ord_date_sql}
                  AND o.status IN ('delivered', 'completed')
            """, ids_params + ord_date_params)
            row = cursor.fetchone()
            if row and row[0]:
                total_items_sold += int(row[0])
                
            # From Grocery orders (legacy/R01 specific)
            if (business_type or '').upper() == 'R01':
                cursor.execute(f"""
                    SELECT SUM(goi.quantity)
                    FROM Groceries_order_items goi
                    INNER JOIN Groceries_orders go ON go.order_id = goi.order_id
                    WHERE go.business_id IN ({ids_sql}) {gro_ord_date_sql}
                      AND go.order_status = 'delivered'
                """, ids_params + gro_ord_date_params)
                row = cursor.fetchone()
                if row and row[0]:
                    total_items_sold += int(row[0])
        except Exception as e:
            logger.error("Error calculating items sold: %s", str(e))
        
        # 2. Categories count
        try:
            cursor.execute(f"""
                SELECT COUNT(DISTINCT cm.category_id) 
                FROM category_mapping cm
                JOIN universal_Categories uc ON uc.category_id = cm.category_id
                WHERE cm.business_id IN ({ids_sql}) 
                  AND cm.is_active = 1
            """, ids_params)
            categories_count = int(cursor.fetchone()[0] or 0)
        except Exception as e:
            logger.error("Error calculating categories count: %s", str(e))
        
        # 3. Out of stock count
        try:
            if (business_type or '').upper() == 'R01':
                # For groceries, check variants stock
                # Note: DB table is Groceries_ProductVariants_1
                cursor.execute(f"""
                    SELECT COUNT(*) 
                    FROM Groceries_ProductVariants_1 v
                    JOIN Groceries_Products p ON p.product_id = v.product_id
                    WHERE p.business_id IN ({ids_sql})
                      AND v.stock <= 0 
                      AND v.is_active = 1
                      AND p.is_visible = 1
                """, ids_params)
            elif (business_type or '').upper() == 'R02':
                # For restaurants, check menu items quantity if tracked
                cursor.execute(f"""
                    SELECT COUNT(*) 
                    FROM menuItems 
                    WHERE business_id IN ({ids_sql})
                      AND quantity IS NOT NULL 
                      AND quantity <= 0 
                      AND is_active = 1
                """, ids_params)
            elif (business_type or '').upper() == 'R08':
                # For fashion, check variants stock
                cursor.execute(f"""
                    SELECT COUNT(*) 
                    FROM fashion_product_variants v
                    JOIN fashion_products p ON p.product_id = v.product_id
                    WHERE p.business_id IN ({ids_sql})
                      AND v.stock <= 0 
                      AND v.is_active = 1
                """, ids_params)
        except Exception as e:
            logger.error("Error calculating out of stock: %s", str(e))

        return {
            "total_items_sold": total_items_sold,
            "categories_count": categories_count,
        }
