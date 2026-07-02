from django.db import models
from django.utils import timezone
from kirazee_app.models import Business, Registration
import json

# Create your models here.

class DashboardSnapshot(models.Model):
    """
    Pre-calculated dashboard metrics for performance optimization
    Updated every 5 minutes via cron job
    """
    id = models.AutoField(primary_key=True)
    
    # Revenue Metrics
    total_revenue = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    total_gmv = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    average_order_value = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    
    # Order Metrics
    total_orders = models.IntegerField(default=0)
    online_orders = models.IntegerField(default=0)
    counter_orders = models.IntegerField(default=0)
    active_orders = models.IntegerField(default=0)  # Orders being prepared or out for delivery
    pending_orders = models.IntegerField(default=0)  # Orders placed but not started
    completed_orders = models.IntegerField(default=0)
    cancelled_orders = models.IntegerField(default=0)
    
    # Business Metrics
    active_businesses = models.IntegerField(default=0)
    total_businesses = models.IntegerField(default=0)
    paid_businesses = models.IntegerField(default=0)
    
    # Customer Metrics
    unique_customers = models.IntegerField(default=0)
    total_users = models.IntegerField(default=0)
    active_users = models.IntegerField(default=0)
    
    # Delivery Metrics
    active_delivery_partners = models.IntegerField(default=0)
    available_drivers = models.IntegerField(default=0)
    busy_drivers = models.IntegerField(default=0)
    
    # Performance Metrics
    completion_rate = models.DecimalField(max_digits=5, decimal_places=2, default=0)  # Percentage
    cancellation_rate = models.DecimalField(max_digits=5, decimal_places=2, default=0)  # Percentage
    
    # Timestamps
    created_at = models.DateTimeField(default=timezone.now)
    
    class Meta:
        db_table = "dashboard_snapshots"
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['-created_at'], name='ds_created_at_idx'),
        ]
    
    def __str__(self):
        return f"Dashboard Snapshot - {self.created_at.strftime('%Y-%m-%d %H:%M:%S')}"
    
    @property
    def total_revenue_formatted(self):
        """Format total revenue with K/M suffix"""
        if self.total_revenue >= 1000000:
            return f"{self.total_revenue/1000000:.1f}M"
        elif self.total_revenue >= 1000:
            return f"{self.total_revenue/1000:.1f}K"
        else:
            return str(self.total_revenue)
    
    @property
    def snapshot_age_minutes(self):
        """Return how old this snapshot is in minutes"""
        return int((timezone.now() - self.created_at).total_seconds() / 60)


# ===== COMPREHENSIVE BUSINESS DETAILS MODELS =====

