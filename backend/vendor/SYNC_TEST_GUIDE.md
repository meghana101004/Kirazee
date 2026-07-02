# Vendor Product to Groceries Sync - Testing Guide

## Overview
When a vendor product is approved (is_approved=1, approval_status='approved'), it automatically syncs to the Groceries_Products table.

## What Gets Synced

### From vendor_products → Groceries_Products
- `product_id` (same ID)
- `business_id` → `business`
- `product_name` → `product_name`
- `brand_name` → `brand_name`
- `category_name` → `category` (creates category if doesn't exist)
- `sub_category_name` → `sub_category`
- `description` → `description`
- `item_placed_at` → `item_placed_at`
- `images[0]` → `main_image`
- `is_active` → `is_visible`

### From vendor_products → Groceries_ProductVariants_1
- Auto-generated `sku` from product_name
- `weight` → `net_weight`
- `weight_unit` → `net_weight_unit` (mapped: kg→kg, g→g, ltr→l, ml→ml, unit→pcs)
- `original_price` → `original_cost`
- `selling_price` → `selling_price`
- `gst_percentage` → `gst`
- `stock_quantity` → `stock`
- `is_active` → `is_active`

## Testing Steps

### 1. Create a Vendor Product

**Endpoint:** `POST /kirazee/vendor/{vendor_id}/products/`

**Request Body:**
```json
{
  "business_id": "R01",
  "product_name": "Test Product",
  "product_slug": "test-product",
  "category_name": "Groceries",
  "sub_category_name": "Vegetables",
  "original_price": 100.00,
  "selling_price": 90.00,
  "gst_percentage": 5.00,
  "weight": 1,
  "weight_unit": "kg",
  "stock_quantity": 50,
  "description": "Test product description",
  "images": ["https://example.com/image.jpg"]
}
```

**Expected Response:**
```json
{
  "product_id": 123,
  "approval_status": "pending",
  "is_approved": false,
  ...
}
```

### 2. Approve the Product

**Endpoint:** `PATCH /kirazee/vendor/{vendor_id}/products/{product_id}/approve/`

**Request Body:**
```json
{
  "approval_status": "approved"
}
```

**Expected Response:**
```json
{
  "message": "Product 123 has been approved. Sync: Product 123 successfully synced to Groceries_Products",
  "product_id": 123,
  "vendor_id": 6,
  "approval_status": "approved",
  "is_approved": true
}
```

### 3. Verify Sync in Database

**Check Groceries_Products:**
```sql
SELECT * FROM Groceries_Products WHERE product_id = 123;
```

**Check Groceries_ProductVariants_1:**
```sql
SELECT * FROM Groceries_ProductVariants_1 WHERE product_id = 123;
```

**Check universal_Categories:**
```sql
SELECT * FROM universal_Categories WHERE category_name = 'Groceries';
```

## Console Logs to Watch For

When approval happens, you should see:
```
Post-save signal for product 123: is_approved=True, approval_status=approved, created=False, approval_changed=True, was_approved=False
Starting sync for product 123 to Groceries_Products
Found existing category: Groceries with ID 5
Creating Groceries_Products entry for product 123
Created Groceries_Products entry for product 123
Created variant for product 123 with SKU test_product_1kg
✓ Successfully synced vendor product 123 to Groceries_Products
✓ Vendor product 123 synced to Groceries_Products
```

## Troubleshooting

### Signal Not Triggering
- Ensure `vendor` app is in INSTALLED_APPS ✓
- Ensure `vendor/apps.py` has `ready()` method that imports models ✓
- Restart Django server after code changes

### Category Not Found Error
- The system automatically creates categories in universal_Categories table
- Check if category_name is provided in the vendor product

### Business Not Found Error
- Ensure the business_id exists in the businesses table
- Verify business_id matches exactly (case-sensitive)

### Duplicate Product Error
- Product already exists in Groceries_Products
- Check if product_id already exists before approval

## API Endpoints Summary

| Method | Endpoint | Purpose |
|--------|----------|---------|
| POST | `/kirazee/vendor/{vendor_id}/products/` | Create vendor product |
| GET | `/kirazee/vendor/{vendor_id}/products/` | List all vendor products |
| GET | `/kirazee/vendor/{vendor_id}/products/{product_id}/` | Get single product |
| PUT | `/kirazee/vendor/{vendor_id}/products/{product_id}/` | Full update product |
| PATCH | `/kirazee/vendor/{vendor_id}/products/{product_id}/` | Partial update product |
| DELETE | `/kirazee/vendor/{vendor_id}/products/{product_id}/` | Soft delete product |
| PATCH | `/kirazee/vendor/{vendor_id}/products/{product_id}/approve/` | Approve/reject product |

## Notes

- Product IDs are shared between vendor_products and Groceries_Products tables
- The system uses GREATEST() SQL function to get the next available ID from both tables
- Sync happens automatically via Django signals (post_save)
- Transaction rollback ensures data consistency if sync fails
- All sync operations are logged for debugging
