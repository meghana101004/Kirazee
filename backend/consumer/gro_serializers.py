from rest_framework import serializers
from django.db import models
from .gro_models import GroceriesCategories, GroceriesProducts, GroceriesProductVariants, GroceriesCart, GroceriesPayments, GroceriesOrders, GroceriesOrderItems, GroceryPartner, GroceryDeliverDetails, GroceriesRatingHistory, BusinessFeedback, GroceriesCustomDesigns
from datetime import date
from django.db import transaction
from consumer.image_utils import build_s3_file_url
import logging
import math

logger = logging.getLogger(__name__)



class GroceriesCategoriesSerializer(serializers.ModelSerializer):
    # parent_category already stores the parent category NAME (from parent_category_id column)
    parent_category_name = serializers.CharField(source='parent_category', read_only=True)

    class Meta:
        model = GroceriesCategories
        fields = ['category_id', 'category_name', 'parent_category', 'parent_category_name', 'gst_rate', 'category_image', 'created_at', 'updated_at']


class GroceriesProductsSerializer(serializers.ModelSerializer):
    category_name = serializers.SerializerMethodField()
    business_name = serializers.CharField(source='business.business_name', read_only=True)
    parent_category_name = serializers.SerializerMethodField()
    product_image = serializers.SerializerMethodField()
    main_image_url = serializers.SerializerMethodField()
    sub_images_url = serializers.SerializerMethodField()
    
    class Meta:
        model = GroceriesProducts
        fields = ['product_id', 'business', 'business_name', 'product_name', 'brand_name', 'category', 'category_name', 'parent_category_name', 'sub_category', 'sub_category_id', 'description', 'item_placed_at', 'main_image', 'sub_images', 'sub_images_url', 'is_featured', 'is_customizable', 'product_image', 'main_image_url', 'base_price', 'is_organic', 'is_visible', 'rating', 'created_at', 'updated_at']
        extra_kwargs = {
            'business': {'required': False, 'allow_null': True},
            'product_name': {'required': False},
            'category': {'required': False, 'allow_null': True},
            'sub_images': {'required': False},
        }

    def get_category_name(self, obj):
        try:
            cat = getattr(obj, 'category', None)
            return getattr(cat, 'category_name', None) if cat else None
        except Exception:
            return None
    
    def get_main_image_url(self, obj):
        """Generate S3 URL for grocery product images"""
        image_path = (getattr(obj, 'main_image', '') or '').strip()
        if not image_path:
            return None
        return build_s3_file_url(image_path)
    
    def get_parent_category_name(self, obj):
        try:
            if obj.category and getattr(obj.category, 'parent_category', None):
                # parent_category is a string name when set
                return obj.category.parent_category
            return obj.category.category_name if obj.category else None
        except Exception:
            return None

    def get_sub_images_url(self, obj):
        """Generate S3 URLs for sub_images"""
        sub_images = getattr(obj, 'sub_images', None)
        if not sub_images:
            return []
        
        # Handle both object format and legacy array format
        if isinstance(sub_images, dict):
            urls = []
            for key, image_path in sub_images.items():
                if image_path:
                    url = build_s3_file_url(image_path)
                    if url:
                        urls.append(url)
            return urls
        elif isinstance(sub_images, list):
            urls = []
            for image_path in sub_images:
                if image_path:
                    url = build_s3_file_url(image_path)
                    if url:
                        urls.append(url)
            return urls
        return []

    def get_product_image(self, obj):
        """Alias for main_image_url for backward compatibility"""
        return self.get_main_image_url(obj)
    
    def to_representation(self, instance):
        rep = super().to_representation(instance)
        # Ensure both fields have the proper S3 URL
        url = self.get_main_image_url(instance)
        rep['main_image'] = url
        rep['product_image'] = url
        rep['main_image_url'] = url
        # Add sub_images_url
        rep['sub_images_url'] = self.get_sub_images_url(instance)

        # Ensure sub_images values are also S3 URLs
        sub_images = rep.get('sub_images')
        if isinstance(sub_images, dict):
            updated = {}
            for k, image_path in sub_images.items():
                if image_path:
                    updated[k] = build_s3_file_url(image_path)
            rep['sub_images'] = updated
        return rep


class GroceriesCustomDesignsSerializer(serializers.ModelSerializer):
    asset_url = serializers.SerializerMethodField()

    class Meta:
        model = GroceriesCustomDesigns
        fields = '__all__'

    def get_asset_url(self, obj):
        return build_s3_file_url(obj.asset_url)
    
    def validate_is_visible(self, value):
        if value is None:
            return None
        if isinstance(value, str):
            v = value.strip().lower()
            if v in ('1', 'true', 'yes', 'y'):
                return True
            if v in ('0', 'false', 'no', 'n'):
                return False
        return bool(value)


class GroceriesProductsWithVariantInfoSerializer(serializers.ModelSerializer):
    """Enhanced product serializer that includes variant information for order items"""
    category_name = serializers.CharField(source='category.category_name', read_only=True)
    business_name = serializers.CharField(source='business.business_name', read_only=True)
    product_image = serializers.SerializerMethodField()
    main_image_url = serializers.SerializerMethodField()
    net_weight = serializers.SerializerMethodField()
    net_weight_unit = serializers.SerializerMethodField()
    
    class Meta:
        model = GroceriesProducts
        fields = ['product_id', 'business', 'business_name', 'product_name', 'brand_name', 'category', 'category_name', 'sub_category', 'description', 'main_image', 'product_image', 'main_image_url', 'is_organic', 'is_visible', 'rating', 'net_weight', 'net_weight_unit', 'created_at', 'updated_at']
        extra_kwargs = {
            'business': {'required': False, 'allow_null': True},
            'product_name': {'required': False},
            'category': {'required': False, 'allow_null': True},
        }

    def get_main_image_url(self, obj):
        """Generate S3 URL for grocery product images"""
        image_path = (getattr(obj, 'main_image', '') or '').strip()
        if not image_path:
            return None
        return build_s3_file_url(image_path)

    def get_product_image(self, obj):
        return self.get_main_image_url(obj)

    def to_representation(self, instance):
        rep = super().to_representation(instance)
        url = self.get_main_image_url(instance)
        rep['main_image'] = url
        rep['product_image'] = url
        rep['main_image_url'] = url
        return rep
    
    def get_net_weight(self, obj):
        """Get net weight from the first active variant"""
        try:
            # Try to get from prefetched data first
            if hasattr(obj, 'groceriesproductvariants_set'):
                variants = [v for v in obj.groceriesproductvariants_set.all() if v.is_active]
                if variants:
                    return float(variants[0].net_weight) if variants[0].net_weight else 0.0
            
            # Fallback to database query
            variant = obj.groceriesproductvariants_set.filter(is_active=True).first()
            if variant and variant.net_weight:
                return float(variant.net_weight)
            return 0.0
        except Exception:
            return 0.0
    
    def get_net_weight_unit(self, obj):
        """Get net weight unit from the first active variant"""
        try:
            # Try to get from prefetched data first
            if hasattr(obj, 'groceriesproductvariants_set'):
                variants = [v for v in obj.groceriesproductvariants_set.all() if v.is_active]
                if variants:
                    return variants[0].net_weight_unit or 'pcs'
            
            # Fallback to database query
            variant = obj.groceriesproductvariants_set.filter(is_active=True).first()
            if variant:
                return variant.net_weight_unit or 'pcs'
            return 'pcs'
        except Exception:
            return 'pcs'


