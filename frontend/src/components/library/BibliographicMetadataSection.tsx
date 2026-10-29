import { LockOutlined, SearchOutlined } from '@ant-design/icons';
import { Button, Card, Descriptions, List, Space, Tag, Tooltip, Typography, message } from 'antd';
import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';

import apiClient from '../../services/api-client';
import type {
  AppliedBibliographicMetadata,
  BibliographicMetadata,
  BibliographicProviderCandidate,
  ResearchAsset,
} from '../../types/research-asset';

interface BibliographicMetadataSectionProps {
  asset: ResearchAsset;
  onAssetUpdated?: (asset: ResearchAsset) => void;
  variant?: 'overview' | 'management';
}

function candidateIdentifiers(candidate: BibliographicProviderCandidate): string[] {
  return [
    candidate.doi ? `DOI ${candidate.doi}` : null,
    candidate.pmid ? `PMID ${candidate.pmid}` : null,
    candidate.pmcid || null,
    candidate.arxiv_id ? `arXiv ${candidate.arxiv_id}` : null,
  ].filter((value): value is string => Boolean(value));
}

function appliedIdentifiers(metadata: AppliedBibliographicMetadata): string[] {
  return [
    metadata.doi ? `DOI ${metadata.doi}` : null,
    metadata.pmid ? `PMID ${metadata.pmid}` : null,
    metadata.pmcid || null,
    metadata.arxiv_id ? `arXiv ${metadata.arxiv_id}` : null,
  ].filter((value): value is string => Boolean(value));
}

function isAppliedCandidate(
  candidate: BibliographicProviderCandidate,
  applied: AppliedBibliographicMetadata,
  displayTitle: string,
): boolean {
  if (candidate.provider !== applied.source) return false;
  const candidateValues = [
    candidate.doi,
    candidate.pmid,
    candidate.pmcid,
    candidate.arxiv_id,
  ].filter(Boolean);
  const appliedValues = [
    applied.doi,
    applied.pmid,
    applied.pmcid,
    applied.arxiv_id,
  ].filter(Boolean);
  if (candidateValues.some((value) => appliedValues.includes(value))) return true;
  return candidate.title.trim().toLocaleLowerCase() === displayTitle.trim().toLocaleLowerCase();
}

function safeExternalUrl(value: string | undefined): string | null {
  if (!value) return null;
  try {
    const url = new URL(value);
    return url.protocol === 'https:' || url.protocol === 'http:' ? url.toString() : null;
  } catch {
    return null;
  }
}

