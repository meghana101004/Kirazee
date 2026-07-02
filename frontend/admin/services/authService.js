import { config, API_ENDPOINTS } from '../utils/config';
import { safeStorage } from '../utils/storageHelper';

// API service for authentication
export class AuthService {
  
  // Verify login OTP
  static async verifyLoginOtp(mobile, otp) {
    try {
      const response = await fetch(API_ENDPOINTS.VERIFY_LOGIN_OTP, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          mobile: mobile,
          otp: otp,
          whichapp: config.APP_NAME
        })
      });
      
      const data = await response.json();
      return data;
    } catch {
      throw new Error('Network error. Please check your connection and try again.');
    }
  }

  // Send login OTP 
  static async sendLoginOtp(mobile) {
    try {
      const response = await fetch(API_ENDPOINTS.SEND_LOGIN_OTP, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          mobile: mobile,
          whichapp: config.APP_NAME
        })
      });
      
      const data = await response.json();
      return data;
    } catch {
      throw new Error('Network error. Please check your connection and try again.');
    }
  }

  // Register new user and send OTP
  static async registerUser(userData) {
    try {
      const response = await fetch(API_ENDPOINTS.SEND_REGISTER_OTP, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          firstName: userData.firstName,
          lastName: userData.lastName,
          emailID: userData.emailID,
          mobileNumber: userData.mobileNumber,
          countryCode: userData.countryCode || '+91', // Default to India country code
          whichapp: config.APP_NAME
        })
      });
      
      const data = await response.json();
      return data;
    } catch {
      throw new Error('Network error. Please check your connection and try again.');
    }
  }

  // Verify registration OTP (uses same endpoint as login verification)
  static async verifyRegisterOtp(mobile, otp) {
    try {
      const response = await fetch(API_ENDPOINTS.VERIFY_REGISTER_OTP, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          mobile: mobile,
          otp: otp,
          whichapp: config.APP_NAME
        })
      });
      
      const data = await response.json();
      return data;
    } catch {
      throw new Error('Network error. Please check your connection and try again.');
    }
  }

  // Store user data in localStorage
  static storeUserData(userData) {
    try {
      safeStorage.setItem('kirazee_user', JSON.stringify(userData));
      safeStorage.setItem('kirazee_token', userData.token || '');
    } catch (error) {
      console.error('Error storing user data:', error);
    }
  }

  // Get user data from localStorage
  static getUserData() {
    try {
      const userData = safeStorage.getItem('kirazee_user');
      return userData ? JSON.parse(userData) : null;
    } catch (error) {
      console.error('Error retrieving user data:', error);
      return null;
    }
  }

  // Clear user data from localStorage
  static clearUserData() {
    try {
      safeStorage.removeItem('kirazee_user');
      safeStorage.removeItem('kirazee_token');
    } catch (error) {
      console.error('Error clearing user data:', error);
    }
  }

  // Get stored token
  static getToken() {
    return safeStorage.getItem('kirazee_token');
  }

  // Check if user is authenticated
  static isAuthenticated() {
    const userData = this.getUserData();
    const token = safeStorage.getItem('kirazee_token');
    return !!(userData && token);
  }

  // Change user mode
  static async changeUserMode(userID, mode_to) {
    try {
      const response = await fetch(`${API_ENDPOINTS.CHANGE_MODE}?userID=${userID}`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          mode_to: mode_to
        })
      });
      
      const data = await response.json();
      return data;
    } catch (error) {
      console.error('Error changing user mode:', error);
      throw new Error('Network error. Please check your connection and try again.');
    }
  }

  // Fetch user comprehensive details
  static async getUserComprehensiveDetails() {
    try {
      const userData = this.getUserData();
      if (!userData || !userData.user_id) {
        throw new Error('User not authenticated or user ID not found');
      }

      const userID = userData.user_id;
      const mode = userData.user_mode || 'consumer';
      const whichapp = 'kirazee';

      const url = `${API_ENDPOINTS.BASE_URL}/user-comprehensive?userID=${userID}&mode=${mode}&whichapp=${whichapp}`;
      
      const response = await fetch(url, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        }
      });

      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
      }

      const data = await response.json();
      return data;
    } catch (error) {
      console.error('Error fetching user comprehensive details:', error);
      throw error;
    }
  }
}
