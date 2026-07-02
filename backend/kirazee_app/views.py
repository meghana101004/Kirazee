# your_app/views.py
from django.db.models import Q
from django.db import connection
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.exceptions import ValidationError
from django.db import transaction  # Import transaction
from django.utils import timezone
from datetime import timedelta
from django.conf import settings
import os
from PIL import Image
import json
from types import SimpleNamespace
from typing import Any, Optional
from drf_yasg.utils import swagger_auto_schema
from drf_yasg import openapi
from .models import (
    Registration,
    Otp,
    UserAddress,
    Business,
    BusinessType,
    BusinessMapping,
    BusinessOwnerDetails,
    NavigationItem,
    CompanyRegistration,
    CompanyOffers,
)
from .serializers import (
    RegistrationSerializer, 
    UserAddressSerializer, 
    NavigationItemSerializer,
    CompanyRegistrationSerializer,
    CompanyRegistrationUpdateSerializer,
    CompanyVerificationSerializer,
    CompanyOffersSerializer,
    CompanyEmployeeSerializer,
    CompanyOrderSerializer,
    CompanyOrderListSerializer,
)
from .utils import generate_otp, send_otp_email, send_otp_dual_channel
from delivery.image_utils import build_s3_file_url
from rest_framework import status
from django.shortcuts import render

def sitemap(request):
    return render(request, 'flowchat.html') 

def docmap(request):
    return render(request, 'docmap.html') 
# Helper to build absolute profile URL with default fallback

def splash_screen(request):
    return render(request, 'Kirazee_splash_screen.html') 

from django.core.files.storage import default_storage

def build_profile_url(request, user: Registration):
    """Build S3 URL for user profile image."""
    path = getattr(user, 'profileUrl', None)
    if not path:
        path = "default_images/user.png"
    return build_s3_file_url(path)

def build_business_logo_url(request, logo: Business):
    """Build S3 URL for business logo."""
    img_field = getattr(logo, 'logo', None)
    if img_field and hasattr(img_field, 'url'):
        try:
            return img_field.url
        except Exception:
            pass
    path = str(img_field) if img_field else None
    if not path:
        path = "business_logos/default_logo.jpeg"
    return build_s3_file_url(path)

def build_business_banner_url(request, banner: Business):
    """Build S3 URL for business banner."""
    img_field = getattr(banner, 'banner', None)
    if img_field and hasattr(img_field, 'url'):
        try:
            return img_field.url
        except Exception:
            pass
    path = str(img_field) if img_field else None
    if not path:
        path = "business_banners/default_banners.jpg"
    return build_s3_file_url(path)

class RegistrationAPIView(APIView):
    @swagger_auto_schema(
        tags=['Core'],
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            properties={
                'firstName': openapi.Schema(type=openapi.TYPE_STRING, description='User first name'),
                'lastName': openapi.Schema(type=openapi.TYPE_STRING, description='User last name'),
                'mobileNumber': openapi.Schema(type=openapi.TYPE_STRING, description='Mobile number', required=['mobileNumber']),
                'emailID': openapi.Schema(type=openapi.TYPE_STRING, description='Email address'),
                'countryCode': openapi.Schema(type=openapi.TYPE_STRING, description='Country code'),
                'tokenID': openapi.Schema(type=openapi.TYPE_STRING, description='Device token ID'),
                'uuid': openapi.Schema(type=openapi.TYPE_STRING, description='Device UUID'),
                'os': openapi.Schema(type=openapi.TYPE_STRING, description='Operating system'),
                'dob': openapi.Schema(type=openapi.TYPE_STRING, format='date', description='Date of birth'),
            },
            required=['mobileNumber']
        ),
        responses={
            200: openapi.Response(
                description='Registration updated for existing user',
                examples={
                    'application/json': {
                        'status': 'success',
                        'otp_sent_status': 1,
                        'message': 'Registration updated successful. An OTP has been sent to your email and WhatsApp for verification.',
                        'data': {
                            'user_id': 'string',
                            'emailID': 'string',
                            'user_mode': 'string'
                        }
                    }
                }
            ),
            201: openapi.Response(
                description='New user registration successful',
                examples={
                    'application/json': {
                        'status': 'success',
                        'otp_sent_status': 1,
                        'message': 'Registration successful. An OTP has been sent to your email and WhatsApp for verification.',
                        'data': {
                            'user_id': 'string',
                            'emailID': 'string',
                            'user_mode': 'string'
                        }
                    }
                }
            ),
            400: openapi.Response(
                description='Bad request - validation failed',
                examples={
                    'application/json': {
                        'field_name': ['Error message']
                    }
                }
            )
        }
    )
    @transaction.atomic  # Ensures all database operations succeed or none do
    def post(self, request, *args, **kwargs):
        mobile = request.data.get('mobileNumber')
        email = request.data.get('emailID')

        unverified_user = Registration.objects.filter(mobileNumber=mobile, is_verified=False).first()

        if unverified_user and unverified_user.emailID != email:
            # SCENARIO: MISTYPED EMAIL FOUND.

            # THE FIX: First, delete the old OTP record linked to the mobile number.
            # This unlocks the parent 'registrations' record for updates.
            Otp.objects.filter(mobileNumber=unverified_user).delete()

            # Now, you can safely update the user's details, including the email.
            unverified_user.firstName = request.data.get('firstName', unverified_user.firstName)
            unverified_user.lastName = request.data.get('lastName', unverified_user.lastName)
            unverified_user.countryCode = request.data.get('countryCode', unverified_user.countryCode)
            unverified_user.emailID = email
            unverified_user.dob = request.data.get('dob', unverified_user.dob)
            unverified_user.tokenID = request.data.get('tokenID', unverified_user.tokenID)
            unverified_user.uuid = request.data.get('uuid', unverified_user.uuid)
            unverified_user.os = request.data.get('os', unverified_user.os)
            unverified_user.mobileNumber = request.data.get('mobileNumber', unverified_user.mobileNumber)
            unverified_user.save()
            registration = unverified_user

            # Finally, create a brand new OTP record linked to the mobile number.
            otp_code = generate_otp()
            # --- CORRECTED OTP CREATION FOR UPDATE ---
            Otp.objects.create(
                mobileNumber=registration,
                tokenID=registration.tokenID,
                emailID=registration.emailID,
                code=otp_code
            )
            # Send OTP via both Email and WhatsApp
            user_name = f"{registration.firstName} {registration.lastName}"
            send_results = send_otp_dual_channel(
                registration.emailID, 
                registration.mobileNumber, 
                otp_code, 
                "REGISTRATION_OTP", 
                user_name
            )
            # print(f"OTP sending results for {registration.emailID}: {send_results}")
            # Return the success response
            response_data = {
                "status": "success",
                "otp_sent_status": 1,
                "message": "Registration updated successful. An OTP has been sent to your email and WhatsApp for verification.",
                "data": {
                    "user_id": registration.user_id,
                    "emailID": registration.emailID,
                    "user_mode": registration.user_mode
                }
            }
            return Response(response_data, status=status.HTTP_200_OK)

        # --- Fallback for all other cases (new user, etc.) ---
        try:
            serializer = RegistrationSerializer(data=request.data)
            serializer.is_valid(raise_exception=True)
            registration = serializer.save()

            # Automatic tag assignment based on email domain
            if registration.emailID:
                try:
                    from consumer.models import UserTags, DomainTagMapping
                    from datetime import datetime
                    email_domain = registration.emailID.split('@')[-1].lower()
                    
                    # Get domain to tag mapping from database
                    domain_mapping = DomainTagMapping.objects.filter(
                        domain=email_domain,
                        is_active=True
                    ).first()
                    
                    if domain_mapping:
                        # Calculate expiry based on tag type
                        expires_at = None
                        if 'student' in domain_mapping.tag.lower():
                            # Students typically graduate after 4-5 years
                            expires_at = datetime.now().replace(year=datetime.now().year + 5)
                        elif 'employee' in domain_mapping.tag.lower():
                            # Employees don't expire unless they leave
                            expires_at = None
                        
                        UserTags.objects.get_or_create(
                            user_id=registration,
                            tag=domain_mapping.tag,
                            defaults={
                                'expires_at': expires_at,
                                'is_active': True
                            }
                        )
                except (IndexError, AttributeError):
                    pass  # Skip if email format is invalid

            otp_code = generate_otp()
            # This part now works correctly because the model is fixed
            Otp.objects.create(
                mobileNumber=registration,
                tokenID=registration.tokenID,
                emailID=registration.emailID,
                code=otp_code
            )
            # Send OTP via both Email and WhatsApp
            user_name = f"{registration.firstName} {registration.lastName}"
            send_results = send_otp_dual_channel(
                registration.emailID, 
                registration.mobileNumber, 
                otp_code, 
                "REGISTRATION_OTP", 
                user_name
            )
            # print(f"OTP sending results for {registration.emailID}: {send_results}")
            response_data = {
                "status": "success",
                "otp_sent_status": 1,
                "message": "Registration successful. An OTP has been sent to your email and WhatsApp for verification.",
                "data": {
                    "user_id": registration.user_id,
                    "emailID": registration.emailID,
                    "user_mode": registration.user_mode
                }
            }
            return Response(response_data, status=status.HTTP_201_CREATED)

        except ValidationError as e:
            return Response(e.detail, status=status.HTTP_400_BAD_REQUEST)

class OtpVerificationAPIView(APIView):
    """
    Verifies the OTP sent to a user.
    """
    @swagger_auto_schema(
        tags=['Core'],
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            properties={
                'mobile': openapi.Schema(type=openapi.TYPE_STRING, description='Mobile number for OTP verification', required=['mobile']),
                'otp': openapi.Schema(type=openapi.TYPE_STRING, description='OTP code to verify', required=['otp']),
            },
            required=['mobile', 'otp']
        ),
        responses={
            200: openapi.Response(
                description='OTP verification successful',
                examples={
                    'application/json': {
                        'verification_status': True,
                        'message': 'Verification Successfull',
                        'user_details': {
                            'user_id': 'string',
                            'firstName': 'string',
                            'lastName': 'string',
                            'displayName': 'string',
                            'mobileNumber': 'string',
                            'emailID': 'string',
                            'tokenID': 'string',
                            'is_verified': True,
                            'is_active': True,
                            'user_mode': 'string',
                            'profileUrl': 'string'
                        }
                    }
                }
            ),
            400: openapi.Response(
                description='Bad request - missing or invalid parameters',
                examples={
                    'application/json': {
                        'message': 'Mobile number and OTP are required.'
                    }
                }
            ),
            404: openapi.Response(
                description='User not found',
                examples={
                    'application/json': {
                        'message': 'User with mobile number X not found.'
                    }
                }
            )
        }
    )
    def post(self, request, *args, **kwargs):
        mobile = request.data.get('mobile')
        otp_code = request.data.get('otp')

        # Accept default OTP for development testing
        if otp_code == "565458":
            try:
                user = Registration.objects.get(mobileNumber=mobile)
                if not user.is_verified:
                    user.is_verified = True
                    user.save()
                
                return Response({
                    "verification_status": True,
                    "message": "Development OTP verification successful",
                    "user_details": {
                        "user_id": user.user_id,
                        "firstName": user.firstName,
                        "lastName": user.lastName,
                        "displayName": f"{user.firstName}{user.lastName}",
                        "mobileNumber": user.mobileNumber,
                        "emailID": user.emailID,
                        "tokenID": user.tokenID,
                        "dob": user.dob,
                        "is_verified": user.is_verified,
                        "is_active": user.is_active,
                        "user_mode": user.user_mode,
                        "status": user.status,
                        "profileUrl": build_profile_url(request, user),
                        "uuid": user.uuid,
                        "os": user.os,
                        "whichapp": user.whichapp,
                        "created_at": user.created_at,
                        "updated_at": user.updated_at
                    }
                }, status=status.HTTP_200_OK)
            except Registration.DoesNotExist:
                return Response(
                    {"message": f"User with mobile number {mobile} not found."},
                    status=status.HTTP_404_NOT_FOUND
                )

        # Rest of the original OTP verification logic
        if not mobile or not otp_code:
            return Response(
                {"message": "Mobile number and OTP are required."},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            # Step 1: Find the user by their mobile number
            user = Registration.objects.get(mobileNumber=mobile)

            # Handle case where user is already verified
            if user.is_verified:
                return Response({
                    "message": "User already verified.",
                    "verification_status": True
                }, status=status.HTTP_200_OK)

            # Step 2: Find the latest, unused OTP for this user
            latest_otp = Otp.objects.filter(mobileNumber=user, status=False).latest('created_at')

            # Step 3: Check if the OTP has expired (3-minute limit)
            if timezone.now() - latest_otp.updated_at > timedelta(minutes=3):
                return Response(
                    {"message": "OTP has expired. Please request a new one."},
                    status=status.HTTP_400_BAD_REQUEST
                )

            # Step 4: Check if the submitted OTP is correct
            if latest_otp.code != otp_code:
                return Response(
                    {"message": "Invalid OTP. Please try again."},
                    status=status.HTTP_400_BAD_REQUEST
                )

            # --- Verification Success ---
            # Step 5: Update user and OTP status
            user.is_verified = True
            user.save()

            latest_otp.status = True  # Mark this OTP as used
            latest_otp.save()

            # Step 6: Prepare the detailed success response
            user_details = {
                "user_id": user.user_id,
                "firstName": user.firstName,
                "lastName": user.lastName,
                "displayName": f"{user.firstName}{user.lastName}",
                "mobileNumber": user.mobileNumber,
                "emailID": user.emailID,
                "tokenID": user.tokenID,
                "dob": user.dob,
                "is_verified": user.is_verified,
                "is_active": user.is_active,
                "user_mode": user.user_mode,
                "status": user.status,
                "profileUrl": build_profile_url(request, user),
                "uuid": user.uuid,
                "os": user.os,
                "whichapp": user.whichapp,
                "created_at": user.created_at,
                "updated_at": user.updated_at
            }

            return Response({
                "verification_status": True,
                "message": "Verification Successfull",
                "user_details": user_details
            }, status=status.HTTP_200_OK)

        except Registration.DoesNotExist:
            return Response(
                {"message": f"User with mobile number {mobile} not found."},
                status=status.HTTP_404_NOT_FOUND
            )
        except Otp.DoesNotExist:
            # This occurs if no unused OTPs are found for the user
            return Response(
                {"message": "Invalid OTP or it has already been used. Please request a new one."},
                status=status.HTTP_404_NOT_FOUND
            )

class LoginAPIView(APIView):
    """
    Handles login for registered and verified users by sending an OTP.
    """
    @swagger_auto_schema(
        tags=['Core'],
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            properties={
                'mobile': openapi.Schema(type=openapi.TYPE_STRING, description='Mobile number for login', required=['mobile']),
                'emailID': openapi.Schema(type=openapi.TYPE_STRING, description='Email ID for login', required=['emailID']),
                'tokenID': openapi.Schema(type=openapi.TYPE_STRING, description='Token ID for login', required=['tokenID']),
                'uuid': openapi.Schema(type=openapi.TYPE_STRING, description='UUID for login', required=['uuid']),
            },
            required=['mobile', 'emailID', 'tokenID', 'uuid']
        ),
        responses={
            200: openapi.Response(
                description='Login successful',
                examples={
                    'application/json': {
                        'message': 'OTP generated and sent to your registered email and WhatsApp.',
                        'otp_sent_status': True,
                        'mobile': 'string',
                        'emailID': 'string',
                        'is_verified': True,
                        'is_active': True,
                        'user_mode': 'string',
                    }
                }
            ),
            400: openapi.Response(
                description='Bad request - missing or invalid parameters',
                examples={
                    'application/json': {
                        'message': 'Mobile number or emailID is required.'
                    }
                }
            ),
            404: openapi.Response(
                description='User not found',
                examples={
                    'application/json': {
                        'message': 'User not registered. Please register'
                    }
                }
            )
        }
    )
    def post(self, request, *args, **kwargs):
        mobile = request.data.get('mobile')
        email = request.data.get('emailID')
        token_id = request.data.get('tokenID')
        uuid = request.data.get('uuid')

        if not mobile and not email:
            return Response(
                {"Message": "Mobile number or emailID is required."},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Find the user by either mobile or email
        user_query = Q()
        if mobile:
            user_query |= Q(mobileNumber=mobile)
        if email:
            user_query |= Q(emailID=email)

        user = Registration.objects.filter(user_query).first()

        # Case 1: User does not exist
        if not user:
            return Response(
                {"Message": "User not registered. Please register", "otp_sent_status": False},
                status=status.HTTP_404_NOT_FOUND
            )

        # Case 2: User account is deactivated (status=0)
        if not user.status:
            return Response(
                {"Message": "User deactivated the account. please contact support..!!", "status": 2},
                status=status.HTTP_404_NOT_FOUND
            )

        # Case 3: User exists but has not completed initial verification
        if not user.is_verified:
            return Response(
                {"Message": "Intiated verification process, but not registered yet.", "otp_sent_status": False},
                status=status.HTTP_403_FORBIDDEN
            )

        # Case 4: User is valid. Update device tokens and send OTP.
        user.tokenID = token_id
        user.uuid = uuid
        user.save()

        # --- MODIFIED OTP HANDLING LOGIC ---
        latest_otp = Otp.objects.filter(mobileNumber=user).order_by('-created_at').first()
        new_otp_code = generate_otp()
        user_name = f"{user.firstName} {user.lastName}"

        if latest_otp and not latest_otp.status:
            # If the latest OTP was never used (status=0), update it.
            latest_otp.code = new_otp_code
            # The 'updated_at' field will refresh automatically, resetting the timer.
            latest_otp.save()
            # Send OTP via both Email and WhatsApp
            send_results = send_otp_dual_channel(
                user.emailID, 
                user.mobileNumber, 
                new_otp_code, 
                "LOGIN_OTP", 
                user_name
            )
            # print(f"--- UPDATED OTP for {user.emailID} is: {new_otp_code} ---")
            # print(f"OTP sending results: {send_results}")
        else:
            # If no OTP exists or the last one was used (status=1), create a new one.
            Otp.objects.create(
                mobileNumber=user,
                tokenID=user.tokenID,
                emailID=user.emailID,
                code=new_otp_code
            )
            # Send OTP via both Email and WhatsApp
            # CORRECTED: Removed the auth_token from the call
            send_results = send_otp_dual_channel(
                user.emailID, 
                user.mobileNumber, 
                new_otp_code, 
                "LOGIN_OTP", 
                user_name
            )
            # print(f"--- CREATED new OTP for {user.emailID} is: {new_otp_code} ---")
            # print(f"OTP sending results: {send_results}")
        # --- END OF MODIFICATION ---

        if user.is_active:
            message = "OTP generated and sent to your registered email and WhatsApp. Informing that your account is logged in another device please logout"
        else:
            message = "OTP generated and sent to your registered email and WhatsApp."

        response_data = {
            "message": message,
            "otp_sent_status": True,
            "mobile": user.mobileNumber,
            "emailID": user.emailID,
            "is_verified": user.is_verified,
        }
        return Response(response_data, status=status.HTTP_200_OK)
    
class VerifyLoginOtpAPIView(APIView):
    """
    Verifies the OTP sent during login and returns user details if successful.
    """
    @swagger_auto_schema(
        tags=['Core'],
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            properties={
                'mobile': openapi.Schema(type=openapi.TYPE_STRING, description='Mobile number for login', required=['mobile']),
                'emailID': openapi.Schema(type=openapi.TYPE_STRING, description='Email ID for login', required=['emailID']),
                'otp': openapi.Schema(type=openapi.TYPE_STRING, description='OTP code to verify', required=['otp']),
            },
            required=['mobile', 'emailID', 'otp']
        ),
        responses={
            200: openapi.Response(
                description='Login successful',
                examples={
                    'application/json': {
                        'verification_status': True,
                        'message': 'Verification Successfull',
                        'user_details': {
                            'user_id': 'string',
                            'firstName': 'string',
                            'lastName': 'string',
                            'displayName': 'string',
                            'mobileNumber': 'string',
                            'emailID': 'string',
                            'tokenID': 'string',
                            'is_verified': True,
                            'is_active': True,
                            'user_mode': 'string',
                            'profileUrl': 'string'
                        }
                    }
                }
            ),
            400: openapi.Response(
                description='Bad request - missing or invalid parameters',
                examples={
                    'application/json': {
                        'message': 'Mobile/Email and OTP are required.'
                    }
                }
            ),
            404: openapi.Response(
                description='User not found',
                examples={
                    'application/json': {
                        'message': 'User not found.'
                    }
                }
            )
        }
    )
    def post(self, request, *args, **kwargs):
        mobile = request.data.get('mobile')
        email = request.data.get('emailID')
        otp_code = request.data.get('otp')

        # Accept default OTP for development testing
        if otp_code == "565458":
            user_query = Q()
            if mobile:
                user_query |= Q(mobileNumber=mobile)
            if email:
                user_query |= Q(emailID=email)
                
            user = Registration.objects.filter(user_query).first()


            if not user:
                return Response({"message": "User not found."}, status=status.HTTP_404_NOT_FOUND)
            
            if not user.is_verified:
                user.is_verified = True
                
            if not user.status:
                return Response({"message": "Account is deactivated."}, status=status.HTTP_403_FORBIDDEN)

            user.is_active = True
            user.save()

            return Response({
                "verification_status": True,
                "message": "Development OTP verification successful",
                "user_details": {
                    "user_id": user.user_id,
                    "firstName": user.firstName,
                    "lastName": user.lastName,
                    "displayName": f"{user.firstName}{user.lastName}",
                    "mobileNumber": user.mobileNumber,
                    "emailID": user.emailID,
                    "tokenID": user.tokenID,
                    "dob": user.dob,
                    "is_verified": user.is_verified,
                    "is_active": user.is_active,
                    "user_mode": user.user_mode,
                    "status": user.status,
                    "profileUrl": build_profile_url(request, user),
                    "uuid": user.uuid,
                    "os": user.os,
                    "whichapp": user.whichapp,
                    "created_at": user.created_at,
                    "updated_at": user.updated_at
                }
            }, status=status.HTTP_200_OK)

        # Rest of the original OTP verification logic
        if not (mobile or email) or not otp_code:
            return Response({"message": "Mobile/Email and OTP are required."}, status=status.HTTP_400_BAD_REQUEST)
        
        # Find the user by either mobile or email
        user_query = Q()
        if mobile:
            user_query |= Q(mobileNumber=mobile)
        if email:
            user_query |= Q(emailID=email)
            
        user = Registration.objects.filter(user_query).first()

        if not user:
            return Response({"message": "User not found."}, status=status.HTTP_404_NOT_FOUND)

        try:
            latest_otp = Otp.objects.filter(mobileNumber=user, status=False).latest('created_at')
        except Otp.DoesNotExist:
            return Response({"message": "Invalid OTP or it has already been used."}, status=status.HTTP_400_BAD_REQUEST)

        # Check for OTP expiration
        if timezone.now() - latest_otp.updated_at > timedelta(minutes=3):
            return Response({"message": "OTP has expired. Please request a new one."}, status=status.HTTP_400_BAD_REQUEST)

        # Check if OTP code is correct
        if latest_otp.code != otp_code:
            return Response({"message": "Invalid OTP. Please try again."}, status=status.HTTP_400_BAD_REQUEST)

        # --- Success: Activate user and complete login ---
        user.is_active = True
        user.save()

        latest_otp.status = True # Mark OTP as used
        latest_otp.save()

        user_details = {
            "user_id": user.user_id,
            "firstName": user.firstName,
            "lastName": user.lastName,
            "displayName": f"{user.firstName}{user.lastName}",
            "mobileNumber": user.mobileNumber,
            "emailID": user.emailID,
            "tokenID": user.tokenID,
            "dob": user.dob,
            "is_verified": user.is_verified,
            "is_active": user.is_active,
            "user_mode": user.user_mode,
            "status": user.status,
            "profileUrl": build_profile_url(request, user),
            "uuid": user.uuid,
            "os": user.os,
            "whichapp": user.whichapp,
            "created_at": user.created_at,
            "updated_at": user.updated_at
        }
        
        return Response({
            "verification_status": True,
            "message": "Verification Successfull",
            "user_details": user_details
        }, status=status.HTTP_200_OK)

