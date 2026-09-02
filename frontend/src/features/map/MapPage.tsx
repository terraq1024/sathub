import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Alert, App as AntdApp, Button, Checkbox, Descriptions, Empty, Form, Input, Modal, Select, Slider, Space, Spin, Tabs, Tag, Typography } from 'antd';
import { CloseOutlined, DeleteOutlined, EnvironmentOutlined, FolderOpenOutlined, SaveOutlined, SplitCellsOutlined } from '@ant-design/icons';
import dayjs from 'dayjs';
import type { ImageOverlay as LeafletImageOverlay } from 'leaflet';
import { GeoJSON, ImageOverlay, MapContainer, Popup } from 'react-leaflet';
import { api } from '../../api/client';
import { useImageryDetail, useImageryFacets, useImageryMap } from '../../api/hooks';
import type { Imagery, ImagerySavedSearch, ImagerySearchParams, Project } from '../../api/types';
import { FitBounds, RefreshMapSize, TianDiTuLayer, type BaseMapType } from '../imagery/MapPrimitives';
import { ImageryFilters, filtersToParams, type ImageryFilterValues } from '../imagery/ImageryFilters';
import { SelectionActions } from '../imagery/SelectionActions';
import { imageryBounds, imageryName, normalizeError } from '../imagery/utils';

type MapImagery = Imagery & { geometry?: Record<string, unknown> | null };

function imageryPreviewRole(imagery: Imagery) {
  return imagery.preview_status === 'ready' ? 'preview' : 'thumbnail';
}

function hasPreview(imagery: Imagery) {
  return imagery.preview_status === 'ready' || Boolean(imagery.thumbnail_path);
}

function PreviewImageLayer({
  imagery,
  opacity,
  zIndex,
  splitEnabled,
  splitPosition,
}: {
  imagery: MapImagery;
  opacity: number;
  zIndex: number;
  splitEnabled: boolean;
  splitPosition: number;
}) {
  const bounds = imageryBounds(imagery);
  const layerRef = useRef<LeafletImageOverlay | null>(null);
  const handleLayerRef = useCallback((layer: LeafletImageOverlay | null) => { layerRef.current = layer; }, []);

  useEffect(() => {
    const timer = window.setTimeout(() => {
      const element = layerRef.current?.getElement();
      if (element) element.style.clipPath = splitEnabled ? `inset(0 0 0 ${splitPosition}%)` : '';
    }, 0);
    return () => window.clearTimeout(timer);
  }, [splitEnabled, splitPosition]);

  if (!bounds || !hasPreview(imagery)) return null;
  return (
    <ImageOverlay
      ref={handleLayerRef}
      url={api.imageryAssetUrl(imagery.image_id, imageryPreviewRole(imagery))}
      bounds={bounds}
      opacity={opacity}
      zIndex={zIndex}
    />
  );
}

function ResultItem({
  imagery,
  active,
  checked,
  onFocus,
  onCheck
}: {
  imagery: Imagery;
  active: boolean;
  checked: boolean;
  onFocus: () => void;
  onCheck: (checked: boolean) => void;
}) {
  return (
    <div className={`map-result ${active ? 'map-result-active' : ''}`}>
      <Checkbox checked={checked} onChange={(event) => onCheck(event.target.checked)} aria-label={`选择 ${imageryName(imagery)}`} />
      <button type="button" onClick={onFocus}>
        <span className="map-result-name">{imageryName(imagery)}</span>
        <span className="map-result-meta">{imagery.platform ?? imagery.platform_code ?? '-'} · {imagery.product_level ?? '-'} · {imagery.polarization ?? '-'}</span>
        <span className="map-result-meta">{imagery.acquisition_time ? dayjs(imagery.acquisition_time).format('YYYY-MM-DD HH:mm') : '时间未知'}</span>
      </button>
    </div>
  );
}

