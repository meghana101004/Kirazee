from django.db import models
from django.utils import timezone
from .storage import PrefixedMediaNameStorage
import os
import time
import uuid

def business_logo_path(instance, filename):
    ext = filename.split('.')[-1]
    timestamp = int(time.time())
    filename = f"{instance.business_id}_{timestamp}.{ext}"
    return os.path.join("media/business_logos", filename)

def business_banner_path(instance, filename):
    ext = filename.split('.')[-1]
    timestamp = int(time.time())
    filename = f"{instance.business_id}_{timestamp}.{ext}"
    return os.path.join("media/business_banners", filename)

def generate_user_id():
    """
    Generates a new unique user_id starting from 14771.
    It finds the latest user_id and increments it.
    """
    # Define the starting ID
    start_id = 14771
    
    # Find the last registration record by descending user_id
    try:
        last_registration = Registration.objects.order_by('-user_id').first()
        
        if last_registration and last_registration.user_id:
            # If a user exists, increment the last user_id
            new_id = last_registration.user_id + 1
            # Ensure the new ID is not smaller than the starting ID
            return max(new_id, start_id)
        else:
            # If no users exist, this is the first one
            return start_id
    except:
        # If there's any error (like table doesn't exist), use UUID as fallback
        return int(uuid.uuid4().int >> 64) & 0x7FFFFFFFFFFFFFFF

# ==============================================================================
# 1️⃣ User Management Tables - CORRECTED
# ==============================================================================

class Registration(models.Model):
    # Note: The 'id' primary key is automatically created by Django.
    user_id = models.BigIntegerField(unique=True, editable=False, default=generate_user_id)
    firstName = models.CharField(max_length=100)
    lastName = models.CharField(max_length=100)
    countryCode = models.CharField(max_length=10)
    mobileNumber = models.CharField(max_length=15,unique=True, db_column='mobileNumber')
    emailID = models.EmailField(max_length=255, unique=True)
    dob = models.DateField(null=True, blank=True)
    is_verified = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    user_mode = models.CharField(max_length=255, default='consumer')
    profileUrl = models.CharField(max_length=255, null=True, blank=True)
    tokenID = models.CharField(max_length=255, null=True, blank=True, db_column='tokenID')
    uuid = models.CharField(max_length=100, null=True, blank=True)
    os = models.CharField(max_length=50, null=True, blank=True)
    status = models.BooleanField(default=True)
    whichapp = models.CharField(max_length=50, default='Kirazee')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    # Company/B2B related fields
    user_type = models.CharField(
        max_length=20, 
        choices=[
            ('individual', 'Individual'),
            ('company_employee', 'Company Employee'),
            ('company_admin', 'Company Admin'),
        ],
        default='individual',
        db_index=True,
        help_text="Type of user: individual consumer or company employee"
    )
    company_id = models.BigIntegerField(
        null=True, 
        blank=True, 
        db_index=True,
        help_text="Reference to company registration if user is company employee"
    )
    employee_role = models.CharField(
        max_length=50, 
        null=True, 
        blank=True,
        choices=[
            ('admin', 'Company Admin'),
            ('purchaser', 'Purchaser'),
            ('manager', 'Manager'),
            ('employee', 'Employee'),
        ],
        help_text="Role within the company"
    )
    department = models.CharField(
        max_length=100, 
        null=True, 
        blank=True,
        help_text="Department within the company"
    )
    employee_id = models.CharField(
        max_length=50, 
        null=True, 
        blank=True,
        help_text="Employee ID within the company"
    )
    purchase_limit = models.DecimalField(
        max_digits=12, 
        decimal_places=2, 
        null=True, 
        blank=True,
        help_text="Maximum purchase amount per order for this employee"
    )
    reporting_manager = models.BigIntegerField(
        null=True, 
        blank=True,
        help_text="User ID of reporting manager for approval workflow"
    )
    can_approve_orders = models.BooleanField(
        default=False,
        help_text="Whether this employee can approve orders"
    )
    joined_company_at = models.DateTimeField(
        null=True, 
        blank=True,
        help_text="When this user joined the company"
    )

    class Meta:
        # This tells Django which table to use.
        db_table = 'registrations'
        indexes = [
            models.Index(fields=['user_type']),
            models.Index(fields=['company_id']),
        ]

    def __str__(self):
        return f"{self.firstName} {self.lastName} ({self.user_id})"

    @property
    def is_company_user(self):
        return self.user_type in ['company_employee', 'company_admin']

    @property
    def is_company_admin(self):
        return self.user_type == 'company_admin'

    @property
    def company(self):
        """Get company registration if user is company employee"""
        if self.company_id and self.is_company_user:
            from .models import CompanyRegistration
            try:
                return CompanyRegistration.objects.get(company_id=self.company_id)
            except CompanyRegistration.DoesNotExist:
                return None
        return None

    @property
    def can_place_company_orders(self):
        """Check if user can place company orders"""
        if not self.is_company_user:
            return False
        
        company = self.company
        return company and company.can_place_orders and self.is_active

    @property
    def display_name(self):
        """Get display name for company users"""
        if self.is_company_user:
            return f"{self.firstName} {self.lastName} - {self.company.company_name if self.company else 'N/A'}"
        return f"{self.firstName} {self.lastName}"


