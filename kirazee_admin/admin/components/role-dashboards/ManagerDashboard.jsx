import React, { useState, useEffect } from 'react';
import AdminService from '../../services/adminService';
import '../../../css/admin/ManagerDashboard.css';
import { 
  FaBox, FaStore, FaUsers, FaChartLine, FaFileAlt, 
  FaBell, FaSpinner, FaArrowUp, FaArrowDown 
} from 'react-icons/fa';
import { MdRefresh } from 'react-icons/md';
import RevenueAnalyticsChart from './manager/RevenueAnalyticsChart';
import MonthlyTargetWidget from './manager/MonthlyTargetWidget';
import TopCategoriesWidget from './manager/TopCategoriesWidget';
import ActiveUsersWidget from './manager/ActiveUsersWidget';
import ConversionRateWidget from './manager/ConversionRateWidget';
import TrafficSourcesWidget from './manager/TrafficSourcesWidget';
import OrdersSection from './manager/OrdersSection';
import ProductsSection from './manager/ProductsSection';
import CustomersSection from './manager/CustomersSection';
import ReportsSection from './manager/ReportsSection';
import NotificationsSection from './manager/NotificationsSection';

const ManagerDashboard = () => {
  const [activeTab, setActiveTab] = useState('dashboard');
  const [dashboardData, setDashboardData] = useState({
    snapshot: null,
    summary: null
  });
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [lastUpdated, setLastUpdated] = useState(new Date());

  useEffect(() => {
    fetchDashboardData();
  }, []);

  const fetchDashboardData = async () => {
    try {
      setLoading(true);
      setError(null);
      
      // Fetch snapshot data (this is the main data source)
      const snapshotData = await AdminService.getDashboardSnapshot();
      
      console.log('Dashboard Snapshot Response:', snapshotData);
      
      if (snapshotData && snapshotData.success) {
        setDashboardData({
          snapshot: snapshotData.data,
          summary: null // Summary is optional
        });
        setLastUpdated(new Date(snapshotData.data?.last_updated || Date.now()));
      } else {
        throw new Error(snapshotData.message || 'Failed to fetch dashboard data');
      }
    } catch (error) {
      console.error('Error fetching dashboard data:', error);
      setError('Failed to load dashboard data');
    } finally {
      setLoading(false);
    }
  };

  const formatCurrency = (amount) => {
    return new Intl.NumberFormat('en-IN', {
      style: 'currency',
      currency: 'INR',
      maximumFractionDigits: 0
    }).format(amount || 0);
  };

  const formatNumber = (num) => {
    return new Intl.NumberFormat('en-IN').format(num || 0);
  };

  const renderSidebar = () => (
    <div className="manager-sidebar">
      <div className="sidebar-header">
        <div className="logo">
          <span className="logo-text">Kirazee</span>
        </div>
      </div>
      
      <nav className="sidebar-nav">
        <button 
          className={`nav-item ${activeTab === 'dashboard' ? 'active' : ''}`}
          onClick={() => setActiveTab('dashboard')}
        >
          <FaChartLine className="nav-icon" />
          <span>Dashboard</span>
        </button>
        
        <button 
          className={`nav-item ${activeTab === 'orders' ? 'active' : ''}`}
          onClick={() => setActiveTab('orders')}
        >
          <FaBox className="nav-icon" />
          <span>Orders</span>
        </button>
        
        <button 
          className={`nav-item ${activeTab === 'products' ? 'active' : ''}`}
          onClick={() => setActiveTab('products')}
        >
          <FaStore className="nav-icon" />
          <span>Products</span>
        </button>
        
        <button 
          className={`nav-item ${activeTab === 'customers' ? 'active' : ''}`}
          onClick={() => setActiveTab('customers')}
        >
          <FaUsers className="nav-icon" />
          <span>Customers</span>
        </button>
        
        <button 
          className={`nav-item ${activeTab === 'reports' ? 'active' : ''}`}
          onClick={() => setActiveTab('reports')}
        >
          <FaFileAlt className="nav-icon" />
          <span>Reports</span>
        </button>
        
        <button 
          className={`nav-item ${activeTab === 'notifications' ? 'active' : ''}`}
          onClick={() => setActiveTab('notifications')}
        >
          <FaBell className="nav-icon" />
          <span>Notifications</span>
        </button>
      </nav>
    </div>
  );

  const renderTopBar = () => null;

  const renderDashboardContent = () => {
    if (loading) {
      return (
        <div className="loading-container">
          <FaSpinner className="loading-spinner" />
          <p>Loading dashboard...</p>
        </div>
      );
    }

    if (error) {
      return (
        <div className="error-container">
          <p>{error}</p>
          <button onClick={fetchDashboardData} className="retry-btn">
            <MdRefresh /> Retry
          </button>
        </div>
      );
    }

    const snapshot = dashboardData.snapshot;
    const summary = dashboardData.summary;
    
    const totalSales = snapshot?.revenue?.total_revenue || 0;
    const totalOrders = snapshot?.orders?.total_orders || 0;
    const totalVisitors = snapshot?.customers?.total_users || 0;
    
    // Calculate growth percentages from summary data if available
    const salesGrowth = summary?.revenue_metrics?.growth_percentage || 3.5;
    const ordersGrowth = summary?.order_metrics?.growth_percentage || -0.89;
    const visitorsGrowth = summary?.user_analytics?.growth_percentage || 8.02;

    return (
      <div className="dashboard-content">
        {/* KPI Cards */}
        <div className="kpi-row">
          <div className="kpi-card">
            <div className="kpi-header">
              <span className="kpi-label">Total Sales</span>
              <span className="kpi-icon">💰</span>
            </div>
            <div className="kpi-value">{formatCurrency(totalSales)}</div>
            <div className={`kpi-change ${salesGrowth >= 0 ? 'positive' : 'negative'}`}>
              {salesGrowth >= 0 ? <FaArrowUp /> : <FaArrowDown />} {Math.abs(salesGrowth).toFixed(2)}%
              <span className="kpi-period">vs last week</span>
            </div>
          </div>

          <div className="kpi-card">
            <div className="kpi-header">
              <span className="kpi-label">Total Orders</span>
              <span className="kpi-icon">🛒</span>
            </div>
            <div className="kpi-value">{formatNumber(totalOrders)}</div>
            <div className={`kpi-change ${ordersGrowth >= 0 ? 'positive' : 'negative'}`}>
              {ordersGrowth >= 0 ? <FaArrowUp /> : <FaArrowDown />} {Math.abs(ordersGrowth).toFixed(2)}%
              <span className="kpi-period">vs last week</span>
            </div>
          </div>

          <div className="kpi-card">
            <div className="kpi-header">
              <span className="kpi-label">Total Visitors</span>
              <span className="kpi-icon">👁️</span>
            </div>
            <div className="kpi-value">{formatNumber(totalVisitors)}</div>
            <div className={`kpi-change ${visitorsGrowth >= 0 ? 'positive' : 'negative'}`}>
              {visitorsGrowth >= 0 ? <FaArrowUp /> : <FaArrowDown />} {Math.abs(visitorsGrowth).toFixed(2)}%
              <span className="kpi-period">vs last week</span>
            </div>
          </div>
        </div>

        {/* Charts Row */}
        <div className="charts-row">
          <div className="chart-container revenue-chart">
            <RevenueAnalyticsChart 
              snapshot={snapshot} 
              summary={summary}
            />
          </div>
          
          <div className="chart-container monthly-target">
            <MonthlyTargetWidget 
              snapshot={snapshot} 
              summary={summary}
            />
          </div>
        </div>

        {/* Widgets Row */}
        <div className="widgets-row">
          <div className="widget-container">
            <TopCategoriesWidget 
              snapshot={snapshot} 
              summary={summary}
            />
          </div>
          
          <div className="widget-container">
            <ActiveUsersWidget 
              snapshot={snapshot} 
              summary={summary}
            />
          </div>
          
          <div className="widget-container">
            <ConversionRateWidget 
              snapshot={snapshot} 
              summary={summary}
            />
          </div>
          
          <div className="widget-container">
            <TrafficSourcesWidget 
              snapshot={snapshot} 
              summary={summary}
            />
          </div>
        </div>
      </div>
    );
  };

  const renderContent = () => {
    switch (activeTab) {
      case 'dashboard':
        return renderDashboardContent();
      case 'orders':
        return <OrdersSection />;
      case 'products':
        return <ProductsSection />;
      case 'customers':
        return <CustomersSection />;
      case 'reports':
        return <ReportsSection />;
      case 'notifications':
        return <NotificationsSection />;
      default:
        return renderDashboardContent();
    }
  };

  return (
    <div className="manager-dashboard-container">
      {renderSidebar()}
      <div className="manager-main">
        {renderTopBar()}
        <div className="manager-content">
          {renderContent()}
        </div>
      </div>
    </div>
  );
};

export default ManagerDashboard;
