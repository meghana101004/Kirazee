import json
import uuid
from decimal import Decimal
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from django.shortcuts import get_object_or_404
from django.db import transaction, connection
from django.utils import timezone

from .models import PurchaseRequisition, PurchaseRequisitionLog
from .serializers import PurchaseRequisitionSerializer, PurchaseRequisitionLogSerializer
from kirazee_app.models import Business, Registration


@api_view(['POST'])
def create_purchase_requisition(request):
    """
    Create a new purchase requisition (only if item exists in inventory)
    Query parameters:
    - user_id (required)
    - business_id (required)
    
    Expected payload:
    {
        "item_name": "Notebook",
        "quantity": 50,
        "unit": "pieces",
        "purpose": "Monthly office supply"
    }
    """
    try:
        user_id = request.GET.get('user_id')
        business_id = request.GET.get('business_id')
        
        if not user_id or not business_id:
            return Response({
                'error': 'user_id and business_id are required URL parameters'
            }, status=status.HTTP_400_BAD_REQUEST)

        # Validate user and business
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

        # Check if item exists in inventory before creating requisition
        from .models import Inventory
        try:
            inventory_item = Inventory.objects.filter(
                business_id=business,
                item_name__iexact=request.data.get('item_name', '').strip()
            ).only('item_name', 'current_stock', 'sku', 'reference_table', 'reference_id').first()
            
            if not inventory_item:
                inventory_count = Inventory.objects.filter(business_id=business).count()
                
                return Response({
                    'error': f'Item "{request.data.get("item_name")}" not found in inventory. Cannot create requisition for non-inventory items.',
                    'suggestion': 'Please add this item to inventory first, then create a new requisition.',
                    'debug_info': {
                        'searched_item': request.data.get('item_name'),
                        'business_id': business_id,
                        'total_inventory_items': inventory_count,
                        'available_items': list(Inventory.objects.filter(business_id=business).values_list('item_name', flat=True)[:5])
                    }
                }, status=status.HTTP_400_BAD_REQUEST)
                
        except Exception as e:
            return Response({
                'error': 'Database query timeout while checking inventory',
                'details': str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        # Prepare data
        requisition_data = request.data.copy()
        requisition_data['user_id'] = user.user_id
        requisition_data['business_id'] = business.business_id

        serializer = PurchaseRequisitionSerializer(data=requisition_data)
        if serializer.is_valid():
            requisition = serializer.save()
            
            # Create log entry for request
            PurchaseRequisitionLog.objects.create(
                requisition=requisition,
                business_id=business,
                action='requested',
                action_by=user,
                reason=requisition.purpose
            )
            
            response_serializer = PurchaseRequisitionSerializer(requisition)
            return Response({
                'message': 'Purchase requisition created successfully',
                'requisition': response_serializer.data,
                'inventory_item': {
                    'item_name': inventory_item.item_name,
                    'current_stock': inventory_item.current_stock,
                    'sku': inventory_item.sku
                }
            }, status=status.HTTP_201_CREATED)
        else:
            return Response({
                'error': 'Validation failed',
                'details': serializer.errors
            }, status=status.HTTP_400_BAD_REQUEST)
            
    except Exception as e:
        return Response({
            'error': 'An error occurred while creating purchase requisition',
            'details': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
def get_purchase_requisitions(request):
    """
    Get purchase requisitions for a specific business
    Query parameters:
    - business_id (optional)
    - user_id (optional, filter by requester)
    - status (optional, filter by status)
    - limit (optional, default=50)
    - offset (optional, default=0)
    """
    try:
        business_id = request.GET.get('business_id')
        
        # Get filter parameters
        user_id = request.GET.get('user_id')
        status_filter = request.GET.get('status')
        limit = int(request.GET.get('limit', 50))
        offset = int(request.GET.get('offset', 0))
        
        # Build query
        requisitions = PurchaseRequisition.objects.all()
        
        if business_id:
            # Validate business if provided
            try:
                business = Business.objects.get(business_id=business_id)
                requisitions = requisitions.filter(business_id=business)
            except Business.DoesNotExist:
                return Response({
                    'error': f'Business with business_id {business_id} does not exist'
                }, status=status.HTTP_400_BAD_REQUEST)
        
        if user_id:
            requisitions = requisitions.filter(user_id__user_id=user_id)
        if status_filter:
            requisitions = requisitions.filter(status=status_filter)
        
        requisitions = requisitions[offset:offset+limit]
        
        serializer = PurchaseRequisitionSerializer(requisitions, many=True)
        
        return Response({
            'requisitions': serializer.data,
            'count': len(serializer.data)
        }, status=status.HTTP_200_OK)
        
    except ValueError as e:
        return Response({
            'error': 'Invalid limit or offset parameter'
        }, status=status.HTTP_400_BAD_REQUEST)
    except Exception as e:
        return Response({
            'error': 'An error occurred while fetching purchase requisitions',
            'details': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
def get_purchase_requisition_detail(request, purchase_req_id):
    """
    Get detailed information about a specific purchase requisition
    URL parameters:
    - purchase_req_id (required)
    Query parameters:
    - business_id (optional)
    """
    try:
        business_id = request.GET.get('business_id')

        # Get specific requisition
        if business_id:
            # Validate business if provided
            try:
                business = Business.objects.get(business_id=business_id)
            except Business.DoesNotExist:
                return Response({
                    'error': f'Business with business_id {business_id} does not exist'
                }, status=status.HTTP_400_BAD_REQUEST)

            # Get requisition filtered by business
            requisition = get_object_or_404(
                PurchaseRequisition,
                purchase_req_id=purchase_req_id,
                business_id=business
            )
        else:
            # Get requisition without business filter
            requisition = get_object_or_404(
                PurchaseRequisition,
                purchase_req_id=purchase_req_id
            )
        
        serializer = PurchaseRequisitionSerializer(requisition)
        
        return Response({
            'requisition': serializer.data
        }, status=status.HTTP_200_OK)
        
    except Exception as e:
        return Response({
            'error': 'An error occurred while fetching requisition details',
            'details': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['PUT'])
def approve_purchase_requisition(request, purchase_req_id):
    """
    Approve a purchase requisition
    URL parameters:
    - purchase_req_id (required)
    
    Expected payload (optional):
    {
        "business_id": "KIR147712008250351"
    }
    """
    try:
        business_id = request.data.get('business_id')

        # Get requisition
        if business_id:
            # Validate business if provided
            try:
                business = Business.objects.get(business_id=business_id)
            except Business.DoesNotExist:
                return Response({
                    'error': f'Business with business_id {business_id} does not exist'
                }, status=status.HTTP_400_BAD_REQUEST)

            # Get requisition filtered by business
            requisition = get_object_or_404(
                PurchaseRequisition,
                purchase_req_id=purchase_req_id,
                business_id=business
            )
        else:
            # Get requisition without business filter
            requisition = get_object_or_404(
                PurchaseRequisition,
                purchase_req_id=purchase_req_id
            )
        
        if requisition.status != 'pending':
            return Response({
                'error': f'Cannot approve requisition with status {requisition.status}'
            }, status=status.HTTP_400_BAD_REQUEST)

        # Reduce inventory stock before updating status
        try:
            from .models import Inventory
            inventory_item = Inventory.objects.get(
                business_id=requisition.business_id,
                item_name__iexact=requisition.item_name.strip()
            )
            
            if inventory_item.current_stock < requisition.quantity:
                return Response({
                    'error': f'Insufficient stock for {requisition.item_name}. Available: {inventory_item.current_stock}, Requested: {requisition.quantity}'
                }, status=status.HTTP_400_BAD_REQUEST)
            
            # Update inventory
            inventory_item.sold_stock = inventory_item.sold_stock + requisition.quantity
            inventory_item.save(update_fields=['sold_stock'])
            
            # Create inventory log
            with connection.cursor() as cursor:
                cursor.execute("""
                    INSERT INTO Inventory_Log (
                        inventory_id, business_id, sku, reference_table, reference_id, 
                        item_name, action, reason, old_stock, new_stock, user_id, changed_at
                    ) VALUES (
                        %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, CONVERT_TZ(NOW(), 'UTC', 'Asia/Kolkata')
                    )
                """, [
                    inventory_item.inventory_id,
                    requisition.business_id.business_id,
                    inventory_item.sku,
                    'PurchaseRequisition',
                    str(requisition.purchase_req_id),
                    requisition.item_name,
                    'REQUISITION',
                    f'Stock reduced via purchase requisition {requisition.requisition_number}',
                    json.dumps({
                        'sold_stock': inventory_item.sold_stock - requisition.quantity,
                        'current_stock': inventory_item.current_stock
                    }),
                    json.dumps({
                        'sold_stock': inventory_item.sold_stock,
                        'current_stock': inventory_item.current_stock - requisition.quantity
                    }),
                    request.user.id if hasattr(request, 'user') and request.user.is_authenticated else 1
                ])
                
        except Inventory.DoesNotExist:
            return Response({
                'error': f'Item "{requisition.item_name}" not found in inventory'
            }, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            return Response({
                'error': 'Failed to update inventory stock',
                'details': str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        # Update requisition status
        requisition.status = 'approved'
        requisition.save(update_fields=['status'])
        
        # Create log entry for approval
        approver = request.user if hasattr(request, 'user') and request.user.is_authenticated else requisition.user_id
        PurchaseRequisitionLog.objects.create(
            requisition=requisition,
            business_id=requisition.business_id,
            action='approved',
            action_by=approver,
            reason='Purchase requisition approved'
        )
        
        serializer = PurchaseRequisitionSerializer(requisition)
        return Response({
            'message': 'Purchase requisition approved successfully',
            'requisition': serializer.data
        }, status=status.HTTP_200_OK)
        
    except Exception as e:
        return Response({
            'error': 'An error occurred while approving purchase requisition',
            'details': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['PUT'])
def reject_purchase_requisition(request, purchase_req_id):
    """
    Reject a purchase requisition
    URL parameters:
    - purchase_req_id (required)
    
    Expected payload:
    {
        "business_id": "KIR147712008250351",
        "reason": "Insufficient budget"  # Required
    }
    """
    try:
        business_id = request.data.get('business_id')
        reason = request.data.get('reason')

        # Validate reason is required for rejection
        if not reason or not reason.strip():
            return Response({
                'error': 'Reason is required when rejecting a purchase requisition'
            }, status=status.HTTP_400_BAD_REQUEST)

        # Get requisition
        if business_id:
            # Validate business if provided
            try:
                business = Business.objects.get(business_id=business_id)
            except Business.DoesNotExist:
                return Response({
                    'error': f'Business with business_id {business_id} does not exist'
                }, status=status.HTTP_400_BAD_REQUEST)

            # Get requisition filtered by business
            requisition = get_object_or_404(
                PurchaseRequisition,
                purchase_req_id=purchase_req_id,
                business_id=business
            )
        else:
            # Get requisition without business filter
            requisition = get_object_or_404(
                PurchaseRequisition,
                purchase_req_id=purchase_req_id
            )
        
        if requisition.status != 'pending':
            return Response({
                'error': f'Cannot reject requisition with status {requisition.status}'
            }, status=status.HTTP_400_BAD_REQUEST)

        # Update requisition status
        requisition.status = 'rejected'
        requisition.save(update_fields=['status'])
        
        # Create log entry for rejection
        rejecter = request.user if hasattr(request, 'user') and request.user.is_authenticated else requisition.user_id
        PurchaseRequisitionLog.objects.create(
            requisition=requisition,
            business_id=requisition.business_id,
            action='rejected',
            action_by=rejecter,
            reason=reason
        )
        
        serializer = PurchaseRequisitionSerializer(requisition)
        return Response({
            'message': 'Purchase requisition rejected successfully',
            'requisition': serializer.data
        }, status=status.HTTP_200_OK)
        
    except Exception as e:
        return Response({
            'error': 'An error occurred while rejecting purchase requisition',
            'details': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
def get_requisition_logs(request, requisition_id):
    """
    Get audit logs for a specific purchase requisition
    URL parameters:
    - requisition_id (required)
    Query parameters:
    - business_id (optional)
    """
    try:
        business_id = request.GET.get('business_id')

        # Get logs
        if business_id:
            # Validate business if provided
            try:
                business = Business.objects.get(business_id=business_id)
            except Business.DoesNotExist:
                return Response({
                    'error': f'Business with business_id {business_id} does not exist'
                }, status=status.HTTP_400_BAD_REQUEST)

            # Get logs filtered by business
            logs = PurchaseRequisitionLog.objects.filter(
                requisition_id=requisition_id,
                business_id=business
            ).order_by('-action_date')
        else:
            # Get logs without business filter
            logs = PurchaseRequisitionLog.objects.filter(
                requisition_id=requisition_id
            ).order_by('-action_date')
        
        serializer = PurchaseRequisitionLogSerializer(logs, many=True)
        
        return Response({
            'logs': serializer.data,
            'count': len(serializer.data)
        }, status=status.HTTP_200_OK)
        
    except Exception as e:
        return Response({
            'error': 'An error occurred while fetching requisition logs',
            'details': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
def get_all_requisition_logs(request):
    """
    Get all audit logs for purchase requisitions
    Query parameters:
    - business_id (optional, filter by business)
    - action (optional, filter by action: requested, approved, rejected)
    - limit (optional, default=50)
    - offset (optional, default=0)
    """
    try:
        business_id = request.GET.get('business_id')
        action_filter = request.GET.get('action')
        limit = int(request.GET.get('limit', 50))
        offset = int(request.GET.get('offset', 0))
        
        # Build query
        logs = PurchaseRequisitionLog.objects.all()
        
        if business_id:
            logs = logs.filter(business_id__business_id=business_id)
        if action_filter:
            logs = logs.filter(action=action_filter)
        
        logs = logs.order_by('-action_date')[offset:offset+limit]
        
        serializer = PurchaseRequisitionLogSerializer(logs, many=True)
        
        return Response({
            'logs': serializer.data,
            'count': len(serializer.data)
        }, status=status.HTTP_200_OK)
        
    except ValueError as e:
        return Response({
            'error': 'Invalid limit or offset parameter'
        }, status=status.HTTP_400_BAD_REQUEST)
    except Exception as e:
        return Response({
            'error': 'An error occurred while fetching logs',
            'details': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


def _reduce_inventory_stock(item, approved_quantity, approver):
    """Reduce inventory stock when requisition is approved"""
    with connection.cursor() as cursor:
        # Try to find existing inventory
        cursor.execute("""
            SELECT inventory_id, opening_stock, purchased_stock, sold_stock, current_stock
            FROM Inventory 
            WHERE business_id = %s AND reference_table = %s AND reference_id = %s
        """, [
            item.business_id.business_id,
            item.reference_table,
            item.reference_id
        ])
        
        existing = cursor.fetchone()
        
        if existing:
            inventory_id, opening_stock, purchased_stock, sold_stock, current_stock = existing
            
            # Check if sufficient stock is available
            if current_stock < approved_quantity:
                raise ValueError(f'Insufficient stock for {item.item_name}. Available: {current_stock}, Requested: {approved_quantity}')
            
            # Update inventory (reduce from current_stock)
            new_sold_stock = sold_stock + approved_quantity
            
            cursor.execute("""
                UPDATE Inventory 
                SET sold_stock = %s, user_id = %s, last_updated = CONVERT_TZ(NOW(), 'UTC', 'Asia/Kolkata')
                WHERE inventory_id = %s
            """, [
                new_sold_stock, approver.id, inventory_id
            ])
            
            # Create inventory log
            old_stock_data = {
                'opening_stock': opening_stock,
                'purchased_stock': purchased_stock,
                'sold_stock': sold_stock,
                'current_stock': current_stock
            }
            
            new_stock_data = {
                'opening_stock': opening_stock,
                'purchased_stock': purchased_stock,
                'sold_stock': new_sold_stock,
                'current_stock': current_stock - approved_quantity
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
                'REQUISITION',
                f'Stock reduced via purchase requisition {item.requisition_id.requisition_number}',
                json.dumps(old_stock_data),
                json.dumps(new_stock_data),
                approver.id
            ])
        else:
            raise ValueError(f'No inventory record found for {item.item_name}')


def _log_requisition_action(requisition, action, old_data, new_data, actor):
    """Log requisition actions for audit trail"""
    log_data = {
        'requisition_id': requisition.requisition_id,
        'requisition_number': requisition.requisition_number,
        'status': requisition.status,
        'total_estimated_cost': str(requisition.total_estimated_cost),
        'items_count': requisition.items.count()
    }
    
    with connection.cursor() as cursor:
        cursor.execute("""
            INSERT INTO purchase_requisition_log (
                requisition_id, business_id, action, action_table, reason, 
                old_data, new_data, user_id, changed_at
            ) VALUES (
                %s, %s, %s, %s, %s, %s, %s, %s, CONVERT_TZ(NOW(), 'UTC', 'Asia/Kolkata')
            )
        """, [
            requisition.requisition_id,
            requisition.business_id.business_id,
            action,
            'PurchaseRequisition',
            new_data.get('reason', '') if isinstance(new_data, dict) else '',
            json.dumps(old_data) if old_data else None,
            json.dumps(log_data),
            actor.id
        ])


@api_view(['GET', 'PUT'])
def manager_approval_dashboard(request):
    """
    Manager Approval Dashboard - View and approve/reject pending requisitions
    GET: Get all pending requisitions for manager approval
    PUT: Bulk approve/reject multiple requisitions
    
    Query parameters for GET:
    - business_id (optional)
    - limit (optional, default=50)
    - offset (optional, default=0)
    
    Expected payload for PUT:
    {
        "requisitions": [
            {
                "purchase_req_id": 1,
                "action": "approved",
                "reason": "Approved - budget available"
            },
            {
                "purchase_req_id": 2, 
                "action": "rejected",
                "reason": "Insufficient stock"
            }
        ]
    }
    """
    if request.method == 'GET':
        try:
            business_id = request.GET.get('business_id')
            limit = int(request.GET.get('limit', 50))
            offset = int(request.GET.get('offset', 0))
            
            # Get only pending AND submitted requisitions
            requisitions = PurchaseRequisition.objects.filter(status='pending', submitted_to_manager='submitted')
            
            if business_id:
                # Validate business if provided
                try:
                    business = Business.objects.get(business_id=business_id)
                    requisitions = requisitions.filter(business_id=business)
                except Business.DoesNotExist:
                    return Response({
                        'error': f'Business with business_id {business_id} does not exist'
                    }, status=status.HTTP_400_BAD_REQUEST)
            
            # Order by request date (oldest first)
            requisitions = requisitions.order_by('request_date')[offset:offset+limit]
            
            serializer = PurchaseRequisitionSerializer(requisitions, many=True)
            
            return Response({
                'pending_requisitions': serializer.data,
                'count': len(serializer.data)
            }, status=status.HTTP_200_OK)
            
        except ValueError as e:
            return Response({
                'error': 'Invalid limit or offset parameter'
            }, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            return Response({
                'error': 'An error occurred while fetching pending requisitions',
                'details': str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    
    elif request.method == 'PUT':
        try:
            requisitions_data = request.data.get('requisitions', [])
            results = []
            
            for req_data in requisitions_data:
                purchase_req_id = req_data.get('purchase_req_id')
                action = req_data.get('action')
                reason = req_data.get('reason', '')
                
                if not purchase_req_id or not action:
                    results.append({
                        'purchase_req_id': purchase_req_id,
                        'success': False,
                        'error': 'purchase_req_id and action are required'
                    })
                    continue
                
                # Get requisition
                try:
                    requisition = PurchaseRequisition.objects.get(purchase_req_id=purchase_req_id)
                except PurchaseRequisition.DoesNotExist:
                    results.append({
                        'purchase_req_id': purchase_req_id,
                        'success': False,
                        'error': 'Requisition not found'
                    })
                    continue
                
                if requisition.status != 'pending':
                    results.append({
                        'purchase_req_id': purchase_req_id,
                        'success': False,
                        'error': f'Cannot {action} requisition with status {requisition.status}'
                    })
                    continue
                
                try:
                    if action == 'approved':
                        # Check inventory stock
                        from .models import Inventory
                        inventory_item = Inventory.objects.get(
                            business_id=requisition.business_id,
                            item_name__iexact=requisition.item_name.strip()
                        )
                        
                        if inventory_item.current_stock < requisition.quantity:
                            results.append({
                                'purchase_req_id': purchase_req_id,
                                'success': False,
                                'error': f'Insufficient stock for {requisition.item_name}. Available: {inventory_item.current_stock}, Requested: {requisition.quantity}'
                            })
                            continue
                        
                        # Update inventory
                        inventory_item.sold_stock = inventory_item.sold_stock + requisition.quantity
                        inventory_item.save(update_fields=['sold_stock'])
                        
                        # Update requisition status
                        requisition.status = 'approved'
                        requisition.save(update_fields=['status'])
                        
                        # Create log entry
                        approver = request.user if hasattr(request, 'user') and request.user.is_authenticated else requisition.user_id
                        PurchaseRequisitionLog.objects.create(
                            requisition=requisition,
                            business_id=requisition.business_id,
                            action='approved',
                            action_by=approver,
                            reason=reason or 'Purchase requisition approved'
                        )
                        
                        results.append({
                            'purchase_req_id': purchase_req_id,
                            'success': True,
                            'action': 'approved',
                            'message': 'Requisition approved successfully'
                        })
                        
                    elif action == 'rejected':
                        # Validate reason for rejection
                        if not reason or not reason.strip():
                            results.append({
                                'purchase_req_id': purchase_req_id,
                                'success': False,
                                'error': 'Reason is required when rejecting a requisition'
                            })
                            continue
                        
                        # Update requisition status
                        requisition.status = 'rejected'
                        requisition.save(update_fields=['status'])
                        
                        # Create log entry
                        rejecter = request.user if hasattr(request, 'user') and request.user.is_authenticated else requisition.user_id
                        PurchaseRequisitionLog.objects.create(
                            requisition=requisition,
                            business_id=requisition.business_id,
                            action='rejected',
                            action_by=rejecter,
                            reason=reason
                        )
                        
                        results.append({
                            'purchase_req_id': purchase_req_id,
                            'success': True,
                            'action': 'rejected',
                            'message': 'Requisition rejected successfully'
                        })
                        
                    else:
                        results.append({
                            'purchase_req_id': purchase_req_id,
                            'success': False,
                            'error': 'Invalid action. Must be approved or rejected'
                        })
                        
                except Exception as e:
                    results.append({
                        'purchase_req_id': purchase_req_id,
                        'success': False,
                        'error': str(e)
                    })
            
            return Response({
                'results': results,
                'processed_count': len(results),
                'success_count': len([r for r in results if r.get('success')])
            }, status=status.HTTP_200_OK)
            
        except Exception as e:
            return Response({
                'error': 'An error occurred while processing requisitions',
                'details': str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['PUT'])
def submit_requisitions_to_manager(request):
    """
    Submit multiple requisitions to manager for approval
    Only requisitions with 'draft' status can be submitted
    
    Expected payload:
    {
        "requisition_ids": [1, 2, 3]
    }
    """
    try:
        requisition_ids = request.data.get('requisition_ids', [])
        results = []
        
        for req_id in requisition_ids:
            try:
                requisition = PurchaseRequisition.objects.get(purchase_req_id=req_id)
                
                if requisition.submitted_to_manager != 'draft':
                    results.append({
                        'purchase_req_id': req_id,
                        'success': False,
                        'error': f'Requisition is already {requisition.submitted_to_manager}'
                    })
                    continue
                
                # Update submission status
                requisition.submitted_to_manager = 'submitted'
                requisition.save(update_fields=['submitted_to_manager'])
                
                # Create log entry
                submitter = request.user if hasattr(request, 'user') and request.user.is_authenticated else requisition.user_id
                PurchaseRequisitionLog.objects.create(
                    requisition=requisition,
                    business_id=requisition.business_id,
                    action='submitted',
                    action_by=submitter,
                    reason='Requisition submitted to manager for approval'
                )
                
                results.append({
                    'purchase_req_id': req_id,
                    'success': True,
                    'message': 'Requisition submitted to manager successfully'
                })
                
            except PurchaseRequisition.DoesNotExist:
                results.append({
                    'purchase_req_id': req_id,
                    'success': False,
                    'error': 'Requisition not found'
                })
            except Exception as e:
                results.append({
                    'purchase_req_id': req_id,
                    'success': False,
                    'error': str(e)
                })
        
        return Response({
            'results': results,
            'processed_count': len(results),
            'success_count': len([r for r in results if r.get('success')])
        }, status=status.HTTP_200_OK)
        
    except Exception as e:
        return Response({
            'error': 'An error occurred while submitting requisitions',
            'details': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['DELETE'])
def delete_draft_requisition(request, purchase_req_id):
    """
    Delete a draft requisition (only if not submitted to manager)
    URL parameters:
    - purchase_req_id (required)
    
    Query parameters (optional):
    - user_id (optional) - for additional validation
    - business_id (optional) - for additional validation
    
    Only requisitions with submitted_to_manager = 'draft' can be deleted
    """
    try:
        # Get optional query parameters
        user_id = request.GET.get('user_id')
        business_id = request.GET.get('business_id')
        
        # Get requisition
        try:
            requisition = PurchaseRequisition.objects.get(purchase_req_id=purchase_req_id)
        except PurchaseRequisition.DoesNotExist:
            return Response({
                'error': 'Requisition not found'
            }, status=status.HTTP_404_NOT_FOUND)
        
        # Optional validation if parameters provided
        if user_id and str(requisition.user_id.user_id) != user_id:
            return Response({
                'error': 'Requisition does not belong to the specified user'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        if business_id and str(requisition.business_id.business_id) != business_id:
            return Response({
                'error': 'Requisition does not belong to the specified business'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Check if requisition can be deleted (must be draft)
        if requisition.submitted_to_manager != 'draft':
            return Response({
                'error': f'Cannot delete requisition. It is already {requisition.submitted_to_manager}'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Create log entry before deletion
        deleter = request.user if hasattr(request, 'user') and request.user.is_authenticated else requisition.user_id
        PurchaseRequisitionLog.objects.create(
            requisition=requisition,
            business_id=requisition.business_id,
            action='deleted',
            action_by=deleter,
            reason='Draft requisition deleted before submission'
        )
        
        # Store requisition info for response
        requisition_info = {
            'purchase_req_id': requisition.purchase_req_id,
            'requisition_number': requisition.requisition_number,
            'item_name': requisition.item_name,
            'quantity': requisition.quantity,
            'unit': requisition.unit
        }
        
        # Delete the requisition
        requisition.delete()
        
        return Response({
            'message': 'Requisition deleted successfully',
            'deleted_requisition': requisition_info
        }, status=status.HTTP_200_OK)
        
    except Exception as e:
        return Response({
            'error': 'An error occurred while deleting requisition',
            'details': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
