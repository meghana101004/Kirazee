import React, { useState, useEffect } from 'react';
// Fixed TextArea import issue - using Input.TextArea instead
import {
  Table,
  Button,
  Select,
  DatePicker,
  Input,
  InputNumber,
  Tag,
  Space,
  Card,
  Row,
  Col,
  Statistic,
  Modal,
  message,
  Tooltip,
  Badge
} from 'antd';
import {
  FiSearch,
  FiFilter,
  FiEye,
  FiCheckCircle,
  FiXCircle,
  FiTruck,
  FiCalendar,
  FiMapPin,
  FiRefreshCw,
  FiDownload,
  FiPhone,
  FiClipboard,
  FiSettings,
  FiFileText,
  FiFile,
  FiPaperclip,
  FiUser,
  FiAlertCircle,
  FiList,
  FiGrid
} from 'react-icons/fi';
import dayjs from 'dayjs';
import AdminService from '../services/adminService';
import '../../css/admin/DeliveryPartnerDetails.css';

const { Option } = Select;
const { RangePicker } = DatePicker;

const DeliveryPartnerReview = () => {
  // Static data for delivery partners
  const staticDeliveryPartners = [
    {
      id: 1,
      fullName: 'Rajesh Kumar',
      lastName: 'Kumar',
      mobileNumber: '+91 9876543210',
      licenseNumber: 'DL1420110012345',
      vehicleType: 'Motorcycle',
      vehicleNumber: 'DL01AB1234',
      status: 'Pending Review',
      fullAddress: '123 Main Street, Sector 15, New Delhi',
      currentAddress: '123 Main Street, Sector 15, New Delhi',
      city: 'New Delhi',
      deliveryServiceArea: 'Central Delhi',
      pincode: '110001',
      state: 'Delhi',
      bankAccountNumber: '1234567890123456',
      ifscCode: 'SBIN0001234',
      panNumber: 'ABCDE1234F',
      submissionDate: '2024-10-15',
      documents: [
        { type: 'License Document', name: 'driving_license.pdf', url: '#' },
        { type: 'RC Book Document', name: 'rc_book.pdf', url: '#' },
        { type: 'Aadhar Document', name: 'aadhar_card.pdf', url: '#' },
        { type: 'Bank Book Document', name: 'bank_passbook.pdf', url: '#' }
      ]
    },
    {
      id: 2,
      fullName: 'Priya Sharma',
      lastName: 'Sharma',
      mobileNumber: '+91 9876543211',
      licenseNumber: 'DL1420110012346',
      vehicleType: 'Scooter',
      vehicleNumber: 'DL02CD5678',
      status: 'Approved',
      fullAddress: '456 Park Avenue, Sector 22, Gurgaon',
      currentAddress: '456 Park Avenue, Sector 22, Gurgaon',
      city: 'Gurgaon',
      deliveryServiceArea: 'Gurgaon Central',
      pincode: '122001',
      state: 'Haryana',
      bankAccountNumber: '2345678901234567',
      ifscCode: 'HDFC0001235',
      panNumber: 'BCDEF2345G',
      submissionDate: '2024-10-12',
      documents: [
        { type: 'License Document', name: 'driving_license.pdf', url: '#' },
        { type: 'RC Book Document', name: 'rc_book.pdf', url: '#' },
        { type: 'Aadhar Document', name: 'aadhar_card.pdf', url: '#' },
        { type: 'Bank Book Document', name: 'bank_passbook.pdf', url: '#' }
      ]
    },
    {
      id: 3,
      fullName: 'Amit Singh',
      lastName: 'Singh',
      mobileNumber: '+91 9876543212',
      licenseNumber: 'DL1420110012347',
      vehicleType: 'Bicycle',
      vehicleNumber: 'N/A',
      status: 'Rejected',
      fullAddress: '789 Green Street, Sector 45, Noida',
      currentAddress: '789 Green Street, Sector 45, Noida',
      city: 'Noida',
      deliveryServiceArea: 'Noida Extension',
      pincode: '201301',
      state: 'Uttar Pradesh',
      bankAccountNumber: '3456789012345678',
      ifscCode: 'ICIC0001236',
      panNumber: 'CDEFG3456H',
      submissionDate: '2024-10-10',
      documents: [
        { type: 'License Document', name: 'driving_license.pdf', url: '#' },
        { type: 'Aadhar Document', name: 'aadhar_card.pdf', url: '#' },
        { type: 'Bank Book Document', name: 'bank_passbook.pdf', url: '#' }
      ]
    },
    {
      id: 4,
      fullName: 'Ravi Kumar',
      lastName: 'Kumar',
      mobileNumber: '+91 9876543213',
      licenseNumber: 'DL1420110012348',
      vehicleType: 'Car',
      vehicleNumber: 'DL03EF9012',
      status: 'Pending Review',
      fullAddress: '321 Market Road, Sector 18, Faridabad',
      currentAddress: '321 Market Road, Sector 18, Faridabad',
      city: 'Faridabad',
      deliveryServiceArea: 'Faridabad Central',
      pincode: '121001',
      state: 'Haryana',
      bankAccountNumber: '4567890123456789',
      ifscCode: 'AXIS0001237',
      panNumber: 'DEFGH4567I',
      submissionDate: '2024-10-18',
      documents: [
        { type: 'License Document', name: 'driving_license.pdf', url: '#' },
        { type: 'RC Book Document', name: 'rc_book.pdf', url: '#' },
        { type: 'Aadhar Document', name: 'aadhar_card.pdf', url: '#' },
        { type: 'Bank Book Document', name: 'bank_passbook.pdf', url: '#' }
      ]
    }
  ];

  const [deliveryPartners, setDeliveryPartners] = useState([]);
  const [filteredPartners, setFilteredPartners] = useState([]);
  const [recentApprovedPartners, setRecentApprovedPartners] = useState([]);
  const [loading, setLoading] = useState(false);
  const [selectedPartner, setSelectedPartner] = useState(null);
  const [detailModalVisible, setDetailModalVisible] = useState(false);
  const [selectedRowKeys, setSelectedRowKeys] = useState([]);
  const [bulkActionLoading, setBulkActionLoading] = useState(false);
  const [documentModalVisible, setDocumentModalVisible] = useState(false);
  const [selectedDocument, setSelectedDocument] = useState(null);
  const [pagination, setPagination] = useState({ current: 1, pageSize: 10, total: 0 });
  const [error, setError] = useState(null);
  const [decisionModalVisible, setDecisionModalVisible] = useState(false);
  const [decisionAction, setDecisionAction] = useState(null);
  const [decisionDeclineReason, setDecisionDeclineReason] = useState('');
  const [decisionRequiredChanges, setDecisionRequiredChanges] = useState([]);
  const [decisionReapplyDays, setDecisionReapplyDays] = useState(3);
  const [decisionRejectionReasons, setDecisionRejectionReasons] = useState([]);

  // Review Templates Management
  const [reviewTemplates, setReviewTemplates] = useState({
    rejection: [],
    required_changes: [],
    approval: []
  });
  const [templatesLoading, setTemplatesLoading] = useState(false);

  // Filter states
  const [filters, setFilters] = useState({
    status: 'all', // Default to show all partners
    vehicleType: 'all',
    location: '',
    dateRange: null,
    searchText: ''
  });

  // View mode state
  const [viewMode, setViewMode] = useState('grid'); // 'list' or 'grid' - default to grid

  // Load review templates when component mounts
  useEffect(() => {
    loadReviewTemplates();
  }, []);

  const loadReviewTemplates = async () => {
    try {
      setTemplatesLoading(true);
      const response = await AdminService.getReviewTemplates();
      if (response.success) {
        const templates = response.data || [];
        const grouped = {
          rejection: templates.filter(t => t.reason_type === 'rejection'),
          required_changes: templates.filter(t => t.reason_type === 'required_changes'),
          approval: templates.filter(t => t.reason_type === 'approval')
        };
        setReviewTemplates(grouped);
      }
    } catch (error) {
      console.error('Failed to load review templates:', error);
    } finally {
      setTemplatesLoading(false);
    }
  };

  // Load unverified delivery partners from API
  const loadUnverifiedPartners = async () => {
    try {
      setLoading(true);
      setError(null);
      console.log('Loading unverified partners with filters:', filters);

      // Prepare query params - only pagination, no filtering (client-side filtering)
      const params = {
        page: pagination.current,
        limit: pagination.pageSize
      };

      console.log('Making API call with params:', params);

      // Call the API
      const response = await AdminService.getUnverifiedDeliveryPartnersNew(params);
      console.log('API response:', response);

      if (response && response.success) {
        const partners = response.partners || [];
        const recentApproved = response.recent_approved_partners || [];

        console.log('Partners loaded:', partners.length);
        console.log('Recent approved partners loaded:', recentApproved.length);

        // Map partners to table rows
        const mappedPartners = partners.map(mapUnverifiedPartnerToRow);
        const mappedRecentApproved = recentApproved.map(mapUnverifiedPartnerToRow);

        setDeliveryPartners(mappedPartners);
        setFilteredPartners(mappedPartners);
        setRecentApprovedPartners(mappedRecentApproved);

        // Update pagination
        if (response.pagination) {
          setPagination(prev => ({
            ...prev,
            current: response.pagination.current_page || 1,
            pageSize: response.pagination.per_page || 10,
            total: response.pagination.total || 0
          }));
        }
        console.log('State updated successfully');
      } else {
        throw new Error(response?.message || 'Failed to load partners');
      }
    } catch (error) {
      console.error('Error loading unverified partners:', error);
      const errorMsg = error.message || 'Failed to load delivery partners';
      setError(errorMsg);
      message.error(errorMsg);
      setDeliveryPartners([]);
      setFilteredPartners([]);
      setRecentApprovedPartners([]);

      // Reset pagination on error
      setPagination({
        ...pagination,
        total: 0,
        current: 1,
        pageSize: 10,
        totalPages: 0
      });
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadUnverifiedPartners();
  }, [pagination.current, pagination.pageSize]);

  useEffect(() => {
    applyFilters();
  }, [deliveryPartners, filters]);

  const applyFilters = () => {
    let filtered = [...deliveryPartners];

    // Filter by status
    if (filters.status && filters.status !== 'all') {
      filtered = filtered.filter(partner => {
        const partnerStatus = partner.status?.toLowerCase();
        const filterStatus = filters.status.toLowerCase();

        if (filterStatus === 'pending') {
          return partnerStatus === 'pending review' || partnerStatus === 'pending';
        } else if (filterStatus === 'approved') {
          return partnerStatus === 'approved';
        } else if (filterStatus === 'rejected') {
          return partnerStatus === 'rejected';
        }
        return true;
      });
    }

    // Filter by vehicle type
    if (filters.vehicleType && filters.vehicleType !== 'all') {
      filtered = filtered.filter(partner => {
        const partnerVehicleType = partner.vehicleType?.toLowerCase();
        const filterVehicleType = filters.vehicleType.toLowerCase();
        
        // Map both partner's vehicle type and filter to standardized categories
        const partnerCategory = mapVehicleTypeToCategory(partnerVehicleType);
        const filterCategory = filterVehicleType;
        
        // Check direct match or category match
        return partnerVehicleType === filterVehicleType || partnerCategory === filterCategory;
      });
    }

    // Filter by search text
    if (filters.searchText && filters.searchText.trim()) {
      const searchTerm = filters.searchText.toLowerCase().trim();
      filtered = filtered.filter(partner => {
        return (
          (partner.fullName && partner.fullName.toLowerCase().includes(searchTerm)) ||
          (partner.lastName && partner.lastName.toLowerCase().includes(searchTerm)) ||
          (partner.mobileNumber && partner.mobileNumber.includes(searchTerm)) ||
          (partner.vehicleNumber && partner.vehicleNumber.toLowerCase().includes(searchTerm)) ||
          (partner.licenseNumber && partner.licenseNumber.toLowerCase().includes(searchTerm))
        );
      });
    }

    // Filter by location
    if (filters.location && filters.location.trim()) {
      const locationTerm = filters.location.toLowerCase().trim();
      filtered = filtered.filter(partner => {
        return (
          (partner.fullAddress && partner.fullAddress.toLowerCase().includes(locationTerm)) ||
          (partner.city && partner.city.toLowerCase().includes(locationTerm)) ||
          (partner.state && partner.state.toLowerCase().includes(locationTerm))
        );
      });
    }

    // Filter by date range
    if (filters.dateRange && filters.dateRange[0] && filters.dateRange[1]) {
      const startDate = filters.dateRange[0].startOf('day');
      const endDate = filters.dateRange[1].endOf('day');

      filtered = filtered.filter(partner => {
        if (!partner.submissionDate) return false;
        const partnerDate = dayjs(partner.submissionDate);
        return partnerDate.isAfter(startDate) && partnerDate.isBefore(endDate);
      });
    }

    setFilteredPartners(filtered);
  };

  const mapBackendStatusToUI = (status) => {
    const s = (status || '').toString().toLowerCase();
    if (s === 'approved') return 'Approved';
    if (s === 'declined' || s === 'rejected') return 'Rejected';
    if (s === 'in_progress' || s === 'pending' || s === 'submitted' || s === 'pending_review') return 'Pending Review';
    return 'Pending Review';
  };

  const capitalize = (str) => {
    if (!str || typeof str !== 'string') return '';
    return str.charAt(0).toUpperCase() + str.slice(1);
  };

  const mapUnverifiedPartnerToRow = (p) => ({
    id: p.partner_id || p.id,
    application_id: null,
    userId: p.user?.user_id || p.user_id || '',
    fullName: p.full_name || '',
    lastName: p.last_name || '',
    mobileNumber: p.mobile_number || '',
    licenseNumber: p.license_number || '',
    vehicleType: capitalize(p.vehicle_type || ''),
    vehicleNumber: p.vehicle_number || 'N/A',
    status: mapBackendStatusToUI(p.status),
    city: p.city || '',
    state: p.state || '',
    deliveryServiceArea: p.delivery_service_area || '',
    pincode: p.pincode || '',
    submissionDate: p.submission_date || p.created_at || new Date().toISOString(),
    documents: Array.isArray(p.documents) ? p.documents : []
  });

  const mapApplicantToRow = (a) => ({
    id: a.application_id,

    applicationId: a.application_id,
    userId: a.user?.user_id || a.user_id || '',
    fullName: a.full_name || a.onboarding_data?.full_name || '',
    lastName: a.last_name || a.onboarding_data?.last_name || '',
    mobileNumber: a.mobile_number || a.onboarding_data?.mobile_number || '',
    licenseNumber: a.license_number || a.onboarding_data?.license_number || '',
    vehicleType: capitalize(a.vehicle_type || a.onboarding_data?.vehicle_type || ''),
    vehicleNumber: a.vehicle_number || a.onboarding_data?.vehicle_number || 'N/A',
    status: mapBackendStatusToUI(a.status),
    city: a.city || a.onboarding_data?.city || '',
    state: a.state || a.onboarding_data?.state || '',
    deliveryServiceArea: a.delivery_service_area || a.onboarding_data?.delivery_service_area || '',
    pincode: a.pincode || a.onboarding_data?.pincode || '',
    submissionDate: a.submission_date || a.created_at || new Date().toISOString(),
    documents: Array.isArray(a.documents) ? a.documents : []
  });

  const loadApplicants = async () => {
    try {
      setLoading(true);
      const params = {
        status: filters.status,
        vehicle_type: filters.vehicleType,
        q: filters.searchText || '',
        city: filters.location || '',
        page: pagination.current,
        limit: pagination.pageSize
      };
      if (filters.dateRange && filters.dateRange[0] && filters.dateRange[1]) {
        params.date_from = dayjs(filters.dateRange[0]).toISOString();
        params.date_to = dayjs(filters.dateRange[1]).toISOString();
      }

      const data = await AdminService.getOnboardingApplicants(params);
      if (data && data.success) {
        const rows = Array.isArray(data.applicants) ? data.applicants.map(mapApplicantToRow) : [];
        setDeliveryPartners(rows);
        const total = data.pagination?.total || data.total || data.count || rows.length;
        setPagination((prev) => ({ ...prev, total }));
      } else {
        setDeliveryPartners([]);
        setPagination((prev) => ({ ...prev, total: 0 }));
      }
    } catch (error) {
      message.error('Failed to load applicants');
      setDeliveryPartners([]);
      setPagination((prev) => ({ ...prev, total: 0 }));
    } finally {
      setLoading(false);
    }
  };

  const handleTableChange = (pg) => {
    setPagination((prev) => ({ ...prev, current: pg.current, pageSize: pg.pageSize }));
  };

  const handleFilterChange = (key, value) => {
    setFilters(prev => ({
      ...prev,
      [key]: value
    }));
  };

  const clearFilters = () => {
    setFilters({
      status: 'all',
      vehicleType: 'all',
      location: '',
      dateRange: null,
      searchText: ''
    });
  };

  const mapDocTypeToName = (t) => {
    const key = (t || '').toString().toLowerCase();
    const map = {
      license: 'License Document',
      rc_book: 'RC Book Document',
      aadhar: 'Aadhar Document',
      bank_book: 'Bank Book Document',
      bank_passbook: 'Bank Book Document'
    };
    return map[key] || capitalize(key.replace(/_/g, ' ')) || 'Document';
  };

  const mapNameToDocType = (display) => {
    const k = (display || '').toString().toLowerCase().trim();
    const rev = {
      'license document': 'license',
      'rc book document': 'rc_book',
      'aadhar document': 'aadhar',
      'bank book document': 'bank_book',
      'bank passbook document': 'bank_book'
    };
    return rev[k] || k.replace(/\s+/g, '_');
  };

  const mapDetailToPartner = (resp) => {
    const ap = resp?.application || resp || {};
    const ob = ap?.onboarding_data || {};
    const docsSource = Array.isArray(resp?.documents)
      ? resp.documents
      : Array.isArray(ap?.documents)
        ? ap.documents
        : [];
    const docs = docsSource.map(d => ({
      type: mapDocTypeToName(d.document_type || d.type),
      rawType: (d.document_type || d.type || '').toLowerCase(),
      name: d.document_name || d.file_name || '',
      url: d.document_url || d.file_url || '#',
      content_type: d.content_type || d.mime_type || '',
      uploadedAt: d.uploaded_at || null,
      isVerified: !!d.is_verified
    }));
    const vs = resp?.verification_summary || ap?.verification_summary || {};
    return {
      id: ap.application_id || ap.id,
      applicationId: ap.application_id || ap.id,
      userId: resp?.user?.user_id || resp?.user_id || '',
      fullName: ob.full_name || ap.full_name || '',
      lastName: ob.last_name || ap.last_name || '',
      mobileNumber: ob.mobile_number || ap.mobile_number || '',
      licenseNumber: ob.license_number || ap.license_number || '',
      vehicleType: capitalize(ob.vehicle_type || ap.vehicle_type || ''),
      vehicleNumber: ob.vehicle_number || ap.vehicle_number || 'N/A',
      status: mapBackendStatusToUI(ap.status),
      fullAddress: ob.full_address || ap.full_address || '',
      currentAddress: ob.current_address || ob.full_address || ap.current_address || ap.full_address || '',
      city: ob.city || ap.city || '',
      deliveryServiceArea: ob.delivery_service_area || ap.delivery_service_area || '',
      pincode: ob.pincode || ap.pincode || '',
      state: ob.state || ap.state || '',
      bankAccountNumber: ob.bank_account_number || ap.bank_account_number || '',
      ifscCode: ob.ifsc_code || ap.ifsc_code || '',
      panNumber: ob.pan_number || ap.pan_number || '',
      submissionDate: ap.submission_date || ap.created_at || new Date().toISOString(),
      documents: docs,
      verificationSummary: {
        required_doc_types: Array.isArray(vs.required_doc_types) ? vs.required_doc_types : [],
        present_doc_types: Array.isArray(vs.present_doc_types) ? vs.present_doc_types : [],
        verified_doc_types: Array.isArray(vs.verified_doc_types) ? vs.verified_doc_types : [],
        all_documents_present: !!vs.all_documents_present,
        all_documents_verified: !!vs.all_documents_verified
      }
    };
  };

  const mapKycDetailToPartner = (resp) => {
    const p = resp?.partner || {};
    const f = resp?.financials || {};
    const vs = resp?.verification_summary || {};
    const docs = Array.isArray(resp?.documents) ? resp.documents.map(d => ({
      type: mapDocTypeToName(d.document_type || d.type),
      rawType: (d.document_type || d.type || '').toLowerCase(),
      name: d.document_name || d.file_name || '',
      url: d.document_url || d.file_url || '#',
      content_type: d.content_type || d.mime_type || '',
      uploadedAt: d.uploaded_at || null,
      isVerified: !!d.is_verified
    })) : [];
    const appId = resp?.application_id || resp?.application?.application_id || resp?.application?.id || resp?.partner?.application_id || resp?.latest_application_id || resp?.latest_application?.id;
    const user_id = resp?.user?.user_id || resp?.user_id || '';
    return {
      id: p.partner_id || p.id,
      applicationId: appId || null,
      userId: user_id || '',
      fullName: p.full_name || '',
      lastName: p.last_name || '',
      mobileNumber: p.mobile_number || '',
      licenseNumber: p.license_number || '',
      vehicleType: capitalize(p.vehicle_type || ''),
      vehicleNumber: p.vehicle_number || 'N/A',
      status: mapBackendStatusToUI(p.status),
      fullAddress: p.full_address || '',
      currentAddress: p.current_address || p.full_address || '',
      city: p.city || '',
      deliveryServiceArea: p.delivery_service_area || '',
      pincode: p.pincode || '',
      state: p.state || '',
      bankAccountNumber: f.bank_account_number || f.account_number || '',
      ifscCode: f.ifsc_code || '',
      panNumber: f.pan_number || f.pan || '',
      submissionDate: p.created_at || new Date().toISOString(),
      documents: docs,
      verificationSummary: {
        required_doc_types: Array.isArray(vs.required_doc_types) ? vs.required_doc_types : [],
        present_doc_types: Array.isArray(vs.present_doc_types) ? vs.present_doc_types : [],
        verified_doc_types: Array.isArray(vs.verified_doc_types) ? vs.verified_doc_types : [],
        all_documents_present: !!vs.all_documents_present,
        all_documents_verified: !!vs.all_documents_verified
      }
    };
  };

  const viewPartnerDetails = async (partner) => {
    if (!partner || (partner.id === undefined && partner.application_id === undefined)) {
      console.error('Invalid partner data:', partner);
      message.error('Invalid partner data. Please try again.');
      return;
    }

    const partnerId = partner.id || partner.application_id;

    try {
      setLoading(true);
      console.log(`Fetching details for partner ID: ${partnerId}`);

      // Fetch the delivery partner KYC details (with fallback inside service)
      const data = await AdminService.getDeliveryPartnerKycDetail(partnerId);

      if (!data) {
        throw new Error('No data received from server');
      }

      console.log('Partner details response:', data);

      // Map the data to our internal format based on shape
      const mapped = (data && (data.partner || data.financials))
        ? mapKycDetailToPartner(data)
        : mapDetailToPartner(data);

      setSelectedPartner(mapped);
      setDetailModalVisible(true);

    } catch (error) {
      console.error('Error loading applicant details:', error);
      const errMsg = error?.message || 'Unknown error';
      message.error(`Failed to load full details: ${errMsg}`);
      // Fallback: show minimal details from the row so user isn't blocked
      const minimal = {
        id: partnerId,
        userId: partner.userId || partner.user_id || partner.id || '',
        fullName: partner.fullName || '',
        lastName: partner.lastName || '',
        mobileNumber: partner.mobileNumber || '',
        licenseNumber: partner.licenseNumber || '',
        vehicleType: partner.vehicleType || '',
        vehicleNumber: partner.vehicleNumber || 'N/A',
        status: partner.status || 'Pending Review',
        fullAddress: partner.fullAddress || '',
        currentAddress: partner.currentAddress || partner.fullAddress || '',
        city: partner.city || '',
        deliveryServiceArea: partner.deliveryServiceArea || '',
        pincode: partner.pincode || '',
        state: partner.state || '',
        bankAccountNumber: partner.bankAccountNumber || '',
        ifscCode: partner.ifscCode || '',
        panNumber: partner.panNumber || '',
        submissionDate: partner.submissionDate || new Date().toISOString(),
        documents: Array.isArray(partner.documents) ? partner.documents : []
      };
      setSelectedPartner(minimal);
      setDetailModalVisible(true);
      message.info('Showing limited details until the full KYC endpoint is available.');
    } finally {
      setLoading(false);
    }
  };

  const promptForBusinessId = () => new Promise((resolve) => {
    let value = '';
    Modal.confirm({
      title: 'Approve Applicant',
      content: (
        <div>
          <div style={{ marginBottom: '8px' }}>Enter Business ID to assign</div>
          <Input placeholder="Business ID" onChange={(e) => { value = e.target.value; }} />
        </div>
      ),
      okText: 'Approve',
      onOk: () => resolve(value?.trim() || null),
      onCancel: () => resolve(null)
    });
  });

  const promptForDeclineReason = () => new Promise((resolve) => {
    let reason = '';
    Modal.confirm({
      title: 'Decline Applicant',
      content: (
        <div>
          <div style={{ marginBottom: '8px' }}>Provide decline reason (optional)</div>
          <Input.TextArea rows={3} placeholder="Reason" onChange={(e) => { reason = e.target.value; }} />
        </div>
      ),
      okText: 'Decline',
      onOk: () => resolve(reason?.trim() || ''),
      onCancel: () => resolve(null)
    });
  });

  const handlePartnerAction = async (partnerId, action) => {
    if (!partnerId) {
      message.error('Invalid partner id');
      return;
    }
    try {
      setLoading(true);
      if (action === 'approve') {
        await AdminService.approveDeliveryPartner(partnerId);
        message.success('Partner approved');
        await loadUnverifiedPartners();
      } else if (action === 'reject') {
        // Find the partner in the list to open decision modal
        const partner = filteredPartners.find(p => p.id === partnerId) || deliveryPartners.find(p => p.id === partnerId);
        if (partner) {
          setLoading(false);
          openDecision(partner, 'reject');
        } else {
          message.error('Partner not found');
        }
      } else {
        message.info('Only approval and rejection are supported.');
      }
    } catch (e) {
      message.error(e?.message || 'Action failed');
    } finally {
      setLoading(false);
    }
  };

  const handleBulkAction = async (action) => {
    if (selectedRowKeys.length === 0) {
      message.warning('Please select delivery partners to perform bulk action');
      return;
    }
    try {
      setBulkActionLoading(true);
      if (action === 'approve') {
        const approved = [];
        const skipped = [];
        for (const id of selectedRowKeys) {
          try {
            const data = await AdminService.getDeliveryPartnerKycDetail(id);
            const mapped = (data && (data.partner || data.financials))
              ? mapKycDetailToPartner(data)
              : mapDetailToPartner(data);
            const vs = mapped.verificationSummary || {};
            if (vs.all_documents_present && vs.all_documents_verified) {
              await AdminService.approveDeliveryPartner(id);
              approved.push(id);
            } else {
              const missing = (vs.required_doc_types || []).filter((r) => !(vs.present_doc_types || []).includes(r));
              const unverified = (vs.required_doc_types || []).filter((r) => !(vs.verified_doc_types || []).includes(r));
              skipped.push({ id, missing, unverified });
            }
          } catch (e) {
            skipped.push({ id, error: e?.message || 'Unknown error' });
          }
        }
        if (approved.length) message.success(`${approved.length} partner(s) approved`);
        if (skipped.length) {
          const lines = skipped.slice(0, 5).map(s => `#${s.id}: ${[
            s.missing && s.missing.length ? `Missing: ${s.missing.join(', ')}` : null,
            s.unverified && s.unverified.length ? `Unverified: ${s.unverified.join(', ')}` : null,
            s.error ? `Error: ${s.error}` : null
          ].filter(Boolean).join(' | ')}`);
          message.warning(`Skipped ${skipped.length} partner(s).\n${lines.join('\n')}`);
        }
      } else {
        message.info('Bulk reject/pending is not supported in this KYC flow.');
      }
      setSelectedRowKeys([]);
      await loadUnverifiedPartners();
    } catch (e) {
      message.error(e?.message || 'Bulk action failed');
    } finally {
      setBulkActionLoading(false);
    }
  };

  const openDocument = (doc) => {
    const url = doc?.url || doc?.upload_url || doc?.file_url || (typeof doc === 'string' ? doc : '');
    if (!url) {
      message.warning('Document URL not available');
      return;
    }

    // Check if it's an image file
    const isImage = isImageFile(url);

    if (isImage) {
      // Show images in modal
      setSelectedDocument(doc);
      setDocumentModalVisible(true);
    } else {
      // Open PDF, DOC, DOCX, PPT files in new tab
      window.open(url, '_blank', 'noopener,noreferrer');
    }
  };

  const getFileExtension = (url) => {
    if (!url) return '';
    const urlWithoutQuery = url.split('?')[0];
    const match = urlWithoutQuery.match(/\.([^.]+)$/);
    return match ? match[1].toLowerCase() : '';
  };

  const isSameOrigin = (url) => {
    try {
      const urlObj = new URL(url);
      return urlObj.origin === window.location.origin;
    } catch (e) {
      return false;
    }
  };

  const isImageFile = (url, contentType) => {
    if (contentType && contentType.startsWith('image/')) return true;
    const ext = getFileExtension(url);
    return ['png', 'jpg', 'jpeg', 'gif', 'bmp', 'webp', 'svg'].includes(ext);
  };

  const isPdfFile = (url, contentType) => {
    if (contentType && contentType === 'application/pdf') return true;
    const ext = getFileExtension(url);
    return ext === 'pdf';
  };

  const isDocumentFile = (url, contentType) => {
    if (contentType && (contentType.includes('word') || contentType.includes('document') || contentType.includes('msword') || contentType.includes('openxml'))) return true;
    const ext = getFileExtension(url);
    return ['doc', 'docx', 'xls', 'xlsx', 'ppt', 'pptx'].includes(ext);
  };

  const getDocumentViewerUrl = (url) => {
    const ext = getFileExtension(url);

    // For same-origin URLs, check if we can use external viewers
    if (!isSameOrigin(url)) {
      const encodedUrl = encodeURIComponent(url);

      // Use Microsoft Office Online Viewer for Office documents
      if (['doc', 'docx', 'xls', 'xlsx', 'ppt', 'pptx'].includes(ext)) {
        return `https://view.officeapps.live.com/op/view.aspx?src=${encodedUrl}`;
      }

      // Use Google Docs Viewer as fallback
      return `https://docs.google.com/viewer?url=${encodedUrl}&embedded=true`;
    }

    // For same-origin URLs that might be blocked by X-Frame-Options, return null to force direct display
    return null;
  };

  const toggleDocumentVerification = async (doc) => {
    const docType = doc?.rawType || (doc?.type ? mapNameToDocType(doc.type) : null);
    if (!selectedPartner?.id || !docType) {
      message.error('Missing partner or document type');
      return;
    }
    try {
      setLoading(true);
      await AdminService.setPartnerDocumentVerification(selectedPartner.id, docType, !doc.isVerified);
      const data = await AdminService.getDeliveryPartnerKycDetail(selectedPartner.id);
      const mapped = (data && (data.partner || data.financials))
        ? mapKycDetailToPartner(data)
        : mapDetailToPartner(data);
      setSelectedPartner(mapped);
      message.success(!doc.isVerified ? 'Document verified' : 'Verification removed');
    } catch (e) {
      const msg = e?.message || '';
      if (msg.includes('404')) {
        message.error('Document verification endpoint is not available yet');
      } else {
        message.error(msg || 'Failed to update document verification');
      }
    } finally {
      setLoading(false);
    }
  };

  const canApproveSelected = () => {
    const vs = selectedPartner?.verificationSummary || {};
    return !!(vs.all_documents_present && vs.all_documents_verified);
  };

  const handleApproveSelected = async () => {
    if (!selectedPartner?.id) return;
    try {
      setLoading(true);
      await AdminService.approveDeliveryPartner(selectedPartner.id);
      message.success('Partner approved');
      setDetailModalVisible(false);
      await loadUnverifiedPartners();
    } catch (e) {
      const details = e?.details || {};
      const missing = details.missing_docs || [];
      const unverified = details.unverified_docs || [];
      const parts = [];
      if (missing.length) parts.push(`Missing: ${missing.join(', ')}`);
      if (unverified.length) parts.push(`Unverified: ${unverified.join(', ')}`);
      const info = parts.length ? ` (${parts.join(' | ')})` : '';
      message.error((e?.message || 'Approval failed') + info);
    } finally {
      setLoading(false);
    }
  };

  const openDecision = (partner, action) => {
    setSelectedPartner(partner);
    const act = action === 'reject' ? 'declined' : 'required_changes';
    setDecisionAction(act);
    setDecisionDeclineReason('');
    setDecisionRequiredChanges([]);
    setDecisionRejectionReasons([]);
    setDecisionReapplyDays(3);
    setDecisionModalVisible(true);
  };

  const submitDecision = async () => {
    let appId = selectedPartner?.applicationId;
    
    // Try to get application ID from partner details
    if (!appId && selectedPartner?.id) {
      try {
        const data = await AdminService.getDeliveryPartnerKycDetail(selectedPartner.id);
        const mapped = (data && (data.partner || data.financials))
          ? mapKycDetailToPartner(data)
          : mapDetailToPartner(data);
        if (mapped?.applicationId) {
          appId = mapped.applicationId;
          setSelectedPartner((prev) => ({ ...(prev || {}), applicationId: appId }));
        }
      } catch (_) { }
    }
    
    // Fallback 1: Search by user_id if available
    if (!appId && selectedPartner?.userId) {
      try {
        const listResp = await AdminService.getOnboardingApplicants({ status: 'all', limit: 100 });
        const arr = listResp?.applicants || listResp?.data?.applicants || listResp?.results || listResp?.items || [];
        if (Array.isArray(arr)) {
          const match = arr.find(a => a.user_id === selectedPartner.userId || a.user?.user_id === selectedPartner.userId);
          if (match) {
            appId = match.application_id || match.id;
          }
        }
      } catch (_) { }
    }
    
    // Fallback 2: Search by phone/name to resolve application_id
    if (!appId) {
      try {
        const qRaw = selectedPartner?.mobileNumber || selectedPartner?.fullName || '';
        const q = typeof qRaw === 'string' ? (qRaw.replace(/\D/g, '') || qRaw) : qRaw;
        if (q) {
          const listResp = await AdminService.getOnboardingApplicants({ q, status: 'all', limit: 10 });
          const arr = listResp?.applicants || listResp?.data?.applicants || listResp?.results || listResp?.items || [];
          if (Array.isArray(arr) && arr.length > 0) {
            // Try to match by user_id first, then by phone
            let match = arr.find(a => 
              (a.user_id === selectedPartner.userId) || 
              (a.user?.user_id === selectedPartner.userId) ||
              (a.mobile_number === selectedPartner.mobileNumber)
            );
            if (!match) match = arr[0]; // Fallback to first result
            appId = match?.application_id || match?.id;
          }
        }
      } catch (_) { }
    }
    
    if (!appId) {
      // If no application ID found, use the partner reject endpoint directly
      if (decisionAction === 'declined' && selectedPartner?.id) {
        try {
          const body = {
            decline_reason: decisionDeclineReason || undefined,
            rejection_reasons: decisionRejectionReasons,
            reapply_after_days: decisionReapplyDays || undefined
          };
          await AdminService.rejectDeliveryPartner(selectedPartner.id, body);
          message.success('Partner rejected successfully');
          setDecisionModalVisible(false);
          setDetailModalVisible(false);
          await loadUnverifiedPartners();
          return;
        } catch (e) {
          const details = e?.details || {};
          const msg = details.message || e?.message || 'Failed to reject partner';
          message.error(msg);
          return;
        }
      }
      message.error('Could not resolve applicant ID for decision. This partner may not have an application record.');
      return;
    }
    try {
      const body = decisionAction === 'declined'
        ? {
          decision: 'declined',
          decline_reason: decisionDeclineReason || undefined,
          rejection_reasons: decisionRejectionReasons, // New format
          reapply_after_days: decisionReapplyDays || undefined
        }
        : {
          decision: 'required_changes',
          // Convert tags array into an object the API expects
          required_changes: Array.isArray(decisionRequiredChanges)
            ? decisionRequiredChanges.reduce((acc, curr, idx) => {
              const key = (curr || `change_${idx + 1}`)
                .toString()
                .trim()
                .toLowerCase()
                .replace(/[^a-z0-9]+/g, '_') || `change_${idx + 1}`;
              acc[key] = curr;
              return acc;
            }, {})
            : decisionRequiredChanges || {},
          reapply_after_days: decisionReapplyDays || undefined
        };
      await AdminService.decideOnboardingApplicant(appId, body);
      message.success(decisionAction === 'declined' ? 'Applicant declined' : 'Changes requested');
      
      setDecisionModalVisible(false);
      setDetailModalVisible(false);
      await loadUnverifiedPartners();
    } catch (e) {
      const details = e?.details || {};
      const msg = details.message || e?.message || 'Failed to submit decision';
      message.error(msg);
    }
  };

  // Map legacy vehicle types to new standardized categories
  const mapVehicleTypeToCategory = (vehicleType) => {
    if (!vehicleType) return '';
    
    const type = String(vehicleType).toLowerCase().trim();
    
    // Mapping old types to new categories
    const categoryMap = {
      'bicycle': 'cycles',
      'bike': 'cycles',
      'cycle': 'cycles',
      'motorcycle': 'bikes_scooters',
      'scooter': 'bikes_scooters', 
      'scooty': 'bikes_scooters',
      'motor bike': 'bikes_scooters',
      'motor-bike': 'bikes_scooters',
      'electric': 'electric_bikes',
      'ev': 'electric_bikes',
      'e-bike': 'electric_bikes',
      'electric bike': 'electric_bikes',
      'electric scooter': 'electric_bikes',
      'car': 'cars',
      'van': 'cars',
      'truck': 'cars'
    };
    
    return categoryMap[type] || type;
  };

  const getVehicleTypeColor = (vehicleType) => {
    if (!vehicleType) return '#F4F4F8';

    const colors = {
      // New standardized categories
      'cycles': '#4CAF50',                    // Green for eco-friendly cycles
      'electric_bikes': '#2196F3',           // Blue for electric vehicles  
      'bikes_scooters': '#FF9800',           // Orange for bikes/scooters
      'cars': '#9C27B0',                     // Purple for cars
      
      // Legacy mappings for backward compatibility
      motorcycle: '#FF9800',
      scooter: '#FF9800', 
      bicycle: '#4CAF50',
      car: '#9C27B0',
      bike: '#4CAF50',
      'motor bike': '#FF9800',
      'motor-bike': '#FF9800',
      'scooty': '#FF9800',
      'cycle': '#4CAF50',
      'electric': '#2196F3',
      'ev': '#2196F3'
    };

    const type = String(vehicleType).toLowerCase().trim();
    return colors[type] || '#F4F4F8';
  };

  const getStatusColor = (status) => {
    if (!status) return { color: '#2A2C41', bg: 'rgba(42, 44, 65, 0.1)' };

    const statusStr = String(status).toLowerCase().trim();

    if (['approved', 'active', 'approve', 'completed'].includes(statusStr)) {
      return {
        color: '#28a745',
        bg: 'rgba(40, 167, 69, 0.1)',
        text: 'Approved'
      };
    }

    if (['rejected', 'declined', 'reject', 'inactive'].includes(statusStr)) {
      return {
        color: '#dc3545',
        bg: 'rgba(220, 53, 69, 0.1)',
        text: 'Rejected'
      };
    }

    // Default for pending/under review status
    return {
      color: '#ffc107',
      bg: 'rgba(255, 193, 7, 0.1)',
      text: 'Pending Review'
    };
  };

  const columns = [
    {
      title: 'Partner Name',
      dataIndex: 'fullName',
      key: 'fullName',
      render: (text, record) => (
        <div>
          <div style={{ fontWeight: '600', color: '#2A2C41', fontSize: '15px' }}>
            {text} {record.lastName}
          </div>
          <div style={{ fontSize: '13px', color: '#2A2C41' }}>
            {record.mobileNumber}
          </div>
        </div>
      ),
    },
    {
      title: 'Vehicle Type',
      dataIndex: 'vehicleType',
      key: 'vehicleType',
      render: (vehicleType) => (
        <Tag
          color={getVehicleTypeColor(vehicleType)}
          style={{
            borderRadius: '6px',
            fontWeight: '500',
            fontSize: '12px'
          }}
        >
          {vehicleType}
        </Tag>
      ),
    },
    {
      title: 'Service Area',
      dataIndex: 'deliveryServiceArea',
      key: 'deliveryServiceArea',
      render: (area, record) => (
        <div style={{ display: 'flex', alignItems: 'center', gap: '6px', minWidth: 0 }}>
          <FiMapPin style={{ color: '#2A2C41', fontSize: '12px', flex: '0 0 auto' }} />
          <span style={{
            fontSize: '13px',
            color: '#2A2C41',
            overflow: 'hidden',
            textOverflow: 'ellipsis',
            whiteSpace: 'nowrap',
            display: 'inline-block',
            maxWidth: '220px'
          }}>{area}, {record.city}</span>
        </div>
      ),
    },
    {
      title: 'License Number',
      dataIndex: 'licenseNumber',
      key: 'licenseNumber',
      render: (license) => (
        <span style={{ fontSize: '13px', color: '#2A2C41', fontFamily: 'monospace' }}>
          {license}
        </span>
      ),
    },
    {
      title: 'Submission Date',
      dataIndex: 'submissionDate',
      key: 'submissionDate',
      render: (date) => (
        <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
          <FiCalendar style={{ color: '#2A2C41', fontSize: '12px' }} />
          <span style={{ fontSize: '13px', color: '#2A2C41' }}>
            {dayjs(date).format('MMM DD, YYYY')}
          </span>
        </div>
      ),
    },
    {
      title: 'Status',
      dataIndex: 'status',
      key: 'status',
      render: (status) => {
        const statusStyle = getStatusColor(status);
        let badgeStatus = 'processing';
        if (status === 'Approved') badgeStatus = 'success';
        else if (status === 'Rejected') badgeStatus = 'error';

        return (
          <div style={{
            padding: '4px 8px',
            borderRadius: '6px',
            backgroundColor: statusStyle.bg,
            display: 'inline-flex',
            alignItems: 'center',
            gap: '6px'
          }}>
            <Badge status={badgeStatus} />
            <span style={{
              color: statusStyle.color,
              fontWeight: '500',
              fontSize: '13px'
            }}>
              {status}
            </span>
          </div>
        );
      },
    },
    {
      title: 'Actions',
      key: 'actions',
      render: (_, record) => (
        <Space size="small">
          <Tooltip title="View Details">
            <Button
              type="text"
              icon={<FiEye />}
              onClick={() => viewPartnerDetails(record)}
              style={{
                color: '#2A2C41',
                borderRadius: '8px',
                padding: '4px 8px',
                height: '32px'
              }}
            >
              View
            </Button>
          </Tooltip>
        </Space>
      ),
    },
  ];

  const rowSelection = {
    selectedRowKeys,
    onChange: (keys) => setSelectedRowKeys(keys),
  };

  return (
    <div style={{ backgroundColor: '#F4F4F8' }}>
      <div>
        {/* Header */}
        <div style={{ marginBottom: '24px' }}>
          <div style={{
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'center',
            gap: '20px',
            marginBottom: '8px'
          }}>
            <div>
              <h1 style={{
                fontSize: '30px',
                fontWeight: '700',
                color: '#2A2C41',
                margin: '0',
                letterSpacing: '-0.025em'
              }}>
                Delivery Partner KYC Verification
              </h1>

            </div>

            {/* View Toggle Buttons */}
            <div style={{
              display: 'flex',
              alignItems: 'center',
              gap: '8px',
              background: 'white',
              padding: '4px',
              borderRadius: '8px',
              boxShadow: '0 2px 8px rgba(0,0,0,0.1)',
              border: '1px solid #e0e0e0'
            }}>
              <button
                onClick={() => setViewMode('list')}
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: '6px',
                  background: viewMode === 'list' ? '#F55D00' : 'transparent',
                  color: viewMode === 'list' ? 'white' : '#2A2C41',
                  border: 'none',
                  padding: '8px 16px',
                  borderRadius: '6px',
                  cursor: 'pointer',
                  fontSize: '14px',
                  fontWeight: '500',
                  transition: 'all 0.2s ease'
                }}
                onMouseEnter={(e) => {
                  if (viewMode !== 'list') {
                    e.currentTarget.style.background = 'rgba(245, 93, 0, 0.1)';
                  }
                }}
                onMouseLeave={(e) => {
                  if (viewMode !== 'list') {
                    e.currentTarget.style.background = 'transparent';
                  }
                }}
              >
                <FiList style={{ fontSize: '16px' }} />
                List View
              </button>
              <button
                onClick={() => setViewMode('grid')}
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: '6px',
                  background: viewMode === 'grid' ? '#F55D00' : 'transparent',
                  color: viewMode === 'grid' ? 'white' : '#2A2C41',
                  border: 'none',
                  padding: '8px 16px',
                  borderRadius: '6px',
                  cursor: 'pointer',
                  fontSize: '14px',
                  fontWeight: '500',
                  transition: 'all 0.2s ease'
                }}
                onMouseEnter={(e) => {
                  if (viewMode !== 'grid') {
                    e.currentTarget.style.background = 'rgba(245, 93, 0, 0.1)';
                  }
                }}
                onMouseLeave={(e) => {
                  if (viewMode !== 'grid') {
                    e.currentTarget.style.background = 'transparent';
                  }
                }}
              >
                <FiGrid style={{ fontSize: '16px' }} />
                Grid View
              </button>
            </div>
          </div>
        </div>

        {/* Statistics Cards */}
        <Row gutter={[16, 16]} style={{ marginBottom: '20px' }}>
          <Col xs={24} sm={12} md={6}>
            <Card style={{
              borderRadius: '12px',
              border: '1px solid #2A2C41',
              boxShadow: '0 4px 12px rgba(42, 44, 65, 0.1)',
              padding: '8px'
            }}>
              <Statistic
                title={<span style={{ color: '#2A2C41', fontSize: '13px' }}>Total Partners</span>}
                value={filteredPartners.length}
                valueStyle={{ color: '#2A2C41', fontSize: '20px', fontWeight: '700' }}
              />
            </Card>
          </Col>
          <Col xs={24} sm={12} md={6}>
            <Card style={{
              borderRadius: '12px',
              border: '1px solid #FDBF50',
              boxShadow: '0 4px 12px rgba(253, 191, 80, 0.1)',
              padding: '8px'
            }}>
              <Statistic
                title={<span style={{ color: '#2A2C41', fontSize: '13px' }}>Approved</span>}
                value={filteredPartners.filter(p => p.status === 'Approved').length}
                valueStyle={{ color: '#FDBF50', fontSize: '20px', fontWeight: '700' }}
              />
            </Card>
          </Col>
          <Col xs={24} sm={12} md={6}>
            <Card style={{
              borderRadius: '12px',
              border: '1px solid #F55D00',
              boxShadow: '0 4px 12px rgba(245, 93, 0, 0.1)',
              padding: '8px'
            }}>
              <Statistic
                title={<span style={{ color: '#2A2C41', fontSize: '13px' }}>Pending</span>}
                value={filteredPartners.filter(p => p.status === 'Pending Review').length}
                valueStyle={{ color: '#F55D00', fontSize: '20px', fontWeight: '700' }}
              />
            </Card>
          </Col>
          <Col xs={24} sm={12} md={6}>
            <Card style={{
              borderRadius: '12px',
              border: '1px solid #dc3545',
              boxShadow: '0 4px 12px rgba(220, 53, 69, 0.1)',
              padding: '8px'
            }}>
              <Statistic
                title={<span style={{ color: '#2A2C41', fontSize: '13px' }}>Rejected</span>}
                value={filteredPartners.filter(p => p.status === 'Rejected').length}
                valueStyle={{ color: '#dc3545', fontSize: '20px', fontWeight: '700' }}
              />
            </Card>
          </Col>
        </Row>

        {/* Recent Approved Partners */}
        {recentApprovedPartners.length > 0 && (
          <Card
            style={{
              borderRadius: '12px',
              marginBottom: '20px',
              border: '1px solid #28a745',
              boxShadow: '0 4px 12px rgba(40, 167, 69, 0.1)'
            }}
            title={
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                <FiCheckCircle style={{ color: '#28a745', fontSize: '18px' }} />
                <span style={{ color: '#28a745', fontWeight: '600' }}>
                  Recent Approved Partners ({recentApprovedPartners.length})
                </span>
              </div>
            }
            extra={
              <span style={{ fontSize: '12px', color: '#666' }}>
                Last 7 days
              </span>
            }
          >
            <Row gutter={[16, 12]}>
              {recentApprovedPartners.map((partner) => (
                <Col xs={24} sm={12} md={8} lg={6} key={partner.id}>
                  <Card
                    size="small"
                    style={{
                      borderRadius: '8px',
                      border: '1px solid #e8f5e8',
                      backgroundColor: '#f8fff8',
                      cursor: 'pointer',
                      transition: 'all 0.2s ease'
                    }}
                    hoverable
                    onClick={() => {
                      setSelectedPartner(partner);
                      setDetailModalVisible(true);
                    }}
                  >
                    <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '8px' }}>
                      <div style={{
                        width: '32px',
                        height: '32px',
                        borderRadius: '50%',
                        backgroundColor: '#28a745',
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'center',
                        color: 'white',
                        fontSize: '12px',
                        fontWeight: '600'
                      }}>
                        {partner.name ? partner.name.charAt(0).toUpperCase() : 'D'}
                      </div>
                      <div style={{ flex: 1, minWidth: 0 }}>
                        <div style={{
                          fontSize: '13px',
                          fontWeight: '600',
                          color: '#2A2C41',
                          whiteSpace: 'nowrap',
                          overflow: 'hidden',
                          textOverflow: 'ellipsis'
                        }}>
                          {partner.fullName || partner.full_name || 'Delivery Partner'}
                        </div>
                        <div style={{
                          fontSize: '11px',
                          color: '#666',
                          whiteSpace: 'nowrap',
                          overflow: 'hidden',
                          textOverflow: 'ellipsis'
                        }}>
                          {partner.userId || partner.user_id || partner.id || 'N/A'}
                        </div>
                      </div>
                    </div>

                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                      <div>
                        <Tag
                          color="success"
                          style={{ fontSize: '10px', margin: 0 }}
                        >
                          <FiCheckCircle style={{ fontSize: '10px', marginRight: '2px' }} />
                          Approved
                        </Tag>
                      </div>
                      <div style={{ fontSize: '10px', color: '#666' }}>
                        {partner.vehicleType && (
                          <span style={{
                            backgroundColor: '#e8f5e8',
                            padding: '2px 6px',
                            borderRadius: '4px',
                            textTransform: 'capitalize'
                          }}>
                            {partner.vehicleType}
                          </span>
                        )}
                      </div>
                    </div>

                    {partner.approvalDate && (
                      <div style={{
                        fontSize: '10px',
                        color: '#999',
                        marginTop: '4px',
                        fontStyle: 'italic'
                      }}>
                        Approved: {dayjs(partner.approvalDate).format('MMM DD, YYYY')}
                      </div>
                    )}
                  </Card>
                </Col>
              ))}
            </Row>
          </Card>
        )}

        {/* Filters */}
        <Card style={{
          borderRadius: '12px',
          marginBottom: '16px',
          border: '1px solid rgba(42, 44, 65, 0.08)',
          boxShadow: '0 2px 8px rgba(42, 44, 65, 0.04)'
        }}>
          <Row gutter={[12, 8]} align="middle">
            <Col xs={24} sm={12} md={4} lg={4}>
              <div style={{ marginBottom: '4px' }}>
                <span style={{ fontSize: '12px', fontWeight: '500', color: '#2A2C41' }}>
                  Search
                </span>
              </div>
              <Input
                placeholder="Search partners..."
                prefix={<FiSearch style={{ color: '#2A2C41' }} />}
                value={filters.searchText}
                onChange={(e) => handleFilterChange('searchText', e.target.value)}
                style={{
                  width: '100%',
                  borderRadius: '6px',
                  borderColor: 'rgba(42, 44, 65, 0.2)',
                  height: '32px'
                }}
              />
            </Col>
            <Col xs={24} sm={12} md={4} lg={4}>
              <div style={{ marginBottom: '4px' }}>
                <span style={{ fontSize: '12px', fontWeight: '500', color: '#2A2C41' }}>
                  Vehicle Type
                </span>
              </div>
              <Select
                placeholder="All Vehicles"
                value={filters.vehicleType}
                onChange={(value) => handleFilterChange('vehicleType', value)}
                style={{
                  width: '100%',
                  borderRadius: '6px',
                  height: '32px'
                }}
              >
                <Option value="all">All Vehicles</Option>
                <Option value="cycles">Cycles (Bicycle)</Option>
                <Option value="electric_bikes">Electric Bikes/Scooters (E-Bikes)</Option>
                <Option value="bikes_scooters">Bikes/Scooters</Option>
                <Option value="cars">Cars</Option>
              </Select>
            </Col>
            <Col xs={24} sm={12} md={4} lg={4}>
              <div style={{ marginBottom: '4px' }}>
                <span style={{ fontSize: '12px', fontWeight: '500', color: '#2A2C41' }}>
                  Status
                </span>
              </div>
              <Select
                value={filters.status}
                onChange={(value) => handleFilterChange('status', value)}
                style={{
                  width: '100%',
                  borderRadius: '6px',
                  height: '32px'
                }}
              >
                <Option value="all">All Status</Option>
                <Option value="pending">Pending</Option>
                <Option value="approved">Approved</Option>
                <Option value="rejected">Rejected</Option>
              </Select>
            </Col>
            <Col xs={24} sm={12} md={4} lg={4}>
              <div style={{ marginBottom: '4px' }}>
                <span style={{ fontSize: '12px', fontWeight: '500', color: '#2A2C41' }}>
                  Location
                </span>
              </div>
              <Input
                placeholder="Enter location"
                value={filters.location}
                onChange={(e) => handleFilterChange('location', e.target.value)}
                style={{
                  width: '100%',
                  borderRadius: '6px',
                  borderColor: 'rgba(42, 44, 65, 0.2)',
                  height: '32px'
                }}
              />
            </Col>
            <Col xs={24} sm={12} md={4} lg={4}>
              <div style={{ marginBottom: '4px' }}>
                <span style={{ fontSize: '12px', fontWeight: '500', color: '#2A2C41' }}>
                  Date Range
                </span>
              </div>
              <RangePicker
                value={filters.dateRange}
                onChange={(dates) => handleFilterChange('dateRange', dates)}
                style={{
                  width: '100%',
                  borderRadius: '6px',
                  borderColor: 'rgba(42, 44, 65, 0.2)'
                }}
                placeholder={['Start date', 'End date']}
              />
            </Col>
            <Col xs={24} sm={24} md={4} lg={4} style={{ display: 'flex', justifyContent: 'flex-end', gap: '8px', alignItems: 'end' }}>
              <Button
                onClick={clearFilters}
                style={{
                  borderRadius: '6px',
                  backgroundColor: '#6c757d',
                  borderColor: '#6c757d',
                  color: '#ffffff',
                  fontSize: '11px',
                  height: '32px',
                  padding: '0 12px'
                }}
                size="small"
              >
                Clear Filters
              </Button>
              <Button
                icon={<FiRefreshCw />}
                onClick={() => {
                  setFilters({
                    status: 'all',
                    vehicleType: 'all',
                    location: '',
                    dateRange: null,
                    searchText: ''
                  });
                  setPagination((prev) => ({ ...prev, current: 1 }));
                  loadUnverifiedPartners();
                }}
                style={{
                  borderRadius: '6px',
                  backgroundColor: '#F55D00',
                  borderColor: '#F55D00',
                  color: '#ffffff',
                  fontSize: '11px',
                  height: '32px',
                  padding: '0 12px'
                }}
                size="small"
              >
                Refresh
              </Button>
            </Col>
          </Row>
        </Card>

        {/* Partner Table/Grid View */}
        {viewMode === 'list' ? (
          <Card style={{
            borderRadius: '12px',
            border: '1px solid rgba(42, 44, 65, 0.08)',
            boxShadow: '0 2px 8px rgba(42, 44, 65, 0.04)'
          }}>
            {/* Bulk Actions */}
            {selectedRowKeys.length > 0 && (
              <div style={{
                padding: '16px',
                backgroundColor: 'rgba(42, 44, 65, 0.05)',
                borderBottom: '1px solid rgba(42, 44, 65, 0.08)',
                display: 'flex',
                justifyContent: 'space-between',
                alignItems: 'center'
              }}>
                <span style={{
                  fontSize: '14px',
                  fontWeight: '600',
                  color: '#2A2C41'
                }}>
                  {selectedRowKeys.length} partner{selectedRowKeys.length > 1 ? 's' : ''} selected
                </span>
                <Space>
                  <Button
                    icon={<FiCheckCircle />}
                    onClick={() => handleBulkAction('approve')}
                    loading={bulkActionLoading}
                    style={{
                      backgroundColor: '#FDBF50',
                      borderColor: '#FDBF50',
                      color: '#ffffff',
                      borderRadius: '8px',
                      fontWeight: '500'
                    }}
                  >
                    Bulk Approve
                  </Button>
                  <Button
                    icon={<FiXCircle />}
                    onClick={() => handleBulkAction('reject')}
                    loading={bulkActionLoading}
                    style={{
                      backgroundColor: '#F55D00',
                      borderColor: '#F55D00',
                      color: '#ffffff',
                      borderRadius: '8px',
                      fontWeight: '500'
                    }}
                  >
                    Bulk Reject
                  </Button>
                  <Button
                    onClick={() => setSelectedRowKeys([])}
                    style={{
                      borderRadius: '8px',
                      borderColor: '#2A2C41',
                      color: '#2A2C41'
                    }}
                  >
                    Clear Selection
                  </Button>
                </Space>
              </div>
            )}

            {error ? (
              <div style={{
                padding: '40px 20px',
                textAlign: 'center',
                backgroundColor: '#fff',
                borderRadius: '12px',
                border: '1px dashed #ff4d4f',
                margin: '20px 0'
              }}>
                <FiAlertCircle style={{ fontSize: '48px', color: '#ff4d4f', marginBottom: '16px' }} />
                <h3 style={{ color: '#2A2C41', marginBottom: '8px' }}>Error Loading Data</h3>
                <p style={{ color: '#666', marginBottom: '24px' }}>{error}</p>
                <Button
                  type="primary"
                  onClick={loadUnverifiedPartners}
                  loading={loading}
                  style={{
                    backgroundColor: '#F55D00',
                    borderColor: '#F55D00',
                    borderRadius: '8px',
                    padding: '8px 24px',
                    height: 'auto'
                  }}
                >
                  Retry
                </Button>
              </div>
            ) : (
              <Table
                columns={columns}
                dataSource={filteredPartners}
                rowKey="id"
                loading={loading}
                rowSelection={rowSelection}
                pagination={{
                  current: pagination.current,
                  pageSize: pagination.pageSize,
                  total: pagination.total,
                  showSizeChanger: true,
                  showQuickJumper: true,
                  showTotal: (total, range) => `${range[0]}-${range[1]} of ${total} partners`
                }}
                onChange={(pg) => handleTableChange(pg)}
                style={{
                  borderRadius: '12px'
                }}
                scroll={{ x: 1000 }}
                locale={{
                  emptyText: (
                    <div style={{ padding: '40px 0' }}>
                      <FiUser style={{ fontSize: '48px', color: '#d9d9d9', marginBottom: '16px' }} />
                      <p style={{ color: '#666' }}>No delivery partners found</p>
                    </div>
                  )
                }}
              />
            )}
          </Card>
        ) : (
          /* Grid View */
          <div>
            {loading ? (
              <div style={{ textAlign: 'center', padding: '40px' }}>
                <span>Loading...</span>
              </div>
            ) : error ? (
              <div style={{
                padding: '40px 20px',
                textAlign: 'center',
                backgroundColor: '#fff',
                borderRadius: '12px',
                border: '1px dashed #ff4d4f',
                margin: '20px 0'
              }}>
                <FiAlertCircle style={{ fontSize: '48px', color: '#ff4d4f', marginBottom: '16px' }} />
                <h3 style={{ color: '#2A2C41', marginBottom: '8px' }}>Error Loading Data</h3>
                <p style={{ color: '#666', marginBottom: '24px' }}>{error}</p>
                <Button
                  type="primary"
                  onClick={loadUnverifiedPartners}
                  loading={loading}
                  style={{
                    backgroundColor: '#F55D00',
                    borderColor: '#F55D00',
                    borderRadius: '8px',
                    padding: '8px 24px',
                    height: 'auto'
                  }}
                >
                  Retry
                </Button>
              </div>
            ) : (
              <Row gutter={[16, 16]}>
                {filteredPartners.map((partner) => {
                  let badgeStatus = 'processing';
                  let textColor = '#2A2C41';
                  let backgroundColor = 'rgba(42, 44, 65, 0.1)';

                  if (partner.status === 'Approved') {
                    badgeStatus = 'success';
                    textColor = '#FDBF50';
                    backgroundColor = 'rgba(253, 191, 80, 0.1)';
                  } else if (partner.status === 'Rejected') {
                    badgeStatus = 'error';
                    textColor = '#F55D00';
                    backgroundColor = 'rgba(245, 93, 0, 0.1)';
                  }

                  return (
                    <Col xs={24} sm={12} md={12} lg={6} xl={6} key={partner.id}>
                      <Card
                        style={{
                          borderRadius: '12px',
                          border: '1px solid rgba(42, 44, 65, 0.08)',
                          boxShadow: '0 2px 8px rgba(42, 44, 65, 0.04)',
                          height: '100%',
                          display: 'flex',
                          flexDirection: 'column',
                          transition: 'all 0.3s ease'
                        }}
                        bodyStyle={{ padding: '16px', flex: 1, display: 'flex', flexDirection: 'column' }}
                        hoverable
                      >
                        {/* Header: Partner Name & Status */}
                        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '12px' }}>
                          <div style={{ flex: 1, minWidth: 0 }}>
                            <div style={{ fontWeight: '700', color: '#2A2C41', fontSize: '16px', marginBottom: '4px', lineHeight: '1.3' }}>
                              {partner.fullName}
                            </div>
                            <div style={{ fontSize: '12px', color: '#6c757d', display: 'flex', alignItems: 'center', gap: '4px' }}>
                              <FiPhone style={{ fontSize: '11px' }} />
                              {partner.mobileNumber}
                            </div>
                          </div>
                          {/* Status Badge - Top Right */}
                          <div style={{
                            padding: '4px 8px',
                            borderRadius: '6px',
                            backgroundColor: backgroundColor,
                            display: 'flex',
                            alignItems: 'center',
                            gap: '4px',
                            marginLeft: '8px',
                            flexShrink: 0
                          }}>
                            <Badge status={badgeStatus} />
                            <span style={{
                              color: textColor,
                              fontWeight: '600',
                              fontSize: '11px',
                              whiteSpace: 'nowrap'
                            }}>
                              {partner.status}
                            </span>
                          </div>
                        </div>

                        {/* Info Section */}
                        <div style={{ flex: 1, marginBottom: '12px' }}>
                          {/* Vehicle Type & Number */}
                          <div style={{ marginBottom: '8px' }}>
                            <Tag
                              color="#2A2C41"
                              style={{
                                borderRadius: '6px',
                                fontWeight: '500',
                                fontSize: '11px',
                                padding: '2px 10px',
                                marginBottom: '6px',
                                margin: 0
                              }}
                            >
                              <FiTruck style={{ fontSize: '11px', marginRight: '4px' }} />
                              {partner.vehicleType}
                            </Tag>
                            <div style={{
                              fontSize: '12px',
                              color: '#2A2C41',
                              fontWeight: '600',
                              backgroundColor: 'rgba(42, 44, 65, 0.05)',
                              padding: '4px 8px',
                              borderRadius: '6px',
                              display: 'inline-block',
                              marginTop: '6px'
                            }}>
                              {partner.vehicleNumber}
                            </div>
                          </div>

                          {/* Location */}
                          <div style={{ display: 'flex', alignItems: 'center', gap: '6px', marginBottom: '6px' }}>
                            <FiMapPin style={{ color: '#6c757d', fontSize: '12px', flex: '0 0 auto' }} />
                            <span style={{
                              fontSize: '12px',
                              color: '#2A2C41',
                              overflow: 'hidden',
                              textOverflow: 'ellipsis',
                              whiteSpace: 'nowrap'
                            }}>
                              {partner.city}
                            </span>
                          </div>

                          {/* Submission Date */}
                          <div style={{ display: 'flex', alignItems: 'center', gap: '6px', marginBottom: '8px' }}>
                            <FiCalendar style={{ color: '#6c757d', fontSize: '12px' }} />
                            <span style={{ fontSize: '12px', color: '#2A2C41' }}>
                              {dayjs(partner.submissionDate).format('MMM DD, YYYY')}
                            </span>
                          </div>
                        </div>

                        {/* Actions */}
                        <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap', marginTop: 'auto' }}>
                          <Button
                            icon={<FiEye />}
                            onClick={() => viewPartnerDetails(partner)}
                            style={{
                              color: '#2A2C41',
                              backgroundColor: '#ffffff',
                              borderColor: '#2A2C41',
                              border: '1.5px solid #2A2C41',
                              borderRadius: '6px',
                              fontWeight: '500',
                              padding: '4px 8px',
                              height: '28px',
                              fontSize: '11px',
                              flex: 1,
                              display: 'flex',
                              alignItems: 'center',
                              justifyContent: 'center',
                              gap: '4px'
                            }}
                            onMouseEnter={(e) => {
                              e.currentTarget.style.backgroundColor = '#2A2C41';
                              e.currentTarget.style.color = '#ffffff';
                            }}
                            onMouseLeave={(e) => {
                              e.currentTarget.style.backgroundColor = '#ffffff';
                              e.currentTarget.style.color = '#2A2C41';
                            }}
                          >
                            View
                          </Button>
                          {partner.status === 'Pending Review' && (
                            <>
                              <Button
                                size="small"
                                icon={<FiCheckCircle />}
                                onClick={() => handlePartnerAction(partner.id, 'approve')}
                                style={{
                                  color: '#ffffff',
                                  backgroundColor: '#FDBF50',
                                  borderColor: '#FDBF50',
                                  borderRadius: '6px',
                                  fontWeight: '500',
                                  height: '28px',
                                  padding: '4px 8px',
                                  fontSize: '11px',
                                  flex: 1
                                }}
                              >
                                Approve
                              </Button>
                              <Button
                                size="small"
                                icon={<FiXCircle />}
                                onClick={() => handlePartnerAction(partner.id, 'reject')}
                                style={{
                                  color: '#ffffff',
                                  backgroundColor: '#F55D00',
                                  borderColor: '#F55D00',
                                  borderRadius: '6px',
                                  fontWeight: '500',
                                  height: '28px',
                                  padding: '4px 8px',
                                  fontSize: '11px',
                                  flex: 1
                                }}
                              >
                                Reject
                              </Button>
                            </>
                          )}
                          {partner.status === 'Rejected' && (
                            <Button
                              size="small"
                              icon={<FiCheckCircle />}
                              onClick={() => handlePartnerAction(partner.id, 'approve')}
                              style={{
                                color: '#ffffff',
                                backgroundColor: '#FDBF50',
                                borderColor: '#FDBF50',
                                borderRadius: '6px',
                                fontWeight: '500',
                                height: '28px',
                                padding: '4px 8px',
                                fontSize: '11px',
                                flex: 1
                              }}
                            >
                              Approve
                            </Button>
                          )}
                        </div>
                      </Card>
                    </Col>
                  );
                })}
              </Row>
            )}
          </div>
        )}

        {/* Partner Detail Modal */}
        <Modal
          title={null}
          open={detailModalVisible}
          onCancel={() => setDetailModalVisible(false)}
          footer={null}
          width={750}
          centered
          className="partner-modal"
          closeIcon={<div className="partner-modal-close">×</div>}
        >
          {selectedPartner && (
            <div className="partner-modal-container">
              {/* Modal Header */}
              <div className="partner-modal-header">
                <div className="partner-modal-header-content">
                  <div>
                    <h2 className="partner-modal-title">
                      {selectedPartner.fullName} {selectedPartner.lastName}
                    </h2>
                    <p className="partner-modal-subtitle">
                      License: {selectedPartner.licenseNumber}
                    </p>
                  </div>

                  <div style={{ textAlign: 'right' }}>
                    <div className="partner-modal-badge">
                      {selectedPartner.vehicleType}
                    </div>
                    <div className="partner-modal-vehicle-number">
                      {selectedPartner.vehicleNumber !== 'N/A' ? selectedPartner.vehicleNumber : 'No Vehicle Number'}
                    </div>
                  </div>
                </div>
              </div>

              {/* Modal Content */}
              <div className="partner-modal-body">
                {/* Personal Information */}
                <Row gutter={[8, 8]} style={{ marginBottom: '8px' }}>
                  <Col xs={24} md={12}>
                    <div className="partner-info-section">
                      <h4 className="partner-info-section-header">
                        <FiUser className="partner-info-section-icon" />
                        Personal Information
                      </h4>
                      <div className="partner-info-field">
                        <div className="partner-info-label">Full Name:</div>
                        <div className="partner-info-value">{selectedPartner.fullName} {selectedPartner.lastName}</div>
                      </div>
                      <div className="partner-info-field">
                        <div className="partner-info-label">Mobile Number:</div>
                        <div className="partner-info-value">{selectedPartner.mobileNumber}</div>
                      </div>
                      <div className="partner-info-field">
                        <div className="partner-info-label">License Number:</div>
                        <div className="partner-info-value monospace">{selectedPartner.licenseNumber}</div>
                      </div>
                      <div className="partner-info-field">
                        <div className="partner-info-label">Status:</div>
                        <div className={`partner-status-tag ${selectedPartner.status === 'Approved' ? 'approved' : selectedPartner.status === 'Rejected' ? 'rejected' : 'pending'}`}>
                          {selectedPartner.status}
                        </div>
                      </div>
                    </div>
                  </Col>

                  {/* Vehicle Information */}
                  <Col xs={24} md={12}>
                    <div className="partner-info-section">
                      <h4 className="partner-info-section-header">
                        <FiTruck className="partner-info-section-icon" />
                        Vehicle Information
                      </h4>
                      <div className="partner-info-field">
                        <div className="partner-info-label">Vehicle Type:</div>
                        <div className="partner-vehicle-tag">
                          {selectedPartner.vehicleType}
                        </div>
                      </div>
                      <div className="partner-info-field">
                        <div className="partner-info-label">Vehicle Number:</div>
                        <div className="partner-info-value monospace">
                          {selectedPartner.vehicleNumber !== 'N/A' ? selectedPartner.vehicleNumber : 'Not Applicable'}
                        </div>
                      </div>
                      <div className="partner-info-field">
                        <div className="partner-info-label">Service Area:</div>
                        <div className="partner-info-value">{selectedPartner.deliveryServiceArea}, {selectedPartner.city}</div>
                      </div>
                    </div>
                  </Col>
                </Row>

                {/* Address Information */}
                <Row gutter={[8, 8]} style={{ marginBottom: '8px' }}>
                  <Col xs={24}>
                    <div className="partner-info-section">
                      <h4 className="partner-info-section-header">
                        <FiMapPin className="partner-info-section-icon" />
                        Address Information
                      </h4>
                      <Row gutter={[12, 8]}>
                        <Col xs={24} md={12}>
                          <div className="partner-info-field">
                            <div className="partner-info-label">Full Address:</div>
                            <div className="partner-info-value">{selectedPartner.fullAddress}</div>
                          </div>
                          <div className="partner-info-field">
                            <div className="partner-info-label">City:</div>
                            <div className="partner-info-value">{selectedPartner.city}</div>
                          </div>
                          <div className="partner-info-field">
                            <div className="partner-info-label">Pincode:</div>
                            <div className="partner-info-value">{selectedPartner.pincode}</div>
                          </div>
                        </Col>
                        <Col xs={24} md={12}>
                          <div className="partner-info-field">
                            <div className="partner-info-label">Current Address:</div>
                            <div className="partner-info-value">{selectedPartner.currentAddress}</div>
                          </div>
                          <div className="partner-info-field">
                            <div className="partner-info-label">State:</div>
                            <div className="partner-info-value">{selectedPartner.state}</div>
                          </div>
                          <div className="partner-info-field">
                            <div className="partner-info-label">Service Area:</div>
                            <div className="partner-info-value">{selectedPartner.deliveryServiceArea}</div>
                          </div>
                        </Col>
                      </Row>
                    </div>
                  </Col>
                </Row>

                {/* Financial Information */}
                <Row gutter={[8, 8]} style={{ marginBottom: '8px' }}>
                  <Col xs={24}>
                    <div className="partner-info-section">
                      <h4 className="partner-info-section-header">
                        <FiClipboard className="partner-info-section-icon" />
                        Financial Information
                      </h4>
                      <Row gutter={[12, 8]}>
                        <Col xs={24} md={8}>
                          <div className="partner-info-field">
                            <div className="partner-info-label">Bank Account:</div>
                            <div className="partner-info-value monospace">{selectedPartner.bankAccountNumber}</div>
                          </div>
                        </Col>
                        <Col xs={24} md={8}>
                          <div className="partner-info-field">
                            <div className="partner-info-label">IFSC Code:</div>
                            <div className="partner-info-value monospace">{selectedPartner.ifscCode}</div>
                          </div>
                        </Col>
                        <Col xs={24} md={8}>
                          <div className="partner-info-field">
                            <div className="partner-info-label">PAN Number:</div>
                            <div className="partner-info-value monospace">{selectedPartner.panNumber}</div>
                          </div>
                        </Col>
                      </Row>
                    </div>
                  </Col>
                </Row>

                {/* Documents */}
                <Row gutter={[8, 8]}>
                  <Col xs={24}>
                    <div className="partner-documents-section">
                      <h4 className="partner-documents-header">
                        <FiFileText className="partner-info-section-icon" />
                        Documents
                      </h4>
                      <div className="partner-documents-grid">
                        {selectedPartner.documents.map((doc, index) => (
                          <div
                            key={index}
                            onClick={() => openDocument(doc)}
                            className="partner-document-card"
                          >
                            <div className="partner-document-icon">
                              <FiFile />
                            </div>
                            <div className="partner-document-title">
                              {doc.type}
                            </div>
                            <div className="partner-document-name">
                              {doc.name}
                            </div>
                            <div className="partner-document-footer">
                              <div className={`partner-document-status ${doc.isVerified ? 'verified' : 'pending'}`}>
                                {doc.isVerified ? 'Verified' : 'Pending'}
                              </div>
                              <button
                                onClick={(e) => { e.stopPropagation(); toggleDocumentVerification(doc); }}
                                className={`partner-document-btn ${doc.isVerified ? 'unverify' : 'verify'}`}
                              >
                                {doc.isVerified ? 'Unverify' : 'Verify'}
                              </button>
                            </div>
                          </div>
                        ))}
                      </div>
                    </div>
                  </Col>
                </Row>

                {/* KYC Verification Summary and Approve */}
                {selectedPartner?.verificationSummary && (
                  <div className="partner-kyc-section">
                    <h4 className="partner-kyc-header">
                      <FiSettings className="partner-info-section-icon" />
                      KYC Verification Summary
                    </h4>
                    {(() => {
                      const vs = selectedPartner.verificationSummary || {};
                      const required = vs.required_doc_types || [];
                      const present = vs.present_doc_types || [];
                      const verified = vs.verified_doc_types || [];
                      const missing = required.filter((r) => !present.includes(r));
                      const notVerified = required.filter((r) => !verified.includes(r));
                      const canApprove = !!(vs.all_documents_present && vs.all_documents_verified);
                      return (
                        <div>
                          <div className="partner-kyc-tags">
                            <div className={`partner-kyc-tag ${vs.all_documents_present ? 'success' : 'warning'}`}>
                              Required: {required.length}
                            </div>
                            <div className={`partner-kyc-tag ${vs.all_documents_present ? 'success' : 'warning'}`}>
                              Present: {present.length}
                            </div>
                            <div className={`partner-kyc-tag ${vs.all_documents_verified ? 'success' : 'warning'}`}>
                              Verified: {verified.length}
                            </div>
                          </div>
                          {(!canApprove) && (
                            <div style={{ color: '#8c8c8c', fontSize: 12, marginBottom: 8 }}>
                              {missing.length > 0 && (<div>Missing: {missing.join(', ')}</div>)}
                              {notVerified.length > 0 && (<div>Unverified: {notVerified.join(', ')}</div>)}
                            </div>
                          )}
                          <div className="partner-kyc-actions">
                            <Button onClick={() => setDetailModalVisible(false)} className="partner-kyc-btn secondary">Close</Button>
                            <Button
                              icon={<FiXCircle />}
                              onClick={() => openDecision(selectedPartner, 'reject')}
                              className="partner-kyc-btn danger"
                            >
                              Decline
                            </Button>
                            <Button
                              icon={<FiRefreshCw />}
                              onClick={() => openDecision(selectedPartner, 'required_changes')}
                              className="partner-kyc-btn secondary"
                            >
                              Request Changes
                            </Button>
                            <Button
                              type="primary"
                              icon={<FiCheckCircle />}
                              disabled={!canApprove}
                              onClick={handleApproveSelected}
                              className={`partner-kyc-btn ${canApprove ? 'primary' : 'secondary'}`}
                            >
                              Approve
                            </Button>
                          </div>
                        </div>
                      );
                    })()}
                  </div>
                )}
              </div>
            </div>
          )}
        </Modal>

        {/* Document Modal */}
        <Modal
          title={null}
          open={documentModalVisible}
          onCancel={() => setDocumentModalVisible(false)}
          footer={null}
          width={900}
          centered
          styles={{
            body: { padding: 0 },
            content: { borderRadius: '16px', overflow: 'hidden' }
          }}
        >
          {selectedDocument && (() => {
            const url = selectedDocument?.url || selectedDocument?.upload_url || selectedDocument?.file_url || (typeof selectedDocument === 'string' ? selectedDocument : '');
            const type = selectedDocument?.content_type || selectedDocument?.mime_type || '';
            const docName = selectedDocument?.name || selectedDocument?.file_name || selectedDocument?.type || 'Document';

            // Check file type
            const isImage = isImageFile(url, type);
            const isPdf = isPdfFile(url, type);
            const isDoc = isDocumentFile(url, type);

            return (
              <div>
                <div style={{ padding: '12px 16px', background: '#2A2C41', color: '#fff', fontWeight: 600, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                  <span>{docName}</span>
                  <a href={url} target="_blank" rel="noopener noreferrer" download style={{ color: '#FDBF50', textDecoration: 'none', fontSize: '14px' }}>
                    <FiDownload style={{ marginRight: '4px' }} />
                    Download
                  </a>
                </div>
                {isImage ? (
                  <img alt="document" src={url} style={{ width: '100%', height: 'auto', display: 'block' }} />
                ) : isPdf ? (
                  (() => {
                    if (isSameOrigin(url)) {
                      // For same-origin PDFs, show download option to avoid X-Frame-Options
                      return (
                        <div style={{ padding: '40px', textAlign: 'center', background: '#F4F4F8', minHeight: '400px' }}>
                          <div style={{ fontSize: '64px', color: '#2A2C41', marginBottom: '20px' }}>📄</div>
                          <h3 style={{ color: '#2A2C41', marginBottom: '12px' }}>PDF Available for Download</h3>
                          <p style={{ color: '#666', marginBottom: '24px' }}>
                            This PDF is hosted on the same server and cannot be displayed inline due to security restrictions.
                          </p>
                          <a
                            href={url}
                            target="_blank"
                            rel="noopener noreferrer"
                            download
                            style={{
                              display: 'inline-block',
                              padding: '12px 28px',
                              background: '#F55D00',
                              color: '#fff',
                              borderRadius: '8px',
                              textDecoration: 'none',
                              fontWeight: 500,
                              fontSize: '16px'
                            }}
                          >
                            ⬇ Download PDF
                          </a>
                        </div>
                      );
                    } else {
                      // For cross-origin PDFs, use iframe
                      return (
                        <iframe title="document" src={url} style={{ width: '100%', height: '80vh', border: 'none' }} />
                      );
                    }
                  })()
                ) : isDoc ? (
                  (() => {
                    const viewerUrl = getDocumentViewerUrl(url);
                    if (viewerUrl) {
                      // Use external viewer for different-origin URLs
                      return (
                        <iframe
                          title="document"
                          src={viewerUrl}
                          style={{ width: '100%', height: '80vh', border: 'none' }}
                          onError={(e) => {
                            // Fallback to download if viewer fails
                            const fallbackDiv = document.createElement('div');
                            fallbackDiv.style.cssText = 'padding: 40px; text-align: center; background: #F4F4F8; min-height: 400px;';
                            fallbackDiv.innerHTML = `
                              <div style="font-size: 64px; color: #2A2C41; margin-bottom: 20px;">📄</div>
                              <h3 style="color: #2A2C41; margin-bottom: 12px;">Document Viewer Unavailable</h3>
                              <p style="color: #666; margin-bottom: 24px;">
                                The online viewer couldn't load this document. Please download it to view.
                              </p>
                              <a href="${url}" target="_blank" rel="noopener noreferrer" download
                                style="display: inline-block; padding: 10px 24px; background: #F55D00; color: #fff; border-radius: 8px; text-decoration: none; font-weight: 500;">
                                ⬇ Download Document
                              </a>
                            `;
                            e.target.parentNode.replaceChild(fallbackDiv, e.target);
                          }}
                        />
                      );
                    } else {
                      // For same-origin URLs, show download option directly to avoid X-Frame-Options issues
                      return (
                        <div style={{ padding: '40px', textAlign: 'center', background: '#F4F4F8', minHeight: '400px' }}>
                          <div style={{ fontSize: '64px', color: '#2A2C41', marginBottom: '20px' }}>📄</div>
                          <h3 style={{ color: '#2A2C41', marginBottom: '12px' }}>Document Available for Download</h3>
                          <p style={{ color: '#666', marginBottom: '24px' }}>
                            This document is hosted on the same server and cannot be displayed inline due to security restrictions.
                          </p>
                          <a
                            href={url}
                            target="_blank"
                            rel="noopener noreferrer"
                            download
                            style={{
                              display: 'inline-block',
                              padding: '12px 28px',
                              background: '#F55D00',
                              color: '#fff',
                              borderRadius: '8px',
                              textDecoration: 'none',
                              fontWeight: 500,
                              fontSize: '16px'
                            }}
                          >
                            ⬇ Download Document
                          </a>
                        </div>
                      );
                    }
                  })()
                ) : (
                  <div style={{ padding: '40px', textAlign: 'center', background: '#F4F4F8', minHeight: '400px' }}>
                    <FiFile style={{ fontSize: '64px', color: '#2A2C41', marginBottom: '20px' }} />
                    <h3 style={{ color: '#2A2C41', marginBottom: '12px' }}>Preview Not Available</h3>
                    <p style={{ color: '#666', marginBottom: '24px' }}>
                      Please download the file to view its contents.
                    </p>
                    <a
                      href={url}
                      target="_blank"
                      rel="noopener noreferrer"
                      download
                      style={{
                        display: 'inline-block',
                        padding: '10px 24px',
                        background: '#F55D00',
                        color: '#fff',
                        borderRadius: '8px',
                        textDecoration: 'none',
                        fontWeight: 500
                      }}
                    >
                      <FiDownload style={{ marginRight: '8px' }} />
                      Download File
                    </a>
                  </div>
                )}
              </div>
            );
          })()}
        </Modal>

        {/* Temporarily commented out to force cache refresh */}
        <Modal
          title={decisionAction === 'declined' ? 'Reject Partner' : 'Request Changes'}
          open={decisionModalVisible}
          onCancel={() => setDecisionModalVisible(false)}
          onOk={submitDecision}
          okText={decisionAction === 'declined' ? 'Reject' : 'Request Changes'}
          width={600}
        >
          <div style={{ marginBottom: '16px' }}>
            <label style={{ display: 'block', marginBottom: '8px', fontWeight: '500' }}>
              Comments (optional)
            </label>
            <Input.TextArea
              rows={3}
              value={decisionDeclineReason}
              onChange={(e) => setDecisionDeclineReason(e.target.value)}
              placeholder="Add comments for the partner..."
            />
          </div>

          {decisionAction === 'declined' && (
            <div>
              <label style={{ display: 'block', marginBottom: '8px', fontWeight: '500' }}>
                Rejection Reasons
              </label>
              <Select
                mode="multiple"
                style={{ width: '100%', marginBottom: '8px' }}
                placeholder="Select reasons from templates"
                loading={templatesLoading}
                value={decisionRejectionReasons.filter(r => r.template_id).map(r => r.template_id)}
                onChange={(selectedIds) => {
                  const templateReasons = selectedIds.map(id => {
                    const template = reviewTemplates.rejection.find(t => t.id === id);
                    return {
                      template_id: id,
                      title: template?.title || '',
                      description: template?.description || ''
                    };
                  });
                  const customReasons = decisionRejectionReasons.filter(r => !r.template_id);
                  setDecisionRejectionReasons([...templateReasons, ...customReasons]);
                }}
              >
                {reviewTemplates.rejection.map(template => (
                  <Option key={template.id} value={template.id}>
                    <div>
                      <div style={{ fontWeight: '500' }}>{template.title}</div>
                      <div style={{ fontSize: '12px', color: '#666' }}>
                        {template.category} - {template.description}
                      </div>
                    </div>
                  </Option>
                ))}
              </Select>

              <Select
                mode="tags"
                style={{ width: '100%' }}
                placeholder="Add custom reasons..."
                value={decisionRejectionReasons.filter(r => !r.template_id).map(r => r.title)}
                onChange={(customTitles) => {
                  const templateReasons = decisionRejectionReasons.filter(r => r.template_id);
                  const customReasons = customTitles.map(title => ({
                    title,
                    description: ''
                  }));
                  setDecisionRejectionReasons([...templateReasons, ...customReasons]);
                }}
              />
            </div>
          )}

          {decisionAction === 'required_changes' && (
            <div>
              <label style={{ display: 'block', marginBottom: '8px', fontWeight: '500' }}>
                Required Changes
              </label>
              <Select
                mode="multiple"
                style={{ width: '100%', marginBottom: '8px' }}
                placeholder="Select changes from templates"
                loading={templatesLoading}
                value={decisionRequiredChanges.filter(r => r.template_id).map(r => r.template_id)}
                onChange={(selectedIds) => {
                  const templateChanges = selectedIds.map(id => {
                    const template = reviewTemplates.required_changes.find(t => t.id === id);
                    return {
                      template_id: id,
                      title: template?.title || '',
                      description: template?.description || ''
                    };
                  });
                  const customChanges = decisionRequiredChanges.filter(r => !r.template_id);
                  setDecisionRequiredChanges([...templateChanges, ...customChanges]);
                }}
              >
                {reviewTemplates.required_changes.map(template => (
                  <Option key={template.id} value={template.id}>
                    <div>
                      <div style={{ fontWeight: '500' }}>{template.title}</div>
                      <div style={{ fontSize: '12px', color: '#666' }}>
                        {template.category} - {template.description}
                      </div>
                    </div>
                  </Option>
                ))}
              </Select>

              <Select
                mode="tags"
                style={{ width: '100%' }}
                placeholder="Add custom changes..."
                value={decisionRequiredChanges.filter(r => !r.template_id).map(r => r.title)}
                onChange={(customTitles) => {
                  const templateChanges = decisionRequiredChanges.filter(r => r.template_id);
                  const customChanges = customTitles.map(title => ({
                    title,
                    description: ''
                  }));
                  setDecisionRequiredChanges([...templateChanges, ...customChanges]);
                }}
              />
            </div>
          )}

          <div style={{ marginTop: '16px' }}>
            <label style={{ display: 'block', marginBottom: '8px', fontWeight: '500' }}>
              Reapply After (days)
            </label>
            <InputNumber
              min={0}
              max={365}
              value={decisionReapplyDays}
              onChange={(v) => setDecisionReapplyDays(v || 0)}
              style={{ width: '100%' }}
            />
          </div>
        </Modal>
      </div>
    </div>
  );
};

export default DeliveryPartnerReview;
