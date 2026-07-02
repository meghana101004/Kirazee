from django.db import transaction
from django.utils import timezone
from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework import status as http_status
from django.shortcuts import get_object_or_404
from django.db import connection
from django.utils import timezone
from drf_yasg.utils import swagger_auto_schema
from geopy.distance import geodesic
from decimal import Decimal
import math
from kirazee_app.models import Business
from .serializers import DeliveryChargesSerializer
from .models import DeliveryCharges
from kirazee_app.models import Registration, UserAddress, Business


@swagger_auto_schema(methods=['POST'],tags=['Consumer'])
@api_view(['POST'])
def calculate_delivery_charges(request):
    """
    Calculate delivery charges based on business rules and distance
    Accepts delivery_address with coordinates instead of user_address_id
    """
    try:
        data = request.data
        business_id = data.get('business_id')
        delivery_address = data.get('delivery_address', {})
        cart_value = Decimal(str(data.get('cart_value', 0)))
        order_type = data.get('order_type', 'delivery')
        
        # Validate required fields
        if not business_id:
            return Response({
                'success': False,
                'error': 'business_id is required'
            }, status=http_status.HTTP_400_BAD_REQUEST)
        
        if not delivery_address or not all([delivery_address.get('latitude'), delivery_address.get('longitude')]):
            return Response({
                'success': False,
                'error': 'delivery_address with latitude and longitude is required'
            }, status=http_status.HTTP_400_BAD_REQUEST)
        
        # Return zero for non-delivery orders
        if order_type != 'delivery':
            return Response({
                'success': True,
                'data': {
                    'delivery_charges': 0.00,
                    'free_delivery_applied': False,
                    'distance_km': 0,
                    'message': f'No delivery charges for {order_type} orders'
                }
            }, status=http_status.HTTP_200_OK)
        
        # Get business by ID (business_id is CharField)
        try:
            business = Business.objects.get(business_id=business_id)
        except Business.DoesNotExist:
            # Per requirement: if business_id not found, return default base charge of 10
            base_charge = Decimal('10.00')
            return Response({
                'success': True,
                'data': {
                    'delivery_charges': float(base_charge),
                    'free_delivery_applied': False,
                    'distance_km': None,
                    'base_charge': float(base_charge),
                    'free_delivery_threshold': None,
                    'message': 'Default base charge applied (business_id not found)'
                }
            }, status=http_status.HTTP_200_OK)
        
        # Get business location with master business fallback
        business_latitude = business.latitude
        business_longitude = business.longitude
        
        # If business doesn't have coordinates, check master business by master business_id
        if not all([business_latitude, business_longitude]) and getattr(business, 'master', None):
            try:
                master_business = Business.objects.get(business_id=business.master)
                business_latitude = master_business.latitude
                business_longitude = master_business.longitude
            except Business.DoesNotExist:
                pass
        
        # If still no coordinates, return error
        if not all([business_latitude, business_longitude]):
            return Response({
                'success': False,
                'error': 'Business location coordinates not found'
            }, status=http_status.HTTP_400_BAD_REQUEST)
        
        # Calculate distance between business and delivery address
        business_coords = (float(business_latitude), float(business_longitude))
        delivery_coords = (float(delivery_address['latitude']), float(delivery_address['longitude']))
        distance_km = geodesic(business_coords, delivery_coords).kilometers
        
        # Get delivery charge configuration
        delivery_config = DeliveryCharges.objects.filter(
            business_id=business,
            is_active=True
        ).first()
        
        if not delivery_config:
            # Default delivery charge if no configuration found for this business
            base_charge = Decimal('10.00')
            delivery_charges = base_charge
            free_delivery_applied = False
            
            return Response({
                'success': True,
                'data': {
                    'delivery_charges': float(delivery_charges),
                    'free_delivery_applied': free_delivery_applied,
                    'distance_km': round(distance_km, 2),
                    'base_charge': float(base_charge),
                    'free_delivery_threshold': None,
                    'message': 'Default base charge applied (no delivery configuration found for this business)',
                    'business_info': {
                        'business_code': business.business_id,
                        'business_name': business.businessName,
                        'business_type': business.businessType,
                        'business_location': {
                            'latitude': float(business_latitude),
                            'longitude': float(business_longitude)
                        }
                    },
                    'delivery_location': {
                        'latitude': float(delivery_address['latitude']),
                        'longitude': float(delivery_address['longitude'])
                    }
                }
            }, status=http_status.HTTP_200_OK)
        
        # Check for free delivery threshold
        if delivery_config.free_delivery_above and cart_value >= delivery_config.free_delivery_above:
            return Response({
                'success': True,
                'data': {
                    'delivery_charges': 0.00,
                    'free_delivery_applied': True,
                    'distance_km': round(distance_km, 2),
                    'free_delivery_threshold': float(delivery_config.free_delivery_above),
                    'message': f'Free delivery applied for orders above ₹{delivery_config.free_delivery_above}',
                    'business_info': {
                        'business_code': business.business_id,
                        'business_name': business.businessName,
                        'business_type': business.businessType,
                        'business_location': {
                            'latitude': float(business_latitude),
                            'longitude': float(business_longitude)
                        }
                    },
                    'delivery_location': {
                        'latitude': float(delivery_address['latitude']),
                        'longitude': float(delivery_address['longitude'])
                    }
                }
            }, status=http_status.HTTP_200_OK)
        
        # Calculate charges based on distance slabs
        delivery_charges = delivery_config.base_charge
        
        # Apply distance-based charges if slabs are configured
        if delivery_config.distance_slabs:
            matched_slab = False
            last_max_km = 0.0
            for slab in delivery_config.distance_slabs:
                min_km = float(slab.get('min_km', 0))
                raw_max = slab.get('max_km', None)
                max_km = float(raw_max) if raw_max is not None else float('inf')
                charge = Decimal(str(slab.get('charge', 0)))
                
                # Track the largest finite max_km for overflow handling
                if math.isfinite(max_km):
                    last_max_km = max(last_max_km, max_km)
                else:
                    last_max_km = float('inf')
                
                if min_km <= float(distance_km) < max_km:
                    delivery_charges = charge
                    matched_slab = True
                    break
            
            # If distance exceeds configured slabs, use max_charge when available
            if not matched_slab and float(distance_km) > last_max_km and delivery_config.max_charge:
                delivery_charges = delivery_config.max_charge
        
        # Apply peak hour multiplier if configured
        current_hour = timezone.now().hour
        is_peak_hour = False
        if (delivery_config.peak_hours_start and delivery_config.peak_hours_end and 
            delivery_config.peak_hour_multiplier):
            
            peak_start = delivery_config.peak_hours_start.hour
            peak_end = delivery_config.peak_hours_end.hour
            
            # Handle peak hours that span midnight
            if peak_start <= peak_end:
                is_peak_hour = peak_start <= current_hour < peak_end
            else:
                is_peak_hour = current_hour >= peak_start or current_hour < peak_end
            
            if is_peak_hour:
                delivery_charges = delivery_charges * delivery_config.peak_hour_multiplier
        
        # Apply maximum charge limit if configured
        if delivery_config.max_charge and delivery_charges > delivery_config.max_charge:
            delivery_charges = delivery_config.max_charge
        
        return Response({
            'success': True,
            'data': {
                'delivery_charges': float(delivery_charges),
                'free_delivery_applied': False,
                'distance_km': round(distance_km, 2),
                'base_charge': float(delivery_config.base_charge),
                'free_delivery_threshold': float(delivery_config.free_delivery_above) if delivery_config.free_delivery_above else None,
                'peak_hour_applied': is_peak_hour,
                'configuration_id': delivery_config.delivery_id,
                'business_info': {
                    'business_id': business.business_id,
                    'business_name': business.businessName,
                    'business_type': business.businessType,
                    'business_location': {
                        'latitude': float(business_latitude),
                        'longitude': float(business_longitude)
                    }
                },
                'delivery_location': {
                    'latitude': float(delivery_address['latitude']),
                    'longitude': float(delivery_address['longitude'])
                }
            }
        }, status=http_status.HTTP_200_OK)
        
    except Exception as e:
        return Response({
            'success': False,
            'error': str(e)
        }, status=http_status.HTTP_500_INTERNAL_SERVER_ERROR)


