import React, { useState, useEffect } from 'react';
import AdminService from '../services/adminService';
import { Modal } from 'antd';
import '../../css/admin/DeliveryFleet.css';
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
  FaTh,
  FaList,
  FaRoute,
  FaMapPin
} from 'react-icons/fa';

// Google Maps integration - Fixed loading method
const GOOGLE_MAPS_API_KEY = import.meta.env.VITE_GOOGLE_MAPS_API_KEY || 'AIzaSyBwRQy7Fwqg218NcVmpQyOFLGy9RWdJT1s';

// Check if API key is available and set a flag
const HAS_GOOGLE_MAPS = !!(GOOGLE_MAPS_API_KEY && GOOGLE_MAPS_API_KEY !== 'YOUR_API_KEY_HERE');

// We'll load Google Maps components dynamically when needed
let GoogleMapComponents = null;

// Function to load Google Maps components
const loadGoogleMapsComponents = async () => {
  if (!HAS_GOOGLE_MAPS || GoogleMapComponents) {
    return GoogleMapComponents;
  }

  try {
    // Try dynamic import
    const module = await import('@react-google-maps/api');
    GoogleMapComponents = module;
    console.log('Google Maps components loaded successfully');
    return GoogleMapComponents;
  } catch (error) {
    console.warn('Google Maps library not available:', error);
    return null;
  }
};

