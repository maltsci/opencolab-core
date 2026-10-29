# Orchestrator Gateway and Runtime Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a run-scoped Tool Gateway, administratively governed MCP registrations, auditable tool invocations, and resumable Codex Sandbox events.

**Architecture:** The backend issues an opaque short-lived run token and makes the Tool Gateway the only capability surface visible to Codex. The Gateway validates task policy and dispatches adapters; the Sandbox streams structured events and returns a pause/resume identity. No credentials or raw PDF data are passed to Codex.

**Tech Stack:** FastAPI, SQLAlchemy async ORM, httpx, Pydantic v2, Codex CLI Sandbox, pytest/pytest-asyncio.

---

## File Structure

- Create: `backend/app/models/mcp_server.py` — registered MCP server metadata.
- Create: `backend/app/models/tool_invocation.py` — tool audit records.
- Create: `backend/app/schemas/mcp_server.py` and `backend/app/schemas/tool_gateway.py`.
- Create: `backend/app/services/tool_gateway_service.py` — token, policy, adapters, redaction, approval.
- Create: `backend/app/api/mcp_servers.py`, `backend/app/api/tool_gateway.py`, and `backend/app/api/orchestration_events.py`.
- Modify: `backend/app/services/codex_runtime.py` and `codex-sandbox/server.py` — start/resume and event protocol.
- Modify: `backend/app/schemas/task.py`, `backend/app/models/task_definition.py`, `backend/app/services/task_service.py`, and admin task API/UI contracts — add task policies.
- Create: `backend/alembic/versions/q8r9s0t1u2v3_add_tool_gateway_models.py`.
- Test: `tests/test_tool_gateway.py`, `tests/test_codex_sandbox_server.py`, and `tests/test_orchestration_runs.py`.

### Task 1: Add task capability, orchestration, and output contracts

**Files:**
- Modify: `backend/app/models/task_definition.py`
- Modify: `backend/app/schemas/task.py`
- Modify: `backend/app/services/task_service.py`
- Create: `backend/alembic/versions/q8r9s0t1u2v3_add_tool_gateway_models.py`
- Modify: `tests/test_tasks_api.py`

- [ ] **Step 1: Write the failing task API test**

```python
async def test_task_definition_exposes_orchestration_policy(client, admin_headers):
    response = await client.post(
        "/api/v1/admin/tasks",
        headers=admin_headers,
        json={
            "id": "codex-qa",
            "name": "Codex Q&A",
            "description": "Answer project questions.",
            "workflow_id": "literature_synthesizer",
            "capabilities": {"skills": ["rag-retrieve"], "mcp_tools": []},
            "orchestration_policy": {"runtime": "codex", "max_tool_calls": 4},
            "output_contract": {"artifact_type": "answer", "citation_required": True},
        },
    )
    assert response.status_code == 201
    assert response.json()["orchestration_policy"]["runtime"] == "codex"
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `pytest tests/test_tasks_api.py::test_task_definition_exposes_orchestration_policy -v`

Expected: FAIL because the schema rejects the fields.

- [ ] **Step 3: Add JSON fields and defaults**

Add `capabilities`, `orchestration_policy`, and `output_contract` JSON columns with `{}` server defaults. Add optional fields to create/update schemas and default empty dictionaries in the record-to-schema conversion. Seed the three MVP task definitions with exact contracts:

```python
"project-qa": {"artifact_type": "answer", "citation_required": True},
"literature-synthesis": {"artifact_type": "report", "required_sections": ["overview", "evidence", "contradictions", "gaps"]},
"research-document-draft": {"artifact_type": "document", "content_format": "markdown", "citation_required": True},
```

- [ ] **Step 4: Run focused tests**

Run: `pytest tests/test_tasks_api.py -v`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/models/task_definition.py backend/app/schemas/task.py backend/app/services/task_service.py backend/alembic/versions/q8r9s0t1u2v3_add_tool_gateway_models.py tests/test_tasks_api.py
git commit -m "feat: add task orchestration policies"
```

### Task 2: Add MCP registration and tool-invocation persistence

**Files:**
- Create: `backend/app/models/mcp_server.py`
- Create: `backend/app/models/tool_invocation.py`
- Modify: `backend/app/models/__init__.py`
- Create: `backend/app/schemas/mcp_server.py`
- Modify: `backend/alembic/versions/q8r9s0t1u2v3_add_tool_gateway_models.py`
- Create: `tests/test_tool_gateway.py`

