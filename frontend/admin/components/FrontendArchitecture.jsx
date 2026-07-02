import React from 'react';

const FrontendArchitecture = () => {
  return (
    <div className="platform-content admin-card">
      <h1 className="platform-title">Frontend Architecture</h1>

      <div className="frontend-section">
        <h2 className="section-title">Project Structure</h2>
        <div className="folder-structure">
          <pre className="code-block">
{`Frontend React/
├── dist/
├── node_modules/
├── src/
│   ├── assets/       // Images, SVGs, Icons, Logos
│   ├── components/   // Reusable UI components
│   ├── css/          // Global stylesheets
│   ├── data/         // Static data/JSON
│   ├── forms/        // Form schemas & validation logic
│   ├── pages/        // Route components (Views)
│   ├── App.jsx
│   ├── main.jsx
│   └── styles.css
├── .gitignore
├── eslint.config.js
├── package.json
└── vite.config.js`}
          </pre>
        </div>
      </div>

      <div className="frontend-section">
        <h2 className="section-title">Component Architecture</h2>
        <div className="component-grid">
          <div className="component-category">
            <h3 className="component-title">Admin Components</h3>
            <ul className="component-list">
              <li>AdminSidebar.jsx - Navigation sidebar</li>
              <li>DashboardOverview.jsx - Main dashboard</li>
              <li>BusinessManagement.jsx - Business operations</li>
              <li>DeliveryFleet.jsx - Delivery management</li>
              <li>Analytics.jsx - Reports and analytics</li>
            </ul>
          </div>
          <div className="component-category">
            <h3 className="component-title">Shared Components</h3>
            <ul className="component-list">
              <li>Charts - Data visualization components</li>
              <li>Forms - Reusable form components</li>
              <li>Modals - Dialog and popup components</li>
              <li>Tables - Data table components</li>
            </ul>
          </div>
        </div>
      </div>

      <div className="frontend-section">
        <h2 className="section-title">Styling Approach</h2>
        <div className="style-grid">
          <div className="style-card">
            <h3 className="style-title">CSS Architecture</h3>
            <ul className="style-list">
              <li>Modular CSS files per component</li>
              <li>Custom CSS variables for theming</li>
              <li>Responsive design with mobile-first approach</li>
              <li>CSS Grid and Flexbox for layouts</li>
            </ul>
          </div>
          <div className="style-card">
            <h3 className="style-title">Design System</h3>
            <ul className="style-list">
              <li>Consistent color palette</li>
              <li>Typography scale</li>
              <li>Spacing and sizing utilities</li>
              <li>Component variants and states</li>
            </ul>
          </div>
        </div>
      </div>
    </div>
  );
};

export default FrontendArchitecture;
