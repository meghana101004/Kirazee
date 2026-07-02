# serializers.py
from pyexpat import model
from datetime import datetime
from django.conf import settings  # Add this import
from rest_framework import serializers
from kirazee_app.models import BusinessFinancial, BusinessType, BusinessFeature, Business, Registration, BusinessMapping
from kirazee_app.business_utils import resolve_subcategory_name
from .models import MenuItems, BOM, productItems, CountryandStates, FashionProduct, FashionProductVariant, ProductCustomizationTemplate, MenuItemVariant
from business.image_utils import build_s3_file_url
from consumer.gro_models import GroceriesCategories
import json
import re

class CountryandStatesSerializer(serializers.ModelSerializer):
    class Meta:
        model = CountryandStates
        fields = ['id', 'country', 'state', 'district', 'taluk', 'pincode', 'status']

class BusinessTypeSerializer(serializers.ModelSerializer):
    logo_url = serializers.SerializerMethodField()
    banner_url = serializers.SerializerMethodField()
    mobile_logo_url = serializers.SerializerMethodField()
    mobile_banner_url = serializers.SerializerMethodField()
    order_types = serializers.SerializerMethodField()
    theme = serializers.SerializerMethodField()  # expose theme JSON
    
    class Meta:
        model = BusinessType
        fields = ['type', 'code', 'categories', 'title', 'svg', 'caption', 'logo_url', 'banner_url', 'mobile_logo_url', 'mobile_banner_url', 'order_types', 'theme']

    def get_logo_url(self, obj):
        return self._build_file_url(getattr(obj, 'logo', None))

    def get_banner_url(self, obj):
        return self._build_file_url(getattr(obj, 'banner', None))

    def get_mobile_logo_url(self, obj):
        return self._build_file_url(getattr(obj, 'mobile_logo', None))

    def get_mobile_banner_url(self, obj):
        return self._build_file_url(getattr(obj, 'mobile_banner', None))

    def _build_file_url(self, value):
        if not value:
            return None

        # Construct S3 URL directly
        # Files are stored at: prod/media/{relative_path}
        bucket_name = getattr(settings, 'AWS_STORAGE_BUCKET_NAME', None)
        region = getattr(settings, 'AWS_S3_REGION_NAME', 'ap-south-1')
        
        if not bucket_name:
            return None

        # Get the file path
        if hasattr(value, 'name'):
            file_path = value.name
        else:
            file_path = str(value)

        # Clean up the path - remove 'media/' prefix if present since S3 location already includes it
        file_path = file_path.lstrip('/')
        if file_path.startswith('media/'):
            file_path = file_path[6:]  # Remove 'media/' prefix

        # Build S3 URL
        s3_url = f"https://{bucket_name}.s3.{region}.amazonaws.com/prod/media/{file_path}"
        return s3_url.replace(' ', '%20')

    def get_order_types(self, obj):
        """Return the list of possible order types for this business type.
        If a DB column `order_types` is later added to business_types and mapped on the model,
        prefer that value; otherwise use defaults by code.
        """
        # Prefer DB-provided list if present on the object and is a list
        try:
            db_val = getattr(obj, 'order_types', None)
            if isinstance(db_val, (list, tuple)) and db_val:
                return [str(x).lower().replace('-', '_') for x in db_val]
        except Exception:
            pass

        # Fallback defaults by business type code
        code = (getattr(obj, 'code', None) or '').upper()
        defaults = {
            'R01': ['delivery', 'pickup'],
            'R02': ['delivery', 'dine_in', 'takeaway'],
            # Extend as needed for other codes (R03..R09 etc.)
        }
        return defaults.get(code, ['delivery'])

    def get_theme(self, obj):
        """
        Return theme JSON as-is (dict) or None.
        Example: { "primary_color": "#FF9800", "gradient": "...", "text_color": "#fff" }
        """
        try:
            theme = getattr(obj, 'theme', None)
            # If theme is stored as JSON string accidentally, try to parse
            if isinstance(theme, str):
                import json
                try:
                    return json.loads(theme)
                except Exception:
                    return None
            return theme
        except Exception:
            return None

class BusinessFeatureSerializer(serializers.ModelSerializer):
    class Meta:
        model = BusinessFeature
        fields = ['feature_id', 'details']

