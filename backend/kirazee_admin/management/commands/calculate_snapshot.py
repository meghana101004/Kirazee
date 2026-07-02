from django.core.management.base import BaseCommand
from django.db import connection
from django.utils import timezone
from kirazee_admin.models import DashboardSnapshot
import logging

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = 'Calculate and store dashboard snapshot metrics'

    def handle(self, *args, **options):
        """Calculate dashboard snapshot metrics"""
        try:
            self.stdout.write('Starting dashboard snapshot calculation...')
            
            with connection.cursor() as cursor:
                # Detect connection collation for safe operations
                detected_collation = 'utf8_general_ci'
                try:
                    cursor.execute("SELECT @@collation_connection")
                    row = cursor.fetchone()
                    if row and isinstance(row[0], str):
                        detected_collation = row[0].split('_')[-1]
                except:
                    pass
                
                # =================== REVENUE METRICS ===================
                cursor.execute(f"""
                    SELECT 
                        COALESCE(SUM(final_amount), 0) as total_revenue,
                        COUNT(*) as total_orders,
                        COALESCE(AVG(final_amount), 0) as average_order_value
                    FROM orders 
                    WHERE status IN ('completed', 'delivered') 
                    AND created_at >= DATE_SUB(NOW(), INTERVAL 30 DAY)
                """)
                revenue_data = cursor.fetchone()
                total_revenue = revenue_data[0] if revenue_data else 0
                total_orders = revenue_data[1] if revenue_data else 0
                average_order_value = revenue_data[2] if revenue_data else 0
                
                # =================== BUSINESS METRICS ===================
                cursor.execute("""
                    SELECT 
                        COUNT(*) as total_businesses,
                        COUNT(CASE WHEN status = 1 THEN 1 END) as active_businesses
                    FROM businesses
                """)
                business_data = cursor.fetchone()
                total_businesses = business_data[0] if business_data else 0
                active_businesses = business_data[1] if business_data else 0
                
                # =================== USER METRICS ===================
                # Active users = users who placed orders in last 30 days
                cursor.execute("""
                    SELECT 
                        COUNT(DISTINCT o.user_id) as unique_customers,
                        COUNT(DISTINCT u.user_id) as total_users,
                        COUNT(DISTINCT CASE 
                            WHEN o.created_at >= DATE_SUB(NOW(), INTERVAL 30 DAY) 
                            THEN o.user_id 
                        END) as active_users
                    FROM orders o
                    LEFT JOIN registrations u ON o.user_id = u.user_id
                    WHERE o.status IN ('completed', 'delivered')
                """)
                user_data = cursor.fetchone()
                unique_customers = user_data[0] if user_data else 0
                total_users = user_data[1] if user_data else 0
                active_users = user_data[2] if user_data else 0
                
                # =================== COMPLETION RATE ===================
                cursor.execute("""
                    SELECT 
                        COUNT(CASE WHEN status IN ('completed', 'delivered') THEN 1 END) * 100.0 / NULLIF(COUNT(*), 0)
                    FROM orders 
                    WHERE created_at >= DATE_SUB(NOW(), INTERVAL 30 DAY)
                """)
                completion_data = cursor.fetchone()
                completion_rate = completion_data[0] if completion_data and completion_data[0] else 0
                
                # =================== ORDER BREAKDOWN BY STATUS ===================
                cursor.execute("""
                    SELECT 
                        COUNT(CASE WHEN order_type = 'online' THEN 1 END) as online_orders,
                        COUNT(CASE WHEN order_type = 'counter' THEN 1 END) as counter_orders,
                        COUNT(CASE WHEN status IN ('preparing', 'ready', 'assigned', 'picked_up') THEN 1 END) as active_orders,
                        COUNT(CASE WHEN status = 'placed' THEN 1 END) as pending_orders,
                        COUNT(CASE WHEN status IN ('completed', 'delivered') THEN 1 END) as completed_orders,
                        COUNT(CASE WHEN status = 'cancelled' THEN 1 END) as cancelled_orders
                    FROM orders 
                    WHERE created_at >= DATE_SUB(NOW(), INTERVAL 30 DAY)
                """)
                order_breakdown = cursor.fetchone()
                online_orders = order_breakdown[0] if order_breakdown else 0
                counter_orders = order_breakdown[1] if order_breakdown else 0
                active_orders = order_breakdown[2] if order_breakdown else 0
                pending_orders = order_breakdown[3] if order_breakdown else 0
                completed_orders = order_breakdown[4] if order_breakdown else 0
                cancelled_orders = order_breakdown[5] if order_breakdown else 0
                
                # =================== DELIVERY PARTNERS ===================
                # status: 1 = active, 0 = inactive
                # is_available: 1 = available, 0 = not available
                cursor.execute("""
                    SELECT 
                        COUNT(CASE WHEN status = 1 AND is_available = 1 THEN 1 END) as active_and_available,
                        COUNT(CASE WHEN status = 1 THEN 1 END) as active_partners,
                        COUNT(CASE WHEN is_available = 1 THEN 1 END) as available_partners,
                        COUNT(*) as total_partners
                    FROM delivery_partner
                """)
                delivery_data = cursor.fetchone()
                active_delivery_partners = delivery_data[0] if delivery_data else 0  # Both active AND available
                total_delivery_partners = delivery_data[3] if delivery_data else 0
                available_drivers = delivery_data[2] if delivery_data else 0
                busy_drivers = delivery_data[1] - delivery_data[0] if delivery_data else 0  # Active but not available
                
                # =================== CREATE SNAPSHOT ===================
                snapshot = DashboardSnapshot.objects.create(
                    total_revenue=total_revenue,
                    total_orders=total_orders,
                    average_order_value=average_order_value,
                    online_orders=online_orders,
                    counter_orders=counter_orders,
                    active_orders=active_orders,
                    pending_orders=pending_orders,
                    completed_orders=completed_orders,
                    cancelled_orders=cancelled_orders,
                    unique_customers=unique_customers,
                    active_businesses=active_businesses,
                    completion_rate=completion_rate,
                    active_delivery_partners=active_delivery_partners,
                    available_drivers=available_drivers,
                    busy_drivers=busy_drivers,
                    total_businesses=total_businesses,
                    total_users=total_users,
                    active_users=active_users
                )
                
                self.stdout.write(
                    self.style.SUCCESS(
                        f'Snapshot created successfully! ID: {snapshot.id}\n'
                        f'  Revenue: ₹{total_revenue:.2f}, Orders: {total_orders}, Avg: ₹{average_order_value:.2f}\n'
                        f'  Online: {online_orders}, Counter: {counter_orders}, Active: {active_orders}\n'
                        f'  Completed: {completed_orders}, Cancelled: {cancelled_orders}, Pending: {pending_orders}\n'
                        f'  Active Users: {active_users}, Active Partners: {active_delivery_partners}'
                    )
                )
                
        except Exception as e:
            logger.error(f"Error calculating snapshot: {str(e)}")
            self.stdout.write(
                self.style.ERROR(f'Error calculating snapshot: {str(e)}')
            )
