import os
import re
import json
import logging
from typing import List, Dict, Optional, Any

try:
    import requests  # Preferred HTTP client
except Exception:  # Fallback if requests is not installed
    requests = None
from django.conf import settings
from django.utils import timezone

logger = logging.getLogger(__name__)

INTERAKT_ENDPOINT = "https://api.interakt.ai/v1/public/message/"


def _get_setting(name: str, default: Optional[str] = None) -> Optional[str]:
    try:
        return getattr(settings, name, None) or os.getenv(name, default)
    except Exception:
        return os.getenv(name, default)


def normalize_phone(country_code: Optional[str], phone: Optional[str]) -> Dict[str, str]:
    """Normalize phone to Interakt format: countryCode with leading +, phoneNumber digits only."""
    cc = (country_code or "+91").strip()
    if not cc.startswith("+"):
        cc = "+" + re.sub(r"[^0-9]", "", cc)
    pn = re.sub(r"[^0-9]", "", phone or "")
    return {"countryCode": cc or "+91", "phoneNumber": pn}


def _sanitize_interakt_value(val: Any) -> str:
    """Interakt does not allow tabs/newlines or >2 consecutive spaces in body values.
    Normalize any value to a single-line, single-spaced string.
    """
    try:
        s = "" if val is None else str(val)
    except Exception:
        s = ""
    # Replace forbidden whitespace with spaces and collapse
    s = s.replace("\r", " ").replace("\n", " ").replace("\t", " ")
    s = re.sub(r"\s+", " ", s)
    return s.strip()


class InteraktClient:
    def __init__(self, api_key: Optional[str] = None, default_language: str = "en"):
        self.api_key = api_key or _get_setting("INTERAKT_API_KEY") or _get_setting("VITE_INTERAKT_API_KEY")
        # Fallback to provided dev key only if nothing configured
        if not self.api_key:
            self.api_key = "Y0xvRW9kNGZrNkRZQUpLbURjdDNUN3dKRUpfc1djUFZwekgtcjg0QWdRTTo="
            logger.warning("INTERAKT_API_KEY not configured. Using provided fallback API key. Please move this to settings for security.")
        self.default_language = _get_setting("INTERAKT_LANGUAGE_CODE", default_language) or default_language

    def _headers(self) -> Dict[str, str]:
        return {
            "Authorization": f"Basic {self.api_key}",
            "Content-Type": "application/json",
        }

    def send_template(
        self,
        *,
        country_code: str,
        phone_number: str,
        template_name: str,
        language_code: Optional[str] = None,
        body_values: Optional[List[str]] = None,
        header_values: Optional[List[str]] = None,
        button_values: Optional[Dict[str, List[str]]] = None,
        callback_data: Optional[str] = None,
        file_name: Optional[str] = None,
    ) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "countryCode": country_code,
            "phoneNumber": phone_number,
            "type": "Template",
            "template": {
                "name": template_name,
                "languageCode": (language_code or self.default_language),
            },
        }
        if callback_data:
            payload["callbackData"] = callback_data[:512]
        if header_values is not None and len(header_values) > 0:
            payload["template"]["headerValues"] = header_values
        if body_values is not None and len(body_values) > 0:
            payload["template"]["bodyValues"] = body_values
        if button_values is not None and len(button_values) > 0:
            payload["template"]["buttonValues"] = button_values
        if file_name:
            payload["template"]["fileName"] = file_name

        try:
            if requests is not None:
                resp = requests.post(INTERAKT_ENDPOINT, headers=self._headers(), data=json.dumps(payload), timeout=10)
                resp_json: Any
                try:
                    resp_json = resp.json()
                except Exception:
                    resp_json = {"text": resp.text}
                ok = resp.status_code in (200, 201) and bool(resp_json)
                if not ok:
                    logger.error(f"Interakt send failed: status={resp.status_code}, body={resp_json}")
                return {
                    "ok": ok and bool(resp_json.get("result", True)),
                    "status_code": resp.status_code,
                    "response": resp_json,
                    "payload": payload,
                }
            else:
                # Fallback using urllib
                import urllib.request
                req = urllib.request.Request(
                    INTERAKT_ENDPOINT,
                    data=json.dumps(payload).encode("utf-8"),
                    headers=self._headers(),
                    method="POST",
                )
                with urllib.request.urlopen(req, timeout=10) as r:  # nosec B310 - trusted endpoint
                    status_code = getattr(r, 'status', 200)
                    text = r.read().decode("utf-8")
                try:
                    resp_json = json.loads(text)
                except Exception:
                    resp_json = {"text": text}
                ok = status_code in (200, 201) and bool(resp_json)
                if not ok:
                    logger.error(f"Interakt send failed: status={status_code}, body={resp_json}")
                return {
                    "ok": ok and bool(resp_json.get("result", True)),
                    "status_code": status_code,
                    "response": resp_json,
                    "payload": payload,
                }
        except Exception as e:
            logger.error(f"Error calling Interakt: {e}")
            return {"ok": False, "error": str(e), "payload": payload}


