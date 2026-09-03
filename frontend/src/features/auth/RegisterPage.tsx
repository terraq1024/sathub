import { App, Button, Form, Input, Typography } from 'antd';
import { GlobalOutlined, LinkOutlined, UserOutlined } from '@ant-design/icons';
import { api } from '../../api/client';
import { useRegister } from '../../api/hooks';
import { normalizeError } from '../imagery/utils';
import { SatHubMark } from '../../components/SatHubMark';

const brandPoints = [
  { title: '开放注册', text: '注册即可开始汇聚你的卫星影像' },
  { title: '目录与地图', text: '统一接入、空间检索和快速预览' },
  { title: '数据组织', text: '数据集与项目标签，沉淀团队资产' }
];

export function RegisterPage() {
  const { message } = App.useApp();
  const register = useRegister();

  const submit = async (values: { username: string; password: string; confirm: string; email?: string }) => {
    try {
      await api.csrf();
      await register.mutateAsync({ username: values.username, password: values.password, email: values.email });
      message.success('注册成功');
    } catch (error) {
      message.error(normalizeError(error));
    }
  };

  return (
    <div className="login-screen">
      <div className="login-brand-pane">
        <div className="login-brand-top">
          <span className="brand-mark brand-mark-lg"><SatHubMark size={27} /></span>
          <div>
            <Typography.Title level={3} className="login-brand-title">SatHub</Typography.Title>
            <Typography.Text className="login-brand-subtitle">卫星影像管理平台</Typography.Text>
          </div>
        </div>
        <div className="login-brand-hero">
          <Typography.Title level={2} className="login-brand-headline">从一块硬盘，到整个团队的影像库</Typography.Title>
          <Typography.Paragraph className="login-brand-desc">
            注册一个账号，把散落的卫星影像接入统一目录，检索、预览与组织你的数据资产。
          </Typography.Paragraph>
        </div>
        <ul className="login-brand-points">
          {brandPoints.map((point) => (
            <li key={point.title}>
              <span className="login-brand-point-icon"><LinkOutlined /></span>
              <div>
                <Typography.Text strong className="login-brand-point-title">{point.title}</Typography.Text>
                <Typography.Text className="login-brand-point-text">{point.text}</Typography.Text>
              </div>
            </li>
          ))}
        </ul>
        <div className="login-brand-footer">
          <GlobalOutlined />
          <Typography.Text>SatHub · 开源影像平台</Typography.Text>
        </div>
      </div>
      <div className="login-form-pane">
        <section className="login-panel">
          <div className="login-panel-head">
            <Typography.Title level={4}>注册账号</Typography.Title>
            <Typography.Text type="secondary">创建后立即进入平台</Typography.Text>
          </div>
          <Form layout="vertical" requiredMark={false} onFinish={submit} size="large">
            <Form.Item name="username" label="用户名" rules={[{ required: true, message: '请输入用户名' }]}>
              <Input prefix={<UserOutlined />} autoComplete="username" placeholder="3-150 个字符" />
            </Form.Item>
            <Form.Item name="email" label="邮箱（可选）" rules={[{ type: 'email', message: '邮箱格式不正确' }]}>
              <Input autoComplete="email" placeholder="you@example.com" />
            </Form.Item>
            <Form.Item
              name="password"
              label="密码"
              rules={[
                { required: true, message: '请输入密码' },
                { min: 8, message: '至少 8 位字符' }
              ]}
            >
              <Input.Password autoComplete="new-password" placeholder="至少 8 位，避免纯数字" />
            </Form.Item>
            <Form.Item
              name="confirm"
              label="确认密码"
              dependencies={['password']}
              rules={[
                { required: true, message: '请再次输入密码' },
                ({ getFieldValue }) => ({
                  validator(_, value) {
                    if (!value || getFieldValue('password') === value) return Promise.resolve();
                    return Promise.reject(new Error('两次输入的密码不一致'));
                  }
                })
              ]}
            >
              <Input.Password autoComplete="new-password" placeholder="再次输入密码" />
            </Form.Item>
            {register.isError ? <Typography.Text type="danger">{normalizeError(register.error)}</Typography.Text> : null}
            <Button type="primary" htmlType="submit" loading={register.isPending} block>注册并进入</Button>
            <div style={{ marginTop: 14, textAlign: 'center' }}>
              <Typography.Text type="secondary">已有账号？</Typography.Text>
              <Typography.Link href="/">返回登录</Typography.Link>
            </div>
          </Form>
        </section>
      </div>
    </div>
  );
}