class Businesssection1serializers(serializers.ModelSerializer):
    logo_url = serializers.SerializerMethodField()
    banner_url = serializers.SerializerMethodField()

    class Meta:
        model = Business
        fields = [
            'businessName', 'businessType', 'businessCategory',
            'description', 'business_hours',
            'level', 'master',
            'businessEmail', 'businessNumber', 'businessWhatsapp',
            'logo_url', 'banner_url'
            ]

    def get_logo_url(self, obj):
        return build_s3_file_url(obj.logo)

    def get_banner_url(self, obj):
        return build_s3_file_url(obj.banner)

    def create(self, validated_data):
        user_id = self.context.get("user_id")

        try:
            user = Registration.objects.get(user_id=user_id, status=True)
        except:
            raise serializers.ValidationError("Invalid userID")

        # Default level = master if not provided
        level = validated_data.get("level", "master").lower()
        master = validated_data.get("master", None)

        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")

        # Master business
        if level == "master":
            business_id = f"KIR{user_id}{timestamp}"
            validated_data["master"] = None

        # Sublevel business
        elif level == "sublevel":
            if not master:
                raise serializers.ValidationError({"master": "Master business_id is required for sublevel"})
            if not Business.objects.filter(business_id=master, level="master").exists():
                raise serializers.ValidationError({"master": "Invalid master business_id"})
            business_id = f"KIR{user_id}{timestamp}"

        else:
            raise serializers.ValidationError({"level": "Invalid level. Must be 'master' or 'sublevel'"})

        validated_data["business_id"] = business_id

        # Pre-fill email/number from user if not mentioned
        if not validated_data.get("businessEmail"):
            validated_data["businessEmail"] = getattr(user, "email", None) or getattr(user, "mobileNumber", None)

        if not validated_data.get("businessNumber"):
            validated_data["businessNumber"] = getattr(user, "mobileNumber", None)

        # Whatsapp default = businessNumber
        if not validated_data.get("businessWhatsapp"):
            validated_data["businessWhatsapp"] = validated_data["businessNumber"]

        # Set status based on business type - R02 should be active by default
        business_type = validated_data.get("businessType", "")
        validated_data["status"] = (business_type == "R02")  # Active for R02, inactive for others

        # Save business
        business = Business.objects.create(**validated_data)

        if level == "master":
            # Only create BusinessMapping if it doesn't exist for this user
            BusinessMapping.objects.get_or_create(
                user=user, 
                defaults={'business': business}
            )

        return business

    def update(self, instance, validated_data):
        # Update business fields
        for field, value in validated_data.items():
            if field not in ['business_id']:  # Don't update business_id
                setattr(instance, field, value)
        
        instance.save()
        return instance

class Businesssection2Serializer(serializers.ModelSerializer):
    class Meta:
        model = Business
        fields = [
            'business_id', 'location', 'address',
            'landmark', 'city',
            'state', 'pincode',
            'contact_support', 'contact_mobile', 'website_url',
            'business_features', 'latitude', 'longitude'
            ]
    
    def update(self, instance, validated_data):
        # Update address & location fields
        instance.location = validated_data.get("location", instance.location)
        instance.address = validated_data.get("address", instance.address)
        instance.landmark = validated_data.get("landmark", instance.landmark)
        instance.city = validated_data.get("city", instance.city)
        instance.state = validated_data.get("state", instance.state)
        instance.pincode = validated_data.get("pincode", instance.pincode)
        instance.contact_support = validated_data.get("contact_support", instance.contact_support)
        instance.contact_mobile = validated_data.get("contact_mobile", instance.contact_mobile)
        instance.website_url = validated_data.get("website_url", instance.website_url)
        instance.business_features = validated_data.get("business_features", instance.business_features)
        instance.latitude = validated_data.get("latitude", instance.latitude)
        instance.longitude = validated_data.get("longitude", instance.longitude)

        instance.save()
        return instance

class Businesssection3Serializer(serializers.ModelSerializer):
    business_id = serializers.CharField(write_only=True)

    class Meta:
        model = BusinessFinancial
        exclude = ['business'] 

    def create(self, validated_data):
        business_id = validated_data.pop("business_id", None)
        
        if not business_id:
            raise serializers.ValidationError({"business_id": "This field is required."})

        try:
            business = Business.objects.get(business_id=business_id)
        except Business.DoesNotExist:
            raise serializers.ValidationError({"business_id": "Invalid business_id"})

        # Set default Razorpay credentials from settings if not provided
        if not validated_data.get('razor_pay_key_id'):
            validated_data['razor_pay_key_id'] = getattr(settings, 'RAZORPAY_KEY_ID', '')
        
        if not validated_data.get('razor_pay_key_code'):
            validated_data['razor_pay_key_code'] = getattr(settings, 'RAZORPAY_KEY_SECRET', '')
        
        if not validated_data.get('razor_webhook_secret'):
            validated_data['razor_webhook_secret'] = getattr(settings, 'RAZORPAY_WEBHOOK_SECRET', '')

        try:
            # Add business instance to validated data
            validated_data['business'] = business
            
            # Create new financial record
            financial = BusinessFinancial.objects.create(**validated_data)
            return financial
            
        except Exception as e:
            raise serializers.ValidationError({"error": str(e)})

class LenientJSONField(serializers.JSONField):
    """
    Custom JSONField that accepts both JSON strings and objects from FormData.
    This bypasses DRF's strict JSON validation that rejects valid JSON strings from multipart/form-data.
    """
    def to_internal_value(self, data):
        # Check if it's DRF's JSONString wrapper
        # JSONString is created when a dict is passed through QueryDict
        # It's a str subclass but contains the original dict value
        if type(data).__name__ == 'JSONString':
            # JSONString stores the dict as a Python repr string (with single quotes)
            # Use ast.literal_eval to safely parse it back to a dict
            try:
                import ast
                return ast.literal_eval(str(data))
            except (ValueError, SyntaxError) as e:
                self.fail('invalid', error=str(e))
        
        # If it's already a dict/list, return as-is
        if isinstance(data, (dict, list)):
            return data
        
        # If it's a string, try to parse it as JSON
        if isinstance(data, str):
            if not data or data.strip() == '':
                return None
            try:
                import json
                return json.loads(data)
            except (json.JSONDecodeError, ValueError, TypeError) as e:
                self.fail('invalid', error=str(e))
        
        # If it's None, return None
        if data is None:
            return None
        
        # Otherwise, let the parent handle it
        return super().to_internal_value(data)


