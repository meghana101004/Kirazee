"""
Test script to verify vendor product sync functionality
Run this in Django shell: python manage.py shell < vendor/test_sync.py
"""

print("=" * 80)
print("VENDOR PRODUCT SYNC TEST")
print("=" * 80)

# Step 1: Check if vendor app is loaded
print("\n[1] Checking if vendor app is loaded...")
from django.apps import apps
vendor_loaded = apps.is_installed('vendor')
print(f"   Vendor app loaded: {vendor_loaded}")
if not vendor_loaded:
    print("   ❌ ERROR: Vendor app not in INSTALLED_APPS!")
    exit(1)
else:
    print("   ✅ OK")

# Step 2: Check if signals are registered
print("\n[2] Checking if signals are registered...")
from vendor.models import VendorProduct
from django.db.models.signals import post_save, pre_save
post_save_registered = post_save.has_listeners(VendorProduct)
pre_save_registered = pre_save.has_listeners(VendorProduct)
print(f"   Post-save signal registered: {post_save_registered}")
print(f"   Pre-save signal registered: {pre_save_registered}")
if not post_save_registered or not pre_save_registered:
    print("   ❌ ERROR: Signals not registered!")
    print("   Solution: Restart Django server")
else:
    print("   ✅ OK")

# Step 3: Check if any vendor products exist
print("\n[3] Checking vendor products...")
product_count = VendorProduct.objects.count()
print(f"   Total vendor products: {product_count}")

if product_count == 0:
    print("   ⚠️  No vendor products found")
    print("   Create a product first using the API")
else:
    print("   ✅ OK")
    
    # Get first product
    product = VendorProduct.objects.first()
    print(f"\n   Sample product:")
    print(f"   - ID: {product.product_id}")
    print(f"   - Name: {product.product_name}")
    print(f"   - Approved: {product.is_approved}")
    print(f"   - Status: {product.approval_status}")
    print(f"   - Business ID: {product.business_id}")
    print(f"   - Category: {product.category_name}")

# Step 4: Check Groceries models
print("\n[4] Checking Groceries models...")
try:
    from consumer.gro_models import GroceriesProducts, GroceriesProductVariants, GroceriesCategories
    print("   ✅ Groceries models imported successfully")
    
    grocery_count = GroceriesProducts.objects.count()
    print(f"   Total grocery products: {grocery_count}")
    
except Exception as e:
    print(f"   ❌ ERROR importing Groceries models: {e}")

# Step 5: Check Business model
print("\n[5] Checking Business model...")
try:
    from kirazee_app.models import Business
    business_count = Business.objects.count()
    print(f"   Total businesses: {business_count}")
    
    if business_count > 0:
        print("   ✅ OK")
        # Show first few businesses
        businesses = Business.objects.all()[:5]
        print("   Sample businesses:")
        for b in businesses:
            print(f"   - {b.business_id}")
    else:
        print("   ⚠️  No businesses found")
        
except Exception as e:
    print(f"   ❌ ERROR: {e}")

# Step 6: Test manual sync if product exists
if product_count > 0:
    print("\n[6] Testing manual sync...")
    product = VendorProduct.objects.first()
    
    # Check if product is approved
    if not product.is_approved or product.approval_status != 'approved':
        print(f"   ⚠️  Product {product.product_id} is not approved")
        print(f"   - is_approved: {product.is_approved}")
        print(f"   - approval_status: {product.approval_status}")
        print("   Approve it first using the API:")
        print(f"   PATCH /kirazee/vendor/{product.vendor_id}/products/{product.product_id}/approve/")
        print('   Body: {"approval_status": "approved"}')
    else:
        print(f"   Testing sync for product {product.product_id}...")
        try:
            success, message = product.sync_to_groceries()
            if success:
                print(f"   ✅ SUCCESS: {message}")
            else:
                print(f"   ❌ FAILED: {message}")
        except Exception as e:
            print(f"   ❌ ERROR: {e}")
            import traceback
            traceback.print_exc()

# Step 7: Summary
print("\n" + "=" * 80)
print("SUMMARY")
print("=" * 80)
print(f"Vendor app loaded: {'✅' if vendor_loaded else '❌'}")
print(f"Signals registered: {'✅' if post_save_registered and pre_save_registered else '❌'}")
print(f"Vendor products: {product_count}")
print(f"Grocery products: {grocery_count if 'grocery_count' in locals() else 'N/A'}")
print(f"Businesses: {business_count if 'business_count' in locals() else 'N/A'}")

print("\n" + "=" * 80)
print("NEXT STEPS")
print("=" * 80)
if not vendor_loaded:
    print("1. Add 'vendor' to INSTALLED_APPS in settings.py")
    print("2. Restart Django server")
elif not post_save_registered or not pre_save_registered:
    print("1. Restart Django server to register signals")
elif product_count == 0:
    print("1. Create a vendor product using the API:")
    print("   POST /kirazee/vendor/{vendor_id}/products/")
    print("2. Approve it:")
    print("   PATCH /kirazee/vendor/{vendor_id}/products/{product_id}/approve/")
else:
    print("1. Use the approval API to test automatic sync:")
    print(f"   PATCH /kirazee/vendor/{product.vendor_id}/products/{product.product_id}/approve/")
    print('   Body: {"approval_status": "approved"}')
    print("\n2. Or use manual sync API:")
    print(f"   POST /kirazee/vendor/{product.vendor_id}/products/{product.product_id}/sync/")
    print("\n3. Check sync status:")
    print(f"   GET /kirazee/vendor/{product.vendor_id}/products/{product.product_id}/sync/")

print("=" * 80)
