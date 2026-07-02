# PATCH Method Test Guide

## Update Product by user_id

**URL:**
```
PATCH https://dev-kirazee.zdotapps.in/kirazee/vendor/user/14948/products/157391/
```

**Method:** PATCH

**Headers:**
```
Content-Type: application/json
```

**Request Body Examples:**

### Example 1: Update Price and Stock
```json
{
  "selling_price": 95.00,
  "stock_quantity": 200
}
```

### Example 2: Update Product Details
```json
{
  "product_name": "Updated Product Name",
  "description": "Updated description",
  "brand_name": "New Brand"
}
```

### Example 3: Update Images
```json
{
  "images": {
    "image1": "https://example.com/new-image1.jpg",
    "image2": "https://example.com/new-image2.jpg",
    "image3": "https://example.com/new-image3.jpg"
  }
}
```

### Example 4: Update Stock Status
```json
{
  "is_active": true,
  "stock_status": "in_stock"
}
```

### Example 5: Update Multiple Fields
```json
{
  "selling_price": 85.00,
  "stock_quantity": 150,
  "description": "New description with updated price",
  "gst_percentage": 18.0,
  "weight": 600,
  "weight_unit": "g"
}
```

---

## Expected Response (200 OK)

```json
{
  "product_id": 157391,
  "vendor_id": 1,
  "user_id": 14948,
  "business_id": "R01",
  "product_name": "Updated Product Name",
  "product_slug": "updated-product-name",
  "product_type": "physical",
  "description": "Updated description",
  "short_description": "Short desc",
  "brand_name": "New Brand",
  "base_sku": "SKU123",
  "hsn_code": "12345678",
  "item_placed_at": "Shelf A",
  "category_name": "Electronics",
  "category_id": 1,
  "sub_category_name": "Mobile Phones",
  "sub_category_id": 10,
  "original_price": "100.00",
  "selling_price": "85.00",
  "gst_percentage": "18.0",
  "weight": "600",
  "weight_unit": "g",
  "length_cm": "10.0",
  "width_cm": "5.0",
  "height_cm": "2.0",
  "condition_new": true,
  "is_returnable": true,
  "return_days": 7,
  "images": {
    "image1": "https://example.com/new-image1.jpg",
    "image2": "https://example.com/new-image2.jpg"
  },
  "media_url": "https://dev-kirazee.zdotapps.in/media/",
  "variants": null,
  "inventory": null,
  "attributes": null,
  "sizes_available": ["S", "M", "L"],
  "colors_available": {
    "S": ["Red", "Blue"],
    "M": ["Red", "Blue", "Green"],
    "L": ["Black"]
  },
  "has_variants": true,
  "manage_stock": true,
  "stock_quantity": 150,
  "stock_status": "in_stock",
  "is_active": true,
  "is_approved": false,
  "approval_status": "pending",
  "created_at": "2026-02-28T10:00:00Z",
  "updated_at": "2026-02-28T11:30:00Z"
}
```

---

## Error Responses

### 404 Not Found - Vendor Not Found
```json
{
  "error": "Vendor not found"
}
```

### 404 Not Found - Product Not Found
```json
{
  "error": "Product not found"
}
```

### 400 Bad Request - Validation Error
```json
{
  "errors": {
    "selling_price": ["A valid number is required."],
    "stock_quantity": ["A valid integer is required."]
  }
}
```

### 400 Bad Request - Missing Parameters
```json
{
  "error": "Either vendor_id or user_id is required"
}
```

---

## Key Features

1. **Partial Update** - Only send the fields you want to update
2. **Supports both vendor_id and user_id** - Use either parameter
3. **Response includes both IDs** - Returns both vendor_id and user_id
4. **Validation** - All fields are validated before update
5. **Vendor ID Protection** - vendor_id cannot be changed via PATCH

---

## Alternative URLs

### By vendor_id:
```
PATCH https://dev-kirazee.zdotapps.in/kirazee/vendor/{vendor_id}/products/{product_id}/
```

Example:
```
PATCH https://dev-kirazee.zdotapps.in/kirazee/vendor/1/products/157391/
```

### By user_id:
```
PATCH https://dev-kirazee.zdotapps.in/kirazee/vendor/user/{user_id}/products/{product_id}/
```

Example:
```
PATCH https://dev-kirazee.zdotapps.in/kirazee/vendor/user/14948/products/157391/
```

---

## Notes

- PATCH allows partial updates (only send fields you want to change)
- PUT requires all fields (full update)
- Both methods now support vendor_id and user_id
- Product must belong to the specified vendor
- Changes are saved immediately
- Updated timestamp is automatically updated
