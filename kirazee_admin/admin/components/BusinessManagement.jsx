import React, { useState, useEffect, useRef } from 'react';
import AdminService from '../services/adminService';
import '../../css/admin/BusinessManagement.css';
import {
  FaRegBuilding,
  FaEye,
  FaCheckCircle,
  FaTimesCircle,
  FaMoneyBillWave,
  FaTrash,
  FaSpinner,
  FaSearch,
  FaFilter,
  FaTimes,
  FaSave,
  FaChevronLeft,
  FaChevronRight,
  FaChevronDown,
  FaExclamationTriangle,
  FaChartLine,
  FaBox,
  FaUsers,
  FaMapMarkerAlt,
  FaCalendarAlt,
  FaTag,
  FaCrown
} from 'react-icons/fa';
import { MdRefresh } from 'react-icons/md';
import { Card, Row, Col, Statistic, Table, Tag, Progress, Avatar, Space, Typography, Button, Input, Select, Tooltip } from 'antd';

const { Title, Text } = Typography;
const { Search } = Input;
const { Option } = Select;

const BusinessManagement = () => {
  const [businesses, setBusinesses] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [filters, setFilters] = useState({
    status: '',
    business_type: '',
    search: '',
    page: 1,
    limit: 20
  });
  const [pagination, setPagination] = useState({});
  const [selectedBusiness, setSelectedBusiness] = useState(null);
  const [showActionModal, setShowActionModal] = useState(false);
  const [actionType, setActionType] = useState('');
  const [updating, setUpdating] = useState(false);
  const [showDetailsModal, setShowDetailsModal] = useState(false);
  const [editingBusiness, setEditingBusiness] = useState(null);
  const [businessDetails, setBusinessDetails] = useState({});
  const [dropdownOpen, setDropdownOpen] = useState(false);
  const [statusDropdownOpen, setStatusDropdownOpen] = useState(false);
  const [activeTab, setActiveTab] = useState('details'); // 'details' or 'orders'
  const [searchInput, setSearchInput] = useState(''); // Local search input state
  const searchTimeoutRef = useRef(null); // Ref for debounce timeout

  useEffect(() => {
    fetchBusinesses();
  }, [filters]);

  // Close dropdown when clicking outside
  useEffect(() => {
    const handleClickOutside = (event) => {
      if (dropdownOpen && !event.target.closest('.custom-dropdown')) {
        setDropdownOpen(false);
      }
      if (statusDropdownOpen && !event.target.closest('.status-dropdown')) {
        setStatusDropdownOpen(false);
      }
    };

    document.addEventListener('mousedown', handleClickOutside);
    return () => {
      document.removeEventListener('mousedown', handleClickOutside);
    };
  }, [dropdownOpen, statusDropdownOpen]);

  const fetchBusinesses = async () => {
    try {
      setLoading(true);
      setError(null);

      console.log('Fetching businesses with filters:', filters);

      // Fetch data from the new businesses-simple API
      const response = await AdminService.getBusinessesSimple(filters);

      console.log('Businesses response:', response);

      setBusinesses(response.businesses);
      setPagination(response.pagination);
    } catch (err) {
      setError('Failed to fetch businesses');
      console.error('Businesses fetch error:', err);

      // Fallback to mock data if API fails
      const mockResponse = {
        success: true,
        message: "Business data retrieved successfully",
        pagination: {
          total_businesses: 12,
          current_page: 1,
          per_page: 20,
          total_pages: 1,
          has_next_page: false,
          has_prev_page: false
        },
        businesses: [
          {
            business_id: "KIR1478820251021185505",
            businessName: "The Fort Royal Biryani",
            businessType: "R02",
            businessCategory: "Restaurant",
            businessEmail: "reddy.sangeetha@gmail.com",
            businessNumber: "",
            address: "120 East Jeedi Drive",
            city: "Sri City",
            state: "Andhra Pradesh",
            status: "Active",
            payment_status: "Paid",
            created_at: "2026-03-01T18:55:05",
            level: "master",
            master: null,
            status_code: 1,
            total_orders: 34,
            total_revenue: 4409.02,
            revenue_by_status: {
              delivered: { order_count: 3, revenue: 769.0, total_amount: 769.0 },
              completed: { order_count: 1, revenue: 231.0, total_amount: 231.0 },
              cancelled: { order_count: 7, revenue: 5884.0, total_amount: 5884.0 },
              pending: { order_count: 6, revenue: 890.0, total_amount: 890.0 }
            },
            is_master: true,
            has_subs: false,
            financial_details: {
              has_financial_data: true
            }
          }
        ]
      };

      setBusinesses(mockResponse.businesses);
      setPagination(mockResponse.pagination);
    } finally {
      setLoading(false);
    }
  };

  // Calculate summary statistics
  const calculateStats = () => {
    const totalBusinesses = businesses.length;
    const activeBusinesses = businesses.filter(b => b.status === 'Active').length;
    const totalRevenue = businesses.reduce((sum, b) => sum + (b.total_revenue || 0), 0);
    const totalOrders = businesses.reduce((sum, b) => sum + (b.total_orders || 0), 0);
    const masterBusinesses = businesses.filter(b => b.is_master).length;
    const subBusinesses = businesses.filter(b => !b.is_master).length;

    return {
      totalBusinesses,
      activeBusinesses,
      totalRevenue,
      totalOrders,
      masterBusinesses,
      subBusinesses
    };
  };

  const getStatusColor = (status) => {
    const colors = {
      'Active': 'green',
      'Inactive': 'red',
      'Pending': 'orange',
      'Paid': 'blue',
      'Unpaid': 'red'
    };
    return colors[status] || 'default';
  };

  const getLevelIcon = (business) => {
    if (business.is_master) {
      return <FaCrown style={{ color: '#FFD700' }} />;
    }
    return <FaRegBuilding style={{ color: '#1890ff' }} />;
  };

  const formatCurrency = (amount) => {
    return new Intl.NumberFormat('en-IN', {
      style: 'currency',
      currency: 'INR',
      minimumFractionDigits: 2
    }).format(amount || 0);
  };

  const handleFilterChange = (field, value) => {
    console.log('Filter change:', field, value);
    setFilters(prev => {
      const newFilters = {
        ...prev,
        [field]: value || '', // Convert undefined/null to empty string
        page: 1 // Reset to first page when filters change
      };
      console.log('New filters:', newFilters);
      return newFilters;
    });
  };

  // Handle search input change with debounce
  const handleSearchChange = (e) => {
    const value = e.target.value;
    setSearchInput(value);
    
    // Clear existing timeout
    if (searchTimeoutRef.current) {
      clearTimeout(searchTimeoutRef.current);
    }
    
    // Set new timeout to update filters after 500ms of no typing
    searchTimeoutRef.current = setTimeout(() => {
      handleFilterChange('search', value);
    }, 500);
  };

  // Cleanup timeout on unmount
  useEffect(() => {
    return () => {
      if (searchTimeoutRef.current) {
        clearTimeout(searchTimeoutRef.current);
      }
    };
  }, []);

  const handleViewDetails = (business) => {
    // Navigate to the new tabbed business details page
    window.location.hash = `business-details-tabbed/${business.business_id}`;
  };

  const stats = calculateStats();

  // Table columns for business data
  const columns = [
    {
      title: 'Business',
      key: 'business',
      width: '20%',
      render: (_, record) => (
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <span style={{ fontSize: 16, color: '#1890ff', flexShrink: 0 }}>
            {getLevelIcon(record)}
          </span>
          <div style={{ minWidth: 0, flex: 1 }}>
            <div style={{ 
              fontWeight: 600, 
              fontSize: 15,
              color: '#2A2C41',
              whiteSpace: 'nowrap',
              overflow: 'hidden',
              textOverflow: 'ellipsis',
              marginBottom: 3,
              lineHeight: 1.3
            }}>
              {record.businessName}
            </div>
            <Text type="secondary" style={{ 
              fontSize: 12,
              fontFamily: 'monospace',
              color: '#8c8c8c',
              fontWeight: 500
            }}>
              {record.business_id}
            </Text>
          </div>
        </div>
      )
    },
    {
      title: 'Business Type',
      key: 'businessType',
      width: '12%',
      align: 'center',
      render: (_, record) => (
        <Tag 
          color="geekblue" 
          style={{ 
            borderRadius: 4,
            fontWeight: 500,
            fontSize: 10,
            padding: '2px 8px'
          }}
        >
          {record.businessType}
        </Tag>
      )
    },
    {
      title: 'Category',
      dataIndex: 'businessCategory',
      key: 'category',
      width: '10%',
      align: 'center',
      render: (category) => (
        <Tag 
          color="blue" 
          style={{ 
            borderRadius: 4,
            fontWeight: 500,
            fontSize: 10,
            padding: '1px 6px'
          }}
        >
          {category}
        </Tag>
      )
    },
    {
      title: 'Location',
      key: 'location',
      width: '15%',
      render: (_, record) => (
        <div style={{ lineHeight: 1.3 }}>
          <div style={{ 
            fontSize: 12, 
            fontWeight: 500,
            color: '#2A2C41',
            marginBottom: 1
          }}>
            {record.city}, {record.state}
          </div>
          <Text type="secondary" style={{ 
            fontSize: 10,
            display: 'block',
            whiteSpace: 'nowrap',
            overflow: 'hidden',
            textOverflow: 'ellipsis',
            maxWidth: '140px'
          }}>
            {record.address}
          </Text>
        </div>
      )
    },
    {
      title: 'Registration Date',
      key: 'registrationDate',
      width: '12%',
      align: 'center',
      render: (_, record) => {
        const date = new Date(record.created_at);
        const formattedDate = date.toLocaleDateString('en-GB', {
          day: '2-digit',
          month: 'short',
          year: 'numeric'
        });
        const timeAgo = (() => {
          const now = new Date();
          const diffTime = Math.abs(now - date);
          const diffDays = Math.ceil(diffTime / (1000 * 60 * 60 * 24));
          if (diffDays < 30) return `${diffDays}d ago`;
          if (diffDays < 365) return `${Math.floor(diffDays / 30)}m ago`;
          return `${Math.floor(diffDays / 365)}y ago`;
        })();
        
        return (
          <div style={{ textAlign: 'center' }}>
            <div style={{ 
              fontSize: 11, 
              fontWeight: 500,
              color: '#2A2C41',
              marginBottom: 1
            }}>
              {formattedDate}
            </div>
            <Text type="secondary" style={{ fontSize: 9 }}>
              {timeAgo}
            </Text>
          </div>
        );
      }
    },
    {
      title: 'Performance',
      key: 'performance',
      width: '15%',
      align: 'center',
      render: (_, record) => (
        <div style={{ display: 'flex', gap: 12, justifyContent: 'center', alignItems: 'center' }}>
          <div style={{ textAlign: 'center' }}>
            <Text strong style={{ fontSize: 13, color: '#2A2C41', display: 'block' }}>
              {record.total_orders || 0}
            </Text>
            <Text type="secondary" style={{ fontSize: 9 }}>
              orders
            </Text>
          </div>
          <div style={{ textAlign: 'center' }}>
            <Text strong style={{ fontSize: 12, color: '#52c41a', display: 'block' }}>
              {formatCurrency(record.total_revenue)}
            </Text>
            <Text type="secondary" style={{ fontSize: 9 }}>
              revenue
            </Text>
          </div>
        </div>
      )
    },
    {
      title: 'Actions',
      key: 'actions',
      width: '16%',
      align: 'center',
      render: (_, record) => (
        <Space size={6}>
          <Button
            type="primary"
            size="small"
            icon={<FaEye />}
            onClick={() => handleViewDetails(record)}
            style={{
              fontSize: 10,
              height: 28,
              padding: '0 12px',
              borderRadius: 4
            }}
          >
            View
          </Button>
          {(record.status_code === 1 || record.status === 'Active') ? (
            <Button
              danger
              size="small"
              onClick={() => handleBusinessAction(record, 'deactivate')}
              style={{
                fontSize: 10,
                height: 28,
                padding: '0 12px',
                borderRadius: 4
              }}
            >
              Deactivate
            </Button>
          ) : (
            <Button
              type="primary"
              size="small"
              onClick={() => handleBusinessAction(record, 'activate')}
              style={{
                fontSize: 10,
                height: 28,
                padding: '0 12px',
                borderRadius: 4,
                background: '#52c41a',
                borderColor: '#52c41a'
              }}
            >
              Activate
            </Button>
          )}
        </Space>
      )
    }
  ];

  const handleBusinessAction = async (business, action) => {
    setSelectedBusiness(business);
    setActionType(action);
    setShowActionModal(true);
  };

  const confirmAction = async () => {
    if (!selectedBusiness || !actionType) return;

    try {
      setUpdating(true);

      switch (actionType) {
        case 'activate': {
          const res = await AdminService.updateBusinessStatus(selectedBusiness.business_id, 'activate');
          setBusinesses(prev => prev.map(b =>
            b.business_id === selectedBusiness.business_id
              ? { ...b, status: (res && res.current_status) || 'Active', status_code: (res && res.current_status_code) ?? b.status_code }
              : b
          ));
          break;
        }
        case 'deactivate': {
          const res = await AdminService.updateBusinessStatus(selectedBusiness.business_id, 'deactivate');
          setBusinesses(prev => prev.map(b =>
            b.business_id === selectedBusiness.business_id
              ? { ...b, status: (res && res.current_status) || 'Deactivated', status_code: (res && res.current_status_code) ?? b.status_code }
              : b
          ));
          break;
        }
        case 'mark_paid':
          await AdminService.updateBusinessPaymentStatus(selectedBusiness.business_id, 'Paid');
          setBusinesses(prev => prev.map(b =>
            b.business_id === selectedBusiness.business_id
              ? { ...b, payment_status: 'Paid' }
              : b
          ));
          break;
        case 'delete':
          await AdminService.deactivateBusiness(selectedBusiness.business_id);
          setBusinesses(prev => prev.filter(b => b.business_id !== selectedBusiness.business_id));
          break;
        default:
          break;
      }

      setShowActionModal(false);
      setSelectedBusiness(null);
      setActionType('');
    } catch (err) {
      console.error('Action failed:', err);
      setError(`Failed to ${actionType} business`);
    } finally {
      setUpdating(false);
    }
  };

  if (loading) {
    return (
      <div style={{ 
        display: 'flex', 
        justifyContent: 'center', 
        alignItems: 'center', 
        height: '100vh',
        flexDirection: 'column',
        gap: 16
      }}>
        <FaSpinner className="loading-spinner" style={{ fontSize: 48, color: '#1890ff' }} />
        <p style={{ color: '#666' }}>Loading businesses...</p>
      </div>
    );
  }

  return (
    <div style={{ 
      padding: '24px', 
      background: '#f5f5f5', 
      minHeight: '100vh',
      fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif'
    }}>
      {/* Header */}
      <div style={{ 
        background: 'white', 
        padding: '24px', 
        borderRadius: '12px', 
        marginBottom: '24px',
        boxShadow: '0 2px 8px rgba(0,0,0,0.1)'
      }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <div>
            <Title level={2} style={{ margin: 0, color: '#001529' }}>
              Business Management
            </Title>
            <Text type="secondary" style={{ fontSize: 14 }}>
              Manage and monitor all registered businesses
            </Text>
          </div>
          <Button 
            type="primary" 
            icon={<MdRefresh />}
            onClick={fetchBusinesses}
            loading={loading}
          >
            Refresh
          </Button>
        </div>
      </div>

      {/* Error Display */}
      {error && (
        <div style={{ 
          background: '#fff2f0', 
          border: '1px solid #ffccc7', 
          borderRadius: '8px', 
          padding: '16px', 
          marginBottom: '24px',
          display: 'flex',
          alignItems: 'center',
          gap: 12
        }}>
          <FaExclamationTriangle style={{ color: '#ff4d4f' }} />
          <span style={{ color: '#cf1322' }}>{error}</span>
          <Button 
            type="text" 
            icon={<FaTimes />} 
            onClick={() => setError(null)}
            style={{ marginLeft: 'auto' }}
          />
        </div>
      )}

      {/* Statistics Cards */}
      <Row gutter={[16, 16]} style={{ marginBottom: '24px' }}>
        <Col xs={24} sm={12} md={8} lg={4}>
          <Card>
            <Statistic
              title="Total Businesses"
              value={stats.totalBusinesses}
            />
          </Card>
        </Col>
        <Col xs={24} sm={12} md={8} lg={4}>
          <Card>
            <Statistic
              title="Active Businesses"
              value={stats.activeBusinesses}
            />
          </Card>
        </Col>
        <Col xs={24} sm={12} md={8} lg={4}>
          <Card>
            <Statistic
              title="Total Revenue"
              value={stats.totalRevenue}
              formatter={(value) => formatCurrency(value)}
            />
          </Card>
        </Col>
        <Col xs={24} sm={12} md={8} lg={4}>
          <Card>
            <Statistic
              title="Total Orders"
              value={stats.totalOrders}
            />
          </Card>
        </Col>
        <Col xs={24} sm={12} md={8} lg={4}>
          <Card>
            <Statistic
              title="Master Businesses"
              value={stats.masterBusinesses}
            />
          </Card>
        </Col>
        <Col xs={24} sm={12} md={8} lg={4}>
          <Card>
            <Statistic
              title="Sub-Businesses"
              value={stats.subBusinesses}
            />
          </Card>
        </Col>
      </Row>

      {/* Filters and Search */}
      <Card style={{ marginBottom: '24px' }}>
        <Row gutter={[16, 16]} align="middle">
          <Col xs={24} md={8}>
            <Search
              placeholder="Search businesses..."
              allowClear
              enterButton
              value={searchInput}
              onChange={handleSearchChange}
              onSearch={(value) => {
                setSearchInput(value);
                handleFilterChange('search', value);
              }}
              style={{ width: '100%' }}
            />
          </Col>
          <Col xs={24} md={6}>
            <Select
              placeholder="Filter by status"
              allowClear
              value={filters.status || undefined}
              style={{ width: '100%' }}
              onChange={(value) => handleFilterChange('status', value)}
            >
              <Option value="">All Status</Option>
              <Option value="Active">Active</Option>
              <Option value="Inactive">Inactive</Option>
              <Option value="Pending">Pending</Option>
            </Select>
          </Col>
          <Col xs={24} md={6}>
            <Select
              placeholder="Filter by category"
              allowClear
              value={filters.business_type || undefined}
              style={{ width: '100%' }}
              onChange={(value) => handleFilterChange('business_type', value)}
            >
              <Option value="">All Categories</Option>
              <Option value="R01">Grocery & Kirana</Option>
              <Option value="R02">Restaurant</Option>
              <Option value="R08">Clothing & Accessories</Option>
            </Select>
          </Col>
          <Col xs={24} md={4}>
            <Text type="secondary">
              {pagination.total_businesses} businesses total
            </Text>
          </Col>
        </Row>
      </Card>

      {/* Businesses Table */}
      <Card>
        <Table
          columns={columns}
          dataSource={businesses.map((business, index) => ({ ...business, key: index }))}
          pagination={{
            current: filters.page,
            pageSize: filters.limit,
            total: pagination.total_businesses,
            showSizeChanger: true,
            showQuickJumper: true,
            showTotal: (total, range) => 
              `${range[0]}-${range[1]} of ${total} businesses`,
            onChange: (page, pageSize) => {
              handleFilterChange('page', page);
              handleFilterChange('limit', pageSize);
            }
          }}
          scroll={{ x: 'max-content' }}
          size="middle"
        />
      </Card>

      {/* Action Confirmation Modal */}
      {showActionModal && selectedBusiness && (
        <div className="modal-overlay">
          <div className="action-modal-modern">
            {/* Modal Header */}
            <div className="modal-header-modern">
              <div className="modal-title-section">
                <div className="modal-icon">
                  <FaExclamationTriangle />
                </div>
                <h3>Confirm Action</h3>
              </div>
              <button
                className="close-btn-modern"
                onClick={() => setShowActionModal(false)}
              >
                <FaTimes />
              </button>
            </div>

            {/* Modal Content */}
            <div className="modal-content-modern">
              <div className="confirmation-message">
                <p>Are you sure you want to <span className="action-highlight">{actionType.replace('_', ' ')}</span> this business?</p>
              </div>

              <div className="business-summary-modern">
                <div className="summary-item">
                  <span className="summary-label">Business Name</span>
                  <span className="summary-value">{selectedBusiness.businessName}</span>
                </div>
                <div className="summary-item">
                  <span className="summary-label">Business ID</span>
                  <span className="summary-value">{selectedBusiness.business_id}</span>
                </div>
                <div className="summary-item">
                  <span className="summary-label">Current Status</span>
                  <span className={`summary-value status-badge ${selectedBusiness.status.toLowerCase()}`}>{selectedBusiness.status}</span>
                </div>
                <div className="summary-item">
                  <span className="summary-label">Payment Status</span>
                  <span className={`summary-value status-badge ${selectedBusiness.payment_status.toLowerCase()}`}>{selectedBusiness.payment_status}</span>
                </div>
              </div>
            </div>

            {/* Modal Actions */}
            <div className="modal-actions-modern">
              <button
                className="btn-cancel-modern"
                onClick={() => setShowActionModal(false)}
                disabled={updating}
              >
                Cancel
              </button>
              <button
                className="btn-confirm-modern"
                onClick={confirmAction}
                disabled={updating}
              >
                {updating ? (
                  <>
                    <FaSpinner className="spin" />
                    Processing...
                  </>
                ) : (
                  <>
                    <FaCheckCircle />
                    Confirm
                  </>
                )}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Business Details Modal */}
      {showDetailsModal && editingBusiness && (
        <div className="modal-overlay">
          <div className="details-modal-modern">
            {/* Fixed Header */}
            <div className="modal-header-fixed">
              <div className="modal-title-section">
                <div className="modal-icon business-icon">
                  <FaStore />
                </div>
                <div className="title-info">
                  <h3>Business Details</h3>
                  <span className="business-name">{editingBusiness.businessName}</span>
                </div>
              </div>
              <button
                className="close-btn-modern"
                onClick={handleCloseDetailsModal}
              >
                <FaTimes />
              </button>
            </div>

            {/* Tabs */}
            <div className="modal-tabs">
              <button
                className={`modal-tab ${activeTab === 'details' ? 'active' : ''}`}
                onClick={() => setActiveTab('details')}
              >
                Business Details
              </button>
              <button
                className={`modal-tab ${activeTab === 'orders' ? 'active' : ''}`}
                onClick={() => setActiveTab('orders')}
              >
                Revenue Analytics
              </button>
            </div>

            {/* Scrollable Content */}
            <div className="modal-content-scrollable">
              <div className="details-form-modern">

                {/* Business Details Tab */}
                {activeTab === 'details' && (
                  <>
                    {/* Basic Information */}
                    <div className="form-section">
                      <h4>Basic Information</h4>
                      <div className="form-grid">
                        <div className="form-group">
                          <label>Business Name</label>
                          <input
                            type="text"
                            value={businessDetails.businessName}
                            disabled
                            className="disabled-field"
                          />
                        </div>
                        <div className="form-group">
                          <label>Business ID</label>
                          <input
                            type="text"
                            value={editingBusiness.business_id}
                            disabled
                            className="disabled-field"
                          />
                        </div>
                        <div className="form-group">
                          <label>Business Type</label>
                          <input
                            type="text"
                            value={businessDetails.business_type_name}
                            disabled
                            className="disabled-field"
                          />
                        </div>
                        <div className="form-group">
                          <label>Email</label>
                          <input
                            type="email"
                            value={businessDetails.businessEmail}
                            disabled
                            className="disabled-field"
                          />
                        </div>
                        <div className="form-group">
                          <label>Phone Number</label>
                          <input
                            type="tel"
                            value={businessDetails.businessNumber}
                            disabled
                            className="disabled-field"
                          />
                        </div>
                      </div>
                    </div>

                    {/* Address Information */}
                    <div className="form-section">
                      <h4>Address Information</h4>
                      <div className="form-grid">
                        <div className="form-group full-width">
                          <label>Address</label>
                          <textarea
                            value={businessDetails.address}
                            disabled
                            className="disabled-field"
                            rows="3"
                          />
                        </div>
                        <div className="form-group">
                          <label>City</label>
                          <input
                            type="text"
                            value={businessDetails.city}
                            disabled
                            className="disabled-field"
                          />
                        </div>
                        <div className="form-group">
                          <label>State</label>
                          <input
                            type="text"
                            value={businessDetails.state}
                            disabled
                            className="disabled-field"
                          />
                        </div>
                        <div className="form-group">
                          <label>Pincode</label>
                          <input
                            type="text"
                            value={businessDetails.pincode}
                            disabled
                            className="disabled-field"
                          />
                        </div>
                      </div>
                    </div>

                    {/* Business Hierarchy */}
                    <div className="form-section">
                      <h4>Business Hierarchy</h4>
                      <div className="form-grid">
                        <div className="form-group">
                          <label>Business Level</label>
                          <input
                            type="text"
                            value={editingBusiness.level}
                            disabled
                            className="disabled-field"
                          />
                        </div>
                        <div className="form-group">
                          <label>Master Business</label>
                          <input
                            type="text"
                            value={editingBusiness.master || 'None'}
                            disabled
                            className="disabled-field"
                          />
                        </div>
                        <div className="form-group">
                          <label>Is Master</label>
                          <input
                            type="text"
                            value={editingBusiness.is_master ? 'Yes' : 'No'}
                            disabled
                            className="disabled-field"
                          />
                        </div>
                        <div className="form-group">
                          <label>Has Subsidiaries</label>
                          <input
                            type="text"
                            value={editingBusiness.has_subs ? 'Yes' : 'No'}
                            disabled
                            className="disabled-field"
                          />
                        </div>
                      </div>
                    </div>

                    {/* Business Classification */}
                    <div className="form-section">
                      <h4>Business Classification</h4>
                      <div className="form-grid">
                        <div className="form-group">
                          <label>Business Type Code</label>
                          <input
                            type="text"
                            value={editingBusiness.businessType}
                            disabled
                            className="disabled-field"
                          />
                        </div>
                        <div className="form-group">
                          <label>Business Category</label>
                          <input
                            type="text"
                            value={editingBusiness.businessCategory}
                            disabled
                            className="disabled-field"
                          />
                        </div>
                      </div>
                    </div>

                    {/* Business Status */}
                    <div className="form-section">
                      <h4>Business Status</h4>
                      <div className="form-grid">
                        <div className="form-group">
                          <label>Status</label>
                          <input
                            type="text"
                            value={businessDetails.status}
                            disabled
                            className="disabled-field"
                          />
                        </div>
                        <div className="form-group">
                          <label>Payment Status</label>
                          <input
                            type="text"
                            value={businessDetails.payment_status}
                            disabled
                            className="disabled-field"
                          />
                        </div>
                      </div>
                    </div>

                  </>
                )}

                {/* Revenue Analytics Tab */}
                {activeTab === 'orders' && (
                  <>
                    {/* Revenue Analytics */}
                    <div className="form-section">
                      <h4>Revenue Analytics</h4>
                      <div className="revenue-breakdown">
                        <div className="revenue-summary">
                          <div className="summary-item">
                            <span className="label">Total Orders</span>
                            <span className="value">{editingBusiness.total_orders}</span>
                          </div>
                          <div className="summary-item">
                            <span className="label">Total Revenue</span>
                            <span className="value">{formatCurrency(editingBusiness.total_revenue)}</span>
                          </div>
                        </div>

                        {editingBusiness.revenue_by_status && Object.keys(editingBusiness.revenue_by_status).length > 0 && (
                          <div className="revenue-by-status">
                            <h5>Revenue by Order Status</h5>
                            <div className="revenue-status-grid">
                              {Object.entries(editingBusiness.revenue_by_status).map(([status, data]) => (
                                <div key={status} className="revenue-status-item">
                                  <div className="status-header">
                                    <span className="status-name">{status}</span>
                                    <span className="order-count">{data.order_count} orders</span>
                                  </div>
                                  <div className="revenue-details">
                                    <div className="revenue-item">
                                      <span className="revenue-label">Actual Revenue:</span>
                                      <span className="revenue-value">{formatCurrency(data.revenue)}</span>
                                    </div>
                                    <div className="revenue-item">
                                      <span className="revenue-label">Total Amount:</span>
                                      <span className="revenue-value">{formatCurrency(data.total_amount)}</span>
                                    </div>
                                  </div>
                                </div>
                              ))}
                            </div>
                          </div>
                        )}
                      </div>
                    </div>
                  </>
                )}

              </div>
            </div>

            {/* Fixed Footer */}
            <div className="modal-footer-fixed">
              <button
                className="btn-cancel-modern"
                onClick={handleCloseDetailsModal}
              >
                Close
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default BusinessManagement;
