import { CopyOutlined, DeleteOutlined, HighlightOutlined } from '@ant-design/icons';
import { Button, Empty, Input, Popover, Spin, Typography, message } from 'antd';
import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from 'react';
import { useTranslation } from 'react-i18next';

import apiClient from '../../services/api-client';
import { getSourcePreviewToken } from '../../services/source-preview';
import './pdf-text-annotation-reader.css';

interface SourceAnnotation {
  id: string;
  source_id: string;
  selected_text: string;
  start_offset: number;
  end_offset: number;
  note: string | null;
  color: string;
  created_at: string;
  updated_at: string;
  author_name: string | null;
  can_delete: boolean;
}

interface SelectionDraft {
  startOffset: number;
  endOffset: number;
  selectedText: string;
}

interface PdfTextAnnotationReaderProps {
  sourceId: string;
}

type ReaderLineKind =
  | 'body'
  | 'code'
  | 'figure'
  | 'formula'
  | 'heading-1'
  | 'heading-2'
  | 'heading-3'
  | 'list'
  | 'page-break'
  | 'quote'
  | 'table';

function annotationMatchesText(annotation: SourceAnnotation, text: string): boolean {
  return (
    annotation.start_offset >= 0
    && annotation.end_offset <= text.length
    && annotation.start_offset < annotation.end_offset
    && text.slice(annotation.start_offset, annotation.end_offset) === annotation.selected_text
  );
}

function selectionOffset(root: HTMLElement, node: Node, offset: number): number | null {
  if (!root.contains(node)) return null;
  const range = document.createRange();
  range.selectNodeContents(root);
  try {
    range.setEnd(node, offset);
  } catch {
    return null;
  }
  return range.toString().length;
}

