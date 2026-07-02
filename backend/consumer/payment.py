import razorpay
import os
from typing import Optional
from django.conf import settings
from django.http import JsonResponse, HttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.shortcuts import render, get_object_or_404
from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework import status
from decimal import Decimal
import json
import logging
from drf_yasg.utils import swagger_auto_schema
import hmac
import hashlib
import time
import urllib.request
import ssl
from urllib.error import URLError, HTTPError
from django.utils import timezone
from django.db import connection, transaction, models

from .models import Orders, Payments, Coupons, CouponRedemptions
from kirazee_app.models import Business, BusinessFinancial
from notifications.hooks import on_payment_success

logger = logging.getLogger(__name__)

def _finalize_coupon_redemption_for_order(order: Orders):
    try:
        if not order or not getattr(order, 'coupon_code', None):
            return
        # If already redeemed for this order, skip
        with transaction.atomic():
            if CouponRedemptions.objects.select_for_update().filter(order_id=order).exists():
                return
            try:
                coupon = Coupons.objects.select_for_update().get(coupon_code=order.coupon_code)
            except Coupons.DoesNotExist:
                return

            # Increment global usage if under cap (do not fail if cap reached between order and payment)
            try:
                if coupon.max_total_redemptions:
                    Coupons.objects.filter(
                        pk=coupon.pk,
                        current_usage_count__lt=coupon.max_total_redemptions
                    ).update(current_usage_count=models.F('current_usage_count') + 1)
                else:
                    Coupons.objects.filter(pk=coupon.pk).update(current_usage_count=models.F('current_usage_count') + 1)
            except Exception:
                # Non-fatal
                pass

            # Create redemption row (idempotent by order check above)
            try:
                CouponRedemptions.objects.create(
                    coupon_id=coupon,
                    order_id=order,
                    user_id=order.user_id,
                    discount_amount_applied=getattr(order, 'discount_amount', 0) or Decimal('0'),
                    original_order_amount=getattr(order, 'total_amount', 0) or Decimal('0'),
                    final_order_amount=getattr(order, 'final_amount', 0) or Decimal('0'),
                )
            except Exception:
                # Best-effort; do not break payment success flow
                pass
    except Exception as ex:
        try:
            logger.error(f"finalize coupon redemption failed for order {getattr(order, 'order_id', None)}: {ex}")
        except Exception:
            pass

