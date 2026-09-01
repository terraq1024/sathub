import { useEffect, useMemo, useState } from 'react';
import {
  Alert,
  App,
  Button,
  Descriptions,
  Drawer,
  Empty,
  Form,
  Grid,
  Input,
  Modal,
  Popconfirm,
  Select,
  Space,
  Spin,
  Switch,
  Table,
  Tag,
  Tooltip,
  Typography
} from 'antd';
import type { ColumnsType } from 'antd/es/table';
import {
  ApiOutlined,
  ArrowDownOutlined,
  ArrowUpOutlined,
  DeleteOutlined,
  EditOutlined,
  PlusOutlined,
  VerticalAlignBottomOutlined,
  VerticalAlignTopOutlined
} from '@ant-design/icons';
import dayjs from 'dayjs';
import type { LatLngBoundsExpression } from 'leaflet';
import { GeoJSON, MapContainer, Rectangle } from 'react-leaflet';
import {
  getListCount,
  unwrapList,
  useArchiveDataset,
  useCreateDataset,
  useCreateService,
  useDataset,
  useDatasets,
  useOrderDatasetMembers,
  usePublishService,
  useRemoveDatasetMember,
  useServices,
  useUpdateDataset,
  useUpdateDatasetMember,
  useRefreshDataset
} from '../../api/hooks';
import type { ImageryDataset, ImageryDatasetMember, User } from '../../api/types';
import { BaseMapLayer, FitBounds, RefreshMapSize } from '../imagery/MapPrimitives';
import { ImageryThumbnail } from '../imagery/ImageryThumbnail';
import { imageryBounds, imageryName, memberImageId, memberImagery, normalizeError } from '../imagery/utils';
import { SectionBar, StatusTag } from '../../components/VisualPrimitives';

function datasetCanManage(dataset: ImageryDataset, user?: User) {
  if (dataset.can_manage !== undefined) return dataset.can_manage;
  const creatorId = typeof dataset.created_by === 'object' ? dataset.created_by.id : dataset.created_by;
  return Boolean(user?.is_staff || user?.is_superuser || String(creatorId) === String(user?.id));
}

function datasetBounds(dataset: ImageryDataset, members: ImageryDatasetMember[]): LatLngBoundsExpression | undefined {
  if (dataset.bbox?.length === 4) {
    const [minLon, minLat, maxLon, maxLat] = dataset.bbox;
    return [[minLat, minLon], [maxLat, maxLon]];
  }
  const values = members.map((member) => imageryBounds(memberImagery(member))).filter(Boolean) as Array<[[number, number], [number, number]]>;
  if (!values.length) return undefined;
  return [
    [Math.min(...values.map((value) => value[0][0])), Math.min(...values.map((value) => value[0][1]))],
    [Math.max(...values.map((value) => value[1][0])), Math.max(...values.map((value) => value[1][1]))]
  ];
}

interface DatasetDetailProps {
  datasetId?: string;
  onClose: () => void;
  currentUser?: User;
  onPublish: (dataset: ImageryDataset) => void;
}