class LogoutAPIView(APIView):
    """
    Handles user logout by setting their account to inactive.
    Accepts userID as a query parameter.
    """
    @swagger_auto_schema(
        tags=['Core'],
        manual_parameters=[
            openapi.Parameter(
                'userID',
                openapi.IN_QUERY,
                description='User ID for logout',
                type=openapi.TYPE_STRING,
                required=True
            ),
        ],
        responses={
            200: openapi.Response(
                description='User logged out successfully',
                examples={
                    'application/json': {
                        'message': 'User X has been successfully logged out.',
                        'is_active': False
                    }
                }
            ),
            400: openapi.Response(
                description='Bad request - missing userID',
                examples={
                    'application/json': {
                        'message': 'userID is a required query parameter.'
                    }
                }
            ),
            404: openapi.Response(
                description='User not found',
                examples={
                    'application/json': {
                        'message': 'User with userID X not found.'
                    }
                }
            )
        }
    )
    def get(self, request, *args, **kwargs):
        # Retrieve the userID from the URL's query parameters
        rider_id = request.query_params.get('userID')

        if not rider_id:
            return Response(
                {"message": "userID is a required query parameter."},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            user = Registration.objects.get(user_id=rider_id)

            # Case 1: If user is currently active, log them out.
            # This also handles the 'is_active: null' case as the condition will be false.
            if user.is_active:
                user.is_active = False
                user.save()
                return Response(
                    {"message": f"User {rider_id} has been successfully logged out.", "is_active": user.is_active},
                    status=status.HTTP_200_OK
                )
            # Case 2: If user is already inactive.
            else:
                return Response(
                    {"message": "User already logged out from the app."},
                    status=status.HTTP_200_OK
                )

        except Registration.DoesNotExist:
            return Response(
                {"message": f"User with userID {rider_id} not found."},
                status=status.HTTP_404_NOT_FOUND
            )

class ChangeModeAPIView(APIView):
    """
    Changes the user's mode based on query param userID and body param mode_to.
    Expected URL: /change_mode?userID=<id>
    Expected body: { "mode_to": "retail business" }
    Allowed modes: consumer, retail_business, delivery_partner
    """
    @swagger_auto_schema(
        tags=['Core'],
        manual_parameters=[
            openapi.Parameter(
                'userID',
                openapi.IN_QUERY,
                description='User ID for mode change',
                type=openapi.TYPE_STRING,
                required=True
            ),
        ],
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            properties={
                'mode_to': openapi.Schema(
                    type=openapi.TYPE_STRING,
                    description='Target user mode (consumer, retail_business, delivery_partner)',
                    enum=['consumer', 'retail_business', 'delivery_partner'],
                    required=['mode_to']
                ),
            },
            required=['mode_to']
        ),
        responses={
            200: openapi.Response(
                description='Mode changed successfully',
                examples={
                    'application/json': {
                        'message': 'Mode changed to retail_business successfully',
                        'current_mode': 'retail_business',
                        'user_details': {
                            'user_id': 'string',
                            'firstName': 'string',
                            'lastName': 'string',
                            'is_verified': True,
                            'is_active': True,
                            'user_mode': 'retail_business'
                        }
                    }
                }
            ),
            400: openapi.Response(
                description='Bad request - missing or invalid parameters',
                examples={
                    'application/json': {
                        'message': 'user_id doesnot exist'
                    }
                }
            ),
            404: openapi.Response(
                description='User not found',
                examples={
                    'application/json': {
                        'message': 'user_id doesnot exist'
                    }
                }
            )
        }
    )
    def post(self, request, *args, **kwargs):
        # 1) Validate userID in query params
        user_id = request.query_params.get('userID')
        if not user_id:
            return Response({"message": "user_id doesnot exist"}, status=status.HTTP_400_BAD_REQUEST)

        # 2) Normalize and validate target mode
        mode_to_raw = request.data.get('mode_to')
        if not mode_to_raw:
            return Response({"message": "mode is not defined"}, status=status.HTTP_400_BAD_REQUEST)

        # Normalize input like "retail business" -> "retail_business", case-insensitive
        normalized = str(mode_to_raw).strip().lower().replace(" ", "_")
        allowed_modes = {"consumer", "retail_business", "delivery_partner"}
        if normalized not in allowed_modes:
            return Response({"message": "mode is not defined"}, status=status.HTTP_400_BAD_REQUEST)

        # 3) Find user by user_id
        try:
            user = Registration.objects.get(user_id=user_id)
        except Registration.DoesNotExist:
            return Response({"message": "user_id doesnot exist"}, status=status.HTTP_404_NOT_FOUND)

        # 4) If already in the target mode
        if user.user_mode == normalized:
            user_details = {
                "displayName": f"{user.firstName}{user.lastName}",
                "mobileNumber": user.mobileNumber,
                "emailID": user.emailID,
                "is_verified": user.is_verified,
                "is_active": user.is_active,
                "status": user.status,
                "profileUrl": build_profile_url(request, user),
                "tokenID": user.tokenID,
                "dob": user.dob,
                "uuid": user.uuid,
                "os": user.os,
                "whichapp": user.whichapp,
                "created_at": user.created_at,
                "updated_at": user.updated_at,
                "user_id": user.user_id,
            }
            return Response({
                "message": f"Mode is already active in {normalized}",
                "current_mode": user.user_mode,
                "user_details": user_details
            }, status=status.HTTP_200_OK)

        # 5) Change mode and return success
        previous = user.user_mode
        user.user_mode = normalized
        user.save()

        user_details = {
            "displayName": f"{user.firstName}{user.lastName}",
            "mobileNumber": user.mobileNumber,
            "emailID": user.emailID,
            "is_verified": user.is_verified,
            "is_active": user.is_active,
            "status": user.status,
            "profileUrl": build_profile_url(request, user),
            "tokenID": user.tokenID,
            "dob": user.dob,
            "uuid": user.uuid,
            "os": user.os,
            "whichapp": user.whichapp,
            "user_mode": user.user_mode,
            "created_at": user.created_at,
            "updated_at": user.updated_at,
            "user_id": user.user_id,
        }
        return Response({
            "message": f"Mode changed to {normalized} successfully",
            "current_mode": user.user_mode,
            "user_details": user_details
        }, status=status.HTTP_200_OK)

