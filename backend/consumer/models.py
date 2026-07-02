from django.db import models, transaction
from django.utils import timezone
from django.conf import settings
from datetime import datetime, timedelta
from django_fsm import FSMField, transition  # Temporary revert
from decimal import Decimal
import uuid
import json
from kirazee_app.models import Business, Registration, BusinessFeature, BusinessType, BusinessMapping, BusinessOwnerDetails, UserAddress
from business.models import MenuItems, productItems, BOM, BillOfMaterialsLog, BusinessPayment

class MenuCart(models.Model):
    id = models.PositiveBigIntegerField(primary_key=True)
    user_id = models.BigIntegerField()
    menu_id = models.BigIntegerField()
    quantity = models.PositiveIntegerField()
    customizations = models.JSONField(default=list, null=True, blank=True)
    added_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    business_id = models.CharField(max_length=50, null=True, blank=True)  

    class Meta:
        db_table = "menuCart"

    def save(self, *args, **kwargs):
        if not self.id:
            last_item = MenuCart.objects.order_by('-id').first()
            if last_item:
                self.id = last_item.id + 1
            else:
                self.id = 1101
        super().save(*args, **kwargs)

    def __str__(self):
        return str(self.id)

class GroceryCart(models.Model):
    id = models.BigAutoField(primary_key=True)
    user_id = models.BigIntegerField()
    item_id = models.BigIntegerField()
    quantity = models.PositiveIntegerField()
    added_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    business_id = models.CharField(max_length=45, null=True, blank=True)

    class Meta:
        db_table = "GroceryCart"

    def save(self, *args, **kwargs):
        if not self.id:
            last_item = GroceryCart.objects.order_by('-id').first()
            if last_item:
                self.id = last_item.id + 1
            else:
                self.id = 1101
        super().save(*args, **kwargs)

    def __str__(self):
        return f"GroceryCart {self.id} - User {self.user_id}"

