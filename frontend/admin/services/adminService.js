import { API_ENDPOINTS } from '../utils/config';

// Database configuration
export const DB_CONFIG = {
  host: 'localhost',
  port: 3306,
  database: 'kirazee',
  username: 'root',
  password: 'Meghana@10'
};

export class AdminService {
  // Base admin API URL - Updated to use local backend (removed trailing slash)
  static get ADMIN_BASE_URL() {
    return `https://kirazee.com/kirazee/api/v1/admin`;
  }

  static get DELIVERY_ADMIN_BASE_URL() {
    return `https://kirazee.com/kirazee/delivery-partner/api/v1/admin`;
  }

  // Database connection method for role-based dashboards
  static async getRoleBasedData(role) {
    try {
      // Use existing dashboard endpoints with cache-busting
      const timestamp = new Date().getTime();
      const response = await fetch(`${this.ADMIN_BASE_URL}/dashboard/latest/?t=${timestamp}`, {
        method: 'GET',
        headers: {
          'Content-Type': 'application/json',
          'Cache-Control': 'no-cache'
        }
      });
      
      if (!response.ok) {
        // If dashboard/latest doesn't exist, try dashboard/summary
        try {
          const summaryResponse = await fetch(`${this.ADMIN_BASE_URL}/dashboard/summary/?t=${timestamp}`, {
            method: 'GET',
            headers: {
              'Content-Type': 'application/json',
              'Cache-Control': 'no-cache'
            }
          });
          
          if (summaryResponse.ok) {
            const summaryData = await summaryResponse.json();
            return this.transformDataForRole(summaryData, role);
          }
        } catch (summaryError) {
          console.warn('Dashboard summary also failed:', summaryError);
        }
        
        // If both fail, return mock data
        console.warn(`Dashboard API not available, using mock data for ${role}`);
        return this.getMockDataForRole(role);
      }
      
      const data = await response.json();
      
      // Transform data based on role for different views
      return this.transformDataForRole(data, role);
    } catch (error) {
      console.error(`Error fetching ${role} dashboard data:`, error);
      // Return mock data instead of throwing error
      return this.getMockDataForRole(role);
    }
  }

  // Transform general dashboard data for specific roles
  static transformDataForRole(data, role) {
    const transformed = {};
    
    switch (role) {
      case 'Manager':
        transformed.businessMetrics = {
          totalBusinesses: data.data?.businesses?.total_businesses || 0,
          activeBusinesses: data.data?.businesses?.active_businesses || 0,
          pendingApproval: (data.data?.businesses?.total_businesses || 0) - (data.data?.businesses?.active_businesses || 0),
          totalRevenue: data.data?.revenue?.total_revenue || 0,
          monthlyGrowth: data.data?.businesses?.monthly_growth || 0
        };
        transformed.orderMetrics = {
          totalOrders: data.data?.orders?.total_orders || 0,
          completedOrders: data.data?.orders?.completed_orders || 0,
          pendingOrders: data.data?.orders?.active_orders || 0,
          averageOrderValue: data.data?.orders?.average_order_value || 0
        };
        transformed.deliveryMetrics = {
          activePartners: data.data?.delivery?.available_drivers || 0,
          averageRating: data.data?.delivery?.average_rating || 0,
          totalDeliveries: data.data?.delivery?.total_deliveries || 0
        };
        break;
        
      case 'Support Team':
        transformed.supportTickets = {
          total: data.data?.support_tickets?.total || 0,
          open: data.data?.support_tickets?.open || 0,
          inProgress: data.data?.support_tickets?.in_progress || 0,
          resolved: data.data?.support_tickets?.resolved || 0,
          averageResolutionTime: data.data?.support_tickets?.avg_resolution_time || 'N/A'
        };
        transformed.customerIssues = {
          total: data.data?.customer_issues?.total || 0,
          orderRelated: data.data?.customer_issues?.order_related || 0,
          paymentRelated: data.data?.customer_issues?.payment_related || 0,
          deliveryRelated: data.data?.customer_issues?.delivery_related || 0
        };
        break;
        
      case 'KYC Associates':
        transformed.kycMetrics = {
          totalBusinesses: data.data?.businesses?.total_businesses || 0,
          verifiedBusinesses: data.data?.businesses?.verified_businesses || 0,
          pendingVerification: data.data?.businesses?.pending_verification || 0,
          rejectedApplications: data.data?.businesses?.rejected_applications || 0
        };
        transformed.deliveryPartners = {
          totalPartners: data.data?.delivery_partners?.total || 0,
          verifiedPartners: data.data?.delivery_partners?.verified || 0,
          pendingVerification: data.data?.delivery_partners?.pending || 0,
          averageVerificationTime: data.data?.delivery_partners?.avg_verification_time || 'N/A'
        };
        break;
        
      case 'CA/Finance':
        transformed.financialMetrics = {
          totalRevenue: data.data?.revenue?.total_revenue || 0,
          monthlyRevenue: data.data?.revenue?.monthly_revenue || 0,
          totalExpenses: data.data?.expenses?.total || 0,
          netProfit: data.data?.revenue?.net_profit || 0,
          profitMargin: data.data?.revenue?.profit_margin || 0
        };
        transformed.paymentMetrics = {
          totalTransactions: data.data?.payments?.total_transactions || 0,
          successfulPayments: data.data?.payments?.successful || 0,
          failedPayments: data.data?.payments?.failed || 0,
          averageTransactionValue: data.data?.payments?.average_value || 0
        };
        break;
        
      default:
        return data.data || {};
    }
    
    return transformed;
  }

  // Mock data for when API is not available
  static getMockDataForRole(role) {
    switch (role) {
      case 'Manager':
        return {
          businessMetrics: {
            totalBusinesses: 150,
            activeBusinesses: 120,
            pendingApproval: 30,
            totalRevenue: 2500000,
            monthlyGrowth: 15
          },
          orderMetrics: {
            totalOrders: 5000,
            completedOrders: 4500,
            pendingOrders: 500,
            averageOrderValue: 450
          },
          deliveryMetrics: {
            activePartners: 85,
            averageRating: 4.2,
            totalDeliveries: 4500
          }
        };
        
      case 'Support Team':
        return {
          supportTickets: {
            total: 250,
            open: 45,
            inProgress: 30,
            resolved: 175,
            averageResolutionTime: '2.5 hours'
          },
          customerIssues: {
            total: 180,
            orderRelated: 80,
            paymentRelated: 50,
            deliveryRelated: 50
          }
        };
        
      case 'KYC Associates':
        return {
          kycMetrics: {
            totalBusinesses: 150,
            verifiedBusinesses: 120,
            pendingVerification: 25,
            rejectedApplications: 5
          },
          deliveryPartners: {
            totalPartners: 100,
            verifiedPartners: 85,
            pendingVerification: 12,
            averageVerificationTime: '24 hours'
          }
        };
        
      case 'CA/Finance':
        return {
          financialMetrics: {
            totalRevenue: 2500000,
            monthlyRevenue: 350000,
            totalExpenses: 1800000,
            netProfit: 700000,
            profitMargin: 28
          },
          paymentMetrics: {
            totalTransactions: 5000,
            successfulPayments: 4750,
            failedPayments: 250,
            averageTransactionValue: 500
          }
        };
        
      default:
        return {
          totalBusinesses: 150,
          activeBusinesses: 120,
          totalOrders: 5000,
          totalRevenue: 2500000
        };
    }
  }

