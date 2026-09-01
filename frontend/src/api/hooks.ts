import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { api } from './client';
import type {
  CreateDatasetPayload,
  CreateImageryServicePayload,
  CreateProcessingJobPayload,
  DeliveryExport,
  ImageryBatchPayload,
  ImagerySearchParams,
  ImageryService,
  IngestionJob,
  ListResponse,
  ProcessingJob,
  UpdateDatasetPayload,
  UpdateImageryPayload
} from './types';

export function unwrapList<T>(response?: ListResponse<T>) {
  if (!response) return [];
  return Array.isArray(response) ? response : response.results;
}

export function getListCount<T>(response?: ListResponse<T>) {
  if (!response) return 0;
  return Array.isArray(response) ? response.length : response.count;
}

export function useMe() {
  return useQuery({ queryKey: ['auth', 'me'], queryFn: api.me, retry: false });
}

export function useLogin() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: api.login,
    onSuccess: (user) => {
      queryClient.setQueryData(['auth', 'me'], user);
      void queryClient.invalidateQueries({ queryKey: ['projects'] });
    }
  });
}

export function useLogout() {
  const queryClient = useQueryClient();
  return useMutation({ mutationFn: api.logout, onSuccess: () => queryClient.clear() });
}

export function useProjects(enabled = true) {
  return useQuery({ queryKey: ['projects'], queryFn: api.projects, enabled });
}

export function useJobs(enabled = true) {
  return useQuery({
    queryKey: ['jobs'],
    queryFn: api.jobs,
    enabled,
    refetchInterval: (query) => {
      const jobs = unwrapList(query.state.data as ListResponse<IngestionJob> | undefined);
      return jobs.some((job) => ['pending', 'validating', 'running', 'scanning', 'parsing', 'storing'].includes(job.status))
        ? 5000
        : false;
    }
  });
}

export function useJobItems(jobId?: string | number) {
  return useQuery({
    queryKey: ['jobs', jobId, 'items'],
    queryFn: () => api.jobItems(jobId!),
    enabled: Boolean(jobId)
  });
}

function useIngestionMutation<TPayload>(mutationFn: (payload: TPayload) => Promise<IngestionJob>) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn,
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ['jobs'] })
  });
}

export function useCreateUrlImport() {
  return useIngestionMutation(api.createUrlImport);
}

export function useUploadZip() {
  return useIngestionMutation(
    ({ onProgress, ...payload }: { project_id?: string | number; file: File; onProgress?: (percent: number) => void }) =>
      api.uploadArchive(payload, onProgress)
  );
}

export function useUploadFolder() {
  return useIngestionMutation(
    ({ onProgress, ...payload }: { project_id?: string | number; files: File[]; relativePaths: string[]; onProgress?: (percent: number) => void }) =>
      api.uploadFolder(payload, onProgress)
  );
}

export function useRetryItem() {
  const queryClient = useQueryClient();
  return useMutation({ mutationFn: api.retryItem, onSuccess: () => void queryClient.invalidateQueries({ queryKey: ['jobs'] }) });
}

export function useImagery(params: ImagerySearchParams, enabled = true) {
  return useQuery({ queryKey: ['imagery', 'list', params], queryFn: () => api.imagery(params), enabled });
}

export function useImageryMap(params: ImagerySearchParams, enabled = true) {
  return useQuery({ queryKey: ['imagery', 'map', params], queryFn: () => api.imageryMap(params), enabled });
}

export function useImageryFacets(enabled = true) {
  return useQuery({ queryKey: ['imagery', 'facets'], queryFn: api.imageryFacets, enabled, staleTime: 30_000 });
}

export function useBasket(enabled = true) { return useQuery({ queryKey: ['delivery', 'basket'], queryFn: api.basket, enabled }); }
export function useAddBasketItems() { const qc = useQueryClient(); return useMutation({ mutationFn: api.addBasketItems, onSuccess: () => void qc.invalidateQueries({ queryKey: ['delivery', 'basket'] }) }); }
export function useRemoveBasketItem() { const qc = useQueryClient(); return useMutation({ mutationFn: api.removeBasketItem, onSuccess: () => void qc.invalidateQueries({ queryKey: ['delivery', 'basket'] }) }); }
export function useClearBasket() { const qc = useQueryClient(); return useMutation({ mutationFn: api.clearBasket, onSuccess: () => void qc.invalidateQueries({ queryKey: ['delivery', 'basket'] }) }); }
export function useDeliveryExports(enabled = true) {
  return useQuery({
    queryKey: ['delivery', 'exports'],
    queryFn: api.exports,
    enabled,
    refetchInterval: (query) => {
      const jobs = unwrapList(query.state.data as ListResponse<DeliveryExport> | undefined);
      return jobs.some((job) => ['pending', 'running'].includes(job.status)) ? 3000 : false;
    }
  });
}
export function useCreateDeliveryExport() { const qc = useQueryClient(); return useMutation({ mutationFn: api.createExport, onSuccess: () => void qc.invalidateQueries({ queryKey: ['delivery', 'exports'] }) }); }
export function useAccessTokens(enabled = true) { return useQuery({ queryKey: ['access', 'tokens'], queryFn: api.accessTokens, enabled }); }
export function useCreateAccessToken() { const qc = useQueryClient(); return useMutation({ mutationFn: api.createAccessToken, onSuccess: () => void qc.invalidateQueries({ queryKey: ['access', 'tokens'] }) }); }
export function useDeleteAccessToken() { const qc = useQueryClient(); return useMutation({ mutationFn: api.deleteAccessToken, onSuccess: () => void qc.invalidateQueries({ queryKey: ['access', 'tokens'] }) }); }

