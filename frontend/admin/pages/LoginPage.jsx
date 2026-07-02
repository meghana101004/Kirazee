import React, { useState } from 'react';
import { FaUser, FaLock, FaEye, FaEyeSlash } from 'react-icons/fa';
import '../../css/auth/LoginPage.css';

const LoginPage = ({ onLogin }) => {
  const [credentials, setCredentials] = useState({
    username: '',
    password: ''
  });
  const [showPassword, setShowPassword] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  const handleChange = (e) => {
    const { name, value } = e.target;
    setCredentials(prev => ({
      ...prev,
      [name]: value
    }));
    if (error) setError('');
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    setLoading(true);
    setError('');

    // Simulate authentication (replace with actual API call)
    try {
      // Mock authentication logic based on roles
      const mockUsers = {
        'superadmin': { password: 'admin123', role: 'SuperAdmin', name: 'Super Administrator' },
        'manager': { password: 'manager123', role: 'Manager', name: 'Manager' },
        'support': { password: 'support123', role: 'Support Team', name: 'Support Agent' },
        'kyc': { password: 'kyc123', role: 'KYC Associates', name: 'KYC Associate' },
        'finance': { password: 'finance123', role: 'CA/Finance', name: 'Finance Manager' }
      };

      const user = mockUsers[credentials.username.toLowerCase()];
      
      if (user && user.password === credentials.password) {
        const userData = {
          id: credentials.username,
          name: user.name,
          role: user.role,
          token: 'mock-jwt-token-' + Date.now()
        };
        
        localStorage.setItem('user', JSON.stringify(userData));
        onLogin(userData);
      } else {
        setError('Invalid username or password');
      }
    } catch (err) {
      setError('Login failed. Please try again.');
    } finally {
      setLoading(false);
    }
  };

  const togglePasswordVisibility = () => {
    setShowPassword(!showPassword);
  };

  return (
    <div className="login-container">
      <div className="login-background">
        <div className="login-overlay"></div>
      </div>
      
      <div className="login-card">
        <div className="login-header">
          <div className="login-logo">
            <div className="logo-icon">
              <FaUser />
            </div>
            <h1>Kirazee</h1>
          </div>
          <h2>Admin Portal</h2>
          <p>Sign in to access your dashboard</p>
        </div>

        <form onSubmit={handleSubmit} className="login-form">
          {error && (
            <div className="error-message">
              {error}
            </div>
          )}

          <div className="form-group">
            <label htmlFor="username">Username</label>
            <div className="input-wrapper">
              <input
                type="text"
                id="username"
                name="username"
                value={credentials.username}
                onChange={handleChange}
                placeholder="Enter your username"
                required
                disabled={loading}
              />
            </div>
          </div>

          <div className="form-group">
            <label htmlFor="password">Password</label>
            <div className="input-wrapper">
              <input
                type={showPassword ? 'text' : 'password'}
                id="password"
                name="password"
                value={credentials.password}
                onChange={handleChange}
                placeholder="Enter your password"
                required
                disabled={loading}
              />
              <button
                type="button"
                className="password-toggle"
                onClick={togglePasswordVisibility}
                disabled={loading}
              >
                {showPassword ? <FaEyeSlash /> : <FaEye />}
              </button>
            </div>
          </div>

          <button 
            type="submit" 
            className={`login-button ${loading ? 'loading' : ''}`}
            disabled={loading}
          >
            {loading ? '' : 'Sign In'}
          </button>
        </form>
      </div>
    </div>
  );
};

export default LoginPage;