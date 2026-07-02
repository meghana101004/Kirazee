"""
Business and Item Availability Services

This module implements the comprehensive availability logic for businesses and items.

AVAILABILITY MATRIX LOGIC:

Rule 4 (HIDE):        business.status=2 OR item.is_visible=0 → Hide completely
Rule 6 (TEMP_UNAVAIL): business.status=0 OR item.is_active=0  → Show but block orders
Rule 5 (OUT_OF_STOCK): stock <= 0 → Show but block orders
Rule 3 (SCHEDULE):     Business closed but stock>0 → Schedule order
Rule 2 (TIME_RESTRICT): Business open but item timing outside → Show only
Rule 1 (AVAILABLE):    Everything OK → Add to cart

UI_ACTION codes returned:
- ADD_TO_CART: Green button, can order now
- SHOW_ONLY: Greyed out, item visible but cannot order
- SCHEDULE_ORDER: Blue/Orange button, can schedule for later
- HIDE: Don't show item at all

DATABASE FIELD MAPPING:
- Business: status (0=off, 1=active, 2=hidden)
- R01 (Grocery): stock on variant, is_active, is_visible
- R02 (Restaurant): stock_qty on variant, is_active, status on item
- R08 (Fashion): stock_qty on variant, is_active, is_visible
"""

from datetime import datetime, time
from django.utils import timezone
from decimal import Decimal


def is_business_open(business, current_dt=None):
    """
    Check if business is currently open based on business_hours.
    
    Args:
        business: Business model instance
        current_dt: datetime object (defaults to current time)
    
    Returns:
        bool: True if business is open, False otherwise
    """
    if current_dt is None:
        current_dt = timezone.now()
    
    business_hours = business.business_hours
    if not business_hours:
        # No business hours defined - assume always open
        return True
    
    # Use abbreviated day name (mon, tue, wed, etc.) to match business_hours keys
    current_day = current_dt.strftime('%a').lower()[:3]  # mon, tue, wed, etc.
    current_time = current_dt.time()
    
    # DEBUG: Log timing check
    print(f"[DEBUG] is_business_open - business: {getattr(business, 'businessName', 'Unknown')}")
    print(f"[DEBUG] current_dt: {current_dt}, day: {current_day}, time: {current_time}")
    print(f"[DEBUG] business_hours type: {type(business_hours)}")
    
    # Handle different business_hours formats
    if isinstance(business_hours, dict):
        day_hours = business_hours.get(current_day)
        if not day_hours:
            return False
        
        # Handle format: [{"open": "09:00", "close": "18:00"}] - LIST of dicts
        if isinstance(day_hours, list):
            for time_slot in day_hours:
                if isinstance(time_slot, dict):
                    open_time = time_slot.get('open')
                    close_time = time_slot.get('close')
                    if open_time and close_time:
                        try:
                            open_t = _parse_time(open_time)
                            close_t = _parse_time(close_time)
                            # Check if current time falls within this time slot
                            if open_t <= current_time <= close_t:
                                return True
                        except (ValueError, TypeError):
                            continue
            return False  # No matching time slot found
        
        # Handle format: {"open": "09:00", "close": "22:00"} - single dict
        if isinstance(day_hours, dict):
            open_time = day_hours.get('open')
            close_time = day_hours.get('close')
            
            if not open_time or not close_time:
                return False
            
            try:
                open_t = _parse_time(open_time)
                close_t = _parse_time(close_time)
                return open_t <= current_time <= close_t
            except (ValueError, TypeError):
                return False
        
        # Handle format: "09:00 - 22:00" or "09:00-22:00"
        elif isinstance(day_hours, str):
            try:
                parts = day_hours.replace(' ', '').split('-')
                if len(parts) == 2:
                    open_t = _parse_time(parts[0])
                    close_t = _parse_time(parts[1])
                    return open_t <= current_time <= close_t
            except (ValueError, TypeError):
                return False
    
    # Handle list format: [{"day": "monday", "open": "09:00", "close": "22:00"}, ...]
    elif isinstance(business_hours, list):
        for day_entry in business_hours:
            if isinstance(day_entry, dict):
                if day_entry.get('day', '').lower() == current_day:
                    open_time = day_entry.get('open')
                    close_time = day_entry.get('close')
                    if open_time and close_time:
                        try:
                            open_t = _parse_time(open_time)
                            close_t = _parse_time(close_time)
                            return open_t <= current_time <= close_t
                        except (ValueError, TypeError):
                            return False
    
    return False


