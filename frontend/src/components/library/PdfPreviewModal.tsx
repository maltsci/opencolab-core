import {
  DownloadOutlined,
  FileTextOutlined,
  LeftOutlined,
  RightOutlined,
  ZoomInOutlined,
  ZoomOutOutlined,
} from '@ant-design/icons';
import { Button, Empty, Modal, Space, Spin, Typography } from 'antd';
import mammoth from 'mammoth/mammoth.browser';
import { useEffect, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';

import apiClient from '../../services/api-client';
import { getSourcePreviewToken, getSourcePreviewUrl } from '../../services/source-preview';
import PdfTextAnnotationReader from './PdfTextAnnotationReader';

export interface PdfPreviewModalProps {
  inline?: boolean;
  open: boolean;
  sourceId: string | null;
  title?: string;
  fileName?: string;
  evidenceExcerpt?: string;
  pageNumber?: number | null;
  onClose: () => void;
}

const TEXT_IFRAME_EXTENSIONS = new Set(['md', 'markdown', 'txt']);
const DOCX_EXTENSIONS = new Set(['docx']);
const EXTRACTED_TEXT_EXTENSIONS = new Set(['doc']);

type PreviewMode = 'pdf' | 'iframe' | 'docx' | 'text' | 'unsupported';
type PdfViewMode = 'layout' | 'text';

function getExtension(name?: string): string {
  if (!name) return '';
  const index = name.lastIndexOf('.');
  return index >= 0 ? name.slice(index + 1).toLowerCase() : '';
}

const DOCX_CONTENT_STYLES = `
.docx-preview-content {
  height: 100%;
  overflow: auto;
  padding: 8px 16px;
  line-height: 1.7;
  word-break: break-word;
}
.docx-preview-content img { max-width: 100%; }
.docx-preview-content table {
  border-collapse: collapse;
  margin: 8px 0;
  max-width: 100%;
}
.docx-preview-content td,
.docx-preview-content th {
  border: 1px solid rgba(0, 0, 0, 0.15);
  padding: 4px 8px;
}
.docx-preview-content h1,
.docx-preview-content h2,
.docx-preview-content h3,
.docx-preview-content h4 {
  line-height: 1.4;
  margin: 12px 0 6px;
}
.docx-preview-content p { margin: 6px 0; }
`;

export default function PdfPreviewModal({
  inline = false,
  open,
  sourceId,
  title,
  fileName,
  evidenceExcerpt,
  pageNumber,
  onClose,
}: PdfPreviewModalProps) {
  const { t } = useTranslation();
  const [text, setText] = useState<string | null>(null);
  const [html, setHtml] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [resolvedName, setResolvedName] = useState<string | null>(null);
  const [iframeUrl, setIframeUrl] = useState<string | null>(null);
  const [pdfPage, setPdfPage] = useState(1);
  const [pdfPageCount, setPdfPageCount] = useState<number | null>(null);
  const [pdfZoom, setPdfZoom] = useState(100);
  const [pdfImageUrl, setPdfImageUrl] = useState<string | null>(null);
  const [pdfLoading, setPdfLoading] = useState(false);
  const [pdfLoadFailed, setPdfLoadFailed] = useState(false);
  const [pdfRetryNonce, setPdfRetryNonce] = useState(0);
  const [pdfViewMode, setPdfViewMode] = useState<PdfViewMode>('layout');
  const [downloading, setDownloading] = useState(false);
  const [downloadFailed, setDownloadFailed] = useState(false);
  const evidenceMarkerRef = useRef<HTMLElement | null>(null);

  const knownExtension = getExtension(fileName || title);
  const needsNameResolution = open && !!sourceId
    && knownExtension !== 'pdf'
    && !TEXT_IFRAME_EXTENSIONS.has(knownExtension)
    && !DOCX_EXTENSIONS.has(knownExtension)
    && !EXTRACTED_TEXT_EXTENSIONS.has(knownExtension);

  // Callers may pass a display label instead of the real file name (e.g.
  // source links in chat). Resolve the actual name to pick a preview mode.
  useEffect(() => {
    if (!needsNameResolution || !sourceId) {
      setResolvedName(null);
      return;
    }
    let cancelled = false;
    setResolvedName(null);
    apiClient
      .get<{ name?: string }>(`/sources/${sourceId}`)
      .then(({ data }) => {
        if (!cancelled) setResolvedName(data?.name || '');
      })
      .catch(() => {
        if (!cancelled) setResolvedName('');
      });
    return () => { cancelled = true; };
  }, [needsNameResolution, sourceId]);

  const extension = needsNameResolution && resolvedName
    ? getExtension(resolvedName)
    : knownExtension;
  const mode: PreviewMode = pageNumber && extension === 'pdf'
    ? 'pdf'
    : evidenceExcerpt
      ? 'text'
      : extension === 'pdf'
        ? 'pdf'
        : TEXT_IFRAME_EXTENSIONS.has(extension)
          ? 'iframe'
          : DOCX_EXTENSIONS.has(extension)
            ? 'docx'
            : EXTRACTED_TEXT_EXTENSIONS.has(extension)
              ? 'text'
              : 'unsupported';

  useEffect(() => {
    if (!open || !sourceId || (mode !== 'text' && mode !== 'docx')) {
      setText(null);
      setHtml(null);
      setLoading(false);
      return;
    }
    let cancelled = false;
    setLoading(true);
    setText(null);
    setHtml(null);
    if (mode === 'docx') {
      getSourcePreviewToken(sourceId)
        .then((token) => apiClient.get(`/sources/${sourceId}/file`, {
            params: { token },
            responseType: 'arraybuffer',
          }))
        .then(async ({ data }) => {
          const result = await mammoth.convertToHtml({ arrayBuffer: data });
          if (!cancelled) setHtml(sanitizePreviewHtml(result.value));
        })
        .catch(() => {
          if (cancelled) return;
          // Fall back to extracted plain text when conversion fails.
          getSourcePreviewToken(sourceId)
            .then((token) => apiClient
            .get(`/sources/${sourceId}/text`, {
              params: { token },
              responseType: 'text',
            }))
            .then(({ data }) => {
              if (!cancelled) setText(typeof data === 'string' ? data : String(data));
            })
            .catch(() => undefined);
        })
        .finally(() => {
          if (!cancelled) setLoading(false);
        });
    } else {
      getSourcePreviewToken(sourceId)
        .then((token) => apiClient.get(`/sources/${sourceId}/text`, {
            params: { token },
            responseType: 'text',
          }))
        .then(({ data }) => {
          if (!cancelled) setText(typeof data === 'string' ? data : String(data));
        })
        .catch(() => {
          if (!cancelled) setText(null);
        })
        .finally(() => {
          if (!cancelled) setLoading(false);
        });
    }
    return () => { cancelled = true; };
  }, [open, sourceId, mode]);

  useEffect(() => {
    if (evidenceExcerpt && text && evidenceMarkerRef.current) {
      evidenceMarkerRef.current.scrollIntoView({ block: 'center' });
    }
  }, [evidenceExcerpt, text]);

  const renderText = () => {
    if (!text) return null;
    const excerpt = evidenceExcerpt || '';
    const index = excerpt ? text.indexOf(excerpt) : -1;
    if (index < 0) return text;
    return <>{text.slice(0, index)}<mark ref={evidenceMarkerRef}>{text.slice(index, index + excerpt.length)}</mark>{text.slice(index + excerpt.length)}</>;
  };

  useEffect(() => {
    if (!open || !sourceId || mode !== 'iframe') {
      setIframeUrl(null);
      return;
    }
    let cancelled = false;
    setIframeUrl(null);
    getSourcePreviewUrl(sourceId, 'file')
      .then((url) => {
        if (!cancelled) setIframeUrl(pageNumber ? `${url}#page=${pageNumber}` : url);
      })
      .catch(() => {
        if (!cancelled) setIframeUrl(null);
      });
    return () => { cancelled = true; };
  }, [open, sourceId, mode, pageNumber]);

  useEffect(() => {
    if (!open || mode !== 'pdf') return;
    setPdfPage(Math.max(1, pageNumber || 1));
    setPdfPageCount(null);
    setPdfZoom(100);
    setPdfLoadFailed(false);
    setPdfViewMode('layout');
  }, [open, sourceId, mode, pageNumber]);

  useEffect(() => {
    if (!open || !sourceId || mode !== 'pdf' || pdfViewMode !== 'layout') {
      setPdfImageUrl(null);
      setPdfLoading(false);
      return;
    }

    let cancelled = false;
    let objectUrl: string | null = null;
    setPdfImageUrl(null);
    setPdfLoading(true);
    setPdfLoadFailed(false);

    getSourcePreviewToken(sourceId)
      .then((token) => apiClient.get<Blob>(`/sources/${sourceId}/thumbnail`, {
        params: { token, page: pdfPage },
        responseType: 'blob',
      }))
      .then((response) => {
        if (cancelled) return;
        const pageCount = Number(response.headers['x-pdf-page-count']);
        if (Number.isInteger(pageCount) && pageCount > 0) {
          setPdfPageCount(pageCount);
        }
        objectUrl = URL.createObjectURL(response.data);
        setPdfImageUrl(objectUrl);
      })
      .catch(() => {
        if (!cancelled) setPdfLoadFailed(true);
      })
      .finally(() => {
        if (!cancelled) setPdfLoading(false);
      });

    return () => {
      cancelled = true;
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [open, sourceId, mode, pdfPage, pdfRetryNonce, pdfViewMode]);

  const downloadPdf = async () => {
    if (!sourceId) return;
    setDownloading(true);
    setDownloadFailed(false);
    try {
      const url = await getSourcePreviewUrl(sourceId, 'file');
      const link = document.createElement('a');
      link.href = url;
      link.download = fileName || title || 'document.pdf';
      document.body.appendChild(link);
      link.click();
      link.remove();
    } catch {
      setDownloadFailed(true);
    } finally {
      setDownloading(false);
    }
  };

  const emptyPlaceholder = (
    <Empty description={t('library.detail.previewUnavailable')} style={{ marginTop: 80 }} />
  );
  const resolvingName = needsNameResolution && resolvedName === null;
  const pdfToolbar = (
    <div
      style={{
        alignItems: 'center',
        background: '#fff',
        borderBottom: '1px solid rgba(5, 5, 5, 0.08)',
        display: 'flex',
        justifyContent: 'space-between',
        padding: '8px 12px',
      }}
    >
      <Space>
        <Button
          onClick={() => setPdfViewMode('layout')}
          type={pdfViewMode === 'layout' ? 'primary' : 'default'}
        >
          {t('library.preview.layoutReading')}
        </Button>
        <Button
          icon={<FileTextOutlined />}
          onClick={() => setPdfViewMode('text')}
          type={pdfViewMode === 'text' ? 'primary' : 'default'}
        >
          {t('library.preview.textReading')}
        </Button>
        {pdfViewMode === 'layout' ? (
          <>
            <Button
              aria-label={t('library.preview.previousPage')}
              disabled={pdfPage <= 1 || pdfLoading}
              icon={<LeftOutlined />}
              onClick={() => setPdfPage((current) => Math.max(1, current - 1))}
            />
            <Typography.Text>
              {t('library.preview.pageOf', {
                page: pdfPage,
                total: pdfPageCount || '—',
              })}
            </Typography.Text>
            <Button
              aria-label={t('library.preview.nextPage')}
              disabled={pdfLoading || (pdfPageCount !== null && pdfPage >= pdfPageCount)}
              icon={<RightOutlined />}
              onClick={() => setPdfPage((current) => current + 1)}
            />
          </>
        ) : null}
      </Space>
      <Space>
        {pdfViewMode === 'layout' ? (
          <>
            <Button
              aria-label={t('library.preview.zoomOut')}
              disabled={pdfZoom <= 50}
              icon={<ZoomOutOutlined />}
              onClick={() => setPdfZoom((current) => Math.max(50, current - 25))}
            />
            <Typography.Text>{pdfZoom}%</Typography.Text>
            <Button
              aria-label={t('library.preview.zoomIn')}
              disabled={pdfZoom >= 200}
              icon={<ZoomInOutlined />}
              onClick={() => setPdfZoom((current) => Math.min(200, current + 25))}
            />
          </>
        ) : null}
        <Button
          icon={<DownloadOutlined />}
          loading={downloading}
          onClick={() => void downloadPdf()}
        >
          {t('library.preview.downloadOriginal')}
        </Button>
        {downloadFailed ? (
          <Typography.Text type="danger">
            {t('library.preview.downloadFailed')}
          </Typography.Text>
        ) : null}
      </Space>
    </div>
  );

  const previewContent = open && sourceId ? (
        resolvingName ? (
          <Spin spinning style={{ width: '100%', marginTop: 80 }} />
        ) : mode === 'pdf' ? (
          <div style={{ display: 'flex', flexDirection: 'column', height: '100%' }}>
            {pdfToolbar}
            {pdfViewMode === 'text' ? (
              <PdfTextAnnotationReader sourceId={sourceId} />
            ) : (
              <div
              style={{
                alignItems: pdfZoom <= 100 ? 'flex-start' : undefined,
                background: '#f0f2f5',
                display: 'flex',
                flex: 1,
                justifyContent: 'center',
                overflow: 'auto',
                padding: 16,
              }}
              >
                {pdfLoadFailed ? (
                  <Empty description={t('library.preview.loadFailed')} style={{ marginTop: 80 }}>
                    <Button onClick={() => setPdfRetryNonce((current) => current + 1)}>
                      {t('common.retry')}
                    </Button>
                  </Empty>
                ) : (
                  <Spin spinning={pdfLoading} style={{ width: '100%', marginTop: 80 }}>
                    {pdfImageUrl ? (
                      <img
                        alt={title || t('library.preview.document')}
                        src={pdfImageUrl}
                        style={{
                          display: 'block',
                          height: 'auto',
                          margin: '0 auto',
                          maxWidth: pdfZoom <= 100 ? '100%' : 'none',
                          width: `${pdfZoom}%`,
                        }}
                      />
                    ) : null}
                  </Spin>
                )}
              </div>
            )}
          </div>
        ) : mode === 'iframe' && iframeUrl ? (
          <iframe
            src={iframeUrl}
            style={{ width: '100%', height: '100%', border: 'none' }}
            title={title}
          />
        ) : (
          <Spin
            spinning={loading}
            styles={{
              root: { width: '100%', height: '100%', overflow: 'hidden' },
              container: { height: '100%', overflow: 'hidden' },
            }}
          >
            {mode === 'docx' && html ? (
              <div
                className="docx-preview-content"
                dangerouslySetInnerHTML={{ __html: html }}
              />
            ) : text ? (
              <pre
                style={{
                  margin: 0,
                  height: '100%',
                  overflow: 'auto',
                  whiteSpace: 'pre-wrap',
                  wordBreak: 'break-word',
                  fontFamily: 'inherit',
                }}
              >{renderText()}</pre>
            ) : !loading ? (
              emptyPlaceholder
            ) : null}
          </Spin>
        )
      ) : null;

  if (inline) {
    return (
      <div className="resource-inline-preview">
        <style>{DOCX_CONTENT_STYLES}</style>
        {previewContent}
      </div>
    );
  }

  return (
    <Modal
      title={title}
      open={open}
      onCancel={onClose}
      footer={null}
      width="80vw"
      style={{ top: 20 }}
      styles={{ body: { height: 'calc(90vh - 80px)', padding: mode === 'iframe' || mode === 'pdf' ? 0 : 16 } }}
      destroyOnHidden
    >
      <style>{DOCX_CONTENT_STYLES}</style>
      {previewContent}
    </Modal>
  );
}

function sanitizePreviewHtml(html: string): string {
  const template = document.createElement('template');
  template.innerHTML = html;
  const blockedTags = new Set(['script', 'style', 'iframe', 'object', 'embed', 'link', 'meta']);
  const walker = document.createTreeWalker(template.content, NodeFilter.SHOW_ELEMENT);
  const removals: Element[] = [];

  while (walker.nextNode()) {
    const element = walker.currentNode as Element;
    if (blockedTags.has(element.tagName.toLowerCase())) {
      removals.push(element);
      continue;
    }
    for (const attr of Array.from(element.attributes)) {
      const name = attr.name.toLowerCase();
      const value = attr.value.trim().toLowerCase();
      if (
        name.startsWith('on')
        || name === 'srcdoc'
        || ((name === 'href' || name === 'src') && value.startsWith('javascript:'))
      ) {
        element.removeAttribute(attr.name);
      }
    }
  }

  removals.forEach((element) => element.remove());
  return template.innerHTML;
}