class Otp(models.Model):
    mobileNumber = models.ForeignKey(
        Registration,
        to_field='mobileNumber',
        on_delete=models.CASCADE,
        db_column='mobileNumber',
        related_name='otps'
    )
    emailID = models.CharField(max_length=255, null=True, blank=True)
    tokenID = models.CharField(max_length=255, null=True, blank=True)
    code = models.CharField(max_length=6)
    # status 0 = not verified, 1 = verified
    status = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'otps'


# ============================================================================== 
# 2️⃣ User Address Table
# ============================================================================== 

class UserAddress(models.Model):
    id = models.BigAutoField(primary_key=True)
    # Link to Registration via user_id numeric column
    user = models.ForeignKey(
        Registration,
        to_field='user_id',
        db_column='user_id',
        on_delete=models.CASCADE,
        related_name='addresses',
        null=True,  # Make nullable for company addresses
        blank=True
    )
    # Company ID for company addresses (null for user addresses)
    company_id = models.IntegerField(
        null=True, 
        blank=True, 
        db_index=True,
        help_text='Company ID if this is a company address'
    )
    address_type = models.CharField(max_length=10, null=True, blank=True)
    tag = models.CharField(max_length=50, null=True, blank=True)
    is_default = models.BooleanField(default=False)
    address = models.JSONField()
    status = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'user_address'
        indexes = [
            models.Index(fields=['company_id'], name='idx_user_address_company_id'),
            models.Index(fields=['user', 'company_id'], name='idx_user_address_user_company'),
        ]


# ============================================================================== 
# 3️⃣ Business Domain Tables
# ============================================================================== 

class BusinessType(models.Model):
    code = models.CharField(max_length=10, primary_key=True)
    type = models.CharField(max_length=100)
    categories = models.JSONField()
    status = models.BooleanField(default=True)
    title = models.CharField(max_length=200, null=True, blank=True)
    svg = models.TextField(null=True, blank=True)
    caption = models.TextField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    # new
    logo = models.ImageField(upload_to='business_types/logos/', null=True, blank=True)
    banner = models.ImageField(upload_to='business_types/banners/', null=True, blank=True)
    mobile_logo = models.CharField(max_length=255, null=True, blank=True)
    mobile_banner = models.CharField(max_length=255, null=True, blank=True)
    # This maps to the theme JSON column you added in the DB.
    theme = models.JSONField(null=True, blank=True)

    class Meta:
        db_table = 'business_types'
        managed = False


class BusinessFeature(models.Model):
    feature_id = models.CharField(max_length=10, primary_key=True)
    details = models.CharField(max_length=255)
    status = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'business_features'
        managed = False


