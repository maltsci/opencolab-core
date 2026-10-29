# Session Task Prompt Sync Design

## Goal

Keep the session composer prompt aligned with the recommended task selected by
the user.

## Behavior

- Selecting any recommended task replaces the composer value with that task's
  first starter prompt.
- The replacement occurs even when the user has typed or edited content.
- A task without a starter prompt clears the composer value.
- Sending behavior and task execution remain unchanged.

## Implementation

- Update `startTaskFromCurrentSession` in `frontend/src/pages/Session.tsx`.
- Set the selected task, then set the composer value from
  `task.starter_prompts[0] ?? ''`.
- No API, persistence, or translation changes are required.

## Validation

- Run the production frontend build in the existing frontend container.
- Manually verify that clicking each recommended task replaces the current
  composer content with the corresponding starter prompt.
