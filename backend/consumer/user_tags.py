from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework import status
from django.shortcuts import get_object_or_404
from .models import UserTags, Registration
from drf_yasg.utils import swagger_auto_schema
from drf_yasg import openapi
import json


@swagger_auto_schema(
    methods=['POST'],
    tags=['Consumer'],
    request_body=openapi.Schema(
        type=openapi.TYPE_OBJECT,
        required=['user_id', 'tag'],
        properties={
            'user_id': openapi.Schema(type=openapi.TYPE_INTEGER),
            'tag': openapi.Schema(type=openapi.TYPE_STRING)
        }
    ),
    responses={
        201: openapi.Response(
            description='Tag added successfully',
            examples={
                'application/json': {
                    'success': True,
                    'message': 'Tag added successfully'
                }
            }
        ),
        400: openapi.Response(
            description='Bad request',
            examples={
                'application/json': {
                    'success': False,
                    'error': 'user_id and tag are required'
                }
            }
        )
    }
)
@api_view(['POST'])
def add_user_tag(request):
    """
    Add tag to user for segmentation
    """
    try:
        data = request.data
        user_id = data.get('user_id')
        tag = data.get('tag')
        
        if not user_id or not tag:
            return Response({
                'success': False,
                'error': 'user_id and tag are required'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        user = get_object_or_404(Registration, user_id=user_id)
        
        # Check if tag already exists
        existing_tag = UserTags.objects.filter(user_id=user, tag=tag).first()
        if existing_tag:
            return Response({
                'success': False,
                'error': 'User already has this tag'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Create new tag
        user_tag = UserTags.objects.create(
            user_id=user,
            tag=tag.strip().lower()
        )
        
        return Response({
            'success': True,
            'message': 'Tag added successfully',
            'data': {
                'id': user_tag.id,
                'user_id': user_id,
                'tag': user_tag.tag,
                'created_at': user_tag.created_at.isoformat()
            }
        }, status=status.HTTP_201_CREATED)
        
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
            description='User tags retrieved successfully',
            examples={
                'application/json': {
                    'success': True,
                    'data': {
                        'user_id': 123,
                        'tags': ['student', 'employee']
                    }
                }
            }
        ),
        404: openapi.Response(
            description='User not found',
            examples={
                'application/json': {
                    'success': False,
                    'error': 'User not found'
                }
            }
        )
    }
)
@api_view(['GET'])
def get_user_tags(request, user_id):
    """
    Get all tags for a user
    """
    try:
        user = get_object_or_404(Registration, user_id=user_id)
        
        tags = list(UserTags.objects.filter(user_id=user).values_list('tag', flat=True))
        
        return Response({
            'success': True,
            'data': {
                'user_id': user_id,
                'tags': tags
            }
        }, status=status.HTTP_200_OK)
        
    except Exception as e:
        return Response({
            'success': False,
            'error': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@swagger_auto_schema(
    methods=['DELETE'],
    tags=['Consumer'],
    responses={
        200: openapi.Response(
            description='Tag removed successfully',
            examples={
                'application/json': {
                    'success': True,
                    'message': 'Tag removed successfully'
                }
            }
        ),
        404: openapi.Response(
            description='Tag not found',
            examples={
                'application/json': {
                    'success': False,
                    'error': 'Tag not found for this user'
                }
            }
        )
    }
)
@api_view(['DELETE'])
def remove_user_tag(request, user_id, tag):
    """
    Remove tag from user
    """
    try:
        user = get_object_or_404(Registration, user_id=user_id)
        
        user_tag = UserTags.objects.filter(user_id=user, tag=tag.lower()).first()
        if not user_tag:
            return Response({
                'success': False,
                'error': 'Tag not found for this user'
            }, status=status.HTTP_404_NOT_FOUND)
        
        user_tag.delete()
        
        return Response({
            'success': True,
            'message': 'Tag removed successfully'
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
        required=['coupon_id', 'user_id'],
        properties={
            'coupon_id': openapi.Schema(type=openapi.TYPE_INTEGER),
            'user_id': openapi.Schema(type=openapi.TYPE_INTEGER),
            'expires_at': openapi.Schema(type=openapi.TYPE_STRING, format='date-time')
        }
    ),
    responses={
        201: openapi.Response(
            description='Private coupon mapped successfully',
            examples={
                'application/json': {
                    'success': True,
                    'message': 'Private coupon mapped successfully'
                }
            }
        )
    }
)
@api_view(['POST'])
def map_private_coupon(request):
    """
    Map a private coupon to a specific user
    """
    try:
        data = request.data
        coupon_id = data.get('coupon_id')
        user_id = data.get('user_id')
        expires_at = data.get('expires_at')
        
        if not coupon_id or not user_id:
            return Response({
                'success': False,
                'error': 'coupon_id and user_id are required'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        from .models import Coupons, CouponUserMapping
        
        coupon = get_object_or_404(Coupons, coupon_id=coupon_id)
        user = get_object_or_404(Registration, user_id=user_id)
        
        # Check if coupon is PRIVATE type
        if coupon.visibility_type != 'PRIVATE':
            return Response({
                'success': False,
                'error': 'Only PRIVATE coupons can be mapped to users'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Check if mapping already exists
        existing_mapping = CouponUserMapping.objects.filter(
            coupon_id=coupon,
            user_id=user
        ).first()
        
        if existing_mapping:
            return Response({
                'success': False,
                'error': 'Coupon already mapped to this user'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Create mapping
        mapping = CouponUserMapping.objects.create(
            coupon_id=coupon,
            user_id=user,
            expires_at=expires_at
        )
        
        return Response({
            'success': True,
            'message': 'Private coupon mapped successfully',
            'data': {
                'id': mapping.id,
                'coupon_id': coupon_id,
                'user_id': user_id,
                'expires_at': mapping.expires_at.isoformat() if mapping.expires_at else None,
                'created_at': mapping.created_at.isoformat()
            }
        }, status=status.HTTP_201_CREATED)
        
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
        required=['user_tags'],
        properties={
            'user_tags': openapi.Schema(
                type=openapi.TYPE_ARRAY,
                items=openapi.Schema(
                    type=openapi.TYPE_OBJECT,
                    properties={
                        'user_id': openapi.Schema(type=openapi.TYPE_INTEGER),
                        'tag': openapi.Schema(type=openapi.TYPE_STRING)
                    }
                )
            )
        }
    ),
    responses={
        201: openapi.Response(
            description='Bulk tags added successfully',
            examples={
                'application/json': {
                    'success': True,
                    'message': 'Bulk tags processed',
                    'processed': 10,
                    'created': 8,
                    'skipped': 2
                }
            }
        )
    }
)
@api_view(['POST'])
def bulk_add_user_tags(request):
    """
    Add tags to multiple users in bulk
    """
    try:
        user_tags_data = request.data.get('user_tags', [])
        
        if not user_tags_data:
            return Response({
                'success': False,
                'error': 'user_tags array is required'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        created_count = 0
        skipped_count = 0
        
        for tag_data in user_tags_data:
            user_id = tag_data.get('user_id')
            tag = tag_data.get('tag')
            
            if not user_id or not tag:
                skipped_count += 1
                continue
            
            try:
                user = get_object_or_404(Registration, user_id=user_id)
                user_tag, created = UserTags.objects.get_or_create(
                    user_id=user,
                    tag=tag.strip().lower()
                )
                if created:
                    created_count += 1
                else:
                    skipped_count += 1
            except Exception:
                skipped_count += 1
        
        return Response({
            'success': True,
            'message': 'Bulk tags processed',
            'processed': len(user_tags_data),
            'created': created_count,
            'skipped': skipped_count
        }, status=status.HTTP_201_CREATED)
        
    except Exception as e:
        return Response({
            'success': False,
            'error': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
