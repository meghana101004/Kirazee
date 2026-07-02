# collegues_views.py
from kirazee_app.business_utils import resolve_subcategory_name
from requests import api
from rest_framework.decorators import api_view, parser_classes
from rest_framework import status
from rest_framework.response import Response
from rest_framework.parsers import MultiPartParser, FormParser, JSONParser
from rest_framework.views import APIView
from drf_yasg.utils import swagger_auto_schema
from drf_yasg import openapi
from decimal import Decimal
from kirazee_app.models import BusinessType, BusinessFeature, Business, BusinessMapping, Registration, BusinessOwnerDetails, BusinessFinancial
from .serializers import (
    BusinessTypeSerializer, BusinessFeatureSerializer, 
    Businesssection1serializers, Businesssection2Serializer, 
    Businesssection3Serializer, BusinessFinancialDetailSerializer,
    MenuItemsSerializer, MenuItemsWithVariantsSerializer, MenuItemVariantSerializer, BOMSerializer, productItemsSerializer,
    FashionProductSerializer, FashionProductVariantSerializer, FashionProductWithVariantsSerializer,
    GroceriesCategorySerializer, CountryandStatesSerializer, ProductCustomizationTemplateSerializer,
    )
from .models import MenuItemVariant
from consumer.gro_serializers import (
    GroceriesProductsSerializer,
    GroceriesProductVariantsSerializer,
    GroceriesProductWithPricingSerializer,
    GroceriesCustomDesignsSerializer,
)
from consumer.gro_models import (
    GroceriesProducts,
    GroceriesCategories,
    GroceriesProductVariants,
    GroceriesCustomDesigns,
)
from .models import MenuItems, BOM, BillOfMaterialsLog, productItems, BusinessApplication, ApplicationStep, CountryandStates, FashionProduct, FashionProductVariant, UniversalCategory, ProductCustomizationTemplate
import json
import uuid
from .google_maps import parse_google_maps_url
from PIL import Image
from io import BytesIO
from django.core.files import File
from django.core.files.storage import default_storage
from business.image_utils import (
    build_s3_file_url,
    upload_image_to_s3,
    save_model_image_field,
    upload_multiple_images,
    upload_multiple_images_as_array,
    compress_image as utils_compress_image
)
import os
import time
import csv
import io
from decimal import Decimal
from django.db import connection
from django.db.models import Q, F, ExpressionWrapper, DecimalField
from django.db import transaction
from django.conf import settings
from consumer.gro_views import GroceriesBulkUploadView
from django.db.models import Count, Value
from django.db.models.functions import Coalesce
import datetime, json, traceback
from consumer.serializers import BusinessSerializer
from consumer.combine import calculate_business_rating
from rest_framework.pagination import PageNumberPagination
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

def compress_image(image_file):
        """Compress image to 75% quality"""
        if not image_file:
            return None
            
        img = Image.open(image_file)
        # Convert RGBA to RGB if necessary
        if img.mode in ('RGBA', 'P'):
            img = img.convert('RGB')
            
        # Create a BytesIO object
        img_io = BytesIO()
        # Save image with 75% quality
        img.save(img_io, format='JPEG', quality=75, optimize=True)
        # Rewind buffer so subsequent reads write full content
        img_io.seek(0)
        # Create a new Django friendly File object
        new_image = File(img_io, name=image_file.name)
        return new_image

# Ensure DB stores names starting with 'media/' while physical storage remains under MEDIA_ROOT
def _prefix_media_if_needed(field_file):
    try:
        if not field_file:
            return
        name = str(field_file).replace('\\', '/').lstrip('/')
        if not name.startswith('media/'):
            field_file.name = f"media/{name}"
    except Exception:
        pass

@swagger_auto_schema(methods=['PUT'], tags=['Business'])
@api_view(["PUT"])
@parser_classes([MultiPartParser, FormParser, JSONParser])
def update_business_details(request):
    """
    Unified update endpoint for business owners after setup.
    Query params: userID
    Body: business_id and any combination of fields across sections 1, 2, and 3.
    Supports multipart for logo/banner along with JSON fields.
    """
    user_id = request.query_params.get('userID')
    business_id = request.data.get('business_id')

    if not user_id or not business_id:
        return Response({"error": "userID (query) and business_id (body) are required"}, status=status.HTTP_400_BAD_REQUEST)

    # Ownership and existence
    try:
        business = Business.objects.get(business_id=business_id)
    except Business.DoesNotExist:
        return Response({"error": "Business not found"}, status=status.HTTP_404_NOT_FOUND)

    if not BusinessMapping.objects.filter(user__user_id=user_id, business=business).exists():
        return Response({"error": "You don't have permission to edit this business"}, status=status.HTTP_403_FORBIDDEN)

    # Handle image compression if provided
    if 'logo' in request.FILES:
        request.FILES['logo'] = compress_image(request.FILES['logo'])
    if 'banner' in request.FILES:
        request.FILES['banner'] = compress_image(request.FILES['banner'])

    # SECTION 1 updates (basic/business details + images)
    section1_serializer = Businesssection1serializers(
        business,
        data=request.data,
        partial=True,
        context={"user_id": user_id, "request": request}
    )
    section1_data = None
    if section1_serializer.is_valid():
        # Save images using S3 helper
        if 'logo' in request.FILES:
            save_model_image_field(business, 'logo', request.FILES['logo'], 'business_logos')
        if 'banner' in request.FILES:
            save_model_image_field(business, 'banner', request.FILES['banner'], 'business_banners')
        
        updated_business = section1_serializer.save()
        section1_data = Businesssection1serializers(updated_business, context={"user_id": user_id, "request": request}).data
    else:
        return Response({"section1_errors": section1_serializer.errors}, status=status.HTTP_400_BAD_REQUEST)

    # SECTION 2 updates (address/contact/location)
    section2_serializer = Businesssection2Serializer(business, data=request.data, partial=True)
    section2_data = None
    if section2_serializer.is_valid():
        updated_business2 = section2_serializer.save()
        section2_data = section2_serializer.data
    else:
        return Response({"section2_errors": section2_serializer.errors}, status=status.HTTP_400_BAD_REQUEST)

    # SECTION 3 updates (financial)
    try:
        financial = BusinessFinancial.objects.get(business=business)
        section3_serializer = Businesssection3Serializer(financial, data=request.data, partial=True)
    except BusinessFinancial.DoesNotExist:
        payload = request.data.copy()
        payload['business_id'] = business_id
        section3_serializer = Businesssection3Serializer(data=payload)

    section3_data = None
    if section3_serializer.is_valid():
        updated_financial = section3_serializer.save()
        section3_data = BusinessFinancialDetailSerializer(updated_financial).data
    else:
        return Response({"section3_errors": section3_serializer.errors}, status=status.HTTP_400_BAD_REQUEST)

    return Response({
        "message": "Business details updated successfully",
        "business_id": business.business_id,
        "section1": section1_data,
        "section2": section2_data,
        "section3": section3_data
    }, status=status.HTTP_200_OK)

@swagger_auto_schema(methods=['PUT'], tags=['Business'])
@api_view(['PUT'])
@parser_classes([MultiPartParser, FormParser, JSONParser])
def owner_update_business_details(request):
    user_id = request.query_params.get('userID')
    business_id = request.data.get('business_id')
    if not user_id or not business_id:
        return Response({"error": "userID (query) and business_id (body) are required"}, status=status.HTTP_400_BAD_REQUEST)

    try:
        business = Business.objects.get(business_id=business_id)
    except Business.DoesNotExist:
        return Response({"error": "Business not found"}, status=status.HTTP_404_NOT_FOUND)

    if not BusinessMapping.objects.filter(user__user_id=user_id, business=business).exists():
        return Response({"error": "You don't have permission to edit this business"}, status=status.HTTP_403_FORBIDDEN)

    if 'logo' in request.FILES:
        request.FILES['logo'] = compress_image(request.FILES['logo'])
    if 'banner' in request.FILES:
        request.FILES['banner'] = compress_image(request.FILES['banner'])

    if 'logo' in request.FILES:
        save_model_image_field(business, 'logo', request.FILES['logo'], 'business_logos')

    if 'banner' in request.FILES:
        save_model_image_field(business, 'banner', request.FILES['banner'], 'business_banners')

    if request.data.get('logo') == 'null':
        if business.logo:
            business.logo.delete(save=False)
        business.logo = None

    if request.data.get('banner') == 'null':
        if business.banner:
            business.banner.delete(save=False)
        business.banner = None

    section1_fields = ['businessName', 'businessWhatsapp', 'description', 'business_hours']
    data1 = {k: request.data.get(k) for k in section1_fields if k in request.data}
    if data1:
        s1 = Businesssection1serializers(business, data=data1, partial=True, context={"user_id": user_id, "request": request})
        if not s1.is_valid():
            return Response({"errors": s1.errors}, status=status.HTTP_400_BAD_REQUEST)
        s1.save()

    section2_fields = ['location', 'address', 'landmark', 'city', 'state', 'pincode', 'contact_support', 'contact_mobile', 'website_url', 'latitude', 'longitude']
    data2 = {k: request.data.get(k) for k in section2_fields if k in request.data}
    if data2:
        s2 = Businesssection2Serializer(business, data=data2, partial=True)
        if not s2.is_valid():
            return Response({"errors": s2.errors}, status=status.HTTP_400_BAD_REQUEST)
        s2.save()

    if 'business_licence' in request.data:
        business.business_licence = request.data.get('business_licence')
    if 'gst_num' in request.data:
        business.gst_num = request.data.get('gst_num')

    status_value = None
    if 'status' in request.data:
        status_value = request.data.get('status')
    elif 'Status' in request.data:
        status_value = request.data.get('Status')
    if status_value is not None:
        if isinstance(status_value, str):
            business.status = status_value.lower() in ['1', 'true', 'yes', 'on']
        else:
            business.status = bool(status_value)

    business.save()

    return Response({
        "message": "Business details updated successfully",
        "business_id": business.business_id
    }, status=status.HTTP_200_OK)

@swagger_auto_schema(methods=['GET'], tags=['Business'])
@api_view(['GET'])
def user_status(request):
    """
    Unified user status endpoint
    Query: userID
    Returns a directive for frontend navigation across ONBOARDING, BUSINESS_SETUP, PAYMENT, COMPLETE.
    """
    user_id = request.query_params.get('userID')
    if not user_id:
        return Response({"error": "userID is required"}, status=status.HTTP_400_BAD_REQUEST)

    # 1) Try to find existing business via mapping
    try:
        # Prefer mapping to ensure ownership
        mapping = BusinessMapping.objects.filter(user__user_id=user_id).select_related('business').order_by('-id').first()
    except Exception:
        mapping = None

    if mapping and mapping.business:
        business = mapping.business

        # Section completion
        section1_complete = bool(business.businessName and business.businessType)
        section2_complete = bool(business.address and business.city and business.state)
        # Financial exists -> section3 base complete
        financial_exists = BusinessFinancial.objects.filter(business=business).exists()
        section3_complete = bool(financial_exists)

        overall_complete = section1_complete and section2_complete and section3_complete

        # Determine resume step
        resume_step = 1
        if not section1_complete:
            resume_step = 1
        elif not section2_complete:
            resume_step = 2
        elif not section3_complete:
            resume_step = 3

        # Payment status (DB stores as boolean/int)
        payment_status = bool(getattr(business, 'paymentstatus', False))

        if payment_status:
            return Response({
                "stage": "COMPLETE",
                "status": "ACTIVE",
                "redirectTo": None,
                "context": {"business_id": business.business_id}
            })

        if section3_complete and not payment_status:
            return Response({
                "stage": "PAYMENT",
                "status": "PENDING_PAYMENT",
                "redirectTo": "/business/preview-and-pay",
                "context": {"business_id": business.business_id}
            })

        # Business setup incomplete
        return Response({
            "stage": "BUSINESS_SETUP",
            "status": "IN_PROGRESS",
            "redirectTo": f"/business-setup/step-{resume_step}",
            "context": {"business_id": business.business_id, "resumeAtStep": resume_step}
        })

    # 2) No business: check onboarding application state
    try:
        app = (BusinessApplication.objects
               .filter(user__user_id=user_id)
               .order_by('-created_at')
               .first())
    except Exception:
        app = None

    if not app:
        return Response({
            "stage": "ONBOARDING",
            "status": "NOT_STARTED",
            "redirectTo": "/onboarding-flow",
            "context": {"application_id": None, "resumeAtStep": 1}
        })

    # Determine first incomplete step from ApplicationStep
    steps = {s.step_number: s for s in ApplicationStep.objects.filter(application=app)}
    resume_step = 1
    for n in [1, 2, 3]:
        s = steps.get(n)
        if not (s and s.is_completed):
            resume_step = n
            break

    status_map = {
        'in_progress': ('ONBOARDING', 'IN_PROGRESS', '/onboarding-flow'),
        'submitted': ('ONBOARDING', 'PENDING_REVIEW', '/onboarding-status'),
        'pending_review': ('ONBOARDING', 'PENDING_REVIEW', '/onboarding-status'),
        'requires_changes': ('ONBOARDING', 'REQUIRES_CHANGES', '/onboarding-flow'),
        'rejected': ('ONBOARDING', 'REJECTED', '/onboarding-status'),
        'approved': ('BUSINESS_SETUP', 'NOT_STARTED', '/business-setup/step-1'),
    }

    phase, st, redirect = status_map.get(app.status, ('ONBOARDING', app.status.upper(), '/onboarding-flow'))

    payload = {
        "stage": phase,
        "status": st,
        "redirectTo": redirect,
        "context": {
            "application_id": app.application_id,
        }
    }

    if phase == 'ONBOARDING':
        payload["context"]["resumeAtStep"] = resume_step

    return Response(payload)