# Convenience high-level helpers bound to project models

def _get_user_contact_from_order(order) -> Dict[str, Any]:
    """Get contact info from order using robust raw SQL lookup.
    
    Args:
        order: The order object with order_id
        
    Returns:
        Dict with countryCode and phoneNumber (may be empty)
    """
    default = {"countryCode": "+91", "phoneNumber": ""}
    try:
        order_id = getattr(order, 'order_id', None)
        if not order_id:
            logger.warning("Order has no order_id")
            return default
            
        # Use raw SQL to get customer contact (same approach as in views)
        from django.db import connection
        with connection.cursor() as cursor:
            cursor.execute("""
                SELECT 
                    r.mobileNumber,
                    r.countryCode
                FROM Groceries_orders go
                LEFT JOIN registrations r ON go.user_id = r.user_id
                WHERE go.order_id = %s
                LIMIT 1
            """, [order_id])
            
            result = cursor.fetchone()
            
            if result:
                mobile_number, country_code = result
                
                if mobile_number:
                    processed_country_code = country_code or '+91'
                    if processed_country_code and not str(processed_country_code).startswith('+'):
                        processed_country_code = f"+{processed_country_code}"
                    
                    contact = normalize_phone(processed_country_code, str(mobile_number))
                    logger.info(f"[_get_user_contact_from_order] Found contact for order {order_id}: {contact}")
                    return contact
                else:
                    logger.warning(f"[_get_user_contact_from_order] No mobile number found for order {order_id}")
            else:
                logger.warning(f"[_get_user_contact_from_order] No customer data found for order {order_id}")
            
        return default
    except Exception as e:
        logger.error(f"[_get_user_contact_from_order] Error getting contact for order {getattr(order, 'order_id', '?')}: {e}")
        return default


def _business_name(order) -> str:
    try:
        return getattr(order.business, "business_name", "Your Store")
    except Exception:
        return "Your Store"


