from django.db import connection, models
from django.utils import timezone
from datetime import timedelta
from typing import Dict, Any, List
import logging

from .models import SuperadminNotificationCampaign, NotificationLog

logger = logging.getLogger(__name__)


class CampaignAnalyticsService:
    
    @staticmethod
    def get_campaign_detailed_stats(campaign_id: int) -> Dict[str, Any]:
        """Return comprehensive campaign statistics with recipient breakdown"""
        try:
            campaign = SuperadminNotificationCampaign.objects.get(id=campaign_id)
            
            # Get detailed notification logs
            notification_logs = NotificationLog.objects.filter(
                data__campaign_id=str(campaign_id)
            ).order_by('-created_at')
            
            # Get user information for all logs
            user_ids = list(set(log.user_id for log in notification_logs))
            user_info_map = CampaignAnalyticsService._get_user_info_map(user_ids)
            
            # Recipient breakdown by status
            recipient_breakdown = {
                'sent': [],
                'failed': [],
                'pending': [],
                'skipped': []
            }
            
            # Channel-specific breakdown
            channel_breakdown = {
                'firebase': {'sent': [], 'failed': [], 'pending': []},
                'email': {'sent': [], 'failed': [], 'pending': []},
                'whatsapp': {'sent': [], 'failed': [], 'pending': []}
            }
            
            # Process notification logs
            for log in notification_logs:
                user_info = user_info_map.get(log.user_id, {
                    'full_name': 'Unknown',
                    'emailID': 'N/A',
                    'user_mode': 'N/A',
                    'business_name': 'N/A'
                })
                
                user_data = {
                    'user_id': log.user_id,
                    'user_name': user_info['full_name'],
                    'user_email': user_info['emailID'],
                    'user_mode': user_info['user_mode'],
                    'business_name': user_info['business_name'],
                    'status': log.status,
                    'channel': log.data.get('channel', 'all') if log.data else 'all',
                    'error': log.error,
                    'sent_at': log.delivered_at,
                    'created_at': log.created_at
                }
                
                # Add to recipient breakdown
                if log.status in recipient_breakdown:
                    recipient_breakdown[log.status].append(user_data)
                
                # Add to channel breakdown
                channel = user_data['channel']
                if channel in channel_breakdown and log.status in channel_breakdown[channel]:
                    channel_breakdown[channel][log.status].append(user_data)
            
            # Calculate success rates
            total_attempts = (campaign.firebase_sent + campaign.email_sent + campaign.whatsapp_sent +
                            campaign.firebase_failed + campaign.email_failed + campaign.whatsapp_failed)
            
            firebase_success_rate = 0
            if campaign.firebase_sent + campaign.firebase_failed > 0:
                firebase_success_rate = (campaign.firebase_sent / 
                                       (campaign.firebase_sent + campaign.firebase_failed)) * 100
            
            email_success_rate = 0
            if campaign.email_sent + campaign.email_failed > 0:
                email_success_rate = (campaign.email_sent / 
                                    (campaign.email_sent + campaign.email_failed)) * 100
            
            overall_success_rate = 0
            if total_attempts > 0:
                overall_success_rate = ((campaign.firebase_sent + campaign.email_sent + campaign.whatsapp_sent) / 
                                       total_attempts) * 100
            
            # Get target users details
            target_users = CampaignAnalyticsService._get_campaign_target_users(campaign)
            
            return {
                'campaign_id': campaign.id,
                'campaign_name': campaign.campaign_name,
                'campaign_type': campaign.campaign_type,
                'status': campaign.status,
                'created_at': campaign.created_at,
                'sent_at': campaign.sent_at,
                'scheduled_at': campaign.scheduled_at,
                'total_recipients': campaign.total_recipients,
                'target_users': target_users,
                'recipient_breakdown': recipient_breakdown,
                'channel_breakdown': channel_breakdown,
                'delivery_statistics': {
                    'firebase': {
                        'sent': campaign.firebase_sent,
                        'failed': campaign.firebase_failed,
                        'success_rate': round(firebase_success_rate, 2)
                    },
                    'email': {
                        'sent': campaign.email_sent,
                        'failed': campaign.email_failed,
                        'success_rate': round(email_success_rate, 2)
                    },
                    'whatsapp': {
                        'sent': campaign.whatsapp_sent,
                        'failed': campaign.whatsapp_failed,
                        'success_rate': 0  # Not implemented yet
                    },
                    'overall': {
                        'total_sent': campaign.firebase_sent + campaign.email_sent + campaign.whatsapp_sent,
                        'total_failed': campaign.firebase_failed + campaign.email_failed + campaign.whatsapp_failed,
                        'success_rate': round(overall_success_rate, 2)
                    }
                },
                'notification_logs': {
                    'total_logs': notification_logs.count(),
                    'sent_logs': notification_logs.filter(status='sent').count(),
                    'failed_logs': notification_logs.filter(status='failed').count(),
                    'skipped_logs': notification_logs.filter(status='skipped').count(),
                    'recent_logs': list(notification_logs.values(
                        'user_id', 'title', 'status', 'error', 'created_at', 'delivered_at'
                    )[:10])
                }
            }
            
        except SuperadminNotificationCampaign.DoesNotExist:
            return {
                'error': 'Campaign not found'
            }
        except Exception as e:
            logger.error(f"Error getting campaign detailed stats {campaign_id}: {str(e)}")
            return {
                'error': str(e)
            }
    
    @staticmethod
    def get_campaign_recipients(campaign_id: int, status: str = None, channel: str = None, 
                                page: int = 1, per_page: int = 50) -> Dict[str, Any]:
        """Get paginated list of campaign recipients with filtering"""
        try:
            campaign = SuperadminNotificationCampaign.objects.get(id=campaign_id)
            
            # Base query
            logs_query = NotificationLog.objects.filter(
                data__campaign_id=str(campaign_id)
            )
            
            # Apply filters
            if status:
                logs_query = logs_query.filter(status=status)
            if channel:
                # Filter by channel in the data JSON field
                logs_query = logs_query.filter(data__channel=channel)
            
            # Pagination
            offset = (page - 1) * per_page
            total_count = logs_query.count()
            logs = logs_query[offset:offset + per_page]
            
            # Get user information for all logs
            user_ids = list(set(log.user_id for log in logs))
            user_info_map = CampaignAnalyticsService._get_user_info_map(user_ids)
            
            # Format recipient data
            recipients = []
            for log in logs:
                user_info = user_info_map.get(log.user_id, {
                    'full_name': 'Unknown',
                    'emailID': 'N/A',
                    'mobileNumber': 'N/A',
                    'user_mode': 'N/A',
                    'business_name': 'N/A'
                })
                
                recipient_data = {
                    'user_id': log.user_id,
                    'user_name': user_info['full_name'],
                    'user_email': user_info['emailID'],
                    'user_mobile': user_info['mobileNumber'],
                    'user_mode': user_info['user_mode'],
                    'business_name': user_info['business_name'],
                    'status': log.status,
                    'channel': log.data.get('channel', 'all') if log.data else 'all',
                    'error': log.error,
                    'sent_at': log.delivered_at,
                    'created_at': log.created_at,
                    'retry_count': 0  # Not tracked in current model
                }
                recipients.append(recipient_data)
            
            return {
                'success': True,
                'campaign_id': campaign_id,
                'campaign_name': campaign.campaign_name,
                'recipients': recipients,
                'pagination': {
                    'current_page': page,
                    'per_page': per_page,
                    'total_count': total_count,
                    'total_pages': (total_count + per_page - 1) // per_page
                },
                'filters': {
                    'status': status,
                    'channel': channel
                }
            }
            
        except SuperadminNotificationCampaign.DoesNotExist:
            return {
                'success': False,
                'error': 'Campaign not found'
            }
        except Exception as e:
            logger.error(f"Error getting campaign recipients {campaign_id}: {str(e)}")
            return {
                'success': False,
                'error': str(e)
            }
    
    @staticmethod
    def retry_failed_notifications(campaign_id: int, user_ids: List[int] = None, 
                                   channels: str = 'all') -> Dict[str, Any]:
        """Retry failed notifications for specific users or all failed notifications"""
        try:
            campaign = SuperadminNotificationCampaign.objects.get(id=campaign_id)
            
            if campaign.status not in ['sent', 'failed']:
                return {
                    'success': False,
                    'error': f'Cannot retry campaign in {campaign.status} status'
                }
            
            # Get failed notification logs
            logs_query = NotificationLog.objects.filter(
                data__campaign_id=str(campaign_id),
                status='failed'
            )
            
            if user_ids:
                logs_query = logs_query.filter(user_id__in=user_ids)
            
            failed_logs = logs_query
            
            if not failed_logs.exists():
                return {
                    'success': True,
                    'message': 'No failed notifications to retry',
                    'retried_count': 0
                }
            
            retried_count = 0
            results = {'firebase_sent': 0, 'email_sent': 0, 'whatsapp_sent': 0}
            
            for log in failed_logs:
                user_id = log.user_id
                
                # Prepare notification data
                notification_data = {
                    'type': 'CAMPAIGN_NOTIFICATION',
                    'campaign_id': campaign.id,
                    'campaign_type': campaign.campaign_type,
                    'campaign_name': campaign.campaign_name
                }
                
                if campaign.media_url:
                    notification_data['media_url'] = campaign.media_url
                    notification_data['media_type'] = campaign.media_type
                
                # Retry based on channels
                if channels in ['all', 'firebase']:
                    try:
                        from .service import send_order_notification
                        fcm_result = send_order_notification(
                            user_id=user_id,
                            title=log.title,
                            body=log.body,
                            data=notification_data,
                            image_url=campaign.media_url
                        )
                        if fcm_result:
                            results['firebase_sent'] += 1
                            retried_count += 1
                            # Update log status
                            log.status = 'sent'
                            log.delivered_at = timezone.now()
                            log.error = None
                            log.save()
                    except Exception as e:
                        logger.error(f"Retry failed for user {user_id}: {str(e)}")
                
                if channels in ['all', 'email']:
                    try:
                        from .service import send_email_notification
                        email_result = send_email_notification(
                            user_id=user_id,
                            subject=log.title,
                            body=log.body,
                            data=notification_data
                        )
                        if email_result:
                            results['email_sent'] += 1
                            retried_count += 1
                            # Update log status
                            log.status = 'sent'
                            log.delivered_at = timezone.now()
                            log.error = None
                            log.save()
                    except Exception as e:
                        logger.error(f"Email retry failed for user {user_id}: {str(e)}")
            
            return {
                'success': True,
                'message': f'Retried {retried_count} notifications',
                'retried_count': retried_count,
                'results': results
            }
            
        except SuperadminNotificationCampaign.DoesNotExist:
            return {
                'success': False,
                'error': 'Campaign not found'
            }
        except Exception as e:
            logger.error(f"Error retrying campaign {campaign_id}: {str(e)}")
            return {
                'success': False,
                'error': str(e)
            }
    
    @staticmethod
    def _get_user_info_map(user_ids: List[int]) -> Dict[int, Dict[str, Any]]:
        """Get user information map for given user IDs"""
        if not user_ids:
            return {}
        
        try:
            with connection.cursor() as cursor:
                placeholders = ','.join(['%s'] * len(user_ids))
                query = f"""
                    SELECT 
                        r.user_id,
                        CONCAT(r.firstName, ' ', r.lastName) as full_name,
                        r.emailID,
                        r.mobileNumber,
                        r.user_mode,
                        b.businessName as business_name
                    FROM registrations r
                    LEFT JOIN business_mapping bm ON r.user_id = bm.user_id
                    LEFT JOIN businesses b ON bm.business_id = b.business_id
                    WHERE r.user_id IN ({placeholders})
                """
                cursor.execute(query, user_ids)
                results = cursor.fetchall()
                
                user_info_map = {}
                for row in results:
                    user_id, full_name, email, mobile, user_mode, business_name = row
                    user_info_map[user_id] = {
                        'full_name': full_name or 'Unknown',
                        'emailID': email or 'N/A',
                        'mobileNumber': mobile or 'N/A',
                        'user_mode': user_mode or 'N/A',
                        'business_name': business_name or 'N/A'
                    }
                
                return user_info_map
                
        except Exception as e:
            logger.error(f"Error getting user info map: {str(e)}")
            return {}
    
    @staticmethod
    def _get_campaign_target_users(campaign: SuperadminNotificationCampaign) -> List[Dict[str, Any]]:
        """Get detailed information about campaign target users"""
        try:
            from .campaign_service import CampaignExecutionService
            target_users = CampaignExecutionService._get_target_users(campaign)
            
            detailed_users = []
            for user in target_users:
                detailed_users.append({
                    'user_id': user['id'],
                    'user_name': user.get('full_name', 'N/A'),
                    'user_email': user.get('email', 'N/A'),
                    'user_mobile': user.get('mobile', 'N/A'),
                    'user_mode': user.get('user_mode', 'N/A'),
                    'business_id': user.get('business_id'),
                    'business_name': user.get('business_name', 'N/A'),
                    'device_type': user.get('device_type', 'N/A'),
                    'fcm_token': user.get('fcm_token'),
                    'is_active': user.get('is_active', False)
                })
            
            return detailed_users
            
        except Exception as e:
            logger.error(f"Error getting campaign target users: {str(e)}")
            return []
    
    @staticmethod
    def get_campaign_stats(campaign_id: int) -> Dict[str, Any]:
        """Return detailed delivery statistics for a specific campaign"""
        try:
            campaign = SuperadminNotificationCampaign.objects.get(id=campaign_id)
            
            # Calculate success rates
            total_attempts = (campaign.firebase_sent + campaign.email_sent + campaign.whatsapp_sent +
                            campaign.firebase_failed + campaign.email_failed + campaign.whatsapp_failed)
            
            firebase_success_rate = 0
            if campaign.firebase_sent + campaign.firebase_failed > 0:
                firebase_success_rate = (campaign.firebase_sent / 
                                       (campaign.firebase_sent + campaign.firebase_failed)) * 100
            
            email_success_rate = 0
            if campaign.email_sent + campaign.email_failed > 0:
                email_success_rate = (campaign.email_sent / 
                                    (campaign.email_sent + campaign.email_failed)) * 100
            
            overall_success_rate = 0
            if total_attempts > 0:
                overall_success_rate = ((campaign.firebase_sent + campaign.email_sent + campaign.whatsapp_sent) / 
                                       total_attempts) * 100
            
            return {
                'campaign_id': campaign.id,
                'campaign_name': campaign.campaign_name,
                'campaign_type': campaign.campaign_type,
                'status': campaign.status,
                'created_at': campaign.created_at,
                'sent_at': campaign.sent_at,
                'scheduled_at': campaign.scheduled_at,
                'total_recipients': campaign.total_recipients,
                'delivery_statistics': {
                    'firebase': {
                        'sent': campaign.firebase_sent,
                        'failed': campaign.firebase_failed,
                        'success_rate': round(firebase_success_rate, 2)
                    },
                    'email': {
                        'sent': campaign.email_sent,
                        'failed': campaign.email_failed,
                        'success_rate': round(email_success_rate, 2)
                    },
                    'whatsapp': {
                        'sent': campaign.whatsapp_sent,
                        'failed': campaign.whatsapp_failed,
                        'success_rate': 0  # Not implemented yet
                    },
                    'overall': {
                        'total_sent': campaign.firebase_sent + campaign.email_sent + campaign.whatsapp_sent,
                        'total_failed': campaign.firebase_failed + campaign.email_failed + campaign.whatsapp_failed,
                        'success_rate': round(overall_success_rate, 2)
                    }
                }
            }
            
        except SuperadminNotificationCampaign.DoesNotExist:
            return {
                'error': 'Campaign not found'
            }
        except Exception as e:
            logger.error(f"Error getting campaign stats {campaign_id}: {str(e)}")
            return {
                'error': str(e)
            }
    
    @staticmethod
    def get_campaign_stats(campaign_id: int) -> Dict[str, Any]:
        """Return detailed delivery statistics for a specific campaign"""
        try:
            campaign = SuperadminNotificationCampaign.objects.get(id=campaign_id)
            
            # Calculate success rates
            total_attempts = (campaign.firebase_sent + campaign.email_sent + campaign.whatsapp_sent +
                            campaign.firebase_failed + campaign.email_failed + campaign.whatsapp_failed)
            
            firebase_success_rate = 0
            if campaign.firebase_sent + campaign.firebase_failed > 0:
                firebase_success_rate = (campaign.firebase_sent / 
                                       (campaign.firebase_sent + campaign.firebase_failed)) * 100
            
            email_success_rate = 0
            if campaign.email_sent + campaign.email_failed > 0:
                email_success_rate = (campaign.email_sent / 
                                    (campaign.email_sent + campaign.email_failed)) * 100
            
            overall_success_rate = 0
            if total_attempts > 0:
                overall_success_rate = ((campaign.firebase_sent + campaign.email_sent + campaign.whatsapp_sent) / 
                                       total_attempts) * 100
            
            return {
                'campaign_id': campaign.id,
                'campaign_name': campaign.campaign_name,
                'campaign_type': campaign.campaign_type,
                'status': campaign.status,
                'created_at': campaign.created_at,
                'sent_at': campaign.sent_at,
                'scheduled_at': campaign.scheduled_at,
                'total_recipients': campaign.total_recipients,
                'delivery_statistics': {
                    'firebase': {
                        'sent': campaign.firebase_sent,
                        'failed': campaign.firebase_failed,
                        'success_rate': round(firebase_success_rate, 2)
                    },
                    'email': {
                        'sent': campaign.email_sent,
                        'failed': campaign.email_failed,
                        'success_rate': round(email_success_rate, 2)
                    },
                    'whatsapp': {
                        'sent': campaign.whatsapp_sent,
                        'failed': campaign.whatsapp_failed,
                        'success_rate': 0  # Not implemented yet
                    },
                    'overall': {
                        'total_sent': campaign.firebase_sent + campaign.email_sent + campaign.whatsapp_sent,
                        'total_failed': campaign.firebase_failed + campaign.email_failed + campaign.whatsapp_failed,
                        'success_rate': round(overall_success_rate, 2)
                    }
                }
            }
            
        except SuperadminNotificationCampaign.DoesNotExist:
            return {
                'error': 'Campaign not found'
            }
        except Exception as e:
            logger.error(f"Error getting campaign stats {campaign_id}: {str(e)}")
            return {
                'error': str(e)
            }
    
    @staticmethod
    def get_overall_stats() -> Dict[str, Any]:
        """Return overall notification statistics for dashboard"""
        try:
            # Campaign statistics
            total_campaigns = SuperadminNotificationCampaign.objects.count()
            
            campaigns_by_status = {}
            for status, _ in SuperadminNotificationCampaign.STATUS_CHOICES:
                count = SuperadminNotificationCampaign.objects.filter(status=status).count()
                if count > 0:
                    campaigns_by_status[status] = count
            
            campaigns_by_type = {}
            for campaign_type, _ in SuperadminNotificationCampaign.CAMPAIGN_TYPES:
                count = SuperadminNotificationCampaign.objects.filter(campaign_type=campaign_type).count()
                if count > 0:
                    campaigns_by_type[campaign_type] = count
            
            # Delivery statistics
            delivery_stats = SuperadminNotificationCampaign.objects.aggregate(
                total_recipients=models.Sum('total_recipients'),
                firebase_sent=models.Sum('firebase_sent'),
                email_sent=models.Sum('email_sent'),
                whatsapp_sent=models.Sum('whatsapp_sent'),
                firebase_failed=models.Sum('firebase_failed'),
                email_failed=models.Sum('email_failed'),
                whatsapp_failed=models.Sum('whatsapp_failed')
            )
            
            total_recipients = delivery_stats['total_recipients'] or 0
            firebase_sent = delivery_stats['firebase_sent'] or 0
            email_sent = delivery_stats['email_sent'] or 0
            whatsapp_sent = delivery_stats['whatsapp_sent'] or 0
            firebase_failed = delivery_stats['firebase_failed'] or 0
            email_failed = delivery_stats['email_failed'] or 0
            whatsapp_failed = delivery_stats['whatsapp_failed'] or 0
            
            total_sent = firebase_sent + email_sent + whatsapp_sent
            total_failed = firebase_failed + email_failed + whatsapp_failed
            
            # Recent campaigns (last 7 days)
            seven_days_ago = timezone.now() - timedelta(days=7)
            recent_campaigns = SuperadminNotificationCampaign.objects.filter(
                created_at__gte=seven_days_ago
            ).count()
            
            # Active users and businesses
            active_users = CampaignAnalyticsService._get_active_users_count()
            active_businesses = CampaignAnalyticsService._get_active_businesses_count()
            
            return {
                'total_campaigns': total_campaigns,
                'campaigns_by_status': campaigns_by_status,
                'campaigns_by_type': campaigns_by_type,
                'total_recipients': total_recipients,
                'delivery_statistics': {
                    'firebase_sent': firebase_sent,
                    'email_sent': email_sent,
                    'whatsapp_sent': whatsapp_sent,
                    'firebase_failed': firebase_failed,
                    'email_failed': email_failed,
                    'whatsapp_failed': whatsapp_failed,
                    'total_sent': total_sent,
                    'total_failed': total_failed
                },
                'recent_campaigns': recent_campaigns,
                'active_users': active_users,
                'active_businesses': active_businesses
            }
            
        except Exception as e:
            logger.error(f"Error getting overall stats: {str(e)}")
            return {
                'total_campaigns': 0,
                'campaigns_by_status': {},
                'campaigns_by_type': {},
                'total_recipients': 0,
                'delivery_statistics': {
                    'firebase_sent': 0,
                    'email_sent': 0,
                    'whatsapp_sent': 0,
                    'firebase_failed': 0,
                    'email_failed': 0,
                    'whatsapp_failed': 0,
                    'total_sent': 0,
                    'total_failed': 0
                },
                'recent_campaigns': 0,
                'active_users': 0,
                'active_businesses': 0
            }
    
    @staticmethod
    def get_campaign_performance(days: int = 30) -> Dict[str, Any]:
        """Get campaign performance over time"""
        try:
            end_date = timezone.now()
            start_date = end_date - timedelta(days=days)
            
            campaigns = SuperadminNotificationCampaign.objects.filter(
                created_at__gte=start_date,
                created_at__lte=end_date
            ).order_by('created_at')
            
            daily_stats = {}
            for campaign in campaigns:
                date_key = campaign.created_at.date().isoformat()
                if date_key not in daily_stats:
                    daily_stats[date_key] = {
                        'campaigns_created': 0,
                        'campaigns_sent': 0,
                        'total_recipients': 0,
                        'total_sent': 0,
                        'total_failed': 0
                    }
                
                daily_stats[date_key]['campaigns_created'] += 1
                if campaign.status == 'sent':
                    daily_stats[date_key]['campaigns_sent'] += 1
                
                daily_stats[date_key]['total_recipients'] += campaign.total_recipients
                daily_stats[date_key]['total_sent'] += (
                    campaign.firebase_sent + campaign.email_sent + campaign.whatsapp_sent
                )
                daily_stats[date_key]['total_failed'] += (
                    campaign.firebase_failed + campaign.email_failed + campaign.whatsapp_failed
                )
            
            return {
                'period': f'{days} days',
                'start_date': start_date.date().isoformat(),
                'end_date': end_date.date().isoformat(),
                'daily_stats': daily_stats
            }
            
        except Exception as e:
            logger.error(f"Error getting campaign performance: {str(e)}")
            return {
                'period': f'{days} days',
                'start_date': (timezone.now() - timedelta(days=days)).date().isoformat(),
                'end_date': timezone.now().date().isoformat(),
                'daily_stats': {}
            }
    
    @staticmethod
    def get_top_performing_campaigns(limit: int = 10) -> List[Dict[str, Any]]:
        """Get top performing campaigns by delivery success rate"""
        try:
            campaigns = SuperadminNotificationCampaign.objects.filter(
                status='sent',
                total_recipients__gt=0
            ).order_by('-created_at')[:limit]
            
            top_campaigns = []
            for campaign in campaigns:
                total_attempts = (campaign.firebase_sent + campaign.email_sent + campaign.whatsapp_sent +
                                campaign.firebase_failed + campaign.email_failed + campaign.whatsapp_failed)
                
                success_rate = 0
                if total_attempts > 0:
                    success_rate = ((campaign.firebase_sent + campaign.email_sent + campaign.whatsapp_sent) / 
                                   total_attempts) * 100
                
                top_campaigns.append({
                    'id': campaign.id,
                    'campaign_name': campaign.campaign_name,
                    'campaign_type': campaign.campaign_type,
                    'total_recipients': campaign.total_recipients,
                    'success_rate': round(success_rate, 2),
                    'created_at': campaign.created_at,
                    'sent_at': campaign.sent_at
                })
            
            # Sort by success rate
            top_campaigns.sort(key=lambda x: x['success_rate'], reverse=True)
            
            return top_campaigns[:limit]
            
        except Exception as e:
            logger.error(f"Error getting top performing campaigns: {str(e)}")
            return []
    
    @staticmethod
    def _get_active_users_count() -> int:
        """Get count of active users"""
        try:
            with connection.cursor() as cursor:
                query = """
                    SELECT COUNT(*) as count
                    FROM registrations
                    WHERE is_active = 1 AND status = 1
                """
                cursor.execute(query)
                result = cursor.fetchone()
                return result[0] if result else 0
        except Exception as e:
            logger.error(f"Error getting active users count: {str(e)}")
            return 0
    
    @staticmethod
    def _get_active_businesses_count() -> int:
        """Get count of active businesses"""
        try:
            with connection.cursor() as cursor:
                query = """
                    SELECT COUNT(*) as count
                    FROM businesses
                    WHERE status = 1
                """
                cursor.execute(query)
                result = cursor.fetchone()
                return result[0] if result else 0
        except Exception as e:
            logger.error(f"Error getting active businesses count: {str(e)}")
            return 0
