"""
Vendor Registration and Profile Serializers
"""
from rest_framework import serializers
from kirazee_app.models import Registration
from .models import VendorProfiles
from django.db import transaction
from django.utils import timezone
import re


def generate_shop_slug(shop_name: str, max_attempts: int = 100) -> str:
    """
    Generate a unique shop slug from shop name
    
    Args:
        shop_name: The shop name to convert to slug
        max_attempts: Maximum attempts to find unique slug (default: 100)
        
    Returns:
        str: Unique kebab-case slug
        
    Raises:
        ValueError: If unable to generate unique slug after max attempts
    """
    if not shop_name or not shop_name.strip():
        raise ValueError("Shop name cannot be empty or whitespace-only")
    
    # Convert to lowercase
    slug = shop_name.lower()
    
    # Replace spaces with hyphens
    slug = slug.replace(' ', '-')
    
    # Remove special characters (keep only alphanumeric and hyphens)
    slug = re.sub(r'[^a-z0-9\-]', '', slug)
    
    # Remove consecutive hyphens
    slug = re.sub(r'-+', '-', slug)
    
    # Strip leading/trailing hyphens
    slug = slug.strip('-')
    
    # If slug is empty after cleaning, raise error
    if not slug:
        raise ValueError(f"Cannot generate valid slug from shop name: {shop_name}")
    
    # Check uniqueness and append numeric suffix if needed
    base_slug = slug
    counter = 1
    
    for attempt in range(max_attempts):
        # Check if slug exists in database
        if not VendorProfiles.objects.filter(shop_slug=slug).exists():
            return slug
        
        # Slug exists, try with numeric suffix
        slug = f"{base_slug}-{counter}"
        counter += 1
    
    # If we've exhausted all attempts, raise error
    raise ValueError(f"Unable to generate unique slug after {max_attempts} attempts for shop name: {shop_name}")


class VendorRegistrationSerializer(serializers.Serializer):
    """
    Serializer for vendor registration that creates both Registration and VendorProfiles records
    """
    # Registration fields
    firstName = serializers.CharField(max_length=100, required=True)
    lastName = serializers.CharField(max_length=100, required=True)
    countryCode = serializers.CharField(max_length=10, required=True)
    mobileNumber = serializers.CharField(max_length=15, required=True)
    emailID = serializers.EmailField(max_length=255, required=True)
    dob = serializers.DateField(required=False, allow_null=True)
    
    # VendorProfiles fields
    shop_name = serializers.CharField(max_length=255, required=True)
    business_type = serializers.CharField(max_length=150, required=True)
    gst_number = serializers.CharField(max_length=20, required=False, allow_blank=True, allow_null=True)
    gst_image_url = serializers.URLField(max_length=500, required=False, allow_blank=True, allow_null=True)
    aadhar_number = serializers.CharField(max_length=20, required=False, allow_blank=True, allow_null=True)
    aadhar_image_url = serializers.URLField(max_length=500, required=False, allow_blank=True, allow_null=True)
    shop_address = serializers.CharField(required=True)
    shipping_from = serializers.CharField(max_length=255, required=True)
    business_category = serializers.CharField(max_length=100, required=False, allow_blank=True, allow_null=True)
    business_description = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    years_in_business = serializers.IntegerField(required=False, allow_null=True)
    contact_email = serializers.EmailField(max_length=255, required=False, allow_blank=True, allow_null=True)
    contact_phone = serializers.CharField(max_length=20, required=False, allow_blank=True, allow_null=True)
    website_url = serializers.URLField(max_length=500, required=False, allow_blank=True, allow_null=True)
   
    def validate_mobileNumber(self, value):
        """Check mobile number uniqueness"""
        if Registration.objects.filter(mobileNumber=value).exists():
            raise serializers.ValidationError("A user with this mobile number already exists.")
        return value
    
    def validate_emailID(self, value):
        """Check email uniqueness"""
        if Registration.objects.filter(emailID=value).exists():
            raise serializers.ValidationError("A user with this email already exists.")
        return value
    
    def validate_shop_name(self, value):
        """Validate shop name is not empty/whitespace"""
        if not value or not value.strip():
            raise serializers.ValidationError("Shop name cannot be empty or whitespace-only.")
        return value.strip()
    
    def create(self, validated_data):
        """Create Registration and VendorProfiles records atomically"""
        # Extract user fields
        user_data = {
            'firstName': validated_data['firstName'],
            'lastName': validated_data['lastName'],
            'countryCode': validated_data['countryCode'],
            'mobileNumber': validated_data['mobileNumber'],
            'emailID': validated_data['emailID'],
            'dob': validated_data.get('dob'),
            'user_mode': 'vendor',
            'user_type': 'individual',
            'is_verified': False,
            'is_active': True,
            'status': True,
        }
        
        # Extract vendor fields
        vendor_data = {
            'shop_name': validated_data['shop_name'],
            'business_type': validated_data['business_type'],
            'gst_number': validated_data.get('gst_number', ''),
            'gst_image_url': validated_data.get('gst_image_url', ''),
            'aadhar_number': validated_data.get('aadhar_number', ''),
            'aadhar_image_url': validated_data.get('aadhar_image_url', ''),
            'shop_address': validated_data['shop_address'],
            'shipping_from': validated_data['shipping_from'],
            'business_category': validated_data.get('business_category', ''),
            'business_description': validated_data.get('business_description', ''),
            'years_in_business': validated_data.get('years_in_business'),
            'contact_email': validated_data.get('contact_email', ''),
            'contact_phone': validated_data.get('contact_phone', ''),
            'website_url': validated_data.get('website_url', ''),
           
            'is_active': 1,
            'approval_status': 'pending',
            'is_vendor_approved': 0,
            'created_at': timezone.now(),
            'updated_at': timezone.now(),
        }
        
        try:
            with transaction.atomic():
                # Create Registration record
                user = Registration.objects.create(**user_data)
                
                # Generate unique shop slug
                shop_slug = generate_shop_slug(validated_data['shop_name'])
                vendor_data['shop_slug'] = shop_slug
                vendor_data['user'] = user
                
                # Create VendorProfiles record
                vendor = VendorProfiles.objects.create(**vendor_data)
                
                # Return combined data
                return {
                    'user': user,
                    'vendor': vendor
                }
        except Exception as e:
            raise serializers.ValidationError(f"Error creating vendor account: {str(e)}")


