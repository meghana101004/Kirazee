from django.db import models
from kirazee_app.models import Business, Registration
from datetime import datetime
from django.utils import timezone


class GroceriesCategories(models.Model):
    category_id = models.BigAutoField(primary_key=True)
    category_name = models.CharField(max_length=100)
    category_image = models.CharField(max_length=225, null=True, blank=True)
    # Store parent category NAME directly in the parent_category_id column (VARCHAR)
    # instead of referencing another GroceriesCategories row by id.
    parent_category_id = models.BigIntegerField(null=True, blank=True)
    created_at = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = 'universal_Categories'
        managed = False

    def __str__(self):
        return self.category_name

    @property
    def parent_category(self):
        try:
            pid = getattr(self, 'parent_category_id', None)
            if not pid:
                return None
            parent = self.__class__.objects.filter(category_id=pid).only('category_name').first()
            return parent.category_name if parent else None
        except Exception:
            return None

    @property
    def gst_rate(self):
        return 0


class GroceriesProducts(models.Model):
    product_id = models.BigAutoField(primary_key=True)
    business = models.ForeignKey(Business, on_delete=models.CASCADE, db_column='business_id')
    product_name = models.CharField(max_length=255)
    brand_name = models.CharField(max_length=100, null=True, blank=True)
    category = models.ForeignKey(GroceriesCategories, on_delete=models.CASCADE, db_column='category_id')
    sub_category = models.CharField(null=True, blank=True, max_length=225)
    # Numeric FK to universal_Categories for structured sub-category lookup
    sub_category_id = models.BigIntegerField(null=True, blank=True, db_column='sub_category_id')
    description = models.TextField(null=True, blank=True)
    item_placed_at = models.CharField(max_length=100, null=True, blank=True)
    main_image = models.CharField(max_length=255, null=True, blank=True)
    sub_images = models.JSONField(null=True, blank=True, help_text="Additional images in JSON array format")
    is_featured = models.BooleanField(default=False, help_text="Mark product as featured")
    is_customizable = models.BooleanField(default=False, db_column='is_customizable')
    is_visible = models.BooleanField(null=True, default=True)
    is_organic = models.BooleanField(default=False)
    # Base price for this product — variants inherit this when no price_override is set
    base_price = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    rating = models.DecimalField(max_digits=2, decimal_places=1, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'Groceries_Products'
        indexes = [
            models.Index(fields=['business', 'category'], name='idx_business_category'),
            models.Index(fields=['business', 'product_name'], name='idx_business_product'),
            models.Index(fields=['category'], name='idx_category'),
            models.Index(fields=['brand_name'], name='idx_brand'),
        ]

    def __str__(self):
        return self.product_name


class GroceriesProductVariants(models.Model):
    WEIGHT_UNIT_CHOICES = [
        ('g', 'Grams'),
        ('kg', 'Kilograms'),
        ('ml', 'Milliliters'),
        ('l', 'Liters'),
        ('pcs', 'Pieces'),
        ('pack', 'Pack'),
        ('Packet', 'Packet'),
        ('Bag', 'Bag'),
        ('Bottle', 'Bottle'),
        ('Box', 'Box'),
        ('Can', 'Can'),
        ('Dozen', 'Dozen'),
        ('Jar', 'Jar'),
        ('Roll', 'Roll'),
        ('Tray', 'Tray'),
        ('Other', 'Other'),
        ('Pants', 'Pants'),
        ('Shirts', 'Shirts'),
    ]
    
    variant_id = models.BigAutoField(primary_key=True)
    product = models.ForeignKey(GroceriesProducts, on_delete=models.CASCADE, db_column='product_id')
    # sku is nullable in DB (DEFAULT NULL) but has a UNIQUE constraint
    sku = models.CharField(max_length=100, unique=True, null=True, blank=True)
    barcode = models.CharField(max_length=255, null=True, blank=True)
    net_weight = models.IntegerField(null=True, blank=True)
    net_weight_unit = models.CharField(max_length=10, choices=WEIGHT_UNIT_CHOICES, default='g')
    # size is stored as JSON in DB: e.g. {"value": "1L"} or {"length": 10, "breadth": 5, "width": 3}
    size = models.JSONField(null=True, blank=True)
    original_cost = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    selling_price = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    # Admin-only override: if set, bypasses base_price + premium formula
    price_override = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    charges = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    gst = models.DecimalField(max_digits=5, decimal_places=2, default=0.00, null=True, blank=True, help_text="GST percentage for this variant (e.g., 5.00, 12.00, 18.00)")
    stock = models.IntegerField(default=0)
    rating = models.DecimalField(max_digits=3, decimal_places=2, null=True, blank=True, default=4.0)
    rating_count = models.IntegerField(null=True, blank=True, default=0)
    mfg_date = models.DateField(null=True, blank=True)
    expiry_date = models.DateField(null=True, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    # --- New attribute columns ---
    color = models.CharField(max_length=100, null=True, blank=True)
    gender = models.CharField(max_length=50, null=True, blank=True)
    age = models.CharField(max_length=50, null=True, blank=True)
    # Structured integer age range for slider queries (e.g. WHERE 5 BETWEEN min_age AND max_age)
    min_age = models.IntegerField(null=True, blank=True)
    max_age = models.IntegerField(null=True, blank=True)
    material = models.CharField(max_length=100, null=True, blank=True)
    # Free-form extra attributes (e.g. {"fabric": "cotton", "fit": "slim"})
    attributes = models.JSONField(null=True, blank=True)
    pack = models.CharField(max_length=100, null=True, blank=True)
    # 1 = visible on counter/POS, 0 = hidden; default 1
    is_visible_counter = models.BooleanField(default=True)
    # Product dimensions in JSON format: {"L": length, "B": breadth, "H": height}
    dimension = models.JSONField(null=True, blank=True, help_text="Product dimensions in JSON format: {'L': length, 'B': breadth, 'H': height}")

    class Meta:
        db_table = 'Groceries_ProductVariants_1'
        managed = False  # Table is managed via raw SQL / modification.sql, not Django migrations
    
    def save(self, *args, **kwargs):
        # Auto-generate SKU if not provided
        if not self.sku:
            self.sku = self._generate_sku()
        
        # Ensure is_active is properly set as boolean
        if self.is_active is None:
            self.is_active = True
        
        super().save(*args, **kwargs)
    
    def _generate_sku(self):
        """Generate SKU from product_name, net_weight, and net_weight_unit.
        size is now a JSON field — extract string value safely.
        """
        import re
        # Clean product name: remove special chars, convert to lowercase
        product_name = self.product.product_name if self.product else 'product'
        clean_name = re.sub(r'[^a-zA-Z0-9\s]', '', product_name)
        clean_name = clean_name.lower().replace(' ', '')

        # Add net_weight and unit if available
        if self.net_weight and self.net_weight_unit:
            sku = f"{clean_name}_{self.net_weight}{self.net_weight_unit}"
        elif self.size:
            # size is a JSON dict — extract a human-readable string safely
            # Supports: {"value": "1L"}, {"length": 10, "breadth": 5, "width": 3}, or plain strings
            if isinstance(self.size, dict):
                size_str = (
                    self.size.get('value')
                    or '_'.join(str(v) for v in self.size.values() if v is not None)
                    or 'size'
                )
            else:
                size_str = str(self.size)
            clean_size = re.sub(r'[^a-zA-Z0-9]', '', size_str.lower())
            sku = f"{clean_name}_{clean_size}" if clean_size else clean_name
        elif self.color:
            clean_color = re.sub(r'[^a-zA-Z0-9]', '', str(self.color).lower())
            sku = f"{clean_name}_{clean_color}"
        else:
            sku = clean_name

        # Ensure uniqueness by appending a counter if needed
        base_sku = sku
        counter = 1
        while GroceriesProductVariants.objects.filter(sku=sku).exclude(variant_id=self.variant_id).exists():
            sku = f"{base_sku}_{counter}"
            counter += 1

        return sku

    def __str__(self):
        return f"{self.product.product_name} - {self.sku}"


class GroceriesCart(models.Model):
    id = models.BigAutoField(primary_key=True)
    user = models.ForeignKey(Registration, on_delete=models.CASCADE, db_column='user_id')
    product = models.ForeignKey(GroceriesProducts, on_delete=models.CASCADE, db_column='product_id')
    quantity = models.PositiveIntegerField()
    customizations = models.JSONField(default=list, null=True, blank=True)
    added_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    business = models.ForeignKey(Business, on_delete=models.CASCADE, db_column='business_id', null=True, blank=True)
    class Meta:
        db_table = 'Groceries_cart'

class GroceriesCustomDesigns(models.Model):
    id = models.BigAutoField(primary_key=True)
    business = models.ForeignKey(Business, on_delete=models.CASCADE, db_column='business_id')
    product_id = models.BigIntegerField() # Linking to either Menu, Grocery or Fashion product_id
    name = models.CharField(max_length=255)
    design_type = models.CharField(max_length=100)
    price_delta = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    asset_url = models.CharField(max_length=255, null=True, blank=True)
    max_chars = models.IntegerField(null=True, blank=True)
    per_char_price = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    flat_price = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    base_price = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    is_active = models.BooleanField(default=True)
    position = models.IntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'Groceries_CustomDesigns'
        managed = False

    def __str__(self):
        return f"{self.name} ({self.design_type})"


class GroceriesOrders(models.Model):
    order_id = models.BigAutoField(primary_key=True)
    user = models.ForeignKey(Registration, on_delete=models.CASCADE, db_column='user_id')
    business = models.ForeignKey(Business, on_delete=models.CASCADE, db_column='business_id')
    order_type = models.CharField(max_length=20)
    order_status = models.CharField(max_length=20, default='pending')
    payment_status = models.CharField(max_length=20, default='pending')
    total_amount = models.DecimalField(max_digits=10, decimal_places=2)
    gst_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    delivery_charge = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    discount = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    final_amount = models.DecimalField(max_digits=10, decimal_places=2)
    delivery_address = models.TextField(null=True, blank=True)
    delivery_latitude = models.DecimalField(max_digits=10, decimal_places=8, null=True, blank=True)
    delivery_longitude = models.DecimalField(max_digits=11, decimal_places=8, null=True, blank=True)
    delivery_time = models.DateTimeField(null=True, blank=True)
    delivery_instructions = models.TextField(null=True, blank=True)
    pickup_time = models.DateTimeField(null=True, blank=True)
    pickup_otp = models.CharField(max_length=6, null=True, blank=True)
    pickup_otp_generated_at = models.DateTimeField(null=True, blank=True)
    pickup_otp_verified_at = models.DateTimeField(null=True, blank=True)
    
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

    def generate_pickup_otp(self):
        """Generate a 6-digit OTP for pickup verification"""
        import random
        from django.utils import timezone
        from django.db import connection
        
        otp = str(random.randint(100000, 999999))
        
        # Check if OTP fields exist in database, if not use raw SQL
        try:
            self.pickup_otp = otp
            self.pickup_otp_generated_at = timezone.now()
            self.pickup_otp_verified_at = None
            self.save(update_fields=['pickup_otp', 'pickup_otp_generated_at', 'pickup_otp_verified_at'])
        except Exception as e:
            print(f"DEBUG: OTP fields don't exist yet, using raw SQL: {e}")
            # Use raw SQL to update if fields don't exist in model
            with connection.cursor() as cursor:
                try:
                    cursor.execute(
                        "UPDATE Groceries_orders SET pickup_otp = %s, pickup_otp_generated_at = %s, pickup_otp_verified_at = NULL WHERE order_id = %s",
                        [otp, timezone.now(), self.order_id]
                    )
                except Exception as sql_error:
                    print(f"DEBUG: Raw SQL also failed, fields likely don't exist: {sql_error}")
                    # Store OTP in a temporary way or return it for manual handling
                    pass
        
        return otp
    
    def verify_pickup_otp(self, otp):
        """Verify the pickup OTP"""
        from django.utils import timezone
        from django.db import connection
        
        # Get current OTP from database using raw SQL if needed
        try:
            current_otp = self.pickup_otp
        except:
            # If field doesn't exist, get from raw SQL
            with connection.cursor() as cursor:
                cursor.execute("SELECT pickup_otp FROM Groceries_orders WHERE order_id = %s", [self.order_id])
                result = cursor.fetchone()
                current_otp = result[0] if result else None
        
        if current_otp and str(current_otp).strip() == str(otp).strip():
            try:
                self.pickup_otp_verified_at = timezone.now()
                self.save(update_fields=['pickup_otp_verified_at'])
            except:
                # Use raw SQL if field doesn't exist
                with connection.cursor() as cursor:
                    cursor.execute(
                        "UPDATE Groceries_orders SET pickup_otp_verified_at = %s WHERE order_id = %s",
                        [timezone.now(), self.order_id]
                    )
            return True
        return False
    
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
            return f"{self.user.firstName} {self.user.lastName}" if self.user else 'Unknown Customer'

    def is_pickup_otp_valid(self):
        """Check if pickup OTP is valid and not expired"""
        from django.utils import timezone
        from datetime import timedelta
        from django.db import connection
        
        try:
            pickup_otp = self.pickup_otp
            pickup_otp_generated_at = self.pickup_otp_generated_at
            pickup_otp_verified_at = self.pickup_otp_verified_at
        except:
            # If fields don't exist, get from raw SQL
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT pickup_otp, pickup_otp_generated_at, pickup_otp_verified_at FROM Groceries_orders WHERE order_id = %s", 
                    [self.order_id]
                )
                result = cursor.fetchone()
                if not result:
                    return False
                pickup_otp, pickup_otp_generated_at, pickup_otp_verified_at = result
        
        if not pickup_otp or not pickup_otp_generated_at:
            return False
        
        # OTP expires after 30 minutes
        expiry_time = pickup_otp_generated_at + timedelta(minutes=30)
        return timezone.now() <= expiry_time and not pickup_otp_verified_at

    class Meta:
        db_table = 'Groceries_orders'


class GroceriesOrderItems(models.Model):
    order_item_id = models.BigAutoField(primary_key=True)
    order = models.ForeignKey(GroceriesOrders, on_delete=models.CASCADE, db_column='order_id')
    product = models.ForeignKey(GroceriesProducts, on_delete=models.CASCADE, db_column='product_id')
    quantity = models.PositiveIntegerField()
    unit_price = models.DecimalField(max_digits=10, decimal_places=2)
    gst = models.DecimalField(max_digits=5, decimal_places=2, default=0.00)
    total_price = models.DecimalField(max_digits=10, decimal_places=2)

    class Meta:
        db_table = 'Groceries_order_items'


class GroceriesPayments(models.Model):
    PAYMENT_METHOD_CHOICES = [
        ('cash', 'Cash'),
        ('card', 'Card'),
        ('upi', 'UPI'),
        ('wallet', 'Wallet'),
        ('razorpay', 'Razorpay'),
    ]
    PAYMENT_STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
        ('refunded', 'Refunded'),
        ('cancelled', 'Cancelled'),
    ]

    payment_id = models.BigAutoField(primary_key=True)
    order = models.ForeignKey(GroceriesOrders, on_delete=models.CASCADE, db_column='order_id')
    user = models.ForeignKey(Registration, on_delete=models.CASCADE, db_column='user_id')
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    payment_method = models.CharField(max_length=10, choices=PAYMENT_METHOD_CHOICES)
    payment_status = models.CharField(max_length=10, choices=PAYMENT_STATUS_CHOICES, default='pending')
    transaction_id = models.CharField(max_length=255, null=True, blank=True)
    payment_date = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'Groceries_payments'