@swagger_auto_schema(methods=['GET'],tags=['Consumer'])
@api_view(['GET'])
def get_delivery_zones(request, business_id):
    """
    Get delivery zones and charges for a business
    """
    try:
        business = get_object_or_404(Business, business_id=business_id)
        
        delivery_config = DeliveryCharges.objects.filter(
            business_id=business,
            is_active=True
        ).first()
        
        if not delivery_config:
            return Response({
                'success': False,
                'error': 'No delivery configuration found for this business'
            }, status=http_status.HTTP_404_NOT_FOUND)
        
        # Format distance slabs for response
        delivery_zones = []
        if delivery_config.distance_slabs:
            for i, slab in enumerate(delivery_config.distance_slabs):
                zone_name = f"Zone {i + 1}"
                min_km = slab.get('min_km', 0)
                max_km = slab.get('max_km')
                charge = slab.get('charge', 0)
                
                zone_description = f"{min_km}km"
                if max_km and max_km != float('inf'):
                    zone_description += f" - {max_km}km"
                else:
                    zone_description += "+"
                
                delivery_zones.append({
                    'zone_name': zone_name,
                    'distance_range': zone_description,
                    'min_km': min_km,
                    'max_km': max_km if max_km != float('inf') else None,
                    'charge': float(charge)
                })
        
        return Response({
            'success': True,
            'data': {
                'business_id': business_id,
                'business_name': business.businessName,
                'base_charge': float(delivery_config.base_charge),
                'max_charge': float(delivery_config.max_charge) if delivery_config.max_charge else None,
                'free_delivery_above': float(delivery_config.free_delivery_above) if delivery_config.free_delivery_above else None,
                'delivery_zones': delivery_zones,
                'peak_hours': {
                    'start': delivery_config.peak_hours_start.strftime('%H:%M') if delivery_config.peak_hours_start else None,
                    'end': delivery_config.peak_hours_end.strftime('%H:%M') if delivery_config.peak_hours_end else None,
                    'multiplier': float(delivery_config.peak_hour_multiplier) if delivery_config.peak_hour_multiplier else None
                },
                'is_active': delivery_config.is_active
            }
        }, status=http_status.HTTP_200_OK)
        
    except Exception as e:
        return Response({
            'success': False,
            'error': str(e)
        }, status=http_status.HTTP_500_INTERNAL_SERVER_ERROR)


