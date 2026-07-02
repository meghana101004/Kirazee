# urls.py
from django.shortcuts import render
from django.urls import path
from django.conf import settings
from django.conf.urls.static import static
from .views import ( 
    fetchbusinessesTypes,
    fetchbusinessFeatures,
    CreateBusinessAPIView,
    update_business_details,
    owner_update_business_details,
    user_status,
    business_summary,
    business_hierarchy,
    toggle_business_status,
    CreateMenuItemsAPIView,
    MenuItemsManagementAPIView,
    MenuItemVariantManagementAPIView,
    addBOMItems, addProductItems,
    addProductVariant,
    fashion_product_variant_detail,
    groceries_product_variant_detail,
    BOMItemsManagementAPIView, 
    updateProductItems,
    menuDetailView, productDetailView, fashionDetailView, getItemDetails,
    parse_address_from_maps,
    search_grocery_skus,
    list_menu_items,
    list_grocery_products_owner,
    groceries_custom_designs_owner,
    groceries_custom_design_detail_owner,
    bulk_upload_menu_items,
    bulk_upload_grocery_products,
    get_countries_with_states,
    get_states_by_country,
    get_districts_by_state,
    get_taluks_by_district,
    get_pincodes_by_taluk,
    get_geographical_summary,
    search_geographical_data,
    ItemsViewBasedonBusinessID,
    manageCustomizationTemplates,
    list_customizable_items
)
from .categories import (
    list_universal_categories,
    list_universal_categories_tree,
    universal_category_detail,
    create_universal_category,
    update_universal_category,
    delete_universal_category,
    search_universal_category,
    add_category_mapping,
    update_category_mapping,
    delete_category_mapping,
    selected_categories_for_business,
    groceries_ensure_category,
    groceries_categories,
    groceries_category_detail,
)
from .coupons import (
    create_coupon,
    list_business_coupons,
    get_coupon_details,
    get_coupon_for_editing,
    update_coupon,
    toggle_coupon_status,
    delete_coupon,
    add_coupon_rule,
    update_coupon_rule,
    coupon_analytics,
    get_user_businesses,
)
from .delivery import (
    configure_delivery_charges,
    get_delivery_configuration,
    configure_points_system,
    get_points_configuration,
    configure_order_types,
    get_order_types,
    RBOPendingOrdersView,   
    order_online_history,
    RBOOrderDetailsView
)
from .delivery_charges_crud import (
    delete_delivery_configuration,
    list_all_delivery_configurations,
    update_delivery_configuration
)
from .kot import (
    assign_kot,
    list_kot_users,
    update_kot_user,
    delete_kot_user,
    kot_login,
)
from .onboarding import (
    get_user_progress,
    initialize_application,
    application_details,
    step1_save,
    step1_get,
    step2_upload,
    step2_get_documents,
    step2_complete,
    step3_save,
    step3_get_data,
    submit_application,
    get_application_status,
    admin_list_pending,
    admin_list_all,
    admin_list_approved,
    admin_list_rejected,
    admin_list_in_progress,
    admin_application_details,
    admin_review_application,
    autosave,
    heartbeat,
    onboarding_config_business_types,
    validate_gstin,
    validate_financial_details,
)

from .payment import payment_gateway, save_payment_data, process_refund, business_payment_gateway, save_business_payment_data, payment_success, business_payment_success

from .Counter_POS import (
    create_counter_order,
    create_counter_order_with_invoice,
    get_counter_orders,
    get_counter_order_detail,
    update_counter_order,
    cancel_counter_order,
    get_counter_logs,
    create_manual_log,
    get_payment_collections,
    get_daily_collection_summary,
    get_collection_history,
    apply_payment_reduction,
    get_pos_grocery_categories,
)

