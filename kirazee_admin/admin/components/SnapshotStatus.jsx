import React from 'react';
import { dashboardSnapshotService } from '../services/dashboardSnapshotService';
import { 
  FiActivity, 
  FiTrendingUp, 
  FiUsers, 
  FiShoppingCart, 
  FiDollarSign, 
  FiClock,
  FiRefreshCw,
  FiCheckCircle,
  FiAlertCircle,
  FiXCircle,
  FiInfo,
  FiDatabase
} from 'react-icons/fi';

const SnapshotStatus = ({ status, loading, onRefresh }) => {
  if (!status) {
    return (
      <div className="empty-state">
        <div className="empty-icon">
          <FiDatabase />
        </div>
        <h3 className="empty-title">Loading Status</h3>
        <p className="empty-text">Fetching dashboard snapshot information...</p>
      </div>
    );
  }

  const statusColor = dashboardSnapshotService.getStatusColor(status.calculation_status);
  const latest = status.latest_snapshot;

  const getStatusIcon = (status) => {
    switch (status) {
      case 'healthy':
      case 'active':
        return;
      case 'stale':
      case 'irregular':
        return;
      case 'no_snapshots':
      case 'error':
        return;
      default:
        return;
    }
  };

  const getStatusColorClass = (status) => {
    switch (status) {
      case 'healthy':
      case 'active':
        return 'positive';
      case 'stale':
      case 'irregular':
        return 'neutral';
      case 'no_snapshots':
      case 'error':
        return 'negative';
      default:
        return 'neutral';
    }
  };

  return (
    <>
      {/* Compact Metrics */}
      <div className="metrics-grid">
        <div className="metric-box">
          <div className="metric-label">
            <FiActivity />
            Status
          </div>
          <div className={` ${getStatusColorClass(status.calculation_status)}`}>
         
            {status.calculation_status}
          </div>
          <div className="metric-info">
            Last: {latest?.time_since_last || 'Never'} • Age: {latest?.age_minutes || 0}m
          </div>
        </div>

        <div className="metric-box">
          <div className="metric-label">
            <FiTrendingUp />
            Completion
          </div>
          <div className="metric-number">{latest?.completion_rate || 0}%</div>
          <div className="metric-info">
            {status.total_snapshots} total snapshots
          </div>
        </div>
      </div>

      {/* Simple Table */}
      <div className="data-table">
        <table>
          <thead>
            <tr>
              <th>Component</th>
              <th>Status</th>
              <th>Last Updated</th>
            </tr>
          </thead>
          <tbody>
            <tr>
              <td>
                <FiDatabase /> Dashboard Data
              </td>
              <td>
                <span className={`status-badge ${getStatusColorClass(status.calculation_status)}`}>
                  {getStatusIcon(statusColor)}
                  {status.calculation_status}
                </span>
              </td>
              <td>{latest?.time_since_last || 'Never'}</td>
            </tr>
            <tr>
              <td>
                <FiShoppingCart /> Order Processing
              </td>
              <td>
                <span className="status-badge positive">
                  Operational
                </span>
              </td>
              <td>2 min ago</td>
            </tr>
            <tr>
              <td>
                <FiUsers /> User Analytics
              </td>
              <td>
                <span className="status-badge positive">
                  Healthy
                </span>
              </td>
              <td>5 min ago</td>
            </tr>
          </tbody>
        </table>
      </div>
    </>
  );
};

export default SnapshotStatus;
