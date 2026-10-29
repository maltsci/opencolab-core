# Assistant Markdown Rendering Design

## Goal

Render Markdown returned by assistant responses consistently in the session and task workspace result cards, without changing stored message content or the copy action.

## Scope

- Add a shared renderer inside `ChatMessage` for assistant messages.
- Support headings, paragraphs, emphasis, ordered and unordered lists, blockquotes, tables, links, and fenced code blocks.
- Keep user messages and in-progress streaming content as plain text.
- Reuse the same renderer in the task workspace message cards.

## Safety

The renderer will not enable raw HTML. Links will use the existing browser-safe handling and open only ordinary HTTP(S) URLs. The original Markdown remains the canonical stored and copied value.

## Presentation

Assistant output will use compact typography aligned with the existing Ant Design card: clear heading hierarchy, readable list spacing, a subtle quote border, scrollable code blocks, and responsive tables. No backend schema or API change is required.

## Validation

- Add focused rendering coverage for representative Markdown.
- Run the frontend production build.
- Verify one completed Project Q&A result in the browser.
