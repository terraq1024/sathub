import { useState } from 'react';
import { App, Button, Drawer, Form, Grid, Input, Progress, Radio, Segmented, Select, Space, Upload, Typography } from 'antd';
import type { UploadFile, UploadProps } from 'antd';
import { FileZipOutlined, FolderOpenOutlined, LinkOutlined, UploadOutlined } from '@ant-design/icons';
import type { Project } from '../../api/types';
import { useCreateUrlImport, useUploadFolder, useUploadZip } from '../../api/hooks';
import { normalizeError } from '../imagery/utils';

type ImportMode = 'url' | 'archive' | 'folder';
const { Dragger } = Upload;

interface ImportDrawerProps {
  open: boolean;
  onClose: () => void;
  projects: Project[];
  projectLoading?: boolean;
}

function ProjectField({ projects, loading }: { projects: Project[]; loading?: boolean }) {
  return (
    <Select
      allowClear
      loading={loading}
      placeholder="不指定项目"
      options={projects.map((project) => ({ value: project.id, label: project.name }))}
    />
  );
}

export function ImportDrawer({ open, onClose, projects, projectLoading }: ImportDrawerProps) {
  const screens = Grid.useBreakpoint();
  const { message } = App.useApp();
  const [mode, setMode] = useState<ImportMode>('url');
  const [urlForm] = Form.useForm();
  const [uploadForm] = Form.useForm();
  const [folderFiles, setFolderFiles] = useState<UploadFile[]>([]);
  const [progress, setProgress] = useState(0);
  const createUrl = useCreateUrlImport();
  const uploadArchive = useUploadZip();
  const uploadFolder = useUploadFolder();

  const submitUrls = async (values: { project_id?: string | number; urls: string; visibility?: string }) => {
    try {
      const job = await createUrl.mutateAsync(values);
      message.success(`导入任务 ${job.id} 已创建`);
      urlForm.resetFields(['urls']);
    } catch (error) {
      message.error(normalizeError(error));
    }
  };

  const archiveRequest: UploadProps['customRequest'] = async (options) => {
    try {
      const values = await uploadForm.validateFields();
      setProgress(0);
      const job = await uploadArchive.mutateAsync({
        project_id: values.project_id,
        file: options.file as File,
        visibility: values.visibility,
        onProgress: setProgress
      });
      setProgress(100);
      options.onSuccess?.(job);
      message.success(`上传任务 ${job.id} 已创建`);
    } catch (error) {
      options.onError?.(error as Error);
      message.error(normalizeError(error));
    }
  };

  const submitFolder = async () => {
    if (!folderFiles.length) {
      message.warning('请先选择文件夹');
      return;
    }
    try {
      const values = await uploadForm.validateFields();
      const files = folderFiles.map((item) => item.originFileObj as File);
      const relativePaths = files.map(
        (file) => (file as File & { webkitRelativePath?: string }).webkitRelativePath || file.name
      );
      setProgress(0);
      const job = await uploadFolder.mutateAsync({
        project_id: values.project_id,
        files,
        relativePaths,
        visibility: values.visibility,
        onProgress: setProgress
      });
      setProgress(100);
      setFolderFiles([]);
      message.success(`文件夹任务 ${job.id} 已创建`);
    } catch (error) {
      message.error(normalizeError(error));
    }
  };

  const busy = createUrl.isPending || uploadArchive.isPending || uploadFolder.isPending;

  return (
    <Drawer className="import-drawer" title="导入影像" open={open} onClose={onClose} width={screens.md ? 520 : '100%'}>
      <Space direction="vertical" size={20} className="full-width">
        <Segmented<ImportMode>
          block
          value={mode}
          onChange={(value) => { setMode(value); setProgress(0); }}
          options={[
            { value: 'url', label: '链接', icon: <LinkOutlined /> },
            { value: 'archive', label: 'ZIP / 7Z', icon: <FileZipOutlined /> },
            { value: 'folder', label: '文件夹', icon: <FolderOpenOutlined /> }
          ]}
        />
        {mode === 'url' ? (
          <Form form={urlForm} layout="vertical" requiredMark={false} onFinish={submitUrls}>
            <Form.Item name="project_id" label="项目标签（可选）"><ProjectField projects={projects} loading={projectLoading} /></Form.Item>
            <Form.Item name="visibility" label="可见范围" initialValue="private" tooltip="私有数据仅自己和管理员可见；公共数据所有用户可见">
              <Radio.Group optionType="button" buttonStyle="solid">
                <Radio.Button value="private">私有</Radio.Button>
                <Radio.Button value="public">公共</Radio.Button>
              </Radio.Group>
            </Form.Item>
            <Form.Item
              name="urls"
              label="下载链接"
              rules={[{ required: true, message: '请输入至少一个链接' }]}
            >
              <Input.TextArea rows={10} placeholder={'每行一个 HTTP/HTTPS 地址\nhttps://example.com/scene.7z'} />
            </Form.Item>
            <Button type="primary" htmlType="submit" icon={<LinkOutlined />} loading={createUrl.isPending}>创建任务</Button>
          </Form>
        ) : (
          <Form form={uploadForm} layout="vertical" requiredMark={false}>
            <Form.Item name="project_id" label="项目标签（可选）"><ProjectField projects={projects} loading={projectLoading} /></Form.Item>
            <Form.Item name="visibility" label="可见范围" initialValue="private" tooltip="私有数据仅自己和管理员可见；公共数据所有用户可见">
              <Radio.Group optionType="button" buttonStyle="solid">
                <Radio.Button value="private">私有</Radio.Button>
                <Radio.Button value="public">公共</Radio.Button>
              </Radio.Group>
            </Form.Item>
            {mode === 'archive' ? (
              <Dragger
                accept=".zip,.7z,application/zip,application/x-7z-compressed"
                maxCount={1}
                customRequest={archiveRequest}
                beforeUpload={(file) => {
                  if (!/\.(zip|7z)$/i.test(file.name)) {
                    message.error('仅支持 ZIP 或 7Z 文件');
                    return Upload.LIST_IGNORE;
                  }
                  return true;
                }}
              >
                <p className="ant-upload-drag-icon"><FileZipOutlined /></p>
                <p className="ant-upload-text">拖入 ZIP / 7Z，或点击选择</p>
                <p className="ant-upload-hint">上传前会按压缩包文件名检查是否已存在</p>
              </Dragger>
            ) : (
              <Space direction="vertical" size={12} className="full-width">
                <Upload
                  directory
                  multiple
                  fileList={folderFiles}
                  beforeUpload={() => false}
                  onChange={({ fileList }) => setFolderFiles(fileList)}
                  onRemove={(file) => setFolderFiles((current) => current.filter((item) => item.uid !== file.uid))}
                >
                  <Button icon={<FolderOpenOutlined />}>选择已解压文件夹</Button>
                </Upload>
                <Space wrap>
                  <Button type="primary" icon={<UploadOutlined />} disabled={!folderFiles.length} loading={uploadFolder.isPending} onClick={() => void submitFolder()}>
                    上传文件夹
                  </Button>
                  <Typography.Text type="secondary">已选择 {folderFiles.length} 个文件</Typography.Text>
                </Space>
              </Space>
            )}
          </Form>
        )}
        {busy || progress > 0 ? <Progress percent={progress} status={progress === 100 ? 'success' : 'active'} /> : null}
      </Space>
    </Drawer>
  );
}
