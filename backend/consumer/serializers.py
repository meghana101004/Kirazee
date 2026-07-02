from pyexpat import model
from django.utils import timezone
from django.conf import settings
from datetime import datetime, timedelta
from rest_framework import serializers
from consumer.image_utils import build_s3_file_url
from kirazee_app.models import BusinessFinancial, BusinessType, BusinessFeature, Business, Registration, BusinessMapping
from business.models import MenuItems, BOM, productItems
from consumer.models import MenuCart, Orders, OrderItems, WalletPoints, Coupons, CouponRules, CouponRedemptions, DeliveryCharges, PointsConfiguration, Payments


def _normalize_media_url(url: str) -> str:
    """Normalize built URLs to avoid duplicate media segments across envs.
    Examples fixed:
    - /kirazee/media/media/... -> /kirazee/media/...
    - /media/media/... -> /media/...
    """
    try:
        if not isinstance(url, str):
            return url
        # Fix common duplications regardless of host prefix
        url = url.replace('/kirazee/media/media/', '/kirazee/media/')
        url = url.replace('/media/media/', '/media/')
        return url
    except Exception:
        return url

class BusinessSerializer(serializers.ModelSerializer):
    logo_url = serializers.SerializerMethodField()
    banner_url = serializers.SerializerMethodField()

    class Meta:
        model = Business
        fields = [
            'business_id', 'business_features', 'level', 'master',
            'businessName', 'businessType', 'businessCategory',
            'businessEmail', 'businessNumber', 'businessWhatsapp',
            'description', 'logo_url', 'banner_url',  # Remove logo, banner from fields
            'business_licence', 'business_hours', 'gst_num',
            'currency', 'location', 'address', 'landmark',
            'city', 'state', 'pincode', 'contact_support',
            'contact_mobile', 'website_url', 'is_verified',
            'status', 'paymentstatus', 'latitude', 'longitude',
            'created_at', 'updated_at'
        ]

    def get_logo_url(self, obj):
        return build_s3_file_url(obj.logo)

    def get_banner_url(self, obj):
        return build_s3_file_url(obj.banner)

    def get_business_features(self, obj):
        """
        Fetch feature details from DB for the feature_ids stored in Business.business_features
        and return them in the format: 'FEA01 - Feature_Name'
        """
        feature_ids = obj.business_features or []
        features = BusinessFeature.objects.filter(
            feature_id__in=feature_ids,
            status=True
        ).values_list("feature_id", "details")

        # make a mapping dict {feature_id: details}
        feature_map = dict(features)

        return [
            f"{fid} - {feature_map.get(fid, 'Unknown_Feature')}"
            for fid in feature_ids
        ]

class BusinessnearbySerializer(serializers.ModelSerializer):
    business_features = serializers.SerializerMethodField()
    distance_km = serializers.SerializerMethodField()
    logo_url = serializers.SerializerMethodField()
    banner_url = serializers.SerializerMethodField()
    master_branch_name = serializers.SerializerMethodField()
    rating = serializers.SerializerMethodField()
    estimated_delivery_time = serializers.SerializerMethodField()
    sub_branches = serializers.SerializerMethodField()
    address = serializers.SerializerMethodField()
    is_visible = serializers.SerializerMethodField()
    can_order = serializers.SerializerMethodField()
    availability_status = serializers.SerializerMethodField()
    availability_message = serializers.SerializerMethodField()
    is_business_open = serializers.SerializerMethodField()
    
    class Meta:
        model = Business
        fields = [
            'business_id', 'businessName', 'businessType', 'businessCategory', 'address', 'city', 'state', 
            'pincode', 'location', 'distance_km', 'business_features', 'latitude', 'longitude', 'logo_url', 
            'banner_url', 'master_branch_name', 'master', 'rating', 'businessNumber', 
            'businessWhatsapp', 'description', 'business_hours', 'contact_support', 'contact_mobile', 'website_url', 
            'estimated_delivery_time', 'sub_branches', 'is_visible', 'can_order', 'availability_status', 
            'availability_message', 'is_business_open', 'created_at', 'updated_at'
        ]
        read_only_fields = ['distance_km', 'logo_url', 'banner_url', 'master_branch_name', 'rating', 'estimated_delivery_time', 'sub_branches', 'is_visible', 'can_order', 'availability_status', 'availability_message', 'is_business_open', 'created_at', 'updated_at']
    
    def get_distance_km(self, obj):
        return getattr(obj, 'distance_km', None)
    
    def get_address(self, obj):
        parts = [
            getattr(obj, 'address', ''),
            getattr(obj, 'city', ''),
            getattr(obj, 'state', ''),
            str(getattr(obj, 'pincode', ''))
        ]
        return ", ".join([p for p in parts if p and str(p).strip()])
    
    def get_logo_url(self, obj):
        """Build S3 URL for business logo"""
        return build_s3_file_url(obj.logo)
    
    def get_banner_url(self, obj):
        """Build S3 URL for business banner"""
        return build_s3_file_url(obj.banner)
        return None
    
    def get_master_branch_name(self, obj):
        """Get master branch name if this business has a master"""
        if obj.master and obj.level != 'Master Level':
            try:
                master_business = Business.objects.get(business_id=obj.master)
                return master_business.businessName
            except Business.DoesNotExist:
                return None
        return None
    
    def get_rating(self, obj):
        """Return default rating of 4.0 for now"""
        return 4.0
    
    def get_estimated_delivery_time(self, obj):
        """Calculate estimated delivery time based on business type and distance"""
        try:
            # Base preparation time based on business type
            if obj.businessType == 'R02':  # Restaurant
                base_prep_time = 30  # 30 minutes
            elif obj.businessType == 'R01':  # Grocery
                base_prep_time = 15  # 15 minutes
            else:
                base_prep_time = 20  # Default
            
            # Calculate delivery time based on distance
            delivery_time = 0
            distance_km = getattr(obj, 'distance_km', None)
            
            if distance_km:
                # Estimate travel time (assuming 20 km/h average speed in city)
                travel_time_minutes = (distance_km / 20) * 60
                delivery_time = max(30, int(travel_time_minutes))  # Minimum 10 minutes
            else:
                delivery_time = 15  # Default delivery time if no distance
            
            total_time = base_prep_time + delivery_time
            
            def _round_to_5(n):
                return int(5 * round(float(n) / 5.0))

            # Derive a reasonable window around the estimate
            lower_buffer = max(5, int(total_time * 0.15))
            upper_buffer = max(10, int(total_time * 0.25))

            min_total_time = _round_to_5(max(5, total_time - lower_buffer))
            max_total_time = _round_to_5(total_time + upper_buffer)

            min_delivery_time = _round_to_5(max(5, delivery_time - lower_buffer))
            max_delivery_time = _round_to_5(delivery_time + upper_buffer)

            now_value = timezone.now() if getattr(settings, 'USE_TZ', False) else datetime.now()
            estimated_time = now_value + timedelta(minutes=total_time)
            estimated_from = now_value + timedelta(minutes=min_total_time)
            estimated_to = now_value + timedelta(minutes=max_total_time)

            return {
                'preparation_time_minutes': base_prep_time,
                'delivery_time_minutes': delivery_time,
                'delivery_time_minutes_min': min_delivery_time,
                'delivery_time_minutes_max': max_delivery_time,
                'total_time_minutes': total_time,
                'total_time_minutes_min': min_total_time,
                'total_time_minutes_max': max_total_time,
                'delivery_time_range': f"{min_delivery_time}-{max_delivery_time}",
                'total_time_range': f"{min_total_time}-{max_total_time}",
                'estimated_delivery_time': estimated_time.isoformat(),
                'estimated_delivery_time_formatted': estimated_time.strftime('%I:%M %p, %d %b %Y'),
                'estimated_delivery_time_from': estimated_from.isoformat(),
                'estimated_delivery_time_to': estimated_to.isoformat(),
                'estimated_delivery_time_from_formatted': estimated_from.strftime('%I:%M %p, %d %b %Y'),
                'estimated_delivery_time_to_formatted': estimated_to.strftime('%I:%M %p, %d %b %Y'),
            }
        except Exception as e:
            # Return default values if calculation fails
            base_prep_time = 10
            delivery_time = 10
            total_time = base_prep_time + delivery_time
            min_total = max(5, total_time - 5)
            max_total = total_time + 10
            now_value = timezone.now() if getattr(settings, 'USE_TZ', False) else datetime.now()
            return {
                'preparation_time_minutes': base_prep_time,
                'delivery_time_minutes': delivery_time,
                'delivery_time_minutes_min': max(5, delivery_time - 5),
                'delivery_time_minutes_max': delivery_time + 10,
                'total_time_minutes': total_time,
                'total_time_minutes_min': min_total,
                'total_time_minutes_max': max_total,
                'delivery_time_range': f"{max(5, delivery_time - 5)}-{delivery_time + 10}",
                'total_time_range': f"{min_total}-{max_total}",
                'estimated_delivery_time': (now_value + timedelta(minutes=total_time)).isoformat(),
                'estimated_delivery_time_formatted': (now_value + timedelta(minutes=total_time)).strftime('%I:%M %p, %d %b %Y'),
                'estimated_delivery_time_from': (now_value + timedelta(minutes=min_total)).isoformat(),
                'estimated_delivery_time_to': (now_value + timedelta(minutes=max_total)).isoformat(),
                'estimated_delivery_time_from_formatted': (now_value + timedelta(minutes=min_total)).strftime('%I:%M %p, %d %b %Y'),
                'estimated_delivery_time_to_formatted': (now_value + timedelta(minutes=max_total)).strftime('%I:%M %p, %d %b %Y'),
            }

    def get_business_features(self, obj):
        """
        Fetch feature details from DB for the feature_ids stored in Business.business_features
        and return them in the format: 'FEA01 - Feature_Name'
        """
        feature_ids = obj.business_features or []
        features = BusinessFeature.objects.filter(
            feature_id__in=feature_ids,
            status=True
        ).values_list("feature_id", "details")

        # make a mapping dict {feature_id: details}
        feature_map = dict(features)

        return [
            f"{fid} - {feature_map.get(fid, 'Unknown_Feature')}"
            for fid in feature_ids
        ]

    def get_sub_branches(self, obj):
        # Only include sub-branches for master branches
        if obj.level == 'master' or not obj.master:
            from geopy.distance import geodesic
            
            sub_branches = Business.objects.filter(master=obj.business_id)
            
            # Get user location from context if available
            request = self.context.get('request')
            user_location = None
            
            if request:
                lat = request.query_params.get('lat')
                lng = request.query_params.get('lng')
                
                if lat and lng:
                    try:
                        user_location = (float(lat), float(lng))
                    except (ValueError, TypeError):
                        user_location = None
            
            # Calculate distance for each sub-branch if user location is available
            if user_location:
                sub_branches_with_distance = []
                for sub_branch in sub_branches:
                    try:
                        if sub_branch.latitude and sub_branch.longitude:
                            business_lat = float(sub_branch.latitude)
                            business_lng = float(sub_branch.longitude)
                            business_location = (business_lat, business_lng)
                            distance = geodesic(user_location, business_location).kilometers
                            sub_branch.distance_km = round(distance, 2)
                        else:
                            sub_branch.distance_km = None
                    except (TypeError, ValueError):
                        sub_branch.distance_km = None
                    
                    sub_branches_with_distance.append(sub_branch)
                
                sub_branches = sub_branches_with_distance
            
            return BusinessnearbySerializer(sub_branches, many=True, context=self.context).data
        return []
    
    def get_is_visible(self, obj):
        """Check if business should be visible to consumers"""
        return bool(getattr(obj, 'is_visible', True))
    
    def get_can_order(self, obj):
        """Check if ordering is allowed for this business"""
        from .availability_services import get_business_availability
        availability = get_business_availability(obj)
        return availability.get('can_order', False)
    
    def get_availability_status(self, obj):
        """Get business availability status"""
        from .availability_services import get_business_availability
        availability = get_business_availability(obj)
        return availability.get('availability_status', 'unknown')
    
    def get_availability_message(self, obj):
        """Get business availability message"""
        from .availability_services import get_business_availability
        availability = get_business_availability(obj)
        return availability.get('availability_message')
    
    def get_is_business_open(self, obj):
        """Check if business is currently open based on timings"""
        from .availability_services import get_business_availability
        availability = get_business_availability(obj)
        return availability.get('is_business_open', False)
    
    def to_representation(self, instance):
        """Override to include sub_branches in the response for all master businesses"""
        representation = super().to_representation(instance)
        # Always include sub_branches for master businesses, each with their own is_visible status
        if instance.level == 'Master Level' or not instance.master:
            representation['sub_branches'] = self.get_sub_branches(instance)
        return representation


