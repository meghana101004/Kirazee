import React from 'react';
import { PieChart, Pie, Cell, ResponsiveContainer, Tooltip } from 'recharts';

const CustomerMetricsChart = ({ data }) => {
  const chartData = [
    { name: 'Active Users', value: data.active_users, color: '#10b981' },
    { name: 'Inactive Users', value: data.total_users - data.active_users, color: '#6b7280' }
  ];

  const uniqueCustomersPercentage = ((data.unique_customers / data.total_users) * 100).toFixed(1);

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
      }}>Customer Analytics</h3>
      <div style={{ 
        width: '100%', 
        height: window.innerWidth <= 480 ? '140px' : '180px', 
        minHeight: window.innerWidth <= 480 ? '140px' : '180px', 
        position: 'relative' 
      }}>
        <ResponsiveContainer 
          width="100%" 
          height={window.innerWidth <= 480 ? 140 : 180} 
          minHeight={window.innerWidth <= 480 ? 140 : 180}
        >
          <PieChart>
            <Pie
              data={chartData}
              cx="50%"
              cy="50%"
              innerRadius={window.innerWidth <= 480 ? 30 : 40}
              outerRadius={window.innerWidth <= 480 ? 50 : 60}
              fill="transparent"
              paddingAngle={2}
              dataKey="value"
            >
              {chartData.map((entry, index) => (
                <Cell 
                  key={`cell-${index}`} 
                  fill={entry.color} 
                  fillOpacity={0.8} 
                  stroke={entry.color} 
                  strokeWidth={1} 
                />
              ))}
            </Pie>
            <Tooltip 
              formatter={(value) => [value, 'Users']} 
              contentStyle={{ 
                backgroundColor: 'rgba(255, 255, 255, 0.95)', 
                border: '1px solid #e5e7eb', 
                borderRadius: '6px', 
                fontSize: window.innerWidth <= 480 ? '10px' : '12px' 
              }}
            />
          </PieChart>
        </ResponsiveContainer>
      </div>
      <div style={{ 
        textAlign: 'center', 
        marginTop: window.innerWidth <= 480 ? '4px' : '8px', 
        fontSize: window.innerWidth <= 480 ? '9px' : '11px' 
      }}>
        <div style={{ marginBottom: '4px' }}>
          <span style={{ color: '#10b981', fontWeight: '600' }}>
            Active: {data.active_users}
          </span>
          <span style={{ margin: '0 8px' }}>|</span>
          <span style={{ color: '#6b7280', fontWeight: '600' }}>
            Inactive: {data.total_users - data.active_users}
          </span>
        </div>
        <div style={{ color: '#374151', fontSize: window.innerWidth <= 480 ? '8px' : '10px' }}>
          Total Users: {data.total_users}
        </div>
      </div>
    </div>
  );
};

export default CustomerMetricsChart;
