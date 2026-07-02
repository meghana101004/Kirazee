import React from 'react';

const PlatformOverview = () => {
  return (
    <div className="platform-content admin-card">
      <h1 className="platform-title">Kirazee Platform Overview</h1>
      <p className="platform-description">
        Kirazee is an integrated retail business platform empowering Retail Business Owners (RBOs) to manage inventory, sales, expenses, and staff, while offering consumers a seamless way to order from local businesses (Restaurants, Grocery, Pharmacy, etc.).
      </p>
      <div className="platform-grid">
        <div className="platform-card">
          <h3 className="platform-card-title">
            <span className="platform-icon">🛒</span> For Consumers
          </h3>
          <ul className="platform-list">
            <li>Local business discovery based on location.</li>
            <li>Real-time product catalog &amp; menu browsing.</li>
            <li>Multiple fulfillment: Delivery, Takeaway, Dine-in.</li>
            <li>Order tracking &amp; history.</li>
          </ul>
        </div>
        <div className="platform-card">
          <h3 className="platform-card-title">
            <span className="platform-icon">💼</span> For Business Owners
          </h3>
          <ul className="platform-list">
            <li>Inventory &amp; Purchase Management.</li>
            <li>Staff Roles &amp; Payroll.</li>
            <li>Unified Order Dashboard (Online + Counter).</li>
            <li>Comprehensive Sales &amp; Financial Reports.</li>
          </ul>
        </div>
      </div>
    </div>
  );
};

export default PlatformOverview;