def _parse_time(time_str):
    """Parse time string to time object."""
    time_str = str(time_str).strip()
    
    # Handle HH:MM format
    if ':' in time_str:
        parts = time_str.split(':')
        hour = int(parts[0])
        minute = int(parts[1].split()[0])  # Handle "22:00 PM"
        return time(hour=hour, minute=minute)
    
    # Handle HHMM format
    if len(time_str) == 4:
        return time(hour=int(time_str[:2]), minute=int(time_str[2:]))
    
    raise ValueError(f"Invalid time format: {time_str}")


def is_item_available(item, current_dt=None):
    """
    Check if item is currently available based on item_timings.
    
    Args:
        item: Item model instance (MenuItems, GroceriesProducts, FashionProduct, etc.)
        current_dt: datetime object (defaults to current time)
    
    Returns:
        bool: True if item is available, False otherwise
    """
    if current_dt is None:
        current_dt = timezone.now()
    
    # Check if item has timing restrictions
    item_timings = getattr(item, 'item_timings', None) or getattr(item, 'timings', None)
    
    if not item_timings:
        # No timing restrictions - always available
        return True
    
    # Use abbreviated day name (mon, tue, wed, etc.) to match item_timings keys
    current_day = current_dt.strftime('%a').lower()[:3]  # mon, tue, wed, etc.
    current_time = current_dt.time()
    
    # Handle same formats as business_hours
    if isinstance(item_timings, dict):
        day_hours = item_timings.get(current_day)
        if not day_hours:
            return False
        
        if isinstance(day_hours, dict):
            open_time = day_hours.get('open')
            close_time = day_hours.get('close')
            if open_time and close_time:
                try:
                    open_t = _parse_time(open_time)
                    close_t = _parse_time(close_time)
                    return open_t <= current_time <= close_t
                except (ValueError, TypeError):
                    return True
        elif isinstance(day_hours, str):
            try:
                parts = day_hours.replace(' ', '').split('-')
                if len(parts) == 2:
                    open_t = _parse_time(parts[0])
                    close_t = _parse_time(parts[1])
                    return open_t <= current_time <= close_t
            except (ValueError, TypeError):
                return True
    
    elif isinstance(item_timings, list):
        for day_entry in item_timings:
            if isinstance(day_entry, dict):
                if day_entry.get('day', '').lower() == current_day:
                    open_time = day_entry.get('open')
                    close_time = day_entry.get('close')
                    if open_time and close_time:
                        try:
                            open_t = _parse_time(open_time)
                            close_t = _parse_time(close_time)
                            return open_t <= current_time <= close_t
                        except (ValueError, TypeError):
                            return True
    
    return True


def get_stock_message(stock):
    """
    Get stock message for display.
    
    Args:
        stock: Stock quantity (int or None)
    
    Returns:
        dict: {"stock_message": str or None, "stock_status": str}
    """
    if stock is None:
        return {"stock_message": None, "stock_status": "available"}
    
    try:
        stock = int(stock)
    except (ValueError, TypeError):
        return {"stock_message": None, "stock_status": "available"}
    
    if stock == 0:
        return {
            "stock_message": "Out of stock",
            "stock_status": "out_of_stock"
        }
    elif stock < 5:
        return {
            "stock_message": f"Only {stock} left",
            "stock_status": "low_stock"
        }
    else:
        return {"stock_message": None, "stock_status": "available"}


