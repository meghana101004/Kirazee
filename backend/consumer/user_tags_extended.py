from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework import status
from django.shortcuts import get_object_or_404
from .models import UserTags, Registration
from drf_yasg.utils import swagger_auto_schema
from drf_yasg import openapi
from django.db.models import Count


@swagger_auto_schema(
    methods=['GET'],
    tags=['Consumer'],
    manual_parameters=[
        openapi.Parameter(
            'business_id',
            openapi.IN_QUERY,
            description="Filter by business ID (optional)",
            type=openapi.TYPE_INTEGER,
            required=False
        )
    ],
    responses={
        200: openapi.Response(
            description='Domain configuration retrieved',
            examples={
                'application/json': {
                    'success': True,
                    'data': {
                        'iiits.in': {
                            'tag': 'student_iiit',
                            'org_name': 'IIIT Sricity'
                        },
                        'infosys.com': {
                            'tag': 'employee',
                            'org_name': 'Infosys Limited'
                        }
                    }
                }
            }
        )
    }
)
@api_view(['GET'])
def get_domain_tag_mapping(request):
    """
    Get current domain to tag mapping configuration from database
    Supports business-scoped mappings with organization details
    """
    try:
        from .models import DomainTagMapping
        
        business_id = request.GET.get('business_id')
        
        # Filter by business if specified, otherwise return all active mappings
        if business_id:
            mappings = DomainTagMapping.objects.filter(
                business_id=business_id,
                is_active=True
            )
        else:
            # Return all active mappings (admin view)
            mappings = DomainTagMapping.objects.filter(is_active=True)
        
        # New format with org_name support
        domain_mapping = {
            mapping.domain: {
                'tag': mapping.tag,
                'org_name': mapping.org_name or ''
            } 
            for mapping in mappings
        }
        
        return Response({
            'success': True,
            'data': domain_mapping
        }, status=status.HTTP_200_OK)
        
    except Exception as e:
        return Response({
            'success': False,
            'error': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@swagger_auto_schema(
    methods=['POST'],
    tags=['Consumer'],
    request_body=openapi.Schema(
        type=openapi.TYPE_OBJECT,
        required=['business_id', 'domain_mapping'],
        properties={
            'business_id': openapi.Schema(
                type=openapi.TYPE_STRING,
                description='Business ID for scoping the domain mappings'
            ),
            'domain_mapping': openapi.Schema(
                type=openapi.TYPE_OBJECT,
                example={
                    'iiits.in': {
                        'tag': 'student_iiit',
                        'org_name': 'IIIT Sricity'
                    },
                    'company.com': {
                        'tag': 'employee',
                        'org_name': 'Company Name'
                    }
                }
            )
        }
    ),
    responses={
        200: openapi.Response(
            description='Domain configuration updated',
            examples={
                'application/json': {
                    'success': True,
                    'message': 'Domain mapping updated successfully (2 created, 1 updated)'
                }
            }
        )
    }
)
@api_view(['POST'])
def update_domain_tag_mapping(request):
    """
    Update domain to tag mapping configuration in database
    Supports business-scoped mappings with organization details
    """
    try:
        from .models import DomainTagMapping
        from django.db import transaction
        
        business_id = request.data.get('business_id')
        domain_mapping = request.data.get('domain_mapping')
        
        # Debug logging
        print(f"DEBUG: business_id = {business_id} (type: {type(business_id)})")
        print(f"DEBUG: domain_mapping = {domain_mapping}")
        
        if not business_id:
            return Response({
                'success': False,
                'error': 'business_id is required'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Ensure business_id is a string (not None)
        business_id = str(business_id).strip()
        if not business_id:
            return Response({
                'success': False,
                'error': 'business_id cannot be empty'
            }, status=status.HTTP_400_BAD_REQUEST)
            
        if not domain_mapping:
            return Response({
                'success': False,
                'error': 'domain_mapping is required'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        updated_count = 0
        created_count = 0
        
        with transaction.atomic():
            for domain, mapping_data in domain_mapping.items():
                # Support both new format (object) and legacy format (string)
                if isinstance(mapping_data, dict):
                    tag = mapping_data.get('tag')
                    org_name = mapping_data.get('org_name', '')
                else:
                    # Legacy format: mapping_data is just the tag string
                    tag = mapping_data
                    org_name = ''
                
                if not tag:
                    return Response({
                        'success': False,
                        'error': f'tag is required for domain {domain}'
                    }, status=status.HTTP_400_BAD_REQUEST)
                
                # Only update existing mappings - no creation
                try:
                    # Check if mapping exists first
                    try:
                        mapping_obj = DomainTagMapping.objects.get(
                            domain=domain.lower(),
                            business_id=business_id
                        )
                        # Update existing mapping
                        DomainTagMapping.objects.filter(
                            domain=domain.lower(),
                            business_id=business_id
                        ).update(
                            tag=tag,
                            org_name=org_name,
                            is_active=True
                        )
                        updated_count += 1
                        print(f"DEBUG: Updated existing mapping for {domain}")
                        
                    except DomainTagMapping.DoesNotExist:
                        # Domain doesn't exist - skip it (don't create)
                        print(f"DEBUG: Domain {domain} does not exist for business {business_id} - skipping")
                        continue
                        
                except Exception as update_error:
                    # Handle schema issues - fallback to old schema
                    if 'business_id' in str(update_error):
                        try:
                            # Check if mapping exists in old schema
                            mapping_obj = DomainTagMapping.objects.get(
                                domain=domain.lower()
                            )
                            # Update existing mapping (old schema)
                            DomainTagMapping.objects.filter(
                                domain=domain.lower()
                            ).update(
                                tag=tag,
                                org_name=org_name,
                                is_active=True
                            )
                            updated_count += 1
                            print(f"DEBUG: Updated existing mapping (old schema) for {domain}")
                            
                        except DomainTagMapping.DoesNotExist:
                            # Domain doesn't exist in old schema either - skip
                            print(f"DEBUG: Domain {domain} does not exist globally - skipping")
                            continue
                    else:
                        raise update_error
        
        return Response({
            'success': True,
            'message': f'Domain mapping updated successfully ({updated_count} updated, {len(domain_mapping) - updated_count} skipped - not found)'
        }, status=status.HTTP_200_OK)
        
    except Exception as e:
        print(f"DEBUG: Full error details: {e}")
        print(f"DEBUG: Error type: {type(e)}")
        import traceback
        print(f"DEBUG: Traceback: {traceback.format_exc()}")
        return Response({
            'success': False,
            'error': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@swagger_auto_schema(
    methods=['GET'],
    tags=['Consumer'],
    responses={
        200: openapi.Response(
            description='Tag analytics retrieved',
            examples={
                'application/json': {
                    'success': True,
                    'data': {
                        'total_users_with_tags': 150,
                        'tag_distribution': {
                            'student_iiit': 45,
                            'employee': 30,
                            'vip': 15,
                            'loyal_customer': 25
                        }
                    }
                }
            }
        )
    }
)
@api_view(['GET'])
def get_tag_analytics(request):
    """
    Get analytics on user tag distribution
    """
    try:
        # Get tag distribution
        tag_counts = UserTags.objects.values('tag').annotate(
            user_count=Count('user_id', distinct=True)
        ).order_by('-user_count')
        
        # Get total users with tags
        total_users_with_tags = UserTags.objects.values('user_id').distinct().count()
        
        return Response({
            'success': True,
            'data': {
                'total_users_with_tags': total_users_with_tags,
                'tag_distribution': {
                    item['tag']: item['user_count'] for item in tag_counts
                }
            }
        }, status=status.HTTP_200_OK)
        
    except Exception as e:
        return Response({
            'success': False,
            'error': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@swagger_auto_schema(
    methods=['GET'],
    tags=['Consumer'],
    manual_parameters=[
        openapi.Parameter(
            'business_id',
            openapi.IN_QUERY,
            description="Filter by business ID (optional)",
            type=openapi.TYPE_STRING,
            required=False
        )
    ],
    responses={
        200: openapi.Response(
            description='Targeting options retrieved',
            examples={
                'application/json': {
                    'success': True,
                    'data': {
                        'available_domains': [
                            {
                                'domain': 'station-s.org',
                                'tag': 'employee',
                                'org_name': 'Station S Organization',
                                'user_count': 25
                            }
                        ],
                        'available_tags': [
                            {
                                'tag': 'employee',
                                'description': 'Users with tag: employee',
                                'user_count': 45
                            }
                        ]
                    }
                }
            }
        )
    }
)
@api_view(['GET'])
def get_targeting_options(request):
    """
    Get comprehensive targeting options for coupon creation (domains with user counts)
    Supports business-scoped domain mappings with organization details
    """
    try:
        from .models import DomainTagMapping, UserTags
        from django.db.models import Count
        
        business_id = request.GET.get('business_id')
        
        # Get domain mappings with user counts (business-scoped or all)
        if business_id:
            domain_mappings = DomainTagMapping.objects.filter(
                business_id=business_id,
                is_active=True
            )
        else:
            # Return all active mappings (admin view)
            domain_mappings = DomainTagMapping.objects.filter(is_active=True)
        
        available_domains = []
        for mapping in domain_mappings:
            # Count users with this tag
            user_count = UserTags.objects.filter(tag=mapping.tag).values('user_id').distinct().count()
            
            available_domains.append({
                'domain': mapping.domain,
                'tag': mapping.tag,
                'org_name': mapping.org_name or '',
                'description': mapping.org_name or f"Users from {mapping.domain}",
                'user_count': user_count
            })
        
        # Get all available tags with user counts
        tag_counts = UserTags.objects.values('tag').annotate(
            user_count=Count('user_id', distinct=True)
        ).order_by('-user_count')
        
        available_tags = []
        for tag_data in tag_counts:
            available_tags.append({
                'tag': tag_data['tag'],
                'description': f"Users with tag: {tag_data['tag']}",
                'user_count': tag_data['user_count']
            })
        
        return Response({
            'success': True,
            'data': {
                'available_domains': available_domains,
                'available_tags': available_tags
            }
        }, status=status.HTTP_200_OK)
        
    except Exception as e:
        return Response({
            'success': False,
            'error': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@swagger_auto_schema(
    methods=['GET'],
    tags=['Consumer'],
    responses={
        200: openapi.Response(
            description='User tag summary retrieved',
            examples={
                'application/json': {
                    'success': True,
                    'data': {
                        'user_id': 123,
                        'tags': ['student_iiit', 'loyal_customer'],
                        'order_count': 8,
                        'total_spent': 2500.00,
                        'tag_descriptions': {
                            'student_iiit': 'IIIT Student',
                            'loyal_customer': 'Loyal customer (15+ orders)'
                        }
                    }
                }
            }
        )
    }
)
@api_view(['GET'])
def get_user_tag_summary(request, user_id):
    """
    Get comprehensive summary of user's tags and behavior
    """
    try:
        from .tag_assignment_service import TagAssignmentService
        
        summary = TagAssignmentService.get_user_tag_summary(user_id)
        
        if summary:
            return Response({
                'success': True,
                'data': summary
            }, status=status.HTTP_200_OK)
        else:
            return Response({
                'success': False,
                'error': 'User not found'
            }, status=status.HTTP_404_NOT_FOUND)
        
    except Exception as e:
        return Response({
            'success': False,
            'error': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@swagger_auto_schema(
    methods=['POST'],
    tags=['Consumer'],
    request_body=openapi.Schema(
        type=openapi.TYPE_OBJECT,
        required=['business_id', 'domain', 'tag'],
        properties={
            'business_id': openapi.Schema(
                type=openapi.TYPE_STRING,
                description='Business ID for scoping the domain mapping'
            ),
            'domain': openapi.Schema(
                type=openapi.TYPE_STRING,
                description='Domain to add (e.g., example.com)'
            ),
            'tag': openapi.Schema(
                type=openapi.TYPE_STRING,
                description='Tag to assign to this domain'
            ),
            'org_name': openapi.Schema(
                type=openapi.TYPE_STRING,
                description='Organization name (optional)'
            )
        }
    ),
    responses={
        200: openapi.Response(
            description='Domain added successfully',
            examples={
                'application/json': {
                    'success': True,
                    'message': 'Domain added successfully'
                }
            }
        )
    }
)
@api_view(['POST'])
def add_domain_tag_mapping(request):
    """
    Add a new domain to tag mapping configuration in database
    Dedicated service for adding new domains only (no updates)
    """
    try:
        from .models import DomainTagMapping
        
        business_id = request.data.get('business_id')
        domain = request.data.get('domain')
        tag = request.data.get('tag')
        org_name = request.data.get('org_name', '')
        
        # Debug logging
        print(f"DEBUG ADD: business_id = {business_id}")
        print(f"DEBUG ADD: domain = {domain}")
        print(f"DEBUG ADD: tag = {tag}")
        print(f"DEBUG ADD: org_name = {org_name}")
        
        if not business_id:
            return Response({
                'success': False,
                'error': 'business_id is required'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        if not domain:
            return Response({
                'success': False,
                'error': 'domain is required'
            }, status=status.HTTP_400_BAD_REQUEST)
            
        if not tag:
            return Response({
                'success': False,
                'error': 'tag is required'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Ensure business_id is a string
        business_id = str(business_id).strip()
        if not business_id:
            return Response({
                'success': False,
                'error': 'business_id cannot be empty'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Check if domain already exists for this business
        try:
            existing = DomainTagMapping.objects.get(
                domain=domain.lower(),
                business_id=business_id
            )
            return Response({
                'success': False,
                'error': f'Domain {domain} already exists for this business. Use update service to modify.'
            }, status=status.HTTP_400_BAD_REQUEST)
        except DomainTagMapping.DoesNotExist:
            # Domain doesn't exist, proceed with creation
            pass
        
        # Create new domain mapping
        try:
            DomainTagMapping.objects.create(
                domain=domain.lower(),
                business_id=business_id,
                tag=tag,
                org_name=org_name,
                is_active=True
            )
            print(f"DEBUG ADD: Created new mapping for {domain}")
            
            return Response({
                'success': True,
                'message': 'Domain added successfully'
            }, status=status.HTTP_200_OK)
            
        except Exception as create_error:
            # Handle schema issues
            if 'business_id' in str(create_error):
                # Fallback to old schema (no business_id)
                try:
                    existing = DomainTagMapping.objects.get(domain=domain.lower())
                    return Response({
                        'success': False,
                        'error': f'Domain {domain} already exists globally. Use update service to modify.'
                    }, status=status.HTTP_400_BAD_REQUEST)
                except DomainTagMapping.DoesNotExist:
                    # Create new mapping without business_id
                    DomainTagMapping.objects.create(
                        domain=domain.lower(),
                        tag=tag,
                        org_name=org_name,
                        is_active=True
                    )
                    print(f"DEBUG ADD: Created new mapping (old schema) for {domain}")
                    
                    return Response({
                        'success': True,
                        'message': 'Domain added successfully'
                    }, status=status.HTTP_200_OK)
            else:
                raise create_error
        
    except Exception as e:
        print(f"DEBUG ADD: Full error details: {e}")
        print(f"DEBUG ADD: Error type: {type(e)}")
        import traceback
        print(f"DEBUG ADD: Traceback: {traceback.format_exc()}")
        return Response({
            'success': False,
            'error': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@swagger_auto_schema(
    methods=['POST'],
    tags=['Consumer'],
    request_body=openapi.Schema(
        type=openapi.TYPE_OBJECT,
        required=['business_id', 'domains'],
        properties={
            'business_id': openapi.Schema(
                type=openapi.TYPE_STRING,
                description='Business ID for scoping the domain mappings'
            ),
            'domains': openapi.Schema(
                type=openapi.TYPE_ARRAY,
                items=openapi.Schema(type=openapi.TYPE_STRING),
                description='List of domains to deactivate'
            )
        }
    ),
    responses={
        200: openapi.Response(
            description='Domains deactivated successfully',
            examples={
                'application/json': {
                    'success': True,
                    'message': 'Domains deactivated successfully (2 deactivated, 1 not found)'
                }
            }
        )
    }
)
@api_view(['POST'])
def deactivate_domain_tag_mapping(request):
    """
    Deactivate domain mappings (set is_active=False)
    Supports business-scoped domain deactivation
    """
    try:
        from .models import DomainTagMapping
        
        business_id = request.data.get('business_id')
        domains = request.data.get('domains', [])
        
        # Debug logging
        print(f"DEBUG DEACTIVATE: business_id = {business_id}")
        print(f"DEBUG DEACTIVATE: domains = {domains}")
        
        if not business_id:
            return Response({
                'success': False,
                'error': 'business_id is required'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        if not domains:
            return Response({
                'success': False,
                'error': 'domains list is required'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Ensure business_id is a string
        business_id = str(business_id).strip()
        if not business_id:
            return Response({
                'success': False,
                'error': 'business_id cannot be empty'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        deactivated_count = 0
        not_found_count = 0
        
        for domain in domains:
            try:
                # Try to deactivate with business_id (new schema)
                updated = DomainTagMapping.objects.filter(
                    domain=domain.lower(),
                    business_id=business_id,
                    is_active=True
                ).update(is_active=False)
                
                if updated > 0:
                    deactivated_count += 1
                    print(f"DEBUG DEACTIVATE: Deactivated {domain}")
                else:
                    not_found_count += 1
                    print(f"DEBUG DEACTIVATE: Domain {domain} not found or already inactive")
                    
            except Exception as deactivate_error:
                # Handle schema issues - fallback to old schema
                if 'business_id' in str(deactivate_error):
                    try:
                        # Try old schema (no business_id)
                        updated = DomainTagMapping.objects.filter(
                            domain=domain.lower(),
                            is_active=True
                        ).update(is_active=False)
                        
                        if updated > 0:
                            deactivated_count += 1
                            print(f"DEBUG DEACTIVATE: Deactivated {domain} (old schema)")
                        else:
                            not_found_count += 1
                            print(f"DEBUG DEACTIVATE: Domain {domain} not found or already inactive (old schema)")
                    except Exception:
                        not_found_count += 1
                        print(f"DEBUG DEACTIVATE: Failed to deactivate {domain}")
                else:
                    raise deactivate_error
        
        return Response({
            'success': True,
            'message': f'Domains deactivated successfully ({deactivated_count} deactivated, {not_found_count} not found)'
        }, status=status.HTTP_200_OK)
        
    except Exception as e:
        print(f"DEBUG DEACTIVATE: Full error details: {e}")
        print(f"DEBUG DEACTIVATE: Error type: {type(e)}")
        import traceback
        print(f"DEBUG DEACTIVATE: Traceback: {traceback.format_exc()}")
        return Response({
            'success': False,
            'error': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
