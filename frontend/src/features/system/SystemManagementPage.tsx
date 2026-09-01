import { Tabs } from 'antd';
import { DatabaseOutlined, FileSearchOutlined, SafetyCertificateOutlined } from '@ant-design/icons';
import MetadataManagementPage from './MetadataManagementPage';
import { StorageManagementPage } from './StorageManagementPage';
import { GovernanceManagementPage } from './GovernanceManagementPage';

export function SystemManagementPage() {
  return (
    <div className="system-management-shell">
      <div className="system-management-heading">
        <h1>系统管理</h1>
        <p>存储、元数据、目录与审计</p>
      </div>
      <Tabs items={[
        { key: 'storage', label: <span><DatabaseOutlined /> 存储管理</span>, children: <StorageManagementPage /> },
        { key: 'metadata', label: <span><FileSearchOutlined /> 元数据规则</span>, children: <MetadataManagementPage /> },
        { key: 'governance', label: <span><SafetyCertificateOutlined /> 目录与审计</span>, children: <GovernanceManagementPage /> }
      ]} />
    </div>
  );
}