  // ===== DELIVERY FLEET MANAGEMENT =====
  
  // Get comprehensive delivery fleet data
  static async getDeliveryFleetData(params = {}) {
    try {
      const queryParams = new URLSearchParams();
      
      // Add pagination
      if (params.page) queryParams.append('page', params.page);
      if (params.limit) queryParams.append('limit', params.limit);
      
      // Add filters
      if (params.distance_period) queryParams.append('distance_period', params.distance_period);
      if (params.order_period) queryParams.append('order_period', params.order_period);
      if (params.date_from) queryParams.append('date_from', params.date_from);
      if (params.date_to) queryParams.append('date_to', params.date_to);
      if (params.status) queryParams.append('status', params.status);
      if (params.vehicle_type) queryParams.append('vehicle_type', params.vehicle_type);
      
      const queryString = queryParams.toString();
      const endpoint = `delivery-fleet/${queryString ? `?${queryString}` : ''}`;
      
      const response = await this.adminApiCall(endpoint);
      
      if (!response) {
        console.error('Empty response from fleet API');
        return { success: false, message: 'Empty response from server' };
      }
      
      return response;
    } catch (error) {
      console.error('Error in getDeliveryFleetData:', error);
      return { 
        success: false, 
        message: error.message || 'Failed to fetch delivery fleet data',
        providers: [],
        pagination: {
          total_providers: 0,
          current_page: 1,
          per_page: 20,
          total_pages: 0
        },
        kpi_metrics: {}
      };
    }
  }

  // Get detailed delivery partner information
  static async getDeliveryFleetDetails(providerId, params = {}) {
    try {
      const queryParams = new URLSearchParams();
      
      // Add filters for details
      if (params.include_orders) queryParams.append('include_orders', params.include_orders);
      if (params.include_location) queryParams.append('include_location', params.include_location);
      if (params.include_performance) queryParams.append('include_performance', params.include_performance);
      
      const queryString = queryParams.toString();
      const endpoint = `delivery-fleet/${providerId}/${queryString ? `?${queryString}` : ''}`;
      
      const response = await this.adminApiCall(endpoint);
      
      if (!response) {
        console.error('Empty response from fleet details API');
        return { success: false, message: 'Empty response from server' };
      }
      
      return response;
    } catch (error) {
      console.error('Error in getDeliveryFleetDetails:', error);
      return { 
        success: false, 
        message: error.message || 'Failed to fetch delivery partner details'
      };
    }
  }

  // Helper method for admin API calls
  static async adminApiCall(endpoint, options = {}) {
    try {
      const defaultHeaders = {
        'Content-Type': 'application/json'
      };

      // Ensure endpoint starts with / for proper URL construction
      const cleanEndpoint = endpoint.startsWith('/') ? endpoint : `/${endpoint}`;
      const url = `${this.ADMIN_BASE_URL}${cleanEndpoint}`;

      const response = await fetch(url, {
        ...options,
        headers: {
          ...defaultHeaders,
          ...options.headers
        }
      });

      if (!response.ok) {
        let rawText = '';
        let jsonData = null;
        try { rawText = await response.text(); } catch (_) {}
        try { jsonData = rawText ? JSON.parse(rawText) : await response.json(); } catch (_) {}
        const msg = (jsonData && (jsonData.message || jsonData.detail)) || rawText || `HTTP error! status: ${response.status}`;
        const err = new Error(msg);
        if (jsonData) err.details = jsonData;
        throw err;
      }

      const data = await response.json();
      return data;
    } catch (error) {
      console.error('Admin API call failed:', error);
      throw error;
    }
  }

  static async deliveryAdminApiCall(endpoint, options = {}) {
    try {
      const defaultHeaders = {
        'Content-Type': 'application/json'
      };

      // Ensure endpoint starts with / for proper URL construction
      const cleanEndpoint = endpoint.startsWith('/') ? endpoint : `/${endpoint}`;
      const url = `${this.DELIVERY_ADMIN_BASE_URL}${cleanEndpoint}`;

      const response = await fetch(url, {
        ...options,
        headers: {
          ...defaultHeaders,
          ...options.headers
        }
      });

      if (!response.ok) {
        let rawText = '';
        let jsonData = null;
        try { rawText = await response.text(); } catch (_) {}
        try { jsonData = rawText ? JSON.parse(rawText) : await response.json(); } catch (_) {}
        const msg = (jsonData && (jsonData.message || jsonData.detail)) || rawText || `HTTP error! status: ${response.status}`;
        const err = new Error(msg);
        if (jsonData) err.details = jsonData;
        throw err;
      }

      const data = await response.json();
      return data;
    } catch (error) {
      console.error('Delivery Admin API call failed:', error);
      throw error;
    }
  }

  // ===== BUSINESS MANAGEMENT SERVICE =====

  // List all businesses with pagination and filtering (Simple)
  // Get businesses with simple data structure
  static async getBusinessesSimple(params = {}) {
    const queryParams = new URLSearchParams();
    
    if (params.page) queryParams.append('page', params.page);
    if (params.limit) queryParams.append('limit', params.limit);
    if (params.status) queryParams.append('status', params.status);
    if (params.business_type) queryParams.append('business_type', params.business_type);
    if (params.search) queryParams.append('search', params.search);

    const queryString = queryParams.toString();
    const endpoint = `businesses-simple${queryString ? `?${queryString}` : ''}`;
    
    return this.adminApiCall(endpoint);
  }

  static async getAllBusinesses(params = {}) {
    const queryParams = new URLSearchParams();
    
    if (params.page) queryParams.append('page', params.page);
    if (params.limit) queryParams.append('limit', params.limit);
    if (params.status) queryParams.append('status', params.status);
    if (params.business_type) queryParams.append('business_type', params.business_type);
    if (params.search) queryParams.append('search', params.search);

    const queryString = queryParams.toString();
    const endpoint = `businesses-simple${queryString ? `?${queryString}` : ''}`;
    
    return this.adminApiCall(endpoint);
  }

  // Get comprehensive business data
  static async getBusinessesComprehensive(params = {}) {
    const queryParams = new URLSearchParams();
    
    if (params.page) queryParams.append('page', params.page);
    if (params.limit) queryParams.append('limit', params.limit);
    if (params.status) queryParams.append('status', params.status);
    if (params.business_type) queryParams.append('business_type', params.business_type);

    const queryString = queryParams.toString();
    const endpoint = `businesses${queryString ? `?${queryString}` : ''}`;
    
    return this.adminApiCall(endpoint);
  }