class MenuItemsSerializer(serializers.ModelSerializer):
    business_features = serializers.SerializerMethodField()
    item_image = serializers.SerializerMethodField()
    category_id = serializers.IntegerField(required=False, allow_null=True)
    category_name = serializers.SerializerMethodField()
    sub_Category_id = serializers.IntegerField(required=False, allow_null=True, source='sub_category_id')
    sub_category = serializers.CharField(max_length=100, required=False, allow_blank=True, allow_null=True)
    sub_category_name = serializers.SerializerMethodField()
    variants = serializers.SerializerMethodField()
    
    def get_variants(self, obj):
        from business.models import MenuItemVariant
        variants_qs = MenuItemVariant.objects.filter(item=obj).order_by('variant_id')
        return [
            {
                'variant_id': v.variant_id,
                'size_label': v.size_label,
                'selling_price': f"{round(float(v.selling_price)):.2f}" if v.selling_price is not None else None,
                'original_cost': f"{round(float(v.original_cost)):.2f}" if v.original_cost is not None else None,
                'gst_percentage': f"{float(v.gst):.2f}" if v.gst is not None else None,
                'stock': v.stock_qty,
                'is_active': v.is_active,
                'can_add_to_cart': v.is_active,
                'rating': float(v.rating) if v.rating else 4.0,
                'rating_count': int(v.rating_count) if v.rating_count else 0,
            }
            for v in variants_qs
        ]

    def get_category_name(self, obj):
        # Check universal_Categories if category_id exists
        if hasattr(obj, 'category_id') and obj.category_id:
            from django.db import connection
            with connection.cursor() as cursor:
                cursor.execute("SELECT category_name FROM universal_Categories WHERE category_id = %s", [obj.category_id])
                row = cursor.fetchone()
                if row:
                    return row[0]
        return getattr(obj, 'item_category', None)

    def get_sub_category_name(self, obj):
        if hasattr(obj, 'sub_category_id') and obj.sub_category_id:
            from django.db import connection
            with connection.cursor() as cursor:
                cursor.execute("SELECT category_name FROM universal_Categories WHERE category_id = %s", [obj.sub_category_id])
                row = cursor.fetchone()
                if row:
                    return row[0]
        return getattr(obj, 'sub_category', None)
    
    class Meta:
        model = MenuItems
        fields = [
            'item_id', 'item_name', 'description', 'item_image',
            'item_category', 'item_type', 'availability_timings', 'preparation_time',
            'quantity', 'charges', 'size_label', 'business_features', 'is_active', 'status', 'created_at', 'updated_at',
            'category_id', 'category_name', 'sub_Category_id', 'sub_category_name', 'sub_category', 'variants'
        ]
    
    def get_business_features(self, obj):
        """
        Fetch feature details from DB for the feature_ids stored in Business.business_features
        and return them in the format: 'FEA01 - Feature_Name'
        """
        if hasattr(obj, 'business_id') and obj.business_id:
            feature_ids = obj.business_id.business_features or []
            features = BusinessFeature.objects.filter(
                feature_id__in=feature_ids,
                status=True
            ).values_list("feature_id", "details")

            # make a mapping dict {feature_id: details}
            feature_map = dict(features)

            return [
                f"{fid} - {feature_map.get(fid, 'Unknown_Feature')}"
                for fid in feature_ids
            ]
        return []
    
    def get_item_image(self, obj):
        """Build S3 URL for item image"""
        return build_s3_file_url(obj.item_image)

