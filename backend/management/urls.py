from django.urls import path
from . import Purchases_views
from . import sales
from . import report
from . import Staff_views
from . import tax_invoive
from . import payment_detail_reports
from . import financial_breakdown
from . import business_settings_views
from . import feature_payment_callback
from . import purchase_requisition_views
from .feature_payment_callback import FeaturePaymentCallbackView
from .Staff_views import (
    StaffLoginView,
    StaffOTPSendView,
    StaffOTPVerifyView,
    StaffLogoutView,
    StaffNavigationView,
    DefaultNavbarView,
    StaffChangePasswordView,
    StaffLoginLogsView,
    StaffNavAssignmentView,
    AllRoleNavItemsView,
    BusinessFeaturePurchasesView,
)
from .business_settings_views import BusinessSettingsView, FeaturePaymentRedirectView
from .feature_payment_callback import FeaturePaymentCallbackView

urlpatterns = [
    # Purchase endpoints
    path('purchases/create/', Purchases_views.create_purchase, name='create_purchase'),
    path('purchases/', Purchases_views.get_purchases, name='get_purchases'),
    path('purchases/business/', Purchases_views.get_purchases_by_business, name='get_purchases_by_business'),
    path('purchases/<int:purchase_id>/', Purchases_views.get_purchase_detail, name='get_purchase_detail'),
    path('purchases/<int:purchase_id>/status/', Purchases_views.update_purchase_status, name='update_purchase_status'),
    path('purchases/<int:purchase_id>/update/', Purchases_views.update_purchase, name='update_purchase'),
    path('purchases/<int:purchase_id>/delete/', Purchases_views.delete_purchase, name='delete_purchase'),
    
    # Staff endpoints
    path('staff/', Staff_views.staff_list_create_view, name='staff_list_create'),  # GET, POST
    path('staff/<int:staff_id>/', Staff_views.get_staff_detail, name='get_staff_detail'),  # GET
    path('staff/<int:staff_id>/update/', Staff_views.update_staff, name='update_staff'),  # PUT
    path('staff/<int:staff_id>/delete/', Staff_views.delete_staff, name='delete_staff'),  # DELETE
    path('staff/<int:staff_id>/salary/', Staff_views.get_staff_salary, name='get_staff_salary'),  # GET (individual staff)
    path('staff/<int:staff_id>/attendance/', Staff_views.get_staff_attendance, name='get_staff_attendance'),  # GET (individual staff attendance)
    path('staff/<int:staff_id>/pay-salary/', Staff_views.pay_staff_salary, name='pay_staff_salary'),  # POST (pay salary to staff)
    path('staff/<int:staff_id>/salary-status/', Staff_views.get_staff_salary_payment_status, name='get_staff_salary_payment_status'),  # GET (salary payment status)
    path('staff/salary/', Staff_views.get_all_staff_salaries, name='get_all_staff_salaries'),  # GET (all staff)
    path('staff/debug-salary/', Staff_views.debug_salary_records, name='debug_salary_records'),  # GET (debug)
    path('staff/test-payment/', Staff_views.test_payment_creation, name='test_payment_creation'),  # GET (test)
    path('attendance/', Staff_views.mark_attendance, name='mark_attendance'),  # POST
    # Staff navigation assignment endpoints
    path('staff/<int:staff_id>/nav-items/', StaffNavAssignmentView.as_view(), name='staff_nav_assignment'),
    
    # Expense endpoints
    path('expenses/', Purchases_views.get_expenses_by_business, name='get_expenses_by_business'),
    path('expenses/create/', Purchases_views.create_expense, name='create_expense'),
    path('expenses/<int:expense_id>/update/', Purchases_views.update_expense, name='update_expense'),
    path('expenses/<int:expense_id>/delete/', Purchases_views.delete_expense, name='delete_expense'),
    
    # Supplier endpoints
    path('suppliers/<str:business_id>/', Purchases_views.get_suppliers, name='get_suppliers'),  # GET
    path('suppliers/<str:business_id>/create/', Purchases_views.create_supplier, name='create_supplier'),  # POST
    path('suppliers/<str:business_id>/<int:supplier_id>/', Purchases_views.get_supplier_by_id, name='get_supplier_by_id'),  # GET
    path('suppliers/<str:business_id>/<int:supplier_id>/update/', Purchases_views.update_supplier, name='update_supplier'),  # PUT
    path('suppliers/<str:business_id>/<int:supplier_id>/delete/', Purchases_views.delete_supplier, name='delete_supplier'),  # DELETE
    
    # Inventory endpoints
    path('inventory/', Purchases_views.get_inventory_by_business, name='get_inventory_by_business'),
    path('inventory/<int:inventory_id>/update/', Purchases_views.update_inventory_item, name='update_inventory_item'),
    path('inventory/<int:inventory_id>/delete/', Purchases_views.delete_inventory_item, name='delete_inventory_item'),

    # Purchase Requisition endpoints
    path('purchase-requisitions/', purchase_requisition_views.create_purchase_requisition, name='create_purchase_requisition'),
    path('purchase-requisitions/list/', purchase_requisition_views.get_purchase_requisitions, name='get_purchase_requisitions'),
    path('purchase-requisitions/<int:purchase_req_id>/', purchase_requisition_views.get_purchase_requisition_detail, name='get_purchase_requisition_detail'),
    path('purchase-requisitions/<int:purchase_req_id>/approve/', purchase_requisition_views.approve_purchase_requisition, name='approve_purchase_requisition'),
    path('purchase-requisitions/<int:purchase_req_id>/reject/', purchase_requisition_views.reject_purchase_requisition, name='reject_purchase_requisition'),
    path('purchase-requisitions/<int:requisition_id>/logs/', purchase_requisition_views.get_requisition_logs, name='get_requisition_logs'),
    path('purchase-requisitions/logs/all/', purchase_requisition_views.get_all_requisition_logs, name='get_all_requisition_logs'),
    path('purchase-requisitions/manager/', purchase_requisition_views.manager_approval_dashboard, name='manager_approval_dashboard'),
    path('purchase-requisitions/submit/', purchase_requisition_views.submit_requisitions_to_manager, name='submit_requisitions_to_manager'),
    path('purchase-requisitions/<int:purchase_req_id>/delete/', purchase_requisition_views.delete_draft_requisition, name='delete_draft_requisition'),
    
    # Log endpoints
    path('logs/purchases/', Purchases_views.get_purchase_logs, name='get_purchase_logs'),
    path('logs/inventory/', Purchases_views.get_inventory_logs, name='get_inventory_logs'),
    path('logs/expenses/', Purchases_views.get_expenses_logs, name='get_expenses_logs'),
    
    # Product search endpoints
    path('products/search/', Purchases_views.search_product_by_sku, name='search_products'),
    path('products/search-by-sku/', Purchases_views.search_product_by_sku, name='search_product_by_sku'),  # Keep for backward compatibility

    # Sales endpoints
    path('sales/summary/', sales.BusinessSalesView.as_view(), name='sales_summary'),
    
    # Financial Breakdown endpoints
    path('financial/breakdown/', financial_breakdown.FinancialBreakdownView.as_view(), name='financial_breakdown'),
    
    # Payment Detail Reports endpoints
    path('reports/payment-details/', payment_detail_reports.PaymentDetailReportView.as_view(), name='payment_detail_report'),
    
    # Report endpoints
    path('reports/profit-loss/', report.ProfitLossReportView.as_view(), name='profit_loss_report'),
    path('reports/performance/', report.BusinessPerformanceReportView.as_view(), name='business_performance_report'),
    path('reports/dashboard/', report.ComprehensiveDashboardReportView.as_view(), name='comprehensive_dashboard_report'),
    
    # Tax invoice endpoints
    path('tax-invoices/<str:business_id>/', tax_invoive.tax_invoices_list_create, name='tax_invoices_list_create'),
    path('tax-invoices/<str:business_id>/<str:invoice_number>/', tax_invoive.tax_invoice_detail, name='tax_invoice_detail'),
    
    # Staff Authentication endpoints
    path('staff/login/', StaffLoginView.as_view(), name='staff_login'),
    path('staff/send-otp/', StaffOTPSendView.as_view(), name='staff_send_otp'),
    path('staff/verify-otp/', StaffOTPVerifyView.as_view(), name='staff_verify_otp'),
    path('staff/logout/', StaffLogoutView.as_view(), name='staff_logout'),
    path('staff/navigation/', StaffNavigationView.as_view(), name='staff_navigation'),
    path('default-navbar/', DefaultNavbarView.as_view(), name='default_navbar'),
    path('staff/change-password/', StaffChangePasswordView.as_view(), name='staff_change_password'),
    path('staff/login-logs/', StaffLoginLogsView.as_view(), name='staff_login_logs'),
    path('staff/nav-items/all/', AllRoleNavItemsView.as_view(), name='all_role_nav_items'),
    
    # Feature purchase endpoints
    path('features/purchases/', BusinessFeaturePurchasesView.as_view(), name='business_feature_purchases'),
    path('features/payment-callback/', FeaturePaymentCallbackView.as_view(), name='feature_payment_callback'),
    
    # Business Settings endpoints
    path('business-settings/', BusinessSettingsView.as_view(), name='business_settings'),
    path('business-settings/payment-redirect/', FeaturePaymentRedirectView.as_view(), name='feature_payment_redirect'),
]