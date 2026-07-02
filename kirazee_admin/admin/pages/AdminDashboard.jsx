import React, { useState, useEffect } from 'react';
import AdminSidebar from '../components/AdminSidebar';
import UserDropdown from '../components/UserDropdown';
import DashboardOverview from '../components/DashboardOverview';
import OrderManagement from '../components/OrderManagement';
import BusinessManagement from '../components/BusinessManagement';
import BusinessReview from '../components/BusinessReview';
import DeliveryPartnerReview from '../components/DeliveryPartnerReview';
import DeliveryFleet from '../components/DeliveryFleet';
import DeliveryPartnerDetails from '../components/DeliveryPartnerDetails';
import BusinessDetails from './BusinessDetails';
import BusinessDetailsTabbed from './BusinessDetailsTabbed';
import Analytics from '../components/Analytics';
import Analytics_Enhanced from '../components/Analytics_Enhanced';
import NotificationManagement from '../components/NotificationManagement';
import SnapshotManager from '../components/SnapshotManager';
import PlatformBlueprint from '../components/PlatformBlueprint';
import '../../css/admin/AdminDashboard.css';
import '../../css/admin/MobileResponsive.css';

const AdminDashboard = () => {
  const [activeSection, setActiveSection] = useState('dashboard');
  const [selectedProviderId, setSelectedProviderId] = useState(null);
  const [selectedProviderData, setSelectedProviderData] = useState(null);
  const [selectedBusinessId, setSelectedBusinessId] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    // Admin dashboard is now accessible without token authentication
    setLoading(false);
    
    // Check if we should show business details (from hash)
    const handleHashChange = () => {
      const hash = window.location.hash.replace('#', '');
      console.log('AdminDashboard - Hash changed to:', hash);
      
      if (hash.startsWith('business-details-tabbed/')) {
        const businessId = hash.replace('business-details-tabbed/', '');
        setSelectedBusinessId(businessId);
        setActiveSection('business-details-tabbed');
      } else if (hash.startsWith('business-details/')) {
        const businessId = hash.replace('business-details/', '');
        setSelectedBusinessId(businessId);
        setActiveSection('business-details');
      } else if (hash === 'business-details') {
        setActiveSection('business-details');
      } else if (hash === 'analytics') {
        setActiveSection('analytics');
      } else if (hash === 'businesses') {
        setActiveSection('businesses');
      } else if (hash === '' || hash === 'dashboard') {
        setActiveSection('dashboard');
      }
    };
    
    // Handle initial hash
    handleHashChange();
    
    // Listen for hash changes
    window.addEventListener('hashchange', handleHashChange);
    
    return () => {
      window.removeEventListener('hashchange', handleHashChange);
    };
  }, []);

  useEffect(() => {
    console.log('AdminDashboard activeSection changed to:', activeSection);
  }, [activeSection]);

  if (loading) {
    return (
      <div className="admin-loading">
        <div className="loading-spinner"></div>
        <h2>Loading Kirazee Admin Dashboard...</h2>
        <p className="loading-subtitle">Preparing your admin interface</p>
      </div>
    );
  }

  return (
    <div className="admin-dashboard">
      <AdminSidebar 
        activeSection={activeSection} 
        setActiveSection={setActiveSection} 
      />
      <div className="admin-main-content">
        <div className="admin-header">
          <div className="admin-header-left">
            <div className="header-logo">
              <div className="header-logo-icon">
                <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 512 512" fill="white" width="20" height="20">
                  <path d="M495.9 166.6c3.2 8.7 .5 18.4-6.4 24.6l-43.3 39.4c1.1 8.3 1.7 16.8 1.7 25.4s-.6 17.1-1.7 25.4l43.3 39.4c6.9 6.2 9.6 15.9 6.4 24.6c-4.4 11.9-9.7 23.3-15.8 34.3l-4.7 8.1c-6.6 11-14 21.4-22.1 31.2c-5.9 7.2-15.7 9.6-24.5 6.8l-55.7-17.7c-13.4 10.3-28.2 18.9-44 25.4l-12.5 57.1c-2 9.1-9 16.3-18.2 17.8c-13.8 2.3-28 3.5-42.5 3.5s-28.7-1.2-42.5-3.5c-9.2-1.5-16.2-8.7-18.2-17.8l-12.5-57.1c-15.8-6.5-30.6-15.1-44-25.4L83.1 425.9c-8.8 2.8-18.6 .3-24.5-6.8c-8.1-9.8-15.5-20.2-22.1-31.2l-4.7-8.1c-6.1-11-11.4-22.4-15.8-34.3c-3.2-8.7-.5-18.4 6.4-24.6l43.3-39.4C64.6 273.1 64 264.6 64 256s.6-17.1 1.7-25.4L22.4 191.2c-6.9-6.2-9.6-15.9-6.4-24.6c4.4-11.9 9.7-23.3 15.8-34.3l4.7-8.1c6.6-11 14-21.4 22.1-31.2c5.9-7.2 15.7-9.6 24.5-6.8l55.7 17.7c13.4-10.3 28.2-18.9 44-25.4l12.5-57.1c2-9.1 9-16.3 18.2-17.8C227.3 1.2 241.5 0 256 0s28.7 1.2 42.5 3.5c9.2 1.5 16.2 8.7 18.2 17.8l12.5 57.1c15.8 6.5 30.6 15.1 44 25.4l55.7-17.7c8.8-2.8 18.6-.3 24.5 6.8c8.1 9.8 15.5 20.2 22.1 31.2l4.7 8.1c6.1 11 11.4 22.4 15.8 34.3zM256 336a80 80 0 1 0 0-160 80 80 0 1 0 0 160z"/>
                </svg>
              </div>
              <div className="header-logo-text">
                <h2>Kirazee</h2>
                <span>SuperAdmin Panel</span>
              </div>
            </div>
          </div>
          <div className="admin-header-right">
            <UserDropdown />
          </div>
        </div>
        <div className="admin-content">
          {activeSection === 'dashboard' && <DashboardOverview />}
          {activeSection === 'orders' && <OrderManagement />}
          {activeSection === 'businesses' && <BusinessManagement />}
          {activeSection === 'business-details' && <BusinessDetails />}
          {activeSection === 'business-details-tabbed' && <BusinessDetailsTabbed businessId={selectedBusinessId} />}
          {activeSection === 'business-review' && <BusinessReview />}
          {activeSection === 'delivery-partner-review' && <DeliveryPartnerReview />}
          {(activeSection === 'delivery' || activeSection === 'delivery-fleet') && (
            <DeliveryFleet onViewDetails={(providerId, providerData) => {
              setSelectedProviderId(providerId);
              setSelectedProviderData(providerData);
              setActiveSection('delivery-details');
            }} />
          )}
          {activeSection === 'delivery-details' && (
            <DeliveryPartnerDetails 
              providerId={selectedProviderId}
              providerData={selectedProviderData}
              onBack={() => {
                setSelectedProviderId(null);
                setSelectedProviderData(null);
                setActiveSection('delivery-fleet');
              }}
            />
          )}
          {activeSection === 'notifications' && <NotificationManagement />}
          {activeSection === 'analytics' && <Analytics_Enhanced />}
          {activeSection === 'snapshot-manager' && <SnapshotManager />}
          {(activeSection === 'platform-blueprint' || 
            activeSection === 'product-vision' || 
            activeSection === 'user-journey' || 
            activeSection === 'order-lifecycle' || 
            activeSection === 'system-architecture' || 
            activeSection === 'database-design' || 
            activeSection === 'api-specifications' || 
            activeSection === 'operational-workflows' || 
            activeSection === 'frontend-architecture') && (
            <PlatformBlueprint activeSection={activeSection} />
          )}
        </div>
      </div>
    </div>
  );
};

export default AdminDashboard;
