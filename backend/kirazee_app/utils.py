import random
import smtplib
import requests
import json
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from django.conf import settings

def generate_otp():
    """
    Generates a random 6-digit OTP.
    """
    return str(random.randint(100000, 999999))

def get_email_template(template_type="login", user_name="User", otp_code="123456"):
    """
    Generate HTML email template based on type.
    
    Args:
        template_type (str): "login" or "registration"
        user_name (str): User's name
        otp_code (str): OTP code
        
    Returns:
        tuple: (subject, html_body, text_body)
    """
    
    # Template configurations
    templates = {
        "login": {
            "subject": "Kirazee - Your Login OTP",
            "title": "Login Verification",
            "message": "You're trying to log in to your Kirazee account.",
            "action": "Complete your login",
            "icon": "🔐",
            "color": "#FF6B35",  # Orange
            "gradient": "linear-gradient(135deg, #FF6B35 0%, #F7931E 50%, #FFFFFF 100%)"  # Orange to white
        },
        "registration": {
            "subject": "Kirazee - Welcome! Verify Your Account",
            "title": "Account Verification", 
            "message": "Welcome to Kirazee! Please verify your account to get started.",
            "action": "Activate your account",
            "icon": "🎉",
            "color": "#FF6B35",  # Orange
            "gradient": "linear-gradient(135deg, #FF6B35 0%, #F7931E 50%, #FFFFFF 100%)"  # Orange to white
        }
    }
    
    config = templates.get(template_type, templates["login"])
    
    # HTML Email Template
    html_body = f"""
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>{config['subject']}</title>
        <style>
            * {{ margin: 0; padding: 0; box-sizing: border-box; }}
            body {{ font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; background-color: #f8fafc; }}
            .container {{ max-width: 600px; margin: 0 auto; background-color: #ffffff; }}
            .header {{ background: linear-gradient(135deg, {config['color']} 0%, #1e293b 100%); padding: 40px 30px; text-align: center; }}
            .logo {{ color: #ffffff; font-size: 32px; font-weight: bold; margin-bottom: 10px; }}
            .header-subtitle {{ color: #e2e8f0; font-size: 16px; }}
            .content {{ padding: 40px 30px; }}
            .icon {{ font-size: 48px; text-align: center; margin-bottom: 20px; }}
            .title {{ font-size: 24px; font-weight: 600; color: #1e293b; text-align: center; margin-bottom: 16px; }}
            .message {{ font-size: 16px; color: #64748b; text-align: center; margin-bottom: 32px; line-height: 1.6; }}
            .otp-container {{ background-color: #f1f5f9; border-radius: 12px; padding: 24px; text-align: center; margin-bottom: 32px; border: 2px dashed {config['color']}; }}
            .otp-label {{ font-size: 14px; color: #64748b; margin-bottom: 8px; text-transform: uppercase; letter-spacing: 1px; }}
            .otp-code {{ font-size: 36px; font-weight: bold; color: {config['color']}; letter-spacing: 8px; font-family: 'Courier New', monospace; }}
            .validity {{ font-size: 14px; color: #ef4444; margin-top: 12px; font-weight: 500; }}
            .action-text {{ font-size: 16px; color: #374151; text-align: center; margin-bottom: 24px; }}
            .security-note {{ background-color: #fef3c7; border-left: 4px solid #f59e0b; padding: 16px; margin-bottom: 24px; border-radius: 4px; }}
            .security-title {{ font-size: 14px; font-weight: 600; color: #92400e; margin-bottom: 4px; }}
            .security-text {{ font-size: 14px; color: #a16207; }}
            .footer {{ background-color: #f8fafc; padding: 24px 30px; text-align: center; border-top: 1px solid #e2e8f0; }}
            .footer-text {{ font-size: 14px; color: #64748b; margin-bottom: 8px; }}
            .company {{ font-weight: 600; color: {config['color']}; }}
            .divider {{ height: 1px; background-color: #e2e8f0; margin: 24px 0; }}
        </style>
    </head>
    <body>
        <div class="container">
            <!-- Header -->
            <div class="header">
                <div class="logo">Kirazee</div>
                <div class="header-subtitle">Your Trusted Partner</div>
            </div>
            
            <!-- Content -->
            <div class="content">
                <div class="icon">{config['icon']}</div>
                <h1 class="title">{config['title']}</h1>
                <p class="message">Hi <strong>{user_name}</strong>,<br>{config['message']}</p>
                
                <!-- OTP Container -->
                <div class="otp-container">
                    <div class="otp-label">Your Verification Code</div>
                    <div class="otp-code">{otp_code}</div>
                    <div class="validity">⏰ Expires in 3 minutes</div>
                </div>
                
                <p class="action-text">{config['action']} by entering this code in the app.</p>
                
                <!-- Security Note -->
                <div class="security-note">
                    <div class="security-title">🔒 Security Notice</div>
                    <div class="security-text">Never share this code with anyone. Kirazee will never ask for your OTP via phone or email.</div>
                </div>
                
                <div class="divider"></div>
                
                <p style="font-size: 14px; color: #64748b; text-align: center;">
                    If you didn't request this code, please ignore this email or contact our support team.
                </p>
            </div>
            
            <!-- Footer -->
            <div class="footer">
                <div class="footer-text">Best regards,</div>
                <div class="footer-text">The <span class="company">Kirazee</span> Team</div>
                <div style="margin-top: 16px; font-size: 12px; color: #94a3b8;">
                    © 2025 Kirazee. All rights reserved.
                </div>
            </div>
        </div>
    </body>
    </html>
    """
    
    # Plain text fallback
    text_body = f"""
    {config['icon']} {config['title']} - Kirazee
    
    Hi {user_name},
    
    {config['message']}
    
    Your verification code is: {otp_code}
    
    This code will expire in 3 minutes.
    
    {config['action']} by entering this code in the app.
    
    🔒 Security Notice:
    Never share this code with anyone. Kirazee will never ask for your OTP via phone or email.
    
    If you didn't request this code, please ignore this email.
    
    Best regards,
    The Kirazee Team
    
    © 2025 Kirazee. All rights reserved.
    """
    
    return config["subject"], html_body, text_body

