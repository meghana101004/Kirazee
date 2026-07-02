from django.shortcuts import render
from django.http import JsonResponse
from django.views import View
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator
from rest_framework.permissions import AllowAny
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from .models import NavDisplayItem, BusinessFeaturePurchase
from .serializers import NavDisplayItemSerializer
from kirazee_app.models import Business
import json
from decimal import Decimal
from django.utils import timezone
from django.conf import settings
import logging


logger = logging.getLogger(__name__)


class BusinessSettingsView(APIView):
    """Display Business Settings items with purchase status for a business"""
    permission_classes = [AllowAny]
    
    def get(self, request):
        business_id = request.query_params.get('business_id')
        
        if not business_id:
            return Response({
                'success': False,
                'message': 'business_id parameter is required'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            # Get Business Settings navigation item (assuming it exists with nav_name='Business Settings')
            from .models import RoleBasedNavItems
            business_settings_nav = RoleBasedNavItems.objects.filter(
                nav_name='Business Settings'
            ).first()
            
            if not business_settings_nav:
                return Response({
                    'success': False,
                    'message': 'Business Settings navigation item not found'
                }, status=status.HTTP_404_NOT_FOUND)
            
            # Get all display items for Business Settings
            display_items = NavDisplayItem.objects.filter(
                nav_item=business_settings_nav,
                status=True
            ).order_by('order_index')
            
            # Serialize with purchase status
            serializer = NavDisplayItemSerializer(
                display_items, 
                many=True, 
                context={'request': request}
            )
            
            return Response({
                'success': True,
                'data': {
                    'business_id': business_id,
                    'nav_item_id': business_settings_nav.id,
                    'nav_item_name': business_settings_nav.nav_name,
                    'display_items': serializer.data
                }
            })
            
        except Exception as e:
            return Response({
                'success': False,
                'message': f'Internal server error: {str(e)}'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class FeaturePaymentRedirectView(APIView):
    """Render payment gateway page with feature details"""
    permission_classes = [AllowAny]
    
    def get(self, request):
        business_id = request.query_params.get('business_id')
        feature_key = request.query_params.get('feature_key')
        user_id = request.query_params.get('user_id')
        
        logger.info(f"FeaturePaymentRedirectView.get called with business_id={business_id}, feature_key={feature_key}, user_id={user_id}")
        
        if not all([business_id, feature_key, user_id]):
            return JsonResponse({
                'success': False,
                'message': 'business_id, feature_key, and user_id are required'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            # Get feature details
            feature = NavDisplayItem.objects.get(
                key=feature_key,
                status=True
            )
            
            # Check if already purchased
            is_purchased = False
            if feature.is_premium:
                purchase = BusinessFeaturePurchase.objects.filter(
                    business_id=business_id,
                    feature_key=feature_key,
                    status='ACTIVE'
                ).first()
                if purchase and purchase.is_active():
                    is_purchased = True
            
            # If already purchased, render success page
            if is_purchased:
                context = {
                    'feature_name': feature.label,
                    'is_purchased': True,
                    'purchased_at': purchase.purchased_at,
                    'expires_at': purchase.expires_at
                }
                return render(request, 'feature_payment_success.html', context)
            
            # Ensure there is a pending feature purchase record for this business & feature
            try:
                amount_to_pay = Decimal(str(feature.price)) if feature.price is not None else Decimal('0.00')
                business_obj = Business.objects.get(business_id=business_id)
                feature_purchase, created = BusinessFeaturePurchase.objects.get_or_create(
                    business_id=business_obj,
                    feature_key=feature.key,
                    defaults={
                        'amount_paid': amount_to_pay,
                    }
                )
                if not created:
                    feature_purchase.amount_paid = amount_to_pay
                    feature_purchase.status = 'PENDING'
                    feature_purchase.payment_id = None
                    feature_purchase.save(update_fields=['amount_paid', 'status', 'payment_id'])
            except Exception as e:
                logger.error(f"Failed to ensure feature purchase record: {str(e)}")

            # Create proper Razorpay order before redirecting
            logger.info(f"Creating Razorpay order for feature: {feature.key}, business: {business_id}")
            try:
                import razorpay
                logger.info("Razorpay import successful")
                client = razorpay.Client(auth=(
                    getattr(settings, 'RAZORPAY_KEY_ID', ''),
                    getattr(settings, 'RAZORPAY_KEY_SECRET', ''),
                ))
                logger.info("Razorpay client created successfully")
                
                # Create Razorpay order with custom receipt ID
                razorpay_order = client.order.create({
                    'amount': int(float(str(feature.price)) * 100),  # Convert to paise
                    'currency': 'INR',
                    'payment_capture': 1,
                    'receipt': f'feature_{feature.key}',  # Use custom ID as receipt
                    'notes': {
                        'business_id': business_id,
                        'feature_key': feature.key,
                        'user_id': user_id
                    }
                })
                
                # Get Razorpay order ID
                razorpay_order_id = razorpay_order['id']
                logger.info(f"Created Razorpay order: {razorpay_order_id}")
                
                # Render payment template with valid Razorpay order ID
                context = {
                    'business_id': business_id,
                    'feature_key': feature.key,
                    'user_id': user_id,
                    'feature_name': feature.label,
                    'price': str(feature.price),
                    'description': feature.description,
                    'is_new': 'True',
                    'expiry_days': feature.expiry_days,
                    'razorpay_order_id': razorpay_order_id,  # Pass valid order ID to template
                    'razorpay_key_id': getattr(settings, 'RAZORPAY_KEY_ID', '')
                }
                return render(request, 'feature_payment.html', context)
                
            except ImportError as ie:
                logger.error(f"Razorpay import failed: {str(ie)}")
                return JsonResponse({
                    'success': False,
                    'message': f'Payment gateway library error: {str(ie)}'
                }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
            except Exception as e:
                logger.error(f"Razorpay order creation failed: {str(e)}")
                return JsonResponse({
                    'success': False,
                    'message': f'Payment gateway error: {str(e)}'
                }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
            
            # Build payment URL parameters for existing Razorpay gateway
            payment_params = {
                'userID': user_id,
                'amount': str(feature.price) if feature.price else '0.00',
                'business_id': business_id,
                'mode': 'test',  # or 'live' for production
                'order_id': razorpay_order_id  # Use real Razorpay order ID
            }
            
            logger.info(f"Payment params: {payment_params}")
            
            # Build Razorpay payment gateway URL
            payment_url = f"/kirazee/business/business-payment-gateway/?{'&'.join([f'{k}={v}' for k, v in payment_params.items()])}"
            
            logger.info(f"Redirecting to: {payment_url}")
            
            # Redirect to Razorpay payment gateway
            from django.shortcuts import redirect
            return redirect(payment_url)
            
        except NavDisplayItem.DoesNotExist:
            return JsonResponse({
                'success': False,
                'message': 'Feature not found'
            }, status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            return JsonResponse({
                'success': False,
                'message': f'Internal server error: {str(e)}'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