  // Update business status
  static async updateBusinessStatus(businessId, action) {
    return this.adminApiCall(`businesses/${businessId}/status/`, {
      method: 'PATCH',
      body: JSON.stringify({ action })
    });
  }

  static async toggleBusinessStatus(businessId, currentStatusCode) {
    const action = currentStatusCode === 1 ? 'deactivate' : 'activate';
    return this.updateBusinessStatus(businessId, action);
  }

  // Update business payment status
  static async updateBusinessPaymentStatus(businessId, paymentStatus) {
    return this.adminApiCall(`businesses/${businessId}/payment-status/`, {
      method: 'PATCH',
      body: JSON.stringify({ new_payment_status: paymentStatus })
    });
  }

  // Update business details
  static async updateBusinessDetails(businessId, businessDetails) {
    return this.adminApiCall(`businesses/${businessId}/details/`, {
      method: 'PATCH',
      body: JSON.stringify(businessDetails)
    });
  }

  // Business comprehensive details (Swiggy-style)
  static async getBusinessDetails(businessId) {
    return this.adminApiCall(`businesses/${encodeURIComponent(businessId)}/details/`);
  }

  // Business detailed view with all tabs data
  static async getBusinessDetailedView(businessId, period = '7days') {
    const endpoint = `business-management/${encodeURIComponent(businessId)}/detailed/?period=${period}`;
    return this.adminApiCall(endpoint);
  }

  // Business menu items
  static async getBusinessMenuItems(businessId) {
    return this.adminApiCall(`business-management/${encodeURIComponent(businessId)}/menu/`);
  }

  // Create menu item
  static async createMenuItem(businessId, itemData) {
    return this.adminApiCall(
      `business-management/${encodeURIComponent(businessId)}/menu/`,
      {
        method: 'POST',
        body: JSON.stringify(itemData)
      }
    );
  }

  // Update menu item
  static async updateMenuItem(businessId, itemData) {
    return this.adminApiCall(
      `business-management/${encodeURIComponent(businessId)}/menu/`,
      {
        method: 'PUT',
        body: JSON.stringify(itemData)
      }
    );
  }

  // Delete menu item
  static async deleteMenuItem(businessId, itemId, itemType) {
    return this.adminApiCall(
      `business-management/${encodeURIComponent(businessId)}/menu/?item_id=${itemId}&item_type=${itemType}`,
      {
        method: 'DELETE'
      }
    );
  }

  // Update order
  static async updateOrder(businessId, orderData) {
    return this.adminApiCall(
      `business-management/${encodeURIComponent(businessId)}/orders/`,
      {
        method: 'PUT',
        body: JSON.stringify(orderData)
      }
    );
  }

  // Delete order
  static async deleteOrder(businessId, orderId, orderType) {
    return this.adminApiCall(
      `business-management/${encodeURIComponent(businessId)}/orders/?order_id=${orderId}&order_type=${orderType}`,
      {
        method: 'DELETE'
      }
    );
  }

  // Create coupon
  static async createCoupon(businessId, couponData) {
    return this.adminApiCall(
      `business-management/${encodeURIComponent(businessId)}/coupons/`,
      {
        method: 'POST',
        body: JSON.stringify(couponData)
      }
    );
  }

  // Update coupon
  static async updateCoupon(businessId, couponId, couponData) {
    return this.adminApiCall(
      `business-management/${encodeURIComponent(businessId)}/coupons/`,
      {
        method: 'PUT',
        body: JSON.stringify({
          ...couponData,
          coupon_id: couponId
        })
      }
    );
  }

  // Delete coupon
  static async deleteCoupon(businessId, couponId) {
    return this.adminApiCall(
      `business-management/${encodeURIComponent(businessId)}/coupons/?coupon_id=${couponId}`,
      {
        method: 'DELETE'
      }
    );
  }

  // Create offer
  static async createOffer(businessId, offerData) {
    return this.adminApiCall(
      `business-management/${encodeURIComponent(businessId)}/offers/`,
      {
        method: 'POST',
        body: JSON.stringify(offerData)
      }
    );
  }

  // Update offer
  static async updateOffer(businessId, offerId, offerData) {
    return this.adminApiCall(
      `business-management/${encodeURIComponent(businessId)}/offers/`,
      {
        method: 'PUT',
        body: JSON.stringify({
          ...offerData,
          offer_id: offerId
        })
      }
    );
  }

  // Delete offer
  static async deleteOffer(businessId, offerId) {
    return this.adminApiCall(
      `business-management/${encodeURIComponent(businessId)}/offers/?offer_id=${offerId}`,
      {
        method: 'DELETE'
      }
    );
  }

  // Business performance metrics
  static async getBusinessPerformanceMetrics(businessId, days = 30) {
    return this.adminApiCall(`analytics/business-performance/${encodeURIComponent(businessId)}/?days=${days}`);
  }

  // Best selling items
  static async getBestSellingItems(businessId, days = 30, limit = 10) {
    return this.adminApiCall(`analytics/best-selling-items/${encodeURIComponent(businessId)}/?days=${days}&limit=${limit}`);
  }

  // Frequent users
  static async getFrequentUsers(businessId, days = 90, limit = 10) {
    return this.adminApiCall(`analytics/frequent-users/${encodeURIComponent(businessId)}/?days=${days}&limit=${limit}`);
  }

  // Business alerts
  static async getBusinessAlerts(businessId) {
    return this.adminApiCall(`businesses/${encodeURIComponent(businessId)}/alerts/`);
  }

  static async createBusinessAlert(businessId, payload) {
    return this.adminApiCall(`businesses/${encodeURIComponent(businessId)}/alerts/`, {
      method: 'POST',
      body: JSON.stringify(payload),
    });
  }

  static async resolveBusinessAlert(businessId, alertId, payload = {}) {
    return this.adminApiCall(`businesses/${encodeURIComponent(businessId)}/alerts/${alertId}/resolve/`, {
      method: 'PATCH',
      body: JSON.stringify(payload),
    });
  }

  // Deactivate business (soft delete)
  static async deactivateBusiness(businessId) {
    return this.adminApiCall(`businesses/${businessId}/`, {
      method: 'DELETE'
    });
  }

  // ===== ORDER MANAGEMENT SERVICE =====

  // List all orders with filtering
  static async getAllOrders(params = {}) {
    const queryParams = new URLSearchParams();
    
    if (params.page) queryParams.append('page', params.page);
    if (params.limit) queryParams.append('limit', params.limit);
    if (params.status) queryParams.append('status', params.status);
    if (params.order_type) queryParams.append('order_type', params.order_type);
    if (params.business_id) queryParams.append('business_id', params.business_id);

    const queryString = queryParams.toString();
    const endpoint = `orders${queryString ? `?${queryString}` : ''}`;
    
    return this.adminApiCall(endpoint);
  }