def send_order_summary_message(
    order, 
    override_contact: Optional[Dict[str, str]] = None,
    override_customer_name: Optional[str] = None,
    override_layout_mode: Optional[str] = None,
    override_max_items: Optional[int] = None,
) -> Dict[str, Any]:
    contact = _get_user_contact_from_order(order)
    # If override contact is provided, prefer it when primary contact missing or to force a specific destination
    if override_contact and override_contact.get("phoneNumber"):
        # Normalize override
        oc = normalize_phone(override_contact.get("countryCode"), override_contact.get("phoneNumber"))
        contact = oc
    if not contact.get("phoneNumber"):
        return {"ok": False, "error": "Missing phone number"}

    # Best-effort body values (must match your Interakt template variables order)
    items_count = 0
    try:
        items_count = order.groceriesorderitems_set.count()
    except Exception:
        pass

    # Prepare variables as expected by the Interakt template in this order:
    # [customer_name, order_id, final_amount, order_type_text, address_or_pickup, estimated_time_text]
    try:
        customer_name = (override_customer_name or "").strip() if override_customer_name else ""
        if not customer_name:
            customer_name = f"{getattr(order.user, 'firstName', '')} {getattr(order.user, 'lastName', '')}".strip() or "Customer"
    except Exception:
        customer_name = "Customer"

    # Order type in human-friendly text
    try:
        ot = (order.order_type or "").strip().lower()
    except Exception:
        ot = ""
    order_type_text = "Delivery" if ot == "delivery" else ("Pickup" if ot == "pickup" else (order.order_type or "Order"))

    # Address or pickup location text
    try:
        if ot == 'delivery':
            address_text = (getattr(order, 'delivery_address', '') or '').strip() or 'Delivery'
        else:
            # Fallback to business name as pickup location
            address_text = (getattr(order.business, 'business_name', '') or 'Store Pickup').strip()
    except Exception:
        address_text = 'Store Pickup'

    # Estimated time text from delivery_time or pickup_time
    try:
        dt = getattr(order, 'delivery_time', None) if ot == 'delivery' else getattr(order, 'pickup_time', None)
        if dt:
            # Format nicely; fallback to str if no strftime
            try:
                estimated_time_text = dt.strftime('%b %d, %I:%M %p')
            except Exception:
                estimated_time_text = str(dt)
        else:
            estimated_time_text = 'ASAP'
    except Exception:
        estimated_time_text = 'ASAP'

    # Decide layout: 'compact' (single variable with items) or 'list' (each item as its own variable)
    layout_mode = (override_layout_mode or _get_setting("INTERAKT_SUMMARY_LAYOUT", "compact") or "compact").strip().lower()
    max_items = 3
    try:
        max_raw = override_max_items if override_max_items is not None else _get_setting("INTERAKT_SUMMARY_MAX_ITEMS", "3")
        max_items = int(max_raw or 3)
        if max_items < 1:
            max_items = 1
        if max_items > 10:
            max_items = 10
    except Exception:
        max_items = 3

    # Choose appropriate template name for the selected layout
    list_template_name = _get_setting("INTERAKT_TEMPLATE_ORDER_SUMMARY_LIST")
    default_template_name = _get_setting("INTERAKT_TEMPLATE_ORDER_SUMMARY", "order_summary_confirmation") or "order_summary_confirmation"
    if layout_mode == 'list' and not list_template_name:
        # Fallback to compact if list template not configured to avoid placeholder mismatch errors
        layout_mode = 'compact'

    try:
        items_qs = None
        try:
            items_qs = order.groceriesorderitems_set.select_related('product').all()
        except Exception:
            items_qs = order.groceriesorderitems_set.all()

        def _fmt_item(it):
            try:
                name = getattr(it.product, 'product_name', 'Item')
            except Exception:
                name = 'Item'
            qty = getattr(it, 'quantity', 1) or 1
            line_total = getattr(it, 'total_price', None)
            if not line_total:
                try:
                    unit_price = getattr(it, 'unit_price', 0)
                    line_total = (unit_price or 0) * qty
                except Exception:
                    line_total = ''
            return f"• {name} x{qty} - ₹{line_total}"

        if layout_mode == 'list':
            # Build fixed number of item lines = max_items.
            # If there are more than max_items items, use last slot as '+N more'. If fewer, pad with '-'.
            all_lines = [_fmt_item(it) for it in items_qs]
            if len(all_lines) > max_items:
                # Keep max_items-1 real items, last slot shows '+N more'
                visible = all_lines[:max_items - 1]
                remaining = len(all_lines) - (max_items - 1)
                visible.append(f"+{remaining} more item(s)")
                lines = visible
            else:
                lines = all_lines[:max_items]
            while len(lines) < max_items:
                lines.append("-")
            total_line = f"Total: ₹{getattr(order, 'final_amount', '')}"
            # Build body values for list template: [name, order_id, item1..itemN, total, order_type, address, eta]
            body_values = [customer_name, str(order.order_id)] + lines + [total_line, order_type_text, address_text, estimated_time_text]
        else:
            # Compact: single variable with items joined by ' | '
            items_lines = [_fmt_item(it) for it in items_qs]
            items_lines.append(f"Total: ₹{getattr(order, 'final_amount', '')}")
            items_block = " | ".join(items_lines)
            body_values = [
                customer_name,
                str(order.order_id),
                items_block,
                order_type_text,
                address_text,
                estimated_time_text,
            ]
    except Exception:
        # Fallback: compact with only total
        body_values = [
            customer_name,
            str(order.order_id),
            f"Total: ₹{getattr(order, 'final_amount', '')}",
            order_type_text,
            address_text,
            estimated_time_text,
        ]

    # Sanitize all values to comply with Interakt restrictions (no newlines/tabs/multi-spaces)
    body_values = [_sanitize_interakt_value(v) for v in body_values]

    # Sanitize body values
    body_values = [_sanitize_interakt_value(v) for v in body_values]
    client = InteraktClient()
    # Resolve template based on final layout_mode
    template_name = list_template_name if layout_mode == 'list' and list_template_name else default_template_name
    result = client.send_template(
        country_code=contact["countryCode"],
        phone_number=contact["phoneNumber"],
        template_name=template_name,
        body_values=body_values,
        callback_data=f"order_id={order.order_id}",
    )
    return result


