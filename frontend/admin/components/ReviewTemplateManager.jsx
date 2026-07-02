import React, { useState, useEffect } from 'react';
import { Table, Button, Modal, Form, Input, Select, message, Space } from 'antd';
import { FiPlus, FiEdit, FiTrash2 } from 'react-icons/fi';
import AdminService from '../services/adminService';

const { Option } = Select;

const ReviewTemplateManager = () => {
  const [templates, setTemplates] = useState([]);
  const [loading, setLoading] = useState(false);
  const [modalVisible, setModalVisible] = useState(false);
  const [editingTemplate, setEditingTemplate] = useState(null);
  const [form] = Form.useForm();

  useEffect(() => {
    loadTemplates();
  }, []);

  const loadTemplates = async () => {
    try {
      setLoading(true);
      const response = await AdminService.getReviewTemplates();
      if (response.success) {
        setTemplates(response.data || []);
      }
    } catch (error) {
      message.error('Failed to load templates');
    } finally {
      setLoading(false);
    }
  };

  const handleSubmit = async (values) => {
    try {
      if (editingTemplate) {
        await AdminService.updateReviewTemplate(editingTemplate.id, values);
        message.success('Template updated');
      } else {
        await AdminService.createReviewTemplate(values);
        message.success('Template created');
      }
      setModalVisible(false);
      setEditingTemplate(null);
      form.resetFields();
      loadTemplates();
    } catch (error) {
      message.error('Failed to save template');
    }
  };

  const handleDelete = async (id) => {
    try {
      await AdminService.deleteReviewTemplate(id);
      message.success('Template deleted');
      loadTemplates();
    } catch (error) {
      message.error('Failed to delete template');
    }
  };

  const columns = [
    {
      title: 'Title',
      dataIndex: 'title',
      key: 'title',
    },
    {
      title: 'Type',
      dataIndex: 'reason_type',
      key: 'reason_type',
      render: (type) => type.replace('_', ' ').toUpperCase(),
    },
    {
      title: 'Category',
      dataIndex: 'category',
      key: 'category',
    },
    {
      title: 'Description',
      dataIndex: 'description',
      key: 'description',
      ellipsis: true,
    },
    {
      title: 'Actions',
      key: 'actions',
      render: (_, record) => (
        <Space>
          <Button
            icon={<FiEdit />}
            size="small"
            onClick={() => {
              setEditingTemplate(record);
              form.setFieldsValue(record);
              setModalVisible(true);
            }}
          />
          <Button
            icon={<FiTrash2 />}
            size="small"
            danger
            onClick={() => handleDelete(record.id)}
          />
        </Space>
      ),
    },
  ];

  return (
    <div>
      <div style={{ marginBottom: '16px', display: 'flex', justifyContent: 'space-between' }}>
        <h2>Review Templates Management</h2>
        <Button
          type="primary"
          icon={<FiPlus />}
          onClick={() => {
            setEditingTemplate(null);
            form.resetFields();
            setModalVisible(true);
          }}
        >
          Add Template
        </Button>
      </div>

      <Table
        columns={columns}
        dataSource={templates}
        loading={loading}
        rowKey="id"
      />

      <Modal
        title={editingTemplate ? 'Edit Template' : 'Add Template'}
        open={modalVisible}
        onCancel={() => {
          setModalVisible(false);
          setEditingTemplate(null);
          form.resetFields();
        }}
        onOk={() => form.submit()}
      >
        <Form form={form} onFinish={handleSubmit} layout="vertical">
          <Form.Item
            name="title"
            label="Title"
            rules={[{ required: true, message: 'Please enter title' }]}
          >
            <Input />
          </Form.Item>
          
          <Form.Item
            name="reason_type"
            label="Type"
            rules={[{ required: true, message: 'Please select type' }]}
          >
            <Select>
              <Option value="rejection">Rejection</Option>
              <Option value="required_changes">Required Changes</Option>
              <Option value="approval">Approval</Option>
            </Select>
          </Form.Item>
          
          <Form.Item
            name="category"
            label="Category"
            rules={[{ required: true, message: 'Please select category' }]}
          >
            <Select>
              <Option value="documentation">Documentation Issues</Option>
              <Option value="business_info">Business Information</Option>
              <Option value="legal_compliance">Legal & Compliance</Option>
              <Option value="operational">Operational Requirements</Option>
              <Option value="quality">Quality Standards</Option>
              <Option value="other">Other</Option>
            </Select>
          </Form.Item>
          
          <Form.Item
            name="description"
            label="Description"
            rules={[{ required: true, message: 'Please enter description' }]}
          >
            <Input.TextArea rows={3} />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
};

export default ReviewTemplateManager;