export function useImageryDetail(imageId?: string) {
  return useQuery({
    queryKey: ['imagery', 'detail', imageId],
    queryFn: () => api.imageryDetail(imageId!),
    enabled: Boolean(imageId)
  });
}

function invalidateImagery(queryClient: ReturnType<typeof useQueryClient>, imageId?: string) {
  void queryClient.invalidateQueries({ queryKey: ['imagery'] });
  void queryClient.invalidateQueries({ queryKey: ['datasets'] });
  if (imageId) void queryClient.invalidateQueries({ queryKey: ['imagery', 'detail', imageId] });
}

export function useUpdateImagery() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ imageId, payload }: { imageId: string; payload: UpdateImageryPayload }) =>
      api.updateImagery(imageId, payload),
    onSuccess: (_, variables) => invalidateImagery(queryClient, variables.imageId)
  });
}

export function useArchiveImagery() {
  const queryClient = useQueryClient();
  return useMutation({ mutationFn: api.archiveImagery, onSuccess: (_, imageId) => invalidateImagery(queryClient, imageId) });
}

export function useRestoreImagery() {
  const queryClient = useQueryClient();
  return useMutation({ mutationFn: api.restoreImagery, onSuccess: (_, imageId) => invalidateImagery(queryClient, imageId) });
}

export function useBatchImagery() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: ImageryBatchPayload) => api.batchImagery(payload),
    onSuccess: () => invalidateImagery(queryClient)
  });
}

export function useDatasets(params: { q?: string; page?: number; page_size?: number } = {}, enabled = true) {
  return useQuery({ queryKey: ['datasets', 'list', params], queryFn: () => api.datasets(params), enabled });
}

export function useDataset(datasetId?: string) {
  return useQuery({
    queryKey: ['datasets', 'detail', datasetId],
    queryFn: () => api.dataset(datasetId!),
    enabled: Boolean(datasetId)
  });
}

function invalidateDatasets(queryClient: ReturnType<typeof useQueryClient>, datasetId?: string) {
  void queryClient.invalidateQueries({ queryKey: ['datasets'] });
  void queryClient.invalidateQueries({ queryKey: ['services'] });
  if (datasetId) void queryClient.invalidateQueries({ queryKey: ['datasets', 'detail', datasetId] });
}

export function useCreateDataset() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: CreateDatasetPayload) => api.createDataset(payload),
    onSuccess: () => invalidateDatasets(queryClient)
  });
}
export function useRefreshDataset() { const queryClient = useQueryClient(); return useMutation({ mutationFn: api.refreshDataset, onSuccess: (_, id) => invalidateDatasets(queryClient, id) }); }

export function useUpdateDataset() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ datasetId, payload }: { datasetId: string; payload: UpdateDatasetPayload }) =>
      api.updateDataset(datasetId, payload),
    onSuccess: (_, variables) => invalidateDatasets(queryClient, variables.datasetId)
  });
}

export function useArchiveDataset() {
  const queryClient = useQueryClient();
  return useMutation({ mutationFn: api.archiveDataset, onSuccess: (_, id) => invalidateDatasets(queryClient, id) });
}

export function useAddDatasetMembers() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ datasetId, imageryIds }: { datasetId: string; imageryIds: string[] }) =>
      api.addDatasetMembers(datasetId, imageryIds),
    onSuccess: (_, variables) => invalidateDatasets(queryClient, variables.datasetId)
  });
}

export function useRemoveDatasetMember() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ datasetId, imageId }: { datasetId: string; imageId: string }) =>
      api.removeDatasetMember(datasetId, imageId),
    onSuccess: (_, variables) => invalidateDatasets(queryClient, variables.datasetId)
  });
}

export function useUpdateDatasetMember() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ datasetId, imageId, enabled }: { datasetId: string; imageId: string; enabled: boolean }) =>
      api.updateDatasetMember(datasetId, imageId, enabled),
    onSuccess: (_, variables) => invalidateDatasets(queryClient, variables.datasetId)
  });
}

export function useOrderDatasetMembers() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ datasetId, imageryIds }: { datasetId: string; imageryIds: string[] }) =>
      api.orderDatasetMembers(datasetId, imageryIds),
    onSuccess: (_, variables) => invalidateDatasets(queryClient, variables.datasetId)
  });
}

export function useServices(enabled = true) {
  return useQuery({
    queryKey: ['services'],
    queryFn: api.services,
    enabled,
    refetchInterval: (query) => {
      const services = query.state.data as ImageryService[] | undefined;
      return services?.some(
        (service) =>
          ['validating', 'preparing', 'publishing'].includes(service.status) ||
          ['pending', 'running'].includes(service.latest_job?.status ?? '')
      )
        ? 3000
        : false;
    }
  });
}

export function useCreateService() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: CreateImageryServicePayload) => api.createService(payload),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ['services'] })
  });
}

export function usePublishService() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: api.publishService,
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ['services'] })
  });
}

export function useOfflineService() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: api.offlineService,
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ['services'] })
  });
}

export function useProcessingJobs(enabled = true) {
  return useQuery({
    queryKey: ['processing', 'jobs'],
    queryFn: api.processingJobs,
    enabled,
    refetchInterval: (query) => {
      const jobs = unwrapList(query.state.data as ListResponse<ProcessingJob> | undefined);
      return jobs.some((job) => ['pending', 'queued', 'running'].includes(job.status)) ? 2500 : false;
    }
  });
}

export function useCreateProcessingJob() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: CreateProcessingJobPayload) => api.createProcessingJob(payload),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ['processing', 'jobs'] })
  });
}

export function useRetryProcessingJob() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: api.retryProcessingJob,
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ['processing', 'jobs'] })
  });
}
