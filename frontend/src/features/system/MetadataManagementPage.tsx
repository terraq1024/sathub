import { useEffect, useMemo, useState } from 'react';
import { App as AntdApp, Button, Card, Col, Descriptions, Divider, Empty, Form, Input, InputNumber, Popconfirm, Row, Select, Space, Switch, Table, Tabs, Tag, Typography } from 'antd';
import { DeleteOutlined, EyeOutlined, PlayCircleOutlined, PlusOutlined, ReloadOutlined, SaveOutlined, SendOutlined } from '@ant-design/icons';
import { api } from '../../api/client';
import type { MetadataParserRun, MetadataSchema, MetadataSchemaField, ParserTemplate, ParserTemplateVersion } from '../../api/types';
const dataTypes = ['string', 'integer', 'float', 'boolean', 'datetime', 'enum', 'array', 'geometry', 'bbox', 'object'];
const emptyField = (): MetadataSchemaField => ({ key: '', label: '', data_type: 'string', unit: '', required: false, searchable: false, enum_values: [], validation: {}, display_order: 0 });

function jsonValue(value: string, fallback: Record<string, unknown> = {}) {
  try {
    const parsed = JSON.parse(value) as unknown;
    return parsed && typeof parsed === 'object' && !Array.isArray(parsed) ? parsed as Record<string, unknown> : fallback;
  } catch {
    throw new Error('JSON 格式不正确');
  }
}

function runStatus(status: string) {
  const colors: Record<string, string> = { running: 'processing', succeeded: 'success', failed: 'error', dry_run: 'default' };
  const labels: Record<string, string> = { running: '执行中', succeeded: '成功', failed: '失败', dry_run: '试跑' };
  return <Tag color={colors[status]}>{labels[status] ?? status}</Tag>;
}

const dateTime = (value?: string | null) => value ? new Date(value).toLocaleString() : '-';

