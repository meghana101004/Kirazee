import React from 'react';
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from 'recharts';

const RevenueTrendChart = ({ data }) => {
  // If no data, show a message
  if (!data || data.length === 0) {
    return (
      <div className="chart-box" style={{ background: 'white', padding: '20px', borderRadius: '12px', height: '400px', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
        <div style={{ textAlign: 'center' }}>
          <h3>Revenue Trend</h3>
          <p style={{ color: '#64748b', marginTop: '16px' }}>No daily revenue data available</p>
          <p style={{ color: '#94a3b8', fontSize: '14px', marginTop: '8px' }}>Daily revenue tracking requires historical data</p>
        </div>
      </div>
    );
  }

  return (
    <div className="chart-box" style={{ background: 'white', padding: '20px', borderRadius: '12px', height: '400px' }}>
      <h3>Revenue Trend (30 Days)</h3>
      <ResponsiveContainer width="100%" height="320px">
        <LineChart data={data} margin={{ top: 20, right: 30, left: 20, bottom: 20 }}>
          <CartesianGrid strokeDasharray="3 3" vertical={false} />
          <XAxis 
            dataKey="date" 
            tickFormatter={(str) => new Date(str).getDate()} // Show only day number
          />
          <YAxis />
          <Tooltip 
            formatter={(value) => [`₹${value?.toLocaleString() || 0}`, 'Revenue']}
            labelFormatter={(label) => new Date(label).toLocaleDateString()}
          />
          <Line 
            type="monotone" 
            dataKey="revenue" 
            stroke="#F55D00" 
            strokeWidth={3} 
            dot={false}
            activeDot={{ r: 8 }} 
          />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
};

export default RevenueTrendChart;
