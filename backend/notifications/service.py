from __future__ import annotations
from typing import Any, Dict, Optional, Tuple

from django.utils import timezone
from django.core.mail import send_mail
from django.conf import settings

from .firebase_utils import send_push_notification
from .models import NotificationLog
from django.utils import timezone
from django.core.mail import send_mail
from django.conf import settings
# NOTE: We currently read the device token from registrations.tokenID per user.
# If you later add a dedicated DeviceToken table, adjust token lookup accordingly.

def _lookup_user_token(user_id: int) -> Optional[str]:
    try:
        # Lazy import to avoid hard coupling
        from kirazee_app.models import Registration
        reg = Registration.objects.filter(user_id=user_id).only('tokenID').first()
        return getattr(reg, 'tokenID', None)
    except Exception:
        return None


def send_order_notification(user_id: int, title: str, body: str, data: Optional[Dict[str, Any]] = None, 
                           image_url: Optional[str] = None) -> Optional[str]:
    """Send a push notification and log it into notifications_log.
    Returns FCM message id on success, or None on failure.
    
    Args:
        user_id: User ID to send notification to
        title: Notification title
        body: Notification body text
        data: Additional data payload
        image_url: URL of image to display in notification
    """
    fcm_id: Optional[str] = None
    try:
        token = _lookup_user_token(user_id)
        if not token:
            NotificationLog.objects.create(
                user_id=user_id,
                title=title,
                body=body,
                data={**(data or {}), 'image_url': image_url} if image_url else (data or {}),
                status='skipped',
                error='Missing device token'
            )
            return None

        # Enhanced data with image information
        enhanced_data = data or {}
        if image_url:
            enhanced_data['image_url'] = image_url
            enhanced_data['media_type'] = 'image'

        fcm_id = send_push_notification(token, title, body, enhanced_data, image_url)
        NotificationLog.objects.create(
            user_id=user_id,
            title=title,
            body=body,
            data=enhanced_data,
            status='sent',
            fcm_id=fcm_id,
            delivered_at=timezone.now(),
        )
        return fcm_id
    except Exception as e:
        NotificationLog.objects.create(
            user_id=user_id,
            title=title,
            body=body,
            data={**(data or {}), 'image_url': image_url} if image_url else (data or {}),
            status='failed',
            error=str(e)
        )
        return None


def send_rich_notification(user_id: int, title: str, body: str, 
                          image_url: Optional[str] = None,
                          deep_link: Optional[str] = None,
                          data: Optional[Dict[str, Any]] = None) -> Optional[str]:
    """Send a rich notification with image and deep link support like Swiggy/Zomato.
    
    Args:
        user_id: User ID to send notification to
        title: Notification title
        body: Notification body text
        image_url: URL of image to display
        deep_link: Deep link URL for app navigation
        data: Additional data payload
    """
    fcm_id: Optional[str] = None
    try:
        token = _lookup_user_token(user_id)
        if not token:
            NotificationLog.objects.create(
                user_id=user_id,
                title=title,
                body=body,
                data={
                    **(data or {}),
                    'image_url': image_url,
                    'deep_link': deep_link,
                    'media_type': 'image'
                },
                status='skipped',
                error='Missing device token'
            )
            return None

        # Enhanced data with rich notification information
        enhanced_data = data or {}
        if image_url:
            enhanced_data['image_url'] = image_url
            enhanced_data['media_type'] = 'image'
        if deep_link:
            enhanced_data['deep_link'] = deep_link

        fcm_id = send_rich_notification(token, title, body, image_url, deep_link, enhanced_data)
        NotificationLog.objects.create(
            user_id=user_id,
            title=title,
            body=body,
            data=enhanced_data,
            status='sent',
            fcm_id=fcm_id,
            delivered_at=timezone.now(),
        )
        return fcm_id
    except Exception as e:
        NotificationLog.objects.create(
            user_id=user_id,
            title=title,
            body=body,
            data={
                **(data or {}),
                'image_url': image_url,
                'deep_link': deep_link,
                'media_type': 'image'
            },
            status='failed',
            error=str(e)
        )
        return None


