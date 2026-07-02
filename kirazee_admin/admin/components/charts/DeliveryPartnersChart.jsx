import React from 'react';
import { PieChart, Pie, Cell, ResponsiveContainer, Tooltip } from 'recharts';

const DeliveryPartnersChart = ({ data }) => {
  console.log('DeliveryPartnersChart received data:', data);
  
  // Ensure data is an array
  const processedData = Array.isArray(data) ? data : [];
  console.log('Processed partners data length:', processedData.length);
  
  const statusCount = processedData.reduce((acc, partner) => {
    acc[partner.status] = (acc[partner.status] || 0) + 1;
    return acc;
  }, {});

  console.log('Status count:', statusCount);

  const chartData = [
    { name: 'Available', value: statusCount['Available'] || 0, color: '#10b981' },
    { name: 'Busy', value: statusCount['Busy'] || 0, color: '#f59e0b' },
    { name: 'Unavailable', value: statusCount['Unavailable'] || 0, color: '#ef4444' }
  ].filter(item => item.value > 0);

  const total = processedData.length;

  // Handle empty data case
  if (total === 0) {
    return (
      <div style={{ 
        background: 'white', 
        padding: window.innerWidth <= 480 ? '12px' : '20px', 
        borderRadius: window.innerWidth <= 480 ? '6px' : '12px', 
        border: '1px solid #e5e7eb',
        boxShadow: '0 1px 3px rgba(0,0,0,0.1)',
        height: 'auto',
        width: '100%',
        overflow: 'hidden'
      }}>
        <h3 style={{ 
          margin: '0 0 ' + (window.innerWidth <= 480 ? '12px' : '16px') + ' 0', 
          fontSize: window.innerWidth <= 480 ? '12px' : '16px', 
          fontWeight: '600',
          color: '#1f2937'
        }}>
          Delivery Partners Status
        </h3>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: window.innerWidth <= 480 ? '120px' : '140px', color: '#6b7280' }}>
          <div style={{ textAlign: 'center' }}>
            <div style={{ fontSize: window.innerWidth <= 480 ? '24px' : '32px', marginBottom: '8px' }}>🚚</div>
            <p style={{ fontSize: window.innerWidth <= 480 ? '10px' : '12px', margin: '0' }}>No delivery partner data available</p>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div style={{ 
      background: 'white', 
      padding: window.innerWidth <= 480 ? '12px' : '20px', 
      borderRadius: window.innerWidth <= 480 ? '6px' : '12px', 
      border: '1px solid #e5e7eb',
      boxShadow: '0 1px 3px rgba(0,0,0,0.1)',
      height: 'auto',
      width: '100%',
      overflow: 'hidden'
    }}>
      <h3 style={{ 
        margin: '0 0 ' + (window.innerWidth <= 480 ? '12px' : '16px') + ' 0', 
        fontSize: window.innerWidth <= 480 ? '12px' : '16px', 
        fontWeight: '600',
        color: '#1f2937'
      }}>
        Delivery Partners Status
      </h3>
      
      <div style={{ 
        display: 'flex', 
        alignItems: 'center', 
        gap: window.innerWidth <= 480 ? '12px' : '24px',
        flexDirection: window.innerWidth <= 480 ? 'column' : 'row'
      }}>
        {/* Compact Pie Chart */}
        <div style={{ 
          flex: window.innerWidth <= 480 ? 'none' : '0 0 140px', 
          width: window.innerWidth <= 480 ? '100%' : '140px', 
          height: window.innerWidth <= 480 ? '140px' : '140px', 
          minHeight: '140px', 
          position: 'relative',
          display: 'flex',
          justifyContent: 'center'
        }}>
          <ResponsiveContainer 
            width={window.innerWidth <= 480 ? 140 : 140} 
            height={window.innerWidth <= 480 ? 140 : 140} 
            minHeight={140}
          >
            <PieChart>
              <Pie
                data={chartData}
                cx="50%"
                cy="50%"
                innerRadius={window.innerWidth <= 480 ? 35 : 45}
                outerRadius={window.innerWidth <= 480 ? 55 : 65}
                paddingAngle={2}
                dataKey="value"
              >
                {chartData.map((entry, index) => (
                  <Cell key={`cell-${index}`} fill={entry.color} />
                ))}
              </Pie>
              <Tooltip 
                formatter={(value) => [value, 'Partners']}
                contentStyle={{ 
                  backgroundColor: 'white', 
                  border: '1px solid #e5e7eb', 
                  borderRadius: '6px',
                  fontSize: window.innerWidth <= 480 ? '10px' : '12px'
                }}
              />
            </PieChart>
          </ResponsiveContainer>
        </div>

        {/* Stats Grid */}
        <div style={{ 
          flex: 1, 
          display: 'grid', 
          gridTemplateColumns: window.innerWidth <= 480 ? '1fr' : '1fr 1fr', 
          gap: window.innerWidth <= 480 ? '8px' : '12px',
          width: '100%'
        }}>
          <div style={{ 
            padding: window.innerWidth <= 480 ? '8px' : '12px', 
            background: '#f9fafb', 
            borderRadius: '8px',
            border: '1px solid #e5e7eb'
          }}>
            <div style={{ fontSize: window.innerWidth <= 480 ? '9px' : '11px', color: '#6b7280', marginBottom: '4px', fontWeight: '500' }}>
              Total Partners
            </div>
            <div style={{ fontSize: window.innerWidth <= 480 ? '18px' : '24px', fontWeight: '700', color: '#1f2937' }}>
              {total}
            </div>
          </div>

          <div style={{ 
            padding: window.innerWidth <= 480 ? '8px' : '12px', 
            background: '#ecfdf5', 
            borderRadius: '8px',
            border: '1px solid #a7f3d0'
          }}>
            <div style={{ fontSize: window.innerWidth <= 480 ? '9px' : '11px', color: '#059669', marginBottom: '4px', fontWeight: '500' }}>
              Available
            </div>
            <div style={{ fontSize: window.innerWidth <= 480 ? '18px' : '24px', fontWeight: '700', color: '#10b981' }}>
              {statusCount['Available'] || 0}
            </div>
          </div>

          <div style={{ 
            padding: window.innerWidth <= 480 ? '8px' : '12px', 
            background: '#fef3c7', 
            borderRadius: '8px',
            border: '1px solid #fcd34d'
          }}>
            <div style={{ fontSize: window.innerWidth <= 480 ? '9px' : '11px', color: '#d97706', marginBottom: '4px', fontWeight: '500' }}>
              Busy
            </div>
            <div style={{ fontSize: window.innerWidth <= 480 ? '18px' : '24px', fontWeight: '700', color: '#f59e0b' }}>
              {statusCount['Busy'] || 0}
            </div>
          </div>

          <div style={{ 
            padding: window.innerWidth <= 480 ? '8px' : '12px', 
            background: '#fee2e2', 
            borderRadius: '8px',
            border: '1px solid #fca5a5'
          }}>
            <div style={{ fontSize: window.innerWidth <= 480 ? '9px' : '11px', color: '#dc2626', marginBottom: '4px', fontWeight: '500' }}>
              Unavailable
            </div>
            <div style={{ fontSize: window.innerWidth <= 480 ? '18px' : '24px', fontWeight: '700', color: '#ef4444' }}>
              {statusCount['Unavailable'] || 0}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};

export default DeliveryPartnersChart;