  // Update order status
  static async updateOrderStatus(orderId, newStatus, orderSystem = 'standard') {
    return this.adminApiCall(`orders/${orderId}/status/`, {
      method: 'PATCH',
      body: JSON.stringify({ 
        new_status: newStatus,
        order_system: orderSystem 
      })
    });
  }

  // Assign delivery partner to order
  static async assignDeliveryPartner(orderId, deliveryPartnerId, orderSystem = 'standard') {
    return this.adminApiCall(`orders/${orderId}/assign-delivery/`, {
      method: 'POST',
      body: JSON.stringify({ 
        delivery_partner_id: deliveryPartnerId,
        order_system: orderSystem 
      })
    });
  }

  // ===== DELIVERY PROVIDER SERVICE =====

  // List all delivery providers
  static async getAllDeliveryProviders(params = {}) {
    const queryParams = new URLSearchParams();
    
    if (params.page) queryParams.append('page', params.page);
    if (params.limit) queryParams.append('limit', params.limit);

    const queryString = queryParams.toString();
    const endpoint = `delivery-providers${queryString ? `?${queryString}` : ''}`;
    
    return this.adminApiCall(endpoint);
  }

  // Get delivery provider details
  static async getDeliveryProviderDetails(providerId) {
    return this.adminApiCall(`delivery-providers/${providerId}/`);
  }

  // Update delivery provider details
  static async updateDeliveryProvider(providerId, updateData) {
    return this.adminApiCall(`delivery-providers/${providerId}`, {
      method: 'PUT',
      body: JSON.stringify(updateData)
    });
  }

  // Get delivery location history for a specific order
  static async getDeliveryLocationHistory(orderId) {
    try {
      console.log('🔄 Calling snap-to-roads endpoint for order:', orderId);
      
      // Call the snap-to-roads endpoint for clean, road-aligned routes
      const response = await fetch(`https://kirazee.com/kirazee/delivery-partner/snap-to-roads/?order_id=${orderId}`, {
        method: 'GET',
        headers: {
          'Content-Type': 'application/json'
        }
      });
      
      console.log('📡 Snap-to-roads response status:', response.status);
      
      if (!response.ok) {
        console.error('❌ Failed to fetch snapped route:', response.status, response.statusText);
        return null;  // Return null instead of empty array
      }
      
      const data = await response.json();
      console.log('📡 Snap-to-Roads API full response:', data);
      
      // Extract snapped points from the response
      if (data.success && data.data && data.data.points) {
        const points = data.data.points.map(point => ({
          latitude: parseFloat(point.latitude),
          longitude: parseFloat(point.longitude),
          placeId: point.placeId
        })).filter(point => 
          !isNaN(point.latitude) && 
          !isNaN(point.longitude)
        );
        
        console.log('✅ Route processing:');
        console.log('  - Snapped to roads:', data.data.snapped);
        console.log('  - Original GPS points:', data.data.original_count);
        console.log('  - After cleaning:', data.data.cleaned_count);
        console.log('  - Final route points:', points.length);
        console.log('  - First 3 points:', points.slice(0, 3));
        console.log('  - Last 3 points:', points.slice(-3));
        console.log('  - START POINT (for RED marker):', data.data.start_point);
        console.log('  - END POINT (for BLUE marker):', data.data.end_point);
        
        // Return both route points and start/end markers from GPS data
        const result = {
          points: points,
          startPoint: data.data.start_point,  // First GPS point for RED marker
          endPoint: data.data.end_point,      // Last GPS point for BLUE marker
          snapped: data.data.snapped,
          method: data.data.method
        };
        
        console.log('📦 Returning location data object:', result);
        return result;
      }
      
      console.warn('⚠️ No points in response');
      return null;
    } catch (error) {
      console.error('❌ Error fetching snapped route:', error);
      return null;  // Return null instead of empty array
    }
  }

  // Get all delivery orders for a delivery partner (combines active and history)
  static async getAllDeliveryPartnerOrders(userId) {
    try {
      console.log('Fetching ALL delivery orders for user ID:', userId);
      
      // Fetch both active orders and order history simultaneously
      const [activeResponse, historyResponse] = await Promise.all([
        this.getDeliveryPartnerActiveOrders(userId),
        this.getDeliveryPartnerOrderHistory(userId)
      ]);
      
      // Process and combine all orders
      const allOrders = {
        active_orders: activeResponse || [],
        order_history: historyResponse || [],
        total_count: 0,
        combined_orders: []
      };
      
      // Extract orders from responses
      let activeOrders = [];
      let historyOrders = [];
      
      // Process active orders (new API structure with status-based categorization)
      if (activeResponse && activeResponse.success) {
        activeOrders = activeResponse.orders || []; // Truly active orders
        // Also get orders that were categorized as history from the active API
        if (activeResponse.history_orders && activeResponse.history_orders.length > 0) {
          historyOrders.push(...activeResponse.history_orders);
        }
      } else if (activeResponse && Array.isArray(activeResponse)) {
        activeOrders = activeResponse;
      } else if (activeResponse && activeResponse.data && Array.isArray(activeResponse.data)) {
        activeOrders = activeResponse.data;
      }
      
      // Process order history (correct API structure)
      if (historyResponse && historyResponse.success && historyResponse.orders) {
        // Add orders from history API to the existing history orders
        historyOrders.push(...historyResponse.orders);
      } else if (historyResponse && Array.isArray(historyResponse)) {
        historyOrders.push(...historyResponse);
      } else if (historyResponse && historyResponse.data && Array.isArray(historyResponse.data)) {
        historyOrders.push(...historyResponse.data);
      } else if (historyResponse && historyResponse.results && Array.isArray(historyResponse.results)) {
        historyOrders.push(...historyResponse.results);
      }
      
      console.log('Final history orders after processing both APIs:', historyOrders);
      
      // Mark orders with their type for easier identification
      const markedActiveOrders = activeOrders.map(order => ({ ...order, order_type: 'active' }));
      const markedHistoryOrders = historyOrders.map(order => ({ ...order, order_type: 'completed' }));
      
      // Combine all orders
      allOrders.active_orders = markedActiveOrders;
      allOrders.order_history = markedHistoryOrders;
      allOrders.combined_orders = [...markedActiveOrders, ...markedHistoryOrders];
      allOrders.total_count = markedActiveOrders.length + markedHistoryOrders.length;
      
      console.log('Combined orders result:', allOrders);
      console.log(`Total orders found: ${allOrders.total_count} (Active: ${markedActiveOrders.length}, History: ${markedHistoryOrders.length})`);
      
      // Add additional metadata from active orders response
      if (activeResponse && activeResponse.success) {
        allOrders.standard_count = activeResponse.standard_count || 0;
        allOrders.grocery_count = activeResponse.grocery_count || 0;
      }
      
      return allOrders;
    } catch (error) {
      console.error('Failed to fetch all delivery partner orders:', error);
      throw error;
    }
  }