class Orders(models.Model):
    class OrderStatus(models.TextChoices):
        PENDING = 'pending', 'Pending'
        CONFIRMED = 'confirmed', 'Confirmed'
        NOTIFIED = 'notified', 'Notified'
        PREPARING = 'preparing', 'Preparing'
        READY = 'ready', 'Ready'
        DISPATCHED = 'dispatched', 'Dispatched'
        OUT_FOR_DELIVERY = 'out_for_delivery', 'Out for Delivery'
        DELIVERED = 'delivered', 'Delivered'
        CANCELLED = 'cancelled', 'Cancelled'
        TRAVELLING = 'travelling', 'Travelling'
    
    class OrderType(models.TextChoices):
        DELIVERY = 'delivery', 'Delivery'
        PICKUP = 'pickup', 'Pickup'
        DINE_IN = 'dine_in', 'Dine In'
        TAKEAWAY = 'takeaway', 'Takeaway'
    
    order_id = models.BigAutoField(primary_key=True)
    token_num = models.IntegerField(null=True, blank=True)
    order_number = models.UUIDField(default=uuid.uuid4, editable=False, unique=True, db_index=True)
    user_id = models.ForeignKey('kirazee_app.Registration', on_delete=models.SET_NULL, null=True, blank=True, to_field='user_id', db_column='user_id')
    business_id = models.ForeignKey('kirazee_app.Business', on_delete=models.CASCADE, to_field='business_id', db_column='business_id')
    order_type = models.CharField(max_length=20, choices=OrderType.choices, default=OrderType.DELIVERY)
    status = FSMField(default=OrderStatus.PENDING, choices=OrderStatus.choices)
    
    # Financial fields
    total_amount = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'))
    discount_amount = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'))
    delivery_charges = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'))
    parcel_charges = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'))
    final_amount = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'))
    
    # Add this field if it doesn't exist.
    delivery_partner = models.ForeignKey(
        'delivery.DeliveryPartner',  # Adjust the app name if different
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='assigned_orders'
    )
    # Address fields with Historical Immutability
    delivery_address_snapshot = models.JSONField(null=True, blank=True, help_text="Snapshot of delivery address at order time")
    billing_address_snapshot = models.JSONField(null=True, blank=True, help_text="Snapshot of billing address at order time")
    delivery_address = models.ForeignKey('kirazee_app.UserAddress', on_delete=models.SET_NULL, null=True, blank=True, related_name='delivery_orders', db_column='delivery_address_id')
    
    # Coupon and wallet fields
    coupon_code = models.CharField(max_length=50, null=True, blank=True)
    wallet_points_used = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'))
  
  
    # Instruction fields
    delivery_instruction = models.JSONField(null=True, blank=True, help_text="Delivery instructions with emoji support")
    order_instruction = models.JSONField(null=True, blank=True, help_text="Order instructions with emoji support")
    
    # Timing fields
    estimated_delivery_time = models.DateTimeField(null=True, blank=True)
    actual_delivery_time = models.DateTimeField(null=True, blank=True)
    scheduled_time = models.DateTimeField(null=True, blank=True)
    
    # Company/B2B related fields
    order_customer_type = models.CharField(
        max_length=20, 
        choices=[
            ('individual', 'Individual'),
            ('company', 'Company'),
        ],
        default='individual',
        db_index=True,
        help_text="Type of customer: individual consumer or company"
    )
    company_id = models.BigIntegerField(
        null=True, 
        blank=True, 
        db_index=True,
        help_text="Reference to company registration if this is a company order"
    )
    ordered_by_employee = models.BigIntegerField(
        null=True, 
        blank=True,
        help_text="User ID of employee who placed this company order"
    )
    company_purchase_order = models.CharField(
        max_length=100, 
        null=True, 
        blank=True,
        help_text="Company's internal purchase order number"
    )
    is_bulk_order = models.BooleanField(
        default=False,
        help_text="Whether this is a bulk order (typically > 100 units)"
    )
    bulk_order_reference = models.CharField(
        max_length=100, 
        null=True, 
        blank=True,
        help_text="Reference number for bulk order tracking"
    )
    company_department = models.CharField(
        max_length=100, 
        null=True, 
        blank=True,
        help_text="Department within company that placed this order"
    )
    approval_status = models.CharField(
        max_length=20,
        choices=[
            ('auto_approved', 'Auto Approved'),
            ('pending_approval', 'Pending Approval'),
            ('manager_approved', 'Manager Approved'),
            ('admin_approved', 'Admin Approved'),
            ('rejected', 'Rejected'),
        ],
        default='auto_approved',
        help_text="Approval status for company orders"
    )
    approved_by = models.BigIntegerField(
        null=True, 
        blank=True,
        help_text="User ID of manager/admin who approved this order"
    )
    approved_at = models.DateTimeField(
        null=True, 
        blank=True,
        help_text="When this order was approved"
    )
    company_notes = models.TextField(
        null=True, 
        blank=True,
        help_text="Internal notes from company about this order"
    )
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'orders'
        ordering = ['-created_at']
        # Note: No unique constraint on token_num since it resets daily
        # Uniqueness is enforced by query logic (date filtering + select_for_update)
    
    def save(self, *args, **kwargs):
        if not self.order_id:
            last_order = Orders.objects.order_by('-order_id').first()
            if last_order:
                self.order_id = last_order.order_id + 1
            else:
                self.order_id = 1001
        super().save(*args, **kwargs)
    
    def _create_address_snapshot(self, address):
        """Create JSON snapshot of address for historical immutability"""
        if not address:
            return None
            
        try:
            # Get address data from JSON field
            address_data = address.address
            
            return {
                'state': address_data.get('state'),
                'street': address_data.get('street'),
                'door_no': address_data.get('Door no'),
                'country': address_data.get('country'),
                'pincode': address_data.get('pincode'),
                'city': address_data.get('city/town'),
                'latitude': address_data.get('latitude'),
                'longitude': address_data.get('longitude'),
                'address_type': address.address_type,
                'snapshot_created_at': (timezone.now() if getattr(settings, 'USE_TZ', False) else datetime.now()).isoformat()
            }
        except Exception:
            return None
    
    # Company/B2B related properties and methods
    @property
    def is_company_order(self):
        """Check if this is a company order"""
        return self.order_customer_type == 'company'
    
    @property
    def company(self):
        """Get company registration if this is a company order"""
        if self.is_company_order and self.company_id:
            from kirazee_app.models import CompanyRegistration
            try:
                return CompanyRegistration.objects.get(company_id=self.company_id)
            except CompanyRegistration.DoesNotExist:
                return None
        return None
    
    @property
    def ordering_employee(self):
        """Get employee who placed this company order"""
        if self.is_company_order and self.ordered_by_employee:
            from kirazee_app.models import Registration
            try:
                return Registration.objects.get(user_id=self.ordered_by_employee)
            except Registration.DoesNotExist:
                return None
        return None
    
    @property
    def needs_approval(self):
        """Check if this order needs approval"""
        if not self.is_company_order:
            return False
        return self.approval_status in ['pending_approval']
    
    @property
    def is_approved(self):
        """Check if this order is approved"""
        if not self.is_company_order:
            return True  # Individual orders don't need approval
        return self.approval_status in ['auto_approved', 'manager_approved', 'admin_approved']
    
    @property
    def approving_user(self):
        """Get user who approved this order"""
        if self.approved_by:
            from kirazee_app.models import Registration
            try:
                return Registration.objects.get(user_id=self.approved_by)
            except Registration.DoesNotExist:
                return None
        return None
    
    def approve_order(self, approved_by_user):
        """Approve a company order"""
        if not self.is_company_order:
            return False
        
        approver = self.ordering_employee.company if self.ordering_employee else None
        if not approver:
            return False
        
        # Set approval details
        self.approval_status = 'manager_approved' if approved_by_user.employee_role == 'manager' else 'admin_approved'
        self.approved_by = approved_by_user.user_id
        self.approved_at = timezone.now()
        self.save(update_fields=['approval_status', 'approved_by', 'approved_at'])
        return True
    
    def reject_order(self, rejected_by_user, reason=None):
        """Reject a company order"""
        if not self.is_company_order:
            return False
        
        self.approval_status = 'rejected'
        self.approved_by = rejected_by_user.user_id
        self.approved_at = timezone.now()
        if reason:
            self.company_notes = f"Rejected: {reason}"
        self.save(update_fields=['approval_status', 'approved_by', 'approved_at', 'company_notes'])
        return True
    
    @property
    def display_customer_name(self):
        """Get display name for customer (individual or company)"""
        if self.is_company_order:
            company_name = self.company.company_name if self.company else 'Unknown Company'
            employee_name = f"{self.ordering_employee.firstName} {self.ordering_employee.lastName}" if self.ordering_employee else 'Unknown Employee'
            return f"{company_name} - {employee_name}"
        else:
            return f"{self.user_id.firstName} {self.user_id.lastName}" if self.user_id else 'Unknown Customer'
    
    # FSM Transitions
    @transition(field=status, source=OrderStatus.PENDING, target=OrderStatus.CONFIRMED)
    def confirm_order(self):
        pass
    
    @transition(field=status, source=OrderStatus.CONFIRMED, target=OrderStatus.NOTIFIED)
    def notify_order(self):
        pass
    
    @transition(field=status, source=[OrderStatus.CONFIRMED, OrderStatus.NOTIFIED], target=OrderStatus.PREPARING)
    def start_preparing(self):
        pass
    
    @transition(field=status, source=OrderStatus.PREPARING, target=OrderStatus.READY)
    def mark_ready(self):
        pass
    
    @transition(field=status, source=OrderStatus.READY, target=OrderStatus.DISPATCHED)
    def dispatch_for_delivery(self):
        pass
    
    @transition(field=status, source=OrderStatus.DISPATCHED, target=OrderStatus.TRAVELLING)
    def start_travelling(self):
        pass
    
    @transition(field=status, source=OrderStatus.TRAVELLING, target=OrderStatus.OUT_FOR_DELIVERY)
    def out_for_delivery_grocery(self):
        pass
    
    @transition(field=status, source=[OrderStatus.DISPATCHED, OrderStatus.TRAVELLING, OrderStatus.OUT_FOR_DELIVERY], target=OrderStatus.DELIVERED)
    def complete_order(self):
        # Use timezone-aware or naive datetime based on Django settings
        if getattr(settings, 'USE_TZ', False):
            self.actual_delivery_time = timezone.now()
        else:
            self.actual_delivery_time = datetime.now()
    
    @transition(field=status, source='*', target=OrderStatus.CANCELLED)
    def cancel_order(self):
        pass
    
    def __str__(self):
        return f"Order {self.order_number} - {self.user_id.name if self.user_id else 'Unknown'}"


