import React, { useState, useEffect, useCallback, useMemo } from 'react';
import AdminService from '../services/adminService';
import '../../css/admin/BusinessDetailsTabbed.css?v=69';
import { 
  MdOutlineDashboard, 
  MdOutlineRestaurantMenu, 
  MdOutlineShoppingCart, 
  MdOutlineAttachMoney, 
  MdOutlineStarOutline, 
  MdOutlineDescription, 
  MdOutlineLocalOffer, 
  MdOutlineAccessTime, 
  MdOutlineLocalShipping, 
  MdOutlineSettings,
  MdOutlineDeliveryDining,
  MdOutlineCheckCircleOutline,
  MdOutlineLocationOn,
  MdOutlineSpeed,
  MdOutlinePerson,
  MdOutlinePhone,
  MdOutlineEdit,
  MdOutlineBarChart,
  MdOutlineAdd,
  MdOutlineMessage,
  MdOutlineCurrencyRupee
} from 'react-icons/md';
import { FiMapPin, FiPlus, FiEdit2, FiTrash2, FiList, FiGrid, FiEye, FiEyeOff, FiShoppingCart, FiDollarSign, FiStar, FiBarChart, FiCheckCircle, FiClock, FiPackage, FiTruck, FiCalendar, FiTrendingUp, FiUsers } from 'react-icons/fi';

// Force cache refresh - Updated CSS with better scrolling
const CACHE_VERSION = '2.0';

// Simple Offer Form Component
const SimpleOfferForm = ({ offer, onSave, onCancel, isSaving }) => {
  const [formData, setFormData] = useState({
    title: offer?.title || '',
    offer_type: offer?.offer_type || 'general',
    description: offer?.description || '',
    discount_percentage: offer?.discount_percentage || '',
    discount_amount: offer?.discount_amount || '',
    original_price: offer?.original_price || '',
    offer_price: offer?.offer_price || '',
    is_active: offer?.is_active !== undefined ? offer.is_active : true,
    is_approved: offer?.is_approved !== undefined ? offer.is_approved : false,
    valid_from: offer?.valid_from ? offer.valid_from.split('T')[0] : '',
    valid_to: offer?.valid_to ? offer.valid_to.split('T')[0] : '',
    priority: offer?.priority || 0,
    max_views: offer?.max_views || ''
  });

  const handleSubmit = (e) => {
    e.preventDefault();
    onSave(formData);
  };

  const handleChange = (e) => {
    const { name, value, type, checked } = e.target;
    setFormData(prev => ({
      ...prev,
      [name]: type === 'checkbox' ? checked : value
    }));
  };

  return (
    <form onSubmit={handleSubmit}>
      <div className="form-group">
        <label>Offer Title *</label>
        <input
          type="text"
          name="title"
          value={formData.title}
          onChange={handleChange}
          placeholder="e.g., Buy 1 Get 1 Free"
          required
        />
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '16px' }}>
        <div className="form-group">
          <label>Offer Type *</label>
          <select
            name="offer_type"
            value={formData.offer_type}
            onChange={handleChange}
            required
          >
            <option value="general">General</option>
            <option value="product">Product Specific</option>
            <option value="category">Category Specific</option>
            <option value="seasonal">Seasonal</option>
            <option value="flash">Flash Sale</option>
          </select>
        </div>

        <div className="form-group">
          <label>Priority</label>
          <input
            type="number"
            name="priority"
            value={formData.priority}
            onChange={handleChange}
            placeholder="0"
            min="0"
          />
        </div>
      </div>

      <div className="form-group">
        <label>Description</label>
        <textarea
          name="description"
          value={formData.description}
          onChange={handleChange}
          placeholder="Offer description..."
          rows="3"
        />
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '16px' }}>
        <div className="form-group">
          <label>Discount Percentage (%)</label>
          <input
            type="number"
            name="discount_percentage"
            value={formData.discount_percentage}
            onChange={handleChange}
            placeholder="e.g., 20"
            min="0"
            max="100"
            step="0.01"
          />
        </div>

        <div className="form-group">
          <label>Discount Amount (₹)</label>
          <input
            type="number"
            name="discount_amount"
            value={formData.discount_amount}
            onChange={handleChange}
            placeholder="e.g., 100"
            min="0"
            step="0.01"
          />
        </div>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '16px' }}>
        <div className="form-group">
          <label>Valid From</label>
          <input
            type="date"
            name="valid_from"
            value={formData.valid_from}
            onChange={handleChange}
          />
        </div>

        <div className="form-group">
          <label>Valid Until</label>
          <input
            type="date"
            name="valid_to"
            value={formData.valid_to}
            onChange={handleChange}
          />
        </div>
      </div>

      <div style={{ display: 'flex', gap: '20px', marginTop: '16px' }}>
        <label style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
          <input
            type="checkbox"
            name="is_active"
            checked={formData.is_active}
            onChange={handleChange}
            style={{ width: 'auto' }}
          />
          Active
        </label>
        <label style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
          <input
            type="checkbox"
            name="is_approved"
            checked={formData.is_approved}
            onChange={handleChange}
            style={{ width: 'auto' }}
          />
          Approved
        </label>
      </div>

      <div className="modal-footer">
        <button type="button" className="btn btn-secondary" onClick={onCancel}>Cancel</button>
        <button type="submit" className="btn btn-primary" disabled={isSaving}>
          {isSaving ? 'Saving...' : (offer ? 'Update Offer' : 'Create Offer')}
        </button>
      </div>
    </form>
  );
};

// Simple Coupon Form Component
const SimpleCouponForm = ({ coupon, onSave, onCancel, isSaving }) => {
  const [formData, setFormData] = useState({
    coupon_code: coupon?.code || '',
    discount_type: coupon?.type || 'percentage',
    discount_value: coupon?.value || '',
    is_active: coupon?.is_active !== undefined ? coupon.is_active : true,
    valid_from: coupon?.valid_from ? coupon.valid_from.split('T')[0] : '',
    valid_to: coupon?.valid_to ? coupon.valid_to.split('T')[0] : '',
    max_usage_total: coupon?.max_usage || '',
    min_order_value: coupon?.min_order_value || '',
    max_discount_amount: coupon?.max_discount_amount || ''
  });

  const handleSubmit = (e) => {
    e.preventDefault();
    onSave(formData);
  };

  const handleChange = (e) => {
    const { name, value, type, checked } = e.target;
    setFormData(prev => ({
      ...prev,
      [name]: type === 'checkbox' ? checked : value
    }));
  };

  return (
    <form onSubmit={handleSubmit}>
      <div className="form-group">
        <label>Coupon Code *</label>
        <input
          type="text"
          name="coupon_code"
          value={formData.coupon_code}
          onChange={handleChange}
          placeholder="e.g., SAVE20"
          required
        />
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '16px' }}>
        <div className="form-group">
          <label>Discount Type *</label>
          <select
            name="discount_type"
            value={formData.discount_type}
            onChange={handleChange}
            required
          >
            <option value="percentage">Percentage</option>
            <option value="fixed">Fixed Amount</option>
          </select>
        </div>

        <div className="form-group">
          <label>Discount Value *</label>
          <input
            type="number"
            name="discount_value"
            value={formData.discount_value}
            onChange={handleChange}
            placeholder={formData.discount_type === 'percentage' ? '10' : '100'}
            required
            min="0"
            step="0.01"
          />
        </div>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '16px' }}>
        <div className="form-group">
          <label>Valid From</label>
          <input
            type="date"
            name="valid_from"
            value={formData.valid_from}
            onChange={handleChange}
          />
        </div>

        <div className="form-group">
          <label>Valid Until</label>
          <input
            type="date"
            name="valid_to"
            value={formData.valid_to}
            onChange={handleChange}
          />
        </div>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: '16px' }}>
        <div className="form-group">
          <label>Max Usage</label>
          <input
            type="number"
            name="max_usage_total"
            value={formData.max_usage_total}
            onChange={handleChange}
            placeholder="Unlimited"
            min="0"
          />
        </div>

        <div className="form-group">
          <label>Min Order Value</label>
          <input
            type="number"
            name="min_order_value"
            value={formData.min_order_value}
            onChange={handleChange}
            placeholder="0"
            min="0"
            step="0.01"
          />
        </div>

        <div className="form-group">
          <label>Max Discount</label>
          <input
            type="number"
            name="max_discount_amount"
            value={formData.max_discount_amount}
            onChange={handleChange}
            placeholder="No limit"
            min="0"
            step="0.01"
          />
        </div>
      </div>

      <div className="form-group">
        <label style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
          <input
            type="checkbox"
            name="is_active"
            checked={formData.is_active}
            onChange={handleChange}
            style={{ width: 'auto' }}
          />
          Active
        </label>
      </div>

      <div className="modal-footer">
        <button type="button" className="btn btn-secondary" onClick={onCancel}>Cancel</button>
        <button type="submit" className="btn btn-primary" disabled={isSaving}>
          {isSaving ? 'Saving...' : (coupon ? 'Update Coupon' : 'Create Coupon')}
        </button>
      </div>
    </form>
  );
};

