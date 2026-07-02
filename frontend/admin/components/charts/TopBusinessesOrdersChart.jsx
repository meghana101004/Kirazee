import React from 'react';
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Cell } from 'recharts';

const TopBusinessesOrdersChart = ({ data }) => {
  console.log('TopBusinessesOrdersChart received data:', data);
  
  // Ensure data is an array
  const processedData = Array.isArray(data) ? data : [];
  console.log('Processed data length:', processedData.length);
  
  // Filter out businesses with zero orders and take top 5
  const topBusinesses = processedData
    .filter(business => business.total_orders > 0)
    .slice(0, 5)
    .map(business => ({
      name: business.business_name.length > 15 ? business.business_name.substring(0, 15) + '...' : business.business_name,
      orders: business.total_orders
    }));

  console.log('Top businesses after filtering:', topBusinesses);

  // Professional color palette
  const colors = ['#2563eb', '#10b981', '#f59e0b', '#ef4444', '#8b5cf6'];

  // Handle empty data case
  if (!topBusinesses || topBusinesses.length === 0) {
    return (
      <div className="chart-widget" style={{ 
        background: 'white', 
        padding: window.innerWidth <= 480 ? '8px' : '16px', 
        borderRadius: window.innerWidth <= 480 ? '6px' : '8px', 
        height: window.innerWidth <= 480 ? 'auto' : '280px', 
        width: '100%', 
        minHeight: window.innerWidth <= 480 ? '200px' : '280px',
        overflow: 'hidden'
      }}>
        <h3 style={{ 
          fontSize: window.innerWidth <= 480 ? '11px' : '14px', 
          fontWeight: '600', 
          marginBottom: window.innerWidth <= 480 ? '6px' : '12px', 
          color: '#374151',
          lineHeight: 1.1
        }}>Top 5 Businesses by Orders</h3>
        <div style={{ 
          display: 'flex', 
          alignItems: 'center', 
          justifyContent: 'center', 
          height: window.innerWidth <= 480 ? '160px' : '220px', 
          color: '#6b7280' 
        }}>
          <div style={{ textAlign: 'center' }}>
            <div style={{ 
              fontSize: window.innerWidth <= 480 ? '24px' : '32px', 
              marginBottom: '8px' 
            }}>📦</div>
            <p style={{ 
              fontSize: window.innerWidth <= 480 ? '10px' : '12px', 
              margin: '0' 
            }}>No order data available</p>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="chart-widget" style={{ 
      background: 'white', 
      padding: window.innerWidth <= 480 ? '8px' : '16px', 
      borderRadius: window.innerWidth <= 480 ? '6px' : '8px', 
      height: window.innerWidth <= 480 ? 'auto' : '280px', 
      width: '100%', 
      minHeight: window.innerWidth <= 480 ? '200px' : '280px',
      overflow: 'hidden'
    }}>
      <h3 style={{ 
        fontSize: window.innerWidth <= 480 ? '11px' : '14px', 
        fontWeight: '600', 
        marginBottom: window.innerWidth <= 480 ? '6px' : '12px', 
        color: '#374151',
        lineHeight: 1.1
      }}>Top 5 Businesses by Orders</h3>
      <div style={{ 
        width: '100%', 
        height: window.innerWidth <= 480 ? '160px' : '220px', 
        minHeight: window.innerWidth <= 480 ? '160px' : '220px', 
        position: 'relative' 
      }}>
        <ResponsiveContainer 
          width="100%" 
          height={window.innerWidth <= 480 ? 160 : 220} 
          minHeight={window.innerWidth <= 480 ? 160 : 220}
        >
          <BarChart data={topBusinesses} margin={{ 
            top: window.innerWidth <= 480 ? 5 : 10, 
            right: window.innerWidth <= 480 ? 10 : 30, 
            left: 0, 
            bottom: window.innerWidth <= 480 ? 40 : 0 
          }}>
            <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#e5e7eb" />
            <XAxis 
              dataKey="name" 
              angle={window.innerWidth <= 480 ? -45 : -45} 
              textAnchor="end" 
              height={window.innerWidth <= 480 ? 50 : 60} 
              tick={{ fontSize: window.innerWidth <= 480 ? '8px' : '11px' }} 
              stroke="#6b7280" 
            />
            <YAxis 
              tick={{ fontSize: window.innerWidth <= 480 ? '9px' : '11px' }} 
              stroke="#6b7280" 
            />
            <Tooltip 
              formatter={(value) => [value, 'Orders']}
              contentStyle={{ 
                backgroundColor: 'rgba(255, 255, 255, 0.95)', 
                border: '1px solid #e5e7eb', 
                borderRadius: '6px', 
                fontSize: window.innerWidth <= 480 ? '10px' : '12px' 
              }}
            />
            <Bar 
              dataKey="orders" 
              radius={[window.innerWidth <= 480 ? 2 : 4, window.innerWidth <= 480 ? 2 : 4, 0, 0]}
            >
              {topBusinesses.map((entry, index) => (
                <Cell 
                  key={`cell-${index}`} 
                  fill={colors[index % colors.length]} 
                />
              ))}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
};

export default TopBusinessesOrdersChart;
