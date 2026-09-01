import { useEffect, useMemo, useState } from 'react';
import {
  Alert,
  App,
  Button,
  Divider,
  Drawer,
  Empty,
  Form,
  Grid,
  Input,
  InputNumber,
  List,
  Segmented,
  Select,
  Space,
  Spin,
  Tag,
  Typography
} from 'antd';
import { DownloadOutlined, ReloadOutlined, ScissorOutlined } from '@ant-design/icons';
import dayjs from 'dayjs';
import { api } from '../../api/client';
import {
  unwrapList,
  useCreateProcessingJob,
  useProcessingJobs,
  useRetryProcessingJob
} from '../../api/hooks';
import type {
  CreateProcessingJobPayload,
  Imagery,
  ProcessingCropType,
  ProcessingJob,
  ProcessingJobStatus,
  ProcessingOutputFormat
} from '../../api/types';
import { imageryName, normalizeError } from '../imagery/utils';

interface ProcessingDrawerProps {
  open: boolean;
  imagery?: Imagery;
  onClose: () => void;
}

interface ProcessingFormValues {
  crop_geometry_type: ProcessingCropType;
  bbox?: Array<number | null>;
  geometry_text?: string;
  bands?: string[];
  expression?: string;
  output_format: ProcessingOutputFormat;
}

const STATUS_META: Record<ProcessingJobStatus, { label: string; color: string }> = {
  pending: { label: '待处理', color: 'default' },
  queued: { label: '排队中', color: 'processing' },
  running: { label: '处理中', color: 'processing' },
  succeeded: { label: '已完成', color: 'success' },
  failed: { label: '失败', color: 'error' },
  canceled: { label: '已取消', color: 'default' }
};

function defaultBbox(imagery?: Imagery): number[] | undefined {
  if (imagery?.bbox?.length === 4) return [...imagery.bbox];
  if (
    imagery?.min_lon !== undefined && imagery.min_lat !== undefined &&
    imagery.max_lon !== undefined && imagery.max_lat !== undefined
  ) {
    return [imagery.min_lon, imagery.min_lat, imagery.max_lon, imagery.max_lat];
  }
  return undefined;
}

function parsePolygon(value?: string) {
  if (!value?.trim()) throw new Error('请输入 Polygon GeoJSON');
  let geometry: unknown;
  try {
    geometry = JSON.parse(value);
  } catch {
    throw new Error('Polygon JSON 格式不正确');
  }
  if (!geometry || typeof geometry !== 'object') throw new Error('请输入有效的 Polygon GeoJSON');
  const candidate = geometry as { type?: unknown; coordinates?: unknown };
  if (candidate.type !== 'Polygon' || !Array.isArray(candidate.coordinates)) {
    throw new Error('空间范围必须是 Polygon geometry');
  }
  const outerRing = candidate.coordinates[0];
  if (!Array.isArray(outerRing) || outerRing.length < 4) throw new Error('Polygon 外环至少需要 4 个坐标点');
  return geometry as Record<string, unknown>;
}

function normalizeBands(values?: string[]) {
  const valuesAsText = [...new Set((values ?? []).map((value) => String(value).trim()).filter(Boolean))];
  if (valuesAsText.some((value) => !/^\d+$/.test(value) || Number(value) < 1)) {
    throw new Error('波段索引必须是大于 0 的整数');
  }
  return valuesAsText.map(Number);
}

function jobImageryName(job: ProcessingJob) {
  if (job.imagery_name) return job.imagery_name;
  if (job.imagery && typeof job.imagery === 'object') return imageryName(job.imagery);
  return job.imagery_id || String(job.imagery ?? '影像');
}

