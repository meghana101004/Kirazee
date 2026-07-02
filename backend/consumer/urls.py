from django.urls import path
from django.conf import settings
from django.conf.urls.static import static
from .views import (
    business, nearby_businesses,
     AddToCartViewRES, AddToCartViewGROCERY, search, item_detail, most_ordered_items, business_search,
)
from .combine import (
    ItemsViewBasedonBusinessID, AddToCartViewBasedonBusinessID,
    get_cart_items, update_cart_quantity
)
from .whatsapp_orders_create import create_whatsapp_order, search_whatsapp_items, get_user_by_mobile
from .orders import (
    create_order, update_order_status, get_order_details, list_user_orders, get_order_analytics, re_order,
    cart_summary_preview, order_timeline, get_order_status_logs, list_order_status_logs
)
from .reviews import (
    add_reviews, display_reviews, business_reviews, order_reviews, item_review
)
from .wallet import (
    get_wallet_balance, get_wallet_transactions, spend_wallet_points, list_available_coupons,
    validate_coupon, add_wallet_points
)
from .user_tags import (
    add_user_tag, get_user_tags, remove_user_tag, map_private_coupon, bulk_add_user_tags
)
from .user_tags_extended import (
    get_domain_tag_mapping, add_domain_tag_mapping, update_domain_tag_mapping, deactivate_domain_tag_mapping, get_tag_analytics, get_user_tag_summary, get_targeting_options
)
from .delivery import (
    calculate_delivery_charges, get_delivery_zones, create_delivery_configuration,
    check_delivery_availability, get_delivery_time_estimate, get_delivery_partner_to_business_estimate, get_delivery_partner_current_orders
)
from .payment import (
    payment_page, initiate_payment, payment_callback, payment_webhook, 
    verify_payment_manual, payment_success, payment_failure, payment_success_page, payment_failure_page,
    handle_icici_payment_advice_web, handle_icici_payment_advice,
    mark_offline_payment_collected, finalize_payment_success
)
from .orders import (
    get_order_details, list_user_orders, update_order_status,
)
from .whatsapp_orders_create import (
    create_whatsapp_order, search_whatsapp_items, get_user_by_mobile,
)
from .feedback import BusinessFeedbackView, feedback, feedback_form_page, wishlist_operations, business_feedback_combined
from .products_details import product_details
from .refund import (
    initiate_order_refund,
    get_refund_status,
    list_order_refunds,
)

from .category_services import (
    fetch_categories, menu_items_by_category, product_items_by_category, popular_items, item_designs,
    new_arrivals, featured_products, on_sale_items
)
from .consumer_report import reports_daily, reports_weekly, reports_monthly

