# Vendor App - Available APIs

## Base URL
```
http://localhost:8000/kirazee/vendor/
```

---

## Available Endpoints

### 1. Vendor Registration
```
POST /kirazee/vendor/register/
```
Create a new vendor account with user registration and vendor profile.

---

### 2. Get Vendor Profile (by vendor_id)
```
GET /kirazee/vendor/<vendor_id>/profile/
```
Retrieve detailed vendor profile information by vendor ID.

---

### 3. Get Vendor Profile (by user_id)
```
GET /kirazee/vendor/user/<user_id>/profile/
```
Retrieve detailed vendor profile information by user ID.

---

### 4. Update Vendor Profile (Full Update)
```
PUT /kirazee/vendor/<vendor_id>/profile/
PUT /kirazee/vendor/user/<user_id>/profile/
```
Full update of vendor profile (all fields required).

---

### 5. Update Vendor Profile (Partial Update)
```
PATCH /kirazee/vendor/<vendor_id>/profile/
PATCH /kirazee/vendor/user/<user_id>/profile/
```
Partial update of vendor profile (only changed fields required).

---

### 6. Create Vendor Product
```
POST /kirazee/vendor/<vendor_id>/products/
```
Create a new product for a specific vendor.

---

### 7. Get All Vendor Products
```
GET /kirazee/vendor/<vendor_id>/products/
```
Retrieve all products for a specific vendor.

---

### 8. Get Single Product
```
GET /kirazee/vendor/<vendor_id>/products/<product_id>/
```
Retrieve detailed information for a specific product.

---

### 9. Update Product (Full Update)
```
PUT /kirazee/vendor/<vendor_id>/products/<product_id>/
```
Full update of product information.

---

### 10. Update Product (Partial Update)
```
PATCH /kirazee/vendor/<vendor_id>/products/<product_id>/
```
Partial update of product information.

---

### 11. Delete Product
```
DELETE /kirazee/vendor/<vendor_id>/products/<product_id>/
```
Delete a specific product.

---

### 12. Bulk Upload Products
```
POST /kirazee/vendor/<vendor_id>/products/bulk/
```
Upload multiple products at once for a vendor.

---

### 13. Approve/Reject Product (Admin)
```
POST /kirazee/vendor/<business_id>/<businessType>/<vendor_id>/products/<product_id>/approve/
```
Admin endpoint to approve or reject vendor products. Approved products are synced to Groceries_Products.

---

### 14. Check Product Sync Status
```
GET /kirazee/vendor/<vendor_id>/products/<product_id>/sync/
```
Check if a vendor product is synced to Groceries_Products table.

---

### 15. Approve/Reject Vendor (Admin)
```
POST /kirazee/vendor/<vendor_id>/approve/
```
Admin endpoint to approve or reject vendor profiles.

---

### 16. List Pending Vendors (Admin)
```
GET /kirazee/vendor/approval/
```
Admin endpoint to list all pending vendor approvals.

---

## Notes

- All endpoints require proper authentication (implementation dependent)
- Admin endpoints (#13, #15, #16) require admin privileges
- Products can only be added by approved vendors
- Approved products are automatically synced to Groceries_Products table
- Vendor profiles include complete user information

---

## Status

✅ Backend is clean and working
✅ All list vendors API code removed
✅ Documentation files cleaned up
✅ No syntax errors
✅ Ready for use
