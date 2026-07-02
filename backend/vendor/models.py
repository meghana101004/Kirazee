"""
Vendor Models
"""
from django.db import models


class VendorProfiles(models.Model):
    vendor_id = models.BigAutoField(primary_key=True)
    user = models.OneToOneField(
        'kirazee_app.Registration', 
        models.DO_NOTHING, 
        to_field='user_id', 
        db_column='user_id',
        related_name='vendor_profile'
    )
    shop_name = models.CharField(max_length=255)
    shop_slug = models.CharField(unique=True, max_length=255)
    business_type = models.CharField(max_length=150)
    gst_number = models.CharField(max_length=20, blank=True, null=True)
    gst_image_url = models.CharField(max_length=500, blank=True, null=True)
    aadhar_number = models.CharField(max_length=20, blank=True, null=True)
    aadhar_image_url = models.CharField(max_length=500, blank=True, null=True)
    shop_address = models.TextField()
    shipping_from = models.CharField(max_length=255)
    business_category = models.CharField(max_length=100, blank=True, null=True)
    business_description = models.TextField(blank=True, null=True)
    years_in_business = models.IntegerField(blank=True, null=True)
    contact_email = models.CharField(max_length=255, blank=True, null=True)
    contact_phone = models.CharField(max_length=20, blank=True, null=True)
    website_url = models.CharField(max_length=500, blank=True, null=True)
    is_gst_verified = models.BooleanField(default=False)
    is_vendor_approved = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    approval_status = models.CharField(
        max_length=8,
        choices=[
            ('pending', 'Pending'),
            ('approved', 'Approved'),
            ('rejected', 'Rejected')
        ],
        default='pending'
    )
    rejection_reason = models.TextField(blank=True, null=True)
    commission_percentage = models.DecimalField(max_digits=5, decimal_places=2, blank=True, null=True)
    max_products_limit = models.IntegerField(blank=True, null=True, default=1000)
    logo_url = models.CharField(max_length=500, blank=True, null=True)
    default_shipping_states = models.JSONField(blank=True, null=True)
    metadata = models.JSONField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        managed = False
        db_table = 'vendor_profiles'

    def __str__(self):
        return f"{self.shop_name} ({self.vendor_id})"


