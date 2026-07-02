# models.py
from django.db import models
from django.db.models.fields.files import FieldFile
from kirazee_app.models import Business, Registration
from datetime import datetime
from django.db.models.signals import pre_save, post_save, pre_delete, post_delete
from django.dispatch import receiver
import decimal
import datetime as dt
from django.utils import timezone
from consumer.gro_models import GroceriesProducts

class CountryandStates(models.Model):
    country = models.TextField()
    state = models.TextField()
    district = models.TextField()
    taluk = models.TextField()
    pincode = models.TextField()
    status = models.IntegerField(default=1)
    
    class Meta:
        db_table = 'CountryandStates'
    
    def __str__(self):
        return f"{self.country} - {self.state} - {self.district} - {self.taluk}"
    
class BusinessPayment(models.Model):
    id = models.BigAutoField(primary_key=True)
    transaction_id = models.CharField(max_length=100, null=True, blank=True)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    currency = models.CharField(max_length=10, default='INR')
    payment_method = models.CharField(max_length=50, null=True, blank=True)
    status = models.CharField(max_length=50)
    refund_status = models.CharField(max_length=50, null=True, blank=True)
    refund_id = models.CharField(max_length=100, null=True, blank=True)
    upi_id = models.CharField(max_length=100, null=True, blank=True)
    payment_type = models.CharField(max_length=50, null=True, blank=True)
    
    payment_source = models.CharField(max_length=100, null=True, blank=True)
    business_id = models.ForeignKey(Business, on_delete=models.CASCADE, to_field='business_id', db_column='business_id')
    user_id = models.ForeignKey(Registration, on_delete=models.CASCADE, to_field='user_id', db_column='user_id')
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'business_payments'

def menu_item_upload_path(instance, filename):
    """Generate upload path for menu item images - stored in menuItems folder"""
    timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
    ext = filename.split('.')[-1]
    # Store menu items (R02 business type) in menuItems folder (matching existing folder name)
    # Note: Django ImageField upload_to is relative to MEDIA_ROOT, so we return path without 'media/' prefix
    # The path will be stored in database as 'menuItems/...' and serializer will add 'media/' when building URLs
    
    # Handle case where item_id might not be set yet (during initial file upload)
    # Generate item_id on the fly if not available
    if instance.item_id is None or instance.item_id == 0:
        # Get the next item_id by querying the last item
        # This ensures we generate a valid ID even before save() is called
        last_item = MenuItems.objects.order_by('-item_id').first()
        if last_item:
            item_id = last_item.item_id + 1
        else:
            item_id = 182250
    else:
        item_id = instance.item_id
    
    return f'menuItems/{item_id}_{timestamp}.{ext}'

class MenuItems(models.Model):
    item_id = models.BigAutoField(primary_key=True)
    business_id = models.ForeignKey(Business, on_delete=models.CASCADE, to_field='business_id', db_column='business_id')
    item_name = models.CharField(max_length=255)
    size_label = models.CharField(max_length=225)
    sku = models.CharField(max_length=255, blank=True, null=True)
    description = models.TextField(null=True, blank=True)
    item_image = models.ImageField(upload_to=menu_item_upload_path, null=True, blank=True)
    item_category = models.CharField(max_length=100, null=True, blank=True)
    category_id = models.BigIntegerField(db_column='item_category_id', null=True, blank=True)
    sub_category_id = models.BigIntegerField(db_column='sub_category_id', null=True, blank=True)
    sub_category = models.CharField(max_length=100, null=True, blank=True)
    item_type = models.CharField(max_length=100, null=True, blank=True)
    availability_timings = models.JSONField(null=True, blank=True)
    preparation_time = models.CharField(max_length=50, null=True, blank=True)
    quantity = models.IntegerField(null=True, blank=True)
    rating = models.DecimalField(max_digits=3, decimal_places=2, null=True, blank=True, default=4.0)
    original_cost = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    gst = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True, help_text="GST percentage")
    charges = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True, help_text="Calculated GST amount")
    selling_price = models.DecimalField(max_digits=10, decimal_places=2)
    is_active = models.BooleanField(default=True)
    is_customizable = models.BooleanField(default=False)
    is_featured = models.BooleanField(default=False, help_text="Mark menu item as featured")
    is_variable = models.BooleanField(default=False, help_text="Item has multiple size variants")
    status = models.BooleanField(default=True)
    is_visible = models.IntegerField(default=1)
    is_visible_counter = models.IntegerField(default=1)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'menuItems'
        ordering = ['item_name']

    def save(self, *args, **kwargs):
        # Auto-generate SKU if not providedF
        if not self.sku:
            self.sku = self._generate_sku()
        
        # Calculate GST charges if original_cost and gst are provided
        if self.original_cost and self.gst:
            # Ensure both values are Decimal for multiplication
            from decimal import Decimal
            original_cost = Decimal(str(self.original_cost)) if not isinstance(self.original_cost, Decimal) else self.original_cost
            gst = Decimal(str(self.gst)) if not isinstance(self.gst, Decimal) else self.gst
            self.charges = (original_cost * gst) / 100
        
        if self.is_active is None:
            self.is_active = True
        if self.status is None:
            self.status = True

        # Set custom item_id starting from 182250 if not set
        if not self.item_id:
            last_item = MenuItems.objects.order_by('-item_id').first()
            if last_item:
                self.item_id = last_item.item_id + 1
            else:
                self.item_id = 182250
        
        super().save(*args, **kwargs)
        
        # For variable items, update base_price to lowest variant price
        if self.is_variable and hasattr(self, 'variants'):
            lowest_price = self.variants.filter(is_active=True).order_by('selling_price').first()
            if lowest_price and lowest_price.selling_price != self.selling_price:
                self.selling_price = lowest_price.selling_price
                super().save(update_fields=['selling_price'])
    
    def _generate_sku(self):
        """Generate SKU from item_name only"""
        import re
        # Clean item name: remove special chars, convert to lowercase
        clean_name = re.sub(r'[^a-zA-Z0-9\s]', '', self.item_name or '')
        sku = clean_name.lower().replace(' ', '')
        
        # Ensure uniqueness by checking existing SKUs
        base_sku = sku
        counter = 1
        while MenuItems.objects.filter(sku=sku).exclude(item_id=self.item_id).exists():
            sku = f"{base_sku}_{counter}"
            counter += 1
        
        return sku

    def __str__(self):
        return self.item_name


