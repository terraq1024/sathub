export type JobStatus =
  | 'pending'
  | 'validating'
  | 'running'
  | 'scanning'
  | 'parsing'
  | 'storing'
  | 'done'
  | 'failed'
  | 'canceled';

export type ItemStatus =
  | 'pending'
  | 'downloading'
  | 'extracting'
  | 'scanning'
  | 'parsing'
  | 'storing'
  | 'done'
  | 'failed'
  | 'skipped';

export type SourceType = 'url_text' | 'zip_upload' | 'archive_upload' | 'folder_zip' | 'folder_upload';

export interface User {
  id: string | number;
  username: string;
  email?: string;
  first_name?: string;
  last_name?: string;
  is_staff?: boolean;
  is_superuser?: boolean;
}

export interface StorageEndpoint {
  id: string;
  name: string;
  endpoint_type: 'local_directory' | 'nas_smb' | 's3' | 'sftp' | 'ftp' | string;
  mode: 'reference' | 'managed' | string;
  root_uri: string;
  status: string;
  status_message?: string;
  enabled: boolean;
  has_credential?: boolean;
  last_check_at?: string | null;
  last_scan_at?: string | null;
}

export interface StorageScanJob {
  id: string;
  endpoint: string;
  endpoint_name?: string;
  mode: string;
  status: string;
  files_scanned: number;
  scenes_found: number;
  new_count: number;
  changed_count: number;
  missing_count: number;
  error_message?: string;
  prefix?: string;
  unchanged_count?: number;
  started_at?: string | null;
  finished_at?: string | null;
  created_at?: string;
}

export interface StorageObject {
  id: string;
  endpoint: string;
  object_key: string;
  scene_group_key: string;
  scene_role: string;
  size_bytes: number;
  status: string;
  missing_confirmed: boolean;
  modified_at?: string;
  scene_stem?: string;
  source_metadata?: Record<string, unknown>;
}

export interface MetadataSchema {
  id: number;
  code: string;
  name: string;
  version: string;
  status: string;
  description?: string;
  object_type?: string;
  fields?: MetadataSchemaField[];
}

export interface MetadataSchemaField {
  id?: number;
  key: string;
  label?: string;
  data_type: string;
  unit?: string;
  required: boolean;
  searchable: boolean;
  enum_values?: string[];
  validation?: Record<string, unknown>;
  display_order: number;
}

export interface ParserTemplate {
  id: number;
  schema: number;
  schema_code?: string;
  name: string;
  priority: number;
  status: string;
  matcher?: Record<string, unknown>;
  versions?: ParserTemplateVersion[];
}

export interface ParserTemplateVersion {
  id: number;
  template: number;
  template_name?: string;
  version: string;
  rules: Record<string, unknown>;
  status: string;
  created_at?: string;
  published_at?: string | null;
}

export interface CatalogEntry {
  id: number;
  name: string;
  code?: string;
  enabled?: boolean;
  description?: string;
  color?: string;
  parent?: number | null;
}

export interface AuditEvent {
  id: number;
  actor?: User | null;
  action: string;
  object_type: string;
  object_id: string;
  request_id?: string;
  payload: Record<string, unknown>;
  ip?: string | null;
  created_at: string;
}

export interface AdministrativeUnit {
  id: number; level: string; code: string; name: string; parent_id?: number | null;
  geometry?: Record<string, unknown> | null; bbox?: [number, number, number, number] | null;
  source_version?: string; source_file?: string; is_valid?: boolean;
}

export interface MetadataQualityIssue {
  id: number; imagery: string; parser_run?: number | null; field_key: string; code: string;
  severity: string; message: string; details?: Record<string, unknown>; status: string;
  created_at: string; resolved_at?: string | null;
}

export interface MetadataOverride {
  id: number; imagery: string; field_key: string; value: unknown; raw_value?: string;
  reason?: string; locked: boolean; created_by?: User; created_at: string;
}

export interface Project {
  id: string | number;
  name: string;
  code?: string;
  description?: string;
}

export interface LoginPayload {
  username: string;
  password: string;
}

export interface IngestionJob {
  id: string | number;
  project?: string | number;
  project_name?: string | null;
  source_type: SourceType;
  status: JobStatus;
  total_count: number;
  success_count: number;
  failed_count: number;
  skipped_count?: number;
  warning_count?: number;
  created_by?: string | number;
  created_by_username?: string;
  source_payload?: Record<string, unknown>;
  error_message?: string;
  started_at?: string | null;
  finished_at?: string | null;
  created_at: string;
  updated_at?: string;
}

export interface IngestionItem {
  id: string | number;
  job: string | number;
  source: string;
  source_kind: 'url' | 'archive_member' | 'file' | 'folder_file';
  status: ItemStatus;
  raw_path?: string;
  cog_path?: string;
  stac_id?: string;
  image_id?: string;
  scene_key?: string;
  duplicate_of?: string | number | null;
  metadata_status?: string;
  relative_path?: string;
  error_message?: string;
  retry_count: number;
  created_at: string;
  updated_at?: string;
}

