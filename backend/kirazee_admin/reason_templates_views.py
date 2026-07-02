from rest_framework.decorators import api_view, parser_classes
from rest_framework import status
from rest_framework.response import Response
from rest_framework.parsers import JSONParser
from django.db import IntegrityError
from business.models import ReviewReasonTemplate

# =============================
# Review Reason Template Management
# =============================

@api_view(["GET"])  # /kirazee/api/v1/admin/review-templates/
def get_review_templates(request):
    """
    Get review reason templates with optional filtering
    Query params:
    - reason_type: filter by type (rejection, required_changes, approval)
    - category: filter by category
    - is_active: filter by active status
    """
    try:
        queryset = ReviewReasonTemplate.objects.all()
        
        # Apply filters
        reason_type = request.GET.get('reason_type')
        if reason_type:
            queryset = queryset.filter(reason_type=reason_type)
            
        category = request.GET.get('category')
        if category:
            queryset = queryset.filter(category=category)
            
        is_active = request.GET.get('is_active')
        if is_active is not None:
            queryset = queryset.filter(is_active=is_active.lower() == 'true')
        
        # Order by display_order and title
        templates = queryset.order_by('reason_type', 'display_order', 'title')
        
        # Serialize data and compute metrics
        data = []
        total = 0
        active_count = 0
        by_reason_type = {}
        by_category = {}
        for template in templates:
            total += 1
            if template.is_active:
                active_count += 1
            # Aggregate by reason_type
            rt = template.reason_type or 'unknown'
            by_reason_type[rt] = by_reason_type.get(rt, 0) + 1
            # Aggregate by category
            cat = template.category or 'unknown'
            by_category[cat] = by_category.get(cat, 0) + 1

            data.append({
                'id': template.id,
                'reason_type': template.reason_type,
                'category': template.category,
                'title': template.title,
                'description': template.description,
                'is_active': template.is_active,
                'is_required': template.is_required,
                'display_order': template.display_order,
                'created_at': template.created_at.isoformat() if template.created_at else None,
                'updated_at': template.updated_at.isoformat() if template.updated_at else None,
            })
        
        inactive_count = total - active_count

        metrics = {
            'total': total,
            'active': active_count,
            'inactive': inactive_count,
            'by_reason_type': by_reason_type,
            'by_category': by_category,
        }

        return Response({
            'success': True,
            'data': data,
            'count': len(data),
            'metrics': metrics,
        })
        
    except Exception as e:
        return Response({
            'success': False,
            'message': f'Failed to fetch review templates: {str(e)}'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(["POST"])  # /kirazee/api/v1/admin/review-templates/create/
@parser_classes([JSONParser])
def create_review_template(request):
    """
    Create a new review reason template
    """
    try:
        data = request.data
        
        # Validate required fields
        required_fields = ['reason_type', 'title', 'description']
        for field in required_fields:
            if not data.get(field):
                return Response({
                    'success': False,
                    'message': f'Missing required field: {field}'
                }, status=status.HTTP_400_BAD_REQUEST)
        
        # Validate reason_type
        valid_types = dict(ReviewReasonTemplate.REASON_TYPES)
        if data['reason_type'] not in valid_types:
            return Response({
                'success': False,
                'message': f'Invalid reason_type. Must be one of: {list(valid_types.keys())}'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Validate category
        valid_categories = dict(ReviewReasonTemplate.CATEGORIES)
        category = data.get('category', 'other')
        if category not in valid_categories:
            return Response({
                'success': False,
                'message': f'Invalid category. Must be one of: {list(valid_categories.keys())}'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Create template
        template = ReviewReasonTemplate.objects.create(
            reason_type=data['reason_type'],
            category=category,
            title=data['title'].strip(),
            description=data['description'].strip(),
            is_active=data.get('is_active', True),
            is_required=data.get('is_required', False),
            display_order=data.get('display_order', 0)
        )
        
        return Response({
            'success': True,
            'data': {
                'id': template.id,
                'reason_type': template.reason_type,
                'category': template.category,
                'title': template.title,
                'description': template.description,
                'is_active': template.is_active,
                'is_required': template.is_required,
                'display_order': template.display_order,
                'created_at': template.created_at.isoformat(),
                'updated_at': template.updated_at.isoformat(),
            },
            'message': 'Review template created successfully'
        }, status=status.HTTP_201_CREATED)
        
    except IntegrityError as e:
        if 'unique constraint' in str(e).lower():
            return Response({
                'success': False,
                'message': 'A template with this title and reason type already exists'
            }, status=status.HTTP_409_CONFLICT)
        return Response({
            'success': False,
            'message': f'Database integrity error: {str(e)}'
        }, status=status.HTTP_400_BAD_REQUEST)
        
    except Exception as e:
        return Response({
            'success': False,
            'message': f'Failed to create review template: {str(e)}'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(["PUT"])  # /kirazee/api/v1/admin/review-templates/<int:template_id>/
@parser_classes([JSONParser])
def update_review_template(request, template_id: int):
    """
    Update an existing review reason template
    """
    try:
        template = ReviewReasonTemplate.objects.get(id=template_id)
        data = request.data
        
        # Validate reason_type if provided
        if 'reason_type' in data:
            valid_types = dict(ReviewReasonTemplate.REASON_TYPES)
            if data['reason_type'] not in valid_types:
                return Response({
                    'success': False,
                    'message': f'Invalid reason_type. Must be one of: {list(valid_types.keys())}'
                }, status=status.HTTP_400_BAD_REQUEST)
        
        # Validate category if provided
        if 'category' in data:
            valid_categories = dict(ReviewReasonTemplate.CATEGORIES)
            if data['category'] not in valid_categories:
                return Response({
                    'success': False,
                    'message': f'Invalid category. Must be one of: {list(valid_categories.keys())}'
                }, status=status.HTTP_400_BAD_REQUEST)
        
        # Update fields
        if 'reason_type' in data:
            template.reason_type = data['reason_type']
        if 'category' in data:
            template.category = data['category']
        if 'title' in data:
            template.title = data['title'].strip()
        if 'description' in data:
            template.description = data['description'].strip()
        if 'is_active' in data:
            template.is_active = data['is_active']
        if 'is_required' in data:
            template.is_required = data['is_required']
        if 'display_order' in data:
            template.display_order = data['display_order']
        
        template.save()
        
        return Response({
            'success': True,
            'data': {
                'id': template.id,
                'reason_type': template.reason_type,
                'category': template.category,
                'title': template.title,
                'description': template.description,
                'is_active': template.is_active,
                'is_required': template.is_required,
                'display_order': template.display_order,
                'created_at': template.created_at.isoformat(),
                'updated_at': template.updated_at.isoformat(),
            },
            'message': 'Review template updated successfully'
        })
        
    except ReviewReasonTemplate.DoesNotExist:
        return Response({
            'success': False,
            'message': 'Review template not found'
        }, status=status.HTTP_404_NOT_FOUND)
        
    except IntegrityError as e:
        if 'unique constraint' in str(e).lower():
            return Response({
                'success': False,
                'message': 'A template with this title and reason type already exists'
            }, status=status.HTTP_409_CONFLICT)
        return Response({
            'success': False,
            'message': f'Database integrity error: {str(e)}'
        }, status=status.HTTP_400_BAD_REQUEST)
        
    except Exception as e:
        return Response({
            'success': False,
            'message': f'Failed to update review template: {str(e)}'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(["DELETE"])  # /kirazee/api/v1/admin/review-templates/<int:template_id>/delete/
def delete_review_template(request, template_id: int):
    """
    Delete a review reason template
    """
    try:
        template = ReviewReasonTemplate.objects.get(id=template_id)
        template.delete()
        
        return Response({
            'success': True,
            'message': 'Review template deleted successfully'
        })
        
    except ReviewReasonTemplate.DoesNotExist:
        return Response({
            'success': False,
            'message': 'Review template not found'
        }, status=status.HTTP_404_NOT_FOUND)
        
    except Exception as e:
        return Response({
            'success': False,
            'message': f'Failed to delete review template: {str(e)}'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(["POST"])  # /kirazee/api/v1/admin/review-templates/bulk/
@parser_classes([JSONParser])
def bulk_create_review_templates(request):
    """
    Bulk create review reason templates
    """
    try:
        templates_data = request.data.get('templates', [])
        
        if not templates_data:
            return Response({
                'success': False,
                'message': 'No templates data provided'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        created_templates = []
        errors = []
        
        for index, data in enumerate(templates_data):
            try:
                # Validate required fields
                required_fields = ['reason_type', 'title', 'description']
                for field in required_fields:
                    if not data.get(field):
                        errors.append({
                            'index': index,
                            'message': f'Missing required field: {field}'
                        })
                        continue
                
                # Validate reason_type
                valid_types = dict(ReviewReasonTemplate.REASON_TYPES)
                if data['reason_type'] not in valid_types:
                    errors.append({
                        'index': index,
                        'message': f'Invalid reason_type: {data["reason_type"]}'
                    })
                    continue
                
                # Validate category
                valid_categories = dict(ReviewReasonTemplate.CATEGORIES)
                category = data.get('category', 'other')
                if category not in valid_categories:
                    errors.append({
                        'index': index,
                        'message': f'Invalid category: {category}'
                    })
                    continue
                
                # Create template
                template = ReviewReasonTemplate.objects.create(
                    reason_type=data['reason_type'],
                    category=category,
                    title=data['title'].strip(),
                    description=data['description'].strip(),
                    is_active=data.get('is_active', True),
                    is_required=data.get('is_required', False),
                    display_order=data.get('display_order', 0)
                )
                
                created_templates.append({
                    'id': template.id,
                    'reason_type': template.reason_type,
                    'category': template.category,
                    'title': template.title,
                    'description': template.description,
                    'is_active': template.is_active,
                    'is_required': template.is_required,
                    'display_order': template.display_order,
                })
                
            except IntegrityError:
                errors.append({
                    'index': index,
                    'message': 'Template with this title and reason type already exists'
                })
            except Exception as e:
                errors.append({
                    'index': index,
                    'message': str(e)
                })
        
        return Response({
            'success': True,
            'data': {
                'created': created_templates,
                'created_count': len(created_templates),
                'errors': errors,
                'error_count': len(errors)
            },
            'message': f'Bulk creation completed. Created: {len(created_templates)}, Errors: {len(errors)}'
        })
        
    except Exception as e:
        return Response({
            'success': False,
            'message': f'Failed to bulk create review templates: {str(e)}'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
