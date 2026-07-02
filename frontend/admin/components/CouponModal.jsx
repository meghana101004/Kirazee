import React, { useState } from 'react';

const CouponModal = ({ coupon, onClose, onSave, isSaving }) => {
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
    console.log('CouponModal submit called with:', formData);
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
          maxWidth: '600px',
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
            {coupon ? 'Edit Coupon' : 'Add New Coupon'}
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
                Coupon Code *
              </label>
              <input
                type="text"
                name="coupon_code"
                value={formData.coupon_code}
                onChange={handleChange}
                placeholder="e.g., SAVE20"
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
                  Discount Type *
                </label>
                <select
                  name="discount_type"
                  value={formData.discount_type}
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
                  <option value="percentage">Percentage</option>
                  <option value="fixed">Fixed Amount</option>
                </select>
              </div>

              <div className="form-group" style={{ marginBottom: '16px' }}>
                <label style={{ display: 'block', fontSize: '14px', fontWeight: '500', color: '#374151', marginBottom: '6px' }}>
                  Discount Value *
                </label>
                <input
                  type="number"
                  name="discount_value"
                  value={formData.discount_value}
                  onChange={handleChange}
                  placeholder={formData.discount_type === 'percentage' ? '10' : '100'}
                  required
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

            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: '16px' }}>
              <div className="form-group" style={{ marginBottom: '16px' }}>
                <label style={{ display: 'block', fontSize: '14px', fontWeight: '500', color: '#374151', marginBottom: '6px' }}>
                  Max Usage
                </label>
                <input
                  type="number"
                  name="max_usage_total"
                  value={formData.max_usage_total}
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

              <div className="form-group" style={{ marginBottom: '16px' }}>
                <label style={{ display: 'block', fontSize: '14px', fontWeight: '500', color: '#374151', marginBottom: '6px' }}>
                  Min Order Value
                </label>
                <input
                  type="number"
                  name="min_order_value"
                  value={formData.min_order_value}
                  onChange={handleChange}
                  placeholder="0"
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
                  Max Discount
                </label>
                <input
                  type="number"
                  name="max_discount_amount"
                  value={formData.max_discount_amount}
                  onChange={handleChange}
                  placeholder="No limit"
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

            <div className="form-group" style={{ marginBottom: '16px' }}>
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
            {isSaving ? 'Saving...' : (coupon ? 'Update Coupon' : 'Create Coupon')}
          </button>
        </div>
      </div>
    </div>
  );
};

export default CouponModal;
