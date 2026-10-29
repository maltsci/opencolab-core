import { Button, Card, Empty, List, Modal, Space, Tag, Typography, theme } from 'antd';
import { useState } from 'react';
import { useTranslation } from 'react-i18next';

import { ResearchRelationEditor } from './ResearchRelationEditor';
import { ResearchObjectDirectionSuggestion } from './ResearchObjectDirectionSuggestion';
import { normalizeStructuredResearchContent } from './research-object-content';
import type {
  ResearchRelationCitation,
  ResearchRelationMetadata,
  ResearchRelationSubmitPayload,
  SessionResearchObject,
  SessionResearchObjectRelation,
} from './types';

const { Text } = Typography;

interface ResearchObjectDetailsProps {
  activeObject: SessionResearchObject;
  relations: SessionResearchObjectRelation[];
  availableTargets: SessionResearchObject[];
  onSubmitRelation: (sourceObjectId: string, payload: ResearchRelationSubmitPayload) => Promise<void>;
  onDeleteRelation: (relationId: string) => Promise<void>;
  onSelectTargetObject: (targetObjectId: string) => void;
  viewMode?: 'details' | 'graph';
}

function readConfidence(metadataJson: ResearchRelationMetadata): string | null {
  const confidence = metadataJson.confidence;
  return typeof confidence === 'number' ? confidence.toFixed(2) : null;
}

function readNote(metadataJson: ResearchRelationMetadata): string {
  if (typeof metadataJson.evidence?.note === 'string') {
    return metadataJson.evidence.note.trim();
  }

  return typeof metadataJson.note === 'string' ? metadataJson.note.trim() : '';
}

function readTraceId(metadataJson: ResearchRelationMetadata): string {
  if (typeof metadataJson.evidence?.trace_id === 'string') {
    return metadataJson.evidence.trace_id.trim();
  }

  return typeof metadataJson.trace_id === 'string' ? metadataJson.trace_id.trim() : '';
}

function readCitations(metadataJson: ResearchRelationMetadata): ResearchRelationCitation[] {
  if (Array.isArray(metadataJson.evidence?.citations)) {
    return metadataJson.evidence.citations;
  }

  return Array.isArray(metadataJson.citations) ? metadataJson.citations : [];
}

function readCitationSnippet(citations: ResearchRelationCitation[]): string {
  for (const citation of citations) {
    if (typeof citation.snippet === 'string' && citation.snippet.trim()) {
      return citation.snippet.trim();
    }
  }

  return '';
}

function readCitationFallback(citations: ResearchRelationCitation[]): string {
  for (const citation of citations) {
    if (typeof citation.source_id === 'string' && citation.source_id.trim()) {
      return citation.source_id.trim();
    }

    if (typeof citation.chunk_id === 'string' && citation.chunk_id.trim()) {
      return citation.chunk_id.trim();
    }
  }

  return '';
}

function readEvidenceSummary(metadataJson: ResearchRelationMetadata): string {
  const citations = readCitations(metadataJson);
  const snippet = readCitationSnippet(citations);
  if (snippet) {
    return snippet;
  }

  const note = readNote(metadataJson);
  if (note) {
    return note;
  }

  return readCitationFallback(citations);
}