def notify_order_placed(user_id: int, order_id: int) -> Optional[str]:
    return send_order_notification(
        user_id,
        title="Order Placed Successfully",
        body=f"Your order #{order_id} has been placed.",
        data={"type": "ORDER_PLACED", "order_id": str(order_id)}
    )


def notify_order_status(user_id: int, order_id: int, status: str) -> Optional[str]:
    human = status.replace('_', ' ').title()
    return send_order_notification(
        user_id,
        title=f"Order {human}",
        body=f"Your order #{order_id} is now {human}.",
        data={"type": "ORDER_STATUS", "order_id": str(order_id), "status": status}
    )


def notify_otp_sent(user_id: int, order_id: int, otp_code: str) -> Optional[str]:
    return send_order_notification(
        user_id,
        title="Delivery OTP",
        body=f"Your delivery OTP is {otp_code}. Share it only with the delivery partner.",
        data={"type": "OTP_SENT", "order_id": str(order_id)}
    )


def send_notification_test(user_id: int, title: str, body: str, data: Optional[Dict[str, Any]] = None, token_override: Optional[str] = None) -> Optional[str]:
    fcm_id: Optional[str] = None
    try:
        token = token_override or _lookup_user_token(user_id)
        if not token:
            NotificationLog.objects.create(
                user_id=user_id,
                title=title,
                body=body,
                data=data or {},
                status='skipped',
                error='Missing device token'
            )
            return None

        fcm_id = send_push_notification(token, title, body, data or {})
        NotificationLog.objects.create(
            user_id=user_id,
            title=title,
            body=body,
            data=data or {},
            status='sent',
            fcm_id=fcm_id,
            delivered_at=timezone.now(),
        )
        return fcm_id
    except Exception as e:
        NotificationLog.objects.create(
            user_id=user_id,
            title=title,
            body=body,
            data=data or {},
            status='failed',
            error=str(e)
        )
        return None


def _lookup_user_email(user_id: int) -> Optional[str]:
    try:
        from kirazee_app.models import Registration
        reg = Registration.objects.filter(user_id=user_id).only('emailID').first()
        return getattr(reg, 'emailID', None)
    except Exception:
        return None


