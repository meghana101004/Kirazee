import React, { useEffect, useState, useMemo } from 'react';
import AdminService from '../services/adminService';
import '../../css/admin/BusinessDetails.css';
import { FaRupeeSign } from "react-icons/fa";
import { FaGift, FaCog, FaBuilding, FaTruck, FaStar, FaClipboardList, FaInbox, FaCheckCircle, FaCircle, FaUtensils, FaStore, FaShoppingCart, FaAppleAlt, FaChartBar, FaDollarSign, FaCreditCard, FaCogs, FaDownload, FaTrophy, FaUsers, FaCalendarAlt, FaCopy, FaMapMarkerAlt, FaPhone, FaEnvelope, FaFileDownload } from 'react-icons/fa';
import InventoryVisualization from '../components/InventoryVisualization';

// Simple chart components
const MiniBarChart = ({ data = [], color = '#3b82f6' }) => {
  const max = Math.max(...data.map(d => d.value || 0));

};

const MiniLineChart = ({ data = [], color = '#3b82f6' }) => {
  const max = Math.max(...data);
  const min = Math.min(...data);
  const range = max - min || 1;
  const points = data.map((v, i) => {
    const x = (i / (data.length - 1)) * 100;
    const y = 100 - ((v - min) / range) * 100;
    return `${x},${y}`;
  }).join(' ');
  return (
    <svg className="mini-line-chart" viewBox="0 0 100 100" preserveAspectRatio="none">
      <polyline points={points} fill="none" stroke={color} strokeWidth="2" />
    </svg>
  );
};

const DonutChart = ({ data = [], size = 120 }) => {
  const total = data.reduce((sum, d) => sum + (d.value || 0), 0);

  let currentAngle = -90;
  const radius = 40;
  const centerX = 50;
  const centerY = 50;

  return (
    <svg className="donut-chart" width={size} height={size} viewBox="0 0 100 100">
      {data.map((d, i) => {
        const percentage = (d.value / total) * 100;
        const angle = (percentage / 100) * 360;
        
        // Special case: if this slice is 100% (or very close), draw a full circle
        if (angle >= 359.9) {
          return (
            <circle 
              key={i} 
              cx={centerX} 
              cy={centerY} 
              r={radius} 
              fill={d.color || '#3b82f6'} 
            />
          );
        }
        
        const startAngle = currentAngle;
        const endAngle = currentAngle + angle;
        currentAngle = endAngle;

        const startRad = (startAngle * Math.PI) / 180;
        const endRad = (endAngle * Math.PI) / 180;

        const x1 = centerX + radius * Math.cos(startRad);
        const y1 = centerY + radius * Math.sin(startRad);
        const x2 = centerX + radius * Math.cos(endRad);
        const y2 = centerY + radius * Math.sin(endRad);

        const largeArc = angle > 180 ? 1 : 0;

        const pathData = [
          `M ${centerX} ${centerY}`,
          `L ${x1} ${y1}`,
          `A ${radius} ${radius} 0 ${largeArc} 1 ${x2} ${y2}`,
          'Z'
        ].join(' ');

        return <path key={i} d={pathData} fill={d.color || '#3b82f6'} />;
      })}
      <circle cx={centerX} cy={centerY} r={25} fill="white" />
    </svg>
  );
};

const PieChart = ({ data = [], size = 120 }) => {
  const total = data.reduce((sum, d) => sum + (d.value || 0), 0);

  let currentAngle = -90;
  const centerX = 50;
  const centerY = 50;
  const radius = 40;

  return (
    <svg className="pie-chart" width={size} height={size} viewBox="0 0 100 100">
      {data.map((d, i) => {
        const percentage = (d.value / total) * 100;
        const angle = (percentage / 100) * 360;
        
        const startAngle = currentAngle;
        const endAngle = currentAngle + angle;
        
        const largeArcFlag = angle > 180 ? 1 : 0;
        
        const startX = centerX + radius * Math.cos((startAngle * Math.PI) / 180);
        const startY = centerY + radius * Math.sin((startAngle * Math.PI) / 180);
        const endX = centerX + radius * Math.cos((endAngle * Math.PI) / 180);
        const endY = centerY + radius * Math.sin((endAngle * Math.PI) / 180);
        
        const pathData = [
          `M ${centerX} ${centerY}`,
          `L ${startX} ${startY}`,
          `A ${radius} ${radius} 0 ${largeArcFlag} 1 ${endX} ${endY}`,
          'Z'
        ].join(' ');
        
        currentAngle = endAngle;
        
        return (
          <g key={i}>
            <path
              d={pathData}
              fill={d.color}
              stroke="white"
              strokeWidth="1"
            />
            {percentage > 5 && (
              <text
                x={centerX + (radius * 0.7) * Math.cos(((startAngle + angle/2) * Math.PI) / 180)}
                y={centerY + (radius * 0.7) * Math.sin(((startAngle + angle/2) * Math.PI) / 180)}
                fill="white"
                fontSize="8"
                fontWeight="bold"
                textAnchor="middle"
                dominantBaseline="middle"
              >
                {`${percentage.toFixed(1)}%`}
              </text>
            )}
          </g>
        );
      })}
    </svg>
  );
};

const ConicalFlaskChart = ({ data = [], size = 120 }) => {
  const total = data.reduce((sum, d) => sum + (d.value || 0), 0);
  const maxValue = Math.max(...data.map(d => d.value || 0));
  
  // Sort data by value (descending)
  const sortedData = [...data].sort((a, b) => (b.value || 0) - (a.value || 0));
  
  const flaskWidth = size;
  const flaskHeight = size * 1.2; // Make it longer/taller
  const neckHeight = flaskHeight * 0.15;
  const bodyHeight = flaskHeight - neckHeight;
  
  // Professional color palette - no repeats
  const colorPalette = [
    '#1e40af', '#3b82f6', '#06b6d4', '#10b981', '#f59e0b', '#ef4444', '#8b5cf6', '#ec4899', 
    '#14b8a6', '#6366f1', '#84cc16', '#a855f7', '#e11d48', '#F55D00', '#f97316', '#c084fc', 
    '#64748b', '#059669', '#d946ef', '#722ed1', '#a78bfa', '#f87171', '#60a5fa', '#34d399', 
    '#fbbf24', '#f472b6', '#a78bfa', '#94a3b8', '#22d3ee', '#86efac', '#fca5a5', '#93c5fd', 
    '#fde047', '#c7d2fe', '#d4d4d8', '#fbbf24', '#fb923c', '#a3e635', '#e879f9', '#38bdf8', 
    '#4ade80', '#facc15', '#e11d48', '#F55D00', '#0ea5e9', '#22c55e'
  ];
  
  return (
    <svg className="conical-flask-chart" width={flaskWidth} height={flaskHeight} viewBox={`0 0 ${flaskWidth} ${flaskHeight}`}>
      {/* Flask Body - Trapezoid shape */}
      {sortedData.map((d, i) => {
        const percentage = (d.value / total) * 100;
        const widthRatio = d.value / maxValue;
        
        // Calculate trapezoid points for this segment
        const prevWidth = i > 0 ? (sortedData[i-1].value / maxValue) * flaskWidth : flaskWidth;
        const currentWidth = widthRatio * flaskWidth;
        
        const yTop = (i / sortedData.length) * bodyHeight;
        const yBottom = ((i + 1) / sortedData.length) * bodyHeight;
        
        // Create trapezoid path
        const pathData = [
          `M ${(flaskWidth - prevWidth) / 2} ${yTop}`,
          `L ${(flaskWidth + prevWidth) / 2} ${yTop}`,
          `L ${(flaskWidth + currentWidth) / 2} ${yBottom}`,
          `L ${(flaskWidth - currentWidth) / 2} ${yBottom}`,
          'Z'
        ].join(' ');
        
        // Use unique color from palette
        const segmentColor = colorPalette[i % colorPalette.length];
        
        return (
          <g key={i}>
            <path
              d={pathData}
              fill={segmentColor}
              stroke="rgba(255,255,255,0.3)"
              strokeWidth="1"
            />
            {/* Add gradient effect for larger segments */}
            {currentWidth > 15 && (
              <>
                <defs>
                  <linearGradient id={`gradient-${i}`} x1="0%" y1="0%" x2="100%" y2="100%">
                    <stop offset="0%" stopColor={segmentColor} stopOpacity="0.8" />
                    <stop offset="100%" stopColor={segmentColor} stopOpacity="1" />
                  </linearGradient>
                </defs>
                <path
                  d={pathData}
                  fill={`url(#gradient-${i})`}
                  stroke="rgba(255,255,255,0.5)"
                  strokeWidth="2"
                />
              </>
            )}
            {/* Add percentage label if segment is wide enough */}
            {currentWidth > 20 && (
              <text
                x={flaskWidth / 2}
                y={yTop + (yBottom - yTop) / 2}
                fill="white"
                fontSize="11"
                fontWeight="bold"
                textAnchor="middle"
                dominantBaseline="middle"
              >
                {`${percentage.toFixed(1)}%`}
              </text>
            )}
          </g>
        );
      })}
      
      {/* Flask Neck with gradient */}
      <defs>
        <linearGradient id="neckGradient" x1="0%" y1="0%" x2="0%" y2="100%">
          <stop offset="0%" stopColor="#e5e7eb" />
          <stop offset="100%" stopColor="#d1d5db" />
        </linearGradient>
      </defs>
      <rect
        x={flaskWidth * 0.4}
        y={bodyHeight}
        width={flaskWidth * 0.2}
        height={neckHeight}
        fill="url(#neckGradient)"
        stroke="#9ca3af"
        strokeWidth="1"
      />
      
      {/* Flask Top with metallic effect */}
      <defs>
        <radialGradient id="topGradient">
          <stop offset="0%" stopColor="#fbbf24" />
          <stop offset="70%" stopColor="#d1d5db" />
          <stop offset="100%" stopColor="#9ca3af" />
        </radialGradient>
      </defs>
      <ellipse
        cx={flaskWidth / 2}
        cy={bodyHeight}
        rx={flaskWidth * 0.15}
        ry={flaskWidth * 0.05}
        fill="url(#topGradient)"
        stroke="#6b7280"
        strokeWidth="2"
      />
      
      {/* Add shine effect */}
      <ellipse
        cx={flaskWidth / 2 - flaskWidth * 0.05}
        cy={bodyHeight - flaskWidth * 0.02}
        rx={flaskWidth * 0.08}
        ry={flaskWidth * 0.02}
        fill="rgba(255,255,255,0.4)"
        transform="rotate(-20)"
      />
    </svg>
  );
};

const HorizontalBarChart = ({ data = [], size = 120 }) => {
  const total = data.reduce((sum, d) => sum + (d.value || 0), 0);
  const maxValue = Math.max(...data.map(d => d.value || 0));
  
  // Sort data by value (descending)
  const sortedData = [...data].sort((a, b) => (b.value || 0) - (a.value || 0));
  
  const barWidth = size * 1.5; // Make it wider
  const barHeight = size * 0.8;
  const barSpacing = 2; // Small spacing between bars
  
  // Professional color palette - no repeats
  const colorPalette = [
    '#1e40af', '#3b82f6', '#06b6d4', '#10b981', '#f59e0b', '#ef4444', '#8b5cf6', '#ec4899', 
    '#14b8a6', '#6366f1', '#84cc16', '#a855f7', '#e11d48', '#F55D00', '#f97316', '#c084fc', 
    '#64748b', '#059669', '#d946ef', '#722ed1', '#a78bfa', '#f87171', '#60a5fa', '#34d399', 
    '#fbbf24', '#f472b6', '#a78bfa', '#94a3b8', '#22d3ee', '#86efac', '#fca5a5', '#93c5fd', 
    '#fde047', '#c7d2fe', '#d4d4d8', '#fbbf24', '#fb923c', '#a3e635', '#e879f9', '#38bdf8', 
    '#4ade80', '#facc15', '#e11d48', '#F55D00', '#0ea5e9', '#22c55e'
  ];
  
  return (
    <svg className="horizontal-bar-chart" width={barWidth} height={barHeight} viewBox={`0 0 ${barWidth} ${barHeight}`}>
      {sortedData.map((d, i) => {
        const percentage = (d.value / total) * 100;
        const barLength = (d.value / maxValue) * (barWidth * 0.8); // Use 80% of width for bars
        const barY = (i * (barHeight / sortedData.length)) + barSpacing;
        const barHeightPerItem = (barHeight / sortedData.length) - (barSpacing * 2);
        
        // Use unique color from palette
        const barColor = colorPalette[i % colorPalette.length];
        
        return (
          <g key={i}>
            {/* Bar with rounded corners */}
            <rect
              x={10}
              y={barY}
              width={barLength}
              height={barHeightPerItem}
              fill={barColor}
              rx="2"
              ry="2"
            />
            {/* Add gradient effect for longer bars */}
            {barLength > 20 && (
              <defs>
                <linearGradient id={`bar-gradient-${i}`} x1="0%" y1="0%" x2="100%" y2="0%">
                  <stop offset="0%" stopColor={barColor} stopOpacity="0.9" />
                  <stop offset="100%" stopColor={barColor} stopOpacity="1" />
                </linearGradient>
              </defs>
            )}
            {/* Add percentage label if bar is long enough */}
            {barLength > 40 && (
              <text
                x={barLength + 15}
                y={barY + barHeightPerItem / 2}
                fill="#374151"
                fontSize="10"
                fontWeight="500"
                textAnchor="start"
                dominantBaseline="middle"
              >
                {`${percentage.toFixed(1)}%`}
              </text>
            )}
          </g>
        );
      })}
    </svg>
  );
};

// Report Tabs Component
const ReportTabs = ({ activeTab, setActiveTab }) => {
  const tabs = [
    { id: 'overview', label: 'Overview', icon: <FaChartBar /> },
    { id: 'consumption', label: 'Consumption Report', icon: <FaUtensils /> },
    { id: 'consumer', label: 'Consumer Report', icon: <FaUsers /> },
    { id: 'sales', label: 'Sales Report', icon: <FaChartBar /> },
    { id: 'menu', label: 'Menu Report', icon: <FaAppleAlt /> },
    { id: 'performance', label: 'Performance Report', icon: <FaTrophy /> },
    { id: 'inventory', label: 'Inventory Report', icon: <FaCogs /> }
  ];

  return (
    <div style={{
      background: 'white',
      border: '1px solid #e5e7eb',
      borderRadius: '8px',
      padding: '16px',
      marginBottom: '16px',
      boxShadow: '0 1px 3px rgba(0,0,0,0.1)'
    }}>
      <div style={{
        display: 'flex',
        gap: '8px',
        borderBottom: '1px solid #e5e7eb',
        paddingBottom: '12px',
        marginBottom: '16px',
        flexWrap: 'wrap'
      }}>
        {tabs.map(tab => (
          <button
            key={tab.id}
            onClick={() => setActiveTab(tab.id)}
            style={{
              padding: '8px 16px',
              borderRadius: '6px',
              border: 'none',
              background: activeTab === tab.id ? '#3b82f6' : '#f3f4f6',
              color: activeTab === tab.id ? 'white' : '#374151',
              fontSize: '0.875rem',
              fontWeight: activeTab === tab.id ? '600' : '400',
              cursor: 'pointer',
              transition: 'all 0.2s',
              display: 'flex',
              alignItems: 'center',
              gap: '6px'
            }}
          >
            {tab.icon}
            {tab.label}
          </button>
        ))}
      </div>
    </div>
  );
};

// Tab Content Component
const TabContent = ({ activeTab }) => {
  const getTabContent = () => {
    return (
      <div style={{
        background: 'white',
        border: '1px solid #e5e7eb',
        borderRadius: '8px',
        padding: '60px',
        textAlign: 'center',
        boxShadow: '0 1px 3px rgba(0,0,0,0.1)',
        minHeight: '400px',
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        justifyContent: 'center'
      }}>
        <div style={{
          fontSize: '2.5rem',
          fontWeight: '700',
          color: '#9ca3af',
          marginBottom: '16px'
        }}>
          Coming Soon
        </div>
        <div style={{
          fontSize: '1.125rem',
          color: '#6b7280',
          marginBottom: '8px'
        }}>
          {activeTab.charAt(0).toUpperCase() + activeTab.slice(1)} Report
        </div>
        <div style={{
          fontSize: '0.875rem',
          color: '#9ca3af',
          maxWidth: '400px',
          lineHeight: '1.5'
        }}>
          This report is currently under development. We're working hard to bring you detailed analytics and insights for this section.
        </div>
      </div>
    );
  };

  return getTabContent();
};

const toCurrency = (n) => (n == null ? '-' : `₹${Number(n).toLocaleString('en-IN', { maximumFractionDigits: 2 })}`);
const toNumber = (n) => (n == null ? '-' : Number(n).toLocaleString('en-IN'));
const formatDate = (s) => { try { return s ? new Date(s).toLocaleString() : '-'; } catch (e) { return s || '-'; } };
const last4 = (v) => (v ? String(v).slice(-4) : '-');

// Excel download functions
const downloadMenuExcel = (menuData, businessType) => {
  const menuItems = menuData?.menu_items || [];
  const groceries = menuData?.grocery_products || [];

  // Combine menu items and grocery products
  const allItems = [
    ...menuItems.map(item => ({
      'Item Name': item.name || '-',
      'Type': 'Restaurant',
      'Category': item.category || '-',
      'Size': item.size_label || '-',
      'Price': item.price || 0,
      'Status': item.is_active ? 'Active' : 'Inactive',
      'Updated At': formatDate(item.updated_at),
      'Item ID': item.item_id || '-'
    })),
    ...groceries.map(product => ({
      'Item Name': product.name || '-',
      'Type': 'Grocery',
      'Category': product.category_id || '-',
      'Size': '-',
      'Price': product.price || 0,
      'Status': product.is_active !== false ? 'Active' : 'Inactive',
      'Updated At': formatDate(product.updated_at),
      'Item ID': product.product_id || '-'
    }))
  ];

  if (allItems.length === 0) {
    alert('No menu items to export');
    return;
  }

  // Convert to CSV
  const headers = Object.keys(allItems[0]);
  const csvContent = [
    headers.join(','),
    ...allItems.map(item =>
      headers.map(header => {
        const value = item[header];
        // Escape commas and quotes in CSV
        return typeof value === 'string' && (value.includes(',') || value.includes('"'))
          ? `"${value.replace(/"/g, '""')}"`
          : value;
      }).join(',')
    )
  ].join('\n');

  // Download file
  const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' });
  const link = document.createElement('a');
  const url = URL.createObjectURL(blob);
  link.setAttribute('href', url);
  link.setAttribute('download', `menu_items_${new Date().toISOString().split('T')[0]}.csv`);
  link.style.visibility = 'hidden';
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
};

const downloadPaymentsExcel = (paymentsData, orderData) => {
  const payments = paymentsData?.recent_payments || [];
  const orders = orderData || [];

  if (payments.length === 0) {
    alert('No payment data to export');
    return;
  }

  // Combine payment and order data
  const paymentOrderData = payments.map(payment => {
    const relatedOrder = orders.find(order => order.order_id === payment.order_id);
    return {
      'Payment ID': payment.id || '-',
      'Order ID': payment.order_id || '-',
      'Payment Status': payment.status || '-',
      'Payment Method': payment.method || '-',
      'Payment Amount': payment.amount || 0,
      'Order Status': relatedOrder?.status || relatedOrder?.order_status || '-',
      'Order Amount': relatedOrder?.amount || 0,
      'User ID': payment.user_id || relatedOrder?.user_id || relatedOrder?.customer_id || '-',
      'Customer Email': relatedOrder?.email || relatedOrder?.customer_email || '-',
      'Customer Phone': relatedOrder?.phone || relatedOrder?.mobile || relatedOrder?.customer_phone || '-',
      'Transaction ID': payment.transaction_id || payment.txn_id || payment.razorpay_payment_id || payment.payment_id || '-',
      'Payment Created': formatDate(payment.created_at),
      'Order Created': formatDate(relatedOrder?.created_at)
    };
  });

  // Convert to CSV
  const headers = Object.keys(paymentOrderData[0]);
  const csvContent = [
    headers.join(','),
    ...paymentOrderData.map(item =>
      headers.map(header => {
        const value = item[header];
        // Escape commas and quotes in CSV
        return typeof value === 'string' && (value.includes(',') || value.includes('"'))
          ? `"${value.replace(/"/g, '""')}"`
          : value;
      }).join(',')
    )
  ].join('\n');

  // Download file
  const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' });
  const link = document.createElement('a');
  const url = URL.createObjectURL(blob);
  link.setAttribute('href', url);
  link.setAttribute('download', `payments_orders_${new Date().toISOString().split('T')[0]}.csv`);
  link.style.visibility = 'hidden';
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
};

