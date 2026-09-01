import { useMemo, useState } from 'react';
import { Alert, App, Button, Descriptions, Drawer, Grid, Input, Modal, Progress, Space, Table, Tag, Typography } from 'antd';
import type { ColumnsType } from 'antd/es/table';
import {
  ApiOutlined,
  CopyOutlined,
  EnvironmentOutlined,
  PlayCircleOutlined,
  ReloadOutlined,
  StopOutlined
} from '@ant-design/icons';
import dayjs from 'dayjs';
import type { LatLngBoundsExpression } from 'leaflet';
import { MapContainer, TileLayer } from 'react-leaflet';
import { api } from '../../api/client';
import { useOfflineService, usePublishService, useServices } from '../../api/hooks';
import type { ImageryService } from '../../api/types';
import { BaseMapLayer, FitBounds, RefreshMapSize } from '../imagery/MapPrimitives';
import { normalizeError } from '../imagery/utils';
import { MetricStrip, PageHeader, SectionBar, StatusTag } from '../../components/VisualPrimitives';

const statusColor: Record<string, string> = {
  draft: 'default', validating: 'processing', preparing: 'cyan', publishing: 'blue', online: 'success',
  degraded: 'warning', offline: 'default', failed: 'error', archived: 'default'
};

const statusLabel: Record<string, string> = {
  draft: '草稿', validating: '校验', preparing: '准备', publishing: '发布中', online: '在线',
  degraded: '降级运行', offline: '已下线', failed: '失败', archived: '已归档'
};

function sourceType(service: ImageryService) {
  return service.source_type ?? service.service_type;
}

function ServicePreview({ service }: { service: ImageryService }) {
  const [tileState, setTileState] = useState<'loading' | 'ok' | 'error'>('loading');
  const bounds = useMemo<LatLngBoundsExpression | undefined>(() => {
    if (!service.bbox?.length) return undefined;
    const [minLon, minLat, maxLon, maxLat] = service.bbox;
    return [[minLat, minLon], [maxLat, maxLon]];
  }, [service.bbox]);

  return (
    <div className="service-preview-map">
      <MapContainer center={[31.2, 115]} zoom={5} scrollWheelZoom className="map">
        <RefreshMapSize />
        <BaseMapLayer />
        <FitBounds bounds={bounds} />
        <TileLayer
          key={service.service_key}
          url={api.serviceTileUrl(service.service_key)}
          bounds={bounds}
          minZoom={service.minzoom ?? 0}
          maxZoom={service.maxzoom ?? 22}
          opacity={0.9}
          eventHandlers={{ tileerror: () => setTileState('error'), tileload: () => setTileState('ok') }}
        />
      </MapContainer>
      <div className="service-preview-status">
        <Tag color={tileState === 'error' ? 'error' : tileState === 'ok' ? 'success' : 'processing'}>
          {tileState === 'error' ? '瓦片加载失败' : tileState === 'ok' ? '瓦片已加载' : '瓦片加载中'}
        </Tag>
      </div>
    </div>
  );
}

