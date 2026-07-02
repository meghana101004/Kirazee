import React from 'react';
import { PieChart, Pie, Cell, ResponsiveContainer } from 'recharts';

const OrdersBreakdownChart = ({ data }) => {
  const chartData = [
    { name: 'Completed', value: data.completed_orders || 0, color: '#28a745' },
    { name: 'Active', value: data.active_orders || 0, color: '#007bff' },
    { name: 'Pending', value: data.pending_orders || 0, color: '#ffc107' },
    { name: 'Cancelled', value: data.cancelled_orders || 0, color: '#dc3545' }
  ];

  const total = chartData.reduce((sum, item) => sum + item.value, 0);

  // Calculate percentages that sum to 100%
  const calculatePercentages = (data, total) => {
    if (total === 0) return data.map(item => ({ ...item, percentage: 0 }));
    
    // Calculate raw percentages
    const rawPercentages = data.map(item => ({
      ...item,
      rawPercentage: (item.value / total) * 100
    }));
    
    // Round down all percentages
    const flooredPercentages = rawPercentages.map(item => ({
      ...item,
      percentage: Math.floor(item.rawPercentage),
      remainder: item.rawPercentage - Math.floor(item.rawPercentage)
    }));
    
    // Calculate how much we need to add to reach 100%
    const currentSum = flooredPercentages.reduce((sum, item) => sum + item.percentage, 0);
    const difference = 100 - currentSum;
    
    // Sort by remainder (descending) and add 1% to the items with highest remainders
    flooredPercentages.sort((a, b) => b.remainder - a.remainder);
    
    for (let i = 0; i < difference && i < flooredPercentages.length; i++) {
      flooredPercentages[i].percentage += 1;
    }
    
    // Sort back to original order
    return data.map(originalItem => {
      const found = flooredPercentages.find(item => item.name === originalItem.name);
      return { ...originalItem, percentage: found.percentage };
    });
  };

  const dataWithPercentages = calculatePercentages(chartData, total);

  return (
    <div className="orders-breakdown-compact" style={{
      background: 'white',
      padding: window.innerWidth <= 480 ? '8px' : '16px',
      borderRadius: window.innerWidth <= 480 ? '6px' : '8px',
      width: '100%',
      overflow: 'hidden'
    }}>
      <h3 style={{
        fontSize: window.innerWidth <= 480 ? '11px' : '14px',
        fontWeight: '600',
        marginBottom: window.innerWidth <= 480 ? '8px' : '12px',
        color: '#374151'
      }}>Orders Breakdown</h3>
      <div className="breakdown-content">
        {total === 0 ? (
          <div style={{ textAlign: 'center', padding: window.innerWidth <= 480 ? '20px 10px' : '40px 20px', color: '#8c8c8c' }}>
            <div style={{ fontSize: window.innerWidth <= 480 ? '18px' : '24px', marginBottom: '8px' }}>0</div>
            <div style={{ fontSize: window.innerWidth <= 480 ? '12px' : '14px' }}>No orders in system</div>
          </div>
        ) : (
          <>
            <div className="breakdown-chart">
              <div style={{ 
                width: '100%', 
                height: window.innerWidth <= 480 ? '120px' : '140px', 
                minHeight: window.innerWidth <= 480 ? '120px' : '140px', 
                position: 'relative' 
              }}>
                <ResponsiveContainer 
                  width="100%" 
                  height={window.innerWidth <= 480 ? 120 : 140} 
                  minHeight={window.innerWidth <= 480 ? 120 : 140}
                >
                  <PieChart>
                    <Pie
                      data={dataWithPercentages}
                      cx="50%"
                      cy="50%"
                      innerRadius={window.innerWidth <= 480 ? 25 : 35}
                      outerRadius={window.innerWidth <= 480 ? 45 : 60}
                      fill="#8884d8"
                      dataKey="value"
                      strokeWidth={0}
                    >
                      {dataWithPercentages.map((entry, index) => (
                        <Cell key={`cell-${index}`} fill={entry.color} />
                      ))}
                    </Pie>
                  </PieChart>
                </ResponsiveContainer>
              </div>
              <div className="chart-center-label" style={{
                position: 'absolute',
                top: '50%',
                left: '50%',
                transform: 'translate(-50%, -50%)',
                textAlign: 'center'
              }}>
                <div className="total-orders" style={{
                  fontSize: window.innerWidth <= 480 ? '20px' : '24px',
                  fontWeight: '700',
                  color: '#1f2937'
                }}>{total}</div>
                <div className="total-label" style={{
                  fontSize: window.innerWidth <= 480 ? '10px' : '12px',
                  color: '#6b7280'
                }}>Total</div>
              </div>
            </div>
            <div className="breakdown-stats">
              {dataWithPercentages.map((item, index) => (
                <div key={index} className="stat-row" style={{
                  display: 'flex',
                  justifyContent: 'space-between',
                  alignItems: 'center',
                  padding: window.innerWidth <= 480 ? '6px 0' : '8px 0',
                  borderBottom: '1px solid #f3f4f6'
                }}>
                  <div className="stat-info" style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                    <span className="stat-dot" style={{ 
                      background: item.color, 
                      width: '8px', 
                      height: '8px', 
                      borderRadius: '50%' 
                    }}></span>
                    <span className="stat-name" style={{
                      fontSize: window.innerWidth <= 480 ? '11px' : '12px',
                      color: '#374151',
                      fontWeight: '500'
                    }}>{item.name}</span>
                  </div>
                  <div className="stat-values" style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                    <span className="stat-count" style={{
                      fontSize: window.innerWidth <= 480 ? '12px' : '14px',
                      fontWeight: '600',
                      color: '#1f2937'
                    }}>{item.value}</span>
                    <span className="stat-percent" style={{
                      fontSize: window.innerWidth <= 480 ? '10px' : '11px',
                      color: '#6b7280',
                      fontWeight: '500'
                    }}>{item.percentage}%</span>
                  </div>
                </div>
              ))}
            </div>
          </>
        )}
      </div>
    </div>
  );
};

export default OrdersBreakdownChart;