def get_email_template_v2(
    template_type: str = "login",
    user_name: str = "User",
    otp_code: str = "123456",
    data: Optional[Dict[str, Any]] = None,
) -> Tuple[str, str, str]:
    data = data or {}
    t = template_type.upper()
    from datetime import datetime
    now_date = datetime.utcnow().strftime("%d %b %Y")

    brand_name = "Kirazee"
    company_note = "This is an automated message from Kirazee. Please do not reply."
    support_text = "If you didn't request this, please ignore this email or contact support."

    templates = {
        "LOGIN": {
            "subject": f"{brand_name} — Your login OTP",
            "title": "Login Verification",
            "lead": f"Hi {user_name}, you're trying to sign in to {brand_name}.",
            "accent": "#FF6B35",
            "icon": "🔐",
            "cta": "Complete your login"
        },
        "REGISTRATION": {
            "subject": f"{brand_name} — Welcome! Verify your account",
            "title": "Welcome to Kirazee",
            "lead": f"Hi {user_name}, thanks for joining {brand_name}! Verify your account to get started.",
            "accent": "#FF6B35",
            "icon": "🎉",
            "cta": "Activate your account"
        },
        "GENERIC": {
            "subject": f"{brand_name} — Notification",
            "title": f"{brand_name} Notification",
            "lead": data.get("body", "You have a new notification from Kirazee."),
            "accent": "#111827",
            "icon": "ℹ️",
            "cta": ""
        }
    }

    cfg = templates.get(t, templates["GENERIC"])

    base_style = (
        "background:#f5f7fb;margin:0;padding:24px;font-family:Inter,Segoe UI,Roboto,Arial,sans-serif;"
        "color:#111;-webkit-font-smoothing:antialiased;"
    )
    card_style = (
        "max-width:640px;margin:0 auto;background:#ffffff;border-radius:12px;overflow:hidden;"
        "box-shadow:0 6px 24px rgba(0,0,0,0.06);"
    )
    header_html = f"""
      <div style="{card_style}">
        <div style="background:linear-gradient(135deg,{cfg['accent']},#1F2937);padding:22px 28px;">
          <div style="font-size:18px;letter-spacing:.4px;color:#e6eef6;margin-bottom:6px;">{brand_name}</div>
          <div style="font-size:20px;font-weight:700;color:#fff;">{cfg['title']}</div>
        </div>
    """
    footer_html = f"""
        <div style="padding:18px 28px;border-top:1px solid #eef2f7;color:#6b7280;font-size:12px;">
          <div style="margin-bottom:6px;">{company_note}</div>
          <div style="color:#9ca3af;font-size:11px;">{now_date} · {brand_name}</div>
        </div>
      </div>
    """

    if t == "VOUCHER_ISSUED" and data.get("coupon_code"):
        coupon = data.get("coupon_code")
        discount_value = data.get("discount_value")
        valid_to = data.get("valid_to")
        order_id = data.get("order_id")
        body = data.get("body", f"We're excited to offer you this exclusive voucher as a special treat!")

        # Format discount value
        discount_display = f"₹{discount_value}" if discount_value and str(discount_value).replace('.', '').isdigit() else str(discount_value or "DISCOUNT")
        
        # New modern voucher template
        html = f"""
        <div style="{base_style}">
          <div style="max-width: 600px; margin: 0 auto; padding: 20px;">
            <div style="background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; padding: 30px; text-align: center; border-radius: 10px 10px 0 0;">
              <h1 style="margin: 0; font-size: 24px;">🎉 Exclusive Voucher!</h1>
              <p style="margin: 10px 0 0 0; font-size: 16px;">A special gift from Kirazee for your cancelled order</p>
            </div>
            
            <div style="padding: 30px; background: white; border: 1px solid #ddd; border-radius: 0 0 10px 10px;">
              <h2 style="color: #333; margin-top: 0;">Hello,</h2>
              <p style="color: #666; line-height: 1.6;">{body}</p>
              
              <div style="background: #f8f9fa; border: 2px dashed #667eea; padding: 30px; text-align: center; margin: 20px 0; border-radius: 10px;">
                <h3 style="color: #333; margin-top: 0;">🎁 Your Special Voucher</h3>
                <div style="font-size: 32px; font-weight: bold; color: #667eea; letter-spacing: 2px; margin: 20px 0; font-family: monospace;">
                  {coupon}
                </div>
                <p style="margin: 10px 0;"><strong>Discount:</strong> {discount_display} OFF</p>
                {f"<p style='margin: 10px 0;'><strong>Valid until:</strong> {valid_to}</p>" if valid_to else ""}
                {f"<p style='margin: 10px 0;'><strong>Order:</strong> #{order_id}</p>" if order_id else ""}
              </div>
              
              <h3 style="color: #333;">How to Use:</h3>
              <ol style="color: #666; line-height: 1.6;">
                <li>Shop your favorite items on Kirazee</li>
                <li>Follow the rule to redeem the voucher</li>
                <li>Enter the voucher code at checkout</li>
                <li>Enjoy your {discount_display} discount!</li>
              </ol>
              
              <div style="background: #f1f3f4; padding: 20px; border-radius: 5px; margin-top: 20px; font-size: 14px; color: #666;">
                <h4 style="margin-top: 0; color: #333;">Terms & Conditions:</h4>
                <ul style="margin: 10px 0; padding-left: 20px;">
                  <li>{f"Valid until {valid_to}" if valid_to else "Validity period applies"}</li>
                  <li>Cannot be combined with other offers</li>
                  <li>One-time use only</li>
                  <li>Kirazee reserves the right to modify/cancel the offer</li>
                </ul>
              </div>
            </div>
            
            <div style="text-align: center; margin-top: 20px; color: #666; font-size: 12px;">
              <p>This is a special voucher sent exclusively to you.</p>
              <p>© 2024 Kirazee. All rights reserved.</p>
              <p>If you didn't expect this email, please contact our support team.</p>
            </div>
          </div>
        </div>
        """

        text = f"""EXCLUSIVE VOUCHER FROM KIRAZEE
        
Hello,

We're excited to offer you this exclusive voucher as a special treat!

Here's your special voucher code:

VOUCHER CODE: {coupon}
DISCOUNT: {discount_display} OFF
{f"VALID UNTIL: {valid_to}" if valid_to else ""}
{f"ORDER: #{order_id}" if order_id else ""}

How to use:
1. Shop on Kirazee
2. Enter the code at checkout
3. Enjoy your {discount_display} discount!

Terms & Conditions:
- {f"Valid until {valid_to}" if valid_to else "Validity period applies"}
- Cannot be combined with other offers
- One-time use only
- Kirazee reserves the right to modify/cancel the offer

This is a special voucher sent exclusively to you.
© 2024 Kirazee. All rights reserved.
"""

        subject = f"🎉 Exclusive Voucher from Kirazee - Special Offer!"
        return subject, html, text

    if t == "WALLET_CREDITED":
        amount = data.get("credited_amount") or data.get("discount_value") or "0.00"
        body = data.get("body", f"Your Kirazee wallet has been credited.")
        html = f"""
        <div style="{base_style}">
          {header_html}
          <div style="padding:28px;">
            <div style="font-size:16px;color:#374151;line-height:1.6;margin-bottom:18px;">{body}</div>
            <div style="display:inline-block;padding:12px 16px;border-radius:10px;border:1px solid #e6fffa;background:#ecfeff;font-weight:700;">
              Wallet credited: ₹{amount}
            </div>
          </div>
          {footer_html}
        </div>
        """
        text = f"""{brand_name} — Wallet credited

{body}

Amount credited: ₹{amount}

{support_text}

{brand_name} Team
"""
        subject = f"{brand_name} — Wallet credited: ₹{amount}"
        return subject, html, text

    otp_block = ""
    if t in ("LOGIN", "REGISTRATION"):
        otp_block = f"""
        <div style="margin-top:22px;background:#f1f5f9;border-radius:12px;padding:20px;text-align:center;border:2px dashed {cfg['accent']}">
          <div style="font-size:13px;color:#64748b;text-transform:uppercase;letter-spacing:1px;margin-bottom:8px;">Your verification code</div>
          <div style="font-family:'Courier New',monospace;font-size:34px;font-weight:700;letter-spacing:6px;color:{cfg['accent']};">{otp_code}</div>
          <div style="font-size:13px;color:#ef4444;margin-top:10px;">⏰ Expires in 3 minutes</div>
        </div>
        """

    lead = cfg.get("lead", "")
    html = f"""
    <div style="{base_style}">
      {header_html}
      <div style="padding:28px;">
        <div style="font-size:16px;color:#374151;line-height:1.6;margin-bottom:16px;">{lead}</div>
        {otp_block}
        <div style="margin-top:20px;font-size:14px;color:#6b7280;">{support_text}</div>
      </div>
      {footer_html}
    </div>
    """

    text_body = f"""{cfg.get('icon','')} {cfg.get('title','Notification')} - {brand_name}

{lead}

{"Your verification code is: " + otp_code if otp_block else ""}
{support_text}

Best regards,
The {brand_name} Team
© {datetime.utcnow().year} {brand_name}. All rights reserved.
"""

    subject = cfg.get("subject", f"{brand_name} — Notification")
    return subject, html, text_body


