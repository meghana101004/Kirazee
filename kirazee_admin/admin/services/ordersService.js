import { API_ENDPOINTS } from '../utils/config';

export class OrdersService {
  static async getPendingOrders(businessId) {
    try {
      const url = `${API_ENDPOINTS.BASE_URL}/delivery-partner/pending-orders/?business_id=${businessId}`;
      console.log('OrdersService: Calling API with URL:', url);
      console.log('OrdersService: Business ID:', businessId);
      
      const response = await fetch(url, {
        method: 'GET',
        headers: {
          'Content-Type': 'application/json',
        },
      });

      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
      }

      const data = await response.json();
      console.log('OrdersService: API Response:', data);
      console.log('OrdersService: Orders count:', data.orders?.length || 0);
      return data;
    } catch (error) {
      console.error('Error fetching pending orders:', error);
      throw error;
    }
  }

  static async getOrderDetails(orderId) {
    try {
      const url = `${API_ENDPOINTS.BASE_URL}/delivery-partner/orders/${orderId}/`;
      
      console.log('Fetching order details from:', url);
      
      const response = await fetch(url, {
        method: 'GET',
        headers: {
          'Content-Type': 'application/json',
        },
      });

      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
      }

      const data = await response.json();
      
      console.log('Order details response:', data);
      
      if (data.success && data.data && data.data.order) {
        return {
          success: true,
          data: data.data.order,
          message: 'Order details fetched successfully'
        };
      } else {
        throw new Error('Invalid response format');
      }
    } catch (error) {
      console.error('Error fetching order details:', error);
      return {
        success: false,
        error: error.message || 'Failed to fetch order details'
      };
    }
  }

  static formatOrderDate(dateString) {
    const date = new Date(dateString);
    return date.toLocaleDateString('en-IN', {
      year: 'numeric',
      month: 'short',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit'
    });
  }

  static formatCurrency(amount) {
    return new Intl.NumberFormat('en-IN', {
      style: 'currency',
      currency: 'INR'
    }).format(amount);
  }

  static getStatusColor(status) {
    switch (status) {
      case 'pending':
        return '#ff8b00';
      case 'paid':
        return '#28a745';
      case 'cancelled':
        return '#dc3545';
      default:
        return '#6c757d';
    }
  }

  static getOrderTypeIcon(orderType) {
    switch (orderType) {
      case 'delivery':
        return 'Delivery';
      case 'pickup':
        return 'Pickup';
      default:
        return 'Standard';
    }
  }

  static async notifyOrderToKirazee(orderId, userId, currentStatus, orderType) {
    try {
      // Per latest API spec, send 'notified' explicitly when user clicks Notify to Kirazee
      const apiAction = 'notified';
      console.log(`Using API action: ${apiAction} (requested via Notify to Kirazee)`);

      const url = `${API_ENDPOINTS.BASE_URL}/consumer/orders/${orderId}/status/`;
      const body = {
        user_id: userId,
        action: apiAction,
        estimated_delivery_time: new Date(Date.now() + 30 * 60 * 1000).toISOString()
      };

      console.log('Notify order payload:', {
        orderId,
        userId,
        currentStatus,
        orderType,
        apiAction,
        body,
        url
      });

      const response = await fetch(url, {
        method: 'PUT',
        headers: {
          'Content-Type': 'application/json'
        },
        body: JSON.stringify(body)
      });

      const data = await response.json();
      
      console.log('Notify order API response:', {
        status: response.status,
        ok: response.ok,
        data: data
      });

      if (!response.ok) {
        console.error('API Error Response:', data);
        throw new Error(data.error || data.message || `HTTP error! status: ${response.status}`);
      }

      // Check if the API response indicates success
      if (data.success === false) {
        console.error('API returned success: false', data);
        throw new Error(data.error || data.message || 'API returned failure status');
      }

      return {
        success: true,
        data,
        message: data.message || 'Order notification sent successfully'
      };
    } catch (error) {
      console.error('Error notifying Kirazee:', error);
      return {
        success: false,
        error: error.message || 'Failed to notify Kirazee'
      };
    }
  }

  static async getActiveDeliveryPartners(businessId) {
    try {
      // Ensure businessId is properly encoded
      const encodedBusinessId = encodeURIComponent(businessId);
      const response = await fetch(
        `${API_ENDPOINTS.BASE_URL}/delivery-partner/boys/?business_id=${encodedBusinessId}`,
        {
          method: 'GET',
          headers: {
            'Content-Type': 'application/json',
            'Accept': 'application/json',
            // Add any required authentication headers here if needed
          },
          // Remove credentials to avoid CORS issues with wildcard origin
          credentials: 'same-origin'
        }
      );

      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
      }

      const data = await response.json();
      // Check if the response has the expected structure
      if (data && data.success && data.providers) {
        return data.providers;
      } else if (Array.isArray(data)) {
        // Handle case where the API returns the array directly
        return data;
      }
      console.warn('Unexpected API response format:', data);
      return [];
    } catch (error) {
      console.error('Error fetching active delivery partners:', error);
      throw error;
    }
  }

  static async getDeliveryPartnerProfile(userId) {
    try {
      const response = await fetch(
        `${API_ENDPOINTS.BASE_URL}/delivery-partner/get-profile/?user_id=${userId}`,
        {
          method: 'GET',
          headers: {
            'Content-Type': 'application/json',
          },
        }
      );

      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
      }

      const data = await response.json();
      return data;
    } catch (error) {
      console.error('Error fetching delivery partner profile:', error);
      throw error;
    }
  }

  static async assignOrderToDeliveryPartner(orderId, deliveryPartnerId, assignedByUserId) {
    try {
      const body = {
        order_id: orderId,
        delivery_partner_id: deliveryPartnerId,
        assigned_by_user_id: assignedByUserId
      };

      // Debug log to verify the data being sent
      console.log('Assign order payload:', {
        orderId,
        deliveryPartnerId,
        assignedByUserId,
        body,
        url: `${API_ENDPOINTS.BASE_URL}/delivery-partner/assign-order/?order_id=${orderId}`
      });

      const response = await fetch(
        `${API_ENDPOINTS.BASE_URL}/delivery-partner/assign-order/?order_id=${orderId}`,
        {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
          },
          body: JSON.stringify(body)
        }
      );

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}));
        console.error('API Error Response:', errorData);
        throw new Error(`HTTP error! status: ${response.status}. ${errorData.error || errorData.message || ''}`);
      }

      const data = await response.json();
      return {
        success: true,
        data: data,
        message: data.message || 'Order assigned successfully'
      };
    } catch (error) {
      console.error('Error assigning order to delivery partner:', error);
      return {
        success: false,
        error: error.message || 'Failed to assign order to delivery partner'
      };
    }
  }

  static async updateOrderStatus(orderId, userId, action, estimatedDeliveryTime = null) {
    try {
      // Map our action names to the API's expected action names
      let finalAction = action;
      
      if (action === 'confirmed') {
        finalAction = 'confirm_order';
      } else if (action === 'ready') {
        finalAction = 'picked_up';
      } else if (action === 'prepared') {
        finalAction = 'mark_ready'; // Both ready and prepared map to mark_ready
      } else if (action === 'picked_up') {
        finalAction = 'picked_up'; // Send picked_up as-is to the API
      } else if (action === 'dispatch') {
        finalAction = 'dispatch_for_delivery';
      } else if (action === 'complete' || action === 'completed') {
        finalAction = 'complete_order';
      }

      // Get the logged-in user's ID from localStorage for assigned_by_user_id
      let assignedByUserId = userId; // fallback
      let deliveryPartnerId = null;
      
      try {
        const loggedInUserData = JSON.parse(localStorage.getItem('kirazee_user') || '{}');
        assignedByUserId = loggedInUserData.user_id || loggedInUserData.id || userId;
        
        // If user is a delivery partner, get delivery partner ID from profile
        if (loggedInUserData.user_mode === 'delivery_partner') {
          try {
            const profileResponse = await this.getDeliveryPartnerProfile(assignedByUserId);
            if (profileResponse && profileResponse.delivery_partner_data) {
              deliveryPartnerId = profileResponse.delivery_partner_data.id;
            }
          } catch (profileError) {
            console.warn('Error getting delivery partner profile:', profileError);
          }
        }
      } catch (error) {
        console.warn('Error parsing logged-in user data from localStorage:', error);
      }

      const body = {
        user_id: userId,
        action: finalAction,
        estimated_delivery_time: estimatedDeliveryTime || new Date(Date.now() + 30 * 60 * 1000).toISOString(),
        assigned_by_user_id: assignedByUserId // Get from logged-in user data
      };

      // Add delivery_partner_id if available
      if (deliveryPartnerId) {
        body.delivery_partner_id = deliveryPartnerId;
      }

      // Debug log to verify the data being sent
      console.log('Order status update payload:', {
        orderId,
        body,
        loggedInUser: localStorage.getItem('kirazee_user')
      });

      const response = await fetch(
        `${API_ENDPOINTS.BASE_URL}/consumer/orders/${orderId}/status/`,
        {
          method: 'PUT',
          headers: {
            'Content-Type': 'application/json',
          },
          body: JSON.stringify(body)
        }
      );

      const data = await response.json();
      
      if (!response.ok) {
        throw new Error(data.message || `HTTP error! status: ${response.status}`);
      }

      return {
        success: true,
        data: data,
        message: data.message || 'Order status updated successfully'
      };
    } catch (error) {
      console.error('Error updating order status:', error);
      return {
        success: false,
        error: error.message || 'Failed to update order status'
      };
    }
  }

  static getAvailableActions(orderType) {
    const deliveryActions = ['assign', 'confirm'];
    const nonDeliveryActions = [
      'confirm_order',
      'start_preparing', 
      'mark_ready',
      'dispatch_for_delivery',
      'start_travelling',
      'complete_order',
      'cancel_order'
    ];

    return orderType?.toLowerCase() === 'delivery' ? deliveryActions : nonDeliveryActions;
  }

  static getActionDisplayName(action) {
    const actionNames = {
      'assign': 'Assign Order',
      'confirm': 'Confirm Order',
      'confirm_order': 'Confirm Order',
      'start_preparing': 'Start Preparing',
      'mark_ready': 'Mark Ready',
      'dispatch_for_delivery': 'Dispatch for Delivery',
      'start_travelling': 'Start Travelling',
      'complete_order': 'Complete Order',
      'cancel_order': 'Cancel Order'
    };

    return actionNames[action] || action.replace('_', ' ').replace(/\b\w/g, l => l.toUpperCase());
  }

  static formatDistance(distanceKm) {
    if (distanceKm === null || distanceKm === undefined || Number.isNaN(distanceKm)) {
      return 'N/A';
    }

    if (distanceKm < 1) {
      return `${Math.round(distanceKm * 1000)}m`;
    }
    return `${distanceKm.toFixed(1)}km`;
  }

  static async getOrderHistory(businessId, status = null, limit = 50, offset = 0) {
    try {
      let url = `${API_ENDPOINTS.BASE_URL}/business/order-online-history/?business_id=${businessId}`;
      
      // Add optional parameters
      const params = new URLSearchParams();
      if (status) params.append('status', status);
      if (limit) params.append('limit', limit.toString());
      if (offset) params.append('offset', offset.toString());
      
      if (params.toString()) {
        url += '&' + params.toString();
      }

      console.log('Fetching order history from:', url);

      const response = await fetch(url, {
        method: 'GET',
        headers: {
          'Content-Type': 'application/json',
        },
      });

      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
      }

      const data = await response.json();
      return {
        success: true,
        data: data,
        orders: data.orders || [],
        pagination: data.pagination || {},
        statusCounts: data.status_counts || {},
        businessInfo: {
          businessId: data.business_id,
          isMasterBusiness: data.is_master_business || false,
          businessesIncluded: data.businesses_included || []
        },
        message: data.message || 'Order history fetched successfully'
      };
    } catch (error) {
      console.error('Error fetching order history:', error);
      return {
        success: false,
        error: error.message || 'Failed to fetch order history',
        orders: [],
        pagination: {},
        statusCounts: {}
      };
    }
  }

  static getOrderStatusColor(status) {
    switch (status?.toLowerCase()) {
      case 'pending':
        return '#ff8b00';
      case 'confirmed':
        return '#17a2b8';
      case 'preparing':
      case 'start_preparing':
        return '#ffc107';
      case 'ready':
        return '#6f42c1';
      case 'picked_up':
        return '#20c997';
      case 'accepted':
        return '#28a745';
      case 'travelling':
      case 'out_for_delivery':
        return '#fd7e14';
      case 'delivered':
      case 'completed':
        return '#28a745';
      case 'cancelled':
        return '#dc3545';
      case 'assigned':
        return '#007bff';
      case 'notified':
        return '#28a745'; // Green color for notified status
      default:
        return '#6c757d';
    }
  }

}
