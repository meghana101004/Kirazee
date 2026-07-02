import axios from 'axios';
import { safeStorage } from '../utils/storageHelper';

// Configuration for the API
const API_CONFIG = {
  BASE_URL: 'https://kirazee.com/kirazee/consumer',
  DEFAULT_HEADERS: {
    'Content-Type': 'application/json',
  },
  DEFAULT_LOCATION: {
    LATITUDE: '13.559993795653225',
    LONGITUDE: '80.0230231690796',
    RADIUS: 5, // in kilometers
  },
  BUSINESS_TYPE_MAP: {
    'Restaurant': 'R02',
    'Grocery': 'R01',
    // Add other business types and their codes if known
  }
};

// Create an Axios instance
const api = axios.create({
  baseURL: API_CONFIG.BASE_URL,
  headers: API_CONFIG.DEFAULT_HEADERS,
  timeout: 10000, // Set a default timeout for requests (10 seconds)
});

// Request Interceptor: Add Authorization token
api.interceptors.request.use(
  (config) => {
    const token = safeStorage.getItem('authToken');
    if (token) {
      config.headers.Authorization = `Bearer ${token}`;
    }
    return config;
  },
  (error) => {
    // Do something with request error
    console.error('Request Interceptor Error:', error);
    return Promise.reject(error);
  }
);

// Response Interceptor: Handle global errors or common responses
api.interceptors.response.use(
  (response) => {
    // Any status code that lies in the range of 2xx causes this function to trigger
    return response;
  },
  (error) => {
    // Any status codes that falls outside the range of 2xx causes this function to trigger
    if (error.response) {
      // The request was made and the server responded with a status code
      // that falls out of the range of 2xx
      console.error('API Response Error Status:', error.response.status);
      console.error('API Response Error Data:', error.response.data);
      console.error('API Response Error Headers:', error.response.headers);

      // Example: Redirect to login if token is expired (401 Unauthorized)
      if (error.response.status === 401) {
        // safeStorage.removeItem('authToken');
        // window.location.href = '/login'; // Or dispatch an action in a state management system
        console.warn('Unauthorized request. User might need to log in again.');
      }
    } else if (error.request) {
      // The request was made but no response was received
      console.error('API Request Error: No response received', error.request);
    } else {
      // Something happened in setting up the request that triggered an Error
      console.error('API General Error:', error.message);
    }
    return Promise.reject(error);
  }
);

export default api;

