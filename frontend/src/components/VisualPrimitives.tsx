import type { ReactNode } from 'react';
import { Space, Tag, Typography } from 'antd';
import type { TagProps } from 'antd';

interface PageHeaderProps {
  title: string;
  description?: string;
  extra?: ReactNode;
  status?: ReactNode;
}

export function PageHeader({ title, description, extra, status }: PageHeaderProps) {
  return (
    <div className="visual-page-header">
      <div className="visual-page-header-copy">
        <Space size={10} align="center" wrap>
          <Typography.Title level={3}>{title}</Typography.Title>
          {status}
        </Space>
        {description ? <Typography.Text type="secondary">{description}</Typography.Text> : null}
      </div>
      {extra ? <div className="visual-page-header-extra">{extra}</div> : null}
    </div>
  );
}

export interface MetricItem {
  key: string;
  label: string;
  value: ReactNode;
  detail?: ReactNode;
  icon?: ReactNode;
  tone?: 'primary' | 'success' | 'warning' | 'danger';
}

const metricToneClass: Record<NonNullable<MetricItem['tone']>, string> = {
  primary: 'visual-metric-tone-primary',
  success: 'visual-metric-tone-success',
  warning: 'visual-metric-tone-warning',
  danger: 'visual-metric-tone-danger'
};

export function MetricStrip({ items }: { items: MetricItem[] }) {
  return (
    <div className="visual-metric-strip">
      {items.map((item) => (
        <div className={`visual-metric ${item.tone ? metricToneClass[item.tone] : ''}`} key={item.key}>
          <div className="visual-metric-head">
            <span className="visual-metric-icon">{item.icon}</span>
            <Typography.Text className="visual-metric-label">{item.label}</Typography.Text>
          </div>
          <div className="visual-metric-body">
            <Typography.Title level={4}>{item.value}</Typography.Title>
            {item.detail ? <Typography.Text type="secondary" className="visual-metric-detail">{item.detail}</Typography.Text> : null}
          </div>
        </div>
      ))}
    </div>
  );
}

// 轻量商务标签：浅底色 + 同色系文字，避免实心彩边在表格里形成视觉噪音。
type Tone = TagProps['color'];

const statusMap: Record<string, { label: string; color: Tone; cls: string }> = {
  online: { label: '在线', color: 'success', cls: 'status-tag status-tag-success' },
  done: { label: '完成', color: 'success', cls: 'status-tag status-tag-success' },
  ready: { label: '可用', color: 'success', cls: 'status-tag status-tag-success' },
  succeeded: { label: '完成', color: 'success', cls: 'status-tag status-tag-success' },
  active: { label: '有效', color: 'success', cls: 'status-tag status-tag-success' },
  frozen: { label: '已冻结', color: 'success', cls: 'status-tag status-tag-success' },
  processing: { label: '处理中', color: 'processing', cls: 'status-tag status-tag-processing' },
  running: { label: '处理中', color: 'processing', cls: 'status-tag status-tag-processing' },
  publishing: { label: '发布中', color: 'processing', cls: 'status-tag status-tag-processing' },
  validating: { label: '校验中', color: 'processing', cls: 'status-tag status-tag-processing' },
  preparing: { label: '准备中', color: 'cyan', cls: 'status-tag status-tag-info' },
  pending: { label: '等待', color: 'cyan', cls: 'status-tag status-tag-info' },
  scanning: { label: '扫描中', color: 'cyan', cls: 'status-tag status-tag-info' },
  parsing: { label: '解析中', color: 'cyan', cls: 'status-tag status-tag-info' },
  storing: { label: '入库中', color: 'cyan', cls: 'status-tag status-tag-info' },
  downloading: { label: '下载中', color: 'cyan', cls: 'status-tag status-tag-info' },
  extracting: { label: '解压中', color: 'cyan', cls: 'status-tag status-tag-info' },
  warning: { label: '警告', color: 'warning', cls: 'status-tag status-tag-warning' },
  degraded: { label: '降级', color: 'warning', cls: 'status-tag status-tag-warning' },
  skipped: { label: '已跳过', color: 'warning', cls: 'status-tag status-tag-warning' },
  canceled: { label: '已取消', color: 'warning', cls: 'status-tag status-tag-warning' },
  needs_review: { label: '待复核', color: 'warning', cls: 'status-tag status-tag-warning' },
  failed: { label: '失败', color: 'error', cls: 'status-tag status-tag-error' },
  error: { label: '错误', color: 'error', cls: 'status-tag status-tag-error' },
  broken: { label: '异常', color: 'error', cls: 'status-tag status-tag-error' },
  offline: { label: '已下线', color: 'default', cls: 'status-tag status-tag-muted' },
  archived: { label: '已归档', color: 'default', cls: 'status-tag status-tag-muted' },
  draft: { label: '草稿', color: 'default', cls: 'status-tag status-tag-muted' },
  dry_run: { label: '试跑', color: 'default', cls: 'status-tag status-tag-muted' },
  disabled: { label: '已停用', color: 'default', cls: 'status-tag status-tag-muted' }
};

export function StatusTag({ status, label }: { status?: string; label?: string }) {
  const entry = status ? statusMap[status] : undefined;
  if (!entry) return <Tag className="status-tag status-tag-muted">{label ?? status ?? '-'}</Tag>;
  return <Tag color={entry.color} className={entry.cls} bordered={false}>{label ?? entry.label}</Tag>;
}

export function SectionBar({ title, detail, extra }: { title: string; detail?: ReactNode; extra?: ReactNode }) {
  return (
    <div className="visual-section-bar">
      <div>
        <Typography.Text strong className="visual-section-bar-title">{title}</Typography.Text>
        {detail ? <Typography.Text type="secondary">{detail}</Typography.Text> : null}
      </div>
      {extra ? <div>{extra}</div> : null}
    </div>
  );
}
