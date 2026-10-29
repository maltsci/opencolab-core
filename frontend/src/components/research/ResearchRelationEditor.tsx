import { Button, Form, Input, InputNumber, Select, Space } from 'antd';
import { useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';

import type { ResearchRelationSubmitPayload, SessionResearchObject } from './types';

interface ResearchRelationEditorProps {
  activeObject: SessionResearchObject;
  availableTargets: SessionResearchObject[];
  onSubmit: (payload: ResearchRelationSubmitPayload) => Promise<void>;
}

export function ResearchRelationEditor({
  activeObject,
  availableTargets,
  onSubmit,
}: ResearchRelationEditorProps) {
  const { t } = useTranslation();
  const [relationType, setRelationType] = useState<'supports' | 'contradicts'>('supports');
  const [targetObjectId, setTargetObjectId] = useState<string | null>(null);
  const [confidence, setConfidence] = useState<number>(0.8);
  const [note, setNote] = useState('');
  const [submitting, setSubmitting] = useState(false);

  const targetOptions = useMemo(
    () => availableTargets
      .filter((item) => item.id !== activeObject.id)
      .map((item) => ({
        value: item.id,
        label: `[${item.type === 'hypothesis'
          ? t('researchObject.typeHypothesis')
          : t('researchObject.typeDiscussion')}] ${item.title || t('timeline.untitled')}`,
      })),
    [activeObject.id, availableTargets, t],
  );

  const activeObjectLabel = `${activeObject.type === 'hypothesis'
    ? t('researchObject.typeHypothesis')
    : t('researchObject.typeDiscussion')} · ${activeObject.title || t('timeline.untitled')}`;

  const disabled = !targetObjectId || confidence < 0 || confidence > 1 || submitting;

  const handleSubmit = async () => {
    if (!targetObjectId) return;

    setSubmitting(true);
    try {
      await onSubmit({
        relation_type: relationType,
        target_object_id: targetObjectId,
        metadata_json: {
          confidence: Number(confidence),
          evidence: {
            citations: [],
            ...(note.trim() ? { note: note.trim() } : {}),
          },
        },
      });
      setTargetObjectId(null);
      setConfidence(0.8);
      setNote('');
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Form layout="vertical" style={{ marginTop: 8 }}>
      <div
        style={{
          marginBottom: 12,
          padding: 12,
          borderRadius: 8,
          background: '#f7faff',
          border: '1px solid #d6e4ff',
          color: '#1f1f1f',
          fontSize: 13,
        }}
      >
        {t('relations.directionPreview', {
          source: activeObjectLabel,
          relation: t(`relations.${relationType}`),
        })}
      </div>
      <Form.Item label={t('relations.type')}>
        <Select
          value={relationType}
          onChange={(value: 'supports' | 'contradicts') => setRelationType(value)}
          options={[
            { value: 'supports', label: t('relations.supports') },
            { value: 'contradicts', label: t('relations.contradicts') },
          ]}
        />
      </Form.Item>
      <Form.Item label={t('relations.target')}>
        <Select
          value={targetObjectId}
          onChange={(value: string) => setTargetObjectId(value)}
          options={targetOptions}
          placeholder={t('relations.targetPlaceholder')}
        />
      </Form.Item>
      <Form.Item label={t('relations.confidence')}>
        <InputNumber
          min={0}
          max={1}
          step={0.1}
          value={confidence}
          onChange={(value) => setConfidence(typeof value === 'number' ? value : 0)}
          style={{ width: '100%' }}
        />
      </Form.Item>
      <Form.Item label={t('relations.evidenceNote')}>
        <Input.TextArea
          value={note}
          onChange={(event) => setNote(event.target.value)}
          rows={3}
          placeholder={t('relations.evidenceNotePlaceholder')}
        />
      </Form.Item>
      <Space>
        <Button type="primary" onClick={handleSubmit} disabled={disabled} loading={submitting}>
          {t('relations.createAction')}
        </Button>
      </Space>
    </Form>
  );
}
