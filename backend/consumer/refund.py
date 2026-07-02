from decimal import Decimal
import json
from django.conf import settings
from django.db import connection, transaction
from django.utils import timezone
from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework import status
import razorpay
from django.core.mail import send_mail
from django.template.loader import render_to_string
from drf_yasg.utils import swagger_auto_schema
from django.utils.html import strip_tags
from .models import Orders, Payments, WalletPoints
from .gro_models import GroceriesOrders, GroceriesPayments


def _dictfetchone(cursor):
    row = cursor.fetchone()
    if row is None:
        return None
    columns = [col[0] for col in cursor.description]
    return dict(zip(columns, row))


def _insert_order_refund(data):
    with connection.cursor() as cursor:
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
                data.get("order_system"), data.get("order_id"), data.get("business_id"), data.get("user_id"),
                data.get("payment_method"), data.get("provider_payment_id"),
                str(data.get("requested_amount")), str(data.get("refund_amount")) if data.get("refund_amount") is not None else None, data.get("currency", "INR"),
                data.get("reason"), data.get("initiated_by"), data.get("refund_mode"),
                data.get("status", "initiated"), data.get("provider_refund_id"), json.dumps(data.get("provider_response")) if data.get("provider_response") is not None else json.dumps({}),
                1 if data.get("email_sent") else 0,
            ],
        )
        refund_id = cursor.lastrowid
    return refund_id


