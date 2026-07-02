import React, { useState } from 'react';
import { FaCog, FaUser, FaBell, FaLock, FaPalette, FaSave } from 'react-icons/fa';

const SettingsSection = () => {
  const [activeTab, setActiveTab] = useState('profile');
  const [settings, setSettings] = useState({
    // Profile settings
    name: 'Marcus George',
    email: 'marcus@kirazee.com',
    phone: '+91 9876543210',
    role: 'Manager',
    
    // Notification settings
    emailNotifications: true,
    pushNotifications: true,
    orderNotifications: true,
    customerNotifications: false,
    reportNotifications: true,
    
    // Display settings
    theme: 'light',
    language: 'en',
    dateFormat: 'DD/MM/YYYY',
    currency: 'INR',
    
    // Security settings
    twoFactorAuth: false,
    sessionTimeout: '30'
  });

  const [saved, setSaved] = useState(false);

  const handleChange = (field, value) => {
    setSettings(prev => ({ ...prev, [field]: value }));
    setSaved(false);
  };

  const handleSave = () => {
    // Save settings logic here
    console.log('Saving settings:', settings);
    setSaved(true);
    setTimeout(() => setSaved(false), 3000);
  };

  const renderProfileSettings = () => (
    <div className="settings-content">
      <h3>Profile Settings</h3>
      <div className="settings-form">
        <div className="form-group">
          <label>Full Name</label>
          <input
            type="text"
            value={settings.name}
            onChange={(e) => handleChange('name', e.target.value)}
          />
        </div>
        <div className="form-group">
          <label>Email Address</label>
          <input
            type="email"
            value={settings.email}
            onChange={(e) => handleChange('email', e.target.value)}
          />
        </div>
        <div className="form-group">
          <label>Phone Number</label>
          <input
            type="tel"
            value={settings.phone}
            onChange={(e) => handleChange('phone', e.target.value)}
          />
        </div>
        <div className="form-group">
          <label>Role</label>
          <input
            type="text"
            value={settings.role}
            disabled
            className="disabled-input"
          />
        </div>
      </div>
    </div>
  );

  const renderNotificationSettings = () => (
    <div className="settings-content">
      <h3>Notification Preferences</h3>
      <div className="settings-form">
        <div className="toggle-group">
          <div className="toggle-item">
            <div className="toggle-info">
              <span className="toggle-label">Email Notifications</span>
              <span className="toggle-description">Receive notifications via email</span>
            </div>
            <label className="toggle-switch">
              <input
                type="checkbox"
                checked={settings.emailNotifications}
                onChange={(e) => handleChange('emailNotifications', e.target.checked)}
              />
              <span className="toggle-slider"></span>
            </label>
          </div>

          <div className="toggle-item">
            <div className="toggle-info">
              <span className="toggle-label">Push Notifications</span>
              <span className="toggle-description">Receive push notifications in browser</span>
            </div>
            <label className="toggle-switch">
              <input
                type="checkbox"
                checked={settings.pushNotifications}
                onChange={(e) => handleChange('pushNotifications', e.target.checked)}
              />
              <span className="toggle-slider"></span>
            </label>
          </div>

          <div className="toggle-item">
            <div className="toggle-info">
              <span className="toggle-label">Order Notifications</span>
              <span className="toggle-description">Get notified about new orders</span>
            </div>
            <label className="toggle-switch">
              <input
                type="checkbox"
                checked={settings.orderNotifications}
                onChange={(e) => handleChange('orderNotifications', e.target.checked)}
              />
              <span className="toggle-slider"></span>
            </label>
          </div>

          <div className="toggle-item">
            <div className="toggle-info">
              <span className="toggle-label">Customer Notifications</span>
              <span className="toggle-description">Get notified about new customers</span>
            </div>
            <label className="toggle-switch">
              <input
                type="checkbox"
                checked={settings.customerNotifications}
                onChange={(e) => handleChange('customerNotifications', e.target.checked)}
              />
              <span className="toggle-slider"></span>
            </label>
          </div>

          <div className="toggle-item">
            <div className="toggle-info">
              <span className="toggle-label">Report Notifications</span>
              <span className="toggle-description">Get notified when reports are ready</span>
            </div>
            <label className="toggle-switch">
              <input
                type="checkbox"
                checked={settings.reportNotifications}
                onChange={(e) => handleChange('reportNotifications', e.target.checked)}
              />
              <span className="toggle-slider"></span>
            </label>
          </div>
        </div>
      </div>
    </div>
  );

  const renderDisplaySettings = () => (
    <div className="settings-content">
      <h3>Display Settings</h3>
      <div className="settings-form">
        <div className="form-group">
          <label>Theme</label>
          <select
            value={settings.theme}
            onChange={(e) => handleChange('theme', e.target.value)}
          >
            <option value="light">Light</option>
            <option value="dark">Dark</option>
            <option value="auto">Auto</option>
          </select>
        </div>
        <div className="form-group">
          <label>Language</label>
          <select
            value={settings.language}
            onChange={(e) => handleChange('language', e.target.value)}
          >
            <option value="en">English</option>
            <option value="hi">Hindi</option>
            <option value="ta">Tamil</option>
          </select>
        </div>
        <div className="form-group">
          <label>Date Format</label>
          <select
            value={settings.dateFormat}
            onChange={(e) => handleChange('dateFormat', e.target.value)}
          >
            <option value="DD/MM/YYYY">DD/MM/YYYY</option>
            <option value="MM/DD/YYYY">MM/DD/YYYY</option>
            <option value="YYYY-MM-DD">YYYY-MM-DD</option>
          </select>
        </div>
        <div className="form-group">
          <label>Currency</label>
          <select
            value={settings.currency}
            onChange={(e) => handleChange('currency', e.target.value)}
          >
            <option value="INR">INR (₹)</option>
            <option value="USD">USD ($)</option>
            <option value="EUR">EUR (€)</option>
          </select>
        </div>
      </div>
    </div>
  );

  const renderSecuritySettings = () => (
    <div className="settings-content">
      <h3>Security Settings</h3>
      <div className="settings-form">
        <div className="toggle-group">
          <div className="toggle-item">
            <div className="toggle-info">
              <span className="toggle-label">Two-Factor Authentication</span>
              <span className="toggle-description">Add an extra layer of security to your account</span>
            </div>
            <label className="toggle-switch">
              <input
                type="checkbox"
                checked={settings.twoFactorAuth}
                onChange={(e) => handleChange('twoFactorAuth', e.target.checked)}
              />
              <span className="toggle-slider"></span>
            </label>
          </div>
        </div>

        <div className="form-group">
          <label>Session Timeout (minutes)</label>
          <select
            value={settings.sessionTimeout}
            onChange={(e) => handleChange('sessionTimeout', e.target.value)}
          >
            <option value="15">15 minutes</option>
            <option value="30">30 minutes</option>
            <option value="60">1 hour</option>
            <option value="120">2 hours</option>
          </select>
        </div>

        <div className="form-group">
          <label>Change Password</label>
          <button className="secondary-btn">Change Password</button>
        </div>
      </div>
    </div>
  );

  return (
    <div className="settings-section">
      {/* Header */}
      <div className="settings-header">
        <div className="header-left">
          <h2>
            <FaCog /> Settings
          </h2>
          <p>Manage your account and preferences</p>
        </div>
        <button 
          onClick={handleSave} 
          className={`save-btn ${saved ? 'saved' : ''}`}
        >
          <FaSave /> {saved ? 'Saved!' : 'Save Changes'}
        </button>
      </div>

      {/* Settings Tabs */}
      <div className="settings-container">
        <div className="settings-sidebar">
          <button
            className={`settings-tab ${activeTab === 'profile' ? 'active' : ''}`}
            onClick={() => setActiveTab('profile')}
          >
            <FaUser /> Profile
          </button>
          <button
            className={`settings-tab ${activeTab === 'notifications' ? 'active' : ''}`}
            onClick={() => setActiveTab('notifications')}
          >
            <FaBell /> Notifications
          </button>
          <button
            className={`settings-tab ${activeTab === 'display' ? 'active' : ''}`}
            onClick={() => setActiveTab('display')}
          >
            <FaPalette /> Display
          </button>
          <button
            className={`settings-tab ${activeTab === 'security' ? 'active' : ''}`}
            onClick={() => setActiveTab('security')}
          >
            <FaLock /> Security
          </button>
        </div>

        <div className="settings-main">
          {activeTab === 'profile' && renderProfileSettings()}
          {activeTab === 'notifications' && renderNotificationSettings()}
          {activeTab === 'display' && renderDisplaySettings()}
          {activeTab === 'security' && renderSecuritySettings()}
        </div>
      </div>
    </div>
  );
};

export default SettingsSection;