@swagger_auto_schema(methods=['POST'],tags=['Consumer'])
@api_view(['POST'])
def create_delivery_configuration(request):
    """
    Create or update delivery charge configuration for a business
    """
    try:
        data = request.data
        business_id = data.get('business_id')
        
        if not business_id:
            return Response({
                'success': False,
                'error': 'business_id is required'
            }, status=http_status.HTTP_400_BAD_REQUEST)
        
        business = get_object_or_404(Business, business_id=business_id)
        
        # Check if configuration already exists
        existing_config = DeliveryCharges.objects.filter(business_id=business).first()
        
        if existing_config:
            # Update existing configuration
            serializer = DeliveryChargesSerializer(existing_config, data=data, partial=True)
        else:
            # Create new configuration
            serializer = DeliveryChargesSerializer(data=data)
        
        if serializer.is_valid():
            delivery_config = serializer.save(business_id=business)
            
            return Response({
                'success': True,
                'message': 'Delivery configuration saved successfully',
                'data': DeliveryChargesSerializer(delivery_config).data
            }, status=http_status.HTTP_201_CREATED if not existing_config else http_status.HTTP_200_OK)
        
        return Response({
            'success': False,
            'error': serializer.errors
        }, status=http_status.HTTP_400_BAD_REQUEST)
        
    except Exception as e:
        return Response({
            'success': False,
            'error': str(e)
        }, status=http_status.HTTP_500_INTERNAL_SERVER_ERROR)