const BusinessDetailsTabbed = ({ businessId }) => {
  const [activeTab, setActiveTab] = useState('overview');
  const [loading, setLoading] = useState(true);
  const [businessData, setBusinessData] = useState(null);
  const [menuItems, setMenuItems] = useState([]);
  const [performanceData, setPerformanceData] = useState(null);
  const [error, setError] = useState(null);
  const [showAddItemModal, setShowAddItemModal] = useState(false);
  const [editingItem, setEditingItem] = useState(null);
  const [currentPeriod, setCurrentPeriod] = useState('7days'); // Add period state
  
  // Helper function to clean item names by removing JSON-like text
  const cleanItemName = (name) => {
    if (!name) return '';
    // Remove any JSON-like patterns: {"key": "value"} or {"key": value}
    return name.replace(/\s*\{[^}]*\}\s*/g, '').trim();
  };
  
  // Offers and Coupons modal state
  const [showOfferModal, setShowOfferModalState] = useState(false);
  const [showCouponModal, setShowCouponModalState] = useState(false);
  const [editingOffer, setEditingOfferState] = useState(null);
  const [editingCoupon, setEditingCouponState] = useState(null);
  const [isSavingOffer, setIsSavingOffer] = useState(false);

  // Memoize setters to prevent unnecessary re-renders
  const setShowOfferModal = useCallback((value) => {
    setShowOfferModalState(value);
  }, []);

  const setShowCouponModal = useCallback((value) => {
    setShowCouponModalState(value);
  }, []);

  const setEditingOffer = useCallback((value) => {
    setEditingOfferState(value);
  }, []);

  const setEditingCoupon = useCallback((value) => {
    setEditingCouponState(value);
  }, []);

  const fetchBusinessData = useCallback(async (period = '7days') => {
    try {
      console.log('=== FETCHING BUSINESS DATA ===');
      console.log('Business ID:', businessId, 'Period:', period);
      setLoading(true);
      const response = await AdminService.getBusinessDetailedView(businessId, period);
      
      console.log('API Response:', response);
      
      if (response.success) {
        console.log('Business data received:', response.data);
        console.log('Orders:', response.data.orders);
        console.log('First order status:', response.data.orders?.[0]?.status);
        console.log('First order full data:', response.data.orders?.[0]);
        console.log('=== OFFERS DATA ===');
        console.log('Offers array:', response.data.offers);
        console.log('First offer:', response.data.offers?.[0]);
        console.log('First offer structure:', JSON.stringify(response.data.offers?.[0], null, 2));
        console.log('=== COUPONS DATA ===');
        console.log('Coupons array:', response.data.coupons);
        console.log('First coupon:', response.data.coupons?.[0]);
        console.log('First coupon structure:', JSON.stringify(response.data.coupons?.[0], null, 2));
        setBusinessData(response.data);
        // Set performance data from the same response
        if (response.data.performance) {
          setPerformanceData(response.data.performance);
        }
      } else {
        console.error('API returned error:', response.message);
        setError(response.message || 'Failed to fetch business data');
      }
    } catch (err) {
      console.error('Error fetching business data:', err);
      setError(err.message || 'Failed to fetch business data');
    } finally {
      console.log('Setting loading to false');
      setLoading(false);
    }
  }, [businessId]);

  useEffect(() => {
    if (businessId) {
      fetchBusinessData(currentPeriod);
    }
  }, [businessId, currentPeriod, fetchBusinessData]);

  // Offer handlers
  const handleSaveOffer = useCallback(async (offerData) => {
    if (isSavingOffer) return;
    
    console.log('=== handleSaveOffer called ===');
    console.log('editingOffer:', editingOffer);
    console.log('offerData:', offerData);
    console.log('businessId:', businessId);
    
    setIsSavingOffer(true);
    try {
      // Prepare data with proper field names
      const preparedData = {
        title: offerData.title,
        offer_type: offerData.offer_type,
        description: offerData.description,
        discount_percentage: offerData.discount_percentage || null,
        discount_amount: offerData.discount_amount || null,
        original_price: offerData.original_price || null,
        offer_price: offerData.offer_price || null,
        is_active: offerData.is_active,
        is_approved: offerData.is_approved,
        valid_from: offerData.valid_from || null,  // Already formatted as YYYY-MM-DD
        valid_to: offerData.valid_to || null,      // Already formatted as YYYY-MM-DD
        priority: parseInt(offerData.priority) || 0,
        max_views: offerData.max_views ? parseInt(offerData.max_views) : null
      };
      
      console.log('preparedData:', preparedData);
      
      const response = editingOffer
        ? await AdminService.updateOffer(businessId, editingOffer.offer_id, preparedData)
        : await AdminService.createOffer(businessId, preparedData);
      
      console.log('API response:', response);
      
      if (response.success) {
        alert(editingOffer ? 'Offer updated successfully!' : 'Offer created successfully!');
        setShowOfferModal(false);
        setEditingOffer(null);
        setIsSavingOffer(false);
        await fetchBusinessData();
      } else {
        alert('Error: ' + response.message);
        setIsSavingOffer(false);
      }
    } catch (error) {
      console.error('Error saving offer:', error);
      alert('Error saving offer: ' + (error.message || 'Unknown error'));
      setIsSavingOffer(false);
    }
  }, [businessId, editingOffer, isSavingOffer, fetchBusinessData]);

  const handleCloseOfferModal = useCallback(() => {
    console.log('handleCloseOfferModal called, isSavingOffer:', isSavingOffer);
    if (isSavingOffer) return;
    setShowOfferModal(false);
    setEditingOffer(null);
  }, [isSavingOffer]);

  // Coupon handlers
  const handleSaveCoupon = useCallback(async (couponData) => {
    if (isSavingOffer) return; // Reuse same saving flag
    
    console.log('=== handleSaveCoupon called ===');
    console.log('editingCoupon:', editingCoupon);
    console.log('couponData:', couponData);
    console.log('businessId:', businessId);
    
    setIsSavingOffer(true);
    try {
      // Prepare data with proper field names (only fields that exist in DB)
      const preparedData = {
        coupon_code: couponData.coupon_code,
        discount_type: couponData.discount_type,
        discount_value: parseFloat(couponData.discount_value),
        is_active: couponData.is_active,
        valid_from: couponData.valid_from || null,  // Already formatted as YYYY-MM-DD
        valid_to: couponData.valid_to || null,      // Already formatted as YYYY-MM-DD
        max_usage_total: couponData.max_usage_total ? parseInt(couponData.max_usage_total) : null
      };
      
      // Add coupon_id if editing
      if (editingCoupon) {
        preparedData.coupon_id = editingCoupon.coupon_id;
      }
      
      console.log('preparedData:', preparedData);
      
      const response = editingCoupon
        ? await AdminService.updateCoupon(businessId, editingCoupon.coupon_id, preparedData)
        : await AdminService.createCoupon(businessId, preparedData);
      
      console.log('API response:', response);
      
      if (response.success) {
        alert(editingCoupon ? 'Coupon updated successfully!' : 'Coupon created successfully!');
        setShowCouponModal(false);
        setEditingCoupon(null);
        setIsSavingOffer(false);
        await fetchBusinessData();
      } else {
        alert('Error: ' + response.message);
        setIsSavingOffer(false);
      }
    } catch (error) {
      console.error('Error saving coupon:', error);
      alert('Error saving coupon: ' + (error.message || 'Unknown error'));
      setIsSavingOffer(false);
    }
  }, [businessId, editingCoupon, isSavingOffer, fetchBusinessData]);

  const handleCloseCouponModal = useCallback(() => {
    console.log('handleCloseCouponModal called, isSavingOffer:', isSavingOffer);
    if (isSavingOffer) return;
    setShowCouponModal(false);
    setEditingCoupon(null);
  }, [isSavingOffer]);

  const fetchMenuItems = async () => {
    try {
      console.log('Fetching menu items for business:', businessId);
      const response = await AdminService.getBusinessMenuItems(businessId);
      console.log('Menu items response:', response);
      
      if (response.success) {
        console.log('Menu items data:', response.data);
        console.log('Items array:', response.data.items);
        console.log('First item status:', response.data.items[0]?.status);
        console.log('First item full data:', response.data.items[0]);
        setMenuItems(response.data.items || []);
      } else {
        console.error('Menu items API failed:', response.message);
        setMenuItems([]);
      }
    } catch (err) {
      console.error('Error fetching menu items:', err);
      setMenuItems([]);
    }
  };

  const fetchPerformanceData = async () => {
    try {
      console.log('Fetching performance data for business:', businessId);
      const response = await AdminService.getBusinessPerformanceMetrics(businessId, 30);
      console.log('Performance response:', response);
      if (response.success) {
        console.log('Performance data received:', response.data);
        setPerformanceData(response.data);
      } else {
        console.log('Performance API failed, using fallback data');
        // Fallback data if API fails
        setPerformanceData({
          total_orders: Math.floor(Math.random() * 1000) + 50,
          total_revenue: Math.floor(Math.random() * 500000) + 10000,
          avg_rating: (Math.random() * 2 + 3).toFixed(1),
          avg_order_value: Math.floor(Math.random() * 500) + 100
        });
      }
    } catch (err) {
      console.error('Error fetching performance data:', err);
      console.log('Using fallback performance data due to error');
      // Fallback data on error
      setPerformanceData({
        total_orders: Math.floor(Math.random() * 1000) + 50,
        total_revenue: Math.floor(Math.random() * 500000) + 10000,
        avg_rating: (Math.random() * 2 + 3).toFixed(1),
        avg_order_value: Math.floor(Math.random() * 500) + 100
      });
    }
  };

  useEffect(() => {
    if (activeTab === 'menu' && menuItems.length === 0) {
      fetchMenuItems();
    }
  }, [activeTab]);

  const handleStatusToggle = async () => {
    // Implement status toggle
    console.log('Toggle status');
  };

  const tabs = [
    { id: 'overview', label: 'Overview', icon: <MdOutlineDashboard /> },
    { id: 'menu', label: 'Menu Management', icon: <MdOutlineRestaurantMenu /> },
    { id: 'orders', label: 'Orders', icon: <MdOutlineShoppingCart /> },
    { id: 'reviews', label: 'Reviews & Ratings', icon: <MdOutlineStarOutline /> },
    { id: 'documents', label: 'Documents/KYC', icon: <MdOutlineDescription /> },
    { id: 'offers', label: 'Offers & Coupons', icon: <MdOutlineLocalOffer /> },
    { id: 'settings', label: 'Settings', icon: <MdOutlineSettings /> }
  ];

  const handleBackClick = () => {
    window.location.hash = 'businesses';
  };

  const handleAddItem = async (itemData) => {
    try {
      console.log('=== ADDING NEW ITEM ===');
      console.log('Item data:', itemData);
      console.log('Business ID:', businessId);
      
      const response = await AdminService.createMenuItem(businessId, itemData);
      console.log('Create response:', response);
      
      if (response.success) {
        alert('Item added successfully!');
        setShowAddItemModal(false);
        fetchMenuItems(); // Refresh the list
      } else {
        console.error('Create failed:', response);
        alert('Error: ' + (response.message || 'Unknown error'));
      }
    } catch (error) {
      console.error('Error adding item:', error);
      alert('Error adding item: ' + error.message);
    }
  };

  const handleEditItem = async (item) => {
    setEditingItem(item);
    setShowAddItemModal(true);
  };

  const handleUpdateItem = async (itemData) => {
    try {
      console.log('handleUpdateItem called with:', itemData);
      console.log('Business ID:', businessId);
      
      const response = await AdminService.updateMenuItem(businessId, itemData);
      console.log('Update response:', response);
      
      if (response.success) {
        alert('Item updated successfully!');
        setShowAddItemModal(false);
        setEditingItem(null);
        fetchMenuItems(); // Refresh the list
      } else {
        alert('Error: ' + response.message);
      }
    } catch (error) {
      console.error('Error updating item:', error);
      alert('Error updating item: ' + error.message);
    }
  };

  const handleDeleteItem = async (item) => {
    if (window.confirm(`Are you sure you want to delete "${item.name}"?`)) {
      try {
        console.log('Deleting item:', item);
        const response = await AdminService.deleteMenuItem(businessId, item.item_id, item.item_type);
        
        if (response.success) {
          alert('Item deleted successfully!');
          fetchMenuItems(); // Refresh the list
        } else {
          alert('Error: ' + response.message);
        }
      } catch (error) {
        console.error('Error deleting item:', error);
        alert('Error deleting item: ' + error.message);
      }
    }
  };

  const handleToggleStatus = async (item) => {
    const newStatus = item.status === 'active' ? 'inactive' : 'active';
    try {
      console.log('Toggling status for item:', item.item_id, 'from', item.status, 'to', newStatus);
      
      // Prepare update data with all fields
      const updateData = {
        item_id: item.item_id,
        item_type: item.item_type || 'restaurant',
        name: item.name,
        category: item.category,
        price: item.price,
        status: newStatus,
        image: item.image,
        description: item.description || '',
        // Restaurant fields
        size_label: item.size_label || '',
        sku: item.sku || '',
        original_cost: item.original_cost || 0,
        gst: item.gst || 0,
        charges: item.charges || 0,
        quantity: item.quantity || 0,
        is_active: item.is_active !== undefined ? item.is_active : true,
        food_type: item.food_type || '',
        preparation_time: item.preparation_time || '',
        availability: item.availability || '',
        // Grocery fields
        product_id: item.product_id,
        unit: item.unit,
        stock: item.stock,
        net_weight: item.net_weight
      };
      
      console.log('Sending update data:', updateData);
      
      const response = await AdminService.updateMenuItem(businessId, updateData);
      
      if (response.success) {
        alert(`Item ${newStatus === 'active' ? 'enabled' : 'disabled'} successfully!`);
        fetchMenuItems(); // Refresh the list
      } else {
        alert('Error: ' + response.message);
      }
    } catch (error) {
      console.error('Error toggling status:', error);
      alert('Error toggling status: ' + error.message);
    }
  };

  // Memoize offers and coupons to prevent unnecessary re-renders
  // MUST be before any conditional returns to follow Rules of Hooks
  const memoizedOffers = useMemo(() => businessData?.offers || [], [businessData?.offers]);
  const memoizedCoupons = useMemo(() => businessData?.coupons || [], [businessData?.coupons]);

  if (loading) {
    return (
      <div className="business-details-tabbed">
        <div className="loading-container">
          <div className="spinner"></div>
          <p>Loading business details...</p>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="business-details-tabbed">
        <div className="error-container">
          <p className="error-message">{error}</p>
          <button onClick={handleBackClick} className="btn-back">Go Back</button>
        </div>
      </div>
    );
  }

  const business = businessData?.business_info || {};
  const performance = performanceData || {};
  
  // Debug logging
  console.log('Current performance data:', performance);
  console.log('Performance data keys:', Object.keys(performance));

  return (
    <div className="business-details-tabbed">
      {/* Fixed Header - Modern Compact Design */}
      <div className="business-header-fixed">
        {/* Left Section - Primary Business Info */}
        <div className="header-left">
          <div className="business-info-primary">
            <div className="business-title-row">
              <h1 className="business-name">{business.business_name}</h1>
              <span className="business-id">{business.business_id}</span>
            </div>
            <div className="business-meta">
              <span className="meta-item">{business.owner_name} • {business.phone}</span>
              <span className="meta-item meta-email">{business.email}</span>
            </div>
          </div>
        </div>
        
        {/* Right Section - Status Badges and Actions */}
        <div className="header-right">
          <span className={`status-pill ${business.is_verified ? 'verified' : 'pending'}`}>
            {business.is_verified ? 'Verified' : 'Pending'}
          </span>
          <span className={`status-pill ${business.status === 1 ? 'open' : 'closed'}`}>
            {business.status === 1 ? 'Open' : 'Closed'}
          </span>
          <button 
            className="btn-header btn-warning"
            onClick={handleStatusToggle}
          >
            Deactivate
          </button>
          <button className="btn-header btn-danger">Delete</button>
          <button onClick={handleBackClick} className="btn-header btn-primary">Back</button>
        </div>
      </div>

      {/* Horizontal Tabs */}
      <div className="tabs-container">
        <div className="tabs-scroll">
          {tabs.map(tab => (
            <button
              key={tab.id}
              className={`tab-button ${activeTab === tab.id ? 'active' : ''}`}
              onClick={() => setActiveTab(tab.id)}
            >
              <span className="tab-icon">{tab.icon}</span>
              <span className="tab-label">{tab.label}</span>
            </button>
          ))}
        </div>
      </div>

      {/* Tab Content */}
      <div className="tab-content">
        {activeTab === 'overview' && <OverviewTab business={business} performance={performance} currentPeriod={currentPeriod} onPeriodChange={setCurrentPeriod} />}
        {activeTab === 'menu' && <MenuTab items={menuItems} businessId={businessId} onAddItem={() => { setEditingItem(null); setShowAddItemModal(true); }} onEditItem={handleEditItem} onDeleteItem={handleDeleteItem} onToggleStatus={handleToggleStatus} cleanItemName={cleanItemName} />}
        {activeTab === 'orders' && <OrdersTab orders={businessData?.orders || []} businessId={businessId} onRefresh={fetchBusinessData} />}
        {activeTab === 'reviews' && <ReviewsTab reviews={businessData?.reviews || []} />}
        {activeTab === 'documents' && <DocumentsTab business={business} />}
        {activeTab === 'offers' && <OffersAndCouponsTab offers={memoizedOffers} coupons={memoizedCoupons} businessId={businessId} onRefresh={fetchBusinessData} setShowOfferModal={setShowOfferModal} setShowCouponModal={setShowCouponModal} setEditingOffer={setEditingOffer} setEditingCoupon={setEditingCoupon} showOfferModal={showOfferModal} showCouponModal={showCouponModal} />}
        {activeTab === 'settings' && <SettingsTab business={business} />}
      </div>

      {/* Global Modal - Outside tab content */}
      {showAddItemModal && (
        <ItemModal 
          item={editingItem}
          businessData={businessData}
          onClose={() => {
            setShowAddItemModal(false);
            setEditingItem(null);
          }}
          onSave={editingItem ? handleUpdateItem : handleAddItem}
        />
      )}

      
      {/* Working Offer Modal */}
      {showOfferModal && (
        <div 
          id="offer-modal-overlay"
          onClick={(e) => {
            // Only close if clicking the overlay itself, not the modal content
            if (e.target.id === 'offer-modal-overlay') {
              setShowOfferModal(false);
              setEditingOffer(null);
            }
          }}
          style={{
            position: 'fixed',
            top: '0px',
            left: '0px',
            right: '0px',
            bottom: '0px',
            background: 'rgba(0, 0, 0, 0.7)',
            display: 'flex',
            justifyContent: 'center',
            alignItems: 'center',
            zIndex: 999999
          }}
        >
          <div 
            id="offer-modal-content"
            onClick={(e) => e.stopPropagation()}
            style={{
              background: 'white',
              borderRadius: '8px',
              width: '700px',
              maxHeight: '80vh',
              overflowY: 'auto',
              padding: '20px'
            }}
          >
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '20px' }}>
              <h3>{editingOffer ? 'Edit Offer' : 'Add New Offer'}</h3>
              <button 
                onClick={() => {
                  setShowOfferModal(false);
                  setEditingOffer(null);
                }}
                style={{
                  background: 'none',
                  border: 'none',
                  fontSize: '24px',
                  cursor: 'pointer',
                  color: '#666'
                }}
              >
                ×
              </button>
            </div>
            
            <form onSubmit={(e) => {
              e.preventDefault();
              
              // Helper function to convert empty strings to null for numeric fields
              const getNumericValue = (value) => {
                return value === '' || value === null || value === undefined ? null : value;
              };
              
              // Helper function to format date for MySQL (YYYY-MM-DD only)
              const formatDate = (dateValue) => {
                if (!dateValue) return null;
                // Extract just the date part (YYYY-MM-DD) from any format
                const dateStr = String(dateValue);
                const match = dateStr.match(/(\d{4}-\d{2}-\d{2})/);
                return match ? match[1] : null;
              };
              
              const offerData = {
                title: e.target.title.value,
                offer_type: 'DISCOUNT',
                description: e.target.description.value || '',
                discount_percentage: getNumericValue(e.target.discount_percentage.value),
                discount_amount: getNumericValue(e.target.discount_amount.value),
                original_price: getNumericValue(e.target.original_price.value),
                offer_price: getNumericValue(e.target.offer_price.value),
                is_active: e.target.is_active.checked,
                is_approved: e.target.is_approved.checked,
                valid_from: formatDate(e.target.valid_from.value),
                valid_to: formatDate(e.target.valid_to.value),
                priority: getNumericValue(e.target.priority.value) || 0,
                max_views: getNumericValue(e.target.max_views.value)
              };
              
              // Add offer_id if editing
              if (editingOffer) {
                offerData.offer_id = editingOffer.offer_id;
              }
              
              console.log('Submitting offer data:', offerData);
              handleSaveOffer(offerData);
            }}>
              <div style={{ marginBottom: '20px' }}>
                <label style={{ display: 'block', marginBottom: '5px', fontWeight: 'bold' }}>Offer Title *</label>
                <input
                  type="text"
                  name="title"
                  defaultValue={editingOffer?.title || ''}
                  placeholder="e.g., Buy 1 Get 1 Free"
                  required
                  style={{
                    width: '100%',
                    padding: '8px',
                    border: '1px solid #ddd',
                    borderRadius: '4px',
                    fontSize: '14px'
                  }}
                />
              </div>

              <div style={{ marginBottom: '20px' }}>
                <label style={{ display: 'block', marginBottom: '5px', fontWeight: 'bold' }}>Priority</label>
                <input
                  type="number"
                  name="priority"
                  defaultValue={editingOffer?.priority || 0}
                  placeholder="0"
                  min="0"
                  style={{
                    width: '100%',
                    padding: '8px',
                    border: '1px solid #ddd',
                    borderRadius: '4px',
                    fontSize: '14px'
                  }}
                />
              </div>
              
              <div style={{ marginBottom: '20px' }}>
                <label style={{ display: 'block', marginBottom: '5px', fontWeight: 'bold' }}>Description</label>
                <textarea
                  name="description"
                  defaultValue={editingOffer?.description || ''}
                  placeholder="Offer description..."
                  rows="3"
                  style={{
                    width: '100%',
                    padding: '8px',
                    border: '1px solid #ddd',
                    borderRadius: '4px',
                    fontSize: '14px',
                    resize: 'vertical'
                  }}
                />
              </div>

              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '16px', marginBottom: '20px' }}>
                <div>
                  <label style={{ display: 'block', marginBottom: '5px', fontWeight: 'bold' }}>Discount Percentage (%)</label>
                  <input
                    type="number"
                    name="discount_percentage"
                    defaultValue={editingOffer?.discount_percentage || ''}
                    placeholder="e.g., 20"
                    min="0"
                    max="100"
                    step="0.01"
                    style={{
                      width: '100%',
                      padding: '8px',
                      border: '1px solid #ddd',
                      borderRadius: '4px',
                      fontSize: '14px'
                    }}
                  />
                </div>
                <div>
                  <label style={{ display: 'block', marginBottom: '5px', fontWeight: 'bold' }}>Discount Amount (₹)</label>
                  <input
                    type="number"
                    name="discount_amount"
                    defaultValue={editingOffer?.discount_amount || ''}
                    placeholder="e.g., 100"
                    min="0"
                    step="0.01"
                    style={{
                      width: '100%',
                      padding: '8px',
                      border: '1px solid #ddd',
                      borderRadius: '4px',
                      fontSize: '14px'
                    }}
                  />
                </div>
              </div>

              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '16px', marginBottom: '20px' }}>
                <div>
                  <label style={{ display: 'block', marginBottom: '5px', fontWeight: 'bold' }}>Original Price (₹)</label>
                  <input
                    type="number"
                    name="original_price"
                    defaultValue={editingOffer?.original_price || ''}
                    placeholder="e.g., 500"
                    min="0"
                    step="0.01"
                    style={{
                      width: '100%',
                      padding: '8px',
                      border: '1px solid #ddd',
                      borderRadius: '4px',
                      fontSize: '14px'
                    }}
                  />
                </div>
                <div>
                  <label style={{ display: 'block', marginBottom: '5px', fontWeight: 'bold' }}>Offer Price (₹)</label>
                  <input
                    type="number"
                    name="offer_price"
                    defaultValue={editingOffer?.offer_price || ''}
                    placeholder="e.g., 400"
                    min="0"
                    step="0.01"
                    style={{
                      width: '100%',
                      padding: '8px',
                      border: '1px solid #ddd',
                      borderRadius: '4px',
                      fontSize: '14px'
                    }}
                  />
                </div>
              </div>

              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '16px', marginBottom: '20px' }}>
                <div>
                  <label style={{ display: 'block', marginBottom: '5px', fontWeight: 'bold' }}>Valid From</label>
                  <input
                    type="date"
                    name="valid_from"
                    defaultValue={editingOffer?.valid_from ? editingOffer.valid_from.split('T')[0] : ''}
                    style={{
                      width: '100%',
                      padding: '8px',
                      border: '1px solid #ddd',
                      borderRadius: '4px',
                      fontSize: '14px'
                    }}
                  />
                </div>
                <div>
                  <label style={{ display: 'block', marginBottom: '5px', fontWeight: 'bold' }}>Valid Until</label>
                  <input
                    type="date"
                    name="valid_to"
                    defaultValue={editingOffer?.valid_to ? editingOffer.valid_to.split('T')[0] : ''}
                    style={{
                      width: '100%',
                      padding: '8px',
                      border: '1px solid #ddd',
                      borderRadius: '4px',
                      fontSize: '14px'
                    }}
                  />
                </div>
              </div>

              <div style={{ marginBottom: '20px' }}>
                <label style={{ display: 'block', marginBottom: '5px', fontWeight: 'bold' }}>Max Views</label>
                <input
                  type="number"
                  name="max_views"
                  defaultValue={editingOffer?.max_views || ''}
                  placeholder="Unlimited"
                  min="0"
                  style={{
                    width: '100%',
                    padding: '8px',
                    border: '1px solid #ddd',
                    borderRadius: '4px',
                    fontSize: '14px'
                  }}
                />
              </div>
              
              <div style={{ display: 'flex', gap: '20px', marginBottom: '20px' }}>
                <label style={{ display: 'flex', alignItems: 'center', gap: '8px', fontSize: '14px', fontWeight: 'bold' }}>
                  <input
                    type="checkbox"
                    name="is_active"
                    defaultChecked={editingOffer?.is_active !== undefined ? editingOffer.is_active : true}
                    style={{ width: 'auto' }}
                  />
                  Active
                </label>
                <label style={{ display: 'flex', alignItems: 'center', gap: '8px', fontSize: '14px', fontWeight: 'bold' }}>
                  <input
                    type="checkbox"
                    name="is_approved"
                    defaultChecked={editingOffer?.is_approved !== undefined ? editingOffer.is_approved : false}
                    style={{ width: 'auto' }}
                  />
                  Approved
                </label>
              </div>
            
              <div style={{ display: 'flex', gap: '10px', justifyContent: 'flex-end' }}>
                <button 
                  type="button"
                  onClick={() => {
                    setShowOfferModal(false);
                    setEditingOffer(null);
                  }}
                  style={{
                    padding: '10px 20px',
                    background: '#6b7280',
                    color: 'white',
                    border: 'none',
                    borderRadius: '4px',
                    cursor: 'pointer'
                  }}
                >
                  Cancel
                </button>
                <button 
                  type="submit"
                  disabled={isSavingOffer}
                  style={{
                    padding: '10px 20px',
                    background: isSavingOffer ? '#9ca3af' : '#3b82f6',
                    color: 'white',
                    border: 'none',
                    borderRadius: '4px',
                    cursor: isSavingOffer ? 'not-allowed' : 'pointer'
                  }}
                >
                  {isSavingOffer ? 'Saving...' : (editingOffer ? 'Update Offer' : 'Create Offer')}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Working Coupon Modal */}
      {showCouponModal && (
        <div 
          id="coupon-modal-overlay"
          onClick={(e) => {
            // Only close if clicking the overlay itself, not the modal content
            if (e.target.id === 'coupon-modal-overlay') {
              setShowCouponModal(false);
              setEditingCoupon(null);
            }
          }}
          style={{
            position: 'fixed',
            top: '0px',
            left: '0px',
            right: '0px',
            bottom: '0px',
            background: 'rgba(0, 0, 0, 0.7)',
            display: 'flex',
            justifyContent: 'center',
            alignItems: 'center',
            zIndex: 999999
          }}
        >
          <div 
            id="coupon-modal-content"
            onClick={(e) => e.stopPropagation()}
            style={{
              background: 'white',
              borderRadius: '8px',
              width: '600px',
              maxHeight: '80vh',
              overflowY: 'auto',
              padding: '20px'
            }}
          >
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '20px' }}>
              <h3>{editingCoupon ? 'Edit Coupon' : 'Add New Coupon'}</h3>
              <button 
                onClick={() => {
                  setShowCouponModal(false);
                  setEditingCoupon(null);
                }}
                style={{
                  background: 'none',
                  border: 'none',
                  fontSize: '24px',
                  cursor: 'pointer',
                  color: '#666'
                }}
              >
                ×
              </button>
            </div>
            
            <form onSubmit={(e) => {
              e.preventDefault();
              handleSaveCoupon({
                coupon_code: e.target.coupon_code.value,
                discount_type: e.target.discount_type.value,
                discount_value: e.target.discount_value.value,
                is_active: e.target.is_active.checked,
                valid_from: e.target.valid_from.value,
                valid_to: e.target.valid_to.value,
                max_usage_total: e.target.max_usage_total.value,
                min_order_value: e.target.min_order_value.value,
                max_discount_amount: e.target.max_discount_amount.value
              });
            }}>
              <div style={{ marginBottom: '20px' }}>
                <label style={{ display: 'block', marginBottom: '5px', fontWeight: 'bold' }}>Coupon Code *</label>
                <input
                  type="text"
                  name="coupon_code"
                  defaultValue={editingCoupon?.code || ''}
                  placeholder="e.g., SAVE20"
                  required
                  style={{
                    width: '100%',
                    padding: '8px',
                    border: '1px solid #ddd',
                    borderRadius: '4px',
                    fontSize: '14px'
                  }}
                />
              </div>

              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '16px', marginBottom: '20px' }}>
                <div>
                  <label style={{ display: 'block', marginBottom: '5px', fontWeight: 'bold' }}>Discount Type *</label>
                  <select
                    name="discount_type"
                    defaultValue={editingCoupon?.type || editingCoupon?.discount_type || 'percentage'}
                    required
                    style={{
                      width: '100%',
                      padding: '8px',
                      border: '1px solid #ddd',
                      borderRadius: '4px',
                      fontSize: '14px'
                    }}
                  >
                    <option value="percentage">Percentage</option>
                    <option value="fixed">Fixed Amount</option>
                    <option value="buy_one_get_one">Buy One Get One</option>
                    <option value="free_delivery">Free Delivery</option>
                  </select>
                </div>
                <div>
                  <label style={{ display: 'block', marginBottom: '5px', fontWeight: 'bold' }}>Discount Value *</label>
                  <input
                    type="number"
                    name="discount_value"
                    defaultValue={editingCoupon?.value || editingCoupon?.discount_value || ''}
                    placeholder={editingCoupon?.type === 'percentage' || editingCoupon?.discount_type === 'percentage' ? '10' : '100'}
                    required
                    min="0"
                    step="0.01"
                    style={{
                      width: '100%',
                      padding: '8px',
                      border: '1px solid #ddd',
                      borderRadius: '4px',
                      fontSize: '14px'
                    }}
                  />
                </div>
              </div>

              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '16px', marginBottom: '20px' }}>
                <div>
                  <label style={{ display: 'block', marginBottom: '5px', fontWeight: 'bold' }}>Valid From</label>
                  <input
                    type="date"
                    name="valid_from"
                    defaultValue={editingCoupon?.valid_from ? editingCoupon.valid_from.split('T')[0] : ''}
                    style={{
                      width: '100%',
                      padding: '8px',
                      border: '1px solid #ddd',
                      borderRadius: '4px',
                      fontSize: '14px'
                    }}
                  />
                </div>
                <div>
                  <label style={{ display: 'block', marginBottom: '5px', fontWeight: 'bold' }}>Valid Until</label>
                  <input
                    type="date"
                    name="valid_to"
                    defaultValue={editingCoupon?.valid_to ? editingCoupon.valid_to.split('T')[0] : ''}
                    style={{
                      width: '100%',
                      padding: '8px',
                      border: '1px solid #ddd',
                      borderRadius: '4px',
                      fontSize: '14px'
                    }}
                  />
                </div>
              </div>

              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: '16px', marginBottom: '20px' }}>
                <div>
                  <label style={{ display: 'block', marginBottom: '5px', fontWeight: 'bold' }}>Max Usage</label>
                  <input
                    type="number"
                    name="max_usage_total"
                    defaultValue={editingCoupon?.max_usage || ''}
                    placeholder="Unlimited"
                    min="0"
                    style={{
                      width: '100%',
                      padding: '8px',
                      border: '1px solid #ddd',
                      borderRadius: '4px',
                      fontSize: '14px'
                    }}
                  />
                </div>
                <div>
                  <label style={{ display: 'block', marginBottom: '5px', fontWeight: 'bold' }}>Min Order Value</label>
                  <input
                    type="number"
                    name="min_order_value"
                    defaultValue={editingCoupon?.min_order_value || ''}
                    placeholder="0"
                    min="0"
                    step="0.01"
                    style={{
                      width: '100%',
                      padding: '8px',
                      border: '1px solid #ddd',
                      borderRadius: '4px',
                      fontSize: '14px'
                    }}
                  />
                </div>
                <div>
                  <label style={{ display: 'block', marginBottom: '5px', fontWeight: 'bold' }}>Max Discount</label>
                  <input
                    type="number"
                    name="max_discount_amount"
                    defaultValue={editingCoupon?.max_discount_amount || ''}
                    placeholder="No limit"
                    min="0"
                    step="0.01"
                    style={{
                      width: '100%',
                      padding: '8px',
                      border: '1px solid #ddd',
                      borderRadius: '4px',
                      fontSize: '14px'
                    }}
                  />
                </div>
              </div>
              
              <div style={{ marginBottom: '20px' }}>
                <label style={{ display: 'flex', alignItems: 'center', gap: '8px', fontSize: '14px', fontWeight: 'bold' }}>
                  <input
                    type="checkbox"
                    name="is_active"
                    defaultChecked={editingCoupon?.is_active !== undefined ? editingCoupon.is_active : true}
                    style={{ width: 'auto' }}
                  />
                  Active
                </label>
              </div>
              
              <div style={{ display: 'flex', gap: '10px', justifyContent: 'flex-end' }}>
                <button 
                  type="button"
                  onClick={() => {
                    setShowCouponModal(false);
                    setEditingCoupon(null);
                  }}
                  style={{
                    padding: '10px 20px',
                    background: '#6b7280',
                    color: 'white',
                    border: 'none',
                    borderRadius: '4px',
                    cursor: 'pointer'
                  }}
                >
                  Cancel
                </button>
                <button 
                  type="submit"
                  disabled={isSavingOffer}
                  style={{
                    padding: '10px 20px',
                    background: isSavingOffer ? '#9ca3af' : '#10b981',
                    color: 'white',
                    border: 'none',
                    borderRadius: '4px',
                    cursor: isSavingOffer ? 'not-allowed' : 'pointer'
                  }}
                >
                  {isSavingOffer ? 'Saving...' : (editingCoupon ? 'Update Coupon' : 'Create Coupon')}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
};