function getLineKind(line: string): ReaderLineKind {
  const trimmed = line.trim();
  if (/^<!--\s*page\s+\d+\s*-->$/i.test(trimmed)) return 'page-break';
  if (/^#{1}\s+/.test(trimmed)) return 'heading-1';
  if (/^#{2}\s+/.test(trimmed)) return 'heading-2';
  if (/^#{3,6}\s+/.test(trimmed)) return 'heading-3';
  if (/^(?:[-*+]\s+|\d+[.)]\s+)/.test(trimmed)) return 'list';
  if (/^>\s?/.test(trimmed)) return 'quote';
  if (/^```/.test(trimmed)) return 'code';
  if (
    /^!\[[^\]]*\]\([^)]*\)\s*$/.test(trimmed)
    || /^(?:figure|fig\.)\s*\d+/i.test(trimmed)
  ) return 'figure';
  if (
    /^(?:\$\$|\\\[|\\begin\{)/.test(trimmed)
    || /(?:\\(?:frac|sum|int|sqrt|alpha|beta|gamma)|[∑∫√])/.test(trimmed)
  ) return 'formula';
  if (/^\|.*\|\s*$/.test(trimmed)) return 'table';
  return 'body';
}

export default function PdfTextAnnotationReader({ sourceId }: PdfTextAnnotationReaderProps) {
  const { t } = useTranslation();
  const readerRef = useRef<HTMLDivElement>(null);
  const [messageApi, messageContext] = message.useMessage();
  const [text, setText] = useState<string | null>(null);
  const [annotations, setAnnotations] = useState<SourceAnnotation[]>([]);
  const [loading, setLoading] = useState(true);
  const [pendingSelection, setPendingSelection] = useState<SelectionDraft | null>(null);
  const [note, setNote] = useState('');
  const [saving, setSaving] = useState(false);
  const [activeAnnotationKey, setActiveAnnotationKey] = useState<string | null>(null);
  const [deleteConfirmationKey, setDeleteConfirmationKey] = useState<string | null>(null);
  const [deletingAnnotationId, setDeletingAnnotationId] = useState<string | null>(null);

  const loadReaderData = useCallback(async () => {
    setLoading(true);
    try {
      const [token, annotationResponse] = await Promise.all([
        getSourcePreviewToken(sourceId),
        apiClient.get<SourceAnnotation[]>(`/sources/${sourceId}/annotations`),
      ]);
      const textResponse = await apiClient.get(`/sources/${sourceId}/text`, {
        params: { token },
        responseType: 'text',
      });
      setText(typeof textResponse.data === 'string' ? textResponse.data : String(textResponse.data));
      setAnnotations(annotationResponse.data);
    } catch {
      setText(null);
      setAnnotations([]);
    } finally {
      setLoading(false);
    }
  }, [sourceId]);

  useEffect(() => {
    void loadReaderData();
    setPendingSelection(null);
    setNote('');
    setActiveAnnotationKey(null);
    setDeleteConfirmationKey(null);
  }, [loadReaderData]);

  const highlightedAnnotations = useMemo(() => {
    if (!text) return [];
    return annotations
      .filter((annotation) => annotationMatchesText(annotation, text))
      .sort((left, right) => left.start_offset - right.start_offset || left.end_offset - right.end_offset);
  }, [annotations, text]);

  const captureSelection = () => {
    const root = readerRef.current;
    const selection = window.getSelection();
    if (!root || !selection || selection.rangeCount === 0 || selection.isCollapsed || !text) return;

    const range = selection.getRangeAt(0);
    const startOffset = selectionOffset(root, range.startContainer, range.startOffset);
    const endOffset = selectionOffset(root, range.endContainer, range.endOffset);
    if (startOffset === null || endOffset === null || endOffset <= startOffset) return;

    const rawSelection = text.slice(startOffset, endOffset);
    const leadingWhitespace = rawSelection.length - rawSelection.trimStart().length;
    const trailingWhitespace = rawSelection.length - rawSelection.trimEnd().length;
    const trimmedStart = startOffset + leadingWhitespace;
    const trimmedEnd = endOffset - trailingWhitespace;
    const selectedText = text.slice(trimmedStart, trimmedEnd);
    if (!selectedText) return;

    setPendingSelection({ startOffset: trimmedStart, endOffset: trimmedEnd, selectedText });
    setNote('');
  };

  const copySelection = async () => {
    if (!pendingSelection) return;
    try {
      await navigator.clipboard.writeText(pendingSelection.selectedText);
      messageApi.success(t('library.annotations.copySuccess'));
    } catch {
      messageApi.error(t('library.annotations.copyFailed'));
    }
  };

  const saveAnnotation = async () => {
    if (!pendingSelection) return;
    setSaving(true);
    try {
      const { data } = await apiClient.post<SourceAnnotation>(
        `/sources/${sourceId}/annotations`,
        {
          selected_text: pendingSelection.selectedText,
          start_offset: pendingSelection.startOffset,
          end_offset: pendingSelection.endOffset,
          note: note || null,
        },
      );
      setAnnotations((current) => [...current, data]);
      setActiveAnnotationKey(null);
      setPendingSelection(null);
      setNote('');
      window.getSelection()?.removeAllRanges();
      messageApi.success(t('library.annotations.saveSuccess'));
    } catch {
      messageApi.error(t('library.annotations.saveFailed'));
    } finally {
      setSaving(false);
    }
  };

  const deleteAnnotation = useCallback(async (annotation: SourceAnnotation) => {
    setDeletingAnnotationId(annotation.id);
    try {
      await apiClient.delete(`/sources/${sourceId}/annotations/${annotation.id}`);
      setAnnotations((current) => current.filter((item) => item.id !== annotation.id));
      setActiveAnnotationKey((current) => current?.startsWith(`${annotation.id}-`) ? null : current);
      setDeleteConfirmationKey((current) => current?.startsWith(`${annotation.id}-`) ? null : current);
      messageApi.success(t('library.annotations.deleteSuccess'));
    } catch {
      messageApi.error(t('library.annotations.deleteFailed'));
    } finally {
      setDeletingAnnotationId(null);
    }
  }, [messageApi, sourceId, t]);

  const renderAnnotationNote = useCallback((annotation: SourceAnnotation, annotationKey: string) => (
    <div className="pdf-reader-note-popover">
      {annotation.note ? (
        <Typography.Paragraph>{annotation.note}</Typography.Paragraph>
      ) : (
        <Typography.Text type="secondary">
          {t('library.annotations.noNote')}
        </Typography.Text>
      )}
      <div className="pdf-reader-note-meta">
        <Typography.Text type="secondary">
          {annotation.author_name || t('library.annotations.formerMember')}
        </Typography.Text>
        <Typography.Text type="secondary">
          {new Intl.DateTimeFormat(undefined, { dateStyle: 'medium' }).format(new Date(annotation.created_at))}
        </Typography.Text>
        {annotation.can_delete && deleteConfirmationKey !== annotationKey ? (
          <Button
            aria-label={t('common.delete')}
            icon={<DeleteOutlined />}
            onClick={() => setDeleteConfirmationKey(annotationKey)}
            size="small"
            type="text"
          />
        ) : null}
      </div>
      {annotation.can_delete && deleteConfirmationKey === annotationKey ? (
        <div className="pdf-reader-delete-confirmation">
          <Typography.Text type="secondary">
            {t('library.annotations.deleteConfirm')}
          </Typography.Text>
          <div>
            <Button onClick={() => setDeleteConfirmationKey(null)} size="small">
              {t('common.cancel')}
            </Button>
            <Button
              danger
              loading={deletingAnnotationId === annotation.id}
              onClick={() => void deleteAnnotation(annotation)}
              size="small"
              type="primary"
            >
              {t('common.delete')}
            </Button>
          </div>
        </div>
      ) : null}
    </div>
  ), [deleteAnnotation, deleteConfirmationKey, deletingAnnotationId, t]);

  const renderedText = useMemo(() => {
    if (!text) return null;
    const lines = text.match(/.*(?:\n|$)/g) || [];
    let lineStart = 0;

    return lines.map((line, lineIndex) => {
      if (!line && lineStart >= text.length) return null;
      const lineEnd = lineStart + line.length;
      const segments: ReactNode[] = [];
      let cursor = lineStart;

      for (const annotation of highlightedAnnotations) {
        const segmentStart = Math.max(annotation.start_offset, lineStart);
        const segmentEnd = Math.min(annotation.end_offset, lineEnd);
        if (segmentEnd <= segmentStart || segmentStart < cursor) continue;
        if (segmentStart > cursor) segments.push(text.slice(cursor, segmentStart));
        const annotationKey = `${annotation.id}-${lineStart}`;
        const isAnnotationOpen = activeAnnotationKey === annotationKey;
        segments.push(
          <Popover
            content={renderAnnotationNote(annotation, annotationKey)}
            destroyOnHidden
            key={annotationKey}
            onOpenChange={(visible) => {
              setActiveAnnotationKey(visible ? annotationKey : null);
              if (!visible) setDeleteConfirmationKey(null);
            }}
            open={isAnnotationOpen}
            placement="topLeft"
            trigger="click"
          >
            <mark
              className={isAnnotationOpen ? 'pdf-reader-highlight is-active' : 'pdf-reader-highlight'}
              onKeyDown={(event) => {
                if (event.key === 'Enter' || event.key === ' ') {
                  event.preventDefault();
                  setActiveAnnotationKey(annotationKey);
                }
              }}
              role="button"
              tabIndex={0}
            >
              {text.slice(segmentStart, segmentEnd)}
            </mark>
          </Popover>,
        );
        cursor = segmentEnd;
      }
      if (cursor < lineEnd) segments.push(text.slice(cursor, lineEnd));

      const lineKind = getLineKind(line);
      const renderedLine = (
        <span className={`pdf-reader-line is-${lineKind}`} key={`${lineStart}-${lineIndex}`}>
          {segments}
        </span>
      );
      lineStart = lineEnd;
      return renderedLine;
    });
  }, [activeAnnotationKey, highlightedAnnotations, renderAnnotationNote, text]);

  return (
    <section className="pdf-text-annotation-reader">
      {messageContext}
      <div className="pdf-reader-toolbar">
        <Typography.Text type="secondary">
          {t('library.annotations.selectionHint')}
        </Typography.Text>
        <Typography.Text type="secondary">
          {t('library.annotations.structuredReadingHint')}
        </Typography.Text>
      </div>
      {loading ? (
        <Spin className="pdf-reader-loading" />
      ) : !text ? (
        <Empty description={t('library.annotations.textUnavailable')} />
      ) : (
        <>
          <div
            className="pdf-reader-text"
            onKeyUp={captureSelection}
            onMouseUp={captureSelection}
            ref={readerRef}
          >
            <div className="pdf-reader-document" role="document">{renderedText}</div>
          </div>
          {pendingSelection ? (
            <div className="pdf-reader-composer">
              <div className="pdf-reader-selection">
                <HighlightOutlined />
                <Typography.Text ellipsis={{ tooltip: pendingSelection.selectedText }}>
                  {pendingSelection.selectedText}
                </Typography.Text>
              </div>
              <Input.TextArea
                autoSize={{ minRows: 2, maxRows: 5 }}
                maxLength={4000}
                onChange={(event) => setNote(event.target.value)}
                placeholder={t('library.annotations.notePlaceholder')}
                value={note}
              />
              <div className="pdf-reader-composer-actions">
                <Button icon={<CopyOutlined />} onClick={() => void copySelection()}>
                  {t('library.annotations.copySelection')}
                </Button>
                <Button onClick={() => setPendingSelection(null)}>
                  {t('common.cancel')}
                </Button>
                <Button loading={saving} onClick={() => void saveAnnotation()} type="primary">
                  {t('library.annotations.save')}
                </Button>
              </div>
            </div>
          ) : null}
        </>
      )}
    </section>
  );
}
