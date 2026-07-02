import React from 'react';

const MonthlyTargetWidget = ({ snapshot, summary }) => {
  const totalRevenue = snapshot?.revenue?.total_revenue || 0;
  const monthlyTarget = snapshot?.revenue?.monthly_target || 3400000; // Get from DB or default to ₹34 lakh
  const achievementPercentage = Math.min((totalRevenue / monthlyTarget) * 100, 100);
  const remainingAmount = Math.max(monthlyTarget - totalRevenue, 0);
  
  // Get growth from summary data
  const monthlyGrowth = summary?.revenue_metrics?.monthly_growth || snapshot?.revenue?.monthly_growth || 8.02;

  const formatCurrency = (amount) => {
    if (amount >= 10000000) {
      return `₹${(amount / 10000000).toFixed(1)}Cr`;
    }
    if (amount >= 100000) {
      return `₹${(amount / 100000).toFixed(0)} Lakh`;
    }
    return `₹${(amount / 1000).toFixed(0)}K`;
  };

  return (
    <div className="monthly-target-widget">
      <div className="widget-header">
        <h3>Monthly Target</h3>
        <button className="more-btn">⋯</button>
      </div>

      <div className="target-circle">
        <svg viewBox="0 0 200 200" className="progress-ring">
          <circle
            cx="100"
            cy="100"
            r="85"
            fill="none"
            stroke="#f0f0f0"
            strokeWidth="20"
          />
          <circle
            cx="100"
            cy="100"
            r="85"
            fill="none"
            stroke="#FF8C42"
            strokeWidth="20"
            strokeDasharray={`${achievementPercentage * 5.34} 534`}
            strokeLinecap="round"
            transform="rotate(-90 100 100)"
          />
        </svg>
        <div className="target-percentage">
          <span className="percentage-value">{achievementPercentage.toFixed(0)}%</span>
          <span className="percentage-change">+{monthlyGrowth.toFixed(2)}% from last month</span>
        </div>
      </div>

      <div className="target-details">
        <div className="target-row">
          <span className="label">Great Progress!</span>
        </div>
        <div className="target-row achievement">
          <span className="label">Our achievement increased by</span>
          <span className="value highlight">{formatCurrency(totalRevenue)}</span>
        </div>
        <div className="target-row">
          <span className="label">till reach 100% over month</span>
        </div>
      </div>

      <div className="target-footer">
        <div className="footer-stat">
          <span className="stat-label">This Month</span>
          <span className="stat-value">{formatCurrency(totalRevenue)}</span>
        </div>
        <div className="footer-stat">
          <span className="stat-label">Remaining</span>
          <span className="stat-value">{formatCurrency(remainingAmount)}</span>
        </div>
      </div>
    </div>
  );
};

export default MonthlyTargetWidget;
