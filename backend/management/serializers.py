import json
import logging
import bcrypt
import secrets
from datetime import datetime, timedelta
from decimal import Decimal
from django.db import transaction, connection, models
from rest_framework import serializers
from django.utils import timezone
from django.contrib.auth.hashers import check_password
from kirazee_app.utils import generate_otp as app_generate_otp, send_otp_dual_channel

logger = logging.getLogger(__name__)

from .models import (
    Suppliers,
    Purchases,
    Purchase_Items,
    Inventory,
    Inventory_Log,
    Purchase_Log,
    Expenses,
    Expenses_Log,
    Counter_Sales_Details,
    BusinessStaff,
    SupplierBankDetails,
    BusinessTaxInvoice,
    RoleBasedNavItems,
    StaffLoginLogs,
    NavDisplayItem,
    BusinessFeaturePurchase,
    PurchaseRequisition,
    PurchaseRequisitionLog,
)
from kirazee_app.models import Business, Registration
from business.models import productItems, FashionProduct, FashionProductVariant
from consumer.gro_models import GroceriesProductVariants


class SuppliersSerializer(serializers.ModelSerializer):
    business_id = serializers.SlugRelatedField(
        slug_field='business_id', 
        queryset=Business.objects.all(),
        required=True
    )
    bank_details = serializers.SerializerMethodField(read_only=True)
    
    class Meta:
        model = Suppliers
        fields = [
            'supplier_id', 'business_id', 'supplier_code', 'supplier_name',
            'contact_person', 'email', 'phone', 'address', 'city', 'state',
            'country', 'postal_code', 'product_supplied', 'payment_terms',
            'bank_details_id', 'gst_number', 'tax_percentage', 'status',
            'notes', 'created_at', 'updated_at', 'bank_details'
        ]
        read_only_fields = ['supplier_id', 'created_at', 'updated_at']
    
    def validate_email(self, value):
        """Validate email format if provided"""
        if value and '@' not in value:
            raise serializers.ValidationError("Enter a valid email address.")
        return value
    
    def validate_tax_percentage(self, value):
        """Validate tax percentage is within reasonable range"""
        if value is not None and (value < 0 or value > 100):
            raise serializers.ValidationError("Tax percentage must be between 0 and 100.")
        return value
    
    def validate_status(self, value):
        """Validate status is one of the allowed choices"""
        valid_statuses = ['Active', 'Inactive', 'Blacklisted']
        if value not in valid_statuses:
            raise serializers.ValidationError(f"Status must be one of: {', '.join(valid_statuses)}")
        return value

    def get_bank_details(self, obj):
        request = self.context.get('request') if hasattr(self, 'context') else None
        include_inactive = False
        if request is not None:
            try:
                include_inactive = str(request.query_params.get('include_inactive_bank_details', '')).lower() in ('1', 'true', 'yes')
            except Exception:
                include_inactive = str(request.GET.get('include_inactive_bank_details', '')).lower() in ('1', 'true', 'yes')

        accounts = SupplierBankDetails.objects.filter(supplier_id=obj)
        if not include_inactive:
            accounts = accounts.filter(status__iexact='Active')
        accounts = accounts.order_by('-is_primary', 'bank_details_id')
        return [
            {
                'bank_details_id': acc.bank_details_id,
                'business_id': acc.business_id.business_id if acc.business_id_id else None,
                'bank_name': acc.bank_name,
                'account_holder_name': acc.account_holder_name,
                'account_number': acc.account_number,
                'ifsc_code': acc.ifsc_code,
                'branch_name': acc.branch_name,
                'upi_id': acc.upi_id,
                'is_primary': acc.is_primary,
                'status': acc.status,
                'created_at': acc.created_at,
                'updated_at': acc.updated_at,
            }
            for acc in accounts
        ]


