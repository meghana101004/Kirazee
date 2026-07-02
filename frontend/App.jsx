import React from 'react';
import { BrowserRouter as Router } from 'react-router-dom';
import AppContent from './AppContent';

function App() {
  return (
    <Router future={{
      v7_startTransition: true,
      v7_relativeSplatPath: true
    }}>
      <AppContent />
    </Router>
  );
}

export default App;