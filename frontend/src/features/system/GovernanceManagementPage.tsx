import { useEffect, useState } from 'react';
import { App, Button, Card, Col, Descriptions, Empty, Form, Input, Modal, Row, Select, Space, Table, Tabs, Tag, Typography } from 'antd';
import { EditOutlined, PlusOutlined, ReloadOutlined, SearchOutlined, StopOutlined } from '@ant-design/icons';
import { api } from '../../api/client';
import type { AdministrativeUnit, AuditEvent, CatalogEntry, MetadataOverride, MetadataQualityIssue } from '../../api/types';
import { normalizeError } from '../imagery/utils';

const date = (value?: string | null) => value ? new Date(value).toLocaleString() : '-';

interface GovernanceAssociation {
  administrative_units?: Array<{ administrative_unit?: number; name?: string; code?: string; level?: string; relation?: string; coverage_ratio?: number }>;
  classifications?: Array<{ classification?: number; classification_name?: string; source?: string; confidence?: number }>;
  tags?: Array<{ tag?: number; tag_name?: string }>;
}

interface CatalogAssociationPayload {
  object_type: 'imagery' | 'dataset';
  object_ids: string[];
  classification_ids: number[];
  tag_ids: number[];
  replace: boolean;
}

const governanceApi = api as typeof api & {
  updateCatalogClassification: (id: number, payload: Record<string, unknown>) => Promise<CatalogEntry>;
  deleteCatalogClassification: (id: number) => Promise<void>;
  updateCatalogTag: (id: number, payload: Record<string, unknown>) => Promise<CatalogEntry>;
  deleteCatalogTag: (id: number) => Promise<void>;
  associateCatalog: (payload: CatalogAssociationPayload) => Promise<unknown>;
  imageryGovernance: (imageryId: string) => Promise<GovernanceAssociation>;
};