class productItemsSerializer(serializers.ModelSerializer):
    business_features = serializers.SerializerMethodField()
    item_image = serializers.SerializerMethodField()
    
    class Meta:
        model = productItems
        fields = [
            'item_id', 'item_name', 'item_image', 'item_type', 'material', 'gender', 'color',
            'item_category', 'description', 'is_organic', 'availability_timings', 'weight',
            'size', 'unit', 'rating', 'rating_count', 'original_cost', 'gst', 'charges', 'selling_price',
            'wallet_points_availablity', 'wallet_points', 'mfg_data', 'expiry_date', 'stock',
            'business_features', 'is_active', 'status', 'created_at', 'updated_at'
        ]
    
    def get_business_features(self, obj):
        """
        Fetch feature details from DB for the feature_ids stored in Business.business_features
        and return them in the format: 'FEA01 - Feature_Name'
        """
        if hasattr(obj, 'business_id') and obj.business_id:
            feature_ids = obj.business_id.business_features or []
            features = BusinessFeature.objects.filter(
                feature_id__in=feature_ids,
                status=True
            ).values_list("feature_id", "details")

            # make a mapping dict {feature_id: details}
            feature_map = dict(features)

            return [
                f"{fid} - {feature_map.get(fid, 'Unknown_Feature')}"
                for fid in feature_ids
            ]
        return []
    
    def get_item_image(self, obj):
        """Build S3 URL for item image"""
        return build_s3_file_url(obj.item_image)

class MenuCartSerializer(serializers.ModelSerializer):
    class Meta:
        model = MenuCart
        fields = "__all__"


class OrderSerializer(serializers.ModelSerializer):
    order_number = serializers.UUIDField(read_only=True)
    business_name = serializers.CharField(source='business_id.businessName', read_only=True)
    user_name = serializers.CharField(source='user_id.name', read_only=True)
    
    class Meta:
        model = Orders
        fields = [
            'order_id', 'order_number', 'user_id', 'business_id', 'business_name', 'user_name',
            'order_type', 'status', 'total_amount', 'discount_amount', 'delivery_charges',
            'final_amount', 'delivery_address_snapshot', 'billing_address_snapshot',
            'delivery_address', 'coupon_code', 'wallet_points_used', 'estimated_delivery_time',
            'actual_delivery_time', 'scheduled_time','delivery_instruction', 'order_instruction', 
            'created_at', 'updated_at'
        ]
        read_only_fields = ['order_id', 'order_number', 'created_at', 'updated_at']