export function ResearchObjectDetails({
  activeObject,
  relations,
  availableTargets,
  onSubmitRelation,
  onDeleteRelation,
  onSelectTargetObject,
  viewMode = 'details',
}: ResearchObjectDetailsProps) {
  const { t } = useTranslation();
  const { token } = theme.useToken();
  const [relationModalOpen, setRelationModalOpen] = useState(false);
  const [relationSourceObject, setRelationSourceObject] = useState<SessionResearchObject>(activeObject);

  const supports = relations.filter((item) => item.relation_type === 'supports');
  const contradicts = relations.filter((item) => item.relation_type === 'contradicts');
  const structuredContent = normalizeStructuredResearchContent(activeObject.content);
  const activeObjectTypeLabel = activeObject.type === 'hypothesis'
    ? t('researchObject.typeHypothesis')
    : t('researchObject.typeDiscussion');
  const activeObjectTitle = activeObject.title || t('timeline.untitled');

  const openRelationModal = (sourceObject: SessionResearchObject) => {
    setRelationSourceObject(sourceObject);
    setRelationModalOpen(true);
  };

  const openRelationModalById = (sourceObjectId: string) => {
    const sourceObject = availableTargets.find((item) => item.id === sourceObjectId);
    if (sourceObject) {
      openRelationModal(sourceObject);
    }
  };

  const handleSubmitRelation = async (payload: ResearchRelationSubmitPayload) => {
    await onSubmitRelation(relationSourceObject.id, payload);
    setRelationModalOpen(false);
  };

  const renderStructuredSection = (label: string, items: string[]) => {
    if (items.length === 0) return null;
    return (
      <div>
        <div style={{ fontSize: 12, color: token.colorTextTertiary, marginBottom: 6 }}>
          {label}
        </div>
        <List
          size="small"
          split={false}
          dataSource={items}
          renderItem={(item) => (
            <List.Item style={{ padding: '2px 0' }}>{item}</List.Item>
          )}
        />
      </div>
    );
  };

  const renderRelationList = (items: SessionResearchObjectRelation[]) => {
    if (items.length === 0) {
      return <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={t('relations.empty')} />;
    }

    return (
      <List
        split={false}
        dataSource={items}
        renderItem={(relation) => {
          const confidence = readConfidence(relation.metadata_json);
          const traceId = readTraceId(relation.metadata_json);
          const citations = readCitations(relation.metadata_json);
          const evidenceSummary = readEvidenceSummary(relation.metadata_json);

          return (
            <List.Item style={{ padding: '8px 0' }}>
              <Card size="small" style={{ width: '100%' }}>
                <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                  <Space wrap>
                    <Tag color={relation.target_object.type === 'hypothesis' ? 'purple' : 'blue'}>
                      {relation.target_object.type === 'hypothesis'
                        ? t('researchObject.typeHypothesis')
                        : t('researchObject.typeDiscussion')}
                    </Tag>
                    <Text strong>{relation.target_object.title || t('timeline.untitled')}</Text>
                    {confidence && (
                      <Tag>{t('relations.confidenceValue', { value: confidence })}</Tag>
                    )}
                    <Tag>{relation.created_by_type}</Tag>
                    {traceId && <Tag>{t('relations.evidenceFromTrace')}</Tag>}
                    {citations.length > 0 && (
                      <Tag>{t('relations.evidenceCitationCount', { count: citations.length })}</Tag>
                    )}
                  </Space>
                  <div
                    style={{
                      padding: 10,
                      borderRadius: 8,
                      background: token.colorFillQuaternary,
                      border: `1px solid ${token.colorBorderSecondary}`,
                    }}
                  >
                    <Text strong>
                      {t('relations.directionPreview', {
                        source: activeObject.title || t('timeline.untitled'),
                        relation: t(`relations.${relation.relation_type}`),
                      })}
                    </Text>
                    <div style={{ marginTop: 6 }}>
                      <Button
                        type="link"
                        size="small"
                        onClick={() => onSelectTargetObject(relation.target_object.id)}
                        style={{ padding: 0 }}
                      >
                        {relation.target_object.title || t('timeline.untitled')}
                      </Button>
                    </div>
                  </div>
                  {evidenceSummary && (
                    <Text type="secondary" style={{ whiteSpace: 'pre-wrap' }}>
                      {evidenceSummary}
                    </Text>
                  )}
                  <div>
                    <Button
                      type="link"
                      danger
                      size="small"
                      onClick={() => onDeleteRelation(relation.id)}
                      style={{ padding: 0 }}
                    >
                      {t('common.delete')}
                    </Button>
                  </div>
                </div>
              </Card>
            </List.Item>
          );
        }}
      />
    );
  };

  const renderRelationMapColumn = (
    title: string,
    color: string,
    items: SessionResearchObjectRelation[],
  ) => (
    <div
      style={{
        flex: 1,
        minWidth: 0,
        display: 'flex',
        flexDirection: 'column',
        gap: 8,
      }}
    >
      <div style={{ fontSize: 12, color: token.colorTextTertiary }}>{title}</div>
      {items.length === 0 ? (
        <div
          style={{
            padding: 12,
            borderRadius: 8,
            border: `1px dashed ${token.colorBorder}`,
            background: token.colorBgContainer,
            color: token.colorTextTertiary,
            fontSize: 13,
          }}
        >
          {t('relations.empty')}
        </div>
      ) : (
        items.map((relation) => {
          const evidenceSummary = readEvidenceSummary(relation.metadata_json);
          return (
            <div
              key={relation.id}
              style={{
                padding: 12,
                borderRadius: 8,
                border: `1px solid ${color}`,
                background: token.colorBgContainer,
                display: 'flex',
                flexDirection: 'column',
                gap: 8,
              }}
            >
              <Space wrap>
                <Tag color={relation.target_object.type === 'hypothesis' ? 'purple' : 'blue'}>
                  {relation.target_object.type === 'hypothesis'
                    ? t('researchObject.typeHypothesis')
                    : t('researchObject.typeDiscussion')}
                </Tag>
                <Text strong>{relation.target_object.title || t('timeline.untitled')}</Text>
              </Space>
              {evidenceSummary && (
                <Text type="secondary" style={{ whiteSpace: 'pre-wrap', fontSize: 13 }}>
                  {evidenceSummary}
                </Text>
              )}
              <Space size={12} wrap>
                <Button
                  type="link"
                  size="small"
                  onClick={() => onSelectTargetObject(relation.target_object.id)}
                  style={{ padding: 0 }}
                >
                  {t('timeline.openObject')}
                </Button>
                <Button
                  type="link"
                  size="small"
                  onClick={() => openRelationModalById(relation.target_object.id)}
                  style={{ padding: 0 }}
                >
                  {t('relations.add')}
                </Button>
              </Space>
            </div>
          );
        })
      )}
    </div>
  );

  return (
    <Card
      size="small"
      title={t('relations.detailsTitle')}
      extra={viewMode === 'details' ? (
        <Space size={8}>
          <ResearchObjectDirectionSuggestion researchObject={activeObject} />
          <Button size="small" onClick={() => openRelationModal(activeObject)}>
            {t('relations.add')}
          </Button>
        </Space>
      ) : null}
      styles={{ body: { display: 'flex', flexDirection: 'column', gap: 16 } }}
    >
      <div
        style={{
          display: 'flex',
          flexDirection: 'column',
          gap: 10,
          padding: 12,
          borderRadius: 8,
          border: `1px solid ${token.colorBorderSecondary}`,
          background: activeObject.type === 'hypothesis' ? token.colorFillQuaternary : token.colorPrimaryBg,
        }}
      >
        <div style={{ fontSize: 12, color: token.colorTextTertiary }}>
          {t('relations.currentObject')}
        </div>
        <Space wrap>
          <Tag color={activeObject.type === 'hypothesis' ? 'purple' : 'blue'}>
            {activeObjectTypeLabel}
          </Tag>
          <Text strong>{activeObjectTitle}</Text>
        </Space>
        <Text type="secondary" style={{ fontSize: 13 }}>
          {t('relations.currentObjectHint')}
        </Text>
        {structuredContent ? (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 12, color: token.colorTextSecondary }}>
            {structuredContent.overview && (
              <div>
                <div style={{ fontSize: 12, color: token.colorTextTertiary, marginBottom: 6 }}>
                  {t('agent.overview')}
                </div>
                <div style={{ whiteSpace: 'pre-wrap' }}>
                  {structuredContent.overview}
                </div>
              </div>
            )}
            {renderStructuredSection(t('agent.keyPoints'), structuredContent.keyPoints)}
            {renderStructuredSection(t('agent.contradictions'), structuredContent.contradictions)}
            {renderStructuredSection(t('agent.gaps'), structuredContent.gaps)}
            {renderStructuredSection(t('agent.actionItems'), structuredContent.actionItems)}
            {renderStructuredSection(t('agent.responseOutline'), structuredContent.responseOutline)}
            {renderStructuredSection(t('agent.validationNotes'), structuredContent.validationNotes)}
          </div>
        ) : (
          <div style={{ whiteSpace: 'pre-wrap', color: token.colorTextSecondary }}>
            {activeObject.content || t('timeline.emptyContent')}
          </div>
        )}
      </div>

      <div
        style={{
          padding: 12,
          borderRadius: 8,
          border: `1px solid ${token.colorBorderSecondary}`,
          background: token.colorBgContainer,
        }}
      >
        <div style={{ fontSize: 12, color: token.colorTextTertiary, marginBottom: 8 }}>
          {t('relations.mapTitle')}
        </div>
        <Text type="secondary" style={{ fontSize: 13 }}>
          {t('relations.mapHint')}
        </Text>
        <div
          style={{
            marginTop: 12,
            display: 'flex',
            flexDirection: 'column',
            gap: 12,
          }}
        >
          <div
            style={{
              padding: 12,
              borderRadius: 8,
              border: `1px solid ${token.colorBorder}`,
              background: token.colorBgContainer,
            }}
          >
            <Space wrap>
              <Tag color={activeObject.type === 'hypothesis' ? 'purple' : 'blue'}>
                {activeObjectTypeLabel}
              </Tag>
              <Text strong>{activeObjectTitle}</Text>
              {viewMode === 'graph' && (
                <Button size="small" onClick={() => openRelationModal(activeObject)}>
                  {t('relations.add')}
                </Button>
              )}
            </Space>
          </div>
          <div
            style={{
              display: 'flex',
              gap: 12,
              flexWrap: 'wrap',
            }}
          >
            {renderRelationMapColumn(t('relations.supportsList'), token.colorSuccessBorder, supports)}
            {renderRelationMapColumn(t('relations.contradictsList'), token.colorErrorBorder, contradicts)}
          </div>
        </div>
      </div>

      {viewMode === 'details' && (
        <>
          <div>
            <div style={{ fontSize: 12, color: token.colorTextTertiary, marginBottom: 8 }}>
              {t('relations.supportsList')}
            </div>
            {renderRelationList(supports)}
          </div>

          <div>
            <div style={{ fontSize: 12, color: token.colorTextTertiary, marginBottom: 8 }}>
              {t('relations.contradictsList')}
            </div>
            {renderRelationList(contradicts)}
          </div>

        </>
      )}
      <Modal
        title={t('relations.addModalTitle')}
        open={relationModalOpen}
        footer={null}
        onCancel={() => setRelationModalOpen(false)}
        destroyOnHidden
      >
        <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
          <Text type="secondary" style={{ fontSize: 13 }}>
            {t('relations.addHint')}
          </Text>
          <ResearchRelationEditor
            activeObject={relationSourceObject}
            availableTargets={availableTargets}
            onSubmit={handleSubmitRelation}
          />
        </div>
      </Modal>
    </Card>
  );
}
