from django.urls import path
from .views import (
    NotificationListView,
    DeliveryNotificationListView,
    NotificationDeleteView,
    NotificationReadView,
    TestPushNotificationView,
    NotificationClearAllView,
    NotificationReadAllView,
    NotificationStatisticsView,
    CampaignListView,
    CampaignCreateView,
    CampaignDetailView, 
    UsersListView,
    BusinessesListView,
    UserModesListView,
    MediaUploadView,
)
from .analytics_views import (
    campaign_detailed_stats,
    campaign_recipients,
    retry_failed_notifications,
    campaign_performance_overview,
    export_campaign_data,
)

urlpatterns = [
    path('list/<int:user_id>/', NotificationListView.as_view(), name='notifications-list'),
    path('list/delivery/<int:user_id>/', DeliveryNotificationListView.as_view(), name='notifications-delivery-list'),
    path('delete/<int:notif_id>/', NotificationDeleteView.as_view(), name='notifications-delete'),
    path('read/<int:notif_id>/', NotificationReadView.as_view(), name='notifications-read'),
    path('test-push/', TestPushNotificationView.as_view(), name='notifications-test-push'),
    path('clear-all/<int:user_id>/', NotificationClearAllView.as_view(), name='notifications-clear-all'),
    path('read-all/<int:user_id>/', NotificationReadAllView.as_view(), name='notifications-read-all'),

    # Notification Management - matching frontend URLs
    path('statistics/', NotificationStatisticsView.as_view(), name='notification_statistics'),
    path('superadmin/campaigns/', CampaignListView.as_view(), name='campaign_list'),
    path('superadmin/campaigns/create/', CampaignCreateView.as_view(), name='campaign_create'),
    path('superadmin/campaigns/<int:campaign_id>/', CampaignDetailView.as_view(), name='campaign_detail'),
    path('users/', UsersListView.as_view(), name='notification_users'),
    path('businesses/', BusinessesListView.as_view(), name='notification_businesses'),
    path('user-modes/', UserModesListView.as_view(), name='notification_user_modes'),
    path('media/upload/', MediaUploadView.as_view(), name='notification_media_upload'),

    # Campaign Analytics Endpoints
    path('campaigns/<int:campaign_id>/detailed-stats/', campaign_detailed_stats, name='campaign_detailed_stats'),
    path('campaigns/<int:campaign_id>/recipients/', campaign_recipients, name='campaign_recipients'),
    path('campaigns/<int:campaign_id>/retry/', retry_failed_notifications, name='campaign_retry'),
    path('campaigns/<int:campaign_id>/performance/', campaign_performance_overview, name='campaign_performance'),
    path('campaigns/<int:campaign_id>/export/', export_campaign_data, name='campaign_export'),
]
