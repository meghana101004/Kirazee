from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from django.utils import timezone
from drf_yasg.utils import swagger_auto_schema

from .models import NotificationLog
from .service import send_notification_test


@swagger_auto_schema(tags=['Notifications'])
class NotificationListView(APIView):
    def get(self, request, user_id: int):
        try:
            qs = NotificationLog.objects.filter(user_id=user_id, is_deleted=False).order_by('-created_at')
            data = []
            for n in qs:
                nf = ''
                try:
                    if isinstance(n.data, dict):
                        nf = str(n.data.get('notification_for') or '')
                except Exception:
                    nf = ''
                if nf == 'delivery_partner':
                    continue
                data.append({
                    "id": n.id,
                    "title": n.title,
                    "body": n.body,
                    "data": n.data,
                    "status": n.status,
                    "fcm_id": n.fcm_id,
                    "is_read": n.is_read,
                    "created_at": n.created_at,
                    "delivered_at": n.delivered_at,
                })
            return Response({"success": True, "notifications": data})
        except Exception as e:
            return Response({"success": False, "error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class DeliveryNotificationListView(APIView):
    def get(self, request, user_id: int):
        try:
            qs = NotificationLog.objects.filter(user_id=user_id, is_deleted=False).order_by('-created_at')
            data = []
            for n in qs:
                nf = ''
                try:
                    if isinstance(n.data, dict):
                        nf = str(n.data.get('notification_for') or '')
                except Exception:
                    nf = ''
                if nf != 'delivery_partner':
                    continue
                data.append({
                    "id": n.id,
                    "title": n.title,
                    "body": n.body,
                    "data": n.data,
                    "status": n.status,
                    "fcm_id": n.fcm_id,
                    "is_read": n.is_read,
                    "created_at": n.created_at,
                    "delivered_at": n.delivered_at,
                })
            return Response({"success": True, "notifications": data})
        except Exception as e:
            return Response({"success": False, "error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class NotificationDeleteView(APIView):
    def post(self, request, notif_id: int):
        try:
            updated = NotificationLog.objects.filter(id=notif_id).update(is_deleted=True)
            if not updated:
                return Response({"success": False, "message": "Not found"}, status=status.HTTP_404_NOT_FOUND)
            return Response({"success": True, "message": "Notification deleted"})
        except Exception as e:
            return Response({"success": False, "error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class NotificationReadView(APIView):
    def post(self, request, notif_id: int):
        try:
            updated = NotificationLog.objects.filter(id=notif_id).update(is_read=True, delivered_at=timezone.now())
            if not updated:
                return Response({"success": False, "message": "Not found"}, status=status.HTTP_404_NOT_FOUND)
            return Response({"success": True, "message": "Marked as read"})
        except Exception as e:
            return Response({"success": False, "error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class NotificationClearAllView(APIView):
    def post(self, request, user_id: int):
        try:
            count = NotificationLog.objects.filter(user_id=user_id, is_deleted=False).update(is_deleted=True)
            return Response({"success": True, "deleted_count": int(count)})
        except Exception as e:
            return Response({"success": False, "error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class NotificationReadAllView(APIView):
    def post(self, request, user_id: int):
        try:
            count = NotificationLog.objects.filter(user_id=user_id, is_deleted=False, is_read=False).update(
                is_read=True,
                delivered_at=timezone.now()
            )
            return Response({"success": True, "marked_read_count": int(count)})
        except Exception as e:
            return Response({"success": False, "error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class TestPushNotificationView(APIView):
    def post(self, request):
        try:
            user_id = request.data.get('user_id')
            if not user_id:
                return Response({"success": False, "message": "user_id is required"}, status=status.HTTP_400_BAD_REQUEST)
            try:
                user_id_int = int(user_id)
            except (TypeError, ValueError):
                return Response({"success": False, "message": "user_id must be an integer"}, status=status.HTTP_400_BAD_REQUEST)

            title = request.data.get('title') or "Test Notification"
            body = request.data.get('body') or "Hello from Kirazee backend"
            data = request.data.get('data') or {}
            token_override = (
                request.data.get('token')
                or request.data.get('tokenID')
                or request.data.get('tokenId')
                or request.data.get('fcmToken')
                or request.data.get('deviceToken')
                or request.data.get('fcm_token')
                or request.data.get('device_token')
            )

            fcm_id = send_notification_test(user_id_int, title, body, data, token_override)
            return Response({"success": True, "fcm_id": fcm_id})
        except Exception as e:
            return Response({"success": False, "error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)



# ============================================================================
# NOTIFICATION MANAGEMENT SERVICES
# ============================================================================

class NotificationStatisticsView(APIView):
    """
    Get overall notification statistics for dashboard
    GET /api/notifications/statistics/
    """
    permission_classes = []  # Remove authentication requirement
    
    def get(self, request):
        try:
            from notifications.analytics_service import CampaignAnalyticsService
            
            statistics = CampaignAnalyticsService.get_overall_stats()
            
            return Response({
                "success": True,
                "statistics": statistics
            })
        except Exception as e:
            logger.error(f"Error getting notification statistics: {str(e)}")
            return Response({
                "success": False,
                "error": str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class CampaignListView(APIView):
    """
    List all notification campaigns
    GET /api/notifications/superadmin/campaigns/
    """
    permission_classes = []  # Remove authentication requirement
    
    def get(self, request):
        try:
            from notifications.models import SuperadminNotificationCampaign
            
            # Get query parameters
            page = int(request.query_params.get('page', 1))
            limit = min(int(request.query_params.get('limit', 20)), 100)
            offset = (page - 1) * limit
            
            status_filter = request.query_params.get('status')
            campaign_type_filter = request.query_params.get('campaign_type')
            
            # Build query
            queryset = SuperadminNotificationCampaign.objects.all()
            
            if status_filter:
                queryset = queryset.filter(status=status_filter)
            if campaign_type_filter:
                queryset = queryset.filter(campaign_type=campaign_type_filter)
            
            # Get total count
            total_count = queryset.count()
            
            # Get paginated results
            campaigns = queryset.order_by('-created_at')[offset:offset + limit]
            
            campaign_data = []
            for campaign in campaigns:
                campaign_data.append({
                    "id": campaign.id,
                    "campaign_name": campaign.campaign_name,
                    "campaign_type": campaign.campaign_type,
                    "title": campaign.title,
                    "message": campaign.message[:100] + "..." if len(campaign.message) > 100 else campaign.message,
                    "channels": campaign.channels,
                    "status": campaign.status,
                    "target_all_users": campaign.target_all_users,
                    "target_business_ids": campaign.target_business_ids,
                    "target_user_ids": campaign.target_user_ids,
                    "target_user_modes": campaign.target_user_modes,
                    "media_url": campaign.media_url,
                    "media_type": campaign.media_type,
                    "scheduled_at": campaign.scheduled_at,
                    "created_at": campaign.created_at,
                    "sent_at": campaign.sent_at,
                    "created_by": campaign.created_by,
                    "statistics": {
                        "total_recipients": campaign.total_recipients,
                        "firebase_sent": campaign.firebase_sent,
                        "email_sent": campaign.email_sent,
                        "whatsapp_sent": campaign.whatsapp_sent,
                        "firebase_failed": campaign.firebase_failed,
                        "email_failed": campaign.email_failed,
                        "whatsapp_failed": campaign.whatsapp_failed,
                        "total_sent": campaign.firebase_sent + campaign.email_sent + campaign.whatsapp_sent,
                        "total_failed": campaign.firebase_failed + campaign.email_failed + campaign.whatsapp_failed
                    }
                })
            
            return Response({
                "success": True,
                "campaigns": campaign_data,
                "pagination": {
                    "total_count": total_count,
                    "current_page": page,
                    "per_page": limit,
                    "total_pages": (total_count + limit - 1) // limit
                }
            })
        except Exception as e:
            logger.error(f"Error getting campaign list: {str(e)}")
            return Response({
                "success": False,
                "error": str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class CampaignCreateView(APIView):
    """
    Create new notification campaign
    POST /api/notifications/superadmin/campaigns/create/
    """
    permission_classes = []  # Remove authentication requirement
    
    def post(self, request):
        try:
            from notifications.models import SuperadminNotificationCampaign
            from notifications.campaign_service import CampaignExecutionService
            
            data = request.data
            
            # Validate required fields
            required_fields = ['campaign_name', 'campaign_type', 'title', 'message', 'created_by']
            for field in required_fields:
                if not data.get(field):
                    return Response({
                        "success": False,
                        "error": f"Field '{field}' is required"
                    }, status=status.HTTP_400_BAD_REQUEST)
            
            # Create campaign
            campaign = SuperadminNotificationCampaign.objects.create(
                campaign_name=data['campaign_name'],
                campaign_type=data['campaign_type'],
                title=data['title'],
                message=data['message'],
                channels=data.get('channels', 'all'),
                target_all_users=data.get('target_all_users', False),
                target_business_ids=data.get('target_business_ids', []),
                target_user_ids=data.get('target_user_ids', []),
                target_user_modes=data.get('target_user_modes', []),
                media_url=data.get('media_url'),
                media_type=data.get('media_type'),
                created_by=data['created_by'],
                template_data=data.get('template_data')
            )
            
            # Execute campaign immediately (send notifications)
            execution_result = CampaignExecutionService.execute_campaign(campaign.id)
            
            if execution_result['success']:
                return Response({
                    "success": True,
                    "message": "Campaign created and sent successfully",
                    "campaign_id": campaign.id,
                    "execution_result": execution_result
                })
            else:
                return Response({
                    "success": False,
                    "error": execution_result.get('error', 'Campaign execution failed'),
                    "campaign_id": campaign.id
                }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
            
        except Exception as e:
            logger.error(f"Error creating campaign: {str(e)}")
            return Response({
                "success": False,
                "error": str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class CampaignDetailView(APIView):
    """
    Get campaign details
    GET /api/notifications/superadmin/campaigns/{campaign_id}/
    """
    permission_classes = []  # Remove authentication requirement
    
    def get(self, request, campaign_id):
        try:
            from notifications.models import SuperadminNotificationCampaign
            from notifications.analytics_service import CampaignAnalyticsService
            
            campaign = SuperadminNotificationCampaign.objects.get(id=campaign_id)
            
            campaign_data = {
                "id": campaign.id,
                "campaign_name": campaign.campaign_name,
                "campaign_type": campaign.campaign_type,
                "title": campaign.title,
                "message": campaign.message,
                "channels": campaign.channels,
                "status": campaign.status,
                "target_all_users": campaign.target_all_users,
                "target_business_ids": campaign.target_business_ids,
                "target_user_ids": campaign.target_user_ids,
                "target_user_modes": campaign.target_user_modes,
                "media_url": campaign.media_url,
                "media_type": campaign.media_type,
                "scheduled_at": campaign.scheduled_at,
                "created_at": campaign.created_at,
                "sent_at": campaign.sent_at,
                "created_by": campaign.created_by,
                "template_data": campaign.template_data,
                "error_message": campaign.error_message
            }
            
            # Get detailed statistics
            stats = CampaignAnalyticsService.get_campaign_stats(campaign_id)
            if 'error' not in stats:
                campaign_data['statistics'] = stats['delivery_statistics']
            else:
                campaign_data['statistics'] = {
                    "total_recipients": campaign.total_recipients,
                    "firebase_sent": campaign.firebase_sent,
                    "email_sent": campaign.email_sent,
                    "whatsapp_sent": campaign.whatsapp_sent,
                    "firebase_failed": campaign.firebase_failed,
                    "email_failed": campaign.email_failed,
                    "whatsapp_failed": campaign.whatsapp_failed,
                    "total_sent": campaign.firebase_sent + campaign.email_sent + campaign.whatsapp_sent,
                    "total_failed": campaign.firebase_failed + campaign.email_failed + campaign.whatsapp_failed
                }
            
            return Response({
                "success": True,
                "campaign": campaign_data
            })
            
        except SuperadminNotificationCampaign.DoesNotExist:
            return Response({
                "success": False,
                "error": "Campaign not found"
            }, status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            logger.error(f"Error getting campaign details: {str(e)}")
            return Response({
                "success": False,
                "error": str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class UsersListView(APIView):
    """
    Get users for targeting
    GET /api/notifications/users/
    """
    permission_classes = []  # Remove authentication requirement
    
    def get(self, request):
        try:
            from notifications.targeting_service import TargetAudienceService
            
            # Get query parameters
            page = int(request.query_params.get('page', 1))
            per_page = min(int(request.query_params.get('per_page', 50)), 100)
            search = request.query_params.get('search', '')
            user_mode = request.query_params.get('user_mode', '')
            business_id = request.query_params.get('business_id', '')
            
            result = TargetAudienceService.search_users(
                search=search,
                user_mode=user_mode,
                business_id=business_id,
                page=page,
                per_page=per_page
            )
            
            return Response({
                "success": True,
                "users": result['users'],
                "pagination": result['pagination']
            })
            
        except Exception as e:
            logger.error(f"Error getting users list: {str(e)}")
            return Response({
                "success": False,
                "error": str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class BusinessesListView(APIView):
    """
    Get businesses for targeting
    GET /api/notifications/businesses/
    """
    permission_classes = []  # Remove authentication requirement
    
    def get(self, request):
        try:
            from notifications.targeting_service import TargetAudienceService
            
            search = request.query_params.get('search', '')
            businesses = TargetAudienceService.get_business_list(search=search)
            
            return Response({
                "success": True,
                "businesses": businesses
            })
            
        except Exception as e:
            logger.error(f"Error getting businesses list: {str(e)}")
            return Response({
                "success": False,
                "error": str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class UserModesListView(APIView):
    """
    Get user modes with counts
    GET /api/notifications/user-modes/
    """
    permission_classes = []  # Remove authentication requirement
    
    def get(self, request):
        try:
            from notifications.targeting_service import TargetAudienceService
            
            user_modes = TargetAudienceService.get_user_modes()
            
            return Response({
                "success": True,
                "user_modes": user_modes
            })
            
        except Exception as e:
            logger.error(f"Error getting user modes: {str(e)}")
            return Response({
                "success": False,
                "error": str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class MediaUploadView(APIView):
    """
    Upload media for campaigns
    POST /api/notifications/media/upload/
    """
    permission_classes = []  # Remove authentication requirement
    
    def post(self, request):
        try:
            import os
            from django.core.files.uploadedfile import InMemoryUploadedFile
            from django.utils import timezone
            import uuid
            
            if 'media_file' not in request.FILES:
                return Response({
                    "success": False,
                    "error": "No media file provided"
                }, status=status.HTTP_400_BAD_REQUEST)
            
            media_file = request.FILES['media_file']
            media_type = request.POST.get('media_type', 'image')
            
            # Validate file type
            allowed_types = {
                'image': ['image/jpeg', 'image/png', 'image/gif', 'image/webp'],
                'video': ['video/mp4', 'video/avi', 'video/mov'],
                'document': ['application/pdf', 'application/msword', 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'],
                'audio': ['audio/mpeg', 'audio/wav', 'audio/mp3']
            }
            
            file_mime_type = media_file.content_type
            valid_mime_types = []
            for type_group in allowed_types.values():
                valid_mime_types.extend(type_group)
            
            if file_mime_type not in valid_mime_types:
                return Response({
                    "success": False,
                    "error": f"File type {file_mime_type} not allowed"
                }, status=status.HTTP_400_BAD_REQUEST)
            
            # Generate unique filename
            file_extension = os.path.splitext(media_file.name)[1]
            unique_filename = f"{uuid.uuid4()}{file_extension}"
            
            # Create upload directory structure
            upload_dir = os.path.join('media', 'api', 'notifications', 'media', media_type, 
                                   timezone.now().strftime('%Y'), timezone.now().strftime('%m'), 
                                   timezone.now().strftime('%d'))
            
            # Ensure directory exists
            os.makedirs(upload_dir, exist_ok=True)
            
            # Save file
            file_path = os.path.join(upload_dir, unique_filename)
            with open(file_path, 'wb+') as destination:
                for chunk in media_file.chunks():
                    destination.write(chunk)
            
            # Generate URL
            media_url = f"http://localhost:8000/{file_path.replace(os.sep, '/')}"
            
            return Response({
                "success": True,
                "media_url": media_url,
                "media_type": media_type,
                "original_filename": media_file.name,
                "file_size": media_file.size,
                "mime_type": file_mime_type
            })
            
        except Exception as e:
            logger.error(f"Error uploading media: {str(e)}")
            return Response({
                "success": False,
                "error": str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
