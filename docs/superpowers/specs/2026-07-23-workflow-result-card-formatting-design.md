# Workflow Result Card Formatting Design

## Goal

Make structured workflow results readable, visually distinct, and consistently
formatted with Markdown.

## Behavior

- Assistant messages with structured workflow output do not render an empty
  chat bubble before the result card.
- Overview text, section values, and list entries in workflow result cards use
  the existing Markdown renderer.
- The result card uses a white surface, subtle border, and compact section
  spacing rather than a large tinted text block.
- Existing runtime/status tags, trace controls, workflow steps, and output
  fields remain available.

## Implementation

- Add an option to `ChatMessage` that suppresses the content bubble when the
  caller renders a child result card.
- Use that option for assistant messages with normalized workflow output.
- Extract or reuse a Markdown content renderer in `Session.tsx` for structured
  output fields, preserving safe links and GFM support.
- Replace plain `List.Item` values with Markdown-rendered content and give the
  result card and its sections a white, bordered layout.

## Validation

- Run the production frontend build in the existing frontend container.
- Verify a completed structured task has no empty top bubble and renders
  headings, lists, emphasis, inline code, and numbered items in its output.
