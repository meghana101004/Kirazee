import { API_ENDPOINTS } from '../utils/config';
import { AuthService } from './authService';
import { safeStorage } from '../utils/storageHelper';

// Business API service
export class BusinessService {
  
  // Fetch business types from backend
  static async fetchBusinessTypes() {
    try {
      const response = await fetch(`${API_ENDPOINTS.BASE_URL}/business/fetch-types/`, {
        method: 'GET',
        headers: {
          'Content-Type': 'application/json',
        }
      });
      
      const data = await response.json();
      return data;
    } catch (error) {
      console.error('Error fetching business types:', error);
      throw new Error('Network error. Please check your connection and try again.');
    }
  }

  // Fetch business features from backend
  static async fetchBusinessFeatures() {
    try {
      const response = await fetch(`${API_ENDPOINTS.BASE_URL}/business/business-features/`, {
        method: 'GET',
        headers: {
          'Content-Type': 'application/json',
        }
      });
      
      const data = await response.json();
      return data;
    } catch (error) {
      console.error('Error fetching business features:', error);
      throw new Error('Network error. Please check your connection and try again.');
    }
  }
  
  // Get existing business data for user (draft retrieval)
  static async getExistingBusiness() {
    try {
      const userData = AuthService.getUserData();
      if (!userData || !userData.user_id) {
        throw new Error('User not authenticated');
      }

      const response = await fetch(`${API_ENDPOINTS.BASE_URL}/business/create?userID=${userData.user_id}`, {
        method: 'GET',
        headers: {
          'Content-Type': 'application/json',
        }
      });
      
      const data = await response.json();
      return data;
    } catch (error) {
      console.error('Error fetching existing business:', error);
      throw new Error('Network error. Please check your connection and try again.');
    }
  }

