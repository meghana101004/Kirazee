from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from django.utils import timezone
from django.db.models import Max
from .models import DashboardSnapshot
import logging

logger = logging.getLogger(__name__)

class DashboardPulseView(APIView):
    """
    Ultra-fast dashboard pulse endpoint
    Returns pre-calculated metrics from snapshot table
    Response time: <50ms
    """
    permission_classes = []  # Remove authentication for testing
    
    def get(self, request):
        """Get latest dashboard snapshot"""
        try:
            # Get the most recent snapshot
            snapshot = DashboardSnapshot.objects.order_by('-created_at').first()
            
            if not snapshot:
                return Response({
                    'success': False,
                    'message': 'No dashboard snapshot available. Please run calculate_snapshot command.',
                    'data': None
                }, status=status.HTTP_404_NOT_FOUND)
            
            # Check if snapshot is too old (>10 minutes)
            age_minutes = snapshot.snapshot_age_minutes
            if age_minutes > 10:
                freshness_status = 'stale'
            elif age_minutes > 5:
                freshness_status = 'fresh'
            else:
                freshness_status = 'realtime'
            
            # Format response for frontend consumption
            pulse_data = {
                'snapshot_id': snapshot.id,
                'last_updated': snapshot.created_at.isoformat(),
                'snapshot_age_minutes': age_minutes,
                'freshness_status': freshness_status,
                
                # Revenue Metrics
                'revenue': {
                    'total_revenue': float(snapshot.total_revenue),
                    'total_revenue_formatted': snapshot.total_revenue_formatted,
                    'total_gmv': float(snapshot.total_gmv),
                    'average_order_value': float(snapshot.average_order_value)
                },
                
                # Order Metrics
                'orders': {
                    'total_orders': snapshot.total_orders,
                    'online_orders': snapshot.online_orders,
                    'counter_orders': snapshot.counter_orders,
                    'active_orders': snapshot.active_orders,
                    'pending_orders': snapshot.pending_orders,
                    'completed_orders': snapshot.completed_orders,
                    'cancelled_orders': snapshot.cancelled_orders
                },
                
                # Business Metrics
                'businesses': {
                    'active_businesses': snapshot.active_businesses,
                    'total_businesses': snapshot.total_businesses,
                    'paid_businesses': snapshot.paid_businesses
                },
                
                # Customer Metrics
                'customers': {
                    'unique_customers': snapshot.unique_customers,
                    'total_users': snapshot.total_users,
                    'active_users': snapshot.active_users
                },
                
                # Delivery Metrics
                'delivery': {
                    'active_delivery_partners': snapshot.active_delivery_partners,
                    'available_drivers': snapshot.available_drivers,
                    'busy_drivers': snapshot.busy_drivers
                },
                
                # Performance Metrics
                'performance': {
                    'completion_rate': float(snapshot.completion_rate),
                    'cancellation_rate': float(snapshot.cancellation_rate)
                }
            }
            
            return Response({
                'success': True,
                'message': 'Dashboard pulse retrieved successfully',
                'data': pulse_data
            }, status=status.HTTP_200_OK)
            
        except Exception as e:
            logger.error(f"Error retrieving dashboard pulse: {str(e)}")
            return Response({
                'success': False,
                'message': f'Error retrieving dashboard pulse: {str(e)}',
                'data': None
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class DashboardHealthView(APIView):
    """
    Health check endpoint for dashboard monitoring
    Returns system status and snapshot freshness
    """
    permission_classes = []  # Remove authentication for testing
    
    def get(self, request):
        """Check dashboard system health"""
        try:
            # Get latest snapshot
            snapshot = DashboardSnapshot.objects.order_by('-created_at').first()
            
            # Count total snapshots
            total_snapshots = DashboardSnapshot.objects.count()
            
            # Get oldest snapshot timestamp
            oldest_snapshot = DashboardSnapshot.objects.order_by('created_at').first()
            
            health_status = {
                'system_status': 'healthy',
                'snapshot_status': 'active',
                'last_snapshot_age_minutes': snapshot.snapshot_age_minutes if snapshot else None,
                'total_snapshots': total_snapshots,
                'oldest_snapshot': oldest_snapshot.created_at.isoformat() if oldest_snapshot else None,
                'database_connection': 'ok',
                'recommendations': []
            }
            
            # Add recommendations based on status
            if not snapshot:
                health_status['system_status'] = 'warning'
                health_status['recommendations'].append('Run calculate_snapshot command to generate first snapshot')
            elif snapshot.snapshot_age_minutes > 15:
                health_status['system_status'] = 'warning'
                health_status['recommendations'].append('Snapshot is stale. Check cron job schedule.')
            elif total_snapshots < 10:
                health_status['recommendations'].append('Consider keeping more snapshots for better analytics')
            
            return Response({
                'success': True,
                'message': 'Dashboard health check completed',
                'health': health_status
            }, status=status.HTTP_200_OK)
            
        except Exception as e:
            logger.error(f"Error checking dashboard health: {str(e)}")
            return Response({
                'success': False,
                'message': f'Error checking dashboard health: {str(e)}',
                'health': {
                    'system_status': 'error',
                    'database_connection': 'error',
                    'recommendations': ['Check database connection and model migrations']
                }
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