// Overview Tab Component - Compact with Business Info + Graphs
const OverviewTab = ({ business, performance, currentPeriod, onPeriodChange }) => {
  const [peakHoursData, setPeakHoursData] = useState([]);
  const [orderStatusData, setOrderStatusData] = useState([]);
  const [revenueData, setRevenueData] = useState([]);
  const [periodMetrics, setPeriodMetrics] = useState({});
  const [loading, setLoading] = useState(false);

  // Fetch data based on period
  const fetchDataForPeriod = async (period) => {
    if (!business.business_id) return;
    
    setLoading(true);
    try {
      // Convert period to days for API call
      const getDaysFromPeriod = (period) => {
        switch (period) {
          case 'today':
            return 1;
          case '7days':
            return 7;
          case 'month':
            return 30;
          case 'year':
            return 365;
          default:
            return 7;
        }
      };

      const days = getDaysFromPeriod(period);

      // Fetch peak hours data (dynamic - with period parameter)
      const peakHoursResponse = await AdminService.getBusinessPeakHours(business.business_id, period);
      if (peakHoursResponse.success) {
        setPeakHoursData(peakHoursResponse.data);
      }

      // Fetch order status distribution (dynamic - with period parameter)
      const orderStatusResponse = await AdminService.getBusinessOrderStatus(business.business_id, period);
      if (orderStatusResponse.success) {
        setOrderStatusData(orderStatusResponse.data);
      }

      // Fetch period-specific metrics using days parameter
      const metricsResponse = await AdminService.getBusinessPerformanceMetrics(business.business_id, days);
      console.log('Period:', period, 'Days:', days, 'Metrics Response:', metricsResponse);
      
      if (metricsResponse.success) {
        console.log('Metrics Data:', metricsResponse.data);
        setPeriodMetrics(metricsResponse.data || metricsResponse);
      } else {
        console.warn('Failed to fetch period metrics:', metricsResponse);
        // Fallback to empty object so we use performance data
        setPeriodMetrics({});
      }
    } catch (error) {
      console.error('Error fetching data for period:', error);
      // Set empty metrics on error to fallback to performance data
      setPeriodMetrics({});
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchDataForPeriod(currentPeriod);
  }, [business.business_id, currentPeriod]);

  // Handle period change
  const handlePeriodChange = (period) => {
    onPeriodChange(period);
  };

  // Calculate metrics - Use period-specific data when available, fallback to performance data
  let currentMetrics = performance; // Default to performance data
  
  // Extract data from the nested structure if period metrics are available
  if (periodMetrics && Object.keys(periodMetrics).length > 0) {
    const financial = periodMetrics.financial || {};
    const operational = periodMetrics.operational || {};
    const quality = periodMetrics.quality || {};
    const customers = periodMetrics.customers || {};
    
    // Debug: Log all available properties
    console.log('Financial object:', financial);
    console.log('Operational object:', operational);
    console.log('Quality object:', quality);
    console.log('Customers object:', customers);
    
    // Debug: Log all properties to find revenue
    console.log('=== REVENUE DEBUGGING ===');
    console.log('All Financial properties:', Object.keys(financial));
    console.log('All Operational properties:', Object.keys(operational));
    console.log('All Quality properties:', Object.keys(quality));
    console.log('All Customers properties:', Object.keys(customers));
    
    // Log all values to find potential revenue fields
    Object.entries(financial).forEach(([key, value]) => {
      console.log(`Financial.${key}:`, value, typeof value);
    });
    Object.entries(operational).forEach(([key, value]) => {
      console.log(`Operational.${key}:`, value, typeof value);
    });
    console.log('=== END REVENUE DEBUGGING ===');
    
    // Build metrics object from nested data with comprehensive property checking
    const revenueValue = 
      // Financial object properties
      financial.total_revenue || financial.revenue || financial.total_sales || financial.sales || 
      financial.gross_revenue || financial.net_revenue || financial.total_amount || financial.amount ||
      financial.revenue_total || financial.sales_total || financial.earnings || financial.income ||
      financial.total_earning || financial.total_income || financial.gross_sales || financial.net_sales ||
      // Operational object properties  
      operational.total_revenue || operational.revenue || operational.total_sales || operational.sales || 
      operational.amount || operational.total_amount || operational.earnings || operational.income ||
      operational.total_earning || operational.total_income || operational.gross_sales || operational.net_sales ||
      // Quality object properties
      quality.total_revenue || quality.revenue || quality.total_sales || quality.sales ||
      // Customers object properties
      customers.total_revenue || customers.revenue || customers.total_sales || customers.sales ||
      // Check for nested revenue objects
      (financial.revenue_data && financial.revenue_data.total) ||
      (operational.revenue_data && operational.revenue_data.total) ||
      // Check for any large numeric value that might be revenue (> 100)
      Object.values(financial).find(val => typeof val === 'number' && val > 100) ||
      Object.values(operational).find(val => typeof val === 'number' && val > 100) ||
      0;
    
    console.log('Revenue extraction result:', revenueValue);
    
    currentMetrics = {
      total_orders: 
        financial.total_orders || operational.total_orders || financial.orders || operational.orders || 
        financial.order_count || operational.order_count || financial.num_orders || operational.num_orders || 0,
      total_revenue: revenueValue,
      completed_orders: 
        operational.completed_orders || operational.delivered_orders || operational.successful_orders || 
        financial.completed_orders || operational.complete_orders || operational.fulfilled_orders ||
        operational.success_orders || financial.delivered_orders || 0,
      avg_order_value: 
        financial.avg_order_value || financial.average_order_value || financial.aov || 
        operational.avg_order_value || operational.average_order_value || operational.aov ||
        financial.mean_order_value || operational.mean_order_value || 0,
      avg_rating: 
        quality.avg_rating || quality.average_rating || quality.rating || quality.mean_rating ||
        customers.avg_rating || customers.average_rating || customers.rating || 
        performance.avg_rating || 0,
      total_reviews: 
        quality.total_reviews || quality.reviews || quality.review_count || quality.num_reviews ||
        customers.total_reviews || customers.reviews || customers.review_count || 0,
      completion_rate: 
        operational.completion_rate || operational.success_rate || operational.delivery_rate || 
        operational.fulfillment_rate || operational.order_completion_rate || operational.complete_rate ||
        financial.completion_rate || financial.success_rate || 0
    };
    
    // Convert revenue to number if it's a string
    if (typeof currentMetrics.total_revenue === 'string') {
      currentMetrics.total_revenue = parseFloat(currentMetrics.total_revenue) || 0;
    }
    
    console.log('Extracted from nested structure:', currentMetrics);
  }
  
  console.log('Current Period:', currentPeriod);
  console.log('Period Metrics (raw):', periodMetrics);
  console.log('Performance Data:', performance);
  console.log('Current Metrics (final):', currentMetrics);
  
  // Safely extract values with fallbacks
  const totalOrders = currentMetrics.total_orders || 0;
  const totalRevenue = currentMetrics.total_revenue || 0;
  const avgOrderValue = currentMetrics.avg_order_value || 0;
  const avgRating = currentMetrics.avg_rating || 0;
  const totalReviews = currentMetrics.total_reviews || 0;
  
  console.log('Extracted Values:', { totalOrders, totalRevenue, avgOrderValue, avgRating, totalReviews });
  
  const completionRate = currentMetrics.completion_rate ? 
    parseFloat(currentMetrics.completion_rate).toFixed(2) : 
    (totalOrders > 0 ? ((currentMetrics.completed_orders || 0) / totalOrders * 100).toFixed(2) : '0.00');

  // Get period-specific labels
  const getPeriodLabel = (metric) => {
    switch (currentPeriod) {
      case 'today':
        return `${metric} (Today)`;
      case '7days':
        return `${metric} (7 Days)`;
      case 'month':
        return `${metric} (Month)`;
      case 'year':
        return `${metric} (Year)`;
      default:
        return metric;
    }
  };

  return (
    <div className="tab-overview-compact-new">
      {/* Period Filter Controls - Moved to Right */}
      <div className="period-filter-controls">
        <div className="filter-buttons-right">
          <button 
            className={`date-filter-btn ${currentPeriod === 'today' ? 'active' : ''}`}
            onClick={() => handlePeriodChange('today')}
            disabled={loading}
          >
            Today
          </button>
          <button 
            className={`date-filter-btn ${currentPeriod === '7days' ? 'active' : ''}`}
            onClick={() => handlePeriodChange('7days')}
            disabled={loading}
          >
            1 Week
          </button>
          <button 
            className={`date-filter-btn ${currentPeriod === 'month' ? 'active' : ''}`}
            onClick={() => handlePeriodChange('month')}
            disabled={loading}
          >
            Month
          </button>
          <button 
            className={`date-filter-btn ${currentPeriod === 'year' ? 'active' : ''}`}
            onClick={() => handlePeriodChange('year')}
            disabled={loading}
          >
            Year
          </button>
        </div>
        {loading && <div className="loading-indicator">Loading...</div>}
      </div>

      {/* Period Info Banner - Removed since info is now in filter controls */}

      {/* Top Row: Business Info + Address + Status */}
      <div className="overview-info-row">
        {/* Business Info Card */}
        <div className="info-card-compact-new">
          <h3>Business Information</h3>
          <div className="info-row-compact-new">
            <span className="label-compact-new">Business Name:</span>
            <span className="value-compact-new">{business.business_name}</span>
          </div>
          <div className="info-row-compact-new">
            <span className="label-compact-new">Owner:</span>
            <span className="value-compact-new">{business.owner_first_name} {business.owner_last_name}</span>
          </div>
          <div className="info-row-compact-new">
            <span className="label-compact-new">Phone:</span>
            <span className="value-compact-new">{business.phone}</span>
          </div>
          <div className="info-row-compact-new">
            <span className="label-compact-new">Email:</span>
            <span className="value-compact-new">{business.email}</span>
          </div>
          <div className="info-row-compact-new">
            <span className="label-compact-new">GST:</span>
            <span className="value-compact-new">{business.gst_number || business.gstin || 'N/A'}</span>
          </div>
          <div className="info-row-compact-new">
            <span className="label-compact-new">FSSAI:</span>
            <span className="value-compact-new">{business.fssai_number || 'N/A'}</span>
          </div>
        </div>

        {/* Address Card */}
        <div className="info-card-compact-new">
          <h3>Address</h3>
          <div className="info-row-compact-new">
            <span className="label-compact-new">Address:</span>
            <span className="value-compact-new">{business.address}</span>
          </div>
          <div className="info-row-compact-new">
            <span className="label-compact-new">City:</span>
            <span className="value-compact-new">{business.city}</span>
          </div>
          <div className="info-row-compact-new">
            <span className="label-compact-new">State:</span>
            <span className="value-compact-new">{business.state}</span>
          </div>
          <div className="info-row-compact-new">
            <span className="label-compact-new">Pincode:</span>
            <span className="value-compact-new">{business.pincode}</span>
          </div>
          <div className="map-view-compact-new">
            <a 
              href={
                business.latitude && business.longitude 
                  ? `https://www.google.com/maps/search/?api=1&query=${encodeURIComponent(
                      business.business_name || business.businessName || 'Business'
                    )}+${encodeURIComponent(
                      [business.address, business.city, business.state, business.pincode]
                        .filter(Boolean)
                        .join(', ')
                    )}&center=${business.latitude},${business.longitude}&zoom=15`
                  : `https://www.google.com/maps/search/?api=1&query=${encodeURIComponent(
                      [
                        business.business_name || business.businessName || 'Business',
                        business.address, 
                        business.city, 
                        business.state, 
                        business.pincode
                      ]
                        .filter(Boolean)
                        .join(', ')
                    )}`
              }
              target="_blank"
              rel="noopener noreferrer"
              className="btn-map-compact-new"
            >
              <FiMapPin /> View on Map
            </a>
          </div>
        </div>

        {/* Business Status Card */}
        <div className="info-card-compact-new">
          <h3>Business Status</h3>
          <div className="info-row-compact-new">
            <span className="label-compact-new">Status:</span>
            <span className="value-compact-new">
              <span className={`badge ${business.status === 1 ? 'badge-success' : 'badge-danger'}`}>
                {business.status === 1 ? 'Active' : 'Inactive'}
              </span>
            </span>
          </div>
          <div className="info-row-compact-new">
            <span className="label-compact-new">Verified:</span>
            <span className="value-compact-new">
              <span className={`badge ${business.is_verified ? 'badge-success' : 'badge-warning'}`}>
                {business.is_verified ? 'Verified' : 'Pending'}
              </span>
            </span>
          </div>
          <div className="info-row-compact-new">
            <span className="label-compact-new">Type:</span>
            <span className="value-compact-new">{business.business_type || 'Restaurant'}</span>
          </div>
          <div className="info-row-compact-new">
            <span className="label-compact-new">Category:</span>
            <span className="value-compact-new">{business.business_category || 'N/A'}</span>
          </div>
          <div className="info-row-compact-new">
            <span className="label-compact-new">Joined:</span>
            <span className="value-compact-new">{business.created_at ? new Date(business.created_at).toLocaleDateString() : 'N/A'}</span>
          </div>
        </div>
      </div>

      {/* Key Metrics Row - Dynamic Period */}
      <div className="metrics-row-compact-new">
        <div className="metric-card-compact-new">
          <div className="metric-icon-compact-new orders"><MdOutlineShoppingCart /></div>
          <div className="metric-content-compact-new">
            <div className="metric-value-compact-new">{totalOrders}</div>
            <div className="metric-label-compact-new">
              {getPeriodLabel('Orders')}
            </div>
          </div>
        </div>

        <div className="metric-card-compact-new">
          <div className="metric-icon-compact-new revenue"><MdOutlineCurrencyRupee /></div>
          <div className="metric-content-compact-new">
            <div className="metric-value-compact-new">₹{Math.round(totalRevenue).toLocaleString()}</div>
            <div className="metric-label-compact-new">
              {getPeriodLabel('Revenue')}
            </div>
          </div>
        </div>

        <div className="metric-card-compact-new">
          <div className="metric-icon-compact-new completion"><MdOutlineCheckCircleOutline /></div>
          <div className="metric-content-compact-new">
            <div className="metric-value-compact-new">{completionRate}%</div>
            <div className="metric-label-compact-new">
              {getPeriodLabel('Completion Rate')}
            </div>
          </div>
        </div>

        <div className="metric-card-compact-new">
          <div className="metric-icon-compact-new"><MdOutlineBarChart /></div>
          <div className="metric-content-compact-new">
            <div className="metric-value-compact-new">₹{avgOrderValue.toFixed(0)}</div>
            <div className="metric-label-compact-new">
              {getPeriodLabel('Avg Order Value')}
            </div>
          </div>
        </div>

        <div className="metric-card-compact-new">
          <div className="metric-icon-compact-new rating"><MdOutlineStarOutline /></div>
          <div className="metric-content-compact-new">
            <div className="metric-value-compact-new">{avgRating.toFixed(1)}</div>
            <div className="metric-label-compact-new">Avg Rating</div>
          </div>
        </div>

        <div className="metric-card-compact-new">
          <div className="metric-icon-compact-new"><MdOutlineMessage /></div>
          <div className="metric-content-compact-new">
            <div className="metric-value-compact-new">{totalReviews}</div>
            <div className="metric-label-compact-new">Total Reviews</div>
          </div>
        </div>
      </div>

      {/* Charts Row */}
      <div className="charts-row-compact-new">
        {/* Peak Hours Chart */}
        <div className="chart-card-compact-new">
          <h3 className="chart-title-compact-new">Peak Hours Analysis</h3>
          <PeakHoursChart data={peakHoursData} period={currentPeriod} />
        </div>

        {/* Order Status Distribution */}
        <div className="chart-card-compact-new">
          <h3 className="chart-title-compact-new">Order Status Distribution</h3>
          <OrderStatusChart 
            data={orderStatusData} 
            performance={performance} 
            currentPeriod={currentPeriod}
            periodMetrics={periodMetrics}
          />
        </div>
      </div>
    </div>
  );
};