class MenuItemVariant(models.Model):
    variant_id = models.BigAutoField(primary_key=True)
    item = models.ForeignKey(MenuItems, on_delete=models.CASCADE, related_name='variants')
    size_label = models.CharField(max_length=50, default='Regular')
    sku = models.CharField(max_length=100, blank=True, null=True)
    selling_price = models.DecimalField(max_digits=10, decimal_places=2)
    mrp = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    original_cost = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    stock_qty = models.IntegerField(null=True, blank=True)
    rating = models.DecimalField(max_digits=3, decimal_places=2, null=True, blank=True, default=4.0)
    rating_count = models.IntegerField(null=True, blank=True, default=0)
    charges = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    gst = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'menu_item_variants'
        constraints = [
            models.UniqueConstraint(fields=['item', 'size_label'], name='uq_menu_item_size')
        ]
    
    def save(self, *args, **kwargs):
        # Auto-generate SKU if not provided
        if not self.sku:
            self.sku = self._generate_sku()
        
        # Calculate charges if gst and original_cost are provided
        if self.original_cost and self.gst:
            self.charges = (self.original_cost * self.gst) / 100
        
        super().save(*args, **kwargs)
    
    def _generate_sku(self):
        """Generate SKU: ITEMID-SIZE-BUSSID"""
        import re
        clean_size = re.sub(r'[^a-zA-Z0-9]', '', self.size_label).upper()
        return f"{self.item.item_id}-{clean_size}-{self.item.business_id.business_id}"

    def __str__(self):
        return f"{self.item.item_name} - {self.size_label}"


# =============================
# Onboarding Data Models
# =============================

def onboarding_document_upload_path(instance, filename):
    """Upload path for onboarding documents: onboarding_docs/<application_id>/<document_id>.<ext>"""
    try:
        ext = filename.split('.')[-1]
    except Exception:
        ext = 'bin'
    app_id = None
    try:
        app_id = instance.application.application_id
    except Exception:
        app_id = 'unknown'
    doc_id = instance.document_id or 'doc'
    return f'onboarding_docs/{app_id}/{doc_id}.{ext}'


class BusinessApplication(models.Model):
    id = models.BigAutoField(primary_key=True)
    application_id = models.CharField(max_length=100, unique=True)
    user = models.ForeignKey(Registration, on_delete=models.CASCADE, to_field='user_id', db_column='user_id')
    current_step = models.IntegerField(default=1)
    total_steps = models.IntegerField(default=3)
    status = models.CharField(max_length=50, default='in_progress')  # not_started, in_progress, submitted, approved, rejected, requires_changes
    submitted_at = models.DateTimeField(null=True, blank=True)
    reviewed_at = models.DateTimeField(null=True, blank=True)
    rejection_reasons = models.JSONField(null=True, blank=True)
    last_activity = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'business_applications'
        ordering = ['-created_at']


