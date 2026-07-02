import { storeApi } from './api';

/**
 * Service for handling product-related API calls
 */

/**
 * Fetches products from the API
 * @param {string} businessId - The ID of the business
 * @returns {Promise<Array>} - A promise that resolves to an array of products
 */

/**
 * Fetches paginated products for a specific store
 * @param {string} businessId - The ID of the business
 * @param {string} businessType - The type of business (e.g., 'R01' for Grocery, 'R02' for Restaurant)
 * @param {number} page - The page number to fetch (1-based index)
 * @param {number} pageSize - Number of items per page
 * @returns {Promise<{items: Array, pagination: Object}>} Object containing products and pagination info
 */
export const fetchStoreProducts = async (businessId, businessType = 'R01', page = 1, pageSize = 10) => {
  try {
    if (!businessId || typeof businessId !== 'string' || businessId.trim() === '') {
      console.warn('fetchStoreProducts: businessId is missing or invalid:', businessId);
      return { items: [], pagination: { currentPage: 1, totalPages: 1, totalItems: 0, pageSize } };
    }

    console.log(`Fetching products for businessId: ${businessId}, page: ${page}, pageSize: ${pageSize}`);
    
    // Make the API call with pagination parameters
    const response = await storeApi.getItemsByBusiness(businessId, businessType, page, pageSize);
    
    console.log('API response for products:', {
      itemsCount: response.items?.length || 0,
      pagination: response.pagination
    });
    
    // Transform items to a consistent format
    const transformProductItem = (item) => ({
      id: item.id?.toString() || item.item_id?.toString() || '',
      item_id: item.id?.toString() || item.item_id?.toString() || '',
      name: item.item_name || item.name || 'Unnamed Item',
      item_name: item.item_name || item.name || 'Unnamed Item',
      description: item.description || item.item_description || '',
      price: parseFloat(item.selling_price || item.price || 0),
      selling_price: parseFloat(item.selling_price || item.price || 0),
      original_price: parseFloat(item.original_cost || item.mrp || item.selling_price || item.price || 0),
      item_image: item.item_image || item.image_url || null,
      stock: parseInt(item.stock_quantity || item.stock || item.quantity || 0, 10),
      rating: parseFloat(item.rating || 0),
      rating_count: parseInt(item.rating_count || 0, 10),
      store_name: response.business?.businessName || item.business_name || item.store_name || '',
      category: item.item_category || item.category_name || item.category || 'Uncategorized',
      mrp: parseFloat(item.mrp || item.original_cost || item.selling_price || item.price || 0),
      quantity: parseInt(item.quantity || 1, 10),
      // Additional fields
      weight: item.weight,
      unit: item.unit,
      item_type: item.item_type
    });

    // Transform all items in the response
    const items = Array.isArray(response.items) 
      ? response.items.map(transformProductItem)
      : [];
    
    // Calculate totalPages based on totalItems and pageSize if not provided by the API
    const totalItems = response.pagination?.totalItems || items.length;
    const apiPageSize = response.pagination?.pageSize || pageSize;
    const calculatedTotalPages = Math.ceil(totalItems / apiPageSize);
    
    // Use the API's totalPages if provided and valid, otherwise use our calculated value
    const totalPages = (response.pagination?.totalPages && response.pagination.totalPages > 0)
      ? response.pagination.totalPages
      : calculatedTotalPages;
    
    console.log('Pagination data:', {
      fromAPI: response.pagination,
      calculated: { totalItems, pageSize: apiPageSize, totalPages: calculatedTotalPages },
      usingTotalPages: totalPages
    });
    
    return {
      items,
      pagination: {
        currentPage: response.pagination?.currentPage || page,
        totalPages: totalPages,
        totalItems: totalItems,
        pageSize: apiPageSize,
        hasNextPage: response.pagination?.hasNextPage || (page < totalPages)
      }
    };
  } catch (error) {
    console.error('Error in fetchStoreProducts:', error);
    // Return empty result with error state
    return {
      items: [],
      pagination: {
        currentPage: 1,
        totalPages: 1,
        totalItems: 0,
        pageSize: pageSize || 10,
        hasNextPage: false,
        error: error.message || 'Failed to fetch products'
      }
    };
  }
}

/**
 * Fetches a single product by ID
 * @param {string} productId - The ID of the product to fetch
 * @returns {Promise<Object>} - A promise that resolves to the product data
 */
export const fetchProductById = async (productId) => {
  // Simulate API delay
  await new Promise(resolve => setTimeout(resolve, 300));
  
  try {
    const product = mockProducts.find(p => p.item_id === productId);
    
    if (!product) {
      throw new Error('Product not found');
    }
    
    return {
      id: product.item_id,
      item_id: product.item_id,
      name: product.item_name,
      item_name: product.item_name,
      description: product.item_description || '',
      price: product.selling_price,
      selling_price: product.selling_price,
      original_price: product.mrp || product.selling_price,
      item_image: product.item_image,
      stock: product.stock_quantity || 0,
      rating: product.rating || 0,
      store_name: product.business_name || 'Mock Store',
      category: product.category_name || 'Uncategorized',
    };
  } catch (error) {
    console.error('Error with mock product:', error);
    throw error;
  }
};

/**
 * Searches for products by query
 * @param {string} query - The search query
 * @param {string} [businessId] - Optional business ID to filter by (unused in mock)
 * @returns {Promise<Array>} - A promise that resolves to an array of matching products
 */
export const searchProducts = async (query, businessId = '') => {
  // Simulate API delay
  await new Promise(resolve => setTimeout(resolve, 300));
  
  try {
    if (!query) {
      return [];
    }
    
    const searchTerm = query.toLowerCase();
    
    return mockProducts
      .filter(product => 
        product.item_name.toLowerCase().includes(searchTerm) ||
        (product.item_description && product.item_description.toLowerCase().includes(searchTerm))
      )
      .map(item => ({
        id: item.item_id,
        item_id: item.item_id,
        name: item.item_name,
        item_name: item.item_name,
        description: item.item_description || '',
        price: item.selling_price,
        selling_price: item.selling_price,
        original_price: item.mrp || item.selling_price,
        item_image: item.item_image,
        stock: item.stock_quantity || 0,
        rating: item.rating || 0,
        store_name: item.business_name || 'Mock Store',
        category: item.category_name || 'Uncategorized',
      }));
  } catch (error) {
    console.error('Error with mock search:', error);
    throw error;
  }
};

export default {
  fetchStoreProducts,
  fetchProductById,
  searchProducts
}