from .offers import (
    create_promotion,
    list_business_offers,
    get_promotion_details,
    update_promotion,
    toggle_promotion_status,
    set_promotion_categories,
    add_promotion_media,
    delete_promotion_media,
    offers_feed,
    click_promotion,
    approve_promotion_admin,
)
from .dashboard import (
    dashboard_today_snapshot,
    dashboard_daily_sales,
    dashboard_inventory_alerts,
    dashboard_recent_orders,
    dashboard_health,
)

urlpatterns = [
    #fetch to create business
    path('fetch-types/', fetchbusinessesTypes, name='fetch_businesses'), #featches the business Types
    path('business-features/', fetchbusinessFeatures, name='fetch_business_Features'), #fetches the business features

    # Business management endpoints
    path('create', CreateBusinessAPIView, name='CreateBusinessAPIView'), #create/retrieve/update the business in 3 sections
    path('summary', business_summary, name='business_summary'),
    path('user-status/', user_status, name='business_user_status'),
    path('hierarchy/', business_hierarchy, name='business_hierarchy'),
    path('api/business/<str:business_id>/toggle-status/', toggle_business_status, name='toggle_business_status'),
    path('parse-address/', parse_address_from_maps, name='parse_address'),
    path('payment-gateway/', payment_gateway, name='payment_gateway'), #calls the paymnet Gatway html page to create a busienss
    path('business-payment-gateway/', business_payment_gateway, name='business_payment_gateway'), #business setup payment gateway - exact replica of order payment
    path('save-payment-data/', save_payment_data, name='save_payment_data'), #save payment details while creating the business
    path('save-business-payment-data/', save_business_payment_data, name='save_business_payment_data'), #save business setup payment data
    path('payment/success/', payment_success, name='payment_success'), #general payment success handler
    path('business/payment/success/', business_payment_success, name='business_payment_success'), #dedicated business setup payment success
    path('test-payment-simulation/', lambda request: render(request, 'test_payment_simulation.html'), name='test_payment_simulation'), #test payment simulation
    path('process-refund/', process_refund, name='process_refund'), # currently no need refunding the payment if they don't want

    #display the busienss details for the user businesses
    path('user-businesses/', get_user_businesses, name='get_user_businesses'),
    path('update', update_business_details, name='update_business_details'), # unified update after setup
    path('owner/update-details', owner_update_business_details, name='owner_update_business_details'),
    
    #create menu items
    path('add-menu-items', CreateMenuItemsAPIView, name='CreateMenuItemsAPIView'),  #add menu items here by busienss owners
    path('menu-items-management/<int:item_id>/', MenuItemsManagementAPIView, name='MenuItemsManagementAPIView'), # update the menu items here
    path('menu-item-variants/', MenuItemVariantManagementAPIView, name='MenuItemVariantManagementAPIView'), # manage menu item variants (POST for create)
    path('menu-item-variants/<int:variant_id>/', MenuItemVariantManagementAPIView, name='MenuItemVariantManagementAPIViewDetail'), # manage menu item variants (GET/PATCH/DELETE)
    path('menu-items', list_menu_items, name='list_menu_items'),
    path('bulk-add-menu-items', bulk_upload_menu_items, name='bulk_upload_menu_items'),
    path('add-bom-items', addBOMItems, name='addBOMItems'), # add ingredients here for your menu items
    path('bom-items-management/', BOMItemsManagementAPIView, name='BOMItemsManagementAPIView'), #Manage your ingredients here 
    path('items', ItemsViewBasedonBusinessID, name='fetch_items'), 

    #create product items
    path('add-product-items', addProductItems, name='addProductItems'), # add product items for your grocery business
    path('product-variants-management/', addProductVariant, name='addProductVariant'),
    path('fashion/product-variants/<int:variant_id>/', fashion_product_variant_detail, name='fashion_product_variant_detail'),
    path('product-items-management/<int:item_id>/', updateProductItems, name='updateProductItems'), #update the grocery items that owner want to sell
    path('groceries/product-items', list_grocery_products_owner, name='list_grocery_products_owner'),
    path('groceries/product-variants/<int:variant_id>/', groceries_product_variant_detail, name='groceries_product_variant_detail'),
    path('groceries/custom-designs', groceries_custom_designs_owner, name='groceries_custom_designs_owner'),
    path('groceries/custom-designs/<int:design_id>/', groceries_custom_design_detail_owner, name='groceries_custom_design_detail_owner'),
    path('groceries/sku-search', search_grocery_skus, name='search_grocery_skus'),
    path('groceries/bulk-product-items', bulk_upload_grocery_products, name='bulk_upload_grocery_products'),
    path('customization-templates/', manageCustomizationTemplates, name='manage_customization_templates'),
    path('customization-templates/<int:template_id>/', manageCustomizationTemplates, name='manage_customization_template_detail'),
    path('customizable-items/', list_customizable_items, name='list_customizable_items'),
    
    #coupons
    path('coupons/create/', create_coupon, name='create_coupon'),
    path('coupons/', list_business_coupons, name='list_business_coupons_all'),
    path('coupons/business/<str:business_id>/', list_business_coupons, name='list_business_coupons'),
    path('coupons/<str:coupon_id>/', get_coupon_details, name='get_coupon_details'),
    path('coupons/<str:coupon_id>/edit/', get_coupon_for_editing, name='get_coupon_for_editing'),
    path('coupons/<str:coupon_id>/update/', update_coupon, name='update_coupon'),
    path('coupons/<str:coupon_id>/toggle/', toggle_coupon_status, name='toggle_coupon_status'),
    path('coupons/<str:coupon_id>/delete/', delete_coupon, name='delete_coupon'),
    path('coupons/<str:coupon_id>/add-rule/', add_coupon_rule, name='add_coupon_rule'),
    path('coupons/<str:coupon_id>/rules/<str:rule_id>/update/', update_coupon_rule, name='update_coupon_rule'),
    path('coupons/analytics/', coupon_analytics, name='coupon_analytics'),
    
    # promotional offers
    path('offers/create/', create_promotion, name='create_promotion'),
    path('offers/', list_business_offers, name='list_business_offers_all'),
    path('offers/business/<str:business_id>/', list_business_offers, name='list_business_offers'),
    path('offers/<int:promo_id>/', get_promotion_details, name='get_promotion_details'),
    path('offers/<int:promo_id>/update/', update_promotion, name='update_promotion'),
    path('offers/<int:promo_id>/toggle/', toggle_promotion_status, name='toggle_promotion_status'),
    path('offers/<int:promo_id>/categories/', set_promotion_categories, name='set_promotion_categories'),
    path('offers/<int:promo_id>/media/add/', add_promotion_media, name='add_promotion_media'),
    path('offers/<int:promo_id>/media/<int:media_id>/delete/', delete_promotion_media, name='delete_promotion_media'),
    path('offers/feed/', offers_feed, name='offers_feed'),
    path('offers/<int:promo_id>/click/', click_promotion, name='click_promotion'),
    path('offers/<int:promo_id>/approve/', approve_promotion_admin, name='approve_promotion_admin'),
    
    # Dashboard
    path('api/v1/businesses/<str:business_id>/dashboard/today/', dashboard_today_snapshot, name='dashboard_today_snapshot'),
    path('api/v1/businesses/<str:business_id>/dashboard/daily-sales/', dashboard_daily_sales, name='dashboard_daily_sales'),
    path('api/v1/businesses/<str:business_id>/dashboard/inventory-alerts/', dashboard_inventory_alerts, name='dashboard_inventory_alerts'),
    path('api/v1/businesses/<str:business_id>/dashboard/recent-orders/', dashboard_recent_orders, name='dashboard_recent_orders'),
    path('api/v1/businesses/<str:business_id>/dashboard/health/', dashboard_health, name='dashboard_health'),
    
    #delivery
    path('delivery/configure/', configure_delivery_charges, name='configure_delivery_charges'),
    path('delivery/configuration/', get_delivery_configuration, name='get_delivery_configuration'),
    path('delivery/configurations/', list_all_delivery_configurations, name='list_all_delivery_configurations'),
    path('delivery/configuration/<int:delivery_id>/', update_delivery_configuration, name='update_delivery_configuration'),
    path('delivery/configuration/delete/', delete_delivery_configuration, name='delete_delivery_configuration'),
    path('points/configure/', configure_points_system, name='configure_points_system'),
    path('points/configuration/', get_points_configuration, name='get_points_configuration'),

    # order type configuration per business
    path('order-types/configure/', configure_order_types, name='configure_order_types'),
    path('order-types/', get_order_types, name='get_order_types'),

    # KOT (Kitchen Order Display) management
    path('kot/assign/', assign_kot, name='assign_kot'),
    path('kot/login/', kot_login, name='kot_login'),
    path('kot/users/', list_kot_users, name='list_kot_users'),
    path('kot/users/<int:id>/', update_kot_user, name='update_kot_user'),
    path('kot/users/<int:id>/delete/', delete_kot_user, name='delete_kot_user'),
    
    #display pending orders of a consumer 
    path('pending-orders/', RBOPendingOrdersView.as_view(), name='pending_orders'),
    path('orders/<int:order_id>/', RBOOrderDetailsView.as_view(), name='order-details'),
    
    #Order Management
    path('order-online-history/', order_online_history, name='order_online_history'),
    
    #item details
    path('menu-details/', menuDetailView, name='menuDetailView'),
    path('product-details/', productDetailView, name='productDetailView'),
    path('fashion-details/', fashionDetailView, name='fashionDetailView'),
    path('get-item-details/', getItemDetails, name='getItemDetails'),

    # Onboarding (v1) - final URL will be /kirazee/business/onboarding/...
    path('onboarding/progress/<int:user_id>/', get_user_progress, name='onboarding_get_user_progress'),
    path('onboarding/application/<str:application_id>/details', application_details, name='onboarding_application_details'),
    path('onboarding/initialize', initialize_application, name='onboarding_initialize'),
    path('onboarding/step1/save', step1_save, name='onboarding_step1_save'),
    path('onboarding/step1/<str:application_id>/', step1_get, name='onboarding_step1_get'),
    path('onboarding/step2/upload', step2_upload, name='onboarding_step2_upload'),
    path('onboarding/step2/<str:application_id>/documents', step2_get_documents, name='onboarding_step2_docs'),
    path('onboarding/step2/complete', step2_complete, name='onboarding_step2_complete'),
    path('onboarding/step3/save', step3_save, name='onboarding_step3_save'),
    path('onboarding/step3/<str:application_id>/data', step3_get_data, name='onboarding_step3_data'),
    path('onboarding/validate-gstin', validate_gstin, name='onboarding_validate_gstin'),
    path('onboarding/validate-financial-details', validate_financial_details, name='onboarding_validate_financial'),
    path('onboarding/submit', submit_application, name='onboarding_submit'),
    path('onboarding/status/<str:application_id>/', get_application_status, name='onboarding_status'),
    path('onboarding/auto-save', autosave, name='onboarding_autosave'),
    path('onboarding/heartbeat', heartbeat, name='onboarding_heartbeat'),
    path('onboarding/config/business-types', onboarding_config_business_types, name='onboarding_business_types'),

    # Admin review endpoints
    path('onboarding/admin/business-applications/pending', admin_list_pending, name='onboarding_admin_pending'),
    path('onboarding/admin/business-applications/all', admin_list_all, name='onboarding_admin_all'),
    path('onboarding/admin/business-applications/approved', admin_list_approved, name='onboarding_admin_approved'),
    path('onboarding/admin/business-applications/rejected', admin_list_rejected, name='onboarding_admin_rejected'),
    path('onboarding/in_progress/business-applications/pending', admin_list_in_progress, name='onboarding_admin_in_progress'),
    path('onboarding/admin/business-applications/<str:application_id>/details', admin_application_details, name='onboarding_admin_details'),
    path('onboarding/admin/business-applications/<str:application_id>/review', admin_review_application, name='onboarding_admin_review'),
    
    # universal category selection & mapping
    path('categories/universal/', list_universal_categories, name='list_universal_categories'),
    path('categories/universal/tree/', list_universal_categories_tree, name='list_universal_categories_tree'),
    path('categories/universal/create/', create_universal_category, name='create_universal_category'),
    path('categories/universal/<int:category_id>/', universal_category_detail, name='universal_category_detail'),
    path('categories/universal/<int:category_id>/update/', update_universal_category, name='update_universal_category'),
    path('categories/universal/<int:category_id>/delete/', delete_universal_category, name='delete_universal_category'),
    path('categories/universal/search/', search_universal_category, name='search_universal_category'),
    path('categories/mapping/', add_category_mapping, name='add_category_mapping'),
    path('categories/mapping/<int:mapping_id>/', update_category_mapping, name='update_category_mapping'),
    path('categories/mapping/<int:mapping_id>/delete/', delete_category_mapping, name='delete_category_mapping'),
    path('categories/selected/', selected_categories_for_business, name='selected_categories_for_business'),
    path('groceries/categories/ensure', groceries_ensure_category, name='groceries_ensure_category'),
    path('groceries/categories/', groceries_categories, name='groceries_categories'),
    path('groceries/categories/<int:category_id>/', groceries_category_detail, name='groceries_category_detail'),


     # Counter POS - Order Management
    path('counter/orders/create/', create_counter_order, name='create_counter_order'),
    path('counter/orders/create-with-invoice/', create_counter_order_with_invoice, name='create_counter_order_with_invoice'),
    path('counter/orders/<str:business_id>/', get_counter_orders, name='get_counter_orders'),
    path('counter/orders/<str:business_id>/<int:order_id>/', get_counter_order_detail, name='get_counter_order_detail'),
    path('counter/orders/<str:business_id>/<int:order_id>/update/', update_counter_order, name='update_counter_order'),
    path('counter/orders/<str:business_id>/<int:order_id>/cancel/', cancel_counter_order, name='cancel_counter_order'),
    path('counter/orders/<str:business_id>/<int:order_id>/apply-payment/', apply_payment_reduction, name='apply_payment_reduction'),
    
    # Counter POS - Collections & Reports
    path('counter/collections/<str:business_id>/', get_payment_collections, name='get_payment_collections'),
    path('counter/collections/<str:business_id>/daily/', get_daily_collection_summary, name='get_daily_collection_summary'),
    path('counter/collections/<str:business_id>/history/', get_collection_history, name='get_collection_history'),
    
    # Counter POS - Logging
    path('counter/logs/<str:business_id>/', get_counter_logs, name='get_counter_logs'),
    path('counter/logs/create/', create_manual_log, name='create_manual_log'),
    # Counter POS - Grocery Categories for dropdowns
    path('counter/categories/<str:business_id>/', get_pos_grocery_categories, name='get_pos_grocery_categories'),
    
    # Geographical Data APIs
    path('geo/countries-states/', get_countries_with_states, name='get_countries_with_states'),
    path('geo/countries/<str:country>/states/', get_states_by_country, name='get_states_by_country'),
    path('geo/countries/<str:country>/states/<str:state>/districts/', get_districts_by_state, name='get_districts_by_state'),
    path('geo/countries/<str:country>/states/<str:state>/districts/<str:district>/taluks/', get_taluks_by_district, name='get_taluks_by_district'),
    path('geo/countries/<str:country>/states/<str:state>/districts/<str:district>/taluks/<str:taluk>/pincodes/', get_pincodes_by_taluk, name='get_pincodes_by_taluk'),
    path('geo/summary/', get_geographical_summary, name='get_geographical_summary'),
    path('geo/search/', search_geographical_data, name='search_geographical_data'),
    
] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)