@swagger_auto_schema(methods=['GET'],tags=['Consumer'])
@api_view(['GET'])
def check_delivery_availability(request):
    """
    Check if delivery is available for a specific address
    """
    try:
        business_id = request.query_params.get('business_id')
        user_address_id = request.query_params.get('user_address_id')
        latitude = request.query_params.get('latitude')
        longitude = request.query_params.get('longitude')
        
        if not business_id:
            return Response({
                'success': False,
                'error': 'business_id is required'
            }, status=http_status.HTTP_400_BAD_REQUEST)
        
        business = get_object_or_404(Business, business_id=business_id)
        
        # Get delivery configuration
        delivery_config = DeliveryCharges.objects.filter(
            business_id=business,
            is_active=True
        ).first()
        
        if not delivery_config:
            return Response({
                'success': True,
                'data': {
                    'delivery_available': True,
                    'message': 'Delivery available with default charges',
                    'max_distance_km': None
                }
            }, status=http_status.HTTP_200_OK)
        
        # Calculate distance if coordinates provided
        distance_km = None
        delivery_available = True
        
        if user_address_id:
            user_address = get_object_or_404(UserAddress, id=user_address_id)
            if (business.latitude and business.longitude and 
                user_address.latitude and user_address.longitude):
                business_coords = (float(business.latitude), float(business.longitude))
                user_coords = (float(user_address.latitude), float(user_address.longitude))
                distance_km = geodesic(business_coords, user_coords).kilometers
        
        elif latitude and longitude:
            if business.latitude and business.longitude:
                business_coords = (float(business.latitude), float(business.longitude))
                user_coords = (float(latitude), float(longitude))
                distance_km = geodesic(business_coords, user_coords).kilometers
        
        # Check if distance exceeds maximum delivery range
        if distance_km and delivery_config.max_delivery_distance:
            if distance_km > delivery_config.max_delivery_distance:
                delivery_available = False
        
        return Response({
            'success': True,
            'data': {
                'delivery_available': delivery_available,
                'distance_km': round(distance_km, 2) if distance_km else None,
                'max_delivery_distance': float(delivery_config.max_delivery_distance) if delivery_config.max_delivery_distance else None,
                'message': 'Delivery available' if delivery_available else 'Outside delivery area'
            }
        }, status=http_status.HTTP_200_OK)
        
    except Exception as e:
        return Response({
            'success': False,
            'error': str(e)
        }, status=http_status.HTTP_500_INTERNAL_SERVER_ERROR)


@swagger_auto_schema(methods=['POST', 'GET'],tags=['Consumer'])
@api_view(['POST', 'GET'])  # Support both methods
def get_delivery_time_estimate(request):
    try:
        business_id = request.query_params.get('business_id')
        
        if not business_id:
            return Response({
                'success': False,
                'error': 'business_id is required'
            }, status=http_status.HTTP_400_BAD_REQUEST)
        
        business = get_object_or_404(Business, business_id=business_id)
        
        # Base preparation time
        if business.businessType == 'R02':  # Restaurant
            base_prep_time = 30
        elif business.businessType == 'R01':  # Grocery
            base_prep_time = 15
        else:
            base_prep_time = 20
        
        # Get delivery coordinates - support both methods
        user_lat = user_lng = None
        order_type = request.query_params.get('order_type', 'delivery')
        
        # Method 1: Direct coordinates in JSON body (your current usage)
        if request.method == 'POST' and request.data:
            delivery_address = request.data.get('delivery_address', {})
            order_type = request.data.get('order_type', order_type)
            user_lat = delivery_address.get('latitude')
            user_lng = delivery_address.get('longitude')
        
        # Method 2: user_address_id in query params (fallback)
        if not user_lat or not user_lng:
            user_address_id = request.query_params.get('user_address_id')
            if user_address_id:
                user_address = get_object_or_404(UserAddress, id=user_address_id)
                if user_address.address:
                    addr_data = user_address.address
                    user_lat = addr_data.get('latitude')
                    user_lng = addr_data.get('longitude')
        
        # Calculate delivery time
        delivery_time = 0
        if order_type == 'delivery' and user_lat and user_lng:
            # Convert to float (handle both string and number formats)
            try:
                user_lat = float(user_lat)
                user_lng = float(user_lng)
                
                if business.latitude and business.longitude:
                    business_coords = (float(business.latitude), float(business.longitude))
                    user_coords = (user_lat, user_lng)
                    distance_km = geodesic(business_coords, user_coords).kilometers
                    
                    # Estimate travel time (20 km/h average speed)
                    travel_time_minutes = (distance_km / 20) * 60
                    delivery_time = max(10, int(travel_time_minutes))
            except (ValueError, TypeError):
                # Invalid coordinates, keep delivery_time as 0
                pass
        
        total_time = base_prep_time + delivery_time
        # Build a tight time window (target width ~10 mins) and round to nearest 5
        def _round_to_5(n):
            return int(5 * round(float(n) / 5.0))

        min_total_time = _round_to_5(max(5, total_time - 5))
        max_total_time = _round_to_5(total_time + 5)

        min_delivery_time = _round_to_5(max(5, delivery_time - 5))
        max_delivery_time = _round_to_5(delivery_time + 5)

        now_value = timezone.now()
        estimated_time = now_value + timezone.timedelta(minutes=total_time)
        estimated_from = now_value + timezone.timedelta(minutes=min_total_time)
        estimated_to = now_value + timezone.timedelta(minutes=max_total_time)
        
        return Response({
            'success': True,
            'data': {
                'preparation_time_minutes': base_prep_time,
                'delivery_time_minutes': delivery_time,
                'delivery_time_minutes_min': min_delivery_time,
                'delivery_time_minutes_max': max_delivery_time,
                'delivery_time_range': f"{min_delivery_time}-{max_delivery_time}",
                'total_time_minutes': total_time,
                'total_time_minutes_min': min_total_time,
                'total_time_minutes_max': max_total_time,
                'total_time_range': f"{min_total_time}-{max_total_time}",
                'estimated_delivery_time': estimated_time.isoformat(),
                'estimated_delivery_time_formatted': estimated_time.strftime('%I:%M %p, %d %b %Y'),
                'estimated_delivery_time_from': estimated_from.isoformat(),
                'estimated_delivery_time_to': estimated_to.isoformat(),
                'estimated_delivery_time_from_formatted': estimated_from.strftime('%I:%M %p, %d %b %Y'),
                'estimated_delivery_time_to_formatted': estimated_to.strftime('%I:%M %p, %d %b %Y')
            }
        }, status=http_status.HTTP_200_OK)
        
    except Exception as e:
        return Response({
            'success': False,
            'error': str(e)
        }, status=http_status.HTTP_500_INTERNAL_SERVER_ERROR)


