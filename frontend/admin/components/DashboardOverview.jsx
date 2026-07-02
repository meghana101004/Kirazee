import React, { useState, useEffect } from 'react';
import AdminService from '../services/adminService';
import { dashboardSnapshotService } from '../services/dashboardSnapshotService';
import '../../css/admin/DashboardOverview.css';
import { Modal, Tooltip, Progress, Table, Tag, Tabs, Empty, Avatar } from 'antd';
import { InfoCircleOutlined, UserOutlined, ShopOutlined, CarOutlined, HistoryOutlined } from '@ant-design/icons';
import { 
  MdRefresh,
  MdCurrencyRupee,
  MdShoppingBag,
  MdStorefront,
  MdGroup,
  MdTrendingUp,
  MdDeliveryDining
} from 'react-icons/md';
import { 
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip as RechartsTooltip, 
  ResponsiveContainer, PieChart, Pie, Cell, AreaChart, Area, Legend 
} from 'recharts';
import OrdersBreakdownChart from './charts/OrdersBreakdownChart';
import CustomerMetricsChart from './charts/CustomerMetricsChart';
import TopBusinessesRevenueChart from './charts/TopBusinessesRevenueChart';
import TopBusinessesOrdersChart from './charts/TopBusinessesOrdersChart';
import DeliveryPartnersChart from './charts/DeliveryPartnersChart';

// MetricInfoIcon component for professional tooltips
const MetricInfoIcon = ({ title, content }) => (
  <Tooltip title={<div style={{ maxWidth: 250 }}><strong>{title}</strong><br/>{content}</div>} placement="topRight">
    <InfoCircleOutlined style={{ color: '#1890ff', marginLeft: 6, cursor: 'help' }} />
  </Tooltip>
);