  // Get delivery partner's current/active orders
  static async getDeliveryPartnerActiveOrders(userId) {
    try {
      const url = `https://kirazee.com/kirazee/delivery-partner/display-took-orders/?user_id=${userId}`;
      console.log('Fetching active orders from URL:', url);
      
      const response = await fetch(url, {
        method: 'GET',
        headers: {
          'Content-Type': 'application/json'
        }
      });
      
      console.log('Active orders response status:', response.status);
      
      if (!response.ok) {
        const errorText = await response.text();
        console.error('Active orders API error response:', errorText);
        throw new Error(`HTTP error! status: ${response.status}, message: ${errorText}`);
      }
      
      const data = await response.json();
      console.log('Active orders API response data:', data);
      
      // Process the response structure based on your API format
      if (data.success) {
        const allOrders = [];
        const activeOrders = [];
        const historyOrders = [];
        
        // Define statuses that should go to order history
        const historyStatuses = ['picked_up', 'delivered', 'cancelled'];
        
        // Process standard delivery orders
        if (data.standard_delivery && data.standard_delivery.orders) {
          const standardOrders = data.standard_delivery.orders.map(order => ({
            ...order,
            delivery_type: 'standard',
            order_system: 'standard'
          }));
          
          // Categorize orders based on status
          standardOrders.forEach(order => {
            if (historyStatuses.includes(order.status)) {
              historyOrders.push(order);
            } else {
              activeOrders.push(order);
            }
          });
          
          allOrders.push(...standardOrders);
        }
        
        // Process grocery delivery orders
        if (data.grocery_delivery && data.grocery_delivery.orders) {
          const groceryOrders = data.grocery_delivery.orders.map(order => ({
            ...order,
            delivery_type: 'grocery',
            order_system: 'grocery'
          }));
          
          // Categorize orders based on status
          groceryOrders.forEach(order => {
            if (historyStatuses.includes(order.status)) {
              historyOrders.push(order);
            } else {
              activeOrders.push(order);
            }
          });
          
          allOrders.push(...groceryOrders);
        }
        
        console.log('Processed orders:', {
          total: allOrders.length,
          active: activeOrders.length,
          history: historyOrders.length,
          standard: data.standard_delivery?.count || 0,
          grocery: data.grocery_delivery?.count || 0
        });
        
        return {
          success: true,
          orders: activeOrders, // Only return truly active orders
          history_orders: historyOrders, // Return history orders separately
          all_orders: allOrders, // Return all orders
          total_count: data.total_count || allOrders.length,
          active_count: activeOrders.length,
          history_count: historyOrders.length,
          standard_count: data.standard_delivery?.count || 0,
          grocery_count: data.grocery_delivery?.count || 0
        };
      } else {
        console.warn('API response indicates failure:', data);
        return {
          success: false,
          orders: [],
          total_count: 0,
          standard_count: 0,
          grocery_count: 0
        };
      }
    } catch (error) {
      console.error('Failed to fetch active orders:', error);
      throw error;
    }
  }

  // Get delivery partner's order history
  static async getDeliveryPartnerOrderHistory(userId) {
    try {
      const url = `https://kirazee.com/kirazee/delivery-partner/delivery-order-history/?user_id=${userId}`;
      console.log('Fetching order history from URL:', url);
      
      const response = await fetch(url, {
        method: 'GET',
        headers: {
          'Content-Type': 'application/json'
        }
      });
      
      console.log('Order history response status:', response.status);
      
      if (!response.ok) {
        const errorText = await response.text();
        console.error('Order history API error response:', errorText);
        throw new Error(`HTTP error! status: ${response.status}, message: ${errorText}`);
      }
      
      const data = await response.json();
      console.log('Order history API response data:', data);
      
      // Process the order history response (actual API structure)
      if (data.success && data.delivered_orders) {
        // Separate orders by type (delivery vs grocery)
        const deliveryOrders = [];
        const groceryOrders = [];
        
        data.delivered_orders.forEach(order => {
          const processedOrder = {
            ...order,
            order_type: 'completed',
            delivery_type: order.order_type === 'grocery' ? 'grocery' : 'standard',
            order_system: order.order_type === 'grocery' ? 'grocery' : 'standard'
          };
          
          if (order.order_type === 'grocery') {
            groceryOrders.push(processedOrder);
          } else {
            deliveryOrders.push(processedOrder);
          }
        });
        
        const allHistoryOrders = [...deliveryOrders, ...groceryOrders];
        
        console.log('Processed order history:', allHistoryOrders);
        console.log(`Total history orders: ${allHistoryOrders.length} (Delivery: ${deliveryOrders.length}, Grocery: ${groceryOrders.length})`);
        console.log(`API reported: Total: ${data.total_orders}, Delivered: ${data.delivered_count}`);
        
        return {
          success: true,
          orders: allHistoryOrders,
          total_count: data.total_orders || allHistoryOrders.length,
          delivered_count: data.delivered_count || allHistoryOrders.length,
          delivery_count: deliveryOrders.length,
          grocery_count: groceryOrders.length,
          available_statuses: data.available_statuses || []
        };
      } else {
        console.warn('Order history API response indicates failure or no delivered_orders:', data);
        return {
          success: false,
          orders: [],
          total_count: 0,
          delivered_count: 0,
          delivery_count: 0,
          grocery_count: 0,
          available_statuses: []
        };
      }
    } catch (error) {
      console.error('Failed to fetch order history:', error);
      throw error;
    }
  }

  // ===== BUSINESS REVIEW SERVICE =====

  // Get pending businesses for review
  static async getPendingBusinesses(params = {}) {
    const queryParams = new URLSearchParams();
    
    if (params.page) queryParams.append('page', params.page);
    if (params.limit) queryParams.append('limit', params.limit);
    if (params.business_type) queryParams.append('business_type', params.business_type);
    if (params.location) queryParams.append('location', params.location);
    if (params.submission_date) queryParams.append('submission_date', params.submission_date);
    if (params.search) queryParams.append('search', params.search);

    const queryString = queryParams.toString();
    const endpoint = `businesses/pending-review${queryString ? `?${queryString}` : ''}`;
    
    return this.adminApiCall(endpoint);
  }

  // Get business details for review
  static async getBusinessReviewDetails(businessId) {
    return this.adminApiCall(`businesses/${businessId}/review-details/`);
  }

  // Approve business
  static async approveBusiness(businessId, reviewData = {}) {
    return this.adminApiCall(`businesses/${businessId}/approve/`, {
      method: 'POST',
      body: JSON.stringify({
        approved_by: reviewData.approved_by || 'admin',
        approval_notes: reviewData.approval_notes || '',
        approval_date: new Date().toISOString()
      })
    });
  }

