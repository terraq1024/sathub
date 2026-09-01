import { useEffect, useState } from 'react';
import { Alert, App, Button, Divider, Drawer, Empty, Input, List, Modal, Space, Tag, Typography } from 'antd';
import { ClearOutlined, DeleteOutlined, DownloadOutlined, FileTextOutlined, ReloadOutlined } from '@ant-design/icons';
import { api } from '../../api/client';
import { useAccessTokens, useBasket, useClearBasket, useCreateAccessToken, useCreateDeliveryExport, useDeleteAccessToken, useDeliveryExports, useRemoveBasketItem } from '../../api/hooks';
import { imageryName, normalizeError } from '../imagery/utils';

interface Props { open: boolean; onClose: () => void; }

export function BasketDrawer({ open, onClose }: Props) {
  const { message } = App.useApp();
  const basket = useBasket(open);
  const exportsQuery = useDeliveryExports(open);
  const remove = useRemoveBasketItem();
  const clear = useClearBasket();
  const createExport = useCreateDeliveryExport();
  const [token, setToken] = useState<string>();
  const [snapshotOpen, setSnapshotOpen] = useState(false);
  const [snapshotName, setSnapshotName] = useState('交付版本');
  const items = basket.data?.items ?? [];
  const exports = Array.isArray(exportsQuery.data) ? exportsQuery.data : exportsQuery.data?.results ?? [];
  useEffect(() => { if (open) void exportsQuery.refetch(); }, [open]);
  const exportData = async (format: string) => {
    try { await createExport.mutateAsync(format); message.success('导出任务已创建'); void exportsQuery.refetch(); }
    catch (error) { message.error(normalizeError(error)); }
  };
  const freezeSnapshot = async () => {
    try {
      await api.createDeliverySnapshot({ name: snapshotName.trim() || '交付版本' });
      message.success('交付版本已冻结');
      setSnapshotOpen(false);
      void exportsQuery.refetch();
    } catch (error) { message.error(normalizeError(error)); }
  };
  return <Drawer title={`数据篮${items.length ? `（${items.length}）` : ''}`} width="min(360px, 100vw)" open={open} onClose={onClose}>
    {basket.isError ? <Alert type="error" showIcon message={normalizeError(basket.error)} /> : null}
    <Space direction="vertical" className="full-width" size={10}>
      <Space wrap>
        <Button icon={<FileTextOutlined />} disabled={!items.length} onClick={() => void exportData('manifest')}>Manifest</Button>
        <Button icon={<FileTextOutlined />} disabled={!items.length} onClick={() => void exportData('stac')}>STAC</Button>
        <Button icon={<DownloadOutlined />} disabled={!items.length} onClick={() => void exportData('zip')}>ZIP</Button>
        <Button disabled={!items.length} onClick={() => setSnapshotOpen(true)}>冻结交付版本</Button>
        <Button danger icon={<ClearOutlined />} disabled={!items.length} loading={clear.isPending} onClick={() => clear.mutate(undefined, { onSuccess: () => message.success('数据篮已清空'), onError: (e) => message.error(normalizeError(e)) })}>清空</Button>
      </Space>
      <List size="small" bordered loading={basket.isLoading} locale={{ emptyText: <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="数据篮为空" /> }} dataSource={items} renderItem={(item) => <List.Item actions={[<Button type="text" danger icon={<DeleteOutlined />} title="移除" onClick={() => remove.mutate(item.imagery_id, { onError: (e) => message.error(normalizeError(e)) })} />]}>
        <Typography.Text ellipsis={{ tooltip: true }}>{imageryName(item.imagery ?? { source_name: item.imagery_id } as never)}</Typography.Text>
      </List.Item>} />
      <Divider orientation="left">导出任务</Divider>
      <List size="small" dataSource={exports.slice(0, 8)} locale={{ emptyText: '暂无导出任务' }} renderItem={(job) => <List.Item actions={job.status === 'done' ? [<Button type="link" icon={<DownloadOutlined />} href={job.download_url ?? api.downloadExportUrl(job.id)} target="_blank">下载</Button>] : undefined}>
        <Space direction="vertical" size={0}><Typography.Text>{job.format.toUpperCase()}</Typography.Text><Tag color={job.status === 'done' ? 'success' : job.status === 'failed' ? 'error' : 'processing'}>{job.status === 'done' ? '完成' : job.status === 'failed' ? '失败' : '处理中'}</Tag>{job.status === 'failed' && (job.error || job.error_message) ? <Typography.Text type="danger" ellipsis={{ tooltip: true }}>{job.error || job.error_message}</Typography.Text> : null}</Space>
      </List.Item>} />
      <Divider orientation="left">访问令牌</Divider>
      <TokenSection open={open} token={token} setToken={setToken} />
    </Space>
    <Modal title="冻结交付版本" open={snapshotOpen} onCancel={() => setSnapshotOpen(false)} onOk={() => void freezeSnapshot()} okText="冻结" cancelText="取消">
      <Input value={snapshotName} onChange={(event) => setSnapshotName(event.target.value)} placeholder="版本名称" />
    </Modal>
  </Drawer>;
}

function TokenSection({ open, token, setToken }: { open: boolean; token?: string; setToken: (v?: string) => void }) {
  const { message } = App.useApp(); const query = useAccessTokens(open); const create = useCreateAccessToken(); const remove = useDeleteAccessToken();
  const [name, setName] = useState('QGIS 调用');
  return <Space direction="vertical" className="full-width" size={6}>
    <Space.Compact className="full-width"><Input value={name} onChange={(e) => setName(e.target.value)} placeholder="令牌名称" /><Button type="primary" loading={create.isPending} onClick={() => create.mutate(name, { onSuccess: (data) => { setToken(data.token); message.success('令牌已创建，仅显示一次'); }, onError: (e) => message.error(normalizeError(e)) })}>创建</Button></Space.Compact>
    {token ? <Input.Password readOnly value={token} addonAfter={<Button type="text" icon={<ReloadOutlined />} onClick={() => void navigator.clipboard.writeText(token)}>复制</Button>} /> : null}
    <List size="small" dataSource={query.data ?? []} locale={{ emptyText: '暂无令牌' }} renderItem={(item) => <List.Item actions={[<Button type="text" danger icon={<DeleteOutlined />} title="删除令牌" onClick={() => remove.mutate(item.id, { onError: (e) => message.error(normalizeError(e)) })} />]}><Typography.Text>{item.name}</Typography.Text></List.Item>} />
  </Space>;
}
