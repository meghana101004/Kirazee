"""
Pricing service for grocery products and variants.
"""
from decimal import Decimal


def calculate_variant_price(variant):
    """
    Returns the effective / calculated price for a variant.

    Priority:
      1. If ``price_override`` is set (not None) → return price_override directly.
      2. Otherwise → base_price (from parent product) + attributes['premium'] (if any).

    Always returns a plain float (safe for JSON serialisation).
    """
    try:
        if variant.price_override is not None:
            effective_base = float(variant.price_override)
        else:
            # Fall back to product base_price + any premium in attributes JSON
            try:
                effective_base = float(variant.product.base_price) if (
                    variant.product and variant.product.base_price is not None
                ) else 0.0
            except Exception:
                effective_base = 0.0

            premium = 0.0
            try:
                attrs = variant.attributes or {}
                raw = attrs.get('premium', 0)
                premium = float(raw) if raw not in (None, '') else 0.0
            except Exception:
                premium = 0.0
            
            effective_base += premium

        # Add charges (variant level)
        try:
            charges = float(variant.charges) if variant.charges is not None else 0.0
        except Exception:
            charges = 0.0

        return round(effective_base + charges, 2)

    except Exception:
        return None