class Business(models.Model):
    business_id = models.CharField(max_length=50, primary_key=True)
    level = models.CharField(max_length=50, default='Master Level', null=True, blank=True)
    master = models.CharField(max_length=50, null=True, blank=True)
    businessName = models.CharField(max_length=255)
    businessType = models.CharField(max_length=10)
    businessCategory = models.CharField(max_length=255)
    businessEmail = models.CharField(max_length=255, null=True, blank=True)
    businessNumber = models.CharField(max_length=15, null=True, blank=True)
    businessWhatsapp = models.CharField(max_length=15, null=True, blank=True)
    description = models.TextField(null=True, blank=True)
    logo = models.ImageField(upload_to=business_logo_path, storage=PrefixedMediaNameStorage(), max_length=255, null=True, blank=True)
    banner = models.ImageField(upload_to=business_banner_path, storage=PrefixedMediaNameStorage(), max_length=255, null=True, blank=True)
    business_licence = models.CharField(max_length=255, null=True, blank=True)
    business_features = models.JSONField(null=True, blank=True)
    business_hours = models.JSONField(null=True, blank=True)
    gst_num = models.CharField(max_length=50, null=True, blank=True)
    currency = models.CharField(max_length=10, default='INR')
    location = models.TextField(null=True, blank=True)  # Changed from CharField to TextField
    address = models.TextField(null=True, blank=True)
    landmark = models.CharField(max_length=255, null=True, blank=True)
    city = models.CharField(max_length=100, null=True, blank=True)
    state = models.CharField(max_length=100, null=True, blank=True)
    pincode = models.CharField(max_length=20, null=True, blank=True)
    contact_support = models.CharField(max_length=255, null=True, blank=True)
    contact_mobile = models.CharField(max_length=15, null=True, blank=True)
    website_url = models.CharField(max_length=255, null=True, blank=True)
    latitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    longitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    is_verified = models.BooleanField(default=False)
    is_visible = models.BooleanField(default=True)
    status = models.BooleanField(default=True)
    paymentstatus = models.BooleanField(default=False)
    latitude = models.FloatField(null=True, blank=True)
    longitude = models.FloatField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'businesses'
        managed = False

    def save(self, *args, **kwargs):
        # Only try to update lat/long if location is a dict/object with coordinates
        if isinstance(self.location, dict):
            try:
                self.longitude = self.location.get('longitude') or self.location.get('x')
                self.latitude = self.location.get('latitude') or self.location.get('y')
            except AttributeError:
                pass
        # Handle string location - don't try to extract coordinates
        elif isinstance(self.location, str):
            pass
        
        # Ensure DB stores prefixed media paths for logo and banner
        try:
            if getattr(self, 'logo', None):
                name = str(self.logo).replace('\\', '/').lstrip('/')
                if name and not name.startswith('media/'):
                    self.logo.name = f"media/{name}"
            if getattr(self, 'banner', None):
                name = str(self.banner).replace('\\', '/').lstrip('/')
                if name and not name.startswith('media/'):
                    self.banner.name = f"media/{name}"
        except Exception:
            pass
        
        super().save(*args, **kwargs)

class BusinessFinancial(models.Model):
    PAYMENT_GATEWAY_RAZORPAY = "razorpay"
    PAYMENT_GATEWAY_ICICI = "icici"

    id = models.BigAutoField(primary_key=True)
    business = models.OneToOneField(
        Business,
        to_field="business_id",
        db_column="business_id",
        on_delete=models.CASCADE,
        related_name="financial_config",
    )

    # DB-driven selection of which payment gateway this business uses
    payment_gateway = models.CharField(
        max_length=30,
        default=PAYMENT_GATEWAY_RAZORPAY,
    )

    # Generic, gateway-agnostic credentials blob (per business)
    gateway_credentials = models.JSONField(null=True, blank=True)

    owner_pan = models.CharField(max_length=20, null=True, blank=True)
    gstin = models.CharField(max_length=20, null=True, blank=True)
    ifsc_code = models.CharField(max_length=20, null=True, blank=True)
    account_number = models.CharField(max_length=50, null=True, blank=True)

    # Legacy Razorpay-specific columns (kept for backwards compatibility)
    razor_pay_key_id = models.CharField(max_length=100, null=True, blank=True)
    razor_pay_key_code = models.CharField(max_length=100, null=True, blank=True)
    razor_webhook_secret = models.CharField(max_length=255, null=True, blank=True)
    fssai_certification_number = models.CharField(max_length=50, null=True, blank=True)

    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "business_financials"
        verbose_name = "Business Financial"
        verbose_name_plural = "Business Financials"
        managed = True  # Changed from implicit False to explicit True

    def __str__(self):
        return f"Financials for {self.business.business_id}"

    # Backwards-compatible attribute names expected by payment code
    @property
    def razorpay_key_id(self):
        return self.razor_pay_key_id

    @razorpay_key_id.setter
    def razorpay_key_id(self, value):
        self.razor_pay_key_id = value

    @property
    def razorpay_key_secret(self):
        return self.razor_pay_key_code

    @razorpay_key_secret.setter
    def razorpay_key_secret(self, value):
        self.razor_pay_key_code = value

    @property
    def razorpay_webhook_secret(self):
        return self.razor_webhook_secret

    @razorpay_webhook_secret.setter
    def razorpay_webhook_secret(self, value):
        self.razor_webhook_secret = value

    def get_gateway_config(self):
        """Return (gateway, creds_dict) for this business's payment gateway.

        This is a low-level helper used by higher-level payment helpers that
        also apply master-business and global settings fallbacks.
        """
        gateway = (self.payment_gateway or self.PAYMENT_GATEWAY_RAZORPAY).lower()
        creds = self.gateway_credentials or {}
        return gateway, creds

    def save(self, *args, **kwargs):
        from django.db import connection
        print(f"Saving BusinessFinancial with business_id: {self.business.business_id}")
        print(f"Using database: {connection.settings_dict['NAME']}")
        super().save(*args, **kwargs)

