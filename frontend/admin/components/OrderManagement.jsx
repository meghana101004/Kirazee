import React, { useState, useEffect, useCallback, useRef } from 'react';
import AdminService from '../services/adminService';
import '../../css/admin/OrderManagement.css';
import { FaChevronDown, FaTimes, FaSearch, FaFilter, FaClipboardList, FaStore, FaUser, FaMotorcycle } from 'react-icons/fa';
import { MdRefresh } from 'react-icons/md';

const OrderManagement = () => {
  console.log('OrderManagement component rendered');

  // Helper function to format status display
  const getStatusDisplay = (order) => {
    if (!order || !order.status) return 'UNKNOWN';
    if ((order.status === 'delivered' || order.status === 'completed') &&
      order.order_type?.toLowerCase() === 'pickup') {
      return 'COMPLETED';
    }
    return order.status.toUpperCase();
  };

  const [orders, setOrders] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [filters, setFilters] = useState({
    status: '',
    order_type: '',
    business_id: '',
    page: 1,
    limit: 9
  });
  const [pagination, setPagination] = useState({});
  const [selectedOrder, setSelectedOrder] = useState(null);
  const [showStatusModal, setShowStatusModal] = useState(false);
  const [showDetailsModal, setShowDetailsModal] = useState(false);
  const [updatingStatus, setUpdatingStatus] = useState(false);

  // Debug modal state changes - SEPARATE effects to avoid interference
  useEffect(() => {
    console.log('=== showStatusModal changed to:', showStatusModal);
    if (showStatusModal) {
      console.log('Status modal opened with selectedOrder:', selectedOrder);
      document.body.style.overflow = 'hidden';
    } else {
      console.log('Status modal closed');
      if (!showDetailsModal) {
        document.body.style.overflow = '';
      }
    }
    
    return () => {
      if (!showDetailsModal && !showStatusModal) {
        document.body.style.overflow = '';
      }
    };
  }, [showStatusModal]); // Removed selectedOrder dependency

  // Separate effect for details modal
  useEffect(() => {
    console.log('=== showDetailsModal changed to:', showDetailsModal);
    if (showDetailsModal) {
      console.log('Details modal opened with selectedOrder:', selectedOrder);
      document.body.style.overflow = 'hidden';
    } else {
      console.log('Details modal closed');
      if (!showStatusModal) {
        document.body.style.overflow = '';
      }
    }
    
    return () => {
      if (!showDetailsModal && !showStatusModal) {
        document.body.style.overflow = '';
      }
    };
  }, [showDetailsModal]);

  // Enhanced status update modal states
  const [deliveryPartners, setDeliveryPartners] = useState([]);
  const [selectedDeliveryPartner, setSelectedDeliveryPartner] = useState(null);
  const [loadingPartners, setLoadingPartners] = useState(false);
  const [selectedStatus, setSelectedStatus] = useState('');

  // Custom dropdown states
  const [statusDropdownOpen, setStatusDropdownOpen] = useState(false);
  const [orderTypeDropdownOpen, setOrderTypeDropdownOpen] = useState(false);
  const [searchTimeout, setSearchTimeout] = useState(null);
  const modalOpenTimeRef = useRef(0);

  // Fetch available delivery partners
  const fetchDeliveryPartners = useCallback(async () => {
    try {
      setLoadingPartners(true);
      const response = await AdminService.getAllDeliveryProviders({
        page: 1,
        limit: 50,
        status: 'Available' // Only fetch available partners
      });
      setDeliveryPartners(response.providers || []);
    } catch (err) {
      console.error('Failed to fetch delivery partners:', err);
      setDeliveryPartners([]);
    } finally {
      setLoadingPartners(false);
    }
  }, []);

  // Removed sidebar state - now handled by AdminDashboard

  const fetchOrders = useCallback(async () => {
    try {
      console.log('Fetching orders with filters:', filters);
      setLoading(true);
      setError(null);

      // Fetch real data from admin API
      const response = await AdminService.getAllOrders(filters);
      console.log('Orders API response:', response);

      setOrders(response.orders || []);
      setPagination(response.pagination || {});
    } catch (err) {
      setError('Failed to fetch orders');
      console.error('Orders fetch error:', err);

      // Fallback to mock data if API fails
      const mockResponse = {
        success: true,
        message: "Orders retrieved successfully",
        pagination: {
          total_orders: 1250,
          current_page: 1,
          per_page: 20,
          total_pages: 63,
          has_next_page: true,
          has_prev_page: false
        },
        orders: [
          {
            order_system: "standard",
            order_id: 1001,
            order_number: "ORD-1001-2025",
            status: "confirmed",
            order_type: "delivery",
            total_amount: 350.50,
            created_at: "2025-09-26T14:30:00Z",
            business_id: "KIR123456789",
            business_name: "Spicy Bites Restaurant",
            customer_name: "John Doe",
            customer_phone: "+1234567890",
            delivery_partner_name: "Mike Wilson",
            delivery_partner_phone: "+1555123456"
          },
          {
            order_system: "grocery",
            order_id: 2001,
            order_number: "GRO-2001",
            status: "packed",
            order_type: "delivery",
            total_amount: 125.75,
            created_at: "2025-09-26T15:15:00Z",
            business_id: "KIR987654321",
            business_name: "Fresh Mart Grocery",
            customer_name: "Jane Smith",
            customer_phone: "+0987654321",
            delivery_partner_name: null,
            delivery_partner_phone: null
          },
          {
            order_system: "standard",
            order_id: 1002,
            order_number: "ORD-1002-2025",
            status: "pending",
            order_type: "pickup",
            total_amount: 89.25,
            created_at: "2025-09-26T15:45:00Z",
            business_id: "KIR147712008250351",
            business_name: "DILLI GALLI",
            customer_name: "Alice Johnson",
            customer_phone: "+1122334455",
            delivery_partner_name: null,
            delivery_partner_phone: null
          },
          {
            order_system: "standard",
            order_id: 1003,
            order_number: "ORD-1003-2025",
            status: "assigned",
            order_type: "dine_in",
            total_amount: 245.00,
            created_at: "2025-09-26T16:00:00Z",
            business_id: "KIR147712008250351",
            business_name: "DILLI GALLI",
            customer_name: "Bob Wilson",
            customer_phone: "+9988776655",
            delivery_partner_name: "Sarah Connor",
            delivery_partner_phone: "+1555987654"
          }
        ]
      };

      setOrders(mockResponse.orders);
      setPagination(mockResponse.pagination);
    } finally {
      setLoading(false);
    }
  }, [filters.status, filters.order_type, filters.business_id, filters.page, filters.limit]);

  useEffect(() => {
    fetchOrders();
  }, [fetchOrders]);

  // Close dropdowns when clicking outside
  useEffect(() => {
    const handleClickOutside = (event) => {
      if (statusDropdownOpen && !event.target.closest('.status-dropdown')) {
        setStatusDropdownOpen(false);
      }
      if (orderTypeDropdownOpen && !event.target.closest('.order-type-dropdown')) {
        setOrderTypeDropdownOpen(false);
      }
    };

    document.addEventListener('mousedown', handleClickOutside);
    return () => {
      document.removeEventListener('mousedown', handleClickOutside);
    };
  }, [statusDropdownOpen, orderTypeDropdownOpen]);

  // Cleanup search timeout on unmount
  useEffect(() => {
    return () => {
      if (searchTimeout) {
        clearTimeout(searchTimeout);
      }
    };
  }, [searchTimeout]);

  // Replaced duplicate useEffect for fetching delivery partners and moved its condition fully to handleOpenStatusModal.

  // Removed debug useEffect to prevent extra re-renders

  // Debug showDetailsModal changes - MOVED ABOVE as separate effect

  const handleFilterChange = (key, value) => {
    console.log(`Filter change: ${key} = ${value}`);
    setFilters(prev => {
      const newFilters = {
        ...prev,
        [key]: value,
        page: key === 'page' ? value : 1 // Reset to first page when filter changes, except for page changes
      };
      console.log('New filters:', newFilters);
      return newFilters;
    });
  };

  const handlePageChange = (newPage) => {
    if (newPage >= 1 && newPage <= pagination.total_pages) {
      setFilters(prev => ({
        ...prev,
        page: newPage
      }));
    }
  };

  const handleSearchChange = (value) => {
    // Clear existing timeout
    if (searchTimeout) {
      clearTimeout(searchTimeout);
    }

    // Set new timeout for debounced search
    const newTimeout = setTimeout(() => {
      handleFilterChange('business_id', value);
    }, 300); // 300ms delay

    setSearchTimeout(newTimeout);
  };

  const clearFilters = () => {
    setFilters({
      status: '',
      order_type: '',
      business_id: '',
      page: 1,
      limit: 9
    });
  };



  // Open status update modal and fetch delivery partners
  const handleOpenStatusModal = useCallback((order) => {
    console.log('=== handleOpenStatusModal called ===');
    console.log('Order:', order);
    
    // Record modal open time
    modalOpenTimeRef.current = Date.now();
    
    // Batch state updates (React 18 automatically batches these)
    setSelectedOrder(order);
    setSelectedStatus('');
    setSelectedDeliveryPartner(null);
    setShowStatusModal(true);
    
    console.log('Modal state updated');
    
    // Fetch delivery partners if needed
    if (!loadingPartners && deliveryPartners.length === 0) {
      console.log('Fetching delivery partners');
      fetchDeliveryPartners();
    }
  }, [loadingPartners, deliveryPartners.length, fetchDeliveryPartners]);

  // Open order details modal
  const handleOpenDetailsModal = async (order) => {
    try {
      console.log('Opening order details modal for order:', order);
      console.log('Order customer_name from list:', order.customer_name);
      console.log('Order customer_phone from list:', order.customer_phone);

      // Fetch full order details including items from the API
      const response = await AdminService.getOrderDetails(order.order_id, order.order_system || 'standard');
      
      console.log('API Response:', response);
      
      // API returns {success: true, data: {order: {...}}}
      const orderData = response.data?.order || response.order;
      
      // Check if response has error indicators
      const hasErrorInResponse = !response.success || 
                                 response.error || 
                                 (response.message && response.message.includes('Error'));
      
      if (response.success && orderData) {
        console.log('Customer name from API:', orderData.customer_name);
        console.log('Customer phone from API:', orderData.customer_phone);
        setSelectedOrder(orderData);
        modalOpenTimeRef.current = Date.now();
        setShowDetailsModal(true);
      } else if (hasErrorInResponse) {
        // Backend returned error response - extract error message
        const backendErrorMsg = response.message || response.error || 'Unknown backend error';
        console.log('Backend error in response:', backendErrorMsg);
        throw new Error(backendErrorMsg);
      } else {
        throw new Error('Failed to fetch order details');
      }

    } catch (err) {
      console.error('Failed to open order details:', err);
      
      // ALWAYS fallback to table data when API fails
      // This ensures users can still see basic order info even if backend has errors
      console.log('API failed, falling back to table data for order:', order);
      console.log('Error was:', err.message || err);
      
      // Construct minimal order object from table data
      const fallbackOrder = {
        ...order,
        // Ensure items is at least an empty array
        items: order.items || [],
        // Ensure customer object exists
        customer: order.customer || {
          display_name: order.customer_name,
          phone: order.customer_phone,
          id: order.user_id
        },
        // Ensure business_details exists
        business_details: order.business_details || {
          business_name: order.business_name,
          business_id: order.business_id
        },
        // Minimal summary from available data
        summary: order.summary || {
          subtotal: order.total_amount || 0,
          total: order.final_amount || order.total_amount || 0
        }
      };
      
      setSelectedOrder(fallbackOrder);
      modalOpenTimeRef.current = Date.now();
      setShowDetailsModal(true);
      
      // Don't set blocking error - let user see the modal with fallback data
      console.log('Modal opened with fallback data');
    }
  };

  // Handle status selection
  const handleStatusSelection = useCallback((status) => {
    setSelectedStatus(status);
    // Clear delivery partner selection if not assigning
    if (status !== 'assigned') {
      setSelectedDeliveryPartner(null);
    }
  }, []);

  // Handle final status update
  const handleStatusUpdate = async () => {
    if (!selectedStatus) {
      setError('Please select a status');
      return;
    }

    // Check if delivery partner is required for assignment
    if (selectedStatus === 'assigned' && !selectedDeliveryPartner) {
      setError('Please select a delivery partner for assignment');
      return;
    }

    try {
      setUpdatingStatus(true);
      setError(null);

      if (selectedStatus === 'assigned' && selectedDeliveryPartner) {
        // Use assignment API if assigning to delivery partner
        await AdminService.assignDeliveryPartner(
          selectedOrder.order_id,
          selectedDeliveryPartner.provider_id,
          selectedOrder.order_system || 'standard'
        );
      } else {
        // Use regular status update API
        await AdminService.updateOrderStatus(
          selectedOrder.order_id,
          selectedStatus,
          selectedOrder.order_system || 'standard'
        );
      }

      // Update local state
      setOrders(prev => prev.map(order =>
        order.order_id === selectedOrder.order_id
          ? { ...order, status: selectedStatus }
          : order
      ));

      setShowStatusModal(false);
      setSelectedOrder(null);
      setSelectedStatus('');
      setSelectedDeliveryPartner(null);
    } catch (err) {
      console.error('Status update failed:', err);
      console.error('Error details:', err.response?.data || err.message);
      const errorMessage = err.response?.data?.message || err.message || 'Failed to update order status';
      setError(errorMessage);
    } finally {
      setUpdatingStatus(false);
    }
  };

  const getStatusColor = (status) => {
    return AdminService.getStatusColor(status);
  };

  const formatCurrency = (amount) => {
    return AdminService.formatCurrency(amount);
  };

  const formatDate = (dateString) => {
    return AdminService.formatDate(dateString);
  };

  const formatTime = (dateString) => {
    if (!dateString) return 'N/A';
    const date = new Date(dateString);
    return date.toLocaleTimeString('en-US', { 
      hour: '2-digit', 
      minute: '2-digit',
      hour12: true 
    });
  };

  const statusOptions = [
    'pending', 'confirmed', 'preparing', 'ready', 'assigned',
    'picked_up', 'travelling', 'out_for_delivery', 'delivered',
    'completed', 'cancelled'
  ];

  console.log('OrderManagement render state:', { loading, error, orders: orders.length });

  if (loading) {
    return (
      <div className="order-management-loading">
        <div className="loading-spinner"></div>
        <p>Loading orders...</p>
      </div>
    );
  }

  if (error) {
    return (
      <div className="order-management-error">
        <h3>Error Loading Orders</h3>
        <p>{error}</p>
        <button
          onClick={() => {
            setError(null);
            fetchOrders();
          }}
          style={{
            background: '#F55D00',
            color: 'white',
            border: 'none',
            padding: '6px 12px',
            borderRadius: '6px',
            cursor: 'pointer',
            fontSize: '12px',
            fontWeight: '500'
          }}
        >
          Retry
        </button>
      </div>
    );
  }

  return (
    <div className="order-management">
      {/* Header */}
      <div className="order-management-header">
        <div className="header-content">
          <div className="header-text">
            <h2>Order Management</h2>
            <p>Real-time oversight and manual intervention for all order types</p>
          </div>
        </div>
      </div>

      {/* Filters */}
      <div className="order-filters">
        <div className="filter-group">
          <label>Status</label>
          <div className="status-dropdown custom-dropdown">
            <div
              className="dropdown-input"
              onClick={() => setStatusDropdownOpen(!statusDropdownOpen)}
            >
              <span className="dropdown-placeholder">
                {filters.status ? statusOptions.find(s => s === filters.status)?.replace('_', ' ').toUpperCase() || filters.status : 'All Statuses'}
              </span>
              <FaChevronDown className={`dropdown-arrow ${statusDropdownOpen ? 'open' : ''}`} />
            </div>
            {statusDropdownOpen && (
              <div className="dropdown-menu">
                <div
                  className="dropdown-option"
                  onClick={() => {
                    handleFilterChange('status', '');
                    setStatusDropdownOpen(false);
                  }}
                >
                  All Statuses
                </div>
                {statusOptions.map(status => (
                  <div
                    key={status}
                    className="dropdown-option"
                    onClick={() => {
                      handleFilterChange('status', status);
                      setStatusDropdownOpen(false);
                    }}
                  >
                    {status.replace('_', ' ').toUpperCase()}
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>

        <div className="filter-group">
          <label>Order Type</label>
          <div className="order-type-dropdown custom-dropdown">
            <div
              className="dropdown-input"
              onClick={() => setOrderTypeDropdownOpen(!orderTypeDropdownOpen)}
            >
              <span className="dropdown-placeholder">
                {filters.order_type === 'delivery' ? 'Delivery' :
                  filters.order_type === 'pickup' ? 'Pickup' :
                    filters.order_type === 'dine-in' ? 'Dine In' :
                      filters.order_type === 'takeaway' ? 'Takeaway' :
                        'All Types'}
              </span>
              <FaChevronDown className={`dropdown-arrow ${orderTypeDropdownOpen ? 'open' : ''}`} />
            </div>
            {orderTypeDropdownOpen && (
              <div className="dropdown-menu">
                <div
                  className="dropdown-option"
                  onClick={() => {
                    handleFilterChange('order_type', '');
                    setOrderTypeDropdownOpen(false);
                  }}
                >
                  All Types
                </div>
                <div
                  className="dropdown-option"
                  onClick={() => {
                    handleFilterChange('order_type', 'delivery');
                    setOrderTypeDropdownOpen(false);
                  }}
                >
                  Delivery
                </div>
                <div
                  className="dropdown-option"
                  onClick={() => {
                    handleFilterChange('order_type', 'pickup');
                    setOrderTypeDropdownOpen(false);
                  }}
                >
                  Pickup
                </div>
                <div
                  className="dropdown-option"
                  onClick={() => {
                    handleFilterChange('order_type', 'dine-in');
                    setOrderTypeDropdownOpen(false);
                  }}
                >
                  Dine In
                </div>
                <div
                  className="dropdown-option"
                  onClick={() => {
                    handleFilterChange('order_type', 'takeaway');
                    setOrderTypeDropdownOpen(false);
                  }}
                >
                  Takeaway
                </div>
              </div>
            )}
          </div>
        </div>

        <div className="filter-actions">
          <button className="clear-btn" onClick={clearFilters}>
            Clear Filters
          </button>
          <button className="refresh-btn" onClick={fetchOrders}>
            <MdRefresh className="refresh-icon" />
            Refresh
          </button>
        </div>
      </div>

      {/* Error Display */}
      {error && (
        <div className="error-message">
          {error}
          <button onClick={() => setError(null)}>×</button>
        </div>
      )}

      {/* Orders Table */}
      <div className="orders-table-container">
        {orders.length === 0 ? (
          <div style={{
            textAlign: 'center',
            padding: '40px',
            background: 'white',
            borderRadius: '8px',
            border: '1px solid #e0e0e0'
          }}>
            <h3>No Orders Found</h3>
            <p>No orders match the current filters.</p>
            <button
              onClick={() => {
                setFilters({
                  status: '',
                  order_type: '',
                  business_id: '',
                  page: 1,
                  limit: 10
                });
              }}
              style={{
                background: '#FDBF50',
                color: 'white',
                border: 'none',
                padding: '6px 12px',
                borderRadius: '6px',
                cursor: 'pointer',
                fontSize: '12px',
                fontWeight: '500'
              }}
            >
              Clear Filters
            </button>
          </div>
        ) : (
          <>
            {/* Desktop Table View */}
            <table className="orders-table">
              <thead>
                <tr>
                  <th>Order #</th>
                  <th>Customer</th>
                  <th>Business</th>
                  <th>Type</th>
                  <th>Amount</th>
                  <th>Status</th>
                  <th>Payment</th>
                  <th>Delivery Partner</th>
                  <th>Date</th>
                  <th>Actions</th>
                </tr>
              </thead>
              <tbody>
                {orders.map((order) => (
                  <tr key={`${order.order_system}-${order.order_id}`}>
                    <td className="order-id">
                      <div className="order-number">#{order.order_id}</div>
                      <div className="order-hash">{order.order_id}</div>
                    </td>
                    <td className="customer-info">
                      <div className="customer-name">{order.customer_name}</div>
                      <div className="customer-phone">{order.customer_phone}</div>
                    </td>
                    <td className="business-name">
                      <div className="business-info">
                        <div className="name">{order.business_name}</div>
                      </div>
                    </td>
                    <td className="order-type">
                      <span className={`type-badge ${order.order_type}`}>
                        {order.order_type}
                      </span>
                    </td>
                    <td className="amount">
                      <div className="amount-info">
                        <div className="total">₹{order.total_amount.toFixed(2)}</div>
                      </div>
                    </td>
                    <td className="status">
                      <span
                        className={`status-badge ${order.status.toLowerCase()}`}
                      >
                        {getStatusDisplay(order)}
                      </span>
                    </td>
                    <td style={{ 
                      minWidth: '100px',
                      padding: '12px',
                      textAlign: 'center',
                      verticalAlign: 'middle'
                    }}>
                      <div style={{
                        display: 'inline-block',
                        padding: '4px 8px',
                        borderRadius: '12px',
                        fontSize: '11px',
                        fontWeight: '600',
                        textTransform: 'uppercase',
                        backgroundColor: order.payment_status === 'success' ? '#d4edda' : 
                                         order.payment_status === 'cancelled' ? '#f8d7da' : '#fff3cd',
                        color: order.payment_status === 'success' ? '#155724' : 
                               order.payment_status === 'cancelled' ? '#721c24' : '#856404'
                      }}>
                        {(order.payment_status || 'PENDING').toUpperCase()}
                      </div>
                    </td>
                    <td className="delivery-partner">
                      {order.delivery_partner_name ? (
                        <div className="partner-info">
                          <div className="partner-name">{order.delivery_partner_name}</div>
                        </div>
                      ) : (
                        <div className="no-partner">
                          <span className="no-partner-text">Not Assigned</span>
                        </div>
                      )}
                    </td>
                    <td className="created-date">
                      <div className="date-info">
                        <div className="date">{formatDate(order.created_at)}</div>
                      </div>
                    </td>
                    <td className="actions">
                      <div className="action-buttons">
                        <button
                          type="button"
                          className="details-btn"
                          onClick={(e) => {
                            e.stopPropagation();
                            handleOpenDetailsModal(order);
                          }}
                        >
                          View
                        </button>
                        <button
                          type="button"
                          className="status-btn"
                          onClick={(e) => {
                            e.stopPropagation();
                            handleOpenStatusModal(order);
                          }}
                        >
                          Update
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>

            {/* Mobile Card View */}
            <div className="mobile-orders-container">
              {orders.map((order) => (
                <div key={`mobile-${order.order_system}-${order.order_id}`} className="mobile-order-card">
                  <div className="mobile-order-header">
                    <div className="mobile-order-id">#{order.order_id}</div>
                    <span
                      className={`mobile-status-badge ${order.status.toLowerCase()}`}
                    >
                      {getStatusDisplay(order)}
                    </span>
                  </div>

                  <div className="mobile-order-details">
                    <div className="mobile-detail-item">
                      <div className="mobile-detail-label">Business</div>
                      <div className="mobile-detail-value">
                        <div className="mobile-business-name">{order.business_name}</div>
                        <div className="mobile-business-id">{order.business_id}</div>
                      </div>
                    </div>

                    <div className="mobile-detail-item">
                      <div className="mobile-detail-label">Customer</div>
                      <div className="mobile-detail-value">
                        <div className="mobile-customer-name">{order.customer_name}</div>
                        <div className="mobile-customer-phone">{order.customer_phone}</div>
                      </div>
                    </div>

                    <div className="mobile-detail-item">
                      <div className="mobile-detail-label">Type</div>
                      <div className="mobile-detail-value">
                        <span className={`mobile-type-badge ${order.order_type}`}>
                          {order.order_type}
                        </span>
                      </div>
                    </div>

                    <div className="mobile-detail-item">
                      <div className="mobile-detail-label">Amount</div>
                      <div className="mobile-detail-value mobile-amount">
                        {formatCurrency(order.total_amount)}
                      </div>
                    </div>

                    <div className="mobile-detail-item">
                      <div className="mobile-detail-label">Delivery Partner</div>
                      <div className="mobile-detail-value">
                        {order.delivery_partner_name ? (
                          <div className="mobile-partner-info">
                            <div className="mobile-partner-name">{order.delivery_partner_name}</div>
                            <div className="mobile-partner-phone">{order.delivery_partner_phone}</div>
                          </div>
                        ) : (
                          <span className="mobile-no-partner">Not Assigned</span>
                        )}
                      </div>
                    </div>

                    <div className="mobile-detail-item">
                      <div className="mobile-detail-label">System</div>
                      <div className="mobile-detail-value">
                        <span className={`mobile-system-badge ${order.order_system}`}>
                          {order.order_system}
                        </span>
                      </div>
                    </div>

                    <div className="mobile-detail-item">
                      <div className="mobile-detail-label">Created</div>
                      <div className="mobile-detail-value mobile-created-date">
                        {formatDate(order.created_at)}
                      </div>
                    </div>
                  </div>

                  <div className="mobile-order-actions">
                    <button
                      type="button"
                      className="details-btn"
                      onClick={(e) => {
                        e.stopPropagation();
                        handleOpenDetailsModal(order);
                      }}
                    >
                      View Details
                    </button>
                    <button
                      type="button"
                      className="status-btn"
                      onClick={(e) => {
                        e.stopPropagation();
                        handleOpenStatusModal(order);
                      }}
                    >
                      Update Status
                    </button>
                  </div>
                </div>
              ))}
            </div>
          </>
        )}

        {/* Pagination Inside Table Container */}
        {pagination.total_pages > 1 && (
          <div className="table-pagination" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '12px 20px', borderTop: '1px solid #e0e0e0', background: '#fafafa', flexShrink: 0 }}>
            {/* Pagination Info */}
            <div className="pagination-info" style={{ fontSize: '13px', color: '#666' }}>
              {pagination.total_orders && (
                <span>
                  Showing {pagination.showing_from || 1}-{pagination.showing_to || pagination.items_on_page || 0} 
                  of {pagination.total_orders} orders
                  {pagination.remaining_items && (
                    <span style={{ marginLeft: '8px', color: '#888' }}>
                      ({pagination.remaining_items} remaining)
                    </span>
                  )}
                </span>
              )}
            </div>

            {/* Pagination Controls */}
            <div className="header-pagination">
              <button
                disabled={!pagination.has_prev_page || pagination.current_page <= 1}
                onClick={() => handlePageChange(pagination.current_page - 1)}
                className="pagination-btn"
                style={{
                  padding: '4px 8px',
                  border: '1px solid #ddd',
                  background: pagination.has_prev_page && pagination.current_page > 1 ? '#fff' : '#f5f5f5',
                  cursor: pagination.has_prev_page && pagination.current_page > 1 ? 'pointer' : 'not-allowed',
                  borderRadius: '4px',
                  marginRight: '8px'
                }}
              >
                Previous
              </button>

              <div className="page-info-header" style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
                <input
                  type="number"
                  min="1"
                  max={pagination.total_pages}
                  value={pagination.current_page}
                  onChange={(e) => {
                    const page = parseInt(e.target.value);
                    if (page >= 1 && page <= pagination.total_pages) {
                      handlePageChange(page);
                    }
                  }}
                  className="page-input"
                  style={{
                    width: '50px',
                    padding: '4px 6px',
                    border: '1px solid #ddd',
                    borderRadius: '4px',
                    textAlign: 'center',
                    fontSize: '13px'
                  }}
                />
                <span style={{ fontSize: '13px', color: '#666' }}>of {pagination.total_pages}</span>
              </div>

              <button
                disabled={!pagination.has_next_page || pagination.current_page >= pagination.total_pages}
                onClick={() => handlePageChange(pagination.current_page + 1)}
                className="pagination-btn"
                style={{
                  padding: '4px 8px',
                  border: '1px solid #ddd',
                  background: pagination.has_next_page && pagination.current_page < pagination.total_pages ? '#fff' : '#f5f5f5',
                  cursor: pagination.has_next_page && pagination.current_page < pagination.total_pages ? 'pointer' : 'not-allowed',
                  borderRadius: '4px',
                  marginLeft: '8px'
                }}
              >
                Next
              </button>
            </div>
          </div>
        )}
      </div>

      {/* Enhanced Status Update Modal */}
      {showStatusModal && selectedOrder && (
        <div 
          className="modal-overlay" 
          style={{ 
            display: 'flex !important', 
            position: 'fixed', 
            top: 0,
            left: 0,
            right: 0,
            bottom: 0,
            zIndex: 999999,
            backgroundColor: 'rgba(0, 0, 0, 0.5)',
            alignItems: 'center',
            justifyContent: 'center',
            visibility: 'visible',
            opacity: 1
          }}
        >
          {console.log('🔴 MODAL IS RENDERING - showStatusModal:', showStatusModal, 'selectedOrder:', selectedOrder)}
          <div 
            className="enhanced-status-modal" 
            onClick={(e) => e.stopPropagation()} 
            style={{ 
              position: 'relative', 
              zIndex: 1000000,
              backgroundColor: 'white',
              borderRadius: '16px',
              maxWidth: '650px',
              width: '90%',
              maxHeight: '90vh',
              visibility: 'visible',
              opacity: 1,
              display: 'block'
            }}
          >
            {console.log('🔴 MODAL CONTENT IS RENDERING')}
            <div className="modal-header">
              <h3>Update Order Status - #{selectedOrder?.order_id || selectedOrder?.id || 'Unknown'}</h3>
              <button
                className="close-btn"
                onClick={(e) => {
                  e.stopPropagation();
                  setShowStatusModal(false);
                }}
              >
                ×
              </button>
            </div>

            <div className="modal-content">
              {error && (
                <div className="error-message" style={{ marginBottom: '20px', padding: '10px', backgroundColor: '#f8d7da', color: '#721c24', borderRadius: '5px' }}>
                  {error}
                  <button onClick={() => setError(null)} style={{ float: 'right', background: 'none', border: 'none', fontSize: '16px' }}>×</button>
                </div>
              )}

              {/* Order Summary */}
              <div className="order-summary-details">
                <div className="order-details-grid">
                  <div className="order-detail-item">
                    <div className="detail-label">Customer : </div>
                    <div className="detail-value customer-name">{selectedOrder.customer_name}</div>
                  </div>
                  <div className="order-detail-item">
                    <div className="detail-label">Amount : </div>
                    <div className="detail-value amount-value">₹{selectedOrder.total_amount}</div>
                  </div>
                  <div className="order-detail-item">
                    <div className="detail-label">Order ID : </div>
                    <div className="detail-value">#{selectedOrder.order_id}</div>
                  </div>
                  <div className="order-detail-item">
                    <div className="detail-label">Business : </div>
                    <div className="detail-value">{selectedOrder.business_name}</div>
                  </div>
                  <div className="order-detail-item">
                    <div className="detail-label">Order Type : </div>
                    <div className="detail-value">{selectedOrder.order_type}</div>
                  </div>
                  <div className="order-detail-item">
                    <div className="detail-label">Current Status : </div>
                    <div className="detail-value">
                      <span className="current-status-mini-badge">{getStatusDisplay(selectedOrder)}</span>
                    </div>
                  </div>
                </div>
              </div>

              {/* Order Status Section */}
              <div className="order-status-section">
                <h3>Order Status</h3>
                <div className="current-status-display">
                  <span className="current-status-badge">{getStatusDisplay(selectedOrder)}</span>
                </div>
                <div className="status-options-grid">
                  {statusOptions.map(status => (
                    <button
                      key={status}
                      className={`status-option ${selectedStatus === status ? 'selected' : ''} ${selectedOrder.status === status ? 'current' : ''}`}
                      onClick={() => handleStatusSelection(status)}
                      disabled={selectedOrder.status === status}
                    >
                      {status.replace('_', ' ')}
                    </button>
                  ))}
                </div>
              </div>

              {/* Available Delivery Partners Section */}
              {selectedStatus === 'assigned' && (
                <div className="delivery-partners-section">
                  <h3>Available Delivery Partners</h3>
                  {loadingPartners ? (
                    <div className="loading-state">
                      <div className="loading-spinner"></div>
                      <p>Loading delivery partners...</p>
                    </div>
                  ) : deliveryPartners.length === 0 ? (
                    <div className="no-partners">
                      <p>No available delivery partners found</p>
                    </div>
                  ) : (
                    <>
                      <div className="partners-list">
                        {deliveryPartners.map((partner) => (
                          <div
                            key={partner.provider_id}
                            className={`partner-card ${selectedDeliveryPartner?.provider_id === partner.provider_id ? 'selected' : ''}`}
                            onClick={() => setSelectedDeliveryPartner(partner)}
                          >
                            <div className="partner-info">
                              <div className="partner-name">
                                <span className="partner-label">Name:</span>
                                <span className="partner-value">{partner.name}</span>
                              </div>
                              <div className="partner-phone">
                                <span className="partner-label">Phone:</span>
                                <span className="partner-value">{partner.phone}</span>
                              </div>
                              <div className="partner-vehicle">
                                <span className="partner-label">Vehicle:</span>
                                <span className="partner-value">
                                  <FaMotorcycle className="vehicle-icon" />
                                  {partner.vehicle_type}
                                </span>
                              </div>
                            </div>
                            {selectedDeliveryPartner?.provider_id === partner.provider_id && (
                              <div className="selected-indicator">✓</div>
                            )}
                          </div>
                        ))}
                      </div>
                    </>
                  )}
                </div>
              )}

              {/* Assignment Warning */}
              {selectedStatus === 'assigned' && !selectedDeliveryPartner && (
                <div className="assignment-warning">
                  ⚠️ Please select a delivery partner to assign this order
                </div>
              )}

              {/* Action Buttons */}
              <div className="modal-actions">
                <button
                  className="cancel-btn"
                  onClick={() => setShowStatusModal(false)}
                  disabled={updatingStatus}
                >
                  Cancel
                </button>
                <button
                  className="update-btn"
                  onClick={handleStatusUpdate}
                  disabled={updatingStatus || !selectedStatus || (selectedStatus === 'assigned' && !selectedDeliveryPartner)}
                >
                  {updatingStatus ? 'Updating...' : selectedStatus === 'assigned' ? 'Assign Order' : 'Update Status'}
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Order Details Modal - Professional Redesign */}
      {showDetailsModal && selectedOrder && (
        <div 
          key={`details-modal-${selectedOrder.id || selectedOrder.order_id}`}
          className="modal-overlay order-details-overlay"
          onClick={(e) => {
            // Close only when clicking the overlay background, not the modal content
            // Also guard against immediate closing after opening (within 300ms)
            if (e.target === e.currentTarget) {
              const timeSinceOpen = Date.now() - modalOpenTimeRef.current;
              if (timeSinceOpen > 300) {
                console.log('Overlay clicked, closing modal');
                setShowDetailsModal(false);
              } else {
                console.log('Ignoring early overlay click, time since open:', timeSinceOpen);
              }
            }
          }}
          style={{ 
            display: 'flex !important', 
            position: 'fixed', 
            top: 0,
            left: 0,
            right: 0,
            bottom: 0,
            zIndex: 999999,
            backgroundColor: 'rgba(0, 0, 0, 0.6)',
            alignItems: 'center',
            justifyContent: 'center',
            padding: '20px',
            visibility: 'visible !important',
            opacity: 1
          }}
        >
          {(() => {
            try {
              return (
                <>
          {console.log('🔥 RENDERING DETAILS MODAL CONTENT')}
          <div
            className="order-details-modal"
            onClick={(e) => e.stopPropagation()}
            style={{ 
              backgroundColor: '#f8fafc',
              borderRadius: '20px',
              maxWidth: '900px',
              width: '100%',
              maxHeight: '90vh',
              overflow: 'hidden',
              display: 'flex !important',
              flexDirection: 'column',
              boxShadow: '0 25px 50px -12px rgba(0, 0, 0, 0.25)',
              visibility: 'visible !important',
              opacity: 1
            }}
          >
            {/* Modal Header */}
            <div style={{
              background: 'linear-gradient(135deg, #F55D00 0%, #FDBF50 100%)',
              padding: '24px 32px',
              color: 'white',
              display: 'flex',
              justifyContent: 'space-between',
              alignItems: 'center'
            }}>
              <div>
                <h2 style={{ margin: 0, fontSize: '24px', fontWeight: 700 }}>
                  Order #{selectedOrder.id || selectedOrder.order_id}
                </h2>
                <p style={{ margin: '4px 0 0 0', opacity: 0.9, fontSize: '14px' }}>
                  {selectedOrder.order_number?.slice(0, 16)}...
                </p>
              </div>
              <div style={{ display: 'flex', gap: '12px', alignItems: 'center' }}>
                <span style={{
                  background: 'rgba(255,255,255,0.2)',
                  padding: '6px 14px',
                  borderRadius: '20px',
                  fontSize: '13px',
                  fontWeight: 600,
                  textTransform: 'uppercase'
                }}>
                  {selectedOrder.order_type}
                </span>
                <button
                  onClick={() => setShowDetailsModal(false)}
                  style={{
                    background: 'rgba(255,255,255,0.2)',
                    border: 'none',
                    color: 'white',
                    width: '36px',
                    height: '36px',
                    borderRadius: '50%',
                    cursor: 'pointer',
                    fontSize: '20px',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center'
                  }}
                >
                  ×
                </button>
              </div>
            </div>

            {/* Scrollable Content */}
            <div style={{ 
              overflowY: 'auto', 
              flex: 1,
              padding: '24px 32px'
            }}>
              {/* Status Bar */}
              <div style={{
                background: 'white',
                borderRadius: '12px',
                padding: '16px 20px',
                marginBottom: '20px',
                display: 'flex',
                justifyContent: 'space-between',
                alignItems: 'center',
                boxShadow: '0 1px 3px rgba(0,0,0,0.1)'
              }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '16px' }}>
                  <div>
                    <span style={{ fontSize: '12px', color: '#64748b', textTransform: 'uppercase', fontWeight: 600 }}>
                      Order Status
                    </span>
                    <div style={{ marginTop: '4px' }}>
                      <span style={{
                        background: selectedOrder.status === 'delivered' ? '#dcfce7' : 
                                    selectedOrder.status === 'cancelled' ? '#fee2e2' : 
                                    selectedOrder.status === 'pending' ? '#fef3c7' : '#e0e7ff',
                        color: selectedOrder.status === 'delivered' ? '#166534' : 
                               selectedOrder.status === 'cancelled' ? '#991b1b' : 
                               selectedOrder.status === 'pending' ? '#92400e' : '#3730a3',
                        padding: '6px 16px',
                        borderRadius: '20px',
                        fontSize: '13px',
                        fontWeight: 600,
                        textTransform: 'uppercase'
                      }}>
                        {selectedOrder.status}
                      </span>
                    </div>
                  </div>
                  <div style={{ width: '1px', height: '40px', background: '#e2e8f0' }}></div>
                  <div>
                    <span style={{ fontSize: '12px', color: '#64748b', textTransform: 'uppercase', fontWeight: 600 }}>
                      Payment Status
                    </span>
                    <div style={{ marginTop: '4px' }}>
                      <span style={{
                        background: selectedOrder.payment_status === 'success' ? '#dcfce7' : 
                                    selectedOrder.payment_status === 'cancelled' ? '#fee2e2' : '#fef3c7',
                        color: selectedOrder.payment_status === 'success' ? '#166534' : 
                               selectedOrder.payment_status === 'cancelled' ? '#991b1b' : '#92400e',
                        padding: '6px 16px',
                        borderRadius: '20px',
                        fontSize: '13px',
                        fontWeight: 600,
                        textTransform: 'uppercase'
                      }}>
                        {selectedOrder.payment_status || 'PENDING'}
                      </span>
                    </div>
                  </div>
                </div>
                <div style={{ textAlign: 'right' }}>
                  <span style={{ fontSize: '12px', color: '#64748b' }}>Order Date</span>
                  <div style={{ fontSize: '14px', fontWeight: 600, color: '#1e293b' }}>
                    {formatDate(selectedOrder.created_at)}
                  </div>
                  <div style={{ fontSize: '12px', color: '#64748b' }}>
                    {formatTime(selectedOrder.created_at)}
                  </div>
                </div>
              </div>

              {/* Two Column Layout */}
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '20px', marginBottom: '20px' }}>
                {/* Customer Card */}
                <div style={{
                  background: 'white',
                  borderRadius: '16px',
                  padding: '20px',
                  boxShadow: '0 1px 3px rgba(0,0,0,0.1)'
                }}>
                  <h3 style={{ 
                    margin: '0 0 16px 0', 
                    fontSize: '16px', 
                    fontWeight: 700, 
                    color: '#1e293b',
                    display: 'flex',
                    alignItems: 'center',
                    gap: '8px'
                  }}>
                    Customer Details
                  </h3>
                  <div style={{ display: 'flex', gap: '16px', marginBottom: '16px' }}>
                    {selectedOrder.customer?.profile_image ? (
                      <img 
                        src={selectedOrder.customer.profile_image} 
                        alt="Customer"
                        style={{ width: '64px', height: '64px', borderRadius: '50%', objectFit: 'cover' }}
                      />
                    ) : (
                      <div style={{
                        width: '64px',
                        height: '64px',
                        borderRadius: '50%',
                        background: 'linear-gradient(135deg, #F55D00 0%, #FDBF50 100%)',
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'center',
                        color: 'white',
                        fontSize: '24px',
                        fontWeight: 600
                      }}>
                        {selectedOrder.customer_name?.charAt(0) || 'C'}
                      </div>
                    )}
                    <div>
                      <div style={{ fontSize: '18px', fontWeight: 700, color: '#1e293b' }}>
                        {selectedOrder.customer?.display_name || selectedOrder.customer_name}
                      </div>
                      <div style={{ fontSize: '14px', color: '#64748b', marginTop: '4px' }}>
                        ID: #{selectedOrder.customer?.id || selectedOrder.user_id}
                      </div>
                    </div>
                  </div>
                  <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
                      <div style={{ width: '32px', height: '32px', borderRadius: '8px', background: '#f1f5f9', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                        <span style={{ fontSize: '14px' }}>📱</span>
                      </div>
                      <div>
                        <div style={{ fontSize: '12px', color: '#64748b' }}>Phone</div>
                        <div style={{ fontSize: '14px', fontWeight: 600, color: '#1e293b' }}>
                          {selectedOrder.customer?.phone || selectedOrder.customer_phone || 'N/A'}
                        </div>
                      </div>
                    </div>
                    {selectedOrder.customer?.email && (
                      <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
                        <div style={{ width: '32px', height: '32px', borderRadius: '8px', background: '#f1f5f9', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                          <span style={{ fontSize: '14px' }}>✉️</span>
                        </div>
                        <div>
                          <div style={{ fontSize: '12px', color: '#64748b' }}>Email</div>
                          <div style={{ fontSize: '14px', fontWeight: 600, color: '#1e293b' }}>
                            {selectedOrder.customer.email}
                          </div>
                        </div>
                      </div>
                    )}
                  </div>
                </div>

                {/* Business Card */}
                <div style={{
                  background: 'white',
                  borderRadius: '16px',
                  padding: '20px',
                  boxShadow: '0 1px 3px rgba(0,0,0,0.1)'
                }}>
                  <h3 style={{ 
                    margin: '0 0 16px 0', 
                    fontSize: '16px', 
                    fontWeight: 700, 
                    color: '#1e293b',
                    display: 'flex',
                    alignItems: 'center',
                    gap: '8px'
                  }}>
                    Business Details
                  </h3>
                  <div style={{ marginBottom: '12px' }}>
                    <div style={{ fontSize: '18px', fontWeight: 700, color: '#1e293b' }}>
                      {selectedOrder.business_details?.business_name || selectedOrder.business_name}
                    </div>
                    <div style={{ fontSize: '13px', color: '#64748b', marginTop: '4px' }}>
                      ID: {selectedOrder.business_details?.business_id || selectedOrder.business_id}
                    </div>
                    <div style={{ fontSize: '12px', color: '#94a3b8', marginTop: '2px' }}>
                      Type: {selectedOrder.business_details?.business_type || 'N/A'}
                    </div>
                  </div>
                  <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
                    {selectedOrder.business_details?.address && (
                      <div style={{ display: 'flex', alignItems: 'flex-start', gap: '12px' }}>
                        <div style={{ width: '32px', height: '32px', borderRadius: '8px', background: '#f1f5f9', display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0 }}>
                          <span style={{ fontSize: '14px' }}>📍</span>
                        </div>
                        <div>
                          <div style={{ fontSize: '12px', color: '#64748b' }}>Address</div>
                          <div style={{ fontSize: '13px', color: '#1e293b', lineHeight: 1.4 }}>
                            {selectedOrder.business_details.address}
                            {selectedOrder.business_details.city && `, ${selectedOrder.business_details.city}`}
                            {selectedOrder.business_details.state && `, ${selectedOrder.business_details.state}`}
                            {selectedOrder.business_details.pincode && ` - ${selectedOrder.business_details.pincode}`}
                          </div>
                        </div>
                      </div>
                    )}
                    {(selectedOrder.business_contact?.business_number || selectedOrder.business_details?.business_number) && (
                      <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
                        <div style={{ width: '32px', height: '32px', borderRadius: '8px', background: '#f1f5f9', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                          <span style={{ fontSize: '14px' }}>📞</span>
                        </div>
                        <div>
                          <div style={{ fontSize: '12px', color: '#64748b' }}>Contact</div>
                          <div style={{ fontSize: '14px', fontWeight: 600, color: '#1e293b' }}>
                            {selectedOrder.business_contact?.business_number || selectedOrder.business_details?.business_number}
                          </div>
                        </div>
                      </div>
                    )}
                  </div>
                </div>
              </div>

              {/* Delivery Partner Card */}
              {selectedOrder.delivery_partner ? (
                <div style={{
                  background: 'white',
                  borderRadius: '16px',
                  padding: '20px',
                  marginBottom: '20px',
                  boxShadow: '0 1px 3px rgba(0,0,0,0.1)'
                }}>
                  <h3 style={{ 
                    margin: '0 0 16px 0', 
                    fontSize: '16px', 
                    fontWeight: 700, 
                    color: '#1e293b'
                  }}>
                    Delivery Partner
                  </h3>
                  <div style={{ display: 'flex', gap: '16px', alignItems: 'center' }}>
                    <div style={{
                      width: '56px',
                      height: '56px',
                      borderRadius: '50%',
                      background: '#f0fdf4',
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'center',
                      fontSize: '24px'
                    }}>
                      🚚
                    </div>
                    <div style={{ flex: 1 }}>
                      <div style={{ fontSize: '16px', fontWeight: 700, color: '#1e293b' }}>
                        {selectedOrder.delivery_partner.name}
                      </div>
                      <div style={{ fontSize: '14px', color: '#64748b', marginTop: '2px' }}>
                        {selectedOrder.delivery_partner.phone}
                      </div>
                    </div>
                    <div style={{ display: 'flex', gap: '8px' }}>
                      <a 
                        href={`tel:${selectedOrder.delivery_partner.phone}`}
                        style={{
                          padding: '10px 20px',
                          background: '#22c55e',
                          color: 'white',
                          borderRadius: '8px',
                          textDecoration: 'none',
                          fontSize: '14px',
                          fontWeight: 600
                        }}
                      >
                        Call Partner
                      </a>
                    </div>
                  </div>
                </div>
              ) : (
                selectedOrder.order_type === 'delivery' && (
                  <div style={{
                    background: '#fef3c7',
                    borderRadius: '16px',
                    padding: '16px 20px',
                    marginBottom: '20px',
                    display: 'flex',
                    alignItems: 'center',
                    gap: '12px'
                  }}>
                    <span style={{ fontSize: '20px' }}>⚠️</span>
                    <span style={{ fontSize: '14px', fontWeight: 600, color: '#92400e' }}>
                      Delivery partner not assigned yet
                    </span>
                  </div>
                )
              )}

              {/* Order Items Section */}
              {selectedOrder.items && selectedOrder.items.length > 0 && (
                <div style={{
                  background: 'white',
                  borderRadius: '16px',
                  padding: '20px',
                  marginBottom: '20px',
                  boxShadow: '0 1px 3px rgba(0,0,0,0.1)'
                }}>
                  <h3 style={{ 
                    margin: '0 0 16px 0', 
                    fontSize: '16px', 
                    fontWeight: 700, 
                    color: '#1e293b'
                  }}>
                    Order Items ({selectedOrder.items.length})
                  </h3>
                  <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
                    {selectedOrder.items.map((item, index) => (
                      <div 
                        key={index}
                        style={{
                          display: 'flex',
                          gap: '16px',
                          padding: '16px',
                          background: '#f8fafc',
                          borderRadius: '12px',
                          alignItems: 'center'
                        }}
                      >
                        {item.image ? (
                          <img 
                            src={item.image} 
                            alt={item.name}
                            style={{ width: '72px', height: '72px', borderRadius: '8px', objectFit: 'cover' }}
                          />
                        ) : (
                          <div style={{
                            width: '72px',
                            height: '72px',
                            borderRadius: '8px',
                            background: '#e2e8f0',
                            display: 'flex',
                            alignItems: 'center',
                            justifyContent: 'center',
                            fontSize: '24px'
                          }}>
                            📦
                          </div>
                        )}
                        <div style={{ flex: 1 }}>
                          <div style={{ fontSize: '15px', fontWeight: 600, color: '#1e293b', marginBottom: '4px' }}>
                            {item.name}
                          </div>
                          {item.category && (
                            <div style={{ fontSize: '12px', color: '#64748b', marginBottom: '4px' }}>
                              {item.category}
                            </div>
                          )}
                          <div style={{ display: 'flex', gap: '16px', fontSize: '13px', color: '#64748b' }}>
                            <span>Qty: <strong style={{ color: '#1e293b' }}>{item.quantity}</strong></span>
                            <span>Unit: <strong style={{ color: '#1e293b' }}>₹{item.unit_price?.toFixed(2)}</strong></span>
                          </div>
                        </div>
                        <div style={{ textAlign: 'right' }}>
                          <div style={{ fontSize: '18px', fontWeight: 700, color: '#F55D00' }}>
                            ₹{item.total_price?.toFixed(2)}
                          </div>
                          {item.tax_amount > 0 && (
                            <div style={{ fontSize: '11px', color: '#64748b' }}>
                              Incl. ₹{item.tax_amount?.toFixed(2)} tax
                            </div>
                          )}
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* Order Summary */}
              {(selectedOrder.summary || selectedOrder.total_amount) && (
                <div style={{
                  background: 'white',
                  borderRadius: '16px',
                  padding: '20px',
                  boxShadow: '0 1px 3px rgba(0,0,0,0.1)'
                }}>
                  <h3 style={{ 
                    margin: '0 0 16px 0', 
                    fontSize: '16px', 
                    fontWeight: 700, 
                    color: '#1e293b'
                  }}>
                    Order Summary
                  </h3>
                  <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
                    {(selectedOrder.summary?.subtotal || selectedOrder.total_amount) && (
                      <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '14px' }}>
                        <span style={{ color: '#64748b' }}>Subtotal</span>
                        <span style={{ fontWeight: 600, color: '#1e293b' }}>
                          ₹{(selectedOrder.summary?.subtotal || selectedOrder.total_amount)?.toFixed(2)}
                        </span>
                      </div>
                    )}
                    {selectedOrder.summary?.delivery_charges > 0 && (
                      <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '14px' }}>
                        <span style={{ color: '#64748b' }}>Delivery Charges</span>
                        <span style={{ fontWeight: 600, color: '#1e293b' }}>
                          ₹{selectedOrder.summary.delivery_charges?.toFixed(2)}
                        </span>
                      </div>
                    )}
                    {selectedOrder.summary?.parcel_charges > 0 && (
                      <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '14px' }}>
                        <span style={{ color: '#64748b' }}>Parcel Charges</span>
                        <span style={{ fontWeight: 600, color: '#1e293b' }}>
                          ₹{selectedOrder.summary.parcel_charges?.toFixed(2)}
                        </span>
                      </div>
                    )}
                    {selectedOrder.summary?.tax > 0 && (
                      <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '14px' }}>
                        <span style={{ color: '#64748b' }}>Tax</span>
                        <span style={{ fontWeight: 600, color: '#1e293b' }}>
                          ₹{selectedOrder.summary.tax?.toFixed(2)}
                        </span>
                      </div>
                    )}
                    <div style={{ height: '1px', background: '#e2e8f0', margin: '8px 0' }}></div>
                    <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                      <span style={{ fontSize: '16px', fontWeight: 700, color: '#1e293b' }}>Total Amount</span>
                      <span style={{ fontSize: '20px', fontWeight: 700, color: '#F55D00' }}>
                        ₹{(selectedOrder.summary?.total || selectedOrder.final_amount)?.toFixed(2)}
                      </span>
                    </div>
                  </div>
                </div>
              )}
            </div>

            {/* Modal Footer Actions */}
            <div style={{
              padding: '20px 32px',
              borderTop: '1px solid #e2e8f0',
              background: 'white',
              display: 'flex',
              justifyContent: 'space-between',
              alignItems: 'center',
              borderRadius: '0 0 20px 20px'
            }}>
              <div style={{ display: 'flex', gap: '12px' }}>
                <button
                  onClick={() => navigator.clipboard.writeText(selectedOrder.order_number)}
                  style={{
                    padding: '10px 20px',
                    background: '#f1f5f9',
                    color: '#475569',
                    border: 'none',
                    borderRadius: '8px',
                    fontSize: '14px',
                    fontWeight: 600,
                    cursor: 'pointer'
                  }}
                >
                  Copy Order ID
                </button>
                <button
                  onClick={() => {
                    setShowDetailsModal(false);
                    handleOpenStatusModal(selectedOrder);
                  }}
                  style={{
                    padding: '10px 20px',
                    background: '#f1f5f9',
                    color: '#475569',
                    border: 'none',
                    borderRadius: '8px',
                    fontSize: '14px',
                    fontWeight: 600,
                    cursor: 'pointer'
                  }}
                >
                  Update Status
                </button>
              </div>
              <button
                onClick={() => setShowDetailsModal(false)}
                style={{
                  padding: '10px 24px',
                  background: 'linear-gradient(135deg, #F55D00 0%, #FDBF50 100%)',
                  color: 'white',
                  border: 'none',
                  borderRadius: '8px',
                  fontSize: '14px',
                  fontWeight: 600,
                  cursor: 'pointer'
                }}
              >
                Close
              </button>
            </div>
          </div>
                </>
              );
            } catch (renderError) {
              console.error('Modal rendering error:', renderError);
              return (
                <div style={{ 
                  background: 'white', 
                  padding: '40px', 
                  borderRadius: '16px',
                  maxWidth: '500px',
                  textAlign: 'center'
                }}>
                  <h3>Error displaying order details</h3>
                  <p>There was a problem loading the order information.</p>
                  <button 
                    onClick={() => setShowDetailsModal(false)}
                    style={{
                      padding: '10px 20px',
                      background: '#667eea',
                      color: 'white',
                      border: 'none',
                      borderRadius: '8px',
                      cursor: 'pointer'
                    }}
                  >
                    Close
                  </button>
                </div>
              );
            }
          })()}
        </div>
      )}
    </div>
  );
};

export default OrderManagement;
