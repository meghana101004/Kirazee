from decimal import Decimal
import json

from django.db import connection

__all__ = [
    "get_designs_map",
    "compute_customization_extra",
    "apply_customizations_pricing_r01",
]

def get_designs_map(product_id, business_id, design_ids):
    try:
        if not design_ids:
            return {}
        placeholders = ",".join(["%s"] * len(design_ids))
        with connection.cursor() as cursor:
            cursor.execute(
                f"""
                SELECT id, design_type, price_delta, max_chars, per_char_price, flat_price, base_price
                FROM Groceries_CustomDesigns
                WHERE is_active = 1 AND product_id = %s AND business_id = %s AND id IN ({placeholders})
                """,
                [product_id, business_id] + design_ids,
            )
            rows = cursor.fetchall()
        return {int(r[0]): r for r in rows}
    except Exception:
        return {}

def compute_customization_extra(selections, designs_map):
    extra = Decimal("0")
    if not isinstance(selections, list):
        return extra
    for s in selections:
        if not isinstance(s, dict) or s.get("design_id") is None:
            raise ValueError("Invalid customization payload")
        did = int(s.get("design_id"))
        if did not in designs_map:
            raise ValueError(f"Invalid design_id {did} for this product")
        r = designs_map[did]
        design_type = (r[1] or "").strip()
        price_delta = Decimal(str(r[2] or "0"))
        max_chars = r[3]
        per_char = Decimal(str(r[4])) if r[4] is not None else None
        flat_price = Decimal(str(r[5])) if r[5] is not None else None
        base_price = Decimal(str(r[6])) if r[6] is not None else None
        extra += price_delta
        if design_type == "text":
            text_val = str(s.get("text", "") or "")
            if isinstance(max_chars, int) and len(text_val) > max_chars:
                raise ValueError(f"Text exceeds max_chars ({max_chars}) for design {did}")
            if flat_price is not None:
                extra += flat_price
            if per_char is not None and text_val:
                extra += per_char * Decimal(str(len(text_val)))
        elif design_type in ("user_upload", "drawing"):
            if base_price is not None:
                extra += base_price
            if design_type == "user_upload" and not s.get("asset_url"):
                raise ValueError(f"asset_url required for design {did}")
    return extra

def apply_customizations_pricing_r01(business_id, product_id, selections, base_price):
    try:
        if selections is None or selections == []:
            return base_price

        if isinstance(selections, str):
            try:
                selections = json.loads(selections)
            except Exception:
                raise ValueError('Invalid customizations JSON')

        if isinstance(selections, dict):
            selections = [selections]

        if not isinstance(selections, list):
            raise ValueError('Invalid customization payload')
        design_ids = []
        for s in selections:
            try:
                if isinstance(s, dict) and s.get("design_id") is not None:
                    design_ids.append(int(s.get("design_id")))
            except Exception:
                continue
        designs_map = get_designs_map(product_id, business_id, design_ids)
        extra = compute_customization_extra(selections, designs_map)
        if extra > 0:
            return (base_price or Decimal("0")) + extra
        return base_price
    except ValueError as ve:
        raise ve
    except Exception:
        return base_price
