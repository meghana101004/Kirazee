import React from 'react';
import { FaSignOutAlt } from 'react-icons/fa';
import './LogoutButton.css';

const LogoutButton = () => {
  const handleLogout = () => {
    // Clear user data and reload page
    localStorage.removeItem('user');
    window.location.reload();
  };

  // Get user info from localStorage
  const getUserInfo = () => {
    try {
      const savedUser = localStorage.getItem('user');
      if (savedUser) {
        return JSON.parse(savedUser);
      }
    } catch (error) {
      console.error('Error parsing user data:', error);
    }
    return null;
  };

  const user = getUserInfo();

  return (
    <div className="logout-container">
      <div className="user-info">
        <span className="user-name">{user?.name || 'User'}</span>
        <span className="user-role">{user?.role || 'Guest'}</span>
      </div>
      <button className="logout-button" onClick={handleLogout} title="Logout">
        <FaSignOutAlt />
        <span>Logout</span>
      </button>
    </div>
  );
};

export default LogoutButton;
