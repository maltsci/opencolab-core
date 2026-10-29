import { useEffect, useState } from 'react';

import { getSourcePreviewUrl } from '../../services/source-preview';

interface SourceThumbnailProps {
  sourceId: string;
  alt: string;
  maxWidth?: number;
  maxHeight?: number;
}

export default function SourceThumbnail({
  sourceId,
  alt,
  maxWidth = 300,
  maxHeight = 400,
}: SourceThumbnailProps) {
  const [url, setUrl] = useState<string | null>(null);
  const [hidden, setHidden] = useState(false);

  useEffect(() => {
    let cancelled = false;
    setUrl(null);
    setHidden(false);

    getSourcePreviewUrl(sourceId, 'thumbnail')
      .then((nextUrl) => {
        if (!cancelled) setUrl(nextUrl);
      })
      .catch(() => {
        if (!cancelled) setHidden(true);
      });

    return () => {
      cancelled = true;
    };
  }, [sourceId]);

  if (!url || hidden) return null;

  return (
    <img
      src={url}
      alt={alt}
      style={{ maxWidth, maxHeight, display: 'block' }}
      onError={() => setHidden(true)}
    />
  );
}
