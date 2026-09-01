import { useState } from 'react';
import { App, Button, Form, Input, Modal, Select, Space, Typography } from 'antd';
import { ApiOutlined, ClearOutlined, FolderAddOutlined, PlusOutlined } from '@ant-design/icons';
import {
  unwrapList,
  useAddDatasetMembers,
  useCreateDataset,
  useCreateService,
  useDatasets,
  usePublishService
} from '../../api/hooks';
import { useAddBasketItems } from '../../api/hooks';
import { normalizeError } from './utils';

type Dialog = 'add' | 'create' | 'publish';

interface SelectionActionsProps {
  selectedIds: string[];
  onClear: () => void;
}

export function SelectionActions({ selectedIds, onClear }: SelectionActionsProps) {
  const { message } = App.useApp();
  const [dialog, setDialog] = useState<Dialog>();
  const [form] = Form.useForm();
  const datasetsQuery = useDatasets({ page_size: 200 }, Boolean(selectedIds.length));
  const createDataset = useCreateDataset();
  const addMembers = useAddDatasetMembers();
  const createService = useCreateService();
  const publishService = usePublishService();
  const addBasket = useAddBasketItems();
  const pending = createDataset.isPending || addMembers.isPending || createService.isPending || publishService.isPending || addBasket.isPending;

  if (!selectedIds.length) return null;

  const close = () => {
    setDialog(undefined);
    form.resetFields();
  };

  const submit = async () => {
    try {
      const values = await form.validateFields();
      if (dialog === 'add') {
        await addMembers.mutateAsync({ datasetId: values.dataset_id, imageryIds: selectedIds });
        message.success(`已将 ${selectedIds.length} 景影像加入数据集`);
      }
      if (dialog === 'create') {
        let queryDefinition: Record<string, unknown> | undefined;
        if (values.membership_type === 'query') {
          try {
            queryDefinition = JSON.parse(values.query_definition);
          } catch {
            throw new Error('筛选定义必须是合法的 JSON 对象');
          }
          if (!queryDefinition || typeof queryDefinition !== 'object' || Array.isArray(queryDefinition)) {
            throw new Error('筛选定义必须是 JSON 对象，例如 {"q":"AS05"}');
          }
        }
        const payload = queryDefinition
          ? { name: values.name, description: values.description, membership_type: 'query' as const, query_definition: queryDefinition, refresh_mode: values.refresh_mode }
          : { name: values.name, description: values.description, imagery_ids: selectedIds, membership_type: 'static' as const };
        await createDataset.mutateAsync(payload);
        message.success('数据集已创建');
      }
      if (dialog === 'publish') {
        let source: { imagery_id?: string; dataset_id?: string };
        if (selectedIds.length === 1) {
          source = { imagery_id: selectedIds[0] };
        } else {
          const dataset = await createDataset.mutateAsync({
            name: values.dataset_name || `${values.name} 数据集`,
            description: '由多景服务发布自动创建',
            imagery_ids: selectedIds
          });
          source = { dataset_id: dataset.id };
        }
        const service = await createService.mutateAsync({
          ...source,
          name: values.name,
          visibility: values.visibility
        });
        await publishService.mutateAsync(service.service_key);
        message.success('服务发布任务已创建');
      }
      close();
      onClear();
    } catch (error) {
      if (error instanceof Error) message.error(normalizeError(error));
    }
  };

  const title = dialog === 'add' ? '加入数据集' : dialog === 'create' ? '创建数据集' : '发布服务';

  return (
    <>
      <div className="selection-toolbar" role="toolbar" aria-label="已选影像操作">
        <Typography.Text strong>已选 {selectedIds.length} 景</Typography.Text>
        <Space size={4} wrap>
          <Button icon={<FolderAddOutlined />} onClick={() => setDialog('add')}>加入数据集</Button>
          <Button icon={<FolderAddOutlined />} loading={addBasket.isPending} onClick={() => addBasket.mutate(selectedIds, { onSuccess: () => { message.success('已加入数据篮'); onClear(); }, onError: (e) => message.error(normalizeError(e)) })}>加入数据篮</Button>
          <Button icon={<PlusOutlined />} onClick={() => setDialog('create')}>创建数据集</Button>
          <Button type="primary" icon={<ApiOutlined />} onClick={() => setDialog('publish')}>发布服务</Button>
          <Button icon={<ClearOutlined />} onClick={onClear}>清空</Button>
        </Space>
      </div>
      <Modal title={title} open={Boolean(dialog)} onCancel={close} onOk={() => void submit()} confirmLoading={pending} destroyOnHidden>
        <Form form={form} layout="vertical" requiredMark={false} preserve={false}>
          {dialog === 'add' ? (
            <Form.Item name="dataset_id" label="目标数据集" rules={[{ required: true, message: '请选择数据集' }]}>
              <Select
                showSearch
                loading={datasetsQuery.isLoading}
                optionFilterProp="label"
                options={unwrapList(datasetsQuery.data).map((dataset) => ({ value: dataset.id, label: dataset.name }))}
              />
            </Form.Item>
          ) : null}
          {dialog === 'create' ? (
            <>
              <Form.Item name="name" label="数据集名称" rules={[{ required: true, message: '请输入数据集名称' }]}>
                <Input maxLength={255} />
              </Form.Item>
              <Form.Item name="description" label="备注"><Input.TextArea rows={3} maxLength={1000} showCount /></Form.Item>
              <Form.Item name="membership_type" label="成员类型" initialValue="static"><Select options={[{ value: 'static', label: '静态成员' }, { value: 'query', label: '动态筛选' }]} /></Form.Item>
              <Form.Item noStyle shouldUpdate={(prev, next) => prev.membership_type !== next.membership_type}>{({ getFieldValue }) => getFieldValue('membership_type') === 'query' ? <><Form.Item name="query_definition" label="筛选定义（JSON）" rules={[{ required: true, message: '请输入筛选定义' }]}><Input.TextArea rows={3} placeholder='{"q":"AS05"}' /></Form.Item><Form.Item name="refresh_mode" label="刷新模式" initialValue="manual"><Select options={[{ value: 'manual', label: '手动刷新' }, { value: 'on_ingestion', label: '入库自动刷新' }]} /></Form.Item></> : null}</Form.Item>
            </>
          ) : null}
          {dialog === 'publish' ? (
            <>
              <Form.Item name="name" label="服务名称" rules={[{ required: true, message: '请输入服务名称' }]}>
                <Input maxLength={255} />
              </Form.Item>
              {selectedIds.length > 1 ? (
                <Form.Item name="dataset_name" label="自动创建的数据集名称">
                  <Input maxLength={255} placeholder="默认使用服务名称" />
                </Form.Item>
              ) : null}
              <Form.Item name="visibility" label="访问范围" initialValue="authenticated">
                <Select options={[{ value: 'authenticated', label: '登录用户' }, { value: 'public', label: '公开' }]} />
              </Form.Item>
            </>
          ) : null}
        </Form>
      </Modal>
    </>
  );
}
