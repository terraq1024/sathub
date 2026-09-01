import { useEffect, useMemo, useState } from 'react';
import { Alert, App as AntdApp, Button, Card, Col, Descriptions, Empty, Form, Input, Layout, Modal, Popconfirm, Row, Select, Space, Statistic, Table, Tag, Typography } from 'antd';
import { CheckCircleOutlined, DeleteOutlined, EditOutlined, EyeOutlined, PlusOutlined, ReloadOutlined, ScanOutlined, SendOutlined } from '@ant-design/icons';
import { api } from '../../api/client';
import type { StorageEndpoint, StorageObject, StorageScanJob } from '../../api/types';
import { normalizeError } from '../imagery/utils';

const endpointTypes = [
  { value: 'local_directory', label: '本地目录' },
  { value: 'nas_smb', label: 'NAS / SMB' },
  { value: 's3', label: 'S3（规划中）', disabled: true },
  { value: 'ftp', label: 'FTP（规划中）', disabled: true }
];
const typeLabel = Object.fromEntries(endpointTypes.map((item) => [item.value, item.label]));
const statusLabel: Record<string, string> = { configured: '已配置', online: '正常', degraded: '降级', offline: '不可用', permission_denied: '无权限', error: '错误', checking: '检查中', scanning: '扫描中', failed: '失败', pending: '等待', running: '扫描中', succeeded: '完成' };
const jobStatusColor: Record<string, string> = { succeeded: 'success', done: 'success', failed: 'error', running: 'processing', pending: 'default' };
const storageModeOptions = [
  { value: 'reference', label: '引用' },
  { value: 'managed', label: '托管' }
];
type EndpointPayload = Pick<StorageEndpoint, 'name' | 'endpoint_type' | 'root_uri' | 'mode'>;
type StorageApi = typeof api & {
  updateStorageEndpoint: (id: string, payload: EndpointPayload) => Promise<StorageEndpoint>;
  deleteStorageEndpoint: (id: string) => Promise<void>;
  storageScanJob: (id: string) => Promise<StorageScanJob>;
  storageObject: (id: string) => Promise<StorageObject>;
};
const storageApi = api as StorageApi;

