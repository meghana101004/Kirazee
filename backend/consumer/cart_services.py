from django.db import connection
from datetime import datetime
import json
import hashlib

class CartService:
    """Service layer for cart operations across all business types."""
    
    @staticmethod
    def get_business_type(business_id):
        """Get the business type for a given business_id."""
        with connection.cursor() as cursor:
            cursor.execute("SELECT businessType FROM businesses WHERE business_id=%s", [business_id])
            row = cursor.fetchone()
            return row[0] if row else None

    @staticmethod
    def _has_column(table_name, column_name):
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT 1
                FROM information_schema.COLUMNS
                WHERE TABLE_SCHEMA = DATABASE()
                  AND TABLE_NAME = %s
                  AND COLUMN_NAME = %s
                LIMIT 1
                """,
                [table_name, column_name],
            )
            return cursor.fetchone() is not None

    @staticmethod
    def _normalize_customizations(customizations):
        if not customizations:
            return []
        if isinstance(customizations, str):
            try:
                return json.loads(customizations) or []
            except Exception:
                return []
        return customizations

    @staticmethod
    def _customizations_hash(customizations):
        normalized = CartService._normalize_customizations(customizations)
        try:
            payload = json.dumps(normalized, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        except Exception:
            payload = "[]"
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()
    
    @staticmethod
    def delete_user_cart(business_type, user_id):
        """Delete all cart items for a user based on business type."""
        with connection.cursor() as cursor:
            if business_type == "R02":
                cursor.execute("DELETE FROM menuCart WHERE user_id=%s", [user_id])
            elif business_type == "R01":
                cursor.execute("DELETE FROM Groceries_cart WHERE user_id=%s", [user_id])
            elif business_type == "R08":
                cursor.execute("DELETE FROM fashion_cart WHERE user_id=%s", [user_id])
            else:
                return 0
            return cursor.rowcount

    @staticmethod
    def get_cart_line_by_id(business_type, cart_id, user_id):
        """Fetch a single cart row (cart line) by its cart id."""
        table = {
            "R01": "Groceries_cart",
            "R02": "menuCart",
            "R08": "fashion_cart",
        }.get(business_type)
        if not table:
            raise ValueError(f"Unsupported business type: {business_type}")

        with connection.cursor() as cursor:
            cursor.execute(
                f"SELECT id, user_id, business_id, quantity FROM {table} WHERE id=%s AND user_id=%s",
                [cart_id, user_id],
            )
            return cursor.fetchone()

    @staticmethod
    def set_cart_line_quantity(business_type, cart_id, user_id, quantity):
        """Set quantity for a cart line by cart id. If quantity <= 0, deletes the row."""
        table = {
            "R01": "Groceries_cart",
            "R02": "menuCart",
            "R08": "fashion_cart",
        }.get(business_type)
        if not table:
            raise ValueError(f"Unsupported business type: {business_type}")

        qty = int(quantity)
        with connection.cursor() as cursor:
            if qty <= 0:
                cursor.execute(
                    f"DELETE FROM {table} WHERE id=%s AND user_id=%s",
                    [cart_id, user_id],
                )
                return "Item removed from cart", 0

            cursor.execute(
                f"UPDATE {table} SET quantity=%s, updated_at=NOW() WHERE id=%s AND user_id=%s",
                [qty, cart_id, user_id],
            )
            if cursor.rowcount == 0:
                return "Cart item not found", None
            return "Quantity updated", qty
    
    @staticmethod
    def delete_cart_item(business_type, item_id, user_id):
        """Delete cart item based on business type."""
        with connection.cursor() as cursor:
            if business_type == "R02":
                cursor.execute("DELETE FROM menuCart WHERE id=%s AND user_id=%s", [item_id, user_id])
            elif business_type == "R01":
                cursor.execute("DELETE FROM Groceries_cart WHERE id=%s AND user_id=%s", [item_id, user_id])
            elif business_type == "R08":
                cursor.execute("DELETE FROM fashion_cart WHERE id=%s AND user_id=%s", [item_id, user_id])
            else:
                return 0
            return cursor.rowcount
    
    @staticmethod
    def get_item_details(business_type, item_id, business_id, variant_id=None):
        """Get item details based on business type.

        Variant-aware behavior:
        - R01: if variant_id provided, fetch that variant; else treat item_id as product_id and pick a variant (stock-first).
        - R02: if variant_id provided, fetch from menu_item_variants; else treat item_id as menuItems.item_id.
        - R08: item_id is expected to be product_id (variant_id param also supported).
        """
        with connection.cursor() as cursor:
            if business_type == "R02":
                if variant_id is not None:
                    cursor.execute(
                        """
                        SELECT
                            mv.variant_id,
                            mi.item_name,
                            mi.description,
                            mv.selling_price,
                            mi.availability_timings,
                            mv.stock_qty,
                            mv.is_active,
                            mi.item_id
                        FROM menu_item_variants mv
                        JOIN menuItems mi ON mv.item_id = mi.item_id
                        WHERE mv.variant_id=%s AND mi.business_id=%s AND mv.is_active=1 AND mi.is_active=1 AND mi.status=1
                        """,
                        [variant_id, business_id],
                    )
                    return cursor.fetchone()

                cursor.execute(
                    """
                    SELECT item_id, item_name, description, selling_price, availability_timings
                    FROM menuItems 
                    WHERE item_id=%s AND business_id=%s AND is_active=1 AND status=1
                    """,
                    [item_id, business_id]
                )
            elif business_type == "R01":
                if variant_id is not None:
                    cursor.execute(
                        """
                        SELECT 
                            gpv.variant_id, gp.product_name, gp.description, gpv.selling_price, gpv.stock, gpv.is_active, gp.product_id
                        FROM Groceries_ProductVariants_1 gpv
                        JOIN Groceries_Products gp ON gpv.product_id = gp.product_id
                        WHERE gpv.variant_id=%s AND gp.business_id=%s AND gpv.is_active=1 AND gp.is_visible=1
                        """,
                        [variant_id, business_id],
                    )
                    return cursor.fetchone()

                # Groceries: treat item_id as product_id; pick a variant that has stock
                cursor.execute(
                    """
                    SELECT 
                        gpv.variant_id, gp.product_name, gp.description, gpv.selling_price, gpv.stock, gpv.is_active, gp.product_id
                    FROM Groceries_ProductVariants_1 gpv
                    JOIN Groceries_Products gp ON gpv.product_id = gp.product_id
                    WHERE gp.product_id=%s AND gp.business_id=%s AND gpv.is_active=1 AND gp.is_visible=1 AND gpv.stock > 0
                    ORDER BY gpv.variant_id ASC
                    LIMIT 1
                    """,
                    [item_id, business_id],
                )
                item = cursor.fetchone()
                
                # If no variant with stock, try any variant (might be out of stock but still valid)
                if not item:
                    cursor.execute(
                        """
                        SELECT 
                            gpv.variant_id, gp.product_name, gp.description, gpv.selling_price, gpv.stock, gpv.is_active, gp.product_id
                        FROM Groceries_ProductVariants_1 gpv
                        JOIN Groceries_Products gp ON gpv.product_id = gp.product_id
                        WHERE gp.product_id=%s AND gp.business_id=%s AND gpv.is_active=1 AND gp.is_visible=1
                        ORDER BY gpv.variant_id ASC
                        LIMIT 1
                        """,
                        [item_id, business_id],
                    )
                    item = cursor.fetchone()
                
                # If not found by product_id, try by variant_id
                if not item:
                    cursor.execute(
                        """
                        SELECT 
                            gpv.variant_id, gp.product_name, gp.description, gpv.selling_price, gpv.stock, gpv.is_active, gp.product_id
                        FROM Groceries_ProductVariants_1 gpv
                        JOIN Groceries_Products gp ON gpv.product_id = gp.product_id
                        WHERE gpv.variant_id=%s AND gp.business_id=%s AND gpv.is_active=1 AND gp.is_visible=1
                        """,
                        [item_id, business_id],
                    )
                    item = cursor.fetchone()
                
                return item
            elif business_type == "R08":
                if variant_id is None:
                    variant_id = item_id
                cursor.execute(
                    """
                    SELECT fpv.variant_id, fp.name, fp.description, fpv.selling_price, fpv.stock_qty
                    FROM fashion_product_variants fpv
                    JOIN fashion_products fp ON fpv.product_id = fp.product_id
                    WHERE fpv.variant_id=%s AND fp.business_id=%s AND fpv.is_active=1 AND fp.is_active=1
                    """,
                    [variant_id, business_id]
                )
            else:
                return None
            
            return cursor.fetchone()

    @staticmethod
    def upsert_cart(business_type, user_id, business_id, item_id, quantity, customizations=None, variant_id=None):
        """Insert/update a cart line.

        Variant-aware cart line key:
        - Prefer variant_id when available (R08 already).
        - If customizations_hash column exists, split lines by hash so (same variant + different customizations) become different rows.
        """
        customizations_obj = CartService._normalize_customizations(customizations)
        cust_json = json.dumps(customizations_obj) if customizations_obj is not None else None
        cust_hash = CartService._customizations_hash(customizations_obj)

        if business_type == "R01":
            table_name = "Groceries_cart"
            item_col_name = "product_id"
            variant_col_name = "variant_id"
        elif business_type == "R02":
            table_name = "menuCart"
            item_col_name = "menu_id"
            variant_col_name = "variant_id"
        elif business_type == "R08":
            table_name = "fashion_cart"
            item_col_name = "item_id"
            variant_col_name = "variant_id"
        else:
            raise ValueError(f"Unsupported business type: {business_type}")

        has_variant_col = (business_type == "R08") or CartService._has_column(table_name, variant_col_name)
        has_cust_hash_col = CartService._has_column(table_name, "customizations_hash")

        resolved_product_id = None
        resolved_menu_id = None

        # Resolve variant_id (and base item_id where required) when missing
        if business_type == "R08":
            if variant_id is None:
                # Backward compat: item_id is variant_id
                variant_id = item_id
                # Resolve product_id from variant_id
                details = CartService.get_item_details(business_type, item_id, business_id)
                if not details:
                    raise ValueError("Item not found")
                resolved_product_id = details[6]  # fashion_products.product_id
            else:
                # variant_id provided, assume item_id is product_id
                resolved_product_id = item_id
        elif has_variant_col and variant_id is None and business_type in ["R01", "R02"]:
            # Backward compatible: if client didn't send variant_id, pick from get_item_details
            details = CartService.get_item_details(business_type, item_id, business_id)
            if not details:
                raise ValueError("Item not found")
            variant_id = details[0]

        # For R01, Groceries_cart.product_id is FK'd to Groceries_Products.product_id.
        # When using variant_id-aware cart lines, we must still persist a valid product_id.
        if business_type == "R01":
            if variant_id is not None:
                details = CartService.get_item_details(business_type, item_id, business_id, variant_id=variant_id)
                if not details:
                    raise ValueError("Item not found")
                # details: (variant_id, product_name, description, selling_price, stock, is_active, product_id)
                resolved_product_id = details[6]
            else:
                # Legacy/compat: item_id is product_id
                resolved_product_id = item_id

        # For R02, when variant_id is used, resolve the base menu_id
        if business_type == "R02" and variant_id is not None:
            details = CartService.get_item_details(business_type, item_id, business_id, variant_id=variant_id)
            if not details:
                raise ValueError("Item not found")
            # details: (variant_id, item_name, description, selling_price, availability_timings, stock_qty, is_active, item_id)
            resolved_menu_id = details[7]

        with connection.cursor() as cursor:
            where_parts = ["user_id=%s", "business_id=%s"]
            where_vals = [user_id, business_id]

            if has_variant_col:
                where_parts.append(f"{variant_col_name}=%s")
                where_vals.append(variant_id)
            else:
                where_parts.append(f"{item_col_name}=%s")
                where_vals.append(item_id)

            if has_cust_hash_col:
                where_parts.append("customizations_hash=%s")
                where_vals.append(cust_hash)

            cursor.execute(
                f"SELECT id, quantity FROM {table_name} WHERE " + " AND ".join(where_parts),
                where_vals,
            )
            row = cursor.fetchone()

            if row:
                cart_id, existing_qty = row
                new_qty = existing_qty + quantity
                if has_cust_hash_col and cust_json is not None:
                    cursor.execute(
                        f"UPDATE {table_name} SET quantity=%s, customizations=%s, updated_at=NOW() WHERE id=%s",
                        [new_qty, cust_json, cart_id],
                    )
                elif cust_json is not None and CartService._has_column(table_name, "customizations"):
                    cursor.execute(
                        f"UPDATE {table_name} SET quantity=%s, customizations=%s, updated_at=NOW() WHERE id=%s",
                        [new_qty, cust_json, cart_id],
                    )
                else:
                    cursor.execute(
                        f"UPDATE {table_name} SET quantity=%s, updated_at=NOW() WHERE id=%s",
                        [new_qty, cart_id],
                    )
                return "Quantity updated", new_qty

            # insert
            insert_cols = ["user_id", "business_id", "quantity", "customizations", "added_at"]
            insert_vals = [user_id, business_id, quantity, cust_json, datetime.now()]

            if has_variant_col:
                # For R01/R02/R08 we must persist base item_id as well.
                if business_type == "R01":
                    insert_cols.insert(2, "product_id")
                    insert_vals.insert(2, resolved_product_id)
                    insert_cols.insert(3, variant_col_name)
                    insert_vals.insert(3, variant_id)
                elif business_type == "R02":
                    insert_cols.insert(2, "menu_id")
                    insert_vals.insert(2, resolved_menu_id)
                    insert_cols.insert(3, variant_col_name)
                    insert_vals.insert(3, variant_id)
                elif business_type == "R08":
                    insert_cols.insert(2, "item_id")
                    insert_vals.insert(2, resolved_product_id)
                    insert_cols.insert(3, variant_col_name)
                    insert_vals.insert(3, variant_id)
                else:
                    insert_cols.insert(2, variant_col_name)
                    insert_vals.insert(2, variant_id)
            else:
                insert_cols.insert(2, item_col_name)
                insert_vals.insert(2, item_id)

            if has_cust_hash_col:
                insert_cols.append("customizations_hash")
                insert_vals.append(cust_hash)

            cursor.execute(
                f"INSERT INTO {table_name} ({', '.join(insert_cols)}) VALUES ({', '.join(['%s'] * len(insert_vals))})",
                insert_vals,
            )
            return "Item added to cart", quantity
    
    @staticmethod
    def check_item_availability(business_type, availability_timings):
        """Check if item is available based on business type and availability data"""
        if business_type == "R02":
            # Restaurant: Check time-based availability
            if not availability_timings:
                return True
                
            try:
                if isinstance(availability_timings, str):
                    availability = json.loads(availability_timings or '{}')
                else:
                    availability = availability_timings or {}
                    
                today = datetime.now().strftime("%a").lower()[:3]
                current_time = datetime.now().strftime("%H:%M")
                
                available_today = availability.get(today, [])
                if not available_today:
                    return True  # If no timings set, assume available
                    
                for slot in available_today:
                    if isinstance(slot, dict) and "open" in slot and "close" in slot:
                        if slot["open"] <= current_time <= slot["close"]:
                            return True
                            
                return False
            except (json.JSONDecodeError, TypeError, KeyError):
                return True  # If parsing fails, assume available
                
        elif business_type == "R01":
            # Grocery: Check if in stock (availability_timings is stock count for R01)
            if availability_timings is None:
                return True  # If no stock info, assume available
            try:
                stock = int(availability_timings) if availability_timings else 0
                return stock > 0
            except (ValueError, TypeError):
                return True  # If stock parsing fails, assume available
                
        elif business_type == "R08":
            # Fashion: Check if in stock (availability_timings is stock count for R08)
            if availability_timings is None:
                return True  # If no stock info, assume available
            try:
                stock = int(availability_timings) if availability_timings else 0
                return stock > 0
            except (ValueError, TypeError):
                return True  # If stock parsing fails, assume available
                
        return True  # Default to available

    @staticmethod
    def get_cart_items(business_type, user_id):
        """Get cart items for a user based on business type.

        Variant-aware:
        - R01: if Groceries_cart.variant_id exists, returns/joins by variant_id to avoid duplicates.
        - R02: if menuCart.variant_id exists, returns/joins by variant_id and uses menu_item_variants price.
        - R08: already variant-based.
        """
        groceries_has_variant = CartService._has_column("Groceries_cart", "variant_id")
        menu_has_variant = CartService._has_column("menuCart", "variant_id")
        fashion_has_item = CartService._has_column("fashion_cart", "item_id")

        queries = {
            "R01": """
                SELECT c.id, {item_id_expr}, c.quantity, gp.product_name, gp.description,
                       gpv.selling_price, gp.main_image, c.business_id, b.businessName,
                       c.customizations, {variant_id_expr}
                FROM Groceries_cart c
                JOIN Groceries_Products gp ON c.product_id = gp.product_id
                JOIN Groceries_ProductVariants_1 gpv ON {variant_join_expr}
                JOIN businesses b ON c.business_id = b.business_id
                WHERE c.user_id = %s
            """,
            "R02": """
                SELECT c.id, {menu_item_id_expr}, c.quantity, m.item_name, m.description,
                       {menu_price_expr}, m.item_image, c.business_id, b.businessName,
                       c.customizations, {menu_variant_id_expr}
                FROM menuCart c
                {menu_variant_join}
                JOIN menuItems m ON {menu_item_join_expr}
                JOIN businesses b ON c.business_id = b.business_id
                WHERE c.user_id = %s
            """,
            "R08": """
                SELECT DISTINCT c.id, {fashion_item_id_expr}, c.quantity, fp.name, fp.description,
                       fpv.selling_price, fp.main_image, c.business_id, b.businessName,
                       c.customizations, c.variant_id
                FROM fashion_cart c
                {fashion_join}
                JOIN businesses b ON c.business_id = b.business_id
                WHERE c.user_id = %s
            """,
        }

        if groceries_has_variant:
            queries["R01"] = queries["R01"].format(
                item_id_expr="c.product_id",
                variant_join_expr="c.variant_id = gpv.variant_id",
                variant_id_expr="c.variant_id",
            )
        else:
            queries["R01"] = queries["R01"].format(
                item_id_expr="c.product_id",
                variant_join_expr="gp.product_id = gpv.product_id",
                variant_id_expr="gpv.variant_id",
            )

        if menu_has_variant:
            queries["R02"] = queries["R02"].format(
                menu_item_id_expr="m.item_id",
                menu_price_expr="mv.selling_price",
                menu_variant_join="JOIN menu_item_variants mv ON c.variant_id = mv.variant_id",
                menu_item_join_expr="mv.item_id = m.item_id",
                menu_variant_id_expr="c.variant_id",
            )
        else:
            queries["R02"] = queries["R02"].format(
                menu_item_id_expr="c.menu_id",
                menu_price_expr="m.selling_price",
                menu_variant_join="",
                menu_item_join_expr="c.menu_id = m.item_id",
                menu_variant_id_expr="c.menu_id",
            )

        if fashion_has_item:
            queries["R08"] = queries["R08"].format(
                fashion_item_id_expr="fp.product_id",
                fashion_join="JOIN fashion_products fp ON c.item_id = fp.product_id\n                JOIN fashion_product_variants fpv ON fp.product_id = fpv.product_id AND c.variant_id = fpv.variant_id",
            )
        else:
            queries["R08"] = queries["R08"].format(
                fashion_item_id_expr="c.variant_id",
                fashion_join="JOIN fashion_product_variants fpv ON c.variant_id = fpv.variant_id\n                JOIN fashion_products fp ON fp.product_id = fp.product_id",
            )

        if business_type not in queries:
            raise ValueError(f"Unsupported business type: {business_type}")

        with connection.cursor() as cursor:
            cursor.execute(queries[business_type], [user_id])
            return cursor.fetchall()