class OrderItems(models.Model):
    item_id = models.BigAutoField(primary_key=True)
    order_id = models.ForeignKey(Orders, on_delete=models.CASCADE, related_name='items', db_column='order_id')
    menu_item_id = models.BigIntegerField(null=True, blank=True, help_text="Reference to MenuItems.item_id")
    product_item_id = models.BigIntegerField(null=True, blank=True, help_text="Reference to productItems.item_id")
    variant_id = models.BigIntegerField(null=True, blank=True, help_text="Chosen variant_id for this order line")
    
    # Historical snapshots for immutability
    item_name_snapshot = models.CharField(max_length=255, help_text="Item name at order time")
    quantity = models.PositiveIntegerField()
    unit_price_snapshot = models.DecimalField(max_digits=10, decimal_places=2, help_text="Item price at order time")
    total_price = models.DecimalField(max_digits=10, decimal_places=2)
    item_details_snapshot = models.JSONField(help_text="Complete item details at order time")
    
    # Customizations
    customizations = models.JSONField(default=list, blank=True, help_text="Item customizations")
    
    # Tax fields
    gst = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    gst_amount = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'))
    
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = 'order_items'
    
    def save(self, *args, **kwargs):
        if not self.item_id:
            last_item = OrderItems.objects.order_by('-item_id').first()
            if last_item:
                self.item_id = last_item.item_id + 1
            else:
                self.item_id = 2001
        
        # Calculate total price
        self.total_price = self.unit_price_snapshot * self.quantity
        super().save(*args, **kwargs)
    
    def __str__(self):
        return f"{self.item_name_snapshot} x {self.quantity}"


class WalletPoints(models.Model):
    class TransactionType(models.TextChoices):
        EARNED = 'earned', 'Earned'
        SPENT = 'spent', 'Spent'
        REFUNDED = 'refunded', 'Refunded'
        EXPIRED = 'expired', 'Expired'
        ADJUSTMENT = 'adjustment', 'Adjustment'
    
    wallet_id = models.BigAutoField(primary_key=True)
    user_id = models.ForeignKey('kirazee_app.Registration', on_delete=models.CASCADE, to_field='user_id', db_column='user_id')
    transaction_type = models.CharField(max_length=20, choices=TransactionType.choices)
    points = models.DecimalField(max_digits=10, decimal_places=2)
    balance_after = models.DecimalField(max_digits=10, decimal_places=2, help_text="Balance after this transaction")
    
    # Related transactions
    related_order = models.ForeignKey(Orders, on_delete=models.SET_NULL, null=True, blank=True, related_name='wallet_transactions')
    
    description = models.TextField(help_text="Human readable description")
    expires_at = models.DateTimeField(null=True, blank=True, help_text="When these points expire")
    is_expired = models.BooleanField(default=False)
    
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = 'wallet_points'
        ordering = ['-created_at']
    
    def save(self, *args, **kwargs):
        if not self.wallet_id:
            last_wallet = WalletPoints.objects.order_by('-wallet_id').first()
            if last_wallet:
                self.wallet_id = last_wallet.wallet_id + 1
            else:
                self.wallet_id = 3001
        super().save(*args, **kwargs)
    
    @classmethod
    def get_user_balance(cls, user_id):
        """Get current wallet balance for user"""
        latest_transaction = cls.objects.filter(user_id=user_id).order_by('-created_at').first()
        return latest_transaction.balance_after if latest_transaction else Decimal('0.00')
    
    @classmethod
    def atomic_transaction(cls, user_id, points, transaction_type, description, related_order=None, expires_at=None):
        """Atomic wallet transaction with balance validation"""
        with transaction.atomic():
            # Get current balance
            current_balance = cls.get_user_balance(user_id)
            
            # Validate transaction
            if transaction_type == cls.TransactionType.SPENT and current_balance < points:
                raise ValueError(f"Insufficient balance. Available: {current_balance}, Required: {points}")
            
            # Calculate new balance
            if transaction_type in [cls.TransactionType.EARNED, cls.TransactionType.REFUNDED, cls.TransactionType.ADJUSTMENT]:
                new_balance = current_balance + points
            else:  # SPENT, EXPIRED
                new_balance = current_balance - points
            
            # Create transaction record
            wallet_transaction = cls.objects.create(
                user_id=user_id,
                transaction_type=transaction_type,
                points=points,
                balance_after=new_balance,
                related_order=related_order,
                description=description,
                expires_at=expires_at
            )
            
            return wallet_transaction
    
    def __str__(self):
        return f"{self.transaction_type} {self.points} points - {self.user_id.name if self.user_id else 'Unknown'}"


class Payments(models.Model):
    class Method(models.TextChoices):
        PAYTM = 'paytm', 'Paytm'
        PAYU = 'payu', 'PayU'
        ICICI = 'icici', 'ICICI'
        RAZORPAY = 'razorpay', 'Razorpay'
        CASH = 'cash', 'Cash'
        WALLET = 'wallet', 'Wallet'
        UPI = 'upi', 'UPI'
        CARD = 'card', 'Card'
        NET_BANKING = 'net_banking', 'Net Banking'
        AMAZON_PAY = 'amazon_pay', 'Amazon Pay'
        PHONE_PE = 'phone_pe', 'PhonePe'
        GOOGLE_PAY = 'google_pay', 'Google Pay'
        BANK_TRANSFER = 'bank_transfer', 'Bank Transfer'
        FREE = 'free', 'Free'
    
    class Status(models.TextChoices):
        PENDING = 'pending', 'Pending'
        SUCCESS = 'success', 'Success'
        FAILED = 'failed', 'Failed'
        REFUNDED = 'refunded', 'Refunded'
        EXPIRED = 'expired', 'Expired'
    
    payment_id = models.BigAutoField(primary_key=True)
    user = models.ForeignKey('kirazee_app.Registration', on_delete=models.CASCADE, to_field='user_id', db_column='user_id')
    business = models.ForeignKey('kirazee_app.Business', on_delete=models.CASCADE, to_field='business_id', db_column='business_id', null=True, blank=True)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    payment_method = models.CharField(max_length=20, choices=Method.choices)
    status = models.CharField(max_length=20, choices=Status.choices)
    transaction_id = models.CharField(max_length=100, null=True, blank=True)
    payment_source = models.CharField(max_length=50, null=True, blank=True)
    currency = models.CharField(max_length=10, default='INR')
    order_id = models.ForeignKey(Orders, on_delete=models.SET_NULL, null=True, blank=True, related_name='payments', db_column='order_id')
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = 'payments'
    
    def save(self, *args, **kwargs):
        if not self.payment_id:
            last_payment = Payments.objects.order_by('-payment_id').first()
            if last_payment:
                self.payment_id = last_payment.payment_id + 1
            else:
                self.payment_id = 1001
        super().save(*args, **kwargs)
    
    def __str__(self):
        return f"{self.payment_method} - {self.amount} - {self.status}"