class GroceryPartner(models.Model):
    VEHICLE_TYPE_CHOICES = [
        ('bike', 'Bike'),
        ('scooter', 'Scooter'),
        ('car', 'Car'),
        ('van', 'Van'),
        ('truck', 'Truck'),
        ('bicycle', 'Bicycle'),
        ('auto', 'Auto Rickshaw'),
    ]
    
    AVAILABILITY_STATUS_CHOICES = [
        ('available', 'Available'),
        ('busy', 'Busy'),
        ('offline', 'Offline'),
        ('break', 'Break'),
    ]

    id = models.AutoField(primary_key=True)
    user = models.OneToOneField(Registration, on_delete=models.CASCADE, db_column='user_id', to_field='user_id')
    business = models.ForeignKey(Business, on_delete=models.CASCADE, db_column='business_id', to_field='business_id', null=True, blank=True)
    vehicle_number = models.CharField(max_length=20, unique=True)
    vehicle_type = models.CharField(max_length=20, choices=VEHICLE_TYPE_CHOICES)
    driving_license_number = models.CharField(max_length=20, unique=True)
    aadhar_card_number = models.CharField(max_length=12, unique=True)
    bank_account_number = models.CharField(max_length=20, null=True, blank=True)
    bank_ifsc_code = models.CharField(max_length=11, null=True, blank=True)
    bank_account_holder_name = models.CharField(max_length=100, null=True, blank=True)
    emergency_contact_name = models.CharField(max_length=100, null=True, blank=True)
    emergency_contact_phone = models.CharField(max_length=15, null=True, blank=True)
    delivery_zones = models.JSONField(null=True, blank=True, help_text="Store array of delivery area codes")
    current_latitude = models.DecimalField(max_digits=10, decimal_places=8, null=True, blank=True)
    current_longitude = models.DecimalField(max_digits=11, decimal_places=8, null=True, blank=True)
    availability_status = models.CharField(max_length=10, choices=AVAILABILITY_STATUS_CHOICES, default='offline')
    rating_average = models.DecimalField(max_digits=3, decimal_places=2, default=0.00)
    total_deliveries = models.IntegerField(default=0)
    is_verified = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    joined_date = models.DateField()
    last_active_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'Grocery_partner'
        indexes = [
            models.Index(fields=['availability_status']),
            models.Index(fields=['current_latitude', 'current_longitude']),
        ]

    def __str__(self):
        return f"Partner {self.user.firstName} {self.user.lastName} - {self.vehicle_number}"

    def set_delivery_zones(self, zones_list):
        """Helper method to set delivery zones as JSON"""
        self.delivery_zones = zones_list

    def get_delivery_zones(self):
        """Helper method to get delivery zones from JSON"""
        return self.delivery_zones if self.delivery_zones else []


