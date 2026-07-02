from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework import status
from django.db import transaction
from consumer.models import Coupons, CouponRules, CouponRedemptions, CouponApplicableItems
from consumer.serializers import CouponSerializer, CouponRulesSerializer
from kirazee_app.models import BusinessMapping
from drf_yasg.utils import swagger_auto_schema
import json
from datetime import datetime
from kirazee_app.models import Business
from django.db import connection
import random
import string
from django.db.models.signals import pre_save, post_save, post_delete
from django.dispatch import receiver
from business.models import MCPLog, _serialize_instance


def _generate_unique_coupon_code(prefix='KZ', length=6, max_attempts=50):
    alphabet = string.ascii_uppercase + string.digits
    for _ in range(max_attempts):
        suffix = ''.join(random.choices(alphabet, k=length))
        code = f"{prefix}{suffix}"
        if not Coupons.objects.filter(coupon_code=code).exists():
            return code
    # Fallback with timestamp-style entropy if collisions persist
    suffix = ''.join(random.choices(alphabet, k=length + 4))
    return f"{prefix}{suffix}"

@swagger_auto_schema(methods=['POST'], tags=['Business'])
@api_view(['POST'])
def create_coupon(request):
    """
    Create a new coupon by business owner
    POST /business/create-coupon/
    Required: user_id, business_id (for multi-business support)
    """
    try:
        user_id = request.data.get('user_id')
        business_id = request.data.get('business_id')
        
        if not user_id:
            return Response({
                'success': False,
                'message': 'user_id is required'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        if not business_id:
            return Response({
                'success': False,
                'message': 'business_id is required for coupon creation'
            }, status=status.HTTP_400_BAD_REQUEST)

        # Verify user owns this business or its master business
        try:
            business = Business.objects.get(business_id=business_id)
            
            # If this is a sublevel business, check authorization against master
            if business.level and business.level.lower() != 'master' and business.master:
                business_mapping = BusinessMapping.objects.get(
                    user_id=user_id, 
                    business_id=business.master,
                    status=True
                )
            else:
                business_mapping = BusinessMapping.objects.get(
                    user_id=user_id, 
                    business_id=business_id,
                    status=True
                )
        except (Business.DoesNotExist, BusinessMapping.DoesNotExist):
            return Response({
                'success': False,
                'message': 'You are not authorized to create coupons for this business'
            }, status=status.HTTP_403_FORBIDDEN)

        # Prepare coupon data
        coupon_data = request.data.copy()
        # If user selected MASTER business, coupon should be applicable to all businesses
        # We store it as a PLATFORM coupon (no business_id) so it applies everywhere.
        is_master_selected = bool(getattr(business, 'level', None) and str(business.level).lower() == 'master')
        if is_master_selected:
            coupon_data['coupon_scope'] = 'PLATFORM'
            coupon_data['business_id'] = None
        else:
            coupon_data['coupon_scope'] = coupon_data.get('coupon_scope', 'BUSINESS')
            coupon_data['business_id'] = business_id
        coupon_data['created_by'] = 'business_owner'

        # Auto-generate unique coupon_code if not provided
        incoming_code = coupon_data.get('coupon_code')
        if incoming_code is None or str(incoming_code).strip() == '':
            coupon_data['coupon_code'] = _generate_unique_coupon_code()
        else:
            coupon_data['coupon_code'] = str(incoming_code).strip().upper()

        # Convert visibility_type and coupon_scope to uppercase if provided
        if 'visibility_type' in coupon_data:
            coupon_data['visibility_type'] = coupon_data['visibility_type'].upper()
        if 'coupon_scope' in coupon_data:
            coupon_data['coupon_scope'] = coupon_data['coupon_scope'].upper()
        
        # Set default values for new fields if not provided
        coupon_data.setdefault('visibility_type', 'PUBLIC')
        coupon_data.setdefault('coupon_scope', 'BUSINESS')
        coupon_data.setdefault('free_delivery', False)
        coupon_data.setdefault('free_packaging', False)
        coupon_data.setdefault('max_redemptions_per_user', 1)

        # Validate dates
        valid_from = coupon_data.get('valid_from')
        valid_to = coupon_data.get('valid_to')
        
        if valid_from and valid_to:
            if datetime.fromisoformat(valid_from.replace('Z', '+00:00')) >= datetime.fromisoformat(valid_to.replace('Z', '+00:00')):
                return Response({
                    'success': False,
                    'message': 'valid_from must be before valid_to'
                }, status=status.HTTP_400_BAD_REQUEST)

        with transaction.atomic():
            # Create coupon
            coupon_serializer = CouponSerializer(data=coupon_data)
            if coupon_serializer.is_valid():
                coupon = coupon_serializer.save()
                
                # Create coupon rules if provided
                rules_data = request.data.get('rules', [])
                created_rules = []
                
                for rule_data in rules_data:
                    rule_data['coupon_id'] = coupon.coupon_id
                    rule_serializer = CouponRulesSerializer(data=rule_data)
                    if rule_serializer.is_valid():
                        rule = rule_serializer.save()
                        created_rules.append(rule_serializer.data)
                    else:
                        return Response({
                            'success': False,
                            'message': 'Invalid rule data',
                            'errors': rule_serializer.errors
                        }, status=status.HTTP_400_BAD_REQUEST)

                # Create applicable item mappings if provided
                applicable_items = request.data.get('applicable_items', [])
                created_mappings = 0
                if isinstance(applicable_items, list) and applicable_items:
                    for it in applicable_items:
                        try:
                            ref_table = str(it.get('reference_table')).strip()
                            ref_id = int(it.get('reference_id'))
                            if ref_table and ref_id:
                                CouponApplicableItems.objects.create(
                                    coupon=coupon,
                                    reference_table=ref_table,
                                    reference_id=ref_id,
                                    applicability_type=it.get('applicability_type', 'INCLUDE')
                                )
                                created_mappings += 1
                        except Exception:
                            continue

                return Response({
                    'success': True,
                    'message': 'Coupon created successfully',
                    'data': {
                        'coupon': coupon_serializer.data,
                        'rules': created_rules,
                        'applicable_items_created': created_mappings
                    }
                }, status=status.HTTP_201_CREATED)
            else:
                return Response({
                    'success': False,
                    'message': 'Invalid coupon data',
                    'errors': coupon_serializer.errors
                }, status=status.HTTP_400_BAD_REQUEST)

    except Exception as e:
        return Response({
            'success': False,
            'message': f'Error creating coupon: {str(e)}'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@swagger_auto_schema(methods=['GET'], tags=['Business'])
@api_view(['GET'])
def get_coupon_for_editing(request, coupon_id):
    """
    Get comprehensive coupon details for editing (including targeting options)
    GET /business/coupons/{coupon_id}/edit/?user_id=123
    """
    try:
        user_id = request.query_params.get('user_id')
        if not user_id:
            return Response({'success': False, 'message': 'user_id is required'}, status=status.HTTP_400_BAD_REQUEST)

        # Get all businesses owned by user (including sublevels)
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT DISTINCT b.business_id
                FROM business_mapping bm
                INNER JOIN businesses b ON bm.business_id = b.business_id
                WHERE bm.user_id = %s AND bm.status = 1
                UNION
                SELECT DISTINCT sb.business_id
                FROM business_mapping bm
                INNER JOIN businesses mb ON bm.business_id = mb.business_id
                INNER JOIN businesses sb ON mb.business_id = sb.master
                WHERE bm.user_id = %s AND bm.status = 1
                """,
                [user_id, user_id]
            )
            user_business_ids = [row[0] for row in cursor.fetchall()]

        if not user_business_ids:
            return Response({'success': False, 'message': 'No businesses found for this user'}, status=status.HTTP_404_NOT_FOUND)

        # Ensure coupon belongs to one of user's businesses
        try:
            coupon = Coupons.objects.get(coupon_id=coupon_id, business_id__business_id__in=user_business_ids)
        except Coupons.DoesNotExist:
            return Response({'success': False, 'message': 'Coupon not found or not owned by this user'}, status=status.HTTP_404_NOT_FOUND)

        # Serialize coupon and its rules
        coupon_data = CouponSerializer(coupon).data
        rules_qs = CouponRules.objects.filter(coupon_id=coupon).order_by('rule_id')
        rules_data = CouponRulesSerializer(rules_qs, many=True).data
        
        # Get applicable items
        mappings = list(
            CouponApplicableItems.objects.filter(coupon=coupon)
            .values('reference_table', 'reference_id', 'applicability_type')
        )
        
        # Get targeting options for editing
        try:
            from consumer.user_tags_extended import get_targeting_options
            from rest_framework.test import APIRequestFactory
            factory = APIRequestFactory()
            target_request = factory.get('/kirazee/consumer/user-tags/targeting-options/')
            targeting_response = get_targeting_options(target_request)
            targeting_options = targeting_response.data if targeting_response.status_code == 200 else {'available_domains': [], 'available_tags': []}
        except Exception:
            targeting_options = {'available_domains': [], 'available_tags': []}

        # Parse rules for easier frontend consumption
        parsed_rules = {}
        for rule in rules_data:
            rule_type = rule['rule_type']
            if rule_type == 'email_domain':
                parsed_rules['email_domains'] = rule['rule_value'].get('allowed_domains', [])
            elif rule_type == 'user_tag':
                parsed_rules['user_tags'] = rule['rule_value'].get('allowed_tags', [])
            elif rule_type == 'min_cart_value':
                parsed_rules['min_cart_value'] = rule['rule_value'].get('min_value')
            elif rule_type == 'time_window':
                parsed_rules['time_window'] = rule['rule_value']
            elif rule_type == 'first_order_only':
                parsed_rules['first_order_only'] = True
            elif rule_type == 'delivery_only':
                parsed_rules['delivery_only'] = True
            elif rule_type == 'order_type':
                parsed_rules['order_types'] = rule['rule_value'].get('order_types', [])

        return Response({
            'success': True,
            'data': {
                'coupon': coupon_data,
                'rules': rules_data,
                'applicable_items': mappings,
                'parsed_rules': parsed_rules,
                'targeting_options': targeting_options.get('data', {}),
                'edit_form_data': {
                    'selected_domains': parsed_rules.get('email_domains', []),
                    'selected_tags': parsed_rules.get('user_tags', []),
                    'min_cart_value': parsed_rules.get('min_cart_value'),
                    'time_window': parsed_rules.get('time_window'),
                    'first_order_only': parsed_rules.get('first_order_only', False),
                    'delivery_only': parsed_rules.get('delivery_only', False),
                    'order_types': parsed_rules.get('order_types', [])
                }
            }
        }, status=status.HTTP_200_OK)
    except Exception as e:
        return Response({'success': False, 'message': f'Error fetching coupon for editing: {str(e)}'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@swagger_auto_schema(methods=['GET'], tags=['Business'])
@api_view(['GET'])
def get_coupon_details(request, coupon_id):
    """
    Fetch a single coupon with its rules for prefill in owner UI.
    GET /business/coupons/{coupon_id}/?user_id=123
    """
    try:
        user_id = request.query_params.get('user_id')
        if not user_id:
            return Response({'success': False, 'message': 'user_id is required'}, status=status.HTTP_400_BAD_REQUEST)

        # Get all businesses owned by user (including sublevels)
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT DISTINCT b.business_id
                FROM business_mapping bm
                INNER JOIN businesses b ON bm.business_id = b.business_id
                WHERE bm.user_id = %s AND bm.status = 1
                UNION
                SELECT DISTINCT sb.business_id
                FROM business_mapping bm
                INNER JOIN businesses mb ON bm.business_id = mb.business_id
                INNER JOIN businesses sb ON mb.business_id = sb.master
                WHERE bm.user_id = %s AND bm.status = 1
                """,
                [user_id, user_id]
            )
            user_business_ids = [row[0] for row in cursor.fetchall()]

        if not user_business_ids:
            return Response({'success': False, 'message': 'No businesses found for this user'}, status=status.HTTP_404_NOT_FOUND)

        # Ensure coupon belongs to one of user's businesses
        try:
            coupon = Coupons.objects.get(coupon_id=coupon_id, business_id__business_id__in=user_business_ids)
        except Coupons.DoesNotExist:
            return Response({'success': False, 'message': 'Coupon not found or not owned by this user'}, status=status.HTTP_404_NOT_FOUND)

        # Serialize coupon and its rules
        coupon_data = CouponSerializer(coupon).data
        rules_qs = CouponRules.objects.filter(coupon_id=coupon).order_by('rule_id')
        rules_data = CouponRulesSerializer(rules_qs, many=True).data
        mappings = list(
            CouponApplicableItems.objects.filter(coupon=coupon)
            .values('reference_table', 'reference_id')
        )
        flat_ids = [m['reference_id'] for m in mappings]

        return Response({
            'success': True,
            'data': {
                'coupon': coupon_data,
                'rules': rules_data,
                'applicable_items': mappings,
                'applicable_item_ids': flat_ids
            }
        }, status=status.HTTP_200_OK)
    except Exception as e:
        return Response({'success': False, 'message': f'Error fetching coupon: {str(e)}'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


# ==========
# MCP Logs for Coupon entities (CRUD)
# ==========

@receiver(pre_save, sender=Coupons)
def _mcp_pre_save_coupons(sender, instance, **kwargs):
    if instance._state.adding:
        instance._mcp_old_data = None
    else:
        try:
            old = sender.objects.get(pk=instance.pk)
            instance._mcp_old_data = _serialize_instance(old)
        except sender.DoesNotExist:
            instance._mcp_old_data = None


@receiver(post_save, sender=Coupons)
def _mcp_post_save_coupons(sender, instance, created, **kwargs):
    old_data = getattr(instance, '_mcp_old_data', None)
    new_data = _serialize_instance(instance)
    action = 'INSERT' if created else 'UPDATE'
    changed = None
    if action == 'UPDATE' and old_data:
        diff = {}
        for k, v in new_data.items():
            if old_data.get(k) != v:
                diff[k] = [old_data.get(k), v]
        changed = diff or None
    # Resolve business id
    biz = None
    try:
        biz = str(instance.business_id_id)
    except Exception:
        try:
            biz = str(getattr(instance.business_id, 'business_id', None))
        except Exception:
            biz = None
    MCPLog.objects.create(
        entity_type='coupon',
        table_name=instance._meta.db_table,
        entity_id=str(instance.pk),
        business_id=biz,
        user_id=None,
        action_type=action,
        old_data=old_data,
        new_data=new_data,
        changed_fields=changed
    )


@receiver(post_delete, sender=Coupons)
def _mcp_post_delete_coupons(sender, instance, **kwargs):
    old_data = _serialize_instance(instance)
    biz = None
    try:
        biz = str(instance.business_id_id)
    except Exception:
        try:
            biz = str(getattr(instance.business_id, 'business_id', None))
        except Exception:
            biz = None
    MCPLog.objects.create(
        entity_type='coupon',
        table_name=instance._meta.db_table,
        entity_id=str(instance.pk),
        business_id=biz,
        user_id=None,
        action_type='DELETE',
        old_data=old_data,
        new_data=None,
        changed_fields=None
    )


@receiver(pre_save, sender=CouponRules)
def _mcp_pre_save_couponrules(sender, instance, **kwargs):
    if instance._state.adding:
        instance._mcp_old_data = None
    else:
        try:
            old = sender.objects.get(pk=instance.pk)
            instance._mcp_old_data = _serialize_instance(old)
        except sender.DoesNotExist:
            instance._mcp_old_data = None


@receiver(post_save, sender=CouponRules)
def _mcp_post_save_couponrules(sender, instance, created, **kwargs):
    old_data = getattr(instance, '_mcp_old_data', None)
    new_data = _serialize_instance(instance)
    action = 'INSERT' if created else 'UPDATE'
    changed = None
    if action == 'UPDATE' and old_data:
        diff = {}
        for k, v in new_data.items():
            if old_data.get(k) != v:
                diff[k] = [old_data.get(k), v]
        changed = diff or None
    # Resolve business id via related coupon
    biz = None
    try:
        biz = str(getattr(instance.coupon_id.business_id, 'business_id', None))
    except Exception:
        biz = None
    MCPLog.objects.create(
        entity_type='coupon_rule',
        table_name=instance._meta.db_table,
        entity_id=str(instance.pk),
        business_id=biz,
        user_id=None,
        action_type=action,
        old_data=old_data,
        new_data=new_data,
        changed_fields=changed
    )


@receiver(post_delete, sender=CouponRules)
def _mcp_post_delete_couponrules(sender, instance, **kwargs):
    old_data = _serialize_instance(instance)
    biz = None
    try:
        biz = str(getattr(instance.coupon_id.business_id, 'business_id', None))
    except Exception:
        biz = None
    MCPLog.objects.create(
        entity_type='coupon_rule',
        table_name=instance._meta.db_table,
        entity_id=str(instance.pk),
        business_id=biz,
        user_id=None,
        action_type='DELETE',
        old_data=old_data,
        new_data=None,
        changed_fields=None
    )


@swagger_auto_schema(methods=['GET'], tags=['Business'])
@api_view(['GET'])
def get_user_businesses(request):
    """
    Get all businesses owned by a user with hierarchical structure (master/sublevel)
    GET /business/user-businesses/?user_id=123
    """
    try:
        user_id = request.query_params.get('user_id')
        
        if not user_id:
            return Response({
                'success': False,
                'message': 'user_id is required'
            }, status=status.HTTP_400_BAD_REQUEST)

        # Get all businesses for this user
        business_mappings = BusinessMapping.objects.filter(
            user_id=user_id,
            status=True
        ).select_related('business')

        if not business_mappings.exists():
            return Response({
                'success': False,
                'message': 'No businesses found for this user'
            }, status=status.HTTP_404_NOT_FOUND)

        businesses = []
        for mapping in business_mappings:
            business = mapping.business
            business_data = {
                'business_id': business.business_id,
                'business_name': business.businessName,
                'business_type': business.businessType,
                'business_category': business.businessCategory,
                'level': business.level,
                'master': business.master,
                'city': business.city,
                'status': business.status,
                'is_verified': business.is_verified,
                'sub_level': []  # Initialize for child businesses
            }
            
            # If this is a master business, get its sublevel businesses
            level_val = str(business.level or "").strip().lower()
            if level_val == "master":
                with connection.cursor() as cursor:
                    cursor.execute(
                        """
                        SELECT business_id, businessName, businessType, businessCategory, 
                               level, master, city, status, is_verified
                        FROM businesses
                        WHERE master = %s AND status = 1
                        ORDER BY created_at ASC
                        """,
                        [business.business_id],
                    )
                    columns = [col[0] for col in cursor.description]
                    sub_rows = [dict(zip(columns, row)) for row in cursor.fetchall()]

                # Add sublevel businesses
                for sub_business in sub_rows:
                    business_data['sub_level'].append({
                        'business_id': sub_business['business_id'],
                        'business_name': sub_business['businessName'],
                        'business_type': sub_business['businessType'],
                        'business_category': sub_business['businessCategory'],
                        'level': sub_business['level'],
                        'master': sub_business['master'],
                        'city': sub_business['city'],
                        'status': sub_business['status'],
                        'is_verified': sub_business['is_verified']
                    })
            
            businesses.append(business_data)

        # Count total businesses including sublevels
        total_count = len(businesses)
        sublevel_count = sum(len(b['sub_level']) for b in businesses)
        
        return Response({
            'success': True,
            'message': f'Found {total_count} main businesses with {sublevel_count} sublevels for user',
            'data': {
                'user_id': user_id,
                'businesses': businesses,
                'main_business_count': total_count,
                'sublevel_business_count': sublevel_count,
                'total_business_count': total_count + sublevel_count
            }
        }, status=status.HTTP_200_OK)

    except Exception as e:
        return Response({
            'success': False,
            'message': f'Error fetching user businesses: {str(e)}'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@swagger_auto_schema(methods=['GET', 'POST'], tags=['Business'])
@api_view(['GET', 'POST'])
def list_business_coupons(request, business_id=None):
    """
    Securely list all coupons from all businesses owned by a user (master + sublevel)
    POST /business/coupons/
    Body: {"user_id": 123, "filters": {...}}
    """
    try:
        # Input validation and sanitization
        if request.method == 'GET':
            user_id = request.query_params.get('user_id')
            filters = {
                'status': request.query_params.get('status', 'all'),
                'business_type': request.query_params.get('business_type'),
                'date_from': request.query_params.get('date_from'),
                'date_to': request.query_params.get('date_to'),
            }
            names_only_flag = str(request.query_params.get('names_only', '')).lower() in ['1', 'true', 'yes']
        else:
            user_id = request.data.get('user_id')
            filters = request.data.get('filters', {})
            names_only_flag = bool(request.data.get('names_only'))
        
        if not user_id:
            return Response({
                'success': False,
                'message': 'user_id is required'
            }, status=status.HTTP_400_BAD_REQUEST)

        # Validate user_id is numeric to prevent injection
        try:
            user_id = int(user_id)
        except (ValueError, TypeError):
            return Response({
                'success': False,
                'message': 'Invalid user_id format'
            }, status=status.HTTP_400_BAD_REQUEST)

        # Validate optional filters
        status_filter = filters.get('status', 'all')
        business_type_filter = filters.get('business_type')
        date_from = filters.get('date_from')
        date_to = filters.get('date_to')
        
        # Sanitize status filter
        if status_filter not in ['all', 'active', 'inactive']:
            status_filter = 'all'

        with connection.cursor() as cursor:
            # Step 1: Get all businesses for this user with parameterized query
            cursor.execute("""
                SELECT DISTINCT b.business_id, b.businessName, b.businessType, 
                       b.level, b.master, b.city, b.status, b.is_verified
                FROM business_mapping bm
                INNER JOIN businesses b ON bm.business_id = b.business_id
                WHERE bm.user_id = %s AND bm.status = 1
            """, [user_id])
            
            business_rows = cursor.fetchall()
            if not business_rows:
                return Response({
                    'success': False,
                    'message': 'No businesses found for this user'
                }, status=status.HTTP_404_NOT_FOUND)

            # Step 2: Collect business IDs and get sublevel businesses
            all_business_ids = []
            business_details = {}
            
            for row in business_rows:
                biz_id = row[0]
                all_business_ids.append(biz_id)
                business_details[biz_id] = {
                    'business_id': row[0],
                    'business_name': row[1],
                    'business_type': row[2],
                    'level': row[3],
                    'master': row[4],
                    'city': row[5],
                    'status': row[6],
                    'is_verified': row[7]
                }
                
                # If master business, get sublevels
                if str(row[3] or "").strip().lower() == "master":
                    cursor.execute("""
                        SELECT business_id, businessName, businessType, level, 
                               master, city, status, is_verified
                        FROM businesses
                        WHERE master = %s
                    """, [biz_id])
                    
                    sub_rows = cursor.fetchall()
                    for sub_row in sub_rows:
                        sub_id = sub_row[0]
                        all_business_ids.append(sub_id)
                        business_details[sub_id] = {
                            'business_id': sub_row[0],
                            'business_name': sub_row[1],
                            'business_type': sub_row[2],
                            'level': sub_row[3],
                            'master': sub_row[4],
                            'city': sub_row[5],
                            'status': sub_row[6],
                            'is_verified': sub_row[7]
                        }

            # If a specific business_id is provided via path, restrict to it
            if business_id:
                all_business_ids = [business_id]

            # Step 3: Build secure coupon query with filters
            coupon_query = """
                SELECT c.coupon_id, c.coupon_code, c.name, c.discount_type, c.discount_value,
                       c.business_id, c.valid_from, c.valid_to, c.is_active,
                       c.max_total_redemptions, c.max_redemptions_per_user, c.current_usage_count,
                       c.visibility_type, c.coupon_scope, c.free_delivery, c.free_packaging,
                       c.created_by, c.created_at, c.updated_at
                FROM coupons c
                WHERE c.business_id IN ({})
            """.format(','.join(['%s'] * len(all_business_ids)))
            
            query_params = all_business_ids.copy()
            
            # Add status filter
            if status_filter == 'active':
                coupon_query += " AND c.is_active = 1"
            elif status_filter == 'inactive':
                coupon_query += " AND c.is_active = 0"
            
            # Add business type filter
            if business_type_filter:
                # Validate business type format (R01, R02, etc.)
                if business_type_filter.upper() in ['R01', 'R02', 'R03']:
                    coupon_query += """
                        AND c.business_id IN (
                            SELECT business_id FROM businesses 
                            WHERE businessType = %s
                        )
                    """
                    query_params.append(business_type_filter.upper())
            
            # Add date filters
            if date_from:
                coupon_query += " AND c.created_at >= %s"
                query_params.append(date_from)
            if date_to:
                coupon_query += " AND c.created_at <= %s"
                query_params.append(date_to)
            
            coupon_query += " ORDER BY c.created_at DESC"
            
            # Execute secure coupon query
            cursor.execute(coupon_query, query_params)
            coupon_rows = cursor.fetchall()

            # Early return if only names are requested
            if names_only_flag:
                names_list = []
                for row in coupon_rows:
                    # row indices after adding name:
                    # 0:id, 1:code, 2:name, 3:type, 4:value, 5:business_id
                    names_list.append({
                        'coupon_id': row[0],
                        'name': row[2] if row[2] else row[1],
                        'coupon_code': row[1],
                        'business_id': row[5]
                    })
                return Response({
                    'success': True,
                    'message': f'Retrieved {len(names_list)} coupon names',
                    'data': {
                        'coupon_names': names_list,
                        'total_coupon_count': len(names_list),
                        'filters_applied': filters
                    }
                }, status=status.HTTP_200_OK)
            
            # Step 4: Process coupon data with usage statistics
            coupon_list = []
            grouped_coupons = {}
            
            for row in coupon_rows:
                coupon_id = row[0]
                business_id = row[5]
                
                # Get coupon rules securely
                cursor.execute("""
                    SELECT rule_id, rule_type, rule_value, is_active, created_at
                    FROM coupon_rules
                    WHERE coupon_id = %s AND is_active = 1
                """, [coupon_id])
                
                rule_rows = cursor.fetchall()
                rules = []
                for rule_row in rule_rows:
                    rules.append({
                        'rule_id': rule_row[0],
                        'rule_type': rule_row[1],
                        'rule_value': json.loads(rule_row[2]) if rule_row[2] else {},
                        'is_active': rule_row[3],
                        'created_at': rule_row[4].isoformat() if rule_row[4] else None
                    })
                
                # Get redemption statistics (handle missing table gracefully)
                total_redemptions = 0
                total_discount_given = 0.0
                
                try:
                    cursor.execute("""
                        SELECT COUNT(*) as total_redemptions,
                               COALESCE(SUM(discount_amount_applied), 0) as total_discount_given
                        FROM coupon_redemptions
                        WHERE coupon_id = %s
                    """, [coupon_id])
                    
                    stats_row = cursor.fetchone()
                    total_redemptions = stats_row[0] if stats_row else 0
                    total_discount_given = float(stats_row[1]) if stats_row else 0.0
                except Exception as e:
                    # Table doesn't exist or other error - use default values
                    if "doesn't exist" in str(e):
                        total_redemptions = 0
                        total_discount_given = 0.0
                    else:
                        raise e
                
                coupon_data = {
                    'coupon_id': row[0],
                    'coupon_code': row[1],
                    'name': row[2],
                    'discount_type': row[3],
                    'discount_value': float(row[4]),
                    'business_id': row[5],
                    'business_info': business_details.get(business_id, {}),
                    'valid_from': row[6].isoformat() if row[6] else None,
                    'valid_to': row[7].isoformat() if row[7] else None,
                    'is_active': bool(row[8]),
                    'max_total_redemptions': row[9],
                    'max_redemptions_per_user': row[10],
                    'current_usage_count': row[11],
                    'visibility_type': row[12],
                    'coupon_scope': row[13],
                    'free_delivery': bool(row[14]),
                    'free_packaging': bool(row[15]),
                    'created_by': row[16],
                    'created_at': row[17].isoformat() if row[17] else None,
                    'updated_at': row[18].isoformat() if row[18] else None,
                    'rules': rules,
                    'usage_stats': {
                        'total_redemptions': total_redemptions,
                        'current_usage_count': row[11],
                        'max_total_redemptions': row[9],
                        'remaining_uses': row[9] - row[11] if row[9] else None,
                        'total_discount_given': total_discount_given
                    }
                }
                
                coupon_list.append(coupon_data)
                
                # Group by business
                if business_id not in grouped_coupons:
                    grouped_coupons[business_id] = {
                        'business_info': business_details.get(business_id, {}),
                        'coupons': []
                    }
                grouped_coupons[business_id]['coupons'].append(coupon_data)

        return Response({
            'success': True,
            'message': f'Securely retrieved {len(coupon_list)} coupons from {len(all_business_ids)} businesses',
            'data': {
                'all_coupons': coupon_list,
                'grouped_by_business': grouped_coupons,
                'total_coupon_count': len(coupon_list),
                'total_business_count': len(all_business_ids),
                'filters_applied': filters
            }
        }, status=status.HTTP_200_OK)

    except Exception as e:
        return Response({
            'success': False,
            'message': f'Error retrieving coupons: {str(e)}'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@swagger_auto_schema(methods=['PUT'], tags=['Business'])
@api_view(['PUT'])
def update_coupon(request, coupon_id):
    """
    Update a coupon by business owner
    PUT /business/coupons/{coupon_id}/
    """
    try:
        user_id = request.data.get('user_id')
        if not user_id:
            return Response({
                'success': False,
                'message': 'user_id is required'
            }, status=status.HTTP_400_BAD_REQUEST)

        # Get business_id from business mapping
        try:
            business_mapping = BusinessMapping.objects.get(user_id=user_id)
            business_id = business_mapping.business_id
        except BusinessMapping.DoesNotExist:
            return Response({
                'success': False,
                'message': 'Business not found for this user'
            }, status=status.HTTP_404_NOT_FOUND)

        # Get coupon - remove ownership validation
        try:
            coupon = Coupons.objects.get(coupon_id=coupon_id)
        except Coupons.DoesNotExist:
            return Response({
                'success': False,
                'message': 'Coupon not found'
            }, status=status.HTTP_404_NOT_FOUND)

        # Update coupon
        coupon_data = request.data.copy()
        coupon_data.pop('user_id', None)  # Remove user_id from update data
        rules_payload = coupon_data.pop('rules', None)
        applicable_items_payload = coupon_data.pop('applicable_items', None)
        
        # Convert visibility_type and coupon_scope to uppercase if provided
        if 'visibility_type' in coupon_data:
            coupon_data['visibility_type'] = coupon_data['visibility_type'].upper()
        if 'coupon_scope' in coupon_data:
            coupon_data['coupon_scope'] = coupon_data['coupon_scope'].upper()
        
        coupon_serializer = CouponSerializer(coupon, data=coupon_data, partial=True)
        if coupon_serializer.is_valid():
            with transaction.atomic():
                coupon = coupon_serializer.save()
                # Replace applicable items if provided
                if isinstance(applicable_items_payload, list):
                    CouponApplicableItems.objects.filter(coupon=coupon).delete()
                    new_items = applicable_items_payload or []
                    created_mappings = 0
                    for it in new_items:
                        try:
                            ref_table = str(it.get('reference_table')).strip()
                            ref_id = int(it.get('reference_id'))
                            if ref_table and ref_id:
                                CouponApplicableItems.objects.create(
                                    coupon=coupon,
                                    reference_table=ref_table,
                                    reference_id=ref_id,
                                )
                                created_mappings += 1
                        except Exception:
                            continue

                # Replace coupon rules if provided
                if isinstance(rules_payload, list):
                    CouponRules.objects.filter(coupon_id=coupon).delete()
                    for rule_data in rules_payload:
                        try:
                            if not isinstance(rule_data, dict):
                                continue
                            rule_type = rule_data.get('rule_type')
                            rule_value = rule_data.get('rule_value')
                            if not rule_type or rule_value is None:
                                continue

                            CouponRules.objects.create(
                                coupon_id=coupon,
                                rule_type=rule_type,
                                rule_value=rule_value,
                                is_active=True,
                            )
                        except Exception:
                            continue
            
            return Response({
                'success': True,
                'message': 'Coupon updated successfully',
                'data': coupon_serializer.data
            }, status=status.HTTP_200_OK)
        else:
            return Response({
                'success': False,
                'message': 'Invalid coupon data',
                'errors': coupon_serializer.errors
            }, status=status.HTTP_400_BAD_REQUEST)

    except Exception as e:
        return Response({
            'success': False,
            'message': f'Error updating coupon: {str(e)}'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@swagger_auto_schema(methods=['PATCH'], tags=['Business'])
@api_view(['PATCH'])
def toggle_coupon_status(request, coupon_id):
    """
    Activate/Deactivate a coupon (soft delete toggle)
    PATCH /business/coupons/{coupon_id}/toggle/
    Body: {"user_id": 14774, "action": "activate" | "deactivate"}
    """
    try:
        user_id = request.data.get('user_id')
        action = request.data.get('action', '').lower()
        
        if not user_id:
            return Response({'success': False, 'message': 'user_id is required'}, status=status.HTTP_400_BAD_REQUEST)
        if action not in ['activate', 'deactivate']:
            return Response({'success': False, 'message': 'action must be either "activate" or "deactivate"'}, status=status.HTTP_400_BAD_REQUEST)

        # Validate user_id
        try:
            user_id = int(user_id)
        except (ValueError, TypeError):
            return Response({'success': False, 'message': 'Invalid user_id format'}, status=status.HTTP_400_BAD_REQUEST)

        # Get owned businesses (master + sublevels)
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT DISTINCT b.business_id
                FROM business_mapping bm
                INNER JOIN businesses b ON bm.business_id = b.business_id
                WHERE bm.user_id = %s AND bm.status = 1
                UNION
                SELECT DISTINCT sb.business_id
                FROM business_mapping bm
                INNER JOIN businesses mb ON bm.business_id = mb.business_id
                INNER JOIN businesses sb ON mb.business_id = sb.master
                WHERE bm.user_id = %s AND bm.status = 1 AND sb.status = 1
                """,
                [user_id, user_id]
            )
            user_business_ids = [row[0] for row in cursor.fetchall()]

        if not user_business_ids:
            return Response({'success': False, 'message': 'No businesses found for this user'}, status=status.HTTP_404_NOT_FOUND)

        # Get coupon and verify ownership
        try:
            coupon = Coupons.objects.get(coupon_id=coupon_id, business_id__business_id__in=user_business_ids)
        except Coupons.DoesNotExist:
            return Response({'success': False, 'message': 'Coupon not found or not owned by this user'}, status=status.HTTP_404_NOT_FOUND)

        # Toggle
        new_status = True if action == 'activate' else False
        coupon.is_active = new_status
        coupon.save()

        return Response({
            'success': True,
            'message': f'Coupon {action}d successfully',
            'data': {
                'coupon_id': coupon_id,
                'coupon_code': coupon.coupon_code,
                'is_active': coupon.is_active,
                'action_performed': action
            }
        }, status=status.HTTP_200_OK)

    except Exception as e:
        return Response({'success': False, 'message': f'Error {action}ing coupon: {str(e)}'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@swagger_auto_schema(methods=['DELETE'], tags=['Business'])
@api_view(['DELETE'])
def delete_coupon(request, coupon_id):
    """
    Soft delete (deactivate) a coupon by business owner
    DELETE /business/coupons/{coupon_id}/
    Body: {"user_id": 14774}
    """
    try:
        user_id = request.data.get('user_id')
        if not user_id:
            return Response({
                'success': False,
                'message': 'user_id is required'
            }, status=status.HTTP_400_BAD_REQUEST)

        # Validate user_id format
        try:
            user_id = int(user_id)
        except (ValueError, TypeError):
            return Response({
                'success': False,
                'message': 'Invalid user_id format'
            }, status=status.HTTP_400_BAD_REQUEST)

        # Get all businesses owned by user (including sublevels)
        with connection.cursor() as cursor:
            cursor.execute("""
                SELECT DISTINCT b.business_id
                FROM business_mapping bm
                INNER JOIN businesses b ON bm.business_id = b.business_id
                WHERE bm.user_id = %s AND bm.status = 1
                UNION
                SELECT DISTINCT sb.business_id
                FROM business_mapping bm
                INNER JOIN businesses mb ON bm.business_id = mb.business_id
                INNER JOIN businesses sb ON mb.business_id = sb.master
                WHERE bm.user_id = %s AND bm.status = 1 AND sb.status = 1
            """, [user_id, user_id])
            
            user_business_ids = [row[0] for row in cursor.fetchall()]

        if not user_business_ids:
            return Response({
                'success': False,
                'message': 'No businesses found for this user'
            }, status=status.HTTP_404_NOT_FOUND)

        # Get coupon and verify ownership
        try:
            coupon = Coupons.objects.get(coupon_id=coupon_id, business_id__business_id__in=user_business_ids)
        except Coupons.DoesNotExist:
            return Response({
                'success': False,
                'message': 'Coupon not found or not owned by this user'
            }, status=status.HTTP_404_NOT_FOUND)

        # Soft delete by deactivating
        if coupon.is_active:
            coupon.is_active = False
            coupon.save()

        return Response({
            'success': True,
            'message': 'Coupon deactivated successfully',
            'data': {
                'coupon_id': coupon_id,
                'coupon_code': coupon.coupon_code,
                'is_active': coupon.is_active
            }
        }, status=status.HTTP_200_OK)

    except Exception as e:
        return Response({
            'success': False,
            'message': f'Error deleting coupon: {str(e)}'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@swagger_auto_schema(methods=['POST'], tags=['Business'])
@api_view(['POST'])
def add_coupon_rule(request, coupon_id):
    """
    Add a rule to existing coupon
    POST /business/coupons/{coupon_id}/rules/
    """
    try:
        user_id = request.data.get('user_id')
        if not user_id:
            return Response({
                'success': False,
                'message': 'user_id is required'
            }, status=status.HTTP_400_BAD_REQUEST)

        # Get business_id from business mapping
        try:
            business_mapping = BusinessMapping.objects.get(user_id=user_id)
            business_id = business_mapping.business_id
        except BusinessMapping.DoesNotExist:
            return Response({
                'success': False,
                'message': 'Business not found for this user'
            }, status=status.HTTP_404_NOT_FOUND)

        # Verify coupon ownership
        try:
            coupon = Coupons.objects.get(coupon_id=coupon_id, business_id__business_id=business_id)
        except Coupons.DoesNotExist:
            return Response({
                'success': False,
                'message': 'Coupon not found or not owned by this business'
            }, status=status.HTTP_404_NOT_FOUND)

        # Create rule
        rule_data = request.data.copy()
        rule_data['coupon_id'] = coupon_id
        rule_data.pop('user_id', None)

        rule_serializer = CouponRulesSerializer(data=rule_data)
        if rule_serializer.is_valid():
            rule = rule_serializer.save()
            return Response({
                'success': True,
                'message': 'Coupon rule added successfully',
                'data': rule_serializer.data
            }, status=status.HTTP_201_CREATED)
        else:
            return Response({
                'success': False,
                'message': 'Invalid rule data',
                'errors': rule_serializer.errors
            }, status=status.HTTP_400_BAD_REQUEST)

    except Exception as e:
        return Response({
            'success': False,
            'message': f'Error adding coupon rule: {str(e)}'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@swagger_auto_schema(methods=['PATCH'], tags=['Business'])
@api_view(['PATCH'])
def update_coupon_rule(request, coupon_id, rule_id):
    """
    Update an existing coupon rule (owner).
    PATCH /business/coupons/{coupon_id}/rules/{rule_id}/update/
    """
    try:
        if request.method == 'GET':
            user_id = request.query_params.get('user_id')
            if not user_id:
                return Response({'success': False, 'message': 'user_id is required'}, status=status.HTTP_400_BAD_REQUEST)

            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT DISTINCT b.business_id
                    FROM business_mapping bm
                    INNER JOIN businesses b ON bm.business_id = b.business_id
                    WHERE bm.user_id = %s AND bm.status = 1
                    UNION
                    SELECT DISTINCT sb.business_id
                    FROM business_mapping bm
                    INNER JOIN businesses mb ON bm.business_id = mb.business_id
                    INNER JOIN businesses sb ON mb.business_id = sb.master
                    WHERE bm.user_id = %s AND bm.status = 1 AND sb.status = 1
                    """,
                    [user_id, user_id]
                )
                user_business_ids = [row[0] for row in cursor.fetchall()]

            if not user_business_ids:
                return Response({'success': False, 'message': 'No businesses found for this user'}, status=status.HTTP_404_NOT_FOUND)

            try:
                coupon = Coupons.objects.get(coupon_id=coupon_id, business_id__business_id__in=user_business_ids)
            except Coupons.DoesNotExist:
                return Response({'success': False, 'message': 'Coupon not found or not owned by this user'}, status=status.HTTP_404_NOT_FOUND)

            qs = CouponApplicableItems.objects.filter(coupon=coupon)
            items = list(qs.values('reference_table', 'reference_id'))
            by_table = {}
            for m in items:
                by_table.setdefault(m['reference_table'], []).append(m['reference_id'])
            flat_ids = [m['reference_id'] for m in items]
            unique_tables = list(by_table.keys())

            return Response({
                'success': True,
                'data': {
                    'coupon_id': coupon_id,
                    'applicable_items': items,
                    'item_ids': flat_ids,
                    'by_reference_table': by_table,
                    'reference_tables': unique_tables
                }
            }, status=status.HTTP_200_OK)

        user_id = request.data.get('user_id')
        if not user_id:
            return Response({'success': False, 'message': 'user_id is required'}, status=status.HTTP_400_BAD_REQUEST)

        # Get business_id from business mapping
        try:
            business_mapping = BusinessMapping.objects.get(user_id=user_id)
            business_id = business_mapping.business_id
        except BusinessMapping.DoesNotExist:
            return Response({'success': False, 'message': 'Business not found for this user'}, status=status.HTTP_404_NOT_FOUND)

        # Verify coupon ownership
        try:
            coupon = Coupons.objects.get(coupon_id=coupon_id, business_id__business_id=business_id)
        except Coupons.DoesNotExist:
            return Response({'success': False, 'message': 'Coupon not found or not owned by this business'}, status=status.HTTP_404_NOT_FOUND)

        # Fetch rule
        try:
            rule = CouponRules.objects.get(rule_id=rule_id, coupon_id=coupon)
        except CouponRules.DoesNotExist:
            return Response({'success': False, 'message': 'Rule not found for this coupon'}, status=status.HTTP_404_NOT_FOUND)

        # Prepare update data
        rule_data = request.data.copy()
        rule_data.pop('user_id', None)
        rule_data.pop('coupon_id', None)  # Prevent reassigning to another coupon

        serializer = CouponRulesSerializer(rule, data=rule_data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response({'success': True, 'message': 'Coupon rule updated successfully', 'data': serializer.data}, status=status.HTTP_200_OK)

        return Response({'success': False, 'message': 'Invalid rule data', 'errors': serializer.errors}, status=status.HTTP_400_BAD_REQUEST)

    except Exception as e:
        return Response({'success': False, 'message': f'Error updating coupon rule: {str(e)}'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@swagger_auto_schema(methods=['GET', 'PUT'], tags=['Business'])
@api_view(['GET', 'PUT'])
def set_coupon_applicable_items(request, coupon_id):
    """
    Overwrite applicable items for a coupon.
    PUT /business/coupons/{coupon_id}/applicable-items/
    Body:
      {
        "user_id": 123,
        "item_ids": [101, 104, 205],
        "reference_table": "productItems"  # optional; inferred by business type if missing
        # OR
        # "items": [{"reference_table":"menuItems","reference_id":1}, ...]
      }
    """
    try:
        user_id = request.data.get('user_id')
        if not user_id:
            return Response({'success': False, 'message': 'user_id is required'}, status=status.HTTP_400_BAD_REQUEST)

        # Determine all businesses owned by user (include sublevels)
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT DISTINCT b.business_id
                FROM business_mapping bm
                INNER JOIN businesses b ON bm.business_id = b.business_id
                WHERE bm.user_id = %s AND bm.status = 1
                UNION
                SELECT DISTINCT sb.business_id
                FROM business_mapping bm
                INNER JOIN businesses mb ON bm.business_id = mb.business_id
                INNER JOIN businesses sb ON mb.business_id = sb.master
                WHERE bm.user_id = %s AND bm.status = 1 AND sb.status = 1
                """,
                [user_id, user_id]
            )
            user_business_ids = [row[0] for row in cursor.fetchall()]

        if not user_business_ids:
            return Response({'success': False, 'message': 'No businesses found for this user'}, status=status.HTTP_404_NOT_FOUND)

        # Verify coupon belongs to one of the user's businesses
        try:
            coupon = Coupons.objects.get(coupon_id=coupon_id, business_id__business_id__in=user_business_ids)
        except Coupons.DoesNotExist:
            return Response({'success': False, 'message': 'Coupon not found or not owned by this user'}, status=status.HTTP_404_NOT_FOUND)

        # Parse payload
        items_payload = request.data.get('items')
        item_ids = request.data.get('item_ids')
        reference_table = request.data.get('reference_table')

        mappings = []
        if isinstance(items_payload, list):
            for it in items_payload:
                try:
                    rt = str(it.get('reference_table')).strip()
                    rid = int(it.get('reference_id'))
                    if rt and rid:
                        mappings.append((rt, rid))
                except Exception:
                    continue
        else:
            # item_ids mode: require or infer reference_table
            # Infer table by business type if not provided
            if not reference_table:
                try:
                    biz = coupon.business_id
                    biz_type = getattr(biz, 'businessType', None)
                    if str(biz_type).upper() == 'R01':
                        reference_table = 'Groceries_ProductVariants'
                    else:
                        reference_table = 'productItems'
                except Exception:
                    reference_table = 'productItems'

            if isinstance(item_ids, list):
                for rid in item_ids:
                    try:
                        rid_int = int(rid)
                        mappings.append((reference_table, rid_int))
                    except Exception:
                        continue

        # Perform overwrite
        with transaction.atomic():
            CouponApplicableItems.objects.filter(coupon=coupon).delete()
            created = 0
            for rt, rid in mappings:
                try:
                    CouponApplicableItems.objects.create(
                        coupon=coupon,
                        reference_table=rt,
                        reference_id=rid
                    )
                    created += 1
                except Exception:
                    continue

        return Response({
            'success': True,
            'message': 'Applicable items updated',
            'data': {
                'coupon_id': coupon_id,
                'mappings_created': created
            }
        }, status=status.HTTP_200_OK)
    except Exception as e:
        return Response({'success': False, 'message': f'Error updating applicable items: {str(e)}'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@swagger_auto_schema(methods=['GET'], tags=['Business'])
@api_view(['GET'])
def coupon_analytics(request):
    """
    Get coupon usage analytics for business
    GET /business/coupon-analytics/?user_id=123
    """
    try:
        user_id = request.GET.get('user_id')
        if not user_id:
            return Response({
                'success': False,
                'message': 'user_id is required'
            }, status=status.HTTP_400_BAD_REQUEST)

        # Get business_id from business mapping
        try:
            business_mapping = BusinessMapping.objects.get(user_id=user_id)
            business_id = business_mapping.business_id
        except BusinessMapping.DoesNotExist:
            return Response({
                'success': False,
                'message': 'Business not found for this user'
            }, status=status.HTTP_404_NOT_FOUND)

        from django.db import connection
        
        with connection.cursor() as cursor:
            # Get coupon analytics
            cursor.execute("""
                SELECT 
                    c.coupon_code,
                    c.discount_type,
                    c.discount_value,
                    c.max_usage_total,
                    c.current_usage_count,
                    COALESCE(SUM(cr.discount_amount_applied), 0) as total_discount_given,
                    COUNT(cr.redemption_id) as total_redemptions,
                    c.created_at
                FROM coupons c
                LEFT JOIN coupon_redemptions cr ON c.coupon_id = cr.coupon_id
                WHERE c.business_id = %s
                GROUP BY c.coupon_id
                ORDER BY c.created_at DESC
            """, [business_id])
            
            columns = [col[0] for col in cursor.description]
            analytics_data = [dict(zip(columns, row)) for row in cursor.fetchall()]

        return Response({
            'success': True,
            'message': 'Coupon analytics retrieved successfully',
            'data': analytics_data
        }, status=status.HTTP_200_OK)

    except Exception as e:
        return Response({
            'success': False,
            'message': f'Error retrieving analytics: {str(e)}'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
