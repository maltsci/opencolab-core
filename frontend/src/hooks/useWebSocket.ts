import { notification } from 'antd';
import { useCallback, useEffect, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';

import { getAuthToken, subscribeAuthToken } from '../services/auth-token';

export interface CitationItem {
  source_id?: string;
  chunk_id?: string;
  snippet?: string;
  score?: number;
  [key: string]: unknown;
}

export interface TraceInputs {
  query?: string;
  source_ids?: string[];
  [key: string]: unknown;
}

export interface RetrievalItem {
  source_id?: string;
  chunk_id?: string;
  score?: number;
  [key: string]: unknown;
}

export interface ResearchTraceMeta {
  traceId: string | null;
  messageId: string | null;
  workflowRunId?: string | null;
  inputs: TraceInputs;
  retrieval: RetrievalItem[];
  citations: CitationItem[];
  summarySteps: string[];
}

export interface StreamErrorState {
  eventId: number;
  message: string | null;
}

interface WSMessage {
  type: 'token' | 'done' | 'error' | 'title_updated';
  content?: string;
  message_id?: string;
  message?: string;
  title?: string;
  trace_id?: string;
  inputs?: TraceInputs;
  retrieval?: RetrievalItem[];
  citations?: CitationItem[];
  summary_steps?: string[];
}

export interface CompletedAssistantMessage {
  eventId: number;
  messageId: string | null;
  content: string;
}

interface SendMessageOptions {
  replaceMessageId?: string | null;
}

export function useWebSocket(sessionId: string | undefined) {
  const { t, i18n } = useTranslation();
  const wsRef = useRef<WebSocket | null>(null);
  const [authToken, setAuthTokenState] = useState(() => getAuthToken());
  const [isConnected, setIsConnected] = useState(false);
  const [streamingContent, setStreamingContent] = useState('');
  const [isStreaming, setIsStreaming] = useState(false);
  const [sessionTitle, setSessionTitle] = useState<string | null>(null);
  const [streamError, setStreamError] = useState<StreamErrorState>({
    eventId: 0,
    message: null,
  });
  const [completedAssistantMessage, setCompletedAssistantMessage] = useState<CompletedAssistantMessage>({
    eventId: 0,
    messageId: null,
    content: '',
  });
  const [latestTrace, setLatestTrace] = useState<ResearchTraceMeta>({
    traceId: null,
    messageId: null,
    inputs: {},
    retrieval: [],
    citations: [],
    summarySteps: [],
  });

  useEffect(() => subscribeAuthToken(() => {
    setAuthTokenState(getAuthToken());
  }), []);

  useEffect(() => {
    if (!sessionId) return;

    setStreamingContent('');
    setIsStreaming(false);
    setSessionTitle(null);
    setStreamError({
      eventId: 0,
      message: null,
    });
    setCompletedAssistantMessage({
      eventId: 0,
      messageId: null,
      content: '',
    });
    setLatestTrace({
      traceId: null,
      messageId: null,
      inputs: {},
      retrieval: [],
      citations: [],
      summarySteps: [],
    });

    if (!authToken) {
      setIsConnected(false);
      setIsStreaming(false);
      return;
    }

    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const ws = new WebSocket(
      `${protocol}//${window.location.host}/api/v1/ws/sessions/${sessionId}?token=${authToken}`
    );

    ws.onopen = () => setIsConnected(true);
    ws.onclose = () => {
      setIsConnected(false);
      setIsStreaming(false);
    };

    ws.onmessage = (event) => {
      const data: WSMessage = JSON.parse(event.data);
      if (data.type === 'token') {
        setStreamingContent((prev) => prev + (data.content || ''));
      } else if (data.type === 'done') {
        setIsStreaming(false);
        setCompletedAssistantMessage((prev) => ({
          eventId: prev.eventId + 1,
          messageId: data.message_id || null,
          content: data.content || '',
        }));
        setLatestTrace({
          traceId: data.trace_id || null,
          messageId: data.message_id || null,
          inputs: data.inputs || {},
          retrieval: data.retrieval || [],
          citations: data.citations || [],
          summarySteps: data.summary_steps || [],
        });
      } else if (data.type === 'error') {
        setIsStreaming(false);
        const errorMessage = data.message || t('session.responseFailedDescription');
        setStreamError((prev) => ({
          eventId: prev.eventId + 1,
          message: errorMessage,
        }));
        notification.error({
          message: t('session.responseFailed'),
          description: errorMessage,
        });
      } else if (data.type === 'title_updated') {
        setSessionTitle(data.title || null);
      }
    };

    wsRef.current = ws;

    return () => {
      ws.close();
    };
  }, [authToken, sessionId, t]);

  const sendMessage = useCallback(
    (content: string, sourceIds: string[] = [], options: SendMessageOptions = {}) => {
      if (wsRef.current?.readyState === WebSocket.OPEN) {
        setStreamingContent('');
        setIsStreaming(true);
        setStreamError((prev) => ({
          ...prev,
          message: null,
        }));
        wsRef.current.send(JSON.stringify({
          content,
          source_ids: sourceIds,
          locale: i18n.language,
          replace_message_id: options.replaceMessageId || undefined,
        }));
      }
    },
    [i18n.language]
  );

  return {
    isConnected,
    streamingContent,
    isStreaming,
    sendMessage,
    sessionTitle,
    latestTrace,
    streamError,
    completedAssistantMessage,
  };
}
