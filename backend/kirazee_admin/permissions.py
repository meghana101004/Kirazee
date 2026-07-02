from rest_framework.permissions import BasePermission
from django.contrib.auth.models import User
from rest_framework.request import Request
from rest_framework.views import APIView

class IsSuperAdminOrReadOnly(BasePermission):
    """
    Custom permission class for admin dashboard
    - Superusers: Full access (GET, POST, PUT, DELETE)
    - Other authenticated users: Read-only access (GET only)
    - Unauthenticated users: No access
    """
    
    def has_permission(self, request: Request, view: APIView) -> bool:
        """
        Check if user has permission for the requested action
        """
        if not request.user or not request.user.is_authenticated:
            return False
        
        # Superusers have full access
        if request.user.is_superuser:
            return True
        
        # Other authenticated users only have read-only access
        if request.method in ['GET', 'HEAD', 'OPTIONS']:
            return True
        
        # Non-superusers cannot modify data
        return False
    
    def has_object_permission(self, request: Request, view: APIView, obj) -> bool:
        """
        Object-level permission (same as has_permission for this use case)
        """
        return self.has_permission(request, view)


class IsSuperAdminOrDashboardViewer(BasePermission):
    """
    Permission class specifically for dashboard viewing
    Allows:
    - Superusers: Full access
    - Staff users: Dashboard read access
    - Users with 'dashboard_viewer' group: Dashboard read access
    """
    
    def has_permission(self, request: Request, view: APIView) -> bool:
        """
        Check if user can access dashboard endpoints
        """
        if not request.user or not request.user.is_authenticated:
            return False
        
        # Superusers have full access
        if request.user.is_superuser:
            return True
        
        # Staff users have dashboard access
        if request.user.is_staff:
            return True
        
        # Check if user belongs to dashboard_viewer group
        return request.user.groups.filter(name='dashboard_viewer').exists()


class IsSuperAdminOrBusinessOwner(BasePermission):
    """
    Permission class for business-specific endpoints
    Allows:
    - Superusers: Full access to all businesses
    - Business owners: Access to their own businesses only
    """
    
    def has_permission(self, request: Request, view: APIView) -> bool:
        """
        Base permission check
        """
        if not request.user or not request.user.is_authenticated:
            return False
        
        # Superusers have full access
        if request.user.is_superuser:
            return True
        
        # For non-superusers, we'll check object-level permissions
        return request.method in ['GET', 'HEAD', 'OPTIONS']
    
    def has_object_permission(self, request: Request, view: APIView, obj) -> bool:
        """
        Object-level permission for business-specific resources
        """
        if not request.user or not request.user.is_authenticated:
            return False
        
        # Superusers have full access
        if request.user.is_superuser:
            return True
        
        # Check if user owns this business
        # This assumes the object has a business_id or owner field
        if hasattr(obj, 'business_id'):
            from business.models import BusinessMapping
            return BusinessMapping.objects.filter(
                user=request.user,
                business_id=obj.business_id,
                role='owner'
            ).exists()
        
        if hasattr(obj, 'owner'):
            return obj.owner == request.user
        
        return False


class IsDeliveryPartnerOrReadOnly(BasePermission):
    """
    Permission class for delivery partner endpoints
    Allows:
    - Superusers: Full access
    - Delivery partners: Access to their own data
    - Others: Read-only access
    """
    
    def has_permission(self, request: Request, view: APIView) -> bool:
        """
        Base permission check
        """
        if not request.user or not request.user.is_authenticated:
            return False
        
        # Superusers have full access
        if request.user.is_superuser:
            return True
        
        # Read-only access for authenticated users
        if request.method in ['GET', 'HEAD', 'OPTIONS']:
            return True
        
        # Write access only for delivery partners (will be checked at object level)
        return False
    
    def has_object_permission(self, request: Request, view: APIView, obj) -> bool:
        """
        Object-level permission for delivery partner resources
        """
        if not request.user or not request.user.is_authenticated:
            return False
        
        # Superusers have full access
        if request.user.is_superuser:
            return True
        
        # Check if user is the delivery partner
        if hasattr(obj, 'user_id'):
            return obj.user_id == request.user.id
        
        if hasattr(obj, 'id'):
            # Check if this delivery partner belongs to the user
            from management.models import Staff
            try:
                staff = Staff.objects.get(user=request.user, role='delivery_partner')
                return obj.id == staff.delivery_partner_id
            except Staff.DoesNotExist:
                return False
        
        return False


# Permission mapping for easy reference
ADMIN_PERMISSIONS = {
    'superadmin_only': IsSuperAdminOrReadOnly,
    'dashboard_viewer': IsSuperAdminOrDashboardViewer,
    'business_owner': IsSuperAdminOrBusinessOwner,
    'delivery_partner': IsDeliveryPartnerOrReadOnly,
}
