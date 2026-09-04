import { Alert, App, Button, Checkbox, Form, Input, Typography } from 'antd';
import { DatabaseOutlined, SearchOutlined, FolderOutlined, LockOutlined, UserOutlined } from '@ant-design/icons';
import { api } from '../../api/client';
import { useLogin } from '../../api/hooks';
import { normalizeError } from '../imagery/utils';
import { SatHubMarkColor } from '../../components/SatHubMarkColor';
import { LoginOrbitDecor } from '../../components/LoginOrbitDecor';

const brandPoints = [
  { icon: <DatabaseOutlined />, title: '汇聚接入', text: '本地目录、NAS 与链接数据统一登记入库' },
  { icon: <SearchOutlined />, title: '检索与地图', text: '目录查询、空间检索和快速预览' },
  { icon: <FolderOutlined />, title: '数据资产', text: '数据集与项目标签，沉淀你的影像库' }
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
        <LoginOrbitDecor />
        <div className="login-brand-top">
          <span className="login-brand-logo"><img src="/logo.png" alt="SatHub" style={{ width: 56, height: 61, objectFit: 'contain', display: 'block' }} /></span>
          <div>
            <Typography.Title level={3} className="login-brand-title">SatHub</Typography.Title>
            <Typography.Text className="login-brand-subtitle">卫星影像管理平台</Typography.Text>
          </div>
        </div>
        <div className="login-brand-hero">
          <Typography.Title level={2} className="login-brand-headline">
            统一<em>接入</em>、<br />检索与<em>服务</em>
          </Typography.Title>
          <Typography.Paragraph className="login-brand-desc">
            把散落在硬盘与目录中的卫星影像接入统一平台，
            完成从汇聚、编目到检索与预览的全流程管理。
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
          <Typography.Text>SatHub · 开源影像平台</Typography.Text>
        </div>
      </div>
      <div className="login-form-pane">
        <section className="login-panel">
          <div className="login-panel-brand">
            <span className="login-panel-logo"><img src="/logo.png" alt="SatHub" style={{ width: 46, height: 50, objectFit: 'contain', display: 'block' }} /></span>
            <Typography.Title level={3} className="login-panel-name">SatHub</Typography.Title>
          </div>
          <div className="login-panel-head">
            <Typography.Text type="secondary">使用平台账号继续</Typography.Text>
          </div>
          <Form layout="vertical" requiredMark={false} onFinish={submit} size="large">
            <Form.Item name="username" label="用户名" rules={[{ required: true, message: '请输入用户名' }]}>
              <Input prefix={<UserOutlined />} autoComplete="username" placeholder="请输入用户名" />
            </Form.Item>
            <Form.Item name="password" label="密码" rules={[{ required: true, message: '请输入密码' }]}>
              <Input.Password prefix={<LockOutlined />} autoComplete="current-password" placeholder="请输入密码" />
            </Form.Item>
            <div className="login-panel-options">
              <Checkbox>记住我</Checkbox>
              <Typography.Link className="login-panel-forgot">忘记密码？</Typography.Link>
            </div>
            {login.isError ? <Alert type="error" showIcon message={normalizeError(login.error)} /> : null}
            <Button type="primary" htmlType="submit" loading={login.isPending} block>登 录</Button>
            <div className="login-panel-switch">
              <Typography.Text type="secondary">还没有账号？</Typography.Text>
              <Typography.Link href="/register">注册一个</Typography.Link>
            </div>
          </Form>
        </section>
      </div>
    </div>
  );
}