class UpdateProfileAPIView(APIView):
    """
    Updates a user's profile fields based on userID query param.
    Also supports account deletion via a 'delete' flag in the body.
      - delete (optional; true/false)
    """
    @swagger_auto_schema(
        tags=['Core'],
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            properties={
                'firstName': openapi.Schema(type=openapi.TYPE_STRING, description='First name'),
                'lastName': openapi.Schema(type=openapi.TYPE_STRING, description='Last name'),
                'displayName': openapi.Schema(type=openapi.TYPE_STRING, description='Display name'),
                'dob': openapi.Schema(type=openapi.TYPE_STRING, description='Date of birth'),
                'profileurl': openapi.Schema(type=openapi.TYPE_FILE, description='Profile image'),
                'delete': openapi.Schema(type=openapi.TYPE_BOOLEAN, description='Delete account (optional)'),
            },
            required=[]
        ),
        responses={
            200: openapi.Response(
                description='Profile updated successfully',
                examples={
                    'application/json': {
                        'message': 'Profile updated successfully',
                        'details': {
                            'user_id': 'string',
                            'firstName': 'string',
                            'lastName': 'string',
                            'displayName': 'string',
                            'mobileNumber': 'string',
                            'emailID': 'string',
                            'dob': 'string',
                            'is_verified': True,
                            'is_active': True,
                            'status': True,
                            'uuid': 'string',
                            'os': 'string',
                            'whichapp': 'string',
                            'user_mode': 'string',
                            'created_at': 'string',
                            'updated_at': 'string'
                        }
                    }
                }
            ),
            400: openapi.Response(
                description='Bad request - validation failed',
                examples={
                    'application/json': {
                        'message': 'user_id doesnot exist'
                    }
                }
            ),
            404: openapi.Response(
                description='User not found',
                examples={
                    'application/json': {
                        'message': 'user_id doesnot exist'
                    }
                }
            )
        }
    )
    def post(self, request, *args, **kwargs):
        user_id = request.query_params.get('userID')
        if not user_id:
            return Response({"message": "user_id doesnot exist"}, status=status.HTTP_400_BAD_REQUEST)

        # Disallow updates to these fields
        forbidden_fields = []
        for field in ["mobileNumber", "emailID"]:
            if field in request.data:
                forbidden_fields.append(field)
        if forbidden_fields:
            value = ", ".join(forbidden_fields)
            return Response({"message": f"You cannot update the {value}"}, status=status.HTTP_400_BAD_REQUEST)

        # Fetch user
        try:
            user = Registration.objects.get(user_id=user_id)
        except Registration.DoesNotExist:
            return Response({"message": "user_id doesnot exist"}, status=status.HTTP_404_NOT_FOUND)

        # Deletion is not handled via POST anymore. Use HTTP DELETE on this endpoint.
        if 'delete' in request.data:
            return Response({"message": "Use HTTP DELETE /update-profile?userID=<id> for account deletion (soft delete)."}, status=status.HTTP_405_METHOD_NOT_ALLOWED)

        # If account is soft-deleted (status=0), block profile updates
        if not bool(user.status):
            return Response({
                "message": "unable to update profile. account is deactivated"
            }, status=status.HTTP_403_FORBIDDEN)

        # Track if any update happened
        updated = False

        # Update firstName and lastName if provided
        first_name = request.data.get('firstName')
        last_name = request.data.get('lastName')
        display_name = request.data.get('displayName')  # Informational only; DB generated
        dob = request.data.get('dob')
        if first_name is not None:
            user.firstName = first_name
            updated = True
        if last_name is not None:
            user.lastName = last_name
            updated = True
        if dob is not None:
            user.dob = dob
            updated = True

        # Handle profile image upload
        file_obj = request.FILES.get('profileurl')
        if file_obj:
            # Build new filename: KIR<user_id><DDMMYYHRMMSS><orig_ext>
            timestamp = timezone.now().strftime('%d%m%y%H%M%S')
            orig_ext = os.path.splitext(file_obj.name)[1]
            # Default to .jpg if no extension provided
            ext = orig_ext if orig_ext else '.jpg'
            new_filename = f"KIR{user.user_id}{timestamp}{ext}"
            rel_dir = 'profiles'
            abs_dir = os.path.join(settings.BASE_DIR, 'media', rel_dir)
            os.makedirs(abs_dir, exist_ok=True)
            abs_path = os.path.join(abs_dir, new_filename)

            # Compress and save image using Django Storage API
            try:
                img = Image.open(file_obj)
                fmt = ext.lower().lstrip('.')
                pil_format = {
                    'jpg': 'JPEG',
                    'jpeg': 'JPEG',
                    'png': 'PNG',
                    'webp': 'WEBP',
                    'gif': 'GIF',
                    'bmp': 'BMP',
                    'tif': 'TIFF',
                    'tiff': 'TIFF',
                }.get(fmt, None)
                
                from io import BytesIO
                # Create a BytesIO buffer to hold the saved image
                img_io = BytesIO()
                
                save_kwargs = {}
                if pil_format in ('JPEG', 'WEBP'):
                    if pil_format == 'JPEG':
                        if img.mode in ("RGBA", "LA"):
                            background = Image.new("RGB", img.size, (255, 255, 255))
                            background.paste(img, mask=img.split()[-1])
                            img = background
                        elif img.mode != "RGB":
                            img = img.convert("RGB")
                    save_kwargs = {"quality": 70, "optimize": True}
                elif pil_format == 'PNG':
                    save_kwargs = {"optimize": True}

                if pil_format:
                    img.save(img_io, format=pil_format, **save_kwargs)
                else:
                    img.save(img_io)
                
                # Seek to beginning of buffer
                img_io.seek(0)
                
                # Save to storage (S3 or local)
                relative_path = os.path.join(rel_dir, new_filename).replace('\\', '/')
                # Use default_storage to save
                # If file exists, it might overwrite or append random string depending on storage config
                saved_name = default_storage.save(relative_path, img_io)
                
                # Store the relative path (or use saved_name which might have hash)
                user.profileUrl = saved_name
                updated = True

            except Exception as e:
                print(f"Image save error: {e}")
                return Response({"message": "invalid image file"}, status=status.HTTP_400_BAD_REQUEST)

        if updated:
            user.save()

        # Build response details
        details = {
            "user_id": user.user_id,
            "firstName": user.firstName,
            "lastName": user.lastName,
            "displayName": f"{user.firstName}{user.lastName}",
            "mobileNumber": user.mobileNumber,
            "emailID": user.emailID,
            "dob": user.dob,
            "is_verified": user.is_verified,
            "is_active": user.is_active,
            "status": user.status,
            "uuid": user.uuid,
            "os": user.os,
            "whichapp": user.whichapp,
            "user_mode": user.user_mode,
            "created_at": user.created_at,
            "updated_at": user.updated_at,
        }

        # Provide full profile URL if set
        details["profileUrl"] = build_profile_url(request, user)

        message = "profile update successfully" if updated else "no changes"
        return Response({"message": message, "details": details}, status=status.HTTP_200_OK)

    @swagger_auto_schema(
        tags=['Core'],
        responses={
            200: openapi.Response(
                description='Account deleted successfully',
                examples={
                    'application/json': {
                        'message': 'account permanently deleted successfully'
                    }
                }
            ),
            400: openapi.Response(
                description='Bad request - validation failed',
                examples={
                    'application/json': {
                        'message': 'user_id doesnot exist'
                    }
                }
            ),
            404: openapi.Response(
                description='User not found',
                examples={
                    'application/json': {
                        'message': 'user_id doesnot exist'
                    }
                }
            )
        }
    )
    def delete(self, request, *args, **kwargs):
        """
        Account deletion rules:
        1) If is_active == 0 => block deletion with message.
        2) If is_verified == 0 => permanently delete (hard delete).
        3) Else => soft delete (status=0, is_active=0).
        URL: DELETE /update-profile?userID=<id>
        """
        user_id = request.query_params.get('userID')
        if not user_id:
            return Response({"message": "user_id doesnot exist"}, status=status.HTTP_400_BAD_REQUEST)

        try:
            user = Registration.objects.get(user_id=user_id)
        except Registration.DoesNotExist:
            return Response({"message": "user_id doesnot exist"}, status=status.HTTP_404_NOT_FOUND)

        # 1) Block if not active (not logged-in for deletion)
        if not bool(user.is_active):
            return Response({
                "message": "unable to delete your account. you not logged in to delete the account"
            }, status=status.HTTP_403_FORBIDDEN)

        # 2) If not verified => permanently delete
        if not bool(user.is_verified):
            user.delete()
            return Response({
                "message": "account permanently deleted successfully"
            }, status=status.HTTP_200_OK)

        # 3) Otherwise => soft delete
        user.status = False
        user.is_active = False
        user.save()

        # Build confirmation details
        details = {
            "user_id": user.user_id,
            "firstName": user.firstName,
            "lastName": user.lastName,
            "displayName": f"{user.firstName}{user.lastName}",
            "mobileNumber": user.mobileNumber,
            "emailID": user.emailID,
            "dob": user.dob,
            "is_verified": user.is_verified,
            "is_active": int(user.is_active) if isinstance(user.is_active, bool) else user.is_active,
            "status": int(user.status) if isinstance(user.status, bool) else user.status,
            "uuid": user.uuid,
            "os": user.os,
            "whichapp": user.whichapp,
            "user_mode": user.user_mode,
            "created_at": user.created_at,
            "updated_at": user.updated_at
        }
        details["profileUrl"] = build_profile_url(request, user)

        return Response({
            "message": "account soft-deleted successfully",
            "user_details": details
        }, status=status.HTTP_200_OK)

class UpdateProfileImageAPIView(APIView):
    @swagger_auto_schema(
        tags=['Core'],
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            properties={
                'profile_image': openapi.Schema(type=openapi.TYPE_FILE, description='Profile image'),
            },
            required=['profile_image']
        ),
        responses={
            200: openapi.Response(
                description='Profile image updated successfully',
                examples={
                    'application/json': {
                        'message': 'Profile updated successfully',
                        'profile_image': 'string'
                    }
                }
            ),
            400: openapi.Response(
                description='Bad request - validation failed',
                examples={
                    'application/json': {
                        'message': 'user_id doesnot exist'
                    }
                }
            ),
            404: openapi.Response(
                description='User not found',
                examples={
                    'application/json': {
                        'message': 'user_id doesnot exist'
                    }
                }
            )
        }
    )
    def patch(self, request, *args, **kwargs):
        user_id = request.query_params.get('userID')
        if not user_id:
            return Response({"message": "user_id doesnot exist"}, status=status.HTTP_400_BAD_REQUEST)

        try:
            user = Registration.objects.get(user_id=user_id)
        except Registration.DoesNotExist:
            return Response({"message": "user_id doesnot exist"}, status=status.HTTP_404_NOT_FOUND)

        if not bool(user.status):
            return Response({"message": "unable to update profile. account is deactivated"}, status=status.HTTP_403_FORBIDDEN)

        file_obj = request.FILES.get('profile_image') or request.FILES.get('profileurl')
        if not file_obj:
            return Response({"message": "profile image is required"}, status=status.HTTP_400_BAD_REQUEST)

        timestamp = timezone.now().strftime('%d%m%y%H%M%S')
        orig_ext = os.path.splitext(file_obj.name)[1]
        ext = orig_ext if orig_ext else '.jpg'
        new_filename = f"KIR{user.user_id}{timestamp}{ext}"
        rel_dir = 'profiles'
        abs_dir = os.path.join(settings.BASE_DIR, 'media', rel_dir)
        os.makedirs(abs_dir, exist_ok=True)
        abs_path = os.path.join(abs_dir, new_filename)

        try:
            img = Image.open(file_obj)
            fmt = ext.lower().lstrip('.')
            pil_format = {
                'jpg': 'JPEG',
                'jpeg': 'JPEG',
                'png': 'PNG',
                'webp': 'WEBP',
                'gif': 'GIF',
                'bmp': 'BMP',
                'tif': 'TIFF',
                'tiff': 'TIFF',
            }.get(fmt, None)
            
            from io import BytesIO
            img_io = BytesIO()

            save_kwargs = {}
            if pil_format in ('JPEG', 'WEBP'):
                if pil_format == 'JPEG':
                    if img.mode in ("RGBA", "LA"):
                        background = Image.new("RGB", img.size, (255, 255, 255))
                        background.paste(img, mask=img.split()[-1])
                        img = background
                    elif img.mode != "RGB":
                        img = img.convert("RGB")
                save_kwargs = {"quality": 70, "optimize": True}
            elif pil_format == 'PNG':
                save_kwargs = {"optimize": True}

            if pil_format:
                img.save(img_io, format=pil_format, **save_kwargs)
            else:
                img.save(img_io)
            
            img_io.seek(0)
            
            # Save to storage (S3 or local)
            relative_path = os.path.join(rel_dir, new_filename).replace('\\', '/')
            saved_name = default_storage.save(relative_path, img_io)
            user.profileUrl = saved_name
            user.save()

        except Exception as e:
            print(f"Image update error: {e}")
            return Response({"message": "invalid image file"}, status=status.HTTP_400_BAD_REQUEST)

        profile_full_url = build_profile_url(request, user)
        return Response({
            "message": "Profile updated successfully",
            "profile_image": profile_full_url
        }, status=status.HTTP_200_OK)

