import { useState } from 'react';
import { Avatar, Dropdown, Layout, Menu, Space, Spin } from 'antd';
import { CompassOutlined, DatabaseOutlined, DownOutlined, KeyOutlined, LogoutOutlined, RadarChartOutlined, SettingOutlined, UserOutlined } from '@ant-design/icons';
import { useLogout, useMe, useProjects } from './api/hooks';
import { LoginPage } from './features/auth/LoginPage';
import { ProfileDrawer } from './features/auth/ProfileDrawer';
import { RegisterPage } from './features/auth/RegisterPage';
import { SettingsPage } from './features/settings/SettingsPage';
import { DataPage } from './features/imagery/DataPage';
import { MapPage } from './features/map/MapPage';
import { normalizeError } from './features/imagery/utils';

type PageKey = 'data' | 'map' | 'settings';
const { Header, Content } = Layout;

function isRegisterPath() {
  return typeof window !== 'undefined' && window.location.pathname === '/register';
}

function Workspace() {
  const [page, setPage] = useState<PageKey>('data');
  const [profileOpen, setProfileOpen] = useState(false);
  const me = useMe();
  const logout = useLogout();
  const projectsQuery = useProjects(Boolean(me.data));
  const projects = projectsQuery.data ?? [];
  const isStaff = Boolean(me.data?.is_staff || me.data?.is_superuser);
  const menuItems = [
    { key: 'data', icon: <DatabaseOutlined />, label: '数据管理' },
    { key: 'map', icon: <CompassOutlined />, label: '地图' }
  ];

  const userMenuItems = [
    { key: 'profile', icon: <KeyOutlined />, label: '账号设置' },
    ...(isStaff ? [{ key: 'settings', icon: <SettingOutlined />, label: '系统设置' }] : []),
    { key: 'logout', icon: <LogoutOutlined />, label: '退出登录' }
  ];

  return (
    <Layout className="app-layout">
      <Header className="app-header">
        <div className="top-navigation">
          <div className="brand">
            <span className="brand-mark"><RadarChartOutlined /></span>
            <span className="brand-copy">
              <span className="brand-name">SatHub</span>
              <span className="brand-sub">Imagery Hub</span>
            </span>
          </div>
          <nav className="top-nav-divider" aria-hidden />
          <Menu
            className="top-menu"
            theme="light"
            mode="horizontal"
            selectedKeys={[page]}
            items={menuItems}
            onClick={({ key }) => setPage(key as PageKey)}
          />
        </div>
        <Space className="header-actions" size={8}>
          <Dropdown menu={{ items: userMenuItems, onClick: ({ key }) => { if (key === 'profile') setProfileOpen(true); else if (key === 'settings') setPage('settings'); else logout.mutate(); } }}>
            <button type="button" className="user-chip" aria-label="账户菜单">
              <Avatar size={26} className="user-avatar" icon={<UserOutlined />} />
              <span className="user-chip-name">{me.data?.username}</span>
              {isStaff ? <span className="user-chip-role">管理员</span> : null}
              <DownOutlined className="user-chip-arrow" />
            </button>
          </Dropdown>
        </Space>
      </Header>
      <Content className={`app-content app-content-${page}`}>
        {projectsQuery.isError ? (
          <div className="global-alert-wrap">
            <span className="global-alert">{normalizeError(projectsQuery.error)}</span>
          </div>
        ) : null}
        {page === 'data' ? <DataPage projects={projects} projectLoading={projectsQuery.isLoading} currentUser={me.data} /> : null}
        {page === 'map' ? <MapPage projects={projects} projectLoading={projectsQuery.isLoading} /> : null}
        {page === 'settings' && isStaff ? <SettingsPage /> : null}
      </Content>
      <ProfileDrawer open={profileOpen} onClose={() => setProfileOpen(false)} />
    </Layout>
  );
}

export default function App() {
  // Lightweight path routing: the SPA only has one page plus /register.
  return isRegisterPath() ? <RegisterPage /> : <AuthenticatedApp />;
}

function AuthenticatedApp() {
  const me = useMe();
  if (me.isLoading) return <div className="loading-screen"><Spin size="large" /></div>;
  if (me.isError) return <LoginPage />;
  return <Workspace />;
}
