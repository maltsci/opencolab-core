import { Alert, Card, Progress, Space, Tag, Typography, theme } from 'antd';
import { useTranslation } from 'react-i18next';

import type { IdeaEvaluation, PeerReview } from '../../types/superagent';

const { Text } = Typography;

interface ScoreBarProps {
  label: string;
  value: number | null | undefined;
  max: number;
  unscoredLabel: string;
}

function ScoreBar({ label, value, max, unscoredLabel }: ScoreBarProps) {
  const hasValue = typeof value === 'number';
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
      <Text style={{ width: 96, fontSize: 12 }}>{label}</Text>
      <Progress
        style={{ flex: 1, margin: 0 }}
        percent={hasValue ? Math.round(((value as number) / max) * 100) : 0}
        showInfo={false}
        size="small"
        status={hasValue ? 'normal' : 'exception'}
      />
      <Text strong style={{ width: 64, fontSize: 12, textAlign: 'right' }}>
        {hasValue ? `${value} / ${max}` : unscoredLabel}
      </Text>
    </div>
  );
}

export function IdeaEvaluationCard({ evaluation }: { evaluation: IdeaEvaluation }) {
  const { t } = useTranslation();
  const { token } = theme.useToken();
  const scores = evaluation.scores || {};
  const novelty = evaluation.novelty_check;
  const unscored = t('superagent.scorecard.unscored');

  let noveltyTag = <Tag>{t('superagent.scorecard.undecided')}</Tag>;
  if (novelty?.decision_made) {
    noveltyTag = novelty.novel ? (
      <Tag color="green">{t('superagent.scorecard.novel')}</Tag>
    ) : (
      <Tag color="red">{t('superagent.scorecard.notNovel')}</Tag>
    );
  }

  return (
    <Card
      size="small"
      style={{ background: token.colorBgContainer }}
      title={(
        <Space wrap>
          <Tag color="blue">Planner + Literature Agent</Tag>
          <Text strong style={{ fontSize: 13 }}>
            {t('superagent.scorecard.ideaTitle')}
          </Text>
          {typeof evaluation.composite_score === 'number' && (
            <Tag color="gold">
              {`${t('superagent.scorecard.composite')} ${evaluation.composite_score} / 10`}
            </Tag>
          )}
        </Space>
      )}
    >
      {evaluation.status !== 'scored' && (
        <Alert
          type="info"
          showIcon
          style={{ marginBottom: 8 }}
          message={t('superagent.scorecard.unavailable')}
        />
      )}
      <Space direction="vertical" style={{ width: '100%' }} size={4}>
        <ScoreBar
          label={t('superagent.scorecard.interestingness')}
          value={scores.interestingness}
          max={10}
          unscoredLabel={unscored}
        />
        <ScoreBar
          label={t('superagent.scorecard.feasibility')}
          value={scores.feasibility}
          max={10}
          unscoredLabel={unscored}
        />
        <ScoreBar
          label={t('superagent.scorecard.novelty')}
          value={scores.novelty}
          max={10}
          unscoredLabel={unscored}
        />
      </Space>
      {evaluation.thought && (
        <Text type="secondary" style={{ display: 'block', fontSize: 12, marginTop: 8 }}>
          {evaluation.thought}
        </Text>
      )}
      {typeof evaluation.archive_size === 'number' && (
        <Text type="secondary" style={{ display: 'block', fontSize: 11, marginTop: 4 }}>
          {t('superagent.scorecard.archiveSize', { count: evaluation.archive_size })}
        </Text>
      )}
      {novelty && (
        <div
          style={{
            marginTop: 10,
            padding: '8px 10px',
            borderRadius: token.borderRadius,
            background: token.colorFillQuaternary,
            border: `1px solid ${token.colorBorderSecondary}`,
          }}
        >
          <Space wrap size={6}>
            <Text strong style={{ fontSize: 12 }}>
              {t('superagent.scorecard.noveltyTitle')}
            </Text>
            {noveltyTag}
            <Tag>{t('superagent.scorecard.rounds', { count: novelty.rounds_used ?? 0 })}</Tag>
            <Tag color={novelty.outbound_used ? 'orange' : 'green'}>
              {novelty.outbound_used
                ? t('superagent.scorecard.outbound')
                : t('superagent.scorecard.localOnly')}
            </Tag>
          </Space>
          {novelty.queries && novelty.queries.length > 0 && (
            <div style={{ marginTop: 6 }}>
              <Text type="secondary" style={{ fontSize: 11, marginRight: 6 }}>
                {t('superagent.scorecard.queries')}
              </Text>
              {novelty.queries.map((q, idx) => (
                <Tag key={`${q}-${idx}`} style={{ marginBottom: 4 }}>
                  {q}
                </Tag>
              ))}
            </div>
          )}
        </div>
      )}
    </Card>
  );
}

