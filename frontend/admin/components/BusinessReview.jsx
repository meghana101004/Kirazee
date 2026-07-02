import React, { useState, useEffect } from 'react';
import {
  Table,
  Button,
  Select,
  DatePicker,
  Input,
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
  FiShoppingBag,
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
  FiList,
  FiGrid,
  FiUser
} from 'react-icons/fi';
import dayjs from 'dayjs';
import { API_ENDPOINTS } from '../utils/config';
import AdminService from '../services/adminService';
import '../../css/admin/BusinessReviewModal.css';

const { Option } = Select;
const { RangePicker } = DatePicker;

const PendingBusinessDashboard = () => {
  const BASE = `${API_ENDPOINTS.BASE_URL}/business`;
  const getAuthHeaders = () => {
    try {
      const token = localStorage.getItem('admin_token');
      return token ? { Authorization: `Bearer ${token}` } : {};
    } catch (_) {
      return {};
    }
  };
  const getAdminId = () => {
    try {
      return (
        localStorage.getItem('admin_id') ||
        localStorage.getItem('admin_user_id') ||
        localStorage.getItem('user_id') ||
        null
      );
    } catch (_) {
      return null;
    }
  };

  const formatPaymentModes = (pm) => {
    if (!pm || pm === '—') return '—';
    if (typeof pm === 'string') return pm;
    const list = [];
    if (pm.upi) list.push('UPI');
    if (pm.card) list.push('Card');
    if (pm.cash) list.push('Cash');
    return list.length ? list.join(', ') : '—';
  };

  const formatDeliveryPreferences = (dp) => {
    if (!dp || dp === '—') return '—';
    if (typeof dp === 'string') return dp;
    const list = [];
    if (dp.pickup_only) list.push('Pickup Only');
    if (dp.self_delivery) list.push('Self Delivery');
    if (dp.kirazee_delivery) list.push('Kirazee Delivery');
    return list.length ? list.join(', ') : '—';
  };
  const [businesses, setBusinesses] = useState([]);
  const [filteredBusinesses, setFilteredBusinesses] = useState([]);
  const [loading, setLoading] = useState(false);
  const [selectedBusiness, setSelectedBusiness] = useState(null);
  const [detailModalVisible, setDetailModalVisible] = useState(false);
  const [selectedRowKeys, setSelectedRowKeys] = useState([]);
  const [bulkActionLoading, setBulkActionLoading] = useState(false);
  const [documentModalVisible, setDocumentModalVisible] = useState(false);
  const [selectedDocument, setSelectedDocument] = useState(null);
  const [decisionModalVisible, setDecisionModalVisible] = useState(false);
  const [decisionAction, setDecisionAction] = useState(null);
  const [decisionBusinessId, setDecisionBusinessId] = useState(null);
  const [decisionComments, setDecisionComments] = useState('');
  const [decisionRejectionReasons, setDecisionRejectionReasons] = useState([]);
  const [decisionRequiredChanges, setDecisionRequiredChanges] = useState([]);

  // Review Templates Management
  const [reviewTemplates, setReviewTemplates] = useState({
    rejection: [],
    required_changes: [],
    approval: []
  });
  const [templatesLoading, setTemplatesLoading] = useState(false);

  // Pagination states
  const [currentPage, setCurrentPage] = useState(1);
  const [pageSize, setPageSize] = useState(10);
  const [totalPages, setTotalPages] = useState(1);
  const [totalItems, setTotalItems] = useState(0);

  // Filter states
  const [categories, setCategories] = useState([]);
  const [filters, setFilters] = useState({
    status: 'all',
    category: 'all',
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

  const mapApplicationToRow = (app) => {
    const applicationId = app?.application_id || app?.id || app?.business_id;
    const businessInfo = app?.business_info || app?.business || {};
    const ownerInfo = app?.owner_info || app?.owner || {};
    const address = businessInfo?.address || app?.address || {};
    const documents = app?.documents || businessInfo?.documents || [];
    const city = address?.city || '';
    const state = address?.state || '';
    const formatted = address?.formatted_address || '';
    const location = app?.location || formatted || [city, state].filter(Boolean).join(', ');
    const categoryRaw = businessInfo?.business_category || businessInfo?.category || businessInfo?.business_type || app?.category || 'others';
    const statusRaw = app?.status || app?.business_status || 'pending';
    const rejectionReasons = app?.rejection_reasons || app?.status?.rejection_reasons || [];
    const requiredChanges = app?.required_changes || app?.status?.required_changes || [];
    const adminComments = app?.comments || app?.status?.comments || '';
    const toUiStatus = (s) => {
      const val = String(s || '').toLowerCase();
      if (val === 'approved') return 'Approved';
      if (val === 'rejected') return 'Rejected';
      if (val === 'in_progress') return 'In Progress';
      if (val === 'requires_changes' || val === 'request_changes' || val === 'changes_requested') return 'Requires Changes';
      if (val === 'submitted') return 'Submitted';
      if (val === 'pending' || val === 'pending review' || val === 'under_review' || val === 'under review') return 'Pending Review';
      return val ? val.replace(/_/g, ' ').replace(/\b\w/g, (m) => m.toUpperCase()) : 'Pending Review';
    };
    return {
      id: applicationId,
      application_id: applicationId,
      businessName: app?.business_name || businessInfo?.business_name || app?.business_name || businessInfo?.name || 'Unknown',
      category: typeof categoryRaw === 'string' ? categoryRaw.toLowerCase() : 'others',
      ownerName: ownerInfo?.name || app?.owner_name || 'Unknown',
      location: location || '—',
      submissionDate: app?.submitted_at || app?.submission_date || app?.created_at || new Date().toISOString(),
      status: toUiStatus(statusRaw),
      rawStatus: String(statusRaw || '').toLowerCase(),
      phone: ownerInfo?.phone || app?.phone || businessInfo?.phone || '—',
      email: ownerInfo?.email || app?.email || businessInfo?.email || '—',
      registrationNumber: app?.registration_number || businessInfo?.registration_number || '—',
      workingHours: app?.operational_details?.working_hours || app?.working_hours || businessInfo?.working_hours || '—',
      paymentModes: app?.operational_details?.payment_modes || app?.payment_modes || '—',
      deliveryPreferences: app?.operational_details?.delivery_preferences || app?.delivery_preferences || '—',
      documents: Array.isArray(documents) ? documents.map((d) => {
        if (typeof d === 'string') return { type: 'Document', name: d, url: d };
        return {
          type: d?.type || d?.document_type || 'Document',
          name: d?.file_name || d?.type || 'Document',
          url: d?.url || d?.upload_url || d?.file_url || '',
          content_type: d?.content_type || d?.mime_type || ''
        };
      }) : [],
      rejection_reasons: Array.isArray(rejectionReasons) ? rejectionReasons : [],
      required_changes: Array.isArray(requiredChanges) ? requiredChanges : [],
      comments: adminComments
    };
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

  useEffect(() => {
    const fetchData = async () => {
      await loadBusinesses();
    };
    fetchData();
  }, [filters, currentPage]); // Add currentPage to dependency array

  const loadBusinesses = async () => {
    setLoading(true);
    try {
      // Build query parameters
      const params = new URLSearchParams({
        page: currentPage,
        limit: pageSize,
        ...(filters.searchText && { search: filters.searchText }),
        ...(filters.category && filters.category !== 'all' && { category: filters.category }),
        ...(filters.businessType && { business_type: filters.businessType }),
        ...(filters.location && { location: filters.location }),
        ...(filters.dateRange?.[0] && filters.dateRange?.[1] && {
          start_date: dayjs(filters.dateRange[0]).format('YYYY-MM-DD'),
          end_date: dayjs(filters.dateRange[1]).format('YYYY-MM-DD')
        })
      });

      // Determine the correct endpoint based on status filter
      let endpoint = '/onboarding/admin/business-applications/';
      switch (filters.status) {
        case 'approved':
          endpoint += 'approved';
          break;
        case 'rejected':
          endpoint += 'rejected';
          break;
        case 'pending':
          endpoint += 'pending';
          break;
        case 'in_progress':
          endpoint = '/onboarding/in_progress/business-applications/pending';
          break;
        default:
          endpoint += 'all';
      }

      const response = await fetch(`${BASE}${endpoint}?${params.toString()}`, {
        headers: {
          'Content-Type': 'application/json',
          ...getAuthHeaders()
        }
      });

      if (!response.ok) {
        const errorData = await response.json();
        throw new Error(errorData.detail || 'Failed to fetch businesses');
      }

      const data = await response.json();
      if (data.success && data.data && data.data.applications) {
        const mapped = data.data.applications.map(mapApplicationToRow);
        setBusinesses(mapped);
        setFilteredBusinesses(mapped);

        // Update pagination if available in response
        if (data.data.pagination) {
          const p = data.data.pagination;
          setCurrentPage(p.current_page || 1);
          if (p.items_per_page) setPageSize(p.items_per_page);
          if (p.total_pages) setTotalPages(p.total_pages);
          if (typeof p.total_items === 'number') setTotalItems(p.total_items);
        }
      } else {
        console.error('Unexpected response format:', data);
        message.error('Failed to load business applications: Invalid response format');
      }
    } catch (error) {
      console.error('Error loading businesses:', error);
      message.error(`Failed to load business applications: ${error.message || 'Unknown error'}`);
    } finally {
      setLoading(false);
    }
  };

  // Pagination functions
  const paginatedBusinesses = filteredBusinesses;

  const handlePageChange = (page) => {
    if (page >= 1 && page <= totalPages) {
      setCurrentPage(page);
    }
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
      category: 'all',
      location: '',
      dateRange: null,
      searchText: ''
    });
  };


  const viewBusinessDetails = async (business) => {
    // Show modal with existing row data immediately
    setSelectedBusiness(business);
    setDetailModalVisible(true);
    try {
      const id = business?.application_id || business?.id;
      const response = await fetch(`${BASE}/onboarding/admin/business-applications/${id}/details`, { headers: { 'Content-Type': 'application/json', ...getAuthHeaders() } });
      if (!response.ok) {
        throw new Error('Failed to fetch details');
      }
      const json = await response.json();
      const d = json?.data || json;
      
      console.log('API Response for business details:', {
        apiStatus: d?.status,
        apiBusinessStatus: d?.business_status,
        currentBusinessStatus: business?.status,
        currentBusinessRawStatus: business?.rawStatus
      });
      
      const detailMapped = mapApplicationToRow({
        application_id: d?.application_id || id,
        business_name: d?.business_name,  // Add business_name at root level
        business_info: d?.business_info || {},  // Pass empty object if business_info doesn't exist
        owner_info: d?.owner_info,
        documents: d?.documents,
        submission_date: d?.submitted_at || d?.last_updated,
        status: d?.status || d?.business_status,  // Add status field from API response
        operational_details: d?.operational_details,
        working_hours: d?.working_hours,
        payment_modes: d?.payment_modes,
        delivery_preferences: d?.delivery_preferences,
        rejection_reasons: d?.status?.rejection_reasons || d?.rejection_reasons,
        required_changes: d?.status?.required_changes || d?.required_changes,
        comments: d?.status?.comments || d?.comments
      });
      
      // Preserve the original status if it was approved (don't let API overwrite it)
      if (business?.status === 'Approved' || business?.rawStatus === 'approved') {
        detailMapped.status = business.status;
        detailMapped.rawStatus = business.rawStatus;
      }
      
      setSelectedBusiness((prev) => ({ ...(prev || {}), ...detailMapped }));
    } catch (e) {
      message.error('Failed to load business details');
      setSelectedBusiness(business);
    }
  };

  const handleBusinessAction = async (businessId, action, extra = {}) => {
    if (!businessId) {
      message.error('Invalid application id');
      return;
    }
    const newStatus = action === 'approve' ? 'Approved' : action === 'pending' ? 'Requires Changes' : 'Rejected';
    try {
      const id = businessId;
      const payloadAction = action === 'approve' ? 'approve' : (action === 'pending' ? 'request_changes' : 'reject');
      const payload = { action: payloadAction };
      const adminId = getAdminId();
      if (adminId) payload.admin_id = adminId;
      if (extra && typeof extra.comments === 'string' && extra.comments.trim()) payload.comments = extra.comments.trim();
      if (payloadAction === 'reject' && Array.isArray(extra.rejection_reasons) && extra.rejection_reasons.length) {
        payload.rejection_reasons = extra.rejection_reasons;
      }
      if (payloadAction === 'request_changes' && Array.isArray(extra.required_changes) && extra.required_changes.length) {
        payload.required_changes = extra.required_changes;
      }
      const response = await fetch(`${BASE}/onboarding/admin/business-applications/${id}/review`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', ...getAuthHeaders() },
        body: JSON.stringify(payload)
      });
      if (!response.ok) throw new Error('Review failed');
      let respJson = {};
      try { respJson = await response.json(); } catch (_) { respJson = {}; }
      const respData = respJson?.data || respJson || {};
      const updatedRaw = payloadAction === 'approve' ? 'approved' : payloadAction === 'reject' ? 'rejected' : 'requires_changes';
      const rejectionReasons = respData.rejection_reasons || respData.status?.rejection_reasons || extra.rejection_reasons || [];
      const requiredChanges = respData.required_changes || respData.status?.required_changes || extra.required_changes || [];
      const comments = respData.comments || respData.status?.comments || extra.comments || '';
      setBusinesses(prevBusinesses =>
        prevBusinesses.map(business =>
          business.id === id
            ? {
              ...business,
              status: newStatus,
              rawStatus: updatedRaw,
              rejection_reasons: Array.isArray(rejectionReasons) ? rejectionReasons : [],
              required_changes: Array.isArray(requiredChanges) ? requiredChanges : [],
              comments: typeof comments === 'string' ? comments : '',
              actionDate: new Date().toISOString().split('T')[0]
            }
            : business
        )
      );
      if (action === 'approve') {
        message.success({ content: `Business approved successfully!`, style: { marginTop: '100px' }, duration: 3 });
      } else if (action === 'pending') {
        message.info({ content: `Requested changes recorded.`, style: { marginTop: '100px' }, duration: 3 });
      } else {
        message.warning({ content: `Business rejected successfully!`, style: { marginTop: '100px' }, duration: 3 });
      }
    } catch (error) {
      message.error('Failed to update business status');
    }
  };

  const openDecision = (record, action) => {
    const id = record?.application_id || record?.id;
    setDecisionAction(action);
    setDecisionBusinessId(id);
    setDecisionComments('');
    setDecisionRejectionReasons([]);
    setDecisionRequiredChanges([]);
    setDecisionModalVisible(true);
  };

  const submitDecision = async () => {
    await handleBusinessAction(decisionBusinessId, decisionAction, {
      comments: decisionComments,
      rejection_reasons: decisionRejectionReasons,
      required_changes: decisionRequiredChanges
    });
    setDecisionModalVisible(false);
  };

  const handleBulkAction = async (action) => {
    if (selectedRowKeys.length === 0) {
      message.warning('Please select businesses to perform bulk action');
      return;
    }
    setBulkActionLoading(true);
    try {
      for (const id of selectedRowKeys) {
        const payload = action === 'approve' ? { action: 'approve' } : { action: 'reject' };
        const res = await fetch(`${BASE}/onboarding/admin/business-applications/${id}/review`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json', ...getAuthHeaders() },
          body: JSON.stringify(payload)
        });
        if (!res.ok) throw new Error('Bulk review failed');
      }
      const newStatus = action === 'approve' ? 'Approved' : 'Rejected';
      setBusinesses(prev => prev.map(b =>
        selectedRowKeys.includes(b.id)
          ? { ...b, status: newStatus, actionDate: new Date().toISOString().split('T')[0] }
          : b
      ));
      const count = selectedRowKeys.length;
      setSelectedRowKeys([]);
      message.success({
        content: `${count} businesses ${action === 'approve' ? 'approved' : 'rejected'} successfully!`,
        style: { marginTop: '100px' },
        duration: 3
      });
    } catch (error) {
      message.error('Failed to perform bulk action');
    } finally {
      setBulkActionLoading(false);
    }
  };

  const rowSelection = {
    selectedRowKeys,
    onChange: (keys) => setSelectedRowKeys(keys),
  };

  const exportToCSV = () => {
    const csvData = filteredBusinesses.map(business => ({
      'Business Name': business.businessName,
      'Owner Name': business.ownerName,
      'Category': getCategoryLabel(business.category),
      'Location': business.location,
      'Phone': business.phone,
      'Email': business.email,
      'Registration Number': business.registrationNumber,
      'Submission Date': dayjs(business.submissionDate).format('YYYY-MM-DD'),
      'Status': business.status,
      'Working Hours': business.workingHours,
    }));

    const csvContent = [
      Object.keys(csvData[0]).join(','),
      ...csvData.map(row => Object.values(row).map(value => `"${value}"`).join(','))
    ].join('\n');

    const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' });
    const link = document.createElement('a');
    const url = URL.createObjectURL(blob);
    link.setAttribute('href', url);
    link.setAttribute('download', `pending-businesses-${dayjs().format('YYYY-MM-DD')}.csv`);
    link.style.visibility = 'hidden';
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);

    message.success('Business data exported successfully!');
  };

  const getCategoryColor = (category) => {
    const colors = {
      food: '#F55D00',
      grocery: '#FDBF50',
      clothing: '#2A2C41',
      others: '#F55D00'
    };
    return colors[category] || '#F4F4F8';
  };

  const getCategoryLabel = (category) => {
    const labels = {
      food: 'Food',
      grocery: 'Grocery',
      clothing: 'Clothing',
      others: 'Others'
    };
    return labels[category] || category;
  };

  const formatWorkingHours = (wh) => {
    if (!wh || wh === '—') return '—';
    if (typeof wh === 'string') return wh;
    try {
      const open = wh.opening_time || wh.open || wh.start;
      const close = wh.closing_time || wh.close || wh.end;
      const tz = wh.timezone || wh.tz;
      const range = (open || close) ? `${open || ''}${open && close ? ' - ' : ''}${close || ''}` : '';
      const tzStr = tz ? ` (${tz})` : '';
      return (range || tzStr) ? `${range}${tzStr}` : '—';
    } catch (_) {
      return '—';
    }
  };

  const columns = [
    {
      title: 'Business Name',
      dataIndex: 'businessName',
      key: 'businessName',
      render: (text, record) => (
        <div>
          <div style={{ fontWeight: '600', color: '#2A2C41', fontSize: '15px' }}>
            {text}
          </div>
          <div style={{ fontSize: '13px', color: '#2A2C41' }}>
            {record.ownerName}
          </div>
        </div>
      ),
    },
    {
      title: 'Category',
      dataIndex: 'category',
      key: 'category',
      render: (category) => (
        <Tag
          color={getCategoryColor(category)}
          style={{
            borderRadius: '6px',
            fontWeight: '500',
            fontSize: '12px'
          }}
        >
          {getCategoryLabel(category)}
        </Tag>
      ),
    },
    {
      title: 'Location',
      dataIndex: 'location',
      key: 'location',
      render: (location) => (
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
          }}>{location}</span>
        </div>
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
        let badgeStatus = 'processing';
        let textColor = '#2A2C41';
        let backgroundColor = 'rgba(42, 44, 65, 0.1)';

        if (status === 'Approved') {
          badgeStatus = 'success';
          textColor = '#FDBF50';
          backgroundColor = 'rgba(253, 191, 80, 0.1)';
        } else if (status === 'Rejected') {
          badgeStatus = 'error';
          textColor = '#F55D00';
          backgroundColor = 'rgba(245, 93, 0, 0.1)';
        }

        return (
          <div style={{
            padding: '4px 8px',
            borderRadius: '6px',
            backgroundColor: backgroundColor,
            display: 'inline-flex',
            alignItems: 'center',
            gap: '6px'
          }}>
            <Badge status={badgeStatus} />
            <span style={{
              color: textColor,
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
      title: 'Notes',
      key: 'notes',
      render: (_, record) => {
        const isRejected = record.status === 'Rejected';
        const isReqChanges = record.status === 'Requires Changes';
        const items = isRejected ? (record.rejection_reasons || []) : (isReqChanges ? (record.required_changes || []) : []);
        if (!items || items.length === 0) return null;
        return (
          <div style={{ display: 'flex', gap: '6px', flexWrap: 'wrap', maxWidth: 260 }}>
            {items.slice(0, 3).map((t, idx) => (
              <Tag key={idx} color={isRejected ? '#F55D00' : '#FDBF50'} style={{ borderRadius: '6px' }}>
                {String(t)}
              </Tag>
            ))}
            {items.length > 3 && (
              <Tag style={{ borderRadius: '6px' }}>+{items.length - 3}</Tag>
            )}
          </div>
        );
      }
    },
    {
      title: 'Actions',
      key: 'actions',
      render: (_, record) => {
        const raw = String(record.rawStatus || '').toLowerCase();
        const statusGroup = (
          raw === 'approved' ? 'approved' :
            raw === 'rejected' ? 'rejected' :
              (raw === 'pending' || raw === 'submitted' || raw === 'under_review' || raw === 'under review') ? 'pending' :
                (raw === 'in_progress' || raw === 'requires_changes' || raw === 'request_changes') ? 'in-progress' :
                  'pending'
        );
        const isRequiresChanges = raw === 'requires_changes' || raw === 'request_changes' || raw === 'changes_requested';
        const showApprove = statusGroup === 'pending' || statusGroup === 'rejected' || isRequiresChanges;
        const showReject = statusGroup === 'pending' || statusGroup === 'in-progress' || isRequiresChanges || statusGroup === 'approved';
        const showPending = statusGroup === 'in-progress' || statusGroup === 'rejected' || isRequiresChanges;
        return (
          <Space size="small">
            <Tooltip title="View Details">
              <Button
                type="text"
                icon={<FiEye />}
                onClick={() => viewBusinessDetails(record)}
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
            {showApprove && (
              <Tooltip title="Approve Business">
                <Button
                  size="small"
                  icon={<FiCheckCircle />}
                  onClick={() => openDecision(record, 'approve')}
                  style={{
                    color: '#ffffff',
                    backgroundColor: '#FDBF50',
                    borderColor: '#FDBF50',
                    borderRadius: '8px',
                    fontWeight: '500',
                    height: '32px',
                    padding: '4px 12px'
                  }}
                  onMouseEnter={(e) => {
                    e.currentTarget.style.backgroundColor = '#F55D00';
                    e.currentTarget.style.borderColor = '#F55D00';
                  }}
                  onMouseLeave={(e) => {
                    e.currentTarget.style.backgroundColor = '#FDBF50';
                    e.currentTarget.style.borderColor = '#FDBF50';
                  }}
                >
                  Approve
                </Button>
              </Tooltip>
            )}
            {showReject && (
              <Tooltip title="Reject Business">
                <Button
                  size="small"
                  icon={<FiXCircle />}
                  onClick={() => openDecision(record, 'reject')}
                  style={{
                    color: '#ffffff',
                    backgroundColor: '#F55D00',
                    borderColor: '#F55D00',
                    borderRadius: '8px',
                    fontWeight: '500',
                    height: '32px',
                    padding: '4px 12px'
                  }}
                  onMouseEnter={(e) => {
                    e.currentTarget.style.backgroundColor = '#2A2C41';
                    e.currentTarget.style.borderColor = '#2A2C41';
                  }}
                  onMouseLeave={(e) => {
                    e.currentTarget.style.backgroundColor = '#F55D00';
                    e.currentTarget.style.borderColor = '#F55D00';
                  }}
                >
                  Reject
                </Button>
              </Tooltip>
            )}
            {showPending && (
              <Tooltip title="Mark as Pending">
                <Button
                  size="small"
                  icon={<FiRefreshCw />}
                  onClick={() => openDecision(record, 'pending')}
                  style={{
                    color: '#2A2C41',
                    backgroundColor: '#f0f0f0',
                    borderColor: '#d9d9d9',
                    borderRadius: '8px',
                    fontWeight: '500',
                    height: '32px',
                    padding: '4px 12px'
                  }}
                >
                  Pending
                </Button>
              </Tooltip>
            )}
          </Space>
        );
      },
    },
  ];

  return (
    <div style={{
      backgroundColor: '#F4F4F8',
    }}>
      <style>
        {`
          .ant-modal .ant-modal-content {
            position: relative !important;
            background-color: white !important;
            background-clip: initial !important;
            border: none !important;
            border-radius: 16px !important;
            box-shadow: 0 4px 20px rgba(0,0,0,0.15) !important;
            pointer-events: auto !important;
            padding: 0px !important;
            max-height: 90vh !important;
            overflow-y: auto !important;
            scrollbar-width: none !important; /* Firefox */
            -ms-overflow-style: none !important; /* IE and Edge */
          }
          .ant-modal .ant-modal-content::-webkit-scrollbar {
            display: none !important; /* Chrome, Safari and Opera */
          }
          .ant-modal .ant-modal-close {
            color: white !important;
            font-size: 18px !important;
            top: 16px !important;
            right: 16px !important;
          }
          .ant-modal .ant-modal-close:hover {
            color: #F55D00 !important;
          }
          .ant-modal .ant-modal-close .ant-modal-close-x {
            display: flex !important;
            align-items: center !important;
            justify-content: center !important;
            width: 32px !important;
            height: 32px !important;
            font-size: 18px !important;
          }
        `}
      </style>
      <div> {/* Reduced max width */}
        {/* Header */}
        <div style={{ marginBottom: '24px' }}>
          <div style={{
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'center',
            gap: '20px',
            marginBottom: '8px',
            flexWrap: 'wrap'
          }}>
            <div style={{ flex: '1 1 auto', minWidth: '200px' }}>
              <h1 style={{
                fontSize: 'clamp(20px, 4vw, 30px)',
                fontWeight: '700',
                color: '#2A2C41',
                margin: '0',
                letterSpacing: '-0.025em',
                lineHeight: '1.2'
              }}>
                Business Merchant KYC Verification
              </h1>

            </div>

            {/* Header Pagination and Export */}
            <div style={{
              display: 'flex',
              alignItems: 'center',
              gap: '12px',
              flexWrap: 'wrap'
            }}>
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
              {/* Pagination */}
              {totalPages > 1 && (
                <div style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: '12px',
                  background: 'white',
                  padding: '12px 16px',
                  borderRadius: '8px',
                  boxShadow: '0 2px 8px rgba(0,0,0,0.1)',
                  border: '1px solid #e0e0e0'
                }}>
                  <button
                    disabled={currentPage <= 1}
                    onClick={() => handlePageChange(currentPage - 1)}
                    style={{
                      background: currentPage <= 1 ? 'rgba(245, 93, 0, 0.3)' : '#F55D00',
                      color: currentPage <= 1 ? 'rgba(255, 255, 255, 0.6)' : 'white',
                      border: 'none',
                      padding: '8px 12px',
                      borderRadius: '6px',
                      cursor: currentPage <= 1 ? 'not-allowed' : 'pointer',
                      fontSize: '14px',
                      fontWeight: '500',
                      transition: 'all 0.2s ease',
                      minWidth: '40px'
                    }}
                  >
                    ◀
                  </button>

                  <div style={{
                    display: 'flex',
                    alignItems: 'center',
                    gap: '8px',
                    fontSize: '14px',
                    color: '#495057',
                    fontWeight: '500'
                  }}>
                    <input
                      type="number"
                      min="1"
                      max={totalPages}
                      value={currentPage}
                      onChange={(e) => {
                        const page = parseInt(e.target.value);
                        if (page >= 1 && page <= totalPages) {
                          handlePageChange(page);
                        }
                      }}
                      style={{
                        width: '50px',
                        textAlign: 'center',
                        padding: '6px 8px',
                        border: '1px solid #F55D00',
                        borderRadius: '4px',
                        fontSize: '14px',
                        fontWeight: '500'
                      }}
                    />
                    <span>of {totalPages}</span>
                  </div>

                  <button
                    disabled={currentPage >= totalPages}
                    onClick={() => handlePageChange(currentPage + 1)}
                    style={{
                      background: currentPage >= totalPages ? 'rgba(245, 93, 0, 0.3)' : '#F55D00',
                      color: currentPage >= totalPages ? 'rgba(255, 255, 255, 0.6)' : 'white',
                      border: 'none',
                      padding: '8px 12px',
                      borderRadius: '6px',
                      cursor: currentPage >= totalPages ? 'not-allowed' : 'pointer',
                      fontSize: '14px',
                      fontWeight: '500',
                      transition: 'all 0.2s ease',
                      minWidth: '40px'
                    }}
                  >
                    ▶
                  </button>
                </div>
              )}

              {/* Export Button */}
              <button
                onClick={exportToCSV}
                disabled={filteredBusinesses.length === 0}
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: '6px',
                  background: filteredBusinesses.length === 0 ? '#dee2e6' : '#2A2C41',
                  color: filteredBusinesses.length === 0 ? '#6c757d' : 'white',
                  border: 'none',
                  padding: '8px 12px',
                  borderRadius: '6px',
                  cursor: filteredBusinesses.length === 0 ? 'not-allowed' : 'pointer',
                  fontSize: '12px',
                  fontWeight: '500',
                  transition: 'all 0.2s ease',
                  boxShadow: '0 2px 8px rgba(0,0,0,0.1)',
                  minHeight: '36px'
                }}
                onMouseEnter={(e) => {
                  if (filteredBusinesses.length > 0) {
                    e.target.style.background = '#1a1c2e';
                    e.target.style.transform = 'translateY(-1px)';
                  }
                }}
                onMouseLeave={(e) => {
                  if (filteredBusinesses.length > 0) {
                    e.target.style.background = '#2A2C41';
                    e.target.style.transform = 'translateY(0)';
                  }
                }}
              >
                <FiDownload style={{ fontSize: '12px' }} />
                Export
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
                title={<span style={{ color: '#2A2C41', fontSize: '13px' }}>Total Pending</span>}
                value={filteredBusinesses.length}
                valueStyle={{ color: '#2A2C41', fontSize: '20px', fontWeight: '700' }}
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
                title={<span style={{ color: '#2A2C41', fontSize: '13px' }}>Food Businesses</span>}
                value={filteredBusinesses.filter(b => b.category === 'food').length}
                valueStyle={{ color: '#F55D00', fontSize: '20px', fontWeight: '700' }}
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
                title={<span style={{ color: '#2A2C41', fontSize: '13px' }}>Grocery Stores</span>}
                value={filteredBusinesses.filter(b => b.category === 'grocery').length}
                valueStyle={{ color: '#FDBF50', fontSize: '20px', fontWeight: '700' }}
              />
            </Card>
          </Col>
          <Col xs={24} sm={12} md={6}>
            <Card style={{
              borderRadius: '12px',
              border: '1px solid #2A2C41',
              boxShadow: '0 4px 12px rgba(42, 44, 65, 0.1)',
              padding: '8px'
            }}>
              <Statistic
                title={<span style={{ color: '#2A2C41', fontSize: '13px' }}>Other Categories</span>}
                value={filteredBusinesses.filter(b => b.category === 'clothing' || b.category === 'others').length}
                valueStyle={{ color: '#2A2C41', fontSize: '20px', fontWeight: '700' }}
              />
            </Card>
          </Col>
        </Row>

        {/* Filters */}
        <Card style={{
          borderRadius: '12px',
          marginBottom: '16px',
          border: '1px solid rgba(42, 44, 65, 0.08)',
          boxShadow: '0 2px 8px rgba(42, 44, 65, 0.04)'
        }}>
          <Row gutter={[12, 8]} align="middle">
            <Col xs={24} sm={12} md={4} lg={3}>
              <div style={{ marginBottom: '4px' }}>
                <span style={{ fontSize: '12px', fontWeight: '500', color: '#2A2C41' }}>
                  Search
                </span>
              </div>
              <Input
                placeholder="Search businesses..."
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
            <Col xs={24} sm={12} md={4} lg={3}>
              <div style={{ marginBottom: '4px' }}>
                <span style={{ fontSize: '12px', fontWeight: '500', color: '#2A2C41' }}>
                  Category
                </span>
              </div>
              <Select
                placeholder="All Categories"
                value={filters.category}
                onChange={(value) => handleFilterChange('category', value)}
                style={{
                  width: '100%',
                  borderRadius: '6px',
                  height: '32px'
                }}
                className="custom-select"
              >
                <Option value="all">All Categories</Option>
                <Option value="Retail_and_Wholesale">Retail & Wholesale</Option>
                <Option value="Food_and_Beverage">Food & Beverage</Option>
                <Option value="Fashion_Retail">Clothing & Fashions</Option>
                <Option value="Pharmacy_and_Healthcare">Pharmacy & Healthcare</Option>
              </Select>
            </Col>
            <Col xs={24} sm={12} md={4} lg={3}>
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
                className="custom-select"
              >
                <Option value="all">All Status</Option>
                <Option value="pending">Pending</Option>
                <Option value="approved">Approved</Option>
                <Option value="rejected">Rejected</Option>
                <Option value="in_progress">In Progress</Option>
              </Select>
            </Col>
            <Col xs={24} sm={12} md={4} lg={3}>
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
            <Col xs={24} sm={12} md={6} lg={6}>
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
                  borderColor: 'rgba(42, 44, 65, 0.2)',
                  height: '32px'
                }}
                placeholder={['Start date', 'End date']}
                size="small"
              />
            </Col>
            <Col xs={24} sm={24} md={6} lg={6} style={{ display: 'flex', justifyContent: 'flex-end', gap: '8px', alignItems: 'end !important' }}>
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
                onClick={loadBusinesses}
                loading={loading}
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

        {/* Business Table/Grid View */}
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
                  {selectedRowKeys.length} business{selectedRowKeys.length > 1 ? 'es' : ''} selected
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

            <Table
              columns={columns}
              dataSource={paginatedBusinesses}
              rowKey={(row) => row?.application_id || row?.id}
              loading={loading}
              rowSelection={rowSelection}
              pagination={false}
              style={{
                borderRadius: '12px'
              }}
              scroll={{ x: 1000 }}
            />
          </Card>
        ) : (
          /* Grid View */
          <div>
            {loading ? (
              <div style={{ textAlign: 'center', padding: '40px' }}>
                <span>Loading...</span>
              </div>
            ) : (
              <Row gutter={[16, 16]}>
                {paginatedBusinesses.map((business) => {
                  const raw = String(business.rawStatus || '').toLowerCase();
                  const statusGroup = (
                    raw === 'approved' ? 'approved' :
                      raw === 'rejected' ? 'rejected' :
                        (raw === 'pending' || raw === 'submitted' || raw === 'under_review' || raw === 'under review') ? 'pending' :
                          (raw === 'in_progress' || raw === 'requires_changes' || raw === 'request_changes') ? 'in-progress' :
                            'pending'
                  );
                  const isRequiresChanges = raw === 'requires_changes' || raw === 'request_changes' || raw === 'changes_requested';
                  const showApprove = statusGroup === 'pending' || statusGroup === 'rejected' || isRequiresChanges;
                  const showReject = statusGroup === 'pending' || statusGroup === 'in-progress' || isRequiresChanges || statusGroup === 'approved';
                  const showPending = statusGroup === 'in-progress' || statusGroup === 'rejected' || isRequiresChanges;

                  const isRejected = business.status === 'Rejected';
                  const isReqChanges = business.status === 'Requires Changes';
                  const items = isRejected ? (business.rejection_reasons || []) : (isReqChanges ? (business.required_changes || []) : []);

                  let badgeStatus = 'processing';
                  let textColor = '#2A2C41';
                  let backgroundColor = 'rgba(42, 44, 65, 0.1)';

                  if (business.status === 'Approved') {
                    badgeStatus = 'success';
                    textColor = '#FDBF50';
                    backgroundColor = 'rgba(253, 191, 80, 0.1)';
                  } else if (business.status === 'Rejected') {
                    badgeStatus = 'error';
                    textColor = '#F55D00';
                    backgroundColor = 'rgba(245, 93, 0, 0.1)';
                  }

                  return (
                    <Col xs={24} sm={12} md={12} lg={6} xl={6} key={business.id}>
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
                        {/* Header: Business Name & Status */}
                        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '12px' }}>
                          <div style={{ flex: 1, minWidth: 0 }}>
                            <div style={{ fontWeight: '700', color: '#2A2C41', fontSize: '16px', marginBottom: '4px', lineHeight: '1.3' }}>
                              {business.businessName}
                            </div>
                            <div style={{ fontSize: '12px', color: '#6c757d', display: 'flex', alignItems: 'center', gap: '4px' }}>
                              <FiUser style={{ fontSize: '11px' }} />
                              {business.ownerName}
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
                              {business.status}
                            </span>
                          </div>
                        </div>

                        {/* Info Section */}
                        <div style={{ flex: 1, marginBottom: '12px' }}>
                          {/* Category */}
                          <div style={{ marginBottom: '8px' }}>
                            <Tag
                              color={getCategoryColor(business.category)}
                              style={{
                                borderRadius: '6px',
                                fontWeight: '500',
                                fontSize: '11px',
                                padding: '2px 10px',
                                margin: 0
                              }}
                            >
                              {getCategoryLabel(business.category)}
                            </Tag>
                          </div>

                          {/* Location */}
                          <div style={{ display: 'flex', alignItems: 'flex-start', gap: '6px', marginBottom: '6px' }}>
                            <FiMapPin style={{ color: '#6c757d', fontSize: '12px', marginTop: '2px', flex: '0 0 auto' }} />
                            <span style={{
                              fontSize: '12px',
                              color: '#2A2C41',
                              lineHeight: '1.4',
                              overflow: 'hidden',
                              textOverflow: 'ellipsis',
                              display: '-webkit-box',
                              WebkitLineClamp: 2,
                              WebkitBoxOrient: 'vertical'
                            }}>
                              {business.location}
                            </span>
                          </div>

                          {/* Submission Date */}
                          <div style={{ display: 'flex', alignItems: 'center', gap: '6px', marginBottom: '8px' }}>
                            <FiCalendar style={{ color: '#6c757d', fontSize: '12px' }} />
                            <span style={{ fontSize: '12px', color: '#2A2C41' }}>
                              {dayjs(business.submissionDate).format('MMM DD, YYYY')}
                            </span>
                          </div>

                          {/* Notes */}
                          {items && items.length > 0 && (
                            <div style={{ marginTop: '8px' }}>
                              <div style={{ fontSize: '10px', color: '#6c757d', marginBottom: '4px', fontWeight: '500' }}>
                                Notes:
                              </div>
                              <div style={{ display: 'flex', gap: '4px', flexWrap: 'wrap' }}>
                                {items.slice(0, 2).map((t, idx) => (
                                  <Tag key={idx} color={isRejected ? '#F55D00' : '#FDBF50'} style={{ borderRadius: '4px', fontSize: '9px', margin: 0, padding: '2px 6px' }}>
                                    {String(t)}
                                  </Tag>
                                ))}
                                {items.length > 2 && (
                                  <Tag style={{ borderRadius: '4px', fontSize: '9px', margin: 0, padding: '2px 6px' }}>+{items.length - 2}</Tag>
                                )}
                              </div>
                            </div>
                          )}
                        </div>

                        {/* Actions */}
                        <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap', marginTop: 'auto' }}>
                          <Button
                            icon={<FiEye />}
                            onClick={() => viewBusinessDetails(business)}
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
                          {showApprove && (
                            <Button
                              size="small"
                              icon={<FiCheckCircle />}
                              onClick={() => openDecision(business, 'approve')}
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
                          {showReject && (
                            <Button
                              size="small"
                              icon={<FiXCircle />}
                              onClick={() => openDecision(business, 'reject')}
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
                          )}
                          {showPending && (
                            <Button
                              size="small"
                              icon={<FiRefreshCw />}
                              onClick={() => openDecision(business, 'pending')}
                              style={{
                                color: '#2A2C41',
                                backgroundColor: '#f0f0f0',
                                borderColor: '#d9d9d9',
                                borderRadius: '6px',
                                fontWeight: '500',
                                height: '28px',
                                padding: '4px 8px',
                                fontSize: '11px',
                                flex: 1
                              }}
                            >
                              Pending
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

        {/* CSS for hiding scrollbar */}
        <style>
          {`
            .modal-content-scrollable::-webkit-scrollbar {
              display: none;
            }
          `}
        </style>

        {/* Business Detail Modal */}
        <Modal
          title={null}
          open={detailModalVisible}
          onCancel={() => setDetailModalVisible(false)}
          footer={null}
          width={900}
          centered
          styles={{
            body: { padding: 0 },
            content: { borderRadius: '20px', overflow: 'hidden', boxShadow: '0 20px 60px rgba(0, 0, 0, 0.15)' }
          }}
        >
          {selectedBusiness && (
            <div style={{ backgroundColor: '#ffffff', padding: '0 !important', height: '90vh', display: 'flex', flexDirection: 'column' }}>
              {/* Debug log */}
              {console.log('=== MODAL RENDER DEBUG ===', {
                businessName: selectedBusiness.businessName,
                status: selectedBusiness.status,
                rawStatus: selectedBusiness.rawStatus,
                statusType: typeof selectedBusiness.status,
                rawStatusType: typeof selectedBusiness.rawStatus
              })}
              {/* Modal Header */}
              <div style={{
                padding: '24px 32px',
                backgroundColor: '#2A2C41',
                position: 'sticky',
                top: 0,
                zIndex: 10,
                flexShrink: 0
              }}>
                <div style={{
                  display: 'flex',
                  justifyContent: 'space-between',
                  alignItems: 'center',
                  gap: '20px'
                }}>
                  {/* Left Side - Store Name */}
                  <div>
                    <h2 style={{
                      margin: '0',
                      fontSize: '28px',
                      fontWeight: '700',
                      color: '#ffffff',
                      letterSpacing: '-0.025em'
                    }}>
                      {selectedBusiness.businessName}
                    </h2>
                  </div>

                  {/* Right Side - Owner & Category */}
                  <div style={{
                    textAlign: 'right', marginRight: '15px',
                  }}>
                    <p style={{
                      margin: '0 0 8px 0',
                      fontSize: '16px',
                      color: '#ffffff',
                      fontWeight: '500',
                      opacity: 0.9
                    }}>
                      Owner: {selectedBusiness.ownerName}
                    </p>
                  </div>
                </div>
              </div>

              {/* Modal Content */}
              <div
                className="modal-content-scrollable"
                style={{
                  padding: '20px',
                  flex: 1,
                  overflowY: 'auto',
                  scrollbarWidth: 'none', /* Firefox */
                  msOverflowStyle: 'none', /* Internet Explorer 10+ */
                }}
              >
                {/* Reasons / Changes Banner */}
                {selectedBusiness && (
                  (() => {
                    const isRejected = selectedBusiness.status === 'Rejected';
                    const isReqChanges = selectedBusiness.status === 'Requires Changes';
                    const hasReasons = Array.isArray(selectedBusiness.rejection_reasons) && selectedBusiness.rejection_reasons.length > 0;
                    const hasChanges = Array.isArray(selectedBusiness.required_changes) && selectedBusiness.required_changes.length > 0;
                    const hasComments = typeof selectedBusiness.comments === 'string' && selectedBusiness.comments.trim();
                    if (!isRejected && !isReqChanges && !hasComments) return null;
                    return (
                      <div style={{
                        backgroundColor: isRejected ? 'rgba(245, 93, 0, 0.08)' : 'rgba(253, 191, 80, 0.12)',
                        border: `1px solid ${isRejected ? '#F55D00' : '#FDBF50'}`,
                        borderRadius: '12px',
                        padding: '16px',
                        marginBottom: '20px'
                      }}>
                        {hasComments && (
                          <div style={{ marginBottom: (hasReasons || hasChanges) ? '8px' : 0 }}>
                            <div style={{ fontWeight: 600, color: '#2A2C41', marginBottom: '6px' }}>Admin Comments</div>
                            <div style={{ color: '#2A2C41' }}>{selectedBusiness.comments}</div>
                          </div>
                        )}
                        {isRejected && hasReasons && (
                          <div>
                            <div style={{ fontWeight: 600, color: '#2A2C41', marginBottom: '6px' }}>Rejection Reasons</div>
                            <div style={{ display: 'flex', flexWrap: 'wrap', gap: '8px' }}>
                              {selectedBusiness.rejection_reasons.map((r, idx) => (
                                <Tag key={idx} color="#F55D00" style={{ borderRadius: '8px' }}>
                                  {String(r)}
                                </Tag>
                              ))}
                            </div>
                          </div>
                        )}
                        {isReqChanges && hasChanges && (
                          <div>
                            <div style={{ fontWeight: 600, color: '#2A2C41', marginBottom: '6px' }}>Required Changes</div>
                            <div style={{ display: 'flex', flexWrap: 'wrap', gap: '8px' }}>
                              {selectedBusiness.required_changes.map((c, idx) => (
                                <Tag key={idx} color="#FDBF50" style={{ borderRadius: '8px' }}>
                                  {String(c)}
                                </Tag>
                              ))}
                            </div>
                          </div>
                        )}
                      </div>
                    );
                  })()
                )}
                {/* First Row - Contact Information and Registration Details */}
                <Row gutter={[16, 16]} style={{ marginBottom: '16px' }}>
                  {/* Contact Information */}
                  <Col xs={24} md={12}>
                    <div style={{
                      backgroundColor: 'white',
                      borderRadius: '8px',
                      padding: '12px',
                      border: '1px solid rgba(0, 0, 0, 0.08)',
                      height: '100%',
                      boxShadow: '0 2px 4px rgba(0, 0, 0, 0.04)'
                    }}>
                      <h4 style={{
                        margin: '0 0 10px 0',
                        fontSize: '14px',
                        fontWeight: '600',
                        color: '#1f2937',
                        display: 'flex',
                        alignItems: 'center',
                        gap: '6px'
                      }}>
                        <FiPhone style={{ fontSize: '14px', color: '#F55D00' }} />
                        Contact Information
                      </h4>
                      <div style={{ space: '12px' }}>
                        <div style={{
                          display: 'flex',
                          alignItems: 'center',
                          gap: '6px',
                          marginBottom: '6px',
                          fontSize: '12px',
                          color: '#374151'
                        }}>
                          <span style={{ fontWeight: '500', color: '#6b7280', minWidth: '45px', fontSize: '11px' }}>Phone:</span>
                          <span>{selectedBusiness.phone}</span>
                        </div>
                        <div style={{
                          display: 'flex',
                          alignItems: 'center',
                          gap: '6px',
                          fontSize: '12px',
                          color: '#374151'
                        }}>
                          <span style={{ fontWeight: '500', color: '#6b7280', minWidth: '45px', fontSize: '11px' }}>Email:</span>
                          <span>{selectedBusiness.email}</span>
                        </div>
                      </div>
                    </div>
                  </Col>

                  {/* Registration Details */}
                  <Col xs={24} md={12}>
                    <div style={{
                      backgroundColor: 'white',
                      borderRadius: '8px',
                      padding: '12px',
                      border: '1px solid rgba(0, 0, 0, 0.08)',
                      height: '100%',
                      boxShadow: '0 2px 4px rgba(0, 0, 0, 0.04)'
                    }}>
                      <h4 style={{
                        margin: '0 0 10px 0',
                        fontSize: '14px',
                        fontWeight: '600',
                        color: '#1f2937',
                        display: 'flex',
                        alignItems: 'center',
                        gap: '6px'
                      }}>
                        <FiClipboard style={{ fontSize: '14px', color: '#F55D00' }} />
                        Registration Details
                      </h4>
                      <div style={{ space: '12px' }}>
                        <div style={{
                          display: 'flex',
                          alignItems: 'center',
                          gap: '6px',
                          marginBottom: '6px',
                          fontSize: '12px',
                          color: '#374151'
                        }}>
                          <span style={{ fontWeight: '500', color: '#6b7280', minWidth: '55px', fontSize: '11px' }}>Number:</span>
                          <span>{selectedBusiness.registrationNumber}</span>
                        </div>
                        <div style={{
                          display: 'flex',
                          alignItems: 'center',
                          gap: '6px',
                          fontSize: '12px',
                          color: '#374151'
                        }}>
                          <span style={{ fontWeight: '500', color: '#6b7280', minWidth: '55px', fontSize: '11px' }}>Submitted:</span>
                          <span>{dayjs(selectedBusiness.submissionDate).format('MMM DD, YYYY')}</span>
                        </div>
                      </div>
                    </div>
                  </Col>
                </Row>

                {/* Second Row - Business Operations and Business Info */}
                <Row gutter={[16, 16]}>
                  {/* Business Operations */}
                  <Col xs={24} md={12}>
                    <div style={{
                      backgroundColor: 'white',
                      borderRadius: '8px',
                      padding: '12px',
                      border: '1px solid rgba(0, 0, 0, 0.08)',
                      height: '100%',
                      boxShadow: '0 2px 4px rgba(0, 0, 0, 0.04)'
                    }}>
                      <h4 style={{
                        margin: '0 0 10px 0',
                        fontSize: '14px',
                        fontWeight: '600',
                        color: '#1f2937',
                        display: 'flex',
                        alignItems: 'center',
                        gap: '6px'
                      }}>
                        <FiSettings style={{ fontSize: '14px', color: '#F55D00' }} />
                        Business Operations
                      </h4>
                      <div style={{ space: '12px' }}>
                        <div style={{
                          display: 'flex',
                          alignItems: 'center',
                          gap: '6px',
                          marginBottom: '6px',
                          fontSize: '12px',
                          color: '#374151'
                        }}>
                          <span style={{ fontWeight: '500', color: '#6b7280', minWidth: '80px', fontSize: '11px' }}>Working Hours:</span>
                          <span>{formatWorkingHours(selectedBusiness.workingHours)}</span>
                        </div>
                        <div style={{
                          display: 'flex',
                          alignItems: 'center',
                          gap: '6px',
                          marginBottom: '6px',
                          fontSize: '12px',
                          color: '#374151'
                        }}>
                          <span style={{ fontWeight: '500', color: '#6b7280', minWidth: '80px', fontSize: '11px' }}>Payment Modes:</span>
                          <span>{formatPaymentModes(selectedBusiness.paymentModes)}</span>
                        </div>
                        <div style={{
                          display: 'flex',
                          alignItems: 'center',
                          gap: '6px',
                          fontSize: '12px',
                          color: '#374151'
                        }}>
                          <span style={{ fontWeight: '500', color: '#6b7280', minWidth: '80px', fontSize: '11px' }}>Delivery:</span>
                          <span>{formatDeliveryPreferences(selectedBusiness.deliveryPreferences)}</span>
                        </div>
                      </div>
                    </div>
                  </Col>

                  {/* Business Info */}
                  <Col xs={24} md={12}>
                    <div style={{
                      backgroundColor: 'white',
                      borderRadius: '8px',
                      padding: '12px',
                      border: '1px solid rgba(0, 0, 0, 0.08)',
                      height: '100%',
                      boxShadow: '0 2px 4px rgba(0, 0, 0, 0.04)'
                    }}>
                      <h4 style={{
                        margin: '0 0 10px 0',
                        fontSize: '14px',
                        fontWeight: '600',
                        color: '#1f2937',
                        display: 'flex',
                        alignItems: 'center',
                        gap: '6px'
                      }}>
                        <FiMapPin style={{ fontSize: '14px', color: '#F55D00' }} />
                        Business Info
                      </h4>
                      <div style={{ space: '12px' }}>
                        <div style={{
                          display: 'flex',
                          alignItems: 'center',
                          gap: '6px',
                          fontSize: '12px',
                          color: '#374151'
                        }}>
                          <span style={{ fontWeight: '500', color: '#6b7280', minWidth: '55px', fontSize: '11px' }}>Location:</span>
                          <span>{selectedBusiness.location}</span>
                        </div>
                      </div>
                    </div>
                  </Col>

                  {/* Documents */}
                  <Col span={24}>
                    <div style={{
                      backgroundColor: '#F4F4F8',
                      borderRadius: '16px',
                      padding: '20px',
                      border: '1px solid rgba(42, 44, 65, 0.1)'
                    }}>
                      <h4 style={{
                        margin: '0 0 16px 0',
                        fontSize: '16px',
                        fontWeight: '600',
                        color: '#2A2C41',
                        display: 'flex',
                        alignItems: 'center',
                        gap: '8px'
                      }}>
                        <FiFile style={{ fontSize: '18px', color: '#2A2C41' }} />
                        Submitted Documents ({selectedBusiness.documents.length})
                      </h4>
                      <div style={{
                        display: 'grid',
                        gridTemplateColumns: 'repeat(auto-fill, minmax(200px, 1fr))',
                        gap: '12px'
                      }}>
                        {selectedBusiness.documents.map((doc, index) => {
                          const label = typeof doc === 'string' ? doc : (doc.name || doc.type || 'Document');
                          return (
                            <div
                              key={index}
                              onClick={() => openDocument(doc)}
                              style={{
                                padding: '12px 16px',
                                backgroundColor: '#ffffff',
                                borderRadius: '12px',
                                border: '1px solid rgba(42, 44, 65, 0.1)',
                                cursor: 'pointer',
                                transition: 'all 0.2s ease',
                                display: 'flex',
                                alignItems: 'center',
                                gap: '8px',
                                fontSize: '13px',
                                fontWeight: '500',
                                color: '#2A2C41'
                              }}
                              onMouseEnter={(e) => {
                                e.currentTarget.style.borderColor = '#F55D00';
                                e.currentTarget.style.backgroundColor = '#F4F4F8';
                              }}
                              onMouseLeave={(e) => {
                                e.currentTarget.style.borderColor = 'rgba(42, 44, 65, 0.1)';
                                e.currentTarget.style.backgroundColor = '#ffffff';
                              }}
                            >
                              <FiPaperclip style={{ fontSize: '16px', color: '#2A2C41' }} />
                              <span style={{
                                overflow: 'hidden',
                                textOverflow: 'ellipsis',
                                whiteSpace: 'nowrap'
                              }}>
                                {label}
                              </span>
                            </div>
                          );
                        })}
                      </div>
                    </div>
                  </Col>
                </Row>
              </div>

              {/* Modal Actions */}
              <div style={{
                padding: '24px 32px',
                backgroundColor: '#F4F4F8',
                borderTop: '1px solid rgba(42, 44, 65, 0.1)',
                display: 'flex',
                justifyContent: 'space-between',
                alignItems: 'center',
                position: 'sticky',
                bottom: 0,
                zIndex: 10,
                flexShrink: 0
              }}>
                <Button
                  onClick={() => setDetailModalVisible(false)}
                  style={{
                    borderRadius: '12px',
                    borderColor: 'rgba(42, 44, 65, 0.2)',
                    color: '#2A2C41',
                    height: '40px',
                    padding: '0 20px',
                    fontWeight: '500'
                  }}
                >
                  Close
                </Button>
                <Space size={12}>
                  <Button
                    icon={<FiXCircle />}
                    onClick={() => openDecision(selectedBusiness, 'reject')}
                    style={{
                      borderRadius: '12px',
                      backgroundColor: 'rgba(245, 93, 0, 0.1)',
                      borderColor: '#F55D00',
                      color: '#F55D00',
                      height: '40px',
                      padding: '0 20px',
                      fontWeight: '500'
                    }}
                  >
                    Reject
                  </Button>
                  <Button
                    icon={<FiRefreshCw />}
                    onClick={() => openDecision(selectedBusiness, 'pending')}
                    style={{
                      borderRadius: '12px',
                      backgroundColor: '#F4F4F8',
                      borderColor: 'rgba(42, 44, 65, 0.2)',
                      color: '#2A2C41',
                      height: '40px',
                      padding: '0 20px',
                      fontWeight: '500'
                    }}
                  >
                    Mark Pending
                  </Button>
                  {/* Only show Approve button if business is NOT approved */}
                  {(() => {
                    const status = selectedBusiness?.status;
                    const rawStatus = selectedBusiness?.rawStatus;
                    const isApproved = 
                      status === 'Approved' || 
                      status === 'approved' ||
                      rawStatus === 'approved' ||
                      rawStatus === 'Approved' ||
                      (typeof status === 'string' && status.toLowerCase() === 'approved') ||
                      (typeof rawStatus === 'string' && rawStatus.toLowerCase() === 'approved');
                    
                    if (isApproved) {
                      return null; // Don't show Approve button for approved businesses
                    }
                    
                    return (
                      <Button
                        type="primary"
                        icon={<FiCheckCircle />}
                        onClick={() => openDecision(selectedBusiness, 'approve')}
                        style={{
                          borderRadius: '12px',
                          backgroundColor: '#FDBF50',
                          borderColor: '#FDBF50',
                          height: '40px',
                          padding: '0 20px',
                          fontWeight: '500',
                          boxShadow: '0 4px 12px rgba(253, 191, 80, 0.3)'
                        }}
                      >
                        Approve
                      </Button>
                    );
                  })()}
                </Space>
              </div>
            </div>
          )}
        </Modal>
        {/* Decision Modal */}
        <Modal
          title={decisionAction === 'approve' ? 'Approve Business' : decisionAction === 'reject' ? 'Reject Business' : 'Request Changes'}
          open={decisionModalVisible}
          onCancel={() => setDecisionModalVisible(false)}
          onOk={async () => { await submitDecision(); setDetailModalVisible(false); }}
          okText={decisionAction === 'approve' ? 'Approve' : decisionAction === 'reject' ? 'Reject' : 'Save'}
          className={decisionAction === 'approve' ? 'approve-modal-modern' : decisionAction === 'reject' ? 'reject-modal-modern' : 'pending-modal-modern'}
          width={600}
        >
          <div className="reject-form-section">
            <label className="reject-form-label optional">Comments (optional)</label>
            <textarea
              className="reject-textarea"
              rows={3}
              value={decisionComments}
              onChange={(e) => setDecisionComments(e.target.value)}
              placeholder="Add comments for the owner..."
            />
          </div>

          {decisionAction === 'reject' && (
            <div>
              <label className="reject-form-label">Rejection Reasons</label>
              <Select
                mode="multiple"
                className="reject-select"
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
                className="reject-select"
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

          {decisionAction === 'pending' && (
            <div>
              <label className="reject-form-label">Required Changes</label>
              <Select
                mode="multiple"
                className="reject-select"
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
                className="reject-select"
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
        </Modal>
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
            const docName = selectedDocument?.name || selectedDocument?.file_name || 'Document';

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
      </div>
    </div>
  );
};

export default PendingBusinessDashboard;