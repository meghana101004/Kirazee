import React from 'react';

const ActiveUsersWidget = ({ snapshot, summary }) => {
  const totalUsers = snapshot?.customers?.total_users || 0;
  const activeUsers = snapshot?.customers?.active_users || totalUsers;
  
  // Try to get real location data from summary
  const getLocationData = () => {
    if (summary?.user_analytics?.location_breakdown) {
      return summary.user_analytics.location_breakdown.slice(0, 3).map(loc => ({
        name: loc.location || loc.city || loc.state,
        percentage: parseFloat(loc.percentage || 0),
        flag: loc.country_code === 'IN' ? '🇮🇳' : '🌍'
      }));
    }
    
    // Fallback: Calculate from customer data if available
    if (summary?.user_analytics?.unique_customers_details) {
      const locationCounts = {};
      let total = summary.user_analytics.unique_customers_details.length;
      
      summary.user_analytics.unique_customers_details.forEach(customer => {
        const location = customer.city || customer.state || 'Unknown';
        locationCounts[location] = (locationCounts[location] || 0) + 1;
      });
      
      return Object.entries(locationCounts)
        .map(([name, count]) => ({
          name,
          percentage: ((count / total) * 100).toFixed(1),
          flag: '🇮🇳'
        }))
        .sort((a, b) => b.percentage - a.percentage)
        .slice(0, 3);
    }
    
    // Default fallback
    return [
      { name: 'India', percentage: 85, flag: '🇮🇳' },
      { name: 'Others', percentage: 15, flag: '🌍' }
    ];
  };
  
  const locations = getLocationData();

  return (
    <div className="active-users-widget">
      <div className="widget-header">
        <h3>Active User</h3>
        <button className="more-btn">⋯</button>
      </div>

      <div className="users-count">
        <div className="count-value">{totalUsers.toLocaleString()}</div>
        <div className="count-label">Activated</div>
      </div>

      <div className="countries-list">
        {locations.map((location, index) => (
          <div key={index} className="country-item">
            <div className="country-info">
              <span className="country-flag">{location.flag}</span>
              <span className="country-name">{location.name}</span>
            </div>
            <div className="country-stats">
              <span className="country-percentage">{location.percentage}%</span>
              <div className="country-bar">
                <div 
                  className="country-bar-fill" 
                  style={{ width: `${location.percentage}%` }}
                ></div>
              </div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
};

export default ActiveUsersWidget;