@swagger_auto_schema(methods=['POST'],tags=['Consumer'])
@api_view(['POST'])
def get_delivery_partner_to_business_estimate(request):
    """
    Calculate distance and estimated time for delivery partner to reach business/store.
    This helps chefs prepare food based on when delivery partner will arrive.
    
    Expected payload:
    {
        "delivery_partner_id": 1,
        "business_id": "KIR1477220250826162337"
    }
    
    Response:
    {
        "success": true,
        "data": {
            "distance_km": 2.5,
            "travel_time_minutes": 8,
            "estimated_arrival_time": "2025-10-24T18:08:12.238036",
            "estimated_arrival_time_formatted": "06:08 PM, 24 Oct 2025",
            "delivery_partner": {
                "id": 1,
                "name": "John Doe",
                "vehicle_type": "bike",
                "current_location": [13.5607, 80.0224]
            },
            "business": {
                "business_id": "KIR1477220250826162337",
                "name": "Sample Restaurant",
                "location": [13.5597, 80.0231]
            }
        }
    }
    """
    try:
        delivery_partner_id = request.data.get('delivery_partner_id')
        business_id = request.data.get('business_id')
        
        if not delivery_partner_id or not business_id:
            return Response({
                'success': False,
                'error': 'delivery_partner_id and business_id are required'
            }, status=http_status.HTTP_400_BAD_REQUEST)
        
        # Get delivery partner with coordinates
        try:
            from delivery.models import DeliveryPartner
            delivery_partner = DeliveryPartner.objects.select_related('user').get(id=delivery_partner_id)
        except DeliveryPartner.DoesNotExist:
            return Response({
                'success': False,
                'error': 'Delivery partner not found'
            }, status=http_status.HTTP_404_NOT_FOUND)
        
        # Get business with coordinates
        business = get_object_or_404(Business, business_id=business_id)
        
        # Check if delivery partner has current location
        if not delivery_partner.latitude or not delivery_partner.longitude:
            return Response({
                'success': False,
                'error': 'Delivery partner location not available. Partner needs to update their location first.'
            }, status=http_status.HTTP_400_BAD_REQUEST)
        
        # Check if business has coordinates
        if not business.latitude or not business.longitude:
            return Response({
                'success': False,
                'error': 'Business location not available'
            }, status=http_status.HTTP_400_BAD_REQUEST)
        
        # Calculate distance between delivery partner and business
        try:
            partner_coords = (float(delivery_partner.latitude), float(delivery_partner.longitude))
            business_coords = (float(business.latitude), float(business.longitude))
            
            distance_km = geodesic(partner_coords, business_coords).kilometers
            
            # Estimate travel time based on vehicle type
            # Different speeds for different vehicle types
            speed_kmh = {
                'bike': 25,      # Bike/motorcycle - faster in traffic
                'scooter': 20,   # Scooter - moderate speed
                'bicycle': 12,   # Bicycle - slower
                'car': 18,       # Car - slower in city traffic
                'auto': 15,      # Auto-rickshaw
                'van': 15        # Van - similar to auto
            }.get(delivery_partner.vehicle_type.lower(), 20)  # Default 20 km/h
            
            # Calculate travel time in minutes
            travel_time_minutes = (distance_km / speed_kmh) * 60
            travel_time_minutes = max(2, int(travel_time_minutes))  # Minimum 2 minutes
            
            # Calculate estimated arrival time
            estimated_arrival = timezone.now() + timezone.timedelta(minutes=travel_time_minutes)
            
            # Prepare delivery partner info
            partner_name = f"{delivery_partner.user.firstName} {delivery_partner.user.lastName}".strip()
            if not partner_name:
                partner_name = f"Partner {delivery_partner.user.user_id}"
            
            response_data = {
                'success': True,
                'data': {
                    'distance_km': round(distance_km, 2),
                    'travel_time_minutes': travel_time_minutes,
                    'estimated_arrival_time': estimated_arrival.isoformat(),
                    'estimated_arrival_time_formatted': estimated_arrival.strftime('%I:%M %p, %d %b %Y'),
                    'delivery_partner': {
                        'id': delivery_partner.id,
                        'name': partner_name,
                        'vehicle_type': delivery_partner.vehicle_type,
                        'phone_number': delivery_partner.phone_number,
                        'current_location': [delivery_partner.latitude, delivery_partner.longitude]
                    },
                    'business': {
                        'business_id': business.business_id,
                        'name': business.businessName,
                        'location': [float(business.latitude), float(business.longitude)],
                        'address': business.address
                    }
                }
            }
            
            return Response(response_data, status=http_status.HTTP_200_OK)
            
        except (ValueError, TypeError) as e:
            return Response({
                'success': False,
                'error': f'Invalid coordinate data: {str(e)}'
            }, status=http_status.HTTP_400_BAD_REQUEST)
        
    except Exception as e:
        return Response({
            'success': False,
            'error': str(e)
        }, status=http_status.HTTP_500_INTERNAL_SERVER_ERROR)


