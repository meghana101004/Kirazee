import React from 'react';

const TopCategoriesWidget = ({ snapshot, summary }) => {
  const totalRevenue = snapshot?.revenue?.total_revenue || 3400000;
  
  // Try to get real category data from summary
  const getCategoriesData = () => {
    // Check if summary has category breakdown
    if (summary?.category_metrics?.categories && summary.category_metrics.categories.length > 0) {
      return summary.category_metrics.categories.map((cat, index) => ({
        name: cat.category_name || cat.name,
        amount: parseFloat(cat.revenue || cat.amount || 0),
        color: ['#FF8C42', '#FFD93D', '#6BCF7F', '#4A90E2', '#9B59B6'][index % 5]
      }));
    }
    
    // Fallback: Use business type data if available
    if (summary?.business_list_metrics?.all_businesses) {
      const businessTypes = {};
      summary.business_list_metrics.all_businesses.forEach(business => {
        const type = business.business_type || 'Other';
        if (!businessTypes[type]) {
          businessTypes[type] = 0;
        }
        businessTypes[type] += parseFloat(business.revenue || 0);
      });
      
      return Object.entries(businessTypes)
        .map(([name, amount], index) => ({
          name,
          amount,
          color: ['#FF8C42', '#FFD93D', '#6BCF7F', '#4A90E2', '#9B59B6'][index % 5]
        }))
        .sort((a, b) => b.amount - a.amount)
        .slice(0, 4);
    }
    
    // Default fallback categories
    return [
      { name: 'Food & Beverage', amount: totalRevenue * 0.35, color: '#FF8C42' },
      { name: 'Retail', amount: totalRevenue * 0.28, color: '#FFD93D' },
      { name: 'Grocery', amount: totalRevenue * 0.22, color: '#6BCF7F' },
      { name: 'Services', amount: totalRevenue * 0.15, color: '#4A90E2' }
    ];
  };
  
  const categories = getCategoriesData();

  const formatCurrency = (amount) => {
    if (amount >= 10000000) {
      return `₹${(amount / 10000000).toFixed(1)}Cr`;
    }
    if (amount >= 100000) {
      return `₹${(amount / 100000).toFixed(2)} Lakh`;
    }
    return `₹${(amount / 1000).toFixed(0)}K`;
  };
  
  // Calculate donut chart segments
  const total = categories.reduce((sum, cat) => sum + cat.amount, 0);
  const circumference = 2 * Math.PI * 70; // radius = 70
  let currentOffset = 0;

  return (
    <div className="top-categories-widget">
      <div className="widget-header">
        <h3>Top Categories</h3>
        <button className="see-all-btn">See All</button>
      </div>

      <div className="category-chart">
        <svg viewBox="0 0 200 200" className="donut-chart">
          {categories.map((category, index) => {
            const percentage = (category.amount / total) * 100;
            const dashArray = (percentage / 100) * circumference;
            const segment = (
              <circle
                key={index}
                cx="100"
                cy="100"
                r="70"
                fill="none"
                stroke={category.color}
                strokeWidth="40"
                strokeDasharray={`${dashArray} ${circumference}`}
                strokeDashoffset={-currentOffset}
                transform="rotate(-90 100 100)"
              />
            );
            currentOffset += dashArray;
            return segment;
          })}
        </svg>
        <div className="chart-center">
          <div className="center-value">{formatCurrency(total)}</div>
          <div className="center-label">Total</div>
        </div>
      </div>

      <div className="categories-list">
        {categories.map((category, index) => (
          <div key={index} className="category-item">
            <div className="category-info">
              <span className="category-dot" style={{ backgroundColor: category.color }}></span>
              <span className="category-name">{category.name}</span>
            </div>
            <span className="category-amount">{formatCurrency(category.amount)}</span>
          </div>
        ))}
      </div>
    </div>
  );
};

export default TopCategoriesWidget;