export function StorageManagementPage() {
  const { message } = AntdApp.useApp();
  const [form] = Form.useForm();
  const [editForm] = Form.useForm<EndpointPayload>();
  const [endpoints, setEndpoints] = useState<StorageEndpoint[]>([]);
  const [jobs, setJobs] = useState<StorageScanJob[]>([]);
  const [objects, setObjects] = useState<StorageObject[]>([]);
  const [selectedEndpoint, setSelectedEndpoint] = useState<StorageEndpoint>();
  const [selectedObjectIds, setSelectedObjectIds] = useState<string[]>([]);
  const [loading, setLoading] = useState(false);
  const [objectLoading, setObjectLoading] = useState(false);
  const [editingEndpoint, setEditingEndpoint] = useState<StorageEndpoint>();
  const [savingEndpoint, setSavingEndpoint] = useState(false);
  const [jobDetail, setJobDetail] = useState<StorageScanJob>();
  const [objectDetail, setObjectDetail] = useState<StorageObject>();
  const [detailLoading, setDetailLoading] = useState(false);

  const load = async () => {
    setLoading(true);
    try {
      const [nextEndpoints, nextJobs] = await Promise.all([api.storageEndpoints(), api.storageScanJobs()]);
      setEndpoints(nextEndpoints); setJobs(nextJobs);
      if (selectedEndpoint) setSelectedEndpoint(nextEndpoints.find((item) => item.id === selectedEndpoint.id));
    } catch (error) { message.error(normalizeError(error)); } finally { setLoading(false); }
  };
  useEffect(() => { void load(); }, []);

  const openObjects = async (endpoint: StorageEndpoint) => {
    setSelectedEndpoint(endpoint); setSelectedObjectIds([]); setObjectLoading(true);
    try { setObjects(await api.storageObjects(endpoint.id)); } catch (error) { message.error(normalizeError(error)); } finally { setObjectLoading(false); }
  };
  const createEndpoint = async () => {
    try { await api.createStorageEndpoint(await form.validateFields()); form.resetFields(); message.success('存储源已登记'); await load(); }
    catch (error) { message.error(normalizeError(error)); }
  };
  const run = async (endpoint: StorageEndpoint, mode: 'health_check' | 'incremental' | 'full') => {
    try { await (mode === 'health_check' ? api.checkStorageEndpoint(endpoint.id) : api.scanStorageEndpoint(endpoint.id, { mode })); message.success(mode === 'health_check' ? '健康检查已完成' : `${mode === 'full' ? '全量' : '增量'}扫描已提交`); await load(); if (selectedEndpoint?.id === endpoint.id) await openObjects(endpoint); }
    catch (error) { message.error(normalizeError(error)); }
  };
  const openEdit = (endpoint: StorageEndpoint) => { setEditingEndpoint(endpoint); editForm.setFieldsValue({ name: endpoint.name, endpoint_type: endpoint.endpoint_type, root_uri: endpoint.root_uri, mode: endpoint.mode }); };
  const saveEdit = async () => {
    if (!editingEndpoint) return;
    setSavingEndpoint(true);
    try { await storageApi.updateStorageEndpoint(editingEndpoint.id, await editForm.validateFields()); message.success('存储源已更新'); setEditingEndpoint(undefined); await load(); }
    catch (error) { message.error(normalizeError(error)); } finally { setSavingEndpoint(false); }
  };
  const disableEndpoint = async (endpoint: StorageEndpoint) => {
    try { await storageApi.deleteStorageEndpoint(endpoint.id); message.success('存储源已禁用'); if (selectedEndpoint?.id === endpoint.id) { setSelectedEndpoint(undefined); setObjects([]); } await load(); }
    catch (error) { message.error(normalizeError(error)); }
  };
  const showJob = async (job: StorageScanJob) => { setDetailLoading(true); setJobDetail(job); try { setJobDetail(await storageApi.storageScanJob(job.id)); } catch (error) { message.error(normalizeError(error)); } finally { setDetailLoading(false); } };
  const showObject = async (object: StorageObject) => { setDetailLoading(true); setObjectDetail(object); try { setObjectDetail(await storageApi.storageObject(object.id)); } catch (error) { message.error(normalizeError(error)); } finally { setDetailLoading(false); } };
  const ingest = async () => {
    if (!selectedEndpoint || !selectedObjectIds.length) return;
    try { await api.ingestStorageObjects(selectedEndpoint.id, { object_ids: selectedObjectIds }); message.success('引用登记任务已创建'); setSelectedObjectIds([]); }
    catch (error) { message.error(normalizeError(error)); }
  };
  const activeObjects = useMemo(() => objects.filter((item) => !item.missing_confirmed), [objects]);
  return <Layout className="page-shell"><div className="data-page">
    <div className="page-header"><div><Typography.Title level={2}>存储管理</Typography.Title><Typography.Text type="secondary">登记已有目录并以引用方式接入影像</Typography.Text></div><Button icon={<ReloadOutlined />} onClick={() => void load()}>刷新</Button></div>
    <Row gutter={16} className="management-metrics"><Col span={6}><Card><Statistic title="存储源" value={endpoints.length} /></Card></Col><Col span={6}><Card><Statistic title="正常存储源" value={endpoints.filter((item) => item.status === 'online').length} /></Card></Col><Col span={6}><Card><Statistic title="扫描任务" value={jobs.length} /></Card></Col><Col span={6}><Card><Statistic title="已发现对象" value={objects.length} /></Card></Col></Row>
    <Card title="登记存储源" className="section-card"><Alert type="info" showIcon message="引用：直接使用原目录中的文件，平台不复制数据；原目录必须持续可访问。托管：登记入库时将文件复制到平台管理的存储目录，后续不依赖原目录，但会占用平台存储空间。" style={{ marginBottom: 16 }} /><Form form={form} layout="inline" onFinish={() => void createEndpoint()}><Form.Item name="name" rules={[{ required: true, message: '请输入名称' }]}><Input placeholder="名称" /></Form.Item><Form.Item name="endpoint_type" initialValue="local_directory"><Select options={endpointTypes} style={{ width: 170 }} /></Form.Item><Form.Item name="root_uri" rules={[{ required: true, message: '请输入目录或地址' }]}><Input placeholder="D:\\影像目录或 UNC 路径" style={{ width: 300 }} /></Form.Item><Form.Item name="mode" initialValue="reference"><Select options={storageModeOptions} style={{ width: 110 }} /></Form.Item><Button type="primary" htmlType="submit" icon={<PlusOutlined />}>登记</Button></Form></Card>
    <Card title="存储源" className="section-card"><Table rowKey="id" tableLayout="fixed" loading={loading} dataSource={endpoints} pagination={false} columns={[{ title: '名称', dataIndex: 'name', width: '12%', ellipsis: true }, { title: '类型', dataIndex: 'endpoint_type', width: '10%', render: (v: string) => typeLabel[v] ?? v }, { title: '目录', dataIndex: 'root_uri', width: '24%', ellipsis: true }, { title: '模式', dataIndex: 'mode', width: '7%', render: (v: string) => v === 'reference' ? '引用' : '托管' }, { title: '状态', dataIndex: 'status', width: '8%', render: (v: string, r) => <Tag color={!r.enabled ? 'default' : ['error', 'offline', 'permission_denied'].includes(v) ? 'error' : v === 'online' ? 'success' : 'default'}>{!r.enabled ? '已禁用' : statusLabel[v] ?? v}</Tag> }, { title: '最近扫描', dataIndex: 'last_scan_at', width: '13%', render: (v: string | null) => v ? new Date(v).toLocaleString() : '未扫描' }, { title: '操作', key: 'actions', width: '26%', render: (_, record: StorageEndpoint) => <Space size={4} wrap><Button size="small" icon={<CheckCircleOutlined />} disabled={!record.enabled} onClick={() => void run(record, 'health_check')}>检查</Button><Button size="small" icon={<ScanOutlined />} disabled={!record.enabled} onClick={() => void run(record, 'incremental')}>增量</Button><Button size="small" icon={<ScanOutlined />} disabled={!record.enabled} onClick={() => void run(record, 'full')}>全量</Button><Button size="small" icon={<EyeOutlined />} onClick={() => void openObjects(record)}>对象</Button><Button size="small" icon={<EditOutlined />} onClick={() => openEdit(record)}>编辑</Button>{record.enabled && <Popconfirm title="禁用存储源" description="禁用后不会删除已发现对象，确定继续？" onConfirm={() => void disableEndpoint(record)}><Button size="small" danger icon={<DeleteOutlined />}>禁用</Button></Popconfirm>}</Space> }]} locale={{ emptyText: <Empty description="尚未登记存储源" /> }} /></Card>
    <Row gutter={16}><Col span={15}><Card title={selectedEndpoint ? `对象列表 · ${selectedEndpoint.name}` : '对象列表'} extra={selectedEndpoint && <Button type="primary" icon={<SendOutlined />} disabled={!selectedObjectIds.length} onClick={() => void ingest()}>创建引用登记任务（{selectedObjectIds.length}）</Button>}><Table rowKey="id" tableLayout="fixed" loading={objectLoading} dataSource={activeObjects} rowSelection={{ selectedRowKeys: selectedObjectIds, onChange: (keys) => setSelectedObjectIds(keys.map(String)) }} pagination={{ pageSize: 12 }} columns={[{ title: '对象路径', dataIndex: 'object_key', width: '38%', ellipsis: true }, { title: '产品组', dataIndex: 'scene_group_key', width: '25%', ellipsis: true }, { title: '角色', dataIndex: 'scene_role', width: '11%' }, { title: '大小', dataIndex: 'size_bytes', width: '11%', render: (v: number) => `${(v / 1024 / 1024).toFixed(1)} MB` }, { title: '状态', dataIndex: 'status', width: '8%' }, { title: '', width: '7%', render: (_, r) => <Button type="link" size="small" onClick={() => void showObject(r)}>详情</Button> }]} locale={{ emptyText: <Empty description="请选择存储源查看对象" /> }} /></Card></Col><Col span={9}><Card title="扫描任务"><Table rowKey="id" tableLayout="fixed" size="small" loading={loading} dataSource={jobs.slice(0, 10)} pagination={false} columns={[{ title: '存储源', dataIndex: 'endpoint_name', width: '30%', ellipsis: true }, { title: '类型', dataIndex: 'mode', width: '23%', render: (v: string) => v === 'health_check' ? '健康检查' : v === 'full' ? '全量扫描' : '增量扫描' }, { title: '状态', dataIndex: 'status', width: '18%', render: (v: string) => <Tag color={jobStatusColor[v]}>{statusLabel[v] ?? v}</Tag> }, { title: '文件', dataIndex: 'files_scanned', width: '13%' }, { title: '', width: '16%', render: (_, r) => <Button type="link" size="small" onClick={() => void showJob(r)}>详情</Button> }]} locale={{ emptyText: <Empty description="暂无扫描任务" /> }} /></Card>{selectedEndpoint && <Card title="存储源信息" className="section-card"><Descriptions column={1} size="small"><Descriptions.Item label="名称">{selectedEndpoint.name}</Descriptions.Item><Descriptions.Item label="类型">{typeLabel[selectedEndpoint.endpoint_type] ?? selectedEndpoint.endpoint_type}</Descriptions.Item><Descriptions.Item label="路径">{selectedEndpoint.root_uri}</Descriptions.Item><Descriptions.Item label="更新时间">{selectedEndpoint.last_check_at ? new Date(selectedEndpoint.last_check_at).toLocaleString() : '未检查'}</Descriptions.Item></Descriptions></Card>}</Col></Row>
    <Modal title="编辑存储源" open={Boolean(editingEndpoint)} confirmLoading={savingEndpoint} okText="保存" cancelText="取消" onOk={() => void saveEdit()} onCancel={() => setEditingEndpoint(undefined)} destroyOnHidden><Form form={editForm} layout="vertical"><Form.Item name="name" label="名称" rules={[{ required: true }]}><Input /></Form.Item><Form.Item name="endpoint_type" label="类型" rules={[{ required: true }]}><Select options={endpointTypes} /></Form.Item><Form.Item name="root_uri" label="目录或地址" rules={[{ required: true }]}><Input /></Form.Item><Form.Item name="mode" label="管理模式" extra="引用依赖原目录持续可访问；托管会在登记入库时复制文件到平台存储。" rules={[{ required: true }]}><Select options={storageModeOptions} /></Form.Item></Form></Modal>
    <Modal title="扫描任务详情" open={Boolean(jobDetail)} loading={detailLoading} footer={null} onCancel={() => setJobDetail(undefined)} width={680}><Descriptions bordered size="small" column={2}><Descriptions.Item label="任务 ID" span={2}>{jobDetail?.id}</Descriptions.Item><Descriptions.Item label="存储源">{jobDetail?.endpoint_name ?? jobDetail?.endpoint}</Descriptions.Item><Descriptions.Item label="扫描类型">{jobDetail?.mode === 'full' ? '全量扫描' : jobDetail?.mode === 'health_check' ? '健康检查' : '增量扫描'}</Descriptions.Item><Descriptions.Item label="状态"><Tag color={jobStatusColor[jobDetail?.status ?? '']}>{statusLabel[jobDetail?.status ?? ''] ?? jobDetail?.status ?? '-'}</Tag></Descriptions.Item><Descriptions.Item label="扫描文件">{jobDetail?.files_scanned ?? 0}</Descriptions.Item><Descriptions.Item label="发现影像">{jobDetail?.scenes_found ?? 0}</Descriptions.Item><Descriptions.Item label="新增 / 变更">{jobDetail?.new_count ?? 0} / {jobDetail?.changed_count ?? 0}</Descriptions.Item><Descriptions.Item label="缺失 / 未变化">{jobDetail?.missing_count ?? 0} / {jobDetail?.unchanged_count ?? 0}</Descriptions.Item><Descriptions.Item label="扫描前缀">{jobDetail?.prefix || '全部'}</Descriptions.Item><Descriptions.Item label="开始时间">{jobDetail?.started_at ? new Date(jobDetail.started_at).toLocaleString() : '-'}</Descriptions.Item><Descriptions.Item label="完成时间">{jobDetail?.finished_at ? new Date(jobDetail.finished_at).toLocaleString() : '-'}</Descriptions.Item><Descriptions.Item label="错误信息" span={2}><Typography.Text type={jobDetail?.error_message ? 'danger' : 'secondary'} style={{ whiteSpace: 'pre-wrap', overflowWrap: 'anywhere' }}>{jobDetail?.error_message || '无'}</Typography.Text></Descriptions.Item></Descriptions></Modal>
    <Modal title="存储对象详情" open={Boolean(objectDetail)} loading={detailLoading} footer={null} onCancel={() => setObjectDetail(undefined)} width={680}><Descriptions bordered size="small" column={1}><Descriptions.Item label="对象 ID">{objectDetail?.id}</Descriptions.Item><Descriptions.Item label="对象路径"><Typography.Text style={{ overflowWrap: 'anywhere' }}>{objectDetail?.object_key}</Typography.Text></Descriptions.Item><Descriptions.Item label="产品组">{objectDetail?.scene_group_key}</Descriptions.Item><Descriptions.Item label="场景名称">{objectDetail?.scene_stem || '-'}</Descriptions.Item><Descriptions.Item label="资产角色">{objectDetail?.scene_role}</Descriptions.Item><Descriptions.Item label="文件大小">{objectDetail ? `${(objectDetail.size_bytes / 1024 / 1024).toFixed(2)} MB` : '-'}</Descriptions.Item><Descriptions.Item label="状态">{objectDetail?.status}</Descriptions.Item><Descriptions.Item label="修改时间">{objectDetail?.modified_at ? new Date(objectDetail.modified_at).toLocaleString() : '-'}</Descriptions.Item><Descriptions.Item label="来源元数据"><Typography.Text style={{ whiteSpace: 'pre-wrap', overflowWrap: 'anywhere' }}>{objectDetail?.source_metadata ? JSON.stringify(objectDetail.source_metadata, null, 2) : '无'}</Typography.Text></Descriptions.Item></Descriptions></Modal>
  </div></Layout>;
}