- [ ] **Step 1: Write failing persistence tests**

```python
async def test_tool_invocation_tracks_redacted_payload(db, orchestration_run):
    invocation = ToolInvocation(
        orchestration_run_id=orchestration_run.id,
        sequence=1,
        capability_namespace="mcp",
        capability_id="local-literature.search",
        risk_level="local_read",
        status="pending",
        request_payload={"query": "enzyme", "api_key": "[REDACTED]"},
    )
    db.add(invocation)
    await db.commit()
    assert invocation.request_payload["api_key"] == "[REDACTED]"
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `pytest tests/test_tool_gateway.py::test_tool_invocation_tracks_redacted_payload -v`

Expected: FAIL because `ToolInvocation` does not exist.

- [ ] **Step 3: Implement models and migration**

Define `McpServer` with unique `id`, `name`, `transport`, `endpoint`, encrypted config, `network_classification` (`local` or `remote`), `tool_schemas`, `is_enabled`, creator, and timestamps. Define `ToolInvocation` with a foreign key to `orchestration_runs`, unique `(orchestration_run_id, sequence)`, capability fields, risk/status, redacted request/result JSON, approval fields, safe errors, and timestamps. Add indexes on run, status, and capability ID.

- [ ] **Step 4: Run persistence tests**

Run: `pytest tests/test_tool_gateway.py -v`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/models/mcp_server.py backend/app/models/tool_invocation.py backend/app/models/__init__.py backend/app/schemas/mcp_server.py backend/alembic/versions/q8r9s0t1u2v3_add_tool_gateway_models.py tests/test_tool_gateway.py
git commit -m "feat: add governed tool models"
```

### Task 3: Implement run-scoped Tool Gateway policy enforcement

**Files:**
- Create: `backend/app/services/tool_gateway_service.py`
- Create: `backend/app/schemas/tool_gateway.py`
- Create: `backend/app/api/tool_gateway.py`
- Modify: `tests/test_tool_gateway.py`

- [ ] **Step 1: Write failing policy tests**

```python
async def test_gateway_rejects_unlisted_capability(db, orchestration_run, task_policy):
    with pytest.raises(ToolGatewayDeniedError, match="Capability is not allowed"):
        await invoke_tool_gateway(
            run=orchestration_run,
            capability_id="remote-web.search",
            arguments={"query": "x"},
            db=db,
        )

async def test_gateway_marks_remote_call_waiting_for_approval(db, remote_mcp_run):
    result = await invoke_tool_gateway(
        run=remote_mcp_run,
        capability_id="remote-literature.search",
        arguments={"query": "x"},
        db=db,
    )
    assert result.status == "approval_required"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_tool_gateway.py -k "unlisted or remote" -v`

Expected: FAIL because the service does not exist.

- [ ] **Step 3: Implement the gateway service**

Implement `issue_run_tool_token`, `verify_run_tool_token`, `list_allowed_tools`, `invoke_tool_gateway`, and `resolve_tool_approval`. Use an opaque random token hashed in `OrchestrationRun`; bind it to one run and expiry. Apply these rules before adapter execution:

```python
AUTO_RISK_LEVELS = {"project_read", "local_read", "draft_write"}
APPROVAL_RISK_LEVELS = {"remote_read", "publish_write", "memory_write"}
```

Reject unlisted capabilities and disabled/remote tools in offline mode. Redact keys named `api_key`, `authorization`, `token`, `password`, and `secret` recursively before persistence. Dispatch project retrieval to existing RAG services and fixed workflows through their existing service entry points; do not call a database or MCP server directly from Codex.

- [ ] **Step 4: Add authenticated gateway routes**

Add:

```text
GET  /orchestration-runs/{run_id}/tool-manifest
POST /tool-gateway/invoke
POST /orchestration-runs/{run_id}/tool-invocations/{invocation_id}/approval
```

The invoke route authenticates with the run token; the approval route authenticates the human user and transitions a waiting run back to `running` only after a valid decision.

- [ ] **Step 5: Run gateway tests**