def _build_html_email(subject: str, body: str, data: Optional[Dict[str, Any]] = None) -> Optional[str]:
    try:
        t = (data or {}).get('type') if isinstance(data, dict) else None
        order_id = (data or {}).get('order_id') if isinstance(data, dict) else None
        coupon_code = (data or {}).get('coupon_code') if isinstance(data, dict) else None
        discount_value = (data or {}).get('discount_value') if isinstance(data, dict) else None
        valid_to = (data or {}).get('valid_to') if isinstance(data, dict) else None
        credited_amount = (data or {}).get('credited_amount') if isinstance(data, dict) else None

        base_styles = "background:#f5f7fb;margin:0;padding:24px;font-family:Inter,Segoe UI,Roboto,Arial,sans-serif;color:#111;"
        card_styles = "max-width:640px;margin:0 auto;background:#ffffff;border-radius:12px;overflow:hidden;box-shadow:0 6px 24px rgba(0,0,0,0.06);"
        header = f"""
        <div style='{card_styles}'>
          <div style="background:linear-gradient(135deg,#111827,#1f2937);padding:24px 28px;">
            <div style="font-size:18px;letter-spacing:.4px;color:#9ca3af;margin-bottom:4px;">Kirazee</div>
            <div style="font-size:22px;font-weight:700;color:#fff;">{subject}</div>
          </div>
        """
        footer = """
          <div style="padding:18px 28px;border-top:1px solid #eef2f7;color:#6b7280;font-size:12px;">
            This is an automated message from Kirazee. Please do not reply.
          </div>
        </div>
        """

        if t == 'VOUCHER_ISSUED' and coupon_code:
            code_badge = f"<div style=\"display:inline-block;background:#111827;color:#fff;font-weight:800;font-size:28px;letter-spacing:2px;padding:14px 22px;border-radius:12px;\">{coupon_code}</div>"
            meta = []
            if discount_value is not None:
                meta.append(f"<div style='font-size:15px;color:#111;margin-top:14px;'>Value: <span style='font-weight:700'>₹{discount_value}</span></div>")
            if valid_to:
                meta.append(f"<div style='font-size:13px;color:#6b7280;margin-top:6px;'>Valid until {valid_to}</div>")
            if order_id:
                meta.append(f"<div style='font-size:12px;color:#9ca3af;margin-top:6px;'>Order #{order_id}</div>")
            html = f"""
            <div style='{base_styles}'>
              {header}
              <div style="padding:28px;">
                <div style="font-size:16px;color:#374151;line-height:1.6;margin-bottom:18px;">{body}</div>
                <div style="margin:20px 0 12px;">{code_badge}</div>
                {''.join(meta)}
                <div style="margin-top:26px;padding:14px 16px;background:#f9fafb;border:1px dashed #e5e7eb;border-radius:10px;color:#4b5563;">
                  Redeem this voucher in the Kirazee app at checkout.
                </div>
              </div>
              {footer}
            </div>
            """
            return html

        if t == 'WALLET_CREDITED':
            amount = credited_amount or discount_value
            html = f"""
            <div style='{base_styles}'>
              {header}
              <div style="padding:28px;">
                <div style="font-size:16px;color:#374151;line-height:1.6;margin-bottom:18px;">{body}</div>
                <div style="display:inline-block;background:#e6fffa;color:#065f46;border:1px solid #a7f3d0;padding:10px 14px;border-radius:10px;font-weight:600;">Wallet credited: ₹{amount}</div>
              </div>
              {footer}
            </div>
            """
            return html

        html = f"""
        <div style='{base_styles}'>
          {header}
          <div style="padding:28px;">
            <div style="font-size:16px;color:#374151;line-height:1.6;">{body}</div>
          </div>
          {footer}
        </div>
        """
        return html
    except Exception:
        return None


