import { Alert, App, Button, Form, Input, Typography } from 'antd';
import { DatabaseOutlined, GlobalOutlined, LockOutlined, RadarChartOutlined, SafetyCertificateOutlined, UserOutlined } from '@ant-design/icons';
import { api } from '../../api/client';
import { useLogin } from '../../api/hooks';
import { normalizeError } from '../imagery/utils';

const brandPoints = [
  { icon: <DatabaseOutlined />, title: '汇聚接入', text: '本地、NAS 与链接数据统一登记入库' },
  { icon: <GlobalOutlined />, title: '检索与地图', text: '目录、空间查询和 JPG 快速预览' },
  { icon: <SafetyCertificateOutlined />, title: '服务与交付', text: 'XYZ/STAC 服务、审计和冻结交付' }
];

export function LoginPage() {
  const { message } = App.useApp();
  const login = useLogin();

  const submit = async (values: { username: string; password: string }) => {
    try {
      await api.csrf();
      await login.mutateAsync(values);
      message.success('登录成功');
    } catch (error) {
      message.error(normalizeError(error));
    }
  };

  return (
    <div className="login-screen">
      <div className="login-brand-pane">
        <div className="login-brand-top">
          <span className="brand-mark brand-mark-lg"><RadarChartOutlined /></span>
          <div>
            <Typography.Title level={3} className="login-brand-title">SatHub</Typography.Title>
            <Typography.Text className="login-brand-subtitle">卫星影像管理平台</Typography.Text>
          </div>
        </div>
        <div className="login-brand-hero">
          <Typography.Title level={2} className="login-brand-headline">统一接入、检索与服务</Typography.Title>
          <Typography.Paragraph className="login-brand-desc">
            面向内部研发、售前与交付团队的遥感影像工作台，从数据汇聚到在线服务与交付冻结的全流程管理。
          </Typography.Paragraph>
        </div>
        <ul className="login-brand-points">
          {brandPoints.map((point) => (
            <li key={point.title}>
              <span className="login-brand-point-icon">{point.icon}</span>
              <div>
                <Typography.Text strong className="login-brand-point-title">{point.title}</Typography.Text>
                <Typography.Text className="login-brand-point-text">{point.text}</Typography.Text>
              </div>
            </li>
          ))}
        </ul>
        <div className="login-brand-footer">
          <GlobalOutlined />
          <Typography.Text>内网工作区 · 仅限授权用户访问</Typography.Text>
        </div>
      </div>
      <div className="login-form-pane">
        <section className="login-panel">
          <div className="login-panel-head">
            <Typography.Title level={4}>登录</Typography.Title>
            <Typography.Text type="secondary">使用平台账号继续</Typography.Text>
          </div>
          <Form layout="vertical" requiredMark={false} onFinish={submit} size="large">
            <Form.Item name="username" label="用户名" rules={[{ required: true, message: '请输入用户名' }]}>
              <Input prefix={<UserOutlined />} autoComplete="username" placeholder="请输入用户名" />
            </Form.Item>
            <Form.Item name="password" label="密码" rules={[{ required: true, message: '请输入密码' }]}>
              <Input.Password prefix={<LockOutlined />} autoComplete="current-password" placeholder="请输入密码" />
            </Form.Item>
            {login.isError ? <Alert type="error" showIcon message={normalizeError(login.error)} /> : null}
            <Button type="primary" htmlType="submit" loading={login.isPending} block>登录</Button>
          </Form>
        </section>
      </div>
    </div>
  );
}