export interface ImagerySearchParams {
  project_id?: string | number;
  sensor_type?: 'sar' | 'optical';
  source_vendor?: string;
  platform?: string;
  satellite_name?: string;
  sensor?: string;
  imaging_mode?: string;
  imaging_mode_detail?: string;
  product_level?: string;
  polarization?: string;
  polarizations?: string[];
  metadata_status?: string;
  preview_status?: string;
  cog_status?: string;
  administrative_unit_id?: string | number;
  classification_id?: string | number;
  tag_id?: string | number;
  resolution_min?: number;
  resolution_max?: number;
  time_start?: string;
  time_end?: string;
  bbox?: string;
  geometry?: string;
  q?: string;
  include_archived?: boolean;
  page?: number;
  page_size?: number;
}

export interface ImageryFacetOption {
  value: string;
  label: string;
  count: number;
  platform?: string;
  satellite?: string;
  vendor?: string;
}

export interface ImageryFacets {
  satellites: ImageryFacetOption[];
  vendors: ImageryFacetOption[];
  sensors: ImageryFacetOption[];
  imaging_modes: ImageryFacetOption[];
  product_levels: ImageryFacetOption[];
  polarizations: ImageryFacetOption[];
}

export interface Imagery {
  image_id: string;
  id?: string;
  scene_key?: string;
  stac_id: string;
  collection_id?: string;
  project_id?: string | number;
  project_ids?: Array<string | number>;
  projects?: Project[];
  source_name: string;
  display_name?: string;
  effective_display_name?: string;
  description?: string;
  file_path?: string;
  raw_path?: string;
  cog_path?: string;
  thumbnail_path?: string;
  platform?: string;
  platform_code?: string;
  satellite_name?: string;
  sensor?: string;
  imaging_mode?: string;
  imaging_mode_detail?: string;
  product_level?: string;
  polarization?: string;
  polarizations?: string[];
  resolution_m?: number;
  pixel_spacing_range_m?: number;
  pixel_spacing_azimuth_m?: number;
  acquisition_time?: string;
  acquisition_start?: string;
  acquisition_end?: string;
  center_lon?: number;
  center_lat?: number;
  min_lon?: number;
  min_lat?: number;
  max_lon?: number;
  max_lat?: number;
  bbox?: [number, number, number, number];
  epsg?: number;
  spatial_status?: string;
  metadata_status?: string;
  preview_status?: string;
  cog_status?: string;
  cog_error?: string;
  cog_updated_at?: string | null;
  geometry?: Record<string, unknown>;
  footprint_geojson?: Record<string, unknown>;
  first_uploaded_by?: User;
  can_manage?: boolean;
  is_archived?: boolean;
  archived_at?: string | null;
  archived_by?: User | null;
  status: string;
  created_at?: string;
  updated_at?: string;
}

export interface UpdateImageryPayload {
  display_name?: string;
  description?: string;
  project_ids?: Array<string | number>;
}

export type ImageryBatchAction = 'archive' | 'restore' | 'add_project' | 'remove_project';

export interface ImageryBatchPayload {
  action: ImageryBatchAction;
  imagery_ids: string[];
  project_id?: string | number;
}

export interface PaginatedResponse<T> {
  count: number;
  next?: string | null;
  previous?: string | null;
  results: T[];
}

export type ListResponse<T> = T[] | PaginatedResponse<T>;
export type StacItem = Record<string, unknown>;

export interface ImageryMapFeature {
  type: 'Feature';
  id: string;
  geometry: Record<string, unknown>;
  properties: Imagery & { preview_url?: string };
}

export interface ImageryMapResponse {
  type: 'FeatureCollection';
  count: number;
  features: ImageryMapFeature[];
}

export interface ImagerySavedSearch {
  id: string;
  name: string;
  description?: string;
  query_definition: Record<string, unknown>;
  created_by?: User | string | number;
  created_at?: string;
  updated_at?: string;
}

export type DatasetStatus = 'active' | 'archived';

export interface ImageryDatasetMember {
  id?: string | number;
  imagery_id: string;
  image_id?: string;
  imagery?: Imagery;
  source_name?: string;
  display_name?: string;
  effective_display_name?: string;
  acquisition_time?: string;
  platform_code?: string;
  satellite_name?: string;
  polarization?: string;
  bbox?: [number, number, number, number] | null;
  is_archived?: boolean;
  thumbnail_url?: string | null;
  preview_url?: string | null;
  position: number;
  enabled: boolean;
  added_by?: User;
  added_at?: string;
}

export interface ImageryDataset {
  id: string;
  name: string;
  description?: string;
  status: DatasetStatus;
  revision: number;
  created_by?: User | string | number;
  created_by_username?: string;
  can_manage?: boolean;
  member_count?: number;
  imagery_count?: number;
  enabled_count?: number;
  enabled_member_count?: number;
  bbox?: [number, number, number, number] | null;
  acquisition_start?: string | null;
  acquisition_end?: string | null;
  time_start?: string | null;
  time_end?: string | null;
  service_status?: string | null;
  needs_update?: boolean;
  members?: ImageryDatasetMember[];
  archived_at?: string | null;
  created_at: string;
  updated_at: string;
  membership_type?: 'static' | 'query';
  query_definition?: Record<string, unknown> | null;
  refresh_mode?: 'manual' | 'on_ingestion';
  last_refreshed_at?: string | null;
}

