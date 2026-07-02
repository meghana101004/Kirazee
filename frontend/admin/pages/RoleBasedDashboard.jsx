import React, { useState, useEffect } from 'react';
import ManagerDashboard from '../components/role-dashboards/ManagerDashboard';
import SupportDashboard from '../components/role-dashboards/SupportDashboard';
import KYCDashboard from '../components/role-dashboards/KYCDashboard';
import FinanceDashboard from '../components/role-dashboards/FinanceDashboard';
import DashboardOverview from '../components/DashboardOverview';
import UserDropdown from '../components/UserDropdown';

const RoleBasedDashboard = () => {
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    console.log('RoleBasedDashboard: Starting...');
    // Get user from localStorage
    const savedUser = localStorage.getItem('user');
    console.log('RoleBasedDashboard: Saved user found:', !!savedUser);
    
    if (savedUser) {
      try {
        const userData = JSON.parse(savedUser);
        console.log('RoleBasedDashboard: User data:', userData);
        setUser(userData);
      } catch (error) {
        console.error('RoleBasedDashboard: Error parsing user data:', error);
      }
    }
    
    console.log('RoleBasedDashboard: Setting loading to false');
    setLoading(false);
  }, []);

  // Simple role-based dashboard rendering
  const getDashboardHeading = () => {
    switch (user?.role) {
      case 'Manager':
        return 'Manager Dashboard';
      case 'Support Team':
        return 'Support Team Dashboard';
      case 'KYC Associates':
        return 'KYC Dashboard';
      case 'CA/Finance':
        return 'Finance Dashboard';
      case 'SuperAdmin':
        return 'Admin Dashboard';
      default:
        return 'Dashboard';
    }
  };

  const renderDashboard = () => {
    console.log('RoleBasedDashboard: Rendering content for user:', user?.role);
    return (
      <>
        {(() => {
          switch (user?.role) {
            case 'Manager':
              return <ManagerDashboard />;
            case 'Support Team':
              return <SupportDashboard />;
            case 'KYC Associates':
              return <KYCDashboard />;
            case 'CA/Finance':
              return <FinanceDashboard />;
            case 'SuperAdmin':
              return <DashboardOverview />;
            default:
              return (
                <div style={{ textAlign: 'center', padding: '50px' }}>
                  <h2>Welcome to Kirazee Dashboard</h2>
                  <p>Role: {user?.role || 'Unknown'}</p>
                  <p>Please contact administrator for proper role assignment.</p>
                </div>
              );
          }
        })()}
      </>
    );
  };

  if (loading) {
    console.log('RoleBasedDashboard: Still loading...');
    return (
      <div style={{ 
        display: 'flex', 
        justifyContent: 'center', 
        alignItems: 'center', 
        height: '100vh',
        flexDirection: 'column',
        fontFamily: 'Arial, sans-serif',
        background: 'linear-gradient(135deg, #F55D00 0%, #FDBF50 100%)',
        color: 'white'
      }}>
        <div style={{ 
          width: '40px', 
          height: '40px', 
          border: '4px solid rgba(255,255,255,0.3)', 
          borderTop: '4px solid #ffffff', 
          borderRadius: '50%', 
          animation: 'spin 1s linear infinite',
          marginBottom: '20px'
        }}></div>
        <p>Loading Kirazee Dashboard...</p>
        <small style={{ fontSize: '12px', opacity: 0.7 }}>
          User: {user?.role || 'Loading...'}
        </small>
        <style>{`
          @keyframes spin {
            0% { transform: rotate(0deg); }
            100% { transform: rotate(360deg); }
          }
        `}</style>
      </div>
    );
  }

  console.log('RoleBasedDashboard: Rendering content for user:', user?.role);
  
  const heading = getDashboardHeading();
  
  return (
    <div style={{ minHeight: '100vh', background: '#f5f5f5' }}>
      <div style={{ 
        background: 'white', 
        padding: '20px', 
        borderBottom: '1px solid #ddd',
        display: 'flex',
        justifyContent: 'space-between',
        alignItems: 'center'
      }}>
        <h1 style={{ margin: 0, color: '#333', fontSize: '24px', fontWeight: '600' }}>{heading}</h1>
        <UserDropdown />
      </div>
      <div style={{ padding: '20px' }}>
        {renderDashboard()}
      </div>
    </div>
  );
};

export default RoleBasedDashboard;
