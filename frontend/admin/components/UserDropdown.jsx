import React, { useState, useRef, useEffect } from 'react';
import { FaUserCircle, FaCaretDown, FaSignOutAlt } from 'react-icons/fa';
import './UserDropdown.css';

const UserDropdown = () => {
  const [isOpen, setIsOpen] = useState(false);
  const dropdownRef = useRef(null);

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

  const toggleDropdown = () => {
    setIsOpen(!isOpen);
  };

  const handleLogout = () => {
    // Clear user data and reload page
    localStorage.removeItem('user');
    window.location.reload();
  };

  // Close dropdown when clicking outside
  useEffect(() => {
    const handleClickOutside = (event) => {
      if (dropdownRef.current && !dropdownRef.current.contains(event.target)) {
        setIsOpen(false);
      }
    };

    document.addEventListener('mousedown', handleClickOutside);
    return () => {
      document.removeEventListener('mousedown', handleClickOutside);
    };
  }, []);

  return (
    <div className="user-dropdown" ref={dropdownRef}>
      <div 
        className="dropdown-trigger-icon" 
        onClick={toggleDropdown}
        aria-expanded={isOpen}
        aria-haspopup="true"
      >
        <FaUserCircle className="user-icon" />
        <FaCaretDown className={`dropdown-arrow ${isOpen ? 'open' : ''}`} />
      </div>
      
      {isOpen && (
        <div 
          className="dropdown-menu" 
          style={{
            position: 'absolute',
            top: 'calc(100% + 8px)',
            right: 'auto',
            left: '-180px',
            background: 'white',
            border: '2px solid #F55D00',
            borderRadius: '12px',
            boxShadow: '0 8px 24px rgba(0, 0, 0, 0.12)',
            minWidth: '240px',
            zIndex: 9999
          }}
        >
          <div className="dropdown-header">
            <div className="user-avatar">
              <FaUserCircle />
            </div>
            <div className="user-details">
              <div className="user-display-name">{user?.name || 'User'}</div>
              <div className="user-role-badge">{user?.role || 'SuperAdmin'}</div>
            </div>
          </div>
          
          <div className="dropdown-divider"></div>
          
          <button className="dropdown-item logout-item" onClick={handleLogout}>
            <FaSignOutAlt className="item-icon" />
            <span>Logout</span>
          </button>
        </div>
      )}
    </div>
  );
};

export default UserDropdown;
