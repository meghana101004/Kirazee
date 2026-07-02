import React from 'react';

const OperationalWorkflows = () => {
  return (
    <div className="platform-content admin-card">
      <h1 className="platform-title">Operational Workflows</h1>

      <div className="workflow-section">
        <h2 className="section-title">Consumer Order &amp; Payment Flow</h2>
        <div className="workflow-diagram">
          <div className="workflow-step">
            <div className="step-number">1</div>
            <div className="step-content">
              <strong>User Browses</strong> → Adds Items to Cart (Cart Total: ₹800)
            </div>
          </div>
          <div className="workflow-arrow">↓</div>
          <div className="workflow-step">
            <div className="step-number">2</div>
            <div className="step-content">
              <strong>Create Order API</strong> (POST /orders/create) → Status:{' '}
              <span className="status-pending">PENDING_PAYMENT</span>
            </div>
          </div>
          <div className="workflow-arrow">↓</div>
          <div className="workflow-step">
            <div className="step-number">3</div>
            <div className="step-content">
              <strong>Initiate Payment</strong> (POST /payment/initiate) → Get Razorpay Key &amp;
              Order ID
            </div>
          </div>
          <div className="workflow-arrow">↓</div>
          <div className="workflow-step">
            <div className="step-number">4</div>
            <div className="step-content">
              <strong>User Pays</strong> on Frontend (Razorpay Modal)
            </div>
          </div>
          <div className="workflow-arrow">↓</div>
          <div className="workflow-step">
            <div className="step-number">5</div>
            <div className="step-content">
              <strong>Success</strong> → Webhook Triggered (POST /payment/webhook/)
            </div>
          </div>
          <div className="workflow-arrow">↓</div>
          <div className="workflow-step">
            <div className="step-number">6</div>
            <div className="step-content">
              <strong>Server Verifies</strong> Signature → Updates Payment Table → Updates Order
              Status: <span className="status-confirmed">CONFIRMED</span>
            </div>
          </div>
          <div className="workflow-arrow">↓</div>
          <div className="workflow-step">
            <div className="step-number">7</div>
            <div className="step-content">
              <strong>RBO Receives</strong> Order → Status:{' '}
              <span className="status-preparing">PREPARING</span> →{' '}
              <span className="status-ready">READY</span> →{' '}
              <span className="status-delivered">DELIVERED</span>
            </div>
          </div>
        </div>
      </div>

      <div className="workflow-section">
        <h2 className="section-title">Rider Technology &amp; Operations</h2>
        <div className="tech-grid">
          <div className="tech-card">
            <h3 className="tech-card-title">Platforms</h3>
            <ul className="tech-list">
              <li>Mobile App</li>
              <li>Web Dashboard</li>
            </ul>
          </div>
          <div className="tech-card">
            <h3 className="tech-card-title">Notifications</h3>
            <ul className="tech-list">
              <li>WhatsApp</li>
              <li>Email (No SMS)</li>
            </ul>
          </div>
          <div className="tech-card">
            <h3 className="tech-card-title">Requirements</h3>
            <ul className="tech-list">
              <li>Own Smartphone</li>
              <li>Google Maps Integration</li>
            </ul>
          </div>
          <div className="tech-card">
            <h3 className="tech-card-title">Payment &amp; Settlement</h3>
            <ul className="tech-list">
              <li>
                <strong>Modes:</strong> COD, UPI, Z.Wallet
              </li>
              <li>
                <strong>Collection:</strong> Direct by Partner
              </li>
              <li>
                <strong>Settlement:</strong> Monthly cycle
              </li>
            </ul>
          </div>
        </div>
      </div>
    </div>
  );
};

export default OperationalWorkflows;
