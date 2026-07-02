import React, { createContext, useContext, useState, useEffect } from 'react';

const AuthContext = createContext();

export const useAuth = () => {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error('useAuth must be used within an AuthProvider');
  }
  return context;
};

export const AuthProvider = ({ children }) => {
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    console.log('AuthContext: useEffect started');
    
    // Force loading to false after 2 seconds as a fallback
    const fallbackTimer = setTimeout(() => {
      console.log('AuthContext: Fallback timer - forcing loading to false');
      setLoading(false);
    }, 2000);
    
    // Direct check without timer
    try {
      const savedUser = localStorage.getItem('user');
      console.log('AuthContext: Saved user from localStorage:', savedUser);
      
      if (savedUser) {
        const userData = JSON.parse(savedUser);
        console.log('AuthContext: Parsed user data:', userData);
        setUser(userData);
      }
    } catch (error) {
      console.error('AuthContext: Error checking localStorage:', error);
    }
    
    console.log('AuthContext: Setting loading to false');
    setLoading(false);
    
    return () => clearTimeout(fallbackTimer);
  }, []);

  const login = (userData) => {
    setUser(userData);
    localStorage.setItem('user', JSON.stringify(userData));
  };

  const logout = () => {
    setUser(null);
    localStorage.removeItem('user');
  };

  const hasPermission = (requiredRole) => {
    if (!user) return false;
    
    // Role hierarchy: SuperAdmin > Manager > Support Team > KYC Associates > CA/Finance
    const roleHierarchy = {
      'SuperAdmin': 5,
      'Manager': 4,
      'Support Team': 3,
      'KYC Associates': 2,
      'CA/Finance': 1
    };
    
    const userRoleLevel = roleHierarchy[user.role] || 0;
    const requiredRoleLevel = roleHierarchy[requiredRole] || 0;
    
    return userRoleLevel >= requiredRoleLevel;
  };

  const canAccess = (feature) => {
    if (!user) return false;
    
    const permissions = {
      'SuperAdmin': [
        'dashboard', 'orders', 'businesses', 'business-review', 'delivery-partner-review',
        'delivery', 'notifications', 'analytics', 'snapshot-manager', 'platform-blueprint',
        'product-vision', 'user-journey', 'order-lifecycle', 'system-architecture',
        'database-design', 'api-specifications', 'operational-workflows', 'frontend-architecture'
      ],
      'Manager': [
        'dashboard', 'businesses', 'delivery', 'analytics', 'notifications'
      ],
      'Support Team': [
        'dashboard', 'orders', 'businesses', 'delivery', 'notifications'
      ],
      'KYC Associates': [
        'dashboard', 'business-review', 'delivery-partner-review'
      ],
      'CA/Finance': [
        'dashboard', 'analytics', 'businesses'
      ]
    };
    
    return permissions[user.role]?.includes(feature) || false;
  };

  const value = {
    user,
    login,
    logout,
    hasPermission,
    canAccess,
    loading,
    isAuthenticated: !!user
  };

  return (
    <AuthContext.Provider value={value}>
      {children}
    </AuthContext.Provider>
  );
};

export default AuthContext;