class SupplierBankDetailsSerializer(serializers.ModelSerializer):
    business_id = serializers.SlugRelatedField(
        slug_field='business_id', queryset=Business.objects.all()
    )

    class Meta:
        model = SupplierBankDetails
        fields = [
            'bank_details_id', 'supplier_id', 'business_id', 'bank_name', 'account_holder_name',
            'account_number', 'ifsc_code', 'branch_name', 'upi_id', 'is_primary', 'status',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['bank_details_id', 'supplier_id', 'created_at', 'updated_at']


class PurchaseItemSerializer(serializers.ModelSerializer):
    user_id = serializers.PrimaryKeyRelatedField(
        queryset=Registration.objects.all()
    )
    business_id = serializers.SlugRelatedField(
        slug_field='business_id', queryset=Business.objects.all()
    )
    purchase_id = serializers.PrimaryKeyRelatedField(queryset=Purchases.objects.all(), required=False)
    
    class Meta:
        model = Purchase_Items
        fields = [
            'purchase_item_id', 'purchase_id', 'business_id', 'user_id', 'sku',
            'reference_table', 'reference_id', 'item_name', 'unit', 'mfg_date',
            'exp_date', 'quantity', 'cost_price', 'selling_price', 'category',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['purchase_item_id', 'created_at', 'updated_at']


class PurchaseSerializer(serializers.ModelSerializer):
    items = PurchaseItemSerializer(many=True, required=False)
    user_id = serializers.SlugRelatedField(
        slug_field='user_id', queryset=Registration.objects.all()
    )
    business_id = serializers.SlugRelatedField(
        slug_field='business_id', queryset=Business.objects.all()
    )
    supplier_id = serializers.PrimaryKeyRelatedField(
        queryset=Suppliers.objects.all(), 
        required=False, 
        allow_null=True
    )
    supplier_name = serializers.SerializerMethodField(read_only=True)
    supplier_details = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = Purchases
        fields = '__all__'
        read_only_fields = ['purchase_id', 'created_at', 'updated_at', 'supplier_name', 'supplier_details']

    def validate(self, attrs):
        # Ensure required relations exist
        business = attrs.get('business_id')
        if isinstance(business, str):
            try:
                attrs['business_id'] = Business.objects.get(pk=business)
            except Business.DoesNotExist:
                raise serializers.ValidationError({'business_id': 'Invalid business_id'})
        user = attrs.get('user_id')
        # Accept raw numeric/string user_id
        if isinstance(user, (int, str)):
            try:
                attrs['user_id'] = Registration.objects.get(user_id=user)
            except Registration.DoesNotExist:
                raise serializers.ValidationError({'user_id': 'Invalid user_id'})
        return attrs

    def get_supplier_name(self, obj):
        """Get supplier name if supplier exists"""
        if obj.supplier_id:
            return obj.supplier_id.supplier_name
        return None

    def get_supplier_details(self, obj):
        """Get full supplier details if supplier exists"""
        if obj.supplier_id:
            return {
                'supplier_id': obj.supplier_id.supplier_id,
                'supplier_name': obj.supplier_id.supplier_name,
                'contact_person': obj.supplier_id.contact_person,
                'email': obj.supplier_id.email,
                'phone': obj.supplier_id.phone,
                'address': obj.supplier_id.address
            }
        return None

    def _resolve_r08_fashion_variant_id(self, business: Business, reference_id) -> int:
        """Resolve R08 fashion purchase payload reference_id to a FashionProductVariant.variant_id.

        For R08 purchases, client may send product_id as reference_id while using
        reference_table='fashion_product_variants'. We store inventory against variant_id.
        """
        try:
            ref_id = int(reference_id)
        except (TypeError, ValueError):
            raise serializers.ValidationError({'reference_id': 'reference_id must be an integer'})

        # Accept variant_id directly
        var = FashionProductVariant.objects.filter(
            variant_id=ref_id,
            business_id=business,
            is_active=True,
        ).first()
        if var:
            return int(var.variant_id)

        # Otherwise treat as product_id (Option A2)
        product = FashionProduct.objects.filter(
            product_id=ref_id,
            business_id=business,
            is_active=True,
        ).first()
        if not product:
            raise serializers.ValidationError({'reference_id': f'Invalid fashion reference_id {reference_id} (expected product_id or variant_id)'})

        # A2: default variant pointer first
        if getattr(product, 'variant_id', None):
            var = FashionProductVariant.objects.filter(
                variant_id=product.variant_id,
                business_id=business,
                is_active=True,
            ).first()
            if var:
                return int(var.variant_id)

        # A2 fallback: first active variant
        var = FashionProductVariant.objects.filter(
            product_id=product.product_id,
            business_id=business,
            is_active=True,
        ).order_by('variant_id').first()
        if var:
            return int(var.variant_id)

        raise serializers.ValidationError({'reference_id': f'No active fashion variant found for product_id {product.product_id}'})

    def _normalize_purchase_item_payload(self, business: Business, item: dict) -> None:
        """Mutate incoming purchase item payload in-place to normalize R08 fashion refs."""
        business_type = str(getattr(business, 'businessType', '') or '').strip().upper()
        if business_type != 'R08':
            return

        ref_table = str(item.get('reference_table') or '').strip().lower()
        if ref_table != 'fashion_product_variants':
            return

        resolved_variant_id = self._resolve_r08_fashion_variant_id(business, item.get('reference_id'))
        item['reference_table'] = 'fashion_product_variants'
        item['reference_id'] = resolved_variant_id

    @transaction.atomic
    def create(self, validated_data):
        print("DEBUG: PurchaseSerializer create method called!")
        items_data = validated_data.pop('items', [])
        print(f"DEBUG: Processing {len(items_data)} items")
        purchase = Purchases.objects.create(**validated_data)

        total_amount = Decimal('0.00')
        for item in items_data:
            item['purchase_id'] = purchase
            # default business/user from parent if not provided
            item.setdefault('business_id', validated_data['business_id'])
            item.setdefault('user_id', validated_data['user_id'])

            # R08: resolve product_id -> variant_id for fashion inventory writes
            self._normalize_purchase_item_payload(validated_data['business_id'], item)
            
            # Remove total_cost if it exists (it's a generated column)
            item.pop('total_cost', None)
            
            # Use raw SQL to insert Purchase_Items to avoid generated column issues
            with connection.cursor() as cursor:
                cursor.execute("""
                    INSERT INTO Purchase_Items (
                        purchase_id, business_id, user_id, sku, reference_table, 
                        reference_id, item_name, unit, mfg_date, exp_date, quantity, cost_price, 
                        selling_price, category, updated_at
                    ) VALUES (
                        %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, CONVERT_TZ(NOW(), 'UTC', 'Asia/Kolkata')
                    )
                """, [
                    item['purchase_id'].purchase_id,  # Get the actual purchase_id value
                    item['business_id'].business_id,  # Get the actual business_id value
                    item['user_id'].id,  # Use Registration.id (primary key) for Purchase_Items FK
                    item.get('sku'),
                    item['reference_table'],
                    item['reference_id'],
                    item['item_name'],
                    item.get('unit'),
                    item.get('mfg_date'),
                    item.get('exp_date'),
                    item['quantity'],
                    item['cost_price'],
                    item.get('selling_price', 0),
                    item.get('category')
                ])
                
                # Get the created item ID
                purchase_item_id = cursor.lastrowid
            
            # Calculate total for parent aggregation (database handles total_cost automatically)
            line_total = (Decimal(item['quantity']) * Decimal(item['cost_price']))
            total_amount += line_total
            
            # Create a Purchase_Items instance for inventory logging (without saving)
            purchase_item = Purchase_Items(
                purchase_item_id=purchase_item_id,
                purchase_id=item['purchase_id'],
                business_id=item['business_id'],
                user_id=item['user_id'],
                sku=item.get('sku'),
                reference_table=item['reference_table'],
                reference_id=item['reference_id'],
                item_name=item['item_name'],
                unit=item.get('unit'),
                mfg_date=item.get('mfg_date'),
                exp_date=item.get('exp_date'),
                quantity=item['quantity'],
                cost_price=item['cost_price'],
                selling_price=item.get('selling_price', 0),
                category=item.get('category')
            )

            # Upsert inventory and log
            self._apply_inventory_in(item=purchase_item, actor=validated_data['user_id'])

        # If client did not send total_amount, set it
        if not validated_data.get('total_amount'):
            purchase.total_amount = total_amount
            # Since managed=False, update explicitly
            Purchases.objects.filter(pk=purchase.pk).update(total_amount=total_amount)
            purchase.total_amount = total_amount

        # Write purchase log using raw SQL to avoid FK constraint issues
        # Prepare detailed log data with item information
        items_info = []
        for item_data in items_data:
            items_info.append({
                'item_name': item_data.get('item_name'),
                'sku': item_data.get('sku'),
                'quantity': str(item_data.get('quantity', 0)),
                'cost_price': str(item_data.get('cost_price', 0)),
                'selling_price': str(item_data.get('selling_price')) if item_data.get('selling_price') else None,
                'category': item_data.get('category'),
                'unit': item_data.get('unit'),
                'reference_table': item_data.get('reference_table'),
                'reference_id': item_data.get('reference_id')
            })
        
        log_data = {
            'purchase_id': purchase.purchase_id,
            'business_id': validated_data['business_id'].business_id,
            'user_id': validated_data['user_id'].id,
            'user_id_slug': getattr(validated_data['user_id'], 'user_id', None),
            'invoice_number': purchase.invoice_number,
            'total_amount': str(purchase.total_amount),
            'items_count': len(items_data),
            'items': items_info,
            'supplier_id': purchase.supplier_id.supplier_id if purchase.supplier_id else None,
            'payment_status': purchase.payment_status,
            'payment_method': purchase.payment_method,
            'purchase_date': purchase.purchase_date.isoformat() if purchase.purchase_date else None,
            'created_at': purchase.created_at.isoformat() if getattr(purchase, 'created_at', None) else None,
            'updated_at': purchase.updated_at.isoformat() if getattr(purchase, 'updated_at', None) else None
        }
        
        # First, check if business_id column exists, if not, insert without it
        with connection.cursor() as cursor:
            try:
                # Try inserting with business_id column
                print(f"DEBUG: Attempting to log with detailed data: {json.dumps(log_data)[:200]}...")
                cursor.execute("""
                    INSERT INTO Purchase_Log (
                        purchase_id, business_id, action, action_table, reason, old_data, new_data, user_id, changed_at
                    ) VALUES (
                        %s, %s, %s, %s, %s, %s, %s, %s, CONVERT_TZ(NOW(), 'UTC', 'Asia/Kolkata')
                    )
                """, [
                    purchase.purchase_id,
                    validated_data['business_id'].business_id,  # Add business_id
                    'INSERT',
                    'Purchases',
                    self.context.get('reason', 'Created via API'),
                    None,  # old_data
                    json.dumps(log_data),
                    validated_data['user_id'].id  # Use the primary key
                ])
                print("DEBUG: Successfully logged with business_id column")
            except Exception as e:
                print(f"DEBUG: Failed to log with business_id, falling back. Error: {e}")
                # If business_id column doesn't exist, insert without it
                cursor.execute("""
                    INSERT INTO Purchase_Log (
                        purchase_id, action, action_table, reason, old_data, new_data, user_id, changed_at
                    ) VALUES (
                        %s, %s, %s, %s, %s, %s, %s, CONVERT_TZ(NOW(), 'UTC', 'Asia/Kolkata')
                    )
                """, [
                    purchase.purchase_id,
                    'INSERT',
                    'Purchases',
                    self.context.get('reason', 'Created via API'),
                    None,  # old_data
                    json.dumps(log_data),
                    validated_data['user_id'].id  # Use the primary key
                ])
                print("DEBUG: Successfully logged without business_id column")

        return purchase

    def _apply_inventory_in(self, item: Purchase_Items, actor: Registration, is_update=False):
        # Determine inventory type: product/material based on explicit table mapping
        ref_table = (item.reference_table or '').lower()
        
        # Explicit mapping of reference_table to inventory type
        table_type_mapping = {
            # Restaurant items
            'menuitems': 'product',
            'menu_items': 'product',
            
            # Grocery items  
            'groceries_productvariants': 'product',
            'groceriesproductvariants': 'product',
            'groceries_products': 'product',
            'groceriesproducts': 'product',
            
            # Fashion items
            'fashion_product_variants': 'product',
            'fashionproductvariants': 'product',
            'fashion_products': 'product',
            'fashionproducts': 'product',
            
            # Generic product tables
            'productitems': 'product',
            'product_items': 'product',
            'products': 'product',
            'product': 'product'
        }
        
        inv_type = table_type_mapping.get(ref_table, 'material')

        # Use raw SQL to handle inventory to avoid generated column issues
        with connection.cursor() as cursor:
            # First, try to get existing inventory
            cursor.execute("""
                SELECT inventory_id, opening_stock, purchased_stock, sold_stock 
                FROM Inventory 
                WHERE business_id = %s AND reference_table = %s AND reference_id = %s
            """, [
                item.business_id.business_id,
                item.reference_table,
                item.reference_id
            ])
            
            existing = cursor.fetchone()

            # Fallback 1: match by SKU within the same business
            if not existing and item.sku:
                cursor.execute(
                    """
                    SELECT inventory_id, opening_stock, purchased_stock, sold_stock
                    FROM Inventory
                    WHERE business_id = %s AND sku = %s
                    ORDER BY inventory_id DESC
                    LIMIT 1
                    """,
                    [item.business_id.business_id, item.sku]
                )
                existing = cursor.fetchone()

            # Fallback 2: match by item_name (case-insensitive) within the same business
            if not existing and item.item_name:
                cursor.execute(
                    """
                    SELECT inventory_id, opening_stock, purchased_stock, sold_stock
                    FROM Inventory
                    WHERE business_id = %s AND LOWER(item_name) = LOWER(%s)
                    ORDER BY inventory_id DESC
                    LIMIT 1
                    """,
                    [item.business_id.business_id, item.item_name]
                )
                existing = cursor.fetchone()
            
            if existing:
                # Update existing inventory
                inventory_id, old_opening, old_purchased, old_sold = existing
                new_purchased = old_purchased + int(item.quantity)
                
                cursor.execute("""
                    UPDATE Inventory 
                    SET purchased_stock = %s, user_id = %s, sku = COALESCE(sku, %s), 
                        unit = COALESCE(unit, %s), item_name = COALESCE(item_name, %s), 
                        type = COALESCE(type, %s), last_updated = CONVERT_TZ(NOW(), 'UTC', 'Asia/Kolkata')
                    WHERE inventory_id = %s
                """, [
                    new_purchased, actor.id, item.sku, item.unit, 
                    item.item_name, inv_type, inventory_id
                ])
                
                old_snapshot = {
                    'opening_stock': old_opening,
                    'purchased_stock': old_purchased,
                    'sold_stock': old_sold,
                    'current_stock': None  # Will be calculated by DB
                }
                
                new_snapshot = {
                    'opening_stock': old_opening,
                    'purchased_stock': new_purchased,
                    'sold_stock': old_sold,
                    'current_stock': None  # Will be calculated by DB
                }
                
                # Only log if there's an actual quantity change
                should_log = int(item.quantity) > 0
                
            else:
                # Create new inventory record
                cursor.execute("""
                    INSERT INTO Inventory (
                        business_id, user_id, sku, reference_table, reference_id, 
                        item_name, type, unit, opening_stock, purchased_stock, 
                        sold_stock, last_updated
                    ) VALUES (
                        %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, CONVERT_TZ(NOW(), 'UTC', 'Asia/Kolkata')
                    )
                """, [
                    item.business_id.business_id, actor.id, item.sku, 
                    item.reference_table, item.reference_id, item.item_name, 
                    inv_type, item.unit, 0, int(item.quantity), 0
                ])
                
                inventory_id = cursor.lastrowid
                
                old_snapshot = {
                    'opening_stock': 0,
                    'purchased_stock': 0,
                    'sold_stock': 0,
                    'current_stock': None
                }
                
                new_snapshot = {
                    'opening_stock': 0,
                    'purchased_stock': int(item.quantity),
                    'sold_stock': 0,
                    'current_stock': None
                }
                
                # Always log when creating new inventory item (new item added)
                should_log = True
        
        # CRITICAL: Synchronize stock with item tables (MenuItems, productItems, GroceriesProductVariants)
        # This ensures that the stock shown in inventory matches the stock checked during orders
        self._sync_item_table_stock(item, int(item.quantity))

        # Only create inventory log if there's a meaningful change
        if should_log:
            with connection.cursor() as cursor:
                cursor.execute("""
                    INSERT INTO Inventory_Log (
                        inventory_id, business_id, sku, reference_table, reference_id, 
                        item_name, action, reason, old_stock, new_stock, user_id, changed_at
                    ) VALUES (
                        %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, CONVERT_TZ(NOW(), 'UTC', 'Asia/Kolkata')
                    )
                """, [
                    inventory_id,
                    item.business_id.business_id,
                    item.sku,
                    item.reference_table,
                    item.reference_id,
                    item.item_name,
                    'UPDATE' if is_update else 'ADD',
                    f'Updated via purchase_id {item.purchase_id.purchase_id}' if is_update else f'Purchased via purchase_id {item.purchase_id.purchase_id}',
                    json.dumps(old_snapshot),  # Convert dict to JSON string
                    json.dumps(new_snapshot),  # Convert dict to JSON string
                    actor.id
                ])


    def _sync_item_table_stock(self, item: Purchase_Items, quantity_to_add: int):
        """
        Synchronize stock in item tables (MenuItems, productItems, GroceriesProductVariants)
        when inventory is updated via purchases.
        This ensures order validation checks the correct stock levels.
        """
        ref_table = (item.reference_table or '').lower()
        
        try:
            if 'menuitems' in ref_table or ref_table == 'menuitems':
                # Update MenuItems.quantity
                from business.models import MenuItems
                try:
                    menu_item = MenuItems.objects.get(item_id=item.reference_id)
                    # Increment quantity by purchased amount
                    current_qty = menu_item.quantity if menu_item.quantity is not None else 0
                    menu_item.quantity = current_qty + quantity_to_add
                    menu_item.save(update_fields=['quantity'])
                    logger.info(f"Synced MenuItems stock for {menu_item.item_name}: {current_qty} + {quantity_to_add} = {menu_item.quantity}")
                except MenuItems.DoesNotExist:
                    logger.warning(f"MenuItems with ID {item.reference_id} not found for stock sync")
            
            elif 'groceries_productvariants' in ref_table or 'groceriesproductvariants' in ref_table:
                # Update GroceriesProductVariants.stock
                from consumer.gro_models import GroceriesProductVariants
                try:
                    variant = GroceriesProductVariants.objects.get(variant_id=item.reference_id)
                    # Increment stock by purchased amount
                    current_stock = variant.stock if variant.stock is not None else 0
                    variant.stock = current_stock + quantity_to_add
                    variant.save(update_fields=['stock'])
                    logger.info(f"Synced GroceriesProductVariants stock for {variant.sku}: {current_stock} + {quantity_to_add} = {variant.stock}")
                except GroceriesProductVariants.DoesNotExist:
                    logger.warning(f"GroceriesProductVariants with ID {item.reference_id} not found for stock sync")
            
            elif 'groceryitems' in ref_table or ref_table == 'groceryitems':
                # Update productItems.stock (table name is GroceryItems)
                from business.models import productItems
                try:
                    product_item = productItems.objects.get(item_id=item.reference_id)
                    # Increment stock by purchased amount
                    current_stock = product_item.stock if product_item.stock is not None else 0
                    product_item.stock = current_stock + quantity_to_add
                    product_item.save(update_fields=['stock'])
                    logger.info(f"Synced productItems stock for {product_item.item_name}: {current_stock} + {quantity_to_add} = {product_item.stock}")
                except productItems.DoesNotExist:
                    logger.warning(f"productItems with ID {item.reference_id} not found for stock sync")

            elif 'fashion_product_variants' in ref_table or 'fashionproductvariants' in ref_table:
                # Update FashionProductVariant.stock (authoritative) and keep stock_qty synced
                try:
                    var = FashionProductVariant.objects.filter(variant_id=item.reference_id, is_active=True).first()
                    if not var:
                        # Robustness: accept product_id as reference_id and resolve to default variant (A2)
                        try:
                            business = getattr(item, 'business_id', None)
                            if business and getattr(business, 'businessType', None):
                                resolved_variant_id = self._resolve_r08_fashion_variant_id(business, item.reference_id)
                                var = FashionProductVariant.objects.filter(variant_id=resolved_variant_id, is_active=True).first()
                        except Exception:
                            var = None

                    if var:
                        current_stock = var.stock if var.stock is not None else int(var.stock_qty or 0)
                        new_stock = int(current_stock) + int(quantity_to_add)
                        var.stock = new_stock
                        var.stock_qty = new_stock
                        var.save(update_fields=['stock', 'stock_qty'])
                        logger.info(f"Synced FashionProductVariant stock for {var.sku}: {current_stock} + {quantity_to_add} = {new_stock}")
                    else:
                        logger.warning(f"FashionProductVariant not found for reference_id {item.reference_id} (stock sync skipped)")
                except Exception as e:
                    logger.error(f"Error syncing FashionProductVariant stock for reference_id {item.reference_id}: {str(e)}")
            
            else:
                logger.info(f"No stock sync needed for reference_table: {item.reference_table}")
        
        except Exception as e:
            logger.error(f"Error syncing item table stock for {item.item_name}: {str(e)}")
            # Don't raise - stock sync is supplementary

    def _apply_inventory_out(self, item: Purchase_Items, actor: Registration, is_update=False):
        """Reverse inventory effect for an existing purchase item (subtract purchased_stock)."""
        ref_table_lower = (item.reference_table or '').lower()
        # Use raw SQL similar to _apply_inventory_in, but subtract quantity from purchased_stock
        with connection.cursor() as cursor:
            # Try to get existing inventory
            cursor.execute("""
                SELECT inventory_id, opening_stock, purchased_stock, sold_stock 
                FROM Inventory 
                WHERE business_id = %s AND reference_table = %s AND reference_id = %s
            """, [
                item.business_id.business_id,
                item.reference_table,
                item.reference_id
            ])

            existing = cursor.fetchone()

            # Fallback 1: match by SKU within the same business
            if not existing and item.sku:
                cursor.execute(
                    """
                    SELECT inventory_id, opening_stock, purchased_stock, sold_stock
                    FROM Inventory
                    WHERE business_id = %s AND sku = %s
                    ORDER BY inventory_id DESC
                    LIMIT 1
                    """,
                    [item.business_id.business_id, item.sku]
                )
                existing = cursor.fetchone()

            # Fallback 2: match by item_name (case-insensitive) within the same business
            if not existing and item.item_name:
                cursor.execute(
                    """
                    SELECT inventory_id, opening_stock, purchased_stock, sold_stock
                    FROM Inventory
                    WHERE business_id = %s AND LOWER(item_name) = LOWER(%s)
                    ORDER BY inventory_id DESC
                    LIMIT 1
                    """,
                    [item.business_id.business_id, item.item_name]
                )
                existing = cursor.fetchone()

            if existing:
                inventory_id, old_opening, old_purchased, old_sold = existing
                new_purchased = max(int(old_purchased) - int(item.quantity), 0)

                cursor.execute("""
                    UPDATE Inventory 
                    SET purchased_stock = %s, user_id = %s, last_updated = CONVERT_TZ(NOW(), 'UTC', 'Asia/Kolkata')
                    WHERE inventory_id = %s
                """, [
                    new_purchased, actor.id, inventory_id
                ])

                old_snapshot = {
                    'opening_stock': int(old_opening) if old_opening is not None else 0,
                    'purchased_stock': int(old_purchased) if old_purchased is not None else 0,
                    'sold_stock': int(old_sold) if old_sold is not None else 0,
                    'current_stock': None
                }
                new_snapshot = {
                    'opening_stock': int(old_opening) if old_opening is not None else 0,
                    'purchased_stock': int(new_purchased),
                    'sold_stock': int(old_sold) if old_sold is not None else 0,
                    'current_stock': None
                }

                # Only log if there's an actual quantity reduction
                if int(item.quantity) > 0 and old_purchased != new_purchased:
                    cursor.execute("""
                        INSERT INTO Inventory_Log (
                            inventory_id, business_id, sku, reference_table, reference_id, 
                            item_name, action, reason, old_stock, new_stock, user_id, changed_at
                        ) VALUES (
                            %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, CONVERT_TZ(NOW(), 'UTC', 'Asia/Kolkata')
                        )
                    """, [
                        inventory_id,
                        item.business_id.business_id,
                        item.sku,
                        item.reference_table,
                        item.reference_id,
                        item.item_name,
                        'UPDATE' if is_update else 'ADJUST',
                        f'Updated purchase_id {item.purchase_id.purchase_id}' if is_update else f'Reversal of purchase_id {item.purchase_id.purchase_id} during update',
                        json.dumps(old_snapshot),
                        json.dumps(new_snapshot),
                        actor.id
                    ])
                
                # CRITICAL: Reverse sync stock in item tables (reduce stock)
                self._sync_item_table_stock(item, -int(item.quantity))
            else:
                # Nothing to adjust if inventory does not exist
                pass

    def _apply_inventory_in_silent(self, item: Purchase_Items, actor: Registration):
        """Apply inventory changes without logging - used during updates."""
        ref_table = (item.reference_table or '').lower()
        
        # Explicit mapping of reference_table to inventory type
        table_type_mapping = {
            # Restaurant items
            'menuitems': 'product',
            'menu_items': 'product',
            
            # Grocery items  
            'groceries_productvariants': 'product',
            'groceriesproductvariants': 'product',
            'groceries_products': 'product',
            'groceriesproducts': 'product',
            
            # Fashion items
            'fashion_product_variants': 'product',
            'fashionproductvariants': 'product',
            'fashion_products': 'product',
            'fashionproducts': 'product',
            
            # Generic product tables
            'productitems': 'product',
            'product_items': 'product',
            'products': 'product',
            'product': 'product'
        }
        
        inv_type = table_type_mapping.get(ref_table, 'material')

        with connection.cursor() as cursor:
            # Try to get existing inventory
            cursor.execute("""
                SELECT inventory_id, opening_stock, purchased_stock, sold_stock 
                FROM Inventory 
                WHERE business_id = %s AND reference_table = %s AND reference_id = %s
            """, [
                item.business_id.business_id,
                item.reference_table,
                item.reference_id
            ])
            
            existing = cursor.fetchone()

            # Fallback searches
            if not existing and item.sku:
                cursor.execute(
                    """
                    SELECT inventory_id, opening_stock, purchased_stock, sold_stock
                    FROM Inventory
                    WHERE business_id = %s AND sku = %s
                    ORDER BY inventory_id DESC
                    LIMIT 1
                    """,
                    [item.business_id.business_id, item.sku]
                )
                existing = cursor.fetchone()

            if not existing and item.item_name:
                cursor.execute(
                    """
                    SELECT inventory_id, opening_stock, purchased_stock, sold_stock
                    FROM Inventory
                    WHERE business_id = %s AND LOWER(item_name) = LOWER(%s)
                    ORDER BY inventory_id DESC
                    LIMIT 1
                    """,
                    [item.business_id.business_id, item.item_name]
                )
                existing = cursor.fetchone()
            
            if existing:
                # Update existing inventory
                inventory_id, old_opening, old_purchased, old_sold = existing
                new_purchased = old_purchased + int(item.quantity)
                
                cursor.execute("""
                    UPDATE Inventory 
                    SET purchased_stock = %s, user_id = %s, sku = COALESCE(sku, %s), 
                        unit = COALESCE(unit, %s), item_name = COALESCE(item_name, %s), 
                        type = COALESCE(type, %s), last_updated = CONVERT_TZ(NOW(), 'UTC', 'Asia/Kolkata')
                    WHERE inventory_id = %s
                """, [
                    new_purchased, actor.id, item.sku, item.unit, 
                    item.item_name, inv_type, inventory_id
                ])
            else:
                # Create new inventory record
                cursor.execute("""
                    INSERT INTO Inventory (
                        business_id, user_id, sku, reference_table, reference_id, 
                        item_name, type, unit, opening_stock, purchased_stock, 
                        sold_stock, last_updated
                    ) VALUES (
                        %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, CONVERT_TZ(NOW(), 'UTC', 'Asia/Kolkata')
                    )
                """, [
                    item.business_id.business_id, actor.id, item.sku, 
                    item.reference_table, item.reference_id, item.item_name, 
                    inv_type, item.unit, 0, int(item.quantity), 0
                ])
            
            # Sync stock in item tables
            self._sync_item_table_stock(item, int(item.quantity))

    def _apply_inventory_out_silent(self, item: Purchase_Items, actor: Registration):
        """Reverse inventory effect without logging - used during updates."""
        with connection.cursor() as cursor:
            # Try to get existing inventory
            cursor.execute("""
                SELECT inventory_id, opening_stock, purchased_stock, sold_stock 
                FROM Inventory 
                WHERE business_id = %s AND reference_table = %s AND reference_id = %s
            """, [
                item.business_id.business_id,
                item.reference_table,
                item.reference_id
            ])

            existing = cursor.fetchone()

            # Fallback searches
            if not existing and item.sku:
                cursor.execute(
                    """
                    SELECT inventory_id, opening_stock, purchased_stock, sold_stock
                    FROM Inventory
                    WHERE business_id = %s AND sku = %s
                    ORDER BY inventory_id DESC
                    LIMIT 1
                    """,
                    [item.business_id.business_id, item.sku]
                )
                existing = cursor.fetchone()

            if not existing and item.item_name:
                cursor.execute(
                    """
                    SELECT inventory_id, opening_stock, purchased_stock, sold_stock
                    FROM Inventory
                    WHERE business_id = %s AND LOWER(item_name) = LOWER(%s)
                    ORDER BY inventory_id DESC
                    LIMIT 1
                    """,
                    [item.business_id.business_id, item.item_name]
                )
                existing = cursor.fetchone()

            if existing:
                inventory_id, old_opening, old_purchased, old_sold = existing
                new_purchased = max(int(old_purchased) - int(item.quantity), 0)

                cursor.execute("""
                    UPDATE Inventory 
                    SET purchased_stock = %s, user_id = %s, last_updated = CONVERT_TZ(NOW(), 'UTC', 'Asia/Kolkata')
                    WHERE inventory_id = %s
                """, [
                    new_purchased, actor.id, inventory_id
                ])
                
                # Reverse sync stock in item tables (reduce stock)
                self._sync_item_table_stock(item, -int(item.quantity))

    def _log_inventory_change(self, item: Purchase_Items, actor: Registration, action: str, reason: str, quantity_change: int, old_purchased_stock: int = None):
        """Log a single inventory change with proper old and new data states."""
        with connection.cursor() as cursor:
            # Get current inventory state for logging
            cursor.execute("""
                SELECT inventory_id, opening_stock, purchased_stock, sold_stock 
                FROM Inventory 
                WHERE business_id = %s AND reference_table = %s AND reference_id = %s
            """, [
                item.business_id.business_id,
                item.reference_table,
                item.reference_id
            ])
            
            existing = cursor.fetchone()
            if existing:
                inventory_id, opening, current_purchased, sold = existing
                
                # Calculate old purchased stock
                if old_purchased_stock is not None:
                    # Use provided old stock value
                    old_purchased = old_purchased_stock
                else:
                    # Calculate based on quantity change
                    old_purchased = max(0, int(current_purchased) - quantity_change)
                
                old_snapshot = {
                    'opening_stock': int(opening) if opening is not None else 0,
                    'purchased_stock': old_purchased,
                    'sold_stock': int(sold) if sold is not None else 0,
                    'current_stock': (int(opening) if opening is not None else 0) + old_purchased - (int(sold) if sold is not None else 0)
                }
                
                new_snapshot = {
                    'opening_stock': int(opening) if opening is not None else 0,
                    'purchased_stock': int(current_purchased),
                    'sold_stock': int(sold) if sold is not None else 0,
                    'current_stock': (int(opening) if opening is not None else 0) + int(current_purchased) - (int(sold) if sold is not None else 0)
                }
                
                cursor.execute("""
                    INSERT INTO Inventory_Log (
                        inventory_id, business_id, sku, reference_table, reference_id, 
                        item_name, action, reason, old_stock, new_stock, user_id, changed_at
                    ) VALUES (
                        %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, CONVERT_TZ(NOW(), 'UTC', 'Asia/Kolkata')
                    )
                """, [
                    inventory_id,
                    item.business_id.business_id,
                    item.sku,
                    item.reference_table,
                    item.reference_id,
                    item.item_name,
                    action,
                    reason,
                    json.dumps(old_snapshot),
                    json.dumps(new_snapshot),
                    actor.id
                ])


    @transaction.atomic
    def update(self, instance, validated_data):
        """Update purchase with items and inventory adjustments."""
        # Pop items from validated_data
        items_data = validated_data.pop('items', [])

        # Determine context objects
        user = validated_data.get('user_id', None)
        business = validated_data.get('business_id', None)
        # Capture old parent fields BEFORE any mutations
        old_invoice_number = instance.invoice_number
        old_payment_status = instance.payment_status
        old_payment_method = instance.payment_method
        old_purchase_date = instance.purchase_date
        old_supplier_id_value = instance.supplier_id.supplier_id if instance.supplier_id else None
        old_business_id_value = instance.business_id.business_id if getattr(instance, 'business_id', None) else None
        old_created_at_val = instance.created_at if hasattr(instance, 'created_at') else None
        old_updated_at_val = instance.updated_at if hasattr(instance, 'updated_at') else None
        # Keep snapshot for logs with detailed item information
        old_items_count = instance.items.count()
        old_total = instance.total_amount
        old_items_info = []
        for item in instance.items.all():
            old_items_info.append({
                'item_name': item.item_name,
                'sku': item.sku,
                'quantity': str(item.quantity),
                'cost_price': str(item.cost_price),
                'selling_price': str(item.selling_price) if item.selling_price else None,
                'category': item.category,
                'unit': item.unit,
                'reference_table': item.reference_table,
                'reference_id': item.reference_id,
                'purchase_item_id': item.purchase_item_id
            })

        # Replace items if provided
        if items_data is not None:
            # R08: resolve product_id -> variant_id for fashion inventory writes
            for item in items_data:
                try:
                    self._normalize_purchase_item_payload(business, item)
                except Exception:
                    raise

            # Calculate net inventory changes to avoid duplicate logs
            old_inventory_map = {}  # {(reference_table, reference_id): quantity}
            new_inventory_map = {}  # {(reference_table, reference_id): quantity}
            
            # Map old quantities
            existing_items = list(instance.items.all())
            for ex in existing_items:
                key = (ex.reference_table, ex.reference_id)
                old_inventory_map[key] = old_inventory_map.get(key, 0) + int(ex.quantity)
            
            # Map new quantities
            for item in items_data:
                key = (item['reference_table'], item['reference_id'])
                new_inventory_map[key] = new_inventory_map.get(key, 0) + int(item['quantity'])
            
            # Reverse inventory for existing items (without logging)
            for ex in existing_items:
                ex_for_inv = Purchase_Items(
                    purchase_item_id=ex.purchase_item_id,
                    purchase_id=instance,
                    business_id=business,
                    user_id=user,
                    sku=ex.sku,
                    reference_table=ex.reference_table,
                    reference_id=ex.reference_id,
                    item_name=ex.item_name,
                    unit=ex.unit,
                    mfg_date=getattr(ex, 'mfg_date', None),
                    exp_date=getattr(ex, 'exp_date', None),
                    quantity=ex.quantity,
                    cost_price=ex.cost_price,
                    selling_price=ex.selling_price,
                    category=ex.category
                )
                # Apply inventory changes without logging (we'll log net changes later)
                self._apply_inventory_out_silent(item=ex_for_inv, actor=user)

                # Delete the existing purchase item
                with connection.cursor() as cursor:
                    cursor.execute("DELETE FROM Purchase_Items WHERE purchase_item_id = %s", [ex.purchase_item_id])

            # Insert new items and apply inventory
            total_amount = Decimal('0.00')
            print(f"[DEBUG SERIALIZER] User object: {user}, user.id: {user.id if user else 'None'}")
            print(f"[DEBUG SERIALIZER] Business object: {business}, business.business_id: {business.business_id if business else 'None'}")
            
            for item in items_data:
                item['purchase_id'] = instance
                item.setdefault('business_id', business)
                item.setdefault('user_id', user)
                item.pop('total_cost', None)
                
                print(f"[DEBUG SERIALIZER] About to insert item with user_id: {user.id if user else 'None'}")
                
                # Verify user exists in registrations table
                with connection.cursor() as cursor:
                    cursor.execute("SELECT id, user_id FROM registrations WHERE id = %s", [user.id])
                    user_check = cursor.fetchone()
                    if user_check:
                        print(f"[DEBUG SERIALIZER] User verification: Found user with id={user_check[0]}, user_id={user_check[1]}")
                    else:
                        print(f"[DEBUG SERIALIZER] ERROR: User with id={user.id} NOT FOUND in registrations table!")
                        raise ValueError(f"User with id={user.id} does not exist in registrations table")

                with connection.cursor() as cursor:
                    cursor.execute("""
                        INSERT INTO Purchase_Items (
                            purchase_id, business_id, user_id, sku, reference_table, 
                            reference_id, item_name, unit, mfg_date, exp_date, quantity, cost_price, 
                            selling_price, category, created_at, updated_at
                        ) VALUES (
                            %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, CONVERT_TZ(NOW(), 'UTC', 'Asia/Kolkata'), CONVERT_TZ(NOW(), 'UTC', 'Asia/Kolkata')
                        )
                    """, [
                        instance.purchase_id,
                        business.business_id,
                        user.id,
                        item.get('sku'),
                        item['reference_table'],
                        item['reference_id'],
                        item['item_name'],
                        item.get('unit'),
                        item.get('mfg_date'),
                        item.get('exp_date'),
                        item['quantity'],
                        item['cost_price'],
                        item.get('selling_price', 0),
                        item.get('category')
                    ])
                    purchase_item_id = cursor.lastrowid

                line_total = (Decimal(item['quantity']) * Decimal(item['cost_price']))
                total_amount += line_total

                purchase_item = Purchase_Items(
                    purchase_item_id=purchase_item_id,
                    purchase_id=instance,
                    business_id=business,
                    user_id=user,
                    sku=item.get('sku'),
                    reference_table=item['reference_table'],
                    reference_id=item['reference_id'],
                    item_name=item['item_name'],
                    unit=item.get('unit'),
                    mfg_date=item.get('mfg_date'),
                    exp_date=item.get('exp_date'),
                    quantity=item['quantity'],
                    cost_price=item['cost_price'],
                    selling_price=item.get('selling_price', 0),
                    category=item.get('category')
                )
                # Apply inventory changes without logging (we'll log net changes later)
                self._apply_inventory_in_silent(item=purchase_item, actor=user)
            
            # Capture current inventory states before logging
            inventory_states = {}  # {(ref_table, ref_id): (inventory_id, opening, purchased, sold)}
            with connection.cursor() as cursor:
                for key in set(old_inventory_map.keys()) | set(new_inventory_map.keys()):
                    ref_table, ref_id = key
                    cursor.execute("""
                        SELECT inventory_id, opening_stock, purchased_stock, sold_stock 
                        FROM Inventory 
                        WHERE business_id = %s AND reference_table = %s AND reference_id = %s
                    """, [
                        business.business_id,
                        ref_table,
                        ref_id
                    ])
                    result = cursor.fetchone()
                    if result:
                        inventory_states[key] = result
            
            # Now log only the net changes
            all_keys = set(old_inventory_map.keys()) | set(new_inventory_map.keys())
            for key in all_keys:
                old_qty = old_inventory_map.get(key, 0)
                new_qty = new_inventory_map.get(key, 0)
                net_change = new_qty - old_qty
                
                if net_change != 0 and key in inventory_states:  # Only log if there's a net change and inventory exists
                    # Get current inventory state
                    inventory_id, opening, current_purchased, sold = inventory_states[key]
                    old_purchased_stock = max(0, int(current_purchased) - net_change)
                    
                    # Find a representative item for this key to use for logging
                    ref_table, ref_id = key
                    sample_item = None
                    
                    # Look for item in new items first
                    for item_data in items_data:
                        if item_data['reference_table'] == ref_table and item_data['reference_id'] == ref_id:
                            sample_item = Purchase_Items(
                                purchase_id=instance,
                                business_id=business,
                                user_id=user,
                                sku=item_data.get('sku'),
                                reference_table=ref_table,
                                reference_id=ref_id,
                                item_name=item_data['item_name'],
                                unit=item_data.get('unit'),
                                quantity=abs(net_change),  # Use absolute value for logging
                                cost_price=item_data['cost_price'],
                                selling_price=item_data.get('selling_price', 0),
                                category=item_data.get('category')
                            )
                            break
                    
                    # If not found in new items, use old item data
                    if not sample_item:
                        for ex in existing_items:
                            if ex.reference_table == ref_table and ex.reference_id == ref_id:
                                sample_item = Purchase_Items(
                                    purchase_id=instance,
                                    business_id=business,
                                    user_id=user,
                                    sku=ex.sku,
                                    reference_table=ref_table,
                                    reference_id=ref_id,
                                    item_name=ex.item_name,
                                    unit=ex.unit,
                                    quantity=abs(net_change),
                                    cost_price=ex.cost_price,
                                    selling_price=ex.selling_price,
                                    category=ex.category
                                )
                                break
                    
                    if sample_item:
                        if net_change > 0:
                            # Net increase - log as UPDATE action
                            self._log_inventory_change(sample_item, actor=user, action='UPDATE', 
                                                     reason=f'Net increase of {net_change} via purchase_id {instance.purchase_id}',
                                                     quantity_change=net_change, old_purchased_stock=old_purchased_stock)
                        else:
                            # Net decrease - log as UPDATE action  
                            self._log_inventory_change(sample_item, actor=user, action='UPDATE',
                                                     reason=f'Net decrease of {abs(net_change)} via purchase_id {instance.purchase_id}',
                                                     quantity_change=net_change, old_purchased_stock=old_purchased_stock)

            # Update total_amount
            Purchases.objects.filter(pk=instance.pk).update(total_amount=total_amount)
            instance.total_amount = total_amount

        # Update parent fields if provided
        update_fields = {}
        for field in ['supplier_id', 'invoice_number', 'payment_status', 'payment_method', 'purchase_date']:
            if field in validated_data:
                update_fields[field] = validated_data[field]

        if update_fields:
            Purchases.objects.filter(pk=instance.pk).update(**update_fields)
            for k, v in update_fields.items():
                setattr(instance, k, v)

        # Ensure instance fields (e.g. updated_at) reflect DB after updates
        try:
            instance.refresh_from_db()
        except Exception:
            pass

        # Write update log with detailed item information
        new_items_count = instance.items.count()
        new_items_info = []
        for item in instance.items.all():
            new_items_info.append({
                'item_name': item.item_name,
                'sku': item.sku,
                'quantity': str(item.quantity),
                'cost_price': str(item.cost_price),
                'selling_price': str(item.selling_price) if item.selling_price else None,
                'category': item.category,
                'unit': item.unit,
                'reference_table': item.reference_table,
                'reference_id': item.reference_id,
                'purchase_item_id': item.purchase_item_id
            })
        
        old_snapshot = {
            'purchase_id': instance.purchase_id,
            'business_id': old_business_id_value if old_business_id_value is not None else (getattr(instance.business_id, 'business_id', None)),
            'user_id': user.id if user else getattr(instance.user_id, 'id', None),
            'user_id_slug': user.user_id if user else getattr(instance.user_id, 'user_id', None),
            'invoice_number': old_invoice_number,
            'total_amount': str(old_total) if old_total is not None else None,
            'items_count': old_items_count,
            'items': old_items_info,
            'supplier_id': old_supplier_id_value,
            'payment_status': old_payment_status,
            'payment_method': old_payment_method,
            'purchase_date': old_purchase_date.isoformat() if old_purchase_date else None,
            'created_at': old_created_at_val.isoformat() if old_created_at_val else None,
            'updated_at': old_updated_at_val.isoformat() if old_updated_at_val else None
        }
        
        new_snapshot = {
            'purchase_id': instance.purchase_id,
            'business_id': business.business_id if business else getattr(instance.business_id, 'business_id', None),
            'user_id': user.id if user else getattr(instance.user_id, 'id', None),
            'user_id_slug': user.user_id if user else getattr(instance.user_id, 'user_id', None),
            'invoice_number': instance.invoice_number,
            'total_amount': str(instance.total_amount),
            'items_count': new_items_count,
            'items': new_items_info,
            'supplier_id': instance.supplier_id.supplier_id if instance.supplier_id else None,
            'payment_status': instance.payment_status,
            'payment_method': instance.payment_method,
            'purchase_date': instance.purchase_date.isoformat() if instance.purchase_date else None,
            'created_at': instance.created_at.isoformat() if getattr(instance, 'created_at', None) else None,
            'updated_at': instance.updated_at.isoformat() if getattr(instance, 'updated_at', None) else None
        }

        with connection.cursor() as cursor:
            try:
                cursor.execute("""
                    INSERT INTO Purchase_Log (
                        purchase_id, business_id, action, action_table, reason, old_data, new_data, user_id, changed_at
                    ) VALUES (
                        %s, %s, %s, %s, %s, %s, %s, %s, CONVERT_TZ(NOW(), 'UTC', 'Asia/Kolkata')
                    )
                """, [
                    instance.purchase_id,
                    business.business_id,
                    'UPDATE',
                    'Purchases',
                    self.context.get('reason'),
                    json.dumps(old_snapshot),
                    json.dumps(new_snapshot),
                    user.id
                ])
            except Exception:
                cursor.execute("""
                    INSERT INTO Purchase_Log (
                        purchase_id, action, action_table, reason, old_data, new_data, user_id, changed_at
                    ) VALUES (
                        %s, %s, %s, %s, %s, %s, %s, CONVERT_TZ(NOW(), 'UTC', 'Asia/Kolkata')
                    )
                """, [
                    instance.purchase_id,
                    'UPDATE',
                    'Purchases',
                    self.context.get('reason'),
                    json.dumps(old_snapshot),
                    json.dumps(new_snapshot),
                    user.id
                ])

        return instance
class InventorySerializer(serializers.ModelSerializer):
    user_id = serializers.PrimaryKeyRelatedField(
        queryset=Registration.objects.all()
    )
    mfg_date = serializers.SerializerMethodField(read_only=True)
    expiry_date = serializers.SerializerMethodField(read_only=True)
    days_to_expiry = serializers.SerializerMethodField(read_only=True)
    is_expiring_soon = serializers.SerializerMethodField(read_only=True)
    batches = serializers.SerializerMethodField(read_only=True)

    def _get_purchase_batches(self, obj):
        """Build batch-level info from Purchase_Items for this inventory row.

        Groups by (mfg_date, exp_date) and applies a simple FIFO allocation of
        sold_stock to estimate remaining quantity per batch.
        """
        qs = Purchase_Items.objects.filter(
            business_id=obj.business_id,
            reference_table=obj.reference_table,
            reference_id=obj.reference_id,
        )
        if obj.sku:
            qs = qs.filter(sku=obj.sku)

        if not qs.exists():
            return []

        from datetime import date

        grouped = {}
        for it in qs:
            key = (it.mfg_date, it.exp_date)
            if key not in grouped:
                grouped[key] = {
                    "mfg_date": it.mfg_date,
                    "exp_date": it.exp_date,
                    "purchased_qty": 0,
                }
            grouped[key]["purchased_qty"] += int(it.quantity or 0)

        def _sort_key(batch):
            exp = batch["exp_date"] or date.max
            mfg = batch["mfg_date"] or date.max
            return (exp, mfg)

        batches = sorted(grouped.values(), key=_sort_key)

        # Allocate sold_stock across batches using FIFO (oldest expiry first)
        remaining_sold = int(obj.sold_stock or 0)
        for batch in batches:
            purchased = batch["purchased_qty"]
            sold_from_batch = min(purchased, remaining_sold)
            batch["sold_qty_estimated"] = sold_from_batch
            batch["remaining_qty_estimated"] = max(purchased - sold_from_batch, 0)
            remaining_sold -= sold_from_batch

        return batches

    def get_batches(self, obj):
        batches = self._get_purchase_batches(obj)
        return [
            {
                "mfg_date": batch["mfg_date"],
                "exp_date": batch["exp_date"],
                "purchased_quantity": batch["purchased_qty"],
                "estimated_remaining_quantity": batch["remaining_qty_estimated"],
            }
            for batch in batches
        ]

    def _get_earliest_active_batch(self, obj):
        batches = self._get_purchase_batches(obj)
        if not batches:
            return None

        from datetime import date
        today = date.today()

        # Separate batches into unexpired and expired, considering only those with remaining stock
        unexpired_with_stock = []
        expired_with_stock = []

        for b in batches:
            if b.get("remaining_qty_estimated", 0) > 0 and b.get("exp_date"):
                if b["exp_date"] >= today:
                    unexpired_with_stock.append(b)
                else:
                    expired_with_stock.append(b)

        def _sort_key(batch):
            # Safely handle None dates for sorting
            exp = batch.get("exp_date") or date.max
            mfg = batch.get("mfg_date") or date.max
            return (exp, mfg)

        # Prioritize the earliest-expiring batch that is NOT yet expired
        if unexpired_with_stock:
            return sorted(unexpired_with_stock, key=_sort_key)[0]

        # If no unexpired stock, the item is effectively expired. Return the latest expired batch.
        if expired_with_stock:
            return sorted(expired_with_stock, key=_sort_key, reverse=True)[0]
        
        # Fallback for items with no stock or no expiry dates
        return None

    def get_mfg_date(self, obj):
        batch = self._get_earliest_active_batch(obj)
        if not batch:
            return None
        return batch["mfg_date"]

    def get_expiry_date(self, obj):
        batch = self._get_earliest_active_batch(obj)
        if not batch:
            return None
        return batch["exp_date"]

    def get_days_to_expiry(self, obj):
        expiry = self.get_expiry_date(obj)
        if not expiry:
            return None

        from datetime import date

        try:
            delta = expiry - date.today()
            return delta.days
        except Exception:
            return None

    def get_is_expiring_soon(self, obj):
        days = self.get_days_to_expiry(obj)
        if days is None:
            return False
        # Consider items expiring within the next 10 days (including today) as "soon"
        return 0 <= days <= 10

    class Meta:
        model = Inventory
        fields = '__all__'
        read_only_fields = ['inventory_id', 'current_stock', 'last_updated']


class PurchaseLogSerializer(serializers.ModelSerializer):
    user_name = serializers.SerializerMethodField(read_only=True)
    business_id = serializers.SerializerMethodField(read_only=True)
    purchase_invoice_number = serializers.SerializerMethodField(read_only=True)
    
    class Meta:
        model = Purchase_Log
        fields = '__all__'
        read_only_fields = ['log_id', 'changed_at']
    
    def get_user_name(self, obj):
        """Get user name from Registration model"""
        if obj.user_id:
            return f"{obj.user_id.firstName} {obj.user_id.lastName}"
        return None
    
    def get_business_id(self, obj):
        """Get business_id directly from the log record or through purchase relationship"""
        # Try to get business_id directly from the log record
        if hasattr(obj, 'business_id') and obj.business_id:
            return obj.business_id.business_id
        # Fallback to getting business_id through purchase relationship
        elif obj.purchase_id and obj.purchase_id.business_id:
            return obj.purchase_id.business_id.business_id
        return None
    
    def get_purchase_invoice_number(self, obj):
        """Get invoice number from related purchase"""
        if obj.purchase_id:
            return obj.purchase_id.invoice_number
        return None


class InventoryLogSerializer(serializers.ModelSerializer):
    user_name = serializers.SerializerMethodField(read_only=True)
    
    class Meta:
        model = Inventory_Log
        fields = '__all__'
        read_only_fields = ['log_id', 'changed_at']
    
    def get_user_name(self, obj):
        """Get user name from Registration model"""
        if obj.user_id:
            return f"{obj.user_id.firstName} {obj.user_id.lastName}"
        return None

    def to_representation(self, instance):
        data = super().to_representation(instance)
        edit_reason = getattr(instance, 'edit_reason', None)
        if edit_reason:
            data['reason'] = edit_reason
        return data


class ExpensesSerializer(serializers.ModelSerializer):
    user_id = serializers.SlugRelatedField(
        slug_field='user_id', queryset=Registration.objects.all()
    )
    business_id = serializers.SlugRelatedField(
        slug_field='business_id', queryset=Business.objects.all()
    )
    supplier_id = serializers.PrimaryKeyRelatedField(
        queryset=Suppliers.objects.all(), 
        required=False, 
        allow_null=True
    )
    supplier_name = serializers.SerializerMethodField(read_only=True)
    supplier_details = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = Expenses
        fields = '__all__'
        read_only_fields = ['expense_id', 'created_at', 'updated_at', 'supplier_name', 'supplier_details']

    def validate(self, attrs):
        # Ensure required relations exist
        business = attrs.get('business_id')
        if isinstance(business, str):
            try:
                attrs['business_id'] = Business.objects.get(pk=business)
            except Business.DoesNotExist:
                raise serializers.ValidationError({'business_id': 'Invalid business_id'})
        user = attrs.get('user_id')
        # Accept raw numeric/string user_id
        if isinstance(user, (int, str)):
            try:
                attrs['user_id'] = Registration.objects.get(user_id=user)
            except Registration.DoesNotExist:
                raise serializers.ValidationError({'user_id': 'Invalid user_id'})
        return attrs

    def get_supplier_name(self, obj):
        """Get supplier name if supplier exists"""
        if obj.supplier_id:
            return obj.supplier_id.supplier_name
        return None

    def get_supplier_details(self, obj):
        """Get full supplier details if supplier exists"""
        if obj.supplier_id:
            return {
                'supplier_id': obj.supplier_id.supplier_id,
                'supplier_name': obj.supplier_id.supplier_name,
                'contact_person': obj.supplier_id.contact_person,
                'email': obj.supplier_id.email,
                'phone': obj.supplier_id.phone,
                'address': obj.supplier_id.address
            }
        return None

    @transaction.atomic
    def create(self, validated_data):
        print("DEBUG: ExpensesSerializer create method called!")
        expense = Expenses.objects.create(**validated_data)

        # Prepare detailed log data
        log_data = {
            'category': expense.category,
            'description': expense.description,
            'amount': str(expense.amount),
            'payment_method': expense.payment_method,
            'payment_status': expense.payment_status,
            'expense_date': expense.expense_date.isoformat() if expense.expense_date else None,
            'receipt_path': expense.receipt_path,
            'supplier_id': expense.supplier_id.supplier_id if expense.supplier_id else None,
        }
        
        # Write expense log using raw SQL
        with connection.cursor() as cursor:
            print(f"DEBUG: Attempting to log expense creation: {json.dumps(log_data)[:200]}...")
            cursor.execute("""
                INSERT INTO Expenses_Log (
                    expense_id, action, old_data, new_data, reason, user_id, changed_at
                ) VALUES (
                    %s, %s, %s, %s, %s, %s, CONVERT_TZ(NOW(), 'UTC', 'Asia/Kolkata')
                )
            """, [
                expense.expense_id,
                'INSERT',
                None,  # old_data
                json.dumps(log_data),
                'Created via API',
                validated_data['user_id'].id  # Use the primary key
            ])
            print("DEBUG: Successfully logged expense creation")

        return expense

    @transaction.atomic
    def update(self, instance, validated_data):
        """Update expense with logging."""
        print("DEBUG: ExpensesSerializer update method called!")
        
        # Keep snapshot for logs
        old_log_data = {
            'category': instance.category,
            'description': instance.description,
            'amount': str(instance.amount),
            'payment_method': instance.payment_method,
            'payment_status': instance.payment_status,
            'expense_date': instance.expense_date.isoformat() if instance.expense_date else None,
            'receipt_path': instance.receipt_path,
            'supplier_id': instance.supplier_id.supplier_id if instance.supplier_id else None,
        }

        # Update the instance
        for field, value in validated_data.items():
            setattr(instance, field, value)
        instance.save()

        # Prepare new log data
        new_log_data = {
            'category': instance.category,
            'description': instance.description,
            'amount': str(instance.amount),
            'payment_method': instance.payment_method,
            'payment_status': instance.payment_status,
            'expense_date': instance.expense_date.isoformat() if instance.expense_date else None,
            'receipt_path': instance.receipt_path,
            'supplier_id': instance.supplier_id.supplier_id if instance.supplier_id else None,
        }

        # Write update log using raw SQL
        with connection.cursor() as cursor:
            print(f"DEBUG: Attempting to log expense update: {json.dumps(new_log_data)[:200]}...")
            cursor.execute("""
                INSERT INTO Expenses_Log (
                    expense_id, action, old_data, new_data, reason, user_id, changed_at
                ) VALUES (
                    %s, %s, %s, %s, %s, %s, CONVERT_TZ(NOW(), 'UTC', 'Asia/Kolkata')
                )
            """, [
                instance.expense_id,
                'UPDATE',
                json.dumps(old_log_data),
                json.dumps(new_log_data),
                'Updated via API',
                validated_data.get('user_id', instance.user_id).id
            ])
            print("DEBUG: Successfully logged expense update")

        return instance


class ExpensesLogSerializer(serializers.ModelSerializer):
    user_name = serializers.SerializerMethodField(read_only=True)
    business_id = serializers.SerializerMethodField(read_only=True)
    expense_category = serializers.SerializerMethodField(read_only=True)
    
    class Meta:
        model = Expenses_Log
        fields = '__all__'
        read_only_fields = ['log_id', 'changed_at']
    
    def get_user_name(self, obj):
        """Get user name from Registration model"""
        if obj.user_id:
            return f"{obj.user_id.firstName} {obj.user_id.lastName}"
        return None
    
    def get_business_id(self, obj):
        """Get business_id through expense relationship"""
        if obj.expense_id and obj.expense_id.business_id:
            return obj.expense_id.business_id.business_id
        return None
    
    def get_expense_category(self, obj):
        """Get category from related expense"""
        if obj.expense_id:
            return obj.expense_id.category
        return None


class CounterSalesDetailsSerializer(serializers.ModelSerializer):
    business_id = serializers.SlugRelatedField(
        slug_field='business_id', 
        queryset=Business.objects.all(),
        required=True
    )
    uploaded_by = serializers.SlugRelatedField(
        slug_field='user_id', 
        queryset=Registration.objects.all(),
        required=False,
        allow_null=True
    )
    uploader_name = serializers.SerializerMethodField(read_only=True)
    
    class Meta:
        model = Counter_Sales_Details
        exclude = ['total_amount', 'grand_total']  # Exclude generated columns
        read_only_fields = ['id', 'created_at', 'updated_at', 'uploader_name']
    
    def validate(self, attrs):
        """Validate counter sales data"""
        # Ensure required relations exist
        business = attrs.get('business_id')
        if isinstance(business, str):
            try:
                attrs['business_id'] = Business.objects.get(pk=business)
            except Business.DoesNotExist:
                raise serializers.ValidationError({'business_id': 'Invalid business_id'})
        
        # Handle uploaded_by validation
        uploaded_by = attrs.get('uploaded_by')
        if uploaded_by and isinstance(uploaded_by, (int, str)):
            try:
                attrs['uploaded_by'] = Registration.objects.get(user_id=uploaded_by)
            except Registration.DoesNotExist:
                raise serializers.ValidationError({'uploaded_by': 'Invalid user_id'})
        
        # Validate quantity is positive
        quantity = attrs.get('quantity', 1)
        if quantity <= 0:
            raise serializers.ValidationError({'quantity': 'Quantity must be greater than 0'})
        
        # Validate price is positive
        price = attrs.get('price')
        if price and price <= 0:
            raise serializers.ValidationError({'price': 'Price must be greater than 0'})
        
        # Validate discount and tax are non-negative
        discount = attrs.get('discount', 0)
        if discount < 0:
            raise serializers.ValidationError({'discount': 'Discount cannot be negative'})
        
        tax = attrs.get('tax', 0)
        if tax < 0:
            raise serializers.ValidationError({'tax': 'Tax cannot be negative'})
        
        # Validate net_weight if provided
        net_weight = attrs.get('net_weight')
        if net_weight is not None and net_weight <= 0:
            raise serializers.ValidationError({'net_weight': 'Net weight must be greater than 0'})
        
        return attrs
    
    def get_uploader_name(self, obj):
        """Get uploader name from Registration model"""
        if obj.uploaded_by:
            return f"{obj.uploaded_by.firstName} {obj.uploaded_by.lastName}"
        return None
    
    @transaction.atomic
    def create(self, validated_data):
        """Create counter sales record using raw SQL to handle generated columns"""
        print("DEBUG: CounterSalesDetailsSerializer create method called!")
        
        # Use raw SQL to insert and avoid generated column issues
        with connection.cursor() as cursor:
            cursor.execute("""
                INSERT INTO counter_sales_details (
                    business_id, uploaded_by, bill_no, product_name, customer_name,
                    payment_method, quantity, net_weight, price, discount, tax,
                    sale_date, remarks, created_at, updated_at
                ) VALUES (
                    %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, CONVERT_TZ(NOW(), 'UTC', 'Asia/Kolkata'), CONVERT_TZ(NOW(), 'UTC', 'Asia/Kolkata')
                )
            """, [
                validated_data['business_id'].business_id,
                validated_data.get('uploaded_by').id if validated_data.get('uploaded_by') else None,
                validated_data.get('bill_no'),
                validated_data['product_name'],
                validated_data.get('customer_name'),
                validated_data.get('payment_method'),
                validated_data.get('quantity', 1),
                validated_data.get('net_weight'),
                validated_data['price'],
                validated_data.get('discount', 0.00),
                validated_data.get('tax', 0.00),
                validated_data['sale_date'],
                validated_data.get('remarks')
            ])
            
            # Get the created record ID
            sale_id = cursor.lastrowid
            
            # Fetch the complete record to return
            cursor.execute("""
                SELECT * FROM counter_sales_details WHERE id = %s
            """, [sale_id])
            
            # Create a Counter_Sales_Details instance for return
            sale_record = Counter_Sales_Details.objects.get(id=sale_id)
            
        print(f"DEBUG: Successfully created counter sale record #{sale_id}")
        return sale_record
    
    @transaction.atomic
    def update(self, instance, validated_data):
        """Update counter sales record using raw SQL to handle generated columns"""
        print("DEBUG: CounterSalesDetailsSerializer update method called!")
        
        # Update fields using raw SQL to avoid generated column issues
        update_fields = {}
        sql_parts = []
        sql_values = []
        
        for field, value in validated_data.items():
            if field == 'business_id':
                sql_parts.append("business_id = %s")
                sql_values.append(value.business_id)
                update_fields[field] = value
            elif field == 'uploaded_by':
                sql_parts.append("uploaded_by = %s")
                sql_values.append(value.id if value else None)
                update_fields[field] = value
            elif field in ['bill_no', 'product_name', 'customer_name', 'payment_method', 
                          'quantity', 'net_weight', 'price', 'discount', 'tax', 
                          'sale_date', 'remarks']:
                sql_parts.append(f"{field} = %s")
                sql_values.append(value)
                update_fields[field] = value
        
        if sql_parts:
            sql_parts.append("updated_at = CONVERT_TZ(NOW(), 'UTC', 'Asia/Kolkata')")
            sql_values.append(instance.id)
            
            with connection.cursor() as cursor:
                sql = f"UPDATE counter_sales_details SET {', '.join(sql_parts)} WHERE id = %s"
                cursor.execute(sql, sql_values)
            
            # Update the instance attributes
            for field, value in update_fields.items():
                setattr(instance, field, value)
        
        print(f"DEBUG: Successfully updated counter sale record #{instance.id}")
        return instance


class BusinessStaffSerializer(serializers.ModelSerializer):
    business_id = serializers.SlugRelatedField(
        slug_field='business_id', 
        queryset=Business.objects.all(),
        required=True
    )
    full_name = serializers.ReadOnlyField()
    role_display = serializers.CharField(source='get_role_display', read_only=True)
    current_salary = serializers.SerializerMethodField()
    
    class Meta:
        model = BusinessStaff
        fields = [
            'staff_id', 'business_id', 'first_name', 'last_name', 'full_name',
            'role', 'role_display', 'email', 'phone', 'join_date', 'status',
            'password_hash', 'current_salary', 'created_at', 'updated_at'
        ]
        read_only_fields = ['staff_id', 'created_at', 'updated_at']
        extra_kwargs = {
            'first_name': { 'required': False, 'allow_blank': True },
            'last_name': { 'required': False, 'allow_blank': True },
            'role': { 'required': False, 'allow_blank': True },
            'join_date': { 'required': False, 'allow_null': True },
        }
    
    def get_current_salary(self, obj):
        """Get the current salary from payment records (since we don't have salary structure table)"""
        try:
            print(f"[Serializer] === GETTING SALARY FROM PAYMENT RECORDS FOR STAFF {obj.staff_id} ===")
            
            # Use BusinessStaffSalaryPayments instead of BusinessStaffSalaries
            from .models import BusinessStaffSalaryPayments
            from datetime import date
            
            current_date = date.today()
            current_year = current_date.year
            current_month = current_date.month
            
            # Get the most recent payment record for this staff
            latest_payment = BusinessStaffSalaryPayments.objects.filter(
                staff_id=obj
            ).order_by('-year', '-month').first()
            
            print(f"[Serializer] Latest payment record: {latest_payment}")
            
            if not latest_payment:
                print(f"[Serializer] NO PAYMENT RECORD FOUND - returning None")
                return None
            
            # Calculate attendance for current month
            from .models import BusinessStaffAttendance
            from calendar import monthrange
            
            # Get working days in current month (excluding Sundays)
            _, days_in_month = monthrange(current_year, current_month)
            working_days = 0
            for day in range(1, days_in_month + 1):
                check_date = date(current_year, current_month, day)
                if check_date.weekday() != 6:  # 6 = Sunday
                    working_days += 1
            
            # Get attendance records for current month
            attendance_records = BusinessStaffAttendance.objects.filter(
                staff_id=obj,
                attendance_date__year=current_year,
                attendance_date__month=current_month,
                attendance_status__in=['Present', 'Half Day']
            )
            
            present_days = attendance_records.filter(attendance_status='Present').count()
            half_days = attendance_records.filter(attendance_status='Half Day').count()
            effective_days = present_days + (half_days * 0.5)
            
            # Calculate salary based on attendance
            base_amount = float(latest_payment.salary_amount)
            if working_days > 0:
                daily_rate = base_amount / working_days
                calculated_salary = daily_rate * effective_days
            else:
                calculated_salary = base_amount
            
            print(f"[Serializer] Calculation - Base: {base_amount}, Working days: {working_days}, Present: {present_days}, Half: {half_days}, Calculated: {calculated_salary}")
            
            return {
                'base_salary_amount': str(latest_payment.salary_amount),
                'calculated_salary_amount': f"{calculated_salary:.2f}",
                'working_days_in_month': working_days,
                'present_days': present_days,
                'half_days': half_days,
                'effective_days': effective_days,
                'daily_rate': f"{daily_rate:.2f}" if working_days > 0 else "0.00",
                'calculation_month': f"{current_year}-{current_month:02d}",
                'payment_year': latest_payment.year,
                'payment_month': latest_payment.month,
                'is_paid': latest_payment.is_paid,
                'amount_paid': str(latest_payment.salary_paid)
            }
        except Exception as e:
            print(f"[Serializer] Error getting salary from payment records for staff {obj.staff_id}: {e}")
            import traceback
            traceback.print_exc()
        return None
    
    def validate_email(self, value):
        """Validate email format and uniqueness if provided"""
        if value:
            # Check if email already exists for other staff members
            if self.instance:
                # Update case - exclude current instance
                if BusinessStaff.objects.filter(email=value).exclude(staff_id=self.instance.staff_id).exists():
                    raise serializers.ValidationError("A staff member with this email already exists.")
            else:
                # Create case
                if BusinessStaff.objects.filter(email=value).exists():
                    raise serializers.ValidationError("A staff member with this email already exists.")
        return value
    
    def validate_phone(self, value):
        """Validate phone number format if provided"""
        if value and not value.replace('+', '').replace('-', '').replace(' ', '').isdigit():
            raise serializers.ValidationError("Enter a valid phone number.")
        return value



class BusinessTaxInvoiceSerializer(serializers.ModelSerializer):
    business_id = serializers.SlugRelatedField(
        slug_field='business_id', queryset=Business.objects.all()
    )

    class Meta:
        model = BusinessTaxInvoice
        fields = '__all__'
        read_only_fields = ['invoice_id', 'created_at', 'updated_at']


# ==================== Staff Authentication Serializers ====================

class StaffLoginSerializer(serializers.Serializer):
    """Serializer for staff login with email/mobile and password"""
    login_identifier = serializers.CharField(max_length=255)  # email or mobile
    password = serializers.CharField(max_length=255, write_only=True)
    login_method = serializers.ChoiceField(choices=['PASSWORD', 'OTP'], default='PASSWORD')

    def validate_login_identifier(self, value):
        """Validate that the identifier exists and staff is active"""
        try:
            # Try to find by email first
            staff = BusinessStaff.objects.get(
                models.Q(email=value) | models.Q(mobile_number=value),
                status=True
            )
            self.staff_instance = staff
            return value
        except BusinessStaff.DoesNotExist:
            raise serializers.ValidationError("Invalid credentials or staff account not found")

    def validate_password(self, value):
        """Validate password against stored hash"""
        if hasattr(self, 'staff_instance') and self.staff_instance:
            if not self.staff_instance.password_hash:
                raise serializers.ValidationError("Password authentication not set up for this account")

            # Use Django's check_password to verify hashed password
            if not check_password(value, self.staff_instance.password_hash):
                raise serializers.ValidationError("Invalid password")
        return value

    def create(self, validated_data):
        """Create login response with staff data and navigation"""
        staff = self.staff_instance
        
        # Update last login
        staff.last_login = timezone.now()
        staff.login_method = validated_data['login_method']
        staff.save(update_fields=['last_login', 'login_method'])
        
        # Get navigation items based on staff's nav_items JSON
        nav_items_ids = staff.nav_items or []
        navigation_items = []
        
        if nav_items_ids:
            nav_queryset = RoleBasedNavItems.objects.filter(
                id__in=nav_items_ids,
                status=True,
                is_visible=True
            ).order_by('order_index')
            
            navigation_items = RoleBasedNavItemsSerializer(nav_queryset, many=True).data
        
        return {
            'staff_id': staff.staff_id,
            'business_id': staff.business_id.business_id,
            'staff_name': staff.full_name,
            'role': staff.role,
            'email': staff.email,
            # Return primary contact number: prefer mobile_number, fallback to phone
            'mobile_number': staff.mobile_number or staff.phone,
            'last_login': staff.last_login,
            'navigation_items': navigation_items,
            'login_method': validated_data['login_method']
        }


class StaffChangePasswordSerializer(serializers.Serializer):
    """Serializer for changing staff password (plain text, no hashing)"""
    login_identifier = serializers.CharField(max_length=255)
    new_password = serializers.CharField(max_length=255, write_only=True)

    def validate_login_identifier(self, value):
        try:
            staff = BusinessStaff.objects.get(
                models.Q(email=value) | models.Q(mobile_number=value),
                status=True
            )
            self.staff_instance = staff
            return value
        except BusinessStaff.DoesNotExist:
            raise serializers.ValidationError("Staff account not found")

    def validate(self, attrs):
        staff = getattr(self, 'staff_instance', None)
        if not staff:
            raise serializers.ValidationError("Staff account not found")

        new_password = attrs.get('new_password')

        # Plain-text comparison per requirement: new password must be different from current password
        if new_password == staff.password_hash:
            raise serializers.ValidationError({"new_password": "New password must be different from current password"})

        return attrs

    def create(self, validated_data):
        staff = self.staff_instance
        staff.password_hash = validated_data['new_password']
        staff.save(update_fields=['password_hash'])

        return {
            'message': 'Password updated successfully'
        }


class StaffOTPSendSerializer(serializers.Serializer):
    """Serializer for sending OTP to staff"""
    login_identifier = serializers.CharField(max_length=255)  # email or mobile

    def validate_login_identifier(self, value):
        """Validate that the identifier exists and staff is active"""
        try:
            staff = BusinessStaff.objects.get(
                models.Q(email=value) | models.Q(mobile_number=value),
                status=True
            )
            self.staff_instance = staff
            return value
        except BusinessStaff.DoesNotExist:
            raise serializers.ValidationError("Staff account not found")

    def create(self, validated_data):
        """Generate and save OTP"""
        staff = self.staff_instance
        
        # Generate 6-digit OTP via app utils and set 3 min expiry (as per email template)
        otp_code = app_generate_otp()
        otp_expires_at = timezone.now() + timedelta(minutes=3)
        
        # Save OTP
        staff.otp_code = otp_code
        staff.otp_expires_at = otp_expires_at
        staff.save(update_fields=['otp_code', 'otp_expires_at'])
        
        # Send OTP via Email and WhatsApp using kirazee_app.utils
        try:
            send_result = send_otp_dual_channel(
                email=(staff.email or ""),
                mobile_number=(staff.mobile_number or staff.phone or ""),
                otp_code=otp_code,
                template_type="LOGIN_OTP",
                user_name=staff.full_name,
            )
            logger.info(f"OTP dispatched for staff {staff.full_name}: {send_result}")
        except Exception as e:
            logger.error(f"Failed to dispatch OTP for staff {staff.full_name}: {e}")
        
        return {
            'message': 'OTP sent successfully',
            'expires_at': otp_expires_at,
            'staff_id': staff.staff_id
        }


class StaffOTPVerifySerializer(serializers.Serializer):
    """Serializer for verifying OTP and logging in"""
    login_identifier = serializers.CharField(max_length=255)
    otp_code = serializers.CharField(max_length=6)

    def validate(self, attrs):
        """Validate OTP and staff credentials"""
        login_identifier = attrs.get('login_identifier')
        otp_code = attrs.get('otp_code')
        
        try:
            staff = BusinessStaff.objects.get(
                models.Q(email=login_identifier) | models.Q(mobile_number=login_identifier),
                status=True
            )
            
            if not staff.otp_code:
                raise serializers.ValidationError("No OTP generated for this account")
            
            if staff.otp_code != otp_code:
                raise serializers.ValidationError("Invalid OTP")
            
            if timezone.now() > staff.otp_expires_at:
                raise serializers.ValidationError("OTP has expired")
            
            self.staff_instance = staff
            
        except BusinessStaff.DoesNotExist:
            raise serializers.ValidationError("Staff account not found")
        
        return attrs

    def create(self, validated_data):
        """Create login response after OTP verification"""
        staff = self.staff_instance
        
        # Clear OTP and update login info
        staff.otp_code = None
        staff.otp_expires_at = None
        staff.last_login = timezone.now()
        staff.login_method = 'OTP'
        staff.save(update_fields=['otp_code', 'otp_expires_at', 'last_login', 'login_method'])
        
        # Get navigation items
        nav_items_ids = staff.nav_items or []
        navigation_items = []
        
        if nav_items_ids:
            nav_queryset = RoleBasedNavItems.objects.filter(
                id__in=nav_items_ids,
                status=True,
                is_visible=True
            ).order_by('order_index')
            
            navigation_items = RoleBasedNavItemsSerializer(nav_queryset, many=True).data
        
        return {
            'staff_id': staff.staff_id,
            'business_id': staff.business_id.business_id,
            'staff_name': staff.full_name,
            'role': staff.role,
            'email': staff.email,
            # Return primary contact number: prefer mobile_number, fallback to phone
            'mobile_number': staff.mobile_number or staff.phone,
            'last_login': staff.last_login,
            'navigation_items': navigation_items,
            'login_method': 'OTP'
        }


class RoleBasedNavItemsSerializer(serializers.ModelSerializer):
    """Serializer for navigation items"""
    children = serializers.SerializerMethodField()

    class Meta:
        model = RoleBasedNavItems
        fields = ['id', 'nav_name', 'sub_nav', 'status', 'is_visible', 
                 'parent', 'order_index', 'icon', 'route_path', 'children']
        read_only_fields = ['id', 'created_at', 'updated_at']

    def get_children(self, obj):
        """Get child navigation items"""
        children = obj.children.filter(status=True, is_visible=True).order_by('order_index')
        return RoleBasedNavItemsSerializer(children, many=True).data


class StaffLoginLogsSerializer(serializers.ModelSerializer):
    """Serializer for staff login logs"""
    staff_name = serializers.CharField(source='staff_id.full_name', read_only=True)
    business_id = serializers.CharField(source='business_id.business_id', read_only=True)

    class Meta:
        model = StaffLoginLogs
        fields = ['log_id', 'staff_id', 'staff_name', 'business_id', 'login_method',
                 'login_time', 'ip_address', 'user_agent', 'login_status',
                 'failure_reason', 'logout_time', 'session_duration_minutes']
        read_only_fields = ['log_id', 'login_time', 'created_at']


class NavDisplayItemSerializer(serializers.ModelSerializer):
    """Serializer for navigation display items with premium flags and purchase status"""
    is_purchased = serializers.SerializerMethodField()
    price_display = serializers.SerializerMethodField()

    class Meta:
        model = NavDisplayItem
        fields = ['id', 'label', 'key', 'route_path', 'order_index', 'is_premium',
                 'price', 'price_display', 'is_new_feature', 'description', 'status',
                 'is_purchased', 'parent_item', 'children']
        read_only_fields = ['id', 'created_at', 'updated_at']

    def get_is_purchased(self, obj):
        """Check if this premium feature is purchased by the business"""
        if not obj.is_premium:
            return True  # Free features are always available
        
        request = self.context.get('request')
        if not request:
            return False
            
        business_id = request.query_params.get('business_id') or request.data.get('business_id')
        if not business_id:
            return False
            
        try:
            purchase = BusinessFeaturePurchase.objects.get(
                business_id=business_id,
                feature_key=obj.key,
                status='ACTIVE'
            )
            return purchase.is_active()
        except BusinessFeaturePurchase.DoesNotExist:
            return False

    def get_price_display(self, obj):
        """Format price for display"""
        if obj.is_premium and obj.price:
            return f"₹{obj.price}"
        return "Free"

    def get_children(self, obj):
        """Get child display items"""
        children = obj.children.filter(status=True).order_by('order_index')
        return NavDisplayItemSerializer(children, many=True, context=self.context).data


class BusinessFeaturePurchaseSerializer(serializers.ModelSerializer):
    """Serializer for business feature purchases"""
    feature_label = serializers.SerializerMethodField()
    feature_description = serializers.SerializerMethodField()
    days_remaining = serializers.SerializerMethodField()

    class Meta:
        model = BusinessFeaturePurchase
        fields = ['purchase_id', 'business_id', 'feature_key', 'feature_label',
                 'feature_description', 'purchased_at', 'expires_at', 'amount_paid',
                 'status', 'days_remaining']
        read_only_fields = ['purchase_id', 'purchased_at']

    def get_feature_label(self, obj):
        """Get feature label from NavDisplayItem"""
        try:
            feature = NavDisplayItem.objects.get(key=obj.feature_key)
            return feature.label
        except NavDisplayItem.DoesNotExist:
            return obj.feature_key

    def get_feature_description(self, obj):
        """Get feature description from NavDisplayItem"""
        try:
            feature = NavDisplayItem.objects.get(key=obj.feature_key)
            return feature.description
        except NavDisplayItem.DoesNotExist:
            return None

    def get_days_remaining(self, obj):
        """Calculate days remaining until expiry"""
        if not obj.expires_at:
            return None
        from django.utils import timezone
        delta = obj.expires_at - timezone.now()
        return max(0, delta.days)


class PurchaseRequisitionSerializer(serializers.ModelSerializer):
    user_id = serializers.SlugRelatedField(
        slug_field='user_id', queryset=Registration.objects.all()
    )
    business_id = serializers.SlugRelatedField(
        slug_field='business_id', queryset=Business.objects.all()
    )

    class Meta:
        model = PurchaseRequisition
        fields = [
            'purchase_req_id', 'requisition_number', 'business_id', 'user_id', 
            'item_name', 'quantity', 'unit', 'purpose', 'status', 'submitted_to_manager', 'request_date'
        ]
        read_only_fields = ['purchase_req_id', 'requisition_number', 'request_date']

    def create(self, validated_data):
        # Generate unique requisition number
        import uuid
        from django.utils import timezone
        requisition_number = f"REQ-{timezone.now().strftime('%y%m%d')}-{str(uuid.uuid4())[:3].upper()}"
        validated_data['requisition_number'] = requisition_number
        
        return PurchaseRequisition.objects.create(**validated_data)


class PurchaseRequisitionLogSerializer(serializers.ModelSerializer):
    action_by_name = serializers.SerializerMethodField()
    requisition_number = serializers.CharField(source='requisition.requisition_number', read_only=True)
    
    class Meta:
        model = PurchaseRequisitionLog
        fields = [
            'log_id', 'requisition', 'requisition_number', 'business_id', 
            'action', 'action_by', 'action_by_name', 'action_date', 'reason'
        ]
        read_only_fields = ['log_id', 'action_date']
    
    def get_action_by_name(self, obj):
        return f"{obj.action_by.firstName} {obj.action_by.lastName}" if obj.action_by else None

