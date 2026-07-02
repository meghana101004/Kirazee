import { useState, useEffect } from 'react';
import AdminService from '../../../services/adminService';
import { 
  FaUsers, FaSearch, FaEye, FaSpinner, 
  FaUserCircle, FaShoppingCart, FaMapMarkerAlt, FaPhone, 
  FaEnvelope, FaCalendar, FaCheckCircle, FaBan, FaClock
} from 'react-icons/fa';
import { MdRefresh } from 'react-icons/md';

const CustomersSection = () => {
  const [customers, setCustomers] = useState([]);
  const [filteredCustomers, setFilteredCustomers] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [searchQuery, setSearchQuery] = useState('');
  const [statusFilter, setStatusFilter] = useState('all');
  const [selectedCustomer, setSelectedCustomer] = useState(null);
  const [showCustomerDetails, setShowCustomerDetails] = useState(false);
  const [customerOrders, setCustomerOrders] = useState([]);
  const [loadingOrders, setLoadingOrders] = useState(false);
  const [pagination, setPagination] = useState({
    currentPage: 1,
    totalPages: 1,
    pageSize: 20
  });

  useEffect(() => {
    fetchCustomers();
  }, [pagination.currentPage]);

  useEffect(() => {
    filterCustomers();
  }, [customers, searchQuery, statusFilter]);

  const fetchCustomers = async () => {
    try {
      setLoading(true);
      setError(null);
      
      // Get customers from dashboard summary API
      const summaryResponse = await AdminService.getDashboardSummary();
      
      if (summaryResponse && summaryResponse.success && summaryResponse.user_analytics) {
        const customersList = summaryResponse.user_analytics.unique_customers_details || [];
        
        // Get all orders to calculate customer statistics
        const ordersResponse = await AdminService.getAllOrders({ limit: 10000 });
        const allOrders = ordersResponse?.orders || [];
        
        // Calculate order statistics per customer
        const customerStats = {};
        allOrders.forEach(order => {
          const userId = order.user_id;
          
          if (userId) {
            if (!customerStats[userId]) {
              customerStats[userId] = {
                total_orders: 0,
                total_spent: 0
              };
            }
            customerStats[userId].total_orders += 1;
            
            // Use final_amount if available, otherwise total_amount
            const amount = parseFloat(order.final_amount || order.total_amount || 0);
            customerStats[userId].total_spent += amount;
          }
        });
        
        // Transform customer data with calculated statistics
        const transformedCustomers = customersList.map(customer => ({
          id: customer.user_id,
          user_id: customer.user_id,
          name: customer.name,
          email: customer.email,
          phone: customer.mobile,
          is_active: customer.is_active === 'Active',
          status: customer.is_active === 'Active' ? 'active' : 'inactive',
          last_order_date: customer.last_order_date,
          created_at: customer.registration_date || customer.created_at,
          total_orders: customerStats[customer.user_id]?.total_orders || 0,
          total_spent: customerStats[customer.user_id]?.total_spent || 0
        }));
        
        setCustomers(transformedCustomers);
        setPagination(prev => ({
          ...prev,
          totalPages: Math.ceil(transformedCustomers.length / pagination.pageSize),
          total: transformedCustomers.length
        }));
      } else {
        throw new Error('Failed to fetch customers from dashboard');
      }
    } catch (error) {
      console.error('Error fetching customers:', error);
      setError('Failed to load customers. Please try again.');
    } finally {
      setLoading(false);
    }
  };

  const filterCustomers = () => {
    let filtered = [...customers];

    // Filter by status
    if (statusFilter !== 'all') {
      filtered = filtered.filter(customer => {
        const status = (customer.status || customer.is_active ? 'active' : 'inactive').toLowerCase();
        return status === statusFilter;
      });
    }

    // Filter by search query
    if (searchQuery) {
      const query = searchQuery.toLowerCase();
      filtered = filtered.filter(customer => 
        (customer.name || customer.user_name || customer.username || '').toLowerCase().includes(query) ||
        (customer.email || '').toLowerCase().includes(query) ||
        (customer.phone || customer.phone_number || '').toLowerCase().includes(query) ||
        (customer.city || customer.location || '').toLowerCase().includes(query)
      );
    }

    setFilteredCustomers(filtered);
  };

  const handleViewCustomer = async (customer) => {
    setSelectedCustomer(customer);
    setShowCustomerDetails(true);
    setLoadingOrders(true);
    
    try {
      // Fetch customer orders to get accurate statistics
      const ordersResponse = await AdminService.getCustomerOrders(customer.id || customer.user_id);
      
      if (ordersResponse && ordersResponse.success) {
        const orders = ordersResponse.orders || [];
        setCustomerOrders(orders);
        
        // Update selected customer with calculated statistics
        setSelectedCustomer(prev => ({
          ...prev,
          total_orders: orders.length,
          total_spent: orders.reduce((sum, order) => 
            sum + (parseFloat(order.total_amount || order.final_amount || 0)), 0
          )
        }));
      } else {
        setCustomerOrders([]);
      }
    } catch (error) {
      console.error('Error fetching customer orders:', error);
      setCustomerOrders([]);
    } finally {
      setLoadingOrders(false);
    }
  };

  const handleUpdateStatus = async (customerId, newStatus) => {
    try {
      const response = await AdminService.updateCustomerStatus(customerId, newStatus);
      if (response && response.success) {
        alert('Customer status updated successfully!');
        fetchCustomers();
        setShowCustomerDetails(false);
      } else {
        throw new Error(response.message || 'Failed to update customer status');
      }
    } catch (error) {
      console.error('Error updating customer status:', error);
      alert('Failed to update customer status: ' + error.message);
    }
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
    return new Date(dateString).toLocaleDateString('en-IN', {
      day: '2-digit',
      month: 'short',
      year: 'numeric'
    });
  };

  const getStatusBadge = (customer) => {
    const isActive = customer.status === 'active' || customer.is_active;
    return {
      label: isActive ? 'Active' : 'Inactive',
      class: isActive ? 'status-active' : 'status-inactive',
      icon: isActive ? <FaCheckCircle /> : <FaBan />
    };
  };

  if (loading) {
    return (
      <div className="customers-loading">
        <FaSpinner className="loading-spinner" />
        <p>Loading customers...</p>
      </div>
    );
  }

  if (error) {
    return (
      <div className="customers-error">
        <p>{error}</p>
        <button onClick={fetchCustomers} className="retry-btn">
          <MdRefresh /> Retry
        </button>
      </div>
    );
  }

  return (
    <div className="customers-section">
      {/* Header */}
      <div className="customers-header">
        <div className="header-left">
          <h2>
            <FaUsers /> Customers Management
          </h2>
          <p>{filteredCustomers.length} customers found</p>
        </div>
        <button onClick={fetchCustomers} className="refresh-btn">
          <MdRefresh /> Refresh
        </button>
      </div>

      {/* Filters */}
      <div className="customers-filters">
        <div className="search-box">
          <FaSearch />
          <input
            type="text"
            placeholder="Search by name, email, phone, or location..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
          />
        </div>

        <div className="status-filters">
          <button
            className={`filter-btn ${statusFilter === 'all' ? 'active' : ''}`}
            onClick={() => setStatusFilter('all')}
          >
            All Customers
          </button>
          <button
            className={`filter-btn ${statusFilter === 'active' ? 'active' : ''}`}
            onClick={() => setStatusFilter('active')}
          >
            <FaCheckCircle /> Active
          </button>
          <button
            className={`filter-btn ${statusFilter === 'inactive' ? 'active' : ''}`}
            onClick={() => setStatusFilter('inactive')}
          >
            <FaBan /> Inactive
          </button>
        </div>
      </div>

      {/* Customers Table */}
      <div className="customers-table-container">
        <table className="customers-table">
          <thead>
            <tr>
              <th>Customer</th>
              <th>Email</th>
              <th>Phone</th>
              <th>Total Orders</th>
              <th>Total Spent</th>
              <th>Last Order Date</th>
              <th>Status</th>
              <th>Actions</th>
            </tr>
          </thead>
          <tbody>
            {filteredCustomers.length === 0 ? (
              <tr>
                <td colSpan="8" className="no-customers">
                  No customers found
                </td>
              </tr>
            ) : (
              filteredCustomers.map((customer) => {
                const statusBadge = getStatusBadge(customer);
                return (
                  <tr key={customer.id || customer.user_id}>
                    <td className="customer-name">
                      <div className="customer-avatar">
                        <FaUserCircle />
                      </div>
                      <span>{customer.name || customer.user_name || customer.username || 'N/A'}</span>
                    </td>
                    <td>{customer.email || 'N/A'}</td>
                    <td>{customer.phone || customer.phone_number || 'N/A'}</td>
                    <td className="text-center">{customer.total_orders || 0}</td>
                    <td className="amount">{formatCurrency(customer.total_spent || 0)}</td>
                    <td className="date">{formatDate(customer.last_order_date || customer.last_order)}</td>
                    <td>
                      <span className={`status-badge ${statusBadge.class}`}>
                        {statusBadge.icon}
                        {statusBadge.label}
                      </span>
                    </td>
                    <td>
                      <button
                        className="action-btn view-btn"
                        onClick={() => handleViewCustomer(customer)}
                        title="View Details"
                      >
                        <FaEye />
                      </button>
                    </td>
                  </tr>
                );
              })
            )}
          </tbody>
        </table>
      </div>

      {/* Pagination */}
      {pagination.totalPages > 1 && (
        <div className="pagination">
          <button
            className="page-btn"
            disabled={pagination.currentPage === 1}
            onClick={() => setPagination(prev => ({ ...prev, currentPage: prev.currentPage - 1 }))}
          >
            Previous
          </button>
          
          <span className="page-info">
            Page {pagination.currentPage} of {pagination.totalPages}
          </span>
          
          <button
            className="page-btn"
            disabled={pagination.currentPage === pagination.totalPages}
            onClick={() => setPagination(prev => ({ ...prev, currentPage: prev.currentPage + 1 }))}
          >
            Next
          </button>
        </div>
      )}

      {/* Customer Details Modal */}
      {showCustomerDetails && selectedCustomer && (
        <div className="modal-overlay" onClick={() => setShowCustomerDetails(false)}>
          <div className="modal-content customer-details-modal" onClick={(e) => e.stopPropagation()}>
            <div className="modal-header">
              <h3>Customer Details</h3>
              <button className="close-btn" onClick={() => setShowCustomerDetails(false)}>
                ×
              </button>
            </div>
            <div className="modal-body">
              {/* Customer Info */}
              <div className="customer-detail-header">
                <div className="customer-avatar-large">
                  <FaUserCircle />
                </div>
                <div className="customer-basic-info">
                  <h2>{selectedCustomer.name || selectedCustomer.user_name || selectedCustomer.username}</h2>
                  <span className={`status-badge ${getStatusBadge(selectedCustomer).class}`}>
                    {getStatusBadge(selectedCustomer).icon}
                    {getStatusBadge(selectedCustomer).label}
                  </span>
                </div>
              </div>

              {/* Contact Information */}
              <div className="detail-section">
                <h4>Contact Information</h4>
                <div className="detail-grid">
                  <div className="detail-item">
                    <FaEnvelope className="detail-icon" />
                    <div>
                      <span className="label">Email</span>
                      <span className="value">{selectedCustomer.email || 'N/A'}</span>
                    </div>
                  </div>
                  <div className="detail-item">
                    <FaPhone className="detail-icon" />
                    <div>
                      <span className="label">Phone</span>
                      <span className="value">{selectedCustomer.phone || selectedCustomer.phone_number || 'N/A'}</span>
                    </div>
                  </div>
                  <div className="detail-item">
                    <FaMapMarkerAlt className="detail-icon" />
                    <div>
                      <span className="label">Address</span>
                      <span className="value">{selectedCustomer.address || selectedCustomer.delivery_address || 'N/A'}</span>
                    </div>
                  </div>
                  <div className="detail-item">
                    <FaCalendar className="detail-icon" />
                    <div>
                      <span className="label">Last Order Date</span>
                      <span className="value">{formatDate(selectedCustomer.last_order_date || selectedCustomer.last_order)}</span>
                    </div>
                  </div>
                  <div className="detail-item">
                    <FaUserCircle className="detail-icon" />
                    <div>
                      <span className="label">Customer ID</span>
                      <span className="value">#{selectedCustomer.id || selectedCustomer.user_id || 'N/A'}</span>
                    </div>
                  </div>
                </div>
              </div>

              {/* Order Statistics */}
              <div className="detail-section">
                <h4>Order Statistics</h4>
                <div className="stats-grid">
                  <div className="stat-card">
                    <FaShoppingCart className="stat-icon" />
                    <div className="stat-info">
                      <span className="stat-value">{selectedCustomer.total_orders || customerOrders.length || 0}</span>
                      <span className="stat-label">Total Orders</span>
                    </div>
                  </div>
                  <div className="stat-card">
                    <FaCheckCircle className="stat-icon success" />
                    <div className="stat-info">
                      <span className="stat-value">
                        {customerOrders.filter(o => ['delivered', 'completed'].includes(o.status?.toLowerCase())).length}
                      </span>
                      <span className="stat-label">Completed Orders</span>
                    </div>
                  </div>
                  <div className="stat-card">
                    <FaClock className="stat-icon warning" />
                    <div className="stat-info">
                      <span className="stat-value">
                        {customerOrders.filter(o => !['delivered', 'completed', 'cancelled'].includes(o.status?.toLowerCase())).length}
                      </span>
                      <span className="stat-label">Active Orders</span>
                    </div>
                  </div>
                  <div className="stat-card">
                    <span className="stat-icon currency">₹</span>
                    <div className="stat-info">
                      <span className="stat-value">{formatCurrency(selectedCustomer.total_spent || 0)}</span>
                      <span className="stat-label">Total Spent</span>
                    </div>
                  </div>
                </div>
              </div>

              {/* Recent Orders */}
              <div className="detail-section">
                <h4>Recent Orders</h4>
                {loadingOrders ? (
                  <div className="loading-orders">
                    <FaSpinner className="loading-spinner" />
                    <p>Loading orders...</p>
                  </div>
                ) : customerOrders.length === 0 ? (
                  <p className="no-data">No orders found</p>
                ) : (
                  <div className="orders-list">
                    {customerOrders.slice(0, 5).map((order, index) => (
                      <div key={index} className="order-item">
                        <div className="order-info">
                          <span className="order-id">#{order.order_id || order.id}</span>
                          <span className="order-date">{formatDate(order.created_at || order.order_date)}</span>
                        </div>
                        <div className="order-details">
                          <span className="order-amount">{formatCurrency(order.total_amount || order.amount)}</span>
                          <span className={`order-status status-${order.status?.toLowerCase()}`}>
                            {order.status}
                          </span>
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </div>

              {/* Actions */}
              <div className="detail-actions">
                {getStatusBadge(selectedCustomer).label === 'Active' ? (
                  <button
                    className="action-btn-large danger"
                    onClick={() => handleUpdateStatus(selectedCustomer.id || selectedCustomer.user_id, 'inactive')}
                  >
                    <FaBan /> Deactivate Customer
                  </button>
                ) : (
                  <button
                    className="action-btn-large primary"
                    onClick={() => handleUpdateStatus(selectedCustomer.id || selectedCustomer.user_id, 'active')}
                  >
                    <FaCheckCircle /> Activate Customer
                  </button>
                )}
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default CustomersSection;