class GroceriesProductVariantsSerializer(serializers.ModelSerializer):
    product_name = serializers.CharField(source='product.product_name', read_only=True)
    category_name = serializers.CharField(source='product.category.category_name', read_only=True)
    sku = serializers.CharField(max_length=100, required=False, allow_blank=True, allow_null=True)
    # Human-readable representation of the JSON size field
    size_display = serializers.SerializerMethodField()
    # Computed effective price using the pricing service
    calculated_price = serializers.SerializerMethodField()

    class Meta:
        model = GroceriesProductVariants
        fields = [
            'variant_id', 'product', 'product_name', 'category_name',
            'sku', 'barcode',
            'net_weight', 'net_weight_unit',
            'size', 'size_display',
            'color', 'gender', 'age', 'min_age', 'max_age', 'material', 'attributes', 'pack',
            'is_visible_counter',
            'original_cost', 'selling_price', 'price_override', 'charges', 'gst',
            'calculated_price',
            'stock', 'mfg_date', 'expiry_date',
            'rating', 'rating_count',
            'is_active', 'created_at', 'updated_at',
        ]

    def get_size_display(self, obj):
        """Return a human-readable string for the JSON size field."""
        size = obj.size
        if not size:
            return None
        if isinstance(size, dict):
            # {"value": "1L"} -> "1L"
            if 'value' in size:
                return str(size['value'])
            # {"length": 10, "breadth": 5, "width": 3} -> "10x5x3"
            parts = [f"{k}: {v}" for k, v in size.items() if v is not None]
            return ', '.join(parts) if parts else None
        return str(size)

    def get_calculated_price(self, obj):
        """Return the effective price using the pricing service."""
        try:
            from .gro_services import calculate_variant_price
            return calculate_variant_price(obj)
        except Exception:
            return None

    def validate_is_active(self, value):
        """Convert string boolean values to actual boolean"""
        if isinstance(value, str):
            if value.lower() in ('true', '1', 'yes'):
                return True
            elif value.lower() in ('false', '0', 'no'):
                return False
        return value

    def to_representation(self, instance):
        data = super().to_representation(instance)
        # Round price fields to nearest whole number
        if data.get('original_cost') is not None:
            data['original_cost'] = f"{round(float(data['original_cost'])):.2f}"
        if data.get('selling_price') is not None:
            data['selling_price'] = f"{round(float(data['selling_price'])):.2f}"
        if data.get('price_override') is not None:
            data['price_override'] = f"{round(float(data['price_override'])):.2f}"
        if data.get('charges') is not None:
            data['charges'] = f"{round(float(data['charges'])):.2f}"
        if data.get('gst') is not None:
            data['gst'] = f"{round(float(data['gst'])):.2f}"
        return data

    def validate_is_visible_counter(self, value):
        if isinstance(value, str):
            if value.lower() in ('true', '1', 'yes'):
                return True
            elif value.lower() in ('false', '0', 'no'):
                return False
        return bool(value) if value is not None else True


