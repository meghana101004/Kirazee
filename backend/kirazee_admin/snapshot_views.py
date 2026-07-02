from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from django.core.management import call_command
from django.utils import timezone
from django.contrib.auth.models import User
from .models import DashboardSnapshot
from .permissions import IsSuperAdminOrReadOnly
import logging

logger = logging.getLogger(__name__)

class SnapshotCalculationView(APIView):
    """
    Manual snapshot calculation trigger for admins
    POST /api/v1/admin/snapshot/calculate/
    Allows admins to trigger snapshot calculation from frontend
    """
    permission_classes = []  # No authentication required for admin access
    
    def post(self, request):
        """Manually trigger snapshot calculation"""
        try:
            # No authentication check - allow all admin users
            # In production, you can add admin role check if needed:
            # if not request.user.is_staff:
            #     return Response({
            #         'success': False,
            #         'message': 'Admin privileges required to access snapshot management',
            #         'data': None
            #     }, status=status.HTTP_403_FORBIDDEN)
            
            # Get latest snapshot before calculation
            latest_before = DashboardSnapshot.objects.order_by('-created_at').first()
            
            # Run the management command
            username = getattr(request.user, 'username', 'anonymous') if hasattr(request, 'user') else 'anonymous'
            logger.info(f"Snapshot calculation triggered by user: {username}")
            call_command('calculate_snapshot')
            
            # Get latest snapshot after calculation
            latest_after = DashboardSnapshot.objects.order_by('-created_at').first()
            
            if latest_after:
                return Response({
                    'success': True,
                    'message': 'Snapshot calculated successfully',
                    'data': {
                        'snapshot_id': latest_after.id,
                        'calculated_at': latest_after.created_at.isoformat(),
                        'metrics': {
                            'total_revenue': float(latest_after.total_revenue),
                            'total_orders': latest_after.total_orders,
                            'unique_customers': latest_after.unique_customers,
                            'active_businesses': latest_after.active_businesses,
                            'completion_rate': float(latest_after.completion_rate),
                            'previous_snapshot_id': latest_before.id if latest_before else None,
                            'time_since_previous': None
                        }
                    }
                }, status=status.HTTP_200_OK)
            else:
                return Response({
                    'success': False,
                    'message': 'Snapshot calculation failed - no data created',
                    'data': None
                }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
                
        except Exception as e:
            logger.error(f"Error in manual snapshot calculation: {str(e)}")
            return Response({
                'success': False,
                'message': f'Error calculating snapshot: {str(e)}',
                'data': None
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    
    def get(self, request):
        """Get snapshot calculation status and history"""
        try:
            # Get recent snapshots
            recent_snapshots = DashboardSnapshot.objects.order_by('-created_at')[:10]
            
            # Get calculation frequency info
            total_snapshots = DashboardSnapshot.objects.count()
            
            # Calculate time since last snapshot
            latest = recent_snapshots.first()
            time_since_last = None
            if latest:
                time_diff = timezone.now() - latest.created_at
                minutes_ago = int(time_diff.total_seconds() / 60)
                if minutes_ago < 60:
                    time_since_last = f"{minutes_ago} minutes ago"
                else:
                    hours_ago = minutes_ago // 60
                    time_since_last = f"{hours_ago} hours ago"
            
            # Format snapshot history
            snapshot_history = []
            for snapshot in recent_snapshots:
                snapshot_history.append({
                    'id': snapshot.id,
                    'created_at': snapshot.created_at.isoformat(),
                    'total_revenue': float(snapshot.total_revenue),
                    'total_orders': snapshot.total_orders,
                    'unique_customers': snapshot.unique_customers,
                    'completion_rate': float(snapshot.completion_rate),
                    'age_minutes': snapshot.snapshot_age_minutes
                })
            
            return Response({
                'success': True,
                'message': 'Snapshot status retrieved successfully',
                'data': {
                    'latest_snapshot': {
                        'id': latest.id if latest else None,
                        'created_at': latest.created_at.isoformat() if latest else None,
                        'time_since_last': time_since_last,
                        'age_minutes': latest.snapshot_age_minutes if latest else None
                    },
                    'total_snapshots': total_snapshots,
                    'snapshot_history': snapshot_history,
                    'calculation_status': 'active' if latest and latest.snapshot_age_minutes < 15 else 'stale'
                }
            }, status=status.HTTP_200_OK)
            
        except Exception as e:
            logger.error(f"Error retrieving snapshot status: {str(e)}")
            return Response({
                'success': False,
                'message': f'Error retrieving snapshot status: {str(e)}',
                'data': None
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class SnapshotScheduleView(APIView):
    """
    View and manage snapshot calculation schedule information
    GET /api/v1/admin/snapshot/schedule/
    Shows cron job status and setup instructions
    """
    permission_classes = []  # No authentication required for admin access
    
    def get(self, request):
        """Get snapshot schedule information"""
        try:
            # Get recent snapshots to analyze schedule
            recent_snapshots = DashboardSnapshot.objects.order_by('-created_at')[:20]
            
            # Calculate average interval between snapshots
            intervals = []
            for i in range(len(recent_snapshots) - 1):
                current = recent_snapshots[i]
                previous = recent_snapshots[i + 1]
                interval_minutes = (current.created_at - previous.created_at).total_seconds() / 60
                intervals.append(interval_minutes)
            
            avg_interval = sum(intervals) / len(intervals) if intervals else 0
            
            # Determine schedule status
            latest = recent_snapshots.first()
            if not latest:
                schedule_status = 'no_snapshots'
                recommendation = 'Run manual snapshot calculation and setup cron job'
            elif latest.snapshot_age_minutes > 15:
                schedule_status = 'stale'
                recommendation = 'Check cron job setup or run manual calculation'
            elif avg_interval > 10:
                schedule_status = 'irregular'
                recommendation = 'Cron job may not be running consistently'
            else:
                schedule_status = 'healthy'
                recommendation = 'Snapshot calculation is working properly'
            
            # Cron job setup instructions
            cron_instructions = {
                'linux_mac': {
                    'command': '*/5 * * * * /path/to/venv/bin/python /path/to/project/manage.py calculate_snapshot',
                    'setup_steps': [
                        'Open crontab: crontab -e',
                        'Add the cron line above',
                        'Save and exit',
                        'Verify with: crontab -l'
                    ]
                },
                'windows': {
                    'setup_steps': [
                        'Open Task Scheduler',
                        'Create Basic Task',
                        'Set trigger: Daily → Repeat every 5 minutes',
                        'Action: Start program',
                        'Program: python',
                        'Arguments: manage.py calculate_snapshot',
                        'Start in: your project directory'
                    ]
                }
            }
            
            return Response({
                'success': True,
                'message': 'Schedule information retrieved successfully',
                'data': {
                    'schedule_status': schedule_status,
                    'recommendation': recommendation,
                    'average_interval_minutes': round(avg_interval, 2),
                    'latest_snapshot_age': latest.snapshot_age_minutes if latest else None,
                    'total_snapshots_24h': DashboardSnapshot.objects.filter(
                        created_at__gte=timezone.now() - timezone.timedelta(hours=24)
                    ).count(),
                    'cron_instructions': cron_instructions,
                    'recent_intervals': [round(interval, 2) for interval in intervals[-10:]]
                }
            }, status=status.HTTP_200_OK)
            
        except Exception as e:
            logger.error(f"Error retrieving schedule info: {str(e)}")
            return Response({
                'success': False,
                'message': f'Error retrieving schedule info: {str(e)}',
                'data': None
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