  // Reject business
  static async rejectBusiness(businessId, rejectionData) {
    return this.adminApiCall(`businesses/${businessId}/reject/`, {
      method: 'POST',
      body: JSON.stringify({
        rejected_by: rejectionData.rejected_by || 'admin',
        rejection_reason: rejectionData.rejection_reason,
        rejection_date: new Date().toISOString()
      })
    });
  }

  // Verify business document
  static async verifyBusinessDocument(businessId, documentType, verificationStatus) {
    return this.adminApiCall(`businesses/${businessId}/documents/${documentType}/verify/`, {
      method: 'PATCH',
      body: JSON.stringify({
        verification_status: verificationStatus,
        verified_by: 'admin',
        verification_date: new Date().toISOString()
      })
    });
  }

  // Check for duplicate businesses
  static async checkDuplicateBusiness(businessData) {
    return this.adminApiCall('/businesses/check-duplicate/', {
      method: 'POST',
      body: JSON.stringify({
        business_name: businessData.business_name,
        gst_number: businessData.gst_number,
        phone: businessData.phone,
        email: businessData.email
      })
    });
  }

  // Verify GST number
  static async verifyGSTNumber(gstNumber) {
    return this.adminApiCall('/businesses/verify-gst/', {
      method: 'POST',
      body: JSON.stringify({ gst_number: gstNumber })
    });
  }

  // Verify FSSAI number
  static async verifyFSSAINumber(fssaiNumber) {
    return this.adminApiCall('/businesses/verify-fssai/', {
      method: 'POST',
      body: JSON.stringify({ fssai_number: fssaiNumber })
    });
  }

  // Get business review statistics
  static async getBusinessReviewStats() {
    return this.adminApiCall('/businesses/review-stats/');
  }

  // ===== ANALYTICS & REPORTING SERVICE =====

  // Get business performance analytics
  static async getBusinessAnalytics(params = {}) {
    const queryParams = new URLSearchParams();
    
    if (params.date_from) queryParams.append('date_from', params.date_from);
    if (params.date_to) queryParams.append('date_to', params.date_to);
    if (params.business_type) queryParams.append('business_type', params.business_type);

    const queryString = queryParams.toString();
    const endpoint = `analytics/businesses${queryString ? `?${queryString}` : ''}`;
    
    return this.adminApiCall(endpoint);
  }

  // Get dashboard summary data from new API endpoint
  static async getDashboardSummary() {
    return this.adminApiCall('/dashboard/summary/');
  }

  // NEW: Get lightweight snapshot (cached on backend)
  static async getDashboardSnapshot() {
    return this.adminApiCall('/dashboard/latest/');
  }

  // NEW: Get real monthly revenue trend data from database  
  static async getRevenueTrend(period = 'monthly', days = 180) {
    return this.adminApiCall(`analytics/revenue-trend/?period=${period}&days=${days}&include_business_details=true`);
  }

  // NEW: Get active fleet locations for map visualization
  static async getActiveFleetLocations() {
    return this.adminApiCall('/delivery/active-fleet/');
  }

  // ===== ORDER MANAGEMENT SERVICE =====

  // Get dashboard overview data (legacy method - now uses new API)
  static async getDashboardOverview() {
    try {
      // Use the new dashboard summary API
      const response = await this.getDashboardSummary();
      
      if (response.success) {
        return {
          platformSummary: {
            totalRevenue: response.kpi_metrics.total_revenue,
            totalOrders: response.kpi_metrics.total_orders,
            activeBusinesses: response.kpi_metrics.active_businesses,
            uniqueCustomers: response.kpi_metrics.unique_customers,
            averageOrderValue: response.kpi_metrics.average_order_value,
            activeDeliveryPartners: response.kpi_metrics.active_delivery_partners
          },
          recentOrders: response.recent_orders || [],
          businessStats: {
            totalBusinessCount: response.business_stats.total_business_count,
            nonVerifiedCount: response.business_stats.non_verified_count,
            paymentPendingCount: response.business_stats.payment_pending_count,
            activeBusinessCount: response.business_stats.active_business_count
          },
          deliveryStats: {
            activePartners: response.delivery_fleet_stats.active_partners_count,
            ordersInTransit: response.delivery_fleet_stats.in_transit_orders_count,
            completedToday: response.delivery_fleet_stats.completed_today_count
          },
          debugInfo: response.debug_info || null
        };
      }
      
      throw new Error('API response was not successful');
    } catch (error) {
      console.error('Error fetching dashboard overview:', error);
      
      // Fallback to old method if new API fails
      try {
        const [analyticsData, orderData, deliveryData] = await Promise.all([
          this.getBusinessAnalytics(),
          this.getAllOrders({ limit: 10 }),
          this.getAllDeliveryProviders({ limit: 20 })
        ]);

        // Calculate delivery stats
        const activePartners = deliveryData.providers?.filter(p => p.status === 'Available').length || 0;
        const busyPartners = deliveryData.providers?.filter(p => p.status === 'Busy').length || 0;
        const ordersInTransit = orderData.orders?.filter(o => 
          ['assigned', 'picked_up', 'travelling', 'out_for_delivery'].includes(o.status)
        ).length || 0;

        return {
          platformSummary: analyticsData.platform_summary || {},
          recentOrders: orderData.orders || [],
          businessStats: {
            newRegistrations: analyticsData.business_performance?.length || 0,
            pendingApprovals: analyticsData.platform_summary?.total_businesses - analyticsData.platform_summary?.active_businesses || 0,
            activeToday: analyticsData.platform_summary?.active_businesses || 0
          },
          deliveryStats: {
            activePartners: activePartners,
            ordersInTransit: ordersInTransit,
            completedToday: orderData.orders?.filter(o => o.status === 'completed' || o.status === 'delivered').length || 0,
            busyPartners: busyPartners
          }
        };
      } catch (fallbackError) {
        console.error('Fallback method also failed:', fallbackError);
        throw fallbackError;
      }
    }
  }

  // ===== AUTHENTICATION & UTILITIES =====

  // Verify admin authentication
  static async verifyAdminAuth() {
    try {
      // This would verify the admin token with the backend
      const adminToken = localStorage.getItem('admin_token') || 
                        sessionStorage.getItem('admin_session');
      
      if (!adminToken) {
        return { isValid: false, message: 'No admin token found' };
      }

      // Mock verification - replace with actual API call
      return { isValid: true, message: 'Admin authenticated' };
    } catch (error) {
      return { isValid: false, message: 'Authentication failed' };
    }
  }

  // Admin login
  static async adminLogin(credentials) {
    try {
      const response = await fetch(`${this.ADMIN_BASE_URL}/auth/login`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json'
        },
        body: JSON.stringify(credentials)
      });

      const data = await response.json();
      
      if (data.success && data.admin_token) {
        localStorage.setItem('admin_token', data.admin_token);
        return { success: true, token: data.admin_token };
      }
      