class GroceriesProductWithPricingSerializer(serializers.ModelSerializer):
    """Combined serializer that includes product info with pricing from variants"""
    category_name = serializers.SerializerMethodField()
    business_name = serializers.CharField(source='business.business_name', read_only=True)
    main_image_url = serializers.SerializerMethodField()
    selling_price = serializers.SerializerMethodField()
    original_cost = serializers.SerializerMethodField()
    stock = serializers.SerializerMethodField()
    net_weight = serializers.SerializerMethodField()
    net_weight_unit = serializers.SerializerMethodField()
    size = serializers.SerializerMethodField()
    variants = serializers.SerializerMethodField()
    default_variant_id = serializers.SerializerMethodField()
    gst = serializers.SerializerMethodField()
    offer_percent = serializers.SerializerMethodField()
    offer_text = serializers.SerializerMethodField()
    
    class Meta:
        model = GroceriesProducts
        fields = ['product_id', 'business', 'business_name', 'product_name', 'brand_name', 'category', 'category_name', 'sub_category',
                 'description', 'main_image', 'main_image_url', 'is_organic', 'is_visible', 'is_customizable', 'rating', 'selling_price', 'original_cost', 'stock', 
                 'net_weight', 'net_weight_unit', 'size', 'created_at', 'updated_at', 'variants', 'default_variant_id', 'gst',
                 'offer_percent', 'offer_text']

    def get_is_customizable(self, obj):
        """Get is_customizable from product model"""
        return getattr(obj, 'is_customizable', False)

    def get_category_name(self, obj):
        try:
            cat = getattr(obj, 'category', None)
            return getattr(cat, 'category_name', None) if cat else None
        except Exception:
            return None

    def get_main_image_url(self, obj):
        """Generate S3 URL for grocery product images"""
        image_path = (getattr(obj, 'main_image', '') or '').strip()
        if not image_path:
            return None
        return build_s3_file_url(image_path)

    def to_representation(self, instance):
        rep = super().to_representation(instance)
        url = self.get_main_image_url(instance)
        rep['main_image'] = url
        rep['main_image_url'] = url
        return rep
    
    def get_selling_price(self, obj):
        """Get selling price from the first active variant - OPTIMIZED"""
        # Use prefetched data instead of querying database
        variants = [v for v in obj.groceriesproductvariants_set.all() if v.is_active]
        if variants:
            return float(variants[0].selling_price) if variants[0].selling_price else 0.0
        return 0.0
    
    def get_original_cost(self, obj):
        """Get original cost from the first active variant - OPTIMIZED"""
        # Use prefetched data instead of querying database
        variants = [v for v in obj.groceriesproductvariants_set.all() if v.is_active]
        if variants:
            return float(variants[0].original_cost) if variants[0].original_cost else 0.0
        return 0.0
    
    def get_stock(self, obj):
        """Get total stock from all active variants - OPTIMIZED"""
        # Use prefetched data instead of querying database
        variants = [v for v in obj.groceriesproductvariants_set.all() if v.is_active]
        return sum(v.stock for v in variants if v.stock)
    
    def get_net_weight(self, obj):
        """Get net weight from the first active variant - OPTIMIZED"""
        # Use prefetched data instead of querying database
        variants = [v for v in obj.groceriesproductvariants_set.all() if v.is_active]
        if variants:
            return float(variants[0].net_weight) if variants[0].net_weight else 0.0
        return 0.0
    
    def get_net_weight_unit(self, obj):
        """Get net weight unit from the first active variant - OPTIMIZED"""
        # Use prefetched data instead of querying database
        variants = [v for v in obj.groceriesproductvariants_set.all() if v.is_active]
        return variants[0].net_weight_unit if variants else 'pcs'
    
    def get_size(self, obj):
        """Get size from the first active variant - OPTIMIZED"""
        # Use prefetched data instead of querying database
        variants = [v for v in obj.groceriesproductvariants_set.all() if v.is_active]
        return variants[0].size if variants else None

    def get_variants(self, obj):
        """Return all variants for this product (including inactive for admin view) - OPTIMIZED"""
        # Use prefetched data instead of querying database.
        # Include ALL variants (both active and inactive) for owner/admin management.
        from .gro_services import calculate_variant_price as _calc_price
        variants = list(obj.groceriesproductvariants_set.all())
        variants.sort(key=lambda v: (v.net_weight or 0, v.selling_price or 0))
        result = []
        for v in variants:
            try:
                item = {
                    'variant_id': v.variant_id,
                    'sku': v.sku,
                    'barcode': v.barcode,
                    'net_weight': float(v.net_weight) if v.net_weight is not None else None,
                    'net_weight_unit': v.net_weight_unit,
                    'size': v.size,
                    'size_display': self._size_display(v.size),
                    'color': v.color,
                    'gender': v.gender,
                    'age': v.age,
                    'min_age': v.min_age,
                    'max_age': v.max_age,
                    'material': v.material,
                    'attributes': v.attributes,
                    'pack': v.pack,
                    'is_visible_counter': v.is_visible_counter,
                    'sub_category_id': getattr(v.product, 'sub_category_id', None),
                    'dimension': v.dimension,
                    'original_cost': float(v.original_cost) if v.original_cost is not None else None,
                    'selling_price': float(v.selling_price) if v.selling_price is not None else None,
                    'price_override': float(v.price_override) if v.price_override is not None else None,
                    'gst': float(v.gst) if v.gst is not None else 0.00,
                    'stock': v.stock,
                    'mfg_date': v.mfg_date,
                    'expiry_date': v.expiry_date,
                    'is_active': v.is_active,
                    'base_price': float(v.product.base_price) if v.product and v.product.base_price is not None else 0.0,
                    'calculated_price': _calc_price(v),
                }
            except Exception:
                # Fallback without casting in case of unexpected types
                item = {
                    'variant_id': getattr(v, 'variant_id', None),
                    'sku': getattr(v, 'sku', None),
                    'barcode': getattr(v, 'barcode', None),
                    'net_weight': getattr(v, 'net_weight', None),
                    'net_weight_unit': getattr(v, 'net_weight_unit', None),
                    'size': getattr(v, 'size', None),
                    'size_display': self._size_display(getattr(v, 'size', None)),
                    'color': getattr(v, 'color', None),
                    'gender': getattr(v, 'gender', None),
                    'age': getattr(v, 'age', None),
                    'min_age': getattr(v, 'min_age', None),
                    'max_age': getattr(v, 'max_age', None),
                    'material': getattr(v, 'material', None),
                    'attributes': getattr(v, 'attributes', None),
                    'pack': getattr(v, 'pack', None),
                    'is_visible_counter': getattr(v, 'is_visible_counter', True),
                    'sub_category_id': getattr(getattr(v, 'product', None), 'sub_category_id', None),
                    'original_cost': getattr(v, 'original_cost', None),
                    'selling_price': getattr(v, 'selling_price', None),
                    'price_override': getattr(v, 'price_override', None),
                    'gst': getattr(v, 'gst', 0.00),
                    'stock': getattr(v, 'stock', None),
                    'mfg_date': getattr(v, 'mfg_date', None),
                    'expiry_date': getattr(v, 'expiry_date', None),
                    'is_active': getattr(v, 'is_active', True),
                    'base_price': getattr(getattr(v, 'product', None), 'base_price', 0.0),
                    'calculated_price': _calc_price(v),
                }
            # Compute per-variant discount fields for display consistency
            try:
                oc = float(v.original_cost) if v.original_cost is not None else None
                sp = float(v.selling_price) if v.selling_price is not None else None
                if oc and sp and oc > 0:
                    disc = (oc - sp) / oc * 100.0
                    item['discount_percent'] = round(disc, 2)
                    item['discount_text'] = f"{math.floor(disc)}% OFF"
                else:
                    item['discount_percent'] = 0.0
                    item['discount_text'] = None
            except Exception:
                item['discount_percent'] = None
                item['discount_text'] = None
            result.append(item)
        return result

    @staticmethod
    def _size_display(size):
        """Convert a JSON size value to a human-readable string."""
        if not size:
            return None
        if isinstance(size, dict):
            if 'value' in size:
                return str(size['value'])
            parts = [f"{k}: {v}" for k, v in size.items() if v is not None]
            return ', '.join(parts) if parts else None
        return str(size)

    def get_default_variant_id(self, obj):
        """Choose a default variant (cheapest active) - OPTIMIZED"""
        # Use prefetched data instead of querying database
        variants = [v for v in obj.groceriesproductvariants_set.all() if v.is_active]
        if variants:
            cheapest = min(variants, key=lambda v: v.selling_price or 0)
            return cheapest.variant_id
        return None

    def get_gst(self, obj):
        """Expose GST rate from linked category as a float (percent)."""
        try:
            rate = obj.category.gst_rate if obj.category else None
            return float(rate) if rate is not None else 0.0
        except Exception:
            return 0.0

    def get_offer_percent(self, obj):
        """Compute the best (max) discount percent across active variants for this product - OPTIMIZED"""
        try:
            # Use prefetched data instead of querying database
            variants = [v for v in obj.groceriesproductvariants_set.all() if v.is_active]
            best = None
            for v in variants:
                oc = v.original_cost
                sp = v.selling_price
                try:
                    if oc is not None and sp is not None and float(oc) > 0:
                        d = (float(oc) - float(sp)) / float(oc) * 100.0
                        best = d if best is None else max(best, d)
                except Exception:
                    continue
            return round(float(best), 2) if best is not None else 0.0
        except Exception:
            return 0.0

    def get_offer_text(self, obj):
        """Human-readable offer text like '12% OFF' based on offer_percent."""
        try:
            offer = self.get_offer_percent(obj)
            if offer and offer > 0:
                try:
                    return f"{math.floor(offer)}% OFF"
                except Exception:
                    return f"{int(offer)}% OFF"
            return None
        except Exception:
            return None


class GroceriesCartSerializer(serializers.ModelSerializer):
    product_details = GroceriesProductsSerializer(source='product', read_only=True)
    product_id = serializers.IntegerField(write_only=True)

    class Meta:
        model = GroceriesCart
        fields = ['id', 'user', 'business', 'product_details', 'product_id', 'quantity', 'added_at', 'updated_at']
        read_only_fields = ['user', 'business']


class GroceriesPaymentsSerializer(serializers.ModelSerializer):
    class Meta:
        model = GroceriesPayments
        fields = ['payment_method', 'payment_status', 'transaction_id', 'payment_date']


class GroceriesOrderItemsSerializer(serializers.ModelSerializer):
    item = serializers.SerializerMethodField()

    class Meta:
        model = GroceriesOrderItems
        fields = ['order_item_id', 'item', 'product', 'quantity', 'unit_price', 'gst', 'total_price']
    
    def get_item(self, obj):
        """Get product information with the specific variant details used in this order"""
        product = obj.product
        
        # Get the variant that matches the unit price from this order item
        try:
            # Try to find the variant with matching selling price
            matching_variant = product.groceriesproductvariants_set.filter(
                is_active=True,
                selling_price=obj.unit_price
            ).first()
            
            # If no exact match, get the first active variant as fallback
            if not matching_variant:
                matching_variant = product.groceriesproductvariants_set.filter(is_active=True).first()
            
            # Build the item data with variant information
            item_data = {
                'product_id': product.product_id,
                'business': product.business_id,
                'business_name': product.business.businessName if product.business else '',
                'product_name': product.product_name,
                'brand_name': product.brand_name,
                'category': product.category_id,
                'category_name': product.category.category_name if product.category else '',
                'sub_category': product.sub_category,
                'description': product.description,
                'main_image': product.main_image,
                'product_image': product.main_image,
                'is_organic': product.is_organic,
                'rating': float(product.rating) if product.rating else 0.0,
                'created_at': product.created_at,
                'updated_at': product.updated_at,
            }
            
            # Add variant-specific weight information
            if matching_variant:
                item_data.update({
                    'net_weight': float(matching_variant.net_weight) if matching_variant.net_weight else 0.0,
                    'net_weight_unit': matching_variant.net_weight_unit or 'pcs'
                })
            else:
                item_data.update({
                    'net_weight': 0.0,
                    'net_weight_unit': 'pcs'
                })
            
            return item_data
            
        except Exception as e:
            # Fallback to basic product info without variant details
            return {
                'product_id': product.product_id,
                'business': product.business_id,
                'business_name': product.business.businessName if product.business else '',
                'product_name': product.product_name,
                'brand_name': product.brand_name,
                'category': product.category_id,
                'category_name': product.category.category_name if product.category else '',
                'sub_category': product.sub_category,
                'description': product.description,
                'main_image': product.main_image,
                'product_image': product.main_image,
                'is_organic': product.is_organic,
                'rating': float(product.rating) if product.rating else 0.0,
                'net_weight': 0.0,
                'net_weight_unit': 'pcs',
                'created_at': product.created_at,
                'updated_at': product.updated_at,
            }


