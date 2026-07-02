import React from 'react';

const OrderLifecycleManagement = () => {
  return (
    <div className="platform-content admin-card">
      <h1 className="platform-title">Order Lifecycle Management</h1>
      <div className="lifecycle-section">
        <h2 className="section-title">Assignment Logic</h2>
        <p className="platform-description">
          <strong>Purely manual.</strong> RBOs select their own rider or a Kirazee partner based on availability.
        </p>
        <div className="lifecycle-flow">
          <div className="lifecycle-step active">Order Placed</div>
          <div className="lifecycle-arrow">→</div>
          <div className="lifecycle-step">RBO Confirms</div>
          <div className="lifecycle-arrow">→</div>
          <div className="lifecycle-step">Manual Assignment</div>
          <div className="lifecycle-arrow">→</div>
          <div className="lifecycle-step">Rider Pickup</div>
          <div className="lifecycle-arrow">→</div>
          <div className="lifecycle-step">Out for Delivery</div>
          <div className="lifecycle-arrow">→</div>
          <div className="lifecycle-step">OTP Verified</div>
          <div className="lifecycle-arrow">→</div>
          <div className="lifecycle-step completed">Delivered</div>
        </div>
      </div>
      <div className="interaction-section">
        <h2 className="section-title">Detailed Interaction Flow</h2>
        <div className="interaction-flow">
          <div className="interaction-step">
            <div className="actor">Consumer</div>
            <div className="action">Place Order</div>
          </div>
          <div className="interaction-arrow">↓</div>
          <div className="interaction-step">
            <div className="actor">RBO</div>
            <div className="action">Confirm Order</div>
          </div>
          <div className="interaction-arrow">↓</div>
          <div className="interaction-step">
            <div className="actor">RBO</div>
            <div className="action">Manually Assign</div>
          </div>
          <div className="interaction-arrow">↓</div>
          <div className="interaction-step">
            <div className="actor">Rider</div>
            <div className="action">Accept (Mandatory)</div>
          </div>
          <div className="interaction-arrow">↓</div>
          <div className="interaction-step">
            <div className="actor">Rider</div>
            <div className="action">Pickup Package</div>
          </div>
          <div className="interaction-arrow">↓</div>
          <div className="interaction-step">
            <div className="actor">Rider</div>
            <div className="action">Verify OTP</div>
          </div>
          <div className="interaction-arrow">↓</div>
          <div className="interaction-step">
            <div className="actor">Rider</div>
            <div className="action">Mark Delivered</div>
          </div>
        </div>
      </div>
    </div>
  );
};

export default OrderLifecycleManagement;
