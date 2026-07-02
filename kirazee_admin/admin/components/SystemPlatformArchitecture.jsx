import React from 'react';

const SystemPlatformArchitecture = () => {
  return (
    <div className="platform-content admin-card">
      <h1 className="platform-title">System &amp; Platform Architecture</h1>
      <div className="architecture-section">
        <h2 className="section-title">System Architecture Map</h2>
        <div className="architecture-grid">
          <div className="arch-category">
            <h3 className="arch-title">Web Portals</h3>
            <div className="arch-items">
              <div className="arch-item">Consumer Website</div>
              <div className="arch-item">Business Admin Portal</div>
              <div className="arch-item">Delivery Console</div>
            </div>
          </div>
          <div className="arch-category">
            <h3 className="arch-title">Mobile Apps</h3>
            <div className="arch-items">
              <div className="arch-item">Consumer App</div>
              <div className="arch-item">Business Lite</div>
              <div className="arch-item">Delivery Partner</div>
            </div>
          </div>
          <div className="arch-category">
            <h3 className="arch-title">Core Services</h3>
            <div className="arch-items">
              <div className="arch-item">User Management</div>
              <div className="arch-item">Business Operations</div>
              <div className="arch-item">Logistics (Delivery/Tracking)</div>
            </div>
          </div>
        </div>
      </div>
      <div className="tech-stack-section">
        <h2 className="section-title">Technology Stack</h2>
        <div className="tech-grid">
          <div className="tech-category">
            <h3 className="tech-title">Frontend</h3>
            <ul className="tech-list">
              <li>React.js</li>
              <li>Tailwind CSS</li>
              <li>Vite</li>
            </ul>
          </div>
          <div className="tech-category">
            <h3 className="tech-title">Backend</h3>
            <ul className="tech-list">
              <li>Node.js</li>
              <li>Express.js</li>
              <li>MySQL</li>
            </ul>
          </div>
          <div className="tech-category">
            <h3 className="tech-title">Infrastructure</h3>
            <ul className="tech-list">
              <li>AWS</li>
              <li>Docker</li>
              <li>Redis</li>
            </ul>
          </div>
        </div>
      </div>
    </div>
  );
};

export default SystemPlatformArchitecture;
