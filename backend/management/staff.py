import json
from datetime import datetime, date
from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.response import Response
from django.shortcuts import get_object_or_404
from django.db import transaction
from django.core.paginator import Paginator
from django.db.models import Q

from .models import BusinessStaff, BusinessStaffSalaries
from .serializers import BusinessStaffSerializer, BusinessStaffSalariesSerializer
from kirazee_app.models import Business, Registration


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