def send_otp_email(email, otp_code, user_name="User", template_type="login"):
    """
    Send OTP via email using beautiful HTML templates.
    
    Args:
        email (str): Recipient email address
        otp_code (str): OTP code to send
        user_name (str): User's name for personalization
        template_type (str): "login" or "registration"
    """
    try:
        # Get email template
        subject, html_body, text_body = get_email_template(template_type, user_name, otp_code)
        
        # Create message
        msg = MIMEMultipart('alternative')
        msg['From'] = f"Kirazee <{settings.EMAIL_HOST_USER}>"
        msg['To'] = email
        msg['Subject'] = subject
        
        # Create both plain text and HTML versions
        text_part = MIMEText(text_body, 'plain', 'utf-8')
        html_part = MIMEText(html_body, 'html', 'utf-8')
        
        # Add parts to message
        msg.attach(text_part)
        msg.attach(html_part)
        
        # Create SMTP session
        server = smtplib.SMTP(settings.EMAIL_HOST, settings.EMAIL_PORT)
        server.starttls()  # Enable security
        server.login(settings.EMAIL_HOST_USER, settings.EMAIL_HOST_PASSWORD)
        
        # Send email
        text = msg.as_string()
        server.sendmail(settings.EMAIL_HOST_USER, email, text)
        server.quit()
        
        print(f"✅ {template_type.title()} OTP email sent successfully to {email}")
        return True
        
    except Exception as e:
        print(f"❌ Failed to send {template_type} OTP email to {email}: {str(e)}")
        return False