def get_item_availability_status(business, item, variant=None, business_type=None, current_dt=None):
    """
    Get comprehensive availability status for an item.
    
    This is the MAIN function that implements the complete availability matrix logic.
    
    Args:
        business: Business model instance
        item: Item model instance (product/base item)
        variant: Optional variant instance (for R01/R08 where stock is on variant)
        business_type: Optional business type code ('R01', 'R02', 'R08')
        current_dt: datetime object (defaults to current time)
    
    Returns:
        dict: {
            "ui_action": str,           # ADD_TO_CART | SHOW_ONLY | SCHEDULE_ORDER
            "can_add_to_cart": bool,
            "availability_status": str, # AVAILABLE | TEMPORARY_UNAVAILABLE | OUT_OF_STOCK | 
                                        # SCHEDULE_ONLY | NOT_IN_TIMING | HIDDEN
            "availability_message": str or None,
            "stock_message": str or None,
            "stock_status": str,        # available | low_stock | out_of_stock
            "is_business_open": bool,
            "is_visible": bool          # False means hide completely from API
        }
        OR None if business/item should be hidden
    """
    if current_dt is None:
        current_dt = timezone.now()
    
    # ---------------------------------------------------------
    # 1. DATA NORMALIZATION (Handle inconsistent DB fields)
    # ---------------------------------------------------------
    
    # Business status: 0=off, 1=active, 2=hidden
    b_status = int(getattr(business, 'status', 1))
    
    # Item-level flags (handle both boolean and int representations)
    item_status = getattr(item, 'status', 1)
    if isinstance(item_status, bool):
        item_status = 1 if item_status else 0
    item_status = int(item_status)
    
    # is_visible: 0 or False means hide completely
    is_visible = getattr(item, 'is_visible', 1)
    if isinstance(is_visible, bool):
        is_visible = 1 if is_visible else 0
    is_visible = int(is_visible)
    
    # is_active: 0 or False means temporarily disabled
    is_active = getattr(item, 'is_active', 1)
    if isinstance(is_active, bool):
        is_active = 1 if is_active else 0
    is_active = int(is_active)
    
    # ---------------------------------------------------------
    # RULE 4: HIDE COMPLETELY
    # ---------------------------------------------------------
    # Business status=2 (hidden) OR item is_visible=0
    if b_status == 2 or is_visible == 0:
        return None  # Do not return in API
    
    # ---------------------------------------------------------
    # RULE 6: TEMPORARY UNAVAILABLE (Owner turned off)
    # ---------------------------------------------------------
    # Business status=0 (turned off) OR item is_active=0 (disabled)
    if b_status == 0 or is_active == 0:
        return {
            "ui_action": "SHOW_ONLY",
            "can_add_to_cart": False,
            "availability_status": "TEMPORARY_UNAVAILABLE",
            "availability_message": "Temporarily unavailable",
            "stock_message": None,
            "stock_status": "available",
            "is_business_open": False,
            "is_visible": True
        }
    
    # ---------------------------------------------------------
    # STOCK CHECK (Rule 5: Out of Stock)
    # ---------------------------------------------------------
    # For grocery/fashion, check variant stock if variant provided
    # For restaurant, stock is usually on variant (stock_qty) or item may not have stock tracking
    target = variant if variant else item
    
    # Try different stock field names based on business type
    stock = None
    if business_type == 'R01':
        # Grocery uses 'stock' on variant
        stock = getattr(target, 'stock', None)
    elif business_type == 'R02':
        # Restaurant may not have numeric stock, uses is_active toggle
        stock = getattr(target, 'stock_qty', None)
    elif business_type == 'R08':
        # Fashion uses 'stock_qty' on variant
        stock = getattr(target, 'stock_qty', None)
    else:
        # Generic fallback - try both field names
        stock = getattr(target, 'stock', None)
        if stock is None:
            stock = getattr(target, 'stock_qty', None)
    
    # Default stock to 0 if None for R01/R08 (require stock tracking)
    # For R02, None stock means no tracking (assume available)
    if stock is None:
        if business_type in ['R01', 'R08']:
            stock = 0
        else:
            stock = 999  # Assume available for R02
    
    try:
        stock = int(stock)
    except (ValueError, TypeError):
        stock = 0
    
    stock_info = get_stock_message(stock)
    
    # Rule 5: Out of Stock
    if stock <= 0:
        return {
            "ui_action": "SHOW_ONLY",
            "can_add_to_cart": False,
            "availability_status": "OUT_OF_STOCK",
            "availability_message": "Out of stock",
            "stock_message": "Out of stock",
            "stock_status": "out_of_stock",
            "is_business_open": True,
            "is_visible": True
        }
    
    # ---------------------------------------------------------
    # TIMING CHECKS (Business vs Item)
    # ---------------------------------------------------------
    business_open = is_business_open(business, current_dt)
    
    # For R02 (Restaurant), check item-specific timings
    # For R01/R08, item timing is not typically used
    item_in_time = True
    if business_type == 'R02' or (business_type is None and hasattr(item, 'item_timings')):
        item_in_time = is_item_available(item, current_dt) if business_open else False
    
    # ---------------------------------------------------------
    # RULE 1: EVERYTHING OK → ADD TO CART
    # ---------------------------------------------------------
    if business_open and item_in_time:
        return {
            "ui_action": "ADD_TO_CART",
            "can_add_to_cart": True,
            "availability_status": "AVAILABLE",
            "availability_message": None,
            "stock_message": stock_info["stock_message"],
            "stock_status": stock_info["stock_status"],
            "is_business_open": True,
            "is_visible": True
        }
    
    # ---------------------------------------------------------
    # RULE 3: SCHEDULE ORDER (Business closed, item valid)
    # ---------------------------------------------------------
    if not business_open:
        return {
            "ui_action": "SCHEDULE_ORDER",
            "can_add_to_cart": True,  # True because it can be added for later
            "availability_status": "SCHEDULE_ONLY",
            "availability_message": "Store closed. Schedule for later.",
            "stock_message": stock_info["stock_message"],
            "stock_status": stock_info["stock_status"],
            "is_business_open": False,
            "is_visible": True
        }
    
    # ---------------------------------------------------------
    # RULE 2: SHOW BUT NO ADD (Item timing restriction)
    # ---------------------------------------------------------
    # Business open but item not in timing (e.g., Breakfast item during Dinner)
    if business_open and not item_in_time:
        return {
            "ui_action": "SHOW_ONLY",
            "can_add_to_cart": False,
            "availability_status": "NOT_IN_TIMING",
            "availability_message": "Available at specific times",
            "stock_message": stock_info["stock_message"],
            "stock_status": stock_info["stock_status"],
            "is_business_open": True,
            "is_visible": True
        }
    
    # Default fallback (should not reach here)
    return {
        "ui_action": "ADD_TO_CART",
        "can_add_to_cart": True,
        "availability_status": "AVAILABLE",
        "availability_message": None,
        "stock_message": stock_info["stock_message"],
        "stock_status": stock_info["stock_status"],
        "is_business_open": True,
        "is_visible": True
    }


