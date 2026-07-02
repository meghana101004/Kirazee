import React, { useState, useEffect } from 'react';
import {
  FaTachometerAlt,
  FaClipboardList,
  FaStore,
  FaTruck,
  FaChartBar,
  FaCogs,
  FaBuilding,
  FaShoppingCart,
  FaShippingFast,
  FaCheckCircle,
  FaBars,
  FaTimes,
  FaBell,
  FaDatabase,
  FaStar,
  FaEye,
  FaRoute,
  FaProjectDiagram,
  FaServer,
  FaCode,
  FaTasks,
  FaLaptopCode
} from 'react-icons/fa';
import '../../css/admin/AdminSidebar.css';

const AdminSidebar = ({ activeSection, setActiveSection, userRole }) => {
  const [isMobileOpen, setIsMobileOpen] = useState(false);
  const [isMobile, setIsMobile] = useState(false);

  useEffect(() => {
    const checkScreenSize = () => {
      setIsMobile(window.innerWidth <= 1024);
      if (window.innerWidth > 1024) {
        setIsMobileOpen(false);
      }
    };

    checkScreenSize();
    window.addEventListener('resize', checkScreenSize);
    return () => window.removeEventListener('resize', checkScreenSize);
  }, []);

  const toggleMobileSidebar = () => {
    setIsMobileOpen(!isMobileOpen);
  };

  const handleNavClick = (itemId) => {
    setActiveSection(itemId);
    // Close mobile sidebar when nav item is clicked
    if (isMobile) {
      setIsMobileOpen(false);
    }
  };
  
  const menuItems = [
    {
      heading: 'Overview'
    },
    {
      id: 'dashboard',
      label: 'Dashboard Overview',
      icon: <FaTachometerAlt />
    },
    // {
    //   id: 'snapshot-manager',
    //   label: 'Dashboard Snapshot',
    //   icon: <FaDatabase />,
    //   description: 'Manage dashboard data calculations'
    // },
    {
      heading: 'Verification & Reviews'
    },
    {
      id: 'business-review',
      label: 'Business Merchant KYC',
      icon: <FaCheckCircle />
    },
    {
      id: 'delivery-partner-review',
      label: 'Delivery Partner KYC',
      icon: <FaTruck />
    },

    {
      heading: 'Business Operations'
    },
    {
      id: 'businesses',
      label: 'Business Management',
      icon: <FaStore />
    },
    {
      id: 'orders',
      label: 'Order Management',
      icon: <FaClipboardList />
    },
    {
      id: 'delivery',
      label: 'Delivery Partner Management',
      icon: <FaClipboardList />
    },
    // {
    //   id: 'pricing',
    //   label: 'Pricing Management',
    //   icon: <FaCogs />
    // },

    {
      heading: 'Communication'
    },
    {
      id: 'notifications',
      label: 'Notification Management',
      icon: <FaBell />
    },
    // {
    //   id: 'announcements',
    //   label: 'Announcements',
    //   icon: <FaBell />
    // },

    {
      heading: 'Analytics'
    },
    {
      id: 'delivery-fleet',
      label: 'Delivery Fleet',
      icon: <FaTruck />
    },
    {
      id: 'analytics',
      label: 'Business Analytics & Reports',
      icon: <FaChartBar />
    },
    // {
    //   id: 'sales-reports',
    //   label: 'Sales Reports',
    //   icon: <FaChartBar />
    // }
        {
      heading: 'Kirazee Ecosystem'
    },
    {
      id: 'product-vision',
      label: 'Product Vision & Roadmap',
      icon: <FaEye />
    },
    {
      id: 'user-journey',
      label: 'User Journey & User Flows',
      icon: <FaRoute />
    },
    {
      id: 'order-lifecycle',
      label: 'Order Lifecycle Management',
      icon: <FaTasks />
    },
    {
      id: 'system-architecture',
      label: 'System & Platform Architecture',
      icon: <FaProjectDiagram />
    },
    {
      id: 'database-design',
      label: 'Database Design',
      icon: <FaServer />
    },
    {
      id: 'api-specifications',
      label: 'API & Service Specifications',
      icon: <FaCode />
    },
    {
      id: 'operational-workflows',
      label: 'Operational Workflows',
      icon: <FaTasks />
    },
    {
      id: 'frontend-architecture',
      label: 'Frontend Architecture',
      icon: <FaLaptopCode />
    },
  ];

  return (
    <>
      {/* Mobile Toggle Button */}
      {isMobile && (
        <button
          className="mobile-sidebar-toggle"
          onClick={toggleMobileSidebar}
          aria-label="Toggle sidebar"
        >
          {isMobileOpen ? <FaTimes /> : <FaBars />}
        </button>
      )}

      {/* Mobile Overlay */}
      {isMobile && isMobileOpen && (
        <div
          className="mobile-sidebar-overlay"
          onClick={() => setIsMobileOpen(false)}
        />
      )}

      {/* Sidebar */}
      <div className={`admin-sidebar ${isMobileOpen ? 'mobile-open' : ''}`}>
        {/* Navigation Menu */}
        <nav className="admin-nav">
          {menuItems.map((item, idx) => {
            if (item.heading) {
              return (
                <div key={`heading-${item.heading}`} className="nav-section-title">
                  {item.heading}
                </div>
              );
            }
            
            const isActive = activeSection === item.id;
            
            return (
              <button
                key={item.id || `item-${idx}`}
                className={`nav-item ${isActive ? 'active' : ''}`}
                onClick={() => handleNavClick(item.id)}
                data-active={isActive ? 'true' : 'false'}
                data-item-id={item.id}
                data-tooltip={item.label}
              >
                <span className="nav-icon">{item.icon}</span>
                <div className="nav-content">
                  <span className="nav-label">
                    {item.label}
                    {item.badge && <span className="nav-badge">{item.badge}</span>}
                  </span>
                  <span className="nav-description">{item.description}</span>
                </div>
              </button>
            );
          })}
        </nav>

      </div>
    </>
  );
};

export default AdminSidebar;
