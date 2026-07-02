# delivery/urls.py
from django.urls import path
from django.views.decorators.csrf import csrf_exempt
from . import views
from . import regisrations
urlpatterns = [
    # Profile
    path('get-profile/', regisrations.GetDeliveryPartnerProfileView.as_view(), name='get-delivery-partner-profile'),
    path('register/', regisrations.RegisterDeliveryPartnerView.as_view(), name='register-delivery-partner'),
    # Onboarding (Applicant-Facing)
    path('api/v1/partners/onboarding/start-session/', regisrations.StartOrResumeOnboardingSessionView.as_view(), name='dp-onboarding-start-session'),
    
    path('boys/', views.DeliveryPartnerListView.as_view(), name='list-delivery-partners'),
    # Location
    path('update-location/', csrf_exempt(regisrations.UpdateDeliveryPartnerLocation.as_view()), name='update_delivery_location'),
    # Partner self-service
    path('api/v1/partners/me/availability/', regisrations.PartnerAvailabilityView.as_view(), name='dp-availability'),
    path('api/v1/partners/update/', regisrations.UpdateDeliveryPartnerDetailsView.as_view(), name='dp-update-details'),

    # Documents & Financials
    path('api/v1/partners/documents/upload/', regisrations.DeliveryPartnerDocumentUploadView.as_view(), name='dp-docs-upload'),
    path('api/v1/partners/financials/', regisrations.DeliveryPartnerFinancialsUpsertView.as_view(), name='dp-financials-upsert'),
    
    # Basic signup (no OTP)
    path('api/v1/partners/signup/basic/', regisrations.BasicDeliveryPartnerSignupView.as_view(), name='dp-basic-signup'),
    
    # Business Owner Services
    path('display/active-partners/', views.ActiveDeliveryPartnersView.as_view(), name='active-delivery-partners'),
    path('assign-order/', views.AssignOrderView.as_view(), name='assign-order'),

    # Orders management services
    path('orders/nearby/', views.NearbyOrdersView.as_view(), name='nearby-orders'),
    path('display-took-orders/', views.DeliveryPartnerOrdersView.as_view(), name='delivery-partner-orders'),
    path('assigned-orders/', views.AssignedOrdersView.as_view(), name='assigned-orders'),
    path('orders/<int:order_id>/accept/', views.OrderAcceptView.as_view(), name='accept-order'),
    path('orders/<int:order_id>/status/', views.OrderStatusUpdateView.as_view(), name='update-order-status'),
    path('orders/<int:order_id>/', views.OrderDetailsView.as_view(), name='order-details'),
    
    # Admin KYC
    path('api/v1/admin/applicants/', regisrations.AdminApplicantListView.as_view(), name='dp-admin-applicants-list'),
    path('api/v1/admin/applicants/<int:application_id>/', regisrations.AdminApplicantDetailView.as_view(), name='dp-admin-applicant-detail'),
    path('api/v1/admin/applicants/<int:application_id>/status/', regisrations.AdminApplicantStatusUpdateView.as_view(), name='dp-admin-applicant-status'),
    path('api/v1/admin/applicants/<int:application_id>/decision/', regisrations.ApplicantDecisionView.as_view(), name='dp-applicant-decision'),
    path('api/v1/admin/partners/unverified/', regisrations.AdminUnverifiedPartnersListView.as_view(), name='dp-admin-unverified-partners'),
    path('api/v1/admin/partners/<int:partner_id>/', regisrations.AdminPartnerDetailView.as_view(), name='dp-admin-partner-detail'),
    path('api/v1/admin/partners/<int:partner_id>/documents/<str:document_type>/verify/', regisrations.AdminPartnerDocumentVerifyView.as_view(), name='dp-admin-verify-document'),
    path('api/v1/admin/partners/<int:partner_id>/approve/', regisrations.AdminPartnerApproveView.as_view(), name='dp-admin-approve-partner'),
    path('api/v1/admin/partners/<int:partner_id>/reject/', regisrations.AdminPartnerRejectView.as_view(), name='dp-admin-reject-partner'),
    
    # OTP
    path('send-order-otp/', views.SendOrderOTPView.as_view(), name='send-order-otp'),
    path('verify-order-otp/', views.VerifyOrderOTPView.as_view(), name='verify-order-otp'),
    path('resend-order-otp/', views.ResendOrderOTPView.as_view(), name='resend-order-otp'),
    path('delivery-order-history/', views.DeliveryOrderHistoryView.as_view(), name='delivery-order-history'),
    
    # Pending Orders Service
    path('pending-orders/', views.PendingOrdersView.as_view(), name='pending-orders'),

    # Distance/Kilometer calculation
    path('delivery-partner-kilometer-calculation/', views.DeliveryPartnerKilometerCalculationView.as_view(), name='delivery-partner-km'),

    # Snap to Roads - Clean GPS route
    path('snap-to-roads/', views.SnapToRoadsView.as_view(), name='snap-to-roads'),

    # Debug
    path('debug/grocery-orders/', views.GroceryOrdersDebugView.as_view(), name='debug-grocery-orders'),
]  