def send_delivery_otp_message(
    delivery_detail, 
    override_contact: Optional[Dict[str, str]] = None,
    template_name_override: Optional[str] = None,
    language_override: Optional[str] = None,
    body_mode_override: Optional[str] = None,
    button_value_override: Optional[str] = None
) -> Dict[str, Any]:
    """Send delivery OTP via WhatsApp, with fallback to partner phone if customer phone is missing.
    
    Args:
        delivery_detail: GroceryDeliverDetails instance with order and partner info
        override_contact: Optional dict with 'phoneNumber' and 'countryCode' to force a specific recipient
        template_name_override: Optional template name to use instead of the default
        language_override: Optional language code to use instead of the default
        
    Returns:
        Dict with 'ok' status and details of the send attempt
    """
    # Re-enabled: send delivery OTP over WhatsApp when partner accepts order
    logger.info("[send_delivery_otp_message] Enabled - sending delivery OTP via WhatsApp")
    client = InteraktClient()
    order = delivery_detail.order
    order_id = getattr(order, 'order_id', 'unknown')
    otp = delivery_detail.delivery_otp or getattr(delivery_detail, "generate_otp", lambda: None)() or ""
    
    # Default template and language - configurable via settings, with sensible defaults
    template_name = template_name_override or _get_setting("INTERAKT_TEMPLATE_DELIVERY_OTP_NAME", "delivery_otp_customer")
    language_code = (
        language_override
        or _get_setting("INTERAKT_LANGUAGE_CODE", client.default_language)
        or client.default_language
    )
    
    # Fallback template names and languages to try
    # Include valid WhatsApp language codes for regional variants
    template_fallbacks = [
        ("delivery_otp_customer", "en"),
        ("delivery_otp_customer", "en_US"),
        ("delivery_otp_customer", "en_GB"),
        ("delivery_otp_customer", "hi"),
        ("delivery_otp", "en"),
        ("otp_delivery", "en"),
        ("delivery_notification", "en")
    ]
    
    # Log initial debug info
    logger.info(f"[send_delivery_otp_message] Starting for order {order_id}, OTP: {otp}, template: {template_name}")
    
    # Try to get customer contact first
    contact = None
    contact_source = "none"
    
    # 1. Use override contact if provided (for testing/fallback)
    if override_contact and override_contact.get("phoneNumber"):
        contact = normalize_phone(
            override_contact.get("countryCode"), 
            override_contact.get("phoneNumber")
        )
        contact_source = "override"
        logger.info(f"[send_delivery_otp_message] Using override contact: {contact}")
    
    # 2. Try customer's phone from order user
    if not contact or not contact.get("phoneNumber"):
        contact = _get_user_contact_from_order(order)
        contact_source = "customer"
        if contact and contact.get("phoneNumber"):
            logger.info(f"[send_delivery_otp_message] Using customer contact: {contact}")
        else:
            logger.warning(f"[send_delivery_otp_message] No valid customer contact found for order {order_id}")
    
    # 3. Fallback to delivery partner's phone if customer phone is missing
    if (not contact or not contact.get("phoneNumber")) and hasattr(delivery_detail, 'partner'):
        try:
            partner = delivery_detail.partner
            if hasattr(partner, 'user') and hasattr(partner.user, 'mobileNumber'):
                contact = normalize_phone(
                    getattr(partner.user, 'countryCode', '+91'),
                    partner.user.mobileNumber
                )
                contact_source = "partner"
                logger.warning(f"[send_delivery_otp_message] Falling back to partner contact: {contact}")
        except Exception as e:
            logger.error(f"[send_delivery_otp_message] Error getting partner contact: {e}")
    
    # Prepare the message content
    business_name = _business_name(order)
    
    # Log the attempt
    logger.info(f"[send_delivery_otp_message] Attempting to send OTP {otp} for order {order_id} to {contact} via {contact_source}")
    
    # Prepare the response template
    response_template = {
        'ok': False,
        'status': 'pending',
        'message': 'Sending OTP',
        'phone': contact.get('phoneNumber') if contact else None,
        'country_code': contact.get('countryCode') if contact else None,
        'order_id': order_id,
        'template_used': template_name,
        'language_used': language_code,
        'contact_source': contact_source
    }
    
    # If no contact info, return early
    if not contact or not contact.get('phoneNumber'):
        error_msg = f"[send_delivery_otp_message] Cannot send OTP - no valid phone number found (tried: {contact_source})"
        logger.error(error_msg)
        return {"ok": False, "error": error_msg, "tried_source": contact_source}
    
    logger.info(f"[send_delivery_otp_message] Sending to {contact_source} contact: {contact}")

    # Decide body payload format based on override/configuration
    # Modes: 'otp_only' (default) or 'full' (order_id, otp, business_name, customer_name)
    body_mode = ((body_mode_override or _get_setting("INTERAKT_TEMPLATE_DELIVERY_OTP_BODY_MODE", None) or "otp_only").strip().lower())

    if body_mode == "full":
        # Compute customer_name only when needed
        customer_name = "Customer"
        try:
            # Prefer attached user on order
            user_obj = getattr(order, 'user', None)
            if user_obj:
                fn = getattr(user_obj, 'firstName', '') or ''
                ln = getattr(user_obj, 'lastName', '') or ''
                full = f"{fn} {ln}".strip()
                if full:
                    customer_name = full
            else:
                # Robust fallback via raw SQL
                from django.db import connection
                with connection.cursor() as cursor:
                    cursor.execute(
                        """
                            SELECT r.firstName, r.lastName
                            FROM Groceries_orders go
                            LEFT JOIN registrations r ON go.user_id = r.user_id
                            WHERE go.order_id = %s
                            LIMIT 1
                        """,
                        [order.order_id],
                    )
                    row = cursor.fetchone()
                    if row:
                        fn, ln = row
                        full = f"{(fn or '').strip()} {(ln or '').strip()}".strip()
                        if full:
                            customer_name = full
        except Exception as _name_err:
            logger.warning(f"[send_delivery_otp_message] Could not resolve customer name for order {order_id}: {_name_err}")

        body_values = [
            str(order.order_id),
            str(otp),
            _business_name(order),
            customer_name,
        ]
    else:
        # otp_only mode
        customer_name = None  # not used
        body_values = [str(otp)]

    # Log where we're sending (masked) for debugging
    try:
        masked_tail = (contact.get("phoneNumber", "")[-4:] if contact and contact.get("phoneNumber") else "")
        country_code = contact.get('countryCode', '+91')
        phone_number = contact.get("phoneNumber", "")
        
        # Log the exact values being sent to Interakt
        logger.info(f"[Interakt] Sending {template_name} for order {order.order_id}")
        logger.info(f"[Interakt] To: {country_code}****{masked_tail} (full: {country_code}{phone_number})")
        logger.info(f"[Interakt] Template: {template_name} | Language: {language_code} | Mode: {body_mode}")
        if len(body_values) == 1:
            logger.info(f"[Interakt] Body values: otp={otp}")
        else:
            logger.info(
                f"[Interakt] Body values: order_id={order.order_id}, otp={otp}, business_name={_business_name(order)}, customer_name={customer_name}"
            )
    except Exception as e:
        logger.error(f"[Interakt] Error in logging contact info: {str(e)}")

    client = InteraktClient()
    
    # Prepare optional button values if provided (button index '0')
    provided_button_values = None
    if button_value_override is not None and str(button_value_override).strip() != "":
        provided_button_values = {"0": [str(button_value_override)]}

    # Try the primary template first
    logger.info(f"[Interakt] Attempting primary template: {template_name} with language: {language_code}")
    result = client.send_template(
        country_code=contact["countryCode"],
        phone_number=contact["phoneNumber"],
        template_name=template_name,
        body_values=body_values,
        button_values=provided_button_values,
        callback_data=f"order_id={order.order_id}",
        language_code=language_code
    )
    # If the template expects button variables, retry once with OTP for button index 0
    try:
        resp_msg = str(result.get("response", {}).get("message", "")).lower()
    except Exception:
        resp_msg = str(result)
    if (not result.get("ok", False)) and ("button" in resp_msg) and ("expected number of values" in resp_msg):
        logger.info("[Interakt] Retrying primary send with buttonValues[0]=OTP due to missing button variable")
        retry_result = client.send_template(
            country_code=contact["countryCode"],
            phone_number=contact["phoneNumber"],
            template_name=template_name,
            body_values=body_values,
            button_values={"0": [str(otp)]},
            callback_data=f"order_id={order.order_id}",
            language_code=language_code
        )
        if retry_result.get("ok", False):
            return retry_result
        else:
            result = retry_result
    
    # If primary template fails, try fallbacks
    if not result.get("ok", False) and "template" in str(result.get("response", {})).lower():
        logger.warning(f"[Interakt] Primary template '{template_name}' failed, trying fallbacks...")
        
        for fallback_template, fallback_lang in template_fallbacks:
            if fallback_template == template_name and fallback_lang == language_code:
                continue  # Skip the one we already tried
                
            logger.info(f"[Interakt] Trying fallback template: {fallback_template} with language: {fallback_lang}")
            
            try:
                fallback_result = client.send_template(
                    country_code=contact["countryCode"],
                    phone_number=contact["phoneNumber"],
                    template_name=fallback_template,
                    body_values=body_values,
                    button_values=provided_button_values,
                    callback_data=f"order_id={order.order_id}",
                    language_code=fallback_lang
                )
                
                if fallback_result.get("ok", False):
                    logger.info(f"[Interakt] Successfully sent with fallback template: {fallback_template}")
                    return fallback_result
                else:
                    # If missing button values, retry once with OTP for button index 0
                    try:
                        fb_msg = str(fallback_result.get("response", {}).get("message", "")).lower()
                    except Exception:
                        fb_msg = str(fallback_result)
                    if ("button" in fb_msg) and ("expected number of values" in fb_msg):
                        logger.info(f"[Interakt] Retrying fallback '{fallback_template}' with buttonValues[0]=OTP")
                        retry_fb = client.send_template(
                            country_code=contact["countryCode"],
                            phone_number=contact["phoneNumber"],
                            template_name=fallback_template,
                            body_values=body_values,
                            button_values={"0": [str(otp)]},
                            callback_data=f"order_id={order.order_id}",
                            language_code=fallback_lang
                        )
                        if retry_fb.get("ok", False):
                            logger.info(f"[Interakt] Successfully sent with fallback (button retry): {fallback_template}")
                            return retry_fb
                        else:
                            fallback_result = retry_fb
                    logger.warning(f"[Interakt] Fallback template '{fallback_template}' also failed: {fallback_result}")
                    
            except Exception as e:
                logger.error(f"[Interakt] Error trying fallback template '{fallback_template}': {e}")
        
        logger.error(f"[Interakt] All template fallbacks failed for order {order_id}")
    
    return result