class VendorProfileUpdateSerializer(serializers.Serializer):
    """
    Serializer for updating vendor profile information
    """
    # User fields (optional for update)
    firstName = serializers.CharField(max_length=100, required=False)
    lastName = serializers.CharField(max_length=100, required=False)
    dob = serializers.DateField(required=False, allow_null=True)
    
    # Vendor profile fields (optional for update)
    shop_name = serializers.CharField(max_length=255, required=False)
    business_type = serializers.CharField(max_length=150, required=False)
    gst_number = serializers.CharField(max_length=20, required=False, allow_blank=True, allow_null=True)
    gst_image_url = serializers.URLField(max_length=500, required=False, allow_blank=True, allow_null=True)
    aadhar_number = serializers.CharField(max_length=20, required=False, allow_blank=True, allow_null=True)
    aadhar_image_url = serializers.URLField(max_length=500, required=False, allow_blank=True, allow_null=True)
    shop_address = serializers.CharField(required=False)
    shipping_from = serializers.CharField(max_length=255, required=False)
    business_category = serializers.CharField(max_length=100, required=False, allow_blank=True, allow_null=True)
    business_description = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    years_in_business = serializers.IntegerField(required=False, allow_null=True)
    contact_email = serializers.EmailField(max_length=255, required=False, allow_blank=True, allow_null=True)
    contact_phone = serializers.CharField(max_length=20, required=False, allow_blank=True, allow_null=True)
    website_url = serializers.URLField(max_length=500, required=False, allow_blank=True, allow_null=True)
    logo_url = serializers.URLField(max_length=500, required=False, allow_blank=True, allow_null=True)
    
    def validate_shop_name(self, value):
        """Validate shop name is not empty/whitespace"""
        if value and not value.strip():
            raise serializers.ValidationError("Shop name cannot be empty or whitespace-only.")
        return value.strip() if value else value
    
    def update(self, instance, validated_data):
        """Update vendor profile and associated user information"""
        # Extract user fields
        user_fields = ['firstName', 'lastName', 'dob']
        user_data = {k: v for k, v in validated_data.items() if k in user_fields}
        
        # Extract vendor fields
        vendor_data = {k: v for k, v in validated_data.items() if k not in user_fields}
        
        try:
            with transaction.atomic():
                # Update user information if provided
                if user_data:
                    user = instance.user
                    for field, value in user_data.items():
                        setattr(user, field, value)
                    user.save()
                
                # Update vendor profile
                if vendor_data:
                    # If shop_name is being updated, regenerate slug
                    if 'shop_name' in vendor_data and vendor_data['shop_name'] != instance.shop_name:
                        # Generate new slug only if shop name changed
                        new_slug = generate_shop_slug(vendor_data['shop_name'])
                        vendor_data['shop_slug'] = new_slug
                    
                    # Update vendor fields
                    for field, value in vendor_data.items():
                        setattr(instance, field, value)
                    
                    instance.updated_at = timezone.now()
                    instance.save()
                
                return instance
        except Exception as e:
            raise serializers.ValidationError(f"Error updating vendor profile: {str(e)}")