class GroceriesOrdersSerializer(serializers.ModelSerializer):
    order_items = GroceriesOrderItemsSerializer(many=True, read_only=True, source='groceriesorderitems_set')
    payments = GroceriesPaymentsSerializer(many=True, read_only=True, source='groceriespayments_set')

    class Meta:
        model = GroceriesOrders
        fields = [
            'order_id', 'user', 'business', 'order_type', 'order_status',
            'payment_status', 'total_amount', 'gst_amount', 'delivery_charge',
            'discount', 'final_amount', 'delivery_address', 'delivery_latitude', 'delivery_longitude', 
            'delivery_time', 'delivery_instructions', 'pickup_time',
            'created_at', 'updated_at', 'order_items', 'payments'
        ]


class OrderItemRequestSerializer(serializers.Serializer):
    product_id = serializers.IntegerField()
    quantity = serializers.IntegerField(min_value=1)
    variant_id = serializers.IntegerField(required=False, allow_null=True)
    
    def validate_product_id(self, value):
        """Validate that the product exists and is active"""
        try:
            product = GroceriesProducts.objects.get(product_id=value)
            if not product:
                raise serializers.ValidationError("Product not found.")
        except GroceriesProducts.DoesNotExist:
            raise serializers.ValidationError("Product does not exist.")
        return value

    def validate(self, attrs):
        """Cross-field validation: if variant_id provided, ensure it belongs to product and is active"""
        product_id = attrs.get('product_id')
        variant_id = attrs.get('variant_id')
        if variant_id is not None:
            try:
                exists = GroceriesProductVariants.objects.filter(
                    variant_id=variant_id,
                    product_id=product_id,
                    is_active=True
                ).exists()
                if not exists:
                    raise serializers.ValidationError({
                        'variant_id': 'Invalid or inactive variant for the specified product.'
                    })
            except Exception:
                raise serializers.ValidationError({'variant_id': 'Invalid variant.'})
        return attrs


class CreateOrderSerializer(serializers.Serializer):
    order_type = serializers.CharField(max_length=20)
    delivery_address = serializers.CharField(max_length=255, allow_blank=True, required=False)
    delivery_latitude = serializers.DecimalField(max_digits=10, decimal_places=8, required=False, allow_null=True)
    delivery_longitude = serializers.DecimalField(max_digits=11, decimal_places=8, required=False, allow_null=True)
    delivery_time = serializers.DateTimeField(required=False)
    delivery_instructions = serializers.CharField(allow_blank=True, required=False)
    pickup_time = serializers.DateTimeField(required=False)
    delivery_charge = serializers.DecimalField(max_digits=10, decimal_places=2, required=False, default=0.00)
    discount = serializers.DecimalField(max_digits=10, decimal_places=2, required=False, default=0.00)
    items = OrderItemRequestSerializer(many=True)

    def validate(self, data):
        if data.get('order_type') == 'delivery':
            if not data.get('delivery_address'):
                raise serializers.ValidationError("Delivery address is required for delivery orders.")
            # Validate that both latitude and longitude are provided for delivery orders
            delivery_lat = data.get('delivery_latitude')
            delivery_lng = data.get('delivery_longitude')
            if delivery_lat is not None and delivery_lng is None:
                raise serializers.ValidationError("Both delivery_latitude and delivery_longitude must be provided together.")
            if delivery_lng is not None and delivery_lat is None:
                raise serializers.ValidationError("Both delivery_latitude and delivery_longitude must be provided together.")
        # If customer scheduled a delivery time, ensure it is not in the past
        if data.get('order_type') == 'delivery' and data.get('delivery_time'):
            try:
                from django.utils import timezone
                if data['delivery_time'] < timezone.now():
                    raise serializers.ValidationError("Delivery time cannot be in the past.")
            except Exception:
                # If parsing or timezone issues occur, let DRF handle datetime parsing errors elsewhere
                pass
        if data.get('order_type') == 'pickup':
            if not data.get('pickup_time'):
                raise serializers.ValidationError("Pickup time is required for pickup orders.")
            if data.get('delivery_charge', 0.00) > 0:
                raise serializers.ValidationError("Delivery charge is not applicable for pickup orders.")
        if not data.get('items'):
            raise serializers.ValidationError("The items list cannot be empty.")
        return data




class CreatePaymentSerializer(serializers.Serializer):
    order_id = serializers.IntegerField()
    amount = serializers.DecimalField(max_digits=10, decimal_places=2)
    payment_method = serializers.CharField(max_length=10)
    transaction_id = serializers.CharField(max_length=255, required=False)


class RazorpayPaymentVerificationSerializer(serializers.Serializer):
    order_id = serializers.IntegerField()
    razorpay_order_id = serializers.CharField(max_length=255)
    razorpay_payment_id = serializers.CharField(max_length=255)
    razorpay_signature = serializers.CharField(max_length=255, allow_blank=True)


class CancelPaymentSerializer(serializers.Serializer):
    """Serializer for cancelling a payment for an order"""
    order_id = serializers.IntegerField()
    payment_method = serializers.CharField(max_length=10, required=False, default='razorpay')
    reason = serializers.CharField(required=False, allow_blank=True)

    def validate_payment_method(self, value):
        allowed_methods = [m[0] for m in GroceriesPayments.PAYMENT_METHOD_CHOICES]
        if value not in allowed_methods:
            raise serializers.ValidationError(f"Invalid payment_method. Must be one of: {', '.join(allowed_methods)}")
        return value


class ServiceAvailabilitySerializer(serializers.Serializer):
    """Serializer for exposing delivery/pickup availability flags."""
    delivery_enabled = serializers.BooleanField()
    pickup_enabled = serializers.BooleanField()


class ServiceAvailabilityUpdateSerializer(serializers.Serializer):
    """Serializer for updating delivery/pickup availability flags (admin side)."""
    delivery_enabled = serializers.BooleanField(required=False)
    pickup_enabled = serializers.BooleanField(required=False)

    def validate(self, attrs):
        # Require at least one field to be provided
        if 'delivery_enabled' not in attrs and 'pickup_enabled' not in attrs:
            raise serializers.ValidationError(
                "At least one of 'delivery_enabled' or 'pickup_enabled' must be provided."
            )
        return attrs


class HighRatedProductsRequestSerializer(serializers.Serializer):
    business_id = serializers.IntegerField()


