import { DeleteOutlined, LockOutlined, PlusOutlined } from '@ant-design/icons';
import { Button, Card, Form, Input, Modal, Popconfirm, Select, Table, Tooltip, message } from 'antd';
import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';

import { ROLE_ADMIN, ROLE_OPTIONS, ROLE_PI, ROLE_RESEARCHER } from '../../constants/roles';
import { useAuth } from '../../hooks/useAuth';
import apiClient from '../../services/api-client';

interface User {
  id: string;
  username: string;
  role: string;
}

export default function UsersAdmin() {
  const { t } = useTranslation();
  const { user: currentUser } = useAuth();
  const [users, setUsers] = useState<User[]>([]);
  const [showCreate, setShowCreate] = useState(false);
  const [changingPasswordUser, setChangingPasswordUser] = useState<User | null>(null);
  const [form] = Form.useForm();
  const [pwForm] = Form.useForm();

  const loadUsers = () => {
    apiClient.get('/admin/users').then((r) => setUsers(r.data));
  };

  useEffect(loadUsers, []);

  const createUser = async (values: { username: string; password: string; role: string }) => {
    await apiClient.post('/admin/users', values);
    setShowCreate(false);
    form.resetFields();
    loadUsers();
  };

  const deleteUser = async (id: string) => {
    await apiClient.delete(`/admin/users/${id}`);
    loadUsers();
  };

  const canEditUserRole = (target: User) => {
    if (currentUser?.role === ROLE_ADMIN) return true;
    if (currentUser?.role !== ROLE_PI) return false;
    return target.id === currentUser.id || target.role === ROLE_RESEARCHER;
  };

  const roleOptionsForUser = (target: User) => {
    if (currentUser?.role === ROLE_ADMIN) {
      return ROLE_OPTIONS.map((o) => ({ value: o.value, label: o.label }));
    }
    if (!canEditUserRole(target)) return [];
    return ROLE_OPTIONS
      .filter((o) => o.value !== ROLE_ADMIN)
      .map((o) => ({ value: o.value, label: o.label }));
  };

  const updateRole = async (target: User, role: string) => {
    await apiClient.put(`/admin/users/${target.id}`, { role });
    message.success(t('admin.roleUpdated'));
    loadUsers();
  };

  const openChangePassword = (user: User) => {
    setChangingPasswordUser(user);
    pwForm.resetFields();
  };

  const changePassword = async (values: { password: string }) => {
    if (!changingPasswordUser) return;
    await apiClient.put(`/admin/users/${changingPasswordUser.id}`, { password: values.password });
    message.success(t('auth.change-password-success'));
    setChangingPasswordUser(null);
  };

  return (
    <div style={{ padding: 24 }}>
      <Card
        title={t('admin.users')}
        extra={
          <Button icon={<PlusOutlined />} onClick={() => setShowCreate(true)}>
            {t('admin.create-user')}
          </Button>
        }
      >
        <Table
          dataSource={users}
          rowKey="id"
          scroll={{ x: 'max-content' }}
          columns={[
            { title: t('auth.username'), dataIndex: 'username' },
            {
              title: t('admin.role'),
              dataIndex: 'role',
              render: (_, record) => (
                <Select
                  size="small"
                  value={record.role}
                  disabled={!canEditUserRole(record)}
                  options={roleOptionsForUser(record)}
                  style={{ width: 140 }}
                  onChange={(role) => updateRole(record, role)}
                />
              ),
            },
            {
              title: t('common.actions'),
              render: (_, record) => (
                <div style={{ display: 'flex', gap: 8 }}>
                  <Tooltip title={t('admin.change-password')}>
                    <Button
                      icon={<LockOutlined />}
                      size="small"
                      aria-label={t('admin.change-password')}
                      onClick={() => openChangePassword(record)}
                    />
                  </Tooltip>
                  {currentUser?.role === ROLE_ADMIN && (
                    <Popconfirm title={t('common.confirm')} onConfirm={() => deleteUser(record.id)}>
                      <Button icon={<DeleteOutlined />} danger size="small" aria-label={t('common.delete')} />
                    </Popconfirm>
                  )}
                </div>
              ),
            },
          ]}
        />
      </Card>

      <Modal
        title={t('admin.create-user')}
        open={showCreate}
        onCancel={() => setShowCreate(false)}
        onOk={() => form.submit()}
      >
        <Form form={form} onFinish={createUser} layout="vertical">
          <Form.Item name="username" label={t('auth.username')} rules={[{ required: true }]}>
            <Input />
          </Form.Item>
          <Form.Item name="password" label={t('auth.password')} rules={[{ required: true }]}>
            <Input.Password />
          </Form.Item>
          <Form.Item name="role" label={t('admin.role')} initialValue={ROLE_OPTIONS[0].value}>
            <Select options={ROLE_OPTIONS
              .filter((o) => currentUser?.role === ROLE_ADMIN || o.value !== ROLE_ADMIN)
              .map((o) => ({ value: o.value, label: o.label }))}
            />
          </Form.Item>
        </Form>
      </Modal>

      <Modal
        title={`${t('admin.change-password')} — ${changingPasswordUser?.username}`}
        open={!!changingPasswordUser}
        onCancel={() => setChangingPasswordUser(null)}
        onOk={() => pwForm.submit()}
      >
        <Form form={pwForm} onFinish={changePassword} layout="vertical">
          <Form.Item name="password" label={t('admin.new-password')} rules={[{ required: true }]}>
            <Input.Password />
          </Form.Item>
          <Form.Item
            name="confirm_password"
            label={t('auth.confirm-password')}
            dependencies={['password']}
            rules={[
              { required: true },
              ({ getFieldValue }) => ({
                validator(_, value) {
                  if (!value || getFieldValue('password') === value) return Promise.resolve();
                  return Promise.reject(new Error(t('auth.password-mismatch')));
                },
              }),
            ]}
          >
            <Input.Password />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
}