class OrderItemSerializer(serializers.ModelSerializer):
    enhanced_product_details = serializers.SerializerMethodField()
    item_details = serializers.SerializerMethodField()
    variant_details = serializers.SerializerMethodField()
    base_product_id = serializers.SerializerMethodField()
    item_name = serializers.CharField(source='item_name_snapshot', read_only=True)
    base_unit_price = serializers.SerializerMethodField()
    customization_extra_unit = serializers.SerializerMethodField()
    customization_extra_total = serializers.SerializerMethodField()
    unit_price = serializers.SerializerMethodField()
    delivery_instruction = serializers.SerializerMethodField()
    order_instruction = serializers.SerializerMethodField()
    image_url = serializers.SerializerMethodField()
    product_id = serializers.SerializerMethodField()
    variant_id = serializers.SerializerMethodField()
    name = serializers.CharField(source='item_name_snapshot', read_only=True)
    description = serializers.SerializerMethodField()
    category = serializers.SerializerMethodField()
    type = serializers.SerializerMethodField()
    brand_name = serializers.SerializerMethodField()
    rating = serializers.SerializerMethodField()
    is_organic = serializers.SerializerMethodField()
    gst = serializers.SerializerMethodField()
    tax_amount = serializers.SerializerMethodField()
    
    class Meta:
        model = OrderItems
        fields = [
            'item_id', 'order_id', 'menu_item_id', 'product_item_id', 'product_id', 'variant_id', 'item_name_snapshot',
            'quantity', 'unit_price_snapshot', 'total_price', 'item_details_snapshot',
            'base_product_id', 'item_name', 'base_unit_price', 'customization_extra_unit',
            'customization_extra_total', 'unit_price', 'item_details', 'variant_details',
            'customizations', 'delivery_instruction', 'order_instruction', 
            'created_at', 'enhanced_product_details', 'image_url', 'name',
            'description', 'category', 'type', 'brand_name', 'rating', 'is_organic', 'gst', 'tax_amount'
        ]
        read_only_fields = ['item_id', 'created_at']

    def _resolve_fashion_details(self, obj):
        request = self.context.get('request')
        # Use variant_id column if available, else fallback to product_item_id
        variant_id_to_use = getattr(obj, 'variant_id', None) or obj.product_item_id
        if not variant_id_to_use:
            return None
        try:
            from django.db import connection
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT fp.product_id, fp.name, fp.description, fp.main_image, uc.category_name,
                           fpv.variant_id, fpv.size, fpv.color
                    FROM fashion_product_variants fpv
                    JOIN fashion_products fp ON fpv.product_id = fp.product_id
                    LEFT JOIN universal_Categories uc ON fp.category_id = uc.category_id
                    WHERE fpv.variant_id = %s
                    LIMIT 1
                    """,
                    [variant_id_to_use],
                )
                row = cursor.fetchone()
                if not row:
                    return None

                product_id, name, description, main_image, category_name, variant_id, size, color = row
                image_url = build_s3_file_url(main_image)

                return {
                    'product_id': int(product_id) if product_id is not None else None,
                    'variant_id': int(variant_id) if variant_id is not None else None,
                    'product_name': name,
                    'brand_name': None,
                    'description': description,
                    'image_url': image_url,
                    'category': category_name,
                    'is_organic': None,
                    'rating': None,
                    'size': size,
                    'color': color,
                }
        except Exception:
            return None

    def _resolve_grocery_variant_details(self, obj):
        """Resolve Groceries_ProductVariants_1 details for R01 using variant_id column."""
        variant_id_to_use = getattr(obj, 'variant_id', None) or obj.product_item_id
        if not variant_id_to_use:
            return None
        try:
            from django.db import connection
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT v.variant_id, v.product_id, v.net_weight, v.net_weight_unit, v.size,
                           v.original_cost, v.selling_price, v.gst,
                           v.color, v.gender, v.age, v.min_age, v.max_age, v.material,
                           v.attributes, v.pack, v.dimension
                    FROM Groceries_ProductVariants_1 v
                    WHERE v.variant_id = %s
                    LIMIT 1
                    """,
                    [variant_id_to_use],
                )
                row = cursor.fetchone()
                if not row:
                    return None

                (
                    variant_id, product_id, net_weight, net_weight_unit, size,
                    original_cost, selling_price, gst,
                    color, gender, age, min_age, max_age, material,
                    attributes, pack, dimension,
                ) = row

                import json as _json
                def _try_json(val):
                    if val is None:
                        return None
                    if isinstance(val, (dict, list)):
                        return val
                    if isinstance(val, str):
                        try:
                            return _json.loads(val)
                        except Exception:
                            return val
                    return val

                return {
                    'variant_id': int(variant_id) if variant_id is not None else None,
                    'product_id': int(product_id) if product_id is not None else None,
                    'net_weight': float(net_weight) if net_weight is not None else None,
                    'net_weight_unit': net_weight_unit,
                    'size': _try_json(size),
                    'original_cost': f"{round(float(original_cost)):.2f}" if original_cost is not None else None,
                    'selling_price': f"{round(float(selling_price)):.2f}" if selling_price is not None else None,
                    'gst_percentage': f"{float(gst):.2f}" if gst is not None else None,
                    'color': color,
                    'gender': gender,
                    'age': age,
                    'min_age': min_age,
                    'max_age': max_age,
                    'material': material,
                    'attributes': _try_json(attributes),
                    'pack': pack,
                    'dimension': _try_json(dimension),
                }
        except Exception:
            return None
    
    def _resolve_restaurant_variant_details(self, obj):
        """Resolve MenuItemVariant details for R02 using variant_id column."""
        request = self.context.get('request')
        variant_id_to_use = getattr(obj, 'variant_id', None) or obj.product_item_id
        if not variant_id_to_use:
            return None
        try:
            from django.db import connection
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT mv.variant_id, mv.item_id, mi.item_name, mi.description, mi.item_image,
                           mv.selling_price, mv.original_cost, mi.gst, mv.size, mv.color
                    FROM menu_item_variants mv
                    JOIN menuItems mi ON mv.item_id = mi.item_id
                    WHERE mv.variant_id = %s AND mv.is_active = 1
                    LIMIT 1
                    """,
                    [variant_id_to_use],
                )
                row = cursor.fetchone()
                if not row:
                    return None

                variant_id, item_id, item_name, description, item_image, selling_price, original_cost, gst, size, color = row
                image_url = build_s3_file_url(item_image)

                return {
                    'product_id': item_id,
                    'variant_id': variant_id,
                    'product_name': item_name,
                    'brand_name': None,
                    'description': description,
                    'image_url': image_url,
                    'category': None,
                    'is_organic': None,
                    'rating': None,
                    'size': size,
                    'color': color,
                    'selling_price': f"{float(selling_price):.2f}" if selling_price is not None else None,
                    'original_cost': f"{float(original_cost):.2f}" if original_cost is not None else None,
                    'gst_percentage': f"{float(gst):.2f}" if gst is not None else None,
                }
        except Exception:
            return None
    
    def get_enhanced_product_details(self, obj):
        """Get enhanced product details from respective variant tables based on business type"""
        if obj.product_item_id:
            try:
                bt = None
                try:
                    bt = getattr(getattr(obj.order_id, 'business_id', None), 'businessType', None)
                except Exception:
                    bt = None

                if str(bt).upper() == 'R08':
                    details = self._resolve_fashion_details(obj)
                    if details:
                        return details
                elif str(bt).upper() == 'R02':
                    details = self._resolve_restaurant_variant_details(obj)
                    if details:
                        return details
                elif str(bt).upper() == 'R01':
                    # Use variant_id column if available, else fallback to product_item_id
                    variant_id_to_use = getattr(obj, 'variant_id', None) or obj.product_item_id
                    resolved_product_id = None
                    if variant_id_to_use:
                        # Try to resolve via Groceries_ProductVariants_1 first
                        try:
                            from django.db import connection
                            with connection.cursor() as cursor:
                                cursor.execute("SELECT product_id FROM Groceries_ProductVariants_1 WHERE variant_id = %s LIMIT 1", [variant_id_to_use])
                                map_row = cursor.fetchone()
                                if map_row:
                                    resolved_product_id = map_row[0]
                                    # Get full product details
                                    cursor.execute("""
                                        SELECT 
                                            p.product_name,
                                            p.brand_name,
                                            p.description,
                                            p.main_image,
                                            p.sub_category,
                                            p.is_organic,
                                            p.rating
                                        FROM Groceries_Products p
                                        WHERE p.product_id = %s
                                    """, [resolved_product_id])
                                    row = cursor.fetchone()
                                    if row:
                                        request = self.context.get('request')
                                        image_url = None
                                        if row[3] and request:  # main_image
                                            # Build absolute URL safely; do not prepend base if already absolute
                                            rel_path = str(row[3]).strip()
                                            low = rel_path.lower()
                                            if low.startswith('http://') or low.startswith('https://'):
                                                image_url = _normalize_media_url(rel_path)
                                            else:
                                                # Clean common prefixes
                                                rel_clean = rel_path.lstrip('/')
                                                if rel_clean.startswith('media/'):
                                                    rel_clean = rel_clean[6:]
                                                # If path already starts with kirazee route, use it directly
                                                    image_url = build_s3_file_url(rel_clean)
                                        return {
                                            'product_id': resolved_product_id,
                                            'variant_id': variant_id_to_use,
                                            'product_name': row[0],
                                            'brand_name': row[1],
                                            'description': row[2],
                                            'image_url': image_url,
                                            'category': row[4],  # sub_category
                                            'is_organic': bool(row[5]),
                                            'rating': float(row[6]) if row[6] is not None else None
                                        }
                        except Exception:
                            pass
                    # If variant resolution failed, try direct product lookup
                    if not resolved_product_id:
                        try:
                            from django.db import connection
                            with connection.cursor() as cursor:
                                cursor.execute("SELECT product_id FROM Groceries_Products WHERE product_id = %s LIMIT 1", [obj.product_item_id])
                                row_pid = cursor.fetchone()
                                if row_pid:
                                    resolved_product_id = row_pid[0]
                                    # Get full product details
                                    cursor.execute("""
                                        SELECT 
                                            p.product_name,
                                            p.brand_name,
                                            p.description,
                                            p.main_image,
                                            p.sub_category,
                                            p.is_organic,
                                            p.rating
                                        FROM Groceries_Products p
                                        WHERE p.product_id = %s
                                    """, [resolved_product_id])
                                    row = cursor.fetchone()
                                    if row:
                                        request = self.context.get('request')
                                        image_url = None
                                        if row[3] and request:  # main_image
                                            # Build absolute URL safely; do not prepend base if already absolute
                                            rel_path = str(row[3]).strip()
                                            low = rel_path.lower()
                                            if low.startswith('http://') or low.startswith('https://'):
                                                image_url = _normalize_media_url(rel_path)
                                            else:
                                                # Clean common prefixes
                                                rel_clean = rel_path.lstrip('/')
                                                if rel_clean.startswith('media/'):
                                                    rel_clean = rel_clean[6:]
                                                # If path already starts with kirazee route, use it directly
                                                    image_url = build_s3_file_url(rel_clean)
                                        return {
                                            'product_id': resolved_product_id,
                                            'variant_id': variant_id_to_use,
                                            'product_name': row[0],
                                            'brand_name': row[1],
                                            'description': row[2],
                                            'image_url': image_url,
                                            'category': row[4],  # sub_category
                                            'is_organic': bool(row[5]),
                                            'rating': float(row[6]) if row[6] is not None else None
                                        }
                        except Exception:
                            pass
            except Exception:
                pass

            try:
                from django.db import connection
                with connection.cursor() as cursor:
                    # Use variant_id column if available, else fallback to product_item_id
                    variant_id_to_use = getattr(obj, 'variant_id', None) or obj.product_item_id
                    # Resolve groceries product_id when product_item_id stores variant_id
                    # 1) Try variant->product mapping
                    cursor.execute("SELECT product_id FROM Groceries_ProductVariants_1 WHERE variant_id = %s LIMIT 1", [variant_id_to_use])
                    map_row = cursor.fetchone()
                    resolved_product_id = None
                    resolved_variant_id = None
                    if map_row:
                        resolved_product_id = map_row[0]
                        resolved_variant_id = variant_id_to_use
                    else:
                        # 2) Fallback: treat product_item_id as product_id directly (legacy data)
                        cursor.execute("SELECT product_id FROM Groceries_Products WHERE product_id = %s LIMIT 1", [obj.product_item_id])
                        row_pid = cursor.fetchone()
                        if row_pid:
                            resolved_product_id = row_pid[0]

                    if resolved_product_id:
                        cursor.execute("""
                            SELECT 
                                p.product_name,
                                p.brand_name,
                                p.description,
                                p.main_image,
                                p.sub_category,
                                p.is_organic,
                                p.rating
                            FROM Groceries_Products p
                            WHERE p.product_id = %s
                        """, [resolved_product_id])
                        row = cursor.fetchone()
                        if row:
                            request = self.context.get('request')
                            image_url = build_s3_file_url(row[3])
                            # Prefer variant_id from DB mapping; fallback to snapshot if available
                            variant_from_snapshot = None
                            try:
                                if isinstance(obj.item_details_snapshot, dict):
                                    variant_from_snapshot = obj.item_details_snapshot.get('variant_id')
                            except Exception:
                                variant_from_snapshot = None
                            return {
                                'product_id': resolved_product_id,
                                'variant_id': resolved_variant_id if resolved_variant_id is not None else variant_from_snapshot,
                                'product_name': row[0],
                                'brand_name': row[1],
                                'description': row[2],
                                'image_url': image_url,
                                'category': row[4],  # sub_category
                                'is_organic': bool(row[5]),
                                'rating': float(row[6]) if row[6] is not None else None
                            }
            except Exception as e:
                # Log error but don't break the serialization
                import logging
                logger = logging.getLogger(__name__)
                logger.error(f"Error fetching enhanced product details: {str(e)}")
        
        return None

    def get_base_product_id(self, obj):
        """Base product id for the order line (canonical product_id)."""
        return self.get_product_id(obj)

    def get_base_unit_price(self, obj):
        """Unit price without any additional customization extras (currently same as snapshot)."""
        try:
            return float(obj.unit_price_snapshot)
        except Exception:
            return obj.unit_price_snapshot

    def get_customization_extra_unit(self, obj):
        return 0.0

    def get_customization_extra_total(self, obj):
        return 0.0

    def get_unit_price(self, obj):
        return self.get_base_unit_price(obj)

    def get_item_details(self, obj):
        """Return item_details as snapshot + variant-specific attributes from the respective businessType."""
        base = {}
        try:
            if isinstance(obj.item_details_snapshot, dict):
                base = dict(obj.item_details_snapshot)
        except Exception:
            base = {}

        product_id = self.get_product_id(obj)
        variant_id = self.get_variant_id(obj)
        if product_id is not None:
            base['product_id'] = product_id
        if variant_id is not None:
            base['variant_id'] = variant_id

        try:
            bt = getattr(getattr(obj.order_id, 'business_id', None), 'businessType', None)
        except Exception:
            bt = None

        bt_val = str(bt).upper() if bt is not None else None
        variant_details = None
        if bt_val == 'R08':
            variant_details = self._resolve_fashion_details(obj)
        elif bt_val == 'R02':
            variant_details = self._resolve_restaurant_variant_details(obj)
        elif bt_val == 'R01':
            variant_details = self._resolve_grocery_variant_details(obj)

        if isinstance(variant_details, dict):
            allowed = {
                'product_id', 'variant_id', 'description', 'category', 'type',
                'gst_percentage', 'gst_amount', 'original_cost', 'selling_price',
                'size', 'color',
                'net_weight', 'net_weight_unit', 'pack', 'attributes', 'material',
                'gender', 'age', 'min_age', 'max_age', 'dimension',
            }
            for k, v in variant_details.items():
                if k in allowed and v is not None:
                    base[k] = v

        return base
    
    def get_delivery_instruction(self, obj):
        """Get delivery instruction from the parent order"""
        return obj.order_id.delivery_instruction if obj.order_id else None
    
    def get_order_instruction(self, obj):
        """Get order instruction from the parent order"""
        return obj.order_id.order_instruction if obj.order_id else None

    def get_image_url(self, obj):
        """Build absolute image URL for the order item.
        Priority:
        - If it's a menu item (R02 restaurant), use MenuItems.item_image
        - If it's a product item (R02 products), use productItems.item_image
        - For groceries (R01), the image is available under enhanced_product_details
        """
        request = self.context.get('request')
        if not request:
            return None
        try:
            bt = None
            try:
                bt = getattr(getattr(obj.order_id, 'business_id', None), 'businessType', None)
            except Exception:
                bt = None

            # Menu item image (restaurant menu)
            if obj.menu_item_id:
                try:
                    menu = MenuItems.objects.get(item_id=obj.menu_item_id)
                    if getattr(menu, 'item_image', None):
                        return build_s3_file_url(menu.item_image)
                except MenuItems.DoesNotExist:
                    pass

            # Product item image (restaurant products)
            if obj.product_item_id:
                if str(bt).upper() == 'R08':
                    details = self._resolve_fashion_details(obj)
                    if details and details.get('image_url'):
                        return details.get('image_url')
                    return None

                try:
                    prod = productItems.objects.get(item_id=obj.product_item_id)
                    if getattr(prod, 'item_image', None):
                        return build_s3_file_url(prod.item_image)
                except productItems.DoesNotExist:
                    pass

                # Groceries fallback: resolve product_id and return main_image
                try:
                    pid, _ = self._resolve_grocery_ids(obj)
                    if pid:
                        from django.db import connection
                        with connection.cursor() as cursor:
                            cursor.execute("SELECT main_image FROM Groceries_Products WHERE product_id = %s LIMIT 1", [pid])
                            row = cursor.fetchone()
                            if row and row[0]:
                                return build_s3_file_url(row[0])
                except Exception:
                    pass
        except Exception:
            # Be resilient: never break serialization due to image issues
            return None
        return None

    def _resolve_grocery_ids(self, obj):
        """Helper to resolve groceries product_id and variant_id from product_item_id when needed."""
        # Use variant_id column if available, else fallback to product_item_id
        variant_id_to_use = getattr(obj, 'variant_id', None) or obj.product_item_id
        if not variant_id_to_use:
            return (None, None)
        try:
            from django.db import connection
            with connection.cursor() as cursor:
                cursor.execute("SELECT product_id FROM Groceries_ProductVariants_1 WHERE variant_id = %s LIMIT 1", [variant_id_to_use])
                row = cursor.fetchone()
                if row:
                    return (row[0], variant_id_to_use)
                cursor.execute("SELECT product_id FROM Groceries_Products WHERE product_id = %s LIMIT 1", [obj.product_item_id])
                row2 = cursor.fetchone()
                if row2:
                    return (row2[0], None)
                # Snapshot fallback when DB mapping doesn't resolve variant/product
                try:
                    if isinstance(obj.item_details_snapshot, dict):
                        pid = obj.item_details_snapshot.get('product_id')
                        vid = obj.item_details_snapshot.get('variant_id')
                        return (pid, vid)
                except Exception:
                    pass
        except Exception:
            pass
        return (None, None)

    def get_product_id(self, obj):
        """Expose canonical product_id for groceries; for non-grocery returns productItems.item_id or None."""
        # If menu item, no product_id
        if obj.menu_item_id:
            return None
        try:
            bt = getattr(getattr(obj.order_id, 'business_id', None), 'businessType', None)
            if str(bt).upper() == 'R08':
                details = self._resolve_fashion_details(obj)
                if details and details.get('product_id') is not None:
                    return int(details.get('product_id'))
                if isinstance(obj.item_details_snapshot, dict) and obj.item_details_snapshot.get('product_id') is not None:
                    return int(obj.item_details_snapshot.get('product_id'))
        except Exception:
            pass
        # Try groceries resolution
        pid, _ = self._resolve_grocery_ids(obj)
        if pid:
            return int(pid)
        # Else fall back to productItems (R02 products)
        try:
            return int(obj.product_item_id) if obj.product_item_id is not None else None
        except Exception:
            return obj.product_item_id

    def get_variant_id(self, obj):
        """Expose variant_id from OrderItems.variant_id column; fallback to resolution logic."""
        # Prefer explicit variant_id column
        if getattr(obj, 'variant_id', None) is not None:
            try:
                return int(obj.variant_id)
            except Exception:
                return obj.variant_id

        # Menu items (restaurants) don't have variant_id in this schema unless stored in snapshot
        if obj.menu_item_id:
            try:
                if isinstance(obj.item_details_snapshot, dict) and obj.item_details_snapshot.get('variant_id') is not None:
                    return int(obj.item_details_snapshot.get('variant_id'))
            except Exception:
                return obj.item_details_snapshot.get('variant_id') if isinstance(obj.item_details_snapshot, dict) else None
            return None

        # Fashion fallback
        try:
            bt = getattr(getattr(obj.order_id, 'business_id', None), 'businessType', None)
            if str(bt).upper() == 'R08':
                details = self._resolve_fashion_details(obj)
                if details and details.get('variant_id') is not None:
                    return int(details.get('variant_id'))
        except Exception:
            pass

        # Groceries fallback
        try:
            _, vid = self._resolve_grocery_ids(obj)
            if vid is not None:
                return int(vid)
        except Exception:
            pass

        # Final fallback: snapshot
        try:
            if isinstance(obj.item_details_snapshot, dict) and obj.item_details_snapshot.get('variant_id') is not None:
                return int(obj.item_details_snapshot.get('variant_id'))
        except Exception:
            return obj.item_details_snapshot.get('variant_id') if isinstance(obj.item_details_snapshot, dict) else None
        return None

    def get_description(self, obj):
        """Get description from enhanced_product_details or fallback to snapshot"""
        details = self.get_enhanced_product_details(obj)
        if details and details.get('description') is not None:
            return details.get('description')
        # Fallback to snapshot
        try:
            if isinstance(obj.item_details_snapshot, dict):
                return obj.item_details_snapshot.get('description')
        except Exception:
            pass
        return None
    
    def get_category(self, obj):
        """Get category from enhanced_product_details or fallback to snapshot"""
        details = self.get_enhanced_product_details(obj)
        if details and details.get('category') is not None:
            return details.get('category')
        # Fallback to snapshot
        try:
            if isinstance(obj.item_details_snapshot, dict):
                return obj.item_details_snapshot.get('category')
        except Exception:
            pass
        return None
    
    def get_type(self, obj):
        """Get type/subcategory from enhanced_product_details or fallback to snapshot"""
        details = self.get_enhanced_product_details(obj)
        if details and details.get('type') is not None:
            return details.get('type')
        # Fallback to snapshot
        try:
            if isinstance(obj.item_details_snapshot, dict):
                return obj.item_details_snapshot.get('type')
        except Exception:
            pass
        return None
    
    def get_brand_name(self, obj):
        """Get brand_name from enhanced_product_details or fallback to snapshot"""
        details = self.get_enhanced_product_details(obj)
        if details and details.get('brand_name') is not None:
            return details.get('brand_name')
        # Fallback to snapshot
        try:
            if isinstance(obj.item_details_snapshot, dict):
                return obj.item_details_snapshot.get('brand_name')
        except Exception:
            pass
        return None
    
    def get_rating(self, obj):
        """Get rating from enhanced_product_details or fallback to snapshot"""
        details = self.get_enhanced_product_details(obj)
        if details and details.get('rating') is not None:
            return details.get('rating')
        # Fallback to snapshot
        try:
            if isinstance(obj.item_details_snapshot, dict):
                return obj.item_details_snapshot.get('rating')
        except Exception:
            pass
        return None
    
    def get_is_organic(self, obj):
        """Get is_organic from enhanced_product details or fallback to snapshot"""
        details = self.get_enhanced_product_details(obj)
        if details and details.get('is_organic') is not None:
            return details.get('is_organic')
        # Fallback to snapshot
        try:
            if isinstance(obj.item_details_snapshot, dict):
                return obj.item_details_snapshot.get('is_organic')
        except Exception:
            pass
        return None
    
    def get_gst(self, obj):
        """Get GST percentage from enhanced_product_details or fallback to snapshot"""
        details = self.get_enhanced_product_details(obj)
        if details and details.get('gst_percentage') is not None:
            return details.get('gst_percentage')
        # Fallback to snapshot
        try:
            if isinstance(obj.item_details_snapshot, dict):
                return obj.item_details_snapshot.get('gst_percentage')
        except Exception:
            pass
        return None
    
    def get_tax_amount(self, obj):
        """Get GST amount from enhanced_product_details or fallback to snapshot"""
        details = self.get_enhanced_product_details(obj)
        if details and details.get('gst_amount') is not None:
            return details.get('gst_amount')
        # Fallback to snapshot
        try:
            if isinstance(obj.item_details_snapshot, dict):
                return obj.item_details_snapshot.get('gst_amount')
        except Exception:
            pass
        return None

    def get_variant_details(self, obj):
        """Get comprehensive variant details based on business type"""
        request = self.context.get('request')
        if not request:
            return None
            
        # Get business type from the order
        try:
            business_type = getattr(obj.order_id, 'business_id', None)
            if business_type:
                from kirazee_app.models import Business
                business = Business.objects.get(business_id=business_type.business_id)
                business_type = business.businessType
            else:
                return None
        except Exception:
            return None
        
        # Use variant_id column if available, else fallback to product_item_id
        variant_id_to_use = getattr(obj, 'variant_id', None) or obj.product_item_id
        if not variant_id_to_use:
            return None
        
        # Get variant details based on business type
        if business_type == 'R01':
            return self._get_grocery_variant_details(variant_id_to_use)
        elif business_type == 'R02':
            return self._get_restaurant_variant_details(variant_id_to_use, request)
        elif business_type == 'R08':
            return self._get_fashion_variant_details(variant_id_to_use, request)
        else:
            return None
    
    def _get_grocery_variant_details(self, variant_id):
        """Get comprehensive grocery variant details matching business endpoint format"""
        try:
            from django.db import connection
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT v.variant_id, v.product_id, v.sku, v.barcode,
                           v.net_weight, v.net_weight_unit, v.size,
                           v.original_cost, v.selling_price, v.charges, v.gst, v.stock,
                           v.mfg_date, v.expiry_date, v.is_active, v.created_at, v.updated_at,
                           v.color, v.gender, v.age, v.material, v.attributes, v.pack,
                           v.is_visible_counter, v.price_override, v.min_age, v.max_age, v.dimension
                    FROM Groceries_ProductVariants_1 v
                    WHERE v.variant_id = %s
                    LIMIT 1
                    """,
                    [variant_id],
                )
                row = cursor.fetchone()
                if not row:
                    return None

                import json as _json
                def _try_json(val):
                    if val is None:
                        return None
                    if isinstance(val, (dict, list)):
                        return val
                    if isinstance(val, str):
                        try:
                            return _json.loads(val)
                        except Exception:
                            return val
                    return val

                return {
                    "variant_id": row[0],
                    "product_id": row[1],
                    "sku": row[2],
                    "barcode": row[3],
                    "net_weight": row[4],
                    "net_weight_unit": row[5],
                    "size": _try_json(row[6]),
                    "original_cost": float(row[7]) if row[7] is not None else None,
                    "selling_price": float(row[8]) if row[8] is not None else None,
                    "price_override": float(row[18]) if row[18] is not None else None,
                    "charges": float(row[9]) if row[9] is not None else None,
                    "gst": float(row[10]) if row[10] is not None else None,
                    "stock": row[11],
                    "mfg_date": row[12].isoformat() if row[12] else None,
                    "expiry_date": row[13].isoformat() if row[13] else None,
                    "is_active": bool(row[14]) if row[14] is not None else True,
                    "created_at": row[15].isoformat() if row[15] else None,
                    "updated_at": row[16].isoformat() if row[16] else None,
                    "color": row[17],
                    "gender": row[18],
                    "age": row[19],
                    "material": row[20],
                    "attributes": _try_json(row[21]),
                    "pack": row[22],
                    "is_visible_counter": bool(row[23]) if row[23] is not None else False,
                    "min_age": row[24],
                    "max_age": row[25],
                    "dimension": _try_json(row[26]),
                }
        except Exception:
            return None
    
    def _get_fashion_variant_details(self, variant_id, request):
        """Get comprehensive fashion variant details matching business endpoint format"""
        try:
            from django.db import connection
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT fpv.variant_id, fpv.product_id, fpv.sku, fpv.barcode,
                           fpv.selling_price, fpv.mrp, fpv.stock_qty, fpv.net_weight, fpv.net_weight_unit,
                           fpv.original_cost, fpv.charges, fpv.stock, fpv.mfg_date, fpv.expiry_date,
                           fpv.size, fpv.color, fpv.material, fpv.gender, fpv.min_age, fpv.max_age,
                           fpv.pack, fpv.attributes, fpv.dimension, fpv.is_active, fpv.created_at, fpv.updated_at
                    FROM fashion_product_variants fpv
                    WHERE fpv.variant_id = %s
                    LIMIT 1
                    """,
                    [variant_id],
                )
                row = cursor.fetchone()
                if not row:
                    return None

                import json as _json
                def _try_json(val):
                    if val is None:
                        return None
                    if isinstance(val, (dict, list)):
                        return val
                    if isinstance(val, str):
                        try:
                            return _json.loads(val)
                        except Exception:
                            return val
                    return val

                return {
                    "variant_id": row[0],
                    "product_id": row[1],
                    "sku": row[2],
                    "barcode": row[3],
                    "selling_price": float(row[4]) if row[4] is not None else None,
                    "mrp": float(row[5]) if row[5] is not None else None,
                    "stock_qty": row[6],
                    "net_weight": row[7],
                    "net_weight_unit": row[8],
                    "original_cost": float(row[9]) if row[9] is not None else None,
                    "charges": float(row[10]) if row[10] is not None else None,
                    "stock": row[11],
                    "mfg_date": row[12].isoformat() if row[12] else None,
                    "expiry_date": row[13].isoformat() if row[13] else None,
                    "size": row[14],
                    "color": row[15],
                    "material": row[16],
                    "gender": row[17],
                    "min_age": row[18],
                    "max_age": row[19],
                    "pack": row[20],
                    "attributes": _try_json(row[21]),
                    "dimension": _try_json(row[22]),
                    "is_active": bool(row[23]) if row[23] is not None else True,
                    "created_at": row[24].isoformat() if row[24] else None,
                    "updated_at": row[25].isoformat() if row[25] else None,
                }
        except Exception:
            return None
    
    def _get_restaurant_variant_details(self, variant_id, request):
        """Get comprehensive restaurant variant details matching business endpoint format"""
        try:
            from django.db import connection
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT mv.variant_id, mv.item_id, mv.selling_price, mv.original_cost,
                           mv.size, mv.color, mv.stock_qty, mv.is_active, mv.created_at, mv.updated_at
                    FROM menu_item_variants mv
                    WHERE mv.variant_id = %s
                    LIMIT 1
                    """,
                    [variant_id],
                )
                row = cursor.fetchone()
                if not row:
                    return None

                return {
                    "variant_id": row[0],
                    "menu_item_id": row[1],
                    "selling_price": float(row[2]) if row[2] is not None else None,
                    "original_cost": float(row[3]) if row[3] is not None else None,
                    "size": row[4],
                    "color": row[5],
                    "stock_qty": row[6],
                    "is_active": bool(row[7]) if row[7] is not None else True,
                    "created_at": row[8].isoformat() if row[8] else None,
                    "updated_at": row[9].isoformat() if row[9] else None,
                }
        except Exception:
            return None