export const storeApi = {
  /**
   * Fetches nearby businesses (stores) based on category and location.
   * @param {object} filters - Filtering options.
   * @param {string} [filters.lat] - Latitude for location. Defaults to API_CONFIG.DEFAULT_LOCATION.LATITUDE.
   * @param {string} [filters.lng] - Longitude for location. Defaults to API_CONFIG.DEFAULT_LOCATION.LONGITUDE.
   * @param {number} [filters.radius] - Search radius in kilometers. Defaults to API_CONFIG.DEFAULT_LOCATION.RADIUS.
   * @param {string} [filters.business_type] - Type of business to filter by (e.g., 'Restaurant', 'Grocery').
   * @returns {Promise<Array>} A promise that resolves to an array of business objects.
   */
  getStoresByCategory: async (filters = {}) => {
    const {
      lat = API_CONFIG.DEFAULT_LOCATION.LATITUDE,
      lng = API_CONFIG.DEFAULT_LOCATION.LONGITUDE,
      radius = API_CONFIG.DEFAULT_LOCATION.RADIUS,
      business_type,
      business_id,
    } = filters;

    try {
      // Using Axios params object for cleaner URL construction and proper encoding
      const params = { lat, lng, radius };
      if (business_type) {
        params.business_type = business_type;
      }
      if (business_id) {
        params.business_id = business_id;
      }

      console.log('Fetching nearby businesses with params:', params);
      const response = await api.get('/nearby-businesses', { params });
      console.log('Nearby businesses API raw response:', response.data);

      // Unified data extraction logic
      let businesses = [];
      if (Array.isArray(response.data)) {
        businesses = response.data;
      } else if (response.data && Array.isArray(response.data.results)) {
        businesses = response.data.results;
      } else if (response.data && Array.isArray(response.data.data)) {
        businesses = response.data.data;
      } else {
        console.warn('Unexpected response format for nearby businesses:', response.data);
      }
      return businesses;
    } catch (error) {
      console.error('Error in getStoresByCategory:', error);
      throw error; // Re-throw to allow calling component to handle
    }
  },

  /**
   * Fetches menu items or products for a specific business.
   * @param {string} businessId - The ID of the business.
   * @param {string} businessType - The type of business (e.g., 'Restaurant', 'Grocery').
   * @returns {Promise<object>} A promise that resolves to an object containing business and items.
   */
  /**
   * Fetches ALL menu items or products for a specific business by handling pagination automatically
   * @param {string} businessId - The ID of the business.
   * @param {string} businessType - The type of business (e.g., 'Restaurant', 'Grocery').
   * @returns {Promise<object>} A promise that resolves to an object containing all items.
   */
  /**
   * Fetches paginated menu items or products for a specific business
   * @param {string} businessId - The ID of the business
   * @param {string} businessType - The type of business (e.g., 'Restaurant', 'Grocery')
   * @param {number} page - The page number to fetch (1-based index)
   * @param {number} pageSize - Number of items per page
   * @returns {Promise<object>} Object containing items, business info, and pagination metadata
   */
  getItemsByBusiness: async (businessId, businessType, page = 1, pageSize = 10) => {
    if (!businessId) throw new Error('businessId is required');
    if (!businessType) throw new Error('businessType is required');

    const typeParam = API_CONFIG.BUSINESS_TYPE_MAP[businessType] || businessType;
    if (!typeParam) throw new Error(`Unknown businessType: ${businessType}`);

    try {
      console.log(`Fetching items for business ${businessId} (page ${page}, ${pageSize} items)`);
      
      const response = await api.post('/items', null, {
        params: {
          business_id: businessId,
          type: typeParam,
          page: Math.max(1, parseInt(page, 10)),
          page_size: Math.min(50, Math.max(1, parseInt(pageSize, 10))) // Cap at 50 items per page
        }
      });
      
      // For R01 (Grocery) stores
      if (typeParam === 'R01') {
        const items = Array.isArray(response.data?.items) ? response.data.items : [];
        const paginationData = {
          currentPage: response.data?.current_page || page,
          totalPages: response.data?.total_pages || Math.ceil((response.data?.total_items || items.length) / pageSize) || 1,
          totalItems: response.data?.total_items || items.length || 0,
          pageSize: response.data?.page_size || pageSize,
          hasNextPage: response.data?.has_next !== undefined 
            ? response.data.has_next 
            : (response.data?.current_page || page) < (response.data?.total_pages || 1)
        };
        
        return {
          business: response.data?.business || {},
          items,
          pagination: paginationData
        };
      } 
      // For R02 (Restaurant) and other types
      else {
        // Handle different response formats for R02
        let items = [];
        let totalItems = 0;
        
        // Handle different possible response structures
        if (response.data?.results?.items) {
          items = Array.isArray(response.data.results.items) ? response.data.results.items : [];
          totalItems = response.data.results.total || response.data.results.total_items || items.length;
        } else if (Array.isArray(response.data?.items)) {
          items = response.data.items;
          totalItems = response.data.total || response.data.total_items || items.length;
        } else if (Array.isArray(response.data)) {
          items = response.data;
          totalItems = items.length;
        } else if (response.data?.data) {
          // Handle case where data is nested under 'data' property
          items = Array.isArray(response.data.data) ? response.data.data : [];
          totalItems = response.data.total || response.data.total_items || items.length;
        }
        
        // Calculate pagination data for R02
        const paginationData = {
          currentPage: response.data?.current_page || response.data?.page || page,
          totalPages: response.data?.total_pages || Math.ceil(totalItems / pageSize) || 1,
          totalItems: totalItems,
          pageSize: response.data?.page_size || pageSize,
          hasNextPage: response.data?.has_next !== undefined 
            ? response.data.has_next 
            : (response.data?.current_page || page) < (response.data?.total_pages || 1)
        };
        
        console.log('R02 Pagination Data:', paginationData);
        
        return {
          business: response.data?.business || {},
          items,
          pagination: paginationData
        };
      }
    } catch (error) {
      console.error(`Error in getItemsByBusiness for business ${businessId}:`, error);
      throw error;
    }
  },

  /**
   * Searches for stores based on a query and optional filters.
   * @param {string} query - The search query string.
   * @param {object} [filters] - Additional filters for the search.
   * @returns {Promise<Array>} A promise that resolves to an array of matching stores.
   */
  searchStores: async (query, filters = {}) => {
    if (!query) {
      console.warn('searchStores called without a query.');
      return []; // Return empty array if no query
    }
    try {
      const response = await api.get('/stores/search', {
        params: {
          q: query,
          ...filters, // Spread any additional filters directly into params
        },
      });
      console.log('Search stores API response:', response.data);
      // Assuming search results are directly in response.data or response.data.results
      return response.data.results || response.data || [];
    } catch (error) {
      console.error(`Error in searchStores for query "${query}":`, error);
      throw error;
    }
  },

  // Example of how to add another API call:
  /**
   * Gets details for a specific store.
   * @param {string} storeId - The ID of the store.
   * @returns {Promise<object>} A promise that resolves to the store details object.
   */
  getStoreDetails: async (storeId) => {
    if (!storeId) {
      throw new Error('storeId is required for fetching store details.');
    }
    try {
      const response = await api.get(`/stores/${storeId}`);
      console.log(`Store details for ${storeId}:`, response.data);
      return response.data;
    } catch (error) {
      console.error(`Error fetching details for store ${storeId}:`, error);
      throw error;
    }
  },

  /**
   * Gets user addresses for delivery
   * @param {string} userId - The ID of the user
   * @returns {Promise<Array>} A promise that resolves to an array of user addresses
   */
  getUserAddresses: async (userId) => {
    if (!userId) {
      throw new Error('userId is required for fetching user addresses.');
    }
    try {
      const response = await axios.get(`https://kirazee.com/kirazee/user-addresses/?userID=${userId}`, {
        headers: {
          'Content-Type': 'application/json',
          'Accept': 'application/json'
        },
        timeout: 10000
      });
      
      console.log(`User addresses for ${userId}:`, response.data);
      
      if (response.data && response.data.user_address) {
        // Helper function to format address consistently
        const formatAddress = (addressData) => {
          if (!addressData) return '';
          
          const parts = [];
          const doorNo = addressData['Door no'] || addressData.doorNo || addressData.door_no || '';
          const street = addressData.street || addressData.streetAddress1 || '';
          const landmark = addressData.landmark || '';
          const city = addressData['city/town'] || addressData.city || '';
          const state = addressData.state || '';
          const pincode = addressData.pincode || addressData.zipCode || '';
          
          if (doorNo) parts.push(doorNo);
          if (street) parts.push(street);
          if (landmark) parts.push(`Near ${landmark}`);
          if (city) parts.push(city);
          if (state) parts.push(state);
          if (pincode) parts.push(pincode);
          
          return parts.filter(part => part.trim()).join(', ');
        };

        const addresses = response.data.user_address.map(addr => {
          // Parse the JSON string in the address field
          const addressData = typeof addr.address === 'string' ? JSON.parse(addr.address) : addr.address;
          
          // Build complete address using helper function
          const completeAddress = formatAddress(addressData);
          
          return {
            id: addr.id,
            fullName: 'User', // Not provided in API response
            phoneNumber: '', // Not provided in API response
            streetAddress1: addressData['Door no'] || '',
            streetAddress2: addressData.street || '',
            landmark: addressData.landmark || '',
            city: addressData['city/town'] || '',
            state: addressData.state || '',
            pincode: addressData.pincode || '',
            isDefault: addr.is_default === 1,
            addressType: addr.address_type,
            completeAddress: completeAddress
          };
        });
        
        return addresses;
      } else {
        return [];
      }
    } catch (error) {
      console.error(`Error fetching addresses for user ${userId}:`, error);
      throw error;
    }
  },

  /**
   * Saves a new address for the user
   * @param {string} userId - The ID of the user
   * @param {object} addressData - The address data to save
   * @returns {Promise<object>} A promise that resolves to the saved address response
   */
  saveUserAddress: async (userId, addressData) => {
    if (!userId) {
      throw new Error('userId is required for saving address.');
    }
    if (!addressData) {
      throw new Error('addressData is required for saving address.');
    }
    
    try {
      const addressPayload = {
        address_type: addressData.addressType || 'home',
        is_default: addressData.isDefault ? 1 : 0,
        ...(addressData.addressType === 'other' && { tag: addressData.tag || 'Custom label' }),
        address: {
          'Door no': addressData.streetAddress1 || '',
          street: addressData.streetAddress2 || '',
          'city/town': addressData.city || '',
          state: addressData.state || '',
          pincode: addressData.pincode || '',
          country: 'India',
          ...(addressData.latitude && { latitude: addressData.latitude }),
          ...(addressData.longitude && { longitude: addressData.longitude })
        }
      };

      const response = await axios.post(
        `https://kirazee.com/kirazee/address?userID=${userId}`,
        addressPayload,
        {
          headers: {
            'Content-Type': 'application/json',
            'Accept': 'application/json'
          },
          timeout: 10000
        }
      );

      console.log('Address saved successfully:', response.data);
      return response.data;
    } catch (error) {
      console.error(`Error saving address for user ${userId}:`, error);
      throw error;
    }
  },

  /**
   * Creates an order (delivery or pickup)
   * @param {object} orderData - The order payload as required by the API
   * @returns {Promise<object>} API response data
   */
  createOrder: async (orderData) => {
    if (!orderData) {
      throw new Error('orderData is required to create order.');
    }
    try {
      const response = await api.post('/orders/create/', orderData);
      return response.data;
    } catch (error) {
      console.error('Error creating order:', error);
      throw error;
    }
  },

  /**
   * Builds the hosted payment URL with dynamic query params
   * @param {object} params
   * @param {string|number} params.orderId - The order ID returned from create order API
   * @param {string|number} [params.userId] - The user ID (optional but requested)
   * @param {string} [params.businessId] - The business ID (optional but requested)
   * @param {string} [params.redirectUrl] - Optional URL to redirect back after payment (home page, orders page, etc.)
   * @returns {string} The payment URL
   */
  getPaymentUrl: ({ orderId, userId, businessId, redirectUrl }) => {
    const qs = new URLSearchParams();
    if (orderId !== undefined && orderId !== null) qs.set('order_id', orderId);
    if (userId !== undefined && userId !== null) qs.set('user_id', userId);
    if (businessId) qs.set('business_id', businessId);
    if (redirectUrl) {
      // Add multiple common aliases for compatibility with the hosted page
      qs.set('redirect_url', redirectUrl);
      qs.set('return_url', redirectUrl);
      qs.set('success_url', redirectUrl);
    }
    return `https://kirazee.com/kirazee/consumer/payment/?${qs.toString()}`;
  },

  /**
   * Fetches orders for a given user with optional status and pagination
   * @param {string|number} userId - The user ID
   * @param {object} [filters]
   * @param {string} [filters.status] - Order status filter (e.g., 'pending', 'confirmed', ...)
   * @param {number} [filters.page=1] - Page number
   * @returns {Promise<object>} The API response data
   */
  getUserOrders: async (userId, { status, page = 1 } = {}) => {
    if (!userId) throw new Error('userId is required to fetch user orders');
    try {
      const params = {};
      if (status) params.status = status;
      if (page) params.page = page;
      const response = await api.get(`/orders/user/${userId}/`, { params });
      return response.data;
    } catch (error) {
      console.error(`Error fetching orders for user ${userId}:`, error);
      throw error;
    }
  },

  /**
   * Fetch a single order's details
   * @param {string|number} orderId - The order ID
   * @param {string|number} userId - The user ID
   * @returns {Promise<object>} The API response data
   */
  getOrderDetails: async (orderId, userId) => {
    if (!orderId) throw new Error('orderId is required to fetch order details');
    if (!userId) throw new Error('userId is required to fetch order details');
    try {
      const response = await api.get(`/orders/${orderId}/`, { params: { user_id: userId } });
      return response.data;
    } catch (error) {
      console.error(`Error fetching order details for order ${orderId} and user ${userId}:`, error);
      throw error;
    }
  },

  /**
   * Fetch order timeline (progress line) for tracker
   * @param {string|number} orderId
   * @param {string|number} userId
   */
  getOrderTimeline: async (orderId, userId) => {
    if (!orderId) throw new Error('orderId is required to fetch order timeline');
    if (!userId) throw new Error('userId is required to fetch order timeline');
    try {
      // Backend expects POST, but also requires query parameters
      const response = await api.post(
        '/order-timeline/',
        {},
        { params: { order_id: orderId, user_id: userId } }
      );
      return response.data;
    } catch (error) {
      console.error(`Error fetching order timeline for order ${orderId} and user ${userId}:`, error);
      throw error;
    }
  },

  /**
   * Fetch categories for a specific business
   * @param {string} businessId - The business ID to fetch categories for
   * @returns {Promise<object>} The API response data containing categories
   */
  getBusinessCategories: async (businessId) => {
    if (!businessId) {
      throw new Error('businessId is required to fetch categories');
    }
    try {
      const response = await api.post('/fetch-categories', null, {
        params: { business_id: businessId }
      });
      
      console.log(`Categories for business ${businessId}:`, response.data);
      return response.data;
    } catch (error) {
      console.error(`Error fetching categories for business ${businessId}:`, error);
      throw error;
    }
  },

  /**
   * Fetch popular items based on business type
   * @param {string} businessType - The business type (e.g., 'R01' for Grocery, 'R02' for Restaurant)
   * @param {number} [limit=12] - Number of items to fetch (default: 12)
   * @returns {Promise<Array>} The API response data containing popular items
   */
  getPopularItems: async (businessType, limit = 12) => {
    if (!businessType) {
      throw new Error('businessType is required to fetch popular items');
    }
    try {
      const response = await api.get('/popular-items', {
        params: { 
          business_type: businessType,
          limit: limit
        }
      });
      
      console.log(`Popular items for business type ${businessType}:`, response.data);
      
      // Handle different response formats
      if (response.data && Array.isArray(response.data.popular_items)) {
        return response.data.popular_items;
      } else if (Array.isArray(response.data)) {
        return response.data;
      } else if (response.data && Array.isArray(response.data.items)) {
        return response.data.items;
      } else if (response.data && Array.isArray(response.data.data)) {
        return response.data.data;
      } else if (response.data && Array.isArray(response.data.results)) {
        return response.data.results;
      } else {
        console.warn('Unexpected response format for popular items:', response.data);
        return [];
      }
    } catch (error) {
      console.error(`Error fetching popular items for business type ${businessType}:`, error);
      throw error;
    }
  },

  /**
   * Fetches purchase logs for a business
   * @param {string} businessId - The business ID
   * @returns {Promise<object>} A promise that resolves to purchase logs data
   */
  getPurchaseLogs: async (businessId) => {
    if (!businessId) {
      throw new Error('businessId is required for fetching purchase logs.');
    }
    try {
      const response = await axios.get(`https://kirazee.com/kirazee/management/logs/purchases/?business_id=${businessId}`, {
        headers: {
          'Content-Type': 'application/json',
          'Accept': 'application/json'
        },
        timeout: 10000
      });
      
      console.log(`Purchase logs for business ${businessId}:`, response.data);
      return response.data;
    } catch (error) {
      console.error(`Error fetching purchase logs for business ${businessId}:`, error);
      throw error;
    }
  },

  /**
   * Fetches inventory data for a business
   * @param {string} businessId - The business ID
   * @param {object} filters - Optional filters for the inventory
   * @param {string} [filters.type] - Filter by inventory type
   * @param {string} [filters.search] - Search term for items
   * @returns {Promise<object>} A promise that resolves to inventory data
   */
  getInventory: async (businessId, filters = {}) => {
    if (!businessId) {
      throw new Error('businessId is required for fetching inventory.');
    }
    try {
      const params = new URLSearchParams({ business_id: businessId });
      if (filters.type) params.append('type', filters.type);
      if (filters.search) params.append('search', filters.search);

      const response = await axios.get(`https://kirazee.com/kirazee/management/inventory/?${params.toString()}`, {
        headers: {
          'Content-Type': 'application/json',
          'Accept': 'application/json'
        },
        timeout: 10000
      });
      
      console.log(`Inventory for business ${businessId}:`, response.data);
      return response.data;
    } catch (error) {
      console.error(`Error fetching inventory for business ${businessId}:`, error);
      throw error;
    }
  },

  /**
   * Fetches inventory logs for a business
   * @param {string} businessId - The business ID
   * @param {object} filters - Optional filters for the inventory logs
   * @param {string} [filters.inventory_id] - Filter by inventory ID
   * @param {string} [filters.sku] - Filter by SKU
   * @param {string} [filters.action] - Filter by action type
   * @returns {Promise<object>} A promise that resolves to inventory logs data
   */
  getInventoryLogs: async (businessId, filters = {}) => {
    if (!businessId) {
      throw new Error('businessId is required for fetching inventory logs.');
    }
    try {
      const params = new URLSearchParams({ business_id: businessId });
      if (filters.inventory_id) params.append('inventory_id', filters.inventory_id);
      if (filters.sku) params.append('sku', filters.sku);
      if (filters.action) params.append('action', filters.action);

      const response = await axios.get(`https://kirazee.com/kirazee/management/logs/inventory/?${params.toString()}`, {
        headers: {
          'Content-Type': 'application/json',
          'Accept': 'application/json'
        },
        timeout: 10000
      });
      
      console.log(`Inventory logs for business ${businessId}:`, response.data);
      return response.data;
    } catch (error) {
      console.error(`Error fetching inventory logs for business ${businessId}:`, error);
      throw error;
    }
  },
};