class ApplicationStep(models.Model):
    id = models.BigAutoField(primary_key=True)
    application = models.ForeignKey(BusinessApplication, on_delete=models.CASCADE, related_name='steps')
    step_number = models.SmallIntegerField()
    step_data = models.JSONField(null=True, blank=True)
    is_completed = models.BooleanField(default=False)
    data_saved = models.BooleanField(default=False)
    completed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'application_steps'
        unique_together = ('application', 'step_number')
        ordering = ['application', 'step_number']


class ApplicationDocument(models.Model):
    id = models.BigAutoField(primary_key=True)
    application = models.ForeignKey(BusinessApplication, on_delete=models.CASCADE, related_name='documents')
    document_id = models.CharField(max_length=50, unique=True)
    document_type = models.CharField(max_length=50)
    file = models.FileField(upload_to=onboarding_document_upload_path, null=True, blank=True)
    file_name = models.CharField(max_length=255, null=True, blank=True)
    file_size = models.BigIntegerField(null=True, blank=True)
    upload_status = models.CharField(max_length=50, default='uploaded')  # uploaded, failed
    verification_status = models.CharField(max_length=50, default='pending')  # pending, verified, rejected
    uploaded_at = models.DateTimeField(auto_now_add=True)
    verified_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = 'application_documents'
        ordering = ['-uploaded_at']


class AdminReview(models.Model):
    id = models.BigAutoField(primary_key=True)
    application = models.ForeignKey(BusinessApplication, on_delete=models.CASCADE, related_name='reviews')
    admin_id = models.CharField(max_length=50)
    action = models.CharField(max_length=20)  # approve, reject, request_changes
    comments = models.TextField(null=True, blank=True)
    rejection_reasons = models.JSONField(null=True, blank=True)
    required_changes = models.JSONField(null=True, blank=True)
    business_id_assignment = models.CharField(max_length=50, null=True, blank=True)
    reviewed_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'admin_reviews'
        ordering = ['-reviewed_at']
        
class BOM(models.Model):
    bom_id = models.BigAutoField(primary_key=True)
    business_id = models.ForeignKey(Business, on_delete=models.CASCADE, to_field='business_id', db_column='business_id')
    product_id = models.ForeignKey(MenuItems, on_delete=models.CASCADE, to_field='item_id', db_column='product_id')
    ingredients = models.CharField(max_length=100)
    quantity = models.DecimalField(max_digits=10, decimal_places=2)
    unit = models.CharField(max_length=10)
    cost = models.DecimalField(max_digits=10, decimal_places=2)
    status = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'bill_of_materials'
        ordering = ['ingredients']
    
    def save(self, *args, **kwargs):
        if self.status is None:
            self.status = True

        # Set custom bom_id starting from 105501 if not set
        if not self.bom_id:
            last_item = BOM.objects.order_by('-bom_id').first()
            if last_item:
                self.bom_id = last_item.bom_id + 1
            else:
                self.bom_id = 105501
        
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.ingredients} for {self.product_id.item_name}"

class BillOfMaterialsLog(models.Model):
    ACTION_CHOICES = [
        ('INSERT', 'Insert'),
        ('UPDATE', 'Update'),
        ('DELETE', 'Delete'),
    ]
    
    log_id = models.BigAutoField(primary_key=True)
    bom_id = models.BigIntegerField()
    user_id = models.BigIntegerField(null=True, blank=True)
    action_type = models.CharField(max_length=10, choices=ACTION_CHOICES)
    old_data = models.JSONField(null=True, blank=True)
    new_data = models.JSONField(null=True, blank=True)
    action_timestamp = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = 'bill_of_materials_log'
        ordering = ['-action_timestamp']
    
    def __str__(self):
        return f"BOM {self.bom_id} - {self.action_type} at {self.action_timestamp}"

class MCPLog(models.Model):
    ACTION_CHOICES = [
        ('INSERT', 'Insert'),
        ('UPDATE', 'Update'),
        ('DELETE', 'Delete'),
    ]
    id = models.BigAutoField(primary_key=True)
    entity_type = models.CharField(max_length=50)
    table_name = models.CharField(max_length=100)
    entity_id = models.CharField(max_length=100)
    business_id = models.CharField(max_length=100, null=True, blank=True)
    user_id = models.BigIntegerField(null=True, blank=True)
    action_type = models.CharField(max_length=10, choices=ACTION_CHOICES)
    old_data = models.JSONField(null=True, blank=True)
    new_data = models.JSONField(null=True, blank=True)
    changed_fields = models.JSONField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'mcp_logs'
        ordering = ['-created_at']

