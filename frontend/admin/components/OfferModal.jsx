import React, { useState } from 'react';

const OfferModal = ({ offer, onClose, onSave, isSaving }) => {
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
    console.log('OfferModal submit called with:', formData);
    onSave(formData);
  };

  const handleChange = (e) => {
    const { name, value, type, checked } = e.target;
    setFormData(prev => ({
      ...prev,
      [name]: type === 'checkbox' ? checked : value
    }));
  };

  const handleOverlayClick = (e) => {
    // Only close if clicking directly on the overlay
    if (e.target === e.currentTarget) {
      console.log('Overlay clicked - closing modal');
      onClose();
    }
  };

  const handleModalContentClick = (e) => {
    // Prevent event from bubbling up to overlay
    e.stopPropagation();
  };

  const handleCloseClick = (e) => {
    e.stopPropagation();
    onClose();
  };

  const handleCancelClick = (e) => {
    e.stopPropagation();
    onClose();
  };

  return (
    <div 
      className="modal-overlay" 
      onClick={handleOverlayClick}
      style={{
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
        padding: '20px',
        boxSizing: 'border-box'
      }}
    >
      <div 
        className="modal-content" 
        onClick={handleModalContentClick}
        style={{
          background: 'white',
          borderRadius: '8px',
          width: '90%',
          maxWidth: '700px',
          maxHeight: '90vh',
          overflowY: 'auto',
          cursor: 'default',
          pointerEvents: 'auto',
          boxShadow: '0 20px 25px -5px rgba(0, 0, 0, 0.1), 0 10px 10px -5px rgba(0, 0, 0, 0.04)'
        }}
      >
        <div className="modal-header" style={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          padding: '20px',
          borderBottom: '1px solid #e5e7eb'
        }}>
          <h3 style={{ margin: 0, fontSize: '18px', fontWeight: '600', color: '#111827' }}>
            {offer ? 'Edit Offer' : 'Add New Offer'}
          </h3>
          <button 
            className="close-btn" 
            onClick={handleCloseClick}
            style={{
              background: 'none',
              border: 'none',
              fontSize: '24px',
              cursor: 'pointer',
              color: '#6b7280',
              padding: '0',
              width: '30px',
              height: '30px',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center'
            }}
          >
            ×
          </button>
        </div>
        
        <div className="modal-body" style={{ padding: '20px' }}>
          <form onSubmit={handleSubmit}>
            <div className="form-group" style={{ marginBottom: '16px' }}>
              <label style={{ display: 'block', fontSize: '14px', fontWeight: '500', color: '#374151', marginBottom: '6px' }}>
                Offer Title *
              </label>
              <input
                type="text"
                name="title"
                value={formData.title}
                onChange={handleChange}
                placeholder="e.g., Buy 1 Get 1 Free"
                required
                style={{
                  width: '100%',
                  padding: '8px 12px',
                  border: '1px solid #d1d5db',
                  borderRadius: '4px',
                  fontSize: '14px'
                }}
              />
            </div>

            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '16px' }}>
              <div className="form-group" style={{ marginBottom: '16px' }}>
                <label style={{ display: 'block', fontSize: '14px', fontWeight: '500', color: '#374151', marginBottom: '6px' }}>
                  Offer Type *
                </label>
                <select
                  name="offer_type"
                  value={formData.offer_type}
                  onChange={handleChange}
                  required
                  style={{
                    width: '100%',
                    padding: '8px 12px',
                    border: '1px solid #d1d5db',
                    borderRadius: '4px',
                    fontSize: '14px'
                  }}
                >
                  <option value="general">General</option>
                  <option value="product">Product Specific</option>
                  <option value="category">Category Specific</option>
                  <option value="seasonal">Seasonal</option>
                  <option value="flash">Flash Sale</option>
                </select>
              </div>

              <div className="form-group" style={{ marginBottom: '16px' }}>
                <label style={{ display: 'block', fontSize: '14px', fontWeight: '500', color: '#374151', marginBottom: '6px' }}>
                  Priority
                </label>
                <input
                  type="number"
                  name="priority"
                  value={formData.priority}
                  onChange={handleChange}
                  placeholder="0"
                  min="0"
                  style={{
                    width: '100%',
                    padding: '8px 12px',
                    border: '1px solid #d1d5db',
                    borderRadius: '4px',
                    fontSize: '14px'
                  }}
                />
              </div>
            </div>

            <div className="form-group" style={{ marginBottom: '16px' }}>
              <label style={{ display: 'block', fontSize: '14px', fontWeight: '500', color: '#374151', marginBottom: '6px' }}>
                Description
              </label>
              <textarea
                name="description"
                value={formData.description}
                onChange={handleChange}
                placeholder="Offer description..."
                rows="3"
                style={{
                  width: '100%',
                  padding: '8px 12px',
                  border: '1px solid #d1d5db',
                  borderRadius: '4px',
                  fontSize: '14px',
                  resize: 'vertical'
                }}
              />
            </div>

            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '16px' }}>
              <div className="form-group" style={{ marginBottom: '16px' }}>
                <label style={{ display: 'block', fontSize: '14px', fontWeight: '500', color: '#374151', marginBottom: '6px' }}>
                  Discount Percentage (%)
                </label>
                <input
                  type="number"
                  name="discount_percentage"
                  value={formData.discount_percentage}
                  onChange={handleChange}
                  placeholder="e.g., 20"
                  min="0"
                  max="100"
                  step="0.01"
                  style={{
                    width: '100%',
                    padding: '8px 12px',
                    border: '1px solid #d1d5db',
                    borderRadius: '4px',
                    fontSize: '14px'
                  }}
                />
              </div>

              <div className="form-group" style={{ marginBottom: '16px' }}>
                <label style={{ display: 'block', fontSize: '14px', fontWeight: '500', color: '#374151', marginBottom: '6px' }}>
                  Discount Amount (₹)
                </label>
                <input
                  type="number"
                  name="discount_amount"
                  value={formData.discount_amount}
                  onChange={handleChange}
                  placeholder="e.g., 100"
                  min="0"
                  step="0.01"
                  style={{
                    width: '100%',
                    padding: '8px 12px',
                    border: '1px solid #d1d5db',
                    borderRadius: '4px',
                    fontSize: '14px'
                  }}
                />
              </div>
            </div>

            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '16px' }}>
              <div className="form-group" style={{ marginBottom: '16px' }}>
                <label style={{ display: 'block', fontSize: '14px', fontWeight: '500', color: '#374151', marginBottom: '6px' }}>
                  Original Price (₹)
                </label>
                <input
                  type="number"
                  name="original_price"
                  value={formData.original_price}
                  onChange={handleChange}
                  placeholder="e.g., 500"
                  min="0"
                  step="0.01"
                  style={{
                    width: '100%',
                    padding: '8px 12px',
                    border: '1px solid #d1d5db',
                    borderRadius: '4px',
                    fontSize: '14px'
                  }}
                />
              </div>

              <div className="form-group" style={{ marginBottom: '16px' }}>
                <label style={{ display: 'block', fontSize: '14px', fontWeight: '500', color: '#374151', marginBottom: '6px' }}>
                  Offer Price (₹)
                </label>
                <input
                  type="number"
                  name="offer_price"
                  value={formData.offer_price}
                  onChange={handleChange}
                  placeholder="e.g., 400"
                  min="0"
                  step="0.01"
                  style={{
                    width: '100%',
                    padding: '8px 12px',
                    border: '1px solid #d1d5db',
                    borderRadius: '4px',
                    fontSize: '14px'
                  }}
                />
              </div>
            </div>

            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '16px' }}>
              <div className="form-group" style={{ marginBottom: '16px' }}>
                <label style={{ display: 'block', fontSize: '14px', fontWeight: '500', color: '#374151', marginBottom: '6px' }}>
                  Valid From
                </label>
                <input
                  type="date"
                  name="valid_from"
                  value={formData.valid_from}
                  onChange={handleChange}
                  style={{
                    width: '100%',
                    padding: '8px 12px',
                    border: '1px solid #d1d5db',
                    borderRadius: '4px',
                    fontSize: '14px'
                  }}
                />
              </div>

              <div className="form-group" style={{ marginBottom: '16px' }}>
                <label style={{ display: 'block', fontSize: '14px', fontWeight: '500', color: '#374151', marginBottom: '6px' }}>
                  Valid Until
                </label>
                <input
                  type="date"
                  name="valid_to"
                  value={formData.valid_to}
                  onChange={handleChange}
                  style={{
                    width: '100%',
                    padding: '8px 12px',
                    border: '1px solid #d1d5db',
                    borderRadius: '4px',
                    fontSize: '14px'
                  }}
                />
              </div>
            </div>

            <div className="form-group" style={{ marginBottom: '16px' }}>
              <label style={{ display: 'block', fontSize: '14px', fontWeight: '500', color: '#374151', marginBottom: '6px' }}>
                Max Views
              </label>
              <input
                type="number"
                name="max_views"
                value={formData.max_views}
                onChange={handleChange}
                placeholder="Unlimited"
                min="0"
                style={{
                  width: '100%',
                  padding: '8px 12px',
                  border: '1px solid #d1d5db',
                  borderRadius: '4px',
                  fontSize: '14px'
                }}
              />
            </div>

            <div style={{ display: 'flex', gap: '20px', marginTop: '16px' }}>
              <label style={{ display: 'flex', alignItems: 'center', gap: '8px', fontSize: '14px', fontWeight: '500', color: '#374151' }}>
                <input
                  type="checkbox"
                  name="is_active"
                  checked={formData.is_active}
                  onChange={handleChange}
                  style={{ width: 'auto' }}
                />
                Active
              </label>
              <label style={{ display: 'flex', alignItems: 'center', gap: '8px', fontSize: '14px', fontWeight: '500', color: '#374151' }}>
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
          </form>
        </div>
        
        <div className="modal-footer" style={{
          display: 'flex',
          justifyContent: 'flex-end',
          gap: '10px',
          padding: '20px',
          borderTop: '1px solid #e5e7eb'
        }}>
          <button 
            type="button" 
            className="btn btn-secondary" 
            onClick={handleCancelClick}
            style={{
              padding: '8px 16px',
              border: '1px solid #d1d5db',
              borderRadius: '6px',
              background: '#f9fafb',
              color: '#374151',
              cursor: 'pointer',
              fontSize: '14px'
            }}
          >
            Cancel
          </button>
          <button 
            type="button" 
            className="btn btn-primary" 
            onClick={handleSubmit} 
            disabled={isSaving}
            style={{
              padding: '8px 16px',
              border: 'none',
              borderRadius: '6px',
              background: isSaving ? '#9ca3af' : '#3b82f6',
              color: 'white',
              cursor: isSaving ? 'not-allowed' : 'pointer',
              fontSize: '14px'
            }}
          >
            {isSaving ? 'Saving...' : (offer ? 'Update Offer' : 'Create Offer')}
          </button>
        </div>
      </div>
    </div>
  );
};

export default OfferModal;
