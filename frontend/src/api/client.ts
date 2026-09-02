import type {
  CreateDatasetPayload,
  Imagery,
  ImageryBatchPayload,
  ImageryDataset,
  ImageryMapResponse,
  ImagerySearchParams,
  ImageryFacets,
  ImagerySavedSearch,
  IngestionItem,
  IngestionJob,
  ListResponse,
  LoginPayload,
  Project,
  StacItem,
  UpdateDatasetPayload,
  UpdateImageryPayload,
  User
} from './types';

const API_BASE = import.meta.env.VITE_API_BASE_URL ?? '';

class ApiError extends Error {
  status: number;
  details: unknown;

  constructor(status: number, message: string, details: unknown) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.details = details;
  }
}

function getCookie(name: string) {
  const match = document.cookie.split('; ').find((row) => row.startsWith(`${name}=`));
  return match ? decodeURIComponent(match.split('=').slice(1).join('=')) : undefined;
}

async function parseResponse<T>(response: Response): Promise<T> {
  if (response.status === 204) return undefined as T;
  const contentType = response.headers.get('content-type') ?? '';
  const body = contentType.includes('application/json') ? await response.json() : await response.text();
  if (!response.ok) {
    const message =
      typeof body === 'object' && body && 'detail' in body
        ? String((body as { detail: unknown }).detail)
        : response.statusText || '请求失败';
    throw new ApiError(response.status, message, body);
  }
  return body as T;
}

async function request<T>(path: string, init: RequestInit = {}) {
  const csrfToken = getCookie('csrftoken');
  const headers = new Headers(init.headers);
  if (!(init.body instanceof FormData) && init.body !== undefined) headers.set('Content-Type', 'application/json');
  if (csrfToken) headers.set('X-CSRFToken', csrfToken);
  const response = await fetch(`${API_BASE}${path}`, { credentials: 'include', ...init, headers });
  return parseResponse<T>(response);
}

function toQuery(params: object) {
  const search = new URLSearchParams();
  Object.entries(params).forEach(([key, value]) => {
    if (value !== undefined && value !== null && value !== '') {
      search.set(key, Array.isArray(value) ? value.join(',') : String(value));
    }
  });
  const query = search.toString();
  return query ? `?${query}` : '';
}

async function xhrUpload(
  path: string,
  formData: FormData,
  errorLabel: string,
  onProgress?: (percent: number) => void
) {
  const csrfResponse = await request<{ csrfToken?: string }>('/api/auth/csrf');
  return new Promise<IngestionJob>((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open('POST', `${API_BASE}${path}`);
    xhr.withCredentials = true;
    const csrfToken = csrfResponse.csrfToken ?? getCookie('csrftoken');
    if (csrfToken) xhr.setRequestHeader('X-CSRFToken', csrfToken);
    xhr.upload.onprogress = (event) => {
      if (event.lengthComputable && onProgress) onProgress(Math.round((event.loaded / event.total) * 100));
    };
    xhr.onload = () => {
      try {
        const contentType = xhr.getResponseHeader('content-type') ?? '';
        const body = contentType.includes('application/json') ? JSON.parse(xhr.responseText) : xhr.responseText;
        if (xhr.status >= 200 && xhr.status < 300) resolve(body as IngestionJob);
        else reject(new ApiError(xhr.status, xhr.statusText || errorLabel, body));
      } catch (error) {
        reject(error);
      }
    };
    xhr.onerror = () => reject(new ApiError(xhr.status, errorLabel, null));
    xhr.send(formData);
  });
}

