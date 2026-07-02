"""
Vendor Admin Configuration
"""
from django.contrib import admin
from .models import VendorProfiles


@admin.register(VendorProfiles)
class VendorProfilesAdmin(admin.ModelAdmin):
    list_display = ['vendor_id', 'shop_name', 'business_type', 'approval_status', 'is_vendor_approved', 'is_active', 'created_at']
    list_filter = ['approval_status', 'is_vendor_approved', 'is_active', 'business_type']
    search_fields = ['shop_name', 'shop_slug', 'contact_email', 'contact_phone', 'gst_number']
    readonly_fields = ['vendor_id', 'created_at', 'updated_at']
    
    fieldsets = (
        ('Basic Information', {
            'fields': ('vendor_id', 'user', 'shop_name', 'shop_slug', 'business_type')
        }),
        ('Business Details', {
            'fields': ('business_category', 'business_description', 'years_in_business', 'shop_address', 'shipping_from')
        }),
        ('Contact Information', {
            'fields': ('contact_email', 'contact_phone', 'website_url', 'social_instagram', 'social_facebook')
        }),
        ('Documents', {
            'fields': ('gst_number', 'gst_image_url', 'aadhar_number', 'aadhar_image_url')
        }),
        ('Verification & Approval', {
            'fields': ('is_gst_verified', 'is_vendor_approved', 'approval_status', 'rejection_reason')
        }),
        ('Business Settings', {
            'fields': ('commission_percentage', 'max_products_limit', 'logo_url', 'default_shipping_states', 'metadata')
        }),
        ('Status', {
            'fields': ('is_active', 'created_at', 'updated_at')
        }),
    )
