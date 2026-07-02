import React from 'react';

const UserJourneyFlows = () => {
  return (
    <div className="platform-content admin-card">
      <h1 className="platform-title">User Journey &amp; User Flows</h1>
      <div className="journey-section">
        <h2 className="section-title">Delivery User Roles</h2>
        <p className="platform-description">
          The ecosystem follows a simplified structure with a single delivery-side role. Control resides with the RBO.
        </p>
        <div className="role-cards">
          <div className="role-card">
            <h3 className="role-title">Delivery Partner (Rider)</h3>
            <p className="role-desc">
              Responsible for pickup, fulfillment, payment collection, and customer interaction.
            </p>
          </div>
          <div className="role-card">
            <h3 className="role-title">Retail Business Owner (RBO)</h3>
            <p className="role-desc">Acts as the dispatcher, manually assigning orders to riders.</p>
          </div>
        </div>
      </div>
      <div className="flow-section">
        <h2 className="section-title">Order Capture &amp; Architecture</h2>
        <div className="flow-diagram">
          <div className="flow-step">Consumer App/Web</div>
          <div className="flow-arrow">→</div>
          <div className="flow-step">RBO Dashboard</div>
          <div className="flow-arrow">→</div>
          <div className="flow-step">Manual Assignment</div>
          <div className="flow-arrow">→</div>
          <div className="flow-step">Delivery Partner App</div>
        </div>
        <div className="flow-note">
          <strong>Mandatory Data Points:</strong> Pickup Lat/Long, Customer Address, Payment Method (COD/Prepaid), Live Location Sharing.
        </div>
      </div>
    </div>
  );
};

export default UserJourneyFlows;
