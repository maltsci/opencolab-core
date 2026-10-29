# Project Q&A Query Retrieval Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Use the Project Q&A goal to retrieve relevant authorized document passages for Codex.

**Architecture:** Add an optional query to `build_research_execution_context`; when supplied, it calls the existing `_rag_chunks` retrieval path after source authorization instead of selecting chunks by index. `execute_project_qa_run` passes the user goal and persists retrieval metadata in the existing context manifest.

**Tech Stack:** FastAPI, SQLAlchemy async, existing Qdrant RAG service, pytest.

---

### Task 1: Query-aware Project Q&A context

**Files:**
- Modify: `backend/app/services/research_context.py`
- Modify: `backend/app/services/orchestration_service.py`
- Modify: `tests/test_orchestration_runs.py`

- [ ] **Step 1: Write a failing retrieval test**

Create one source with an abstract chunk and a later method/result chunk. Patch the existing RAG retrieval helper to return the later chunk for `"experimental model"`. Assert `build_orchestration_context(query="experimental model")` returns the later chunk rather than chunk index zero.

- [ ] **Step 2: Verify RED**

Run `backend/.venv/bin/pytest tests/test_orchestration_runs.py::test_project_qa_context_retrieves_query_relevant_chunks -q`.

Expected: FAIL because the current implementation ignores the query and orders by chunk index.

- [ ] **Step 3: Implement query retrieval**

Add `query: str | None = None` to `build_research_execution_context`. When it is non-empty, call the existing `_rag_chunks(query, authorized_source_ids, db, max_chunks)` and hydrate each returned chunk with its source name. Keep the current ordered selection as the no-query fallback. Pass `goal` from `execute_project_qa_run` and add `retrieval_mode: "query"` plus selected scores to the safe run manifest.

- [ ] **Step 4: Verify GREEN**

Run the Step 2 command. Expected: PASS.

- [ ] **Step 5: Run focused regression tests**

Run `backend/.venv/bin/pytest tests/test_orchestration_runs.py tests/test_research_assets.py -q`.

Expected: PASS.

- [ ] **Step 6: Commit**

Run `git add backend/app/services/research_context.py backend/app/services/orchestration_service.py tests/test_orchestration_runs.py && git commit -m "feat: retrieve project qa context by query"`.

### Task 2: Verify an answer uses body evidence

**Files:**
- Verify: `backend/app/services/orchestration_service.py`
- Verify: `tests/test_orchestration_runs.py`

- [ ] **Step 1: Assert persisted manifest evidence**

Extend the Project Q&A run test to assert the manifest has `retrieval_mode == "query"` and contains the method/result chunk ID but not raw chunk text.

- [ ] **Step 2: Run the focused test**

Run `backend/.venv/bin/pytest tests/test_orchestration_runs.py -q`.

Expected: PASS.
