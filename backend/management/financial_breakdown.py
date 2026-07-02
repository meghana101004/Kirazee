from datetime import datetime, timedelta, date
from django.db import connection
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
import logging

logger = logging.getLogger(__name__)

# Import helper functions from sales.py
def _normalize_date_bounds(date_from, date_to):
    df = str(date_from).strip() if date_from is not None else None
    dt = str(date_to).strip() if date_to is not None else None

    if df and len(df) == 10:
        df = f"{df} 00:00:00"
    if dt and len(dt) == 10:
        dt = f"{dt} 23:59:59"

    return df, dt


def _build_in_clause(ids):
    """Build IN clause and parameters for SQL queries"""
    if not ids:
        return "%s", ["__NONE__"]
    placeholders = ','.join(['%s'] * len(ids))
    return placeholders, list(ids)

def _date_filters(date_from, date_to, column_name):
    """Generate date filter SQL and parameters"""
    if date_from and date_to:
        return f"AND {column_name} BETWEEN %s AND %s", [date_from, date_to]
    elif date_from:
        return f"AND {column_name} >= %s", [date_from]
    elif date_to:
        return f"AND {column_name} <= %s", [date_to]
    else:
        return "", []

def _parse_bool(val, default=False):
    """Parse boolean value from string"""
    if val is None:
        return default
    if isinstance(val, bool):
        return val
    return str(val).strip().lower() in ('true', '1', 'yes', 'on')

