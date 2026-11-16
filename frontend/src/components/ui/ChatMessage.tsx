import { MoreOutlined, RobotOutlined, UserOutlined } from '@ant-design/icons';
import { Button, Dropdown, Typography, theme } from 'antd';
import { memo, type ReactNode } from 'react';
import { useTranslation } from 'react-i18next';
import 'katex/dist/katex.min.css';
import ReactMarkdown, { defaultUrlTransform } from 'react-markdown';
import rehypeKatex from 'rehype-katex';
import remarkGfm from 'remark-gfm';
import remarkMath from 'remark-math';

export interface ChatMessageAction {
  key: string;
  label: string;
  icon?: ReactNode;
  danger?: boolean;
  onClick: () => void;
}

export type SourceClickHandler = (sourceId: string, label?: string) => void;

interface ChatMessageProps {
  id?: string;
  role: 'user' | 'assistant';
  content: ReactNode;
  renderMarkdown?: boolean;
  timestamp?: string;
  actions?: ChatMessageAction[];
  children?: ReactNode;
  selected?: boolean;
  hideContentBubble?: boolean;
  onSourceClick?: SourceClickHandler;
}

function getSafeLinkHref(href?: string): string | undefined {
  if (!href) return undefined;

  try {
    const url = new URL(href, 'https://opencolab.local');
    return url.protocol === 'http:' || url.protocol === 'https:' ? href : undefined;
  } catch {
    return undefined;
  }
}

function cleanTrailingLatexFragment(mathText: string): string {
  // Trim trailing whitespace first so "$" matches truncated tokens like "\sigma_{\"
  let cleaned = mathText
    .trimEnd()
    .replace(/\\[a-zA-Z]+[_^]?\{[^}]*$/, '')
    .replace(/[_^]\{[^}]*$/, '')
    .replace(/\\[a-zA-Z]*$/, '')
    .replace(/[,;\\]+$/, '')
    .trimEnd();
  const opens = (cleaned.match(/\{/g) || []).length;
  const closes = (cleaned.match(/\}/g) || []).length;
  if (opens > closes) {
    cleaned += '}'.repeat(opens - closes);
  }
  return cleaned;
}

