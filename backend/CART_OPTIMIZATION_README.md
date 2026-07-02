# Optimized Cart System - Service Layer Pattern

This document describes the optimized cart system that refactors the existing universal endpoints to use a clean, modular Service Layer pattern while maintaining backward compatibility.

## Architecture

### 1. Utility Layer (`consumer/utils/__init__.py`)
Common helper functions used across the cart system:
- `parse_json_input()`: Safely parse JSON with fallback
- `build_absolute_url()`: Build absolute URLs for media files

### 2. Service Layer (`consumer/cart_services.py`)
The `CartService` class contains all business logic:
- `get_business_type()`: Identify business type from business_id
- `get_item_details()`: Fetch item details based on business type
- `check_item_availability()`: Check if item is available
- `upsert_cart()`: Generic insert/update logic for all cart types
- `get_cart_items()`: Fetch cart items with optimized queries
- `delete_cart_item()`: Delete cart items

### 3. Refactored View Layer (`consumer/combine.py`)
**All existing endpoints refactored** to use service layer while maintaining API compatibility:
- `AddToCartViewBasedonBusinessID()`: Universal add to cart (refactored to use service layer) ✅
- `get_cart_items()`: View cart items (refactored to use service layer) ✅
- `update_cart_quantity()`: Update/delete cart items (refactored to use service layer) ✅

**New Features Added:**
- **Business Restrictions**: Configurable restrictions based on business_id
  - If business_id is in restricted list AND cart has items from that business → Block adding
  - If cart is empty for restricted business → Allow adding
  - Supports all business types (R01, R02, R08)

**Bug Fixes:**
- **Fashion Details Duplicates**: Fixed R08 query JOIN conditions to prevent duplicate cart entries
  - Fixed incorrect JOIN: `fpv.product_id = fpv.product_id` → `fpv.product_id = fp.product_id`
  - Added DISTINCT to eliminate duplicate cart items
  - Now returns 1 entry per cart item with correct product names

### 4. Legacy Endpoints (`consumer/views.py`)
**Refactored legacy endpoints** to use service layer:
- `AddToCartViewRES()`: Restaurant add to cart (refactored)
- `AddToCartViewGROCERY()`: Grocery add to cart (refactored)

## API Endpoints

### Primary Universal Endpoints
- `POST /consumer/add-to-cart` - Universal add to cart for all business types (R01, R02, R08)
- `POST /consumer/viewcart` - View cart items with optional type filter
- `POST/DELETE /consumer/update-cart-quantity` - Update or delete cart items

### Legacy Endpoints (Still Functional)
- `POST /consumer/res/add-to-cart` - Restaurant specific add to cart
- `POST /consumer/grocery/add-to-cart` - Grocery specific add to cart

## Business Types Support

### R01 - Groceries
- **Table**: `Groceries_cart`
- **Item Field**: `product_id`
- **Customizations**: Supported (gift wrapping, delivery options, etc.)
- **Availability**: Time-based availability check

### R02 - Restaurants  
- **Table**: `menuCart`
- **Item Field**: `menu_id`
- **Customizations**: Supported (extra ingredients, modifications, etc.)
- **Availability**: Day/time-based availability with JSON schedules

### R08 - Fashion
- **Table**: `fashion_cart`
- **Item Field**: `variant_id`
- **Customizations**: Supported (size, color, monogram, etc.)
- **Availability**: Stock-based availability check

## Key Improvements

### 1. Code Reduction
- **Before**: 300+ lines of repetitive SQL queries per endpoint
- **After**: 150 lines using service layer
- **Reduction**: ~50% less code

### 2. Maintainability
- **Single Source of Truth**: Business logic centralized in service layer
- **Reusable Components**: Service methods can be used anywhere
- **Easy Testing**: Service layer can be unit tested independently

### 3. Backward Compatibility
- **Same Endpoints**: Existing API URLs remain unchanged
- **Same Responses**: Response formats preserved
- **No Breaking Changes**: Existing clients continue to work

