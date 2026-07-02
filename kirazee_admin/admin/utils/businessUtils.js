/**
 * Business utility functions for loading business data
 */

import { AuthService } from '../services/authService';

console.log('businessUtils.js loaded successfully');

// Global function to load business data into profile form
window.loadBusinessData = async function() {
  console.log('loadBusinessData called - START');
  
  try {
    console.log('Step 1: Attempting API call via AuthService import...');
    
    // First try to fetch fresh user-comprehensive details from API
    try {
      console.log('Step 2: Calling getUserComprehensiveDetails...');
      const data = await AuthService.getUserComprehensiveDetails();
      console.log('API response:', data);
      
      if (data && data.user_details) {
        console.log('API response received, extracting business data...');
        const businessDetails = extractBusinessDetailsFromAPI(data);
        const profileDetails = extractProfileDetailsFromAPI(data);
        
        // Store the actual business details in localStorage
        localStorage.setItem('businessDetailsData', JSON.stringify(businessDetails));
        
        // Store profile data in localStorage for form population
        localStorage.setItem('businessProfileData', JSON.stringify(profileDetails));
        
        console.log('Business data loaded successfully');
        console.log('Navigating to business page...');
        window.location.href = '/#/account/business';
        return;
      } else {
        console.warn('API response missing user_details:', data);
      }
    } catch (apiError) {
      console.warn('API call failed, falling back to localStorage:', apiError);
    }
    
    // Fallback to localStorage if API fails
    console.log('Step 3: Falling back to localStorage for business data...');
    const localStorageSuccess = loadBusinessDataFromLocalStorage();
    
    if (localStorageSuccess) {
      // Navigate to business page if not already there
      if (window.location.pathname !== '/account/business') {
        console.log('Navigating to business page after localStorage load...');
        window.location.href = '/#/account/business';
      }
    } else {
      // If no data available, still navigate to business page
      console.log('No business data found, navigating to business page anyway...');
      showNotification('No business data found. Please complete your business onboarding.', 'warning');
      if (window.location.pathname !== '/account/business') {
        window.location.href = '/#/account/business';
      }
    }
    
  } catch (error) {
    console.error('Error in loadBusinessData:', error);
    showNotification('Failed to load business data', 'error');
    
    // Still navigate to business page even on error
    if (window.location.pathname !== '/account/business') {
      window.location.href = '/#/account/business';
    }
  }
  
  console.log('loadBusinessData called - END');
};

// Function to extract actual business details from API response
function extractBusinessDetailsFromAPI(data) {
  const userBusiness = data.user_business || {};
  const userDetails = data.user_details || {};
  
  console.log('Extracting business details from:', { userBusiness, userDetails });
  
  const businessDetails = {
    businessName: userBusiness.businessName || '',
    businessType: userBusiness.businessType || '',
    businessCategory: userBusiness.businessCategory || '',
    gstin: userBusiness.gst_num || '',
    pan: '', // Not provided in backend data
    businessEmail: userBusiness.businessEmail || userDetails.emailID || '',
    businessPhone: userBusiness.businessNumber || userBusiness.contact_mobile || userDetails.mobileNumber || '',
    businessAddress: userBusiness.address || '',
    website: userBusiness.website_url || '',
    description: userBusiness.description || '',
    fssaiNumber: userBusiness.business_licence || '',
    ifscCode: '', // Not provided in backend data
    accountNumber: '', // Not provided in backend data
    bankName: '', // Not provided in backend data
    razorpayKeyId: '', // Not provided in backend data
    razorpayKeySecret: '' // Not provided in backend data
  };
  
  console.log('Extracted business details:', businessDetails);
  
  return businessDetails;
}

// Function to extract profile details from API response for form population
function extractProfileDetailsFromAPI(data) {
  const userDetails = data.user_details || {};
  const userBusiness = data.user_business || {};
  
  const profileDetails = {
    firstName: userDetails.firstName || '',
    lastName: userDetails.lastName || '',
    phone: userDetails.mobileNumber || userBusiness.businessNumber || '',
    email: userDetails.emailID || userBusiness.businessEmail || '',
    addressHome: userBusiness.address || '',
    addressOffice: '',
    addressOther: '',
    avatarUrl: userDetails.profileUrl || ''
  };
  
  console.log('Extracted profile details:', profileDetails);
  
  return profileDetails;
}

