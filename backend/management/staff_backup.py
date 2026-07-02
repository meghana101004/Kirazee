import json
import bcrypt
import secrets
import string
from datetime import datetime, date, timedelta
from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.response import Response
from django.shortcuts import get_object_or_404
from django.db import transaction
from django.core.paginator import Paginator
from django.db.models import Q
from django.utils import timezone

from .models import BusinessStaff, BusinessStaffSalaries, StaffLoginLog, RoleBasedNavItems
from .serializers import BusinessStaffSerializer, BusinessStaffSalariesSerializer
from kirazee_app.models import Business, Registration


def hash_password(password: str) -> str:
    """Hash a password using bcrypt"""
    salt = bcrypt.gensalt()
    return bcrypt.hashpw(password.encode('utf-8'), salt).decode('utf-8')


def verify_password(password: str, hashed: str) -> bool:
    """Verify password against hash"""
    return bcrypt.checkpw(password.encode('utf-8'), hashed.encode('utf-8'))


def generate_otp() -> str:
    """Generate 6-digit OTP"""
    return ''.join(secrets.choice(string.digits) for _ in range(6))


def log_staff_login(staff: BusinessStaff, method: str, status: str, request=None, failure_reason=None):
    """Log staff login attempt"""
    ip_address = None
    user_agent = None
    
    if request:
        ip_address = request.META.get('REMOTE_ADDR')
        user_agent = request.META.get('HTTP_USER_AGENT', '')
    
    StaffLoginLog.objects.create(
        staff_id=staff,
        business_id=staff.business_id,
        login_method=method,
        login_status=status,
        ip_address=ip_address,
        user_agent=user_agent,
        failure_reason=failure_reason
    )


def get_staff_navigation_items(staff: BusinessStaff) -> list:
    """Get navigation items for staff based on their role"""
    if not staff.nav_items:
        return []
    
    nav_items = RoleBasedNavItems.objects.filter(
        id__in=staff.nav_items,
        status=True,
        is_visible=True
    ).order_by('order_index')
    
    # Build hierarchical structure
    main_items = []
    sub_items = {}
    
    for item in nav_items:
        if item.parent is None:
            main_items.append(item)
        else:
            if item.parent.id not in sub_items:
                sub_items[item.parent.id] = []
            sub_items[item.parent.id].append(item)
    
    # Build final navigation structure
    navigation = []
    for item in main_items:
        nav_data = {
            'id': item.id,
            'name': item.nav_name,
            'icon': item.icon,
            'route': item.route_path,
            'children': []
        }
        
        if item.id in sub_items:
            nav_data['children'] = [
                {
                    'id': child.id,
                    'name': child.nav_name,
                    'icon': child.icon,
                    'route': child.route_path
                }
                for child in sub_items[item.id]
            ]
        
        navigation.append(nav_data)
    
    return navigation


