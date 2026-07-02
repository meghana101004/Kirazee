from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from django.utils import timezone
from django.db import connection
from django.db.models import Q
import logging

logger = logging.getLogger(__name__)

class ActiveFleetView(APIView):
    """
    Active delivery fleet tracking for real-time map visualization
    GET /api/v1/admin/delivery/active-fleet/
    Returns drivers with recent location updates (last 15 minutes)
    """
    permission_classes = []
    
    def get(self, request):
        """Get active delivery fleet with location data"""
        try:
            # Get query parameters
            minutes_threshold = int(request.query_params.get('minutes', 15))
            include_inactive = request.query_params.get('include_inactive', 'false').lower() == 'true'
            
            # Limit threshold to reasonable range
            minutes_threshold = min(minutes_threshold, 60)  # Max 1 hour
            
            cutoff_time = timezone.now() - timezone.timedelta(minutes=minutes_threshold)
            
            with connection.cursor() as cursor:
                # Query active delivery partners with location data
                if include_inactive:
                    cursor.execute(f"""
                        SELECT 
                            dp.id,
                            CONCAT(r.firstName, ' ', COALESCE(r.lastName, '')) as name,
                            dp.phone,
                            dp.is_available,
                            dp.current_lat,
                            dp.current_lng,
                            dp.last_location_update,
                            dp.status as driver_status,
                            COUNT(o.order_id) as active_orders,
                            COALESCE(MAX(o.created_at), NULL) as last_order_time
                        FROM delivery_partner dp
                        LEFT JOIN registrations r ON dp.user_id = r.user_id
                        LEFT JOIN orders o ON dp.id = o.assigned_driver_id 
                            AND o.status IN ('confirmed', 'preparing', 'out_for_delivery', 'travelling')
                        WHERE dp.last_location_update >= DATE_SUB(NOW(), INTERVAL {minutes_threshold} MINUTE)
                            AND dp.current_lat IS NOT NULL 
                            AND dp.current_lng IS NOT NULL
                        GROUP BY dp.id, r.firstName, r.lastName, dp.phone, dp.is_available, 
                                dp.current_lat, dp.current_lng, dp.last_location_update, dp.status
                        ORDER BY dp.last_location_update DESC
                    """)
                else:
                    cursor.execute(f"""
                        SELECT 
                            dp.id,
                            CONCAT(r.firstName, ' ', COALESCE(r.lastName, '')) as name,
                            dp.phone,
                            dp.is_available,
                            dp.current_lat,
                            dp.current_lng,
                            dp.last_location_update,
                            dp.status as driver_status,
                            COUNT(o.order_id) as active_orders,
                            COALESCE(MAX(o.created_at), NULL) as last_order_time
                        FROM delivery_partner dp
                        LEFT JOIN registrations r ON dp.user_id = r.user_id
                        LEFT JOIN orders o ON dp.id = o.assigned_driver_id 
                            AND o.status IN ('confirmed', 'preparing', 'out_for_delivery', 'travelling')
                        WHERE dp.status = 'active'
                            AND dp.last_location_update >= DATE_SUB(NOW(), INTERVAL {minutes_threshold} MINUTE)
                            AND dp.current_lat IS NOT NULL 
                            AND dp.current_lng IS NOT NULL
                        GROUP BY dp.id, r.firstName, r.lastName, dp.phone, dp.is_available, 
                                dp.current_lat, dp.current_lng, dp.last_location_update, dp.status
                        ORDER BY dp.last_location_update DESC
                    """)
                
                results = cursor.fetchall()
                
                # Format fleet data for map visualization
                fleet_data = []
                available_count = 0
                busy_count = 0
                total_active_orders = 0
                
                for row in results:
                    (driver_id, name, phone, is_available, lat, lng, 
                     last_location_update, driver_status, active_orders, last_order_time) = row
                    
                    # Calculate location freshness
                    if last_location_update:
                        age_minutes = (timezone.now() - last_location_update).total_seconds() / 60
                        location_freshness = 'realtime' if age_minutes < 5 else ('fresh' if age_minutes < 15 else 'stale')
                    else:
                        location_freshness = 'unknown'
                    
                    driver_info = {
                        'driver_id': driver_id,
                        'name': name or f'Driver {driver_id}',
                        'phone': phone,
                        'status': 'available' if is_available else 'busy',
                        'driver_status': driver_status,
                        'location': {
                            'lat': float(lat),
                            'lng': float(lng),
                            'last_update': last_location_update.isoformat() if last_location_update else None,
                            'freshness': location_freshness
                        },
                        'active_orders': active_orders,
                        'last_order_time': last_order_time.isoformat() if last_order_time else None,
                        'performance': {
                            'orders_today': 0,  # Could be calculated if needed
                            'completion_rate': 0  # Could be calculated if needed
                        }
                    }
                    
                    fleet_data.append(driver_info)
                    
                    if is_available:
                        available_count += 1
                    else:
                        busy_count += 1
                    
                    total_active_orders += active_orders
                
                # Get fleet summary statistics
                cursor.execute(f"""
                    SELECT 
                        COUNT(*) as total_drivers,
                        COUNT(CASE WHEN status = 'active' THEN 1 END) as active_drivers,
                        COUNT(CASE WHEN is_available = 1 THEN 1 END) as available_drivers,
                        COUNT(CASE WHEN is_available = 0 THEN 1 END) as busy_drivers,
                        COUNT(CASE WHEN last_location_update >= DATE_SUB(NOW(), INTERVAL {minutes_threshold} MINUTE) 
                            AND current_lat IS NOT NULL AND current_lng IS NOT NULL THEN 1 END) as drivers_with_location
                    FROM delivery_partner
                """)
                
                fleet_stats = cursor.fetchone()
                (total_drivers, active_drivers, available_drivers, 
                 busy_drivers, drivers_with_location) = fleet_stats
                
                return Response({
                    'success': True,
                    'message': 'Active fleet data retrieved successfully',
                    'metadata': {
                        'minutes_threshold': minutes_threshold,
                        'total_drivers': total_drivers,
                        'active_drivers': active_drivers,
                        'available_drivers': available_drivers,
                        'busy_drivers': busy_drivers,
                        'drivers_with_recent_location': drivers_with_location,
                        'total_active_orders': total_active_orders,
                        'fleet_utilization': round((busy_count / max(available_count + busy_count, 1)) * 100, 2)
                    },
                    'fleet': fleet_data
                }, status=status.HTTP_200_OK)
                
        except Exception as e:
            logger.error(f"Error retrieving active fleet: {str(e)}")
            return Response({
                'success': False,
                'message': f'Error retrieving active fleet: {str(e)}',
                'fleet': []
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class FleetHeatmapView(APIView):
    """
    Fleet density heatmap data
    GET /api/v1/admin/delivery/heatmap/
    Returns grid-based location density for heatmap visualization
    """
    permission_classes = []
    
    def get(self, request):
        """Get fleet heatmap data"""
        try:
            # Get query parameters
            minutes_threshold = int(request.query_params.get('minutes', 15))
            grid_size = float(request.query_params.get('grid_size', 0.01))  # ~1km grid
            
            cutoff_time = timezone.now() - timezone.timedelta(minutes=minutes_threshold)
            
            with connection.cursor() as cursor:
                # Create grid-based density query
                cursor.execute(f"""
                    SELECT 
                        ROUND(dp.current_lat / {grid_size}) * {grid_size} as lat_grid,
                        ROUND(dp.current_lng / {grid_size}) * {grid_size} as lng_grid,
                        COUNT(*) as driver_count,
                        COUNT(CASE WHEN dp.is_available = 1 THEN 1 END) as available_count,
                        AVG(dp.last_location_update) as avg_update_time
                    FROM delivery_partner dp
                    WHERE dp.status = 'active'
                        AND dp.last_location_update >= DATE_SUB(NOW(), INTERVAL {minutes_threshold} MINUTE)
                        AND dp.current_lat IS NOT NULL 
                        AND dp.current_lng IS NOT NULL
                    GROUP BY lat_grid, lng_grid
                    HAVING driver_count > 0
                    ORDER BY driver_count DESC
                """)
                
                results = cursor.fetchall()
                
                # Format heatmap data
                heatmap_data = []
                for row in results:
                    lat_grid, lng_grid, driver_count, available_count, avg_update_time = row
                    
                    heatmap_data.append({
                        'lat': float(lat_grid),
                        'lng': float(lng_grid),
                        'weight': driver_count,  # Heat intensity
                        'available_drivers': available_count,
                        'busy_drivers': driver_count - available_count,
                        'avg_update_time': avg_update_time.isoformat() if avg_update_time else None
                    })
                
                return Response({
                    'success': True,
                    'message': 'Fleet heatmap data retrieved successfully',
                    'metadata': {
                        'minutes_threshold': minutes_threshold,
                        'grid_size': grid_size,
                        'hotspots': len(heatmap_data),
                        'total_grid_points': len(heatmap_data)
                    },
                    'heatmap': heatmap_data
                }, status=status.HTTP_200_OK)
                
        except Exception as e:
            logger.error(f"Error retrieving fleet heatmap: {str(e)}")
            return Response({
                'success': False,
                'message': f'Error retrieving fleet heatmap: {str(e)}',
                'heatmap': []
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
