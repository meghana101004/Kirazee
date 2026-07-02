import React from 'react';
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Cell } from 'recharts';

const TopBusinessesRevenueChart = ({ data }) => {
  console.log('TopBusinessesRevenueChart data:', data);
  
  // Handle different data structures and field names
  const processedData = data || [];
  console.log('Number of businesses processed:', processedData.length);
  
  // Filter out businesses with zero revenue and take top 5
  const topBusinesses = processedData
    .filter(business => {
      const revenue = business.raw_revenue || business.revenue || business.total_revenue || 0;
      console.log(`Business ${business.business_name}: revenue = ${revenue}`);
      return revenue > 0;
    })
    .slice(0, 5)
    .map((business, index) => {
      const businessName = business.business_name || business.name || 'Unknown Business';
      const revenue = business.raw_revenue || business.revenue || business.total_revenue || 0;
      return {
        rank: index + 1,
        name: businessName.length > 8 ? businessName.substring(0, 8) + '...' : businessName,
        fullName: businessName,
        revenue: revenue,
        formattedRevenue: `₹${revenue.toLocaleString()}`
      };
    });

  console.log('Processed topBusinesses:', topBusinesses);

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
        }}>Top 5 Businesses by Revenue</h3>
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
            }}>📊</div>
            <p style={{ 
              fontSize: window.innerWidth <= 480 ? '10px' : '12px', 
              margin: '0' 
            }}>No revenue data available</p>
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
      }}>Top 5 Businesses by Revenue</h3>
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
          <LineChart data={topBusinesses} margin={{ 
            top: window.innerWidth <= 480 ? 5 : 10, 
            right: window.innerWidth <= 480 ? 10 : 30, 
            left: 0, 
            bottom: 0 
          }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />
            <XAxis 
              dataKey="rank" 
              ticks={[1, 2, 3, 4, 5]}
              tick={{ fontSize: window.innerWidth <= 480 ? '9px' : '11px' }} 
              stroke="#6b7280"
              label={{ 
                value: 'Rank', 
                position: 'insideBottom', 
                offset: -5, 
                fontSize: window.innerWidth <= 480 ? '9px' : '11px', 
                fill: '#6b7280' 
              }}
            />
            <YAxis 
              tick={{ fontSize: window.innerWidth <= 480 ? '9px' : '11px' }} 
              stroke="#6b7280"
              label={{ 
                value: 'Revenue (₹)', 
                angle: -90, 
                position: 'insideLeft', 
                fontSize: window.innerWidth <= 480 ? '9px' : '11px', 
                fill: '#6b7280' 
              }}
              tickFormatter={(value) => `${(value / 1000).toFixed(0)}k`}
            />
            <Tooltip 
              formatter={(value, name) => {
                if (name === 'revenue') return [`₹${value.toLocaleString()}`, 'Revenue'];
                return [value, name];
              }}
              labelFormatter={(label, payload) => {
                if (payload && payload[0]) {
                  return `Rank ${label}: ${payload[0].payload.fullName}`;
                }
                return `Rank ${label}`;
              }}
              contentStyle={{ 
                backgroundColor: 'rgba(255, 255, 255, 0.95)', 
                border: '1px solid #e5e7eb', 
                borderRadius: '6px', 
                fontSize: window.innerWidth <= 480 ? '10px' : '12px' 
              }}
            />
            <Line 
              type="monotone" 
              dataKey="revenue" 
              stroke="#2563eb" 
              strokeWidth={window.innerWidth <= 480 ? 1.5 : 2}
              dot={{ 
                fill: '#2563eb', 
                strokeWidth: 2, 
                r: window.innerWidth <= 480 ? 3 : 4 
              }}
              activeDot={{ r: window.innerWidth <= 480 ? 4 : 6 }}
            />
          </LineChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
};

export default TopBusinessesRevenueChart;