class OrderDetailSerializer(serializers.ModelSerializer):
    order_number = serializers.UUIDField(read_only=True)
    business_details = serializers.SerializerMethodField()
    user_details = serializers.SerializerMethodField()
    delivery_address_details = serializers.SerializerMethodField()
    available_transitions = serializers.SerializerMethodField()
    total_gst = serializers.SerializerMethodField()
    items_total = serializers.SerializerMethodField()
    subtotal = serializers.SerializerMethodField()
    calculated_final_amount = serializers.SerializerMethodField()
    payment_status = serializers.SerializerMethodField()
    payment_method = serializers.SerializerMethodField()
    
    class Meta:
        model = Orders
        fields = [
            'order_id', 'order_number', 'token_num', 'user_id', 'business_id', 'business_details',
            'user_details', 'order_type', 'status', 'items_total',
            'delivery_charges', 'parcel_charges', 'total_gst', 'subtotal', 'discount_amount',
            'calculated_final_amount', 'final_amount', 'delivery_address_snapshot',
            'billing_address_snapshot', 'delivery_address_details', 'coupon_code',
            'wallet_points_used', 'estimated_delivery_time', 'actual_delivery_time',
            'delivery_instruction', 'order_instruction', 'available_transitions', 
            'payment_status', 'payment_method',
            'created_at', 'updated_at'
        ]
    
    def get_business_details(self, obj):
        if obj.business_id:
            logo_url = build_s3_file_url(getattr(obj.business_id, 'logo', None))
            banner_url = build_s3_file_url(getattr(obj.business_id, 'banner', None))

            return {
                'business_id': obj.business_id.business_id,
                'business_name': obj.business_id.businessName,
                'business_type': obj.business_id.businessType,
                'address': obj.business_id.address,
                'business_number': obj.business_id.businessNumber,
                'contact_mobile': obj.business_id.contact_mobile,
                'contact_support': obj.business_id.contact_support,
                'logo_url': logo_url,
                'banner_url': banner_url
            }
        return None
    
    def get_user_details(self, obj):
        if obj.user_id:
            return {
                'user_id': obj.user_id.user_id,
                'first_name': obj.user_id.firstName,
                'last_name': obj.user_id.lastName,
                'mobile_number': obj.user_id.mobileNumber,
                'email': obj.user_id.emailID
            }
        return None
    
    def get_delivery_address_details(self, obj):
        if obj.delivery_address_snapshot:
            return obj.delivery_address_snapshot
        elif obj.delivery_address:
            # Access address data from the JSONField
            address_data = obj.delivery_address.address or {}
            return {
                'address_line_1': address_data.get('street', ''),
                'address_line_2': address_data.get('Door no', ''),
                'city': address_data.get('city/town', ''),
                'state': address_data.get('state', ''),
                'pincode': address_data.get('pincode', ''),
                'country': address_data.get('country', ''),
                'latitude': address_data.get('latitude'),
                'longitude': address_data.get('longitude'),
                'address_type': obj.delivery_address.address_type
            }
        return None
    
    def get_available_transitions(self, obj):
        transitions = []
        for transition in obj.get_available_status_transitions():
            transitions.append({
                'action': transition.name,
                'target_status': transition.target,
                'description': transition.name.replace('_', ' ').title()
            })
        return transitions
    
    def get_total_gst(self, obj):
        """Calculate total GST from all order items"""
        from decimal import Decimal
        total_gst = Decimal('0.00')
        
        try:
            # Get all order items for this order
            order_items = obj.items.all()
            
            for item in order_items:
                # Get GST amount from item details snapshot
                if item.item_details_snapshot and isinstance(item.item_details_snapshot, dict):
                    gst_amount = item.item_details_snapshot.get('gst_amount', 0)
                    if gst_amount:
                        # Convert to Decimal and multiply by quantity
                        gst_per_item = round(Decimal(str(gst_amount)))
                        total_gst += gst_per_item * Decimal(str(item.quantity))
        
        except Exception as e:
            # Log error but don't fail the serialization
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f"Error calculating total GST for order {obj.order_id}: {str(e)}")
            total_gst = Decimal('0.00')
        
        return float(total_gst)
    
    def get_items_total(self, obj):
        """Calculate items total: sum(unit_price * quantity)"""
        from decimal import Decimal
        items_total = Decimal('0.00')
        
        try:
            # Get all order items for this order
            order_items = obj.items.all()
            
            for item in order_items:
                # Get unit price from snapshot and multiply by quantity
                unit_price = Decimal(str(item.unit_price_snapshot))
                items_total += unit_price * Decimal(str(item.quantity))
        
        except Exception as e:
            # Log error but don't fail the serialization
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f"Error calculating items total for order {obj.order_id}: {str(e)}")
            items_total = Decimal('0.00')
        
        return float(items_total)
    
    def get_subtotal(self, obj):
        """Calculate subtotal: total_gst + parcel_charges + delivery_charges + items_total"""
        from decimal import Decimal
        
        try:
            total_gst = Decimal(str(self.get_total_gst(obj)))
            items_total = Decimal(str(self.get_items_total(obj)))
            parcel_charges = Decimal(str(obj.parcel_charges))
            delivery_charges = Decimal(str(obj.delivery_charges))
            
            subtotal = total_gst + parcel_charges + delivery_charges + items_total
            return float(subtotal)
        
        except Exception as e:
            # Log error but don't fail the serialization
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f"Error calculating subtotal for order {obj.order_id}: {str(e)}")
            return 0.0
    
    def get_calculated_final_amount(self, obj):
        """Calculate final amount: subtotal - coupon_discount - wallet_points_value"""
        from decimal import Decimal
        
        try:
            subtotal = Decimal(str(self.get_subtotal(obj)))
            coupon_discount = Decimal(str(obj.discount_amount))
            wallet_points_value = Decimal(str(obj.wallet_points_used))
            
            calculated_final_amount = subtotal - coupon_discount - wallet_points_value
            return float(calculated_final_amount)
        
        except Exception as e:
            # Log error but don't fail the serialization
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f"Error calculating final amount for order {obj.order_id}: {str(e)}")
            return 0.0

    def get_payment_status(self, obj):
        try:
            p = Payments.objects.filter(order_id=obj.order_id).order_by('-created_at').first()
            return p.status if p else None
        except Exception:
            return None

    def get_payment_method(self, obj):
        try:
            p = Payments.objects.filter(order_id=obj.order_id).order_by('-created_at').first()
            return p.payment_method if p else None
        except Exception:
            return None


