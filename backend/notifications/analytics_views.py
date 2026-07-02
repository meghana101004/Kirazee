from rest_framework.decorators import api_view
from rest_framework import status
from rest_framework.response import Response
from django.http import JsonResponse
import logging

from .analytics_service import CampaignAnalyticsService

logger = logging.getLogger(__name__)


@api_view(["GET"])
def campaign_detailed_stats(request, campaign_id: int):
    """
    Get comprehensive campaign statistics with recipient breakdown
    GET /api/notifications/campaigns/<int:campaign_id>/detailed-stats/
    """
    try:
        stats = CampaignAnalyticsService.get_campaign_detailed_stats(campaign_id)
        
        if 'error' in stats:
            return Response({
                'success': False,
                'message': stats['error']
            }, status=status.HTTP_404_NOT_FOUND)
        
        return Response({
            'success': True,
            'data': stats
        })
        
    except Exception as e:
        logger.error(f"Error in campaign_detailed_stats view: {str(e)}")
        return Response({
            'success': False,
            'message': 'Internal server error'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(["GET"])
def campaign_recipients(request, campaign_id: int):
    """
    Get paginated list of campaign recipients with filtering
    GET /api/notifications/campaigns/<int:campaign_id>/recipients/
    
    Query parameters:
    - status: filter by status (sent, failed, pending, skipped)
    - channel: filter by channel (firebase, email, whatsapp)
    - page: page number (default: 1)
    - per_page: items per page (default: 50)
    """
    try:
        # Get query parameters
        status_filter = request.GET.get('status')
        channel_filter = request.GET.get('channel')
        page = int(request.GET.get('page', 1))
        per_page = min(int(request.GET.get('per_page', 50)), 100)  # Max 100 per page
        
        # Validate parameters
        valid_statuses = ['sent', 'failed', 'pending', 'skipped']
        if status_filter and status_filter not in valid_statuses:
            return Response({
                'success': False,
                'message': f'Invalid status. Must be one of: {valid_statuses}'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        valid_channels = ['firebase', 'email', 'whatsapp']
        if channel_filter and channel_filter not in valid_channels:
            return Response({
                'success': False,
                'message': f'Invalid channel. Must be one of: {valid_channels}'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        if page < 1:
            page = 1
        if per_page < 1:
            per_page = 50
        
        result = CampaignAnalyticsService.get_campaign_recipients(
            campaign_id=campaign_id,
            status=status_filter,
            channel=channel_filter,
            page=page,
            per_page=per_page
        )
        
        if not result.get('success'):
            status_code = status.HTTP_404_NOT_FOUND if 'not found' in result.get('error', '').lower() else status.HTTP_400_BAD_REQUEST
            return Response({
                'success': False,
                'message': result.get('error', 'Unknown error')
            }, status=status_code)
        
        return Response(result)
        
    except ValueError as e:
        return Response({
            'success': False,
            'message': 'Invalid parameter format'
        }, status=status.HTTP_400_BAD_REQUEST)
    except Exception as e:
        logger.error(f"Error in campaign_recipients view: {str(e)}")
        return Response({
            'success': False,
            'message': 'Internal server error'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(["POST"])
def retry_failed_notifications(request, campaign_id: int):
    """
    Retry failed notifications for a campaign
    POST /api/notifications/campaigns/<int:campaign_id>/retry/
    
    Request body:
    {
        "user_ids": [1, 2, 3],  // Optional - specific users to retry
        "channels": "all"        // Optional - "all", "firebase", "email"
    }
    """
    try:
        data = request.data or {}
        user_ids = data.get('user_ids')
        channels = data.get('channels', 'all')
        
        # Validate parameters
        if user_ids is not None:
            if not isinstance(user_ids, list):
                return Response({
                    'success': False,
                    'message': 'user_ids must be an array'
                }, status=status.HTTP_400_BAD_REQUEST)
            
            if not all(isinstance(uid, int) for uid in user_ids):
                return Response({
                    'success': False,
                    'message': 'All user_ids must be integers'
                }, status=status.HTTP_400_BAD_REQUEST)
        
        valid_channels = ['all', 'firebase', 'email']
        if channels not in valid_channels:
            return Response({
                'success': False,
                'message': f'Invalid channels. Must be one of: {valid_channels}'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        result = CampaignAnalyticsService.retry_failed_notifications(
            campaign_id=campaign_id,
            user_ids=user_ids,
            channels=channels
        )
        
        if not result.get('success'):
            status_code = status.HTTP_404_NOT_FOUND if 'not found' in result.get('error', '').lower() else status.HTTP_400_BAD_REQUEST
            return Response({
                'success': False,
                'message': result.get('error', 'Unknown error')
            }, status=status_code)
        
        return Response(result)
        
    except Exception as e:
        logger.error(f"Error in retry_failed_notifications view: {str(e)}")
        return Response({
            'success': False,
            'message': 'Internal server error'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(["GET"])
def campaign_performance_overview(request, campaign_id: int):
    """
    Get campaign performance overview with charts data
    GET /api/notifications/campaigns/<int:campaign_id>/performance/
    """
    try:
        # Get detailed stats
        detailed_stats = CampaignAnalyticsService.get_campaign_detailed_stats(campaign_id)
        
        if 'error' in detailed_stats:
            return Response({
                'success': False,
                'message': detailed_stats['error']
            }, status=status.HTTP_404_NOT_FOUND)
        
        # Prepare chart data
        recipient_breakdown = detailed_stats.get('recipient_breakdown', {})
        channel_breakdown = detailed_stats.get('channel_breakdown', {})
        delivery_stats = detailed_stats.get('delivery_statistics', {})
        
        # Status distribution for pie chart
        status_distribution = [
            { 'name': 'Sent', 'value': len(recipient_breakdown.get('sent', [])), 'color': '#52c41a' },
            { 'name': 'Failed', 'value': len(recipient_breakdown.get('failed', [])), 'color': '#ff4d4f' },
            { 'name': 'Pending', 'value': len(recipient_breakdown.get('pending', [])), 'color': '#faad14' },
            { 'name': 'Skipped', 'value': len(recipient_breakdown.get('skipped', [])), 'color': '#8c8c8c' }
        ]
        
        # Channel performance for bar chart
        channel_performance = []
        for channel, stats in channel_breakdown.items():
            sent = len(stats.get('sent', []))
            failed = len(stats.get('failed', []))
            pending = len(stats.get('pending', []))
            
            channel_performance.append({
                'channel': channel.capitalize(),
                'sent': sent,
                'failed': failed,
                'pending': pending,
                'total': sent + failed + pending,
                'success_rate': (sent / (sent + failed) * 100) if (sent + failed) > 0 else 0
            })
        
        # Timeline data (recent logs)
        recent_logs = detailed_stats.get('notification_logs', {}).get('recent_logs', [])
        timeline_data = []
        for log in recent_logs:
            timeline_data.append({
                'time': log.get('created_at'),
                'user_id': log.get('user_id'),
                'status': log.get('status'),
                'channel': log.get('channel')
            })
        
        return Response({
            'success': True,
            'data': {
                'campaign_summary': {
                    'name': detailed_stats.get('campaign_name'),
                    'type': detailed_stats.get('campaign_type'),
                    'status': detailed_stats.get('status'),
                    'total_recipients': detailed_stats.get('total_recipients'),
                    'created_at': detailed_stats.get('created_at'),
                    'sent_at': detailed_stats.get('sent_at')
                },
                'status_distribution': status_distribution,
                'channel_performance': channel_performance,
                'delivery_statistics': delivery_stats,
                'timeline_data': timeline_data,
                'target_users_count': len(detailed_stats.get('target_users', [])),
                'notification_logs_summary': detailed_stats.get('notification_logs', {})
            }
        })
        
    except Exception as e:
        logger.error(f"Error in campaign_performance_overview view: {str(e)}")
        return Response({
            'success': False,
            'message': 'Internal server error'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(["GET"])
def export_campaign_data(request, campaign_id: int):
    """
    Export campaign data as CSV
    GET /api/notifications/campaigns/<int:campaign_id>/export/
    
    Query parameters:
    - format: export format (csv, json) - default: csv
    - status: filter by status (optional)
    - channel: filter by channel (optional)
    """
    try:
        export_format = request.GET.get('format', 'csv')
        status_filter = request.GET.get('status')
        channel_filter = request.GET.get('channel')
        
        if export_format not in ['csv', 'json']:
            return Response({
                'success': False,
                'message': 'Invalid format. Must be csv or json'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Get recipients data
        result = CampaignAnalyticsService.get_campaign_recipients(
            campaign_id=campaign_id,
            status=status_filter,
            channel=channel_filter,
            page=1,
            per_page=10000  # Large number for export
        )
        
        if not result.get('success'):
            return Response({
                'success': False,
                'message': result.get('error', 'Unknown error')
            }, status=status.HTTP_400_BAD_REQUEST)
        
        recipients = result.get('recipients', [])
        campaign_name = result.get('campaign_name', f'campaign_{campaign_id}')
        
        if export_format == 'csv':
            import csv
            from django.http import HttpResponse
            import io
            
            output = io.StringIO()
            writer = csv.writer(output)
            
            # Write header
            writer.writerow([
                'User ID', 'User Name', 'Email', 'Mobile', 'User Mode',
                'Business Name', 'Status', 'Channel', 'Error', 'Sent At', 'Created At'
            ])
            
            # Write data
            for recipient in recipients:
                writer.writerow([
                    recipient.get('user_id', ''),
                    recipient.get('user_name', ''),
                    recipient.get('user_email', ''),
                    recipient.get('user_mobile', ''),
                    recipient.get('user_mode', ''),
                    recipient.get('business_name', ''),
                    recipient.get('status', ''),
                    recipient.get('channel', ''),
                    recipient.get('error', ''),
                    recipient.get('sent_at', ''),
                    recipient.get('created_at', '')
                ])
            
            # Create response
            response = HttpResponse(
                output.getvalue(),
                content_type='text/csv'
            )
            response['Content-Disposition'] = f'attachment; filename="{campaign_name}_recipients.csv"'
            return response
        
        else:  # JSON format
            return JsonResponse({
                'success': True,
                'campaign_id': campaign_id,
                'campaign_name': campaign_name,
                'export_timestamp': timezone.now().isoformat(),
                'filters': {
                    'status': status_filter,
                    'channel': channel_filter
                },
                'total_recipients': len(recipients),
                'recipients': recipients
            })
        
    except Exception as e:
        logger.error(f"Error in export_campaign_data view: {str(e)}")
        return Response({
            'success': False,
            'message': 'Internal server error'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
