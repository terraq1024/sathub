import { useState } from 'react';
import { Tabs } from 'antd';
import { TeamOutlined } from '@ant-design/icons';
import { UsersPanel } from '../auth/UsersPanel';

type SettingsKey = 'users';

const modules: Array<{ key: SettingsKey; label: string; icon: React.ReactNode; description: string }> = [
  { key: 'users', label: '用户管理', icon: <TeamOutlined />, description: '账号、角色与密码' }
];

export function SettingsPage() {
  const [active, setActive] = useState<SettingsKey>('users');

  return (
    <div className="settings-page">
      <div className="visual-page-header">
        <div className="visual-page-header-copy">
          <h1 className="settings-page-title">系统设置</h1>
          <p className="settings-page-desc">平台运行配置与账号管理</p>
        </div>
      </div>
      <Tabs
        activeKey={active}
        onChange={(key) => setActive(key as SettingsKey)}
        items={modules.map((module) => ({
          key: module.key,
          label: <span>{module.icon} {module.label}</span>,
          children: <UsersPanel />
        }))}
      />
    </div>
  );
}
