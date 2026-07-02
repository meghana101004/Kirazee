from django.db.models.fields import return_None
from rest_framework.decorators import api_view
from rest_framework import status
from django.shortcuts import render, redirect
from django.http import JsonResponse
from django.conf import settings
from django.utils import timezone
from drf_yasg.utils import swagger_auto_schema
import json
import razorpay
import logging
import pytz
from django.db import transaction
from rest_framework.response import Response
from rest_framework.views import csrf_exempt
from kirazee_app.models import Business, Registration, BusinessFinancial
from .models import BusinessPayment
from consumer.models import Payments  # Import Payments model from consumer app
from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.utils.html import strip_tags

# Configure logger
logger = logging.getLogger(__name__)

def get_ist_now():
    """Returns current time in IST (Asia/Kolkata)"""
    ist = pytz.timezone('Asia/Kolkata')
    return timezone.now().astimezone(ist)

def convert_to_ist(dt):
    """Converts any datetime to IST (Asia/Kolkata)"""
    if dt is None:
        return None
    ist = pytz.timezone('Asia/Kolkata')
    if timezone.is_aware(dt):
        return dt.astimezone(ist)
    return timezone.make_aware(dt, ist) 

@csrf_exempt
@transaction.atomic
def save_payment_data(request):
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            transaction_id = data.get('transaction_id')
            amount = data.get('amount')
            status_param = data.get('status')
            business_id_str = data.get('business_id')
            user_id_str = data.get('user_id')
            
            # Initialize payment variables from request data
            payment_method_from_razorpay = data.get('payment_method')
            upi_id_from_razorpay = data.get('upi_id')

            payment_source_from_razorpay = None
            
            # Fetch payment details from Razorpay if transaction_id is present
            if transaction_id and transaction_id != 'no_txn_id' and status_param == 'success':
                client = razorpay.Client(auth=(settings.RAZORPAY_KEY_ID, settings.RAZORPAY_KEY_SECRET))
                try:
                    payment_details = client.payment.fetch(transaction_id)
                    payment_method_from_razorpay = payment_details.get('method')
                    upi_id_from_razorpay = payment_details.get('vpa') if payment_method_from_razorpay == 'upi' else None
                    status_param = payment_details.get('status') # Use the official status from Razorpay
                
                    # Extract payment source based on method
                    if payment_method_from_razorpay == 'upi':
                        if 'vpa' in payment_details:
                            # Define the dictionary and assign it to a variable
                            domain_mapping = {
                                "okicici": "Google Pay",
                                "okaxis": "Google Pay",
                                "oksbi": "Google Pay",
                                "okhdfc": "Google Pay",
                                "ybl": "PhonePe",
                                "ibl": "PhonePe",
                                "paytm": "Paytm",
                                "upi": "BHIM",
                                "apl": "Amazon Pay",
                                "cred": "Cred",
                                "wa": "WhatsApp Pay",
                                "airtel": "Airtel Payments Bank",
                                "kotak": "Kotak Mahindra Bank",
                                "axisbank": "Axis Bank",
                                "hdfcbank": "HDFC Bank",
                                "sbi": "State Bank of India",
                                "icici": "ICICI Bank"
                            }
                            # Extract the domain part of the VPA (e.g., 'paytm' from 'user@paytm')
                            vpa_domain = payment_details['vpa'].split('@')[-1]
                            payment_source_from_razorpay = domain_mapping.get(vpa_domain, vpa_domain)
                        else:
                            # Fallback if no VPA is available but method is UPI
                            payment_source_from_razorpay = payment_details.get('provider')
                    elif payment_method_from_razorpay == 'card':
                        payment_source_from_razorpay = payment_details.get('card', {}).get('issuer')
                    elif payment_method_from_razorpay == 'wallet':
                        payment_source_from_razorpay = payment_details.get('wallet')

                except Exception as e:
                    logger.error(f"Failed to fetch payment details from Razorpay for {transaction_id}: {e}") 
                    # Handle this as a verification failure to avoid saving inaccurate data
                    status_param = 'verification_failed'
            else:
                pass

            try:
                business_instance = Business.objects.get(business_id=business_id_str)
            except Business.DoesNotExist:
                return JsonResponse({'status': 'error', 'message': f'Invalid businessID: {business_id_str}. Please use a valid businessID from Business table.'}, status=400)

            try:
                user_instance = Registration.objects.get(user_id=user_id_str)
            except Registration.DoesNotExist:
                return JsonResponse({'status': 'error', 'message': f'Invalid userID: {user_id_str}. Please use a valid userID from Registration table.'}, status=400)

            # Get current time in IST
            current_time = get_ist_now()

            try:
                payment = BusinessPayment.objects.create(
                    transaction_id=transaction_id,
                    amount=amount,
                    currency='INR',
                    payment_method=payment_method_from_razorpay,
                    status=status_param,
                    upi_id=upi_id_from_razorpay,
                    payment_source=payment_source_from_razorpay,
                    business_id=business_instance,
                    user_id=user_instance,
                    created_at=current_time,
                    updated_at=current_time,
                    refund_status='Not Applicable',
                    refund_id='Not Applicable',
                    payment_type='Business'
                )

                # Update the business's payment status and activate business on success
                if status_param in ['captured', 'authorized', 'success']:
                    business_instance.paymentstatus = 1
                    business_instance.status = True
                    business_instance.save(update_fields=['paymentstatus', 'status'])  # Use update_fields for efficiency
                
                return JsonResponse({
                    'status': 'success',
                    'message': 'Payment data saved successfully!',
                    'payment': {
                        'transaction_id': payment.transaction_id,
                        'amount': float(payment.amount),
                        'payment_method': payment.payment_method,
                        'status': payment.status,
                        'upi_id': payment.upi_id,
                        'payment_source': payment.payment_source,
                        'business_id': str(payment.business_id.business_id),
                        'user_id': str(payment.user_id.user_id),
                        'created_at': convert_to_ist(payment.created_at).isoformat(),
                    }
                })
            except Exception as e:
                logger.error(f"Failed to create BusinessPayment record: {e}")
                return JsonResponse({'status': 'error', 'message': f'Failed to create payment record: {e}'}, status=500)
        except json.JSONDecodeError:
            return JsonResponse({'status': 'error', 'message': 'Invalid JSON data.'}, status=400)
    return JsonResponse({'status': 'error', 'message': 'Invalid request method.'}, status=405)

