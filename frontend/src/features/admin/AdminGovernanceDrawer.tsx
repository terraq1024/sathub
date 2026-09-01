import { useEffect, useState } from 'react';
import { App as AntdApp, Button, Checkbox, Drawer, Empty, Form, Input, Modal, Select, Space, Table, Tabs, Tag, Typography } from 'antd';
import { CheckCircleOutlined, PlusOutlined, ScanOutlined } from '@ant-design/icons';
import { api } from '../../api/client';
import type { AuditEvent, CatalogEntry, MetadataSchema, ParserTemplate, StorageEndpoint, StorageObject, StorageScanJob } from '../../api/types';
import { normalizeError } from '../imagery/utils';

interface AdminGovernanceDrawerProps {
  open: boolean;
  onClose: () => void;
}

export function AdminGovernanceDrawer({ open, onClose }: AdminGovernanceDrawerProps) {
  const { message } = AntdApp.useApp();
  const [endpoints, setEndpoints] = useState<StorageEndpoint[]>([]);
  const [schemas, setSchemas] = useState<MetadataSchema[]>([]);
  const [templates, setTemplates] = useState<ParserTemplate[]>([]);
  const [classifications, setClassifications] = useState<CatalogEntry[]>([]);
  const [tags, setTags] = useState<CatalogEntry[]>([]);
  const [events, setEvents] = useState<AuditEvent[]>([]);
  const [objects, setObjects] = useState<StorageObject[]>([]);
  const [objectEndpoint, setObjectEndpoint] = useState<StorageEndpoint>();
  const [objectIds, setObjectIds] = useState<string[]>([]);
  const [objectModalOpen, setObjectModalOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const [storageForm] = Form.useForm();
  const [catalogForm] = Form.useForm();

  const load = async () => {
    setLoading(true);
    try {
      const [nextEndpoints, nextSchemas, nextTemplates, nextClassifications, nextTags, nextEvents] = await Promise.all([
        api.storageEndpoints(),
        api.metadataSchemas(),
        api.metadataTemplates(),
        api.catalogClassifications(),
        api.catalogTags(),
        api.auditEvents()
      ]);
      setEndpoints(nextEndpoints);
      setSchemas(nextSchemas);
      setTemplates(nextTemplates);
      setClassifications(nextClassifications);
      setTags(nextTags);
      setEvents(nextEvents);
    } catch (error) {
      message.error(normalizeError(error));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (open) void load();
  }, [open]);

  const createStorage = async () => {
    try {
      await api.createStorageEndpoint(await storageForm.validateFields());
      storageForm.resetFields();
      message.success('存储源已登记');
      await load();
    } catch (error) {
      message.error(normalizeError(error));
    }
  };

  const scan = async (endpoint: StorageEndpoint, mode: 'health_check' | 'incremental') => {
    try {
      const job = mode === 'health_check' ? await api.checkStorageEndpoint(endpoint.id) : await api.scanStorageEndpoint(endpoint.id, { mode });
      message.success(`${endpoint.name}：${job.status === 'succeeded' ? '检查完成' : '扫描已提交'}`);
      await load();
    } catch (error) {
      message.error(normalizeError(error));
    }
  };

  const openObjects = async (endpoint: StorageEndpoint) => {
    try {
      setObjectEndpoint(endpoint);
      setObjects(await api.storageObjects(endpoint.id));
      setObjectIds([]);
      setObjectModalOpen(true);
    } catch (error) {
      message.error(normalizeError(error));
    }
  };

  const ingestObjects = async () => {
    if (!objectEndpoint || !objectIds.length) return;
    try {
      await api.ingestStorageObjects(objectEndpoint.id, { object_ids: objectIds });
      message.success('引用登记任务已创建');
      setObjectModalOpen(false);
    } catch (error) {
      message.error(normalizeError(error));
    }
  };

  const createCatalogEntry = async () => {
    try {
      const values = await catalogForm.validateFields();
      if (values.kind === 'tag') await api.createCatalogTag({ name: values.name, color: values.color || '#1677ff' });
      else await api.createCatalogClassification({ name: values.name, code: values.code || values.name });
      catalogForm.resetFields();
      message.success('目录项已创建');
      await load();
    } catch (error) {
      message.error(normalizeError(error));
    }
  };

  return (
    <Drawer className="governance-drawer" title="治理设置" open={open} onClose={onClose} width={760} destroyOnClose>
      <Tabs items={[
        {
          key: 'storage',
          label: '存储源',
          children: <Space direction="vertical" size={16} className="full-width">
            <Form form={storageForm} layout="inline" onFinish={() => void createStorage()}>
              <Form.Item name="name" rules={[{ required: true, message: '请输入名称' }]}><Input placeholder="名称" /></Form.Item>
              <Form.Item name="endpoint_type" initialValue="local_directory"><Select style={{ width: 150 }} options={[{ value: 'local_directory', label: '本地目录' }, { value: 'nas_smb', label: 'NAS / SMB' }]} /></Form.Item>
              <Form.Item name="root_uri" rules={[{ required: true, message: '请输入目录' }]}><Input placeholder="D:\\影像目录或 UNC 路径" /></Form.Item>
              <Form.Item name="mode" initialValue="reference"><Select style={{ width: 100 }} options={[{ value: 'reference', label: '引用' }, { value: 'managed', label: '托管' }]} /></Form.Item>
              <Button type="primary" htmlType="submit" icon={<PlusOutlined />}>登记</Button>
            </Form>
            <Table<StorageEndpoint> rowKey="id" loading={loading} dataSource={endpoints} pagination={false} size="small" columns={[
              { title: '名称', dataIndex: 'name' },
              { title: '类型', dataIndex: 'endpoint_type' },
              { title: '模式', dataIndex: 'mode', render: (value: string) => value === 'reference' ? '引用' : '托管' },
              { title: '状态', dataIndex: 'status', render: (value: string) => <Tag color={value === 'online' ? 'success' : 'default'}>{value}</Tag> },
              { title: '操作', key: 'actions', render: (_, endpoint) => <Space><Button size="small" icon={<CheckCircleOutlined />} onClick={() => void scan(endpoint, 'health_check')}>检查</Button><Button size="small" icon={<ScanOutlined />} onClick={() => void scan(endpoint, 'incremental')}>扫描</Button><Button size="small" onClick={() => void openObjects(endpoint)}>登记影像</Button></Space> }
            ]} locale={{ emptyText: <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="尚未登记存储源" /> }} />
          </Space>
        },
        {
          key: 'metadata',
          label: '元数据规则',
          children: <Space direction="vertical" className="full-width">
            <Typography.Text type="secondary">已发布规则在入库时作为补充解析器，未匹配时继续使用内置解析器。</Typography.Text>
            <Table<MetadataSchema> rowKey="id" loading={loading} dataSource={schemas} pagination={false} size="small" columns={[{ title: 'Schema', dataIndex: 'name' }, { title: '编码', dataIndex: 'code' }, { title: '版本', dataIndex: 'version' }, { title: '状态', dataIndex: 'status' }, { title: '字段', dataIndex: 'fields', render: (value: MetadataSchema['fields']) => value?.length ?? 0 }]} />
            <Table<ParserTemplate> rowKey="id" loading={loading} dataSource={templates} pagination={false} size="small" columns={[{ title: '模板', dataIndex: 'name' }, { title: 'Schema', dataIndex: 'schema_code' }, { title: '优先级', dataIndex: 'priority' }, { title: '状态', dataIndex: 'status' }]} />
          </Space>
        },
        {
          key: 'catalog',
          label: '分类与标签',
          children: <Space direction="vertical" className="full-width">
            <Form form={catalogForm} layout="inline" onFinish={() => void createCatalogEntry()}>
              <Form.Item name="kind" initialValue="classification"><Select style={{ width: 120 }} options={[{ value: 'classification', label: '分类' }, { value: 'tag', label: '标签' }]} /></Form.Item>
              <Form.Item name="name" rules={[{ required: true, message: '请输入名称' }]}><Input placeholder="名称" /></Form.Item>
              <Form.Item name="code"><Input placeholder="分类编码（可选）" /></Form.Item>
              <Button type="primary" htmlType="submit" icon={<PlusOutlined />}>创建</Button>
            </Form>
            <Space wrap>{classifications.map((item) => <Tag key={`c-${item.id}`} color="blue">分类：{item.name}</Tag>)}{tags.map((item) => <Tag key={`t-${item.id}`} color={item.color}>标签：{item.name}</Tag>)}</Space>
          </Space>
        },
        {
          key: 'audit',
          label: '审计',
          children: <Table<AuditEvent> rowKey="id" loading={loading} dataSource={events} pagination={{ pageSize: 10 }} size="small" columns={[{ title: '时间', dataIndex: 'created_at', render: (value: string) => new Date(value).toLocaleString() }, { title: '动作', dataIndex: 'action' }, { title: '对象', key: 'object', render: (_, event) => `${event.object_type}:${event.object_id}` }, { title: '用户', dataIndex: 'actor', render: (value: AuditEvent['actor']) => value?.username ?? '系统' }]} />
        }
      ]} />
      <Modal title={`登记 ${objectEndpoint?.name ?? ''} 中的影像`} open={objectModalOpen} onCancel={() => setObjectModalOpen(false)} onOk={() => void ingestObjects()} okText="创建登记任务" cancelText="取消">
        <Typography.Paragraph type="secondary">选择包含主数据文件的产品组，平台会引用原目录，不复制主影像。</Typography.Paragraph>
        <Checkbox.Group value={objectIds} onChange={(values) => setObjectIds(values.map(String))} className="full-width">
          <Space direction="vertical" className="full-width">
            {objects.filter((object) => !object.missing_confirmed).map((object) => <Checkbox key={object.id} value={object.id}>{object.scene_group_key} <Typography.Text type="secondary">({object.scene_role})</Typography.Text></Checkbox>)}
          </Space>
        </Checkbox.Group>
      </Modal>
    </Drawer>
  );
}
