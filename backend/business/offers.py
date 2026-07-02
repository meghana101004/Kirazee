from rest_framework.decorators import api_view, parser_classes
from rest_framework.parsers import JSONParser
from rest_framework.response import Response
from rest_framework import status
from django.db import connection, transaction
from kirazee_app.models import Business, BusinessMapping
from django.conf import settings
import json
from drf_yasg.utils import swagger_auto_schema
from business.image_utils import build_s3_file_url

def _get_owned_business_ids(user_id):
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
        return [row[0] for row in cursor.fetchall()]


def _parse_ids(value):
    if value is None:
        return []
    if isinstance(value, list):
        try:
            return [int(x) for x in value if str(x).strip() != ""]
        except Exception:
            return []
    if isinstance(value, str):
        parts = [p.strip() for p in value.split(',') if p.strip() != ""]
        out = []
        for p in parts:
            try:
                out.append(int(p))
            except Exception:
                continue
        return out
    return []


@swagger_auto_schema(methods=['POST'], tags=['Business'])
@api_view(['POST'])
@parser_classes([JSONParser])
@transaction.atomic
def create_promotion(request):
    try:
        user_id = request.data.get('user_id')
        business_id = request.data.get('business_id')
        offer_type = request.data.get('offer_type')
        title = request.data.get('title')
        valid_from = request.data.get('valid_from')
        valid_to = request.data.get('valid_to')
        if not user_id:
            return Response({'success': False, 'message': 'user_id is required'}, status=status.HTTP_400_BAD_REQUEST)
        if not business_id:
            return Response({'success': False, 'message': 'business_id is required'}, status=status.HTTP_400_BAD_REQUEST)
        if not offer_type or not title or not valid_from or not valid_to:
            return Response({'success': False, 'message': 'offer_type, title, valid_from, valid_to are required'}, status=status.HTTP_400_BAD_REQUEST)
        try:
            Business.objects.get(business_id=business_id)
        except Business.DoesNotExist:
            return Response({'success': False, 'message': 'Invalid business_id'}, status=status.HTTP_404_NOT_FOUND)
        owned_ids = _get_owned_business_ids(user_id)
        if business_id not in set(owned_ids):
            return Response({'success': False, 'message': 'Not authorized for this business'}, status=status.HTTP_403_FORBIDDEN)
        reference_id = request.data.get('reference_id')
        description = request.data.get('description')
        discount_percentage = request.data.get('discount_percentage')
        discount_amount = request.data.get('discount_amount')
        original_price = request.data.get('original_price')
        offer_price = request.data.get('offer_price')
        priority = request.data.get('priority', 0)
        max_views = request.data.get('max_views')
        category_ids = _parse_ids(request.data.get('category_ids'))
        media = request.data.get('media') or []
        with connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO promotional_offers (
                    business_id, offer_type, reference_id, title, description,
                    discount_percentage, discount_amount, original_price, offer_price,
                    valid_from, valid_to, is_active, is_approved, priority, max_views,
                    current_views, created_by, created_at, updated_at
                ) VALUES (
                    %s, %s, %s, %s, %s,
                    %s, %s, %s, %s,
                    %s, %s, 1, 0, %s, %s,
                    0, %s, NOW(), NOW()
                )
                """,
                [
                    business_id, offer_type, reference_id, title, description,
                    discount_percentage, discount_amount, original_price, offer_price,
                    valid_from, valid_to, priority, max_views, user_id
                ]
            )
            cursor.execute("SELECT LAST_INSERT_ID()")
            promo_id = cursor.fetchone()[0]
            if category_ids:
                args = []
                for cid in category_ids:
                    args.extend([promo_id, cid])
                placeholders = ','.join(['(%s,%s)'] * len(category_ids))
                cursor.execute(
                    f"INSERT INTO promo_category_mapping (promo_id, category_id) VALUES {placeholders}",
                    args
                )
            if isinstance(media, list) and media:
                args = []
                placeholders_list = []
                for m in media:
                    media_type = m.get('media_type')
                    media_url = m.get('media_url')
                    thumbnail_url = m.get('thumbnail_url')
                    display_order = m.get('display_order', 0)
                    is_primary = 1 if str(m.get('is_primary', 0)).lower() in ['1', 'true', 'yes'] else 0
                    if media_type and media_url:
                        placeholders_list.append("(%s,%s,%s,%s,%s,%s,NOW())")
                        args.extend([promo_id, media_type, media_url, thumbnail_url, display_order, is_primary])
                if placeholders_list:
                    cursor.execute(
                        f"INSERT INTO promo_media (promo_id, media_type, media_url, thumbnail_url, display_order, is_primary, created_at) VALUES {','.join(placeholders_list)}",
                        args
                    )
        return Response({'success': True, 'message': 'Promotion created', 'data': {'promo_id': promo_id}}, status=status.HTTP_201_CREATED)
    except Exception as e:
        return Response({'success': False, 'message': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

@swagger_auto_schema(methods=['GET', 'POST'], tags=['Business'])
@api_view(['GET', 'POST'])
@parser_classes([JSONParser])
def list_business_offers(request, business_id=None):
    try:
        if request.method == 'GET':
            user_id = request.query_params.get('user_id')
            status_filter = request.query_params.get('status', 'all')
            offer_type_filter = request.query_params.get('offer_type')
            names_only = str(request.query_params.get('names_only', '')).lower() in ['1', 'true', 'yes']
            limit = int(request.query_params.get('limit', 50))
            offset = int(request.query_params.get('offset', 0))
        else:
            user_id = request.data.get('user_id')
            filters = request.data.get('filters', {})
            status_filter = filters.get('status', 'all')
            offer_type_filter = filters.get('offer_type')
            names_only = bool(request.data.get('names_only'))
            limit = int(filters.get('limit', 50))
            offset = int(filters.get('offset', 0))
        if not user_id:
            return Response({'success': False, 'message': 'user_id is required'}, status=status.HTTP_400_BAD_REQUEST)
        try:
            user_id = int(user_id)
        except Exception:
            return Response({'success': False, 'message': 'Invalid user_id'}, status=status.HTTP_400_BAD_REQUEST)
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT DISTINCT b.business_id, b.businessName, b.businessType, b.level, b.master, b.city, b.status, b.is_verified
                FROM business_mapping bm
                INNER JOIN businesses b ON bm.business_id = b.business_id
                WHERE bm.user_id = %s AND bm.status = 1 AND b.status = 1
                """,
                [user_id]
            )
            business_rows = cursor.fetchall()
            if not business_rows:
                return Response({'success': False, 'message': 'No businesses found for this user'}, status=status.HTTP_404_NOT_FOUND)
            all_business_ids = [r[0] for r in business_rows]
            business_details = {r[0]: {'business_id': r[0], 'business_name': r[1], 'business_type': r[2], 'level': r[3], 'master': r[4], 'city': r[5], 'status': r[6], 'is_verified': r[7]} for r in business_rows}
            masters = [r[0] for r in business_rows if str(r[3] or '').strip().lower() == 'master']
            if masters:
                placeholders = ','.join(['%s'] * len(masters))
                cursor.execute(
                    f"SELECT business_id, businessName, businessType, level, master, city, status, is_verified FROM businesses WHERE master IN ({placeholders}) AND status = 1",
                    masters
                )
                for sr in cursor.fetchall():
                    all_business_ids.append(sr[0])
                    business_details[sr[0]] = {'business_id': sr[0], 'business_name': sr[1], 'business_type': sr[2], 'level': sr[3], 'master': sr[4], 'city': sr[5], 'status': sr[6], 'is_verified': sr[7]}
            if business_id:
                if str(business_id) not in set(str(x) for x in all_business_ids):
                    return Response({'success': False, 'message': 'User not authorized for this business'}, status=status.HTTP_403_FORBIDDEN)
                all_business_ids = [business_id]
            placeholders = ','.join(['%s'] * len(all_business_ids))
            base_query = f"""
                SELECT po.promo_id, po.business_id, po.offer_type, po.reference_id, po.title, po.description,
                       po.discount_percentage, po.discount_amount, po.original_price, po.offer_price,
                       po.valid_from, po.valid_to, po.is_active, po.is_approved, po.priority, po.max_views,
                       po.current_views, po.created_by, po.approved_by, po.created_at, po.updated_at,
                       b.businessName, b.businessType, b.logo
                FROM promotional_offers po
                JOIN businesses b ON po.business_id = b.business_id
                WHERE po.business_id IN ({placeholders})
            """
            params = list(all_business_ids)
            if status_filter == 'active':
                base_query += " AND po.is_active = 1 AND po.is_approved = 1 AND NOW() BETWEEN po.valid_from AND po.valid_to"
            elif status_filter == 'pending':
                base_query += " AND po.is_approved = 0"
            elif status_filter == 'expired':
                base_query += " AND (po.valid_to < NOW() OR po.is_active = 0)"
            elif status_filter == 'upcoming':
                base_query += " AND po.valid_from > NOW() AND po.is_approved = 1"
            if offer_type_filter:
                base_query += " AND po.offer_type = %s"
                params.append(offer_type_filter)
            base_query += " ORDER BY CASE WHEN %s = 'active' THEN po.priority ELSE 0 END DESC, po.valid_from DESC LIMIT %s OFFSET %s"
            params.extend([status_filter, limit, offset])
            cursor.execute(base_query, params)
            rows = cursor.fetchall()
            if names_only:
                names = [{'promo_id': r[0], 'title': r[4], 'business_id': r[1]} for r in rows]
                return Response({'success': True, 'message': f'Retrieved {len(names)} promotion names', 'data': {'offer_names': names, 'total_offer_count': len(names)}}, status=status.HTTP_200_OK)
            promo_ids = [r[0] for r in rows]
            media_map = {}
            cat_map = {}
            if promo_ids:
                ph = ','.join(['%s'] * len(promo_ids))
                cursor.execute(f"SELECT media_id, promo_id, media_type, media_url, thumbnail_url, is_primary, display_order FROM promo_media WHERE promo_id IN ({ph}) ORDER BY is_primary DESC, display_order ASC, media_id ASC", promo_ids)
                for m in cursor.fetchall():
                    media_map.setdefault(m[1], []).append({'media_id': m[0], 'media_type': m[2], 'media_url': m[3], 'thumbnail_url': m[4], 'is_primary': int(m[5]) == 1, 'display_order': m[6]})
                cursor.execute(f"SELECT pcm.promo_id, pc.category_id, pc.name FROM promo_category_mapping pcm JOIN promo_categories pc ON pc.category_id = pcm.category_id WHERE pcm.promo_id IN ({ph})", promo_ids)
                for c in cursor.fetchall():
                    cat_map.setdefault(c[0], []).append({'category_id': c[1], 'name': c[2]})
            offers = []
            grouped = {}
            for r in rows:
                # Construct S3 logo URL
                logo_url = build_s3_file_url(r[23])
                
                data = {
                    'promo_id': r[0],
                    'business_id': r[1],
                    'offer_type': r[2],
                    'reference_id': r[3],
                    'title': r[4],
                    'description': r[5],
                    'discount_percentage': float(r[6]) if r[6] is not None else None,
                    'discount_amount': float(r[7]) if r[7] is not None else None,
                    'original_price': float(r[8]) if r[8] is not None else None,
                    'offer_price': float(r[9]) if r[9] is not None else None,
                    'valid_from': r[10].isoformat() if r[10] else None,
                    'valid_to': r[11].isoformat() if r[11] else None,
                    'is_active': bool(r[12]),
                    'is_approved': bool(r[13]),
                    'priority': r[14],
                    'max_views': r[15],
                    'current_views': r[16],
                    'created_by': r[17],
                    'approved_by': r[18],
                    'created_at': r[19].isoformat() if r[19] else None,
                    'updated_at': r[20].isoformat() if r[20] else None,
                    'business_info': {'business_name': r[21], 'business_type': r[22], 'logo': logo_url},
                    'media': media_map.get(r[0], []),
                    'categories': cat_map.get(r[0], []),
                }
                offers.append(data)
                grouped.setdefault(r[1], {'business_info': business_details.get(r[1], {}), 'offers': []})['offers'].append(data)
            return Response({'success': True, 'message': f'Retrieved {len(offers)} promotions', 'data': {'all_offers': offers, 'grouped_by_business': grouped, 'total_offer_count': len(offers)}}, status=status.HTTP_200_OK)
    except Exception as e:
        return Response({'success': False, 'message': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

@swagger_auto_schema(methods=['GET'], tags=['Business'])
@api_view(['GET'])
@parser_classes([JSONParser])
def get_promotion_details(request, promo_id):
    try:
        user_id = request.query_params.get('user_id')
        if not user_id:
            return Response({'success': False, 'message': 'user_id is required'}, status=status.HTTP_400_BAD_REQUEST)
        try:
            user_id = int(user_id)
        except Exception:
            return Response({'success': False, 'message': 'Invalid user_id'}, status=status.HTTP_400_BAD_REQUEST)
        with connection.cursor() as cursor:
            cursor.execute("SELECT business_id FROM promotional_offers WHERE promo_id = %s", [promo_id])
            row = cursor.fetchone()
            if not row:
                return Response({'success': False, 'message': 'Promotion not found'}, status=status.HTTP_404_NOT_FOUND)
            business_id = row[0]
            owned = set(_get_owned_business_ids(user_id))
            if business_id not in owned:
                return Response({'success': False, 'message': 'Not authorized for this business'}, status=status.HTTP_403_FORBIDDEN)
            cursor.execute(
                """
                SELECT po.promo_id, po.business_id, po.offer_type, po.reference_id, po.title, po.description,
                       po.discount_percentage, po.discount_amount, po.original_price, po.offer_price,
                       po.valid_from, po.valid_to, po.is_active, po.is_approved, po.priority, po.max_views,
                       po.current_views, po.created_by, po.approved_by, po.created_at, po.updated_at,
                       b.businessName, b.businessType, b.logo
                FROM promotional_offers po
                JOIN businesses b ON po.business_id = b.business_id
                WHERE po.promo_id = %s
                """,
                [promo_id]
            )
            r = cursor.fetchone()
            if not r:
                return Response({'success': False, 'message': 'Promotion not found'}, status=status.HTTP_404_NOT_FOUND)
            
            # Construct S3 logo URL
            logo_url = build_s3_file_url(r[23])
            
            data = {
                'promo_id': r[0],
                'business_id': r[1],
                'offer_type': r[2],
                'reference_id': r[3],
                'title': r[4],
                'description': r[5],
                'discount_percentage': float(r[6]) if r[6] is not None else None,
                'discount_amount': float(r[7]) if r[7] is not None else None,
                'original_price': float(r[8]) if r[8] is not None else None,
                'offer_price': float(r[9]) if r[9] is not None else None,
                'valid_from': r[10].isoformat() if r[10] else None,
                'valid_to': r[11].isoformat() if r[11] else None,
                'is_active': bool(r[12]),
                'is_approved': bool(r[13]),
                'priority': r[14],
                'max_views': r[15],
                'current_views': r[16],
                'created_by': r[17],
                'approved_by': r[18],
                'created_at': r[19].isoformat() if r[19] else None,
                'updated_at': r[20].isoformat() if r[20] else None,
                'business_info': {'business_name': r[21], 'business_type': r[22], 'logo': logo_url},
            }
            cursor.execute("SELECT media_id, media_type, media_url, thumbnail_url, is_primary, display_order FROM promo_media WHERE promo_id = %s ORDER BY is_primary DESC, display_order ASC, media_id ASC", [promo_id])
            media = []
            for m in cursor.fetchall():
                media.append({'media_id': m[0], 'media_type': m[1], 'media_url': m[2], 'thumbnail_url': m[3], 'is_primary': int(m[4]) == 1, 'display_order': m[5]})
            cursor.execute("SELECT pc.category_id, pc.name FROM promo_category_mapping pcm JOIN promo_categories pc ON pc.category_id = pcm.category_id WHERE pcm.promo_id = %s", [promo_id])
            cats = [{'category_id': c[0], 'name': c[1]} for c in cursor.fetchall()]
            data['media'] = media
            data['categories'] = cats
            return Response({'success': True, 'data': data}, status=status.HTTP_200_OK)
    except Exception as e:
        return Response({'success': False, 'message': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

@swagger_auto_schema(methods=['PUT'], tags=['Business'])
@api_view(['PUT'])
@parser_classes([JSONParser])
@transaction.atomic
def update_promotion(request, promo_id):
    try:
        user_id = request.data.get('user_id')
        if not user_id:
            return Response({'success': False, 'message': 'user_id is required'}, status=status.HTTP_400_BAD_REQUEST)
        with connection.cursor() as cursor:
            cursor.execute("SELECT business_id FROM promotional_offers WHERE promo_id = %s", [promo_id])
            row = cursor.fetchone()
            if not row:
                return Response({'success': False, 'message': 'Promotion not found'}, status=status.HTTP_404_NOT_FOUND)
            business_id = row[0]
            if business_id not in set(_get_owned_business_ids(user_id)):
                return Response({'success': False, 'message': 'Not authorized for this business'}, status=status.HTTP_403_FORBIDDEN)
            fields = ['title', 'description', 'discount_percentage', 'discount_amount', 'original_price', 'offer_price', 'valid_from', 'valid_to', 'priority', 'max_views', 'is_active']
            sets = []
            params = []
            for f in fields:
                if f in request.data:
                    sets.append(f"{f} = %s")
                    params.append(request.data.get(f))
            if not sets:
                return Response({'success': False, 'message': 'No updatable fields provided'}, status=status.HTTP_400_BAD_REQUEST)
            params.extend([promo_id])
            cursor.execute(f"UPDATE promotional_offers SET {', '.join(sets)}, updated_at = NOW() WHERE promo_id = %s", params)
        return Response({'success': True, 'message': 'Promotion updated'}, status=status.HTTP_200_OK)
    except Exception as e:
        return Response({'success': False, 'message': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

@swagger_auto_schema(methods=['PATCH'], tags=['Business'])
@api_view(['PATCH'])
@parser_classes([JSONParser])
@transaction.atomic
def toggle_promotion_status(request, promo_id):
    try:
        user_id = request.data.get('user_id')
        action = str(request.data.get('action', '')).lower()
        if not user_id:
            return Response({'success': False, 'message': 'user_id is required'}, status=status.HTTP_400_BAD_REQUEST)
        if action not in ['pause', 'resume']:
            return Response({'success': False, 'message': 'action must be pause or resume'}, status=status.HTTP_400_BAD_REQUEST)
        with connection.cursor() as cursor:
            cursor.execute("SELECT business_id FROM promotional_offers WHERE promo_id = %s", [promo_id])
            row = cursor.fetchone()
            if not row:
                return Response({'success': False, 'message': 'Promotion not found'}, status=status.HTTP_404_NOT_FOUND)
            business_id = row[0]
            if business_id not in set(_get_owned_business_ids(user_id)):
                return Response({'success': False, 'message': 'Not authorized for this business'}, status=status.HTTP_403_FORBIDDEN)
            is_active = 0 if action == 'pause' else 1
            cursor.execute("UPDATE promotional_offers SET is_active = %s, updated_at = NOW() WHERE promo_id = %s", [is_active, promo_id])
        return Response({'success': True, 'message': 'Status updated', 'data': {'is_active': is_active}}, status=status.HTTP_200_OK)
    except Exception as e:
        return Response({'success': False, 'message': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

@swagger_auto_schema(methods=['POST'], tags=['Business'])
@api_view(['POST'])
@parser_classes([JSONParser])
@transaction.atomic
def set_promotion_categories(request, promo_id):
    try:
        user_id = request.data.get('user_id')
        category_ids = _parse_ids(request.data.get('category_ids'))
        if not user_id:
            return Response({'success': False, 'message': 'user_id is required'}, status=status.HTTP_400_BAD_REQUEST)
        with connection.cursor() as cursor:
            cursor.execute("SELECT business_id FROM promotional_offers WHERE promo_id = %s", [promo_id])
            row = cursor.fetchone()
            if not row:
                return Response({'success': False, 'message': 'Promotion not found'}, status=status.HTTP_404_NOT_FOUND)
            business_id = row[0]
            if business_id not in set(_get_owned_business_ids(user_id)):
                return Response({'success': False, 'message': 'Not authorized for this business'}, status=status.HTTP_403_FORBIDDEN)
            cursor.execute("DELETE FROM promo_category_mapping WHERE promo_id = %s", [promo_id])
            if category_ids:
                args = []
                placeholders = []
                for cid in category_ids:
                    placeholders.append('(%s,%s)')
                    args.extend([promo_id, cid])
                cursor.execute(f"INSERT INTO promo_category_mapping (promo_id, category_id) VALUES {','.join(placeholders)}", args)
        return Response({'success': True, 'message': 'Categories updated'}, status=status.HTTP_200_OK)
    except Exception as e:
        return Response({'success': False, 'message': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

@swagger_auto_schema(methods=['POST'], tags=['Business'])
@api_view(['POST'])
@parser_classes([JSONParser])
@transaction.atomic
def add_promotion_media(request, promo_id):
    try:
        user_id = request.data.get('user_id')
        items = request.data.get('media') or []
        if not user_id:
            return Response({'success': False, 'message': 'user_id is required'}, status=status.HTTP_400_BAD_REQUEST)
        with connection.cursor() as cursor:
            cursor.execute("SELECT business_id FROM promotional_offers WHERE promo_id = %s", [promo_id])
            row = cursor.fetchone()
            if not row:
                return Response({'success': False, 'message': 'Promotion not found'}, status=status.HTTP_404_NOT_FOUND)
            business_id = row[0]
            if business_id not in set(_get_owned_business_ids(user_id)):
                return Response({'success': False, 'message': 'Not authorized for this business'}, status=status.HTTP_403_FORBIDDEN)
            args = []
            placeholders = []
            for m in items if isinstance(items, list) else []:
                media_type = m.get('media_type')
                media_url = m.get('media_url')
                thumbnail_url = m.get('thumbnail_url')
                display_order = m.get('display_order', 0)
                is_primary = 1 if str(m.get('is_primary', 0)).lower() in ['1', 'true', 'yes'] else 0
                if media_type and media_url:
                    placeholders.append("(%s,%s,%s,%s,%s,%s,NOW())")
                    args.extend([promo_id, media_type, media_url, thumbnail_url, display_order, is_primary])
            if placeholders:
                cursor.execute(f"INSERT INTO promo_media (promo_id, media_type, media_url, thumbnail_url, display_order, is_primary, created_at) VALUES {','.join(placeholders)}", args)
        return Response({'success': True, 'message': 'Media added'}, status=status.HTTP_200_OK)
    except Exception as e:
        return Response({'success': False, 'message': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

@swagger_auto_schema(methods=['DELETE'], tags=['Business'])
@api_view(['DELETE'])
@parser_classes([JSONParser])
@transaction.atomic
def delete_promotion_media(request, promo_id, media_id):
    try:
        user_id = request.data.get('user_id') or request.query_params.get('user_id')
        if not user_id:
            return Response({'success': False, 'message': 'user_id is required'}, status=status.HTTP_400_BAD_REQUEST)
        with connection.cursor() as cursor:
            cursor.execute("SELECT business_id FROM promotional_offers WHERE promo_id = %s", [promo_id])
            row = cursor.fetchone()
            if not row:
                return Response({'success': False, 'message': 'Promotion not found'}, status=status.HTTP_404_NOT_FOUND)
            business_id = row[0]
            if business_id not in set(_get_owned_business_ids(user_id)):
                return Response({'success': False, 'message': 'Not authorized for this business'}, status=status.HTTP_403_FORBIDDEN)
            cursor.execute("DELETE FROM promo_media WHERE media_id = %s AND promo_id = %s", [media_id, promo_id])
        return Response({'success': True, 'message': 'Media deleted'}, status=status.HTTP_200_OK)
    except Exception as e:
        return Response({'success': False, 'message': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

@swagger_auto_schema(methods=['GET'],tags=['Business'])
@api_view(['GET'])
@parser_classes([JSONParser])
def offers_feed(request):
    try:
        category_id = request.query_params.get('category_id')
        business_type = request.query_params.get('business_type')
        offer_type = request.query_params.get('offer_type')
        status_param = (request.query_params.get('status') or 'all').strip().lower()
        limit = int(request.query_params.get('limit', 20))
        offset = int(request.query_params.get('offset', 0))
        params = []
        base = """
            SELECT po.promo_id, po.business_id, po.offer_type, po.title, po.description,
                   po.discount_percentage, po.discount_amount, po.original_price, po.offer_price,
                   po.valid_from, po.valid_to, po.priority, b.businessName, b.businessType, b.logo
            FROM promotional_offers po
            JOIN businesses b ON b.business_id = po.business_id
            WHERE 1=1 AND po.is_active = 1 AND po.is_approved = 1
        """

        # Apply status filter: active|pending|expired|upcoming|all (default: all)
        if status_param == 'active':
            base += " AND po.is_active = 1 AND po.is_approved = 1 AND NOW() BETWEEN po.valid_from AND po.valid_to"
        elif status_param == 'pending':
            base += " AND po.is_approved = 0"
        elif status_param == 'expired':
            base += " AND (po.valid_to < NOW() OR po.is_active = 0)"
        elif status_param == 'upcoming':
            base += " AND po.valid_from > NOW() AND po.is_approved = 1"
        else:
            # 'all' -> no additional constraints
            pass

        if offer_type:
            base += " AND po.offer_type = %s"
            params.append(offer_type)
        if business_type:
            base += " AND b.businessType = %s"
            params.append(business_type)
        if category_id:
            base += " AND EXISTS (SELECT 1 FROM promo_category_mapping pcm WHERE pcm.promo_id = po.promo_id AND pcm.category_id = %s)"
            params.append(int(category_id))
        base += " ORDER BY po.priority DESC, po.created_at DESC LIMIT %s OFFSET %s"
        params.extend([limit, offset])
        with connection.cursor() as cursor:
            cursor.execute(base, params)
            rows = cursor.fetchall()
            promo_ids = [r[0] for r in rows]
            media_map = {}
            if promo_ids:
                ph = ','.join(['%s'] * len(promo_ids))
                cursor.execute(f"SELECT promo_id, media_type, media_url, thumbnail_url FROM promo_media WHERE promo_id IN ({ph}) AND is_primary = 1", promo_ids)
                for m in cursor.fetchall():
                    media_map[m[0]] = {'media_type': m[1], 'media_url': m[2], 'thumbnail_url': m[3]}
            feed = []
            for r in rows:
                # Construct S3 logo URL
                logo_url = build_s3_file_url(r[14])
                
                feed.append({
                    'promo_id': r[0],
                    'business_id': r[1],
                    'offer_type': r[2],
                    'title': r[3],
                    'description': r[4],
                    'discount_percentage': float(r[5]) if r[5] is not None else None,
                    'discount_amount': float(r[6]) if r[6] is not None else None,
                    'original_price': float(r[7]) if r[7] is not None else None,
                    'offer_price': float(r[8]) if r[8] is not None else None,
                    'valid_from': r[9].isoformat() if r[9] else None,
                    'valid_to': r[10].isoformat() if r[10] else None,
                    'priority': r[11],
                    'business': {'name': r[12], 'type': r[13], 'logo': logo_url},
                    'primary_media': media_map.get(r[0])
                })
        return Response({'success': True, 'data': {'feed': feed, 'count': len(feed)}}, status=status.HTTP_200_OK)
    except Exception as e:
        return Response({'success': False, 'message': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

@swagger_auto_schema(methods=['POST'], tags=['Business'])
@api_view(['POST'])
@parser_classes([JSONParser])
@transaction.atomic
def click_promotion(request, promo_id):
    try:
        user_id = request.data.get('user_id')
        device_id = request.data.get('device_id')
        referrer = request.data.get('referrer')
        session_id = request.data.get('session_id')
        ip_address = request.META.get('HTTP_X_FORWARDED_FOR') or request.META.get('REMOTE_ADDR')
        if isinstance(ip_address, str) and ',' in ip_address:
            ip_address = ip_address.split(',')[0].strip()
        user_agent = request.META.get('HTTP_USER_AGENT')
        with connection.cursor() as cursor:
            cursor.execute("INSERT INTO promo_click_analytics (promo_id, user_id, device_id, ip_address, user_agent, referrer, session_id) VALUES (%s,%s,%s,%s,%s,%s,%s)", [promo_id, user_id, device_id, ip_address, user_agent, referrer, session_id])
            cursor.execute("""
                SELECT po.business_id, b.businessType
                FROM promotional_offers po JOIN businesses b ON b.business_id = po.business_id
                WHERE po.promo_id = %s
            """, [promo_id])
            r = cursor.fetchone()
            redirect = None
            if r:
                redirect = {'business_id': r[0], 'business_type': r[1]}
        return Response({'success': True, 'message': 'Click logged', 'data': {'redirect_to': redirect}}, status=status.HTTP_200_OK)
    except Exception as e:
        return Response({'success': False, 'message': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

@swagger_auto_schema(methods=['POST'], tags=['Business'])
@api_view(['POST'])
@parser_classes([JSONParser])
@transaction.atomic
def approve_promotion_admin(request, promo_id):
    try:
        admin_user_id = request.data.get('admin_user_id')
        action = str(request.data.get('action', 'approve')).lower()
        comments = request.data.get('comments')
        if not admin_user_id:
            return Response({'success': False, 'message': 'admin_user_id is required'}, status=status.HTTP_400_BAD_REQUEST)
        if action not in ['approve', 'reject']:
            return Response({'success': False, 'message': 'action must be approve or reject'}, status=status.HTTP_400_BAD_REQUEST)
        is_approved = 1 if action == 'approve' else 0
        with connection.cursor() as cursor:
            cursor.execute("UPDATE promotional_offers SET is_approved = %s, approved_by = %s, updated_at = NOW() WHERE promo_id = %s", [is_approved, admin_user_id, promo_id])
            cursor.execute("INSERT INTO promo_approval_history (promo_id, action, performed_by, comments) VALUES (%s,%s,%s,%s)", [promo_id, 'APPROVED' if is_approved else 'REJECTED', admin_user_id, comments])
        return Response({'success': True, 'message': 'Promotion approval updated', 'data': {'is_approved': is_approved}}, status=status.HTTP_200_OK)
    except Exception as e:
        return Response({'success': False, 'message': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