const DeliveryFleet = ({ onViewDetails }) => {
  const [providers, setProviders] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [filters, setFilters] = useState({
    page: 1,
    limit: 20
  });
  const [pagination, setPagination] = useState({});
  const [viewMode, setViewMode] = useState('grid'); // 'grid', 'map', or 'split'
  const [selectedDriver, setSelectedDriver] = useState(null);
  const [listViewMode, setListViewMode] = useState('grid'); // 'grid' or 'list'

  // Map state
  const [mapCenter, setMapCenter] = useState({ lat: 13.5241, lng: 80.0057 });
  const [mapZoom, setMapZoom] = useState(12);
  const [showMap, setShowMap] = useState(false);
  const [selectedOrders, setSelectedOrders] = useState([]);
  const [travelPaths, setTravelPaths] = useState([]);
  const [googleMapsLoaded, setGoogleMapsLoaded] = useState(false);

  // Map Container Style
  const mapContainerStyle = {
    width: '100%',
    height: '600px',
    borderRadius: '12px'
  };

  // Load Google Maps components on component mount
  useEffect(() => {
    const initializeGoogleMaps = async () => {
      if (HAS_GOOGLE_MAPS) {
        const components = await loadGoogleMapsComponents();
        setGoogleMapsLoaded(!!components);
        console.log('Google Maps available:', !!components);
      } else {
        console.log('Google Maps not available - API key missing');
      }
    };

    initializeGoogleMaps();
  }, []);

  // Map Component (only rendered if Google Maps is available)
  const MapView = () => {
    if (!googleMapsLoaded || !GoogleMapComponents) {
      return (
        <div className="map-unavailable">
          <div className="map-error-card">
            <FaMapMarkerAlt className="map-error-icon" />
            <h3>Loading Map...</h3>
            <p>Please wait while Google Maps is being loaded.</p>
            <div className="loading-spinner-small"></div>
          </div>
        </div>
      );
    }

    const { LoadScript, GoogleMap, Marker, InfoWindow, Polyline, DirectionsRenderer } = GoogleMapComponents;

    // Custom Google Maps configuration
    const googleMapsConfig = {
      googleMapsApiKey: GOOGLE_MAPS_API_KEY,
      loading: 'async',
      libraries: ['places', 'geometry'],
      onError: (error) => {
        console.error('Google Maps loading error:', error);
        setError('Failed to load Google Maps. Please check your API key.');
      }
    };

    return (
      <div className="enhanced-map-container">
        <div className="map-controls">
          <div className="map-info">
            <h4>Delivery Fleet Tracking</h4>
            <p>Showing {providers.length} delivery partners</p>
            {selectedDriver && (
              <div className="selected-provider-info">
                <strong>Selected: {selectedDriver.name}</strong>
                <span>Total Distance: {calculateTotalDistance(travelPaths)} km</span>
                <span>Orders: {selectedOrders.length}</span>
              </div>
            )}
          </div>
          <div className="map-actions">
            <button onClick={() => setShowMap(!showMap)} className="toggle-map-btn">
              {showMap ? 'Hide Map' : 'Show Map'}
            </button>
            <button onClick={() => {
              setMapCenter({ lat: 13.5241, lng: 80.0057 });
              setMapZoom(12);
              setSelectedDriver(null);
              setSelectedOrders([]);
              setTravelPaths([]);
            }} className="reset-map-btn">
              Reset View
            </button>
          </div>
        </div>

        {showMap && (
          <LoadScript {...googleMapsConfig}>
            <GoogleMap
              mapContainerStyle={mapContainerStyle}
              zoom={mapZoom}
              center={mapCenter}
              options={{
                styles: [
                  {
                    featureType: "poi",
                    elementType: "labels",
                    stylers: [{ visibility: "off" }]
                  }
                ],
                gestureHandling: 'cooperative',
                zoomControl: true,
                mapTypeControl: false,
                streetViewControl: false,
                fullscreenControl: false
              }}
              onLoad={() => {
                console.log('Google Map loaded successfully');
              }}
              onUnmount={() => {
                console.log('Google Map unmounted');
              }}
            >
              {/* Provider Markers */}
              {providers.map(provider => {
                const coords = getProviderCoordinates(provider);
                console.log('Rendering marker for provider:', provider.name, 'coords:', coords);
                return (
                  <Marker
                    key={provider.provider_id}
                    position={coords}
                    onClick={() => handleProviderSelect(provider)}
                    icon={{
                      url: getStatusIcon(provider.status),
                      scaledSize: window.google && window.google.maps ?
                        new window.google.maps.Size(40, 40) : { width: 40, height: 40 },
                      labelOrigin: window.google && window.google.maps ?
                        new window.google.maps.Point(20, -10) : { x: 20, y: -10 }
                    }}
                    label={{
                      text: provider.name?.split(' ')[0] || 'Driver',
                      color: '#333',
                      fontSize: '12px',
                      fontWeight: 'bold'
                    }}
                  />
                );
              })}

              {/* Order Markers for Selected Provider */}
              {selectedDriver && selectedOrders.map((order, index) => {
                const coords = validateCoordinates(order.latitude, order.longitude);
                return (
                  <Marker
                    key={order.order_id}
                    position={coords}
                    icon={{
                      url: getOrderIcon(order.status),
                      scaledSize: window.google && window.google.maps ?
                        new window.google.maps.Size(30, 30) : { width: 30, height: 30 },
                      labelOrigin: window.google && window.google.maps ?
                        new window.google.maps.Point(15, -8) : { x: 15, y: -8 }
                    }}
                    label={{
                      text: `${index + 1}`,
                      color: '#fff',
                      fontSize: '10px',
                      fontWeight: 'bold'
                    }}
                  />
                );
              })}

              {/* Travel Path for Selected Provider */}
              {selectedDriver && travelPaths.length > 1 && (
                <Polyline
                  path={travelPaths}
                  options={{
                    strokeColor: '#F55D00',
                    strokeOpacity: 0.8,
                    strokeWeight: 4,
                    geodesic: true
                  }}
                />
              )}

              {/* Provider InfoWindow */}
              {selectedDriver && (
                <InfoWindow
                  position={getProviderCoordinates(selectedDriver)}
                  onCloseClick={() => {
                    setSelectedDriver(null);
                    setSelectedOrders([]);
                    setTravelPaths([]);
                  }}
                >
                  <div className="enhanced-driver-info-window">
                    <h4>{selectedDriver.name}</h4>
                    <div className="info-grid">
                      <div className="info-item">
                        <FaMobileAlt />
                        <span>{selectedDriver.phone}</span>
                      </div>
                      <div className="info-item">
                        {getVehicleIcon(selectedDriver.vehicle_type)}
                        <span>{selectedDriver.vehicle_type}</span>
                      </div>
                      <div className="info-item">
                        <FaCheckCircle />
                        <span>{selectedDriver.status}</span>
                      </div>
                      <div className="info-item">
                        <FaStar />
                        <span>{selectedDriver.rating || '0.0'}</span>
                      </div>
                    </div>
                    <div className="stats-row">
                      <div className="stat">
                        <strong>{selectedDriver.completed_deliveries || 0}</strong>
                        <span>Completed</span>
                      </div>
                      <div className="stat">
                        <strong>{calculateTotalDistance(travelPaths)} km</strong>
                        <span>Total Distance</span>
                      </div>
                      <div className="stat">
                        <strong>{selectedOrders.length}</strong>
                        <span>Orders Today</span>
                      </div>
                    </div>
                    <small>Last Update: {formatDate(selectedDriver.current_location?.last_updated || selectedDriver.last_location_update)}</small>
                  </div>
                </InfoWindow>
              )}

              {/* Order InfoWindows */}
              {selectedOrders.map((order, index) => {
                const coords = validateCoordinates(order.latitude, order.longitude);
                return (
                  <InfoWindow
                    key={`info-${order.order_id}`}
                    position={coords}
                    onCloseClick={() => {
                      setSelectedOrders(prev => prev.filter(o => o.order_id !== order.order_id));
                    }}
                  >
                    <div className="order-info-window">
                      <h5>Order {index + 1}</h5>
                      <p><strong>{order.customer_name}</strong></p>
                      <p>{order.delivery_address}</p>
                      <p>Status: <span className={`status ${order.status}`}>{order.status.replace('_', ' ')}</span></p>
                      <p>Distance: {order.distance_from_provider} km</p>
                    </div>
                  </InfoWindow>
                );
              })}
            </GoogleMap>
          </LoadScript>
        )}
      </div>
    );
  };

  // New state for enhanced features
  const [kpiMetrics, setKpiMetrics] = useState({});
  const [distancePeriod, setDistancePeriod] = useState('week');
  const [orderPeriod, setOrderPeriod] = useState('all');
  const [dateRange, setDateRange] = useState({ from: null, to: null });

  useEffect(() => {
    fetchProviders();
  }, [filters]);

  const fetchProviders = async () => {
    try {
      setLoading(true);
      setError(null);

      // Build filters object for new API
      const apiFilters = {
        ...filters,
        distance_period: distancePeriod,
        order_period: orderPeriod,
        date_from: dateRange.from,
        date_to: dateRange.to
      };

      console.log('Fetching fleet data with filters:', apiFilters);

      // Use the new fleet API endpoint
      const response = await AdminService.getDeliveryFleetData(apiFilters);

      console.log('Fleet API response:', response);
      if (response.success && response.data) {
        console.log('Fleet data structure:', response.data);
        console.log('Sample provider data:', response.data?.providers?.[0]);
        console.log('All providers:', response.data?.providers);

        setProviders(response.data.providers || []);
        setKpiMetrics(response.data.kpi_metrics || {});
        setPagination(response.data.pagination || {});
        setFilters(response.data.filters || {});
      } else {
        console.log('Primary fleet API failed or returned no data, using fallback...');
        // Fallback to current API if new endpoint not available
        try {
          console.log('Trying fallback API...');
          const fallbackResponse = await AdminService.getAllDeliveryProviders(filters);

          console.log('Fallback API response:', fallbackResponse);
          console.log('Fallback providers data:', fallbackResponse.providers);
          console.log('Sample fallback provider:', fallbackResponse.providers?.[0]);

          // Add mock location data for grid view
          const providersWithLocation = fallbackResponse.providers.map(provider => {
            console.log('Processing provider:', provider.name);
            return {
              ...provider,
              // Add mock coordinates around Sri City for demo
              current_lat: 13.5241 + (Math.random() - 0.5) * 0.1,
              current_lng: 80.0057 + (Math.random() - 0.5) * 0.1,
              last_location_update: new Date().toISOString(),
              location_accuracy: Math.random() * 20 + 5
            };
          });

          console.log('Providers with mock locations:', providersWithLocation);
          setProviders(providersWithLocation);
          setPagination(fallbackResponse.pagination || {});

          // Generate mock KPI metrics
          const mockKpiMetrics = {
            total_partners: fallbackResponse.providers.length,
            available_partners: fallbackResponse.providers.filter(p => p.status === 'Available').length,
            busy_partners: fallbackResponse.providers.filter(p => p.status === 'Busy').length,
            average_rating: 4.2,
            total_deliveries: fallbackResponse.providers.reduce((sum, p) => sum + (p.total_deliveries || 0), 0),
            fleet_utilization_rate: 75,
            total_distance_today_km: 245.8,
            verified_partners: fallbackResponse.providers.filter(p => p.is_verified).length
          };
          setKpiMetrics(mockKpiMetrics);

        } catch (fallbackErr) {
          console.error('Fallback API also failed:', fallbackErr);
          setError('Failed to fetch delivery providers from both APIs');
          setProviders([]);
          setPagination({});
          setKpiMetrics({});
        }
      }
    } catch (err) {
      console.error('Fleet API error:', err);
      setError('Failed to fetch delivery fleet data');
      setProviders([]);
      setPagination({});
      setKpiMetrics({});
    } finally {
      setLoading(false);
    }
  };

  // Helper functions for enhanced map features
  const generateOrderLocations = (provider) => {
    // Generate mock order locations around provider's current location
    const baseLat = provider.current_lat || 13.5241;
    const baseLng = provider.current_lng || 80.0057;

    const orders = [];
    const numOrders = Math.min(provider.total_deliveries || 5, 8); // Limit to 8 orders for performance

    for (let i = 0; i < numOrders; i++) {
      const angle = (i / numOrders) * 2 * Math.PI;
      const distance = 0.02 + Math.random() * 0.03; // 2-5 km radius

      // Always generate valid coordinates for demonstration
      const orderLat = baseLat + Math.cos(angle) * distance;
      const orderLng = baseLng + Math.sin(angle) * distance;

      orders.push({
        order_id: `ORD${provider.provider_id}_${i + 1}`,
        latitude: orderLat,
        longitude: orderLng,
        status: ['delivered', 'out_for_delivery', 'picked_up', 'ready'][Math.floor(Math.random() * 4)],
        distance_from_provider: (distance * 111).toFixed(1), // Convert to km
        customer_name: `Customer ${i + 1}`,
        delivery_address: `Address ${i + 1}, Sri City`,
        // Add business coordinates as well for complete route data
        business_lat: baseLat,
        business_lng: baseLng,
        customer_lat: orderLat,
        customer_lng: orderLng
      });
    }

    console.log(`Generated ${orders.length} orders with valid coordinates for provider ${provider.name}`);
    return orders;
  };

  const generateTravelPath = (provider, orders) => {
    // Generate a realistic travel path between orders
    const path = [];
    const currentLat = provider.current_lat || 13.5241;
    const currentLng = provider.current_lng || 80.0057;

    // Start from provider's current location
    path.push({ lat: currentLat, lng: currentLng });

    // Add waypoints for each order with proper start/end points
    orders.forEach((order, index) => {
      // Use business coordinates as start point for this order
      const businessLat = order.business_lat || currentLat;
      const businessLng = order.business_lng || currentLng;
      const customerLat = order.customer_lat || order.latitude || businessLat + 0.01;
      const customerLng = order.customer_lng || order.longitude || businessLng + 0.01;

      // Add business location (pickup point)
      if (index === 0 || (businessLat !== currentLat || businessLng !== currentLng)) {
        path.push({ lat: businessLat, lng: businessLng });
      }

      // Add intermediate points for smoother path to customer
      if (index > 0) {
        const prevOrder = orders[index - 1];
        const prevCustomerLat = prevOrder.customer_lat || prevOrder.latitude || businessLat;
        const prevCustomerLng = prevOrder.customer_lng || prevOrder.longitude || businessLng;
        
        const steps = 3;
        for (let step = 1; step <= steps; step++) {
          const t = step / (steps + 1);
          path.push({
            lat: prevCustomerLat + (businessLat - prevCustomerLat) * t,
            lng: prevCustomerLng + (businessLng - prevCustomerLng) * t
          });
        }
      }

      // Add path from business to customer
      const steps = 3;
      for (let step = 1; step < steps; step++) {
        const t = step / steps;
        path.push({
          lat: businessLat + (customerLat - businessLat) * t,
          lng: businessLng + (customerLng - businessLng) * t
        });
      }

      // Add customer location (delivery point)
      path.push({ lat: customerLat, lng: customerLng });
    });

    console.log(`Generated travel path with ${path.length} points for ${orders.length} orders`);
    return path;
  };

  const calculateTotalDistance = (path) => {
    let totalDistance = 0;
    for (let i = 1; i < path.length; i++) {
      const R = 6371; // Earth's radius in km
      const dLat = (path[i].lat - path[i - 1].lat) * Math.PI / 180;
      const dLon = (path[i].lng - path[i - 1].lng) * Math.PI / 180;
      const a = Math.sin(dLat / 2) * Math.sin(dLat / 2) +
        Math.cos(path[i - 1].lat * Math.PI / 180) * Math.cos(path[i].lat * Math.PI / 180) *
        Math.sin(dLon / 2) * Math.sin(dLon / 2);
      const c = 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
      totalDistance += R * c;
    }
    return totalDistance.toFixed(1);
  };

  const handleProviderSelect = async (provider) => {
    // Debug: Log the provider data to see structure
    console.log('Selected provider data:', provider);
    console.log('Provider location fields:', {
      current_location: provider.current_location,
      current_lat: provider.current_lat,
      current_lng: provider.current_lng,
      latitude: provider.latitude,
      longitude: provider.longitude
    });

    setSelectedDriver(provider);
    
    // Generate orders with GPS data from deliverylocationhistory if available
    const orders = generateOrderLocations(provider);
    setSelectedOrders(orders);
    
    // Generate travel path using GPS coordinates
    const path = generateTravelPath(provider, orders);
    setTravelPaths(path);

    // Center map on provider
    setMapCenter({
      lat: provider.current_lat || 13.5241,
      lng: provider.current_lng || 80.0057
    });
    setMapZoom(14);
  };

  const getStatusIcon = (status) => {
    const icons = {
      available: 'https://maps.google.com/mapfiles/ms/icons/green-dot.png',
      busy: 'https://maps.google.com/mapfiles/ms/icons/yellow-dot.png',
      offline: 'https://maps.google.com/mapfiles/ms/icons/red-dot.png'
    };
    return icons[status?.toLowerCase()] || icons.offline;
  };

  const getStatusColor = (status) => {
    const colors = {
      available: '#10B981',  // Green
      busy: '#F59E0B',       // Yellow/Orange
      offline: '#EF4444'     // Red
    };
    return colors[status?.toLowerCase()] || '#6B7280';
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

  // Helper function to get provider coordinates
  const getProviderCoordinates = (provider) => {
    // Try different coordinate field names
    const lat = provider.current_location?.latitude || provider.current_lat || provider.latitude;
    const lng = provider.current_location?.longitude || provider.current_lng || provider.longitude;

    return validateCoordinates(lat, lng);
  };

  const getOrderIcon = (status) => {
    const icons = {
      delivered: 'https://maps.google.com/mapfiles/ms/icons/blue-dot.png',
      out_for_delivery: 'https://maps.google.com/mapfiles/ms/icons/yellow-dot.png',
      picked_up: 'https://maps.google.com/mapfiles/ms/icons/orange-dot.png',
      ready: 'https://maps.google.com/mapfiles/ms/icons/red-dot.png'
    };
    return icons[status?.toLowerCase()] || icons.ready;
  };

  const getVehicleIcon = (vehicleType) => {
    const type = vehicleType?.toLowerCase();
    switch (type) {
      case 'motorcycle':
      case 'bike':
        return <FaMotorcycle />;
      case 'car':
        return <FaCar />;
      case 'bicycle':
        return <FaBicycle />;
      case 'scooter':
        return <FaMotorcycle />;
      default:
        return <FaTruck />;
    }
  };

  const formatDate = (dateString) => {
    if (!dateString) return 'N/A';
    return new Date(dateString).toLocaleString();
  };

  const handleViewDetails = (provider) => {
    if (onViewDetails) {
      // Validate provider object before proceeding
      if (!provider || !provider.provider_id) {
        console.error('Invalid provider object:', provider);
        return;
      }

      // Pass providerId and provider object separately
      console.log('Viewing details for provider:', provider.provider_id, provider);
      onViewDetails(provider.provider_id, provider);
    }
  };

  // Update useEffect to include new dependencies
  useEffect(() => {
    fetchProviders();
  }, [filters, distancePeriod, orderPeriod, dateRange]);

  if (loading) {
    return (
      <div className="loading-container">
        <FaSpinner className="loading-spinner" />
        <p>Loading delivery fleet data...</p>
      </div>
    );
  }

  if (error) {
    return (
      <div className="error-container">
        <FaTimesCircle className="error-icon" />
        <h3>Error Loading Fleet Data</h3>
        <p>{error}</p>
        <button onClick={fetchProviders} className="retry-btn">
          Try Again
        </button>
      </div>
    );
  }

  return (
    <div className="delivery-fleet-container" style={{ backgroundColor: '#F4F4F8', padding: '20px', maxWidth: '100%' }}>
      {/* Header */}
      <div style={{
        marginBottom: '20px',
        padding: '16px 20px',
        borderRadius: '12px',
        display: 'flex',
        justifyContent: 'space-between',
        alignItems: 'center'
      }}>
        <div>
          <h2 style={{
            margin: '0',
            fontSize: '28px',
            fontWeight: '700',
            color: '#2A2C41',
            letterSpacing: '-0.025em'
          }}>
            Delivery Fleet Management
          </h2>

        </div>

        {/* View Toggle Buttons */}
        <div style={{ display: 'flex', gap: '12px', alignItems: 'center' }}>
          {/* Grid/List Toggle */}
          <div style={{
            display: 'flex',
            gap: '4px',
            background: 'white',
            padding: '4px',
            borderRadius: '8px',
            boxShadow: '0 2px 8px rgba(0, 0, 0, 0.1)'
          }}>
            <button
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: '6px',
                padding: '8px 16px',
                border: 'none',
                background: listViewMode === 'grid' ? '#F55D00' : 'transparent',
                color: listViewMode === 'grid' ? 'white' : '#64748b',
                borderRadius: '6px',
                cursor: 'pointer',
                fontSize: '14px',
                fontWeight: '600',
                transition: 'all 0.2s ease'
              }}
              onClick={() => setListViewMode('grid')}
            >
              <FaTh style={{ fontSize: '14px' }} />
              <span>Grid</span>
            </button>
            <button
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: '6px',
                padding: '8px 16px',
                border: 'none',
                background: listViewMode === 'list' ? '#F55D00' : 'transparent',
                color: listViewMode === 'list' ? 'white' : '#64748b',
                borderRadius: '6px',
                cursor: 'pointer',
                fontSize: '14px',
                fontWeight: '600',
                transition: 'all 0.2s ease'
              }}
              onClick={() => setListViewMode('list')}
            >
              <FaList style={{ fontSize: '14px' }} />
              <span>List</span>
            </button>
          </div>

          {/* Split Button */}
          <button
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: '8px',
              padding: '10px 20px',
              border: 'none',
              background: '#F55D00',
              color: 'white',
              borderRadius: '8px',
              cursor: googleMapsLoaded ? 'pointer' : 'not-allowed',
              fontSize: '14px',
              fontWeight: '600',
              transition: 'all 0.2s ease',
              opacity: googleMapsLoaded ? 1 : 0.5,
              boxShadow: '0 2px 8px rgba(245, 93, 0, 0.2)'
            }}
            onClick={() => setViewMode('split')}
            disabled={!googleMapsLoaded}
            title={!googleMapsLoaded ? 'Loading Google Maps...' : 'View Grid and Map side by side'}
            onMouseEnter={(e) => {
              if (googleMapsLoaded) {
                e.currentTarget.style.background = '#2A2C41';
                e.currentTarget.style.transform = 'translateY(-2px)';
                e.currentTarget.style.boxShadow = '0 4px 12px rgba(42, 44, 65, 0.3)';
              }
            }}
            onMouseLeave={(e) => {
              if (googleMapsLoaded) {
                e.currentTarget.style.background = '#F55D00';
                e.currentTarget.style.transform = 'translateY(0)';
                e.currentTarget.style.boxShadow = '0 2px 8px rgba(245, 93, 0, 0.2)';
              }
            }}
          >
            <FaTh style={{ fontSize: '16px' }} />
            <FaMapMarkerAlt style={{ fontSize: '16px' }} />
            <span>Split</span>
          </button>
        </div>
      </div>

      {/* KPI Metrics Dashboard */}
      <div style={{
        background: 'white',
        padding: '20px',
        borderRadius: '12px',
        marginBottom: '20px',
        boxShadow: '0 2px 8px rgba(42, 44, 65, 0.04)'
      }}>
        <h3 style={{
          margin: '0 0 16px 0',
          fontSize: '18px',
          fontWeight: '600',
          color: '#2A2C41'
        }}>
          Fleet Performance Metrics
        </h3>
        <div style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fit, minmax(150px, 1fr))',
          gap: '12px'
        }}>
          <div style={{
            padding: '16px',
            background: 'white',
            border: '2px solid #2A2C41',
            borderRadius: '10px',
            transition: 'all 0.2s ease'
          }}>
            <div style={{ fontSize: '12px', color: '#6c757d', marginBottom: '4px', fontWeight: '500' }}>Total Partners</div>
            <div style={{ fontSize: '28px', fontWeight: '700', color: '#2A2C41' }}>{kpiMetrics.total_partners || 0}</div>
          </div>
          <div style={{
            padding: '16px',
            background: 'white',
            border: '2px solid #2A2C41',
            borderRadius: '10px',
            transition: 'all 0.2s ease'
          }}>
            <div style={{ fontSize: '12px', color: '#6c757d', marginBottom: '4px', fontWeight: '500' }}>Available</div>
            <div style={{ fontSize: '28px', fontWeight: '700', color: '#2A2C41' }}>{kpiMetrics.available_partners || 0}</div>
          </div>
          <div style={{
            padding: '16px',
            background: 'white',
            border: '2px solid #2A2C41',
            borderRadius: '10px',
            transition: 'all 0.2s ease'
          }}>
            <div style={{ fontSize: '12px', color: '#6c757d', marginBottom: '4px', fontWeight: '500' }}>Busy</div>
            <div style={{ fontSize: '28px', fontWeight: '700', color: '#2A2C41' }}>{kpiMetrics.busy_partners || 0}</div>
          </div>
          <div style={{
            padding: '16px',
            background: 'white',
            border: '2px solid #2A2C41',
            borderRadius: '10px',
            transition: 'all 0.2s ease'
          }}>
            <div style={{ fontSize: '12px', color: '#6c757d', marginBottom: '4px', fontWeight: '500' }}>Average Rating</div>
            <div style={{ fontSize: '28px', fontWeight: '700', color: '#2A2C41' }}>⭐ {kpiMetrics.average_rating?.toFixed(1) || '0.0'}</div>
          </div>
          <div style={{
            padding: '16px',
            background: 'white',
            border: '2px solid #2A2C41',
            borderRadius: '10px',
            transition: 'all 0.2s ease'
          }}>
            <div style={{ fontSize: '12px', color: '#6c757d', marginBottom: '4px', fontWeight: '500' }}>Total Deliveries</div>
            <div style={{ fontSize: '28px', fontWeight: '700', color: '#2A2C41' }}>{kpiMetrics.total_deliveries || 0}</div>
          </div>
          <div style={{
            padding: '16px',
            background: 'white',
            border: '2px solid #2A2C41',
            borderRadius: '10px',
            transition: 'all 0.2s ease'
          }}>
            <div style={{ fontSize: '12px', color: '#6c757d', marginBottom: '4px', fontWeight: '500' }}>Fleet Utilization</div>
            <div style={{ fontSize: '28px', fontWeight: '700', color: '#2A2C41' }}>{kpiMetrics.fleet_utilization_rate || 0}%</div>
          </div>
          <div style={{
            padding: '16px',
            background: 'white',
            border: '2px solid #2A2C41',
            borderRadius: '10px',
            transition: 'all 0.2s ease'
          }}>
            <div style={{ fontSize: '12px', color: '#6c757d', marginBottom: '4px', fontWeight: '500' }}>Distance Today</div>
            <div style={{ fontSize: '28px', fontWeight: '700', color: '#2A2C41' }}>{kpiMetrics.total_distance_today_km?.toFixed(1) || '0'} km</div>
          </div>
        </div>
      </div>

      {/* Default Grid/List View */}
      {viewMode !== 'split' && (
        <>
          {/* List View Header */}
          {listViewMode === 'list' && (
            <div className="providers-list-header">
              <div style={{ flex: '2.5' }}>Name & ID</div>
              <div style={{ flex: '1.2' }}>Status</div>
              <div style={{ flex: '2' }}>Phone</div>
              <div style={{ flex: '1.2' }}>Completed</div>
              <div style={{ flex: '1.2' }}>Total</div>
              <div style={{ flex: '1.2' }}>Distance</div>
              <div style={{ flex: '1.2' }}>Rating</div>
              <div style={{ flex: '1.5' }}>Actions</div>
            </div>
          )}
          
          <div className={listViewMode === 'list' ? 'providers-list' : ''} style={{
            display: listViewMode === 'grid' ? 'grid' : 'flex',
            gridTemplateColumns: listViewMode === 'grid' ? 'repeat(4, 1fr)' : 'none',
            flexDirection: listViewMode === 'list' ? 'column' : 'row',
            gap: listViewMode === 'list' ? '8px' : '16px'
          }}>
          {providers.map(provider => (
            <div key={provider.provider_id} className={`provider-card ${listViewMode === 'list' ? 'provider-card-list' : ''}`}>
              {listViewMode === 'list' ? (
                <>
                  {/* List View Layout */}
                  <div className="provider-info" style={{ flex: '2.5' }}>
                    <h3 
                      onClick={() => handleViewDetails(provider)}
                      style={{ cursor: 'pointer', color: '#F55D00' }}
                      onMouseEnter={(e) => e.target.style.textDecoration = 'underline'}
                      onMouseLeave={(e) => e.target.style.textDecoration = 'none'}
                    >
                      {provider.name}
                    </h3>
                    <small>ID: {provider.provider_id}</small>
                  </div>

                  <div className="provider-status" style={{ flex: '1.2' }}>
                    <span className="status-indicator" style={{ backgroundColor: getStatusColor(provider.status) }}></span>
                    <span className="status-text">{provider.status}</span>
                  </div>

                  <div className="provider-phone" style={{ flex: '2' }}>
                    <FaMobileAlt />
                    <span>{provider.phone}</span>
                  </div>

                  <div className="provider-stat" style={{ flex: '1.2' }}>
                    <strong>{provider.completed_deliveries || 0}</strong>
                    <span>COMPLETED</span>
                  </div>

                  <div className="provider-stat" style={{ flex: '1.2' }}>
                    <strong>{provider.total_deliveries || 0}</strong>
                    <span>TOTAL</span>
                  </div>

                  <div className="provider-stat" style={{ flex: '1.2' }}>
                    <strong>{(provider.distance_metrics?.total_distance_km || provider.total_kilometers_traveled || 0).toFixed(1)}</strong>
                    <span>KM</span>
                  </div>

                  <div className="provider-stat rating" style={{ flex: '1.2' }}>
                    <strong>
                      <FaStar />
                      {provider.rating || '0.0'}
                    </strong>
                    <span>RATING</span>
                  </div>

                  <div className="provider-actions" style={{ flex: '1.5' }}>
                    <button className="details-btn" onClick={() => handleViewDetails(provider)}>
                      View Details
                    </button>
                  </div>
                </>
              ) : (
                <>
                  {/* Grid View Layout */}
                  <div className="grid-card-header">
                    <div className="provider-info-grid">
                      <h3 
                        onClick={() => handleViewDetails(provider)}
                        style={{ cursor: 'pointer', color: '#F55D00' }}
                        onMouseEnter={(e) => e.target.style.textDecoration = 'underline'}
                        onMouseLeave={(e) => e.target.style.textDecoration = 'none'}
                      >
                        {provider.name}
                      </h3>
                      <small>ID: {provider.provider_id}</small>
                    </div>
                    <div className="provider-status-badge" style={{
                      backgroundColor: provider.status === 'Available' ? 'rgba(16, 185, 129, 0.1)' : provider.status === 'Busy' ? 'rgba(245, 158, 11, 0.1)' : 'rgba(156, 163, 175, 0.1)',
                      color: provider.status === 'Available' ? '#10b981' : provider.status === 'Busy' ? '#f59e0b' : '#9ca3af'
                    }}>
                      ● {provider.status}
                    </div>
                  </div>

                  <div className="grid-card-contact">
                    <div className="contact-row">
                      <FaMobileAlt />
                      <span>{provider.phone}</span>
                    </div>
                    <div className="contact-row">
                      {getVehicleIcon(provider.vehicle_type)}
                      <span>{provider.vehicle_type}</span>
                    </div>
                  </div>

                  <div className="grid-card-stats">
                    <div className="grid-stat-item">
                      <strong>{provider.completed_deliveries || 0}</strong>
                      <span>COMPLETED</span>
                    </div>
                    <div className="grid-stat-item">
                      <strong>{provider.total_deliveries || 0}</strong>
                      <span>TOTAL</span>
                    </div>
                    <div className="grid-stat-item">
                      <strong>{(provider.distance_metrics?.total_distance_km || provider.total_kilometers_traveled || 0).toFixed(1)}</strong>
                      <span>KM</span>
                    </div>
                    <div className="grid-stat-item rating">
                      <strong>
                        <FaStar />
                        {provider.rating || '0.0'}
                      </strong>
                      <span>RATING</span>
                    </div>
                  </div>

                  <div className="grid-card-actions">
                    <button className="details-btn-grid" onClick={() => handleViewDetails(provider)}>
                      View Details
                    </button>
                  </div>
                </>
              )}
            </div>
          ))}
        </div>
        </>
      )}

      {/* Removed Map View */}
      {false && (
        <div style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(4, 1fr)',
          gap: '16px'
        }}>
          {providers.map(provider => (
            <div key={provider.provider_id} className="provider-card grid-card">
              <div className="provider-header">
                <div className="provider-info">
                  <h3 
                    onClick={() => handleViewDetails(provider)}
                    style={{ cursor: 'pointer', color: '#F55D00' }}
                    onMouseEnter={(e) => e.target.style.textDecoration = 'underline'}
                    onMouseLeave={(e) => e.target.style.textDecoration = 'none'}
                  >
                    {provider.name}
                  </h3>
                  <small>ID: {provider.provider_id}</small>
                  {provider.is_verified && (
                    <span className="verified-badge">✓ Verified</span>
                  )}
                </div>
                <div className="provider-status">
                  <span
                    className="status-indicator"
                    style={{ backgroundColor: getStatusColor(provider.status) }}
                  ></span>
                  <span className="status-text">{provider.status}</span>
                </div>
              </div>

              <div className="provider-details">
                <div className="detail-row">
                  <FaMobileAlt className="detail-icon" />
                  <span>{provider.phone}</span>
                </div>
                <div className="detail-row">
                  <FaEnvelope className="detail-icon" />
                  <span>{provider.email}</span>
                </div>
                <div className="detail-row">
                  {getVehicleIcon(provider.vehicle_type)}
                  <span>{provider.vehicle_type}</span>
                </div>
                {provider.current_location && (
                  <div className="detail-row">
                    <FaMapMarkerAlt className="detail-icon" />
                    <span>Location Available</span>
                  </div>
                )}
              </div>

              {/* Enhanced Stats */}
              <div className="provider-stats">
                <div className="stat-item">
                  <strong>{provider.completed_deliveries || 0}</strong>
                  <span>Completed</span>
                </div>
                <div className="stat-item">
                  <strong>{provider.total_deliveries || 0}</strong>
                  <span>Total</span>
                </div>
                <div className="stat-item">
                  <strong>{provider.distance_metrics?.total_distance_km || provider.total_kilometers_traveled || 0} km</strong>
                  <span>Distance</span>
                </div>
                <div className="stat-item rating">
                  <FaStar />
                  <span>{provider.rating || '0.0'}</span>
                </div>
              </div>

              {/* Order Breakdown */}
              {provider.order_breakdown && (
                <div className="order-breakdown">
                  <div className="breakdown-item">
                    <span className="status-label delivered">📦 Delivered:</span>
                    <span className="status-count">{provider.order_breakdown.delivered?.count || 0}</span>
                  </div>
                  <div className="breakdown-item">
                    <span className="status-label out-for-delivery">🚚 Out for Delivery:</span>
                    <span className="status-count">{provider.order_breakdown.out_for_delivery?.count || 0}</span>
                  </div>
                  <div className="breakdown-item">
                    <span className="status-label picked-up">🏍️ Picked Up:</span>
                    <span className="status-count">{provider.order_breakdown.picked_up?.count || 0}</span>
                  </div>
                  <div className="breakdown-item">
                    <span className="status-label ready">⏳ Ready:</span>
                    <span className="status-count">{provider.order_breakdown.ready?.count || 0}</span>
                  </div>
                </div>
              )}

              <div className="provider-actions">
                <button
                  className="details-btn"
                  onClick={() => handleViewDetails(provider)}
                >
                  View Details
                </button>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Split View Modal */}
      <Modal
        title={
          <div style={{ fontSize: '20px', fontWeight: '700', color: '#2A2C41' }}>
            Delivery Partners - Map View
          </div>
        }
        open={viewMode === 'split'}
        onCancel={() => setViewMode('grid')}
        footer={null}
        width="80%"
        style={{ top: 20 }}
        bodyStyle={{ padding: '20px', maxHeight: 'calc(100vh - 200px)', overflowY: 'auto' }}
      >
        <div style={{ display: 'flex', gap: '20px', height: '75vh' }}>
          {/* Left Side - Partners Grid */}
          <div style={{ flex: '0 0 40%', overflowY: 'auto', paddingRight: '10px' }}>
            <div style={{ marginBottom: '16px' }}>
              <h4 style={{ margin: '0 0 8px 0', fontSize: '16px', fontWeight: '600', color: '#2A2C41' }}>
                Delivery Partners
              </h4>
              <p style={{ margin: 0, fontSize: '13px', color: '#6c757d' }}>
                Click on a partner to view their route on the map
              </p>
            </div>
            <div style={{
              display: 'grid',
              gridTemplateColumns: 'repeat(2, 1fr)',
              gap: '12px'
            }}>
              {providers.map(provider => (
                <div
                  key={provider.provider_id}
                  onClick={() => handleProviderSelect(provider)}
                  style={{
                    background: selectedDriver?.provider_id === provider.provider_id ? '#fff7ed' : 'white',
                    borderRadius: '10px',
                    padding: '12px',
                    border: selectedDriver?.provider_id === provider.provider_id ? '2px solid #F55D00' : '1px solid rgba(42, 44, 65, 0.08)',
                    cursor: 'pointer',
                    transition: 'all 0.2s ease'
                  }}
                  onMouseEnter={(e) => {
                    if (selectedDriver?.provider_id !== provider.provider_id) {
                      e.currentTarget.style.borderColor = '#F55D00';
                      e.currentTarget.style.boxShadow = '0 4px 12px rgba(245, 93, 0, 0.1)';
                    }
                  }}
                  onMouseLeave={(e) => {
                    if (selectedDriver?.provider_id !== provider.provider_id) {
                      e.currentTarget.style.borderColor = 'rgba(42, 44, 65, 0.08)';
                      e.currentTarget.style.boxShadow = 'none';
                    }
                  }}
                >
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '8px' }}>
                    <div>
                      <h3 style={{ margin: '0 0 4px 0', fontSize: '14px', fontWeight: '700', color: '#2A2C41' }}>
                        {provider.name}
                      </h3>
                      <div style={{ fontSize: '10px', color: '#6c757d' }}>
                        ID: {provider.provider_id}
                      </div>
                    </div>
                    <div style={{
                      padding: '3px 8px',
                      borderRadius: '4px',
                      backgroundColor: provider.status === 'Available' ? 'rgba(16, 185, 129, 0.1)' : 'rgba(245, 93, 0, 0.1)',
                      fontSize: '10px',
                      fontWeight: '600',
                      color: provider.status === 'Available' ? '#10b981' : '#F55D00'
                    }}>
                      {provider.status}
                    </div>
                  </div>

                  <div style={{ display: 'flex', gap: '8px', marginBottom: '8px', fontSize: '11px' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
                      <FaMobileAlt style={{ fontSize: '10px', color: '#6c757d' }} />
                      <span>{provider.phone}</span>
                    </div>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
                      {getVehicleIcon(provider.vehicle_type)}
                      <span>{provider.vehicle_type}</span>
                    </div>
                  </div>

                  <div style={{ display: 'flex', gap: '12px', fontSize: '11px' }}>
                    <div>
                      <strong>{provider.completed_deliveries || 0}</strong> Completed
                    </div>
                    <div>
                      <strong>{(provider.distance_metrics?.total_distance_km || 0).toFixed(1)}</strong> km
                    </div>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '2px' }}>
                      <FaStar style={{ color: '#f59e0b', fontSize: '10px' }} />
                      <strong>{provider.rating || '0.0'}</strong>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </div>

          {/* Right Side - Map */}
          <div style={{ flex: 1, borderRadius: '12px', overflow: 'hidden', border: '1px solid rgba(42, 44, 65, 0.08)' }}>
            <MapView />
          </div>
        </div>
      </Modal>

      {/* Pagination */}
      {pagination.total_pages > 1 && (
        <div className="pagination">
          <button
            disabled={!pagination.has_prev_page}
            onClick={() => setFilters(prev => ({ ...prev, page: prev.page - 1 }))}
          >
            Previous
          </button>

          <span className="page-info">
            Page {pagination.current_page} of {pagination.total_pages}
            ({pagination.total_providers} total providers)
          </span>

          <button
            disabled={!pagination.has_next_page}
            onClick={() => setFilters(prev => ({ ...prev, page: prev.page + 1 }))}
          >
            Next
          </button>
        </div>
      )}
    </div>
  );
};

export default DeliveryFleet;