@swagger_auto_schema(methods=['POST'], tags=['Business'])
@api_view(['POST'])
def parse_address_from_maps(request):
    """
    Parse Google Maps URL and return address components
    """
    maps_url = request.data.get('maps_url')
    if not maps_url:
        return Response(
            {'error': 'maps_url is required'}, 
            status=status.HTTP_400_BAD_REQUEST
        )
    
    try:
        address_data = parse_google_maps_url(maps_url)
        
        if not address_data or 'error' in address_data:
            return Response(
                {'error': address_data.get('error', 'Could not parse the Google Maps URL')}, 
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Ensure required fields are present
        response_data = {
            'address': address_data.get('address', ''),
            'city': address_data.get('city', ''),
            'state': address_data.get('state', ''),
            'pincode': address_data.get('pincode', ''),
            'country': address_data.get('country', 'India'),  # Default to India
            'latitude': address_data.get('latitude'),
            'longitude': address_data.get('longitude'),
            'formatted_address': address_data.get('formatted_address', '')
        }
        
        return Response(response_data)
        
    except Exception as e:
        return Response(
            {'error': f'An error occurred: {str(e)}'}, 
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )

@swagger_auto_schema(
    method='GET',
    tags=['Business'],
    responses={
        200: openapi.Response(
            description='Business features retrieved successfully',
            examples={
                'application/json': [
                    {
                        'id': 1,
                        'feature_id': 'F001',
                        'details': 'Online Ordering',
                        'description': 'Enable online ordering for customers',
                        'status': True
                    }
                ]
            }
        ),
        405: openapi.Response(
            description='Method not allowed',
            examples={
                'application/json': {
                    'error': 'Method not allowed'
                }
            }
        )
    }
)
@api_view(['GET'])
def fetchbusinessesTypes(request):
    if request.method == 'GET':
        business_types = BusinessType.objects.filter(status=True)
        serializer = BusinessTypeSerializer(business_types, many=True, context={'request': request})
        return Response(serializer.data)
    return Response({"error": "Method not allowed"}, status=405)

@swagger_auto_schema(
    methods=['GET'],
    tags=['Business'],
    manual_parameters=[
        openapi.Parameter(
            'business_id',
            openapi.IN_QUERY,
            description='Business ID to fetch specific features (optional)',
            type=openapi.TYPE_STRING,
            required=False
        ),
    ],
    responses={
        200: openapi.Response(
            description='Business features retrieved successfully',
            schema=openapi.Schema(
                type=openapi.TYPE_ARRAY,
                items=openapi.Schema(
                    type=openapi.TYPE_OBJECT,
                    properties={
                        'feature_id': openapi.Schema(type=openapi.TYPE_STRING, description='Feature ID'),
                        'details': openapi.Schema(type=openapi.TYPE_STRING, description='Feature description'),
                    }
                )
            )
        ),
        404: openapi.Response(
            description='Business not found',
            examples={
                'application/json': {
                    'error': 'Business not found'
                }
            }
        ),
        500: openapi.Response(
            description='Internal server error',
            examples={
                'application/json': {
                    'error': 'Error message'
                }
            }
        )
    }
)
@api_view(['GET'])
def fetchbusinessFeatures(request):
    """
    Fetch business features for a specific business.
    If business_id is provided, returns features from business_features column.
    If no business_id, returns all available features (legacy behavior).
    Handles business hierarchy: checks master business if sublevel has no features.
    """
    if request.method == 'GET':
        business_id = request.GET.get('business_id')
        
        if business_id:
            try:
                # Get the business
                business = Business.objects.get(business_id=business_id)
                
                # Get features from business_features column
                business_features = business.business_features or []
                
                # If business has no features and it's a sublevel, check master business
                if not business_features and business.level == 'sublevel' and business.master:
                    try:
                        master_business = Business.objects.get(business_id=business.master)
                        business_features = master_business.business_features or []
                    except Business.DoesNotExist:
                        pass
                
                # If still no features, return empty array
                if not business_features:
                    return Response([])
                
                # Get feature details for each feature_id
                features = []
                for feature_id in business_features:
                    try:
                        feature = BusinessFeature.objects.get(feature_id=feature_id, status=True)
                        features.append({
                            "feature_id": feature.feature_id,
                            "details": feature.details
                        })
                    except BusinessFeature.DoesNotExist:
                        # Skip features that don't exist or are inactive
                        continue
                
                return Response(features)
                
            except Business.DoesNotExist:
                return Response({"error": "Business not found"}, status=404)
            except Exception as e:
                return Response({"error": str(e)}, status=500)
        
        # Legacy behavior: return all features if no business_id provided
        else:
            business_feature = BusinessFeature.objects.filter(status=True)
            serializer = BusinessFeatureSerializer(business_feature, many=True)
            return Response(serializer.data)
    
    return Response({"error": "Method not allowed"}, status=405)

@swagger_auto_schema(
    methods=['POST', 'PUT'],
    tags=['Business'],
    manual_parameters=[
        openapi.Parameter(
            'userID',
            openapi.IN_QUERY,
            description='User ID for business creation/update',
            type=openapi.TYPE_STRING,
            required=True
        ),
    ],
    request_body=openapi.Schema(
        type=openapi.TYPE_OBJECT,
        properties={
            'section1': openapi.Schema(
                type=openapi.TYPE_OBJECT,
                description='Business basic information',
                properties={
                    'businessName': openapi.Schema(type=openapi.TYPE_STRING, description='Business name'),
                    'businessType': openapi.Schema(type=openapi.TYPE_STRING, description='Business type code'),
                    'businessCategory': openapi.Schema(type=openapi.TYPE_STRING, description='Business category'),
                    'businessEmail': openapi.Schema(type=openapi.TYPE_STRING, format='email', description='Business email'),
                    'businessNumber': openapi.Schema(type=openapi.TYPE_STRING, description='Business phone number'),
                    'businessWhatsapp': openapi.Schema(type=openapi.TYPE_STRING, description='Business WhatsApp number'),
                    'description': openapi.Schema(type=openapi.TYPE_STRING, description='Business description'),
                    'logo': openapi.Schema(type=openapi.TYPE_FILE, description='Business logo image'),
                    'banner': openapi.Schema(type=openapi.TYPE_FILE, description='Business banner image'),
                    'business_features': openapi.Schema(type=openapi.TYPE_ARRAY, items=openapi.Schema(type=openapi.TYPE_STRING), description='List of business feature IDs'),
                }
            ),
            'section2': openapi.Schema(
                type=openapi.TYPE_OBJECT,
                description='Business location and contact details',
                properties={
                    'location': openapi.Schema(type=openapi.TYPE_STRING, description='Business location'),
                    'address': openapi.Schema(type=openapi.TYPE_STRING, description='Business address'),
                    'landmark': openapi.Schema(type=openapi.TYPE_STRING, description='Landmark'),
                    'city': openapi.Schema(type=openapi.TYPE_STRING, description='City'),
                    'state': openapi.Schema(type=openapi.TYPE_STRING, description='State'),
                    'pincode': openapi.Schema(type=openapi.TYPE_STRING, description='Pincode'),
                    'contact_support': openapi.Schema(type=openapi.TYPE_STRING, description='Support contact'),
                    'contact_mobile': openapi.Schema(type=openapi.TYPE_STRING, description='Support mobile'),
                    'website_url': openapi.Schema(type=openapi.TYPE_STRING, format='uri', description='Website URL'),
                }
            ),
            'section3': openapi.Schema(
                type=openapi.TYPE_OBJECT,
                description='Business financial details',
                properties={
                    'pan': openapi.Schema(type=openapi.TYPE_STRING, description='PAN number'),
                    'aadhaar': openapi.Schema(type=openapi.TYPE_STRING, description='Aadhaar number'),
                    'per_mobile_number': openapi.Schema(type=openapi.TYPE_STRING, description='Personal mobile number'),
                    'gst_num': openapi.Schema(type=openapi.TYPE_STRING, description='GST number'),
                    'currency': openapi.Schema(type=openapi.TYPE_STRING, description='Currency'),
                }
            ),
        }
    ),
    responses={
        200: openapi.Response(
            description='Business created/updated successfully',
            examples={
                'application/json': {
                    'message': 'Business created successfully',
                    'business_id': 'string',
                    'sections': {
                        'section1': 'Business basic information saved',
                        'section2': 'Business location saved',
                        'section3': 'Business financial details saved'
                    }
                }
            }
        ),
        400: openapi.Response(
            description='Bad request - missing or invalid parameters',
            examples={
                'application/json': {
                    'error': 'userID is required'
                }
            }
        ),
        404: openapi.Response(
            description='User not found',
            examples={
                'application/json': {
                    'error': 'Invalid userID'
                }
            }
        )
    }
)
@swagger_auto_schema(
    method='GET',
    tags=['Business'],
    manual_parameters=[
        openapi.Parameter(
            'userID',
            openapi.IN_QUERY,
            description='User ID to retrieve business information',
            type=openapi.TYPE_STRING,
            required=True
        ),
    ],
    responses={
        200: openapi.Response(
            description='Business information retrieved successfully',
            examples={
                'application/json': {
                    'business_id': 'string',
                    'section1': {
                        'businessName': 'string',
                        'businessType': 'string',
                        'businessCategory': 'string'
                    },
                    'section2': {
                        'address': 'string',
                        'city': 'string',
                        'state': 'string'
                    },
                    'section3': {
                        'pan': 'string',
                        'gst_num': 'string'
                    },
                    'financial_details': {
                        'pan': 'string',
                        'aadhaar': 'string'
                    }
                }
            }
        ),
        400: openapi.Response(
            description='Bad request - missing userID',
            examples={
                'application/json': {
                    'error': 'userID is required'
                }
            }
        ),
        404: openapi.Response(
            description='User not found',
            examples={
                'application/json': {
                    'error': 'Invalid userID'
                }
            }
        )
    }
)
@api_view(['POST', 'GET', 'PUT'])
@parser_classes([MultiPartParser, FormParser, JSONParser])
def CreateBusinessAPIView(request):
    user_id = request.query_params.get("userID")
    
    if not user_id:
        return Response({"error": "userID is required"}, status=status.HTTP_400_BAD_REQUEST)
    
    def compress_image(image_file):
        """Compress image to 75% quality"""
        if not image_file:
            return None
            
        img = Image.open(image_file)
        # Convert RGBA to RGB if necessary
        if img.mode in ('RGBA', 'P'):
            img = img.convert('RGB')
            
        # Create a BytesIO object
        img_io = BytesIO()
        # Save image with 75% quality
        img.save(img_io, format='JPEG', quality=75, optimize=True)
        # Rewind buffer so subsequent reads write full content
        img_io.seek(0)
        # Create a new Django friendly File object
        new_image = File(img_io, name=image_file.name)
        return new_image

    if request.method in ['POST', 'PUT']:
        # Compress images before passing to serializer
        if 'logo' in request.FILES:
            request.FILES['logo'] = compress_image(request.FILES['logo'])
        if 'banner' in request.FILES:
            request.FILES['banner'] = compress_image(request.FILES['banner'])

    # GET: Retrieve draft/existing business for user
    if request.method == 'GET':
        try:
            user = Registration.objects.get(user_id=user_id, status=True)
        except Registration.DoesNotExist:
            return Response({"error": "Invalid userID"}, status=status.HTTP_404_NOT_FOUND)
        
        user_businesses = Business.objects.filter(
            user_mappings__user__user_id=user_id
        ).order_by('-created_at')
        
        if user_businesses.exists():
            business = user_businesses.first()
            
            # Get business financial details if exists
            financial_details = None
            try:
                financial = BusinessFinancial.objects.get(business=business)
                financial_serializer = BusinessFinancialDetailSerializer(financial)
                financial_details = financial_serializer.data
            except BusinessFinancial.DoesNotExist:
                financial_details = None
            
            # Determine completion status
            section1_complete = bool(business.businessName and business.businessType)
            section2_complete = bool(business.address and business.city and business.state)
            section3_complete = bool(financial_details and business.paymentstatus)
            
            business_data = {
                # Basic Business Info (Section 1)
                'business_id': business.business_id,
                'businessName': business.businessName,
                'businessType': business.businessType,
                'businessCategory': business.businessCategory,
                'description': business.description,
                'business_hours': business.business_hours,
                'level': business.level,
                'master': business.master,
                'businessEmail': business.businessEmail,
                'businessNumber': business.businessNumber,
                'businessWhatsapp': business.businessWhatsapp,
                'logo': build_s3_file_url(business.logo),
                'banner': build_s3_file_url(business.banner),
                
                # Location Info (Section 2)
                'location': business.location,
                'address': business.address,
                'landmark': business.landmark,
                'city': business.city,
                'state': business.state,
                'pincode': business.pincode,
                'contact_support': business.contact_support,
                'contact_mobile': business.contact_mobile,
                'website_url': business.website_url,
                'business_features': business.business_features,
                'latitude': business.latitude,
                'longitude': business.longitude,
                
                # Financial Info (Section 3) - Moved to top level
                'owner_pan': financial_details.get('owner_pan') if financial_details else None,
                'gstin': financial_details.get('gstin') if financial_details else None,
                'ifsc_code': financial_details.get('ifsc_code') if financial_details else None,
                'account_number': financial_details.get('account_number') if financial_details else None,
                'razor_pay_key_id': financial_details.get('razor_pay_key_id') if financial_details else None,
                'razor_pay_key_code': financial_details.get('razor_pay_key_code') if financial_details else None,
                'razor_webhook_secret': financial_details.get('razor_webhook_secret') if financial_details else None,
                'fssai_certification_number': financial_details.get('fssai_certification_number') if financial_details else None,
                'payment_status': business.paymentstatus,
                
                # Status Info
                'completion_status': {
                    'section1_complete': section1_complete,
                    'section2_complete': section2_complete,
                    'section3_complete': section3_complete,
                    'overall_complete': section1_complete and section2_complete and section3_complete,
                },
                
                # Metadata
                'created_at': business.created_at,
                'updated_at': business.updated_at
            }
            
            return Response({
                'message': 'Business data retrieved successfully',
                'has_existing_business': True,
                'business_data': business_data
            }, status=status.HTTP_200_OK)
        else:
            return Response({
                'message': 'No existing business found',
                'has_existing_business': False,
                'business_data': None
            }, status=status.HTTP_200_OK)
    
    # PUT: Update existing business (edit functionality)
    elif request.method == 'PUT':
        business_id = request.data.get("business_id")
        section = request.query_params.get("section")
        
        if not business_id or not section:
            return Response({"error": "business_id and section are required for updates"}, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            business = Business.objects.get(business_id=business_id)
            # Verify user owns this business
            if not BusinessMapping.objects.filter(user__user_id=user_id, business=business).exists():
                return Response({"error": "You don't have permission to edit this business"}, status=status.HTTP_403_FORBIDDEN)
        except Business.DoesNotExist:
            return Response({"error": "Business not found"}, status=status.HTTP_404_NOT_FOUND)
        
        # Update based on section
        if section == "1":
            # Handle logo update
            if 'logo' in request.FILES:
                save_model_image_field(business, 'logo', request.FILES['logo'], 'business_logos')

            # Handle banner update
            if 'banner' in request.FILES:
                save_model_image_field(business, 'banner', request.FILES['banner'], 'business_banners')

            # Handle explicit removal of images
            if request.data.get('logo') == 'null':
                if business.logo:
                    business.logo.delete(save=False)
                business.logo = None
                
            if request.data.get('banner') == 'null':
                if business.banner:
                    business.banner.delete(save=False)
                business.banner = None

            # Update other business details
            serializer = Businesssection1serializers(
                business, 
                data=request.data, 
                partial=True, 
                context={
                    "user_id": user_id, 
                    "request": request
                }
            )
            
            if serializer.is_valid():
                updated_business = serializer.save()
                return Response({
                    "message": "Business basic details updated successfully",
                    "business_id": updated_business.business_id,
                    "business_details": serializer.data
                }, status=status.HTTP_200_OK)
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
            
        elif section == "2":
            serializer = Businesssection2Serializer(business, data=request.data, partial=True)
            if serializer.is_valid():
                updated_business = serializer.save()
                return Response({
                    "message": "Business address & location updated successfully",
                    "business_id": updated_business.business_id,
                    "business_details": serializer.data
                }, status=status.HTTP_200_OK)
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        
        elif section == "3":
            # Update financial details
            try:
                financial = BusinessFinancial.objects.get(business=business)
                serializer = Businesssection3Serializer(financial, data=request.data, partial=True)
            except BusinessFinancial.DoesNotExist:
                # Create new financial record if doesn't exist
                request.data['business_id'] = business_id
                serializer = Businesssection3Serializer(data=request.data)
            
            if serializer.is_valid():
                updated_financial = serializer.save()
                return Response({
                    "message": "Business financial details updated successfully",
                    "business_id": business_id,
                    "financial_details": serializer.data
                }, status=status.HTTP_200_OK)
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        
        return Response({"error": "Invalid section"}, status=status.HTTP_400_BAD_REQUEST)
    
    # POST: Create new business (existing functionality)
    elif request.method == 'POST':
        section = request.query_params.get("section")
        
        if not section:
            return Response({"error": "section is required"}, status=status.HTTP_400_BAD_REQUEST)

        # SECTION 1
        if section == "1":
            try:
                user = Registration.objects.get(user_id=user_id, status=True)
            except Registration.DoesNotExist:
                return Response({"error": "Invalid userID"}, status=status.HTTP_400_BAD_REQUEST)
            
            # Check if user already has a business mapping
            try:
                business_mapping = BusinessMapping.objects.get(user=user)
                existing_business = business_mapping.business
                
                # Update existing business
                serializer = Businesssection1serializers(existing_business, data=request.data, partial=True, context={"user_id": user_id, "request": request})
                if serializer.is_valid():
                    business = serializer.save()

                    if 'logo' in request.FILES:
                        save_model_image_field(business, 'logo', request.FILES['logo'], 'business_logos')

                    if 'banner' in request.FILES:
                        save_model_image_field(business, 'banner', request.FILES['banner'], 'business_banners')

                    business.save()

                    response_serializer = Businesssection1serializers(business, context={"user_id": user_id, "request": request})
                    return Response(
                        {"message": "Business updated successfully", "business_id": business.business_id, "business_details": response_serializer.data},
                        status=status.HTTP_200_OK
                    )
                return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
                
            except BusinessMapping.DoesNotExist:
                # No existing business mapping, create new business
                serializer = Businesssection1serializers(data=request.data, context={"user_id": user_id, "request": request})
                if serializer.is_valid():
                    business = serializer.save()

                    # Ensure BusinessMapping is created for new business
                    BusinessMapping.objects.get_or_create(
                        user=user,
                        defaults={'business': business}
                    )

                    # Handle logo upload
                    if 'logo' in request.FILES:
                        save_model_image_field(business, 'logo', request.FILES['logo'], 'business_logos')

                    # Handle banner upload
                    if 'banner' in request.FILES:
                        save_model_image_field(business, 'banner', request.FILES['banner'], 'business_banners')

                    business.save()

                    response_serializer = Businesssection1serializers(business, context={"user_id": user_id, "request": request})
                    return Response(
                        {"message": "Business created successfully", "business_id": business.business_id, "business_details": response_serializer.data},
                        status=status.HTTP_201_CREATED
                    )
                return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        # SECTION 2
        if section == "2":
            business_id = request.data.get("business_id")
            if not business_id:
                return Response({"error": "business_id is required for section 2"}, status=status.HTTP_400_BAD_REQUEST)

            try:
                business = Business.objects.get(business_id=business_id, status=True)
            except Business.DoesNotExist:
                return Response({"error": "Invalid business_id"}, status=status.HTTP_404_NOT_FOUND)

            serializer = Businesssection2Serializer(business, data=request.data, partial=True)
            if serializer.is_valid():
                updated_business = serializer.save()
                return Response(
                    {"message": "Business address & location added successfully", "business_id": updated_business.business_id,
                    "business_details": serializer.data},
                    status=status.HTTP_200_OK
                )
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        
        # SECTION 3
        if section == "3":
            serializer = Businesssection3Serializer(data=request.data)  # request.data is already parsed dict
            if serializer.is_valid():
                financial = serializer.save()
                return Response(
                    {"message": "Business financial details added successfully", "business_id": financial.business_id,
                    "financial_details": serializer.data},
                    status=status.HTTP_201_CREATED
                )
            else:
                return Response(serializer.errors)

        return Response({"error": "Invalid section"}, status=status.HTTP_400_BAD_REQUEST)

@swagger_auto_schema(method='GET', tags=['Business'])
@api_view(['GET'])
def business_summary(request):
    user_id = request.query_params.get('userID')
    business_id = request.query_params.get('business_id') or request.query_params.get('businessId')

    if not user_id:
        return Response({"error": "userID is required"}, status=status.HTTP_400_BAD_REQUEST)

    try:
        Registration.objects.get(user_id=user_id, status=True)
    except Registration.DoesNotExist:
        return Response({"error": "Invalid userID"}, status=status.HTTP_404_NOT_FOUND)

    def serialize_business(business):
        try:
            financial = BusinessFinancial.objects.get(business=business)
            financial_details = BusinessFinancialDetailSerializer(financial).data
        except BusinessFinancial.DoesNotExist:
            financial_details = None

        section1_complete = bool(business.businessName and business.businessType)
        section2_complete = bool(business.address and business.city and business.state)
        section3_complete = bool(financial_details)

        return {
            'business_id': business.business_id,
            'businessName': business.businessName,
            'businessType': business.businessType,
            'businessCategory': business.businessCategory,
            'description': business.description,
            'business_hours': business.business_hours,
            'level': business.level,
            'master': business.master,
            'businessEmail': business.businessEmail,
            'businessNumber': business.businessNumber,
            'businessWhatsapp': business.businessWhatsapp,
            'logo': build_s3_file_url(business.logo),
            'banner': build_s3_file_url(business.banner),
            'location': business.location,
            'address': business.address,
            'landmark': business.landmark,
            'city': business.city,
            'state': business.state,
            'pincode': business.pincode,
            'contact_support': business.contact_support,
            'contact_mobile': business.contact_mobile,
            'website_url': business.website_url,
            'business_features': business.business_features,
            'latitude': business.latitude,
            'longitude': business.longitude,
            'owner_pan': financial_details.get('owner_pan') if financial_details else None,
            'gstin': financial_details.get('gstin') if financial_details else None,
            'ifsc_code': financial_details.get('ifsc_code') if financial_details else None,
            'account_number': financial_details.get('account_number') if financial_details else None,
            'razor_pay_key_id': financial_details.get('razor_pay_key_id') if financial_details else None,
            'razor_pay_key_code': financial_details.get('razor_pay_key_code') if financial_details else None,
            'razor_webhook_secret': financial_details.get('razor_webhook_secret') if financial_details else None,
            'fssai_certification_number': financial_details.get('fssai_certification_number') if financial_details else None,
            'payment_status': business.paymentstatus,
            'status': business.status,
            'completion_status': {
                'section1_complete': section1_complete,
                'section2_complete': section2_complete,
                'section3_complete': section3_complete,
                'overall_complete': section1_complete and section2_complete and section3_complete,
            },
            'created_at': business.created_at,
            'updated_at': business.updated_at
        }

    if business_id:
        try:
            business = Business.objects.get(business_id=business_id)
        except Business.DoesNotExist:
            return Response({"error": "Invalid business_id"}, status=status.HTTP_404_NOT_FOUND)

        # Check if user has BusinessMapping to this business
        has_mapping = BusinessMapping.objects.filter(user__user_id=user_id, business=business).exists()
        
        # Check if user is POS/KOT user for this business or its master
        is_pos_user = False
        with connection.cursor() as cursor:
            # Check if user is POS for the specific business_id
            cursor.execute(
                """
                SELECT role FROM business_role_management
                WHERE assigned_to = %s AND business_id = %s AND status = 1
                """,
                [user_id, business_id]
            )
            row = cursor.fetchone()
            if row and row[0] and row[0].upper() in ['POS', 'KOT', 'COUNTER']:
                is_pos_user = True
            else:
                # Check if user is POS for a master business that has this business as a child
                cursor.execute(
                    """
                    SELECT brm.role, brm.business_id 
                    FROM business_role_management brm
                    INNER JOIN businesses b ON b.business_id = brm.business_id
                    WHERE brm.assigned_to = %s 
                      AND brm.status = 1 
                      AND b.level = 'master'
                      AND b.status = 1
                      AND EXISTS (
                          SELECT 1 FROM businesses child 
                          WHERE child.master = brm.business_id 
                          AND child.business_id = %s 
                          AND child.status = 1
                      )
                    """,
                    [user_id, business_id]
                )
                master_row = cursor.fetchone()
                if master_row and master_row[0] and master_row[0].upper() in ['POS', 'KOT', 'COUNTER']:
                    is_pos_user = True
        
        # Allow access if user has BusinessMapping OR is POS user
        if not has_mapping and not is_pos_user:
            return Response({"error": "You don't have access to this business"}, status=status.HTTP_403_FORBIDDEN)

        return Response({
            'message': 'Business summary retrieved successfully',
            'business_data': serialize_business(business)
        }, status=status.HTTP_200_OK)

    businesses = Business.objects.filter(user_mappings__user__user_id=user_id).order_by('-created_at')
    if not businesses.exists():
        return Response({
            'message': 'No business found',
            'business_data': None,
            'businesses': []
        }, status=status.HTTP_200_OK)

    latest = businesses.first()
    return Response({
        'message': 'Business summary retrieved successfully',
        'business_data': serialize_business(latest),
        'businesses': [serialize_business(b) for b in businesses]
    }, status=status.HTTP_200_OK)

@swagger_auto_schema(method='GET', tags=['Business'])
@api_view(['GET'])
def business_hierarchy(request):
    user_id = request.query_params.get('user_id') or request.query_params.get('userID')
    if not user_id:
        return Response({"error": "user_id is required"}, status=status.HTTP_400_BAD_REQUEST)

    try:
        Registration.objects.get(user_id=user_id, status=True)
    except Registration.DoesNotExist:
        return Response({"error": "Invalid user_id"}, status=status.HTTP_404_NOT_FOUND)

    mapping = (BusinessMapping.objects
               .filter(user__user_id=user_id, status=True)
               .select_related('business')
               .order_by('-id')
               .first())
    if not mapping or not mapping.business:
        return Response({"error": "No business mapped for this user"}, status=status.HTTP_404_NOT_FOUND)

    biz = mapping.business
    master_business = biz
    if getattr(biz, 'master', None):
        try:
            master_business = Business.objects.get(business_id=biz.master)
        except Business.DoesNotExist:
            master_business = biz

    sub_qs = Business.objects.filter(master=master_business.business_id).order_by('created_at')

    def serialize(b):
        return {
            'business_id': b.business_id,
            'businessName': b.businessName,
            'level': b.level,
            'master': b.master,
            'businessType': b.businessType,
            'businessCategory': b.businessCategory,
            'address': b.address,
            'city': b.city,
            'state': b.state,
            'pincode': b.pincode,
            'latitude': b.latitude,
            'longitude': b.longitude,
            'logo': build_s3_file_url(b.logo),
            'banner': build_s3_file_url(b.banner),
            'status': b.status,
            'created_at': b.created_at,
            'updated_at': b.updated_at,
        }

    return Response({
        'master_business': serialize(master_business),
        'sub_businesses': [serialize(s) for s in sub_qs],
        'total_sub_businesses': sub_qs.count()
    }, status=status.HTTP_200_OK)

@swagger_auto_schema(methods=['PATCH'], tags=['Business'])
@api_view(['PATCH'])
def toggle_business_status(request, business_id):
    user_id = request.query_params.get('user_id') or request.query_params.get('userID')
    if not user_id:
        return Response({"error": "user_id is required"}, status=status.HTTP_400_BAD_REQUEST)

    try:
        Registration.objects.get(user_id=user_id, status=True)
    except Registration.DoesNotExist:
        return Response({"error": "Invalid user_id"}, status=status.HTTP_404_NOT_FOUND)

    mapping = (BusinessMapping.objects
               .filter(user__user_id=user_id, status=True)
               .select_related('business')
               .order_by('-id')
               .first())
    if not mapping or not mapping.business:
        return Response({"error": "No business mapped for this user"}, status=status.HTTP_404_NOT_FOUND)

    try:
        target = Business.objects.get(business_id=business_id)
    except Business.DoesNotExist:
        return Response({"error": "Business not found"}, status=status.HTTP_404_NOT_FOUND)

    owner_master = mapping.business
    if getattr(owner_master, 'master', None):
        try:
            owner_master = Business.objects.get(business_id=owner_master.master)
        except Business.DoesNotExist:
            pass

    if not (target.business_id == owner_master.business_id or target.master == owner_master.business_id):
        return Response({"error": "You don't have permission to modify this business"}, status=status.HTTP_403_FORBIDDEN)

    desired = request.data.get('status', None)
    if desired is None:
        new_status = not bool(target.status)
    else:
        if isinstance(desired, str):
            new_status = desired.lower() in ['1', 'true', 'yes', 'on']
        else:
            new_status = bool(desired)

    is_master = (target.master in [None, '', 'null']) or (str(getattr(target, 'level', '')).lower() == 'master')

    affected_subs = 0
    with transaction.atomic():
        if is_master:
            Business.objects.filter(
                Q(business_id=target.business_id) | Q(master=target.business_id)
            ).update(status=new_status)
            affected_subs = Business.objects.filter(master=target.business_id).count()
        else:
            target.status = new_status
            target.save(update_fields=['status'])

    return Response({
        "message": "Status updated successfully",
        "business_id": target.business_id,
        "is_master": is_master,
        "status": new_status,
        "affected_sub_businesses": affected_subs
    }, status=status.HTTP_200_OK)


@swagger_auto_schema(
    method='POST',
    tags=['Business'],
    manual_parameters=[
        openapi.Parameter(
            'userID',
            openapi.IN_QUERY,
            description='User ID creating the menu item',
            type=openapi.TYPE_STRING,
            required=True
        ),
        openapi.Parameter(
            'business_id',
            openapi.IN_QUERY,
            description='Business ID for the menu item',
            type=openapi.TYPE_STRING,
            required=True
        ),
    ],
    request_body=openapi.Schema(
        type=openapi.TYPE_OBJECT,
        properties={
            'item_name': openapi.Schema(type=openapi.TYPE_STRING, description='Menu item name'),
            'category': openapi.Schema(type=openapi.TYPE_STRING, description='Menu item category'),
            'subcategory': openapi.Schema(type=openapi.TYPE_STRING, description='Menu item subcategory'),
            'description': openapi.Schema(type=openapi.TYPE_STRING, description='Menu item description'),
            'is_variable': openapi.Schema(type=openapi.TYPE_BOOLEAN, default=False, description='Item has multiple variants'),
            'variants': openapi.Schema(
                type=openapi.TYPE_ARRAY,
                items=openapi.Schema(
                    type=openapi.TYPE_OBJECT,
                    properties={
                        'size_label': openapi.Schema(type=openapi.TYPE_STRING, description='Size label (Regular, Medium, Large)'),
                        'selling_price': openapi.Schema(type=openapi.TYPE_NUMBER, format='decimal', description='Variant selling price'),
                        'mrp': openapi.Schema(type=openapi.TYPE_NUMBER, format='decimal', description='Variant MRP'),
                        'stock_qty': openapi.Schema(type=openapi.TYPE_INTEGER, description='Stock quantity'),
                        'original_cost': openapi.Schema(type=openapi.TYPE_NUMBER, format='decimal', description='Original cost'),
                    }
                ),
                description='Array of variants (required if is_variable=True)'
            ),
            'selling_price': openapi.Schema(type=openapi.TYPE_NUMBER, format='decimal', description='Menu item selling price'),
            'original_cost': openapi.Schema(type=openapi.TYPE_NUMBER, format='decimal', description='Menu item original cost'),
            'image': openapi.Schema(type=openapi.TYPE_FILE, description='Menu item image'),
            'is_available': openapi.Schema(type=openapi.TYPE_BOOLEAN, description='Item availability status'),
            'preparation_time': openapi.Schema(type=openapi.TYPE_INTEGER, description='Preparation time in minutes'),
            'ingredients': openapi.Schema(type=openapi.TYPE_ARRAY, items=openapi.Schema(type=openapi.TYPE_STRING), description='List of ingredients'),
            'allergens': openapi.Schema(type=openapi.TYPE_ARRAY, items=openapi.Schema(type=openapi.TYPE_STRING), description='List of allergens'),
            'customization_options': openapi.Schema(type=openapi.TYPE_ARRAY, items=openapi.Schema(type=openapi.TYPE_OBJECT), description='Customization options'),
        },
        required=['item_name', 'category']
    ),
    responses={
        201: openapi.Response(
            description='Menu item created successfully',
            examples={
                'application/json': {
                    'message': 'Menu item created successfully',
                    'item_id': 'string',
                    'item_name': 'string',
                    'price': 'decimal'
                }
            }
        ),
        400: openapi.Response(
            description='Bad request - missing or invalid parameters',
            examples={
                'application/json': {
                    'error': 'userID and business_id are required'
                }
            }
        ),
        404: openapi.Response(
            description='User or business not found',
            examples={
                'application/json': {
                    'error': 'Invalid userID'
                }
            }
        )
    }
)
@api_view(['POST'])
def CreateMenuItemsAPIView(request):
    def _generate_variant_sku(menu_item, size_label):
        """Generate SKU for variant: MENUITEMID-SIZE-BUSSID"""
        import re
        clean_size = re.sub(r'[^a-zA-Z0-9]', '', size_label).upper()
        return f"{menu_item.item_id}-{clean_size}-{menu_item.business_id.business_id}"

    if request.method == 'POST':
        user_id = request.query_params.get("userID")
        business_id = request.query_params.get("business_id")

        if not user_id or not business_id:
            return Response({"error": "userID and business_id are required"}, status=status.HTTP_400_BAD_REQUEST)
        
        # Validate user exists and is active
        try:
            user = Registration.objects.get(user_id=user_id, status=True)
        except Registration.DoesNotExist:
            return Response({"error": "Invalid userID"}, status=status.HTTP_404_NOT_FOUND)
        
        # Validate business exists and is active
        try:
            business = Business.objects.get(business_id=business_id, status=True)
        except Business.DoesNotExist:
            return Response({"error": "Invalid business_id"}, status=status.HTTP_404_NOT_FOUND)

        # Check if user is a POS/KOT counter user via business_role_management
        # First check for direct POS role for the business_id
        # Then check if user is POS for a master business that owns this business_id
        is_pos_user = False
        pos_master_business_id = None
        with connection.cursor() as cursor:
            # First check if user is POS for the specific business_id
            cursor.execute(
                """
                SELECT role, business_id FROM business_role_management
                WHERE assigned_to = %s 
                  AND business_id COLLATE utf8mb4_0900_ai_ci = CAST(%s AS CHAR) COLLATE utf8mb4_0900_ai_ci 
                  AND status = 1
                """,
                [user_id, business_id]
            )
            row = cursor.fetchone()
            if row and row[0] and row[0].upper() in ['POS', 'KOT', 'COUNTER']:
                is_pos_user = True
            else:
                # Check if user is POS for a master business that has this business as a child
                cursor.execute(
                    """
                    SELECT brm.role, brm.business_id 
                    FROM business_role_management brm
                    INNER JOIN businesses b ON b.business_id COLLATE utf8mb4_0900_ai_ci = brm.business_id COLLATE utf8mb4_0900_ai_ci
                    WHERE brm.assigned_to = %s 
                      AND brm.status = 1 
                      AND b.level = 'master'
                      AND b.status = 1
                      AND EXISTS (
                          SELECT 1 FROM businesses child 
                          WHERE child.master COLLATE utf8mb4_0900_ai_ci = brm.business_id COLLATE utf8mb4_0900_ai_ci 
                          AND child.business_id COLLATE utf8mb4_0900_ai_ci = %s 
                          AND child.status = 1
                      )
                    """,
                    [user_id, business_id]
                )
                master_row = cursor.fetchone()
                if master_row and master_row[0] and master_row[0].upper() in ['POS', 'KOT', 'COUNTER']:
                    is_pos_user = True
                    pos_master_business_id = master_row[1]

        try:
            user_mapping = BusinessMapping.objects.select_related('business').get(user__user_id=user_id, status=True)
        except BusinessMapping.DoesNotExist:
            # If POS user, allow access
            if is_pos_user:
                user_mapping = None  # Set to None to bypass mapping checks
            else:
                return Response({"error": "User does not have access to any business"}, status=status.HTTP_403_FORBIDDEN)

        level_val = (business.level or '').strip().lower()
        if 'master' in level_val:
            child_ids = list(Business.objects.filter(master=business.business_id, status=True).values_list('business_id', flat=True))
            allowed_business_ids = set([business.business_id] + child_ids)
        else:
            allowed_business_ids = {business.business_id}
            if business.master:
                allowed_business_ids.add(business.master)

        # Skip mapping check if POS user
        if not is_pos_user:
            if user_mapping.business.business_id not in allowed_business_ids:
                return Response({"error": "User does not have access to this business"}, status=status.HTTP_403_FORBIDDEN)

        # Determine target business for creating the menu item
        # For POS users with master access, we still create the item in the selected business (child)
        # For regular users, use the business mapping logic
        target_business = business
        if is_pos_user:
            # POS users can create items in the business_id they specify (which could be a child)
            # The item will be created in the child business, not the master
            target_business = business
        elif not is_pos_user and 'master' in level_val:
            if user_mapping and user_mapping.business.business_id != business.business_id and user_mapping.business.business_id in allowed_business_ids:
                target_business = user_mapping.business

        from django.db import transaction

        # Create menu item with variants
        data = request.data
        
        # Parse variants if it's a string (from form data)
        variants_data = data.get('variants', [])
        if isinstance(variants_data, str):
            try:
                import json
                variants_data = json.loads(variants_data)
            except json.JSONDecodeError:
                return Response({"error": "Invalid JSON format for variants"}, status=status.HTTP_400_BAD_REQUEST)

        try:
            with transaction.atomic():
                # 1. Save Parent Item
                serializer = MenuItemsSerializer(data=data, context={"request": request})
                if serializer.is_valid():
                    # Set the business_id for the menu item
                    serializer.validated_data['business_id'] = target_business
                    
                    # Handle is_variable flag
                    is_variable = data.get('is_variable', False)
                    # Convert string boolean to actual boolean
                    if isinstance(is_variable, str):
                        is_variable = is_variable.lower() in ('true', '1', 'yes')
                    serializer.validated_data['is_variable'] = is_variable
                    
                    # Set base price (lowest variant price or single price)
                    if is_variable and variants_data:
                        prices = [Decimal(str(var.get('selling_price', 0))) for var in variants_data]
                        serializer.validated_data['selling_price'] = min(prices)
                        # Set base original_cost to lowest variant cost
                        costs = [Decimal(str(var.get('original_cost', 0))) for var in variants_data if var.get('original_cost')]
                        if costs:
                            serializer.validated_data['original_cost'] = min(costs)
                    else:
                        # For non-variable items, use the provided price as base price
                        serializer.validated_data['selling_price'] = data.get('selling_price')
                        serializer.validated_data['original_cost'] = data.get('original_cost')
                    
                    menu_item = serializer.save()

                    # 2. Handle Variants
                    if is_variable and variants_data:
                        # Create multiple variants
                        for var in variants_data:
                            MenuItemVariant.objects.create(
                                item=menu_item,
                                size_label=var.get('size_label'),
                                selling_price=Decimal(str(var.get('selling_price', 0))),
                                mrp=Decimal(str(var.get('mrp', var.get('selling_price', 0)))),
                                original_cost=Decimal(str(var.get('original_cost', 0))) if var.get('original_cost') else None,
                                stock_qty=var.get('stock_qty', 0),
                                charges=Decimal(str(var.get('charges', 0))),
                                gst=Decimal(str(var.get('gst', 0))),
                                sku=var.get('sku') or _generate_variant_sku(menu_item, var.get('size_label')),
                                is_active=True
                            )
                    else:
                        # Create a single variant for non-variable items using the first variant data or main item data
                        if variants_data and len(variants_data) > 0:
                            # Use the first variant from variants array
                            var = variants_data[0]
                            MenuItemVariant.objects.create(
                                item=menu_item,
                                size_label=var.get('size_label', data.get('size_label', 'Regular')),
                                selling_price=Decimal(str(var.get('selling_price', data.get('selling_price', 0)))),
                                mrp=Decimal(str(var.get('mrp', var.get('selling_price', data.get('selling_price', 0))))),
                                original_cost=Decimal(str(var.get('original_cost', data.get('original_cost', 0)))) if var.get('original_cost') or data.get('original_cost') else None,
                                stock_qty=var.get('stock_qty', data.get('quantity', 0)),
                                charges=Decimal(str(var.get('charges', data.get('charges', 0)))),
                                gst=Decimal(str(var.get('gst', data.get('gst', 0)))),
                                sku=var.get('sku') or data.get('sku') or _generate_variant_sku(menu_item, var.get('size_label', data.get('size_label', 'Regular'))),
                                is_active=True
                            )
                        else:
                            # Fallback: Create variant using main item data
                            MenuItemVariant.objects.create(
                                item=menu_item,
                                size_label=data.get('size_label', 'Regular'),
                                selling_price=Decimal(str(data.get('selling_price', 0))),
                                mrp=Decimal(str(data.get('mrp', data.get('selling_price', 0)))),
                                original_cost=Decimal(str(data.get('original_cost', 0))) if data.get('original_cost') else None,
                                stock_qty=data.get('quantity', 0),
                                charges=Decimal(str(data.get('charges', 0))),
                                gst=Decimal(str(data.get('gst', 0))),
                                sku=data.get('sku') or _generate_variant_sku(menu_item, data.get('size_label', 'Regular')),
                                is_active=True
                            )

                    return Response({
                        "message": "Menu item and variants created successfully",
                        "item_id": menu_item.item_id,
                        "business_id": target_business.business_id,
                        "is_variable": is_variable,
                        "variants_count": len(variants_data) if is_variable else 1,
                        "base_price": float(menu_item.selling_price),
                        "menu_item_details": MenuItemsWithVariantsSerializer(menu_item, context={"request": request}).data
                    }, status=status.HTTP_201_CREATED)
                
                return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

@swagger_auto_schema(methods=['GET', 'POST', 'PATCH', 'DELETE'], tags=['Business'])
@api_view(['GET', 'POST', 'PATCH', 'DELETE'])
def MenuItemVariantManagementAPIView(request, variant_id=None):
    """
    Manage menu item variants (GET, POST, PATCH, DELETE)
    
    GET /kirazee/business/menu-item-variants/<variant_id>/?userID=14815&business_id=KIR147712009930351
    POST /kirazee/business/menu-item-variants/?userID=14815&business_id=KIR147712009930351
    PATCH /kirazee/business/menu-item-variants/<variant_id>/?userID=14815&business_id=KIR147712009930351
    DELETE /kirazee/business/menu-item-variants/<variant_id>/?userID=14815&business_id=KIR147712009930351
    """
    try:
        # Get parameters
        user_id = request.query_params.get('userID')
        business_id = request.query_params.get('business_id')
        
        if not user_id or not business_id:
            return Response(
                {'error': 'userID and business_id are required'}, 
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Validate business exists
        try:
            business = Business.objects.get(business_id=business_id)
        except Business.DoesNotExist:
            return Response(
                {'error': 'Business not found'}, 
                status=status.HTTP_404_NOT_FOUND
            )
        
        if request.method == 'GET':
            if variant_id:
                # Get specific variant
                try:
                    variant = MenuItemVariant.objects.get(variant_id=variant_id)
                    
                    # Remove business ownership validation - allow access to any variant by ID
                    
                    serializer = MenuItemVariantSerializer(variant)
                    return Response({
                        "message": "Menu item variant retrieved successfully",
                        "variant": serializer.data
                    }, status=status.HTTP_200_OK)
                    
                except MenuItemVariant.DoesNotExist:
                    return Response(
                        {"error": "Variant not found"}, 
                        status=status.HTTP_404_NOT_FOUND
                    )
            else:
                # List all variants for a business (if needed)
                return Response(
                    {"error": "Please provide variant_id for GET requests"}, 
                    status=status.HTTP_400_BAD_REQUEST
                )

        elif request.method == 'POST':
            # Create new variant
            menu_item_id = request.data.get('menu_item_id')
            if not menu_item_id:
                return Response({"error": "menu_item_id is required for POST request"}, status=status.HTTP_400_BAD_REQUEST)
            
            try:
                menu_item = MenuItems.objects.get(item_id=menu_item_id, business_id=business)
            except MenuItems.DoesNotExist:
                return Response({"error": "Menu item not found or doesn't belong to this business"}, status=status.HTTP_404_NOT_FOUND)

            # Validate required fields
            required_fields = ['size_label', 'selling_price']
            for field in required_fields:
                if field not in request.data:
                    return Response({"error": f"{field} is required"}, status=status.HTTP_400_BAD_REQUEST)

            # Create new variant
            variant_data = {
                'item': menu_item,
                'size_label': request.data.get('size_label'),
                'selling_price': Decimal(str(request.data.get('selling_price'))),
                'mrp': Decimal(str(request.data.get('mrp'))) if request.data.get('mrp') else None,
                'original_cost': Decimal(str(request.data.get('original_cost'))) if request.data.get('original_cost') else None,
                'stock_qty': request.data.get('stock_qty', 0),
                'charges': Decimal(str(request.data.get('charges'))) if request.data.get('charges') else None,
                'gst': Decimal(str(request.data.get('gst'))) if request.data.get('gst') else None,
                'is_active': request.data.get('is_active', True)
            }

            variant = MenuItemVariant.objects.create(**variant_data)

            return Response({
                "success": True,
                "message": "Menu item variant created successfully",
                "variant": {
                    "variant_id": variant.variant_id,
                    "menu_item_id": variant.item.item_id,
                    "size_label": variant.size_label,
                    "selling_price": str(variant.selling_price) if variant.selling_price else None,
                    "mrp": str(variant.mrp) if variant.mrp else None,
                    "original_cost": str(variant.original_cost) if variant.original_cost else None,
                    "stock_qty": variant.stock_qty,
                    "charges": str(variant.charges) if variant.charges else None,
                    "gst": str(variant.gst) if variant.gst else None,
                    "is_active": variant.is_active,
                    "created_at": variant.created_at.isoformat() if variant.created_at else None,
                }
            }, status=status.HTTP_201_CREATED)

        elif request.method == 'PATCH':
            # Update variant
            if not variant_id:
                return Response({"error": "variant_id is required for PATCH request"}, status=status.HTTP_400_BAD_REQUEST)
            
            try:
                variant = MenuItemVariant.objects.select_related('item').get(variant_id=variant_id)
            except MenuItemVariant.DoesNotExist:
                return Response({"error": "Variant not found"}, status=status.HTTP_404_NOT_FOUND)

            # Remove business ownership validation - allow access to any variant by ID

            # Update variant or toggle is_active status
            data = request.data
            
            # Handle is_active toggle
            if 'is_active' in data:
                is_active = data.get('is_active')
                if isinstance(is_active, str):
                    is_active = is_active.lower() in ('true', '1', 'yes')
                variant.is_active = is_active
            
            # Update other fields if provided
            if 'size_label' in data:
                variant.size_label = data['size_label']
            
            if 'selling_price' in data:
                variant.selling_price = Decimal(str(data['selling_price']))
            
            if 'mrp' in data:
                variant.mrp = Decimal(str(data['mrp']))
            
            if 'original_cost' in data:
                variant.original_cost = Decimal(str(data['original_cost'])) if data['original_cost'] else None
            
            if 'stock_qty' in data:
                variant.stock_qty = data['stock_qty']
            
            if 'charges' in data:
                variant.charges = Decimal(str(data['charges']))
            
            if 'gst' in data:
                variant.gst = Decimal(str(data['gst']))
            
            variant.save()
            
            return Response({
                "success": True,
                "message": "Variant updated successfully",
                "variant": {
                    "variant_id": variant.variant_id,
                    "menu_item_id": variant.item.item_id,
                    "size_label": variant.size_label,
                    "selling_price": str(variant.selling_price) if variant.selling_price else None,
                    "mrp": str(variant.mrp) if variant.mrp else None,
                    "original_cost": str(variant.original_cost) if variant.original_cost else None,
                    "stock_qty": variant.stock_qty,
                    "charges": str(variant.charges) if variant.charges else None,
                    "gst": str(variant.gst) if variant.gst else None,
                    "is_active": variant.is_active,
                    "updated_at": variant.updated_at.isoformat() if variant.updated_at else None,
                }
            }, status=status.HTTP_200_OK)

        elif request.method == 'DELETE':
            # Soft delete variant
            if not variant_id:
                return Response({"error": "variant_id is required for DELETE request"}, status=status.HTTP_400_BAD_REQUEST)
            
            try:
                variant = MenuItemVariant.objects.select_related('item').get(variant_id=variant_id)
            except MenuItemVariant.DoesNotExist:
                return Response({"error": "Variant not found"}, status=status.HTTP_404_NOT_FOUND)

            # Remove business ownership validation - allow access to any variant by ID

            # Soft delete variant (set is_active=False)
            variant.is_active = False
            variant.save()
            
            return Response({
                "success": True,
                "message": "Variant deactivated successfully",
                "variant_id": variant.variant_id,
                "is_active": False
            }, status=status.HTTP_200_OK)

    except Registration.DoesNotExist:
        return Response({"error": "Invalid userID"}, status=status.HTTP_404_NOT_FOUND)
    except Business.DoesNotExist:
        return Response({"error": "Invalid business_id"}, status=status.HTTP_404_NOT_FOUND)
    except Exception as e:
        return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

@swagger_auto_schema(methods=['POST'], tags=['Business'])
@api_view(['POST'])
@parser_classes([MultiPartParser, FormParser])
def bulk_upload_menu_items(request):
    """Bulk upload MenuItems for a business from a CSV file.

    Query params:
      - userID or user_id (required)
      - business_id (required)
      - dry_run (optional: true/false) -> validate only, do not create

    Body (multipart/form-data):
      - file: CSV file with header row. Required columns:
          item_name, selling_price
        Optional columns:
          sku, description, item_category, item_type, preparation_time,
          quantity, original_cost, gst, availability_timings,
          is_active, status
    """

    user_id = request.query_params.get('userID') or request.query_params.get('user_id')
    business_id = request.query_params.get('business_id')
    dry_run_param = request.query_params.get('dry_run') or request.data.get('dry_run')

    def _to_bool(val, default=False):
        if val is None:
            return default
        if isinstance(val, bool):
            return val
        s = str(val).strip().lower()
        if s in ('1', 'true', 'yes', 'y'):
            return True
        if s in ('0', 'false', 'no', 'n'):
            return False
        return default
    
    def _to_int(val, default=None):
        if val is None or str(val).strip() == '':
            return default
        try:
            return int(float(val))
        except (ValueError, TypeError):
            return default

    dry_run = _to_bool(dry_run_param, default=False)

    if not user_id or not business_id:
        return Response({"error": "userID/user_id and business_id are required"}, status=status.HTTP_400_BAD_REQUEST)

    # Validate user exists and is active
    try:
        user = Registration.objects.get(user_id=user_id, status=True)
    except Registration.DoesNotExist:
        return Response({"error": "Invalid user_id"}, status=status.HTTP_404_NOT_FOUND)

    # Validate business exists and is active
    try:
        business = Business.objects.get(business_id=business_id, status=True)
    except Business.DoesNotExist:
        return Response({"error": "Invalid business_id"}, status=status.HTTP_404_NOT_FOUND)

    # Check if user is a POS/KOT/counter user for this business
    is_pos_user = False
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT role FROM business_role_management
            WHERE assigned_to = %s AND business_id = %s AND status = 1
            """,
            [user_id, business_id]
        )
        row = cursor.fetchone()
        if row and row[0] and row[0].upper() in ['POS', 'KOT', 'COUNTER']:
            is_pos_user = True

    # For non-POS users, enforce BusinessMapping
    if not is_pos_user:
        if not BusinessMapping.objects.filter(user__user_id=user_id, business=business, status=True).exists():
            return Response({"error": "User does not have access to this business"}, status=status.HTTP_403_FORBIDDEN)

    upload = request.FILES.get('file') or request.FILES.get('csv') or request.FILES.get('data')
    if not upload:
        return Response({"error": "CSV file is required (field name 'file')"}, status=status.HTTP_400_BAD_REQUEST)

    # Read CSV with tolerant encoding handling
    try:
        raw = upload.read()
        if isinstance(raw, bytes):
            enc_candidates = ['utf-8-sig', 'utf-8', 'cp1252', 'latin1']
            text = None
            last_exc = None
            for enc in enc_candidates:
                try:
                    text = raw.decode(enc)
                    break
                except UnicodeDecodeError as ue:
                    last_exc = ue
            if text is None:
                return Response({
                    "error": "Failed to read CSV: could not decode file with supported encodings.",
                    "details": str(last_exc) if last_exc else "Unknown decode error",
                    "suggestion": "Save the CSV as UTF-8 (with BOM) or try exporting again from Excel."
                }, status=status.HTTP_400_BAD_REQUEST)
        else:
            text = str(raw)
        reader = csv.DictReader(io.StringIO(text))
    except Exception as e:
        return Response({"error": f"Failed to read CSV: {str(e)}"}, status=status.HTTP_400_BAD_REQUEST)

    if not reader.fieldnames:
        return Response({"error": "CSV file must have a header row"}, status=status.HTTP_400_BAD_REQUEST)

    # Map headers case-insensitively
    field_map = {k.lower().strip(): k for k in reader.fieldnames}

    # Support common header synonyms
    synonyms = {
        'item_name': ['name', 'item', 'item name'],
        'selling_price': ['selling price', 'price'],
        'original_cost': ['original cost', 'mrp', 'cost_price'],
        'item_category': ['category', 'item category'],
        'item_type': ['type', 'item type'],
        'preparation_time': ['prep_time', 'preparation time'],
        'availability_timings': ['availability', 'availability timings'],
        'is_active': ['is active', 'active'],
        'size_label': ['size_label', 'size label', 'size', 'variant_size', 'variant size'],
        'category_id': ['category_id', 'item_category_id', 'category id'],
        'sub_category_id': ['sub_category_id', 'sub category id', 'sub_Category_id'],
    }
    for canonical, alts in synonyms.items():
        if canonical not in field_map:
            for alt in alts:
                key = alt.lower().strip()
                if key in field_map:
                    field_map[canonical] = field_map[key]
                    break

    required_fields = ['item_name', 'selling_price']
    missing = [rf for rf in required_fields if rf not in field_map]
    if missing:
        return Response({
            "error": "Missing required columns in CSV",
            "missing_columns": missing
        }, status=status.HTTP_400_BAD_REQUEST)

    def _get(row, col):
        key = field_map.get(col)
        return row.get(key) if key else None

    def _to_decimal(val, default=None):
        try:
            if val is None or str(val).strip() == '':
                return default
            return Decimal(str(val).strip())
        except Exception:
            return default

    def _to_int(val, default=None):
        try:
            if val is None or str(val).strip() == '':
                return default
            return int(float(str(val).strip()))
        except Exception:
            return default

    results = {
        'rows_processed': 0,
        'created': 0,
        'errors': []
    }

    for idx, row in enumerate(reader, start=2):  # 1-based + header
        results['rows_processed'] += 1

        item_name = (_get(row, 'item_name') or '').strip()
        selling_price_raw = _get(row, 'selling_price')

        if not item_name:
            results['errors'].append({'row': idx, 'error': 'item_name is required'})
            continue
        if selling_price_raw is None or str(selling_price_raw).strip() == '':
            results['errors'].append({'row': idx, 'error': 'selling_price is required'})
            continue

        selling_price = _to_decimal(selling_price_raw)
        if selling_price is None or selling_price <= 0:
            results['errors'].append({'row': idx, 'error': 'selling_price must be a positive number'})
            continue

        original_cost = _to_decimal(_get(row, 'original_cost'))
        gst_val = _to_decimal(row.get(field_map.get('gst')) if 'gst' in field_map else None)
        quantity = _to_int(row.get(field_map.get('quantity')) if 'quantity' in field_map else None)

        is_active_val = None
        status_val = None
        if 'is_active' in field_map:
            is_active_val = _to_bool(_get(row, 'is_active'), default=True)
        if 'status' in field_map:
            status_val = _to_bool(row.get(field_map.get('status')), default=True)

        availability_val = _get(row, 'availability_timings')

        payload = {
            'item_name': item_name,
            'sku': row.get(field_map.get('sku')) if 'sku' in field_map else None,
            'description': row.get(field_map.get('description')) if 'description' in field_map else None,
            'item_category': _get(row, 'item_category'),
            'item_type': _get(row, 'item_type'),
            'preparation_time': _get(row, 'preparation_time'),
            'quantity': quantity,
            'original_cost': original_cost,
            'gst': gst_val,
            'selling_price': selling_price,
            'size_label': _get(row, 'size_label'),
            'category_id': _to_int(_get(row, 'category_id')),
            'sub_Category_id': _to_int(_get(row, 'sub_category_id')),
            'sub_category': _get(row, 'sub_category'),
        }

        if availability_val is not None and str(availability_val).strip() != '':
            payload['availability_timings'] = str(availability_val)

        if is_active_val is not None:
            payload['is_active'] = is_active_val
        if status_val is not None:
            payload['status'] = status_val

        serializer = MenuItemsSerializer(data=payload, context={"request": request})
        if not serializer.is_valid():
            results['errors'].append({'row': idx, 'error': serializer.errors})
            continue

        if not dry_run:
            menu_item = serializer.save(business_id=business)
            # Create default variant for bulk uploaded menu items
            MenuItemVariant.objects.create(
                item=menu_item,
                size_label=payload.get('size_label') or 'Regular',
                selling_price=selling_price,
                original_cost=original_cost,
                gst=gst_val,
                stock_qty=0,
                is_active=True
            )
        results['created'] += 1

    return Response({
        'business_id': business.business_id,
        'dry_run': dry_run,
        **results
    }, status=status.HTTP_200_OK)

@swagger_auto_schema(
    method='GET',
    tags=['Business'],
    manual_parameters=[
        openapi.Parameter(
            'userID',
            openapi.IN_QUERY,
            description='User ID retrieving the menu item',
            type=openapi.TYPE_STRING,
            required=True
        ),
        openapi.Parameter(
            'business_id',
            openapi.IN_QUERY,
            description='Business ID for the menu item',
            type=openapi.TYPE_STRING,
            required=True
        ),
        openapi.Parameter(
            'item_id',
            openapi.IN_QUERY,
            description='Menu item ID to retrieve',
            type=openapi.TYPE_STRING,
            required=True
        ),
    ],
    responses={
        200: openapi.Response(
            description='Menu item retrieved successfully with all variants (active and inactive)',
            examples={
                'application/json': {
                    'message': 'Menu item retrieved successfully',
                    'menu_item': {
                        'item_id': 182436,
                        'item_name': 'Arcot Chicken Dum Biryani',
                        'sku': 'arcotchickendumbiryanilarge',
                        'description': 'Authentic Arcot-style dum biryani...',
                        'item_image': 'http://example.com/media/menuItems/182436.png',
                        'category_id': 471,
                        'category_name': 'Biryanis',
                        'sub_Category_id': 429,
                        'sub_category_name': 'Biryani',
                        'item_type': 'Non-veg',
                        'availability_timings': {
                            'mon': [{'open': '07:00', 'close': '23:00'}]
                        },
                        'preparation_time': '10',
                        'quantity': 263,
                        'gst': 5.0,
                        'charges': '12.70',
                        'size_label': 'Large',
                        'is_active': True,
                        'status': True,
                        'is_variable': False,
                        'variants': [
                            {
                                'variant_id': 187,
                                'item': 182436,
                                'size_label': 'Double',
                                'sku': 'arcotchickendumbiryani',
                                'selling_price': '15.00',
                                'mrp': None,
                                'original_cost': '15.00',
                                'stock_qty': 90,
                                'charges': '0.75',
                                'gst': '5.00',
                                'is_active': True,
                                'can_add_to_cart': True,
                                'created_at': '2026-03-09T07:03:34',
                                'updated_at': '2026-03-17T18:49:41'
                            },
                            {
                                'variant_id': 188,
                                'item': 182436,
                                'size_label': 'Single',
                                'sku': 'arcotchickendumbiryani_1',
                                'selling_price': '209.52',
                                'mrp': None,
                                'original_cost': '300.00',
                                'stock_qty': 75,
                                'charges': '15.00',
                                'gst': '5.00',
                                'is_active': False,
                                'can_add_to_cart': False,
                                'created_at': '2026-03-09T07:03:34',
                                'updated_at': '2026-03-17T09:38:48'
                            }
                        ],
                        'created_at': '2025-10-23T09:18:36',
                        'updated_at': '2026-03-17T18:49:32'
                    }
                }
            }
        ),
        400: openapi.Response(
            description='Bad request - missing or invalid parameters',
            examples={
                'application/json': {
                    'error': 'userID and business_id are required'
                }
            }
        ),
        404: openapi.Response(
            description='User, business, or menu item not found',
            examples={
                'application/json': {
                    'error': 'Invalid userID'
                }
            }
        )
    }
)
@swagger_auto_schema(
    method='PUT',
    tags=['Business'],
    manual_parameters=[
        openapi.Parameter(
            'userID',
            openapi.IN_QUERY,
            description='User ID updating the menu item',
            type=openapi.TYPE_STRING,
            required=True
        ),
        openapi.Parameter(
            'business_id',
            openapi.IN_QUERY,
            description='Business ID for the menu item',
            type=openapi.TYPE_STRING,
            required=True
        ),
        openapi.Parameter(
            'item_id',
            openapi.IN_QUERY,
            description='Menu item ID to update',
            type=openapi.TYPE_STRING,
            required=True
        ),
    ],
    request_body=openapi.Schema(
        type=openapi.TYPE_OBJECT,
        properties={
            'item_name': openapi.Schema(type=openapi.TYPE_STRING, description='Menu item name'),
            'category': openapi.Schema(type=openapi.TYPE_STRING, description='Menu item category'),
            'subcategory': openapi.Schema(type=openapi.TYPE_STRING, description='Menu item subcategory'),
            'description': openapi.Schema(type=openapi.TYPE_STRING, description='Menu item description'),
            'price': openapi.Schema(type=openapi.TYPE_NUMBER, format='decimal', description='Menu item price'),
            'image': openapi.Schema(type=openapi.TYPE_FILE, description='Menu item image'),
            'is_available': openapi.Schema(type=openapi.TYPE_BOOLEAN, description='Item availability status'),
            'preparation_time': openapi.Schema(type=openapi.TYPE_INTEGER, description='Preparation time in minutes'),
            'ingredients': openapi.Schema(type=openapi.TYPE_ARRAY, items=openapi.Schema(type=openapi.TYPE_STRING), description='List of ingredients'),
            'allergens': openapi.Schema(type=openapi.TYPE_ARRAY, items=openapi.Schema(type=openapi.TYPE_STRING), description='List of allergens'),
        }
    ),
    responses={
        200: openapi.Response(
            description='Menu item updated successfully',
            examples={
                'application/json': {
                    'message': 'Menu item updated successfully',
                    'item_id': 'string'
                }
            }
        ),
        400: openapi.Response(
            description='Bad request - missing or invalid parameters',
            examples={
                'application/json': {
                    'error': 'userID and business_id are required'
                }
            }
        ),
        404: openapi.Response(
            description='User, business, or menu item not found',
            examples={
                'application/json': {
                    'error': 'Invalid userID'
                }
            }
        )
    }
)
@swagger_auto_schema(
    method='PATCH',
    tags=['Business'],
    manual_parameters=[
        openapi.Parameter(
            'userID',
            openapi.IN_QUERY,
            description='User ID updating the menu item',
            type=openapi.TYPE_STRING,
            required=True
        ),
        openapi.Parameter(
            'business_id',
            openapi.IN_QUERY,
            description='Business ID for the menu item',
            type=openapi.TYPE_STRING,
            required=True
        ),
        openapi.Parameter(
            'item_id',
            openapi.IN_QUERY,
            description='Menu item ID to update',
            type=openapi.TYPE_STRING,
            required=True
        ),
    ],
    request_body=openapi.Schema(
        type=openapi.TYPE_OBJECT,
        properties={
            'item_name': openapi.Schema(type=openapi.TYPE_STRING, description='Menu item name'),
            'category': openapi.Schema(type=openapi.TYPE_STRING, description='Menu item category'),
            'subcategory': openapi.Schema(type=openapi.TYPE_STRING, description='Menu item subcategory'),
            'description': openapi.Schema(type=openapi.TYPE_STRING, description='Menu item description'),
            'price': openapi.Schema(type=openapi.TYPE_NUMBER, format='decimal', description='Menu item price'),
            'image': openapi.Schema(type=openapi.TYPE_FILE, description='Menu item image'),
            'is_available': openapi.Schema(type=openapi.TYPE_BOOLEAN, description='Item availability status'),
            'preparation_time': openapi.Schema(type=openapi.TYPE_INTEGER, description='Preparation time in minutes'),
        }
    ),
    responses={
        200: openapi.Response(
            description='Menu item patched successfully',
            examples={
                'application/json': {
                    'message': 'Menu item patched successfully',
                    'item_id': 'string'
                }
            }
        ),
        400: openapi.Response(
            description='Bad request - missing or invalid parameters',
            examples={
                'application/json': {
                    'error': 'userID and business_id are required'
                }
            }
        ),
        404: openapi.Response(
            description='User, business, or menu item not found',
            examples={
                'application/json': {
                    'error': 'Invalid userID'
                }
            }
        )
    }
)
@swagger_auto_schema(
    method='DELETE',
    tags=['Business'],
    manual_parameters=[
        openapi.Parameter(
            'userID',
            openapi.IN_QUERY,
            description='User ID deleting the menu item',
            type=openapi.TYPE_STRING,
            required=True
        ),
        openapi.Parameter(
            'business_id',
            openapi.IN_QUERY,
            description='Business ID for the menu item',
            type=openapi.TYPE_STRING,
            required=True
        ),
        openapi.Parameter(
            'item_id',
            openapi.IN_QUERY,
            description='Menu item ID to delete',
            type=openapi.TYPE_STRING,
            required=True
        ),
    ],
    responses={
        200: openapi.Response(
            description='Menu item deleted successfully',
            examples={
                'application/json': {
                    'message': 'Menu item deleted successfully',
                    'item_id': 'string'
                }
            }
        ),
        400: openapi.Response(
            description='Bad request - missing or invalid parameters',
            examples={
                'application/json': {
                    'error': 'userID and business_id are required'
                }
            }
        ),
        404: openapi.Response(
            description='User, business, or menu item not found',
            examples={
                'application/json': {
                    'error': 'Invalid userID'
                }
            }
        )
    }
)
@api_view(['GET', 'PUT', 'PATCH', 'DELETE'])
@parser_classes([MultiPartParser, FormParser, JSONParser])
def MenuItemsManagementAPIView(request, item_id):
    user_id = request.query_params.get("userID") or request.query_params.get("user_id")
    business_id = request.query_params.get("business_id")
    menu_item = request.query_params.get("item_id")
    
    if not user_id or not business_id:
        return Response({"error": "userID and business_id are required"}, status=status.HTTP_400_BAD_REQUEST)
    
    # Validate user exists and is active
    try:
        user = Registration.objects.get(user_id=user_id, status=True)
    except Registration.DoesNotExist:
        return Response({"error": "Invalid userID"}, status=status.HTTP_404_NOT_FOUND)
    
    # Validate business exists and is active
    try:
        business = Business.objects.get(business_id=business_id, status=True)
    except Business.DoesNotExist:
        return Response({"error": "Invalid business_id"}, status=status.HTTP_404_NOT_FOUND)

    # Check if user is a POS/KOT counter user via business_role_management
    is_pos_user = False
    pos_master_business_id = None
    with connection.cursor() as cursor:
        # First check if user is POS for the specific business_id
        cursor.execute(
            """
            SELECT role, business_id FROM business_role_management
            WHERE assigned_to = %s 
              AND business_id COLLATE utf8mb4_0900_ai_ci = CAST(%s AS CHAR) COLLATE utf8mb4_0900_ai_ci 
              AND status = 1
            """,
            [user_id, business_id]
        )
        row = cursor.fetchone()
        if row and row[0] and row[0].upper() in ['POS', 'KOT', 'COUNTER']:
            is_pos_user = True
        else:
            # Check if user is POS for a master business that has this business as a child
            cursor.execute(
                """
                SELECT brm.role, brm.business_id 
                FROM business_role_management brm
                INNER JOIN businesses b 
                    ON b.business_id COLLATE utf8mb4_0900_ai_ci = brm.business_id COLLATE utf8mb4_0900_ai_ci
                WHERE brm.assigned_to = %s 
                  AND brm.status = 1 
                  AND b.level = 'master'
                  AND b.status = 1
                  AND EXISTS (
                      SELECT 1 FROM businesses child 
                      WHERE child.master COLLATE utf8mb4_0900_ai_ci = brm.business_id COLLATE utf8mb4_0900_ai_ci
                        AND child.business_id COLLATE utf8mb4_0900_ai_ci = CONVERT(%s USING utf8mb4) COLLATE utf8mb4_0900_ai_ci
                        AND child.status = 1
                  )
                """,
                [user_id, business_id]
            )
            master_row = cursor.fetchone()
            if master_row and master_row[0] and master_row[0].upper() in ['POS', 'KOT', 'COUNTER']:
                is_pos_user = True
                pos_master_business_id = master_row[1]
            else:
                pass

    # Resolve user's mapping and allowed business group
    try:
        user_mapping = BusinessMapping.objects.select_related('business').get(user__user_id=user_id, status=True)
    except BusinessMapping.DoesNotExist:
        # If POS user, allow access
        if is_pos_user:
            user_mapping = None  # Set to None to bypass mapping checks
        else:
            return Response({"error": "User does not have access to any business"}, status=status.HTTP_403_FORBIDDEN)

    level_val = (business.level or '').strip().lower()
    if 'master' in level_val:
        child_ids = list(Business.objects.filter(master=business.business_id, status=True).values_list('business_id', flat=True))
        allowed_business_ids = set([business.business_id] + child_ids)
    else:
        allowed_business_ids = {business.business_id}
        if business.master:
            allowed_business_ids.add(business.master)

    # Skip mapping check if POS user
    if not is_pos_user:
        if user_mapping.business.business_id not in allowed_business_ids:
            return Response({"error": "User does not have access to this business"}, status=status.HTTP_403_FORBIDDEN)
    
    # Get the menu item within allowed scope
    try:
        if is_pos_user:
            # For POS users, determine the master business ID
            # If pos_master_business_id is set, user is POS for master and we're querying a child
            # Otherwise, check if the business we're querying is a master
            master_biz_id = pos_master_business_id
            if not master_biz_id and 'master' in level_val:
                master_biz_id = business.business_id
            
            if master_biz_id:
                # User is POS for master business (either directly or indirectly via child)
                # Search in master + all children
                child_ids = list(Business.objects.filter(master=master_biz_id, status=True).values_list('business_id', flat=True))
                pos_allowed_business_ids = set([master_biz_id] + child_ids)
                menu_item = MenuItems.objects.get(item_id=item_id, business_id__business_id__in=pos_allowed_business_ids)
                print(f"[MenuItemsManagementAPIView] POS user - searching in master + children: {pos_allowed_business_ids}")
            else:
                # For POS users, just get the item for the business (not a master business)
                menu_item = MenuItems.objects.get(item_id=item_id, business_id=business)
        elif 'master' in level_val and user_mapping and user_mapping.business.business_id == business.business_id:
            menu_item = MenuItems.objects.get(item_id=item_id, business_id__business_id__in=allowed_business_ids)
        else:
            target_business = business
            if 'master' in level_val and user_mapping and user_mapping.business.business_id in allowed_business_ids and user_mapping.business.business_id != business.business_id:
                target_business = user_mapping.business
            menu_item = MenuItems.objects.get(item_id=item_id, business_id=target_business)
    except MenuItems.DoesNotExist:
        return Response({"error": "Menu item not found"}, status=status.HTTP_404_NOT_FOUND)
    
    # Handle GET request - retrieve menu item with all variants (active and inactive)
    if request.method == 'GET':
        # Use a serializer that shows all variants for management purposes
        serializer = MenuItemsSerializer(menu_item, context={"request": request})
        
        return Response({
            "message": "Menu item retrieved successfully",
            "menu_item": serializer.data
        }, status=status.HTTP_200_OK)
    
    # Handle DELETE request
    if request.method == 'DELETE':
        item_name = menu_item.item_name
        menu_item.delete()
        return Response({
            "message": f"Menu item '{item_name}' deleted successfully",
            "item_id": item_id
        }, status=status.HTTP_200_OK)
    
    # Handle PUT and PATCH requests (UPDATE)
    if request.method in ['PUT', 'PATCH']:
        # Extract uploaded image file (if any) but do NOT send it through the serializer.
        # We'll attach it directly to the model after other fields are validated.
        uploaded_image = request.FILES.get('item_image')

        # Prepare data for serializer (exclude item_image entirely)
        # Create a proper mutable copy of the data without using deepcopy
        from django.http import QueryDict
        if isinstance(request.data, QueryDict):
            # Manual copy to avoid pickle issues with file uploads
            data = QueryDict(mutable=True)
            for key, value_list in request.data.lists():
                if key != 'item_image':  # Exclude file fields
                    data.setlist(key, value_list)
        else:
            # For non-QueryDict, filter out file objects
            data = {}
            for key, value in request.data.items():
                if not hasattr(value, 'read'):  # Exclude file objects
                    data[key] = value
        
        variant_source_data = dict(data) if isinstance(data, QueryDict) else data.copy() if hasattr(data, 'copy') else dict(data)

       
        # Check if the menu item is currently variable
        is_currently_variable = menu_item.is_variable
        
        # Variant update safety check: require variant_id if >1 active variants AND updating variant-specific fields
        variant_specific_fields = ['original_cost', 'stock_qty', 'stock', 'gst', 'gst_percentage', 'size_label', 'mrp']     
        # Check if we're actually updating variant-specific fields
        # Don't require variant_id if is_variable is explicitly set to false OR if we're updating non-variant fields
        has_variant_fields = any(field in data for field in variant_specific_fields)     
        # If is_variable is explicitly false or item is not variable, don't require variant_id even if variant fields are present
        if data.get('is_variable') == False or not is_currently_variable:
            has_variant_fields = False

        variant_id_from_request = data.get('variant_id')

        # Only require variant_id if we have multiple variants AND are updating variant-specific fields
        
        if has_variant_fields and not variant_id_from_request:
            # Count active variants for this menu item
            active_variant_count = MenuItemVariant.objects.filter(item=menu_item, is_active=True).count()
            if active_variant_count > 1:
                return Response({
                    "error": "Multiple active variants found. Please specify 'variant_id' to update a specific variant.",
                    "details": {
                        "item_id": item_id,
                        "active_variants_count": active_variant_count,
                        "available_variants": list(MenuItemVariant.objects.filter(
                            item=menu_item, is_active=True
                        ).values('variant_id', 'size_label', 'selling_price'))
                    }
                }, status=status.HTTP_400_BAD_REQUEST)

        # Remove item_image from data in all cases so DRF doesn't try to re-validate it
        if 'item_image' in data:
            data.pop('item_image', None)
        
        # Parse JSON fields that might come as strings from FormData
        json_fields = ['availability_timings']
        for field in json_fields:
            if field in data and isinstance(data[field], str):
                # Only try to parse non-empty strings
                if data[field].strip():
                    try:
                        data[field] = json.loads(data[field])
                    except (json.JSONDecodeError, ValueError, TypeError) as e:
                        # Return early with clear error message if JSON parsing fails
                        return Response({
                            "error": "Invalid JSON format",
                            "details": {
                                field: [f"Value must be valid JSON. Parse error: {str(e)}"]
                            }
                        }, status=status.HTTP_400_BAD_REQUEST)
                else:
                    # Empty string should be treated as None/null
                    data[field] = None
        
        # Handle gst_percentage -> gst field mapping
        if 'gst_percentage' in data and 'gst' not in data:
            data['gst'] = data['gst_percentage']
        
        # Convert numeric fields if they come as strings
        numeric_fields = ['quantity', 'original_cost', 'gst', 'gst_percentage', 'selling_price']
        for field in numeric_fields:
            if field in data:
                # Only convert if it's a string, leave other types (int, float, Decimal) as-is
                if isinstance(data[field], str):
                    try:
                        # Handle empty strings
                        if data[field].strip() == '':
                            if field == 'quantity':
                                data[field] = 0
                            else:
                                data.pop(field, None)
                        else:
                            if field in ['gst', 'gst_percentage']:
                                data[field] = float(data[field])
                            else:
                                data[field] = Decimal(data[field])
                    except (ValueError, TypeError):
                        pass
                # Handle numeric types - ensure they're appropriate type
                elif isinstance(data[field], (int, float)):
                    if field in ['gst', 'gst_percentage']:
                        data[field] = float(data[field])
                    else:
                        data[field] = Decimal(str(data[field]))
        
        # Handle boolean fields
        boolean_fields = ['status', 'is_active', 'is_variable']
        for field in boolean_fields:
            if field in data:
                if isinstance(data[field], str):
                    data[field] = data[field].lower() in ('true', '1', 'yes')
                elif isinstance(data[field], int):
                    data[field] = bool(data[field])

        # Always treat updates as partial to avoid requiring all fields.
        serializer = MenuItemsSerializer(menu_item, data=data, partial=True, context={"request": request})

        if serializer.is_valid():
            updated_menu_item = serializer.save()

            # If a new image was uploaded, attach it directly to the model instance.
            if uploaded_image:
                compressed_image = compress_image(uploaded_image)
                if compressed_image:
                    updated_menu_item.item_image = compressed_image
                    updated_menu_item.save(update_fields=['item_image'])
            
            # Get the serialized data with the image URL
            response_serializer = MenuItemsSerializer(updated_menu_item, context={"request": request})
            
            return Response({
                "message": "Menu item updated successfully",
                "item_id": updated_menu_item.item_id,
                "menu_item_details": response_serializer.data
            }, status=status.HTTP_200_OK)
        
        print(f"[MenuItemsManagementAPIView] Validation Errors: {serializer.errors}")
        return Response({"error": "Validation failed", "details": serializer.errors}, status=status.HTTP_400_BAD_REQUEST)

@swagger_auto_schema(methods=['POST'], tags=['Business'])
@api_view(['POST'])
def addBOMItems(request):
    if request.method == 'POST':
        business_id = request.query_params.get("business_id")
        product_id = request.query_params.get("product_id")
        user_id = request.query_params.get("user_id")  # Add user_id for logging

        if not business_id or not product_id:
            return Response({"error": "business_id and product_id are required"}, status=status.HTTP_400_BAD_REQUEST)

        try:
            business = Business.objects.get(business_id=business_id, status=True)
        except Business.DoesNotExist:
            return Response({"error": "Invalid business_id"}, status=status.HTTP_404_NOT_FOUND)

        # Check if menu item exists
        try:
            menu_item = MenuItems.objects.get(item_id=product_id)
        except MenuItems.DoesNotExist:
            return Response({"error": f"Menu item with ID {product_id} does not exist"}, status=status.HTTP_404_NOT_FOUND)

        # Check if menu item belongs to the business
        try:
            item = MenuItems.objects.get(item_id=product_id, business_id=business, status=True)
        except MenuItems.DoesNotExist:
            return Response({
                "error": f"Menu item {product_id} doesn't belong to business {business_id}",
                "debug_info": {
                    "requested_business_id": business_id,
                    "menu_item_business_id": menu_item.business_id.business_id,
                    "menu_item_status": menu_item.status
                }
            }, status=status.HTTP_404_NOT_FOUND)

        serializer = BOMSerializer(data=request.data, context={"request": request})
        if serializer.is_valid():
            from django.db import transaction, connection
            
            try:
                with transaction.atomic():
                    # Save the BOM item first with default status = 1
                    bom = serializer.save(business_id=business, product_id=item)
                    bom.status = 1  # Set default status as active
                    bom.save()
                    
                    # Create log entry after BOM is created (satisfies FK constraint)
                    new_data = {
                        'bom_id': bom.bom_id,
                        'business_id': str(bom.business_id.business_id),
                        'product_id': bom.product_id.item_id,
                        'ingredients': bom.ingredients,
                        'quantity': str(bom.quantity),
                        'unit': bom.unit,
                        'cost': str(bom.cost),
                        'status': bom.status,
                        'created_at': bom.created_at.isoformat() if bom.created_at else None,
                        'updated_at': bom.updated_at.isoformat() if bom.updated_at else None
                    }
                    
                    # Create log entry with user_id
                    BillOfMaterialsLog.objects.create(
                        bom_id=bom.bom_id,
                        user_id=int(user_id) if user_id else None,
                        action_type='INSERT',
                        old_data=None,
                        new_data=new_data
                    )
                    
            except Exception as e:
                return Response({
                    "error": f"Failed to create BOM item: {str(e)}"
                }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
            
            response_serializer = BOMSerializer(bom)
            return Response({
                "message": "BOM item added successfully",
                "bom_id": bom.bom_id,
                "bom_details": response_serializer.data
            }, status=status.HTTP_201_CREATED)
        
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

@swagger_auto_schema(methods=['PUT', 'PATCH', 'DELETE'], tags=['Business'])
@api_view(['PUT', 'PATCH', 'DELETE'])
def BOMItemsManagementAPIView(request):
    user_id = request.query_params.get("user_id")
    business_id = request.query_params.get("business_id")
    bom_id = request.query_params.get("bom_id")

    if not user_id or not business_id or not bom_id:
        return Response({"error": "user_id, business_id and bom_id are required"}, status=status.HTTP_400_BAD_REQUEST)

    try:
        bom = BOM.objects.get(bom_id=bom_id, business_id=business_id, status=1)
    except BOM.DoesNotExist:
        # Check if BOM exists but is soft deleted
        try:
            soft_deleted_bom = BOM.objects.get(bom_id=bom_id, business_id=business_id, status=0)
            return Response({"error": "BOM item is already deleted"}, status=status.HTTP_410_GONE)
        except BOM.DoesNotExist:
            return Response({"error": "Invalid bom_id"}, status=status.HTTP_404_NOT_FOUND)

    if request.method == 'PUT' or request.method == 'PATCH':
        from django.db import transaction
        
        try:
            with transaction.atomic():
                # Capture old data before update
                old_data = {
                    'bom_id': bom.bom_id,
                    'business_id': str(bom.business_id.business_id),
                    'product_id': bom.product_id.item_id,
                    'ingredients': bom.ingredients,
                    'quantity': str(bom.quantity),
                    'unit': bom.unit,
                    'cost': str(bom.cost),
                    'status': bom.status,
                    'created_at': bom.created_at.isoformat() if bom.created_at else None,
                    'updated_at': bom.updated_at.isoformat() if bom.updated_at else None
                }
                
                serializer = BOMSerializer(bom, data=request.data, partial=True)
                if serializer.is_valid():
                    updated_bom = serializer.save()
                    
                    # Capture new data after update
                    new_data = {
                        'bom_id': updated_bom.bom_id,
                        'business_id': str(updated_bom.business_id.business_id),
                        'product_id': updated_bom.product_id.item_id,
                        'ingredients': updated_bom.ingredients,
                        'quantity': str(updated_bom.quantity),
                        'unit': updated_bom.unit,
                        'cost': str(updated_bom.cost),
                        'status': updated_bom.status,
                        'created_at': updated_bom.created_at.isoformat() if updated_bom.created_at else None,
                        'updated_at': updated_bom.updated_at.isoformat() if updated_bom.updated_at else None
                    }
                    
                    # Create log entry for update
                    BillOfMaterialsLog.objects.create(
                        bom_id=updated_bom.bom_id,
                        user_id=int(user_id),
                        action_type='UPDATE',
                        old_data=old_data,
                        new_data=new_data
                    )
                    
                    return Response({
                        "message": "BOM item updated successfully",
                        "bom_id": updated_bom.bom_id,
                        "bom_details": serializer.data
                    }, status=status.HTTP_200_OK)
                return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
                
        except Exception as e:
            return Response({
                "error": f"Failed to update BOM item: {str(e)}"
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    
    elif request.method == 'DELETE':
        from django.db import transaction
        
        try:
            with transaction.atomic():
                # Prepare old_data for logging (before soft delete)
                old_data = {
                    'bom_id': bom.bom_id,
                    'business_id': str(bom.business_id.business_id),
                    'product_id': bom.product_id.item_id,
                    'ingredients': bom.ingredients,
                    'quantity': str(bom.quantity),
                    'unit': bom.unit,
                    'cost': str(bom.cost),
                    'status': bom.status,
                    'created_at': bom.created_at.isoformat() if bom.created_at else None,
                    'updated_at': bom.updated_at.isoformat() if bom.updated_at else None
                }
                
                # Perform soft delete by setting status = 0
                bom.status = 0
                bom.save()
                
                # Prepare new_data after soft delete
                new_data = {
                    'bom_id': bom.bom_id,
                    'business_id': str(bom.business_id.business_id),
                    'product_id': bom.product_id.item_id,
                    'ingredients': bom.ingredients,
                    'quantity': str(bom.quantity),
                    'unit': bom.unit,
                    'cost': str(bom.cost),
                    'status': bom.status,  # Now 0 (soft deleted)
                    'created_at': bom.created_at.isoformat() if bom.created_at else None,
                    'updated_at': bom.updated_at.isoformat() if bom.updated_at else None
                }
                
                # Create log entry for soft delete
                BillOfMaterialsLog.objects.create(
                    bom_id=bom.bom_id,
                    user_id=int(user_id),
                    action_type='DELETE',
                    old_data=old_data,
                    new_data=new_data
                )
                
        except Exception as e:
            return Response({
                "error": f"Failed to delete BOM item: {str(e)}"
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        
        return Response({
            "message": "BOM item deleted successfully (soft delete)",
            "bom_id": bom_id,
            "status": "inactive"
        }, status=status.HTTP_200_OK)

@swagger_auto_schema(
    method='POST',
    tags=['Business'],
    manual_parameters=[
        openapi.Parameter(
            'user_id',
            openapi.IN_QUERY,
            description='User ID adding the product item',
            type=openapi.TYPE_STRING,
            required=True
        ),
        openapi.Parameter(
            'business_id',
            openapi.IN_QUERY,
            description='Business ID for the product item',
            type=openapi.TYPE_STRING,
            required=True
        ),
    ],
    request_body=openapi.Schema(
        type=openapi.TYPE_OBJECT,
        properties={
            'item_name': openapi.Schema(type=openapi.TYPE_STRING, description='Product item name'),
            'category': openapi.Schema(type=openapi.TYPE_STRING, description='Product category'),
            'subcategory': openapi.Schema(type=openapi.TYPE_STRING, description='Product subcategory'),
            'description': openapi.Schema(type=openapi.TYPE_STRING, description='Product description'),
            'selling_price': openapi.Schema(type=openapi.TYPE_NUMBER, format='decimal', description='Selling price'),
            'cost_price': openapi.Schema(type=openapi.TYPE_NUMBER, format='decimal', description='Cost price'),
            'stock_quantity': openapi.Schema(type=openapi.TYPE_INTEGER, description='Stock quantity'),
            'min_stock_level': openapi.Schema(type=openapi.TYPE_INTEGER, description='Minimum stock level'),
            'sku': openapi.Schema(type=openapi.TYPE_STRING, description='Stock keeping unit'),
            'barcode': openapi.Schema(type=openapi.TYPE_STRING, description='Product barcode'),
            'image': openapi.Schema(type=openapi.TYPE_FILE, description='Product image'),
            'sub_images': openapi.Schema(type=openapi.TYPE_ARRAY, items=openapi.Schema(type=openapi.TYPE_FILE), description='Additional product images'),
            'is_available': openapi.Schema(type=openapi.TYPE_BOOLEAN, description='Product availability status'),
            'weight': openapi.Schema(type=openapi.TYPE_NUMBER, description='Product weight'),
            'dimensions': openapi.Schema(type=openapi.TYPE_OBJECT, description='Product dimensions'),
            'tags': openapi.Schema(type=openapi.TYPE_ARRAY, items=openapi.Schema(type=openapi.TYPE_STRING), description='Product tags'),
        },
        required=['item_name', 'category', 'selling_price']
    ),
    responses={
        201: openapi.Response(
            description='Product item created successfully',
            examples={
                'application/json': {
                    'message': 'Product item created successfully',
                    'item_id': 'string',
                    'item_name': 'string',
                    'selling_price': 'decimal'
                }
            }
        ),
        400: openapi.Response(
            description='Bad request - missing or invalid parameters',
            examples={
                'application/json': {
                    'error': 'user_id and business_id are required'
                }
            }
        ),
        404: openapi.Response(
            description='User or business not found',
            examples={
                'application/json': {
                    'error': 'Invalid user_id'
                }
            }
        )
    }
)
@api_view(['POST'])
@parser_classes([MultiPartParser, FormParser, JSONParser])
def addProductItems(request):
    if request.method == 'POST':
        user_id = request.query_params.get("user_id")
        business_id = request.query_params.get("business_id")

        if not user_id or not business_id:
            return Response({"error": "user_id and business_id are required"}, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            user = Registration.objects.get(user_id=user_id, status=True)
        except Registration.DoesNotExist:
            return Response({"error": "Invalid user_id"}, status=status.HTTP_404_NOT_FOUND)
        
        try:
            business = Business.objects.get(business_id=business_id, status=True)
        except Business.DoesNotExist:
            return Response({"error": "Invalid business_id"}, status=status.HTTP_404_NOT_FOUND)
        
        # Check if user is a POS/KOT counter user via business_role_management
        is_pos_user = False
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT role FROM business_role_management
                WHERE assigned_to = %s AND business_id = %s AND status = 1
                """,
                [user_id, business_id]
            )
            row = cursor.fetchone()
            if row and row[0] and row[0].upper() in ['POS', 'KOT', 'COUNTER']:
                is_pos_user = True
        
        # Check user access: direct mapping OR access via master business
        if not is_pos_user:
            # Get user's business mapping
            user_mapping = BusinessMapping.objects.filter(user__user_id=user_id, status=True).select_related('business').first()
            
            if not user_mapping:
                return Response({"error": "User does not have access to any business"}, status=status.HTTP_403_FORBIDDEN)
            
            # Get the user's mapped business
            user_business = user_mapping.business
            
            # Determine if user has access to the requested business
            # User has access if:
            # 1. Direct mapping to the requested business
            # 2. Mapped to master business and requesting a child business
            # 3. Mapped to a child business and requesting the master
            
            has_access = False
            
            # Check if user's business matches the requested business
            if user_business.business_id == business_id:
                has_access = True
            # Check if user's business is the master of the requested business
            elif business.master and user_business.business_id == business.master:
                has_access = True
            # Check if requested business is the master of user's business
            elif user_business.master and user_business.master == business_id:
                has_access = True
            
            if not has_access:
                return Response({"error": "User does not have access to this business"}, status=status.HTTP_403_FORBIDDEN)

        data = request.data.copy()

        bt = (business.businessType or '').strip().upper()
        is_grocery_business = bt == 'R01'
        is_fashion_business = bt == 'R08'

        if is_grocery_business:
            if 'is_visible' not in data or str(data.get('is_visible')).strip() == '':
                data['is_visible'] = 1
        else:
            data.pop('is_visible', None)
        
        if is_grocery_business and 'is_customizable' in data:
            v = data.get('is_customizable')
            if v in [None, '', 'null']:
                data.pop('is_customizable', None)
            elif isinstance(v, str):
                data['is_customizable'] = v.strip().lower() in ('1', 'true', 'yes', 'y')
            else:
                data['is_customizable'] = bool(v)

        if not is_grocery_business:
            data.pop('is_customizable', None)
        
        # Normalize category field name
        if 'category_id' in data and 'category' not in data:
            data['category'] = data.get('category_id')
        
        # Ensure category is present for grocery products; fallback gracefully
        if is_grocery_business and not data.get('category'):
            # Try derive from category_name or sub_category
            cat_name = data.get('category_name') or data.get('sub_category')
            cat_obj = None
            try:
                if cat_name:
                    cat_obj = GroceriesCategories.objects.filter(category_name__iexact=cat_name).first()
            except Exception:
                cat_obj = None
            if not cat_obj:
                # Use or create a default 'Uncategorized' category
                try:
                    cat_obj, _ = GroceriesCategories.objects.get_or_create(category_name='Uncategorized', defaults={'gst_rate': 0})
                except Exception:
                    cat_obj = GroceriesCategories.objects.order_by('category_id').first()
            if cat_obj:
                data['category'] = cat_obj.category_id

        # Subcategory Auto-Resolution
        sub_id = data.get('sub_category_id') or data.get('subcategory_id') or data.get('subcategory')
        try:
            # If the value is a numeric ID, try resolving it to a name
            if sub_id and (isinstance(sub_id, int) or (isinstance(sub_id, str) and sub_id.isdigit())):
                resolved_name = resolve_subcategory_name(sub_id)
                if resolved_name:
                    if is_grocery_business:
                        data['sub_category'] = resolved_name
                        data['sub_category_id'] = sub_id
                    elif is_fashion_business:
                        data['subcategory'] = resolved_name
                        data['subcategory_id'] = sub_id # Map to numeric field if client passed it
        except Exception:
            pass

        # Assign business FK
        data['business_id'] = business.business_id

        # Handle image upload based on product type
        if is_grocery_business:
            # Grocery products use main_image (CharField) and sub_images (JSONField)
                
            # Handle main_image (first image)
            if 'main_image' in request.FILES:
                saved_path = upload_image_to_s3(
                    request.FILES['main_image'], 
                    folder='groceries_images',
                    compress=True,
                    use_uuid=False
                )
                if saved_path:
                    data['main_image'] = saved_path
            
            # Collect all sub_image files
            sub_image_files = []
            sub_image_keys = []
            for key in request.FILES:
                if key.startswith('sub_image_') or key == 'sub_images':
                    sub_image_keys.append(key)
            
            # Sort keys to maintain order
            sub_image_keys.sort()
            
            for key in sub_image_keys:
                if key == 'sub_images':
                    sub_image_files.extend(request.FILES.getlist(key))
                else:
                    sub_image_files.append(request.FILES[key])
            
            # Upload all sub_images using helper (array format)
            if sub_image_files:
                sub_images_array = upload_multiple_images_as_array(
                    sub_image_files,
                    folder='groceries_images',
                    compress=True,
                    use_uuid=False
                )
                if sub_images_array:
                    data['sub_images'] = sub_images_array
            
            # Convert QueryDict to regular dict to avoid list wrapping
            if hasattr(data, 'dict'):
                data = data.dict()
            
            # For grocery products, also handle business field name
            data['business'] = business.business_id

            # NEW: If frontend still sends sub_category_id/sub_category inside variant, move it to top level for product serializer
            vd_raw = data.get('variant')
            if vd_raw:
                vd = vd_raw
                if isinstance(vd, str):
                    try:
                        import json as _json
                        vd = _json.loads(vd)
                    except Exception:
                        vd = None
                if isinstance(vd, dict):
                    if 'sub_category' in vd and not data.get('sub_category'):
                        data['sub_category'] = vd['sub_category']
                    if 'sub_category_id' in vd and not data.get('sub_category_id'):
                        data['sub_category_id'] = vd['sub_category_id']

            # Handle is_featured field
            if 'is_featured' in data:
                v = data.get('is_featured')
                if v in [None, '', 'null']:
                    data['is_featured'] = False
                elif isinstance(v, str):
                    data['is_featured'] = v.strip().lower() in ('1', 'true', 'yes', 'y')
                else:
                    data['is_featured'] = bool(v)
            else:
                data['is_featured'] = False

            print(f"[DEBUG] Data being passed to GroceriesProductsSerializer: {data}")
            product_serializer = GroceriesProductsSerializer(data=data, context={"request": request})
        elif is_fashion_business:
            if 'item_name' in data and 'name' not in data:
                data['name'] = data.get('item_name')
            if 'brand_name' in data and 'brand' not in data:
                data['brand'] = data.get('brand_name')
            if 'gst_percentage' in data and 'gst_rate_default' not in data:
                data['gst_rate_default'] = data.get('gst_percentage')
            if 'gst' in data and 'gst_rate_default' not in data:
                data['gst_rate_default'] = data.get('gst')

            # Accept integer category_id for R08 (frontend sends universal_category_id)
            if 'item_category' in data and not data.get('category') and not data.get('category_id'):
                try:
                    cat_name = str(data.get('item_category') or '').strip()
                    if cat_name:
                        cat_obj = UniversalCategory.objects.filter(category_name__iexact=cat_name, parent_category_id__isnull=True).first()
                        if cat_obj:
                            data['category'] = cat_obj.category_id
                except Exception:
                    pass
            # Frontend may send universal_category_id as 'category' or 'category_id' (integer)
            if 'category_id' in data and isinstance(data['category_id'], (int, str)):
                try:
                    data['category'] = int(data['category_id'])
                except Exception:
                    pass
            if 'category' in data and isinstance(data['category'], (int, str)):
                try:
                    data['category'] = int(data['category'])
                except Exception:
                    pass

            # Resolve subcategory by name and store as string for R08 (subcategory_id is now VARCHAR)
            if 'sub_category' in data and not data.get('subcategory'):
                sub_name = str(data.get('sub_category') or '').strip()
                if sub_name:
                    data['subcategory'] = sub_name
            # Also accept subcategory_id/subcategory as string directly
            if 'subcategory_id' in data and isinstance(data['subcategory_id'], str):
                data['subcategory'] = data['subcategory_id'].strip()
            if 'subcategory' in data and isinstance(data['subcategory'], str):
                data['subcategory'] = data['subcategory'].strip()

            variant_source_data = data.copy()

            def _save_uploaded_image(field_name, folder, target_field=None):
                if field_name not in request.FILES:
                    return
                img_file = request.FILES[field_name]
                compressed = compress_image(img_file)
                if not compressed:
                    return
                orig_name = getattr(img_file, 'name', 'upload.jpg')
                base_name = os.path.splitext(os.path.basename(orig_name))[0]
                filename = f"{base_name}.jpg"
                rel_path = os.path.join(folder, filename).replace('\\', '/')
                
                # Save using default_storage (S3 or local)
                saved_name = default_storage.save(rel_path, compressed)
                
                data[target_field or field_name] = f"media/{saved_name}"

            # Use UUID-based filenames for R08 images (create and update)
            import uuid
            def _save_uploaded_image_uuid(field_name, folder, target_field=None):
                if field_name not in request.FILES:
                    return
                img_file = request.FILES[field_name]
                compressed = compress_image(img_file)
                if not compressed:
                    return
                # Generate UUID filename with .jpg extension
                unique_id = str(uuid.uuid4())
                filename = f"{unique_id}.jpg"
                rel_path = os.path.join(folder, filename).replace('\\', '/')
                
                # Save using default_storage (S3 or local)
                saved_name = default_storage.save(rel_path, compressed)
                
                data[target_field or field_name] = f"media/{saved_name}"

            try:
                # Handle main image and sub_images for fashion products
                sub_images_list = []
                
                # Handle main_image (first image)
                if 'main_image' in request.FILES or 'item_image' in request.FILES:
                    main_img_file = request.FILES.get('main_image') or request.FILES.get('item_image')
                    if main_img_file:
                        saved_path = upload_image_to_s3(
                            main_img_file,
                            folder='fashion_images',
                            compress=True,
                            use_uuid=True
                        )
                        if saved_path:
                            data['main_image'] = saved_path
                
                # Collect all sub_image files
                sub_image_files = []
                sub_image_keys = []
                for key in request.FILES:
                    if key.startswith('sub_image_') or key == 'sub_images':
                        sub_image_keys.append(key)
                
                # Sort keys to maintain order
                sub_image_keys.sort()
                
                for key in sub_image_keys:
                    if key == 'sub_images':
                        sub_image_files.extend(request.FILES.getlist(key))
                    else:
                        sub_image_files.append(request.FILES[key])
                
                # Upload all sub_images using helper (array format)
                if sub_image_files:
                    sub_images_array = upload_multiple_images_as_array(
                        sub_image_files,
                        folder='fashion_images',
                        compress=True,
                        use_uuid=True
                    )
                    if sub_images_array:
                        data['sub_images'] = sub_images_array
                
                # Handle is_featured field
                if 'is_featured' in data:
                    v = data.get('is_featured')
                    if v in [None, '', 'null']:
                        data['is_featured'] = False
                    elif isinstance(v, str):
                        data['is_featured'] = v.strip().lower() in ('1', 'true', 'yes', 'y')
                    else:
                        data['is_featured'] = bool(v)
                else:
                    data['is_featured'] = False
                
            except Exception as e:
                payload = {
                    "error": "Failed to save fashion product image",
                    "details": str(e),
                }
                if getattr(settings, 'DEBUG', False):
                    payload["trace"] = traceback.format_exc()
                return Response(payload, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

            if 'category_id' in data and 'category' not in data:
                data['category'] = data.get('category_id')
            if 'subcategory_id' in data and 'subcategory' not in data:
                data['subcategory'] = data.get('subcategory_id')
            if 'hsn' in data and 'hsn_code' not in data:
                data['hsn_code'] = data.get('hsn')

            # Skip strict universal_Categories DB check for R08; rely on BusinessMapping validation below
            if not is_fashion_business:
                try:
                    if data.get('category') is not None:
                        with connection.cursor() as cursor:
                            cursor.execute("SELECT 1 FROM universal_Categories WHERE category_id = %s", [data.get('category')])
                            if cursor.fetchone() is None:
                                return Response({"error": "Invalid category_id"}, status=status.HTTP_400_BAD_REQUEST)
                    if data.get('subcategory') is not None:
                        with connection.cursor() as cursor:
                            cursor.execute("SELECT parent_category_id FROM universal_Categories WHERE category_id = %s", [data.get('subcategory')])
                            row = cursor.fetchone()
                            if row is None:
                                return Response({"error": "Invalid subcategory_id"}, status=status.HTTP_400_BAD_REQUEST)
                            parent_id = row[0]
                            if parent_id and str(parent_id) != str(data.get('category')):
                                return Response({"error": "subcategory_id does not belong to category_id"}, status=status.HTTP_400_BAD_REQUEST)
                except Exception:
                    pass

            # For R08, validate category_id against category_mapping (business selected categories)
            if data.get('category') is not None:
                try:
                    category_id_val = int(data.get('category'))
                except Exception:
                    return Response({"error": "Invalid category_id"}, status=status.HTTP_400_BAD_REQUEST)

                allowed_bids = [business.business_id]
                if getattr(business, 'master', None) and str(business.master) != str(business.business_id):
                    allowed_bids.append(business.master)

                placeholders_cm = ','.join(['%s'] * len(allowed_bids))
                with connection.cursor() as cursor:
                    cursor.execute(
                        f"SELECT 1 FROM category_mapping WHERE business_id IN ({placeholders_cm}) AND category_id = %s AND is_active = 1 LIMIT 1",
                        allowed_bids + [category_id_val]
                    )
                    if cursor.fetchone() is None:
                        return Response({"error": "Invalid category_id for this business"}, status=status.HTTP_400_BAD_REQUEST)

            allowed_product_fields = {
                'business_id', 'category', 'subcategory',
                'name', 'description', 'brand',
                'base_price', 'gst_rate_default', 'hsn_code',
                'main_image', 'image2', 'image3', 'image4',
                'rating', 'item_placed_at',
                'is_active'
            }
            data = {k: data.get(k) for k in allowed_product_fields if k in data}
            product_serializer = FashionProductSerializer(data=data, context={"request": request})
        else:
            # Regular product items use item_image (ImageField)
            if 'item_image' in request.FILES:
                # Compress the image before saving
                request.FILES['item_image'] = compress_image(request.FILES['item_image'])
            
            product_serializer = productItemsSerializer(data=data, context={"request": request})
        
        if not product_serializer.is_valid():
            print("R08: product_serializer.is_valid() == False")
            print(f"R08: product_serializer errors: {product_serializer.errors}")
            return Response(product_serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        print("R08: product_serializer is valid; attempting product.save()")
        try:
            product = product_serializer.save()
            print(f"R08: product saved successfully: product_id={getattr(product, 'product_id', None)}")
        except Exception as e:
            print(f"R08: product_serializer.save() exception: {e}")
            payload = {
                "error": "Failed to create product",
                "details": str(e),
            }
            if getattr(settings, 'DEBUG', False):
                payload["trace"] = traceback.format_exc()
            return Response(payload, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        # Optional variant creation if provided (only for grocery products or R08)
        created_variants = []
        created_variant = None
        if is_grocery_business:
            # Debug: Check what's being received
            print(f"=== DEBUG VARIANT PROCESSING ===")
            print(f"Raw data keys: {list(data.keys())}")
            print(f"variants_data raw: {data.get('variants')}")
            print(f"variant_data raw: {data.get('variant')}")
            print(f"Type of variants_data: {type(data.get('variants'))}")
            
            # Handle variants array first (multiple variants)
            variants_data = data.get('variants')
            
            # Parse JSON string if variants comes from FormData
            if isinstance(variants_data, str):
                try:
                    variants_data = json.loads(variants_data)
                    print(f"✅ Successfully parsed variants_data from JSON string: {variants_data}")
                except (json.JSONDecodeError, ValueError) as e:
                    print(f"❌ Failed to parse variants_data as JSON: {e}")
                    print(f"Raw string was: {repr(variants_data)}")
                    variants_data = None
            elif isinstance(variants_data, list):
                print(f"✅ variants_data is already a list: {len(variants_data)} items")
            else:
                print(f"⚠️ variants_data is neither string nor list: {type(variants_data)}")
                print(f"Raw value: {repr(variants_data)}")
            
            # Create multiple variants if variants array is provided
            if isinstance(variants_data, list) and len(variants_data) > 0:
                print(f"🔄 Processing {len(variants_data)} variants from array")
                for i, variant_data in enumerate(variants_data):
                    print(f"\n--- Processing variant {i+1} ---")
                    print(f"Raw variant data: {variant_data}")
                    print(f"Variant data type: {type(variant_data)}")
                    
                    if isinstance(variant_data, dict):
                        variant_payload = variant_data.copy()
                        variant_payload['product'] = product.product_id
                        
                        # Normalize status field
                        if 'status' in variant_payload:
                            status_val = variant_payload.pop('status')
                            if isinstance(status_val, str):
                                try:
                                    status_val_bool = status_val.strip().lower() in ('1', 'true', 'yes')
                                except Exception:
                                    status_val_bool = False
                            else:
                                status_val_bool = bool(status_val)
                            variant_payload['is_active'] = status_val_bool
                        
                        # Handle size field
                        if 'size' in variant_payload:
                            size_raw = variant_payload['size']
                            if size_raw not in (None, '', 'null'):
                                if not isinstance(size_raw, dict):
                                    import json as _json
                                    try:
                                        size_parsed = _json.loads(size_raw) if isinstance(size_raw, str) and size_raw.strip().startswith('{') else {'value': str(size_raw)}
                                    except Exception:
                                        size_parsed = {'value': str(size_raw)}
                                    variant_payload['size'] = size_parsed
                            else:
                                variant_payload['size'] = None
                        
                        # Parse attributes JSON string
                        if 'attributes' in variant_payload and isinstance(variant_payload['attributes'], str):
                            try:
                                import json as _json
                                variant_payload['attributes'] = _json.loads(variant_payload['attributes'])
                            except Exception:
                                variant_payload['attributes'] = {'raw': variant_payload['attributes']}
                        
                        # Handle is_visible_counter
                        if 'is_visible_counter' in variant_payload:
                            ivc = variant_payload['is_visible_counter']
                            if isinstance(ivc, str):
                                variant_payload['is_visible_counter'] = ivc.strip().lower() in ('1', 'true', 'yes')
                            else:
                                variant_payload['is_visible_counter'] = bool(ivc) if ivc is not None else True
                        
                        print(f"Final payload for variant {i+1}: {variant_payload}")
                        variant_serializer = GroceriesProductVariantsSerializer(data=variant_payload)
                        print(f"Variant {i+1} serializer valid: {variant_serializer.is_valid()}")
                        
                        if not variant_serializer.is_valid():
                            print(f"❌ Variant {i+1} validation errors: {variant_serializer.errors}")
                            continue  # Skip to next variant instead of returning error
                        
                        try:
                            saved_variant = variant_serializer.save()
                            created_variants.append(saved_variant)
                            print(f"✅ Variant {i+1} created successfully: variant_id={saved_variant.variant_id}")
                        except Exception as e:
                            # Handle unique constraint on SKU by appending suffix
                            if 'unique' in str(e).lower() and 'sku' in str(e).lower():
                                print(f"⚠️ Variant {i+1} has duplicate SKU, attempting to auto-fix...")
                                base_sku = variant_payload.get('sku', '')
                                if not base_sku:
                                    # Generate a base SKU if none provided
                                    import re
                                    product_name = getattr(product, 'product_name', 'product')
                                    clean_name = re.sub(r'[^a-zA-Z0-9]', '', product_name).upper()[:12]
                                    base_sku = f"{clean_name}-VAR"
                                
                                suffix = 1
                                max_attempts = 100
                                while suffix <= max_attempts:
                                    candidate_sku = f"{base_sku}-{suffix}"
                                    variant_payload['sku'] = candidate_sku
                                    variant_serializer = GroceriesProductVariantsSerializer(data=variant_payload)
                                    if variant_serializer.is_valid():
                                        try:
                                            saved_variant = variant_serializer.save()
                                            created_variants.append(saved_variant)
                                            print(f"✅ Variant {i+1} saved with auto-fixed SKU: {candidate_sku}")
                                            break
                                        except Exception:
                                            suffix += 1
                                            continue
                                    else:
                                        suffix += 1
                                        continue
                                else:
                                    print(f"❌ Variant {i+1} failed: Could not generate unique SKU after {max_attempts} attempts")
                            else:
                                print(f"❌ Variant {i+1} database save failed: {e}")
                            continue  # Skip to next variant
                    else:
                        print(f"❌ Variant {i+1} is not a dict: {type(variant_data)}")
                
                print(f"\n=== VARIANT PROCESSING COMPLETE ===")
                print(f"Total variants created: {len(created_variants)}")
                if len(created_variants) == 0:
                    print("⚠️ No variants were created successfully")
                elif len(created_variants) < len(variants_data):
                    print(f"⚠️ Only {len(created_variants)} out of {len(variants_data)} variants were created")
            
            # Handle single variant (fallback)
            elif data.get('variant'):
                print("🔄 Processing single variant as fallback")
                variant_data = data.get('variant')
                
                # Parse JSON string if variant comes from FormData
                if isinstance(variant_data, str):
                    try:
                        variant_data = json.loads(variant_data)
                        print(f"✅ Parsed single variant from JSON: {variant_data}")
                    except (json.JSONDecodeError, ValueError):
                        print("❌ Failed to parse single variant as JSON")
                        variant_data = None
                
                if isinstance(variant_data, dict):
                    variant_payload = variant_data.copy()
                    variant_payload['product'] = product.product_id
                    
                    # Apply same field normalization as above...
                    if 'status' in variant_payload:
                        status_val = variant_payload.pop('status')
                        if isinstance(status_val, str):
                            try:
                                status_val_bool = status_val.strip().lower() in ('1', 'true', 'yes')
                            except Exception:
                                status_val_bool = False
                        else:
                            status_val_bool = bool(status_val)
                        variant_payload['is_active'] = status_val_bool
                    
                    if 'size' in variant_payload:
                        size_raw = variant_payload['size']
                        if size_raw not in (None, '', 'null'):
                            if not isinstance(size_raw, dict):
                                import json as _json
                                try:
                                    size_parsed = _json.loads(size_raw) if isinstance(size_raw, str) and size_raw.strip().startswith('{') else {'value': str(size_raw)}
                                except Exception:
                                    size_parsed = {'value': str(size_raw)}
                                variant_payload['size'] = size_parsed
                        else:
                            variant_payload['size'] = None
                    
                    if 'attributes' in variant_payload and isinstance(variant_payload['attributes'], str):
                        try:
                            import json as _json
                            variant_payload['attributes'] = _json.loads(variant_payload['attributes'])
                        except Exception:
                            variant_payload['attributes'] = {'raw': variant_payload['attributes']}
                    
                    if 'is_visible_counter' in variant_payload:
                        ivc = variant_payload['is_visible_counter']
                        if isinstance(ivc, str):
                            variant_payload['is_visible_counter'] = ivc.strip().lower() in ('1', 'true', 'yes')
                        else:
                            variant_payload['is_visible_counter'] = bool(ivc) if ivc is not None else True
                    
                    variant_serializer = GroceriesProductVariantsSerializer(data=variant_payload)
                    if variant_serializer.is_valid():
                        created_variant = variant_serializer.save()
                        created_variants.append(created_variant)
                        print(f"✅ Single variant created successfully: variant_id={created_variant.variant_id}")
                    else:
                        print(f"❌ Single variant validation failed: {variant_serializer.errors}")
                        return Response({
                            "message": "Product created, but variant invalid",
                            "product": GroceriesProductsSerializer(product, context={"request": request}).data,
                            "variant_errors": variant_serializer.errors
                        }, status=status.HTTP_201_CREATED)
                else:
                    print("❌ Single variant data is not a dict")
            else:
                print("ℹ️ No variant data found - checking for flattened fields...")
                # Accept flattened variant fields (existing logic)
                possible = [
                    'sku', 'barcode',
                    'net_weight', 'net_weight_unit', 'size',
                    'original_cost', 'selling_price', 'price_override', 'charges', 'gst',
                    'stock', 'mfg_date', 'expiry_date', 'is_active', 'status',
                    # Attribute columns
                    'color', 'gender', 'age', 'min_age', 'max_age', 'material', 'attributes', 'pack',
                    'is_visible_counter',
                ]
                if any(k in data for k in possible):
                    variant_payload = {k: data.get(k) for k in possible if k in data}
                    variant_payload['product'] = product.product_id
                    print(f"Found flattened fields: {variant_payload}")

                    if variant_payload:
                        if 'status' in variant_payload:
                            status_val = variant_payload.pop('status')
                            if isinstance(status_val, str):
                                try:
                                    status_val_bool = status_val.strip().lower() in ('1', 'true', 'yes')
                                except Exception:
                                    status_val_bool = False
                            else:
                                status_val_bool = bool(status_val)
                            variant_payload['is_active'] = status_val_bool
                        
                        if 'size' in variant_payload:
                            size_raw = variant_payload['size']
                            if size_raw not in (None, '', 'null'):
                                if not isinstance(size_raw, dict):
                                    import json as _json
                                    try:
                                        size_parsed = _json.loads(size_raw) if isinstance(size_raw, str) and size_raw.strip().startswith('{') else {'value': str(size_raw)}
                                    except Exception:
                                        size_parsed = {'value': str(size_raw)}
                                    variant_payload['size'] = size_parsed
                            else:
                                variant_payload['size'] = None
                        
                        if 'attributes' in variant_payload and isinstance(variant_payload['attributes'], str):
                            try:
                                import json as _json
                                variant_payload['attributes'] = _json.loads(variant_payload['attributes'])
                            except Exception:
                                variant_payload['attributes'] = {'raw': variant_payload['attributes']}
                        
                        if 'is_visible_counter' in variant_payload:
                            ivc = variant_payload['is_visible_counter']
                            if isinstance(ivc, str):
                                variant_payload['is_visible_counter'] = ivc.strip().lower() in ('1', 'true', 'yes')
                            else:
                                variant_payload['is_visible_counter'] = bool(ivc) if ivc is not None else True
                        
                        vp = variant_payload.copy()
                        vp['product'] = product.product_id
                        variant_serializer = GroceriesProductVariantsSerializer(data=vp)
                        if variant_serializer.is_valid():
                            created_variant = variant_serializer.save()
                            created_variants.append(created_variant)
                            print(f"✅ Flattened variant created successfully: variant_id={created_variant.variant_id}")
                        else:
                            print(f"❌ Flattened variant validation failed: {variant_serializer.errors}")
                            return Response({
                                "message": "Product created, but variant invalid",
                                "product": GroceriesProductsSerializer(product, context={"request": request}).data,
                                "variant_errors": variant_serializer.errors
                            }, status=status.HTTP_201_CREATED)

        if is_fashion_business:
            try:
                print("R08: Starting variant assembly")
                created_variants = []
                source_data = variant_source_data or {}
                
                # Handle variants array first (multiple variants)
                variants_data = source_data.get('variants')
                
                # Parse JSON string if variants comes from FormData
                if isinstance(variants_data, str):
                    try:
                        variants_data = json.loads(variants_data)
                        print(f"R08: parsed variants_data from JSON: {variants_data}")
                    except (json.JSONDecodeError, ValueError) as je:
                        print(f"R08: JSON decode failed: {je}")
                        variants_data = None
                
                # Create multiple variants if variants array is provided
                if isinstance(variants_data, list) and len(variants_data) > 0:
                    for variant_data in variants_data:
                        if isinstance(variant_data, dict):
                            variant_payload = variant_data.copy()
                            variant_payload['product'] = product.product_id
                            variant_payload['business_id'] = business.business_id
                            
                            # Normalize variant fields (same as your existing logic)
                            if 'status' in variant_payload and 'is_active' not in variant_payload:
                                variant_payload['is_active'] = variant_payload.pop('status')
                            
                            # Backward/forward compatibility for mfg date key
                            if 'mfg_data' in variant_payload and not variant_payload.get('mfg_date'):
                                variant_payload['mfg_date'] = variant_payload.pop('mfg_data')
                            
                            # Keep both stock and stock_qty in sync
                            if 'stock' in variant_payload and 'stock_qty' not in variant_payload:
                                variant_payload['stock_qty'] = variant_payload.get('stock')
                            if 'stock_qty' in variant_payload and 'stock' not in variant_payload:
                                variant_payload['stock'] = variant_payload.get('stock_qty')
                            
                            # Parse attributes JSON
                            if isinstance(variant_payload.get('attributes'), str):
                                try:
                                    variant_payload['attributes'] = json.loads(variant_payload.get('attributes'))
                                except Exception:
                                    pass
                            
                            # Filter allowed fields
                            allowed_variant_fields = {
                                'product', 'business_id', 'sku', 'barcode',
                                'selling_price', 'mrp', 'stock_qty',
                                'net_weight', 'net_weight_unit',
                                'original_cost', 'charges',
                                'stock', 'mfg_date', 'expiry_date',
                                'size', 'color', 'material', 'gender',
                                'attributes', 'is_active'
                            }
                            variant_payload = {k: variant_payload.get(k) for k in allowed_variant_fields if k in variant_payload}
                            
                            # Auto-generate SKU if missing
                            if not variant_payload.get('sku'):
                                import re
                                base_name = getattr(product, 'name', '') or ''
                                clean_name = re.sub(r'[^a-zA-Z0-9]', '', base_name).upper()[:12]
                                size_part = re.sub(r'[^a-zA-Z0-9]', '', str(variant_payload.get('size', ''))).upper()[:4]
                                color_part = re.sub(r'[^a-zA-Z0-9]', '', str(variant_payload.get('color', ''))).upper()[:4]
                                variant_payload['sku'] = f"{clean_name}{size_part}{color_part}{str(business.business_id)[-6:]}".strip()
                            
                            print(f"R08: Creating fashion variant with payload: {variant_payload}")
                            variant_serializer = FashionProductVariantSerializer(data=variant_payload)
                            if variant_serializer.is_valid():
                                try:
                                    saved_variant = variant_serializer.save()
                                    created_variants.append(saved_variant)
                                    print(f"R08: Fashion variant created successfully: {saved_variant.variant_id}")
                                except Exception as e:
                                    # Handle unique constraint on SKU
                                    if 'unique' in str(e).lower() and 'sku' in str(e).lower():
                                        base_sku = variant_payload.get('sku', '')
                                        suffix = 1
                                        while True:
                                            candidate_sku = f"{base_sku}-{suffix}"
                                            variant_payload['sku'] = candidate_sku
                                            variant_serializer = FashionProductVariantSerializer(data=variant_payload)
                                            if variant_serializer.is_valid():
                                                try:
                                                    saved_variant = variant_serializer.save()
                                                    created_variants.append(saved_variant)
                                                    print(f"R08: Fashion variant saved with new SKU {candidate_sku}: {saved_variant.variant_id}")
                                                    break
                                                except Exception:
                                                    suffix += 1
                                                    continue
                                            else:
                                                suffix += 1
                                                continue
                                    else:
                                        raise e
                            else:
                                print(f"R08: Fashion variant validation failed: {variant_serializer.errors}")
                                return Response({
                                    "message": "Product created, but some variants invalid",
                                    "product": FashionProductSerializer(product, context={"request": request}).data,
                                    "variant_errors": variant_serializer.errors
                                }, status=status.HTTP_201_CREATED)
                
                # Handle single variant (fallback or when variants toggle is OFF)
                elif source_data.get('variant'):
                    # Keep your existing single variant logic here
                    variant_payload = None
                    print(f"R08: source_data keys: {list(source_data.keys())}")
                    variant_data = source_data.get('variant')
                    print(f"R08: raw variant_data: {variant_data} (type: {type(variant_data)})")
                    if isinstance(variant_data, str):
                        try:
                            variant_data = json.loads(variant_data)
                            print(f"R08: parsed variant_data from JSON: {variant_data}")
                        except (json.JSONDecodeError, ValueError) as je:
                            print(f"R08: JSON decode failed: {je}")
                            variant_data = None
                    if isinstance(variant_data, dict):
                        variant_payload = dict(variant_data)
                        print(f"R08: using variant_data dict as payload: {variant_payload}")
                    else:
                        possible = [
                            'sku', 'barcode', 'selling_price', 'mrp',
                            'stock_qty', 'stock',
                            'net_weight', 'net_weight_unit',
                            'original_cost', 'charges',
                            'mfg_date', 'mfg_data', 'expiry_date',
                            'size', 'color', 'material', 'gender',
                            'attributes', 'is_active', 'status'
                        ]
                        if any(k in source_data for k in possible):
                            variant_payload = {k: source_data.get(k) for k in possible if k in source_data}
                            print(f"R08: built variant_payload from flattened fields: {variant_payload}")

                    if not variant_payload:
                        active_val = source_data.get('is_active', source_data.get('status', getattr(product, 'is_active', True)))
                        if isinstance(active_val, str):
                            active_bool = active_val.strip().lower() in ('1', 'true', 'yes', 'y', 'on')
                        else:
                            active_bool = bool(active_val)

                        variant_payload = {
                            'selling_price': source_data.get('selling_price') or getattr(product, 'base_price', None) or 0,
                            'stock_qty': source_data.get('stock_qty') or source_data.get('stock') or 0,
                            'stock': source_data.get('stock') or source_data.get('stock_qty') or 0,
                            'is_active': active_bool,
                        }
                        print(f"R08: auto-built default variant_payload: {variant_payload}")

                    if variant_payload:
                        print(f"R08: variant_payload before normalization: {variant_payload}")
                        if 'status' in variant_payload and 'is_active' not in variant_payload:
                            variant_payload['is_active'] = variant_payload.pop('status')
                            print("R08: mapped status -> is_active")

                        # Backward/forward compatibility for mfg date key
                        if 'mfg_data' in variant_payload and not variant_payload.get('mfg_date'):
                            variant_payload['mfg_date'] = variant_payload.pop('mfg_data')
                            print("R08: mapped mfg_data -> mfg_date")

                        # Keep both stock and stock_qty in sync when only one is provided
                        if 'stock' in variant_payload and 'stock_qty' not in variant_payload:
                            variant_payload['stock_qty'] = variant_payload.get('stock')
                            print("R08: synced stock -> stock_qty")
                        if 'stock_qty' in variant_payload and 'stock' not in variant_payload:
                            variant_payload['stock'] = variant_payload.get('stock_qty')
                            print("R08: synced stock_qty -> stock")

                        extra_attrs = {}
                        for k in [
                            'item_name', 'item_type', 'item_category',
                            'quantity', 'unit', 'weight',
                            'wallet_points_avaliablity', 'wallet_points_availablity', 'wallet_points',
                            'availability_timings',
                            'gst', 'gst_percentage'
                        ]:
                            if k in source_data and source_data.get(k) not in [None, '', 'null']:
                                extra_attrs[k] = source_data.get(k)
                        if extra_attrs:
                            print(f"R08: extra_attrs collected: {extra_attrs}")

                        if 'availability_timings' in extra_attrs and isinstance(extra_attrs.get('availability_timings'), str):
                            try:
                                extra_attrs['availability_timings'] = json.loads(extra_attrs.get('availability_timings'))
                                print("R08: parsed availability_timings JSON")
                            except (json.JSONDecodeError, ValueError, TypeError) as ex:
                                print(f"R08: failed to parse availability_timings JSON: {ex}")
                                return Response({
                                    "error": "Invalid JSON format in availability_timings",
                                    "details": {
                                        "availability_timings": [f"Value must be valid JSON. Parse error: {str(ex)}"]
                                    }
                                }, status=status.HTTP_400_BAD_REQUEST)
                        if isinstance(variant_payload.get('attributes'), str):
                            try:
                                variant_payload['attributes'] = json.loads(variant_payload.get('attributes'))
                                print("R08: parsed attributes JSON")
                            except Exception as ex:
                                print(f"R08: failed to parse attributes JSON: {ex}")
                                pass

                        attrs_val = variant_payload.get('attributes')
                        if not isinstance(attrs_val, dict):
                            attrs_val = {}
                        attrs_val.update(extra_attrs)
                        variant_payload['attributes'] = attrs_val
                        print(f"R08: final attributes: {attrs_val}")

                        vp = variant_payload.copy()
                        vp['product'] = product.product_id
                        vp['business_id'] = business.business_id
                        allowed_variant_fields = {
                            'product', 'business_id', 'sku', 'barcode',
                            'selling_price', 'mrp', 'stock_qty',
                            'net_weight', 'net_weight_unit',
                            'original_cost', 'charges',
                            'stock', 'mfg_date', 'expiry_date',
                            'size', 'color', 'material', 'gender',
                            'attributes', 'is_active'
                        }
                        vp = {k: vp.get(k) for k in allowed_variant_fields if k in vp}
                        # Auto-generate SKU if missing to avoid hard failures
                        if not vp.get('sku'):
                            import re
                            base_name = getattr(product, 'name', '') or ''
                            clean_name = re.sub(r'[^a-zA-Z0-9]', '', base_name).upper()[:12]
                            size_part = re.sub(r'[^a-zA-Z0-9]', '', str(vp.get('size', ''))).upper()[:4]
                            color_part = re.sub(r'[^a-zA-Z0-9]', '', str(vp.get('color', ''))).upper()[:4]
                            vp['sku'] = f"{clean_name}{size_part}{color_part}{str(business.business_id)[-6:]}".strip()
                            print(f"R08: auto-generated SKU: {vp['sku']}")
                        print(f"R08: filtered vp for serializer: {vp}")
                        variant_serializer = FashionProductVariantSerializer(data=vp)
                        print(f"R08: variant_serializer created, is_valid: {variant_serializer.is_valid()}")
                        if not variant_serializer.is_valid():
                            print(f"R08: variant_serializer errors: {variant_serializer.errors}")
                        if variant_serializer.is_valid():
                            try:
                                created_variant = variant_serializer.save()
                                created_variants.append(created_variant)
                                print(f"R08: variant saved successfully: {created_variant.variant_id}")
                            except Exception as e:
                                # Handle unique constraint on (business_id, sku) by appending suffix
                                if 'unique' in str(e).lower() and 'sku' in str(e).lower():
                                    base_sku = vp.get('sku', '')
                                    suffix = 1
                                    while True:
                                        candidate_sku = f"{base_sku}-{suffix}"
                                        vp['sku'] = candidate_sku
                                        variant_serializer = FashionProductVariantSerializer(data=vp)
                                        if variant_serializer.is_valid():
                                            try:
                                                created_variant = variant_serializer.save()
                                                created_variants.append(created_variant)
                                                print(f"R08: variant saved successfully with new SKU {candidate_sku}: {created_variant.variant_id}")
                                                break
                                            except Exception:
                                                suffix += 1
                                                continue
                                        else:
                                            suffix += 1
                                            continue
                                    print(f"R08: auto-fixed duplicate SKU to {candidate_sku}")
                                else:
                                    raise e

                            try:
                                # Always set newest variant as default variant pointer
                                product.variant_id = created_variant.variant_id
                                product.save(update_fields=['variant_id'])
                                print(f"R08: product.variant_id updated to newest variant {created_variant.variant_id}")
                            except Exception as ve:
                                print(f"R08: failed to update product.variant_id: {ve}")
                            except Exception as e:
                                print(f"R08: variant_serializer.save() exception: {e}")
                                payload = {
                                    "error": "Failed to create fashion variant",
                                    "details": str(e),
                                    "variant_payload": vp,
                                    "product_id": getattr(product, 'product_id', None)
                                }
                                if getattr(settings, 'DEBUG', False):
                                    payload["trace"] = traceback.format_exc()
                                return Response(payload, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
                        else:
                            product_data = FashionProductSerializer(product, context={"request": request}).data
                            # If product has no base_price, set it from first variant's selling_price if available
                            if not product_data.get("base_price") and 'created_variants' in locals() and created_variants:
                                try:
                                    product_data["base_price"] = str(created_variants[0].selling_price)
                                except Exception:
                                    pass
                            return Response({
                                "message": "Product created, but variant invalid",
                                "product": product_data,
                                "variant_errors": variant_serializer.errors
                            }, status=status.HTTP_201_CREATED)
                    else:
                        print("R08: No variant_payload built; skipping variant creation")
                        
                        # If no variants and no base_price, set base_price to 0 or from selling_price if provided
                        product_data = FashionProductSerializer(product, context={"request": request}).data
                        if not product_data.get("base_price"):
                            # Try to get selling_price from the product data if it was provided
                            selling_price = getattr(product, 'selling_price', None) or data.get('selling_price')
                            if selling_price:
                                product_data["base_price"] = str(selling_price)
                            else:
                                product_data["base_price"] = "0.00"
                
                # Set newest variant as default variant pointer for fashion business
                if created_variants:
                    try:
                        product.variant_id = created_variants[-1].variant_id
                        product.save(update_fields=['variant_id'])
                        print(f"R08: product.variant_id updated to newest variant {created_variants[-1].variant_id}")
                    except Exception as ve:
                        print(f"R08: failed to update product.variant_id: {ve}")
                        
            except Exception as e:
                print(f"R08: Top-level exception in variant assembly: {e}")
                payload = {
                    "error": "Failed to assemble fashion variant payload",
                    "details": str(e),
                    "source_data_keys": list(variant_source_data.keys()) if variant_source_data else [],
                }
                if getattr(settings, 'DEBUG', False):
                    payload["trace"] = traceback.format_exc()
                return Response(payload, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        # Prepare response based on product type
        if is_grocery_business:
            product_data = GroceriesProductsSerializer(product, context={"request": request}).data
            product_id_field = "product_id"
            product_id_value = product.product_id
        elif is_fashion_business:
            product_data = FashionProductSerializer(product, context={"request": request}).data
            product_id_field = "product_id"
            product_id_value = product.product_id
            
            # If product has no base_price, set it from first variant's selling_price
            if not product_data.get("base_price") and 'created_variants' in locals() and created_variants:
                try:
                    product_data["base_price"] = str(created_variants[0].selling_price)
                except Exception:
                    pass
        else:
            product_data = productItemsSerializer(product, context={"request": request}).data
            product_id_field = "item_id"
            product_id_value = product.item_id
            
            # Add base_price as selling_price for regular product items if not present
            if not product_data.get("base_price") and product_data.get("selling_price"):
                product_data["base_price"] = product_data["selling_price"]

        response = {
            "message": "Product item added successfully",
            product_id_field: product_id_value,
            "product": product_data
        }
        
        # Handle variants in response
        if 'created_variants' in locals() and created_variants:
            if len(created_variants) == 1:
                # Single variant
                if is_grocery_business:
                    response["variant"] = GroceriesProductVariantsSerializer(created_variants[0]).data
                elif is_fashion_business:
                    response["variant"] = FashionProductVariantSerializer(created_variants[0]).data
            else:
                # Multiple variants
                if is_grocery_business:
                    response["variant"] = GroceriesProductVariantsSerializer(created_variants[0]).data  # First variant as main
                    response["variants"] = GroceriesProductVariantsSerializer(created_variants, many=True).data
                elif is_fashion_business:
                    response["variant"] = FashionProductVariantSerializer(created_variants[0]).data  # First variant as main
                    response["variants"] = FashionProductVariantSerializer(created_variants, many=True).data
            
            # Always include variants array for consistency
            if is_grocery_business:
                response["variants"] = GroceriesProductVariantsSerializer(created_variants, many=True).data
            elif is_fashion_business:
                response["variants"] = FashionProductVariantSerializer(created_variants, many=True).data
        elif 'created_variant' in locals() and created_variant:
            if is_grocery_business:
                response["variant"] = GroceriesProductVariantsSerializer(created_variant).data
                response["variants"] = GroceriesProductVariantsSerializer([created_variant], many=True).data
            elif is_fashion_business:
                response["variant"] = FashionProductVariantSerializer(created_variant).data
                response["variants"] = FashionProductVariantSerializer([created_variant], many=True).data

        return Response(response, status=status.HTTP_201_CREATED)

@swagger_auto_schema(methods=['POST'], tags=['Business'])
@api_view(['POST'])
@parser_classes([MultiPartParser, FormParser])
def bulk_upload_grocery_products(request):
    """Bulk upload grocery products, categories, and variants from a CSV file.

    This is a business-owner-facing wrapper around the consumer GroceriesBulkUploadView.

    Query params:
      - userID or user_id (required)
      - business_id (required)

    Body (multipart/form-data):
      - file: CSV, same format as /consumer/groceries-bulk-upload/:
          category_name, parent_category_name, gst_rate,
          product_name, brand_name, sub_category, description, main_image, is_organic, rating,
          sku, net_weight, net_weight_unit, size, original_cost, selling_price, charges,
          stock, mfg_date, expiry_date, is_active

      - Optional flags (in body): dry_run, all_or_nothing, update_existing, create_missing_categories, encoding
    """

    user_id = request.query_params.get('userID') or request.query_params.get('user_id')
    business_id = request.query_params.get('business_id')

    if not user_id or not business_id:
        return Response({"error": "userID/user_id and business_id are required"}, status=status.HTTP_400_BAD_REQUEST)

    # Validate user exists and is active
    try:
        user = Registration.objects.get(user_id=user_id, status=True)
    except Registration.DoesNotExist:
        return Response({"error": "Invalid user_id"}, status=status.HTTP_404_NOT_FOUND)

    # Validate business exists and is active
    try:
        business = Business.objects.get(business_id=business_id, status=True)
    except Business.DoesNotExist:
        return Response({"error": "Invalid business_id"}, status=status.HTTP_404_NOT_FOUND)

    # Only allow for grocery businesses (R01). Other types can still use addProductItems.
    if (business.businessType or '').strip().upper() != 'R01':
        return Response({"error": "Bulk grocery upload is only supported for R01 (grocery) businesses"}, status=status.HTTP_400_BAD_REQUEST)

    # Check if user is a POS/KOT counter user for this business
    is_pos_user = False
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT role FROM business_role_management
            WHERE assigned_to = %s AND business_id = %s AND status = 1
            """,
            [user_id, business_id]
        )
        row = cursor.fetchone()
        if row and row[0] and row[0].upper() in ['POS', 'KOT', 'COUNTER']:
            is_pos_user = True

    # For non-POS users, enforce BusinessMapping
    if not is_pos_user:
        if not BusinessMapping.objects.filter(user__user_id=user_id, business=business, status=True).exists():
            return Response({"error": "User does not have access to this business"}, status=status.HTTP_403_FORBIDDEN)

    # Ensure a file was uploaded
    upload = request.FILES.get('file') or request.FILES.get('csv') or request.FILES.get('data')
    if not upload:
        return Response({"error": "CSV file is required (field name 'file')"}, status=status.HTTP_400_BAD_REQUEST)

    # Delegate CSV parsing and DB operations to the existing consumer bulk upload view
    # That view already validates business_id and file/flags.
    underlying_view = GroceriesBulkUploadView()
    return underlying_view.post(request)


def _get_menu_details_logic(request, menu_id):
    try:
        menu_item = MenuItems.objects.get(item_id=menu_id)
    except MenuItems.DoesNotExist:
        return Response({"error": "Menu item not found or inactive"}, status=status.HTTP_404_NOT_FOUND)
    
    menu_serializer = MenuItemsSerializer(menu_item, context={"request": request})
    bom_items = BOM.objects.filter(product_id=menu_id)
    bom_serializer = BOMSerializer(bom_items, many=True)
    
    return Response({
        "menu_details": menu_serializer.data,
        "BOM_details": bom_serializer.data
    }, status=status.HTTP_200_OK)

def _get_product_details_logic(request, product_id):
    # Try new GroceriesProducts first (R01 with variants)
    try:
        product = GroceriesProducts.objects.prefetch_related('groceriesproductvariants_set').get(product_id=product_id)
        serializer = GroceriesProductWithPricingSerializer(product, context={"request": request})
        
        # Fetch custom designs
        custom_designs = GroceriesCustomDesigns.objects.filter(product_id=product_id, is_active=True).order_by('position')
        design_serializer = GroceriesCustomDesignsSerializer(custom_designs, many=True, context={"request": request})

        # Note: BOM is usually for MenuItems, but checking for it here as well
        bom_items = BOM.objects.filter(product_id=product_id)
        bom_serializer = BOMSerializer(bom_items, many=True)
        return Response({
            "product_details": serializer.data,
            "BOM_details": bom_serializer.data,
            "custom_designs": design_serializer.data
        }, status=status.HTTP_200_OK)
    except GroceriesProducts.DoesNotExist:
        # Fallback to legacy productItems (GroceryItems table)
        try:
            product_item = productItems.objects.get(item_id=product_id)
        except productItems.DoesNotExist:
            return Response({"error": "Product item not found"}, status=status.HTTP_404_NOT_FOUND)
        
        product_serializer = productItemsSerializer(product_item, context={"request": request})
        bom_items = BOM.objects.filter(product_id=product_id)
        bom_serializer = BOMSerializer(bom_items, many=True)
        
        return Response({
            "product_details": product_serializer.data,
            "BOM_details": bom_serializer.data
        }, status=status.HTTP_200_OK)

def _get_fashion_details_logic(request, product_id):
    try:
        product = FashionProduct.objects.prefetch_related('variants').get(product_id=product_id)
        serializer = FashionProductWithVariantsSerializer(product, context={"request": request})
        
        # Fetch custom designs
        custom_designs = GroceriesCustomDesigns.objects.filter(product_id=product_id, is_active=True).order_by('position')
        design_serializer = GroceriesCustomDesignsSerializer(custom_designs, many=True, context={"request": request})

        return Response({
            "product_details": serializer.data,
            "custom_designs": design_serializer.data
        }, status=status.HTTP_200_OK)
    except FashionProduct.DoesNotExist:
        return Response({"error": f"Fashion product {product_id} not found"}, status=status.HTTP_404_NOT_FOUND)
    except Exception as e:
        return Response({"error": f"Fashion product error: {str(e)}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

@swagger_auto_schema(methods=['POST'], tags=['Business'])
@api_view(['POST'])
def menuDetailView(request):
    if request.method == 'POST':
        menu_id = request.query_params.get("menu_id")
        if not menu_id:
            return Response({"error": "menu_id is required"}, status=status.HTTP_400_BAD_REQUEST)
        return _get_menu_details_logic(request, menu_id)

@swagger_auto_schema(methods=['POST'], tags=['Business'])
@api_view(['POST'])
def productDetailView(request):
    if request.method == 'POST':
        product_id = request.query_params.get("product_id")
        if not product_id:
            return Response({"error": "product_id is required"}, status=status.HTTP_400_BAD_REQUEST)
        return _get_product_details_logic(request, product_id)

@swagger_auto_schema(methods=['POST'], tags=['Business'])
@api_view(['POST'])
def fashionDetailView(request):
    if request.method == 'POST':
        product_id = request.query_params.get("product_id")
        if not product_id:
            return Response({"error": "product_id is required"}, status=status.HTTP_400_BAD_REQUEST)
        return _get_fashion_details_logic(request, product_id)

@swagger_auto_schema(methods=['POST'], tags=['Business'])
@api_view(['POST'])
def getItemDetails(request):
    """
    Unified dispatcher to fetch item details based on type.
    Query params: item_id, type (menu/product/fashion)
    """
    item_id = request.query_params.get("item_id")
    item_type = request.query_params.get("type", "").lower()

    if not item_id or not item_type:
        return Response({"error": "Both item_id and type are required"}, status=status.HTTP_400_BAD_REQUEST)

    if item_type == 'menu':
        return _get_menu_details_logic(request, item_id)
    elif item_type == 'product':
        return _get_product_details_logic(request, item_id)
    elif item_type == 'fashion':
        return _get_fashion_details_logic(request, item_id)
    else:
        return Response({"error": f"Invalid type '{item_type}'. Must be menu, product, or fashion."}, status=status.HTTP_400_BAD_REQUEST)


def _check_user_permissions(user_id, business_id):
    """
    Check if user has permission to access the business.
    Returns: (is_pos_user, allowed_business_ids)
    """
    is_pos_user = False
    allowed_business_ids = set()
    
    with connection.cursor() as cursor:
        # Check if user is POS/KOT/COUNTER for the specific business
        cursor.execute(
            """
            SELECT role, business_id FROM business_role_management
            WHERE assigned_to = %s 
              AND business_id COLLATE utf8mb4_0900_ai_ci = CAST(%s AS CHAR) COLLATE utf8mb4_0900_ai_ci 
              AND status = 1
            """,
            [user_id, business_id]
        )
        row = cursor.fetchone()
        
        if row and row[0] and row[0].upper() in ['POS', 'KOT', 'COUNTER']:
            is_pos_user = True
            allowed_business_ids.add(business_id)
        else:
            # Check if user is POS for a master business that has this business as a child
            cursor.execute(
                """
                SELECT brm.role, brm.business_id 
                FROM business_role_management brm
                INNER JOIN businesses b ON b.business_id COLLATE utf8mb4_0900_ai_ci = brm.business_id COLLATE utf8mb4_0900_ai_ci
                WHERE brm.assigned_to = %s 
                  AND brm.status = 1 
                  AND b.level = 'master'
                  AND b.status = 1
                  AND EXISTS (
                      SELECT 1 FROM businesses child 
                      WHERE child.master COLLATE utf8mb4_0900_ai_ci = brm.business_id COLLATE utf8mb4_0900_ai_ci 
                      AND child.business_id COLLATE utf8mb4_0900_ai_ci = %s 
                      AND child.status = 1
                  )
                """,
                [user_id, business_id]
            )
            master_row = cursor.fetchone()
            
            if master_row and master_row[0] and master_row[0].upper() in ['POS', 'KOT', 'COUNTER']:
                is_pos_user = True
                pos_master_business_id = master_row[1]
                allowed_business_ids.add(pos_master_business_id)
                
                # Get all child businesses
                cursor.execute(
                    """
                    SELECT business_id FROM businesses 
                    WHERE master COLLATE utf8mb4_0900_ai_ci = CAST(%s AS CHAR) COLLATE utf8mb4_0900_ai_ci 
                      AND status = 1
                    """,
                    [pos_master_business_id]
                )
                child_businesses = cursor.fetchall()
                for child in child_businesses:
                    allowed_business_ids.add(child[0])
    
    return is_pos_user, allowed_business_ids


def _validate_product_access(product_item, grocery_product, is_grocery, business_id, is_pos_user, allowed_business_ids):
    """
    Validate if user has access to the product.
    Returns: (is_valid, error_response)
    """
    if is_grocery:
        product_business_id = str(grocery_product.business.business_id)
        
        if is_pos_user:
            allowed_ids_str = {str(bid) for bid in allowed_business_ids}
            if product_business_id not in allowed_ids_str:
                return False, Response({
                    "error": "Grocery product doesn't belong to an allowed business",
                    "product_business_id": product_business_id,
                    "allowed_business_ids": list(allowed_ids_str)
                }, status=status.HTTP_403_FORBIDDEN)
        else:
            if product_business_id != str(business_id):
                return False, Response({
                    "error": "Grocery product doesn't belong to this business",
                    "product_business_id": product_business_id,
                    "requested_business_id": str(business_id)
                }, status=status.HTTP_403_FORBIDDEN)
    else:
        if not product_item.status:
            return False, Response({"error": "Product item is already deleted"}, status=status.HTTP_410_GONE)
        
        item_business_id = str(product_item.business_id.business_id)
        
        if is_pos_user:
            allowed_ids_str = {str(bid) for bid in allowed_business_ids}
            if item_business_id not in allowed_ids_str:
                return False, Response({
                    "error": "Product item doesn't belong to an allowed business",
                    "item_business_id": item_business_id,
                    "allowed_business_ids": list(allowed_ids_str)
                }, status=status.HTTP_403_FORBIDDEN)
        else:
            if item_business_id != str(business_id):
                return False, Response({
                    "error": "Product item doesn't belong to this business",
                    "item_business_id": item_business_id,
                    "requested_business_id": str(business_id)
                }, status=status.HTTP_403_FORBIDDEN)
    
    return True, None


def _update_grocery_variant(variant_data, product):
    """
    Update or create grocery product variant using raw SQL to avoid collation issues.
    Returns: (success, variant_response_or_error)
    """
    if not variant_data or not isinstance(variant_data, dict):
        return True, None
    
    from django.db import connection
    
    print(f"[VARIANT UPDATE] Product ID: {product.product_id}, Business: {product.business.business_id}")
    print(f"[VARIANT UPDATE] Variant data received: {variant_data}")
    
    # If frontend supplies a specific variant_id, target it directly.
    # Otherwise fall back to the first variant for this product.
    requested_variant_id = variant_data.get('variant_id')

    with connection.cursor() as cursor:
        if requested_variant_id:
            cursor.execute("""
                SELECT variant_id FROM Groceries_ProductVariants_1
                WHERE variant_id = %s AND product_id = %s
                LIMIT 1
            """, [requested_variant_id, product.product_id])
        else:
            cursor.execute("""
                SELECT variant_id FROM Groceries_ProductVariants_1
                WHERE product_id = %s
                LIMIT 1
            """, [product.product_id])
        variant_row = cursor.fetchone()

    if not variant_row:
        print(f"[VARIANT UPDATE] No existing variant found (requested_variant_id={requested_variant_id}), will create new one")
        existing_variant = None
        variant_id = None
    else:
        variant_id = variant_row[0]
        print(f"[VARIANT UPDATE] Found existing variant_id: {variant_id}")
        existing_variant = type('obj', (object,), {'variant_id': variant_id})()
    
    # Map field names
    if 'status' in variant_data:
        variant_data['is_active'] = variant_data.pop('status')
    
    # Remove fields that shouldn't be updated
    fields_to_remove = ['product', 'variant_id', 'created_at']
    for field in fields_to_remove:
        variant_data.pop(field, None)
    
    # Remove null/empty date fields
    if 'mfg_date' in variant_data and variant_data['mfg_date'] in [None, '', 'null']:
        variant_data.pop('mfg_date', None)
    if 'expiry_date' in variant_data and variant_data['expiry_date'] in [None, '', 'null']:
        variant_data.pop('expiry_date', None)
    
    # Convert empty strings to None for numeric fields to avoid SQL issues
    numeric_fields = ['original_cost', 'selling_price', 'charges', 'gst', 'stock', 'net_weight']
    for field in numeric_fields:
        if field in variant_data and variant_data[field] == '':
            variant_data[field] = None
    
    try:
        if existing_variant:
            # Use raw SQL UPDATE to bypass ORM collation issues
            # Only update numeric and boolean fields
            update_fields = []
            update_values = []
            
            if 'sku' in variant_data:
                update_fields.append('sku = %s')
                update_values.append(variant_data['sku'])
            
            if 'original_cost' in variant_data:
                update_fields.append('original_cost = %s')
                update_values.append(variant_data['original_cost'])
            
            if 'selling_price' in variant_data:
                update_fields.append('selling_price = %s')
                update_values.append(variant_data['selling_price'])
            
            if 'charges' in variant_data:
                update_fields.append('charges = %s')
                update_values.append(variant_data['charges'])
            
            if 'gst' in variant_data:
                update_fields.append('gst = %s')
                update_values.append(variant_data['gst'])
            
            if 'stock' in variant_data:
                update_fields.append('stock = %s')
                update_values.append(variant_data['stock'])
            
            if 'is_active' in variant_data:
                update_fields.append('is_active = %s')
                update_values.append(1 if variant_data['is_active'] else 0)
            
            if 'net_weight' in variant_data:
                update_fields.append('net_weight = %s')
                update_values.append(variant_data['net_weight'])

            # size is a JSON column — accept dict or wrap plain string
            if 'size' in variant_data:
                sz = variant_data['size']
                if sz not in (None, '', 'null'):
                    if not isinstance(sz, dict):
                        import json as _json
                        try:
                            sz = _json.loads(sz) if isinstance(sz, str) and sz.strip().startswith('{') else {'value': str(sz)}
                        except Exception:
                            sz = {'value': str(sz)}
                    import json as _json
                    update_fields.append('size = %s')
                    update_values.append(_json.dumps(sz))
                else:
                    update_fields.append('size = NULL')

            if 'net_weight_unit' in variant_data and variant_data['net_weight_unit']:
                update_fields.append('net_weight_unit = %s')
                update_values.append(variant_data['net_weight_unit'])

            if 'barcode' in variant_data:
                update_fields.append('barcode = %s')
                update_values.append(variant_data['barcode'])

            if 'color' in variant_data:
                update_fields.append('color = %s')
                update_values.append(variant_data['color'])

            if 'gender' in variant_data:
                update_fields.append('gender = %s')
                update_values.append(variant_data['gender'])

            if 'age' in variant_data:
                update_fields.append('age = %s')
                update_values.append(variant_data['age'])

            if 'material' in variant_data:
                update_fields.append('material = %s')
                update_values.append(variant_data['material'])

            if 'attributes' in variant_data:
                import json as _json
                attrs = variant_data['attributes']
                if isinstance(attrs, dict):
                    update_fields.append('attributes = %s')
                    update_values.append(_json.dumps(attrs))
                elif attrs is None:
                    update_fields.append('attributes = NULL')

            if 'dimension' in variant_data:
                import json as _json
                dim = variant_data['dimension']
                if isinstance(dim, dict):
                    update_fields.append('dimension = %s')
                    update_values.append(_json.dumps(dim))
                elif dim is None:
                    update_fields.append('dimension = NULL')

            if 'pack' in variant_data:
                update_fields.append('pack = %s')
                update_values.append(variant_data['pack'])

            if 'is_visible_counter' in variant_data:
                ivc = variant_data['is_visible_counter']
                if isinstance(ivc, str):
                    ivc = ivc.strip().lower() in ('1', 'true', 'yes', 'y')
                update_fields.append('is_visible_counter = %s')
                update_values.append(1 if ivc else 0)

            if 'price_override' in variant_data:
                po = variant_data['price_override']
                if po in (None, '', 'null', 'NULL'):
                    update_fields.append('price_override = NULL')
                else:
                    try:
                        update_fields.append('price_override = %s')
                        update_values.append(float(po))
                    except (ValueError, TypeError):
                        pass

            if 'min_age' in variant_data and variant_data['min_age'] not in (None, '', 'null'):
                try:
                    update_fields.append('min_age = %s')
                    update_values.append(int(variant_data['min_age']))
                except (ValueError, TypeError):
                    pass

            if 'max_age' in variant_data and variant_data['max_age'] not in (None, '', 'null'):
                try:
                    update_fields.append('max_age = %s')
                    update_values.append(int(variant_data['max_age']))
                except (ValueError, TypeError):
                    pass

            if 'mfg_date' in variant_data and variant_data['mfg_date'] not in (None, '', 'null'):
                update_fields.append('mfg_date = %s')
                update_values.append(variant_data['mfg_date'])

            if 'expiry_date' in variant_data and variant_data['expiry_date'] not in (None, '', 'null'):
                update_fields.append('expiry_date = %s')
                update_values.append(variant_data['expiry_date'])

            if update_fields:
                update_values.append(existing_variant.variant_id)
                
                with connection.cursor() as cursor:
                    sql = f"""
                        UPDATE Groceries_ProductVariants_1 
                        SET {', '.join(update_fields)}
                        WHERE variant_id = %s
                    """
                    cursor.execute(sql, update_values)
                
                # Fetch updated variant using all columns
                with connection.cursor() as cursor:
                    cursor.execute("""
                        SELECT variant_id, product_id, sku, barcode,
                               net_weight, net_weight_unit,
                               size, original_cost, selling_price, charges, gst, stock,
                               mfg_date, expiry_date, is_active, created_at, updated_at,
                               color, gender, age, material, attributes, pack,
                               is_visible_counter, price_override, min_age, max_age
                        FROM Groceries_ProductVariants_1
                        WHERE variant_id = %s
                    """, [existing_variant.variant_id])
                    row = cursor.fetchone()

                    if row:
                        import json as _json
                        # Get sub_category_id from the product (lives on Groceries_Products, not the variant)
                        # row[1] is product_id; use the `product` arg if available, else do a quick lookup
                        _sub_cat_id = None
                        try:
                            if product and hasattr(product, 'sub_category_id'):
                                _sub_cat_id = product.sub_category_id
                            else:
                                _prod_id = row[1]
                                _prod = GroceriesProducts.objects.filter(product_id=_prod_id).values('sub_category_id').first()
                                _sub_cat_id = _prod['sub_category_id'] if _prod else None
                        except Exception:
                            _sub_cat_id = None
                        # Resolve base_price from product
                        try:
                            if product and hasattr(product, 'base_price'):
                                _base_price = float(product.base_price) if product.base_price is not None else 0.0
                            else:
                                _prod_id = row[1]
                                _prod = GroceriesProducts.objects.filter(product_id=_prod_id).values('base_price', 'sub_category_id').first()
                                _base_price = float(_prod['base_price']) if _prod and _prod['base_price'] is not None else 0.0
                                if not product:
                                    _sub_cat_id = _prod['sub_category_id'] if _prod else None
                        except Exception:
                            _base_price = 0.0
                        variant_dict = {
                            'variant_id': row[0],
                            'product': row[1],
                            'sku': row[2],
                            'barcode': row[3],
                            'net_weight': row[4],
                            'net_weight_unit': row[5],
                            'size': _json.loads(row[6]) if row[6] and isinstance(row[6], str) else row[6],
                            'original_cost': str(row[7]) if row[7] else None,
                            'selling_price': str(row[8]) if row[8] else None,
                            'charges': str(row[9]) if row[9] else None,
                            'gst': str(row[10]) if row[10] else '0.00',
                            'stock': row[11],
                            'mfg_date': row[12],
                            'expiry_date': row[13],
                            'is_active': bool(row[14]),
                            'created_at': row[15],
                            'updated_at': row[16],
                            'color': row[17],
                            'gender': row[18],
                            'age': row[19],
                            'material': row[20],
                            'attributes': _json.loads(row[21]) if row[21] and isinstance(row[21], str) else row[21],
                            'pack': row[22],
                            'is_visible_counter': bool(row[23]),
                            'price_override': float(row[24]) if row[24] is not None else None,
                            'min_age': row[25],
                            'max_age': row[26],
                            'sub_category_id': _sub_cat_id,
                        }
                        return True, variant_dict
                    else:
                        return True, {}
            else:
                # No fields to update
                return True, {}
        else:
            # Create new variant using raw SQL INSERT
            print(f"[VARIANT UPDATE] Creating new variant for product {product.product_id}")

            # Generate SKU if not provided
            if 'sku' not in variant_data or not variant_data.get('sku'):
                import re
                product_name = product.product_name
                clean_name = re.sub(r'[^a-zA-Z0-9\s]', '', product_name)
                clean_name = clean_name.lower().replace(' ', '')

                if variant_data.get('net_weight') and variant_data.get('net_weight_unit'):
                    sku = f"{clean_name}_{variant_data['net_weight']}{variant_data['net_weight_unit']}"
                elif variant_data.get('size'):
                    # size may be JSON dict or plain string
                    sz = variant_data['size']
                    if isinstance(sz, dict):
                        size_str = sz.get('value') or '_'.join(str(v) for v in sz.values() if v)
                    else:
                        size_str = str(sz)
                    clean_size = re.sub(r'[^a-zA-Z0-9]', '', size_str.lower())
                    sku = f"{clean_name}_{clean_size}" if clean_size else clean_name
                elif variant_data.get('color'):
                    color_part = re.sub(r'[^a-zA-Z0-9]', '', str(variant_data['color']).lower())
                    sku = f"{clean_name}_{color_part}" if color_part else clean_name
                else:
                    sku = clean_name

                # Ensure uniqueness
                base_sku = sku
                counter = 1
                with connection.cursor() as cursor:
                    while True:
                        cursor.execute("SELECT COUNT(*) FROM Groceries_ProductVariants_1 WHERE sku = %s", [sku])
                        if cursor.fetchone()[0] == 0:
                            break
                        sku = f"{base_sku}_{counter}"
                        counter += 1

                variant_data['sku'] = sku

            # Build INSERT query
            insert_fields = ['product_id', 'sku']
            insert_values = [product.product_id, variant_data['sku']]
            
            field_mapping = {
                'net_weight': 'net_weight',
                'net_weight_unit': 'net_weight_unit',
                'original_cost': 'original_cost',
                'selling_price': 'selling_price',
                'charges': 'charges',
                'gst': 'gst',
                'stock': 'stock',
                'mfg_date': 'mfg_date',
                'expiry_date': 'expiry_date',
                'is_active': 'is_active',
                # New attribute columns
                'barcode': 'barcode',
                'color': 'color',
                'gender': 'gender',
                'age': 'age',
                'material': 'material',
                'pack': 'pack',
                'is_visible_counter': 'is_visible_counter',
            }

            import json as _json

            # Handle size separately (JSON column)
            if 'size' in variant_data and variant_data['size'] not in (None, '', 'null'):
                sz = variant_data['size']
                if not isinstance(sz, dict):
                    try:
                        sz = _json.loads(sz) if isinstance(sz, str) and sz.strip().startswith('{') else {'value': str(sz)}
                    except Exception:
                        sz = {'value': str(sz)}
                insert_fields.append('size')
                insert_values.append(_json.dumps(sz))

            # Handle attributes (JSON column)
            if 'attributes' in variant_data and variant_data['attributes'] is not None:
                attrs = variant_data['attributes']
                if isinstance(attrs, dict):
                    insert_fields.append('attributes')
                    insert_values.append(_json.dumps(attrs))

            
            for key, db_field in field_mapping.items():
                if key in variant_data and variant_data[key] is not None:
                    insert_fields.append(db_field)
                    insert_values.append(variant_data[key])
            
            placeholders = ', '.join(['%s'] * len(insert_values))
            fields_str = ', '.join(insert_fields)
            
            with connection.cursor() as cursor:
                sql = f"""
                    INSERT INTO Groceries_ProductVariants_1 ({fields_str})
                    VALUES ({placeholders})
                """
                cursor.execute(sql, insert_values)
                new_variant_id = cursor.lastrowid
            
            # Fetch the created variant
            with connection.cursor() as cursor:
                cursor.execute("""
                    SELECT variant_id, product_id, sku, barcode,
                           net_weight, net_weight_unit,
                           size, original_cost, selling_price, charges, gst, stock,
                           mfg_date, expiry_date, is_active, created_at, updated_at,
                           color, gender, age, material, attributes, pack,
                           is_visible_counter, price_override, min_age, max_age
                    FROM Groceries_ProductVariants_1
                    WHERE variant_id = %s
                """, [new_variant_id])
                row = cursor.fetchone()

                if row:
                    import json as _json
                    variant_dict = {
                        'variant_id': row[0],
                        'product': row[1],
                        'sku': row[2],
                        'barcode': row[3],
                        'net_weight': row[4],
                        'net_weight_unit': row[5],
                        'size': _json.loads(row[6]) if row[6] and isinstance(row[6], str) else row[6],
                        'original_cost': str(row[7]) if row[7] else None,
                        'selling_price': str(row[8]) if row[8] else None,
                        'charges': str(row[9]) if row[9] else None,
                        'gst': str(row[10]) if row[10] else '0.00',
                        'stock': row[11],
                        'mfg_date': row[12],
                        'expiry_date': row[13],
                        'is_active': bool(row[14]),
                        'created_at': row[15],
                        'updated_at': row[16],
                        'color': row[17],
                        'gender': row[18],
                        'age': row[19],
                        'material': row[20],
                        'attributes': _json.loads(row[21]) if row[21] and isinstance(row[21], str) else row[21],
                        'pack': row[22],
                        'is_visible_counter': bool(row[23]),
                        'price_override': float(row[24]) if row[24] is not None else None,
                        'min_age': row[25],
                        'max_age': row[26],
                        'sub_category_id': product.sub_category_id if product else None,  # lives on product
                    }
                    return True, variant_dict
                else:
                    return False, {"error": "Failed to create variant"}
    except Exception as e:
        import traceback
        traceback.print_exc()
        return False, {
            "error": "Failed to update variant",
            "details": str(e)
        }


def _handle_grocery_update(request, grocery_product, request_data, request_files, partial):
    """Handle grocery product update logic.
    Returns: Response object
    """
    print(f"[GROCERY UPDATE] Starting update for product_id: {grocery_product.product_id}")
    print(f"[GROCERY UPDATE] Request data keys: {list(request_data.keys())}")
    print(f"[GROCERY UPDATE] Request files keys: {list(request_files.keys())}")
    
    # Create a mutable copy of the request data, excluding file objects
    data = {k: v for k, v in request_data.items() if not hasattr(v, 'read')}
    
    # Remove fields that shouldn't be updated by the client
    fields_to_remove = ['business', 'business_name', 'category_name', 'product_image', 'created_at', 'updated_at', 'product_id']
    for field in fields_to_remove:
        data.pop(field, None)
    
    # Handle explicit null/empty values - only if they exist in data
    if 'main_image' in data and data['main_image'] in [None, '', 'null']:
        data.pop('main_image', None)
    if 'category' in data and data.get('category') in [None, '']:
        data.pop('category', None)
    if 'is_visible' in data and data.get('is_visible') in [None, '', 'null']:
        data.pop('is_visible', None)

    if 'is_customizable' in data:
        v = data.get('is_customizable')
        if v in [None, '', 'null']:
            data.pop('is_customizable', None)
        elif isinstance(v, str):
            data['is_customizable'] = v.strip().lower() in ('1', 'true', 'yes', 'y')
        else:
            data['is_customizable'] = bool(v)
    
    # Handle image upload - support multiple keys
    image_file = None
    if 'main_image' in request_files:
        image_file = request_files['main_image']
    elif 'product_image' in request_files:
        image_file = request_files['product_image']
    elif 'item_image' in request_files:
        image_file = request_files['item_image']
        
    if image_file:
        saved_path = upload_image_to_s3(
            image_file,
            folder='groceries_images',
            compress=True,
            use_uuid=False
        )
        if saved_path:
            data['main_image'] = saved_path
    elif 'main_image' in data and data['main_image'] not in [None, '', 'null']:
        # If it's a string path/URL, preserve it
        pass
    elif 'product_image' in data and data['product_image'] not in [None, '', 'null']:
        data['main_image'] = data.pop('product_image')
    elif 'item_image' in data and data['item_image'] not in [None, '', 'null']:
        data['main_image'] = data.pop('item_image')
    
    # Handle sub_images (additional images)
    sub_image_files = []
    sub_image_keys = []
    for key in request_files:
        if key.startswith('sub_image_') or key == 'sub_images':
            sub_image_keys.append(key)
    
    # Sort keys to maintain order
    sub_image_keys.sort()
    
    for key in sub_image_keys:
        if key == 'sub_images':
            sub_image_files.extend(request_files.getlist(key))
        else:
            sub_image_files.append(request_files[key])
    
    # Get existing sub_images to determine starting index
    existing_sub_images = getattr(grocery_product, 'sub_images', None)
    start_index = 2
    if isinstance(existing_sub_images, dict):
        max_idx = 1
        for k in existing_sub_images.keys():
            if isinstance(k, str) and k.startswith('image'):
                try:
                    idx = int(k.replace('image', '').strip())
                    max_idx = max(max_idx, idx)
                except Exception:
                    continue
        start_index = max_idx + 1
    
    # Upload all sub_images using helper (array format)
    sub_images_array = []
    if sub_image_files:
        sub_images_array = upload_multiple_images_as_array(
            sub_image_files,
            folder='groceries_images',
            compress=True,
            use_uuid=False
        )
    
    # Handle sub_images from JSON data (merge with uploaded images)
    if 'sub_images' in data:
        if isinstance(data['sub_images'], str):
            try:
                import json as _json
                parsed = _json.loads(data['sub_images'])
                if isinstance(parsed, list):
                    # If it's already an array, use it directly
                    sub_images_array = parsed
                elif isinstance(parsed, dict):
                    # Convert dict to array (extract values)
                    sub_images_array = list(parsed.values())
            except Exception:
                pass
        elif isinstance(data['sub_images'], (dict, list)):
            if isinstance(data['sub_images'], dict):
                # Convert dict to array (extract values)
                sub_images_array = list(data['sub_images'].values())
            elif isinstance(data['sub_images'], list):
                # Use array directly
                sub_images_array = data['sub_images']
        
        # Remove the original field to avoid conflicts
        data.pop('sub_images', None)
    
    # Set sub_images (persist). If empty, store NULL.
    if sub_images_array:
        data['sub_images'] = sub_images_array
    elif 'sub_images' in request_data:
        data['sub_images'] = None
    
    # Handle is_featured field
    if 'is_featured' in data:
        v = data.get('is_featured')
        if v in [None, '', 'null']:
            data['is_featured'] = False
        elif isinstance(v, str):
            data['is_featured'] = v.strip().lower() in ('1', 'true', 'yes', 'y')
        else:
            data['is_featured'] = bool(v)
    
    # Extract and parse variant data
    variant_data = data.pop('variant', None)
    print(f"[GROCERY UPDATE] Raw variant_data type: {type(variant_data)}, value: {variant_data}")
    
    # If no explicit variant object, check for variant fields at top level
    if not variant_data:
        variant_fields = [
            'sku', 'barcode',
            'net_weight', 'net_weight_unit', 'size',
            'original_cost', 'selling_price', 'price_override', 'charges', 'gst',
            'stock', 'mfg_date', 'expiry_date', 'is_active',
            # Attribute columns
            'color', 'gender', 'age', 'min_age', 'max_age', 'material', 'attributes', 'pack',
            'is_visible_counter',
        ]
        top_level_variant_fields = {k: data.pop(k) for k in variant_fields if k in data}
        
        if top_level_variant_fields:
            print(f"[GROCERY UPDATE] Found variant fields at top level: {list(top_level_variant_fields.keys())}")
            # Get the first active variant for this product, or create one
            existing_variant = GroceriesProductVariants.objects.filter(
                product=grocery_product, 
                is_active=True
            ).first()
            
            if existing_variant:
                # Update existing variant
                variant_data = {'variant_id': existing_variant.variant_id}
                variant_data.update(top_level_variant_fields)
                print(f"[GROCERY UPDATE] Updating existing variant {existing_variant.variant_id} with: {top_level_variant_fields}")
            else:
                # Create new variant with these fields
                variant_data = top_level_variant_fields
                print(f"[GROCERY UPDATE] Will create new variant with: {variant_data}")
    
    if variant_data and isinstance(variant_data, str):
        try:
            import json
            variant_data = json.loads(variant_data)
            print(f"[GROCERY UPDATE] Parsed variant_data from JSON: {variant_data}")
        except (json.JSONDecodeError, ValueError) as e:
            print(f"[GROCERY UPDATE] Failed to parse variant JSON: {e}")
            return Response({
                "error": "Invalid variant data format",
                "details": f"Variant must be valid JSON: {str(e)}"
            }, status=status.HTTP_400_BAD_REQUEST)
    
    # If frontend still sends sub_category/sub_category_id inside the variant object,
    # pull them out to the top level so they get updated on the product.
    if variant_data and isinstance(variant_data, dict):
        if 'sub_category' in variant_data and not data.get('sub_category'):
            data['sub_category'] = variant_data.get('sub_category')
        if 'sub_category_id' in variant_data and not data.get('sub_category_id'):
            data['sub_category_id'] = variant_data.get('sub_category_id')

    # Update product only if there's product data to update
    updated_product = grocery_product
    if data:
        # Convert empty strings to None for numeric fields to avoid validation errors
        numeric_fields = ['selling_price', 'original_cost', 'charges', 'gst', 'stock']
        for field in numeric_fields:
            if field in data and data[field] == '':
                data[field] = None
        
        # Update product
        serializer = GroceriesProductsSerializer(
            grocery_product,
            data=data,
            partial=partial,
            context={"request": request}
        )
        
        if not serializer.is_valid():
            return Response({
                "error": "Validation failed",
                "details": serializer.errors,
                "data_received": dict(data)
            }, status=status.HTTP_400_BAD_REQUEST)
        
        updated_product = serializer.save()
    else:
        print(f"[GROCERY UPDATE] No product fields to update, only updating variant")
    
    # Update variant if provided
    variant_response = None
    if variant_data:
    
        success, result = _update_grocery_variant(variant_data, updated_product)
        if not success:
            return Response(result, status=status.HTTP_400_BAD_REQUEST)
        variant_response = result
    
    response_data = {
        "message": "Grocery product updated successfully",
        "product_id": updated_product.product_id,
        "product": GroceriesProductsSerializer(updated_product, context={"request": request}).data
    }
    
    # If product has no base_price, set it from first variant's selling_price
    if not response_data["product"].get("base_price"):
        try:
            from consumer.gro_serializers import GroceriesProductWithPricingSerializer
            product_with_variants = GroceriesProductWithPricingSerializer(updated_product, context={"request": request}).data
            variants = product_with_variants.get("variants", [])
            if variants and variants[0].get("selling_price"):
                response_data["product"]["base_price"] = variants[0]["selling_price"]
        except Exception:
            pass
    
    if variant_response:
        response_data["variant"] = variant_response
    
    # Include all variants with mfg_date, expiry_date in response
    from consumer.gro_serializers import GroceriesProductWithPricingSerializer
    response_data["variants"] = GroceriesProductWithPricingSerializer(updated_product, context={"request": request}).data.get("variants", [])
    
    return Response(response_data, status=status.HTTP_200_OK)


def _handle_fashion_update(request, fashion_product, request_data, request_files, partial, business):
    data = {k: v for k, v in request_data.items() if not hasattr(v, 'read')}

    fields_to_remove = ['business', 'business_name', 'category_name', 'product_image', 'created_at', 'updated_at', 'product_id']
    for field in fields_to_remove:
        data.pop(field, None)

    for img_field in ['main_image']:
        if img_field in data and data[img_field] in [None, '', 'null']:
            data.pop(img_field, None)

    def _save_uploaded_image(field_name, folder, target_field=None):
        if field_name not in request_files:
            return
        img_file = request_files[field_name]
        compressed = compress_image(img_file)
        if not compressed:
            return
        orig_name = getattr(img_file, 'name', 'upload.jpg')
        base_name = os.path.splitext(os.path.basename(orig_name))[0]
        filename = f"{base_name}.jpg"
        rel_path = os.path.join(folder, filename).replace('\\', '/')
        
        # Save using default_storage (S3 or local)
        saved_name = default_storage.save(rel_path, compressed)
        
        data[target_field or field_name] = f"media/{saved_name}"

    # Use UUID-based filenames for R08 images (update)
    import uuid
    def _save_uploaded_image_uuid(field_name, folder, target_field=None):
        if field_name not in request_files:
            return
        img_file = request_files[field_name]
        compressed = compress_image(img_file)
        if not compressed:
            return
        # Generate UUID filename with .jpg extension
        unique_id = str(uuid.uuid4())
        filename = f"{unique_id}.jpg"
        rel_path = os.path.join(folder, filename).replace('\\', '/')
        
        # Save using default_storage (S3 or local)
        saved_name = default_storage.save(rel_path, compressed)
        
        data[target_field or field_name] = f"media/{saved_name}"

    # Handle main image and sub_images for fashion products
    sub_images_list = []
    
    # Handle main_image (first image)
    if 'main_image' in request_files or 'item_image' in request_files:
        main_img_file = request_files.get('main_image') or request_files.get('item_image')
        if main_img_file:
            saved_path = upload_image_to_s3(
                main_img_file,
                folder='fashion_images',
                compress=True,
                use_uuid=True
            )
            if saved_path:
                data['main_image'] = saved_path
    
    # Handle additional images as sub_images only
    sub_image_files = []
    sub_image_keys = []
    for key in request_files:
        if key.startswith('sub_image_') or key == 'sub_images':
            sub_image_keys.append(key)
    
    # Sort keys to maintain order
    sub_image_keys.sort()
    
    for key in sub_image_keys:
        if key == 'sub_images':
            sub_image_files.extend(request_files.getlist(key))
        else:
            sub_image_files.append(request_files[key])
    
    # Upload all sub_images using helper (array format)
    sub_images_array = []
    if sub_image_files:
        sub_images_array = upload_multiple_images_as_array(
            sub_image_files,
            folder='fashion_images',
            compress=True,
            use_uuid=True
        )
    
    # Handle sub_images from JSON data (merge with uploaded images)
    if 'sub_images' in data:
        if isinstance(data['sub_images'], str):
            try:
                import json as _json
                parsed = _json.loads(data['sub_images'])
                if isinstance(parsed, list):
                    # If it's already an array, use it directly
                    sub_images_array = parsed
                elif isinstance(parsed, dict):
                    # Convert dict to array (extract values)
                    sub_images_array = list(parsed.values())
            except Exception:
                pass
        elif isinstance(data['sub_images'], (dict, list)):
            if isinstance(data['sub_images'], dict):
                # Convert dict to array (extract values)
                sub_images_array = list(data['sub_images'].values())
            elif isinstance(data['sub_images'], list):
                # Use array directly
                sub_images_array = data['sub_images']
        
        # Remove the original field to avoid conflicts
        data.pop('sub_images', None)
    
    # Set sub_images if we have any
    if sub_images_array:
        data['sub_images'] = sub_images_array
    
    # Handle is_featured field
    if 'is_featured' in data:
        v = data.get('is_featured')
        if v in [None, '', 'null']:
            data['is_featured'] = False
        elif isinstance(v, str):
            data['is_featured'] = v.strip().lower() in ('1', 'true', 'yes', 'y')
        else:
            data['is_featured'] = bool(v)

    if 'item_name' in data and 'name' not in data:
        data['name'] = data.get('item_name')
    if 'brand_name' in data and 'brand' not in data:
        data['brand'] = data.get('brand_name')
    if 'gst_percentage' in data and 'gst_rate_default' not in data:
        data['gst_rate_default'] = data.get('gst_percentage')
    if 'gst' in data and 'gst_rate_default' not in data:
        data['gst_rate_default'] = data.get('gst')

    if 'item_category' in data and not data.get('category') and not data.get('category_id'):
        try:
            cat_name = str(data.get('item_category') or '').strip()
            if cat_name:
                cat_obj = UniversalCategory.objects.filter(category_name__iexact=cat_name, parent_category_id__isnull=True).first()
                if cat_obj:
                    data['category'] = cat_obj.category_id
        except Exception:
            pass

    if 'category_id' in data and 'category' not in data:
        data['category'] = data.get('category_id')
    if 'subcategory_id' in data and 'subcategory' not in data:
        data['subcategory'] = data.get('subcategory_id')
    if 'hsn' in data and 'hsn_code' not in data:
        data['hsn_code'] = data.get('hsn')

    variant_source_data = dict(data)
    variant_data = data.pop('variant', None)
    if variant_data and isinstance(variant_data, str):
        try:
            variant_data = json.loads(variant_data)
        except (json.JSONDecodeError, ValueError):
            return Response({
                "error": "Invalid variant data format",
                "details": "Variant must be valid JSON"
            }, status=status.HTTP_400_BAD_REQUEST)

    if not variant_data:
        possible = [
            'sku', 'barcode', 'selling_price', 'mrp',
            'stock_qty', 'stock',
            'net_weight', 'net_weight_unit',
            'original_cost', 'charges',
            'mfg_date', 'mfg_data', 'expiry_date',
            'size', 'color', 'material', 'gender',
            'attributes', 'is_active', 'status'
        ]
        if any(k in variant_source_data for k in possible):
            variant_data = {k: variant_source_data.get(k) for k in possible if k in variant_source_data}

    if isinstance(variant_data, dict):
        if 'mfg_data' in variant_data and not variant_data.get('mfg_date'):
            variant_data['mfg_date'] = variant_data.pop('mfg_data')

        if 'stock' in variant_data and 'stock_qty' not in variant_data:
            variant_data['stock_qty'] = variant_data.get('stock')
        if 'stock_qty' in variant_data and 'stock' not in variant_data:
            variant_data['stock'] = variant_data.get('stock_qty')

        extra_attrs = {}
        for k in [
            'item_name', 'item_type', 'item_category',
            'quantity', 'unit', 'weight',
            'wallet_points_avaliablity', 'wallet_points_availablity', 'wallet_points',
            'availability_timings',
            'gst', 'gst_percentage'
        ]:
            if k in variant_source_data and variant_source_data.get(k) not in [None, '', 'null']:
                extra_attrs[k] = variant_source_data.get(k)

        if 'availability_timings' in extra_attrs and isinstance(extra_attrs.get('availability_timings'), str):
            try:
                extra_attrs['availability_timings'] = json.loads(extra_attrs.get('availability_timings'))
            except (json.JSONDecodeError, ValueError, TypeError) as ex:
                return Response({
                    "error": "Invalid JSON format in availability_timings",
                    "details": {
                        "availability_timings": [f"Value must be valid JSON. Parse error: {str(ex)}"]
                    }
                }, status=status.HTTP_400_BAD_REQUEST)

        attrs_val = variant_data.get('attributes')
        if isinstance(attrs_val, str):
            try:
                attrs_val = json.loads(attrs_val)
            except Exception:
                pass
        if not isinstance(attrs_val, dict):
            attrs_val = {}
        attrs_val.update(extra_attrs)
        if attrs_val:
            variant_data['attributes'] = attrs_val

    allowed_product_fields = {
        'category', 'subcategory',
        'name', 'description', 'brand',
        'base_price', 'gst_rate_default', 'hsn_code',
        'main_image', 'sub_images', 'is_featured',
        'rating', 'item_placed_at',
        'is_active'
    }
    data = {k: data.get(k) for k in allowed_product_fields if k in data}

    serializer = FashionProductSerializer(
        fashion_product,
        data=data,
        partial=partial,
        context={"request": request}
    )

    if not serializer.is_valid():
        return Response({
            "error": "Validation failed",
            "details": serializer.errors,
            "data_received": dict(data)
        }, status=status.HTTP_400_BAD_REQUEST)

    updated_product = serializer.save()

    variant_response = None
    if variant_data and isinstance(variant_data, dict):
        if 'status' in variant_data and 'is_active' not in variant_data:
            variant_data['is_active'] = variant_data.pop('status')

        variant_id = variant_data.get('variant_id') or variant_data.get('id')
        if variant_id:
            try:
                variant_obj = FashionProductVariant.objects.get(
                    variant_id=variant_id,
                    product=updated_product,
                    business_id=business.business_id
                )
            except FashionProductVariant.DoesNotExist:
                return Response({"error": "Invalid variant_id"}, status=status.HTTP_400_BAD_REQUEST)

            variant_serializer = FashionProductVariantSerializer(
                variant_obj,
                data=variant_data,
                partial=True,
                context={"request": request}
            )
        else:
            existing_one = None
            try:
                prod_vid = getattr(updated_product, 'variant_id', None)
                if prod_vid:
                    existing_one = FashionProductVariant.objects.filter(
                        variant_id=prod_vid,
                        product=updated_product,
                        business_id=business.business_id
                    ).first()
                if not existing_one:
                    existing_one = FashionProductVariant.objects.filter(
                        product=updated_product,
                        business_id=business.business_id
                    ).order_by('variant_id').first()
            except Exception:
                existing_one = None

            if existing_one:
                variant_serializer = FashionProductVariantSerializer(
                    existing_one,
                    data=variant_data,
                    partial=True,
                    context={"request": request}
                )
            else:
                vp = dict(variant_data)
                vp['product'] = updated_product.product_id
                vp['business_id'] = business.business_id
                allowed_variant_fields = {
                    'product', 'business_id', 'sku', 'barcode',
                    'selling_price', 'mrp', 'stock_qty',
                    'net_weight', 'net_weight_unit',
                    'original_cost', 'charges',
                    'stock', 'mfg_date', 'expiry_date',
                    'size', 'color', 'material', 'gender',
                    'attributes', 'is_active'
                }
                vp = {k: vp.get(k) for k in allowed_variant_fields if k in vp}
                variant_serializer = FashionProductVariantSerializer(data=vp, context={"request": request})

        if variant_serializer.is_valid():
            variant_obj = variant_serializer.save()
            variant_response = FashionProductVariantSerializer(variant_obj, context={"request": request}).data
            try:
                if not getattr(updated_product, 'variant_id', None):
                    updated_product.variant_id = variant_obj.variant_id
                    updated_product.save(update_fields=['variant_id'])
            except Exception:
                pass
        else:
            return Response({
                "message": "Product updated, but variant invalid",
                "product_id": updated_product.product_id,
                "product": FashionProductSerializer(updated_product, context={"request": request}).data,
                "variant_errors": variant_serializer.errors
            }, status=status.HTTP_200_OK)

    response_data = {
        "message": "Fashion product updated successfully",
        "product_id": updated_product.product_id,
        "product": FashionProductSerializer(updated_product, context={"request": request}).data
    }
    
    # If product has no base_price, set it from first variant's selling_price
    if not response_data["product"].get("base_price"):
        try:
            variants = FashionProductVariant.objects.filter(product_id=updated_product.product_id, is_active=True).order_by('selling_price')
            if variants.exists():
                response_data["product"]["base_price"] = str(variants.first().selling_price)
        except Exception:
            pass
    
    if variant_response:
        response_data["variant"] = variant_response
    return Response(response_data, status=status.HTTP_200_OK)


def _handle_menu_item_update(request, product_item, request_data, request_files, partial):
    """Handle menu/product item update logic.
    Returns: Response object
    """
    # Handle image compression and mapping
    image_file = None
    if 'item_image' in request_files:
        image_file = request_files['item_image']
    elif 'main_image' in request_files:
        image_file = request_files['main_image']
    elif 'product_image' in request_files:
        image_file = request_files['product_image']

    if image_file:
        request_files['item_image'] = compress_image(image_file)

    # Create a mutable copy of request data, excluding file objects
    data = {k: v for k, v in request_data.items() if not hasattr(v, 'read')}
    
    # Map alternative image field names to item_image for productItems model
    if 'main_image' in data and 'item_image' not in data:
        data['item_image'] = data.pop('main_image')
    elif 'product_image' in data and 'item_image' not in data:
        data['item_image'] = data.pop('product_image')
    
    # Parse JSON fields that might come as strings from FormData
    json_fields = ['availability_timings']
    for field in json_fields:
        if field in data and isinstance(data[field], str):
            # Only try to parse non-empty strings
            if data[field].strip():
                try:
                    data[field] = json.loads(data[field])
                except (json.JSONDecodeError, ValueError, TypeError) as e:
                    # Return early with clear error message if JSON parsing fails
                    return Response({
                        "error": "Invalid JSON format",
                        "details": {
                            field: [f"Value must be valid JSON. Parse error: {str(e)}"]
                        }
                    }, status=status.HTTP_400_BAD_REQUEST)
            else:
                # Empty string should be treated as None/null
                data[field] = None
        
    data.pop('is_visible', None)
    
    # Convert empty strings to None for numeric fields to avoid validation errors
    numeric_fields = ['selling_price', 'quantity', 'gst']
    for field in numeric_fields:
        if field in data and data[field] == '':
            data[field] = None
    
    serializer = productItemsSerializer(
        product_item,
        data=data,
        partial=partial,
        context={"request": request}
    )
    
    if serializer.is_valid():
        updated_product_item = serializer.save()
        
        # If item has no base_price, set it from selling_price
        response_data = serializer.data
        if not response_data.get("base_price") and response_data.get("selling_price"):
            response_data["base_price"] = response_data["selling_price"]
        
        return Response({
            "message": "Product item updated successfully",
            "item_id": updated_product_item.item_id,
            "product_item_details": response_data
        }, status=status.HTTP_200_OK)
    
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@swagger_auto_schema(method='POST', tags=['Business'])
@api_view(['POST'])
@parser_classes([JSONParser, MultiPartParser, FormParser])
def addProductVariant(request):
    """
    Dedicated endpoint to handle multiple variants for a single product.
    Supports single variant (dict) or multiple variants (list).
    """
    user_id = request.query_params.get("user_id")
    business_id = request.query_params.get("business_id")
    product_id = request.query_params.get("product_id")

    if not user_id or not business_id or not product_id:
        return Response({"error": "user_id, business_id, and product_id are required"}, status=status.HTTP_400_BAD_REQUEST)

    try:
        business = Business.objects.get(business_id=business_id, status=True)
    except Business.DoesNotExist:
        return Response({"error": "Invalid business_id"}, status=status.HTTP_404_NOT_FOUND)

    # Check permissions
    is_pos_user, allowed_business_ids = _check_user_permissions(user_id, business_id)
    if not is_pos_user:
        if not BusinessMapping.objects.filter(user_id=user_id, business_id=business_id).exists():
            return Response({"error": "User does not have access to this business"}, status=status.HTTP_403_FORBIDDEN)

    bt = (business.businessType or '').strip().upper()
    is_grocery = bt == 'R01'
    is_fashion = bt == 'R08'

    # Find the parent product
    product = None
    if is_fashion:
        from .models import FashionProduct
        product = FashionProduct.objects.filter(product_id=product_id, business_id=business).first()
    else:
        from consumer.gro_models import GroceriesProducts
        product = GroceriesProducts.objects.filter(product_id=product_id, business=business).first()

    if not product:
        return Response({"error": "Product not found or doesn't belong to this business"}, status=status.HTTP_404_NOT_FOUND)

    # Detect bulk or single payload
    data_list = request.data
    if isinstance(data_list, dict):
        # Support "variants" key or wrapping single dict in list
        data_list = data_list.get('variants', [data_list])
    if not isinstance(data_list, list):
        return Response({"error": "Payload must be a dictionary or a list of variants"}, status=status.HTTP_400_BAD_REQUEST)

    results = []
    errors = []

    for index, vp_raw in enumerate(data_list):
        vp = vp_raw.copy() if hasattr(vp_raw, 'copy') else vp_raw
        if not isinstance(vp, dict):
            errors.append({"index": index, "error": "Invalid variant data format"})
            continue

        # Map parent info
        if is_fashion:
            from .serializers import FashionProductVariantSerializer
            vp['product'] = product.product_id
            vp['business_id'] = business.business_id
            
            # Sync stock fields
            if 'stock' in vp and 'stock_qty' not in vp:
                vp['stock_qty'] = vp['stock']
            if 'stock_qty' in vp and 'stock' not in vp:
                vp['stock'] = vp['stock_qty']

            # Auto-generate SKU if missing
            if not vp.get('sku'):
                import re
                base_name = getattr(product, 'product_name', getattr(product, 'name', 'ITEM'))
                clean_name = re.sub(r'[^a-zA-Z0-9]', '', base_name).upper()[:12]
                size_part = re.sub(r'[^a-zA-Z0-9]', '', str(vp.get('size', ''))).upper()[:4]
                vp['sku'] = f"{clean_name}{size_part}{str(business.business_id)[-6:]}".strip()

            # Handle pricing normalization
            for field in ['price_override', 'selling_price', 'original_cost', 'mrp']:
                if vp.get(field) == '': vp[field] = None

            serializer = FashionProductVariantSerializer(data=vp)
        else:
            # Grocery Variant
            from consumer.gro_serializers import GroceriesProductVariantsSerializer
            vp['product'] = product.product_id
            
            # Handle pricing normalization
            for field in ['price_override', 'selling_price', 'original_cost']:
                if vp.get(field) == '': vp[field] = None

            # Handle size JSON normalization
            if 'size' in vp:
                size_raw = vp['size']
                if size_raw and not isinstance(size_raw, dict):
                    import json as _json
                    try:
                        vp['size'] = _json.loads(size_raw) if isinstance(size_raw, str) and size_raw.strip().startswith('{') else {'value': str(size_raw)}
                    except Exception:
                        vp['size'] = {'value': str(size_raw)}

            serializer = GroceriesProductVariantsSerializer(data=vp)

        if serializer.is_valid():
            try:
                variant_obj = serializer.save()
                results.append(serializer.data)
            except Exception as e:
                # Handle unique constraint on SKU for Fashion
                if is_fashion and 'unique' in str(e).lower() and 'sku' in str(e).lower():
                    base_sku = vp.get('sku', '')
                    import time
                    vp['sku'] = f"{base_sku}-{int(time.time()) % 1000}"
                    serializer = FashionProductVariantSerializer(data=vp)
                    if serializer.is_valid():
                        variant_obj = serializer.save()
                        results.append(serializer.data)
                    else:
                        errors.append({"index": index, "sku": vp.get('sku'), "errors": serializer.errors})
                else:
                    errors.append({"index": index, "error": str(e)})
        else:
            errors.append({"index": index, "errors": serializer.errors})

    return Response({
        "message": f"Processed {len(results)} variants with {len(errors)} errors",
        "created_count": len(results),
        "results": results,
        "errors": errors
    }, status=status.HTTP_201_CREATED if results else status.HTTP_201_CREATED) # Always return 201 for bulk consistency


@swagger_auto_schema(methods=['GET', 'PUT', 'PATCH', 'DELETE'], tags=['Business'])
@api_view(['GET', 'PUT', 'PATCH', 'DELETE'])
@parser_classes([MultiPartParser, FormParser, JSONParser])
def groceries_product_variant_detail(request, variant_id):
    """
    Retrieve, update, or delete a single grocery product variant.
    PUT/PATCH: update fields. GET: fetch current variant. DELETE: remove it.
    Query params: user_id, business_id
    """
    user_id = request.query_params.get('user_id')
    business_id = request.query_params.get('business_id')

    if not user_id or not business_id:
        return Response({"error": "user_id and business_id are required"}, status=status.HTTP_400_BAD_REQUEST)

    try:
        business = Business.objects.get(business_id=business_id, status=True)
    except Business.DoesNotExist:
        return Response({"error": "Invalid business_id"}, status=status.HTTP_404_NOT_FOUND)

    is_pos_user, allowed_business_ids = _check_user_permissions(user_id, business_id)
    if not is_pos_user:
        if not BusinessMapping.objects.filter(user_id=user_id, business_id=business_id).exists():
            return Response({"error": "Access denied"}, status=status.HTTP_403_FORBIDDEN)

    # Verify variant belongs to this business
    with connection.cursor() as cursor:
        cursor.execute("""
            SELECT v.variant_id, v.product_id, v.sku, v.barcode,
                   v.net_weight, v.net_weight_unit, v.size,
                   v.original_cost, v.selling_price, v.charges, v.gst, v.stock,
                   v.mfg_date, v.expiry_date, v.is_active, v.created_at, v.updated_at,
                   v.color, v.gender, v.age, v.material, v.attributes, v.pack,
                   v.is_visible_counter, v.price_override, v.min_age, v.max_age, v.dimension
            FROM Groceries_ProductVariants_1 v
            INNER JOIN Groceries_Products gp ON gp.product_id = v.product_id
            WHERE v.variant_id = %s AND gp.business_id = %s
            LIMIT 1
        """, [variant_id, business_id])
        row = cursor.fetchone()

    if not row:
        return Response({"error": "Variant not found"}, status=status.HTTP_404_NOT_FOUND)

    def _serialize_variant_row(r):
        import json as _json
        return {
            "variant_id": r[0],
            "product_id": r[1],
            "sku": r[2],
            "barcode": r[3],
            "net_weight": r[4],
            "net_weight_unit": r[5],
            "size": _json.loads(r[6]) if r[6] and isinstance(r[6], str) else r[6],
            "original_cost": str(r[7]) if r[7] else None,
            "selling_price": str(r[8]) if r[8] else None,
            "charges": str(r[9]) if r[9] else None,
            "gst": str(r[10]) if r[10] else "0.00",
            "stock": r[11],
            "mfg_date": r[12].isoformat() if r[12] else None,
            "expiry_date": r[13].isoformat() if r[13] else None,
            "is_active": bool(r[14]) if r[14] is not None else True,
            "created_at": r[15].isoformat() if r[15] else None,
            "updated_at": r[16].isoformat() if r[16] else None,
            "color": r[17],
            "gender": r[18],
            "age": r[19],
            "material": r[20],
            "attributes": _json.loads(r[21]) if r[21] and isinstance(r[21], str) else r[21],
            "pack": r[22],
            "is_visible_counter": bool(r[23]) if r[23] is not None else False,
            "price_override": float(r[24]) if r[24] is not None else None,
            "min_age": r[25],
            "max_age": r[26],
            "dimension": _json.loads(r[27]) if r[27] and isinstance(r[27], str) else r[27],
        }

    if request.method == 'GET':
        return Response({"success": True, "variant": _serialize_variant_row(row)}, status=status.HTTP_200_OK)

    if request.method == 'DELETE':
        with connection.cursor() as cursor:
            cursor.execute(
                "DELETE FROM Groceries_ProductVariants_1 WHERE variant_id = %s",
                [variant_id]
            )
        return Response({"success": True, "message": "Variant deleted", "variant_id": int(variant_id)}, status=status.HTTP_200_OK)

    # PUT / PATCH — delegate to the existing helper which handles all field mapping
    product_id = row[1]
    try:
        product = GroceriesProducts.objects.get(product_id=product_id)
    except GroceriesProducts.DoesNotExist:
        return Response({"error": "Parent product not found"}, status=status.HTTP_404_NOT_FOUND)

    payload = dict(request.data)
    # Ensure variant_id is in the payload so _update_grocery_variant targets this row
    payload['variant_id'] = int(variant_id)

    success, result = _update_grocery_variant(payload, product)
    if not success:
        return Response(result, status=status.HTTP_400_BAD_REQUEST)

    return Response({"success": True, "variant": result}, status=status.HTTP_200_OK)


@swagger_auto_schema(methods=['GET', 'PUT', 'PATCH', 'DELETE'], tags=['Business'])
@api_view(['GET', 'PUT', 'PATCH', 'DELETE'])
@parser_classes([MultiPartParser, FormParser, JSONParser])
def fashion_product_variant_detail(request, variant_id):
    """
    Retrieve, update, or delete a single fashion product variant.
    PUT/PATCH: update fields. GET: fetch current variant. DELETE: remove it.
    Query params: user_id, business_id
    """
    user_id = request.query_params.get('user_id')
    business_id = request.query_params.get('business_id')

    if not user_id or not business_id:
        return Response({"error": "user_id and business_id are required"}, status=status.HTTP_400_BAD_REQUEST)

    try:
        business = Business.objects.get(business_id=business_id, status=True)
    except Business.DoesNotExist:
        return Response({"error": "Invalid business_id"}, status=status.HTTP_404_NOT_FOUND)

    is_pos_user, allowed_business_ids = _check_user_permissions(user_id, business_id)
    if not is_pos_user:
        if not BusinessMapping.objects.filter(user_id=user_id, business_id=business_id).exists():
            return Response({"error": "Access denied"}, status=status.HTTP_403_FORBIDDEN)

    # Verify variant belongs to this business
    is_active_filter = request.method == 'GET'
    try:
        from .models import FashionProductVariant, FashionProduct
        variant = FashionProductVariant.objects.select_related('product').filter(
            variant_id=variant_id, 
            product__business_id=business_id
        )
        if is_active_filter:
            variant = variant.filter(is_active=True)
        variant = variant.get()
    except FashionProductVariant.DoesNotExist:
        return Response({"error": "Fashion variant not found"}, status=status.HTTP_404_NOT_FOUND)

    def _serialize_fashion_variant(variant_obj):
        return {
            "variant_id": variant_obj.variant_id,
            "product_id": variant_obj.product.product_id,
            "sku": variant_obj.sku,
            "barcode": variant_obj.barcode,
            "size": variant_obj.size,
            "color": variant_obj.color,
            "material": variant_obj.material,
            "gender": variant_obj.gender,
            "stock": variant_obj.stock,
            "stock_qty": variant_obj.stock_qty,
            "selling_price": str(variant_obj.selling_price) if variant_obj.selling_price else None,
            "original_cost": str(variant_obj.original_cost) if variant_obj.original_cost else None,
            "charges": str(variant_obj.charges) if variant_obj.charges else None,
            "mrp": str(variant_obj.mrp) if variant_obj.mrp else None,
            "net_weight": variant_obj.net_weight,
            "net_weight_unit": variant_obj.net_weight_unit,
            "mfg_date": variant_obj.mfg_date.isoformat() if variant_obj.mfg_date else None,
            "expiry_date": variant_obj.expiry_date.isoformat() if variant_obj.expiry_date else None,
            "min_age": variant_obj.min_age,
            "max_age": variant_obj.max_age,
            "pack": variant_obj.pack,
            "attributes": variant_obj.attributes,
            "dimension": variant_obj.dimension,
            "is_active": variant_obj.is_active,
            "created_at": variant_obj.created_at.isoformat() if variant_obj.created_at else None,
            "updated_at": variant_obj.updated_at.isoformat() if variant_obj.updated_at else None,
        }

    if request.method == 'GET':
        return Response({"success": True, "variant": _serialize_fashion_variant(variant)}, status=status.HTTP_200_OK)

    if request.method == 'DELETE':
        # Soft delete by setting is_active=False
        variant.is_active = False
        variant.save(update_fields=['is_active'])
        return Response({
            "success": True, 
            "message": "Fashion variant deleted (soft delete)", 
            "variant_id": int(variant_id)
        }, status=status.HTTP_200_OK)

    # PUT / PATCH - Update variant
    from .serializers import FashionProductVariantSerializer
    
    payload = dict(request.data)
    # Ensure variant_id is in the payload
    payload['variant_id'] = int(variant_id)
    payload['product'] = variant.product.product_id
    payload['business_id'] = business_id

    # Sync stock fields if one is provided
    if 'stock' in payload and 'stock_qty' not in payload:
        payload['stock_qty'] = payload['stock']
    elif 'stock_qty' in payload and 'stock' not in payload:
        payload['stock'] = payload['stock_qty']

    # Remove fields that don't exist in FashionProductVariant
    payload.pop('price_override', None)
    payload.pop('is_visible_counter', None)

    serializer = FashionProductVariantSerializer(variant, data=payload, partial=True)
    if not serializer.is_valid():
        return Response({"error": "Validation failed", "errors": serializer.errors}, status=status.HTTP_400_BAD_REQUEST)

    try:
        updated_variant = serializer.save()
        return Response({"success": True, "variant": _serialize_fashion_variant(updated_variant)}, status=status.HTTP_200_OK)
    except Exception as e:
        return Response({"error": f"Update failed: {str(e)}"}, status=status.HTTP_400_BAD_REQUEST)


@swagger_auto_schema(
    method='GET',
    tags=['Business'],
    manual_parameters=[
        openapi.Parameter(
            'user_id',
            openapi.IN_QUERY,
            description='User ID retrieving the product item',
            type=openapi.TYPE_STRING,
            required=True
        ),
        openapi.Parameter(
            'business_id',
            openapi.IN_QUERY,
            description='Business ID for the product item',
            type=openapi.TYPE_STRING,
            required=True
        ),
        openapi.Parameter(
            'include_variants',
            openapi.IN_QUERY,
            description='Set to 1/true to include all variants with mfg_date, expiry_date, stock in response',
            type=openapi.TYPE_STRING,
            required=False
        ),
    ],
    responses={
        200: openapi.Response(
            description='Product item retrieved successfully',
            examples={
                'application/json': {
                    'product_id': 157378,
                    'product_name': 'Wheat Flour',
                    'brand_name': 'ecomall',
                    'category': 401,
                    'category_name': 'CLOTHING',
                    'sub_category': "men's wear",
                    'sub_category_id': 402,
                    'main_image': 'http://example.com/media/groceries_images/image.jpg',
                    'sub_images': {'image2': 'url', 'image3': 'url'},
                    'is_featured': True,
                    'is_customizable': False,
                    'is_visible': True,
                    'base_price': '100.00',
                    'variants': [
                        {
                            'variant_id': 157395,
                            'sku': 'wheatflour1kg',
                            'stock': 25,
                            'mfg_date': '2026-01-15',
                            'expiry_date': '2026-12-31',
                            'selling_price': '120.00',
                            'original_cost': '100.00',
                            'net_weight': 1.0,
                            'net_weight_unit': 'kg',
                            'is_active': True
                        }
                    ]
                }
            }
        ),
        400: openapi.Response(
            description='Bad request - missing or invalid parameters',
            examples={
                'application/json': {
                    'error': 'user_id, business_id and item_id are required'
                }
            }
        ),
        404: openapi.Response(
            description='User, business, or product item not found',
            examples={
                'application/json': {
                    'error': 'Invalid user_id'
                }
            }
        )
    }
)
@swagger_auto_schema(
    method='PUT',
    tags=['Business'],
    manual_parameters=[
        openapi.Parameter(
            'user_id',
            openapi.IN_QUERY,
            description='User ID updating the product item',
            type=openapi.TYPE_STRING,
            required=True
        ),
        openapi.Parameter(
            'business_id',
            openapi.IN_QUERY,
            description='Business ID for the product item',
            type=openapi.TYPE_STRING,
            required=True
        ),
    ],
    request_body=openapi.Schema(
        type=openapi.TYPE_OBJECT,
        properties={
            # Product-level fields
            'product_name': openapi.Schema(type=openapi.TYPE_STRING, description='Product name'),
            'brand_name': openapi.Schema(type=openapi.TYPE_STRING, description='Brand name'),
            'category': openapi.Schema(type=openapi.TYPE_INTEGER, description='Category ID'),
            'sub_category': openapi.Schema(type=openapi.TYPE_STRING, description='Sub-category name'),
            'sub_category_id': openapi.Schema(type=openapi.TYPE_INTEGER, description='Sub-category ID'),
            'description': openapi.Schema(type=openapi.TYPE_STRING, description='Product description'),
            'base_price': openapi.Schema(type=openapi.TYPE_NUMBER, description='Base price'),
            'is_featured': openapi.Schema(type=openapi.TYPE_BOOLEAN, description='Featured product flag'),
            'is_customizable': openapi.Schema(type=openapi.TYPE_BOOLEAN, description='Whether product is customizable'),
            'is_visible': openapi.Schema(type=openapi.TYPE_BOOLEAN, description='Product visibility'),
            'main_image': openapi.Schema(type=openapi.TYPE_FILE, description='Main product image'),
            'sub_images': openapi.Schema(type=openapi.TYPE_ARRAY, items=openapi.Schema(type=openapi.TYPE_FILE), description='Additional product images'),
            # Variant-level fields (nested object)
            'variant': openapi.Schema(
                type=openapi.TYPE_OBJECT,
                description='Variant data to update. Include variant_id to update a specific variant.',
                properties={
                    'variant_id': openapi.Schema(type=openapi.TYPE_INTEGER, description='ID of specific variant to update (required for multi-variant products)'),
                    'sku': openapi.Schema(type=openapi.TYPE_STRING, description='SKU code'),
                    'barcode': openapi.Schema(type=openapi.TYPE_STRING, description='Barcode'),
                    'stock': openapi.Schema(type=openapi.TYPE_INTEGER, description='Stock quantity'),
                    'selling_price': openapi.Schema(type=openapi.TYPE_NUMBER, description='Selling price'),
                    'original_cost': openapi.Schema(type=openapi.TYPE_NUMBER, description='Original cost'),
                    'mfg_date': openapi.Schema(type=openapi.TYPE_STRING, description='Manufacturing date (YYYY-MM-DD)'),
                    'expiry_date': openapi.Schema(type=openapi.TYPE_STRING, description='Expiry date (YYYY-MM-DD)'),
                    'net_weight': openapi.Schema(type=openapi.TYPE_NUMBER, description='Net weight'),
                    'net_weight_unit': openapi.Schema(type=openapi.TYPE_STRING, description='Weight unit (kg, g, L, mL, pcs)'),
                    'size': openapi.Schema(type=openapi.TYPE_STRING, description='Size info'),
                    'color': openapi.Schema(type=openapi.TYPE_STRING, description='Color'),
                    'material': openapi.Schema(type=openapi.TYPE_STRING, description='Material'),
                    'gst': openapi.Schema(type=openapi.TYPE_NUMBER, description='GST percentage'),
                    'is_active': openapi.Schema(type=openapi.TYPE_BOOLEAN, description='Variant active status'),
                }
            ),
        }
    ),
    responses={
        200: openapi.Response(
            description='Product item updated successfully',
            examples={
                'application/json': {
                    'message': 'Grocery product updated successfully',
                    'product_id': 157378,
                    'product': {
                        'product_id': 157378,
                        'product_name': 'Wheat Flour',
                        'is_customizable': False,
                        'is_featured': True
                    },
                    'variant': {
                        'variant_id': 157395,
                        'stock': 25,
                        'mfg_date': '2026-01-15',
                        'expiry_date': '2026-12-31',
                        'selling_price': '120.00'
                    },
                    'variants': [
                        {
                            'variant_id': 157395,
                            'stock': 25,
                            'mfg_date': '2026-01-15',
                            'expiry_date': '2026-12-31'
                        }
                    ]
                }
            }
        ),
        400: openapi.Response(
            description='Bad request - missing or invalid parameters',
            examples={
                'application/json': {
                    'error': 'user_id, business_id and item_id are required'
                }
            }
        ),
        404: openapi.Response(
            description='User, business, or product item not found',
            examples={
                'application/json': {
                    'error': 'Invalid user_id'
                }
            }
        )
    }
)
@swagger_auto_schema(
    method='PATCH',
    tags=['Business'],
    manual_parameters=[
        openapi.Parameter(
            'user_id',
            openapi.IN_QUERY,
            description='User ID updating the product item',
            type=openapi.TYPE_STRING,
            required=True
        ),
        openapi.Parameter(
            'business_id',
            openapi.IN_QUERY,
            description='Business ID for the product item',
            type=openapi.TYPE_STRING,
            required=True
        ),
    ],
    request_body=openapi.Schema(
        type=openapi.TYPE_OBJECT,
        description='Partial update - only include fields to change',
        properties={
            # Product-level fields
            'product_name': openapi.Schema(type=openapi.TYPE_STRING, description='Product name'),
            'brand_name': openapi.Schema(type=openapi.TYPE_STRING, description='Brand name'),
            'category': openapi.Schema(type=openapi.TYPE_INTEGER, description='Category ID'),
            'sub_category': openapi.Schema(type=openapi.TYPE_STRING, description='Sub-category name'),
            'description': openapi.Schema(type=openapi.TYPE_STRING, description='Product description'),
            'base_price': openapi.Schema(type=openapi.TYPE_NUMBER, description='Base price'),
            'is_featured': openapi.Schema(type=openapi.TYPE_BOOLEAN, description='Featured product flag'),
            'is_customizable': openapi.Schema(type=openapi.TYPE_BOOLEAN, description='Whether product is customizable'),
            'is_visible': openapi.Schema(type=openapi.TYPE_BOOLEAN, description='Product visibility'),
            'main_image': openapi.Schema(type=openapi.TYPE_FILE, description='Main product image'),
            'sub_images': openapi.Schema(type=openapi.TYPE_ARRAY, items=openapi.Schema(type=openapi.TYPE_FILE), description='Additional product images'),
            # Variant-level fields (nested object)
            'variant': openapi.Schema(
                type=openapi.TYPE_OBJECT,
                description='Variant data to update. Include variant_id to update a specific variant.',
                properties={
                    'variant_id': openapi.Schema(type=openapi.TYPE_INTEGER, description='ID of specific variant to update (required for multi-variant products)'),
                    'sku': openapi.Schema(type=openapi.TYPE_STRING, description='SKU code'),
                    'barcode': openapi.Schema(type=openapi.TYPE_STRING, description='Barcode'),
                    'stock': openapi.Schema(type=openapi.TYPE_INTEGER, description='Stock quantity'),
                    'selling_price': openapi.Schema(type=openapi.TYPE_NUMBER, description='Selling price'),
                    'original_cost': openapi.Schema(type=openapi.TYPE_NUMBER, description='Original cost'),
                    'mfg_date': openapi.Schema(type=openapi.TYPE_STRING, description='Manufacturing date (YYYY-MM-DD)'),
                    'expiry_date': openapi.Schema(type=openapi.TYPE_STRING, description='Expiry date (YYYY-MM-DD)'),
                    'net_weight': openapi.Schema(type=openapi.TYPE_NUMBER, description='Net weight'),
                    'net_weight_unit': openapi.Schema(type=openapi.TYPE_STRING, description='Weight unit (kg, g, L, mL, pcs)'),
                    'is_active': openapi.Schema(type=openapi.TYPE_BOOLEAN, description='Variant active status'),
                }
            ),
        }
    ),
    responses={
        200: openapi.Response(
            description='Product item patched successfully',
            examples={
                'application/json': {
                    'message': 'Grocery product updated successfully',
                    'product_id': 157378,
                    'product': {
                        'product_id': 157378,
                        'is_customizable': False
                    },
                    'variant': {
                        'variant_id': 157395,
                        'stock': 25,
                        'mfg_date': '2026-01-15',
                        'expiry_date': '2026-12-31'
                    },
                    'variants': [
                        {
                            'variant_id': 157395,
                            'stock': 25,
                            'mfg_date': '2026-01-15',
                            'expiry_date': '2026-12-31'
                        }
                    ]
                }
            }
        ),
        400: openapi.Response(
            description='Bad request - missing or invalid parameters',
            examples={
                'application/json': {
                    'error': 'user_id, business_id and item_id are required'
                }
            }
        ),
        404: openapi.Response(
            description='User, business, or product item not found',
            examples={
                'application/json': {
                    'error': 'Invalid user_id'
                }
            }
        )
    }
)
@swagger_auto_schema(
    method='DELETE',
    tags=['Business'],
    manual_parameters=[
        openapi.Parameter(
            'user_id',
            openapi.IN_QUERY,
            description='User ID deleting the product item',
            type=openapi.TYPE_STRING,
            required=True
        ),
        openapi.Parameter(
            'business_id',
            openapi.IN_QUERY,
            description='Business ID for the product item',
            type=openapi.TYPE_STRING,
            required=True
        ),
    ],
    responses={
        200: openapi.Response(
            description='Product item deleted successfully',
            examples={
                'application/json': {
                    'message': 'Product item deleted successfully',
                    'item_id': 'string'
                }
            }
        ),
        400: openapi.Response(
            description='Bad request - missing or invalid parameters',
            examples={
                'application/json': {
                    'error': 'user_id, business_id and item_id are required'
                }
            }
        ),
        404: openapi.Response(
            description='User, business, or product item not found',
            examples={
                'application/json': {
                    'error': 'Invalid user_id'
                }
            }
        )
    }
)
@api_view(['GET', 'PUT', 'PATCH', 'DELETE'])
@parser_classes([MultiPartParser, FormParser, JSONParser])
def updateProductItems(request, item_id):
    """
    Retrieve, update or delete product items. Handles both:
    - productItems (retail products with item_id)
    - GroceriesProducts (grocery products with product_id)
    """
    # Validate required parameters
    user_id = request.query_params.get("user_id")
    business_id = request.query_params.get("business_id")
    
    if not user_id or not business_id or not item_id:
        return Response({
            "error": "user_id, business_id and item_id are required"
        }, status=status.HTTP_400_BAD_REQUEST)
    
    # Validate user and business
    try:
        user = Registration.objects.get(user_id=user_id, status=True)
    except Registration.DoesNotExist:
        return Response({"error": "Invalid user_id"}, status=status.HTTP_404_NOT_FOUND)
    
    try:
        business = Business.objects.get(business_id=business_id, status=True)
    except Business.DoesNotExist:
        return Response({"error": "Invalid business_id"}, status=status.HTTP_404_NOT_FOUND)
    
    # Check user permissions
    is_pos_user, allowed_business_ids = _check_user_permissions(user_id, business_id)
    
    # Validate business mapping for non-POS users
    if not is_pos_user:
        if not BusinessMapping.objects.filter(user_id=user_id, business_id=business_id).exists():
            return Response({
                "error": "User does not have access to this business"
            }, status=status.HTTP_403_FORBIDDEN)
    
    bt = (business.businessType or '').strip().upper()
    if bt == 'R08':
        try:
            fashion_product = FashionProduct.objects.get(product_id=item_id)
        except FashionProduct.DoesNotExist:
            return Response({
                "error": "Invalid item_id - not found in fashion_products"
            }, status=status.HTTP_404_NOT_FOUND)

        # Validate business ownership/access
        product_business_id = str(getattr(fashion_product.business_id, 'business_id', None))
        if is_pos_user:
            allowed_ids_str = {str(bid) for bid in allowed_business_ids}
            if product_business_id not in allowed_ids_str:
                return Response({
                    "error": "Fashion product doesn't belong to an allowed business",
                    "product_business_id": product_business_id,
                    "allowed_business_ids": list(allowed_ids_str)
                }, status=status.HTTP_403_FORBIDDEN)
        else:
            if product_business_id != str(business_id):
                return Response({
                    "error": "Fashion product doesn't belong to this business",
                    "product_business_id": product_business_id,
                    "requested_business_id": str(business_id)
                }, status=status.HTTP_403_FORBIDDEN)

        if request.method == 'GET':
            serializer = FashionProductWithVariantsSerializer(fashion_product, context={"request": request})
            return Response(serializer.data, status=status.HTTP_200_OK)

        if request.method in ['PUT', 'PATCH']:
            partial = request.method == 'PATCH'
            return _handle_fashion_update(request, fashion_product, request.data, request.FILES, partial, business)

        if request.method == 'DELETE':
            fashion_product.is_active = False
            fashion_product.save(update_fields=['is_active'])
            try:
                FashionProductVariant.objects.filter(product=fashion_product).update(is_active=False)
            except Exception:
                pass
            return Response({
                "message": "Fashion product deleted successfully",
                "product_id": fashion_product.product_id
            }, status=status.HTTP_200_OK)

    # Find product in productItems or GroceriesProducts
    product_item = None
    grocery_product = None
    is_grocery = False
    
    try:
        product_item = productItems.objects.get(item_id=item_id)
    except productItems.DoesNotExist:
        try:
            grocery_product = GroceriesProducts.objects.get(product_id=item_id)
            is_grocery = True
        except GroceriesProducts.DoesNotExist:
            return Response({
                "error": "Invalid item_id - not found in productItems or GroceriesProducts"
            }, status=status.HTTP_404_NOT_FOUND)
    
    # Validate product access
    is_valid, error_response = _validate_product_access(
        product_item, grocery_product, is_grocery, 
        business_id, is_pos_user, allowed_business_ids
    )
    if not is_valid:
        return error_response
    
    # Handle GET
    if request.method == 'GET':
        if is_grocery:
            # For business management, always show all variants (active and inactive)
            include_variants = str(request.query_params.get('include_variants', '1')).lower() in ('1', 'true', 'yes')
            if include_variants:
                from consumer.gro_serializers import GroceriesProductWithPricingSerializer
                serializer = GroceriesProductWithPricingSerializer(grocery_product, context={"request": request})
            else:
                serializer = GroceriesProductsSerializer(grocery_product, context={"request": request})
            return Response({
                "message": "Grocery product retrieved successfully",
                "product": serializer.data
            }, status=status.HTTP_200_OK)
        else:
            from business.serializers import MenuItemsSerializer
            serializer = MenuItemsSerializer(product_item, context={"request": request})
            return Response({
                "message": "Product item retrieved successfully",
                "product": serializer.data
            }, status=status.HTTP_200_OK)
    
    # Handle UPDATE
    if request.method in ['PUT', 'PATCH']:
        partial = request.method == 'PATCH'
        
        if is_grocery:
            return _handle_grocery_update(request, grocery_product, request.data, request.FILES, partial)
        else:
            return _handle_menu_item_update(request, product_item, request.data, request.FILES, partial)
    
    # Handle DELETE
    elif request.method == 'DELETE':
        if is_grocery:
            product_name = grocery_product.product_name
            product_id = grocery_product.product_id
            grocery_product.delete()
            return Response({
                "message": f"Grocery product '{product_name}' deleted successfully",
                "product_id": product_id
            }, status=status.HTTP_200_OK)
        else:
            product_item.status = False
            product_item.is_active = False
            product_item.save()
            return Response({
                "message": "Product item deleted successfully",
                "item_id": product_item.item_id
            }, status=status.HTTP_200_OK)

@swagger_auto_schema(method='GET', tags=['Business'])
@api_view(['GET'])
def search_grocery_skus(request):
    user_id = request.query_params.get('user_id') or request.query_params.get('userID')
    business_id = request.query_params.get('business_id')
    q = request.query_params.get('q') or request.query_params.get('search')
    in_stock_only = request.query_params.get('in_stock_only')
    is_active = request.query_params.get('is_active')
    category_id = request.query_params.get('category_id')
    try:
        limit = int(request.query_params.get('limit', 20))
        offset = int(request.query_params.get('offset', 0))
        if limit > 100:
            limit = 100
        if limit < 1:
            limit = 20
        if offset < 0:
            offset = 0
    except ValueError:
        return Response({"error": "Invalid limit/offset"}, status=status.HTTP_400_BAD_REQUEST)

    if not user_id or not business_id:
        return Response({"error": "user_id and business_id are required"}, status=status.HTTP_400_BAD_REQUEST)

    # Ownership/access check
    business = None
    try:
        business = Business.objects.get(business_id=business_id, status=True)
    except Business.DoesNotExist:
        return Response({"error": "Invalid business_id"}, status=status.HTTP_404_NOT_FOUND)
    if not BusinessMapping.objects.filter(user__user_id=user_id, business=business).exists():
        return Response({"error": "User does not have access to this business"}, status=status.HTTP_403_FORBIDDEN)

    qs = GroceriesProductVariants.objects.select_related('product', 'product__category').filter(
        product__business_id=business_id
    )

    if q:
        qs = qs.filter(
            Q(sku__icontains=q) |
            Q(product__product_name__icontains=q) |
            Q(product__brand_name__icontains=q)
        )

    if in_stock_only is not None:
        val = str(in_stock_only).lower()
        if val in ('1', 'true', 'yes'):
            qs = qs.filter(stock__gt=0)

    if is_active is not None:
        val = str(is_active).lower()
        if val in ('1', 'true', 'yes'):
            qs = qs.filter(is_active=True)
        elif val in ('0', 'false', 'no'):
            qs = qs.filter(is_active=False)

    if category_id:
        qs = qs.filter(product__category_id=category_id)

    total = qs.count()
    items = list(
        qs.order_by('product__product_name', 'sku')[offset:offset+limit]
    )

    results = []
    for v in items:
        p = v.product
        results.append({
            "variant_id": v.variant_id,
            "sku": v.sku,
            "barcode": v.barcode,
            "product_id": p.product_id,
            "product_name": p.product_name,
            "brand_name": p.brand_name,
            "category_id": getattr(p.category, 'category_id', None),
            "category_name": getattr(p.category, 'category_name', None),
            "sub_category": getattr(p, 'sub_category', None),
            "sub_category_id": getattr(p, 'sub_category_id', None),
            "base_price": float(p.base_price) if p.base_price is not None else 0.0,
            "net_weight": v.net_weight,
            "net_weight_unit": v.net_weight_unit,
            "size": v.size,
            "color": v.color,
            "gender": v.gender,
            "age": v.age,
            "material": v.material,
            "attributes": v.attributes,
            "pack": v.pack,
            "original_cost": v.original_cost,
            "selling_price": v.selling_price,
            "price_override": float(v.price_override) if v.price_override is not None else None,
            "charges": v.charges,
            "stock": v.stock,
            "is_active": v.is_active,
            "is_visible_counter": v.is_visible_counter,
            "min_age": v.min_age,
            "max_age": v.max_age,
            "is_visible": True if getattr(p, 'is_visible', None) is None else bool(getattr(p, 'is_visible')),
        })


    return Response({
        "results": results,
        "total": total,
        "offset": offset,
        "limit": limit
    }, status=status.HTTP_200_OK)

@swagger_auto_schema(method='GET', tags=['Business'])   
@api_view(['GET'])
def list_menu_items(request):
    user_id = request.query_params.get('userID') or request.query_params.get('user_id')
    business_id = request.query_params.get('business_id')
    search = request.query_params.get('search') or request.query_params.get('q')
    category = request.query_params.get('category')
    
    # Check if pagination parameters are provided
    limit_param = request.query_params.get('limit')
    offset_param = request.query_params.get('offset')
    use_pagination = limit_param is not None or offset_param is not None
    
    try:
        if use_pagination:
            limit = int(limit_param) if limit_param else 20
            offset = int(offset_param) if offset_param else 0
            if limit > 100:
                limit = 100
            if limit < 1:
                limit = 20
            if offset < 0:
                offset = 0
        else:
            limit = None
            offset = None
    except ValueError:
        return Response({"error": "Invalid limit/offset"}, status=status.HTTP_400_BAD_REQUEST)

    if not user_id or not business_id:
        return Response({"error": "userID and business_id are required"}, status=status.HTTP_400_BAD_REQUEST)

    try:
        business = Business.objects.get(business_id=business_id)
    except Business.DoesNotExist:
        return Response({"error": "Business not found"}, status=status.HTTP_404_NOT_FOUND)

    # Check if user is a POS/KOT counter user
    is_pos_user = False
    pos_master_business_id = None
    with connection.cursor() as cursor:
        # First check if user is POS for the specific business_id
        cursor.execute(
            """
            SELECT role, business_id FROM business_role_management
            WHERE assigned_to = %s AND business_id = %s AND status = 1
            """,
            [user_id, business_id]
        )
        row = cursor.fetchone()
        if row and row[0] and row[0].upper() in ['POS', 'KOT', 'COUNTER']:
            is_pos_user = True
        else:
            # Check if user is POS for a master business that has this business as a child
            cursor.execute(
                """
                SELECT brm.role, brm.business_id 
                FROM business_role_management brm
                INNER JOIN businesses b ON b.business_id = brm.business_id
                WHERE brm.assigned_to = %s 
                  AND brm.status = 1 
                  AND b.level = 'master'
                  AND b.status = 1
                  AND EXISTS (
                      SELECT 1 FROM businesses child 
                      WHERE child.master = brm.business_id 
                      AND child.business_id = %s 
                      AND child.status = 1
                  )
                """,
                [user_id, business_id]
            )
            master_row = cursor.fetchone()
            if master_row and master_row[0] and master_row[0].upper() in ['POS', 'KOT', 'COUNTER']:
                is_pos_user = True
                pos_master_business_id = master_row[1]

    # Check user access using the same logic as addProductItems
    if not is_pos_user:
        # Get user's business mapping
        user_mapping = BusinessMapping.objects.filter(user__user_id=user_id, status=True).select_related('business').first()
        
        if not user_mapping:
            return Response({"error": "User does not have access to any business"}, status=status.HTTP_403_FORBIDDEN)
        
        # Get the user's mapped business
        user_business = user_mapping.business
        
        # Determine if user has access to the requested business
        has_access = False
        
        # Check if user's business matches the requested business
        if user_business.business_id == business_id:
            has_access = True
        # Check if user's business is the master of the requested business
        elif business.master and user_business.business_id == business.master:
            has_access = True
        # Check if requested business is the master of user's business
        elif user_business.master and user_business.master == business_id:
            has_access = True
        
        if not has_access:
            return Response({"error": "User does not have access to this business"}, status=status.HTTP_403_FORBIDDEN)

    # Build query - return items from the REQUESTED business AND all child businesses if it's a master
    business_ids = [business.business_id]  # Always include the requested business
    
    # If this is a master business, include all child businesses
    if business.level and business.level.strip().lower() == 'master':
        child_businesses = Business.objects.filter(master=business.business_id, status=True).values_list('business_id', flat=True)
        business_ids.extend(list(child_businesses))
    
    qs = MenuItems.objects.filter(business_id__in=business_ids, status=True)

    if search:
        qs = qs.filter(item_name__icontains=search)
    if category:
        qs = qs.filter(item_category__iexact=category)
    # Filter out items with status = False

    total = qs.count()
    
    if use_pagination:
        # Apply pagination
        items = list(qs.order_by('item_name')[offset:offset+limit])
        data = MenuItemsSerializer(items, many=True, context={"request": request}).data
        
        # Calculate parent quantity as sum of all variant stock_qty
        for item_data in data:
            total_quantity = 0
            if 'variants' in item_data and item_data['variants']:
                for variant in item_data['variants']:
                    stock_qty = variant.get('stock_qty', 0)
                    if stock_qty is not None:
                        total_quantity += int(stock_qty)
            item_data['quantity'] = total_quantity

        return Response({
            "items": data,
            "count": total,
            "limit": limit,
            "offset": offset,
            "paginated": True
        }, status=status.HTTP_200_OK)
    else:
        # Return all items without pagination
        items = list(qs.order_by('item_name'))
        data = MenuItemsSerializer(items, many=True, context={"request": request}).data
        
        # Calculate parent quantity as sum of all variant stock_qty
        for item_data in data:
            total_quantity = 0
            if 'variants' in item_data and item_data['variants']:
                for variant in item_data['variants']:
                    stock_qty = variant.get('stock_qty', 0)
                    if stock_qty is not None:
                        total_quantity += int(stock_qty)
            item_data['quantity'] = total_quantity

        return Response({
            "items": data,
            "count": total,
            "limit": total,
            "offset": 0,
            "paginated": False
        }, status=status.HTTP_200_OK)


@swagger_auto_schema(method='GET', tags=['Business'])
@api_view(['GET'])
def list_grocery_products_owner(request):
    user_id = request.query_params.get('user_id') or request.query_params.get('userID')
    business_id = request.query_params.get('business_id')
    q = request.query_params.get('q') or request.query_params.get('search')
    category_id = request.query_params.get('category_id')
    include_variants = str(request.query_params.get('include_variants', '0')).lower() in ('1', 'true', 'yes')
    try:
        limit = int(request.query_params.get('limit', 20))
        offset = int(request.query_params.get('offset', 0))
        if limit > 100:
            limit = 100
        if limit < 1:
            limit = 20
        if offset < 0:
            offset = 0
    except ValueError:
        return Response({"error": "Invalid limit/offset"}, status=status.HTTP_400_BAD_REQUEST)

    if not user_id or not business_id:
        return Response({"error": "user_id and business_id are required"}, status=status.HTTP_400_BAD_REQUEST)

    try:
        business = Business.objects.get(business_id=business_id, status=True)
    except Business.DoesNotExist:
        return Response({"error": "Invalid business_id"}, status=status.HTTP_404_NOT_FOUND)

    # Check if user is a POS/KOT counter user
    is_pos_user = False
    pos_master_business_id = None
    with connection.cursor() as cursor:
        # First check if user is POS for the specific business_id
        cursor.execute(
            """
            SELECT role, business_id FROM business_role_management
            WHERE assigned_to = %s AND business_id = %s AND status = 1
            """,
            [user_id, business_id]
        )
        row = cursor.fetchone()
        if row and row[0] and row[0].upper() in ['POS', 'KOT', 'COUNTER']:
            is_pos_user = True
        else:
            # Check if user is POS for a master business that has this business as a child
            cursor.execute(
                """
                SELECT brm.role, brm.business_id 
                FROM business_role_management brm
                INNER JOIN businesses b ON b.business_id = brm.business_id
                WHERE brm.assigned_to = %s 
                  AND brm.status = 1 
                  AND b.level = 'master'
                  AND b.status = 1
                  AND EXISTS (
                      SELECT 1 FROM businesses child 
                      WHERE child.master = brm.business_id 
                      AND child.business_id = %s 
                      AND child.status = 1
                  )
                """,
                [user_id, business_id]
            )
            master_row = cursor.fetchone()
            if master_row and master_row[0] and master_row[0].upper() in ['POS', 'KOT', 'COUNTER']:
                is_pos_user = True
                pos_master_business_id = master_row[1]

    # Check user access using the same logic as addProductItems and list_menu_items
    if not is_pos_user:
        # Get user's business mapping
        user_mapping = BusinessMapping.objects.filter(user__user_id=user_id, status=True).select_related('business').first()
        
        if not user_mapping:
            return Response({"error": "User does not have access to any business"}, status=status.HTTP_403_FORBIDDEN)
        
        # Get the user's mapped business
        user_business = user_mapping.business
        
        # Determine if user has access to the requested business
        has_access = False
        
        # Check if user's business matches the requested business
        if user_business.business_id == business_id:
            has_access = True
        # Check if user's business is the master of the requested business
        elif business.master and user_business.business_id == business.master:
            has_access = True
        # Check if requested business is the master of user's business
        elif user_business.master and user_business.master == business_id:
            has_access = True
        
        if not has_access:
            return Response({"error": "User does not have access to this business"}, status=status.HTTP_403_FORBIDDEN)

    bt = (business.businessType or '').strip().upper()
    min_age = request.query_params.get('min_age')
    max_age = request.query_params.get('max_age')
    pack = request.query_params.get('pack')

    if bt == 'R08':
        qs = FashionProduct.objects.select_related('category', 'business_id').filter(business_id=business)
        if min_age:
            qs = qs.filter(variants__min_age__gte=min_age).distinct()
        if max_age:
            qs = qs.filter(variants__max_age__lte=max_age).distinct()
        if pack:
            qs = qs.filter(variants__pack__icontains=pack).distinct()
        if q:
            qs = qs.filter(Q(name__icontains=q) | Q(brand__icontains=q))
        if category_id:
            qs = qs.filter(category_id=category_id)

        qs = qs.order_by('name')
        total = qs.count()
        page = list(qs[offset:offset+limit])

        if include_variants:
            from django.db.models import Prefetch
            variants_qs = FashionProductVariant.objects.all()
            page = list(
                FashionProduct.objects.select_related('category', 'business_id')
                .prefetch_related(Prefetch('variants', queryset=variants_qs))
                .filter(pk__in=[p.pk for p in page])
                .order_by('name')
            )
            ser = FashionProductWithVariantsSerializer(page, many=True, context={"request": request})
        else:
            ser = FashionProductSerializer(page, many=True, context={"request": request})

        return Response({
            "items": ser.data,
            "count": total,
            "limit": limit,
            "offset": offset
        }, status=status.HTTP_200_OK)

    # Build query - return products from the REQUESTED business only
    # Frontend will make separate requests for each business if needed
    qs = GroceriesProducts.objects.select_related('business').filter(business=business)
    if min_age:
        qs = qs.filter(groceriesproductvariants__min_age__gte=min_age).distinct()
    if max_age:
        qs = qs.filter(groceriesproductvariants__max_age__lte=max_age).distinct()
    if pack:
        qs = qs.filter(groceriesproductvariants__pack__icontains=pack).distinct()
    if q:
        qs = qs.filter(Q(product_name__icontains=q) | Q(brand_name__icontains=q))
    if category_id:
        qs = qs.filter(category_id=category_id)

    qs = qs.order_by('product_name')
    total = qs.count()
    page = list(qs[offset:offset+limit])

    if include_variants:
        # Prefetch variants for serializer efficiency
        # Include ALL variants (both active and inactive) for owner/admin view
        from django.db.models import Prefetch
        variants_qs = GroceriesProductVariants.objects.all()
        page = list(
            GroceriesProducts.objects.select_related('business')
            .prefetch_related(Prefetch('groceriesproductvariants_set', queryset=variants_qs))
            .filter(pk__in=[p.pk for p in page])
            .order_by('product_name')
        )
        ser = GroceriesProductWithPricingSerializer(page, many=True, context={"request": request})
    else:
        ser = GroceriesProductsSerializer(page, many=True, context={"request": request})

    return Response({
        "items": ser.data,
        "count": total,
        "limit": limit,
        "offset": offset
    }, status=status.HTTP_200_OK)


@swagger_auto_schema(methods=['GET', 'POST'], tags=['Business'])
@api_view(['GET', 'POST'])
@parser_classes([MultiPartParser, FormParser, JSONParser])
def groceries_custom_designs_owner(request):
    business_id = request.query_params.get('business_id')
    product_id = request.query_params.get('product_id') or request.query_params.get('item_id')

    if not business_id or not product_id:
        return Response({
            "error": "business_id and product_id are required"
        }, status=status.HTTP_400_BAD_REQUEST)

    # Validate business exists
    try:
        business = Business.objects.get(business_id=business_id, status=True)
    except Business.DoesNotExist:
        return Response({"error": "Invalid business_id"}, status=status.HTTP_404_NOT_FOUND)

    # Validate product access
    try:
        grocery_product = GroceriesProducts.objects.select_related('business').get(product_id=product_id)
    except GroceriesProducts.DoesNotExist:
        return Response({"error": "Invalid product_id"}, status=status.HTTP_404_NOT_FOUND)

    is_valid, error_response = _validate_product_access(
        None, grocery_product, True,
        business_id, False, [business_id]
    )
    if not is_valid:
        return error_response

    def _serialize_design_row(r):
        return {
            "id": int(r[0]),
            "business_id": str(r[1]),
            "product_id": int(r[2]),
            "name": r[3],
            "design_type": r[4],
            "price_delta": float(r[5]) if r[5] is not None else 0.0,
            "asset_url": r[6],
            "max_chars": int(r[7]) if r[7] is not None else None,
            "per_char_price": float(r[8]) if r[8] is not None else None,
            "flat_price": float(r[9]) if r[9] is not None else None,
            "base_price": float(r[10]) if r[10] is not None else None,
            "is_active": bool(r[11]) if r[11] is not None else True,
            "position": int(r[12]) if r[12] is not None else 0,
            "created_at": r[13].isoformat() if r[13] is not None else None,
            "updated_at": r[14].isoformat() if r[14] is not None else None,
        }

    if request.method == 'GET':
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT id, business_id, product_id, name, design_type, price_delta, asset_url,
                       max_chars, per_char_price, flat_price, base_price, is_active, position,
                       created_at, updated_at
                FROM Groceries_CustomDesigns
                WHERE business_id = %s AND product_id = %s
                ORDER BY position ASC, id ASC
                """,
                [business_id, product_id]
            )
            rows = cursor.fetchall()

        designs = [_serialize_design_row(r) for r in rows]
        return Response({
            "success": True,
            "business_id": str(business_id),
            "product_id": int(product_id),
            "designs": designs,
            "total": len(designs)
        }, status=status.HTTP_200_OK)

    # POST (create)
    payload = request.data or {}

    name = payload.get('name')
    design_type = payload.get('design_type')
    if not name or not str(name).strip():
        return Response({"error": "name is required"}, status=status.HTTP_400_BAD_REQUEST)
    if not design_type or not str(design_type).strip():
        return Response({"error": "design_type is required"}, status=status.HTTP_400_BAD_REQUEST)

    allowed_types = {'sticker', 'text', 'drawing', 'user_upload'}
    design_type = str(design_type).strip()
    if design_type not in allowed_types:
        return Response({
            "error": "Invalid design_type",
            "allowed": sorted(list(allowed_types))
        }, status=status.HTTP_400_BAD_REQUEST)

    def to_decimal_or_none(v, default=None):
        if v in [None, '', 'null']:
            return default
        try:
            return Decimal(str(v))
        except Exception:
            return default

    def to_int_or_none(v, default=None):
        if v in [None, '', 'null']:
            return default
        try:
            return int(v)
        except Exception:
            return default

    def to_bool_default(v, default=False):
        if v in [None, '', 'null']:
            return default
        if isinstance(v, bool):
            return v
        try:
            return str(v).strip().lower() in ('1', 'true', 'yes', 'y')
        except Exception:
            return default

    price_delta = to_decimal_or_none(payload.get('price_delta'), default=Decimal('0.00'))
    asset_url = payload.get('asset_url')
    
    # Handle File Upload
    if 'asset' in request.FILES:
        saved_path = upload_image_to_s3(
            request.FILES['asset'],
            folder='custom_designs',
            compress=False,  # Assets may not need compression
            use_uuid=True  # Use UUID for secure naming
        )
        if saved_path:
            asset_url = saved_path
    
    # Path normalization for provided asset_url string
    if asset_url and isinstance(asset_url, str):
        asset_url = asset_url.strip()
        if asset_url and not asset_url.startswith('media/') and not asset_url.startswith('http'):
            # Some old logic might store filenames directly, prefix it
            asset_url = f"media/{asset_url.lstrip('/')}"

    max_chars = to_int_or_none(payload.get('max_chars'))
    per_char_price = to_decimal_or_none(payload.get('per_char_price'))
    flat_price = to_decimal_or_none(payload.get('flat_price'))
    base_price = to_decimal_or_none(payload.get('base_price'))
    is_active = to_bool_default(payload.get('is_active'), default=True)
    position = to_int_or_none(payload.get('position'), default=0)

    with connection.cursor() as cursor:
        cursor.execute(
            """
            INSERT INTO Groceries_CustomDesigns
              (business_id, product_id, name, design_type, price_delta, asset_url,
               max_chars, per_char_price, flat_price, base_price, is_active, position)
            VALUES
              (%s, %s, %s, %s, %s, %s,
               %s, %s, %s, %s, %s, %s)
            """,
            [
                business_id, int(product_id), str(name).strip(), design_type,
                price_delta, asset_url,
                max_chars, per_char_price, flat_price, base_price,
                1 if is_active else 0, position
            ]
        )
        new_id = cursor.lastrowid

        cursor.execute(
            """
            SELECT id, business_id, product_id, name, design_type, price_delta, asset_url,
                   max_chars, per_char_price, flat_price, base_price, is_active, position,
                   created_at, updated_at
            FROM Groceries_CustomDesigns
            WHERE id = %s AND business_id = %s AND product_id = %s
            LIMIT 1
            """,
            [new_id, business_id, product_id]
        )
        row = cursor.fetchone()

    return Response({
        "success": True,
        "message": "Design created successfully",
        "design": _serialize_design_row(row) if row else {"id": new_id}
    }, status=status.HTTP_201_CREATED)


@swagger_auto_schema(methods=['GET', 'PUT', 'PATCH', 'DELETE'], tags=['Business'])
@api_view(['GET', 'PUT', 'PATCH', 'DELETE'])
@parser_classes([MultiPartParser, FormParser, JSONParser])
def groceries_custom_design_detail_owner(request, design_id):
    business_id = request.query_params.get('business_id')
    product_id = request.query_params.get('product_id') or request.query_params.get('item_id')

    if not business_id or not product_id:
        return Response({
            "error": "business_id and product_id are required"
        }, status=status.HTTP_400_BAD_REQUEST)

    # Validate business exists
    try:
        business = Business.objects.get(business_id=business_id, status=True)
    except Business.DoesNotExist:
        return Response({"error": "Invalid business_id"}, status=status.HTTP_404_NOT_FOUND)

    # Validate product access
    try:
        grocery_product = GroceriesProducts.objects.select_related('business').get(product_id=product_id)
    except GroceriesProducts.DoesNotExist:
        return Response({"error": "Invalid product_id"}, status=status.HTTP_404_NOT_FOUND)

    is_valid, error_response = _validate_product_access(
        None, grocery_product, True,
        business_id, False, [business_id]
    )
    if not is_valid:
        return error_response

    def _serialize_design_row(r):
        return {
            "id": int(r[0]),
            "business_id": str(r[1]),
            "product_id": int(r[2]),
            "name": r[3],
            "design_type": r[4],
            "price_delta": float(r[5]) if r[5] is not None else 0.0,
            "asset_url": r[6],
            "max_chars": int(r[7]) if r[7] is not None else None,
            "per_char_price": float(r[8]) if r[8] is not None else None,
            "flat_price": float(r[9]) if r[9] is not None else None,
            "base_price": float(r[10]) if r[10] is not None else None,
            "is_active": bool(r[11]) if r[11] is not None else True,
            "position": int(r[12]) if r[12] is not None else 0,
            "created_at": r[13].isoformat() if r[13] is not None else None,
            "updated_at": r[14].isoformat() if r[14] is not None else None,
        }

    def to_decimal_or_none(v, default=None):
        if v in [None, '', 'null']:
            return default
        try:
            return Decimal(str(v))
        except Exception:
            return default

    def to_int_or_none(v, default=None):
        if v in [None, '', 'null']:
            return default
        try:
            return int(v)
        except Exception:
            return default

    def to_bool_or_none(v):
        if v in [None, '', 'null']:
            return None
        if isinstance(v, bool):
            return v
        try:
            return str(v).strip().lower() in ('1', 'true', 'yes', 'y')
        except Exception:
            return None

    # Get current
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT id, business_id, product_id, name, design_type, price_delta, asset_url,
                   max_chars, per_char_price, flat_price, base_price, is_active, position,
                   created_at, updated_at
            FROM Groceries_CustomDesigns
            WHERE id = %s AND business_id = %s AND product_id = %s
            LIMIT 1
            """,
            [design_id, business_id, product_id]
        )
        current = cursor.fetchone()

    if not current:
        return Response({"error": "Design not found"}, status=status.HTTP_404_NOT_FOUND)

    if request.method == 'GET':
        return Response({
            "success": True,
            "design": _serialize_design_row(current)
        }, status=status.HTTP_200_OK)

    if request.method == 'DELETE':
        with connection.cursor() as cursor:
            cursor.execute(
                "DELETE FROM Groceries_CustomDesigns WHERE id = %s AND business_id = %s AND product_id = %s",
                [design_id, business_id, product_id]
            )
        return Response({
            "success": True,
            "message": "Design deleted successfully",
            "id": int(design_id)
        }, status=status.HTTP_200_OK)

    payload = request.data or {}
    allowed_types = {'sticker', 'text', 'drawing', 'user_upload'}

    update_map = {}
    if 'name' in payload:
        if not payload.get('name') or not str(payload.get('name')).strip():
            return Response({"error": "name cannot be empty"}, status=status.HTTP_400_BAD_REQUEST)
        update_map['name'] = str(payload.get('name')).strip()
    if 'design_type' in payload:
        dt = str(payload.get('design_type') or '').strip()
        if dt not in allowed_types:
            return Response({
                "error": "Invalid design_type",
                "allowed": sorted(list(allowed_types))
            }, status=status.HTTP_400_BAD_REQUEST)
        update_map['design_type'] = dt

    if 'price_delta' in payload:
        update_map['price_delta'] = to_decimal_or_none(payload.get('price_delta'), default=Decimal('0.00'))
    if 'asset_url' in payload:
        update_map['asset_url'] = payload.get('asset_url')
    
    # Handle File Upload in Update
    if 'asset' in request.FILES:
        saved_path = upload_image_to_s3(
            request.FILES['asset'],
            folder='custom_designs',
            compress=False,
            use_uuid=True  # Use UUID for secure naming
        )
        if saved_path:
            update_map['asset_url'] = saved_path
    
    # Path normalization for updated asset_url string
    if 'asset_url' in update_map and isinstance(update_map['asset_url'], str):
        url = update_map['asset_url'].strip()
        if url and not url.startswith('media/') and not url.startswith('http'):
            update_map['asset_url'] = f"media/{url.lstrip('/')}"

    if 'max_chars' in payload:
        update_map['max_chars'] = to_int_or_none(payload.get('max_chars'))
    if 'per_char_price' in payload:
        update_map['per_char_price'] = to_decimal_or_none(payload.get('per_char_price'))
    if 'flat_price' in payload:
        update_map['flat_price'] = to_decimal_or_none(payload.get('flat_price'))
    if 'base_price' in payload:
        update_map['base_price'] = to_decimal_or_none(payload.get('base_price'))
    if 'is_active' in payload:
        b = to_bool_or_none(payload.get('is_active'))
        if b is not None:
            update_map['is_active'] = 1 if b else 0
        else:
            return Response({
                "error": "Invalid is_active value. Expected boolean (true/false or 1/0)."
            }, status=status.HTTP_400_BAD_REQUEST)
    if 'position' in payload:
        update_map['position'] = to_int_or_none(payload.get('position'), default=0)

    if not update_map:
        return Response({
            "success": True,
            "message": "No changes",
            "design": _serialize_design_row(current)
        }, status=status.HTTP_200_OK)

    set_parts = []
    values = []
    for k, v in update_map.items():
        set_parts.append(f"{k} = %s")
        values.append(v)
    values.extend([design_id, business_id, product_id])

    with connection.cursor() as cursor:
        cursor.execute(
            f"UPDATE Groceries_CustomDesigns SET {', '.join(set_parts)}, updated_at = NOW() WHERE id = %s AND business_id = %s AND product_id = %s",
            values
        )
        cursor.execute(
            """
            SELECT id, business_id, product_id, name, design_type, price_delta, asset_url,
                   max_chars, per_char_price, flat_price, base_price, is_active, position,
                   created_at, updated_at
            FROM Groceries_CustomDesigns
            WHERE id = %s AND business_id = %s AND product_id = %s
            LIMIT 1
            """,
            [design_id, business_id, product_id]
        )
        updated = cursor.fetchone()

    return Response({
        "success": True,
        "message": "Design updated successfully",
        "design": _serialize_design_row(updated) if updated else _serialize_design_row(current)
    }, status=status.HTTP_200_OK)


# ==================== COUNTRY, STATE, DISTRICT, TALUK, PINCODE APIS ====================

@swagger_auto_schema(method='GET', tags=['Business'])
@api_view(['GET'])
def get_countries_with_states(request):
    """
    Get all countries with their states, districts, taluks, and pincodes
    Response format:
    {
        "countries": [
            {
                "country": "India",
                "states": [
                    {
                        "state": "Andhra Pradesh",
                        "districts": [
                            {
                                "district": "Alluri Sitharama Raju",
                                "taluks": [
                                    {
                                        "taluk": "Addateegala",
                                        "pincode": "533428",
                                        "status": 1
                                    }
                                ]
                            }
                        ]
                    }
                ]
            }
        ]
    }
    """
    try:
        # Get all data ordered by country, state, district, taluk
        records = CountryandStates.objects.all().order_by('country', 'state', 'district', 'taluk')
        
        countries_data = {}
        
        for record in records:
            country = record.country
            state = record.state
            district = record.district
            
            # Initialize country if not exists
            if country not in countries_data:
                countries_data[country] = {
                    'country': country,
                    'states': {}
                }
            
            # Initialize state if not exists
            if state not in countries_data[country]['states']:
                countries_data[country]['states'][state] = {
                    'state': state,
                    'districts': {}
                }
            
            # Initialize district if not exists
            if district not in countries_data[country]['states'][state]['districts']:
                countries_data[country]['states'][state]['districts'][district] = {
                    'district': district,
                    'taluks': []
                }
            
            # Add taluk data
            taluk_data = {
                'taluk': record.taluk,
                'pincode': record.pincode,
                'status': record.status
            }
            countries_data[country]['states'][state]['districts'][district]['taluks'].append(taluk_data)
        
        # Convert to list format
        result = {
            'countries': []
        }
        
        for country_data in countries_data.values():
            country_data['states'] = list(country_data['states'].values())
            for state_data in country_data['states']:
                state_data['districts'] = list(state_data['districts'].values())
            result['countries'].append(country_data)
        
        return Response(result, status=status.HTTP_200_OK)
        
    except Exception as e:
        return Response(
            {'error': f'An error occurred: {str(e)}'}, 
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@swagger_auto_schema(method='GET', tags=['Business'])
@api_view(['GET'])
def get_states_by_country(request, country):
    """Get all states for a specific country"""
    try:
        states = CountryandStates.objects.filter(country__iexact=country).values_list('state', flat=True).distinct()
        return Response({
            'country': country,
            'states': list(states)
        }, status=status.HTTP_200_OK)
        
    except Exception as e:
        return Response(
            {'error': f'An error occurred: {str(e)}'}, 
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@swagger_auto_schema(method='GET', tags=['Business'])
@api_view(['GET'])
def get_districts_by_state(request, country, state):
    """Get all districts for a specific state in a country"""
    try:
        districts = CountryandStates.objects.filter(
            country__iexact=country, 
            state__iexact=state
        ).values_list('district', flat=True).distinct()
        return Response({
            'country': country,
            'state': state,
            'districts': list(districts)
        }, status=status.HTTP_200_OK)
        
    except Exception as e:
        return Response(
            {'error': f'An error occurred: {str(e)}'}, 
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@swagger_auto_schema(method='GET', tags=['Business'])
@api_view(['GET'])
def get_taluks_by_district(request, country, state, district):
    """Get all taluks with pincodes and status for a specific district"""
    try:
        records = CountryandStates.objects.filter(
            country__iexact=country,
            state__iexact=state,
            district__iexact=district
        ).values('taluk', 'pincode', 'status').order_by('taluk')
        
        taluks = []
        for record in records:
            taluks.append({
                'taluk': record['taluk'],
                'pincode': record['pincode'],
                'status': record['status']
            })
        
        return Response({
            'country': country,
            'state': state,
            'district': district,
            'taluks': taluks
        }, status=status.HTTP_200_OK)
        
    except Exception as e:
        return Response(
            {'error': f'An error occurred: {str(e)}'}, 
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@swagger_auto_schema(method='GET', tags=['Business'])
@api_view(['GET'])
def get_pincodes_by_taluk(request, country, state, district, taluk):
    """Get pincodes and status for a specific taluk"""
    try:
        records = CountryandStates.objects.filter(
            country__iexact=country,
            state__iexact=state,
            district__iexact=district,
            taluk__iexact=taluk
        ).values('pincode', 'status')
        
        pincodes = []
        for record in records:
            pincodes.append({
                'pincode': record['pincode'],
                'status': record['status']
            })
        
        return Response({
            'country': country,
            'state': state,
            'district': district,
            'taluk': taluk,
            'pincodes': pincodes
        }, status=status.HTTP_200_OK)
        
    except Exception as e:
        return Response(
            {'error': f'An error occurred: {str(e)}'}, 
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@swagger_auto_schema(method='GET', tags=['Business'])
@api_view(['GET'])
def get_geographical_summary(request):
    """Get summary counts of countries, states, districts, taluks, and pincodes"""
    try:
        summary = {
            'countries': CountryandStates.objects.values('country').distinct().count(),
            'states': CountryandStates.objects.values('state').distinct().count(),
            'districts': CountryandStates.objects.values('district').distinct().count(),
            'taluks': CountryandStates.objects.values('taluk').distinct().count(),
            'pincodes': CountryandStates.objects.values('pincode').distinct().count(),
            'total_records': CountryandStates.objects.count(),
            'active_records': CountryandStates.objects.filter(status=1).count(),
            'inactive_records': CountryandStates.objects.filter(status=0).count()
        }
        
        return Response(summary, status=status.HTTP_200_OK)
        
    except Exception as e:
        return Response(
            {'error': f'An error occurred: {str(e)}'}, 
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@swagger_auto_schema(method='GET', tags=['Business'])
@api_view(['GET'])
def search_geographical_data(request):
    """
    Search geographical data by any field
    Query parameters:
    - q: search query
    - field: search field (country, state, district, taluk, pincode)
    - status: filter by status (0, 1, or all)
    """
    try:
        search_query = request.GET.get('q', '')
        search_field = request.GET.get('field', 'all')
        status_filter = request.GET.get('status', 'all')
        
        if not search_query:
            return Response({'error': 'Search query is required'}, status=status.HTTP_400_BAD_REQUEST)
        
        # Build base queryset
        queryset = CountryandStates.objects.all()
        
        # Apply status filter
        if status_filter != 'all':
            queryset = queryset.filter(status=int(status_filter))
        
        # Apply search filter
        if search_field == 'all':
            queryset = queryset.filter(
                Q(country__icontains=search_query) |
                Q(state__icontains=search_query) |
                Q(district__icontains=search_query) |
                Q(taluk__icontains=search_query) |
                Q(pincode__icontains=search_query)
            )
        else:
            filter_kwargs = {f'{search_field}__icontains': search_query}
            queryset = queryset.filter(**filter_kwargs)
        
        # Serialize results
        serializer = CountryandStatesSerializer(queryset[:100], many=True)  # Limit to 100 results
        
        return Response({
            'search_query': search_query,
            'search_field': search_field,
            'status_filter': status_filter,
            'total_results': queryset.count(),
            'results': serializer.data
        }, status=status.HTTP_200_OK)
        
    except Exception as e:
        return Response(
            {'error': f'An error occurred: {str(e)}'}, 
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )

#Display Menu Items
@swagger_auto_schema(methods=['GET', 'POST'], tags=['Business'])
@api_view(['GET', 'POST'])
def ItemsViewBasedonBusinessID(request):
    """Main view function that dispatches to appropriate service based on business type."""
    if request.method in ['GET', 'POST']:
        business_id = request.query_params.get("business_id", None)
        business_type = request.query_params.get("type", None)

        if not business_type:
            return Response({"error": "businessType is required"}, status=status.HTTP_400_BAD_REQUEST)

        try:
            business, business_data = _get_business_context_business(request, business_id)
            qp = _parse_items_query_params_business(request)

            # Dispatch to appropriate service based on business type
            if business_type == 'R02':
                # Restaurant/Menu items
                resp = _service_items_r02_business(request, business, business_id, qp)
                payload = resp.data
                payload['business'] = business_data
                payload['is_business_open'] = bool(getattr(business, 'status', True))
                return Response(payload, status=resp.status_code)

            elif business_type == 'R08':
                # Fashion products
                try:
                    resp = _service_items_r08_business(request, business, business_id, qp)
                    payload = resp.data
                    payload['business'] = business_data
                    return Response(payload, status=resp.status_code)
                except Exception as e:
                    return Response({"error": f"Failed to fetch fashion items: {str(e)}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

            elif business_type == 'R01':
                # Grocery products
                try:
                    resp = _service_items_r01_business(request, business, business_id, qp)
                    payload = resp.data
                    payload['business'] = business_data
                    return Response(payload, status=resp.status_code)
                except Exception as e:
                    error_trace = traceback.format_exc()
                    error_response = {
                        "error": "An error occurred while processing your request",
                        "details": str(e)
                    }
                    if settings.DEBUG:
                        error_response["trace"] = error_trace
                    return Response(error_response, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

            else:
                return Response({"error": "Invalid businessType"}, status=status.HTTP_400_BAD_REQUEST)

        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


def _get_business_context_business(request, business_id):
    """Get business data and validation for business owner view."""
    from kirazee_app.models import Business
    
    if not business_id:
        raise ValueError("business_id is required")
    
    # Get business details (include closed businesses for owner)
    business = Business.objects.get(business_id=business_id)
    if business.status == 0:
        raise ValueError("Business is currently closed")
    
    # Serialize business data
    business_data = BusinessSerializer(business, context={'request': request}).data
    business_data['is_business_open'] = bool(getattr(business, 'status', True))
    
    # Calculate business rating
    rating_data = calculate_business_rating(business_id)
    business_data.update(rating_data)
    
    return business, business_data


def _parse_items_query_params_business(request):
    """Parse query parameters for items filtering."""
    # Check if page parameter is provided - if not, return None to get all items
    page_param = request.query_params.get('page')
    page_size_param = request.query_params.get('page_size')
    
    return {
        'search': request.query_params.get('search', ''),
        'category': request.query_params.get('category'),
        'min_price': request.query_params.get('min_price'),
        'max_price': request.query_params.get('max_price'),
        'ordering': request.query_params.get('ordering', 'item_name'),
        'min_age': request.query_params.get('min_age'),
        'max_age': request.query_params.get('max_age'),
        'pack': request.query_params.get('pack'),
        'page': page_param if page_param is not None else None,
        'page_size': page_size_param if page_size_param is not None else None,
        'paginate': page_param is not None  # Flag to indicate if pagination should be used
    }


def _service_items_r02_business(request, business, business_id, qp):
    """Service for R02 (Restaurant) items with variants for business owner."""
    from rest_framework.pagination import PageNumberPagination
    from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
    from django.db.models import F, ExpressionWrapper, DecimalField
    
    # Base queryset - filter out items with status = False
    items = MenuItems.objects.filter(status=True)
    if business_id:
        items = items.filter(business_id=business_id)
    
    # Apply filters
    if qp['search']:
        items = items.filter(item_name__icontains=qp['search'])
    if qp['category']:
        items = items.filter(item_category=qp['category'])
    if qp['min_price']:
        items = items.filter(selling_price__gte=qp['min_price'])
    if qp['max_price']:
        items = items.filter(selling_price__lte=qp['max_price'])
    
    # Apply ordering
    items = items.order_by(qp['ordering'])
    
    # Check if pagination should be used
    if qp['paginate']:
        # Setup pagination
        paginator = PageNumberPagination()
        paginator.page_size = int(qp['page_size']) if qp['page_size'] else 10
        
        # Paginate
        paginated_items = paginator.paginate_queryset(items, request)
        
        # Process items with variants and offer metadata
        items_data = []
        for item in paginated_items:
            item_data = MenuItemsWithVariantsSerializer(item, context={'request': request}).data
            item_data['rating'] = 4.0
            item_data['rating_count'] = 0
            if 'gst' not in item_data or item_data['gst'] is None:
                item_data['gst'] = str(item.gst) if item.gst else "0.00"

            # Calculate parent quantity as sum of all variant stock_qty
            total_quantity = 0
            if 'variants' in item_data and item_data['variants']:
                for variant in item_data['variants']:
                    stock_qty = variant.get('stock_qty', 0)
                    if stock_qty is not None:
                        total_quantity += int(stock_qty)
            item_data['quantity'] = total_quantity

            # Add offer metadata
            try:
                oc = Decimal(str(item_data.get('original_cost') or '0'))
                sp = Decimal(str(item_data.get('selling_price') or '0'))
            except Exception:
                oc = Decimal('0')
                sp = Decimal('0')

            if oc > 0:
                diff = oc - sp
                if diff > 0:
                    percent = (diff / oc * Decimal(100))
                    percent_display = int(percent.quantize(Decimal('1'), rounding=ROUND_HALF_UP))
                    diff_display = int(diff.quantize(Decimal('1'), rounding=ROUND_HALF_UP))
                    if percent > Decimal('10'):
                        badge_text = f"{percent_display}% off"
                        badge_type = 'percent'
                    else:
                        badge_text = f"₹{diff_display} off"
                        badge_type = 'rupee'
                    item_data.update({
                        'diff_amount': str(diff.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)),
                        'percent': str(percent.quantize(Decimal('0.1'), rounding=ROUND_HALF_UP)),
                        'percent_display': percent_display,
                        'diff_display': diff_display,
                        'badge_text': badge_text,
                        'badge_type': badge_type,
                        'is_featured_offer': False,
                        'discount_percentage': percent_display
                    })
                else:
                    item_data.update({
                        'diff_amount': "0.00", 'percent': "0.0", 'percent_display': 0,
                        'diff_display': 0, 'badge_text': None, 'badge_type': None,
                        'is_featured_offer': False, 'discount_percentage': 0
                    })
            else:
                item_data.update({
                    'diff_amount': "0.00", 'percent': "0.0", 'percent_display': 0,
                    'diff_display': 0, 'badge_text': None, 'badge_type': None,
                    'is_featured_offer': False, 'discount_percentage': 0
                })

            items_data.append(item_data)
        
        # Process top offers
        top_offers = _process_top_offers_r02_business(request, business_id)
        
        return paginator.get_paginated_response({
            'top_offers': top_offers,
            'items': items_data,
            'total_items': items.count(),
            'total_pages': paginator.page.paginator.num_pages,
            'current_page': paginator.page.number,
            'page_size': paginator.page_size
        })
    else:
        # No pagination - return all items
        items_data = []
        for item in items:
            item_data = MenuItemsWithVariantsSerializer(item, context={'request': request}).data
            item_data['rating'] = 4.0
            item_data['rating_count'] = 0
            if 'gst' not in item_data or item_data['gst'] is None:
                item_data['gst'] = str(item.gst) if item.gst else "0.00"

            # Calculate parent quantity as sum of all variant stock_qty
            total_quantity = 0
            if 'variants' in item_data and item_data['variants']:
                for variant in item_data['variants']:
                    stock_qty = variant.get('stock_qty', 0)
                    if stock_qty is not None:
                        total_quantity += int(stock_qty)
            item_data['quantity'] = total_quantity

            # Add offer metadata
            try:
                oc = Decimal(str(item_data.get('original_cost') or '0'))
                sp = Decimal(str(item_data.get('selling_price') or '0'))
            except Exception:
                oc = Decimal('0')
                sp = Decimal('0')

            if oc > 0:
                diff = oc - sp
                if diff > 0:
                    percent = (diff / oc * Decimal(100))
                    percent_display = int(percent.quantize(Decimal('1'), rounding=ROUND_HALF_UP))
                    diff_display = int(diff.quantize(Decimal('1'), rounding=ROUND_HALF_UP))
                    if percent > Decimal('10'):
                        badge_text = f"{percent_display}% off"
                        badge_type = 'percent'
                    else:
                        badge_text = f"₹{diff_display} off"
                        badge_type = 'rupee'
                    item_data.update({
                        'diff_amount': str(diff.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)),
                        'percent': str(percent.quantize(Decimal('0.1'), rounding=ROUND_HALF_UP)),
                        'percent_display': percent_display,
                        'diff_display': diff_display,
                        'badge_text': badge_text,
                        'badge_type': badge_type,
                        'is_featured_offer': False,
                        'discount_percentage': percent_display
                    })
                else:
                    item_data.update({
                        'diff_amount': "0.00", 'percent': "0.0", 'percent_display': 0,
                        'diff_display': 0, 'badge_text': None, 'badge_type': None,
                        'is_featured_offer': False, 'discount_percentage': 0
                    })
            else:
                item_data.update({
                    'diff_amount': "0.00", 'percent': "0.0", 'percent_display': 0,
                    'diff_display': 0, 'badge_text': None, 'badge_type': None,
                    'is_featured_offer': False, 'discount_percentage': 0
                })

            items_data.append(item_data)
        
        # Process top offers
        top_offers = _process_top_offers_r02_business(request, business_id)
        
        return Response({
            'top_offers': top_offers,
            'items': items_data,
            'total_items': items.count(),
            'total_pages': 1,
            'current_page': 1,
            'page_size': items.count(),
            'paginated': False
        })


def _process_top_offers_r02_business(request, business_id):
    """Process top offers for R02 items with variants."""
    from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
    from django.db.models import F, ExpressionWrapper, DecimalField
    from django.db import connection
    
    LIMIT_OFFERS = 6
    offer_qs = (
        MenuItems.objects.filter(
            is_active=True, status=True, business_id=business_id,
            original_cost__isnull=False, selling_price__isnull=False, original_cost__gt=0,
        )
        .annotate(
            diff_amount=ExpressionWrapper(
                F('original_cost') - F('selling_price'),
                output_field=DecimalField(max_digits=10, decimal_places=2),
            )
        )
        .filter(diff_amount__gt=0)
    )
    candidates = list(offer_qs[:200])
    
    processed = []
    for it in candidates:
        try:
            oc = Decimal(str(it.original_cost or '0'))
            sp = Decimal(str(it.selling_price or '0'))
        except InvalidOperation:
            continue
        if oc <= 0 or (oc - sp) <= 0:
            continue
            
        percent = (oc - sp) / oc * Decimal(100)
        percent_display = int(percent.quantize(Decimal('1'), rounding=ROUND_HALF_UP))
        diff_display = int((oc - sp).quantize(Decimal('1'), rounding=ROUND_HALF_UP))
        
        if percent > Decimal('10'):
            badge_text = f"{percent_display}% off"
            badge_type = 'percent'
        else:
            badge_text = f"₹{diff_display} off"
            badge_type = 'rupee'
        
        item_data = MenuItemsWithVariantsSerializer(it, context={'request': request}).data
        item_data.update({
            'diff_amount': str((oc - sp).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)),
            'percent': str(percent.quantize(Decimal('0.1'), rounding=ROUND_HALF_UP)),
            'percent_display': percent_display,
            'diff_display': diff_display,
            'badge_text': badge_text,
            'badge_type': badge_type,
            'is_featured_offer': False,
        })
        
        # Calculate parent quantity as sum of all variant stock_qty
        total_quantity = 0
        if 'variants' in item_data and item_data['variants']:
            for variant in item_data['variants']:
                stock_qty = variant.get('stock_qty', 0)
                if stock_qty is not None:
                    total_quantity += int(stock_qty)
        item_data['quantity'] = total_quantity
        
        processed.append(item_data)
    
    processed.sort(key=lambda x: (-float(x['percent']), float(x['selling_price']) if x['selling_price'] else 0))
    return processed[:LIMIT_OFFERS]


def _service_items_r01_business(request, business, business_id, qp):
    """Service for R01 (Grocery) items with variants for business owner."""
    from rest_framework.pagination import PageNumberPagination
    from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
    from django.db import connection
    
    # Build base query
    base_query = """
        SELECT 
            gp.product_id as item_id, gp.product_name as item_name, gp.description,
            gp.main_image as item_image, 
            gp.category_id as category_id, gc.category_name as item_category,
            gp.sub_category_id as sub_category_id, gcs.category_name as sub_category_name,
            gp.sub_category as item_type, gp.base_price as selling_price, gp.base_price as original_cost, 
            0 as gst, 0 as charges, 0 as stock, gp.is_visible as is_active, gp.is_visible as status,
            gp.rating, gp.created_at, gp.item_placed_at
        FROM Groceries_Products gp
        LEFT JOIN universal_Categories gc ON gp.category_id = gc.category_id
        LEFT JOIN universal_Categories gcs ON gp.sub_category_id = gcs.category_id
        WHERE 1=1
    """
    params = []
    
    # Add filters
    if business_id:
        base_query += " AND gp.business_id = %s"
        params.append(business_id)
    if qp['search']:
        base_query += " AND gp.product_name LIKE %s"
        params.append(f"%{qp['search']}%")
    if qp['min_age']:
        base_query += " AND gpv.min_age >= %s"
        params.append(qp['min_age'])
    if qp['max_age']:
        base_query += " AND gpv.max_age <= %s"
        params.append(qp['max_age'])
    if qp['pack']:
        base_query += " AND (gpv.pack LIKE %s OR gpv.attributes->>'$.pack' LIKE %s)"
        params.extend([f"%{qp['pack']}%", f"%{qp['pack']}%"])
    if qp['category']:
        base_query += " AND gc.category_name = %s"
        params.append(qp['category'])
    
    # Filter out items with status = 0 for R01 (Grocery products)
    base_query += " AND gp.is_visible = 1"
    
    # Handle price filters
    if qp['min_price'] or qp['max_price']:
        return Response({"error": "Price filtering not supported for grocery products"}, status=status.HTTP_400_BAD_REQUEST)
    
    # Apply ordering
    ordering_map = {'product_name': 'item_name', 'selling_price': 'selling_price', 'created_at': 'created_at'}
    order_field = ordering_map.get(qp['ordering'].lstrip('-'), 'item_name')
    base_query += f" ORDER BY {order_field} {'DESC' if qp['ordering'].startswith('-') else 'ASC'}"
    
    # Execute query
    with connection.cursor() as cursor:
        cursor.execute(base_query, params)
        rows = cursor.fetchall()
    
    # Process items with variants
    items_data = []
    for row in rows:
        # row indices: 0=item_id, 1=item_name, 2=description, 3=item_image, 
        # 4=category_id, 5=item_category, 6=sub_category_id, 7=sub_category_name,
        # 8=item_type, 9=selling_price, 10=original_cost, 11=gst, 12=charges, 13=stock,
        # 14=is_active, 15=status, 16=rating, 17=created_at, 18=item_placed_at
        
        item_dict = {
            'item_id': row[0], 'item_name': row[1], 'description': row[2], 'item_image': row[3],
            'category_id': row[4], 'item_category': row[5],
            'sub_Category_id': row[6], 'sub_category_name': row[8],
            'item_type': row[8],
            'gst': str(row[11]) if row[11] else "0", 'charges': float(row[12]) if row[12] else 0,
            'is_active': bool(row[14]), 'status': bool(row[15]),
            'rating': float(row[16]) if row[16] else 4.0, 'item_placed_at': row[18], 'rating_count': 0
        }
        
        # Process image URL
        item_dict['item_image'] = _process_image_url_business(request, item_dict['item_image'])
        
        # Add variants
        item_dict['variants'] = _get_grocery_variants_business(item_dict['item_id'])
        
        # Add offer metadata
        item_dict.update(_calculate_offer_metadata_business(item_dict))
        items_data.append(item_dict)
    
    # Check if pagination should be used
    if qp['paginate']:
        # Pagination
        paginator = PageNumberPagination()
        paginator.page_size = int(qp['page_size']) if qp['page_size'] else 10
        page = int(qp['page']) if isinstance(qp['page'], str) and qp['page'].isdigit() else (qp['page'] if isinstance(qp['page'], int) else 1)
        start_index = (page - 1) * paginator.page_size
        end_index = start_index + paginator.page_size
        paginated_items = items_data[start_index:end_index]
        
        # Process image URLs for paginated items
        for item in paginated_items:
            item['item_image'] = _process_image_url_business(request, item['item_image'])
        
        # Process top offers
        top_offers = _process_top_offers_r01_business(request, rows)
        
        total_items = len(items_data)
        total_pages = (total_items + paginator.page_size - 1) // paginator.page_size
        
        return Response({
            'top_offers': top_offers, 'items': paginated_items, 'total_items': total_items,
            'total_pages': total_pages, 'current_page': page, 'page_size': paginator.page_size,
            'next': page + 1 if page < total_pages else None, 'previous': page - 1 if page > 1 else None,
            'paginated': True
        })
    else:
        # No pagination - return all items
        # Process image URLs for all items
        for item in items_data:
            item['item_image'] = _process_image_url_business(request, item['item_image'])
        
        # Process top offers
        top_offers = _process_top_offers_r01_business(request, rows)
        
        total_items = len(items_data)
        
        return Response({
            'top_offers': top_offers, 'items': items_data, 'total_items': total_items,
            'total_pages': 1, 'current_page': 1, 'page_size': total_items,
            'next': None, 'previous': None, 'paginated': False
        })


def _service_items_r08_business(request, business, business_id, qp):
    """Service for R08 (Fashion) items for business owner."""
    from rest_framework.pagination import PageNumberPagination
    from decimal import Decimal
    from django.db import connection
    
    # Build query for fashion products
    base_query = """
        SELECT fp.product_id as item_id, fp.name as item_name, fp.description, fp.main_image as item_image,
               uc.category_name as item_category, uc.parent_id as parent_category_id,
               ucp.category_name as parent_category_name, fp.subcategory as item_type,
               COALESCE(fpv.selling_price, 0) as selling_price, COALESCE(fpv.original_cost, 0) as original_cost,
               COALESCE(fp.gst_rate_default, 0) as gst, COALESCE(fpv.charges, 0) as charges,
               COALESCE(fpv.stock, 0) as stock, COALESCE(fpv.is_active, 1) as is_active,
               COALESCE(fpv.is_active, 1) as status, fp.rating, fp.created_at, fp.item_placed_at
        FROM fashion_products fp
        LEFT JOIN universal_Categories uc ON fp.category_id = uc.category_id
        LEFT JOIN universal_Categories ucp ON ucp.category_id = uc.parent_id
        LEFT JOIN fashion_product_variants fpv ON fp.product_id = fpv.product_id
        WHERE 1=1
    """
    params = []
    
    # Add filters
    if business_id:
        base_query += " AND fp.business_id = %s"
        params.append(business_id)
    if qp['search']:
        base_query += " AND fp.name LIKE %s"
        params.append(f"%{qp['search']}%")
    if qp['min_age']:
        base_query += " AND fpv.min_age >= %s"
        params.append(qp['min_age'])
    if qp['max_age']:
        base_query += " AND fpv.max_age <= %s"
        params.append(qp['max_age'])
    if qp['pack']:
        base_query += " AND fp.pack LIKE %s"
        params.append(f"%{qp['pack']}%")
    if qp['category']:
        base_query += " AND uc.category_name = %s"
        params.append(qp['category'])
    
    # Filter out items with status = false for R08 (Fashion products)
    base_query += " AND COALESCE(fpv.is_active, 1) = 1"
    
    base_query += " ORDER BY fp.name ASC"
    
    # Execute query
    with connection.cursor() as cursor:
        cursor.execute(base_query, params)
        rows = cursor.fetchall()
    
    # Process results
    items_data = []
    for row in rows:
        item_dict = {
            'item_id': row[0], 'item_name': row[1], 'description': row[2], 'item_image': row[3],
            'item_category': row[4], 'parent_category_id': row[5], 'parent_category_name': row[6],
            'item_type': row[7],
            'gst': str(row[10]) if row[10] else "0", 'charges': float(row[11]) if row[11] else 0,
            'stock': row[12] or 0, 'is_active': bool(row[13]), 'status': bool(row[14]),
            'rating': float(row[15]) if row[15] else 4.0, 'item_placed_at': row[17], 'rating_count': 0
        }
        
        # Process image URL
        item_dict['item_image'] = _process_image_url_business(request, item_dict['item_image'])
        
        # Add variants
        item_dict['variants'] = _get_fashion_variants_business(item_dict['item_id'])
        
        items_data.append(item_dict)
    
    # Check if pagination should be used
    if qp['paginate']:
        # Pagination
        paginator = PageNumberPagination()
        paginator.page_size = int(qp['page_size']) if qp['page_size'] else 10
        page = int(qp['page']) if isinstance(qp['page'], str) and qp['page'].isdigit() else (qp['page'] if isinstance(qp['page'], int) else 1)
        start_index = (page - 1) * paginator.page_size
        end_index = start_index + paginator.page_size
        paginated_items = items_data[start_index:end_index]
        
        total_items = len(items_data)
        total_pages = (total_items + paginator.page_size - 1) // paginator.page_size
        
        return Response({
            'items': paginated_items, 'total_items': total_items, 'total_pages': total_pages,
            'current_page': page, 'page_size': paginator.page_size, 'paginated': True
        })
    else:
        # No pagination - return all items
        total_items = len(items_data)
        
        return Response({
            'items': items_data, 'total_items': total_items, 'total_pages': 1,
            'current_page': 1, 'page_size': total_items, 'paginated': False
        })


# Helper functions for business services
def _process_image_url_business(request, item_image):
    """Process image URL for consistent format - returns S3 URL."""
    if not item_image:
        return None
    
    # Convert to string if it's a FileField
    if hasattr(item_image, 'name'):
        item_image = item_image.name
    else:
        item_image = str(item_image)
    
    # If it's already a complete URL, return as is (with space encoding)
    if item_image.startswith('http://') or item_image.startswith('https://'):
        return item_image.replace(' ', '%20')
    
    # Otherwise, build S3 URL
    return build_s3_file_url(item_image)


def _get_grocery_variants_business(product_id):
    """Get variants for grocery product."""
    try:
        from consumer.gro_models import GroceriesProductVariants
        from django.db import models
        # Convert product_id to integer if it's a string
        product_id_int = int(product_id) if isinstance(product_id, str) else product_id
        
        variants = GroceriesProductVariants.objects.filter(
            product_id=product_id_int
        ).filter(
            # Only include active variants (matching consumer service logic)
            models.Q(is_active=True) | models.Q(is_active__isnull=True)
        ).values(
            'variant_id', 'sku', 'barcode', 'net_weight', 'net_weight_unit', 'size',
            'original_cost', 'selling_price', 'charges', 'gst', 'stock',
            'mfg_date', 'expiry_date', 'is_active', 'created_at', 'updated_at',
            'color', 'gender', 'age', 'material', 'attributes', 'pack',
            'is_visible_counter', 'price_override', 'min_age', 'max_age', 'dimension'
        )
        
        variants_list = list(variants)
        
        # Process variants to match consumer service format
        for variant in variants_list:
            # Handle size field (could be JSON or string)
            import json as _json
            def _try_json(val):
                if val is None:
                    return None
                if isinstance(val, (dict, list)):
                    return val
                if isinstance(val, str):
                    try:
                        return _json.loads(val)
                    except Exception:
                        return val
                return val
            
            # Map fields to match consumer service format
            variant['size_label'] = _try_json(variant.pop('size', ''))
            variant['stock_qty'] = variant.pop('stock', 0)
            variant['mrp'] = variant.get('selling_price', 0)  # Use selling_price as MRP
            
            # Can add to cart only if variant is active AND has stock > 0
            variant_is_active = variant.get('is_active', True)
            variant_stock = variant.get('stock_qty', 0)
            variant['can_add_to_cart'] = variant_is_active and variant_stock > 0
            
            # Add stock messages (matching consumer service)
            if variant_stock > 0:
                variant['stock_message'] = 'In stock'
                variant['stock_status'] = 'in_stock'
            else:
                variant['stock_message'] = 'Out of stock'
                variant['stock_status'] = 'out_of_stock'
        
        return variants_list
    except Exception as e:
        print(f"Error fetching variants for product {product_id}: {e}")
        return []


def _get_fashion_variants_business(product_id):
    """Get variants for fashion product."""
    try:
        from consumer.gro_models import FashionProductVariant
        # Convert product_id to integer if it's a string
        product_id_int = int(product_id) if isinstance(product_id, str) else product_id
        
        variants = FashionProductVariant.objects.filter(
            product_id=product_id_int
        ).values(
            'variant_id', 'size', 'sku', 'selling_price', 'original_cost',
            'stock', 'charges', 'gst', 'is_active',
            'created_at', 'updated_at'
        )
        
        variants_list = list(variants)
        
        # Convert size to size_label for consistency and add can_add_to_cart
        for variant in variants_list:
            variant['size_label'] = variant.pop('size', '')
            variant['stock_qty'] = variant.pop('stock', 0)
            variant['mrp'] = variant.get('selling_price', 0)  # Use selling_price as MRP
            # Can add to cart only if variant is active AND has stock > 0
            variant_is_active = variant.get('is_active', True)
            variant_stock = variant.get('stock_qty', 0)
            variant['can_add_to_cart'] = variant_is_active and variant_stock > 0
        
        return variants_list
    except Exception as e:
        print(f"Error fetching fashion variants for product {product_id}: {e}")
        return []


def _calculate_offer_metadata_business(item_dict):
    """Calculate offer metadata for an item."""
    from decimal import Decimal, ROUND_HALF_UP
    
    try:
        oc = Decimal(str(item_dict.get('original_cost', 0)))
        sp = Decimal(str(item_dict.get('selling_price', 0)))
    except Exception:
        oc = Decimal('0')
        sp = Decimal('0')
    
    if oc > 0:
        diff = oc - sp
        if diff > 0:
            percent = (diff / oc * Decimal(100))
            percent_display = int(percent.quantize(Decimal('1'), rounding=ROUND_HALF_UP))
            diff_display = int(diff.quantize(Decimal('1'), rounding=ROUND_HALF_UP))
            if percent > Decimal('10'):
                badge_text = f"{percent_display}% off"
                badge_type = 'percent'
            else:
                badge_text = f"₹{diff_display} off"
                badge_type = 'rupee'
            return {
                'diff_amount': str(diff.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)),
                'percent': str(percent.quantize(Decimal('0.1'), rounding=ROUND_HALF_UP)),
                'percent_display': percent_display, 'diff_display': diff_display,
                'badge_text': badge_text, 'badge_type': badge_type,
                'is_featured_offer': False, 'discount_percentage': percent_display
            }
    
    return {
        'diff_amount': "0.00", 'percent': "0.0", 'percent_display': 0, 'diff_display': 0,
        'badge_text': None, 'badge_type': None, 'is_featured_offer': False, 'discount_percentage': 0
    }


def _process_top_offers_r01_business(request, rows):
    """Process top offers for R01 items."""
    from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
    
    LIMIT_OFFERS = 6
    top_candidates = []
    
    for row in rows:
        try:
            oc = Decimal(str(row[9] or '0'))
            sp = Decimal(str(row[8] or '0'))
        except InvalidOperation:
            continue
        if oc <= 0 or (oc - sp) <= 0:
            continue
            
        percent = (oc - sp) / oc * Decimal(100)
        percent_display = int(percent.quantize(Decimal('1'), rounding=ROUND_HALF_UP))
        diff_display = int((oc - sp).quantize(Decimal('1'), rounding=ROUND_HALF_UP))
        
        if percent > Decimal('10'):
            badge_text = f"{percent_display}% off"
            badge_type = 'percent'
        else:
            badge_text = f"₹{diff_display} off"
            badge_type = 'rupee'
        
        final_url = _process_image_url_business(request, row[3])
        candidate = {
            'item_id': row[0], 'item_name': row[1], 'item_image': final_url,
            'selling_price': str(sp), 'original_cost': str(oc),
            'diff_amount': str((oc - sp).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)),
            'percent': str(percent.quantize(Decimal('0.1'), rounding=ROUND_HALF_UP)),
            'percent_display': percent_display, 'diff_display': diff_display,
            'badge_text': badge_text, 'badge_type': badge_type, 'is_featured_offer': False,
            'item_category': row[4], 'parent_category_id': row[5], 'parent_category_name': row[6],
            'gst': str(row[10]) if row[10] else "0", 'charges': float(row[11]) if row[11] else 0,
            'variants': _get_grocery_variants_business(int(row[0]))  # Convert to int
        }
        top_candidates.append(candidate)
    
    top_candidates.sort(key=lambda x: (-float(x['percent']), float(x['selling_price']) if x['selling_price'] else 0))
    return top_candidates[:LIMIT_OFFERS]


@swagger_auto_schema(methods=['GET', 'POST', 'PUT', 'PATCH', 'DELETE'], tags=['Business'])
@api_view(['GET', 'POST', 'PUT', 'PATCH', 'DELETE'])
def manageCustomizationTemplates(request, template_id=None):
    """
    CRUD for product customization templates.
    Query: ?business_id=...&user_id=...&product_id=...
    """
    business_id = request.query_params.get("business_id")
    user_id = request.query_params.get("user_id")
    product_id = request.query_params.get("product_id")

    if not business_id or not user_id:
        return Response({"error": "business_id and user_id are required"}, status=status.HTTP_400_BAD_REQUEST)

    # Check mapping
    if not BusinessMapping.objects.filter(user_id=user_id, business_id=business_id).exists():
        # Check POS permissions
        is_pos_user, _ = _check_user_permissions(user_id, business_id)
        if not is_pos_user:
            return Response({"error": "Unauthorized access to this business"}, status=status.HTTP_403_FORBIDDEN)

    if request.method == 'GET':
        if template_id:
            template = ProductCustomizationTemplate.objects.filter(id=template_id, business_id=business_id).first()
            if not template: return Response({"error": "Template not found"}, status=status.HTTP_404_NOT_FOUND)
            return Response(ProductCustomizationTemplateSerializer(template).data)
        
        templates = ProductCustomizationTemplate.objects.filter(business_id=business_id)
        return Response(ProductCustomizationTemplateSerializer(templates, many=True).data)

    elif request.method == 'POST':
        data = request.data.copy()
        data['business_id'] = business_id
        
        # Set product_id if provided in query params
        if product_id:
            try:
                data['product_id'] = int(product_id)
            except (ValueError, TypeError):
                return Response({"error": "Invalid product_id format"}, status=status.HTTP_400_BAD_REQUEST)
        
        # Handle file upload for asset_url
        if 'asset_file' in request.FILES:
            asset_file = request.FILES['asset_file']
            print(f"[DEBUG] Customization upload - Original filename: {getattr(asset_file, 'name', 'unknown')}")
            
            # Upload to S3 using helper with UUID
            saved_path = upload_image_to_s3(
                asset_file,
                folder='custom_designs',
                compress=False,  # Assets may not need compression
                use_uuid=True  # Use UUID for secure naming
            )
            
            print(f"[DEBUG] Customization upload - S3 saved_path: {saved_path}")
            
            if saved_path:
                data['asset_url'] = saved_path
                print(f"[DEBUG] Customization upload - Final asset_url: {saved_path}")
            else:
                print(f"[DEBUG] Customization upload - S3 upload FAILED!")
                return Response({"error": "Failed to upload asset to S3"}, status=status.HTTP_400_BAD_REQUEST)
        else:
            print(f"[DEBUG] Customization upload - No file uploaded, using existing asset_url: {data.get('asset_url', 'None')}")
        
        # CRITICAL: Remove any filename-only asset_url to prevent database corruption
        if data.get('asset_url') and not data['asset_url'].startswith('media/'):
            print(f"[DEBUG] Customization upload - DETECTED INVALID asset_url format: {data['asset_url']}")
            return Response({"error": "Invalid asset_url format detected"}, status=status.HTTP_400_BAD_REQUEST)
        
        print(f"[DEBUG] Customization upload - Final data before serializer: {data}")
        
        serializer = ProductCustomizationTemplateSerializer(data=data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    elif request.method == 'PUT':
        if not template_id: return Response({"error": "template_id required"}, status=status.HTTP_400_BAD_REQUEST)
        template = ProductCustomizationTemplate.objects.filter(id=template_id, business_id=business_id).first()
        if not template: return Response({"error": "Template not found"}, status=status.HTTP_404_NOT_FOUND)
        
        data = request.data.copy()
        
        # Set product_id if provided in query params
        if product_id:
            try:
                data['product_id'] = int(product_id)
            except (ValueError, TypeError):
                return Response({"error": "Invalid product_id format"}, status=status.HTTP_400_BAD_REQUEST)
        
        # Handle file upload for asset_url
        if 'asset_file' in request.FILES:
            asset_file = request.FILES['asset_file']
            print(f"[DEBUG] Customization upload - Original filename: {getattr(asset_file, 'name', 'unknown')}")
            
            # Upload to S3 using helper with UUID
            saved_path = upload_image_to_s3(
                asset_file,
                folder='custom_designs',
                compress=False,  # Assets may not need compression
                use_uuid=True  # Use UUID for secure naming
            )
            
            print(f"[DEBUG] Customization upload - S3 saved_path: {saved_path}")
            
            if saved_path:
                data['asset_url'] = saved_path
                print(f"[DEBUG] Customization upload - Final asset_url: {saved_path}")
            else:
                print(f"[DEBUG] Customization upload - S3 upload FAILED!")
                return Response({"error": "Failed to upload asset to S3"}, status=status.HTTP_400_BAD_REQUEST)
        else:
            print(f"[DEBUG] Customization upload - No file uploaded, using existing asset_url: {data.get('asset_url', 'None')}")
        
        # CRITICAL: Remove any filename-only asset_url to prevent database corruption
        if data.get('asset_url') and not data['asset_url'].startswith('media/'):
            print(f"[DEBUG] Customization upload - DETECTED INVALID asset_url format: {data['asset_url']}")
            return Response({"error": "Invalid asset_url format detected"}, status=status.HTTP_400_BAD_REQUEST)
        
        serializer = ProductCustomizationTemplateSerializer(template, data=data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    elif request.method == 'DELETE':
        if not template_id: return Response({"error": "template_id required"}, status=status.HTTP_400_BAD_REQUEST)
        count, _ = ProductCustomizationTemplate.objects.filter(id=template_id, business_id=business_id).update(is_active=False)
        return Response({"message": "Template deactivated" if count else "No template found"})


@swagger_auto_schema(methods=['GET'], tags=['Business'])
@api_view(['GET'])
def list_customizable_items(request):
    """
    Returns a list of items where is_customizable=True, respecting business hierarchy.
    Query: ?business_id=...&user_id=...
    """
    business_id = request.query_params.get('business_id')
    user_id = request.query_params.get('user_id') # Optional user_id check if needed
    
    if not business_id:
        return Response({"error": "business_id is required"}, status=status.HTTP_400_BAD_REQUEST)

    try:
        business = Business.objects.get(business_id=business_id)
        business_type = business.businessType
        
        # Security check (optional but recommended for back-office services)
        if user_id:
            if not BusinessMapping.objects.filter(user_id=user_id, business_id=business_id).exists():
                from .views import _check_user_permissions
                is_pos_user, _ = _check_user_permissions(user_id, business_id)
                if not is_pos_user:
                    return Response({"error": "Unauthorized access to this business"}, status=status.HTTP_403_FORBIDDEN)

        # Resolve hierarchy: if branch, also include products from the master business
        business_ids = [business_id]
        if business.level != 'Master Level' and business.master:
            business_ids.append(business.master)

        items_list = []

        if business_type == 'R02': # Restaurant/Menu
            items = MenuItems.objects.filter(business_id__in=business_ids, is_customizable=True)
            for item in items:
                details_resp = _get_menu_details_logic(request, item.item_id)
                items_list.append({
                    "id": item.item_id,
                    "name": item.item_name,
                    "category": item.item_category,
                    "type": "menu",
                    "is_active": getattr(item, 'is_active', True),
                    "details": details_resp.data if details_resp.status_code == 200 else None
                })

        elif business_type == 'R01': # Grocery
            items = GroceriesProducts.objects.filter(business_id__in=business_ids, is_customizable=True)
            for item in items:
                details_resp = _get_product_details_logic(request, item.product_id)
                items_list.append({
                    "id": item.product_id,
                    "name": item.product_name,
                    "category": item.category.category_name if item.category else None,
                    "type": "grocery",
                    "is_active": getattr(item, 'is_visible', True),
                    "details": details_resp.data if details_resp.status_code == 200 else None
                })

        elif business_type == 'R08': # Fashion
            items = FashionProduct.objects.filter(business_id__in=business_ids, is_customizable=True)
            for item in items:
                details_resp = _get_fashion_details_logic(request, item.product_id)
                items_list.append({
                    "id": item.product_id,
                    "name": item.name,
                    "category": getattr(item, 'category_name', None),
                    "type": "fashion",
                    "is_active": getattr(item, 'is_visible', True),
                    "details": details_resp.data if details_resp.status_code == 200 else None
                })
        else:
            return Response({"error": f"Unsupported business type: {business_type}"}, status=status.HTTP_400_BAD_REQUEST)

        return Response({
            "business_id": business_id,
            "business_type": business_type,
            "count": len(items_list),
            "items": items_list
        })

    except Business.DoesNotExist:
        return Response({"error": "Business not found"}, status=status.HTTP_404_NOT_FOUND)
    except Exception as e:
        return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