def send_out_for_delivery_message(delivery_detail) -> Dict[str, Any]:
    order = delivery_detail.order
    contact = _get_user_contact_from_order(order)
    if not contact.get("phoneNumber"):
        return {"ok": False, "error": "Missing phone number"}

    partner_name = None
    try:
        partner_name = f"{delivery_detail.partner.user.firstName} {delivery_detail.partner.user.lastName}".strip()
    except Exception:
        partner_name = "Delivery Partner"

    body_values = [
        str(order.order_id),
        partner_name,
        _business_name(order),
    ]

    client = InteraktClient()
    result = client.send_template(
        country_code=contact["countryCode"],
        phone_number=contact["phoneNumber"],
        template_name="out_for_delivery_notification",
        body_values=body_values,
        callback_data=f"order_id={order.order_id}",
    )
    return result


def send_pickup_ready_message(order) -> Dict[str, Any]:
    contact = _get_user_contact_from_order(order)
    if not contact.get("phoneNumber"):
        return {"ok": False, "error": "Missing phone number"}

    pickup_time = None
    try:
        if order.pickup_time:
            pickup_time = timezone.localtime(order.pickup_time).strftime("%d %b, %I:%M %p")
    except Exception:
        pickup_time = None

    body_values = [
        str(order.order_id),
        _business_name(order),
        pickup_time or "ASAP",
    ]

    client = InteraktClient()
    result = client.send_template(
        country_code=contact["countryCode"],
        phone_number=contact["phoneNumber"],
        template_name="pickup_ready_notification",
        body_values=body_values,
        callback_data=f"order_id={order.order_id}",
    )
    return result


def send_pickup_otp_message(order, otp: str) -> Dict[str, Any]:
    contact = _get_user_contact_from_order(order)
    if not contact.get("phoneNumber"):
        return {"ok": False, "error": "Missing phone number"}

    body_values = [
        str(order.order_id),
        str(otp),
        _business_name(order),
    ]

    client = InteraktClient()
    result = client.send_template(
        country_code=contact["countryCode"],
        phone_number=contact["phoneNumber"],
        template_name="pickup_otp_for_collection",
        body_values=body_values,
        callback_data=f"order_id={order.order_id}",
    )
    return result