class VendorProduct(models.Model):
    product_id = models.BigAutoField(primary_key=True)
    
    # Core identifiers
    business_id = models.CharField(max_length=50, db_collation='utf8mb4_general_ci')
    vendor_id = models.BigIntegerField()
    
    # Product details
    product_name = models.CharField(max_length=255, db_collation='utf8mb4_general_ci')
    product_slug = models.CharField(max_length=255, db_collation='utf8mb4_general_ci')
    product_type = models.CharField(
        max_length=10,
        choices=[
            ('physical', 'Physical'),
            ('digital', 'Digital'),
            ('service', 'Service')
        ],
        default='physical',
        db_collation='utf8mb4_general_ci'
    )
    
    # Descriptions
    description = models.TextField(blank=True, null=True, db_collation='utf8mb4_general_ci')
    short_description = models.TextField(blank=True, null=True, db_collation='utf8mb4_general_ci')
    
    # Product metadata
    brand_name = models.CharField(max_length=150, blank=True, null=True, db_collation='utf8mb4_general_ci')
    base_sku = models.CharField(max_length=100, blank=True, null=True, db_collation='utf8mb4_general_ci')
    hsn_code = models.CharField(max_length=20, blank=True, null=True, db_collation='utf8mb4_general_ci')
    item_placed_at = models.CharField(max_length=100, blank=True, null=True, db_collation='utf8mb4_general_ci')
    
    # Categorization
    category_name = models.CharField(max_length=150, blank=True, null=True, db_collation='utf8mb4_general_ci')
    category_id = models.IntegerField(blank=True, null=True)
    sub_category_name = models.CharField(max_length=150, blank=True, null=True, db_collation='utf8mb4_general_ci')
    sub_category_id = models.IntegerField(blank=True, null=True)
    
    # Pricing
    original_price = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    selling_price = models.DecimalField(max_digits=12, decimal_places=2, blank=True, null=True)
    gst_percentage = models.DecimalField(max_digits=5, decimal_places=2, default=18.00)
    
    # Dimensions & Weight
    weight = models.DecimalField(max_digits=10, decimal_places=2, blank=True, null=True)
    weight_unit = models.CharField(
        max_length=5,
        choices=[
            ('kg', 'KG'),
            ('g', 'Grams'),
            ('ltr', 'Liters'),
            ('ml', 'ML'),
            ('unit', 'Unit')
        ],
        default='unit',
        db_collation='utf8mb4_general_ci'
    )
    length_cm = models.DecimalField(max_digits=10, decimal_places=2, blank=True, null=True)
    width_cm = models.DecimalField(max_digits=10, decimal_places=2, blank=True, null=True)
    height_cm = models.DecimalField(max_digits=10, decimal_places=2, blank=True, null=True)
    
    # Product conditions
    condition_new = models.BooleanField(default=True)
    is_returnable = models.BooleanField(default=True)
    return_days = models.IntegerField(default=7)
    
    # JSON fields for flexibility
    images = models.JSONField(blank=True, null=True)
    variants = models.JSONField(blank=True, null=True)
    inventory = models.JSONField(blank=True, null=True)
    attributes = models.JSONField(blank=True, null=True)
    sizes_available = models.JSONField(blank=True, null=True)
    colors_available = models.JSONField(blank=True, null=True)
    
    # Stock management
    has_variants = models.BooleanField(default=False)
    manage_stock = models.BooleanField(default=True)
    stock_quantity = models.JSONField(blank=True, null=True)
    stock_status = models.CharField(
        max_length=15,
        choices=[
            ('in_stock', 'In Stock'),
            ('out_of_stock', 'Out of Stock'),
            ('backorder', 'Backorder')
        ],
        default='in_stock',
        db_collation='utf8mb4_general_ci'
    )
    
    # Status flags
    is_active = models.BooleanField(default=True)
    is_approved = models.BooleanField(default=False)
    approval_status = models.CharField(
        max_length=10,
        choices=[
            ('pending', 'Pending'),
            ('approved', 'Approved'),
            ('rejected', 'Rejected')
        ],
        default='pending',
        db_collation='utf8mb4_general_ci'
    )
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'vendor_products'
        indexes = [
            models.Index(fields=['vendor_id', 'is_active'], name='idx_vp_vendor_active'),
            models.Index(fields=['business_id'], name='idx_vp_business_id'),
            models.Index(fields=['category_name'], name='idx_vp_category'),
            models.Index(fields=['sub_category_name'], name='idx_vp_sub_category'),
            models.Index(fields=['gst_percentage'], name='idx_vp_gst'),
            models.Index(fields=['brand_name', 'product_type'], name='idx_vp_brand_type'),
            models.Index(fields=['stock_status', 'manage_stock'], name='idx_vp_stock_status'),
            models.Index(fields=['is_active', 'is_approved', 'approval_status'], name='idx_vp_status_approved'),
        ]
        # Note: FULLTEXT index and UNIQUE constraints need to be created via migration/raw SQL
        # Django doesn't support FULLTEXT indexes natively on MySQL

    def save(self, *args, **kwargs):
        """Override save to set product_id from Groceries_Products sequence"""
        from consumer.gro_models import GroceriesProducts
        from django.db import connection
        
        # If creating a new product (no product_id yet)
        if not self.product_id:
            # Get the maximum product_id from both tables
            with connection.cursor() as cursor:
                cursor.execute("""
                    SELECT GREATEST(
                        COALESCE((SELECT MAX(product_id) FROM Groceries_Products), 0),
                        COALESCE((SELECT MAX(product_id) FROM vendor_products), 0)
                    ) as max_id
                """)
                result = cursor.fetchone()
                max_id = result[0] if result and result[0] else 0
                self.product_id = max_id + 1
        
        super().save(*args, **kwargs)
    
    def sync_to_groceries(self):
        """
        Manually sync this vendor product to Groceries_Products table
        Returns: (success: bool, message: str)
        """
        from consumer.gro_models import GroceriesProducts, GroceriesProductVariants, GroceriesCategories
        from kirazee_app.models import Business
        from django.db import connection, transaction
        import logging
        
        logger = logging.getLogger(__name__)
        
        try:
            with transaction.atomic():
                # Check if already synced
                existing_grocery = GroceriesProducts.objects.filter(product_id=self.product_id).first()
                if existing_grocery:
                    logger.warning(f"Product {self.product_id} already exists in Groceries_Products")
                    return (False, f"Product {self.product_id} already exists in Groceries_Products")
                
                # Validate required fields
                if not self.category_name:
                    return (False, "Category name is required for sync")
                
                # Get or create category using raw SQL (since managed=False)
                category = GroceriesCategories.objects.filter(category_name=self.category_name).first()
                
                if not category:
                    with connection.cursor() as cursor:
                        cursor.execute("""
                            INSERT INTO universal_Categories (category_name, parent_category_id, created_at, updated_at)
                            VALUES (%s, NULL, NOW(), NOW())
                        """, [self.category_name])
                        cursor.execute("SELECT LAST_INSERT_ID()")
                        category_id = cursor.fetchone()[0]
                        category = GroceriesCategories.objects.get(category_id=category_id)
                        logger.info(f"Created new category: {self.category_name} with ID {category_id}")
                
                # Get business
                business = Business.objects.filter(business_id=self.business_id).first()
                
                if not business:
                    logger.error(f"Business {self.business_id} not found")
                    return (False, f"Business {self.business_id} not found")
                
                # Extract main image from images JSON
                main_image = ''
                if self.images:
                    if isinstance(self.images, list) and len(self.images) > 0:
                        main_image = self.images[0]
                    elif isinstance(self.images, str):
                        main_image = self.images
                
                logger.info(f"Creating Groceries_Products entry for product {self.product_id}")
                
                # Create Groceries_Products entry
                grocery_product = GroceriesProducts.objects.create(
                    product_id=self.product_id,
                    business=business,
                    product_name=self.product_name,
                    brand_name=self.brand_name or '',
                    category=category,
                    sub_category=self.sub_category_name or '',
                    description=self.description or '',
                    item_placed_at=self.item_placed_at or '',
                    main_image=main_image,
                    is_customizable=False,
                    is_visible=self.is_active,
                    is_organic=False,
                    rating=None
                )
                
                logger.info(f"Created Groceries_Products entry for product {self.product_id}")
                
                # Create default variant if no variants exist
                if not self.has_variants:
                    import re
                    clean_name = re.sub(r'[^a-zA-Z0-9\s]', '', self.product_name)
                    sku = clean_name.lower().replace(' ', '_')
                    
                    # Ensure unique SKU
                    base_sku = sku
                    counter = 1
                    while GroceriesProductVariants.objects.filter(sku=sku).exists():
                        sku = f"{base_sku}_{counter}"
                        counter += 1
                    
                    # Map weight_unit from vendor to grocery format
                    weight_unit_map = {
                        'kg': 'kg',
                        'g': 'g',
                        'ltr': 'l',
                        'ml': 'ml',
                        'unit': 'pcs'
                    }
                    
                    variant = GroceriesProductVariants.objects.create(
                        product=grocery_product,
                        sku=sku,
                        net_weight=int(self.weight) if self.weight else None,
                        net_weight_unit=weight_unit_map.get(self.weight_unit, 'pcs'),
                        size=None,
                        original_cost=self.original_price,
                        selling_price=self.selling_price or self.original_price,
                        charges=None,
                        gst=self.gst_percentage,
                        stock=self.stock_quantity,
                        mfg_date=None,
                        expiry_date=None,
                        is_active=self.is_active
                    )
                    
                    logger.info(f"Created variant for product {self.product_id} with SKU {sku}")
                
                logger.info(f"✓ Successfully synced vendor product {self.product_id} to Groceries_Products")
                return (True, f"Product {self.product_id} successfully synced to Groceries_Products")
            
        except Exception as e:
            logger.error(f"✗ Error syncing product {self.product_id}: {str(e)}")
            import traceback
            traceback.print_exc()
            return (False, f"Error syncing product {self.product_id}: {str(e)}")

    def __str__(self):
        return f"{self.product_name} (ID: {self.product_id})"


