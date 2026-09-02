import { useEffect, useMemo, useState } from 'react';
import { Button, DatePicker, Form, Input, InputNumber, Popover, Select, Segmented, Switch } from 'antd';
import { FilterOutlined } from '@ant-design/icons';
import type { Dayjs } from 'dayjs';
import type { ImageryFacetOption, ImagerySearchParams, Project } from '../../api/types';

export interface ImageryFilterValues {
  q?: string;
  platform?: string;
  sensor_type?: 'sar' | 'optical';
  source_vendor?: string;
  satellite_name?: string;
  sensor?: string;
  imaging_mode?: string;
  product_level?: string;
  polarization?: string;
  cog_status?: string;
  administrative_unit_id?: string;
  classification_id?: string;
  tag_id?: string;
  project_id?: string | number;
  resolution_min?: number;
  resolution_max?: number;
  time?: [Dayjs, Dayjs];
  include_archived?: boolean;
  geometry?: string;
}

export function filtersToParams(values: ImageryFilterValues): ImagerySearchParams {
  return {
    q: values.q?.trim() || undefined,
    platform: values.platform?.trim() || undefined,
    sensor_type: values.sensor_type || undefined,
    source_vendor: values.source_vendor?.trim() || undefined,
    satellite_name: values.satellite_name?.trim() || undefined,
    sensor: values.sensor?.trim() || undefined,
    imaging_mode: values.sensor_type === 'sar' ? values.imaging_mode?.trim() || undefined : undefined,
    product_level: values.product_level,
    polarization: values.sensor_type === 'sar' ? values.polarization : undefined,
    cog_status: values.cog_status,
    administrative_unit_id: values.administrative_unit_id?.trim() || undefined,
    classification_id: values.classification_id?.trim() || undefined,
    tag_id: values.tag_id?.trim() || undefined,
    project_id: values.project_id,
    resolution_min: values.resolution_min,
    resolution_max: values.resolution_max,
    include_archived: values.include_archived || undefined,
    geometry: values.geometry?.trim() || undefined,
    time_start: values.time?.[0]?.toISOString(),
    time_end: values.time?.[1]?.toISOString()
  };
}

interface ImageryFiltersProps {
  projects: Project[];
  projectLoading?: boolean;
  facets?: {
    satellites: ImageryFacetOption[];
    vendors: ImageryFacetOption[];
    polarizations: ImageryFacetOption[];
    imaging_modes: ImageryFacetOption[];
    product_levels: ImageryFacetOption[];
  };
  values?: ImageryFilterValues;
  onApply: (values: ImageryFilterValues) => void;
  compact?: boolean;
  allowArchived?: boolean;
}

// Fields rendered in the always-visible bar; everything else counts toward the
// advanced-filter badge (product_level lives in the advanced popover).
const BASIC_FILTER_KEYS = ['q', 'sensor_type', 'source_vendor', 'satellite_name', 'polarization', 'imaging_mode', 'resolution_min', 'resolution_max'];
const FILTER_FIELD_KEYS = ['q', 'platform', 'sensor_type', 'source_vendor', 'satellite_name', 'sensor', 'imaging_mode', 'product_level', 'polarization', 'cog_status', 'administrative_unit_id', 'classification_id', 'tag_id', 'project_id', 'resolution_min', 'resolution_max', 'time', 'include_archived', 'geometry'];

