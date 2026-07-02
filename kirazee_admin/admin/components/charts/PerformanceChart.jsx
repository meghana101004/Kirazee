import React from 'react';
import { FiCheckCircle, FiXCircle, FiTrendingUp, FiTrendingDown } from 'react-icons/fi';

const PerformanceChart = ({ data }) => {
  const completionRate = data.completion_rate || 0;
  const cancellationRate = data.cancellation_rate || 0;
  const successRate = 100 - cancellationRate;

  // Calculate performance status
  const getPerformanceStatus = (rate) => {
    if (rate >= 80) return { label: 'Excellent', color: '#10b981', bg: '#d1fae5' };
    if (rate >= 60) return { label: 'Good', color: '#3b82f6', bg: '#dbeafe' };
    if (rate >= 40) return { label: 'Fair', color: '#f59e0b', bg: '#fef3c7' };
    return { label: 'Needs Improvement', color: '#ef4444', bg: '#fee2e2' };
  };

  const completionStatus = getPerformanceStatus(completionRate);
  const cancellationStatus = cancellationRate <= 10 
    ? { label: 'Low', color: '#10b981', bg: '#d1fae5' }
    : cancellationRate <= 20 
    ? { label: 'Moderate', color: '#f59e0b', bg: '#fef3c7' }
    : { label: 'High', color: '#ef4444', bg: '#fee2e2' };

  return (
    <div className="performance-metrics-card" style={{
      background: 'linear-gradient(135deg, #F55D00 0%, #FDBF50 100%)',
      padding: '24px',
      borderRadius: '16px',
      height: '100%',
      minHeight: '320px',
      color: 'white',
      boxShadow: '0 10px 30px rgba(102, 126, 234, 0.3)',
      position: 'relative',
      overflow: 'hidden'
    }}>
      {/* Background decoration */}
      <div style={{
        position: 'absolute',
        top: '-50px',
        right: '-50px',
        width: '200px',
        height: '200px',
        background: 'rgba(255, 255, 255, 0.1)',
        borderRadius: '50%',
        filter: 'blur(40px)'
      }} />
      
      <div style={{ position: 'relative', zIndex: 1 }}>
        <h3 style={{ 
          fontSize: '18px', 
          fontWeight: '700', 
          marginBottom: '20px', 
          color: 'white',
          display: 'flex',
          alignItems: 'center',
          gap: '8px'
        }}>
          <FiTrendingUp size={20} />
          Performance Metrics
        </h3>

        {/* Completion Rate Section */}
        <div style={{
          background: 'rgba(255, 255, 255, 0.15)',
          backdropFilter: 'blur(10px)',
          borderRadius: '12px',
          padding: '16px',
          marginBottom: '16px',
          border: '1px solid rgba(255, 255, 255, 0.2)'
        }}>
          <div style={{ 
            display: 'flex', 
            justifyContent: 'space-between', 
            alignItems: 'center',
            marginBottom: '12px'
          }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
              <FiCheckCircle size={18} style={{ color: '#10b981' }} />
              <span style={{ fontSize: '14px', fontWeight: '600' }}>Completion Rate</span>
            </div>
            <div style={{ 
              background: completionStatus.bg,
              color: completionStatus.color,
              padding: '4px 12px',
              borderRadius: '20px',
              fontSize: '11px',
              fontWeight: '700'
            }}>
              {completionStatus.label}
            </div>
          </div>
          
          <div style={{ 
            fontSize: '36px', 
            fontWeight: '800', 
            marginBottom: '8px',
            letterSpacing: '-1px'
          }}>
            {completionRate.toFixed(1)}%
          </div>
          
          {/* Progress bar */}
          <div style={{
            width: '100%',
            height: '8px',
            background: 'rgba(255, 255, 255, 0.2)',
            borderRadius: '4px',
            overflow: 'hidden'
          }}>
            <div style={{
              width: `${completionRate}%`,
              height: '100%',
              background: 'linear-gradient(90deg, #10b981, #34d399)',
              borderRadius: '4px',
              transition: 'width 0.8s ease'
            }} />
          </div>
          
          <div style={{ 
            fontSize: '12px', 
            marginTop: '8px',
            opacity: 0.9
          }}>
            {Math.round(completionRate * 1.94)} of 194 orders completed
          </div>
        </div>

        {/* Cancellation Rate Section */}
        <div style={{
          background: 'rgba(255, 255, 255, 0.15)',
          backdropFilter: 'blur(10px)',
          borderRadius: '12px',
          padding: '16px',
          border: '1px solid rgba(255, 255, 255, 0.2)'
        }}>
          <div style={{ 
            display: 'flex', 
            justifyContent: 'space-between', 
            alignItems: 'center',
            marginBottom: '12px'
          }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
              <FiXCircle size={18} style={{ color: '#ef4444' }} />
              <span style={{ fontSize: '14px', fontWeight: '600' }}>Cancellation Rate</span>
            </div>
            <div style={{ 
              background: cancellationStatus.bg,
              color: cancellationStatus.color,
              padding: '4px 12px',
              borderRadius: '20px',
              fontSize: '11px',
              fontWeight: '700'
            }}>
              {cancellationStatus.label}
            </div>
          </div>
          
          <div style={{ 
            fontSize: '36px', 
            fontWeight: '800', 
            marginBottom: '8px',
            letterSpacing: '-1px'
          }}>
            {cancellationRate.toFixed(1)}%
          </div>
          
          {/* Progress bar */}
          <div style={{
            width: '100%',
            height: '8px',
            background: 'rgba(255, 255, 255, 0.2)',
            borderRadius: '4px',
            overflow: 'hidden'
          }}>
            <div style={{
              width: `${cancellationRate}%`,
              height: '100%',
              background: 'linear-gradient(90deg, #ef4444, #f87171)',
              borderRadius: '4px',
              transition: 'width 0.8s ease'
            }} />
          </div>
          
          <div style={{ 
            fontSize: '12px', 
            marginTop: '8px',
            opacity: 0.9
          }}>
            Industry standard: 5-10%
          </div>
        </div>
      </div>
    </div>
  );
};

export default PerformanceChart;
