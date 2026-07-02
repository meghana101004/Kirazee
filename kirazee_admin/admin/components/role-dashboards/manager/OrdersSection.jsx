import React, { useState, useEffect } from 'react';
import AdminService from '../../../services/adminService';
import { FaBox, FaSearch, FaFilter, FaTruck, FaEye, FaSpinner, FaCheckCircle, FaClock, FaTimes } from 'react-icons/fa';
import { MdRefresh } from 'react-icons/md';

const OrdersSection = () => {
  const [orders, setOrders] = useState([]);
  const [filteredOrders, setFilteredOrders] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [searchQuery, setSearchQuery] = useState('');
  const [statusFilter, setStatusFilter] = useState('all');
  const [selectedOrder, setSelectedOrder] = useState(null);
  const [showOrderDetails, setShowOrderDetails] = useState(false);
  const [deliveryPartners, setDeliveryPartners] = useState([]);
  const [showAssignModal, setShowAssignModal] = useState(false);
  const [assigningOrder, setAssigningOrder] = useState(null);

  useEffect(() => {
    fetchOrders();
    fetchDeliveryPartners();
  }, []);

  useEffect(() => {
    filterOrders();
  }, [orders, searchQuery, statusFilter]);

  const fetchOrders = async () => {
    try {
      setLoading(true);
      setError(null);
      
      const response = await AdminService.getAllOrders({ limit: 100 });
      
      if (response && response.success) {
        setOrders(response.orders || []);
      } else {
        throw new Error(response.message || 'Failed to fetch orders');
      }
    } catch (error) {
      console.error('Error fetching orders:', error);
      setError('Failed to load orders');
    } finally {
      setLoading(false);
    }
  };

  const fetchDeliveryPartners = async () => {
    try {
      const response = await AdminService.getAllDeliveryProviders({ limit: 50 });
      if (response && response.success) {
        setDeliveryPartners(response.providers || []);
      }
    } catch (error) {
      console.error('Error fetching delivery partners:', error);
    }
  };

  const filterOrders = () => {
    let filtered = [...orders];

    // Filter by status
    if (statusFilter !== 'all') {
      filtered = filtered.filter(order => {
        const status = (order.status || '').toLowerCase();
        if (statusFilter === 'pending') {
          return ['pending', 'confirmed', 'preparing'].includes(status);
        } else if (statusFilter === 'delivered') {
          return ['delivered', 'completed'].includes(status);
        } else if (statusFilter === 'cancelled') {
          return status === 'cancelled';
        }
        return true;
      });
    }

    // Filter by search query
    if (searchQuery) {
      const query = searchQuery.toLowerCase();
      filtered = filtered.filter(order => 
        (order.order_id || '').toString().toLowerCase().includes(query) ||
        (order.business_name || '').toLowerCase().includes(query) ||
        (order.customer_name || '').toLowerCase().includes(query)
      );
    }

    setFilteredOrders(filtered);
  };

  const handleAssignDelivery = async (orderId, partnerId) => {
    try {
      const response = await AdminService.assignDeliveryPartner(orderId, partnerId);
      if (response && response.success) {
        alert('Delivery partner assigned successfully!');
        fetchOrders();
        setShowAssignModal(false);
        setAssigningOrder(null);
      } else {
        throw new Error(response.message || 'Failed to assign delivery partner');
      }
    } catch (error) {
      console.error('Error assigning delivery partner:', error);
      alert('Failed to assign delivery partner: ' + error.message);
    }
  };

  const handleUpdateStatus = async (orderId, newStatus) => {
    try {
      const response = await AdminService.updateOrderStatus(orderId, newStatus);
      if (response && response.success) {
        alert('Order status updated successfully!');
        fetchOrders();
      } else {
        throw new Error(response.message || 'Failed to update order status');
      }
    } catch (error) {
      console.error('Error updating order status:', error);
      alert('Failed to update order status: ' + error.message);
    }
  };

  const getStatusIcon = (status) => {
    const statusLower = (status || '').toLowerCase();
    if (['delivered', 'completed'].includes(statusLower)) return <FaCheckCircle />;
    if (statusLower === 'cancelled') return <FaTimes />;
    return <FaClock />;
  };

  const getStatusClass = (status) => {
    const statusLower = (status || '').toLowerCase();
    if (['delivered', 'completed'].includes(statusLower)) return 'status-delivered';
    if (statusLower === 'cancelled') return 'status-cancelled';
    if (['pending', 'confirmed'].includes(statusLower)) return 'status-pending';
    return 'status-processing';
  };

  const formatCurrency = (amount) => {
    return new Intl.NumberFormat('en-IN', {
      style: 'currency',
      currency: 'INR',
      maximumFractionDigits: 0
    }).format(amount || 0);
  };

  const formatDate = (dateString) => {
    if (!dateString) return 'N/A';
    return new Date(dateString).toLocaleString('en-IN', {
      day: '2-digit',
      month: 'short',
      year: 'numeric',
      hour: '2-digit',
      minute: '2-digit'
    });
  };

  if (loading) {
    return (
      <div className="orders-loading">
        <FaSpinner className="loading-spinner" />
        <p>Loading orders...</p>
      </div>
    );
  }

  if (error) {
    return (
      <div className="orders-error">
        <p>{error}</p>
        <button onClick={fetchOrders} className="retry-btn">
          <MdRefresh /> Retry
        </button>
      </div>
    );
  }

  return (
    <div className="orders-section">
      {/* Header */}
      <div className="orders-header">
        <div className="header-left">
          <h2>
            <FaBox /> Orders Management
          </h2>
          <p>{filteredOrders.length} orders found</p>
        </div>
        <button onClick={fetchOrders} className="refresh-btn">
          <MdRefresh /> Refresh
        </button>
      </div>

      {/* Filters */}
      <div className="orders-filters">
        <div className="search-box">
          <FaSearch />
          <input
            type="text"
            placeholder="Search by order ID, business, or customer..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
          />
        </div>

        <div className="status-filters">
          <button
            className={`filter-btn ${statusFilter === 'all' ? 'active' : ''}`}
            onClick={() => setStatusFilter('all')}
          >
            All Orders
          </button>
          <button
            className={`filter-btn ${statusFilter === 'pending' ? 'active' : ''}`}
            onClick={() => setStatusFilter('pending')}
          >
            <FaClock /> Pending
          </button>
          <button
            className={`filter-btn ${statusFilter === 'delivered' ? 'active' : ''}`}
            onClick={() => setStatusFilter('delivered')}
          >
            <FaCheckCircle /> Delivered
          </button>
          <button
            className={`filter-btn ${statusFilter === 'cancelled' ? 'active' : ''}`}
            onClick={() => setStatusFilter('cancelled')}
          >
            <FaTimes /> Cancelled
          </button>
        </div>
      </div>

      {/* Orders Table */}
      <div className="orders-table-container">
        <table className="orders-table">
          <thead>
            <tr>
              <th>Order ID</th>
              <th>Business</th>
              <th>Customer</th>
              <th>Amount</th>
              <th>Status</th>
              <th>Date</th>
              <th>Delivery Partner</th>
              <th>Actions</th>
            </tr>
          </thead>
          <tbody>
            {filteredOrders.length === 0 ? (
              <tr>
                <td colSpan="8" className="no-orders">
                  No orders found
                </td>
              </tr>
            ) : (
              filteredOrders.map((order) => (
                <tr key={order.order_id || order.id}>
                  <td className="order-id">#{order.order_id || order.id}</td>
                  <td>{order.business_name || 'N/A'}</td>
                  <td>{order.customer_name || order.user_name || 'N/A'}</td>
                  <td className="amount">{formatCurrency(order.total_amount || order.amount)}</td>
                  <td>
                    <span className={`status-badge ${getStatusClass(order.status)}`}>
                      {getStatusIcon(order.status)}
                      {order.status || 'Unknown'}
                    </span>
                  </td>
                  <td className="date">{formatDate(order.created_at || order.order_date)}</td>
                  <td>
                    {order.delivery_partner_name || (
                      <button
                        className="assign-btn"
                        onClick={() => {
                          setAssigningOrder(order);
                          setShowAssignModal(true);
                        }}
                      >
                        <FaTruck /> Assign
                      </button>
                    )}
                  </td>
                  <td>
                    <div className="action-buttons">
                      <button
                        className="action-btn view-btn"
                        onClick={() => {
                          setSelectedOrder(order);
                          setShowOrderDetails(true);
                        }}
                        title="View Details"
                      >
                        <FaEye />
                      </button>
                      {!['delivered', 'completed', 'cancelled'].includes((order.status || '').toLowerCase()) && (
                        <button
                          className="action-btn track-btn"
                          onClick={() => alert(`Tracking order #${order.order_id || order.id}`)}
                          title="Track Order"
                        >
                          <FaTruck />
                        </button>
                      )}
                    </div>
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      {/* Order Details Modal */}
      {showOrderDetails && selectedOrder && (
        <div className="modal-overlay" onClick={() => setShowOrderDetails(false)}>
          <div className="modal-content order-details-modal" onClick={(e) => e.stopPropagation()}>
            <div className="modal-header">
              <h3>Order Details - #{selectedOrder.order_id || selectedOrder.id}</h3>
              <button className="close-btn" onClick={() => setShowOrderDetails(false)}>
                <FaTimes />
              </button>
            </div>
            <div className="modal-body">
              <div className="detail-section">
                <h4>Order Information</h4>
                <div className="detail-grid">
                  <div className="detail-item">
                    <span className="label">Order ID:</span>
                    <span className="value">#{selectedOrder.order_id || selectedOrder.id}</span>
                  </div>
                  <div className="detail-item">
                    <span className="label">Status:</span>
                    <span className={`value status-badge ${getStatusClass(selectedOrder.status)}`}>
                      {selectedOrder.status}
                    </span>
                  </div>
                  <div className="detail-item">
                    <span className="label">Amount:</span>
                    <span className="value">{formatCurrency(selectedOrder.total_amount || selectedOrder.amount)}</span>
                  </div>
                  <div className="detail-item">
                    <span className="label">Date:</span>
                    <span className="value">{formatDate(selectedOrder.created_at || selectedOrder.order_date)}</span>
                  </div>
                </div>
              </div>

              <div className="detail-section">
                <h4>Business Details</h4>
                <div className="detail-grid">
                  <div className="detail-item">
                    <span className="label">Business Name:</span>
                    <span className="value">{selectedOrder.business_name || 'N/A'}</span>
                  </div>
                  <div className="detail-item">
                    <span className="label">Business Phone:</span>
                    <span className="value">{selectedOrder.business_phone || 'N/A'}</span>
                  </div>
                </div>
              </div>

              <div className="detail-section">
                <h4>Customer Details</h4>
                <div className="detail-grid">
                  <div className="detail-item">
                    <span className="label">Customer Name:</span>
                    <span className="value">{selectedOrder.customer_name || selectedOrder.user_name || 'N/A'}</span>
                  </div>
                  <div className="detail-item">
                    <span className="label">Customer Phone:</span>
                    <span className="value">{selectedOrder.customer_phone || selectedOrder.user_phone || 'N/A'}</span>
                  </div>
                  <div className="detail-item full-width">
                    <span className="label">Delivery Address:</span>
                    <span className="value">{selectedOrder.delivery_address || 'N/A'}</span>
                  </div>
                </div>
              </div>

              {selectedOrder.delivery_partner_name && (
                <div className="detail-section">
                  <h4>Delivery Partner</h4>
                  <div className="detail-grid">
                    <div className="detail-item">
                      <span className="label">Partner Name:</span>
                      <span className="value">{selectedOrder.delivery_partner_name}</span>
                    </div>
                    <div className="detail-item">
                      <span className="label">Partner Phone:</span>
                      <span className="value">{selectedOrder.delivery_partner_phone || 'N/A'}</span>
                    </div>
                  </div>
                </div>
              )}

              <div className="detail-actions">
                {!['delivered', 'completed', 'cancelled'].includes((selectedOrder.status || '').toLowerCase()) && (
                  <>
                    <button
                      className="action-btn-large primary"
                      onClick={() => handleUpdateStatus(selectedOrder.order_id || selectedOrder.id, 'delivered')}
                    >
                      Mark as Delivered
                    </button>
                    <button
                      className="action-btn-large danger"
                      onClick={() => handleUpdateStatus(selectedOrder.order_id || selectedOrder.id, 'cancelled')}
                    >
                      Cancel Order
                    </button>
                  </>
                )}
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Assign Delivery Partner Modal */}
      {showAssignModal && assigningOrder && (
        <div className="modal-overlay" onClick={() => setShowAssignModal(false)}>
          <div className="modal-content assign-modal" onClick={(e) => e.stopPropagation()}>
            <div className="modal-header">
              <h3>Assign Delivery Partner</h3>
              <button className="close-btn" onClick={() => setShowAssignModal(false)}>
                <FaTimes />
              </button>
            </div>
            <div className="modal-body">
              <p>Select a delivery partner for Order #{assigningOrder.order_id || assigningOrder.id}</p>
              <div className="partners-list">
                {deliveryPartners.filter(p => p.status === 'Available').length === 0 ? (
                  <p className="no-partners">No available delivery partners</p>
                ) : (
                  deliveryPartners
                    .filter(p => p.status === 'Available')
                    .map((partner) => (
                      <div key={partner.id} className="partner-item">
                        <div className="partner-info">
                          <span className="partner-name">{partner.name || 'Unknown'}</span>
                          <span className="partner-phone">{partner.phone || 'N/A'}</span>
                          <span className="partner-vehicle">{partner.vehicle_type || 'N/A'}</span>
                        </div>
                        <button
                          className="assign-partner-btn"
                          onClick={() => handleAssignDelivery(assigningOrder.order_id || assigningOrder.id, partner.id)}
                        >
                          Assign
                        </button>
                      </div>
                    ))
                )}
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default OrdersSection;
