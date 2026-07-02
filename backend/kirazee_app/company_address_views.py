from django.shortcuts import get_object_or_404
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from django.db import transaction
from django.utils import timezone
from kirazee_app.models import CompanyRegistration
from kirazee_app.models import Registration
from consumer.models import UserAddress
import json

class CompanyAddressAPIView(APIView):
    """
    Manage company addresses using UserAddress table
    Companies can save multiple addresses for deliveries and billing
    """
    
    def post(self, request, company_id):
        """Add new address for company"""
        try:
            data = request.data
            
            # Validate company exists
            company = get_object_or_404(CompanyRegistration, company_id=company_id)
            
            # For company addresses, we don't need a user_id
            # We'll use a special user_id for company addresses or null
            # Let's use the contact person's user_id if available, or use 0 as a system user
            
            # Validate required fields
            required_fields = ['address_type', 'address', 'tag']
            for field in required_fields:
                if field not in data:
                    return Response({
                        'status': 'error',
                        'message': f'Missing required field: {field}'
                    }, status=status.HTTP_400_BAD_REQUEST)
            
            # Parse and validate address JSON
            try:
                address_data = data['address']
                if isinstance(address_data, str):
                    address_data = json.loads(address_data)
                
                address_required_fields = ['address_line1', 'city', 'pincode']
                for field in address_required_fields:
                    if field not in address_data:
                        return Response({
                            'status': 'error',
                            'message': f'Missing required address field: {field}'
                        }, status=status.HTTP_400_BAD_REQUEST)
                
            except (json.JSONDecodeError, TypeError) as e:
                return Response({
                    'status': 'error',
                    'message': 'Invalid address JSON format',
                    'error': str(e)
                }, status=status.HTTP_400_BAD_REQUEST)
            
            # Check if this should be default (first address becomes default)
            is_default = data.get('is_default', False)
            if is_default:
                # Set all existing addresses of this type to non-default
                UserAddress.objects.filter(
                    company_id=company_id,
                    address_type=data['address_type']
                ).update(is_default=False)
            else:
                # If no default exists for this type, make this default
                existing_default = UserAddress.objects.filter(
                    company_id=company_id,
                    address_type=data['address_type'],
                    is_default=True
                ).exists()
                
                if not existing_default:
                    is_default = True
            
            # For company addresses, we need to use a valid user_id due to database constraints
            # We'll use the company's main contact person if available, or find any valid user
            
            # Try to find the main contact person for this company
            main_contact_user = Registration.objects.filter(
                company_id=company_id,
                user_type='company_admin'
            ).first()
            
            # If no main contact found, try any company employee
            if not main_contact_user:
                main_contact_user = Registration.objects.filter(
                    company_id=company_id,
                    user_type='company_employee'
                ).first()
            
            # If still no user found, use any existing user (fallback)
            if not main_contact_user:
                main_contact_user = Registration.objects.first()
            
            if not main_contact_user:
                return Response({
                    'status': 'error',
                    'message': 'No valid user found to associate with company address'
                }, status=status.HTTP_400_BAD_REQUEST)

            # Create address - use the found user_id for company addresses
            address = UserAddress.objects.create(
                user=main_contact_user,  # Use valid user for company addresses
                company_id=company_id,  # Save company_id for easy identification
                address_type=data['address_type'],
                tag=data['tag'],
                is_default=is_default,
                address=address_data,
                status=1,
                created_at=timezone.now(),
                updated_at=timezone.now()
            )
            
            return Response({
                'status': 'success',
                'message': 'Company address added successfully',
                'data': {
                    'id': address.id,
                    'user_id': address.user_id,
                    'company_id': address.company_id,  # Include company_id in response
                    'address_type': address.address_type,
                    'tag': address.tag,
                    'is_default': address.is_default,
                    'address': address.address,
                    'status': address.status,
                    'created_at': address.created_at.isoformat(),
                    'updated_at': address.updated_at.isoformat()
                },
                'company_info': {
                    'company_id': company_id,
                    'company_name': company.company_name
                }
            }, status=status.HTTP_201_CREATED)
            
        except Exception as e:
            return Response({
                'status': 'error',
                'message': 'Failed to add company address',
                'error': str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    
    def get(self, request, company_id):
        """List all addresses for company"""
        try:
            # Validate company exists
            company = get_object_or_404(CompanyRegistration, company_id=company_id)
            
            # Get filter parameters
            address_type = request.GET.get('address_type')
            is_default = request.GET.get('is_default')
            
            # Build query - filter by company_id for company addresses
            addresses = UserAddress.objects.filter(
                company_id=company_id,  # Filter by company_id instead of user_id
                status=1
            )
            
            if address_type:
                addresses = addresses.filter(address_type=address_type)
            
            if is_default is not None:
                addresses = addresses.filter(is_default=is_default.lower() == 'true')
            
            # Format response
            address_list = []
            for address in addresses:
                address_list.append({
                    'id': address.id,
                    'user_id': address.user_id,
                    'company_id': address.company_id,  # Include company_id in response
                    'address_type': address.address_type,
                    'tag': address.tag,
                    'is_default': address.is_default,
                    'address': address.address,
                    'status': address.status,
                    'created_at': address.created_at.isoformat(),
                    'updated_at': address.updated_at.isoformat()
                })
            
            return Response({
                'status': 'success',
                'message': 'Company addresses retrieved successfully',
                'data': address_list,
                'count': len(address_list),
                'company_id': company_id,
                'company_name': company.company_name
            }, status=status.HTTP_200_OK)
            
        except Exception as e:
            return Response({
                'status': 'error',
                'message': 'Failed to retrieve company addresses',
                'error': str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class CompanyAddressDetailAPIView(APIView):
    """
    Manage individual company address
    """
    
    def put(self, request, company_id, address_id):
        """Update company address"""
        try:
            data = request.data
            
            # Validate company exists
            company = get_object_or_404(CompanyRegistration, company_id=company_id)
            
            # Get address - filter by company_id
            address = get_object_or_404(
                UserAddress,
                id=address_id,
                company_id=company_id,  # Filter by company_id instead of user_id
                status=1
            )
            
            # Update fields
            if 'address_type' in data:
                address.address_type = data['address_type']
            
            if 'tag' in data:
                address.tag = data['tag']
            
            if 'is_default' in data:
                is_default = data['is_default']
                if is_default:
                    # Set all existing addresses of this type to non-default
                    UserAddress.objects.filter(
                        company_id=company_id,  # Filter by company_id
                        address_type=address.address_type
                    ).exclude(id=address_id).update(is_default=False)
                address.is_default = is_default
            
            if 'address' in data:
                try:
                    address_data = data['address']
                    if isinstance(address_data, str):
                        address_data = json.loads(address_data)
                    address.address = address_data
                except (json.JSONDecodeError, TypeError) as e:
                    return Response({
                        'status': 'error',
                        'message': 'Invalid address JSON format',
                        'error': str(e)
                    }, status=status.HTTP_400_BAD_REQUEST)
            
            address.updated_at = timezone.now()
            address.save()
            
            return Response({
                'status': 'success',
                'message': 'Company address updated successfully',
                'data': {
                    'id': address.id,
                    'user_id': address.user_id,
                    'company_id': address.company_id,  # Include company_id in response
                    'address_type': address.address_type,
                    'tag': address.tag,
                    'is_default': address.is_default,
                    'address': address.address,
                    'status': address.status,
                    'created_at': address.created_at.isoformat(),
                    'updated_at': address.updated_at.isoformat()
                }
            }, status=status.HTTP_200_OK)
            
        except Exception as e:
            return Response({
                'status': 'error',
                'message': 'Failed to update company address',
                'error': str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    
    def delete(self, request, company_id, address_id):
        """Delete company address"""
        try:
            # Validate company exists
            company = get_object_or_404(CompanyRegistration, company_id=company_id)
            
            # Get address - filter by company_id
            address = get_object_or_404(
                UserAddress,
                id=address_id,
                company_id=company_id  # Filter by company_id instead of user_id
            )
            
            # Soft delete by setting status to 0
            address.status = 0
            address.updated_at = timezone.now()
            address.save()
            
            return Response({
                'status': 'success',
                'message': 'Company address deleted successfully'
            }, status=status.HTTP_200_OK)
            
        except Exception as e:
            return Response({
                'status': 'error',
                'message': 'Failed to delete company address',
                'error': str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    
    def get(self, request, company_id, address_id):
        """Get specific company address"""
        try:
            # Validate company exists
            company = get_object_or_404(CompanyRegistration, company_id=company_id)
            
            # Get address - filter by company_id
            address = get_object_or_404(
                UserAddress,
                id=address_id,
                company_id=company_id,  # Filter by company_id instead of user_id
                status=1
            )
            
            return Response({
                'status': 'success',
                'message': 'Company address retrieved successfully',
                'data': {
                    'id': address.id,
                    'user_id': address.user_id,
                    'company_id': address.company_id,  # Include company_id in response
                    'address_type': address.address_type,
                    'tag': address.tag,
                    'is_default': address.is_default,
                    'address': address.address,
                    'status': address.status,
                    'created_at': address.created_at.isoformat(),
                    'updated_at': address.updated_at.isoformat()
                }
            }, status=status.HTTP_200_OK)
            
        except Exception as e:
            return Response({
                'status': 'error',
                'message': 'Failed to retrieve company address',
                'error': str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