def send_refund_email(user_email, amount):
    """Sends a refund notification email to the user."""
    subject = 'Payment Refund Processed'
    html_message = render_to_string('refund_email_template.html', {'amount': amount})
    plain_message = strip_tags(html_message)
    from_email = settings.DEFAULT_FROM_EMAIL
    
    send_mail(subject, plain_message, from_email, [user_email], html_message=html_message)

@swagger_auto_schema(methods=['POST'], tags=['Business'])
@api_view(['POST'])
def process_refund(request):
    """
    Endpoint to process a refund and send an email notification.
    """
    if request.method == 'POST':
        transaction_id = request.data.get('transaction_id')
        amount = request.data.get('amount')

        if not transaction_id or not amount:
            return Response({"error": "Transaction ID and amount are required"}, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            payment_record = BusinessPayment.objects.get(transaction_id=transaction_id)
            user_email = payment_record.user_id.email
        except BusinessPayment.DoesNotExist:
            return Response({"error": "Payment record not found"}, status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            logger.error(f"Error fetching payment record or user email: {e}")
            return Response({"error": "Internal server error"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        client = razorpay.Client(auth=(settings.RAZORPAY_KEY_ID, settings.RAZORPAY_KEY_SECRET))
        try:
            refund_response = client.payment.refund(transaction_id, int(float(amount) * 100))
            
            # Update the payment record with refund status and ID
            payment_record.refund_status = refund_response['status']
            payment_record.refund_id = refund_response['id']
            payment_record.save()
            
            # Send email notification
            send_refund_email(user_email, amount)
            
            return Response({"message": "Refund processed and email sent", "refund_id": refund_response['id']}, status=status.HTTP_200_OK)
        except Exception as e:
            logger.error(f"Razorpay refund failed for transaction {transaction_id}: {e}")
            return Response({"error": "Refund failed", "details": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
            

@swagger_auto_schema(methods=['GET'], tags=['Business'])
@api_view(['GET'])
def payment_gateway(request):
    if request.method == 'GET':
        user_id_str = request.query_params.get("userID")
        amount = request.query_params.get("amount")
        business_id_str = request.query_params.get("business_id")
        razorpay_mode = request.query_params.get("mode", "test")
        order_id = request.query_params.get("order_id", "")
        
        if not user_id_str:
            return Response({"error": "userID is required"}, status=status.HTTP_400_BAD_REQUEST)
        try:
            # We don't need to fetch the full user object, just validate its existence
            Registration.objects.get(user_id=user_id_str, status=True)
        except Registration.DoesNotExist:
            return Response({"error": "Invalid user_id or user is not active."}, status=status.HTTP_404_NOT_FOUND)
        
        if not business_id_str:
            return Response({"error": "business_id is required"}, status=status.HTTP_400_BAD_REQUEST)
        try:
            # Validate business exists (status can be False prior to payment)
            Business.objects.get(business_id=business_id_str)
        except Business.DoesNotExist:
            return Response({"error": "Invalid business_id."}, status=status.HTTP_404_NOT_FOUND)
        
        if not amount:
            return Response({"error": "amount is required"}, status=status.HTTP_400_BAD_REQUEST)

        # Build URLs for success/cancel pages
        base_url = request.build_absolute_uri('/')
        success_url = f"{base_url}payment/success/?business_id={business_id_str}&amount={amount}"
        cancel_url = f"{base_url}payment/cancel/?business_id={business_id_str}&amount={amount}"
        
        # Get Razorpay key based on mode
        if razorpay_mode == "live":
            razorpay_key = getattr(settings, 'RAZORPAY_KEY_ID', 'rzp_live_XXXXXXXXXXXX')
        else:
            razorpay_key = 'rzp_live_RWVzTgqHj7oJwO'
        
        context = {
            "user_id": user_id_str, # Pass the ID as a string
            "amount": amount,
            "business_id": business_id_str, # Pass the ID as a string
            "razorpay_mode": razorpay_mode,
            "razorpay_key": razorpay_key,
            "order_id": order_id,
            "success_url": success_url,
            "cancel_url": cancel_url,
            "business_name": "Kirazee"
        }
        return render(request, 'payment_gateway.html', context)


@swagger_auto_schema(methods=['GET'], tags=['Business'])
@api_view(['GET'])
def business_payment_gateway(request):
    """Business setup payment gateway - exact replica of order payment flow"""
    if request.method == 'GET':
        user_id_str = request.query_params.get("userID")
        amount = request.query_params.get("amount")
        business_id_str = request.query_params.get("business_id")
        razorpay_mode = request.query_params.get("mode", "test")
        order_id = request.query_params.get("order_id", "")
        
        if not user_id_str:
            return Response({"error": "userID is required"}, status=status.HTTP_400_BAD_REQUEST)
        try:
            # Validate user exists
            Registration.objects.get(user_id=user_id_str, status=True)
        except Registration.DoesNotExist:
            return Response({"error": "Invalid user_id or user is not active."}, status=status.HTTP_404_NOT_FOUND)
        
        if not business_id_str:
            return Response({"error": "business_id is required"}, status=status.HTTP_400_BAD_REQUEST)
        try:
            # Validate business exists
            Business.objects.get(business_id=business_id_str)
        except Business.DoesNotExist:
            return Response({"error": "Invalid business_id."}, status=status.HTTP_404_NOT_FOUND)
        
        if not amount:
            return Response({"error": "amount is required"}, status=status.HTTP_400_BAD_REQUEST)

        # Get Razorpay key based on mode
        if razorpay_mode == "live":
            razorpay_key = getattr(settings, 'RAZORPAY_KEY_ID', 'rzp_live_XXXXXXXXXXXX')
        else:
            razorpay_key = 'rzp_live_RWVzTgqHj7oJwO'
        
        # Build callback URL for UPI app returns
        callback_url = request.build_absolute_uri(f"/kirazee/business/business-payment-gateway/?userID={user_id_str}&amount={amount}&business_id={business_id_str}&mode={razorpay_mode}")
        
        context = {
            "user_id": user_id_str,
            "amount": amount,
            "business_id": business_id_str,
            "razorpay_mode": razorpay_mode,
            "razorpay_key_id": razorpay_key,  # For template compatibility
            "order_id": order_id,
            "business_name": "Kirazee",
            "callback_url": callback_url,  # Add callback URL for UPI returns
            "BASE_URL": settings.BASE_URL
        }
        return render(request, 'business_payment_gateway.html', context)


def payment_success(request):
    """Handle payment success redirect from Razorpay"""
    if request.method == 'GET':
        # Extract payment details from URL parameters
        razorpay_payment_id = request.GET.get('razorpay_payment_id')
        amount = request.GET.get('amount')
        business_id = request.GET.get('business_id')
        user_id = request.GET.get('user_id')
        
        # Check if this is an Android WebView requesting callback
        is_android = request.GET.get('platform') == 'android'
        
        context = {
            'amount': amount,
            'business_id': business_id,
            'user_id': user_id,
            'razorpay_payment_id': razorpay_payment_id,
            'is_android': is_android
        }
        
        # Log for debugging
        logger.info(f"Payment success page accessed: payment_id={razorpay_payment_id}, business_id={business_id}, amount={amount}, user_id={user_id}")
        
        # If Android WebView, render callback page
        if is_android:
            return render(request, 'business_payment_callback.html', context)
        
        return render(request, 'payment_success.html', context)


def business_payment_success(request):
    """Dedicated payment success endpoint for business setup"""
    if request.method == 'GET':
        user_id = request.GET.get('userID')
        business_id = request.GET.get('business_id')
        amount = request.GET.get('amount')
        payment_id = request.GET.get('payment_id')
        
        # Check if this is Android WebView
        user_agent = request.META.get('HTTP_USER_AGENT', '').lower()
        is_android_webview = 'wv' in user_agent or 'android' in user_agent
        
        if is_android_webview:
            # Return HTML page with Android callback
            context = {
                'user_id': user_id,
                'business_id': business_id,
                'amount': amount,
                'payment_id': payment_id,
                'status': 'success'
            }
            return render(request, 'business_payment_callback.html', context)
        else:
            # For web browsers, render success page (NOT redirect to user-status)
            context = {
                'amount': amount,
                'business_id': business_id,
                'user_id': user_id,
                'payment_id': payment_id,
                'status': 'success'
            }
            return render(request, 'payment_success.html', context)


def payment_cancel(request):
    """Handle payment cancel/failure redirect from Razorpay"""
    if request.method == 'GET':
        # Extract payment details from URL parameters
        error_code = request.GET.get('error_code', 'CANCELLED')
        error_message = request.GET.get('error', 'Payment was cancelled')
        amount = request.GET.get('amount')
        business_id = request.GET.get('business_id')
        
        context = {
            'amount': amount,
            'business_id': business_id,
            'error_code': error_code,
            'error_message': error_message
        }
        
        # Log for debugging
        logger.info(f"Payment cancel page accessed: error_code={error_code}, business_id={business_id}, amount={amount}")
        
        return render(request, 'payment_cancel.html', context)


@swagger_auto_schema(methods=['POST'], tags=['Business'])
@api_view(['POST'])
@csrf_exempt
def save_business_payment_data(request):
    """Save business setup payment data - exact replica of order payment flow"""
    try:
        # Debug logging
        logger.info(f"Payment data request received")
        logger.info(f"Request content type: {request.content_type}")
        logger.info(f"Request method: {request.method}")
        logger.info(f"POST data: {dict(request.POST)}")
        logger.info(f"JSON data: {request.data}")
        
        # Handle both form data and JSON data
        if request.content_type == 'application/json':
            data = request.data
        else:
            # Form data from JavaScript form submission
            data = request.POST
        
        user_id = data.get('user_id')
        business_id = data.get('business_id')
        amount = data.get('amount')
        payment_id = data.get('payment_id')
        order_id = data.get('order_id')
        signature = data.get('signature')
        payment_status = data.get('status')  # Renamed to avoid conflict
        payment_method = data.get('payment_method', 'razorpay')
        platform = data.get('platform', 'web')
        
        logger.info(f"Extracted fields: user_id={user_id}, business_id={business_id}, amount={amount}, payment_id={payment_id}, status={payment_status}")
        
        if not all([user_id, business_id, amount, payment_id, payment_status]):
            return Response(
                {'status': 'error', 'message': f'Missing required fields: user_id={user_id}, business_id={business_id}, amount={amount}, payment_id={payment_id}, status={payment_status}'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Validate user exists
        try:
            user = Registration.objects.get(user_id=user_id, status=True)
        except Registration.DoesNotExist:
            return Response(
                {'status': 'error', 'message': f'Invalid user_id: {user_id}'},
                status=status.HTTP_404_NOT_FOUND
            )
        
        # Validate business exists
        try:
            business = Business.objects.get(business_id=business_id)
        except Business.DoesNotExist:
            return Response(
                {'status': 'error', 'message': f'Invalid business_id: {business_id}'},
                status=status.HTTP_404_NOT_FOUND
            )
        
        # Create payment record for business setup
        payment = Payments.objects.create(
            user=user,
            business=business,
            amount=amount,
            payment_method=Payments.Method.RAZORPAY if payment_method == 'razorpay' else Payments.Method.ONLINE,
            status=Payments.Status.SUCCESS if payment_status == 'success' else Payments.Status.FAILED,
            transaction_id=payment_id,
            payment_source=platform,
            currency='INR',
            payment_type='setup_fee'  # Differentiate from order payments
        )
        
        if payment_status == 'success':
            # Update business payment status
            business.paymentstatus = True
            business.status = True  # Activate business
            business.save()
            
            # Create or update BusinessMapping to link user to business
            from kirazee_app.models import BusinessMapping
            try:
                logger.info(f"Looking for BusinessMapping for user {user_id}")
                mapping = BusinessMapping.objects.get(user=user)
                # Update existing mapping
                mapping.business = business
                mapping.status = True
                mapping.save()
                logger.info(f"Updated existing BusinessMapping for user {user_id} -> business {business_id}")
            except BusinessMapping.DoesNotExist:
                # Create new mapping
                logger.info(f"Creating new BusinessMapping for user {user_id} -> business {business_id}")
                mapping = BusinessMapping.objects.create(
                    user=user,
                    business=business,
                    status=True
                )
                logger.info(f"Created new BusinessMapping with ID {mapping.id} for user {user_id} -> business {business_id}")
            except Exception as e:
                logger.error(f"Error creating/updating BusinessMapping: {e}")
                # Continue with payment processing even if mapping fails
            
            # Update BusinessFinancial record
            try:
                financial = BusinessFinancial.objects.get(business=business)
                financial.is_payment_done = True
                financial.save()
            except BusinessFinancial.DoesNotExist:
                # Create if doesn't exist
                BusinessFinancial.objects.create(
                    business=business,
                    is_payment_done=True
                )
            
            # Send notifications
            try:
                from notifications.hooks import on_business_payment_success
                on_business_payment_success(business, user, payment)
            except ImportError:
                # Fallback if hook doesn't exist
                pass
            
            # Check if this is an Android WebView request
            user_agent = request.META.get('HTTP_USER_AGENT', '').lower()
            is_android_webview = 'wv' in user_agent or 'android' in user_agent
            
            if is_android_webview:
                # Return HTML page with Android callback for WebView
                context = {
                    'user_id': user_id,
                    'business_id': business_id,
                    'amount': amount,
                    'payment_id': payment.id,
                    'status': 'success'
                }
                return render(request, 'business_payment_callback.html', context)
            else:
                # For web browsers, directly redirect to success page (NOT user-status)
                success_url = f'/kirazee/business/payment/success/?userID={user_id}&business_id={business_id}&amount={amount}&payment_id={payment.id}'
                return redirect(success_url)
        else:
            return Response({
                'status': 'failed',
                'message': 'Payment failed or cancelled',
                'data': {
                    'payment_id': payment.id,
                    'business_id': business.business_id,
                    'amount': float(amount),
                    'status': 'failed'
                }
            })
            
    except Exception as e:
        logger.error(f"Error saving business payment data: {str(e)}")
        return Response(
            {'status': 'error', 'message': f'Failed to save payment data: {str(e)}'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )
