import React from 'react';
import { dashboardSnapshotService } from '../services/dashboardSnapshotService';
import { 
  FiClock, 
  FiTrendingUp, 
  FiDollarSign, 
  FiShoppingCart, 
  FiUsers, 
  FiActivity,
  FiCheckCircle,
  FiAlertCircle,
  FiXCircle,
  FiInfo,
  FiDatabase,
  FiCalendar,
  FiTarget,
  FiEye,
  FiDownload
} from 'react-icons/fi';

const SnapshotHistory = ({ status, loading }) => {
  if (!status || !status.snapshot_history || status.snapshot_history.length === 0) {
    return (
      <div className="empty-state">
        <div className="empty-icon">
          <FiClock />
        </div>
        <h3 className="empty-title">No History Available</h3>
        <p className="empty-text">No snapshot history found. Start calculating snapshots to see history.</p>
      </div>
    );
  }

  const getCompletionColor = (rate) => {
    if (rate >= 90) return 'high';
    if (rate >= 70) return 'medium';
    return 'low';
  };

  const getCompletionIcon = (rate) => {
    if (rate >= 90) return <FiCheckCircle />;
    if (rate >= 70) return <FiAlertCircle />;
    return <FiXCircle />;
  };

  const formatTimeAgo = (minutes) => {
    if (minutes < 60) return `${minutes} min ago`;
    if (minutes < 1440) return `${Math.floor(minutes / 60)} hours ago`;
    return `${Math.floor(minutes / 1440)} days ago`;
  };

  return (
    <>
      {/* Summary Stats */}
      <div className="metrics-grid">
        <div className="metric-box">
          <div className="metric-label">
            <FiDatabase />
            Total
          </div>
          <div className="metric-number">{status.snapshot_history.length}</div>
          <div className="metric-info">
            Last 24h: {status.snapshot_history.filter(s => {
              const hoursAgo = (Date.now() - new Date(s.created_at)) / (1000 * 60 * 60);
              return hoursAgo <= 24;
            }).length}
          </div>
        </div>

        <div className="metric-box">
          <div className="metric-label">
            <FiDollarSign />
            Latest Revenue
          </div>
          <div className="metric-number">
            ₹{parseFloat(status.snapshot_history[0]?.total_revenue || 0).toLocaleString()}
          </div>
          <div className="metric-info">
            {status.snapshot_history[0]?.total_orders || 0} orders
          </div>
        </div>

        <div className="metric-box">
          <div className="metric-label">
            <FiActivity />
            Avg Completion
          </div>
          <div className="metric-number">
            {Math.round(
              status.snapshot_history.reduce((sum, s) => sum + s.completion_rate, 0) / 
              status.snapshot_history.length
            )}%
          </div>
          <div className="metric-info">
            Success rate: 98.5%
          </div>
        </div>
      </div>

      {/* History Table */}
      <div className="data-table">
        <table>
          <thead>
            <tr>
              <th>ID</th>
              <th>Created</th>
              <th>Revenue</th>
              <th>Orders</th>
              <th>Customers</th>
              <th>Completion</th>
            </tr>
          </thead>
          <tbody>
            {status.snapshot_history.map((snapshot) => (
              <tr key={snapshot.id}>
                <td>#{snapshot.id}</td>
                <td>{new Date(snapshot.created_at).toLocaleString()}</td>
                <td>₹{parseFloat(snapshot.total_revenue).toLocaleString()}</td>
                <td>{snapshot.total_orders}</td>
                <td>{snapshot.unique_customers}</td>
                <td>
                  <span className={`completion-badge ${getCompletionColor(snapshot.completion_rate)}`}>
                    {snapshot.completion_rate}%
                  </span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </>
  );
};

export default SnapshotHistory;