def send_whatsapp_otp(phone_number: str, otp_code: str, template_type: str = "login") -> dict:
    """
    Send OTP via WhatsApp using Interakt API with smart template detection.
    
    Args:
        phone_number (str): Phone number without country code
        otp_code (str): The OTP code to send
        template_type (str): Type of OTP - "login" or "register"
        
    Returns:
        dict: Response from Interakt API
    """
    try:
        from consumer.utils.interakt import InteraktClient
        
        # Remove any non-digit characters
        phone_number = ''.join(filter(str.isdigit, str(phone_number)))
        
        client = InteraktClient()
        
        # Based on test results, these templates exist but need different parameters:
        # - kirazee_login_otp (en_US) - needs button values
        # - kirazee_registration_otp (en) - needs button values  
        # - delivery_otp_customer (en_US) - needs button values
        # - pickup_otp_for_collection (en_US) - needs 3 body values
        # - out_for_delivery_notification (en) - needs 4 body values
        # - pickup_ready_notification (en) - needs 4 body values
        
        # Try templates that exist with correct parameters
        template_configs = [
            # Template with button values (most likely for OTP)
            {
                "name": "kirazee_login_otp" if template_type.lower() == "login" else "kirazee_registration_otp",
                "language": "en_US" if template_type.lower() == "login" else "en",
                "body_values": [otp_code],
                "button_values": {"0": [otp_code]}  # Button at index 0 with OTP
            },
            {
                "name": "delivery_otp_customer",
                "language": "en_US", 
                "body_values": [otp_code],
                "button_values": {"0": [otp_code]}
            },
            # Template with 3 body values (order_id, otp, business_name)
            {
                "name": "pickup_otp_for_collection",
                "language": "en_US",
                "body_values": ["ORDER001", otp_code, "Kirazee"],  # Dummy values for missing fields
                "button_values": None
            }
        ]
        
        for config in template_configs:
            print(f"Trying template: {config['name']} with language: {config['language']}")
            
            try:
                kwargs = {
                    "country_code": "+91",
                    "phone_number": phone_number,
                    "template_name": config["name"],
                    "language_code": config["language"],
                    "body_values": config["body_values"],
                    "callback_data": f"type={template_type}_otp"
                }
                
                if config["button_values"]:
                    kwargs["button_values"] = config["button_values"]
                
                result = client.send_template(**kwargs)
                
                # If successful, return immediately
                if result.get('ok', False):
                    print(f"✅ SUCCESS: OTP sent using template: {config['name']} ({config['language']})")
                    return result
                else:
                    error_msg = result.get('response', {}).get('message', 'Unknown error')
                    print(f"❌ FAILED: {config['name']} ({config['language']}): {error_msg}")
                    
            except Exception as e:
                print(f"❌ ERROR: {config['name']} ({config['language']}): {str(e)}")
        
        # If all specific templates failed, return error
        return {
            "ok": False, 
            "error": "No working WhatsApp templates found. Please create and approve OTP templates in your Interakt dashboard.",
            "suggestion": "Create a template named 'kirazee_login_otp' with body: 'Your Kirazee login OTP is {{1}}' and approve it."
        }
        
    except ImportError:
        return {"ok": False, "error": "InteraktClient not available"}
    except Exception as e:
        return {"ok": False, "error": str(e)}

        
def send_otp_dual_channel(email, mobile_number, otp_code, template_type="LOGIN_OTP", user_name="User"):
    """
    Send OTP via both Email and WhatsApp channels with beautiful templates.
    
    Args:
        email (str): Email address
        mobile_number (str): Mobile number
        otp_code (str): 6-digit OTP code
        template_type (str): "REGISTRATION_OTP" or "LOGIN_OTP"
        user_name (str): User's name
    
    Returns:
        dict: Status of both channels
    """
    results = {
        'email_sent': False,
        'whatsapp_sent': False,
        'at_least_one_sent': False
    }
    
    # Map template types for both email and WhatsApp
    email_template_type = "registration" if template_type == "REGISTRATION_OTP" else "login"
    whatsapp_template_type = "register" if template_type == "REGISTRATION_OTP" else "login"
    
    # Send via Email with beautiful HTML template
    try:
        results['email_sent'] = send_otp_email(email, otp_code, user_name, email_template_type)
    except Exception as e:
        print(f"Email sending failed: {str(e)}")
        results['email_sent'] = False
    
    # Send via WhatsApp
    try:
        whatsapp_result = send_whatsapp_otp(mobile_number, otp_code, whatsapp_template_type)
        results['whatsapp_sent'] = whatsapp_result.get('ok', False)
    except Exception as e:
        print(f"WhatsApp sending failed: {str(e)}")
        results['whatsapp_sent'] = False
    
    # Check if at least one channel succeeded
    results['at_least_one_sent'] = results['email_sent'] or results['whatsapp_sent']
    
    return results


