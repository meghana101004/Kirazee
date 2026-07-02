from django.urls import path
from django.conf import settings
from django.conf.urls.static import static
from .gro_views import (
    GroceriesByBusinessView, 
    GroceryCategoriesByBusinessView, 
    GroceriesByCategoryView, 
    GroceriesCartView, 
    CreateOrderView, 
    OrderDetailsView, 
    CreatePaymentView, 
    VerifyPaymentView, 
    CancelPaymentView,
    HighRatedProductsView,
    DiscountedProductsView,
    TopSellingItemsByCategoryView,
    TopSellingOverallView,
    UserTopItemsView,
    GroceryPartnerRegistrationView,
    BusinessOrdersView,
    UpdateOrderStatusView,
    DeliveryPartnerCheckView,
    AssignOrderToPartnerView,
    UpdateDeliveryStatusView,
    UpdatePartnerStatusView,
    PartnerDeliveryDetailsView,
    DeliveryDetailsByOrderView,
    VerifyDeliveryOTPView,
    GeneratePickupOTPView,
    VerifyPickupOTPView,
    GroceriesBulkTemplateView,
    GroceriesBulkUploadView,
    ServiceAvailabilityView,
    UpdateServiceAvailabilityView,
    BusinessFeedbackView,
    CalculateDeliveryChargeView,
)
from .gro_ratings_views import CreateRatingHistoryView, GetRatingHistoryView

urlpatterns = [
    
    path('product-items/', GroceriesByBusinessView.as_view(), name='product-items-by-business'),
    path('grocery-categories/', GroceryCategoriesByBusinessView.as_view(), name='grocery-categories-by-business'),
    path('groceries-by-category/', GroceriesByCategoryView.as_view(), name='groceries-by-category'),
    
    # Bulk CSV template and upload
    path('groceries-bulk-template/', GroceriesBulkTemplateView.as_view(), name='groceries-bulk-template'),
    path('groceries-bulk-upload/', GroceriesBulkUploadView.as_view(), name='groceries-bulk-upload'),

    # Business service availability (delivery/pickup) endpoints
    path('service-availability/', ServiceAvailabilityView.as_view(), name='service-availability'),
    path('admin/service-availability/', UpdateServiceAvailabilityView.as_view(), name='update-service-availability'),

    # Cart URL (uses query parameters)
    path('cart/', GroceriesCartView.as_view(), name='cart-operations'),
    
    # Order URL
    path('create-order/', CreateOrderView.as_view(), name='create-order'),
    path('order-details/', OrderDetailsView.as_view(), name='order-details'),

    # Razorpay Payment URLs
    path('create-razorpay-order/', CreatePaymentView.as_view(), name='create-razorpay-order'),
    path('verify-razorpay-payment/', VerifyPaymentView.as_view(), name='verify-razorpay-payment'),
    path('cancel-payment/', CancelPaymentView.as_view(), name='cancel-payment'),
    
    # High-rated products URL
    path('high-rated-products/', HighRatedProductsView.as_view(), name='high-rated-products'),
    # Discounted products URL (10–14% off by default)
    path('discounted-products/', DiscountedProductsView.as_view(), name='discounted-products'),
    
    # Top-selling items by category URL
    path('top-selling-by-category/', TopSellingItemsByCategoryView.as_view(), name='top-selling-by-category'),

    # Overall top-selling items URL
    path('top-selling-overall/', TopSellingOverallView.as_view(), name='top-selling-overall'),

    # User's top items URL (top-N items a specific user buys most for a business)
    path('user-top-items/', UserTopItemsView.as_view(), name='user-top-items'),
    
    # Partner registration URL (uses query parameters for user_id and business_id)
    path('partner-registration/', GroceryPartnerRegistrationView.as_view(), name='partner-registration'),
    
    # Business orders URL (uses query parameters for business_id and optional filters)
    path('business-orders/', BusinessOrdersView.as_view(), name='business-orders'),
    
    # Single order status update URL (accepts business_id, order_id, status parameters)
    path('update-order-status/', UpdateOrderStatusView.as_view(), name='update-order-status'),
    
    # Delivery partner check URL (accepts user_mode and business_id parameters)
    path('check-delivery-partner/', DeliveryPartnerCheckView.as_view(), name='check-delivery-partner'),
    
    # Assign order to delivery partner URL (accepts user_id and business_id parameters)
    path('assign-order/', AssignOrderToPartnerView.as_view(), name='assign-order'),
    path('update-delivery-status/', UpdateDeliveryStatusView.as_view(), name='update-delivery-status'),
    path('update-partner-status/', UpdatePartnerStatusView.as_view(), name='update-partner-status'),
    
    # Get delivery details by partner user_id URL (accepts partner_user_id and optional business_id parameters)
    path('partner-delivery-details/', PartnerDeliveryDetailsView.as_view(), name='partner-delivery-details'),
    
    # Get delivery details by order ID
    path('delivery-details/', DeliveryDetailsByOrderView.as_view(), name='delivery-details-by-order'),
    
    # Verify delivery OTP and mark order as delivered (use query parameters: ?partner_user_id=123&order_id=456)
    path('verify-delivery-otp/', VerifyDeliveryOTPView.as_view(), name='verify-delivery-otp'),
    
    # Generate pickup OTP for customer verification (use query parameter: ?business_id=123)
    path('generate-pickup-otp/', GeneratePickupOTPView.as_view(), name='generate-pickup-otp'),
    
    # Verify pickup OTP and mark order as delivered (use query parameter: ?business_id=123)
    path('verify-pickup-otp/', VerifyPickupOTPView.as_view(), name='verify-pickup-otp'),
    # Ratings History (POST create, GET list)
    path('rating-history/create/', CreateRatingHistoryView.as_view(), name='create-rating-history'),
    path('rating-history/', GetRatingHistoryView.as_view(), name='get-rating-history'),

    # Business Feedback (POST create multiple items, GET list by business and optional user)
    path('business-feedback/', BusinessFeedbackView.as_view(), name='business-feedback'),

    path('calculate-delivery-charge/', CalculateDeliveryChargeView.as_view(), name='calculate-delivery-charge'),
]+ static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)