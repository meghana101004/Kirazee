import React from 'react'
import ReactDOM from 'react-dom/client'
import App from './App.jsx'

// Filter out browser extension errors in development
if (import.meta.env.DEV) {
  window.addEventListener('error', (event) => {
    // Ignore errors from browser extensions
    if (event.filename && (
      event.filename.includes('general.js') ||
      event.filename.includes('contentScript.bundle.js') ||
      event.filename.includes('extension') ||
      event.filename.includes('chrome-extension') ||
      event.filename.includes('moz-extension')
    )) {
      event.preventDefault()
      return false
    }
  })

  window.addEventListener('unhandledrejection', (event) => {
    // Ignore promise rejections from browser extensions
    if (event.reason && typeof event.reason === 'object' && event.reason.message) {
      const message = event.reason.message
      if (message.includes('FirebaseError') && 
          (message.includes('Remote Config') || message.includes('indexedDB'))) {
        event.preventDefault()
        return false
      }
    }
  })
}

ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
)
