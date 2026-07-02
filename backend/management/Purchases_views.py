import json
import os
import uuid

from rest_framework import status
from rest_framework.decorators import api_view, parser_classes, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from django.shortcuts import get_object_or_404
from django.db import transaction, connection
from decimal import Decimal
from rest_framework.parsers import MultiPartParser, FormParser, JSONParser
from django.conf import settings
from django.core.files.storage import default_storage
from drf_yasg.utils import swagger_auto_schema

from .models import Purchases, Purchase_Items, Suppliers, Inventory, Purchase_Log, Inventory_Log, Expenses, Expenses_Log, SupplierBankDetails
from .serializers import (
    PurchaseSerializer, PurchaseItemSerializer, SuppliersSerializer, 
    InventorySerializer, PurchaseLogSerializer, InventoryLogSerializer,
    ExpensesSerializer, ExpensesLogSerializer
)
from kirazee_app.models import Business, Registration
from consumer.gro_models import GroceriesProducts, GroceriesProductVariants, GroceriesCategories
from business.models import MenuItems, productItems, FashionProductVariant
from delivery.image_utils import build_s3_file_url


@swagger_auto_schema(method='POST', tags=['management'])
@api_view(['POST'])
def create_purchase(request):
    """
    Create a new purchase with items
    URL parameters:
    - user_id (required)
    - business_id (required)
    
    Expected payload:
    {
        "supplier_id": 789,  // optional
        "invoice_number": "INV-001",  // optional
        "payment_status": "unpaid",  // optional, defaults to 'unpaid'
        "payment_method": "cash",  // optional
        "purchase_date": "2023-12-01",
        "items": [
            {
                "sku": "SKU001",  // optional
                "reference_table": "products",
                "reference_id": 1,
                "item_name": "Product Name",
                "unit": "pcs",  // optional
                "quantity": 10,
                "cost_price": 100.50,
                "selling_price": 150.00,  // optional
                "category": "Electronics"  // optional
            }
        ]
    }
    """
    try:
        # Get required parameters from URL query params
        user_id = request.GET.get('user_id')
        business_id = request.GET.get('business_id')
        
        if not user_id or not business_id:
            return Response({
                'error': 'user_id and business_id are required URL parameters'
            }, status=status.HTTP_400_BAD_REQUEST)

        # Validate user and business exist
        try:
            user = Registration.objects.get(user_id=user_id)
            print(f"DEBUG: Found user - ID: {user.id}, user_id: {user.user_id}")
        except Registration.DoesNotExist:
            # Let's check what users exist
            existing_users = Registration.objects.all().values('id', 'user_id', 'firstName', 'lastName')[:5]
            return Response({
                'error': f'User with user_id {user_id} does not exist',
                'available_users': list(existing_users),
                'note': 'Use one of the available user_id values'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            business = Business.objects.get(business_id=business_id)
            print(f"DEBUG: Found business - business_id: {business.business_id}")
        except Business.DoesNotExist:
            # Let's check what businesses exist
            existing_businesses = Business.objects.all().values('business_id', 'business_name')[:5]
            return Response({
                'error': f'Business with business_id {business_id} does not exist',
                'available_businesses': list(existing_businesses),
                'note': 'Use one of the available business_id values'
            }, status=status.HTTP_400_BAD_REQUEST)

        # Create purchase data and add user and business values that serializer expects
        purchase_data = request.data.copy()
        purchase_data['user_id'] = user.user_id  # Pass user_id value for SlugRelatedField (PurchaseSerializer still uses SlugRelatedField)
        purchase_data['business_id'] = business.business_id  # Pass business_id value
        
        # Ensure user_id and business_id are set for all items
        items = purchase_data.get('items', [])
        for item in items:
            item['user_id'] = user.id  # Pass primary key for PrimaryKeyRelatedField
            item['business_id'] = business.business_id  # Pass business_id value

        # Check if supplier_id is provided and exists
        supplier_id = purchase_data.get('supplier_id')
        if supplier_id:
            try:
                supplier = Suppliers.objects.get(supplier_id=supplier_id, business_id=business)
            except Suppliers.DoesNotExist:
                return Response({
                    'error': f'Supplier with supplier_id {supplier_id} does not exist for this business'
                }, status=status.HTTP_400_BAD_REQUEST)
        # Optional reason for audit log
        reason = request.GET.get('reason') or request.data.get('reason') or 'Created via API'

        serializer = PurchaseSerializer(data=purchase_data, context={'reason': reason})
        if serializer.is_valid():
            purchase = serializer.save()
            
            # Return the created purchase with items
            response_serializer = PurchaseSerializer(purchase)
            return Response({
                'message': 'Purchase created successfully',
                'purchase': response_serializer.data
            }, status=status.HTTP_201_CREATED)
        else:
            return Response({
                'error': 'Validation failed',
                'details': serializer.errors
            }, status=status.HTTP_400_BAD_REQUEST)
            
    except Exception as e:
        return Response({
            'error': 'An error occurred while creating the purchase',
            'details': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
def get_purchases(request):
    """
    Get purchases for a specific user and business
    Query parameters:
    - user_id (required)
    - business_id (required)
    - limit (optional, default=50)
    - offset (optional, default=0)
    """
    try:
        user_id = request.GET.get('user_id')
        business_id = request.GET.get('business_id')
        
        if not user_id or not business_id:
            return Response({
                'error': 'user_id and business_id are required query parameters'
            }, status=status.HTTP_400_BAD_REQUEST)

        # Validate user and business exist
        try:
            user = Registration.objects.get(user_id=user_id)
            business = Business.objects.get(business_id=business_id)
        except Registration.DoesNotExist:
            return Response({
                'error': f'User with user_id {user_id} does not exist'
            }, status=status.HTTP_400_BAD_REQUEST)
        except Business.DoesNotExist:
            return Response({
                'error': f'Business with business_id {business_id} does not exist'
            }, status=status.HTTP_400_BAD_REQUEST)

        # Get pagination parameters
        limit = int(request.GET.get('limit', 50))
        offset = int(request.GET.get('offset', 0))
        
        # Filter purchases
        purchases = Purchases.objects.filter(
            user_id=user,
            business_id=business
        ).prefetch_related('items')[offset:offset+limit]
        
        serializer = PurchaseSerializer(purchases, many=True)
        
        return Response({
            'purchases': serializer.data,
            'count': len(serializer.data)
        }, status=status.HTTP_200_OK)
        
    except ValueError as e:
        return Response({
            'error': 'Invalid limit or offset parameter'
        }, status=status.HTTP_400_BAD_REQUEST)
    except Exception as e:
        return Response({
            'error': 'An error occurred while fetching purchases',
            'details': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
def get_purchases_by_business(request):
    """
    Get all purchases for a specific business
    Query parameters:
    - business_id (required)
    - limit (optional, default=50)
    - offset (optional, default=0)
    """
    try:
        business_id = request.GET.get('business_id')
        
        if not business_id:
            return Response({
                'error': 'business_id is required query parameter'
            }, status=status.HTTP_400_BAD_REQUEST)

        # Validate business exists
        try:
            business = Business.objects.get(business_id=business_id)
        except Business.DoesNotExist:
            return Response({
                'error': f'Business with business_id {business_id} does not exist'
            }, status=status.HTTP_400_BAD_REQUEST)

        # Get pagination parameters
        limit = int(request.GET.get('limit', 50))
        offset = int(request.GET.get('offset', 0))
        
        # Filter purchases by business only
        purchases = Purchases.objects.filter(
            business_id=business
        ).prefetch_related('items').order_by('-purchase_date', '-created_at')[offset:offset+limit]
        
        serializer = PurchaseSerializer(purchases, many=True)
        
        return Response({
            'purchases': serializer.data,
            'count': len(serializer.data),
            'business_id': business_id
        }, status=status.HTTP_200_OK)
        
    except ValueError as e:
        return Response({
            'error': 'Invalid limit or offset parameter'
        }, status=status.HTTP_400_BAD_REQUEST)
    except Exception as e:
        return Response({
            'error': 'An error occurred while fetching purchases by business',
            'details': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
def get_purchase_detail(request, purchase_id):
    """
    Get detailed information about a specific purchase
    URL parameters:
    - purchase_id (required)
    Query parameters:
    - user_id (required)
    - business_id (required)
    """
    try:
        user_id = request.GET.get('user_id')
        business_id = request.GET.get('business_id')
        
        if not user_id or not business_id:
            return Response({
                'error': 'user_id and business_id are required query parameters'
            }, status=status.HTTP_400_BAD_REQUEST)

        # Validate user and business exist
        try:
            user = Registration.objects.get(user_id=user_id)
            business = Business.objects.get(business_id=business_id)
        except Registration.DoesNotExist:
            return Response({
                'error': f'User with user_id {user_id} does not exist'
            }, status=status.HTTP_400_BAD_REQUEST)
        except Business.DoesNotExist:
            return Response({
                'error': f'Business with business_id {business_id} does not exist'
            }, status=status.HTTP_400_BAD_REQUEST)

        # Get the specific purchase
        purchase = get_object_or_404(
            Purchases.objects.prefetch_related('items'),
            purchase_id=purchase_id,
            user_id=user,
            business_id=business
        )
        
        serializer = PurchaseSerializer(purchase)
        
        return Response({
            'purchase': serializer.data
        }, status=status.HTTP_200_OK)
        
    except Exception as e:
        return Response({
            'error': 'An error occurred while fetching purchase details',
            'details': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['PUT'])
def update_purchase_status(request, purchase_id):
    """
    Update purchase payment status
    URL parameters:
    - purchase_id (required)
    Expected payload:
    {
        "user_id": 123,
        "business_id": 456,
        "payment_status": "paid",
        "payment_method": "bank_transfer"  // optional
    }
    """
    try:
        user_id = request.data.get('user_id')
        business_id = request.data.get('business_id')
        payment_status = request.data.get('payment_status')
        
        if not user_id or not business_id or not payment_status:
            return Response({
                'error': 'user_id, business_id, and payment_status are required'
            }, status=status.HTTP_400_BAD_REQUEST)

        # Validate user and business exist
        try:
            user = Registration.objects.get(user_id=user_id)
            business = Business.objects.get(business_id=business_id)
        except Registration.DoesNotExist:
            return Response({
                'error': f'User with user_id {user_id} does not exist'
            }, status=status.HTTP_400_BAD_REQUEST)
        except Business.DoesNotExist:
            return Response({
                'error': f'Business with business_id {business_id} does not exist'
            }, status=status.HTTP_400_BAD_REQUEST)

        # Get the purchase
        purchase = get_object_or_404(
            Purchases,
            purchase_id=purchase_id,
            user_id=user,
            business_id=business
        )
        
        # Update payment status
        purchase.payment_status = payment_status
        if request.data.get('payment_method'):
            purchase.payment_method = request.data.get('payment_method')
        
        purchase.save(update_fields=['payment_status', 'payment_method', 'updated_at'])
        
        serializer = PurchaseSerializer(purchase)
        
        return Response({
            'message': 'Purchase status updated successfully',
            'purchase': serializer.data
        }, status=status.HTTP_200_OK)
        
    except Exception as e:
        return Response({
            'error': 'An error occurred while updating purchase status',
            'details': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['PUT'])
def update_purchase(request, purchase_id):
    """
    Full update of a purchase and its items.
    URL parameters or request body:
    - user_id (required)
    - business_id (required)

    Expected payload (any subset of fields; items replaces existing when provided):
    {
        "supplier_id": 2,               // optional
        "invoice_number": "INV-001",   // optional
        "payment_status": "paid",     // optional
        "payment_method": "cash",     // optional
        "purchase_date": "2024-01-15",// optional
        "items": [                      // optional; if provided, replaces all items
          { "sku": "FDG_1", "reference_table": "Groceries_ProductVariants_1", "reference_id": 156105,
            "item_name": "Test Product 1", "unit": "l", "quantity": 10, "cost_price": 100.50,
            "selling_price": 150.00, "category": "OIL&GHEE" }
        ]
    }
    """
    try:
        # Accept both query and body for ids
        user_id = request.GET.get('user_id') or request.data.get('user_id')
        business_id = request.GET.get('business_id') or request.data.get('business_id')

        if not user_id or not business_id:
            return Response({
                'error': 'user_id and business_id are required'
            }, status=status.HTTP_400_BAD_REQUEST)

        # Validate user and business
        try:
            user = Registration.objects.get(user_id=user_id)
            business = Business.objects.get(business_id=business_id)
        except Registration.DoesNotExist:
            return Response({'error': f'User with user_id {user_id} does not exist'}, status=status.HTTP_400_BAD_REQUEST)
        except Business.DoesNotExist:
            return Response({'error': f'Business with business_id {business_id} does not exist'}, status=status.HTTP_400_BAD_REQUEST)

        # Locate purchase
        purchase = get_object_or_404(
            Purchases,
            purchase_id=purchase_id,
            user_id=user,
            business_id=business
        )

        # Prepare data
        update_data = request.data.copy()
        update_data['user_id'] = user.user_id  # PurchaseSerializer uses SlugRelatedField with user_id
        update_data['business_id'] = business.business_id
        items = update_data.get('items', [])
        print(f"[DEBUG] User object: id={user.id}, user_id={user.user_id}")
        print(f"[DEBUG] Business object: business_id={business.business_id}")
        if isinstance(items, list):
            for item in items:
                item['user_id'] = user.id  # PurchaseItemSerializer uses PrimaryKeyRelatedField
                item['business_id'] = business.business_id
                print(f"[DEBUG] Item user_id set to: {user.id}, business_id set to: {business.business_id}")
                
        # Verify user exists in registrations table
        try:
            reg_check = Registration.objects.get(id=user.id)
            print(f"[DEBUG] User verification: Found user with id={reg_check.id}, user_id={reg_check.user_id}")
        except Registration.DoesNotExist:
            print(f"[DEBUG] ERROR: User with id={user.id} not found in registrations table!")
            return Response({
                'error': f'User integrity error: user.id={user.id} not found in registrations table'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        print(f"[DEBUG] Final update_data: {update_data}")
        print(f"[DEBUG] Purchase object: {purchase}")
        # Require reason for audit log (no defaults)
        reason = request.GET.get('reason') or request.data.get('reason')
        if not reason:
            return Response({'error': 'reason is required for updating a purchase'}, status=status.HTTP_400_BAD_REQUEST)
        serializer = PurchaseSerializer(purchase, data=update_data, partial=True, context={'reason': reason})
        if serializer.is_valid():
            updated = serializer.save()
            response_serializer = PurchaseSerializer(updated)
            return Response({
                'message': 'Purchase updated successfully',
                'purchase': response_serializer.data
            }, status=status.HTTP_200_OK)
        else:
            return Response({
                'error': 'Validation failed',
                'details': serializer.errors
            }, status=status.HTTP_400_BAD_REQUEST)

    except Exception as e:
        import traceback
        error_traceback = traceback.format_exc()
        print(f"[DEBUG] Purchase update error: {str(e)}")
        print(f"[DEBUG] Traceback: {error_traceback}")
        print(f"[DEBUG] Request data: {request.data}")
        print(f"[DEBUG] User: {user.id if 'user' in locals() else 'Not found'}")
        print(f"[DEBUG] Business: {business.business_id if 'business' in locals() else 'Not found'}")
        return Response({
            'error': 'An error occurred while updating the purchase',
            'details': str(e),
            'traceback': error_traceback
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['DELETE'])
def delete_purchase(request, purchase_id):
    """
    Delete a purchase and its items, with inventory adjustments.
    URL parameters:
    - purchase_id (required)
    Query parameters:
    - user_id (required)
    - business_id (required)
    """
    try:
        # Accept both query and body for ids
        user_id = request.GET.get('user_id') or request.data.get('user_id')
        business_id = request.GET.get('business_id') or request.data.get('business_id')

        if not user_id or not business_id:
            return Response({
                'error': 'user_id and business_id are required'
            }, status=status.HTTP_400_BAD_REQUEST)

        # Validate user and business exist
        try:
            user = Registration.objects.get(user_id=user_id)
            business = Business.objects.get(business_id=business_id)
        except Registration.DoesNotExist:
            return Response({'error': f'User with user_id {user_id} does not exist'}, status=status.HTTP_400_BAD_REQUEST)
        except Business.DoesNotExist:
            return Response({'error': f'Business with business_id {business_id} does not exist'}, status=status.HTTP_400_BAD_REQUEST)

        # Get the purchase
        purchase = get_object_or_404(
            Purchases,
            purchase_id=purchase_id,
            user_id=user,
            business_id=business
        )

        # Get purchase items for inventory reversal
        purchase_items = list(Purchase_Items.objects.filter(purchase_id=purchase))

        # Reverse inventory for each item
        from .serializers import PurchaseSerializer
        serializer = PurchaseSerializer()

        for item in purchase_items:
            try:
                # Build a transient Purchase_Items instance with related objects resolved
                item_for_inv = Purchase_Items(
                    purchase_item_id=item.purchase_item_id,
                    purchase_id=purchase,
                    business_id=business,
                    user_id=user,
                    sku=item.sku,
                    reference_table=item.reference_table,
                    reference_id=item.reference_id,
                    item_name=item.item_name,
                    unit=item.unit,
                    quantity=item.quantity,
                    cost_price=item.cost_price,
                    selling_price=item.selling_price,
                    category=item.category
                )
                serializer._apply_inventory_out(item=item_for_inv, actor=user)
            except Exception as e:
                return Response({
                    'error': f'Failed to reverse inventory for item {item.item_name}: {str(e)}',
                    'item_id': item.purchase_item_id
                }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        purchase_data = PurchaseSerializer(purchase).data

        # Add deletion log entry BEFORE deleting the purchase to preserve audit trail
        log_warning = None
        # Require reason for audit log (no defaults)
        reason = request.GET.get('reason') or request.data.get('reason')
        if not reason:
            return Response({'error': 'reason is required for deleting a purchase'}, status=status.HTTP_400_BAD_REQUEST)
        try:
            # Prepare detailed log data with item information
            items_info = []
            for item in purchase_items:
                items_info.append({
                    'purchase_item_id': item.purchase_item_id,
                    'item_name': item.item_name,
                    'sku': item.sku,
                    'quantity': str(item.quantity),
                    'unit': item.unit,
                    'cost_price': str(item.cost_price),
                    'selling_price': str(item.selling_price) if item.selling_price else None,
                    'category': item.category,
                    'reference_table': item.reference_table,
                    'reference_id': item.reference_id
                })
            
            log_data = {
                'purchase_id': purchase.purchase_id,
                'business_id': business.business_id,
                'user_id': user.id,
                'user_id_slug': user.user_id if hasattr(user, 'user_id') else None,
                'invoice_number': purchase.invoice_number,
                'total_amount': str(purchase.total_amount),
                'items_count': len(purchase_items),
                'items': items_info,
                'supplier_id': purchase.supplier_id.supplier_id if purchase.supplier_id else None,
                'payment_status': purchase.payment_status,
                'payment_method': purchase.payment_method,
                'purchase_date': purchase.purchase_date.isoformat() if purchase.purchase_date else None,
                'created_at': purchase.created_at.isoformat() if hasattr(purchase, 'created_at') and purchase.created_at else None,
                'updated_at': purchase.updated_at.isoformat() if hasattr(purchase, 'updated_at') and purchase.updated_at else None
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
                        purchase.purchase_id,
                        business.business_id,
                        'DELETE',
                        'Purchases',
                        reason,
                        json.dumps(log_data),
                        None,
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
                        purchase.purchase_id,
                        'DELETE',
                        'Purchases',
                        reason,
                        json.dumps(log_data),
                        None,
                        user.id
                    ])
        except Exception as e:
            log_warning = 'Deletion completed but audit log could not be recorded.'

        # Delete purchase items via raw SQL for safety with generated columns
        try:
            with connection.cursor() as cursor:
                cursor.execute("DELETE FROM Purchase_Items WHERE purchase_id = %s", [purchase_id])
        except Exception as e:
            return Response({
                'error': f'Failed to delete purchase items: {str(e)}'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        # CRITICAL: Disable foreign key checks temporarily to prevent CASCADE DELETE on Purchase_Log
        try:
            with connection.cursor() as cursor:
                # Disable foreign key checks (MySQL/MariaDB)
                cursor.execute("SET FOREIGN_KEY_CHECKS = 0")
                
                # Delete the purchase itself
                cursor.execute("DELETE FROM Purchases WHERE purchase_id = %s", [purchase_id])
                
                # Re-enable foreign key checks
                cursor.execute("SET FOREIGN_KEY_CHECKS = 1")
        except Exception as e:
            # Try to re-enable foreign key checks even if deletion failed
            try:
                with connection.cursor() as cursor:
                    cursor.execute("SET FOREIGN_KEY_CHECKS = 1")
            except:
                pass
            return Response({
                'error': f'Failed to delete purchase: {str(e)}'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        response_payload = {
            'message': 'Purchase deleted successfully',
            'deleted_purchase': purchase_data
        }
        if log_warning:
            response_payload['log_warning'] = log_warning

        return Response(response_payload, status=status.HTTP_200_OK)

    except Exception as e:
        return Response({
            'error': f'An error occurred while deleting the purchase: {str(e)}',
            'details': str(type(e).__name__)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['POST'])
@parser_classes([JSONParser, MultiPartParser, FormParser])
def create_expense(request):
    """
    Create a new expense and record an audit entry in Expenses_Log.

    Query/body parameters:
    - user_id (required)
    - business_id (required)

    Payload:
    {
      "supplier_id": 123,                // optional
      "category": "Utilities",         // required
      "description": "Electric bill",  // optional
      "amount": 1200.50,                // required
      "payment_method": "bank",        // optional
      "payment_status": "unpaid",      // optional (default unpaid)
      "expense_date": "2025-09-01",    // required (YYYY-MM-DD)
      "receipt_path": "/receipts/...", // optional
      "reason": "Monthly bill"         // optional, stored in log
    }
    """
    try:
        # Accept ids from query or body
        user_id_slug = request.GET.get('user_id') or request.data.get('user_id')
        business_id_slug = request.GET.get('business_id') or request.data.get('business_id')

        if not user_id_slug or not business_id_slug:
            return Response({'error': 'user_id and business_id are required'}, status=status.HTTP_400_BAD_REQUEST)

        # Validate user and business
        try:
            user = Registration.objects.get(user_id=user_id_slug)
        except Registration.DoesNotExist:
            return Response({'error': f'User with user_id {user_id_slug} does not exist'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            business = Business.objects.get(business_id=business_id_slug)
        except Business.DoesNotExist:
            return Response({'error': f'Business with business_id {business_id_slug} does not exist'}, status=status.HTTP_400_BAD_REQUEST)

        # Copy request.data but exclude file objects to avoid JSON serialization errors
        data = {k: v for k, v in request.data.items() if not hasattr(v, 'read')}
        supplier_id = data.get('supplier_id')
        category = data.get('category')
        description = data.get('description')
        amount = data.get('amount')
        payment_method = data.get('payment_method')
        payment_status = data.get('payment_status') or 'unpaid'
        expense_date = data.get('expense_date')
        receipt_path = data.get('receipt_path')  # optional string path
        reason = data.get('reason') or 'Created via API'

        # Handle optional receipt file upload (multipart/form-data)
        try:
            receipt_file = request.FILES.get('receipt_file') or request.FILES.get('receipt_path')
        except Exception:
            receipt_file = None

        if receipt_file:
            subdir = 'expenses_recepit'
            ext = os.path.splitext(receipt_file.name)[1] or ''
            filename = f"{uuid.uuid4().hex}{ext}"
            relative_path = f"{subdir}/{filename}"
            try:
                os.makedirs(os.path.join(settings.MEDIA_ROOT, subdir), exist_ok=True)
            except Exception:
                pass

            saved_name = default_storage.save(relative_path, receipt_file)
            try:
                relative_url = default_storage.url(saved_name)
            except Exception:
                relative_url = f"/{saved_name}"

            if isinstance(relative_url, str) and relative_url.lower().startswith(('http://', 'https://')):
                receipt_path = relative_url
            else:
                receipt_path = build_s3_file_url(saved_name)
        else:
            # If caller sent a relative URL string, normalize to S3 URL
            if isinstance(receipt_path, str) and receipt_path.startswith('/') and not receipt_path.lower().startswith(('http://', 'https://')):
                receipt_path = build_s3_file_url(receipt_path)

        # Required fields
        if not category or amount is None or not expense_date:
            return Response({'error': 'category, amount, and expense_date are required'}, status=status.HTTP_400_BAD_REQUEST)

        # Validate amount
        try:
            amount_dec = Decimal(str(amount))
        except Exception:
            return Response({'error': 'amount must be a valid number'}, status=status.HTTP_400_BAD_REQUEST)

        # Validate supplier if provided
        supplier_id_val = None
        if supplier_id not in (None, "", "null"):
            try:
                supplier_id_val = int(supplier_id)
                Suppliers.objects.get(supplier_id=supplier_id_val, business_id=business)
            except (ValueError, Suppliers.DoesNotExist):
                return Response({'error': f'Supplier with supplier_id {supplier_id} does not exist for this business'}, status=status.HTTP_400_BAD_REQUEST)

        # Insert expense and audit log atomically
        with transaction.atomic():
            # Insert into Expenses
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO Expenses (
                        business_id, user_id, supplier_id, category, description,
                        amount, payment_method, payment_status, expense_date, receipt_path,
                        created_at, updated_at
                    ) VALUES (
                        %s, %s, %s, %s, %s,
                        %s, %s, %s, %s, %s,
                        CONVERT_TZ(NOW(), 'UTC', 'Asia/Kolkata'), CONVERT_TZ(NOW(), 'UTC', 'Asia/Kolkata')
                    )
                    """,
                    [
                        business.business_id, user.id, supplier_id_val, category, description,
                        amount_dec, payment_method, payment_status, expense_date, receipt_path,
                    ],
                )
                expense_id = cursor.lastrowid

            # Build response/new_data snapshot
            new_data = {
                'expense_id': expense_id,
                'business_id': business.business_id,
                'user_id': user.id,
                'supplier_id': supplier_id_val,
                'category': category,
                'description': description,
                'amount': str(amount_dec),
                'payment_method': payment_method,
                'payment_status': payment_status,
                'expense_date': str(expense_date),
                'receipt_path': receipt_path,
            }

            # Insert into Expenses_Log
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO Expenses_Log (
                        expense_id, action, old_data, new_data, reason, user_id, changed_at
                    ) VALUES (
                        %s, %s, %s, %s, %s, %s, CONVERT_TZ(NOW(), 'UTC', 'Asia/Kolkata')
                    )
                    """,
                    [expense_id, 'INSERT', None, json.dumps(new_data), reason, user.id],
                )

        return Response({'message': 'Expense created successfully', 'expense': new_data}, status=status.HTTP_201_CREATED)

    except Exception as e:
        return Response({'error': 'An error occurred while creating the expense', 'details': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['PUT'])
def update_expense(request, expense_id):
    """
    Update an existing expense and write an audit entry.

    Query/body parameters:
    - user_id (required)
    - business_id (required)

    Payload: any of
    - supplier_id, category, description, amount, payment_method, payment_status, expense_date, receipt_path
    - reason (optional) for audit log
    """
    try:
        user_id_slug = request.GET.get('user_id') or request.data.get('user_id')
        business_id_slug = request.GET.get('business_id') or request.data.get('business_id')

        if not user_id_slug or not business_id_slug:
            return Response({'error': 'user_id and business_id are required'}, status=status.HTTP_400_BAD_REQUEST)

        # Validate user and business
        try:
            user = Registration.objects.get(user_id=user_id_slug)
        except Registration.DoesNotExist:
            return Response({'error': f'User with user_id {user_id_slug} does not exist'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            business = Business.objects.get(business_id=business_id_slug)
        except Business.DoesNotExist:
            return Response({'error': f'Business with business_id {business_id_slug} does not exist'}, status=status.HTTP_400_BAD_REQUEST)

        # Fetch current expense snapshot (ensure it belongs to the business)
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT expense_id, business_id, user_id, supplier_id, category, description,
                       amount, payment_method, payment_status, expense_date, receipt_path,
                       created_at, updated_at
                FROM Expenses
                WHERE expense_id = %s AND business_id = %s
                """,
                [expense_id, business.business_id],
            )
            row = cursor.fetchone()

        if not row:
            return Response({'error': f'Expense with id {expense_id} not found for this business'}, status=status.HTTP_404_NOT_FOUND)

        columns = [
            'expense_id', 'business_id', 'user_id', 'supplier_id', 'category', 'description',
            'amount', 'payment_method', 'payment_status', 'expense_date', 'receipt_path',
            'created_at', 'updated_at'
        ]
        old_obj = dict(zip(columns, row))
        # Serialize fields for JSON
        if old_obj.get('amount') is not None:
            old_obj['amount'] = str(old_obj['amount'])
        if old_obj.get('expense_date') is not None:
            old_obj['expense_date'] = old_obj['expense_date'].isoformat() if hasattr(old_obj['expense_date'], 'isoformat') else str(old_obj['expense_date'])
        if old_obj.get('created_at') is not None:
            old_obj['created_at'] = old_obj['created_at'].isoformat()
        if old_obj.get('updated_at') is not None:
            old_obj['updated_at'] = old_obj['updated_at'].isoformat()

        data = request.data.copy()
        reason = data.get('reason') or 'Updated via API'

        # Validate supplier if provided
        supplier_id = data.get('supplier_id', '__not_provided__')
        supplier_id_val = None
        supplier_included = supplier_id != '__not_provided__'
        if supplier_included:
            if supplier_id in (None, "", "null"):
                supplier_id_val = None
            else:
                try:
                    supplier_id_val = int(supplier_id)
                    Suppliers.objects.get(supplier_id=supplier_id_val, business_id=business)
                except (ValueError, Suppliers.DoesNotExist):
                    return Response({'error': f'Supplier with supplier_id {supplier_id} does not exist for this business'}, status=status.HTTP_400_BAD_REQUEST)

        # Prepare fields to update
        fields_map = {}
        for key in ['category', 'description', 'payment_method', 'payment_status', 'expense_date', 'receipt_path']:
            if key in data:
                fields_map[key] = data.get(key)

        # amount handling
        if 'amount' in data:
            try:
                fields_map['amount'] = Decimal(str(data.get('amount')))
            except Exception:
                return Response({'error': 'amount must be a valid number'}, status=status.HTTP_400_BAD_REQUEST)

        # supplier_id handling
        if supplier_included:
            fields_map['supplier_id'] = supplier_id_val

        if not fields_map:
            return Response({'error': 'No updatable fields provided'}, status=status.HTTP_400_BAD_REQUEST)

        # Build dynamic SQL
        set_clauses = []
        params = []
        for k, v in fields_map.items():
            set_clauses.append(f"{k} = %s")
            params.append(v)
        set_clauses.append("updated_at = CONVERT_TZ(NOW(), 'UTC', 'Asia/Kolkata')")

        with transaction.atomic():
            with connection.cursor() as cursor:
                cursor.execute(
                    f"UPDATE Expenses SET {', '.join(set_clauses)} WHERE expense_id = %s AND business_id = %s",
                    params + [expense_id, business.business_id],
                )

            # Fetch new snapshot
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT expense_id, business_id, user_id, supplier_id, category, description,
                           amount, payment_method, payment_status, expense_date, receipt_path,
                           created_at, updated_at
                    FROM Expenses
                    WHERE expense_id = %s
                    """,
                    [expense_id],
                )
                new_row = cursor.fetchone()

            new_obj = dict(zip(columns, new_row))
            if new_obj.get('amount') is not None:
                new_obj['amount'] = str(new_obj['amount'])
            if new_obj.get('expense_date') is not None:
                new_obj['expense_date'] = new_obj['expense_date'].isoformat() if hasattr(new_obj['expense_date'], 'isoformat') else str(new_obj['expense_date'])
            if new_obj.get('created_at') is not None:
                new_obj['created_at'] = new_obj['created_at'].isoformat()
            if new_obj.get('updated_at') is not None:
                new_obj['updated_at'] = new_obj['updated_at'].isoformat()

            # Log update
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO Expenses_Log (
                        expense_id, action, old_data, new_data, reason, user_id, changed_at
                    ) VALUES (
                        %s, %s, %s, %s, %s, %s, CONVERT_TZ(NOW(), 'UTC', 'Asia/Kolkata')
                    )
                    """,
                    [expense_id, 'UPDATE', json.dumps(old_obj), json.dumps(new_obj), reason, user.id],
                )

        return Response({'message': 'Expense updated successfully', 'expense': new_obj}, status=status.HTTP_200_OK)

    except Exception as e:
        return Response({'error': 'An error occurred while updating the expense', 'details': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['DELETE'])
def delete_expense(request, expense_id):
    """
    Delete an expense and write a deletion audit. We disable FK checks temporarily
    to prevent CASCADE from removing the log entry.

    Query/body parameters:
    - user_id (required)
    - business_id (required)
    - reason (optional)
    """
    try:
        user_id_slug = request.GET.get('user_id') or request.data.get('user_id')
        business_id_slug = request.GET.get('business_id') or request.data.get('business_id')
        reason = request.GET.get('reason') or request.data.get('reason') or 'Deleted via API'

        if not user_id_slug or not business_id_slug:
            return Response({'error': 'user_id and business_id are required'}, status=status.HTTP_400_BAD_REQUEST)

        # Validate user and business
        try:
            user = Registration.objects.get(user_id=user_id_slug)
        except Registration.DoesNotExist:
            return Response({'error': f'User with user_id {user_id_slug} does not exist'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            business = Business.objects.get(business_id=business_id_slug)
        except Business.DoesNotExist:
            return Response({'error': f'Business with business_id {business_id_slug} does not exist'}, status=status.HTTP_400_BAD_REQUEST)

        # Fetch expense row
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT expense_id, business_id, user_id, supplier_id, category, description,
                       amount, payment_method, payment_status, expense_date, receipt_path,
                       created_at, updated_at
                FROM Expenses
                WHERE expense_id = %s AND business_id = %s
                """,
                [expense_id, business.business_id],
            )
            row = cursor.fetchone()

        if not row:
            return Response({'error': f'Expense with id {expense_id} not found for this business'}, status=status.HTTP_404_NOT_FOUND)

        columns = [
            'expense_id', 'business_id', 'user_id', 'supplier_id', 'category', 'description',
            'amount', 'payment_method', 'payment_status', 'expense_date', 'receipt_path',
            'created_at', 'updated_at'
        ]
        old_obj = dict(zip(columns, row))
        if old_obj.get('amount') is not None:
            old_obj['amount'] = str(old_obj['amount'])
        if old_obj.get('expense_date') is not None:
            old_obj['expense_date'] = old_obj['expense_date'].isoformat() if hasattr(old_obj['expense_date'], 'isoformat') else str(old_obj['expense_date'])
        if old_obj.get('created_at') is not None:
            old_obj['created_at'] = old_obj['created_at'].isoformat()
        if old_obj.get('updated_at') is not None:
            old_obj['updated_at'] = old_obj['updated_at'].isoformat()

        # Insert deletion log BEFORE deleting
        with connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO Expenses_Log (
                    expense_id, action, old_data, new_data, reason, user_id, changed_at
                ) VALUES (
                    %s, %s, %s, %s, %s, %s, CONVERT_TZ(NOW(), 'UTC', 'Asia/Kolkata')
                )
                """,
                [expense_id, 'DELETE', json.dumps(old_obj), None, reason, user.id],
            )

        # Disable FK checks, delete, and re-enable (to retain the log)
        try:
            with connection.cursor() as cursor:
                cursor.execute("SET FOREIGN_KEY_CHECKS = 0")
                cursor.execute("DELETE FROM Expenses WHERE expense_id = %s", [expense_id])
                cursor.execute("SET FOREIGN_KEY_CHECKS = 1")
        except Exception as e:
            # Try to re-enable regardless
            try:
                with connection.cursor() as cursor:
                    cursor.execute("SET FOREIGN_KEY_CHECKS = 1")
            except Exception:
                pass
            return Response({'error': f'Failed to delete expense: {str(e)}'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        return Response({'message': 'Expense deleted successfully', 'deleted_expense': old_obj}, status=status.HTTP_200_OK)

    except Exception as e:
        return Response({'error': 'An error occurred while deleting the expense', 'details': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
def get_expenses_by_business(request):
    """
    List expenses for a specific business with optional filters.

    Query parameters:
    - business_id (required)
    - user_id (optional; Registration.user_id slug; filters Expenses.user_id by Registration.id)
    - supplier_id (optional)
    - payment_status (optional; e.g., paid/unpaid)
    - start_date (optional; YYYY-MM-DD)
    - end_date (optional; YYYY-MM-DD)
    - search (optional; matches category or description)
    - limit (optional; default 50)
    - offset (optional; default 0)
    """
    try:
        business_id = request.GET.get('business_id')
        if not business_id:
            return Response({'error': 'business_id is required query parameter'}, status=status.HTTP_400_BAD_REQUEST)

        # Validate business
        try:
            business = Business.objects.get(business_id=business_id)
        except Business.DoesNotExist:
            return Response({'error': f'Business with business_id {business_id} does not exist'}, status=status.HTTP_400_BAD_REQUEST)

        # Filters
        user_id_slug = request.GET.get('user_id')
        supplier_id = request.GET.get('supplier_id')
        payment_status = request.GET.get('payment_status')
        start_date = request.GET.get('start_date')
        end_date = request.GET.get('end_date')
        search = request.GET.get('search')
        try:
            limit = int(request.GET.get('limit', 50))
            offset = int(request.GET.get('offset', 0))
        except ValueError:
            return Response({'error': 'Invalid limit or offset parameter'}, status=status.HTTP_400_BAD_REQUEST)

        # Resolve user filter to Registration.id if provided
        user_pk = None
        if user_id_slug:
            try:
                user_pk = Registration.objects.only('id').get(user_id=user_id_slug).id
            except Registration.DoesNotExist:
                return Response({'error': f'User with user_id {user_id_slug} does not exist'}, status=status.HTTP_400_BAD_REQUEST)

        # Build SQL
        base_query = [
            "SELECT e.expense_id, e.business_id, e.user_id, e.supplier_id,",
            "       s.supplier_name, e.category, e.description, e.amount,",
            "       e.payment_method, e.payment_status, e.expense_date, e.receipt_path,",
            "       e.created_at, e.updated_at",
            "FROM Expenses e",
            "LEFT JOIN Suppliers s ON s.supplier_id = e.supplier_id AND s.business_id = e.business_id",
            "WHERE e.business_id = %s",
        ]
        params = [business.business_id]

        if user_pk is not None:
            base_query.append("AND e.user_id = %s")
            params.append(user_pk)
        if supplier_id:
            base_query.append("AND e.supplier_id = %s")
            params.append(supplier_id)
        if payment_status:
            base_query.append("AND e.payment_status = %s")
            params.append(payment_status)
        if start_date:
            base_query.append("AND e.expense_date >= %s")
            params.append(start_date)
        if end_date:
            base_query.append("AND e.expense_date <= %s")
            params.append(end_date)
        if search:
            base_query.append("AND (e.category LIKE %s OR e.description LIKE %s)")
            like = f"%{search}%"
            params.extend([like, like])

        base_query.append("ORDER BY e.expense_date DESC, e.updated_at DESC")
        base_query.append("LIMIT %s OFFSET %s")
        params.extend([limit, offset])

        query = "\n".join(base_query)

        with connection.cursor() as cursor:
            cursor.execute(query, params)
            rows = cursor.fetchall()
            cols = [
                'expense_id', 'business_id', 'user_id', 'supplier_id', 'supplier_name', 'category',
                'description', 'amount', 'payment_method', 'payment_status', 'expense_date',
                'receipt_path', 'created_at', 'updated_at'
            ]
            expenses = []
            for r in rows:
                obj = dict(zip(cols, r))
                # Serialize types
                if obj.get('amount') is not None:
                    obj['amount'] = str(obj['amount'])
                if obj.get('expense_date') is not None and hasattr(obj['expense_date'], 'isoformat'):
                    obj['expense_date'] = obj['expense_date'].isoformat()
                if obj.get('created_at') is not None and hasattr(obj['created_at'], 'isoformat'):
                    obj['created_at'] = obj['created_at'].isoformat()
                if obj.get('updated_at') is not None and hasattr(obj['updated_at'], 'isoformat'):
                    obj['updated_at'] = obj['updated_at'].isoformat()
                expenses.append(obj)

        return Response({
            'expenses': expenses,
            'count': len(expenses),
            'business_id': business.business_id,
            'filters': {
                'user_id': user_id_slug,
                'supplier_id': supplier_id,
                'payment_status': payment_status,
                'start_date': start_date,
                'end_date': end_date,
                'search': search,
            }
        }, status=status.HTTP_200_OK)

    except Exception as e:
        return Response({'error': 'An error occurred while fetching expenses', 'details': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
def get_suppliers(request):
    """
    Get suppliers for a specific business
    Query parameters:
    - business_id (required)
    - limit (optional, default=50)
    - offset (optional, default=0)
    - search (optional) - search by supplier name
    """
    try:
        business_id = request.GET.get('business_id')
        
        if not business_id:
            return Response({
                'error': 'business_id is required query parameter'
            }, status=status.HTTP_400_BAD_REQUEST)

        # Validate business exists
        try:
            business = Business.objects.get(business_id=business_id)
        except Business.DoesNotExist:
            return Response({
                'error': f'Business with business_id {business_id} does not exist'
            }, status=status.HTTP_400_BAD_REQUEST)

        # Get pagination and search parameters
        limit = int(request.GET.get('limit', 50))
        offset = int(request.GET.get('offset', 0))
        search = request.GET.get('search')
        
        # Build query
        suppliers_queryset = Suppliers.objects.filter(business_id=business)
        
        # Apply search filter
        if search:
            suppliers_queryset = suppliers_queryset.filter(supplier_name__icontains=search)
        
        # Order by supplier name and apply pagination
        suppliers = suppliers_queryset.order_by('supplier_name')[offset:offset+limit]
        
        serializer = SuppliersSerializer(suppliers, many=True)
        
        return Response({
            'suppliers': serializer.data,
            'count': len(serializer.data),
            'business_id': business_id,
            'search': search
        }, status=status.HTTP_200_OK)
        
    except ValueError as e:
        return Response({
            'error': 'Invalid limit or offset parameter'
        }, status=status.HTTP_400_BAD_REQUEST)
    except Exception as e:
        return Response({
            'error': 'An error occurred while fetching suppliers',
            'details': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['POST'])
def create_supplier(request):
    """
    Create a new supplier
    URL parameters:
    - business_id (required)
    
    Expected payload:
    {
        "supplier_name": "ABC Suppliers",
        "contact_person": "John Doe",  // optional
        "email": "john@abc.com",  // optional
        "phone": "1234567890",  // optional
        "address": "123 Main St"  // optional
    }
    """
    try:
        business_id = request.GET.get('business_id')
        
        if not business_id:
            return Response({
                'error': 'business_id is required URL parameter'
            }, status=status.HTTP_400_BAD_REQUEST)

        # Validate business exists
        try:
            business = Business.objects.get(business_id=business_id)
        except Business.DoesNotExist:
            return Response({
                'error': f'Business with business_id {business_id} does not exist'
            }, status=status.HTTP_400_BAD_REQUEST)

        # Add business_id to supplier data
        supplier_data = request.data.copy()
        supplier_data['business_id'] = business_id

        serializer = SuppliersSerializer(data=supplier_data)
        if serializer.is_valid():
            supplier = serializer.save()
            
            return Response({
                'message': 'Supplier created successfully',
                'supplier': serializer.data
            }, status=status.HTTP_201_CREATED)
        else:
            return Response({
                'error': 'Validation failed',
                'details': serializer.errors
            }, status=status.HTTP_400_BAD_REQUEST)
            
    except Exception as e:
        return Response({
            'error': 'An error occurred while creating the supplier',
            'details': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
def get_supplier_detail(request, supplier_id):
    """
    Get detailed information about a specific supplier
    URL parameters:
    - supplier_id (required)
    Query parameters:
    - business_id (required)
    """
    try:
        business_id = request.GET.get('business_id')
        
        if not business_id:
            return Response({
                'error': 'business_id is required query parameter'
            }, status=status.HTTP_400_BAD_REQUEST)

        # Validate business exists
        try:
            business = Business.objects.get(business_id=business_id)
        except Business.DoesNotExist:
            return Response({
                'error': f'Business with business_id {business_id} does not exist'
            }, status=status.HTTP_400_BAD_REQUEST)

        # Get supplier
        try:
            supplier = Suppliers.objects.get(supplier_id=supplier_id, business_id=business)
        except Suppliers.DoesNotExist:
            return Response({
                'error': f'Supplier with supplier_id {supplier_id} does not exist for this business'
            }, status=status.HTTP_404_NOT_FOUND)

        serializer = SuppliersSerializer(supplier)
        
        return Response({
            'supplier': serializer.data
        }, status=status.HTTP_200_OK)
        
    except Exception as e:
        return Response({
            'error': 'An error occurred while fetching supplier details',
            'details': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['PUT'])
def update_supplier(request, supplier_id):
    """
    Update supplier information
    URL parameters:
    - supplier_id (required)
    Query parameters:
    - business_id (required)
    
    Expected payload:
    {
        "supplier_name": "Updated Supplier Name",
        "contact_person": "Jane Doe",
        "email": "jane@updated.com",
        "phone": "9876543210",
        "address": "456 New Street"
    }
    """
    try:
        business_id = request.GET.get('business_id')
        
        if not business_id:
            return Response({
                'error': 'business_id is required query parameter'
            }, status=status.HTTP_400_BAD_REQUEST)

        # Validate business exists
        try:
            business = Business.objects.get(business_id=business_id)
        except Business.DoesNotExist:
            return Response({
                'error': f'Business with business_id {business_id} does not exist'
            }, status=status.HTTP_400_BAD_REQUEST)

        # Get supplier
        try:
            supplier = Suppliers.objects.get(supplier_id=supplier_id, business_id=business)
        except Suppliers.DoesNotExist:
            return Response({
                'error': f'Supplier with supplier_id {supplier_id} does not exist for this business'
            }, status=status.HTTP_404_NOT_FOUND)

        # Update supplier
        serializer = SuppliersSerializer(supplier, data=request.data, partial=True)
        if serializer.is_valid():
            updated_supplier = serializer.save()
            
            return Response({
                'message': 'Supplier updated successfully',
                'supplier': serializer.data
            }, status=status.HTTP_200_OK)
        else:
            return Response({
                'error': 'Validation failed',
                'details': serializer.errors
            }, status=status.HTTP_400_BAD_REQUEST)
            
    except Exception as e:
        return Response({
            'error': 'An error occurred while updating the supplier',
            'details': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['DELETE'])
def delete_supplier(request, supplier_id):
    """
    Delete a supplier
    URL parameters:
    - supplier_id (required)
    Query parameters:
    - business_id (required)
    """
    try:
        business_id = request.GET.get('business_id')
        
        if not business_id:
            return Response({
                'error': 'business_id is required query parameter'
            }, status=status.HTTP_400_BAD_REQUEST)

        # Validate business exists
        try:
            business = Business.objects.get(business_id=business_id)
        except Business.DoesNotExist:
            return Response({
                'error': f'Business with business_id {business_id} does not exist'
            }, status=status.HTTP_400_BAD_REQUEST)

        # Get supplier
        try:
            supplier = Suppliers.objects.get(supplier_id=supplier_id, business_id=business)
        except Suppliers.DoesNotExist:
            return Response({
                'error': f'Supplier with supplier_id {supplier_id} does not exist for this business'
            }, status=status.HTTP_404_NOT_FOUND)

        # Check if supplier is used in any purchases
        purchase_count = Purchases.objects.filter(supplier_id=supplier).count()
        if purchase_count > 0:
            return Response({
                'error': f'Cannot delete supplier. It is referenced in {purchase_count} purchase(s)',
                'suggestion': 'You can update the supplier information instead'
            }, status=status.HTTP_400_BAD_REQUEST)

        # Delete supplier
        supplier_data = SuppliersSerializer(supplier).data
        supplier.delete()
        
        return Response({
            'message': 'Supplier deleted successfully',
            'deleted_supplier': supplier_data
        }, status=status.HTTP_200_OK)
            
    except Exception as e:
        return Response({
            'error': 'An error occurred while deleting the supplier',
            'details': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
def get_inventory_by_business(request):
    """
    Get inventory for a specific business
    Query parameters:
    - business_id (required)
    - limit (optional, default=100)
    - offset (optional, default=0)
    - type (optional) - filter by inventory type (product/material)
    - search (optional) - search by item name
    """
    try:
        business_id = request.GET.get('business_id')
        
        if not business_id:
            return Response({
                'error': 'business_id is required query parameter'
            }, status=status.HTTP_400_BAD_REQUEST)

        # Validate business exists
        try:
            business = Business.objects.get(business_id=business_id)
        except Business.DoesNotExist:
            return Response({
                'error': f'Business with business_id {business_id} does not exist'
            }, status=status.HTTP_400_BAD_REQUEST)

        # Get pagination and filter parameters
        limit = int(request.GET.get('limit', 100))
        offset = int(request.GET.get('offset', 0))
        inventory_type = request.GET.get('type')
        search = request.GET.get('search')
        
        # Build query
        inventory_queryset = Inventory.objects.filter(business_id=business)
        
        # Apply filters
        if inventory_type:
            inventory_queryset = inventory_queryset.filter(type=inventory_type)
        
        if search:
            from django.db.models import Q

            q = Q(item_name__icontains=search) | Q(sku__icontains=search)

            business_type = str(getattr(business, 'businessType', '') or '').strip().upper()
            if business_type == 'R08':
                matching_variant_ids = FashionProductVariant.objects.filter(
                    business_id=business,
                    is_active=True,
                ).filter(
                    Q(sku__icontains=search) |
                    Q(product__name__icontains=search) |
                    Q(product__brand__icontains=search) |
                    Q(product__category__category_name__icontains=search) |
                    Q(product__description__icontains=search)
                ).values_list('variant_id', flat=True)

                q |= (
                    (Q(reference_table__iexact='fashion_product_variants') | Q(reference_table__icontains='fashion_product_variants'))
                    & Q(reference_id__in=matching_variant_ids)
                )

            inventory_queryset = inventory_queryset.filter(q)
        
        total_count = inventory_queryset.count()

        # Order by item name and apply pagination
        inventory = list(inventory_queryset.order_by('item_name')[offset:offset+limit])

        serializer = InventorySerializer(inventory, many=True)
        data = list(serializer.data)

        business_type = str(getattr(business, 'businessType', '') or '').strip().upper()
        if business_type == 'R08':
            fashion_variant_ids = [
                int(it.reference_id)
                for it in inventory
                if str(getattr(it, 'reference_table', '') or '').strip().lower() == 'fashion_product_variants'
            ]

            if fashion_variant_ids:
                variants = FashionProductVariant.objects.select_related(
                    'product',
                    'product__category',
                    'business_id',
                ).filter(
                    variant_id__in=fashion_variant_ids,
                    is_active=True,
                )
                variant_map = {int(v.variant_id): v for v in variants}

                for idx, inv in enumerate(inventory):
                    if str(getattr(inv, 'reference_table', '') or '').strip().lower() != 'fashion_product_variants':
                        continue

                    var = variant_map.get(int(inv.reference_id))
                    if not var:
                        continue

                    product = getattr(var, 'product', None)
                    data[idx]['variant_id'] = int(var.variant_id)
                    data[idx]['product_id'] = getattr(product, 'product_id', None) if product else None
                    data[idx]['reference_table'] = 'fashion_product_variants'
                    data[idx]['reference_id'] = getattr(product, 'product_id', None) if product else data[idx].get('reference_id')

                    if product and getattr(product, 'name', None):
                        data[idx]['item_name'] = product.name

                    if getattr(var, 'sku', None):
                        data[idx]['sku'] = var.sku

        return Response({
            'inventory': data,
            'count': len(data),
            'total_count': total_count,
            'business_id': business_id,
            'filters': {
                'type': inventory_type,
                'search': search
            }
        }, status=status.HTTP_200_OK)
        
    except ValueError as e:
        return Response({
            'error': 'Invalid limit or offset parameter'
        }, status=status.HTTP_400_BAD_REQUEST)
    except Exception as e:
        return Response({
            'error': 'An error occurred while fetching inventory',
            'details': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['PUT'])
def update_inventory_item(request, inventory_id):
    """Manually update an inventory item for a business and record an audit entry.

    Required parameters (query or body):
    - business_id: Business.business_id
    - user_id: Registration.user_id (slug)
    - reason: Human explanation for the edit (stored in edit_reason)

    Body can include any of these updatable inventory fields:
    - opening_stock, purchased_stock, sold_stock (integers)
    - sku, item_name, unit, type, reference_table (strings)
    - reference_id (integer)
    """
    try:
        business_id = request.GET.get('business_id') or request.data.get('business_id')
        user_id_slug = request.GET.get('user_id') or request.data.get('user_id')
        edit_reason = request.data.get('reason') or request.GET.get('reason')

        if not business_id or not user_id_slug or not edit_reason:
            return Response({
                'error': 'business_id, user_id, and reason are required'
            }, status=status.HTTP_400_BAD_REQUEST)

        # Validate business and user
        try:
            business = Business.objects.get(business_id=business_id)
        except Business.DoesNotExist:
            return Response({
                'error': f'Business with business_id {business_id} does not exist'
            }, status=status.HTTP_400_BAD_REQUEST)

        try:
            user = Registration.objects.get(user_id=user_id_slug)
        except Registration.DoesNotExist:
            return Response({
                'error': f'User with user_id {user_id_slug} does not exist'
            }, status=status.HTTP_400_BAD_REQUEST)

        # Locate inventory row for this business
        inventory = get_object_or_404(
            Inventory,
            inventory_id=inventory_id,
            business_id=business
        )

        # Snapshot before changes
        old_snapshot = {
            'opening_stock': inventory.opening_stock,
            'purchased_stock': inventory.purchased_stock,
            'sold_stock': inventory.sold_stock,
            'current_stock': inventory.current_stock,
        }

        data = request.data or {}

        # Update allowed inventory fields if provided
        numeric_fields = ['opening_stock', 'purchased_stock', 'sold_stock']
        text_fields = ['sku', 'item_name', 'unit', 'type', 'reference_table']
        updated_any = False
        updated_fields = []

        for field in numeric_fields:
            if field in data:
                try:
                    value = int(data.get(field))
                except (TypeError, ValueError):
                    return Response({
                        'error': f'{field} must be an integer'
                    }, status=status.HTTP_400_BAD_REQUEST)
                setattr(inventory, field, value)
                updated_any = True
                if field not in updated_fields:
                    updated_fields.append(field)

        for field in text_fields:
            if field in data:
                setattr(inventory, field, data.get(field))
                updated_any = True
                if field not in updated_fields:
                    updated_fields.append(field)

        if 'reference_id' in data:
            try:
                inventory.reference_id = int(data.get('reference_id'))
            except (TypeError, ValueError):
                return Response({
                    'error': 'reference_id must be an integer'
                }, status=status.HTTP_400_BAD_REQUEST)
            updated_any = True
            if 'reference_id' not in updated_fields:
                updated_fields.append('reference_id')

        try:
            business_type = str(getattr(business, 'businessType', '') or '').strip().upper()
        except Exception:
            business_type = ''

        if business_type == 'R08':
            ref_table_lower = str(inventory.reference_table or '').strip().lower()
            if ref_table_lower == 'fashion_product_variants' or 'fashion_product_variants' in ref_table_lower:
                try:
                    resolved_variant_id = PurchaseSerializer()._resolve_r08_fashion_variant_id(business, inventory.reference_id)
                except Exception as e:
                    return Response({
                        'error': 'Invalid fashion reference_id for R08 inventory',
                        'details': str(e)
                    }, status=status.HTTP_400_BAD_REQUEST)

                if int(inventory.reference_id) != int(resolved_variant_id):
                    inventory.reference_id = int(resolved_variant_id)
                    if 'reference_id' not in updated_fields:
                        updated_fields.append('reference_id')

                if inventory.reference_table != 'fashion_product_variants':
                    inventory.reference_table = 'fashion_product_variants'
                    if 'reference_table' not in updated_fields:
                        updated_fields.append('reference_table')

        if not updated_any:
            return Response({
                'error': 'No updatable inventory fields were provided'
            }, status=status.HTTP_400_BAD_REQUEST)

        # Record actor on inventory row
        inventory.user_id = user
        if 'user_id' not in updated_fields:
            updated_fields.append('user_id')

        # Also let Django update the timestamp field while avoiding generated columns
        if 'last_updated' not in updated_fields:
            updated_fields.append('last_updated')

        # Save only changed, non-generated fields to avoid writing to generated column current_stock
        inventory.save(update_fields=updated_fields)

        # Reload to ensure DB-computed fields like current_stock are up to date
        inventory.refresh_from_db()

        # Snapshot after changes
        new_snapshot = {
            'opening_stock': inventory.opening_stock,
            'purchased_stock': inventory.purchased_stock,
            'sold_stock': inventory.sold_stock,
            'current_stock': inventory.current_stock,
        }

        try:
            ref_table_lower = str(inventory.reference_table or '').strip().lower()
            current_stock = int(inventory.current_stock or 0)

            if 'menuitems' in ref_table_lower or ref_table_lower == 'menuitems':
                MenuItems.objects.filter(item_id=inventory.reference_id).update(quantity=current_stock)
            elif 'groceries_productvariants' in ref_table_lower or 'groceriesproductvariants' in ref_table_lower:
                GroceriesProductVariants.objects.filter(variant_id=inventory.reference_id).update(stock=current_stock)
            elif 'groceryitems' in ref_table_lower or ref_table_lower == 'groceryitems':
                productItems.objects.filter(item_id=inventory.reference_id).update(stock=current_stock)
            elif 'fashion_product_variants' in ref_table_lower or 'fashionproductvariants' in ref_table_lower:
                FashionProductVariant.objects.filter(variant_id=inventory.reference_id).update(stock=current_stock, stock_qty=current_stock)
        except Exception:
            pass
        system_reason = f'Manual inventory edit via API by user_id {user.user_id}'

        # Insert audit log with edit_reason and system reason
        with connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO Inventory_Log (
                    inventory_id, business_id, sku, reference_table, reference_id,
                    item_name, action, edit_reason, reason, old_stock, new_stock,
                    user_id, changed_at
                ) VALUES (
                    %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s, %s,
                    %s, CONVERT_TZ(NOW(), 'UTC', 'Asia/Kolkata')
                )
                """,
                [
                    inventory.inventory_id,
                    business.business_id,
                    inventory.sku,
                    inventory.reference_table,
                    inventory.reference_id,
                    inventory.item_name,
                    'ADJUST',
                    edit_reason,
                    system_reason,
                    json.dumps(old_snapshot),
                    json.dumps(new_snapshot),
                    user.id,
                ],
            )

        serializer = InventorySerializer(inventory)
        inventory_data = dict(serializer.data)

        business_type = str(getattr(business, 'businessType', '') or '').strip().upper()
        ref_table_lower = str(inventory.reference_table or '').strip().lower()

        if business_type == 'R08' and (ref_table_lower == 'fashion_product_variants' or 'fashion_product_variants' in ref_table_lower):
            var = FashionProductVariant.objects.select_related('product').filter(
                variant_id=inventory.reference_id,
                is_active=True,
            ).first()

            if var:
                product = getattr(var, 'product', None)
                inventory_data['variant_id'] = int(var.variant_id)
                inventory_data['product_id'] = getattr(product, 'product_id', None) if product else None
                inventory_data['reference_table'] = 'fashion_product_variants'
                inventory_data['reference_id'] = getattr(product, 'product_id', None) if product else inventory_data.get('reference_id')

                if product and getattr(product, 'name', None):
                    inventory_data['item_name'] = product.name

                if getattr(var, 'sku', None):
                    inventory_data['sku'] = var.sku

        return Response({
            'message': 'Inventory updated successfully',
            'inventory': inventory_data
        }, status=status.HTTP_200_OK)

    except Exception as e:
        return Response({
            'error': 'An error occurred while updating inventory',
            'details': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

@swagger_auto_schema(method='DELETE', tags=['management'])
@api_view(['DELETE'])
def delete_inventory_item(request, inventory_id):
    """
    Delete an inventory item for a business and record an audit entry.
    
    Required parameters (query or body):
    - business_id: Business.business_id
    - user_id: Registration.user_id (slug)
    - reason: Human explanation for deletion (stored in edit_reason)
    
    This will:
    - Delete inventory item permanently
    - Create an audit log entry
    - NOT update reference table (MenuItems, GroceriesProductVariants, etc.)
    """
    try:
        business_id = request.GET.get('business_id') or request.data.get('business_id')
        user_id_slug = request.GET.get('user_id') or request.data.get('user_id')
        delete_reason = request.data.get('reason') or request.GET.get('reason')

        if not business_id or not user_id_slug or not delete_reason:
            return Response({
                'error': 'business_id, user_id, and reason are required'
            }, status=status.HTTP_400_BAD_REQUEST)

        # Validate business and user
        try:
            business = Business.objects.get(business_id=business_id)
        except Business.DoesNotExist:
            return Response({
                'error': f'Business with business_id {business_id} does not exist'
            }, status=status.HTTP_400_BAD_REQUEST)

        try:
            user = Registration.objects.get(user_id=user_id_slug)
        except Registration.DoesNotExist:
            return Response({
                'error': f'User with user_id {user_id_slug} does not exist'
            }, status=status.HTTP_400_BAD_REQUEST)

        # Locate inventory row for this business
        inventory = get_object_or_404(
            Inventory,
            inventory_id=inventory_id,
            business_id=business
        )

        # Snapshot before deletion for audit trail
        inventory_snapshot = {
            'inventory_id': inventory.inventory_id,
            'business_id': business.business_id,
            'sku': inventory.sku,
            'reference_table': inventory.reference_table,
            'reference_id': inventory.reference_id,
            'item_name': inventory.item_name,
            'type': inventory.type,
            'unit': inventory.unit,
            'opening_stock': inventory.opening_stock,
            'purchased_stock': inventory.purchased_stock,
            'sold_stock': inventory.sold_stock,
            'current_stock': inventory.current_stock,
            'last_updated': inventory.last_updated.isoformat() if inventory.last_updated else None
        }

        # Insert audit log before deletion
        with connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO Inventory_Log (
                    inventory_id, business_id, sku, reference_table, reference_id,
                    item_name, action, edit_reason, reason, old_stock, new_stock,
                    user_id, changed_at
                ) VALUES (
                    %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s, %s,
                    %s, CONVERT_TZ(NOW(), 'UTC', 'Asia/Kolkata')
                )
                """,
                [
                    inventory.inventory_id,
                    business.business_id,
                    inventory.sku,
                    inventory.reference_table,
                    inventory.reference_id,
                    inventory.item_name,
                    'DELETE',
                    delete_reason,
                    f'Inventory item deleted via API by user_id {user.user_id}',
                    json.dumps(inventory_snapshot),
                    json.dumps({'deleted': True}),
                    user.id,
                ],
            )

        # Delete the inventory item
        inventory.delete()

        return Response({
            'message': 'Inventory item deleted successfully',
            'deleted_inventory': inventory_snapshot
        }, status=status.HTTP_200_OK)

    except Exception as e:
        return Response({
            'error': 'An error occurred while deleting inventory item',
            'details': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        
@api_view(['GET'])
def get_purchase_logs(request):
    """
    Get purchase logs for a specific business
    Query parameters:
    - business_id (required)
    - purchase_id (optional) - filter by specific purchase
    - limit (optional, default=50)
    - offset (optional, default=0)
    """
    try:
        business_id = request.GET.get('business_id')
        
        if not business_id:
            return Response({
                'error': 'business_id is required query parameter'
            }, status=status.HTTP_400_BAD_REQUEST)

        # Validate business exists
        try:
            business = Business.objects.get(business_id=business_id)
        except Business.DoesNotExist:
            return Response({
                'error': f'Business with business_id {business_id} does not exist'
            }, status=status.HTTP_400_BAD_REQUEST)

        # Get filter and pagination parameters
        purchase_id = request.GET.get('purchase_id')
        limit = int(request.GET.get('limit', 50))
        offset = int(request.GET.get('offset', 0))
        
        # Use raw SQL to query Purchase_Log, include user_name via registrations.
        # Also handle older schemas without Purchase_Log.business_id by joining Purchases.
        with connection.cursor() as cursor:
            base_query = """
                SELECT 
                    pl.log_id,
                    pl.purchase_id,
                    pl.business_id,
                    pl.action,
                    pl.action_table,
                    pl.reason,
                    pl.old_data,
                    pl.new_data,
                    pl.user_id,
                    CONCAT(COALESCE(r.firstName, ''), ' ', COALESCE(r.lastName, '')) AS user_name,
                    r.user_id AS user_slug,
                    pl.changed_at
                FROM Purchase_Log pl
                LEFT JOIN registrations r ON pl.user_id = r.id
                WHERE pl.business_id = %s
            """
            params = [business_id]

            # Apply purchase filter if provided
            if purchase_id:
                base_query += " AND pl.purchase_id = %s"
                params.append(purchase_id)

            # Add ordering and pagination
            base_query += " ORDER BY pl.changed_at DESC LIMIT %s OFFSET %s"
            params.extend([limit, offset])

            try:
                cursor.execute(base_query, params)
            except Exception:
                # Fallback: older schemas may not have business_id on Purchase_Log
                fallback_query = """
                    SELECT 
                        pl.log_id,
                        pl.purchase_id,
                        p.business_id,
                        pl.action,
                        pl.action_table,
                        pl.reason,
                        pl.old_data,
                        pl.new_data,
                        pl.user_id,
                        CONCAT(COALESCE(r.firstName, ''), ' ', COALESCE(r.lastName, '')) AS user_name,
                        r.user_id AS user_slug,
                        pl.changed_at
                    FROM Purchase_Log pl
                    INNER JOIN Purchases p ON pl.purchase_id = p.purchase_id
                    LEFT JOIN registrations r ON pl.user_id = r.id
                    WHERE p.business_id = %s
                """
                fb_params = [business_id]
                if purchase_id:
                    fallback_query += " AND pl.purchase_id = %s"
                    fb_params.append(purchase_id)
                fallback_query += " ORDER BY pl.changed_at DESC LIMIT %s OFFSET %s"
                fb_params.extend([limit, offset])
                cursor.execute(fallback_query, fb_params)

            # Fetch results and convert to list of dictionaries
            columns = [col[0] for col in cursor.description]
            logs_data = []
            for row in cursor.fetchall():
                log_dict = dict(zip(columns, row))
                # Convert datetime to string for JSON serialization
                if log_dict.get('changed_at'):
                    log_dict['changed_at'] = log_dict['changed_at'].isoformat()
                # Parse JSON fields
                if log_dict.get('old_data'):
                    try:
                        log_dict['old_data'] = json.loads(log_dict['old_data']) if isinstance(log_dict['old_data'], str) else log_dict['old_data']
                    except Exception:
                        pass
                if log_dict.get('new_data'):
                    try:
                        log_dict['new_data'] = json.loads(log_dict['new_data']) if isinstance(log_dict['new_data'], str) else log_dict['new_data']
                    except Exception:
                        pass

                # Add summary of items for easier reading
                log_dict['items_summary'] = []
                for data_field in ['old_data', 'new_data']:
                    if log_dict.get(data_field) and isinstance(log_dict[data_field], dict) and 'items' in log_dict[data_field]:
                        items = log_dict[data_field]['items']
                        if items:
                            summary = []
                            for item in items:
                                if isinstance(item, dict) and 'item_name' in item:
                                    summary.append(f"{item['item_name']} (Qty: {item.get('quantity', 'N/A')})")
                            if summary:
                                log_dict['items_summary'] = summary
                                break

                logs_data.append(log_dict)
        
        return Response({
            'purchase_logs': logs_data,
            'count': len(logs_data),
            'business_id': business_id,
            'purchase_id': purchase_id
        }, status=status.HTTP_200_OK)
        
    except ValueError as e:
        return Response({
            'error': 'Invalid limit, offset, or purchase_id parameter'
        }, status=status.HTTP_400_BAD_REQUEST)
    except Exception as e:
        return Response({
            'error': 'An error occurred while fetching purchase logs',
            'details': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
def get_inventory_logs(request):
    """
    Get inventory logs for a specific business
    Query parameters:
    - business_id (required)
    - inventory_id (optional) - filter by specific inventory item
    - sku (optional) - filter by SKU
    - action (optional) - filter by action type (ADD, REMOVE, ADJUST)
    - limit (optional, default=50)
    - offset (optional, default=0)
    """
    try:
        business_id = request.GET.get('business_id')
        
        if not business_id:
            return Response({
                'error': 'business_id is required query parameter'
            }, status=status.HTTP_400_BAD_REQUEST)

        # Validate business exists
        try:
            business = Business.objects.get(business_id=business_id)
        except Business.DoesNotExist:
            return Response({
                'error': f'Business with business_id {business_id} does not exist'
            }, status=status.HTTP_400_BAD_REQUEST)

        # Get filter and pagination parameters
        inventory_id = request.GET.get('inventory_id')
        sku = request.GET.get('sku')
        action = request.GET.get('action')
        limit = int(request.GET.get('limit', 50))
        offset = int(request.GET.get('offset', 0))
        
        # Build query - filter by business
        logs_queryset = Inventory_Log.objects.filter(
            business_id=business.business_id
        ).select_related('user_id')
        
        # Apply filters if provided
        if inventory_id:
            logs_queryset = logs_queryset.filter(inventory_id=inventory_id)
        
        if sku:
            logs_queryset = logs_queryset.filter(sku__icontains=sku)
            
        if action:
            logs_queryset = logs_queryset.filter(action=action)
        
        # Order by most recent and apply pagination
        logs = logs_queryset.order_by('-changed_at')[offset:offset+limit]
        
        serializer = InventoryLogSerializer(logs, many=True)
        
        return Response({
            'inventory_logs': serializer.data,
            'count': len(serializer.data),
            'business_id': business_id,
            'filters': {
                'inventory_id': inventory_id,
                'sku': sku,
                'action': action
            }
        }, status=status.HTTP_200_OK)
        
    except ValueError as e:
        return Response({
            'error': 'Invalid limit, offset, or inventory_id parameter'
        }, status=status.HTTP_400_BAD_REQUEST)
    except Exception as e:
        return Response({
            'error': 'An error occurred while fetching inventory logs',
            'details': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
def get_expenses_logs(request):
    """
    Get expenses logs for a specific business - includes all INSERT, UPDATE, DELETE operations
    Query parameters:
    - business_id (required)
    - expense_id (optional) - filter by specific expense
    - action (optional) - filter by action type (INSERT, UPDATE, DELETE)
    - limit (optional, default=50)
    - offset (optional, default=0)
    """
    try:
        business_id = request.GET.get('business_id')
        
        if not business_id:
            return Response({
                'error': 'business_id is required query parameter'
            }, status=status.HTTP_400_BAD_REQUEST)

        # Validate business exists
        try:
            business = Business.objects.get(business_id=business_id)
        except Business.DoesNotExist:
            return Response({
                'error': f'Business with business_id {business_id} does not exist'
            }, status=status.HTTP_400_BAD_REQUEST)

        # Get filter and pagination parameters
        expense_id = request.GET.get('expense_id')
        action = request.GET.get('action')
        from_date = request.GET.get('from_date')
        to_date = request.GET.get('to_date')
        limit = int(request.GET.get('limit', 50))
        offset = int(request.GET.get('offset', 0))
        
        
        # Build base query using raw SQL for better performance and to handle deleted expenses
        # This ensures we get logs even for expenses that have been deleted
        with connection.cursor() as cursor:
            # Debug: Check what actions exist in the database
            cursor.execute("SELECT DISTINCT action FROM Expenses_Log ORDER BY action")
            existing_actions = [row[0] for row in cursor.fetchall()]
            print(f"DEBUG: Available actions in database: {existing_actions}")
            # Build WHERE clause conditions
            where_conditions = ["1=1"]  # Base condition
            params = []
            
            # Filter by business_id - handle both existing and deleted expenses
            # For deleted expenses, we need to extract business_id from the log data
            where_conditions.append("""
                (
                    el.expense_id IN (SELECT e.expense_id FROM Expenses e WHERE e.business_id = %s)
                    OR 
                    (
                        el.old_data IS NOT NULL 
                        AND JSON_UNQUOTE(JSON_EXTRACT(el.old_data, '$.business_id')) = %s
                    )
                    OR
                    (
                        el.new_data IS NOT NULL 
                        AND JSON_UNQUOTE(JSON_EXTRACT(el.new_data, '$.business_id')) = %s
                    )
                )
            """)
            params.extend([business.business_id, business.business_id, business.business_id])
            
            # Apply optional filters
            if expense_id:
                try:
                    expense_id_int = int(expense_id)
                    where_conditions.append("el.expense_id = %s")
                    params.append(expense_id_int)
                except ValueError:
                    return Response({
                        'error': 'expense_id must be a valid integer'
                    }, status=status.HTTP_400_BAD_REQUEST)
            
            if action and action.upper() in ['INSERT', 'UPDATE', 'DELETE']:
                where_conditions.append("el.action = %s")
                params.append(action.upper())
                print(f"DEBUG: Added action filter: {action.upper()}")
            
            # Apply date filters
            if from_date:
                where_conditions.append("DATE(el.changed_at) >= %s")
                params.append(from_date)
                print(f"DEBUG: Added from_date filter: {from_date}")
            
            if to_date:
                where_conditions.append("DATE(el.changed_at) <= %s")
                params.append(to_date)
                print(f"DEBUG: Added to_date filter: {to_date}")
            
            # Get total count first (using same WHERE conditions as main query)
            count_query = f"""
                SELECT COUNT(*) as total_count
                FROM Expenses_Log el
                LEFT JOIN Expenses e ON el.expense_id = e.expense_id
                LEFT JOIN registrations r ON el.user_id = r.id
                WHERE {' AND '.join(where_conditions)}
            """
            
            print(f"DEBUG: Count query params: {params}")
            cursor.execute(count_query, params)
            total_count = cursor.fetchone()[0]
            print(f"DEBUG: Count query returned: {total_count}")
            
            # Get paginated results with all necessary data
            main_query = f"""
                SELECT 
                    el.log_id,
                    el.expense_id,
                    el.action,
                    el.old_data,
                    el.new_data,
                    el.reason,
                    el.user_id,
                    el.changed_at,
                    COALESCE(r.firstName, '') as first_name,
                    COALESCE(r.lastName, '') as last_name,
                    COALESCE(
                        e.business_id,
                        JSON_UNQUOTE(JSON_EXTRACT(el.old_data, '$.business_id')),
                        JSON_UNQUOTE(JSON_EXTRACT(el.new_data, '$.business_id'))
                    ) as business_id,
                    COALESCE(e.category, 
                        CASE 
                            WHEN el.new_data IS NOT NULL THEN JSON_UNQUOTE(JSON_EXTRACT(el.new_data, '$.category'))
                            WHEN el.old_data IS NOT NULL THEN JSON_UNQUOTE(JSON_EXTRACT(el.old_data, '$.category'))
                            ELSE NULL
                        END
                    ) as expense_category
                FROM Expenses_Log el
                LEFT JOIN Expenses e ON el.expense_id = e.expense_id
                LEFT JOIN registrations r ON el.user_id = r.id
                WHERE {' AND '.join(where_conditions)}
                ORDER BY el.changed_at DESC
                LIMIT %s OFFSET %s
            """
            
            final_params = params + [limit, offset]
            print(f"DEBUG: Main query params: {final_params}")
            
            cursor.execute(main_query, final_params)
            rows = cursor.fetchall()
            print(f"DEBUG: Main query returned {len(rows)} rows")
            
            # Convert to list of dictionaries
            columns = [
                'log_id', 'expense_id', 'action', 'old_data', 'new_data', 'reason', 
                'user_id', 'changed_at', 'first_name', 'last_name', 'business_id', 'expense_category'
            ]
            
            logs_data = []
            for row in rows:
                log_dict = dict(zip(columns, row))
                
                # Format user name
                user_name = f"{log_dict['first_name']} {log_dict['last_name']}".strip()
                log_dict['user_name'] = user_name if user_name else None
                
                # Parse JSON fields
                if log_dict['old_data']:
                    try:
                        log_dict['old_data'] = json.loads(log_dict['old_data'])
                    except (json.JSONDecodeError, TypeError):
                        log_dict['old_data'] = None
                
                if log_dict['new_data']:
                    try:
                        log_dict['new_data'] = json.loads(log_dict['new_data'])
                    except (json.JSONDecodeError, TypeError):
                        log_dict['new_data'] = None
                
                # Format datetime
                if log_dict['changed_at']:
                    log_dict['changed_at'] = log_dict['changed_at'].isoformat()
                
                # Remove helper fields
                del log_dict['first_name']
                del log_dict['last_name']
                
                logs_data.append(log_dict)
        
        return Response({
            'expenses_logs': logs_data,
            'count': total_count,
            'business_id': business_id,
            'filters': {
                'expense_id': expense_id,
                'action': action
            },
            'pagination': {
                'limit': limit,
                'offset': offset,
                'total': total_count,
                'has_next': offset + limit < total_count,
                'has_previous': offset > 0
            }
        }, status=status.HTTP_200_OK)
        
    except ValueError as e:
        return Response({
            'error': 'Invalid limit, offset, or expense_id parameter'
        }, status=status.HTTP_400_BAD_REQUEST)
    except Exception as e:
        return Response({
            'error': 'An error occurred while fetching expenses logs',
            'details': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
def search_product_by_sku(request):
    """
    Search for product and item details by SKU or product name
    Query parameters:
    - sku (optional) - The SKU to search for
    - search (optional) - Search term for product name, brand, or category
    - business_id (optional) - Filter by business
    - exact_match (optional, default=false) - Whether to perform exact match or partial search
    - limit (optional, default=20) - Maximum number of results
    """
    try:
        sku = request.GET.get('sku')
        search_term = request.GET.get('search')
        business_id = request.GET.get('business_id')
        exact_match = request.GET.get('exact_match', 'false').lower() == 'true'
        limit = int(request.GET.get('limit', 20))
        price_search = request.GET.get('price')

        def get_clean_image_url(image_field):
            """Build S3 URL for image field."""
            return build_s3_file_url(image_field)

        if not sku and not search_term and not price_search:
            return Response({
                'error': 'Either sku, search, or price parameter is required'
            }, status=status.HTTP_400_BAD_REQUEST)

        # Validate business if provided
        business = None
        if business_id:
            try:
                business = Business.objects.get(business_id=business_id)
            except Business.DoesNotExist:
                return Response({
                    'error': f'Business with business_id {business_id} does not exist'
                }, status=status.HTTP_400_BAD_REQUEST)

        # Build query for product variants
        variants_queryset = GroceriesProductVariants.objects.select_related(
            'product', 
            'product__category', 
            'product__business'
        )
        
        # Apply search filters
        if sku:
            # SKU-based search
            if exact_match:
                variants_queryset = variants_queryset.filter(sku=sku)
            else:
                variants_queryset = variants_queryset.filter(sku__icontains=sku)
        
        if search_term:
            # Product name/brand/category search
            from django.db.models import Q
            if exact_match:
                # Exact match for product name or brand
                variants_queryset = variants_queryset.filter(
                    Q(product__product_name__iexact=search_term) |
                    Q(product__brand_name__iexact=search_term)
                )
            else:
                # Partial match across multiple fields
                variants_queryset = variants_queryset.filter(
                    Q(product__product_name__icontains=search_term) |
                    Q(product__brand_name__icontains=search_term) |
                    Q(product__sub_category__icontains=search_term) |
                    Q(product__category__category_name__icontains=search_term) |
                    Q(product__description__icontains=search_term)
                )
        
        if price_search:
            try:
                price_val = float(price_search)
                variants_queryset = variants_queryset.filter(selling_price=price_val)
            except ValueError:
                pass
        
        included_business_ids = None
        # Apply business filter if provided
        if business:
            level_val = (business.level or '').strip().lower()
            if 'master' in level_val:
                child_ids = list(Business.objects.filter(master=business.business_id).values_list('business_id', flat=True))
                included_business_ids = [business.business_id] + child_ids
            else:
                included_business_ids = [business.business_id]
            variants_queryset = variants_queryset.filter(product__business__business_id__in=included_business_ids)
        
        # Get the variants with ordering by relevance
        variants = variants_queryset.filter(is_active=True).order_by(
            'product__product_name', 'product__brand_name'
        )[:limit]

        # Build combined results from multiple sources
        results = []

        # First, map grocery variants
        if variants.exists():
            for variant in variants:
                product = variant.product
                category = product.category

                # Calculate profit margin if both costs are available
                profit_margin = None
                if variant.original_cost and variant.selling_price:
                    profit_margin = float(variant.selling_price) - float(variant.original_cost)

                # Format expiry status
                expiry_status = None
                if variant.expiry_date:
                    from datetime import date
                    today = date.today()
                    days_to_expiry = (variant.expiry_date - today).days
                    if days_to_expiry < 0:
                        expiry_status = "Expired"
                    elif days_to_expiry <= 30:
                        expiry_status = f"Expires in {days_to_expiry} days"
                    else:
                        expiry_status = "Fresh"

                results.append({
                    'variant_id': variant.variant_id,
                    'sku': variant.sku,
                    'net_weight': variant.net_weight,
                    'net_weight_unit': variant.net_weight_unit,
                    'size': variant.size,
                    'original_cost': float(variant.original_cost) if variant.original_cost else None,
                    'selling_price': float(variant.selling_price) if variant.selling_price else None,
                    'charges': float(variant.charges) if variant.charges else None,
                    'profit_margin': profit_margin,
                    'stock': variant.stock,
                    'mfg_date': variant.mfg_date.isoformat() if variant.mfg_date else None,
                    'expiry_date': variant.expiry_date.isoformat() if variant.expiry_date else None,
                    'expiry_status': expiry_status,
                    'is_active': variant.is_active,
                    'variant_created_at': variant.created_at.isoformat(),
                    'variant_updated_at': variant.updated_at.isoformat(),
                    'reference_table': 'Groceries_ProductVariants_1',
                    'reference_id': variant.variant_id,
                    'product': {
                        'product_id': product.product_id,
                        'product_name': product.product_name,
                        'brand_name': product.brand_name,
                        'sub_category': product.sub_category,
                        'description': product.description,
                        'main_image': get_clean_image_url(product.main_image),
                        'is_organic': product.is_organic,
                        'rating': float(product.rating) if product.rating else None,
                        'created_at': product.created_at.isoformat(),
                        'updated_at': product.updated_at.isoformat(),
                    },
                    'category': {
                        'category_id': category.category_id if category else None,
                        'category_name': category.category_name if category else None,
                        'gst_rate': float(category.gst_rate) if category and category.gst_rate else 0.0,
                        'category_image': get_clean_image_url(category.category_image) if category else None,
                    },
                    'business': {
                        'business_id': product.business.business_id if product.business else None,
                        'business_name': product.business.businessName if product.business else None,
                    }
                })

        remaining = max(0, limit - len(results))
        business_type = str(getattr(business, 'businessType', '') or '').strip().upper() if business else ''
        if remaining > 0 and business_type == 'R08':
            fashion_qs = FashionProductVariant.objects.select_related(
                'product',
                'product__category',
                'business_id'
            )

            if included_business_ids:
                fashion_qs = fashion_qs.filter(business_id__business_id__in=included_business_ids)

            if sku:
                if exact_match:
                    fashion_qs = fashion_qs.filter(sku=sku)
                else:
                    fashion_qs = fashion_qs.filter(sku__icontains=sku)

            if search_term:
                from django.db.models import Q
                if exact_match:
                    fashion_qs = fashion_qs.filter(
                        Q(product__name__iexact=search_term) |
                        Q(product__brand__iexact=search_term)
                    )
                else:
                    fashion_qs = fashion_qs.filter(
                        Q(product__name__icontains=search_term) |
                        Q(product__brand__icontains=search_term) |
                        Q(product__category__category_name__icontains=search_term) |
                        Q(product__description__icontains=search_term)
                    )

            if price_search:
                try:
                    price_val = float(price_search)
                    fashion_qs = fashion_qs.filter(selling_price=price_val)
                except ValueError:
                    pass

            fashion_variants = fashion_qs.filter(is_active=True).order_by(
                'product__name', 'sku'
            )[:remaining]

            for variant in fashion_variants:
                product = variant.product
                category = getattr(product, 'category', None)

                profit_margin = None
                if variant.original_cost and variant.selling_price:
                    profit_margin = float(variant.selling_price) - float(variant.original_cost)

                expiry_status = None
                if variant.expiry_date:
                    from datetime import date
                    today = date.today()
                    days_to_expiry = (variant.expiry_date - today).days
                    if days_to_expiry < 0:
                        expiry_status = "Expired"
                    elif days_to_expiry <= 30:
                        expiry_status = f"Expires in {days_to_expiry} days"
                    else:
                        expiry_status = "Fresh"

                results.append({
                    'variant_id': variant.variant_id,
                    'sku': variant.sku,
                    'net_weight': variant.net_weight,
                    'net_weight_unit': variant.net_weight_unit,
                    'size': variant.size,
                    'original_cost': float(variant.original_cost) if variant.original_cost else None,
                    'selling_price': float(variant.selling_price) if variant.selling_price else None,
                    'charges': float(variant.charges) if variant.charges else None,
                    'profit_margin': profit_margin,
                    'stock': variant.stock if variant.stock is not None else variant.stock_qty,
                    'mfg_date': variant.mfg_date.isoformat() if variant.mfg_date else None,
                    'expiry_date': variant.expiry_date.isoformat() if variant.expiry_date else None,
                    'expiry_status': expiry_status,
                    'is_active': variant.is_active,
                    'variant_created_at': variant.created_at.isoformat() if variant.created_at else None,
                    'variant_updated_at': variant.updated_at.isoformat() if variant.updated_at else None,
                    'reference_table': 'fashion_product_variants',
                    'reference_id': getattr(product, 'product_id', None),
                    'product': {
                        'product_id': getattr(product, 'product_id', None),
                        'product_name': getattr(product, 'name', None),
                        'brand_name': getattr(product, 'brand', None),
                        'sub_category': getattr(product, 'subcategory', None),
                        'description': getattr(product, 'description', None),
                        'main_image': get_clean_image_url(getattr(product, 'main_image', None)),
                        'is_organic': None,
                        'rating': float(product.rating) if getattr(product, 'rating', None) else None,
                        'created_at': product.created_at.isoformat() if getattr(product, 'created_at', None) else None,
                        'updated_at': product.updated_at.isoformat() if getattr(product, 'updated_at', None) else None,
                    },
                    'category': {
                        'category_id': getattr(category, 'category_id', None) if category else None,
                        'category_name': getattr(category, 'category_name', None) if category else None,
                        'gst_rate': float(getattr(product, 'gst_rate_default', 0) or 0) if product else 0.0,
                        'category_image': get_clean_image_url(getattr(category, 'category_image', None)) if category else None,
                    },
                    'business': {
                        'business_id': variant.business_id.business_id if getattr(variant, 'business_id_id', None) else None,
                        'business_name': variant.business_id.businessName if getattr(variant, 'business_id_id', None) else None,
                    }
                })
        # Then, if searching by name, include MenuItems and productItems to fill remaining slots
        if search_term:
            remaining = max(0, limit - len(results))

            # MenuItems (restaurant menus)
            if remaining > 0:
                menu_qs = MenuItems.objects.filter(is_active=True, status=True)
                if included_business_ids:
                    menu_qs = menu_qs.filter(business_id__business_id__in=included_business_ids)
                if exact_match:
                    menu_qs = menu_qs.filter(item_name__iexact=search_term)
                else:
                    from django.db.models import Q
                    menu_qs = menu_qs.filter(
                        Q(item_name__icontains=search_term) |
                        Q(item_category__icontains=search_term) |
                        Q(description__icontains=search_term)
                    )
                
                if price_search:
                    try:
                        price_val = float(price_search)
                        menu_qs = menu_qs.filter(selling_price=price_val)
                    except ValueError:
                        pass
                menu_qs = menu_qs.order_by('item_name')[:remaining]

                for mi in menu_qs:
                    # Profit margin if possible
                    pm = None
                    if mi.original_cost and mi.selling_price:
                        pm = float(mi.selling_price) - float(mi.original_cost)
                    results.append({
                        'variant_id': mi.item_id,
                        'sku': None,
                        'net_weight': None,
                        'net_weight_unit': None,
                        'size': None,
                        'original_cost': float(mi.original_cost) if mi.original_cost else None,
                        'selling_price': float(mi.selling_price) if mi.selling_price else None,
                        'charges': float(mi.charges) if mi.charges else None,
                        'profit_margin': pm,
                        'stock': mi.quantity if mi.quantity is not None else 0,
                        'mfg_date': None,
                        'expiry_date': None,
                        'expiry_status': None,
                        'is_active': mi.is_active,
                        'variant_created_at': mi.created_at.isoformat() if mi.created_at else None,
                        'variant_updated_at': mi.updated_at.isoformat() if mi.updated_at else None,
                        'reference_table': 'menuItems',
                        'reference_id': mi.item_id,
                        'product': {
                            'product_id': mi.item_id,
                            'product_name': mi.item_name,
                            'brand_name': None,
                            'sub_category': None,
                            'description': mi.description,
                            'main_image': get_clean_image_url(mi.item_image),
                            'is_organic': None,
                            'rating': None,
                            'created_at': mi.created_at.isoformat() if mi.created_at else None,
                            'updated_at': mi.updated_at.isoformat() if mi.updated_at else None,
                        },
                        'category': {
                            'category_id': None,
                            'category_name': mi.item_category,
                            'gst_rate': float(mi.gst) if mi.gst else 0.0,
                            'category_image': None,
                        },
                        'business': {
                            'business_id': mi.business_id.business_id,
                            'business_name': mi.business_id.businessName,
                        }
                    })

            # productItems (generic products)
            remaining = max(0, limit - len(results))
            if remaining > 0:
                gi_qs = productItems.objects.filter(is_active=True, status=True)
                if included_business_ids:
                    gi_qs = gi_qs.filter(business_id__business_id__in=included_business_ids)
                if exact_match:
                    gi_qs = gi_qs.filter(item_name__iexact=search_term)
                else:
                    from django.db.models import Q
                    gi_qs = gi_qs.filter(
                        Q(item_name__icontains=search_term) |
                        Q(item_category__icontains=search_term) |
                        Q(description__icontains=search_term)
                    )

                if price_search:
                    try:
                        price_val = float(price_search)
                        gi_qs = gi_qs.filter(selling_price=price_val)
                    except ValueError:
                        pass
                gi_qs = gi_qs.order_by('item_name')[:remaining]

                for pi in gi_qs:
                    pm = None
                    if pi.original_cost and pi.selling_price:
                        pm = float(pi.selling_price) - float(pi.original_cost)
                    results.append({
                        'variant_id': pi.item_id,
                        'sku': None,
                        'net_weight': None,
                        'net_weight_unit': pi.unit,
                        'size': pi.size,
                        'original_cost': float(pi.original_cost) if pi.original_cost else None,
                        'selling_price': float(pi.selling_price) if pi.selling_price else None,
                        'charges': float(pi.charges) if pi.charges else None,
                        'profit_margin': pm,
                        'stock': pi.stock if pi.stock is not None else 0,
                        'mfg_date': pi.mfg_data.isoformat() if pi.mfg_data else None,
                        'expiry_date': pi.expiry_date.isoformat() if pi.expiry_date else None,
                        'expiry_status': None,
                        'is_active': pi.is_active,
                        'variant_created_at': pi.created_at.isoformat() if pi.created_at else None,
                        'variant_updated_at': pi.updated_at.isoformat() if pi.updated_at else None,
                        'reference_table': 'GroceryItems',
                        'reference_id': pi.item_id,
                        'product': {
                            'product_id': pi.item_id,
                            'product_name': pi.item_name,
                            'brand_name': None,
                            'sub_category': None,
                            'description': pi.description,
                            'main_image': get_clean_image_url(pi.item_image),
                            'is_organic': pi.is_organic,
                            'rating': float(pi.rating) if pi.rating else None,
                            'created_at': pi.created_at.isoformat() if pi.created_at else None,
                            'updated_at': pi.updated_at.isoformat() if pi.updated_at else None,
                        },
                        'category': {
                            'category_id': None,
                            'category_name': pi.item_category,
                            'gst_rate': float(pi.gst) if pi.gst else 0.0,
                            'category_image': None,
                        },
                        'business': {
                            'business_id': pi.business_id.business_id,
                            'business_name': pi.business_id.businessName,
                        }
                    })

        # If no results from any source
        if not results:
            return Response({
                'message': 'No products found with the given search criteria',
                'sku_searched': sku,
                'search_term': search_term,
                'exact_match': exact_match,
                'business_id': business_id,
                'included_businesses': included_business_ids,
                'results': []
            }, status=status.HTTP_200_OK)

        return Response({
            'message': f'Found {len(results)} product(s) matching search criteria',
            'sku_searched': sku,
            'search_term': search_term,
            'price': price_search,
            'exact_match': exact_match,
            'business_id': business_id,
            'included_businesses': included_business_ids,
            'results_count': len(results),
            'results': results
        }, status=status.HTTP_200_OK)
        
    except Exception as e:
        return Response({
            'error': 'An error occurred while searching for products by SKU',
            'details': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['POST'])
def create_supplier(request, business_id):
    """
    Create a new supplier for a business.
    
    Expected payload:
    {
        "business_id": "KIR1234567890",
        "supplier_code": "SUP001",  // optional
        "supplier_name": "ABC Suppliers Ltd",
        "contact_person": "John Doe",  // optional
        "email": "contact@abcsuppliers.com",  // optional
        "phone": "+1234567890",  // optional
        "address": "123 Business Street",  // optional
        "city": "Business City",  // optional
        "state": "Business State",  // optional
        "country": "Business Country",  // optional
        "postal_code": "12345",  // optional
        "product_supplied": "Raw materials, Components",  // optional
        "payment_terms": "Net 30",  // optional
        "bank_details_id": 123,  // optional
        "gst_number": "GST123456789",  // optional
        "tax_percentage": 18.00,  // optional
        "status": "Active",  // optional, defaults to 'Active'
        "notes": "Reliable supplier"  // optional
    }
    """
    try:
        data = request.data.copy()
        
        # business_id comes from URL parameter now
        # Add it to data for serializer
        data['business_id'] = business_id
        
        # Validate business exists
        try:
            business = Business.objects.get(business_id=business_id)
        except Business.DoesNotExist:
            return Response({
                'error': f'Business with business_id {business_id} does not exist'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Validate required fields
        if not data.get('supplier_name'):
            return Response({
                'error': 'supplier_name is required'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Generate supplier_code if not provided
        if not data.get('supplier_code'):
            import random
            import string
            while True:
                code = 'SUP' + ''.join(random.choices(string.digits, k=6))
                if not Suppliers.objects.filter(supplier_code=code, business_id=business).exists():
                    data['supplier_code'] = code
                    break
        
        # Validate supplier_code uniqueness within business
        supplier_code = data.get('supplier_code')
        if Suppliers.objects.filter(supplier_code=supplier_code, business_id=business).exists():
            return Response({
                'error': f'Supplier with code {supplier_code} already exists for this business'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Create supplier using serializer, and optionally create bank details
        serializer = SuppliersSerializer(data=data, context={'request': request})
        if serializer.is_valid():
            with transaction.atomic():
                supplier = serializer.save()

                # Parse optional bank_details from payload (can be dict, list, or JSON string)
                bank_payload = request.data.get('bank_details') or data.get('bank_details')
                created_primary_id = None
                if bank_payload:
                    if isinstance(bank_payload, str):
                        try:
                            bank_payload = json.loads(bank_payload)
                        except Exception:
                            return Response({'error': 'bank_details must be valid JSON'}, status=status.HTTP_400_BAD_REQUEST)

                    entries = bank_payload if isinstance(bank_payload, list) else [bank_payload]
                    for entry in entries:
                        # Required fields according to schema
                        if not entry.get('bank_name') or not entry.get('account_holder_name') or not entry.get('account_number'):
                            return Response({'error': 'bank_details requires bank_name, account_holder_name, and account_number'}, status=status.HTTP_400_BAD_REQUEST)

                        entry_status = entry.get('status') or 'Active'
                        requested_primary = bool(entry.get('is_primary')) if 'is_primary' in entry else False
                        if str(entry_status).lower() != 'active':
                            requested_primary = False

                        rec = SupplierBankDetails.objects.create(
                            supplier_id=supplier,
                            business_id=business,
                            bank_name=entry.get('bank_name'),
                            account_holder_name=entry.get('account_holder_name'),
                            account_number=entry.get('account_number'),
                            ifsc_code=entry.get('ifsc_code'),
                            branch_name=entry.get('branch_name'),
                            upi_id=entry.get('upi_id'),
                            is_primary=requested_primary,
                            status=entry_status,
                        )

                        if rec.is_primary and str(rec.status).lower() == 'active':
                            created_primary_id = rec.bank_details_id
                            SupplierBankDetails.objects.filter(
                                supplier_id=supplier,
                                business_id=business,
                            ).exclude(bank_details_id=rec.bank_details_id).update(is_primary=False)

                    # Ensure there is a primary active bank account if any active accounts exist
                    if not created_primary_id:
                        primary_obj = SupplierBankDetails.objects.filter(
                            supplier_id=supplier,
                            business_id=business,
                            status__iexact='Active',
                        ).order_by('bank_details_id').first()
                        if primary_obj:
                            SupplierBankDetails.objects.filter(
                                supplier_id=supplier,
                                business_id=business,
                            ).exclude(bank_details_id=primary_obj.bank_details_id).update(is_primary=False)
                            if not primary_obj.is_primary:
                                primary_obj.is_primary = True
                                primary_obj.save(update_fields=['is_primary'])
                            created_primary_id = primary_obj.bank_details_id

                    # Update supplier.bank_details_id to the primary bank record if present
                    if created_primary_id:
                        Suppliers.objects.filter(pk=supplier.pk).update(bank_details_id=created_primary_id)
                        supplier.bank_details_id = created_primary_id

                # Compose response including bank details
                bank_details_list = [
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
                        'created_at': acc.created_at.isoformat(),
                        'updated_at': acc.updated_at.isoformat(),
                    }
                    for acc in SupplierBankDetails.objects.filter(supplier_id=supplier, status__iexact='Active').order_by('-is_primary', 'bank_details_id')
                ]

                return Response({
                    'message': 'Supplier created successfully',
                    'supplier': {
                        'supplier_id': supplier.supplier_id,
                        'business_id': supplier.business_id.business_id,
                        'supplier_code': supplier.supplier_code,
                        'supplier_name': supplier.supplier_name,
                        'contact_person': supplier.contact_person,
                        'email': supplier.email,
                        'phone': supplier.phone,
                        'address': supplier.address,
                        'city': supplier.city,
                        'state': supplier.state,
                        'country': supplier.country,
                        'postal_code': supplier.postal_code,
                        'product_supplied': supplier.product_supplied,
                        'payment_terms': supplier.payment_terms,
                        'bank_details_id': supplier.bank_details_id,
                        'gst_number': supplier.gst_number,
                        'tax_percentage': float(supplier.tax_percentage) if supplier.tax_percentage else None,
                        'status': supplier.status,
                        'notes': supplier.notes,
                        'created_at': supplier.created_at.isoformat(),
                        'updated_at': supplier.updated_at.isoformat(),
                        'bank_details': bank_details_list,
                    }
                }, status=status.HTTP_201_CREATED)
        else:
            return Response({
                'error': 'Validation failed',
                'details': serializer.errors
            }, status=status.HTTP_400_BAD_REQUEST)
            
    except Exception as e:
        return Response({
            'error': 'An error occurred while creating supplier',
            'details': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
def get_suppliers(request, business_id):
    """
    Get all suppliers for a business with optional filtering.
    
    URL parameters:
    - business_id (required): Business ID from URL
    
    Query parameters:
    - status (optional): Filter by status (Active, Inactive, Blacklisted)
    - search (optional): Search in supplier_name, supplier_code, contact_person
    - limit (optional): Number of results per page (default: 50)
    - offset (optional): Offset for pagination (default: 0)
    """
    try:
        # Validate business exists
        try:
            business = Business.objects.get(business_id=business_id)
        except Business.DoesNotExist:
            return Response({
                'error': f'Business with business_id {business_id} does not exist'
            }, status=status.HTTP_400_BAD_REQUEST)

        # Get filter parameters
        status_filter = request.GET.get('status')
        search_query = request.GET.get('search')
        limit = int(request.GET.get('limit', 50))
        offset = int(request.GET.get('offset', 0))

        qs = Suppliers.objects.filter(business_id=business)
        if status_filter:
            qs = qs.filter(status=status_filter)
        if search_query:
            from django.db.models import Q
            qs = qs.filter(
                Q(supplier_name__icontains=search_query) |
                Q(supplier_code__icontains=search_query) |
                Q(contact_person__icontains=search_query)
            )

        qs = qs.order_by('supplier_name')
        suppliers = list(qs[offset:offset + limit])
        serializer = SuppliersSerializer(suppliers, many=True, context={'request': request})

        return Response({
            'suppliers': serializer.data,
            'count': len(serializer.data),
            'business_id': business_id,
            'filters': {
                'status': status_filter,
                'search': search_query,
                'limit': limit,
                'offset': offset,
            }
        }, status=status.HTTP_200_OK)

    except ValueError:
        return Response({'error': 'Invalid limit or offset parameter'}, status=status.HTTP_400_BAD_REQUEST)
    except Exception as e:
        return Response({
            'error': 'An error occurred while fetching suppliers',
            'details': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
def get_supplier_by_id(request, business_id, supplier_id):
    """
    Get a specific supplier by ID.
    
    URL parameters:
    - business_id: The business ID
    - supplier_id: The supplier ID
    """
    try:
        # Validate business exists
        try:
            business = Business.objects.get(business_id=business_id)
        except Business.DoesNotExist:
            return Response({
                'error': f'Business with business_id {business_id} does not exist'
            }, status=status.HTTP_400_BAD_REQUEST)

        try:
            supplier = Suppliers.objects.get(supplier_id=supplier_id, business_id=business)
        except Suppliers.DoesNotExist:
            return Response({
                'error': f'Supplier with ID {supplier_id} not found for this business'
            }, status=status.HTTP_404_NOT_FOUND)

        include_inactive_bank_details = str(request.GET.get('include_inactive_bank_details', '')).lower() in ('1', 'true', 'yes')
        bank_qs = SupplierBankDetails.objects.filter(supplier_id=supplier)
        if not include_inactive_bank_details:
            bank_qs = bank_qs.filter(status__iexact='Active')
        bank_details_list = [
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
                'created_at': acc.created_at.isoformat(),
                'updated_at': acc.updated_at.isoformat(),
            }
            for acc in bank_qs.order_by('-is_primary', 'bank_details_id')
        ]

        return Response({
            'supplier': {
                'supplier_id': supplier.supplier_id,
                'business_id': supplier.business_id.business_id,
                'supplier_code': supplier.supplier_code,
                'supplier_name': supplier.supplier_name,
                'contact_person': supplier.contact_person,
                'email': supplier.email,
                'phone': supplier.phone,
                'address': supplier.address,
                'city': supplier.city,
                'state': supplier.state,
                'country': supplier.country,
                'postal_code': supplier.postal_code,
                'product_supplied': supplier.product_supplied,
                'payment_terms': supplier.payment_terms,
                'bank_details_id': supplier.bank_details_id,
                'gst_number': supplier.gst_number,
                'tax_percentage': float(supplier.tax_percentage) if supplier.tax_percentage else None,
                'status': supplier.status,
                'notes': supplier.notes,
                'created_at': supplier.created_at.isoformat(),
                'updated_at': supplier.updated_at.isoformat(),
                'bank_details': bank_details_list,
            }
        }, status=status.HTTP_200_OK)

    except Exception as e:
        return Response({
            'error': 'An error occurred while fetching supplier',
            'details': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['PUT'])
def update_supplier(request, business_id, supplier_id):
    """
    Update a supplier.
    
    URL parameters:
    - business_id: The business ID
    - supplier_id: The supplier ID
    
    Expected payload (any subset of fields):
    {
        "supplier_code": "SUP001",
        "supplier_name": "ABC Suppliers Ltd",
        "contact_person": "John Doe",
        "email": "contact@abcsuppliers.com",
        "phone": "+1234567890",
        "address": "123 Business Street",
        "city": "Business City",
        "state": "Business State",
        "country": "Business Country",
        "postal_code": "12345",
        "product_supplied": "Raw materials, Components",
        "payment_terms": "Net 30",
        "bank_details_id": 123,
        "gst_number": "GST123456789",
        "tax_percentage": 18.00,
        "status": "Active",
        "notes": "Reliable supplier"
    }
    """
    try:
        data = request.data.copy()
        
        # business_id comes from URL parameter now
        # Add it to data for serializer
        data['business_id'] = business_id

        bank_payload = request.data.get('bank_details') or data.get('bank_details')
        if not bank_payload:
            bank_field_names = [
                'bank_details_id',
                'bank_name',
                'account_holder_name',
                'account_number',
                'ifsc_code',
                'branch_name',
                'upi_id',
                'is_primary',
                'status',
            ]
            if any(k in request.data for k in bank_field_names):
                bank_payload = {}
                for k in bank_field_names:
                    if k in request.data:
                        bank_payload[k] = request.data.get(k)

        if 'bank_details' in data:
            data.pop('bank_details', None)
        for k in ['bank_name', 'account_holder_name', 'account_number', 'ifsc_code', 'branch_name', 'upi_id', 'is_primary', 'status']:
            if k in data:
                data.pop(k, None)

        # Validate business exists
        try:
            business = Business.objects.get(business_id=business_id)
        except Business.DoesNotExist:
            return Response({
                'error': f'Business with business_id {business_id} does not exist'
            }, status=status.HTTP_400_BAD_REQUEST)

        # Get supplier
        try:
            supplier = Suppliers.objects.get(supplier_id=supplier_id, business_id=business)
        except Suppliers.DoesNotExist:
            return Response({
                'error': f'Supplier with ID {supplier_id} not found for this business'
            }, status=status.HTTP_404_NOT_FOUND)

        # Check supplier_code uniqueness if being updated
        supplier_code = data.get('supplier_code')
        if supplier_code and supplier_code != supplier.supplier_code:
            if Suppliers.objects.filter(supplier_code=supplier_code, business_id=business).exclude(supplier_id=supplier_id).exists():
                return Response({
                    'error': f'Supplier with code {supplier_code} already exists for this business'
                }, status=status.HTTP_400_BAD_REQUEST)

        # Update supplier using serializer
        serializer = SuppliersSerializer(supplier, data=data, partial=True, context={'request': request})
        if not serializer.is_valid():
            return Response({
                'error': 'Validation failed',
                'details': serializer.errors
            }, status=status.HTTP_400_BAD_REQUEST)

        with transaction.atomic():
            updated_supplier = serializer.save()

            primary_bank_id = None

            if bank_payload:
                if isinstance(bank_payload, str):
                    try:
                        bank_payload = json.loads(bank_payload)
                    except Exception:
                        return Response({'error': 'bank_details must be valid JSON'}, status=status.HTTP_400_BAD_REQUEST)

                entries = bank_payload if isinstance(bank_payload, list) else [bank_payload]
                for entry in entries:
                    if not isinstance(entry, dict):
                        return Response({'error': 'bank_details must be an object or list of objects'}, status=status.HTTP_400_BAD_REQUEST)

                    entry_bank_id = entry.get('bank_details_id')
                    bank_obj = None
                    if entry_bank_id:
                        try:
                            bank_obj = SupplierBankDetails.objects.get(
                                bank_details_id=entry_bank_id,
                                supplier_id=updated_supplier,
                                business_id=business,
                            )
                        except SupplierBankDetails.DoesNotExist:
                            return Response({
                                'error': f'bank_details_id {entry_bank_id} not found for this supplier'
                            }, status=status.HTTP_404_NOT_FOUND)

                    if not bank_obj:
                        # Only create if no bank_details_id provided; otherwise update existing
                        if not entry.get('bank_name') or not entry.get('account_holder_name') or not entry.get('account_number'):
                            return Response({
                                'error': 'bank_details requires bank_name, account_holder_name, and account_number'
                            }, status=status.HTTP_400_BAD_REQUEST)

                        entry_status = entry.get('status') or 'Active'
                        requested_primary = bool(entry.get('is_primary')) if 'is_primary' in entry else False
                        if str(entry_status).lower() != 'active':
                            requested_primary = False
                        bank_obj = SupplierBankDetails.objects.create(
                            supplier_id=updated_supplier,
                            business_id=business,
                            bank_name=entry.get('bank_name'),
                            account_holder_name=entry.get('account_holder_name'),
                            account_number=entry.get('account_number'),
                            ifsc_code=entry.get('ifsc_code'),
                            branch_name=entry.get('branch_name'),
                            upi_id=entry.get('upi_id'),
                            is_primary=requested_primary,
                            status=entry_status,
                        )
                    else:
                        # Update only provided fields
                        if 'bank_name' in entry:
                            bank_obj.bank_name = entry.get('bank_name')
                        if 'account_holder_name' in entry:
                            bank_obj.account_holder_name = entry.get('account_holder_name')
                        if 'account_number' in entry:
                            bank_obj.account_number = entry.get('account_number')
                        if 'ifsc_code' in entry:
                            bank_obj.ifsc_code = entry.get('ifsc_code')
                        if 'branch_name' in entry:
                            bank_obj.branch_name = entry.get('branch_name')
                        if 'upi_id' in entry:
                            bank_obj.upi_id = entry.get('upi_id')
                        if 'status' in entry:
                            bank_obj.status = entry.get('status')
                        if 'is_primary' in entry:
                            bank_obj.is_primary = bool(entry.get('is_primary'))

                        # If bank account is being inactivated, ensure it isn't primary
                        if str(getattr(bank_obj, 'status', '')).lower() != 'active':
                            bank_obj.is_primary = False
                        bank_obj.save()

                    # Track primary bank; ensure only one primary across all entries
                    if getattr(bank_obj, 'is_primary', False) and str(getattr(bank_obj, 'status', '')).lower() == 'active':
                        if primary_bank_id is None:
                            primary_bank_id = bank_obj.bank_details_id
                        SupplierBankDetails.objects.filter(
                            supplier_id=updated_supplier,
                            business_id=business,
                        ).exclude(bank_details_id=bank_obj.bank_details_id).update(is_primary=False)

            if not primary_bank_id and request.data.get('bank_details_id'):
                try:
                    requested_id = int(request.data.get('bank_details_id'))
                except Exception:
                    requested_id = None
                if requested_id:
                    try:
                        bank_obj = SupplierBankDetails.objects.get(
                            bank_details_id=requested_id,
                            supplier_id=updated_supplier,
                            business_id=business,
                        )
                    except SupplierBankDetails.DoesNotExist:
                        return Response({
                            'error': f'bank_details_id {requested_id} not found for this supplier'
                        }, status=status.HTTP_404_NOT_FOUND)

                    if str(getattr(bank_obj, 'status', '')).lower() != 'active':
                        return Response({
                            'error': f'bank_details_id {requested_id} is not Active and cannot be set as primary'
                        }, status=status.HTTP_400_BAD_REQUEST)

                    SupplierBankDetails.objects.filter(
                        supplier_id=updated_supplier,
                        business_id=business,
                    ).exclude(bank_details_id=bank_obj.bank_details_id).update(is_primary=False)
                    if not bank_obj.is_primary:
                        bank_obj.is_primary = True
                        bank_obj.save(update_fields=['is_primary'])
                    primary_bank_id = bank_obj.bank_details_id

            # Reconcile primary bank among ACTIVE accounts and keep supplier.bank_details_id consistent
            active_bank_qs = SupplierBankDetails.objects.filter(
                supplier_id=updated_supplier,
                business_id=business,
                status__iexact='Active',
            )
            if primary_bank_id:
                active_primary = active_bank_qs.filter(bank_details_id=primary_bank_id).first()
                if not active_primary:
                    primary_bank_id = None

            if not primary_bank_id:
                # Prefer existing supplier bank_details_id if it points to an active bank
                existing_primary = None
                if getattr(updated_supplier, 'bank_details_id', None):
                    existing_primary = active_bank_qs.filter(bank_details_id=updated_supplier.bank_details_id).first()
                if existing_primary:
                    primary_bank_id = existing_primary.bank_details_id
                    if not existing_primary.is_primary:
                        existing_primary.is_primary = True
                        existing_primary.save(update_fields=['is_primary'])
                    SupplierBankDetails.objects.filter(
                        supplier_id=updated_supplier,
                        business_id=business,
                    ).exclude(bank_details_id=existing_primary.bank_details_id).update(is_primary=False)
                else:
                    any_active = active_bank_qs.order_by('bank_details_id').first()
                    if any_active:
                        primary_bank_id = any_active.bank_details_id
                        if not any_active.is_primary:
                            any_active.is_primary = True
                            any_active.save(update_fields=['is_primary'])
                        SupplierBankDetails.objects.filter(
                            supplier_id=updated_supplier,
                            business_id=business,
                        ).exclude(bank_details_id=any_active.bank_details_id).update(is_primary=False)

            if primary_bank_id:
                Suppliers.objects.filter(pk=updated_supplier.pk).update(bank_details_id=primary_bank_id)
                updated_supplier.bank_details_id = primary_bank_id
            else:
                # No active bank accounts left
                Suppliers.objects.filter(pk=updated_supplier.pk).update(bank_details_id=None)
                updated_supplier.bank_details_id = None

            include_inactive_bank_details = str(request.GET.get('include_inactive_bank_details', '')).lower() in ('1', 'true', 'yes')
            bank_qs = SupplierBankDetails.objects.filter(supplier_id=updated_supplier)
            if not include_inactive_bank_details:
                bank_qs = bank_qs.filter(status__iexact='Active')
            bank_details_list = [
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
                    'created_at': acc.created_at.isoformat(),
                    'updated_at': acc.updated_at.isoformat(),
                }
                for acc in bank_qs.order_by('-is_primary', 'bank_details_id')
            ]

            return Response({
                'message': 'Supplier updated successfully',
                'supplier': {
                    'supplier_id': updated_supplier.supplier_id,
                    'business_id': updated_supplier.business_id.business_id,
                    'supplier_code': updated_supplier.supplier_code,
                    'supplier_name': updated_supplier.supplier_name,
                    'contact_person': updated_supplier.contact_person,
                    'email': updated_supplier.email,
                    'phone': updated_supplier.phone,
                    'address': updated_supplier.address,
                    'city': updated_supplier.city,
                    'state': updated_supplier.state,
                    'country': updated_supplier.country,
                    'postal_code': updated_supplier.postal_code,
                    'product_supplied': updated_supplier.product_supplied,
                    'payment_terms': updated_supplier.payment_terms,
                    'bank_details_id': updated_supplier.bank_details_id,
                    'gst_number': updated_supplier.gst_number,
                    'tax_percentage': float(updated_supplier.tax_percentage) if updated_supplier.tax_percentage else None,
                    'status': updated_supplier.status,
                    'notes': updated_supplier.notes,
                    'created_at': updated_supplier.created_at.isoformat(),
                    'updated_at': updated_supplier.updated_at.isoformat(),
                    'bank_details': bank_details_list,
                }
            }, status=status.HTTP_200_OK)

    except Exception as e:
        return Response({
            'error': 'An error occurred while updating supplier',
            'details': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['DELETE'])
def delete_supplier(request, business_id, supplier_id):
    """
    Delete a supplier (soft delete by setting status to 'Inactive').
    
    URL parameters:
    - business_id: The business ID
    - supplier_id: The supplier ID
    
    Query parameters:
    - hard_delete (optional): Set to 'true' for permanent deletion
    """
    try:
        # Validate business exists
        try:
            business = Business.objects.get(business_id=business_id)
        except Business.DoesNotExist:
            return Response({
                'error': f'Business with business_id {business_id} does not exist'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Get supplier
        try:
            supplier = Suppliers.objects.get(supplier_id=supplier_id, business_id=business)
        except Suppliers.DoesNotExist:
            return Response({
                'error': f'Supplier with ID {supplier_id} not found for this business'
            }, status=status.HTTP_404_NOT_FOUND)
        
        # Check if hard delete is requested
        hard_delete = request.GET.get('hard_delete', '').lower() == 'true'
        
        if hard_delete:
            # Check if supplier is referenced in purchases or expenses
            purchase_count = Purchases.objects.filter(supplier_id=supplier).count()
            expense_count = Expenses.objects.filter(supplier_id=supplier_id).count()
            
            if purchase_count > 0 or expense_count > 0:
                return Response({
                    'error': f'Cannot delete supplier. It is referenced in {purchase_count} purchase(s) and {expense_count} expense(s). Use soft delete instead.'
                }, status=status.HTTP_400_BAD_REQUEST)
            
            # Permanent deletion
            supplier_name = supplier.supplier_name
            supplier.delete()
            
            return Response({
                'message': f'Supplier "{supplier_name}" permanently deleted'
            }, status=status.HTTP_200_OK)
        else:
            # Soft delete - set status to Inactive
            supplier.status = 'Inactive'
            supplier.save()
            
            return Response({
                'message': f'Supplier "{supplier.supplier_name}" deactivated (soft delete)',
                'supplier_id': supplier.supplier_id,
                'status': supplier.status
            }, status=status.HTTP_200_OK)
            
    except Exception as e:
        return Response({
            'error': 'An error occurred while deleting supplier',
            'details': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)