      return { success: false, message: data.message || 'Login failed' };
    } catch (error) {
      console.error('Admin login failed:', error);
      return { success: false, message: 'Network error' };
    }
  }

  // Admin logout
  static adminLogout() {
    localStorage.removeItem('admin_token');
    sessionStorage.removeItem('admin_session');
  }

  // ===== ORDER MANAGEMENT SERVICE =====

  // Get order details by ID with items
  static async getOrderDetails(orderId, orderSystem = 'standard') {
    try {
      return await this.adminApiCall(`orders/${orderId}/?order_system=${orderSystem}`);
    } catch (error) {
      console.error('Failed to fetch order details:', error);
      throw error;
    }
  }

  // Format currency for display
  static formatCurrency(amount) {
    return new Intl.NumberFormat('en-IN', {
      style: 'currency',
      currency: 'INR'
    }).format(amount);
  }

  // Format date for display
  static formatDate(dateString) {
    return new Date(dateString).toLocaleDateString('en-IN', {
      year: 'numeric',
      month: 'short',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit'
    });
  }

  // Get status color
  static getStatusColor(status) {
    const colors = {
      active: '#4caf50',
      inactive: '#f44336',
      pending: '#ff9800',
      confirmed: '#2196f3',
      preparing: '#ff5722',
      ready: '#4caf50',
      delivered: '#8bc34a',
      cancelled: '#f44336',
      paid: '#4caf50',
      unpaid: '#f44336'
    };
    return colors[status?.toLowerCase()] || '#666';
  }

  // ===== CUSTOMER MANAGEMENT SERVICE =====

  /**
   * Get all customers with pagination and filters
   * @param {Object} params - Query parameters
   * @returns {Promise} Customer list with pagination
   */
  static async getAllCustomers(params = {}) {
    try {
      const queryParams = new URLSearchParams();
      
      if (params.page) queryParams.append('page', params.page);
      if (params.limit) queryParams.append('limit', params.limit);
      if (params.search) queryParams.append('search', params.search);
      if (params.status) queryParams.append('status', params.status);
      if (params.date_from) queryParams.append('date_from', params.date_from);
      if (params.date_to) queryParams.append('date_to', params.date_to);

      const queryString = queryParams.toString();
      const endpoint = `customers${queryString ? `?${queryString}` : ''}`;
      
      return await this.adminApiCall(endpoint);
    } catch (error) {
      console.error('Error fetching customers:', error);
      // Return fallback data from dashboard summary
      try {
        const summaryData = await this.getDashboardSummary();
        if (summaryData.success && summaryData.user_analytics) {
          return {
            success: true,
            customers: summaryData.user_analytics.unique_customers_details || [],
            pagination: {
              total: summaryData.user_analytics.unique_customers_details?.length || 0,
              current_page: 1,
              per_page: params.limit || 20,
              total_pages: 1
            }
          };
        }
      } catch (fallbackError) {
        console.error('Fallback also failed:', fallbackError);
      }
      throw error;
    }
  }

  /**
   * Get customer details by ID
   * @param {string} customerId - Customer ID
   * @returns {Promise} Customer details
   */
  static async getCustomerDetails(customerId) {
    try {
      return await this.adminApiCall(`customers/${customerId}/`);
    } catch (error) {
      console.error('Error fetching customer details:', error);
      throw error;
    }
  }

  /**
   * Get customer order history
   * @param {string} customerId - Customer ID
   * @returns {Promise} Customer orders
   */
  static async getCustomerOrders(customerId) {
    try {
      return await this.adminApiCall(`customers/${customerId}/orders/`);
    } catch (error) {
      console.error('Error fetching customer orders:', error);
      // Fallback: get all orders and filter by customer
      try {
        const ordersResponse = await this.getAllOrders({ limit: 100 });
        if (ordersResponse.success) {
          const customerOrders = ordersResponse.orders.filter(
            order => order.user_id === customerId || order.customer_id === customerId
          );
          return {
            success: true,
            orders: customerOrders,
            total_orders: customerOrders.length,
            total_spent: customerOrders.reduce((sum, order) => sum + (order.total_amount || 0), 0)
          };
        }
      } catch (fallbackError) {
        console.error('Fallback failed:', fallbackError);
      }
      throw error;
    }
  }

  /**
   * Update customer status
   * @param {string} customerId - Customer ID
   * @param {string} status - New status (active/inactive/blocked)
   * @returns {Promise} Update result
   */
  static async updateCustomerStatus(customerId, status) {
    try {
      return await this.adminApiCall(`customers/${customerId}/status/`, {
        method: 'PATCH',
        body: JSON.stringify({ status })
      });
    } catch (error) {
      console.error('Error updating customer status:', error);
      throw error;
    }
  }

  // ===== DELIVERY PARTNER ONBOARDING (ADMIN) =====
  
  // Get unverified delivery partners (KYC verification)
  static async getUnverifiedDeliveryPartnersNew(params = {}) {
    try {
      console.log('Fetching unverified partners with params:', params);
      const queryParams = new URLSearchParams();
      
      // Add pagination
      if (params.page) queryParams.append('page', params.page);
      if (params.limit) queryParams.append('limit', params.limit);
      
      // Add filters
      if (params.q) queryParams.append('q', params.q);
      if (params.vehicle_type && params.vehicle_type !== 'all') queryParams.append('vehicle_type', params.vehicle_type);
      if (params.city) queryParams.append('city', params.city);
      if (params.state) queryParams.append('state', params.state);
      if (params.date_from) queryParams.append('date_from', params.date_from);
      if (params.date_to) queryParams.append('date_to', params.date_to);
      
      const queryString = queryParams.toString();
      const endpoint = `/partners/unverified/${queryString ? `?${queryString}` : ''}`;
      console.log('API Endpoint:', endpoint);
      
      const response = await this.deliveryAdminApiCall(endpoint);
      console.log('API Response:', response);
      
      if (!response) {
        console.error('Empty response from API');
        return { success: false, message: 'Empty response from server' };
      }
      
      return response;
    } catch (error) {
      console.error('Error in getUnverifiedDeliveryPartnersNew:', error);
      return { 
        success: false, 
        message: error.message || 'Failed to fetch unverified partners',
        partners: [],
        pagination: {
          total: 0,
          current_page: 1,
          per_page: 10,
          total_pages: 0
        }
      };
    }
  }

  // Delivery Partner KYC (Admin)
  static async getDeliveryPartnerKycDetail(partnerId) {
    if (!partnerId) throw new Error('Partner ID is required');
    try {
      return await this.deliveryAdminApiCall(`partners/${partnerId}/`);
    } catch (err) {
      const msg = err?.message || '';
      // Fallback to legacy applicant detail if the new endpoint is missing
      if (msg.includes('404')) {
        try {
          // 1) Try delivery admin applicants
          const detail = await this.deliveryAdminApiCall(`applicants/${partnerId}/`);
          if (detail && !detail.documents) {
            try {
              const docs = await this.deliveryAdminApiCall(`applicants/${partnerId}/documents/`);
              if (docs && docs.documents) detail.documents = docs.documents;
            } catch (_) { /* ignore */ }
          }
          return detail;
        } catch (_) {
          // 2) Try global admin applicants
          try {
            const detail2 = await this.adminApiCall(`applicants/${partnerId}/`);
            if (detail2 && !detail2.documents) {
              try {
                const docs2 = await this.adminApiCall(`applicants/${partnerId}/documents/`);
                if (docs2 && docs2.documents) detail2.documents = docs2.documents;
              } catch (_) { /* ignore */ }
            }
            return detail2;
          } catch (_) {
            // If both fallbacks fail, rethrow original error
            throw err;
          }
        }
      }
      throw err;
    }
  }

  static async setPartnerDocumentVerification(partnerId, documentType, isVerified) {
    if (!partnerId || !documentType) throw new Error('Partner ID and document type are required');
    return this.deliveryAdminApiCall(`partners/${partnerId}/documents/${documentType}/verify/`, {
      method: 'PATCH',
      body: JSON.stringify({ is_verified: !!isVerified })
    });
  }

  static async approveDeliveryPartner(partnerId, force = false) {
    if (!partnerId) throw new Error('Partner ID is required');
    return this.deliveryAdminApiCall(`partners/${partnerId}/approve/`, {
      method: 'POST',
      body: JSON.stringify({ force: !!force })
    });
  }

  static async rejectDeliveryPartner(partnerId, decisionBody) {
    if (!partnerId) throw new Error('Partner ID is required');
    return this.deliveryAdminApiCall(`partners/${partnerId}/reject/`, {
      method: 'POST',
      body: JSON.stringify(decisionBody)
    });
  }

  static async getOnboardingApplicants(params = {}) {
    const queryParams = new URLSearchParams();

    if (params.status && params.status !== 'all') queryParams.append('status', params.status);
    if (params.vehicle_type && params.vehicle_type !== 'all') queryParams.append('vehicle_type', params.vehicle_type);
    if (params.q) queryParams.append('q', params.q);
    if (params.city) queryParams.append('city', params.city);
    if (params.state) queryParams.append('state', params.state);
    if (params.date_from) queryParams.append('date_from', params.date_from);
    if (params.date_to) queryParams.append('date_to', params.date_to);
    if (params.page) queryParams.append('page', params.page);
    if (params.limit) queryParams.append('limit', params.limit);

    const queryString = queryParams.toString();
    const endpoint = `applicants/${queryString ? `?${queryString}` : ''}`;

    return this.deliveryAdminApiCall(endpoint);
  }

  static async getOnboardingApplicantDetail(applicationId) {
    if (!applicationId) {
      console.error('No application ID provided');
      throw new Error('Application ID is required');
    }

    try {
      console.log(`Fetching applicant details for ID: ${applicationId}`);
      
      // First get the basic applicant details
      let response;
      try {
        response = await this.deliveryAdminApiCall(`applicants/${applicationId}/`);
      } catch (err) {
        if ((err?.message || '').includes('404')) {
          // Fallback to global admin base
          response = await this.adminApiCall(`applicants/${applicationId}/`);
        } else {
          throw err;
        }
      }
      
      if (!response) {
        throw new Error('Empty response from server');
      }
      
      // If the response already has documents, return as is
      if (response.documents && response.documents.length > 0) {
        return response;
      }
      
      // Otherwise, try to fetch documents separately if not included
      try {
        let docsResponse;
        try {
          docsResponse = await this.deliveryAdminApiCall(`applicants/${applicationId}/documents/`);
        } catch (err) {
          if ((err?.message || '').includes('404')) {
            docsResponse = await this.adminApiCall(`applicants/${applicationId}/documents/`);
          } else {
            throw err;
          }
        }
        if (docsResponse && docsResponse.documents) {
          response.documents = docsResponse.documents;
        }
      } catch (docsError) {
        console.warn('Could not fetch documents separately:', docsError);
        // Continue without documents if this fails
        response.documents = [];
      }
      
      return response;
      
    } catch (error) {
      console.error(`Error fetching applicant details for ID ${applicationId}:`, error);
      throw new Error(`Failed to fetch applicant details: ${error.message || 'Unknown error'}`);
    }
  }

  static async updateOnboardingApplicantStatus(applicationId, status) {
    return this.deliveryAdminApiCall(`applicants/${applicationId}/status/`, {
      method: 'PATCH',
      body: JSON.stringify({ status })
    });
  }

  static async decideOnboardingApplicant(applicationId, decisionBody) {
    return this.deliveryAdminApiCall(`applicants/${applicationId}/decision/`, {
      method: 'POST',
      body: JSON.stringify(decisionBody)
    });
  }

  static async batchDecideOnboardingApplicants(payload) {
    return this.deliveryAdminApiCall(`applicants/batch-decision/`, {
      method: 'POST',
      body: JSON.stringify(payload)
    });
  }

  // Review Templates Management
  static async getReviewTemplates(params = {}) {
    const queryParams = new URLSearchParams();
    
    if (params.reason_type) queryParams.append('reason_type', params.reason_type);
    if (params.category) queryParams.append('category', params.category);
    if (params.is_active) queryParams.append('is_active', params.is_active);

    const queryString = queryParams.toString();
    const endpoint = `review-templates${queryString ? `?${queryString}` : ''}`;
    
    return this.adminApiCall(endpoint);
  }

  static async createReviewTemplate(data) {
    return this.adminApiCall('/review-templates/create/', {
      method: 'POST',
      body: JSON.stringify(data)
    });
  }

  static async updateReviewTemplate(id, data) {
    return this.adminApiCall(`review-templates/${id}/`, {
      method: 'PUT',
      body: JSON.stringify(data)
    });
  }

  static async deleteReviewTemplate(id) {
    return this.adminApiCall(`review-templates/${id}/delete/`, {
      method: 'DELETE'
    });
  }

  static async bulkCreateTemplates(data) {
    return this.adminApiCall('review-templates/bulk/', {
      method: 'POST',
      body: JSON.stringify(data)
    });
  }

  // Get business peak hours data (dynamic - with period filtering)
  static async getBusinessPeakHours(businessId, period = '7days') {
    try {
      const response = await this.adminApiCall(`business-management/${businessId}/peak-hours/?period=${period}`);
      return response;
    } catch (error) {
      console.error('Error fetching business peak hours:', error);
      throw error;
    }
  }

  // Get business order status distribution
  static async getBusinessOrderStatus(businessId, period = '7days') {
    try {
      const response = await this.adminApiCall(`business-management/${businessId}/order-status/?period=${period}`);
      return response;
    } catch (error) {
      console.error('Error fetching business order status:', error);
      throw error;
    }
  }
}

export default AdminService;