function BulletList({ title, items }: { title: string; items?: string[] }) {
  if (!items || items.length === 0) return null;
  return (
    <div style={{ marginTop: 6 }}>
      <Text strong style={{ fontSize: 12 }}>{title}</Text>
      <ul style={{ margin: '2px 0 0', paddingLeft: 18 }}>
        {items.slice(0, 5).map((item, idx) => (
          <li key={idx}>
            <Text style={{ fontSize: 12 }}>{item}</Text>
          </li>
        ))}
      </ul>
    </div>
  );
}

export function PeerReviewCard({ review }: { review: PeerReview }) {
  const { t } = useTranslation();
  const { token } = theme.useToken();
  const unscored = t('superagent.scorecard.unscored');

  if (review.status !== 'reviewed') {
    return (
      <Alert type="info" showIcon message={t('superagent.scorecard.reviewUnavailable')} />
    );
  }

  return (
    <Card
      size="small"
      style={{ background: token.colorBgContainer }}
      title={(
        <Space wrap>
          <Tag color="green">Writer Agent</Tag>
          <Text strong style={{ fontSize: 13 }}>
            {t('superagent.scorecard.reviewTitle')}
          </Text>
          <Tag color={review.Decision === 'Accept' ? 'green' : 'red'}>
            {review.Decision === 'Accept'
              ? t('superagent.scorecard.accept')
              : t('superagent.scorecard.reject')}
          </Tag>
          {review.ensemble_size && (
            <Tag>{t('superagent.scorecard.ensemble', { count: review.ensemble_size })}</Tag>
          )}
        </Space>
      )}
    >
      <Space direction="vertical" style={{ width: '100%' }} size={4}>
        <ScoreBar label={t('superagent.scorecard.overall')} value={review.Overall} max={10} unscoredLabel={unscored} />
        <ScoreBar label={t('superagent.scorecard.soundness')} value={review.Soundness} max={4} unscoredLabel={unscored} />
        <ScoreBar label={t('superagent.scorecard.presentation')} value={review.Presentation} max={4} unscoredLabel={unscored} />
        <ScoreBar label={t('superagent.scorecard.contribution')} value={review.Contribution} max={4} unscoredLabel={unscored} />
        <ScoreBar label={t('superagent.scorecard.confidence')} value={review.Confidence} max={5} unscoredLabel={unscored} />
      </Space>
      {review.Summary && (
        <Text type="secondary" style={{ display: 'block', fontSize: 12, marginTop: 8 }}>
          {review.Summary}
        </Text>
      )}
      <BulletList title={t('superagent.scorecard.strengths')} items={review.Strengths} />
      <BulletList title={t('superagent.scorecard.weaknesses')} items={review.Weaknesses} />
      <BulletList title={t('superagent.scorecard.questions')} items={review.Questions} />
      <Text type="secondary" style={{ display: 'block', fontSize: 11, marginTop: 8 }}>
        {t('superagent.scorecard.reviewDisclaimer')}
      </Text>
    </Card>
  );
}
