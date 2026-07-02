from django.db import models
from kirazee_app.models import Business, Registration


class BusinessTaxInvoice(models.Model):
    invoice_id = models.BigAutoField(primary_key=True)
    business_id = models.ForeignKey(
        Business,
        on_delete=models.CASCADE,
        to_field='business_id',
        db_column='business_id',
    )
    business_name = models.CharField(max_length=255)
    business_address = models.TextField(null=True, blank=True)
    customer_details = models.TextField(null=True, blank=True)
    invoice_number = models.CharField(max_length=100)
    invoice_date = models.DateField(null=True, blank=True)
    due_date = models.DateField(null=True, blank=True)
    billing_address = models.TextField(null=True, blank=True)
    shipping_address = models.TextField(null=True, blank=True)
    place_of_supply = models.CharField(max_length=150, null=True, blank=True)
    items = models.JSONField()
    total_taxable_value = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    total_amount = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    bank_name = models.CharField(max_length=200, null=True, blank=True)
    bank_account_holder = models.CharField(max_length=200, null=True, blank=True)
    bank_account_number = models.CharField(max_length=50, null=True, blank=True)
    bank_ifsc = models.CharField(max_length=20, null=True, blank=True)
    bank_branch = models.CharField(max_length=150, null=True, blank=True)
    source = models.CharField(max_length=50, null=True, blank=True, help_text="Source: POS_sample_invoice, POS_original_invoice, RBO_original_invoice, RBO_sample_invoice")
    reverse_charge = models.CharField(max_length=10, default='No', help_text="Reverse charge applicable: Yes/No")
    state_code = models.CharField(max_length=5, null=True, blank=True, help_text="State code for place of supply")
    cgst_amount = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    sgst_amount = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    igst_amount = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    amount_in_words = models.TextField(null=True, blank=True)
    declaration_text = models.TextField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'business_tax_invoice'
        managed = False
        unique_together = (('business_id', 'invoice_number'),)

    def __str__(self):
        return f"Invoice {self.invoice_number} - {self.business_id.business_id}"


class Suppliers(models.Model):
    """Maps to the existing `Suppliers` table"""
    
    STATUS_CHOICES = [
        ('Active', 'Active'),
        ('Inactive', 'Inactive'),
        ('Blacklisted', 'Blacklisted'),
    ]
    
    supplier_id = models.BigAutoField(primary_key=True)
    business_id = models.ForeignKey(
        Business,
        on_delete=models.CASCADE,
        to_field='business_id',
        db_column='business_id',
    )
    supplier_code = models.CharField(max_length=50, null=True, blank=True)
    supplier_name = models.CharField(max_length=255)
    contact_person = models.CharField(max_length=255, null=True, blank=True)
    email = models.CharField(max_length=255, null=True, blank=True)
    phone = models.CharField(max_length=20, null=True, blank=True)
    address = models.TextField(null=True, blank=True)
    city = models.CharField(max_length=100, null=True, blank=True)
    state = models.CharField(max_length=100, null=True, blank=True)
    country = models.CharField(max_length=100, null=True, blank=True)
    postal_code = models.CharField(max_length=20, null=True, blank=True)
    product_supplied = models.TextField(null=True, blank=True)
    payment_terms = models.CharField(max_length=255, null=True, blank=True)
    bank_details_id = models.BigIntegerField(null=True, blank=True)
    gst_number = models.CharField(max_length=50, null=True, blank=True)
    tax_percentage = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='Active')
    notes = models.TextField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'Suppliers'
        managed = False

    def __str__(self):
        return f"{self.supplier_name} ({self.supplier_code or self.supplier_id})"


class SupplierBankDetails(models.Model):
    bank_details_id = models.BigAutoField(primary_key=True)
    supplier_id = models.ForeignKey(
        Suppliers,
        on_delete=models.CASCADE,
        db_column='supplier_id',
        related_name='bank_details',
    )
    business_id = models.ForeignKey(
        Business,
        on_delete=models.CASCADE,
        to_field='business_id',
        db_column='business_id',
    )
    bank_name = models.CharField(max_length=255)
    account_holder_name = models.CharField(max_length=255)
    account_number = models.CharField(max_length=50)
    ifsc_code = models.CharField(max_length=20, null=True, blank=True)
    branch_name = models.CharField(max_length=255, null=True, blank=True)
    upi_id = models.CharField(max_length=100, null=True, blank=True)
    is_primary = models.BooleanField(default=True)
    status = models.CharField(max_length=8, default='Active')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'supplier_bank_details'
        managed = False


