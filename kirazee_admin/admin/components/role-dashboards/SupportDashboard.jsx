import { useState, useEffect } from 'react';
import SupportService from '../../services/supportService';
import '../../../css/admin/RoleDashboards.css';
import { FaSpinner, FaTicketAlt, FaClock, FaUserCheck, FaUsers, FaShoppingCart, FaCreditCard, FaShippingFast, FaUserCircle } from 'react-icons/fa';
import { MdRefresh } from 'react-icons/md';

const SupportDashboard = () => {
  const [dashboardData, setDashboardData] = useState({
    supportTickets: {},
    customerIssues: {},
    recentActivity: []
  });
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [lastUpdated, setLastUpdated] = useState(new Date());

  useEffect(() => {
    fetchSupportData();
  }, []);

  const fetchSupportData = async () => {
      try {
        setLoading(true);
        setError(null);
        
        console.log('SupportDashboard: Fetching data from support service...');
        console.log('API URL:', `${SupportService.SUPPORT_BASE_URL}/dashboard/`);
        
        // Use dedicated support service
        const supportData = await SupportService.getSupportDashboard();
        
        console.log('SupportDashboard: Raw API response:', supportData);
        
        if (supportData && supportData.success) {
          console.log('SupportDashboard: Real support data received:', supportData);
          
          // Transform support data for dashboard
          const transformedData = SupportService.transformSupportData(supportData);
          
          setDashboardData(transformedData);
          setLastUpdated(new Date());
          
          console.log('SupportDashboard: Transformed data:', transformedData);
        } else {
          throw new Error(supportData?.message || 'Support service returned unsuccessful response');
        }
    } catch (err) {
      const errorMessage = `Failed to load support dashboard data: ${err.message}`;
      setError(errorMessage);
      console.error('Support Dashboard error:', err);
      console.error('Error details:', {
        message: err.message,
        stack: err.stack,
        name: err.name
      });
    } finally {
      setLoading(false);
    }
  };

  if (loading) {
    return (
      <div className="dashboard-loading">
        <FaSpinner className="loading-spinner" />
        <p>Loading Support Dashboard...</p>
      </div>
    );
  }

  if (error) {
    return (
      <div className="dashboard-error">
        <h3>Error Loading Dashboard</h3>
        <p>{error}</p>
        <button onClick={fetchSupportData} className="retry-btn">
          <MdRefresh /> Retry
        </button>
      </div>
    );
  }

  return (
    <div className="dashboard-overview">
      {/* Header - Removed since it's now in main header */}

      {/* KPI Cards - Support Focus */}
      <div className="kpi-grid">
        <div className="kpi-cards orders">
          <div className="kpi-icon">
            <FaTicketAlt />
          </div>
          <div className="kpi-content">
            <h3>{dashboardData.supportTickets?.open || 0}</h3>
            <p>Open Tickets</p>
            <small>Need attention</small>
          </div>
        </div>

        <div className="kpi-cards businesses">
          <div className="kpi-icon">
            <FaUsers />
          </div>
          <div className="kpi-content">
            <h3>{dashboardData.customerIssues?.total || 0}</h3>
            <p>Total Customers</p>
            <small>With issues</small>
          </div>
        </div>

        <div className="kpi-cards delivery">
          <div className="kpi-icon">
            <FaClock />
          </div>
          <div className="kpi-content">
            <h3>{dashboardData.supportTickets?.averageResolutionTime || 'N/A'}</h3>
            <p>Avg Resolution</p>
            <small>Response time</small>
          </div>
        </div>

        <div className="kpi-cards support">
          <div className="kpi-icon">
            <FaUserCheck />
          </div>
          <div className="kpi-content">
            <h3>{dashboardData.supportTickets?.resolved || 0}</h3>
            <p>Resolved Issues</p>
            <small>Completed support</small>
          </div>
        </div>
      </div>

      {/* Support Metrics Overview */}
      <div className="support-section">
        <h3>Support Metrics Overview</h3>
        <div className="metrics-grid">
          <div className="metric-card">
            <h4>Total Tickets</h4>
            <p>{dashboardData.supportTickets?.total || 0}</p>
          </div>
          <div className="metric-card">
            <h4>Open Issues</h4>
            <p>{dashboardData.supportTickets?.open || 0}</p>
          </div>
          <div className="metric-card">
            <h4>In Progress</h4>
            <p>{dashboardData.supportTickets?.inProgress || 0}</p>
          </div>
          <div className="metric-card">
            <h4>Resolved</h4>
            <p>{dashboardData.supportTickets?.resolved || 0}</p>
          </div>
        </div>
      </div>

      {/* Customer Issues Overview */}
      <div className="support-section">
        <h3>Customer Issues by Category</h3>
        <div className="issues-grid">
          <div className="issue-card">
            <h4>
              <FaShoppingCart style={{ color: '#ff6b6b' }} />
              Order Issues
            </h4>
            <p>{dashboardData.customerIssues?.orderRelated || 0}</p>
            <small>Delivery, quality, missing items</small>
          </div>
          <div className="issue-card">
            <h4>
              <FaCreditCard style={{ color: '#4ecdc4' }} />
              Payment Issues
            </h4>
            <p>{dashboardData.customerIssues?.paymentRelated || 0}</p>
            <small>Failed payments, refunds</small>
          </div>
          <div className="issue-card">
            <h4>
              <FaShippingFast style={{ color: '#45b7d1' }} />
              Delivery Issues
            </h4>
            <p>{dashboardData.customerIssues?.deliveryRelated || 0}</p>
            <small>Late delivery, partner issues</small>
          </div>
          <div className="issue-card">
            <h4>
              <FaUserCircle style={{ color: '#f7b731' }} />
              Account Issues
            </h4>
            <p>{dashboardData.customerIssues?.accountRelated || 0}</p>
            <small>Login, registration, profile</small>
          </div>
        </div>
      </div>

      {/* Performance Metrics */}
      <div className="support-section">
        <h3>Performance Metrics</h3>
        <div className="performance-info">
          <p><strong>Average Resolution Time:</strong> {dashboardData.supportTickets?.averageResolutionTime || 'N/A'}</p>
          <p><strong>Resolution Rate:</strong> {dashboardData.performance?.resolutionRate || 0}%</p>
          <p><strong>Tickets Last 24h:</strong> {dashboardData.performance?.ticketsLast24h || 0}</p>
          <p><strong>Tickets Last 7 Days:</strong> {dashboardData.performance?.ticketsLast7d || 0}</p>
          <p><strong>Last Updated:</strong> {lastUpdated.toLocaleString()}</p>
        </div>
      </div>

      {/* Recent Support Activity */}
      <div className="support-section">
        <h3>Recent Support Activity</h3>
        {dashboardData.recentActivity && dashboardData.recentActivity.length > 0 ? (
          <div className="recent-activity-table">
            <table>
              <thead>
                <tr>
                  <th>Ticket ID</th>
                  <th>Customer</th>
                  <th>Subject</th>
                  <th>Category</th>
                  <th>Priority</th>
                  <th>Status</th>
                  <th>Agent</th>
                </tr>
              </thead>
              <tbody>
                {dashboardData.recentActivity.slice(0, 10).map((ticket, index) => (
                  <tr key={index}>
                    <td>{ticket.ticket_id}</td>
                    <td>{ticket.customer_name}</td>
                    <td>{ticket.subject}</td>
                    <td>{ticket.category}</td>
                    <td>
                      <span 
                        className="priority-badge"
                        style={{
                          backgroundColor: ticket.priority === 'Urgent' ? '#f44336' :
                                         ticket.priority === 'High' ? '#ff9800' :
                                         ticket.priority === 'Medium' ? '#2196f3' : '#4caf50',
                          color: 'white',
                          padding: '2px 8px',
                          borderRadius: '12px',
                          fontSize: '12px'
                        }}
                      >
                        {ticket.priority}
                      </span>
                    </td>
                    <td>
                      <span 
                        className="status-badge"
                        style={{
                          backgroundColor: ticket.status === 'Open' ? '#ff9800' :
                                         ticket.status === 'In Progress' ? '#2196f3' :
                                         ticket.status === 'Resolved' ? '#4caf50' : '#9e9e9e',
                          color: 'white',
                          padding: '2px 8px',
                          borderRadius: '12px',
                          fontSize: '12px'
                        }}
                      >
                        {ticket.status}
                      </span>
                    </td>
                    <td>{ticket.assigned_agent || 'Unassigned'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <div className="no-data-message">
            <p>No recent support activity available</p>
          </div>
        )}
      </div>
    </div>
  );
};

export default SupportDashboard;