class VendorProductSerializer(serializers.Serializer):
    """
    Serializer for creating and managing vendor products
    """
    # Core identifiers (vendor_id will be set from authenticated user)
    business_id = serializers.CharField(max_length=50, required=True)
    
    # Product details
    product_name = serializers.CharField(max_length=255, required=True)
    product_type = serializers.ChoiceField(
        choices=['physical', 'digital', 'service'],
        default='physical',
        required=False
    )
    
    # Descriptions
    description = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    short_description = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    
    # Product metadata
    brand_name = serializers.CharField(max_length=150, required=False, allow_blank=True, allow_null=True)
    base_sku = serializers.CharField(max_length=100, required=False, allow_blank=True, allow_null=True)
    hsn_code = serializers.CharField(max_length=20, required=False, allow_blank=True, allow_null=True)
    item_placed_at = serializers.CharField(max_length=100, required=False, allow_blank=True, allow_null=True)
    
    # Categorization
    category_name = serializers.CharField(max_length=150, required=False, allow_blank=True, allow_null=True)
    sub_category_name = serializers.CharField(max_length=150, required=False, allow_blank=True, allow_null=True)
    
    # Pricing
    original_price = serializers.DecimalField(max_digits=12, decimal_places=2, required=True)
    selling_price = serializers.DecimalField(max_digits=12, decimal_places=2, required=False, allow_null=True)
    gst_percentage = serializers.DecimalField(max_digits=5, decimal_places=2, default=18.00, required=False)
    
    # Dimensions & Weight
    weight = serializers.DecimalField(max_digits=10, decimal_places=2, required=False, allow_null=True)
    weight_unit = serializers.ChoiceField(
        choices=['kg', 'g', 'ltr', 'ml', 'unit'],
        default='unit',
        required=False
    )
    length_cm = serializers.DecimalField(max_digits=10, decimal_places=2, required=False, allow_null=True)
    width_cm = serializers.DecimalField(max_digits=10, decimal_places=2, required=False, allow_null=True)
    height_cm = serializers.DecimalField(max_digits=10, decimal_places=2, required=False, allow_null=True)
    
    # Product conditions
    condition_new = serializers.BooleanField(default=True, required=False)
    is_returnable = serializers.BooleanField(default=True, required=False)
    return_days = serializers.IntegerField(default=7, required=False)
    
    # JSON fields
    images = serializers.JSONField(required=False, allow_null=True)
    variants = serializers.JSONField(required=False, allow_null=True)
    inventory = serializers.JSONField(required=False, allow_null=True)
    attributes = serializers.JSONField(required=False, allow_null=True)
    sizes_available = serializers.JSONField(required=False, allow_null=True)
    colors_available = serializers.JSONField(required=False, allow_null=True)
    
    # Stock management
    has_variants = serializers.BooleanField(default=False, required=False)
    manage_stock = serializers.BooleanField(default=True, required=False)
    stock_quantity = serializers.JSONField(required=False, allow_null=True)
    stock_status = serializers.ChoiceField(
        choices=['in_stock', 'out_of_stock', 'backorder'],
        default='in_stock',
        required=False
    )

    def validate_images(self, value):
        """Validate images JSON structure: dict with keys like 'image2', 'image3', etc."""
        if value is None:
            return value
        if not isinstance(value, dict):
            raise serializers.ValidationError("Images must be a dictionary.")
        for key, val in value.items():
            if not isinstance(key, str) or not key.startswith('image'):
                raise serializers.ValidationError("Image keys must be strings starting with 'image'.")
            if not isinstance(val, str):
                raise serializers.ValidationError("Image values must be strings (file paths).")
        return value

    def validate_sizes_available(self, value):
        """Validate sizes_available: list of strings."""
        if value is None:
            return value
        if not isinstance(value, list):
            raise serializers.ValidationError("Sizes available must be a list.")
        for item in value:
            if not isinstance(item, str):
                raise serializers.ValidationError("Each size must be a string.")
        return value

    def validate_colors_available(self, value):
        """Validate colors_available: dict with string keys (sizes), values as lists of strings."""
        if value is None:
            return value
        if not isinstance(value, dict):
            raise serializers.ValidationError("Colors available must be a dictionary.")
        for size, colors in value.items():
            if not isinstance(size, str):
                raise serializers.ValidationError("Color keys must be strings (sizes).")
            if not isinstance(colors, list):
                raise serializers.ValidationError("Color values must be lists.")
            for color in colors:
                if not isinstance(color, str):
                    raise serializers.ValidationError("Each color must be a string.")
        return value

    def validate_stock_quantity(self, value):
        """Validate stock_quantity: dict with string keys (sizes), values as integers."""
        if value is None:
            return value
        if not isinstance(value, dict):
            raise serializers.ValidationError("Stock quantity must be a dictionary.")
        for size, qty in value.items():
            if not isinstance(size, str):
                raise serializers.ValidationError("Stock keys must be strings (sizes).")
            try:
                int(qty)
            except (ValueError, TypeError):
                raise serializers.ValidationError("Stock values must be integers.")
        return value
    
    def validate_product_name(self, value):
        """Validate product name is not empty"""
        if not value or not value.strip():
            raise serializers.ValidationError("Product name cannot be empty.")
        return value.strip()
    
    def validate_original_price(self, value):
        """Validate original price is positive"""
        if value < 0:
            raise serializers.ValidationError("Original price must be positive.")
        return value
    
    def validate_selling_price(self, value):
        """Validate selling price is positive if provided"""
        if value is not None and value < 0:
            raise serializers.ValidationError("Selling price must be positive.")
        return value
    
    def validate(self, data):
        """Cross-field validation"""
        # For partial updates, we need to check if the instance exists
        instance = getattr(self, 'instance', None)
        
        # Get original_price from data or instance
        original_price = data.get('original_price')
        if original_price is None and instance:
            original_price = instance.original_price
        
        # Get selling_price from data or instance
        selling_price = data.get('selling_price')
        if selling_price is None and instance:
            selling_price = instance.selling_price
        
        # If selling_price not provided and original_price is provided, set selling_price to original_price
        if 'selling_price' not in data and 'original_price' in data:
            data['selling_price'] = data['original_price']
            selling_price = data['selling_price']
        
        # Validate selling_price <= original_price (only if both are available)
        if selling_price is not None and original_price is not None:
            if selling_price > original_price:
                raise serializers.ValidationError({
                    'selling_price': 'Selling price cannot be greater than original price.'
                })
        
        return data
    
    def create(self, validated_data):
        """Create a new vendor product"""
        from .models import VendorProduct
        
        # Generate product slug from product name
        product_name = validated_data['product_name']
        product_slug = re.sub(r'[^a-z0-9\-]', '', product_name.lower().replace(' ', '-'))
        product_slug = re.sub(r'-+', '-', product_slug).strip('-')
        
        # Ensure unique slug
        base_slug = product_slug
        counter = 1
        while VendorProduct.objects.filter(product_slug=product_slug).exists():
            product_slug = f"{base_slug}-{counter}"
            counter += 1
        
        validated_data['product_slug'] = product_slug
        
        # Create product
        product = VendorProduct.objects.create(**validated_data)
        return product
    
    def update(self, instance, validated_data):
        """Update an existing vendor product"""
        # If product name changed, regenerate slug
        if 'product_name' in validated_data and validated_data['product_name'] != instance.product_name:
            product_name = validated_data['product_name']
            product_slug = re.sub(r'[^a-z0-9\-]', '', product_name.lower().replace(' ', '-'))
            product_slug = re.sub(r'-+', '-', product_slug).strip('-')
            
            # Ensure unique slug (excluding current instance)
            base_slug = product_slug
            counter = 1
            from .models import VendorProduct
            while VendorProduct.objects.filter(product_slug=product_slug).exclude(product_id=instance.product_id).exists():
                product_slug = f"{base_slug}-{counter}"
                counter += 1
            
            validated_data['product_slug'] = product_slug
        
        # Update fields
        for field, value in validated_data.items():
            setattr(instance, field, value)
        
        instance.save()
        return instance
