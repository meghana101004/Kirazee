from rest_framework.decorators import api_view, parser_classes
from rest_framework.parsers import JSONParser, MultiPartParser, FormParser
from rest_framework.response import Response
from rest_framework import status
from django.utils import timezone
from django.db import transaction, IntegrityError
from django.db.models import Q, Count
from django.conf import settings
from django.core.files.base import ContentFile
from django.shortcuts import get_object_or_404
from drf_yasg.utils import swagger_auto_schema
from drf_yasg import openapi
from django.urls import reverse
import os
import uuid
import logging
from business.image_utils import build_s3_file_url
from django.core.mail import EmailMultiAlternatives, send_mail
from notifications.service import send_order_notification

from kirazee_app.models import Registration, Business, BusinessMapping, BusinessType, BusinessFinancial
from .models import BusinessApplication, ApplicationStep, ApplicationDocument, AdminReview, ReviewReasonTemplate, CustomReviewReason
import re

# Configure logger
logger = logging.getLogger(__name__)


def _generate_application_id(user_id: int) -> str:
    now = timezone.now()
    return f"APP_KIR{now.strftime('%Y%m%d')}_{user_id}_{now.strftime('%H%M%S%f')}_{uuid.uuid4().hex[:6].upper()}"


def _generate_document_id() -> str:
    return f"DOC_{uuid.uuid4().hex[:10].upper()}"


def _get_application_business_name(app) -> str:
    s1 = ApplicationStep.objects.filter(application=app, step_number=1).first()
    name = None
    if s1 and s1.step_data:
        try:
            name = s1.step_data.get("business_name")
        except Exception:
            name = None
    return name or f"Business_{app.user.user_id}"


@swagger_auto_schema(method='GET', tags=['Business'])
@api_view(["GET"])  # /kirazee/api/v1/business-onboarding/progress/<int:user_id>
def get_user_progress(request, user_id: int):
    try:
        user = Registration.objects.get(user_id=user_id, status=True)
    except Registration.DoesNotExist:
        return Response({"error": "Invalid user_id"}, status=status.HTTP_404_NOT_FOUND)

    app = (BusinessApplication.objects.filter(user=user)
            .order_by('-created_at')
            .first())

    if not app:
        return Response({
            "success": True,
            "data": {
                "user_id": user_id,
                "current_step": 1,
                "completed_steps": [],
                "total_steps": 3,
                "application_id": None,
                "status": "not_started",
                "last_updated": None,
                "step_data": {
                    "step_1": {"completed": False, "data_saved": False},
                    "step_2": {"completed": False, "data_saved": False},
                    "step_3": {"completed": False, "data_saved": False},
                }
            }
        })

    steps = {s.step_number: s for s in ApplicationStep.objects.filter(application=app)}
    completed_steps = [n for n, s in steps.items() if s.is_completed]

    data = {
        "user_id": user_id,
        "current_step": app.current_step,
        "completed_steps": sorted(completed_steps),
        "total_steps": app.total_steps,
        "application_id": app.application_id,
        "status": app.status,
        "last_updated": app.updated_at.isoformat() if app.updated_at else None,
        "step_data": {
            "step_1": {
                "completed": steps.get(1).is_completed if steps.get(1) else False,
                "completed_at": steps.get(1).completed_at.isoformat() if (steps.get(1) and steps.get(1).completed_at) else None,
                "data_saved": steps.get(1).data_saved if steps.get(1) else False,
            },
            "step_2": {
                "completed": steps.get(2).is_completed if steps.get(2) else False,
                "completed_at": steps.get(2).completed_at.isoformat() if (steps.get(2) and steps.get(2).completed_at) else None,
                "data_saved": steps.get(2).data_saved if steps.get(2) else False,
            },
            "step_3": {
                "completed": steps.get(3).is_completed if steps.get(3) else False,
                "completed_at": steps.get(3).completed_at.isoformat() if (steps.get(3) and steps.get(3).completed_at) else None,
                "data_saved": steps.get(3).data_saved if steps.get(3) else False,
            }
        }
    }
    return Response({"success": True, "data": data})


@swagger_auto_schema(method='GET', tags=['Business'])
@api_view(["GET"])  # /kirazee/api/v1/business-onboarding/application/<str:application_id>/details
def application_details(request, application_id: str):
    """
    Aggregates onboarding details for a single application_id:
    - step1 fields (user-entered)
    - step2 documents (uploads + missing list)
    - step3 data (preferences)
    - application status and metadata
    """
    app = get_object_or_404(BusinessApplication, application_id=application_id)

    # Step 1 data
    s1 = ApplicationStep.objects.filter(application=app, step_number=1).first()
    step1 = (s1.step_data or {}) if s1 else {}
    if s1 and s1.updated_at:
        step1["last_updated"] = s1.updated_at.isoformat()

    # Step 2 documents
    docs_qs = ApplicationDocument.objects.filter(application=app).order_by("-uploaded_at")
    documents = []
    for d in docs_qs:
        documents.append({
            "document_id": d.document_id,
            "document_type": d.document_type,
            "file_name": d.file_name,
            "status": d.upload_status,
            "verification_status": d.verification_status,
            "upload_url": build_s3_file_url(d.file),
            "uploaded_at": d.uploaded_at.isoformat() if d.uploaded_at else None,
        })
    required_documents = ["identity_proof", "business_registration", "store_photo", "bank_proof"]
    uploaded_types = set(d.document_type for d in docs_qs)
    missing_documents = [t for t in required_documents if t not in uploaded_types]

    step2 = {
        "documents": documents,
        "required_documents": required_documents,
        "missing_documents": missing_documents,
        "all_uploaded": len(missing_documents) == 0
    }

    # Step 3 data
    s3 = ApplicationStep.objects.filter(application=app, step_number=3).first()
    step3 = (s3.step_data or {}) if s3 else {}
    if s3 and s3.updated_at:
        step3["last_updated"] = s3.updated_at.isoformat()

    # Status & review
    review = AdminReview.objects.filter(application=app).order_by('-reviewed_at').first()
    # Compute display status: pending for in_progress/submitted, otherwise reflect actual terminal or change-required states
    status_out = (
        "required_changes" if app.status == "requires_changes" else
        ("rejected" if app.status == "rejected" else
         ("approved" if app.status == "approved" else "pending"))
    )

    status_payload = {
        "application_id": app.application_id,
        "status": status_out,
        "submitted_at": app.submitted_at.isoformat() if app.submitted_at else None,
        "last_updated": app.updated_at.isoformat() if app.updated_at else None,
        "review_progress": {
            "documents_reviewed": False if not review else review.action in ["approve", "reject", "request_changes"],
            "business_verified": True if (review and review.action == "approve") else False,
            "admin_assigned": bool(review)
        },
        "admin_comments": [] if not review else ([review.comments] if review.comments else []),
        # Only include reasons/changes when the CURRENT status matches
        "rejection_reasons": [] if app.status != "rejected" else ((review.rejection_reasons or []) if review else []),
        "required_changes": [] if app.status != "requires_changes" else ((review.required_changes or []) if review else []),
        "approval_details": None
    }

    return Response({
        "success": True,
        "data": {
            "application_id": app.application_id,
            "user_id": app.user.user_id,
            "current_step": app.current_step,
            "total_steps": app.total_steps,
            "step1": step1,
            "step2": step2,
            "step3": step3,
            "status": status_payload
        }
    })