class GroceryPartnerSerializer(serializers.ModelSerializer):
    delivery_zones = serializers.ListField(
        child=serializers.CharField(max_length=50),
        required=False,
        allow_empty=True,
        help_text="List of delivery area codes"
    )
    
    class Meta:
        model = GroceryPartner
        fields = [
            'id', 'user', 'business', 'vehicle_number', 'vehicle_type',
            'driving_license_number', 'aadhar_card_number', 'bank_account_number',
            'bank_ifsc_code', 'bank_account_holder_name', 'emergency_contact_name',
            'emergency_contact_phone', 'delivery_zones', 'current_latitude',
            'current_longitude', 'availability_status', 'rating_average',
            'total_deliveries', 'is_verified', 'is_active', 'joined_date',
            'last_active_at', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'user', 'business', 'rating_average', 'total_deliveries', 
                           'is_verified', 'created_at', 'updated_at', 'last_active_at']

    def validate_aadhar_card_number(self, value):
        """Validate Aadhar card number format"""
        if len(value) != 12 or not value.isdigit():
            raise serializers.ValidationError("Aadhar card number must be exactly 12 digits.")
        return value

    def validate_vehicle_number(self, value):
        """Validate vehicle number format"""
        if len(value) < 6:
            raise serializers.ValidationError("Vehicle number must be at least 6 characters long.")
        return value.upper()

    def validate_driving_license_number(self, value):
        """Validate driving license number format"""
        if len(value) < 10:
            raise serializers.ValidationError("Driving license number must be at least 10 characters long.")
        return value.upper()

    def validate_bank_ifsc_code(self, value):
        """Validate IFSC code format"""
        if value and len(value) != 11:
            raise serializers.ValidationError("IFSC code must be exactly 11 characters long.")
        return value.upper() if value else value

    def validate_emergency_contact_phone(self, value):
        """Validate emergency contact phone number"""
        if value and (len(value) < 10 or not value.isdigit()):
            raise serializers.ValidationError("Emergency contact phone must be at least 10 digits.")
        return value

    def create(self, validated_data):
        """Create a new grocery partner"""
        # Set joined_date to today if not provided
        if 'joined_date' not in validated_data:
            validated_data['joined_date'] = date.today()
        
        return super().create(validated_data)


class GroceryPartnerRegistrationSerializer(serializers.ModelSerializer):
    """Serializer specifically for partner registration form"""
    delivery_zones = serializers.ListField(
        child=serializers.CharField(max_length=50),
        required=False,
        allow_empty=True,
        help_text="List of delivery area codes"
    )
    
    class Meta:
        model = GroceryPartner
        fields = [
            'vehicle_number', 'vehicle_type', 'driving_license_number',
            'aadhar_card_number', 'bank_account_number', 'bank_ifsc_code',
            'bank_account_holder_name', 'emergency_contact_name',
            'emergency_contact_phone', 'delivery_zones'
        ]

    def validate_aadhar_card_number(self, value):
        """Validate Aadhar card number format"""
        if len(value) != 12 or not value.isdigit():
            raise serializers.ValidationError("Aadhar card number must be exactly 12 digits.")
        
        # Check if Aadhar number already exists
        if GroceryPartner.objects.filter(aadhar_card_number=value).exists():
            raise serializers.ValidationError("A partner with this Aadhar card number already exists.")
        
        return value

    def validate_vehicle_number(self, value):
        """Validate vehicle number format"""
        if len(value) < 6:
            raise serializers.ValidationError("Vehicle number must be at least 6 characters long.")
        
        # Check if vehicle number already exists
        vehicle_number = value.upper()
        if GroceryPartner.objects.filter(vehicle_number=vehicle_number).exists():
            raise serializers.ValidationError("A partner with this vehicle number already exists.")
        
        return vehicle_number

    def validate_driving_license_number(self, value):
        """Validate driving license number format"""
        if len(value) < 10:
            raise serializers.ValidationError("Driving license number must be at least 10 characters long.")
        
        # Check if license number already exists
        license_number = value.upper()
        if GroceryPartner.objects.filter(driving_license_number=license_number).exists():
            raise serializers.ValidationError("A partner with this driving license number already exists.")
        
        return license_number

    def validate_bank_ifsc_code(self, value):
        """Validate IFSC code format"""
        if value and len(value) != 11:
            raise serializers.ValidationError("IFSC code must be exactly 11 characters long.")
        return value.upper() if value else value

    def validate_emergency_contact_phone(self, value):
        """Validate emergency contact phone number"""
        if value and (len(value) < 10 or not value.isdigit()):
            raise serializers.ValidationError("Emergency contact phone must be at least 10 digits.")
        return value


class GroceryDeliverDetailsSerializer(serializers.ModelSerializer):
    """Serializer for delivery details with nested order and partner information"""
    order_details = GroceriesOrdersSerializer(source='order', read_only=True)
    partner_details = GroceryPartnerSerializer(source='partner', read_only=True)
    assigned_by_user_name = serializers.SerializerMethodField()
    
    class Meta:
        model = GroceryDeliverDetails
        fields = [
            'delivery_detail_id', 'order', 'partner', 'assigned_by_user',
            'assignment_status', 'assigned_at', 'delivered_at', 'delivery_otp',
            'otp_verified_at', 'is_active', 'created_at', 'updated_at',
            'order_details', 'partner_details', 'assigned_by_user_name'
        ]
        read_only_fields = [
            'delivery_detail_id', 'assigned_at', 'delivered_at', 'delivery_otp',
            'otp_verified_at', 'created_at', 'updated_at'
        ]

    def get_assigned_by_user_name(self, obj):
        """Get the full name of the user who assigned the order"""
        if obj.assigned_by_user:
            return f"{obj.assigned_by_user.firstName} {obj.assigned_by_user.lastName}".strip()
        return None


class BusinessOrdersSerializer(serializers.ModelSerializer):
    """Serializer for business orders with detailed user and order items information"""
    order_items = GroceriesOrderItemsSerializer(many=True, read_only=True, source='groceriesorderitems_set')
    user_details = serializers.SerializerMethodField()
    
    class Meta:
        model = GroceriesOrders
        fields = [
            'order_id', 'user', 'business', 'order_type', 'order_status',
            'payment_status', 'total_amount', 'gst_amount', 'delivery_charge',
            'discount', 'final_amount', 'delivery_address', 'delivery_latitude', 'delivery_longitude',
            'delivery_time', 'delivery_instructions', 'pickup_time',
            'created_at', 'updated_at', 'order_items', 'user_details'
        ]

    def get_user_details(self, obj):
        """Get user details for the order"""
        if obj.user:
            return {
                'user_id': obj.user.user_id,
                'first_name': obj.user.firstName,
                'last_name': obj.user.lastName,
                'email': obj.user.emailID,
                'phone_number': obj.user.mobileNumber
            }
        return None


class UpdateOrderStatusSerializer(serializers.Serializer):
    """Serializer for updating order status"""
    order_id = serializers.IntegerField()
    new_status = serializers.CharField(max_length=20)
    
    def validate_new_status(self, value):
        """Validate the new status value"""
        valid_statuses = ['pending', 'confirmed', 'packed', 'shipped', 'delivered', 'cancelled']
        if value not in valid_statuses:
            raise serializers.ValidationError(f"Invalid status. Must be one of: {', '.join(valid_statuses)}")
        return value