function sanitizeUnclosedMath(content: string): string {
  // Unwrap backticks around $...$ / $$...$$ and convert \[...\] delimiters
  let out = content
    .replace(/`(\$\$[\s\S]*?\$\$|\$[^$\n]+\$)`/g, '$1')
    .replace(/\\\[([\s\S]*?)\\\]/g, (_, inner: string) => `$$${inner}$$`);

  // Close an unclosed \[ if a markdown heading or EOF follows
  const openBracketIdx = out.lastIndexOf('\\[');
  if (openBracketIdx !== -1 && out.indexOf('\\]', openBracketIdx) === -1) {
    const before = out.slice(0, openBracketIdx);
    const after = out.slice(openBracketIdx + 2);
    const headingMatch = after.match(/\n(#{1,6}\s)/);
    const trimmed = cleanTrailingLatexFragment(after).trim().replace(/\n{2,}/g, '\n');
    if (headingMatch && headingMatch.index !== undefined) {
      const mathPart = cleanTrailingLatexFragment(after.slice(0, headingMatch.index)).trim().replace(/\n{2,}/g, '\n');
      const rest = after.slice(headingMatch.index);
      out = `${before}$$\n${mathPart}\n$$${rest}`;
    } else {
      out = `${before}$$\n${trimmed}\n$$`;
    }
  }

  // Close an odd number of $$ blocks before any subsequent markdown heading or EOF
  const parts = out.split('$$');
  if (parts.length % 2 === 0) {
    const prefix = parts.slice(0, -1).join('$$');
    const tail = parts[parts.length - 1];
    const headingMatch = tail.match(/\n(#{1,6}\s)/);
    if (headingMatch && headingMatch.index !== undefined) {
      const mathPart = cleanTrailingLatexFragment(tail.slice(0, headingMatch.index)).trim().replace(/\n{2,}/g, '\n');
      const rest = tail.slice(headingMatch.index);
      out = `${prefix}$$\n${mathPart}\n$$${rest}`;
    } else {
      const mathPart = cleanTrailingLatexFragment(tail).trim().replace(/\n{2,}/g, '\n');
      out = `${prefix}$$\n${mathPart}\n$$`;
    }
  }

  // Also ensure any existing $$...$$ block has balanced braces, no blank lines, and no backticks so KaTeX renders cleanly
  out = out.replace(/\$\$([\s\S]*?)\$\$/g, (_, inner: string) => {
    const fixed = cleanTrailingLatexFragment(inner.replace(/`/g, '')).trim().replace(/\n{2,}/g, '\n');
    return `$$\n${fixed}\n$$`;
  });

  return out;
}

function formatReferencesSection(content: string): string {
  const hasCjk = /[\u4e00-\u9fff]/.test(content);
  // Ensure inline "[Doc_1_Page_1] ... [Doc_2_Page_1] ..." citations render as separate list items
  return content.replace(
    /(#{1,6}\s*(?:[56]\.\s*)?(?:References|参考文献)[^\n]*\n)([\s\S]*)$/i,
    (_, heading: string, body: string) => {
      const normalizedHeading = hasCjk
        ? heading.replace(/References(?:\s*\([^)]*\))?/i, '参考文献')
        : heading;
      const formattedBody = body
        .replace(/\s+(?=\[(?:Doc|Scholar|Exp)_[^\]]+\])/g, '\n')
        .split('\n')
        .map((line) => {
          const trimmed = line.trim();
          if (!trimmed) return '';
          if (/^[-*]\s/.test(trimmed)) return trimmed;
          if (/^\[(?:Doc|Scholar|Exp)_[^\]]+\]/.test(trimmed)) {
            return `- ${trimmed.replace(/^(\[[^\]]+\])/, '**$1**')}`;
          }
          return trimmed;
        })
        .filter(Boolean)
        .join('\n');
      return `${normalizedHeading}\n${formattedBody}\n`;
    },
  );
}

function normalizeMarkdownContent(content: string): string {
  return formatReferencesSection(sanitizeUnclosedMath(content))
    .replace(/([：:])\s*(\d+)）/g, '$1\n\n$2. ')
    .replace(/([。；;])\s*(\d+)）/g, '$1\n\n$2. ');
}

const SOURCE_REFERENCE_PATTERN = /(?<!\])([(\(（])source:\s*([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})([)\)）])/gi;

function linkifySourceReferences(content: string, label: string): string {
  return content.replace(SOURCE_REFERENCE_PATTERN, `$1[${label}](source://$2)$3`);
}

function markdownUrlTransform(url: string): string {
  return url.startsWith('source:') ? url : defaultUrlTransform(url);
}

export const MarkdownContent = memo(function MarkdownContent({
  content,
  onSourceClick,
}: {
  content: string;
  onSourceClick?: SourceClickHandler;
}) {
  const { token } = theme.useToken();
  const { t } = useTranslation();
  const sourceLinkLabel = t('chat.viewSource');
  const normalizedContent = linkifySourceReferences(
    normalizeMarkdownContent(content),
    sourceLinkLabel,
  );

  return (
    <ReactMarkdown
      remarkPlugins={[remarkGfm, remarkMath]}
      rehypePlugins={[rehypeKatex]}
      urlTransform={markdownUrlTransform}
      components={{
        h1: ({ children: headingChildren }) => (
          <Typography.Title level={2} style={{ margin: '0 0 12px', fontSize: 22 }}>
            {headingChildren}
          </Typography.Title>
        ),
        h2: ({ children: headingChildren }) => (
          <Typography.Title level={3} style={{ margin: '18px 0 10px', fontSize: 18 }}>
            {headingChildren}
          </Typography.Title>
        ),
        h3: ({ children: headingChildren }) => (
          <Typography.Title level={4} style={{ margin: '16px 0 8px', fontSize: 16 }}>
            {headingChildren}
          </Typography.Title>
        ),
        p: ({ children: paragraphChildren }) => (
          <p style={{ margin: '0 0 10px', lineHeight: 1.7 }}>{paragraphChildren}</p>
        ),
        ul: ({ children: listChildren }) => (
          <ul style={{ margin: '0 0 10px', paddingInlineStart: 22 }}>{listChildren}</ul>
        ),
        ol: ({ children: listChildren }) => (
          <ol style={{ margin: '0 0 10px', paddingInlineStart: 22 }}>{listChildren}</ol>
        ),
        li: ({ children: listItemChildren }) => (
          <li style={{ marginBottom: 4, lineHeight: 1.65 }}>{listItemChildren}</li>
        ),
        blockquote: ({ children: quoteChildren }) => (
          <blockquote
            style={{
              margin: '12px 0',
              padding: '8px 12px',
              borderInlineStart: `3px solid ${token.colorPrimaryBorder}`,
              background: token.colorBgContainer,
              color: token.colorTextSecondary,
            }}
          >
            {quoteChildren}
          </blockquote>
        ),
        table: ({ children: tableChildren }) => (
          <div style={{ overflowX: 'auto', marginBottom: 12 }}>
            <table style={{ width: '100%', borderCollapse: 'collapse', minWidth: 360 }}>
              {tableChildren}
            </table>
          </div>
        ),
        th: ({ children: cellChildren }) => (
          <th
            style={{
              padding: '8px 10px',
              border: `1px solid ${token.colorBorderSecondary}`,
              background: token.colorFillSecondary,
              textAlign: 'left',
            }}
          >
            {cellChildren}
          </th>
        ),
        td: ({ children: cellChildren }) => (
          <td style={{ padding: '8px 10px', border: `1px solid ${token.colorBorderSecondary}` }}>
            {cellChildren}
          </td>
        ),
        pre: ({ children: codeChildren }) => (
          <pre
            style={{
              margin: '12px 0',
              padding: 12,
              overflowX: 'auto',
              borderRadius: token.borderRadius,
              background: token.colorBgContainer,
              color: token.colorText,
            }}
          >
            {codeChildren}
          </pre>
        ),
        code: ({ children: codeChildren }) => (
          <code
            style={{
              padding: '1px 4px',
              borderRadius: token.borderRadiusSM,
              background: token.colorFillSecondary,
              color: token.colorText,
              fontFamily: 'ui-monospace, SFMono-Regular, Menlo, monospace',
            }}
          >
            {codeChildren}
          </code>
        ),
        a: ({ href, children: linkChildren }) => {
          const sourceMatch = href?.match(/^source:(?:\/\/)?([0-9a-fA-F-]{36})$/);
          if (sourceMatch && onSourceClick) {
            const label =
              typeof linkChildren === 'string' && linkChildren !== sourceLinkLabel
                ? linkChildren
                : undefined;
            return (
              <a
                href="#"
                onClick={(event) => {
                  event.preventDefault();
                  onSourceClick(sourceMatch[1], label);
                }}
              >
                {linkChildren}
              </a>
            );
          }
          const safeHref = getSafeLinkHref(href);
          return safeHref ? (
            <a href={safeHref} target="_blank" rel="noreferrer">
              {linkChildren}
            </a>
          ) : <span>{linkChildren}</span>;
        },
      }}
    >
      {normalizedContent}
    </ReactMarkdown>
  );
});

export default memo(function ChatMessage({
  id,
  role,
  content,
  renderMarkdown = false,
  timestamp,
  actions,
  children,
  selected,
  hideContentBubble = false,
  onSourceClick,
}: ChatMessageProps) {
  const { token } = theme.useToken();
  const { t } = useTranslation();
  const isUser = role === 'user';

  return (
    <div
      id={id}
      style={{
        display: 'flex',
        justifyContent: isUser ? 'flex-end' : 'flex-start',
        marginBottom: 16,
        padding: selected ? 12 : 0,
        margin: selected ? -12 : 0,
        borderRadius: token.borderRadiusLG,
        background: selected ? token.colorPrimaryBg : undefined,
        boxShadow: selected ? `0 0 0 1px ${token.colorPrimaryBorder} inset` : undefined,
        transition: 'background 0.2s ease, box-shadow 0.2s ease',
      }}
    >
      <div style={{ display: 'flex', gap: 12, maxWidth: '80%', flexDirection: isUser ? 'row-reverse' : 'row' }}>
        <div
          style={{
            width: 32,
            height: 32,
            borderRadius: '50%',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            flexShrink: 0,
            background: isUser ? token.colorPrimary : token.colorFillTertiary,
            color: isUser ? token.colorWhite : token.colorText,
          }}
        >
          {isUser ? <UserOutlined /> : <RobotOutlined />}
        </div>
        <div style={{ minWidth: 0 }}>
          {timestamp || actions?.length ? (
            <div
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: 8,
                marginBottom: 4,
                justifyContent: isUser ? 'flex-end' : 'flex-start',
              }}
            >
              {timestamp ? (
                <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                  {timestamp}
                </Typography.Text>
              ) : null}
              {actions?.length ? (
                <Dropdown
                  menu={{
                    items: actions.map((action) => ({
                      key: action.key,
                      label: action.label,
                      icon: action.icon,
                      danger: action.danger,
                      onClick: action.onClick,
                    })),
                  }}
                  trigger={['click']}
                  placement="bottomRight"
                >
                  <Button
                    type="text"
                    size="small"
                    icon={<MoreOutlined />}
                    aria-label={t('common.actions')}
                    style={{ padding: '0 4px' }}
                  />
                </Dropdown>
              ) : null}
            </div>
          ) : null}
          {!hideContentBubble && (
            <div
              style={{
                padding: '10px 14px',
                borderRadius: token.borderRadius * 1.5,
                background: isUser ? token.colorPrimary : token.colorFillTertiary,
                color: isUser ? token.colorWhite : token.colorText,
                wordBreak: 'break-word',
              }}
            >
              {renderMarkdown && typeof content === 'string' ? (
                <MarkdownContent content={content} onSourceClick={onSourceClick} />
              ) : (
                <span style={{ whiteSpace: 'pre-wrap' }}>{content}</span>
              )}
            </div>
          )}
          {children ? <div style={{ marginTop: 12 }}>{children}</div> : null}
        </div>
      </div>
    </div>
  );
}, chatMessagePropsEqual);

// Compare actions by their rendered menu fields only. The onClick closures are
// rebuilt by the parent on every render, but they only capture per-message data
// that is already covered by the other comparisons, so treating equal-looking
// action lists as equal does not go stale in a user-visible way.
function chatMessageActionsEqual(
  prev?: ChatMessageAction[],
  next?: ChatMessageAction[],
): boolean {
  if (prev === next) return true;
  if (!prev || !next || prev.length !== next.length) return false;
  return prev.every((action, index) => {
    const other = next[index];
    return (
      action.key === other.key
      && action.label === other.label
      && action.danger === other.danger
    );
  });
}

// Custom equality so historical messages skip re-rendering on every streamed
// token: primitive props are compared by value, and unstable props rebuilt by
// the parent (actions, onSourceClick, children) are handled explicitly.
// `children` is null for plain messages, so those remain referentially stable;
// messages with workflow/agent extras still re-render, but the memoized
// MarkdownContent inside them blocks the expensive markdown re-parse.
function chatMessagePropsEqual(prev: ChatMessageProps, next: ChatMessageProps): boolean {
  return (
    prev.id === next.id
    && prev.role === next.role
    && prev.content === next.content
    && prev.renderMarkdown === next.renderMarkdown
    && prev.timestamp === next.timestamp
    && prev.selected === next.selected
    && prev.hideContentBubble === next.hideContentBubble
    && prev.children === next.children
    && prev.onSourceClick === next.onSourceClick
    && chatMessageActionsEqual(prev.actions, next.actions)
  );
}