def _serialize_instance(instance):
    data = {}
    for field in instance._meta.concrete_fields:
        name = field.name
        val = getattr(instance, name)
        # Normalize relational fields to their primary key
        if hasattr(field, 'remote_field') and field.remote_field is not None:
            try:
                val = getattr(instance, f"{name}_id")
            except Exception:
                try:
                    val = getattr(val, 'pk', None)
                except Exception:
                    val = None
        if isinstance(val, decimal.Decimal):
            val = str(val)
        elif isinstance(val, (dt.datetime, dt.date, dt.time)):
            val = val.isoformat() if val else None
        elif isinstance(val, FieldFile):
            try:
                # Prefer a URL if available; fall back to stored name
                val = val.url if getattr(val, 'url', None) else (val.name or None)
            except Exception:
                val = val.name if getattr(val, 'name', None) else None
        data[name] = val
    return data

@receiver(pre_save, sender=MenuItems)
def _mcp_pre_save_menuitems(sender, instance, **kwargs):
    if instance._state.adding:
        instance._mcp_old_data = None
    else:
        try:
            old = sender.objects.get(pk=instance.pk)
            instance._mcp_old_data = _serialize_instance(old)
        except sender.DoesNotExist:
            instance._mcp_old_data = None

@receiver(post_save, sender=MenuItems)
def _mcp_post_save_menuitems(sender, instance, created, **kwargs):
    old_data = getattr(instance, '_mcp_old_data', None)
    new_data = _serialize_instance(instance)
    action = 'INSERT' if created else 'UPDATE'
    changed = None
    if action == 'UPDATE' and old_data:
        diff = {}
        for k, v in new_data.items():
            if old_data.get(k) != v:
                diff[k] = [old_data.get(k), v]
        changed = diff or None
    # Resolve business id robustly
    try:
        biz = str(instance.business_id_id)
    except Exception:
        try:
            biz = str(getattr(instance.business_id, 'business_id', None))
        except Exception:
            biz = None
    MCPLog.objects.create(
        entity_type='menu_item',
        table_name=instance._meta.db_table,
        entity_id=str(instance.pk),
        business_id=biz,
        user_id=None,
        action_type=action,
        old_data=old_data,
        new_data=new_data,
        changed_fields=changed
    )

@receiver(post_delete, sender=MenuItems)
def _mcp_post_delete_menuitems(sender, instance, **kwargs):
    old_data = _serialize_instance(instance)
    try:
        biz = str(instance.business_id_id)
    except Exception:
        try:
            biz = str(getattr(instance.business_id, 'business_id', None))
        except Exception:
            biz = None
    MCPLog.objects.create(
        entity_type='menu_item',
        table_name=instance._meta.db_table,
        entity_id=str(instance.pk),
        business_id=biz,
        user_id=None,
        action_type='DELETE',
        old_data=old_data,
        new_data=None,
        changed_fields=None
    )

@receiver(pre_save, sender=GroceriesProducts)
def _mcp_pre_save_groceries(sender, instance, **kwargs):
    if instance._state.adding:
        instance._mcp_old_data = None
    else:
        try:
            old = sender.objects.get(pk=instance.pk)
            instance._mcp_old_data = _serialize_instance(old)
        except sender.DoesNotExist:
            instance._mcp_old_data = None

@receiver(post_save, sender=GroceriesProducts)
def _mcp_post_save_groceries(sender, instance, created, **kwargs):
    old_data = getattr(instance, '_mcp_old_data', None)
    new_data = _serialize_instance(instance)
    action = 'INSERT' if created else 'UPDATE'
    changed = None
    if action == 'UPDATE' and old_data:
        diff = {}
        for k, v in new_data.items():
            if old_data.get(k) != v:
                diff[k] = [old_data.get(k), v]
        changed = diff or None
    # business raw id exists as business_id on this model
    biz = None
    try:
        biz = str(instance.business_id)
    except Exception:
        try:
            biz = str(getattr(instance.business, 'business_id', None))
        except Exception:
            biz = None
    MCPLog.objects.create(
        entity_type='grocery_product',
        table_name=instance._meta.db_table,
        entity_id=str(instance.pk),
        business_id=biz,
        user_id=None,
        action_type=action,
        old_data=old_data,
        new_data=new_data,
        changed_fields=changed
    )

