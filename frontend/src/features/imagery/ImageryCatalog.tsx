import { useState } from 'react';
import {
  Alert,
  App,
  Button,
  Card,
  Checkbox,
  Empty,
  Pagination,
  Segmented,
  Space,
  Spin,
  Table,
  Tag,
  Typography
} from 'antd';
import type { ColumnsType } from 'antd/es/table';
import { AppstoreOutlined, EyeOutlined, UnorderedListOutlined } from '@ant-design/icons';
import dayjs from 'dayjs';
import {
  getListCount,
  unwrapList,
  useImageryFacets,
  useImagery
} from '../../api/hooks';
import type { Imagery, ImagerySearchParams, Project, User } from '../../api/types';
import { ImageryFilters, filtersToParams, type ImageryFilterValues } from './ImageryFilters';
import { ImageryThumbnail } from './ImageryThumbnail';
import { ImageryDetailDrawer } from './ImageryDetailDrawer';
import { SelectionActions } from './SelectionActions';
import { imageryName, normalizeError } from './utils';
import { SectionBar, StatusTag } from '../../components/VisualPrimitives';

type CatalogView = 'list' | 'grid';

interface ImageryCatalogProps {
  projects: Project[];
  projectLoading?: boolean;
  currentUser?: User;
}

export function ImageryCatalog({ projects, projectLoading, currentUser }: ImageryCatalogProps) {
  const [filters, setFilters] = useState<ImageryFilterValues>({});
  const [params, setParams] = useState<ImagerySearchParams>({ page: 1, page_size: 20 });
  const [view, setView] = useState<CatalogView>('list');
  const [selectedIds, setSelectedIds] = useState<string[]>([]);
  const [detailId, setDetailId] = useState<string>();
  const imageryQuery = useImagery(params);
  const facetsQuery = useImageryFacets();
  const records = unwrapList(imageryQuery.data);

  const applyFilters = (values: ImageryFilterValues) => {
    setFilters(values);
    setSelectedIds([]);
    setParams({ ...filtersToParams(values), page: 1, page_size: params.page_size ?? 20 });
  };

  const toggleSelected = (imageId: string, checked: boolean) => {
    setSelectedIds((current) => checked ? [...new Set([...current, imageId])] : current.filter((id) => id !== imageId));
  };

  const columns: ColumnsType<Imagery> = [
    { title: '缩略图', width: 96, render: (_, record) => <ImageryThumbnail imagery={record} /> },
    { title: '影像名称', minWidth: 220, ellipsis: true, render: (_, record) => imageryName(record) },
    { title: '卫星', dataIndex: 'platform', width: 88, render: (value, record) => value || record.platform_code || '-' },
    { title: '模式', dataIndex: 'imaging_mode', width: 100, render: (value) => value || '-' },
    { title: '级别', dataIndex: 'product_level', width: 72, render: (value) => value || '-' },
    { title: '极化', dataIndex: 'polarization', width: 72, render: (value) => value || '-' },
    { title: '分辨率', dataIndex: 'resolution_m', width: 90, render: (value) => value !== undefined ? `${value} m` : '-' },
    { title: '状态', dataIndex: 'is_archived', width: 80, render: (value) => <StatusTag status={value ? 'archived' : 'ready'} /> },
    {
      title: '拍摄时间', dataIndex: 'acquisition_time', width: 150,
      render: (value) => value ? dayjs(value).format('YYYY-MM-DD HH:mm') : '-'
    },
    {
      title: '操作', width: 90,
      render: (_, record) => (
        <Space size={0}>
          <Button type="link" icon={<EyeOutlined />} onClick={() => setDetailId(record.image_id)}>查看</Button>
        </Space>
      )
    }
  ];

  return (
    <div className="catalog-page">
      <div className="catalog-toolbar">
        <ImageryFilters projects={projects} projectLoading={projectLoading} facets={facetsQuery.data} values={filters} onApply={applyFilters} />
        <Segmented<CatalogView>
          value={view}
          onChange={setView}
          options={[
            { value: 'list', label: '列表', icon: <UnorderedListOutlined /> },
            { value: 'grid', label: '图标', icon: <AppstoreOutlined /> }
          ]}
        />
      </div>
      <SectionBar
        title="影像目录"
        detail={`共 ${getListCount(imageryQuery.data)} 景`}
        extra={selectedIds.length ? <Tag color="blue">已选 {selectedIds.length} 景</Tag> : null}
      />
      {imageryQuery.isError ? <Alert type="error" showIcon message={normalizeError(imageryQuery.error)} /> : null}
      {view === 'list' ? (
        <Table
          rowKey="image_id"
          size="middle"
          columns={columns}
          dataSource={records}
          loading={imageryQuery.isLoading}
          tableLayout="fixed"
          rowSelection={{
            preserveSelectedRowKeys: true,
            selectedRowKeys: selectedIds,
            onChange: (keys) => setSelectedIds(keys.map(String))
          }}
          pagination={{
            current: params.page ?? 1,
            pageSize: params.page_size ?? 20,
            total: getListCount(imageryQuery.data),
            showSizeChanger: true,
            onChange: (page, pageSize) => setParams((current) => ({ ...current, page, page_size: pageSize }))
          }}
        />
      ) : (
        <>
          <Spin spinning={imageryQuery.isLoading}>
            <div className="catalog-grid">
              {records.map((record) => {
                const checked = selectedIds.includes(record.image_id);
                return (
                  <Card
                    key={record.image_id}
                    hoverable
                    size="small"
                    className={`catalog-card ${checked ? 'catalog-card-selected' : ''}`}
                    cover={<ImageryThumbnail imagery={record} large />}
                    onClick={() => setDetailId(record.image_id)}
                  >
                    <Checkbox
                      className="catalog-card-check"
                      checked={checked}
                      onClick={(event) => event.stopPropagation()}
                      onChange={(event) => toggleSelected(record.image_id, event.target.checked)}
                      aria-label={`选择 ${imageryName(record)}`}
                    />
                    <Card.Meta
                      title={imageryName(record)}
                      description={
                        <Space direction="vertical" size={2}>
                          <Typography.Text type="secondary">{record.platform ?? record.platform_code ?? '-'} · {record.imaging_mode ?? '-'} · {record.polarization ?? '-'}</Typography.Text>
                          <Typography.Text type="secondary">{record.acquisition_time ? dayjs(record.acquisition_time).format('YYYY-MM-DD HH:mm') : '时间未知'}</Typography.Text>
                        </Space>
                      }
                    />
                  </Card>
                );
              })}
            </div>
          </Spin>
          {!imageryQuery.isLoading && !records.length ? <Empty description="暂无影像" /> : null}
          <Pagination
            align="end"
            current={params.page ?? 1}
            pageSize={params.page_size ?? 20}
            total={getListCount(imageryQuery.data)}
            showSizeChanger
            onChange={(page, pageSize) => setParams((current) => ({ ...current, page, page_size: pageSize }))}
          />
        </>
      )}

      <SelectionActions selectedIds={selectedIds} onClear={() => setSelectedIds([])} />
      <ImageryDetailDrawer
        imageId={detailId}
        onClose={() => setDetailId(undefined)}
        projects={projects}
        currentUser={currentUser}
      />
    </div>
  );
}