export default function BibliographicMetadataSection({
  asset,
  onAssetUpdated,
  variant = 'overview',
}: BibliographicMetadataSectionProps) {
  const { t } = useTranslation();
  const [metadata, setMetadata] = useState<BibliographicMetadata | null>(null);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const managementOnly = variant === 'management';
  const appliedMetadata = metadata?.catalog_metadata.bibliographic;
  const verifiedMetadata = appliedMetadata?.verification_status === 'verified'
    ? appliedMetadata
    : null;
  const verifiedRecordUrl = safeExternalUrl(verifiedMetadata?.record_url);
  const verifiedIdentifiers = verifiedMetadata ? appliedIdentifiers(verifiedMetadata) : [];
  const hasCurrentMetadata = Boolean(
    metadata?.keywords.length
    || verifiedMetadata?.authors?.length
    || verifiedMetadata?.container_title
    || verifiedMetadata?.published_date
    || verifiedIdentifiers.length
    || verifiedRecordUrl,
  );
  const providerCandidates = metadata?.provider_candidates
    .map((candidate, index) => ({ candidate, index }))
    .filter(({ candidate }) => (
      !verifiedMetadata || !isAppliedCandidate(candidate, verifiedMetadata, metadata.title)
    )) ?? [];
  const hasLookupIdentifier = metadata?.identifier_candidates.some(
    (candidate) => candidate.eligible_for_lookup,
  ) ?? false;

  const loadMetadata = async () => {
    setLoading(true);
    try {
      const { data } = await apiClient.get<BibliographicMetadata>(
        `/research-assets/${asset.id}/bibliographic-metadata`,
      );
      setMetadata(data);
    } catch {
      setMetadata(null);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void loadMetadata();
  }, [asset.id]);

  const refreshAsset = async () => {
    const { data } = await apiClient.get<ResearchAsset>(`/research-assets/${asset.id}`);
    onAssetUpdated?.(data);
    await loadMetadata();
  };

  const runAction = async (path: string, successKey: string) => {
    setSaving(true);
    try {
      await apiClient.post(`/research-assets/${asset.id}/bibliographic-metadata/${path}`);
      message.success(t(successKey));
      await refreshAsset();
    } catch {
      message.error(t('library.bibliographic.actionFailed'));
    } finally {
      setSaving(false);
    }
  };

  const applyCandidate = async (candidateIndex: number) => {
    setSaving(true);
    try {
      await apiClient.post(
        `/research-assets/${asset.id}/bibliographic-metadata/apply`,
        { candidate_index: candidateIndex },
      );
      message.success(t('library.bibliographic.candidateApplied'));
      await refreshAsset();
    } catch {
      message.error(t('library.bibliographic.actionFailed'));
    } finally {
      setSaving(false);
    }
  };

  return (
    <Card
      size="small"
      loading={loading}
      title={t('library.bibliographic.title')}
      style={{ marginTop: 16 }}
    >
      {metadata ? (
        <Space orientation="vertical" size="middle" style={{ width: '100%' }}>
          {hasCurrentMetadata || (managementOnly && metadata.can_update) ? (
            <Descriptions column={1} size="small">
              {verifiedMetadata?.authors?.length ? (
                <Descriptions.Item label={t('library.bibliographic.authors')}>
                  {verifiedMetadata.authors.join(', ')}
                </Descriptions.Item>
              ) : null}
              {verifiedMetadata?.container_title ? (
                <Descriptions.Item label={t('library.bibliographic.containerTitle')}>
                  {verifiedMetadata.container_title}
                </Descriptions.Item>
              ) : null}
              {verifiedMetadata?.published_date ? (
                <Descriptions.Item label={t('library.bibliographic.publishedDate')}>
                  {verifiedMetadata.published_date}
                </Descriptions.Item>
              ) : null}
              {verifiedIdentifiers.length > 0 ? (
                <Descriptions.Item label={t('library.bibliographic.verifiedIdentifiers')}>
                  <Space size={[4, 4]} wrap>
                    {verifiedIdentifiers.map((identifier) => (
                      <Tag key={identifier} color="blue">{identifier}</Tag>
                    ))}
                  </Space>
                </Descriptions.Item>
              ) : null}
              <Descriptions.Item label={t('library.bibliographic.keywords')}>
                <Space size={[4, 4]} wrap>
                  {metadata.keywords.length > 0 ? metadata.keywords.map((keyword) => (
                    <Tag key={keyword}>{keyword}</Tag>
                  )) : (
                    <Typography.Text type="secondary">
                      {t('library.bibliographic.keywordsEmpty')}
                    </Typography.Text>
                  )}
                  {managementOnly && metadata.can_update ? (
                    <Button
                      type="link"
                      size="small"
                      loading={saving}
                      onClick={() => void runAction(
                        'reextract',
                        'library.bibliographic.keywordsExtracted',
                      )}
                    >
                      {t('library.bibliographic.extractKeywords')}
                    </Button>
                  ) : null}
                </Space>
              </Descriptions.Item>
              {verifiedRecordUrl || (managementOnly && hasLookupIdentifier) ? (
                <Descriptions.Item label={t('library.bibliographic.recordUrl')}>
                  <Space size={[4, 4]} wrap>
                    {verifiedRecordUrl ? (
                      <Typography.Link href={verifiedRecordUrl} target="_blank" rel="noreferrer">
                        {t('library.bibliographic.openRecord')}
                      </Typography.Link>
                    ) : (
                      <Typography.Text type="secondary">-</Typography.Text>
                    )}
                    {managementOnly && hasLookupIdentifier ? (
                      <Tooltip title={t('library.bibliographic.retryHint')}>
                        <Button
                          type="text"
                          size="small"
                          aria-label={t('library.bibliographic.retry')}
                          icon={<SearchOutlined />}
                          loading={saving}
                          onClick={() => void runAction('retry', 'library.bibliographic.retryQueued')}
                        />
                      </Tooltip>
                    ) : null}
                  </Space>
                </Descriptions.Item>
              ) : null}
            </Descriptions>
          ) : (
            <Typography.Text type="secondary">
              {t('library.bibliographic.unavailable')}
            </Typography.Text>
          )}

          {!managementOnly ? (
            <Descriptions column={1} size="small">
            <Descriptions.Item label={t('library.bibliographic.displayTitle')}>
              <Space size={4} wrap>
                <Typography.Text>{metadata.title}</Typography.Text>
                {metadata.title_locked ? <LockOutlined /> : null}
              </Space>
            </Descriptions.Item>
            <Descriptions.Item label={t('library.bibliographic.originalFilename')}>
              {metadata.original_filename || '-'}
            </Descriptions.Item>
            <Descriptions.Item label={t('library.bibliographic.status')}>
              <Tag color={metadata.metadata_status === 'resolved' ? 'success' : undefined}>
                {t(
                  `library.bibliographic.status.${metadata.metadata_status}`,
                  metadata.metadata_status,
                )}
              </Tag>
            </Descriptions.Item>
            <Descriptions.Item label={t('library.bibliographic.keywords')}>
              <Space orientation="vertical" size={4}>
                {metadata.keywords.length > 0 ? (
                  <Space size={[4, 4]} wrap>
                    {metadata.keywords.map((keyword) => (
                      <Tag key={keyword}>{keyword}</Tag>
                    ))}
                  </Space>
                ) : (
                  <Typography.Text type="secondary">
                    {t('library.bibliographic.keywordsEmpty')}
                  </Typography.Text>
                )}
              </Space>
            </Descriptions.Item>
            </Descriptions>
          ) : null}

          {!managementOnly && metadata.identifier_candidates.length > 0 ? (
            <div>
              <Typography.Text strong>
                {t('library.bibliographic.identifiers')}
              </Typography.Text>
              <div style={{ marginTop: 8 }}>
                {metadata.identifier_candidates.map((candidate) => (
                  <Tag key={`${candidate.identifier_type}:${candidate.value}`}>
                    {candidate.identifier_type.toUpperCase()} {candidate.value}
                  </Tag>
                ))}
              </div>
            </div>
          ) : null}

          {managementOnly && providerCandidates.length > 0 ? (
            <List
              size="small"
              header={(
                <Typography.Text strong>
                  {t('library.bibliographic.candidates')}
                </Typography.Text>
              )}
              dataSource={providerCandidates}
              renderItem={({ candidate, index }) => {
                return (
                  <List.Item
                    actions={metadata.can_update ? [
                      <Button
                        key="apply"
                        size="small"
                        type="link"
                        loading={saving}
                        onClick={() => void applyCandidate(index)}
                      >
                        {t('library.bibliographic.applyCandidate')}
                      </Button>,
                    ] : undefined}
                  >
                    <List.Item.Meta
                      title={candidate.title}
                      description={[
                        candidate.authors?.join(', '),
                        candidate.container_title,
                        candidate.published_date,
                        candidateIdentifiers(candidate).join(' · '),
                      ].filter(Boolean).join(' · ')}
                    />
                  </List.Item>
                );
              }}
            />
          ) : null}

        </Space>
      ) : (
        <Typography.Text type="secondary">
          {t('library.bibliographic.unavailable')}
        </Typography.Text>
      )}
    </Card>
  );
}