@receiver(post_delete, sender=GroceriesProducts)
def _mcp_post_delete_groceries(sender, instance, **kwargs):
    old_data = _serialize_instance(instance)
    biz = None
    try:
        biz = str(instance.business_id)
    except Exception:
        try:
            biz = str(getattr(instance.business, 'business_id', None))
        except Exception:
            biz = None
    MCPLog.objects.create(
        entity_type='grocery_product',
        table_name=instance._meta.db_table,
        entity_id=str(instance.pk),
        business_id=biz,
        user_id=None,
        action_type='DELETE',
        old_data=old_data,
        new_data=None,
        changed_fields=None
    )


def product_item_upload_path(instance, filename):
    """Generate upload path for product item images based on business type"""
    timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
    ext = filename.split('.')[-1]
    
    # Check business type to determine folder
    # Note: Django ImageField upload_to is relative to MEDIA_ROOT, so we return path without 'media/' prefix
    # The path will be stored in database and serializer will add 'media/' when building URLs
    try:
        business_type = instance.business_id.businessType if instance.business_id else None
        if business_type == 'R01':  # Grocery business
            return f'grocery/{instance.item_id}_{timestamp}.{ext}'
        else:
            # Default fallback for other business types
            return f'productItems/{instance.item_id}_{timestamp}.{ext}'
    except Exception:
        # Fallback if business type cannot be determined
        return f'productItems/{instance.item_id}_{timestamp}.{ext}'

class productItems(models.Model):
    item_id = models.BigAutoField(primary_key=True)
    business_id = models.ForeignKey(
        Business,
        on_delete=models.CASCADE,
        to_field="business_id",
        db_column="business_id"
    )
    item_name = models.CharField(max_length=255)
    item_image = models.ImageField(
        upload_to=product_item_upload_path, null=True, blank=True
    )
    item_type = models.CharField(max_length=100, null=True, blank=True)
    material = models.CharField(max_length=45, null=True, blank=True)
    gender = models.CharField(max_length=45, null=True, blank=True)
    color = models.CharField(max_length=45, null=True, blank=True)
    item_category = models.CharField(max_length=100, null=True, blank=True)
    description = models.CharField(max_length=100, null=True, blank=True)
    item_placed_at = models.CharField(max_length=100, null=True, blank=True)
    is_organic = models.CharField(max_length=45, null=True, blank=True)
    availability_timings = models.TimeField(null=True, blank=True)
    weight = models.CharField(max_length=45, null=True, blank=True)
    size = models.CharField(max_length=45, null=True, blank=True)
    unit = models.CharField(max_length=10, null=True, blank=True)
    rating = models.DecimalField(max_digits=2, decimal_places=1, null=True, blank=True)
    rating_count = models.IntegerField(null=True, blank=True, default=0)
    original_cost = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    gst = models.IntegerField(null=True, blank=True, help_text="GST percentage")
    charges = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True, help_text="Calculated GST amount")
    selling_price = models.DecimalField(max_digits=10, decimal_places=2)
    wallet_points_availablity = models.BooleanField(default=False)
    wallet_points = models.BigIntegerField(default=0)
    mfg_data = models.DateField(null=True, blank=True)
    expiry_date = models.DateField(null=True, blank=True)
    stock = models.IntegerField(null=True, blank=True)
    sub_images = models.JSONField(null=True, blank=True, help_text="Additional images in JSON array format")
    is_featured = models.BooleanField(default=False, help_text="Mark product as featured")
    is_active = models.BooleanField(default=True)
    status = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "GroceryItems"
        ordering = ["item_name"]

    def save(self, *args, **kwargs):
        # Calculate GST charges if original_cost and gst are provided
        if self.original_cost and self.gst:
            self.charges = (self.original_cost * self.gst) / 100

        if self.is_active is None:
            self.is_active = True
        if self.status is None:
            self.status = True

        # Custom item_id starting point if table empty
        if not self.item_id:
            last_item = productItems.objects.order_by("-item_id").first()
            if last_item:
                self.item_id = last_item.item_id + 1
            else:
                self.item_id = 105501

        super().save(*args, **kwargs)

    def __str__(self):
        return self.item_name


class UniversalCategory(models.Model):
    category_id = models.BigAutoField(primary_key=True)
    category_name = models.CharField(max_length=100)
    category_image = models.CharField(max_length=225, null=True, blank=True)
    parent_category_id = models.BigIntegerField(null=True, blank=True)
    created_at = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = 'universal_Categories'
        managed = False

    def __str__(self):
        return self.category_name


