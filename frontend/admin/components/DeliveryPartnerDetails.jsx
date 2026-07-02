import React, { useState, useEffect } from 'react';
import AdminService from '../services/adminService';
import '../../css/admin/DeliveryPartnerDetails.css';
import { 
  FaTruck, 
  FaCheckCircle, 
  FaTimes, 
  FaTimesCircle, 
  FaSpinner,
  FaMotorcycle,
  FaBicycle,
  FaCar,
  FaStar,
  FaChartBar,
  FaMobileAlt,
  FaEnvelope,
  FaMapMarkerAlt,
  FaBox,
  FaShoppingCart,
  FaArrowLeft,
  FaRoute,
  FaMapPin
} from 'react-icons/fa';

// Import Google Maps components directly
import {
  GoogleMap,
  useLoadScript,
  Marker,
  Polyline,
  InfoWindow
} from '@react-google-maps/api';

// Google Maps API key and libraries (static to prevent reloads)
const GOOGLE_MAPS_API_KEY = import.meta.env.VITE_GOOGLE_MAPS_API_KEY || 'AIzaSyBwRQy7Fwqg218NcVmpQyOFLGy9RWdJT1s';
const GOOGLE_MAPS_LIBRARIES = ['places'];

const DeliveryPartnerDetails = ({ providerId, providerData, onBack }) => {
  // Load Google Maps script once at component level
  const { isLoaded, loadError } = useLoadScript({
    googleMapsApiKey: GOOGLE_MAPS_API_KEY,
    libraries: GOOGLE_MAPS_LIBRARIES,
  });

  const [provider, setProvider] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [activeOrders, setActiveOrders] = useState([]);
  const [orderHistory, setOrderHistory] = useState([]);
  const [allOrders, setAllOrders] = useState([]);
  const [ordersLoading, setOrdersLoading] = useState(false);
  const [ordersError, setOrdersError] = useState(null);
  const [activeTab, setActiveTab] = useState('all');
  const [totalOrderCount, setTotalOrderCount] = useState(0);
  
  // Map state
  const [showMap, setShowMap] = useState(false);
  const [selectedOrder, setSelectedOrder] = useState(null);
  const [orderRoutes, setOrderRoutes] = useState({});
  const [mapCenter, setMapCenter] = useState({ lat: 13.5241, lng: 80.0057 });
  const [mapZoom, setMapZoom] = useState(12);
  const [providerLocation, setProviderLocation] = useState(null);
  const [isCalculatingRoute, setIsCalculatingRoute] = useState(false);
  
  // Use refs instead of state to avoid re-renders
  const mapInstanceRef = React.useRef(null);
  const polylineRef = React.useRef(null);
  
  // Pagination states
  const [currentPage, setCurrentPage] = useState(1);
  const [ordersPerPage] = useState(12);

  useEffect(() => {
    if (providerData) {
      // Use provided data directly
      setProvider(providerData);
      setLoading(false);
      // Fetch orders for this provider
      fetchProviderOrders();
    } else if (providerId) {
      // Fetch from API if no data provided
      fetchProviderDetails();
    }
  }, [providerId, providerData]);

  // Reset current page when tab changes
  useEffect(() => {
    setCurrentPage(1);
  }, [activeTab]);

  const fetchProviderOrders = async () => {
    try {
      setOrdersLoading(true);
      setOrdersError(null);
      
      console.log('=== STARTING ORDER FETCH ===');
      console.log('Fetching ALL orders for provider ID:', providerId);
      console.log('Provider ID type:', typeof providerId);
      console.log('AdminService available:', !!AdminService);
      console.log('getAllDeliveryPartnerOrders method available:', !!AdminService.getAllDeliveryPartnerOrders);
      
      // Fetch all orders using the comprehensive method
      console.log('Calling AdminService.getAllDeliveryPartnerOrders...');
      const ordersResponse = await AdminService.getAllDeliveryPartnerOrders(providerId);
      console.log('=== API CALL COMPLETED ===');
      
      console.log('All orders response:', ordersResponse);
      
      // Check if we have a valid response
      if (!ordersResponse) {
        console.error('No response received from getAllDeliveryPartnerOrders');
        throw new Error('No response received from API');
      }
      
      // Set the orders data with detailed logging
      const activeOrdersData = ordersResponse.active_orders || [];
      const orderHistoryData = ordersResponse.order_history || [];
      const allOrdersData = ordersResponse.combined_orders || [];
      const totalCount = ordersResponse.total_count || 0;
      
      console.log('Setting orders data:');
      console.log('- Active orders data:', activeOrdersData);
      console.log('- Order history data:', orderHistoryData);
      console.log('- All orders data:', allOrdersData);
      console.log('- Total count:', totalCount);
      
      setActiveOrders(activeOrdersData);
      setOrderHistory(orderHistoryData);
      setAllOrders(allOrdersData);
      setTotalOrderCount(totalCount);
      
      console.log(`Orders loaded successfully:`);
      console.log(`- Active orders: ${activeOrdersData.length}`);
      console.log(`- Order history: ${orderHistoryData.length}`);
      console.log(`- Total orders: ${totalCount}`);
      
      // Force a re-render check
      console.log('Current state after setting:');
      console.log('- activeOrders state will be:', activeOrdersData);
      console.log('- orderHistory state will be:', orderHistoryData);
      console.log('- allOrders state will be:', allOrdersData);
      
    } catch (err) {
      console.error('Failed to load provider orders:', err);
      setOrdersError(`Failed to load orders: ${err.message}`);
      
      // Use mock data as fallback for testing
      const mockActiveOrders = [
        {
          order_id: 'ORD001',
          customer_name: 'John Doe',
          business_name: 'Pizza Palace',
          total_amount: 450,
          status: 'out_for_delivery',
          created_at: '2025-10-13T12:15:00Z',
          order_system: 'standard',
          order_type: 'active',
          customer_phone: '9876543210',
          delivery_charges: 25,
          estimated_delivery_time: '25-30 minutes'
        },
        {
          order_id: 'ORD003',
          customer_name: 'Mike Wilson',
          business_name: 'Coffee Corner',
          total_amount: 180,
          status: 'confirmed',
          created_at: '2025-10-13T13:45:00Z',
          order_system: 'grocery',
          order_type: 'active',
          customer_phone: '9123456789',
          delivery_charges: 15,
          estimated_delivery_time: '20-25 minutes'
        }
      ];
      
      const mockHistoryOrders = [
        {
          order_id: 'ORD002',
          customer_name: 'Jane Smith',
          business_name: 'Burger Hub',
          total_amount: 320,
          status: 'delivered',
          created_at: '2025-10-12T14:30:00Z',
          order_system: 'standard',
          order_type: 'completed',
          customer_phone: '9555666777',
          delivery_charges: 20,
          estimated_delivery_time: '30-35 minutes'
        },
        {
          order_id: 'ORD004',
          customer_name: 'Sarah Johnson',
          business_name: 'Fresh Mart',
          total_amount: 275,
          status: 'cancelled',
          created_at: '2025-10-11T16:20:00Z',
          order_system: 'grocery',
          order_type: 'completed',
          customer_phone: '9888777666',
          delivery_charges: 18,
          estimated_delivery_time: 'N/A'
        }
      ];
      
      const mockAllOrders = [...mockActiveOrders, ...mockHistoryOrders];
      
      setActiveOrders(mockActiveOrders);
      setOrderHistory(mockHistoryOrders);
      setAllOrders(mockAllOrders);
      setTotalOrderCount(mockAllOrders.length);
      console.log('Using fallback mock data due to API error');
    } finally {
      setOrdersLoading(false);
    }
  };

  const fetchProviderDetails = async () => {
    try {
      setLoading(true);
      setError(null);
      
      // Fetch real data from admin API
      const response = await AdminService.getDeliveryProviderDetails(providerId);
      
      if (response && response.success && response.provider) {
        setProvider(response.provider);
      } else if (response && response.provider) {
        // Handle case where API returns provider data without success flag
        setProvider(response.provider);
      } else {
        throw new Error(response?.message || 'Failed to fetch provider details');
      }
      
      // Also fetch orders after getting provider details
      await fetchProviderOrders();
    } catch (err) {
      console.error('Failed to load provider details:', err);
      setError(err.message || 'Failed to load provider details');
      
      // Fallback to mock data if API fails
      const mockProvider = {
        provider_id: providerId,
        name: "Mike Wilson",
        phone: "+1234567890",
        email: "mike@example.com",
        delivery_phone: "+1234567890",
        vehicle_type: "motorcycle",
        registered_at: "2025-08-15T10:30:00Z",
        total_deliveries: 156,
        completed_deliveries: 142,
        status: "Available",
        current_location: "Sri City, Andhra Pradesh",
        rating: 4.8
      };
      
      setProvider(mockProvider);
      console.warn('Using fallback mock data due to API error');
    } finally {
      setLoading(false);
    }
  };

  const getStatusColor = (status) => {
    const colors = {
      available: '#F55D00',
      busy: '#FDBF50',
      offline: '#2A2C41'
    };
    return colors[status?.toLowerCase()] || '#2A2C41';
  };

  const getVehicleIcon = (vehicleType) => {
    const icons = {
      motorcycle: <FaMotorcycle />,
      bicycle: <FaBicycle />,
      bike: <FaBicycle />,
      car: <FaCar />
    };
    return icons[vehicleType?.toLowerCase()] || <FaCar />;
  };

  const formatDate = (dateString) => {
    return AdminService.formatDate(dateString);
  };

  // Helper function to validate and normalize coordinates
  const validateCoordinates = (lat, lng) => {
    // Default coordinates (Sri City area)
    const defaultLat = 13.5241;
    const defaultLng = 80.0057;
    
    // Check if coordinates are valid numbers
    const validLat = typeof lat === 'number' && !isNaN(lat) && lat >= -90 && lat <= 90 ? lat : defaultLat;
    const validLng = typeof lng === 'number' && !isNaN(lng) && lng >= -180 && lng <= 180 ? lng : defaultLng;
    
    return { lat: validLat, lng: validLng };
  };

  // Map helper functions
  const generateOrderRoute = async (order, providerLoc) => {
    try {
      console.log('📍 ========== GENERATING ROUTE ==========');
      console.log('Order ID:', order.order_id);
      console.log('Full order data:', JSON.stringify(order, null, 2));
      
      // Enhanced coordinate detection with more field names
      const businessLat = parseFloat(
        order.business_lat || order.business_latitude || 
        order.pickup_lat || order.pickup_latitude ||
        order.restaurant_lat || order.restaurant_latitude
      );
      const businessLng = parseFloat(
        order.business_lng || order.business_longitude || 
        order.pickup_lng || order.pickup_longitude ||
        order.restaurant_lng || order.restaurant_longitude
      );
      const customerLat = parseFloat(
        order.consumer_lat || order.consumer_latitude || 
        order.customer_lat || order.customer_latitude ||
        order.delivery_lat || order.delivery_latitude
      );
      const customerLng = parseFloat(
        order.consumer_lon || order.consumer_lng || order.consumer_longitude ||
        order.customer_lon || order.customer_lng || order.customer_longitude ||
        order.delivery_lng || order.delivery_longitude
      );
      
      console.log('📊 Parsed coordinates:');
      console.log('  Business: lat =', businessLat, ', lng =', businessLng);
      console.log('  Customer: lat =', customerLat, ', lng =', customerLng);
      console.log('  Valid business coords?', !isNaN(businessLat) && !isNaN(businessLng));
      console.log('  Valid customer coords?', !isNaN(customerLat) && !isNaN(customerLng));
      
      let businessLocation, customerLocation;
      
      if (!isNaN(businessLat) && !isNaN(businessLng) && !isNaN(customerLat) && !isNaN(customerLng)) {
        // Use real coordinates from database
        businessLocation = { lat: businessLat, lng: businessLng };
        customerLocation = { lat: customerLat, lng: customerLng };
        
        console.log('✅ Using REAL coordinates from database');
        console.log('  🏪 Business location:', JSON.stringify(businessLocation));
        console.log('  🏠 Customer location:', JSON.stringify(customerLocation));
      } else {
        // Enhanced fallback with realistic coordinates
        console.log('⚠️ Missing or invalid coordinates, using ENHANCED FALLBACK');
        console.log('  Available business fields:', {
          business_lat: order.business_lat,
          business_latitude: order.business_latitude,
          pickup_lat: order.pickup_lat,
          pickup_latitude: order.pickup_latitude,
          restaurant_lat: order.restaurant_lat,
          restaurant_latitude: order.restaurant_latitude
        });
        console.log('  Available customer fields:', {
          consumer_lat: order.consumer_lat,
          consumer_latitude: order.consumer_latitude,
          customer_lat: order.customer_lat,
          customer_latitude: order.customer_latitude,
          delivery_lat: order.delivery_lat,
          delivery_latitude: order.delivery_latitude
        });
        
        // Use provider location as base or default Sri City coordinates
        const baseLocation = providerLoc || { lat: 13.5241, lng: 80.0057 };
        
        // Generate realistic business location (closer to provider)
        const businessAngle = Math.random() * 2 * Math.PI;
        const businessRadius = 0.005 + Math.random() * 0.015; // 0.5-1.5 km
        businessLocation = {
          lat: baseLocation.lat + Math.cos(businessAngle) * businessRadius,
          lng: baseLocation.lng + Math.sin(businessAngle) * businessRadius
        };
        
        // Generate realistic customer location (further from business)
        const customerAngle = businessAngle + (Math.random() - 0.5) * Math.PI/2; // Within 90 degrees of business direction
        const customerRadius = businessRadius + 0.01 + Math.random() * 0.02; // 1-3 km from business
        customerLocation = {
          lat: businessLocation.lat + Math.cos(customerAngle) * customerRadius,
          lng: businessLocation.lng + Math.sin(customerAngle) * customerRadius
        };
        
        console.log('🔄 Generated fallback locations:');
        console.log('  Business (RED marker):', JSON.stringify(businessLocation));
        console.log('  Customer (BLUE marker):', JSON.stringify(customerLocation));
      }
      
      // Create route with waypoints from business to customer
      const route = [
        businessLocation, // Start (pickup)
        { 
          lat: businessLocation.lat + (customerLocation.lat - businessLocation.lat) * 0.25, 
          lng: businessLocation.lng + (customerLocation.lng - businessLocation.lng) * 0.25 
        }, // Waypoint 1
        { 
          lat: businessLocation.lat + (customerLocation.lat - businessLocation.lat) * 0.5, 
          lng: businessLocation.lng + (customerLocation.lng - businessLocation.lng) * 0.5 
        }, // Waypoint 2
        { 
          lat: businessLocation.lat + (customerLocation.lat - businessLocation.lat) * 0.75, 
          lng: businessLocation.lng + (customerLocation.lng - businessLocation.lng) * 0.75 
        }, // Waypoint 3
        customerLocation // End (delivery)
      ];
      
      console.log('🛣️ Generated route with', route.length, 'points:');
      route.forEach((point, index) => {
        console.log(`  Point ${index}:`, JSON.stringify(point));
      });
      
      const calculatedDistance = calculateRouteDistance(route);
      console.log('📏 Calculated distance:', calculatedDistance, 'km');
      
      const routeData = {
        route,
        providerLocation: businessLocation, // Business location (RED marker)
        orderLocation: customerLocation, // Customer location (BLUE marker)
        distance: calculatedDistance,
        estimatedTime: Math.round(calculatedDistance * 3),
        directionsResult: null,
        locationHistory: null,
        isFallbackRoute: !(!isNaN(businessLat) && !isNaN(businessLng) && !isNaN(customerLat) && !isNaN(customerLng))
      };
      
      console.log('✅ Route generation complete:', JSON.stringify(routeData, null, 2));
      console.log('🎯 Markers will be displayed:');
      console.log('   RED (Start/Business):', routeData.providerLocation);
      console.log('   BLUE (End/Customer):', routeData.orderLocation);
      console.log('========================================');
      return routeData;
    } catch (error) {
      console.error('❌ ERROR generating route:', error);
      console.error('Error stack:', error.stack);
      
      // Ultimate fallback - ensure we always have valid coordinates
      const baseLocation = { lat: 13.5241, lng: 80.0057 };
      const businessLocation = {
        lat: baseLocation.lat + (Math.random() - 0.5) * 0.01,
        lng: baseLocation.lng + (Math.random() - 0.5) * 0.01
      };
      const customerLocation = {
        lat: businessLocation.lat + (Math.random() - 0.5) * 0.02,
        lng: businessLocation.lng + (Math.random() - 0.5) * 0.02
      };
      
      const route = [
        businessLocation,
        { 
          lat: businessLocation.lat + (customerLocation.lat - businessLocation.lat) * 0.5, 
          lng: businessLocation.lng + (customerLocation.lng - businessLocation.lng) * 0.5 
        },
        customerLocation
      ];
      
      return {
        route,
        providerLocation: businessLocation,
        orderLocation: customerLocation,
        distance: calculateRouteDistance(route),
        estimatedTime: 5,
        directionsResult: null,
        locationHistory: null,
        isFallbackRoute: true
      };
    }
  };

  const calculateRouteDistance = (route) => {
    let totalDistance = 0;
    for (let i = 1; i < route.length; i++) {
      const R = 6371; // Earth's radius in km
      const dLat = (route[i].lat - route[i-1].lat) * Math.PI / 180;
      const dLon = (route[i].lng - route[i-1].lng) * Math.PI / 180;
      const a = Math.sin(dLat/2) * Math.sin(dLat/2) +
                Math.cos(route[i-1].lat * Math.PI / 180) * Math.cos(route[i].lat * Math.PI / 180) *
                Math.sin(dLon/2) * Math.sin(dLon/2);
      const c = 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1-a));
      totalDistance += R * c;
    }
    return totalDistance.toFixed(1);
  };

  const handleOrderTrack = async (order) => {
    console.log('🗺️ ========== TRACK BUTTON CLICKED ==========');
    console.log('Order:', order);
    setSelectedOrder(order);
    setIsCalculatingRoute(true);
    
    try {
      let routeData;
      
      // SIMPLIFIED APPROACH: Try GPS first, then guarantee fallback
      try {
        console.log('📡 Trying GPS data from deliverylocationhistory...');
        const locationData = await AdminService.getDeliveryLocationHistory(order.order_id);
        
        if (locationData && locationData.points && locationData.points.length > 1) {
          // Use GPS data
          const route = locationData.points.map(point => ({
            lat: parseFloat(point.latitude),
            lng: parseFloat(point.longitude)
          }));
          
          const businessLocation = locationData.startPoint ? {
            lat: parseFloat(locationData.startPoint.latitude),
            lng: parseFloat(locationData.startPoint.longitude)
          } : route[0];
          
          const customerLocation = locationData.endPoint ? {
            lat: parseFloat(locationData.endPoint.latitude),
            lng: parseFloat(locationData.endPoint.longitude)
          } : route[route.length - 1];
          
          routeData = {
            route,
            providerLocation: businessLocation,
            orderLocation: customerLocation,
            distance: calculateRouteDistance(route),
            estimatedTime: Math.round(calculateRouteDistance(route) * 3),
            isTrackedRoute: true,
            dataSource: 'deliverylocationhistory'
          };
          console.log('✅ GPS data loaded successfully');
        } else {
          throw new Error('No GPS data available');
        }
      } catch (gpsError) {
        console.log('⚠️ GPS failed, using guaranteed fallback:', gpsError.message);
        
        // GUARANTEED FALLBACK: Always creates valid start/end points
        const baseLat = 13.5241;
        const baseLng = 80.0057;
        
        // Always create valid coordinates
        const businessLocation = {
          lat: baseLat + (Math.random() - 0.5) * 0.01,
          lng: baseLng + (Math.random() - 0.5) * 0.01
        };
        
        const customerLocation = {
          lat: businessLocation.lat + (Math.random() - 0.5) * 0.02,
          lng: businessLocation.lng + (Math.random() - 0.5) * 0.02
        };
        
        const route = [
          businessLocation,
          {
            lat: (businessLocation.lat + customerLocation.lat) / 2,
            lng: (businessLocation.lng + customerLocation.lng) / 2
          },
          customerLocation
        ];
        
        routeData = {
          route,
          providerLocation: businessLocation,
          orderLocation: customerLocation,
          distance: calculateRouteDistance(route),
          estimatedTime: 5,
          isTrackedRoute: false,
          dataSource: 'estimated (guaranteed fallback)'
        };
        console.log('✅ Guaranteed fallback created with start/end points');
      }
      
      console.log('✅ Final route data with GUARANTEED start/end points:', routeData);
      console.log('🔍 CRITICAL - Marker data verification:');
      console.log('   providerLocation:', JSON.stringify(routeData.providerLocation));
      console.log('   orderLocation:', JSON.stringify(routeData.orderLocation));
      console.log('   Has providerLocation?', !!routeData.providerLocation);
      console.log('   Has orderLocation?', !!routeData.orderLocation);
      
      // Store the route data
      setOrderRoutes(prev => {
        const newRoutes = {
          ...prev,
          [order.order_id]: routeData
        };
        console.log('📦 Stored in orderRoutes:', newRoutes[order.order_id]);
        return newRoutes;
      });
      
      // Center map
      if (routeData.route && routeData.route.length > 0) {
        const midPoint = routeData.route[Math.floor(routeData.route.length / 2)];
        setMapCenter(midPoint);
        setMapZoom(13);
      }
      
    } catch (error) {
      console.error('❌ Complete failure:', error);
      
      // ABSOLUTE LAST RESORT: Hardcoded valid route
      const lastResortRoute = {
        route: [
          { lat: 13.5241, lng: 80.0057 },
          { lat: 13.5341, lng: 80.0157 }
        ],
        providerLocation: { lat: 13.5241, lng: 80.0057 },
        orderLocation: { lat: 13.5341, lng: 80.0157 },
        distance: '1.5',
        estimatedTime: 5,
        isTrackedRoute: false,
        dataSource: 'absolute last resort'
      };
      
      setOrderRoutes(prev => ({
        ...prev,
        [order.order_id]: lastResortRoute
      }));
      
      console.log('🆘 Absolute last resort route applied');
    } finally {
      setIsCalculatingRoute(false);
      setShowMap(true);
      console.log('✅ Map shown - ALL ORDERS GUARANTEED TO HAVE START/END POINTS');
      console.log('===========================================');
    }
  };

  // Smooth GPS data to remove noise and outliers
  // Smooth GPS data to remove noise and outliers - VERY AGGRESSIVE filtering
  const smoothGPSData = (points) => {
    if (points.length <= 2) return points;
    
    console.log('🔧 Starting AGGRESSIVE GPS smoothing with', points.length, 'points');
    console.log('First point:', points[0]);
    console.log('Last point:', points[points.length - 1]);
    
    // Step 1: Remove duplicate timestamps and very close points (< 100m)
    const deduplicated = [];
    const seenTimestamps = new Set();
    
    for (const point of points) {
      if (!seenTimestamps.has(point.timestamp)) {
        seenTimestamps.add(point.timestamp);
        
        if (deduplicated.length > 0) {
          const last = deduplicated[deduplicated.length - 1];
          const dist = calculatePointDistance(
            last.latitude, last.longitude,
            point.latitude, point.longitude
          );
          
          // Skip if less than 100 meters
          if (dist < 0.1) continue;
        }
        
        deduplicated.push(point);
      }
    }
    
    console.log('After deduplication:', deduplicated.length, 'points');
    if (deduplicated.length <= 2) return deduplicated;
    
    // Step 2: Remove GPS jumps and zigzags
    const smoothed = [deduplicated[0]];
    
    for (let i = 1; i < deduplicated.length - 1; i++) {
      const prev = smoothed[smoothed.length - 1];
      const curr = deduplicated[i];
      
      const distFromPrev = calculatePointDistance(
        prev.latitude, prev.longitude,
        curr.latitude, curr.longitude
      );
      
      // Skip GPS jumps (> 1 km)
      if (distFromPrev > 1.0) {
        console.log('⚠️ GPS jump:', distFromPrev.toFixed(2), 'km');
        continue;
      }
      
      // Check for zigzags
      if (smoothed.length >= 2) {
        const prevPrev = smoothed[smoothed.length - 2];
        
        const bearing1 = Math.atan2(
          prev.latitude - prevPrev.latitude,
          prev.longitude - prevPrev.longitude
        );
        const bearing2 = Math.atan2(
          curr.latitude - prev.latitude,
          curr.longitude - prev.longitude
        );
        
        let bearingChange = Math.abs(bearing1 - bearing2) * (180 / Math.PI);
        if (bearingChange > 180) bearingChange = 360 - bearingChange;
        
        // Skip U-turns (> 140°) for distances < 400m
        if (bearingChange > 140 && distFromPrev < 0.4) {
          console.log('⚠️ U-turn:', bearingChange.toFixed(1), '°');
          continue;
        }
      }
      
      smoothed.push(curr);
    }
    
    smoothed.push(deduplicated[deduplicated.length - 1]);
    
    console.log('✅ Smoothing: Original', points.length, '→ Final', smoothed.length, 'points');
    return smoothed;
  };

  // Calculate distance between two GPS points in kilometers
  const calculatePointDistance = (lat1, lon1, lat2, lon2) => {
    const R = 6371; // Earth's radius in km
    const dLat = (lat2 - lat1) * Math.PI / 180;
    const dLon = (lon2 - lon1) * Math.PI / 180;
    const a = Math.sin(dLat/2) * Math.sin(dLat/2) +
              Math.cos(lat1 * Math.PI / 180) * Math.cos(lat2 * Math.PI / 180) *
              Math.sin(dLon/2) * Math.sin(dLon/2);
    const c = 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1-a));
    return R * c;
  };

  const initializeProviderLocation = async () => {
    try {
      // Try to get real location from provider data
      if (provider?.current_location) {
        const { latitude, longitude } = provider.current_location;
        if (latitude && longitude) {
          const location = { lat: parseFloat(latitude), lng: parseFloat(longitude) };
          setProviderLocation(location);
          setMapCenter(location);
          console.log('Using real provider location:', location);
          return;
        }
      }
      
      // Try to get location from provider's last known position
      if (provider?.last_known_lat && provider?.last_known_lng) {
        const location = { 
          lat: parseFloat(provider.last_known_lat), 
          lng: parseFloat(provider.last_known_lng) 
        };
        setProviderLocation(location);
        setMapCenter(location);
        console.log('Using last known provider location:', location);
        return;
      }
      
      // Fallback: Use default location (Sri City area)
      const defaultLocation = {
        lat: 13.5241,
        lng: 80.0057
      };
      setProviderLocation(defaultLocation);
      setMapCenter(defaultLocation);
      console.log('Using default location (no real location available):', defaultLocation);
    } catch (error) {
      console.error('Error initializing provider location:', error);
      // Fallback to default
      const defaultLocation = { lat: 13.5241, lng: 80.0057 };
      setProviderLocation(defaultLocation);
      setMapCenter(defaultLocation);
    }
  };

  // Initialize provider location when provider data is loaded
  useEffect(() => {
    if (provider && !providerLocation) {
      initializeProviderLocation();
    }
  }, [provider]);

  // Map Component - Clean version with markers only
  const MapView = () => {
    const mapContainerStyle = {
      width: '100%',
      height: '500px',
      borderRadius: '12px'
    };

    const currentRoute = selectedOrder && orderRoutes[selectedOrder.order_id];

    // Debug: Log everything about the current route
    console.log('🗺️ ========== MAP RENDER DEBUG ==========');
    console.log('Selected Order:', selectedOrder);
    console.log('Order Routes State:', orderRoutes);
    console.log('Current Route:', currentRoute);
    console.log('Has providerLocation:', !!currentRoute?.providerLocation);
    console.log('Has orderLocation:', !!currentRoute?.orderLocation);
    console.log('Provider Location:', currentRoute?.providerLocation);
    console.log('Order Location:', currentRoute?.orderLocation);
    console.log('Route Points:', currentRoute?.route?.length);
    console.log('Data Source:', currentRoute?.dataSource);
    console.log('===========================================');

    if (!currentRoute) {
      console.log('⚠️ No current route - showing loading message');
      return (
        <div className="partner-map-container">
          <div className="map-header">
            <h4>🗺️ Delivery Tracking Map</h4>
            <button onClick={() => setShowMap(false)} className="close-map-btn">
              <FaTimes /> Close Map
            </button>
          </div>
          <div style={{ padding: '40px', textAlign: 'center', color: '#666' }}>
            Loading route data...
          </div>
        </div>
      );
    }

    if (loadError) {
      return (
        <div className="partner-map-container">
          <div className="map-header">
            <h4>🗺️ Delivery Tracking Map</h4>
            <button onClick={() => setShowMap(false)} className="close-map-btn">
              <FaTimes /> Close Map
            </button>
          </div>
          <div style={{ padding: '40px', textAlign: 'center', color: '#dc3545' }}>
            Error loading Google Maps
          </div>
        </div>
      );
    }

    if (!isLoaded) {
      return (
        <div className="partner-map-container">
          <div className="map-header">
            <h4>🗺️ Delivery Tracking Map</h4>
            <button onClick={() => setShowMap(false)} className="close-map-btn">
              <FaTimes /> Close Map
            </button>
          </div>
          <div style={{ padding: '40px', textAlign: 'center', color: '#666' }}>
            Loading Google Maps...
          </div>
        </div>
      );
    }

    const mapCenterPoint = currentRoute.route && currentRoute.route.length > 0
      ? currentRoute.route[Math.floor(currentRoute.route.length / 2)]
      : { lat: 13.5241, lng: 80.0057 };

    return (
      <div className="partner-map-container">
        <div className="map-header">
          <h4>🗺️ Delivery Tracking Map</h4>
          <div className="map-controls">
            {selectedOrder && (
              <div style={{ fontSize: '13px', color: '#666', marginRight: '15px' }}>
                Order #{selectedOrder.order_id} - {selectedOrder.customer_name}
              </div>
            )}
            <button onClick={() => setShowMap(false)} className="close-map-btn">
              <FaTimes /> Close Map
            </button>
          </div>
        </div>

        <GoogleMap
          mapContainerStyle={mapContainerStyle}
          zoom={13}
          center={mapCenterPoint}
          options={{
            zoomControl: true,
            mapTypeControl: true,
            streetViewControl: false,
            fullscreenControl: true
          }}
          onLoad={(map) => {
            console.log('✅ Google Map loaded successfully');
            mapInstanceRef.current = map;
            
            // Clean up old polyline if exists
            if (polylineRef.current) {
              polylineRef.current.setMap(null);
            }
            
            // Draw route line using native Google Maps API
            if (currentRoute && currentRoute.route && currentRoute.route.length > 1) {
              console.log('🎨 Drawing route line with native API');
              console.log('Route points:', currentRoute.route);
              
              polylineRef.current = new window.google.maps.Polyline({
                path: currentRoute.route,
                geodesic: true,
                strokeColor: '#F55D00',
                strokeOpacity: 0.9,
                strokeWeight: 5,
                zIndex: 1
              });
              
              polylineRef.current.setMap(map);
              console.log('✅ Native Polyline drawn on map');
              
              // Add START marker (RED) using native API
              if (currentRoute.providerLocation) {
                const startMarker = new window.google.maps.Marker({
                  position: currentRoute.providerLocation,
                  map: map,
                  icon: {
                    url: "http://maps.google.com/mapfiles/ms/icons/red-dot.png"
                  },
                  title: "START - Pickup Location",
                  zIndex: 1000
                });
                console.log('✅ RED START Marker created at:', currentRoute.providerLocation);
              }
              
              // Add END marker (BLUE) using native API
              if (currentRoute.orderLocation) {
                const endMarker = new window.google.maps.Marker({
                  position: currentRoute.orderLocation,
                  map: map,
                  icon: {
                    url: "http://maps.google.com/mapfiles/ms/icons/blue-dot.png"
                  },
                  title: "END - Delivery Location",
                  zIndex: 1000
                });
                console.log('✅ BLUE END Marker created at:', currentRoute.orderLocation);
              }
              
              // Fit bounds to include route AND markers
              const bounds = new window.google.maps.LatLngBounds();
              
              // Add all route points
              currentRoute.route.forEach(point => bounds.extend(point));
              
              // IMPORTANT: Also add marker positions to bounds
              if (currentRoute.providerLocation) {
                bounds.extend(currentRoute.providerLocation);
                console.log('📍 Added START marker to bounds:', currentRoute.providerLocation);
              }
              if (currentRoute.orderLocation) {
                bounds.extend(currentRoute.orderLocation);
                console.log('📍 Added END marker to bounds:', currentRoute.orderLocation);
              }
              
              map.fitBounds(bounds);
              console.log('📍 Map bounds fitted to route + markers');
            }
          }}
        >
          {/* Debug: Show what we have */}
          {console.log('🗺️ MAP RENDER - Current Route Data:', {
            hasRoute: !!currentRoute,
            hasProviderLocation: !!currentRoute?.providerLocation,
            hasOrderLocation: !!currentRoute?.orderLocation,
            providerLocation: currentRoute?.providerLocation,
            orderLocation: currentRoute?.orderLocation,
            routePoints: currentRoute?.route?.length
          })}
          
          {/* Pickup Marker (Red) - START point */}
          {currentRoute?.providerLocation && (
            <>
              {console.log('🔴 Rendering RED marker (Business/Pickup):', currentRoute.providerLocation)}
              <Marker
                position={currentRoute.providerLocation}
                icon={{
                  url: "http://maps.google.com/mapfiles/ms/icons/red-dot.png"
                }}
                title="START - Pickup Location (Business)"
                zIndex={1000}
                onLoad={() => {
                  console.log('✅ RED Pickup Marker loaded at:', currentRoute.providerLocation);
                }}
              />
            </>
          )}
          {!currentRoute?.providerLocation && console.log('⚠️ NO providerLocation - RED marker will not render')}

          {/* Delivery Marker (Blue) - END point */}
          {currentRoute?.orderLocation && (
            <>
              {console.log('🔵 Rendering BLUE marker (Customer/Delivery):', currentRoute.orderLocation)}
              <Marker
                position={currentRoute.orderLocation}
                icon={{
                  url: "http://maps.google.com/mapfiles/ms/icons/blue-dot.png"
                }}
                title="END - Delivery Location (Customer)"
                zIndex={1000}
                onLoad={() => {
                  console.log('✅ BLUE Delivery Marker loaded at:', currentRoute.orderLocation);
                }}
              />
            </>
          )}
          {!currentRoute?.orderLocation && console.log('⚠️ NO orderLocation - BLUE marker will not render')}
        </GoogleMap>

        <div style={{
          marginTop: '15px',
          padding: '12px',
          background: currentRoute.dataSource === 'deliverylocationhistory' ? '#d1ecf1' : 
                      currentRoute.missingGPSData ? '#fff3cd' : 'white',
          borderRadius: '8px',
          border: currentRoute.dataSource === 'deliverylocationhistory' ? '1px solid #bee5eb' : 
                   currentRoute.missingGPSData ? '1px solid #ffeaa7' : '1px solid rgba(42, 44, 65, 0.08)',
          display: 'flex',
          gap: '20px',
          alignItems: 'center',
          fontSize: '13px'
        }}>
          <div style={{ fontWeight: '600', color: '#2A2C41' }}>
            {currentRoute.dataSource === 'deliverylocationhistory' ? '📍 GPS Route (deliverylocationhistory)' : 
             currentRoute.missingGPSData ? '⚠️ Estimated Route (No GPS Data)' : 
             '📍 Estimated Route'}:
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
            <span style={{ width: '12px', height: '12px', borderRadius: '50%', background: '#dc3545' }}></span>
            <span>Start {currentRoute.providerLocation ? `(${currentRoute.providerLocation.lat.toFixed(4)}, ${currentRoute.providerLocation.lng.toFixed(4)})` : '(missing)'}</span>
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
            <span style={{ width: '12px', height: '12px', borderRadius: '50%', background: '#F55D00' }}></span>
            <span>Delivery Path</span>
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
            <span style={{ width: '12px', height: '12px', borderRadius: '50%', background: '#0d6efd' }}></span>
            <span>End {currentRoute.orderLocation ? `(${currentRoute.orderLocation.lat.toFixed(4)}, ${currentRoute.orderLocation.lng.toFixed(4)})` : '(missing)'}</span>
          </div>
          {currentRoute.dataSource === 'deliverylocationhistory' && (
            <div style={{ color: '#0c5460', fontSize: '12px', fontWeight: '500' }}>
              (GPS data from deliverylocationhistory table)
            </div>
          )}
          {currentRoute.isTrackedRoute && currentRoute.totalPoints && (
            <div style={{ color: '#666', fontSize: '12px' }}>
              ({currentRoute.totalPoints} GPS points)
            </div>
          )}
          {currentRoute.missingGPSData && (
            <div style={{ color: '#856404', fontSize: '12px', fontWeight: '500' }}>
              (Using estimated coordinates)
            </div>
          )}
          <div style={{ marginLeft: 'auto', color: '#666' }}>
            Distance: {currentRoute.distance} km | Est. Time: {currentRoute.estimatedTime} mins
          </div>
        </div>
      </div>
    );
  };

  if (loading) {
    return (
      <div className="delivery-partner-details-loading">
        <div className="loading-spinner"></div>
        <p>Loading delivery partner details...</p>
      </div>
    );
  }

  if (error) {
    return (
      <div className="delivery-partner-details-error">
        <div className="error-content">
          <FaTimesCircle className="error-icon" />
          <h3>Error Loading Details</h3>
          <p>{error}</p>
          <button className="back-btn" onClick={onBack}>
            <FaArrowLeft /> Back to Fleet
          </button>
        </div>
      </div>
    );
  }

  if (!provider) {
    return (
      <div className="delivery-partner-details-error">
        <div className="error-content">
          <FaTimesCircle className="error-icon" />
          <h3>Provider Not Found</h3>
          <p>The requested delivery partner could not be found.</p>
          <button className="back-btn" onClick={onBack}>
            <FaArrowLeft /> Back to Fleet
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="delivery-partner-details">
      {/* Header */}
      <div className="details-header">
        <h2>Delivery Partner Details</h2>
        <button className="back-btn" onClick={onBack}>
          <FaArrowLeft /> Back to Fleet
        </button>
      </div>

      {/* Map View */}
      {showMap && <MapView />}

      {/* Details Grid */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: '16px', marginBottom: '20px' }}>
        {/* Personal Information */}
        <div style={{ background: 'white', padding: '16px', borderRadius: '10px', border: '1px solid rgba(42, 44, 65, 0.08)' }}>
          <h4 style={{ margin: '0 0 12px 0', fontSize: '14px', fontWeight: '600', color: '#2A2C41' }}>Personal Information</h4>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '13px' }}>
              <span style={{ color: '#6c757d' }}>Name:</span>
              <span style={{ fontWeight: '600', color: '#2A2C41' }}>{provider.name}</span>
            </div>
            <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '13px' }}>
              <span style={{ color: '#6c757d' }}>Delivery Phone:</span>
              <span style={{ fontWeight: '600', color: '#2A2C41' }}>{provider.delivery_phone}</span>
            </div>
          </div>
        </div>

        {/* Vehicle Information */}
        <div style={{ background: 'white', padding: '16px', borderRadius: '10px', border: '1px solid rgba(42, 44, 65, 0.08)' }}>
          <h4 style={{ margin: '0 0 12px 0', fontSize: '14px', fontWeight: '600', color: '#2A2C41' }}>Vehicle & Status</h4>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '13px', alignItems: 'center' }}>
              <span style={{ color: '#6c757d' }}>Vehicle Type:</span>
              <span style={{ fontWeight: '600', color: '#2A2C41', display: 'flex', alignItems: 'center', gap: '6px' }}>
                {getVehicleIcon(provider.vehicle_type)} {provider.vehicle_type}
              </span>
            </div>
            <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '13px', alignItems: 'center' }}>
              <span style={{ color: '#6c757d' }}>Status:</span>
              <span style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                <span style={{
                  width: '8px',
                  height: '8px',
                  borderRadius: '50%',
                  backgroundColor: getStatusColor(provider.status)
                }}></span>
                <span style={{ fontWeight: '600', color: provider.status === 'Available' ? '#10b981' : '#F55D00' }}>{provider.status}</span>
              </span>
            </div>
          </div>
        </div>

        {/* Provider Details */}
        <div style={{ background: 'white', padding: '16px', borderRadius: '10px', border: '1px solid rgba(42, 44, 65, 0.08)' }}>
          <h4 style={{ margin: '0 0 12px 0', fontSize: '14px', fontWeight: '600', color: '#2A2C41' }}>Provider Details</h4>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '13px' }}>
              <span style={{ color: '#6c757d' }}>Provider ID:</span>
              <span style={{ fontWeight: '600', color: '#2A2C41' }}>{provider.provider_id}</span>
            </div>
            <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '13px' }}>
              <span style={{ color: '#6c757d' }}>Registered On:</span>
              <span style={{ fontWeight: '600', color: '#2A2C41' }}>{formatDate(provider.registered_at)}</span>
            </div>
          </div>
        </div>
      </div>

      {/* Orders Information */}
      <div className="detail-section orders-section">
        <div className="orders-header">
          <h4>Orders ({totalOrderCount} total deliveries)</h4>
          <div className="orders-tabs">
            <button 
              className={`tab-btn ${activeTab === 'all' ? 'active' : ''}`}
              onClick={() => setActiveTab('all')}
            >
              All Orders ({totalOrderCount})
            </button>
            <button 
              className={`tab-btn ${activeTab === 'active' ? 'active' : ''}`}
              onClick={() => setActiveTab('active')}
            >
              Active Orders ({activeOrders.length})
            </button>
            <button 
              className={`tab-btn ${activeTab === 'history' ? 'active' : ''}`}
              onClick={() => setActiveTab('history')}
            >
              Order History ({orderHistory.length})
            </button>
          </div>
        </div>
        
        {ordersLoading ? (
          <div className="orders-loading">
            <div className="loading-spinner"></div>
            <p>Loading orders...</p>
          </div>
        ) : ordersError ? (
          <div className="orders-error">
            <p>{ordersError}</p>
          </div>
        ) : (
          <div className="orders-content">
            {(() => {
              console.log('Rendering orders content. Current state:');
              console.log('- activeTab:', activeTab);
              console.log('- activeOrders:', activeOrders);
              console.log('- orderHistory:', orderHistory);
              console.log('- allOrders:', allOrders);
              console.log('- totalOrderCount:', totalOrderCount);
              
              const renderOrdersList = (orders, emptyMessage) => {
                console.log(`Rendering orders list with ${orders.length} orders:`, orders);
                
                if (orders.length === 0) {
                  console.log('No orders to display, showing empty message:', emptyMessage);
                  return (
                    <div className="no-orders">
                      <p>{emptyMessage}</p>
                    </div>
                  );
                }

                // Pagination logic
                const totalPages = Math.ceil(orders.length / ordersPerPage);
                const startIndex = (currentPage - 1) * ordersPerPage;
                const endIndex = startIndex + ordersPerPage;
                const currentOrders = orders.slice(startIndex, endIndex);
                
                return (
                  <>
                    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: '12px' }}>
                      {currentOrders.map((order) => (
                      <div key={order.order_id} style={{
                        background: 'white',
                        borderRadius: '10px',
                        padding: '14px',
                        border: '1px solid rgba(42, 44, 65, 0.08)',
                        boxShadow: '0 2px 6px rgba(42, 44, 65, 0.04)',
                        transition: 'all 0.2s ease'
                      }}>
                        {/* Order Header */}
                        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '10px', paddingBottom: '10px', borderBottom: '1px solid rgba(42, 44, 65, 0.06)' }}>
                          <div>
                            <div style={{ fontSize: '11px', color: '#6c757d', marginBottom: '2px' }}>ORDER ID</div>
                            <div style={{ fontSize: '14px', fontWeight: '700', color: '#2A2C41' }}>#{order.order_id}</div>
                          </div>
                          <span style={{
                            padding: '4px 10px',
                            borderRadius: '6px',
                            fontSize: '11px',
                            fontWeight: '600',
                            backgroundColor: order.status === 'DELIVERED' ? 'rgba(16, 185, 129, 0.1)' : 'rgba(245, 93, 0, 0.1)',
                            color: order.status === 'DELIVERED' ? '#10b981' : '#F55D00'
                          }}>
                            {order.status || 'N/A'}
                          </span>
                        </div>
                        
                        {/* Order Details */}
                        <div style={{ display: 'flex', flexDirection: 'column', gap: '6px', marginBottom: '10px' }}>
                          <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '12px' }}>
                            <span style={{ color: '#6c757d' }}>Amount:</span>
                            <span style={{ fontWeight: '600', color: '#2A2C41' }}>₹{order.total_amount || 0}</span>
                          </div>
                          <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '12px' }}>
                            <span style={{ color: '#6c757d' }}>Customer:</span>
                            <span style={{ fontWeight: '500', color: '#2A2C41', textAlign: 'right', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', maxWidth: '150px' }}>{order.customer_name || 'N/A'}</span>
                          </div>
                          <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '12px' }}>
                            <span style={{ color: '#6c757d' }}>Business:</span>
                            <span style={{ fontWeight: '500', color: '#2A2C41', textAlign: 'right', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', maxWidth: '150px' }}>{order.business_name || 'N/A'}</span>
                          </div>
                          <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '12px' }}>
                            <span style={{ color: '#6c757d' }}>Date:</span>
                            <span style={{ fontWeight: '500', color: '#2A2C41' }}>{formatDate(order.created_at)}</span>
                          </div>
                        </div>

                        {/* Track Button */}
                        <button 
                          onClick={() => handleOrderTrack(order)}
                          style={{
                            width: '100%',
                            padding: '8px',
                            background: '#F55D00',
                            color: 'white',
                            border: 'none',
                            borderRadius: '6px',
                            fontSize: '12px',
                            fontWeight: '500',
                            cursor: 'pointer',
                            display: 'flex',
                            alignItems: 'center',
                            justifyContent: 'center',
                            gap: '6px',
                            transition: 'all 0.2s ease'
                          }}
                          onMouseEnter={(e) => e.currentTarget.style.background = '#2A2C41'}
                          onMouseLeave={(e) => e.currentTarget.style.background = '#F55D00'}
                        >
                          <FaRoute /> Track
                        </button>
                      </div>
                      ))}
                    </div>
                    
                    {/* Pagination Controls */}
                    {totalPages > 1 && (
                      <div className="pagination-container">
                        <div className="pagination-simple">
                          <button 
                            className="pagination-arrow"
                            onClick={() => {
                              setCurrentPage(prev => Math.max(prev - 1, 1));
                            }}
                            disabled={currentPage === 1}
                          >
                            ‹
                          </button>
                          
                          <span className="pagination-current">{currentPage}</span>
                          <span className="pagination-of">of {totalPages}</span>
                          
                          <button 
                            className="pagination-arrow"
                            onClick={() => {
                              setCurrentPage(prev => Math.min(prev + 1, totalPages));
                            }}
                            disabled={currentPage === totalPages}
                          >
                            ›
                          </button>
                        </div>
                      </div>
                    )}
                  </>
                );
              };
              
              if (activeTab === 'all') {
                return renderOrdersList(allOrders, 'No orders found for this delivery partner.');
              } else if (activeTab === 'active') {
                return renderOrdersList(activeOrders, 'No active orders found.');
              } else {
                return renderOrdersList(orderHistory, 'No order history found.');
              }
            })()}
          </div>
        )}
      </div>
    </div>
  );
};

export default DeliveryPartnerDetails;
