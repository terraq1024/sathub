import type { LatLngBoundsExpression } from 'leaflet';
import type { Imagery, ImageryDatasetMember, User } from '../../api/types';

export function normalizeError(error: unknown) {
  return error instanceof Error ? error.message : '请求失败';
}

export function imageryName(imagery: Imagery) {
  return imagery.display_name?.trim() || imagery.effective_display_name?.trim() || imagery.source_name || imagery.scene_key || imagery.image_id;
}

export function imageryBounds(imagery?: Imagery): LatLngBoundsExpression | undefined {
  if (!imagery) return undefined;
  if (imagery.bbox?.length === 4) {
    const [minLon, minLat, maxLon, maxLat] = imagery.bbox;
    return [[minLat, minLon], [maxLat, maxLon]];
  }
  if (
    imagery.min_lat !== undefined &&
    imagery.min_lon !== undefined &&
    imagery.max_lat !== undefined &&
    imagery.max_lon !== undefined
  ) {
    return [[imagery.min_lat, imagery.min_lon], [imagery.max_lat, imagery.max_lon]];
  }
  return undefined;
}

export function canManageImagery(imagery: Imagery, user?: User) {
  if (imagery.can_manage !== undefined) return imagery.can_manage;
  return Boolean(
    user?.is_staff ||
      user?.is_superuser ||
      (imagery.first_uploaded_by && String(imagery.first_uploaded_by.id) === String(user?.id))
  );
}

export function memberImageId(member: ImageryDatasetMember) {
  return member.imagery_id || member.image_id || member.imagery?.image_id || '';
}

export function memberImagery(member: ImageryDatasetMember): Imagery {
  return member.imagery ?? ({
    image_id: memberImageId(member),
    stac_id: '',
    source_name: member.source_name || memberImageId(member),
    display_name: member.display_name,
    effective_display_name: member.effective_display_name,
    acquisition_time: member.acquisition_time,
    platform_code: member.platform_code,
    satellite_name: member.satellite_name,
    polarization: member.polarization,
    bbox: member.bbox ?? undefined,
    is_archived: member.is_archived,
    preview_status: member.preview_url ? 'ready' : 'missing',
    status: member.is_archived ? 'archived' : 'ready'
  } as Imagery);
}
