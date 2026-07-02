from django.utils import timezone
from django.db import connection
from typing import List, Dict, Any, Optional, Set
import logging
import json
import time
from datetime import datetime, timedelta

from .models import SuperadminNotificationCampaign, NotificationLog
from .targeting_service import TargetAudienceService
from .service import send_order_notification, send_email_notification

logger = logging.getLogger(__name__)


class CampaignExecutionService:
    
    @staticmethod
    def execute_campaign(campaign_id: int, dry_run: bool = False) -> Dict[str, Any]:
        """Execute campaign delivery based on target criteria
        
        Args:
            campaign_id: ID of the campaign to execute
            dry_run: If True, preview without actually sending
        """
        start_time = time.time()
        execution_id = f"{campaign_id}_{int(start_time)}"
        
        try:
            campaign = SuperadminNotificationCampaign.objects.get(id=campaign_id)
            logger.info(f"[{execution_id}] Starting campaign execution: {campaign.campaign_name}")
            
            # Update status to processing
            if not dry_run:
                campaign.status = 'processing'
                campaign.save()
            
            # Get target users
            target_users = CampaignExecutionService._get_target_users(campaign)
            campaign.total_recipients = len(target_users)
            
            if not dry_run:
                campaign.save()
            
            if not target_users:
                campaign.status = 'sent'  # No recipients, mark as sent
                campaign.error_message = "No target users found"
                if not dry_run:
                    campaign.save()
                return {
                    'success': True,
                    'message': 'No target users found',
                    'total_recipients': 0,
                    'execution_time': time.time() - start_time,
                    'dry_run': dry_run
                }
            
            # Analyze target users
            user_analysis = CampaignExecutionService._analyze_target_users(target_users, campaign.channels)
            logger.info(f"[{execution_id}] Target analysis: {user_analysis}")
            
            # Send notifications
            if dry_run:
                results = CampaignExecutionService._preview_campaign_notifications(campaign, target_users)
            else:
                results = CampaignExecutionService._send_campaign_notifications(campaign, target_users, execution_id)
            
            # Update campaign statistics
            if not dry_run:
                campaign.firebase_sent = results.get('firebase_sent', 0)
                campaign.email_sent = results.get('email_sent', 0)
                campaign.whatsapp_sent = results.get('whatsapp_sent', 0)
                campaign.firebase_failed = results.get('firebase_failed', 0)
                campaign.email_failed = results.get('email_failed', 0)
                campaign.whatsapp_failed = results.get('whatsapp_failed', 0)
                campaign.sent_at = timezone.now()
                
                # Determine final status
                total_sent = campaign.firebase_sent + campaign.email_sent + campaign.whatsapp_sent
                total_failed = campaign.firebase_failed + campaign.email_failed + campaign.whatsapp_failed
                
                if total_failed == 0:
                    campaign.status = 'sent'
                elif total_sent == 0:
                    campaign.status = 'failed'
                    campaign.error_message = "All notifications failed to send"
                else:
                    campaign.status = 'sent'  # Partial success still counts as sent
                
                campaign.save()
            
            execution_time = time.time() - start_time
            logger.info(f"[{execution_id}] Campaign execution completed in {execution_time:.2f}s")
            
            return {
                'success': True,
                'total_recipients': campaign.total_recipients,
                'sent': results.get('firebase_sent', 0) + results.get('email_sent', 0) + results.get('whatsapp_sent', 0),
                'failed': results.get('firebase_failed', 0) + results.get('email_failed', 0) + results.get('whatsapp_failed', 0),
                'results': results,
                'user_analysis': user_analysis,
                'execution_time': execution_time,
                'dry_run': dry_run
            }
            
        except SuperadminNotificationCampaign.DoesNotExist:
            return {
                'success': False,
                'error': 'Campaign not found',
                'execution_time': time.time() - start_time
            }
        except Exception as e:
            execution_time = time.time() - start_time
            logger.error(f"[{execution_id}] Error executing campaign {campaign_id}: {str(e)}")
            try:
                campaign = SuperadminNotificationCampaign.objects.get(id=campaign_id)
                campaign.status = 'failed'
                campaign.error_message = str(e)
                campaign.save()
            except:
                pass
            return {
                'success': False,
                'error': str(e),
                'execution_time': execution_time
            }
    
    @staticmethod
    def _get_target_users(campaign: SuperadminNotificationCampaign) -> List[Dict[str, Any]]:
        """Get list of target users based on campaign criteria"""
        target_users = []
        seen_user_ids: Set[int] = set()  # Track to avoid duplicates
        
        logger.info(f"Getting target users for campaign {campaign.id}: target_all_users={campaign.target_all_users}")
        logger.info(f"Campaign type: {campaign.campaign_type}")
        logger.info(f"Target user IDs: {campaign.target_user_ids}")
        logger.info(f"Target business IDs: {campaign.target_business_ids}")
        logger.info(f"Target user modes: {campaign.target_user_modes}")
        
        # If targeting all users
        if campaign.target_all_users:
            target_users = TargetAudienceService.get_all_users(limit=10000)  # Large limit for all users
            logger.info(f"Found {len(target_users)} users for 'all users' targeting")
            return target_users
        
        # For user_targeted campaigns, ONLY use the specific user IDs
        if campaign.campaign_type == 'user_targeted' and campaign.target_user_ids:
            users_by_ids = TargetAudienceService.get_users_by_ids(campaign.target_user_ids)
            logger.info(f"User-targeted campaign: Found {len(users_by_ids)} users by IDs: {campaign.target_user_ids}")
            
            # Filter by user modes if specified
            if campaign.target_user_modes:
                filtered_users = [user for user in users_by_ids if user.get('user_mode') in campaign.target_user_modes]
                logger.info(f"Filtered to {len(filtered_users)} users by modes: {campaign.target_user_modes}")
                return filtered_users
            return users_by_ids
        
        # For other campaign types, use combination of targeting criteria
        # Get users by specific criteria
        if campaign.target_user_ids:
            users_by_ids = TargetAudienceService.get_users_by_ids(campaign.target_user_ids)
            logger.info(f"Found {len(users_by_ids)} users by IDs: {campaign.target_user_ids}")
            for user in users_by_ids:
                if user['id'] not in seen_user_ids:
                    target_users.append(user)
                    seen_user_ids.add(user['id'])
        
        if campaign.target_business_ids:
            users_by_business = TargetAudienceService.get_users_by_business_ids(campaign.target_business_ids)
            logger.info(f"Found {len(users_by_business)} users by businesses: {campaign.target_business_ids}")
            for user in users_by_business:
                if user['id'] not in seen_user_ids:
                    target_users.append(user)
                    seen_user_ids.add(user['id'])
        
        # Only use target_user_modes if no specific user IDs or business IDs are provided
        # This prevents fetching all users of a mode when specific targeting is intended
        if not campaign.target_user_ids and not campaign.target_business_ids and campaign.target_user_modes:
            users_by_modes = TargetAudienceService.get_users_by_modes(campaign.target_user_modes)
            logger.info(f"Found {len(users_by_modes)} users by modes: {campaign.target_user_modes}")
            for user in users_by_modes:
                if user['id'] not in seen_user_ids:
                    target_users.append(user)
                    seen_user_ids.add(user['id'])
        elif campaign.target_user_modes and (campaign.target_user_ids or campaign.target_business_ids):
            # If modes are specified along with specific IDs, filter the existing users
            logger.info(f"Filtering existing {len(target_users)} users by modes: {campaign.target_user_modes}")
            target_users = [user for user in target_users if user.get('user_mode') in campaign.target_user_modes]
            logger.info(f"Filtered to {len(target_users)} users after mode filtering")
        
        logger.info(f"Total unique target users: {len(target_users)}")
        return target_users
    
    @staticmethod
    def _send_campaign_notifications(campaign: SuperadminNotificationCampaign, 
                                   target_users: List[Dict[str, Any]],
                                   execution_id: str = None) -> Dict[str, Any]:
        """Send campaign to specific users via specified channels"""
        results = {
            'firebase_sent': 0,
            'email_sent': 0,
            'whatsapp_sent': 0,
            'firebase_failed': 0,
            'email_failed': 0,
            'whatsapp_failed': 0
        }
        
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
        
        # Determine which channels to use
        channels = campaign.channels.lower()
        logger.info(f"[{execution_id}] Sending notifications via {channels} to {len(target_users)} users")
        
        for i, user in enumerate(target_users):
            user_id = user['id']
            
            # Log progress for large campaigns
            if execution_id and (i + 1) % 100 == 0:
                logger.info(f"[{execution_id}] Processed {i + 1}/{len(target_users)} users")
            
            # Send Firebase notification
            if channels in ['all', 'firebase']:
                try:
                    if user.get('fcm_token'):
                        # Enhanced notification with media support
                        fcm_result = send_order_notification(
                            user_id=user_id,
                            title=campaign.title,
                            body=campaign.message,
                            data=notification_data,
                            image_url=campaign.media_url
                        )
                        if fcm_result:
                            results['firebase_sent'] += 1
                        else:
                            results['firebase_failed'] += 1
                    else:
                        results['firebase_failed'] += 1
                except Exception as e:
                    logger.error(f"[{execution_id}] Firebase send failed for user {user_id}: {str(e)}")
                    results['firebase_failed'] += 1
            
            # Send Email notification
            if channels in ['all', 'email']:
                try:
                    if user.get('email'):
                        email_result = send_email_notification(
                            user_id=user_id,
                            subject=campaign.title,
                            body=campaign.message,
                            data=notification_data
                        )
                        if email_result:
                            results['email_sent'] += 1
                        else:
                            results['email_failed'] += 1
                    else:
                        results['email_failed'] += 1
                except Exception as e:
                    logger.error(f"[{execution_id}] Email send failed for user {user_id}: {str(e)}")
                    results['email_failed'] += 1
            
            # Send WhatsApp notification (placeholder for future implementation)
            if channels in ['all', 'whatsapp']:
                # WhatsApp integration would go here
                # For now, we'll skip WhatsApp
                pass
        
        logger.info(f"[{execution_id}] Final results: {results}")
        return results
    
    @staticmethod
    def _analyze_target_users(target_users: List[Dict[str, Any]], channels: str) -> Dict[str, Any]:
        """Analyze target users for campaign delivery"""
        analysis = {
            'total_users': len(target_users),
            'firebase_eligible': 0,
            'email_eligible': 0,
            'whatsapp_eligible': 0,
            'user_modes': {},
            'business_distribution': {},
            'device_types': {}
        }
        
        channels = channels.lower()
        
        for user in target_users:
            # Channel eligibility
            if channels in ['all', 'firebase'] and user.get('fcm_token'):
                analysis['firebase_eligible'] += 1
            if channels in ['all', 'email'] and user.get('email'):
                analysis['email_eligible'] += 1
            # WhatsApp eligibility would be determined here
            
            # User modes distribution
            mode = user.get('user_mode', 'unknown')
            analysis['user_modes'][mode] = analysis['user_modes'].get(mode, 0) + 1
            
            # Business distribution
            business_id = user.get('business_id')
            if business_id:
                analysis['business_distribution'][business_id] = analysis['business_distribution'].get(business_id, 0) + 1
            
            # Device types
            device_type = user.get('device_type', 'unknown')
            analysis['device_types'][device_type] = analysis['device_types'].get(device_type, 0) + 1
        
        return analysis
    
    @staticmethod
    def _preview_campaign_notifications(campaign: SuperadminNotificationCampaign, 
                                      target_users: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Preview campaign notifications without actually sending"""
        results = {
            'firebase_sent': 0,
            'email_sent': 0,
            'whatsapp_sent': 0,
            'firebase_failed': 0,
            'email_failed': 0,
            'whatsapp_failed': 0
        }
        
        channels = campaign.channels.lower()
        
        for user in target_users:
            # Simulate Firebase eligibility
            if channels in ['all', 'firebase']:
                if user.get('fcm_token'):
                    results['firebase_sent'] += 1
                else:
                    results['firebase_failed'] += 1
            
            # Simulate Email eligibility
            if channels in ['all', 'email']:
                if user.get('email'):
                    results['email_sent'] += 1
                else:
                    results['email_failed'] += 1
            
            # WhatsApp simulation
            if channels in ['all', 'whatsapp']:
                # For now, assume all users are eligible for WhatsApp in preview
                results['whatsapp_sent'] += 1
        
        return results
    
    @staticmethod
    def schedule_campaign(campaign_id: int, scheduled_time: timezone.datetime) -> Dict[str, Any]:
        """Schedule campaign for later delivery"""
        try:
            campaign = SuperadminNotificationCampaign.objects.get(id=campaign_id)
            campaign.scheduled_at = scheduled_time
            campaign.status = 'scheduled'
            campaign.save()
            
            # In a production environment, you would use Celery or similar
            # to handle the scheduled execution
            logger.info(f"Campaign {campaign_id} scheduled for {scheduled_time}")
            
            return {
                'success': True,
                'message': f'Campaign scheduled for {scheduled_time}',
                'scheduled_at': scheduled_time
            }
            
        except SuperadminNotificationCampaign.DoesNotExist:
            return {
                'success': False,
                'error': 'Campaign not found'
            }
        except Exception as e:
            logger.error(f"Error scheduling campaign {campaign_id}: {str(e)}")
            return {
                'success': False,
                'error': str(e)
            }
    
    @staticmethod
    def cancel_campaign(campaign_id: int) -> Dict[str, Any]:
        """Cancel a scheduled campaign"""
        try:
            campaign = SuperadminNotificationCampaign.objects.get(id=campaign_id)
            
            if campaign.status not in ['draft', 'scheduled']:
                return {
                    'success': False,
                    'error': f'Cannot cancel campaign in {campaign.status} status'
                }
            
            campaign.status = 'cancelled'
            campaign.save()
            
            return {
                'success': True,
                'message': 'Campaign cancelled successfully'
            }
            
        except SuperadminNotificationCampaign.DoesNotExist:
            return {
                'success': False,
                'error': 'Campaign not found'
            }
        except Exception as e:
            logger.error(f"Error cancelling campaign {campaign_id}: {str(e)}")
            return {
                'success': False,
                'error': str(e)
            }
    
    @staticmethod
    def get_campaign_preview(campaign_id: int) -> Dict[str, Any]:
        """Get preview of campaign without sending"""
        try:
            campaign = SuperadminNotificationCampaign.objects.get(id=campaign_id)
            target_users = CampaignExecutionService._get_target_users(campaign)
            
            # Get channel breakdown
            channels = campaign.channels.lower()
            channel_breakdown = {
                'total_users': len(target_users),
                'firebase_eligible': 0,
                'email_eligible': 0,
                'whatsapp_eligible': 0
            }
            
            for user in target_users:
                if channels in ['all', 'firebase'] and user.get('fcm_token'):
                    channel_breakdown['firebase_eligible'] += 1
                if channels in ['all', 'email'] and user.get('email'):
                    channel_breakdown['email_eligible'] += 1
                # WhatsApp eligibility would be determined here
            
            return {
                'success': True,
                'campaign': {
                    'id': campaign.id,
                    'name': campaign.campaign_name,
                    'type': campaign.campaign_type,
                    'title': campaign.title,
                    'message': campaign.message,
                    'channels': campaign.channels,
                    'status': campaign.status
                },
                'target_preview': channel_breakdown,
                'sample_users': target_users[:5]  # First 5 users as sample
            }
            
        except SuperadminNotificationCampaign.DoesNotExist:
            return {
                'success': False,
                'error': 'Campaign not found'
            }
        except Exception as e:
            logger.error(f"Error getting campaign preview {campaign_id}: {str(e)}")
            return {
                'success': False,
                'error': str(e)
            }
    
    @staticmethod
    def get_campaign_statistics(campaign_id: int) -> Dict[str, Any]:
        """Get detailed statistics for a campaign"""
        try:
            campaign = SuperadminNotificationCampaign.objects.get(id=campaign_id)
            
            # Get notification logs for this campaign
            notification_logs = NotificationLog.objects.filter(
                data__campaign_id=str(campaign_id)
            ).order_by('-created_at')
            
            # Calculate detailed statistics
            stats = {
                'campaign': {
                    'id': campaign.id,
                    'name': campaign.campaign_name,
                    'type': campaign.campaign_type,
                    'status': campaign.status,
                    'created_at': campaign.created_at,
                    'sent_at': campaign.sent_at,
                    'scheduled_at': campaign.scheduled_at
                },
                'delivery_stats': {
                    'total_recipients': campaign.total_recipients,
                    'firebase_sent': campaign.firebase_sent,
                    'email_sent': campaign.email_sent,
                    'whatsapp_sent': campaign.whatsapp_sent,
                    'firebase_failed': campaign.firebase_failed,
                    'email_failed': campaign.email_failed,
                    'whatsapp_failed': campaign.whatsapp_failed
                },
                'notification_logs': {
                    'total_logs': notification_logs.count(),
                    'sent_logs': notification_logs.filter(status='sent').count(),
                    'failed_logs': notification_logs.filter(status='failed').count(),
                    'skipped_logs': notification_logs.filter(status='skipped').count(),
                    'recent_logs': list(notification_logs.values('user_id', 'title', 'status', 'error', 'created_at')[:10])
                }
            }
            
            return {
                'success': True,
                'statistics': stats
            }
            
        except SuperadminNotificationCampaign.DoesNotExist:
            return {
                'success': False,
                'error': 'Campaign not found'
            }
        except Exception as e:
            logger.error(f"Error getting campaign statistics {campaign_id}: {str(e)}")
            return {
                'success': False,
                'error': str(e)
            }
    
    @staticmethod
    def retry_failed_notifications(campaign_id: int, channels: str = 'firebase') -> Dict[str, Any]:
        """Retry failed notifications for a campaign"""
        try:
            campaign = SuperadminNotificationCampaign.objects.get(id=campaign_id)
            
            if campaign.status not in ['sent', 'failed']:
                return {
                    'success': False,
                    'error': f'Cannot retry campaign in {campaign.status} status'
                }
            
            # Get failed notification logs for this campaign
            failed_logs = NotificationLog.objects.filter(
                data__campaign_id=str(campaign_id),
                status='failed'
            )
            
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
                
                # Retry based on channels
                if channels in ['all', 'firebase']:
                    try:
                        fcm_result = send_order_notification(
                            user_id=user_id,
                            title=log.title,
                            body=log.body,
                            data=log.data
                        )
                        if fcm_result:
                            results['firebase_sent'] += 1
                            retried_count += 1
                    except Exception as e:
                        logger.error(f"Retry failed for user {user_id}: {str(e)}")
                
                # Similar retry logic for email and WhatsApp would go here
            
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
