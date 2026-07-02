// Updated NotificationManagement.jsx with "Send to All Users" functionality

import React, { useState, useEffect } from 'react';
import { Card, Row, Col, Button, Table, Modal, Form, Select, Input, Upload, message, Space, Checkbox, Tooltip, Tabs } from 'antd';
import { PlusOutlined, SendOutlined, UploadOutlined, SearchOutlined } from '@ant-design/icons';
import UserSelectionModal from './UserSelectionModal';
import BusinessSelectionModal from './BusinessSelectionModal';
import '../../css/admin/NotificationManagement.css';

const { TabPane } = Tabs;

const BASE_URL = import.meta.env.VITE_BASE_URL || 'https://kirazee.com/kirazee';

const NotificationManagement = () => {
    const [statistics, setStatistics] = useState({});
    const [campaigns, setCampaigns] = useState([]);
    const [users, setUsers] = useState([]);
    const [businesses, setBusinesses] = useState([]);
    const [userModes, setUserModes] = useState([]);
    const [createModalVisible, setCreateModalVisible] = useState(false);
    const [userSelectionVisible, setUserSelectionVisible] = useState(false);
    const [businessSelectionVisible, setBusinessSelectionVisible] = useState(false);
    const [selectedUsers, setSelectedUsers] = useState([]);
    const [selectedBusinesses, setSelectedBusinesses] = useState([]);
    const [uploadedMedia, setUploadedMedia] = useState(null);
    const [loading, setLoading] = useState(false);
    const [sendToAllUsers, setSendToAllUsers] = useState(false); // NEW STATE
    const [selectedCampaign, setSelectedCampaign] = useState(null);
    const [campaignDetailsVisible, setCampaignDetailsVisible] = useState(false);
    const [form] = Form.useForm();

    // Fetch data on component mount
    useEffect(() => {
        fetchStatistics();
        fetchCampaigns();
        fetchUsers();
        fetchBusinesses();
        fetchUserModes();
    }, []);

    const fetchStatistics = async () => {
        try {
            const response = await fetch(`${BASE_URL}/api/notifications/statistics/`);
            const data = await response.json();
            if (data.success) {
                setStatistics(data.statistics);
            }
        } catch (error) {
            message.error('Failed to fetch statistics');
        }
    };

    const fetchCampaigns = async () => {
        try {
            const response = await fetch(`${BASE_URL}/api/notifications/superadmin/campaigns/`);
            const data = await response.json();
            if (data.success) {
                setCampaigns(data.campaigns || []);
            }
        } catch (error) {
            message.error('Failed to fetch campaigns');
        }
    };

    const fetchUsers = async (search = '', userMode = '') => {
        try {
            const params = new URLSearchParams({ search, user_mode: userMode });
            const response = await fetch(`${BASE_URL}/api/notifications/users/?${params}`);
            const data = await response.json();
            if (data.success) {
                setUsers(data.users);
            }
        } catch (error) {
            message.error('Failed to fetch users');
        }
    };

    const fetchBusinesses = async (search = '') => {
        try {
            const params = new URLSearchParams({ search });
            const response = await fetch(`${BASE_URL}/api/notifications/businesses/?${params}`);
            const data = await response.json();
            if (data.success) {
                setBusinesses(data.businesses);
            }
        } catch (error) {
            message.error('Failed to fetch businesses');
        }
    };

    const fetchUserModes = async () => {
        try {
            const response = await fetch(`${BASE_URL}/api/notifications/user-modes/`);
            const data = await response.json();
            if (data.success) {
                setUserModes(data.user_modes);
            }
        } catch (error) {
            message.error('Failed to fetch user modes');
        }
    };

    const handleMediaUpload = async (file) => {
        const formData = new FormData();
        formData.append('media_file', file);
        formData.append('media_type', file.type.startsWith('image/') ? 'image' : 
                                    file.type.startsWith('video/') ? 'video' : 
                                    file.type.includes('pdf') ? 'document' : 'audio');

        try {
            const response = await fetch(`${BASE_URL}/api/notifications/media/upload/`, {
                method: 'POST',
                body: formData
            });
            const data = await response.json();
            if (data.success) {
                setUploadedMedia({
                    url: data.media_url,
                    type: data.media_type,
                    original_filename: data.original_filename
                });
                message.success('Media uploaded successfully');
                return false; // Prevent default upload behavior
            }
        } catch (error) {
            message.error('Failed to upload media');
        }
        return false;
    };

    const handleCreateCampaign = async (values) => {
        setLoading(true);
        try {
            const payload = {
                ...values,
                media_url: uploadedMedia?.url,
                media_type: uploadedMedia?.type,
                target_all_users: sendToAllUsers, // KEY CHANGE: Use the checkbox state
                target_user_ids: sendToAllUsers ? [] : selectedUsers.map(u => u.id),
                target_business_ids: sendToAllUsers ? [] : selectedBusinesses.map(b => b.id),
                target_user_modes: sendToAllUsers ? [] : selectedUsers.map(u => u.user_mode).filter((v, i, a) => a.indexOf(v) === i),
                created_by: 1 // Replace with actual admin ID
            };

            const response = await fetch(`${BASE_URL}/api/notifications/superadmin/campaigns/create/`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload)
            });

            const data = await response.json();
            if (data.success) {
                message.success('Campaign created and sent successfully');
                setCreateModalVisible(false);
                form.resetFields();
                setSelectedUsers([]);
                setSelectedBusinesses([]);
                setUploadedMedia(null);
                setSendToAllUsers(false); // Reset the checkbox
                fetchCampaigns();
                fetchStatistics();
            } else {
                message.error(data.error || 'Failed to create campaign');
            }
        } catch (error) {
            message.error('Failed to create campaign');
        }
        setLoading(false);
    };

    // Statistics Cards
    const StatisticsCards = () => (
        <div className="stats-grid-modern">
            <div className="stat-card-modern stat-blue">
                <div className="stat-value">{statistics.total_campaigns || 0}</div>
                <div className="stat-label">Total Campaigns</div>
            </div>
            <div className="stat-card-modern stat-green">
                <div className="stat-value">{statistics.total_recipients || 0}</div>
                <div className="stat-label">Total Recipients</div>
                <div className="stat-sublabel">Across all campaigns</div>
            </div>
            <div className="stat-card-modern stat-orange">
                <div className="stat-value">{statistics.delivery_statistics?.total_sent || 0}</div>
                <div className="stat-label">Successfully Sent</div>
                <div className="stat-sublabel">
                    {statistics.total_recipients > 0 
                        ? `${((statistics.delivery_statistics?.total_sent || 0) / statistics.total_recipients * 100).toFixed(1)}%` 
                        : '0%'
                    }
                </div>
            </div>
            <div className="stat-card-modern stat-red">
                <div className="stat-value">{statistics.delivery_statistics?.total_failed || 0}</div>
                <div className="stat-label">Failed</div>
                <div className="stat-sublabel">
                    {statistics.total_recipients > 0 
                        ? `${((statistics.delivery_statistics?.total_failed || 0) / statistics.total_recipients * 100).toFixed(1)}%` 
                        : '0%'
                    }
                </div>
            </div>
        </div>
    );

    // Handle campaign row click
    const handleCampaignClick = (campaign) => {
        setSelectedCampaign(campaign);
        setCampaignDetailsVisible(true);
    };

    // Campaigns Table
    const CampaignsTable = () => {
        const columns = [
            { 
                title: 'Campaign', 
                dataIndex: 'campaign_name', 
                key: 'campaign_name',
                width: '18%'
            },
            { 
                title: 'Type', 
                dataIndex: 'campaign_type', 
                key: 'campaign_type',
                width: '10%',
                render: (type) => (
                    <span className="type-tag-modern">
                        {type?.replace('_', ' ').toUpperCase() || type}
                    </span>
                )
            },
            { 
                title: 'Targeting', 
                key: 'targeting',
                width: '15%',
                render: (_, record) => {
                    if (record.target_all_users) {
                        return <span className="target-badge all-users">🌐 All Users</span>;
                    }
                    const parts = [];
                    if (record.target_user_ids?.length > 0) {
                        parts.push(`${record.target_user_ids.length} Users`);
                    }
                    if (record.target_business_ids?.length > 0) {
                        parts.push(`${record.target_business_ids.length} Businesses`);
                    }
                    if (record.target_user_modes?.length > 0) {
                        parts.push(record.target_user_modes.join(', '));
                    }
                    return <span className="target-badge specific">{parts.join(' | ') || 'None'}</span>;
                }
            },
            { 
                title: 'Title', 
                dataIndex: 'title', 
                key: 'title',
                width: '20%',
                ellipsis: true
            },
            { 
                title: 'Status', 
                dataIndex: 'status', 
                key: 'status',
                width: '10%',
                render: (status) => (
                    <span className={`status-badge-modern status-${status}`}>
                        {status?.toUpperCase() || 'UNKNOWN'}
                    </span>
                )
            },
            { 
                title: 'Delivery', 
                key: 'delivery',
                width: '12%',
                align: 'center',
                render: (_, record) => {
                    const stats = record.statistics || {};
                    const sent = stats.total_sent || 0;
                    const failed = stats.total_failed || 0;
                    const total = sent + failed;
                    
                    return (
                        <div className="delivery-stats">
                            <span className="sent-count">{sent}</span>
                            <span className="divider">/</span>
                            <span className="failed-count">{failed}</span>
                            <Tooltip title={`Sent: ${sent}, Failed: ${failed}`}>
                                <span className="total-count">({total})</span>
                            </Tooltip>
                        </div>
                    );
                }
            },
            { 
                title: 'Created', 
                dataIndex: 'created_at', 
                key: 'created_at',
                width: '12%',
                render: (date) => date ? new Date(date).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' }) : 'N/A'
            },
        ];

        return (
            <Table
                className="campaigns-table-modern"
                columns={columns}
                dataSource={campaigns}
                rowKey="id"
                onRow={(record) => ({
                    onClick: () => handleCampaignClick(record),
                    style: { cursor: 'pointer' }
                })}
                pagination={{ 
                    pageSize: 15,
                    showSizeChanger: false,
                    showTotal: (total) => `${total} campaigns`
                }}
                scroll={{ x: 800 }}
            />
        );
    };

    // Create Campaign Modal
    const CreateCampaignModal = () => (
        <Modal
            title="Create Notification Campaign"
            open={createModalVisible}
            onCancel={() => {
                setCreateModalVisible(false);
                form.resetFields();
                setSelectedUsers([]);
                setSelectedBusinesses([]);
                setUploadedMedia(null);
                setSendToAllUsers(false);
            }}
            footer={null}
            width={600}
            className="notification-modal-wrapper"
        >
            <Form form={form} onFinish={handleCreateCampaign} layout="vertical" className="notification-form-clean">
                <Row gutter={10}>
                    <Col span={14}>
                        <Form.Item name="campaign_name" label="Campaign Name" rules={[{ required: true, message: 'Required' }]} className="form-field-compact">
                            <Input placeholder="Campaign name" className="input-clean" />
                        </Form.Item>
                    </Col>
                    <Col span={10}>
                        <Form.Item name="campaign_type" label="Type" rules={[{ required: true, message: 'Required' }]} className="form-field-compact">
                            <Select placeholder="Select" className="select-clean">
                                <Select.Option value="business_offer">Offer</Select.Option>
                                <Select.Option value="system_update">Update</Select.Option>
                                <Select.Option value="user_targeted">Targeted</Select.Option>
                                <Select.Option value="general">General</Select.Option>
                            </Select>
                        </Form.Item>
                    </Col>
                </Row>

                <Form.Item name="title" label="Title" rules={[{ required: true, message: 'Required' }]} className="form-field-compact">
                    <Input placeholder="Notification title" className="input-clean" />
                </Form.Item>

                <Form.Item name="message" label="Message" rules={[{ required: true, message: 'Required' }]} className="form-field-compact">
                    <Input.TextArea rows={2} placeholder="Message content" className="textarea-clean" />
                </Form.Item>

                <Row gutter={10}>
                    <Col span={14}>
                        <Form.Item name="channels" label="Channel" initialValue="all" className="form-field-compact">
                            <Select className="select-clean">
                                <Select.Option value="all">All Channels</Select.Option>
                                <Select.Option value="firebase">App</Select.Option>
                                <Select.Option value="email">Email</Select.Option>
                            </Select>
                        </Form.Item>
                    </Col>
                    <Col span={10}>
                        <Form.Item label="Media" className="form-field-compact">
                            <Upload
                                beforeUpload={handleMediaUpload}
                                showUploadList={false}
                                accept="image/*,video/*,.pdf"
                            >
                                <Button icon={<UploadOutlined />} block className="upload-btn-clean">
                                    {uploadedMedia ? '✓ File' : 'Upload'}
                                </Button>
                            </Upload>
                        </Form.Item>
                    </Col>
                </Row>

                <div className="audience-box-clean">
                    <div className="audience-header">
                        <Checkbox
                            checked={sendToAllUsers}
                            onChange={(e) => setSendToAllUsers(e.target.checked)}
                            className="checkbox-clean"
                        >
                            Send to All Users
                        </Checkbox>
                        <span className="audience-info">
                            {sendToAllUsers 
                                ? `Will reach ${statistics.active_users || 0} active users` 
                                : 'Select specific users/businesses'
                            }
                        </span>
                    </div>
                    
                    {!sendToAllUsers && (
                        <div className="selection-grid">
                            <Button 
                                onClick={() => setUserSelectionVisible(true)}
                                className="selection-btn-clean"
                                disabled={sendToAllUsers}
                            >
                                👥 Users ({selectedUsers.length})
                            </Button>
                            <Button 
                                onClick={() => setBusinessSelectionVisible(true)}
                                className="selection-btn-clean"
                                disabled={sendToAllUsers}
                            >
                                🏢 Businesses ({selectedBusinesses.length})
                            </Button>
                            <div className="selection-summary">
                                {selectedUsers.length + selectedBusinesses.length > 0 && (
                                    <span className="summary-text">
                                        Will reach {selectedUsers.length + selectedBusinesses.length} recipients
                                    </span>
                                )}
                            </div>
                        </div>
                    )}
                </div>

                <div className="modal-footer-clean">
                    <Button type="primary" htmlType="submit" loading={loading} icon={<SendOutlined />} className="btn-send-clean">
                        Create & Send
                    </Button>
                    <Button onClick={() => {
                        setCreateModalVisible(false);
                        form.resetFields();
                        setSelectedUsers([]);
                        setSelectedBusinesses([]);
                        setUploadedMedia(null);
                        setSendToAllUsers(false);
                    }} className="btn-cancel-clean">
                        Cancel
                    </Button>
                </div>
            </Form>
        </Modal>
    );

    // Enhanced Campaign Details Modal with detailed analytics
    const CampaignDetailsModal = () => {
        const [detailedStats, setDetailedStats] = useState(null);
        const [recipients, setRecipients] = useState([]);
        const [loading, setLoading] = useState(false);
        const [activeTab, setActiveTab] = useState('overview');
        const [filters, setFilters] = useState({ status: '', channel: '' });
        const [pagination, setPagination] = useState({ current: 1, pageSize: 50, total: 0 });

        useEffect(() => {
            if (selectedCampaign && campaignDetailsVisible) {
                fetchDetailedStats();
                fetchRecipients();
            }
        }, [selectedCampaign, campaignDetailsVisible, filters, pagination.current]);

        const fetchDetailedStats = async () => {
            try {
                setLoading(true);
                const response = await fetch(`${BASE_URL}/api/notifications/campaigns/${selectedCampaign.id}/detailed-stats/`);
                const data = await response.json();
                if (data.success) {
                    setDetailedStats(data.data);
                }
            } catch (error) {
                message.error('Failed to fetch campaign details');
            } finally {
                setLoading(false);
            }
        };

        const fetchRecipients = async () => {
            try {
                const params = new URLSearchParams({
                    page: pagination.current,
                    per_page: pagination.pageSize,
                    ...(filters.status && { status: filters.status }),
                    ...(filters.channel && { channel: filters.channel })
                });
                
                const response = await fetch(`${BASE_URL}/api/notifications/campaigns/${selectedCampaign.id}/recipients/?${params}`);
                const data = await response.json();
                if (data.success) {
                    setRecipients(data.recipients);
                    setPagination(prev => ({ ...prev, total: data.pagination.total_count }));
                }
            } catch (error) {
                message.error('Failed to fetch recipients');
            }
        };

        const handleRetry = async (userIds = null, channels = 'all') => {
            try {
                const response = await fetch(`${BASE_URL}/api/notifications/campaigns/${selectedCampaign.id}/retry/`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ user_ids: userIds, channels })
                });
                const data = await response.json();
                if (data.success) {
                    message.success(data.message);
                    fetchDetailedStats();
                    fetchRecipients();
                } else {
                    message.error(data.message);
                }
            } catch (error) {
                message.error('Failed to retry notifications');
            }
        };

        const handleExport = async (format = 'csv') => {
            try {
                const params = new URLSearchParams({
                    format,
                    ...(filters.status && { status: filters.status }),
                    ...(filters.channel && { channel: filters.channel })
                });
                
                const response = await fetch(`${BASE_URL}/api/notifications/campaigns/${selectedCampaign.id}/export/?${params}`);
                if (format === 'csv') {
                    const blob = await response.blob();
                    const url = window.URL.createObjectURL(blob);
                    const a = document.createElement('a');
                    a.href = url;
                    a.download = `${selectedCampaign.campaign_name}_recipients.csv`;
                    a.click();
                    window.URL.revokeObjectURL(url);
                } else {
                    const data = await response.json();
                    const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' });
                    const url = window.URL.createObjectURL(blob);
                    const a = document.createElement('a');
                    a.href = url;
                    a.download = `${selectedCampaign.campaign_name}_recipients.json`;
                    a.click();
                    window.URL.revokeObjectURL(url);
                }
            } catch (error) {
                message.error('Failed to export data');
            }
        };

        if (!selectedCampaign) return null;

        const stats = detailedStats?.delivery_statistics || {};
        const recipientBreakdown = detailedStats?.recipient_breakdown || {};
        const { Option } = Select;

        return (
            <Modal
                title={
                    <div className="modal-title-with-actions">
                        <span>Campaign Details: {selectedCampaign.campaign_name}</span>
                        <div className="modal-actions">
                            <Button onClick={() => handleExport('csv')} size="small">
                                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" style={{marginRight: 4}}>
                                    <path d="M21 15V19A2 2 0 0 1 19 21H5A2 2 0 0 1 3 19V15"/>
                                    <polyline points="7,10 12,15 17,10"/>
                                    <line x1="12" y1="15" x2="12" y2="3"/>
                                </svg>
                                Export CSV
                            </Button>
                            <Button onClick={() => handleExport('json')} size="small">
                                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" style={{marginRight: 4}}>
                                    <path d="M14 2H6A2 2 0 0 0 4 4V20A2 2 0 0 0 6 22H18A2 2 0 0 0 20 20V8L14 2Z"/>
                                    <polyline points="14,2 14,8 20,8"/>
                                    <line x1="16" y1="13" x2="8" y2="13"/>
                                    <line x1="16" y1="17" x2="8" y2="17"/>
                                    <polyline points="10,9 9,9 8,9"/>
                                </svg>
                                Export JSON
                            </Button>
                        </div>
                    </div>
                }
                open={campaignDetailsVisible}
                onCancel={() => {
                    setCampaignDetailsVisible(false);
                    setSelectedCampaign(null);
                    setDetailedStats(null);
                    setRecipients([]);
                    setActiveTab('overview');
                }}
                footer={null}
                width={1000}
                className="notification-modal-wrapper"
            >
                <Tabs activeKey={activeTab} onChange={setActiveTab}>
                    {/* Overview Tab */}
                    <TabPane tab={
                        <span>
                            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" style={{marginRight: 4}}>
                                <path d="M21 21H3V3H21V21Z"/>
                                <path d="M9 9H6V12H9V9Z"/>
                                <path d="M15 9H12V12H15V9Z"/>
                                <path d="M9 15H6V18H9V15Z"/>
                                <path d="M15 15H12V18H15V15Z"/>
                            </svg>
                            Overview
                        </span>
                    } key="overview">
                        <div className="campaign-overview-content">
                            {/* Campaign Header */}
                            <div className="campaign-header-section">
                                <div className="campaign-title-row">
                                    <h3 className="campaign-title">{selectedCampaign.campaign_name}</h3>
                                    <span className={`status-badge-modern status-${selectedCampaign.status}`}>
                                        {selectedCampaign.status?.toUpperCase() || 'UNKNOWN'}
                                    </span>
                                </div>
                                <div className="campaign-meta">
                                    <span className="campaign-type">{selectedCampaign.campaign_type?.replace('_', ' ').toUpperCase()}</span>
                                    <span className="campaign-date">
                                        Created: {selectedCampaign.created_at ? new Date(selectedCampaign.created_at).toLocaleString() : 'N/A'}
                                    </span>
                                </div>
                            </div>

                            {/* Content Section */}
                            <div className="campaign-content-section">
                                <div className="content-item">
                                    <label className="content-label">Title</label>
                                    <div className="content-value">{selectedCampaign.title || 'N/A'}</div>
                                </div>
                                <div className="content-item">
                                    <label className="content-label">Message</label>
                                    <div className="content-value message-content">{selectedCampaign.message || 'N/A'}</div>
                                </div>
                                {selectedCampaign.channels && (
                                    <div className="content-item">
                                        <label className="content-label">Channels</label>
                                        <div className="content-value">
                                            {selectedCampaign.channels === 'all' ? 'All Channels' : selectedCampaign.channels}
                                        </div>
                                    </div>
                                )}
                                {selectedCampaign.media_url && (
                                    <div className="content-item">
                                        <label className="content-label">Media</label>
                                        <div className="content-value">
                                            <a href={selectedCampaign.media_url} target="_blank" rel="noopener noreferrer" className="media-link">
                                                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" style={{marginRight: 4}}>
                                                    <path d="M21.44 11.05L12.25 20.24C11.78 20.71 11.14 21 10.44 21H4A2 2 0 0 1 2 19V12.56C2 11.86 2.29 11.22 2.76 10.75L11.95 1.56C12.42 1.09 13.06 0.8 13.76 0.8C14.46 0.8 15.1 1.09 15.57 1.56L21.44 7.43C21.91 7.9 22.2 8.54 22.2 9.24C22.2 9.94 21.91 10.58 21.44 11.05Z"/>
                                                    <line x1="7" y1="17" x2="17" y2="7"/>
                                                </svg>
                                                {selectedCampaign.media_original_filename || 'View Attachment'}
                                            </a>
                                        </div>
                                    </div>
                                )}
                            </div>

                            {/* Enhanced Delivery Statistics */}
                            <div className="campaign-delivery-section">
                                <h4 className="section-title">Delivery Statistics</h4>
                                <div className="delivery-stats-table">
                                    <div className="stats-table">
                                        <div className="status-header pending">Pending</div>
                                        <div className="status-header failed">Failed</div>
                                        <div className="status-header sent">Sent</div>
                                        <div className="status-header total">Total</div>
                                        
                                        <div className="status-cell pending">
                                            <div className="stat-number">{selectedCampaign.total_recipients - (stats.overall?.total_sent || 0) - (stats.overall?.total_failed || 0)}</div>
                                            <div className="stat-percentage">
                                                {selectedCampaign.total_recipients && selectedCampaign.total_recipients > 0 
                                                    ? `${((selectedCampaign.total_recipients - (stats.overall?.total_sent || 0) - (stats.overall?.total_failed || 0)) / selectedCampaign.total_recipients * 100).toFixed(1)}%` 
                                                    : '0%'
                                                }
                                            </div>
                                        </div>
                                        <div className="status-cell failed">
                                            <div className="stat-number">{stats.overall?.total_failed || 0}</div>
                                            <div className="stat-percentage">
                                                {stats.overall?.total_sent && stats.overall?.total_failed && (stats.overall.total_sent + stats.overall.total_failed) > 0 
                                                    ? `${((stats.overall.total_failed / (stats.overall.total_sent + stats.overall.total_failed)) * 100).toFixed(1)}%` 
                                                    : '0%'
                                                }
                                            </div>
                                        </div>
                                        <div className="status-cell sent">
                                            <div className="stat-number">{stats.overall?.total_sent || 0}</div>
                                            <div className="stat-percentage">
                                                {stats.overall?.success_rate ? `${stats.overall.success_rate}%` : '0%'}
                                            </div>
                                        </div>
                                        <div className="status-cell total">
                                            <div className="stat-number">{selectedCampaign.total_recipients || 0}</div>
                                            <div className="stat-percentage">100%</div>
                                        </div>
                                    </div>
                                </div>

                                {/* Channel Breakdown */}
                                <div className="channel-breakdown">
                                    <h5>Channel Performance</h5>
                                    <div className="channel-table">
                                        <table className="channel-stats-table">
                                            <thead>
                                                <tr>
                                                    <th className="channel-header">Channel</th>
                                                    <th className="channel-header">Sent</th>
                                                    <th className="channel-header">Failed</th>
                                                    <th className="channel-header">Success Rate</th>
                                                </tr>
                                            </thead>
                                            <tbody>
                                                <tr className="channel-row">
                                                    <td className="channel-cell name">
                                                        <svg className="channel-icon" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                                                            <path d="M12 2L15.09 8.26L22 9.27L17 14.14L18.18 21.02L12 17.77L5.82 21.02L7 14.14L2 9.27L8.91 8.26L12 2Z"/>
                                                        </svg>
                                                        <span className="channel-name">Firebase</span>
                                                    </td>
                                                    <td className="channel-cell sent">{stats.firebase?.sent || 0}</td>
                                                    <td className="channel-cell failed">{stats.firebase?.failed || 0}</td>
                                                    <td className="channel-cell rate">{stats.firebase?.success_rate || 0}%</td>
                                                </tr>
                                                <tr className="channel-row">
                                                    <td className="channel-cell name">
                                                        <svg className="channel-icon" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                                                            <path d="M4 4h16c1.1 0 2 .9 2 2v12c0 1.1-.9 2-2 2H4c-1.1 0-2-.9-2-2V6c0-1.1.9-2 2-2z"/>
                                                            <polyline points="22,6 12,13 2,6"/>
                                                        </svg>
                                                        <span className="channel-name">Email</span>
                                                    </td>
                                                    <td className="channel-cell sent">{stats.email?.sent || 0}</td>
                                                    <td className="channel-cell failed">{stats.email?.failed || 0}</td>
                                                    <td className="channel-cell rate">{stats.email?.success_rate || 0}%</td>
                                                </tr>
                                                <tr className="channel-row">
                                                    <td className="channel-cell name">
                                                        <svg className="channel-icon" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                                                            <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/>
                                                            <line x1="8" y1="9" x2="16" y2="9"/>
                                                            <line x1="8" y1="13" x2="14" y2="13"/>
                                                        </svg>
                                                        <span className="channel-name">WhatsApp</span>
                                                    </td>
                                                    <td className="channel-cell sent">{stats.whatsapp?.sent || 0}</td>
                                                    <td className="channel-cell failed">{stats.whatsapp?.failed || 0}</td>
                                                    <td className="channel-cell rate">{stats.whatsapp?.success_rate || 0}%</td>
                                                </tr>
                                            </tbody>
                                        </table>
                                    </div>
                                </div>
                            </div>
                        </div>
                    </TabPane>

                    {/* Recipients Tab */}
                    <TabPane tab={
                        <span>
                            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" style={{marginRight: 4}}>
                                <path d="M17 21V19A4 4 0 0 0 13 15H5A4 4 0 0 0 1 19V21"/>
                                <circle cx="9" cy="7" r="4"/>
                                <path d="M23 21V19A4 4 0 0 0 19 15H18"/>
                                <circle cx="16" cy="7" r="3"/>
                            </svg>
                            Recipients
                        </span>
                    } key="recipients">
                        <div className="recipients-section">
                            {/* Filters */}
                            <div className="recipients-filters">
                                <Select
                                    placeholder="Filter by Status"
                                    allowClear
                                    value={filters.status || undefined}
                                    onChange={(value) => setFilters(prev => ({ ...prev, status: value || '' }))}
                                    style={{ width: 120, marginRight: 8 }}
                                >
                                    <Option value="sent">✅ Sent</Option>
                                    <Option value="failed">❌ Failed</Option>
                                    <Option value="pending">⏳ Pending</Option>
                                    <Option value="skipped">⏭️ Skipped</Option>
                                </Select>
                                
                                <Select
                                    placeholder="Filter by Channel"
                                    allowClear
                                    value={filters.channel || undefined}
                                    onChange={(value) => setFilters(prev => ({ ...prev, channel: value || '' }))}
                                    style={{ width: 120, marginRight: 8 }}
                                >
                                    <Option value="firebase">🔥 Firebase</Option>
                                    <Option value="email">📧 Email</Option>
                                    <Option value="whatsapp">💬 WhatsApp</Option>
                                </Select>

                                <Button onClick={() => handleRetry()} type="primary" size="small">
                                    🔄 Retry All Failed
                                </Button>
                            </div>

                            {/* Recipients Table */}
                            <Table
                                dataSource={recipients}
                                rowKey="user_id"
                                loading={loading}
                                pagination={{
                                    ...pagination,
                                    showSizeChanger: true,
                                    showTotal: (total) => `${total} recipients`,
                                    onChange: (page, pageSize) => {
                                        setPagination(prev => ({ ...prev, current: page, pageSize }));
                                    }
                                }}
                                columns={[
                                    {
                                        title: 'User',
                                        dataIndex: 'user_name',
                                        key: 'user_name',
                                        render: (name, record) => (
                                            <div className="user-info">
                                                <div className="user-name">{name}</div>
                                                <div className="user-email">{record.user_email}</div>
                                            </div>
                                        )
                                    },
                                    {
                                        title: 'Contact',
                                        key: 'contact',
                                        render: (_, record) => (
                                            <div className="contact-info">
                                                <div>{record.user_mobile}</div>
                                                <div className="user-mode">{record.user_mode}</div>
                                            </div>
                                        )
                                    },
                                    {
                                        title: 'Business',
                                        dataIndex: 'business_name',
                                        key: 'business_name'
                                    },
                                    {
                                        title: 'Status',
                                        dataIndex: 'status',
                                        key: 'status',
                                        render: (status) => (
                                            <span className={`status-badge status-${status}`}>
                                                {status?.toUpperCase()}
                                            </span>
                                        )
                                    },
                                    {
                                        title: 'Channel',
                                        dataIndex: 'channel',
                                        key: 'channel',
                                        render: (channel) => {
                                            const channelIcons = {
                                                firebase: '🔥',
                                                email: '📧',
                                                whatsapp: '💬',
                                                all: '📢'
                                            };
                                            return `${channelIcons[channel] || '📢'} ${channel?.toUpperCase()}`;
                                        }
                                    },
                                    {
                                        title: 'Error',
                                        dataIndex: 'error',
                                        key: 'error',
                                        render: (error) => error && (
                                            <Tooltip title={error}>
                                                <span className="error-message">⚠️ {error}</span>
                                            </Tooltip>
                                        )
                                    },
                                    {
                                        title: 'Actions',
                                        key: 'actions',
                                        render: (_, record) => (
                                            <Space>
                                                {record.status === 'failed' && (
                                                    <Button
                                                        size="small"
                                                        onClick={() => handleRetry([record.user_id])}
                                                        type="primary"
                                                        ghost
                                                    >
                                                        Retry
                                                    </Button>
                                                )}
                                            </Space>
                                        )
                                    }
                                ]}
                                scroll={{ x: 800 }}
                            />
                        </div>
                    </TabPane>

                    {/* Analytics Tab */}
                    <TabPane tab={
                        <span>
                            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" style={{marginRight: 4}}>
                                <line x1="18" y1="20" x2="18" y2="10"/>
                                <line x1="12" y1="20" x2="12" y2="4"/>
                                <line x1="6" y1="20" x2="6" y2="14"/>
                            </svg>
                            Analytics
                        </span>
                    } key="analytics">
                        <div className="analytics-section">
                            {/* Status Distribution Chart */}
                            <div className="chart-container">
                                <h4>Status Distribution</h4>
                                <div className="status-chart">
                                    <div className="chart-item sent" style={{ width: `${(recipientBreakdown.sent?.length || 0) / selectedCampaign.total_recipients * 100}%` }}>
                                        Sent: {recipientBreakdown.sent?.length || 0}
                                    </div>
                                    <div className="chart-item failed" style={{ width: `${(recipientBreakdown.failed?.length || 0) / selectedCampaign.total_recipients * 100}%` }}>
                                        Failed: {recipientBreakdown.failed?.length || 0}
                                    </div>
                                    <div className="chart-item pending" style={{ width: `${(recipientBreakdown.pending?.length || 0) / selectedCampaign.total_recipients * 100}%` }}>
                                        Pending: {recipientBreakdown.pending?.length || 0}
                                    </div>
                                </div>
                            </div>

                            {/* Target Users Summary */}
                            <div className="target-users-summary">
                                <h4>Target Users Summary</h4>
                                <div className="summary-grid">
                                    <div className="summary-item">
                                        <span className="summary-label">Total Targeted:</span>
                                        <span className="summary-value">{detailedStats?.target_users?.length || 0}</span>
                                    </div>
                                    <div className="summary-item">
                                        <span className="summary-label">Delivered:</span>
                                        <span className="summary-value">{stats.overall?.total_sent || 0}</span>
                                    </div>
                                    <div className="summary-item">
                                        <span className="summary-label">Failed:</span>
                                        <span className="summary-value">{stats.overall?.total_failed || 0}</span>
                                    </div>
                                    <div className="summary-item">
                                        <span className="summary-label">Success Rate:</span>
                                        <span className="summary-value">{stats.overall?.success_rate || 0}%</span>
                                    </div>
                                </div>
                            </div>
                        </div>
                    </TabPane>
                </Tabs>
            </Modal>
        );
    };

    return (
        <div className="notification-management-modern">
            <div className="page-header-modern">
                <h1 className="page-title-modern">Notifications</h1>
                <Button 
                    type="primary" 
                    icon={<PlusOutlined />}
                    onClick={() => setCreateModalVisible(true)}
                    className="create-btn-modern"
                >
                    Create
                </Button>
            </div>

            <StatisticsCards />
            
            <div className="campaigns-section-modern">
                <h2 className="section-title-modern">Recent Campaigns</h2>
                <CampaignsTable />
            </div>

            <CreateCampaignModal />
            <CampaignDetailsModal />
            
            <UserSelectionModal
                visible={userSelectionVisible}
                onCancel={() => setUserSelectionVisible(false)}
                onConfirm={(users) => setSelectedUsers(users)}
                selectedUsers={selectedUsers}
                zIndex={1060}
                mask={true}
                maskClosable={false}
            />
            
            <BusinessSelectionModal
                visible={businessSelectionVisible}
                onCancel={() => setBusinessSelectionVisible(false)}
                onConfirm={(businesses) => setSelectedBusinesses(businesses)}
                selectedBusinesses={selectedBusinesses}
                zIndex={1060}
                mask={true}
                maskClosable={false}
            />
        </div>
    );
};

export default NotificationManagement;
