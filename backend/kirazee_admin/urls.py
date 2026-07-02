from django.urls import path
from . import views
from . import business_contact_views
from .dashboard_views import AdminDashboardSummaryView
from .delivery_partners import BusinessDeliveryPartnersView
from .pulse_views import DashboardPulseView, DashboardHealthView
from .analytics_views import RevenueTrendView, CategoryMixView, BusinessOffersAndCouponsView, BusinessPerformanceMetricsView, BestSellingItemsView, FrequentUsersView
from .fleet_views import ActiveFleetView, FleetHeatmapView
from .export_views import OrderExportView, BusinessExportView, DeliveryFleetExportView
from .snapshot_views import SnapshotCalculationView, SnapshotScheduleView
from .business_details_views import BusinessDetailsView, BusinessAlertsView, BusinessAlertResolveView
from .business_management_views import BusinessDetailedView, BusinessMenuItemsView, BusinessOrdersView, BusinessCouponsView, BusinessOffersView, BusinessPeakHoursView, BusinessOrderStatusView
from .support_views import SupportDashboardView, SupportTicketsListView, SupportTicketDetailView
from .reason_templates_views import (
    get_review_templates,
    create_review_template,
    update_review_template,
    delete_review_template,
    bulk_create_review_templates,
)

urlpatterns = [
    # Dashboard Pulse (Performance Optimized)
    path('dashboard/latest/', DashboardPulseView.as_view(), name='admin_dashboard_pulse'),
    path('dashboard/health/', DashboardHealthView.as_view(), name='admin_dashboard_health'),
    
    # Dashboard Summary (Full Data)
    path('dashboard/summary/', AdminDashboardSummaryView.as_view(), name='admin_dashboard_summary'),
    
    # Snapshot Management (Super Admin Only)
    path('snapshot/calculate/', SnapshotCalculationView.as_view(), name='admin_snapshot_calculate'),
    path('snapshot/schedule/', SnapshotScheduleView.as_view(), name='admin_snapshot_schedule'),
    
    # Analytics & Reporting
    path('analytics/businesses/', views.AdminBusinessAnalyticsView.as_view(), name='admin_business_analytics'),
    path('analytics/revenue-trend/', RevenueTrendView.as_view(), name='admin_revenue_trend'),
    path('analytics/category-mix/', CategoryMixView.as_view(), name='admin_category_mix'),
    path('analytics/business-offers-coupons/', BusinessOffersAndCouponsView.as_view(), name='admin_business_offers_coupons'),
    path('analytics/business-performance/<str:business_id>/', BusinessPerformanceMetricsView.as_view(), name='admin_business_performance'),
    path('analytics/best-selling-items/<str:business_id>/', BestSellingItemsView.as_view(), name='admin_best_selling_items'),
    path('analytics/frequent-users/<str:business_id>/', FrequentUsersView.as_view(), name='admin_frequent_users'),
    
    # Delivery Fleet Tracking
    path('delivery/active-fleet/', ActiveFleetView.as_view(), name='admin_active_fleet'),
    path('delivery/heatmap/', FleetHeatmapView.as_view(), name='admin_fleet_heatmap'),
    
    # Export Functionality
    path('export/orders/', OrderExportView.as_view(), name='admin_export_orders'),
    path('export/businesses/', BusinessExportView.as_view(), name='admin_export_businesses'),
    path('export/delivery-fleet/', DeliveryFleetExportView.as_view(), name='admin_export_delivery_fleet'),
    
    # Business Management
    path('businesses/', views.AdminBusinessManagementView.as_view(), name='admin_businesses'),
    path('businesses/<str:business_id>/status/', views.AdminBusinessStatusView.as_view(), name='admin_business_status'),
    path('businesses/<str:business_id>/payment-status/', views.AdminBusinessPaymentStatusView.as_view(), name='admin_business_payment_status'),
    path('businesses/<str:business_id>/', views.AdminBusinessDeleteView.as_view(), name='admin_business_delete'),
    
    # Comprehensive Business Details (Swiggy-style)
    path('businesses/<str:business_id>/details/', BusinessDetailsView.as_view(), name='admin_business_details'),
    path('businesses/<str:business_id>/alerts/', BusinessAlertsView.as_view(), name='admin_business_alerts'),
    path('businesses/<str:business_id>/alerts/<int:alert_id>/resolve/', BusinessAlertResolveView.as_view(), name='admin_business_alert_resolve'),
    
    # Business Management - Detailed Tabbed View
    path('business-management/<str:business_id>/detailed/', BusinessDetailedView.as_view(), name='admin_business_detailed'),
    path('business-management/<str:business_id>/menu/', BusinessMenuItemsView.as_view(), name='admin_business_menu'),
    path('business-management/<str:business_id>/orders/', BusinessOrdersView.as_view(), name='admin_business_orders'),
    path('business-management/<str:business_id>/coupons/', BusinessCouponsView.as_view(), name='admin_business_coupons'),
    path('business-management/<str:business_id>/offers/', BusinessOffersView.as_view(), name='admin_business_offers'),
    path('business-management/<str:business_id>/peak-hours/', BusinessPeakHoursView.as_view(), name='admin_business_peak_hours'),
    path('business-management/<str:business_id>/order-status/', BusinessOrderStatusView.as_view(), name='admin_business_order_status'),
    
    # Order Management
    path('orders/', views.AdminOrderManagementView.as_view(), name='admin_orders'),
    path('orders/<int:order_id>/', views.AdminOrderDetailsView.as_view(), name='admin_order_details'),
    path('orders/<int:order_id>/status/', views.AdminOrderStatusView.as_view(), name='admin_order_status'),
    path('orders/<int:order_id>/assign-delivery/', views.AdminOrderAssignDeliveryView.as_view(), name='admin_assign_delivery'),
    
    # Delivery Provider Management
    path('delivery-fleet/', views.AdminDeliveryFleetManagementView.as_view(), name='admin_delivery_fleet'),
    path('delivery-fleet/<int:provider_id>/', views.AdminDeliveryFleetDetailView.as_view(), name='admin_delivery_fleet_detail'),
    path('delivery-providers/', views.AdminDeliveryProviderManagementView.as_view(), name='admin_delivery_providers'),
    path('delivery-providers/<int:provider_id>/', views.AdminDeliveryProviderDetailView.as_view(), name='admin_delivery_provider_detail'),

    # Delivery Partners per Business (create/update/delete)
    path('businesses/<str:business_id>/delivery-partners/', BusinessDeliveryPartnersView.as_view(), name='admin_business_delivery_partners_create'),
    path('businesses/<str:business_id>/delivery-partners/<int:partner_id>/', BusinessDeliveryPartnersView.as_view(), name='admin_business_delivery_partners_update_delete'),
    
    # Test endpoint
    path('test/', views.AdminTestView.as_view(), name='admin_test'),
    path('businesses-simple/', views.AdminBusinessSimpleView.as_view(), name='admin_businesses_simple'),
    
    # Contact Us
    path('contact-us/', views.ContactUsView.as_view(), name='contact_us'),
    path('contact-us/manage/', views.ContactUsManagementView.as_view(), name='contact_us_management'),
    path('contact-us/<int:contact_id>/reply/', views.ContactUsReplyView.as_view(), name='contact_us_reply'),
    
    # Business Contact Us - For contacting specific businesses
    path('business-contact-us/', business_contact_views.BusinessContactUsView.as_view(), name='business_contact_us'),
    path('business-contact-us/manage/', business_contact_views.BusinessContactUsManagementView.as_view(), name='business_contact_us_management'),
    path('business-contact-us/<int:contact_id>/reply/', business_contact_views.BusinessContactUsReplyView.as_view(), name='business_contact_us_reply'),

    # Review Reason Template Management
    path('review-templates/', get_review_templates, name='admin_review_templates_get'),
    path('review-templates/create/', create_review_template, name='admin_review_templates_create'),
    path('review-templates/<int:template_id>/', update_review_template, name='admin_review_templates_update'),
    path('review-templates/<int:template_id>/delete/', delete_review_template, name='admin_review_templates_delete'),
    path('review-templates/bulk/', bulk_create_review_templates, name='admin_review_templates_bulk_create'),

    # Support Dashboard (Isolated System)
    path('support/dashboard/', SupportDashboardView.as_view(), name='admin_support_dashboard'),
    path('support/tickets/', SupportTicketsListView.as_view(), name='admin_support_tickets_list'),
    path('support/tickets/<str:ticket_id>/', SupportTicketDetailView.as_view(), name='admin_support_ticket_detail'),

]