class Coupons(models.Model):
    class DiscountType(models.TextChoices):
        PERCENTAGE = 'percentage', 'Percentage'
        FIXED_AMOUNT = 'fixed_amount', 'Fixed Amount'
        FREE_DELIVERY = 'free_delivery', 'Free Delivery'
        BOGO = 'bogo', 'Buy One Get One'
    
    class CreatedBy(models.TextChoices):
        KIRAZEE_ADMIN = 'kirazee_admin', 'Kirazee Admin'
        BUSINESS_OWNER = 'business_owner', 'Business Owner'
    
    class VisibilityType(models.TextChoices):
        PUBLIC = 'PUBLIC', 'Public'
        HIDDEN = 'HIDDEN', 'Hidden'
        PRIVATE = 'PRIVATE', 'Private'
    
    class CouponScope(models.TextChoices):
        BUSINESS = 'BUSINESS', 'Business'
        PLATFORM = 'PLATFORM', 'Platform'
    
    coupon_id = models.BigAutoField(primary_key=True)
    coupon_code = models.CharField(max_length=50, unique=True, db_index=True)
    name = models.CharField(max_length=120, null=True, blank=True)
    discount_type = models.CharField(max_length=20, choices=DiscountType.choices)
    discount_value = models.DecimalField(max_digits=10, decimal_places=2)
    description = models.TextField(null=True, blank=True)
    terms_and_conditions = models.TextField(null=True, blank=True)
    
    created_by = models.CharField(max_length=20, choices=CreatedBy.choices)
    business_id = models.ForeignKey('kirazee_app.Business', on_delete=models.CASCADE, null=True, blank=True, to_field='business_id', db_column='business_id')
    
    valid_from = models.DateTimeField()
    valid_to = models.DateTimeField()
    is_active = models.BooleanField(default=True)
    
    # Usage limits
    max_total_redemptions = models.PositiveIntegerField(null=True, blank=True, help_text="Total usage limit across all users")
    max_redemptions_per_user = models.PositiveIntegerField(default=1, help_text="Usage limit per user")
    current_usage_count = models.PositiveIntegerField(default=0)
    
    # Visibility and scope
    visibility_type = models.CharField(max_length=20, default='PUBLIC', choices=VisibilityType.choices)
    coupon_scope = models.CharField(max_length=20, default='BUSINESS', choices=CouponScope.choices)
    
    # Additional benefits
    free_delivery = models.BooleanField(default=False)
    free_packaging = models.BooleanField(default=False)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'coupons'
        ordering = ['-created_at']
    
    def save(self, *args, **kwargs):
        if not self.coupon_id:
            last_coupon = Coupons.objects.order_by('-coupon_id').first()
            if last_coupon:
                self.coupon_id = last_coupon.coupon_id + 1
            else:
                self.coupon_id = 4001
        super().save(*args, **kwargs)
    
    def is_valid_for_user(self, user_id):
        """Check if coupon is valid for specific user"""
        # Check if coupon is active and within validity period
        if not self.is_active:
            return False, "Coupon is not active"
        
        now = timezone.now() if getattr(settings, 'USE_TZ', False) else datetime.now()
        if now < self.valid_from or now > self.valid_to:
            return False, "Coupon has expired"
        
        # Check total usage limit
        if self.max_total_redemptions and self.current_usage_count >= self.max_total_redemptions:
            return False, "Coupon usage limit exceeded"
        
        # Check per-user usage limit
        user_usage_count = CouponRedemptions.objects.filter(
            coupon_id=self,
            user_id=user_id
        ).count()
        
        if user_usage_count >= self.max_redemptions_per_user:
            return False, "You have already used this coupon"
        
        return True, "Coupon is valid"
    
    def __str__(self):
        return f"{self.coupon_code} - {self.discount_value}{'%' if self.discount_type == 'percentage' else ''} OFF"


