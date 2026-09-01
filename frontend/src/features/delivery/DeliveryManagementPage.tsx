import { useEffect, useMemo, useState } from 'react';
import {
  App,
  Button,
  Card,
  Col,
  Input,
  Modal,
  Popconfirm,
  Row,
  Space,
  Table,
  Tag,
  Typography
} from 'antd';
import {
  DeleteOutlined,
  DownloadOutlined,
  FileZipOutlined,
  KeyOutlined,
  ReloadOutlined
} from '@ant-design/icons';
import { api } from '../../api/client';
import type { AccessToken, DeliveryExport, DeliverySnapshot, ListResponse } from '../../api/types';
import { normalizeError } from '../imagery/utils';

type DeliveryApi = typeof api & {
  deliverySnapshots: () => Promise<ListResponse<DeliverySnapshot>>;
};

const deliveryApi = api as DeliveryApi;
const list = <T,>(value: ListResponse<T>): T[] => Array.isArray(value) ? value : value.results;
const formatTime = (value?: string | null) => value ? new Date(value).toLocaleString() : '-';

const statusMeta: Record<string, { text: string; color: string }> = {
  pending: { text: '等待中', color: 'default' },
  running: { text: '生成中', color: 'processing' },
  done: { text: '已完成', color: 'success' },
  failed: { text: '失败', color: 'error' },
  frozen: { text: '已冻结', color: 'success' },
  archived: { text: '已归档', color: 'default' },
  active: { text: '可用', color: 'success' },
  revoked: { text: '已吊销', color: 'default' }
};

function StatusTag({ value }: { value: string }) {
  const meta = statusMeta[value] ?? { text: value || '未知', color: 'default' };
  return <Tag color={meta.color}>{meta.text}</Tag>;
}

