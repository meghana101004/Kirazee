from django.utils import timezone
from datetime import datetime
from django.db import models
import pytz
import bcrypt
import secrets
from .models import BusinessStaff, RoleBasedNavItems

def get_ist_now():
    """
    Get current timestamp in IST timezone.
    Since USE_TZ = False in settings, we need to manually handle timezone conversion.
    """
    utc_now = datetime.utcnow()
    ist_tz = pytz.timezone('Asia/Kolkata')
    utc_tz = pytz.timezone('UTC')
    
    # Convert UTC to IST
    utc_aware = utc_tz.localize(utc_now)
    ist_aware = utc_aware.astimezone(ist_tz)
    
    # Return naive datetime in IST (since USE_TZ = False)
    return ist_aware.replace(tzinfo=None)


# ==================== Staff Authentication Utilities ====================

def hash_password(password: str) -> str:
    """Hash a password using bcrypt"""
    salt = bcrypt.gensalt()
    return bcrypt.hashpw(password.encode('utf-8'), salt).decode('utf-8')


def verify_password(password: str, hashed_password: str) -> bool:
    """Verify a password against its hash"""
    return bcrypt.checkpw(password.encode('utf-8'), hashed_password.encode('utf-8'))


def generate_otp() -> str:
    """Generate 6-digit OTP"""
    return ''.join(str(secrets.randbelow(10)) for _ in range(6))


def get_staff_navigation_items(staff: BusinessStaff) -> list:
    """
    Get hierarchical navigation items for a staff member based on their role
    """
    nav_items_ids = staff.nav_items or []
    navigation_items = []
    
    if nav_items_ids:
        # Get parent items first
        parent_items = RoleBasedNavItems.objects.filter(
            id__in=nav_items_ids,
            status=True,
            is_visible=True,
            parent__isnull=True
        ).order_by('order_index')
        
        # Build hierarchical structure
        for parent in parent_items:
            parent_data = {
                'id': parent.id,
                'nav_name': parent.nav_name,
                'icon': parent.icon,
                'route_path': parent.route_path,
                'order_index': parent.order_index,
                'children': []
            }
            
            # Get children for this parent
            children = RoleBasedNavItems.objects.filter(
                parent_id=parent.id,
                id__in=nav_items_ids,
                status=True,
                is_visible=True
            ).order_by('order_index')
            
            for child in children:
                parent_data['children'].append({
                    'id': child.id,
                    'nav_name': child.nav_name,
                    'sub_nav': child.sub_nav,
                    'icon': child.icon,
                    'route_path': child.route_path,
                    'order_index': child.order_index
                })
            
            navigation_items.append(parent_data)
    
    return navigation_items


def get_role_based_navigation_items(role: str) -> list:
    """
    Get navigation items based on staff role (fallback if nav_items is not set)
    """
    role_navigation_mapping = {
        'Manager': [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23, 24, 25, 26],
        'Admin': [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23, 24, 25, 26],
        'Employee': [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 25],
        'Cashier': [1, 13, 14, 18],
        'Store Keeper': [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 18, 25],
        'Accountant': [1, 2, 3, 4, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 25],
        'HR Executive': [1, 21, 22, 23, 24, 19, 20],
    }
    
    nav_ids = role_navigation_mapping.get(role, [1])  # Default to business overview
    
    navigation_items = []
    parent_items = RoleBasedNavItems.objects.filter(
        id__in=nav_ids,
        status=True,
        is_visible=True,
        parent__isnull=True
    ).order_by('order_index')
    
    for parent in parent_items:
        parent_data = {
            'id': parent.id,
            'nav_name': parent.nav_name,
            'icon': parent.icon,
            'route_path': parent.route_path,
            'order_index': parent.order_index,
            'children': []
        }
        
        children = RoleBasedNavItems.objects.filter(
            parent_id=parent.id,
            id__in=nav_ids,
            status=True,
            is_visible=True
        ).order_by('order_index')
        
        for child in children:
            parent_data['children'].append({
                'id': child.id,
                'nav_name': child.nav_name,
                'sub_nav': child.sub_nav,
                'icon': child.icon,
                'route_path': child.route_path,
                'order_index': child.order_index
            })
        
        navigation_items.append(parent_data)
    
    return navigation_items


def validate_staff_credentials(login_identifier: str, password: str = None, otp_code: str = None) -> tuple:
    """
    Validate staff credentials for password or OTP login
    Returns: (success: bool, staff_instance: BusinessStaff or None, error_message: str)
    """
    try:
        staff = BusinessStaff.objects.get(
            models.Q(email=login_identifier) | models.Q(mobile_number=login_identifier),
            status=True
        )
        
        if password:
            # Password validation
            if not staff.password_hash:
                return False, None, "Password authentication not set up for this account"
            
            if not verify_password(password, staff.password_hash):
                return False, None, "Invalid password"
                
        elif otp_code:
            # OTP validation
            if not staff.otp_code:
                return False, None, "No OTP generated for this account"
            
            if staff.otp_code != otp_code:
                return False, None, "Invalid OTP"
            
            if timezone.now() > staff.otp_expires_at:
                return False, None, "OTP has expired"
        else:
            return False, None, "Either password or OTP code is required"
        
        return True, staff, "Authentication successful"
        
    except BusinessStaff.DoesNotExist:
        return False, None, "Staff account not found"
    except Exception as e:
        return False, None, f"Authentication error: {str(e)}"


def create_staff_login_session(staff: BusinessStaff, login_method: str, request=None) -> dict:
    """
    Create staff login session data
    """
    # Update last login
    staff.last_login = timezone.now()
    staff.login_method = login_method
    staff.save(update_fields=['last_login', 'login_method'])
    
    # Get navigation items
    navigation_items = get_staff_navigation_items(staff)
    
    return {
        'staff_id': staff.staff_id,
        'business_id': staff.business_id.business_id,
        'staff_name': staff.full_name,
        'role': staff.role,
        'email': staff.email,
        'mobile_number': staff.mobile_number,
        'last_login': staff.last_login,
        'navigation_items': navigation_items,
        'login_method': login_method
    }

def get_mysql_ist_timestamp():
    """
    Get MySQL function call for IST timestamp.
    Use this in raw SQL queries.
    """
    return "CONVERT_TZ(NOW(), 'UTC', 'Asia/Kolkata')"