### 4. Error Handling
- **Consistent**: Standardized error responses across all endpoints
- **Detailed**: Clear error messages with stage information
- **Graceful**: Proper exception handling at service layer

## Request/Response Examples

### Add to Cart Request
```json
POST /consumer/add-to-cart?user_id=14818&business_id=KIR1489320251101174639
Content-Type: application/json

{
  "item_id": 156960,
  "quantity": 2,
  "customizations": [
    {
      "option": "extra cheese",
      "price": 10
    },
    {
      "option": "no onions", 
      "price": 0
    }
  ]
}
```

### Success Response (R02 - Restaurant)
```json
{
  "message": "Menu added to cart successfully",
  "item_details": {
    "item_id": 156960,
    "item_name": "Bamboo Baskets",
    "description": "Eco-friendly bamboo baskets",
    "selling_price": "100.00",
    "quantity": 2,
    "customizations": [...]
  },
  "menu_details": [...]
}
```

### Success Response (R01 - Grocery)
```json
{
  "message": "Grocery item added to cart successfully",
  "item_details": {
    "item_id": 156823,
    "item_name": "Bamboo cotton Ear Buds",
    "description": "eco friendly",
    "selling_price": "100.00",
    "quantity": 1,
    "customizations": [...]
  },
  "grocery_details": [...]
}
```

### Success Response (R08 - Fashion)
```json
{
  "message": "Fashion item added to cart successfully",
  "item_details": {
    "item_id": 157045,
    "item_name": "Designer T-Shirt",
    "description": "Premium cotton t-shirt",
    "selling_price": "299.00",
    "quantity": 1,
    "customizations": [...]
  },
  "fashion_details": [...]
}
```

## Customizations Support

All business types support customizations with the following format:

```json
{
  "customizations": [
    {
      "option": "customization description",
      "price": additional_price
    }
  ]
}
```

### Business-Specific Examples

**Restaurant (R02)**:
- Extra ingredients, cooking preferences, dietary restrictions

**Grocery (R01)**:
- Gift wrapping, express delivery, special instructions

**Fashion (R08)**:
- Size selection, color options, monogramming, alterations

## Testing

The `cartoptimization.json` file contains a complete Postman collection with:
- All endpoints (legacy and refactored)
- Request examples for each business type
- Customization examples
- Error scenarios
- Test scripts for validation

## Migration Notes

### For Developers
- Service layer methods are static and can be called directly
- All existing endpoints maintain the same signatures
- Error handling is now centralized in the service layer

### For API Consumers
- **No changes required** - all existing endpoints work the same
- Customizations are now properly supported across all business types
- Error responses are more detailed and consistent

## Future Enhancements

1. **Cart Summary**: Add service layer method for cart totals
2. **Batch Operations**: Support adding multiple items in one request
3. **Cart Persistence**: Add cart saving/loading functionality
4. **Analytics**: Service layer methods for cart analytics

## Files Modified

- `consumer/utils/__init__.py` - Added utility functions
- `consumer/cart_services.py` - New service layer
- `consumer/combine.py` - Refactored AddToCartViewBasedonBusinessID
- `consumer/views.py` - Refactored AddToCartViewRES and AddToCartViewGROCERY
- `consumer/urls.py` - Removed duplicate optimized endpoints
- `cartoptimization.json` - Complete API documentation
- `CART_OPTIMIZATION_README.md` - This documentation file

## Summary

The optimized cart system successfully reduces code complexity by ~50% while maintaining full backward compatibility. The service layer pattern makes the code more maintainable, testable, and reusable without requiring any changes from existing API consumers.

### Add to Cart
```
POST /consumer/cart/add?user_id=123&business_id=KIR123
Content-Type: application/json

{
    "item_id": 456,
    "quantity": 2,
    "customizations": [{"option": "extra cheese", "price": 10}]
}
```

