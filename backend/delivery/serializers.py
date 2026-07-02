# delivery_partner/serializers.py
from rest_framework import serializers
from .models import DeliveryPartner, OrderOTP
from consumer.serializers import OrderListSerializer
from consumer.models import Orders
from kirazee_app.models import Registration
from delivery.image_utils import build_s3_file_url

class DeliveryPartnerSerializer(serializers.ModelSerializer):
    name = serializers.SerializerMethodField()
    email = serializers.EmailField(source='user.emailID', read_only=True)
    user_id = serializers.IntegerField(source='user.user_id', read_only=True)
    business_id = serializers.CharField(read_only=True)
    created_at = serializers.DateTimeField(read_only=True)
    updated_at = serializers.DateTimeField(read_only=True)
    status = serializers.SerializerMethodField()

    class Meta:
        model = DeliveryPartner
        fields = [
            'id', 'user_id', 'business_id', 'name', 'email', 'phone_number',
            'vehicle_type', 'vehicle_number', 'status', 'is_available', 'rating',
            'total_deliveries', 'current_location', 'is_verified',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['rating', 'total_deliveries']
    
    def get_name(self, obj):
        first = getattr(obj.user, 'firstName', '') or ''
        last = getattr(obj.user, 'lastName', '') or ''
        full = f"{first} {last}".strip()
        return full or str(getattr(obj.user, 'user_id', ''))

    def get_status(self, obj):
        # Map model choices to boolean-like string as requested
        # Treat 'available' and 'on_delivery' or numeric '1' as active -> '1', else '0'
        raw = obj.status
        if raw is None:
            return '0'
        val = str(raw).strip().lower()
        return '1' if val in {'1', 'available', 'on_delivery'} else '0'

class LocationSerializer(serializers.Serializer):
    latitude = serializers.FloatField()
    longitude = serializers.FloatField()

class OrderOTPSerializer(serializers.ModelSerializer):
    class Meta:
        model = OrderOTP
        fields = ['otp', 'is_verified', 'expires_at']
        read_only_fields = ['otp', 'is_verified', 'expires_at']

class NearbyOrdersSerializer(serializers.ModelSerializer):
    distance_km = serializers.SerializerMethodField()
    business_name = serializers.CharField(source='business.name')
    business_address = serializers.CharField(source='business.address')

    class Meta:
        model = Orders
        fields = [
            'id', 'order_number', 'status', 'total_amount',
            'distance_km', 'business_name', 'business_address'
        ]

    def get_distance_km(self, obj):
        return getattr(obj, 'distance_km', None)

class UserProfileSerializer(serializers.ModelSerializer):
    """Serializer for Registration model data"""
    displayName = serializers.SerializerMethodField()
    profileUrl = serializers.SerializerMethodField()
    
    class Meta:
        model = Registration
        fields = [
            'user_id', 'firstName', 'lastName', 'displayName', 'countryCode',
            'mobileNumber', 'emailID', 'dob', 'is_verified', 'is_active',
            'user_mode', 'profileUrl', 'os', 'status', 'whichapp',
            'created_at', 'updated_at'
        ]
    
    def get_displayName(self, obj):
        return f"{obj.firstName} {obj.lastName}"
    
    def get_profileUrl(self, obj):
        """Build S3 URL for profile image"""
        return build_s3_file_url(obj.profileUrl)

class DeliveryPartnerProfileSerializer(serializers.ModelSerializer):
    """Serializer for DeliveryPartner model data"""
    current_location = serializers.SerializerMethodField()
    
    class Meta:
        model = DeliveryPartner
        fields = [
            'id', 'vehicle_type', 'vehicle_number', 'latitude', 'longitude',
            'status', 'is_available', 'rating', 'total_deliveries',
            'phone_number', 'is_verified', 'created_at', 'updated_at',
            'current_location'
        ]
    
    def get_current_location(self, obj):
        if obj.latitude is not None and obj.longitude is not None:
            return [obj.latitude, obj.longitude]
        return None

class CombinedProfileSerializer(serializers.Serializer):
    """Combined serializer for user registration and delivery partner data"""
    user_data = UserProfileSerializer()
    delivery_partner_data = DeliveryPartnerProfileSerializer()
    
class DeliveryPartnerRegistrationSerializer(serializers.Serializer):
    vehicle_type = serializers.CharField()
    vehicle_number = serializers.CharField()
    phone_number = serializers.CharField()
    license_number = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    full_address = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    city = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    state = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    pincode = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    delivery_service_area = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    delivery_timings = serializers.JSONField(required=False, allow_null=True)
    business_id = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    latitude = serializers.FloatField(required=False, allow_null=True)
    longitude = serializers.FloatField(required=False, allow_null=True)
    status = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    is_available = serializers.BooleanField(required=False)
        
    def validate_vehicle_type(self, value):
        """
        Validates that the vehicle type is one of the allowed choices,
        and normalizes the output to a capitalized format.
        """
        # 1. A clean, lowercase set for efficient and case-insensitive checking.
        valid_types = {'bike', 'scooter', 'car', 'bicycle', 'scooty', 'van', 'auto', 'motorcycle'}
        
        # 2. Convert the input value to lowercase for comparison.
        normalized_value = value.lower()

        # 3. Check for membership in the clean set.
        if normalized_value not in valid_types:
            # Show the user the clean list of options.
            raise serializers.ValidationError(f"Vehicle type must be one of: {sorted(list(valid_types))}")

        # 4. Return the value in a consistent, capitalized format.
        return normalized_value.capitalize()
    
    def validate_latitude(self, value):
        """Validate latitude is within valid range"""
        if value is not None:
            if not -90 <= value <= 90:
                raise serializers.ValidationError("Latitude must be between -90 and 90 degrees")
        return value
    
    def validate_longitude(self, value):
        """Validate longitude is within valid range"""
        if value is not None:
            if not -180 <= value <= 180:
                raise serializers.ValidationError("Longitude must be between -180 and 180 degrees")
        return value

class DeliveryPartnerFinancialsSerializer(serializers.Serializer):
    pan_number = serializers.CharField(max_length=10)
    bank_account_number = serializers.CharField(max_length=50)
    ifsc_code = serializers.CharField(max_length=11)

    def validate_pan_number(self, value):
        v = value.strip().upper()
        if len(v) != 10:
            raise serializers.ValidationError("PAN must be 10 characters")
        return v

    def validate_ifsc_code(self, value):
        return value.strip().upper()

class DeliveryPartnerDocumentUploadSerializer(serializers.Serializer):
    document_type = serializers.ChoiceField(choices=['license','rc_book','aadhar','bank_book'])
    file = serializers.FileField()

class BasicDeliveryPartnerSignupSerializer(DeliveryPartnerRegistrationSerializer):
    """Serializer to capture both user registration and delivery partner basic details"""
    firstName = serializers.CharField(required=False, allow_blank=True, default="")
    lastName = serializers.CharField(required=False, allow_blank=True, default="")
    countryCode = serializers.CharField(required=False, allow_blank=True, default="+91")
    mobileNumber = serializers.CharField()
    emailID = serializers.EmailField()
    # Make phone_number optional; default to mobileNumber in view if absent
    phone_number = serializers.CharField(required=False, allow_blank=True)

class ActiveDeliveryPartnerSerializer(serializers.Serializer):
    """Serializer for active delivery partners list"""
    id = serializers.IntegerField()
    user_id = serializers.IntegerField()
    name = serializers.CharField()
    phone_number = serializers.CharField()
    vehicle_type = serializers.CharField()
    vehicle_number = serializers.CharField()
    rating = serializers.FloatField()
    total_deliveries = serializers.IntegerField()
    current_location = serializers.ListField(child=serializers.FloatField(), allow_null=True)
    distance_km = serializers.FloatField(allow_null=True)
    is_available = serializers.BooleanField()
    status = serializers.CharField()

class OrderAssignmentSerializer(serializers.Serializer):
    """Serializer for order assignment"""
    delivery_partner_id = serializers.IntegerField()
    
    def validate_delivery_partner_id(self, value):
        """Validate delivery partner exists and is available"""
        from .models import DeliveryPartner
        try:
            partner = DeliveryPartner.objects.get(id=value)
            if not partner.is_available:
                raise serializers.ValidationError("Delivery partner is not available")
            return value
        except DeliveryPartner.DoesNotExist:
            raise serializers.ValidationError("Delivery partner not found")

class DeliveryOrderSerializer(serializers.Serializer):
    """Serializer for delivery partner orders"""
    order_id = serializers.CharField()
    order_number = serializers.CharField()
    business_name = serializers.CharField()
    business_address = serializers.CharField()
    customer_name = serializers.CharField()
    customer_phone = serializers.CharField()
    delivery_address = serializers.CharField()
    total_amount = serializers.DecimalField(max_digits=10, decimal_places=2)
    status = serializers.CharField()
    order_type = serializers.CharField()
    created_at = serializers.DateTimeField()
    updated_at = serializers.DateTimeField()
    delivery_charges = serializers.DecimalField(max_digits=10, decimal_places=2, allow_null=True)
    estimated_delivery_time = serializers.CharField(allow_null=True)

class PendingOrderSerializer(serializers.Serializer):
    """Serializer for pending orders from both orders and Groceries_orders tables"""
    order_id = serializers.IntegerField()
    order_number = serializers.CharField(allow_null=True)
    token_num = serializers.IntegerField(required=False, allow_null=True)
    order_type = serializers.CharField()
    order_status = serializers.CharField()
    payment_status = serializers.CharField()
    total_amount = serializers.DecimalField(max_digits=10, decimal_places=2)
    final_amount = serializers.DecimalField(max_digits=10, decimal_places=2)
    delivery_charge = serializers.DecimalField(max_digits=10, decimal_places=2, allow_null=True)
    discount = serializers.DecimalField(max_digits=10, decimal_places=2, allow_null=True)
    gst_amount = serializers.DecimalField(max_digits=10, decimal_places=2, allow_null=True)
    
    # Customer details
    customer_id = serializers.IntegerField()
    customer_name = serializers.CharField()
    customer_phone = serializers.CharField()
    customer_email = serializers.CharField(allow_null=True)
    
    # Business details
    business_id = serializers.CharField()
    business_name = serializers.CharField()
    business_type = serializers.CharField(allow_null=True)
    
    # Address and delivery
    delivery_address = serializers.CharField(allow_null=True, allow_blank=True)
    delivery_instructions = serializers.CharField(allow_null=True)
    delivery_time = serializers.DateTimeField(allow_null=True)
    scheduled_time = serializers.DateTimeField(allow_null=True)
    pickup_time = serializers.DateTimeField(allow_null=True)
    
    # Order items count
    items_count = serializers.IntegerField(allow_null=True)
    
    # Items with customizations (optional)
    class ItemSerializer(serializers.Serializer):
        name = serializers.CharField()
        quantity = serializers.IntegerField(allow_null=True)
        customizations = serializers.JSONField(required=False, allow_null=True)
    items = ItemSerializer(many=True, required=False)

    # Optional items preview (for lightweight list cards)
    class ItemPreviewSerializer(serializers.Serializer):
        name = serializers.CharField(allow_null=True, required=False)
        image = serializers.CharField(allow_null=True, required=False)
        quantity = serializers.IntegerField(allow_null=True, required=False)
        item_type = serializers.CharField(allow_null=True, required=False)
    items_preview = ItemPreviewSerializer(many=True, required=False)
    
    # Timestamps
    created_at = serializers.DateTimeField()
    updated_at = serializers.DateTimeField()
    
    # System info
    order_system = serializers.CharField(help_text="'regular' for orders table, 'grocery' for Groceries_orders table")
    
    # Company/B2B Details
    company_details = serializers.JSONField(required=False, allow_null=True)

class PendingOrdersResponseSerializer(serializers.Serializer):
    """Response serializer for pending orders API"""
    success = serializers.BooleanField()
    message = serializers.CharField()
    total_pending_orders = serializers.IntegerField(required=False, default=0)
    regular_orders_count = serializers.IntegerField(required=False, default=0)
    grocery_orders_count = serializers.IntegerField(required=False, default=0)
    orders = PendingOrderSerializer(many=True)
    estimated_delivery_time = serializers.CharField(required=False, allow_null=True, default=None)
    
    # Optional pagination and counts blocks from the response
    class PaginationSerializer(serializers.Serializer):
        total_orders = serializers.IntegerField()
        current_page = serializers.IntegerField()
        per_page = serializers.IntegerField()
        total_pages = serializers.IntegerField()
        has_next_page = serializers.BooleanField()
        has_prev_page = serializers.BooleanField()
        next_offset = serializers.IntegerField(allow_null=True)
        prev_offset = serializers.IntegerField(allow_null=True)
    pagination = PaginationSerializer(required=False)
    
    class CountsSerializer(serializers.Serializer):
        total_orders = serializers.IntegerField()
        regular_orders_count = serializers.IntegerField()
        grocery_orders_count = serializers.IntegerField()
        current_batch_count = serializers.IntegerField()
    counts = CountsSerializer(required=False)