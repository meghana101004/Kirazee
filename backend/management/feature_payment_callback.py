from django.shortcuts import render
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from rest_framework.permissions import AllowAny
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from .models import NavDisplayItem, BusinessFeaturePurchase
from business.models import BusinessPayment
from kirazee_app.models import Business
from decimal import Decimal
import logging
from django.utils import timezone

logger = logging.getLogger(__name__)


class FeaturePaymentCallbackView(APIView):
    """Handle Razorpay payment success callback and activate feature purchases"""
    permission_classes = [AllowAny]
    
    def get(self, request):
        """Handle payment success callback from Razorpay"""
        try:
            # Extract payment details
            razorpay_payment_id = request.GET.get('razorpay_payment_id')
            payment_id = request.GET.get('payment_id')
            business_id = request.GET.get('business_id')
            user_id = request.GET.get('userID')
            amount = request.GET.get('amount')
            order_id = request.GET.get('order_id', '')
            feature_key = request.GET.get('feature_key')
            
            if not all([razorpay_payment_id, business_id, feature_key]):
                return JsonResponse({
                    'success': False,
                    'message': 'Missing payment details'
                }, status=400)
            
            logger.info(
                f"FeaturePaymentCallbackView received: razorpay_payment_id={razorpay_payment_id}, "
                f"payment_id={payment_id}, business_id={business_id}, user_id={user_id}, "
                f"amount={amount}, order_id={order_id}, feature_key={feature_key}"
            )
            
            # Resolve Business object for FK operations
            try:
                business_obj = Business.objects.get(business_id=business_id)
            except Business.DoesNotExist:
                logger.error(f"Business not found for business_id {business_id}")
                return JsonResponse({
                    'success': False,
                    'message': 'Business not found'
                }, status=404)
            
            # Parse amount if possible (for amount_paid tracking)
            amount_decimal = None
            if amount is not None:
                try:
                    amount_decimal = Decimal(str(amount))
                except Exception:
                    logger.warning(f"Could not parse amount '{amount}' as Decimal in FeaturePaymentCallbackView")
            
            # Get payment record if provided
            payment = None
            if payment_id:
                try:
                    payment = BusinessPayment.objects.get(id=payment_id)
                    if payment.status != 'PENDING':
                        return JsonResponse({
                            'success': False,
                            'message': 'Payment already processed'
                        }, status=400)
                except BusinessPayment.DoesNotExist:
                    logger.error(f"Payment record not found for id {payment_id}")
                    payment = None
            
            # Activate feature purchase
            try:
                feature_purchase = BusinessFeaturePurchase.objects.get(
                    business_id=business_obj,
                    feature_key=feature_key,
                    status='PENDING'
                )
                
                # Update purchase to ACTIVE
                feature_purchase.status = 'ACTIVE'
                if payment:
                    feature_purchase.payment_id = payment
                if amount_decimal is not None:
                    feature_purchase.amount_paid = amount_decimal
                feature_purchase.save()
                
                logger.info(f"Feature purchase activated: {feature_key} for business {business_id}")
                
            except BusinessFeaturePurchase.DoesNotExist:
                # If we cannot find a pending record, create an ACTIVE one so the feature is not lost
                logger.warning(
                    f"Feature purchase record not found for {feature_key}, business {business_id}. "
                    "Creating new ACTIVE purchase record from callback."
                )
                create_kwargs = {
                    'business_id': business_obj,
                    'feature_key': feature_key,
                    'status': 'ACTIVE',
                }
                if amount_decimal is not None:
                    create_kwargs['amount_paid'] = amount_decimal
                if payment:
                    create_kwargs['payment_id'] = payment
                feature_purchase = BusinessFeaturePurchase.objects.create(**create_kwargs)
                logger.info(f"Created new ACTIVE feature purchase {feature_key} for business {business_id}")
            
            # Update payment status to SUCCESS if we have a payment record
            if payment:
                payment.status = 'SUCCESS'
                payment.razorpay_payment_id = razorpay_payment_id
                payment.save(update_fields=['status', 'razorpay_payment_id'])
            
            # Render success page
            context = {
                'amount': amount,
                'business_id': business_id,
                'user_id': user_id,
                'razorpay_payment_id': razorpay_payment_id,
                'feature_key': feature_key,
                'status': 'success'
            }
            
            return render(request, 'feature_payment_success.html', context)
            
        except Exception as e:
            logger.error(f"Feature payment callback error: {str(e)}")
            return JsonResponse({
                'success': False,
                'message': 'Internal server error'
            }, status=500)
    
    def post(self, request):
        """Handle Razorpay webhook for payment verification"""
        try:
            import json
            webhook_data = json.loads(request.body)
            
            # Verify webhook signature (implement in production)
            payment_id = webhook_data.get('payload', {}).get('payment', {}).get('entity', {}).get('id')
            
            if not payment_id:
                return JsonResponse({'success': False}, status=400)
            
            # Get and update payment
            try:
                payment = BusinessPayment.objects.get(transaction_id=payment_id)
                if payment.status == 'SUCCESS':
                    return JsonResponse({'success': True}, status=200)
                
                payment.status = 'SUCCESS'
                payment.save(update_fields=['status'])
                
                # Activate corresponding feature purchase
                try:
                    feature_purchase = BusinessFeaturePurchase.objects.get(payment_id=payment.id)
                    feature_purchase.status = 'ACTIVE'
                    feature_purchase.save(update_fields=['status'])
                    logger.info(f"Webhook activated feature: {feature_purchase.feature_key}")
                    
                except BusinessFeaturePurchase.DoesNotExist:
                    logger.error(f"Feature purchase not found for payment {payment.id}")
                
            except BusinessPayment.DoesNotExist:
                logger.error(f"Payment not found: {payment_id}")
                return JsonResponse({'success': False}, status=404)
            
            return JsonResponse({'success': True}, status=200)
            
        except Exception as e:
            logger.error(f"Webhook error: {str(e)}")
            return JsonResponse({'success': False}, status=500)