export function ImageryFilters({ projects, projectLoading, facets, values, onApply, compact = false, allowArchived = true }: ImageryFiltersProps) {
  const [form] = Form.useForm<ImageryFilterValues>();
  const [advancedOpen, setAdvancedOpen] = useState(false);
  const sensorType = Form.useWatch('sensor_type', form);

  useEffect(() => {
    // Replace (not merge) so a sparser `values` (e.g. applying a saved search)
    // clears fields that are absent from the new definition.
    const next: Record<string, unknown> = {};
    FILTER_FIELD_KEYS.forEach((field) => { next[field] = (values as Record<string, unknown> | undefined)?.[field] ?? undefined; });
    form.setFieldsValue(next);
  }, [form, values]);

  const advancedCount = useMemo(
    () =>
      Object.entries(values ?? {}).filter(([key, value]) => {
        if (BASIC_FILTER_KEYS.includes(key) || value === undefined || value === '') return false;
        if (typeof value === 'boolean') return value;
        return !Array.isArray(value) || value.length;
      }).length,
    [values]
  );

  const submit = () => form.submit();
  const reset = () => {
    form.resetFields();
    setAdvancedOpen(false);
    onApply({});
  };

  const advanced = (
    <div className="advanced-filter-panel">
      <div className="advanced-filter-grid">
        <Form.Item name="cog_status" label="COG 状态">
          <Select allowClear options={[
            { value: 'none', label: '未生成' },
            { value: 'queued', label: '排队中' },
            { value: 'processing', label: '生成中' },
            { value: 'ready', label: '可服务' },
            { value: 'failed', label: '失败' },
            { value: 'stale', label: '待更新' }
          ]} />
        </Form.Item>
        <Form.Item name="product_level" label="产品级别">
          <Select allowClear showSearch placeholder="选择产品级别" options={(facets?.product_levels ?? []).map((item) => ({ value: item.value, label: `${item.label}（${item.count}景）` }))} />
        </Form.Item>
        <Form.Item name="administrative_unit_id" label="行政区 ID"><Input allowClear placeholder="支持多个，逗号分隔" /></Form.Item>
        <Form.Item name="classification_id" label="分类 ID"><Input allowClear placeholder="支持多个，逗号分隔" /></Form.Item>
        <Form.Item name="tag_id" label="标签 ID"><Input allowClear placeholder="支持多个，逗号分隔" /></Form.Item>
        <Form.Item name="project_id" label="项目标签">
          <Select
            allowClear
            loading={projectLoading}
            options={projects.map((project) => ({ value: project.id, label: project.name }))}
          />
        </Form.Item>
        <Form.Item name="time" label="拍摄时间" className="filter-time-field">
          <DatePicker.RangePicker showTime className="full-width" />
        </Form.Item>
        <Form.Item name="geometry" label="空间范围 GeoJSON" className="filter-time-field">
          <Input.TextArea rows={2} placeholder='例如 {"type":"Polygon","coordinates":[...]}' />
        </Form.Item>
        {allowArchived ? (
          <Form.Item name="include_archived" label="归档数据" valuePropName="checked">
            <Switch checkedChildren="显示" unCheckedChildren="隐藏" />
          </Form.Item>
        ) : null}
      </div>
      <div className="advanced-filter-actions">
        <Button onClick={reset}>重置</Button>
        <Button type="primary" onClick={() => { setAdvancedOpen(false); submit(); }}>应用筛选</Button>
      </div>
    </div>
  );

  return (
    <Form
      form={form}
      className={`imagery-filter-bar ${compact ? 'imagery-filter-bar-compact' : ''}`}
      onFinish={(next) => onApply(next)}
    >
      <Form.Item name="q" noStyle>
        <Input.Search allowClear placeholder="名称、任务号或文件名" enterButton="查询" onSearch={submit} />
      </Form.Item>
      {compact ? <div className="map-filter-section-title">基础条件</div> : null}
      <div className="basic-filter-fields">
        <Form.Item name="sensor_type" label="数据类型" className="basic-filter-item filter-type-item">
          <Segmented block options={[{ label: '全部', value: '' }, { label: 'SAR', value: 'sar' }, { label: '光学', value: 'optical' }]} />
        </Form.Item>
        <Form.Item name="source_vendor" label="厂商" className="basic-filter-item">
          <Select
            allowClear
            showSearch
            placeholder="选择厂商"
            options={(facets?.vendors ?? []).map((item) => ({ value: item.value, label: `${item.label}（${item.count}景）` }))}
            filterOption={(input, option) => String(option?.label ?? '').toLowerCase().includes(input.toLowerCase())}
          />
        </Form.Item>
        <Form.Item name="satellite_name" label="卫星" className="basic-filter-item">
          <Select allowClear showSearch placeholder="选择卫星" options={(facets?.satellites ?? []).map((item) => ({ value: item.value, label: `${item.label}（${item.count}景）` }))} filterOption={(input, option) => String(option?.label ?? '').toLowerCase().includes(input.toLowerCase())} />
        </Form.Item>
        {sensorType === 'sar' ? <>
            <Form.Item name="polarization" label="极化方式" className="basic-filter-item"><Select allowClear showSearch placeholder="选择极化方式" options={(facets?.polarizations ?? []).map((item) => ({ value: item.value, label: `${item.label}（${item.count}景）` }))} /></Form.Item>
            <Form.Item name="imaging_mode" label="成像方式" className="basic-filter-item"><Select allowClear showSearch placeholder="选择成像方式" options={(facets?.imaging_modes ?? []).map((item) => ({ value: item.value, label: `${item.label}（${item.count}景）` }))} /></Form.Item>
          </> : null}
        <Form.Item name="resolution_min" label="分辨率起始（米）" className="basic-filter-item"><InputNumber min={0} placeholder="不限" /></Form.Item>
        <Form.Item name="resolution_max" label="分辨率上限（米）" className="basic-filter-item"><InputNumber min={0} placeholder="不限" /></Form.Item>
      </div>
      <Popover
        trigger="click"
        placement="bottomLeft"
        open={advancedOpen}
        onOpenChange={setAdvancedOpen}
        title="高级查询"
        content={advanced}
      >
        <Button icon={<FilterOutlined />}>高级查询{advancedCount ? ` ${advancedCount}` : ''}</Button>
      </Popover>
    </Form>
  );
}