// Function to load business data from localStorage
function loadBusinessDataFromLocalStorage() {
  console.log('Loading business data from localStorage...');
  console.log('Available localStorage keys:', Object.keys(localStorage));
  
  // Try to get business data from localStorage
  const businessData = localStorage.getItem('businessFormData');
  
  if (businessData) {
    console.log('Found businessFormData in localStorage');
    const parsedBusinessData = JSON.parse(businessData);
    
    // Extract actual business details from form data
    const businessDetails = {
      businessName: parsedBusinessData.form2?.businessName || '',
      businessType: parsedBusinessData.form1?.businessType || '',
      businessCategory: parsedBusinessData.form1?.businessCategory || '',
      gstin: parsedBusinessData.form2?.gstin || '',
      pan: parsedBusinessData.form2?.pan || '',
      businessEmail: parsedBusinessData.form2?.businessEmail || '',
      businessPhone: parsedBusinessData.form2?.businessNumber || parsedBusinessData.form3?.contact_mobile || '',
      businessAddress: parsedBusinessData.form3?.address || '',
      website: parsedBusinessData.form2?.website || '',
      description: parsedBusinessData.form1?.description || '',
      fssaiNumber: parsedBusinessData.form2?.fssaiNumber || '',
      ifscCode: parsedBusinessData.form3?.ifscCode || '',
      accountNumber: parsedBusinessData.form3?.accountNumber || '',
      bankName: parsedBusinessData.form3?.bankName || '',
      razorpayKeyId: parsedBusinessData.form3?.razorpayKeyId || '',
      razorpayKeySecret: parsedBusinessData.form3?.razorpayKeySecret || ''
    };
    
    // Store the actual business details in localStorage
    localStorage.setItem('businessDetailsData', JSON.stringify(businessDetails));
    
    showNotification('Business details loaded successfully from local storage');
    return true;
  } else {
    console.log('businessFormData not found, trying alternative keys...');
    // Try alternative localStorage keys
    const alternativeKeys = [
      'form1Data',
      'form2Data', 
      'form3Data',
      'businessOnboardingData',
      'kirazeeBusinessData',
      'user_business'
    ];
    
    let foundData = null;
    let foundKey = null;
    for (const key of alternativeKeys) {
      const data = localStorage.getItem(key);
      if (data) {
        try {
          foundData = JSON.parse(data);
          foundKey = key;
          console.log(`Found data in key: ${key}`, foundData);
          break;
        } catch (error) {
          console.error(`Error parsing data from key ${key}:`, error);
        }
      }
    }
    
    if (foundData) {
      console.log(`Found business data in localStorage key: ${foundKey}`);
      // Handle different data structures
      const businessDetails = {
        businessName: foundData.businessName || foundData.form2?.businessName || '',
        businessType: foundData.businessType || foundData.form1?.businessType || '',
        businessCategory: foundData.businessCategory || foundData.form1?.businessCategory || '',
        gstin: foundData.gstin || foundData.gst_num || foundData.form2?.gstin || '',
        pan: foundData.pan || foundData.form2?.pan || '',
        businessEmail: foundData.businessEmail || foundData.form2?.businessEmail || '',
        businessPhone: foundData.businessPhone || foundData.businessNumber || foundData.form2?.businessNumber || foundData.contact_mobile || '',
        businessAddress: foundData.businessAddress || foundData.address || foundData.form3?.address || '',
        website: foundData.website || foundData.website_url || foundData.form2?.website || '',
        description: foundData.description || foundData.form1?.description || '',
        fssaiNumber: foundData.fssaiNumber || foundData.business_licence || foundData.form2?.fssaiNumber || '',
        ifscCode: foundData.ifscCode || foundData.form3?.ifscCode || '',
        accountNumber: foundData.accountNumber || foundData.form3?.accountNumber || '',
        bankName: foundData.bankName || foundData.form3?.bankName || '',
        razorpayKeyId: foundData.razorpayKeyId || foundData.form3?.razorpayKeyId || '',
        razorpayKeySecret: foundData.razorpayKeySecret || foundData.form3?.razorpayKeySecret || ''
      };
      
      // Store the actual business details in localStorage
      localStorage.setItem('businessDetailsData', JSON.stringify(businessDetails));
      
      showNotification('Business details loaded successfully from local storage');
      return true;
    } else {
      console.log('No business data found in any localStorage keys');
      
      // Create sample business data for testing
      console.log('Creating sample business data for testing...');
      const sampleBusinessData = {
        businessName: 'Sample Business',
        businessType: 'Restaurant',
        businessCategory: 'Food & Beverage',
        gstin: '29ABCDE1234F1Z5',
        pan: 'ABCDE1234F',
        businessEmail: 'business@example.com',
        businessPhone: '+91 9876543210',
        businessAddress: '123 Business Street, City, State - 123456',
        website: 'https://samplebusiness.com',
        description: 'A sample restaurant business for demonstration purposes',
        fssaiNumber: '12345678901234',
        ifscCode: 'HDFC0000123',
        accountNumber: '12345678901234',
        bankName: 'HDFC Bank',
        razorpayKeyId: 'rzp_test_1234567890',
        razorpayKeySecret: 'rzp_test_secret_1234567890'
      };
      
      localStorage.setItem('businessDetailsData', JSON.stringify(sampleBusinessData));
      showNotification('Sample business data created for testing', 'warning');
      return true;
    }
  }
}

