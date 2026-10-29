import { ArrowRightOutlined, FolderOutlined, ReadOutlined, RobotOutlined, SearchOutlined, TeamOutlined, UserOutlined } from '@ant-design/icons';
import { Alert, Button, Input, Spin, Tag, message } from 'antd';
import { type ReactNode, useCallback, useEffect, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useNavigate, useSearchParams } from 'react-router-dom';

import PageContainer from '../components/library/PageContainer';
import EmptyState from '../components/ui/EmptyState';
import apiClient from '../services/api-client';
import type { LibraryCatalogSearchResult, LibraryFullTextSearchResult, LibrarySearchResponse } from '../types/research-asset';
import type { PersonDirectoryEntry } from '../types/person';
import type { Project } from '../types/project';
import type { ResearchDirection, ResearchDirectionPage } from '../types/research-direction';
import './knowledge-assistant.css';

interface ResourceResult {
  resource: LibraryCatalogSearchResult | LibraryFullTextSearchResult;
  canReadContent: boolean;
}

function orderResourceResults(response: LibrarySearchResponse): ResourceResult[] {
  const metadataResultIds = new Set(response.catalog_results.map((resource) => resource.id));
  return [
    ...response.catalog_results.map((resource) => ({
      resource,
      canReadContent: resource.can_read_content,
    })),
    ...response.full_text_results
      .filter((resource) => !metadataResultIds.has(resource.id))
      .map((resource) => ({ resource, canReadContent: true })),
  ];
}

type DirectionSearchResult = Pick<ResearchDirection, 'id' | 'name' | 'summary'>;

interface ProjectKnowledgeContext {
  members: PersonDirectoryEntry[];
  directions: DirectionSearchResult[];
}

function matchesPerson(person: PersonDirectoryEntry, query: string): boolean {
  const haystack = [
    person.display_name,
    person.username,
    person.bio,
    ...person.consultation_topics,
    ...person.current_directions.map((direction) => direction.name),
  ].filter(Boolean).join(' ').toLocaleLowerCase();
  return query.toLocaleLowerCase().split(/\s+/).every((term) => haystack.includes(term));
}

function matchesDirection(direction: DirectionSearchResult, query: string): boolean {
  const haystack = [direction.name, direction.summary]
    .filter(Boolean)
    .join(' ')
    .toLocaleLowerCase();
  return query.toLocaleLowerCase().split(/\s+/).every((term) => haystack.includes(term));
}

function extractSearchTopic(query: string): string {
  const original = query.trim().replace(/[？?。！!]+$/g, '');
  const topic = original
    .replace(/^(?:请问|帮我|麻烦)?(?:找一下|查一下|搜索一下|看看|告诉我)?/u, '')
    .replace(/^(?:谁|有谁)(?:熟悉|了解|负责|在做|研究|擅长)?/u, '')
    .replace(/^(?:哪些?|有什么)(?:成员|人|资源|研究方向)?(?:熟悉|相关|可用)?/u, '')
    .replace(/(?:相关的?(?:成员|人|资源|研究方向)?|有哪些?|吗)$/u, '')
    .trim();
  return topic || original;
}

function highlightSearchTerms(text: string, query: string): ReactNode {
  const normalizedQuery = query.trim();
  if (!normalizedQuery) return text;

  const terms = Array.from(new Set([
    normalizedQuery,
    ...normalizedQuery.split(/[\s\p{P}\p{S}]+/u),
  ]))
    .map((term) => term.trim())
    .filter((term) => term.length >= 2)
    .sort((left, right) => right.length - left.length)
    .slice(0, 12);
  if (terms.length === 0) return text;

  const patternTerms = terms.map((term) => {
    const escapedTerm = term.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
    return /^[a-z0-9]{1,3}$/i.test(term)
      ? `(?<![a-z0-9])${escapedTerm}(?![a-z0-9])`
      : escapedTerm;
  });
  const pattern = new RegExp(`(${patternTerms.join('|')})`, 'giu');
  const normalizedTerms = new Set(terms.map((term) => term.toLocaleLowerCase()));

  return text.split(pattern).map((part, index) => (
    normalizedTerms.has(part.toLocaleLowerCase())
      ? <mark key={`${part}-${index}`} className="knowledge-search-highlight">{part}</mark>
      : part
  ));
}