def send_email_notification(user_id: int, subject: str, body: str, data: Optional[Dict[str, Any]] = None, html_body: Optional[str] = None) -> bool:
    try:
        to_email = _lookup_user_email(user_id)
        if not to_email:
            NotificationLog.objects.create(
                user_id=user_id,
                title=subject,
                body=body,
                data={**(data or {}), 'channel': 'email'},
                status='skipped',
                error='Missing email address'
            )
            return False
        from_email = getattr(settings, 'DEFAULT_FROM_EMAIL', None) or 'no-reply@kirazee.local'
        html = html_body
        if not html and isinstance(data, dict):
            t = (data or {}).get('type')
            if t in ('VOUCHER_ISSUED', 'WALLET_CREDITED', 'LOGIN', 'REGISTRATION', 'GENERIC'):
                s2, h2, _ = get_email_template_v2(t, data=data)
                subject = s2
                html = h2
        if not html:
            html = _build_html_email(subject, body, data)
        if html:
            sent_count = send_mail(subject, body, from_email, [to_email], fail_silently=False, html_message=html)
        else:
            sent_count = send_mail(subject, body, from_email, [to_email], fail_silently=False)
        NotificationLog.objects.create(
            user_id=user_id,
            title=subject,
            body=body,
            data={**(data or {}), 'channel': 'email'},
            status='sent' if sent_count > 0 else 'failed',
            delivered_at=timezone.now() if sent_count > 0 else None,
        )
        return sent_count > 0
    except Exception as e:
        NotificationLog.objects.create(
            user_id=user_id,
            title=subject,
            body=body,
            data={**(data or {}), 'channel': 'email'},
            status='failed',
            error=str(e)
        )
        return False