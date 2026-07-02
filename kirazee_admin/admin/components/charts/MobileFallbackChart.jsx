import React from 'react';

const MobileFallbackChart = ({ title, children, data }) => {
  const hasData = data && (Array.isArray(data) ? data.length > 0 : Object.keys(data).length > 0);
  
  return (
    <div className="chart-widget" style={{ 
      background: 'white', 
      padding: window.innerWidth <= 480 ? '8px' : '16px', 
      borderRadius: window.innerWidth <= 480 ? '6px' : '8px', 
      height: window.innerWidth <= 480 ? '200px' : '280px', 
      width: '100%', 
      minHeight: window.innerWidth <= 480 ? '200px' : '280px',
      overflow: 'hidden',
      border: '1px solid #e5e7eb',
      display: 'flex',
      flexDirection: 'column'
    }}>
      <h3 style={{ 
        fontSize: window.innerWidth <= 480 ? '11px' : '14px', 
        fontWeight: '600', 
        marginBottom: window.innerWidth <= 480 ? '6px' : '12px', 
        color: '#374151',
        lineHeight: 1.1
      }}>{title}</h3>
      
      <div style={{ 
        flex: 1,
        display: 'flex', 
        alignItems: 'center', 
        justifyContent: 'center',
        minHeight: '150px'
      }}>
        {hasData ? (
          children
        ) : (
          <div style={{ textAlign: 'center', color: '#6b7280' }}>
            <div style={{ 
              fontSize: window.innerWidth <= 480 ? '24px' : '32px', 
              marginBottom: '8px' 
            }}>📊</div>
            <p style={{ 
              fontSize: window.innerWidth <= 480 ? '10px' : '12px', 
              margin: '0' 
            }}>
              {window.innerWidth <= 480 ? 'Loading...' : 'No data available'}
            </p>
          </div>
        )}
      </div>
    </div>
  );
};

export default MobileFallbackChart;