class BusinessMapping(models.Model):
    id = models.BigAutoField(primary_key=True)
    # UNIQUE KEY on user_id -> model as OneToOne to Registration.user_id
    user = models.OneToOneField(
        'Registration',
        to_field='user_id',
        db_column='user_id',
        on_delete=models.CASCADE,
        related_name='business_mapping',
    )
    business = models.ForeignKey(
        'Business',
        to_field='business_id',
        db_column='business_id',
        on_delete=models.CASCADE,
        related_name='user_mappings',
    )
    status = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'business_mapping'
        managed = False


class BusinessOwnerDetails(models.Model):
    id = models.BigAutoField(primary_key=True)
    # FK references business_mapping(user_id), not its PK. Point to the OneToOne field 'user'.
    user = models.ForeignKey(
        'BusinessMapping',
        to_field='user',
        db_column='user_id',
        on_delete=models.CASCADE,
        related_name='owner_details',
    )
    pan = models.CharField(max_length=20, null=True, blank=True)
    aadhaar = models.CharField(max_length=20, null=True, blank=True)
    per_mobile_number = models.CharField(max_length=15, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'business_owner_details'
        managed = False


# ============================================================================== 
# 4️⃣ Navigation System Tables
# ============================================================================== 

class NavigationItem(models.Model):
    id = models.CharField(max_length=50, primary_key=True)
    label = models.CharField(max_length=100)
    icon_svg = models.TextField(null=True, blank=True)
    order = models.BigIntegerField(null=True, blank=True)
    is_visible = models.BooleanField(default=True)
    mode = models.CharField(max_length=50, null=True, blank=True)
    route_path = models.CharField(max_length=100, null=True, blank=True)
    parent = models.ForeignKey(
        'self',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        db_column='parent_id',
        related_name='children'
    )

    class Meta:
        db_table = 'NavigationItem'
        managed = False
        ordering = ['order', 'label']

    def __str__(self):
        return f"{self.label} ({self.mode})"


# ==============================================================================
# 6️⃣ Company Management Tables - B2B System
# ==============================================================================

class CompanyRegistration(models.Model):
    """Company registration for B2B orders"""
    company_id = models.BigAutoField(primary_key=True)
    company_name = models.CharField(max_length=255, db_index=True)
    gst_number = models.CharField(max_length=15, unique=True, db_index=True)
    business_type = models.CharField(max_length=50, help_text="Type of business: manufacturing, IT, retail, etc.")
    business_address = models.JSONField(help_text="Complete business address details")
    contact_person_name = models.CharField(max_length=255)
    contact_person_phone = models.CharField(max_length=15)
    contact_person_email = models.EmailField()
    alternative_contact_person_name = models.CharField(max_length=255, null=True, blank=True)
    alternative_contact_person_phone = models.CharField(max_length=15, null=True, blank=True)
    alternative_contact_person_email = models.EmailField(null=True, blank=True)
    
    # Verification fields
    verification_status = models.CharField(
        max_length=20, 
        choices=[
            ('pending', 'Pending'),
            ('email_verified', 'Email Verified'),
            ('mobile_verified', 'Mobile Verified'),
            ('document_verified', 'Document Verified'),
            ('approved', 'Approved'),
            ('rejected', 'Rejected'),
            ('suspended', 'Suspended')
        ],
        default='pending'
    )
    verification_documents = models.JSONField(
        null=True, 
        blank=True,
        help_text="Uploaded verification documents: GST certificate, business license, etc."
    )
    verification_remarks = models.TextField(null=True, blank=True, help_text="Admin remarks for verification")
    
    # Business details
    years_in_business = models.IntegerField(null=True, blank=True)
    annual_revenue = models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True)
    number_of_employees = models.IntegerField(null=True, blank=True)
    
    # System fields
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    approved_at = models.DateTimeField(null=True, blank=True)
    approved_by = models.ForeignKey('self', on_delete=models.SET_NULL, null=True, blank=True, related_name='approved_companies')
    
    class Meta:
        db_table = 'company_registrations'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['verification_status']),
            models.Index(fields=['gst_number']),
            models.Index(fields=['company_name']),
        ]

    def __str__(self):
        return f"{self.company_name} ({self.gst_number})"

    @property
    def is_verified(self):
        return self.verification_status in ['approved']

    @property
    def can_place_orders(self):
        return self.verification_status == 'approved' and self.is_active