export function DeliveryManagementPage() {
  const { message } = App.useApp();
  const [snapshots, setSnapshots] = useState<DeliverySnapshot[]>([]);
  const [exports, setExports] = useState<DeliveryExport[]>([]);
  const [tokens, setTokens] = useState<AccessToken[]>([]);
  const [loading, setLoading] = useState(false);
  const [publishing, setPublishing] = useState('');
  const [tokenName, setTokenName] = useState('');
  const [creatingToken, setCreatingToken] = useState(false);
  const [createdToken, setCreatedToken] = useState<AccessToken>();

  const load = async () => {
    setLoading(true);
    try {
      const [snapshotResponse, exportResponse, tokenResponse] = await Promise.all([
        deliveryApi.deliverySnapshots(),
        api.exports(),
        api.accessTokens()
      ]);
      setSnapshots(list(snapshotResponse));
      setExports(list(exportResponse));
      setTokens(tokenResponse);
    } catch (error) {
      message.error(normalizeError(error));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { void load(); }, []);

  const createExport = async (snapshot: DeliverySnapshot, format: 'manifest' | 'stac' | 'zip') => {
    const key = `${snapshot.id}:${format}`;
    setPublishing(key);
    try {
      await api.createSnapshotExport(snapshot.id, format);
      message.success(`${format.toUpperCase()} 导出任务已创建`);
      setExports(list(await api.exports()));
    } catch (error) {
      message.error(normalizeError(error));
    } finally {
      setPublishing('');
    }
  };

  const createToken = async () => {
    const name = tokenName.trim();
    if (!name) {
      message.warning('请输入令牌名称');
      return;
    }
    setCreatingToken(true);
    try {
      const token = await api.createAccessToken(name);
      setCreatedToken(token);
      setTokenName('');
      setTokens(await api.accessTokens());
    } catch (error) {
      message.error(normalizeError(error));
    } finally {
      setCreatingToken(false);
    }
  };

  const revokeToken = async (token: AccessToken) => {
    try {
      await api.deleteAccessToken(token.id);
      message.success('访问令牌已吊销');
      setTokens(await api.accessTokens());
    } catch (error) {
      message.error(normalizeError(error));
    }
  };

  const exportCounts = useMemo(() => ({
    running: exports.filter(item => item.status === 'pending' || item.status === 'running').length,
    done: exports.filter(item => item.status === 'done').length,
    failed: exports.filter(item => item.status === 'failed').length
  }), [exports]);

  return (
    <div className="delivery-management-page">
      <Space direction="vertical" size={20} style={{ width: '100%' }}>
        <Row align="middle" justify="space-between">
          <Col>
            <Typography.Title level={2} style={{ marginBottom: 4 }}>交付管理</Typography.Title>
            <Typography.Text type="secondary">管理冻结快照、交付包和外部访问凭据</Typography.Text>
          </Col>
          <Col><Button icon={<ReloadOutlined />} loading={loading} onClick={() => void load()}>刷新</Button></Col>
        </Row>

        <Card title="交付快照" extra={<Typography.Text type="secondary">共 {snapshots.length} 个</Typography.Text>}>
          <Table<DeliverySnapshot>
            rowKey="id"
            loading={loading}
            dataSource={snapshots}
            tableLayout="fixed"
            pagination={{ pageSize: 8, showSizeChanger: false }}
            columns={[
              { title: '快照名称', dataIndex: 'name', width: '25%', ellipsis: true },
              { title: '说明', dataIndex: 'description', width: '25%', ellipsis: true, render: value => value || '-' },
              { title: '影像数', dataIndex: 'imagery_count', width: '10%', align: 'right' },
              { title: '状态', dataIndex: 'status', width: '10%', render: value => <StatusTag value={value} /> },
              { title: '冻结时间', dataIndex: 'frozen_at', width: '15%', render: formatTime },
              {
                title: '发起导出', key: 'actions', width: '15%',
                render: (_, snapshot) => <Space size={4} wrap>
                  {(['manifest', 'stac', 'zip'] as const).map(format => <Button key={format} type="link" size="small" loading={publishing === `${snapshot.id}:${format}`} onClick={() => void createExport(snapshot, format)}>{format.toUpperCase()}</Button>)}
                </Space>
              }
            ]}
          />
        </Card>

        <Card title="导出任务" extra={<Space size={16}><Typography.Text type="secondary">处理中 {exportCounts.running}</Typography.Text><Typography.Text type="secondary">已完成 {exportCounts.done}</Typography.Text><Typography.Text type="secondary">失败 {exportCounts.failed}</Typography.Text></Space>}>
          <Table<DeliveryExport>
            rowKey="id"
            loading={loading}
            dataSource={exports}
            tableLayout="fixed"
            pagination={{ pageSize: 10, showSizeChanger: false }}
            columns={[
              { title: '任务编号', dataIndex: 'id', width: '15%', ellipsis: true },
              { title: '格式', dataIndex: 'format', width: '10%', render: value => <Tag icon={value === 'zip' ? <FileZipOutlined /> : undefined}>{String(value).toUpperCase()}</Tag> },
              { title: '状态', dataIndex: 'status', width: '12%', render: value => <StatusTag value={value} /> },
              { title: '创建时间', dataIndex: 'created_at', width: '18%', render: formatTime },
              { title: '完成时间', dataIndex: 'finished_at', width: '18%', render: formatTime },
              { title: '错误信息', key: 'error', width: '17%', ellipsis: true, render: (_, item) => item.error_message || item.error || '-' },
              { title: '操作', key: 'action', width: '10%', render: (_, item) => item.status === 'done' ? <Button type="link" size="small" icon={<DownloadOutlined />} href={item.download_url || api.downloadExportUrl(item.id)}>下载</Button> : '-' }
            ]}
          />
        </Card>

        <Card title="访问令牌" extra={<Space.Compact><Input value={tokenName} maxLength={80} placeholder="令牌名称" onChange={event => setTokenName(event.target.value)} onPressEnter={() => void createToken()} /><Button type="primary" icon={<KeyOutlined />} loading={creatingToken} onClick={() => void createToken()}>创建</Button></Space.Compact>}>
          <Table<AccessToken>
            rowKey="id"
            loading={loading}
            dataSource={tokens}
            tableLayout="fixed"
            pagination={{ pageSize: 8, showSizeChanger: false }}
            columns={[
              { title: '名称', dataIndex: 'name', width: '35%', ellipsis: true },
              { title: '创建时间', dataIndex: 'created_at', width: '25%', render: formatTime },
              { title: '最后使用', dataIndex: 'last_used_at', width: '25%', render: formatTime },
              { title: '操作', key: 'action', width: '15%', render: (_, token) => <Popconfirm title="确定吊销此访问令牌？" description="吊销后使用该令牌的调用会立即失效。" okText="吊销" cancelText="取消" onConfirm={() => void revokeToken(token)}><Button danger type="link" size="small" icon={<DeleteOutlined />}>吊销</Button></Popconfirm> }
            ]}
          />
        </Card>
      </Space>

      <Modal title="访问令牌已创建" open={Boolean(createdToken)} footer={<Button type="primary" onClick={() => setCreatedToken(undefined)}>我已保存</Button>} closable={false}>
        <Typography.Paragraph type="secondary">令牌明文仅在此处显示一次，请妥善保存。</Typography.Paragraph>
        <Input.TextArea value={createdToken?.token || ''} readOnly autoSize={{ minRows: 3, maxRows: 5 }} />
      </Modal>
    </div>
  );
}
