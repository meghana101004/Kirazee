import React, { useState, useEffect } from 'react';
import AdminService from '../../../services/adminService';
import { fetchStoreProducts } from '../../../services/productService';
import { 
  FaStore, FaSearch, FaFilter, FaPlus, FaEdit, FaTrash, 
  FaEye, FaSpinner, FaImage, FaStar, FaBox 
} from 'react-icons/fa';
import { MdRefresh } from 'react-icons/md';

const ProductsSection = () => {
  const [businesses, setBusinesses] = useState([]);
  const [selectedBusiness, setSelectedBusiness] = useState(null);
  const [products, setProducts] = useState([]);
  const [filteredProducts, setFilteredProducts] = useState([]);
  const [loading, setLoading] = useState(true);
  const [productsLoading, setProductsLoading] = useState(false);
  const [error, setError] = useState(null);
  const [searchQuery, setSearchQuery] = useState('');
  const [categoryFilter, setCategoryFilter] = useState('all');
  const [stockFilter, setStockFilter] = useState('all');
  const [selectedProduct, setSelectedProduct] = useState(null);
  const [showProductDetails, setShowProductDetails] = useState(false);
  const [categories, setCategories] = useState([]);
  const [businessTypeFilter, setBusinessTypeFilter] = useState('all');
  const [businessTypes, setBusinessTypes] = useState([]);
  const [pagination, setPagination] = useState({
    currentPage: 1,
    totalPages: 1,
    pageSize: 20
  });

  useEffect(() => {
    fetchBusinesses();
  }, []);

  useEffect(() => {
    if (selectedBusiness) {
      fetchProducts(selectedBusiness.id, pagination.currentPage);
    }
  }, [selectedBusiness, pagination.currentPage]);

  useEffect(() => {
    filterProducts();
  }, [products, searchQuery, categoryFilter, stockFilter]);

  const fetchBusinesses = async () => {
    try {
      setLoading(true);
      setError(null);
      
      const response = await AdminService.getBusinessesComprehensive({ limit: 100 });
      
      if (response && response.success) {
        const businessList = response.businesses || [];
        // Map business_id to id for compatibility
        const mappedBusinesses = businessList.map(b => ({
          ...b,
          id: b.business_id,
          business_name: b.businessName,
          name: b.businessName
        }));
        
        setBusinesses(mappedBusinesses);
        
        // Extract unique business types
        const types = [...new Set(mappedBusinesses.map(b => b.business_type_name || b.businessType).filter(Boolean))];
        setBusinessTypes(types);
        
        // Auto-select first business
        if (mappedBusinesses.length > 0) {
          setSelectedBusiness(mappedBusinesses[0]);
        }
      } else {
        throw new Error(response.message || 'Failed to fetch businesses');
      }
    } catch (error) {
      console.error('Error fetching businesses:', error);
      setError('Failed to load businesses');
    } finally {
      setLoading(false);
    }
  };

  const fetchProducts = async (businessId, page = 1) => {
    try {
      setProductsLoading(true);
      
      // Get the business to determine its type
      const business = businesses.find(b => b.id === businessId);
      const businessType = business?.business_type || business?.businessType || 'R01';
      
      // Map business types to API codes
      // R01 = Grocery, R02 = Restaurant, etc.
      const typeCode = businessType.includes('Grocery') || businessType.includes('grocery') ? 'R01' : 
                       businessType.includes('Restaurant') || businessType.includes('restaurant') ? 'R02' : 
                       businessType;
      
      console.log('Fetching products for business:', {
        businessId,
        businessType,
        typeCode,
        page
      });
      
      const response = await fetchStoreProducts(businessId, typeCode, page, pagination.pageSize);
      
      if (response && response.items) {
        // Fix image URLs - backend returns URLs with double /media/ path
        // Example: /kirazee/media/media/menuItems/image.png
        // We need: https://kirazee.com/kirazee/media/menuItems/image.png
        const productsWithFixedImages = response.items.map(product => {
          let imageUrl = product.item_image;
          
          console.log('Original image URL:', imageUrl);
          
          if (imageUrl) {
            // If it's a relative URL, add the backend base URL
            if (!imageUrl.startsWith('http')) {
              // Fix double /media/ issue
              imageUrl = imageUrl.replace('/media/media/', '/media/');
              // Add backend base URL
              imageUrl = `https://kirazee.com${imageUrl.startsWith('/') ? '' : '/'}${imageUrl}`;
            }
          }
          
          console.log('Fixed image URL:', imageUrl);
          
          return {
            ...product,
            item_image: imageUrl
          };
        });
        
        setProducts(productsWithFixedImages);
        setPagination(prev => ({
          ...prev,
          currentPage: response.pagination?.currentPage || page,
          totalPages: response.pagination?.totalPages || 1,
          totalItems: response.pagination?.totalItems || response.items.length
        }));
        
        // Extract unique categories
        const uniqueCategories = [...new Set(productsWithFixedImages.map(p => p.category).filter(Boolean))];
        setCategories(uniqueCategories);
      }
    } catch (error) {
      console.error('Error fetching products:', error);
      setProducts([]);
    } finally {
      setProductsLoading(false);
    }
  };

  const filterProducts = () => {
    let filtered = [...products];

    // Filter by category
    if (categoryFilter !== 'all') {
      filtered = filtered.filter(product => product.category === categoryFilter);
    }

    // Filter by stock
    if (stockFilter === 'in-stock') {
      filtered = filtered.filter(product => product.stock > 0);
    } else if (stockFilter === 'out-of-stock') {
      filtered = filtered.filter(product => product.stock === 0);
    } else if (stockFilter === 'low-stock') {
      filtered = filtered.filter(product => product.stock > 0 && product.stock < 10);
    }

    // Filter by search query
    if (searchQuery) {
      const query = searchQuery.toLowerCase();
      filtered = filtered.filter(product => 
        (product.name || '').toLowerCase().includes(query) ||
        (product.description || '').toLowerCase().includes(query) ||
        (product.category || '').toLowerCase().includes(query)
      );
    }

    setFilteredProducts(filtered);
  };

  const formatCurrency = (amount) => {
    return new Intl.NumberFormat('en-IN', {
      style: 'currency',
      currency: 'INR',
      maximumFractionDigits: 0
    }).format(amount || 0);
  };

  const getStockStatus = (stock) => {
    if (stock === 0) return { label: 'Out of Stock', class: 'stock-out' };
    if (stock < 10) return { label: 'Low Stock', class: 'stock-low' };
    return { label: 'In Stock', class: 'stock-in' };
  };

  if (loading) {
    return (
      <div className="products-loading">
        <FaSpinner className="loading-spinner" />
        <p>Loading products...</p>
      </div>
    );
  }

  if (error) {
    return (
      <div className="products-error">
        <p>{error}</p>
        <button onClick={fetchBusinesses} className="retry-btn">
          <MdRefresh /> Retry
        </button>
      </div>
    );
  }

  return (
    <div className="products-section">
      {/* Header */}
      <div className="products-header">
        <div className="header-left">
          <h2>
            <FaStore /> Products Management
          </h2>
          <p>{filteredProducts.length} products found</p>
        </div>
        <div className="header-actions">
          <button onClick={() => selectedBusiness && fetchProducts(selectedBusiness.id)} className="refresh-btn">
            <MdRefresh /> Refresh
          </button>
        </div>
      </div>

      {/* Business Selector */}
      <div className="business-selector-section">
        <div className="business-type-filter">
          <label>Filter by Business Type:</label>
          <select 
            value={businessTypeFilter} 
            onChange={(e) => {
              setBusinessTypeFilter(e.target.value);
              // Reset to first business of selected type
              if (e.target.value === 'all') {
                setSelectedBusiness(businesses[0]);
              } else {
                const firstOfType = businesses.find(b => 
                  (b.business_type_name || b.businessType) === e.target.value
                );
                if (firstOfType) setSelectedBusiness(firstOfType);
              }
              setPagination(prev => ({ ...prev, currentPage: 1 }));
            }}
          >
            <option value="all">All Types</option>
            {businessTypes.map(type => (
              <option key={type} value={type}>{type}</option>
            ))}
          </select>
        </div>
        
        <div className="business-selector">
          <label>Select Business:</label>
          <select 
            value={selectedBusiness?.id || ''} 
            onChange={(e) => {
              const business = businesses.find(b => b.id === e.target.value);
              setSelectedBusiness(business);
              setPagination(prev => ({ ...prev, currentPage: 1 }));
            }}
          >
            {businesses
              .filter(b => businessTypeFilter === 'all' || 
                (b.business_type_name || b.businessType) === businessTypeFilter)
              .map(business => (
                <option key={business.id} value={business.id}>
                  {business.business_name || business.name} 
                  {business.business_type_name && ` (${business.business_type_name})`}
                </option>
              ))
            }
          </select>
          
          {selectedBusiness && (
            <div className="business-info">
              <span className="business-type-badge">
                {selectedBusiness.business_type_name || selectedBusiness.businessType || 'Unknown Type'}
              </span>
              <span className="business-location">
                {selectedBusiness.city || selectedBusiness.location || 'Location N/A'}
              </span>
            </div>
          )}
        </div>
      </div>

      {/* Filters */}
      <div className="products-filters">
        <div className="search-box">
          <FaSearch />
          <input
            type="text"
            placeholder="Search products by name, description, or category..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
          />
        </div>

        <div className="filter-group">
          <label>Category:</label>
          <select value={categoryFilter} onChange={(e) => setCategoryFilter(e.target.value)}>
            <option value="all">All Categories</option>
            {categories.map(category => (
              <option key={category} value={category}>{category}</option>
            ))}
          </select>
        </div>

        <div className="filter-group">
          <label>Stock:</label>
          <select value={stockFilter} onChange={(e) => setStockFilter(e.target.value)}>
            <option value="all">All Stock</option>
            <option value="in-stock">In Stock</option>
            <option value="low-stock">Low Stock</option>
            <option value="out-of-stock">Out of Stock</option>
          </select>
        </div>
      </div>

      {/* Products Grid */}
      {productsLoading ? (
        <div className="products-loading">
          <FaSpinner className="loading-spinner" />
          <p>Loading products...</p>
        </div>
      ) : (
        <>
          <div className="products-grid">
            {filteredProducts.length === 0 ? (
              <div className="no-products">
                <FaBox />
                <p>No products found</p>
              </div>
            ) : (
              filteredProducts.map((product, index) => {
                const stockStatus = getStockStatus(product.stock);
                const productKey = product.id || product.item_id || `product-${index}`;
                return (
                  <div key={productKey} className="product-card">
                    <div className="product-image">
                      {product.item_image ? (
                        <img 
                          src={product.item_image} 
                          alt=""
                          onError={(e) => {
                            // If image fails to load, hide it and show no-image placeholder
                            e.target.style.display = 'none';
                            e.target.nextElementSibling?.classList.add('show-placeholder');
                          }}
                        />
                      ) : null}
                      <div className="no-image" style={{ display: product.item_image ? 'none' : 'flex' }}>
                        <FaImage />
                      </div>
                      <span className={`stock-badge ${stockStatus.class}`}>
                        {stockStatus.label}
                      </span>
                    </div>
                    
                    <div className="product-info">
                      <h3 className="product-name">{product.name}</h3>
                      <p className="product-category">{product.category}</p>
                      
                      <div className="product-rating">
                        <FaStar className="star-icon" />
                        <span>{product.rating?.toFixed(1) || '0.0'}</span>
                        <span className="rating-count">({product.rating_count || 0})</span>
                      </div>
                      
                      <div className="product-pricing">
                        <span className="current-price">{formatCurrency(product.price)}</span>
                        {product.original_price > product.price && (
                          <span className="original-price">{formatCurrency(product.original_price)}</span>
                        )}
                      </div>
                      
                      <div className="product-stock">
                        <FaBox />
                        <span>Stock: {product.stock}</span>
                      </div>
                      
                      <div className="product-actions">
                        <button
                          className="action-btn view-btn"
                          onClick={() => {
                            setSelectedProduct(product);
                            setShowProductDetails(true);
                          }}
                        >
                          <FaEye /> View
                        </button>
                      </div>
                    </div>
                  </div>
                );
              })
            )}
          </div>

          {/* Pagination */}
          {pagination.totalPages > 1 && (
            <div className="pagination">
              <button
                className="page-btn"
                disabled={pagination.currentPage === 1}
                onClick={() => setPagination(prev => ({ ...prev, currentPage: prev.currentPage - 1 }))}
              >
                Previous
              </button>
              
              <span className="page-info">
                Page {pagination.currentPage} of {pagination.totalPages}
              </span>
              
              <button
                className="page-btn"
                disabled={pagination.currentPage === pagination.totalPages}
                onClick={() => setPagination(prev => ({ ...prev, currentPage: prev.currentPage + 1 }))}
              >
                Next
              </button>
            </div>
          )}
        </>
      )}

      {/* Product Details Modal */}
      {showProductDetails && selectedProduct && (
        <div className="modal-overlay" onClick={() => setShowProductDetails(false)}>
          <div className="modal-content product-details-modal" onClick={(e) => e.stopPropagation()}>
            <div className="modal-header">
              <h3>Product Details</h3>
              <button className="close-btn" onClick={() => setShowProductDetails(false)}>
                ×
              </button>
            </div>
            <div className="modal-body">
              <div className="product-detail-content">
                <div className="product-detail-image">
                  {selectedProduct.item_image ? (
                    <img src={selectedProduct.item_image} alt={selectedProduct.name} />
                  ) : (
                    <div className="no-image-large">
                      <FaImage />
                    </div>
                  )}
                </div>
                
                <div className="product-detail-info">
                  <h2>{selectedProduct.name}</h2>
                  <p className="product-detail-category">{selectedProduct.category}</p>
                  
                  <div className="product-detail-rating">
                    <FaStar className="star-icon" />
                    <span>{selectedProduct.rating?.toFixed(1) || '0.0'}</span>
                    <span className="rating-count">({selectedProduct.rating_count || 0} reviews)</span>
                  </div>
                  
                  <div className="product-detail-pricing">
                    <span className="current-price">{formatCurrency(selectedProduct.price)}</span>
                    {selectedProduct.original_price > selectedProduct.price && (
                      <>
                        <span className="original-price">{formatCurrency(selectedProduct.original_price)}</span>
                        <span className="discount">
                          {Math.round(((selectedProduct.original_price - selectedProduct.price) / selectedProduct.original_price) * 100)}% OFF
                        </span>
                      </>
                    )}
                  </div>
                  
                  <div className="product-detail-description">
                    <h4>Description</h4>
                    <p>{selectedProduct.description || 'No description available'}</p>
                  </div>
                  
                  <div className="product-detail-specs">
                    <div className="spec-item">
                      <span className="spec-label">Stock:</span>
                      <span className={`spec-value ${getStockStatus(selectedProduct.stock).class}`}>
                        {selectedProduct.stock} units
                      </span>
                    </div>
                    
                    {selectedProduct.weight && (
                      <div className="spec-item">
                        <span className="spec-label">Weight:</span>
                        <span className="spec-value">{selectedProduct.weight} {selectedProduct.unit || 'g'}</span>
                      </div>
                    )}
                    
                    <div className="spec-item">
                      <span className="spec-label">Business:</span>
                      <span className="spec-value">{selectedProduct.store_name || selectedBusiness?.business_name}</span>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default ProductsSection;
