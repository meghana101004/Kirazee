# Vendor Product API Endpoints

## Updated: Now supports both vendor_id and user_id

---

## Add Product (POST)

### Option 1: Using vendor_id
```
POST http://localhost:8000/kirazee/vendor/{vendor_id}/products/
```

**Example:**
```
POST http://localhost:8000/kirazee/vendor/1/products/
```

### Option 2: Using user_id
```
POST http://localhost:8000/kirazee/vendor/user/{user_id}/products/
```

**Example:**
```
POST http://localhost:8000/kirazee/vendor/user/123/products/
```

**Request Body (JSON):**
```json
{
  "business_id": "R01",
  "product_name": "Sample Product",
  "original_price": 100.00,
  "selling_price": 90.00,
  "category_name": "Electronics",
  "sub_category_name": "Mobile Phones",
  "description": "Product description",
  "brand_name": "Brand Name",
  "gst_percentage": 18.0,
  "weight": 500,
  "weight_unit": "g",
  "stock_quantity": 100,
  "images": {
    "image1": "https://example.com/image1.jpg",
    "image2": "https://example.com/image2.jpg"
  }
}
```

**Response (201 Created):**
```json
{
  "product_id": 1,
  "vendor_id": 1,
  "user_id": 123,
  "business_id": "R01",
  "product_name": "Sample Product",
  "product_slug": "sample-product",
  "original_price": "100.00",
  "selling_price": "90.00",
  "is_active": true,
  "is_approved": false,
  "approval_status": "pending",
  "created_at": "2026-02-28T10:00:00Z",
  "updated_at": "2026-02-28T10:00:00Z"
}
```

---

## Get Products (GET)

### Get All Products by vendor_id
```
GET http://localhost:8000/kirazee/vendor/{vendor_id}/products/
```

**Example:**
```
GET http://localhost:8000/kirazee/vendor/1/products/
```

### Get All Products by user_id
```
GET http://localhost:8000/kirazee/vendor/user/{user_id}/products/
```

**Example:**
```
GET http://localhost:8000/kirazee/vendor/user/123/products/
```

**Response (200 OK):**
```json
{
  "vendor_id": 1,
  "user_id": 123,
  "total_products": 2,
  "products": [
    {
      "product_id": 1,
      "vendor_id": 1,
      "user_id": 123,
      "business_id": "R01",
      "product_name": "Sample Product",
      "product_slug": "sample-product",
      "original_price": "100.00",
      "selling_price": "90.00",
      "stock_quantity": 100,
      "is_active": true,
      "is_approved": false,
      "approval_status": "pending",
      "created_at": "2026-02-28T10:00:00Z",
      "updated_at": "2026-02-28T10:00:00Z"
    }
  ]
}
```

---

## Get Single Product (GET)

### Get Product by vendor_id
```
GET http://localhost:8000/kirazee/vendor/{vendor_id}/products/{product_id}/
```

**Example:**
```
GET http://localhost:8000/kirazee/vendor/1/products/1/
```

### Get Product by user_id
```
GET http://localhost:8000/kirazee/vendor/user/{user_id}/products/{product_id}/
```

**Example:**
```
GET http://localhost:8000/kirazee/vendor/user/123/products/1/
```

**Response (200 OK):**
```json
{
  "product_id": 1,
  "vendor_id": 1,
  "user_id": 123,
  "business_id": "R01",
  "product_name": "Sample Product",
  "product_slug": "sample-product",
  "product_type": "physical",
  "description": "Product description",
  "brand_name": "Brand Name",
  "category_name": "Electronics",
  "original_price": "100.00",
  "selling_price": "90.00",
  "gst_percentage": "18.0",
  "weight": "500",
  "weight_unit": "g",
  "images": {
    "image1": "https://example.com/image1.jpg",
    "image2": "https://example.com/image2.jpg"
  },
  "stock_quantity": 100,
  "is_active": true,
  "is_approved": false,
  "approval_status": "pending",
  "created_at": "2026-02-28T10:00:00Z",
  "updated_at": "2026-02-28T10:00:00Z"
}
```

---

## Update Product (PUT/PATCH)

### Update by vendor_id
```
PUT http://localhost:8000/kirazee/vendor/{vendor_id}/products/{product_id}/
PATCH http://localhost:8000/kirazee/vendor/{vendor_id}/products/{product_id}/
```

### Update by user_id
```
PUT http://localhost:8000/kirazee/vendor/user/{user_id}/products/{product_id}/
PATCH http://localhost:8000/kirazee/vendor/user/{user_id}/products/{product_id}/
```

**Request Body (JSON):**
```json
{
  "selling_price": 85.00,
  "stock_quantity": 150
}
```

---

## Delete Product (DELETE)

### Delete by vendor_id
```
DELETE http://localhost:8000/kirazee/vendor/{vendor_id}/products/{product_id}/
```

