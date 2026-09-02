import { useEffect } from 'react';
import { App, Button, Descriptions, Drawer, Form, Input, Space } from 'antd';
import { useChangePassword, useMe, useUpdateUser } from '../../api/hooks';
import { normalizeError } from '../imagery/utils';

export function ProfileDrawer({ open, onClose }: { open: boolean; onClose: () => void }) {
  const { message } = App.useApp();
  const me = useMe();
  const changePassword = useChangePassword();
  const updateUser = useUpdateUser();
  const [profileForm] = Form.useForm();
  const [passwordForm] = Form.useForm();

  useEffect(() => {
    if (me.data) {
      profileForm.setFieldsValue({ email: me.data.email });
    }
  }, [me.data, profileForm, open]);

  const saveEmail = async () => {
    try {
      const values = await profileForm.validateFields();
      await updateUser.mutateAsync({ id: Number(me.data!.id), payload: { email: values.email ?? '' } });
      message.success('邮箱已更新');
    } catch (error) {
      if (error instanceof Error) message.error(normalizeError(error));
    }
  };

  const savePassword = async () => {
    try {
      const values = await passwordForm.validateFields();
      await changePassword.mutateAsync({ current_password: values.current_password, new_password: values.new_password });
      message.success('密码已更新');
      passwordForm.resetFields();
    } catch (error) {
      if (error instanceof Error) message.error(normalizeError(error));
    }
  };

  return (
    <Drawer title="账号设置" open={open} onClose={onClose} width={380}>
      <Space direction="vertical" size={20} style={{ width: '100%' }}>
        <Descriptions size="small" bordered column={1}>
          <Descriptions.Item label="用户名">{me.data?.username}</Descriptions.Item>
          <Descriptions.Item label="角色">{me.data?.is_staff || me.data?.is_superuser ? '管理员' : '普通用户'}</Descriptions.Item>
        </Descriptions>

        <Form form={profileForm} layout="vertical" requiredMark={false}>
          <Form.Item name="email" label="邮箱" rules={[{ type: 'email', message: '邮箱格式不正确' }]}>
            <Input placeholder="you@example.com" />
          </Form.Item>
          <Button htmlType="button" loading={updateUser.isPending} onClick={() => void saveEmail()}>保存邮箱</Button>
        </Form>

        <Form form={passwordForm} layout="vertical" requiredMark={false}>
          <Form.Item
            name="current_password"
            label="当前密码"
          >
            <Input.Password autoComplete="current-password" placeholder="请输入当前密码" />
          </Form.Item>
          <Form.Item
            name="new_password"
            label="新密码"
            rules={[{ required: true, message: '请输入新密码' }, { min: 8, message: '至少 8 位字符' }]}
            dependencies={['current_password']}
          >
            <Input.Password autoComplete="new-password" placeholder="至少 8 位" />
          </Form.Item>
          <Form.Item
            name="confirm"
            label="确认新密码"
            dependencies={['new_password']}
            rules={[
              { required: true, message: '请再次输入新密码' },
              ({ getFieldValue }) => ({
                validator(_, value) {
                  if (!value || getFieldValue('new_password') === value) return Promise.resolve();
                  return Promise.reject(new Error('两次输入的密码不一致'));
                }
              })
            ]}
          >
            <Input.Password autoComplete="new-password" placeholder="再次输入新密码" />
          </Form.Item>
          <Button type="primary" htmlType="button" loading={changePassword.isPending} onClick={() => void savePassword()}>更新密码</Button>
        </Form>
      </Space>
    </Drawer>
  );
}