export default function MetadataManagementPage() {
  const { message } = AntdApp.useApp();
  const [schemas, setSchemas] = useState<MetadataSchema[]>([]);
  const [templates, setTemplates] = useState<ParserTemplate[]>([]);
  const [schema, setSchema] = useState<MetadataSchema | null>(null);
  const [template, setTemplate] = useState<ParserTemplate | null>(null);
  const [versions, setVersions] = useState<ParserTemplateVersion[]>([]);
  const [allVersions, setAllVersions] = useState<ParserTemplateVersion[]>([]);
  const [runs, setRuns] = useState<MetadataParserRun[]>([]);
  const [selectedRun, setSelectedRun] = useState<MetadataParserRun | null>(null);
  const [dryRunResult, setDryRunResult] = useState<Record<string, unknown> | null>(null);
  const [loading, setLoading] = useState(false);
  const [running, setRunning] = useState(false);
  const [schemaForm] = Form.useForm();
  const [templateForm] = Form.useForm();
  const [versionForm] = Form.useForm();
  const [dryRunForm] = Form.useForm();
  const [executeForm] = Form.useForm();

  const loadRuns = async () => {
    setRuns(await api.metadataRuns());
  };

  const reload = async () => {
    setLoading(true);
    try {
      const [nextSchemas, nextTemplates] = await Promise.all([api.metadataSchemas(), api.metadataTemplates()]);
      setSchemas(nextSchemas);
      setTemplates(nextTemplates);
      setAllVersions((await Promise.all(nextTemplates.map((item) => api.metadataVersions(item.id)))).flat());
      await loadRuns();
    } catch (error) {
      message.error(error instanceof Error ? error.message : '元数据治理数据加载失败');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { void reload(); }, []);

  const schemaOptions = useMemo(() => schemas.map((item) => ({ label: `${item.name} (${item.code})`, value: item.id })), [schemas]);
  const versionOptions = useMemo(() => allVersions.map((item) => ({ label: `${item.template_name ?? '模板'} ${item.version}`, value: item.id })), [allVersions]);

  const editSchema = (value?: MetadataSchema) => {
    setSchema(value ?? null);
    schemaForm.setFieldsValue(value ? {
      ...value,
      fields: (value.fields ?? []).map((field) => ({
        ...field,
        enum_values: Array.isArray(field.enum_values) ? field.enum_values.join(', ') : field.enum_values,
        validation: typeof field.validation === 'object' ? JSON.stringify(field.validation, null, 2) : field.validation
      }))
    } : { code: '', name: '', version: '1.0.0', status: 'draft', fields: [emptyField()] });
  };

  const saveSchema = async () => {
    try {
      const values = await schemaForm.validateFields();
      const payload = { ...values, fields: (values.fields ?? []).map((field: MetadataSchemaField, index: number) => ({
        ...field,
        display_order: field.display_order ?? index,
        enum_values: typeof field.enum_values === 'string' ? String(field.enum_values).split(',').map((item) => item.trim()).filter(Boolean) : field.enum_values,
        validation: typeof field.validation === 'string' ? jsonValue(field.validation) : (field.validation ?? {})
      })) };
      if (schema) await api.updateMetadataSchema(schema.id, payload); else await api.createMetadataSchema(payload);
      message.success('Schema 已保存');
      editSchema();
      await reload();
    } catch (error) {
      message.error(error instanceof Error ? error.message : '保存失败');
    }
  };

  const editTemplate = (value?: ParserTemplate) => {
    setTemplate(value ?? null);
    templateForm.setFieldsValue(value ? { ...value, matcher: JSON.stringify(value.matcher ?? {}, null, 2) } : { name: '', schema: undefined, priority: 100, status: 'draft', matcher: '{}' });
    setVersions([]);
  };

  const saveTemplate = async () => {
    try {
      const values = await templateForm.validateFields();
      const payload = { ...values, matcher: jsonValue(values.matcher) };
      if (template) await api.updateMetadataTemplate(template.id, payload); else await api.createMetadataTemplate(payload);
      message.success('解析模板已保存');
      editTemplate();
      await reload();
    } catch (error) {
      message.error(error instanceof Error ? error.message : '保存失败');
    }
  };

  const selectTemplate = async (value: ParserTemplate) => {
    setTemplate(value);
    templateForm.setFieldsValue({ ...value, matcher: JSON.stringify(value.matcher ?? {}, null, 2) });
    setVersions(await api.metadataVersions(value.id));
  };

  const createVersion = async () => {
    if (!template) return;
    try {
      const values = await versionForm.validateFields();
      const created = await api.createMetadataVersion(template.id, { version: values.version, rules: jsonValue(values.rules) });
      setVersions((current) => [created, ...current]);
      versionForm.resetFields();
      message.success('版本已创建');
    } catch (error) {
      message.error(error instanceof Error ? error.message : '版本创建失败');
    }
  };

  const dryRun = async () => {
    try {
      setDryRunResult(await api.metadataDryRun(await dryRunForm.validateFields()));
    } catch (error) {
      message.error(error instanceof Error ? error.message : '试跑失败');
    }
  };

  const executeRun = async () => {
    setRunning(true);
    try {
      const created = await api.executeMetadataRun(await executeForm.validateFields());
      setRuns((current) => [created, ...current.filter((item) => item.id !== created.id)]);
      setSelectedRun(created);
      message.success('正式解析执行完成');
    } catch (error) {
      message.error(error instanceof Error ? error.message : '正式解析执行失败');
    } finally {
      setRunning(false);
    }
  };

  const schemaTab = <Row gutter={18}>
    <Col flex="380px"><Card title="Schema 列表" extra={<Button icon={<PlusOutlined />} onClick={() => editSchema()}>新建</Button>}>
      <Table<MetadataSchema> rowKey="id" size="small" loading={loading} dataSource={schemas} pagination={false} tableLayout="fixed" columns={[
        { title: '名称', dataIndex: 'name', ellipsis: true },
        { title: '版本', dataIndex: 'version', width: 80 },
        { title: '状态', dataIndex: 'status', width: 72, render: (value) => <Tag>{value}</Tag> },
        { title: '操作', width: 64, render: (_, record) => <Button type="link" onClick={() => editSchema(record)}>编辑</Button> }
      ]} />
    </Card></Col>
    <Col flex="auto"><Card title={schema ? `编辑 Schema：${schema.name}` : '新建 Schema'}><Form form={schemaForm} layout="vertical">
      <Row gutter={12}><Col span={8}><Form.Item name="code" label="编码" rules={[{ required: true }]}><Input /></Form.Item></Col><Col span={8}><Form.Item name="name" label="名称" rules={[{ required: true }]}><Input /></Form.Item></Col><Col span={8}><Form.Item name="version" label="版本"><Input /></Form.Item></Col></Row>
      <Form.Item name="description" label="说明"><Input.TextArea rows={2} /></Form.Item>
      <Form.List name="fields">{(fields, { add, remove }) => <Space direction="vertical" style={{ width: '100%' }}>
        {fields.map((field, index) => <Card size="small" key={field.key} title={`字段 ${index + 1}`} extra={<Button danger type="text" icon={<DeleteOutlined />} onClick={() => remove(field.name)} />}><Row gutter={8}>
          <Col span={5}><Form.Item {...field} name={[field.name, 'key']} label="key" rules={[{ required: true }]}><Input /></Form.Item></Col>
          <Col span={5}><Form.Item {...field} name={[field.name, 'label']} label="标签"><Input /></Form.Item></Col>
          <Col span={4}><Form.Item {...field} name={[field.name, 'data_type']} label="类型"><Select options={dataTypes.map((item) => ({ label: item, value: item }))} /></Form.Item></Col>
          <Col span={3}><Form.Item {...field} name={[field.name, 'unit']} label="单位"><Input /></Form.Item></Col>
          <Col span={3}><Form.Item {...field} name={[field.name, 'display_order']} label="顺序"><InputNumber min={0} style={{ width: '100%' }} /></Form.Item></Col>
          <Col span={2}><Form.Item {...field} name={[field.name, 'required']} label="必填" valuePropName="checked"><Switch /></Form.Item></Col>
          <Col span={2}><Form.Item {...field} name={[field.name, 'searchable']} label="检索" valuePropName="checked"><Switch /></Form.Item></Col>
          <Col span={12}><Form.Item {...field} name={[field.name, 'enum_values']} label="枚举值（逗号分隔）"><Input /></Form.Item></Col>
          <Col span={12}><Form.Item {...field} name={[field.name, 'validation']} label="校验规则 JSON"><Input.TextArea rows={1} /></Form.Item></Col>
        </Row></Card>)}
        <Button type="dashed" block icon={<PlusOutlined />} onClick={() => add(emptyField())}>添加字段</Button>
      </Space>}</Form.List>
      <Divider /><Button type="primary" icon={<SaveOutlined />} onClick={() => void saveSchema()}>保存 Schema</Button>
    </Form></Card></Col>
  </Row>;

  const templateTab = <Row gutter={18}>
    <Col flex="380px"><Card title="模板列表" extra={<Button icon={<PlusOutlined />} onClick={() => editTemplate()}>新建</Button>}>
      <Table<ParserTemplate> rowKey="id" size="small" dataSource={templates} pagination={false} tableLayout="fixed" columns={[
        { title: '名称', dataIndex: 'name', ellipsis: true },
        { title: '优先级', dataIndex: 'priority', width: 72 },
        { title: '操作', width: 64, render: (_, record) => <Button type="link" onClick={() => void selectTemplate(record)}>版本</Button> }
      ]} />
    </Card></Col>
    <Col flex="auto"><Card title={template ? `编辑模板：${template.name}` : '新建模板'}><Form form={templateForm} layout="vertical">
      <Row gutter={12}><Col span={8}><Form.Item name="schema" label="Schema" rules={[{ required: true }]}><Select options={schemaOptions} /></Form.Item></Col><Col span={8}><Form.Item name="name" label="名称" rules={[{ required: true }]}><Input /></Form.Item></Col><Col span={4}><Form.Item name="priority" label="优先级"><InputNumber min={0} style={{ width: '100%' }} /></Form.Item></Col><Col span={4}><Form.Item name="status" label="状态"><Select options={['draft', 'active', 'disabled'].map((item) => ({ label: item, value: item }))} /></Form.Item></Col></Row>
      <Form.Item name="matcher" label="匹配条件 JSON"><Input.TextArea rows={4} /></Form.Item><Button type="primary" icon={<SaveOutlined />} onClick={() => void saveTemplate()}>保存模板</Button>
    </Form></Card>
      {template && <Card title="版本管理" style={{ marginTop: 16 }}><Form form={versionForm} layout="inline"><Form.Item name="version" rules={[{ required: true }]}><Input placeholder="版本号" /></Form.Item><Form.Item name="rules" rules={[{ required: true }]}><Input placeholder="rules JSON" style={{ width: 360 }} /></Form.Item><Button icon={<PlusOutlined />} onClick={() => void createVersion()}>新建版本</Button></Form>
        <Table<ParserTemplateVersion> rowKey="id" size="small" dataSource={versions} pagination={false} tableLayout="fixed" columns={[
          { title: '版本', dataIndex: 'version' }, { title: '状态', dataIndex: 'status', width: 100 },
          { title: '操作', width: 100, render: (_, record) => record.status === 'published' ? <Tag color="green">已发布</Tag> : <Popconfirm title="发布此版本？" onConfirm={async () => {
            try {
              await api.publishMetadataVersion(record.id);
              message.success('版本已发布');
              setVersions(await api.metadataVersions(template.id));
            } catch (error) {
              message.error(error instanceof Error ? error.message : '版本发布失败');
            }
          }}><Button type="link" icon={<SendOutlined />}>发布</Button></Popconfirm> }
        ]} />
      </Card>}
    </Col>
  </Row>;

  const dryRunTab = <Card title="按影像试跑解析规则"><Form form={dryRunForm} layout="inline"><Form.Item name="imagery_id" label="影像 ID" rules={[{ required: true }]}><Input placeholder="imagery_id" /></Form.Item><Form.Item name="parser_version_id" label="规则版本"><Select allowClear placeholder="自动匹配已发布规则" style={{ width: 260 }} options={versionOptions} /></Form.Item><Button type="primary" icon={<PlayCircleOutlined />} onClick={() => void dryRun()}>开始试跑</Button></Form>
    {dryRunResult && <Input.TextArea readOnly autoSize={{ minRows: 12, maxRows: 24 }} style={{ marginTop: 16 }} value={JSON.stringify(dryRunResult, null, 2)} />}
  </Card>;

  const runsTab = <Space direction="vertical" size={16} style={{ width: '100%' }}>
    <Card title="正式执行解析"><Form form={executeForm} layout="inline" onFinish={() => void executeRun()}>
      <Form.Item name="imagery_id" label="影像 ID" rules={[{ required: true, message: '请输入影像 ID' }]}><Input placeholder="imagery_id" style={{ width: 300 }} /></Form.Item>
      <Form.Item name="parser_version_id" label="规则版本"><Select allowClear placeholder="自动匹配已发布规则" style={{ width: 260 }} options={versionOptions} /></Form.Item>
      <Button type="primary" htmlType="submit" icon={<PlayCircleOutlined />} loading={running}>执行解析</Button>
    </Form></Card>
    <Row gutter={16}>
      <Col span={15}><Card title="解析运行记录" extra={<Button icon={<ReloadOutlined />} loading={loading} onClick={() => void reload()}>刷新</Button>}>
        <Table<MetadataParserRun> rowKey="id" size="small" loading={loading} dataSource={runs} pagination={{ pageSize: 10, showSizeChanger: false }} tableLayout="fixed" locale={{ emptyText: <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无解析运行记录" /> }} columns={[
          { title: '影像', dataIndex: 'imagery', ellipsis: true },
          { title: '规则版本', dataIndex: 'parser_version', width: 90, render: (value) => value ?? '自动' },
          { title: '状态', dataIndex: 'status', width: 90, render: runStatus },
          { title: '类型', dataIndex: 'dry_run', width: 70, render: (value) => value ? '试跑' : '正式' },
          { title: '开始时间', dataIndex: 'started_at', width: 155, render: dateTime },
          { title: '操作', width: 72, render: (_, record) => <Button type="link" icon={<EyeOutlined />} onClick={() => setSelectedRun(record)}>查看</Button> }
        ]} />
      </Card></Col>
      <Col span={9}><Card title="运行结果">{!selectedRun ? <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="选择一条运行记录查看结果" /> : <Space direction="vertical" size={12} style={{ width: '100%' }}>
        <Descriptions column={1} size="small" bordered items={[
          { key: 'id', label: '运行 ID', children: selectedRun.id }, { key: 'imagery', label: '影像', children: selectedRun.imagery ?? '-' },
          { key: 'version', label: '规则版本', children: selectedRun.parser_version ?? '自动匹配' }, { key: 'status', label: '状态', children: runStatus(selectedRun.status) },
          { key: 'started', label: '开始时间', children: dateTime(selectedRun.started_at) }, { key: 'finished', label: '完成时间', children: dateTime(selectedRun.finished_at) }
        ]} />
        <Typography.Text strong>解析结果</Typography.Text>
        <Input.TextArea readOnly autoSize={{ minRows: 8, maxRows: 16 }} value={JSON.stringify({ values: selectedRun.values ?? {}, provenance: selectedRun.provenance ?? {}, warnings: selectedRun.warnings ?? [], errors: selectedRun.errors ?? [] }, null, 2)} />
      </Space>}</Card></Col>
    </Row>
  </Space>;

  return <div className="system-page"><Space direction="vertical" size={18} style={{ width: '100%' }}>
    <div><Typography.Title level={2} style={{ marginBottom: 4 }}>元数据治理</Typography.Title><Typography.Text type="secondary">配置数据结构、解析规则、版本发布和解析运行</Typography.Text></div>
    <Tabs items={[
      { key: 'schemas', label: 'Schema 管理', children: schemaTab },
      { key: 'templates', label: '解析模板', children: templateTab },
      { key: 'dry-run', label: '规则试跑', children: dryRunTab },
      { key: 'runs', label: '解析运行', children: runsTab }
    ]} />
  </Space></div>;
}