# Signal to sync approved vendor products to Groceries_Products
from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver


@receiver(pre_save, sender=VendorProduct)
def track_approval_change(sender, instance, **kwargs):
    """Track if approval status is changing"""
    if instance.pk:
        try:
            old_instance = VendorProduct.objects.get(pk=instance.pk)
            instance._approval_changed = (
                old_instance.is_approved != instance.is_approved or
                old_instance.approval_status != instance.approval_status
            )
            instance._was_approved = old_instance.is_approved
        except VendorProduct.DoesNotExist:
            instance._approval_changed = False
            instance._was_approved = False
    else:
        instance._approval_changed = False
        instance._was_approved = False


@receiver(post_save, sender=VendorProduct)
def sync_to_groceries_on_approval(sender, instance, created, **kwargs):
    """
    When a vendor product is approved, sync it to Groceries_Products table
    """
    from consumer.gro_models import GroceriesProducts, GroceriesProductVariants, GroceriesCategories
    from kirazee_app.models import Business
    from django.db import connection, transaction
    import logging
    
    logger = logging.getLogger(__name__)
    
    # Check if product was just approved
    approval_changed = getattr(instance, '_approval_changed', False)
    was_approved = getattr(instance, '_was_approved', False)
    
    logger.info(f"Post-save signal for product {instance.product_id}: is_approved={instance.is_approved}, approval_status={instance.approval_status}, created={created}, approval_changed={approval_changed}, was_approved={was_approved}")
    
    # Only sync if product is approved and either just created as approved or approval status changed to approved
    if instance.is_approved and instance.approval_status == 'approved' and (created or (approval_changed and not was_approved)):
        try:
            with transaction.atomic():
                # Check if already synced to Groceries_Products
                existing_grocery = GroceriesProducts.objects.filter(product_id=instance.product_id).first()
                
                if existing_grocery:
                    logger.info(f"Product {instance.product_id} already exists in Groceries_Products")
                    return
                
                logger.info(f"Starting sync for product {instance.product_id} to Groceries_Products")
                
                # Validate required fields
                if not instance.category_name:
                    logger.error(f"Category name is required for product {instance.product_id}")
                    return
                
                # Get or create category using raw SQL (since managed=False)
                category = GroceriesCategories.objects.filter(category_name=instance.category_name).first()
                
                if not category:
                    # Create category using raw SQL since managed=False
                    with connection.cursor() as cursor:
                        cursor.execute("""
                            INSERT INTO universal_Categories (category_name, parent_category_id, created_at, updated_at)
                            VALUES (%s, NULL, NOW(), NOW())
                        """, [instance.category_name])
                        
                        # Get the created category_id
                        cursor.execute("SELECT LAST_INSERT_ID()")
                        category_id = cursor.fetchone()[0]
                        
                        # Fetch the created category
                        category = GroceriesCategories.objects.get(category_id=category_id)
                        logger.info(f"Created new category: {instance.category_name} with ID {category_id}")
                else:
                    logger.info(f"Found existing category: {instance.category_name} with ID {category.category_id}")
                
                # Get business
                business = Business.objects.filter(business_id=instance.business_id).first()
                
                if not business:
                    logger.error(f"Business {instance.business_id} not found")
                    return
                
                # Extract main image from images JSON
                main_image = ''
                if instance.images:
                    if isinstance(instance.images, list) and len(instance.images) > 0:
                        main_image = instance.images[0]
                    elif isinstance(instance.images, str):
                        main_image = instance.images
                
                logger.info(f"Creating Groceries_Products entry for product {instance.product_id}")
                
                # Create Groceries_Products entry
                grocery_product = GroceriesProducts.objects.create(
                    product_id=instance.product_id,
                    business=business,
                    product_name=instance.product_name,
                    brand_name=instance.brand_name or '',
                    category=category,
                    sub_category=instance.sub_category_name or '',
                    description=instance.description or '',
                    item_placed_at=instance.item_placed_at or '',
                    main_image=main_image,
                    is_customizable=False,
                    is_visible=instance.is_active,
                    is_organic=False,
                    rating=None
                )
                
                logger.info(f"Created Groceries_Products entry for product {instance.product_id}")
                
                # Create a default variant if no variants exist
                if not instance.has_variants:
                    # Generate SKU
                    import re
                    clean_name = re.sub(r'[^a-zA-Z0-9\s]', '', instance.product_name)
                    sku = clean_name.lower().replace(' ', '_')
                    
                    # Ensure unique SKU
                    base_sku = sku
                    counter = 1
                    while GroceriesProductVariants.objects.filter(sku=sku).exists():
                        sku = f"{base_sku}_{counter}"
                        counter += 1
                    
                    # Map weight_unit from vendor to grocery format
                    weight_unit_map = {
                        'kg': 'kg',
                        'g': 'g',
                        'ltr': 'l',
                        'ml': 'ml',
                        'unit': 'pcs'
                    }
                    
                    variant = GroceriesProductVariants.objects.create(
                        product=grocery_product,
                        sku=sku,
                        net_weight=int(instance.weight) if instance.weight else None,
                        net_weight_unit=weight_unit_map.get(instance.weight_unit, 'pcs'),
                        size=None,
                        original_cost=instance.original_price,
                        selling_price=instance.selling_price or instance.original_price,
                        charges=None,
                        gst=instance.gst_percentage,
                        stock=instance.stock_quantity,
                        mfg_date=None,
                        expiry_date=None,
                        is_active=instance.is_active
                    )
                    
                    logger.info(f"Created variant for product {instance.product_id} with SKU {sku}")
                
                logger.info(f"✓ Successfully synced vendor product {instance.product_id} to Groceries_Products")
                print(f"✓ Vendor product {instance.product_id} synced to Groceries_Products")
                    
        except Exception as e:
            logger.error(f"✗ Error syncing vendor product {instance.product_id} to Groceries_Products: {str(e)}")
            print(f"✗ Error syncing vendor product {instance.product_id} to Groceries_Products: {str(e)}")
            import traceback
            traceback.print_exc()