function LayerWorkbench({
  item,
  opacities,
  splitEnabled,
  splitPosition,
  onSplitChange,
  onSplitPositionChange,
  onOpacityChange,
  onClear
}: {
  item?: MapImagery;
  opacities: Record<string, number>;
  splitEnabled: boolean;
  splitPosition: number;
  onSplitChange: (enabled: boolean) => void;
  onSplitPositionChange: (position: number) => void;
  onOpacityChange: (imageId: string, value: number) => void;
  onClear: () => void;
}) {
  if (!item) return null;

  return (
    <div className="map-layer-toolbar" aria-label="地图预览控制">
      <Typography.Text strong>单景预览</Typography.Text>
      <Typography.Text type="secondary" className="map-layer-toolbar-name" title={imageryName(item)}>{imageryName(item)}</Typography.Text>
      <Typography.Text type="secondary">透明度</Typography.Text>
      <Slider className="map-layer-toolbar-slider" min={0} max={100} value={opacities[item.image_id] ?? 82} onChange={(value) => onOpacityChange(item.image_id, value)} tooltip={{ formatter: (value) => `${value ?? 82}%` }} />
      <Button size="small" type={splitEnabled ? 'primary' : 'default'} icon={<SplitCellsOutlined />} onClick={() => onSplitChange(!splitEnabled)}>卷帘</Button>
      {splitEnabled ? <Slider className="map-layer-toolbar-swipe" min={5} max={95} value={splitPosition} onChange={onSplitPositionChange} tooltip={{ formatter: (value) => `分界 ${value ?? splitPosition}%` }} /> : null}
      <Button size="small" type="text" icon={<CloseOutlined />} onClick={onClear} title="关闭预览" aria-label="关闭预览" />
    </div>
  );
}