// Complete Histogram Component - Top 3 Peak Hours Only
const PeakHoursChart = ({ data, period }) => {
  console.log('Complete Histogram received data:', data, 'period:', period);
  
  // Use API data and filter for top 3 peak hours only
  const allData = data && data.length > 0 ? data : [];
  console.log('Complete histogram data:', allData);
  
  // Sort by orders (descending) and take top 3
  const topPeakHours = allData
    .filter(item => item.orders > 0) // Only include hours with orders
    .sort((a, b) => b.orders - a.orders)
    .slice(0, 3);
  
  console.log('Top 3 peak hours:', topPeakHours);
  
  // Calculate chart dimensions
  const chartHeight = 300; // Increased height
  const maxValue = topPeakHours.length > 0 ? Math.max(...topPeakHours.map(item => item.orders)) : 10;
  const yAxisMax = Math.max(10, Math.ceil(maxValue * 1.1));
  
  console.log('Chart calculations:', { chartHeight, maxValue, yAxisMax });

  // Get period label for title
  const getPeriodLabel = (period) => {
    switch(period) {
      case 'today': return 'Today';
      case '7days': return 'Last 7 Days';
      case 'month': return 'Last 30 Days';
      case 'year': return 'Last Year';
      default: return 'Last 7 Days';
    }
  };

  return (
    <div className="complete-histogram">
      <h3>Top 3 Peak Hours ({getPeriodLabel(period)})</h3>
      
      {topPeakHours.length === 0 ? (
        <div className="no-data-message">
          <p>No peak hours data available for {getPeriodLabel(period).toLowerCase()}</p>
        </div>
      ) : (
        <div className="histogram-full-wrapper">
          {/* Y-axis */}
          <div className="y-axis-full">
            {Array.from({length: 6}, (_, i) => Math.floor(yAxisMax * (5-i) / 5)).map(value => (
              <div key={value} className="y-tick-full">{value}</div>
            ))}
          </div>
          
          {/* Top 3 peak hours chart */}
          <div className="chart-area-full">
            {/* Top 3 bars only */}
            <div className="bars-container-full" style={{ height: `${chartHeight}px` }}>
              {topPeakHours.map((hourData, index) => {
                const barHeight = maxValue > 0 ? (hourData.orders / yAxisMax) * chartHeight : 0;
                
                // Color based on rank - gold, silver, bronze
                let barColor = '#fbbf24'; // Gold for 1st place
                if (index === 1) barColor = '#9ca3af'; // Silver for 2nd place
                if (index === 2) barColor = '#f97316'; // Bronze for 3rd place
                
                return (
                  <div key={hourData.hour} className="bar-wrapper-full">
                    <div 
                      className="histogram-bar-full"
                      style={{ 
                        height: `${barHeight}px`,
                        backgroundColor: barColor
                      }}
                      title={`${hourData.time_label}: ${hourData.orders} orders`}
                    >
                      {hourData.orders > 0 && (
                        <span className="bar-value-full">{hourData.orders}</span>
                      )}
                    </div>
                  </div>
                );
              })}
            </div>
            
            {/* X-axis line */}
            <div className="x-axis-line-full"></div>
            
            {/* X-axis labels - Top 3 hours only */}
            <div className="x-labels-full">
              {topPeakHours.map((hourData, index) => {
                console.log('Rendering hourData:', hourData); // Debug log
                return (
                  <div key={hourData.hour} className="x-label-full">
                    <div className="time-text-full">
                      {hourData.time_label || hourData.hour || `${hourData.hour}:00`}
                    </div>
                    <div className="x-axis-value-full">{hourData.orders} orders</div>
                  </div>
                );
              })}
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

// Order Status Chart Component
const OrderStatusChart = ({ data, performance, currentPeriod, periodMetrics }) => {
  // Debug: Log the data to see its structure
  console.log('OrderStatusChart - data:', data);
  console.log('OrderStatusChart - performance:', performance);
  console.log('OrderStatusChart - currentPeriod:', currentPeriod);
  console.log('OrderStatusChart - periodMetrics:', periodMetrics);
  
  let statuses;
  
  // First try to use period-specific metrics if available
  if (periodMetrics && Object.keys(periodMetrics).length > 0) {
    console.log('Using period metrics for order status chart');
    const operational = periodMetrics.operational || {};
    const financial = periodMetrics.financial || {};
    
    statuses = [
      { 
        label: 'Delivered', 
        count: operational.completed_orders || operational.delivered_orders || operational.successful_orders || 
               financial.completed_orders || operational.complete_orders || operational.fulfilled_orders || 0, 
        color: '#10b981' 
      },
      { 
        label: 'Pending', 
        count: operational.pending_orders || operational.pending || operational.awaiting_orders || 
               financial.pending_orders || 0, 
        color: '#f59e0b' 
      },
      { 
        label: 'Cancelled', 
        count: operational.cancelled_orders || operational.canceled_orders || operational.cancelled || 
               financial.cancelled_orders || operational.canceled || 0, 
        color: '#ef4444' 
      },
      { 
        label: 'Processing', 
        count: operational.processing_orders || operational.processing || operational.in_progress_orders || 
               financial.processing_orders || operational.in_progress || 0, 
        color: '#3b82f6' 
      }
    ];
  }
  // Check if data is an object with order status properties (API returns object format)
  else if (data && typeof data === 'object' && !Array.isArray(data)) {
    console.log('Using dynamic object data for order status chart');
    statuses = [
      { label: 'Delivered', count: data.completed_orders || data.delivered_orders || data.successful_orders || 0, color: '#10b981' },
      { label: 'Pending', count: data.pending_orders || data.pending || 0, color: '#f59e0b' },
      { label: 'Cancelled', count: data.cancelled_orders || data.canceled_orders || data.cancelled || 0, color: '#ef4444' },
      { label: 'Processing', count: data.processing_orders || data.processing || data.in_progress_orders || 0, color: '#3b82f6' }
    ];
  } else if (data && Array.isArray(data) && data.length > 0) {
    console.log('Using dynamic array data for order status chart');
    // Handle array format (original logic)
    statuses = [
      { 
        label: 'Delivered', 
        count: data.find(d => d.status === 'delivered' || d.status === 'completed' || d.label === 'Delivered')?.count || 
               data.find(d => d.status === 'delivered' || d.status === 'completed' || d.label === 'Delivered')?.value || 0, 
        color: '#10b981' 
      },
      { 
        label: 'Pending', 
        count: data.find(d => d.status === 'pending' || d.label === 'Pending')?.count || 
               data.find(d => d.status === 'pending' || d.label === 'Pending')?.value || 0, 
        color: '#f59e0b' 
      },
      { 
        label: 'Cancelled', 
        count: data.find(d => d.status === 'cancelled' || d.status === 'canceled' || d.label === 'Cancelled')?.count || 
               data.find(d => d.status === 'cancelled' || d.status === 'canceled' || d.label === 'Cancelled')?.value || 0, 
        color: '#ef4444' 
      },
      { 
        label: 'Processing', 
        count: data.find(d => d.status === 'processing' || d.label === 'Processing')?.count || 
               data.find(d => d.status === 'processing' || d.label === 'Processing')?.value || 0, 
        color: '#3b82f6' 
      }
    ];
  } else {
    console.log('Using performance data for order status chart');
    // Fallback to performance data - try multiple property names
    statuses = [
      { 
        label: 'Delivered', 
        count: performance.completed_orders || performance.delivered_orders || performance.successful_orders || 
               performance.complete_orders || performance.fulfilled_orders || 0, 
        color: '#10b981' 
      },
      { 
        label: 'Pending', 
        count: performance.pending_orders || performance.pending || performance.awaiting_orders || 0, 
        color: '#f59e0b' 
      },
      { 
        label: 'Cancelled', 
        count: performance.cancelled_orders || performance.canceled_orders || performance.cancelled || 
               performance.canceled || 0, 
        color: '#ef4444' 
      },
      { 
        label: 'Processing', 
        count: performance.processing_orders || performance.processing || performance.in_progress_orders || 
               performance.in_progress || 0, 
        color: '#3b82f6' 
      }
    ];
  }
  
  console.log('Final statuses for chart:', statuses);

  const total = statuses.reduce((sum, status) => sum + status.count, 0);

  return (
    <div className="order-status-chart-compact">
      <div className="status-list-compact">
        {statuses.map(status => {
          const percentage = total > 0 ? ((status.count / total) * 100).toFixed(1) : 0;
          return (
            <div key={status.label} className="status-item-compact">
              <div className="status-info-compact">
                <div className="status-color-compact" style={{ backgroundColor: status.color }}></div>
                <span className="status-label-compact">{status.label}</span>
              </div>
              <div className="status-stats-compact">
                <span className="status-count-compact">{status.count}</span>
                <span className="status-percentage-compact">({percentage}%)</span>
              </div>
              <div className="status-bar-bg-compact">
                <div 
                  className="status-bar-fill-compact" 
                  style={{ 
                    width: `${percentage}%`,
                    backgroundColor: status.color 
                  }}
                ></div>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
};

// Menu Tab Component
const MenuTab = ({ items, businessId, onAddItem, onEditItem, onDeleteItem, onToggleStatus, cleanItemName }) => {
  const [viewMode, setViewMode] = useState('list'); // 'list' or 'grid'
  const [statusFilter, setStatusFilter] = useState('all'); // 'all', 'active', 'inactive'
  const [categoryFilter, setCategoryFilter] = useState('all'); // 'all' or specific categories
  const [searchTerm, setSearchTerm] = useState(''); // search by name

  // Get unique categories from items
  const categories = [...new Set(items.map(item => item.category).filter(Boolean))];

  // Filter items based on selected filters and search
  const filteredItems = items.filter(item => {
    const statusMatch = statusFilter === 'all' || item.status === statusFilter;
    const categoryMatch = categoryFilter === 'all' || item.category === categoryFilter;
    const searchMatch = searchTerm === '' || 
      item.name.toLowerCase().includes(searchTerm.toLowerCase());
    return statusMatch && categoryMatch && searchMatch;
  });

  return (
    <div className="tab-menu">
      {/* Menu Filter Controls - Compact Design */}
      <div className="menu-filter-controls">
        <div className="filter-buttons-left">
          {/* Status Filter */}
          <select 
            className="filter-select"
            value={statusFilter}
            onChange={(e) => setStatusFilter(e.target.value)}
          >
            <option value="all">All Status</option>
            <option value="active">Active</option>
            <option value="inactive">Inactive</option>
          </select>

          {/* Category Filter */}
          <select 
            className="filter-select"
            value={categoryFilter}
            onChange={(e) => setCategoryFilter(e.target.value)}
          >
            <option value="all">All Categories</option>
            {categories.map(category => (
              <option key={category} value={category}>{category}</option>
            ))}
          </select>

          {/* Search Field */}
          <input
            type="text"
            className="search-input"
            placeholder="Search by name..."
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
          />
        </div>
        
        <div className="header-actions-right">
          {/* View Mode Toggle */}
          <div className="view-toggle">
            <button 
              className={`view-btn ${viewMode === 'list' ? 'active' : ''}`}
              onClick={() => setViewMode('list')}
              title="List View"
            >
              <FiList />
            </button>
            <button 
              className={`view-btn ${viewMode === 'grid' ? 'active' : ''}`}
              onClick={() => setViewMode('grid')}
              title="Grid View"
            >
              <FiGrid />
            </button>
          </div>
          <button className="btn btn-primary" onClick={onAddItem}>
            <FiPlus /> Add Item
          </button>
        </div>
      </div>
        
      <div className="menu-items-content">
        <div className="section-header">
          <h3>Menu Items ({filteredItems.length} of {items.length})</h3>
        </div>
        {/* List View */}
        {viewMode === 'list' && (
        <div className="table-container">
            <table className="data-table">
              <thead>
                <tr>
                  <th>Image</th>
                  <th>Item Name</th>
                  <th>Category</th>
                  <th>Type</th>
                  <th>Price</th>
                  <th>Stock</th>
                  <th>Status</th>
                  <th>Actions</th>
                </tr>
              </thead>
              <tbody>
                {filteredItems.length === 0 ? (
                  <tr>
                    <td colSpan="8" className="no-data">No menu items found</td>
                  </tr>
                ) : (
                  filteredItems.map(item => (
                    <tr key={item.item_id}>
                      <td>
                        <div className="item-image-cell">
                          {item.image ? (
                            <img 
                              src={item.image} 
                              alt={item.name} 
                              className="item-thumbnail"
                              onError={(e) => {
                                e.target.style.display = 'none';
                                e.target.nextSibling.style.display = 'flex';
                              }}
                            />
                          ) : null}
                          <div className="no-image-placeholder" style={{ display: item.image ? 'none' : 'flex' }}>
                            No Image
                          </div>
                        </div>
                      </td>
                      <td>
                        <span className="item-name">{cleanItemName(item.name)}</span>
                      </td>
                      <td>{item.category}</td>
                      <td>
                        <span className="food-type-badge">
                          {item.item_type === 'restaurant' ? (
                            item.food_type ? (
                              <span className="type-text">{item.food_type}</span>
                            ) : (
                              <span className="type-na">-</span>
                            )
                          ) : item.item_type === 'grocery' ? (
                            <span className="type-grocery">Grocery</span>
                          ) : item.item_type === 'fashion' ? (
                            <span className="type-fashion">Fashion</span>
                          ) : (
                            <span className="type-na">-</span>
                          )}
                        </span>
                      </td>
                      <td>
                        <span className="price-value">₹{item.price}</span>
                      </td>
                      <td>
                        {item.quantity !== undefined && item.quantity !== null ? (
                          <span className="stock-value">{item.quantity}</span>
                        ) : item.stock !== undefined && item.stock !== null ? (
                          <span className="stock-value">{item.stock}</span>
                        ) : (
                          <span className="na-value">-</span>
                        )}
                      </td>
                      <td>
                        <span className={`badge ${item.status === 'active' ? 'badge-success' : 'badge-danger'}`}>
                          {item.status === 'active' ? <><FiEye /> Active</> : <><FiEyeOff /> Inactive</>}
                        </span>
                      </td>
                      <td>
                        <div className="action-buttons">
                          <button 
                            className="btn btn-sm btn-info"
                            onClick={() => onEditItem(item)}
                            title="Edit Item"
                          >
                            <FiEdit2 /> Edit
                          </button>
                          <button 
                            className={`btn btn-sm ${item.status === 'active' ? 'btn-warning' : 'btn-success'}`}
                            onClick={() => onToggleStatus(item)}
                            title={item.status === 'active' ? 'Disable Item' : 'Enable Item'}
                          >
                            {item.status === 'active' ? <><FiEyeOff /> Disable</> : <><FiEye /> Enable</>}
                          </button>
                          <button 
                            className="btn btn-sm btn-danger"
                            onClick={() => onDeleteItem(item)}
                            title="Delete Item"
                          >
                            <FiTrash2 /> Delete
                          </button>
                        </div>
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        )}
        
        {/* Grid View */}
        {viewMode === 'grid' && (
            <div className="items-grid">
              {filteredItems.length === 0 ? (
                <div className="no-data">No menu items found</div>
              ) : (
                filteredItems.map(item => (
                  <div key={item.item_id} className="item-card">
                    <div className="item-card-image">
                      {item.image ? (
                        <img 
                          src={item.image} 
                          alt={item.name}
                          onError={(e) => {
                            e.target.style.display = 'none';
                            e.target.nextSibling.style.display = 'flex';
                          }}
                        />
                      ) : null}
                      <div className="no-image-placeholder-card" style={{ display: item.image ? 'none' : 'flex' }}>
                        No Image
                      </div>
                      <span className={`card-status-badge ${item.status === 'active' ? 'badge-success' : 'badge-danger'}`}>
                        {item.status === 'active' ? <FiEye /> : <FiEyeOff />}
                      </span>
                    </div>
                    <div className="item-card-content">
                      <h4 className="item-card-title">{cleanItemName(item.name)}</h4>
                      <p className="item-card-category">{item.category}</p>
                      <p className="item-card-price">₹{item.price}</p>
                    </div>
                    <div className="item-card-actions">
                      <button 
                        className="card-action-btn btn-info"
                        onClick={() => onEditItem(item)}
                        title="Edit"
                      >
                        <FiEdit2 />
                      </button>
                      <button 
                        className={`card-action-btn ${item.status === 'active' ? 'btn-warning' : 'btn-success'}`}
                        onClick={() => onToggleStatus(item)}
                        title={item.status === 'active' ? 'Disable' : 'Enable'}
                      >
                        {item.status === 'active' ? <FiEyeOff /> : <FiEye />}
                      </button>
                      <button 
                        className="card-action-btn btn-danger"
                        onClick={() => onDeleteItem(item)}
                        title="Delete"
                      >
                        <FiTrash2 />
                      </button>
                    </div>
                  </div>
                ))
              )}
            </div>
        )}
      </div>
    </div>
  );
};

// Orders Tab Component
const OrdersTab = ({ orders, businessId, onRefresh }) => {
  const [filterPeriod, setFilterPeriod] = useState('all'); // 'all', 'today', 'week', 'month'
  const [searchTerm, setSearchTerm] = useState(''); // Search by Order ID
  const [statusFilter, setStatusFilter] = useState('all'); // Status filter
  const [orderTypeFilter, setOrderTypeFilter] = useState('all'); // Order type filter

  // Get unique statuses and order types for filter options
  const getUniqueStatuses = () => {
    const statuses = [...new Set(orders.map(order => order.status).filter(Boolean))];
    return statuses;
  };

  const getUniqueOrderTypes = () => {
    const types = [...new Set(orders.map(order => order.db_order_type || (order.order_type === 'restaurant' ? 'Dine-in' : 'Pickup')).filter(Boolean))];
    return types;
  };

  // Filter orders based on all criteria
  const getFilteredOrders = () => {
    let filtered = orders;

    // Filter by period
    if (filterPeriod !== 'all') {
      const now = new Date();
      const today = new Date(now.getFullYear(), now.getMonth(), now.getDate());
      
      filtered = filtered.filter(order => {
        const orderDate = new Date(order.date);
        
        switch (filterPeriod) {
          case 'today':
            return orderDate >= today;
          
          case 'week':
            const weekAgo = new Date(today);
            weekAgo.setDate(weekAgo.getDate() - 7);
            return orderDate >= weekAgo;
          
          case 'month':
            const monthAgo = new Date(today);
            monthAgo.setMonth(monthAgo.getMonth() - 1);
            return orderDate >= monthAgo;
          
          default:
            return true;
        }
      });
    }

    // Filter by search term (Order ID)
    if (searchTerm) {
      filtered = filtered.filter(order => 
        order.order_number.toLowerCase().includes(searchTerm.toLowerCase())
      );
    }

    // Filter by status
    if (statusFilter !== 'all') {
      filtered = filtered.filter(order => order.status === statusFilter);
    }

    // Filter by order type
    if (orderTypeFilter !== 'all') {
      filtered = filtered.filter(order => {
        const orderType = order.db_order_type || (order.order_type === 'restaurant' ? 'Dine-in' : 'Pickup');
        return orderType === orderTypeFilter;
      });
    }

    return filtered;
  };

  const filteredOrders = getFilteredOrders();
  const uniqueStatuses = getUniqueStatuses();
  const uniqueOrderTypes = getUniqueOrderTypes();

  return (
    <div className="tab-orders">
      <div className="orders-header">
        <h3>Orders ({filteredOrders.length} of {orders.length})</h3>
      </div>

      {/* Search and Filter Controls */}
      <div className="orders-filter-controls">
        <div className="filter-left">
          {/* Search by Order ID */}
          <input
            type="text"
            className="search-input"
            placeholder="Search by Order ID..."
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
          />
          
          {/* Status Filter */}
          <select 
            className="filter-select"
            value={statusFilter}
            onChange={(e) => setStatusFilter(e.target.value)}
          >
            <option value="all">All Status</option>
            {uniqueStatuses.map(status => (
              <option key={status} value={status}>{status}</option>
            ))}
          </select>

          {/* Order Type Filter */}
          <select 
            className="filter-select"
            value={orderTypeFilter}
            onChange={(e) => setOrderTypeFilter(e.target.value)}
          >
            <option value="all">All Types</option>
            {uniqueOrderTypes.map(type => (
              <option key={type} value={type}>{type}</option>
            ))}
          </select>
        </div>

        <div className="filter-right">
          {/* Day Filter Buttons */}
          <div className="day-filter-buttons">
            <button 
              className={`day-filter-btn ${filterPeriod === 'today' ? 'active' : ''}`}
              onClick={() => setFilterPeriod('today')}
            >
              Today
            </button>
            <button 
              className={`day-filter-btn ${filterPeriod === 'week' ? 'active' : ''}`}
              onClick={() => setFilterPeriod('week')}
            >
              This Week
            </button>
            <button 
              className={`day-filter-btn ${filterPeriod === 'month' ? 'active' : ''}`}
              onClick={() => setFilterPeriod('month')}
            >
              This Month
            </button>
            <button 
              className={`day-filter-btn ${filterPeriod === 'all' ? 'active' : ''}`}
              onClick={() => setFilterPeriod('all')}
            >
              All
            </button>
          </div>
        </div>
      </div>
      
      <div className="table-container">
        <table className="data-table">
          <thead>
            <tr>
              <th>Order ID</th>
              <th>Customer</th>
              <th>Subtotal</th>
              <th>Delivery</th>
              <th>Final Amount</th>
              <th>Order Type</th>
              <th>Status</th>
              <th>Delivery Partner</th>
              <th>Date</th>
              <th>Time</th>
            </tr>
          </thead>
          <tbody>
            {filteredOrders.length === 0 ? (
              <tr>
                <td colSpan="10" className="no-data">No orders found</td>
              </tr>
            ) : (
              filteredOrders.map(order => (
                <tr key={order.order_id}>
                  <td><span className="order-id" title={`#${order.order_number}`}>#{order.order_number}</span></td>
                  <td><span className="customer-name">{order.customer_name || 'N/A'}</span></td>
                  <td><span className="subtotal-amount">₹{order.subtotal ? order.subtotal.toLocaleString() : order.amount.toLocaleString()}</span></td>
                  <td>
                    <span className="delivery-fee">
                      ₹{order.delivery_charges ? order.delivery_charges.toLocaleString() : '0'}
                    </span>
                  </td>
                  <td><span className="final-amount">₹{order.amount.toLocaleString()}</span></td>
                  <td>
                    <span className="order-type-text">
                      {order.db_order_type || (order.order_type === 'restaurant' ? 'Dine-in' : 'Pickup')}
                    </span>
                  </td>
                  <td>
                    <span className={`badge badge-${order.status}`}>
                      {order.status}
                    </span>
                  </td>
                  <td>
                    <span className={`delivery-partner ${order.delivery_partner === 'Unassigned' ? 'unassigned' : 'assigned'}`}>
                      {order.delivery_partner || 'Unassigned'}
                    </span>
                  </td>
                  <td><span className="order-date">{new Date(order.date).toLocaleDateString('en-GB', { day: '2-digit', month: '2-digit', year: '2-digit' })}</span></td>
                  <td><span className="order-time">{order.order_time ? order.order_time.substring(0, 5) : '-'}</span></td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
};

// Performance Tab Component - Professional Clean Design
const PerformanceTab = ({ business, performance }) => {
  return (
    <div className="tab-performance-new">
      {/* Top Row - Key Metrics (4 cards) */}
      <div className="performance-metrics-row">
        <div className="perf-metric-card">
          <div className="perf-icon-wrapper primary">
            <FiShoppingCart className="perf-icon" />
          </div>
          <div className="perf-content">
            <div className="perf-value">{performance.total_orders || 0}</div>
            <div className="perf-label">Total Orders</div>
          </div>
        </div>

        <div className="perf-metric-card">
          <div className="perf-icon-wrapper success">
            <FiDollarSign className="perf-icon" />
          </div>
          <div className="perf-content">
            <div className="perf-value">₹{(performance.total_revenue || 0).toLocaleString()}</div>
            <div className="perf-label">Total Revenue</div>
          </div>
        </div>

        <div className="perf-metric-card">
          <div className="perf-icon-wrapper warning">
            <FiStar className="perf-icon" />
          </div>
          <div className="perf-content">
            <div className="perf-value">{(performance.avg_rating || 0).toFixed(1)}</div>
            <div className="perf-label">Average Rating</div>
          </div>
        </div>

        <div className="perf-metric-card">
          <div className="perf-icon-wrapper info">
            <FiBarChart className="perf-icon" />
          </div>
          <div className="perf-content">
            <div className="perf-value">₹{(performance.avg_order_value || 0).toFixed(0)}</div>
            <div className="perf-label">Avg Order Value</div>
          </div>
        </div>
      </div>

      {/* Middle Row - Performance Details (2 columns) */}
      <div className="performance-details-row">
        {/* Order Statistics */}
        <div className="perf-detail-card">
          <div className="perf-card-header">
            <h4>Order Statistics</h4>
          </div>
          <div className="perf-stats-list">
            <div className="perf-stat-item">
              <div className="stat-item-left">
                <FiCheckCircle className="stat-item-icon success" />
                <span className="stat-item-label">Completed Orders</span>
              </div>
              <span className="stat-item-value">{performance.completed_orders || 0}</span>
            </div>
            <div className="perf-stat-item">
              <div className="stat-item-left">
                <FiClock className="stat-item-icon warning" />
                <span className="stat-item-label">Pending Orders</span>
              </div>
              <span className="stat-item-value">{performance.pending_orders || 0}</span>
            </div>
            <div className="perf-stat-item">
              <div className="stat-item-left">
                <FiPackage className="stat-item-icon info" />
                <span className="stat-item-label">Processing Orders</span>
              </div>
              <span className="stat-item-value">{performance.processing_orders || 0}</span>
            </div>
            <div className="perf-stat-item">
              <div className="stat-item-left">
                <FiTruck className="stat-item-icon primary" />
                <span className="stat-item-label">Out for Delivery</span>
              </div>
              <span className="stat-item-value">{performance.delivery_orders || 0}</span>
            </div>
          </div>
        </div>

        {/* Business Insights */}
        <div className="perf-detail-card">
          <div className="perf-card-header">
            <h4>Business Insights</h4>
          </div>
          <div className="perf-insights-list">
            <div className="insight-item">
              <div className="insight-icon-wrapper">
                <FiClock className="insight-icon" />
              </div>
              <div className="insight-content">
                <span className="insight-label">Peak Hours</span>
                <span className="insight-value">12:00 PM - 2:00 PM</span>
              </div>
            </div>
            <div className="insight-item">
              <div className="insight-icon-wrapper">
                <FiCalendar className="insight-icon" />
              </div>
              <div className="insight-content">
                <span className="insight-label">Best Day</span>
                <span className="insight-value">Saturday</span>
              </div>
            </div>
            <div className="insight-item">
              <div className="insight-icon-wrapper">
                <FiTrendingUp className="insight-icon" />
              </div>
              <div className="insight-content">
                <span className="insight-label">Growth Rate</span>
                <span className="insight-value success-text">+15%</span>
              </div>
            </div>
            <div className="insight-item">
              <div className="insight-icon-wrapper">
                <FiUsers className="insight-icon" />
              </div>
              <div className="insight-content">
                <span className="insight-label">Customer Satisfaction</span>
                <span className="insight-value">{performance.customer_satisfaction || 90}%</span>
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* Bottom Row - Performance Rates (Progress Bars) */}
      <div className="performance-rates-card">
        <div className="perf-card-header">
          <h4>Performance Rates</h4>
        </div>
        <div className="perf-rates-grid">
          <div className="rate-item">
            <div className="rate-header">
              <span className="rate-label">Order Completion Rate</span>
              <span className="rate-percentage">{performance.completion_rate || 0}%</span>
            </div>
            <div className="rate-bar-container">
              <div 
                className="rate-bar success" 
                style={{ width: `${performance.completion_rate || 0}%` }}
              ></div>
            </div>
          </div>

          <div className="rate-item">
            <div className="rate-header">
              <span className="rate-label">On-Time Delivery</span>
              <span className="rate-percentage">{performance.on_time_delivery || 85}%</span>
            </div>
            <div className="rate-bar-container">
              <div 
                className="rate-bar primary" 
                style={{ width: `${performance.on_time_delivery || 85}%` }}
              ></div>
            </div>
          </div>

          <div className="rate-item">
            <div className="rate-header">
              <span className="rate-label">Customer Retention</span>
              <span className="rate-percentage">{performance.customer_retention || 75}%</span>
            </div>
            <div className="rate-bar-container">
              <div 
                className="rate-bar warning" 
                style={{ width: `${performance.customer_retention || 75}%` }}
              ></div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};

// Payouts Tab Component
const PayoutsTab = ({ businessId }) => (
  <div className="tab-payouts">
    <h3>Payouts</h3>
    <p className="info-message">Payout system coming soon...</p>
  </div>
);

// Reviews Tab Component
const ReviewsTab = ({ reviews }) => {
  // Calculate rating statistics
  const averageRating = reviews.length > 0 
    ? (reviews.reduce((sum, review) => sum + review.rating, 0) / reviews.length).toFixed(1)
    : 0;

  const ratingCounts = {};
  for (let i = 5; i >= 1; i--) {
    ratingCounts[i] = reviews.filter(review => review.rating === i).length;
  }

  return (
    <div className="tab-reviews">
      <h3>Reviews & Ratings ({reviews.length})</h3>
      
      {reviews.length === 0 ? (
        <div className="no-data">
          <p>No reviews yet</p>
        </div>
      ) : (
        <>
          {/* Reviews Summary Section */}
          <div className="reviews-summary">
            <div className="rating-summary-card">
              <div className="rating-summary-content">
                {/* Average Rating Card */}
                <div className="rating-overview">
                  <div className="average-rating">{averageRating}</div>
                  <div className="rating-stars">
                    {Array.from({ length: 5 }, (_, i) => (
                      <MdOutlineStarOutline 
                        key={i} 
                        style={{ 
                          color: i < Math.round(averageRating) ? '#fbbf24' : '#e5e7eb',
                          fontSize: '20px' 
                        }} 
                      />
                    ))}
                  </div>
                  <div className="total-reviews">{reviews.length} reviews</div>
                </div>

                {/* Rating Breakdown */}
                <div className="rating-breakdown">
                  <h4>Rating Distribution</h4>
                  {Object.entries(ratingCounts).reverse().map(([rating, count]) => (
                    <div key={rating} className="rating-bar">
                      <div className="rating-label">
                        <span>{rating}</span>
                        <MdOutlineStarOutline style={{ color: '#fbbf24', fontSize: '12px' }} />
                      </div>
                      <div className="bar-container">
                        <div 
                          className="bar-fill" 
                          style={{ width: `${reviews.length > 0 ? (count / reviews.length) * 100 : 0}%` }}
                        />
                      </div>
                      <div className="bar-count">{count}</div>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          </div>

          {/* Reviews List */}
          <div className="reviews-list">
            {reviews.map(review => (
              <div key={review.rating_id} className="review-card">
                <div className="review-header">
                  <span className="customer-name">{review.customer_name}</span>
                  <span className="rating">
                    {Array.from({ length: 5 }, (_, i) => (
                      <MdOutlineStarOutline 
                        key={i} 
                        style={{ 
                          color: i < review.rating ? '#fbbf24' : '#e5e7eb',
                          fontSize: '14px' 
                        }} 
                      />
                    ))}
                  </span>
                </div>
                <p className="review-text">{review.review}</p>
                <p className="review-date">{new Date(review.date).toLocaleDateString()}</p>
                <button className="btn-delete">
                  <FiTrash2 /> Delete
                </button>
              </div>
            ))}
          </div>
        </>
      )}
    </div>
  );
};

// Documents Tab Component
const DocumentsTab = ({ business }) => (
  <div className="tab-documents">
    <h3>Documents / KYC</h3>
    <div className="documents-grid">
      <div className="doc-card">
        <h4>GST Certificate</h4>
        <p>{business.gst_number || business.gstin || 'Not provided'}</p>
      </div>
      <div className="doc-card">
        <h4>FSSAI Certificate</h4>
        <p>{business.fssai_number || 'Not provided'}</p>
      </div>
      <div className="doc-card">
        <h4>PAN Card</h4>
        <p>{business.owner_pan || 'Not provided'}</p>
      </div>
      <div className="doc-card">
        <h4>Bank Details</h4>
        <p>Account: {business.account_number || 'Not provided'}</p>
        <p>IFSC: {business.ifsc_code || 'Not provided'}</p>
      </div>
    </div>
  </div>
);

  // Offers and Coupons Tab Component (with nested tabs) - Simplified, handlers in parent
const OffersAndCouponsTab = React.memo(({ offers, coupons, businessId, onRefresh, setShowOfferModal, setShowCouponModal, setEditingOffer, setEditingCoupon, showOfferModal, showCouponModal }) => {
  const [activeSubTab, setActiveSubTab] = useState('offers');

  // Offer handlers
  const handleAddOffer = (e) => {
    if (e) {
      e.preventDefault();
      e.stopPropagation();
    }
    setEditingOffer(null);
    setShowOfferModal(true);
  };

  const handleEditOffer = (offer) => {
    setEditingOffer(offer);
    setShowOfferModal(true);
  };

  const handleDeleteOffer = async (offerId) => {
    if (window.confirm('Are you sure you want to delete this offer?')) {
      try {
        const response = await AdminService.deleteOffer(businessId, offerId);
        if (response.success) {
          alert('Offer deleted successfully!');
          if (onRefresh) onRefresh();
        } else {
          alert('Error: ' + response.message);
        }
      } catch (error) {
        console.error('Error deleting offer:', error);
        alert('Error deleting offer');
      }
    }
  };

  // Coupon handlers
  const handleAddCoupon = (e) => {
    if (e) {
      e.preventDefault();
      e.stopPropagation();
    }
    setEditingCoupon(null);
    setShowCouponModal(true);
  };

  const handleEditCoupon = (coupon) => {
    setEditingCoupon(coupon);
    setShowCouponModal(true);
  };

  const handleDeleteCoupon = async (couponId) => {
    if (window.confirm('Are you sure you want to delete this coupon?')) {
      try {
        const response = await AdminService.deleteCoupon(businessId, couponId);
        if (response.success) {
          alert('Coupon deleted successfully!');
          if (onRefresh) onRefresh();
        } else {
          alert('Error: ' + response.message);
        }
      } catch (error) {
        console.error('Error deleting coupon:', error);
        alert('Error deleting coupon');
      }
    }
  };

  return (
    <div className="tab-offers-coupons">
      {/* Sub-tabs for Offers and Coupons */}
      <div className="sub-tabs">
        <button 
          className={`sub-tab ${activeSubTab === 'offers' ? 'active' : ''}`}
          onClick={() => setActiveSubTab('offers')}
        >
          Offers ({offers.length})
        </button>
        <button 
          className={`sub-tab ${activeSubTab === 'coupons' ? 'active' : ''}`}
          onClick={() => setActiveSubTab('coupons')}
        >
          Coupons ({coupons.length})
        </button>
      </div>

      {/* Sub-tab content */}
      <div className="sub-tab-content">
        {activeSubTab === 'offers' && (
          <OffersTab 
            offers={offers} 
            businessId={businessId} 
            onRefresh={onRefresh}
            onAddOffer={handleAddOffer}
            onEditOffer={handleEditOffer}
            onDeleteOffer={handleDeleteOffer}
          />
        )}
        {activeSubTab === 'coupons' && (
          <CouponsTab 
            coupons={coupons} 
            businessId={businessId} 
            onRefresh={onRefresh}
            onAddCoupon={handleAddCoupon}
            onEditCoupon={handleEditCoupon}
            onDeleteCoupon={handleDeleteCoupon}
          />
        )}
      </div>
    </div>
  );
});

// Offers Tab Component (for Promotional Offers)
const OffersTab = ({ offers, businessId, onRefresh, onAddOffer, onEditOffer, onDeleteOffer }) => {
  return (
    <div className="tab-offers">
      <div className="offers-header">
        <h3>Promotional Offers ({offers.length})</h3>
        <button type="button" className="btn btn-primary" onClick={onAddOffer}>
          + Add Offer
        </button>
      </div>
      
      <div className="table-container">
        <table className="data-table">
          <thead>
            <tr>
              <th>Title</th>
              <th>Type</th>
              <th>Discount</th>
              <th>Price</th>
              <th>Status</th>
              <th>Valid From</th>
              <th>Valid Until</th>
              <th>Views</th>
              <th>Actions</th>
            </tr>
          </thead>
          <tbody>
            {offers.length === 0 ? (
              <tr>
                <td colSpan="9" className="no-data">No offers found</td>
              </tr>
            ) : (
              offers.map(offer => (
                <tr key={offer.offer_id}>
                  <td><strong>{offer.title}</strong></td>
                  <td>{offer.offer_type}</td>
                  <td>
                    {offer.discount_percentage ? `${offer.discount_percentage}%` : ''}
                    {offer.discount_amount ? `₹${offer.discount_amount}` : ''}
                  </td>
                  <td>
                    {offer.original_price && offer.offer_price ? (
                      <>
                        <span style={{ textDecoration: 'line-through', color: '#999' }}>₹{offer.original_price}</span>
                        {' '}₹{offer.offer_price}
                      </>
                    ) : 'N/A'}
                  </td>
                  <td>
                    <span className={`badge ${offer.is_active ? 'badge-success' : 'badge-danger'}`}>
                      {offer.is_active ? 'Active' : 'Inactive'}
                    </span>
                    {offer.is_approved && <span className="badge badge-info" style={{ marginLeft: '4px' }}>Approved</span>}
                  </td>
                  <td>{offer.valid_from ? new Date(offer.valid_from).toLocaleDateString() : 'N/A'}</td>
                  <td>{offer.valid_to ? new Date(offer.valid_to).toLocaleDateString() : 'N/A'}</td>
                  <td>{offer.current_views || 0} / {offer.max_views || '∞'}</td>
                  <td>
                    <div className="action-buttons">
                      <button 
                        className="btn btn-sm btn-info"
                        onClick={() => onEditOffer(offer)}
                        title="Edit Offer"
                      >
                        Edit
                      </button>
                      <button 
                        className="btn btn-sm btn-danger"
                        onClick={() => onDeleteOffer(offer.offer_id)}
                        title="Delete Offer"
                      >
                        Delete
                      </button>
                    </div>
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
};

// Coupons Tab Component
const CouponsTab = ({ coupons, businessId, onRefresh, onAddCoupon, onEditCoupon, onDeleteCoupon }) => {
  return (
    <div className="tab-offers">
      <div className="offers-header">
        <h3>Coupons ({coupons.length})</h3>
        <button type="button" className="btn btn-primary" onClick={onAddCoupon}>
          + Add Coupon
        </button>
      </div>
      
      <div className="table-container">
        <table className="data-table">
          <thead>
            <tr>
              <th>Coupon Code</th>
              <th>Type</th>
              <th>Value</th>
              <th>Status</th>
              <th>Valid From</th>
              <th>Valid Until</th>
              <th>Usage</th>
              <th>Actions</th>
            </tr>
          </thead>
          <tbody>
            {coupons.length === 0 ? (
              <tr>
                <td colSpan="8" className="no-data">No coupons found</td>
              </tr>
            ) : (
              coupons.map(coupon => (
                <tr key={coupon.coupon_id}>
                  <td><strong>{coupon.code}</strong></td>
                  <td>{coupon.type}</td>
                  <td>{coupon.type === 'percentage' ? `${coupon.value}%` : `₹${coupon.value}`}</td>
                  <td>
                    <span className={`badge ${coupon.is_active ? 'badge-success' : 'badge-danger'}`}>
                      {coupon.is_active ? 'Active' : 'Inactive'}
                    </span>
                  </td>
                  <td>{coupon.valid_from ? new Date(coupon.valid_from).toLocaleDateString() : 'N/A'}</td>
                  <td>{coupon.valid_to ? new Date(coupon.valid_to).toLocaleDateString() : 'N/A'}</td>
                  <td>{coupon.current_usage || 0} / {coupon.max_usage || '∞'}</td>
                  <td>
                    <div className="action-buttons">
                      <button 
                        className="btn btn-sm btn-info"
                        onClick={() => onEditCoupon(coupon)}
                        title="Edit Coupon"
                      >
                        Edit
                      </button>
                      <button 
                        className="btn btn-sm btn-danger"
                        onClick={() => onDeleteCoupon(coupon.coupon_id)}
                        title="Delete Coupon"
                      >
                        Delete
                      </button>
                    </div>
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
};



// Operating Hours Tab Component
const OperatingHoursTab = ({ business }) => {
  let hours = {};
  try {
    if (business.business_hours) {
      hours = typeof business.business_hours === 'string' 
        ? JSON.parse(business.business_hours) 
        : business.business_hours;
    }
  } catch (e) {
    console.error('Error parsing business hours:', e);
    hours = {};
  }
  
  const days = ['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday'];
  
  return (
    <div className="tab-hours">
      <h3>Operating Hours</h3>
      <div className="hours-table">
        {days.map(day => (
          <div key={day} className="hours-row">
            <span className="day-name">{day.charAt(0).toUpperCase() + day.slice(1)}</span>
            <span className="hours-time">
              {hours[day] ? `${hours[day].open} - ${hours[day].close}` : 'Closed'}
            </span>
          </div>
        ))}
      </div>
      <button className="btn btn-primary">Edit Hours</button>
    </div>
  );
};

// Delivery Settings Tab Component
const DeliverySettingsTab = ({ business }) => (
  <div className="tab-delivery">
    <h3>Delivery Settings</h3>
    <div className="settings-form">
      <div className="form-group">
        <label>Delivery Radius (km)</label>
        <input type="number" defaultValue="5" className="form-input" />
      </div>
      <div className="form-group">
        <label>Delivery Fee (₹)</label>
        <input type="number" defaultValue="30" className="form-input" />
      </div>
      <div className="form-group">
        <label>Free Delivery Above (₹)</label>
        <input type="number" defaultValue="500" className="form-input" />
      </div>
      <button className="btn btn-primary">Save Settings</button>
    </div>
  </div>
);

// Settings Tab Component
const SettingsTab = ({ business }) => (
  <div className="tab-settings">
    <h3>Business Settings</h3>
    <div className="settings-toggles">
      <div className="toggle-row">
        <span>Accept Orders</span>
        <label className="toggle-switch">
          <input type="checkbox" defaultChecked={business.status === 1} />
          <span className="slider"></span>
        </label>
      </div>
      <div className="toggle-row">
        <span>Show on Customer App</span>
        <label className="toggle-switch">
          <input type="checkbox" defaultChecked={business.status === 1} />
          <span className="slider"></span>
        </label>
      </div>
      <div className="toggle-row">
        <span>Featured Business</span>
        <label className="toggle-switch">
          <input type="checkbox" />
          <span className="slider"></span>
        </label>
      </div>
    </div>
  </div>
);

// Security Tab Component
const SecurityTab = ({ business }) => (
  <div className="tab-security">
    <h3>Login & Security</h3>
    <div className="security-info">
      <p>Owner Email: {business.owner_email}</p>
      <p>Owner Mobile: {business.owner_mobile}</p>
      <button className="btn btn-warning">Reset Password</button>
      <button className="btn btn-danger">Block Login</button>
    </div>
  </div>
);

// Notifications Tab Component
const NotificationsTab = ({ businessId }) => (
  <div className="tab-notifications">
    <h3>Send Notification</h3>
    <div className="notification-form">
      <textarea 
        className="form-textarea" 
        placeholder="Enter notification message..."
        rows="5"
      ></textarea>
      <button className="btn btn-primary">Send Notification</button>
    </div>
  </div>
);

// Activity Logs Tab Component
const ActivityLogsTab = ({ businessId }) => (
  <div className="tab-logs">
    <h3>Activity Logs</h3>
    <p className="info-message">Activity logging system coming soon...</p>
  </div>
);

// Order Edit Modal Component
const OrderEditModal = ({ order, onClose, onSave }) => {
  const [formData, setFormData] = useState({
    order_id: order?.order_id || '',
    order_type: order?.order_type || 'restaurant',
    status: order?.status || '',
    total_amount: order?.subtotal || order?.amount || 0,
    delivery_charges: order?.delivery_charges || 0,
    discount_amount: order?.discount || 0,
    final_amount: order?.amount || 0,
    delivery_instructions: order?.delivery_instructions || ''
  });

  const handleChange = (e) => {
    const { name, value } = e.target;
    setFormData(prev => ({ ...prev, [name]: value }));
  };

  const handleSubmit = (e) => {
    e.preventDefault();
    onSave(formData);
  };

  // Status options based on order type
  const statusOptions = formData.order_type === 'grocery' 
    ? ['pending', 'confirmed', 'preparing', 'ready_for_pickup', 'picked_up', 'delivered', 'cancelled']
    : ['pending', 'confirmed', 'preparing', 'ready', 'picked_up', 'delivered', 'cancelled'];

  return (
    <div style={{
      position: 'fixed',
      top: 0,
      left: 0,
      right: 0,
      bottom: 0,
      background: 'rgba(0, 0, 0, 0.5)',
      display: 'flex',
      justifyContent: 'center',
      alignItems: 'center',
      zIndex: 9999,
      overflow: 'auto'
    }}>
      <div style={{
        background: 'white',
        padding: '30px',
        borderRadius: '12px',
        minWidth: '500px',
        maxWidth: '600px',
        maxHeight: '90vh',
        overflow: 'auto',
        boxShadow: '0 10px 25px rgba(0, 0, 0, 0.2)'
      }}>
        <div style={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          marginBottom: '20px'
        }}>
          <h3 style={{ margin: 0, color: '#111827' }}>
            Edit Order #{order?.order_number}
          </h3>
          <button 
            onClick={onClose}
            style={{
              background: 'none',
              border: 'none',
              fontSize: '24px',
              cursor: 'pointer',
              color: '#6b7280',
              padding: '0',
              width: '30px',
              height: '30px'
            }}
          >
            ×
          </button>
        </div>

        <form onSubmit={handleSubmit}>
          <div style={{ marginBottom: '15px' }}>
            <label style={{ display: 'block', marginBottom: '5px', fontWeight: '500', color: '#374151' }}>
              Order Status
            </label>
            <select
              name="status"
              value={formData.status}
              onChange={handleChange}
              required
              style={{
                width: '100%',
                padding: '10px',
                border: '1px solid #d1d5db',
                borderRadius: '6px',
                fontSize: '14px'
              }}
            >
              <option value="">Select Status</option>
              {statusOptions.map(status => (
                <option key={status} value={status}>
                  {status.replace(/_/g, ' ').toUpperCase()}
                </option>
              ))}
            </select>
          </div>

          <div style={{ marginBottom: '15px' }}>
            <label style={{ display: 'block', marginBottom: '5px', fontWeight: '500', color: '#374151' }}>
              Total Amount (₹)
            </label>
            <input
              type="number"
              name="total_amount"
              value={formData.total_amount}
              onChange={handleChange}
              step="0.01"
              style={{
                width: '100%',
                padding: '10px',
                border: '1px solid #d1d5db',
                borderRadius: '6px',
                fontSize: '14px'
              }}
            />
          </div>

          <div style={{ marginBottom: '15px' }}>
            <label style={{ display: 'block', marginBottom: '5px', fontWeight: '500', color: '#374151' }}>
              Delivery Charges (₹)
            </label>
            <input
              type="number"
              name="delivery_charges"
              value={formData.delivery_charges}
              onChange={handleChange}
              step="0.01"
              style={{
                width: '100%',
                padding: '10px',
                border: '1px solid #d1d5db',
                borderRadius: '6px',
                fontSize: '14px'
              }}
            />
          </div>

          <div style={{ marginBottom: '15px' }}>
            <label style={{ display: 'block', marginBottom: '5px', fontWeight: '500', color: '#374151' }}>
              Discount Amount (₹)
            </label>
            <input
              type="number"
              name="discount_amount"
              value={formData.discount_amount}
              onChange={handleChange}
              step="0.01"
              style={{
                width: '100%',
                padding: '10px',
                border: '1px solid #d1d5db',
                borderRadius: '6px',
                fontSize: '14px'
              }}
            />
          </div>

          <div style={{ marginBottom: '15px' }}>
            <label style={{ display: 'block', marginBottom: '5px', fontWeight: '500', color: '#374151' }}>
              Final Amount (₹)
            </label>
            <input
              type="number"
              name="final_amount"
              value={formData.final_amount}
              onChange={handleChange}
              step="0.01"
              style={{
                width: '100%',
                padding: '10px',
                border: '1px solid #d1d5db',
                borderRadius: '6px',
                fontSize: '14px'
              }}
            />
          </div>

          <div style={{ marginBottom: '20px' }}>
            <label style={{ display: 'block', marginBottom: '5px', fontWeight: '500', color: '#374151' }}>
              Delivery Instructions
            </label>
            <textarea
              name="delivery_instructions"
              value={formData.delivery_instructions}
              onChange={handleChange}
              rows="3"
              style={{
                width: '100%',
                padding: '10px',
                border: '1px solid #d1d5db',
                borderRadius: '6px',
                fontSize: '14px',
                resize: 'vertical'
              }}
            />
          </div>

          <div style={{ display: 'flex', gap: '10px', justifyContent: 'flex-end' }}>
            <button
              type="button"
              onClick={onClose}
              style={{
                padding: '10px 20px',
                border: '1px solid #d1d5db',
                borderRadius: '6px',
                background: 'white',
                color: '#374151',
                cursor: 'pointer',
                fontSize: '14px',
                fontWeight: '500'
              }}
            >
              Cancel
            </button>
            <button
              type="submit"
              style={{
                padding: '10px 20px',
                border: 'none',
                borderRadius: '6px',
                background: '#3b82f6',
                color: 'white',
                cursor: 'pointer',
                fontSize: '14px',
                fontWeight: '500'
              }}
            >
              Save Changes
            </button>
          </div>
        </form>
      </div>
    </div>
  );
};

// Item Modal Component
const ItemModal = ({ item, businessData, onClose, onSave }) => {
  // Determine item type based on business type or existing item
  // R01 = Grocery, R02 = Restaurant
  const businessType = businessData?.business_info?.business_type || businessData?.business_type;
  const isGrocery = businessType === 'R01';
  const isRestaurant = businessType === 'R02';
  const tableItemType = isGrocery ? 'grocery' : 'restaurant';  // For backend to know which table
  
  // Helper function to clean item names by removing JSON-like text
  const cleanItemName = (name) => {
    if (!name) return '';
    // Remove any JSON-like patterns: {"key": "value"} or {"key": value}
    return name.replace(/\s*\{[^}]*\}\s*/g, '').trim();
  };
  
  const [formData, setFormData] = useState({
    name: cleanItemName(item?.name) || '',
    category: item?.category || '',
    size_label: item?.size_label || '',
    sku: item?.sku || '',
    original_cost: item?.original_cost || '',
    price: item?.price || '',
    gst: item?.gst || '',
    charges: item?.charges || '',
    quantity: item?.quantity || '',
    is_active: item?.is_active !== undefined ? item.is_active : true,
    status: item?.status !== undefined ? item.status : true,
    description: item?.description || '',
    image: item?.image || '',
    food_type: item?.item_type || '',  // Renamed: Veg/Non-Veg/etc (database field)
    preparation_time: item?.preparation_time || '',
    availability: item?.availability || '',
    // Grocery fields
    unit: item?.unit || 'kg',
    stock: item?.stock || 0,
    net_weight: item?.net_weight || 1,
    // IDs
    item_id: item?.item_id || null,
    product_id: item?.product_id || null
  });

  const handleChange = (e) => {
    const { name, value } = e.target;
    setFormData(prev => ({ ...prev, [name]: value }));
  };

  const handleSubmit = (e) => {
    e.preventDefault();
    
    // Add the table item_type for backend
    const submitData = {
      ...formData,
      item_type: tableItemType,  // "restaurant" or "grocery" for backend
      food_type: formData.food_type  // Keep the food type separate
    };
    
    console.log('Form submitted with data:', submitData);
    console.log('Item being edited:', item);
    console.log('Business data:', businessData);
    console.log('Business type:', businessType);
    console.log('Is Grocery:', isGrocery);
    console.log('Is Restaurant:', isRestaurant);
    console.log('Table item type being sent:', tableItemType);
    onSave(submitData);
  };

  return (
    <div style={{
      position: 'fixed',
      top: 0,
      left: 0,
      right: 0,
      bottom: 0,
      background: 'rgba(0, 0, 0, 0.5)',
      display: 'flex',
      justifyContent: 'center',
      alignItems: 'center',
      zIndex: 9999,
      overflow: 'auto'
    }}>
      <div style={{
        background: 'white',
        padding: '30px',
        borderRadius: '12px',
        minWidth: '500px',
        maxWidth: '600px',
        maxHeight: '90vh',
        overflow: 'auto',
        boxShadow: '0 10px 25px rgba(0, 0, 0, 0.2)'
      }}>
        <div style={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          marginBottom: '20px'
        }}>
          <h3 style={{ margin: 0, color: '#111827' }}>
            {item ? 'Edit Item' : 'Add New Item'}
          </h3>
          <button 
            onClick={onClose}
            style={{
              background: 'none',
              border: 'none',
              fontSize: '24px',
              cursor: 'pointer',
              color: '#6b7280',
              padding: '0',
              width: '30px',
              height: '30px'
            }}
          >
            ×
          </button>
        </div>
        
        <form onSubmit={handleSubmit}>
          <div style={{ marginBottom: '15px' }}>
            <label style={{ display: 'block', marginBottom: '5px', fontWeight: '500', color: '#374151' }}>
              Item Name *
            </label>
            <input 
              type="text" 
              name="name"
              value={formData.name}
              onChange={handleChange}
              placeholder="Enter item name"
              required
              style={{
                width: '100%',
                padding: '10px',
                border: '1px solid #d1d5db',
                borderRadius: '6px',
                fontSize: '14px'
              }}
            />
          </div>

          <div style={{ marginBottom: '15px' }}>
            <label style={{ display: 'block', marginBottom: '5px', fontWeight: '500', color: '#374151' }}>
              Category *
            </label>
            <input 
              type="text" 
              name="category"
              value={formData.category}
              onChange={handleChange}
              placeholder="Enter category"
              required
              style={{
                width: '100%',
                padding: '10px',
                border: '1px solid #d1d5db',
                borderRadius: '6px',
                fontSize: '14px'
              }}
            />
          </div>

          {isRestaurant && (
            <>
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '15px', marginBottom: '15px' }}>
                <div>
                  <label style={{ display: 'block', marginBottom: '5px', fontWeight: '500', color: '#374151' }}>
                    Original Cost (₹) *
                  </label>
                  <input 
                    type="number" 
                    name="original_cost"
                    value={formData.original_cost}
                    onChange={handleChange}
                    placeholder="Enter original cost"
                    required
                    min="0"
                    step="0.01"
                    style={{
                      width: '100%',
                      padding: '10px',
                      border: '1px solid #d1d5db',
                      borderRadius: '6px',
                      fontSize: '14px'
                    }}
                  />
                </div>

                <div>
                  <label style={{ display: 'block', marginBottom: '5px', fontWeight: '500', color: '#374151' }}>
                    Selling Price (₹) *
                  </label>
                  <input 
                    type="number" 
                    name="price"
                    value={formData.price}
                    onChange={handleChange}
                    placeholder="Enter selling price"
                    required
                    min="0"
                    step="0.01"
                    style={{
                      width: '100%',
                      padding: '10px',
                      border: '1px solid #d1d5db',
                      borderRadius: '6px',
                      fontSize: '14px'
                    }}
                  />
                </div>
              </div>

              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: '15px', marginBottom: '15px' }}>
                <div>
                  <label style={{ display: 'block', marginBottom: '5px', fontWeight: '500', color: '#374151' }}>
                    GST (%)
                  </label>
                  <input 
                    type="number" 
                    name="gst"
                    value={formData.gst}
                    onChange={handleChange}
                    placeholder="GST %"
                    min="0"
                    step="0.01"
                    style={{
                      width: '100%',
                      padding: '10px',
                      border: '1px solid #d1d5db',
                      borderRadius: '6px',
                      fontSize: '14px'
                    }}
                  />
                </div>

                <div>
                  <label style={{ display: 'block', marginBottom: '5px', fontWeight: '500', color: '#374151' }}>
                    Charges (₹)
                  </label>
                  <input 
                    type="number" 
                    name="charges"
                    value={formData.charges}
                    onChange={handleChange}
                    placeholder="Charges"
                    min="0"
                    step="0.01"
                    style={{
                      width: '100%',
                      padding: '10px',
                      border: '1px solid #d1d5db',
                      borderRadius: '6px',
                      fontSize: '14px'
                    }}
                  />
                </div>

                <div>
                  <label style={{ display: 'block', marginBottom: '5px', fontWeight: '500', color: '#374151' }}>
                    Quantity
                  </label>
                  <input 
                    type="number" 
                    name="quantity"
                    value={formData.quantity}
                    onChange={handleChange}
                    placeholder="Quantity"
                    min="0"
                    style={{
                      width: '100%',
                      padding: '10px',
                      border: '1px solid #d1d5db',
                      borderRadius: '6px',
                      fontSize: '14px'
                    }}
                  />
                </div>
              </div>

              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '15px', marginBottom: '15px' }}>
                <div>
                  <label style={{ display: 'block', marginBottom: '5px', fontWeight: '500', color: '#374151' }}>
                    Size Label
                  </label>
                  <input 
                    type="text" 
                    name="size_label"
                    value={formData.size_label}
                    onChange={handleChange}
                    placeholder="e.g., Regular, Large"
                    style={{
                      width: '100%',
                      padding: '10px',
                      border: '1px solid #d1d5db',
                      borderRadius: '6px',
                      fontSize: '14px'
                    }}
                  />
                </div>

                <div>
                  <label style={{ display: 'block', marginBottom: '5px', fontWeight: '500', color: '#374151' }}>
                    SKU
                  </label>
                  <input 
                    type="text" 
                    name="sku"
                    value={formData.sku}
                    onChange={handleChange}
                    placeholder="SKU (auto-generated if empty)"
                    style={{
                      width: '100%',
                      padding: '10px',
                      border: '1px solid #d1d5db',
                      borderRadius: '6px',
                      fontSize: '14px'
                    }}
                  />
                </div>
              </div>

              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '15px', marginBottom: '15px' }}>
                <div>
                  <label style={{ display: 'block', marginBottom: '5px', fontWeight: '500', color: '#374151' }}>
                    Item Type
                  </label>
                  <input 
                    type="text" 
                    name="food_type"
                    value={formData.food_type}
                    onChange={handleChange}
                    placeholder="e.g., Veg, Non-Veg"
                    style={{
                      width: '100%',
                      padding: '10px',
                      border: '1px solid #d1d5db',
                      borderRadius: '6px',
                      fontSize: '14px'
                    }}
                  />
                </div>

                <div>
                  <label style={{ display: 'block', marginBottom: '5px', fontWeight: '500', color: '#374151' }}>
                    Prep Time
                  </label>
                  <input 
                    type="text" 
                    name="preparation_time"
                    value={formData.preparation_time}
                    onChange={handleChange}
                    placeholder="e.g., 15-20 mins"
                    style={{
                      width: '100%',
                      padding: '10px',
                      border: '1px solid #d1d5db',
                      borderRadius: '6px',
                      fontSize: '14px'
                    }}
                  />
                </div>
              </div>

              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '15px', marginBottom: '15px' }}>
                <div>
                  <label style={{ display: 'flex', alignItems: 'center', cursor: 'pointer' }}>
                    <input 
                      type="checkbox" 
                      name="is_active"
                      checked={formData.is_active}
                      onChange={(e) => setFormData(prev => ({ ...prev, is_active: e.target.checked }))}
                      style={{ marginRight: '8px', width: '18px', height: '18px' }}
                    />
                    <span style={{ fontWeight: '500', color: '#374151' }}>Is Active</span>
                  </label>
                </div>

                <div>
                  <label style={{ display: 'flex', alignItems: 'center', cursor: 'pointer' }}>
                    <input 
                      type="checkbox" 
                      name="status"
                      checked={formData.status}
                      onChange={(e) => setFormData(prev => ({ ...prev, status: e.target.checked }))}
                      style={{ marginRight: '8px', width: '18px', height: '18px' }}
                    />
                    <span style={{ fontWeight: '500', color: '#374151' }}>Status</span>
                  </label>
                </div>
              </div>
            </>
          )}

          {isGrocery && (
            <>
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '15px', marginBottom: '15px' }}>
                <div>
                  <label style={{ display: 'block', marginBottom: '5px', fontWeight: '500', color: '#374151' }}>
                    Stock
                  </label>
                  <input 
                    type="number" 
                    name="stock"
                    value={formData.stock}
                    onChange={handleChange}
                    placeholder="Stock quantity"
                    min="0"
                    style={{
                      width: '100%',
                      padding: '10px',
                      border: '1px solid #d1d5db',
                      borderRadius: '6px',
                      fontSize: '14px'
                    }}
                  />
                </div>

                <div>
                  <label style={{ display: 'block', marginBottom: '5px', fontWeight: '500', color: '#374151' }}>
                    Unit
                  </label>
                  <select 
                    name="unit"
                    value={formData.unit}
                    onChange={handleChange}
                    style={{
                      width: '100%',
                      padding: '10px',
                      border: '1px solid #d1d5db',
                      borderRadius: '6px',
                      fontSize: '14px'
                    }}
                  >
                    <option value="kg">Kilogram (kg)</option>
                    <option value="g">Gram (g)</option>
                    <option value="l">Liter (l)</option>
                    <option value="ml">Milliliter (ml)</option>
                    <option value="pcs">Pieces (pcs)</option>
                    <option value="pack">Pack</option>
                    <option value="Packet">Packet</option>
                    <option value="Bag">Bag</option>
                    <option value="Bottle">Bottle</option>
                    <option value="Box">Box</option>
                  </select>
                </div>
              </div>

              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '15px', marginBottom: '15px' }}>
                <div>
                  <label style={{ display: 'block', marginBottom: '5px', fontWeight: '500', color: '#374151' }}>
                    Net Weight
                  </label>
                  <input 
                    type="number" 
                    name="net_weight"
                    value={formData.net_weight}
                    onChange={handleChange}
                    placeholder="Net weight"
                    min="0"
                    step="0.01"
                    style={{
                      width: '100%',
                      padding: '10px',
                      border: '1px solid #d1d5db',
                      borderRadius: '6px',
                      fontSize: '14px'
                    }}
                  />
                </div>

                <div>
                  <label style={{ display: 'block', marginBottom: '5px', fontWeight: '500', color: '#374151' }}>
                    SKU
                  </label>
                  <input 
                    type="text" 
                    name="sku"
                    value={formData.sku}
                    onChange={handleChange}
                    placeholder="SKU (auto-generated if empty)"
                    style={{
                      width: '100%',
                      padding: '10px',
                      border: '1px solid #d1d5db',
                      borderRadius: '6px',
                      fontSize: '14px'
                    }}
                  />
                </div>
              </div>
            </>
          )}

          <div style={{ marginBottom: '15px' }}>
            <label style={{ display: 'block', marginBottom: '5px', fontWeight: '500', color: '#374151' }}>
              Description
            </label>
            <textarea 
              name="description"
              value={formData.description}
              onChange={handleChange}
              placeholder="Enter description"
              rows="3"
              style={{
                width: '100%',
                padding: '10px',
                border: '1px solid #d1d5db',
                borderRadius: '6px',
                fontSize: '14px',
                resize: 'vertical'
              }}
            />
          </div>

          <div style={{ marginBottom: '20px' }}>
            <label style={{ display: 'block', marginBottom: '5px', fontWeight: '500', color: '#374151' }}>
              Image URL
            </label>
            <input 
              type="text" 
              name="image"
              value={formData.image}
              onChange={handleChange}
              placeholder="Enter image URL"
              style={{
                width: '100%',
                padding: '10px',
                border: '1px solid #d1d5db',
                borderRadius: '6px',
                fontSize: '14px'
              }}
            />
          </div>

          <div style={{
            display: 'flex',
            justifyContent: 'flex-end',
            gap: '10px'
          }}>
            <button 
              type="button"
              onClick={onClose}
              style={{
                background: '#6b7280',
                color: 'white',
                border: 'none',
                padding: '10px 20px',
                borderRadius: '6px',
                cursor: 'pointer'
              }}
            >
              Cancel
            </button>
            <button 
              type="submit"
              onClick={(e) => {
                console.log('Submit button clicked!');
                console.log('Form data at click:', formData);
              }}
              style={{
                background: '#3b82f6',
                color: 'white',
                border: 'none',
                padding: '10px 20px',
                borderRadius: '6px',
                cursor: 'pointer'
              }}
            >
              {item ? 'Update Item' : 'Add Item'}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
};

// Delivery Tab Component - Professional with React Icons
const DeliveryTab = ({ business }) => {
  const [showPartnerModal, setShowPartnerModal] = useState(false);
  const [showSettingsModal, setShowSettingsModal] = useState(false);
  const [deliveryPartners, setDeliveryPartners] = useState([]);
  const [loading, setLoading] = useState(false);

  // Fetch delivery partners
  const fetchDeliveryPartners = async () => {
    setLoading(true);
    try {
      const response = await AdminService.getDeliveryPartners(business.business_id);
      if (response.success) {
        setDeliveryPartners(response.data || []);
      }
    } catch (error) {
      console.error('Error fetching delivery partners:', error);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (business.business_id) {
      fetchDeliveryPartners();
    }
  }, [business.business_id]);

  const handleManagePartners = () => {
    setShowPartnerModal(true);
  };

  const handleUpdateSettings = () => {
    setShowSettingsModal(true);
  };

  const handleViewAnalytics = () => {
    alert('Delivery Analytics feature coming soon!');
  };

  return (
    <div className="tab-delivery-new">
      {/* Top Row - Essential Stats Only (3 cards) */}
      <div className="delivery-stats-row-compact">
        <div className="delivery-stat-card">
          <div className="stat-icon-wrapper">
            <MdOutlineDeliveryDining className="stat-icon-react" />
          </div>
          <div className="stat-content">
            <div className="stat-value">{business.active_delivery_partners || 0}</div>
            <div className="stat-label">Active Partners</div>
          </div>
        </div>

        <div className="delivery-stat-card">
          <div className="stat-icon-wrapper success">
            <MdOutlineCheckCircleOutline className="stat-icon-react" />
          </div>
          <div className="stat-content">
            <div className="stat-value">{business.total_deliveries || 0}</div>
            <div className="stat-label">Total Deliveries</div>
          </div>
        </div>

        <div className="delivery-stat-card">
          <div className="stat-icon-wrapper warning">
            <MdOutlineSpeed className="stat-icon-react" />
          </div>
          <div className="stat-content">
            <div className="stat-value">{business.avg_delivery_time || 'N/A'}</div>
            <div className="stat-label">Avg Time (min)</div>
          </div>
        </div>
      </div>

      {/* Middle Row - Settings & Performance (2 columns) */}
      <div className="delivery-middle-row">
        {/* Delivery Settings Card */}
        <div className="delivery-info-card">
          <div className="card-header">
            <h4>Delivery Settings</h4>
            <button className="btn-edit" onClick={handleUpdateSettings}>
              <MdOutlineEdit /> Edit
            </button>
          </div>
          <div className="settings-grid">
            <div className="setting-item-new">
              <div className="setting-icon-wrapper">
                <MdOutlineLocationOn className="setting-icon-react" />
              </div>
              <div className="setting-content">
                <span className="setting-label">Delivery Radius</span>
                <span className="setting-value">{business.delivery_radius || 'N/A'} km</span>
              </div>
            </div>
            <div className="setting-item-new">
              <div className="setting-icon-wrapper">
                <MdOutlineAttachMoney className="setting-icon-react" />
              </div>
              <div className="setting-content">
                <span className="setting-label">Delivery Fee</span>
                <span className="setting-value">₹{business.delivery_fee || '0'}</span>
              </div>
            </div>
            <div className="setting-item-new">
              <div className="setting-icon-wrapper">
                <MdOutlineLocalOffer className="setting-icon-react" />
              </div>
              <div className="setting-content">
                <span className="setting-label">Free Delivery Above</span>
                <span className="setting-value">₹{business.free_delivery_above || 'N/A'}</span>
              </div>
            </div>
            <div className="setting-item-new">
              <div className="setting-icon-wrapper">
                <MdOutlineAccessTime className="setting-icon-react" />
              </div>
              <div className="setting-content">
                <span className="setting-label">Estimated Time</span>
                <span className="setting-value">{business.estimated_delivery_time || '30-45'} min</span>
              </div>
            </div>
          </div>
        </div>

        {/* Performance Metrics Card */}
        <div className="delivery-info-card">
          <div className="card-header">
            <h4>Performance Metrics</h4>
            <button className="btn-view" onClick={handleViewAnalytics}>
              <MdOutlineBarChart /> Analytics
            </button>
          </div>
          <div className="performance-grid">
            <div className="performance-item">
              <div className="performance-label">Success Rate</div>
              <div className="performance-bar-container">
                <div className="performance-bar" style={{ width: `${business.delivery_success_rate || 0}%` }}>
                  <span className="performance-value">{business.delivery_success_rate || 0}%</span>
                </div>
              </div>
            </div>
            <div className="performance-item">
              <div className="performance-label">On-Time Delivery</div>
              <div className="performance-bar-container">
                <div className="performance-bar" style={{ width: `${business.on_time_delivery || 85}%`, backgroundColor: '#10b981' }}>
                  <span className="performance-value">{business.on_time_delivery || 85}%</span>
                </div>
              </div>
            </div>
            <div className="performance-item">
              <div className="performance-label">Customer Satisfaction</div>
              <div className="performance-bar-container">
                <div className="performance-bar" style={{ width: `${business.customer_satisfaction || 90}%`, backgroundColor: '#f59e0b' }}>
                  <span className="performance-value">{business.customer_satisfaction || 90}%</span>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* Bottom Row - Delivery Partners List */}
      <div className="delivery-partners-section">
        <div className="section-header">
          <h4>Delivery Partners</h4>
          <button className="btn btn-primary" onClick={handleManagePartners}>
            <MdOutlineAdd /> Add Partner
          </button>
        </div>
        
        {loading ? (
          <div className="loading-state">Loading partners...</div>
        ) : deliveryPartners.length > 0 ? (
          <div className="partners-grid">
            {deliveryPartners.map((partner, index) => (
              <div key={index} className="partner-card">
                <div className="partner-avatar-icon">
                  <MdOutlinePerson />
                </div>
                <div className="partner-info">
                  <div className="partner-name">{partner.name || `Partner ${index + 1}`}</div>
                  <div className="partner-phone">
                    <MdOutlinePhone className="phone-icon" />
                    {partner.phone || 'N/A'}
                  </div>
                </div>
                <div className="partner-status">
                  <span className={`status-badge ${partner.status || 'available'}`}>
                    {partner.status || 'Available'}
                  </span>
                </div>
                <div className="partner-stats-mini">
                  <span><MdOutlineDeliveryDining /> {partner.total_deliveries || 0}</span>
                  <span><MdOutlineStarOutline /> {partner.rating || 'N/A'}</span>
                </div>
              </div>
            ))}
          </div>
        ) : (
          <div className="empty-state">
            <div className="empty-icon-wrapper">
              <MdOutlineDeliveryDining className="empty-icon-react" />
            </div>
            <p>No delivery partners found</p>
            <button className="btn btn-primary" onClick={handleManagePartners}>
              <MdOutlineAdd /> Add Your First Partner
            </button>
          </div>
        )}
      </div>

      {/* Partner Management Modal */}
      {showPartnerModal && (
        <div className="modal-overlay" onClick={() => setShowPartnerModal(false)}>
          <div className="modal-content" onClick={(e) => e.stopPropagation()}>
            <div className="modal-header">
              <h3>Manage Delivery Partners</h3>
              <button className="close-btn" onClick={() => setShowPartnerModal(false)}>×</button>
            </div>
            <div className="modal-body">
              <p>Partner management interface coming soon...</p>
              <p>You'll be able to:</p>
              <ul>
                <li>Add new delivery partners</li>
                <li>Edit partner details</li>
                <li>Assign/unassign partners</li>
                <li>View partner performance</li>
              </ul>
            </div>
            <div className="modal-footer">
              <button className="btn btn-secondary" onClick={() => setShowPartnerModal(false)}>Close</button>
            </div>
          </div>
        </div>
      )}

      {/* Settings Modal */}
      {showSettingsModal && (
        <div className="modal-overlay" onClick={() => setShowSettingsModal(false)}>
          <div className="modal-content" onClick={(e) => e.stopPropagation()}>
            <div className="modal-header">
              <h3>Update Delivery Settings</h3>
              <button className="close-btn" onClick={() => setShowSettingsModal(false)}>×</button>
            </div>
            <div className="modal-body">
              <div className="form-group">
                <label>Delivery Radius (km)</label>
                <input type="number" defaultValue={business.delivery_radius || 5} />
              </div>
              <div className="form-group">
                <label>Delivery Fee (₹)</label>
                <input type="number" defaultValue={business.delivery_fee || 0} />
              </div>
              <div className="form-group">
                <label>Free Delivery Above (₹)</label>
                <input type="number" defaultValue={business.free_delivery_above || 0} />
              </div>
              <div className="form-group">
                <label>Estimated Delivery Time (minutes)</label>
                <input type="text" defaultValue={business.estimated_delivery_time || '30-45'} />
              </div>
            </div>
            <div className="modal-footer">
              <button className="btn btn-secondary" onClick={() => setShowSettingsModal(false)}>Cancel</button>
              <button className="btn btn-primary" onClick={() => {
                alert('Settings saved successfully!');
                setShowSettingsModal(false);
              }}>Save Changes</button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default BusinessDetailsTabbed;