export function ProcessingDrawer({ open, imagery, onClose }: ProcessingDrawerProps) {
  const screens = Grid.useBreakpoint();
  const { message } = App.useApp();
  const [form] = Form.useForm<ProcessingFormValues>();
  const [cropType, setCropType] = useState<ProcessingCropType>('bbox');
  const jobsQuery = useProcessingJobs(open);
  const createJob = useCreateProcessingJob();
  const retryJob = useRetryProcessingJob();
  const jobs = useMemo(() => unwrapList(jobsQuery.data), [jobsQuery.data]);

  useEffect(() => {
    if (!open) return;
    setCropType('bbox');
    form.setFieldsValue({
      crop_geometry_type: 'bbox',
      bbox: defaultBbox(imagery),
      geometry_text: imagery?.geometry ? JSON.stringify(imagery.geometry, null, 2) : '',
      bands: ['1'],
      expression: '',
      output_format: 'geotiff'
    });
  }, [form, imagery, open]);

  const submit = async (values: ProcessingFormValues) => {
    if (!imagery) return;
    try {
      const expression = values.expression?.trim() ?? '';
      const selectedBands = normalizeBands(values.bands);
      if (!selectedBands.length && !expression) {
        form.setFields([{ name: 'bands', errors: ['波段索引和表达式至少填写一项'] }]);
        return;
      }
      const bands = expression ? [] : selectedBands;

      const payload: CreateProcessingJobPayload = {
        imagery_id: imagery.image_id,
        crop_geometry_type: values.crop_geometry_type,
        bands,
        expression,
        output_format: values.output_format
      };
      if (values.crop_geometry_type === 'bbox') {
        const bbox = values.bbox ?? [];
        if (bbox.length !== 4 || bbox.some((value) => value === null || value === undefined)) {
          throw new Error('请完整填写裁剪范围');
        }
        const numbers = bbox.map(Number) as [number, number, number, number];
        if (numbers[0] >= numbers[2] || numbers[1] >= numbers[3]) throw new Error('最小坐标必须小于最大坐标');
        payload.bbox = numbers;
      } else {
        payload.geometry = parsePolygon(values.geometry_text);
      }

      await createJob.mutateAsync(payload);
      message.success('在线处理任务已提交');
    } catch (error) {
      message.error(normalizeError(error));
    }
  };

  const retry = async (jobId: string) => {
    try {
      await retryJob.mutateAsync(jobId);
      message.success('任务已重新提交');
    } catch (error) {
      message.error(normalizeError(error));
    }
  };

  return (
    <Drawer
      title="在线影像处理"
      open={open}
      onClose={onClose}
      width={screens.sm ? 580 : '100%'}
      styles={{ body: { overflowX: 'hidden' } }}
      extra={imagery ? <Typography.Text type="secondary" className="processing-source-name">{imageryName(imagery)}</Typography.Text> : null}
    >
      {!imagery ? <Alert type="warning" showIcon message="请先选择一景影像" /> : null}
      {imagery?.is_archived ? <Alert type="warning" showIcon message="已归档影像不能创建新的处理任务" /> : null}
      {imagery ? (
        <Form<ProcessingFormValues>
          form={form}
          layout="vertical"
          requiredMark={false}
          className="processing-form"
          onFinish={(values) => void submit(values)}
        >
          <Form.Item name="crop_geometry_type" label="裁剪范围" rules={[{ required: true }]}> 
            <Segmented
              block
              options={[{ label: '边界框', value: 'bbox' }, { label: 'Polygon JSON', value: 'polygon' }]}
              onChange={(value) => setCropType(value as ProcessingCropType)}
            />
          </Form.Item>

          {cropType === 'bbox' ? (
            <Form.Item label="边界坐标" required>
              <div className="processing-bbox-grid">
                {[
                  { index: 0, label: '最小经度', min: -180, max: 180 },
                  { index: 1, label: '最小纬度', min: -90, max: 90 },
                  { index: 2, label: '最大经度', min: -180, max: 180 },
                  { index: 3, label: '最大纬度', min: -90, max: 90 }
                ].map((field) => (
                  <Form.Item
                    key={field.index}
                    name={['bbox', field.index]}
                    label={field.label}
                    rules={[{ required: true, message: `请输入${field.label}` }]}
                    noStyle={false}
                  >
                    <InputNumber min={field.min} max={field.max} precision={8} controls={false} className="full-width" />
                  </Form.Item>
                ))}
              </div>
            </Form.Item>
          ) : (
            <Form.Item
              name="geometry_text"
              label="Polygon GeoJSON"
              rules={[{
                validator: async (_, value) => {
                  parsePolygon(value);
                }
              }]}
            >
              <Input.TextArea rows={7} spellCheck={false} placeholder='{"type":"Polygon","coordinates":[[[...]]]}' />
            </Form.Item>
          )}

          <Form.Item name="bands" label="波段索引" extra="输入波段序号后按回车，可选择多个波段。">
            <Select
              mode="tags"
              tokenSeparators={[',', ' ']}
              placeholder="例如 1, 2, 3"
              options={[1, 2, 3, 4].map((value) => ({ label: `波段 ${value}`, value: String(value) }))}
            />
          </Form.Item>
          <Form.Item name="expression" label="波段表达式" extra="例如 (b3-b2)/(b3+b2)。填写后按表达式输出，并忽略上方波段选择。">
            <Input maxLength={500} placeholder="可选" />
          </Form.Item>
          <Form.Item name="output_format" label="输出格式" rules={[{ required: true }]}>
            <Select options={[{ value: 'geotiff', label: 'GeoTIFF' }, { value: 'png', label: 'PNG' }]} />
          </Form.Item>
          <Button
            type="primary"
            htmlType="submit"
            icon={<ScissorOutlined />}
            loading={createJob.isPending}
            disabled={imagery.is_archived}
            block
          >
            提交处理
          </Button>
        </Form>
      ) : null}

      <Divider orientation="left">处理任务</Divider>
      {jobsQuery.isError ? <Alert type="error" showIcon message={normalizeError(jobsQuery.error)} /> : null}
      <Spin spinning={jobsQuery.isLoading}>
        <List
          className="processing-job-list"
          dataSource={jobs}
          locale={{ emptyText: <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无处理任务" /> }}
          renderItem={(job) => {
            const status = STATUS_META[job.status] ?? { label: job.status, color: 'default' };
            const downloadUrl = job.download_url || api.processingDownloadUrl(job.id);
            return (
              <List.Item
                actions={[
                  job.status === 'failed' ? (
                    <Button key="retry" type="link" size="small" icon={<ReloadOutlined />} loading={retryJob.isPending} onClick={() => void retry(job.id)}>重试</Button>
                  ) : null,
                  job.status === 'succeeded' ? (
                    <Button key="download" type="link" size="small" icon={<DownloadOutlined />} href={downloadUrl}>下载</Button>
                  ) : null
                ].filter(Boolean)}
              >
                <List.Item.Meta
                  title={
                    <Space size={6} wrap className="processing-job-title">
                      <Typography.Text ellipsis className="processing-job-name">{jobImageryName(job)}</Typography.Text>
                      <Tag color={status.color}>{status.label}</Tag>
                      <Tag>{job.output_format === 'png' ? 'PNG' : 'GeoTIFF'}</Tag>
                    </Space>
                  }
                  description={
                    <Space direction="vertical" size={2} className="full-width">
                      <Typography.Text type="secondary">{dayjs(job.created_at).format('YYYY-MM-DD HH:mm:ss')}</Typography.Text>
                      {job.error_message ? <Typography.Text type="danger" className="processing-job-error">{job.error_message}</Typography.Text> : null}
                    </Space>
                  }
                />
              </List.Item>
            );
          }}
        />
      </Spin>
    </Drawer>
  );
}
