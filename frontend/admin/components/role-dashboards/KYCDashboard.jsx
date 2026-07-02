import React, { useState, useEffect } from 'react';
import AdminService from '../../services/adminService';
import '../../../css/admin/DashboardOverview.css';
import '../../../css/admin/RoleDashboards.css';
import { FaCheckCircle, FaExclamationTriangle, FaSpinner, FaStore, FaTruck, FaFileAlt, FaClock } from 'react-icons/fa';
import { MdRefresh } from 'react-icons/md';

const KYCDashboard = () => {
  const [dashboardData, setDashboardData] = useState({
    pendingBusinessKYC: [],
    pendingPartnerKYC: [],
    verifiedBusinesses: [],
    verifiedPartners: [],
    kycStats: {}
  });
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [lastUpdated, setLastUpdated] = useState(new Date());
  const [selectedBusiness, setSelectedBusiness] = useState(null);
  const [selectedPartner, setSelectedPartner] = useState(null);
  const [showModal, setShowModal] = useState(false);

  useEffect(() => {
    fetchDashboardData();
  }, []);

  const fetchDashboardData = async () => {
    try {
      setLoading(true);
      setError(null);

      // Use existing business API with KYC data
      const businessesData = await AdminService.getBusinessesComprehensive({ limit: 1000 });
      const deliveryData = await AdminService.getDeliveryFleetData({ limit: 1000 });

      if (businessesData.success) {
        const allBusinesses = businessesData.businesses || [];
        
        // Filter businesses by KYC status
        // Treat missing or null kyc_status as 'pending'
        const pendingBusinessKYC = allBusinesses.filter(b => {
          const ownerDetails = b.owner_details || {};
          const kycStatus = ownerDetails.kyc_status || 'pending';
          return kycStatus === 'pending' || kycStatus === 'incomplete';
        });
        
        const verifiedBusinesses = allBusinesses.filter(b => {
          const ownerDetails = b.owner_details || {};
          const kycStatus = ownerDetails.kyc_status || 'pending';
          return kycStatus === 'verified';
        });
        
        const rejectedBusinesses = allBusinesses.filter(b => {
          const ownerDetails = b.owner_details || {};
          const kycStatus = ownerDetails.kyc_status || 'pending';
          return kycStatus === 'rejected';
        });

        // Process delivery partners - store full objects
        const allPartners = deliveryData.providers || [];
        const pendingPartnerKYC = allPartners.filter(p => !p.is_verified);
        const verifiedPartners = allPartners.filter(p => p.is_verified);

        const transformedData = {
          // Store the full business objects with all details
          pendingBusinessKYC: pendingBusinessKYC,
          verifiedBusinesses: verifiedBusinesses,
          rejectedBusinesses: rejectedBusinesses.map(b => ({
            business_id: b.business_id,
            name: b.businessName,
            business_name: b.businessName,
            owner_name: b.owner_details?.owner_name || 
                       `${b.owner_details?.first_name || ''} ${b.owner_details?.last_name || ''}`.trim() || 
                       'N/A',
            kyc_status: b.owner_details?.kyc_status || 'pending'
          })),
          pendingPartnerKYC: pendingPartnerKYC,
          verifiedPartners: verifiedPartners,
          kycStats: {
            totalBusinesses: allBusinesses.length,
            activeBusinesses: verifiedBusinesses.length,
            pendingBusinesses: pendingBusinessKYC.length,
            rejectedBusinesses: rejectedBusinesses.length,
            totalPartners: allPartners.length,
            activePartners: verifiedPartners.length,
            pendingPartners: pendingPartnerKYC.length
          }
        };

        setDashboardData(transformedData);
        setLastUpdated(new Date());
      }
    } catch (err) {
      setError(`Failed to load KYC dashboard data: ${err.message}`);
      console.error('KYC Dashboard error:', err);
    } finally {
      setLoading(false);
    }
  };

  const getKYCStatus = (item) => {
    if (item.status === 'Active' && item.verified) return 'verified';
    if (item.status === 'Pending') return 'pending';
    return 'incomplete';
  };

  const handleReviewBusiness = (business) => {
    setSelectedBusiness(business);
    setSelectedPartner(null);
    setShowModal(true);
  };

  const handleReviewPartner = (partner) => {
    setSelectedPartner(partner);
    setSelectedBusiness(null);
    setShowModal(true);
  };

  const handleCloseModal = () => {
    setShowModal(false);
    setSelectedBusiness(null);
    setSelectedPartner(null);
  };

  const handleApproveKYC = async (businessId) => {
    // TODO: Implement KYC approval API call
    console.log('Approve KYC for business:', businessId);
    alert('KYC approval functionality will be implemented');
    handleCloseModal();
    fetchDashboardData(); // Refresh data
  };

  const handleRejectKYC = async (businessId) => {
    // TODO: Implement KYC rejection API call
    console.log('Reject KYC for business:', businessId);
    alert('KYC rejection functionality will be implemented');
    handleCloseModal();
    fetchDashboardData(); // Refresh data
  };

  if (loading) {
    return (
      <div className="dashboard-loading">
        <FaSpinner className="loading-spinner" />
        <p>Loading KYC Dashboard...</p>
      </div>
    );
  }

  if (error) {
    return (
      <div className="dashboard-error">
        <h3>Error Loading Dashboard</h3>
        <p>{error}</p>
        <button onClick={fetchDashboardData} className="retry-btn">
          <MdRefresh /> Retry
        </button>
      </div>
    );
  }

  return (
    <div className="dashboard-overview">
      {/* Header */}
      <div className="dashboard-header">
        <div>
          <h2>KYC Verification Dashboard</h2>
          <p>
            KYC verification overview as of: <strong>{lastUpdated.toLocaleTimeString()}</strong>
          </p>
        </div>
        <button
          className="refresh-btn"
          onClick={fetchDashboardData}
          disabled={loading}
        >
          <MdRefresh className={loading ? 'spin' : ''} />
          {loading ? ' Refreshing...' : ' Refresh Data'}
        </button>
      </div>

      {/* KPI Cards - KYC Focus */}
      <div className="kpi-grid">
        <div className="kpi-cards pending-business">
          <div className="kpi-icon">
            <FaStore />
          </div>
          <div className="kpi-content">
            <h3>{dashboardData.pendingBusinessKYC.length || 0}</h3>
            <p>Pending Business KYC</p>
            <small>Need verification</small>
          </div>
        </div>

        <div className="kpi-cards verified-business">
          <div className="kpi-icon">
            <FaCheckCircle />
          </div>
          <div className="kpi-content">
            <h3>{dashboardData.verifiedBusinesses.length || 0}</h3>
            <p>Verified Businesses</p>
            <small>Total active</small>
          </div>
        </div>

        <div className="kpi-cards pending-partner">
          <div className="kpi-icon">
            <FaTruck />
          </div>
          <div className="kpi-content">
            <h3>{dashboardData.pendingPartnerKYC.length || 0}</h3>
            <p>Pending Partner KYC</p>
            <small>Need verification</small>
          </div>
        </div>

        <div className="kpi-cards verified-partner">
          <div className="kpi-icon">
            <FaCheckCircle />
          </div>
          <div className="kpi-content">
            <h3>{dashboardData.verifiedPartners.length || 0}</h3>
            <p>Verified Partners</p>
            <small>Ready to work</small>
          </div>
        </div>
      </div>

      {/* Pending Business KYC */}
      <div className="kyc-section">
        <h3>Pending Business KYC Verification</h3>
        {dashboardData.pendingBusinessKYC.length > 0 ? (
          <div className="kyc-table">
            <table>
              <thead>
                <tr>
                  <th>Business Name</th>
                  <th>Owner Name</th>
                  <th>Documents</th>
                  <th>Submitted</th>
                  <th>Action</th>
                </tr>
              </thead>
              <tbody>
                {dashboardData.pendingBusinessKYC.map((business, index) => (
                  <tr key={index}>
                    <td>{business.businessName || business.name}</td>
                    <td>{business.owner_details?.owner_name || 
                        `${business.owner_details?.first_name || ''} ${business.owner_details?.last_name || ''}`.trim() || 
                        'N/A'}</td>
                    <td>
                      <span className="doc-status">
                        {(business.owner_details?.pan_number || business.owner_details?.pan || 
                          business.owner_details?.account_number || business.financial_details?.account_number) ? 
                          <FaCheckCircle style={{ color: '#4caf50' }} /> : 
                          <FaExclamationTriangle style={{ color: '#ff9800' }} />
                        }
                        {(business.owner_details?.pan_number || business.owner_details?.pan || 
                          business.owner_details?.account_number || business.financial_details?.account_number) ? 
                          'Uploaded' : 'Pending'}
                      </span>
                    </td>
                    <td>
                      {business.created_at ? 
                        new Date(business.created_at).toLocaleDateString() : 
                        'N/A'
                      }
                    </td>
                    <td>
                      <button 
                        className="action-btn review"
                        onClick={() => handleReviewBusiness(business)}
                      >
                        Review
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <p>No pending business KYC applications</p>
        )}
      </div>

      {/* Pending Partner KYC */}
      <div className="kyc-section">
        <h3>Pending Delivery Partner KYC Verification</h3>
        {dashboardData.pendingPartnerKYC.length > 0 ? (
          <div className="kyc-table">
            <table>
              <thead>
                <tr>
                  <th>Partner Name</th>
                  <th>Phone</th>
                  <th>Documents</th>
                  <th>Background Check</th>
                  <th>Submitted</th>
                  <th>Action</th>
                </tr>
              </thead>
              <tbody>
                {dashboardData.pendingPartnerKYC.map((partner, index) => (
                  <tr key={index}>
                    <td>{partner.name}</td>
                    <td>{partner.phone || 'N/A'}</td>
                    <td>
                      <span className="doc-status">
                        {(partner.vehicle_type && partner.vehicle_number) ? 
                          <FaCheckCircle style={{ color: '#4caf50' }} /> : 
                          <FaExclamationTriangle style={{ color: '#ff9800' }} />
                        }
                        {(partner.vehicle_type && partner.vehicle_number) ? 'Uploaded' : 'Pending'}
                      </span>
                    </td>
                    <td>
                      <span className="bg-check pending">
                        Pending
                      </span>
                    </td>
                    <td>
                      {partner.registered_at ? 
                        new Date(partner.registered_at).toLocaleDateString() : 
                        'N/A'
                      }
                    </td>
                    <td>
                      <button 
                        className="action-btn review"
                        onClick={() => handleReviewPartner(partner)}
                      >
                        Review
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <p>No pending partner KYC applications</p>
        )}
      </div>

      {/* Recent Verified */}
      <div className="kyc-section">
        <h3>Recently Verified</h3>
        <div className="verified-grid">
          <div className="verified-section">
            <h4>Businesses</h4>
            {dashboardData.verifiedBusinesses.map((business, index) => (
              <div key={index} className="verified-item">
                <FaCheckCircle style={{ color: '#4caf50' }} />
                <span>{business.name || business.business_name}</span>
                <small>Verified: {business.verified_at ? new Date(business.verified_at).toLocaleDateString() : 'Recently'}</small>
              </div>
            ))}
          </div>
          <div className="verified-section">
            <h4>Delivery Partners</h4>
            {dashboardData.verifiedPartners.map((partner, index) => (
              <div key={index} className="verified-item">
                <FaCheckCircle style={{ color: '#4caf50' }} />
                <span>{partner.name}</span>
                <small>Verified: {partner.verified_at ? new Date(partner.verified_at).toLocaleDateString() : 'Recently'}</small>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* KYC Review Modal */}
      {showModal && (
        <div className="modal-overlay" onClick={handleCloseModal}>
          <div className="modal-content kyc-modal" onClick={(e) => e.stopPropagation()}>
            <div className="modal-header">
              <h2>KYC Review - {selectedBusiness ? selectedBusiness.businessName : selectedPartner?.name || 'Review'}</h2>
              <button className="close-btn" onClick={handleCloseModal}>&times;</button>
            </div>
            
            {selectedBusiness ? (
              <div className="modal-body">
                {/* Business Information */}
                <div className="info-section">
                  <h3>Business Information</h3>
                  <div className="info-grid">
                    <div className="info-item">
                      <label>Business ID:</label>
                      <span>{selectedBusiness.business_id}</span>
                    </div>
                    <div className="info-item">
                      <label>Business Name:</label>
                      <span>{selectedBusiness.businessName}</span>
                    </div>
                    <div className="info-item">
                      <label>Business Type:</label>
                      <span>{selectedBusiness.business_type_name || selectedBusiness.businessType}</span>
                    </div>
                    <div className="info-item">
                      <label>Category:</label>
                      <span>{selectedBusiness.businessCategory}</span>
                    </div>
                    <div className="info-item">
                      <label>Email:</label>
                      <span>{selectedBusiness.businessEmail}</span>
                    </div>
                    <div className="info-item">
                      <label>Phone:</label>
                      <span>{selectedBusiness.businessNumber}</span>
                    </div>
                    <div className="info-item">
                      <label>Address:</label>
                      <span>{selectedBusiness.address}, {selectedBusiness.city}, {selectedBusiness.state} - {selectedBusiness.pincode}</span>
                    </div>
                    <div className="info-item">
                      <label>Status:</label>
                      <span className={`status-badge ${selectedBusiness.status?.toLowerCase()}`}>
                        {selectedBusiness.status}
                      </span>
                    </div>
                  </div>
                </div>

                {/* Owner Information */}
                <div className="info-section">
                  <h3>Owner Information</h3>
                  <div className="info-grid">
                    <div className="info-item">
                      <label>Owner Name:</label>
                      <span>{selectedBusiness.owner_details?.owner_name || 
                             `${selectedBusiness.owner_details?.first_name || ''} ${selectedBusiness.owner_details?.last_name || ''}`.trim() || 
                             'N/A'}</span>
                    </div>
                    <div className="info-item">
                      <label>Owner Email:</label>
                      <span>{selectedBusiness.owner_details?.owner_email || selectedBusiness.owner_details?.email || 'N/A'}</span>
                    </div>
                    <div className="info-item">
                      <label>Owner Phone:</label>
                      <span>{selectedBusiness.owner_details?.owner_phone || selectedBusiness.owner_details?.mobile || 'N/A'}</span>
                    </div>
                    <div className="info-item">
                      <label>PAN Number:</label>
                      <span>{selectedBusiness.owner_details?.pan_number || selectedBusiness.owner_details?.pan || 'Not Provided'}</span>
                    </div>
                    <div className="info-item">
                      <label>Aadhaar:</label>
                      <span>{selectedBusiness.owner_details?.aadhaar || 'Not Provided'}</span>
                    </div>
                  </div>
                </div>

                {/* KYC Status */}
                <div className="info-section">
                  <h3>KYC Status</h3>
                  <div className="info-grid">
                    <div className="info-item">
                      <label>Overall KYC Status:</label>
                      <span className={`status-badge ${selectedBusiness.owner_details?.kyc_status || 'pending'}`}>
                        {selectedBusiness.owner_details?.kyc_status || 'Pending'}
                      </span>
                    </div>
                    <div className="info-item">
                      <label>PAN Status:</label>
                      <span className={`status-badge ${selectedBusiness.owner_details?.pan_status || 'pending'}`}>
                        {selectedBusiness.owner_details?.pan_status || 'Pending'}
                      </span>
                    </div>
                    <div className="info-item">
                      <label>Bank Status:</label>
                      <span className={`status-badge ${selectedBusiness.owner_details?.bank_status || 'pending'}`}>
                        {selectedBusiness.owner_details?.bank_status || 'Pending'}
                      </span>
                    </div>
                  </div>
                </div>

                {/* Financial Details */}
                <div className="info-section">
                  <h3>Financial Information</h3>
                  <div className="info-grid">
                    <div className="info-item">
                      <label>GST Number:</label>
                      <span>{selectedBusiness.financial_details?.gstin || selectedBusiness.gst_num || 'Not Provided'}</span>
                    </div>
                    <div className="info-item">
                      <label>Bank Account:</label>
                      <span>{selectedBusiness.financial_details?.account_number || 'Not Provided'}</span>
                    </div>
                    <div className="info-item">
                      <label>IFSC Code:</label>
                      <span>{selectedBusiness.financial_details?.ifsc_code || 'Not Provided'}</span>
                    </div>
                    <div className="info-item">
                      <label>FSSAI Number:</label>
                      <span>{selectedBusiness.financial_details?.fssai_certification_number || 'Not Provided'}</span>
                    </div>
                  </div>
                </div>

                {/* Business Analytics */}
                {selectedBusiness.analytics && (
                  <div className="info-section">
                    <h3>Business Performance</h3>
                    <div className="info-grid">
                      <div className="info-item">
                        <label>Total Orders:</label>
                        <span>{selectedBusiness.analytics.total_orders || 0}</span>
                      </div>
                      <div className="info-item">
                        <label>Total Revenue:</label>
                        <span>₹{selectedBusiness.analytics.total_revenue?.toFixed(2) || '0.00'}</span>
                      </div>
                      <div className="info-item">
                        <label>Completed Orders:</label>
                        <span>{selectedBusiness.analytics.completed_orders || 0}</span>
                      </div>
                      <div className="info-item">
                        <label>Completion Rate:</label>
                        <span>{selectedBusiness.analytics.completion_rate || 0}%</span>
                      </div>
                    </div>
                  </div>
                )}

                {/* Action Buttons */}
                <div className="modal-actions">
                  <button 
                    className="btn-approve"
                    onClick={() => handleApproveKYC(selectedBusiness.business_id)}
                  >
                    <FaCheckCircle /> Approve KYC
                  </button>
                  <button 
                    className="btn-reject"
                    onClick={() => handleRejectKYC(selectedBusiness.business_id)}
                  >
                    <FaExclamationTriangle /> Reject KYC
                  </button>
                  <button 
                    className="btn-cancel"
                    onClick={handleCloseModal}
                  >
                    Close
                  </button>
                </div>
              </div>
            ) : selectedPartner ? (
              <div className="modal-body">
                {/* Partner Information */}
                <div className="info-section">
                  <h3>Delivery Partner Information</h3>
                  <div className="info-grid">
                    <div className="info-item">
                      <label>Partner ID:</label>
                      <span>{selectedPartner.provider_id}</span>
                    </div>
                    <div className="info-item">
                      <label>Name:</label>
                      <span>{selectedPartner.name}</span>
                    </div>
                    <div className="info-item">
                      <label>Phone:</label>
                      <span>{selectedPartner.phone || 'N/A'}</span>
                    </div>
                    <div className="info-item">
                      <label>Email:</label>
                      <span>{selectedPartner.email || 'N/A'}</span>
                    </div>
                    <div className="info-item">
                      <label>Status:</label>
                      <span className={`status-badge ${selectedPartner.status?.toLowerCase()}`}>
                        {selectedPartner.status}
                      </span>
                    </div>
                    <div className="info-item">
                      <label>Verified:</label>
                      <span className={`status-badge ${selectedPartner.is_verified ? 'verified' : 'pending'}`}>
                        {selectedPartner.is_verified ? 'Verified' : 'Not Verified'}
                      </span>
                    </div>
                  </div>
                </div>

                {/* Vehicle Information */}
                <div className="info-section">
                  <h3>Vehicle Information</h3>
                  <div className="info-grid">
                    <div className="info-item">
                      <label>Vehicle Type:</label>
                      <span>{selectedPartner.vehicle_type || 'Not Provided'}</span>
                    </div>
                    <div className="info-item">
                      <label>Vehicle Number:</label>
                      <span>{selectedPartner.vehicle_number || 'Not Provided'}</span>
                    </div>
                  </div>
                </div>

                {/* Performance Metrics */}
                {selectedPartner.total_deliveries !== undefined && (
                  <div className="info-section">
                    <h3>Performance Metrics</h3>
                    <div className="info-grid">
                      <div className="info-item">
                        <label>Total Deliveries:</label>
                        <span>{selectedPartner.total_deliveries || 0}</span>
                      </div>
                      <div className="info-item">
                        <label>Completed Deliveries:</label>
                        <span>{selectedPartner.completed_deliveries || 0}</span>
                      </div>
                      <div className="info-item">
                        <label>Average Rating:</label>
                        <span>{selectedPartner.average_rating || 'N/A'}</span>
                      </div>
                      <div className="info-item">
                        <label>Total Distance (km):</label>
                        <span>{selectedPartner.total_distance_km?.toFixed(2) || '0.00'}</span>
                      </div>
                    </div>
                  </div>
                )}

                {/* Registration Details */}
                <div className="info-section">
                  <h3>Registration Details</h3>
                  <div className="info-grid">
                    <div className="info-item">
                      <label>Registered At:</label>
                      <span>{selectedPartner.registered_at ? new Date(selectedPartner.registered_at).toLocaleString() : 'N/A'}</span>
                    </div>
                    <div className="info-item">
                      <label>Last Active:</label>
                      <span>{selectedPartner.last_active_at ? new Date(selectedPartner.last_active_at).toLocaleString() : 'N/A'}</span>
                    </div>
                  </div>
                </div>

                {/* Action Buttons */}
                <div className="modal-actions">
                  <button 
                    className="btn-approve"
                    onClick={() => {
                      alert('Partner KYC approval functionality will be implemented');
                      handleCloseModal();
                      fetchDashboardData();
                    }}
                  >
                    <FaCheckCircle /> Approve Partner
                  </button>
                  <button 
                    className="btn-reject"
                    onClick={() => {
                      alert('Partner KYC rejection functionality will be implemented');
                      handleCloseModal();
                      fetchDashboardData();
                    }}
                  >
                    <FaExclamationTriangle /> Reject Partner
                  </button>
                  <button 
                    className="btn-cancel"
                    onClick={handleCloseModal}
                  >
                    Close
                  </button>
                </div>
              </div>
            ) : (
              <div className="modal-body">
                <p>No details available</p>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
};

export default KYCDashboard;
