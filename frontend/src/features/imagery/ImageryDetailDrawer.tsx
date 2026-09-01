import { useEffect, useMemo, useState } from 'react';
import {
  App,
  Button,
  Descriptions,
  Drawer,
  Empty,
  Form,
  Grid,
  Input,
  Select,
  Segmented,
  Space,
  Spin,
  Tag,
  Typography
} from 'antd';
import { ApiOutlined, DeleteOutlined, DownloadOutlined, EditOutlined, RollbackOutlined, SaveOutlined, ScissorOutlined } from '@ant-design/icons';
import dayjs from 'dayjs';
import { ImageOverlay, MapContainer } from 'react-leaflet';
import { api } from '../../api/client';
import {
  useArchiveImagery,
  useImageryDetail,
  useRestoreImagery,
  useUpdateImagery
} from '../../api/hooks';
import type { Imagery, Project, User } from '../../api/types';
import { BaseMapLayer, FitBounds, RefreshMapSize } from './MapPrimitives';
import { ImageryThumbnail } from './ImageryThumbnail';
import { canManageImagery, imageryBounds, imageryName, normalizeError } from './utils';

interface ImageryDetailDrawerProps {
  imageId?: string;
  onClose: () => void;
  projects: Project[];
  currentUser?: User;
  onPublish?: (imageId: string) => void;
  onProcess?: (imagery: Imagery) => void;
}