export function GovernanceManagementPage() {
  const { message } = App.useApp();
  const [classifications, setClassifications] = useState<CatalogEntry[]>([]);
  const [tags, setTags] = useState<CatalogEntry[]>([]);
  const [units, setUnits] = useState<AdministrativeUnit[]>([]);
  const [events, setEvents] = useState<AuditEvent[]>([]);
  const [allEvents, setAllEvents] = useState<AuditEvent[]>([]);
  const [issues, setIssues] = useState<MetadataQualityIssue[]>([]);
  const [overrides, setOverrides] = useState<MetadataOverride[]>([]);
  const [loading, setLoading] = useState(false);
  const [catalogForm] = Form.useForm();
  const [overrideForm] = Form.useForm();
  const [auditQuery, setAuditQuery] = useState({ action: '', object_type: '' });
  const [issueQuery, setIssueQuery] = useState({ imagery_id: '', status: '', severity: '' });
  const [overrideImagery, setOverrideImagery] = useState('');
  const [detail, setDetail] = useState<unknown>();
  const [editingCatalog, setEditingCatalog] = useState<{ kind: 'classification' | 'tag'; item: CatalogEntry }>();
  const [editForm] = Form.useForm();
  const [associationForm] = Form.useForm();
  const [governanceImageryId, setGovernanceImageryId] = useState('');
  const [governance, setGovernance] = useState<GovernanceAssociation>();
  const [submitting, setSubmitting] = useState(false);

  const load = async () => {
    setLoading(true);
    try {
      const [c, t, u, a, q, o] = await Promise.all([
        api.catalogClassifications(), api.catalogTags(), api.administrativeUnits(),
        api.auditEvents(), api.qualityIssues(issueQuery.imagery_id ? { imagery_id: issueQuery.imagery_id, status: issueQuery.status, severity: issueQuery.severity } : {}),
        api.metadataOverrides(overrideImagery || undefined)
      ]);
      setClassifications(c); setTags(t); setUnits(u); setAllEvents(a); setEvents(a); setIssues(q); setOverrides(o);
    } catch (error) { message.error(normalizeError(error)); } finally { setLoading(false); }
  };
  useEffect(() => { void load(); }, []);

  const createCatalog = async () => {
    try { const v = await catalogForm.validateFields(); if (v.kind === 'tag') await api.createCatalogTag({ name: v.name, color: v.color || '#1677ff', description: v.description }); else await api.createCatalogClassification({ name: v.name, code: v.code || v.name, description: v.description }); catalogForm.resetFields(); message.success('已创建'); await load(); }
    catch (error) { message.error(normalizeError(error)); }
  };
  const createOverride = async () => {
    try { await api.createMetadataOverride(await overrideForm.validateFields()); overrideForm.resetFields(); message.success('覆盖值已登记'); await load(); }
    catch (error) { message.error(normalizeError(error)); }
  };
  const filterIssues = async () => { try { setIssues(await api.qualityIssues(Object.fromEntries(Object.entries(issueQuery).filter(([, v]) => v)))); } catch (e) { message.error(normalizeError(e)); } };
  const filterOverrides = async () => { try { setOverrides(await api.metadataOverrides(overrideImagery || undefined)); } catch (e) { message.error(normalizeError(e)); } };

  const openCatalogEdit = (kind: 'classification' | 'tag', item: CatalogEntry) => {
    setEditingCatalog({ kind, item });
    editForm.setFieldsValue({ name: item.name, code: item.code, description: item.description, color: item.color, enabled: item.enabled !== false ? 'yes' : 'no' });
  };
  const saveCatalog = async () => {
    if (!editingCatalog) return;
    setSubmitting(true);
    try {
      const values = await editForm.validateFields();
      const payload = { ...values, enabled: values.enabled !== 'no' };
      if (editingCatalog.kind === 'tag') await governanceApi.updateCatalogTag(editingCatalog.item.id, payload);
      else await governanceApi.updateCatalogClassification(editingCatalog.item.id, payload);
      message.success('目录项已更新'); setEditingCatalog(undefined); await load();
    } catch (error) { message.error(normalizeError(error)); } finally { setSubmitting(false); }
  };
  const disableCatalog = async (kind: 'classification' | 'tag', item: CatalogEntry) => {
    try {
      if (kind === 'tag') await governanceApi.deleteCatalogTag(item.id); else await governanceApi.deleteCatalogClassification(item.id);
      message.success(`${item.name} 已停用`); await load();
    } catch (error) { message.error(normalizeError(error)); }
  };
  const associate = async () => {
    setSubmitting(true);
    try {
      const values = await associationForm.validateFields();
      const objectIds = String(values.object_ids).split(/[\s,，]+/).map(value => value.trim()).filter(Boolean);
      await governanceApi.associateCatalog({ object_type: values.object_type, object_ids: objectIds, classification_ids: values.classification_ids || [], tag_ids: values.tag_ids || [], replace: Boolean(values.replace) });
      message.success(`已关联 ${objectIds.length} 个对象`); associationForm.resetFields();
    } catch (error) { message.error(normalizeError(error)); } finally { setSubmitting(false); }
  };
  const queryGovernance = async () => {
    if (!governanceImageryId.trim()) { message.warning('请输入影像 ID'); return; }
    setSubmitting(true);
    try { setGovernance(await governanceApi.imageryGovernance(governanceImageryId.trim())); }
    catch (error) { message.error(normalizeError(error)); } finally { setSubmitting(false); }
  };

  return <div className="system-management-page">
    <Space direction="vertical" size={20} style={{ width: '100%' }}>
      <div><Typography.Title level={2}>系统管理</Typography.Title><Typography.Text type="secondary">目录、元数据与审计治理</Typography.Text></div>
      <Tabs items={[
        { key: 'catalog', label: '分类与标签', children: <Space direction="vertical" size={16} style={{ width: '100%' }}>
          <Row gutter={20}><Col span={8}><Card title="新建目录项"><Form form={catalogForm} layout="vertical" onFinish={() => void createCatalog()}><Form.Item name="kind" label="类型" initialValue="classification"><Select options={[{ value: 'classification', label: '分类' }, { value: 'tag', label: '标签' }]} /></Form.Item><Form.Item name="name" label="名称" rules={[{ required: true }]}><Input /></Form.Item><Form.Item name="code" label="编码"><Input /></Form.Item><Form.Item name="description" label="说明"><Input.TextArea rows={2} /></Form.Item><Button type="primary" htmlType="submit" icon={<PlusOutlined />}>创建</Button></Form></Card></Col>
          <Col span={16}><Card title="分类目录"><Table tableLayout="fixed" size="small" rowKey="id" dataSource={classifications} loading={loading} pagination={{ pageSize: 6 }} columns={[{ title: '名称', dataIndex: 'name', ellipsis: true }, { title: '编码', dataIndex: 'code', ellipsis: true }, { title: '状态', dataIndex: 'enabled', width: 80, render: (v: boolean) => <Tag color={v === false ? 'default' : 'success'}>{v === false ? '停用' : '启用'}</Tag> }, { title: '操作', width: 150, render: (_, item) => <Space><Button type="link" size="small" icon={<EditOutlined />} onClick={() => openCatalogEdit('classification', item)}>编辑</Button>{item.enabled !== false && <Button danger type="link" size="small" icon={<StopOutlined />} onClick={() => void disableCatalog('classification', item)}>停用</Button>}</Space> }]} /></Card></Col></Row>
          <Card title="标签目录"><Table tableLayout="fixed" size="small" rowKey="id" dataSource={tags} loading={loading} pagination={{ pageSize: 8 }} columns={[{ title: '标签', dataIndex: 'name', render: (value, item) => <Tag color={item.color}>{value}</Tag> }, { title: '说明', dataIndex: 'description', ellipsis: true }, { title: '状态', dataIndex: 'enabled', width: 80, render: (v: boolean) => <Tag color={v === false ? 'default' : 'success'}>{v === false ? '停用' : '启用'}</Tag> }, { title: '操作', width: 150, render: (_, item) => <Space><Button type="link" size="small" icon={<EditOutlined />} onClick={() => openCatalogEdit('tag', item)}>编辑</Button>{item.enabled !== false && <Button danger type="link" size="small" icon={<StopOutlined />} onClick={() => void disableCatalog('tag', item)}>停用</Button>}</Space> }]} /></Card>
          <Row gutter={20}><Col span={12}><Card title="批量关联"><Form form={associationForm} layout="vertical" onFinish={() => void associate()} initialValues={{ object_type: 'imagery', replace: false }}><Form.Item name="object_type" label="关联对象"><Select options={[{ value: 'imagery', label: '影像' }, { value: 'dataset', label: '数据集' }]} /></Form.Item><Form.Item name="object_ids" label="对象 ID" rules={[{ required: true, message: '请输入至少一个对象 ID' }]}><Input.TextArea rows={3} placeholder="每行一个 ID，也可使用逗号分隔" /></Form.Item><Form.Item name="classification_ids" label="分类"><Select mode="multiple" allowClear optionFilterProp="label" options={classifications.filter(item => item.enabled !== false).map(item => ({ value: item.id, label: item.name }))} /></Form.Item><Form.Item name="tag_ids" label="标签"><Select mode="multiple" allowClear optionFilterProp="label" options={tags.filter(item => item.enabled !== false).map(item => ({ value: item.id, label: item.name }))} /></Form.Item><Form.Item name="replace" label="关联方式"><Select options={[{ value: false, label: '追加关联' }, { value: true, label: '替换现有关联' }]} /></Form.Item><Button type="primary" htmlType="submit" loading={submitting}>执行关联</Button></Form></Card></Col>
          <Col span={12}><Card title="影像治理关联" extra={<Space.Compact><Input value={governanceImageryId} onChange={event => setGovernanceImageryId(event.target.value)} onPressEnter={() => void queryGovernance()} placeholder="输入影像 ID" /><Button icon={<SearchOutlined />} loading={submitting} onClick={() => void queryGovernance()}>查询</Button></Space.Compact>}>
            {!governance ? <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="输入影像 ID 查询关联信息" /> : <Space direction="vertical" size={16} style={{ width: '100%' }}><div><Typography.Text strong>分类</Typography.Text><div>{governance.classifications?.map(item => <Tag key={item.classification}>{item.classification_name || item.classification}</Tag>)}{!governance.classifications?.length && <Typography.Text type="secondary"> 未关联</Typography.Text>}</div></div><div><Typography.Text strong>标签</Typography.Text><div>{governance.tags?.map(item => <Tag key={item.tag}>{item.tag_name || item.tag}</Tag>)}{!governance.tags?.length && <Typography.Text type="secondary"> 未关联</Typography.Text>}</div></div><div><Typography.Text strong>行政区划</Typography.Text><Table tableLayout="fixed" size="small" rowKey={item => String(item.administrative_unit)} pagination={false} dataSource={governance.administrative_units || []} columns={[{ title: '名称', dataIndex: 'name', ellipsis: true }, { title: '编码', dataIndex: 'code', ellipsis: true }, { title: '关系', dataIndex: 'relation' }, { title: '覆盖率', dataIndex: 'coverage_ratio', render: value => value == null ? '-' : `${(Number(value) * 100).toFixed(1)}%` }]} /></div></Space>}
          </Card></Col></Row>
        </Space> },
        { key: 'units', label: '行政区划', children: <Card title="行政区划目录"><Table size="small" rowKey="id" loading={loading} dataSource={units} pagination={{ pageSize: 15 }} columns={[{ title: '名称', dataIndex: 'name' }, { title: '层级', dataIndex: 'level' }, { title: '编码', dataIndex: 'code' }, { title: '数据版本', dataIndex: 'source_version' }, { title: '范围', dataIndex: 'bbox', render: (v: unknown) => v ? JSON.stringify(v) : '-' }]} /></Card> },
        { key: 'audit', label: '审计记录', children: <Card title="审计记录" extra={<Space><Input placeholder="动作" value={auditQuery.action} onChange={e => setAuditQuery({ ...auditQuery, action: e.target.value })} /><Input placeholder="对象类型" value={auditQuery.object_type} onChange={e => setAuditQuery({ ...auditQuery, object_type: e.target.value })} /><Button icon={<SearchOutlined />} onClick={() => setEvents(allEvents.filter(e => (!auditQuery.action || e.action.includes(auditQuery.action)) && (!auditQuery.object_type || e.object_type.includes(auditQuery.object_type))))}>检索</Button><Button icon={<ReloadOutlined />} title="刷新" onClick={() => void load()} /></Space>}><Table size="small" rowKey="id" loading={loading} dataSource={events} pagination={{ pageSize: 12 }} onRow={record => ({ onClick: () => setDetail(record) })} columns={[{ title: '时间', dataIndex: 'created_at', render: date }, { title: '动作', dataIndex: 'action' }, { title: '对象', render: (_, r) => `${r.object_type}:${r.object_id}` }, { title: '用户', render: (_, r) => r.actor?.username || '系统' }]} /></Card> },
        { key: 'quality', label: '质量问题', children: <Card title="元数据质量问题" extra={<Space><Input placeholder="影像 ID" value={issueQuery.imagery_id} onChange={e => setIssueQuery({ ...issueQuery, imagery_id: e.target.value })} /><Select allowClear placeholder="严重级别" style={{ width: 120 }} onChange={severity => setIssueQuery({ ...issueQuery, severity })} options={['warning', 'error', 'critical'].map(v => ({ value: v, label: v }))} /><Button icon={<SearchOutlined />} onClick={() => void filterIssues()} /></Space>}><Table size="small" rowKey="id" loading={loading} dataSource={issues} onRow={record => ({ onClick: () => setDetail(record) })} columns={[{ title: '影像', dataIndex: 'imagery' }, { title: '字段', dataIndex: 'field_key' }, { title: '级别', dataIndex: 'severity' }, { title: '问题', dataIndex: 'message' }, { title: '状态', dataIndex: 'status' }, { title: '时间', dataIndex: 'created_at', render: date }]} /></Card> },
        { key: 'overrides', label: '人工覆盖', children: <Row gutter={20}><Col span={10}><Card title="新增元数据覆盖"><Form form={overrideForm} layout="vertical" onFinish={() => void createOverride()}><Form.Item name="imagery" label="影像 ID" rules={[{ required: true }]}><Input /></Form.Item><Form.Item name="field_key" label="字段名" rules={[{ required: true }]}><Input placeholder="如 satellite_name" /></Form.Item><Form.Item name="value" label="覆盖值" rules={[{ required: true }]}><Input /></Form.Item><Form.Item name="reason" label="原因"><Input.TextArea rows={3} /></Form.Item><Button type="primary" htmlType="submit">登记覆盖</Button></Form></Card></Col><Col span={14}><Card title="覆盖记录" extra={<Space><Input placeholder="按影像 ID 查询" value={overrideImagery} onChange={e => setOverrideImagery(e.target.value)} /><Button icon={<SearchOutlined />} onClick={() => void filterOverrides()} /></Space>}><Table size="small" rowKey="id" loading={loading} dataSource={overrides} columns={[{ title: '影像', dataIndex: 'imagery' }, { title: '字段', dataIndex: 'field_key' }, { title: '值', dataIndex: 'value', render: v => String(v) }, { title: '原因', dataIndex: 'reason' }, { title: '时间', dataIndex: 'created_at', render: date }]} /></Card></Col></Row> }
      ]} />
    </Space>
    <Modal open={Boolean(detail)} onCancel={() => setDetail(undefined)} footer={null} title="详细信息"><Descriptions column={1} bordered size="small">{detail ? Object.entries(detail as Record<string, unknown>).map(([key, value]) => <Descriptions.Item key={key} label={key}>{typeof value === 'object' && value !== null ? String(JSON.stringify(value)) : String(value ?? '-')}</Descriptions.Item>) : null}</Descriptions></Modal>
    <Modal title={`编辑${editingCatalog?.kind === 'tag' ? '标签' : '分类'}`} open={Boolean(editingCatalog)} onCancel={() => setEditingCatalog(undefined)} onOk={() => void saveCatalog()} confirmLoading={submitting} okText="保存" cancelText="取消"><Form form={editForm} layout="vertical"><Form.Item name="name" label="名称" rules={[{ required: true }]}><Input /></Form.Item>{editingCatalog?.kind === 'classification' && <Form.Item name="code" label="编码" rules={[{ required: true }]}><Input /></Form.Item>}{editingCatalog?.kind === 'tag' && <Form.Item name="color" label="颜色"><Input /></Form.Item>}<Form.Item name="description" label="说明"><Input.TextArea rows={3} /></Form.Item><Form.Item name="enabled" hidden><Input /></Form.Item></Form></Modal>
  </div>;
}
