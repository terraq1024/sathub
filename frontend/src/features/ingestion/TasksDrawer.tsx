import { useState } from 'react';
import { App, Button, Descriptions, Drawer, Grid, Progress, Space, Table, Typography } from 'antd';
import type { ColumnsType } from 'antd/es/table';
import { ReloadOutlined, RedoOutlined } from '@ant-design/icons';
import dayjs from 'dayjs';
import { getListCount, unwrapList, useJobItems, useJobs, useRetryItem } from '../../api/hooks';
import type { IngestionItem, IngestionJob, ItemStatus, JobStatus, Project, SourceType } from '../../api/types';
import { normalizeError } from '../imagery/utils';
import { MetricStrip, SectionBar, StatusTag as VisualStatusTag } from '../../components/VisualPrimitives';

const statusLabel: Record<JobStatus | ItemStatus, string> = {
  pending: '等待', validating: '校验', running: '处理中', scanning: '扫描', parsing: '解析', storing: '入库',
  done: '完成', failed: '失败', canceled: '取消', downloading: '下载', extracting: '解压', skipped: '已跳过'
};

const sourceLabel: Record<SourceType, string> = {
  url_text: '下载链接', zip_upload: 'ZIP', archive_upload: 'ZIP / 7Z', folder_zip: '文件夹压缩包', folder_upload: '文件夹'
};

function StatusTag({ status }: { status: JobStatus | ItemStatus }) {
  return <VisualStatusTag status={status} label={statusLabel[status] ?? status} />;
}

function progress(job: IngestionJob) {
  if (!job.total_count) return job.status === 'done' ? 100 : 0;
  return Math.round(((job.success_count + job.failed_count + (job.skipped_count ?? 0)) / job.total_count) * 100);
}

function JobItems({ jobId }: { jobId: string | number }) {
  const { message } = App.useApp();
  const itemsQuery = useJobItems(jobId);
  const retry = useRetryItem();
  const [retryingId, setRetryingId] = useState<string | number>();
  const columns: ColumnsType<IngestionItem> = [
    { title: '来源', dataIndex: 'source', ellipsis: true },
    { title: '状态', dataIndex: 'status', width: 90, render: (value) => <StatusTag status={value} /> },
    { title: '影像 ID', dataIndex: 'image_id', width: 150, ellipsis: true },
    { title: '错误', dataIndex: 'error_message', ellipsis: true },
    {
      title: '', width: 54,
      render: (_, item) => (
        <Button
          type="text"
          title="重试"
          icon={<RedoOutlined />}
          disabled={item.status !== 'failed'}
          loading={retryingId === item.id && retry.isPending}
          onClick={() => {
            setRetryingId(item.id);
            retry.mutate(item.id, {
              onError: (error) => message.error(normalizeError(error)),
              onSettled: () => setRetryingId(undefined)
            });
          }}
        />
      )
    }
  ];
  return <Table rowKey="id" size="small" columns={columns} dataSource={unwrapList(itemsQuery.data)} loading={itemsQuery.isLoading} pagination={{ pageSize: 8 }} tableLayout="fixed" />;
}

interface TasksDrawerProps {
  open: boolean;
  onClose: () => void;
  projects: Project[];
}

export function TasksDrawer({ open, onClose, projects }: TasksDrawerProps) {
  const screens = Grid.useBreakpoint();
  const jobsQuery = useJobs(open);
  const jobs = unwrapList(jobsQuery.data);
  const projectName = (job: IngestionJob) => job.project_name ?? projects.find((project) => String(project.id) === String(job.project))?.name ?? '-';
  const running = jobs.filter((job) => ['pending', 'validating', 'running', 'scanning', 'parsing', 'storing'].includes(job.status)).length;
  const failed = jobs.filter((job) => job.status === 'failed').length;
  const completed = jobs.filter((job) => job.status === 'done').length;
  const columns: ColumnsType<IngestionJob> = [
    { title: '任务', dataIndex: 'id', width: 78 },
    { title: '来源', dataIndex: 'source_type', width: 110, render: (value) => sourceLabel[value as SourceType] ?? value },
    { title: '项目', width: 120, render: (_, job) => projectName(job) },
    { title: '状态', dataIndex: 'status', width: 90, render: (value) => <StatusTag status={value} /> },
    { title: '进度', width: 130, render: (_, job) => <Progress percent={progress(job)} size="small" /> },
    { title: '成功 / 跳过 / 失败', width: 150, render: (_, job) => `${job.success_count} / ${job.skipped_count ?? 0} / ${job.failed_count}` },
    { title: '创建时间', dataIndex: 'created_at', width: 145, render: (value) => dayjs(value).format('YYYY-MM-DD HH:mm') }
  ];

  return (
    <Drawer
      title="导入任务"
      open={open}
      onClose={onClose}
      width={screens.lg ? 980 : '100%'}
      extra={<Button type="text" icon={<ReloadOutlined />} title="刷新" onClick={() => void jobsQuery.refetch()} />}
    >
      <Space direction="vertical" size={12} className="full-width">
        <MetricStrip items={[
          { key: 'running', label: '处理中', value: running, detail: '实时任务', tone: running > 0 ? 'warning' : undefined },
          { key: 'done', label: '已完成', value: completed, detail: '任务', tone: 'success' },
          { key: 'failed', label: '失败', value: failed, detail: '需要处理', tone: failed > 0 ? 'danger' : undefined },
          { key: 'all', label: '全部', value: getListCount(jobsQuery.data), detail: '导入任务' }
        ]} />
        <SectionBar title="任务列表" detail="展开行查看每景处理结果" />
        <Table
          rowKey="id"
          size="small"
          columns={columns}
          dataSource={jobs}
          loading={jobsQuery.isLoading}
          pagination={{ pageSize: 12 }}
          tableLayout="fixed"
          expandable={{
            expandedRowRender: (job) => (
              <Space direction="vertical" size={8} className="full-width">
                {job.error_message ? <Descriptions size="small" items={[{ key: 'error', label: '任务错误', children: job.error_message }]} /> : null}
                <JobItems jobId={job.id} />
              </Space>
            )
          }}
        />
      </Space>
    </Drawer>
  );
}