class FinancialBreakdownView(APIView):
    """
    Dedicated financial breakdown service for business financial reporting
    Provides comprehensive financial metrics including:
    - Net Income (sales without GST, with delivery & parcel charges)
    - Sales (sales with GST and delivery & parcel charges)  
    - Expenses (expenses + salary)
    - Purchases (from Purchases table)
    - Revenue (Sales - Expenses - Purchases)
    - P&L (with carryover from previous months)
    """
    
    permission_classes = []
    
    def get(self, request):
        business_id = request.query_params.get("business_id")
        date_from = request.query_params.get("date_from")
        date_to = request.query_params.get("date_to")
        include_branches_param = request.query_params.get("include_branches")

        if not business_id:
            return Response({
                "success": False,
                "message": "business_id is required"
            }, status=status.HTTP_400_BAD_REQUEST)

        try:
            with connection.cursor() as cursor:
                # 1) Resolve business scope (master + branches if applicable)
                cursor.execute(
                    """
                    SELECT business_id, businessName, level, master, businessType 
                    FROM businesses 
                    WHERE business_id = %s
                    """,
                    [business_id]
                )
                row = cursor.fetchone()
                if not row:
                    return Response({
                        "success": False,
                        "message": "Business not found"
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

                # 2) Get financial breakdown
                financials = self._get_financial_breakdown(cursor, included_business_ids, date_from, date_to, business_type)

                return Response({
                    "success": True,
                    "message": "Financial breakdown retrieved successfully",
                    "inputs": {
                        "business_id": business_id,
                        "date_from": date_from,
                        "date_to": date_to,
                        "include_branches": include_branches
                    },
                    "scope": {
                        "is_master": is_master,
                        "base_business_name": base_business_name,
                        "included_business_ids": included_business_ids
                    },
                    "financials": financials
                })

        except Exception as e:
            logger.error(f"Error retrieving financial breakdown: {str(e)}")
            return Response({
                "success": False,
                "message": f"Error retrieving financial breakdown: {str(e)}"
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    def _get_financial_breakdown(self, cursor, business_ids, date_from=None, date_to=None, business_type=None):
        """
        Get comprehensive financial breakdown for the given business(es)
        Returns a dictionary with all financial metrics according to business requirements
        """
        ids_sql, ids_params = _build_in_clause(business_ids)

        date_from_dt, date_to_dt = _normalize_date_bounds(date_from, date_to)
        
        # Use the same date filtering approach as the main API
        co_date_sql, co_date_params = _date_filters(date_from_dt, date_to_dt, "created_at")  # For counter orders
        ord_date_sql, ord_date_params = _date_filters(date_from_dt, date_to_dt, "o.created_at")  # For orders
        gro_date_sql, gro_date_params = _date_filters(date_from_dt, date_to_dt, "go.created_at")  # For Groceries_orders
        
        print(f"DEBUG Financial Breakdown - Business IDs: {business_ids}")
        print(f"DEBUG Financial Breakdown - co_date_sql: {co_date_sql}")
        print(f"DEBUG Financial Breakdown - ord_date_sql: {ord_date_sql}")
        print(f"DEBUG Financial Breakdown - gro_date_sql: {gro_date_sql}")
        
        # 1. Get sales data from all sources with proper date filtering
        cursor.execute(f"""
            SELECT 
                COALESCE(SUM(final_amount), 0) as total_sales_with_gst,
                COALESCE(SUM(gst_amount), 0) as total_gst,
                COALESCE(SUM(discount), 0) as total_discount,
                COALESCE(SUM(delivery_charge), 0) as total_delivery,
                COALESCE(SUM(parcel_charge), 0) as total_parcel
            FROM (
                -- Restaurant orders
                SELECT final_amount, 0 as gst_amount, discount_amount as discount, delivery_charges as delivery_charge, parcel_charges as parcel_charge
                FROM orders o
                WHERE business_id IN ({ids_sql}) AND status IN ('delivered','completed') {ord_date_sql}
                UNION ALL
                -- Groceries orders  
                SELECT final_amount, gst_amount, discount, delivery_charge, 0 as parcel_charge
                FROM Groceries_orders go
                WHERE business_id IN ({ids_sql}) AND order_status='delivered' {gro_date_sql}
                UNION ALL
                -- Counter orders (using business_counter_orders)
                SELECT total_amount as final_amount, 0 as gst_amount, discount_amount as discount, 0 as delivery_charge, 0 as parcel_charge
                FROM business_counter_orders
                WHERE business_id IN ({ids_sql}) AND status='paid' {co_date_sql}
            ) combined_sales
        """, ids_params + ord_date_params + ids_params + gro_date_params + ids_params + co_date_params)
        
        sales_row = cursor.fetchone()
        total_sales_with_gst, total_gst, total_discount, total_delivery, total_parcel = sales_row or (0, 0, 0, 0, 0)
        
        print(f"DEBUG Financial Breakdown - Raw sales data: {sales_row}")
        
        # Convert to float for calculations
        total_sales_with_gst = float(total_sales_with_gst)
        total_gst = float(total_gst)
        total_discount = float(total_discount)
        total_delivery = float(total_delivery)
        total_parcel = float(total_parcel)
        
        # 2. Calculate Net Income (sales WITHOUT GST; final_amount already includes delivery/parcel)
        net_income = (total_sales_with_gst - total_gst)
        
        # 3. Calculate Sales total (WITH GST; final_amount already includes delivery/parcel)
        sales = total_sales_with_gst
        
        # 4. Get expenses from expenses table
        cursor.execute(f"""
            SELECT COALESCE(SUM(amount), 0) as total_expenses
            FROM Expenses
            WHERE business_id IN ({ids_sql}) AND expense_date BETWEEN %s AND %s
        """, ids_params + [date_from or '2020-01-01', date_to or '2030-12-31'])
        expenses_row = cursor.fetchone()
        expenses_without_salary = float(expenses_row[0] or 0)
        
        # 5. Get staff salaries
        sal_date_sql, sal_date_params = _date_filters(date_from_dt, date_to_dt, "created_at")
        cursor.execute(f"""
            SELECT COALESCE(SUM(salary_paid), 0) as total_salaries
            FROM business_staff_salary_payments
            WHERE business_id IN ({ids_sql}) {sal_date_sql}
        """, ids_params + sal_date_params)
        salaries_row = cursor.fetchone()
        salaries_total = float(salaries_row[0] or 0)
        
        # 6. Total expenses (expenses + salary)
        expenses = expenses_without_salary + salaries_total
        
        # 7. Get purchases from Purchases table
        cursor.execute(f"""
            SELECT COALESCE(SUM(total_amount), 0) as total_purchases
            FROM Purchases
            WHERE business_id IN ({ids_sql}) AND purchase_date BETWEEN %s AND %s
        """, ids_params + [date_from or '2020-01-01', date_to or '2030-12-31'])
        purchases_row = cursor.fetchone()
        purchases = float(purchases_row[0] or 0)
        
        # 8. Calculate Revenue = Sales - Expenses - Purchases
        revenue = sales - expenses - purchases
        
        # 9. P&L calculation with carryover from previous months
        pnl_carryover = 0.0
        prev_months = []
        
        try:
            curr_from = datetime.strptime(date_from, '%Y-%m-%d').date() if date_from else None
            curr_to = datetime.strptime(date_to, '%Y-%m-%d').date() if date_to else None
        except Exception:
            curr_from = None
            curr_to = None
            
        if curr_from and curr_to:
            # Calculate P&L for previous 6 months
            for i in range(1, 7):
                # Calculate month start by going back i months from current month start
                year = curr_from.year
                month = curr_from.month - i
                if month <= 0:
                    year -= 1
                    month += 12
                month_start = date(year, month, 1)
                
                # Calculate month end as the last day of that month
                if month == 12:
                    month_end = date(year + 1, 1, 1) - timedelta(days=1)
                else:
                    month_end = date(year, month + 1, 1) - timedelta(days=1)

                month_start_dt = datetime.combine(month_start, datetime.min.time())
                month_end_dt = datetime.combine(month_end, datetime.max.time()).replace(microsecond=0)
                
                cursor.execute(f"""
                    SELECT 
                        COALESCE(SUM(final_amount), 0) as month_sales,
                        COALESCE(SUM(amount), 0) as month_expenses,
                        COALESCE(SUM(total_amount), 0) as month_purchases
                    FROM (
                        SELECT final_amount, 0 as amount, 0 as total_amount
                        FROM orders 
                        WHERE business_id IN ({ids_sql}) AND status IN ('delivered','completed') 
                          AND created_at BETWEEN %s AND %s
                        UNION ALL
                        SELECT final_amount, 0, 0
                        FROM Groceries_orders 
                        WHERE business_id IN ({ids_sql}) AND order_status='delivered' 
                          AND created_at BETWEEN %s AND %s
                        UNION ALL
                        SELECT total_amount, 0, 0
                        FROM business_counter_orders 
                        WHERE business_id IN ({ids_sql}) AND status='paid' 
                          AND created_at BETWEEN %s AND %s
                        UNION ALL
                        SELECT 0, amount, 0
                        FROM Expenses
                        WHERE business_id IN ({ids_sql}) 
                          AND expense_date BETWEEN %s AND %s
                        UNION ALL
                        SELECT 0, 0, total_amount
                        FROM Purchases
                        WHERE business_id IN ({ids_sql}) 
                          AND purchase_date BETWEEN %s AND %s
                    ) monthly_data
                """, ids_params + [month_start_dt, month_end_dt] + ids_params + [month_start_dt, month_end_dt] + ids_params + [month_start_dt, month_end_dt] + ids_params + [month_start, month_end] + ids_params + [month_start, month_end])
                
                month_data = cursor.fetchone()
                month_sales, month_expenses, month_purchases = month_data or (0, 0, 0)
                month_sales = float(month_sales)
                month_expenses = float(month_expenses) 
                month_purchases = float(month_purchases)
                month_revenue = month_sales - month_expenses - month_purchases
                pnl_carryover += month_revenue
                prev_months.append({
                    "month": month_start.strftime('%Y-%m'),
                    "revenue": float(month_revenue)
                })
        
        # 10. Final P&L calculation
        current_month_revenue = revenue
        adjusted_pnl = current_month_revenue - pnl_carryover if pnl_carryover < 0 else current_month_revenue + pnl_carryover
        
        # Build response
        return {
            "calculation_rules": {
                "net_income_excludes_gst": True,
                "sales_includes_gst": True,
                "delivery_charges_included": True,
                "parcel_charges_included": True
            },
            "sales": {
                "total": float(sales),
                "gross_sales": float(total_sales_with_gst),
                "breakdown": {
                    "subtotal": float(total_sales_with_gst - total_gst),
                    "gst": float(total_gst),
                    "discount": float(total_discount),
                    "delivery": float(total_delivery),
                    "parcel": float(total_parcel)
                }
            },
            "expenses": {
                "total": float(expenses),
                "operational_expenses": float(expenses_without_salary),
                "salary_expenses": float(salaries_total)
            },
            "purchases": {
                "total": float(purchases),
                "note": "GST and other charges not available in Purchases table structure"
            },
            "net_income": float(net_income),
            "revenue": float(revenue),
            "p_and_l": {
                "current_month": {
                    "revenue": float(current_month_revenue),
                    "expenses": float(expenses),
                    "purchases": float(purchases),
                    "net": float(current_month_revenue)
                },
                "carryover_analysis": {
                    "past_months": prev_months,
                    "total_carryover": float(pnl_carryover),
                    "adjusted_p_and_l": float(adjusted_pnl)
                }
            }
        }
