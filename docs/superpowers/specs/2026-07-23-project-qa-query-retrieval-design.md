# Project Q&A Query Retrieval Design

## Goal

Select Project Q&A context from authorized document passages that are relevant to the user question rather than always sending the first document chunks.

## Retrieval Policy

After the existing project-source authorization checks, Project Q&A passes the user goal and authorized source IDs to the existing RAG retrieval service. Specific questions receive the top relevant body passages. Overview questions retain a small amount of front matter per document as background. If vector retrieval returns no passages, the runtime falls back to the current front-matter selection and records that fallback.

## Traceability

The orchestration context manifest records the selected source IDs, chunk IDs, document names, retrieval scores where available, and whether fallback was used. It never stores raw document text.

## Safety and Compatibility

The change uses only already-authorized source IDs and the existing vector store. It does not change access policies, data-sharing rules, or raw-document handling.

## Validation

- A service test creates distinct abstract and method/result passages, then verifies a specific query selects the method/result passage.
- An overview-query test verifies front matter is retained.
- Project Q&A API tests and the frontend production build pass.