class OrderListSerializer(serializers.ModelSerializer):
    order_number = serializers.UUIDField(read_only=True)
    business_name = serializers.CharField(source='business_id.businessName', read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    order_customer_type_display = serializers.CharField(source='get_order_customer_type_display', read_only=True)
    logo_url = serializers.SerializerMethodField()
    banner_url = serializers.SerializerMethodField()
    items_count = serializers.SerializerMethodField()
    payment_status = serializers.SerializerMethodField()
    payment_method = serializers.SerializerMethodField()
    
    class Meta:
        model = Orders
        fields = [
            'order_id', 'order_number', 'token_num', 'business_name', 'logo_url', 'banner_url',
            'order_type', 'status_display', 'final_amount', 'created_at', 'items_count',
            'payment_status', 'payment_method', 'order_customer_type', 'order_customer_type_display'
        ]
    
    def get_items_count(self, obj):
        """Get the count of items in the order"""
        return obj.items.count() if hasattr(obj, 'items') else 0
    
    def get_logo_url(self, obj):
        """Get business logo S3 URL"""
        return build_s3_file_url(getattr(obj.business_id, 'logo', None))
    
    def get_banner_url(self, obj):
        """Get business banner S3 URL"""
        return build_s3_file_url(getattr(obj.business_id, 'banner', None))

    def get_payment_status(self, obj):
        try:
            p = Payments.objects.filter(order_id=obj.order_id).order_by('-created_at').first()
            return p.status if p else None
        except Exception:
            return None

    def get_payment_method(self, obj):
        try:
            p = Payments.objects.filter(order_id=obj.order_id).order_by('-created_at').first()
            return p.payment_method if p else None
        except Exception:
            return None


class WalletPointsSerializer(serializers.ModelSerializer):
    transaction_type_display = serializers.CharField(source='get_transaction_type_display', read_only=True)
    rupee_value = serializers.SerializerMethodField()
    
    class Meta:
        model = WalletPoints
        fields = [
            'wallet_id', 'user_id', 'transaction_type', 'transaction_type_display',
            'points', 'balance_after', 'rupee_value', 'related_order', 'related_coupon_purchase',
            'description', 'expires_at', 'is_expired', 'created_at'
        ]
        read_only_fields = ['wallet_id', 'balance_after', 'created_at']
    
    def get_rupee_value(self, obj):
        return float(obj.points * 0.10)  # 10 points = 1 rupee


class CouponSerializer(serializers.ModelSerializer):
    business_name = serializers.CharField(source='business_id.businessName', read_only=True)
    discount_display = serializers.SerializerMethodField()
    usage_remaining = serializers.SerializerMethodField()
    
    class Meta:
        model = Coupons
        fields = [
            'coupon_id', 'coupon_code', 'name', 'discount_type', 'discount_value', 'discount_display',
            'created_by', 'business_id', 'business_name', 'valid_from', 'valid_to',
            'is_active', 'max_total_redemptions', 'max_redemptions_per_user', 'current_usage_count',
            'visibility_type', 'coupon_scope', 'free_delivery', 'free_packaging',
            'usage_remaining', 'created_at', 'updated_at'
        ]
        read_only_fields = ['coupon_id', 'current_usage_count', 'created_at', 'updated_at']
    
    def get_discount_display(self, obj):
        if obj.discount_type == 'percentage':
            return f'{obj.discount_value}% OFF'
        elif obj.discount_type == 'fixed_amount':
            return f'₹{obj.discount_value} OFF'
        elif obj.discount_type == 'free_delivery':
            return 'FREE DELIVERY'
        elif obj.discount_type == 'bogo':
            return 'BUY 1 GET 1'
        return f'{obj.discount_value} OFF'
    
    def get_usage_remaining(self, obj):
        if obj.max_total_redemptions:
            return max(0, obj.max_total_redemptions - obj.current_usage_count)
        return None


class CouponRulesSerializer(serializers.ModelSerializer):
    class Meta:
        model = CouponRules
        fields = [
            'rule_id', 'coupon_id', 'rule_type', 'rule_value', 'is_active', 'created_at'
        ]
        read_only_fields = ['rule_id', 'created_at']




class CouponRedemptionSerializer(serializers.ModelSerializer):
    coupon_code = serializers.CharField(source='coupon_id.coupon_code', read_only=True)
    order_number = serializers.UUIDField(source='order_id.order_number', read_only=True)
    user_name = serializers.CharField(source='user_id.name', read_only=True)
    
    class Meta:
        model = CouponRedemptions
        fields = [
            'redemption_id', 'coupon_id', 'coupon_code', 'order_id', 'order_number',
            'user_id', 'user_name', 'discount_amount_applied', 'original_order_amount',
            'final_order_amount', 'redeemed_at'
        ]
        read_only_fields = ['redemption_id', 'redeemed_at']


class DeliveryChargesSerializer(serializers.ModelSerializer):
    business_name = serializers.CharField(source='business_id.businessName', read_only=True)
    
    class Meta:
        model = DeliveryCharges
        fields = [
            'delivery_id', 'business_id', 'business_name', 'base_charge', 'parcel_charges', 'distance_slabs',
            'free_delivery_above', 'max_charge', 'max_delivery_distance', 'peak_hours_start',
            'peak_hours_end', 'peak_hour_multiplier', 'is_active', 'created_at', 'updated_at'
        ]
        read_only_fields = ['delivery_id', 'created_at', 'updated_at']


class PointsConfigurationSerializer(serializers.ModelSerializer):
    business_name = serializers.CharField(source='business_id.businessName', read_only=True)
    
    class Meta:
        model = PointsConfiguration
        fields = [
            'config_id', 'business_id', 'business_name', 'points_per_rupee_spent',
            'points_per_rupee_value', 'min_order_value_for_points', 'max_points_per_order',
            'points_expiry_days', 'is_active', 'created_at', 'updated_at'
        ]
        read_only_fields = ['config_id', 'created_at', 'updated_at']


class SearchResultSerializer(serializers.Serializer):
    """Unified search result serializer for businesses, menu items, and product items"""
    result_type = serializers.CharField()  # 'business', 'menu_item', 'product_item'
    id = serializers.CharField()
    name = serializers.CharField()
    description = serializers.CharField(allow_blank=True, allow_null=True)
    image_url = serializers.CharField(allow_blank=True, allow_null=True)
    business_id = serializers.CharField(allow_null=True)
    business_name = serializers.CharField(allow_blank=True, allow_null=True)
    business_type = serializers.CharField(allow_blank=True, allow_null=True)
    category = serializers.CharField(allow_blank=True, allow_null=True)
    price = serializers.DecimalField(max_digits=10, decimal_places=2, allow_null=True)
    rating = serializers.FloatField(allow_null=True)
    distance_km = serializers.FloatField(allow_null=True)
    is_available = serializers.BooleanField()
    location = serializers.CharField(allow_blank=True, allow_null=True)
    
    class Meta:
        fields = [
            'result_type', 'id', 'name', 'description', 'image_url', 'business_id',
            'business_name', 'business_type', 'category', 'price', 'rating', 
            'distance_km', 'is_available', 'location'
        ]


class BusinessSearchSerializer(serializers.ModelSerializer):
    """Simplified business serializer for search results"""
    logo_url = serializers.SerializerMethodField()
    distance_km = serializers.SerializerMethodField()
    rating = serializers.SerializerMethodField()
    
    class Meta:
        model = Business
        fields = [
            'business_id', 'businessName', 'businessType', 'businessCategory',
            'description', 'logo_url', 'address', 'city', 'state', 'latitude',
            'longitude', 'distance_km', 'rating', 'businessNumber', 'is_verified'
        ]
    
    def get_logo_url(self, obj):
        return build_s3_file_url(obj.logo)
        return None
    
    def get_distance_km(self, obj):
        return getattr(obj, 'distance_km', None)
    
    def get_rating(self, obj):
        return 4.0  # Default rating


class MenuItemSearchSerializer(serializers.ModelSerializer):
    """Simplified menu item serializer for search results"""
    item_image_url = serializers.SerializerMethodField()
    business_name = serializers.CharField(source='business_id.businessName', read_only=True)
    business_type = serializers.CharField(source='business_id.businessType', read_only=True)
    
    class Meta:
        model = MenuItems
        fields = [
            'item_id', 'item_name', 'description', 'item_image_url', 'item_category',
            'item_type', 'selling_price', 'business_id', 'business_name', 'business_type',
            'is_active', 'status'
        ]
    
    def get_item_image_url(self, obj):
        return build_s3_file_url(obj.item_image)
        return None


class ProductItemSearchSerializer(serializers.ModelSerializer):
    """Simplified product item serializer for search results"""
    item_image_url = serializers.SerializerMethodField()
    business_name = serializers.CharField(source='business_id.businessName', read_only=True)
    business_type = serializers.CharField(source='business_id.businessType', read_only=True)
    
    class Meta:
        model = productItems
        fields = [
            'item_id', 'item_name', 'description', 'item_image_url', 'item_category',
            'item_type', 'selling_price', 'business_id', 'business_name', 'business_type',
            'is_active', 'status', 'stock'
        ]
    
    def get_item_image_url(self, obj):
        return build_s3_file_url(obj.item_image)
        return None
