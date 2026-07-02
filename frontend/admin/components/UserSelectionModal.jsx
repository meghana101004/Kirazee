import React, { useState, useEffect } from 'react';
import { Modal, Table, Input, Select, Checkbox, Space, Button } from 'antd';
import { SearchOutlined } from '@ant-design/icons';

const BASE_URL = import.meta.env.VITE_BASE_URL || 'https://kirazee.com/kirazee';

const UserSelectionModal = ({ visible, onCancel, onConfirm, selectedUsers }) => {
    const [users, setUsers] = useState([]);
    const [loading, setLoading] = useState(false);
    const [searchText, setSearchText] = useState('');
    const [userModeFilter, setUserModeFilter] = useState('');

    useEffect(() => {
        if (visible) {
            fetchUsers();
        }
    }, [visible, searchText, userModeFilter]);

    const fetchUsers = async () => {
        setLoading(true);
        try {
            const params = new URLSearchParams({ 
                search: searchText, 
                user_mode: userModeFilter 
            });
            const response = await fetch(`${BASE_URL}/api/notifications/users/?${params}`);
            const data = await response.json();
            if (data.success) {
                setUsers(data.users || []);
            }
        } catch (error) {
            console.error('Failed to fetch users:', error);
        }
        setLoading(false);
    };

    const handleUserSelection = (userId, checked) => {
        if (checked) {
            const user = users.find(u => u.id === userId);
            if (user && !selectedUsers.some(u => u.id === userId)) {
                onConfirm([...selectedUsers, user]);
            }
        } else {
            onConfirm(selectedUsers.filter(u => u.id !== userId));
        }
    };

    const columns = [
        {
            title: '',
            dataIndex: 'id',
            key: 'select',
            width: 50,
            render: (userId) => (
                <Checkbox
                    checked={selectedUsers.some(u => u.id === userId)}
                    onChange={(e) => handleUserSelection(userId, e.target.checked)}
                />
            )
        },
        { 
            title: 'Name', 
            dataIndex: 'full_name', 
            key: 'full_name',
            width: 130,
            ellipsis: true,
            render: (name) => name || 'N/A'
        },
        { 
            title: 'Email', 
            dataIndex: 'email', 
            key: 'email',
            width: 180,
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
            title: 'Mode', 
            dataIndex: 'user_mode', 
            key: 'user_mode',
            width: 100,
            render: (mode) => {
                const formatted = mode?.replace('_', ' ').toUpperCase() || mode;
                return <span className="mode-badge">{formatted}</span>;
            }
        },
        { 
            title: 'Business', 
            dataIndex: 'business_name', 
            key: 'business_name',
            width: 130,
            ellipsis: true,
            render: (business) => business || 'N/A'
        },
        { 
            title: 'Device', 
            dataIndex: 'device_type', 
            key: 'device_type',
            width: 80,
            render: (device) => device?.toUpperCase() || '-'
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
            title="Select Target Users"
            open={visible}
            onCancel={onCancel}
            width={1100}
            className="user-selection-modal-clean"
            zIndex={1060}
            mask={true}
            maskClosable={false}
            footer={
                <div className="user-modal-footer-clean">
                    <Button onClick={onCancel} className="user-cancel-btn">
                        Cancel
                    </Button>
                    <Button type="primary" onClick={onCancel} className="user-confirm-btn">
                        Confirm Selection ({selectedUsers.length} users)
                    </Button>
                </div>
            }
        >
            <div className="user-search-bar-clean">
                <Input
                    placeholder="Search by name, email, or mobile..."
                    prefix={<SearchOutlined />}
                    value={searchText}
                    onChange={(e) => setSearchText(e.target.value)}
                    className="user-search-input"
                    allowClear
                />
                <Select
                    placeholder="Filter by user mode"
                    value={userModeFilter || undefined}
                    onChange={setUserModeFilter}
                    className="user-filter-select"
                    allowClear
                >
                    <Select.Option value="">All Users</Select.Option>
                    <Select.Option value="CONSUMER">Consumer</Select.Option>
                    <Select.Option value="business_owner">Business Owner</Select.Option>
                    <Select.Option value="delivery_partner">Delivery Partner</Select.Option>
                    <Select.Option value="DELIVERY_PARTNER">Delivery Partner (Alt)</Select.Option>
                </Select>
            </div>

            <Table
                columns={columns}
                dataSource={users}
                rowKey="id"
                loading={loading}
                pagination={{ 
                    pageSize: 10,
                    showSizeChanger: true,
                    showQuickJumper: true,
                    showTotal: (total, range) => `${range[0]}-${range[1]} of ${total} users`,
                    size: 'small'
                }}
                scroll={{ x: true }}
                size="small"
                className="user-table-clean"
            />
        </Modal>
    );
};

export default UserSelectionModal;
