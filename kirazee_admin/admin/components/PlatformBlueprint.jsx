import React, { useState, useEffect } from 'react';
import '../../css/admin/PlatformBlueprint.css';
import PlatformOverview from './PlatformOverview';
import ProductVisionRoadmap from './ProductVisionRoadmap';
import UserJourneyFlows from './UserJourneyFlows';
import OrderLifecycleManagement from './OrderLifecycleManagement';
import SystemPlatformArchitecture from './SystemPlatformArchitecture';
import DatabaseDesign from './DatabaseDesign';
import ApiServiceSpecifications from './ApiServiceSpecifications';
import OperationalWorkflows from './OperationalWorkflows';
import FrontendArchitecture from './FrontendArchitecture';

const PlatformBlueprint = ({ activeSection }) => {
  const [selectedContent, setSelectedContent] = useState('overview');

  useEffect(() => {
    // Map the active section to content
    const sectionMap = {
      'platform-blueprint': 'overview',
      'product-vision': 'product-vision',
      'user-journey': 'user-journey',
      'order-lifecycle': 'order-lifecycle',
      'system-architecture': 'system-architecture',
      'database-design': 'database-design',
      'api-specifications': 'api-specifications',
      'operational-workflows': 'operational-workflows',
      'frontend-architecture': 'frontend-architecture'
    };
    
    setSelectedContent(sectionMap[activeSection] || 'overview');
  }, [activeSection]);

  const renderContent = () => {
    switch (selectedContent) {
      case 'overview':
        return <PlatformOverview />;
      case 'product-vision':
        return <ProductVisionRoadmap />;
      case 'user-journey':
        return <UserJourneyFlows />;
      case 'order-lifecycle':
        return <OrderLifecycleManagement />;
      case 'system-architecture':
        return <SystemPlatformArchitecture />;
      case 'database-design':
        return <DatabaseDesign />;
      case 'api-specifications':
        return <ApiServiceSpecifications />;
      case 'operational-workflows':
        return <OperationalWorkflows />;
      case 'frontend-architecture':
        return <FrontendArchitecture />;
      default:
        return <PlatformOverview />;
    }
  };

  return (
    <div className="platform-blueprint">
      {renderContent()}
    </div>
  );
};

export default PlatformBlueprint;
