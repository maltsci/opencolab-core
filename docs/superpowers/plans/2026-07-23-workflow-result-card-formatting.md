# Workflow Result Card Formatting Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Render structured workflow results as readable Markdown cards without an empty message bubble.

**Architecture:** Add a `hideContentBubble` option to `ChatMessage` so child-only task results do not reserve an empty bubble. Export a reusable Markdown body from the chat-message component and use it in workflow output sections in `Session.tsx`, keeping the existing safe-link and GFM behavior consistent.

**Tech Stack:** React, TypeScript, Ant Design, react-markdown, remark-gfm.

---

### Task 1: Make the chat Markdown renderer reusable and suppress empty workflow bubbles

**Files:**
- Modify: `frontend/src/components/ui/ChatMessage.tsx:15-212`
- Test: production frontend build

- [ ] **Step 1: Add a `hideContentBubble` prop**

```ts
interface ChatMessageProps {
  // existing props
  hideContentBubble?: boolean;
}
```

- [ ] **Step 2: Render the padded chat content only when the prop is false**

```tsx
{!hideContentBubble && (
  <div style={{ padding: '10px 14px', borderRadius: token.borderRadius * 1.5 }}>
    {/* existing Markdown or text content */}
  </div>
)}
```

- [ ] **Step 3: Extract the existing `ReactMarkdown` configuration into an exported `MarkdownContent` component**

```tsx
export function MarkdownContent({ content }: { content: string }) {
  const { token } = theme.useToken();
  return <ReactMarkdown remarkPlugins={[remarkGfm]}>{content}</ReactMarkdown>;
}
```

Preserve the existing headings, lists, tables, inline code, blockquotes, and safe-link component mappings inside the extracted component.

### Task 2: Render workflow output as a white Markdown result card

**Files:**
- Modify: `frontend/src/pages/Session.tsx:32, 2678-2815`
- Test: production frontend build

- [ ] **Step 1: Import `MarkdownContent` and pass `hideContentBubble` for structured workflow output**

```tsx
import ChatMessage, { MarkdownContent, type ChatMessageAction } from '../components/ui/ChatMessage';

<ChatMessage
  // existing props
  hideContentBubble={msg.role === 'assistant' && hasWorkflowOutput}
>
```

- [ ] **Step 2: Add a shared white result-card container**

```tsx
<div
  style={{
    display: 'flex',
    flexDirection: 'column',
    gap: 16,
    padding: 16,
    border: `1px solid ${token.colorBorderSecondary}`,
    borderRadius: token.borderRadiusLG,
    background: token.colorBgContainer,
  }}
>
```

- [ ] **Step 3: Replace plain structured output text with `MarkdownContent`**

```tsx
<MarkdownContent content={normalizedWorkflowOutput.overview} />
```

For each list field, replace the plain list item content with:

```tsx
<List.Item style={{ padding: '6px 0' }}>
  <MarkdownContent content={item} />
</List.Item>
```

Apply the same rendering to raw sections and validation notes.

- [ ] **Step 4: Run the production frontend build**

Run: `docker compose exec -T frontend npm run build`

Expected: Vite production build completes successfully; the existing chunk-size warning is acceptable.

- [ ] **Step 5: Commit the implementation**

```bash
git add frontend/src/components/ui/ChatMessage.tsx frontend/src/pages/Session.tsx
git commit -m "feat: format workflow result cards"
```