class CouponRules(models.Model):
    class RuleType(models.TextChoices):
        MIN_CART_VALUE = 'min_cart_value', 'Minimum Cart Value'
        ALLOWED_BUSINESS = 'allowed_business', 'Allowed Business'
        DELIVERY_ONLY = 'delivery_only', 'Delivery Only'
        FIRST_ORDER_ONLY = 'first_order_only', 'First Order Only'
        FIRST_ORDER_AT_BUSINESS = 'first_order_at_business', 'First Order At Business'
        USER_GROUP = 'user_group', 'User Group'
        ORDER_TYPE = 'order_type', 'Order Type'
        ALLOWED_USER = 'allowed_user', 'Allowed User'
        USER_TAG = 'user_tag', 'User Tag'
        INCLUDE_CATEGORY = 'include_category', 'Include Category'
        EXCLUDE_CATEGORY = 'exclude_category', 'Exclude Category'
        INCLUDE_ITEM = 'include_item', 'Include Item'
        EXCLUDE_ITEM = 'exclude_item', 'Exclude Item'
        TIME_WINDOW = 'time_window', 'Time Window'
        RETURNING_USER = 'returning_user', 'Returning User'
        EMAIL_DOMAIN = 'email_domain', 'Email Domain'
        BIRTHDAY = 'birthday', 'Birthday'
    
    rule_id = models.BigAutoField(primary_key=True)
    coupon_id = models.ForeignKey(Coupons, on_delete=models.CASCADE, related_name='rules', db_column='coupon_id', to_field='coupon_id')
    rule_type = models.CharField(max_length=30, choices=RuleType.choices)
    rule_value = models.JSONField(help_text="Rule configuration in JSON format")
    is_active = models.BooleanField(default=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = 'coupon_rules'
    
    def save(self, *args, **kwargs):
        if not self.rule_id:
            last_rule = CouponRules.objects.order_by('-rule_id').first()
            if last_rule:
                self.rule_id = last_rule.rule_id + 1
            else:
                self.rule_id = 5001
        super().save(*args, **kwargs)
    
    def evaluate_rule(self, order_data):
        """Evaluate rule against order data"""
        if self.rule_type == self.RuleType.MIN_CART_VALUE:
            min_value = self.rule_value.get('min_value', 0)
            return order_data.get('cart_value', 0) >= min_value
        
        elif self.rule_type == self.RuleType.ALLOWED_BUSINESS:
            allowed_businesses = self.rule_value.get('business_ids', [])
            return order_data.get('business_id') in allowed_businesses
        
        elif self.rule_type == self.RuleType.DELIVERY_ONLY:
            return order_data.get('order_type') == 'delivery'
        
        elif self.rule_type == self.RuleType.ORDER_TYPE:
            # Support array of allowed order types e.g. {'order_types': ['delivery','pickup','dinein']}
            try:
                rv = self.rule_value if isinstance(self.rule_value, dict) else {}
                allowed = rv.get('order_types') or rv.get('allowed_order_types') or []
                if not isinstance(allowed, list):
                    return True
                incoming = str(order_data.get('order_type') or '').lower().replace('-', '_')
                # Normalize dinein/dine_in
                if incoming == 'dinein':
                    incoming = 'dine_in'
                norm_allowed = [str(x).lower().replace('-', '_') for x in allowed]
                norm_allowed = ['dine_in' if a == 'dinein' else a for a in norm_allowed]
                return incoming in norm_allowed if norm_allowed else True
            except Exception:
                return True
        
        elif self.rule_type == self.RuleType.FIRST_ORDER_ONLY:
            user_id = order_data.get('user_id')
            if user_id:
                return not Orders.objects.filter(user_id=user_id, status=Orders.OrderStatus.DELIVERED).exists()
            return False
        
        elif self.rule_type == self.RuleType.FIRST_ORDER_AT_BUSINESS:
            user_id = order_data.get('user_id')
            business_id = order_data.get('business_id')
            if user_id and business_id:
                return not Orders.objects.filter(user_id=user_id, business_id=business_id, status=Orders.OrderStatus.DELIVERED).exists()
            return False
        
        elif self.rule_type == self.RuleType.ALLOWED_USER:
            user_id = order_data.get('user_id')
            # Allow either a single user_id or a list of user_ids in rule_value
            if isinstance(self.rule_value, dict):
                if 'user_ids' in self.rule_value:
                    return user_id in self.rule_value.get('user_ids', [])
                if 'user_id' in self.rule_value:
                    return user_id == self.rule_value.get('user_id')
            return False
        
        elif self.rule_type == self.RuleType.USER_TAG:
            user_id = order_data.get('user_id')
            if user_id:
                # Support both 'tags' and 'allowed_tags' for flexibility
                required_tags = self.rule_value.get('tags') or self.rule_value.get('allowed_tags', [])
                user_tags = list(UserTags.get_active_tags(user_id))
                return any(tag in user_tags for tag in required_tags)
            return False
        
        elif self.rule_type == self.RuleType.INCLUDE_CATEGORY:
            included_categories = self.rule_value.get('categories', [])
            cart_categories = order_data.get('cart_categories', [])
            return bool(set(included_categories) & set(cart_categories))
        
        elif self.rule_type == self.RuleType.EXCLUDE_CATEGORY:
            excluded_categories = self.rule_value.get('categories', [])
            cart_categories = order_data.get('cart_categories', [])
            return not bool(set(excluded_categories) & set(cart_categories))
        
        elif self.rule_type == self.RuleType.INCLUDE_ITEM:
            included_items = self.rule_value.get('items', [])
            cart_items = order_data.get('cart_items', [])
            return bool(set(included_items) & set(cart_items))
        
        elif self.rule_type == self.RuleType.EXCLUDE_ITEM:
            excluded_items = self.rule_value.get('items', [])
            cart_items = order_data.get('cart_items', [])
            return not bool(set(excluded_items) & set(cart_items))
        
        elif self.rule_type == self.RuleType.TIME_WINDOW:
            from datetime import datetime
            start_time = self.rule_value.get('start_time')
            end_time = self.rule_value.get('end_time')
            if start_time and end_time:
                current_time = datetime.now().time()
                return start_time <= current_time <= end_time
            return True
        
        elif self.rule_type == self.RuleType.RETURNING_USER:
            from datetime import datetime, timedelta
            from django.utils import timezone
            user_id = order_data.get('user_id')
            if user_id:
                inactive_days = self.rule_value.get('inactive_days', 30)
                cutoff_date = timezone.now() - timedelta(days=inactive_days)
                # Check if user has any orders before cutoff date
                has_old_orders = Orders.objects.filter(
                    user_id=user_id,
                    created_at__lt=cutoff_date,
                    status=Orders.OrderStatus.DELIVERED
                ).exists()
                # Check if user has recent orders after cutoff
                has_recent_orders = Orders.objects.filter(
                    user_id=user_id,
                    created_at__gte=cutoff_date,
                    status=Orders.OrderStatus.DELIVERED
                ).exists()
                return has_old_orders and not has_recent_orders
            return False
        
        elif self.rule_type == self.RuleType.EMAIL_DOMAIN:
            user_id = order_data.get('user_id')
            if user_id:
                try:
                    from kirazee_app.models import Registration
                    user = Registration.objects.get(user_id=user_id)
                    if user.emailID:
                        user_domain = user.emailID.split('@')[-1].lower()
                        allowed_domains = self.rule_value.get('allowed_domains', [])
                        if isinstance(allowed_domains, list):
                            return user_domain in [d.lower() for d in allowed_domains]
                        return user_domain == allowed_domains.lower()
                except (Registration.DoesNotExist, IndexError, AttributeError):
                    pass
            return False
        
        elif self.rule_type == self.RuleType.BIRTHDAY:
            user_id = order_data.get('user_id')
            if user_id:
                try:
                    from kirazee_app.models import Registration
                    from datetime import date, timedelta
                    user = Registration.objects.get(user_id=user_id)
                    if user.dob:
                        valid_days = self.rule_value.get('valid_days', 7)
                        today = date.today()
                        current_year_birthday = date(today.year, user.dob.month, user.dob.day)
                        
                        # Check if birthday is within valid days window
                        start_date = current_year_birthday - timedelta(days=valid_days)
                        end_date = current_year_birthday + timedelta(days=valid_days)
                        
                        return start_date <= today <= end_date
                except (Registration.DoesNotExist, ValueError, AttributeError):
                    pass
            return False
        
        return True
    
    def __str__(self):
        return f"{self.coupon_id.coupon_code} - {self.rule_type}"


class CouponApplicableItems(models.Model):
    mapping_id = models.BigAutoField(primary_key=True)
    coupon = models.ForeignKey(Coupons, on_delete=models.CASCADE, db_column='coupon_id', to_field='coupon_id')
    reference_table = models.CharField(max_length=64)
    reference_id = models.BigIntegerField()
    applicability_type = models.CharField(max_length=20, default='INCLUDE', choices=[
        ('INCLUDE', 'Include'),
        ('EXCLUDE', 'Exclude')
    ])

    class Meta:
        db_table = 'coupon_applicable_items'
        unique_together = ['coupon', 'reference_table', 'reference_id']


class CouponUserMapping(models.Model):
    id = models.BigAutoField(primary_key=True)
    coupon_id = models.ForeignKey(Coupons, on_delete=models.CASCADE, db_column='coupon_id', to_field='coupon_id')
    user_id = models.ForeignKey('kirazee_app.Registration', on_delete=models.CASCADE, to_field='user_id', db_column='user_id')
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField(null=True, blank=True)
    
    class Meta:
        db_table = 'coupon_user_mapping'
        unique_together = ['coupon_id', 'user_id']
    
    def save(self, *args, **kwargs):
        if not self.id:
            last_mapping = CouponUserMapping.objects.order_by('-id').first()
            if last_mapping:
                self.id = last_mapping.id + 1
            else:
                self.id = 8001
        super().save(*args, **kwargs)


class UserTags(models.Model):
    id = models.BigAutoField(primary_key=True)
    user_id = models.ForeignKey('kirazee_app.Registration', on_delete=models.CASCADE, to_field='user_id', db_column='user_id')
    tag = models.CharField(max_length=50)
    assigned_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField(null=True, blank=True)
    is_active = models.BooleanField(default=True)
    
    class Meta:
        db_table = 'user_tags'
        unique_together = ['user_id', 'tag']
        indexes = [
            models.Index(fields=['user_id', 'is_active', 'expires_at']),
        ]
    
    def save(self, *args, **kwargs):
        if not self.id:
            last_tag = UserTags.objects.order_by('-id').first()
            if last_tag:
                self.id = last_tag.id + 1
            else:
                self.id = 9001
        super().save(*args, **kwargs)
    
    @classmethod
    def get_active_tags(cls, user_id):
        """Get active tags for user (non-expired)"""
        from django.utils import timezone
        return cls.objects.filter(
            user_id=user_id,
            is_active=True
        ).filter(
            models.Q(expires_at__isnull=True) | models.Q(expires_at__gte=timezone.now())
        ).values_list('tag', flat=True)


class DomainTagMapping(models.Model):
    """Database model for domain to tag mapping configuration"""
    id = models.BigAutoField(primary_key=True)
    domain = models.CharField(max_length=100, db_index=True)  # Removed unique=True to allow per-business mappings
    tag = models.CharField(max_length=50)
    description = models.CharField(max_length=200, blank=True, null=True)
    org_name = models.CharField(max_length=255, blank=True, default='')  # Organization name for better context
    business_id = models.ForeignKey(
        'kirazee_app.Business',
        on_delete=models.CASCADE,
        to_field='business_id',
        db_column='business_id',
        null=True,
        blank=True,
        help_text="Business owner for this domain mapping. Null for global mappings."
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'domain_tag_mapping'
        ordering = ['business_id', 'domain']
        unique_together = ['domain', 'business_id']  # Ensure domain is unique per business
    
    def save(self, *args, **kwargs):
        if not self.id:
            last_mapping = DomainTagMapping.objects.order_by('-id').first()
            if last_mapping:
                self.id = last_mapping.id + 1
            else:
                self.id = 10001
        super().save(*args, **kwargs)
    
    def __str__(self):
        business_prefix = f"[{self.business_id}] " if self.business_id else "[Global] "
        return f"{business_prefix}{self.domain} → {self.tag} ({self.org_name or 'No org'})"


class CouponRedemptions(models.Model):
    redemption_id = models.BigAutoField(primary_key=True)
    coupon_id = models.ForeignKey(Coupons, on_delete=models.CASCADE, db_column='coupon_id', to_field='coupon_id')
    order_id = models.ForeignKey(Orders, on_delete=models.CASCADE, db_column='order_id')
    user_id = models.ForeignKey('kirazee_app.Registration', on_delete=models.CASCADE, to_field='user_id', db_column='user_id')
    
    discount_amount_applied = models.DecimalField(max_digits=10, decimal_places=2)
    original_order_amount = models.DecimalField(max_digits=10, decimal_places=2)
    final_order_amount = models.DecimalField(max_digits=10, decimal_places=2)
    
    redeemed_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = 'coupon_redemptions'
    
    def save(self, *args, **kwargs):
        if not self.redemption_id:
            last_redemption = CouponRedemptions.objects.order_by('-redemption_id').first()
            if last_redemption:
                self.redemption_id = last_redemption.redemption_id + 1
            else:
                self.redemption_id = 7001
        super().save(*args, **kwargs)
    
    def __str__(self):
        return f"{self.coupon_id.coupon_code} redeemed in order {self.order_id.order_number}"


class DeliveryCharges(models.Model):
    delivery_id = models.BigAutoField(primary_key=True)
    business_id = models.ForeignKey('kirazee_app.Business', on_delete=models.CASCADE, to_field='business_id', db_column='business_id')
    
    base_charge = models.DecimalField(max_digits=8, decimal_places=2, default=Decimal('30.00'))
    parcel_charges = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'))
    distance_slabs = models.JSONField(default=list, help_text="Distance-based pricing slabs")
    free_delivery_above = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True, help_text="Free delivery threshold")
    max_charge = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True, help_text="Maximum delivery charge")
    max_delivery_distance = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True, help_text="Maximum delivery distance in km")
    
    # Peak hour pricing
    peak_hours_start = models.TimeField(null=True, blank=True)
    peak_hours_end = models.TimeField(null=True, blank=True)
    peak_hour_multiplier = models.DecimalField(max_digits=3, decimal_places=2, default=Decimal('1.00'))
    
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'delivery_charges'
        unique_together = ['business_id']
    
    def save(self, *args, **kwargs):
        if not self.delivery_id:
            last_delivery = DeliveryCharges.objects.order_by('-delivery_id').first()
            if last_delivery:
                self.delivery_id = last_delivery.delivery_id + 1
            else:
                self.delivery_id = 8001
        super().save(*args, **kwargs)
    
    def __str__(self):
        return f"Delivery config for {self.business_id.businessName if self.business_id else 'Unknown'}"


class BusinessOrderTypes(models.Model):
    id = models.BigAutoField(primary_key=True)
    business = models.ForeignKey('kirazee_app.Business', on_delete=models.CASCADE, to_field='business_id', db_column='business_id')
    order_types = models.JSONField(default=list, help_text="List of allowed order types e.g. ['delivery','pickup']")
    is_cod_available = models.BooleanField(default=False, help_text="Whether COD (Cash on Delivery) is available for this business")
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'business_order_types'
        unique_together = ['business']

    def __str__(self):
        bid = self.business.business_id if self.business else 'Unknown'
        return f"Order types for {bid}: {self.order_types}"

    @staticmethod
    def default_for_business_type(business_type: str):
        mapping = {
            'R01': ['delivery', 'pick_up'],
            'R02': ['delivery', 'dine_in', 'takeaway', 'pick_up'],
        }
        return mapping.get(str(business_type).upper() if business_type else None, ['delivery'])

    @classmethod
    def get_allowed_for_business(cls, business_obj):
        try:
            config = cls.objects.filter(business=business_obj, is_active=True).first()
            if config and isinstance(config.order_types, list) and len(config.order_types) > 0:
                # Normalize to internal format
                return [str(t).lower().replace('-', '_') for t in config.order_types]
        except Exception:
            pass
        # Fallback to defaults by business type
        return cls.default_for_business_type(getattr(business_obj, 'businessType', None))


class PointsConfiguration(models.Model):
    config_id = models.BigAutoField(primary_key=True)
    business_id = models.ForeignKey('kirazee_app.Business', on_delete=models.CASCADE, null=True, blank=True, to_field='business_id', db_column='business_id')
    
    # Points earning configuration
    points_per_rupee_spent = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal('1.00'), help_text="Points earned per rupee spent")
    points_per_rupee_value = models.DecimalField(max_digits=5, decimal_places=4, default=Decimal('0.1000'), help_text="Rupee value per point (default: 10 points = 1 rupee)")
    
    min_order_value_for_points = models.DecimalField(max_digits=8, decimal_places=2, default=Decimal('100.00'))
    max_points_per_order = models.PositiveIntegerField(null=True, blank=True, help_text="Maximum points that can be earned per order")
    points_expiry_days = models.PositiveIntegerField(default=365, help_text="Days after which points expire")
    
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'points_configuration'
    
    def save(self, *args, **kwargs):
        if not self.config_id:
            last_config = PointsConfiguration.objects.order_by('-config_id').first()
            if last_config:
                self.config_id = last_config.config_id + 1
            else:
                self.config_id = 9001
        super().save(*args, **kwargs)
    
    def __str__(self):
        business_name = self.business_id.businessName if self.business_id else "Global"
        return f"Points config for {business_name}"


class Payments(models.Model):
    class Status(models.TextChoices):
        PENDING = 'pending', 'Pending'
        SUCCESS = 'success', 'Success'
        FAILED = 'failed', 'Failed'
        CANCELLED = 'cancelled', 'Cancelled'
        COD = 'cod', 'Cash on Delivery'
        
    class Method(models.TextChoices):
        RAZORPAY = 'razorpay', 'Razorpay'
        ICICI = 'icici', 'ICICI'
        WALLET = 'wallet', 'Wallet'
        COD = 'cod', 'Cash on Delivery'
    
    id = models.BigAutoField(primary_key=True)
    transaction_id = models.CharField(max_length=100, blank=True, null=True)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    currency = models.CharField(max_length=10, default='INR')
    payment_method = models.CharField(max_length=50, choices=Method.choices, blank=True, null=True)
    status = models.CharField(max_length=50, choices=Status.choices, default=Status.PENDING)
    refund_status = models.CharField(max_length=50, blank=True, null=True)
    refund_id = models.CharField(max_length=100, blank=True, null=True)
    upi_id = models.CharField(max_length=100, blank=True, null=True)
    payment_type = models.CharField(max_length=50, blank=True, null=True)
    business = models.ForeignKey('kirazee_app.Business', on_delete=models.CASCADE, db_column='business_id')
    user = models.ForeignKey('kirazee_app.Registration', on_delete=models.CASCADE, db_column='user_id')
    order_id = models.IntegerField(blank=True, null=True, help_text='Reference to the order this payment is for')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    payment_source = models.CharField(max_length=100, blank=True, null=True)
    
    # Additional fields for order reference (not in DB, will be handled in code)
    order = None
    provider_order_id = None
    provider_payment_id = None
    
    class Meta:
        db_table = 'payments'
        verbose_name = 'Payment'
        verbose_name_plural = 'Payments'
        
    def __str__(self):
        return f"Payment {self.id} - {self.amount} {self.currency} ({self.status})"