def get_business_availability(business, current_dt=None):
    """
    Get availability status for a business (without item context).
    
    Args:
        business: Business model instance
        current_dt: datetime object (defaults to current time)
    
    Returns:
        dict: {
            "is_visible": bool,
            "can_order": bool,
            "availability_status": str,
            "availability_message": str or None,
            "is_business_open": bool
        }
    """
    if current_dt is None:
        current_dt = timezone.now()
    
    business_status = getattr(business, 'status', 1)
    
    # status=2 → Hidden
    if business_status == 2:
        return {
            "is_visible": False,
            "can_order": False,
            "availability_status": "hidden",
            "availability_message": None,
            "is_business_open": False
        }
    
    # status=0 → Owner turned off
    if business_status == 0:
        return {
            "is_visible": True,
            "can_order": False,
            "availability_status": "unavailable",
            "availability_message": "Currently unavailable",
            "is_business_open": False
        }
    
    # status=1 → Active
    business_open = is_business_open(business, current_dt)
    
    if business_open:
        return {
            "is_visible": True,
            "can_order": True,
            "availability_status": "open",
            "availability_message": None,
            "is_business_open": True
        }
    else:
        return {
            "is_visible": True,
            "can_order": False,
            "availability_status": "closed",
            "availability_message": "Schedule order available",
            "is_business_open": False
        }


def add_availability_to_item(item_dict, business, item_obj=None, variant_obj=None, business_type=None, current_dt=None):
    """
    Add availability fields to an item dictionary (for API response).
    
    Args:
        item_dict: dict - Item data dictionary to modify
        business: Business model instance
        item_obj: Optional item model instance (if different from dict source)
        variant_obj: Optional variant model instance (for R01/R08 stock checking)
        business_type: Optional business type code ('R01', 'R02', 'R08')
        current_dt: datetime object (defaults to current time)
    
    Returns:
        dict: Modified item_dict with availability fields added, or None if item should be hidden
    """
    if current_dt is None:
        current_dt = timezone.now()
    
    # Create a pseudo-item object from dict if no item_obj provided
    if item_obj is None:
        class PseudoItem:
            pass
        item_obj = PseudoItem()
        item_obj.status = item_dict.get('status', 1)
        item_obj.is_active = item_dict.get('is_active', True)
        item_obj.is_visible = item_dict.get('is_visible', 1)
        item_obj.stock = item_dict.get('stock')
        item_obj.stock_qty = item_dict.get('stock_qty')
        item_obj.item_timings = item_dict.get('item_timings')
    
    # Create pseudo-variant if variant data in dict but no variant_obj
    if variant_obj is None:
        variant_stock = item_dict.get('variant_stock') or item_dict.get('stock') or item_dict.get('stock_qty')
        if variant_stock is not None:
            class PseudoVariant:
                pass
            variant_obj = PseudoVariant()
            variant_obj.stock = variant_stock if 'R01' == business_type else None
            variant_obj.stock_qty = variant_stock if business_type in ['R02', 'R08'] else None
    
    availability = get_item_availability_status(business, item_obj, variant_obj, business_type, current_dt)
    
    if availability is None:
        # Item should be hidden
        return None
    
    # Add availability fields to item dict
    item_dict['ui_action'] = availability['ui_action']
    item_dict['can_add_to_cart'] = availability['can_add_to_cart']
    item_dict['availability_status'] = availability['availability_status']
    item_dict['availability_message'] = availability['availability_message']
    item_dict['stock_message'] = availability['stock_message']
    item_dict['stock_status'] = availability['stock_status']
    item_dict['is_business_open'] = availability['is_business_open']
    
    return item_dict