export function ServicesPage() {
  const screens = Grid.useBreakpoint();
  const { message } = App.useApp();
  const servicesQuery = useServices();
  const publishService = usePublishService();
  const offlineService = useOfflineService();
  const [preview, setPreview] = useState<ImageryService>();
  const [accessOpen, setAccessOpen] = useState(false);
  const [publishingKey, setPublishingKey] = useState<string>();
  const [offliningKey, setOffliningKey] = useState<string>();
  const services = servicesQuery.data ?? [];

  const copy = async (url: string) => {
    try {
      await navigator.clipboard.writeText(url);
      message.success('调用地址已复制');
    } catch {
      message.error('无法访问剪贴板');
    }
  };

  const publish = (service: ImageryService) => {
    setPublishingKey(service.service_key);
    publishService.mutate(service.service_key, {
      onSuccess: () => message.success('发布任务已创建'),
      onError: (error) => message.error(normalizeError(error)),
      onSettled: () => setPublishingKey(undefined)
    });
  };

  const columns: ColumnsType<ImageryService> = [
    { title: '服务名称', dataIndex: 'name', minWidth: 210, ellipsis: true },
    {
      title: '来源', minWidth: 200, ellipsis: true,
      render: (_, record) => record.dataset_name ?? record.imagery_name ?? '-'
    },
    {
      title: '类型', width: 100,
      render: (_, record) => <Tag color={sourceType(record) === 'dataset_mosaic' ? 'blue' : 'default'}>{sourceType(record) === 'dataset_mosaic' ? '数据集' : '单景'}</Tag>
    },
    { title: '影像数', dataIndex: 'imagery_count', width: 80, render: (value, record) => value ?? (record.imagery_id ? 1 : '-') },
    { title: '状态', dataIndex: 'status', width: 100, render: (value) => <StatusTag status={value} label={statusLabel[value] ?? value} /> },
    {
      title: '版本', width: 90,
      render: (_, record) => record.needs_update ? <Tag color="warning">需更新</Tag> : record.source_revision ? `v${record.source_revision}` : '-'
    },
    {
      title: '进度', width: 140,
      render: (_, record) => record.latest_job ? <Progress percent={record.latest_job.progress} size="small" status={record.latest_job.status === 'failed' ? 'exception' : undefined} /> : '-'
    },
    { title: '发布时间', dataIndex: 'published_at', width: 145, render: (value) => value ? dayjs(value).format('YYYY-MM-DD HH:mm') : '-' },
    {
      title: '操作', width: 260,
      render: (_, record) => {
        const available = ['online', 'degraded'].includes(record.status);
        const publishing = ['validating', 'preparing', 'publishing'].includes(record.status);
        return (
          <Space size={0}>
            {available ? <Button type="link" icon={<EnvironmentOutlined />} onClick={() => setPreview(record)}>预览</Button> : null}
            {available ? <Button type="link" icon={<CopyOutlined />} onClick={() => void copy(record.xyz_url ?? api.serviceTileUrl(record.service_key))}>XYZ</Button> : null}
            {record.needs_update || !available ? (
              <Button type="link" icon={<PlayCircleOutlined />} disabled={publishing} loading={publishingKey === record.service_key && publishService.isPending} onClick={() => publish(record)}>
                {record.status === 'failed' ? '重试' : record.needs_update ? '更新' : '发布'}
              </Button>
            ) : null}
            {available ? (
              <Button
                type="link"
                danger
                icon={<StopOutlined />}
                loading={offliningKey === record.service_key && offlineService.isPending}
                onClick={() => {
                  setOffliningKey(record.service_key);
                  offlineService.mutate(record.service_key, {
                    onError: (error) => message.error(normalizeError(error)),
                    onSettled: () => setOffliningKey(undefined)
                  });
                }}
              >下线</Button>
            ) : null}
          </Space>
        );
      }
    }
  ];

  return (
    <div className="services-page">
      <PageHeader
        title="服务"
        description="影像服务发布、状态和外部访问"
        extra={<Space><Button icon={<ApiOutlined />} onClick={() => setAccessOpen(true)}>外部访问</Button><Button icon={<ReloadOutlined />} onClick={() => void servicesQuery.refetch()}>刷新</Button></Space>}
      />
      <MetricStrip items={[
        { key: 'all', label: '全部服务', value: services.length, detail: '已登记', icon: <ApiOutlined /> },
        { key: 'online', label: '在线', value: services.filter((service) => ['online', 'degraded'].includes(service.status)).length, detail: '可访问', icon: <PlayCircleOutlined />, tone: 'success' },
        { key: 'publishing', label: '发布中', value: services.filter((service) => ['validating', 'preparing', 'publishing'].includes(service.status)).length, detail: '正在处理', icon: <ReloadOutlined />, tone: 'warning' },
        { key: 'attention', label: '需关注', value: services.filter((service) => service.needs_update || service.status === 'failed').length, detail: '更新或失败', icon: <StopOutlined />, tone: 'danger' }
      ]} />
      {servicesQuery.isError ? <Alert type="error" showIcon message={normalizeError(servicesQuery.error)} /> : null}
      <SectionBar title="服务目录" detail="展开行查看访问地址和发布信息" />
      <Table
        rowKey="id"
        columns={columns}
        dataSource={services}
        loading={servicesQuery.isLoading}
        tableLayout="fixed"
        pagination={{ pageSize: 15 }}
        expandable={{
          expandedRowRender: (record) => (
            <Descriptions size="small" bordered column={2}>
              <Descriptions.Item label="服务标识">{record.service_key}</Descriptions.Item>
              <Descriptions.Item label="访问范围">{record.visibility === 'public' ? '公开' : '登录用户'}</Descriptions.Item>
              <Descriptions.Item label="TileJSON" span={2}>{['online', 'degraded'].includes(record.status) ? record.tilejson_url : '-'}</Descriptions.Item>
              <Descriptions.Item label="OGC API Tiles" span={2}>
                {['online', 'degraded'].includes(record.status) ? <Typography.Text copyable>{record.ogcapi_url}</Typography.Text> : '-'}
              </Descriptions.Item>
              <Descriptions.Item label="当前步骤">{record.latest_job?.current_step || '-'}</Descriptions.Item>
              <Descriptions.Item label="最后错误">{record.error_message || record.latest_job?.error_message || '-'}</Descriptions.Item>
            </Descriptions>
          )
        }}
      />
      <Modal
        title={preview ? `服务预览 · ${preview.name}` : '服务预览'}
        open={Boolean(preview)}
        footer={null}
        width={screens.md ? 1000 : '100%'}
        destroyOnHidden
        onCancel={() => setPreview(undefined)}
      >
        {preview ? (
          <Space direction="vertical" size={12} className="full-width">
            <ServicePreview service={preview} />
            <Descriptions size="small" bordered column={screens.md ? 2 : 1}>
              <Descriptions.Item label="XYZ 地址" span={screens.md ? 2 : 1}><Typography.Text copyable>{preview.xyz_url ?? api.serviceTileUrl(preview.service_key)}</Typography.Text></Descriptions.Item>
              <Descriptions.Item label="OGC API Tiles" span={screens.md ? 2 : 1}><Typography.Text copyable>{preview.ogcapi_url}</Typography.Text></Descriptions.Item>
              <Descriptions.Item label="范围">{preview.bbox?.join(', ') || '-'}</Descriptions.Item>
              <Descriptions.Item label="成员">{preview.imagery_count ?? (preview.imagery_id ? 1 : '-')} 景</Descriptions.Item>
            </Descriptions>
          </Space>
        ) : null}
      </Modal>
      <Drawer title="外部访问" width={420} open={accessOpen} onClose={() => setAccessOpen(false)}>
        <Space direction="vertical" className="full-width" size={12}>
          <Typography.Title level={5}>STAC API</Typography.Title>
          <Space.Compact className="full-width"><Input readOnly value={api.stacApiUrl()} /><Button onClick={() => void navigator.clipboard.writeText(api.stacApiUrl())}>复制</Button></Space.Compact>
          <Typography.Title level={5}>调用说明</Typography.Title>
          <Typography.Paragraph copyable={{ text: api.stacApiUrl() }}>QGIS：使用 STAC 浏览器连接上述地址；Python：使用 requests 或 pystac-client 查询 /search。</Typography.Paragraph>
          <Typography.Text type="secondary">令牌和签名资产管理在数据篮中进行。令牌只在创建成功后展示一次，请妥善保存。</Typography.Text>
        </Space>
      </Drawer>
    </div>
  );
}
