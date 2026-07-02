from typing import Optional

from .service import (
    notify_order_placed,
    notify_order_status,
    notify_otp_sent,
)


def on_payment_success(user_id: int, order_id: int) -> Optional[str]:
    try:
        return notify_order_placed(user_id=user_id, order_id=order_id)
    except Exception:
        return None


def on_order_status(user_id: int, order_id: int, status: str) -> Optional[str]:
    try:
        return notify_order_status(user_id=user_id, order_id=order_id, status=status)
    except Exception:
        return None


def on_otp_sent(user_id: int, order_id: int, otp_code: str) -> Optional[str]:
    try:
        return notify_otp_sent(user_id=user_id, order_id=order_id, otp_code=otp_code)
    except Exception:
        return None
