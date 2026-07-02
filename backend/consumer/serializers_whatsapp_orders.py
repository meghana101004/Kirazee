from rest_framework import serializers
from decimal import Decimal
from .models import Orders


class WhatsAppOrderItemSerializer(serializers.Serializer):
    item_name = serializers.CharField(max_length=255)
    quantity = serializers.IntegerField(min_value=1)
    unit_price = serializers.DecimalField(max_digits=10, decimal_places=2, required=False, default=Decimal('0.00'))
    customizations = serializers.JSONField(required=False, default=list)
    menu_item_id = serializers.IntegerField(required=False, allow_null=True)
    product_item_id = serializers.IntegerField(required=False, allow_null=True)


class CustomerSerializer(serializers.Serializer):
    firstName = serializers.CharField(max_length=100)
    lastName = serializers.CharField(max_length=100, required=False, allow_blank=True, default="")
    countryCode = serializers.CharField(max_length=10)
    mobileNumber = serializers.CharField(max_length=15)
    emailID = serializers.EmailField(max_length=255)


class WhatsAppOrderCreateSerializer(serializers.Serializer):
    order_type = serializers.ChoiceField(choices=[c[0] for c in Orders.OrderType.choices], default=Orders.OrderType.DELIVERY)
    total_amount = serializers.DecimalField(max_digits=10, decimal_places=2, required=False)
    discount_amount = serializers.DecimalField(max_digits=10, decimal_places=2, required=False, default=Decimal('0.00'))
    delivery_charges = serializers.DecimalField(max_digits=10, decimal_places=2, required=False, default=Decimal('0.00'))
    parcel_charges = serializers.DecimalField(max_digits=10, decimal_places=2, required=False, default=Decimal('0.00'))
    final_amount = serializers.DecimalField(max_digits=10, decimal_places=2, required=False)
    coupon_code = serializers.CharField(required=False, allow_blank=True, default="")
    delivery_address = serializers.JSONField(required=False)
    items = WhatsAppOrderItemSerializer(many=True)
    customer = CustomerSerializer()

    def validate(self, attrs):
        items = attrs.get('items') or []
        if not items:
            raise serializers.ValidationError({'items': 'At least one item is required.'})
        return attrs

class WhatsAppItemSearchSerializer(serializers.Serializer):
    q = serializers.CharField(max_length=255)
    limit = serializers.IntegerField(required=False, min_value=1, max_value=50, default=20)