@swagger_auto_schema(methods=['GET'],tags=['Consumer'])
@api_view(['GET'])
def get_delivery_partner_current_orders(request):
    """
    Get current orders for a specific delivery partner filtered by business_id.
    
    Query Parameters:
    - delivery_partner_user_id: User ID of the delivery partner
    - business_id: Business ID to filter orders
    
    Returns orders categorized by status: assigned, accepted, picked_up, out_for_delivery, delivered
    """
    try:
        delivery_partner_user_id = request.query_params.get('delivery_partner_user_id')
        business_id = request.query_params.get('business_id')
        
        if not delivery_partner_user_id or not business_id:
            return Response({
                'success': False,
                'error': 'delivery_partner_user_id and business_id are required'
            }, status=http_status.HTTP_400_BAD_REQUEST)
        
        # Get delivery partner details
        try:
            from delivery.models import DeliveryPartner
            delivery_partner = DeliveryPartner.objects.select_related('user').get(user_id=delivery_partner_user_id)
        except DeliveryPartner.DoesNotExist:
            return Response({
                'success': False,
                'error': 'Delivery partner not found'
            }, status=http_status.HTTP_404_NOT_FOUND)
        
        # Initialize response structure
        orders_by_status = {
            'assigned_orders': [],
            'accepted_orders': [],
            'picked_up_orders': [],
            'out_for_delivery_orders': [],
            'delivered_orders': []
        }
        
        counts = {
            'total_orders': 0,
            'assigned_count': 0,
            'accepted_count': 0,
            'picked_up_count': 0,
            'out_for_delivery_count': 0,
            'delivered_count': 0
        }
        
        with connection.cursor() as cursor:
            # Query 1: Standard orders from 'orders' table
            standard_orders_query = """
                SELECT 
                    o.order_id,
                    o.order_number,
                    o.order_type,
                    o.status as order_status,
                    o.total_amount,
                    o.final_amount,
                    o.delivery_charges,
                    o.estimated_delivery_time,
                    o.actual_delivery_time,
                    o.created_at,
                    o.updated_at,
                    
                    -- Customer details
                    r.user_id as customer_id,
                    CONCAT(COALESCE(r.firstName, ''), ' ', COALESCE(r.lastName, '')) as customer_name,
                    r.mobileNumber as customer_phone,
                    
                    -- Business details
                    b.businessName as business_name,
                    
                    -- Delivery address
                    CASE 
                        WHEN o.delivery_address_snapshot IS NOT NULL THEN 
                            CONCAT(
                                COALESCE(JSON_UNQUOTE(JSON_EXTRACT(o.delivery_address_snapshot, '$.\"Door no\"')), ''), ' ',
                                COALESCE(JSON_UNQUOTE(JSON_EXTRACT(o.delivery_address_snapshot, '$.street')), ''), ', ',
                                COALESCE(JSON_UNQUOTE(JSON_EXTRACT(o.delivery_address_snapshot, '$.\"city/town\"')), ''), ', ',
                                COALESCE(JSON_UNQUOTE(JSON_EXTRACT(o.delivery_address_snapshot, '$.state')), ''), ' ',
                                COALESCE(JSON_UNQUOTE(JSON_EXTRACT(o.delivery_address_snapshot, '$.pincode')), '')
                            )
                        ELSE 'Address not available'
                    END as delivery_address,
                    
                    'standard' as order_system
                    
                FROM orders o
                LEFT JOIN registrations r ON o.user_id = r.user_id
                LEFT JOIN businesses b ON o.business_id = b.business_id
                WHERE o.delivery_partner_id = %s 
                AND o.business_id = %s
                ORDER BY o.created_at DESC
            """
            
            cursor.execute(standard_orders_query, [delivery_partner_user_id, business_id])
            standard_results = cursor.fetchall()
            
            # Query 2: Grocery orders from 'Groceries_orders' + 'Grocery_deliver_details'
            grocery_orders_query = """
                SELECT 
                    go.order_id,
                    NULL as order_number,
                    go.order_type,
                    go.order_status,
                    go.total_amount,
                    go.final_amount,
                    go.delivery_charge,
                    go.delivery_time as estimated_delivery_time,
                    gdd.delivered_at as actual_delivery_time,
                    go.created_at,
                    go.updated_at,
                    
                    -- Customer details
                    r.user_id as customer_id,
                    CONCAT(COALESCE(r.firstName, ''), ' ', COALESCE(r.lastName, '')) as customer_name,
                    r.mobileNumber as customer_phone,
                    
                    -- Business details
                    b.businessName as business_name,
                    
                    -- Delivery address
                    COALESCE(go.delivery_address, 'Address not available') as delivery_address,
                    
                    -- Assignment status from delivery details
                    gdd.assignment_status,
                    gdd.assigned_at,
                    gdd.delivered_at,
                    
                    'grocery' as order_system
                    
                FROM Groceries_orders go
                INNER JOIN Grocery_deliver_details gdd ON go.order_id = gdd.order_id
                LEFT JOIN registrations r ON go.user_id = r.user_id
                LEFT JOIN businesses b ON go.business_id = b.business_id
                WHERE gdd.partner_id = %s 
                AND go.business_id = %s
                AND gdd.is_active = 1
                ORDER BY go.created_at DESC
            """
            
            cursor.execute(grocery_orders_query, [delivery_partner_user_id, business_id])
            grocery_results = cursor.fetchall()
            
            # Process standard orders
            for row in standard_results:
                order_data = {
                    'order_id': row[0],
                    'order_number': row[1],
                    'order_type': row[2],
                    'order_status': row[3],
                    'total_amount': float(row[4]) if row[4] else 0.0,
                    'final_amount': float(row[5]) if row[5] else 0.0,
                    'delivery_charges': float(row[6]) if row[6] else 0.0,
                    'estimated_delivery_time': row[7].isoformat() if row[7] else None,
                    'actual_delivery_time': row[8].isoformat() if row[8] else None,
                    'created_at': row[9].isoformat() if row[9] else None,
                    'updated_at': row[10].isoformat() if row[10] else None,
                    'customer_id': row[11],
                    'customer_name': row[12].strip() if row[12] else 'Unknown Customer',
                    'customer_phone': row[13],
                    'business_name': row[14],
                    'delivery_address': row[15],
                    'order_system': row[16]
                }
                
                # Categorize by status
                status = row[3].lower() if row[3] else 'pending'
                if status in ['pending', 'confirmed']:
                    orders_by_status['assigned_orders'].append(order_data)
                    counts['assigned_count'] += 1
                elif status in ['accepted', 'preparing']:
                    orders_by_status['accepted_orders'].append(order_data)
                    counts['accepted_count'] += 1
                elif status in ['picked_up', 'ready']:
                    orders_by_status['picked_up_orders'].append(order_data)
                    counts['picked_up_count'] += 1
                elif status in ['out_for_delivery', 'in_transit']:
                    orders_by_status['out_for_delivery_orders'].append(order_data)
                    counts['out_for_delivery_count'] += 1
                elif status in ['delivered', 'completed']:
                    orders_by_status['delivered_orders'].append(order_data)
                    counts['delivered_count'] += 1
                
                counts['total_orders'] += 1
            
            # Process grocery orders
            for row in grocery_results:
                order_data = {
                    'order_id': row[0],
                    'order_number': row[1],
                    'order_type': row[2],
                    'order_status': row[3],
                    'total_amount': float(row[4]) if row[4] else 0.0,
                    'final_amount': float(row[5]) if row[5] else 0.0,
                    'delivery_charges': float(row[6]) if row[6] else 0.0,
                    'estimated_delivery_time': row[7].isoformat() if row[7] else None,
                    'actual_delivery_time': row[8].isoformat() if row[8] else None,
                    'created_at': row[9].isoformat() if row[9] else None,
                    'updated_at': row[10].isoformat() if row[10] else None,
                    'customer_id': row[11],
                    'customer_name': row[12].strip() if row[12] else 'Unknown Customer',
                    'customer_phone': row[13],
                    'business_name': row[14],
                    'delivery_address': row[15],
                    'assignment_status': row[16],
                    'assigned_at': row[17].isoformat() if row[17] else None,
                    'delivered_at': row[18].isoformat() if row[18] else None,
                    'order_system': row[19]
                }
                
                # Categorize by assignment_status for grocery orders
                assignment_status = row[16].lower() if row[16] else 'assigned'
                if assignment_status == 'assigned':
                    orders_by_status['assigned_orders'].append(order_data)
                    counts['assigned_count'] += 1
                elif assignment_status == 'accepted':
                    orders_by_status['accepted_orders'].append(order_data)
                    counts['accepted_count'] += 1
                elif assignment_status == 'picked_up':
                    orders_by_status['picked_up_orders'].append(order_data)
                    counts['picked_up_count'] += 1
                elif assignment_status == 'in_transit':
                    orders_by_status['out_for_delivery_orders'].append(order_data)
                    counts['out_for_delivery_count'] += 1
                elif assignment_status == 'delivered':
                    orders_by_status['delivered_orders'].append(order_data)
                    counts['delivered_count'] += 1
                
                counts['total_orders'] += 1
        
        # Prepare delivery partner info
        partner_name = f"{delivery_partner.user.firstName} {delivery_partner.user.lastName}".strip()
        if not partner_name:
            partner_name = f"Partner {delivery_partner.user.user_id}"
        
        response_data = {
            'success': True,
            'data': {
                'delivery_partner': {
                    'id': delivery_partner.id,
                    'name': partner_name,
                    'phone': delivery_partner.phone_number,
                    'vehicle_type': delivery_partner.vehicle_type
                },
                'business_id': business_id,
                'summary': counts,
                'orders': orders_by_status
            }
        }
        
        return Response(response_data, status=http_status.HTTP_200_OK)
        
    except Exception as e:
        return Response({
            'success': False,
            'error': str(e)
        }, status=http_status.HTTP_500_INTERNAL_SERVER_ERROR)
        