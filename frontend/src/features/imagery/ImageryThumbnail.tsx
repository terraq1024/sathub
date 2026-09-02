import { useEffect, useMemo, useState } from 'react';
import { Empty, Image } from 'antd';
import { api } from '../../api/client';
import type { Imagery } from '../../api/types';
import { imageryName } from './utils';

export function ImageryThumbnail({ imagery, large = false }: { imagery: Imagery; large?: boolean }) {
  const preferredRole = large && imagery.preview_status === 'ready' ? 'preview' : 'thumbnail';
  const roles = useMemo(
    () => preferredRole === 'preview' ? ['preview', 'thumbnail'] : imagery.preview_status === 'ready' ? ['thumbnail', 'preview'] : ['thumbnail'],
    [imagery.preview_status, preferredRole]
  );
  const [roleIndex, setRoleIndex] = useState(0);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    setRoleIndex(0);
    setFailed(false);
  }, [imagery.image_id, preferredRole]);

  const activeRole = roles[roleIndex] ?? roles[roles.length - 1];

  const handleError = () => {
    if (roleIndex + 1 < roles.length) setRoleIndex((current) => current + 1);
    else setFailed(true);
  };

  return (
    <div className={`imagery-thumbnail ${large ? 'imagery-thumbnail-large' : ''}`}>
      {failed || !activeRole ? (
        <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={false} />
      ) : (
        <Image
          preview={false}
          src={api.imageryAssetUrl(imagery.image_id, activeRole)}
          alt={imageryName(imagery)}
          onError={handleError}
        />
      )}
    </div>
  );
}