class MenuItemsSerializer(serializers.ModelSerializer):
    item_image_url = serializers.SerializerMethodField()
    gst_percentage = serializers.DecimalField(max_digits=5, decimal_places=2, required=False, source='gst')
    sku = serializers.CharField(max_length=255, required=False, allow_blank=True, allow_null=True)
    size_label = serializers.CharField(max_length=225, required=False, allow_blank=True)
    category_id = serializers.IntegerField(required=False, allow_null=True)
    category_name = serializers.SerializerMethodField()  # Uses get_category_name method
    sub_Category_id = serializers.IntegerField(required=False, allow_null=True, source='sub_category_id')
    sub_category_name = serializers.SerializerMethodField()
    availability_timings = LenientJSONField(required=False, allow_null=True)
    variants = serializers.SerializerMethodField()
    
    class Meta:
        model = MenuItems
        fields = [
            'item_id', 'item_name', 'sku', 'description',
            'item_image', 'item_image_url',
            'category_id', 'category_name', 'sub_Category_id', 'sub_category_name', 'item_type', 'availability_timings', 'preparation_time',
            'quantity', 'gst', 'gst_percentage', 'charges','size_label', 'selling_price',
            'is_active', 'status', 'is_variable', 'variants', 'created_at', 'updated_at'
        ]
        read_only_fields = ['item_id', 'charges', 'created_at', 'updated_at']
        extra_kwargs = {
            'selling_price': {'required': False}
        }

    def _normalize_item_image_db_path(self, instance):
        """Ensure the database stores the image path with 'media/' prefix"""
        if instance.item_image and instance.item_image.name:
            current_path = instance.item_image.name
            # If path doesn't start with 'media/', add it
            if not current_path.startswith('media/'):
                # Normalize folder name: menuitems -> menuItems
                if current_path.startswith('menuitems/'):
                    current_path = 'menuItems/' + current_path[len('menuitems/'):]
                elif not current_path.startswith('menuItems/'):
                    current_path = f'menuItems/{current_path}' if '/' not in current_path else current_path
                
                # Add media/ prefix
                new_path = f'media/{current_path}'
                
                # Update the database field directly
                from django.db import connection
                with connection.cursor() as cursor:
                    cursor.execute(
                        "UPDATE menuItems SET item_image = %s WHERE item_id = %s",
                        [new_path, instance.item_id]
                    )
                # Refresh the instance
                instance.refresh_from_db()

    def get_category_name(self, obj):
        # First check if item_category has a value (this is what frontend sends)
        if hasattr(obj, 'item_category') and obj.item_category:
            return obj.item_category
        
        # Fallback to category_id lookup
        if hasattr(obj, 'category_id') and obj.category_id:
            from django.db import connection
            with connection.cursor() as cursor:
                cursor.execute("SELECT category_name FROM universal_Categories WHERE category_id = %s", [obj.category_id])
                row = cursor.fetchone()
                return row[0] if row else None
        return None

    def get_sub_category_name(self, obj):
        """Returns the sub_category name (aliased as sub_category_name)"""
        if hasattr(obj, 'sub_category_id') and obj.sub_category_id:
            from django.db import connection
            with connection.cursor() as cursor:
                cursor.execute("SELECT category_name FROM universal_Categories WHERE category_id = %s", [obj.sub_category_id])
                row = cursor.fetchone()
                if row:
                    return row[0]
        if hasattr(obj, 'sub_category') and obj.sub_category:
            return obj.sub_category
        return None
    
    def get_variants(self, obj):
        if hasattr(obj, 'variants'):
            variants = obj.variants.all()  # Get all variants, not just active ones
            variant_data = []
            for variant in variants:
                # Can add to cart only if variant is active AND has stock > 0
                variant_is_active = variant.is_active
                variant_stock = variant.stock_qty if variant.stock_qty is not None else 0
                can_add_to_cart = variant_is_active and variant_stock > 0
                
                variant_dict = {
                    'variant_id': variant.variant_id,
                    'item': variant.item.item_id,
                    'size_label': variant.size_label,
                    'sku': variant.sku,
                    'selling_price': f"{round(float(variant.selling_price)):.2f}" if variant.selling_price else None,
                    'mrp': f"{round(float(variant.mrp)):.2f}" if variant.mrp else None,
                    'original_cost': f"{round(float(variant.original_cost)):.2f}" if variant.original_cost else None,
                    'stock_qty': variant.stock_qty,
                    'charges': f"{variant.charges:.2f}" if variant.charges else None,
                    'gst': f"{variant.gst:.2f}" if variant.gst else None,
                    'is_active': variant.is_active,
                    'can_add_to_cart': can_add_to_cart,
                    'created_at': variant.created_at,
                    'updated_at': variant.updated_at
                }
                variant_data.append(variant_dict)
            return variant_data
        return []

    def get_item_image_url(self, obj):
        return build_s3_file_url(obj.item_image)

    def update(self, instance, validated_data):
        # Handle category updates with priority
        category_name = validated_data.pop('category_name', None)
        
        if category_name is not None:
            # Priority 1: Use sent category_name
            instance.item_category = category_name
            
            # Try to find matching category_id for consistency
            try:
                from django.db import connection
                with connection.cursor() as cursor:
                    cursor.execute(
                        "SELECT category_id FROM universal_Categories WHERE category_name = %s", 
                        [category_name]
                    )
                    row = cursor.fetchone()
                    if row:
                        instance.category_id = row[0]
            except Exception:
                # If lookup fails, keep existing category_id
                pass
        
        elif 'category_id' in validated_data:
            # Priority 2: Use category_id lookup if category_name not sent
            category_id = validated_data.get('category_id')
            if category_id:
                try:
                    from django.db import connection
                    with connection.cursor() as cursor:
                        cursor.execute(
                            "SELECT category_name FROM universal_Categories WHERE category_id = %s", 
                            [category_id]
                        )
                        row = cursor.fetchone()
                        if row:
                            instance.item_category = row[0]
                except Exception:
                    # If lookup fails, clear item_category
                    instance.item_category = None
        
        # Handle other updates normally
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        
        # Save instance
        instance.save()
        
        # CRITICAL: Verify what was actually saved and return fresh data
        instance.refresh_from_db()
        
        return instance

    def to_representation(self, instance):
        """Override to ensure both item_image and item_image_url use clean URLs"""
        representation = super().to_representation(instance)
        
        # Get the clean S3 URL
        clean_url = build_s3_file_url(instance.item_image)
        
        # Update both fields with the clean URL
        representation['item_image'] = clean_url
        representation['item_image_url'] = clean_url
        
        return representation

