// Google Maps URL Parser Utility
// Parses Google Maps URLs to extract address components and coordinates

export const parseGoogleMapsUrl = (mapsUrl) => {
  try {
    if (!mapsUrl || typeof mapsUrl !== 'string') {
      return null;
    }

    // Clean the URL
    const cleanUrl = mapsUrl.trim();
    
    // Extract coordinates from various Google Maps URL formats
    const patterns = [
      // Pattern 1: @lat,lng,zoom (most common)
      /@([-+]?[0-9]*\.?[0-9]+),([-+]?[0-9]*\.?[0-9]+)/,
      // Pattern 2: !3d and !4d (newer format)
      /!3d([-+]?[0-9]*\.?[0-9]+).*!4d([-+]?[0-9]*\.?[0-9]+)/,
      // Pattern 3: ll=lat,lng
      /ll=([-+]?[0-9]*\.?[0-9]+),([-+]?[0-9]*\.?[0-9]+)/,
      // Pattern 4: center=lat,lng
      /center=([-+]?[0-9]*\.?[0-9]+),([-+]?[0-9]*\.?[0-9]+)/,
    ];

    let latitude = null;
    let longitude = null;

    // Try to extract coordinates using different patterns
    for (const pattern of patterns) {
      const match = cleanUrl.match(pattern);
      if (match) {
        latitude = parseFloat(match[1]);
        longitude = parseFloat(match[2]);
        break;
      }
    }

    if (latitude === null || longitude === null) {
      console.warn('Could not extract coordinates from Google Maps URL');
      return null;
    }

    // Validate coordinate ranges
    if (latitude < -90 || latitude > 90 || longitude < -180 || longitude > 180) {
      console.warn('Invalid coordinate values');
      return null;
    }

    return {
      latitude,
      longitude,
      success: true,
      message: 'Coordinates extracted successfully'
    };

  } catch (error) {
    console.error('Error parsing Google Maps URL:', error);
    return null;
  }
};

// Parse Google Maps URL using backend API
export const parseMapsUrlWithBackend = async (mapsUrl) => {
  try {
    // Get the API base URL from config or use relative path
    const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || '';
    const response = await fetch(`${API_BASE_URL}/business/parse-address/`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        maps_url: mapsUrl
      })
    });

    if (!response.ok) {
      // Handle 404 specifically
      if (response.status === 404) {
        throw new Error('Backend API endpoint not available');
      }
      
      let errorMessage = 'Failed to parse address';
      try {
        const error = await response.json();
        errorMessage = error.error || errorMessage;
      } catch (e) {
        // If response is not JSON, use status text
        errorMessage = response.statusText || errorMessage;
      }
      throw new Error(errorMessage);
    }

    const data = await response.json();
    return {
      success: true,
      data: {
        address: data.address || '',
        city: data.city || '',
        state: data.state || '',
        pincode: data.pincode || '',
        country: data.country || '',
        latitude: data.latitude || null,
        longitude: data.longitude || null,
        formatted_address: data.formatted_address || ''
      }
    };

  } catch (error) {
    console.error('Error parsing maps URL with backend:', error);
    return {
      success: false,
      message: error.message || 'Failed to parse address'
    };
  }
};

// Main function to parse Google Maps URL and get address details
export const parseMapsUrlAndGetAddress = async (mapsUrl) => {
  try {
    // Use backend API for parsing
    const result = await parseMapsUrlWithBackend(mapsUrl);
    
    if (result.success) {
      return {
        success: true,
        message: 'Address parsed successfully',
        data: result.data
      };
    } else {
      // Fallback to frontend parsing if backend fails
      console.warn('Backend parsing failed, trying frontend fallback:', result.message);
      
      const coords = parseGoogleMapsUrl(mapsUrl);
      if (!coords) {
        return {
          success: false,
          message: 'Could not extract coordinates from the Google Maps URL'
        };
      }

      // Try frontend reverse geocoding as fallback
      try {
        const addressData = await reverseGeocodeFallback(coords.latitude, coords.longitude);
        if (addressData) {
          return {
            success: true,
            message: 'Address parsed successfully (using fallback)',
            data: addressData
          };
        }
      } catch (error) {
        console.warn('Fallback reverse geocoding failed:', error);
      }

      // If all else fails, return just coordinates
      return {
        success: true,
        message: 'Coordinates extracted successfully. Please fill address details manually.',
        data: {
          formatted_address: `Coordinates: ${coords.latitude}, ${coords.longitude}`,
          latitude: coords.latitude,
          longitude: coords.longitude,
          address: '',
          city: '',
          state: '',
          pincode: '',
          country: ''
        }
      };
    }

  } catch (error) {
    console.error('Error parsing maps URL and getting address:', error);
    return {
      success: false,
      message: 'An error occurred while parsing the address'
    };
  }
};

// Fallback reverse geocoding using a CORS proxy or manual parsing
const reverseGeocodeFallback = async (latitude, longitude) => {
  try {
    // Try using a CORS proxy first
    const proxyUrl = 'https://api.allorigins.win/raw?url=';
    const targetUrl = `https://nominatim.openstreetmap.org/reverse?format=json&lat=${latitude}&lon=${longitude}&addressdetails=1`;
    
    const response = await fetch(proxyUrl + encodeURIComponent(targetUrl));
    
    if (!response.ok) {
      throw new Error('Reverse geocoding failed');
    }

    const data = await response.json();
    
    if (!data || !data.address) {
      return null;
    }

    const address = data.address;
    return {
      formatted_address: data.display_name || '',
      latitude: parseFloat(latitude),
      longitude: parseFloat(longitude),
      address: address.house_number && address.road ? 
        `${address.house_number} ${address.road}` : 
        (address.road || address.pedestrian || ''),
      city: address.city || address.town || address.village || address.hamlet || address.municipality || address.county || '',
      state: address.state || address.region || address.province || '',
      pincode: address.postcode || '',
      country: address.country || ''
    };

  } catch (error) {
    console.error('Error in fallback reverse geocoding:', error);
    
    // If all else fails, return basic coordinate info
    return {
      formatted_address: `Coordinates: ${latitude}, ${longitude}`,
      latitude: parseFloat(latitude),
      longitude: parseFloat(longitude),
      address: '',
      city: '',
      state: '',
      pincode: '',
      country: ''
    };
  }
};

// Validate Google Maps URL format
export const isValidGoogleMapsUrl = (url) => {
  if (!url || typeof url !== 'string') return false;
  
  const googleMapsPatterns = [
    /^https?:\/\/(www\.)?google\.com\/maps/,
    /^https?:\/\/maps\.google\.com/,
    /^https?:\/\/goo\.gl\/maps/,
    /^https?:\/\/maps\.app\.goo\.gl/,
  ];

  return googleMapsPatterns.some(pattern => pattern.test(url.trim()));
};