export const api = {
  csrf: () => request<{ csrfToken?: string }>('/api/auth/csrf'),
  login: (payload: LoginPayload) => request<User>('/api/auth/login', { method: 'POST', body: JSON.stringify(payload) }),
  logout: () => request<{ detail?: string }>('/api/auth/logout', { method: 'POST' }),
  me: () => request<User>('/api/auth/me'),
  projects: () => request<Project[]>('/api/projects'),
  jobs: () => request<ListResponse<IngestionJob>>('/api/ingestion/jobs'),
  checkArchive: (filename: string) =>
    request<{ exists: boolean; filename: string; image_id?: string | null; source_name?: string | null }>(
      `/api/ingestion/archives/check?filename=${encodeURIComponent(filename)}`
    ),
  jobItems: (jobId: string | number) => request<ListResponse<IngestionItem>>(`/api/ingestion/jobs/${jobId}/items`),
  retryItem: (itemId: string | number) =>
    request<IngestionItem>(`/api/ingestion/items/${itemId}/retry`, { method: 'POST' }),
  createUrlImport: (payload: { project_id?: string | number; urls: string }) =>
    request<IngestionJob>('/api/ingestion/jobs/url-import', { method: 'POST', body: JSON.stringify(payload) }),
  uploadArchive: async (
    payload: { project_id?: string | number; file: File },
    onProgress?: (percent: number) => void
  ) => {
    const archiveCheck = await api.checkArchive(payload.file.name);
    if (archiveCheck.exists) throw new ApiError(409, `压缩包已存在：${archiveCheck.filename}`, archiveCheck);
    const formData = new FormData();
    if (payload.project_id !== undefined) formData.set('project_id', String(payload.project_id));
    formData.set('file', payload.file);
    return xhrUpload('/api/ingestion/jobs/upload-archive', formData, '压缩包上传失败', onProgress);
  },
  uploadFolder: (
    payload: { project_id?: string | number; files: File[]; relativePaths: string[] },
    onProgress?: (percent: number) => void
  ) => {
    const formData = new FormData();
    if (payload.project_id !== undefined) formData.set('project_id', String(payload.project_id));
    payload.files.forEach((file, index) => {
      formData.append('files', file);
      formData.append('relative_paths', payload.relativePaths[index]);
    });
    return xhrUpload('/api/ingestion/jobs/upload-folder', formData, '文件夹上传失败', onProgress);
  },
  imagery: (params: ImagerySearchParams) => request<ListResponse<Imagery>>(`/api/imagery${toQuery(params)}`),
  imageryMap: (params: ImagerySearchParams) => request<ImageryMapResponse>(`/api/imagery/map${toQuery(params)}`),
  imageryFacets: () => request<ImageryFacets>('/api/imagery/facets'),
  savedSearches: () => request<ListResponse<ImagerySavedSearch>>('/api/imagery/saved-searches'),
  createSavedSearch: (payload: Record<string, unknown>) => request<ImagerySavedSearch>('/api/imagery/saved-searches', { method: 'POST', body: JSON.stringify(payload) }),
  updateSavedSearch: (id: string | number, payload: Record<string, unknown>) => request<ImagerySavedSearch>(`/api/imagery/saved-searches/${id}`, { method: 'PATCH', body: JSON.stringify(payload) }),
  deleteSavedSearch: (id: string | number) => request<void>(`/api/imagery/saved-searches/${id}`, { method: 'DELETE' }),
  imageryDetail: (imageId: string) => request<Imagery>(`/api/imagery/${imageId}?include_archived=true`),
  updateImagery: (imageId: string, payload: UpdateImageryPayload) =>
    request<Imagery>(`/api/imagery/${imageId}`, { method: 'PATCH', body: JSON.stringify(payload) }),
  archiveImagery: (imageId: string) => request<void>(`/api/imagery/${imageId}`, { method: 'DELETE' }),
  restoreImagery: (imageId: string) => request<Imagery>(`/api/imagery/${imageId}/restore`, { method: 'POST' }),
  batchImagery: (payload: ImageryBatchPayload) =>
    request<{ updated: number }>('/api/imagery/batch', { method: 'POST', body: JSON.stringify(payload) }),
  imageryStac: (imageId: string) => request<StacItem>(`/api/imagery/${imageId}/stac`),
  imageryAssetUrl: (imageId: string, role: string) => `${API_BASE}/api/imagery/${imageId}/assets/${role}`,
  datasets: (params: { q?: string; page?: number; page_size?: number } = {}) =>
    request<ListResponse<ImageryDataset>>(`/api/imagery/datasets${toQuery(params)}`),
  dataset: (datasetId: string) => request<ImageryDataset>(`/api/imagery/datasets/${datasetId}`),
  createDataset: (payload: CreateDatasetPayload) =>
    request<ImageryDataset>('/api/imagery/datasets', { method: 'POST', body: JSON.stringify(payload) }),
  refreshDataset: (datasetId: string) => request<ImageryDataset>(`/api/imagery/datasets/${datasetId}/refresh`, { method: 'POST' }),
  updateDataset: (datasetId: string, payload: UpdateDatasetPayload) =>
    request<ImageryDataset>(`/api/imagery/datasets/${datasetId}`, { method: 'PATCH', body: JSON.stringify(payload) }),
  archiveDataset: (datasetId: string) => request<void>(`/api/imagery/datasets/${datasetId}`, { method: 'DELETE' }),
  addDatasetMembers: (datasetId: string, imageryIds: string[]) =>
    request<ImageryDataset>(`/api/imagery/datasets/${datasetId}/members`, {
      method: 'POST',
      body: JSON.stringify({ imagery_ids: imageryIds })
    }),
  removeDatasetMember: (datasetId: string, imageId: string) =>
    request<void>(`/api/imagery/datasets/${datasetId}/members/${imageId}`, { method: 'DELETE' }),
  updateDatasetMember: (datasetId: string, imageId: string, enabled: boolean) =>
    request<ImageryDataset>(`/api/imagery/datasets/${datasetId}/members/${imageId}`, {
      method: 'PATCH',
      body: JSON.stringify({ enabled })
    }),
  orderDatasetMembers: (datasetId: string, imageryIds: string[]) =>
    request<ImageryDataset>(`/api/imagery/datasets/${datasetId}/members/order`, {
      method: 'PUT',
      body: JSON.stringify({ imagery_ids: imageryIds })
    }),
  stacApiUrl: () => `${API_BASE}/api/stac/`
};

export { ApiError };
