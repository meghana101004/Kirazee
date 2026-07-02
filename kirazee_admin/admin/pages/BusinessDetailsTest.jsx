import React, { useState } from 'react';

const BusinessDetailsTest = ({ businessId }) => {
  const [activeTab, setActiveTab] = useState('overview');

  return (
    <div className="biz-details">
      <header className="biz-header">
        <h1>Test Business - {businessId}</h1>
      </header>

      <div style={{
        display: 'flex',
        justifyContent: 'space-between',
        alignItems: 'center',
        padding: '16px 24px',
        borderBottom: '1px solid #e5e7eb',
        backgroundColor: '#f9fafb'
      }}>
        <div style={{
          display: 'flex',
          gap: '4px',
          backgroundColor: 'white',
          padding: '4px',
          borderRadius: '8px',
          border: '1px solid #e5e7eb'
        }}>
          {[
            { id: 'overview', label: '📊 Overview', color: '#3b82f6' },
            { id: 'consumption', label: '📊 Consumption', color: '#10b981' },
            { id: 'consumer', label: '👥 Consumer', color: '#f59e0b' },
            { id: 'sales', label: '💰 Sales', color: '#ef4444' },
            { id: 'menu', label: '🍽️ Menu', color: '#8b5cf6' },
            { id: 'performance', label: '📈 Performance', color: '#06b6d4' },
            { id: 'inventory', label: '📦 Inventory', color: '#84cc16' }
          ].map((tab) => (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id)}
              style={{
                padding: '8px 16px',
                border: 'none',
                borderRadius: '6px',
                backgroundColor: activeTab === tab.id ? tab.color : 'transparent',
                color: activeTab === tab.id ? 'white' : '#6b7280',
                fontWeight: activeTab === tab.id ? '600' : '400',
                fontSize: '14px',
                cursor: 'pointer',
                transition: 'all 0.2s ease'
              }}
            >
              {tab.label}
            </button>
          ))}
        </div>

        <div style={{
          display: 'flex',
          alignItems: 'center',
          gap: '12px'
        }}>
          <span style={{
            fontSize: '14px',
            fontWeight: '500',
            color: '#374151'
          }}>
            📅 Filters:
          </span>
          <select style={{
            padding: '6px 12px',
            border: '1px solid #d1d5db',
            borderRadius: '6px',
            fontSize: '14px',
            backgroundColor: 'white'
          }}>
            <option value="today">Today</option>
            <option value="last7days">Last 7 Days</option>
            <option value="last30days">Last 30 Days</option>
            <option value="last90days">Last 90 Days</option>
            <option value="custom">Custom Range</option>
          </select>
        </div>
      </div>

      <div style={{ padding: '24px' }}>
        {activeTab === 'overview' && (
          <div>
            <h3>Business Overview</h3>
            <p>This is the overview tab content for business: {businessId}</p>
          </div>
        )}
        
        {activeTab === 'consumption' && (
          <div>
            <h3>📊 Consumption Report</h3>
            <p>Analyze consumption patterns and trends</p>
          </div>
        )}
        
        {activeTab === 'consumer' && (
          <div>
            <h3>👥 Consumer Report</h3>
            <p>Customer demographics and behavior analysis</p>
          </div>
        )}
        
        {activeTab === 'sales' && (
          <div>
            <h3>💰 Sales Report</h3>
            <p>Sales performance and revenue analysis</p>
          </div>
        )}
        
        {activeTab === 'menu' && (
          <div>
            <h3>🍽️ Menu Report</h3>
            <p>Menu performance and item analysis</p>
          </div>
        )}
        
        {activeTab === 'performance' && (
          <div>
            <h3>📈 Performance Report</h3>
            <p>Business KPIs and efficiency metrics</p>
          </div>
        )}
        
        {activeTab === 'inventory' && (
          <div>
            <h3>📦 Inventory Report</h3>
            <p>Stock levels and inventory management</p>
          </div>
        )}
      </div>
    </div>
  );
};

export default BusinessDetailsTest;
