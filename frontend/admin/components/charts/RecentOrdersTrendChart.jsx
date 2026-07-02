import React from 'react';
import { ComposedChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Cell, Rectangle } from 'recharts';

// Custom candlestick component
const Candlestick = (props) => {
  const { x, y, width, height, open, close, high, low, payload } = props;
  
  const isPositive = close >= open;
  const color = isPositive ? '#10b981' : '#ef4444';
  const bodyHeight = Math.abs(close - open) || 1;
  const bodyY = y + Math.min(open, close) - low;
  
  // Calculate positions relative to the candlestick space
  const totalRange = high - low || 1;
  const highY = y;
  const lowY = y + height;
  const openY = y + ((high - open) / totalRange) * height;
  const closeY = y + ((high - close) / totalRange) * height;
  
  return (
    <g>
      {/* High-Low Line */}
      <line
        x1={x + width / 2}
        y1={highY}
        x2={x + width / 2}
        y2={lowY}
        stroke={color}
        strokeWidth={1}
      />
      {/* Body */}
      <rect
        x={x + width * 0.2}
        y={Math.min(openY, closeY)}
        width={width * 0.6}
        height={Math.abs(closeY - openY) || 1}
        fill={isPositive ? color : 'transparent'}
        stroke={color}
        strokeWidth={1}
      />
    </g>
  );
};

const RecentOrdersTrendChart = ({ data }) => {
  // Group orders by date and calculate daily totals for candlestick data
  const dailyData = data.reduce((acc, order) => {
    const date = new Date(order.created_at).toLocaleDateString('en-IN', { 
      month: 'short', 
      day: 'numeric' 
    });
    
    if (!acc[date]) {
      acc[date] = { 
        date, 
        orders: 0, 
        revenue: 0, 
        minRevenue: Infinity,
        maxRevenue: 0,
        delivered: 0, 
        completed: 0, 
        cancelled: 0,
        orderAmounts: []
      };
    }
    
    acc[date].orders += 1;
    acc[date].revenue += order.final_amount;
    acc[date].orderAmounts.push(order.final_amount);
    acc[date].minRevenue = Math.min(acc[date].minRevenue, order.final_amount);
    acc[date].maxRevenue = Math.max(acc[date].maxRevenue, order.final_amount);
    
    if (order.status === 'delivered') acc[date].delivered += 1;
    else if (order.status === 'completed') acc[date].completed += 1;
    else if (order.status === 'cancelled') acc[date].cancelled += 1;
    
    return acc;
  }, {});

  // Convert to candlestick format
  const chartData = Object.values(dailyData).slice(-7).map(day => ({
    date: day.date,
    orders: day.orders,
    revenue: day.revenue,
    // Candlestick data for revenue
    open: day.orderAmounts.length > 0 ? Math.min(...day.orderAmounts.slice(0, Math.ceil(day.orderAmounts.length / 2))) : 0,
    high: day.maxRevenue,
    low: day.minRevenue === Infinity ? 0 : day.minRevenue,
    close: day.orderAmounts.length > 0 ? Math.max(...day.orderAmounts.slice(Math.floor(day.orderAmounts.length / 2))) : 0,
    // Additional metrics
    delivered: day.delivered,
    completed: day.completed,
    cancelled: day.cancelled,
    avgOrderValue: day.orders > 0 ? day.revenue / day.orders : 0
  }));

  return (
    <div className="chart-widget" style={{ background: 'white', padding: '16px', borderRadius: '8px', height: '280px', width: '100%', minHeight: '280px' }}>
      <h3 style={{ fontSize: '14px', fontWeight: '600', marginBottom: '12px', color: '#374151' }}>Recent Orders Trend (Last 7 Days)</h3>
      <ResponsiveContainer width="100%" height={200} minWidth={250}>
        <ComposedChart data={chartData} margin={{ top: 10, right: 30, left: 0, bottom: 0 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />
          <XAxis 
            dataKey="date" 
            tick={{ fontSize: '11px' }} 
            stroke="#6b7280"
            interval={0}
          />
          <YAxis 
            yAxisId="revenue" 
            orientation="right"
            tick={{ fontSize: '11px' }} 
            stroke="#6b7280"
            tickFormatter={(value) => `₹${(value / 1000).toFixed(0)}k`}
            label={{ value: 'Revenue (₹)', angle: -90, position: 'insideRight', fontSize: '11px', fill: '#6b7280' }}
          />
          <YAxis 
            yAxisId="orders" 
            tick={{ fontSize: '11px' }} 
            stroke="#6b7280"
            label={{ value: 'Orders', angle: -90, position: 'insideLeft', fontSize: '11px', fill: '#6b7280' }}
          />
          <Tooltip 
            contentStyle={{ backgroundColor: 'rgba(255, 255, 255, 0.95)', border: '1px solid #e5e7eb', borderRadius: '6px', fontSize: '12px' }}
            formatter={(value, name) => {
              if (name === 'orders') return [value, 'Orders'];
              if (name === 'revenue') return [`₹${value.toLocaleString()}`, 'Total Revenue'];
              if (name === 'avgOrderValue') return [`₹${value.toFixed(0)}`, 'Avg Order Value'];
              return [value, name];
            }}
            labelFormatter={(label) => `Date: ${label}`}
          />
          
          {/* Candlestick bars for revenue range */}
          <Bar 
            yAxisId="revenue" 
            dataKey="high" 
            shape={<Candlestick />}
            fill="transparent"
          />
          
          {/* Order count bars */}
          <Bar 
            yAxisId="orders" 
            dataKey="orders" 
            fill="#2563eb" 
            fillOpacity={0.3}
            radius={[4, 4, 0, 0]}
          />
        </ComposedChart>
      </ResponsiveContainer>
    </div>
  );
};

export default RecentOrdersTrendChart;
