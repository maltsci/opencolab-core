import apiClient from './api-client';

interface PreviewTokenResponse {
  token: string;
  expires_in: number;
}

interface CachedPreviewToken {
  token: string;
  expiresAt: number;
}

const previewTokens = new Map<string, CachedPreviewToken>();

export async function getSourcePreviewToken(sourceId: string): Promise<string> {
  const cached = previewTokens.get(sourceId);
  const now = Date.now();
  if (cached && cached.expiresAt > now + 10_000) {
    return cached.token;
  }

  const { data } = await apiClient.get<PreviewTokenResponse>(
    `/sources/${sourceId}/preview-token`,
  );
  const ttlMs = Math.max(30, data.expires_in) * 1000;
  previewTokens.set(sourceId, {
    token: data.token,
    expiresAt: now + ttlMs,
  });
  return data.token;
}

export async function getSourcePreviewUrl(
  sourceId: string,
  kind: 'file' | 'text' | 'thumbnail',
  pageNumber?: number,
): Promise<string> {
  const token = await getSourcePreviewToken(sourceId);
  const pageQuery = pageNumber ? `&page=${pageNumber}` : '';
  return `${apiClient.defaults.baseURL}/sources/${sourceId}/${kind}?token=${encodeURIComponent(token)}${pageQuery}`;
}
