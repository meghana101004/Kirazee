# delivery/admin.py
from django.contrib import admin
from .models import DeliveryPartner, DeliveryLocationHistory, OrderOTP

@admin.register(DeliveryPartner)
class DeliveryPartnerAdmin(admin.ModelAdmin):
    list_display = ('user', 'vehicle_type', 'status', 'is_available', 'total_deliveries', 'rating')
    list_filter = ('status', 'is_available', 'vehicle_type')
    search_fields = ('user__first_name', 'user__last_name', 'user__email', 'phone_number')
    readonly_fields = ('latitude', 'longitude')

@admin.register(DeliveryLocationHistory)
class DeliveryLocationHistoryAdmin(admin.ModelAdmin):
    list_display = ('delivery_partner', 'timestamp')
    list_filter = ('delivery_partner',)
    readonly_fields = ('timestamp', 'latitude', 'longitude')

@admin.register(OrderOTP)
class OrderOTPAdmin(admin.ModelAdmin):
    list_display = ('order_id', 'otp', 'is_verified', 'created_at', 'expires_at')
    list_filter = ('is_verified',)
    readonly_fields = ('created_at', 'updated_at', 'expires_at')
    search_fields = ('order_id', 'otp')