class FashionProduct(models.Model):
    product_id = models.BigAutoField(primary_key=True)
    variant_id = models.BigIntegerField(null=True, blank=True, db_column='variant_id')
    business_id = models.ForeignKey(Business, on_delete=models.CASCADE, to_field='business_id', db_column='business_id')
    category = models.ForeignKey(UniversalCategory, on_delete=models.PROTECT, db_column='category_id', related_name='fashion_products_category')
    subcategory = models.CharField(max_length=50, null=True, blank=True, db_column='subcategory_id')
    name = models.CharField(max_length=255)
    description = models.TextField(null=True, blank=True)
    brand = models.CharField(max_length=120, null=True, blank=True)
    base_price = models.DecimalField(max_digits=10, decimal_places=2, default=decimal.Decimal('0.00'))
    gst_rate_default = models.DecimalField(max_digits=5, decimal_places=2, default=decimal.Decimal('0.00'))
    hsn_code = models.CharField(max_length=20, null=True, blank=True)
    main_image = models.CharField(max_length=500, null=True, blank=True)
    sub_images = models.JSONField(null=True, blank=True, help_text="Additional images in JSON array format")
    is_featured = models.BooleanField(default=False, help_text="Mark product as featured")
    rating = models.DecimalField(max_digits=2, decimal_places=1, default=decimal.Decimal('4.0'))
    item_placed_at = models.CharField(max_length=100, null=True, blank=True)
    is_customizable = models.BooleanField(default=False)
    is_visible = models.BooleanField(default=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = 'fashion_products'
        managed = False
        ordering = ['-product_id']

    def __str__(self):
        return self.name


class FashionProductVariant(models.Model):
    variant_id = models.BigAutoField(primary_key=True)
    business_id = models.ForeignKey(Business, on_delete=models.CASCADE, to_field='business_id', db_column='business_id')
    product = models.ForeignKey(FashionProduct, on_delete=models.CASCADE, db_column='product_id', related_name='variants')
    sku = models.CharField(max_length=100)
    barcode = models.CharField(max_length=100, null=True, blank=True)
    selling_price = models.DecimalField(max_digits=10, decimal_places=2, default=decimal.Decimal('0.00'))
    mrp = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    stock_qty = models.IntegerField(default=0)
    net_weight = models.IntegerField(null=True, blank=True)
    net_weight_unit = models.CharField(max_length=10, null=True, blank=True)
    original_cost = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    charges = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    stock = models.IntegerField(null=True, blank=True, default=0)
    rating = models.DecimalField(max_digits=3, decimal_places=2, null=True, blank=True, default=4.0)
    rating_count = models.IntegerField(null=True, blank=True, default=0)
    mfg_date = models.DateField(null=True, blank=True)
    expiry_date = models.DateField(null=True, blank=True)
    size = models.CharField(max_length=50, null=True, blank=True)
    color = models.CharField(max_length=50, null=True, blank=True)
    material = models.CharField(max_length=80, null=True, blank=True)
    gender = models.CharField(max_length=20, null=True, blank=True)
    min_age = models.IntegerField(null=True, blank=True)
    max_age = models.IntegerField(null=True, blank=True)
    pack = models.CharField(max_length=100, null=True, blank=True)
    attributes = models.JSONField(null=True, blank=True)
    # Product dimensions in JSON format: {"L": length, "B": breadth, "H": height}
    dimension = models.JSONField(null=True, blank=True, help_text="Product dimensions in JSON format: {'L': length, 'B': breadth, 'H': height}")
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = 'fashion_product_variants'
        managed = False
        ordering = ['-variant_id']
        constraints = [
            models.UniqueConstraint(fields=['business_id', 'sku'], name='uq_fashion_variant_business_sku')
        ]

    def save(self, *args, **kwargs):
        if not self.sku:
            self.sku = self._generate_sku()
        super().save(*args, **kwargs)

    def _generate_sku(self):
        import re
        base_name = ''
        try:
            base_name = getattr(getattr(self, 'product', None), 'name', '') or ''
        except Exception:
            base_name = ''

        base = re.sub(r'[^a-zA-Z0-9\s]', '', (base_name or 'product') or '')
        base = base.lower().replace(' ', '')
        parts = [base]
        if self.size:
            parts.append(re.sub(r'[^a-zA-Z0-9]', '', str(self.size).lower()))
        if self.color:
            parts.append(re.sub(r'[^a-zA-Z0-9]', '', str(self.color).lower()))
        sku = '_'.join([p for p in parts if p]) or 'product'

        base_sku = sku
        counter = 1
        while FashionProductVariant.objects.filter(business_id=self.business_id, sku=sku).exclude(variant_id=self.variant_id).exists():
            sku = f"{base_sku}_{counter}"
            counter += 1
        return sku

    def __str__(self):
        return self.sku

# =============================
# Counter POS Models
# =============================

class BusinessCounterOrders(models.Model):
    order_id = models.BigAutoField(primary_key=True)
    business_id = models.ForeignKey(Business, on_delete=models.CASCADE, to_field='business_id', db_column='business_id')
    user_id = models.ForeignKey(Registration, on_delete=models.CASCADE, to_field='user_id', db_column='user_id')
    username = models.CharField(max_length=150, default='skipped')
    customer_mobile = models.CharField(max_length=20, default='skipped', blank=True)
    customer_email = models.CharField(max_length=150, default='skipped', blank=True)
    token_number = models.CharField(max_length=50, null=True, blank=True)
    offline_token_no = models.CharField(max_length=50, null=True, blank=True)
    order_type = models.CharField(max_length=50, null=True, blank=True)  # 'menu', 'grocery'
    service_mode = models.CharField(max_length=50, null=True, blank=True)
    payment_method = models.CharField(max_length=50, null=True, blank=True)  # 'cash', 'card', 'upi'
    subtotal = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    gst_total = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    total_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    delivery_charges = models.DecimalField(max_digits=10, decimal_places=2, default=0.00, null=True, blank=True)
    customization_charges = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    discount_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    discount_percentage = models.DecimalField(max_digits=5, decimal_places=2, default=0.00)  # Discount percentage (0-100)
    discount_type = models.CharField(max_length=20, default='fixed', null=True, blank=True)  # 'fixed' or 'percentage'
    discount_reason = models.TextField(null=True, blank=True)  # Reason for discount
    paid_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)  # Amount paid so far
    remaining_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)  # Amount remaining to be paid
    status = models.CharField(max_length=50, null=True, blank=True)  # 'pending', 'paid', 'cancelled', 'partially_paid'
    cancellation_reason = models.TextField(null=True, blank=True)
    remarks = models.TextField(null=True, blank=True)
    email_sent = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    cancelled_at = models.DateTimeField(null=True, blank=True)
    invoice_id = models.BigIntegerField(null=True, blank=True)  # FK to business_tax_invoice.invoice_id

    class Meta:
        db_table = 'business_counter_orders'
        ordering = ['-created_at']

    def save(self, *args, **kwargs):
        # Auto-generate token number if not provided
        if not self.token_number:
            self.token_number = self._generate_token_number()
        super().save(*args, **kwargs)
    
    def _generate_token_number(self):
        """Generate token number starting from 101 to 999999"""
        today = timezone.now().date()
        last_order = BusinessCounterOrders.objects.filter(
            business_id=self.business_id,
            created_at__date=today
        ).order_by('-created_at').first()

        if last_order and last_order.token_number:
            try:
                last_token = int(last_order.token_number)
            except (ValueError, TypeError):
                last_token = 0
            new_token = last_token + 1
        else:
            new_token = 1

        return f"{new_token:03d}"

    def __str__(self):
        return f"Order #{self.token_number} - {self.business_id}"


