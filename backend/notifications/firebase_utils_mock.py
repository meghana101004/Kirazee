"""
Mock Firebase service for development/testing
Logs notifications instead of sending them
"""
import logging

logger = logging.getLogger(__name__)

def init_firebase() -> None:
    """Mock Firebase initialization"""
    logger.info("Mock Firebase initialized (development mode)")

def send_push_notification(token: str, title: str, body: str, data: dict = None) -> str:
    """Mock send push notification - logs instead of sending"""
    mock_fcm_id = f"mock_fcm_{token[:10]}_{hash(title + body) % 10000}"
    
    logger.info(f"MOCK NOTIFICATION SENT:")
    logger.info(f"  Token: {token[:20]}...")
    logger.info(f"  Title: {title}")
    logger.info(f"  Body: {body}")
    logger.info(f"  Data: {data}")
    logger.info(f"  Mock FCM ID: {mock_fcm_id}")
    
    return mock_fcm_id
