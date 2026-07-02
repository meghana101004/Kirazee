# your_app/urls.py

from django.urls import path
from .views import (
    RegistrationAPIView,
    OtpVerificationAPIView,
    LoginAPIView,
    VerifyLoginOtpAPIView,
    LogoutAPIView,
    ChangeModeAPIView,
    UpdateProfileAPIView,
    UpdateProfileImageAPIView,
    AddressAPIView,
    UserComprehensiveDetailsAPIView,
    NavigationAPIView,
    UserProfileAPIView,
    UserAddressesAPIView,
    SendRegistrationOTPAPIView,
    PrivacyPolicyView,
    TermsOfUseView,
    refundPolicy,
    shippingPolicy,
    faqs,
    CompanyRegistrationAPIView,
    CompanyVerificationAPIView,
    CompanyListAPIView,
    CompanyDetailAPIView,
    CompanyEmployeeListAPIView,
    CompanyEmployeeAPIView,
    CompanyOrderAPIView,
    CompanyOrdersListAPIView,
    CompanyOrderDetailAPIView,
    CompanyOffersAPIView,
    sitemap,
    docmap,
    splash_screen,
)
from .company_address_views import (
    CompanyAddressAPIView,
    CompanyAddressDetailAPIView,
)
urlpatterns = [
    #Kirazee Account Management
    path('', sitemap, name='site_map'),
    path('docmap/', docmap, name='doc_map'),
    path('register/', RegistrationAPIView.as_view(), name='user-register'), # Register
    path('send-otp/', SendRegistrationOTPAPIView.as_view(), name='send-otp'),
    path('verify-otp/', OtpVerificationAPIView.as_view(), name='user-verify-otp'), # Verify OTP
    path('login/', LoginAPIView.as_view(), name='user-login'),     # Login
    path('verify-login-otp/', VerifyLoginOtpAPIView.as_view(), name='user-verify-login-otp'), # Verify Login OTP
    path('logout/', LogoutAPIView.as_view(), name='user-logout'),     # Logout
    path('change_mode', ChangeModeAPIView.as_view(), name='change-mode'),    # Change Mode
    path('update-profile', UpdateProfileAPIView.as_view(), name='update-profile'),    # Update profile / delete account
    path('update-profile-image', UpdateProfileImageAPIView.as_view(), name='update-profile-image'),
    path('address', AddressAPIView.as_view(), name='user-address'),    # Create/Update/Delete addresses
    path('user-comprehensive', UserComprehensiveDetailsAPIView.as_view(), name='user-comprehensive'),
    path('navigation', NavigationAPIView.as_view(), name='navigation'),    # Navigation items based on mode and category
    path('user-profile/', UserProfileAPIView.as_view(), name='user-profile'),    # Get user profile by userID
    path('user-addresses/', UserAddressesAPIView.as_view(), name='user-addresses'),    # Get user addresses by userID
    path('privacy-policy', PrivacyPolicyView, name='privacy-policy'),
    path('terms-of-use', TermsOfUseView, name='terms-of-use'),
    path('refund-policy', refundPolicy, name='refundPolicy'),
    path('shipping-policy', shippingPolicy, name='shippingPolicy'),
    path('faqs', faqs, name='faqs'),
    path('splash-screen', splash_screen, name='splash-screen'),
    
    # Company/B2B Management
    path('company/register/', CompanyRegistrationAPIView.as_view(), name='company-register'),
    path('company/verify/<int:company_id>/', CompanyVerificationAPIView.as_view(), name='company-verify'),
    path('company/list/', CompanyListAPIView.as_view(), name='company-list'),
    path('company/<int:company_id>/', CompanyDetailAPIView.as_view(), name='company-detail'),
    path('company/<int:company_id>/employees/', CompanyEmployeeListAPIView.as_view(), name='company-employee-list'),
    path('company/<int:company_id>/employees/add/', CompanyEmployeeAPIView.as_view(), name='company-employee-add'),
    path('company/<int:company_id>/orders/', CompanyOrderAPIView.as_view(), name='company-orders'),
    path('company/<int:company_id>/orders/list/', CompanyOrdersListAPIView.as_view(), name='company-order-list'),
    path('company/<int:company_id>/orders/<str:order_id>/', CompanyOrderDetailAPIView.as_view(), name='company-order-detail'),
    path('company/<int:company_id>/offers/', CompanyOffersAPIView.as_view(), name='company-offers'),
    path('company/<int:company_id>/addresses/', CompanyAddressAPIView.as_view(), name='company-address-list'),
    path('company/<int:company_id>/addresses/<int:address_id>/', CompanyAddressDetailAPIView.as_view(), name='company-address-detail'),
]