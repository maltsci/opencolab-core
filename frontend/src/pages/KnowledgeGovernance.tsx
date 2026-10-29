import { Tabs } from 'antd';
import { useTranslation } from 'react-i18next';
import { useSearchParams } from 'react-router-dom';

import PageContainer from '../components/library/PageContainer';
import KnowledgeInbox from './KnowledgeInbox';
import KnowledgeReview from './KnowledgeReview';
import MyKnowledgeSuggestions from './MyKnowledgeSuggestions';

interface KnowledgeGovernanceProps {
  canReview: boolean;
}

type KnowledgeGovernanceTab = 'inbox' | 'suggestions' | 'review';

export default function KnowledgeGovernance({ canReview }: KnowledgeGovernanceProps) {
  const { t } = useTranslation();
  const [searchParams, setSearchParams] = useSearchParams();
  const requestedTab = searchParams.get('tab');
  const activeTab: KnowledgeGovernanceTab = requestedTab === 'suggestions'
    ? 'suggestions'
    : requestedTab === 'review' && canReview
      ? 'review'
      : 'inbox';

  const items = [
    {
      key: 'inbox',
      label: t('nav.knowledgeInbox'),
      children: <KnowledgeInbox embedded canReview={canReview} />,
    },
    {
      key: 'suggestions',
      label: t('nav.knowledgeSuggestions'),
      children: <MyKnowledgeSuggestions embedded />,
    },
    ...(canReview ? [{
      key: 'review',
      label: t('nav.knowledgeReview'),
      children: <KnowledgeReview embedded />,
    }] : []),
  ];

  return (
    <PageContainer title={t('nav.knowledgeGovernance')} description={t('knowledgeInbox.description')}>
      <Tabs
        activeKey={activeTab}
        items={items}
        onChange={(tab) => setSearchParams({ tab })}
      />
    </PageContainer>
  );
}
