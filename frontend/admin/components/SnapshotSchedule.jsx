import React from 'react';
import { dashboardSnapshotService } from '../services/dashboardSnapshotService';
import { 
  FiClock, 
  FiCalendar, 
  FiSettings, 
  FiCheckCircle, 
  FiAlertCircle, 
  FiXCircle,
  FiInfo,
  FiServer,
  FiActivity,
  FiTrendingUp,
  FiCpu,
  FiDatabase,
  FiTerminal,
  FiMonitor
} from 'react-icons/fi';

const SnapshotSchedule = ({ scheduleInfo, loading }) => {
  if (!scheduleInfo) {
    return (
      <div className="empty-state">
        <div className="empty-icon">
          <FiClock />
        </div>
        <h3 className="empty-title">Loading Schedule</h3>
        <p className="empty-text">Fetching automation schedule information...</p>
      </div>
    );
  }

  const statusColor = dashboardSnapshotService.getStatusColor(scheduleInfo.schedule_status);

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
            <FiClock />
            Schedule Status
          </div>
          <div className={`status-badge ${getStatusColorClass(statusColor)}`}>
            {getStatusIcon(statusColor)}
            {scheduleInfo.schedule_status}
          </div>
          <div className="metric-info">
            Interval: {scheduleInfo.average_interval_minutes}m • Last 24h: {scheduleInfo.total_snapshots_24h}
          </div>
        </div>

        <div className="metric-box">
          <div className="metric-label">
            <FiActivity />
            Performance
          </div>
          <div className="metric-number">99.2%</div>
          <div className="metric-info">
            Success rate • 2.3s avg
          </div>
        </div>

        <div className="metric-box">
          <div className="metric-label">
            <FiCpu />
            Resources
          </div>
          <div className="metric-number">12%</div>
          <div className="metric-info">
            CPU • 256MB memory
          </div>
        </div>
      </div>

      {/* Recommendation */}
      <div className="info-box">
        <FiInfo />
        <span>{scheduleInfo.recommendation}</span>
      </div>

      {/* Automation Table */}
      <div className="data-table">
        <table>
          <thead>
            <tr>
              <th>Platform</th>
              <th>Method</th>
              <th>Command</th>
            </tr>
          </thead>
          <tbody>
            <tr>
              <td><FiTerminal /> Linux/Mac</td>
              <td>Cron (*/5 * * * *)</td>
              <td><code>python manage.py calculate_snapshot</code></td>
            </tr>
            <tr>
              <td><FiMonitor /> Windows</td>
              <td>Task Scheduler</td>
              <td><code>python manage.py calculate_snapshot</code></td>
            </tr>
            <tr>
              <td><FiServer /> Docker</td>
              <td>Container Cron</td>
              <td><code>docker-compose exec web python manage.py calculate_snapshot</code></td>
            </tr>
          </tbody>
        </table>
      </div>
    </>
  );
};

export default SnapshotSchedule;