class Purchases(models.Model):
    """Maps to the existing `Purchases` table"""
    purchase_id = models.BigAutoField(primary_key=True)
    business_id = models.ForeignKey(
        Business,
        on_delete=models.CASCADE,
        to_field='business_id',
        db_column='business_id',
    )
    # Note: DB references registrations(id), so FK points to Registration PK
    user_id = models.ForeignKey(
        Registration,
        on_delete=models.RESTRICT,
        db_column='user_id',
    )
    supplier_id = models.ForeignKey(
        Suppliers,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        db_column='supplier_id',
    )
    invoice_number = models.CharField(max_length=100, null=True, blank=True)
    total_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    payment_status = models.CharField(max_length=20, default='unpaid')
    payment_method = models.CharField(max_length=50, null=True, blank=True)
    purchase_date = models.DateField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'Purchases'
        managed = False
        ordering = ['-purchase_date', '-created_at']

    def __str__(self):
        return f"Purchase #{self.purchase_id} - {self.business_id_id}"


class Purchase_Items(models.Model):
    """Maps to the existing `Purchase_Items` table"""
    purchase_item_id = models.BigAutoField(primary_key=True)
    purchase_id = models.ForeignKey(
        Purchases,
        on_delete=models.CASCADE,
        db_column='purchase_id',
        related_name='items',
    )
    business_id = models.ForeignKey(
        Business,
        on_delete=models.CASCADE,
        to_field='business_id',
        db_column='business_id',
    )
    user_id = models.ForeignKey(
        Registration,
        on_delete=models.RESTRICT,
        db_column='user_id',
    )
    sku = models.CharField(max_length=100, null=True, blank=True)
    reference_table = models.CharField(max_length=50)
    reference_id = models.BigIntegerField()
    item_name = models.CharField(max_length=255)
    unit = models.CharField(max_length=50, null=True, blank=True)
    mfg_date = models.DateField(null=True, blank=True)
    exp_date = models.DateField(null=True, blank=True)
    quantity = models.IntegerField(default=0)
    cost_price = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    selling_price = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    # Generated column in DB: quantity * cost_price
    total_cost = models.DecimalField(max_digits=12, decimal_places=2, editable=False)
    category = models.CharField(max_length=100, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'Purchase_Items'
        managed = False

    def __str__(self):
        return f"{self.item_name} x{self.quantity} (@{self.cost_price})"


class Inventory(models.Model):
    """Maps to the existing `Inventory` table"""
    inventory_id = models.BigAutoField(primary_key=True)
    business_id = models.ForeignKey(
        Business,
        on_delete=models.CASCADE,
        to_field='business_id',
        db_column='business_id',
    )
    user_id = models.ForeignKey(
        Registration,
        on_delete=models.RESTRICT,
        db_column='user_id',
    )
    sku = models.CharField(max_length=100, null=True, blank=True)
    reference_table = models.CharField(max_length=50)
    reference_id = models.BigIntegerField()
    item_name = models.CharField(max_length=255)
    type = models.CharField(max_length=50)
    unit = models.CharField(max_length=50, null=True, blank=True)
    opening_stock = models.IntegerField(default=0)
    purchased_stock = models.IntegerField(default=0)
    sold_stock = models.IntegerField(default=0)
    # Generated column in DB
    current_stock = models.IntegerField(editable=False)
    last_updated = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'Inventory'
        managed = False
        unique_together = (('business_id', 'reference_table', 'reference_id'),)

    def __str__(self):
        return f"{self.item_name} ({self.reference_table}:{self.reference_id}) - {self.current_stock} {self.unit or ''}"


class Inventory_Log(models.Model):
    """Maps to the existing `Inventory_Log` table"""
    log_id = models.BigAutoField(primary_key=True)
    inventory_id = models.ForeignKey(
        Inventory,
        on_delete=models.CASCADE,
        db_column='inventory_id',
        related_name='logs',
    )
    business_id = models.ForeignKey(
        Business,
        on_delete=models.CASCADE,
        to_field='business_id',
        db_column='business_id',
    )
    sku = models.CharField(max_length=100, null=True, blank=True)
    reference_table = models.CharField(max_length=50)
    reference_id = models.BigIntegerField()
    item_name = models.CharField(max_length=255)
    action = models.CharField(max_length=20)
    edit_reason = models.CharField(max_length=255, null=True, blank=True)
    reason = models.TextField(null=True, blank=True)
    old_stock = models.JSONField(null=True, blank=True)
    new_stock = models.JSONField(null=True, blank=True)
    user_id = models.ForeignKey(
        Registration,
        on_delete=models.RESTRICT,
        db_column='user_id',
    )
    changed_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'Inventory_Log'
        managed = False
        ordering = ['-changed_at']

    def __str__(self):
        return f"InventoryLog #{self.log_id} {self.action} {self.item_name}"


class Purchase_Log(models.Model):
    """Maps to the existing `Purchase_Log` table"""
    log_id = models.BigAutoField(primary_key=True)
    purchase_id = models.ForeignKey(
        Purchases,
        on_delete=models.CASCADE,
        db_column='purchase_id',
        related_name='logs',
    )
    # business_id = models.ForeignKey(
    #     Business,
    #     on_delete=models.CASCADE,
    #     to_field='business_id',
    #     db_column='business_id',
    # )
    action = models.CharField(max_length=20)
    action_table = models.CharField(max_length=50)
    reason = models.TextField(null=True, blank=True)
    old_data = models.JSONField(null=True, blank=True)
    new_data = models.JSONField(null=True, blank=True)
    user_id = models.ForeignKey(
        Registration,
        on_delete=models.RESTRICT,
        db_column='user_id',
    )
    changed_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'Purchase_Log'
        managed = False
        ordering = ['-changed_at']

    def __str__(self):
        return f"PurchaseLog #{self.log_id} {self.action} Purchase {self.purchase_id_id}"


class Expenses(models.Model):
    """Maps to the existing `Expenses` table"""
    expense_id = models.BigAutoField(primary_key=True)
    business_id = models.ForeignKey(
        Business,
        on_delete=models.CASCADE,
        to_field='business_id',
        db_column='business_id',
    )
    user_id = models.ForeignKey(
        Registration,
        on_delete=models.RESTRICT,
        db_column='user_id',
    )
    supplier_id = models.ForeignKey(
        Suppliers,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        db_column='supplier_id',
    )
    category = models.CharField(max_length=100)
    description = models.TextField(null=True, blank=True)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    payment_method = models.CharField(max_length=50, null=True, blank=True)
    payment_status = models.CharField(max_length=20, default='unpaid')
    expense_date = models.DateField()
    receipt_path = models.CharField(max_length=255, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'Expenses'
        managed = False
        ordering = ['-expense_date', '-created_at']

    def __str__(self):
        return f"Expense #{self.expense_id} - {self.category} - {self.amount}"


class Expenses_Log(models.Model):
    """Maps to the existing `Expenses_Log` table"""
    log_id = models.BigAutoField(primary_key=True)
    expense_id = models.ForeignKey(
        Expenses,
        on_delete=models.CASCADE,
        db_column='expense_id',
        related_name='logs',
    )
    action = models.CharField(max_length=10)
    old_data = models.JSONField(null=True, blank=True)
    new_data = models.JSONField(null=True, blank=True)
    reason = models.TextField(null=True, blank=True)
    user_id = models.ForeignKey(
        Registration,
        on_delete=models.RESTRICT,
        db_column='user_id',
    )
    changed_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'Expenses_Log'
        managed = False
        ordering = ['-changed_at']

    def __str__(self):
        return f"ExpenseLog #{self.log_id} {self.action} Expense {self.expense_id_id}"


class Counter_Sales_Details(models.Model):
    """Maps to the existing `counter_sales_details` table"""
    id = models.BigAutoField(primary_key=True)
    business_id = models.ForeignKey(
        Business,
        on_delete=models.CASCADE,
        to_field='business_id',
        db_column='business_id',
    )
    uploaded_by = models.ForeignKey(
        Registration,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        db_column='uploaded_by',
    )
    bill_no = models.CharField(max_length=100, null=True, blank=True)
    product_name = models.CharField(max_length=255)
    customer_name = models.CharField(max_length=255, null=True, blank=True)
    payment_method = models.CharField(max_length=100, null=True, blank=True)
    quantity = models.IntegerField(default=1)
    net_weight = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    price = models.DecimalField(max_digits=10, decimal_places=2)
    # Generated column in DB: quantity * price
    total_amount = models.DecimalField(max_digits=10, decimal_places=2, editable=False)
    discount = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    tax = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    # Generated column in DB: (quantity * price) - discount + tax
    grand_total = models.DecimalField(max_digits=10, decimal_places=2, editable=False)
    sale_date = models.DateField()
    remarks = models.TextField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'counter_sales_details'
        managed = False
        ordering = ['-sale_date', '-created_at']

    def __str__(self):
        return f"Sale #{self.id} - {self.product_name} - {self.customer_name or 'Takeaway'}"


class BusinessStaff(models.Model):
    """Maps to the `business_staff` table"""
    
    ROLE_CHOICES = [
        ('Manager', 'Manager'),
        ('Admin', 'Admin'),
        ('Employee', 'Employee'),
        ('Assistant Manager', 'Assistant Manager'),
        ('Team Lead', 'Team Lead'),
        ('Supervisor', 'Supervisor'),
        ('Senior Employee', 'Senior Employee'),
        ('Junior Employee', 'Junior Employee'),
        ('Trainee', 'Trainee'),
        ('Intern', 'Intern'),
        ('Cashier', 'Cashier'),
        ('Sales Associate', 'Sales Associate'),
        ('Store Keeper', 'Store Keeper'),
        ('Accountant', 'Accountant'),
        ('HR Executive', 'HR Executive'),
        ('Marketing Executive', 'Marketing Executive'),
        ('Customer Service', 'Customer Service'),
        ('Security Guard', 'Security Guard'),
        ('Cleaner', 'Cleaner'),
        ('Driver', 'Driver'),
    ]
    
    staff_id = models.BigAutoField(primary_key=True)
    business_id = models.ForeignKey(
        Business,
        on_delete=models.CASCADE,
        to_field='business_id',
        db_column='business_id',
    )
    first_name = models.CharField(max_length=100)
    last_name = models.CharField(max_length=100)
    role = models.CharField(max_length=100, choices=ROLE_CHOICES)
    email = models.EmailField(max_length=255, unique=True, null=True, blank=True)
    phone = models.CharField(max_length=15, null=True, blank=True)
    mobile_number = models.CharField(max_length=15, unique=True, null=True, blank=True)
    password_hash = models.CharField(max_length=255, null=True, blank=True)
    otp_code = models.CharField(max_length=6, null=True, blank=True)
    otp_expires_at = models.DateTimeField(null=True, blank=True)
    last_login = models.DateTimeField(null=True, blank=True)
    login_method = models.CharField(max_length=20, null=True, blank=True)
    nav_items = models.JSONField(null=True, blank=True)
    join_date = models.DateField(db_column='join_date')
    status = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'business_staff'
        managed = False
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.first_name} {self.last_name} ({self.role})"

    @property
    def full_name(self):
        return f"{self.first_name} {self.last_name}"


class RoleBasedNavItems(models.Model):
    """Maps to the `role_based_nav_items` table"""
    
    id = models.AutoField(primary_key=True)
    nav_name = models.CharField(max_length=100)
    sub_nav = models.CharField(max_length=100, null=True, blank=True)
    status = models.BooleanField(default=True)
    is_visible = models.BooleanField(default=True)
    parent = models.ForeignKey(
        'self',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        db_column='parent_id',
        related_name='children'
    )
    order_index = models.IntegerField(default=0)
    icon = models.CharField(max_length=50, null=True, blank=True)
    route_path = models.CharField(max_length=200, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'role_based_nav_items'
        managed = False
        ordering = ['order_index', 'nav_name']

    def __str__(self):
        return f"{self.nav_name} ({self.sub_nav or 'Main'})"


class StaffLoginLogs(models.Model):
    """Maps to the `staff_login_logs` table"""
    
    LOGIN_METHOD_CHOICES = [
        ('OTP', 'OTP'),
        ('PASSWORD', 'PASSWORD'),
    ]
    
    LOGIN_STATUS_CHOICES = [
        ('SUCCESS', 'SUCCESS'),
        ('FAILED', 'FAILED'),
        ('LOGOUT', 'LOGOUT'),
    ]
    
    log_id = models.BigAutoField(primary_key=True)
    staff_id = models.ForeignKey(
        BusinessStaff,
        on_delete=models.CASCADE,
        db_column='staff_id',
        related_name='login_logs',
    )
    business_id = models.ForeignKey(
        Business,
        on_delete=models.CASCADE,
        to_field='business_id',
        db_column='business_id',
    )
    login_method = models.CharField(max_length=20, choices=LOGIN_METHOD_CHOICES)
    login_time = models.DateTimeField(auto_now_add=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(null=True, blank=True)
    login_status = models.CharField(max_length=20, choices=LOGIN_STATUS_CHOICES, default='SUCCESS')
    failure_reason = models.CharField(max_length=255, null=True, blank=True)
    logout_time = models.DateTimeField(null=True, blank=True)
    session_duration_minutes = models.IntegerField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'staff_login_logs'
        managed = False
        ordering = ['-login_time']

    def __str__(self):
        return f"LoginLog #{self.log_id} - {self.staff_id.full_name} ({self.login_method})"


# BusinessStaffSalaries model removed - using BusinessStaffSalaryPayments instead
# class BusinessStaffSalaries(models.Model):
#     """Maps to the `business_staff_salaries` table"""
#     
#     salary_id = models.BigAutoField(primary_key=True)
#     staff_id = models.ForeignKey(
#         BusinessStaff,
#         on_delete=models.CASCADE,
#         db_column='staff_id',
#         related_name='salaries',
#     )
#     salary_amount = models.DecimalField(max_digits=10, decimal_places=2)
#     effective_from = models.DateField()
#     effective_to = models.DateField(null=True, blank=True)
#     status = models.BooleanField(default=True)
#     created_at = models.DateTimeField(auto_now_add=True)
#     updated_at = models.DateTimeField(auto_now=True)
# 
#     class Meta:
#         db_table = 'business_staff_salaries'
#         managed = True
#         ordering = ['-effective_from']
# 
#     def __str__(self):
#         return f"{self.staff_id.full_name} - ₹{self.salary_amount} (from {self.effective_from})"


class BusinessStaffAttendance(models.Model):
    attendance_id = models.BigAutoField(primary_key=True)
    staff_id = models.ForeignKey(
        BusinessStaff,
        on_delete=models.CASCADE,
        db_column='staff_id',
        related_name='attendance_records',
    )
    business_id = models.ForeignKey(
        Business,
        on_delete=models.CASCADE,
        to_field='business_id',
        db_column='business_id',
    )
    attendance_date = models.DateField()
    attendance_status = models.CharField(max_length=20, default='Present')
    marked_by = models.ForeignKey(
        BusinessStaff,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        db_column='marked_by',
        related_name='marked_attendance',
    )
    check_in = models.TimeField(null=True, blank=True)
    check_out = models.TimeField(null=True, blank=True)
    working_hours = models.DecimalField(max_digits=5, decimal_places=2, editable=False)
    remarks = models.CharField(max_length=255, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'business_staff_attendance'
        managed = False
        ordering = ['-attendance_date', '-created_at']


class BusinessStaffSalaryPayments(models.Model):
    payment_id = models.BigAutoField(primary_key=True)
    staff_id = models.ForeignKey(
        BusinessStaff,
        on_delete=models.CASCADE,
        db_column='staff_id',
        related_name='salary_payments',
    )
    business_id = models.ForeignKey(
        Business,
        on_delete=models.CASCADE,
        to_field='business_id',
        db_column='business_id',
    )
    year = models.IntegerField()
    month = models.PositiveSmallIntegerField()
    salary_amount = models.DecimalField(max_digits=10, decimal_places=2)
    salary_paid = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    is_paid = models.BooleanField(default=False)
    remarks = models.CharField(max_length=255, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'business_staff_salary_payments'
        managed = False
        ordering = ['-year', '-month']


class NavDisplayItem(models.Model):
    """Items to display within each navigation page (e.g., Business Settings items)"""
    id = models.AutoField(primary_key=True)
    nav_item = models.ForeignKey(
        'RoleBasedNavItems',
        on_delete=models.CASCADE,
        related_name='display_items'
    )
    parent_item = models.ForeignKey(
        'self',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='children'
    )
    
    label = models.CharField(max_length=255)
    key = models.CharField(max_length=100, help_text="Unique key for the feature, e.g., 'delivery_charges'")
    route_path = models.CharField(max_length=255, null=True, blank=True)
    order_index = models.IntegerField(default=0)
    
    # Feature flags
    is_premium = models.BooleanField(default=False)
    price = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    is_new_feature = models.BooleanField(default=False)
    description = models.TextField(null=True, blank=True)
    expiry_days = models.IntegerField(null=True, blank=True, help_text="Days after purchase this feature expires")
    
    status = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'nav_display_items'
        unique_together = ('nav_item', 'key')
        ordering = ['order_index']

    def __str__(self):
        return f"{self.nav_item.nav_name} - {self.label}"


class BusinessFeaturePurchase(models.Model):
    """Track premium feature purchases per business"""
    purchase_id = models.BigAutoField(primary_key=True)
    business_id = models.ForeignKey(
        'kirazee_app.Business',
        on_delete=models.CASCADE,
        to_field='business_id',
        db_column='business_id'
    )
    feature_key = models.CharField(max_length=100, help_text="Matches NavDisplayItem.key")
    purchased_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField(null=True, blank=True)
    amount_paid = models.DecimalField(max_digits=10, decimal_places=2)
    status = models.CharField(
        max_length=20,
        choices=[
            ('PENDING', 'Pending'),
            ('ACTIVE', 'Active'),
            ('EXPIRED', 'Expired'),
            ('FAILED', 'Failed')
        ],
        default='PENDING'
    )
    payment_id = models.ForeignKey(
        'business.BusinessPayment',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        db_column='payment_id'
    )

    class Meta:
        db_table = 'business_feature_purchases'
        unique_together = ('business_id', 'feature_key')
        ordering = ['-purchased_at']

    def __str__(self):
        return f"Feature {self.feature_key} for Business {self.business_id.business_id} ({self.status})"

    def is_active(self):
        from django.utils import timezone
        return (
            self.status == 'ACTIVE' and
            (self.expires_at is None or self.expires_at > timezone.now())
        )


class PurchaseRequisition(models.Model):
    """Simplified Purchase Requisition model"""
    
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
    ]
    
    SUBMISSION_CHOICES = [
        ('draft', 'Draft'),
        ('submitted', 'Submitted'),
    ]
    
    purchase_req_id = models.BigAutoField(primary_key=True)
    requisition_number = models.CharField(max_length=100, unique=True)
    business_id = models.ForeignKey(
        Business,
        on_delete=models.CASCADE,
        to_field='business_id',
        db_column='business_id',
    )
    user_id = models.ForeignKey(
        Registration,
        on_delete=models.CASCADE,
        to_field='user_id',
        db_column='user_id',
    )
    item_name = models.CharField(max_length=255)
    quantity = models.IntegerField()
    unit = models.CharField(max_length=50, default='pieces')
    purpose = models.TextField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    submitted_to_manager = models.CharField(max_length=20, choices=SUBMISSION_CHOICES, default='draft')
    request_date = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'purchase_requisitions'
        managed = False
        ordering = ['-request_date']

    def __str__(self):
        return f"{self.requisition_number} - {self.item_name}"


class PurchaseRequisitionLog(models.Model):
    """Audit log for purchase requisitions"""
    
    ACTION_CHOICES = [
        ('requested', 'Requested'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
    ]
    
    log_id = models.BigAutoField(primary_key=True)
    requisition = models.ForeignKey(
        PurchaseRequisition,
        on_delete=models.CASCADE,
        to_field='purchase_req_id',
        db_column='requisition_id',
        related_name='logs'
    )
    business_id = models.ForeignKey(
        Business,
        on_delete=models.CASCADE,
        to_field='business_id',
        db_column='business_id',
    )
    action = models.CharField(max_length=20, choices=ACTION_CHOICES)
    action_by = models.ForeignKey(
        Registration,
        on_delete=models.CASCADE,
        to_field='user_id',
        db_column='user_id',
        related_name='requisition_actions'
    )
    action_date = models.DateTimeField(auto_now_add=True)
    reason = models.TextField(null=True, blank=True)
    
    class Meta:
        db_table = 'purchase_requisition_log'
        managed = False
        ordering = ['-action_date']

    def __str__(self):
        return f"{self.requisition.requisition_number} - {self.action} by {self.action_by}"