class BusinessProfile(models.Model):
    """
    Extended business profile for Swiggy-style admin panel
    """
    business = models.OneToOneField(Business, on_delete=models.CASCADE, primary_key=True)
    
    # Outlet Information
    outlet_code = models.CharField(max_length=20, unique=True, null=True, blank=True)
    outlet_name = models.CharField(max_length=255, null=True, blank=True)
    
    # Business Classification
    business_category_detailed = models.CharField(max_length=100, null=True, blank=True)  # Biryani, Pizza, Cafe
    business_type_detailed = models.CharField(max_length=50, null=True, blank=True)  # Cloud kitchen, Dine-in, Multi-brand
    kitchen_type = models.CharField(max_length=50, null=True, blank=True)  # Central, Satellite, Dark
    
    # Status Management
    operational_status = models.CharField(max_length=20, default='active', choices=[
        ('active', 'Active'),
        ('inactive', 'Inactive'), 
        ('temp_closed', 'Temporarily Closed'),
        ('blocked', 'Account Blocked'),
        ('under_review', 'Under Review')
    ])
    closure_reason = models.CharField(max_length=255, null=True, blank=True)
    closure_notes = models.TextField(null=True, blank=True)
    
    # Performance Metrics
    hygiene_rating = models.DecimalField(max_digits=3, decimal_places=2, null=True, blank=True)
    quality_score = models.DecimalField(max_digits=3, decimal_places=2, null=True, blank=True)
    reliability_score = models.DecimalField(max_digits=3, decimal_places=2, null=True, blank=True)
    
    # Capacity & Operations
    max_orders_per_hour = models.IntegerField(default=50)
    avg_prep_time_minutes = models.IntegerField(default=20)
    kitchen_capacity = models.IntegerField(null=True, blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = "business_profiles"
        indexes = [
            models.Index(fields=['operational_status']),
            models.Index(fields=['business_category_detailed']),
            models.Index(fields=['hygiene_rating']),
        ]


class BusinessCompliance(models.Model):
    """
    Business compliance and licensing information
    """
    business = models.OneToOneField(Business, on_delete=models.CASCADE, primary_key=True)
    
    # FSSAI Details
    fssai_number = models.CharField(max_length=50, null=True, blank=True)
    fssai_expiry = models.DateField(null=True, blank=True)
    fssai_status = models.CharField(max_length=20, default='pending', choices=[
        ('pending', 'Pending'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
        ('expired', 'Expired')
    ])
    fssai_document = models.CharField(max_length=500, null=True, blank=True)
    
    # GST Details
    gst_number = models.CharField(max_length=50, null=True, blank=True)
    gst_status = models.CharField(max_length=20, default='pending', choices=[
        ('pending', 'Pending'),
        ('verified', 'Verified'),
        ('invalid', 'Invalid')
    ])
    
    # Business License
    license_number = models.CharField(max_length=100, null=True, blank=True)
    license_expiry = models.DateField(null=True, blank=True)
    license_document = models.CharField(max_length=500, null=True, blank=True)
    
    # Audit & Verification
    last_audit_date = models.DateField(null=True, blank=True)
    audit_score = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    next_audit_due = models.DateField(null=True, blank=True)
    
    # Mandatory Photos
    kitchen_photo = models.CharField(max_length=500, null=True, blank=True)
    hygiene_photos = models.JSONField(null=True, blank=True)  # Array of photo URLs
    safety_photos = models.JSONField(null=True, blank=True)  # Fire safety, etc.
    
    # Verification Timeline
    submitted_at = models.DateTimeField(null=True, blank=True)
    verified_at = models.DateTimeField(null=True, blank=True)
    verified_by = models.CharField(max_length=100, null=True, blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = "business_compliance"


class BusinessAlert(models.Model):
    """
    System alerts and flags for businesses
    """
    business = models.ForeignKey(Business, on_delete=models.CASCADE)
    
    # Alert Details
    alert_type = models.CharField(max_length=50, choices=[
        ('low_orders', 'Low Order Volume'),
        ('high_cancellation', 'High Cancellation Rate'),
        ('license_expiry', 'License Expiring Soon'),
        ('gst_mismatch', 'GST Mismatch'),
        ('rating_drop', 'Rating Drop'),
        ('payment_issues', 'Payment Issues'),
        ('compliance', 'Compliance Issue'),
        ('quality', 'Quality Concern'),
        ('delay', 'High Order Delays'),
        ('menu_violations', 'Menu Violations'),
        ('fraud_suspicion', 'Fraud Suspicion'),
    ])
    
    severity = models.CharField(max_length=20, choices=[
        ('low', 'Low'),
        ('medium', 'Medium'), 
        ('high', 'High'),
        ('critical', 'Critical')
    ])
    
    title = models.CharField(max_length=255)
    message = models.TextField()
    
    # Status & Resolution
    is_active = models.BooleanField(default=True)
    is_resolved = models.BooleanField(default=False)
    resolved_at = models.DateTimeField(null=True, blank=True)
    resolved_by = models.CharField(max_length=100, null=True, blank=True)
    resolution_notes = models.TextField(null=True, blank=True)
    
    # Metadata
    alert_data = models.JSONField(null=True, blank=True)  # Additional data for the alert
    auto_generated = models.BooleanField(default=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = "business_alerts"
        indexes = [
            models.Index(fields=['business', 'is_active']),
            models.Index(fields=['alert_type', 'severity']),
            models.Index(fields=['created_at']),
        ]


class BusinessPerformanceMetrics(models.Model):
    """
    Daily performance metrics for businesses
    """
    business = models.ForeignKey(Business, on_delete=models.CASCADE)
    date = models.DateField()
    
    # Order Metrics
    total_orders = models.IntegerField(default=0)
    completed_orders = models.IntegerField(default=0)
    cancelled_orders = models.IntegerField(default=0)
    completion_rate = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    cancellation_rate = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    
    # Revenue Metrics
    gross_revenue = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    net_revenue = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    commission_earned = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    average_order_value = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    
    # Time Metrics
    avg_prep_time = models.IntegerField(default=0)  # minutes
    avg_delivery_time = models.IntegerField(default=0)  # minutes
    total_delay_minutes = models.IntegerField(default=0)
    
    # Customer Metrics
    unique_customers = models.IntegerField(default=0)
    repeat_customers = models.IntegerField(default=0)
    repeat_percentage = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    
    # Quality Metrics
    customer_rating = models.DecimalField(max_digits=3, decimal_places=2, null=True, blank=True)
    total_ratings = models.IntegerField(default=0)
    complaints_count = models.IntegerField(default=0)
    
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = "business_performance_metrics"
        unique_together = ['business', 'date']
        indexes = [
            models.Index(fields=['business', 'date']),
            models.Index(fields=['date']),
        ]


class BusinessContactUs(models.Model):
    """
    Model to store contact us form submissions for specific businesses
    Uses the existing contact_us table with additional business_id field
    Emails are sent to the respective business owners
    """
    id = models.AutoField(primary_key=True)
    business = models.ForeignKey(Business, on_delete=models.CASCADE, related_name='contact_messages', db_column='business_id')
    
    # Contact person details
    firstName = models.CharField(max_length=100, db_column='firstName')
    lastName = models.CharField(max_length=100, db_column='lastName')
    emailID = models.EmailField(max_length=255, db_column='emailID')
    phoneNumber = models.CharField(max_length=20, db_column='phoneNumber')
    
    # Message details
    subject = models.CharField(max_length=200, db_column='subject')
    message = models.TextField(db_column='message')
    
    # Status tracking
    created_at = models.DateTimeField(default=timezone.now, db_column='created_at')
    is_resolved = models.BooleanField(default=False, db_column='is_resolved')
    business_notes = models.TextField(blank=True, null=True, db_column='admin_notes')  # Using existing admin_notes column
    
    # Email tracking
    email_sent_at = models.DateTimeField(null=True, blank=True)
    email_sent_status = models.CharField(max_length=20, default='pending', choices=[
        ('pending', 'Pending'),
        ('sent', 'Sent'),
        ('failed', 'Failed'),
        ('bounced', 'Bounced')
    ])
    receiver = models.EmailField(max_length=255, null=True, blank=True, db_column='receiver', help_text="Email address where the notification was sent")
    
    class Meta:
        db_table = "contact_us"
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['business', '-created_at']),
            models.Index(fields=['is_resolved']),
            models.Index(fields=['email_sent_status']),
        ]
    
    def __str__(self):
        return f"{self.business.businessName} - {self.firstName} {self.lastName} - {self.subject}"
    
    @property
    def full_name(self):
        return f"{self.firstName} {self.lastName}"
    
    @property
    def business_email(self):
        """Get the business owner's email from the business table"""
        return self.business.businessEmail


class BusinessOwnerDetails(models.Model):
    """
    Extended owner details for businesses
    """
    business = models.OneToOneField(Business, on_delete=models.CASCADE, primary_key=True)
    
    # Owner Information
    owner_name = models.CharField(max_length=255)
    owner_email = models.EmailField(null=True, blank=True)
    owner_phone = models.CharField(max_length=20, null=True, blank=True)
    owner_alternate_phone = models.CharField(max_length=20, null=True, blank=True)
    
    # KYC Details
    pan_number = models.CharField(max_length=20, null=True, blank=True)
    pan_status = models.CharField(max_length=20, default='pending', choices=[
        ('pending', 'Pending'),
        ('verified', 'Verified'),
        ('rejected', 'Rejected')
    ])
    pan_document = models.CharField(max_length=500, null=True, blank=True)
    
    # Bank Details
    bank_name = models.CharField(max_length=255, null=True, blank=True)
    account_number = models.CharField(max_length=50, null=True, blank=True)
    ifsc_code = models.CharField(max_length=20, null=True, blank=True)
    account_holder_name = models.CharField(max_length=255, null=True, blank=True)
    bank_status = models.CharField(max_length=20, default='pending', choices=[
        ('pending', 'Pending'),
        ('verified', 'Verified'),
        ('rejected', 'Rejected')
    ])
    
    # Verification Status
    kyc_status = models.CharField(max_length=20, default='pending', choices=[
        ('pending', 'Pending'),
        ('verified', 'Verified'),
        ('rejected', 'Rejected'),
        ('incomplete', 'Incomplete')
    ])
    kyc_completed_at = models.DateTimeField(null=True, blank=True)
    kyc_verified_by = models.CharField(max_length=100, null=True, blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = "business_owner_details_extended"


class SupportTicket(models.Model):
    """
    Support ticket system for customer service tracking
    Separate from main business data - isolated support system
    """
    PRIORITY_CHOICES = [
        ('low', 'Low'),
        ('medium', 'Medium'),
        ('high', 'High'),
        ('urgent', 'Urgent')
    ]
    
    STATUS_CHOICES = [
        ('open', 'Open'),
        ('in_progress', 'In Progress'),
        ('resolved', 'Resolved'),
        ('closed', 'Closed')
    ]
    
    CATEGORY_CHOICES = [
        ('order_issue', 'Order Issue'),
        ('payment_issue', 'Payment Issue'),
        ('delivery_issue', 'Delivery Issue'),
        ('account_issue', 'Account Issue'),
        ('technical_issue', 'Technical Issue'),
        ('general_inquiry', 'General Inquiry')
    ]
    
    # Ticket Information
    ticket_id = models.CharField(max_length=20, unique=True, primary_key=True)
    customer_name = models.CharField(max_length=100)
    customer_email = models.EmailField()
    customer_phone = models.CharField(max_length=20, null=True, blank=True)
    
    # Ticket Details
    subject = models.CharField(max_length=200)
    description = models.TextField()
    category = models.CharField(max_length=20, choices=CATEGORY_CHOICES)
    priority = models.CharField(max_length=10, choices=PRIORITY_CHOICES, default='medium')
    status = models.CharField(max_length=15, choices=STATUS_CHOICES, default='open')
    
    # Resolution Information
    assigned_agent = models.CharField(max_length=100, null=True, blank=True)
    resolution_notes = models.TextField(null=True, blank=True)
    resolution_time_minutes = models.IntegerField(null=True, blank=True)
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    resolved_at = models.DateTimeField(null=True, blank=True)
    
    # Additional Fields
    order_id = models.CharField(max_length=50, null=True, blank=True)
    business_name = models.CharField(max_length=100, null=True, blank=True)
    customer_rating = models.IntegerField(null=True, blank=True)  # 1-5 rating after resolution
    
    class Meta:
        db_table = "support_tickets"
        ordering = ['-created_at']
