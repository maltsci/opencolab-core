# Module guide

This guide describes implemented capabilities in the current checkout, their main code locations and operating boundaries. Paths are repository-relative; the [API schema](README.md#api-reference) provides exact request contracts. Detailed historical plans are not completion evidence.

## Workspace, identity and collaboration

Projects carry membership, sharing, instructions, plans, activity, source associations, sessions and research memory. Research objects and evidence relations preserve findings beyond individual chat messages. Users have Researcher, PI and Admin roles; scoped knowledge stewardship grants additional maintenance/review capabilities without making every steward a global administrator.

- UI: `frontend/src/pages/ProjectHome.tsx`, `ProjectAssets.tsx`, `ProjectMemory.tsx`, `Session.tsx`.
- API: `backend/app/api/projects.py`, `project_plans.py`, `project_activities.py`, `sessions.py`, `auth.py`.
- Evidence: `backend/app/api/research_objects.py`, `research_object_relations.py`, `research_threads.py`.
- Regression coverage: `tests/test_project_plans.py`, `test_project_activities.py`, `test_sessions.py`, `test_auth.py`.
- Guides: [Project permissions](project-permissions.md), [sharing](sharing-and-permissions.md).

## Library, ingestion and bibliographic metadata

The library manages source documents, collections, tags, notes and project-linked materials. Uploads include PDF, DOCX, Markdown, TXT, ZIP bundles and experimental data packages. A data package is not a promise that arbitrary binary formats are parsed into searchable text. Processing state distinguishes upload, parsing, embedding and failures. Duplicate handling provides reuse/access guidance rather than silently granting another user access.

PDF parsing can use remote PPS when enabled with a key, then fall back locally. Local parsing uses marker when enabled and basic text extraction otherwise; OCR quality therefore depends on deployment. Embeddings use a configurable local provider and optional cloud fallback. Bibliographic metadata supports local extraction, identifier candidates, optional provider lookup, and applying selected metadata. Provider adapters cover Crossref, PubMed, PMC and arXiv; lookup is disabled by default in application settings.

- UI: `frontend/src/pages/Library.tsx`, `ResourcePreview.tsx`.
- API: `backend/app/api/sources.py`, `research_assets.py`, `notes.py`, `tags.py`.
- Services: `backend/app/services/document_service.py`, `pdf_service.py`, `chunking_service.py`, `embedding_service.py`, `vector_store.py`, `bibliographic_metadata_service.py`, `bibliographic_provider_service.py`.
- Coverage: `tests/test_pdf_service.py`, `test_source_extractions.py`, `test_duplicate_upload_recovery.py`, `test_data_assets.py`.
- Boundary: [Offline deployment and data flow](deployment.md#offline-deployment-and-data-boundaries).

## Asset governance and content access

Assets have revisions, classification, ownership and policies. Search/discovery, reading content, linking materials to a project, publishing and maintenance are separate operations. Requests and grants enable controlled access; notifications inform participants of requests and decisions. Project linkage does not replace content authorization.

- Services: `backend/app/services/access_policy_service.py`, `research_asset_service.py`, `asset_revision_service.py`, `knowledge_access_service.py`, `notification_service.py`.
- Coverage: `tests/test_access_policy_service.py`, `test_research_asset_governance.py`, `test_asset_revisions.py`, `test_notifications.py`.
- Guides: [Project material access](project-material-access.md), [security contract](lab-knowledge-os-v1-security-contract.md), [migration runbook](lab-knowledge-os-v1-migration-runbook.md).

## Research conversations, tasks and skill packs

Sessions support streaming answers, Markdown rendering, citations and traces. Project QA retrieves context by query and selected sources. Research tasks cover literature synthesis, core ideas, gaps, hypotheses and experiment-design suggestions. These outputs are model-generated assistance, not experimentally verified discoveries.

Task and workflow records preserve execution state and results. Built-in workflow definitions remain in code. Administrators extend execution by uploading versioned `SKILL.md` packages; the legacy customizable declarative skill/workflow-definition mechanism is no longer the extension model. Codex execution requires a reachable authenticated runtime, a compatible configured model endpoint and matching shared workspace paths.

- UI: `frontend/src/pages/TaskWorkspace.tsx`, `Session.tsx`, `frontend/src/pages/admin/SkillPacks.tsx`, `Tasks.tsx`.
- API: `backend/app/api/tasks.py`, `workflows.py`, `orchestration.py`, `agent_runtime.py`, `websocket.py`.
- Services: `backend/app/services/rag_service.py`, `research_context.py`, `trace_service.py`, `task_service.py`, `skill_pack_service.py`, `orchestration_service.py`, `codex_runtime.py`.
- Runtime: `backend/app/workflows/`, `backend/app/services/agents/`, `codex-sandbox/server.py`.
- Coverage: `tests/test_rag_service.py`, `test_tasks_api.py`, `test_orchestration_runs.py`, `test_skill_packs.py`, `test_codex_runtime.py`.

## Laboratory knowledge

Research direction directories support lifecycle management, relations, merging, stewards and links to people, resources, projects and research objects. People profiles retain expertise, direction history, representative resources, recent work and archival state. Resource catalog profiles cover papers and manually registered resources such as datasets, repositories, model weights and GPU resources; catalog registration does not provision infrastructure.

The knowledge assistant explores accessible entities and supports continuation into directories. Suggestions have scoped review, decisions, read state and audit history. Maintenance lists and health views expose stale or incomplete knowledge and pending work.

- UI: `frontend/src/pages/Research.tsx`, `People.tsx`, `KnowledgeAssistant.tsx`, `KnowledgeGovernance.tsx`, `KnowledgeHealth.tsx`, `ResourceMaintenance.tsx`.
- API: `backend/app/api/research_directions.py`, `people.py`, `research_groups.py`, `knowledge_governance.py`, `research_assets.py`.
- Services: `backend/app/services/research_direction_service.py`, `people_service.py`, `resource_catalog_service.py`, `knowledge_governance_service.py`.
- Coverage: `tests/test_research_directions.py`, `test_people.py`, `test_resource_catalog.py`, `test_knowledge_governance.py`, `test_lab_knowledge_benchmark.py`.

## Adaptive training

PI/Admin course authoring includes versions, materials, modules, units, knowledge points and evidence. Courses and modules can be assigned to trainees. Learning pages provide generated lessons, material-grounded questions, practice, unit/final assessment, next steps and progress reports. Content language and display translation support en-US and zh-CN. Evidence quote validation constrains grounding; generated teaching content still requires review.

- UI: `frontend/src/pages/TrainingCourses.tsx`, `TrainingHome.tsx`, `TrainingLearningPath.tsx`, `TrainingModuleLearning.tsx`, `TrainingReport.tsx`.
- API/service: `backend/app/api/training.py`, `backend/app/services/training_service.py`.
- Contracts/state: `backend/app/schemas/training.py`, `backend/app/models/training.py`.
- Coverage: `tests/test_training_courses.py`.
- Dependencies: authorized source material and a functioning LLM configuration; local inference is possible when its endpoint supports the required calls.

## Administration and model configuration

Administrators manage users, model profiles, probes, runtime configuration, skill packs and tasks. Runtime values resolve from database configuration before environment and `.env` files; bootstrap database/security/Qdrant settings remain environment-based. LLM profiles resolve the active model connection; provider configuration is shared infrastructure for research and training.

- UI: `frontend/src/pages/admin/`.
- API/core: `backend/app/api/admin.py`, `backend/app/core/config.py`.
- Services: `backend/app/services/runtime_config.py`, `llm_profile_service.py`, `llm_service.py`.
- Coverage: `tests/test_admin.py`, `test_llm_profile_service.py`.
- Full configuration and startup: [Deployment](deployment.md), [development setup](development.md).