export function ImageryDetailDrawer({ imageId, onClose, projects, currentUser, onPublish, onProcess }: ImageryDetailDrawerProps) {
  const screens = Grid.useBreakpoint();
  const { message, modal } = App.useApp();
  const [view, setView] = useState<'preview' | 'map'>('preview');
  const [editing, setEditing] = useState(false);
  const [form] = Form.useForm();
  const detailQuery = useImageryDetail(imageId);
  const updateImagery = useUpdateImagery();
  const archiveImagery = useArchiveImagery();
  const restoreImagery = useRestoreImagery();
  const imagery = detailQuery.data;
  const bounds = useMemo(() => imageryBounds(imagery), [imagery]);
  const manageable = imagery ? canManageImagery(imagery, currentUser) : false;

  useEffect(() => {
    setEditing(false);
    setView('preview');
  }, [imageId]);

  useEffect(() => {
    if (!imagery) return;
    form.setFieldsValue({
      display_name: imagery.display_name,
      description: imagery.description,
      project_ids: imagery.project_ids ?? imagery.projects?.map((project) => project.id) ?? []
    });
  }, [form, imagery]);

  const save = async () => {
    if (!imagery) return;
    try {
      const values = await form.validateFields();
      await updateImagery.mutateAsync({ imageId: imagery.image_id, payload: values });
      message.success('影像信息已更新');
      setEditing(false);
    } catch (error) {
      if (error instanceof Error) message.error(normalizeError(error));
    }
  };

  const confirmArchive = () => {
    if (!imagery) return;
    modal.confirm({
      title: '归档这景影像？',
      content: '归档后将从普通检索和地图中隐藏，已有服务不受影响。',
      okText: '归档',
      okButtonProps: { danger: true },
      cancelText: '取消',
      onOk: async () => {
        try {
          await archiveImagery.mutateAsync(imagery.image_id);
          message.success('影像已归档');
          onClose();
        } catch (error) {
          message.error(normalizeError(error));
        }
      }
    });
  };

  const restore = async () => {
    if (!imagery) return;
    try {
      await restoreImagery.mutateAsync(imagery.image_id);
      message.success('影像已恢复');
    } catch (error) {
      message.error(normalizeError(error));
    }
  };

  return (
    <Drawer
      title={imagery ? imageryName(imagery) : '影像详情'}
      open={Boolean(imageId)}
      onClose={onClose}
      width={screens.md ? 420 : '100%'}
      extra={manageable && !editing ? <Button type="text" icon={<EditOutlined />} title="编辑" onClick={() => setEditing(true)} /> : null}
    >
      {detailQuery.isLoading ? <Spin /> : null}
      {detailQuery.isError ? <Empty description={normalizeError(detailQuery.error)} /> : null}
      {imagery ? (
        <Space direction="vertical" size={14} className="full-width imagery-detail-content">
          <Segmented
            block
            value={view}
            onChange={(value) => setView(value as 'preview' | 'map')}
            options={[{ value: 'preview', label: '缩略图' }, { value: 'map', label: '地图' }]}
          />
          {view === 'preview' ? (
            <ImageryThumbnail imagery={imagery} large />
          ) : bounds ? (
            <div className="detail-map">
              <MapContainer center={[31.23, 121.47]} zoom={5} scrollWheelZoom className="map">
                <RefreshMapSize />
                <BaseMapLayer />
                <FitBounds bounds={bounds} />
                <ImageOverlay
                  url={api.imageryAssetUrl(imagery.image_id, imagery.preview_status === 'ready' ? 'preview' : 'thumbnail')}
                  bounds={bounds}
                  opacity={0.82}
                />
              </MapContainer>
            </div>
          ) : (
            <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无空间范围" />
          )}

          {editing ? (
            <Form form={form} layout="vertical" requiredMark={false}>
              <Form.Item name="display_name" label="显示名称"><Input maxLength={255} placeholder={imagery.source_name} /></Form.Item>
              <Form.Item name="description" label="备注"><Input.TextArea rows={4} maxLength={1000} showCount /></Form.Item>
              <Form.Item name="project_ids" label="项目标签">
                <Select mode="multiple" allowClear options={projects.map((project) => ({ value: project.id, label: project.name }))} />
              </Form.Item>
              <Space>
                <Button type="primary" icon={<SaveOutlined />} loading={updateImagery.isPending} onClick={() => void save()}>保存</Button>
                <Button onClick={() => setEditing(false)}>取消</Button>
              </Space>
            </Form>
          ) : (
            <Descriptions size="small" bordered column={1}>
              <Descriptions.Item label="源文件名">{imagery.source_name}</Descriptions.Item>
              <Descriptions.Item label="平台 / 卫星">{imagery.platform_code ?? imagery.platform ?? '-'} / {imagery.satellite_name ?? '-'}</Descriptions.Item>
              <Descriptions.Item label="传感器 / 模式">{imagery.sensor ?? '-'} / {imagery.imaging_mode_detail ?? imagery.imaging_mode ?? '-'}</Descriptions.Item>
              <Descriptions.Item label="级别 / 极化">{imagery.product_level ?? '-'} / {imagery.polarization ?? '-'}</Descriptions.Item>
              <Descriptions.Item label="分辨率">{imagery.resolution_m !== undefined ? `${imagery.resolution_m} 米` : '-'}</Descriptions.Item>
              <Descriptions.Item label="拍摄时间">{imagery.acquisition_time ? dayjs(imagery.acquisition_time).format('YYYY-MM-DD HH:mm:ss') : '-'}</Descriptions.Item>
              <Descriptions.Item label="状态">
                <Space size={4} wrap>
                  <Tag color={imagery.is_archived ? 'default' : 'success'}>{imagery.is_archived ? '已归档' : '可用'}</Tag>
                  <Tag>{imagery.metadata_status ?? '元数据未知'}</Tag>
                  <Tag>{imagery.preview_status === 'ready' ? '有预览' : '无预览'}</Tag>
                </Space>
              </Descriptions.Item>
              {imagery.description ? <Descriptions.Item label="备注">{imagery.description}</Descriptions.Item> : null}
            </Descriptions>
          )}

          <Space wrap>
            <Button icon={<DownloadOutlined />} href={api.imageryAssetUrl(imagery.image_id, 'data')}>下载</Button>
            {onProcess && !imagery.is_archived ? <Button icon={<ScissorOutlined />} onClick={() => onProcess(imagery)}>在线处理</Button> : null}
            {onPublish && !imagery.is_archived ? <Button icon={<ApiOutlined />} onClick={() => onPublish(imagery.image_id)}>发布服务</Button> : null}
            {manageable && !imagery.is_archived ? <Button danger icon={<DeleteOutlined />} onClick={confirmArchive}>归档</Button> : null}
            {manageable && imagery.is_archived ? <Button icon={<RollbackOutlined />} loading={restoreImagery.isPending} onClick={() => void restore()}>恢复</Button> : null}
          </Space>
          <Typography.Text type="secondary" className="record-id">ID：{imagery.image_id}</Typography.Text>
        </Space>
      ) : null}
    </Drawer>
  );
}
