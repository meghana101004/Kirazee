import React, { useState, useEffect } from 'react';
import AdminService from '../services/adminService';
import { FaRupeeSign, FaChartLine, FaShoppingCart, FaChartBar, FaStore, FaUsers, FaChevronDown } from 'react-icons/fa';
import RevenueTrendChart from './charts/RevenueTrendChart';
import '../../css/admin/Analytics.css';
import '../../css/admin/charts.css';

const Analytics = () => {
  const [analyticsData, setAnalyticsData] = useState({
    platformSummary: {},
    businessPerformance: [],
    itemPerformance: [],
    dailyRevenue: [] // Add daily revenue data
  });
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [dateFilters, setDateFilters] = useState({
    business_type: ''
  });
  const [dropdownOpen, setDropdownOpen] = useState(false);

  const businessTypes = [
    { value: '', label: 'Choose business type' },
    { value: 'R01', label: 'Retail & Wholesale' },
    { value: 'R02', label: 'Food & Beverage' },
    { value: 'S01', label: 'Services' }
  ];

  useEffect(() => {
    fetchAnalytics();
  }, [dateFilters]);

  useEffect(() => {
    const handleClickOutside = (event) => {
      if (!event.target.closest('.custom-dropdown')) {
        setDropdownOpen(false);
      }
    };

    document.addEventListener('mousedown', handleClickOutside);
    return () => {
      document.removeEventListener('mousedown', handleClickOutside);
    };
  }, []);

  const fetchAnalytics = async () => {
    try {
      setLoading(true);
      setError(null);
      
      // Get today's date in YYYY-MM-DD format
      const today = new Date().toISOString().split('T')[0];
      
      // Always fetch today's data only
      const todayFilters = {
        ...dateFilters,
        date_from: today,
        date_to: today
      };
      
      // Fetch business analytics data for today only
      const businessResponse = await AdminService.getBusinessAnalytics(todayFilters);
      
      // Handle the new API response structure
      const data = businessResponse.data || businessResponse;
      
      // Create a safe data structure with fallbacks
      const safeData = {
        platform_summary: {
          total_businesses: data.platform_summary?.total_businesses || 0,
          active_businesses: data.platform_summary?.active_businesses || 0,
          paid_businesses: data.platform_summary?.paid_businesses || 0,
          total_orders: data.platform_summary?.combined_metrics?.total_orders || 
                        data.platform_summary?.regular_orders?.total_orders || 0,
          total_gmv: data.platform_summary?.regular_orders?.total_gmv || 0,
          total_revenue: data.platform_summary?.combined_metrics?.total_revenue || 
                       data.platform_summary?.regular_orders?.total_revenue || 0,
          platform_aov: data.platform_summary?.regular_orders?.platform_aov || 0,
          unique_customers: data.platform_summary?.regular_orders?.unique_customers || 0
        },
        business_performance: data.business_performance || [],
        item_performance: data.item_performance || [],
        dailyRevenue: [] // Empty for now since endpoint doesn't provide daily data
      };
      
      setAnalyticsData(safeData);
    } catch (err) {
      setError('Failed to fetch analytics data');
      console.error('Analytics fetch error:', err);
      
      // Fallback to mock data if API fails
      const mockData = {
        platform_summary: {
          total_businesses: 0,
          active_businesses: 0,
          paid_businesses: 0,
          total_orders: 0,
          total_gmv: 0,
          total_revenue: 0,
          platform_aov: 0,
          unique_customers: 0
        },
        business_performance: [],
        item_performance: [],
        dailyRevenue: []
      };
      
      setAnalyticsData(mockData);
    } finally {
      setLoading(false);
    }
  };

  const handleFilterChange = (key, value) => {
    setDateFilters(prev => ({
      ...prev,
      [key]: value
    }));
  };

  const handleBusinessTypeSelect = (value) => {
    handleFilterChange('business_type', value);
    setDropdownOpen(false);
  };

  const clearFilters = () => {
    setDateFilters({
      business_type: ''
    });
  };

  const getSelectedBusinessType = () => {
    const selected = businessTypes.find(type => type.value === dateFilters.business_type);
    return selected ? selected.label : 'Choose business type';
  };

  // Custom Dropdown Component
  const CustomDropdown = () => (
    <div className={`custom-dropdown ${dropdownOpen ? 'open' : ''}`}>
      <div 
        className="dropdown-trigger"
        onClick={() => setDropdownOpen(!dropdownOpen)}
      >
        <FaChevronDown className="dropdown-icon" />
        <span className="dropdown-text">{getSelectedBusinessType()}</span>
      </div>
      {dropdownOpen && (
        <div className="dropdown-menu">
          {businessTypes.map((type) => (
            <div
              key={type.value}
              className={`dropdown-option ${dateFilters.business_type === type.value ? 'selected' : ''}`}
              onClick={() => handleBusinessTypeSelect(type.value)}
            >
              {type.label}
            </div>
          ))}
        </div>
      )}
    </div>
  );

  const formatCurrency = (amount) => {
    // Handle null, undefined, or NaN values
    if (amount === null || amount === undefined || isNaN(amount)) {
      return '₹0';
    }
    
    // Ensure it's a number
    const numAmount = Number(amount);
    if (isNaN(numAmount)) {
      return '₹0';
    }
    
    return new Intl.NumberFormat('en-IN', {
      style: 'currency',
      currency: 'INR'
    }).format(numAmount);
  };

  const formatDate = (dateString) => {
    return AdminService.formatDate(dateString);
  };

  if (loading) {
    return (
      <div className="analytics-loading">
        <div className="loading-spinner"></div>
        <p>Loading analytics data...</p>
      </div>
    );
  }

  return (
    <div className="analytics">
      {/* Header */}
      <div className="analytics-header">
        <h2>
          Analytics & BI - Today's Data
        </h2>
        <div className="today-indicator">
          <span>📅 {new Date().toLocaleDateString('en-US', { weekday: 'long', year: 'numeric', month: 'long', day: 'numeric' })}</span>
        </div>
      </div>

      {/* Error Display */}
      {error && (
        <div className="error-message">
          {error}
          <button onClick={() => setError(null)}>×</button>
        </div>
      )}

      {/* Revenue Trend Chart */}
      <div className="analytics-charts-section" style={{ marginBottom: '24px' }}>
        {/* Pass the data fetched from your new backend endpoint */}
        <RevenueTrendChart data={analyticsData.dailyRevenue} />
      </div>

      {/* Platform Summary */}
      <div className="platform-summary">
        <div className="section-header">
          <h3>Today's Platform Summary</h3>
        </div>
        <div className="summary-grid">
          <div className="summary-card revenue">
            <div className="card-icon">
              <FaRupeeSign />
            </div>
            <div className="card-content">
              <h4>{formatCurrency(analyticsData.platform_summary.total_revenue)}</h4>
              <p>Total Revenue</p>
            </div>
          </div>
          
          <div className="summary-card gmv">
            <div className="card-icon">
              <FaChartLine />
            </div>
            <div className="card-content">
              <h4>{formatCurrency(analyticsData.platform_summary.total_gmv)}</h4>
              <p>Gross Merchandise Value</p>
            </div>
          </div>
          
          <div className="summary-card orders">
            <div className="card-icon">
              <FaShoppingCart />
            </div>
            <div className="card-content">
              <h4>{analyticsData.platform_summary.total_orders}</h4>
              <p>Total Orders</p>
            </div>
          </div>
          
          <div className="summary-card aov">
            <div className="card-icon">
              <FaChartBar />
            </div>
            <div className="card-content">
              <h4>{formatCurrency(analyticsData.platform_summary.platform_aov)}</h4>
              <p>Average Order Value</p>
            </div>
          </div>
          
          <div className="summary-card businesses">
            <div className="card-icon">
              <FaStore />
            </div>
            <div className="card-content">
              <h4>{analyticsData.platform_summary.active_businesses}/{analyticsData.platform_summary.total_businesses}</h4>
              <p>Active Businesses</p>
            </div>
          </div>
          
          <div className="summary-card customers">
            <div className="card-icon">
              <FaUsers />
            </div>
            <div className="card-content">
              <h4>{analyticsData.platform_summary.unique_customers}</h4>
              <p>Unique Customers</p>
            </div>
          </div>
        </div>
      </div>

      {/* Business Performance */}
      <div className="business-performance">
        <div className="performance-header">
          <h3>Today's Top Performing Businesses</h3>
          <div className="performance-filters">
            <div className="filter-group">
              <label>Business Type</label>
              <CustomDropdown />
            </div>
          </div>
        </div>
        <div className="performance-table">
          <table>
            <thead>
              <tr>
                <th>Business</th>
                <th>Type</th>
                <th>Location</th>
                <th>Orders</th>
                <th>Revenue</th>
                <th>AOV</th>
                <th>Completion Rate</th>
                <th>Status</th>
              </tr>
            </thead>
            <tbody>
              {analyticsData.business_performance.map((business) => (
                <tr key={business.business_id}>
                  <td>
                    <div className="business-cell">
                      <div className="business-name">{business.business_name || 'Unknown Business'}</div>
                      <div className="business-id">{business.business_id || 'N/A'}</div>
                    </div>
                  </td>
                  <td>
                    <span className="business-type">{business.business_type_name || 'Unknown'}</span>
                  </td>
                  <td>
                    <div className="location-cell">
                      <div>{business.city || 'Unknown'}</div>
                      <div className="state">{business.state || 'Unknown'}</div>
                    </div>
                  </td>
                  <td className="orders-cell">{business.revenue_metrics?.total_orders || 0}</td>
                  <td className="revenue-cell">{formatCurrency(business.revenue_metrics?.total_revenue || 0)}</td>
                  <td className="aov-cell">{formatCurrency(business.revenue_metrics?.average_order_value || 0)}</td>
                  <td className="completion-cell">{business.performance_metrics?.completion_rate || 0}%</td>
                  <td>
                    <span 
                      className={`business-status-badge ${business.business_status === 'Active' ? 'active' : 'inactive'}`}
                    >
                      {business.business_status || 'Unknown'}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {/* Item Performance */}
      <div className="item-performance">
        <h3>Today's Top Selling Items</h3>
        <div className="items-grid">
          {analyticsData.item_performance.map((item) => (
            <div key={item.menu_item_id} className="item-card">
              <div className="item-rank">#{item.sales_metrics?.overall_rank || 'N/A'}</div>
              <div className="item-info">
                <h4>{item.item_name || 'Unknown Item'}</h4>
                <p className="item-category">{item.category || 'Unknown Category'}</p>
                <p className="item-business">{item.business_name || 'Unknown Business'}</p>
              </div>
              <div className="item-metrics">
                <div className="metric">
                  <span className="metric-value">{item.sales_metrics?.total_quantity_sold || 0}</span>
                  <span className="metric-label">Sold</span>
                </div>
                <div className="metric">
                  <span className="metric-value">{formatCurrency(item.sales_metrics?.total_item_revenue || 0)}</span>
                  <span className="metric-label">Revenue</span>
                </div>
                <div className="metric">
                  <span className="metric-value">{formatCurrency(item.price || 0)}</span>
                  <span className="metric-label">Price</span>
                </div>
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Power BI Integration Info */}
      <div className="powerbi-info">
        <h3>Power BI Integration</h3>
        <div className="integration-card">
          <div className="integration-icon">📊</div>
          <div className="integration-content">
            <h4>Ready for Power BI</h4>
            <p>This analytics data is structured for seamless Power BI integration with the following reports:</p>
            <ul>
              <li>Sales Revenue Summary (Line charts, KPI Cards)</li>
              <li>Top Selling Business Ranking (Bar charts, Data Tables)</li>
              <li>Item Product Performance (Treemap, Bar charts)</li>
              <li>Operational Funnel Logistics (Funnel charts, Gauge charts)</li>
            </ul>
            <button className="export-btn">Export for Power BI</button>
          </div>
        </div>
      </div>
    </div>
  );
};

export default Analytics;