@swagger_auto_schema(method='POST', tags=['Business'])
@api_view(["POST"])  # /kirazee/api/v1/business-onboarding/initialize
@parser_classes([JSONParser])
def initialize_application(request):
    user_id = request.data.get("user_id")
    resume_existing = bool(request.data.get("resume_existing", True))

    if not user_id:
        return Response({"error": "user_id is required"}, status=status.HTTP_400_BAD_REQUEST)

    try:
        user = Registration.objects.get(user_id=user_id, status=True)
    except Registration.DoesNotExist:
        return Response({"error": "Invalid user_id"}, status=status.HTTP_404_NOT_FOUND)

    with transaction.atomic():
        # Lock the user row to serialize concurrent initializations for the same user
        user_locked = Registration.objects.select_for_update().get(user_id=user.user_id, status=True)

        # Re-check for existing application within the same transaction
        existing = (
            BusinessApplication.objects.select_for_update()
            .filter(user=user_locked)
            .exclude(status__in=["approved"])
            .order_by('-created_at')
            .first()
        )

        if existing and resume_existing:
            # Ensure steps exist and return existing app
            for n in [1, 2, 3]:
                ApplicationStep.objects.get_or_create(
                    application=existing,
                    step_number=n,
                    defaults={"is_completed": False, "data_saved": False}
                )
            return Response({
                "success": True,
                "data": {
                    "application_id": existing.application_id,
                    "current_step": existing.current_step,
                    "redirect_to_step": existing.current_step,
                    "message": "Resuming existing application"
                }
            })

        # Create a new application idempotently
        attempts = 0
        app = None
        while attempts < 5 and app is None:
            try:
                app = BusinessApplication.objects.create(
                    application_id=_generate_application_id(user_locked.user_id),
                    user=user_locked,
                    current_step=1,
                    status="in_progress",
                    total_steps=3,
                    last_activity=timezone.now()
                )
            except IntegrityError:
                attempts += 1

        # If we couldn't create (e.g., concurrent create won), fall back to latest existing
        if app is None:
            app = (
                BusinessApplication.objects.select_for_update()
                .filter(user=user_locked)
                .exclude(status__in(["approved"]))
                .order_by('-created_at')
                .first()
            )
            if app is None:
                return Response({"error": "Failed to initialize application"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        for n in [1, 2, 3]:
            ApplicationStep.objects.get_or_create(
                application=app,
                step_number=n,
                defaults={"is_completed": False, "data_saved": False}
            )

        return Response({
            "success": True,
            "data": {
                "application_id": app.application_id,
                "current_step": 1,
                "redirect_to_step": 1,
                "message": "New application created"
            }
        }, status=status.HTTP_201_CREATED)


@swagger_auto_schema(method='POST', request_body=openapi.Schema(
    type=openapi.TYPE_OBJECT,
    required=['application_id', 'user_id'],
    properties={
        'application_id': openapi.Schema(type=openapi.TYPE_STRING, description='Application ID'),
        'user_id': openapi.Schema(type=openapi.TYPE_STRING, description='User ID'),
        'auto_save': openapi.Schema(type=openapi.TYPE_BOOLEAN, description='Auto save'),
        'business_name': openapi.Schema(type=openapi.TYPE_STRING, description='Business name'),
        'business_type': openapi.Schema(type=openapi.TYPE_STRING, description='Business type'),
        'category': openapi.Schema(type=openapi.TYPE_STRING, description='Category'),
        'address': openapi.Schema(type=openapi.TYPE_STRING, description='Address'),
        'registration_number': openapi.Schema(type=openapi.TYPE_STRING, description='Registration number'),
        'store_description': openapi.Schema(type=openapi.TYPE_STRING, description='Store description'),
        'gstin': openapi.Schema(type=openapi.TYPE_STRING, description='GSTIN'),
        'owner_pan': openapi.Schema(type=openapi.TYPE_STRING, description='Owner PAN'),
        'account_number': openapi.Schema(type=openapi.TYPE_STRING, description='Account number'),
        'ifsc_code': openapi.Schema(type=openapi.TYPE_STRING, description='IFSC code'),
    },
), tags=['Business'])

@api_view(["POST"])  # /kirazee/api/v1/business-onboarding/step1/save
@parser_classes([JSONParser])
def step1_save(request):
    application_id = request.data.get("application_id")
    user_id = request.data.get("user_id")
    auto_save = bool(request.data.get("auto_save", False))

    if not application_id or not user_id:
        return Response({"error": "application_id and user_id are required"}, status=status.HTTP_400_BAD_REQUEST)

    app = get_object_or_404(BusinessApplication, application_id=application_id)
    if app.user.user_id != int(user_id):
        return Response({"error": "Application does not belong to user"}, status=status.HTTP_403_FORBIDDEN)

    # Extract GSTIN from request data for validation
    gstin = request.data.get("gstin", "").strip().upper()
    
    # Validate GSTIN if provided and not auto-save
    if gstin and not auto_save:
        # Check if GSTIN already exists in business_financials table
        from kirazee_app.models import BusinessFinancial
        existing_gstin = BusinessFinancial.objects.filter(gstin=gstin).first()
        
        if existing_gstin:
            return Response({
                "success": False,
                "error": "GSTIN already exists in the system",
                "validation_errors": {
                    "gstin": "This GSTIN is already registered with business ID: " + existing_gstin.business_id
                },
                "existing_business": {
                    "business_id": existing_gstin.business_id,
                    "gstin": existing_gstin.gstin
                }
            }, status=status.HTTP_400_BAD_REQUEST)

    payload = {
        "business_name": request.data.get("business_name"),
        "business_type": request.data.get("business_type"),
        "category": request.data.get("category"),
        "address": request.data.get("address"),
        "registration_number": request.data.get("registration_number"),
        "store_description": request.data.get("store_description"),
        "gstin": gstin,  # Include GSTIN in payload
        # Include financial details in step data for backup
        "owner_pan": request.data.get("owner_pan", ""),
        "account_number": request.data.get("account_number", ""),
        "ifsc_code": request.data.get("ifsc_code", ""),
    }

    step, _ = ApplicationStep.objects.get_or_create(application=app, step_number=1)
    step.step_data = payload
    step.data_saved = True
    if not auto_save:
        step.is_completed = True
        step.completed_at = timezone.now()
        app.current_step = max(app.current_step, 2)
        app.status = "in_progress"
    step.save()
    app.last_activity = timezone.now()
    app.save(update_fields=["current_step", "status", "last_activity", "updated_at"])

    # Save financial details to BusinessFinancial table
    try:
        from kirazee_app.models import BusinessFinancial
        from decimal import Decimal
        
        # Generate a temporary business_id for the financial record
        # This will be updated when the business is actually created
        temp_business_id = f"TEMP_{app.application_id}"
        
        # Get or create BusinessFinancial record
        financial, created = BusinessFinancial.objects.get_or_create(
            business_id=temp_business_id,
            defaults={
                'owner_pan': request.data.get("owner_pan", "").strip().upper(),
                'gstin': gstin,
                'account_number': request.data.get("account_number", "").strip(),
                'ifsc_code': request.data.get("ifsc_code", "").strip().upper(),
                'bank_name': '',  # Will be filled later
                'branch_name': '',  # Will be filled later
                'upi_id': '',  # Will be filled later
                'payment_status': False,
                'razorpay_contact_id': '',
                'razorpay_fund_account_id': '',
                'settlement_status': False,
                'daily_settlement_limit': Decimal('50000.00'),
                'weekly_settlement_limit': Decimal('200000.00'),
                'monthly_settlement_limit': Decimal('800000.00'),
            }
        )
        
        if not created:
            # Update existing record
            financial.owner_pan = request.data.get("owner_pan", "").strip().upper()
            financial.gstin = gstin
            financial.account_number = request.data.get("account_number", "").strip()
            financial.ifsc_code = request.data.get("ifsc_code", "").strip().upper()
            financial.save()
            
        logger.info(f"Financial details {'created' if created else 'updated'} for application {app.application_id}")
        
    except Exception as e:
        logger.error(f"Error saving financial details for application {app.application_id}: {str(e)}")
        # Don't fail the whole operation if financial saving fails
        # The financial details can be saved later during business creation

    return Response({
        "success": True,
        "data": {
            "step_completed": not auto_save,
            "next_step": 2,
            "application_id": app.application_id,
            "validation_errors": [],
            "saved_at": timezone.now().isoformat(),
            "gstin_validated": bool(gstin) and not auto_save
        }
    })


@swagger_auto_schema(method='GET', tags=['Business'])
@api_view(["GET"])  # /kirazee/api/v1/business-onboarding/step1/<str:application_id>
def step1_get(request, application_id: str):
    app = get_object_or_404(BusinessApplication, application_id=application_id)
    step = ApplicationStep.objects.filter(application=app, step_number=1).first()
    return Response({
        "success": True,
        "data": {
            **(step.step_data or {}),
            "last_updated": step.updated_at.isoformat() if step and step.updated_at else None
        }
    })


@swagger_auto_schema(method='POST', tags=['Business'])
@api_view(["POST"])  # /kirazee/api/v1/business-onboarding/step2/upload
@parser_classes([MultiPartParser, FormParser])
def step2_upload(request):
    application_id = request.data.get("application_id")
    document_type = request.data.get("document_type")
    file = request.FILES.get("file")

    if not application_id or not document_type or not file:
        return Response({"error": "application_id, document_type and file are required"}, status=status.HTTP_400_BAD_REQUEST)

    app = get_object_or_404(BusinessApplication, application_id=application_id)
    # If a document with the same type already exists for this application, replace it
    existing = ApplicationDocument.objects.filter(application=app, document_type=document_type).order_by("-uploaded_at").first()
    if existing:
        # Update existing record (preserve document_id), reset verification, and refresh timestamp
        existing.file = file
        existing.file_name = file.name
        existing.file_size = file.size
        existing.upload_status = "uploaded"
        existing.verification_status = "pending"
        existing.verified_at = None
        try:
            # Manually bump uploaded_at to reflect replacement
            existing.uploaded_at = timezone.now()
        except Exception:
            pass
        existing.save()

        # If the application was previously marked as requires_changes, move it back to in_progress on re-upload
        try:
            if app.status == "requires_changes":
                app.status = "in_progress"
                app.save(update_fields=["status", "updated_at"])
        except Exception:
            pass

        url = build_s3_file_url(existing.file)
        return Response({
            "success": True,
            "data": {
                "document_id": existing.document_id,
                "document_type": existing.document_type,
                "file_name": existing.file_name,
                "file_size": existing.file_size,
                "upload_url": url,
                "uploaded_at": existing.uploaded_at.isoformat() if existing.uploaded_at else None,
                "replaced": True
            }
        }, status=status.HTTP_200_OK)
    else:
        # Create a new record
        doc = ApplicationDocument(
            application=app,
            document_id=_generate_document_id(),
            document_type=document_type,
            file=file,
            file_name=file.name,
            file_size=file.size,
            upload_status="uploaded",
            verification_status="pending"
        )
        doc.save()

        # If the application was previously marked as requires_changes, move it back to in_progress on new upload
        try:
            if app.status == "requires_changes":
                app.status = "in_progress"
                app.save(update_fields=["status", "updated_at"])
        except Exception:
            pass

        url = build_s3_file_url(doc.file)

        return Response({
            "success": True,
            "data": {
                "document_id": doc.document_id,
                "document_type": doc.document_type,
                "file_name": doc.file_name,
                "file_size": doc.file_size,
                "upload_url": url,
                "uploaded_at": doc.uploaded_at.isoformat() if doc.uploaded_at else None,
            }
        }, status=status.HTTP_201_CREATED)


@swagger_auto_schema(method='GET', tags=['Business'])
@api_view(["GET"])  # /kirazee/api/v1/business-onboarding/step2/<str:application_id>/documents
def step2_get_documents(request, application_id: str):
    app = get_object_or_404(BusinessApplication, application_id=application_id)
    docs = ApplicationDocument.objects.filter(application=app).order_by("-uploaded_at")

    items = []
    for d in docs:
        items.append({
            "document_id": d.document_id,
            "document_type": d.document_type,
            "file_name": d.file_name,
            "status": d.upload_status,
            "upload_url": build_s3_file_url(d.file),
            "uploaded_at": d.uploaded_at.isoformat() if d.uploaded_at else None
        })

    required_documents = ["identity_proof", "business_registration", "store_photo", "bank_proof"]
    uploaded_types = set(d.document_type for d in docs)
    missing = [t for t in required_documents if t not in uploaded_types]

    return Response({
        "success": True,
        "data": {
            "documents": items,
            "required_documents": required_documents,
            "missing_documents": missing,
            "all_uploaded": len(missing) == 0
        }
    })

@swagger_auto_schema(method='POST', tags=['Business'])
@api_view(["POST"])  # /kirazee/api/v1/business-onboarding/step2/complete
@parser_classes([JSONParser])
def step2_complete(request):
    application_id = request.data.get("application_id")
    user_id = request.data.get("user_id")

    if not application_id or not user_id:
        return Response({"error": "application_id and user_id are required"}, status=status.HTTP_400_BAD_REQUEST)

    app = get_object_or_404(BusinessApplication, application_id=application_id)
    if app.user.user_id != int(user_id):
        return Response({"error": "Application does not belong to user"}, status=status.HTTP_403_FORBIDDEN)

    step = ApplicationStep.objects.filter(application=app, step_number=2).first()
    if not step:
        step = ApplicationStep.objects.create(application=app, step_number=2)

    step.is_completed = True
    step.data_saved = True
    step.completed_at = timezone.now()
    step.save()

    app.current_step = max(app.current_step, 3)
    app.last_activity = timezone.now()
    app.save(update_fields=["current_step", "last_activity", "updated_at"])

    return Response({"success": True, "data": {"step_completed": True, "next_step": 3}})

@swagger_auto_schema(method='POST', tags=['Business'])
@api_view(["POST"])  # /kirazee/api/v1/business-onboarding/step3/save
@parser_classes([JSONParser])
def step3_save(request):
    application_id = request.data.get("application_id")
    user_id = request.data.get("user_id")

    if not application_id or not user_id:
        return Response({"error": "application_id and user_id are required"}, status=status.HTTP_400_BAD_REQUEST)

    app = get_object_or_404(BusinessApplication, application_id=application_id)
    if app.user.user_id != int(user_id):
        return Response({"error": "Application does not belong to user"}, status=status.HTTP_403_FORBIDDEN)

    payload = {
        "working_hours": request.data.get("working_hours"),
        "payment_modes": request.data.get("payment_modes"),
        "delivery_preferences": request.data.get("delivery_preferences"),
    }

    step, _ = ApplicationStep.objects.get_or_create(application=app, step_number=3)
    step.step_data = payload
    step.data_saved = True
    step.is_completed = True
    step.completed_at = timezone.now()
    step.save()

    app.current_step = 3
    app.last_activity = timezone.now()
    # If previously required_changes, move back to in_progress on new data save
    try:
        if app.status == "requires_changes":
            app.status = "in_progress"
    except Exception:
        pass
    app.save(update_fields=["current_step", "last_activity", "status", "updated_at"])

    return Response({
        "success": True,
        "data": {
            "step_completed": True,
            "application_submitted": True,
            "application_id": app.application_id,
            "submission_date": timezone.now().isoformat(),
            "estimated_review_time": "24-48 hours"
        }
    })

@swagger_auto_schema(method='POST', tags=['Business'])
@api_view(["POST"])  # /kirazee/api/v1/business-onboarding/submit
@parser_classes([JSONParser])
def submit_application(request):
    application_id = request.data.get("application_id")
    user_id = request.data.get("user_id")

    if not application_id or not user_id:
        return Response({"error": "application_id and user_id are required"}, status=status.HTTP_400_BAD_REQUEST)

    app = get_object_or_404(BusinessApplication, application_id=application_id)
    if app.user.user_id != int(user_id):
        return Response({"error": "Application does not belong to user"}, status=status.HTTP_403_FORBIDDEN)

    missing = []
    for n in [1, 2, 3]:
        s = ApplicationStep.objects.filter(application=app, step_number=n).first()
        if not (s and s.is_completed):
            missing.append(n)

    if missing:
        return Response({"error": "All steps must be completed before submission", "missing_steps": missing}, status=status.HTTP_400_BAD_REQUEST)

    app.status = "submitted"
    app.submitted_at = timezone.now()
    app.save(update_fields=["status", "submitted_at", "updated_at"])

    ref = f"REF_KIR_{timezone.now().strftime('%Y%m%d')}_{app.application_id.split('_')[-1]}"

    return Response({
        "success": True,
        "data": {
            "application_id": app.application_id,
            "status": "submitted",
            "submitted_at": app.submitted_at.isoformat(),
            "reference_number": ref,
            "estimated_review_time": "24-48 hours",
            "next_steps": [
                "Admin review of documents",
                "Business verification",
                "WhatsApp/Email notification upon approval"
            ]
        }
    })

@swagger_auto_schema(method='GET', tags=['Business'])
@api_view(["GET"])  # /kirazee/api/v1/business-onboarding/status/<str:application_id>
def get_application_status(request, application_id: str):
    app = get_object_or_404(BusinessApplication, application_id=application_id)

    review = AdminReview.objects.filter(application=app).order_by('-reviewed_at').first()

    status_out = (
        "required_changes" if app.status == "requires_changes" else
        ("rejected" if app.status == "rejected" else
         ("approved" if app.status == "approved" else "pending"))
    )

    data = {
        "application_id": app.application_id,
        "business_name": _get_application_business_name(app),
        "status": status_out,
        "submitted_at": app.submitted_at.isoformat() if app.submitted_at else None,
        "last_updated": app.updated_at.isoformat() if app.updated_at else None,
        "review_progress": {
            "documents_reviewed": False if not review else review.action in ["approve", "reject", "request_changes"],
            "business_verified": True if (review and review.action == "approve") else False,
            "admin_assigned": bool(review),
            "estimated_completion": (app.submitted_at + timezone.timedelta(hours=48)).isoformat() if app.submitted_at else None
        },
        "admin_comments": [] if not review else ([review.comments] if review.comments else []),
        # Only include reasons/changes when the CURRENT status matches
        "rejection_reasons": [] if app.status != "rejected" else ((review.rejection_reasons or []) if review else []),
        "required_changes": [] if app.status != "requires_changes" else ((review.required_changes or []) if review else []),
        "approval_details": None
    }
    return Response({"success": True, "data": data})

@swagger_auto_schema(method='GET', tags=['Business'])
@api_view(["GET"])  # /kirazee/api/v1/admin/business-applications/pending
def admin_list_pending(request):
    page = int(request.query_params.get("page", 1))
    limit = min(int(request.query_params.get("limit", 10)), 100)
    offset = (page - 1) * limit

    qs = BusinessApplication.objects.filter(status__in=["submitted","pending_review"]).order_by("-submitted_at")

    category = request.query_params.get("category")
    if category:
        apps = list(qs)
        filtered_ids = []
        for a in apps:
            s1 = ApplicationStep.objects.filter(application=a, step_number=1).first()
            if s1 and s1.step_data and str(s1.step_data.get("business_type", "")).lower() == category.lower():
                filtered_ids.append(a.id)
        qs = qs.filter(id__in=filtered_ids)

    search = request.query_params.get("search")
    if search:
        apps = list(qs)
        filtered_ids = []
        for a in apps:
            s1 = ApplicationStep.objects.filter(application=a, step_number=1).first()
            name = _get_application_business_name(a)
            if name and search.lower() in name.lower():
                filtered_ids.append(a.id)
        qs = qs.filter(id__in=filtered_ids)

    total = qs.count()
    items = []
    for app in qs[offset:offset+limit]:
        s1 = ApplicationStep.objects.filter(application=app, step_number=1).first()
        user = app.user
        docs_count = ApplicationDocument.objects.filter(application=app).count()
        addr = (s1.step_data or {}).get("address") if s1 else None
        location_text = None
        if isinstance(addr, dict):
            city = addr.get("city")
            state = addr.get("state")
            location_text = ", ".join([p for p in [city, state] if p]) if (city or state) else None
        
        # Get latest admin review for rejection reasons and required changes
        review = AdminReview.objects.filter(application=app).order_by('-reviewed_at').first()
        
        items.append({
            "application_id": app.application_id,
            "business_name": _get_application_business_name(app),
            "owner_name": f"{user.firstName} {user.lastName}",
            "business_type": (s1.step_data or {}).get("business_type") if s1 else None,
            "location": location_text,
            "submitted_at": app.submitted_at.isoformat() if app.submitted_at else None,
            "status": "pending_review",
            "phone": user.mobileNumber,
            "email": user.emailID,
            "registration_number": (s1.step_data or {}).get("registration_number") if s1 else None,
            "documents_count": docs_count,
            "priority": "normal",
            # Include rejection reasons and required changes from latest review
            "rejection_reasons": [] if app.status != "rejected" else ((review.rejection_reasons or []) if review else []),
            "required_changes": [] if app.status != "requires_changes" else ((review.required_changes or []) if review else []),
            "comments": review.comments if review else ""
        })

    # statistics
    stats = {"total_pending": total, "food_businesses": 0, "grocery_stores": 0, "other_categories": 0}
    for a in qs:
        s1 = ApplicationStep.objects.filter(application=a, step_number=1).first()
        bt = (s1.step_data or {}).get("business_type") if s1 else None
        if bt and str(bt).lower() == "food":
            stats["food_businesses"] += 1
        elif bt and str(bt).lower() == "grocery":
            stats["grocery_stores"] += 1
        else:
            stats["other_categories"] += 1

    return Response({
        "success": True,
        "data": {
            "applications": items,
            "pagination": {
                "current_page": page,
                "total_pages": (total + limit - 1) // limit,
                "total_items": total,
                "items_per_page": limit
            },
            "statistics": stats
        }
    })

@swagger_auto_schema(method='GET', tags=['Business'])
@api_view(["GET"])  # /kirazee/api/v1/admin/business-applications/all
def admin_list_all(request):
    page = int(request.query_params.get("page", 1))
    limit = min(int(request.query_params.get("limit", 10)), 100)
    offset = (page - 1) * limit

    qs = BusinessApplication.objects.all().order_by("-submitted_at")

    category = request.query_params.get("category")
    if category:
        apps = list(qs)
        filtered_ids = []
        for a in apps:
            s1 = ApplicationStep.objects.filter(application=a, step_number=1).first()
            if s1 and s1.step_data and str(s1.step_data.get("business_type", "")).lower() == category.lower():
                filtered_ids.append(a.id)
        qs = qs.filter(id__in=filtered_ids)

    search = request.query_params.get("search")
    if search:
        apps = list(qs)
        filtered_ids = []
        for a in apps:
            s1 = ApplicationStep.objects.filter(application=a, step_number=1).first()
            name = _get_application_business_name(a)
            if name and search.lower() in name.lower():
                filtered_ids.append(a.id)
        qs = qs.filter(id__in=filtered_ids)

    total = qs.count()
    items = []
    for app in qs[offset:offset+limit]:
        s1 = ApplicationStep.objects.filter(application=app, step_number=1).first()
        user = app.user
        docs_count = ApplicationDocument.objects.filter(application=app).count()
        addr = (s1.step_data or {}).get("address") if s1 else None
        location_text = None
        if isinstance(addr, dict):
            city = addr.get("city")
            state = addr.get("state")
            location_text = ", ".join([p for p in [city, state] if p]) if (city or state) else None
        
        # Get latest admin review for rejection reasons and required changes
        review = AdminReview.objects.filter(application=app).order_by('-reviewed_at').first()
        
        items.append({
            "application_id": app.application_id,
            "business_name": _get_application_business_name(app),
            "owner_name": f"{user.firstName} {user.lastName}",
            "business_type": (s1.step_data or {}).get("business_type") if s1 else None,
            "location": location_text,
            "submitted_at": app.submitted_at.isoformat() if app.submitted_at else None,
            "status": app.status,
            "phone": user.mobileNumber,
            "email": user.emailID,
            "registration_number": (s1.step_data or {}).get("registration_number") if s1 else None,
            "documents_count": docs_count,
            "priority": "normal",
            # Include rejection reasons and required changes from latest review
            "rejection_reasons": [] if app.status != "rejected" else ((review.rejection_reasons or []) if review else []),
            "required_changes": [] if app.status != "requires_changes" else ((review.required_changes or []) if review else []),
            "comments": review.comments if review else ""
        })

    stats = {"total": total, "food_businesses": 0, "grocery_stores": 0, "other_categories": 0}
    for a in qs:
        s1 = ApplicationStep.objects.filter(application=a, step_number=1).first()
        bt = (s1.step_data or {}).get("business_type") if s1 else None
        if bt and str(bt).lower() == "food":
            stats["food_businesses"] += 1
        elif bt and str(bt).lower() == "grocery":
            stats["grocery_stores"] += 1
        else:
            stats["other_categories"] += 1

    return Response({
        "success": True,
        "data": {
            "applications": items,
            "pagination": {
                "current_page": page,
                "total_pages": (total + limit - 1) // limit,
                "total_items": total,
                "items_per_page": limit
            },
            "statistics": stats
        }
    })

@swagger_auto_schema(method='GET', tags=['Business'])
@api_view(["GET"])  # /kirazee/api/v1/admin/business-applications/approved
def admin_list_approved(request):
    page = int(request.query_params.get("page", 1))
    limit = min(int(request.query_params.get("limit", 10)), 100)
    offset = (page - 1) * limit

    qs = BusinessApplication.objects.filter(status="approved").order_by("-submitted_at")

    category = request.query_params.get("category")
    if category:
        apps = list(qs)
        filtered_ids = []
        for a in apps:
            s1 = ApplicationStep.objects.filter(application=a, step_number=1).first()
            if s1 and s1.step_data and str(s1.step_data.get("business_type", "")).lower() == category.lower():
                filtered_ids.append(a.id)
        qs = qs.filter(id__in=filtered_ids)

    search = request.query_params.get("search")
    if search:
        apps = list(qs)
        filtered_ids = []
        for a in apps:
            s1 = ApplicationStep.objects.filter(application=a, step_number=1).first()
            name = _get_application_business_name(a)
            if name and search.lower() in name.lower():
                filtered_ids.append(a.id)
        qs = qs.filter(id__in=filtered_ids)

    total = qs.count()
    items = []
    for app in qs[offset:offset+limit]:
        s1 = ApplicationStep.objects.filter(application=app, step_number=1).first()
        user = app.user
        docs_count = ApplicationDocument.objects.filter(application=app).count()
        addr = (s1.step_data or {}).get("address") if s1 else None
        location_text = None
        if isinstance(addr, dict):
            city = addr.get("city")
            state = addr.get("state")
            location_text = ", ".join([p for p in [city, state] if p]) if (city or state) else None
        
        # Get latest admin review for rejection reasons and required changes
        review = AdminReview.objects.filter(application=app).order_by('-reviewed_at').first()
        
        items.append({
            "application_id": app.application_id,
            "business_name": _get_application_business_name(app),
            "owner_name": f"{user.firstName} {user.lastName}",
            "business_type": (s1.step_data or {}).get("business_type") if s1 else None,
            "location": location_text,
            "submitted_at": app.submitted_at.isoformat() if app.submitted_at else None,
            "status": app.status,
            "phone": user.mobileNumber,
            "email": user.emailID,
            "registration_number": (s1.step_data or {}).get("registration_number") if s1 else None,
            "documents_count": docs_count,
            "priority": "normal",
            # Include rejection reasons and required changes from latest review
            "rejection_reasons": [] if app.status != "rejected" else ((review.rejection_reasons or []) if review else []),
            "required_changes": [] if app.status != "requires_changes" else ((review.required_changes or []) if review else []),
            "comments": review.comments if review else ""
        })

    stats = {"total_approved": total, "food_businesses": 0, "grocery_stores": 0, "other_categories": 0}
    for a in qs:
        s1 = ApplicationStep.objects.filter(application=a, step_number=1).first()
        bt = (s1.step_data or {}).get("business_type") if s1 else None
        if bt and str(bt).lower() == "food":
            stats["food_businesses"] += 1
        elif bt and str(bt).lower() == "grocery":
            stats["grocery_stores"] += 1
        else:
            stats["other_categories"] += 1

    return Response({
        "success": True,
        "data": {
            "applications": items,
            "pagination": {
                "current_page": page,
                "total_pages": (total + limit - 1) // limit,
                "total_items": total,
                "items_per_page": limit
            },
            "statistics": stats
        }
    })

@swagger_auto_schema(method='GET', tags=['Business'])
@api_view(["GET"])  # /kirazee/api/v1/admin/business-applications/rejected
def admin_list_rejected(request):
    page = int(request.query_params.get("page", 1))
    limit = min(int(request.query_params.get("limit", 10)), 100)
    offset = (page - 1) * limit

    qs = BusinessApplication.objects.filter(status="rejected").order_by("-submitted_at")

    category = request.query_params.get("category")
    if category:
        apps = list(qs)
        filtered_ids = []
        for a in apps:
            s1 = ApplicationStep.objects.filter(application=a, step_number=1).first()
            if s1 and s1.step_data and str(s1.step_data.get("business_type", "")).lower() == category.lower():
                filtered_ids.append(a.id)
        qs = qs.filter(id__in=filtered_ids)

    search = request.query_params.get("search")
    if search:
        apps = list(qs)
        filtered_ids = []
        for a in apps:
            s1 = ApplicationStep.objects.filter(application=a, step_number=1).first()
            name = _get_application_business_name(a)
            if name and search.lower() in name.lower():
                filtered_ids.append(a.id)
        qs = qs.filter(id__in=filtered_ids)

    total = qs.count()
    items = []
    for app in qs[offset:offset+limit]:
        s1 = ApplicationStep.objects.filter(application=app, step_number=1).first()
        user = app.user
        docs_count = ApplicationDocument.objects.filter(application=app).count()
        addr = (s1.step_data or {}).get("address") if s1 else None
        location_text = None
        if isinstance(addr, dict):
            city = addr.get("city")
            state = addr.get("state")
            location_text = ", ".join([p for p in [city, state] if p]) if (city or state) else None
        
        # Get latest admin review for rejection reasons and required changes
        review = AdminReview.objects.filter(application=app).order_by('-reviewed_at').first()
        
        items.append({
            "application_id": app.application_id,
            "business_name": _get_application_business_name(app),
            "owner_name": f"{user.firstName} {user.lastName}",
            "business_type": (s1.step_data or {}).get("business_type") if s1 else None,
            "location": location_text,
            "submitted_at": app.submitted_at.isoformat() if app.submitted_at else None,
            "status": app.status,
            "phone": user.mobileNumber,
            "email": user.emailID,
            "registration_number": (s1.step_data or {}).get("registration_number") if s1 else None,
            "documents_count": docs_count,
            "priority": "normal",
            # Include rejection reasons and required changes from latest review
            "rejection_reasons": [] if app.status != "rejected" else ((review.rejection_reasons or []) if review else []),
            "required_changes": [] if app.status != "requires_changes" else ((review.required_changes or []) if review else []),
            "comments": review.comments if review else ""
        })

    stats = {"total_rejected": total, "food_businesses": 0, "grocery_stores": 0, "other_categories": 0}
    for a in qs:
        s1 = ApplicationStep.objects.filter(application=a, step_number=1).first()
        bt = (s1.step_data or {}).get("business_type") if s1 else None
        if bt and str(bt).lower() == "food":
            stats["food_businesses"] += 1
        elif bt and str(bt).lower() == "grocery":
            stats["grocery_stores"] += 1
        else:
            stats["other_categories"] += 1

    return Response({
        "success": True,
        "data": {
            "applications": items,
            "pagination": {
                "current_page": page,
                "total_pages": (total + limit - 1) // limit,
                "total_items": total,
                "items_per_page": limit
            },
            "statistics": stats
        }
    })

@swagger_auto_schema(method='GET', tags=['Business'])
@api_view(["GET"])  # /kirazee/api/v1/in_progress/business-applications/pending
def admin_list_in_progress(request):
    page = int(request.query_params.get("page", 1))
    limit = min(int(request.query_params.get("limit", 10)), 100)
    offset = (page - 1) * limit

    qs = BusinessApplication.objects.filter(status="in_progress").order_by("-updated_at")

    category = request.query_params.get("category")
    if category:
        apps = list(qs)
        filtered_ids = []
        for a in apps:
            s1 = ApplicationStep.objects.filter(application=a, step_number=1).first()
            if s1 and s1.step_data and str(s1.step_data.get("business_type", "")).lower() == category.lower():
                filtered_ids.append(a.id)
        qs = qs.filter(id__in=filtered_ids)

    search = request.query_params.get("search")
    if search:
        apps = list(qs)
        filtered_ids = []
        for a in apps:
            s1 = ApplicationStep.objects.filter(application=a, step_number=1).first()
            name = (s1.step_data or {}).get("business_name") if s1 else None
            if name and search.lower() in name.lower():
                filtered_ids.append(a.id)
        qs = qs.filter(id__in=filtered_ids)

    total = qs.count()
    items = []
    for app in qs[offset:offset+limit]:
        s1 = ApplicationStep.objects.filter(application=app, step_number=1).first()
        user = app.user
        docs_count = ApplicationDocument.objects.filter(application=app).count()
        addr = (s1.step_data or {}).get("address") if s1 else None
        location_text = None
        if isinstance(addr, dict):
            city = addr.get("city")
            state = addr.get("state")
            location_text = ", ".join([p for p in [city, state] if p]) if (city or state) else None
        
        # Get latest admin review for rejection reasons and required changes
        review = AdminReview.objects.filter(application=app).order_by('-reviewed_at').first()
        
        items.append({
            "application_id": app.application_id,
            "business_name": _get_application_business_name(app),
            "owner_name": f"{user.firstName} {user.lastName}",
            "business_type": (s1.step_data or {}).get("business_type") if s1 else None,
            "location": location_text,
            "submitted_at": app.submitted_at.isoformat() if app.submitted_at else None,
            "status": app.status,
            "phone": user.mobileNumber,
            "email": user.emailID,
            "registration_number": (s1.step_data or {}).get("registration_number") if s1 else None,
            "documents_count": docs_count,
            "priority": "normal",
            # Include rejection reasons and required changes from latest review
            "rejection_reasons": [] if app.status != "rejected" else ((review.rejection_reasons or []) if review else []),
            "required_changes": [] if app.status != "requires_changes" else ((review.required_changes or []) if review else []),
            "comments": review.comments if review else ""
        })

    stats = {"total_in_progress": total, "food_businesses": 0, "grocery_stores": 0, "other_categories": 0}
    for a in qs:
        s1 = ApplicationStep.objects.filter(application=a, step_number=1).first()
        bt = (s1.step_data or {}).get("business_type") if s1 else None
        if bt and str(bt).lower() == "food":
            stats["food_businesses"] += 1
        elif bt and str(bt).lower() == "grocery":
            stats["grocery_stores"] += 1
        else:
            stats["other_categories"] += 1

    return Response({
        "success": True,
        "data": {
            "applications": items,
            "pagination": {
                "current_page": page,
                "total_pages": (total + limit - 1) // limit,
                "total_items": total,
                "items_per_page": limit
            },
            "statistics": stats
        }
    })

@swagger_auto_schema(method='GET', tags=['Business'])
@api_view(["GET"])  # /kirazee/api/v1/admin/business-applications/<str:application_id>/details
def admin_application_details(request, application_id: str):
    app = get_object_or_404(BusinessApplication, application_id=application_id)
    s1 = ApplicationStep.objects.filter(application=app, step_number=1).first()
    s3 = ApplicationStep.objects.filter(application=app, step_number=3).first()
    docs = ApplicationDocument.objects.filter(application=app).order_by('uploaded_at')

    business_info = (s1.step_data if s1 and s1.step_data else {})
    operational_details = (s3.step_data if s3 and s3.step_data else {})

    doc_items = []
    for d in docs:
        doc_items.append({
            "document_id": d.document_id,
            "document_type": d.document_type,
            "file_name": d.file_name,
            "file_url": build_s3_file_url(d.file),
            "uploaded_at": d.uploaded_at.isoformat() if d.uploaded_at else None,
            "file_size": d.file_size,
            "verification_status": d.verification_status
        })

    timeline = []
    if s1 and s1.completed_at:
        timeline.append({"step": "step_1_completed", "timestamp": s1.completed_at.isoformat(), "description": "Business information saved"})
    if s3 and s3.completed_at:
        timeline.append({"step": "step_3_completed", "timestamp": s3.completed_at.isoformat(), "description": "Operational details saved"})

    return Response({
        "success": True,
        "data": {
            "application_id": app.application_id,
            "business_name": _get_application_business_name(app),
            "business_info": business_info,
            "owner_info": {
                "name": f"{app.user.firstName} {app.user.lastName}",
                "phone": app.user.mobileNumber,
                "email": app.user.emailID
            },
            "documents": doc_items,
            "operational_details": operational_details,
            # Expose key operational fields at top-level for convenience
            "payment_modes": (operational_details or {}).get("payment_modes"),
            "working_hours": (operational_details or {}).get("working_hours"),
            "delivery_preferences": (operational_details or {}).get("delivery_preferences"),
            "submission_timeline": timeline
        }
    })


def _map_business_type_code(bt: str, category: str = None) -> str:
    if not bt and not category:
        return "OTH"
    
    s0 = str(bt).strip() if bt else ""
    s = s0.lower()
    
    # Normalize by replacing underscores with spaces and vice versa for comparison
    s_normalized = s.replace('_', ' ')
    s_normalized_underscore = s.replace(' ', '_')
    
    print(f"DEBUG: Looking for business_type='{bt}', category='{category}'")
    print(f"DEBUG: Normalized strings: '{s_normalized}', '{s_normalized_underscore}'")
    
    try:
        # Test if we can query BusinessType at all
        print(f"DEBUG: Testing BusinessType table access...")
        all_types = BusinessType.objects.all()
        print(f"DEBUG: Found {all_types.count()} business types in database")
        
        if all_types.count() > 0:
            # Print first few types for debugging
            for i, bt_row in enumerate(all_types[:3]):
                print(f"DEBUG: Type {i}: code='{bt_row.code}', type='{bt_row.type}'")
        
        # First, try exact code/type matches (trim-insensitive) only if bt provided
        if s0:
            print(f"DEBUG: Searching by code__iexact='{s0}'")
            row = BusinessType.objects.filter(code__iexact=s0).first()
            print(f"DEBUG: Code search result: {row}")
            if row:
                print(f"DEBUG: Found by code, returning: {row.code}")
                return row.code
                
            print(f"DEBUG: Searching by type__iexact='{s0}'")
            row = BusinessType.objects.filter(type__iexact=s0).first()
            print(f"DEBUG: Type search result: {row}")
            if row:
                print(f"DEBUG: Found by type, returning: {row.code}")
                return row.code
        
        # If category provided, try to resolve via categories
        if category:
            c0 = str(category).strip()
            print(f"DEBUG: Searching by category='{c0}'")
            # Strict JSON membership (exact)
            row = BusinessType.objects.filter(categories__contains=[c0]).first()
            print(f"DEBUG: Category exact search result: {row}")
            if row:
                print(f"DEBUG: Found by category exact, returning: {row.code}")
                return row.code
            # Case-insensitive membership by scanning
            print(f"DEBUG: Scanning all business types for category match")
            for bt_row in BusinessType.objects.all():
                cats = bt_row.categories or []
                if any(c0.lower() == str(cat).strip().lower() for cat in cats):
                    print(f"DEBUG: Found by category scan, returning: {bt_row.code}")
                    return bt_row.code
        
        # Enhanced fuzzy matches with normalization
        if s:
            print(f"DEBUG: Doing fuzzy search with '{s}' (normalized: '{s_normalized}', '{s_normalized_underscore}')")
            
            # Direct test for food_and_beverage
            if s == 'food_and_beverage':
                print(f"DEBUG: Direct test - looking for 'food and beverage' in database")
                food_type = BusinessType.objects.filter(type__iexact='food and beverage').first()
                if food_type:
                    print(f"DEBUG: Direct test found: {food_type.code}")
                    return food_type.code
            
            for bt_row in BusinessType.objects.all():
                t = (bt_row.type or '').lower()
                t_normalized = t.replace(' ', '_')
                t_spaces = t.replace('_', ' ')
                cats = [str(c).lower().replace(' ', '_') for c in (bt_row.categories or [])]
                cats_spaces = [str(c).lower().replace('_', ' ') for c in (bt_row.categories or [])]
                
                print(f"DEBUG: Checking bt_row.type='{t}' (normalized: '{t_normalized}', '{t_spaces}')")
                print(f"DEBUG: Comparing: s='{s}' vs t='{t}', s_normalized='{s_normalized}' vs t_spaces='{t_spaces}'")
                
                # Check multiple variations
                if (s == t or 
                    s_normalized == t or 
                    s == t_normalized or 
                    s_normalized == t_normalized or
                    s == t_spaces or
                    s_normalized == t_spaces):
                    print(f"DEBUG: Found by enhanced type match, returning: {bt_row.code}")
                    return bt_row.code
                
                # Check categories with normalization
                for cat, cat_space in zip(cats, cats_spaces):
                    if (s in cat or 
                        s_normalized in cat or 
                        s in cat_space or 
                        s_normalized in cat_space):
                        print(f"DEBUG: Found by enhanced category match, returning: {bt_row.code}")
                        return bt_row.code
        
        # Special cases
        if any(k in (s or '') for k in ['medical', 'pharmacy', 'health']):
            return 'R09'
        if category:
            c_l = str(category).strip().lower()
            if any(k in c_l for k in ['medical', 'pharmacy', 'health']):
                return 'R09'
            
    except Exception as e:
        print(f"Error in _map_business_type_code: {str(e)}")
        import traceback
        traceback.print_exc()
        
    print(f"DEBUG: No match found, returning 'OTH'")
    return "OTH"

@swagger_auto_schema(method='POST', tags=['Business'])
@api_view(["POST"])  # /kirazee/api/v1/admin/business-applications/<str:application_id>/review
@parser_classes([JSONParser])
def admin_review_application(request, application_id: str):
    action = request.data.get("action")
    admin_id = request.data.get("admin_id")
    comments = request.data.get("comments")
    
    # Support both old format (arrays) and new format (objects with template/custom data)
    rejection_reasons = request.data.get("rejection_reasons", [])
    required_changes = request.data.get("required_changes", [])
    business_id_assignment = request.data.get("business_id_assignment")

    if action not in ["approve", "reject", "request_changes"]:
        return Response({"error": "Invalid action"}, status=status.HTTP_400_BAD_REQUEST)

    app = get_object_or_404(BusinessApplication, application_id=application_id)

    s1 = ApplicationStep.objects.filter(application=app, step_number=1).first()
    s3 = ApplicationStep.objects.filter(application=app, step_number=3).first()

    email_sent_flag = False
    in_app_sent_flag = False
    
    # Process reasons to extract titles for display
    processed_rejection_reasons = []
    processed_required_changes = []
    
    if action == "reject" and rejection_reasons:
        processed_rejection_reasons = _process_review_reasons(rejection_reasons)
    elif action == "request_changes" and required_changes:
        processed_required_changes = _process_review_reasons(required_changes)
    
    with transaction.atomic():
        if action == "approve":
            # Check if business already exists for this application
            existing_business_mapping = BusinessMapping.objects.filter(user=app.user).first()
            if existing_business_mapping and app.status == "approved":
                # Business already exists and application is already approved - update existing business
                new_business = existing_business_mapping.business
                new_business_id = new_business.business_id
                
                # Update existing business with new data
                data1 = s1.step_data if s1 and s1.step_data else {}
                data3 = s3.step_data if s3 and s3.step_data else {}

                addr = data1.get('address') if isinstance(data1.get('address'), dict) else {}
                address_text = (
                    (addr.get('address') or addr.get('street') or addr.get('formatted_address')) if isinstance(addr, dict) else None
                )
                city = addr.get('city') if isinstance(addr, dict) else None
                state = addr.get('state') if isinstance(addr, dict) else None
                pincode = addr.get('pincode') if isinstance(addr, dict) else None
                latitude = (addr.get('latitude') or addr.get('lat')) if isinstance(addr, dict) else None
                longitude = (addr.get('longitude') or addr.get('lng') or addr.get('lon')) if isinstance(addr, dict) else None

                business_name = data1.get('business_name') or f"Business_{app.user.user_id}"
                incoming_bt = (request.data.get('business_type') or data1.get('business_type'))
                incoming_cat = (request.data.get('category') or request.data.get('business_category') or data1.get('category') or data1.get('business_category') or incoming_bt)
                bt_code_override = request.data.get('business_type_code')
                business_type_code = bt_code_override or _map_business_type_code(incoming_bt, incoming_cat)
                business_category = (incoming_cat or 'OTH')
                description = data1.get('store_description')
                owner_email = getattr(app.user, 'emailID', None)
                owner_mobile = getattr(app.user, 'mobileNumber', None)
                working_hours = data3.get('working_hours') if data3 else None

                # Update existing business - only set is_verified=True, keep status and paymentstatus unchanged
                new_business.businessName = business_name
                new_business.businessType = business_type_code
                new_business.businessCategory = str(business_category).title()
                new_business.businessEmail = owner_email
                new_business.businessNumber = owner_mobile
                new_business.businessWhatsapp = owner_mobile
                new_business.description = description
                new_business.address = address_text
                new_business.city = city
                new_business.state = state
                new_business.pincode = pincode
                new_business.latitude = latitude
                new_business.longitude = longitude
                new_business.business_hours = working_hours
                new_business.is_verified = True  # Only set is_verified=True for existing businesses
                new_business.save()
                
                # Transfer financial details from temporary record to existing business record
                try:
                    temp_business_id = f"TEMP_{app.application_id}"
                    temp_financial = BusinessFinancial.objects.filter(business_id=temp_business_id).first()
                    
                    if temp_financial:
                        # Update the existing business financial record with data from temp record
                        actual_financial, created = BusinessFinancial.objects.get_or_create(
                            business=new_business,
                            defaults={
                                'owner_pan': temp_financial.owner_pan,
                                'gstin': temp_financial.gstin,
                                'account_number': temp_financial.account_number,
                                'ifsc_code': temp_financial.ifsc_code,
                                'razor_pay_key_id': getattr(settings, 'RAZORPAY_KEY_ID', ''),
                                'razor_pay_key_code': getattr(settings, 'RAZORPAY_KEY_SECRET', ''),
                                'razor_webhook_secret': getattr(settings, 'RAZORPAY_WEBHOOK_SECRET', ''),
                                'fssai_certification_number': None,
                            }
                        )
                        
                        if not created:
                            # Update existing financial record
                            actual_financial.owner_pan = temp_financial.owner_pan
                            actual_financial.gstin = temp_financial.gstin
                            actual_financial.account_number = temp_financial.account_number
                            actual_financial.ifsc_code = temp_financial.ifsc_code
                            actual_financial.save()
                        
                        # Delete the temporary record
                        temp_financial.delete()
                        
                        logger.info(f"Transferred financial details from TEMP_{app.application_id} to existing business {new_business_id}")
                except Exception as e:
                    logger.error(f"Error transferring financial details for application {app.application_id}: {str(e)}")
                    # Don't fail the approval process if financial transfer fails
                
                # Update reviewed_at timestamp
                app.reviewed_at = timezone.now()
                app.save(update_fields=["reviewed_at", "updated_at"])
                
                # Create admin review record for this update
                admin_review = AdminReview.objects.create(
                    application=app,
                    admin_id=admin_id or "ADMIN",
                    action=action,
                    comments=comments or "Updated existing business with new data",
                    rejection_reasons=None,
                    required_changes=None,
                    business_id_assignment=new_business_id,
                )
                
                return Response({
                    "success": True,
                    "data": {
                        "application_id": app.application_id,
                        "business_id": new_business_id,
                        "new_status": app.status,
                        "reviewed_at": app.reviewed_at.isoformat() if app.reviewed_at else None,
                        "reviewed_by": admin_id or "ADMIN",
                        "message": "Existing business updated with new data",
                        "updated_fields": ["businessName", "businessType", "businessCategory", "address", "contact_info"]
                    }
                })
            
            data1 = s1.step_data if s1 and s1.step_data else {}
            data3 = s3.step_data if s3 and s3.step_data else {}

            # Check if user already has an existing business to determine hierarchy level
            existing_business_mapping = BusinessMapping.objects.filter(user=app.user).first()
            master_business_id = None
            business_level = 'master'
            
            if existing_business_mapping:
                # User already has a business, so this new business will be a sublevel
                master_business_id = existing_business_mapping.business.business_id
                business_level = 'sublevel'
                logger.info(f"User {app.user.user_id} has existing business {master_business_id}, new business will be sublevel")
            else:
                # User's first business - this will be master level
                logger.info(f"User {app.user.user_id} has no existing business, new business will be master level")
            
            # If business mapping exists but application status is not approved, use existing business
            if existing_business_mapping and app.status == "approved":
                new_business = existing_business_mapping.business
                new_business_id = new_business.business_id
            else:
                # Create new business with appropriate hierarchy
                now_ts = timezone.now().strftime('%Y%m%d%H%M%S')
                new_business_id = business_id_assignment or f"KIR{app.user.user_id}{now_ts}"
                if Business.objects.filter(business_id=new_business_id).exists():
                    new_business_id = f"{new_business_id}{uuid.uuid4().hex[:4].upper()}"

                addr = data1.get('address') if isinstance(data1.get('address'), dict) else {}
                address_text = (
                    (addr.get('address') or addr.get('street') or addr.get('formatted_address')) if isinstance(addr, dict) else None
                )
                city = addr.get('city') if isinstance(addr, dict) else None
                state = addr.get('state') if isinstance(addr, dict) else None
                pincode = addr.get('pincode') if isinstance(addr, dict) else None
                latitude = (addr.get('latitude') or addr.get('lat')) if isinstance(addr, dict) else None
                longitude = (addr.get('longitude') or addr.get('lng') or addr.get('lon')) if isinstance(addr, dict) else None

                business_name = data1.get('business_name') or f"Business_{app.user.user_id}"
                incoming_bt = (request.data.get('business_type') or data1.get('business_type'))
                incoming_cat = (request.data.get('category') or request.data.get('business_category') or data1.get('category') or data1.get('business_category') or incoming_bt)
                bt_code_override = request.data.get('business_type_code')
                business_type_code = bt_code_override or _map_business_type_code(incoming_bt, incoming_cat)
                business_category = (incoming_cat or 'OTH')
                description = data1.get('store_description')
                owner_email = getattr(app.user, 'emailID', None)
                owner_mobile = getattr(app.user, 'mobileNumber', None)
                working_hours = data3.get('working_hours') if data3 else None

                new_business = Business.objects.create(
                    business_id=new_business_id,
                    level=business_level,
                    master=master_business_id,
                    businessName=business_name,
                    businessType=business_type_code,
                    businessCategory=str(business_category).title(),
                    businessEmail=owner_email,
                    businessNumber=owner_mobile,
                    businessWhatsapp=owner_mobile,
                    description=description,
                    address=address_text,
                    city=city,
                    state=state,
                    pincode=pincode,
                    latitude=latitude,
                    longitude=longitude,
                    business_hours=working_hours,
                    status=(business_type_code == 'R02'),
                    paymentstatus=False,
                    is_verified=True
                )

                BusinessMapping.objects.update_or_create(
                    user=app.user,
                    defaults={"business": new_business}
                )

                BusinessFinancial.objects.get_or_create(
                    business=new_business,
                    defaults={
                        'owner_pan': None,
                        'gstin': None,
                        'ifsc_code': None,
                        'account_number': None,
                        'razor_pay_key_id': getattr(settings, 'RAZORPAY_KEY_ID', ''),
                        'razor_pay_key_code': getattr(settings, 'RAZORPAY_KEY_SECRET', ''),
                        'razor_webhook_secret': getattr(settings, 'RAZORPAY_WEBHOOK_SECRET', ''),
                        'fssai_certification_number': None,
                    }
                )
                
                # Transfer financial details from temporary record to actual business record
                try:
                    temp_business_id = f"TEMP_{app.application_id}"
                    temp_financial = BusinessFinancial.objects.filter(business_id=temp_business_id).first()
                    
                    if temp_financial:
                        # Update the actual business financial record with data from temp record
                        actual_financial = BusinessFinancial.objects.get(business=new_business)
                        actual_financial.owner_pan = temp_financial.owner_pan
                        actual_financial.gstin = temp_financial.gstin
                        actual_financial.account_number = temp_financial.account_number
                        actual_financial.ifsc_code = temp_financial.ifsc_code
                        actual_financial.save()
                        
                        # Delete the temporary record
                        temp_financial.delete()
                        
                        logger.info(f"Transferred financial details from TEMP_{app.application_id} to {new_business_id}")
                except Exception as e:
                    logger.error(f"Error transferring financial details for application {app.application_id}: {str(e)}")
                    # Don't fail the approval process if financial transfer fails
            payment_amount = getattr(settings, 'BUSINESS_SETUP_FEE', None)
            payment_url = None
            try:
                if payment_amount is not None:
                    pg_path = reverse('payment_gateway')
                    payment_url = request.build_absolute_uri(f"{pg_path}?userID={app.user.user_id}&amount={payment_amount}&business_id={new_business_id}")
            except Exception:
                payment_url = None
            app.status = "approved"
            app.reviewed_at = timezone.now()
            app.rejection_reasons = None
            app.save(update_fields=["status", "reviewed_at", "rejection_reasons", "updated_at"])

            # Create admin review
            admin_review = AdminReview.objects.create(
                application=app,
                admin_id=admin_id or "ADMIN",
                action=action,
                comments=comments,
                rejection_reasons=None,
                required_changes=None,
                business_id_assignment=new_business_id,
            )

            try:
                recipient = Registration.objects.filter(user_id=app.user.user_id).values_list('emailID', flat=True).first()
                if recipient:
                    subject = "Your Kirazee business has been approved"
                    from_email = getattr(settings, 'DEFAULT_FROM_EMAIL', None) or getattr(settings, 'EMAIL_HOST_USER', None) or 'no-reply@kirazee.com'
                    owner_name = (app.user.displayName if hasattr(app.user, 'displayName') and app.user.displayName else f"{app.user.firstName} {app.user.lastName}").strip()
                    business_name = _get_application_business_name(app)
                    dashboard_url = f"{settings.BASE_URL}/#/business-setup/step-1"
                    html_content = f"""
                    <div style=\"max-width:640px;margin:0 auto;background:#ffffff;border:1px solid #e2e8f0;border-radius:12px;overflow:hidden;font-family:Segoe UI,Roboto,Arial,sans-serif;color:#1f2937\">
                      <div style=\"background:linear-gradient(135deg,#FF6B35 0%,#1e293b 100%);padding:24px 28px;color:#fff\">
                        <div style=\"font-size:20px;font-weight:700\">Kirazee • Business Platform</div>
                        <div style=\"opacity:.9;margin-top:4px\">Business Approval</div>
                      </div>
                      <div style=\"padding:24px 28px\">
                        <p style=\"margin:0 0 12px\">Hi {owner_name},</p>
                        <p style=\"margin:0 0 18px\">Great news! Your onboarding request for <strong>{business_name}</strong> has been approved.</p>
                        <a href=\"{dashboard_url}\" target=\"_blank\" style=\"display:inline-block;background:#FF6B35;color:#fff;text-decoration:none;padding:10px 16px;border-radius:8px;font-weight:600\">Setup your Business now</a>
                        <div style=\"margin-top:20px;padding:12px 14px;border-radius:10px;background:#fff7ed;border:1px solid #fed7aa;color:#9a3412\">Next: set up your catalog, delivery settings, and start accepting orders.</div>
                        <p style=\"margin:18px 0 0;color:#6b7280;font-size:12px\">If you have any questions, reply to this email and our team will assist you.</p>
                      </div>
                      <div style=\"padding:14px 20px;background:#f8fafc;border-top:1px solid #e2e8f0;color:#64748b;font-size:12px;text-align:center\">{timezone.now().year} Kirazee. All rights reserved.</div>
                    </div>
                    """
                    text_content = (
                        f"Hi {owner_name},\n\n"
                        f"Your business onboarding request for {business_name} has been approved.\n"
                        f"Open your dashboard: {dashboard_url}\n"
                    )
                    sent = send_mail(subject, text_content, from_email, [recipient], html_message=html_content, fail_silently=False)
                    email_sent_flag = bool(sent)
            except Exception:
                email_sent_flag = False
            
            try:
                business_name = _get_application_business_name(app)
                title = "Business Approved"
                body = f"Your onboarding for {business_name} has been approved."
                data = {"type": "ONBOARDING_APPROVED", "application_id": app.application_id, "notification_for": "business_owner"}
                send_order_notification(app.user.user_id, title, body, data)
                in_app_sent_flag = True
            except Exception:
                in_app_sent_flag = False

            return Response({
                "success": True,
                "data": {
                    "application_id": app.application_id,
                    "business_id": new_business_id,
                    "new_status": "approved",
                    "reviewed_at": app.reviewed_at.isoformat() if app.reviewed_at else None,
                    "reviewed_by": admin_id or "ADMIN",
                    "notifications_sent": {"email": email_sent_flag, "in_app": in_app_sent_flag, "whatsapp": True, "sms": False},
                    "payment": {"amount": payment_amount, "url": payment_url}
                }
            })

        elif action == "reject":
            app.status = "rejected"
            app.reviewed_at = timezone.now()
            app.rejection_reasons = processed_rejection_reasons or None
            app.save(update_fields=["status", "reviewed_at", "rejection_reasons", "updated_at"])
            
            # Create admin review
            admin_review = AdminReview.objects.create(
                application=app,
                admin_id=admin_id or "ADMIN",
                action=action,
                comments=comments,
                rejection_reasons=processed_rejection_reasons or None,
                required_changes=None,
                business_id_assignment=business_id_assignment
            )
            
            # Create custom reason records
            # _create_custom_reasons(admin_review, 'rejection', rejection_reasons)
            
            try:
                recipient = Registration.objects.filter(user_id=app.user.user_id).values_list('emailID', flat=True).first()
                if recipient:
                    subject = "Your Kirazee business application has been rejected"
                    from_email = getattr(settings, 'DEFAULT_FROM_EMAIL', None) or getattr(settings, 'EMAIL_HOST_USER', None) or 'no-reply@kirazee.com'
                    owner_name = (app.user.displayName if hasattr(app.user, 'displayName') and app.user.displayName else f"{app.user.firstName} {app.user.lastName}").strip()
                    business_name = _get_application_business_name(app)
                    reason_text = "\n- " + "\n- ".join(processed_rejection_reasons) if processed_rejection_reasons else ""
                    html_reasons = "".join([f"<li>{r}</li>" for r in (processed_rejection_reasons or [])])
                    html_content = f"""
                    <div style="max-width:640px;margin:0 auto;background:#ffffff;border:1px solid #e2e8f0;border-radius:12px;overflow:hidden;font-family:Segoe UI,Roboto,Arial,sans-serif;color:#1f2937">
                      <div style="background:linear-gradient(135deg,#FF6B35 0%,#1e293b 100%);padding:24px 28px;color:#fff">
                        <div style="font-size:20px;font-weight:700">Kirazee • Business Platform</div>
                        <div style="opacity:.9;margin-top:4px">Application Rejected</div>
                      </div>
                      <div style="padding:24px 28px">
                        <p>Hi {owner_name},</p>
                        <p style="margin:10px 0 14px">Your onboarding request for <strong>{business_name}</strong> wasn't approved.</p>
                        {("<ul style='margin:0 0 12px 18px;color:#334155'>" + html_reasons + "</ul>") if html_reasons else ""}
                        <div style="margin-top:8px;padding:12px 14px;border-radius:10px;background:#fef2f2;border:1px solid #fecaca;color:#991b1b">Please update details and resubmit your application.</div>
                      </div>
                      <div style="padding:14px 20px;background:#f8fafc;border-top:1px solid #e2e8f0;color:#64748b;font-size:12px;text-align:center">{timezone.now().year} Kirazee. All rights reserved.</div>
                    </div>
                    """
                    text_content = (
                        f"Hi {owner_name},\n\n"
                        f"Your onboarding request for {business_name} has been rejected.\n"
                        + (f"Reasons:{reason_text}\n" if reason_text else "")
                    )
                    sent = send_mail(subject, text_content, from_email, [recipient], html_message=html_content, fail_silently=False)
                    email_sent_flag = bool(sent)
            except Exception:
                email_sent_flag = False

            try:
                business_name = _get_application_business_name(app)
                title = "Application Rejected"
                body = f"Your onboarding for {business_name} was not approved."
                data = {"type": "ONBOARDING_REJECTED", "application_id": app.application_id, "notification_for": "business_owner", "reasons": (processed_rejection_reasons or [])}
                send_order_notification(app.user.user_id, title, body, data)
                in_app_sent_flag = True
            except Exception:
                in_app_sent_flag = False

        elif action == "request_changes":
            app.status = "requires_changes"
            app.reviewed_at = timezone.now()
            app.rejection_reasons = None
            app.save(update_fields=["status", "reviewed_at", "rejection_reasons", "updated_at"])
            
            # Create admin review
            admin_review = AdminReview.objects.create(
                application=app,
                admin_id=admin_id or "ADMIN",
                action=action,
                comments=comments,
                rejection_reasons=None,
                required_changes=processed_required_changes or None,
                business_id_assignment=business_id_assignment
            )
            
            # Create custom reason records
            # _create_custom_reasons(admin_review, 'required_changes', required_changes)
            
            try:
                recipient = Registration.objects.filter(user_id=app.user.user_id).values_list('emailID', flat=True).first()
                if recipient:
                    subject = "Changes required for your Kirazee business application"
                    from_email = getattr(settings, 'DEFAULT_FROM_EMAIL', None) or getattr(settings, 'EMAIL_HOST_USER', None) or 'no-reply@kirazee.com'
                    owner_name = (app.user.displayName if hasattr(app.user, 'displayName') and app.user.displayName else f"{app.user.firstName} {app.user.lastName}").strip()
                    business_name = _get_application_business_name(app)
                    change_items = "".join([f"<li>{c}</li>" for c in (processed_required_changes or [])])
                    html_content = f"""
                    <div style="max-width:640px;margin:0 auto;background:#ffffff;border:1px solid #e2e8f0;border-radius:12px;overflow:hidden;font-family:Segoe UI,Roboto,Arial,sans-serif;color:#1f2937">
                      <div style="background:linear-gradient(135deg,#FF6B35 0%,#1e293b 100%);padding:24px 28px;color:#fff">
                        <div style="font-size:20px;font-weight:700">Kirazee • Business Platform</div>
                        <div style="opacity:.9;margin-top:4px">Action Required</div>
                      </div>
                      <div style="padding:24px 28px">
                        <p>Hi {owner_name},</p>
                        <p style="margin:10px 0 14px">We reviewed your onboarding request for <strong>{business_name}</strong>. Please address the following and resubmit:</p>
                        {("<ul style='margin:0 0 12px 18px;color:#334155'>" + change_items + "</ul>") if change_items else ""}
                        <div style="margin-top:8px;padding:12px 14px;border-radius:10px;background:#fff7ed;border:1px solid #fed7aa;color:#9a3412">Update the requested items and submit again for review.</div>
                      </div>
                      <div style="padding:14px 20px;background:#f8fafc;border-top:1px solid #e2e8f0;color:#64748b;font-size:12px;text-align:center">{timezone.now().year} Kirazee. All rights reserved.</div>
                    </div>
                    """
                    text_content = (
                        f"Hi {owner_name},\n\n"
                        f"Changes requested for your application {business_name}.\n"
                        + ("\n".join([f"- {c}" for c in (processed_required_changes or [])]))
                    )
                    sent = send_mail(subject, text_content, from_email, [recipient], html_message=html_content, fail_silently=False)
                    email_sent_flag = bool(sent)
            except Exception:
                email_sent_flag = False

            try:
                business_name = _get_application_business_name(app)
                title = "Changes Required"
                body = f"Please update your application for {business_name} as requested."
                data = {"type": "ONBOARDING_CHANGES_REQUESTED", "application_id": app.application_id, "notification_for": "business_owner", "required_changes": (processed_required_changes or [])}
                send_order_notification(app.user.user_id, title, body, data)
                in_app_sent_flag = True
            except Exception:
                in_app_sent_flag = False

    return Response({
        "success": True,
        "data": {
            "application_id": app.application_id,
            "new_status": app.status,
            "reviewed_at": app.reviewed_at.isoformat() if app.reviewed_at else None,
            "reviewed_by": admin_id or "ADMIN",
            "notifications_sent": {"email": email_sent_flag, "in_app": in_app_sent_flag},
            "rejection_reasons": (processed_rejection_reasons or None) if action == "reject" else None,
            "required_changes": (processed_required_changes or None) if action == "request_changes" else None
        }
    })


def _process_review_reasons(reasons_data):
    """Process reasons from frontend - support both template IDs and custom text"""
    processed = []
    
    for reason in reasons_data:
        if isinstance(reason, str):
            # Legacy format - just string
            processed.append(reason)
        elif isinstance(reason, dict):
            # New format - could be template_id or custom text
            if 'template_id' in reason:
                # Template-based reason
                try:
                    template = ReviewReasonTemplate.objects.get(id=reason['template_id'])
                    processed.append(template.title)
                except ReviewReasonTemplate.DoesNotExist:
                    # Fallback to custom text if template not found
                    processed.append(reason.get('title', reason.get('text', '')))
            else:
                # Custom reason
                title = reason.get('title', reason.get('text', ''))
                if title:
                    processed.append(title)
    
    return processed


def _create_custom_reasons(admin_review, reason_type, reasons_data):
    """Create CustomReviewReason records for tracking"""
    for reason in reasons_data:
        if isinstance(reason, dict):
            template_instance = None
            is_template_based = False
            
            if 'template_id' in reason:
                try:
                    template_instance = ReviewReasonTemplate.objects.get(id=reason['template_id'])
                    is_template_based = True
                except ReviewReasonTemplate.DoesNotExist:
                    # Template not found, treat as custom reason
                    template_instance = None
                    is_template_based = False
            
            CustomReviewReason.objects.create(
                admin_review=admin_review,
                reason_type=reason_type,
                title=reason.get('title', reason.get('text', '')),
                description=reason.get('description', ''),
                is_template_based=is_template_based,
                template=template_instance
            )

@swagger_auto_schema(method='POST', tags=['Business'])
@api_view(["POST"])  # /kirazee/api/v1/business-onboarding/auto-save
@parser_classes([JSONParser])
def autosave(request):
    application_id = request.data.get("application_id")
    user_id = request.data.get("user_id")
    step_number = int(request.data.get("step", 0))
    form_data = request.data.get("form_data", {})

    if not application_id or not user_id or step_number not in [1, 2, 3]:
        return Response({"error": "application_id, user_id and valid step are required"}, status=status.HTTP_400_BAD_REQUEST)

    app = get_object_or_404(BusinessApplication, application_id=application_id)
    if app.user.user_id != int(user_id):
        return Response({"error": "Application does not belong to user"}, status=status.HTTP_403_FORBIDDEN)

    step, _ = ApplicationStep.objects.get_or_create(application=app, step_number=step_number)
    step.step_data = form_data
    step.data_saved = True
    step.save()

    app.last_activity = timezone.now()
    app.save(update_fields=["last_activity", "updated_at"])

    return Response({"success": True, "message": "Auto-saved", "timestamp": timezone.now().isoformat()})

@swagger_auto_schema(method='POST', tags=['Business'])
@api_view(["POST"])  # /kirazee/api/v1/business-onboarding/heartbeat
@parser_classes([JSONParser])
def heartbeat(request):
    application_id = request.data.get("application_id")
    user_id = request.data.get("user_id")
    current_step = int(request.data.get("current_step", 1))

    if not application_id or not user_id:
        return Response({"error": "application_id and user_id are required"}, status=status.HTTP_400_BAD_REQUEST)

    app = get_object_or_404(BusinessApplication, application_id=application_id)
    if app.user.user_id != int(user_id):
        return Response({"error": "Application does not belong to user"}, status=status.HTTP_403_FORBIDDEN)

    app.current_step = max(app.current_step, current_step)
    app.last_activity = timezone.now()
    app.save(update_fields=["current_step", "last_activity", "updated_at"])

    return Response({"success": True, "message": "Heartbeat recorded"})

@swagger_auto_schema(method='GET', tags=['Business'])
@api_view(["GET"])  # /kirazee/api/v1/business-onboarding/config/business-types
def onboarding_config_business_types(request):
    base_common_fields = {
        "step_1": [
            {"field": "business_name", "label": "Business Name", "type": "text", "required": True},
            {"field": "business_type", "label": "Business Type", "type": "dropdown", "required": True},
            {"field": "category", "label": "Category", "type": "dropdown", "required": False},
            {"field": "description", "label": "Business Description", "type": "textarea", "required": False},
            {"field": "address", "label": "Business Address", "type": "address", "required": True}
        ],
        "step_2": [
            {"field": "business_registration_certificate", "label": "Business Registration Certificate", "type": "file", "required": True, "validation": {"max_size_mb": 5, "formats": ["jpg", "png", "pdf"]}},
            {"field": "owner_id_proof", "label": "Owner ID Proof", "type": "file", "required": True, "validation": {"max_size_mb": 5, "formats": ["jpg", "png", "pdf"]}},
            {"field": "pan_card", "label": "PAN Card", "type": "file", "required": True, "validation": {"max_size_mb": 5, "formats": ["jpg", "png", "pdf"]}},
            {"field": "bank_proof", "label": "Bank Account Proof", "type": "file", "required": True, "validation": {"max_size_mb": 5, "formats": ["jpg", "png", "pdf"]}},
            {"field": "gst_certificate", "label": "GST Certificate", "type": "file", "required": False, "validation": {"max_size_mb": 5, "formats": ["jpg", "png", "pdf"]}}
        ],
        "step_3": [
            {"field": "working_hours", "label": "Working Hours", "type": "time_range", "required": False},
            {"field": "payment_methods", "label": "Accepted Payment Methods", "type": "multi_select", "required": False},
            {"field": "delivery_preferences", "label": "Delivery Preferences", "type": "multi_select", "required": False}
        ]
    }

    business_types = [
        {
            "type": "retail_and_wholesale",
            "display_label": "Shop / Store",
            "label": "Retail and Wholesale",
            "common_fields": base_common_fields,
            "specific_fields": {
                "step_1": [
                    {"field": "registration_number", "label": "Registration Number", "type": "text", "required": False}
                ],
                "step_2": [
                    {"field": "store_photo", "label": "Store Photo", "type": "file", "required": True, "validation": {"max_size_mb": 5, "formats": ["jpg", "png"]}},
                ]
            }
        },
        {
            "type": "food_and_beverage",
            "display_label": "Restaurant / Café",
            "label": "Food and Beverage",
            "common_fields": {
                "step_1": [
                    {"field": "business_name", "label": "Restaurant Name", "type": "text", "required": True},
                    {"field": "business_type", "label": "Business Type", "type": "dropdown", "required": True},
                    {"field": "category", "label": "Category", "type": "dropdown", "required": False},
                    {"field": "description", "label": "About the Restaurant", "type": "textarea", "required": False},
                    {"field": "address", "label": "Restaurant Address", "type": "address", "required": True}
                ],
                "step_2": [
                    {"field": "business_registration_certificate", "label": "Business Registration Certificate", "type": "file", "required": True, "validation": {"max_size_mb": 5, "formats": ["jpg", "png", "pdf"]}},
                    {"field": "owner_id_proof", "label": "Owner ID Proof", "type": "file", "required": True, "validation": {"max_size_mb": 5, "formats": ["jpg", "png", "pdf"]}},
                    {"field": "pan_card", "label": "PAN Card", "type": "file", "required": True, "validation": {"max_size_mb": 5, "formats": ["jpg", "png", "pdf"]}},
                    {"field": "bank_proof", "label": "Bank Account Proof", "type": "file", "required": True, "validation": {"max_size_mb": 5, "formats": ["jpg", "png", "pdf"]}},
                    {"field": "gst_certificate", "label": "GST Certificate", "type": "file", "required": False, "validation": {"max_size_mb": 5, "formats": ["jpg", "png", "pdf"]}}
                ],
                "step_3": [
                    {"field": "working_hours", "label": "Opening Hours", "type": "time_range", "required": False},
                    {"field": "payment_methods", "label": "Payment Methods", "type": "multi_select", "required": False},
                    {"field": "delivery_preferences", "label": "Delivery Options", "type": "multi_select", "required": False}
                ]
            },
            "specific_fields": {
                "step_1": [
                    {"field": "fssai_number", "label": "FSSAI Registration Number", "type": "text", "required": True}
                ],
                "step_2": [
                    {"field": "fssai_certificate", "label": "FSSAI Food License", "type": "file", "required": True, "validation": {"max_size_mb": 5, "formats": ["jpg", "png", "pdf"]}},
                    {"field": "store_photo", "label": "Restaurant Photo", "type": "file", "required": True, "validation": {"max_size_mb": 5, "formats": ["jpg", "png"]}},
                ]
            }
        },
        {
            "type": "fashion_retail",
            "display_label": "Boutique / Fashion Store",
            "label": "Fashion Retail",
            "common_fields": "inherit",
            "specific_fields": {
                "step_2": [
                    {"field": "store_photo", "label": "Store Photo", "type": "file", "required": True, "validation": {"max_size_mb": 5, "formats": ["jpg", "png"]}},
                    {"field": "brand_authorization_certificate", "label": "Brand Authorization Certificate", "type": "file", "required": False, "validation": {"max_size_mb": 5, "formats": ["jpg", "png", "pdf"]}}
                ]
            }
        },
        {
            "type": "pharmacy_and_healthcare",
            "display_label": "Pharmacy / Healthcare Store",
            "label": "Pharmacy and Healthcare",
            "common_fields": "inherit",
            "specific_fields": {
                "step_2": [
                    {"field": "store_photo", "label": "Pharmacy Photo", "type": "file", "required": True, "validation": {"max_size_mb": 5, "formats": ["jpg", "png"]}},
                    {"field": "drug_license_number", "label": "Drug License Number", "type": "text", "required": True},
                    {"field": "drug_license_certificate", "label": "Drug License Certificate", "type": "file", "required": True, "validation": {"max_size_mb": 5, "formats": ["jpg", "png", "pdf"]}}
                ]
            }
        }
    ]

    return Response({"success": True, "business_types": business_types})

@swagger_auto_schema(method='GET', tags=['Business'])
@api_view(["GET"])
def step3_get_data(request, application_id: str):
    """
    Get step 3 data for a specific application
    """
    try:
        application = BusinessApplication.objects.get(application_id=application_id)
        
        # Get step 3 data from ApplicationStep
        step3_data = {}
        
        try:
            step3 = ApplicationStep.objects.get(application=application, step_number=3)
            if step3.step_data:
                step3_data = step3.step_data
        except ApplicationStep.DoesNotExist:
            # Step 3 doesn't exist yet, return empty data
            step3_data = {}
        
        # Extract common fields for backward compatibility
        response_data = {}
        
        # Working hours
        if step3_data.get('working_hours'):
            response_data['working_hours'] = step3_data['working_hours']
        
        # Payment methods  
        if step3_data.get('payment_methods'):
            response_data['payment_methods'] = step3_data['payment_methods']
            
        # Delivery preferences
        if step3_data.get('delivery_preferences'):
            response_data['delivery_preferences'] = step3_data['delivery_preferences']
            
        # Additional operational details
        if step3_data.get('operational_details'):
            response_data['operational_details'] = step3_data['operational_details']
            
        # Include all step3_data for completeness
        response_data.update(step3_data)

        return Response({
            "success": True,
            "data": response_data,
            "application_id": application_id
        })
        
    except BusinessApplication.DoesNotExist:
        return Response({
            "success": False,
            "message": "Application not found"
        }, status=status.HTTP_404_NOT_FOUND)
    except Exception as e:
        logger.error(f"Error fetching step3 data for {application_id}: {str(e)}")
        import traceback
        traceback.print_exc()
        return Response({
            "success": False,
            "message": f"Failed to fetch step 3 data: {str(e)}"
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

@swagger_auto_schema(method='POST', tags=['Business'])
@api_view(["POST"])
def validate_gstin(request):
    """
    Validate GSTIN number and check if it already exists in database
    """
    try:
        gstin = request.data.get('gstin', '').strip().upper()
        
        if not gstin:
            return Response({
                "success": False,
                "message": "GSTIN is required"
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Check if GSTIN already exists in business_financials table
        from kirazee_app.models import BusinessFinancial
        existing_gstin = BusinessFinancial.objects.filter(gstin=gstin).first()
        
        if existing_gstin:
            # GSTIN already exists, return the business details
            return Response({
                "success": False,
                "message": "GSTIN already exists in the system",
                "gstin_exists": True,
                "existing_business": {
                    "business_id": existing_gstin.business_id,
                    "gstin": existing_gstin.gstin
                }
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # GSTIN is available for use
        
        return Response({
            "success": True,
            "message": "GSTIN is available",
            "gstin": gstin,
            "state_code": gstin[:2],
            "pan_part": gstin[2:12],
            "gstin_exists": False
        })
        
    except Exception as e:
        logger.error(f"Error validating GSTIN: {str(e)}")
        return Response({
            "success": False,
            "message": "Failed to validate GSTIN"
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

@swagger_auto_schema(method='POST', tags=['Business'])
@api_view(["POST"])
def validate_financial_details(request):
    try:
        bank_account = request.data.get('bank_account', '').strip()
        ifsc_code = request.data.get('ifsc_code', '').strip().upper()
        account_holder_name = request.data.get('account_holder_name', '').strip()
        account_holder_name = request.data.get('account_holder_name', '').strip()
                
        errors = []
                
        # Validate bank account number
        if not bank_account:
            errors.append("Bank account number is required")
        elif len(bank_account) < 9 or len(bank_account) > 18:
            errors.append("Bank account number must be between 9 and 18 digits")
        elif not bank_account.isdigit():
            errors.append("Bank account number must contain only digits")
                
        # Validate IFSC code
        if not ifsc_code:
            errors.append("IFSC code is required")
        elif len(ifsc_code) != 11:
            errors.append("IFSC code must be 11 characters long")
        elif not ifsc_code[:4].isalpha():   
            errors.append("First 4 characters of IFSC must be alphabetic (bank code)")
        elif not ifsc_code[4].isdigit():
            errors.append("5th character of IFSC must be '0'")
        elif not ifsc_code[5:].isalpha():
            errors.append("Last 6 characters of IFSC must be alphabetic (branch code)")
                
        # Validate account holder name
        if not account_holder_name:
            errors.append("Account holder name is required")
        elif len(account_holder_name) < 3:
            errors.append("Account holder name must be at least 3 characters long")
        elif not account_holder_name.replace(' ', '').isalpha():
            errors.append("Account holder name should contain only alphabets and spaces")
                
        if errors:
            return Response({
                "success": False,
                "message": "Validation failed",
                "errors": errors
            }, status=status.HTTP_400_BAD_REQUEST)
                
        # Optional: You can integrate with bank API for real validation
        # For now, just return format validation success
                
        # Extract bank code from IFSC
        bank_code = ifsc_code[:4]
        branch_code = ifsc_code[5:]
                
        return Response({
        "success": True,
        "message": "Financial details are valid",
        "validated_data": {
        "bank_account": bank_account,
        "ifsc_code": ifsc_code,
        "account_holder_name": account_holder_name,
        "bank_code": bank_code,
        "branch_code": branch_code
        }
        })
            
    except Exception as e:
        logger.error(f"Error validating financial details: {str(e)}")
        return Response({
        "success": False,
        "message": "Failed to validate financial details"
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)