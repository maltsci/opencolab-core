# Assistant Markdown Rendering Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Render completed assistant responses as safe, readable Markdown in every OpenColab conversation card.

**Architecture:** Add `react-markdown` with `remark-gfm` and centralize rendering in `ChatMessage`, the shared conversation-card shell. User and streaming messages remain plain text. Task workspace cards reuse the same component.

**Tech Stack:** React 19, TypeScript, Ant Design 6, react-markdown, remark-gfm, Vite.

---

### Task 1: Add the safe Markdown renderer

**Files:**
- Modify: `frontend/package.json`
- Modify: `frontend/package-lock.json`
- Modify: `frontend/src/components/ui/ChatMessage.tsx`

- [ ] **Step 1: Add the rendering dependencies**

Run `cd frontend && npm install react-markdown remark-gfm`.

Expected: `package.json` and `package-lock.json` include both packages.

- [ ] **Step 2: Add explicit rendering mode**

Extend `ChatMessageProps` with `renderMarkdown?: boolean`. Import `ReactMarkdown` and `remarkGfm`. In the content container, keep the existing plain-text branch as default and add this Markdown branch:

```tsx
{renderMarkdown && typeof content === 'string'
  ? <ReactMarkdown remarkPlugins={[remarkGfm]}>{content}</ReactMarkdown>
  : content}
```

Provide renderer components for headings, paragraphs, lists, blockquotes, tables, anchors, and fenced code blocks. Use Ant Design tokens for color, add compact margins, and constrain tables/code blocks with horizontal overflow. Do not use `rehypeRaw`, `dangerouslySetInnerHTML`, or `skipHtml={false}`.

- [ ] **Step 3: Run the build**

Run `cd frontend && npm run build`.

Expected: exit code 0.

- [ ] **Step 4: Commit the renderer**

Run `git add frontend/package.json frontend/package-lock.json frontend/src/components/ui/ChatMessage.tsx && git commit -m "feat: render assistant markdown responses"`.

### Task 2: Enable completed assistant outputs

**Files:**
- Modify: `frontend/src/pages/Session.tsx:2650-2660`
- Modify: `frontend/src/pages/TaskWorkspace.tsx:1309-1330`

- [ ] **Step 1: Enable Markdown in the main session**

Add the following prop to the existing `ChatMessage` call in `Session.tsx`:

```tsx
renderMarkdown={msg.role === 'assistant' && !isRegeneratingMessage && !isRegeneratingTaskMessage}
```

- [ ] **Step 2: Reuse the shared card in task workspace**

Import `ChatMessage` in `TaskWorkspace.tsx`. Replace the `visibleTaskMessages.map` inner Card with:

```tsx
<ChatMessage
  id={`task-message-${item.id}`}
  role={item.role === 'assistant' ? 'assistant' : 'user'}
  content={item.content}
  renderMarkdown={item.role === 'assistant'}
  timestamp={new Date(item.created_at).toLocaleString(
    i18n.language === 'zh-CN' ? 'zh-CN' : 'en-US',
  )}
/>
```

Keep the enclosing result metadata and empty state unchanged.

- [ ] **Step 3: Build and smoke-test**

Run `cd frontend && npm run build`.

In a completed Project Q&A response, verify headings, bold text, lists, quote blocks, tables, and fenced code blocks render visually; verify “复制” keeps copying the original Markdown.

- [ ] **Step 4: Commit the integration**

Run `git add frontend/src/pages/Session.tsx frontend/src/pages/TaskWorkspace.tsx && git commit -m "feat: format assistant answers in task views"`.

### Task 3: Final safety verification

**Files:**
- Verify: `frontend/src/components/ui/ChatMessage.tsx`
- Verify: `frontend/src/pages/Session.tsx`
- Verify: `frontend/src/pages/TaskWorkspace.tsx`

- [ ] **Step 1: Check for unsafe HTML support**

Run `rg -n "skipHtml=\{false\}|rehypeRaw|dangerouslySetInnerHTML" frontend/src/components/ui/ChatMessage.tsx frontend/src/pages/Session.tsx frontend/src/pages/TaskWorkspace.tsx`.

Expected: no matches.

- [ ] **Step 2: Re-run the production build**

Run `cd frontend && npm run build`.

Expected: exit code 0 (the existing chunk-size warning is acceptable).