Run: `pytest tests/test_tool_gateway.py tests/test_orchestration_runs.py -v`

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/tool_gateway_service.py backend/app/schemas/tool_gateway.py backend/app/api/tool_gateway.py tests/test_tool_gateway.py tests/test_orchestration_runs.py
git commit -m "feat: enforce orchestrator tool policies"
```

### Task 4: Add administrator MCP registration APIs

**Files:**
- Create: `backend/app/api/mcp_servers.py`
- Modify: `backend/app/main.py`
- Modify: `backend/app/api/__init__.py`
- Modify: `tests/test_tool_gateway.py`

- [ ] **Step 1: Write failing admin authorization tests**

```python
async def test_admin_can_create_local_mcp_server(client, admin_headers):
    response = await client.post(
        "/api/v1/admin/mcp-servers",
        headers=admin_headers,
        json={"id": "local-literature", "name": "Local Literature", "transport": "http", "endpoint": "http://localhost:9000", "network_classification": "local", "tool_schemas": []},
    )
    assert response.status_code == 201

async def test_researcher_cannot_create_mcp_server(client, researcher_headers):
    response = await client.post("/api/v1/admin/mcp-servers", headers=researcher_headers, json={})
    assert response.status_code == 403
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_tool_gateway.py -k "mcp_server" -v`

Expected: FAIL with 404.

- [ ] **Step 3: Implement CRUD routes**

Use the existing admin role dependency and encrypted-config service patterns. Provide create/list/update/disable endpoints under `/admin/mcp-servers`. Validate that remote endpoints are not usable when offline mode is enabled; never return encrypted configuration in responses.

- [ ] **Step 4: Run focused tests**

Run: `pytest tests/test_tool_gateway.py -k "mcp_server" -v`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/api/mcp_servers.py backend/app/api/__init__.py backend/app/main.py tests/test_tool_gateway.py
git commit -m "feat: add mcp server administration"
```

### Task 5: Upgrade Codex runtime to stream and resume governed runs

**Files:**
- Modify: `codex-sandbox/server.py`
- Modify: `backend/app/services/codex_runtime.py`
- Create: `backend/app/api/orchestration_events.py`
- Modify: `tests/test_codex_sandbox_server.py`
- Modify: `tests/test_orchestration_runs.py`

- [ ] **Step 1: Write failing Sandbox protocol tests**

```python
def test_sandbox_pause_envelope_contains_resume_identity(client):
    response = client.post("/run", json={"prompt": "Need approval", "tool_manifest": [], "run_id": "run-1"})
    assert response.status_code == 200
    assert response.json()["status"] == "paused"
    assert response.json()["sandbox_session_id"]
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `pytest tests/test_codex_sandbox_server.py::test_sandbox_pause_envelope_contains_resume_identity -v`

Expected: FAIL because `/run` has no governed event envelope.

- [ ] **Step 3: Implement structured events and resume**

Extend Sandbox request bodies with `run_id`, `tool_manifest`, `tool_gateway_url`, and `tool_gateway_token`. Emit newline-delimited JSON events with this exact shape:

```json
{"type":"plan_created","plan":[{"id":"retrieve","summary":"Retrieve evidence"}]}
{"type":"tool_requested","capability_id":"project.retrieve","arguments":{"query":"..."}}
{"type":"paused","reason":"approval_required","sandbox_session_id":"..."}
{"type":"final","content":"...","artifact":{"type":"report","content":"..."},"citations":[]}
```

Add `/resume` accepting the persisted `sandbox_session_id` and approval result. In `codex_runtime.py`, add `start_codex_orchestration_run` and `resume_codex_orchestration_run`; both parse the events, map them to persisted run state, and never log tool tokens.

- [ ] **Step 4: Add event streaming endpoint**

Add `GET /orchestration-runs/{run_id}/events`. Return ordered, audit-safe run events using Server-Sent Events; terminate the stream once the run reaches `completed`, `failed`, or `cancelled`.

- [ ] **Step 5: Run runtime tests**

Run: `pytest tests/test_codex_sandbox_server.py tests/test_orchestration_runs.py tests/test_tool_gateway.py -v`

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add codex-sandbox/server.py backend/app/services/codex_runtime.py backend/app/api/orchestration_events.py tests/test_codex_sandbox_server.py tests/test_orchestration_runs.py tests/test_tool_gateway.py
git commit -m "feat: stream resumable codex orchestration"
```
