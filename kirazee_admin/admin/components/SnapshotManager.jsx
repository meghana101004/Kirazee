import React, { useState, useEffect } from 'react';
import { dashboardSnapshotService } from '../services/dashboardSnapshotService';
import SnapshotStatus from './SnapshotStatus';
import SnapshotHistory from './SnapshotHistory';
import SnapshotSchedule from './SnapshotSchedule';
import '../../css/admin/SnapshotManager.css';

// Import professional icons
import { 
  FiDatabase, 
  FiRefreshCw, 
  FiPlay, 
  FiActivity, 
  FiTrendingUp, 
  FiClock,
  FiSettings,
  FiCheckCircle,
  FiAlertCircle,
  FiXCircle,
  FiBarChart2,
  FiCalendar,
  FiZap,
  FiShield,
  FiInfo
} from 'react-icons/fi';

const SnapshotManager = () => {
  const [snapshotStatus, setSnapshotStatus] = useState(null);
  const [scheduleInfo, setScheduleInfo] = useState(null);
  const [loading, setLoading] = useState(false);
  const [calculating, setCalculating] = useState(false);
  const [error, setError] = useState('');
  const [activeTab, setActiveTab] = useState('status');
  const [notification, setNotification] = useState(null);

  // Check permissions
  const isAdmin = dashboardSnapshotService.isAdmin();

  // Load initial data
  useEffect(() => {
    if (isAdmin) {
      loadSnapshotStatus();
      loadScheduleInfo();
      
      // Refresh status every 30 seconds
      const interval = setInterval(loadSnapshotStatus, 30000);
      return () => clearInterval(interval);
    }
  }, [isAdmin]);

  const loadSnapshotStatus = async () => {
    try {
      setLoading(true);
      const result = await dashboardSnapshotService.getSnapshotStatus();
      if (result.success) {
        setSnapshotStatus(result.data);
        setError('');
      } else {
        setError(result.message);
      }
    } catch (err) {
      setError('Failed to load snapshot status');
    } finally {
      setLoading(false);
    }
  };

  const loadScheduleInfo = async () => {
    try {
      const result = await dashboardSnapshotService.getScheduleInfo();
      if (result.success) {
        setScheduleInfo(result.data);
      }
    } catch (err) {
      console.error('Failed to load schedule info:', err);
    }
  };

  const handleCalculateSnapshot = async () => {
    try {
      setCalculating(true);
      setError('');
      
      const result = await dashboardSnapshotService.calculateSnapshot();
      
      if (result.success) {
        // Refresh data after calculation
        await loadSnapshotStatus();
        await loadScheduleInfo();
        
        // Extract metrics safely
        const metrics = result.data?.metrics || result.data || {};
        const revenue = metrics.total_revenue || 0;
        const orders = metrics.total_orders || 0;
        const customers = metrics.unique_customers || 0;
        
        // Show success notification
        showNotification('success', 'Snapshot calculated successfully!', {
          revenue: `₹${revenue.toLocaleString()}`,
          orders: orders,
          customers: customers
        });
      } else {
        setError(result.message);
        showNotification('error', result.message);
      }
    } catch (err) {
      const errorMsg = err.message || 'Failed to calculate snapshot';
      setError(errorMsg);
      showNotification('error', errorMsg);
    } finally {
      setCalculating(false);
    }
  };

  const showNotification = (type, message, details = null) => {
    setNotification({ type, message, details });
    setTimeout(() => setNotification(null), 5000);
  };

  const closeNotification = () => {
    setNotification(null);
  };

  if (!isAdmin) {
    return (
      <div className="snapshot-manager access-denied">
        <div className="error-message">
          <h3>Access Denied</h3>
          <p>Admin privileges required to access snapshot management.</p>
        </div>
      </div>
    );
  }

  return (
    <div className="snapshot-manager">
      {/* Notification Popup */}
      {notification && (
        <div className="notification-overlay" onClick={closeNotification}>
          <div className="notification-popup" onClick={(e) => e.stopPropagation()}>
            <div className={`notification-content ${notification.type}`}>
              <div className="notification-icon">
                {notification.type === 'success' ? <FiCheckCircle /> : <FiXCircle />}
              </div>
              <div className="notification-body">
                <h3>{notification.type === 'success' ? 'Success!' : 'Error'}</h3>
                <p>{notification.message}</p>
                {notification.details && notification.type === 'success' && (
                  <div className="notification-details">
                    <div className="detail-row">
                      <span>Revenue:</span>
                      <strong>{notification.details.revenue}</strong>
                    </div>
                    <div className="detail-row">
                      <span>Orders:</span>
                      <strong>{notification.details.orders}</strong>
                    </div>
                    <div className="detail-row">
                      <span>Customers:</span>
                      <strong>{notification.details.customers}</strong>
                    </div>
                  </div>
                )}
              </div>
              <button className="notification-close" onClick={closeNotification}>
                <FiXCircle />
              </button>
            </div>
            <button className="notification-btn" onClick={closeNotification}>
              OK
            </button>
          </div>
        </div>
      )}

      {/* Compact Header */}
      <div className="snapshot-header">
        <div className="header-left">
          <FiDatabase />
          <h1>Dashboard Snapshot</h1>
        </div>
        <div className="header-actions">
          <button 
            className="btn-refresh" 
            onClick={loadSnapshotStatus} 
            disabled={loading}
          >
            <FiRefreshCw className={loading ? 'spinning' : ''} />
            Refresh
          </button>
          <button 
            className="btn-calculate" 
            onClick={handleCalculateSnapshot} 
            disabled={calculating}
          >
            {calculating ? <FiRefreshCw className="spinning" /> : <FiPlay />}
            Calculate
          </button>
        </div>
      </div>

      {/* Error Alert */}
      {error && (
        <div className="alert-error">
          <FiXCircle />
          <span>{error}</span>
          <button onClick={() => setError('')}>×</button>
        </div>
      )}

      {/* Tabs */}
      <div className="tabs">
        <button 
          className={activeTab === 'status' ? 'active' : ''}
          onClick={() => setActiveTab('status')}
        >
          <FiBarChart2 />
          Status
        </button>
        <button 
          className={activeTab === 'history' ? 'active' : ''}
          onClick={() => setActiveTab('history')}
        >
          <FiClock />
          History
        </button>
        <button 
          className={activeTab === 'schedule' ? 'active' : ''}
          onClick={() => setActiveTab('schedule')}
        >
          <FiSettings />
          Schedule
        </button>
      </div>

      {/* Tab Content */}
      <div className="tab-content">
        {activeTab === 'status' && (
          <SnapshotStatus 
            status={snapshotStatus} 
            loading={loading}
            onRefresh={loadSnapshotStatus}
          />
        )}
        
        {activeTab === 'history' && (
          <SnapshotHistory 
            status={snapshotStatus}
            loading={loading}
          />
        )}
        
        {activeTab === 'schedule' && (
          <SnapshotSchedule 
            scheduleInfo={scheduleInfo}
            loading={loading}
          />
        )}
      </div>
    </div>
  );
};

export default SnapshotManager;