class MenuItemsWithVariantsSerializer(MenuItemsSerializer):
    # ... (rest of the code remains the same)

    def get_variants(self, obj):
        # Override to ensure all variants are fetched regardless of parent item status
        if hasattr(obj, 'variants'):
            variants = obj.variants.all()  # Get all variants, not just active ones
            variant_data = []
            for variant in variants:
                # Can add to cart only if variant is active AND has stock > 0
                variant_is_active = variant.is_active
                variant_stock = variant.stock_qty if variant.stock_qty is not None else 0
                can_add_to_cart = variant_is_active and variant_stock > 0
                
                variant_dict = {
                    'variant_id': variant.variant_id,
                    'item': variant.item.item_id,
                    'size_label': variant.size_label,
                    'sku': variant.sku,
                    'selling_price': f"{round(float(variant.selling_price)):.2f}" if variant.selling_price else None,
                    'mrp': f"{round(float(variant.mrp)):.2f}" if variant.mrp else None,
                    'original_cost': f"{round(float(variant.original_cost)):.2f}" if variant.original_cost else None,
                    'stock_qty': variant.stock_qty,
                    'charges': f"{variant.charges:.2f}" if variant.charges else None,
                    'gst': f"{variant.gst:.2f}" if variant.gst else None,
                    'is_active': variant.is_active,
                    'can_add_to_cart': can_add_to_cart,
                    'created_at': variant.created_at,
                    'updated_at': variant.updated_at
                }
                variant_data.append(variant_dict)
            return variant_data
        return []


