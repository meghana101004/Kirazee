// Environment configuration utility
const VITE_API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'https://kirazee.com';
const VITE_API_PREFIX = import.meta.env.VITE_API_PREFIX || '/kirazee';
const VITE_APP_NAME = import.meta.env.VITE_APP_NAME || 'kirazee';
const VITE_APP_VERSION = import.meta.env.VITE_APP_VERSION || '1.0.0';

export const config = {
  API_BASE_URL: VITE_API_BASE_URL,
  API_PREFIX: VITE_API_PREFIX,
  APP_NAME: VITE_APP_NAME,
  APP_VERSION: VITE_APP_VERSION,
  ENV: import.meta.env.MODE || 'development'
};

// API endpoints
export const API_ENDPOINTS = {
  BASE_URL: `${config.API_BASE_URL}${config.API_PREFIX}`,
  VERIFY_LOGIN_OTP: `${config.API_BASE_URL}${config.API_PREFIX}/verify-login-otp/`,
  SEND_LOGIN_OTP: `${config.API_BASE_URL}${config.API_PREFIX}/login/`,
  SEND_REGISTER_OTP: `${config.API_BASE_URL}${config.API_PREFIX}/register/`,
  VERIFY_REGISTER_OTP: `${config.API_BASE_URL}${config.API_PREFIX}/verify-otp/`,
  CHANGE_MODE: `${config.API_BASE_URL}${config.API_PREFIX}/change_mode`
};