// Helper function to show notifications
function showNotification(message, type = 'success') {
  if (window.showToast) {
    window.showToast(message, type)
  }
}

// Export function for use in React components
export const loadBusinessDetails = async function() {
  console.log('loadBusinessDetails called - START');
  
  try {
    // First try to get business data from localStorage
    const businessDetailsData = localStorage.getItem('businessDetailsData');
    
    if (businessDetailsData) {
      console.log('Found businessDetailsData in localStorage');
      const parsedData = JSON.parse(businessDetailsData);
      console.log('Business details loaded:', parsedData);
      return parsedData;
    }
    
    // If not found, try to load from other localStorage keys
    console.log('businessDetailsData not found, trying alternative keys...');
    const alternativeKeys = [
      'businessFormData',
      'form1Data',
      'form2Data', 
      'form3Data',
      'businessOnboardingData',
      'kirazeeBusinessData',
      'user_business'
    ];
    
    let foundData = null;
    let foundKey = null;
    for (const key of alternativeKeys) {
      const data = localStorage.getItem(key);
      if (data) {
        try {
          foundData = JSON.parse(data);
          foundKey = key;
          console.log(`Found data in key: ${key}`, foundData);
          break;
        } catch (error) {
          console.error(`Error parsing data from key ${key}:`, error);
        }
      }
    }
    
    if (foundData) {
      console.log(`Found business data in localStorage key: ${foundKey}`);
      // Handle different data structures
      const businessDetails = {
        businessName: foundData.businessName || foundData.form2?.businessName || '',
        businessType: foundData.businessType || foundData.form1?.businessType || '',
        businessCategory: foundData.businessCategory || foundData.form1?.businessCategory || '',
        gstin: foundData.gstin || foundData.gst_num || foundData.form2?.gstin || '',
        pan: foundData.pan || foundData.form2?.pan || '',
        businessEmail: foundData.businessEmail || foundData.form2?.businessEmail || '',
        businessPhone: foundData.businessPhone || foundData.businessNumber || foundData.form2?.businessNumber || foundData.contact_mobile || '',
        businessAddress: foundData.businessAddress || foundData.address || foundData.form3?.address || '',
        website: foundData.website || foundData.website_url || foundData.form2?.website || '',
        description: foundData.description || foundData.form1?.description || '',
        fssaiNumber: foundData.fssaiNumber || foundData.business_licence || foundData.form2?.fssaiNumber || '',
        ifscCode: foundData.ifscCode || foundData.form3?.ifscCode || '',
        accountNumber: foundData.accountNumber || foundData.form3?.accountNumber || '',
        bankName: foundData.bankName || foundData.form3?.bankName || '',
        razorpayKeyId: foundData.razorpayKeyId || foundData.form3?.razorpayKeyId || '',
        razorpayKeySecret: foundData.razorpayKeySecret || foundData.form3?.razorpayKeySecret || ''
      };
      
      // Store the actual business details in localStorage for future use
      localStorage.setItem('businessDetailsData', JSON.stringify(businessDetails));
      
      console.log('Business details extracted and stored:', businessDetails);
      return businessDetails;
    } else {
      console.log('No business data found in any localStorage keys');
      return null;
    }
  } catch (error) {
    console.error('Error in loadBusinessDetails:', error);
    return null;
  }
};

// Function to check if business data is available
window.hasBusinessData = function() {
  const keys = [
    'businessFormData',
    'form1Data',
    'form2Data', 
    'form3Data',
    'businessOnboardingData',
    'kirazeeBusinessData'
  ];
  
  return keys.some(key => localStorage.getItem(key) !== null);
};