class BOMSerializer(serializers.ModelSerializer):
    category_id = serializers.ReadOnlyField(source='product_id.category_id')
    category_name = serializers.SerializerMethodField()
    sub_Category_id = serializers.ReadOnlyField(source='product_id.sub_category_id')
    sub_category = serializers.ReadOnlyField(source='product_id.sub_category')
    
    class Meta:
        model = BOM
        fields = [
            'bom_id', 'business_id', 'product_id', 'ingredients', 'quantity', 'unit', 'cost', 'status', 
            'category_id', 'category_name', 'sub_Category_id', 'sub_category',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['bom_id', 'business_id', 'product_id', 'created_at', 'updated_at']

    def get_category_name(self, obj):
        if obj.product_id and obj.product_id.category_id:
            from django.db import connection
            with connection.cursor() as cursor:
                cursor.execute("SELECT category_name FROM universal_Categories WHERE category_id = %s", [obj.product_id.category_id])
                row = cursor.fetchone()
                return row[0] if row else None
        return None

    def validate_cost(self, value):
        """Validate that cost is positive"""
        if value <= 0:
            raise serializers.ValidationError("Cost must be greater than 0")
        return value

    def validate_quantity(self, value):
        """Validate that quantity is positive"""
        if value <= 0:
            raise serializers.ValidationError("Quantity must be greater than 0")
        return value

    def validate_ingredients(self, value):
        """Validate that ingredients is not empty"""
        if not value or not value.strip():
            raise serializers.ValidationError("Ingredients cannot be empty")
        return value.strip()

    def validate_unit(self, value):
        """Validate that unit is not empty"""
        if not value or not value.strip():
            raise serializers.ValidationError("Unit cannot be empty")
        return value.strip()


class GroceriesCategorySerializer(serializers.ModelSerializer):
    business_id = serializers.CharField(write_only=True)
    business_name = serializers.CharField(source='business.businessName', read_only=True)
    # Accept parent category as a NAME string from the client.
    # We map it directly into the parent_category field (db_column='parent_category_id')
    parent_category_id = serializers.CharField(write_only=True, required=False, allow_blank=True, allow_null=True)
    parent_category_name = serializers.CharField(write_only=True, required=False, allow_blank=True)

    class Meta:
        model = GroceriesCategories
        fields = [
            'category_id', 'business_id', 'business_name',
            'category_name', 'parent_category', 'parent_category_id', 'parent_category_name', 'gst_rate',
            'category_image', 'created_at', 'updated_at'
        ]
        read_only_fields = ['category_id', 'created_at', 'updated_at']

    def create(self, validated_data):
        business_id = validated_data.pop('business_id', None)
        parent_category_id = validated_data.pop('parent_category_id', None)
        parent_category_name = validated_data.pop('parent_category_name', None)

        if not business_id:
            raise serializers.ValidationError({'business_id': 'This field is required.'})

        try:
            business = Business.objects.get(business_id=business_id)
        except Business.DoesNotExist:
            raise serializers.ValidationError({'business_id': 'Invalid business_id'})

        validated_data['business'] = business

        # Determine parent category NAME (string) from the incoming fields, if any.
        parent_name = None
        if parent_category_id:
            parent_name = str(parent_category_id).strip() or None
        if not parent_name and parent_category_name:
            parent_name = str(parent_category_name).strip() or None

        if parent_name:
            # Store the name directly in the parent_category field (VARCHAR column parent_category_id)
            validated_data['parent_category'] = parent_name

        return super().create(validated_data)

    def update(self, instance, validated_data):
        business_id = validated_data.pop('business_id', None)
        parent_category_id = validated_data.pop('parent_category_id', None)
        parent_category_name = validated_data.pop('parent_category_name', None)

        if business_id is not None:
            try:
                business = Business.objects.get(business_id=business_id)
            except Business.DoesNotExist:
                raise serializers.ValidationError({'business_id': 'Invalid business_id'})
            validated_data['business'] = business
        else:
            business = instance.business

        # Determine parent category NAME (string) from incoming fields.
        parent_name = None
        if parent_category_id is not None:
            parent_name = str(parent_category_id).strip() or None
        if not parent_name and parent_category_name:
            parent_name = str(parent_category_name).strip() or None

        # If explicitly provided as empty string or null, clear the parent
        if parent_category_id == "" or parent_category_id is None and parent_category_name == "":
            validated_data['parent_category'] = None
        elif parent_name:
            validated_data['parent_category'] = parent_name

        return super().update(instance, validated_data)


class productItemsSerializer(serializers.ModelSerializer):
    import json
    import re
    from datetime import datetime
    from rest_framework import serializers
    from .models import productItems
    
    item_image_url = serializers.SerializerMethodField()

    class Meta:
        model = productItems
        fields = [
            'item_id', 'business_id', 'item_name', 'item_image', 'item_image_url',
            'item_type', 'material', 'gender', 'color',
            'item_category', 'description', 'item_placed_at', 'is_organic',
            'availability_timings', 'weight', 'size', 'unit',
            'rating', 'original_cost', 'gst', 'charges',
            'selling_price', 'wallet_points_availablity',
            'wallet_points', 'mfg_data', 'expiry_date',
            'stock', 'sub_images', 'is_featured', 'is_active', 'status', 'created_at', 'updated_at'
        ]
        read_only_fields = ['item_id', 'business_id', 'created_at', 'updated_at']
        extra_kwargs = {
            'sub_images': {'read_only': True, 'required': False},
        }
    
    def _normalize_item_image_db_path(self, instance):
        """Ensure the database stores the image path with 'media/' prefix"""
        if instance.item_image and instance.item_image.name:
            current_path = instance.item_image.name
            # If path doesn't start with 'media/', add it
            if not current_path.startswith('media/'):
                # Check business type to determine correct folder
                try:
                    business_type = instance.business_id.businessType if instance.business_id else None
                    if business_type == 'R01':  # Grocery business
                        if not current_path.startswith('grocery/'):
                            current_path = f'grocery/{current_path}' if '/' not in current_path else current_path
                    else:
                        # Default productItems folder for other business types
                        if not current_path.startswith('productItems/'):
                            current_path = f'productItems/{current_path}' if '/' not in current_path else current_path
                except Exception:
                    # Fallback to productItems folder
                    if not current_path.startswith('productItems/'):
                        current_path = f'productItems/{current_path}' if '/' not in current_path else current_path
                
                # Add media/ prefix
                new_path = f'media/{current_path}'
                
                # Update the database field directly
                from django.db import connection
                with connection.cursor() as cursor:
                    cursor.execute(
                        "UPDATE productItems SET item_image = %s WHERE item_id = %s",
                        [new_path, instance.item_id]
                    )
                # Refresh the instance
                instance.refresh_from_db()
    
    def get_item_image_url(self, obj):
        return build_s3_file_url(obj.item_image)
    
    def to_representation(self, instance):
        rep = super().to_representation(instance)
        url = build_s3_file_url(instance.item_image)
        rep['item_image'] = url
        rep['item_image_url'] = url
        return rep
    
    def validate_selling_price(self, value):
        if value <= 0:
            raise serializers.ValidationError("Selling price must be greater than 0")
        return value
    
    def validate_wallet_points_availablity(self, value):
        if value in [0, 1]:
            return bool(value)
        return value
    
    def validate_is_active(self, value):
        if isinstance(value, str):
            if value.lower() in ('true', '1', 'yes'):
                return True
            elif value.lower() in ('false', '0', 'no'):
                return False
        return bool(value)
    
    def validate_status(self, value):
        if isinstance(value, str):
            if value.lower() in ('true', '1', 'yes'):
                return True
            elif value.lower() in ('false', '0', 'no'):
                return False
        return bool(value)
    
    def validate_mfg_data(self, value):
        if value and value > datetime.now().date():
            raise serializers.ValidationError("Manufacturing date cannot be in the future")
        return value
        
    def validate_expiry_date(self, value):
        if value and 'mfg_data' in self.initial_data:
            if value <= datetime.strptime(self.initial_data['mfg_data'], '%Y-%m-%d').date():
                raise serializers.ValidationError("Expiry date must be after manufacturing date")
        return value
    
    def validate_availability_timings(self, value):
        if not value:
            return value
            
        if isinstance(value, str):
            try:
                value = json.loads(value)
            except json.JSONDecodeError:
                raise serializers.ValidationError("Availability timings must be valid JSON")
        
        if not isinstance(value, dict):
            raise serializers.ValidationError("Availability timings must be a JSON object")
        
        valid_days = ['mon', 'tue', 'wed', 'thu', 'fri', 'sat', 'sun']
        
        for day, timings in value.items():
            if day not in valid_days:
                raise serializers.ValidationError(f"Invalid day: {day}. Must be one of {valid_days}")
            
            if not isinstance(timings, list):
                raise serializers.ValidationError(f"Timings for {day} must be a list")
            
            for timing in timings:
                if not isinstance(timing, dict):
                    raise serializers.ValidationError(f"Each timing entry for {day} must be an object")
                
                if 'open' not in timing or 'close' not in timing:
                    raise serializers.ValidationError(f"Each timing entry must have 'open' and 'close' fields")
                
                time_pattern = r'^([0-1]?[0-9]|2[0-3]):[0-5][0-9]$'
                if not re.match(time_pattern, timing['open']) or not re.match(time_pattern, timing['close']):
                    raise serializers.ValidationError("Time format must be HH:MM (24-hour format)")
        
        return value
    
    def create(self, validated_data):
        original_cost = validated_data.get('original_cost')
        gst = validated_data.get('gst')
        if original_cost and gst:
            # Ensure both values are Decimal for multiplication
            from decimal import Decimal
            original_cost = Decimal(str(original_cost)) if not isinstance(original_cost, Decimal) else original_cost
            gst = Decimal(str(gst)) if not isinstance(gst, Decimal) else gst
            validated_data['charges'] = (original_cost * gst) / 100
        
        # Force is_active and status to True (1) when creating new product items
        validated_data['is_active'] = True
        validated_data['status'] = True
        
        # Set other default values if not provided
        validated_data.setdefault('wallet_points_availablity', False)
        validated_data.setdefault('wallet_points', 0)
        validated_data.setdefault('stock', 0)
        
        obj = super().create(validated_data)
        self._normalize_item_image_db_path(obj)
        return obj
    
    def update(self, instance, validated_data):
        if 'original_cost' in validated_data or 'gst' in validated_data:
            original_cost = validated_data.get('original_cost', instance.original_cost)
            gst = validated_data.get('gst', instance.gst)
            if original_cost and gst:
                # Ensure both values are Decimal for multiplication
                from decimal import Decimal
                original_cost = Decimal(str(original_cost)) if not isinstance(original_cost, Decimal) else original_cost
                gst = Decimal(str(gst)) if not isinstance(gst, Decimal) else gst
                validated_data['charges'] = (original_cost * gst) / 100
        
        # Get business type to determine sync behavior
        business_type = None
        try:
            if hasattr(instance, 'business_id') and instance.business_id:
                business_type = instance.business_id.businessType
        except Exception:
            pass
        
        # R01 (Grocery): When status changes, sync is_active with status
        # R02 (Restaurant): When status changes, only change status (not is_active)
        if business_type == 'R01':
            # For R01: Sync is_active with status
            if 'status' in validated_data:
                validated_data['is_active'] = bool(validated_data['status'])
            elif 'is_active' in validated_data:
                validated_data['status'] = bool(validated_data['is_active'])
        else:
            # For R02 or other business types: Only change status, not is_active
            # If status is provided but is_active is not, don't auto-sync
            # If is_active is provided but status is not, don't auto-sync
            pass
        
        # Handle date fields
        if 'mfg_data' in validated_data and 'expiry_date' not in validated_data:
            if validated_data['mfg_data'] and instance.expiry_date:
                if instance.expiry_date <= validated_data['mfg_data']:
                    raise serializers.ValidationError(
                        {"expiry_date": "Must be after manufacturing date"}
                    )
        
        obj = super().update(instance, validated_data)
        
        # Normalize image path if image was updated
        if 'item_image' in validated_data:
            self._normalize_item_image_db_path(obj)
        
        return obj

class BusinessFinancialDetailSerializer(serializers.ModelSerializer):
    class Meta:
        model = BusinessFinancial
        fields = [
            'id', 'owner_pan', 'gstin', 'ifsc_code', 
            'account_number', 'razor_pay_key_id', 
            'razor_pay_key_code', 'razor_webhook_secret',
            'fssai_certification_number', 'created_at',
            'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']

# =============================
# Counter POS Serializers
# =============================
try:
    from .models import BusinessCounterOrders, BusinessCounterItems, BusinessCounterLogs
except Exception:
    BusinessCounterOrders = None
    BusinessCounterItems = None
    BusinessCounterLogs = None

if BusinessCounterItems:
    class BusinessCounterItemsSerializer(serializers.ModelSerializer):
        menu_item_id = serializers.PrimaryKeyRelatedField(
            queryset=MenuItems.objects.all(),
            required=False,
            allow_null=True
        )
        item_id = serializers.ReadOnlyField(source='id')
        class Meta:
            model = BusinessCounterItems
            fields = [
                'item_id', 'order_id', 'business_id', 'menu_item_id', 'product_id', 
                'variant_id', 'sku', 'item_name', 'size_label', 'quantity', 'unit_price', 
                'gst', 'line_total', 'is_customized', 'customization_details', 
                'notes', 'created_at', 'updated_at'
            ]
            read_only_fields = ['item_id', 'order_id', 'business_id', 'line_total', 'created_at', 'updated_at']
        def validate(self, data):
            menu_item_id = data.get('menu_item_id')
            product_id = data.get('product_id')
            variant_id = data.get('variant_id')
            # Allow menu_item_id, product_id, or variant_id (variant_id implies product_id exists)
            if not menu_item_id and not product_id and not variant_id:
                raise serializers.ValidationError(
                    "Either menu_item_id (for restaurant items), product_id (for grocery products), or variant_id (for grocery variants) must be provided"
                )
            return data
        def validate_quantity(self, value):
            if value <= 0:
                raise serializers.ValidationError("Quantity must be greater than 0")
            return value
        def validate_unit_price(self, value):
            if value < 0:
                raise serializers.ValidationError("Unit price cannot be negative")
            return value


if BusinessCounterOrders and BusinessCounterItems:
    class BusinessCounterOrdersSerializer(serializers.ModelSerializer):
        items = BusinessCounterItemsSerializer(many=True, read_only=False, required=False)
        
        class Meta:
            model = BusinessCounterOrders
            fields = [
                'order_id', 'business_id', 'user_id', 'username', 'customer_mobile', 'customer_email', 'token_number', 'offline_token_no', 
                'order_type', 'service_mode', 'payment_method', 'subtotal', 'gst_total', 
                'total_amount', 'discount_amount', 'discount_percentage', 'discount_type', 'discount_reason',
                'paid_amount', 'remaining_amount', 'status', 'remarks', 'email_sent', 'delivery_charges', 'customization_charges', 'items', 'created_at', 'updated_at',
                'cancellation_reason', 'cancelled_at'
            ]
            read_only_fields = ['order_id', 'token_number', 'email_sent', 'created_at', 'updated_at']
        
        def validate_customer_mobile(self, value):
            """Allow blank values for customer_mobile"""
            if value is None or value == '':
                return 'skipped'
            return value
        
        def validate_customer_email(self, value):
            """Allow blank values for customer_email"""
            if value is None or value == '':
                return 'skipped'
            return value
        
        def validate_payment_method(self, value):
            allowed_methods = ['cash', 'card', 'upi', 'online', 'wallet']
            if value and value.lower() not in allowed_methods:
                raise serializers.ValidationError(
                    f"Payment method must be one of: {', '.join(allowed_methods)}"
                )
            return value.lower() if value else value
        def validate_order_type(self, value):
            allowed_types = ['menu', 'grocery', 'mixed']
            if value and value.lower() not in allowed_types:
                raise serializers.ValidationError(
                    f"Order type must be one of: {', '.join(allowed_types)}"
                )
            return value.lower() if value else value
        def validate_service_mode(self, value):
            allowed_modes = ['dine_in', 'takeaway', 'pickup', 'delivery']
            if value:
                normalized = value.lower().replace('-', '_').strip()
                # Normalize common aliases
                if normalized == 'pick_up':
                    normalized = 'pickup'
                if normalized not in allowed_modes:
                    raise serializers.ValidationError(
                        f"Service mode must be one of: {', '.join(allowed_modes)}"
                    )
                return normalized
            return value
        def validate(self, data):
            if data.get('subtotal', 0) < 0:
                raise serializers.ValidationError({"subtotal": "Subtotal cannot be negative"})
            if data.get('total_amount', 0) < 0:
                raise serializers.ValidationError({"total_amount": "Total amount cannot be negative"})
            return data
        def create(self, validated_data):
            items_data = validated_data.pop('items', [])
            order = BusinessCounterOrders.objects.create(**validated_data)
            for item_data in items_data:
                item_data['order_id'] = order
                item_data['business_id'] = order.business_id
                BusinessCounterItems.objects.create(**item_data)
            return order
        def update(self, instance, validated_data):
            items_data = validated_data.pop('items', None)
            for attr, value in validated_data.items():
                setattr(instance, attr, value)
            instance.save()
            if items_data is not None:
                instance.items.all().delete()
                for item_data in items_data:
                    item_data['order_id'] = instance
                    item_data['business_id'] = instance.business_id
                    BusinessCounterItems.objects.create(**item_data)
            return instance


if BusinessCounterLogs:
    class BusinessCounterLogsSerializer(serializers.ModelSerializer):
        class Meta:
            model = BusinessCounterLogs
            fields = [
                'log_id', 'business_id', 'user_id', 'action_type', 
                'reference_id', 'old_data', 'new_data', 'description', 
                'ip_address', 'user_agent', 'created_at'
            ]
            read_only_fields = ['log_id', 'created_at']
        def validate_action_type(self, value):
            if not value or not value.strip():
                raise serializers.ValidationError("Action type cannot be empty")
            return value.strip()

class ProductCustomizationTemplateSerializer(serializers.ModelSerializer):
    asset_url_full = serializers.SerializerMethodField()
    
    class Meta:
        model = ProductCustomizationTemplate
        fields = ['id', 'business_id', 'product_id', 'template_name', 'design_type', 'price_delta', 'asset_url', 'asset_url_full', 'max_chars', 'per_char_price', 'flat_price', 'base_price', 'is_active', 'position', 'created_at', 'updated_at', 'options']
        read_only_fields = ['id', 'created_at', 'updated_at', 'options', 'asset_url_full']
    
    def get_asset_url_full(self, obj):
        if obj.asset_url:
            from business.image_utils import build_s3_file_url
            # If asset_url already starts with http, return as is
            if obj.asset_url.startswith('http'):
                return obj.asset_url
            # Use S3 URL builder for consistent URLs
            return build_s3_file_url(obj.asset_url)
        return None


class MenuItemVariantSerializer(serializers.ModelSerializer):
    """Serializer for MenuItemVariant model"""
    class Meta:
        model = MenuItemVariant
        fields = [
            'variant_id', 'item', 'size_label', 'sku', 'selling_price', 'mrp',
            'original_cost', 'stock_qty', 'charges', 'gst', 'is_active',
            'can_add_to_cart', 'rating', 'rating_count', 'created_at', 'updated_at'
        ]
        read_only_fields = ['variant_id', 'created_at', 'updated_at']
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Set can_add_to_cart based on is_active and stock
        if hasattr(self.instance, 'is_active') and hasattr(self.instance, 'stock_qty'):
            self.fields['can_add_to_cart'] = serializers.BooleanField(
                default=self.instance.is_active and (self.instance.stock_qty or 0) > 0
            )


class FashionProductVariantSerializer(serializers.ModelSerializer):
    """Serializer for FashionProductVariant model"""
    class Meta:
        model = FashionProductVariant
        fields = [
            'variant_id', 'business_id', 'product', 'sku', 'barcode',
            'selling_price', 'mrp', 'stock_qty', 'net_weight', 'net_weight_unit',
            'original_cost', 'charges', 'stock', 'mfg_date', 'expiry_date',
            'size', 'color', 'material', 'gender', 'min_age', 'max_age',
            'pack', 'attributes', 'dimension', 'is_active', 'rating', 'rating_count', 'created_at', 'updated_at'
        ]
        read_only_fields = ['variant_id', 'created_at', 'updated_at']
    
    def to_representation(self, instance):
        data = super().to_representation(instance)
        # Round price fields to nearest whole number
        if data.get('selling_price') is not None:
            data['selling_price'] = f"{round(float(data['selling_price'])):.2f}"
        if data.get('mrp') is not None:
            data['mrp'] = f"{round(float(data['mrp'])):.2f}"
        if data.get('original_cost') is not None:
            data['original_cost'] = f"{round(float(data['original_cost'])):.2f}"
        if data.get('charges') is not None:
            data['charges'] = f"{round(float(data['charges'])):.2f}"
        return data


class FashionProductSerializer(serializers.ModelSerializer):
    """Serializer for FashionProduct model"""
    main_image_url = serializers.SerializerMethodField()

    class Meta:
        model = FashionProduct
        fields = [
            'product_id', 'business_id', 'name', 'description', 'main_image', 'main_image_url',
            'category', 'subcategory', 'brand', 'base_price', 'gst_rate_default', 'hsn_code',
            'is_featured', 'rating', 'is_active', 'created_at', 'updated_at'
        ]
        read_only_fields = ['product_id', 'created_at', 'updated_at']

    def get_main_image_url(self, obj):
        return build_s3_file_url(obj.main_image)

    def to_representation(self, instance):
        rep = super().to_representation(instance)
        url = build_s3_file_url(instance.main_image)
        rep['main_image'] = url
        rep['main_image_url'] = url
        return rep


class FashionProductWithVariantsSerializer(FashionProductSerializer):
    variants = FashionProductVariantSerializer(many=True, read_only=True)
    
    class Meta(FashionProductSerializer.Meta):
        fields = FashionProductSerializer.Meta.fields + ['variants']