class BusinessCounterItems(models.Model):
    id = models.BigAutoField(primary_key=True)
    order_id = models.ForeignKey(BusinessCounterOrders, on_delete=models.CASCADE, related_name='items', db_column='order_id')
    business_id = models.ForeignKey(Business, on_delete=models.CASCADE, to_field='business_id', db_column='business_id')
    menu_item_id = models.ForeignKey(MenuItems, on_delete=models.SET_NULL, null=True, blank=True, to_field='item_id', db_column='menu_item_id')
    product_id = models.BigIntegerField(null=True, blank=True)  # FK to Groceries_Products (not defined in this file)
    variant_id = models.BigIntegerField(null=True, blank=True)  # FK to Groceries_ProductVariants_1 (not defined in this file)
    sku = models.CharField(max_length=100, null=True, blank=True)
    item_name = models.CharField(max_length=255)  # Snapshot at order time
    size_label = models.CharField(max_length=50, null=True, blank=True)
    quantity = models.IntegerField(default=1)
    unit_price = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    gst = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    line_total = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    is_customized = models.BooleanField(default=False)
    customization_details = models.JSONField(null=True, blank=True)
    notes = models.TextField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'business_counter_items'
        ordering = ['order_id', 'id']

    def save(self, *args, **kwargs):
        # Calculate line total based on quantity and unit_price
        self.line_total = (self.unit_price * self.quantity) + self.gst
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.item_name} - Order #{self.order_id.token_number}"


