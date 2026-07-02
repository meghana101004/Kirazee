from django.core.mail import send_mail
from django.conf import settings
from django.template.loader import render_to_string
from django.utils.html import strip_tags
import logging

logger = logging.getLogger(__name__)

def send_feedback_request_email(order, user, business):
    """
    Send feedback request email to customer after order delivery
    
    Args:
        order: Order object (Orders or GroceriesOrders)
        user: Registration object (customer)
        business: Business object
    """
    try:
        # Determine order type and details
        if hasattr(order, 'order_number'):
            # Standard order
            order_id = order.order_id
            order_number = str(order.order_number) if order.order_number is not None else str(order.order_id)
            order_type = 'restaurant'
            total_amount = order.final_amount
        else:
            # Grocery order
            order_id = order.order_id
            order_number = f"GRO-{order_id}"
            order_type = 'grocery'
            total_amount = order.final_amount

        # Email context
        context = {
            'customer_name': f"{user.firstName} {user.lastName}".strip() or 'Valued Customer',
            'business_name': business.businessName,
            'order_number': order_number,
            'order_id': order_id,
            'order_type': order_type,
            'total_amount': total_amount,
            'business_id': business.business_id,
            'user_id': user.user_id,
            'feedback_url': f"{getattr(settings, 'BASE_URL')}/kirazee/consumer/feedback-form/?business_id={business.business_id}&user_id={user.user_id}&order_id={order_id}&order_type={order_type}"
        }

        # Email subject
        subject = f"How was your experience with {business.businessName}? - Order #{order_number}"

        # HTML email template
        html_message = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8">
            <title>Feedback Request</title>
            <style>
                body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
                .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
                .header {{ background-color: #f8f9fa; padding: 20px; text-align: center; border-radius: 8px; }}
                .content {{ padding: 20px 0; }}
                .order-details {{ background-color: #f8f9fa; padding: 15px; border-radius: 5px; margin: 15px 0; }}
                .cta-button {{ 
                    display: inline-block; 
                    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); 
                    color: white; 
                    padding: 15px 30px; 
                    text-decoration: none; 
                    border-radius: 8px; 
                    font-weight: bold; 
                    font-size: 16px; 
                    box-shadow: 0 4px 15px rgba(102, 126, 234, 0.4); 
                    transition: all 0.3s ease;
                    border: none;
                }}
                .cta-button:hover {{ 
                    transform: translateY(-2px); 
                    box-shadow: 0 6px 20px rgba(102, 126, 234, 0.6); 
                }}
                .footer {{ text-align: center; color: #666; font-size: 12px; margin-top: 30px; }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h2>Thank you for your order!</h2>
                    <p>We hope you enjoyed your experience with {context['business_name']}</p>
                </div>
                
                <div class="content">
                    <p>Dear {context['customer_name']},</p>
                    
                    <p>Your order has been successfully delivered! We'd love to hear about your experience.</p>
                    
                    <div class="order-details">
                        <h3>Order Details:</h3>
                        <p><strong>Order Number:</strong> {context['order_id']}</p>
                        <p><strong>Business:</strong> {context['business_name']}</p>
                        <p><strong>Total Amount:</strong> ₹{context['total_amount']}</p>
                    </div>
                    
                    <p>Your feedback helps us improve our service and helps other customers make better choices.</p>
                    
                    <div style="text-align: center; margin: 25px 0;">
                        <a href="{context['feedback_url']}" 
                           class="cta-button" 
                           style="display: inline-block; background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; padding: 15px 30px; text-decoration: none; border-radius: 8px; font-weight: bold; font-size: 16px; box-shadow: 0 4px 15px rgba(102, 126, 234, 0.4); transition: all 0.3s ease;">
                            🌟 Share Your Feedback 🌟
                        </a>
                    </div>
                    
                    <p style="text-align: center; font-size: 12px; color: #666; margin-top: 15px;">
                        Click the button above to rate your experience - it only takes 2 minutes!
                    </p>
                    
                    <p>Thank you for choosing Kirazee!</p>
                </div>
                
                <div class="footer">
                    <p>This is an automated message. Please do not reply to this email.</p>
                    <p>© 2025 Kirazee. All rights reserved.</p>
                </div>
            </div>
        </body>
        </html>
        """

        # Plain text version
        plain_message = f"""
        Dear {context['customer_name']},

        Thank you for your order with {context['business_name']}!

        Your order #{context['order_number']} has been successfully delivered.

        Order Details:
        - Order ID: {context['order_id']}
        - Business: {context['business_name']}
        - Total Amount: ₹{context['total_amount']}

        We'd love to hear about your experience! Your feedback helps us improve our service.

        🌟 SHARE YOUR FEEDBACK 🌟
        Click here to rate your experience (takes only 2 minutes):
        {context['feedback_url']}
        
        Your feedback is valuable and helps other customers make better choices!

        Thank you for choosing Kirazee!

        ---
        This is an automated message. Please do not reply to this email.
        © 2025 Kirazee. All rights reserved.
        """

        # Send email
        send_mail(
            subject=subject,
            message=plain_message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[user.emailID],
            html_message=html_message,
            fail_silently=False
        )

        logger.info(f"Feedback request email sent successfully to {user.emailID} for order {order_id}")
        return True

    except Exception as e:
        logger.error(f"Failed to send feedback request email for order {order_id}: {str(e)}")
        return False


def trigger_feedback_request(order_id, order_system='standard'):
    """
    Trigger feedback request email for a delivered order
    
    Args:
        order_id: ID of the delivered order
        order_system: 'standard' or 'grocery'
    """
    try:
        from kirazee_app.models import Registration, Business
        
        if order_system == 'standard':
            from consumer.models import Orders
            try:
                order = Orders.objects.select_related('user_id', 'business_id').get(order_id=order_id)
                user = order.user_id
                business = order.business_id
            except Orders.DoesNotExist:
                logger.error(f"Standard order {order_id} not found")
                return False
        else:  # grocery
            from consumer.gro_models import GroceriesOrders
            try:
                order = GroceriesOrders.objects.select_related('user', 'business').get(order_id=order_id)
                user = order.user
                business = order.business
            except GroceriesOrders.DoesNotExist:
                logger.error(f"Grocery order {order_id} not found")
                return False

        # Check if user has valid email
        if not user.emailID or '@' not in user.emailID:
            logger.warning(f"User {user.user_id} has invalid email: {user.emailID}")
            return False

        # Send feedback request email
        return send_feedback_request_email(order, user, business)

    except Exception as e:
        logger.error(f"Error triggering feedback request for order {order_id}: {str(e)}")
        return False