export interface CreateDatasetPayload {
  name: string;
  description?: string;
  imagery_ids?: string[];
  membership_type?: 'static' | 'query';
  query_definition?: Record<string, unknown>;
  refresh_mode?: 'manual' | 'on_ingestion';
}

export interface DeliveryBasketItem { id: string | number; imagery_id: string; imagery?: Imagery; added_at?: string; }
export interface DeliveryBasket { id?: string | number; items: DeliveryBasketItem[]; count?: number; }
export interface DeliverySnapshot { id: string; name: string; description?: string; status: string; imagery_ids: string[]; imagery_count: number; manifest?: Record<string, unknown>; owner?: string | number; owner_username?: string; frozen_at: string; created_at?: string; }
export interface DeliveryExport { id: string | number; format: 'manifest' | 'stac' | 'zip' | string; status: string; imagery_ids?: string[]; snapshot?: string | null; file_size?: number; expires_at?: string | null; download_url?: string; error?: string; error_message?: string; created_at?: string; started_at?: string | null; finished_at?: string | null; }
export interface AccessToken { id: string | number; name: string; token?: string; scopes?: string[]; created_at?: string; last_used_at?: string | null; revoked_at?: string | null; }

export interface MetadataParserRun {
  id: number;
  imagery?: string | null;
  parser_version?: number | null;
  status: 'running' | 'succeeded' | 'failed' | 'dry_run' | string;
  dry_run: boolean;
  input_fingerprint?: string;
  values: Record<string, unknown>;
  provenance: Record<string, unknown>;
  warnings: unknown[];
  errors: unknown[];
  started_at: string;
  finished_at?: string | null;
}

export interface ImageryGovernance {
  imagery_id: string;
  administrative_units: Array<Record<string, unknown>>;
  classifications: Array<Record<string, unknown>>;
  tags: Array<Record<string, unknown>>;
}

export interface UpdateDatasetPayload {
  name?: string;
  description?: string;
}

export type ImageryServiceStatus =
  | 'draft'
  | 'validating'
  | 'preparing'
  | 'publishing'
  | 'online'
  | 'degraded'
  | 'offline'
  | 'failed'
  | 'archived';

export interface ServicePublishJob {
  id: number;
  status: 'pending' | 'running' | 'done' | 'failed';
  current_step?: string;
  progress: number;
  error_message?: string;
  target_revision?: number | null;
  source_snapshot?: string[];
  started_at?: string | null;
  finished_at?: string | null;
  created_at: string;
}

export interface ImageryService {
  id: string;
  name: string;
  service_key: string;
  service_type: 'single_scene' | 'dataset_mosaic' | string;
  source_type?: 'single_scene' | 'dataset_mosaic';
  visibility: 'authenticated' | 'public';
  status: ImageryServiceStatus;
  render_config: Record<string, unknown>;
  error_message?: string;
  imagery_id?: string;
  imagery_name?: string;
  dataset_id?: string;
  dataset_name?: string;
  source_revision?: number | null;
  imagery_count?: number;
  needs_update?: boolean;
  latest_job?: ServicePublishJob | null;
  tilejson_url: string;
  xyz_url?: string;
  ogcapi_url?: string;
  bbox?: [number, number, number, number] | null;
  minzoom?: number;
  maxzoom?: number;
  published_at?: string | null;
  unpublished_at?: string | null;
  created_at: string;
  updated_at: string;
}

export interface CreateImageryServicePayload {
  imagery_id?: string;
  dataset_id?: string;
  name?: string;
  visibility: 'authenticated' | 'public';
  render_config?: Record<string, unknown>;
}

export type ProcessingJobStatus = 'pending' | 'queued' | 'running' | 'succeeded' | 'failed' | 'canceled';
export type ProcessingCropType = 'bbox' | 'polygon';
export type ProcessingOutputFormat = 'geotiff' | 'png';

export interface ProcessingJob {
  id: string;
  imagery_id: string;
  imagery_name?: string;
  imagery?: Imagery | string;
  created_by?: User;
  status: ProcessingJobStatus;
  crop_geometry_type: ProcessingCropType;
  crop_bbox?: [number, number, number, number] | null;
  crop_geometry?: Record<string, unknown> | null;
  bbox?: [number, number, number, number] | null;
  geometry?: Record<string, unknown> | null;
  bands: number[];
  expression?: string;
  output_format: ProcessingOutputFormat;
  output_media_type?: string;
  download_url?: string | null;
  error_message?: string;
  attempts?: number;
  started_at?: string | null;
  finished_at?: string | null;
  created_at: string;
  updated_at?: string;
}

export interface CreateProcessingJobPayload {
  imagery_id: string;
  crop_geometry_type: ProcessingCropType;
  bbox?: [number, number, number, number];
  geometry?: Record<string, unknown>;
  bands?: number[];
  expression?: string;
  output_format: ProcessingOutputFormat;
}