class DeliveryPartnerDetailsSerializer(serializers.ModelSerializer):
    """Serializer for delivery partner details with user information"""
    user_details = serializers.SerializerMethodField()
    
    class Meta:
        model = GroceryPartner
        fields = [
            'id', 'vehicle_number', 'vehicle_type', 'driving_license_number',
            'aadhar_card_number', 'bank_account_number', 'bank_ifsc_code',
            'bank_account_holder_name', 'emergency_contact_name', 'emergency_contact_phone',
            'delivery_zones', 'current_latitude', 'current_longitude',
            'availability_status', 'rating_average', 'total_deliveries',
            'is_verified', 'is_active', 'joined_date', 'last_active_at',
            'created_at', 'updated_at', 'user_details'
        ]
    
    def get_user_details(self, obj):
        """Get user registration details"""
        if obj.user:
            return {
                'user_id': obj.user.user_id,
                'firstName': obj.user.firstName,
                'lastName': obj.user.lastName,
                'countryCode': obj.user.countryCode,
                'mobileNumber': obj.user.mobileNumber,
                'emailID': obj.user.emailID,
                'dob': obj.user.dob,
                'is_verified': obj.user.is_verified,
                'is_active': obj.user.is_active,
                'user_mode': obj.user.user_mode,
            }
        return None


class VerifyDeliveryOTPSerializer(serializers.Serializer):
    """Serializer for verifying delivery OTP by delivery partner"""
    otp = serializers.CharField(max_length=6, min_length=6, write_only=True)
    
    def __init__(self, *args, **kwargs):
        # Get order_id from context if provided
        self.order_id = kwargs.pop('order_id', None)
        super().__init__(*args, **kwargs)
    
    def validate(self, attrs):
        """Cross-field validation to verify OTP matches"""
        # Get order_id from context
        order_id = self.order_id
        if not order_id:
            raise serializers.ValidationError({"order_id": "Order ID is required as a query parameter"})
            
        otp = attrs.get('otp')
        if not otp:
            raise serializers.ValidationError({"otp": "OTP is required"})
        
        try:
            # Get delivery details with related order and partner
            delivery_detail = GroceryDeliverDetails.objects.select_related('order', 'partner').get(
                order__order_id=order_id
            )
            
            # Validate delivery details
            if not delivery_detail.delivery_otp:
                raise serializers.ValidationError({"otp": "No OTP generated for this order."})
                
            if delivery_detail.otp_verified_at:
                raise serializers.ValidationError({"otp": "OTP already verified for this order."})
                
            if delivery_detail.assignment_status == 'delivered':
                raise serializers.ValidationError({"status": "Order already marked as delivered."})
                
            # Verify OTP - compare as strings to handle type mismatches
            if str(delivery_detail.delivery_otp).strip() != str(otp).strip():
                raise serializers.ValidationError({"otp": "Invalid OTP provided."})
                
            # Add delivery_detail to attrs for use in view
            attrs['delivery_detail'] = delivery_detail
            
        except GroceryDeliverDetails.DoesNotExist:
            raise serializers.ValidationError({"order_id": f"No delivery assignment found for order {order_id}."})
        except Exception as e:
            raise serializers.ValidationError({"error": str(e)})
            
        return attrs
    
    def validate_otp(self, value):
        """Validate OTP format"""
        if not value.isdigit():
            raise serializers.ValidationError("OTP must contain only digits.")
        if len(value) != 6:
            raise serializers.ValidationError("OTP must be exactly 6 digits.")
        return value
        
        return attrs


class GeneratePickupOTPSerializer(serializers.Serializer):
    """Serializer for generating OTP for pickup orders by retail business"""
    order_id = serializers.IntegerField()
    
    def validate_order_id(self, value):
        """Validate that the order exists and is a pickup order"""
        try:
            # Debug: Print the order_id being searched
            print(f"DEBUG: Searching for order_id: {value}")
            
            # Check if the order exists using raw SQL to debug table/field issues
            from django.db import connection
            with connection.cursor() as cursor:
                cursor.execute("SELECT order_id, order_type, payment_status, order_status FROM Groceries_orders WHERE order_id = %s", [value])
                raw_result = cursor.fetchone()
                if raw_result:
                    print(f"DEBUG: Raw SQL found order - ID: {raw_result[0]}, Type: {raw_result[1]}, Payment: {raw_result[2]}, Status: {raw_result[3]}")
                else:
                    print(f"DEBUG: Raw SQL - No order found with ID {value}")
            
            # Try the Django ORM query without selecting the new OTP fields that might not exist yet
            try:
                order = GroceriesOrders.objects.select_related('user', 'business').get(order_id=value)
            except Exception as orm_error:
                print(f"DEBUG: Django ORM error: {orm_error}")
                # If ORM fails, try without select_related to isolate the issue
                order = GroceriesOrders.objects.get(order_id=value)
            
            # Debug: Print found order details
            print(f"DEBUG: Found order - ID: {order.order_id}, Type: {order.order_type}, Payment: {order.payment_status}, Status: {order.order_status}")
            
            # Check if it's a pickup order
            if order.order_type != 'pickup':
                raise serializers.ValidationError("Only pickup orders can generate OTP for customer verification.")
            
            # Check if order is paid
            if order.payment_status != 'paid':
                raise serializers.ValidationError("Order must be paid before generating OTP.")
            
            # Check if order is already delivered
            if order.order_status == 'delivered':
                raise serializers.ValidationError("Order is already marked as delivered.")
                
        except GroceriesOrders.DoesNotExist as e:
            print(f"DEBUG: Order {value} not found. Error: {e}")
            # Let's also check if any orders exist and show some sample IDs
            total_orders = GroceriesOrders.objects.count()
            print(f"DEBUG: Total orders in database: {total_orders}")
            
            # Show some sample order IDs to compare
            sample_orders = GroceriesOrders.objects.values_list('order_id', flat=True)[:10]
            print(f"DEBUG: Sample order IDs: {list(sample_orders)}")
            
            # Check raw SQL for all orders
            from django.db import connection
            with connection.cursor() as cursor:
                cursor.execute("SELECT order_id FROM Groceries_orders LIMIT 10")
                raw_ids = [row[0] for row in cursor.fetchall()]
                print(f"DEBUG: Raw SQL sample order IDs: {raw_ids}")
            
            raise serializers.ValidationError("Order does not exist.")
        except Exception as e:
            print(f"DEBUG: Unexpected error: {e}")
            raise serializers.ValidationError(f"Error validating order: {str(e)}")
        
        return value
    
    def validate(self, attrs):
        """Cross-field validation"""
        order_id = attrs.get('order_id')
        
        # Get order and add to validated data for use in view
        try:
            # Try the Django ORM query without selecting the new OTP fields that might not exist yet
            try:
                order = GroceriesOrders.objects.select_related('user', 'business').get(order_id=order_id)
            except Exception as orm_error:
                print(f"DEBUG: Django ORM error in validate: {orm_error}")
                # If ORM fails, try without select_related to isolate the issue
                order = GroceriesOrders.objects.get(order_id=order_id)
            
            attrs['order'] = order
            print(f"DEBUG: Order added to validated_data: {order.order_id}")
        except GroceriesOrders.DoesNotExist:
            # This should have been caught in field validation, but handle it anyway
            raise serializers.ValidationError({"order_id": "Order does not exist."})
        except Exception as e:
            print(f"DEBUG: Unexpected error in validate: {e}")
            raise serializers.ValidationError({"error": f"Error validating order: {str(e)}"})
            
        return attrs