def _get_existing_refund(order_system, order_id, provider_payment_id):
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT * FROM order_refunds
            WHERE order_system = %s AND order_id = %s AND provider_payment_id = %s
            ORDER BY created_at DESC
            LIMIT 1
            """,
            [order_system, order_id, provider_payment_id],
        )
        return _dictfetchone(cursor)


def _send_refund_email(email, amount):
    try:
        subject = "Payment Refund Processed"
        html_message = render_to_string("refund_email_template.html", {"amount": amount})
        plain_message = strip_tags(html_message)
        from_email = getattr(settings, "DEFAULT_FROM_EMAIL", None)
        if not from_email:
            from_email = getattr(settings, "EMAIL_HOST_USER", None)
        if not from_email:
            return False
        send_mail(subject, plain_message, from_email, [email], html_message=html_message)
        return True
    except Exception:
        return False


def _get_user_email(reg):
    try:
        email = getattr(reg, "emailID", None)
        if not email:
            email = getattr(reg, "email", None)
        return email
    except Exception:
        return None


def _compute_wallet_points_for_amount(business_id, amount):
    try:
        from .models import PointsConfiguration
        cfg = PointsConfiguration.objects.filter(business_id_id=business_id).first()
        rupee_per_point = Decimal(str(cfg.points_per_rupee_value)) if cfg else Decimal("0.10")
        if rupee_per_point <= 0:
            rupee_per_point = Decimal("0.10")
        pts = (Decimal(str(amount)) / rupee_per_point).quantize(Decimal("0.01"))
        return pts
    except Exception:
        return (Decimal(str(amount)) / Decimal("0.10")).quantize(Decimal("0.01"))


@swagger_auto_schema(methods=['POST'],tags=['Consumer'])
@api_view(["POST"])
@transaction.atomic
def initiate_order_refund(request):
    try:
        order_system = str(request.data.get("order_system", "")).lower()
        order_id = request.data.get("order_id")
        amount = request.data.get("amount")
        reason = request.data.get("reason")
        initiated_by = request.data.get("performed_by") or request.data.get("initiated_by")
        send_email = bool(request.data.get("send_email", True))
        if not order_system or order_system not in ("standard", "grocery"):
            return Response({"success": False, "error": "order_system must be 'standard' or 'grocery'"}, status=status.HTTP_400_BAD_REQUEST)
        if not order_id:
            return Response({"success": False, "error": "order_id is required"}, status=status.HTTP_400_BAD_REQUEST)
        gateway_client = razorpay.Client(auth=(settings.RAZORPAY_KEY_ID, settings.RAZORPAY_KEY_SECRET))
        if order_system == "standard":
            order = Orders.objects.select_related("user_id", "business_id").get(order_id=order_id)
            paid_payment = Payments.objects.filter(order_id=order_id, status="success").order_by("-created_at").first()
            business_id = order.business_id.business_id
            user = order.user_id
            user_email = _get_user_email(user) if user else None
            currency = "INR"
            if not paid_payment:
                existing = Payments.objects.filter(order_id=order_id, status__in=["pending", "initiated"]).exists()
                if existing:
                    data = {
                        "order_system": "standard",
                        "order_id": order_id,
                        "business_id": business_id,
                        "user_id": int(user.user_id) if user else None,
                        "payment_method": None,
                        "provider_payment_id": None,
                        "requested_amount": Decimal(str(amount or 0)),
                        "refund_amount": None,
                        "currency": currency,
                        "reason": reason,
                        "initiated_by": initiated_by,
                        "refund_mode": "not_applicable",
                        "status": "not_applicable",
                        "provider_refund_id": None,
                        "provider_response": {"note": "No captured payment; pending attempts were cancelled"},
                        "email_sent": False,
                    }
                    rid = _insert_order_refund(data)
                    return Response({"success": True, "message": "No captured payment; nothing to refund", "data": {"refund_id": rid, "status": "not_applicable"}}, status=status.HTTP_200_OK)
                return Response({"success": False, "error": "No successful payment found for this order"}, status=status.HTTP_400_BAD_REQUEST)
            provider_payment_id = paid_payment.transaction_id
            method = paid_payment.payment_method
            requested_amount = Decimal(str(amount)) if amount else Decimal(str(paid_payment.amount))
            existing_ref = _get_existing_refund("standard", order_id, provider_payment_id)
            if existing_ref and existing_ref.get("status") in ("initiated", "processing", "completed"):
                return Response({"success": True, "message": "Refund already in-progress or completed", "data": existing_ref}, status=status.HTTP_200_OK)
            if method == "razorpay":
                r = gateway_client.payment.refund(provider_payment_id, int(Decimal(str(requested_amount)) * 100))
                paid_payment.refund_status = r.get("status")
                paid_payment.refund_id = r.get("id")
                paid_payment.save(update_fields=["refund_status", "refund_id", "updated_at"])
                refund_amount = Decimal(str(r.get("amount", 0))) / Decimal("100")
                data = {
                    "order_system": "standard",
                    "order_id": order_id,
                    "business_id": business_id,
                    "user_id": int(user.user_id) if user else None,
                    "payment_method": method,
                    "provider_payment_id": provider_payment_id,
                    "requested_amount": requested_amount,
                    "refund_amount": refund_amount,
                    "currency": r.get("currency", currency),
                    "reason": reason,
                    "initiated_by": initiated_by,
                    "refund_mode": "gateway",
                    "status": "completed" if r.get("status") in ("processed", "completed") else r.get("status", "processing"),
                    "provider_refund_id": r.get("id"),
                    "provider_response": r,
                    "email_sent": _send_refund_email(user_email, refund_amount) if (send_email and user_email) else False,
                }
                rid = _insert_order_refund(data)
                return Response({"success": True, "message": "Refund processed", "data": {"refund_id": rid, **{k: (str(v) if isinstance(v, Decimal) else v) for k, v in data.items() if k != "provider_response"}}}, status=status.HTTP_200_OK)
            elif method == "wallet":
                pts = _compute_wallet_points_for_amount(business_id, requested_amount)
                WalletPoints.atomic_transaction(
                    user_id=user,
                    points=pts,
                    transaction_type=WalletPoints.TransactionType.REFUNDED,
                    description=f"Refund for order {order_id}",
                    related_order=order,
                )
                data = {
                    "order_system": "standard",
                    "order_id": order_id,
                    "business_id": business_id,
                    "user_id": int(user.user_id) if user else None,
                    "payment_method": method,
                    "provider_payment_id": provider_payment_id,
                    "requested_amount": requested_amount,
                    "refund_amount": requested_amount,
                    "currency": currency,
                    "reason": reason,
                    "initiated_by": initiated_by,
                    "refund_mode": "wallet",
                    "status": "completed",
                    "provider_refund_id": None,
                    "provider_response": {"wallet_points_credited": str(pts)},
                    "email_sent": _send_refund_email(user_email, requested_amount) if (send_email and user_email) else False,
                }
                rid = _insert_order_refund(data)
                return Response({"success": True, "message": "Wallet refund completed", "data": {"refund_id": rid}}, status=status.HTTP_200_OK)
            elif method == "cod":
                data = {
                    "order_system": "standard",
                    "order_id": order_id,
                    "business_id": business_id,
                    "user_id": int(user.user_id) if user else None,
                    "payment_method": method,
                    "provider_payment_id": provider_payment_id,
                    "requested_amount": requested_amount,
                    "refund_amount": None,
                    "currency": currency,
                    "reason": reason,
                    "initiated_by": initiated_by,
                    "refund_mode": "manual",
                    "status": "not_applicable",
                    "provider_refund_id": None,
                    "provider_response": {"note": "COD refund to be handled offline"},
                    "email_sent": False,
                }
                rid = _insert_order_refund(data)
                return Response({"success": True, "message": "COD refund recorded for offline handling", "data": {"refund_id": rid}}, status=status.HTTP_200_OK)
            else:
                return Response({"success": False, "error": f"Unsupported payment method: {method}"}, status=status.HTTP_400_BAD_REQUEST)
        else:
            order = GroceriesOrders.objects.select_related("user", "business").get(order_id=order_id)
            paid_payment = GroceriesPayments.objects.filter(order=order, payment_status="completed").order_by("-payment_date").first()
            business_id = order.business.business_id
            user = order.user
            user_email = _get_user_email(user) if user else None
            currency = "INR"
            if not paid_payment:
                existing = GroceriesPayments.objects.filter(order=order, payment_status__in=["pending"]).exists()
                if existing:
                    data = {
                        "order_system": "grocery",
                        "order_id": order_id,
                        "business_id": business_id,
                        "user_id": int(user.user_id) if user else None,
                        "payment_method": None,
                        "provider_payment_id": None,
                        "requested_amount": Decimal(str(amount or 0)),
                        "refund_amount": None,
                        "currency": currency,
                        "reason": reason,
                        "initiated_by": initiated_by,
                        "refund_mode": "not_applicable",
                        "status": "not_applicable",
                        "provider_refund_id": None,
                        "provider_response": {"note": "No captured payment; pending attempts were cancelled"},
                        "email_sent": False,
                    }
                    rid = _insert_order_refund(data)
                    return Response({"success": True, "message": "No captured payment; nothing to refund", "data": {"refund_id": rid, "status": "not_applicable"}}, status=status.HTTP_200_OK)
                return Response({"success": False, "error": "No successful payment found for this grocery order"}, status=status.HTTP_400_BAD_REQUEST)
            provider_payment_id = paid_payment.transaction_id
            method = paid_payment.payment_method
            requested_amount = Decimal(str(amount)) if amount else Decimal(str(paid_payment.amount))
            existing_ref = _get_existing_refund("grocery", order_id, provider_payment_id)
            if existing_ref and existing_ref.get("status") in ("initiated", "processing", "completed"):
                return Response({"success": True, "message": "Refund already in-progress or completed", "data": existing_ref}, status=status.HTTP_200_OK)
            if method == "razorpay":
                r = gateway_client.payment.refund(provider_payment_id, int(Decimal(str(requested_amount)) * 100))
                paid_payment.payment_status = "refunded"
                paid_payment.save(update_fields=["payment_status"])
                refund_amount = Decimal(str(r.get("amount", 0))) / Decimal("100")
                data = {
                    "order_system": "grocery",
                    "order_id": order_id,
                    "business_id": business_id,
                    "user_id": int(user.user_id) if user else None,
                    "payment_method": method,
                    "provider_payment_id": provider_payment_id,
                    "requested_amount": requested_amount,
                    "refund_amount": refund_amount,
                    "currency": r.get("currency", currency),
                    "reason": reason,
                    "initiated_by": initiated_by,
                    "refund_mode": "gateway",
                    "status": "completed" if r.get("status") in ("processed", "completed") else r.get("status", "processing"),
                    "provider_refund_id": r.get("id"),
                    "provider_response": r,
                    "email_sent": _send_refund_email(user_email, refund_amount) if (send_email and user_email) else False,
                }
                rid = _insert_order_refund(data)
                return Response({"success": True, "message": "Refund processed", "data": {"refund_id": rid, **{k: (str(v) if isinstance(v, Decimal) else v) for k, v in data.items() if k != "provider_response"}}}, status=status.HTTP_200_OK)
            elif method == "wallet":
                pts = _compute_wallet_points_for_amount(business_id, requested_amount)
                WalletPoints.atomic_transaction(
                    user_id=user,
                    points=pts,
                    transaction_type=WalletPoints.TransactionType.REFUNDED,
                    description=f"Refund for grocery order {order_id}",
                )
                data = {
                    "order_system": "grocery",
                    "order_id": order_id,
                    "business_id": business_id,
                    "user_id": int(user.user_id) if user else None,
                    "payment_method": method,
                    "provider_payment_id": provider_payment_id,
                    "requested_amount": requested_amount,
                    "refund_amount": requested_amount,
                    "currency": currency,
                    "reason": reason,
                    "initiated_by": initiated_by,
                    "refund_mode": "wallet",
                    "status": "completed",
                    "provider_refund_id": None,
                    "provider_response": {"wallet_points_credited": str(pts)},
                    "email_sent": _send_refund_email(user_email, requested_amount) if (send_email and user_email) else False,
                }
                rid = _insert_order_refund(data)
                return Response({"success": True, "message": "Wallet refund completed", "data": {"refund_id": rid}}, status=status.HTTP_200_OK)
            elif method == "cod":
                data = {
                    "order_system": "grocery",
                    "order_id": order_id,
                    "business_id": business_id,
                    "user_id": int(user.user_id) if user else None,
                    "payment_method": method,
                    "provider_payment_id": provider_payment_id,
                    "requested_amount": requested_amount,
                    "refund_amount": None,
                    "currency": currency,
                    "reason": reason,
                    "initiated_by": initiated_by,
                    "refund_mode": "manual",
                    "status": "not_applicable",
                    "provider_refund_id": None,
                    "provider_response": {"note": "COD refund to be handled offline"},
                    "email_sent": False,
                }
                rid = _insert_order_refund(data)
                return Response({"success": True, "message": "COD refund recorded for offline handling", "data": {"refund_id": rid}}, status=status.HTTP_200_OK)
            else:
                return Response({"success": False, "error": f"Unsupported payment method: {method}"}, status=status.HTTP_400_BAD_REQUEST)
    except Orders.DoesNotExist:
        return Response({"success": False, "error": "Order not found"}, status=status.HTTP_404_NOT_FOUND)
    except GroceriesOrders.DoesNotExist:
        return Response({"success": False, "error": "Grocery order not found"}, status=status.HTTP_404_NOT_FOUND)
    except razorpay.errors.BadRequestError as e:
        return Response({"success": False, "error": str(e)}, status=status.HTTP_400_BAD_REQUEST)
    except Exception as e:
        return Response({"success": False, "error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@swagger_auto_schema(methods=['GET'],tags=['Consumer'])
@api_view(["GET"])
def get_refund_status(request):
    refund_id = request.query_params.get("refund_id")
    order_system = request.query_params.get("order_system")
    order_id = request.query_params.get("order_id")
    if not refund_id and not (order_system and order_id):
        return Response({"success": False, "error": "Provide refund_id or (order_system and order_id)"}, status=status.HTTP_400_BAD_REQUEST)
    with connection.cursor() as cursor:
        if refund_id:
            cursor.execute("SELECT * FROM order_refunds WHERE refund_id = %s LIMIT 1", [refund_id])
            row = _dictfetchone(cursor)
        else:
            cursor.execute(
                """
                SELECT * FROM order_refunds
                WHERE order_system = %s AND order_id = %s
                ORDER BY created_at DESC
                LIMIT 1
                """,
                [order_system, order_id],
            )
            row = _dictfetchone(cursor)
    if not row:
        return Response({"success": False, "error": "Refund record not found"}, status=status.HTTP_404_NOT_FOUND)
    try:
        if isinstance(row.get("provider_response"), (bytes, bytearray)):
            row["provider_response"] = json.loads(row["provider_response"].decode("utf-8"))
        elif isinstance(row.get("provider_response"), str):
            row["provider_response"] = json.loads(row["provider_response"])
    except Exception:
        pass
    return Response({"success": True, "data": row}, status=status.HTTP_200_OK)


@swagger_auto_schema(methods=['GET'],tags=['Consumer'])
@api_view(["GET"])
def list_order_refunds(request):
    order_system = request.query_params.get("order_system")
    order_id = request.query_params.get("order_id")
    page = max(1, int(request.query_params.get("page", 1)))
    limit = max(1, min(100, int(request.query_params.get("limit", 20))))
    offset = (page - 1) * limit
    if not order_system or not order_id:
        return Response({"success": False, "error": "order_system and order_id are required"}, status=status.HTTP_400_BAD_REQUEST)
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT COUNT(*) AS cnt FROM order_refunds WHERE order_system = %s AND order_id = %s",
            [order_system, order_id],
        )
        total = cursor.fetchone()[0]
        cursor.execute(
            """
            SELECT * FROM order_refunds
            WHERE order_system = %s AND order_id = %s
            ORDER BY created_at DESC
            LIMIT %s OFFSET %s
            """,
            [order_system, order_id, limit, offset],
        )
        columns = [col[0] for col in cursor.description]
        rows = [dict(zip(columns, r)) for r in cursor.fetchall()]
    for r in rows:
        try:
            if isinstance(r.get("provider_response"), (bytes, bytearray)):
                r["provider_response"] = json.loads(r["provider_response"].decode("utf-8"))
            elif isinstance(r.get("provider_response"), str):
                r["provider_response"] = json.loads(r["provider_response"])
        except Exception:
            pass
    total_pages = (total + limit - 1) // limit if total else 1
    return Response(
        {
            "success": True,
            "pagination": {
                "total": total,
                "current_page": page,
                "per_page": limit,
                "total_pages": total_pages,
                "has_next_page": page < total_pages,
                "has_prev_page": page > 1,
            },
            "data": rows,
        },
        status=status.HTTP_200_OK,
    )
