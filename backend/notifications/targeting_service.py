from django.db import connection
from typing import List, Dict, Any, Optional
import logging

logger = logging.getLogger(__name__)


class TargetAudienceService:
    
    @staticmethod
    def get_all_users(limit: int = 1000, offset: int = 0) -> List[Dict[str, Any]]:
        """Return all active users with pagination"""
        try:
            with connection.cursor() as cursor:
                query = """
                    SELECT 
                        r.user_id as id,
                        CONCAT(r.firstName, ' ', r.lastName) as full_name,
                        r.emailID as email,
                        CONCAT(r.countryCode, ' ', r.mobileNumber) as mobile,
                        r.user_mode,
                        r.tokenID as fcm_token,
                        r.os as device_type,
                        r.is_active,
                        r.created_at,
                        b.business_id,
                        b.businessName as business_name
                    FROM registrations r
                    LEFT JOIN business_mapping bm ON r.user_id = bm.user_id
                    LEFT JOIN businesses b ON bm.business_id = b.business_id
                    WHERE r.is_active = 1 AND r.status = 1
                    ORDER BY r.created_at DESC
                    LIMIT %s OFFSET %s
                """
                cursor.execute(query, [limit, offset])
                columns = [desc[0] for desc in cursor.description]
                users = []
                for row in cursor.fetchall():
                    user_dict = dict(zip(columns, row))
                    # Clean mobile number
                    if user_dict['mobile']:
                        user_dict['mobile'] = user_dict['mobile'].replace(' ', '')
                    users.append(user_dict)
                return users
        except Exception as e:
            logger.error(f"Error getting all users: {str(e)}")
            return []
    
    @staticmethod
    def get_users_by_business_ids(business_ids: List[str]) -> List[Dict[str, Any]]:
        """Get users associated with specific businesses"""
        if not business_ids:
            return []
        
        try:
            with connection.cursor() as cursor:
                placeholders = ','.join(['%s'] * len(business_ids))
                query = f"""
                    SELECT DISTINCT
                        r.user_id as id,
                        CONCAT(r.firstName, ' ', r.lastName) as full_name,
                        r.emailID as email,
                        CONCAT(r.countryCode, ' ', r.mobileNumber) as mobile,
                        r.user_mode,
                        r.tokenID as fcm_token,
                        r.os as device_type,
                        r.is_active,
                        r.created_at,
                        b.business_id,
                        b.businessName as business_name
                    FROM registrations r
                    INNER JOIN business_mapping bm ON r.user_id = bm.user_id
                    INNER JOIN businesses b ON bm.business_id = b.business_id
                    WHERE bm.business_id IN ({placeholders})
                    AND r.is_active = 1 AND r.status = 1
                    ORDER BY r.created_at DESC
                """
                cursor.execute(query, business_ids)
                columns = [desc[0] for desc in cursor.description]
                users = []
                for row in cursor.fetchall():
                    user_dict = dict(zip(columns, row))
                    if user_dict['mobile']:
                        user_dict['mobile'] = user_dict['mobile'].replace(' ', '')
                    users.append(user_dict)
                return users
        except Exception as e:
            logger.error(f"Error getting users by business IDs: {str(e)}")
            return []
    
    @staticmethod
    def get_users_by_modes(user_modes: List[str]) -> List[Dict[str, Any]]:
        """Get users by user_mode"""
        if not user_modes:
            return []
        
        try:
            with connection.cursor() as cursor:
                placeholders = ','.join(['%s'] * len(user_modes))
                query = f"""
                    SELECT 
                        r.user_id as id,
                        CONCAT(r.firstName, ' ', r.lastName) as full_name,
                        r.emailID as email,
                        CONCAT(r.countryCode, ' ', r.mobileNumber) as mobile,
                        r.user_mode,
                        r.tokenID as fcm_token,
                        r.os as device_type,
                        r.is_active,
                        r.created_at,
                        b.business_id,
                        b.businessName as business_name
                    FROM registrations r
                    LEFT JOIN business_mapping bm ON r.user_id = bm.user_id
                    LEFT JOIN businesses b ON bm.business_id = b.business_id
                    WHERE r.user_mode IN ({placeholders})
                    AND r.is_active = 1 AND r.status = 1
                    ORDER BY r.created_at DESC
                """
                cursor.execute(query, user_modes)
                columns = [desc[0] for desc in cursor.description]
                users = []
                for row in cursor.fetchall():
                    user_dict = dict(zip(columns, row))
                    if user_dict['mobile']:
                        user_dict['mobile'] = user_dict['mobile'].replace(' ', '')
                    users.append(user_dict)
                return users
        except Exception as e:
            logger.error(f"Error getting users by modes: {str(e)}")
            return []
    
    @staticmethod
    def get_users_by_ids(user_ids: List[int]) -> List[Dict[str, Any]]:
        """Get specific users by IDs"""
        if not user_ids:
            return []
        
        try:
            with connection.cursor() as cursor:
                placeholders = ','.join(['%s'] * len(user_ids))
                query = f"""
                    SELECT 
                        r.user_id as id,
                        CONCAT(r.firstName, ' ', r.lastName) as full_name,
                        r.emailID as email,
                        CONCAT(r.countryCode, ' ', r.mobileNumber) as mobile,
                        r.user_mode,
                        r.tokenID as fcm_token,
                        r.os as device_type,
                        r.is_active,
                        r.created_at,
                        b.business_id,
                        b.businessName as business_name
                    FROM registrations r
                    LEFT JOIN business_mapping bm ON r.user_id = bm.user_id
                    LEFT JOIN businesses b ON bm.business_id = b.business_id
                    WHERE r.user_id IN ({placeholders})
                    AND r.is_active = 1 AND r.status = 1
                    ORDER BY r.created_at DESC
                """
                cursor.execute(query, user_ids)
                columns = [desc[0] for desc in cursor.description]
                users = []
                for row in cursor.fetchall():
                    user_dict = dict(zip(columns, row))
                    if user_dict['mobile']:
                        user_dict['mobile'] = user_dict['mobile'].replace(' ', '')
                    users.append(user_dict)
                return users
        except Exception as e:
            logger.error(f"Error getting users by IDs: {str(e)}")
            return []
    
    @staticmethod
    def search_users(search: str = '', user_mode: str = '', business_id: str = '', 
                    page: int = 1, per_page: int = 50) -> Dict[str, Any]:
        """Search users with pagination for admin UI"""
        try:
            offset = (page - 1) * per_page
            conditions = ["r.is_active = 1", "r.status = 1"]
            params = []
            
            if search:
                conditions.append("""
                    (r.firstName LIKE %s OR r.lastName LIKE %s OR 
                     r.emailID LIKE %s OR r.mobileNumber LIKE %s)
                """)
                search_param = f"%{search}%"
                params.extend([search_param, search_param, search_param, search_param])
            
            if user_mode:
                conditions.append("r.user_mode = %s")
                params.append(user_mode)
            
            if business_id:
                conditions.append("b.business_id = %s")
                params.append(business_id)
            
            where_clause = " AND ".join(conditions)
            
            with connection.cursor() as cursor:
                # Get total count
                count_query = f"""
                    SELECT COUNT(*) as total
                    FROM registrations r
                    LEFT JOIN business_mapping bm ON r.user_id = bm.user_id
                    LEFT JOIN businesses b ON bm.business_id = b.business_id
                    WHERE {where_clause}
                """
                cursor.execute(count_query, params)
                total_users = cursor.fetchone()[0]
                
                # Get users
                query = f"""
                    SELECT 
                        r.user_id as id,
                        CONCAT(r.firstName, ' ', r.lastName) as full_name,
                        r.emailID as email,
                        CONCAT(r.countryCode, ' ', r.mobileNumber) as mobile,
                        r.user_mode,
                        r.tokenID as fcm_token,
                        r.os as device_type,
                        r.is_active,
                        r.created_at,
                        b.business_id,
                        b.businessName as business_name
                    FROM registrations r
                    LEFT JOIN business_mapping bm ON r.user_id = bm.user_id
                    LEFT JOIN businesses b ON bm.business_id = b.business_id
                    WHERE {where_clause}
                    ORDER BY r.created_at DESC
                    LIMIT %s OFFSET %s
                """
                cursor.execute(query, params + [per_page, offset])
                columns = [desc[0] for desc in cursor.description]
                users = []
                for row in cursor.fetchall():
                    user_dict = dict(zip(columns, row))
                    if user_dict['mobile']:
                        user_dict['mobile'] = user_dict['mobile'].replace(' ', '')
                    users.append(user_dict)
                
                total_pages = (total_users + per_page - 1) // per_page
                
                return {
                    'users': users,
                    'pagination': {
                        'total_users': total_users,
                        'current_page': page,
                        'per_page': per_page,
                        'total_pages': total_pages
                    }
                }
        except Exception as e:
            logger.error(f"Error searching users: {str(e)}")
            return {
                'users': [],
                'pagination': {
                    'total_users': 0,
                    'current_page': page,
                    'per_page': per_page,
                    'total_pages': 0
                }
            }
    
    @staticmethod
    def get_business_list(search: str = '') -> List[Dict[str, Any]]:
        """Get list of businesses for targeting"""
        try:
            with connection.cursor() as cursor:
                conditions = ["b.status = 1"]
                params = []
                
                if search:
                    conditions.append("""
                        (b.businessName LIKE %s OR b.businessEmail LIKE %s OR 
                         b.businessNumber LIKE %s)
                    """)
                    search_param = f"%{search}%"
                    params.extend([search_param, search_param, search_param])
                
                where_clause = " AND ".join(conditions)
                
                query = f"""
                    SELECT 
                        b.business_id as id,
                        b.businessName as business_name,
                        b.businessType as business_type,
                        b.businessEmail as email,
                        b.businessNumber as mobile,
                        b.address,
                        b.status as is_active,
                        CONCAT(r.firstName, ' ', r.lastName) as owner_name,
                        r.emailID as owner_email
                    FROM businesses b
                    LEFT JOIN business_mapping bm ON b.business_id = bm.business_id
                    LEFT JOIN registrations r ON bm.user_id = r.user_id
                    WHERE {where_clause}
                    ORDER BY b.businessName
                """
                cursor.execute(query, params)
                columns = [desc[0] for desc in cursor.description]
                businesses = []
                for row in cursor.fetchall():
                    business_dict = dict(zip(columns, row))
                    # Get active users count for this business
                    business_dict['active_users_count'] = TargetAudienceService._get_business_user_count(business_dict['id'])
                    businesses.append(business_dict)
                return businesses
        except Exception as e:
            logger.error(f"Error getting business list: {str(e)}")
            return []
    
    @staticmethod
    def _get_business_user_count(business_id: str) -> int:
        """Get count of active users for a business"""
        try:
            with connection.cursor() as cursor:
                query = """
                    SELECT COUNT(DISTINCT o.user_id) as count
                    FROM orders o
                    WHERE o.business_id = %s
                    AND o.user_id IN (
                        SELECT user_id FROM registrations 
                        WHERE is_active = 1 AND status = 1
                    )
                """
                cursor.execute(query, [business_id])
                result = cursor.fetchone()
                return result[0] if result else 0
        except Exception as e:
            logger.error(f"Error getting business user count: {str(e)}")
            return 0
    
    @staticmethod
    def get_user_modes() -> List[Dict[str, Any]]:
        """Get available user modes with counts"""
        try:
            with connection.cursor() as cursor:
                query = """
                    SELECT user_mode as mode, COUNT(*) as count
                    FROM registrations
                    WHERE is_active = 1 AND status = 1
                    GROUP BY user_mode
                    ORDER BY count DESC
                """
                cursor.execute(query)
                return [{'mode': row[0], 'count': row[1]} for row in cursor.fetchall()]
        except Exception as e:
            logger.error(f"Error getting user modes: {str(e)}")
            return []