@swagger_auto_schema(methods=['POST'],tags=['Consumer'])
@api_view(['POST'])
def mark_offline_payment_collected(request):
    """
    Mark a pending/offline (pay-later) payment as collected by merchant.
    Payload: { order_id: number, method?: 'cod'|'cash'|'upi' }
    Idempotent: if already success, returns success.
    """
    try:
        order_id = request.data.get('order_id')
        method = (request.data.get('method') or 'cod').lower()
        if not order_id:
            return Response({'status': 'error', 'message': 'order_id is required'}, status=status.HTTP_400_BAD_REQUEST)

        # Find latest payment for this order
        payment = Payments.objects.filter(order_id=order_id).order_by('-created_at').first()
        if not payment:
            return Response({'status': 'error', 'message': 'No payment found for this order'}, status=status.HTTP_404_NOT_FOUND)

        if payment.status == Payments.Status.SUCCESS:
            return Response({'status': 'success', 'message': 'Payment already marked as success'})

        # Allow only pending to be marked success
        if payment.status != Payments.Status.PENDING:
            return Response({'status': 'error', 'message': f'Cannot mark payment from status {payment.status} to success'}, status=status.HTTP_400_BAD_REQUEST)

        # Update payment
        try:
            # Normalize method
            valid_methods = {m[0] for m in Payments.Method.choices}
            payment.payment_method = method if method in valid_methods else Payments.Method.COD
        except Exception:
            payment.payment_method = Payments.Method.COD
        payment.status = Payments.Status.SUCCESS
        payment.payment_source = 'merchant_panel'
        payment.save()

        # Update order if still pending and finalize coupon redemption
        try:
            order = Orders.objects.get(order_id=order_id)
            if order.status == Orders.OrderStatus.PENDING:
                order.confirm_order()
                order.save()
                try:
                    if order.user_id and getattr(order.user_id, 'user_id', None):
                        on_payment_success(int(order.user_id.user_id), int(order.order_id))
                except Exception:
                    pass
                try:
                    _finalize_coupon_redemption_for_order(order)
                except Exception:
                    pass
        except Orders.DoesNotExist:
            pass

        return Response({'status': 'success', 'message': 'Payment marked as collected'})
    except Exception as e:
        logger.error(f"mark_offline_payment_collected error: {e}")
        return Response({'status': 'error', 'message': 'Failed to mark payment collected'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


def _keys_look_valid(key_id: Optional[str], key_secret: Optional[str]) -> bool:
    """Lightweight validation to ensure keys are non-empty and shaped like Razorpay keys."""
    if not key_id or not key_secret:
        return False
    return key_id.startswith("rzp_test_") or key_id.startswith("rzp_live_")


def _gateway_config_looks_valid(gateway: Optional[str], creds: Optional[dict]) -> bool:
    """Validate that the provided gateway credentials look usable.

    This keeps validation lightweight and pluggable per gateway.
    """
    if not gateway:
        return False
    gateway = gateway.lower()
    creds = creds or {}

    if gateway == BusinessFinancial.PAYMENT_GATEWAY_RAZORPAY:
        return _keys_look_valid(creds.get("key_id"), creds.get("key_secret"))

    if gateway == BusinessFinancial.PAYMENT_GATEWAY_ICICI:
        # DEBUG: Test if file was uploaded correctly
        print("DEBUG_ICICI: ICICI payment function called - file uploaded successfully")
        
        # For direct merchant mode, only merchant_id and aggregator_secret are required
        merchant_id = creds.get("merchant_id")
        aggregator_secret = creds.get("aggregator_secret")
        return bool(merchant_id and aggregator_secret)

    return False


def _build_icici_payload(order: Orders, creds: dict, merchant_txn_no: str, return_url: str) -> dict:
    """Build the initiateSale payload for the ICICI / PayPhi v2 API.

    This implementation follows the UAT KIT provided for MerchantId T_03345.
    The payload includes the exact fields required for redirect-mode initiateSale
    and the secureHash is computed over the documented sequence:

      addlParam1, addlParam2, amount, currencyCode, customerEmailID,
      customerMobileNo, merchantId, merchantTxnNo, payType, returnURL,
      transactionType, txnDate

    All values are converted to strings and missing values are treated as
    empty strings to keep hashing deterministic.
    """

    merchant_id = creds.get("merchant_id") or ""
    aggregator_id = creds.get("aggregator_id") or creds.get("aggregatorID") or ""

    # Amount as string with 2 decimal places
    try:
        amount_str = f"{Decimal(order.final_amount):.2f}"
    except Exception:
        amount_str = str(order.final_amount)

    # ISO numeric currency code for INR is 356
    currency_code = "356"

    # Hosted checkout
    pay_type = "0"

    # Transaction datetime in YYYYMMDDHHMISS (use server timezone)
    now = timezone.now()
    txn_date = now.strftime("%Y%m%d%H%M%S")

    # Customer details
    user = getattr(order, "user_id", None)
    email = "dummy@gmail.com"
    mobile = ""
    customer_name = ""

    if user is not None:
        email = getattr(user, "emailID", None) or email
        mobile = str(getattr(user, "mobileNumber", "") or "")
        # Try to get customer name from user profile
        first_name = getattr(user, "firstName", "")
        last_name = getattr(user, "lastName", "")
        if first_name or last_name:
            customer_name = f"{first_name} {last_name}".strip()

    # Additional params are optional but included for completeness
    addl_param1 = ""  # e.g. "Test1"
    addl_param2 = ""  # e.g. "Test2"

    base_payload = {
        # Core initiateSale v2 fields (per UAT KIT)
        "merchantId": merchant_id,
        "merchantTxnNo": merchant_txn_no,
        "amount": amount_str,
        "currencyCode": currency_code,
        "payType": pay_type,
        "customerEmailID": email,
        "transactionType": "SALE",
        "txnDate": txn_date,
        "returnURL": return_url,
        "customerMobileNo": mobile,
        "addlParam1": addl_param1,
        "addlParam2": addl_param2,
    }
    
    # Add customer name if available (may help enable all payment options)
    if customer_name:
        base_payload["customerName"] = customer_name

    # AggregatorID is optional for direct merchant mode - only include if configured
    if aggregator_id:
        base_payload["aggregatorID"] = aggregator_id
    else:
        # Direct merchant mode - no aggregator needed
        logger.info("Using direct merchant mode - no aggregatorID included")

    return base_payload


def _encrypt_icici_payload(payload: dict, working_key: str) -> str:
    """Compute the ICICI secureHash (HMAC-SHA256) for initiateSale.

    According to the UAT KIT and successful tests, hash is calculated by:
    1. Using only mandatory fields (excluding empty optional fields)
    2. Sorting fields alphabetically
    3. Concatenating their values (no separators)
    4. Computing HMAC-SHA256 with the access_code key

    Note: Empty optional fields like addlParam1, addlParam2 are excluded from hash.
    """
    # Define mandatory fields for hash calculation
    mandatory_fields = [
        "aggregatorID", "amount", "currencyCode", "customerEmailID",
        "customerMobileNo", "merchantId", "merchantTxnNo", 
        "payType", "returnURL", "transactionType", "txnDate"
    ]
    
    # Include customerName only if it has a value
    if payload.get("customerName"):
        mandatory_fields.append("customerName")
    
    # Build hash string with only mandatory fields
    hash_values = []
    for field in sorted(mandatory_fields):
        if field in payload and payload[field] is not None:
            hash_values.append(str(payload[field]))
    
    string_to_sign = "".join(hash_values)
    
    # Compute HMAC-SHA256
    digest = hmac.new(
        working_key.encode("utf-8"),
        string_to_sign.encode("ascii"),
        hashlib.sha256
    ).hexdigest()
    
    # Temporary debug prints to help align with ICICI UAT
    try:
        print("ICICI_DEBUG_STRING_TO_SIGN:", string_to_sign)
        print("ICICI_DEBUG_HASH:", digest)
    except Exception:
        pass
    
    logger.debug(f"ICICI secureHash calculation | string_length={len(string_to_sign)} hash={digest}")
    
    try:
        logger.info(
            "ICICI secureHash computed | merchantId=%s merchantTxnNo=%s len_string=%d hash=%s",
            payload.get("merchantId"),
            payload.get("merchantTxnNo"),
            len(string_to_sign),
            digest,
        )
    except Exception:
        pass

    return digest


def get_payment_gateway_config(business_id):
    """Return (gateway, creds_dict) for the given business_id.

    Resolution order:
      1) This business's BusinessFinancial (JSON first, then legacy Razorpay columns)
      2) Master business's BusinessFinancial (same logic), when applicable
      3) Global Razorpay keys from settings as a final fallback
    """

    def _global_default():
        return BusinessFinancial.PAYMENT_GATEWAY_RAZORPAY, {
            "key_id": getattr(settings, "RAZORPAY_KEY_ID", None),
            "key_secret": getattr(settings, "RAZORPAY_KEY_SECRET", None),
        }

    try:
        business = Business.objects.get(business_id=business_id)
    except Business.DoesNotExist:
        return _global_default()

    # 1) Direct business financial configuration
    financial = getattr(business, "financial_config", None)
    if financial:
        gateway, creds = financial.get_gateway_config()
        normalized_gateway = (gateway or "").lower()
        if _gateway_config_looks_valid(normalized_gateway, creds):
            return normalized_gateway, creds

        # Razorpay legacy fallback: use individual columns if JSON is missing
        # but only when gateway is unset or explicitly Razorpay
        if not normalized_gateway or normalized_gateway == BusinessFinancial.PAYMENT_GATEWAY_RAZORPAY:
            legacy_creds = {
                "key_id": financial.razorpay_key_id,
                "key_secret": financial.razorpay_key_secret,
            }
            if _gateway_config_looks_valid(BusinessFinancial.PAYMENT_GATEWAY_RAZORPAY, legacy_creds):
                return BusinessFinancial.PAYMENT_GATEWAY_RAZORPAY, legacy_creds

    # 2) Master business fallback (only when current business is not itself master)
    if getattr(business, "master", None) and getattr(business, "level", "") != "Master Level":
        try:
            master_business = Business.objects.get(business_id=business.master)
        except Business.DoesNotExist:
            master_business = None

        if master_business is not None:
            master_financial = getattr(master_business, "financial_config", None)
            if master_financial:
                gateway, creds = master_financial.get_gateway_config()
                normalized_gateway = (gateway or "").lower()
                if _gateway_config_looks_valid(normalized_gateway, creds):
                    return normalized_gateway, creds

                if not normalized_gateway or normalized_gateway == BusinessFinancial.PAYMENT_GATEWAY_RAZORPAY:
                    legacy_creds = {
                        "key_id": master_financial.razorpay_key_id,
                        "key_secret": master_financial.razorpay_key_secret,
                    }
                    if _gateway_config_looks_valid(BusinessFinancial.PAYMENT_GATEWAY_RAZORPAY, legacy_creds):
                        return BusinessFinancial.PAYMENT_GATEWAY_RAZORPAY, legacy_creds

    # 3) Global default
    return _global_default()


def get_razorpay_keys(business_id):
    """Backwards-compatible helper to retrieve Razorpay keys for existing flows.

    Uses the generic get_payment_gateway_config() under the hood but always
    returns Razorpay keys, falling back to global settings when the configured
    gateway is not Razorpay or credentials are incomplete.
    """
    gateway, creds = get_payment_gateway_config(business_id)

    if gateway != BusinessFinancial.PAYMENT_GATEWAY_RAZORPAY:
        return (
            getattr(settings, "RAZORPAY_KEY_ID", None),
            getattr(settings, "RAZORPAY_KEY_SECRET", None),
        )

    key_id = creds.get("key_id")
    key_secret = creds.get("key_secret")

    if not _keys_look_valid(key_id, key_secret):
        return (
            getattr(settings, "RAZORPAY_KEY_ID", None),
            getattr(settings, "RAZORPAY_KEY_SECRET", None),
        )

    return key_id, key_secret


def finalize_payment_success(payment: Payments, rp_payment_id: str = None):
    """
    Idempotently mark a payment as success and confirm its order.
    - Updates payment.status to SUCCESS (if not already)
    - Stores provider payment id in-memory field for parity with existing code paths
    - Confirms order by setting Orders.status to 'confirmed' even if it was 'cancelled'
    - Sends user notification hook
    """
    try:
        # Update payment if needed
        if payment.status != Payments.Status.SUCCESS:
            payment.status = Payments.Status.SUCCESS
            if rp_payment_id:
                try:
                    # Not persisted (no DB field), but kept for parity with existing code
                    payment.payment_id = rp_payment_id  # type: ignore[attr-defined]
                except Exception:
                    pass
            payment.save()

        # Update order status when applicable
        if payment.order_id:
            try:
                order = Orders.objects.get(order_id=payment.order_id)
                # Move to pending if currently pending or cancelled (do not regress if progressed further)
                if order.status in [Orders.OrderStatus.PENDING, Orders.OrderStatus.CANCELLED]:
                    order.status = Orders.OrderStatus.PENDING
                    order.save()
                    try:
                        if order.user_id and getattr(order.user_id, 'user_id', None):
                            on_payment_success(int(order.user_id.user_id), int(order.order_id))
                    except Exception:
                        pass
                try:
                    _finalize_coupon_redemption_for_order(order)
                except Exception:
                    pass
            except Orders.DoesNotExist:
                logger.warning(f"Order {payment.order_id} not found for payment {getattr(payment, 'id', None)}")
    except Exception as ex:
        logger.error(f"finalize_payment_success error: {ex}")


@csrf_exempt
@swagger_auto_schema(methods=['POST'],tags=['Consumer'])
@api_view(['POST'])
def initiate_payment(request):
    """
    Initiate payment for an existing order
    Expects: { "order_id": int }
    """
    try:
        order_id = request.data.get('order_id')
        platform = request.data.get('platform')
        
        if not order_id:
            return Response(
                {'status': 'error', 'message': 'order_id is required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Get the order
        try:
            order = Orders.objects.select_related('user_id', 'business_id').get(order_id=order_id)
        except Orders.DoesNotExist:
            return Response(
                {'status': 'error', 'message': 'Order not found'},
                status=status.HTTP_404_NOT_FOUND
            )
        
        # Check if order is in valid state for payment
        # Allow PENDING, CONFIRMED, and CANCELLED orders to be paid (CANCELLED allows retry)
        valid_payment_statuses = [Orders.OrderStatus.PENDING, Orders.OrderStatus.CONFIRMED, Orders.OrderStatus.CANCELLED]
        if order.status not in valid_payment_statuses:
            return Response(
                {'status': 'error', 'message': f'Order is in {order.status} state and cannot be paid'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Determine configured payment gateway and credentials for this business
        gateway, creds = get_payment_gateway_config(order.business_id.business_id)

        if gateway == BusinessFinancial.PAYMENT_GATEWAY_RAZORPAY:
            # Prefer JSON/legacy credentials resolved by get_payment_gateway_config
            razorpay_key_id = creds.get('key_id')
            razorpay_key_secret = creds.get('key_secret')

            # Final safeguard using existing helper (includes global fallbacks)
            if not _keys_look_valid(razorpay_key_id, razorpay_key_secret):
                razorpay_key_id, razorpay_key_secret = get_razorpay_keys(order.business_id.business_id)

            if not razorpay_key_id or not razorpay_key_secret:
                return Response(
                    {'status': 'error', 'message': 'Payment gateway not configured for this business'},
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR
                )

            # Initialize Razorpay client
            razorpay_client = razorpay.Client(auth=(razorpay_key_id, razorpay_key_secret))

            # Create Razorpay order
            # Round final_amount to nearest rupee, then convert to paise
            rounded_amount_rupees = round(float(order.final_amount))
            amount_in_paise = int(rounded_amount_rupees * 100)

            razorpay_order_data = {
                'amount': amount_in_paise,  # Rounded amount in paise
                'currency': 'INR',
                'payment_capture': 1,  # Auto-capture payments
                'notes': {
                    'order_id': str(order.order_id),
                    'order_number': str(order.order_number),
                    'business_id': str(order.business_id.business_id),
                    'user_id': str(order.user_id.user_id) if order.user_id else 'guest'
                }
            }

            razorpay_order = razorpay_client.order.create(razorpay_order_data)

            # Create payment record in database
            payment = Payments.objects.create(
                user=order.user_id,
                business=order.business_id,
                amount=order.final_amount,
                payment_method=Payments.Method.RAZORPAY,
                status=Payments.Status.PENDING,
                transaction_id=razorpay_order['id'],
                payment_source=platform,
                currency='INR',
                order_id=order.order_id
            )

            # Prepare response data for frontend (unchanged contract)
            response_data = {
                'status': 'success',
                'data': {
                    'key': razorpay_key_id,
                    'amount': razorpay_order['amount'],
                    'order_id': razorpay_order['id'],
                    'name': f"{order.business_id.businessName} Order",
                    'description': f"Order #{order.order_number}",
                    'prefill': {
                        'name': f"{order.user_id.firstName} {order.user_id.lastName}" if order.user_id and hasattr(order.user_id, 'firstName') else '',
                        'email': order.user_id.emailID if order.user_id and hasattr(order.user_id, 'emailID') else '',
                        'contact': order.user_id.mobileNumber if order.user_id and hasattr(order.user_id, 'mobileNumber') else ''
                    },
                    'theme': {
                        'color': '#3399cc'
                    },
                    'modal': {
                        'ondismiss': 'function(){alert("Payment cancelled by user")}'
                    }
                },
                'payment_id': payment.id,
                'order_details': {
                    'order_id': order.order_id,
                    'order_number': str(order.order_number),
                    'final_amount': float(order.final_amount),
                    'business_name': order.business_id.businessName
                }
            }

            logger.info(f"Payment initiated for order {order.order_id}, Razorpay order: {razorpay_order['id']}")

            return Response(response_data, status=status.HTTP_200_OK)

        if gateway == BusinessFinancial.PAYMENT_GATEWAY_ICICI:
            # For initiateSale, use the access_code for secureHash calculation
            # The aggregator_secret is used only for status/refund APIs
            access_code = creds.get("access_code")
            aggregator_secret = creds.get("aggregator_secret")
            hash_key = access_code or aggregator_secret  # Use access_code if available, otherwise aggregator_secret

            icici_url = creds.get('payment_url') or getattr(settings, 'ICICI_PAYMENT_URL', None)

            if not _gateway_config_looks_valid(gateway, creds) or not icici_url or not hash_key:
                return Response(
                    {
                        'status': 'error',
                        'message': 'ICICI payment gateway is not correctly configured for this business',
                    },
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR,
                )

            # Build return URL for PayPhi to redirect the user back to after payment
            # Use the success endpoint that handles browser redirect
            try:
                return_url = request.build_absolute_uri('/kirazee/consumer/payment/success/')
            except Exception:
                return_url = getattr(settings, 'ICICI_RETURN_URL', None) or ''

            # Generate a unique merchant transaction number (exactly 20 chars as per spec)
            # Use order_id + current timestamp in milliseconds, then pad/trim to 20 characters.
            base_txn = f"{order.order_id}{int(time.time() * 1000)}"
            merchant_txn_no = (base_txn + "0" * 20)[:20]

            # Build payload according to PayPhi v2 initiateSale specification
            payload = _build_icici_payload(order, creds, merchant_txn_no, return_url)

            # Compute secureHash over documented sequence using access_code
            # For initiateSale, use the access_code as the HMAC key
            secure_hash = _encrypt_icici_payload(payload, hash_key)
            payload['secureHash'] = secure_hash  # ICICI expects camelCase in response
            
            # DEBUG: Explicit print statements that will show in production logs
            print(f"DEBUG_ICICI: payload before API call | order_id={order.order_id} | secureHash_length={len(secure_hash) if secure_hash else 0}")
            print(f"DEBUG_ICICI: aggregatorID in payload = {payload.get('aggregatorID')}")
            print(f"DEBUG_ICICI: secureHash value = {secure_hash}")
            print(f"DEBUG_ICICI: payload keys = {list(payload.keys())}")
            
            # Debug: Log the complete payload before sending
            logger.info(f"ICICI payload before API call | order_id={order.order_id} merchant_txn_no={merchant_txn_no} secureHash_length={len(secure_hash) if secure_hash else 0}")
            
            # Debug: Verify aggregatorID is in payload
            if 'aggregatorID' not in payload:
                logger.error(f"ICICI payload missing aggregatorID | order_id={order.order_id}")
            else:
                logger.info(f"ICICI payload aggregatorID | order_id={order.order_id} value={payload['aggregatorID']}")

            logger.info(
                "ICICI initiateSale payload constructed | order_id=%s merchant_txn_no=%s payload_keys=%s",
                order.order_id,
                merchant_txn_no,
                list(payload.keys()),
            )

            # Log full payload with secureHash redacted for debugging
            try:
                redacted_payload = dict(payload)
                if 'secureHash' in redacted_payload:
                    redacted_payload['secureHash'] = '***redacted***'
                logger.info(
                    "ICICI initiateSale request payload | order_id=%s merchant_txn_no=%s payload=%s",
                    order.order_id,
                    merchant_txn_no,
                    redacted_payload,
                )
            except Exception:
                pass

            # Call ICICI / PayPhi initiateSale v2 API from backend (server-to-server)
            try:
                request_data = json.dumps(payload).encode('utf-8')
                
                # DEBUG: Print exact request data being sent
                print(f"DEBUG_ICICI: API request data size = {len(request_data)}")
                print(f"DEBUG_ICICI: 'secureHash' in request payload = {'secureHash' in json.loads(request_data.decode('utf-8'))}")
                print(f"DEBUG_ICICI: 'securehash' in request payload = {'securehash' in json.loads(request_data.decode('utf-8'))}")
                print(f"DEBUG_ICICI: API request payload = {json.dumps(payload)}")
                
                # Debug: Log the exact request data being sent
                logger.info(f"ICICI API request | order_id={order.order_id} url={icici_url} data_size={len(request_data)}")
                
                http_request = urllib.request.Request(
                    icici_url,
                    data=request_data,
                    headers={'Content-Type': 'application/json'},
                    method='POST',
                )

                # Use default SSL context; adjust if UAT requires relaxed verification
                with urllib.request.urlopen(http_request, timeout=15) as http_response:
                    raw_body = http_response.read().decode('utf-8')
            except HTTPError as e:
                logger.error(
                    "ICICI initiateSale HTTPError | order_id=%s merchant_txn_no=%s status=%s body=%s",
                    order.order_id,
                    merchant_txn_no,
                    e.code,
                    getattr(e, 'read', lambda: b'')().decode('utf-8', errors='ignore'),
                )
                return Response(
                    {
                        'status': 'error',
                        'message': 'ICICI payment gateway is temporarily unavailable (HTTP error)',
                    },
                    status=status.HTTP_502_BAD_GATEWAY,
                )
            except URLError as e:
                logger.error(
                    "ICICI initiateSale URLError | order_id=%s merchant_txn_no=%s error=%s",
                    order.order_id,
                    merchant_txn_no,
                    str(e),
                )
                return Response(
                    {
                        'status': 'error',
                        'message': 'Unable to reach ICICI payment gateway. Please try again later.',
                    },
                    status=status.HTTP_502_BAD_GATEWAY,
                )
            except Exception as e:
                logger.error(
                    "ICICI initiateSale unexpected error | order_id=%s merchant_txn_no=%s error=%s",
                    order.order_id,
                    merchant_txn_no,
                    str(e),
                )
                return Response(
                    {
                        'status': 'error',
                        'message': 'Unexpected error while initiating ICICI payment',
                    },
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR,
                )

            # Parse ICICI response
            try:
                icici_resp = json.loads(raw_body)
            except json.JSONDecodeError:
                logger.error(
                    "ICICI initiateSale non-JSON response | order_id=%s merchant_txn_no=%s body=%s",
                    order.order_id,
                    merchant_txn_no,
                    raw_body,
                )
                return Response(
                    {
                        'status': 'error',
                        'message': 'Invalid response from ICICI payment gateway',
                    },
                    status=status.HTTP_502_BAD_GATEWAY,
                )

            response_code = icici_resp.get('responseCode') or icici_resp.get('response_code')
            resp_desc = icici_resp.get('respDescription') or icici_resp.get('resp_description') or ''

            if response_code != 'R1000':
                logger.error(
                    "ICICI initiateSale error response | order_id=%s merchant_txn_no=%s code=%s desc=%s",
                    order.order_id,
                    merchant_txn_no,
                    response_code,
                    resp_desc,
                )
                # Also log full response body for deeper debugging
                try:
                    logger.error(
                        "ICICI initiateSale full error response | order_id=%s merchant_txn_no=%s resp=%s",
                        order.order_id,
                        merchant_txn_no,
                        icici_resp,
                    )
                except Exception:
                    pass
                return Response(
                    {
                        'status': 'error',
                        'gateway': 'icici',
                        'message': f'ICICI payment gateway error: {response_code or "UNKNOWN"} - {resp_desc or "Unknown error"}',
                    },
                    status=status.HTTP_502_BAD_GATEWAY,
                )

            redirect_uri = icici_resp.get('redirectURI') or icici_resp.get('redirectUri')
            tran_ctx = icici_resp.get('tranCtx') or icici_resp.get('tranctx')

            if not redirect_uri or not tran_ctx:
                logger.error(
                    "ICICI initiateSale missing redirect data | order_id=%s merchant_txn_no=%s resp=%s",
                    order.order_id,
                    merchant_txn_no,
                    icici_resp,
                )
                return Response(
                    {
                        'status': 'error',
                        'gateway': 'icici',
                        'message': 'ICICI payment gateway response is incomplete (missing redirectURI/tranCtx)',
                    },
                    status=status.HTTP_502_BAD_GATEWAY,
                )

            # Create a pending payment record for tracking. For now we reuse the existing
            # RAZORPAY method choice; a dedicated ICICI method can be added later.
            payment = Payments.objects.create(
                user=order.user_id,
                business=order.business_id,
                amount=order.final_amount,
                payment_method=Payments.Method.RAZORPAY,  # TODO: introduce ICICI-specific method when schema changes are allowed
                status=Payments.Status.PENDING,
                transaction_id=merchant_txn_no,
                payment_source=platform,
                currency='INR',
                order_id=order.order_id,
            )

            response_data = {
                'status': 'success',
                'gateway': 'icici',
                'action': 'REDIRECT',
                'data': {
                    'url': redirect_uri,
                    'tranCtx': tran_ctx,
                },
                'payment_id': payment.id,
                'order_details': {
                    'order_id': order.order_id,
                    'order_number': str(order.order_number),
                    'final_amount': float(order.final_amount),
                    'business_name': order.business_id.businessName,
                },
            }

            logger.info(
                "ICICI payment initiation successful | order_id=%s merchant_txn_no=%s redirectURI=%s",
                order.order_id,
                merchant_txn_no,
                redirect_uri,
            )

            return Response(response_data, status=status.HTTP_200_OK)

        return Response(
            {
                'status': 'error',
                'message': f'Unsupported payment gateway: {gateway}',
            },
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )
        
    except Exception as e:
        logger.error(f"Error initiating payment: {str(e)}")
        return Response(
            {'status': 'error', 'message': f'Payment initiation failed: {str(e)}'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@csrf_exempt
@require_http_methods(["POST"])
def razorpay_webhook(request):
    """
    Handle Razorpay webhook notifications (server-to-server)
    This is the secure, reliable source of truth for payment confirmations
    """
    try:
        # Get webhook signature from headers
        webhook_signature = request.META.get('HTTP_X_RAZORPAY_SIGNATURE')
        if not webhook_signature:
            logger.error("Webhook signature missing in headers")
            return JsonResponse({'status': 'error', 'message': 'Signature missing'}, status=400)
        
        # Get raw request body
        webhook_body = request.body
        
        # Parse the webhook payload
        try:
            payload = json.loads(webhook_body.decode('utf-8'))
        except json.JSONDecodeError:
            logger.error("Invalid JSON in webhook payload")
            return JsonResponse({'status': 'error', 'message': 'Invalid JSON'}, status=400)
        
        # Extract event details
        event = payload.get('event')
        if not event:
            logger.error("No event type in webhook payload")
            return JsonResponse({'status': 'error', 'message': 'No event type'}, status=400)
        
        # We're primarily interested in payment.captured events
        if event != 'payment.captured':
            logger.info(f"Ignoring webhook event: {event}")
            return JsonResponse({'status': 'success', 'message': 'Event ignored'})
        
        # Extract payment data
        payment_entity = payload.get('payload', {}).get('payment', {}).get('entity', {})
        if not payment_entity:
            logger.error("No payment entity in webhook payload")
            return JsonResponse({'status': 'error', 'message': 'No payment data'}, status=400)
        
        razorpay_payment_id = payment_entity.get('id')
        razorpay_order_id = payment_entity.get('order_id')
        amount_paid = payment_entity.get('amount', 0) / 100  # Convert from paise to rupees
        
        if not razorpay_order_id:
            logger.error("No order_id in webhook payment data")
            return JsonResponse({'status': 'error', 'message': 'No order_id'}, status=400)
        
        # Find the payment record
        try:
            payment = Payments.objects.get(transaction_id=razorpay_order_id)
        except Payments.DoesNotExist:
            logger.error(f"Payment record not found for order_id: {razorpay_order_id}")
            return JsonResponse({'status': 'error', 'message': 'Payment record not found'}, status=404)
        
        # Get webhook secret for signature verification
        razorpay_key_id, razorpay_key_secret = get_razorpay_keys(payment.business.business_id)
        
        # Try to get webhook secret from BusinessFinancial
        webhook_secret = None
        try:
            business = payment.business
            if hasattr(business, 'financial_config'):
                webhook_secret = business.financial_config.razorpay_webhook_secret
            
            # Fallback to master business
            if not webhook_secret and business.master and business.level != 'Master Level':
                try:
                    master_business = Business.objects.get(business_id=business.master)
                    if hasattr(master_business, 'financial_config'):
                        webhook_secret = master_business.financial_config.razorpay_webhook_secret
                except Business.DoesNotExist:
                    pass
            
            # Fallback to settings
            if not webhook_secret:
                webhook_secret = getattr(settings, 'RAZORPAY_WEBHOOK_SECRET', None)
                
        except Exception as e:
            logger.error(f"Error getting webhook secret: {str(e)}")
        
        if not webhook_secret:
            logger.error("Webhook secret not configured")
            return JsonResponse({'status': 'error', 'message': 'Webhook secret not configured'}, status=500)
        
        # Verify webhook signature
        import hmac
        import hashlib
        
        expected_signature = hmac.new(
            webhook_secret.encode('utf-8'),
            webhook_body,
            hashlib.sha256
        ).hexdigest()
        
        if not hmac.compare_digest(webhook_signature, expected_signature):
            logger.error(f"Webhook signature verification failed for payment {razorpay_payment_id}")
            return JsonResponse({'status': 'error', 'message': 'Invalid signature'}, status=400)
        
        # Signature verified - this is a legitimate webhook from Razorpay
        logger.info(f"Webhook signature verified for payment {razorpay_payment_id}")
        
        # Update payment status if not already updated
        if payment.status != Payments.Status.SUCCESS:
            payment.status = Payments.Status.SUCCESS
            payment.save()
            logger.info(f"Payment {payment.id} status updated to SUCCESS via webhook")
        
        # Find and update the corresponding order
        try:
            # Get order from payment notes or find by matching criteria
            order_notes = payment_entity.get('notes', {})
            order_id = order_notes.get('order_id')
            
            if order_id:
                order = Orders.objects.get(order_id=order_id)
            else:
                # Fallback: find order by matching user, business, and amount
                order = Orders.objects.get(
                    user_id=payment.user,
                    business_id=payment.business,
                    final_amount=payment.amount,
                    status__in=[Orders.OrderStatus.PENDING]
                )
                
        except Orders.DoesNotExist:
            logger.warning(f"Could not find order for payment {payment.id} via webhook")
        except Orders.MultipleObjectsReturned:
            logger.warning(f"Multiple orders found for payment {payment.id} via webhook")
        else:
            try:
                _finalize_coupon_redemption_for_order(order)
            except Exception:
                pass
        
        return JsonResponse({
            'status': 'success',
            'message': 'Webhook processed successfully'
        })
        
    except Exception as e:
        logger.error(f"Error processing webhook: {str(e)}")
        return JsonResponse({
            'status': 'error',
            'message': 'Webhook processing failed'
        }, status=500)


@csrf_exempt
@require_http_methods(["POST"])
def payment_callback(request):
    """
    Handle Razorpay payment callback from frontend
    This provides immediate user feedback but webhook is the source of truth
    """
    try:
        # Parse the request body
        payload = json.loads(request.body.decode('utf-8'))
        
        # Extract payment details
        razorpay_payment_id = payload.get('razorpay_payment_id')
        razorpay_order_id = payload.get('razorpay_order_id')
        razorpay_signature = payload.get('razorpay_signature')
        
        if not all([razorpay_payment_id, razorpay_order_id, razorpay_signature]):
            return JsonResponse({
                'status': 'error',
                'message': 'Missing required payment parameters'
            }, status=400)
        
        # Find the payment record
        try:
            payment = Payments.objects.get(transaction_id=razorpay_order_id)
        except Payments.DoesNotExist:
            return JsonResponse({
                'status': 'error',
                'message': 'Payment record not found'
            }, status=404)
        
        # Get Razorpay keys for verification
        razorpay_key_id, razorpay_key_secret = get_razorpay_keys(payment.business.business_id)
        
        if not razorpay_key_secret:
            return JsonResponse({
                'status': 'error',
                'message': 'Payment verification failed - configuration error'
            }, status=500)
        
        # Initialize Razorpay client for verification
        razorpay_client = razorpay.Client(auth=(razorpay_key_id, razorpay_key_secret))
        
        # Verify payment signature
        try:
            razorpay_client.utility.verify_payment_signature({
                'razorpay_order_id': razorpay_order_id,
                'razorpay_payment_id': razorpay_payment_id,
                'razorpay_signature': razorpay_signature
            })
            
            # Frontend verification successful - update payment status for test mode
            # In production, webhook will be the source of truth
            logger.info(f"Frontend payment verification successful for {razorpay_payment_id}")
            
            # Check if we're in test mode (test keys start with rzp_test_)
            if razorpay_key_id and razorpay_key_id.startswith('rzp_test_'):
                # Update payment and confirm order immediately for test mode
                finalize_payment_success(payment, razorpay_payment_id)
            
            return JsonResponse({
                'status': 'success',
                'message': 'Payment verified successfully'
            })
            
        except razorpay.errors.SignatureVerificationError:
            # Payment verification failed
            logger.error(f"Frontend payment signature verification failed for {razorpay_payment_id}")
            
            return JsonResponse({
                'status': 'error',
                'message': 'Payment verification failed'
            }, status=400)
            
    except Exception as e:
        logger.error(f"Error in payment callback: {str(e)}")
        return JsonResponse({
            'status': 'error',
            'message': 'Payment processing failed'
        }, status=500)


@csrf_exempt
@require_http_methods(["POST"])
def payment_webhook(request):
    """
    Handle Razorpay webhook - This is the source of truth for payment status
    """
    try:
        # Get webhook signature from headers
        webhook_signature = request.META.get('HTTP_X_RAZORPAY_SIGNATURE')
        webhook_body = request.body

        # Parse webhook payload early to determine business and select the right secret
        try:
            payload = json.loads(webhook_body.decode('utf-8'))
        except json.JSONDecodeError:
            logger.error("Invalid JSON in webhook payload")
            return JsonResponse({'status': 'error', 'message': 'Invalid JSON'}, status=400)

        event = payload.get('event')
        
        if event == 'payment.captured':
            # Payment successful
            payment_entity = payload.get('payload', {}).get('payment', {}).get('entity', {})
            razorpay_payment_id = payment_entity.get('id')
            razorpay_order_id = payment_entity.get('order_id')
            amount = payment_entity.get('amount', 0) / 100  # Convert from paise to rupees
        else:
            # For other events, still try to get payment entity if available
            payment_entity = payload.get('payload', {}).get('payment', {}).get('entity', {})
            razorpay_payment_id = payment_entity.get('id') if payment_entity else None
            razorpay_order_id = payment_entity.get('order_id') if payment_entity else None
            amount = None

        # Resolve webhook secret per business using the payment's business
        webhook_secret = None
        payment = None
        try:
            if razorpay_order_id:
                payment = Payments.objects.get(transaction_id=razorpay_order_id)
                business = payment.business
                if hasattr(business, 'financial_config'):
                    webhook_secret = business.financial_config.razorpay_webhook_secret
                if not webhook_secret and business.master and business.level != 'Master Level':
                    try:
                        master_business = Business.objects.get(business_id=business.master)
                        if hasattr(master_business, 'financial_config'):
                            webhook_secret = master_business.financial_config.razorpay_webhook_secret
                    except Business.DoesNotExist:
                        pass
        except Payments.DoesNotExist:
            logger.warning(f"Payment record not found for order_id in webhook: {razorpay_order_id}")

        # Fallback to global settings if no per-business secret found
        if not webhook_secret:
            webhook_secret = getattr(settings, 'RAZORPAY_WEBHOOK_SECRET', None)

        if not webhook_signature or not webhook_secret:
            logger.error("Webhook signature or secret missing")
            return JsonResponse({'status': 'error'}, status=400)

        # Verify webhook signature
        expected_signature = hmac.new(
            webhook_secret.encode('utf-8'),
            webhook_body,
            hashlib.sha256
        ).hexdigest()

        if not hmac.compare_digest(webhook_signature, expected_signature):
            logger.error("Webhook signature verification failed")
            return JsonResponse({'status': 'error'}, status=400)

        
        if event == 'payment.captured':
            # Payment successful
            if razorpay_order_id:
                try:
                    # Update payment and confirm order via shared helper
                    payment = payment or Payments.objects.get(transaction_id=razorpay_order_id)
                    finalize_payment_success(payment, razorpay_payment_id)
                except Payments.DoesNotExist as e:
                    logger.error(f"Payment not found for webhook: {str(e)}")
                    
        elif event == 'payment.failed':
            # Payment failed
            payment_entity = payload.get('payload', {}).get('payment', {}).get('entity', {})
            razorpay_order_id = payment_entity.get('order_id')
            
            if razorpay_order_id:
                try:
                    # Update payment status
                    payment = Payments.objects.get(transaction_id=razorpay_order_id)
                    payment.status = Payments.Status.FAILED
                    payment.save()
                    # Cancel the linked order if present
                    if payment.order_id:
                        try:
                            order = Orders.objects.get(order_id=payment.order_id)
                            if order.status != Orders.OrderStatus.CANCELLED:
                                order.status = Orders.OrderStatus.CANCELLED
                                order.save()
                        except Orders.DoesNotExist:
                            pass
                    
                    logger.info(f"Payment {razorpay_order_id} marked as failed")
                    
                except Payments.DoesNotExist:
                    logger.error(f"Payment not found for failed webhook: {razorpay_order_id}")
        elif event and event.startswith('refund.'):
            # Refund lifecycle events from Razorpay dashboard or API
            refund_entity = payload.get('payload', {}).get('refund', {}).get('entity', {})
            payment_entity = payload.get('payload', {}).get('payment', {}).get('entity', {})
            provider_refund_id = refund_entity.get('id')
            provider_payment_id = refund_entity.get('payment_id') or (payment_entity.get('id') if payment_entity else None)
            order_provider_id = payment_entity.get('order_id') if payment_entity else None
            amount_paise = refund_entity.get('amount')
            currency = refund_entity.get('currency') or (payment_entity.get('currency') if payment_entity else 'INR')

            # Map event to local status
            if event == 'refund.created':
                refund_status = 'processing'
            elif event in ('refund.processed', 'refund.succeeded'):
                refund_status = 'completed'
            elif event == 'refund.failed':
                refund_status = 'failed'
            else:
                refund_status = 'processing'

            payment = None
            # Prefer match by Razorpay order_id stored in our transaction_id
            if order_provider_id:
                try:
                    payment = Payments.objects.get(transaction_id=order_provider_id)
                except Payments.DoesNotExist:
                    payment = None

            # If we couldn't find via order_id, try fetching the payment from Razorpay to obtain order_id
            if not payment and provider_payment_id:
                try:
                    # Try to get business id from notes to fetch keys correctly
                    notes = payment_entity.get('notes', {}) if payment_entity else {}
                    biz_id = notes.get('business_id')
                    key_id, key_secret = get_razorpay_keys(biz_id) if biz_id else (getattr(settings, 'RAZORPAY_KEY_ID', None), getattr(settings, 'RAZORPAY_KEY_SECRET', None))
                    if key_id and key_secret:
                        client = razorpay.Client(auth=(key_id, key_secret))
                        rp_payment = client.payment.fetch(provider_payment_id)
                        ord_id = rp_payment.get('order_id')
                        if ord_id:
                            try:
                                payment = Payments.objects.get(transaction_id=ord_id)
                            except Payments.DoesNotExist:
                                payment = None
                except Exception as ex:
                    logger.error(f"Failed to map refund to local payment: {ex}")

            if payment:
                try:
                    payment.refund_status = refund_status
                    if provider_refund_id:
                        payment.refund_id = provider_refund_id
                    payment.save()
                except Exception as ex:
                    logger.error(f"Failed updating payment refund fields: {ex}")

                # Also insert a row into order_refunds if not present
                try:
                    with connection.cursor() as cursor:
                        cursor.execute("SELECT refund_id FROM order_refunds WHERE provider_refund_id = %s LIMIT 1", [provider_refund_id])
                        exists = cursor.fetchone()
                        if not exists:
                            refund_amount_rupees = None
                            if isinstance(amount_paise, int):
                                refund_amount_rupees = str(Decimal(amount_paise) / Decimal('100'))
                            provider_response_json = json.dumps(payload)
                            cursor.execute(
                                """
                                INSERT INTO order_refunds (
                                    order_system, order_id, business_id, user_id,
                                    payment_method, provider_payment_id,
                                    requested_amount, refund_amount, currency,
                                    reason, initiated_by, refund_mode,
                                    status, provider_refund_id, provider_response,
                                    email_sent, created_at, updated_at
                                ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,CAST(%s AS JSON),%s,NOW(),NOW())
                                """,
                                [
                                    'standard',
                                    payment.order_id,
                                    getattr(payment.business, 'business_id', None),
                                    getattr(payment.user, 'user_id', None),
                                    payment.payment_method,
                                    provider_payment_id,
                                    refund_amount_rupees,  # requested_amount unknown; store equal to refund
                                    refund_amount_rupees,
                                    currency or 'INR',
                                    None,
                                    None,
                                    'gateway',
                                    refund_status,
                                    provider_refund_id,
                                    provider_response_json,
                                    0,
                                ],
                            )
                except Exception as ex:
                    logger.error(f"Failed inserting order_refunds row: {ex}")

        
        return JsonResponse({'status': 'ok'})
        
    except Exception as e:
        logger.error(f"Webhook processing error: {str(e)}")
        return JsonResponse({'status': 'error'}, status=500)


@csrf_exempt
@swagger_auto_schema(methods=['POST'],tags=['Consumer'])
@api_view(['POST'])
def verify_payment_manual(request):
    """
    Manual payment verification endpoint for test environments
    Allows updating payment status when webhooks aren't available
    """
    try:
        razorpay_payment_id = request.data.get('razorpay_payment_id')
        razorpay_order_id = request.data.get('razorpay_order_id')
        
        if not razorpay_payment_id or not razorpay_order_id:
            return Response({
                'status': 'error',
                'message': 'Payment ID and Order ID are required'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Find the payment record
        try:
            payment = Payments.objects.get(transaction_id=razorpay_order_id)
        except Payments.DoesNotExist:
            return Response({
                'status': 'error',
                'message': 'Payment record not found'
            }, status=status.HTTP_404_NOT_FOUND)
        
        # Get Razorpay keys
        razorpay_key_id, razorpay_key_secret = get_razorpay_keys(payment.business.business_id)
        
        # Only allow manual verification for test keys
        if not razorpay_key_id or not razorpay_key_id.startswith('rzp_test_'):
            return Response({
                'status': 'error',
                'message': 'Manual verification only allowed for test keys'
            }, status=status.HTTP_403_FORBIDDEN)
        
        # Initialize Razorpay client to verify payment exists
        razorpay_client = razorpay.Client(auth=(razorpay_key_id, razorpay_key_secret))
        
        try:
            # Fetch payment details from Razorpay
            payment_details = razorpay_client.payment.fetch(razorpay_payment_id)
            
            if payment_details.get('status') == 'captured':
                # Update payment and confirm order
                finalize_payment_success(payment, razorpay_payment_id)
                return Response({
                    'status': 'success',
                    'message': 'Payment verified and updated successfully'
                })
            else:
                return Response({
                    'status': 'error',
                    'message': f'Payment status is {payment_details.get("status")}, not captured'
                }, status=status.HTTP_400_BAD_REQUEST)
                
        except Exception as e:
            logger.error(f"Error fetching payment from Razorpay: {str(e)}")
            return Response({
                'status': 'error',
                'message': 'Failed to verify payment with Razorpay'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
            
    except Exception as e:
        logger.error(f"Error in manual payment verification: {str(e)}")
        return Response({
            'status': 'error',
            'message': 'Payment verification failed'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@csrf_exempt
def payment_page(request):
    """Render the payment page, routing to the correct gateway template."""
    order_id = request.GET.get('order_id')

    # Debug: trace entry into payment_page
    print(f"[payment_page] Called with order_id={order_id}")
    logger.info(f"payment_page called with order_id={order_id}")

    if not order_id:
        return render(request, 'order_payment.html', {
            'error': 'Order ID is missing. Please try again from your orders page.'
        })

    try:
        order = Orders.objects.select_related('business_id').get(order_id=order_id)
        print(f"[payment_page] Found order_id={order_id}, business_id={order.business_id.business_id}")
        logger.info(
            "payment_page order loaded | order_id=%s business_id=%s status=%s",
            order_id,
            getattr(order.business_id, 'business_id', None),
            getattr(order, 'status', None),
        )
    except Orders.DoesNotExist:
        print(f"[payment_page] Order not found for order_id={order_id}")
        logger.warning(f"payment_page: Order not found for order_id={order_id}")
        return render(request, 'order_payment.html', {
            'error': 'Order not found. Please try again from your orders page.'
        })

    # Ensure order is in a state that can be paid
    if order.status not in [Orders.OrderStatus.PENDING, Orders.OrderStatus.CONFIRMED, Orders.OrderStatus.CANCELLED]:
        print(f"[payment_page] Order {order_id} in non-payable status={order.status}")
        logger.info("payment_page: order_id=%s non-payable status=%s", order_id, order.status)
        return render(request, 'order_payment.html', {
            'error': f'Order is in {order.status} state and cannot be paid. Please contact support.'
        })

    # Default template is the existing Razorpay-based page
    template_name = 'order_payment.html'

    try:
        business_id = order.business_id.business_id
        print(f"[payment_page] Resolving gateway for business_id={business_id}")
        logger.info("payment_page: resolving gateway for business_id=%s", business_id)

        gateway, _creds = get_payment_gateway_config(business_id)
        print(f"[payment_page] get_payment_gateway_config returned gateway={gateway} for business_id={business_id}")
        logger.info(
            "payment_page: gateway resolved | business_id=%s gateway=%s template_before=%s",
            business_id,
            gateway,
            template_name,
        )

        if gateway == BusinessFinancial.PAYMENT_GATEWAY_ICICI:
            template_name = 'order_payment_icici.html'
            print(f"[payment_page] Using ICICI template for business_id={business_id}")
            logger.info("payment_page: using ICICI template for business_id=%s", business_id)
        else:
            print(f"[payment_page] Using Razorpay template for business_id={business_id} (gateway={gateway})")
            logger.info(
                "payment_page: using Razorpay template for business_id=%s gateway=%s",
                business_id,
                gateway,
            )
    except Exception as e:
        print(f"[payment_page] Error resolving gateway for order_id={order_id}: {e}")
        logger.error(f"payment_page: failed to resolve gateway for order {order_id}: {e}")

    print(f"[payment_page] Final template for order_id={order_id} is {template_name}")
    logger.info("payment_page: rendering template=%s for order_id=%s", template_name, order_id)

    return render(request, template_name, {
        'order_id': order_id
    })


@csrf_exempt
@swagger_auto_schema(methods=['POST'],tags=['Consumer'])
@require_http_methods(["POST"])
@api_view(['POST'])
def handle_icici_payment_advice_web(request):
    """
    Handle ICICI payment advice (callback) sent to returnURL
    Returns JSON response for frontend polling instead of HTML redirect
    """
    try:
        logger.info("ICICI payment advice received for web")
        logger.debug(f"Request headers: {dict(request.headers)}")
        logger.debug(f"Request content type: {request.content_type}")
        
        # Additional security: Check if request is from ICICI server
        user_agent = request.headers.get('User-Agent', '')
        # ICICI typically uses specific User-Agent patterns
        if not any(icici_ua in user_agent.lower() for icici_ua in ['icici', 'payphi', 'java', 'apache-httpclient']):
            logger.warning(f"Suspicious request to ICICI advice endpoint from User-Agent: {user_agent}")
            return Response({
                'status': 'error',
                'message': 'Invalid request source'
            }, status=status.HTTP_403_FORBIDDEN)
        
        # Parse form data
        if request.content_type == 'application/x-www-form-urlencoded':
            data = request.POST.dict()
        else:
            data = request.data if hasattr(request, 'data') else {}
        
        logger.info(f"ICICI advice data: {data}")
        
        # Extract key fields from ICICI response
        response_code = data.get('responseCode') or data.get('response_code')
        resp_description = data.get('respDescription') or data.get('resp_description') or ''
        merchant_id = data.get('merchantId')
        merchant_txn_no = data.get('merchantTxnNo')
        txn_id = data.get('txnID')
        payment_mode = data.get('paymentMode')
        payment_inst_id = data.get('paymentInstId')
        amount = data.get('amount')
        currency = data.get('currency')
        
        logger.info(f"ICICI response: code={response_code}, merchant_txn_no={merchant_txn_no}, txn_id={txn_id}")
        
        if not merchant_txn_no:
            logger.error("ICICI advice missing merchantTxnNo")
            return Response({
                'status': 'error',
                'message': 'Missing merchant transaction number'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Find payment record by merchant transaction number
        try:
            payment = Payments.objects.get(transaction_id=merchant_txn_no)
            logger.info(f"Found payment record: payment_id={payment.id}, current_status={payment.status}")
        except Payments.DoesNotExist:
            logger.error(f"Payment not found for merchant_txn_no: {merchant_txn_no}")
            return Response({
                'status': 'error',
                'message': 'Payment record not found'
            }, status=status.HTTP_404_NOT_FOUND)
        
        # Check if payment is already processed
        if payment.status == Payments.Status.SUCCESS:
            logger.info(f"Payment {payment.id} already marked as success")
            return Response({
                'status': 'success',
                'message': 'Payment already processed',
                'payment_id': payment.id,
                'order_id': payment.order_id,
                'payment_status': 'success',
                'transaction_id': payment.transaction_id,
                'payment_mode': getattr(payment, 'payment_mode', None)
            })
        
        # Process payment based on response code
        if response_code in ['0000', '0']:  # SUCCESS
            try:
                # Update payment status to success
                payment.status = Payments.Status.SUCCESS
                payment.transaction_id = txn_id  # Update with actual transaction ID
                if payment_mode:
                    payment.payment_mode = payment_mode
                payment.save()
                
                logger.info(f"Payment {payment.id} marked as success")
                
                # Update order status
                try:
                    from .models import Orders
                    order = Orders.objects.get(order_id=payment.order_id)
                    if order.status in [Orders.OrderStatus.PENDING, Orders.OrderStatus.CONFIRMED]:
                        order.status = Orders.OrderStatus.CONFIRMED
                        order.save()
                        logger.info(f"Order {order.order_id} status updated to CONFIRMED")
                except Orders.DoesNotExist:
                    logger.warning(f"Order not found for order_id: {payment.order_id}")
                except Exception as e:
                    logger.error(f"Error updating order status: {str(e)}", exc_info=True)
                
                return Response({
                    'status': 'success',
                    'message': 'Payment processed successfully',
                    'payment_id': payment.id,
                    'order_id': payment.order_id,
                    'payment_status': 'success',
                    'transaction_id': txn_id,
                    'payment_mode': payment_mode,
                    'amount': amount,
                    'currency': currency
                })
                
            except Exception as e:
                logger.error(f"Error updating payment success: {str(e)}", exc_info=True)
                return Response({
                    'status': 'error',
                    'message': 'Failed to update payment status'
                }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        
        else:  # FAILURE
            try:
                # Update payment status to failed
                payment.status = Payments.Status.FAILED
                if hasattr(payment, 'failure_reason'):
                    payment.failure_reason = resp_description
                payment.save()
                
                logger.info(f"Payment {payment.id} marked as failed: {resp_description}")
                
                # Update order status
                try:
                    from .models import Orders
                    order = Orders.objects.get(order_id=payment.order_id)
                    if order.status == Orders.OrderStatus.PENDING:
                        order.status = Orders.OrderStatus.CANCELLED
                        order.save()
                        logger.info(f"Order {order.order_id} status updated to CANCELLED")
                except Orders.DoesNotExist:
                    logger.warning(f"Order not found for order_id: {payment.order_id}")
                except Exception as e:
                    logger.error(f"Error updating order status: {str(e)}", exc_info=True)
                
                return Response({
                    'status': 'failed',
                    'message': 'Payment failed',
                    'payment_id': payment.id,
                    'order_id': payment.order_id,
                    'payment_status': 'failed',
                    'error_message': resp_description,
                    'response_code': response_code
                })
                
            except Exception as e:
                logger.error(f"Error updating payment failure: {str(e)}", exc_info=True)
                return Response({
                    'status': 'error',
                    'message': 'Failed to update payment status'
                }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        
    except Exception as e:
        logger.error(f"Unexpected error in ICICI payment advice: {str(e)}", exc_info=True)
        return Response({
            'status': 'error',
            'message': 'Internal server error'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@csrf_exempt
@swagger_auto_schema(methods=['POST'],tags=['Consumer'])
@api_view(['POST'])
def handle_icici_payment_advice(request):
    """
    Handle ICICI payment advice (callback) sent to returnURL
    ICICI sends POST as application/x-www-form-urlencoded with payment details
    """
    try:
        logger.info("ICICI payment advice received")
        logger.debug(f"Request headers: {dict(request.headers)}")
        logger.debug(f"Request content type: {request.content_type}")
        
        # Parse form data
        if request.content_type == 'application/x-www-form-urlencoded':
            data = request.POST.dict()
        else:
            data = request.data if hasattr(request, 'data') else {}
        
        logger.info(f"ICICI advice data: {data}")
        
        # Extract key fields from ICICI response
        response_code = data.get('responseCode') or data.get('response_code')
        resp_description = data.get('respDescription') or data.get('resp_description') or ''
        merchant_id = data.get('merchantId')
        merchant_txn_no = data.get('merchantTxnNo')
        txn_id = data.get('txnID')
        payment_mode = data.get('paymentMode')
        amount = data.get('amount')
        
        # Log the full response for debugging
        logger.info(
            f"ICICI payment advice | code={response_code} desc={resp_description} "
            f"merchant={merchant_id} txn_no={merchant_txn_no} txn_id={txn_id} "
            f"mode={payment_mode} amount={amount}"
        )
        
        if response_code == '0000' or response_code == '0':  # Success
            # Find the payment record using merchantTxnNo
            payment = None
            try:
                # Try to find by merchantTxnNo first
                logger.info(f"Looking for payment with merchantTxnNo: {merchant_txn_no}")
                payment = Payments.objects.filter(
                    transaction_id=merchant_txn_no  # Exact match, not icontains
                ).first()
                
                if not payment:
                    logger.warning(f"Payment not found for txn_no: {merchant_txn_no}")
                    # Try to find by order_id if available
                    order_id = data.get('order_id')
                    if order_id:
                        logger.info(f"Looking for payment with order_id: {order_id}")
                        payment = Payments.objects.filter(
                            order_id__order_id=order_id
                        ).first()
                        if payment:
                            logger.info(f"Found payment via order_id: {payment.id}")
                        else:
                            logger.warning(f"Payment not found for order_id: {order_id}")
                
                if not payment:
                    logger.error(f"Payment not found for txn_no: {merchant_txn_no} or order_id")
                    return JsonResponse({
                        'status': 'error',
                        'message': 'Payment record not found'
                    }, status=404)
                
                # Update payment status
                if payment.status != Payments.Status.SUCCESS:
                    logger.info(f"Updating payment {payment.id} status to SUCCESS")
                    payment.status = Payments.Status.SUCCESS
                    payment.transaction_id = txn_id  # Save the actual transaction ID from ICICI
                    payment.payment_mode = payment_mode  # Save payment mode (UPI, Card, etc.)
                    payment.save()
                    logger.info(f"Payment {payment.id} updated successfully")
                    
                    # Update order status
                    if payment.order_id:
                        order = payment.order_id
                        if order.status == Orders.OrderStatus.PENDING:
                            logger.info(f"Updating order {order.id} status to CONFIRMED")
                            order.status = Orders.OrderStatus.CONFIRMED
                            order.save()
                            logger.info(f"Order {order.id} updated successfully")
                    
                    logger.info(f"Payment {payment.id} marked as SUCCESS via ICICI advice")
                else:
                    logger.info(f"Payment {payment.id} already marked as SUCCESS")
                    
            except Exception as e:
                logger.error(f"Error updating payment status: {str(e)}")
                logger.error(f"Exception details:", exc_info=True)
                return JsonResponse({
                    'status': 'error',
                    'message': 'Error updating payment status'
                }, status=500)
            
            # Return success response
            # For ICICI, we need to redirect to success page
            # Since ICICI sends POST, we can't directly redirect, so we'll return JavaScript
            stored_platform = (getattr(payment, 'payment_source', None) or 'web').lower()

            if stored_platform == 'web':
                frontend_url = os.environ.get('BASE_URL')
                success_url = f"{frontend_url}/#/order-acknowledgment?order_id={payment.order_id}"
            else:
                success_url = f"{request.build_absolute_uri('/kirazee/consumer/payment/')}?order_id={payment.order_id}&payment_status=success&platform={stored_platform}&payment_id={payment.id}"
            
            return HttpResponse(f"""
                <html>
                <head><title>Payment Successful</title></head>
                <body>
                    <script>
                        window.location.href = '{success_url}';
                    </script>
                    <p>Redirecting to payment success page...</p>
                </body>
                </html>
            """, content_type='text/html')
            
        else:
            # Payment failed
            logger.error(f"ICICI payment failed: {response_code} - {resp_description}")
            
            # Find and update payment as failed
            try:
                logger.info(f"Looking for failed payment with merchantTxnNo: {merchant_txn_no}")
                payment = Payments.objects.filter(
                    transaction_id=merchant_txn_no  # Exact match, not icontains
                ).first()
                
                if payment:
                    logger.info(f"Found payment: {payment.id} with status: {payment.status}")
                    payment.status = Payments.Status.FAILED
                    payment.failure_reason = resp_description
                    payment.save()
                    logger.info(f"Payment {payment.id} marked as FAILED")
                    
                    # Update order status
                    if payment.order_id:
                        order = payment.order_id
                        if order.status not in [Orders.OrderStatus.CANCELLED, Orders.OrderStatus.DELIVERED]:
                            logger.info(f"Updating order {order.id} status to CANCELLED")
                            order.status = Orders.OrderStatus.CANCELLED
                            order.save()
                            logger.info(f"Order {order.id} updated successfully")
                    
                    logger.info(f"Payment {payment.id} marked as FAILED via ICICI advice")
                else:
                    logger.error(f"Payment not found for failed txn_no: {merchant_txn_no}")
                    
            except Exception as e:
                logger.error(f"Error updating failed payment: {str(e)}")
                logger.error(f"Exception details:", exc_info=True)
            
            # Return error response and redirect to failure page
            stored_platform = (getattr(payment, 'payment_source', None) or 'web').lower() if payment else 'web'

            if stored_platform == 'web':
                frontend_url = os.environ.get('BASE_URL')
                failure_url = f"{frontend_url}/#/order-acknowledgment?order_id={payment.order_id if payment else ''}&status=failed&error={resp_description}"
            else:
                failure_url = f"{request.build_absolute_uri('/kirazee/consumer/payment/')}?order_id={payment.order_id if payment else ''}&payment_status=failed&platform={stored_platform}&error={resp_description}&payment_id={payment.id if payment else ''}"
            
            return HttpResponse(f"""
                <html>
                <head><title>Payment Failed</title></head>
                <body>
                    <script>
                        window.location.href = '{failure_url}';
                    </script>
                    <p>Redirecting to payment failure page...</p>
                </body>
                </html>
            """, content_type='text/html')
            
    except Exception as e:
        logger.error(f"Error in ICICI payment advice handler: {str(e)}")
        return JsonResponse({
            'status': 'error',
            'message': 'Error processing payment advice'
        }, status=500)


@swagger_auto_schema(methods=['GET', 'POST'],tags=['Consumer'])
@api_view(['GET', 'POST'])
def payment_success_page(request):
    """
    Display payment success page to the user
    """
    try:
        order_id = request.GET.get('order_id')
        payment_id = request.GET.get('payment_id')
        
        logger.info(f"Success page: order_id={order_id}, payment_id={payment_id}")
        
        # Fetch payment details from database
        payment = None
        order = None
        if payment_id:
            try:
                payment = Payments.objects.get(id=payment_id)
                order = payment.order_id
                logger.info(f"Found payment by ID: {payment.id}, order: {order.order_id if order else 'None'}")
            except Payments.DoesNotExist:
                logger.error(f"Payment not found with ID: {payment_id}")
                pass
        elif order_id:
            try:
                order = Orders.objects.get(order_id=order_id)
                payment = Payments.objects.filter(order_id=order).first()
                logger.info(f"Found payment by order_id: {payment.id if payment else 'None'}")
            except Orders.DoesNotExist:
                logger.error(f"Order not found: {order_id}")
                pass
        
        context = {
            'order_id': order_id,
            'payment_id': payment_id,
            'amount': str(payment.amount) if payment else '0',
            'business_id': str(order.business_id.business_id) if order and order.business_id else 'N/A',
            'user_id': str(order.user_id.user_id) if order and getattr(order, 'user_id', None) else '',
            'is_android': request.GET.get('platform') == 'android'
        }
        
        logger.info(f"Payment success page context: {context}")
        
        return render(request, 'payment_success.html', context)
        
    except Exception as e:
        logger.error(f"Error in payment success page: {str(e)}")
        return render(request, 'payment_success.html', {'error': True})


@swagger_auto_schema(methods=['GET', 'POST'],tags=['Consumer'])
@api_view(['GET', 'POST'])
def payment_failure_page(request):
    """
    Display payment failure page to the user
    """
    try:
        order_id = request.GET.get('order_id')
        error_message = request.GET.get('error', 'Payment failed')
        
        context = {
            'order_id': order_id,
            'error_message': error_message,
            'is_android': request.GET.get('platform') == 'android'
        }
        
        logger.info(f"Payment failure page accessed: order_id={order_id}, error={error_message}")
        
        return render(request, 'payment_cancel.html', context)
        
    except Exception as e:
        logger.error(f"Error in payment failure page: {str(e)}")
        return render(request, 'payment_cancel.html', {'error': True})


@swagger_auto_schema(methods=['POST'],tags=['Consumer'])
@api_view(['POST'])
def payment_success(request):
    """
    Handle successful payment confirmation from frontend or ICICI callback
    """
    try:
        # Check if this is an ICICI payment advice (callback)
        if request.content_type == 'application/x-www-form-urlencoded':
            # Process ICICI payment advice inline
            try:
                logger.info("ICICI payment advice received for web")
                logger.debug(f"Request headers: {dict(request.headers)}")
                logger.debug(f"Request content type: {request.content_type}")
                
                # Parse form data
                if request.content_type == 'application/x-www-form-urlencoded':
                    data = request.POST.dict()
                else:
                    data = request.data if hasattr(request, 'data') else {}
                
                logger.info(f"ICICI advice data: {data}")
                
                # Extract key fields from ICICI response
                response_code = data.get('responseCode') or data.get('response_code')
                resp_description = data.get('respDescription') or data.get('resp_description') or ''
                merchant_id = data.get('merchantId')
                merchant_txn_no = data.get('merchantTxnNo')
                txn_id = data.get('txnID')
                payment_mode = data.get('paymentMode')
                payment_inst_id = data.get('paymentInstId')
                amount = data.get('amount')
                currency = data.get('currency')
                
                logger.info(f"ICICI response: code={response_code}, merchant_txn_no={merchant_txn_no}, txn_id={txn_id}")
                
                if not merchant_txn_no:
                    logger.error("ICICI advice missing merchantTxnNo")
                    return Response({
                        'status': 'error',
                        'message': 'Missing merchant transaction number'
                    }, status=status.HTTP_400_BAD_REQUEST)
                
                # Find payment record by merchant transaction number
                try:
                    payment = Payments.objects.get(transaction_id=merchant_txn_no)
                    logger.info(f"Found payment record: payment_id={payment.id}, current_status={payment.status}")
                except Payments.DoesNotExist:
                    logger.error(f"Payment not found for merchant_txn_no: {merchant_txn_no}")
                    return Response({
                        'status': 'error',
                        'message': 'Payment record not found'
                    }, status=status.HTTP_404_NOT_FOUND)
                
                # Check if payment is already processed
                if payment.status == Payments.Status.SUCCESS:
                    logger.info(f"Payment {payment.id} already marked as success")
                    order_id = payment.order_id
                    stored_platform = (getattr(payment, 'payment_source', None) or 'web').lower()
                    if stored_platform == 'web':
                        frontend_url = os.environ.get('BASE_URL')
                        redirect_url = f"{frontend_url}/#/order-acknowledgment?order_id={order_id}"
                    else:
                        redirect_url = f"{request.build_absolute_uri('/kirazee/consumer/payment/')}?order_id={order_id}&payment_status=success&platform={stored_platform}&payment_id={payment.id}"

                    return HttpResponse(f"""
                        <script>
                            window.location.href = '{redirect_url}';
                        </script>
                    """, content_type='text/html')
                
                # Process payment based on response code
                if response_code in ['0000', '0']:  # SUCCESS
                    try:
                        # Update payment status to success
                        payment.status = Payments.Status.SUCCESS
                        payment.transaction_id = txn_id  # Update with actual transaction ID
                        if payment_mode:
                            payment.payment_mode = payment_mode
                        payment.save()
                        
                        logger.info(f"Payment {payment.id} marked as success")
                        
                        # Update order status
                        try:
                            from .models import Orders
                            order = Orders.objects.get(order_id=payment.order_id)
                            if order.status in [Orders.OrderStatus.PENDING, Orders.OrderStatus.CONFIRMED]:
                                order.status = Orders.OrderStatus.CONFIRMED
                                order.save()
                                logger.info(f"Order {order.order_id} status updated to CONFIRMED")
                        except Orders.DoesNotExist:
                            logger.warning(f"Order not found for order_id: {payment.order_id}")
                        except Exception as e:
                            logger.error(f"Error updating order status: {str(e)}", exc_info=True)
                        
                        order_id = payment.order_id
                        stored_platform = (getattr(payment, 'payment_source', None) or 'web').lower()
                        if stored_platform == 'web':
                            frontend_url = os.environ.get('BASE_URL')
                            redirect_url = f"{frontend_url}/#/order-acknowledgment?order_id={order_id}"
                        else:
                            redirect_url = f"{request.build_absolute_uri('/kirazee/consumer/payment/')}?order_id={order_id}&payment_status=success&platform={stored_platform}&payment_id={payment.id}"

                        return HttpResponse(f"""
                            <script>
                                window.location.href = '{redirect_url}';
                            </script>
                        """, content_type='text/html')
                        
                    except Exception as e:
                        logger.error(f"Error updating payment success: {str(e)}", exc_info=True)
                        return Response({
                            'status': 'error',
                            'message': 'Failed to update payment status'
                        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
                
                else:  # FAILURE
                    try:
                        # Update payment status to failed
                        payment.status = Payments.Status.FAILED
                        if hasattr(payment, 'failure_reason'):
                            payment.failure_reason = resp_description
                        payment.save()
                        
                        logger.info(f"Payment {payment.id} marked as failed: {resp_description}")
                        
                        # Update order status
                        try:
                            from .models import Orders
                            order = Orders.objects.get(order_id=payment.order_id)
                            if order.status == Orders.OrderStatus.PENDING:
                                order.status = Orders.OrderStatus.CANCELLED
                                order.save()
                                logger.info(f"Order {order.order_id} status updated to CANCELLED")
                        except Orders.DoesNotExist:
                            logger.warning(f"Order not found for order_id: {payment.order_id}")
                        except Exception as e:
                            logger.error(f"Error updating order status: {str(e)}", exc_info=True)
                        
                        order_id = payment.order_id
                        stored_platform = (getattr(payment, 'payment_source', None) or 'web').lower()
                        if stored_platform == 'web':
                            frontend_url = os.environ.get('BASE_URL')
                            redirect_url = f"{frontend_url}/#/order-acknowledgment?order_id={order_id}&status=failed&error={resp_description}"
                        else:
                            redirect_url = f"{request.build_absolute_uri('/kirazee/consumer/payment/')}?order_id={order_id}&payment_status=failed&platform={stored_platform}&error={resp_description}&payment_id={payment.id}"

                        return HttpResponse(f"""
                            <script>
                                window.location.href = '{redirect_url}';
                            </script>
                        """, content_type='text/html')
                        
                    except Exception as e:
                        logger.error(f"Error updating payment failure: {str(e)}", exc_info=True)
                        return Response({
                            'status': 'error',
                            'message': 'Failed to update payment status'
                        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
                
            except Exception as e:
                logger.error(f"Unexpected error in ICICI payment advice: {str(e)}", exc_info=True)
                return Response({
                    'status': 'error',
                    'message': 'Internal server error'
                }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        
        # Otherwise, handle Razorpay payment success
        razorpay_payment_id = request.data.get('razorpay_payment_id')
        razorpay_order_id = request.data.get('razorpay_order_id')
        razorpay_signature = request.data.get('razorpay_signature')
        
        # This endpoint can be used for additional processing after payment success
        # The main verification should happen in payment_callback
        
        return Response({
            'status': 'success',
            'message': 'Payment processed successfully',
            'redirect_url': '/account/orders/'  # Redirect to orders page
        })
        
    except Exception as e:
        logger.error(f"Error in payment success handler: {str(e)}")
        return Response({
            'status': 'error',
            'message': 'Error processing payment confirmation'
        }, status=500)


@swagger_auto_schema(methods=['POST'],tags=['Consumer'])
@api_view(['POST'])
def payment_failure(request):
    """
    Handle payment failure from frontend
    """
    try:
        razorpay_order_id = request.data.get('razorpay_order_id')
        error_description = request.data.get('error_description', 'Payment failed')
        
        if razorpay_order_id:
            try:
                payment = Payments.objects.get(transaction_id=razorpay_order_id)
                payment.status = Payments.Status.FAILED
                payment.save()
                # Also cancel the order if linked
                if payment.order_id:
                    try:
                        order = Orders.objects.get(order_id=payment.order_id)
                        if order.status != Orders.OrderStatus.CANCELLED:
                            order.status = Orders.OrderStatus.CANCELLED
                            order.save()
                    except Orders.DoesNotExist:
                        pass
            except Payments.DoesNotExist:
                pass
        
        return Response({
            'status': 'error',
            'message': error_description,
            'redirect_url': '/'  # Redirect to orders page
        })
        
    except Exception as e:
        logger.error(f"Error in payment failure handler: {str(e)}")
        return Response({
            'status': 'error',
            'message': 'Error processing payment failure'
        }, status=500)