class Rating(models.Model):
    id = models.BigAutoField(primary_key=True)
    product_id = models.BigIntegerField(null=True, blank=True, help_text="Reference to MenuItems or GroceryItems item_id")
    variant_id = models.BigIntegerField(null=True, blank=True, help_text="Reference to product variant_id")
    user_id = models.ForeignKey('kirazee_app.Registration', on_delete=models.CASCADE, to_field='user_id', db_column='user_id', null=True, blank=True)
    rating = models.IntegerField(help_text="Rating from 1 to 5")
    review = models.TextField(null=True, blank=True, help_text="Review text with emoji support")
    business_id = models.ForeignKey('kirazee_app.Business', on_delete=models.CASCADE, to_field='business_id', db_column='business_id')
    order_id = models.ForeignKey(Orders, on_delete=models.SET_NULL, null=True, blank=True, db_column='order_id')
    username = models.CharField(max_length=255, null=True, blank=True, help_text="Cached username for performance")
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = 'rating'
        # Note: unique_together with nullable fields can be tricky, 
        # we'll handle duplicate prevention in the API logic instead
    
    def save(self, *args, **kwargs):
        # Cache username from Registration table
        if self.user_id and not self.username:
            try:
                user = self.user_id
                self.username = f"{user.firstName} {user.lastName}".strip()
            except:
                self.username = "Anonymous User"
        elif not self.user_id and not self.username:
            # Handle anonymous users (user_id is None)
            self.username = "Anonymous User"
        
        super().save(*args, **kwargs)
        
        # Update average rating in MenuItems/GroceryItems after saving
        self.update_item_rating()
    
    def update_item_rating(self):
        """Update average rating in MenuItems or GroceryItems table"""
        if not self.product_id:
            return
            
        from django.db import connection
        with connection.cursor() as cursor:
            biz_id = None
            try:
                biz_id = getattr(self, 'business_id_id', None)
            except Exception:
                biz_id = None

            # Calculate average rating for this product
            if biz_id:
                cursor.execute(
                    "SELECT AVG(rating) FROM rating WHERE product_id = %s AND business_id = %s",
                    [self.product_id, biz_id]
                )
            else:
                cursor.execute(
                    "SELECT AVG(rating) FROM rating WHERE product_id = %s",
                    [self.product_id]
                )
            avg_rating = cursor.fetchone()[0]
            
            if avg_rating:
                rounded = round(avg_rating, 2)
                # Try to update MenuItems first
                if biz_id:
                    cursor.execute(
                        "UPDATE menuItems SET rating = %s WHERE item_id = %s AND business_id = %s",
                        [rounded, self.product_id, biz_id]
                    )
                else:
                    cursor.execute(
                        "UPDATE menuItems SET rating = %s WHERE item_id = %s",
                        [rounded, self.product_id]
                    )
                
                # If no rows affected, try GroceryItems
                if cursor.rowcount == 0:
                    if biz_id:
                        cursor.execute(
                            "UPDATE GroceryItems SET rating = %s WHERE item_id = %s AND business_id = %s",
                            [rounded, self.product_id, biz_id]
                        )
                    else:
                        cursor.execute(
                            "UPDATE GroceryItems SET rating = %s WHERE item_id = %s",
                            [rounded, self.product_id]
                        )

                # If no rows affected, try Groceries_Products
                if cursor.rowcount == 0:
                    if biz_id:
                        cursor.execute(
                            "UPDATE Groceries_Products SET rating = %s WHERE product_id = %s AND business_id = %s",
                            [rounded, self.product_id, biz_id]
                        )
                    else:
                        cursor.execute(
                            "UPDATE Groceries_Products SET rating = %s WHERE product_id = %s",
                            [rounded, self.product_id]
                        )

                # If still no rows affected, try fashion_products
                if cursor.rowcount == 0:
                    if biz_id:
                        cursor.execute(
                            "UPDATE fashion_products SET rating = %s WHERE product_id = %s AND business_id = %s",
                            [rounded, self.product_id, biz_id]
                        )
                    else:
                        cursor.execute(
                            "UPDATE fashion_products SET rating = %s WHERE product_id = %s",
                            [rounded, self.product_id]
                        )
    
    def __str__(self):
        return f"{self.username} - {self.rating} stars - {self.product_id}"
 
 
class Feedback(models.Model):
    feedback_id = models.BigAutoField(primary_key=True)
    user_id = models.ForeignKey(
        'kirazee_app.Registration',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        to_field='user_id',
        db_column='user_id'
    )
    rating = models.PositiveSmallIntegerField(help_text="Rating from 1 to 5")
    comments = models.TextField(null=True, blank=True, help_text="Emoji-friendly comments")
    username = models.CharField(max_length=255, null=True, blank=True, help_text="Cached username for performance")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'feedback'
        ordering = ['-created_at']

    def save(self, *args, **kwargs):
        # Cache username similar to Rating model
        if self.user_id and not self.username:
            try:
                user = self.user_id
                self.username = f"{user.firstName} {user.lastName}".strip()
            except Exception:
                self.username = "Anonymous User"
        elif not self.user_id and not self.username:
            self.username = "Anonymous User"

        super().save(*args, **kwargs)

    def __str__(self):
        return f"Feedback {self.feedback_id} - {self.rating} stars"

class Wishlist(models.Model):
    wishlist_id = models.AutoField(primary_key=True)
    user = models.ForeignKey(
        'kirazee_app.Registration', 
        on_delete=models.CASCADE,
        db_column='user_id',
        to_field='user_id',  # Explicitly specify the target field
        db_constraint=True
    )
    item_id = models.BigIntegerField()
    business = models.ForeignKey(
        'kirazee_app.Business',
        on_delete=models.CASCADE,
        db_column='business_id'
    )
    item_type = models.CharField(max_length=20, choices=[
        ('menu', 'Menu Item'),
        ('grocery', 'Grocery Product')
    ])
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'wishlist'
        unique_together = (('user', 'item_id', 'item_type'),)

class OrderRefund(models.Model):
    refund_id = models.BigAutoField(primary_key=True)
    order_system = models.CharField(max_length=20)
    order_id = models.BigIntegerField()
    business_id = models.CharField(max_length=50)
    user_id = models.BigIntegerField(null=True, blank=True)
    payment_method = models.CharField(max_length=50, null=True, blank=True)
    provider_payment_id = models.CharField(max_length=100, null=True, blank=True)
    requested_amount = models.DecimalField(max_digits=10, decimal_places=2)
    refund_amount = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    currency = models.CharField(max_length=10, default='INR')
    reason = models.TextField(null=True, blank=True)
    initiated_by = models.BigIntegerField(null=True, blank=True)
    refund_mode = models.CharField(max_length=20)
    status = models.CharField(max_length=20)
    provider_refund_id = models.CharField(max_length=100, null=True, blank=True)
    provider_response = models.JSONField(null=True, blank=True)
    email_sent = models.BooleanField(default=False)
    created_at = models.DateTimeField()
    updated_at = models.DateTimeField()

    class Meta:
        db_table = 'order_refunds'
        managed = False

class OrderStatusLog(models.Model):
    log_id = models.BigAutoField(primary_key=True)
    order_system = models.CharField(max_length=20)
    order_id = models.BigIntegerField(db_index=True)
    from_status = models.CharField(max_length=50, null=True, blank=True)
    to_status = models.CharField(max_length=50)
    changed_by_user_id = models.BigIntegerField(null=True, blank=True)
    changed_by_role = models.CharField(max_length=30, null=True, blank=True)
    source = models.CharField(max_length=50, null=True, blank=True)
    notes = models.TextField(null=True, blank=True)
    metadata = models.JSONField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'order_status_log'
        indexes = [
            models.Index(fields=['order_system', 'order_id']),
            models.Index(fields=['to_status']),
        ]

def create_status_log(order_system, order_id, from_status, to_status, user_id=None, role=None, notes=None, source=None, metadata=None):
    try:
        uid = None
        try:
            uid = int(user_id) if user_id is not None else None
        except Exception:
            uid = None
        OrderStatusLog.objects.create(
            order_system=str(order_system),
            order_id=int(order_id),
            from_status=(str(from_status) if from_status is not None else None),
            to_status=str(to_status),
            changed_by_user_id=uid,
            changed_by_role=(str(role) if role else None),
            source=(str(source) if source else None),
            notes=(str(notes) if notes else None),
            metadata=metadata or None,
        )
    except Exception:
        return None