  // Create business section 1 (Basic Info)
  static async createBusinessSection1(formData) {
    try {
      const userData = AuthService.getUserData();
      if (!userData || !userData.user_id) {
        throw new Error('User not authenticated');
      }

      const response = await fetch(`${API_ENDPOINTS.BASE_URL}/business/create?userID=${userData.user_id}&section=1`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(formData)
      });
      
      const data = await response.json();
      return data;
    } catch (error) {
      console.error('Error creating business section 1:', error);
      throw new Error('Network error. Please check your connection and try again.');
    }
  }

  // Create business section 2 (Address & Location)
  static async createBusinessSection2(formData) {
    try {
      const userData = AuthService.getUserData();
      if (!userData || !userData.user_id) {
        throw new Error('User not authenticated');
      }

      const response = await fetch(`${API_ENDPOINTS.BASE_URL}/business/create?userID=${userData.user_id}&section=2`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(formData)
      });
      
      const data = await response.json();
      return data;
    } catch (error) {
      console.error('Error creating business section 2:', error);
      throw new Error('Network error. Please check your connection and try again.');
    }
  }

  // Create business section 3 (Financial Details)
  static async createBusinessSection3(formData) {
    try {
      const userData = AuthService.getUserData();
      if (!userData || !userData.user_id) {
        throw new Error('User not authenticated');
      }

      const response = await fetch(`${API_ENDPOINTS.BASE_URL}/business/create?userID=${userData.user_id}&section=3`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(formData)
      });
      
      const data = await response.json();
      return data;
    } catch (error) {
      console.error('Error creating business section 3:', error);
      throw new Error('Network error. Please check your connection and try again.');
    }
  }

  // Update business section 1 (Edit functionality)
  static async updateBusinessSection1(businessId, formData) {
    try {
      const userData = AuthService.getUserData();
      if (!userData || !userData.user_id) {
        throw new Error('User not authenticated');
      }

      const updateData = {
        business_id: businessId,
        ...formData
      };

      console.log('PUT Request to:', `${API_ENDPOINTS.BASE_URL}/business/create?userID=${userData.user_id}&section=1`);
      console.log('PUT Data:', updateData);
      
      const response = await fetch(`${API_ENDPOINTS.BASE_URL}/business/create?userID=${userData.user_id}&section=1`, {
        method: 'PUT',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(updateData)
      });
      
      console.log('📥 PUT Response status:', response.status, response.statusText);
      
      if (!response.ok) {
        const errorText = await response.text();
        console.error('❌ PUT Error response:', errorText);
        throw new Error(`HTTP ${response.status}: ${errorText}`);
      }
      
      const data = await response.json();
      console.log('✅ PUT Success data:', data);
      return data;
    } catch (error) {
      console.error('Error updating business section 1:', error);
      throw new Error('Network error. Please check your connection and try again.');
    }
  }

  // Update business section 2 (Edit functionality)
  static async updateBusinessSection2(businessId, formData) {
    try {
      const userData = AuthService.getUserData();
      if (!userData || !userData.user_id) {
        throw new Error('User not authenticated');
      }

      const updateData = {
        business_id: businessId,
        ...formData
      };

      console.log('PUT Request to:', `${API_ENDPOINTS.BASE_URL}/business/create?userID=${userData.user_id}&section=2`);
      console.log('PUT Data:', updateData);
      
      const response = await fetch(`${API_ENDPOINTS.BASE_URL}/business/create?userID=${userData.user_id}&section=2`, {
        method: 'PUT',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(updateData)
      });
      
      console.log('📥 PUT Response status:', response.status, response.statusText);
      
      if (!response.ok) {
        const errorText = await response.text();
        console.error('❌ PUT Error response:', errorText);
        throw new Error(`HTTP ${response.status}: ${errorText}`);
      }
      
      const data = await response.json();
      console.log('✅ PUT Success data:', data);
      return data;
    } catch (error) {
      console.error('Error updating business section 2:', error);
      throw new Error('Network error. Please check your connection and try again.');
    }
  }

  // Update business section 3 (Edit functionality)
  static async updateBusinessSection3(businessId, formData) {
    try {
      const userData = AuthService.getUserData();
      if (!userData || !userData.user_id) {
        throw new Error('User not authenticated');
      }

      const updateData = {
        business_id: businessId,
        ...formData
      };

      console.log('PUT Request to:', `${API_ENDPOINTS.BASE_URL}/business/create?userID=${userData.user_id}&section=3`);
      console.log('PUT Data:', updateData);
      
      const response = await fetch(`${API_ENDPOINTS.BASE_URL}/business/create?userID=${userData.user_id}&section=3`, {
        method: 'PUT',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(updateData)
      });
      
      console.log('📥 PUT Response status:', response.status, response.statusText);
      
      if (!response.ok) {
        const errorText = await response.text();
        console.error('❌ PUT Error response:', errorText);
        throw new Error(`HTTP ${response.status}: ${errorText}`);
      }
      
      const data = await response.json();
      console.log('✅ PUT Success data:', data);
      return data;
    } catch (error) {
      console.error('Error updating business section 3:', error);
      throw new Error('Network error. Please check your connection and try again.');
    }
  }

  // Fetch business types
  static async getBusinessTypes() {
    try {
      const response = await fetch(`${API_ENDPOINTS.BASE_URL}/business/fetch-types/`, {
        method: 'GET',
        headers: {
          'Content-Type': 'application/json',
        }
      });
      
      const data = await response.json();
      return data;
    } catch (error) {
      console.error('Error fetching business types:', error);
      throw new Error('Network error. Please check your connection and try again.');
    }
  }

  // Fetch business features
  static async getBusinessFeatures() {
    try {
      const response = await fetch(`${API_ENDPOINTS.BASE_URL}/business/business-features/`, {
        method: 'GET',
        headers: {
          'Content-Type': 'application/json',
        }
      });
      
      const data = await response.json();
      return data;
    } catch (error) {
      console.error('Error fetching business features:', error);
      throw new Error('Network error. Please check your connection and try again.');
    }
  }

  // Open payment gateway
  static async openPaymentGateway(businessId, amount = 2999) {
    try {
      const userData = AuthService.getUserData();
      if (!userData || !userData.user_id) {
        throw new Error('User not authenticated');
      }

      const url = `${API_ENDPOINTS.BASE_URL}/business/payment-gateway/?userID=${userData.user_id}&amount=${amount}&business_id=${businessId}`;
      
      // Open payment gateway in new window/tab
      window.open(url, '_blank', 'width=800,height=600,scrollbars=yes,resizable=yes');
      
      return { success: true, message: 'Payment gateway opened' };
    } catch (error) {
      console.error('Error opening payment gateway:', error);
      throw new Error('Failed to open payment gateway');
    }
  }

  // Store business data locally for form persistence
  static storeDraftData(step, formData) {
    try {
      const userData = AuthService.getUserData();
      if (!userData || !userData.user_id) return;

      const draftKey = `kirazee_business_draft_${userData.user_id}`;
      const existingDraft = JSON.parse(localStorage.getItem(draftKey) || '{}');
      
      existingDraft[`section${step}`] = formData;
      existingDraft.lastUpdated = new Date().toISOString();
      
      localStorage.setItem(draftKey, JSON.stringify(existingDraft));
    } catch (error) {
      console.error('Error storing draft data:', error);
    }
  }

  // Get locally stored draft data
  static getDraftData() {
    try {
      const userData = AuthService.getUserData();
      if (!userData || !userData.user_id) return null;

      const draftKey = `kirazee_business_draft_${userData.user_id}`;
      const draftData = localStorage.getItem(draftKey);
      
      return draftData ? JSON.parse(draftData) : null;
    } catch (error) {
      console.error('Error retrieving draft data:', error);
      return null;
    }
  }

  // Clear local draft data (after successful submission)
  static clearDraftData() {
    try {
      const userData = AuthService.getUserData();
      if (!userData || !userData.user_id) return;

      const draftKey = `kirazee_business_draft_${userData.user_id}`;
      localStorage.removeItem(draftKey);
    } catch (error) {
      console.error('Error clearing draft data:', error);
    }
  }
}