class UserProfileAPIView(APIView):
    """
    Get user profile based on userID.
    URL: GET /user-profile/?userID=<value>
    
    For retail_business users, also includes business_owner_details and business_details.
    """
    @swagger_auto_schema(
        tags=['Core'],
        responses={
            200: openapi.Response(
                description='User profile retrieved successfully',
                examples={
                    'application/json': {
                        'user_details': {
                            'id': 'integer',
                            'user_id': 'string',
                            'firstName': 'string',
                            'lastName': 'string',
                            'displayName': 'string',
                            'countryCode': 'string',
                            'mobileNumber': 'string',
                            'emailID': 'string',
                            'dob': 'string',
                            'is_verified': 'boolean',
                            'is_active': 'boolean',
                            'user_mode': 'string',
                            'profileUrl': 'string',
                            'tokenID': 'string',
                            'uuid': 'string',
                            'os': 'string',
                            'status': 'boolean',
                            'whichapp': 'string',
                            'created_at': 'string',
                            'updated_at': 'string'
                        }
                    }
                }
            ),
            400: openapi.Response(
                description='Bad request - validation failed',
                examples={
                    'application/json': {
                        'message': 'userID is required as query parameter'
                    }
                }
            ),
            404: openapi.Response(
                description='User not found',
                examples={
                    'application/json': {
                        'message': 'User with userID X not found'
                    }
                }
            )
        }
    )
    def get(self, request, *args, **kwargs):
        user_id = request.query_params.get('userID')
        if not user_id:
            return Response(
                {"message": "userID is required as query parameter"},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            user = Registration.objects.get(user_id=user_id)
        except Registration.DoesNotExist:
            return Response(
                {"message": f"User with userID {user_id} not found"},
                status=status.HTTP_404_NOT_FOUND
            )

        # Build user details response
        user_details = {
            "id": user.id,
            "user_id": user.user_id,
            "firstName": user.firstName,
            "lastName": user.lastName,
            "displayName": f"{user.firstName} {user.lastName}",
            "countryCode": user.countryCode,
            "mobileNumber": user.mobileNumber,
            "emailID": user.emailID,
            "dob": user.dob,
            "is_verified": int(user.is_verified) if isinstance(user.is_verified, bool) else user.is_verified,
            "is_active": int(user.is_active) if isinstance(user.is_active, bool) else user.is_active,
            "user_mode": user.user_mode,
            "profileUrl": build_profile_url(request, user),
            "tokenID": user.tokenID,
            "uuid": user.uuid,
            "os": user.os,
            "status": int(user.status) if isinstance(user.status, bool) else user.status,
            "whichapp": user.whichapp,
            "created_at": user.created_at,
            "updated_at": user.updated_at
        }

        response_data = {"user_details": user_details}

        # Check if user is a delivery partner
        is_delivery_partner = False
        try:
            from delivery.models import DeliveryPartner
            delivery_partner = DeliveryPartner.objects.filter(user_id=user.user_id).first()
            is_delivery_partner = delivery_partner is not None
        except Exception:
            is_delivery_partner = False

        # Check if user is a business owner
        is_business_owner = False
        try:
            from .models import BusinessMapping
            business_mapping = BusinessMapping.objects.filter(user_id=user.user_id).first()
            is_business_owner = business_mapping is not None
        except Exception:
            is_business_owner = False

        # Add role-based flags based on user_mode
        if user.user_mode == "consumer":
            user_details["is_delivery_partner"] = is_delivery_partner
            user_details["is_business_owner"] = is_business_owner
        elif user.user_mode == "retail_business":
            user_details["is_delivery_partner"] = is_delivery_partner
            user_details["is_consumer"] = True  # Every user is a consumer
        elif user.user_mode == "delivery_partner":
            user_details["is_business_owner"] = is_business_owner
            user_details["is_consumer"] = True  # Every user is a consumer

        # If user is retail_business, add business_owner_details
        if user.user_mode == "retail_business":
            try:
                # Get business mapping first
                from .models import BusinessMapping
                business_mapping = BusinessMapping.objects.get(user_id=user.user_id)
                
                # Get business owner details
                owner_details = BusinessOwnerDetails.objects.get(user=business_mapping)
                
                business_owner_details = {
                    "id": owner_details.id,
                    "user_id": user.user_id,
                    "pan": owner_details.pan,
                    "aadhaar": owner_details.aadhaar,
                    "per_mobile_number": owner_details.per_mobile_number,
                    "created_at": owner_details.created_at,
                    "updated_at": owner_details.updated_at
                }
                
                response_data["business_owner_details"] = business_owner_details
                
                # Add business details
                try:
                    from .models import Business
                    business = Business.objects.get(business_id=business_mapping.business_id)
                    business_details = {
                        "business_id": business.business_id,
                        "businessName": business.businessName,
                        "businessType": business.businessType,
                        "businessCategory": business.businessCategory,
                        "businessEmail": business.businessEmail,
                        "businessNumber": business.businessNumber,
                        "businessWhatsapp": business.businessWhatsapp,
                        "description": business.description,
                        "logo": build_s3_file_url(business.logo.url) if business.logo else None,
                        "banner": build_s3_file_url(business.banner.url) if business.banner else None,
                        "business_features": business.business_features,
                        "business_hours": business.business_hours,
                        "gst_num": business.gst_num,
                        "currency": business.currency,
                        "location": business.location,
                        "address": business.address,
                        "landmark": business.landmark,
                        "city": business.city,
                        "state": business.state,
                        "pincode": business.pincode,
                        "contact_support": business.contact_support,
                        "contact_mobile": business.contact_mobile,
                        "website_url": business.website_url,
                        "is_verified": business.is_verified,
                        "created_at": business.created_at,
                        "updated_at": business.updated_at
                    }
                    response_data["business_details"] = business_details
                except Business.DoesNotExist:
                    pass
                
                # Add verification_status if available
                if hasattr(business_mapping, 'verification_status'):
                    user_details["verification_status"] = business_mapping.verification_status
                    
            except (BusinessMapping.DoesNotExist, BusinessOwnerDetails.DoesNotExist):
                # If business owner details don't exist, continue without them
                pass
        
        # If user is company_admin or company_employee, add company details
        elif user.user_type in ["company_admin", "company_employee"]:
            try:
                from .models import CompanyRegistration
                if user.company_id:
                    company = CompanyRegistration.objects.get(company_id=user.company_id)
                    
                    company_details = {
                        "company_id": company.company_id,
                        "company_name": company.company_name,
                        "gst_number": company.gst_number,
                        "business_type": company.business_type,
                        "contact_person_name": company.contact_person_name,
                        "contact_person_email": company.contact_person_email,
                        "contact_person_phone": company.contact_person_phone,
                        "business_address": company.business_address,
                        "verification_status": company.verification_status,
                        "approved_at": company.approved_at,
                        "created_at": company.created_at,
                        "updated_at": company.updated_at
                    }
                    
                    response_data["company_details"] = company_details
                    
                    # Add employee details
                    employee_details = {
                        "employee_id": getattr(user, 'employee_id', None),
                        "employee_role": getattr(user, 'employee_role', None),
                        "department": getattr(user, 'department', None),
                        "joined_company_at": getattr(user, 'joined_company_at', None),
                        "is_verified": user.is_verified,
                        "purchase_limit": getattr(user, 'purchase_limit', None),
                        "reporting_manager": getattr(user, 'reporting_manager', None),
                        "can_approve_orders": getattr(user, 'can_approve_orders', False)
                    }
                    
                    response_data["employee_details"] = employee_details
                    
            except Exception:
                pass
        
        return Response(response_data, status=status.HTTP_200_OK)

class UserAddressesAPIView(APIView):
    """
    Get user addresses based on userID.
    URL: GET /user-addresses/?userID=<value>
    """
    @swagger_auto_schema(
        tags=['Core'],
        responses={
            200: openapi.Response(
                description='User addresses retrieved successfully',
                examples={
                    'application/json': {
                        'user_address': [
                            {
                                'id': 'integer',
                                'user_id': 'string',
                                'address_type': 'string',
                                'tag': 'string',
                                'is_default': 'boolean',
                                'address': 'string',
                                'status': 'boolean',
                                'created_at': 'string',
                                'updated_at': 'string'
                            }
                        ]
                    }
                }
            ),
            400: openapi.Response(
                description='Bad request - validation failed',
                examples={
                    'application/json': {
                        'message': 'userID is required as query parameter'
                    }
                }
            ),
            404: openapi.Response(
                description='User not found',
                examples={
                    'application/json': {
                        'message': 'User with userID X not found'
                    }
                }
            )
        }
    )
    def get(self, request, *args, **kwargs):
        import json  # Import at function level for use throughout
        user_id = request.query_params.get('userID')
        if not user_id:
            return Response(
                {"message": "userID is required as query parameter"},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Handle JWT token objects sent as userID parameter
        if user_id and user_id.startswith('{'):
            try:
                token_data = json.loads(user_id)
                # Extract numeric user_id from token
                user_id = token_data.get('user_id') or token_data.get('id')
            except (ValueError, TypeError):
                pass
        
        # Ensure user_id is numeric
        try:
            user_id = int(user_id)
        except (ValueError, TypeError):
            return Response(
                {"message": "Invalid userID format. Expected numeric user_id or valid JWT token."},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            user = Registration.objects.get(user_id=user_id)
        except Registration.DoesNotExist:
            return Response(
                {"message": f"User with userID {user_id} not found"},
                status=status.HTTP_404_NOT_FOUND
            )

        # Get all active addresses for the user, ordered by default first, then by creation date
        addresses = UserAddress.objects.filter(
            user=user, 
            status=True
        ).order_by('-is_default', '-created_at')

        user_address_list = []
        for addr in addresses:
            address_data = {
                "id": addr.id,
                "user_id": user.user_id,
                "address_type": addr.address_type,
                "tag": addr.tag,
                "is_default": int(addr.is_default) if isinstance(addr.is_default, bool) else addr.is_default,
                "address": json.dumps(addr.address) if isinstance(addr.address, dict) else addr.address,
                "status": int(addr.status) if isinstance(addr.status, bool) else addr.status,
                "created_at": addr.created_at,
                "updated_at": addr.updated_at
            }
            user_address_list.append(address_data)

        return Response(
            {"user_address": user_address_list},
            status=status.HTTP_200_OK
        )

class AddressAPIView(APIView):
    """
    Manage user addresses.
    - POST /address?userID=... : create or update (home/work singletons; other can be multiple with tag). Handles default switching.
    - PATCH /address?userID=...&&id=... : update specific address and optionally switch default.
    - DELETE /address?userID=...&&id=... : soft delete (status=0) an address.
    """

    def _user_details(self, request, user: Registration):
        return {
            "user_id": user.user_id,
            "firstName": user.firstName,
            "lastName": user.lastName,
            "displayName": f"{user.firstName}{user.lastName}",
            "mobileNumber": user.mobileNumber,
            "emailID": user.emailID,
            "dob": user.dob,
            "is_verified": user.is_verified,
            "is_active": user.is_active,
            "status": user.status,
            "profileUrl": build_profile_url(request, user),
            "uuid": user.uuid,
            "os": user.os,
            "whichapp": user.whichapp,
            "user_mode": user.user_mode,
            "created_at": user.created_at,
            "updated_at": user.updated_at,
        }

    def _list_user_addresses(self, user: Registration):
        qs = UserAddress.objects.filter(user=user, status=True).order_by('-is_default', '-updated_at', '-created_at')
        return UserAddressSerializer(qs, many=True).data

    def _ensure_single_default(self, user: Registration, keep_id: Optional[int]):
        UserAddress.objects.filter(user=user, status=True).exclude(id=keep_id).update(is_default=False)

    @swagger_auto_schema(
        tags=['Core'],
        manual_parameters=[
            openapi.Parameter(
                'userID',
                openapi.IN_QUERY,
                description='User ID for address creation/update',
                type=openapi.TYPE_STRING,
                required=True
            ),
        ],
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            properties={
                'address_type': openapi.Schema(
                    type=openapi.TYPE_STRING,
                    description='Type of address (home, work, other)',
                    enum=['home', 'work', 'other'],
                    required=['address_type']
                ),
                'tag': openapi.Schema(type=openapi.TYPE_STRING, description='Address tag (required for other type)'),
                'is_default': openapi.Schema(type=openapi.TYPE_BOOLEAN, description='Set as default address'),
                'address': openapi.Schema(
                    type=openapi.TYPE_OBJECT,
                    description='Address details',
                    properties={
                        'Door no': openapi.Schema(type=openapi.TYPE_STRING, description='Door number'),
                        'street': openapi.Schema(type=openapi.TYPE_STRING, description='Street name'),
                        'city/town': openapi.Schema(type=openapi.TYPE_STRING, description='City or town'),
                        'state': openapi.Schema(type=openapi.TYPE_STRING, description='State'),
                        'pincode': openapi.Schema(type=openapi.TYPE_STRING, description='Pincode'),
                        'country': openapi.Schema(type=openapi.TYPE_STRING, description='Country'),
                        'landmark': openapi.Schema(type=openapi.TYPE_STRING, description='Landmark'),
                        'latitude': openapi.Schema(type=openapi.TYPE_NUMBER, format='float', description='Latitude'),
                        'longitude': openapi.Schema(type=openapi.TYPE_NUMBER, format='float', description='Longitude'),
                    },
                    required=['Door no', 'street', 'city/town', 'state', 'pincode', 'country']
                ),
            },
            required=['address_type', 'address']
        ),
        responses={
            200: openapi.Response(
                description='Address created/updated successfully',
                examples={
                    'application/json': {
                        'message': 'Address created successfully',
                        'user_address': [
                            {
                                'id': 1,
                                'address_type': 'home',
                                'tag': None,
                                'is_default': True,
                                'address': '{"Door no": "123", "street": "Main St", "city/town": "City", "state": "State", "pincode": "123456", "country": "India"}',
                                'status': True
                            }
                        ]
                    }
                }
            ),
            400: openapi.Response(
                description='Bad request - validation failed',
                examples={
                    'application/json': {
                        'message': 'address_type is required'
                    }
                }
            ),
            404: openapi.Response(
                description='User not found',
                examples={
                    'application/json': {
                        'message': 'user_id not found'
                    }
                }
            )
        }
    )
    def post(self, request, *args, **kwargs):
        user_id = request.query_params.get('userID')
        if not user_id:
            return Response({"message": "user_id not found"}, status=status.HTTP_400_BAD_REQUEST)
        
        # Handle JWT token objects sent as userID parameter
        if user_id and user_id.startswith('{'):
            import json
            try:
                token_data = json.loads(user_id)
                # Extract numeric user_id from token
                user_id = token_data.get('user_id') or token_data.get('id')
            except (ValueError, TypeError):
                pass
        
        # Ensure user_id is numeric
        try:
            user_id = int(user_id)
        except (ValueError, TypeError):
            return Response({"message": "Invalid userID format. Expected numeric user_id or valid JWT token."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            user = Registration.objects.get(user_id=user_id)
        except Registration.DoesNotExist:
            return Response({"message": "user_id not found"}, status=status.HTTP_404_NOT_FOUND)

        address_type = request.data.get('address_type')
        tag = request.data.get('tag')
        is_default = request.data.get('is_default', False)
        address_payload = request.data.get('address', {})
        
        # Validate address type
        if not address_type:
            return Response({"message": "address_type is required"}, status=status.HTTP_400_BAD_REQUEST)

        normalized_type = str(address_type).strip().lower()
        if normalized_type not in {"home", "work", "other"}:
            return Response({"message": "Invalid address_type. Allowed: home, work, other"}, status=status.HTTP_400_BAD_REQUEST)

        if normalized_type == 'other' and not tag:
            return Response({"message": "you mention \"other\" in \"address_type\" , Please mention the tag."}, status=status.HTTP_400_BAD_REQUEST)

        # Convert is_default to bool
        is_default = bool(int(is_default)) if str(is_default).isdigit() else False

        # Ensure address payload contains required fields
        required_fields = ['Door no', 'street', 'city/town', 'state', 'pincode', 'country']
        if not all(field in address_payload for field in required_fields):
            return Response({"message": f"Address must contain: {', '.join(required_fields)}"}, status=status.HTTP_400_BAD_REQUEST)

        # Add latitude/longitude if provided
        if 'latitude' not in address_payload:
            address_payload['latitude'] = None
        if 'longitude' not in address_payload:
            address_payload['longitude'] = None

        with transaction.atomic():
            # For home/work addresses, update existing or create new
            if normalized_type in ['home', 'work']:
                address, created = UserAddress.objects.update_or_create(
                    user=user,
                    address_type=normalized_type,
                    defaults={
                        'tag': None,
                        'address': address_payload,
                        'status': True
                    }
                )
            else:
                # For 'other' addresses, create new entry
                address = UserAddress.objects.create(
                    user=user,
                    address_type=normalized_type,
                    tag=tag,
                    address=address_payload,
                    status=True
                )

            # Handle default address
            if is_default:
                self._ensure_single_default(user, address.id)
                address.is_default = True
                address.save()

        serializer = UserAddressSerializer(address)
        return Response({
            "message": "Address updated successfully" if normalized_type in ['home', 'work'] else "Address created successfully",
            "user_address": self._list_user_addresses(user)
        }, status=status.HTTP_200_OK)

    @swagger_auto_schema(
        tags=['Core'],
        manual_parameters=[
            openapi.Parameter(
                'userID',
                openapi.IN_QUERY,
                description='User ID for address update',
                type=openapi.TYPE_STRING,
                required=True
            ),
            openapi.Parameter(
                'id',
                openapi.IN_QUERY,
                description='Address ID to update',
                type=openapi.TYPE_INTEGER,
                required=True
            ),
        ],
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            properties={
                'address_type': openapi.Schema(
                    type=openapi.TYPE_STRING,
                    description='Type of address (home, work, other)',
                    enum=['home', 'work', 'other']
                ),
                'tag': openapi.Schema(type=openapi.TYPE_STRING, description='Address tag'),
                'is_default': openapi.Schema(type=openapi.TYPE_BOOLEAN, description='Set as default address'),
                'address': openapi.Schema(
                    type=openapi.TYPE_OBJECT,
                    description='Address details',
                    properties={
                        'Door no': openapi.Schema(type=openapi.TYPE_STRING, description='Door number'),
                        'street': openapi.Schema(type=openapi.TYPE_STRING, description='Street name'),
                        'city/town': openapi.Schema(type=openapi.TYPE_STRING, description='City or town'),
                        'state': openapi.Schema(type=openapi.TYPE_STRING, description='State'),
                        'pincode': openapi.Schema(type=openapi.TYPE_STRING, description='Pincode'),
                        'country': openapi.Schema(type=openapi.TYPE_STRING, description='Country'),
                        'landmark': openapi.Schema(type=openapi.TYPE_STRING, description='Landmark'),
                        'latitude': openapi.Schema(type=openapi.TYPE_NUMBER, format='float', description='Latitude'),
                        'longitude': openapi.Schema(type=openapi.TYPE_NUMBER, format='float', description='Longitude'),
                    }
                ),
            }
        ),
        responses={
            200: openapi.Response(
                description='Address updated successfully',
                examples={
                    'application/json': {
                        'message': 'Address updated successfully',
                        'user_address': [
                            {
                                'id': 1,
                                'address_type': 'home',
                                'tag': None,
                                'is_default': True,
                                'address': '{"Door no": "123", "street": "Main St", "city/town": "City", "state": "State", "pincode": "123456", "country": "India"}',
                                'status': True
                            }
                        ]
                    }
                }
            ),
            400: openapi.Response(
                description='Bad request - missing or invalid parameters',
                examples={
                    'application/json': {
                        'message': 'user_id not found'
                    }
                }
            ),
            404: openapi.Response(
                description='User or address not found',
                examples={
                    'application/json': {
                        'message': 'user_id not found'
                    }
                }
            )
        }
    )
    def patch(self, request, *args, **kwargs):
        user_id = request.query_params.get('userID')
        addr_id = request.query_params.get('id')
        if not user_id:
            return Response({"message": "user_id not found"}, status=status.HTTP_400_BAD_REQUEST)
        if not addr_id:
            return Response({"message": "address id not assigned with userID , Please mention the correct id."}, status=status.HTTP_400_BAD_REQUEST)
        
        # Handle JWT token objects sent as userID parameter
        import json
        if user_id and user_id.startswith('{'):
            try:
                token_data = json.loads(user_id)
                # Extract numeric user_id from token
                user_id = token_data.get('user_id') or token_data.get('id')
            except (ValueError, TypeError):
                pass
        
        # Ensure user_id is numeric
        try:
            user_id = int(user_id)
        except (ValueError, TypeError):
            return Response({"message": "Invalid userID format. Expected numeric user_id or valid JWT token."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            user = Registration.objects.get(user_id=user_id)
        except Registration.DoesNotExist:
            return Response({"message": "user_id not found"}, status=status.HTTP_404_NOT_FOUND)

        try:
            address_obj = UserAddress.objects.get(id=addr_id, user=user, status=True)
        except UserAddress.DoesNotExist:
            return Response({"message": "address id not assigned with userID , Please mention the correct id."}, status=status.HTTP_404_NOT_FOUND)

        address_type = request.data.get('address_type')
        tag = request.data.get('tag')
        is_default = request.data.get('is_default')
        address_payload = request.data.get('address')

        if address_type:
            normalized_type = str(address_type).strip().lower()
            if normalized_type not in {"home", "work", "other"}:
                return Response({"message": "Invalid address_type. Allowed: home, work, other"}, status=status.HTTP_400_BAD_REQUEST)
            address_obj.address_type = normalized_type
            if normalized_type == 'other' and not tag and address_obj.tag in (None, ''):
                return Response({"message": "you mention \"other\" in \"address_type\" , Please mention the tag."}, status=status.HTTP_400_BAD_REQUEST)

        if tag is not None:
            address_obj.tag = tag
        if address_payload is not None:
            address_obj.address = address_payload

        def to_bool(val):
            if val is None:
                return None
            if isinstance(val, bool):
                return val
            if isinstance(val, (int, float)):
                return bool(int(val))
            if isinstance(val, str):
                return val.strip() in {"1", "true", "True"}
            return None

        is_default_bool = to_bool(is_default)
        if is_default_bool is not None:
            if is_default_bool:
                # Make this the only default: clear others first, then set this one as default
                with transaction.atomic():
                    self._ensure_single_default(user, keep_id=address_obj.id)
                    address_obj.is_default = True
                    address_obj.save()
            else:
                address_obj.is_default = False
                address_obj.save()
        else:
            address_obj.save()

        # user_details = self._user_details(request, user)
        addresses = self._list_user_addresses(user)
        return Response({
            "message": "Address updated successfully",
            # "user_details": user_details,
            "user_address": addresses
        }, status=status.HTTP_200_OK)

    @swagger_auto_schema(
        tags=['Core'],
        manual_parameters=[
            openapi.Parameter(
                'userID',
                openapi.IN_QUERY,
                description='User ID for address deletion',
                type=openapi.TYPE_STRING,
                required=True
            ),
            openapi.Parameter(
                'id',
                openapi.IN_QUERY,
                description='Address ID to delete',
                type=openapi.TYPE_INTEGER,
                required=True
            ),
        ],
        responses={
            200: openapi.Response(
                description='Address deleted successfully',
                examples={
                    'application/json': {
                        'message': 'Address deleted successfully',
                        'user_address': [
                            {
                                'id': 1,
                                'address_type': 'home',
                                'tag': None,
                                'is_default': False,
                                'address': '{"Door no": "123", "street": "Main St", "city/town": "City", "state": "State", "pincode": "123456", "country": "India"}',
                                'status': True
                            }
                        ]
                    }
                }
            ),
            400: openapi.Response(
                description='Bad request - missing parameters',
                examples={
                    'application/json': {
                        'message': 'user_id not found'
                    }
                }
            ),
            404: openapi.Response(
                description='User or address not found',
                examples={
                    'application/json': {
                        'message': 'user_id not found'
                    }
                }
            )
        }
    )
    def delete(self, request, *args, **kwargs):
        user_id = request.query_params.get('userID')
        addr_id = request.query_params.get('id')
        if not user_id:
            return Response({"message": "user_id not found"}, status=status.HTTP_400_BAD_REQUEST)
        if not addr_id:
            return Response({"message": "address id not assigned with userID , Please mention the correct id."}, status=status.HTTP_400_BAD_REQUEST)
        
        # Handle JWT token objects sent as userID parameter
        import json
        if user_id and user_id.startswith('{'):
            try:
                token_data = json.loads(user_id)
                # Extract numeric user_id from token
                user_id = token_data.get('user_id') or token_data.get('id')
            except (ValueError, TypeError):
                pass
        
        # Ensure user_id is numeric
        try:
            user_id = int(user_id)
        except (ValueError, TypeError):
            return Response({"message": "Invalid userID format. Expected numeric user_id or valid JWT token."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            user = Registration.objects.get(user_id=user_id)
        except Registration.DoesNotExist:
            return Response({"message": "user_id not found"}, status=status.HTTP_404_NOT_FOUND)

        try:
            address_obj = UserAddress.objects.get(id=addr_id, user=user, status=True)
        except UserAddress.DoesNotExist:
            return Response({"message": "address id not assigned with userID , Please mention the correct id."}, status=status.HTTP_404_NOT_FOUND)

        address_obj.status = False
        address_obj.is_default = False
        address_obj.save()

        addresses = self._list_user_addresses(user)
        return Response({
            "message": "Address deleted successfully",
            "user_address": addresses
        }, status=status.HTTP_200_OK)

class UserComprehensiveDetailsAPIView(APIView):
    """
    POST /user-comprehensive?userID={value}&whichapp=kirazee

    Modes supported based on user_mode column:
    - consumer: returns user_details, user_address
    - retail_business: returns user_details, user_address, bussiness_owner_details, user_business
    - delivery_partner: returns user_details, user_address

    Uses RAW SQL for all fetches as requested.
    """

    def _mask_sensitive_financial_data(self, financial_details):
        """
        Mask sensitive Razorpay keys and webhook secrets in financial data.
        Replaces actual values with 'rzy_*****' format.
        """
        if not financial_details:
            return financial_details
            
        # Fields to mask
        sensitive_fields = [
            'razor_pay_key_id',
            'razor_pay_key_code', 
            'razor_webhook_secret'
        ]
        
        # Create a copy to avoid modifying the original
        masked_details = financial_details.copy()
        
        for field in sensitive_fields:
            if masked_details.get(field) and masked_details[field] != '':
                masked_details[field] = 'rzy_*****'
        
        # Also mask gateway_credentials if it contains sensitive data
        if masked_details.get('gateway_credentials'):
            try:
                import json
                gateway_creds = json.loads(masked_details['gateway_credentials']) if isinstance(masked_details['gateway_credentials'], str) else masked_details['gateway_credentials']
                if isinstance(gateway_creds, dict):
                    # Mask common sensitive keys in gateway_credentials
                    sensitive_gateway_keys = ['key_id', 'key_code', 'webhook_secret', 'api_key', 'secret']
                    for key in sensitive_gateway_keys:
                        if key in gateway_creds and gateway_creds[key]:
                            gateway_creds[key] = 'rzy_*****'
                    masked_details['gateway_credentials'] = json.dumps(gateway_creds)
            except Exception:
                # If JSON parsing fails, mask the entire field
                masked_details['gateway_credentials'] = 'rzy_*****'
        
        return masked_details

    def _dictfetchall(self, cursor):
        columns = [col[0] for col in cursor.description]
        return [dict(zip(columns, row)) for row in cursor.fetchall()]

    def _dictfetchone(self, cursor):
        row = cursor.fetchone()
        if row is None:
            return None
        columns = [col[0] for col in cursor.description]
        return dict(zip(columns, row))

    @swagger_auto_schema(
        tags=['Core'],
        manual_parameters=[
            openapi.Parameter(
                'userID',
                openapi.IN_QUERY,
                description='User ID to fetch comprehensive details for',
                type=openapi.TYPE_STRING,
                required=True
            ),
            openapi.Parameter(
                'whichapp',
                openapi.IN_QUERY,
                description='App identifier (kirazee)',
                type=openapi.TYPE_STRING,
                required=False
            ),
        ],
        responses={
            200: openapi.Response(
                description='User comprehensive details retrieved successfully',
                examples={
                    'application/json': {
                        'user_details': {
                            'user_id': 'string',
                            'firstName': 'string',
                            'lastName': 'string',
                            'mobileNumber': 'string',
                            'emailID': 'string',
                            'user_mode': 'consumer',
                            'profileUrl': 'string'
                        },
                        'user_address': [
                            {
                                'id': 1,
                                'address_type': 'home',
                                'address': '{"Door no": "123", "street": "Main St", "city/town": "City", "state": "State", "pincode": "123456", "country": "India"}',
                                'is_default': True
                            }
                        ],
                        'business_owner_details': {
                            'pan': 'string',
                            'aadhaar': 'string',
                            'per_mobile_number': 'string'
                        },
                        'user_business': {
                            'business_id': 'string',
                            'businessName': 'string',
                            'businessType': 'string',
                            'logo': 'string',
                            'banner': 'string'
                        }
                    }
                }
            ),
            400: openapi.Response(
                description='Bad request - missing or invalid parameters',
                examples={
                    'application/json': {
                        'message': 'userID not found'
                    }
                }
            ),
            404: openapi.Response(
                description='User not found',
                examples={
                    'application/json': {
                        'message': 'User not found'
                    }
                }
            )
        }
    )
    def post(self, request, *args, **kwargs):
        user_id = request.query_params.get('userID')
        whichapp = request.query_params.get('whichapp')

        # Validate userID first
        if not user_id:
            return Response({"message": "userID not found"}, status=status.HTTP_400_BAD_REQUEST)

        # Optional check for whichapp parameter presence as per spec (case-insensitive match to "kirazee")
        # Not filtering by whichapp in DB, just acknowledging param.
        if whichapp is None:
            # Proceeding even if not provided, spec shows it in URL, but not mandated for logic.
            pass

        # 1) Fetch user_details from registrations
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT *
                FROM registrations
                WHERE user_id = %s
                LIMIT 1
                """,
                [user_id],
            )
            user_details = self._dictfetchone(cursor)

        # Ensure profileUrl is a full absolute URL with default fallback
        if user_details is not None:
            ns_user = SimpleNamespace(**user_details)
            user_details["profileUrl"] = build_profile_url(request, ns_user)

        if not user_details:
            return Response({"message": "User not found"}, status=status.HTTP_404_NOT_FOUND)

        # Get user_mode from user_details and normalize it
        user_mode = user_details.get('user_mode')
        user_type = user_details.get('user_type')  # Check user_type for company employees
        
        mode_norm = (str(user_mode).strip().lower().replace(" ", "_") if user_mode else None)
        allowed = {"consumer", "retail_business", "retail_business_owner", "delivery_partner", "vendor"}
        if mode_norm not in allowed:
            # Check if user is a company employee/admin
            if user_type in ["company_admin", "company_employee"]:
                mode_norm = "company_employee"  # Treat company users as separate mode
            else:
                return Response({"message": "unable to recognize the user mode."}, status=status.HTTP_400_BAD_REQUEST)

        # 2) Fetch user_address from user_address (only active)
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT *
                FROM user_address
                WHERE user_id = %s AND status = 1
                ORDER BY is_default DESC, updated_at DESC, created_at DESC
                """,
                [user_id],
            )
            user_address = self._dictfetchall(cursor)

        # Base payload
        payload = {
            "user_details": user_details,
            "user_address": user_address,
        }

        if mode_norm == "retail_business" or mode_norm == "retail_business_owner":
            # Check verification status for retail business users
            is_verified = user_details.get('is_verified', 0)
            verification_status_map = {
                0: "pending",
                1: "approved", 
                2: "rejected",
                3: "processing"
            }
            
            # Add verification status to user_details
            user_details["verification_status"] = verification_status_map.get(is_verified, "pending")

            # 3) Identify user's business via business_mapping and fetch from businesses
            user_business = None
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT bm.business_id
                    FROM business_mapping bm
                    WHERE bm.user_id = %s AND bm.status = 1
                    LIMIT 1
                    """,
                    [user_id],
                )
                mapping = self._dictfetchone(cursor)

            if mapping and mapping.get("business_id"):
                with connection.cursor() as cursor:
                    cursor.execute(
                        """
                        SELECT *
                        FROM businesses
                        WHERE business_id = %s
                        LIMIT 1
                        """,
                        [mapping["business_id"]],
                    )
                    user_business = self._dictfetchone(cursor)

            # 3) Fetch user_business_details from business_financials
            user_financial_details = None
            if mapping and mapping.get("business_id"):
                with connection.cursor() as cursor:
                    cursor.execute(
                        """
                        SELECT *
                        FROM business_financials
                        WHERE business_id = %s
                        LIMIT 1
                        """,
                        [mapping["business_id"]],
                    )
                    user_financial_details = self._dictfetchone(cursor)

            # Expand business_features from IDs to details mapping
            if user_business and user_business.get("business_features"):
                features_raw = user_business.get("business_features")
                try:
                    feature_ids = json.loads(features_raw) if isinstance(features_raw, str) else features_raw
                except Exception:
                    feature_ids = []
                if isinstance(feature_ids, list) and feature_ids:
                    # Fetch details for these feature IDs
                    placeholders = ",".join(["%s"] * len(feature_ids))
                    with connection.cursor() as cursor:
                        cursor.execute(
                            f"""
                            SELECT feature_id, details
                            FROM business_features
                            WHERE feature_id IN ({placeholders})
                            """,
                            feature_ids,
                        )
                        rows = cursor.fetchall()
                        # rows come as list of tuples; build map
                        available = {r[0]: r[1] for r in rows}
                    expanded = {fid: available.get(fid, "unknown") for fid in feature_ids}
                    user_business["business_features"] = expanded

            # Apply base URL presentation for logo and banner on main business
            if user_business is not None:
                ns = SimpleNamespace(**user_business)
                user_business["logo"] = build_business_logo_url(request, ns)
                user_business["banner"] = build_business_banner_url(request, ns)
                
                # Add verification status to business data
                business_is_verified = user_business.get('is_verified', 0)
                user_business["verification_status"] = verification_status_map.get(business_is_verified, "pending")
                
                # Add business type details from business_types table
                business_type_code = user_business.get("businessType")
                if business_type_code:
                    with connection.cursor() as cursor:
                        cursor.execute(
                            """
                            SELECT code, type, categories
                            FROM business_types
                            WHERE code = %s
                            LIMIT 1
                            """,
                            [business_type_code],
                        )
                        business_type_details = self._dictfetchone(cursor)
                        if business_type_details:
                            user_business["businessTypeDetails"] = business_type_details

            # Attach sublevel businesses if this is a master business
            if user_business:
                level_val = str(user_business.get("level") or "").strip().lower()
                if level_val == "master":
                    sub_levels = []
                    with connection.cursor() as cursor:
                        cursor.execute(
                            """
                            SELECT *
                            FROM businesses
                            WHERE master = %s AND status = 1
                            ORDER BY created_at ASC
                            """,
                            [user_business.get("business_id")],
                        )
                        sub_rows = self._dictfetchall(cursor)

                    # For each sublevel, expand its business_features
                    for sb in sub_rows:
                        sb_features_raw = sb.get("business_features")
                        try:
                            sb_ids = json.loads(sb_features_raw) if isinstance(sb_features_raw, str) else sb_features_raw
                        except Exception:
                            sb_ids = []
                        if isinstance(sb_ids, list) and sb_ids:
                            placeholders = ",".join(["%s"] * len(sb_ids))
                            with connection.cursor() as cursor:
                                cursor.execute(
                                    f"""
                                    SELECT feature_id, details
                                    FROM business_features
                                    WHERE feature_id IN ({placeholders})
                                    """,
                                    sb_ids,
                                )
                                rows = cursor.fetchall()
                                available = {r[0]: r[1] for r in rows}
                            sb["business_features"] = {fid: available.get(fid, "unknown") for fid in sb_ids}
                        else:
                            sb["business_features"] = {}
                        # Apply base URL presentation for each sublevel logo/banner
                        sb_ns = SimpleNamespace(**sb)
                        sb["logo"] = build_business_logo_url(request, sb_ns)
                        sb["banner"] = build_business_banner_url(request, sb_ns)
                        
                        # Add verification status to sublevel business
                        sb_is_verified = sb.get('is_verified', 0)
                        sb["verification_status"] = verification_status_map.get(sb_is_verified, "pending")
                        
                        sub_levels.append(sb)

                    user_business["sub_level"] = sub_levels
                elif level_val == "sublevel":
                    master_id = user_business.get("master")
                    master_obj = None
                    if master_id:
                        with connection.cursor() as cursor:
                            cursor.execute(
                                """
                                SELECT *
                                FROM businesses
                                WHERE business_id = %s AND status = 1
                                LIMIT 1
                                """,
                                [master_id],
                            )
                            master_obj = self._dictfetchone(cursor)
                        # expand features for master too
                        if master_obj and master_obj.get("business_features"):
                            m_features_raw = master_obj.get("business_features")
                            try:
                                m_ids = json.loads(m_features_raw) if isinstance(m_features_raw, str) else m_features_raw
                            except Exception:
                                m_ids = []
                            if isinstance(m_ids, list) and m_ids:
                                placeholders = ",".join(["%s"] * len(m_ids))
                                with connection.cursor() as cursor:
                                    cursor.execute(
                                        f"""
                                        SELECT feature_id, details
                                        FROM business_features
                                        WHERE feature_id IN ({placeholders})
                                        """,
                                        m_ids,
                                    )
                                    rows = cursor.fetchall()
                                    available = {r[0]: r[1] for r in rows}
                                master_obj["business_features"] = {fid: available.get(fid, "unknown") for fid in m_ids}
                        # Apply base URL presentation for master logo/banner
                        if master_obj:
                            m_ns = SimpleNamespace(**master_obj)
                            master_obj["logo"] = build_business_logo_url(request, m_ns)
                            master_obj["banner"] = build_business_banner_url(request, m_ns)
                            
                            # Add verification status to master business
                            master_is_verified = master_obj.get('is_verified', 0)
                            master_obj["verification_status"] = verification_status_map.get(master_is_verified, "pending")
                            
                    user_business["sub_level"] = master_obj

            payload.update({
                "business_financial_details": self._mask_sensitive_financial_data(user_financial_details),
                "user_business": user_business,
            })

        elif mode_norm == "company_employee":
            # Handle company employees and admins
            try:
                from .models import CompanyRegistration
                company_id = user_details.get('company_id')
                
                if company_id:
                    # Fetch company details using Django ORM for better error handling
                    try:
                        company = CompanyRegistration.objects.get(company_id=company_id)
                        
                        company_details = {
                            "company_id": company.company_id,
                            "company_name": company.company_name,
                            "gst_number": company.gst_number,
                            "business_type": company.business_type,
                            "contact_person_name": company.contact_person_name,
                            "contact_person_email": company.contact_person_email,
                            "contact_person_phone": company.contact_person_phone,
                            "business_address": company.business_address,
                            "verification_status": company.verification_status,
                            "approved_at": company.approved_at,
                            "created_at": company.created_at,
                            "updated_at": company.updated_at
                        }
                        
                        # Add employee details from user_details
                        employee_details = {
                            "employee_id": user_details.get('employee_id'),
                            "employee_role": user_details.get('employee_role'),
                            "department": user_details.get('department'),
                            "joined_company_at": user_details.get('joined_company_at'),
                            "is_verified": user_details.get('is_verified', False),
                            "purchase_limit": user_details.get('purchase_limit'),
                            "reporting_manager": user_details.get('reporting_manager'),
                            "can_approve_orders": user_details.get('can_approve_orders', False)
                        }
                        
                        payload.update({
                            "company_details": company_details,
                            "employee_details": employee_details,
                        })
                        
                    except CompanyRegistration.DoesNotExist:
                        # Company not found, continue without company details
                        pass
                        
            except Exception as e:
                print(f"Error fetching company details for comprehensive view: {e}")

        return Response(payload, status=status.HTTP_200_OK)

class NavigationAPIView(APIView):
    """
    GET /navigation?mode={mode}&category={category}&business_id={id}
    
    Returns navigation items based on user mode and current context.
    
    Examples:
    - /navigation?mode=consumer -> Main consumer navigation (home, categories, orders, profile)
    - /navigation?mode=consumer&category=restaurants -> Restaurant category navigation
    - /navigation?mode=consumer&category=restaurants&business_id=123 -> Restaurant menu navigation
    - /navigation?mode=consumer&category=groceries -> Grocery category navigation
    - /navigation?mode=consumer&category=groceries&business_id=456 -> Grocery products navigation
    """
    
    @swagger_auto_schema(
        tags=['Core'],
        manual_parameters=[
            openapi.Parameter(
                'mode',
                openapi.IN_QUERY,
                description='User mode (consumer, retail_business, retail_business_owner, delivery_partner, company_admin, company_employee)',
                type=openapi.TYPE_STRING,
                required=True,
                enum=['consumer', 'retail_business', 'retail_business_owner', 'delivery_partner', 'company_admin', 'company_employee']
            ),
            openapi.Parameter(
                'category',
                openapi.IN_QUERY,
                description='Category context (restaurants, groceries, orders, profile)',
                type=openapi.TYPE_STRING,
                required=False
            ),
            openapi.Parameter(
                'business_id',
                openapi.IN_QUERY,
                description='Business ID for specific business context',
                type=openapi.TYPE_STRING,
                required=False
            ),
            openapi.Parameter(
                'type',
                openapi.IN_QUERY,
                description='Business type code (R02 for restaurants, etc.)',
                type=openapi.TYPE_STRING,
                required=False
            ),
        ],
        responses={
            200: openapi.Response(
                description='Navigation items retrieved successfully',
                examples={
                    'application/json': {
                        'navigation': [
                            {
                                'id': 'consumer_home',
                                'label': 'Home',
                                'icon': 'home',
                                'route': '/home',
                                'order': 1,
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
                        'message': 'mode parameter is required'
                    }
                }
            )
        }
    )
    def get(self, request, *args, **kwargs):
        mode = request.query_params.get('mode', '').strip().lower()
        category = request.query_params.get('category', '').strip().lower()
        business_id = request.query_params.get('business_id', '').strip()
        business_type = request.query_params.get('type', '').strip().upper()
        
        # Validate mode
        if not mode:
            return Response({"message": "mode parameter is required"}, status=status.HTTP_400_BAD_REQUEST)
        
        allowed_modes = {"consumer", "retail_business", "retail_business_owner", "delivery_partner", "company_admin", "company_employee"}
        if mode not in allowed_modes:
            return Response({"message": "Invalid mode. Allowed: consumer, retail_business, retail_business_owner, delivery_partner, company_admin, company_employee"}, status=status.HTTP_400_BAD_REQUEST)
        
        # Build navigation based on context
        navigation_items = []
        
        if mode == "consumer":
            navigation_items = self._get_consumer_navigation(category, business_id)
        elif mode == "retail_business" or mode == "retail_business_owner":
            navigation_items = self._get_business_navigation(category, business_id, business_type)
        elif mode == "delivery_partner":
            # Future implementation for delivery partner mode
            navigation_items = self._get_delivery_navigation(category, business_id)
        elif mode == "company_admin" or mode == "company_employee":
            # Company employee navigation
            navigation_items = self._get_company_navigation(category, business_id)
        
        return Response({
            "navigation": navigation_items
        }, status=status.HTTP_200_OK)
    
    def _get_consumer_navigation(self, category, business_id):
        """Get consumer mode navigation based on current context"""
        
        if not category:
            # Main consumer navigation: Home, Categories, Orders, Profile
            return self._get_navigation_items(['consumer_home', 'consumer_categories', 'consumer_orders', 'consumer_profile'])
        
        elif category == "restaurants" or category == "resturants":  # Handle typo in sample data
            if business_id:
                # Restaurant menu navigation: Back, Restaurants, Menu, Rewards, Cart
                return self._get_navigation_items([
                    'consumer_back_to_main',
                    'consumer_cat_restaurants', 
                    'consumer_menu',
                    'consumer_rewards_for res',
                    'consumer_cart_for_res'
                ])
            else:
                # Restaurant category navigation: Back, Restaurants, Rewards, Cart
                return self._get_navigation_items([
                    'consumer_back_to_main',
                    'consumer_cat_restaurants',
                    'consumer_rewards_for res', 
                    'consumer_cart_for_res'
                ])
        
        elif category == "groceries":
            if business_id:
                # Grocery products navigation: Back, Groceries, Products, Rewards, Cart
                return self._get_navigation_items([
                    'consumer_back_to_main',
                    'consumer_cat_groceries',
                    'consumer_products',
                    'consumer_rewards_for groc',
                    'consumer_cart_for_groc'
                ])
            else:
                # Grocery category navigation: Back, Groceries, Rewards, Cart
                return self._get_navigation_items([
                    'consumer_back_to_main',
                    'consumer_cat_groceries',
                    'consumer_rewards_for groc',
                    'consumer_cart_for_groc'
                ])
        
        else:
            # Unknown category, return main navigation
            return self._get_navigation_items(['consumer_home', 'consumer_categories', 'consumer_orders', 'consumer_profile'])
    
    def _get_business_navigation(self, category, business_id, business_type=None):
        """Get retail business mode navigation based on business type"""
        
        # For retail_business_owner mode with business type R02 (Restaurant)
        if business_type == "R02":
            return self._get_navigation_items([
                'rbo_dashboard',
                'rbo_purchases', 
                'rbo_inventory',
                'rbo_expenses',
                'rbo_orders',
                'rbo_sales',
                'rbo_reports',
                'rbo_staff',
                'rbo_supplier',
                'rbo_app_settings'
            ])
        
        # Default business navigation (can be extended for other business types)
        return []
    
    def _get_delivery_navigation(self, category, business_id):
        """Get delivery partner mode navigation - placeholder for future implementation"""
        return []
    
    def _get_company_navigation(self, category, business_id):
        """Get company employee/admin navigation based on current context"""
        
        if not category:
            # Main company navigation: Home, Orders, Profile, Company Info
            return self._get_navigation_items(['company_home', 'company_orders', 'company_profile', 'company_info'])
        
        elif category == "orders":
            if business_id:
                # Company orders navigation: Back, Orders, Order Details
                return self._get_navigation_items([
                    'company_back_to_main',
                    'company_orders',
                    'company_order_details'
                ])
            else:
                # Orders category navigation
                return self._get_navigation_items([
                    'company_back_to_main',
                    'company_orders'
                ])
        
        elif category == "profile":
            # Company profile navigation: Back, Profile, Settings
            return self._get_navigation_items([
                'company_back_to_main',
                'company_profile',
                'company_settings'
            ])
        
        else:
            # Unknown category, return main company navigation
            return self._get_navigation_items(['company_home', 'company_orders', 'company_profile', 'company_info'])
    
    def _get_navigation_items(self, item_ids):
        """Fetch navigation items by IDs and serialize them"""
        try:
            items = NavigationItem.objects.filter(
                id__in=item_ids,
                is_visible=True
            ).order_by('order', 'label')
            
            # Maintain the order specified in item_ids
            ordered_items = []
            for item_id in item_ids:
                item = items.filter(id=item_id).first()
                if item:
                    ordered_items.append(item)
            
            serializer = NavigationItemSerializer(ordered_items, many=True)
            return serializer.data
        except Exception as e:
            # Log error and return empty list
            print(f"Error fetching navigation items: {e}")
            return []

class SendRegistrationOTPAPIView(APIView):
    """
    API endpoint for sending registration OTP
    POST /send-otp/
    
    Expected payload:
    {
        "email": "user@example.com",
        "mobile": "1234567890",
        "name": "John Doe"
    }
    """
    
    @swagger_auto_schema(
        tags=['Core'],
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            properties={
                'email': openapi.Schema(type=openapi.TYPE_STRING, description='User email address', required=['email']),
                'mobile': openapi.Schema(type=openapi.TYPE_STRING, description='User mobile number', required=['mobile']),
                'name': openapi.Schema(type=openapi.TYPE_STRING, description='User full name', required=['name']),
            },
            required=['email', 'mobile', 'name']
        ),
        responses={
            200: openapi.Response(
                description='OTP sent successfully',
                examples={
                    'application/json': {
                        'status': 'success',
                        'message': 'Registration OTP sent successfully',
                        'data': {
                            'user_id': 'string',
                            'sent_channels': ['email', 'whatsapp'],
                            'email_sent': True,
                            'whatsapp_sent': True,
                            'user_info': {
                                'email': 'string',
                                'mobile': 'string',
                                'name': 'string'
                            }
                        }
                    }
                }
            ),
            400: openapi.Response(
                description='Bad request - missing required parameters',
                examples={
                    'application/json': {
                        'status': 'error',
                        'message': 'Missing required parameters: email, mobile, name'
                    }
                }
            ),
            500: openapi.Response(
                description='Server error - failed to send OTP',
                examples={
                    'application/json': {
                        'status': 'error',
                        'message': 'Failed to send registration OTP',
                        'error': 'string'
                    }
                }
            )
        }
    )
    def post(self, request, *args, **kwargs):
        try:
            from .utils import send_registration_otp_service
            from .models import Otp, Registration
            from django.utils import timezone
            import random
            
            # Get parameters from request
            user_email = request.data.get('email')
            user_mobile = request.data.get('mobile')
            user_name = request.data.get('name')
            
            # Validate required parameters
            if not all([user_email, user_mobile, user_name]):
                return Response({
                    'status': 'error',
                    'message': 'Missing required parameters: email, mobile, name'
                }, status=status.HTTP_400_BAD_REQUEST)
            
            # Generate 6-digit OTP
            otp_code = ''.join([str(random.randint(0, 9)) for _ in range(6)])
            
            print(f"🔐 Generated OTP for registration: {otp_code}")
            print(f"📧 Email: {user_email}")
            print(f"📱 Mobile: {user_mobile}")
            print(f"👤 User Name: {user_name}")
            
            # Check if a registration with this mobile number already exists
            existing_user = Registration.objects.filter(mobileNumber=user_mobile).first()
            
            if existing_user:
                # User already exists - update their information
                print(f"📝 Updating existing registration for mobile: {user_mobile}")
                
                # Delete old OTP records for this user
                Otp.objects.filter(mobileNumber=existing_user).delete()
                
                # Update user details
                existing_user.firstName = user_name.split()[0] if user_name else ''
                existing_user.lastName = ' '.join(user_name.split()[1:]) if len(user_name.split()) > 1 else ''
                existing_user.emailID = user_email
                existing_user.is_verified = False  # Reset verification status
                existing_user.is_active = False
                existing_user.save()
                
                temp_user = existing_user
            else:
                # Create a new registration record
                print(f"✨ Creating new registration for mobile: {user_mobile}")
                temp_user = Registration(
                    firstName=user_name.split()[0] if user_name else '',
                    lastName=' '.join(user_name.split()[1:]) if len(user_name.split()) > 1 else '',
                    mobileNumber=user_mobile,
                    emailID=user_email,
                    is_verified=False,
                    is_active=False,  # Will be activated after OTP verification
                    user_mode='consumer'
                )
                temp_user.save()
            
            # Save OTP to database
            otp_record = Otp(
                mobileNumber=temp_user,
                emailID=user_email,
                code=otp_code,
                status=False  # 0 = not verified
            )
            otp_record.save()
            
            print(f"💾 OTP saved to database with ID: {otp_record.id}")
            
            # Send OTP using the service
            otp_result = send_registration_otp_service(
                user_email=user_email,
                user_mobile=user_mobile,
                user_name=user_name,
                otp_code=otp_code
            )
            
            # Prepare response
            if otp_result.get('success'):
                return Response({
                    'status': 'success',
                    'message': 'Registration OTP sent successfully',
                    'data': {
                        'user_id': temp_user.user_id,
                        'sent_channels': otp_result.get('sent_channels', []),
                        'email_sent': otp_result.get('email_status', {}).get('sent', False),
                        'whatsapp_sent': otp_result.get('whatsapp_status', {}).get('sent', False),
                        'user_info': {
                            'email': user_email,
                            'mobile': user_mobile,
                            'name': user_name
                        }
                    }
                }, status=status.HTTP_200_OK)
            else:
                # Only delete if this was a new user (not an existing one)
                if not existing_user:
                    temp_user.delete()
                otp_record.delete()
                
                return Response({
                    'status': 'error',
                    'message': 'Failed to send registration OTP',
                    'error': otp_result.get('message', 'Unknown error'),
                    'data': {
                        'email_status': otp_result.get('email_status', {}),
                        'whatsapp_status': otp_result.get('whatsapp_status', {})
                    }
                }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
                
        except Exception as e:
            return Response({
                'status': 'error',
                'message': 'Internal server error while sending OTP',
                'error': str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

def PrivacyPolicyView(request):
    return render(request, 'privacy_policy.html')

def TermsOfUseView(request):
    return render(request, 'terms_of_use.html')

def faqs(request):
    return render(request, 'faqs.html')

def refundPolicy(request):
    return render(request, 'refund_policy.html')

def shippingPolicy(request):
    return render(request, 'shipping_policy.html')
# Company/B2B API Views
# ==============================================================================
class CompanyRegistrationAPIView(APIView):
    """
    API endpoint for company registration
    POST /api/company/register/
    """
    
    @swagger_auto_schema(tags=['Core'], request_body=CompanyRegistrationSerializer)
    def post(self, request, *args, **kwargs):
        try:
            from django.db import transaction
            from .models import generate_user_id, UserAddress
            from django.utils import timezone
            from django.db import models
            
            with transaction.atomic():
                # Step 1: Company Registration
                serializer = CompanyRegistrationSerializer(data=request.data)
                serializer.is_valid(raise_exception=True)
                company = serializer.save()
                
                # Step 2: Create or update main contact person as company employee
                contact_person_name = company.contact_person_name
                contact_person_email = company.contact_person_email
                contact_person_phone = company.contact_person_phone
                
                # Split name into first and last name
                name_parts = contact_person_name.strip().split(' ', 1)
                first_name = name_parts[0]
                last_name = name_parts[1] if len(name_parts) > 1 else ''
                
                # Generate unique employee ID
                import random
                import string
                def generate_employee_id():
                    prefix = "EMP"
                    random_str = ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))
                    return f"{prefix}{random_str}"
                
                employee_id = generate_employee_id()
                
                # Check if user already exists by mobile or email
                existing_user = None
                try:
                    existing_user = Registration.objects.get(mobileNumber=contact_person_phone)
                    print(f"Found existing user by mobile: {existing_user.user_id}")
                except Registration.DoesNotExist:
                    try:
                        existing_user = Registration.objects.get(emailID=contact_person_email)
                        print(f"Found existing user by email: {existing_user.user_id}")
                    except Registration.DoesNotExist:
                        print("No existing user found")
                        pass
                except Registration.MultipleObjectsReturned:
                    existing_user = Registration.objects.filter(
                        models.Q(mobileNumber=contact_person_phone) | 
                        models.Q(emailID=contact_person_email)
                    ).order_by('-created_at').first()
                    print(f"Found multiple users, using most recent: {existing_user.user_id if existing_user else 'None'}")
                
                if existing_user:
                    # Update existing user to be company employee
                    print("Updating existing user...")
                    main_contact_user = existing_user
                    print(f"Before update - user_id: {main_contact_user.user_id}, user_type: {main_contact_user.user_type}")
                    
                    main_contact_user.firstName = first_name
                    main_contact_user.lastName = last_name
                    main_contact_user.emailID = contact_person_email
                    main_contact_user.mobileNumber = contact_person_phone
                    main_contact_user.countryCode = "+91"
                    main_contact_user.user_type = 'company_admin'
                    main_contact_user.company_id = company.company_id
                    main_contact_user.employee_role = 'main'
                    main_contact_user.department = None
                    main_contact_user.employee_id = employee_id
                    main_contact_user.is_verified = False
                    main_contact_user.joined_company_at = timezone.now()
                    main_contact_user.is_active = True
                    main_contact_user.updated_at = timezone.now()
                    
                    try:
                        main_contact_user.save()
                        print(f"Successfully updated user with user_id: {main_contact_user.user_id}")
                    except Exception as update_error:
                        print(f"Error updating user: {update_error}")
                        print(f"Error type: {type(update_error)}")
                        raise update_error
                else:
                    # Create new user registration for main contact person
                    print("Creating new user registration...")
                    print(f"firstName: {first_name}")
                    print(f"lastName: {last_name}")
                    print(f"email: {contact_person_email}")
                    print(f"phone: {contact_person_phone}")
                    
                    try:
                        main_contact_user = Registration.objects.create(
                            firstName=first_name,
                            lastName=last_name,
                            emailID=contact_person_email,
                            mobileNumber=contact_person_phone,
                            countryCode="+91",  # Default country code
                            user_type='company_admin',
                            company_id=company.company_id,
                            employee_role='main',  # Default main role
                            department=None,  # Will be set later
                            employee_id=employee_id,
                            is_verified=False,  # Auto-verify main contact person
                            joined_company_at=timezone.now(),
                            is_active=True,
                            created_at=timezone.now(),
                            updated_at=timezone.now()
                        )
                        print(f"Successfully created user with user_id: {main_contact_user.user_id}")
                    except Exception as create_error:
                        print(f"Error creating user: {create_error}")
                        print(f"Error type: {type(create_error)}")
                        raise create_error
                
                # Step 3: Save business address to user_address table with company_id
                if company.business_address:
                    print("Creating business address...")
                    print(f"Company ID: {company.company_id}")
                    print(f"Business address: {company.business_address}")
                    
                    try:
                        business_address_data = {
                            "address_line1": company.business_address.get('address_line1', ''),
                            "address_line2": company.business_address.get('address_line2', ''),
                            "city": company.business_address.get('city', ''),
                            "state": company.business_address.get('state', ''),
                            "pincode": company.business_address.get('pincode', ''),
                            "country": company.business_address.get('country', 'India'),
                            "landmark": company.business_address.get('landmark', ''),
                        }
                        
                        print(f"Business address data: {business_address_data}")
                        
                        # Create company business address
                        user_address = UserAddress.objects.create(
                            user=main_contact_user,  # Use the main contact user for company addresses
                            company_id=company.company_id,  # Link to company
                            address_type='work',  # Business address
                            tag='Business Address',  # Default tag
                            is_default=True,  # Make it default
                            address=business_address_data,
                            status=True,
                            created_at=timezone.now(),
                            updated_at=timezone.now()
                        )
                        print(f"Successfully created business address with ID: {user_address.id}")
                    except Exception as address_error:
                        print(f"Error creating business address: {address_error}")
                        print(f"Error type: {type(address_error)}")
                        raise address_error
                else:
                    print("No business address provided, skipping address creation.")
                
                # Send verification email/SMS
                # TODO: Implement email/SMS verification
                
                return Response({
                    'status': 'success',
                    'message': 'Company registration successful. Main contact person registered as employee.',
                    'data': {
                        'company': {
                            'company_id': company.company_id,
                            'company_name': company.company_name,
                            'gst_number': company.gst_number,
                            'verification_status': company.verification_status,
                            'created_at': company.created_at
                        },
                        'main_contact_user': {
                            'user_id': main_contact_user.user_id,
                            'name': f"{main_contact_user.firstName} {main_contact_user.lastName}",
                            'email': main_contact_user.emailID,
                            'phone': f"{main_contact_user.countryCode}{main_contact_user.mobileNumber}",
                            'employee_id': main_contact_user.employee_id,
                            'employee_role': main_contact_user.employee_role,
                            'company_id': main_contact_user.company_id,
                            'is_verified': main_contact_user.is_verified
                        },
                        'business_address_saved': True if company.business_address else False
                    }
                }, status=status.HTTP_201_CREATED)
            
        except ValidationError as e:
            return Response({
                'status': 'error',
                'message': 'Validation failed',
                'errors': e.detail
            }, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            error_msg = str(e)
            
            # Handle specific database errors
            if "Column 'user_id' cannot be null" in error_msg:
                return Response({
                    'status': 'error',
                    'message': 'User ID generation failed. Please try again.',
                    'error': 'Database constraint violation: user_id cannot be null'
                }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
            elif "Duplicate entry" in error_msg and "mobileNumber" in error_msg:
                return Response({
                    'status': 'error',
                    'message': 'Mobile number already exists',
                    'error': 'A user with this mobile number is already registered'
                }, status=status.HTTP_400_BAD_REQUEST)
            elif "Duplicate entry" in error_msg and "emailID" in error_msg:
                return Response({
                    'status': 'error',
                    'message': 'Email already exists',
                    'error': 'A user with this email is already registered'
                }, status=status.HTTP_400_BAD_REQUEST)
            else:
                return Response({
                    'status': 'error',
                    'message': 'Registration failed',
                    'error': error_msg
                }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

class CompanyVerificationAPIView(APIView):
    """
    API endpoint for company verification (admin use)
    POST /api/company/verify/{company_id}/
    """
    
    def post(self, request, company_id, *args, **kwargs):
        try:
            company = CompanyRegistration.objects.get(company_id=company_id)
            
            # Check if user is admin (you might want to add proper authentication)
            # TODO: Add admin authentication
            
            serializer = CompanyVerificationSerializer(company, data=request.data, partial=True)
            serializer.is_valid(raise_exception=True)
            updated_company = serializer.save()
            
            return Response({
                'status': 'success',
                'message': f'Company verification status updated to {updated_company.verification_status}',
                'data': {
                    'company_id': updated_company.company_id,
                    'verification_status': updated_company.verification_status,
                    'approved_at': updated_company.approved_at
                }
            }, status=status.HTTP_200_OK)
            
        except CompanyRegistration.DoesNotExist:
            return Response({
                'status': 'error',
                'message': 'Company not found'
            }, status=status.HTTP_404_NOT_FOUND)
        except ValidationError as e:
            return Response({
                'status': 'error',
                'message': 'Validation failed',
                'errors': e.detail
            }, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            return Response({
                'status': 'error',
                'message': 'Verification update failed',
                'error': str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

class CompanyListAPIView(APIView):
    """
    API endpoint to list companies (admin use)
    GET /api/company/list/
    """
    
    @swagger_auto_schema(tags=['Core'])
    def get(self, request, *args, **kwargs):
        try:
            # TODO: Add admin authentication
            
            verification_status = request.query_params.get('verification_status')
            companies = CompanyRegistration.objects.all()
            
            if verification_status:
                companies = companies.filter(verification_status=verification_status)
            
            # Order by creation date (newest first)
            companies = companies.order_by('-created_at')
            
            # Serialize data
            serializer = CompanyRegistrationSerializer(companies, many=True)
            
            return Response({
                'status': 'success',
                'message': f'Found {companies.count()} companies',
                'data': serializer.data
            }, status=status.HTTP_200_OK)
            
        except Exception as e:
            return Response({
                'status': 'error',
                'message': 'Failed to fetch companies',
                'error': str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

class CompanyDetailAPIView(APIView):
    """
    API endpoint for company details
    GET /api/company/{company_id}/
    PUT /api/company/{company_id}/
    """
    
    @swagger_auto_schema(tags=['Core'])
    def get(self, request, company_id, *args, **kwargs):
        try:
            company = CompanyRegistration.objects.get(company_id=company_id)
            serializer = CompanyRegistrationSerializer(company)
            
            response_data = {
                'status': 'success',
                'data': serializer.data
            }
            
            # Check if employees should be included
            include_employees = request.query_params.get('include') == 'employees'
            if include_employees:
                # Get all employees for this company
                employees = Registration.objects.filter(
                    company_id=company_id,
                    user_type='company_employee'
                ).order_by('-joined_company_at')
                
                employees_data = []
                for employee in employees:
                    employee_info = {
                        'user_id': employee.user_id,
                        'firstName': employee.firstName,
                        'lastName': employee.lastName,
                        'emailID': employee.emailID,
                        'mobileNumber': employee.mobileNumber,
                        'countryCode': employee.countryCode,
                        'employee_role': getattr(employee, 'employee_role', None),
                        'department': getattr(employee, 'department', None),
                        'employee_id': getattr(employee, 'employee_id', None),
                        'purchase_limit': getattr(employee, 'purchase_limit', None),
                        'reporting_manager': getattr(employee, 'reporting_manager', None),
                        'can_approve_orders': getattr(employee, 'can_approve_orders', False),
                        'is_verified': employee.is_verified,
                        'joined_company_at': getattr(employee, 'joined_company_at', None),
                        'verification_documents': getattr(employee, 'verification_documents', None)
                    }
                    employees_data.append(employee_info)
                
                response_data['employees'] = {
                    'count': len(employees_data),
                    'employees': employees_data
                }
            
            return Response(response_data, status=status.HTTP_200_OK)
            
        except CompanyRegistration.DoesNotExist:
            return Response({
                'status': 'error',
                'message': 'Company not found'
            }, status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            return Response({
                'status': 'error',
                'message': 'Failed to fetch company details',
                'error': str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    
    @swagger_auto_schema(tags=['Core'], request_body=CompanyRegistrationUpdateSerializer)
    def put(self, request, company_id, *args, **kwargs):
        try:
            company = CompanyRegistration.objects.get(company_id=company_id)
            
            # Check if user can update this company
            # TODO: Add proper authentication/authorization
            
            serializer = CompanyRegistrationUpdateSerializer(company, data=request.data, partial=True)
            serializer.is_valid(raise_exception=True)
            updated_company = serializer.save()
            
            return Response({
                'status': 'success',
                'message': 'Company details updated successfully',
                'data': CompanyRegistrationSerializer(updated_company).data
            }, status=status.HTTP_200_OK)
            
        except CompanyRegistration.DoesNotExist:
            return Response({
                'status': 'error',
                'message': 'Company not found'
            }, status=status.HTTP_404_NOT_FOUND)
        except ValidationError as e:
            return Response({
                'status': 'error',
                'message': 'Validation failed',
                'errors': e.detail
            }, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            return Response({
                'status': 'error',
                'message': 'Failed to update company',
                'error': str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

class CompanyEmployeeListAPIView(APIView):
    """
    API endpoint for listing employees of a company
    GET /api/company/{company_id}/employees/
    """
    
    @swagger_auto_schema(tags=['Core'])
    def get(self, request, company_id, *args, **kwargs):
        try:
            # Check if company exists
            company = CompanyRegistration.objects.get(company_id=company_id)
            
            # Get query parameters for filtering
            department = request.query_params.get('department')
            role = request.query_params.get('role')
            is_verified = request.query_params.get('verified')
            
            # Build query - include both company admins and employees
            employees_query = Registration.objects.filter(
                company_id=company_id,
                user_type__in=['company_admin', 'company_employee']
            )
            
            # Apply filters
            if department:
                employees_query = employees_query.filter(department__iexact=department)
            
            if role:
                employees_query = employees_query.filter(employee_role__iexact=role)
            
            if is_verified is not None:
                if is_verified.lower() == 'true':
                    employees_query = employees_query.filter(is_verified=True)
                elif is_verified.lower() == 'false':
                    employees_query = employees_query.filter(is_verified=False)
            
            # Order by join date (newest first)
            employees = employees_query.order_by('-joined_company_at')
            
            # Serialize employee data with comprehensive details
            employees_data = []
            for employee in employees:
                employee_info = {
                    'user_id': employee.user_id,
                    'firstName': employee.firstName,
                    'lastName': employee.lastName,
                    'fullName': f"{employee.firstName} {employee.lastName}".strip(),
                    'emailID': employee.emailID,
                    'mobileNumber': employee.mobileNumber,
                    'countryCode': employee.countryCode,
                    'fullPhoneNumber': f"{employee.countryCode}{employee.mobileNumber}",
                    'user_type': employee.user_type,
                    'employee_role': getattr(employee, 'employee_role', None),
                    'department': getattr(employee, 'department', None),
                    'employee_id': getattr(employee, 'employee_id', None),
                    'purchase_limit': getattr(employee, 'purchase_limit', None),
                    'reporting_manager': getattr(employee, 'reporting_manager', None),
                    'can_approve_orders': getattr(employee, 'can_approve_orders', False),
                    'is_verified': employee.is_verified,
                    'is_active': employee.is_active,
                    'status': employee.status,
                    'joined_company_at': getattr(employee, 'joined_company_at', None),
                    'created_at': employee.created_at,
                    'updated_at': employee.updated_at,
                    'verification_documents': getattr(employee, 'verification_documents', None),
                    'profileUrl': f"/media/profiles/{employee.user_id}.jpg" if hasattr(employee, 'profileUrl') and employee.profileUrl else None,
                    'company_id': getattr(employee, 'company_id', None)
                }
                employees_data.append(employee_info)
            
            # Get summary statistics
            total_employees = len(employees_data)
            verified_count = len([e for e in employees_data if e['is_verified']])
            unverified_count = total_employees - verified_count
            
            # Group by department
            departments = {}
            for employee in employees_data:
                dept = employee['department'] or 'Unassigned'
                if dept not in departments:
                    departments[dept] = {'count': 0, 'verified': 0}
                departments[dept]['count'] += 1
                if employee['is_verified']:
                    departments[dept]['verified'] += 1
            
            return Response({
                'status': 'success',
                'message': f'Found {total_employees} employees',
                'data': {
                    'company_id': company_id,
                    'company_name': company.company_name,
                    'summary': {
                        'total_employees': total_employees,
                        'verified_employees': verified_count,
                        'unverified_employees': unverified_count,
                        'departments': departments
                    },
                    'employees': employees_data,
                    'filters_applied': {
                        'department': department,
                        'role': role,
                        'verified': is_verified
                    }
                }
            }, status=status.HTTP_200_OK)
            
        except CompanyRegistration.DoesNotExist:
            return Response({
                'status': 'error',
                'message': 'Company not found'
            }, status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            return Response({
                'status': 'error',
                'message': 'Failed to fetch employees',
                'error': str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

class CompanyEmployeeAPIView(APIView):
    """
    API endpoint for adding employees to a company
    POST /api/company/{company_id}/employees/add/
    """
    
    @swagger_auto_schema(tags=['Core'])
    def post(self, request, company_id, *args, **kwargs):
        try:
            # Check if company exists and is approved
            # company = CompanyRegistration.objects.get(company_id=company_id)
            # if not company.can_place_orders:
            #     return Response({
            #         'status': 'error',
            #         'message': 'Company is not approved to add employees'
            #     }, status=status.HTTP_400_BAD_REQUEST)
            
            # Add company_id to employee data
            employee_data = request.data.copy()
            employee_data['company_id'] = company_id
            
            # Pass company context to serializer
            serializer = CompanyEmployeeSerializer(
                data=employee_data, 
                context={'company_id': company_id}
            )
            serializer.is_valid(raise_exception=True)
            result = serializer.save()
            
            # Handle different response formats from serializer
            if isinstance(result, dict):
                # New format with detailed response
                return Response(result, status=status.HTTP_201_CREATED)
            else:
                # Legacy format (user object)
                return Response({
                    'status': 'success',
                    'message': 'Employee added successfully',
                    'data': {
                        'user_id': result.user_id,
                        'firstName': result.firstName,
                        'lastName': result.lastName,
                        'emailID': result.emailID,
                        'mobileNumber': result.mobileNumber,
                        'employee_role': getattr(result, 'employee_role', None),
                        'department': getattr(result, 'department', None),
                        'company_id': getattr(result, 'company_id', None)
                    }
                }, status=status.HTTP_201_CREATED)
            
        except CompanyRegistration.DoesNotExist:
            return Response({
                'status': 'error',
                'message': 'Company not found'
            }, status=status.HTTP_404_NOT_FOUND)
        except ValidationError as e:
            return Response({
                'status': 'error',
                'message': 'Validation failed',
                'errors': e.detail
            }, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            return Response({
                'status': 'error',
                'message': 'Failed to add employee',
                'error': str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class CompanyOrderAPIView(APIView):
    """
    API endpoint for company B2B order creation and management
    POST /api/company/{company_id}/orders/ - Create new order
    GET /api/company/{company_id}/orders/ - List orders with filtering
    
    Company orders support all the same parameters as individual orders plus:
    - ordered_by_employee: Employee user_id who placed the order
    - company_purchase_order: Company's internal PO number
    - is_bulk_order: Whether this is a bulk order
    - bulk_order_reference: Reference number for bulk orders
    - company_department: Department placing the order
    - approval_status: Order approval status
    - company_notes: Internal company notes
    """
    
    @swagger_auto_schema(tags=['Core'])
    def post(self, request, company_id, *args, **kwargs):
        """Create a new company order with full validation and approval workflow"""
        try:
            from consumer.orders import create_order
            from consumer.models import Orders
            from decimal import Decimal
            
            # Validate company exists and is approved
            try:
                company = CompanyRegistration.objects.get(company_id=company_id)
                if not company.can_place_orders:
                    return Response({
                        'success': False,
                        'error': 'Company is not approved to place orders',
                        'verification_status': company.verification_status
                    }, status=status.HTTP_403_FORBIDDEN)
            except CompanyRegistration.DoesNotExist:
                return Response({
                    'success': False,
                    'error': 'Company not found'
                }, status=status.HTTP_404_NOT_FOUND)
            
            # Extract company-specific parameters - support various names
            ordered_by_employee_id = (
                request.data.get('ordered_by_employee') or 
                request.data.get('ordered_by_employee_id') or
                request.data.get('employee_id')
            )
            company_purchase_order = request.data.get('company_purchase_order')
            is_bulk_order = bool(request.data.get('is_bulk_order', False))
            bulk_order_reference = request.data.get('bulk_order_reference')
            company_department = request.data.get('company_department') or request.data.get('department')
            company_notes = request.data.get('company_notes')
            billing_address = request.data.get('billing_address')
            credit_period_days = request.data.get('credit_period_days')
            order_reference = request.data.get('order_reference')
            order_priority = request.data.get('order_priority')
            
            # Combine notes with credit period information if provided
            if credit_period_days:
                credit_note = f"Credit Period: {credit_period_days} days"
                company_notes = f"{company_notes}\n{credit_note}" if company_notes else credit_note
            
            # Extract instructions
            delivery_instruction = request.data.get('delivery_instruction')
            order_instruction = request.data.get('order_instruction')
            
            # Validate employee if provided
            employee = None
            if ordered_by_employee_id:
                try:
                    employee = Registration.objects.get(
                        user_id=ordered_by_employee_id,
                        company_id=company_id,
                        user_type__in=['company_employee', 'company_admin'],
                        is_verified=True,
                        is_active=True
                    )
                except Registration.DoesNotExist:
                    return Response({
                        'success': False,
                        'error': 'Employee not found or not authorized for this company',
                        'employee_id': ordered_by_employee_id
                    }, status=status.HTTP_404_NOT_FOUND)
            
            # Prepare order data for create_order function
            # This includes all standard order parameters
            order_data = request.data.copy()
            
            # Map items product_id to product_item_id if needed
            if 'items' in order_data and isinstance(order_data['items'], list):
                for item in order_data['items']:
                    if 'product_id' in item and 'product_item_id' not in item:
                        item['product_item_id'] = item['product_id']
            
            # Ensure user_id is set (use employee if provided, otherwise use company admin)
            if not order_data.get('user_id'):
                if employee:
                    order_data['user_id'] = employee.user_id
                else:
                    # Find company admin as fallback
                    company_admin = Registration.objects.filter(
                        company_id=company_id,
                        user_type='company_admin',
                        is_verified=True,
                        is_active=True
                    ).first()
                    
                    if not company_admin:
                        return Response({
                            'success': False,
                            'error': 'No verified company admin found. Please specify ordered_by_employee.'
                        }, status=status.HTTP_400_BAD_REQUEST)
                    
                    order_data['user_id'] = company_admin.user_id
            
            # Create a proper Django HttpRequest object for create_order
            from django.test import RequestFactory
            import json
            from io import BytesIO
            
            factory = RequestFactory()
            # Create a request that behaves exactly like a real POST request
            mock_request = factory.post(
                f'/api/company/{company_id}/orders/',
                data=json.dumps(order_data),
                content_type='application/json'
            )
            
            # Copy authentication and user information from original request
            if hasattr(request, 'user'):
                mock_request.user = request.user
            if hasattr(request, 'auth'):
                mock_request.auth = request.auth
            
            # Additional safety for DRF Request object
            # Some DRF internals look for these specifically
            mock_request._body = json.dumps(order_data).encode('utf-8')
            stream = BytesIO(mock_request._body)
            mock_request._stream = stream
            
            # Ensure file-like methods are available on the request itself
            # because DRF's Request.stream property often returns the underlying request
            mock_request.read = stream.read
            mock_request.readline = stream.readline
            mock_request.readlines = stream.readlines
            mock_request.__iter__ = stream.__iter__
            
            # Call the existing create_order function
            order_response = create_order(mock_request)
            
            # Check if order was created successfully
            if order_response.status_code != 201:
                return order_response
            
            response_data = order_response.data
            
            if not response_data.get('success'):
                return order_response
            
            # Get the created order
            order_id = response_data.get('data', {}).get('order_id')
            if not order_id:
                return Response({
                    'success': False,
                    'error': 'Order created but order_id not found in response'
                }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
            
            # Update the order with company-specific fields
            try:
                order = Orders.objects.get(order_id=order_id)
                
                # Calculate if approval is needed based on employee purchase limit
                approval_status = 'auto_approved'
                approved_by = None
                approved_at = None
                
                if employee:
                    purchase_limit = getattr(employee, 'purchase_limit', None)
                    if purchase_limit is not None and purchase_limit > 0:
                        final_amount = Decimal(str(order.final_amount))
                        if final_amount > Decimal(str(purchase_limit)):
                            approval_status = 'pending_approval'
                
                # Update company-specific fields
                order.order_customer_type = 'company'
                order.company_id = company_id
                order.ordered_by_employee = ordered_by_employee_id
                order.company_purchase_order = company_purchase_order
                order.is_bulk_order = is_bulk_order
                order.bulk_order_reference = bulk_order_reference
                order.company_department = company_department or (getattr(employee, 'department', None) if employee else None)
                order.approval_status = approval_status
                order.approved_by = approved_by
                order.approved_at = approved_at
                order.company_notes = company_notes
                
                # Update instructions if not already set by create_order
                if delivery_instruction and not order.delivery_instruction:
                    order.delivery_instruction = delivery_instruction
                if order_instruction and not order.order_instruction:
                    order.order_instruction = order_instruction
                
                # Handle billing address snapshot
                if billing_address and isinstance(billing_address, dict):
                    order.billing_address_snapshot = {
                        'address_line1': billing_address.get('address_line1'),
                        'address_line2': billing_address.get('address_line2'),
                        'city': billing_address.get('city'),
                        'state': billing_address.get('state'),
                        'pincode': billing_address.get('pincode'),
                        'country': billing_address.get('country', 'India'),
                        'snapshot_created_at': timezone.now().isoformat()
                    }
                
                order.save(update_fields=[
                    'order_customer_type', 'company_id', 'ordered_by_employee',
                    'company_purchase_order', 'is_bulk_order', 'bulk_order_reference',
                    'company_department', 'approval_status', 'approved_by', 
                    'approved_at', 'company_notes', 'billing_address_snapshot',
                    'delivery_instruction', 'order_instruction'
                ])
                
                # Add company-specific information to response
                response_data['data'].update({
                    'order_customer_type': 'company',
                    'company_id': company_id,
                    'company_name': company.company_name,
                    'ordered_by_employee': {
                        'user_id': employee.user_id,
                        'name': f"{employee.firstName} {employee.lastName}",
                        'email': employee.emailID,
                        'phone': f"{employee.countryCode}{employee.mobileNumber}",
                        'department': getattr(employee, 'department', None),
                        'employee_id': getattr(employee, 'employee_id', None)
                    } if employee else None,
                    'company_purchase_order': company_purchase_order,
                    'is_bulk_order': is_bulk_order,
                    'bulk_order_reference': bulk_order_reference,
                    'company_department': order.company_department,
                    'approval_status': approval_status,
                    'approval_required': approval_status == 'pending_approval',
                    'company_notes': company_notes
                })
                
                # Add approval workflow information if approval is needed
                if approval_status == 'pending_approval':
                    response_data['message'] = 'Company order created successfully. Approval required before processing.'
                    response_data['data']['approval_info'] = {
                        'reason': 'Order amount exceeds employee purchase limit',
                        'employee_limit': float(purchase_limit) if purchase_limit else None,
                        'order_amount': float(order.final_amount),
                        'next_steps': 'Order will be processed after manager/admin approval'
                    }
                else:
                    response_data['message'] = 'Company order created successfully'
                
                return Response(response_data, status=status.HTTP_201_CREATED)
                
            except Orders.DoesNotExist:
                # Order was created but we couldn't update it with company fields
                # Return the original response with a warning
                response_data['warning'] = 'Order created but company-specific fields could not be updated'
                return Response(response_data, status=status.HTTP_201_CREATED)
            
        except ValidationError as e:
            return Response({
                'success': False,
                'error': 'Order validation failed',
                'details': e.detail if hasattr(e, 'detail') else str(e)
            }, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            import traceback
            return Response({
                'success': False,
                'error': 'Failed to create company order',
                'message': str(e),
                'traceback': traceback.format_exc() if getattr(settings, 'DEBUG', False) else None
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

class CompanyOrdersListAPIView(APIView):
    """
    Dedicated API endpoint for listing company orders with full filtering and summary statistics
    GET /api/company/{company_id}/orders/list/
    """
    
    @swagger_auto_schema(tags=['Core'])
    def get(self, request, company_id, *args, **kwargs):
        """List company orders with filtering"""
        try:
            from consumer.models import Orders
            from django.db.models import Q, Sum, Count
            
            # Check if company exists
            company = CompanyRegistration.objects.get(company_id=company_id)
            
            # Get query parameters for filtering
            status_filter = request.query_params.get('status', 'all')
            date_from = request.query_params.get('date_from')
            date_to = request.query_params.get('date_to')
            employee_id = request.query_params.get('employee_id')
            is_bulk_order = request.query_params.get('is_bulk_order')
            approval_status = request.query_params.get('approval_status')
            department = request.query_params.get('department')
            page = int(request.query_params.get('page', 1))
            page_size = int(request.query_params.get('page_size', 20))
            
            # Build query
            orders_query = Orders.objects.filter(
                company_id=company_id,
                order_customer_type='company'
            )
            
            # Apply filters
            if status_filter and status_filter != 'all':
                orders_query = orders_query.filter(status=status_filter)
            
            if date_from:
                from dateutil import parser as date_parser
                try:
                    date_from_dt = date_parser.parse(date_from)
                    orders_query = orders_query.filter(created_at__gte=date_from_dt)
                except Exception:
                    pass
            
            if date_to:
                from dateutil import parser as date_parser
                try:
                    date_to_dt = date_parser.parse(date_to)
                    orders_query = orders_query.filter(created_at__lte=date_to_dt)
                except Exception:
                    pass
            
            if employee_id:
                orders_query = orders_query.filter(ordered_by_employee=employee_id)
            
            if is_bulk_order is not None:
                orders_query = orders_query.filter(is_bulk_order=is_bulk_order.lower() == 'true')
            
            if approval_status:
                orders_query = orders_query.filter(approval_status=approval_status)
            
            if department:
                orders_query = orders_query.filter(company_department__iexact=department)
            
            # Get summary statistics
            summary = orders_query.aggregate(
                total_orders=Count('order_id'),
                total_amount=Sum('final_amount')
            )
            
            # Get status breakdown
            status_breakdown = {}
            for status_choice in Orders.OrderStatus.choices:
                status_code = status_choice[0]
                count = orders_query.filter(status=status_code).count()
                if count > 0:
                    status_breakdown[status_code] = count
            
            # Get approval status breakdown
            approval_breakdown = {}
            approval_choices = ['auto_approved', 'pending_approval', 'manager_approved', 'admin_approved', 'rejected']
            for approval_choice in approval_choices:
                count = orders_query.filter(approval_status=approval_choice).count()
                if count > 0:
                    approval_breakdown[approval_choice] = count
            
            # Pagination
            total_count = orders_query.count()
            start_idx = (page - 1) * page_size
            end_idx = start_idx + page_size
            
            # Order by created_at descending
            orders = orders_query.order_by('-created_at')[start_idx:end_idx]
            
            # Serialize orders
            orders_data = []
            for order in orders:
                # Get employee details if available
                employee_info = None
                if order.ordered_by_employee:
                    try:
                        employee = Registration.objects.get(user_id=order.ordered_by_employee)
                        employee_info = {
                            'user_id': employee.user_id,
                            'name': f"{employee.firstName} {employee.lastName}",
                            'email': employee.emailID,
                            'department': getattr(employee, 'department', None),
                            'employee_id': getattr(employee, 'employee_id', None)
                        }
                    except Registration.DoesNotExist:
                        pass
                
                order_data = {
                    'order_id': order.order_id,
                    'order_number': str(order.order_number),
                    'token_num': order.token_num,
                    'status': order.status,
                    'order_type': order.order_type,
                    'total_amount': float(order.total_amount),
                    'discount_amount': float(order.discount_amount),
                    'delivery_charges': float(order.delivery_charges),
                    'parcel_charges': float(order.parcel_charges),
                    'final_amount': float(order.final_amount),
                    'created_at': order.created_at.isoformat(),
                    'estimated_delivery_time': order.estimated_delivery_time.isoformat() if order.estimated_delivery_time else None,
                    'scheduled_time': order.scheduled_time.isoformat() if order.scheduled_time else None,
                    
                    # Company-specific fields
                    'company_purchase_order': order.company_purchase_order,
                    'is_bulk_order': order.is_bulk_order,
                    'bulk_order_reference': order.bulk_order_reference,
                    'company_department': order.company_department,
                    'approval_status': order.approval_status,
                    'approved_at': order.approved_at.isoformat() if order.approved_at else None,
                    'company_notes': order.company_notes,
                    'ordered_by_employee': employee_info
                }
                orders_data.append(order_data)
            
            return Response({
                'success': True,
                'message': f'Found {total_count} company orders',
                'data': {
                    'company_id': company_id,
                    'company_name': company.company_name,
                    'orders': orders_data,
                    'pagination': {
                        'page': page,
                        'page_size': page_size,
                        'total_count': total_count,
                        'total_pages': (total_count + page_size - 1) // page_size,
                        'has_next': end_idx < total_count,
                        'has_previous': page > 1
                    },
                    'summary': {
                        'total_orders': summary['total_orders'] or 0,
                        'total_amount': float(summary['total_amount']) if summary['total_amount'] else 0,
                        'status_breakdown': status_breakdown,
                        'approval_breakdown': approval_breakdown
                    },
                    'filters_applied': {
                        'status': status_filter,
                        'date_from': date_from,
                        'date_to': date_to,
                        'employee_id': employee_id,
                        'is_bulk_order': is_bulk_order,
                        'approval_status': approval_status,
                        'department': department
                    }
                }
            }, status=status.HTTP_200_OK)
            
        except CompanyRegistration.DoesNotExist:
            return Response({
                'success': False,
                'error': 'Company not found'
            }, status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            import traceback
            return Response({
                'success': False,
                'error': 'Failed to fetch company orders',
                'message': str(e),
                'traceback': traceback.format_exc() if getattr(settings, 'DEBUG', False) else None
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

class CompanyOrderDetailAPIView(APIView):
    """
    API endpoint for retrieving detailed information about a specific company order
    GET /api/company/{company_id}/orders/{order_id}/
    """
    
    @swagger_auto_schema(tags=['Core'])
    def get(self, request, company_id, order_id, *args, **kwargs):
        try:
            from consumer.models import Orders, OrderItems
            
            # Fetch the order and ensure it belongs to the company
            try:
                # order_id in the URL can be either the primary key or order_number (UUID)
                if '-' in str(order_id):
                    order = Orders.objects.get(order_number=order_id, company_id=company_id)
                else:
                    order = Orders.objects.get(order_id=order_id, company_id=company_id)
            except Orders.DoesNotExist:
                return Response({
                    'success': False,
                    'error': 'Order not found for this company'
                }, status=status.HTTP_404_NOT_FOUND)
            
            # Fetch company details
            company = None
            try:
                company = CompanyRegistration.objects.get(company_id=company_id)
            except CompanyRegistration.DoesNotExist:
                pass

            # Fetch employee details
            employee = None
            if order.ordered_by_employee:
                try:
                    employee = Registration.objects.get(user_id=order.ordered_by_employee)
                except Registration.DoesNotExist:
                    pass

            # Fetch order items
            items = OrderItems.objects.filter(order_id=order)
            items_data = []
            for item in items:
                items_data.append({
                    'item_id': item.item_id,
                    'item_name': item.item_name_snapshot,
                    'quantity': item.quantity,
                    'unit_price': float(item.unit_price_snapshot),
                    'total_price': float(item.total_price),
                    'menu_item_id': item.menu_item_id,
                    'product_item_id': item.product_item_id,
                    'item_details': item.item_details_snapshot,
                    'customizations': item.customizations
                })

            # Prepare complete order response
            order_data = {
                'order_id': order.order_id,
                'order_number': str(order.order_number),
                'token_num': order.token_num,
                'status': order.status,
                'order_type': order.order_type,
                'created_at': order.created_at,
                'updated_at': order.updated_at,
                'scheduled_time': order.scheduled_time,
                'estimated_delivery_time': order.estimated_delivery_time,
                'actual_delivery_time': order.actual_delivery_time,
                
                # Financials
                'order_summary': {
                    'total_amount': float(order.total_amount),
                    'discount_amount': float(order.discount_amount),
                    'delivery_charges': float(order.delivery_charges),
                    'parcel_charges': float(order.parcel_charges),
                    'final_amount': float(order.final_amount),
                    'wallet_points_used': float(order.wallet_points_used),
                    'coupon_code': order.coupon_code
                },
                
                # Addresses and Instructions
                'delivery_address': order.delivery_address_snapshot,
                'billing_address': order.billing_address_snapshot,
                'delivery_instruction': order.delivery_instruction,
                'order_instruction': order.order_instruction,
                
                # Company specific
                'company_info': {
                    'company_id': company_id,
                    'company_name': company.company_name if company else None,
                    'order_customer_type': order.order_customer_type,
                    'company_purchase_order': order.company_purchase_order,
                    'is_bulk_order': order.is_bulk_order,
                    'bulk_order_reference': order.bulk_order_reference,
                    'company_department': order.company_department,
                    'company_notes': order.company_notes
                },
                
                # Employee who placed the order
                'ordered_by': {
                    'user_id': employee.user_id,
                    'name': f"{employee.firstName} {employee.lastName}",
                    'email': employee.emailID,
                    'phone': f"{employee.countryCode}{employee.mobileNumber}",
                    'department': getattr(employee, 'department', None),
                    'employee_id': getattr(employee, 'employee_id', None)
                } if employee else None,
                
                # Approval Info
                'approval': {
                    'status': order.approval_status,
                    'approved_by': order.approved_by,
                    'approved_at': order.approved_at
                },
                
                # Items
                'items': items_data
            }

            return Response({
                'success': True,
                'data': order_data
            }, status=status.HTTP_200_OK)
            
        except Exception as e:
            return Response({
                'success': False,
                'error': f'Failed to retrieve order details: {str(e)}'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

class CompanyOffersAPIView(APIView):
    """
    API endpoint for company offers
    GET /api/company/{company_id}/offers/
    POST /api/company/{company_id}/offers/
    """
    
    @swagger_auto_schema(tags=['Core'])
    def get(self, request, company_id, *args, **kwargs):
        try:
            # Check if company exists
            company = CompanyRegistration.objects.get(company_id=company_id)
            
            # Get active offers for this company
            offers = CompanyOffers.objects.filter(
                company_id=company_id,
                is_active=True
            ).order_by('-created_at')
            
            serializer = CompanyOffersSerializer(offers, many=True)
            
            return Response({
                'status': 'success',
                'message': f'Found {offers.count()} active offers',
                'data': serializer.data
            }, status=status.HTTP_200_OK)
            
        except CompanyRegistration.DoesNotExist:
            return Response({
                'status': 'error',
                'message': 'Company not found'
            }, status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            return Response({
                'status': 'error',
                'message': 'Failed to fetch offers',
                'error': str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    
    @swagger_auto_schema(tags=['Core'])
    def post(self, request, company_id, *args, **kwargs):
        try:
            # Check if company exists and is approved
            company = CompanyRegistration.objects.get(company_id=company_id)
            if not company.can_place_orders:
                return Response({
                    'status': 'error',
                    'message': 'Company is not approved to create offers'
                }, status=status.HTTP_400_BAD_REQUEST)
            
            # Add company_id to offer data
            offer_data = request.data.copy()
            offer_data['company_id'] = company_id
            
            serializer = CompanyOffersSerializer(data=offer_data)
            serializer.is_valid(raise_exception=True)
            offer = serializer.save()
            
            return Response({
                'status': 'success',
                'message': 'Offer created successfully',
                'data': CompanyOffersSerializer(offer).data
            }, status=status.HTTP_201_CREATED)
            
        except CompanyRegistration.DoesNotExist:
            return Response({
                'status': 'error',
                'message': 'Company not found'
            }, status=status.HTTP_404_NOT_FOUND)
        except ValidationError as e:
            return Response({
                'status': 'error',
                'message': 'Validation failed',
                'errors': e.detail
            }, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            return Response({
                'status': 'error',
                'message': 'Failed to create offer',
                'error': str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)