const DashboardOverview = () => {
  const [dashboardData, setDashboardData] = useState({
    platformSummary: {},
    recentOrders: [],
    businessStats: {},
    deliveryStats: {},
    summaryData: {
      revenueMetrics: {},
      orderMetrics: {},
      deliveryPartners: [],
      orderStatusBreakdown: []
    }
  });
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [modalVisible, setModalVisible] = useState(false);
  const [modalType, setModalType] = useState(null);
  const [lastUpdated, setLastUpdated] = useState(new Date());
  const [activeCustomerTab, setActiveCustomerTab] = useState('unique');

  useEffect(() => {
    fetchDashboardData();
  }, []);

  const fetchDashboardData = async () => {
    try {
      setLoading(true);
      setError(null);

      // Ensure we stay on dashboard section
      if (window.location.hash !== '#dashboard' && window.location.hash !== '') {
        window.location.hash = 'dashboard';
      }

      // FIRST: Trigger snapshot calculation
      try {
        const calculateResult = await dashboardSnapshotService.calculateSnapshot();
        if (!calculateResult.success) {
          console.warn('Snapshot calculation warning:', calculateResult.message);
        }
      } catch (calcError) {
        console.warn('Snapshot calculation error:', calcError);
      }

      // Add a small delay to ensure the new snapshot is available
      await new Promise(resolve => setTimeout(resolve, 1000));

      // Add timeout to prevent infinite loading
      const timeoutPromise = new Promise((_, reject) => 
        setTimeout(() => reject(new Error('Request timeout')), 5000)
      );

      // Call the NEW lightweight endpoint with timeout
      const data = await Promise.race([
        AdminService.getDashboardSnapshot(),
        timeoutPromise
      ]);

      if (data.success) {
        const transformedData = {
          platformSummary: {
            totalRevenue: data.data?.revenue?.total_revenue || 0,
            totalOrders: data.data?.orders?.total_orders || 0,
            activeBusinesses: data.data?.businesses?.active_businesses || 0,
            uniqueCustomers: data.data?.customers?.unique_customers || 0,
            recentCustomers: data.data?.customers?.recent_customers_details?.length || 0,
            averageOrderValue: data.data?.revenue?.average_order_value || 0,
            activeDeliveryPartners: data.data?.delivery?.active_delivery_partners || 0
          },
          recentOrders: [],
          businessStats: {
            totalBusinessCount: data.data?.businesses?.total_businesses || 0,
            activeBusinessCount: data.data?.businesses?.active_businesses || 0,
            nonVerifiedCount: (data.data?.businesses?.total_businesses || 0) - (data.data?.businesses?.paid_businesses || 0),
            paymentPendingCount: 0
          },
          deliveryStats: {
            activePartners: data.data?.delivery?.available_drivers || 0,
            ordersInTransit: data.data?.orders?.active_orders || 0,
            completedToday: data.data?.orders?.completed_orders || 0,
            busyPartners: data.data?.delivery?.busy_drivers || 0
          },
          revenueByBusiness: [],
          ordersByBusiness: [],
          deliveryPartners: [],
          userAnalytics: {
            active_users: data.data?.customers?.active_users || 0,
            inactive_users: (data.data?.customers?.total_users || 0) - (data.data?.customers?.active_users || 0),
            total_users: data.data?.customers?.total_users || 0,
            unique_customers_details: [],
            recent_customers_details: []
          },
          statusBreakdown: [],
          allBusinesses: [],
          ordersData: data.data?.orders || {},
          businessesData: data.data?.businesses || {},
          customersData: data.data?.customers || {}
        };

        setDashboardData(transformedData);
        
        // Set the last updated time to the current time when refresh is clicked
        // This ensures the displayed time reflects when the user actually refreshed
        const currentTime = new Date();
        setLastUpdated(currentTime);

        // Also fetch detailed data from summary endpoint
        try {
          const summaryData = await AdminService.getDashboardSummary();
          
          console.log('📊 Summary API Response:', summaryData);
          console.log('📊 Revenue Metrics:', summaryData.revenue_metrics);
          console.log('📊 Order Metrics:', summaryData.order_metrics);
          console.log('📊 Delivery Partner Metrics:', summaryData.delivery_partner_metrics);
          
          if (summaryData.success) {
            setDashboardData(prev => ({
              ...prev,
              recentOrders: summaryData.recent_orders || [],
              revenueByBusiness: summaryData.revenue_metrics?.business_revenue_list || [],
              ordersByBusiness: summaryData.order_metrics?.business_order_breakdown || [],
              deliveryPartners: summaryData.delivery_partner_metrics?.partners_list || [],
              userAnalytics: {
                ...prev.userAnalytics,
                unique_customers_details: summaryData.user_analytics?.unique_customers_details || [],
                recent_customers_details: summaryData.user_analytics?.recent_customers_details || []
              },
              platformSummary: {
                ...prev.platformSummary,
                totalRevenue: summaryData.kpi_metrics?.total_revenue || prev.platformSummary.totalRevenue,
                recentCustomers: summaryData.user_analytics?.recent_customers_details?.length || 0
              },
              statusBreakdown: summaryData.debug_info?.status_breakdown || [],
              allBusinesses: summaryData.business_list_metrics?.all_businesses || [],
              summaryData: {
                revenueMetrics: summaryData.revenue_metrics || {},
                orderMetrics: summaryData.order_metrics || {},
                deliveryPartners: summaryData.delivery_partner_metrics?.partners_list || [],
                orderStatusBreakdown: summaryData.debug_info?.status_breakdown || [],
                recentOrders: summaryData.recent_orders || []
              }
            }));
            
            console.log('✅ Dashboard data updated with summary data');
          }
        } catch (summaryError) {
          console.warn('Failed to fetch summary data:', summaryError);
        }
      } else {
        throw new Error(data.message || 'API returned unsuccessful response');
      }
    } catch (err) {
      console.error('Dashboard error:', err);
      setError('Failed to load dashboard data. Please try again.');
      setLastUpdated(new Date());
    } finally {
      setLoading(false);
    }
  };

  const consolidateBusinessData = (businessData) => {
    // Define master businesses that should be excluded from the chart
    const masterBusinesses = ['FUSION STREET', 'FUSION STREAT', 'FUSION STREAT '];
    
    // Define sub-business display names with their master business indication
    const subBusinessDisplayNames = {
      'DILLI GALLI': 'DILLI GALLI (Fusion Street)',
      // Add more sub-business display names here
      // 'SUB_BUSINESS_NAME': 'SUB_BUSINESS_NAME (Master Business Name)',
    };

    console.log('Original business data:', businessData); // Debug log

    // Filter out master businesses and update display names for sub-businesses
    const filteredData = businessData
      .filter(business => {
        const businessName = business.business_name;
        const isMasterBusiness = masterBusinesses.includes(businessName);
        console.log(`Processing: ${businessName} - ${isMasterBusiness ? 'EXCLUDED (Master)' : 'INCLUDED'}`);
        return !isMasterBusiness;
      })
      .map(business => {
        const businessName = business.business_name;
        const displayName = subBusinessDisplayNames[businessName] || businessName;
        
        return {
          ...business,
          business_name: displayName
        };
      });

    const result = filteredData.sort((a, b) => b.total_orders - a.total_orders);
    console.log('Filtered and processed result:', result); // Debug log
    
    return result;
  };

  const openModal = (type) => {
    setModalType(type);
    setModalVisible(true);
  };

  const formatCurrency = (amount) => {
    return new Intl.NumberFormat('en-IN', {
      style: 'currency',
      currency: 'INR'
    }).format(amount);
  };

  const getStatusColor = (status) => {
    const statusLower = status?.toLowerCase() || '';
    const colors = {
      pending: '#ff9800',
      confirmed: '#2196f3',
      preparing: '#ff5722',
      ready: '#4caf50',
      delivered: '#8bc34a',
      cancelled: '#f44336',
      completed: '#4caf50',
      'in progress': '#2196f3',
      'on the way': '#ff9800'
    };
    return colors[statusLower] || '#666';
  };

  const renderModalContent = () => {
    switch (modalType) {
      case 'REVENUE':
        return (
          <div className="modal-content">
            <h3 className="modal-section-title">Revenue Distribution by Business</h3>
            <div className="revenue-summary-cards">
              {dashboardData.revenueByBusiness?.slice(0, 10).map((biz, index) => (
                <div key={index} className="modal-data-row">
                  <div className="modal-row-header">
                    <span>{biz.business_name}</span>
                    <strong>{formatCurrency(biz.raw_revenue || biz.revenue || 0)}</strong>
                  </div>
                  <Progress 
                    percent={dashboardData.platformSummary.totalRevenue > 0 ? 
                      ((biz.raw_revenue || biz.revenue || 0) / dashboardData.platformSummary.totalRevenue) * 100 : 0} 
                    strokeColor="#52c41a" 
                    showInfo={false} 
                  />
                </div>
              )) || <p style={{ textAlign: 'center', color: '#666', padding: '20px' }}>No revenue data available</p>}
            </div>
            <div className="modal-footer-stats">
              <div className="stat-mini"><span>Platform AOV:</span> <strong>{formatCurrency(dashboardData.platformSummary.averageOrderValue || 0)}</strong></div>
              <div className="stat-mini"><span>Top Earner:</span> <strong>{dashboardData.revenueByBusiness?.[0]?.business_name || 'N/A'}</strong></div>
            </div>
          </div>
        );

      case 'ORDERS':
        return (
          <Tabs defaultActiveKey="1" items={[
            {
              key: '1',
              label: 'Status Breakdown',
              children: (
                <div style={{ textAlign: 'center' }}>
                  <ResponsiveContainer width="100%" height={250}>
                    <PieChart>
                      <Pie 
                        data={dashboardData.statusBreakdown?.map((item, index) => ({
                          name: item.status || item.name,
                          value: item.count || item.value,
                          color: getStatusColor(item.status || item.name),
                          key: index
                        })) || []} 
                        innerRadius={60} 
                        outerRadius={80} 
                        paddingAngle={5} 
                        dataKey="value"
                      >
                        {dashboardData.statusBreakdown?.map((entry, index) => (
                          <Cell key={`cell-${index}`} fill={getStatusColor(entry.status || entry.name)} />
                        ))}
                      </Pie>
                      <RechartsTooltip />
                      <Legend />
                    </PieChart>
                  </ResponsiveContainer>
                </div>
              )
            },
            {
              key: '2',
              label: 'Recent Logs',
              children: (
                <Table 
                  size="small" 
                  pagination={false} 
                  dataSource={dashboardData.recentOrders?.slice(0, 10).map((order, index) => ({...order, key: index})) || []} 
                  columns={[
                    { title: 'Order ID', dataIndex: 'order_id', render: (id) => `#${id}` },
                    { title: 'Business', dataIndex: 'business_name' },
                    { title: 'Status', dataIndex: 'status', render: s => <Tag color={getStatusColor(s)}>{s}</Tag> }
                  ]} 
                />
              )
            }
          ]} />
        );

      case 'CUSTOMERS':
        return (
          <Tabs defaultActiveKey="1" items={[
            {
              key: '1',
              label: 'Top Loyal Customers',
              children: (
                <Table 
                  size="small" 
                  dataSource={dashboardData.userAnalytics?.unique_customers_details?.slice(0, 10).map((customer, index) => ({...customer, key: index})) || []} 
                  pagination={{pageSize: 5}} 
                  columns={[
                    { title: 'Name', dataIndex: 'name', render: (text) => <><UserOutlined style={{marginRight:8}}/>{text}</> },
                    { title: 'Email', dataIndex: 'email' },
                    { title: 'Last Order', dataIndex: 'last_order_date', render: (date) => date ? new Date(date).toLocaleDateString() : 'Never' }
                  ]} 
                />
              )
            },
            {
              key: '2',
              label: 'Recent Registrations',
              children: (
                <Table 
                  size="small" 
                  dataSource={dashboardData.userAnalytics?.recent_customers_details?.slice(0, 10).map((customer, index) => ({...customer, key: index})) || []} 
                  columns={[
                    { title: 'Customer', dataIndex: 'name' },
                    { title: 'Email', dataIndex: 'email' },
                    { title: 'Registration', dataIndex: 'registration_date', render: (date) => date ? new Date(date).toLocaleDateString() : 'Unknown' }
                  ]} 
                />
              )
            }
          ]} />
        );

      case 'BUSINESSES':
        return (
          <Table 
            size="small" 
            dataSource={dashboardData.summaryData?.orderMetrics?.business_order_breakdown?.slice(0, 10).map((business, index) => ({
              ...business,
              key: index,
              name: business.business_name,
              status: business.total_orders > 0 ? 'Active' : 'Inactive'
            })) || []} 
            columns={[
              { title: 'Business', dataIndex: 'name', render: (text) => <strong>{text}</strong> },
              { title: 'Status', dataIndex: 'status', render: s => (
                <Tag color={s === 'Active' ? 'green' : 'orange'}>{s}</Tag>
              )},
              { title: 'Orders', dataIndex: 'total_orders', render: v => <Tag color="blue">{v || 0}</Tag> },
              { title: 'Online Orders', dataIndex: 'online_orders', render: v => <Tag color="cyan">{v || 0}</Tag> },
              { title: 'Counter Orders', dataIndex: 'counter_orders', render: v => <Tag color="orange">{v || 0}</Tag> }
            ]} 
          />
        );

      case 'DELIVERY':
        return (
          <Table 
            size="small" 
            dataSource={dashboardData.deliveryPartners?.slice(0, 10).map((partner, index) => ({...partner, key: index})) || []} 
            columns={[
              { title: 'Partner', dataIndex: 'name' },
              { title: 'Rating', dataIndex: 'average_rating', render: r => <Tag color="gold">★ {r || 'N/A'}</Tag> },
              { title: 'Status', dataIndex: 'status', render: s => (
                <Tag color={s === 'Available' ? 'green' : s === 'Busy' ? 'orange' : 'red'}>{s}</Tag>
              )},
              { title: 'Completed', dataIndex: 'total_completed_orders' }
            ]} 
          />
        );

      default: return <Empty />;
    }
  };

  if (loading) {
    return (
      <div className="dashboard-loading">
        <div className="loading-spinner" style={{
          width: '40px',
          height: '40px',
          border: '4px solid #f3f3f3',
          borderTop: '4px solid #1890ff',
          borderRadius: '50%',
          animation: 'spin 1s linear infinite',
          marginBottom: '16px'
        }}></div>
        <p>Loading dashboard data...</p>
        <style>{`
          @keyframes spin {
            0% { transform: rotate(0deg); }
            100% { transform: rotate(360deg); }
          }
        `}</style>
      </div>
    );
  }

  if (error) {
    return (
      <div className="dashboard-error">
        <h3>Error Loading Dashboard</h3>
        <p>{error}</p>
        <button onClick={fetchDashboardData} className="retry-btn">
          <MdRefresh /> Retry
        </button>
      </div>
    );
  }

  return (
    <div className="pro-dashboard">
      <style>{`
        .pro-dashboard { background: #f4f7fa; min-height: 100vh; padding: 24px; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; }
        .header { display: flex; justify-content: space-between; align-items: center; background: white; padding: 16px 24px; border-radius: 12px; margin-bottom: 24px; box-shadow: 0 2px 8px rgba(0,0,0,0.05); }
        .header h1 { margin: 0; font-size: 22px; color: #001529; font-weight: 700; }
        
        .kpi-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(240px, 1fr)); gap: 20px;}
        .kpi-card { background: white; padding: 24px; border-radius: 12px; cursor: pointer; transition: all 0.3s cubic-bezier(.25,.8,.25,1); border: 1px solid transparent; }
        .kpi-card:hover { transform: translateY(-4px); box-shadow: 0 12px 20px rgba(0,0,0,0.08); border-color: #1890ff; }
        
        .icon-circle { width: 48px; height: 48px; border-radius: 12px; display: flex; align-items: center; justify-content: center; margin-bottom: 16px; border: 2px solid #e8e8e8; color: #1890ff; }
        .kpi-card:hover .icon-circle { border-color: #1890ff; color: #1890ff; }

        .kpi-label { font-size: 14px; color: #8c8c8c; display: flex; align-items: center; gap: 20px; }
        .kpi-value { font-size: 28px; font-weight: 800; color: #262626; margin: 8px 0; letter-spacing: -0.5px; }
        .kpi-subtext { font-size: 12px; color: #bfbfbf; }

        .main-layout { display: grid; grid-template-columns: 2fr 1fr; gap: 24px; }
        .panel { background: white; border-radius: 12px; padding: 24px; box-shadow: 0 2px 8px rgba(0,0,0,0.04); display: flex; flex-direction: column; }
        .panel-title { font-size: 16px; font-weight: 700; margin-bottom: 20px; color: #262626; display: flex; align-items: center; gap: 8px; }
        .table-container { flex: 1; overflow-y: auto; scrollbar-width: thin; scrollbar-color: transparent transparent; }
        .table-container::-webkit-scrollbar { width: 6px; }
        .table-container::-webkit-scrollbar-track { background: transparent; }
        .table-container::-webkit-scrollbar-thumb { background: transparent; }

        .modal-data-row { margin-bottom: 16px; }
        .modal-row-header { display: flex; justify-content: space-between; font-size: 13px; margin-bottom: 4px; }
        .modal-footer-stats { margin-top: 24px; padding-top: 16px; border-top: 1px dashed #e8e8e8; display: flex; gap: 20px; }
        .stat-mini { font-size: 12px; color: #8c8c8c; }
        .stat-mini strong { color: #262626; margin-left: 4px; }
        
        .activity-feed { max-height: 500px; overflow-y: auto; }
        
        .modal-content { border: none !important; }
        .modal-content .ant-modal-content { border: none !important; }
      `}</style>

      <div className="header">
        <div>
          <h1>Platform Intelligence Dashboard</h1>
          <div style={{fontSize: 12, color: '#8c8c8c'}}>Node Active • Updated: {lastUpdated.toLocaleTimeString()}</div>
        </div>
        <div style={{display:'flex', gap: 12, alignItems: 'center'}}>
           <button
             className="refresh-btn"
             onClick={(e) => {
               e.preventDefault();
               e.stopPropagation();
               fetchDashboardData();
             }}
             disabled={loading}
             type="button"
             style={{ 
               padding: '6px 12px', 
               border: '1px solid #d9d9d9', 
               borderRadius: '6px', 
               background: 'white', 
               cursor: 'pointer',
               display: 'flex',
               alignItems: 'center',
               color: 'black',
               gap: '6px'
             }}
           >
             <MdRefresh className={loading ? 'spin' : ''} />
             {loading ? ' Refreshing...' : ' Refresh'}
           </button>
        </div>
      </div>

      <div className="kpi-grid">
        <div className="kpi-card" onClick={() => openModal('REVENUE')}>
          <div className="kpi-label"><MdCurrencyRupee size={24} style={{color: '#FF986C'}}/> Total Revenue</div>
          <div className="kpi-value">{formatCurrency(dashboardData.platformSummary.totalRevenue || 0)}</div>
          <div className="kpi-subtext">Click to view per-business revenue</div>
        </div>

        <div className="kpi-card" onClick={() => openModal('ORDERS')}>
          <div className="kpi-label"><MdShoppingBag size={24} style={{color: '#FF986C'}}/> Total Orders</div>
          <div className="kpi-value">{(dashboardData.platformSummary.totalOrders || 0).toLocaleString()}</div>
          <div className="kpi-subtext">Platform-wide order volume</div>
        </div>

        <div className="kpi-card" onClick={() => openModal('BUSINESSES')}>
          <div className="kpi-label"><MdStorefront size={24} style={{color: '#FF986C'}}/> Active Businesses</div>
          <div className="kpi-value">{dashboardData.platformSummary.activeBusinesses || 0}</div>
          <div className="kpi-subtext">Currently operational partners</div>
        </div>

        <div className="kpi-card" onClick={() => openModal('CUSTOMERS')}>
          <div className="kpi-label"><MdGroup size={24} style={{color: '#FF986C'}}/> Unique Customers</div>
          <div className="kpi-value">{(dashboardData.platformSummary.uniqueCustomers || 0).toLocaleString()}</div>
          <div className="kpi-subtext">Recent: {dashboardData.platformSummary.recentCustomers || 0} new signups</div>
        </div>

        <div className="kpi-card" onClick={() => openModal('REVENUE')}>
          <div className="kpi-label"><MdTrendingUp size={24} style={{color: '#FF986C'}}/> Average Order Value</div>
          <div className="kpi-value">{formatCurrency(dashboardData.platformSummary.averageOrderValue || 0)}</div>
          <div className="kpi-subtext">Platform average transaction value</div>
        </div>

        <div className="kpi-card" onClick={() => openModal('DELIVERY')}>
          <div className="kpi-label"><MdDeliveryDining size={24} style={{color: '#FF986C'}}/> Active Partners</div>
          <div className="kpi-value">{dashboardData.platformSummary.activeDeliveryPartners || 0}</div>
          <div className="kpi-subtext">Currently available for delivery</div>
        </div>
      </div>

      {/* Business Performance Analytics Charts */}
      <div className="detailed-charts-section">
        <h3>Business Performance Analytics</h3>
        {console.log('📊 Dashboard summaryData:', dashboardData.summaryData)}
        {console.log('📊 Revenue Metrics:', dashboardData.summaryData?.revenueMetrics)}
        {console.log('📊 Business Revenue List:', dashboardData.summaryData?.revenueMetrics?.business_revenue_list)}
        <div className="dashboard-charts-grid">
          <TopBusinessesRevenueChart data={dashboardData.summaryData?.revenueMetrics?.business_revenue_list || []} />
          <TopBusinessesOrdersChart data={consolidateBusinessData(dashboardData.summaryData?.orderMetrics?.business_order_breakdown || [])} />
          <OrdersBreakdownChart data={dashboardData.ordersData || {}} />
          <CustomerMetricsChart data={dashboardData.customersData || {}} />
          <DeliveryPartnersChart data={dashboardData.summaryData?.deliveryPartners || []} />
        </div>
      </div>


      <div className="main-layout">
        <div className="panel">
          <div className="panel-title"><ShopOutlined /> Business Performance Breakdown</div>
          <div className="table-container">
            <Table 
              dataSource={dashboardData.summaryData?.revenueMetrics?.business_revenue_list?.slice(0, 10).map((business, index) => {
                // Find corresponding order data for this business
                const orderData = dashboardData.summaryData?.orderMetrics?.business_order_breakdown?.find(o => o.business_name === business.business_name);
                
                return {
                  key: index,
                  business_name: business.business_name,
                  revenue: business.raw_revenue || 0, // Use the actual revenue from database
                  total_orders: orderData?.total_orders || business.orders || 0,
                  average_order_value: (orderData?.total_orders || business.orders || 0) > 0 ? 
                    (business.raw_revenue || 0) / (orderData?.total_orders || business.orders || 1) : 0
                };
              }) || []} 
              pagination={false}
              size="middle"
              onRow={(record) => ({ onClick: () => { setModalType('REVENUE'); setModalVisible(true); } })}
              columns={[
                { title: 'Business Entity', dataIndex: 'business_name', key: 'business_name', render: (t) => <strong>{t}</strong> },
                { title: 'Revenue', dataIndex: 'revenue', key: 'revenue', render: v => formatCurrency(v || 0) },
                { title: 'Orders', dataIndex: 'total_orders', key: 'total_orders', render: v => <Tag color="blue">{v || 0}</Tag> },
                { title: 'AOV', dataIndex: 'average_order_value', key: 'average_order_value', render: v => formatCurrency(v || 0) }
              ]}
            />
          </div>
        </div>

        <div className="panel">
          <div className="panel-title"><HistoryOutlined /> Recent Live Activity</div>
          <div className="activity-feed">
             {dashboardData.recentOrders?.slice(0, 10).map((order, idx) => (
               <div key={idx} style={{padding: '12px 0', borderBottom: '1px solid #f0f0f0'}}>
                 <div style={{display: 'flex', justifyContent: 'space-between', marginBottom: 4}}>
                   <span style={{fontWeight: 600, fontSize: 13}}>#{order.order_id}</span>
                   <span style={{fontSize: 11, color: '#bfbfbf'}}>
                     {order.created_at ? new Date(order.created_at).toLocaleTimeString() : 'Unknown time'}
                   </span>
                 </div>
                 <div style={{fontSize: 12, color: '#595959'}}>{order.business_name} • {formatCurrency(order.final_amount || order.total_amount || 0)}</div>
                 <Tag color={getStatusColor(order.status)} style={{marginTop: 6, fontSize: 10}}>{order.status}</Tag>
               </div>
             )) || <p style={{ textAlign: 'center', color: '#666', padding: '20px' }}>No recent orders</p>}
          </div>
        </div>
      </div>
    </div>
  );
};

export default DashboardOverview;