export default function KnowledgeAssistant() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const contextQuery = searchParams.get('query')?.trim() || '';
  const contextType = searchParams.get('context');
  const projectId = searchParams.get('project')?.trim() || null;
  const [query, setQuery] = useState('');
  const [askedQuery, setAskedQuery] = useState('');
  const [searchTopic, setSearchTopic] = useState('');
  const [loading, setLoading] = useState(false);
  const [directions, setDirections] = useState<DirectionSearchResult[]>([]);
  const [people, setPeople] = useState<PersonDirectoryEntry[]>([]);
  const [resources, setResources] = useState<ResourceResult[]>([]);
  const [fullTextSearchAvailable, setFullTextSearchAvailable] = useState(true);
  const [projectScope, setProjectScope] = useState<Project | null>(null);
  const [projectScopeUnavailable, setProjectScopeUnavailable] = useState(false);

  const totalResults = directions.length + people.length + resources.length;
  const hasAsked = askedQuery.length > 0;

  const peoplePreview = useMemo(() => people.slice(0, 6), [people]);
  const resourcePreview = useMemo(() => resources.slice(0, 6), [resources]);
  const directionPreview = useMemo(() => directions.slice(0, 6), [directions]);
  const accessibleResourceCount = useMemo(
    () => resources.filter((resource) => resource.canReadContent).length,
    [resources],
  );

  const runSearch = useCallback(async (normalizedQuery: string) => {
    setLoading(true);
    setAskedQuery(normalizedQuery);
    const topic = extractSearchTopic(normalizedQuery);
    setSearchTopic(topic);
    try {
      if (projectId) {
        const [contextResponse, resourceResponse] = await Promise.all([
          apiClient.get<ProjectKnowledgeContext>(`/projects/${projectId}/knowledge-context`),
          apiClient.get<LibrarySearchResponse>(
            `/projects/${projectId}/assets/search`,
            { params: { query: topic } },
          ),
        ]);
        setDirections(contextResponse.data.directions.filter((direction) => matchesDirection(direction, topic)));
        setPeople(contextResponse.data.members.filter((person) => matchesPerson(person, topic)));
        setResources(orderResourceResults(resourceResponse.data));
        setFullTextSearchAvailable(resourceResponse.data.full_text_search_available);
        return;
      }
      const [directionResponse, peopleResponse, resourceResponse] = await Promise.all([
        apiClient.get<ResearchDirectionPage>('/research-directions', {
          params: { status: 'active', limit: 20, query: topic },
        }),
        apiClient.get<PersonDirectoryEntry[]>('/people'),
        apiClient.get<LibrarySearchResponse>('/library/assets/search', {
          params: { query: topic, include_project_assets: true },
        }),
      ]);
      setDirections(directionResponse.data.items);
      setPeople(peopleResponse.data.filter((person) => matchesPerson(person, topic)));
      setResources(orderResourceResults(resourceResponse.data));
      setFullTextSearchAvailable(resourceResponse.data.full_text_search_available);
    } catch {
      setDirections([]);
      setPeople([]);
      setResources([]);
      setFullTextSearchAvailable(true);
      message.error(t('assistant.searchFailed'));
    } finally {
      setLoading(false);
    }
  }, [projectId, t]);

  useEffect(() => {
    if (!projectId) {
      setProjectScope(null);
      setProjectScopeUnavailable(false);
      return;
    }
    let active = true;
    setProjectScope(null);
    setProjectScopeUnavailable(false);
    apiClient.get<Project>(`/projects/${projectId}`)
      .then((response) => {
        if (active) setProjectScope(response.data);
      })
      .catch(() => {
        if (active) setProjectScopeUnavailable(true);
      });
    return () => {
      active = false;
    };
  }, [projectId]);

  useEffect(() => {
    setAskedQuery('');
    setSearchTopic('');
    setDirections([]);
    setPeople([]);
    setResources([]);
    setFullTextSearchAvailable(true);
  }, [projectId]);

  const ask = () => {
    const normalizedQuery = query.trim();
    if (!normalizedQuery) {
      message.warning(t('assistant.queryRequired'));
      return;
    }
    void runSearch(normalizedQuery);
  };

  useEffect(() => {
    if (!contextQuery) return;
    setQuery(contextQuery);
    void runSearch(contextQuery);
  }, [contextQuery, runSearch]);

  const contextLabel = contextType === 'person' || contextType === 'direction' || contextType === 'resource'
    ? t(`assistant.context.${contextType}`)
    : null;
  const labAssistantPath = contextQuery
    ? `/assistant?query=${encodeURIComponent(contextQuery)}`
    : '/assistant';

  return (
    <PageContainer title={t('assistant.title')} description={t('assistant.description')}>
      <div className="knowledge-assistant">
        <section className="knowledge-hero" aria-labelledby="knowledge-assistant-heading">
          <div className="knowledge-eyebrow">{t('assistant.eyebrow')}</div>
          <div className="knowledge-hero-copy">
            <h2 id="knowledge-assistant-heading">{t('assistant.heroTitle')}</h2>
            <p>{t(projectId ? 'assistant.projectScopeHint' : 'assistant.scopeHint')}</p>
          </div>
          <Input.Search
            className="knowledge-search"
            size="large"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            onSearch={ask}
            enterButton={t('assistant.ask')}
            prefix={<SearchOutlined />}
            placeholder={t('assistant.placeholder')}
            aria-label={t('assistant.placeholder')}
          />
        </section>

        {projectId && projectScope ? (
          <Alert
            type="info"
            showIcon
            message={t('assistant.projectScope', { name: projectScope.name })}
            description={t('assistant.projectScopeDescription')}
            action={(
              <Button type="link" size="small" onClick={() => navigate(labAssistantPath)}>
                {t('assistant.switchToLab')}
              </Button>
            )}
          />
        ) : null}

        {projectId && projectScopeUnavailable ? (
          <Alert
            type="warning"
            showIcon
            message={t('assistant.projectScopeUnavailable')}
            action={(
              <Button type="link" size="small" onClick={() => navigate(labAssistantPath)}>
                {t('assistant.switchToLab')}
              </Button>
            )}
          />
        ) : null}

        {contextLabel ? (
          <Alert
            type="info"
            showIcon
            message={t('assistant.contextHint', { entity: contextLabel, name: contextQuery })}
          />
        ) : null}

        {loading ? (
          <div className="knowledge-loading"><Spin tip={t('assistant.searching')} /></div>
        ) : null}

        {hasAsked && !loading && !fullTextSearchAvailable ? (
          <Alert type="info" showIcon message={t('assistant.fullTextUnavailable')} />
        ) : null}

        {hasAsked && !loading && totalResults === 0 ? (
          <div className="knowledge-empty">
            <EmptyState icon={<RobotOutlined />} title={t('assistant.emptyTitle')} description={t('assistant.emptyDescription')} />
          </div>
        ) : null}

        {hasAsked && !loading && totalResults > 0 ? (
          <div className="knowledge-results">
            <div className="knowledge-result-context">
              <span>{t('assistant.resultOverview')}</span>
              {searchTopic !== askedQuery ? (
                <strong>{t('assistant.searchTopic', { topic: searchTopic })}</strong>
              ) : (
                <strong>{askedQuery}</strong>
              )}
            </div>

            <div className="knowledge-metrics" aria-label={t('assistant.resultOverview')}>
              <div><strong>{resources.length}</strong><span>{t('assistant.metric.resources')}</span></div>
              <div><strong>{accessibleResourceCount}</strong><span>{t('assistant.metric.readable')}</span></div>
              <div><strong>{people.length}</strong><span>{t('assistant.metric.people')}</span></div>
              <div><strong>{directions.length}</strong><span>{t('assistant.metric.directions')}</span></div>
            </div>

            {resourcePreview.length > 0 ? (
              <section className="knowledge-section">
                <header className="knowledge-section-header">
                  <div>
                    <span className="knowledge-section-kicker">{t('assistant.resourceKicker')}</span>
                    <h3><FolderOutlined /> {t(projectId ? 'assistant.projectResources' : 'assistant.resources')}</h3>
                  </div>
                  <Button
                    type="link"
                    onClick={() => navigate(projectId
                      ? `/projects/${projectId}?tab=assets`
                      : `/library?search=${encodeURIComponent(searchTopic)}`)}
                  >
                    {t('assistant.viewAllResources')}
                  </Button>
                </header>

                <div className="knowledge-resource-grid">
                  {resourcePreview.map(({ resource, canReadContent }) => {
                    const directionsForResource = resource.directions || [];
                    const assetType = resource.asset_type || 'uploaded_file';
                    const isPaper = assetType === 'uploaded_file'
                      && (resource.title.toLocaleLowerCase().endsWith('.pdf')
                        || resource.authors.length > 0
                        || resource.keywords.length > 0);
                    const resourceTypeLabel = isPaper
                      ? t('assistant.resourceType.paper')
                      : t(`library.assetType.${assetType}`, assetType);
                    const description = resource.description
                      || (canReadContent && 'snippet' in resource ? resource.snippet : null)
                      || resource.keywords.join(' · ')
                      || resource.tags.join(' · ')
                      || t('assistant.resourceFallback');
                    const resourceHref = `/resources/${encodeURIComponent(resource.id)}`;
                    const resourcePreviewHref = `${resourceHref}?preview=1`;
                    return (
                      <article
                        key={resource.id}
                        className="knowledge-resource-card"
                        data-asset-type={assetType}
                      >
                        <div className="knowledge-resource-topline">
                          <span className="knowledge-resource-type">
                            {resourceTypeLabel}
                          </span>
                          <Tag bordered={false} color={resource.match_type === 'semantic' ? 'blue' : 'green'}>
                            {t(`assistant.match.${resource.match_type}`)}
                          </Tag>
                        </div>
                        <a
                          className="knowledge-resource-title"
                          href={resourceHref}
                          target="_blank"
                          rel="noopener noreferrer"
                          aria-label={t('assistant.openResourceInNewTab', { title: resource.title })}
                        >
                          {resource.title}
                        </a>
                        <p className="knowledge-resource-description">
                          {highlightSearchTerms(description, searchTopic)}
                        </p>

                        <div className="knowledge-resource-meta">
                          <div>
                            <UserOutlined />
                            <span>{t('assistant.maintainedBy')}</span>
                            <strong>{resource.steward_name || t('assistant.maintainerUnknown')}</strong>
                          </div>
                          <div className="knowledge-direction-links">
                            <ReadOutlined />
                            <span>{t('assistant.relatedDirections')}</span>
                            {directionsForResource.length > 0 ? (
                              directionsForResource.slice(0, 3).map((direction) => (
                                <Button
                                  key={direction.id}
                                  type="link"
                                  size="small"
                                  onClick={() => navigate(`/research?direction=${encodeURIComponent(direction.id)}`)}
                                >
                                  {direction.name}
                                </Button>
                              ))
                            ) : (
                              <strong className="knowledge-empty-relation">
                                {t('assistant.directionsEmpty')}
                              </strong>
                            )}
                          </div>
                        </div>

                        <footer className="knowledge-resource-footer">
                          <span>{canReadContent ? t('assistant.resourceReadable') : t('assistant.catalog')}</span>
                          <Button
                            type="link"
                            icon={<ArrowRightOutlined />}
                            iconPosition="end"
                            href={resourcePreviewHref}
                            target="_blank"
                            rel="noopener noreferrer"
                            aria-label={t('assistant.previewResourceInNewTab', { title: resource.title })}
                          >
                            {t('assistant.previewResource')}
                          </Button>
                        </footer>
                      </article>
                    );
                  })}
                </div>
              </section>
            ) : null}

            {(directionPreview.length > 0 || peoplePreview.length > 0) ? (
              <div className="knowledge-entity-columns">
                {directionPreview.length > 0 ? (
                  <section className="knowledge-section knowledge-entity-section">
                    <header className="knowledge-section-header">
                      <div>
                        <span className="knowledge-section-kicker">{t('assistant.directionKicker')}</span>
                        <h3><ReadOutlined /> {t(projectId ? 'assistant.projectDirections' : 'assistant.directions')}</h3>
                      </div>
                    </header>
                    <div className="knowledge-entity-list">
                      {directionPreview.map((direction) => (
                        <button
                          type="button"
                          key={direction.id}
                          onClick={() => navigate(`/research?direction=${encodeURIComponent(direction.id)}`)}
                        >
                          <span>{direction.name}</span>
                          <small>{direction.summary || t('assistant.directionFallback')}</small>
                          <ArrowRightOutlined />
                        </button>
                      ))}
                    </div>
                  </section>
                ) : null}

                {peoplePreview.length > 0 ? (
                  <section className="knowledge-section knowledge-entity-section">
                    <header className="knowledge-section-header">
                      <div>
                        <span className="knowledge-section-kicker">{t('assistant.peopleKicker')}</span>
                        <h3><TeamOutlined /> {t('assistant.people')}</h3>
                      </div>
                      {!projectId ? (
                        <Button type="link" onClick={() => navigate(`/people?search=${encodeURIComponent(searchTopic)}`)}>
                          {t('assistant.viewAllPeople')}
                        </Button>
                      ) : null}
                    </header>
                    <div className="knowledge-entity-list">
                      {peoplePreview.map((person) => (
                        <button
                          type="button"
                          key={person.id}
                          onClick={() => navigate(`/people?person=${encodeURIComponent(person.id)}`)}
                        >
                          <span>{person.display_name || person.username}</span>
                          <small>
                            {person.bio
                              || person.current_directions.map((direction) => direction.name).join(' · ')
                              || t('assistant.personFallback')}
                          </small>
                          <ArrowRightOutlined />
                        </button>
                      ))}
                    </div>
                  </section>
                ) : null}
              </div>
            ) : null}
          </div>
        ) : null}
      </div>
    </PageContainer>
  );
}
