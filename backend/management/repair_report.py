
import os

file_path = r"d:\Kirazee_Backend_Live\management\report.py"
new_method = r'''
    def _get_order_summary(self, cursor, ids_sql, ids_params, co_date_sql, co_date_params, ord_date_sql, ord_date_params, pay_date_sql, pay_date_params, gro_ord_date_sql, gro_ord_date_params, gro_pay_date_sql, gro_pay_date_params, business_type=None):
        """Get comprehensive order summary including status breakdowns and collections"""
        
        # 1. Counter Orders Logic
        counter_summary = {
            "order_count": 0,
            "status_breakdown": {
                "paid": {"count": 0, "amount": 0.0},
                "pending": {"count": 0, "amount": 0.0},
                "cancelled": {"count": 0, "amount": 0.0}
            },
            "collections": {
                "cash": {"count": 0, "amount": 0.0},
                "upi": {"count": 0, "amount": 0.0},
                "card": {"count": 0, "amount": 0.0},
                "razorpay": {"count": 0, "amount": 0.0},
                "total_collections": 0.0
            }
        }
        
        # Get counts and amounts for paid/pending/cancelled
        cursor.execute(f"""
            SELECT 
                COUNT(*),
                COALESCE(SUM(CASE WHEN status='paid' THEN 1 ELSE 0 END), 0),
                COALESCE(SUM(CASE WHEN payment_method='cash' AND status='paid' THEN total_amount ELSE 0 END), 0),
                COALESCE(SUM(CASE WHEN payment_method='upi' AND status='paid' THEN total_amount ELSE 0 END), 0),
                COALESCE(SUM(CASE WHEN payment_method='card' AND status='paid' THEN total_amount ELSE 0 END), 0),
                COALESCE(SUM(CASE WHEN payment_method='razorpay' AND status='paid' THEN total_amount ELSE 0 END), 0),
                COALESCE(SUM(CASE WHEN status='paid' THEN total_amount ELSE 0 END), 0),
                COALESCE(SUM(CASE WHEN status='pending' THEN total_amount ELSE 0 END), 0),
                COALESCE(SUM(CASE WHEN status='cancelled' THEN total_amount ELSE 0 END), 0)
            FROM business_counter_orders
            WHERE business_id IN ({ids_sql}) {co_date_sql}
        """, ids_params + co_date_params)
        
        row = cursor.fetchone()
        if row:
            counter_summary["order_count"] = int(row[0] or 0)
            counter_summary["status_breakdown"]["paid"]["count"] = int(row[1] or 0)
            counter_summary["collections"]["cash"]["amount"] = float(row[2] or 0)
            counter_summary["collections"]["upi"]["amount"] = float(row[3] or 0)
            counter_summary["collections"]["card"]["amount"] = float(row[4] or 0)
            counter_summary["collections"]["razorpay"]["amount"] = float(row[5] or 0)
            counter_summary["status_breakdown"]["paid"]["amount"] = float(row[6] or 0)
            counter_summary["status_breakdown"]["pending"]["amount"] = float(row[7] or 0)
            counter_summary["status_breakdown"]["cancelled"]["amount"] = float(row[8] or 0)
            
            counter_summary["collections"]["total_collections"] = (
                counter_summary["collections"]["cash"]["amount"] +
                counter_summary["collections"]["upi"]["amount"] +
                counter_summary["collections"]["card"]["amount"] +
                counter_summary["collections"]["razorpay"]["amount"]
            )
            
        # 2. Restaurant Orders (Kirazee App)
        # Delivered
        cursor.execute(f"SELECT COUNT(*), COALESCE(SUM(total_price), 0) FROM orders WHERE business_id IN ({ids_sql}) AND status IN ('delivered','completed') {ord_date_sql.replace('o.created_at', 'created_at') if ord_date_sql else ''}", ids_params + ord_date_params)
        ord_dev_row = cursor.fetchone()
        ord_delivered_count = int(ord_dev_row[0] or 0)
        ord_delivered_revenue = float(ord_dev_row[1] or 0)
        
        # Pickup Delivered
        cursor.execute(f"SELECT COUNT(*), COALESCE(SUM(total_price), 0) FROM orders WHERE business_id IN ({ids_sql}) AND status IN ('delivered','completed') AND order_type='pickup' {ord_date_sql.replace('o.created_at', 'created_at') if ord_date_sql else ''}", ids_params + ord_date_params)
        ord_pick_row = cursor.fetchone()
        ord_pickup_count = int(ord_pick_row[0] or 0)
        ord_pickup_revenue = float(ord_pick_row[1] or 0)
        
        # 3. Grocery Orders (My Order Online)
        gro_delivered_count = 0
        gro_delivered_revenue = 0.0
        gro_pickup_count = 0
        gro_pickup_revenue = 0.0
        
        if (business_type or '').upper() == 'R01':
            # Delivered
            cursor.execute(f"SELECT COUNT(*), COALESCE(SUM(final_amount), 0) FROM Groceries_orders WHERE business_id IN ({ids_sql}) AND order_status='delivered' {gro_ord_date_sql}", ids_params + gro_ord_date_params)
            gro_dev_row = cursor.fetchone()
            gro_delivered_count = int(gro_dev_row[0] or 0)
            gro_delivered_revenue = float(gro_dev_row[1] or 0)
            
            # Pickup Delivered
            cursor.execute(f"SELECT COUNT(*), COALESCE(SUM(final_amount), 0) FROM Groceries_orders WHERE business_id IN ({ids_sql}) AND order_status='delivered' AND order_type='pickup' {gro_ord_date_sql}", ids_params + gro_ord_date_params)
            gro_pick_row = cursor.fetchone()
            gro_pickup_count = int(gro_pick_row[0] or 0)
            gro_pickup_revenue = float(gro_pick_row[1] or 0)

        # 4. Summary Aggregation
        pickup_orders_count = ord_pickup_count + gro_pickup_count
        pickup_orders_amount = ord_pickup_revenue + gro_pickup_revenue
        
        delivery_only_orders_count = (ord_delivered_count - ord_pickup_count) + (gro_delivered_count - gro_pickup_count)
        delivery_only_orders_amount = (ord_delivered_revenue - ord_pickup_revenue) + (gro_delivered_revenue - gro_pickup_revenue)
        
        return {
            "counter_orders_summary": counter_summary,
            "online_orders_summary": {
                "pickup_orders": {
                    "count": pickup_orders_count,
                    "amount": pickup_orders_amount
                },
                "delivery_orders": {
                    "count": delivery_only_orders_count,
                    "amount": delivery_only_orders_amount
                },
                "total_online_orders": {
                    "count": ord_delivered_count + gro_delivered_count,
                    "amount": ord_delivered_revenue + gro_delivered_revenue
                }
            }
        }
'''

try:
    with open(file_path, 'rb') as f:
        content = f.read()
    
    # Check for the corruption start point (look for "def _get_channel_performance")
    # We want to keep everything up to the end of _get_channel_performance
    
    # Find the end of _get_channel_performance
    search_str = b'            "custom_website": {\r\n                "share_percent": (grocery_amt / total * 100) if total > 0 else 0.0,\r\n            },\r\n        }'
    idx = content.find(search_str)
    
    if idx == -1:
        # Try with just LF
        search_str = b'            "custom_website": {\n                "share_percent": (grocery_amt / total * 100) if total > 0 else 0.0,\n            },\n        }'
        idx = content.find(search_str)

    if idx != -1:
        end_idx = idx + len(search_str)
        cleaned_content = content[:end_idx]
        
        # Append newline and new method
        if not cleaned_content.endswith(b'\n'):
             cleaned_content += b'\n'
             
        final_content = cleaned_content + new_method.encode('utf-8')
        
        with open(file_path, 'wb') as f:
            f.write(final_content)
        print("File successfully repaired.")
    else:
        print("Could not find the insertion point.")

except Exception as e:
    print(f"Error: {e}")
