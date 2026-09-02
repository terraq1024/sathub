import { useState } from 'react';
import { Badge, Button, Space, Tabs } from 'antd';
import { CloudUploadOutlined, DatabaseOutlined, FolderOpenOutlined, HddOutlined, TeamOutlined, UnorderedListOutlined } from '@ant-design/icons';
import { getListCount, unwrapList, useDatasets, useImagery, useJobs } from '../../api/hooks';
import type { Project, User } from '../../api/types';
import { MetricStrip, PageHeader } from '../../components/VisualPrimitives';
import { DatasetsPanel } from '../datasets/DatasetsPanel';
import { ImportDrawer } from '../ingestion/ImportDrawer';
import { TasksDrawer } from '../ingestion/TasksDrawer';
import { ImageryCatalog } from './ImageryCatalog';
import { StoragePanel } from '../storage/StoragePanel';
import { UsersPanel } from '../auth/UsersPanel';

interface DataPageProps {
  projects: Project[];
  projectLoading?: boolean;
  currentUser?: User;
}

export function DataPage({ projects, projectLoading, currentUser }: DataPageProps) {
  const [importOpen, setImportOpen] = useState(false);
  const [tasksOpen, setTasksOpen] = useState(false);
  const jobsQuery = useJobs();
  const imageryCountQuery = useImagery({ page: 1, page_size: 1 });
  const datasetsQuery = useDatasets({ page: 1, page_size: 1 });
  const runningCount = unwrapList(jobsQuery.data).filter((job) =>
    ['pending', 'validating', 'running', 'scanning', 'parsing', 'storing'].includes(job.status)
  ).length;

  const actions = (
    <Space>
      <Button icon={<CloudUploadOutlined />} type="primary" onClick={() => setImportOpen(true)}>导入</Button>
      <Badge count={runningCount} size="small" offset={[-2, 2]}>
        <Button icon={<UnorderedListOutlined />} onClick={() => setTasksOpen(true)}>任务</Button>
      </Badge>
    </Space>
  );

  return (
    <div className="data-page">
      <PageHeader
        title="数据管理"
        description="影像目录、数据集与接入任务"
        extra={actions}
      />
      <MetricStrip items={[
        { key: 'imagery', label: '影像', value: getListCount(imageryCountQuery.data), detail: '已入库景数', icon: <DatabaseOutlined />, tone: 'primary' },
        { key: 'datasets', label: '数据集', value: getListCount(datasetsQuery.data), detail: '静态与动态集合', icon: <HddOutlined /> },
        { key: 'jobs', label: '运行任务', value: runningCount, detail: '接入处理中', icon: <UnorderedListOutlined />, tone: runningCount > 0 ? 'warning' : undefined }
      ]} />
      <Tabs
        defaultActiveKey="imagery"
        items={[
          {
            key: 'imagery',
            label: '影像',
            children: <ImageryCatalog projects={projects} projectLoading={projectLoading} currentUser={currentUser} />
          },
          {
            key: 'datasets',
            label: '数据集',
            children: <DatasetsPanel currentUser={currentUser} />
          },
          {
            key: 'storage',
            label: <span><FolderOpenOutlined /> 目录接入</span>,
            children: <StoragePanel />
          },
          ...(currentUser?.is_staff || currentUser?.is_superuser
            ? [{ key: 'users', label: <span><TeamOutlined /> 用户管理</span>, children: <UsersPanel currentUser={currentUser} /> }]
            : [])
        ]}
      />
      <ImportDrawer open={importOpen} onClose={() => setImportOpen(false)} projects={projects} projectLoading={projectLoading} />
      <TasksDrawer open={tasksOpen} onClose={() => setTasksOpen(false)} projects={projects} />
    </div>
  );
}
