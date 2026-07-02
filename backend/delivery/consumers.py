import json
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from django.utils import timezone

class OrderTrackingConsumer(AsyncWebsocketConsumer):
    @database_sync_to_async
    def _get_delivery_partner_info(self, delivery_partner):
        if not delivery_partner:
            return None
            
        return {
            'id': delivery_partner.id,
            'name': delivery_partner.user.get_full_name(),
            'vehicle_type': delivery_partner.vehicle_type,
            'phone': delivery_partner.phone_number
        }

    @database_sync_to_async
    def _get_order_with_related(self, order_id):
        from django.db import connection
        from django.conf import settings
        
        try:
            # First, get the order with delivery_partner_id
            with connection.cursor() as cursor:
                # Get order and delivery partner details in one query
                query = """
                SELECT 
                    o.order_id, o.status, o.delivery_partner_id,
                    dp.id as dp_id, dp.vehicle_type, dp.phone_number,
                    dp.latitude, dp.longitude, dp.updated_at,
                    u.firstName, u.lastName, u.displayName
                FROM 
                    orders o
                LEFT JOIN 
                    delivery_partner dp ON o.delivery_partner_id = dp.user_id
                LEFT JOIN
                    registrations u ON dp.user_id = u.user_id
                WHERE 
                    o.order_id = %s
                """
                cursor.execute(query, [order_id])
                row = cursor.fetchone()
                
                if not row:
                    print(f"Order {order_id} not found")
                    return None
                
                # Map the row to a dictionary
                columns = [col[0] for col in cursor.description]
                order_data = dict(zip(columns, row))
                
                # Debug log
                print(f"Order {order_id} data:", order_data)
                
                # Create a simple object to hold the data
                class SimpleObject:
                    pass
                
                order = SimpleObject()
                order.order_id = order_data['order_id']
                order.status = order_data['status']
                # Preserve the delivery partner user_id for later updates
                order.delivery_partner_id = order_data['delivery_partner_id']
                
                # Only set delivery_partner if we have the data
                if order_data['delivery_partner_id']:
                    delivery_partner = SimpleObject()
                    delivery_partner.id = order_data['dp_id']
                    delivery_partner.vehicle_type = order_data['vehicle_type']
                    delivery_partner.phone_number = order_data['phone_number']
                    delivery_partner.latitude = float(order_data['latitude']) if order_data['latitude'] is not None else None
                    delivery_partner.longitude = float(order_data['longitude']) if order_data['longitude'] is not None else None
                    delivery_partner.updated_at = order_data['updated_at']
                    
                    # Add user info
                    class UserObject:
                        pass
                    
                    user = UserObject()
                    # Get names from the query result
                    user.first_name = order_data.get('firstName', '').strip() or 'Delivery'
                    user.last_name = order_data.get('lastName', '').strip() or 'Partner'
                    display_name = order_data.get('displayName', '').strip()
                    
                    # Use displayName if available, otherwise combine first and last names
                    if not display_name and (user.first_name or user.last_name):
                        display_name = f"{user.first_name} {user.last_name}".strip()
                    
                    user.get_full_name = lambda: display_name or 'Delivery Partner'
                    
                    delivery_partner.user = user
                    order.delivery_partner = delivery_partner
                    
                    print(f"Found delivery partner: {delivery_partner.id} - {delivery_partner.vehicle_type}")
                    print(f"Location: {delivery_partner.latitude}, {delivery_partner.longitude}")
                else:
                    print(f"No delivery partner found for order {order_id}")
                    order.delivery_partner = None
                
                return order
                
        except Exception as e:
            print(f"Error in _get_order_with_related for order {order_id}: {str(e)}")
            import traceback
            print(traceback.format_exc())
            return None

    async def connect(self):
        self.order_id = self.scope['url_route']['kwargs']['order_id']
        self.room_group_name = f'order_{self.order_id}'

        # Join room group
        await self.channel_layer.group_add(
            self.room_group_name,
            self.channel_name
        )

        await self.accept()

        # Send current order status on connect
        order = await self._get_order_with_related(self.order_id)
        if order:
            delivery_partner_info = None
            location_info = None
            
            if hasattr(order, 'delivery_partner') and order.delivery_partner:
                delivery_partner_info = await self._get_delivery_partner_info(order.delivery_partner)
                location_info = {
                    'latitude': float(order.delivery_partner.latitude) if order.delivery_partner.latitude else None,
                    'longitude': float(order.delivery_partner.longitude) if order.delivery_partner.longitude else None,
                    'last_updated': order.delivery_partner.updated_at.isoformat() if hasattr(order.delivery_partner, 'updated_at') and order.delivery_partner.updated_at else None
                }
                
                # Debug log
                print(f"Sending update for order {self.order_id}:")
                print(f"- Status: {order.status}")
                print(f"- Delivery Partner: {delivery_partner_info}")
                print(f"- Location: {location_info}")
            
            await self.send(text_data=json.dumps({
                'type': 'status_update',
                'status': order.status,
                'timestamp': timezone.now().isoformat(),
                'delivery_partner': delivery_partner_info,
                'location': location_info
            }))

    async def disconnect(self, close_code):
        # Leave room group
        await self.channel_layer.group_discard(
            self.room_group_name,
            self.channel_name
        )

    # Receive message from WebSocket
    @database_sync_to_async
    def _update_delivery_partner_location(self, order, latitude, longitude, status):
        """Update partner location and optionally order status using ORM, avoiding redundant re-queries."""
        if not order or not hasattr(order, 'delivery_partner_id') or not order.delivery_partner_id:
            print("No delivery partner ID found for order")
            return None

        try:
            from django.utils import timezone as dj_tz
            from delivery.models import DeliveryPartner
            from consumer.models import Orders

            # Update partner location via ORM
            updated = DeliveryPartner.objects.filter(user__user_id=order.delivery_partner_id).update(
                latitude=latitude,
                longitude=longitude,
                updated_at=dj_tz.now()
            )
            if not updated:
                print(f"Failed to update delivery partner {order.delivery_partner_id}")
                return None

            # Reflect new location on the in-memory object (if present)
            if hasattr(order, 'delivery_partner') and order.delivery_partner:
                try:
                    order.delivery_partner.latitude = float(latitude) if latitude is not None else None
                    order.delivery_partner.longitude = float(longitude) if longitude is not None else None
                    order.delivery_partner.updated_at = dj_tz.now()
                except Exception:
                    pass

            # Update order status if provided and valid
            if status:
                try:
                    valid_statuses = set(val for val, _ in Orders.OrderStatus.choices)
                    if status in valid_statuses:
                        Orders.objects.filter(order_id=order.order_id).update(status=status, updated_at=dj_tz.now())
                        order.status = status
                    else:
                        # Fallback: still attempt update to keep backward-compat with legacy statuses
                        Orders.objects.filter(order_id=order.order_id).update(status=status, updated_at=dj_tz.now())
                        order.status = status
                except Exception:
                    pass

            return order

        except Exception as e:
            print(f"Error updating delivery partner location: {str(e)}")
            import traceback
            print(traceback.format_exc())
            return None

    async def receive(self, text_data):
        try:
            text_data_json = json.loads(text_data)
            message_type = text_data_json.get('type')

            if message_type == 'location_update':
                # Get the order with related data
                order = await self._get_order_with_related(self.order_id)
                if not order or not order.delivery_partner:
                    return

                # Get update data
                latitude = text_data_json.get('latitude')
                longitude = text_data_json.get('longitude')
                status = text_data_json.get('status')
                
                # Update the delivery partner's location
                order = await self._update_delivery_partner_location(
                    order, latitude, longitude, status
                )
                
                if not order:
                    return
                
                # Get updated delivery partner info
                delivery_partner_info = await self._get_delivery_partner_info(order.delivery_partner)
                
                # Broadcast update to all connected clients
                await self.channel_layer.group_send(
                    self.room_group_name,
                    {
                        'type': 'status_update',
                        'status': order.status,
                        'timestamp': timezone.now().isoformat(),
                        'location': {
                            'latitude': latitude,
                            'longitude': longitude,
                            'last_updated': timezone.now().isoformat()
                        },
                        'delivery_partner': delivery_partner_info
                    }
                )
                
        except json.JSONDecodeError:
            await self.send(text_data=json.dumps({
                'type': 'error',
                'message': 'Invalid JSON format'
            }))
        except Exception as e:
            await self.send(text_data=json.dumps({
                'type': 'error',
                'message': str(e)
            }))

    # Receive message from room group
    async def status_update(self, event):
        try:
            # Prepare the base response data
            response_data = {
                'type': 'status_update',
                'status': event.get('status'),
                'timestamp': event.get('timestamp', timezone.now().isoformat())
            }
            
            # Add location if available
            if 'location' in event and event['location']:
                response_data['location'] = event['location']
                
                # Ensure latitude and longitude are floats
                if 'latitude' in response_data['location'] and response_data['location']['latitude'] is not None:
                    try:
                        response_data['location']['latitude'] = float(response_data['location']['latitude'])
                    except (TypeError, ValueError):
                        response_data['location']['latitude'] = None
                        
                if 'longitude' in response_data['location'] and response_data['location']['longitude'] is not None:
                    try:
                        response_data['location']['longitude'] = float(response_data['location']['longitude'])
                    except (TypeError, ValueError):
                        response_data['location']['longitude'] = None
            
            # Add delivery partner info if available
            if 'delivery_partner' in event and event['delivery_partner']:
                response_data['delivery_partner'] = event['delivery_partner']
            
            # Debug log
            print(f"Sending status update for order {getattr(self, 'order_id', 'unknown')}:")
            print(f"- Status: {response_data.get('status')}")
            print(f"- Has location: {'location' in response_data and response_data['location'] is not None}")
            print(f"- Has delivery partner: 'delivery_partner' in response_data and response_data['delivery_partner'] is not None")
            
            # Send the complete message to WebSocket
            await self.send(text_data=json.dumps(response_data))
            
        except Exception as e:
            print(f"Error in status_update: {str(e)}")
            # Send error response
            await self.send(text_data=json.dumps({
                'type': 'error',
                'message': 'Error processing status update',
                'details': str(e)
            }))

    async def location_update(self, event):
        # Send location update to WebSocket
        await self.send(text_data=json.dumps({
            'type': 'location_update',
            'latitude': event['latitude'],
            'longitude': event['longitude'],
            'timestamp': event['timestamp']
        }))

    @database_sync_to_async
    def get_order(self):
        from consumer.models import Orders   # ✅ safe import here
        try:
            return Orders.objects.get(order_id=self.order_id)
        except Orders.DoesNotExist:
            return None


def send_order_update(order):
    """
    Helper function to send order updates to WebSocket consumers
    """
    from channels.layers import get_channel_layer
    from asgiref.sync import async_to_sync
    
    channel_layer = get_channel_layer()
    
    async_to_sync(channel_layer.group_send)(
        f'order_{order.order_id}',
        {
            'type': 'status_update',
            'status': order.status,
            'timestamp': timezone.now().isoformat()
        }
    )