function DatasetDetail({ datasetId, onClose, currentUser, onPublish }: DatasetDetailProps) {
  const screens = Grid.useBreakpoint();
  const { message, modal } = App.useApp();
  const [editing, setEditing] = useState(false);
  const [form] = Form.useForm();
  const [pendingMemberId, setPendingMemberId] = useState<string>();
  const datasetQuery = useDataset(datasetId);
  const updateDataset = useUpdateDataset();
  const refreshDataset = useRefreshDataset();
  const archiveDataset = useArchiveDataset();
  const removeMember = useRemoveDatasetMember();
  const updateMember = useUpdateDatasetMember();
  const orderMembers = useOrderDatasetMembers();
  const servicesQuery = useServices(Boolean(datasetId));
  const dataset = datasetQuery.data;
  const members = useMemo(
    () => [...(dataset?.members ?? [])].sort((left, right) => left.position - right.position),
    [dataset?.members]
  );
  const bounds = useMemo(() => dataset ? datasetBounds(dataset, members) : undefined, [dataset, members]);
  const manageable = dataset ? datasetCanManage(dataset, currentUser) : false;
  const datasetService = servicesQuery.data?.find((service) => service.dataset_id === dataset?.id);

  useEffect(() => {
    setEditing(false);
  }, [datasetId]);

  useEffect(() => {
    if (dataset) form.setFieldsValue({ name: dataset.name, description: dataset.description });
  }, [dataset, form]);

  const move = async (member: ImageryDatasetMember, destination: number) => {
    if (!dataset) return;
    const currentIndex = members.findIndex((item) => memberImageId(item) === memberImageId(member));
    if (currentIndex < 0) return;
    const next = [...members];
    const [item] = next.splice(currentIndex, 1);
    next.splice(Math.max(0, Math.min(destination, next.length)), 0, item);
    try {
      await orderMembers.mutateAsync({ datasetId: dataset.id, imageryIds: next.map(memberImageId) });
    } catch (error) {
      message.error(normalizeError(error));
    }
  };

  const save = async () => {
    if (!dataset) return;
    try {
      const values = await form.validateFields();
      await updateDataset.mutateAsync({ datasetId: dataset.id, payload: values });
      message.success('数据集已更新');
      setEditing(false);
    } catch (error) {
      if (error instanceof Error) message.error(normalizeError(error));
    }
  };

  const archive = () => {
    if (!dataset) return;
    modal.confirm({
      title: '归档数据集？',
      content: '归档只会隐藏数据集，不会删除成员影像。',
      okText: '归档',
      okButtonProps: { danger: true },
      cancelText: '取消',
      onOk: async () => {
        try {
          await archiveDataset.mutateAsync(dataset.id);
          message.success('数据集已归档');
          onClose();
        } catch (error) {
          message.error(normalizeError(error));
        }
      }
    });
  };

  return (
    <Drawer
      title={dataset?.name ?? '数据集详情'}
      open={Boolean(datasetId)}
      onClose={onClose}
      width={screens.md ? 420 : '100%'}
      extra={manageable && !editing ? <Button type="text" icon={<EditOutlined />} title="编辑" onClick={() => setEditing(true)} /> : null}
    >
      {datasetQuery.isLoading ? <Spin /> : null}
      {dataset ? (
        <Space direction="vertical" size={14} className="full-width dataset-detail">
          {bounds ? (
            <div className="dataset-map">
              <MapContainer center={[31.23, 121.47]} zoom={5} scrollWheelZoom className="map">
                <RefreshMapSize />
                <BaseMapLayer />
                <FitBounds bounds={bounds} />
                {members.map((member) => {
                  const imagery = memberImagery(member);
                  return imagery.geometry ? (
                    <GeoJSON
                      key={memberImageId(member)}
                      data={imagery.geometry as never}
                      style={{ color: member.enabled ? '#1677ff' : '#8c8c8c', weight: 2, fillOpacity: member.enabled ? 0.16 : 0.04 }}
                    />
                  ) : imageryBounds(imagery) ? (
                    <Rectangle
                      key={memberImageId(member)}
                      bounds={imageryBounds(imagery)!}
                      pathOptions={{ color: member.enabled ? '#1677ff' : '#8c8c8c', weight: 2, fillOpacity: member.enabled ? 0.12 : 0.03 }}
                    />
                  ) : null;
                })}
              </MapContainer>
            </div>
          ) : <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无空间范围" />}

          {editing ? (
            <Form form={form} layout="vertical" requiredMark={false}>
              <Form.Item name="name" label="名称" rules={[{ required: true, message: '请输入名称' }]}><Input maxLength={255} /></Form.Item>
              <Form.Item name="description" label="备注"><Input.TextArea rows={3} maxLength={1000} showCount /></Form.Item>
              <Space><Button type="primary" loading={updateDataset.isPending} onClick={() => void save()}>保存</Button><Button onClick={() => setEditing(false)}>取消</Button></Space>
            </Form>
          ) : (
            <>
            <Descriptions size="small" column={2} bordered>
              <Descriptions.Item label="成员">{dataset.member_count ?? dataset.imagery_count ?? members.length}</Descriptions.Item>
              <Descriptions.Item label="修订">v{dataset.revision}</Descriptions.Item>
              <Descriptions.Item label="状态"><Tag color={dataset.status === 'active' ? 'success' : 'default'}>{dataset.status === 'active' ? '有效' : '已归档'}</Tag></Descriptions.Item>
            <Descriptions.Item label="服务">{datasetService?.needs_update ? <StatusTag status="warning" label="有更新" /> : datasetService ? <StatusTag status={datasetService.status} /> : '-'}</Descriptions.Item>
              <Descriptions.Item label="类型">{dataset.membership_type === 'query' ? '动态' : '静态'}</Descriptions.Item>
              <Descriptions.Item label="刷新模式">{dataset.refresh_mode === 'on_ingestion' ? '入库自动刷新' : '手动刷新'}</Descriptions.Item>
              <Descriptions.Item label="上次刷新">{dataset.last_refreshed_at ? dayjs(dataset.last_refreshed_at).format('YYYY-MM-DD HH:mm') : '-'}</Descriptions.Item>
            </Descriptions>
            {dataset.membership_type === 'query' && manageable ? <Button size="small" loading={refreshDataset.isPending} onClick={() => refreshDataset.mutate(dataset.id, { onSuccess: () => message.success('数据集已刷新'), onError: (e) => message.error(normalizeError(e)) })}>手动刷新</Button> : null}
            </>
          )}

          <div className="dataset-member-heading">
            <Typography.Text strong>成员与显示顺序</Typography.Text>
            <Typography.Text type="secondary">前面的影像优先</Typography.Text>
          </div>
          <div className="dataset-member-list">
            {!members.length ? <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无成员" /> : null}
            {members.map((member, index) => {
              const imagery = memberImagery(member);
              const imageId = memberImageId(member);
              return (
                <div className="dataset-member" key={imageId}>
                  <ImageryThumbnail imagery={imagery} />
                  <div className="dataset-member-main">
                    <Typography.Text ellipsis title={imageryName(imagery)}>{imageryName(imagery)}</Typography.Text>
                    <Typography.Text type="secondary">{imagery.acquisition_time ? dayjs(imagery.acquisition_time).format('YYYY-MM-DD HH:mm') : '时间未知'}</Typography.Text>
                    <Space size={2} wrap>
                      <Switch
                        size="small"
                        checked={member.enabled}
                        disabled={!manageable}
                        loading={pendingMemberId === imageId && updateMember.isPending}
                        checkedChildren="启用"
                        unCheckedChildren="停用"
                        onChange={(enabled) => {
                          setPendingMemberId(imageId);
                          updateMember.mutate(
                            { datasetId: dataset.id, imageId, enabled },
                            { onError: (error) => message.error(normalizeError(error)), onSettled: () => setPendingMemberId(undefined) }
                          );
                        }}
                      />
                      {manageable ? (
                        <>
                          <Tooltip title="置顶"><Button type="text" size="small" icon={<VerticalAlignTopOutlined />} disabled={index === 0} onClick={() => void move(member, 0)} /></Tooltip>
                          <Tooltip title="上移"><Button type="text" size="small" icon={<ArrowUpOutlined />} disabled={index === 0} onClick={() => void move(member, index - 1)} /></Tooltip>
                          <Tooltip title="下移"><Button type="text" size="small" icon={<ArrowDownOutlined />} disabled={index === members.length - 1} onClick={() => void move(member, index + 1)} /></Tooltip>
                          <Tooltip title="置底"><Button type="text" size="small" icon={<VerticalAlignBottomOutlined />} disabled={index === members.length - 1} onClick={() => void move(member, members.length - 1)} /></Tooltip>
                          <Popconfirm
                            title="移除成员？"
                            okText="移除"
                            cancelText="取消"
                            onConfirm={() => removeMember.mutate(
                              { datasetId: dataset.id, imageId },
                              { onError: (error) => message.error(normalizeError(error)) }
                            )}
                          >
                            <Tooltip title="移除"><Button danger type="text" size="small" icon={<DeleteOutlined />} /></Tooltip>
                          </Popconfirm>
                        </>
                      ) : null}
                    </Space>
                  </div>
                </div>
              );
            })}
          </div>
          {manageable ? (
            <Space wrap>
              <Button type="primary" icon={<ApiOutlined />} disabled={!members.some((member) => member.enabled)} onClick={() => onPublish(dataset)}>发布服务</Button>
              <Button danger icon={<DeleteOutlined />} onClick={archive}>归档数据集</Button>
            </Space>
          ) : null}
        </Space>
      ) : null}
    </Drawer>
  );
}

function validateQueryDefinition(value: string): Record<string, unknown> {
  let parsed: unknown;
  try {
    parsed = JSON.parse(value);
  } catch {
    throw new Error('筛选定义必须是合法的 JSON 对象');
  }
  if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) {
    throw new Error('筛选定义必须是 JSON 对象，例如 {"q":"AS05"}');
  }
  return parsed as Record<string, unknown>;
}

export function DatasetsPanel({ currentUser }: { currentUser?: User }) {
  const { message } = App.useApp();
  const [query, setQuery] = useState('');
  const [params, setParams] = useState({ page: 1, page_size: 20, q: '' });
  const [detailId, setDetailId] = useState<string>();
  const [createOpen, setCreateOpen] = useState(false);
  const [publishTarget, setPublishTarget] = useState<ImageryDataset>();
  const [createForm] = Form.useForm();
  const [publishForm] = Form.useForm();
  const datasetsQuery = useDatasets(params);
  const servicesQuery = useServices();
  const createDataset = useCreateDataset();
  const createService = useCreateService();
  const publishService = usePublishService();
  const datasets = unwrapList(datasetsQuery.data);

  const publish = async () => {
    if (!publishTarget) return;
    try {
      const values = await publishForm.validateFields();
      const service = await createService.mutateAsync({
        dataset_id: publishTarget.id,
        name: values.name,
        visibility: values.visibility
      });
      await publishService.mutateAsync(service.service_key);
      message.success('数据集服务发布任务已创建');
      setPublishTarget(undefined);
    } catch (error) {
      if (error instanceof Error) message.error(normalizeError(error));
    }
  };

  const columns: ColumnsType<ImageryDataset> = [
    { title: '数据集名称', dataIndex: 'name', minWidth: 220, ellipsis: true },
    { title: '成员', width: 80, render: (_, record) => record.member_count ?? record.imagery_count ?? 0 },
    {
      title: '时间范围', width: 220,
      render: (_, record) => {
        const start = record.acquisition_start ?? record.time_start;
        const end = record.acquisition_end ?? record.time_end;
        return start || end ? `${start ? dayjs(start).format('YYYY-MM-DD') : '-'} 至 ${end ? dayjs(end).format('YYYY-MM-DD') : '-'}` : '-';
      }
    },
    { title: '创建人', width: 100, render: (_, record) => typeof record.created_by === 'object' ? record.created_by.username : record.created_by_username ?? record.created_by ?? '-' },
    { title: '修订', dataIndex: 'revision', width: 72, render: (value) => `v${value}` },
    {
      title: '服务', width: 100,
      render: (_, record) => {
        const service = servicesQuery.data?.find((item) => item.dataset_id === record.id);
        return service?.needs_update ? <StatusTag status="warning" label="有更新" /> : service ? <StatusTag status={service.status} /> : '-';
      }
    },
    { title: '更新时间', dataIndex: 'updated_at', width: 150, render: (value) => dayjs(value).format('YYYY-MM-DD HH:mm') },
    { title: '操作', width: 130, render: (_, record) => <Space size={0}><Button type="link" onClick={() => setDetailId(record.id)}>查看</Button><Button type="link" icon={<ApiOutlined />} onClick={() => { setPublishTarget(record); publishForm.setFieldsValue({ name: `${record.name} 服务`, visibility: 'authenticated' }); }}>发布</Button></Space> }
  ];

  return (
    <div className="datasets-page">
      <div className="dataset-toolbar">
        <Input.Search
          allowClear
          value={query}
          placeholder="搜索数据集"
          onChange={(event) => setQuery(event.target.value)}
          onSearch={(value) => setParams((current) => ({ ...current, q: value.trim(), page: 1 }))}
        />
        <Button type="primary" icon={<PlusOutlined />} onClick={() => setCreateOpen(true)}>新建数据集</Button>
      </div>
      <SectionBar title="数据集目录" detail={`共 ${getListCount(datasetsQuery.data)} 个数据集`} />
      {datasetsQuery.isError ? <Alert type="error" showIcon message={normalizeError(datasetsQuery.error)} /> : null}
      <Table
        rowKey="id"
        columns={columns}
        dataSource={datasets}
        loading={datasetsQuery.isLoading}
        tableLayout="fixed"
        pagination={{
          current: params.page,
          pageSize: params.page_size,
          total: getListCount(datasetsQuery.data),
          onChange: (page, pageSize) => setParams((current) => ({ ...current, page, page_size: pageSize }))
        }}
      />
      <DatasetDetail datasetId={detailId} onClose={() => setDetailId(undefined)} currentUser={currentUser} onPublish={(dataset) => { setPublishTarget(dataset); publishForm.setFieldsValue({ name: `${dataset.name} 服务`, visibility: 'authenticated' }); }} />
      <Modal
        title="新建数据集"
        open={createOpen}
        onCancel={() => { setCreateOpen(false); createForm.resetFields(); }}
        confirmLoading={createDataset.isPending}
        onOk={() => void createForm.validateFields().then(async (values) => {
          try {
            const payload = values.membership_type === 'query' ? { ...values, query_definition: validateQueryDefinition(values.query_definition) } : values;
            await createDataset.mutateAsync(payload);
            message.success('数据集已创建');
            setCreateOpen(false);
            createForm.resetFields();
          } catch (error) {
            message.error(normalizeError(error));
          }
        })}
      >
        <Form form={createForm} layout="vertical" requiredMark={false}>
          <Form.Item name="name" label="名称" rules={[{ required: true, message: '请输入名称' }]}><Input maxLength={255} /></Form.Item>
          <Form.Item name="description" label="备注"><Input.TextArea rows={3} maxLength={1000} showCount /></Form.Item>
          <Form.Item name="membership_type" label="成员类型" initialValue="static"><Select options={[{ value: 'static', label: '静态成员' }, { value: 'query', label: '动态筛选' }]} /></Form.Item>
          <Form.Item noStyle shouldUpdate={(prev, next) => prev.membership_type !== next.membership_type}>{({ getFieldValue }) => getFieldValue('membership_type') === 'query' ? <><Form.Item name="query_definition" label="筛选定义（JSON）" rules={[{ required: true, message: '请输入筛选定义' }, { validator: async (_, value) => { if (value) validateQueryDefinition(value); } }]}><Input.TextArea rows={4} placeholder='{"q":"AS05"}' /></Form.Item><Form.Item name="refresh_mode" label="刷新模式" initialValue="manual"><Select options={[{ value: 'manual', label: '手动刷新' }, { value: 'on_ingestion', label: '入库自动刷新' }]} /></Form.Item></> : null}</Form.Item>
        </Form>
      </Modal>
      <Modal
        title="发布数据集服务"
        open={Boolean(publishTarget)}
        onCancel={() => { setPublishTarget(undefined); publishForm.resetFields(); }}
        onOk={() => void publish()}
        confirmLoading={createService.isPending || publishService.isPending}
      >
        <Form form={publishForm} layout="vertical" requiredMark={false}>
          <Form.Item name="name" label="服务名称" rules={[{ required: true, message: '请输入服务名称' }]}><Input /></Form.Item>
          <Form.Item name="visibility" label="访问范围" initialValue="authenticated">
            <Select options={[{ value: 'authenticated', label: '登录用户' }, { value: 'public', label: '公开' }]} />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
}
