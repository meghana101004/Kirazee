import React, { useState, useEffect } from 'react';
import { 
  FaBell, FaCheckCircle, FaExclamationTriangle, FaInfoCircle,
  FaShoppingCart, FaUsers, FaStore, FaTrash, FaCheck, FaPaperPlane, FaPlus
} from 'react-icons/fa';
import { MdRefresh } from 'react-icons/md';

const NotificationsSection = () => {
  const [notifications, setNotifications] = useState([]);
  const [filter, setFilter] = useState('all');
  const [loading, setLoading] = useState(true);
  const [showSendModal, setShowSendModal] = useState(false);
  const [sendingNotification, setSendingNotification] = useState(false);
  
  // Form state for sending notifications
  const [notificationForm, setNotificationForm] = useState({
    recipient: 'all',
    recipientRole: '',
    recipientId: '',
    title: '',
    message: '',
    type: 'info',
    priority: 'normal'
  });

  useEffect(() => {
    fetchNotifications();
  }, []);

  const fetchNotifications = async () => {
    try {
      setLoading(true);
      // TODO: Replace with actual API call to fetch notifications
      // const response = await AdminService.getNotifications();
      // For now, show empty state until real notifications are sent
      setNotifications([]);
    } catch (error) {
      console.error('Error fetching notifications:', error);
      setNotifications([]);
    } finally {
      setLoading(false);
    }
  };

  const markAsRead = (id) => {
    setNotifications(prev =>
      prev.map(notif =>
        notif.id === id ? { ...notif, read: true } : notif
      )
    );
    // TODO: Call API to mark notification as read
  };

  const markAllAsRead = () => {
    setNotifications(prev =>
      prev.map(notif => ({ ...notif, read: true }))
    );
    // TODO: Call API to mark all notifications as read
  };

  const deleteNotification = (id) => {
    setNotifications(prev => prev.filter(notif => notif.id !== id));
    // TODO: Call API to delete notification
  };

  const clearAll = () => {
    if (window.confirm('Are you sure you want to clear all notifications?')) {
      setNotifications([]);
      // TODO: Call API to clear all notifications
    }
  };

  const handleSendNotification = async (e) => {
    e.preventDefault();
    
    if (!notificationForm.title || !notificationForm.message) {
      alert('Please fill in all required fields');
      return;
    }

    try {
      setSendingNotification(true);
      
      // TODO: Replace with actual API call
      // const response = await AdminService.sendNotification(notificationForm);
      
      // Simulate API call
      await new Promise(resolve => setTimeout(resolve, 1000));
      
      alert('Notification sent successfully!');
      
      // Reset form
      setNotificationForm({
        recipient: 'all',
        recipientRole: '',
        recipientId: '',
        title: '',
        message: '',
        type: 'info',
        priority: 'normal'
      });
      
      setShowSendModal(false);
      fetchNotifications();
    } catch (error) {
      console.error('Error sending notification:', error);
      alert('Failed to send notification. Please try again.');
    } finally {
      setSendingNotification(false);
    }
  };

  const getNotificationIcon = (type) => {
    switch (type) {
      case 'order': return <FaShoppingCart />;
      case 'customer': return <FaUsers />;
      case 'business': return <FaStore />;
      case 'alert': return <FaExclamationTriangle />;
      case 'success': return <FaCheckCircle />;
      default: return <FaInfoCircle />;
    }
  };

  const getNotificationColor = (type) => {
    switch (type) {
      case 'order': return '#FF8C42';
      case 'customer': return '#2196F3';
      case 'business': return '#FF9800';
      case 'alert': return '#F44336';
      case 'success': return '#4CAF50';
      default: return '#9C27B0';
    }
  };

  const filteredNotifications = notifications.filter(notif => {
    if (filter === 'all') return true;
    if (filter === 'unread') return !notif.read;
    return notif.type === filter;
  });

  const unreadCount = notifications.filter(n => !n.read).length;

  return (
    <div className="notifications-section">
      {/* Header */}
      <div className="notifications-header">
        <div className="header-left">
          <h2>
            <FaBell /> Notifications
            {unreadCount > 0 && <span className="unread-badge">{unreadCount}</span>}
          </h2>
          <p>{notifications.length} total notifications</p>
        </div>
        <div className="header-actions">
          <button 
            onClick={() => setShowSendModal(true)} 
            className="action-btn primary"
          >
            <FaPlus /> Send Notification
          </button>
          <button onClick={markAllAsRead} className="action-btn" disabled={unreadCount === 0}>
            <FaCheck /> Mark All Read
          </button>
          <button onClick={clearAll} className="action-btn danger" disabled={notifications.length === 0}>
            <FaTrash /> Clear All
          </button>
          <button onClick={fetchNotifications} className="refresh-btn">
            <MdRefresh /> Refresh
          </button>
        </div>
      </div>

      {/* Filters */}
      <div className="notifications-filters">
        <button
          className={`filter-btn ${filter === 'all' ? 'active' : ''}`}
          onClick={() => setFilter('all')}
        >
          All
        </button>
        <button
          className={`filter-btn ${filter === 'unread' ? 'active' : ''}`}
          onClick={() => setFilter('unread')}
        >
          Unread ({unreadCount})
        </button>
        <button
          className={`filter-btn ${filter === 'order' ? 'active' : ''}`}
          onClick={() => setFilter('order')}
        >
          Orders
        </button>
        <button
          className={`filter-btn ${filter === 'customer' ? 'active' : ''}`}
          onClick={() => setFilter('customer')}
        >
          Customers
        </button>
        <button
          className={`filter-btn ${filter === 'business' ? 'active' : ''}`}
          onClick={() => setFilter('business')}
        >
          Business
        </button>
        <button
          className={`filter-btn ${filter === 'alert' ? 'active' : ''}`}
          onClick={() => setFilter('alert')}
        >
          Alerts
        </button>
      </div>

      {/* Notifications List */}
      <div className="notifications-list">
        {loading ? (
          <div className="notifications-loading">
            <p>Loading notifications...</p>
          </div>
        ) : filteredNotifications.length === 0 ? (
          <div className="no-notifications">
            <FaBell />
            <p>No notifications yet</p>
            <small>Notifications will appear here when sent by superadmin or other users</small>
          </div>
        ) : (
          filteredNotifications.map((notif) => (
            <div
              key={notif.id}
              className={`notification-item ${notif.read ? 'read' : 'unread'}`}
              onClick={() => !notif.read && markAsRead(notif.id)}
            >
              <div 
                className="notification-icon" 
                style={{ backgroundColor: getNotificationColor(notif.type) }}
              >
                {getNotificationIcon(notif.type)}
              </div>
              <div className="notification-content">
                <div className="notification-header">
                  <h4>{notif.title}</h4>
                  <span className="notification-time">{notif.time}</span>
                </div>
                <p className="notification-message">{notif.message}</p>
                {notif.sender && (
                  <small className="notification-sender">From: {notif.sender}</small>
                )}
              </div>
              <div className="notification-actions">
                {!notif.read && (
                  <button
                    className="mark-read-btn"
                    onClick={(e) => {
                      e.stopPropagation();
                      markAsRead(notif.id);
                    }}
                    title="Mark as read"
                  >
                    <FaCheck />
                  </button>
                )}
                <button
                  className="delete-btn"
                  onClick={(e) => {
                    e.stopPropagation();
                    deleteNotification(notif.id);
                  }}
                  title="Delete"
                >
                  <FaTrash />
                </button>
              </div>
            </div>
          ))
        )}
      </div>

      {/* Send Notification Modal */}
      {showSendModal && (
        <div className="modal-overlay" onClick={() => setShowSendModal(false)}>
          <div className="modal-content send-notification-modal" onClick={(e) => e.stopPropagation()}>
            <div className="modal-header">
              <h2><FaPaperPlane /> Send Notification</h2>
              <button className="close-btn" onClick={() => setShowSendModal(false)}>×</button>
            </div>
            
            <form onSubmit={handleSendNotification} className="modal-body">
              <div className="form-group">
                <label>Recipient Type *</label>
                <select
                  value={notificationForm.recipient}
                  onChange={(e) => setNotificationForm({ ...notificationForm, recipient: e.target.value })}
                  required
                >
                  <option value="all">All Users</option>
                  <option value="role">Specific Role</option>
                  <option value="user">Specific User</option>
                </select>
              </div>

              {notificationForm.recipient === 'role' && (
                <div className="form-group">
                  <label>Select Role *</label>
                  <select
                    value={notificationForm.recipientRole}
                    onChange={(e) => setNotificationForm({ ...notificationForm, recipientRole: e.target.value })}
                    required
                  >
                    <option value="">Select a role...</option>
                    <option value="superadmin">Super Admin</option>
                    <option value="manager">Manager</option>
                    <option value="kyc">KYC Associates</option>
                    <option value="support">Support Team</option>
                    <option value="finance">Finance/CA</option>
                  </select>
                </div>
              )}

              {notificationForm.recipient === 'user' && (
                <div className="form-group">
                  <label>User ID or Email *</label>
                  <input
                    type="text"
                    value={notificationForm.recipientId}
                    onChange={(e) => setNotificationForm({ ...notificationForm, recipientId: e.target.value })}
                    placeholder="Enter user ID or email"
                    required
                  />
                </div>
              )}

              <div className="form-group">
                <label>Notification Type *</label>
                <select
                  value={notificationForm.type}
                  onChange={(e) => setNotificationForm({ ...notificationForm, type: e.target.value })}
                  required
                >
                  <option value="info">Information</option>
                  <option value="success">Success</option>
                  <option value="alert">Alert</option>
                  <option value="order">Order Related</option>
                  <option value="business">Business Related</option>
                  <option value="customer">Customer Related</option>
                </select>
              </div>

              <div className="form-group">
                <label>Priority *</label>
                <select
                  value={notificationForm.priority}
                  onChange={(e) => setNotificationForm({ ...notificationForm, priority: e.target.value })}
                  required
                >
                  <option value="low">Low</option>
                  <option value="normal">Normal</option>
                  <option value="high">High</option>
                  <option value="urgent">Urgent</option>
                </select>
              </div>

              <div className="form-group">
                <label>Title *</label>
                <input
                  type="text"
                  value={notificationForm.title}
                  onChange={(e) => setNotificationForm({ ...notificationForm, title: e.target.value })}
                  placeholder="Enter notification title"
                  required
                  maxLength={100}
                />
              </div>

              <div className="form-group">
                <label>Message *</label>
                <textarea
                  value={notificationForm.message}
                  onChange={(e) => setNotificationForm({ ...notificationForm, message: e.target.value })}
                  placeholder="Enter notification message"
                  required
                  rows={4}
                  maxLength={500}
                />
                <small>{notificationForm.message.length}/500 characters</small>
              </div>

              <div className="modal-actions">
                <button 
                  type="submit" 
                  className="btn-send"
                  disabled={sendingNotification}
                >
                  {sendingNotification ? (
                    <>Sending...</>
                  ) : (
                    <><FaPaperPlane /> Send Notification</>
                  )}
                </button>
                <button 
                  type="button" 
                  className="btn-cancel"
                  onClick={() => setShowSendModal(false)}
                  disabled={sendingNotification}
                >
                  Cancel
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
};

export default NotificationsSection;