urlpatterns = [
    #-----------combined global code-----------
    
    #Display menu items based on business id
    path('items', ItemsViewBasedonBusinessID, name='fetch_items'), 
    
    #cart management globally based on business id
    path('add-to-cart', AddToCartViewBasedonBusinessID, name='add_to_cart_universal'), #universal add to cart with service layer
    path('viewcart', get_cart_items, name='view_cart'), #view the cart items
    path('update-cart-quantity', update_cart_quantity, name='update_cart_quantity'), #update the cart quantity
    path('cart/summary/', cart_summary_preview, name='cart_summary_preview'),
    
    #-----------New Category Services-----------
    # Category management
    path('fetch-categories', fetch_categories, name='fetch_categories'), #fetch unique categories for a business based on business type
    path('menu-items', menu_items_by_category, name='fetch_menu_items'), #fetch menu items by category
    path('product-items', product_items_by_category, name='fetch_product_items'), #fetch product items by category
    path('item-designs/', item_designs, name='item_designs'), # list customizable designs for a grocery product
    path('popular-items', popular_items, name='popular_items'), #fetch top 10 most popular items based on order count
    path('new-arrivals', new_arrivals, name='new_arrivals'),
    path('featured-products', featured_products, name='featured_products'),
    path('on-sale', on_sale_items, name='on_sale_items'),
    path('most-ordered-items/', most_ordered_items, name='most_ordered_items'), # top most ordered items by user (optionally by business)
    
    #-----------Item Detail-----------
    path('item-detail/', item_detail, name='item_detail'), # get item details + order stats for menu/grocery
    path('business-search/', business_search, name='business_search'), # search businesses by business name and items
    path('product-details/', product_details, name='product_details'), # unified details by item_id/product_id/variant_id
    
    #-----------Basic Code-----------
    # Business and Items Individually
    path('business/', business, name='fetch_businesses'), #fetch the list of businesses
    path('nearby-businesses/', nearby_businesses, name='nearby-businesses'), #fetch the list of nearby businesses
    path('search/', search, name='comprehensive_search'), #comprehensive search across businesses, menu items, and product items
    
    # Cart Management Individually
    path('res/add-to-cart', AddToCartViewRES, name='add_to_cart_res'), #add items to the cart
    path('grocery/add-to-cart', AddToCartViewGROCERY, name='add_to_cart_grocery'), #add grocery items to the cart

    # Spend walllet points or coupons before placing the order
    path('coupons/validate/', validate_coupon, name='validate_coupon'), #validate the coupon code for specific order context
    path('wallet/spend/', spend_wallet_points, name='spend_wallet_points'), # spend some points while ordering the items
    
    #create order here with or without coupons and wallet points
    path('orders/create/', create_order, name='create_order'), 
    path('orders/whatsapp/<str:business_id>/create/', create_whatsapp_order, name='create_whatsapp_order'),
    path('orders/whatsapp/<str:business_id>/items/', search_whatsapp_items, name='search_whatsapp_items'),
    path('users/by-mobile/', get_user_by_mobile, name='get_user_by_mobile'),

    # Payment Gateway
    path('payment/', payment_page, name='payment_page'), #html page
    path('payment/initiate/', initiate_payment, name='initiate_payment'), # intiate the payment and gathers the keys from the business db
    path('payment/callback/', payment_callback, name='payment_callback'),
    path('payment/webhook/', payment_webhook, name='payment_webhook'),
    path('payment/verify/', verify_payment_manual, name='verify_payment_manual'),
    
    # ICICI payment advice handlers
    path('payment/icici-advice-web/', handle_icici_payment_advice_web, name='handle_icici_payment_advice_web'),
    path('payment/success/', payment_success, name='payment_success'), # it is calling the payment sucess response
    path('payment/success-page/', payment_success_page, name='payment_success_page'), # display success page
    path('payment/failure-page/', payment_failure_page, name='payment_failure_page'), # display failure page
    path('payment/failure/', payment_failure, name='payment_failure'), # it is calling the payment failure response
    path('payment/offline/mark/', mark_offline_payment_collected, name='mark_offline_payment_collected'),

    # order management 00
    path('orders/<int:order_id>/status/', update_order_status, name='update_order_status'), #change the status of an order
    path('orders/user/<int:user_id>/', list_user_orders, name='list_user_orders'), #display the list of orders like history
    path('orders/<int:order_id>/', get_order_details, name='get_order_details'), # display the detail view of each order
    path('orders/analytics/', get_order_analytics, name='get_order_analytics'), #dispaly the order analytics of each user order
    path('orders/re-order', re_order, name='re_order'), # re-order groceries items to cart
    path('order-timeline/', order_timeline, name='order_timeline'), # get order timeline with progress line
    path('orders/<int:order_id>/status-logs/', get_order_status_logs, name='get_order_status_logs'),
    path('order-status-logs/', list_order_status_logs, name='list_order_status_logs'),

    # Refund Management
    path('refund/initiate/', initiate_order_refund, name='initiate_order_refund'),
    path('refund/status/', get_refund_status, name='get_refund_status'),
    path('refund/list/', list_order_refunds, name='list_order_refunds'),

    # Wallet Management
    path('wallet/add/', add_wallet_points, name='add_wallet_points'), # add some points to the wallet
    path('wallet/<int:user_id>/', get_wallet_balance, name='get_wallet_balance'), #check the balance of your wallet points
    path('wallet/<int:user_id>/transactions/', get_wallet_transactions, name='get_wallet_transactions'), #get your transaction history of wallet points
    
    # Coupon Management
    path('coupons/available/', list_available_coupons, name='list_available_coupons'), #display the list of available coupons
    path('coupons/user/', list_available_coupons, name='list_available_coupons_user'), #display the list of available coupons by user
    
    # User Tags Management
    path('user-tags/add/', add_user_tag, name='add_user_tag'), #add tag to user
    path('user-tags/<int:user_id>/', get_user_tags, name='get_user_tags'), #get user tags
    path('user-tags/<int:user_id>/<str:tag>/', remove_user_tag, name='remove_user_tag'), #remove user tag
    path('user-tags/bulk-add/', bulk_add_user_tags, name='bulk_add_user_tags'), #bulk add tags
    path('user-tags/domain-mapping/', get_domain_tag_mapping, name='get_domain_tag_mapping'), #get domain mapping
    path('user-tags/domain-mapping/add/', add_domain_tag_mapping, name='add_domain_tag_mapping'), #add domain mapping
    path('user-tags/domain-mapping/update/', update_domain_tag_mapping, name='update_domain_tag_mapping'), #update domain mapping
    path('user-tags/domain-mapping/deactivate/', deactivate_domain_tag_mapping, name='deactivate_domain_tag_mapping'), #deactivate domain mapping
    path('user-tags/analytics/', get_tag_analytics, name='get_tag_analytics'), #tag analytics
    path('user-tags/summary/<int:user_id>/', get_user_tag_summary, name='get_user_tag_summary'), #user tag summary
    path('user-tags/targeting-options/', get_targeting_options, name='get_targeting_options'), #targeting options for coupon creation
    path('coupons/map-private/', map_private_coupon, name='map_private_coupon'), #map private coupon to user
    
    # Reviews and Ratings Management
    path('add-reviews', add_reviews, name='add_reviews'), # submit a review and rating for an order/product
    path('item-reviews', display_reviews, name='display_reviews'), # fetch all reviews for a specific item
    path('item-review', item_review, name='item_review'), # get/update/delete current user's review for a specific item
    path('order-reviews', order_reviews, name='order_reviews'), # fetch all reviews for items in a specific order
    path('reviews', business_reviews, name='business_reviews'), # get average rating for all items from a business

    # Feedback (1-5 ratings + emoji comments)
    path('feedback/', feedback, name='feedback'),
    path('business-feedback/', BusinessFeedbackView.as_view(), name='business_feedback'),
    path('business-feedback/combined/', business_feedback_combined, name='business_feedback_combined'),
    path('wishlist/', wishlist_operations, name='wishlist_operations'),

    # Delivery Management
    path('delivery/calculate/', calculate_delivery_charges, name='calculate_delivery_charges'),
    path('delivery/zones/<int:business_id>/', get_delivery_zones, name='get_delivery_zones'),
    path('delivery/availability/', check_delivery_availability, name='check_delivery_availability'),
    path('delivery/estimate/', get_delivery_time_estimate, name='get_delivery_time_estimate'),
    path('delivery/partner-to-business-estimate/', get_delivery_partner_to_business_estimate, name='get_delivery_partner_to_business_estimate'),
    path('delivery/current-orders/', get_delivery_partner_current_orders, name='get_delivery_partner_current_orders'),

    # Admin level creation
    path('delivery/config/', create_delivery_configuration, name='create_delivery_configuration'),
    
    # Feedback form page
    path('feedback-form/', feedback_form_page, name='feedback_form_page'),

    # consumer reports
    path('reports/daily/', reports_daily, name='reports_daily_alias'),
    path('reports/weekly/', reports_weekly, name='reports_weekly_alias'),
    path('reports/monthly/', reports_monthly, name='reports_monthly_alias'),

]+ static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)