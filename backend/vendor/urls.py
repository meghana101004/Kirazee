"""
Vendor API URL Configuration
"""
from django.urls import path
from .views import (
    VendorRegistrationAPIView, 
    VendorProfileUpdateAPIView, 
    VendorProductAPIView,
    VendorProductApprovalAPIView,
    VendorProductSyncStatusAPIView,
    VendorProductBulkUploadAPIView,
    VendorApprovalAPIView
)

urlpatterns = [
    path('register/', VendorRegistrationAPIView.as_view(), name='vendor-register'),# Vendor Registration
    path('<int:vendor_id>/profile/', VendorProfileUpdateAPIView.as_view(), name='vendor-profile-update'),# Vendor Profile Management (by vendor_id)
    path('user/<int:user_id>/profile/', VendorProfileUpdateAPIView.as_view(), name='vendor-profile-by-user'), # duplicate registion profile update service
    
    # Product management by vendor_id
    path('<int:vendor_id>/products/', VendorProductAPIView.as_view(), name='vendor-products-list'), # Vendor Product Management
    path('<int:vendor_id>/products/<int:product_id>/', VendorProductAPIView.as_view(), name='vendor-product-detail'),
    
    # Product management by user_id
    path('user/<int:user_id>/products/', VendorProductAPIView.as_view(), name='vendor-products-list-by-user'), # Vendor Product Management by user_id
    path('user/<int:user_id>/products/<int:product_id>/', VendorProductAPIView.as_view(), name='vendor-product-detail-by-user'), # Vendor Product Detail by user_id
    path('user/<int:user_id>/products/bulk/', VendorProductBulkUploadAPIView.as_view(), name='vendor-products-bulk-upload-by-user'), # Vendor Product Bulk Upload by user_id
    
    path('<int:vendor_id>/products/bulk/', VendorProductBulkUploadAPIView.as_view(), name='vendor-products-bulk-upload'),# Vendor Product Bulk Upload
    path('<str:business_id>/<str:businessType>/<int:vendor_id>/products/<int:product_id>/approve/', VendorProductApprovalAPIView.as_view(), name='vendor-product-approval'), # Vendor Product Approval (Admin, business-aware)
    path('<int:vendor_id>/products/<int:product_id>/sync/', VendorProductSyncStatusAPIView.as_view(), name='vendor-product-sync'),
    path('<int:vendor_id>/approve/', VendorApprovalAPIView.as_view(), name='vendor-approval'),
    path('approval/', VendorApprovalAPIView.as_view(), name='vendor-approval-list'),        
]