// Paginated Full Menu Section Component
function PaginatedFullMenuSection({ data }) {
  const [currentPage, setCurrentPage] = useState(1);
  const [itemsPerPage, setItemsPerPage] = useState(20);
  const menuItems = data?.menu_items || [];
  const groceries = data?.grocery_products || [];

  // Combine menu items and grocery products
  const allItems = [
    ...menuItems.map(item => ({ ...item, type: 'Restaurant', item_key: `menu_${item.item_id}` })),
    ...groceries.map(product => ({
      ...product,
      type: 'Grocery',
      item_key: `grocery_${product.product_id}`,
      item_id: product.product_id,
      category: product.subcategory || product.category_id,  // Use subcategory if available, fallback to category_id
      size_label: null,  // Remove size for grocery products
      price: product.price || 0,
      updated_at: product.updated_at,  // Use updated_at from backend
      is_active: true
    }))
  ];

  const totalPages = Math.ceil(allItems.length / itemsPerPage);
  const startIndex = (currentPage - 1) * itemsPerPage;
  const endIndex = startIndex + itemsPerPage;
  const currentItems = allItems.slice(startIndex, endIndex);

  return (
    <div>
      <div className="kpi-row">
        <div className="kpi"><div className="kpi-value">{toNumber(menuItems.length)}</div><div className="kpi-label">Restaurant Items</div></div>
        <div className="kpi"><div className="kpi-value">{toNumber(groceries.length)}</div><div className="kpi-label">Grocery Products</div></div>
        <div className="kpi"><div className="kpi-value">{toNumber(allItems.length)}</div><div className="kpi-label">Total Items</div></div>
      </div>
      <div className="scroll-x" style={{ marginTop: 12 }}>
        <table className="data-table">
          <thead>
            <tr>
              <th>Item</th>
              <th>Category</th>
              <th>Size</th>
              <th>Price</th>
              <th>Status</th>
              <th>Updated</th>
            </tr>
          </thead>
          <tbody>
            {currentItems.map(it => (
              <tr key={it.item_key}>
                <td>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                    {it.image && <img className="thumb" src={it.image} alt={it.name} />}
                    {it.name}
                  </div>
                </td>
                <td>{it.category || '-'}</td>
                <td>{it.size_label || '-'}</td>
                <td>{toCurrency(it.price)}</td>
                <td><span className={`badge ${it.is_active ? 'success' : 'neutral'}`}>{it.is_active ? 'Active' : 'Inactive'}</span></td>
                <td>{formatDate(it.updated_at)}</td>
              </tr>
            ))}
            {!allItems.length && (
              <tr>
                <td colSpan="6" className="muted">No items</td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
      {totalPages > 1 && (
        <>
          <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', gap: '8px', marginTop: '20px' }}>
            <button
              onClick={() => setCurrentPage(prev => Math.max(1, prev - 1))}
              disabled={currentPage === 1}
              style={{
                width: '40px',
                height: '40px',
                borderRadius: '12px',
                border: '1px solid #e5e7eb',
                background: 'white',
                color: '#6b7280',
                cursor: currentPage === 1 ? 'not-allowed' : 'pointer',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                fontSize: '1.2rem',
                opacity: currentPage === 1 ? 0.5 : 1,
                transition: 'all 0.2s'
              }}
            >
              ‹
            </button>
            
            {/* First 3 pages */}
            {[1, 2, 3].map(pageNum => {
              if (pageNum > totalPages) return null;
              return (
                <button
                  key={pageNum}
                  onClick={() => setCurrentPage(pageNum)}
                  style={{
                    width: '40px',
                    height: '40px',
                    borderRadius: '12px',
                    border: currentPage === pageNum ? 'none' : '1px solid #e5e7eb',
                    background: currentPage === pageNum ? '#3b82f6' : 'white',
                    color: currentPage === pageNum ? 'white' : '#6b7280',
                    cursor: 'pointer',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    fontSize: '0.95rem',
                    fontWeight: currentPage === pageNum ? '600' : '400',
                    transition: 'all 0.2s'
                  }}
                >
                  {pageNum}
                </button>
              );
            })}
            
            {/* Ellipsis if there are more pages */}
            {totalPages > 4 && (
              <span style={{ color: '#6b7280', fontSize: '1.2rem', padding: '0 4px' }}>...</span>
            )}
            
            {/* Last page */}
            {totalPages > 3 && (
              <button
                onClick={() => setCurrentPage(totalPages)}
                style={{
                  width: '40px',
                  height: '40px',
                  borderRadius: '12px',
                  border: currentPage === totalPages ? 'none' : '1px solid #e5e7eb',
                  background: currentPage === totalPages ? '#3b82f6' : 'white',
                  color: currentPage === totalPages ? 'white' : '#6b7280',
                  cursor: 'pointer',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  fontSize: '0.95rem',
                  fontWeight: currentPage === totalPages ? '600' : '400',
                  transition: 'all 0.2s'
                }}
              >
                {totalPages}
              </button>
            )}
            
            <button
              onClick={() => setCurrentPage(prev => Math.min(totalPages, prev + 1))}
              disabled={currentPage === totalPages}
              style={{
                width: '40px',
                height: '40px',
                borderRadius: '12px',
                border: '1px solid #e5e7eb',
                background: 'white',
                color: '#6b7280',
                cursor: currentPage === totalPages ? 'not-allowed' : 'pointer',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                fontSize: '1.2rem',
                opacity: currentPage === totalPages ? 0.5 : 1,
                transition: 'all 0.2s'
              }}
            >
              ›
            </button>
          </div>
        </>
      )}
      
      {/* Results text and items per page selector - Always visible */}
      <div style={{ display: 'flex', justifyContent: 'flex-start', alignItems: 'center', gap: '16px', marginTop: '16px' }}>
        <select
          value={itemsPerPage}
          onChange={(e) => {
            setItemsPerPage(parseInt(e.target.value));
            setCurrentPage(1);
          }}
          style={{
            padding: '8px 32px 8px 16px',
            borderRadius: '8px',
            border: '1px solid #e5e7eb',
            background: '#f3f4f6',
            fontSize: '0.9rem',
            color: '#374151',
            fontWeight: '500',
            cursor: 'pointer',
            appearance: 'none',
            backgroundImage: 'url("data:image/svg+xml,%3Csvg xmlns=\'http://www.w3.org/2000/svg\' width=\'12\' height=\'12\' viewBox=\'0 0 12 12\'%3E%3Cpath fill=\'%23374151\' d=\'M6 9L1 4h10z\'/%3E%3C/svg%3E")',
            backgroundRepeat: 'no-repeat',
            backgroundPosition: 'right 12px center'
          }}
        >
          <option value="20">20</option>
          <option value="50">50</option>
          <option value="100">100</option>
        </select>
        <div style={{ fontSize: '0.9rem', color: '#374151', fontWeight: '500' }}>
          Results: {startIndex + 1} - {Math.min(endIndex, allItems.length)} of {allItems.length}
        </div>
      </div>
    </div>
  );
}

// Paginated All Orders Section Component
function PaginatedAllOrdersSection({ data }) {
  const [currentPage, setCurrentPage] = useState(1);
  const [itemsPerPage, setItemsPerPage] = useState(20);
  const a = data?.consumer_report || {};
  const recent = data?.recent_orders || [];
  const totalPages = Math.ceil(recent.length / itemsPerPage);
  const startIndex = (currentPage - 1) * itemsPerPage;
  const endIndex = startIndex + itemsPerPage;
  const currentOrders = recent.slice(startIndex, endIndex);

  // Debug: Log first order to see available fields
  if (recent.length > 0 && currentPage === 1) {
    console.log('Sample Order Data:', recent[0]);
  }

  return (
    <div>
      <div className="kpi-row">
        <div className="kpi"><div className="kpi-value">{toNumber(a.total_orders)}</div><div className="kpi-label">Total Orders</div></div>
        <div className="kpi"><div className="kpi-value">{toCurrency(a.total_revenue)}</div><div className="kpi-label">Total Revenue</div></div>
        <div className="kpi"><div className="kpi-value">{a.period_days ? `${a.period_days}d` : '-'}</div><div className="kpi-label">Period</div></div>
      </div>
      <div style={{ marginTop: 12 }} className="scroll-x">
        <table className="data-table">
          <thead>
            <tr>
              <th>Order ID</th>
              <th>Order Status</th>
              <th>Amount</th>
              <th>Payment Status</th>
              <th>Payment Method</th>
              <th>User ID</th>
              <th>Created</th>
            </tr>
          </thead>
          <tbody>
            {currentOrders.map(r => {
              const orderStatus = r.order_status || r.status || 'N/A';
              const paymentStatus = r.payment_status || r.paymentStatus || 'N/A';
              const paymentMethod = r.payment_method || r.paymentMethod || r.method || 'razorpay';
              const userId = r.user_id || r.userId || r.customer_id || '-';

              return (
                <tr key={r.order_id}>
                  <td><span className="link-text">#{r.order_id}</span></td>
                  <td><span className={`badge ${orderStatus === 'success' || orderStatus === 'completed' ? 'success' : orderStatus === 'pending' || orderStatus === 'processing' ? 'warning' : orderStatus === 'N/A' ? 'neutral' : 'danger'}`}>{orderStatus}</span></td>
                  <td>{toCurrency(r.amount)}</td>
                  <td><span className={`badge ${paymentStatus === 'success' || paymentStatus === 'paid' ? 'success' : paymentStatus === 'pending' ? 'warning' : paymentStatus === 'N/A' ? 'neutral' : 'danger'}`}>{paymentStatus}</span></td>
                  <td>{paymentMethod}</td>
                  <td>{userId}</td>
                  <td>{formatDate(r.created_at)}</td>
                </tr>
              );
            })}
            {!recent.length && (
              <tr>
                <td colSpan="7" className="muted">No recent orders</td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
      {totalPages > 1 && (
        <>
          <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', gap: '8px', marginTop: '20px' }}>
            <button
              onClick={() => setCurrentPage(prev => Math.max(1, prev - 1))}
              disabled={currentPage === 1}
              style={{
                width: '40px',
                height: '40px',
                borderRadius: '12px',
                border: '1px solid #e5e7eb',
                background: 'white',
                color: '#6b7280',
                cursor: currentPage === 1 ? 'not-allowed' : 'pointer',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                fontSize: '1.2rem',
                opacity: currentPage === 1 ? 0.5 : 1,
                transition: 'all 0.2s'
              }}
            >
              ‹
            </button>
            
            {/* First 3 pages */}
            {[1, 2, 3].map(pageNum => {
              if (pageNum > totalPages) return null;
              return (
                <button
                  key={pageNum}
                  onClick={() => setCurrentPage(pageNum)}
                  style={{
                    width: '40px',
                    height: '40px',
                    borderRadius: '12px',
                    border: currentPage === pageNum ? 'none' : '1px solid #e5e7eb',
                    background: currentPage === pageNum ? '#3b82f6' : 'white',
                    color: currentPage === pageNum ? 'white' : '#6b7280',
                    cursor: 'pointer',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    fontSize: '0.95rem',
                    fontWeight: currentPage === pageNum ? '600' : '400',
                    transition: 'all 0.2s'
                  }}
                >
                  {pageNum}
                </button>
              );
            })}
            
            {/* Ellipsis if there are more pages */}
            {totalPages > 4 && (
              <span style={{ color: '#6b7280', fontSize: '1.2rem', padding: '0 4px' }}>...</span>
            )}
            
            {/* Last page */}
            {totalPages > 3 && (
              <button
                onClick={() => setCurrentPage(totalPages)}
                style={{
                  width: '40px',
                  height: '40px',
                  borderRadius: '12px',
                  border: currentPage === totalPages ? 'none' : '1px solid #e5e7eb',
                  background: currentPage === totalPages ? '#3b82f6' : 'white',
                  color: currentPage === totalPages ? 'white' : '#6b7280',
                  cursor: 'pointer',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  fontSize: '0.95rem',
                  fontWeight: currentPage === totalPages ? '600' : '400',
                  transition: 'all 0.2s'
                }}
              >
                {totalPages}
              </button>
            )}
            
            <button
              onClick={() => setCurrentPage(prev => Math.min(totalPages, prev + 1))}
              disabled={currentPage === totalPages}
              style={{
                width: '40px',
                height: '40px',
                borderRadius: '12px',
                border: '1px solid #e5e7eb',
                background: 'white',
                color: '#6b7280',
                cursor: currentPage === totalPages ? 'not-allowed' : 'pointer',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                fontSize: '1.2rem',
                opacity: currentPage === totalPages ? 0.5 : 1,
                transition: 'all 0.2s'
              }}
            >
              ›
            </button>
          </div>
        </>
      )}
      
      {/* Results text and items per page selector - Always visible */}
      <div style={{ display: 'flex', justifyContent: 'flex-start', alignItems: 'center', gap: '16px', marginTop: '16px' }}>
        <select
          value={itemsPerPage}
          onChange={(e) => {
            setItemsPerPage(parseInt(e.target.value));
            setCurrentPage(1);
          }}
          style={{
            padding: '8px 32px 8px 16px',
            borderRadius: '8px',
            border: '1px solid #e5e7eb',
            background: '#f3f4f6',
            fontSize: '0.9rem',
            color: '#374151',
            fontWeight: '500',
            cursor: 'pointer',
            appearance: 'none',
            backgroundImage: 'url("data:image/svg+xml,%3Csvg xmlns=\'http://www.w3.org/2000/svg\' width=\'12\' height=\'12\' viewBox=\'0 0 12 12\'%3E%3Cpath fill=\'%23374151\' d=\'M6 9L1 4h10z\'/%3E%3C/svg%3E")',
            backgroundRepeat: 'no-repeat',
            backgroundPosition: 'right 12px center'
          }}
        >
          <option value="20">20</option>
          <option value="50">50</option>
          <option value="100">100</option>
        </select>
        <div style={{ fontSize: '0.9rem', color: '#374151', fontWeight: '500' }}>
          Results: {startIndex + 1} - {Math.min(endIndex, recent.length)} of {recent.length}
        </div>
      </div>
    </div>
  );
}

export default function BusinessDetails() {
  const businessId = useMemo(() => {
    // Read businessId from URL hash (e.g., #business-details/BUS001)
    const hash = window.location.hash.replace('#', '');
    const hashParts = hash.split('/');
    console.log('BusinessDetails - Full hash:', window.location.hash);
    console.log('BusinessDetails - Hash parts:', hashParts);
    
    if (hashParts.length > 1 && hashParts[0] === 'business-details') {
      const extractedId = decodeURIComponent(hashParts[1]);
      console.log('BusinessDetails - Extracted businessId from hash:', extractedId);
      return extractedId;
    }
    
    // Fallback to URL pathname for backward compatibility
    const parts = window.location.pathname.split('/').filter(Boolean);
    const fallbackId = decodeURIComponent(parts[2] || '');
    console.log('BusinessDetails - Fallback businessId from pathname:', fallbackId);
    return fallbackId;
  }, []);

  const [details, setDetails] = useState(null);
  const [alerts, setAlerts] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [showFullOverview, setShowFullOverview] = useState(false);
  const [showPaymentDetails, setShowPaymentDetails] = useState(false);
  const [selectedPayment, setSelectedPayment] = useState(null);
  const [showSettingsModal, setShowSettingsModal] = useState(false);
  const [showShareModal, setShowShareModal] = useState(false);
  const [saveMessage, setSaveMessage] = useState('');
  
  // Date filter states
  const [dateFilter, setDateFilter] = useState('today');
  const [customStartDate, setCustomStartDate] = useState('');
  const [customEndDate, setCustomEndDate] = useState('');
  const [filteredData, setFilteredData] = useState(null);
  
  // Report tabs state
  const [activeTab, setActiveTab] = useState('overview');

  // Date filter function
  const filterDataByDate = (data, filter, startDate, endDate) => {
    console.log('filterDataByDate called with:', { filter, startDate, endDate });
    console.log('Input data keys:', data ? Object.keys(data) : 'no data');
    
    if (!data) return null;
    
    const now = new Date();
    let filterStart, filterEnd;
    
    switch (filter) {
      case 'today':
        filterStart = new Date(now.getFullYear(), now.getMonth(), now.getDate());
        filterEnd = new Date(now.getFullYear(), now.getMonth(), now.getDate() + 1);
        filterEnd.setMilliseconds(filterEnd.getMilliseconds() - 1); // End of today (23:59:59.999)
        console.log('Today filter range:', {
          filterStart: filterStart.toISOString(),
          filterEnd: filterEnd.toISOString(),
          now: now.toISOString(),
          filterStartLocal: filterStart.toLocaleString(),
          filterEndLocal: filterEnd.toLocaleString()
        });
        break;
      case 'week':
        filterStart = new Date(now.getTime() - 7 * 24 * 60 * 60 * 1000);
        filterEnd = now;
        break;
      case 'month':
        filterStart = new Date(now.getTime() - 30 * 24 * 60 * 60 * 1000);
        filterEnd = now;
        break;
      case 'year':
        filterStart = new Date(now.getTime() - 365 * 24 * 60 * 60 * 1000);
        filterEnd = now;
        break;
      case 'all':
        // No filtering - return all data
        return data;
      case 'custom':
        if (!startDate || !endDate) return data;
        filterStart = new Date(startDate);
        filterEnd = new Date(endDate + 'T23:59:59');
        break;
      default:
        return data;
    }
    
    console.log('Filter date range:', { filterStart, filterEnd });
    
    // Create a filtered copy of the data
    const filtered = { ...data };
    
    // Filter orders based on date
    if (data.orders) {
      console.log('Filtering orders, original count:', data.orders.length);
      console.log('Today filter specific:', { 
        filter, 
        filterStart: filterStart.toISOString(), 
        filterEnd: filterEnd.toISOString(),
        now: now.toISOString()
      });
      
      filtered.orders = data.orders.filter(order => {
        const orderDate = new Date(order.created_at || order.date);
        const isInRange = orderDate >= filterStart && orderDate <= filterEnd;
        
        // Debug for today filter specifically
        if (filter === 'today') {
          console.log('Today filter order check:', {
            orderDate: orderDate.toISOString(),
            orderDateLocal: orderDate.toLocaleString(),
            created_at: order.created_at,
            date: order.date,
            isInRange,
            comparison: `${orderDate >= filterStart} && ${orderDate <= filterEnd}`,
            filterStartLocal: filterStart.toLocaleString(),
            filterEndLocal: filterEnd.toLocaleString()
          });
        }
        
        return isInRange;
      });
      console.log('Filtered orders count:', filtered.orders.length);
    }
    
    // Filter recent orders
    if (data.recent_orders) {
      console.log('Filtering recent_orders, original count:', data.recent_orders.length);
      filtered.recent_orders = data.recent_orders.filter(order => {
        const orderDate = new Date(order.created_at || order.date);
        const isInRange = orderDate >= filterStart && orderDate <= filterEnd;
        
        // Debug for today filter specifically
        if (filter === 'today') {
          console.log('Today recent order check:', {
            orderDate: orderDate.toISOString(),
            orderDateLocal: orderDate.toLocaleString(),
            created_at: order.created_at,
            date: order.date,
            isInRange,
            comparison: `${orderDate >= filterStart} && ${orderDate <= filterEnd}`,
            filterStartLocal: filterStart.toLocaleString(),
            filterEndLocal: filterEnd.toLocaleString()
          });
        } else if (!isInRange && data.recent_orders.length <= 5) {
          console.log('Recent order filtered out:', { orderDate, created_at: order.created_at, date: order.date });
        }
        
        return isInRange;
      });
      console.log('Filtered recent_orders count:', filtered.recent_orders.length);
    }
    
    // Filter payments
    if (data.recent_payments) {
      console.log('Filtering recent_payments, original count:', data.recent_payments.length);
      filtered.recent_payments = data.recent_payments.filter(payment => {
        const paymentDate = new Date(payment.created_at || payment.date);
        const isInRange = paymentDate >= filterStart && paymentDate <= filterEnd;
        if (!isInRange && data.recent_payments.length <= 5) {
          console.log('Payment filtered out:', { paymentDate, created_at: payment.created_at, date: payment.date });
        }
        return isInRange;
      });
      console.log('Filtered recent_payments count:', filtered.recent_payments.length);
    }
    
    // Recalculate totals for the filtered data
    const totalOrders = (filtered.orders?.length || 0) + (filtered.recent_orders?.length || 0);
    const totalRevenue = (filtered.orders || []).reduce((sum, order) => sum + (order.amount || 0), 0) +
                         (filtered.recent_orders || []).reduce((sum, order) => sum + (order.amount || 0), 0);
    
    // Update KPI data based on filtered results
    if (filtered.analytics) {
      filtered.analytics.total_orders = totalOrders;
      filtered.analytics.total_revenue = totalRevenue;
      // Note: Other analytics like avg_order_value, completion_rate, etc., would also need
      // to be recalculated based on the filtered data if they are to reflect the date filter.
      // For now, these are kept as is or based on the original `details` if not explicitly filtered.
    }
    
    // Explicitly set total_orders and total_revenue for easy access
    filtered.total_orders = totalOrders;
    filtered.total_revenue = totalRevenue;
    
    console.log('Final filtered data:', { totalOrders, totalRevenue, filteredOrders: filtered.orders?.length, filteredRecentOrders: filtered.recent_orders?.length });
    
    return filtered;
  };

  // Update filtered data when date filters or details change
  useEffect(() => {
    console.log('useEffect triggered:', { dateFilter, customStartDate, customEndDate, hasDetails: !!details });
    if (details) {
      const filtered = filterDataByDate(details, dateFilter, customStartDate, customEndDate);
      console.log('Setting filteredData:', filtered);
      setFilteredData(filtered);
    }
  }, [details, dateFilter, customStartDate, customEndDate]);

  const handleBackToAnalytics = () => {
    // Check if we're in a new tab (opened from Analytics_Enhanced)
    if (window.opener) {
      // We're in a new tab, close it
      window.close();
    } else {
      // We're in the same tab, navigate back to analytics
      window.location.hash = 'analytics';
    }
  };

  // Save business details to localStorage
  const handleSave = () => {
    try {
      const savedData = {
        businessId,
        details,
        alerts,
        savedAt: new Date().toISOString(),
        savedBy: 'admin' // You can replace with actual user info
      };
      
      // Save to localStorage
      localStorage.setItem(`business_${businessId}`, JSON.stringify(savedData));
      
      // Also maintain a list of saved businesses
      const savedBusinesses = JSON.parse(localStorage.getItem('saved_businesses') || '[]');
      const existingIndex = savedBusinesses.findIndex(b => b.businessId === businessId);
      
      const businessSummary = {
        businessId,
        businessName: details?.basic_info?.business_name || 'Unknown',
        savedAt: new Date().toISOString()
      };
      
      if (existingIndex >= 0) {
        savedBusinesses[existingIndex] = businessSummary;
      } else {
        savedBusinesses.unshift(businessSummary);
      }
      
      // Keep only last 50 saved businesses
      if (savedBusinesses.length > 50) {
        savedBusinesses.splice(50);
      }
      
      localStorage.setItem('saved_businesses', JSON.stringify(savedBusinesses));
      
      setSaveMessage('✓ Saved successfully!');
      setTimeout(() => setSaveMessage(''), 3000);
    } catch (error) {
      console.error('Error saving business details:', error);
      setSaveMessage('✗ Failed to save');
      setTimeout(() => setSaveMessage(''), 3000);
    }
  };

  // Export business details as Excel (CSV format)
  const handleExport = () => {
    try {
      const b = details?.basic_info || {};
      const orders = details?.consumer_report || {};
      const analytics = details?.analytics || {};
      const menuData = details?.menu_management || {};
      const fleetData = details?.delivery_fleet || {};
      const paymentsData = details?.payments_settlements || {};
      const recentOrders = details?.recent_orders || [];
      const recentPayments = paymentsData?.recent_payments || [];

      // Create comprehensive CSV data
      const sections = [];

      // Section 1: Business Information
      sections.push('BUSINESS INFORMATION');
      sections.push('Field,Value');
      sections.push(`Business ID,${b.business_id || '-'}`);
      sections.push(`Business Name,${b.business_name || '-'}`);
      sections.push(`Business Type,${b.business_type || '-'}`);
      sections.push(`Category,${b.business_category || '-'}`);
      sections.push(`City,${b.city || '-'}`);
      sections.push(`State,${b.state || '-'}`);
      sections.push(`Status,${b.operational_status || '-'}`);
      sections.push(`Verified,${b.is_verified ? 'Yes' : 'No'}`);
      sections.push(`Payment Status,${b.payment_status ? 'Active' : 'Inactive'}`);
      sections.push('');

      // Section 2: Performance Metrics
      sections.push('PERFORMANCE METRICS');
      sections.push('Metric,Value');
      sections.push(`Total Orders,${orders.total_orders || 0}`);
      sections.push(`Total Revenue,${orders.total_revenue || 0}`);
      sections.push(`Average Order Value,${orders.total_orders > 0 ? (orders.total_revenue / orders.total_orders).toFixed(2) : 0}`);
      sections.push(`Completion Rate,${analytics.completion_rate || 0}`);
      sections.push(`Customer Rating,${analytics.customer_rating || 0}`);
      sections.push(`Period Days,${orders.period_days || '-'}`);
      sections.push('');

      // Section 3: Recent Orders
      if (recentOrders.length > 0) {
        sections.push('RECENT ORDERS');
        sections.push('Order ID,Status,Amount,Payment Status,Payment Method,User ID,Created At');
        recentOrders.forEach(order => {
          const orderStatus = order.order_status || order.status || 'N/A';
          const paymentStatus = order.payment_status || order.paymentStatus || 'N/A';
          const paymentMethod = order.payment_method || order.paymentMethod || order.method || 'razorpay';
          const userId = order.user_id || order.userId || order.customer_id || '-';
          const amount = order.amount || 0;
          const createdAt = order.created_at || '-';
          
          sections.push(`${order.order_id},"${orderStatus}",${amount},"${paymentStatus}","${paymentMethod}",${userId},"${createdAt}"`);
        });
        sections.push('');
      }

      // Section 4: Recent Payments
      if (recentPayments.length > 0) {
        sections.push('RECENT PAYMENTS');
        sections.push('Payment ID,Order ID,Status,Method,Amount,Transaction ID,Created At');
        recentPayments.forEach(payment => {
          const paymentId = payment.id || '-';
          const orderId = payment.order_id || '-';
          const status = payment.status || '-';
          const method = payment.method || '-';
          const amount = payment.amount || 0;
          const txnId = payment.transaction_id || payment.txn_id || payment.razorpay_payment_id || '-';
          const createdAt = payment.created_at || '-';
          
          sections.push(`${paymentId},${orderId},"${status}","${method}",${amount},"${txnId}","${createdAt}"`);
        });
        sections.push('');
      }

      // Section 5: Menu Items
      const menuItems = menuData?.menu_items || [];
      const groceryProducts = menuData?.grocery_products || [];
      const allItems = [
        ...menuItems.map(item => ({
          name: item.name || '-',
          type: 'Restaurant',
          category: item.category || '-',
          price: item.price || 0,
          status: item.is_active ? 'Active' : 'Inactive'
        })),
        ...groceryProducts.map(product => ({
          name: product.name || '-',
          type: 'Grocery',
          category: product.category_id || '-',
          price: product.price || 0,
          status: product.is_active !== false ? 'Active' : 'Inactive'
        }))
      ];

      if (allItems.length > 0) {
        sections.push('MENU ITEMS / PRODUCTS');
        sections.push('Item Name,Type,Category,Price,Status');
        allItems.forEach(item => {
          sections.push(`"${item.name}","${item.type}","${item.category}",${item.price},"${item.status}"`);
        });
        sections.push('');
      }

      // Section 6: Delivery Fleet
      if (fleetData && Object.keys(fleetData).length > 0) {
        sections.push('DELIVERY FLEET');
        sections.push('Metric,Value');
        sections.push(`Total Partners,${fleetData.total_partners || 0}`);
        sections.push(`Available,${fleetData.available || 0}`);
        sections.push(`On Delivery,${fleetData.on_delivery || 0}`);
        sections.push(`Offline,${fleetData.offline || 0}`);
        sections.push('');
      }

      // Section 7: Alerts
      if (alerts.length > 0) {
        sections.push('ACTIVE ALERTS');
        sections.push('Type,Message,Severity,Created At');
        alerts.forEach(alert => {
          sections.push(`"${alert.type || '-'}","${alert.message || '-'}","${alert.severity || '-'}","${alert.created_at || '-'}"`);
        });
        sections.push('');
      }

      // Add export metadata
      sections.push('EXPORT INFORMATION');
      sections.push('Field,Value');
      sections.push(`Exported At,${new Date().toISOString()}`);
      sections.push(`Exported By,admin`);
      sections.push(`Business ID,${businessId}`);

      // Create CSV content
      const csvContent = sections.join('\n');

      // Create and download file
      const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' });
      const url = URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url;
      link.download = `business_${businessId}_${new Date().toISOString().split('T')[0]}.csv`;
      link.style.visibility = 'hidden';
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
      URL.revokeObjectURL(url);

      setSaveMessage('✓ Exported successfully!');
      setTimeout(() => setSaveMessage(''), 3000);
    } catch (error) {
      console.error('Error exporting business details:', error);
      setSaveMessage('✗ Failed to export');
      setTimeout(() => setSaveMessage(''), 3000);
    }
  };

  // Share business details
  const handleShare = () => {
    console.log('Share button clicked!');
    console.log('Current showShareModal state:', showShareModal);
    setShowShareModal(true);
    console.log('Set showShareModal to true');
  };

  // Copy share link to clipboard
  const handleCopyLink = () => {
    const shareUrl = `${window.location.origin}${window.location.pathname}#business-details/${businessId}`;
    navigator.clipboard.writeText(shareUrl).then(() => {
      setSaveMessage('✓ Link copied to clipboard!');
      setTimeout(() => setSaveMessage(''), 3000);
      setShowShareModal(false);
    }).catch(err => {
      console.error('Failed to copy link:', err);
      setSaveMessage('✗ Failed to copy link');
      setTimeout(() => setSaveMessage(''), 3000);
    });
  };

  // Generate CSV content for sharing
  const generateCSVContent = () => {
    const b = details?.basic_info || {};
    const s = details?.status_info || {};
    const a = details?.analytics || {};
    const p = details?.payments || {};
    const menuItems = details?.menu_items || [];
    const groceries = details?.grocery_products || [];
    const partners = details?.partners || [];
    
    let csv = '';
    
    // Business Information
    csv += 'BUSINESS INFORMATION\n';
    csv += `Business Name,"${b.business_name || '-'}"\n`;
    csv += `Business ID,"${b.business_id || businessId}"\n`;
    csv += `Type,"${b.business_type || '-'}"\n`;
    csv += `Status,"${s.status || '-'}"\n`;
    csv += `Verified,"${s.verified ? 'Yes' : 'No'}"\n`;
    csv += `Phone,"${b.phone || '-'}"\n`;
    csv += `Email,"${b.email || '-'}"\n`;
    csv += `Address,"${b.address || '-'}"\n`;
    csv += `City,"${b.city || '-'}"\n`;
    csv += `State,"${b.state || '-'}"\n`;
    csv += `Pincode,"${b.pincode || '-'}"\n\n`;
    
    // Performance Metrics
    csv += 'PERFORMANCE METRICS\n';
    csv += `Total Orders,"${a.total_orders || 0}"\n`;
    csv += `Total Revenue,"${a.total_revenue || 0}"\n`;
    csv += `Average Rating,"${a.average_rating || 0}"\n`;
    csv += `Completion Rate,"${a.completion_rate ? (a.completion_rate * 100).toFixed(1) + '%' : '0%'}"\n`;
    csv += `Active Menu Items,"${menuItems.length + groceries.length}"\n`;
    csv += `Delivery Partners,"${partners.length}"\n\n`;
    
    // Recent Orders
    const recentOrders = details?.recent_orders || [];
    if (recentOrders.length > 0) {
      csv += 'RECENT ORDERS\n';
      csv += 'Order ID,Status,Amount,Date\n';
      recentOrders.slice(0, 10).forEach(order => {
        csv += `"${order.order_id || '-'}","${order.status || '-'}","${order.amount || 0}","${order.created_at || '-'}"\n`;
      });
      csv += '\n';
    }
    
    // Recent Payments
    const recentPayments = details?.recent_payments || [];
    if (recentPayments.length > 0) {
      csv += 'RECENT PAYMENTS\n';
      csv += 'Payment ID,Order ID,Status,Method,Amount,Date\n';
      recentPayments.slice(0, 10).forEach(payment => {
        csv += `"${payment.id || '-'}","${payment.order_id || '-'}","${payment.status || '-'}","${payment.method || '-'}","${payment.amount || 0}","${payment.created_at || '-'}"\n`;
      });
      csv += '\n';
    }
    
    // Menu Items
    if (menuItems.length > 0 || groceries.length > 0) {
      csv += 'MENU ITEMS / PRODUCTS\n';
      csv += 'Name,Category,Price,Status\n';
      [...menuItems, ...groceries].slice(0, 20).forEach(item => {
        csv += `"${item.name || item.product_name || '-'}","${item.category || '-'}","${item.price || 0}","${item.status || item.is_active ? 'Active' : 'Inactive'}"\n`;
      });
      csv += '\n';
    }
    
    // Export Information
    csv += 'EXPORT INFORMATION\n';
    csv += `Exported At,"${new Date().toISOString()}"\n`;
    csv += `Exported By,"Admin"\n`;
    csv += `Source,"KiraZee Admin Dashboard"\n`;
    
    return csv;
  };

  // Share via email with formatted text
  const handleShareEmail = () => {
    const businessName = details?.basic_info?.business_name || 'Business';
    const b = details?.basic_info || {};
    const s = details?.status_info || {};
    const a = details?.analytics || {};
    
    const subject = encodeURIComponent(`Business Analytics Report - ${businessName}`);
    
    // Create clean text format email body
    const emailBody = encodeURIComponent(`Business Analytics Report
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

BUSINESS: ${businessName}
Business ID: ${b.business_id || businessId}
Type: ${b.business_type || 'N/A'}
Status: ${s.status || 'N/A'}
Phone: ${b.phone || 'N/A'}
Email: ${b.email || 'N/A'}

PERFORMANCE METRICS
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Total Orders: ${a.total_orders || 0}
Total Revenue: ₹${(a.total_revenue || 0).toLocaleString('en-IN')}
Average Rating: ${a.average_rating || 0}/5
Completion Rate: ${a.completion_rate ? (a.completion_rate * 100).toFixed(1) + '%' : '0%'}
Average Order Value: ₹${(a.average_order_value || 0).toLocaleString('en-IN')}
Active Menu Items: ${(details?.menu_items?.length || 0) + (details?.grocery_products?.length || 0)}
Delivery Partners: ${details?.partners?.length || 0}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Report Generated: ${new Date().toLocaleString('en-IN', { dateStyle: 'full', timeStyle: 'short' })}
Generated By: KiraZee Admin Team`);
    
    // Open Gmail compose with pre-filled content
    window.open(`https://mail.google.com/mail/?view=cm&fs=1&su=${subject}&body=${emailBody}`, '_blank');
    
    setSaveMessage('✓ Gmail opened with report!');
    setTimeout(() => setSaveMessage(''), 3000);
  };

  // Share via WhatsApp
  const handleShareWhatsApp = () => {
    const businessName = details?.basic_info?.business_name || 'Business';
    const b = details?.basic_info || {};
    const a = details?.analytics || {};
    
    const message = `*BUSINESS ANALYTICS REPORT*
${businessName}

━━━━━━━━━━━━━━━━━━━━━━
<FaChartBar /> PERFORMANCE METRICS
━━━━━━━━━━━━━━━━━━━━━━

• Total Orders: *${a.total_orders || 0}*
• Total Revenue: *₹${(a.total_revenue || 0).toLocaleString('en-IN')}*
• Average Rating: *${a.average_rating || 0}/5*
• Completion Rate: *${a.completion_rate ? (a.completion_rate * 100).toFixed(1) + '%' : '0%'}*

━━━━━━━━━━━━━━━━━━━━━━
<FaMapMarkerAlt /> BUSINESS INFO
━━━━━━━━━━━━━━━━━━━━━━

Business ID: ${b.business_id || businessId}
Type: ${b.business_type || 'N/A'}
Status: ${b.status || 'N/A'}

<FaPhone /> Contact: ${b.phone || 'N/A'}
<FaEnvelope /> Email: ${b.email || 'N/A'}

━━━━━━━━━━━━━━━━━━━━━━

<FaFileDownload /> *Detailed CSV report has been downloaded. Please attach it to share complete data.*

_Report Generated: ${new Date().toLocaleString('en-IN', { dateStyle: 'medium', timeStyle: 'short' })}_`;

    const text = encodeURIComponent(message);
    
    // Download CSV
    const csvContent = generateCSVContent();
    const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' });
    const csvUrl = URL.createObjectURL(blob);
    const fileName = `${businessName.replace(/[^a-z0-9]/gi, '_')}_Report_${new Date().toISOString().split('T')[0]}.csv`;
    
    const link = document.createElement('a');
    link.href = csvUrl;
    link.download = fileName;
    link.style.display = 'none';
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    URL.revokeObjectURL(csvUrl);
    
    setTimeout(() => {
      window.open(`https://wa.me/?text=${text}`, '_blank');
    }, 500);
    
    setSaveMessage('✓ CSV downloaded! Attach it in WhatsApp.');
    setTimeout(() => setSaveMessage(''), 5000);
  };

  // Share via Telegram
  const handleShareTelegram = () => {
    const businessName = details?.basic_info?.business_name || 'Business';
    const b = details?.basic_info || {};
    const a = details?.analytics || {};
    
    const message = `📊 BUSINESS ANALYTICS REPORT
${businessName}

━━━━━━━━━━━━━━━━━━━━━━
PERFORMANCE METRICS
━━━━━━━━━━━━━━━━━━━━━━

• Total Orders: ${a.total_orders || 0}
• Total Revenue: ₹${(a.total_revenue || 0).toLocaleString('en-IN')}
• Average Rating: ${a.average_rating || 0}/5
• Completion Rate: ${a.completion_rate ? (a.completion_rate * 100).toFixed(1) + '%' : '0%'}

━━━━━━━━━━━━━━━━━━━━━━
BUSINESS INFO
━━━━━━━━━━━━━━━━━━━━━━

Business ID: ${b.business_id || businessId}
Type: ${b.business_type || 'N/A'}
Status: ${b.status || 'N/A'}

Contact: ${b.phone || 'N/A'}
Email: ${b.email || 'N/A'}

━━━━━━━━━━━━━━━━━━━━━━

  Detailed CSV report downloaded. Please attach for complete data.

Report Generated: ${new Date().toLocaleString('en-IN', { dateStyle: 'medium', timeStyle: 'short' })}`;

    const text = encodeURIComponent(message);
    
    // Download CSV
    const csvContent = generateCSVContent();
    const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' });
    const csvUrl = URL.createObjectURL(blob);
    const fileName = `${businessName.replace(/[^a-z0-9]/gi, '_')}_Report_${new Date().toISOString().split('T')[0]}.csv`;
    
    const link = document.createElement('a');
    link.href = csvUrl;
    link.download = fileName;
    link.style.display = 'none';
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    URL.revokeObjectURL(csvUrl);
    
    setTimeout(() => {
      window.open(`https://t.me/share/url?url=${encodeURIComponent('')}&text=${text}`, '_blank');
    }, 500);
    
    setSaveMessage('✓ CSV downloaded! Attach it in Telegram.');
    setTimeout(() => setSaveMessage(''), 5000);
  };

  // Share via LinkedIn
  const handleShareLinkedIn = () => {
    const shareUrl = `${window.location.origin}${window.location.pathname}#business-details/${businessId}`;
    window.open(`https://www.linkedin.com/sharing/share-offsite/?url=${encodeURIComponent(shareUrl)}`, '_blank');
  };

  // Share via Twitter/X
  const handleShareTwitter = () => {
    const businessName = details?.basic_info?.business_name || 'Business';
    const shareUrl = `${window.location.origin}${window.location.pathname}#business-details/${businessId}`;
    const text = encodeURIComponent(`Check out ${businessName} business details on KiraZee Admin Dashboard`);
    window.open(`https://twitter.com/intent/tweet?text=${text}&url=${encodeURIComponent(shareUrl)}`, '_blank');
  };

  // Share via Facebook
  const handleShareFacebook = () => {
    const shareUrl = `${window.location.origin}${window.location.pathname}#business-details/${businessId}`;
    window.open(`https://www.facebook.com/sharer/sharer.php?u=${encodeURIComponent(shareUrl)}`, '_blank');
  };

  // Share via SMS
  const handleShareSMS = () => {
    const businessName = details?.basic_info?.business_name || 'Business';
    const shareUrl = `${window.location.origin}${window.location.pathname}#business-details/${businessId}`;
    const body = encodeURIComponent(`${businessName} - Business Details: ${shareUrl}`);
    window.open(`sms:?body=${body}`, '_blank');
  };

  // Native share (if supported)
  const handleNativeShare = async () => {
    const businessName = details?.basic_info?.business_name || 'Business';
    const shareUrl = `${window.location.origin}${window.location.pathname}#business-details/${businessId}`;
    
    if (navigator.share) {
      try {
        await navigator.share({
          title: `${businessName} - Business Details`,
          text: `View business details for ${businessName}`,
          url: shareUrl
        });
        setSaveMessage('✓ Shared successfully!');
        setTimeout(() => setSaveMessage(''), 3000);
        setShowShareModal(false);
      } catch (err) {
        if (err.name !== 'AbortError') {
          console.error('Error sharing:', err);
        }
      }
    } else {
      setSaveMessage('✗ Native sharing not supported');
      setTimeout(() => setSaveMessage(''), 3000);
    }
  };

  // Open settings modal
  const handleSettings = () => {
    setShowSettingsModal(true);
  };

  useEffect(() => {
    let mounted = true;
    (async () => {
      try {
        setLoading(true);
        setError(null);
        const res = await AdminService.getBusinessDetails(businessId);
        const d = res?.business_details || res?.data?.business_details || res;
        if (mounted) setDetails(d || null);
        try {
          const alertsRes = await AdminService.getBusinessAlerts(businessId);
          const alertList = alertsRes?.alerts || alertsRes?.data?.alerts || alertsRes || [];
          if (mounted) setAlerts(Array.isArray(alertList) ? alertList : []);
        } catch (ae) {
          console.warn('Alerts fetch failed', ae);
          if (mounted) setAlerts(d?.alerts || []);
        }
      } catch (e) {
        console.error('Failed to load business details', e);
        if (mounted) setError('Failed to load business details');
      } finally {
        if (mounted) setLoading(false);
      }
    })();
    return () => { mounted = false; };
  }, [businessId]);

  if (loading) return <div className="loading">Loading business details...</div>;
  if (error) return <div className="error">{error}</div>;
  if (!details) return <div className="error">No details found</div>;

  const b = details?.basic_info || {};
  const si = details?.status_info || {};
  const ownerDetails = details?.owner_details || null;
  
  // Debug logging
  console.log('=== OWNER DETAILS DEBUG ===');
  console.log('Business ID:', b.business_id);
  console.log('Business Name:', b.business_name);
  console.log('Business Level:', b.level);
  console.log('Master:', b.master);
  console.log('Owner Details:', ownerDetails);
  console.log('Financials:', details?.financials);
  console.log('Full basic_info:', b);
  console.log('Full details object keys:', Object.keys(details || {}));
  console.log('=== END DEBUG ===');
  
  const name = b.business_name || 'Business Details';
  const status = si.operational_status;
  const verified = !!b.is_verified;
  const payOk = !!b.payment_status;
  const id = b.business_id;
  const outlet = b.outlet_code;
  const scope = Array.isArray(details?.scope_business_ids) ? details.scope_business_ids.length : 1;
  const businessType = b.business_type || '';
  const businessLevel = (b.level || '').toLowerCase();

  // Determine menu label based on business type
  const menuLabel = businessType === 'R01' ? 'Products' : 'Menu Items';

  // Extract real business data
  const orders = {
    total_orders: filteredData?.total_orders || 0,
    total_revenue: filteredData?.total_revenue || 0,
    period_days: details?.consumer_report?.period_days || 30,
    completion_rate: details?.consumer_report?.completion_rate || 0,
    avg_order_value: details?.consumer_report?.avg_order_value || 0
  };
  
  // Debug the orders object
  console.log('Orders object after filtering:', orders);
  const analytics = filteredData?.analytics || details?.analytics || {};
  const menuData = details?.menu_management || {};
  const fleetData = details?.delivery_fleet || {};
  const paymentsData = filteredData?.payments_settlements || details?.payments_settlements || {};
  const inventoryData = details?.inventory || {};
  const recentOrders = filteredData?.recent_orders || filteredData?.orders || details?.recent_orders || details?.orders || [];
  const menuItems = menuData?.menu_items || [];
  const branches = details?.branches || [];

  // Debug logging for all businesses when no orders found
  if (recentOrders.length === 0) {
    console.log(`${businessType} Business - No recent orders found`);
    console.log('Available data keys:', Object.keys(details));
    console.log('details.recent_orders:', details?.recent_orders);
    console.log('details.orders:', details?.orders);
    console.log('Consumer report:', orders);
    console.log('Full details object:', details);
  } else {
    console.log(`Found ${recentOrders.length} recent orders`);
  }

  // Calculate metrics from real data
  console.log('Calculating metrics:', { 
    filteredDataTotalOrders: filteredData?.total_orders, 
    filteredDataTotalRevenue: filteredData?.total_revenue,
    detailsTotalOrders: details?.consumer_report?.total_orders,
    ordersTotalOrders: orders.total_orders,
    filteredDataKeys: filteredData ? Object.keys(filteredData) : 'no filteredData'
  });
  
  const totalOrders = filteredData?.total_orders || 0;
  const totalRevenue = filteredData?.total_revenue || 0;
  
  console.log('Final calculated values:', { totalOrders, totalRevenue });
  const avgOrderValue = totalOrders > 0 ? totalRevenue / totalOrders : 0;
  const completionRate = analytics.completion_rate || 0;
  const customerRating = analytics.customer_rating || 0;

  // Payment metrics - Calculate from actual payment records
  const recentPayments = paymentsData?.recent_payments || [];

  // Calculate payment amounts by status from actual records
  let successAmount = 0;
  let pendingAmount = 0;
  let failedAmount = 0;
  let cancelledAmount = 0;

  recentPayments.forEach(payment => {
    const amount = payment.amount || 0;
    const status = (payment.status || '').toLowerCase();

    if (status === 'success' || status === 'paid' || status === 'completed') {
      successAmount += amount;
    } else if (status === 'pending' || status === 'processing') {
      pendingAmount += amount;
    } else if (status === 'failed') {
      failedAmount += amount;
    } else if (status === 'cancelled' || status === 'canceled') {
      cancelledAmount += amount;
    }
  });

  const totalPayments = successAmount + pendingAmount + failedAmount + cancelledAmount;

  // Fleet metrics
  const totalPartners = fleetData?.total_partners || 0;
  const availablePartners = fleetData?.available || 0;
  const onDelivery = fleetData?.on_delivery || 0;

  // Menu metrics - Include both menu items and grocery products
  const groceryProducts = menuData?.grocery_products || [];
  const activeMenuItems = menuItems.filter(item => item.is_active).length;
  const activeGroceryProducts = groceryProducts.filter(product => product.is_active !== false).length; // Assume active if not specified
  const totalActiveItems = activeMenuItems + activeGroceryProducts;
  const totalItems = menuItems.length + groceryProducts.length;
  const inactiveMenuItems = totalItems - totalActiveItems;

  // Generate chart data from recent orders
  const orderChartData = recentOrders.slice(0, 30).map((order, i) => ({
    label: `Order ${i + 1}`,
    value: order.amount || 0
  }));

  // Payment status breakdown for donut chart - Only Success and Cancelled
  const paymentBreakdown = [
    { value: successAmount, color: '#10b981', label: 'Success' },
    { value: cancelledAmount, color: '#9ca3af', label: 'Cancelled' }
  ].filter(item => item.value > 0);

  // Menu category breakdown
  // Use category_breakdown from backend which now works for both restaurants and supermarkets
  const categoryBreakdownFromBackend = menuData?.category_breakdown || [];
  const menuCategories = {};
  
  // Debug logging
  console.log('=== MENU CATEGORY DEBUG ===');
  console.log('Business Name:', b.business_name);
  console.log('Business ID:', businessId);
  console.log('Category breakdown from backend:', categoryBreakdownFromBackend);
  console.log('Menu items count:', menuItems.length);
  console.log('Sample menu items (first 3):', menuItems.slice(0, 3).map(item => ({ name: item.name, category: item.category })));
  
  // Always use backend category breakdown (now works for both business types)
  if (categoryBreakdownFromBackend.length > 0) {
    console.log('Using backend category breakdown');
    categoryBreakdownFromBackend.forEach(item => {
      menuCategories[item.category] = item.count;
    });
  } else {
    console.log('No category breakdown data available from backend');
    // Only fall back to menu items if absolutely necessary
    menuItems.forEach(item => {
      const cat = item.category || 'Other';
      menuCategories[cat] = (menuCategories[cat] || 0) + 1;
    });
  }
  
  console.log('Final menu categories:', menuCategories);
  
  const menuCategoryData = Object.entries(menuCategories).map(([label, value], i) => {
    // If only one category exists, use green color (represents 100%/max)
    if (Object.keys(menuCategories).length === 1) {
      return { value, label, color: '#10b981' }; // Green for single category
    }
    // Multiple categories - use color rotation
    return {
      value,
      label,
      color: ['#3b82f6', '#f59e0b', '#10b981', '#8b5cf6', '#06b6d4'][i % 5]
    };
  });
  
  console.log('Menu category data for chart:', menuCategoryData);
  console.log('=== END MENU CATEGORY DEBUG ===');

  // Order status breakdown with all possible statuses
  // Define all possible statuses for both food/restaurant and grocery orders with UNIQUE colors
  const allPossibleStatuses = {
    // Common statuses
    'pending': { color: '#f59e0b', label: 'Pending' },
    'confirmed': { color: '#3b82f6', label: 'Confirmed' },
    'accepted': { color: '#10b981', label: 'Accepted' },
    'ready': { color: '#8b5cf6', label: 'Ready' },
    'out_for_delivery': { color: '#06b6d4', label: 'Out for Delivery' },
    'delivered': { color: '#059669', label: 'Delivered' },
    'cancelled': { color: '#ef4444', label: 'Cancelled' },
    
    // Food/Restaurant specific
    'notified': { color: '#14b8a6', label: 'Notified' },
    'preparing': { color: '#f97316', label: 'Preparing' },
    'dispatched': { color: '#0ea5e9', label: 'Dispatched' },
    'travelling': { color: '#6366f1', label: 'Travelling' },
    
    // Grocery specific
    'packed': { color: '#a855f7', label: 'Packed' },
    'assigned': { color: '#ec4899', label: 'Assigned' },
    'picked_up': { color: '#84cc16', label: 'Picked Up' },
    'in_transit': { color: '#22d3ee', label: 'In Transit' },
    'completed': { color: '#22c55e', label: 'Completed' } // Different shade of green
  };
  
  // Additional colors for unknown statuses
  const extraColors = [
    '#fb923c', '#fbbf24', '#a3e635', '#4ade80', '#2dd4bf', 
    '#38bdf8', '#818cf8', '#c084fc', '#f472b6', '#fb7185',
    '#fdba74', '#fcd34d', '#bef264', '#6ee7b7', '#5eead4',
    '#7dd3fc', '#a5b4fc', '#d8b4fe', '#f9a8d4', '#fda4af'
  ];
  
  const orderStatusBreakdown = {};
  recentOrders.forEach(order => {
    const status = order.status || order.order_status || 'unknown';
    orderStatusBreakdown[status] = (orderStatusBreakdown[status] || 0) + 1;
  });
  
  // Debug: Log all statuses found in orders
  console.log('=== ORDER STATUS DEBUG ===');
  console.log('Business:', b.business_name);
  console.log('Total recent orders:', recentOrders.length);
  console.log('Status breakdown from orders:', orderStatusBreakdown);
  console.log('Predefined statuses:', Object.keys(allPossibleStatuses));
  
  // Find any statuses in the data that are NOT in our predefined list
  const unknownStatuses = Object.keys(orderStatusBreakdown).filter(
    status => !allPossibleStatuses[status] && status !== 'unknown'
  );
  
  if (unknownStatuses.length > 0) {
    console.log('Found unknown statuses:', unknownStatuses);
    // Add unknown statuses to the list with unique colors
    unknownStatuses.forEach((status, index) => {
      const colorIndex = index % extraColors.length;
      allPossibleStatuses[status] = {
        color: extraColors[colorIndex],
        label: status.charAt(0).toUpperCase() + status.slice(1).replace(/_/g, ' ')
      };
      console.log(`Added unknown status: ${status} with color ${extraColors[colorIndex]}`);
    });
  }
  console.log('=== END ORDER STATUS DEBUG ===');
  
  // Create order status data with ALL statuses (including those with 0 count)
  const orderStatusData = Object.entries(allPossibleStatuses)
    .map(([status, statusInfo]) => {
      return { 
        value: orderStatusBreakdown[status] || 0, // Show 0 if no data
        label: statusInfo.label, 
        color: statusInfo.color,
        status: status // Keep original status for reference
      };
    }); // Show ALL statuses, even with 0 count

  return (
    <div className="biz-details">
      <header className="biz-header">
        <div className="title-row">
          <div className="breadcrumb">
            <button 
              className="btn-back" 
              onClick={handleBackToAnalytics}
              style={{
                background: '#3b82f6',
                color: 'white',
                border: 'none',
                padding: '8px 16px',
                borderRadius: '4px',
                cursor: 'pointer',
                marginRight: '12px',
                fontSize: '14px',
                fontWeight: '500'
              }}
            >
              ← Back to Analytics
            </button>
            <span className="muted">DASHBOARD / BUSINESS ANALYTICS</span>
            <h2>{name}</h2>
          </div>
          <div className="header-actions">
            {saveMessage && (
              <span style={{
                marginRight: '12px',
                padding: '8px 12px',
                borderRadius: '4px',
                fontSize: '14px',
                backgroundColor: saveMessage.includes('✓') ? '#10b981' : '#ef4444',
                color: 'white'
              }}>
                {saveMessage}
              </span>
            )}
            <button className="btn-secondary" onClick={handleSave} title="Save business details locally">
              SAVE
            </button>
            <button className="btn-secondary" onClick={handleExport} title="Export business data as Excel (CSV)">
              EXPORT
            </button>
            <button className="btn-secondary" onClick={handleShare} title="Share business details">
              SHARE
            </button>
            <button className="btn-primary" onClick={handleSettings} title="Business settings">
              SETTINGS
            </button>
          </div>
        </div>
        <div className="header-meta">
          <div className="badge-row">
            <span className={`badge ${status === 'active' ? 'success' : 'warning'}`}>{status || '-'}</span>
            <span className={`badge ${verified ? 'success' : 'neutral'}`}>{verified ? 'Verified' : 'Unverified'}</span>
            <span className={`badge ${payOk ? 'success' : 'danger'}`}>{payOk ? 'Payments OK' : 'Payments Off'}</span>
          </div>
          <span className="muted">Business ID: {id}</span>
        </div>
      </header>

      {/* Report Navigation Cards and Filters - Below Header */}
      <div style={{
        display: 'grid',
        gridTemplateColumns: 'repeat(8, 1fr)',
        gap: '8px',
        margin: '16px 0',
        alignItems: 'stretch'
      }}>
        {/* Overview Card */}
        <button
          onClick={() => setActiveTab('overview')}
          style={{
            padding: '10px 8px',
            borderRadius: '6px',
            border: '1px solid #e5e7eb',
            background: activeTab === 'overview' ? '#3b82f6' : 'white',
            color: activeTab === 'overview' ? 'white' : '#374151',
            fontSize: '0.75rem',
            fontWeight: activeTab === 'overview' ? '600' : '500',
            cursor: 'pointer',
            transition: 'all 0.2s',
            display: 'flex',
            flexDirection: 'column',
            alignItems: 'center',
            gap: '6px',
            textAlign: 'center',
            boxShadow: activeTab === 'overview' ? '0 2px 4px rgba(59, 130, 246, 0.2)' : '0 1px 2px rgba(0,0,0,0.1)',
            height: '100%',
            minHeight: '80px'
          }}
        >
          <div style={{
            width: '28px',
            height: '28px',
            borderRadius: '6px',
            background: activeTab === 'overview' ? 'rgba(255,255,255,0.2)' : '#f3f4f6',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            flexShrink: 0
          }}>
            <FaChartBar size={12} color={activeTab === 'overview' ? 'white' : '#3b82f6'} />
          </div>
          <div>
            <div style={{ fontWeight: '600', fontSize: '0.7rem', lineHeight: '1.2' }}>Overview</div>
            <div style={{ fontSize: '0.65rem', opacity: 0.7, lineHeight: '1.1' }}>Main Dashboard</div>
          </div>
        </button>

        {/* Consumption Card */}
        <button
          onClick={() => setActiveTab('consumption')}
          style={{
            padding: '10px 8px',
            borderRadius: '6px',
            border: '1px solid #e5e7eb',
            background: activeTab === 'consumption' ? '#3b82f6' : 'white',
            color: activeTab === 'consumption' ? 'white' : '#374151',
            fontSize: '0.75rem',
            fontWeight: activeTab === 'consumption' ? '600' : '500',
            cursor: 'pointer',
            transition: 'all 0.2s',
            display: 'flex',
            flexDirection: 'column',
            alignItems: 'center',
            gap: '6px',
            textAlign: 'center',
            boxShadow: activeTab === 'consumption' ? '0 2px 4px rgba(59, 130, 246, 0.2)' : '0 1px 2px rgba(0,0,0,0.1)',
            height: '100%',
            minHeight: '80px'
          }}
        >
          <div style={{
            width: '28px',
            height: '28px',
            borderRadius: '6px',
            background: activeTab === 'consumption' ? 'rgba(255,255,255,0.2)' : '#f3f4f6',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            flexShrink: 0
          }}>
            <FaUtensils size={12} color={activeTab === 'consumption' ? 'white' : '#f59e0b'} />
          </div>
          <div>
            <div style={{ fontWeight: '600', fontSize: '0.7rem', lineHeight: '1.2' }}>Consumption</div>
            <div style={{ fontSize: '0.65rem', opacity: 0.7, lineHeight: '1.1' }}>Usage Analytics</div>
          </div>
        </button>

        {/* Consumer Card */}
        <button
          onClick={() => setActiveTab('consumer')}
          style={{
            padding: '10px 8px',
            borderRadius: '6px',
            border: '1px solid #e5e7eb',
            background: activeTab === 'consumer' ? '#3b82f6' : 'white',
            color: activeTab === 'consumer' ? 'white' : '#374151',
            fontSize: '0.75rem',
            fontWeight: activeTab === 'consumer' ? '600' : '500',
            cursor: 'pointer',
            transition: 'all 0.2s',
            display: 'flex',
            flexDirection: 'column',
            alignItems: 'center',
            gap: '6px',
            textAlign: 'center',
            boxShadow: activeTab === 'consumer' ? '0 2px 4px rgba(59, 130, 246, 0.2)' : '0 1px 2px rgba(0,0,0,0.1)',
            height: '100%',
            minHeight: '80px'
          }}
        >
          <div style={{
            width: '28px',
            height: '28px',
            borderRadius: '6px',
            background: activeTab === 'consumer' ? 'rgba(255,255,255,0.2)' : '#f3f4f6',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            flexShrink: 0
          }}>
            <FaUsers size={12} color={activeTab === 'consumer' ? 'white' : '#8b5cf6'} />
          </div>
          <div>
            <div style={{ fontWeight: '600', fontSize: '0.7rem', lineHeight: '1.2' }}>Consumer</div>
            <div style={{ fontSize: '0.65rem', opacity: 0.7, lineHeight: '1.1' }}>Customer Insights</div>
          </div>
        </button>

        {/* Sales Card */}
        <button
          onClick={() => setActiveTab('sales')}
          style={{
            padding: '10px 8px',
            borderRadius: '6px',
            border: '1px solid #e5e7eb',
            background: activeTab === 'sales' ? '#3b82f6' : 'white',
            color: activeTab === 'sales' ? 'white' : '#374151',
            fontSize: '0.75rem',
            fontWeight: activeTab === 'sales' ? '600' : '500',
            cursor: 'pointer',
            transition: 'all 0.2s',
            display: 'flex',
            flexDirection: 'column',
            alignItems: 'center',
            gap: '6px',
            textAlign: 'center',
            boxShadow: activeTab === 'sales' ? '0 2px 4px rgba(59, 130, 246, 0.2)' : '0 1px 2px rgba(0,0,0,0.1)',
            height: '100%',
            minHeight: '80px'
          }}
        >
          <div style={{
            width: '28px',
            height: '28px',
            borderRadius: '6px',
            background: activeTab === 'sales' ? 'rgba(255,255,255,0.2)' : '#f3f4f6',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            flexShrink: 0
          }}>
            <FaChartBar size={12} color={activeTab === 'sales' ? 'white' : '#10b981'} />
          </div>
          <div>
            <div style={{ fontWeight: '600', fontSize: '0.7rem', lineHeight: '1.2' }}>Sales</div>
            <div style={{ fontSize: '0.65rem', opacity: 0.7, lineHeight: '1.1' }}>Revenue Reports</div>
          </div>
        </button>

        {/* Menu Card */}
        <button
          onClick={() => setActiveTab('menu')}
          style={{
            padding: '10px 8px',
            borderRadius: '6px',
            border: '1px solid #e5e7eb',
            background: activeTab === 'menu' ? '#3b82f6' : 'white',
            color: activeTab === 'menu' ? 'white' : '#374151',
            fontSize: '0.75rem',
            fontWeight: activeTab === 'menu' ? '600' : '500',
            cursor: 'pointer',
            transition: 'all 0.2s',
            display: 'flex',
            flexDirection: 'column',
            alignItems: 'center',
            gap: '6px',
            textAlign: 'center',
            boxShadow: activeTab === 'menu' ? '0 2px 4px rgba(59, 130, 246, 0.2)' : '0 1px 2px rgba(0,0,0,0.1)',
            height: '100%',
            minHeight: '80px'
          }}
        >
          <div style={{
            width: '28px',
            height: '28px',
            borderRadius: '6px',
            background: activeTab === 'menu' ? 'rgba(255,255,255,0.2)' : '#f3f4f6',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            flexShrink: 0
          }}>
            <FaAppleAlt size={12} color={activeTab === 'menu' ? 'white' : '#ef4444'} />
          </div>
          <div>
            <div style={{ fontWeight: '600', fontSize: '0.7rem', lineHeight: '1.2' }}>Menu</div>
            <div style={{ fontSize: '0.65rem', opacity: 0.7, lineHeight: '1.1' }}>Item Analytics</div>
          </div>
        </button>

        {/* Performance Card */}
        <button
          onClick={() => setActiveTab('performance')}
          style={{
            padding: '10px 8px',
            borderRadius: '6px',
            border: '1px solid #e5e7eb',
            background: activeTab === 'performance' ? '#3b82f6' : 'white',
            color: activeTab === 'performance' ? 'white' : '#374151',
            fontSize: '0.75rem',
            fontWeight: activeTab === 'performance' ? '600' : '500',
            cursor: 'pointer',
            transition: 'all 0.2s',
            display: 'flex',
            flexDirection: 'column',
            alignItems: 'center',
            gap: '6px',
            textAlign: 'center',
            boxShadow: activeTab === 'performance' ? '0 2px 4px rgba(59, 130, 246, 0.2)' : '0 1px 2px rgba(0,0,0,0.1)',
            height: '100%',
            minHeight: '80px'
          }}
        >
          <div style={{
            width: '28px',
            height: '28px',
            borderRadius: '6px',
            background: activeTab === 'performance' ? 'rgba(255,255,255,0.2)' : '#f3f4f6',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            flexShrink: 0
          }}>
            <FaTrophy size={12} color={activeTab === 'performance' ? 'white' : '#f59e0b'} />
          </div>
          <div>
            <div style={{ fontWeight: '600', fontSize: '0.7rem', lineHeight: '1.2' }}>Performance</div>
            <div style={{ fontSize: '0.65rem', opacity: 0.7, lineHeight: '1.1' }}>KPI Metrics</div>
          </div>
        </button>

        {/* Inventory Card */}
        <button
          onClick={() => setActiveTab('inventory')}
          style={{
            padding: '10px 8px',
            borderRadius: '6px',
            border: '1px solid #e5e7eb',
            background: activeTab === 'inventory' ? '#3b82f6' : 'white',
            color: activeTab === 'inventory' ? 'white' : '#374151',
            fontSize: '0.75rem',
            fontWeight: activeTab === 'inventory' ? '600' : '500',
            cursor: 'pointer',
            transition: 'all 0.2s',
            display: 'flex',
            flexDirection: 'column',
            alignItems: 'center',
            gap: '6px',
            textAlign: 'center',
            boxShadow: activeTab === 'inventory' ? '0 2px 4px rgba(59, 130, 246, 0.2)' : '0 1px 2px rgba(0,0,0,0.1)',
            height: '100%',
            minHeight: '80px'
          }}
        >
          <div style={{
            width: '28px',
            height: '28px',
            borderRadius: '6px',
            background: activeTab === 'inventory' ? 'rgba(255,255,255,0.2)' : '#f3f4f6',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            flexShrink: 0
          }}>
            <FaCogs size={12} color={activeTab === 'inventory' ? 'white' : '#6b7280'} />
          </div>
          <div>
            <div style={{ fontWeight: '600', fontSize: '0.7rem', lineHeight: '1.2' }}>Inventory</div>
            <div style={{ fontSize: '0.65rem', opacity: 0.7, lineHeight: '1.1' }}>Stock Reports</div>
          </div>
        </button>

        {/* Date Filters Card */}
        <div style={{
          background: 'white',
          border: '1px solid #e5e7eb',
          borderRadius: '6px',
          padding: '10px 8px',
          boxShadow: '0 1px 2px rgba(0,0,0,0.1)',
          height: '100%',
          minHeight: '80px',
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center'
        }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '4px', marginBottom: '6px' }}>
            <FaCalendarAlt size={12} color="#3b82f6" />
            <h4 style={{ margin: 0, fontSize: '0.7rem', fontWeight: '600', color: '#1f2937' }}>Date Filters</h4>
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '4px', width: '100%' }}>
            <select 
              value={dateFilter} 
              onChange={(e) => setDateFilter(e.target.value)}
              style={{
                padding: '4px 6px',
                border: '1px solid #d1d5db',
                borderRadius: '4px',
                fontSize: '0.7rem',
                background: 'white',
                width: '100%'
              }}
            >
              <option value="today">Today</option>
              <option value="week">Week</option>
              <option value="month">Month</option>
              <option value="year">Year</option>
              <option value="all">All Time</option>
              <option value="custom">Custom</option>
            </select>
            
            {dateFilter === 'custom' && (
              <div style={{ display: 'flex', flexDirection: 'column', gap: '2px' }}>
                <input
                  type="date"
                  value={customStartDate}
                  onChange={(e) => setCustomStartDate(e.target.value)}
                  style={{
                    padding: '3px 4px',
                    border: '1px solid #d1d5db',
                    borderRadius: '4px',
                    fontSize: '0.65rem',
                    width: '100%'
                  }}
                />
                <input
                  type="date"
                  value={customEndDate}
                  onChange={(e) => setCustomEndDate(e.target.value)}
                  style={{
                    padding: '3px 4px',
                    border: '1px solid #d1d5db',
                    borderRadius: '4px',
                    fontSize: '0.65rem',
                    width: '100%'
                  }}
                />
              </div>
            )}
            
            <div style={{ fontSize: '0.6rem', color: '#6b7280', textAlign: 'center', marginTop: '2px' }}>
              {filteredData && (
                <span>{filteredData.total_orders || 0} orders</span>
              )}
            </div>
          </div>
        </div>
      </div>

      {/* Main Layout with Full Width Content */}
      <div style={{
        margin: '16px 0'
      }}>
        {/* Content based on active tab - Full Width */}
        {activeTab === 'overview' ? (
          /* Original Dashboard Layout - Show by default */
          <div style={{
            display: 'grid',
            gridTemplateColumns: '1.8fr 1fr',
            gap: '8px',
            margin: '16px 0'
          }}>
            {/* Left side - All cards in grid */}
            <div style={{
              display: 'grid',
              gridTemplateColumns: 'repeat(3, 1fr)',
              gap: '8px',
              alignContent: 'start'
            }}>
            {/* Total Orders */}
            <div style={{
              background: 'linear-gradient(135deg, #06b6d4 0%, #0891b2 100%)',
              borderRadius: '8px',
              padding: '16px',
              color: 'white',
              boxShadow: '0 2px 4px rgba(0,0,0,0.1)',
              position: 'relative',
              overflow: 'hidden'
            }}>
              <div style={{ fontSize: '0.7rem', opacity: 0.9, marginBottom: '4px', textTransform: 'uppercase', letterSpacing: '0.5px' }}>
                Total Orders ({dateFilter === 'today' ? 'Today' : dateFilter === 'week' ? 'Last 7 Days' : dateFilter === 'month' ? 'Last 30 Days' : dateFilter === 'year' ? 'Last Year' : dateFilter === 'all' ? 'All Time' : dateFilter === 'custom' ? 'Custom Range' : 'Filtered'})
              </div>
              <div style={{ fontSize: '1.75rem', fontWeight: '700', marginBottom: '4px' }}>
                {toNumber(totalOrders)}
              </div>
              <div style={{ fontSize: '0.75rem', opacity: 0.85 }}>
                Revenue: {toCurrency(totalRevenue)}
              </div>
              <div style={{ position: 'absolute', top: '12px', right: '12px', opacity: 0.2 }}>
                <FaShoppingCart size={40} />
              </div>
            </div>

            {/* Avg Order Value */}
            <div style={{
              background: 'linear-gradient(135deg, #8b5cf6 0%, #F55D00 100%)',
              borderRadius: '8px',
              padding: '16px',
              color: 'white',
              boxShadow: '0 2px 4px rgba(0,0,0,0.1)',
              position: 'relative',
              overflow: 'hidden'
            }}>
              <div style={{ fontSize: '0.7rem', opacity: 0.9, marginBottom: '4px', textTransform: 'uppercase', letterSpacing: '0.5px' }}>
                Avg Order Value (All Time)
              </div>
              <div style={{ fontSize: '1.75rem', fontWeight: '700', marginBottom: '4px' }}>
                {toCurrency(avgOrderValue)}
              </div>
              <div style={{ fontSize: '0.75rem', opacity: 0.85 }}>
                Per order
              </div>
              <div style={{ position: 'absolute', top: '12px', right: '12px', opacity: 0.2 }}>
                <FaDollarSign size={40} />
              </div>
            </div>

            {/* Completion Rate */}
            <div style={{
              background: completionRate > 0.8 
                ? 'linear-gradient(135deg, #10b981 0%, #059669 100%)'
                : 'linear-gradient(135deg, #f59e0b 0%, #d97706 100%)',
              borderRadius: '8px',
              padding: '16px',
              color: 'white',
              boxShadow: '0 2px 4px rgba(0,0,0,0.1)',
              position: 'relative',
              overflow: 'hidden'
            }}>
              <div style={{ fontSize: '0.7rem', opacity: 0.9, marginBottom: '4px', textTransform: 'uppercase', letterSpacing: '0.5px' }}>
                Completion Rate (All Time)
              </div>
              <div style={{ fontSize: '1.75rem', fontWeight: '700', marginBottom: '4px' }}>
                {(completionRate * 100).toFixed(1)}%
              </div>
              <div style={{ fontSize: '0.75rem', opacity: 0.85 }}>
                Rating: {customerRating.toFixed(1)}
              </div>
              <div style={{ position: 'absolute', top: '12px', right: '12px', opacity: 0.2 }}>
                <FaCheckCircle size={40} />
              </div>
            </div>

            {/* Active Items - Row 2, Column 1 */}
            <div style={{
              background: 'linear-gradient(135deg, #f59e0b 0%, #d97706 100%)',
              borderRadius: '8px',
              padding: '16px',
              color: 'white',
              boxShadow: '0 2px 4px rgba(0,0,0,0.1)',
              position: 'relative',
              overflow: 'hidden'
            }}>
              <div style={{ fontSize: '0.7rem', opacity: 0.9, marginBottom: '4px', textTransform: 'uppercase', letterSpacing: '0.5px' }}>
                Active {businessType === 'R01' ? 'Products' : 'Menu Items'}
              </div>
              <div style={{ fontSize: '1.75rem', fontWeight: '700', marginBottom: '4px' }}>
                {toNumber(totalActiveItems)}
              </div>
              <div style={{ fontSize: '0.75rem', opacity: 0.85 }}>
                {totalItems} total items
              </div>
              <div style={{ position: 'absolute', top: '12px', right: '12px', opacity: 0.2 }}>
                <FaUtensils size={40} />
              </div>
            </div>

            {/* Payment Status Breakdown - Row 2, Column 2 */}
            <div style={{
              background: 'white',
              border: '1px solid #e5e7eb',
              borderRadius: '8px',
              padding: '14px',
              boxShadow: '0 1px 3px rgba(0,0,0,0.1)'
            }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '6px', marginBottom: '10px', borderBottom: '1px solid #e5e7eb', paddingBottom: '6px' }}>
                <FaCreditCard size={15} color="#10b981" />
                <h4 style={{ margin: 0, fontSize: '0.85rem', fontWeight: '600', color: '#1f2937' }}>Payment Status</h4>
              </div>
              <div style={{ display: 'flex', gap: '14px', alignItems: 'center' }}>
                <div style={{ flexShrink: 0 }}>
                  <DonutChart data={paymentBreakdown} size={90} />
                </div>
                <div style={{ display: 'flex', flexDirection: 'column', gap: '8px', fontSize: '0.72rem', flex: 1 }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '5px' }}>
                    <span style={{ width: '7px', height: '7px', borderRadius: '2px', background: '#10b981', flexShrink: 0 }}></span>
                    <span style={{ color: '#6b7280', fontSize: '0.7rem' }}>Success</span>
                    <span style={{ fontWeight: '600', color: '#111827', fontSize: '0.7rem', marginLeft: 'auto' }}>{toCurrency(successAmount)}</span>
                  </div>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '5px' }}>
                    <span style={{ width: '7px', height: '7px', borderRadius: '2px', background: '#9ca3af', flexShrink: 0 }}></span>
                    <span style={{ color: '#6b7280', fontSize: '0.7rem' }}>Cancelled</span>
                    <span style={{ fontWeight: '600', color: '#111827', fontSize: '0.7rem', marginLeft: 'auto' }}>{toCurrency(cancelledAmount)}</span>
                  </div>
                </div>
              </div>
            </div>

            {/* Rating - Row 2, Column 3 */}
            <div style={{
              background: 'white',
              border: '1px solid #e5e7eb',
              borderRadius: '8px',
              padding: '14px',
              boxShadow: '0 1px 3px rgba(0,0,0,0.1)'
            }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '12px', borderBottom: '1px solid #e5e7eb', paddingBottom: '8px', justifyContent: 'center' }}>
                <FaStar size={15} color="#f59e0b" />
                <h4 style={{ margin: 0, fontSize: '0.85rem', fontWeight: '600', color: '#1f2937' }}>Rating</h4>
              </div>
              
              <div style={{ display: 'flex', gap: '14px', alignItems: 'center' }}>
                <div style={{ flexShrink: 0 }}>
                  <DonutChart 
                    data={[
                      { label: 'Business', value: analytics?.ratings?.business_rating?.count || 0, color: '#f59e0b' },
                      { label: 'Order', value: analytics?.ratings?.order_rating?.count || 0, color: '#3b82f6' },
                      { label: 'Product', value: analytics?.ratings?.product_rating?.count || 0, color: '#10b981' }
                    ]} 
                    size={90} 
                  />
                </div>
                
                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '6px 10px', fontSize: '0.72rem', flex: 1, maxHeight: '110px', overflowY: 'auto' }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '5px' }}>
                    <span style={{ width: '7px', height: '7px', borderRadius: '2px', background: '#f59e0b', flexShrink: 0 }}></span>
                    <span style={{ color: '#6b7280', fontSize: '0.7rem' }}>Business</span>
                    <span style={{ fontWeight: '600', color: '#111827', fontSize: '0.7rem', marginLeft: 'auto' }}>
                      {analytics?.ratings?.business_rating?.average?.toFixed(1) || '0.0'}
                    </span>
                  </div>
                  
                  <div style={{ display: 'flex', alignItems: 'center', gap: '5px' }}>
                    <span style={{ width: '7px', height: '7px', borderRadius: '2px', background: '#3b82f6', flexShrink: 0 }}></span>
                    <span style={{ color: '#6b7280', fontSize: '0.7rem' }}>Order</span>
                    <span style={{ fontWeight: '600', color: '#111827', fontSize: '0.7rem', marginLeft: 'auto' }}>
                      {analytics?.ratings?.order_rating?.average?.toFixed(1) || '0.0'}
                    </span>
                  </div>
                  
                  <div style={{ display: 'flex', alignItems: 'center', gap: '5px' }}>
                    <span style={{ width: '7px', height: '7px', borderRadius: '2px', background: '#10b981', flexShrink: 0 }}></span>
                    <span style={{ color: '#6b7280', fontSize: '0.7rem' }}>Product</span>
                    <span style={{ fontWeight: '600', color: '#111827', fontSize: '0.7rem', marginLeft: 'auto' }}>
                      {analytics?.ratings?.product_rating?.average?.toFixed(1) || '0.0'}
                    </span>
                  </div>
                </div>
              </div>
            </div>

            {/* Order Status - Row 3, spans all 3 columns */}
            <div style={{
              gridColumn: 'span 3',
              background: 'white',
              border: '1px solid #e5e7eb',
              borderRadius: '8px',
              padding: '14px',
              boxShadow: '0 1px 3px rgba(0,0,0,0.1)',
              minHeight: '320px',
              display: 'flex',
              flexDirection: 'column'
            }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '6px', marginBottom: '10px', borderBottom: '1px solid #e5e7eb', paddingBottom: '6px' }}>
                <FaClipboardList size={15} color="#3b82f6" />
                <h4 style={{ margin: 0, fontSize: '0.85rem', fontWeight: '600', color: '#1f2937' }}>Order Status</h4>
              </div>
              <div style={{ display: 'flex', gap: '20px', alignItems: 'center', flex: 1 }}>
                <div style={{ flexShrink: 0, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                  <DonutChart data={orderStatusData.filter(s => s.value > 0)} size={160} />
                </div>
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: '8px 12px', fontSize: '0.72rem', flex: 1, alignContent: 'center' }}>
                  {orderStatusData.map((status, i) => (
                    <div key={i} style={{ display: 'flex', alignItems: 'center', gap: '5px', opacity: status.value === 0 ? 0.5 : 1, padding: '4px 0' }}>
                      <span style={{ width: '8px', height: '8px', borderRadius: '2px', background: status.color, flexShrink: 0 }}></span>
                      <span style={{ color: '#6b7280', fontSize: '0.7rem' }}>{status.label}</span>
                      <span style={{ fontWeight: '600', color: '#111827', fontSize: '0.7rem', marginLeft: 'auto' }}>{status.value}</span>
                    </div>
                  ))}
                </div>
              </div>
            </div>
            </div>

            {/* Right side - Category Breakdown */}
            <div style={{ 
              background: 'white',
              border: '1px solid #e5e7eb',
              borderRadius: '8px',
              padding: '14px',
              boxShadow: '0 1px 3px rgba(0,0,0,0.1)'
            }}>
              <div style={{ marginBottom: '10px', borderBottom: '1px solid #e5e7eb', paddingBottom: '8px' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '6px', marginBottom: '4px' }}>
                  <FaUtensils size={15} color="#8b5cf6" />
                  <h4 style={{ margin: 0, fontSize: '0.85rem', fontWeight: '600', color: '#1f2937' }}>Category Breakdown</h4>
                </div>
                <div style={{ display: 'flex', alignItems: 'baseline', gap: '4px' }}>
                  <span style={{ fontSize: '1rem', fontWeight: '700', color: '#111827' }}>
                    {Object.values(menuCategories).reduce((sum, count) => sum + count, 0)}
                  </span>
                  <span style={{ fontSize: '0.7rem', color: '#6b7280' }}>items</span>
                </div>
              </div>
              <InventoryVisualization inventoryData={menuCategories} />
            </div>
          </div>
        ) : (
          /* Tab Content for other reports - Full Width */
          <TabContent activeTab={activeTab} />
        )}
      </div>

      {/* Detailed Business Information Sections - Inline Display */}
      <div className="detailed-sections">
        {/* Best Selling Items Section */}
        <div className="detail-section variant-menu">
          <div className="section-header-inline">
            <div className="section-icon"><FaTrophy /></div>
            <h3>Best Selling Items</h3>
          </div>
          <BestSellingItemsSection businessId={businessId} />
        </div>

        {/* Business Settings Section */}
        <div className="detail-section variant-ops">
          <div className="section-header-inline">
            <div className="section-icon"><FaCogs /></div>
            <h3>Business Settings</h3>
          </div>
          <OpsSettingsSection data={details?.business_settings || {}} />
        </div>

        {/* Branches Section */}
        <div className="detail-section variant-branches">
          <div className="section-header-inline">
            <div className="section-icon"><FaStore /></div>
            <h3>Branches</h3>
          </div>
          <BranchesSection data={branches} businessType={businessType} />
        </div>

        {/* System Alerts Section */}
        {alerts.length > 0 && (
          <div className="detail-section variant-flags">
            <div className="section-header-inline">
              <div className="section-icon"><FaInbox /></div>
              <h3>System Alerts ({alerts.length})</h3>
            </div>
            <AlertsSection businessId={businessId} alerts={alerts} />
          </div>
        )}

        {/* Payment Details Section */}
        <div className="detail-section variant-payments">
          <div className="section-header-inline">
            <div className="section-icon"><FaCreditCard /></div>
            <h3>Payment and order Details</h3>
            <button className="btn-download-excel" onClick={() => downloadPaymentsExcel(paymentsData, recentOrders)}>
              <FaDownload /> Download
            </button>
          </div>
          <PaymentsSection data={paymentsData} onViewDetails={(payment) => {
            setSelectedPayment(payment);
            setShowPaymentDetails(true);
          }} />
        </div>

        {/* Full Menu Section - Beside Payment Details */}
        <div className="detail-section variant-menu">
          <div className="section-header-inline">
            <div className="section-icon">{businessType === 'G01' ? <FaShoppingCart /> : <FaUtensils />}</div>
            <h3>{menuLabel}</h3>
            <button className="btn-download-excel" onClick={() => downloadMenuExcel(menuData, businessType)}>
              <FaDownload /> Download
            </button>
          </div>
          <PaginatedFullMenuSection data={menuData} />
        </div>

        {/* Offers & Promotions Section - Below Payment Details */}
        <div className="detail-section variant-offers">
          <div className="section-header-inline">
            <div className="section-icon"><FaGift /></div>
            <h3>Offers & Promotions</h3>
          </div>
          <OffersSection data={details?.offers || {}} businessId={businessId} />
        </div>

        {/* Frequent Users Section - Beside Offers & Promotions */}
        <div className="detail-section variant-users">
          <div className="section-header-inline">
            <div className="section-icon"><FaUsers /></div>
            <h3>Frequent Users</h3>
          </div>
          <FrequentUsersSection businessId={businessId} />
        </div>

      </div>

      {/* Full Overview Modal */}
      {showFullOverview && (
        <div className="modal-backdrop" onClick={() => setShowFullOverview(false)}>
          <div className="modal" onClick={(e) => e.stopPropagation()}>
            <div className="modal-header">
              <h3><FaChartBar /> Complete Business Overview</h3>
              <button onClick={() => setShowFullOverview(false)}>×</button>
            </div>
            <div className="modal-body">
              <OverviewSection data={details} isLimited={false} />
            </div>
          </div>
        </div>
      )}

      {/* Payment Details Modal */}
      {showPaymentDetails && (
        <div className="modal-backdrop" onClick={() => setShowPaymentDetails(false)}>
          <div className="modal" onClick={(e) => e.stopPropagation()}>
            <div className="modal-header">
              <h3><FaCreditCard /> Complete Payment & Order Details</h3>
              <button onClick={() => setShowPaymentDetails(false)}>×</button>
            </div>
            <div className="modal-body">
              <PaymentDetailsModal payment={selectedPayment} orderData={recentOrders} />
            </div>
          </div>
        </div>
      )}

      {/* Share Modal */}
      {showShareModal && (
        <div 
          className="modal-backdrop"
          onClick={() => {
            console.log('Share modal overlay clicked');
            setShowShareModal(false);
          }}
        >
          <div 
            className="modal"
            onClick={(e) => {
              console.log('Share modal content clicked');
              e.stopPropagation();
            }}
            style={{ maxWidth: '600px' }}
          >
            <div className="modal-header">
              <h3>Share Business Details</h3>
              <button onClick={() => setShowShareModal(false)}>×</button>
            </div>
            <div className="modal-body">
              <p style={{ marginBottom: '20px', color: '#666' }}>
                Share this business details page via your preferred platform
              </p>

              {/* Share Buttons Grid */}
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(140px, 1fr))', gap: '12px', marginBottom: '20px' }}>
                
                {/* WhatsApp */}
                <button onClick={handleShareWhatsApp} style={{ padding: '16px', background: '#25D366', color: 'white', border: 'none', borderRadius: '8px', cursor: 'pointer', fontSize: '14px', fontWeight: '600' }}>
                  WhatsApp
                </button>

                {/* Email */}
                <button onClick={handleShareEmail} style={{ padding: '16px', background: '#EA4335', color: 'white', border: 'none', borderRadius: '8px', cursor: 'pointer', fontSize: '14px', fontWeight: '600' }}>
                  Email
                </button>

                {/* Telegram */}
                <button onClick={handleShareTelegram} style={{ padding: '16px', background: '#0088cc', color: 'white', border: 'none', borderRadius: '8px', cursor: 'pointer', fontSize: '14px', fontWeight: '600' }}>
                  Telegram
                </button>

                {/* LinkedIn */}
                <button onClick={handleShareLinkedIn} style={{ padding: '16px', background: '#0077B5', color: 'white', border: 'none', borderRadius: '8px', cursor: 'pointer', fontSize: '14px', fontWeight: '600' }}>
                  LinkedIn
                </button>

                {/* Twitter */}
                <button onClick={handleShareTwitter} style={{ padding: '16px', background: '#000000', color: 'white', border: 'none', borderRadius: '8px', cursor: 'pointer', fontSize: '14px', fontWeight: '600' }}>
                  Twitter
                </button>

                {/* Facebook */}
                <button onClick={handleShareFacebook} style={{ padding: '16px', background: '#1877F2', color: 'white', border: 'none', borderRadius: '8px', cursor: 'pointer', fontSize: '14px', fontWeight: '600' }}>
                  Facebook
                </button>

                {/* SMS */}
                <button onClick={handleShareSMS} style={{ padding: '16px', background: '#34C759', color: 'white', border: 'none', borderRadius: '8px', cursor: 'pointer', fontSize: '14px', fontWeight: '600' }}>
                  SMS
                </button>

                {/* Copy Link */}
                <button onClick={handleCopyLink} style={{ padding: '16px', background: '#6B7280', color: 'white', border: 'none', borderRadius: '8px', cursor: 'pointer', fontSize: '14px', fontWeight: '600' }}>
                  Copy Link
                </button>
              </div>

              {/* Link Preview */}
              <div style={{ padding: '12px', background: '#f3f4f6', borderRadius: '6px', fontSize: '13px', wordBreak: 'break-all' }}>
                <strong>Link:</strong><br />
                {`${window.location.origin}${window.location.pathname}#business-details/${businessId}`}
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Settings Modal */}
      {showSettingsModal && (
        <div className="modal-backdrop" onClick={() => setShowSettingsModal(false)}>
          <div className="modal" onClick={(e) => e.stopPropagation()} style={{ maxWidth: '600px' }}>
            <div className="modal-header">
              <h3>Business Settings</h3>
              <button onClick={() => setShowSettingsModal(false)}>×</button>
            </div>
            <div className="modal-body">
              <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
                <div className="setting-group">
                  <h4 style={{ marginBottom: '12px', fontSize: '16px', fontWeight: '600' }}>Display Settings</h4>
                  <label style={{ display: 'flex', alignItems: 'center', gap: '8px', cursor: 'pointer' }}>
                    <input type="checkbox" defaultChecked />
                    <span>Show detailed analytics</span>
                  </label>
                  <label style={{ display: 'flex', alignItems: 'center', gap: '8px', cursor: 'pointer' }}>
                    <input type="checkbox" defaultChecked />
                    <span>Show payment details</span>
                  </label>
                  <label style={{ display: 'flex', alignItems: 'center', gap: '8px', cursor: 'pointer' }}>
                    <input type="checkbox" defaultChecked />
                    <span>Show menu items</span>
                  </label>
                </div>

                <div className="setting-group">
                  <h4 style={{ marginBottom: '12px', fontSize: '16px', fontWeight: '600' }}>Data Refresh</h4>
                  <label style={{ display: 'flex', alignItems: 'center', gap: '8px', cursor: 'pointer' }}>
                    <input type="checkbox" defaultChecked />
                    <span>Auto-refresh data every 5 minutes</span>
                  </label>
                </div>

                <div className="setting-group">
                  <h4 style={{ marginBottom: '12px', fontSize: '16px', fontWeight: '600' }}>Export Settings</h4>
                  <label style={{ display: 'block', marginBottom: '8px' }}>
                    <span style={{ display: 'block', marginBottom: '4px', fontSize: '14px', fontWeight: '500' }}>Default Export Format</span>
                    <select style={{ width: '100%', padding: '8px', borderRadius: '4px', border: '1px solid #d1d5db' }}>
                      <option value="csv">CSV (Excel)</option>
                      <option value="json">JSON</option>
                      <option value="excel">Excel (XLSX)</option>
                    </select>
                  </label>
                </div>

                <div style={{ display: 'flex', gap: '12px', marginTop: '20px' }}>
                  <button 
                    className="btn-primary" 
                    onClick={() => {
                      setSaveMessage('✓ Settings saved!');
                      setTimeout(() => setSaveMessage(''), 3000);
                      setShowSettingsModal(false);
                    }}
                    style={{ flex: 1, padding: '10px' }}
                  >
                    Save Settings
                  </button>
                  <button 
                    className="btn-secondary" 
                    onClick={() => setShowSettingsModal(false)}
                    style={{ flex: 1, padding: '10px' }}
                  >
                    Cancel
                  </button>
                </div>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

// Modal Section Components
function OverviewSection({ data, isLimited = false, onViewMore }) {
  const b = data?.basic_info || {};
  const s = data?.status_info || {};
  const o = data?.owner_details || {};
  const isInherited = o?.inherited_from_master;

  if (isLimited) {
    // Show limited data inline
    return (
      <div className="two-col">
        <div>
          <h4>Basic Info</h4>
          <div className="info-grid">
            <div className="info"><span className="label">Name</span><span className="value">{b.business_name}</span></div>
            <div className="info"><span className="label">Outlet</span><span className="value">{b.outlet_name} ({b.outlet_code})</span></div>
            <div className="info"><span className="label">Category</span><span className="value">{b.business_category_detailed || b.business_category}</span></div>
            <div className="info"><span className="label">Contact</span><span className="value">{b.phone}</span></div>
          </div>
        </div>
        <div>
          <h4>Status</h4>
          <div className="badge-row">
            <span className={`badge ${s.operational_status === 'active' ? 'success' : 'warning'}`}>{s.operational_status || '-'}</span>
            <span className={`badge ${b.is_verified ? 'success' : 'neutral'}`}>{b.is_verified ? 'Verified' : 'Unverified'}</span>
          </div>
          <div className="info-grid" style={{ marginTop: 8 }}>
            <div className="info"><span className="label">Hygiene</span><span className="value">{s.hygiene_rating ?? '-'}</span></div>
            <div className="info"><span className="label">Reliability</span><span className="value">{s.reliability_score ?? '-'}</span></div>
          </div>
          <div style={{ marginTop: 8 }}>
            <h4 style={{ margin: 0 }}>
              Owner {isInherited && <span style={{ fontSize: '0.75rem', color: '#f59e0b', fontWeight: 'normal' }}>(from Master)</span>}
            </h4>
            <div className="info-grid three-col">
              <div className="info"><span className="label">Name</span><span className="value">{o.owner_name || '-'}</span></div>
              <div className="info"><span className="label">Email</span><span className="value">{o.owner_email || '-'}</span></div>
              <div className="info"><span className="label">Phone</span><span className="value">{o.owner_phone || '-'}</span></div>
            </div>
          </div>
        </div>
      </div>
    );
  }

  // Show full data in modal - single column layout
  return (
    <div className="modal-overview-content">
      <div className="modal-section">
        <h4>BASIC INFO</h4>
        <div className="modal-info-grid">
          <div className="modal-info-row">
            <span className="modal-label">Name</span>
            <span className="modal-value">{b.business_name}</span>
          </div>
          <div className="modal-info-row">
            <span className="modal-label">Outlet</span>
            <span className="modal-value">{b.outlet_name} ({b.outlet_code})</span>
          </div>
          <div className="modal-info-row">
            <span className="modal-label">Category</span>
            <span className="modal-value">{b.business_category_detailed || b.business_category}</span>
          </div>
          <div className="modal-info-row">
            <span className="modal-label">Type</span>
            <span className="modal-value">{b.business_type_detailed || b.business_type}</span>
          </div>
          <div className="modal-info-row">
            <span className="modal-label">Contact</span>
            <span className="modal-value">{b.phone} / {b.email}</span>
          </div>
          <div className="modal-info-row">
            <span className="modal-label">Address</span>
            <span className="modal-value">{b.address}, {b.city}, {b.state} - {b.pincode}</span>
          </div>
          <div className="modal-info-row">
            <span className="modal-label">Geo</span>
            <span className="modal-value">{b.latitude}, {b.longitude}</span>
          </div>
          <div className="modal-info-row">
            <span className="modal-label">Created</span>
            <span className="modal-value">{formatDate(b.created_at)}</span>
          </div>
        </div>
      </div>
    </div>
  );
}

function FinancialsSection({ data }) {
  const isInherited = data?.inherited_from_master;
  
  return (
    <div>
      {isInherited && (
        <div style={{
          background: 'linear-gradient(135deg, #f59e0b 0%, #d97706 100%)',
          color: 'white',
          padding: '12px 16px',
          borderRadius: '8px',
          marginBottom: '16px',
          fontSize: '0.875rem',
          fontWeight: '500',
          display: 'flex',
          alignItems: 'center',
          gap: '8px'
        }}>
          <FaBuilding size={16} />
          <span>Financial details inherited from Master Business: {data.master_business_id}</span>
        </div>
      )}
      <div className="two-col">
        <div>
          <h4>Tax & Identity</h4>
          <div className="info-grid">
            <div className="info"><span className="label">PAN</span><span className="value">{data.owner_pan || '-'}</span></div>
            <div className="info"><span className="label">GSTIN</span><span className="value">{data.gstin || '-'}</span></div>
            <div className="info"><span className="label">FSSAI</span><span className="value">{data.fssai_certification_number || '-'}</span></div>
            <div className="info"><span className="label">Updated</span><span className="value">{formatDate(data.updated_at)}</span></div>
          </div>
        </div>
        <div>
          <h4>Banking & Razorpay</h4>
          <div className="info-grid">
            <div className="info"><span className="label">IFSC</span><span className="value">{data.ifsc_code || '-'}</span></div>
            <div className="info"><span className="label">Account#</span><span className="value">****{last4(data.account_number)}</span></div>
            <div className="info"><span className="label">Razorpay Key</span><span className="value">{data.razor_pay_key_id || '-'}</span></div>
            <div className="info"><span className="label">Webhook</span><span className="value">{data.razor_webhook_secret || '-'}</span></div>
          </div>
        </div>
      </div>
    </div>
  );
}

function OrdersAnalyticsSection({ data }) {
  const a = data?.consumer_report || {};
  const recent = data?.recent_orders || [];
  return (
    <div>
      <div className="kpi-row">
        <div className="kpi"><div className="kpi-value">{toNumber(a.total_orders)}</div><div className="kpi-label">Total Orders</div></div>
        <div className="kpi"><div className="kpi-value">{toCurrency(a.total_revenue)}</div><div className="kpi-label">Total Revenue</div></div>
        <div className="kpi"><div className="kpi-value">{a.period_days ? `${a.period_days}d` : '-'}</div><div className="kpi-label">Period</div></div>
      </div>
      <div style={{ marginTop: 12 }} className="scroll-x">
        <table className="data-table">
          <thead>
            <tr>
              <th>Order</th>
              <th>Status</th>
              <th>Amount</th>
              <th>Created</th>
              <th>User</th>
            </tr>
          </thead>
          <tbody>
            {recent.map(r => (
              <tr key={r.order_id}>
                <td>#{r.order_id}</td>
                <td><span className={`badge ${r.status === 'success' ? 'success' : r.status === 'pending' ? 'warning' : 'danger'}`}>{r.status}</span></td>
                <td>{toCurrency(r.amount)}</td>
                <td>{formatDate(r.created_at)}</td>
                <td>{r.user_id}</td>
              </tr>
            ))}
            {!recent.length && (
              <tr>
                <td colSpan="5" className="muted">No recent orders</td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function RatingsSection({ data }) {
  const ar = data?.analytics || {};
  return (
    <div>
      <h4>Performance & Ratings</h4>
      <div className="kpi-row">
        <div className="kpi"><div className="kpi-value">{ar.customer_rating ?? '-'}</div><div className="kpi-label">Customer Rating</div></div>
        <div className="kpi"><div className="kpi-value">{ar.completion_rate != null ? `${Math.round(ar.completion_rate * 100)}%` : '-'}</div><div className="kpi-label">Completion</div></div>
        <div className="kpi"><div className="kpi-value">{ar.average_order_value != null ? toCurrency(ar.average_order_value) : '-'}</div><div className="kpi-label">Avg Order Value</div></div>
      </div>
    </div>
  );
}



function BestSellingItemsSection({ businessId }) {
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let mounted = true;
    (async () => {
      try {
        setLoading(true);
        const res = await AdminService.getBestSellingItems(businessId, 30, 10);
        if (mounted && res?.success) {
          setItems(res.data.items || []);
        }
      } catch (e) {
        console.error('Failed to load best-selling items', e);
      } finally {
        if (mounted) setLoading(false);
      }
    })();
    return () => { mounted = false; };
  }, [businessId]);

  if (loading) return <div className="loading-small">Loading best sellers...</div>;
  if (!items.length) return <div className="muted">No sales data available</div>;

  return (
    <div>
      <h4 style={{ margin: '0 0 12px 0' }}>Top Performing Items</h4>
      <div className="scroll-x">
        <table className="data-table">
          <thead>
            <tr>
              <th style={{ width: '40px' }}>Rank</th>
              <th>Item Name</th>
              <th>Orders</th>
              <th>Qty Sold</th>
              <th>Revenue</th>
              <th>Avg Price</th>
            </tr>
          </thead>
          <tbody>
            {items.map((item, index) => (
              <tr key={index}>
                <td>
                  <div style={{ 
                    display: 'flex', 
                    alignItems: 'center', 
                    justifyContent: 'center',
                    width: '28px',
                    height: '28px',
                    borderRadius: '50%',
                    background: index === 0 ? '#ffd700' : index === 1 ? '#c0c0c0' : index === 2 ? '#cd7f32' : '#e5e7eb',
                    fontWeight: '700',
                    fontSize: '0.85rem',
                    color: index < 3 ? 'white' : '#6b7280'
                  }}>
                    {index + 1}
                  </div>
                </td>
                <td>
                  <div style={{ fontWeight: '600', color: '#111827' }}>{item.item_name}</div>
                </td>
                <td>
                  <span className="badge neutral">{toNumber(item.order_count)}</span>
                </td>
                <td>
                  <span style={{ fontWeight: '600', color: '#3b82f6' }}>{toNumber(item.total_quantity_sold)}</span>
                </td>
                <td>
                  <span style={{ fontWeight: '700', color: '#10b981' }}>{toCurrency(item.total_revenue)}</span>
                </td>
                <td>{toCurrency(item.avg_price)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function FrequentUsersSection({ businessId }) {
  const [users, setUsers] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let mounted = true;
    (async () => {
      try {
        setLoading(true);
        const res = await AdminService.getFrequentUsers(businessId, 90, 10);
        if (mounted && res?.success) {
          setUsers(res.data.users || []);
        }
      } catch (e) {
        console.error('Failed to load frequent users', e);
      } finally {
        if (mounted) setLoading(false);
      }
    })();
    return () => { mounted = false; };
  }, [businessId]);

  if (loading) return <div className="loading-small">Loading frequent users...</div>;
  if (!users.length) return <div className="muted">No user data available</div>;

  return (
    <div>
      <h4 style={{ margin: '0 0 12px 0' }}>Top Customers</h4>
      <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
        {users.map((user, index) => (
          <div key={user.user_id} style={{
            display: 'flex',
            alignItems: 'center',
            gap: '12px',
            padding: '12px',
            background: '#f9fafb',
            borderRadius: '8px',
            border: '1px solid #e5e7eb'
          }}>
            <div style={{
              width: '32px',
              height: '32px',
              borderRadius: '50%',
              background: index === 0 ? '#ffd700' : index === 1 ? '#c0c0c0' : index === 2 ? '#cd7f32' : '#3b82f6',
              color: 'white',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              fontWeight: '700',
              fontSize: '0.85rem',
              flexShrink: 0
            }}>
              {index + 1}
            </div>
            {user.profile_url ? (
              <img 
                src={user.profile_url} 
                alt={user.name}
                style={{
                  width: '40px',
                  height: '40px',
                  borderRadius: '50%',
                  objectFit: 'cover',
                  border: '2px solid #e5e7eb'
                }}
              />
            ) : (
              <div style={{
                width: '40px',
                height: '40px',
                borderRadius: '50%',
                background: '#e5e7eb',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                fontSize: '1.2rem',
                color: '#6b7280',
                fontWeight: '600'
              }}>
                {user.name.charAt(0).toUpperCase()}
              </div>
            )}
            <div style={{ flex: 1, minWidth: 0 }}>
              <div style={{ fontWeight: '600', color: '#111827', fontSize: '0.9rem', marginBottom: '2px' }}>
                {user.name}
              </div>
              <div style={{ fontSize: '0.75rem', color: '#6b7280' }}>
                {user.phone}
              </div>
            </div>
            <div style={{ textAlign: 'right' }}>
              <div style={{ fontWeight: '700', color: '#3b82f6', fontSize: '0.85rem' }}>
                {user.order_count} orders
              </div>
              <div style={{ fontSize: '0.75rem', color: '#10b981', fontWeight: '600' }}>
                {toCurrency(user.total_spent)}
              </div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

function MenuSection({ data }) {
  const menuItems = data?.menu_items || [];
  const groceries = data?.grocery_products || [];
  return (
    <div>
      <h4>Menu Management</h4>
      <div className="kpi-row">
        <div className="kpi"><div className="kpi-value">{toNumber(menuItems.length)}</div><div className="kpi-label">Restaurant Items</div></div>
        <div className="kpi"><div className="kpi-value">{toNumber(groceries.length)}</div><div className="kpi-label">Grocery Products</div></div>
      </div>
      <div className="scroll-x" style={{ marginTop: 12 }}>
        <table className="data-table">
          <thead>
            <tr>
              <th>Item</th>
              <th>Category</th>
              <th>Size</th>
              <th>Price</th>
              <th>Status</th>
              <th>Updated</th>
            </tr>
          </thead>
          <tbody>
            {menuItems.map(it => (
              <tr key={it.item_id}>
                <td>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                    {it.image && <img className="thumb" src={it.image} alt={it.name} />}
                    {it.name}
                  </div>
                </td>
                <td>{it.category}</td>
                <td>{it.size_label}</td>
                <td>{toCurrency(it.price)}</td>
                <td><span className={`badge ${it.is_active ? 'success' : 'neutral'}`}>{it.is_active ? 'Active' : 'Inactive'}</span></td>
                <td>{formatDate(it.updated_at)}</td>
              </tr>
            ))}
            {!menuItems.length && (
              <tr>
                <td colSpan="6" className="muted">No items</td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function FleetSection({ data }) {
  const partners = data?.partners || [];
  return (
    <div>
      <h4>Delivery Fleet</h4>
      <div className="kpi-row">
        <div className="kpi"><div className="kpi-value">{toNumber(data?.total_partners)}</div><div className="kpi-label">Total</div></div>
        <div className="kpi"><div className="kpi-value">{toNumber(data?.available)}</div><div className="kpi-label">Available</div></div>
        <div className="kpi"><div className="kpi-value">{toNumber(data?.on_delivery)}</div><div className="kpi-label">On Delivery</div></div>
      </div>
      <div className="scroll-x" style={{ marginTop: 12 }}>
        <table className="data-table">
          <thead>
            <tr>
              <th>User</th>
              <th>Vehicle</th>
              <th>Number</th>
              <th>Phone</th>
              <th>Status</th>
            </tr>
          </thead>
          <tbody>
            {partners.map(p => (
              <tr key={p.user_id}>
                <td>{p.user_id}</td>
                <td>{p.vehicle_type}</td>
                <td>{p.vehicle_number}</td>
                <td>{p.phone_number}</td>
                <td><span className={`badge ${p.status === '1' ? 'success' : 'neutral'}`}>{p.status === '1' ? 'Online' : 'Offline'}</span></td>
              </tr>
            ))}
            {!partners.length && (
              <tr>
                <td colSpan="5" className="muted">No partners</td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function InventorySection({ data }) {
  return (
    <div>
      <h4>Inventory</h4>
      <div className="kpi-row">
        <div className="kpi"><div className="kpi-value">{toNumber(data?.low_stock_variants?.length || 0)}</div><div className="kpi-label">Low Stock</div></div>
        <div className="kpi"><div className="kpi-value">{toNumber(data?.bom_items?.length || 0)}</div><div className="kpi-label">BOM Items</div></div>
      </div>
    </div>
  );
}

function OffersSection({ data, businessId }) {
  const [offersData, setOffersData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [activeTab, setActiveTab] = useState('offers'); // 'offers', 'coupons'

  useEffect(() => {
    if (businessId) {
      fetchOffersAndCoupons();
    }
  }, [businessId]);

  const fetchOffersAndCoupons = async () => {
    setLoading(true);
    setError(null);
    try {
      const result = await AdminService.adminApiCall(
        `/analytics/business-offers-coupons/?business_id=${businessId}`
      );
      
      if (result.success) {
        setOffersData(result);
      } else {
        throw new Error(result.message || 'Failed to fetch offers and coupons');
      }
    } catch (err) {
      console.error('Error fetching offers and coupons:', err);
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  if (loading) {
    return (
      <div className="enhanced-section-content">
        <div className="loading-state">
          <div className="spinner"></div>
          <p>Loading offers and coupons...</p>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="enhanced-section-content">
        <div className="error-state">
          <p>Error loading offers: {error}</p>
        </div>
      </div>
    );
  }

  const metadata = offersData?.metadata || {};
  const offers = offersData?.data?.offers || [];
  const coupons = offersData?.data?.coupons || [];
  const totalActive = (metadata.active_offers || 0) + (metadata.active_coupons || 0);

  // Render individual offer card
  const renderOfferCard = (offer) => (
    <div 
      key={offer.promo_id} 
      style={{
        padding: '16px',
        border: '1px solid #e0e0e0',
        borderRadius: '8px',
        backgroundColor: '#fff',
        borderLeft: `4px solid ${offer.status === 'active' ? '#28a745' : '#6c757d'}`,
        opacity: offer.status === 'active' ? 1 : 0.7,
        transition: 'all 0.3s ease',
        cursor: 'pointer',
        height: '100%',
        display: 'flex',
        flexDirection: 'column'
      }}
      onMouseEnter={(e) => {
        e.currentTarget.style.boxShadow = '0 4px 12px rgba(0,0,0,0.1)';
        e.currentTarget.style.transform = 'translateY(-2px)';
      }}
      onMouseLeave={(e) => {
        e.currentTarget.style.boxShadow = 'none';
        e.currentTarget.style.transform = 'translateY(0)';
      }}
    >
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '10px' }}>
        <strong style={{ fontSize: '14px', color: '#2c3e50', flex: 1 }}>{offer.title}</strong>
        <span 
          style={{
            padding: '4px 10px',
            borderRadius: '12px',
            fontSize: '11px',
            fontWeight: '600',
            backgroundColor: offer.status === 'active' ? '#d4edda' : '#e2e3e5',
            color: offer.status === 'active' ? '#155724' : '#383d41',
            whiteSpace: 'nowrap',
            marginLeft: '8px'
          }}
        >
          {offer.status}
        </span>
      </div>
      <p style={{ fontSize: '12px', color: '#6c757d', marginBottom: '12px', flex: 1 }}>{offer.description}</p>
      <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
        <span 
          style={{
            backgroundColor: '#28a745',
            color: 'white',
            padding: '6px 12px',
            borderRadius: '20px',
            fontSize: '12px',
            fontWeight: '600',
            textAlign: 'center',
            display: 'inline-block'
          }}
        >
          {offer.discount_percentage ? `${offer.discount_percentage}% OFF` : `₹${offer.discount_amount} OFF`}
        </span>
        <span style={{ fontSize: '11px', color: '#6c757d' }}>
          <FaCalendarAlt /> {new Date(offer.valid_from).toLocaleDateString()} - {new Date(offer.valid_to).toLocaleDateString()}
        </span>
      </div>
    </div>
  );

  // Render individual coupon card
  const renderCouponCard = (coupon) => (
    <div 
      key={coupon.coupon_id} 
      style={{
        padding: '16px',
        border: '1px solid #e0e0e0',
        borderRadius: '8px',
        backgroundColor: '#fff',
        borderLeft: `4px solid ${coupon.status === 'active' ? '#007bff' : '#6c757d'}`,
        opacity: coupon.status === 'active' ? 1 : 0.7,
        transition: 'all 0.3s ease',
        cursor: 'pointer',
        height: '100%',
        display: 'flex',
        flexDirection: 'column'
      }}
      onMouseEnter={(e) => {
        e.currentTarget.style.boxShadow = '0 4px 12px rgba(0,0,0,0.1)';
        e.currentTarget.style.transform = 'translateY(-2px)';
      }}
      onMouseLeave={(e) => {
        e.currentTarget.style.boxShadow = 'none';
        e.currentTarget.style.transform = 'translateY(0)';
      }}
    >
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '10px' }}>
        <div style={{ flex: 1 }}>
          <code 
            style={{
              backgroundColor: '#e7f3ff',
              border: '2px dashed #007bff',
              padding: '6px 12px',
              borderRadius: '4px',
              fontSize: '13px',
              fontWeight: '700',
              color: '#007bff',
              display: 'inline-block',
              marginBottom: '8px'
            }}
          >
            {coupon.coupon_code}
          </code>
          <div style={{ fontSize: '14px', fontWeight: '600', color: '#2c3e50' }}>{coupon.coupon_name}</div>
        </div>
        <span 
          style={{
            padding: '4px 10px',
            borderRadius: '12px',
            fontSize: '11px',
            fontWeight: '600',
            backgroundColor: coupon.status === 'active' ? '#d4edda' : '#e2e3e5',
            color: coupon.status === 'active' ? '#155724' : '#383d41',
            whiteSpace: 'nowrap',
            marginLeft: '8px'
          }}
        >
          {coupon.status}
        </span>
      </div>
      <p style={{ fontSize: '12px', color: '#6c757d', marginBottom: '12px', flex: 1 }}>{coupon.description}</p>
      <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
        <span 
          style={{
            backgroundColor: '#007bff',
            color: 'white',
            padding: '6px 12px',
            borderRadius: '20px',
            fontSize: '12px',
            fontWeight: '600',
            textAlign: 'center',
            display: 'inline-block'
          }}
        >
          {coupon.discount_type === 'percentage' ? `${coupon.discount_value}% OFF` : `₹${coupon.discount_value} OFF`}
        </span>
        <div style={{ fontSize: '11px', color: '#6c757d' }}>
          <FaChartBar /> Used: {coupon.current_usage_count}/{coupon.total_usage_limit || '∞'}
        </div>
        {coupon.total_usage_limit && (
          <div style={{ width: '100%', height: '6px', backgroundColor: '#e9ecef', borderRadius: '3px', overflow: 'hidden' }}>
            <div 
              style={{
                width: `${(coupon.current_usage_count / coupon.total_usage_limit) * 100}%`,
                height: '100%',
                backgroundColor: (coupon.current_usage_count / coupon.total_usage_limit) > 0.8 ? '#dc3545' : '#007bff',
                transition: 'width 0.3s ease'
              }}
            ></div>
          </div>
        )}
      </div>
    </div>
  );

  return (
    <div className="enhanced-section-content">
      {/* Tab Navigation */}
      <div style={{ 
        display: 'flex', 
        gap: '8px', 
        marginBottom: '20px', 
        borderBottom: '2px solid #e9ecef',
        paddingBottom: '0'
      }}>
        <button
          onClick={() => setActiveTab('offers')}
          style={{
            padding: '10px 20px',
            border: 'none',
            backgroundColor: 'transparent',
            borderBottom: activeTab === 'offers' ? '3px solid #28a745' : '3px solid transparent',
            color: activeTab === 'offers' ? '#28a745' : '#6c757d',
            fontWeight: activeTab === 'offers' ? '600' : '400',
            cursor: 'pointer',
            fontSize: '14px',
            transition: 'all 0.3s ease'
          }}
        >
          Offers ({offers.length})
        </button>
        <button
          onClick={() => setActiveTab('coupons')}
          style={{
            padding: '10px 20px',
            border: 'none',
            backgroundColor: 'transparent',
            borderBottom: activeTab === 'coupons' ? '3px solid #007bff' : '3px solid transparent',
            color: activeTab === 'coupons' ? '#007bff' : '#6c757d',
            fontWeight: activeTab === 'coupons' ? '600' : '400',
            cursor: 'pointer',
            fontSize: '14px',
            transition: 'all 0.3s ease'
          }}
        >
          Coupons ({coupons.length})
        </button>
      </div>

      {/* Content based on active tab */}
      {activeTab === 'offers' && (
        <div>
          {offers.length > 0 ? (
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(300px, 1fr))', gap: '16px' }}>
              {offers.map(renderOfferCard)}
            </div>
          ) : (
            <div className="empty-state">
              <div className="empty-state-icon">🎁</div>
              <div className="empty-state-text">No promotional offers available</div>
            </div>
          )}
        </div>
      )}

      {activeTab === 'coupons' && (
        <div>
          {coupons.length > 0 ? (
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(300px, 1fr))', gap: '16px' }}>
              {coupons.map(renderCouponCard)}
            </div>
          ) : (
            <div className="empty-state">
              <div className="empty-state-icon">🎟️</div>
              <div className="empty-state-text">No coupons available</div>
            </div>
          )}
        </div>
      )}

      {/* Empty State when no data at all */}
      {offers.length === 0 && coupons.length === 0 && !loading && (
        <div className="empty-state">
          <div className="empty-state-icon">
            <FaInbox />
          </div>
          <div className="empty-state-text">No active offers or promotions at the moment</div>
        </div>
      )}
    </div>
  );
}

function PaymentsSection({ data, onViewDetails }) {
  const [currentPage, setCurrentPage] = useState(1);
  const [itemsPerPage, setItemsPerPage] = useState(20);
  const [selectedFilter, setSelectedFilter] = useState('Monthly');
  const [startDate, setStartDate] = useState('');
  const [endDate, setEndDate] = useState('');
  const totals = data?.totals || {};
  const recent = data?.recent_payments || [];

  const dateFilters = ['Today', 'Weekly', 'Monthly', 'Quarterly', 'Half Yearly', 'Yearly', 'Custom'];

  // Date filtering function
  const getFilteredPayments = () => {
    if (!recent || recent.length === 0) return [];

    const now = new Date();
    let filteredPayments = [...recent];

    switch (selectedFilter) {
      case 'Today':
        filteredPayments = recent.filter(payment => {
          if (!payment.created_at) return false;
          const paymentDate = new Date(payment.created_at);
          return paymentDate.toDateString() === now.toDateString();
        });
        break;

      case 'Weekly':
        const weekAgo = new Date(now.getTime() - 7 * 24 * 60 * 60 * 1000);
        filteredPayments = recent.filter(payment => {
          if (!payment.created_at) return false;
          const paymentDate = new Date(payment.created_at);
          return paymentDate >= weekAgo && paymentDate <= now;
        });
        break;

      case 'Monthly':
        const monthAgo = new Date(now.getFullYear(), now.getMonth() - 1, now.getDate());
        filteredPayments = recent.filter(payment => {
          if (!payment.created_at) return false;
          const paymentDate = new Date(payment.created_at);
          return paymentDate >= monthAgo && paymentDate <= now;
        });
        break;

      case 'Quarterly':
        const quarterAgo = new Date(now.getFullYear(), now.getMonth() - 3, now.getDate());
        filteredPayments = recent.filter(payment => {
          if (!payment.created_at) return false;
          const paymentDate = new Date(payment.created_at);
          return paymentDate >= quarterAgo && paymentDate <= now;
        });
        break;

      case 'Half Yearly':
        const halfYearAgo = new Date(now.getFullYear(), now.getMonth() - 6, now.getDate());
        filteredPayments = recent.filter(payment => {
          if (!payment.created_at) return false;
          const paymentDate = new Date(payment.created_at);
          return paymentDate >= halfYearAgo && paymentDate <= now;
        });
        break;

      case 'Yearly':
        const yearAgo = new Date(now.getFullYear() - 1, now.getMonth(), now.getDate());
        filteredPayments = recent.filter(payment => {
          if (!payment.created_at) return false;
          const paymentDate = new Date(payment.created_at);
          return paymentDate >= yearAgo && paymentDate <= now;
        });
        break;

      case 'Custom':
        if (startDate && endDate) {
          const start = new Date(startDate);
          const end = new Date(endDate);
          end.setHours(23, 59, 59, 999); // Include the entire end date
          
          filteredPayments = recent.filter(payment => {
            if (!payment.created_at) return false;
            const paymentDate = new Date(payment.created_at);
            return paymentDate >= start && paymentDate <= end;
          });
        }
        break;

      default:
        filteredPayments = recent;
    }

    return filteredPayments;
  };

  const filteredPayments = getFilteredPayments();
  
  // Calculate totals from filtered payments
  const filteredTotals = {
    success_amount: 0,
    pending_amount: 0,
    failed_amount: 0,
    success_count: 0,
    pending_count: 0,
    failed_count: 0
  };
  
  filteredPayments.forEach(payment => {
    const amount = parseFloat(payment.amount) || 0;
    if (payment.status === 'success') {
      filteredTotals.success_amount += amount;
      filteredTotals.success_count++;
    } else if (payment.status === 'pending') {
      filteredTotals.pending_amount += amount;
      filteredTotals.pending_count++;
    } else if (payment.status === 'failed') {
      filteredTotals.failed_amount += amount;
      filteredTotals.failed_count++;
    }
  });
  
  const totalPages = Math.ceil(filteredPayments.length / itemsPerPage);
  const startIndex = (currentPage - 1) * itemsPerPage;
  const endIndex = startIndex + itemsPerPage;
  const currentPayments = filteredPayments.slice(startIndex, endIndex);

  // Reset to first page when filter changes
  const handleFilterChange = (filter) => {
    setSelectedFilter(filter);
    setCurrentPage(1);
  };

  // Handle custom date range application
  const handleApplyDateRange = () => {
    if (startDate && endDate) {
      setCurrentPage(1);
      console.log('Applying date range:', startDate, 'to', endDate);
      // The filtering will happen automatically through getFilteredPayments
    }
  };

  return (
    <div>
      {/* Date Filter Buttons */}
      <div className="date-filter-row">
        {dateFilters.map(filter => (
          <button
            key={filter}
            className={`date-filter-btn ${selectedFilter === filter ? 'active' : ''}`}
            onClick={() => handleFilterChange(filter)}
          >
            {filter}
          </button>
        ))}
      </div>

      {/* Custom Date Range Fields - Second Row */}
      {selectedFilter === 'Custom' && (
        <div className="custom-date-range">
          <div className="date-input-group">
            <label htmlFor="start-date">From Date</label>
            <input
              id="start-date"
              type="date"
              value={startDate}
              onChange={(e) => setStartDate(e.target.value)}
              className="date-input"
              placeholder="dd-mm-yyyy"
            />
          </div>
          <div className="date-input-group">
            <label htmlFor="end-date">To Date</label>
            <input
              id="end-date"
              type="date"
              value={endDate}
              onChange={(e) => setEndDate(e.target.value)}
              className="date-input"
              placeholder="dd-mm-yyyy"
              min={startDate}
            />
          </div>
          <button
            className="apply-date-btn"
            onClick={handleApplyDateRange}
            disabled={!startDate || !endDate}
          >
            Apply
          </button>
        </div>
      )}

      <div className="kpi-row">
        <div className="kpi"><div className="kpi-value">{toNumber(filteredPayments.length)}</div><div className="kpi-label">Filtered Results</div></div>
        <div className="kpi"><div className="kpi-value">{toCurrency(filteredTotals.success_amount)}</div><div className="kpi-label">Success ({filteredTotals.success_count})</div></div>
        <div className="kpi"><div className="kpi-value">{toCurrency(filteredTotals.pending_amount)}</div><div className="kpi-label">Pending ({filteredTotals.pending_count})</div></div>
        <div className="kpi"><div className="kpi-value">{toCurrency(filteredTotals.failed_amount)}</div><div className="kpi-label">Failed ({filteredTotals.failed_count})</div></div>
      </div>
      <div className="scroll-x" style={{ marginTop: 12 }}>
        <table className="data-table">
          <thead>
            <tr>
              <th>Order ID</th>
              <th>Status</th>
              <th>Method</th>
              <th>Amount</th>
              <th>Created</th>
              <th>Actions</th>
            </tr>
          </thead>
          <tbody>
            {currentPayments.map(r => (
              <tr key={r.id}>
                <td><span className="link-text">#{r.order_id}</span></td>
                <td><span className={`badge ${r.status === 'success' ? 'success' : r.status === 'pending' ? 'warning' : 'danger'}`}>{r.status}</span></td>
                <td>{r.method}</td>
                <td>{toCurrency(r.amount)}</td>
                <td>{formatDate(r.created_at)}</td>
                <td>
                  <button
                    className="btn-view-details-row"
                    onClick={() => onViewDetails(r)}
                    title="View payment details"
                  >
                    View
                  </button>
                </td>
              </tr>
            ))}
            {!recent.length && (
              <tr>
                <td colSpan="6" className="muted">No payments</td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
      {totalPages > 1 && (
        <>
          <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', gap: '8px', marginTop: '20px' }}>
            <button
              onClick={() => setCurrentPage(prev => Math.max(1, prev - 1))}
              disabled={currentPage === 1}
              style={{
                width: '40px',
                height: '40px',
                borderRadius: '12px',
                border: '1px solid #e5e7eb',
                background: 'white',
                color: '#6b7280',
                cursor: currentPage === 1 ? 'not-allowed' : 'pointer',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                fontSize: '1.2rem',
                opacity: currentPage === 1 ? 0.5 : 1,
                transition: 'all 0.2s'
              }}
            >
              ‹
            </button>
            
            {/* First 3 pages */}
            {[1, 2, 3].map(pageNum => {
              if (pageNum > totalPages) return null;
              return (
                <button
                  key={pageNum}
                  onClick={() => setCurrentPage(pageNum)}
                  style={{
                    width: '40px',
                    height: '40px',
                    borderRadius: '12px',
                    border: currentPage === pageNum ? 'none' : '1px solid #e5e7eb',
                    background: currentPage === pageNum ? '#3b82f6' : 'white',
                    color: currentPage === pageNum ? 'white' : '#6b7280',
                    cursor: 'pointer',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    fontSize: '0.95rem',
                    fontWeight: currentPage === pageNum ? '600' : '400',
                    transition: 'all 0.2s'
                  }}
                >
                  {pageNum}
                </button>
              );
            })}
            
            {/* Ellipsis if there are more pages */}
            {totalPages > 4 && (
              <span style={{ color: '#6b7280', fontSize: '1.2rem', padding: '0 4px' }}>...</span>
            )}
            
            {/* Last page */}
            {totalPages > 3 && (
              <button
                onClick={() => setCurrentPage(totalPages)}
                style={{
                  width: '40px',
                  height: '40px',
                  borderRadius: '12px',
                  border: currentPage === totalPages ? 'none' : '1px solid #e5e7eb',
                  background: currentPage === totalPages ? '#3b82f6' : 'white',
                  color: currentPage === totalPages ? 'white' : '#6b7280',
                  cursor: 'pointer',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  fontSize: '0.95rem',
                  fontWeight: currentPage === totalPages ? '600' : '400',
                  transition: 'all 0.2s'
                }}
              >
                {totalPages}
              </button>
            )}
            
            <button
              onClick={() => setCurrentPage(prev => Math.min(totalPages, prev + 1))}
              disabled={currentPage === totalPages}
              style={{
                width: '40px',
                height: '40px',
                borderRadius: '12px',
                border: '1px solid #e5e7eb',
                background: 'white',
                color: '#6b7280',
                cursor: currentPage === totalPages ? 'not-allowed' : 'pointer',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                fontSize: '1.2rem',
                opacity: currentPage === totalPages ? 0.5 : 1,
                transition: 'all 0.2s'
              }}
            >
              ›
            </button>
          </div>
        </>
      )}
      
      {/* Results text and items per page selector - Always visible */}
      <div style={{ display: 'flex', justifyContent: 'flex-start', alignItems: 'center', gap: '16px', marginTop: '16px' }}>
        <select
          value={itemsPerPage}
          onChange={(e) => {
            setItemsPerPage(parseInt(e.target.value));
            setCurrentPage(1);
          }}
          style={{
            padding: '8px 32px 8px 16px',
            borderRadius: '8px',
            border: '1px solid #e5e7eb',
            background: '#f3f4f6',
            fontSize: '0.9rem',
            color: '#374151',
            fontWeight: '500',
            cursor: 'pointer',
            appearance: 'none',
            backgroundImage: 'url("data:image/svg+xml,%3Csvg xmlns=\'http://www.w3.org/2000/svg\' width=\'12\' height=\'12\' viewBox=\'0 0 12 12\'%3E%3Cpath fill=\'%23374151\' d=\'M6 9L1 4h10z\'/%3E%3C/svg%3E")',
            backgroundRepeat: 'no-repeat',
            backgroundPosition: 'right 12px center'
          }}
        >
          <option value="20">20</option>
          <option value="50">50</option>
          <option value="100">100</option>
        </select>
        <div style={{ fontSize: '0.9rem', color: '#374151', fontWeight: '500' }}>
          Results: {startIndex + 1} - {Math.min(endIndex, filteredPayments.length)} of {filteredPayments.length}
        </div>
      </div>
    </div>
  );
}

function OpsSettingsSection({ data }) {
  const settings = [
    {
      label: 'Delivery Charges',
      value: data?.delivery_charges ? 'Configured' : 'Not Set',
      status: data?.delivery_charges ? 'success' : 'neutral',
      icon: <FaTruck />
    },
    {
      label: 'Points Configuration',
      value: data?.points_configuration ? 'Configured' : 'Not Set',
      status: data?.points_configuration ? 'success' : 'neutral',
      icon: <FaStar />
    },
    {
      label: 'Order Types',
      value: Array.isArray(data?.order_types) ? data.order_types.join(', ') : 'Not Set',
      status: Array.isArray(data?.order_types) && data.order_types.length > 0 ? 'success' : 'neutral',
      icon: <FaClipboardList />
    }
  ];

  return (
    <div className="enhanced-section-content">
      <div className="settings-grid">
        {settings.map((setting, idx) => (
          <div key={idx} className="setting-card">
            <div className="setting-icon">{setting.icon}</div>
            <div className="setting-content">
              <div className="setting-label">{setting.label}</div>
              <div className="setting-value">{setting.value}</div>
            </div>
            <span className={`badge ${setting.status}`}>
              {setting.status === 'success' ? <FaCheckCircle /> : <FaCircle />}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}

function BranchesSection({ data, businessType }) {
  return (
    <div className="enhanced-section-content">
      {data?.length ? (
        <div className="branches-grid">
          {data.map((b, idx) => (
            <div key={b.business_id || idx} className="branch-card">
              <div className="branch-content">
                <div className="branch-name">{b.businessName || b.business_name || b.outlet_name}</div>
                <div className="branch-code">{b.city}, {b.state}</div>
              </div>
              <div className="branch-status">
                <span className={`badge ${b.status ? 'success' : 'neutral'}`}>
                  {b.status ? 'Active' : 'Inactive'}
                </span>
              </div>
            </div>
          ))}
        </div>
      ) : (
        <div className="empty-state">
          <div className="empty-state-icon">
            <FaStore />
          </div>
          <div className="empty-state-text">No branches configured</div>
        </div>
      )}
    </div>
  );
}

function PaymentDetailsModal({ payment, orderData }) {
  if (!payment) return null;



  const orders = orderData || [];
  const relatedOrder = orders.find(order => order.order_id === payment.order_id);

  return (
    <div className="modal-overview-content">
      {/* Payment Information */}
      <div className="modal-section">
        <h4>PAYMENT INFORMATION</h4>
        <div className="modal-info-grid">
          <div className="modal-info-row">
            <span className="modal-label">Payment ID</span>
            <span className="modal-value">#{payment.id}</span>
          </div>
          <div className="modal-info-row">
            <span className="modal-label">Order ID</span>
            <span className="modal-value">#{payment.order_id}</span>
          </div>
          <div className="modal-info-row">
            <span className="modal-label">Payment Status</span>
            <span className="modal-value">
              <span className={`badge ${payment.status === 'success' ? 'success' : payment.status === 'pending' ? 'warning' : 'danger'}`}>
                {payment.status}
              </span>
            </span>
          </div>
          <div className="modal-info-row">
            <span className="modal-label">Payment Method</span>
            <span className="modal-value">{payment.method}</span>
          </div>
          <div className="modal-info-row">
            <span className="modal-label">Amount</span>
            <span className="modal-value">{toCurrency(payment.amount)}</span>
          </div>
          <div className="modal-info-row">
            <span className="modal-label">User ID</span>
            <span className="modal-value">{payment.user_id || '-'}</span>
          </div>
          <div className="modal-info-row">
            <span className="modal-label">Email</span>
            <span className="modal-value">{relatedOrder?.email || relatedOrder?.customer_email || 'Not available in current data'}</span>
          </div>
          <div className="modal-info-row">
            <span className="modal-label">Mobile Number</span>
            <span className="modal-value">{relatedOrder?.phone || relatedOrder?.mobile || relatedOrder?.customer_phone || 'Not available in current data'}</span>
          </div>
          <div className="modal-info-row">
            <span className="modal-label">Transaction ID</span>
            <span className="modal-value">{payment.transaction_id || payment.txn_id || payment.razorpay_payment_id || payment.payment_id || '-'}</span>
          </div>
          <div className="modal-info-row">
            <span className="modal-label">Created At</span>
            <span className="modal-value">{formatDate(payment.created_at)}</span>
          </div>
        </div>
      </div>

      {/* Related Order Information */}
      {relatedOrder && (
        <div className="modal-section">
          <h4>RELATED ORDER INFORMATION</h4>
          <div className="modal-info-grid">
            <div className="modal-info-row">
              <span className="modal-label">Order Status</span>
              <span className="modal-value">
                <span className={`badge ${relatedOrder.status === 'success' || relatedOrder.status === 'completed' ? 'success' : relatedOrder.status === 'pending' || relatedOrder.status === 'processing' ? 'warning' : 'danger'}`}>
                  {relatedOrder.status || relatedOrder.order_status || 'N/A'}
                </span>
              </span>
            </div>
            <div className="modal-info-row">
              <span className="modal-label">Order Amount</span>
              <span className="modal-value">{toCurrency(relatedOrder.amount)}</span>
            </div>
            <div className="modal-info-row">
              <span className="modal-label">Customer ID</span>
              <span className="modal-value">{relatedOrder.user_id || relatedOrder.customer_id || '-'}</span>
            </div>
            <div className="modal-info-row">
              <span className="modal-label">Items Count</span>
              <span className="modal-value">{relatedOrder.items_count || relatedOrder.item_count || '-'}</span>
            </div>
            <div className="modal-info-row">
              <span className="modal-label">Delivery Address</span>
              <span className="modal-value">{relatedOrder.delivery_address || relatedOrder.address || '-'}</span>
            </div>
            <div className="modal-info-row">
              <span className="modal-label">Order Created</span>
              <span className="modal-value">{formatDate(relatedOrder.created_at)}</span>
            </div>
          </div>
        </div>
      )}

      {/* Share Modal - Debug Version */}
      {showShareModal ? (
        <div 
          style={{ 
            position: 'fixed',
            top: 0,
            left: 0,
            right: 0,
            bottom: 0,
            background: 'rgba(0, 0, 0, 0.8)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            zIndex: 9999
          }}
          onClick={() => {
            console.log('Overlay clicked');
            setShowShareModal(false);
          }}
        >
          <div 
            style={{ 
              background: 'white',
              padding: '40px',
              borderRadius: '12px',
              maxWidth: '600px',
              width: '90%',
              maxHeight: '90vh',
              overflow: 'auto'
            }}
            onClick={(e) => {
              console.log('Modal content clicked');
              e.stopPropagation();
            }}
          >
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '20px' }}>
              <h3 style={{ margin: 0 }}>Share Business Details</h3>
              <button 
                onClick={() => {
                  console.log('Close button clicked');
                  setShowShareModal(false);
                }}
                style={{
                  background: 'none',
                  border: 'none',
                  fontSize: '28px',
                  cursor: 'pointer',
                  padding: '0',
                  width: '32px',
                  height: '32px'
                }}
              >
                ×
              </button>
            </div>
            <p style={{ marginBottom: '20px', color: '#666' }}>
              Share this business details page via your preferred platform
            </p>

            {/* Simplified Share Buttons */}
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(140px, 1fr))', gap: '12px' }}>
              
              {/* WhatsApp */}
              <button onClick={handleShareWhatsApp} style={{ padding: '16px', background: '#25D366', color: 'white', border: 'none', borderRadius: '8px', cursor: 'pointer', fontSize: '14px', fontWeight: '600' }}>
                💬 WhatsApp
              </button>

              {/* Email */}
              <button onClick={handleShareEmail} style={{ padding: '16px', background: '#EA4335', color: 'white', border: 'none', borderRadius: '8px', cursor: 'pointer', fontSize: '14px', fontWeight: '600' }}>
                ✉️ Email
              </button>

              {/* Telegram */}
              <button onClick={handleShareTelegram} style={{ padding: '16px', background: '#0088cc', color: 'white', border: 'none', borderRadius: '8px', cursor: 'pointer', fontSize: '14px', fontWeight: '600' }}>
                ✈️ Telegram
              </button>

              {/* LinkedIn */}
              <button onClick={handleShareLinkedIn} style={{ padding: '16px', background: '#0077B5', color: 'white', border: 'none', borderRadius: '8px', cursor: 'pointer', fontSize: '14px', fontWeight: '600' }}>
                💼 LinkedIn
              </button>

              {/* Twitter */}
              <button onClick={handleShareTwitter} style={{ padding: '16px', background: '#000000', color: 'white', border: 'none', borderRadius: '8px', cursor: 'pointer', fontSize: '14px', fontWeight: '600' }}>
                𝕏 Twitter
              </button>

              {/* Facebook */}
              <button onClick={handleShareFacebook} style={{ padding: '16px', background: '#1877F2', color: 'white', border: 'none', borderRadius: '8px', cursor: 'pointer', fontSize: '14px', fontWeight: '600' }}>
                📘 Facebook
              </button>

              {/* SMS */}
              <button onClick={handleShareSMS} style={{ padding: '16px', background: '#34C759', color: 'white', border: 'none', borderRadius: '8px', cursor: 'pointer', fontSize: '14px', fontWeight: '600' }}>
                💬 SMS
              </button>

              {/* Copy Link */}
              <button onClick={handleCopyLink} style={{ padding: '16px', background: '#6B7280', color: 'white', border: 'none', borderRadius: '8px', cursor: 'pointer', fontSize: '14px', fontWeight: '600' }}>
                <FaCopy /> Copy Link
              </button>
            </div>

            {/* Link Preview */}
            <div style={{ marginTop: '20px', padding: '12px', background: '#f3f4f6', borderRadius: '6px', fontSize: '13px', wordBreak: 'break-all' }}>
              <strong>Link:</strong><br />
              {`${window.location.origin}${window.location.pathname}#business-details/${businessId}`}
            </div>
          </div>
        </div>
      ) : null}

      {/* Settings Modal */}
      {showSettingsModal && (
        <div className="modal-overlay" onClick={() => setShowSettingsModal(false)}>
          <div className="modal-content" onClick={(e) => e.stopPropagation()} style={{ maxWidth: '600px' }}>
            <div className="modal-header">
              <h3>Business Settings</h3>
              <button className="modal-close" onClick={() => setShowSettingsModal(false)}>×</button>
            </div>
            <div className="modal-body">
              <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
                <div className="setting-group">
                  <h4 style={{ marginBottom: '12px', fontSize: '16px', fontWeight: '600' }}>Display Settings</h4>
                  <label style={{ display: 'flex', alignItems: 'center', gap: '8px', cursor: 'pointer' }}>
                    <input type="checkbox" defaultChecked />
                    <span>Show detailed analytics</span>
                  </label>
                  <label style={{ display: 'flex', alignItems: 'center', gap: '8px', cursor: 'pointer' }}>
                    <input type="checkbox" defaultChecked />
                    <span>Show payment details</span>
                  </label>
                  <label style={{ display: 'flex', alignItems: 'center', gap: '8px', cursor: 'pointer' }}>
                    <input type="checkbox" defaultChecked />
                    <span>Show menu items</span>
                  </label>
                </div>

                <div className="setting-group">
                  <h4 style={{ marginBottom: '12px', fontSize: '16px', fontWeight: '600' }}>Data Refresh</h4>
                  <label style={{ display: 'flex', alignItems: 'center', gap: '8px', cursor: 'pointer' }}>
                    <input type="checkbox" defaultChecked />
                    <span>Auto-refresh data every 5 minutes</span>
                  </label>
                </div>

                <div className="setting-group">
                  <h4 style={{ marginBottom: '12px', fontSize: '16px', fontWeight: '600' }}>Export Settings</h4>
                  <label style={{ display: 'block', marginBottom: '8px' }}>
                    <span style={{ display: 'block', marginBottom: '4px', fontSize: '14px', fontWeight: '500' }}>Default Export Format</span>
                    <select style={{ width: '100%', padding: '8px', borderRadius: '4px', border: '1px solid #d1d5db' }}>
                      <option value="csv">CSV (Excel)</option>
                      <option value="json">JSON</option>
                      <option value="excel">Excel (XLSX)</option>
                    </select>
                  </label>
                </div>

                <div style={{ display: 'flex', gap: '12px', marginTop: '20px' }}>
                  <button 
                    className="btn-primary" 
                    onClick={() => {
                      setSaveMessage('✓ Settings saved!');
                      setTimeout(() => setSaveMessage(''), 3000);
                      setShowSettingsModal(false);
                    }}
                    style={{ flex: 1, padding: '10px' }}
                  >
                    Save Settings
                  </button>
                  <button 
                    className="btn-secondary" 
                    onClick={() => setShowSettingsModal(false)}
                    style={{ flex: 1, padding: '10px' }}
                  >
                    Cancel
                  </button>
                </div>
              </div>
            </div>
          </div>
        </div>
      )}

    </div>
  );
}