class CompanyOffers(models.Model):
    """Special offers for companies"""
    OFFER_TYPES = [
        ('percentage_discount', 'Percentage Discount'),
        ('fixed_amount', 'Fixed Amount Discount'),
        ('free_shipping', 'Free Shipping'),
        ('bulk_pricing', 'Bulk Pricing'),
        ('cashback', 'Cashback'),
    ]
    
    offer_id = models.BigAutoField(primary_key=True)
    company_id = models.BigIntegerField(db_index=True)
    offer_name = models.CharField(max_length=255)
    offer_type = models.CharField(max_length=50, choices=OFFER_TYPES)
    offer_value = models.DecimalField(max_digits=10, decimal_places=2, help_text="Discount value or percentage")
    
    # Offer conditions
    min_order_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    min_order_quantity = models.IntegerField(default=1)
    max_discount_amount = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    
    # Applicability
    applicable_business_types = models.JSONField(
        null=True, 
        blank=True,
        help_text="Business types this offer applies to: ['R01', 'R02', 'R08']"
    )
    applicable_categories = models.JSONField(
        null=True, 
        blank=True,
        help_text="Product categories this offer applies to"
    )
    applicable_products = models.JSONField(
        null=True, 
        blank=True,
        help_text="Specific product IDs this offer applies to"
    )
    
    # Validity
    valid_from = models.DateTimeField()
    valid_until = models.DateTimeField()
    usage_limit = models.IntegerField(null=True, blank=True, help_text="Maximum times this offer can be used")
    usage_count = models.IntegerField(default=0, help_text="Times this offer has been used")
    
    # System fields
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey('Registration', on_delete=models.SET_NULL, null=True, blank=True)
    
    class Meta:
        db_table = 'company_offers'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['company_id', 'is_active']),
            models.Index(fields=['valid_from', 'valid_until']),
            models.Index(fields=['offer_type']),
        ]

    def __str__(self):
        return f"{self.offer_name} - {self.company_id}"

    @property
    def is_valid(self):
        from django.utils import timezone
        now = timezone.now()
        return (
            self.is_active and 
            self.valid_from <= now <= self.valid_until and
            (self.usage_limit is None or self.usage_count < self.usage_limit)
        )

    def calculate_discount(self, order_amount):
        """Calculate discount amount based on offer type"""
        if not self.is_valid or order_amount < self.min_order_amount:
            return 0
        
        if self.offer_type == 'percentage_discount':
            discount = order_amount * (self.offer_value / 100)
            if self.max_discount_amount:
                discount = min(discount, self.max_discount_amount)
            return discount
        elif self.offer_type == 'fixed_amount':
            return min(self.offer_value, order_amount)
        else:
            return 0

    def use_offer(self):
        """Increment usage count"""
        self.usage_count += 1
        self.save(update_fields=['usage_count'])
