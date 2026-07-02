from datetime import datetime, timedelta
from django.db import connection
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
import logging
from decimal import Decimal

logger = logging.getLogger(__name__)


def _parse_bool(val, default=False):
    """Parse boolean values from query parameters"""
    if val is None:
        return default
    if isinstance(val, bool):
        return val
    s = str(val).strip().lower()
    return s in {"1", "true", "yes", "y", "on"}


def _build_in_clause(values):
    """Return a tuple: (placeholders_sql, params_list). Ensures at least one placeholder."""
    if not values:
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
    df = str(date_from).strip() if date_from is not None else None
    dt = str(date_to).strip() if date_to is not None else None

    if df and len(df) == 10:
        df = f"{df} 00:00:00"
    if dt and len(dt) == 10:
        dt = f"{dt} 23:59:59"

    return df, dt


class ProfitLossReportView(APIView):
    """
    Comprehensive Profit & Loss Report API
    
    Calculates:
    - Total Revenue (Sales from all sources)
    - Cost of Goods Sold (COGS from purchases)
    - Gross Profit (Revenue - COGS)
    - Operating Expenses (from expenses table)
    - Net Profit (Gross Profit - Operating Expenses)
    
    Query params:
    - business_id: required
    - date_from, date_to: optional (YYYY-MM-DD)
    - include_branches: optional (true/false)
    - report_type: optional ('summary', 'detailed') - default 'summary'
    """
    
    permission_classes = []
    
    def get(self, request):
        business_id = request.query_params.get("business_id")
        date_from = request.query_params.get("date_from")
        date_to = request.query_params.get("date_to")
        include_branches_param = request.query_params.get("include_branches")
        report_type = request.query_params.get("report_type", "summary")
        
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
                    SELECT business_id, businessName, level, master 
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

                base_business_id, base_business_name, base_level, base_master = row
                is_master = str(base_level).strip().lower() == "master"

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

                date_from_dt, date_to_dt = _normalize_date_bounds(date_from, date_to)

                # Date filters for different tables
                co_date_sql, co_date_params = _date_filters(date_from_dt, date_to_dt, "created_at")  # Counter orders date filter
                ord_date_sql, ord_date_params = _date_filters(date_from_dt, date_to_dt, "o.created_at")
                pay_date_sql, pay_date_params = _date_filters(date_from_dt, date_to_dt, "p.created_at")
                gro_ord_date_sql, gro_ord_date_params = _date_filters(date_from_dt, date_to_dt, "created_at")
                gro_pay_date_sql, gro_pay_date_params = _date_filters(date_from_dt, date_to_dt, "gp.payment_date")
                purchase_date_sql, purchase_date_params = _date_filters(date_from, date_to, "purchase_date")
                expense_date_sql, expense_date_params = _date_filters(date_from, date_to, "expense_date")

                # ===== REVENUE CALCULATION =====
                
                # Counter Orders Revenue (from business_counter_orders, paid orders only)
                cursor.execute(
                    f"""
                    SELECT COALESCE(SUM(total_amount), 0) as counter_revenue
                    FROM business_counter_orders
                    WHERE business_id IN ({ids_sql}) 
                      AND status = 'paid' {co_date_sql}
                    """,
                    ids_params + co_date_params
                )
                counter_revenue = float(cursor.fetchone()[0] or 0)

                # Restaurant Orders Revenue (from payments)
                cursor.execute(
                    f"""
                    SELECT COALESCE(SUM(p.amount), 0) as restaurant_revenue
                    FROM payments p
                    INNER JOIN orders o ON o.order_id = p.order_id
                    WHERE o.business_id IN ({ids_sql})
                      AND o.status IN ('delivered','completed')
                      AND p.status = 'success'
                      {pay_date_sql}
                    """,
                    ids_params + pay_date_params
                )
                restaurant_revenue = float(cursor.fetchone()[0] or 0)

                # Grocery Orders Revenue (from payments)
                cursor.execute(
                    f"""
                    SELECT COALESCE(SUM(gp.amount), 0) as grocery_revenue
                    FROM Groceries_payments gp
                    INNER JOIN Groceries_orders go ON go.order_id = gp.order_id
                    WHERE go.business_id IN ({ids_sql})
                      AND go.order_status = 'delivered'
                      AND gp.payment_status = 'completed'
                      {gro_pay_date_sql}
                    """,
                    ids_params + gro_pay_date_params
                )
                grocery_revenue = float(cursor.fetchone()[0] or 0)

                total_revenue = counter_revenue + restaurant_revenue + grocery_revenue

                # ===== COST OF GOODS SOLD (COGS) =====
                
                # Get COGS from Purchase_Items
                cursor.execute(
                    f"""
                    SELECT COALESCE(SUM(pi.total_cost), 0) as total_cogs
                    FROM Purchase_Items pi
                    INNER JOIN Purchases p ON p.purchase_id = pi.purchase_id
                    WHERE p.business_id IN ({ids_sql}) {purchase_date_sql}
                    """,
                    ids_params + purchase_date_params
                )
                total_cogs = float(cursor.fetchone()[0] or 0)

                # ===== OPERATING EXPENSES =====
                
                # Get operating expenses
                cursor.execute(
                    f"""
                    SELECT 
                        COALESCE(SUM(amount), 0) as total_expenses,
                        COUNT(*) as expense_count
                    FROM Expenses
                    WHERE business_id IN ({ids_sql}) {expense_date_sql}
                    """,
                    ids_params + expense_date_params
                )
                expense_row = cursor.fetchone()
                total_expenses = float(expense_row[0] or 0)
                expense_count = int(expense_row[1] or 0)

                # ===== PROFIT CALCULATIONS =====
                
                gross_profit = total_revenue - total_cogs
                net_profit = gross_profit - total_expenses
                
                # Calculate margins
                gross_margin = (gross_profit / total_revenue * 100) if total_revenue > 0 else 0
                net_margin = (net_profit / total_revenue * 100) if total_revenue > 0 else 0

                # ===== DETAILED BREAKDOWN (if requested) =====
                detailed_data = {}
                
                if report_type == "detailed":
                    # Revenue breakdown by source
                    detailed_data["revenue_breakdown"] = {
                        "counter_orders": {
                            "amount": counter_revenue,
                            "percentage": (counter_revenue / total_revenue * 100) if total_revenue > 0 else 0
                        },
                        "kirazee web/app_orders": {
                            "amount": restaurant_revenue,
                            "percentage": (restaurant_revenue / total_revenue * 100) if total_revenue > 0 else 0
                        },
                        "custom_webiste_orders": {
                            "amount": grocery_revenue,
                            "percentage": (grocery_revenue / total_revenue * 100) if total_revenue > 0 else 0
                        }
                    }

                    # Expenses breakdown by category
                    cursor.execute(
                        f"""
                        SELECT 
                            category,
                            COALESCE(SUM(amount), 0) as category_total,
                            COUNT(*) as category_count
                        FROM Expenses
                        WHERE business_id IN ({ids_sql}) {expense_date_sql}
                        GROUP BY category
                        ORDER BY category_total DESC
                        """,
                        ids_params + expense_date_params
                    )
                    expense_categories = []
                    for row in cursor.fetchall():
                        expense_categories.append({
                            "category": row[0],
                            "amount": float(row[1] or 0),
                            "count": int(row[2] or 0),
                            "percentage": (float(row[1] or 0) / total_expenses * 100) if total_expenses > 0 else 0
                        })
                    
                    detailed_data["expense_breakdown"] = expense_categories

                    # Purchase breakdown by supplier (top 10)
                    cursor.execute(
                        f"""
                        SELECT 
                            s.supplier_name,
                            COALESCE(SUM(p.total_amount), 0) as supplier_total,
                            COUNT(p.purchase_id) as purchase_count
                        FROM Purchases p
                        LEFT JOIN Suppliers s ON s.supplier_id = p.supplier_id
                        WHERE p.business_id IN ({ids_sql}) {purchase_date_sql}
                        GROUP BY s.supplier_id, s.supplier_name
                        ORDER BY supplier_total DESC
                        LIMIT 10
                        """,
                        ids_params + purchase_date_params
                    )
                    top_suppliers = []
                    for row in cursor.fetchall():
                        top_suppliers.append({
                            "supplier_name": row[0] or "Unknown Supplier",
                            "amount": float(row[1] or 0),
                            "purchase_count": int(row[2] or 0),
                            "percentage": (float(row[1] or 0) / total_cogs * 100) if total_cogs > 0 else 0
                        })
                    
                    detailed_data["top_suppliers"] = top_suppliers

                # ===== RESPONSE =====
                
                response_data = {
                    "success": True,
                    "message": "Profit & Loss report generated successfully",
                    "report_info": {
                        "business_id": base_business_id,
                        "business_name": base_business_name,
                        "date_from": date_from,
                        "date_to": date_to,
                        "include_branches": include_branches,
                        "included_business_ids": included_business_ids,
                        "report_type": report_type,
                        "generated_at": datetime.now().isoformat()
                    },
                    "profit_loss_summary": {
                        "revenue": {
                            "total_revenue": total_revenue,
                            "counter_orders": counter_revenue,
                            "restaurant_orders": restaurant_revenue,
                            "grocery_orders": grocery_revenue
                        },
                        "cost_of_goods_sold": {
                            "total_cogs": total_cogs
                        },
                        "gross_profit": {
                            "amount": gross_profit,
                            "margin_percentage": round(gross_margin, 2)
                        },
                        "operating_expenses": {
                            "total_expenses": total_expenses,
                            "expense_count": expense_count
                        },
                        "net_profit": {
                            "amount": net_profit,
                            "margin_percentage": round(net_margin, 2)
                        }
                    },
                    "key_metrics": {
                        "revenue_per_day": total_revenue / max(1, (datetime.strptime(date_to, '%Y-%m-%d') - datetime.strptime(date_from, '%Y-%m-%d')).days + 1) if date_from and date_to else 0,
                        "cogs_percentage": (total_cogs / total_revenue * 100) if total_revenue > 0 else 0,
                        "expense_percentage": (total_expenses / total_revenue * 100) if total_revenue > 0 else 0,
                        "profit_per_revenue_rupee": net_profit / total_revenue if total_revenue > 0 else 0
                    }
                }

                # Add detailed data if requested
                if report_type == "detailed":
                    response_data["detailed_breakdown"] = detailed_data

                return Response(response_data, status=status.HTTP_200_OK)

        except Exception as e:
            logger.exception("Error generating profit & loss report")
            return Response({
                "success": False,
                "message": f"Error generating profit & loss report: {str(e)}"
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class BusinessPerformanceReportView(APIView):
    """
    Business Performance Report API
    
    Provides comparative analysis and trends:
    - Month-over-month comparison
    - Year-over-year comparison
    - Performance trends
    """
    
    permission_classes = []
    
    def get(self, request):
        business_id = request.query_params.get("business_id")
        comparison_type = request.query_params.get("comparison_type", "monthly")  # monthly, yearly
        periods = int(request.query_params.get("periods", 6))  # Number of periods to compare
        
        if not business_id:
            return Response({
                "success": False,
                "message": "business_id is required"
            }, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            with connection.cursor() as cursor:
                # Get business info
                cursor.execute(
                    "SELECT business_id, businessName FROM businesses WHERE business_id = %s",
                    [business_id]
                )
                business_row = cursor.fetchone()
                if not business_row:
                    return Response({
                        "success": False,
                        "message": f"Business {business_id} not found"
                    }, status=status.HTTP_404_NOT_FOUND)

                business_name = business_row[1]
                
                # Generate date ranges based on comparison type
                performance_data = []
                current_date = datetime.now()
                
                for i in range(periods):
                    if comparison_type == "monthly":
                        # Calculate month boundaries
                        if i == 0:
                            end_date = current_date.replace(day=1) - timedelta(days=1)
                        else:
                            end_date = (end_date.replace(day=1) - timedelta(days=1))
                        
                        start_date = end_date.replace(day=1)
                        period_label = end_date.strftime("%B %Y")
                        
                    else:  # yearly
                        year = current_date.year - i
                        start_date = datetime(year, 1, 1)
                        end_date = datetime(year, 12, 31)
                        period_label = str(year)
                    
                    # Get performance data for this period
                    period_data = self._get_period_performance(
                        cursor, business_id, start_date.date(), end_date.date()
                    )
                    period_data["period"] = period_label
                    period_data["start_date"] = start_date.date().isoformat()
                    period_data["end_date"] = end_date.date().isoformat()
                    
                    performance_data.append(period_data)
                
                # Calculate trends
                trends = self._calculate_trends(performance_data)
                
                return Response({
                    "success": True,
                    "message": "Business performance report generated successfully",
                    "report_info": {
                        "business_id": business_id,
                        "business_name": business_name,
                        "comparison_type": comparison_type,
                        "periods": periods,
                        "generated_at": datetime.now().isoformat()
                    },
                    "performance_data": performance_data,
                    "trends": trends
                }, status=status.HTTP_200_OK)
                
        except Exception as e:
            logger.exception("Error generating business performance report")
            return Response({
                "success": False,
                "message": f"Error generating business performance report: {str(e)}"
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    
    def _get_period_performance(self, cursor, business_id, start_date, end_date):
        """Get performance metrics for a specific period"""
        
        start_dt = start_date if isinstance(start_date, datetime) else datetime.combine(start_date, datetime.min.time())
        end_dt = end_date if isinstance(end_date, datetime) else datetime.combine(end_date, datetime.max.time())
        
        # Counter Orders Revenue for period (from business_counter_orders, paid orders only)
        cursor.execute(
            """
            SELECT 
                COALESCE(SUM(total_amount), 0) as counter_revenue
            FROM business_counter_orders
            WHERE business_id = %s 
              AND status = 'paid'
              AND created_at BETWEEN %s AND %s
            """,
            [business_id, start_dt, end_dt]
        )
        counter_revenue = float(cursor.fetchone()[0] or 0)
        
        # Restaurant revenue
        cursor.execute(
            """
            SELECT COALESCE(SUM(p.amount), 0) as restaurant_revenue
            FROM payments p
            INNER JOIN orders o ON o.order_id = p.order_id
            WHERE o.business_id = %s 
              AND o.status IN ('delivered','completed')
              AND p.status = 'success'
              AND p.created_at BETWEEN %s AND %s
            """,
            [business_id, start_dt, end_dt]
        )
        restaurant_revenue = float(cursor.fetchone()[0] or 0)
        
        # Grocery revenue
        cursor.execute(
            """
            SELECT COALESCE(SUM(gp.amount), 0) as grocery_revenue
            FROM Groceries_payments gp
            INNER JOIN Groceries_orders go ON go.order_id = gp.order_id
            WHERE go.business_id = %s
              AND go.order_status = 'delivered'
              AND gp.payment_status = 'completed'
              AND gp.payment_date BETWEEN %s AND %s
            """,
            [business_id, start_dt, end_dt]
        )
        grocery_revenue = float(cursor.fetchone()[0] or 0)
        
        total_revenue = counter_revenue + restaurant_revenue + grocery_revenue
        
        # COGS for period
        cursor.execute(
            """
            SELECT COALESCE(SUM(pi.total_cost), 0) as total_cogs
            FROM Purchase_Items pi
            INNER JOIN Purchases p ON p.purchase_id = pi.purchase_id
            WHERE p.business_id = %s AND p.purchase_date BETWEEN %s AND %s
            """,
            [business_id, start_date, end_date]
        )
        total_cogs = float(cursor.fetchone()[0] or 0)
        
        # Expenses for period
        cursor.execute(
            """
            SELECT COALESCE(SUM(amount), 0) as total_expenses
            FROM Expenses
            WHERE business_id = %s AND expense_date BETWEEN %s AND %s
            """,
            [business_id, start_date, end_date]
        )
        total_expenses = float(cursor.fetchone()[0] or 0)
        
        # Calculate metrics
        gross_profit = total_revenue - total_cogs
        net_profit = gross_profit - total_expenses
        
        return {
            "total_revenue": total_revenue,
            "total_cogs": total_cogs,
            "total_expenses": total_expenses,
            "gross_profit": gross_profit,
            "net_profit": net_profit,
            "gross_margin": (gross_profit / total_revenue * 100) if total_revenue > 0 else 0,
            "net_margin": (net_profit / total_revenue * 100) if total_revenue > 0 else 0
        }
    
    def _calculate_trends(self, performance_data):
        """Calculate trends from performance data"""
        if len(performance_data) < 2:
            return {"message": "Insufficient data for trend analysis"}
        
        # Compare latest period with previous period
        latest = performance_data[0]
        previous = performance_data[1]
        
        def calculate_change(current, prev):
            if prev == 0:
                return 100 if current > 0 else 0
            return ((current - prev) / prev) * 100
        
        return {
            "revenue_change": calculate_change(latest["total_revenue"], previous["total_revenue"]),
            "profit_change": calculate_change(latest["net_profit"], previous["net_profit"]),
            "margin_change": latest["net_margin"] - previous["net_margin"],
            "expense_change": calculate_change(latest["total_expenses"], previous["total_expenses"])
        }


class ComprehensiveDashboardReportView(APIView):
    """
    Comprehensive Dashboard Report API
    
    Provides all required metrics:
    - Overview/Summary with KPIs
    - Sales/Revenue analysis with top items
    - Inventory/Stock analysis
    - Customer insights
    - Operational metrics
    - Financial summary
    - Visual data for charts
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
                # Get business info (include type for routing)
                cursor.execute(
                    "SELECT business_id, businessName, level, businessType FROM businesses WHERE business_id = %s",
                    [business_id]
                )
                business_row = cursor.fetchone()
                if not business_row:
                    return Response({
                        "success": False,
                        "message": f"Business {business_id} not found"
                    }, status=status.HTTP_404_NOT_FOUND)

                business_name = business_row[1]
                is_master = str(business_row[2]).strip().lower() == "master"
                business_type = str(business_row[3] or "").strip().upper()
                
                included_business_ids = [business_id]
                include_branches = _parse_bool(include_branches_param, default=is_master)
                
                if include_branches:
                    cursor.execute(
                        "SELECT business_id FROM businesses WHERE master = %s",
                        [business_id]
                    )
                    branch_rows = cursor.fetchall() or []
                    included_business_ids.extend([r[0] for r in branch_rows])

                ids_sql, ids_params = _build_in_clause(included_business_ids)

                date_from_dt, date_to_dt = _normalize_date_bounds(date_from, date_to)
                
                # Date filters
                co_date_sql, co_date_params = _date_filters(date_from_dt, date_to_dt, "created_at")  # Counter orders date filter
                ord_date_sql, ord_date_params = _date_filters(date_from_dt, date_to_dt, "o.created_at")
                pay_date_sql, pay_date_params = _date_filters(date_from_dt, date_to_dt, "p.created_at")
                gro_ord_date_sql, gro_ord_date_params = _date_filters(date_from_dt, date_to_dt, "created_at")
                gro_pay_date_sql, gro_pay_date_params = _date_filters(date_from_dt, date_to_dt, "gp.payment_date")
                
                # Get comprehensive data
                overview_data = self._get_overview_summary(cursor, ids_sql, ids_params, co_date_sql, co_date_params, ord_date_sql, ord_date_params, pay_date_sql, pay_date_params, gro_ord_date_sql, gro_ord_date_params, gro_pay_date_sql, gro_pay_date_params, business_type)
                sales_data = self._get_sales_analysis(cursor, ids_sql, ids_params, co_date_sql, co_date_params, ord_date_sql, ord_date_params, gro_ord_date_sql, gro_ord_date_params, business_type)
                inventory_data = self._get_inventory_analysis(cursor, ids_sql, ids_params)
                customer_data = self._get_customer_insights(cursor, ids_sql, ids_params, ord_date_sql, ord_date_params, gro_ord_date_sql, gro_ord_date_params, business_type)
                operational_data = self._get_operational_metrics(cursor, ids_sql, ids_params, co_date_sql, co_date_params, ord_date_sql, ord_date_params, gro_ord_date_sql, gro_ord_date_params, business_type)
                order_timeline = self._get_order_timeline(cursor, ids_sql, ids_params, co_date_sql, co_date_params, ord_date_sql, ord_date_params, gro_ord_date_sql, gro_ord_date_params, business_type)

                # ===== Additional analytics for comparison, channel performance, and inventory valuation =====
                # Prepare no-alias order date SQL
                ord_date_no_alias_sql = ord_date_sql.replace("o.created_at", "created_at") if ord_date_sql else ""

                # Channel performance (share of gross sales by channel)
                try:
                    sb = overview_data.get("sales_breakdown", {})
                    counter_amt = float(sb.get("counter_orders", {}).get("amount", 0.0))
                    restaurant_amt = float(sb.get("restaurant_sales", {}).get("amount", 0.0))
                    grocery_amt = float(sb.get("grocery_sales", {}).get("amount", 0.0))
                    sales_gross_total = counter_amt + restaurant_amt + grocery_amt
                    channel_performance = {
                        "counter": {
                            "share_percent": (counter_amt / sales_gross_total * 100) if sales_gross_total > 0 else 0.0,
                        },
                        "kirazee_app": {
                            "share_percent": (restaurant_amt / sales_gross_total * 100) if sales_gross_total > 0 else 0.0,
                        },
                        "custom_website": {
                            "share_percent": (grocery_amt / sales_gross_total * 100) if sales_gross_total > 0 else 0.0,
                        },
                    }
                except Exception:
                    channel_performance = {"counter": {"share_percent": 0.0}, "kirazee_app": {"share_percent": 0.0}, "custom_website": {"share_percent": 0.0}}

                # Inventory valuation (exclude GroceryItems table) routed by business_type
                try:
                    mi_mrp = mi_cost = gv_mrp = gv_cost = fv_mrp = fv_cost = 0.0
                    if business_type == 'R02':
                        # Restaurant-like: only menuItems
                        cursor.execute(
                            f"""
                            SELECT 
                                COALESCE(SUM(i.current_stock * COALESCE(m.selling_price,0)),0) AS mrp_value,
                                COALESCE(SUM(i.current_stock * COALESCE(m.original_cost,0)),0) AS cost_value
                            FROM Inventory i
                            JOIN menuItems m ON m.item_id = i.reference_id
                            WHERE i.business_id IN ({ids_sql}) AND i.reference_table IN ('menuitems')
                            """,
                            ids_params
                        )
                        row_mi = cursor.fetchone() or (0, 0)
                        mi_mrp, mi_cost = float(row_mi[0] or 0), float(row_mi[1] or 0)
                    elif business_type == 'R01':
                        # Grocery-like: only grocery variants
                        cursor.execute(
                            f"""
                            SELECT 
                                COALESCE(SUM(i.current_stock * COALESCE(v.selling_price,0)),0) AS mrp_value,
                                COALESCE(SUM(i.current_stock * COALESCE(v.original_cost,0)),0) AS cost_value
                            FROM Inventory i
                            JOIN Groceries_ProductVariants_1 v ON v.variant_id = i.reference_id
                            WHERE i.business_id IN ({ids_sql}) AND i.reference_table IN ('groceries_productvariants','groceriesproductvariants')
                            """,
                            ids_params
                        )
                        row_gv = cursor.fetchone() or (0, 0)
                        gv_mrp, gv_cost = float(row_gv[0] or 0), float(row_gv[1] or 0)
                    elif business_type == 'R08':
                        cursor.execute(
                            f"""
                            SELECT 
                                COALESCE(SUM(COALESCE(inv.current_stock, fpv.stock, fpv.stock_qty, 0) * COALESCE(fpv.mrp, fpv.selling_price, 0)),0) AS mrp_value,
                                COALESCE(SUM(COALESCE(inv.current_stock, fpv.stock, fpv.stock_qty, 0) * COALESCE(fpv.original_cost, 0)),0) AS cost_value
                            FROM fashion_product_variants fpv
                            LEFT JOIN (
                                SELECT business_id, reference_id, MAX(current_stock) AS current_stock
                                FROM Inventory
                                WHERE reference_table IN ('fashion_product_variants','fashionproductvariants')
                                GROUP BY business_id, reference_id
                            ) inv ON inv.business_id = fpv.business_id AND inv.reference_id = fpv.variant_id
                            WHERE fpv.business_id IN ({ids_sql})
                              AND fpv.is_active = 1
                            """,
                            ids_params
                        )
                        row_fv = cursor.fetchone() or (0, 0)
                        fv_mrp, fv_cost = float(row_fv[0] or 0), float(row_fv[1] or 0)
                    else:
                        # Unknown type: compute both
                        cursor.execute(
                            f"""
                            SELECT 
                                COALESCE(SUM(i.current_stock * COALESCE(m.selling_price,0)),0) AS mrp_value,
                                COALESCE(SUM(i.current_stock * COALESCE(m.original_cost,0)),0) AS cost_value
                            FROM Inventory i
                            JOIN menuItems m ON m.item_id = i.reference_id
                            WHERE i.business_id IN ({ids_sql}) AND i.reference_table IN ('menuitems')
                            """,
                            ids_params
                        )
                        row_mi = cursor.fetchone() or (0, 0)
                        mi_mrp, mi_cost = float(row_mi[0] or 0), float(row_mi[1] or 0)
                        cursor.execute(
                            f"""
                            SELECT 
                                COALESCE(SUM(i.current_stock * COALESCE(v.selling_price,0)),0) AS mrp_value,
                                COALESCE(SUM(i.current_stock * COALESCE(v.original_cost,0)),0) AS cost_value
                            FROM Inventory i
                            JOIN Groceries_ProductVariants_1 v ON v.variant_id = i.reference_id
                            WHERE i.business_id IN ({ids_sql}) AND i.reference_table IN ('groceries_productvariants','groceriesproductvariants')
                            """,
                            ids_params
                        )
                        row_gv = cursor.fetchone() or (0, 0)
                        gv_mrp, gv_cost = float(row_gv[0] or 0), float(row_gv[1] or 0)

                        cursor.execute(
                            f"""
                            SELECT 
                                COALESCE(SUM(COALESCE(inv.current_stock, fpv.stock, fpv.stock_qty, 0) * COALESCE(fpv.mrp, fpv.selling_price, 0)),0) AS mrp_value,
                                COALESCE(SUM(COALESCE(inv.current_stock, fpv.stock, fpv.stock_qty, 0) * COALESCE(fpv.original_cost, 0)),0) AS cost_value
                            FROM fashion_product_variants fpv
                            LEFT JOIN (
                                SELECT business_id, reference_id, MAX(current_stock) AS current_stock
                                FROM Inventory
                                WHERE reference_table IN ('fashion_product_variants','fashionproductvariants')
                                GROUP BY business_id, reference_id
                            ) inv ON inv.business_id = fpv.business_id AND inv.reference_id = fpv.variant_id
                            WHERE fpv.business_id IN ({ids_sql})
                              AND fpv.is_active = 1
                            """,
                            ids_params
                        )
                        row_fv = cursor.fetchone() or (0, 0)
                        fv_mrp, fv_cost = float(row_fv[0] or 0), float(row_fv[1] or 0)
                    total_stock_value_at_mrp = mi_mrp + gv_mrp + fv_mrp
                    total_stock_value_at_cost = mi_cost + gv_cost + fv_cost
                    potential_profit = total_stock_value_at_mrp - total_stock_value_at_cost
                    inventory_valuation = {
                        "total_stock_value_at_cost": total_stock_value_at_cost,
                        "total_stock_value_at_mrp": total_stock_value_at_mrp,
                        "potential_profit": potential_profit,
                    }
                    if potential_profit < 0:
                        inventory_valuation["alert"] = {
                            "severity": "warning",
                            "message": "Stock MRP is lower than cost. Review purchase pricing."
                        }
                except Exception:
                    inventory_valuation = {"total_stock_value_at_cost": 0.0, "total_stock_value_at_mrp": 0.0, "potential_profit": 0.0}

                # Comparison metrics: previous period with same length (respect business_type)
                try:
                    # Determine current period
                    if date_from and date_to:
                        curr_from = datetime.strptime(date_from, '%Y-%m-%d').date()
                        curr_to = datetime.strptime(date_to, '%Y-%m-%d').date()
                    else:
                        # Default to last 30 days
                        curr_to = datetime.now().date()
                        curr_from = curr_to - timedelta(days=29)
                    period_days = (curr_to - curr_from).days + 1
                    prev_to = curr_from - timedelta(days=1)
                    prev_from = prev_to - timedelta(days=period_days - 1)

                    prev_from_dt = datetime.combine(prev_from, datetime.min.time())
                    prev_to_dt = datetime.combine(prev_to, datetime.max.time()).replace(microsecond=0)

                    p_co_sql, p_co_params = _date_filters(prev_from_dt, prev_to_dt, "created_at")
                    p_ord_sql, p_ord_params = _date_filters(prev_from_dt, prev_to_dt, "o.created_at")
                    if business_type == 'R01':
                        p_gro_sql, p_gro_params = _date_filters(prev_from_dt, prev_to_dt, "created_at")

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
                    pr2 = cursor.fetchone() or (0, 0)
                    p_ord_amt, p_ord_tx = float(pr2[0] or 0), int(pr2[1] or 0)
                    p_gro_amt = 0.0
                    p_gro_tx = 0
                    if business_type == 'R01':
                        cursor.execute(
                            f"SELECT COALESCE(SUM(CASE WHEN order_status='delivered' THEN final_amount ELSE 0 END),0), COUNT(CASE WHEN order_status='delivered' THEN 1 END) FROM Groceries_orders WHERE business_id IN ({ids_sql}) {p_gro_sql}",
                            ids_params + p_gro_params
                        )
                        pr3 = cursor.fetchone() or (0, 0)
                        p_gro_amt, p_gro_tx = float(pr3[0] or 0), int(pr3[1] or 0)

                    prev_total_revenue = p_co_amt + p_ord_amt + p_gro_amt
                    prev_total_tx = p_co_tx + p_ord_tx + p_gro_tx
                    growth = {}
                    if prev_total_revenue > 0:
                        growth["revenue_growth_percent"] = ((sales_gross_total - prev_total_revenue) / prev_total_revenue * 100)
                    else:
                        growth["revenue_growth_percent"] = None
                        growth["revenue_growth_note"] = "No data in previous period"
                    curr_tx = (overview_data.get("total_transactions", 0) or 0)
                    if prev_total_tx > 0:
                        growth["transaction_growth_percent"] = ((curr_tx - prev_total_tx) / prev_total_tx * 100)
                    else:
                        growth["transaction_growth_percent"] = None
                        growth["transaction_growth_note"] = "No data in previous period"
                    comparison_metrics = {
                        "previous_period": {
                            "date_from": prev_from.isoformat(),
                            "date_to": prev_to.isoformat(),
                            "total_revenue": prev_total_revenue,
                            "total_transactions": prev_total_tx
                        },
                        "growth": growth
                    }
                except Exception:
                    comparison_metrics = {
                        "previous_period": {
                            "date_from": None,
                            "date_to": None,
                            "total_revenue": 0.0,
                            "total_transactions": 0
                        },
                        "growth": {
                            "revenue_growth_percent": 0.0,
                            "transaction_growth_percent": 0.0
                        }
                    }

                # ===== Business health (non-sales) =====
                try:
                    # Active days based on any activity across sources
                    union_parts = [
                        f"SELECT DATE(created_at) d FROM business_counter_orders WHERE business_id IN ({ids_sql}) AND status='paid' {co_date_sql}",
                        f"SELECT DATE(created_at) d FROM orders WHERE business_id IN ({ids_sql}) AND status IN ('delivered','completed') {ord_date_no_alias_sql}"
                    ]
                    params = ids_params + co_date_params + ids_params + ord_date_params
                    if business_type == 'R01':
                        union_parts.append(f"SELECT DATE(created_at) d FROM Groceries_orders WHERE business_id IN ({ids_sql}) AND order_status='delivered' {gro_ord_date_sql}")
                        params = params + ids_params + gro_ord_date_params
                    union_sql = " UNION ".join(union_parts)
                    cursor.execute(
                        f"SELECT COUNT(*) FROM ({union_sql}) t",
                        params
                    )
                    active_days = int(cursor.fetchone()[0] or 0)
                except Exception:
                    active_days = 0

                try:
                    if date_from and date_to:
                        total_days = (datetime.strptime(date_to, '%Y-%m-%d').date() - datetime.strptime(date_from, '%Y-%m-%d').date()).days + 1
                    else:
                        total_days = 30
                except Exception:
                    total_days = 30
                inactive_days = max(0, total_days - active_days)
                avg_daily_tx = (overview_data.get("total_transactions", 0) or 0) / max(1, total_days)
                avg_activity_level = "High" if avg_daily_tx >= 5 else ("Medium" if avg_daily_tx >= 2 else "Low")
                business_health = {
                    "active_days": active_days,
                    "inactive_days": inactive_days,
                    "average_daily_activity": avg_activity_level
                }

                # Inventory health
                try:
                    cursor.execute(
                        f"SELECT COUNT(*) FROM Inventory WHERE business_id IN ({ids_sql}) AND current_stock < 10 AND current_stock > 0",
                        ids_params
                    )
                    low_stock_count = int(cursor.fetchone()[0] or 0)
                    cursor.execute(
                        f"SELECT COUNT(*) FROM Inventory WHERE business_id IN ({ids_sql}) AND current_stock = 0",
                        ids_params
                    )
                    out_of_stock_count = int(cursor.fetchone()[0] or 0)
                    cursor.execute(
                        f"SELECT COUNT(*) FROM Inventory WHERE business_id IN ({ids_sql}) AND current_stock >= 100",
                        ids_params
                    )
                    overstocked_count = int(cursor.fetchone()[0] or 0)
                    inventory_health = {
                        "total_items": inventory_data.get("total_items", 0),
                        "low_stock_items": low_stock_count,
                        "out_of_stock_items": out_of_stock_count,
                        "overstocked_items": overstocked_count,
                        "stock_variance_detected": False
                    }
                except Exception:
                    inventory_health = {"total_items": inventory_data.get("total_items", 0), "low_stock_items": 0, "out_of_stock_items": 0, "overstocked_items": 0, "stock_variance_detected": False}

                # Expiry tracking (only for R01/grocery)
                if business_type == 'R01':
                    try:
                        cursor.execute(
                            f"""
                            SELECT p.product_name, DATEDIFF(v.expiry_date, CURDATE()) AS days_left
                            FROM Groceries_ProductVariants_1 v
                            JOIN Groceries_Products p ON p.product_id = v.product_id
                            WHERE p.business_id IN ({ids_sql})
                              AND v.expiry_date IS NOT NULL
                              AND v.expiry_date BETWEEN CURDATE() AND DATE_ADD(CURDATE(), INTERVAL 30 DAY)
                            ORDER BY v.expiry_date ASC
                            LIMIT 10
                            """,
                            ids_params
                        )
                        exp_rows = cursor.fetchall() or []
                        expiring_soon = [{"item": r[0], "days_left": int(r[1] or 0)} for r in exp_rows]
                        cursor.execute(
                            f"SELECT COUNT(*) FROM Groceries_ProductVariants_1 v JOIN Groceries_Products p ON p.product_id = v.product_id WHERE p.business_id IN ({ids_sql}) AND v.expiry_date IS NOT NULL AND v.expiry_date < CURDATE()",
                            ids_params
                        )
                        expired_items_count = int(cursor.fetchone()[0] or 0)
                        expiry_tracking = {"expiring_soon": expiring_soon, "expired_items": expired_items_count}
                    except Exception:
                        expiry_tracking = {"expiring_soon": [], "expired_items": 0}
                else:
                    expiry_tracking = {"expiring_soon": [], "expired_items": 0}

                # Customer engagement
                try:
                    cursor.execute(
                        f"SELECT COUNT(DISTINCT user_id) FROM orders WHERE business_id IN ({ids_sql}) AND status IN ('delivered','completed') {ord_date_no_alias_sql}",
                        ids_params + ord_date_params
                    )
                    u1 = int(cursor.fetchone()[0] or 0)
                    cursor.execute(
                        f"SELECT COUNT(DISTINCT user_id) FROM Groceries_orders WHERE business_id IN ({ids_sql}) AND order_status='delivered' {gro_ord_date_sql}",
                        ids_params + gro_ord_date_params
                    )
                    u2 = int(cursor.fetchone()[0] or 0)
                    unique_customers = u1 + u2
                    # Return visits: users with more than one order per source, summed (approx)
                    cursor.execute(
                        f"SELECT COUNT(*) FROM (SELECT user_id FROM orders WHERE business_id IN ({ids_sql}) AND status IN ('delivered','completed') {ord_date_no_alias_sql} GROUP BY user_id HAVING COUNT(*)>1) t",
                        ids_params + ord_date_params
                    )
                    rv1 = int(cursor.fetchone()[0] or 0)
                    cursor.execute(
                        f"SELECT COUNT(*) FROM (SELECT user_id FROM Groceries_orders WHERE business_id IN ({ids_sql}) AND order_status='delivered' {gro_ord_date_sql} GROUP BY user_id HAVING COUNT(*)>1) t",
                        ids_params + gro_ord_date_params
                    )
                    rv2 = int(cursor.fetchone()[0] or 0)
                    return_visits = rv1 + rv2
                    visit_freq = "High" if unique_customers and (return_visits / unique_customers) > 0.5 else ("Medium" if unique_customers and (return_visits / unique_customers) > 0.2 else "Low")
                    # Preferred order type by counts
                    counter_tx = int(overview_data.get("sales_breakdown", {}).get("counter_orders", {}).get("transactions", 0))
                    rest_tx = int(overview_data.get("sales_breakdown", {}).get("restaurant_sales", {}).get("transactions", 0))
                    groc_tx = int(overview_data.get("sales_breakdown", {}).get("grocery_sales", {}).get("transactions", 0))
                    pref = "counter" if counter_tx >= max(rest_tx, groc_tx) else ("kirazee_app" if rest_tx >= groc_tx else "custom_website")
                    # Feedback count
                    try:
                        cursor.execute(
                            f"SELECT COUNT(*) FROM business_feedback WHERE business_id IN ({ids_sql})",
                            ids_params
                        )
                        feedback_count = int(cursor.fetchone()[0] or 0)
                    except Exception:
                        feedback_count = 0
                    customer_engagement = {
                        "unique_customers": unique_customers,
                        "return_visits": return_visits,
                        "visit_frequency": visit_freq,
                        "preferred_order_type": pref,
                        "feedback_received": feedback_count
                    }
                except Exception:
                    customer_engagement = {"unique_customers": 0, "return_visits": 0, "visit_frequency": "Low", "preferred_order_type": None, "feedback_received": 0}

                # Staff activity
                try:
                    cursor.execute(
                        f"SELECT COUNT(*) FROM business_staff WHERE business_id IN ({ids_sql})",
                        ids_params
                    )
                    total_staff = int(cursor.fetchone()[0] or 0)
                except Exception:
                    total_staff = 0
                try:
                    cursor.execute(
                        f"SELECT COUNT(DISTINCT staff_id) FROM business_staff_attendance WHERE business_id IN ({ids_sql}) AND attendance_date = CURDATE() AND attendance_status='Present'",
                        ids_params
                    )
                    active_staff_today = int(cursor.fetchone()[0] or 0)
                except Exception:
                    active_staff_today = 0
                total_orders_handled = int(overview_data.get("sales_breakdown", {}).get("counter_orders", {}).get("transactions", 0)) + int(overview_data.get("sales_breakdown", {}).get("restaurant_sales", {}).get("transactions", 0)) + int(overview_data.get("sales_breakdown", {}).get("grocery_sales", {}).get("transactions", 0))
                avg_orders_per_staff = (total_orders_handled / max(1, active_staff_today)) if active_staff_today > 0 else 0
                staff_activity = {
                    "total_staff": total_staff,
                    "active_staff_today": active_staff_today,
                    "average_orders_handled_per_staff": round(avg_orders_per_staff, 2),
                    "idle_time_minutes": 0
                }

                # Workflow metrics (heuristic from fulfillment time)
                try:
                    avg_fulfill_rest = float(operational_data.get("average_fulfillment_time", {}).get("kirazee_app_minutes", 0.0) or 0.0)
                    prep_time = round(avg_fulfill_rest * 0.6, 1)
                    ready_time = round(avg_fulfill_rest * 0.4, 1)
                    # Delay incidents: orders taking more than 60 minutes
                    cursor.execute(
                        f"SELECT COUNT(*) FROM orders WHERE business_id IN ({ids_sql}) AND status IN ('delivered','completed') AND TIMESTAMPDIFF(MINUTE, created_at, updated_at) > 60 {ord_date_no_alias_sql}",
                        ids_params + ord_date_params
                    )
                    delay_incidents = int(cursor.fetchone()[0] or 0)
                    workflow_metrics = {
                        "average_preparation_time_minutes": prep_time,
                        "average_delivery_ready_time_minutes": ready_time,
                        "delay_incidents": delay_incidents
                    }
                except Exception:
                    workflow_metrics = {
                        "average_preparation_time_minutes": 0.0,
                        "average_delivery_ready_time_minutes": 0.0,
                        "delay_incidents": 0
                    }
                
                owner_overview = dict(overview_data)
                owner_overview.pop("average_transaction_value", None)
                owner_overview.pop("revenue_per_transaction", None)

                try:
                    if date_from and date_to:
                        curr_from = datetime.strptime(date_from, '%Y-%m-%d').date()
                        curr_to = datetime.strptime(date_to, '%Y-%m-%d').date()
                    else:
                        curr_to = datetime.now().date()
                        curr_from = curr_to - timedelta(days=29)
                    prev_to = curr_from - timedelta(days=1)
                    prev_from = prev_to - timedelta(days=(curr_to - curr_from).days)

                    cursor.execute(
                        f"SELECT COALESCE(SUM(amount),0) FROM Expenses WHERE business_id IN ({ids_sql}) AND expense_date BETWEEN %s AND %s",
                        ids_params + [curr_from, curr_to]
                    )
                    curr_exp = float(cursor.fetchone()[0] or 0)
                    cursor.execute(
                        f"SELECT COALESCE(SUM(amount),0) FROM Expenses WHERE business_id IN ({ids_sql}) AND expense_date BETWEEN %s AND %s",
                        ids_params + [prev_from, prev_to]
                    )
                    prev_exp = float(cursor.fetchone()[0] or 0)
                    cursor.execute(
                        f"SELECT category, COALESCE(SUM(amount),0) AS total FROM Expenses WHERE business_id IN ({ids_sql}) AND expense_date BETWEEN %s AND %s GROUP BY category ORDER BY total DESC LIMIT 1",
                        ids_params + [curr_from, curr_to]
                    )
                    row = cursor.fetchone()
                    top_cat = (row[0] if row else None)
                    trend = "Stable"
                    if prev_exp > 0:
                        if curr_exp > prev_exp * 1.10:
                            trend = "Rising"
                        elif curr_exp < prev_exp * 0.90:
                            trend = "Falling"
                    else:
                        trend = "New Spend" if curr_exp > 0 else "Stable"
                    expense_spike = True if (prev_exp > 0 and curr_exp > prev_exp * 1.25) else False
                    expense_insights = {
                        "monthly_trend": trend,
                        "highest_expense_category": top_cat,
                        "expense_spike_detected": expense_spike
                    }
                except Exception:
                    expense_insights = {"monthly_trend": "Stable", "highest_expense_category": None, "expense_spike_detected": False}

                try:
                    cursor.execute(
                        f"SELECT COALESCE(SUM(total_amount),0) FROM Purchases WHERE business_id IN ({ids_sql}) AND purchase_date BETWEEN %s AND %s",
                        ids_params + [curr_from, curr_to]
                    )
                    purchases_total = float(cursor.fetchone()[0] or 0)
                    cursor.execute(
                        f"SELECT s.supplier_name, COALESCE(SUM(p.total_amount),0) AS tot FROM Purchases p LEFT JOIN Suppliers s ON s.supplier_id = p.supplier_id WHERE p.business_id IN ({ids_sql}) AND p.purchase_date BETWEEN %s AND %s GROUP BY s.supplier_id, s.supplier_name ORDER BY tot DESC LIMIT 1",
                        ids_params + [curr_from, curr_to]
                    )
                    row = cursor.fetchone()
                    top_share = float(row[1] or 0) if row else 0.0
                    dep_pct = round((top_share / purchases_total * 100), 2) if purchases_total > 0 else 0.0
                    risk = "High" if dep_pct >= 60 else ("Medium" if dep_pct >= 30 else "Low")
                    purchase_risk = {"top_supplier_dependency_percent": dep_pct, "risk_level": risk}
                except Exception:
                    purchase_risk = {"top_supplier_dependency_percent": 0.0, "risk_level": "Low"}

                # Update inventory_valuation with supplier risk (frontend expectation)
                inventory_valuation["supplier_dependency_risk"] = purchase_risk.get("risk_level", "Low")

                try:
                    cursor.execute(
                        f"""
                        SELECT 
                            SUM(CASE WHEN DATEDIFF(CURDATE(), COALESCE(last_updated, '1900-01-01')) BETWEEN 0 AND 30 THEN 1 ELSE 0 END) AS d0_30,
                            SUM(CASE WHEN DATEDIFF(CURDATE(), COALESCE(last_updated, '1900-01-01')) BETWEEN 31 AND 60 THEN 1 ELSE 0 END) AS d31_60,
                            SUM(CASE WHEN DATEDIFF(CURDATE(), COALESCE(last_updated, '1900-01-01')) > 60 THEN 1 ELSE 0 END) AS d61_plus
                        FROM Inventory WHERE business_id IN ({ids_sql})
                        """,
                        ids_params
                    )
                    row = cursor.fetchone() or (0, 0, 0)
                    inventory_aging = {"0_30_days": int(row[0] or 0), "31_60_days": int(row[1] or 0), "61_plus_days": int(row[2] or 0)}
                except Exception:
                    inventory_aging = {"0_30_days": 0, "31_60_days": 0, "61_plus_days": 0}

                # Add today's sales comparison with most recent available day as baseline
                try:
                    today = datetime.now().date()
                    today_start = datetime.combine(today, datetime.min.time())
                    today_end = datetime.combine(today, datetime.max.time())
                    
                    # Get today's sales from all sources
                    today_co_sql, today_co_params = _date_filters(today_start, today_end, "created_at")
                    today_ord_sql, today_ord_params = _date_filters(today_start, today_end, "o.created_at")
                    today_pay_sql, today_pay_params = _date_filters(today_start, today_end, "p.created_at")
                    today_gro_ord_sql, today_gro_ord_params = _date_filters(today_start, today_end, "created_at")
                    today_gro_pay_sql, today_gro_pay_params = _date_filters(today_start, today_end, "gp.payment_date")
                    
                    # Calculate today's sales
                    cursor.execute(f"SELECT COALESCE(SUM(total_amount), 0) FROM business_counter_orders WHERE business_id IN ({ids_sql}) AND status = 'paid' {today_co_sql}", ids_params + today_co_params)
                    today_counter = float(cursor.fetchone()[0] or 0)
                    
                    cursor.execute(f"SELECT COALESCE(SUM(p.amount), 0) FROM payments p INNER JOIN orders o ON o.order_id = p.order_id WHERE o.business_id IN ({ids_sql}) AND o.status IN ('delivered','completed') AND p.status = 'success' {today_pay_sql}", ids_params + today_pay_params)
                    today_restaurant = float(cursor.fetchone()[0] or 0)
                    
                    cursor.execute(f"SELECT COALESCE(SUM(gp.amount), 0) FROM Groceries_payments gp INNER JOIN Groceries_orders go ON go.order_id = gp.order_id WHERE go.business_id IN ({ids_sql}) AND go.order_status = 'delivered' AND gp.payment_status = 'completed' {today_gro_pay_sql}", ids_params + today_gro_pay_params)
                    today_grocery = float(cursor.fetchone()[0] or 0)
                    if (business_type or '').upper() == 'R02':
                        today_grocery = 0.0
                    
                    today_total_sales = today_counter + today_restaurant + today_grocery
                    
                    # Find most recent day with sales data (excluding today)
                    cursor.execute(f"""
                        SELECT DATE(created_at) as sale_date, 
                               COALESCE(SUM(total_amount), 0) as sales_amount
                        FROM business_counter_orders 
                        WHERE business_id IN ({ids_sql}) AND status = 'paid' 
                          AND DATE(created_at) < %s
                        GROUP BY DATE(created_at)
                        UNION ALL
                        SELECT DATE(o.created_at) as sale_date,
                               COALESCE(SUM(p.amount), 0) as sales_amount
                        FROM orders o
                        INNER JOIN payments p ON o.order_id = p.order_id
                        WHERE o.business_id IN ({ids_sql}) AND o.status IN ('delivered','completed') 
                          AND p.status = 'success' AND DATE(o.created_at) < %s
                        GROUP BY DATE(o.created_at)
                        UNION ALL
                        SELECT DATE(go.created_at) as sale_date,
                               COALESCE(SUM(gp.amount), 0) as sales_amount
                        FROM Groceries_orders go
                        INNER JOIN Groceries_payments gp ON go.order_id = gp.order_id
                        WHERE go.business_id IN ({ids_sql}) AND go.order_status = 'delivered' 
                          AND gp.payment_status = 'completed' AND DATE(go.created_at) < %s
                        GROUP BY DATE(go.created_at)
                        ORDER BY sale_date DESC
                        LIMIT 1
                    """, ids_params + [today, ids_params + [today, ids_params + [today]]])
                    
                    baseline_result = cursor.fetchone()
                    baseline_sales = 0.0
                    baseline_date = None
                    comparison_label = "New"
                    
                    if baseline_result:
                        baseline_date = baseline_result[0]
                        baseline_sales = float(baseline_result[1] or 0)
                        
                        # Calculate days difference and appropriate label
                        if baseline_date:
                            days_diff = (today - baseline_date).days
                            if days_diff == 1:
                                comparison_label = "vs yesterday"
                            elif days_diff == 2:
                                comparison_label = "vs 2d ago"
                            elif days_diff == 3:
                                comparison_label = "vs 3d ago"
                            elif days_diff <= 7:
                                comparison_label = f"vs {days_diff}d ago"
                            else:
                                comparison_label = f"vs {baseline_date.strftime('%b %d')}"
                    
                    # Calculate growth percentage
                    growth_percent = None
                    if baseline_sales > 0:
                        growth_percent = ((today_total_sales - baseline_sales) / baseline_sales) * 100
                    
                    # Build comparison response
                    today_sales_comparison = {
                        "today_sales": today_total_sales,
                        "baseline_sales": baseline_sales,
                        "baseline_date": baseline_date.isoformat() if baseline_date else None,
                        "comparison_label": comparison_label,
                        "growth_percent": round(growth_percent, 1) if growth_percent is not None else None,
                        "breakdown": {
                            "counter": today_counter,
                            "restaurant": today_restaurant,
                            "grocery": today_grocery
                        }
                    }
                    
                except Exception as e:
                    logger.exception("Error calculating today's sales comparison")
                    today_sales_comparison = {
                        "today_sales": 0.0,
                        "baseline_sales": 0.0,
                        "baseline_date": None,
                        "comparison_label": "New",
                        "growth_percent": None,
                        "error": str(e)
                    }
                action_items = []
                try:
                    soon = len(expiry_tracking.get("expiring_soon", []) or [])
                    if soon > 0:
                        action_items.append({"severity": "info", "message": f"{soon} item(s) are nearing expiry within 30 days."})
                except Exception:
                    pass
                try:
                    expired = expiry_tracking.get("expired_items", 0)
                    if expired > 0:
                        action_items.append({"severity": "warning", "message": f"{expired} item(s) are expired. Remove from inventory immediately."})
                except Exception:
                    pass
                try:
                    if inventory_health.get("low_stock_items", 0) > 0:
                        action_items.append({"severity": "info", "message": f"Low stock on {inventory_health.get('low_stock_items', 0)} item(s)."})
                except Exception:
                    pass
                try:
                    if comparison_metrics.get("growth", {}).get("revenue_growth_percent") is None:
                        action_items.append({"severity": "info", "message": "No previous-period data to compute growth. Showing current period only."})
                except Exception:
                    pass
                try:
                    if purchase_risk.get("risk_level") == "High":
                        action_items.append({"severity": "warning", "message": "High supplier dependency detected. Diversify purchases."})
                except Exception:
                    pass
                try:
                    if expense_insights.get("expense_spike_detected"):
                        action_items.append({"severity": "warning", "message": "Expense spike detected this period."})
                except Exception:
                    pass
                try:
                    delay_incidents = workflow_metrics.get("delay_incidents", 0)
                    if delay_incidents > 0:
                        action_items.append({"severity": "warning", "message": f"{delay_incidents} orders exceeded 60-minute completion time. Review operational efficiency."})
                except Exception:
                    pass
                try:
                    active_days = business_health.get("active_days", 0)
                    inactive_days = business_health.get("inactive_days", 0)
                    if inactive_days > active_days:
                        action_items.append({"severity": "info", "message": f"Business has {inactive_days} inactive days vs {active_days} active days. Plan marketing activities."})
                except Exception:
                    pass
                try:
                    efficiency_score = operational_metrics.get("efficiency_score", {}).get("value", 100)
                    if efficiency_score < 60:
                        action_items.append({"severity": "warning", "message": "Operational efficiency needs improvement. Review fulfillment processes."})
                except Exception:
                    pass
                try:
                    growth_percent = comparison_metrics.get("growth", {}).get("revenue_growth_percent")
                    if growth_percent is not None and growth_percent < -50:
                        action_items.append({"severity": "warning", "message": f"Revenue declined by {abs(growth_percent):.1f}% compared to previous period."})
                except Exception:
                    pass

                return Response({
                    "success": True,
                    "message": "Comprehensive dashboard report generated successfully",
                    "report_info": {
                        "business_id": business_id,
                        "business_name": business_name,
                        "date_from": date_from,
                        "date_to": date_to,
                        "include_branches": include_branches,
                        "included_business_ids": included_business_ids,
                        "generated_at": datetime.now().isoformat()
                    },
                    "overview": owner_overview,
                    "inventory_stock": inventory_data,
                    "customer_insights": customer_data,
                    "operational_metrics": operational_data,
                    "comparison_metrics": comparison_metrics,
                    "channel_performance": channel_performance,
                    "inventory_valuation": inventory_valuation,
                    "business_health": business_health,
                    "inventory_health": inventory_health,
                    "expiry_tracking": expiry_tracking,
                    "customer_engagement": customer_engagement,
                    "staff_activity": staff_activity,
                    "workflow_metrics": workflow_metrics,
                    "expense_insights": expense_insights,
                    "purchase_risk": purchase_risk,
                    "inventory_aging": inventory_aging,
                    "order_timeline": order_timeline,
                    "today_sales_comparison": today_sales_comparison,
                    "action_items": action_items
                }, status=status.HTTP_200_OK)
                
        except Exception as e:
            logger.exception("Error generating comprehensive dashboard report")
            return Response({
                "success": False,
                "message": f"Error generating dashboard report: {str(e)}"
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    
    def _get_overview_summary(self, cursor, ids_sql, ids_params, co_date_sql, co_date_params, ord_date_sql, ord_date_params, pay_date_sql, pay_date_params, gro_ord_date_sql, gro_ord_date_params, gro_pay_date_sql, gro_pay_date_params, business_type=None):
        """Get overview summary with KPIs and P&L calculation"""
        
        # ===== SALES REVENUE =====
        # Counter orders revenue from business_counter_orders (paid orders only)
        cursor.execute(
            f"""
            SELECT COALESCE(SUM(total_amount), 0) 
            FROM business_counter_orders 
            WHERE business_id IN ({ids_sql}) 
              AND status = 'paid' {co_date_sql}
            """,
            ids_params + co_date_params
        )
        counter_sales = float(cursor.fetchone()[0] or 0)
        
        cursor.execute(f"SELECT COALESCE(SUM(p.amount), 0) FROM payments p INNER JOIN orders o ON o.order_id = p.order_id WHERE o.business_id IN ({ids_sql}) AND o.status IN ('delivered','completed') AND p.status = 'success' {pay_date_sql}", ids_params + pay_date_params)
        restaurant_sales = float(cursor.fetchone()[0] or 0)
        
        cursor.execute(f"SELECT COALESCE(SUM(gp.amount), 0) FROM Groceries_payments gp INNER JOIN Groceries_orders go ON go.order_id = gp.order_id WHERE go.business_id IN ({ids_sql}) AND go.order_status = 'delivered' AND gp.payment_status = 'completed' {gro_pay_date_sql}", ids_params + gro_pay_date_params)
        grocery_sales = float(cursor.fetchone()[0] or 0)
        if (business_type or '').upper() == 'R02':
            grocery_sales = 0.0
        
        total_sales = counter_sales + restaurant_sales + grocery_sales
        
        # ===== DELIVERY & PARCEL CHARGES =====
        # Try to get delivery charges from restaurant orders (with fallback)
        try:
            cursor.execute(f"SELECT COALESCE(SUM(o.delivery_charges), 0) FROM orders o WHERE o.business_id IN ({ids_sql}) AND o.status IN ('delivered','completed') {ord_date_sql}", ids_params + ord_date_params)
            restaurant_delivery_charges = float(cursor.fetchone()[0] or 0)
        except:
            # Fallback: try delivery_fee or set to 0
            try:
                cursor.execute(f"SELECT COALESCE(SUM(o.delivery_fee), 0) FROM orders o WHERE o.business_id IN ({ids_sql}) AND o.status IN ('delivered','completed') {ord_date_sql}", ids_params + ord_date_params)
                restaurant_delivery_charges = float(cursor.fetchone()[0] or 0)
            except:
                restaurant_delivery_charges = 0
        
        # Try to get delivery charges from grocery orders (with fallback)
        try:
            cursor.execute(f"SELECT COALESCE(SUM(go.delivery_charges), 0) FROM Groceries_orders go WHERE go.business_id IN ({ids_sql}) AND go.order_status = 'delivered' {gro_ord_date_sql}", ids_params + gro_ord_date_params)
            grocery_delivery_charges = float(cursor.fetchone()[0] or 0)
        except:
            # Fallback: try delivery_fee or set to 0
            try:
                cursor.execute(f"SELECT COALESCE(SUM(go.delivery_fee), 0) FROM Groceries_orders go WHERE go.business_id IN ({ids_sql}) AND go.order_status = 'delivered' {gro_ord_date_sql}", ids_params + gro_ord_date_params)
                grocery_delivery_charges = float(cursor.fetchone()[0] or 0)
            except:
                grocery_delivery_charges = 0
        if (business_type or '').upper() == 'R02':
            grocery_delivery_charges = 0.0
        
        total_delivery_charges = restaurant_delivery_charges + grocery_delivery_charges
        
        # ===== TOTAL REVENUE (Sales + Delivery) =====
        total_revenue = total_sales + total_delivery_charges
        
        # ===== PURCHASES =====
        # Use the same date range as counter orders if date filtering is applied
        purchase_date_sql, purchase_date_params = "", []
        if co_date_sql and co_date_params:
            if len(co_date_params) >= 2:
                purchase_date_sql, purchase_date_params = _date_filters(co_date_params[0], co_date_params[1], "purchase_date")
            elif len(co_date_params) == 1:
                purchase_date_sql, purchase_date_params = _date_filters(co_date_params[0], None, "purchase_date")
        
        cursor.execute(f"SELECT COALESCE(SUM(total_amount), 0) FROM Purchases WHERE business_id IN ({ids_sql}) {purchase_date_sql}", ids_params + purchase_date_params)
        total_purchases = float(cursor.fetchone()[0] or 0)
        
        # ===== EXPENSES =====
        # Use the same date range as counter orders if date filtering is applied
        expense_date_sql, expense_date_params = "", []
        if co_date_sql and co_date_params:
            if len(co_date_params) >= 2:
                expense_date_sql, expense_date_params = _date_filters(co_date_params[0], co_date_params[1], "expense_date")
            elif len(co_date_params) == 1:
                expense_date_sql, expense_date_params = _date_filters(co_date_params[0], None, "expense_date")
        
        cursor.execute(f"SELECT COALESCE(SUM(amount), 0) FROM Expenses WHERE business_id IN ({ids_sql}) {expense_date_sql}", ids_params + expense_date_params)
        total_expenses = float(cursor.fetchone()[0] or 0)
        
        # ===== PROFIT & LOSS CALCULATION =====
        # P&L = (Sales + Delivery) - (Purchases + Expenses)
        profit_loss = total_revenue - (total_purchases + total_expenses)
        
        # Transaction counts
        # Counter orders count from business_counter_orders (paid orders only)
        cursor.execute(
            f"""
            SELECT COUNT(*) 
            FROM business_counter_orders 
            WHERE business_id IN ({ids_sql}) 
              AND status = 'paid' {co_date_sql}
            """,
            ids_params + co_date_params
        )
        counter_transactions = int(cursor.fetchone()[0] or 0)
        
        cursor.execute(f"SELECT COUNT(*) FROM orders o WHERE o.business_id IN ({ids_sql}) AND o.status IN ('delivered','completed') {ord_date_sql}", ids_params + ord_date_params)
        restaurant_orders = int(cursor.fetchone()[0] or 0)
        
        cursor.execute(f"SELECT COUNT(*) FROM Groceries_orders WHERE business_id IN ({ids_sql}) AND order_status = 'delivered' {gro_ord_date_sql}", ids_params + gro_ord_date_params)
        grocery_orders = int(cursor.fetchone()[0] or 0)
        if (business_type or '').upper() == 'R02':
            grocery_orders = 0
        
        total_transactions = counter_transactions + restaurant_orders + grocery_orders
        
        # Average transaction value
        avg_transaction_value = total_revenue / total_transactions if total_transactions > 0 else 0
        
        return {
            # P&L Card Data
            "profit_loss_cards": {
                "total_sales": total_sales,
                "delivery_parcel_charges": total_delivery_charges,
                "total_revenue": total_revenue,  # Sales + Delivery
                "total_purchases": total_purchases,
                "total_expenses": total_expenses,
                "total_costs": total_purchases + total_expenses,  # Purchases + Expenses
                "profit_loss": profit_loss,  # Revenue - Costs
                "profit_margin": (profit_loss / total_revenue * 100) if total_revenue > 0 else 0
            },
            
            # Detailed Breakdown
            "sales_breakdown": {
                "counter_orders": {"amount": counter_sales, "transactions": counter_transactions},
                "restaurant_sales": {"amount": restaurant_sales, "transactions": restaurant_orders},
                "grocery_sales": {"amount": grocery_sales, "transactions": grocery_orders}
            },
            
            "delivery_breakdown": {
                "restaurant_delivery": restaurant_delivery_charges,
                "grocery_delivery": grocery_delivery_charges
            },
            
            # Summary Metrics
            "total_transactions": total_transactions,
            "average_transaction_value": avg_transaction_value,
            "revenue_per_transaction": total_revenue / total_transactions if total_transactions > 0 else 0
        }
    
    def _get_sales_analysis(self, cursor, ids_sql, ids_params, co_date_sql, co_date_params, ord_date_sql, ord_date_params, gro_ord_date_sql, gro_ord_date_params, business_type=None):
        """Get detailed sales analysis with top items"""
        
        co_date_join_sql = co_date_sql.replace("created_at", "bco.created_at") if co_date_sql else ""
        gro_date_join_sql = gro_ord_date_sql.replace("created_at", "go.created_at") if gro_ord_date_sql else ""

        # Top 5 selling items from counter orders (business_counter_items joined with business_counter_orders)
        cursor.execute(
            f"""
            SELECT 
                bci.item_name,
                SUM(bci.quantity) as qty,
                COALESCE(SUM(bci.line_total), 0) as revenue
            FROM business_counter_items bci
            INNER JOIN business_counter_orders bco ON bco.order_id = bci.order_id
            WHERE bci.business_id IN ({ids_sql}) {co_date_join_sql}
              AND bco.status = 'paid'
            GROUP BY bci.item_name
            ORDER BY qty DESC
            LIMIT 5
            """,
            ids_params + co_date_params
        )
        top_counter_items = [{"name": r[0], "quantity": int(r[1] or 0), "revenue": float(r[2] or 0)} for r in cursor.fetchall()]
        
        # Top 5 from restaurant orders
        cursor.execute(f"SELECT oi.item_name_snapshot, SUM(oi.quantity) as qty, SUM(oi.total_price) as revenue FROM order_items oi INNER JOIN orders o ON o.order_id = oi.order_id WHERE o.business_id IN ({ids_sql}) AND o.status IN ('delivered','completed') {ord_date_sql} GROUP BY oi.item_name_snapshot ORDER BY qty DESC LIMIT 5", ids_params + ord_date_params)
        top_restaurant_items = [{"name": r[0], "quantity": int(r[1]), "revenue": float(r[2])} for r in cursor.fetchall()]
        
        # Top 5 from grocery orders
        top_grocery_items = []
        if (business_type or '').upper() in ('', 'R01'):
            cursor.execute(f"SELECT p.product_name, SUM(goi.quantity) as qty, SUM(goi.total_price) as revenue FROM Groceries_order_items goi INNER JOIN Groceries_orders go ON go.order_id = goi.order_id INNER JOIN Groceries_Products p ON p.product_id = goi.product_id WHERE go.business_id IN ({ids_sql}) AND go.order_status = 'delivered' {gro_date_join_sql} GROUP BY p.product_name ORDER BY qty DESC LIMIT 5", ids_params + gro_ord_date_params)
            top_grocery_items = [{"name": r[0], "quantity": int(r[1]), "revenue": float(r[2])} for r in cursor.fetchall()]
        
        return {
            "top_selling_items": {
                "counter_orders": top_counter_items,
                "restaurant_orders": top_restaurant_items,
                "grocery_orders": top_grocery_items
            }
        }
    
    def _get_inventory_analysis(self, cursor, ids_sql, ids_params):
        """Get inventory and stock analysis"""
        
        # ===== GET CATEGORIES FROM CATEGORY_MAPPING TABLE =====
        # Get mapped categories for this business
        cursor.execute(f"""
            SELECT DISTINCT cm.category_id, uc.category_name, uc.parent_category_id
            FROM category_mapping cm
            INNER JOIN universal_Categories uc ON uc.category_id = cm.category_id
            WHERE cm.business_id IN ({ids_sql})
            ORDER BY uc.category_name
        """, ids_params)
        
        category_mappings = cursor.fetchall()
        all_categories = []
        category_info = {}
        
        for row in category_mappings:
            category_id = row[0]
            category_name = row[1]
            parent_id = row[2]
            parent_name = None  # Not available in table, so set to None
            
            # Use parent category name if available, otherwise use category name
            display_name = parent_name or category_name
            
            if display_name not in all_categories:
                all_categories.append(display_name)
            
            category_info[display_name] = {
                'category_id': category_id,
                'category_name': category_name,
                'parent_category_id': parent_id,
                'parent_category_name': parent_name
            }
        
        # Sort categories
        all_categories.sort()
        
        # ===== GET ITEMS BY CATEGORY WITH STOCK VALUES =====
        category_items = {}
        total_stock_all = 0
        total_items_all = 0
        
        # For each mapped category, find items that belong to it
        for category_name in all_categories:
            category_id = category_info[category_name]['category_id']
            category_items[category_name] = {}
            
            # Get items from MenuItems that match this category (by category_id or name)
            cursor.execute(f"""
                SELECT mi.item_name, COALESCE(mi.quantity, 0) as stock
                FROM menuItems mi
                WHERE mi.business_id IN ({ids_sql})
                AND (mi.item_category_id = %s OR mi.item_category = %s)
                AND mi.is_active = 1
                ORDER BY mi.item_name
            """, ids_params + [category_id, category_name])
            
            menu_items = cursor.fetchall()
            for item in menu_items:
                item_name = item[0]
                stock = int(item[1])
                category_items[category_name][item_name] = stock
                if stock > 0:
                    total_stock_all += stock
                    total_items_all += 1
            
            # Get items from Groceries_Products that match this category
            cursor.execute(f"""
                SELECT gp.product_name, COALESCE(SUM(gpv.stock), 0) as stock
                FROM Groceries_Products gp
                LEFT JOIN Groceries_ProductVariants_1 gpv ON gp.product_id = gpv.product_id AND gpv.is_active = 1
                WHERE gp.business_id IN ({ids_sql})
                AND gp.sub_category = %s
                GROUP BY gp.product_name
                ORDER BY gp.product_name
            """, ids_params + [category_name])
            
            grocery_items = cursor.fetchall()
            for item in grocery_items:
                item_name = item[0]
                stock = int(item[1])
                category_items[category_name][item_name] = stock
                if stock > 0:
                    total_stock_all += stock
                    total_items_all += 1

            # Get items from fashion_products that match this category_id
            cursor.execute(f"""
                SELECT fp.name, COALESCE(SUM(COALESCE(i.current_stock, fpv.stock, fpv.stock_qty, 0)), 0) as stock
                FROM fashion_product_variants fpv
                INNER JOIN fashion_products fp ON fp.product_id = fpv.product_id
                LEFT JOIN Inventory i ON i.reference_id = fpv.variant_id
                    AND i.business_id = fpv.business_id
                    AND i.reference_table IN ('fashion_product_variants','fashionproductvariants')
                WHERE fpv.business_id IN ({ids_sql})
                AND fpv.is_active = 1
                AND fp.category_id = %s
                GROUP BY fp.name
                ORDER BY fp.name
            """, ids_params + [category_id])
            
            fashion_items = cursor.fetchall()
            for item in fashion_items:
                item_name = item[0]
                stock = int(item[1])
                category_items[category_name][item_name] = stock
                if stock > 0:
                    total_stock_all += stock
                    total_items_all += 1
        
        # ===== BUILD STOCK BY CATEGORY RESPONSE =====
        stock_by_category = []
        for category in all_categories:
            if category in category_items:
                items = category_items[category]
                total_stock = sum(stock for stock in items.values() if stock > 0)
                item_count = len([stock for stock in items.values() if stock > 0])
                
                stock_by_category.append({
                    "category": category,
                    "stock": total_stock,
                    "items": item_count
                })
        
        # Sort by stock quantity
        stock_by_category.sort(key=lambda x: x["stock"], reverse=True)
        
        # ===== LOW STOCK ALERTS =====
        cursor.execute(f"SELECT item_name, current_stock, type FROM Inventory WHERE business_id IN ({ids_sql}) AND current_stock < 10 AND current_stock > 0 ORDER BY current_stock ASC LIMIT 10", ids_params)
        low_stock_items = [{"name": r[0], "stock": int(r[1]), "category": r[2] or "Uncategorized"} for r in cursor.fetchall()]
        
        # ===== OUT OF STOCK ITEMS =====
        cursor.execute(f"SELECT COUNT(*) FROM Inventory WHERE business_id IN ({ids_sql}) AND current_stock = 0", ids_params)
        out_of_stock_count = int(cursor.fetchone()[0] or 0)
        
        # ===== SLOW MOVING ITEMS =====
        cursor.execute(f"SELECT i.item_name, i.current_stock, i.type FROM Inventory i WHERE i.business_id IN ({ids_sql}) AND i.current_stock > 0 AND i.last_updated < DATE_SUB(NOW(), INTERVAL 30 DAY) ORDER BY i.last_updated ASC LIMIT 10", ids_params)
        slow_moving_items = [{"name": r[0], "stock": int(r[1]), "category": r[2] or "Uncategorized"} for r in cursor.fetchall()]
        
        # ===== BUILD INVENTORY VISUALIZATION =====
        # Create categories with items structure as requested (show all items, even with 0 stock)
        visualization_categories = []
        colors = ["#FF6B6B", "#4ECDC4", "#45B7D1", "#96CEB4", "#FFEAA7", "#FD79A8", "#A29BFE", "#6C5CE7"]
        
        for i, category in enumerate(all_categories):
            if category in category_items:
                # Show ALL items, not just those with stock > 0
                all_items_in_category = category_items[category]
                category_stock = sum(stock for stock in all_items_in_category.values() if stock > 0)
                items_with_stock_count = len([stock for stock in all_items_in_category.values() if stock > 0])
                
                # Always include category in visualization, even if stock is 0
                color = colors[i % len(colors)]
                percentage = round((category_stock / total_stock_all * 100), 1) if total_stock_all > 0 else 0
                
                visualization_categories.append({
                    "category": category,
                    "stock": category_stock,
                    "items": len(all_items_in_category),  # Total items in category
                    "items_with_stock": items_with_stock_count,  # Items that actually have stock
                    "color": color,
                    "percentage": percentage,
                    "item_details": [{"name": name, "stock": stock} for name, stock in all_items_in_category.items()]
                })
        
        # Sort by stock quantity (categories with stock first)
        visualization_categories.sort(key=lambda x: x["stock"], reverse=True)
        
        # Build inventory visualization
        inventory_visualization = {
            "business_inventory_summary": {
                "total_stock": total_stock_all,
                "total_items": total_items_all,
                "total_categories": len(visualization_categories),
                "total_capacity": max(1000, total_stock_all + 200),
                "available_space": max(0, max(1000, total_stock_all + 200) - total_stock_all),
                "occupied_percentage": round((total_stock_all / max(1000, total_stock_all + 200)) * 100, 1)
            },
            "categories": visualization_categories,
            "items": {cat: [{"name": name, "stock": stock} for name, stock in category_items[cat].items()] 
                     for cat in all_categories if cat in category_items},
            "visual_data": {
                "cylindrical_chart": {
                    "segments": [
                        {
                            "category": cat["category"],
                            "value": cat["stock"],
                            "percentage": cat["percentage"],
                            "color": cat["color"],
                            "label": f"{cat['category']}: {cat['stock']} units ({cat['percentage']}%)",
                            "item_count": cat["items"],
                            "items_with_stock": cat["items_with_stock"]
                        } for cat in visualization_categories
                    ],
                    "total_occupied": total_stock_all,
                    "total_available": max(0, max(1000, total_stock_all + 200) - total_stock_all),
                    "total_capacity": max(1000, total_stock_all + 200)
                }
            }
        }
        
        return {
            "stock_by_category": stock_by_category,
            "low_stock_alerts": low_stock_items,
            "out_of_stock_count": out_of_stock_count,
            "slow_moving_items": slow_moving_items,
            "total_categories": len(stock_by_category),
            "total_items": total_items_all,
            "total_types": len(all_categories),
            "inventory_visualization": inventory_visualization,
            "debug_test": "Visualization function completed successfully"
        }
    def _get_customer_insights(self, cursor, ids_sql, ids_params, ord_date_sql, ord_date_params, gro_ord_date_sql, gro_ord_date_params, business_type=None):
        """Get customer insights and analytics"""
        
        ord_date_no_alias_sql = ord_date_sql.replace("o.created_at", "created_at") if ord_date_sql else ""

        try:
            # Try to get unique customers from restaurant orders (try different possible column names)
            try:
                cursor.execute(f"SELECT COUNT(DISTINCT customer_phone) FROM orders WHERE business_id IN ({ids_sql}) AND status IN ('delivered','completed') {ord_date_no_alias_sql}", ids_params + ord_date_params)
                restaurant_customers = int(cursor.fetchone()[0] or 0)
            except:
                # Fallback: just count orders if customer_phone doesn't exist
                cursor.execute(f"SELECT COUNT(*) FROM orders WHERE business_id IN ({ids_sql}) AND status IN ('delivered','completed') {ord_date_no_alias_sql}", ids_params + ord_date_params)
                restaurant_customers = int(cursor.fetchone()[0] or 0)
            
            # Try to get unique customers from grocery orders
            grocery_customers = 0
            if (business_type or '').upper() in ('', 'R01'):
                try:
                    cursor.execute(f"SELECT COUNT(DISTINCT customer_phone) FROM Groceries_orders WHERE business_id IN ({ids_sql}) AND order_status = 'delivered' {gro_ord_date_sql}", ids_params + gro_ord_date_params)
                    grocery_customers = int(cursor.fetchone()[0] or 0)
                except:
                    cursor.execute(f"SELECT COUNT(*) FROM Groceries_orders WHERE business_id IN ({ids_sql}) AND order_status = 'delivered' {gro_ord_date_sql}", ids_params + gro_ord_date_params)
                    grocery_customers = int(cursor.fetchone()[0] or 0)
            
            # Try to get repeat customers (customers with more than 1 order)
            try:
                cursor.execute(f"SELECT COUNT(*) FROM (SELECT customer_phone FROM orders WHERE business_id IN ({ids_sql}) AND status IN ('delivered','completed') {ord_date_no_alias_sql} GROUP BY customer_phone HAVING COUNT(*) > 1) as repeat_customers", ids_params + ord_date_params)
                restaurant_repeat = int(cursor.fetchone()[0] or 0)
            except:
                restaurant_repeat = 0
            
            grocery_repeat = 0
            if (business_type or '').upper() in ('', 'R01'):
                try:
                    cursor.execute(f"SELECT COUNT(*) FROM (SELECT customer_phone FROM Groceries_orders WHERE business_id IN ({ids_sql}) AND order_status = 'delivered' {gro_ord_date_sql} GROUP BY customer_phone HAVING COUNT(*) > 1) as repeat_customers", ids_params + gro_ord_date_params)
                    grocery_repeat = int(cursor.fetchone()[0] or 0)
                except:
                    grocery_repeat = 0
            
            total_customers = restaurant_customers + grocery_customers
            total_repeat = restaurant_repeat + grocery_repeat
            
            return {
                "total_customers_served": total_customers,
                "repeat_customers": total_repeat,
                "customer_retention_rate": (total_repeat / total_customers * 100) if total_customers > 0 else 0,
                "breakdown": {
                    "kirazee_app": {"total": restaurant_customers, "repeat": restaurant_repeat},
                    "custom_website": {"total": grocery_customers, "repeat": grocery_repeat}
                }
            }
        except Exception as e:
            # If all customer queries fail, return basic structure with zeros
            return {
                "total_customers_served": 0,
                "repeat_customers": 0,
                "customer_retention_rate": 0,
                "breakdown": {
                    "restaurant": {"total": 0, "repeat": 0},
                    "grocery": {"total": 0, "repeat": 0}
                },
                "error": f"Customer data unavailable: {str(e)}"
            }

    def _get_operational_metrics(self, cursor, ids_sql, ids_params, co_date_sql, co_date_params, ord_date_sql, ord_date_params, gro_ord_date_sql, gro_ord_date_params, business_type=None):
        """Get operational efficiency metrics"""
        
        ord_date_no_alias_sql = ord_date_sql.replace("o.created_at", "created_at") if ord_date_sql else ""

        # Average order fulfillment time for restaurant orders
        cursor.execute(f"SELECT AVG(TIMESTAMPDIFF(MINUTE, created_at, updated_at)) FROM orders WHERE business_id IN ({ids_sql}) AND status = 'delivered' {ord_date_no_alias_sql}", ids_params + ord_date_params)
        avg_restaurant_fulfillment = float(cursor.fetchone()[0] or 0)
        
        # Average order fulfillment time for grocery orders
        avg_grocery_fulfillment = 0.0
        if (business_type or '').upper() in ('', 'R01'):
            cursor.execute(f"SELECT AVG(TIMESTAMPDIFF(MINUTE, created_at, updated_at)) FROM Groceries_orders WHERE business_id IN ({ids_sql}) AND order_status = 'delivered' {gro_ord_date_sql}", ids_params + gro_ord_date_params)
            avg_grocery_fulfillment = float(cursor.fetchone()[0] or 0)
        
        # Peak hours analysis for restaurant orders
        cursor.execute(f"SELECT HOUR(created_at) as hour, COUNT(*) as order_count FROM orders WHERE business_id IN ({ids_sql}) AND status IN ('delivered','completed') {ord_date_no_alias_sql} GROUP BY HOUR(created_at) ORDER BY order_count DESC LIMIT 3", ids_params + ord_date_params)
        restaurant_peak_hours = [{"hour": r[0], "orders": int(r[1])} for r in cursor.fetchall()]
        
        # Peak hours analysis for grocery orders
        grocery_peak_hours = []
        if (business_type or '').upper() in ('', 'R01'):
            cursor.execute(f"SELECT HOUR(created_at) as hour, COUNT(*) as order_count FROM Groceries_orders WHERE business_id IN ({ids_sql}) AND order_status = 'delivered' {gro_ord_date_sql} GROUP BY HOUR(created_at) ORDER BY order_count DESC LIMIT 3", ids_params + gro_ord_date_params)
            grocery_peak_hours = [{"hour": r[0], "orders": int(r[1])} for r in cursor.fetchall()]
        
        # Peak hours analysis for counter orders
        cursor.execute(f"SELECT HOUR(created_at) as hour, COUNT(*) as order_count FROM business_counter_orders WHERE business_id IN ({ids_sql}) AND status = 'paid' {co_date_sql} GROUP BY HOUR(created_at) ORDER BY order_count DESC LIMIT 3", ids_params + co_date_params)
        counter_peak_hours = [{"hour": r[0], "orders": int(r[1])} for r in cursor.fetchall()]
        
        # Combine peak hours from all sources
        all_peak_hours = {}
        for peak_list in [restaurant_peak_hours, grocery_peak_hours, counter_peak_hours]:
            for peak in peak_list:
                hour = peak["hour"]
                if hour not in all_peak_hours:
                    all_peak_hours[hour] = 0
                all_peak_hours[hour] += peak["orders"]
        
        # Sort combined peak hours and take top 3
        combined_peak_hours = sorted(
            [{"hour": hour, "orders": orders} for hour, orders in all_peak_hours.items()],
            key=lambda x: x["orders"],
            reverse=True
        )[:3]
        
        eff_val = min(100, max(0, 100 - (avg_restaurant_fulfillment + avg_grocery_fulfillment) / 2))
        if eff_val >= 80:
            eff_label = "Excellent"
        elif eff_val >= 60:
            eff_label = "Good"
        elif eff_val >= 40:
            eff_label = "Average"
        else:
            eff_label = "Needs Improvement"
        
        return {
            "average_fulfillment_time": {
                "kirazee_web/app_minutes": avg_restaurant_fulfillment,
                "own_website_minutes": avg_grocery_fulfillment
            },
            "peak_hours": {
                "combined": combined_peak_hours,
                "kirazee": restaurant_peak_hours,
                "ownsite": grocery_peak_hours,
                "counter": counter_peak_hours
            },
            "efficiency_score": {"value": eff_val, "label": eff_label}
        }


    def _get_order_timeline(self, cursor, ids_sql, ids_params, co_date_sql, co_date_params, ord_date_sql, ord_date_params, gro_ord_date_sql, gro_ord_date_params, business_type=None):
        """Get order breakdown by date within the filtered period"""
        
        # Get counter orders by date
        cursor.execute(
            f"""
            SELECT DATE(created_at) as order_date, COUNT(*) as orders, COALESCE(SUM(total_amount), 0) as revenue
            FROM business_counter_orders 
            WHERE business_id IN ({ids_sql}) AND status = 'paid' {co_date_sql}
            GROUP BY DATE(created_at)
            ORDER BY order_date
            """,
            ids_params + co_date_params
        )
        counter_orders = [{"date": str(r[0]), "orders": int(r[1]), "revenue": float(r[2])} for r in cursor.fetchall()]
        
        # Get restaurant orders by date
        cursor.execute(
            f"""
            SELECT DATE(o.created_at) as order_date, COUNT(*) as orders, COALESCE(SUM(p.amount), 0) as revenue
            FROM orders o
            INNER JOIN payments p ON o.order_id = p.order_id
            WHERE o.business_id IN ({ids_sql}) AND o.status IN ('delivered','completed') AND p.status = 'success' {ord_date_sql}
            GROUP BY DATE(o.created_at)
            ORDER BY order_date
            """,
            ids_params + ord_date_params
        )
        restaurant_orders = [{"date": str(r[0]), "orders": int(r[1]), "revenue": float(r[2])} for r in cursor.fetchall()]
        
        # Get grocery orders by date
        grocery_orders = []
        if (business_type or '').upper() in ('', 'R01'):
            cursor.execute(
                f"""
                SELECT DATE(created_at) as order_date, COUNT(*) as orders, COALESCE(SUM(gp.amount), 0) as revenue
                FROM Groceries_orders go
                INNER JOIN Groceries_payments gp ON go.order_id = gp.order_id
                WHERE go.business_id IN ({ids_sql}) AND go.order_status = 'delivered' AND gp.payment_status = 'completed' {gro_ord_date_sql}
                GROUP BY DATE(created_at)
                ORDER BY order_date
                """,
                ids_params + gro_ord_date_params
            )
            grocery_orders = [{"date": str(r[0]), "orders": int(r[1]), "revenue": float(r[2])} for r in cursor.fetchall()]
        
        # Combine all orders by date
        from collections import defaultdict
        daily_summary = defaultdict(lambda: {"counter_orders": 0, "counter_revenue": 0.0, "restaurant_orders": 0, "restaurant_revenue": 0.0, "grocery_orders": 0, "grocery_revenue": 0.0, "total_orders": 0, "total_revenue": 0.0})
        
        # Add counter orders
        for order in counter_orders:
            date = order["date"]
            daily_summary[date]["counter_orders"] = order["orders"]
            daily_summary[date]["counter_revenue"] = order["revenue"]
            daily_summary[date]["total_orders"] += order["orders"]
            daily_summary[date]["total_revenue"] += order["revenue"]
        
        # Add restaurant orders
        for order in restaurant_orders:
            date = order["date"]
            daily_summary[date]["restaurant_orders"] = order["orders"]
            daily_summary[date]["restaurant_revenue"] = order["revenue"]
            daily_summary[date]["total_orders"] += order["orders"]
            daily_summary[date]["total_revenue"] += order["revenue"]
        
        # Add grocery orders
        for order in grocery_orders:
            date = order["date"]
            daily_summary[date]["grocery_orders"] = order["orders"]
            daily_summary[date]["grocery_revenue"] = order["revenue"]
            daily_summary[date]["total_orders"] += order["orders"]
            daily_summary[date]["total_revenue"] += order["revenue"]
        
        # Convert to list and sort by date
        order_timeline = []
        for date in sorted(daily_summary.keys()):
            data = daily_summary[date]
            order_timeline.append({
                "date": date,
                "orders": {
                    "counter": data["counter_orders"],
                    "restaurant": data["restaurant_orders"],
                    "grocery": data["grocery_orders"],
                    "total": data["total_orders"]
                },
                "revenue": {
                    "counter": round(data["counter_revenue"], 2),
                    "restaurant": round(data["restaurant_revenue"], 2),
                    "grocery": round(data["grocery_revenue"], 2),
                    "total": round(data["total_revenue"], 2)
                }
            })
        
        return order_timeline
    
