import { useState } from 'react';
import { App as AntdApp, Button, Form, Input, Modal, Popconfirm, Select, Space, Switch, Table, Tag, Typography } from 'antd';
import type { ColumnsType } from 'antd/es/table';
import dayjs from 'dayjs';
import { useCreateUser, useDeleteUser, useResetUserPassword, useUpdateUser, useUsers } from '../../api/hooks';
import type { User, UserAdmin } from '../../api/types';
import { normalizeError } from '../imagery/utils';

export function UsersPanel({ currentUser }: { currentUser?: User }) {
  const { message } = AntdApp.useApp();
  const usersQuery = useUsers();
  const createUser = useCreateUser();
  const updateUser = useUpdateUser();
  const deleteUser = useDeleteUser();
  const resetPassword = useResetUserPassword();
  const [createOpen, setCreateOpen] = useState(false);
  const [createForm] = Form.useForm();
  const [resetTarget, setResetTarget] = useState<UserAdmin>();
  const [resetForm] = Form.useForm();

  const users = usersQuery.data ?? [];
  const isSelf = (user: UserAdmin) => user.id === currentUser?.id;

  const submitCreate = async () => {
    try {
      const values = await createForm.validateFields();
      await createUser.mutateAsync(values);
      message.success('用户已创建');
      setCreateOpen(false);
      createForm.resetFields();
    } catch (error) {
      if (error instanceof Error) message.error(normalizeError(error));
    }
  };

  const submitReset = async () => {
    if (!resetTarget) return;
    try {
      const values = await resetForm.validateFields();
      await resetPassword.mutateAsync({ id: resetTarget.id, password: values.new_password });
      message.success('密码已重置');
      setResetTarget(undefined);
      resetForm.resetFields();
    } catch (error) {
      if (error instanceof Error) message.error(normalizeError(error));
    }
  };

  const toggle = (user: UserAdmin, field: 'is_staff' | 'is_active', value: boolean) => {
    updateUser.mutate(
      { id: user.id, payload: { [field]: value } },
      { onError: (error) => message.error(normalizeError(error)) }
    );
  };

  const columns: ColumnsType<UserAdmin> = [
    {
      title: '用户名', dataIndex: 'username', width: 160,
      render: (value, record) => (
        <Space size={6}>
          <span style={{ fontWeight: 500 }}>{value}</span>
          {isSelf(record) ? <Tag>当前账号</Tag> : null}
          {record.is_superuser ? <Tag color="gold">超级管理员</Tag> : null}
        </Space>
      )
    },
    { title: '邮箱', dataIndex: 'email', ellipsis: true, render: (value) => value || '-' },
    {
      title: '管理员', dataIndex: 'is_staff', width: 90,
      render: (value, record) => (
        <Switch size="small" checked={value || record.is_superuser} disabled={record.is_superuser || isSelf(record)} onChange={(checked) => toggle(record, 'is_staff', checked)} />
      )
    },
    {
      title: '启用', dataIndex: 'is_active', width: 80,
      render: (value, record) => (
        <Switch size="small" checked={value} disabled={isSelf(record)} onChange={(checked) => toggle(record, 'is_active', checked)} />
      )
    },
    {
      title: '注册时间', dataIndex: 'date_joined', width: 150,
      render: (value) => dayjs(value).format('YYYY-MM-DD HH:mm')
    },
    {
      title: '最近登录', dataIndex: 'last_login', width: 150,
      render: (value) => (value ? dayjs(value).format('YYYY-MM-DD HH:mm') : '从未')
    },
    {
      title: '操作', width: 160,
      render: (_, record) => (
        <Space size={0}>
          <Button type="link" size="small" onClick={() => setResetTarget(record)}>重置密码</Button>
          {!isSelf(record) && !record.is_superuser ? (
            <Popconfirm
              title="删除用户"
              description={<span>将删除 <b>{record.username}</b> 及其任务记录，确定？</span>}
              okText="删除"
              okButtonProps={{ danger: true }}
              cancelText="取消"
              onConfirm={() => deleteUser.mutate(record.id, { onError: (error) => message.error(normalizeError(error)) })}
            >
              <Button type="link" size="small" danger>删除</Button>
            </Popconfirm>
          ) : null}
        </Space>
      )
    }
  ];

  return (
    <div className="datasets-page">
      <div className="dataset-toolbar">
        <Typography.Text type="secondary">共 {users.length} 个账号 · 注册功能默认开放</Typography.Text>
        <Button type="primary" onClick={() => setCreateOpen(true)}>新建用户</Button>
      </div>
      {usersQuery.isError ? <Typography.Text type="danger">{normalizeError(usersQuery.error)}</Typography.Text> : null}
      <Table
        rowKey="id"
        size="middle"
        columns={columns}
        dataSource={users}
        loading={usersQuery.isLoading}
        tableLayout="fixed"
        pagination={false}
      />

      <Modal
        title="新建用户"
        open={createOpen}
        onCancel={() => { setCreateOpen(false); createForm.resetFields(); }}
        onOk={() => void submitCreate()}
        confirmLoading={createUser.isPending}
        destroyOnHidden
      >
        <Form form={createForm} layout="vertical" requiredMark={false}>
          <Form.Item name="username" label="用户名" rules={[{ required: true, message: '请输入用户名' }]}>
            <Input placeholder="3-150 个字符" />
          </Form.Item>
          <Form.Item name="email" label="邮箱（可选）" rules={[{ type: 'email', message: '邮箱格式不正确' }]}>
            <Input placeholder="you@example.com" />
          </Form.Item>
          <Form.Item name="password" label="初始密码" rules={[{ required: true, message: '请输入密码' }, { min: 8, message: '至少 8 位字符' }]}>
            <Input.Password placeholder="至少 8 位，避免纯数字" />
          </Form.Item>
          <Form.Item name="is_staff" label="角色" initialValue={false}>
            <Select options={[{ value: false, label: '普通用户' }, { value: true, label: '管理员' }]} />
          </Form.Item>
        </Form>
      </Modal>

      <Modal
        title={resetTarget ? `重置 ${resetTarget.username} 的密码` : '重置密码'}
        open={Boolean(resetTarget)}
        onCancel={() => { setResetTarget(undefined); resetForm.resetFields(); }}
        onOk={() => void submitReset()}
        confirmLoading={resetPassword.isPending}
        destroyOnHidden
      >
        <Form form={resetForm} layout="vertical" requiredMark={false}>
          <Form.Item name="new_password" label="新密码" rules={[{ required: true, message: '请输入新密码' }, { min: 8, message: '至少 8 位字符' }]}>
            <Input.Password placeholder="至少 8 位，避免纯数字" />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
}
