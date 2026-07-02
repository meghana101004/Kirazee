import json
import os
from typing import Dict, Any, Optional

import firebase_admin
from firebase_admin import credentials, messaging
from django.conf import settings

_initialized = False


def init_firebase() -> None:
    global _initialized
    if _initialized:
        return
    if not getattr(settings, "FIREBASE_ENABLED", False):
        return
    cred_input = getattr(settings, "FIREBASE_CREDENTIALS_JSON", None)
    if not cred_input:
        raise RuntimeError("Firebase credentials missing: set FIREBASE_ENABLED=1 and FIREBASE_CREDENTIALS_JSON")
    # Accept a file path or raw JSON string
    if os.path.isfile(cred_input):
        cred = credentials.Certificate(cred_input)
    else:
        cred = credentials.Certificate(json.loads(cred_input))
    firebase_admin.initialize_app(cred)
    _initialized = True


def send_push_notification(token: str, title: str, body: str, data: Optional[Dict[str, Any]] = None, 
                         image_url: Optional[str] = None) -> str:
    """Send a notification to a specific device using Firebase Cloud Messaging (FCM).
    
    Args:
        token: FCM device token
        title: Notification title
        body: Notification body text
        data: Additional data payload
        image_url: URL of image to display in notification (for rich notifications)
    """
    init_firebase()
    if not token:
        raise ValueError("Missing FCM token")
    
    # Enhanced data payload with image information
    enhanced_data = data or {}
    if image_url:
        enhanced_data['image_url'] = image_url
        enhanced_data['media_type'] = 'image'
    
    # Create basic message with enhanced data
    # The frontend will handle rich media display based on data payload
    message = messaging.Message(
        token=token,
        notification=messaging.Notification(title=title, body=body),
        data=enhanced_data,
        # Basic Android configuration
        android=messaging.AndroidConfig(
            priority='high',
            ttl=3600  # 1 hour TTL
        ),
        # Basic iOS configuration  
        apns=messaging.APNSConfig(
            payload=messaging.APNSPayload(
                aps=messaging.Aps(
                    alert=messaging.ApsAlert(title=title, body=body),
                    badge=1,
                    sound='default',
                    mutable_content=True  # Allows rich content extensions
                )
            ),
            headers={'apns-priority': '10'}
        ),
        # Web configuration with image support
        webpush=messaging.WebpushConfig(
            notification=messaging.WebpushNotification(
                title=title,
                body=body,
                image=image_url if image_url else None,
                icon='/static/images/notification-icon.png',
                badge='/static/images/notification-badge.png'
            ),
            headers={'TTL': '3600'}
        )
    )
    
    return messaging.send(message)


def send_rich_notification(token: str, title: str, body: str, 
                         image_url: Optional[str] = None,
                         deep_link: Optional[str] = None,
                         data: Optional[Dict[str, Any]] = None) -> str:
    """Send a rich notification with image and deep link support like Swiggy/Zomato.
    
    Args:
        token: FCM device token
        title: Notification title
        body: Notification body text
        image_url: URL of image to display
        deep_link: Deep link URL for app navigation
        data: Additional data payload
    """
    # Add deep link and image to data payload
    enhanced_data = data or {}
    if deep_link:
        enhanced_data['deep_link'] = deep_link
    if image_url:
        enhanced_data['image_url'] = image_url
        enhanced_data['media_type'] = 'image'
    
    return send_push_notification(token, title, body, enhanced_data, image_url)
