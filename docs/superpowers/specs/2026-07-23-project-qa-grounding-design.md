# Project Q&A Grounding Design

## Goal

Ensure Project Q&A answers only from its authorized project context and makes the document basis visible on each result.

## Runtime Instruction

The Project Q&A prompt will require the sandbox to identify the supplied project documents, answer only from their excerpts and project memory, and distinguish supported conclusions from unavailable evidence. It must not assume a repository, README, file path, or external document exists.

## Result Evidence

The persisted run manifest already records source and chunk IDs. The result card will expose a compact evidence summary with the document count, chunk count, and resolved document names. It will state when no searchable project document was supplied.

## Safety and Compatibility

The change does not alter source authorization, retrieval limits, stored message content, or the Codex runtime protocol. Document names and counts are metadata only; raw document text remains inside the existing controlled runtime context.

## Validation

- Service test asserts the Project Q&A prompt contains the grounding instruction and source names.
- Frontend production build passes.
- A Project Q&A run shows the evidence summary beside the answer.
