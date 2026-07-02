import React, { useState, useEffect } from 'react';
import { Modal, Table, Input, Checkbox, Space, Button } from 'antd';
import { SearchOutlined } from '@ant-design/icons';

const BASE_URL = import.meta.env.VITE_BASE_URL || 'https://kirazee.com/kirazee';

const BusinessSelectionModal = ({ visible, onCancel, onConfirm, selectedBusinesses }) => {
    const [businesses, setBusinesses] = useState([]);
    const [loading, setLoading] = useState(false);
    const [searchText, setSearchText] = useState('');

    useEffect(() => {
        if (visible) {
            fetchBusinesses();
        }
    }, [visible, searchText]);

    const fetchBusinesses = async () => {
        setLoading(true);
        try {
            const params = new URLSearchParams({ search: searchText });
            const response = await fetch(`${BASE_URL}/api/notifications/businesses/?${params}`);
            const data = await response.json();
            if (data.success) {
                setBusinesses(data.businesses || []);
            }
        } catch (error) {
            console.error('Failed to fetch businesses:', error);
        }
        setLoading(false);
    };

    const handleBusinessSelection = (businessId, checked) => {
        if (checked) {
            const business = businesses.find(b => b.id === businessId);
            if (business && !selectedBusinesses.some(b => b.id === businessId)) {
                onConfirm([...selectedBusinesses, business]);
            }
        } else {
            onConfirm(selectedBusinesses.filter(b => b.id !== businessId));
        }
    };

    const columns = [
        {
            title: '',
            dataIndex: 'id',
            key: 'select',
            width: 50,
            render: (businessId) => (
                <Checkbox
                    checked={selectedBusinesses.some(b => b.id === businessId)}
                    onChange={(e) => handleBusinessSelection(businessId, e.target.checked)}
                />
            )
        },
        { 
            title: 'Business Name', 
            dataIndex: 'business_name', 
            key: 'business_name',
            width: 160,
            ellipsis: true,
            render: (name) => name || 'N/A'
        },
        { 
            title: 'Business ID', 
            dataIndex: 'id', 
            key: 'business_id',
            width: 140,
            ellipsis: true,
            render: (id) => id || 'N/A'
        },
        { 
            title: 'Type', 
            dataIndex: 'business_type', 
            key: 'business_type',
            width: 70,
            render: (type) => {
                const formatted = type?.replace('_', ' ').toUpperCase() || type;
                return <span className="type-badge">{formatted}</span>;
            }
        },
        { 
            title: 'Owner', 
            dataIndex: 'owner_name', 
            key: 'owner_name',
            width: 130,
            ellipsis: true,
            render: (name) => name || 'N/A'
        },
        { 
            title: 'Email', 
            dataIndex: 'email', 
            key: 'email',
            width: 170,
            ellipsis: true,
            render: (email) => email || 'N/A'
        },
        { 
            title: 'Mobile', 
            dataIndex: 'mobile', 
            key: 'mobile',
            width: 110,
            render: (mobile) => mobile || 'N/A'
        },
        { 
            title: 'Active Users', 
            dataIndex: 'active_users_count', 
            key: 'active_users_count',
            width: 70,
            align: 'center',
            render: (count) => <span className="count-badge-biz">{count || 0}</span>
        },
        {
            title: 'Status',
            dataIndex: 'is_active',
            key: 'is_active',
            width: 70,
            render: (isActive) => (
                <span className={`status-badge-compact ${isActive ? 'status-active' : 'status-inactive'}`}>
                    {isActive ? 'Active' : 'Inactive'}
                </span>
            )
        }
    ];

    return (
        <Modal
            title="Select Target Businesses"
            open={visible}
            onCancel={onCancel}
            width={1100}
            className="business-selection-modal-clean"
            zIndex={1060}
            mask={true}
            maskClosable={false}
            footer={
                <div className="business-modal-footer-clean">
                    <Button onClick={onCancel} className="business-cancel-btn">
                        Cancel
                    </Button>
                    <Button type="primary" onClick={onCancel} className="business-confirm-btn">
                        Confirm Selection ({selectedBusinesses.length} businesses)
                    </Button>
                </div>
            }
        >
            <div className="business-search-bar-clean">
                <Input
                    placeholder="Search by name, owner, email, or mobile..."
                    prefix={<SearchOutlined />}
                    value={searchText}
                    onChange={(e) => setSearchText(e.target.value)}
                    className="business-search-input"
                    allowClear
                />
            </div>

            <Table
                columns={columns}
                dataSource={businesses}
                rowKey="id"
                loading={loading}
                pagination={{ 
                    pageSize: 10,
                    showSizeChanger: true,
                    showQuickJumper: true,
                    showTotal: (total, range) => `${range[0]}-${range[1]} of ${total} businesses`,
                    size: 'small'
                }}
                scroll={{ x: true }}
                size="small"
                className="business-table-clean"
            />
        </Modal>
    );
};

export default BusinessSelectionModal;