@api_view(['POST'])
def create_staff(request):
    """
    Create a new staff member with optional salary information
    URL parameters:
    - business_id (required)
    
    Expected payload:
    {
        "first_name": "John",
        "last_name": "Doe",
        "role": "Manager",  // Manager, Admin, Employee
        "email": "john.doe@example.com",  // optional
        "phone": "+1234567890",  // optional
        "hire_date": "2024-01-15",
        "salary": {  // optional - if provided, creates initial salary record
            "salary_amount": 50000.00,
            "effective_from": "2024-01-15",
            "effective_to": "2024-12-31"  // optional
        }
    }
    """
    try:
        business_id = request.GET.get('business_id')
        
        if not business_id:
            return Response({
                'error': 'business_id is required as URL parameter'
            }, status=status.HTTP_400_BAD_REQUEST)

        # Validate business exists
        try:
            business = Business.objects.get(business_id=business_id)
        except Business.DoesNotExist:
            return Response({
                'error': f'Business with business_id {business_id} does not exist'
            }, status=status.HTTP_400_BAD_REQUEST)

        # Extract salary data if provided
        salary_data = request.data.pop('salary', None)
        
        # Create staff data
        staff_data = request.data.copy()
        staff_data['business_id'] = business.business_id

        # Use transaction to ensure both staff and salary are created together
        with transaction.atomic():
            # Create staff member
            staff_serializer = BusinessStaffSerializer(data=staff_data)
            if not staff_serializer.is_valid():
                return Response({
                    'error': 'Staff validation failed',
                    'details': staff_serializer.errors
                }, status=status.HTTP_400_BAD_REQUEST)
            
            staff = staff_serializer.save()
            
            # Create salary record if provided
            salary_record = None
            if salary_data:
                salary_data['staff_id'] = staff.staff_id
                salary_serializer = BusinessStaffSalariesSerializer(data=salary_data)
                
                if not salary_serializer.is_valid():
                    return Response({
                        'error': 'Salary validation failed',
                        'details': salary_serializer.errors
                    }, status=status.HTTP_400_BAD_REQUEST)
                
                salary_record = salary_serializer.save()

            # Prepare response data
            response_data = {
                'message': 'Staff member created successfully',
                'staff': BusinessStaffSerializer(staff).data
            }
            
            if salary_record:
                response_data['salary'] = BusinessStaffSalariesSerializer(salary_record).data
                response_data['message'] = 'Staff member and salary created successfully'

            return Response(response_data, status=status.HTTP_201_CREATED)

    except Exception as e:
        return Response({
            'error': 'Internal server error',
            'details': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['POST'])
def staff_login(request):
    """
    Staff login with OTP or password
    Expected payload:
    {
        "login_identifier": "email or mobile_number",
        "password": "password",  // optional if using OTP
        "login_method": "PASSWORD" or "OTP"  // required
    }
    """
    try:
        login_identifier = request.data.get('login_identifier')
        password = request.data.get('password')
        login_method = request.data.get('login_method', '').upper()
        
        if not login_identifier or not login_method:
            return Response({
                'error': 'login_identifier and login_method are required'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        if login_method not in ['PASSWORD', 'OTP']:
            return Response({
                'error': 'login_method must be PASSWORD or OTP'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Find staff by email or mobile number
        try:
            staff = BusinessStaff.objects.get(
                Q(email=login_identifier) | Q(mobile_number=login_identifier),
                status=True
            )
        except BusinessStaff.DoesNotExist:
            log_staff_login(None, login_method, 'FAILED', request, 'Staff not found')
            return Response({
                'error': 'Invalid credentials'
            }, status=status.HTTP_401_UNAUTHORIZED)
        
        # Authenticate based on method
        if login_method == 'PASSWORD':
            if not password:
                log_staff_login(staff, 'PASSWORD', 'FAILED', request, 'Password required')
                return Response({
                    'error': 'Password is required for password login'
                }, status=status.HTTP_400_BAD_REQUEST)
            
            if not staff.password_hash:
                log_staff_login(staff, 'PASSWORD', 'FAILED', request, 'Password not set')
                return Response({
                    'error': 'Password not set for this staff member'
                }, status=status.HTTP_400_BAD_REQUEST)
            
            if not verify_password(password, staff.password_hash):
                log_staff_login(staff, 'PASSWORD', 'FAILED', request, 'Invalid password')
                return Response({
                    'error': 'Invalid credentials'
                }, status=status.HTTP_401_UNAUTHORIZED)
        
        elif login_method == 'OTP':
            # Generate and send OTP
            otp = generate_otp()
            staff.otp_code = otp
            staff.otp_expires_at = timezone.now() + timedelta(minutes=5)
            staff.save(update_fields=['otp_code', 'otp_expires_at'])
            
            # TODO: Send OTP via SMS/email
            log_staff_login(staff, 'OTP', 'SUCCESS', request)
            
            return Response({
                'message': 'OTP sent successfully',
                'staff_id': staff.staff_id,
                'expires_in': 300  # 5 minutes
            }, status=status.HTTP_200_OK)
        
        # Update last login and log successful login
        staff.last_login = timezone.now()
        staff.login_method = login_method
        staff.save(update_fields=['last_login', 'login_method'])
        
        log_staff_login(staff, login_method, 'SUCCESS', request)
        
        # Get navigation items
        navigation = get_staff_navigation_items(staff)
        
        return Response({
            'message': 'Login successful',
            'staff': {
                'staff_id': staff.staff_id,
                'first_name': staff.first_name,
                'last_name': staff.last_name,
                'role': staff.role,
                'email': staff.email,
                'business_id': staff.business_id.business_id,
                'last_login': staff.last_login,
                'login_method': staff.login_method
            },
            'navigation': navigation
        }, status=status.HTTP_200_OK)
    
    except Exception as e:
        return Response({
            'error': 'Internal server error',
            'details': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['POST'])
def verify_staff_otp(request):
    """
    Verify OTP for staff login
    Expected payload:
    {
        "staff_id": 123,
        "otp": "123456"
    }
    """
    try:
        staff_id = request.data.get('staff_id')
        otp = request.data.get('otp')
        
        if not staff_id or not otp:
            return Response({
                'error': 'staff_id and otp are required'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            staff = BusinessStaff.objects.get(staff_id=staff_id, status=True)
        except BusinessStaff.DoesNotExist:
            return Response({
                'error': 'Staff not found'
            }, status=status.HTTP_404_NOT_FOUND)
        
        # Verify OTP
        if not staff.otp_code or staff.otp_code != otp:
            log_staff_login(staff, 'OTP', 'FAILED', request, 'Invalid OTP')
            return Response({
                'error': 'Invalid OTP'
            }, status=status.HTTP_401_UNAUTHORIZED)
        
        # Check OTP expiry
        if not staff.otp_expires_at or staff.otp_expires_at < timezone.now():
            log_staff_login(staff, 'OTP', 'FAILED', request, 'OTP expired')
            return Response({
                'error': 'OTP expired'
            }, status=status.HTTP_401_UNAUTHORIZED)
        
        # Clear OTP and update login info
        staff.otp_code = None
        staff.otp_expires_at = None
        staff.last_login = timezone.now()
        staff.login_method = 'OTP'
        staff.save(update_fields=['otp_code', 'otp_expires_at', 'last_login', 'login_method'])
        
        log_staff_login(staff, 'OTP', 'SUCCESS', request)
        
        # Get navigation items
        navigation = get_staff_navigation_items(staff)
        
        return Response({
            'message': 'OTP verification successful',
            'staff': {
                'staff_id': staff.staff_id,
                'first_name': staff.first_name,
                'last_name': staff.last_name,
                'role': staff.role,
                'email': staff.email,
                'business_id': staff.business_id.business_id,
                'last_login': staff.last_login,
                'login_method': staff.login_method
            },
            'navigation': navigation
        }, status=status.HTTP_200_OK)
    
    except Exception as e:
        return Response({
            'error': 'Internal server error',
            'details': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
def get_staff_navigation(request):
    """
    Get navigation items for logged-in staff
    URL parameters:
    - staff_id (required)
    """
    try:
        staff_id = request.GET.get('staff_id')
        
        if not staff_id:
            return Response({
                'error': 'staff_id is required'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            staff = BusinessStaff.objects.get(staff_id=staff_id, status=True)
        except BusinessStaff.DoesNotExist:
            return Response({
                'error': 'Staff not found'
            }, status=status.HTTP_404_NOT_FOUND)
        
        navigation = get_staff_navigation_items(staff)
        
        return Response({
            'staff_id': staff.staff_id,
            'role': staff.role,
            'navigation': navigation
        }, status=status.HTTP_200_OK)
    
    except Exception as e:
        return Response({
            'error': 'Internal server error',
            'details': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
def get_staff_list(request):
    """
    Get list of staff members for a business
    URL parameters:
    - business_id (required)
    - status (optional): true/false to filter by active/inactive
    - role (optional): M/A/E to filter by role
    - search (optional): search by name or email
    - limit (optional): number of records per page (default: 20)
    - offset (optional): pagination offset (default: 0)
    """
    try:
        business_id = request.GET.get('business_id')
        
        if not business_id:
            return Response({
                'error': 'business_id is required as URL parameter'
            }, status=status.HTTP_400_BAD_REQUEST)

        # Validate business exists
        try:
            business = Business.objects.get(business_id=business_id)
        except Business.DoesNotExist:
            return Response({
                'error': f'Business with business_id {business_id} does not exist'
            }, status=status.HTTP_400_BAD_REQUEST)

        # Build query
        queryset = BusinessStaff.objects.filter(business_id=business_id)

        # Apply filters
        status_filter = request.GET.get('status')
        if status_filter is not None:
            queryset = queryset.filter(status=status_filter.lower() == 'true')

        role_filter = request.GET.get('role')
        if role_filter:
            queryset = queryset.filter(role=role_filter.upper())

        search = request.GET.get('search')
        if search:
            queryset = queryset.filter(
                Q(first_name__icontains=search) |
                Q(last_name__icontains=search) |
                Q(email__icontains=search)
            )

        # Pagination
        limit = int(request.GET.get('limit', 20))
        offset = int(request.GET.get('offset', 0))
        
        total_count = queryset.count()
        staff_list = queryset[offset:offset + limit]

        # Serialize data with current salary information
        staff_data = []
        for staff in staff_list:
            staff_info = BusinessStaffSerializer(staff).data
            
            # Get current salary
            current_date = date.today()
            current_salary = BusinessStaffSalaries.objects.filter(
                staff_id=staff.staff_id,
                status=True,
                effective_from__lte=current_date
            ).filter(
                Q(effective_to__isnull=True) | Q(effective_to__gte=current_date)
            ).order_by('-effective_from').first()
            
            if current_salary:
                staff_info['current_salary'] = BusinessStaffSalariesSerializer(current_salary).data
            else:
                staff_info['current_salary'] = None
                
            staff_data.append(staff_info)

        return Response({
            'total': total_count,
            'limit': limit,
            'offset': offset,
            'staff': staff_data
        }, status=status.HTTP_200_OK)

    except Exception as e:
        return Response({
            'error': 'Internal server error',
            'details': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['POST'])
def staff_login(request):
    """
    Staff login with OTP or password
    Expected payload:
    {
        "login_identifier": "email or mobile_number",
        "password": "password",  // optional if using OTP
        "login_method": "PASSWORD" or "OTP"  // required
    }
    """
    try:
        login_identifier = request.data.get('login_identifier')
        password = request.data.get('password')
        login_method = request.data.get('login_method', '').upper()
        
        if not login_identifier or not login_method:
            return Response({
                'error': 'login_identifier and login_method are required'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        if login_method not in ['PASSWORD', 'OTP']:
            return Response({
                'error': 'login_method must be PASSWORD or OTP'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Find staff by email or mobile number
        try:
            staff = BusinessStaff.objects.get(
                Q(email=login_identifier) | Q(mobile_number=login_identifier),
                status=True
            )
        except BusinessStaff.DoesNotExist:
            log_staff_login(None, login_method, 'FAILED', request, 'Staff not found')
            return Response({
                'error': 'Invalid credentials'
            }, status=status.HTTP_401_UNAUTHORIZED)
        
        # Authenticate based on method
        if login_method == 'PASSWORD':
            if not password:
                log_staff_login(staff, 'PASSWORD', 'FAILED', request, 'Password required')
                return Response({
                    'error': 'Password is required for password login'
                }, status=status.HTTP_400_BAD_REQUEST)
            
            if not staff.password_hash:
                log_staff_login(staff, 'PASSWORD', 'FAILED', request, 'Password not set')
                return Response({
                    'error': 'Password not set for this staff member'
                }, status=status.HTTP_400_BAD_REQUEST)
            
            if not verify_password(password, staff.password_hash):
                log_staff_login(staff, 'PASSWORD', 'FAILED', request, 'Invalid password')
                return Response({
                    'error': 'Invalid credentials'
                }, status=status.HTTP_401_UNAUTHORIZED)
        
        elif login_method == 'OTP':
            # Generate and send OTP
            otp = generate_otp()
            staff.otp_code = otp
            staff.otp_expires_at = timezone.now() + timedelta(minutes=5)
            staff.save(update_fields=['otp_code', 'otp_expires_at'])
            
            # TODO: Send OTP via SMS/email
            log_staff_login(staff, 'OTP', 'SUCCESS', request)
            
            return Response({
                'message': 'OTP sent successfully',
                'staff_id': staff.staff_id,
                'expires_in': 300  # 5 minutes
            }, status=status.HTTP_200_OK)
        
        # Update last login and log successful login
        staff.last_login = timezone.now()
        staff.login_method = login_method
        staff.save(update_fields=['last_login', 'login_method'])
        
        log_staff_login(staff, login_method, 'SUCCESS', request)
        
        # Get navigation items
        navigation = get_staff_navigation_items(staff)
        
        return Response({
            'message': 'Login successful',
            'staff': {
                'staff_id': staff.staff_id,
                'first_name': staff.first_name,
                'last_name': staff.last_name,
                'role': staff.role,
                'email': staff.email,
                'business_id': staff.business_id.business_id,
                'last_login': staff.last_login,
                'login_method': staff.login_method
            },
            'navigation': navigation
        }, status=status.HTTP_200_OK)
    
    except Exception as e:
        return Response({
            'error': 'Internal server error',
            'details': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['POST'])
def verify_staff_otp(request):
    """
    Verify OTP for staff login
    Expected payload:
    {
        "staff_id": 123,
        "otp": "123456"
    }
    """
    try:
        staff_id = request.data.get('staff_id')
        otp = request.data.get('otp')
        
        if not staff_id or not otp:
            return Response({
                'error': 'staff_id and otp are required'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            staff = BusinessStaff.objects.get(staff_id=staff_id, status=True)
        except BusinessStaff.DoesNotExist:
            return Response({
                'error': 'Staff not found'
            }, status=status.HTTP_404_NOT_FOUND)
        
        # Verify OTP
        if not staff.otp_code or staff.otp_code != otp:
            log_staff_login(staff, 'OTP', 'FAILED', request, 'Invalid OTP')
            return Response({
                'error': 'Invalid OTP'
            }, status=status.HTTP_401_UNAUTHORIZED)
        
        # Check OTP expiry
        if not staff.otp_expires_at or staff.otp_expires_at < timezone.now():
            log_staff_login(staff, 'OTP', 'FAILED', request, 'OTP expired')
            return Response({
                'error': 'OTP expired'
            }, status=status.HTTP_401_UNAUTHORIZED)
        
        # Clear OTP and update login info
        staff.otp_code = None
        staff.otp_expires_at = None
        staff.last_login = timezone.now()
        staff.login_method = 'OTP'
        staff.save(update_fields=['otp_code', 'otp_expires_at', 'last_login', 'login_method'])
        
        log_staff_login(staff, 'OTP', 'SUCCESS', request)
        
        # Get navigation items
        navigation = get_staff_navigation_items(staff)
        
        return Response({
            'message': 'OTP verification successful',
            'staff': {
                'staff_id': staff.staff_id,
                'first_name': staff.first_name,
                'last_name': staff.last_name,
                'role': staff.role,
                'email': staff.email,
                'business_id': staff.business_id.business_id,
                'last_login': staff.last_login,
                'login_method': staff.login_method
            },
            'navigation': navigation
        }, status=status.HTTP_200_OK)
    
    except Exception as e:
        return Response({
            'error': 'Internal server error',
            'details': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
def get_staff_navigation(request):
    """
    Get navigation items for logged-in staff
    URL parameters:
    - staff_id (required)
    """
    try:
        staff_id = request.GET.get('staff_id')
        
        if not staff_id:
            return Response({
                'error': 'staff_id is required'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            staff = BusinessStaff.objects.get(staff_id=staff_id, status=True)
        except BusinessStaff.DoesNotExist:
            return Response({
                'error': 'Staff not found'
            }, status=status.HTTP_404_NOT_FOUND)
        
        navigation = get_staff_navigation_items(staff)
        
        return Response({
            'staff_id': staff.staff_id,
            'role': staff.role,
            'navigation': navigation
        }, status=status.HTTP_200_OK)
    
    except Exception as e:
        return Response({
            'error': 'Internal server error',
            'details': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
def get_staff_detail(request, staff_id):
    """
    Get details of a specific staff member
    URL parameters:
    - business_id (required)
    """
    try:
        business_id = request.GET.get('business_id')
        
        if not business_id:
            return Response({
                'error': 'business_id is required as URL parameter'
            }, status=status.HTTP_400_BAD_REQUEST)

        # Get staff member
        try:
            staff = BusinessStaff.objects.get(
                staff_id=staff_id,
                business_id=business_id
            )
        except BusinessStaff.DoesNotExist:
            return Response({
                'error': f'Staff member with ID {staff_id} not found for this business'
            }, status=status.HTTP_404_NOT_FOUND)

        # Serialize data with salary history
        staff_info = BusinessStaffSerializer(staff).data
        
        # Get current salary
        current_date = date.today()
        current_salary = BusinessStaffSalaries.objects.filter(
            staff_id=staff.staff_id,
            status=True,
            effective_from__lte=current_date
        ).filter(
            Q(effective_to__isnull=True) | Q(effective_to__gte=current_date)
        ).order_by('-effective_from').first()
        
        # Get all salary history
        salary_history = BusinessStaffSalaries.objects.filter(
            staff_id=staff.staff_id
        ).order_by('-effective_from')
        
        staff_info['current_salary'] = BusinessStaffSalariesSerializer(current_salary).data if current_salary else None
        staff_info['salary_history'] = BusinessStaffSalariesSerializer(salary_history, many=True).data

        return Response({
            'staff': staff_info
        }, status=status.HTTP_200_OK)

    except Exception as e:
        return Response({
            'error': 'Internal server error',
            'details': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['POST'])
def staff_login(request):
    """
    Staff login with OTP or password
    Expected payload:
    {
        "login_identifier": "email or mobile_number",
        "password": "password",  // optional if using OTP
        "login_method": "PASSWORD" or "OTP"  // required
    }
    """
    try:
        login_identifier = request.data.get('login_identifier')
        password = request.data.get('password')
        login_method = request.data.get('login_method', '').upper()
        
        if not login_identifier or not login_method:
            return Response({
                'error': 'login_identifier and login_method are required'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        if login_method not in ['PASSWORD', 'OTP']:
            return Response({
                'error': 'login_method must be PASSWORD or OTP'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Find staff by email or mobile number
        try:
            staff = BusinessStaff.objects.get(
                Q(email=login_identifier) | Q(mobile_number=login_identifier),
                status=True
            )
        except BusinessStaff.DoesNotExist:
            log_staff_login(None, login_method, 'FAILED', request, 'Staff not found')
            return Response({
                'error': 'Invalid credentials'
            }, status=status.HTTP_401_UNAUTHORIZED)
        
        # Authenticate based on method
        if login_method == 'PASSWORD':
            if not password:
                log_staff_login(staff, 'PASSWORD', 'FAILED', request, 'Password required')
                return Response({
                    'error': 'Password is required for password login'
                }, status=status.HTTP_400_BAD_REQUEST)
            
            if not staff.password_hash:
                log_staff_login(staff, 'PASSWORD', 'FAILED', request, 'Password not set')
                return Response({
                    'error': 'Password not set for this staff member'
                }, status=status.HTTP_400_BAD_REQUEST)
            
            if not verify_password(password, staff.password_hash):
                log_staff_login(staff, 'PASSWORD', 'FAILED', request, 'Invalid password')
                return Response({
                    'error': 'Invalid credentials'
                }, status=status.HTTP_401_UNAUTHORIZED)
        
        elif login_method == 'OTP':
            # Generate and send OTP
            otp = generate_otp()
            staff.otp_code = otp
            staff.otp_expires_at = timezone.now() + timedelta(minutes=5)
            staff.save(update_fields=['otp_code', 'otp_expires_at'])
            
            # TODO: Send OTP via SMS/email
            log_staff_login(staff, 'OTP', 'SUCCESS', request)
            
            return Response({
                'message': 'OTP sent successfully',
                'staff_id': staff.staff_id,
                'expires_in': 300  # 5 minutes
            }, status=status.HTTP_200_OK)
        
        # Update last login and log successful login
        staff.last_login = timezone.now()
        staff.login_method = login_method
        staff.save(update_fields=['last_login', 'login_method'])
        
        log_staff_login(staff, login_method, 'SUCCESS', request)
        
        # Get navigation items
        navigation = get_staff_navigation_items(staff)
        
        return Response({
            'message': 'Login successful',
            'staff': {
                'staff_id': staff.staff_id,
                'first_name': staff.first_name,
                'last_name': staff.last_name,
                'role': staff.role,
                'email': staff.email,
                'business_id': staff.business_id.business_id,
                'last_login': staff.last_login,
                'login_method': staff.login_method
            },
            'navigation': navigation
        }, status=status.HTTP_200_OK)
    
    except Exception as e:
        return Response({
            'error': 'Internal server error',
            'details': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['POST'])
def verify_staff_otp(request):
    """
    Verify OTP for staff login
    Expected payload:
    {
        "staff_id": 123,
        "otp": "123456"
    }
    """
    try:
        staff_id = request.data.get('staff_id')
        otp = request.data.get('otp')
        
        if not staff_id or not otp:
            return Response({
                'error': 'staff_id and otp are required'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            staff = BusinessStaff.objects.get(staff_id=staff_id, status=True)
        except BusinessStaff.DoesNotExist:
            return Response({
                'error': 'Staff not found'
            }, status=status.HTTP_404_NOT_FOUND)
        
        # Verify OTP
        if not staff.otp_code or staff.otp_code != otp:
            log_staff_login(staff, 'OTP', 'FAILED', request, 'Invalid OTP')
            return Response({
                'error': 'Invalid OTP'
            }, status=status.HTTP_401_UNAUTHORIZED)
        
        # Check OTP expiry
        if not staff.otp_expires_at or staff.otp_expires_at < timezone.now():
            log_staff_login(staff, 'OTP', 'FAILED', request, 'OTP expired')
            return Response({
                'error': 'OTP expired'
            }, status=status.HTTP_401_UNAUTHORIZED)
        
        # Clear OTP and update login info
        staff.otp_code = None
        staff.otp_expires_at = None
        staff.last_login = timezone.now()
        staff.login_method = 'OTP'
        staff.save(update_fields=['otp_code', 'otp_expires_at', 'last_login', 'login_method'])
        
        log_staff_login(staff, 'OTP', 'SUCCESS', request)
        
        # Get navigation items
        navigation = get_staff_navigation_items(staff)
        
        return Response({
            'message': 'OTP verification successful',
            'staff': {
                'staff_id': staff.staff_id,
                'first_name': staff.first_name,
                'last_name': staff.last_name,
                'role': staff.role,
                'email': staff.email,
                'business_id': staff.business_id.business_id,
                'last_login': staff.last_login,
                'login_method': staff.login_method
            },
            'navigation': navigation
        }, status=status.HTTP_200_OK)
    
    except Exception as e:
        return Response({
            'error': 'Internal server error',
            'details': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
def get_staff_navigation(request):
    """
    Get navigation items for logged-in staff
    URL parameters:
    - staff_id (required)
    """
    try:
        staff_id = request.GET.get('staff_id')
        
        if not staff_id:
            return Response({
                'error': 'staff_id is required'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            staff = BusinessStaff.objects.get(staff_id=staff_id, status=True)
        except BusinessStaff.DoesNotExist:
            return Response({
                'error': 'Staff not found'
            }, status=status.HTTP_404_NOT_FOUND)
        
        navigation = get_staff_navigation_items(staff)
        
        return Response({
            'staff_id': staff.staff_id,
            'role': staff.role,
            'navigation': navigation
        }, status=status.HTTP_200_OK)
    
    except Exception as e:
        return Response({
            'error': 'Internal server error',
            'details': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['PUT'])
def update_staff(request, staff_id):
    """
    Update a staff member
    URL parameters:
    - business_id (required)
    
    Expected payload: Same as create_staff
    """
    try:
        business_id = request.GET.get('business_id')
        
        if not business_id:
            return Response({
                'error': 'business_id is required as URL parameter'
            }, status=status.HTTP_400_BAD_REQUEST)

        # Get staff member
        try:
            staff = BusinessStaff.objects.get(
                staff_id=staff_id,
                business_id=business_id
            )
        except BusinessStaff.DoesNotExist:
            return Response({
                'error': f'Staff member with ID {staff_id} not found for this business'
            }, status=status.HTTP_404_NOT_FOUND)

        # Update staff data
        staff_data = request.data.copy()
        staff_data['business_id'] = business_id

        # Serialize and validate
        serializer = BusinessStaffSerializer(staff, data=staff_data, partial=True)
        if serializer.is_valid():
            updated_staff = serializer.save()
            return Response({
                'message': 'Staff member updated successfully',
                'staff': BusinessStaffSerializer(updated_staff).data
            }, status=status.HTTP_200_OK)
        else:
            return Response({
                'error': 'Validation failed',
                'details': serializer.errors
            }, status=status.HTTP_400_BAD_REQUEST)

    except Exception as e:
        return Response({
            'error': 'Internal server error',
            'details': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['POST'])
def staff_login(request):
    """
    Staff login with OTP or password
    Expected payload:
    {
        "login_identifier": "email or mobile_number",
        "password": "password",  // optional if using OTP
        "login_method": "PASSWORD" or "OTP"  // required
    }
    """
    try:
        login_identifier = request.data.get('login_identifier')
        password = request.data.get('password')
        login_method = request.data.get('login_method', '').upper()
        
        if not login_identifier or not login_method:
            return Response({
                'error': 'login_identifier and login_method are required'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        if login_method not in ['PASSWORD', 'OTP']:
            return Response({
                'error': 'login_method must be PASSWORD or OTP'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Find staff by email or mobile number
        try:
            staff = BusinessStaff.objects.get(
                Q(email=login_identifier) | Q(mobile_number=login_identifier),
                status=True
            )
        except BusinessStaff.DoesNotExist:
            log_staff_login(None, login_method, 'FAILED', request, 'Staff not found')
            return Response({
                'error': 'Invalid credentials'
            }, status=status.HTTP_401_UNAUTHORIZED)
        
        # Authenticate based on method
        if login_method == 'PASSWORD':
            if not password:
                log_staff_login(staff, 'PASSWORD', 'FAILED', request, 'Password required')
                return Response({
                    'error': 'Password is required for password login'
                }, status=status.HTTP_400_BAD_REQUEST)
            
            if not staff.password_hash:
                log_staff_login(staff, 'PASSWORD', 'FAILED', request, 'Password not set')
                return Response({
                    'error': 'Password not set for this staff member'
                }, status=status.HTTP_400_BAD_REQUEST)
            
            if not verify_password(password, staff.password_hash):
                log_staff_login(staff, 'PASSWORD', 'FAILED', request, 'Invalid password')
                return Response({
                    'error': 'Invalid credentials'
                }, status=status.HTTP_401_UNAUTHORIZED)
        
        elif login_method == 'OTP':
            # Generate and send OTP
            otp = generate_otp()
            staff.otp_code = otp
            staff.otp_expires_at = timezone.now() + timedelta(minutes=5)
            staff.save(update_fields=['otp_code', 'otp_expires_at'])
            
            # TODO: Send OTP via SMS/email
            log_staff_login(staff, 'OTP', 'SUCCESS', request)
            
            return Response({
                'message': 'OTP sent successfully',
                'staff_id': staff.staff_id,
                'expires_in': 300  # 5 minutes
            }, status=status.HTTP_200_OK)
        
        # Update last login and log successful login
        staff.last_login = timezone.now()
        staff.login_method = login_method
        staff.save(update_fields=['last_login', 'login_method'])
        
        log_staff_login(staff, login_method, 'SUCCESS', request)
        
        # Get navigation items
        navigation = get_staff_navigation_items(staff)
        
        return Response({
            'message': 'Login successful',
            'staff': {
                'staff_id': staff.staff_id,
                'first_name': staff.first_name,
                'last_name': staff.last_name,
                'role': staff.role,
                'email': staff.email,
                'business_id': staff.business_id.business_id,
                'last_login': staff.last_login,
                'login_method': staff.login_method
            },
            'navigation': navigation
        }, status=status.HTTP_200_OK)
    
    except Exception as e:
        return Response({
            'error': 'Internal server error',
            'details': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['POST'])
def verify_staff_otp(request):
    """
    Verify OTP for staff login
    Expected payload:
    {
        "staff_id": 123,
        "otp": "123456"
    }
    """
    try:
        staff_id = request.data.get('staff_id')
        otp = request.data.get('otp')
        
        if not staff_id or not otp:
            return Response({
                'error': 'staff_id and otp are required'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            staff = BusinessStaff.objects.get(staff_id=staff_id, status=True)
        except BusinessStaff.DoesNotExist:
            return Response({
                'error': 'Staff not found'
            }, status=status.HTTP_404_NOT_FOUND)
        
        # Verify OTP
        if not staff.otp_code or staff.otp_code != otp:
            log_staff_login(staff, 'OTP', 'FAILED', request, 'Invalid OTP')
            return Response({
                'error': 'Invalid OTP'
            }, status=status.HTTP_401_UNAUTHORIZED)
        
        # Check OTP expiry
        if not staff.otp_expires_at or staff.otp_expires_at < timezone.now():
            log_staff_login(staff, 'OTP', 'FAILED', request, 'OTP expired')
            return Response({
                'error': 'OTP expired'
            }, status=status.HTTP_401_UNAUTHORIZED)
        
        # Clear OTP and update login info
        staff.otp_code = None
        staff.otp_expires_at = None
        staff.last_login = timezone.now()
        staff.login_method = 'OTP'
        staff.save(update_fields=['otp_code', 'otp_expires_at', 'last_login', 'login_method'])
        
        log_staff_login(staff, 'OTP', 'SUCCESS', request)
        
        # Get navigation items
        navigation = get_staff_navigation_items(staff)
        
        return Response({
            'message': 'OTP verification successful',
            'staff': {
                'staff_id': staff.staff_id,
                'first_name': staff.first_name,
                'last_name': staff.last_name,
                'role': staff.role,
                'email': staff.email,
                'business_id': staff.business_id.business_id,
                'last_login': staff.last_login,
                'login_method': staff.login_method
            },
            'navigation': navigation
        }, status=status.HTTP_200_OK)
    
    except Exception as e:
        return Response({
            'error': 'Internal server error',
            'details': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
def get_staff_navigation(request):
    """
    Get navigation items for logged-in staff
    URL parameters:
    - staff_id (required)
    """
    try:
        staff_id = request.GET.get('staff_id')
        
        if not staff_id:
            return Response({
                'error': 'staff_id is required'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            staff = BusinessStaff.objects.get(staff_id=staff_id, status=True)
        except BusinessStaff.DoesNotExist:
            return Response({
                'error': 'Staff not found'
            }, status=status.HTTP_404_NOT_FOUND)
        
        navigation = get_staff_navigation_items(staff)
        
        return Response({
            'staff_id': staff.staff_id,
            'role': staff.role,
            'navigation': navigation
        }, status=status.HTTP_200_OK)
    
    except Exception as e:
        return Response({
            'error': 'Internal server error',
            'details': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['DELETE'])
def delete_staff(request, staff_id):
    """
    Delete (deactivate) a staff member
    URL parameters:
    - business_id (required)
    - hard_delete (optional): true to permanently delete, false to deactivate (default: false)
    """
    try:
        business_id = request.GET.get('business_id')
        hard_delete = request.GET.get('hard_delete', 'false').lower() == 'true'
        
        if not business_id:
            return Response({
                'error': 'business_id is required as URL parameter'
            }, status=status.HTTP_400_BAD_REQUEST)

        # Get staff member
        try:
            staff = BusinessStaff.objects.get(
                staff_id=staff_id,
                business_id=business_id
            )
        except BusinessStaff.DoesNotExist:
            return Response({
                'error': f'Staff member with ID {staff_id} not found for this business'
            }, status=status.HTTP_404_NOT_FOUND)

        if hard_delete:
            # Check if staff has salary records
            if BusinessStaffSalaries.objects.filter(staff_id=staff_id).exists():
                return Response({
                    'error': 'Cannot permanently delete staff member with salary records. Use soft delete instead.'
                }, status=status.HTTP_400_BAD_REQUEST)
            
            staff_name = staff.full_name
            staff.delete()
            return Response({
                'message': f'Staff member {staff_name} permanently deleted'
            }, status=status.HTTP_200_OK)
        else:
            # Soft delete - deactivate
            staff.status = False
            staff.save()
            return Response({
                'message': f'Staff member {staff.full_name} deactivated successfully'
            }, status=status.HTTP_200_OK)

    except Exception as e:
        return Response({
            'error': 'Internal server error',
            'details': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['POST'])
def staff_login(request):
    """
    Staff login with OTP or password
    Expected payload:
    {
        "login_identifier": "email or mobile_number",
        "password": "password",  // optional if using OTP
        "login_method": "PASSWORD" or "OTP"  // required
    }
    """
    try:
        login_identifier = request.data.get('login_identifier')
        password = request.data.get('password')
        login_method = request.data.get('login_method', '').upper()
        
        if not login_identifier or not login_method:
            return Response({
                'error': 'login_identifier and login_method are required'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        if login_method not in ['PASSWORD', 'OTP']:
            return Response({
                'error': 'login_method must be PASSWORD or OTP'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Find staff by email or mobile number
        try:
            staff = BusinessStaff.objects.get(
                Q(email=login_identifier) | Q(mobile_number=login_identifier),
                status=True
            )
        except BusinessStaff.DoesNotExist:
            log_staff_login(None, login_method, 'FAILED', request, 'Staff not found')
            return Response({
                'error': 'Invalid credentials'
            }, status=status.HTTP_401_UNAUTHORIZED)
        
        # Authenticate based on method
        if login_method == 'PASSWORD':
            if not password:
                log_staff_login(staff, 'PASSWORD', 'FAILED', request, 'Password required')
                return Response({
                    'error': 'Password is required for password login'
                }, status=status.HTTP_400_BAD_REQUEST)
            
            if not staff.password_hash:
                log_staff_login(staff, 'PASSWORD', 'FAILED', request, 'Password not set')
                return Response({
                    'error': 'Password not set for this staff member'
                }, status=status.HTTP_400_BAD_REQUEST)
            
            if not verify_password(password, staff.password_hash):
                log_staff_login(staff, 'PASSWORD', 'FAILED', request, 'Invalid password')
                return Response({
                    'error': 'Invalid credentials'
                }, status=status.HTTP_401_UNAUTHORIZED)
        
        elif login_method == 'OTP':
            # Generate and send OTP
            otp = generate_otp()
            staff.otp_code = otp
            staff.otp_expires_at = timezone.now() + timedelta(minutes=5)
            staff.save(update_fields=['otp_code', 'otp_expires_at'])
            
            # TODO: Send OTP via SMS/email
            log_staff_login(staff, 'OTP', 'SUCCESS', request)
            
            return Response({
                'message': 'OTP sent successfully',
                'staff_id': staff.staff_id,
                'expires_in': 300  # 5 minutes
            }, status=status.HTTP_200_OK)
        
        # Update last login and log successful login
        staff.last_login = timezone.now()
        staff.login_method = login_method
        staff.save(update_fields=['last_login', 'login_method'])
        
        log_staff_login(staff, login_method, 'SUCCESS', request)
        
        # Get navigation items
        navigation = get_staff_navigation_items(staff)
        
        return Response({
            'message': 'Login successful',
            'staff': {
                'staff_id': staff.staff_id,
                'first_name': staff.first_name,
                'last_name': staff.last_name,
                'role': staff.role,
                'email': staff.email,
                'business_id': staff.business_id.business_id,
                'last_login': staff.last_login,
                'login_method': staff.login_method
            },
            'navigation': navigation
        }, status=status.HTTP_200_OK)
    
    except Exception as e:
        return Response({
            'error': 'Internal server error',
            'details': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['POST'])
def verify_staff_otp(request):
    """
    Verify OTP for staff login
    Expected payload:
    {
        "staff_id": 123,
        "otp": "123456"
    }
    """
    try:
        staff_id = request.data.get('staff_id')
        otp = request.data.get('otp')
        
        if not staff_id or not otp:
            return Response({
                'error': 'staff_id and otp are required'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            staff = BusinessStaff.objects.get(staff_id=staff_id, status=True)
        except BusinessStaff.DoesNotExist:
            return Response({
                'error': 'Staff not found'
            }, status=status.HTTP_404_NOT_FOUND)
        
        # Verify OTP
        if not staff.otp_code or staff.otp_code != otp:
            log_staff_login(staff, 'OTP', 'FAILED', request, 'Invalid OTP')
            return Response({
                'error': 'Invalid OTP'
            }, status=status.HTTP_401_UNAUTHORIZED)
        
        # Check OTP expiry
        if not staff.otp_expires_at or staff.otp_expires_at < timezone.now():
            log_staff_login(staff, 'OTP', 'FAILED', request, 'OTP expired')
            return Response({
                'error': 'OTP expired'
            }, status=status.HTTP_401_UNAUTHORIZED)
        
        # Clear OTP and update login info
        staff.otp_code = None
        staff.otp_expires_at = None
        staff.last_login = timezone.now()
        staff.login_method = 'OTP'
        staff.save(update_fields=['otp_code', 'otp_expires_at', 'last_login', 'login_method'])
        
        log_staff_login(staff, 'OTP', 'SUCCESS', request)
        
        # Get navigation items
        navigation = get_staff_navigation_items(staff)
        
        return Response({
            'message': 'OTP verification successful',
            'staff': {
                'staff_id': staff.staff_id,
                'first_name': staff.first_name,
                'last_name': staff.last_name,
                'role': staff.role,
                'email': staff.email,
                'business_id': staff.business_id.business_id,
                'last_login': staff.last_login,
                'login_method': staff.login_method
            },
            'navigation': navigation
        }, status=status.HTTP_200_OK)
    
    except Exception as e:
        return Response({
            'error': 'Internal server error',
            'details': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
def get_staff_navigation(request):
    """
    Get navigation items for logged-in staff
    URL parameters:
    - staff_id (required)
    """
    try:
        staff_id = request.GET.get('staff_id')
        
        if not staff_id:
            return Response({
                'error': 'staff_id is required'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            staff = BusinessStaff.objects.get(staff_id=staff_id, status=True)
        except BusinessStaff.DoesNotExist:
            return Response({
                'error': 'Staff not found'
            }, status=status.HTTP_404_NOT_FOUND)
        
        navigation = get_staff_navigation_items(staff)
        
        return Response({
            'staff_id': staff.staff_id,
            'role': staff.role,
            'navigation': navigation
        }, status=status.HTTP_200_OK)
    
    except Exception as e:
        return Response({
            'error': 'Internal server error',
            'details': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)