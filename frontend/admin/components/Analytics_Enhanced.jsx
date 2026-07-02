import React, { useState, useEffect } from 'react';
import AdminService from '../services/adminService';
import { 
  FaRupeeSign, FaChartLine, FaShoppingCart, FaChartBar, 
  FaStore, FaUsers, FaChevronDown, FaBox,
  FaUtensils, FaTruck, FaClock, FaCheckCircle, FaTimesCircle,
  FaSpinner, FaExclamationTriangle, FaTimes
} from 'react-icons/fa';
import '../../css/admin/Analytics.css';
import '../../css/admin/Analytics_Enhanced.css';
import '../../css/admin/charts.css';

const Analytics_Enhanced = () => {
  const [analyticsData, setAnalyticsData] = useState({
    platform_summary: {},
    business_performance: [],
    item_performance: [],
    analytics_period: {}
  });
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  // Get today's date in YYYY-MM-DD format
  const today = new Date().toISOString().split('T')[0];
  
  const [dateFilters, setDateFilters] = useState({
    business_type: '',
    date_from: today,
    date_to: today
  });
  const [dropdownOpen, setDropdownOpen] = useState(false);
  const [expandedRows, setExpandedRows] = useState({});

  const toggleRowExpansion = (businessId) => {
    setExpandedRows(prev => ({
      ...prev,
      [businessId]: !prev[businessId]
    }));
  };

  const businessTypes = [
    { value: '', label: 'All Business Types' },
    { value: 'R01', label: 'Retail & Wholesale' },
    { value: 'R02', label: 'Food & Beverage' },
    { value: 'R09', label: 'Pharmacy & Healthcare' },
    { value: 'S01', label: 'Services' }
  ];

  useEffect(() => {
    fetchAnalytics();
  }, [dateFilters]);

  const fetchAnalytics = async () => {
    try {
      setLoading(true);
      setError(null);
      
      // Always use today's date for analytics
      const todayFilters = {
        ...dateFilters,
        date_from: today,
        date_to: today
      };
      
      const businessResponse = await AdminService.getBusinessAnalytics(todayFilters);
      const data = businessResponse.data || businessResponse;
      
      // Handle the new API response structure
      const safeData = {
        platform_summary: data.platform_summary || {},
        business_performance: data.business_performance || [],
        item_performance: data.item_performance || [],
        analytics_period: data.analytics_period || {}
      };
      
      setAnalyticsData(safeData);
    } catch (err) {
      setError('Failed to fetch analytics data');
      console.error('Analytics fetch error:', err);
    } finally {
      setLoading(false);
    }
  };

  const formatCurrency = (amount) => {
    if (amount === null || amount === undefined || isNaN(amount)) {
      return '₹0';
    }
    const numAmount = Number(amount);
    return new Intl.NumberFormat('en-IN', {
      style: 'currency',
      currency: 'INR'
    }).format(numAmount);
  };

  const formatPercentage = (value) => {
    if (value === null || value === undefined || isNaN(value)) {
      return '0%';
    }
    return `${Number(value).toFixed(2)}%`;
  };

  const getPerformanceColor = (rate, type = 'completion') => {
    if (type === 'completion') {
      if (rate >= 80) return '#28a745';
      if (rate >= 60) return '#ffc107';
      return '#dc3545';
    } else {
      // cancellation rate
      if (rate <= 5) return '#28a745';
      if (rate <= 15) return '#ffc107';
      return '#dc3545';
    }
  };

  // Open Business Details in same tab
  const openBusinessDetails = (businessId) => {
    console.log('Analytics_Enhanced - Opening business details for:', businessId);
    // Navigate to business details in the same tab
    window.location.hash = `business-details/${businessId}`;
  };

  const exportForPowerBI = () => {
    const data = {
      platform_summary: analyticsData.platform_summary,
      business_performance: analyticsData.business_performance,
      item_performance: analyticsData.item_performance,
      export_timestamp: new Date().toISOString(),
      data_version: "1.0"
    };
    
    const blob = new Blob([JSON.stringify(data, null, 2)], {
      type: 'application/json'
    });
    
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `kirazee_analytics_${new Date().toISOString().split('T')[0]}.json`;
    a.click();
  };

  const exportCSV = () => {
    // Create CSV content for business performance
    const headers = [
      'Business ID', 'Business Name', 'Type', 'Category', 'City', 'State',
      'Total Orders', 'Total Revenue', 'AOV', 'GMV', 'Completion Rate', 'Cancellation Rate'
    ];
    
    const rows = analyticsData.business_performance.map(business => [
      business.business_id,
      business.business_name,
      business.business_type_name,
      business.business_category,
      business.city,
      business.state,
      business.revenue_metrics?.total_orders || 0,
      business.revenue_metrics?.total_revenue || 0,
      business.revenue_metrics?.average_order_value || 0,
      business.revenue_metrics?.gross_merchandise_value || 0,
      business.performance_metrics?.completion_rate || 0,
      business.performance_metrics?.cancellation_rate || 0
    ]);
    
    const csvContent = [headers, ...rows]
      .map(row => row.map(cell => `"${cell}"`).join(','))
      .join('\n');
    
    const blob = new Blob([csvContent], { type: 'text/csv' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `kirazee_business_performance_${new Date().toISOString().split('T')[0]}.csv`;
    a.click();
  };

  if (loading) {
    return (
      <div className="analytics-loading">
        <FaSpinner className="loading-spinner" />
        <p>Loading comprehensive analytics...</p>
      </div>
    );
  }

  return (
    <div className="analytics">
      {/* Header */}
      <div className="analytics-header">
        <div className="header-content">
          <h2>Business Analytics</h2>
          <div className="today-indicator">
            <span className="today-badge">📅 Today Only</span>
            <span className="today-date">{today}</span>
          </div>
        </div>
        <div className="period-info">
          <span>All metrics show data for today only ({today})</span>
        </div>
      </div>

      {/* Error Display */}
      {error && (
        <div className="error-message">
          <FaExclamationTriangle className="error-icon" />
          <span>{error}</span>
          <button onClick={() => setError(null)}><FaTimes /></button>
        </div>
      )}

      {/* Enhanced Platform Summary */}
      <div className="platform-summary-enhanced">
        <h3>Platform Overview - Today's Performance</h3>
        
        {/* Primary KPIs */}
        <div className="kpi-grid-primary">
          <div className="kpi-card revenue">
            <div className="kpi-icon">
              <FaRupeeSign />
            </div>
            <div className="kpi-content">
              <h4>{formatCurrency(analyticsData.platform_summary.combined_metrics?.total_revenue || 0)}</h4>
              <p>Total Revenue</p>
              <div className="kpi-breakdown">
                <span>kirazee web/app: {formatCurrency(analyticsData.platform_summary.regular_orders?.total_revenue || 0)}</span>
                <span>Custom Website: {formatCurrency(analyticsData.platform_summary.grocery_orders?.total_revenue || 0)}</span>
              </div>
            </div>
          </div>
          
          <div className="kpi-card orders">
            <div className="kpi-icon">
              <FaShoppingCart />
            </div>
            <div className="kpi-content">
              <h4>{analyticsData.platform_summary.combined_metrics?.total_orders || 0}</h4>
              <p>Total Orders</p>
              <div className="kpi-breakdown">
                <span>Kirazee web/app: {analyticsData.platform_summary.regular_orders?.total_orders || 0}</span>
                <span>Custom Website: {analyticsData.platform_summary.grocery_orders?.total_orders || 0}</span>
              </div>
            </div>
          </div>
          
          <div className="kpi-card aov">
            <div className="kpi-icon">
              <FaChartBar />
            </div>
            <div className="kpi-content">
              <h4>{formatCurrency(analyticsData.platform_summary.regular_orders?.platform_aov || 0)}</h4>
              <p>Average Order Value</p>
              <div className="kpi-breakdown">
                <span>kirazee web/app: {formatCurrency(analyticsData.platform_summary.regular_orders?.platform_aov || 0)}</span>
                <span>Custom Website: {formatCurrency(analyticsData.platform_summary.grocery_orders?.platform_aov || 0)}</span>
              </div>
            </div>
          </div>
          
          <div className="kpi-card businesses">
            <div className="kpi-icon">
              <FaStore />
            </div>
            <div className="kpi-content">
              <h4>{analyticsData.platform_summary.active_businesses}/{analyticsData.platform_summary.total_businesses}</h4>
              <p>Active Businesses</p>
              <div className="kpi-breakdown">
                <span>Paid: {analyticsData.platform_summary.paid_businesses}</span>
              </div>
            </div>
          </div>
          
          <div className="kpi-card gmv">
            <div className="kpi-icon">
              <FaChartLine />
            </div>
            <div className="kpi-content">
              <h4>{formatCurrency(analyticsData.platform_summary.regular_orders?.total_gmv || 0)}</h4>
              <p>Gross Merchandise Value</p>
            </div>
          </div>
        </div>
      </div>

      {/* Enhanced Business Performance */}
      <div className="business-performance-enhanced">
        <div className="performance-header">
          <h3>Business Performance Analytics - Today</h3>
          <div className="performance-filters">
            <div className="filter-group">
              <label>Business Type</label>
              <select 
                value={dateFilters.business_type}
                onChange={(e) => setDateFilters(prev => ({...prev, business_type: e.target.value}))}
              >
                {businessTypes.map(type => (
                  <option key={type.value} value={type.value}>{type.label}</option>
                ))}
              </select>
            </div>
          </div>
        </div>

        <div className="business-table-enhanced">
          <table>
            <thead>
              <tr>
                <th>Business</th>
                <th>Type</th>
                <th>Category</th>
                <th>Location</th>
                <th>Level</th>
                <th>Orders</th>
                <th>Revenue</th>
                <th>AOV</th>
                <th>GMV</th>
                <th>Completion</th>
                <th>Cancellation</th>
                <th>Status</th>
              </tr>
            </thead>
            <tbody>
              {analyticsData.business_performance.map((business) => (
                <tr key={business.business_id}>
                  <td>
                    <div className="business-cell">
                      <div
                        className="business-name link"
                        onClick={() => openBusinessDetails(business.business_id)}
                        title="Open Business Details"
                        style={{ cursor: 'pointer', textDecoration: 'underline' }}
                      >
                        {business.business_name}
                      </div>
                      <div className="business-id">{business.business_id}</div>
                      {business.master && (
                        <div className="master-info">Master: {business.master}</div>
                      )}
                    </div>
                  </td>
                  <td>
                    <span className="business-type-badge">{business.business_type}</span>
                    <div className="type-name">{business.business_type_name}</div>
                  </td>
                  <td>
                    <span className="category-badge">{business.business_category}</span>
                  </td>
                  <td>
                    <div className="location-cell">
                      <div>{business.city}</div>
                      <div className="state">{business.state}</div>
                    </div>
                  </td>
                  <td>
                    <span className={`level-badge ${business.level}`}>
                      {business.level}
                    </span>
                  </td>
                  <td 
                    className="orders-cell clickable" 
                    onClick={() => toggleRowExpansion(business.business_id)}
                    style={{ cursor: 'pointer' }}
                  >
                    <div className="primary-metric">
                      {(business.combined_order_metrics?.regular_orders || 0) + (business.combined_order_metrics?.grocery_orders || 0) || business.revenue_metrics?.total_orders || 0}
                    </div>
                    {expandedRows[business.business_id] && (
                      <div className="metric-breakdown">
                        <span>Kirazee web/app: {business.combined_order_metrics?.regular_orders || business.revenue_metrics?.total_orders || 0}</span>
                        <span>Custom Website: {business.combined_order_metrics?.grocery_orders || 0}</span>
                      </div>
                    )}
                  </td>
                  <td 
                    className="revenue-cell clickable" 
                    onClick={() => toggleRowExpansion(business.business_id)}
                    style={{ cursor: 'pointer' }}
                  >
                    <div className="primary-metric">
                      {formatCurrency((business.combined_revenue_metrics?.regular_revenue || 0) + (business.combined_revenue_metrics?.grocery_revenue || 0) || business.revenue_metrics?.total_revenue || 0)}
                    </div>
                    {expandedRows[business.business_id] && (
                      <div className="metric-breakdown">
                        <span>Kirazee web/app: {formatCurrency(business.combined_revenue_metrics?.regular_revenue || business.revenue_metrics?.total_revenue || 0)}</span>
                        <span>Custom Website: {formatCurrency(business.combined_revenue_metrics?.grocery_revenue || 0)}</span>
                      </div>
                    )}
                  </td>
                  <td className="aov-cell">
                    {formatCurrency(business.revenue_metrics?.average_order_value || 0)}
                  </td>
                  <td className="gmv-cell">
                    {formatCurrency(business.revenue_metrics?.gross_merchandise_value || 0)}
                  </td>
                  <td className="completion-cell">
                    <div className="performance-indicator" style={{color: getPerformanceColor(business.performance_metrics?.completion_rate, 'completion')}}>
                      {formatPercentage(business.performance_metrics?.completion_rate)}
                    </div>
                  </td>
                  <td className="cancellation-cell">
                    <div className="performance-indicator" style={{color: getPerformanceColor(business.performance_metrics?.cancellation_rate, 'cancellation')}}>
                      {formatPercentage(business.performance_metrics?.cancellation_rate)}
                    </div>
                  </td>
                  <td>
                    <span className={`status-badge ${business.business_status?.toLowerCase()}`}>
                      {business.business_status}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {/* Enhanced Item Performance */}
      <div className="item-performance-enhanced">
        <h3>Top Selling Products Analytics - Today</h3>
        <div className="items-grid-enhanced">
          {analyticsData.item_performance.map((item, index) => (
            <div key={item.menu_item_id} className="item-card-enhanced">
              <div className="item-rank">#{item.sales_metrics?.overall_rank || index + 1}</div>
              <div className="item-info">
                <h4>{item.item_name || 'Unknown Item'}</h4>
                <p className="item-category">{item.category || 'Unknown Category'}</p>
                <p className="item-business">{item.business_name}</p>
                <div className="item-badges">
                  <span className="category-rank">#{item.sales_metrics?.rank_in_category} in category</span>
                </div>
              </div>
              <div className="item-metrics">
                <div className="metric primary">
                  <span className="metric-value">{item.sales_metrics?.total_quantity_sold || 0}</span>
                  <span className="metric-label">Units Sold</span>
                </div>
                <div className="metric primary">
                  <span className="metric-value">{formatCurrency(item.sales_metrics?.total_item_revenue || 0)}</span>
                  <span className="metric-label">Revenue</span>
                </div>
              </div>
            </div>
          ))}
        </div>
      </div>

    </div>
  );
};

export default Analytics_Enhanced;