class BusinessCounterLogs(models.Model):
    log_id = models.BigAutoField(primary_key=True)
    business_id = models.ForeignKey(Business, on_delete=models.SET_NULL, null=True, blank=True, to_field='business_id', db_column='business_id')
    user_id = models.ForeignKey(Registration, on_delete=models.SET_NULL, null=True, blank=True, to_field='user_id', db_column='user_id')
    action_type = models.CharField(max_length=100)  # 'order_created', 'order_updated', 'item_added', etc.
    reference_id = models.CharField(max_length=100, null=True, blank=True)  # order_id, item_id, etc.
    reason = models.TextField(null=True, blank=True)
    old_data = models.JSONField(null=True, blank=True)
    new_data = models.JSONField(null=True, blank=True)
    description = models.TextField(null=True, blank=True)
    ip_address = models.CharField(max_length=45, null=True, blank=True)
    user_agent = models.CharField(max_length=255, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'business_counter_logs'
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.action_type} - {self.reference_id} at {self.created_at}"


class ProductCustomizationTemplate(models.Model):
    id = models.BigAutoField(primary_key=True)
    business_id = models.CharField(max_length=50)
    product_id = models.BigIntegerField()
    template_name = models.CharField(max_length=255, db_column='name')
    design_type = models.CharField(max_length=20, choices=[
        ('sticker', 'Sticker'),
        ('text', 'Text'),
        ('drawing', 'Drawing'),
        ('user_upload', 'User Upload')
    ], db_column='design_type')
    price_delta = models.DecimalField(max_digits=10, decimal_places=2, default=0.00, db_column='price_delta')
    asset_url = models.CharField(max_length=512, null=True, blank=True, db_column='asset_url')
    max_chars = models.IntegerField(null=True, blank=True, db_column='max_chars')
    per_char_price = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True, db_column='per_char_price')
    flat_price = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True, db_column='flat_price')
    base_price = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True, db_column='base_price')
    is_active = models.BooleanField(default=True, db_column='is_active')
    position = models.SmallIntegerField(default=0, db_column='position')
    created_at = models.DateTimeField(auto_now_add=True, db_column='created_at')
    updated_at = models.DateTimeField(auto_now=True, db_column='updated_at')
    
    # Add options field to map to existing structure
    @property
    def options(self):
        """Return options as JSON structure compatible with frontend"""
        options = []
        if self.design_type == 'text':
            options.append({
                "label": self.template_name,
                "type": "text",
                "max_chars": self.max_chars or 20,
                "price": float(self.per_char_price or self.flat_price or self.price_delta)
            })
        elif self.design_type in ['sticker', 'drawing', 'user_upload']:
            options.append({
                "label": self.template_name,
                "type": self.design_type,
                "price": float(self.flat_price or self.price_delta)
            })
        return options

    class Meta:
        db_table = 'Groceries_CustomDesigns'
        ordering = ['position', 'template_name']

    def __str__(self):
        return self.template_name


# =============================
# Review Reason Templates
# =============================

class ReviewReasonTemplate(models.Model):
    """Templates for rejection/required change reasons"""
    REASON_TYPES = [
        ('rejection', 'Rejection Reason'),
        ('required_changes', 'Required Changes'),
        ('approval', 'Approval Reason'),
    ]
    
    CATEGORIES = [
        ('documentation', 'Documentation Issues'),
        ('business_info', 'Business Information'),
        ('legal_compliance', 'Legal & Compliance'),
        ('operational', 'Operational Requirements'),
        ('quality', 'Quality Standards'),
        ('other', 'Other'),
    ]
    
    id = models.BigAutoField(primary_key=True)
    reason_type = models.CharField(max_length=20, choices=REASON_TYPES)
    category = models.CharField(max_length=20, choices=CATEGORIES, default='other')
    title = models.CharField(max_length=200)  # Short title for dropdown
    description = models.TextField()  # Detailed description
    is_active = models.BooleanField(default=True)
    is_required = models.BooleanField(default=False)  # For mandatory reasons
    display_order = models.IntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'review_reason_templates'
        ordering = ['reason_type', 'display_order', 'title']
        unique_together = ['reason_type', 'title']

    def __str__(self):
        return f"{self.get_reason_type_display()}: {self.title}"


class CustomReviewReason(models.Model):
    """Custom reasons added by admins for specific applications"""
    id = models.BigAutoField(primary_key=True)
    admin_review = models.ForeignKey(AdminReview, on_delete=models.CASCADE, related_name='custom_reasons')
    reason_type = models.CharField(max_length=20, choices=ReviewReasonTemplate.REASON_TYPES)
    title = models.CharField(max_length=200)
    description = models.TextField()
    is_template_based = models.BooleanField(default=False)  # If based on template
    template = models.ForeignKey(ReviewReasonTemplate, on_delete=models.SET_NULL, null=True, blank=True, db_column='template_id')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'custom_review_reasons'
        ordering = ['id']
