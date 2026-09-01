import { useState } from 'react';
import { App, Button, Form, Input, Modal, Select, Space, Typography } from 'antd';
import { ClearOutlined, FolderAddOutlined, PlusOutlined } from '@ant-design/icons';
import {
  unwrapList,
  useAddDatasetMembers,
  useCreateDataset,
  useDatasets
} from '../../api/hooks';
import { normalizeError } from './utils';

type Dialog = 'add' | 'create';

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
  const pending = createDataset.isPending || addMembers.isPending;

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
      close();
      onClear();
    } catch (error) {
      if (error instanceof Error) message.error(normalizeError(error));
    }
  };

  const title = dialog === 'add' ? '加入数据集' : '创建数据集';

  return (
    <>
      <div className="selection-toolbar" role="toolbar" aria-label="已选影像操作">
        <Typography.Text strong>已选 {selectedIds.length} 景</Typography.Text>
        <Space size={4} wrap>
          <Button icon={<FolderAddOutlined />} onClick={() => setDialog('add')}>加入数据集</Button>
          <Button icon={<PlusOutlined />} onClick={() => setDialog('create')}>创建数据集</Button>
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
        </Form>
      </Modal>
    </>
  );
}
