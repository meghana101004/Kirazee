from django.db import models
from django.utils import timezone


class NotificationLog(models.Model):
    user_id = models.BigIntegerField()
    title = models.CharField(max_length=255)
    body = models.TextField(null=True, blank=True)
    data = models.JSONField(null=True, blank=True)
    status = models.CharField(max_length=20, default='sent')
    fcm_id = models.CharField(max_length=255, null=True, blank=True)
    error = models.TextField(null=True, blank=True)
    is_read = models.BooleanField(default=False)
    is_deleted = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    delivered_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = 'notifications_log'
        ordering = ['-created_at']
        managed = False  # Table already exists in DB


class BusinessMapping(models.Model):
    id = models.BigAutoField(primary_key=True)
    user_id = models.BigIntegerField(unique=True)
    business_id = models.CharField(max_length=50)
    status = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'business_mapping'
        indexes = [
            models.Index(fields=['business_id'], name='fk_bm_business'),
        ]


class SuperadminNotificationCampaign(models.Model):
    CAMPAIGN_TYPES = [
        ('system_update', 'System Update'),
        ('business_offer', 'Business Offer'),
        ('user_targeted', 'User Targeted'),
        ('general', 'General Announcement'),
    ]
    
    CHANNEL_CHOICES = [
        ('all', 'All Channels'),
        ('firebase', 'App Notifications Only'),
        ('email', 'Email Only'),
        ('whatsapp', 'WhatsApp Only'),
    ]
    
    STATUS_CHOICES = [
        ('draft', 'Draft'),
        ('scheduled', 'Scheduled'),
        ('processing', 'Processing'),
        ('sent', 'Sent'),
        ('failed', 'Failed'),
        ('cancelled', 'Cancelled'),
    ]

    id = models.AutoField(primary_key=True)
    campaign_name = models.CharField(max_length=255)
    campaign_type = models.CharField(max_length=20, choices=CAMPAIGN_TYPES)
    title = models.CharField(max_length=255)
    message = models.TextField()
    channels = models.CharField(max_length=20, choices=CHANNEL_CHOICES, default='all')
    target_all_users = models.BooleanField(default=False)
    target_business_ids = models.JSONField(null=True, blank=True)
    target_user_ids = models.JSONField(null=True, blank=True)
    target_user_modes = models.JSONField(null=True, blank=True)
    media_url = models.URLField(max_length=2048, null=True, blank=True)
    media_type = models.CharField(max_length=20, null=True, blank=True)
    scheduled_at = models.DateTimeField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='draft')
    created_by = models.BigIntegerField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    sent_at = models.DateTimeField(null=True, blank=True)
    
    # Statistics fields
    total_recipients = models.IntegerField(default=0)
    firebase_sent = models.IntegerField(default=0)
    email_sent = models.IntegerField(default=0)
    whatsapp_sent = models.IntegerField(default=0)
    firebase_failed = models.IntegerField(default=0)
    email_failed = models.IntegerField(default=0)
    whatsapp_failed = models.IntegerField(default=0)
    
    # Additional fields
    template_data = models.JSONField(null=True, blank=True)
    error_message = models.TextField(null=True, blank=True)

    class Meta:
        db_table = 'superadmin_notification_campaigns'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['status']),
            models.Index(fields=['campaign_type']),
            models.Index(fields=['created_at']),
            models.Index(fields=['created_by']),
            models.Index(fields=['scheduled_at']),
        ]