class GroceryDeliverDetails(models.Model):
    ASSIGNMENT_STATUS_CHOICES = [
        ('assigned', 'Assigned'),
        ('accepted', 'Accepted'),
        ('picked_up', 'Picked Up'),
        ('in_transit', 'In Transit'),
        ('delivered', 'Delivered'),
        ('cancelled', 'Cancelled'),
    ]

    delivery_detail_id = models.BigAutoField(primary_key=True)
    order = models.OneToOneField(
        GroceriesOrders, 
        on_delete=models.CASCADE, 
        db_column='order_id',
        to_field='order_id',
        help_text="Each order can only have one delivery assignment"
    )
    partner = models.ForeignKey(
        GroceryPartner, 
        on_delete=models.RESTRICT, 
        db_column='partner_id',
        to_field='user_id',
        help_text="Delivery partner assigned to this order"
    )
    assigned_by_user = models.ForeignKey(
        Registration, 
        on_delete=models.RESTRICT, 
        db_column='assigned_by_user_id',
        to_field='user_id',
        help_text="User who assigned this order to the partner"
    )
    assignment_status = models.CharField(
        max_length=20, 
        choices=ASSIGNMENT_STATUS_CHOICES, 
        default='assigned',
        help_text="Current status of the delivery assignment"
    )
    assigned_at = models.DateTimeField(auto_now_add=True)
    delivered_at = models.DateTimeField(null=True, blank=True)
    delivery_otp = models.CharField(
        max_length=6, 
        null=True, 
        blank=True,
        help_text="OTP for delivery verification"
    )
    otp_verified_at = models.DateTimeField(null=True, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'Grocery_deliver_details'
        indexes = [
            models.Index(fields=['partner', 'assignment_status'], name='idx_partner_status'),
        ]

    def __str__(self):
        return f"Delivery {self.delivery_detail_id} - Order {self.order.order_id} - {self.assignment_status}"

    def generate_otp(self):
        """Generate a 6-digit OTP for delivery verification"""
        import random
        import string
        self.delivery_otp = ''.join(random.choices(string.digits, k=6))
        self.save(update_fields=['delivery_otp'])
        return self.delivery_otp
    
    def send_otp_to_customer(self):
        """Send OTP to customer via SMS/Email using robust customer lookup"""
        if not self.delivery_otp:
            self.generate_otp()
        
        message = f"Your delivery OTP is: {self.delivery_otp}. Please share this with the delivery partner to complete your order delivery. Order ID: {self.order.order_id}"
        
        import logging
        logger = logging.getLogger(__name__)
        
        # Use comprehensive raw SQL to get customer details (same as in views)
        customer_details = {}
        try:
            from django.db import connection
            order_id = self.order.order_id
            
            with connection.cursor() as cursor:
                cursor.execute("""
                    SELECT 
                        go.order_id,
                        go.user_id as order_user_id,
                        r.user_id as reg_user_id,
                        r.firstName,
                        r.lastName,
                        r.mobileNumber,
                        r.emailID,
                        r.countryCode
                    FROM Groceries_orders go
                    LEFT JOIN registrations r ON go.user_id = r.user_id
                    WHERE go.order_id = %s
                    LIMIT 1
                """, [order_id])
                
                result = cursor.fetchone()
                
                if result:
                    (order_id_db, order_user_id, reg_user_id, first_name, last_name, 
                     mobile_number, email_id, country_code) = result
                    
                    if reg_user_id and mobile_number and email_id:
                        # Process country code
                        processed_country_code = country_code or '+91'
                        if processed_country_code and not str(processed_country_code).startswith('+'):
                            processed_country_code = f"+{processed_country_code}"
                        
                        customer_details = {
                            'user_id': reg_user_id,
                            'name': ' '.join(filter(None, [first_name or '', last_name or ''])).strip() or 'Customer',
                            'mobile': str(mobile_number).strip() if mobile_number else '',
                            'country_code': processed_country_code,
                            'email': email_id.strip() if email_id else '',
                            'full_phone': f"{processed_country_code}{mobile_number}" if mobile_number else ''
                        }
                        
                        # TODO: Integrate with actual SMS/Email service here
                        # Example integrations:
                        # - SMS: Twilio, AWS SNS, etc.
                        # - Email: SendGrid, AWS SES, etc.
                        
                        logger.info(f"[SMS/Email] OTP {self.delivery_otp} should be sent to:")
                        logger.info(f"  Customer: {customer_details['name']}")
                        logger.info(f"  Phone: {customer_details['full_phone']}")
                        logger.info(f"  Email: {customer_details['email']}")
                        logger.info(f"  Message: {message}")
                        
                        return {
                            'otp_sent': True,
                            'method': 'SMS/Email',
                            'customer_phone': customer_details['full_phone'],
                            'customer_email': customer_details['email'],
                            'customer_name': customer_details['name'],
                            'message': message,
                            'otp': self.delivery_otp
                        }
                    else:
                        logger.warning(f"[SMS/Email] Incomplete customer data for order {order_id}: reg_user_id={reg_user_id}, mobile={mobile_number}, email={email_id}")
                else:
                    logger.warning(f"[SMS/Email] No order found for order_id {order_id}")
                    
        except Exception as e:
            logger.error(f"[SMS/Email] Error fetching customer details for order {self.order.order_id}: {e}")
        
        # Fallback response when customer details are not available
        logger.info(f"[SMS/Email] OTP {self.delivery_otp} generated for order {self.order.order_id} but customer contact not available")
        return {
            'otp_sent': False,
            'method': 'SMS/Email',
            'customer_phone': 'N/A',
            'customer_email': 'N/A',
            'message': message,
            'otp': self.delivery_otp,
            'error': 'Customer contact details not available'
        }

    def verify_otp(self, otp):
        """Verify the provided OTP and mark as verified if correct"""
        if self.delivery_otp == otp:
            self.otp_verified_at = datetime.now()
            self.save(update_fields=['otp_verified_at'])
            return True
        return False

    def mark_delivered(self):
        """Mark the delivery as completed"""
        self.assignment_status = 'delivered'
        self.delivered_at = datetime.now()
        self.save(update_fields=['assignment_status', 'delivered_at'])

    def can_update_status(self, new_status):
        """Check if status transition is valid"""
        valid_transitions = {
            'assigned': ['accepted', 'picked_up', 'out_for_delivery', 'delivered', 'cancelled'],
            'accepted': ['picked_up', 'out_for_delivery', 'delivered', 'cancelled'],
            'picked_up': ['in_transit', 'out_for_delivery', 'delivered', 'cancelled'],
            'in_transit': ['delivered', 'cancelled'],
            'delivered': [],  # Final state
            'cancelled': [],  # Final state
        }
        return new_status in valid_transitions.get(self.assignment_status, [])


class GroceriesRatingHistory(models.Model):
    """Maps to existing table Groceries_ratings_history for product rating history."""
    RATING_CHOICES = [(i, str(i)) for i in range(1, 6)]

    rating_id = models.BigAutoField(primary_key=True)
    user = models.ForeignKey(Registration, on_delete=models.CASCADE, db_column='user_id', to_field='user_id')
    product = models.ForeignKey(GroceriesProducts, on_delete=models.CASCADE, db_column='product_id', to_field='product_id')
    order = models.ForeignKey(GroceriesOrders, on_delete=models.CASCADE, db_column='order_id', to_field='order_id', null=True, blank=True)
    business = models.ForeignKey(Business, on_delete=models.CASCADE, db_column='business_id', to_field='business_id')
    rating = models.IntegerField(choices=RATING_CHOICES)
    review_title = models.CharField(max_length=200, null=True, blank=True)
    review_text = models.TextField(null=True, blank=True)
    is_verified_purchase = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    helpful_count = models.IntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'Groceries_ratings_history'
        managed = False  # Table already exists in DB; avoid migrations
        indexes = [
            models.Index(fields=['product', 'rating'], name='idx_product_rating_hist'),
            models.Index(fields=['user', 'created_at'], name='idx_user_rating_date_hist'),
            models.Index(fields=['business', 'rating'], name='idx_business_rating_hist'),
            models.Index(fields=['is_active', 'is_verified_purchase'], name='idx_active_verified_hist'),
        ]
        constraints = [
            models.UniqueConstraint(fields=['user', 'product', 'order'], name='unique_user_product_order_hist'),
            models.CheckConstraint(check=models.Q(rating__gte=1) & models.Q(rating__lte=5), name='chk_hist_rating_range'),
        ]

    def __str__(self):
        return f"Rating {self.rating_id}: U{self.user_id}-P{self.product_id}-O{getattr(self.order, 'order_id', None)} -> {self.rating}"

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        try:
            self._update_product_average_rating()
        except Exception:
            # Avoid raising during save if aggregation fails
            pass

    def delete(self, *args, **kwargs):
        super().delete(*args, **kwargs)
        try:
            self._update_product_average_rating()
        except Exception:
            pass

    def _update_product_average_rating(self):
        """Recalculate and update the product.rating as the average of active ratings (1 decimal)."""
        from django.db.models import Avg
        # Compute average on active ratings only
        qs = GroceriesRatingHistory.objects.filter(product=self.product, is_active=True)
        avg_val = qs.aggregate(avg=Avg('rating')).get('avg')
        if avg_val is not None:
            try:
                # Round to 1 decimal place to match product.rating field
                rounded = round(float(avg_val), 1)
                # Cap within [1.0, 5.0]
                if rounded < 1.0:
                    rounded = 1.0
                if rounded > 5.0:
                    rounded = 5.0
                self.product.rating = rounded
                self.product.save(update_fields=['rating', 'updated_at'])
            except Exception:
                pass


class BusinessFeedback(models.Model):
    """Maps to existing table business_feedback for per-question business feedback."""
    feedback_id = models.BigAutoField(primary_key=True)
    business = models.ForeignKey(
        Business,
        on_delete=models.CASCADE,
        db_column='business_id',
        to_field='business_id',
        related_name='feedback_entries'
    )
    user = models.ForeignKey(
        Registration,
        on_delete=models.CASCADE,
        db_column='user_id',
        to_field='user_id',
        related_name='feedback_entries'
    )
    user_name = models.CharField(max_length=200)
    email = models.CharField(max_length=255, null=True, blank=True)
    question = models.CharField(max_length=255)
    rating = models.PositiveSmallIntegerField()
    additional_comments = models.TextField(null=True, blank=True)
    created_at = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = 'business_feedback'
        managed = False  # Table already exists in DB
        indexes = [
            models.Index(fields=['business'], name='idx_business_id'),
            models.Index(fields=['user'], name='idx_user_id'),
        ]