class VerifyPickupOTPSerializer(serializers.Serializer):
    """Serializer for verifying pickup OTP by retail business"""
    order_id = serializers.IntegerField()
    otp = serializers.CharField(max_length=6, min_length=6)
    
    def validate_otp(self, value):
        """Validate OTP format"""
        if not value.isdigit():
            raise serializers.ValidationError("OTP must contain only digits.")
        if len(value) != 6:
            raise serializers.ValidationError("OTP must be exactly 6 digits.")
        return value
    
    def validate_order_id(self, value):
        """Validate that the order exists and is a pickup order"""
        try:
            # Debug: Print the order_id being searched
            print(f"DEBUG: Verifying order_id: {value}")
            
            # Check if the order exists using raw SQL to debug table/field issues
            from django.db import connection
            with connection.cursor() as cursor:
                cursor.execute("SELECT order_id, order_type, payment_status, order_status FROM Groceries_orders WHERE order_id = %s", [value])
                raw_result = cursor.fetchone()
                if raw_result:
                    print(f"DEBUG: Raw SQL found order - ID: {raw_result[0]}, Type: {raw_result[1]}, Payment: {raw_result[2]}, Status: {raw_result[3]}")
                else:
                    print(f"DEBUG: Raw SQL - No order found with ID {value}")
            
            # Try the Django ORM query without selecting the new OTP fields that might not exist yet
            try:
                order = GroceriesOrders.objects.select_related('user', 'business').get(order_id=value)
            except Exception as orm_error:
                print(f"DEBUG: Django ORM error in verify: {orm_error}")
                # If ORM fails, try without select_related to isolate the issue
                order = GroceriesOrders.objects.get(order_id=value)
            
            # Debug: Print found order details
            print(f"DEBUG: Found order for verification - ID: {order.order_id}, Type: {order.order_type}, Payment: {order.payment_status}, Status: {order.order_status}")
            
            # Check if it's a pickup order
            if order.order_type != 'pickup':
                raise serializers.ValidationError("Only pickup orders can be verified with OTP.")
            
            # Check if order is paid
            if order.payment_status != 'paid':
                raise serializers.ValidationError("Order must be paid before OTP verification.")
            
            # Check if order is already delivered
            if order.order_status == 'delivered':
                raise serializers.ValidationError("Order is already marked as delivered.")
                
        except GroceriesOrders.DoesNotExist as e:
            print(f"DEBUG: Order {value} not found during verification. Error: {e}")
            raise serializers.ValidationError("Order does not exist.")
        except Exception as e:
            print(f"DEBUG: Unexpected error in verify validation: {e}")
            raise serializers.ValidationError(f"Error validating order: {str(e)}")
        
        return value
    
    def validate(self, attrs):
        """Cross-field validation to verify OTP matches"""
        order_id = attrs.get('order_id')
        otp = attrs.get('otp')
        
        try:
            # Get order with related data
            try:
                order = GroceriesOrders.objects.select_related('user', 'business').get(order_id=order_id)
            except Exception as orm_error:
                print(f"DEBUG: Django ORM error in validate for verify: {orm_error}")
                # If ORM fails, try without select_related to isolate the issue
                order = GroceriesOrders.objects.get(order_id=order_id)
            
            attrs['order'] = order
            print(f"DEBUG: Order added to validated_data for verification: {order.order_id}")
            
            # Check if OTP was generated for this order using fallback method
            try:
                current_otp = order.pickup_otp
                verified_at = order.pickup_otp_verified_at
            except:
                # If fields don't exist, get from raw SQL
                from django.db import connection
                with connection.cursor() as cursor:
                    cursor.execute(
                        "SELECT pickup_otp, pickup_otp_verified_at FROM Groceries_orders WHERE order_id = %s", 
                        [order_id]
                    )
                    result = cursor.fetchone()
                    if result:
                        current_otp, verified_at = result
                    else:
                        current_otp, verified_at = None, None
            
            if not current_otp:
                raise serializers.ValidationError({"otp": "No OTP generated for this order. Please generate OTP first."})
            
            # Check if OTP is valid (not expired)
            if not order.is_pickup_otp_valid():
                raise serializers.ValidationError({"otp": "OTP has expired. Please generate a new OTP."})
            
            # Verify OTP matches
            if str(current_otp).strip() != str(otp).strip():
                raise serializers.ValidationError({"otp": "Invalid OTP. Please check and try again."})
            
        except GroceriesOrders.DoesNotExist:
            raise serializers.ValidationError({"order_id": "Order does not exist."})
        except Exception as e:
            print(f"DEBUG: Unexpected error in verify validate: {e}")
            raise serializers.ValidationError({"error": f"Error validating OTP: {str(e)}"})
        
        return attrs


class AssignOrderToPartnerSerializer(serializers.Serializer):
    """Serializer for assigning orders to delivery partners"""
    partner_id = serializers.IntegerField()
    order_id = serializers.IntegerField()
    
    def validate_partner_id(self, value):
        """Validate that the partner exists and is available"""
        try:
            partner = GroceryPartner.objects.select_related('user').get(user_id=value)
            
            # Check if user has delivery_partner mode
            if partner.user.user_mode != 'delivery_partner':
                raise serializers.ValidationError(f"Partner with user_id {value} is not registered as delivery_partner. Current user_mode: {partner.user.user_mode}")
            
            if not partner.is_active:
                raise serializers.ValidationError(f"Partner with user_id {value} is not active.")
            if not partner.is_verified:
                raise serializers.ValidationError(f"Partner with user_id {value} is not verified.")
            if partner.availability_status not in ['available']:
                raise serializers.ValidationError(f"Partner with user_id {value} is not available for delivery. Current status: {partner.availability_status}")
                
        except GroceryPartner.DoesNotExist:
            raise serializers.ValidationError(f"Partner with user_id {value} does not exist.")
        return value
    
    def validate_order_id(self, value):
        """Validate that the order exists and is eligible for delivery assignment"""
        try:
            order = GroceriesOrders.objects.get(order_id=value)
            if order.order_type != 'delivery':
                raise serializers.ValidationError("Only delivery orders can be assigned to partners.")
            # Check if order is already assigned
            if GroceryDeliverDetails.objects.filter(order=order).exists():
                raise serializers.ValidationError("Order is already assigned to a delivery partner.")
        except GroceriesOrders.DoesNotExist:
            raise serializers.ValidationError("Order does not exist.")
        return value
    
    def validate(self, data):
        """Cross-field validation"""
        partner_id = data.get('partner_id')
        order_id = data.get('order_id')
        
        # Verify partner belongs to the same business as the order
        try:
            partner = GroceryPartner.objects.get(user_id=partner_id)
            order = GroceriesOrders.objects.get(order_id=order_id)
            
            if partner.business and partner.business != order.business:
                raise serializers.ValidationError("Partner must belong to the same business as the order.")
        except (GroceryPartner.DoesNotExist, GroceriesOrders.DoesNotExist):
            pass  # Already validated in individual field validators
        
        return data
    
    @transaction.atomic
    def create(self, validated_data):
        """Create delivery assignment with OTP generation"""
        partner_id = validated_data['partner_id']
        order_id = validated_data['order_id']
        assigned_by_user = self.context['assigned_by_user']
        
        # Get the partner and order objects
        partner = GroceryPartner.objects.get(user_id=partner_id)
        order = GroceriesOrders.objects.get(order_id=order_id)
        
        # Create delivery assignment (assigned_by_user can be None)
        delivery_detail = GroceryDeliverDetails.objects.create(
            order=order,
            partner=partner,
            assigned_by_user=assigned_by_user,  # This can be None now
            assignment_status='assigned'
        )
        
        # Generate OTP for delivery verification
        delivery_detail.generate_otp()
        
        # Update partner status to busy
        partner.availability_status = 'busy'
        partner.save(update_fields=['availability_status'])
        
        # Update order status to assigned
        order.order_status = 'assigned'
        order.save(update_fields=['order_status'])
        
        logger.info(f"Order {order_id} assigned to partner with user_id {partner_id} by user {assigned_by_user.user_id if assigned_by_user else 'Unknown'}")
        
        return delivery_detail