export function MapPage({ projects, projectLoading }: { projects: Project[]; projectLoading?: boolean }) {
  const { message: messageApi } = AntdApp.useApp();
  const [filters, setFilters] = useState<ImageryFilterValues>({});
  const [baseMap, setBaseMap] = useState<BaseMapType>('vec');
  const [saveOpen, setSaveOpen] = useState(false);
  const [saveForm] = Form.useForm<{ name: string; description?: string }>();
  const [hasSearched, setHasSearched] = useState(false);
  const [leftTab, setLeftTab] = useState<'search' | 'results' | 'saved'>('search');
  const [savedSearches, setSavedSearches] = useState<ImagerySavedSearch[]>([]);
  const [savedLoading, setSavedLoading] = useState(false);
  const [selectedIds, setSelectedIds] = useState<string[]>([]);
  const [layerOpacities, setLayerOpacities] = useState<Record<string, number>>({});
  const [splitEnabled, setSplitEnabled] = useState(false);
  const [splitPosition, setSplitPosition] = useState(50);
  const [focusId, setFocusId] = useState<string>();
  const [imageryCache, setImageryCache] = useState<Record<string, MapImagery>>({});
  const params = useMemo<ImagerySearchParams>(
    () => ({ ...filtersToParams(filters), page: 1, page_size: 200 }),
    [filters]
  );
  const mapQuery = useImageryMap(params, hasSearched);
  const facetsQuery = useImageryFacets();
  const detailQuery = useImageryDetail(focusId);
  const imagery = useMemo(
    () => mapQuery.data?.features.map((feature) => ({ ...feature.properties, image_id: feature.properties.image_id || feature.id, geometry: feature.geometry })) ?? [],
    [mapQuery.data]
  );
  const focusBounds = useMemo(() => {
    const cached = focusId ? imageryCache[focusId] : undefined;
    return imageryBounds(cached ?? detailQuery.data);
  }, [detailQuery.data, focusId, imageryCache]);
  const focusedImagery = useMemo(() => {
    if (!focusId) return undefined;
    const item = imageryCache[focusId] ?? imagery.find((candidate) => candidate.image_id === focusId);
    return item && hasPreview(item) && imageryBounds(item) ? item : undefined;
  }, [focusId, imagery, imageryCache]);

  const loadSavedSearches = useCallback(async () => {
    setSavedLoading(true);
    try {
      const response = await api.savedSearches();
      setSavedSearches(Array.isArray(response) ? response : response.results);
    } catch (error) {
      messageApi.error(normalizeError(error));
    } finally {
      setSavedLoading(false);
    }
  }, [messageApi]);

  useEffect(() => { void loadSavedSearches(); }, [loadSavedSearches]);

  useEffect(() => {
    if (!imagery.length) return;
    setImageryCache((current) => {
      const next = { ...current };
      imagery.forEach((item) => { next[item.image_id] = item; });
      return next;
    });
  }, [imagery]);

  useEffect(() => {
    if (!detailQuery.data) return;
    setImageryCache((current) => ({
      ...current,
      [detailQuery.data.image_id]: { ...detailQuery.data, geometry: detailQuery.data.geometry ?? detailQuery.data.footprint_geojson }
    }));
  }, [detailQuery.data]);

  const toggle = (imageId: string, checked: boolean) => {
    setSelectedIds((current) => checked ? [...new Set([...current, imageId])] : current.filter((id) => id !== imageId));
    setLayerOpacities((current) => ({ ...current, [imageId]: current[imageId] ?? 82 }));
  };

  const clearSelection = () => {
    setSelectedIds([]);
    setSplitEnabled(false);
  };

  const applyFilters = (values: ImageryFilterValues) => {
    setFilters(values);
    setHasSearched(true);
    setFocusId(undefined);
    clearSelection();
  };

  const browseLayer = (imageId: string) => {
    setSplitEnabled(false);
    setFocusId(imageId);
  };

  const focusImagery = (imageId: string) => {
    browseLayer(imageId);
    setLeftTab('results');
  };

  const saveQuery = async () => {
    const values = await saveForm.validateFields();
    try {
      await api.createSavedSearch({ name: values.name, description: values.description ?? '', query_definition: filtersToParams(filters) });
      messageApi.success('查询已保存');
      await loadSavedSearches();
      setSaveOpen(false);
      saveForm.resetFields();
    } catch (error) {
      messageApi.error(normalizeError(error));
    }
  };

  const applySavedSearch = (item: ImagerySavedSearch) => {
    const query = item.query_definition ?? {};
    const next = { ...query } as Record<string, unknown>;
    if (query.time_start && query.time_end) next.time = [dayjs(String(query.time_start)), dayjs(String(query.time_end))];
    delete next.time_start;
    delete next.time_end;
    setFilters(next as ImageryFilterValues);
    setHasSearched(true);
    setFocusId(undefined);
    clearSelection();
    setLeftTab('results');
  };

  const deleteSavedSearch = async (item: ImagerySavedSearch) => {
    try {
      await api.deleteSavedSearch(item.id);
      messageApi.success('保存的查询已删除');
      await loadSavedSearches();
    } catch (error) {
      messageApi.error(normalizeError(error));
    }
  };

  return (
    <div className={`map-page ${focusId ? 'map-page-with-detail' : ''}`}>
      <MapContainer center={[31.2, 115]} zoom={5} scrollWheelZoom className="map">
        <RefreshMapSize trigger={Boolean(focusId)} />
        <TianDiTuLayer mapType={baseMap} />
        <FitBounds bounds={focusBounds} maxZoom={13} />
        {imagery.map((item) => {
          if (!item.geometry) return null;
          const active = item.image_id === focusId;
          const checked = selectedIds.includes(item.image_id);
          return (
            <GeoJSON
              key={`${item.image_id}-${active}-${checked}`}
              data={item.geometry as never}
              style={{
                color: active ? '#f97316' : checked ? '#16a34a' : '#1677ff',
                weight: active ? 3 : 2,
                fillOpacity: active ? 0.28 : checked ? 0.22 : 0.12
              }}
              eventHandlers={{ click: () => focusImagery(item.image_id) }}
            >
              <Popup>
                <Space direction="vertical" size={6}>
                  <Typography.Text strong>{imageryName(item)}</Typography.Text>
                  <Checkbox checked={checked} onChange={(event) => toggle(item.image_id, event.target.checked)}>加入选择</Checkbox>
                </Space>
              </Popup>
            </GeoJSON>
          );
        })}
        {focusedImagery ? <PreviewImageLayer
          key={`${focusedImagery.image_id}-${splitEnabled}`}
          imagery={focusedImagery}
          opacity={(layerOpacities[focusedImagery.image_id] ?? 82) / 100}
          zIndex={400}
          splitEnabled={splitEnabled}
          splitPosition={splitPosition}
        /> : null}
      </MapContainer>

      <div className="map-basemap-switcher" aria-label="底图切换">
        <Typography.Text>底图</Typography.Text>
        <Select<BaseMapType>
          size="small"
          value={baseMap}
          options={[{ value: 'vec', label: '电子地图' }, { value: 'img', label: '影像地图' }, { value: 'esri', label: 'Esri 影像' }]}
          onChange={setBaseMap}
        />
      </div>

      <aside className="map-search-panel">
        <Tabs
          size="small"
          activeKey={leftTab}
          onChange={(key) => setLeftTab(key as 'search' | 'results' | 'saved')}
          items={[
            {
              key: 'search',
              label: <Space size={5}><EnvironmentOutlined />检索</Space>,
              children: <div className="map-search-tab-content">
                <div style={{ display: 'flex', gap: 6, alignItems: 'center', marginBottom: 8 }}>
                  <Button size="small" icon={<SaveOutlined />} disabled={!Object.keys(filtersToParams(filters)).length} onClick={() => setSaveOpen(true)}>保存查询</Button>
                </div>
                <ImageryFilters compact allowArchived={false} projects={projects} projectLoading={projectLoading} facets={facetsQuery.data} values={filters} onApply={(values) => { applyFilters(values); setLeftTab('results'); }} />
                {mapQuery.isError ? <Alert type="error" showIcon message={normalizeError(mapQuery.error)} /> : null}
              </div>
            },
            {
              key: 'results',
              label: <Space size={5}>结果 <Tag color="blue">{mapQuery.data?.count ?? 0}</Tag></Space>,
              children: <>
                <Typography.Text type="secondary" className="viewport-note">当前查询结果，最多显示 200 景</Typography.Text>
                <div className="map-results">
                  {mapQuery.isLoading ? <Spin /> : null}
                  {!mapQuery.isLoading && !imagery.length ? <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={hasSearched ? '查询暂无影像' : '请先执行查询'} /> : null}
                  {imagery.map((item) => (
                    <ResultItem
                      key={item.image_id}
                      imagery={item}
                      active={focusId === item.image_id}
                      checked={selectedIds.includes(item.image_id)}
                      onFocus={() => focusImagery(item.image_id)}
                      onCheck={(checked) => toggle(item.image_id, checked)}
                    />
                  ))}
                </div>
              </>
            },
            {
              key: 'saved',
              label: <Space size={5}><FolderOpenOutlined />已保存</Space>,
              children: <div className="map-saved-searches">
                {savedLoading ? <Spin /> : null}
                {!savedLoading && !savedSearches.length ? <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无保存的查询" /> : null}
                {savedSearches.map((item) => <div className="map-saved-search" key={item.id}>
                  <button type="button" onClick={() => applySavedSearch(item)}>
                    <Typography.Text strong>{item.name}</Typography.Text>
                    <Typography.Text type="secondary" ellipsis>{item.description || '无说明'}</Typography.Text>
                  </button>
                  <Button type="text" danger size="small" icon={<DeleteOutlined />} aria-label={`删除 ${item.name}`} onClick={() => void deleteSavedSearch(item)} />
                </div>)}
              </div>
            }
          ]}
        />
      </aside>

      <LayerWorkbench
        item={focusedImagery}
        opacities={layerOpacities}
        splitEnabled={splitEnabled}
        splitPosition={splitPosition}
        onSplitChange={setSplitEnabled}
        onSplitPositionChange={setSplitPosition}
        onOpacityChange={(imageId, value) => setLayerOpacities((current) => ({ ...current, [imageId]: value }))}
        onClear={() => { setSplitEnabled(false); setFocusId(undefined); }}
      />

      {focusId ? (
        <aside className="map-detail-panel" aria-label="影像详情">
          <div className="map-detail-header">
            <div>
              <Typography.Text strong>{detailQuery.data ? imageryName(detailQuery.data) : '影像详情'}</Typography.Text>
              <Typography.Text type="secondary">已在地图加载预览图</Typography.Text>
            </div>
            <Button type="text" size="small" icon={<CloseOutlined />} title="关闭" onClick={() => setFocusId(undefined)} />
          </div>
          <div className="map-detail-body">
            {detailQuery.isLoading ? <Spin /> : null}
            {detailQuery.data ? (
              <Descriptions size="small" bordered column={1} layout="vertical">
                <Descriptions.Item label="平台 / 卫星">{detailQuery.data.platform_code ?? detailQuery.data.platform ?? '-'} / {detailQuery.data.satellite_name ?? '-'}</Descriptions.Item>
                <Descriptions.Item label="传感器 / 模式">{detailQuery.data.sensor ?? '-'} / {detailQuery.data.imaging_mode_detail ?? detailQuery.data.imaging_mode ?? '-'}</Descriptions.Item>
                <Descriptions.Item label="级别 / 极化">{detailQuery.data.product_level ?? '-'} / {detailQuery.data.polarization ?? '-'}</Descriptions.Item>
                <Descriptions.Item label="分辨率">{detailQuery.data.resolution_m !== undefined ? `${detailQuery.data.resolution_m} 米` : '-'}</Descriptions.Item>
                <Descriptions.Item label="拍摄时间">{detailQuery.data.acquisition_time ? dayjs(detailQuery.data.acquisition_time).format('YYYY-MM-DD HH:mm:ss') : '-'}</Descriptions.Item>
              </Descriptions>
            ) : null}
          </div>
        </aside>
      ) : null}
      <SelectionActions selectedIds={selectedIds} onClear={() => setSelectedIds([])} />
      <Modal title="保存空间查询" open={saveOpen} onCancel={() => setSaveOpen(false)} onOk={() => void saveQuery()} okText="保存" cancelText="取消">
        <Form form={saveForm} layout="vertical">
          <Form.Item name="name" label="查询名称" rules={[{ required: true, message: '请输入查询名称' }]}><Input placeholder="例如：上海区域 SAR 影像" /></Form.Item>
          <Form.Item name="description" label="说明"><Input.TextArea rows={3} placeholder="可选" /></Form.Item>
        </Form>
      </Modal>
    </div>
  );
}
