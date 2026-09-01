import type {
  AccessToken,
  AuditEvent,
  AdministrativeUnit,
  CatalogEntry,
  CreateDatasetPayload,
  CreateImageryServicePayload,
  CreateProcessingJobPayload,
  DeliveryBasket,
  DeliveryExport,
  DeliverySnapshot,
  Imagery,
  ImageryBatchPayload,
  ImageryDataset,
  ImageryMapResponse,
  ImagerySearchParams,
  ImageryFacets,
  ImagerySavedSearch,
  ImageryService,
  IngestionItem,
  IngestionJob,
  ListResponse,
  LoginPayload,
  ProcessingJob,
  Project,
  MetadataSchema,
  MetadataSchemaField,
  MetadataQualityIssue,
  MetadataOverride,
  MetadataParserRun,
  ImageryGovernance,
  ParserTemplate,
  ParserTemplateVersion,
  StorageEndpoint,
  StorageObject,
  StorageScanJob,
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
  services: () => request<ImageryService[]>('/api/services/'),
  createService: (payload: CreateImageryServicePayload) =>
    request<ImageryService>('/api/services/', { method: 'POST', body: JSON.stringify(payload) }),
  publishService: (serviceKey: string) => request(`/api/services/${serviceKey}/publish`, { method: 'POST' }),
  offlineService: (serviceKey: string) => request(`/api/services/${serviceKey}/offline`, { method: 'POST' }),
  serviceTilejsonUrl: (serviceKey: string) => `${API_BASE}/api/services/${serviceKey}/tilejson`,
  serviceTileUrl: (serviceKey: string) => `${API_BASE}/api/services/${serviceKey}/tiles/{z}/{x}/{y}.png`,
  basket: () => request<DeliveryBasket>('/api/delivery/basket'),
  addBasketItems: (imageryIds: string[]) => request<DeliveryBasket>('/api/delivery/basket', { method: 'POST', body: JSON.stringify({ imagery_ids: imageryIds }) }),
  removeBasketItem: (imageId: string) => request<void>(`/api/delivery/basket/items/${imageId}`, { method: 'DELETE' }),
  clearBasket: () => request<void>('/api/delivery/basket/clear', { method: 'POST' }),
  exports: () => request<ListResponse<DeliveryExport>>('/api/delivery/exports'),
  createExport: (format: string) => request<DeliveryExport>('/api/delivery/exports', { method: 'POST', body: JSON.stringify({ format }) }),
  createDeliverySnapshot: (payload: { name: string; description?: string }) => request<DeliverySnapshot>('/api/delivery/snapshots', { method: 'POST', body: JSON.stringify(payload) }),
  deliverySnapshots: () => request<DeliverySnapshot[]>('/api/delivery/snapshots'),
  createSnapshotExport: (snapshotId: string, format: string) => request<DeliveryExport>(`/api/delivery/snapshots/${snapshotId}`, { method: 'POST', body: JSON.stringify({ format }) }),
  exportDetail: (id: string | number) => request<DeliveryExport>(`/api/delivery/exports/${id}`),
  downloadExportUrl: (id: string | number) => `${API_BASE}/api/delivery/downloads/${id}`,
  accessTokens: () => request<AccessToken[]>('/api/access/tokens'),
  createAccessToken: (name: string) => request<AccessToken>('/api/access/tokens', { method: 'POST', body: JSON.stringify({ name }) }),
  deleteAccessToken: (id: string | number) => request<void>(`/api/access/tokens/${id}`, { method: 'DELETE' }),
  signAssets: (payload: Record<string, unknown>) => request<Record<string, unknown>>('/api/access/assets/sign', { method: 'POST', body: JSON.stringify(payload) }),
  stacApiUrl: () => `${API_BASE}/api/stac/`,
  processingJobs: () => request<ListResponse<ProcessingJob>>('/api/processing/jobs'),
  createProcessingJob: (payload: CreateProcessingJobPayload) =>
    request<ProcessingJob>('/api/processing/jobs', { method: 'POST', body: JSON.stringify(payload) }),
  retryProcessingJob: (jobId: string) =>
    request<ProcessingJob>(`/api/processing/jobs/${jobId}/retry`, { method: 'POST' }),
  processingDownloadUrl: (jobId: string) => `${API_BASE}/api/processing/jobs/${jobId}/download`,
  storageEndpoints: () => request<StorageEndpoint[]>('/api/storage/endpoints'),
  storageEndpoint: (id: string) => request<StorageEndpoint>(`/api/storage/endpoints/${id}`),
  updateStorageEndpoint: (id: string, payload: Record<string, unknown>) => request<StorageEndpoint>(`/api/storage/endpoints/${id}`, { method: 'PATCH', body: JSON.stringify(payload) }),
  deleteStorageEndpoint: (id: string) => request<void>(`/api/storage/endpoints/${id}`, { method: 'DELETE' }),
  storageObjects: (endpointId: string) => request<StorageObject[]>(`/api/storage/objects?endpoint=${encodeURIComponent(endpointId)}`),
  createStorageEndpoint: (payload: Record<string, unknown>) => request<StorageEndpoint>('/api/storage/endpoints', { method: 'POST', body: JSON.stringify(payload) }),
  checkStorageEndpoint: (id: string) => request<StorageScanJob>(`/api/storage/endpoints/${id}/check`, { method: 'POST' }),
  scanStorageEndpoint: (id: string, payload: { mode?: string; prefix?: string } = {}) => request<StorageScanJob>(`/api/storage/endpoints/${id}/scan`, { method: 'POST', body: JSON.stringify(payload) }),
  storageScanJobs: () => request<StorageScanJob[]>('/api/storage/scan-jobs'),
  storageScanJob: (id: string) => request<StorageScanJob>(`/api/storage/scan-jobs/${id}`),
  storageObject: (id: string) => request<StorageObject>(`/api/storage/objects/${id}`),
  ingestStorageObjects: (id: string, payload: { object_ids: string[]; project_id?: string | number }) => request<IngestionJob>(`/api/storage/endpoints/${id}/ingest`, { method: 'POST', body: JSON.stringify(payload) }),
  metadataSchemas: () => request<MetadataSchema[]>('/api/metadata/schemas'),
  createMetadataSchema: (payload: Partial<MetadataSchema> & { fields?: MetadataSchemaField[] }) => request<MetadataSchema>('/api/metadata/schemas', { method: 'POST', body: JSON.stringify(payload) }),
  updateMetadataSchema: (id: number, payload: Partial<MetadataSchema> & { fields?: MetadataSchemaField[] }) => request<MetadataSchema>(`/api/metadata/schemas/${id}`, { method: 'PATCH', body: JSON.stringify(payload) }),
  metadataTemplates: () => request<ParserTemplate[]>('/api/metadata/templates'),
  createMetadataTemplate: (payload: Partial<ParserTemplate>) => request<ParserTemplate>('/api/metadata/templates', { method: 'POST', body: JSON.stringify(payload) }),
  updateMetadataTemplate: (id: number, payload: Partial<ParserTemplate>) => request<ParserTemplate>(`/api/metadata/templates/${id}`, { method: 'PATCH', body: JSON.stringify(payload) }),
  metadataVersions: (templateId: number) => request<ParserTemplateVersion[]>(`/api/metadata/templates/${templateId}/versions`),
  createMetadataVersion: (templateId: number, payload: { version: string; rules: Record<string, unknown> }) => request<ParserTemplateVersion>(`/api/metadata/templates/${templateId}/versions`, { method: 'POST', body: JSON.stringify(payload) }),
  publishMetadataVersion: (versionId: number) => request<ParserTemplateVersion>(`/api/metadata/versions/${versionId}/publish`, { method: 'POST' }),
  metadataDryRun: (payload: { imagery_id: string; parser_version_id?: number }) => request<Record<string, unknown>>('/api/metadata/runs/dry-run', { method: 'POST', body: JSON.stringify(payload) }),
  metadataRuns: () => request<MetadataParserRun[]>('/api/metadata/runs'),
  metadataRun: (id: number) => request<MetadataParserRun>(`/api/metadata/runs/${id}`),
  executeMetadataRun: (payload: { imagery_id: string; parser_version_id?: number }) => request<MetadataParserRun>('/api/metadata/runs/execute', { method: 'POST', body: JSON.stringify(payload) }),
  catalogClassifications: () => request<CatalogEntry[]>('/api/catalog/classifications'),
  createCatalogClassification: (payload: Record<string, unknown>) => request<CatalogEntry>('/api/catalog/classifications', { method: 'POST', body: JSON.stringify(payload) }),
  updateCatalogClassification: (id: string | number, payload: Record<string, unknown>) => request<CatalogEntry>(`/api/catalog/classifications/${id}`, { method: 'PATCH', body: JSON.stringify(payload) }),
  deleteCatalogClassification: (id: string | number) => request<void>(`/api/catalog/classifications/${id}`, { method: 'DELETE' }),
  catalogTags: () => request<CatalogEntry[]>('/api/catalog/tags'),
  createCatalogTag: (payload: Record<string, unknown>) => request<CatalogEntry>('/api/catalog/tags', { method: 'POST', body: JSON.stringify(payload) }),
  updateCatalogTag: (id: string | number, payload: Record<string, unknown>) => request<CatalogEntry>(`/api/catalog/tags/${id}`, { method: 'PATCH', body: JSON.stringify(payload) }),
  deleteCatalogTag: (id: string | number) => request<void>(`/api/catalog/tags/${id}`, { method: 'DELETE' }),
  associateCatalog: (payload: { object_type: 'imagery' | 'dataset'; object_ids: string[]; classification_ids?: Array<string | number>; tag_ids?: Array<string | number>; replace?: boolean }) => request<{ linked: boolean }>('/api/catalog/associations', { method: 'POST', body: JSON.stringify(payload) }),
  imageryGovernance: (imageId: string) => request<ImageryGovernance>(`/api/catalog/imagery/${encodeURIComponent(imageId)}`),
  auditEvents: () => request<AuditEvent[]>('/api/audit/'),
  administrativeUnits: (params: Record<string, string> = {}) => request<AdministrativeUnit[]>(`/api/catalog/administrative-units${toQuery(params)}`),
  administrativeUnitTree: () => request<AdministrativeUnit[]>('/api/catalog/administrative-units/tree'),
  qualityIssues: (params: Record<string, string> = {}) => request<MetadataQualityIssue[]>(`/api/metadata/quality-issues${toQuery(params)}`),
  metadataOverrides: (imageryId?: string) => request<MetadataOverride[]>(`/api/metadata/overrides${imageryId ? `?imagery_id=${encodeURIComponent(imageryId)}` : ''}`),
  createMetadataOverride: (payload: { imagery: string; field_key: string; value: unknown; raw_value?: string; reason?: string; locked?: boolean }) => request<MetadataOverride>('/api/metadata/overrides', { method: 'POST', body: JSON.stringify(payload) })
};

export { ApiError };
