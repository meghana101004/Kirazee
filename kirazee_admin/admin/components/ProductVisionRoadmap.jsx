import React from 'react';

const ProductVisionRoadmap = () => {
  return (
    <div className="platform-content admin-card">
      <h1 className="platform-title">Product Vision &amp; Roadmap</h1>
      <div className="vision-section">
        <h2 className="section-title">Executive Overview</h2>
        <p className="platform-description">
          Kirazee is a Retail Business Platform designed to empower Consumers, Retail Business Owners (RBOs), and Delivery Partners without monopolizing branding or operations. Unlike centralized marketplaces, Kirazee promotes individual retail brands. RBOs retain full control, choosing to use Kirazee-provided partners or their own internal fleet.
        </p>
        <div className="vision-highlight">
          <strong>Core Philosophy:</strong> Business-centric delivery (hyperlocal model) where the merchant owns the customer relationship.
        </div>
      </div>
      <div className="roadmap-section">
        <h2 className="section-title">Strategic Roadmap</h2>
        <div className="roadmap-items">
          <div className="roadmap-item">
            <div className="roadmap-number">1</div>
            <div className="roadmap-content">
              <h4 className="roadmap-title">Current Phase: Core Stability</h4>
              <p className="roadmap-desc">
                Bug fixing stage. Access limited to CTO/COO/Devs. Establishing manual assignment flow and physical onboarding.
              </p>
            </div>
          </div>
          <div className="roadmap-item">
            <div className="roadmap-number">2</div>
            <div className="roadmap-content">
              <h4 className="roadmap-title">Next Phase: Optimization</h4>
              <p className="roadmap-desc">
                Defining formal funnels, introducing automated reports, and refining the "white-label" experience for RBOs.
              </p>
            </div>
          </div>
          <div className="roadmap-item">
            <div className="roadmap-number">∞</div>
            <div className="roadmap-content">
              <h4 className="roadmap-title">Expansion Vision</h4>
              <p className="roadmap-desc">
                Operations can scale anywhere, anytime, without geographical restrictions, relying on the "Business Hiring" model.
              </p>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};

export default ProductVisionRoadmap;