### Delete by user_id
```
DELETE http://localhost:8000/kirazee/vendor/user/{user_id}/products/{product_id}/
```

**Response (200 OK):**
```json
{
  "message": "Product deleted successfully",
  "product_id": 1,
  "vendor_id": 1,
  "is_active": false
}
```

---

## Key Changes:

1. **Both vendor_id and user_id supported** - You can now use either parameter to manage products
2. **Response includes both IDs** - All responses now include both `vendor_id` and `user_id`
3. **New URL patterns** - Added `/user/{user_id}/products/` endpoints alongside existing `/vendor/{vendor_id}/products/` endpoints
4. **Backward compatible** - Existing vendor_id endpoints still work as before

---

## Notes:

- The vendor must be approved (`is_vendor_approved = true`) before adding products
- Products are created with `approval_status = 'pending'` by default
- Soft delete is used (sets `is_active = false`)
- Replace `localhost:8000` with your actual server URL


---

## Bulk Upload Products (POST)

### Option 1: Using vendor_id
```
POST http://localhost:8000/kirazee/vendor/{vendor_id}/products/bulk/
```

**Example:**
```
POST http://localhost:8000/kirazee/vendor/1/products/bulk/
```

### Option 2: Using user_id
```
POST http://localhost:8000/kirazee/vendor/user/{user_id}/products/bulk/
```

**Example:**
```
POST http://localhost:8000/kirazee/vendor/user/14948/products/bulk/
```

**Request Body (JSON):**
```json
{
  "products": [
    {
      "business_id": "R01",
      "product_name": "Product 1",
      "original_price": 100.00,
      "selling_price": 90.00,
      "category_name": "Electronics",
      "sub_category_name": "Mobile Phones",
      "description": "Product 1 description",
      "brand_name": "Brand A",
      "gst_percentage": 18.0,
      "weight": 500,
      "weight_unit": "g",
      "stock_quantity": 100
    },
    {
      "business_id": "R01",
      "product_name": "Product 2",
      "original_price": 200.00,
      "selling_price": 180.00,
      "category_name": "Electronics",
      "sub_category_name": "Laptops",
      "description": "Product 2 description",
      "brand_name": "Brand B",
      "gst_percentage": 18.0,
      "weight": 2000,
      "weight_unit": "g",
      "stock_quantity": 50
    }
  ]
}
```

**Response (201 Created):**
```json
{
  "success": true,
  "message": "Successfully created 2 products",
  "vendor_id": 1,
  "user_id": 14948,
  "created_count": 2,
  "failed_count": 0,
  "created_products": [
    {
      "index": 0,
      "product_id": 101,
      "product_name": "Product 1",
      "product_slug": "product-1",
      "status": "success"
    },
    {
      "index": 1,
      "product_id": 102,
      "product_name": "Product 2",
      "product_slug": "product-2",
      "status": "success"
    }
  ]
}
```

**Error Response (400 Bad Request) - Validation Failed:**
```json
{
  "success": false,
  "message": "Validation failed for some products. No products were created.",
  "created_count": 0,
  "failed_count": 1,
  "failed_products": [
    {
      "index": 0,
      "product_name": "Product 1",
      "errors": {
        "original_price": ["This field is required."]
      },
      "status": "validation_failed"
    }
  ]
}
```

**Bulk Upload Rules:**
- Maximum 100 products per bulk upload
- All products must pass validation before any are created (atomic transaction)
- If any product fails validation, no products are created
- Vendor must be approved before bulk uploading products
- All products are created with `approval_status = 'pending'`

---

## Complete URL List

### By vendor_id:
- `POST /kirazee/vendor/{vendor_id}/products/` - Add single product
- `GET /kirazee/vendor/{vendor_id}/products/` - Get all products
- `GET /kirazee/vendor/{vendor_id}/products/{product_id}/` - Get single product
- `PUT /kirazee/vendor/{vendor_id}/products/{product_id}/` - Update product (full)
- `PATCH /kirazee/vendor/{vendor_id}/products/{product_id}/` - Update product (partial)
- `DELETE /kirazee/vendor/{vendor_id}/products/{product_id}/` - Delete product
- `POST /kirazee/vendor/{vendor_id}/products/bulk/` - Bulk upload products

### By user_id:
- `POST /kirazee/vendor/user/{user_id}/products/` - Add single product
- `GET /kirazee/vendor/user/{user_id}/products/` - Get all products
- `GET /kirazee/vendor/user/{user_id}/products/{product_id}/` - Get single product
- `PUT /kirazee/vendor/user/{user_id}/products/{product_id}/` - Update product (full)
- `PATCH /kirazee/vendor/user/{user_id}/products/{product_id}/` - Update product (partial)
- `DELETE /kirazee/vendor/user/{user_id}/products/{product_id}/` - Delete product
- `POST /kirazee/vendor/user/{user_id}/products/bulk/` - Bulk upload products