class BulkGroceriesUploadSerializer(serializers.Serializer):
    """Serializer to validate bulk CSV upload input and options."""
    file = serializers.FileField()
    dry_run = serializers.BooleanField(required=False, default=False)
    all_or_nothing = serializers.BooleanField(required=False, default=False)
    update_existing = serializers.BooleanField(required=False, default=True)
    create_missing_categories = serializers.BooleanField(required=False, default=True)
    encoding = serializers.CharField(required=False, default='utf-8')

    def validate_encoding(self, value):
        # Normalize common encodings and synonyms; default to BOM-tolerant utf-8-sig
        val = (value or '').lower().strip()
        if val in ['', 'utf8', 'utf-8']:
            return 'utf-8-sig'
        if val in ['utf-8-sig']:
            return 'utf-8-sig'
        if val in ['latin1', 'iso-8859-1']:
            return 'latin1'
        if val in ['cp1252', 'windows-1252', 'win-1252']:
            return 'cp1252'
        # Allow advanced users to pass a Python codec name directly
        return val


# ========================
# Ratings History
# ========================


class GroceriesRatingHistorySerializer(serializers.ModelSerializer):
    """Display serializer for rating history entries with related names."""
    user_name = serializers.SerializerMethodField()
    product_name = serializers.CharField(source='product.product_name', read_only=True)
    business_name = serializers.CharField(source='business.business_name', read_only=True)

    class Meta:
        model = GroceriesRatingHistory
        fields = [
            'rating_id', 'user', 'user_name', 'product', 'product_name', 'order', 'business', 'business_name',
            'rating', 'review_title', 'review_text', 'is_verified_purchase', 'is_active', 'helpful_count',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['rating_id', 'user_name', 'product_name', 'business_name', 'created_at', 'updated_at']

    def get_user_name(self, obj):
        try:
            return f"{obj.user.firstName} {obj.user.lastName}".strip()
        except Exception:
            return None


class CreateRatingHistorySerializer(serializers.Serializer):
    """Serializer for creating a new rating entry. Expects user_id and business_id in context."""
    product_id = serializers.IntegerField()
    order_id = serializers.IntegerField(required=False, allow_null=True)
    rating = serializers.IntegerField(min_value=1, max_value=5)
    review_title = serializers.CharField(max_length=200, required=False, allow_blank=True)
    review_text = serializers.CharField(required=False, allow_blank=True)

    def validate(self, attrs):
        from .gro_models import GroceriesOrders, GroceriesOrderItems, GroceriesProducts

        user_id = (self.context or {}).get('user_id')
        business_id = (self.context or {}).get('business_id')
        if not user_id or not business_id:
            raise serializers.ValidationError({
                'params': "user_id and business_id must be provided in URL query parameters"
            })

        product_id = attrs.get('product_id')
        order_id = attrs.get('order_id')

        # Validate product exists and belongs to business
        try:
            product = GroceriesProducts.objects.select_related('business').get(product_id=product_id)
        except GroceriesProducts.DoesNotExist:
            raise serializers.ValidationError({'product_id': 'Product does not exist'})
        if str(product.business_id) != str(business_id):
            raise serializers.ValidationError({'business_id': 'Product does not belong to this business'})

        # Determine/validate order and verified purchase
        order = None
        is_verified = False
        if order_id:
            try:
                order = GroceriesOrders.objects.get(order_id=order_id)
            except GroceriesOrders.DoesNotExist:
                raise serializers.ValidationError({'order_id': 'Order does not exist'})

            # Check ownership and status
            if str(order.user_id) != str(user_id):
                raise serializers.ValidationError({'order_id': 'Order does not belong to the user'})
            if str(order.business_id) != str(business_id):
                raise serializers.ValidationError({'order_id': 'Order does not belong to this business'})
            if (order.order_status or '').strip().lower() != 'delivered':
                raise serializers.ValidationError({'order_id': 'Only delivered orders can be rated'})

            # Ensure product is part of the order
            in_order = GroceriesOrderItems.objects.filter(order_id=order.order_id, product_id=product_id).exists()
            if not in_order:
                raise serializers.ValidationError({'product_id': 'This product was not part of the specified order'})
            is_verified = True
        else:
            # Find the user's most recent delivered order containing this product for this business
            order = (
                GroceriesOrders.objects.filter(
                    user_id=user_id,
                    business_id=business_id,
                    order_status__iexact='delivered',
                    groceriesorderitems_set__product_id=product_id
                )
                .order_by('-created_at')
                .first()
            )
            if not order:
                raise serializers.ValidationError({'order_id': 'No delivered order found for this product and user'})
            is_verified = True

        # Prevent duplicate for same user-product-order
        exists = GroceriesRatingHistory.objects.filter(
            user_id=user_id, product_id=product_id, order_id=order.order_id
        ).exists()
        if exists:
            raise serializers.ValidationError('You have already rated this product for this order')

        # Attach resolved entities
        attrs['order'] = order
        attrs['product'] = product
        attrs['is_verified_purchase'] = is_verified
        attrs['user_id_ctx'] = user_id
        attrs['business_id_ctx'] = business_id
        return attrs

    @transaction.atomic
    def create(self, validated_data):
        from kirazee_app.models import Registration, Business
        user_id = validated_data.pop('user_id_ctx')
        business_id = validated_data.pop('business_id_ctx')
        product = validated_data.pop('product')
        order = validated_data.pop('order')
        is_verified = validated_data.pop('is_verified_purchase', True)

        # Fetch related entities
        user = Registration.objects.get(user_id=user_id)
        business = Business.objects.get(business_id=business_id)

        instance = GroceriesRatingHistory.objects.create(
            user=user,
            product=product,
            order=order,
            business=business,
            rating=validated_data['rating'],
            review_title=validated_data.get('review_title') or None,
            review_text=validated_data.get('review_text') or None,
            is_verified_purchase=is_verified,
            is_active=True,
            helpful_count=0,
        )
        return instance

# ========================
# Business Feedback
# ========================

class BusinessFeedbackItemSerializer(serializers.Serializer):
    question = serializers.CharField(max_length=255)
    rating = serializers.IntegerField(min_value=1, max_value=5)


class BusinessFeedbackCreateSerializer(serializers.Serializer):
    user_name = serializers.CharField(max_length=200, required=False, allow_blank=True)
    email = serializers.EmailField(required=False, allow_blank=True)
    additional_comments = serializers.CharField(required=False, allow_blank=True)
    items = BusinessFeedbackItemSerializer(many=True)

    def validate(self, attrs):
        items = attrs.get('items') or []
        if not items:
            raise serializers.ValidationError({'items': 'At least one feedback item is required.'})
        return attrs


class BusinessFeedbackSerializer(serializers.ModelSerializer):
    business_id = serializers.CharField(source='business.business_id', read_only=True)
    user_id = serializers.IntegerField(source='user.user_id', read_only=True)

    class Meta:
        model = BusinessFeedback
        fields = [
            'feedback_id', 'business', 'business_id', 'user', 'user_id', 'user_name',
            'email', 'question', 'rating', 'additional_comments', 'created_at', 'updated_at'
        ]
        read_only_fields = ['feedback_id', 'business_id', 'user_id', 'created_at', 'updated_at']
