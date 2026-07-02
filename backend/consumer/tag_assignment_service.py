from django.db.models import Sum, Count, Q
from django.utils import timezone
from datetime import timedelta
from decimal import Decimal
from .models import UserTags, Orders, OrderItems
from kirazee_app.models import Registration


class TagAssignmentService:
    """
    Service for automatic tag assignment based on user behavior
    """
    
    # Configuration thresholds
    LOYALTY_THRESHOLDS = {
        'new_user': {'order_count': 1},
        'regular_customer': {'order_count': 5},
        'loyal_customer': {'order_count': 15},
        'vip': {'order_count': 30},
        'premium_customer': {'order_count': 50}
    }
    
    SPENDING_THRESHOLDS = {
        'high_spender': {'total_spent': Decimal('5000.00')},
        'premium_spender': {'total_spent': Decimal('10000.00')},
        'vip_spender': {'total_spent': Decimal('25000.00')}
    }
    
    @classmethod
    def assign_first_order_tag(cls, user_id):
        """
        Assign 'new_user' tag when user completes their first order
        """
        try:
            user = Registration.objects.get(user_id=user_id)
            
            # Check if user already has new_user tag
            if UserTags.objects.filter(user_id=user, tag='new_user').exists():
                return False
            
            # Count delivered orders
            delivered_orders = Orders.objects.filter(
                user_id=user,
                status=Orders.OrderStatus.DELIVERED
            ).count()
            
            if delivered_orders == 1:
                UserTags.objects.get_or_create(user_id=user, tag='new_user')
                return True
                
        except Registration.DoesNotExist:
            pass
        
        return False
    
    @classmethod
    def assign_loyalty_tags(cls, user_id):
        """
        Assign loyalty tags based on order count
        """
        try:
            user = Registration.objects.get(user_id=user_id)
            
            # Count delivered orders
            delivered_orders = Orders.objects.filter(
                user_id=user,
                status=Orders.OrderStatus.DELIVERED
            ).count()
            
            # Determine appropriate loyalty tag
            current_tag = None
            for tag_name, config in cls.LOYALTY_THRESHOLDS.items():
                if delivered_orders >= config['order_count']:
                    current_tag = tag_name
            
            if current_tag:
                UserTags.objects.get_or_create(user_id=user, tag=current_tag)
                
                # Remove lower-level tags if user has reached higher level
                lower_tags = []
                found_current = False
                for tag_name in cls.LOYALTY_THRESHOLDS.keys():
                    if tag_name == current_tag:
                        found_current = True
                    elif found_current:
                        lower_tags.append(tag_name)
                
                UserTags.objects.filter(
                    user_id=user,
                    tag__in=lower_tags
                ).delete()
                
                return True
                
        except Registration.DoesNotExist:
            pass
        
        return False
    
    @classmethod
    def assign_spending_tags(cls, user_id):
        """
        Assign tags based on total spending
        """
        try:
            user = Registration.objects.get(user_id=user_id)
            
            # Calculate total spent on delivered orders
            total_spent = Orders.objects.filter(
                user_id=user,
                status=Orders.OrderStatus.DELIVERED
            ).aggregate(
                total=Sum('final_amount')
            )['total'] or Decimal('0.00')
            
            # Determine appropriate spending tag
            current_tag = None
            for tag_name, config in cls.SPENDING_THRESHOLDS.items():
                if total_spent >= config['total_spent']:
                    current_tag = tag_name
            
            if current_tag:
                UserTags.objects.get_or_create(user_id=user, tag=current_tag)
                return True
                
        except Registration.DoesNotExist:
            pass
        
        return False
    
    @classmethod
    def assign_behavior_tags_on_order_completion(cls, user_id):
        """
        Called when an order is completed to assign appropriate tags
        """
        changes_made = False
        
        # Assign first order tag
        if cls.assign_first_order_tag(user_id):
            changes_made = True
        
        # Assign loyalty tags
        if cls.assign_loyalty_tags(user_id):
            changes_made = True
        
        # Assign spending tags
        if cls.assign_spending_tags(user_id):
            changes_made = True
        
        return changes_made
    
    @classmethod
    def batch_update_user_tags(cls, user_ids=None):
        """
        Batch update tags for multiple users (for maintenance/cron jobs)
        """
        if user_ids is None:
            # Process all users
            user_ids = Registration.objects.filter(
                is_active=True,
                is_verified=True
            ).values_list('user_id', flat=True)
        
        updated_count = 0
        for user_id in user_ids:
            if cls.assign_behavior_tags_on_order_completion(user_id):
                updated_count += 1
        
        return updated_count
    
    @classmethod
    def get_user_tag_summary(cls, user_id):
        """
        Get summary of user's current tags and their meanings
        """
        try:
            user = Registration.objects.get(user_id=user_id)
            tags = list(UserTags.objects.filter(user_id=user).values_list('tag', flat=True))
            
            # Get order statistics
            order_stats = Orders.objects.filter(
                user_id=user,
                status=Orders.OrderStatus.DELIVERED
            ).aggregate(
                order_count=Count('order_id'),
                total_spent=Sum('final_amount')
            )
            
            return {
                'user_id': user_id,
                'tags': tags,
                'order_count': order_stats['order_count'] or 0,
                'total_spent': float(order_stats['total_spent'] or 0),
                'tag_descriptions': cls._get_tag_descriptions(tags)
            }
            
        except Registration.DoesNotExist:
            return None
    
    @classmethod
    def _get_tag_descriptions(cls, tags):
        """
        Get human-readable descriptions for tags
        """
        descriptions = {
            'new_user': 'First-time customer',
            'regular_customer': 'Regular customer (5+ orders)',
            'loyal_customer': 'Loyal customer (15+ orders)',
            'vip': 'VIP customer (30+ orders)',
            'premium_customer': 'Premium customer (50+ orders)',
            'high_spender': 'High spender (₹5,000+ spent)',
            'premium_spender': 'Premium spender (₹10,000+ spent)',
            'vip_spender': 'VIP spender (₹25,000+ spent)',
            'student_iiit': 'IIIT Student',
            'student_krea': 'KREA Student',
            'employee': 'Corporate Employee'
        }
        
        return {tag: descriptions.get(tag, 'Custom tag') for tag in tags}