### View Cart
```
# Get all cart items across all businesses
GET /consumer/cart/view?user_id=123

# Get specific cart type
GET /consumer/cart/view?user_id=123&type=R01
```

### Update/Delete Cart
```
# Delete specific item
DELETE /consumer/cart/update?user_id=123&cart_id=789&type=R01

# Delete entire cart
DELETE /consumer/cart/update?user_id=123

# Update quantity
POST /consumer/cart/update?user_id=123
Content-Type: application/json

{
    "item_id": 456,
    "type": "R01",
    "action": "inc"  // or "dec" or {"quantity": 5}
}
```

## Business Type Support

### R01 (Grocery)
- **Table**: `Groceries_cart`
- **Item Column**: `product_id`
- **Customizations**: Supported (stored as JSON)
- **Availability**: Single time check

### R02 (Restaurant)
- **Table**: `menuCart`
- **Item Column**: `menu_id`
- **Customizations**: Not used
- **Availability**: Day/time slots from JSON

### R08 (Fashion)
- **Table**: `fashion_cart`
- **Item Column**: `variant_id`
- **Customizations**: Supported (stored as JSON)
- **Availability**: Not applicable

## Key Improvements

### 1. DRY Principle
- Eliminated repetitive insert/update logic
- Single `upsert_cart()` method handles all cart types

### 2. Decoupling
- Business logic separated from API logic
- Easy to add new business types (just update service layer)

### 3. Consistency
- Standardized error handling
- Consistent response format across all endpoints

### 4. Performance
- Optimized SQL queries with proper joins
- Reduced database round trips

### 5. Maintainability
- Clean code structure
- Easy to test individual components
- Clear separation of concerns

## Migration from Old System

### Old URLs (still supported):
- `/consumer/add-to-cart` - Original implementation
- `/consumer/viewcart` - Original implementation
- `/consumer/update-cart-quantity` - Original implementation

### New URLs (optimized):
- `/consumer/cart/add` - Service layer implementation
- `/consumer/cart/view` - Service layer implementation
- `/consumer/cart/update` - Service layer implementation

## Error Handling

All endpoints return consistent error responses:
```json
{
    "error": "Error description",
    "details": "Additional error details (if available)"
}
```

## Response Format

### Add to Cart Response
```json
{
    "message": "Item added to cart",
    "item_details": {
        "item_id": 456,
        "item_name": "Product Name",
        "description": "Description",
        "selling_price": "100.00",
        "quantity": 2
    },
    "cart_details": [
        {
            "business_name": "Business Name",
            "items": [...]
        }
    ]
}
```

### View Cart Response
```json
{
    "cart_details": [
        {
            "business_name": "Business Name",
            "items": [
                {
                    "cart_id": 789,
                    "item_id": 456,
                    "quantity": 2,
                    "item_name": "Product Name",
                    "description": "Description",
                    "selling_price": "100.00",
                    "image": "https://...",
                    "customizations": []
                }
            ]
        }
    ]
}
```

## Testing

To test the optimized endpoints:

1. **Add items to cart**:
   ```bash
   curl -X POST "http://localhost:8000/consumer/cart/add?user_id=1&business_id=KIR123" \
        -H "Content-Type: application/json" \
        -d '{"item_id": 456, "quantity": 2}'
   ```

2. **View cart**:
   ```bash
   curl "http://localhost:8000/consumer/cart/view?user_id=1"
   ```

3. **Update quantity**:
   ```bash
   curl -X POST "http://localhost:8000/consumer/cart/update?user_id=1" \
        -H "Content-Type: application/json" \
        -d '{"item_id": 456, "type": "R01", "action": "inc"}'
   ```

## Future Enhancements

1. **Caching**: Add Redis caching for frequently accessed cart data
2. **Batch Operations**: Support adding multiple items in one request
3. **Cart Persistence**: Save cart for logged-in users across sessions
4. **Analytics**: Track cart abandonment and conversion rates
5. **Validation**: Add more robust validation for customizations