def send_registration_otp_service(user_email, user_mobile, user_name, otp_code):
    """
    Dedicated service for sending registration OTP to new users.
    
    This service handles the complete OTP sending process for user registration,
    including both email and WhatsApp channels with proper error handling.
    
    Args:
        user_email (str): User's email address
        user_mobile (str): User's mobile number
        user_name (str): User's full name
        otp_code (str): 6-digit OTP code
        
    Returns:
        dict: Comprehensive result containing:
            - success (bool): Overall success status
            - message (str): Descriptive message
            - email_status (dict): Email sending details
            - whatsapp_status (dict): WhatsApp sending details
            - otp_code (str): The OTP code (for testing/debugging)
            - sent_channels (list): List of successful channels
    """
    try:
        # Validate inputs
        if not all([user_email, user_mobile, user_name, otp_code]):
            return {
                'success': False,
                'message': 'Missing required parameters for OTP sending',
                'email_status': {'sent': False, 'error': 'Invalid input'},
                'whatsapp_status': {'sent': False, 'error': 'Invalid input'},
                'otp_code': otp_code,
                'sent_channels': []
            }
        
        # Validate OTP format (6 digits)
        if not (otp_code.isdigit() and len(otp_code) == 6):
            return {
                'success': False,
                'message': 'Invalid OTP format. Must be 6 digits.',
                'email_status': {'sent': False, 'error': 'Invalid OTP format'},
                'whatsapp_status': {'sent': False, 'error': 'Invalid OTP format'},
                'otp_code': otp_code,
                'sent_channels': []
            }
        
        print(f"🚀 Sending Registration OTP Service")
        print(f"📧 Email: {user_email}")
        print(f"📱 Mobile: {user_mobile}")
        print(f"👤 User Name: {user_name}")
        print(f"🔢 OTP Code: {otp_code}")
        
        # Use the existing send_otp_dual_channel function
        otp_results = send_otp_dual_channel(
            email=user_email,
            mobile_number=user_mobile,
            otp_code=otp_code,
            template_type="REGISTRATION_OTP",
            user_name=user_name
        )
        
        # Prepare detailed response
        sent_channels = []
        if otp_results.get('email_sent'):
            sent_channels.append('email')
        if otp_results.get('whatsapp_sent'):
            sent_channels.append('whatsapp')
        
        # Determine overall success
        overall_success = otp_results.get('at_least_one_sent', False)
        
        result = {
            'success': overall_success,
            'message': 'Registration OTP sent successfully' if overall_success else 'Failed to send registration OTP',
            'email_status': {
                'sent': otp_results.get('email_sent', False),
                'status': 'delivered' if otp_results.get('email_sent') else 'failed'
            },
            'whatsapp_status': {
                'sent': otp_results.get('whatsapp_sent', False),
                'status': 'delivered' if otp_results.get('whatsapp_sent') else 'failed'
            },
            'otp_code': otp_code,  # Include for testing purposes
            'sent_channels': sent_channels,
            'total_channels_attempted': 2,
            'successful_channels': len(sent_channels)
        }
        
        # Log the result
        if overall_success:
            print(f"✅ Registration OTP service completed successfully")
            print(f"📊 Sent via: {', '.join(sent_channels)}")
        else:
            print(f"❌ Registration OTP service failed")
            print(f"📊 No channels were successful")
        
        return result
        
    except Exception as e:
        error_msg = f"Registration OTP service error: {str(e)}"
        print(f"❌ {error_msg}")
        
        return {
            'success': False,
            'message': error_msg,
            'email_status': {'sent': False, 'error': str(e)},
            'whatsapp_status': {'sent': False, 'error': str(e)},
            'otp_code': otp_code,
            'sent_channels': []
        }
