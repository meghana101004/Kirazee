import React, { useState, useEffect } from 'react';
import LoginPage from './admin/pages/LoginPage';
import AdminDashboard from "./admin/pages/AdminDashboard.jsx";
import RoleBasedDashboard from './admin/pages/RoleBasedDashboard';

function AppContent() {
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    console.log('AppContent: useEffect running');
    
    // Direct check without timer
    const savedUser = localStorage.getItem('user');
    console.log('AppContent: Saved user found:', !!savedUser);
    
    if (savedUser) {
      try {
        const userData = JSON.parse(savedUser);
        console.log('AppContent: Found logged in user:', userData);
        setUser(userData);
      } catch (error) {
        console.error('AppContent: Error parsing user data:', error);
        localStorage.removeItem('user');
      }
    } else {
      console.log('AppContent: No saved user found');
    }
    
    console.log('AppContent: Setting loading to false');
    setLoading(false);
  }, []);

  const handleLogin = (userData) => {
    console.log('AppContent: Login successful with:', userData);
    setUser(userData);
    localStorage.setItem('user', JSON.stringify(userData));
  };

  const handleLogout = () => {
    console.log('AppContent: Logging out...');
    setUser(null);
    localStorage.removeItem('user');
  };

  // Show loading while checking authentication
  if (loading) {
    console.log('AppContent: Showing loading screen');
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
        <style>{`
          @keyframes spin {
            0% { transform: rotate(0deg); }
            100% { transform: rotate(360deg); }
          }
        `}</style>
      </div>
    );
  }

  console.log('AppContent: User:', user, 'Loading:', loading);

  // If no user, show login page
  if (!user) {
    console.log('AppContent: Showing login page');
    return <LoginPage onLogin={handleLogin} />;
  }

  // User is logged in, show appropriate dashboard
  console.log('AppContent: Showing dashboard for role:', user.role);
  
  if (user.role === 'SuperAdmin') {
    return (
      <div className="App">
        <AdminDashboard />
      </div>
    );
  }

  return (
    <div className="App">
      <RoleBasedDashboard />
    </div>
  );
}

export default AppContent;
