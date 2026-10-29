# Research Asset Governance, Catalog, and Data Assets v1 Design

## Summary

OpenColab will add a first-class Research Asset Governance layer that lets laboratory members discover governed laboratory assets according to their metadata-discovery rules without automatically gaining access to content. A Research Asset is any logical content unit that can be read, discovered, cited, or access-controlled, including documents, external references, generated outputs, research memory, saved conversation artifacts, experimental material, and specialized scientific data.

`ResearchAsset` provides the stable governed identity. Immutable `AssetRevision` records preserve successive content states, and `AssetContentMember` records let one revision contain one or many physical files or content references. Data Assets remain a specialized, high-value asset category within this common governance model.

Every published L0-L2 asset and every L3 asset without an explicit metadata deny is catalog-searchable through sanitized metadata. L4 discovery remains restricted. Full-text and vector retrieval are separate capabilities available only for authorized `ready` revisions and members.

This release also establishes the foundation for a governed laboratory-wide knowledge base. Every ready revision is indexed once with stable asset, revision, member, and chunk identity. Future knowledge queries unlock already-indexed content through live authorization rather than copying, reparsing, or re-embedding data after approval.

The first release delivers a complete governance loop:

1. register or migrate a governed `ResearchAsset` and its first immutable revision;
2. publish sanitized catalog metadata;
3. discover the asset in Research Explorer;
4. request specific capabilities for a stated purpose and duration;
5. complete the required Asset Owner and/or PI approvals;
6. use an authorized revision through a controlled content gateway;
7. record human and Agent access in an append-only audit trail;
8. expire or revoke the resulting grant.

This design extends the existing `ResearchObject` and `ResearchAsset` architecture. It does not replace the laboratory library, project permissions, source storage, or research-object relation graph.

## Goals

- Bring every existing and future `ResearchAsset` under one governance model.
- Represent each independently governed logical material as one stable Research Asset, whether it has one content member or many.
- Preserve immutable, citable revisions for changing reports, snapshots, memory, conversations, and scientific datasets.
- Support uploaded material, external references, generated documents, research memory, saved conversation artifacts, experimental material, and specialized scientific data.
- Make governed laboratory assets discoverable while keeping their actual content inaccessible by default.
- Introduce `DataAsset` as a first-class type of `ResearchObject`.
- Support five classification levels from Public to Top Secret.
- Separate catalog metadata from protected metadata and raw data.
- Support multiple lightweight research groups and scientific roles.
- Combine RBAC and explicit ABAC conditions without adding a general-purpose policy language.
- Provide capability-specific, purpose-bound, project-bound, time-limited access.
- Provide a complete access request, approval, grant, revocation, and audit workflow.
- Enforce the same access decisions for UI, API, RAG, workflows, and Agents.
- Allow project sessions to use only project-linked asset revisions for which the current user has live `content:use_in_agent` permission.
- Expand secure uploads beyond PDF and ZIP with an explicit parsed-versus-catalog-only file support model.
- Support multi-file scientific data packages, including alignment, sequence, variant, index, metadata, and quality-control members.
- Establish a governed laboratory-wide knowledge foundation across catalog metadata, parsed revision content, and Research Object relations.
- Let members globally discover published L0-L2 materials and L3 materials not narrowed by explicit metadata deny, then request revision-specific access to protected content from the same discovery flow.
- Make approved content usable on the next query without duplicating data or rebuilding its index.
- Preserve OpenColab's local-first and air-gapped deployment model.

## Non-Goals

The first release will not implement:

- AI-generated catalog entries;
- AI-based sensitive-data detection;
- AI-generated permission recommendations;
- automatic external storage account provisioning;
- automatic contract or collaboration-agreement parsing;
- a general-purpose policy DSL;
- multi-lab tenancy;
- automatic relocation of existing external data;
- content inference from catalog metadata when the requesting actor cannot read the content.
- unrestricted project-less AI synthesis over Confidential, Restricted, or Top Secret content;
- a finished general-purpose laboratory-wide AI answer experience beyond the governed indexing and query foundation.

The data model and service boundaries must allow the first three AI capabilities to be added later without bypassing human approval.

## Existing System Context

OpenColab already has:

- `ResearchObject` and `ResearchObjectRelation` for durable research semantics;
- `ResearchAsset` as a laboratory-library index over `Source` and `ResearchObject`;
- project membership through `ResearcherProject`;
- global platform roles `admin`, `pi`, and `researcher`;
- source sharing and project asset links;
- local file storage, parsing, chunking, Qdrant retrieval, RAG, Agents, and workflows.

The existing visibility model answers whether content is readable. It does not represent the new distinction between:

- knowing that a data asset exists;
- viewing its sanitized metadata;
- viewing protected metadata;
- previewing content;
- downloading original content;
- allowing an Agent to use content.

All Research Assets therefore require a common governance model rather than additional `visibility_scope` values or a DataAsset-only permission layer.

## Architecture Decision

### Selected approach

Use `ResearchAsset` as the governed-asset root. Every Research Asset carries classification, catalog metadata, protected metadata, stewardship, group ownership, and governance lifecycle fields.

Use immutable `AssetRevision` records beneath each Research Asset. Each revision owns an ordered manifest of `AssetContentMember` records. A content member may resolve to managed local content, generated text, a Research Object snapshot, or external-reference metadata. Physical files and member paths are not independent permission boundaries.

Use a specialized `DataAsset` record linked one-to-one to both a `ResearchAsset` and a `ResearchObject` with `type = "data_asset"`. `DataAsset` contains only dataset-specific scientific semantics. Revision members, rather than `DataAsset`, own physical storage references.

The three asset concepts have separate responsibilities:

- `ResearchAsset` owns common governance facts and remains the unified index for papers, reports, SOPs, datasets, project outputs, private uploads, and research memory.
- `AssetRevision` owns an immutable content state, processing status, and manifest hash.
- `AssetContentMember` owns one managed payload, generated snapshot, or external-reference member within a revision.
- `ResearchObject` owns research meaning, provenance, and relations to Hypotheses, Evidence, Experiments, SOPs, and other objects.
- `DataAsset` owns dataset-specific facts such as data type, modality, organism, assay, platform, and structured scientific description.

Every active `ResearchAsset` must have a governance classification, catalog state, sanitized catalog metadata, content-access policy baseline, steward, and owning-group state.

Every published Research Asset must have a sealed current revision. A metadata-only external reference satisfies this rule with a sealed `external_metadata` member.

Every active `DataAsset` must additionally have:

- exactly one linked `ResearchObject`;
- exactly one linked governed `ResearchAsset`;
- at least one sealed revision;
- a valid scientific-data subtype and structured description.

`AccessPolicy`, `AccessRequest`, `AccessGrant`, and `AccessAuditEvent` target `research_asset_id` and, where required, `asset_revision_id`, so all asset categories use the same enforcement path.

For managed legacy datasets, a `ResearchAsset` retains its existing `source_id` during migration while gaining a Data Asset `ResearchObject`, revision 1, and a primary content member that resolves to the existing Source. New content reads use revision members rather than `ResearchAsset.source_id`.

### Rejected approaches

Adding a separate `AssetGovernanceProfile` was rejected because every Research Asset must be governed; an optional companion row would add joins and create missing-profile failure modes.

Keeping governance only on `DataAsset` was rejected because papers, reports, SOPs, project outputs, and private uploads must also be discoverable and content-controlled.

Type-specific policy systems were rejected because they would duplicate search, permission, audit, and RAG enforcement and create bypass risk.

Treating every physical file as an independent Research Asset was rejected because scientific datasets commonly require multiple coordinated members such as BAM, BAI, sample metadata, and quality-control reports.

Using mutable content directly on `ResearchAsset` was rejected because it would make historical citations and experimental reproduction unstable.

## Layered Architecture

### Research Workspace

User-facing and Agent-facing clients:

- Research Explorer;
- Data Asset registration and management;
- Access Request Center;
- project workspaces;
- Agents, RAG, and workflows.

### Research Knowledge and Governance Layer

The application layer contains these independent services:

- `ResearchCatalogService`: governed-asset registration, publication, redacted detail responses, and search.
- `AssetRevisionService`: revision creation, validation, sealing, current-revision changes, and member manifests.
- `KnowledgeIndexService`: durable index-event processing for catalog metadata, parsed revision chunks, and Research Object relations.
- `KnowledgeQueryService`: governed candidate discovery, access-state annotation, scope enforcement, and authorized retrieval.
- `AssetPolicyService`: centralized policy decisions for metadata and content capabilities.
- `AccessRequestService`: request validation and approval workflow.
- `AccessGrantService`: immutable grants, expiry, and revocation.
- `GovernedContentGateway`: controlled preview, download, and Agent/RAG content reads through type-specific content adapters.
- `AssetAuditService`: append-only decision and access events.
- `ResearchGroupService`: lightweight group membership and scientific roles.

No content endpoint, Agent, workflow, or vector-search caller may implement its own role shortcut. All governed content access must call `AssetPolicyService` through `KnowledgeQueryService` or `GovernedContentGateway`.

### Metadata plane

PostgreSQL stores:

- Research Asset identity, classification, and governance lifecycle;
- immutable revision manifests and current-revision identity;
- content-member identity, role, format, hash, and protected resolver reference;
- sanitized catalog metadata;
- encrypted protected metadata where required;
- policies, agreements, requests, approvals, grants, and audit events;
- durable knowledge-index events and processing state;
- searchable catalog indexes.

Only explicitly sanitized catalog fields are searchable.

### Data plane

Managed content remains in OpenColab-controlled local storage. `GovernedContentGateway` resolves content through an adapter for a `Source`, a generated `ResearchObject`, or a specialized Data Asset.

External content remains in a laboratory-controlled system such as NAS, object storage, or an instrument system. OpenColab stores only an encrypted locator and controlled handoff instructions.

Qdrant stores parsed chunks for every successfully processed `ready` revision, independent of any individual user's current grant. Each vector payload includes `research_asset_id`, `asset_revision_id`, `asset_content_member_id`, and `chunk_id`. Storage in Qdrant never implies that a caller may retrieve the chunk.

Clients never receive a raw local filesystem path, unencrypted external locator, external credential, or provider token.

## Research Groups and Roles

### Platform roles

Existing global roles remain unchanged:

- `admin`;
- `pi`;
- `researcher`.

They control platform administration. They must not be used as the sole source of scientific data-access decisions.

An Admin can manage governance configuration and perform an explicitly audited emergency grant, but does not automatically receive content access to every Research Asset.

### Research group roles

Add lightweight `ResearchGroup` and `ResearchGroupMember` entities.

Supported group roles:

- `pi`;
- `postdoc`;
- `phd_student`;
- `assistant`;
- `external_collaborator`.

A user may belong to multiple research groups. A user may hold only one role in a given group.

A project may belong to zero or one research group in v1. Assigning or changing the project's group is a PI/Admin action and must be audited.

Research group membership does not automatically make a user a project member. Project membership remains an independent condition.

### ResearchGroup

Required fields:

- `id`;
- `name`;
- `description`;
- `created_by`;
- `created_at`;
- `updated_at`;
- `archived_at`.

### ResearchGroupMember

Required fields:

- `id`;
- `research_group_id`;
- `user_id`;
- `role`;
- `created_by`;
- `created_at`;
- `updated_at`.

The pair `(research_group_id, user_id)` must be unique. All foreign-key columns must be indexed.

## Governed Asset Model

### Research material taxonomy

Asset identity, research semantics, and physical format are separate dimensions.

`asset_category` is a stable top-level classification:

- `uploaded_material`: PDF, Word, spreadsheet, structured file, image, or uploaded package;
- `external_reference`: URL, DOI, public publication metadata, or an explicitly saved web snapshot;
- `generated_document`: task report, literature review, experiment design, or analysis report;
- `research_memory`: discussion, Hypothesis, Evidence, conclusion, or Research Object relation context;
- `conversation_artifact`: a user-saved conversation summary, note, draft, or conclusion;
- `experimental_material`: SOP, protocol, experiment record, or experimental-data description;
- `scientific_data`: bioinformatics and other specialized scientific datasets.

`asset_type` remains the more specific semantic subtype. Initial values include:

- `uploaded_file`;
- `archive_package`;
- `url`;
- `doi`;
- `publication_metadata`;
- `web_snapshot`;
- `task_report`;
- `literature_review`;
- `experiment_design`;
- `analysis_report`;
- `discussion`;
- `hypothesis`;
- `evidence`;
- `conclusion`;
- `relationship_note`;
- `conversation_summary`;
- `note`;
- `draft`;
- `sop`;
- `protocol`;
- `experiment_record`;
- `data_description`;
- `sequencing_dataset`;
- `alignment_dataset`;
- `variant_dataset`;
- `scientific_dataset`.

File extensions, MIME types, and package-member roles are not asset types. They belong to `AssetContentMember`.

A Collection is an organizational container, not a readable content unit. It does not receive content grants, enter content RAG, or appear as an ordinary material in Research Explorer.

### ResearchAsset governance fields

Every `ResearchAsset`, regardless of asset type or origin, is governed.

Add these common fields to the existing model:

- `asset_category`;
- `current_revision_id`, nullable until initial ingestion is sealed and indexed;
- `owning_group_id`, nullable during legacy review and indexed;
- `steward_user_id`, indexed;
- `classification`;
- `catalog_status`;
- `lifecycle_status`;
- `governance_review_status`;
- `catalog_metadata_json`;
- `protected_metadata_json`;
- `catalog_published_at`, nullable;
- `catalog_withdrawn_at`, nullable.

`owning_group_id` represents organizational ownership. `steward_user_id` is the accountable Asset Owner used by the approval workflow.

Supported `catalog_status` values:

- `draft`;
- `published`;
- `withdrawn`.

Supported `lifecycle_status` values:

- `active`;
- `archived`.

Supported `governance_review_status` values:

- `pending`;
- `reviewed`.

Every successful new upload creates a published catalog record with a safe minimal metadata set. New project and library uploads must resolve an owning group from the project context or an explicit user selection. Legacy assets with missing group information remain published under their migrated classification but use `governance_review_status = "pending"` and cannot gain broader content access until reviewed.

Archived content cannot be used to create a new grant. Existing grants become unusable immediately, but history and audit records remain.

### AssetRevision

`ResearchAsset.id` is stable across content updates. Every accepted update creates a new revision rather than overwriting content.

Required fields:

- `id`;
- `research_asset_id`, indexed;
- `revision_number`;
- `processing_state`;
- `manifest_sha256`;
- `change_summary`, nullable;
- `created_by`;
- `created_at`;
- `sealed_at`.

The pair `(research_asset_id, revision_number)` is unique. Revision numbers increase monotonically per asset.

`manifest_sha256` is computed from a canonical ordered representation of member identity, role, normalized path, size, and content hash. It excludes storage locators and credentials.

Revision content and the member manifest become immutable at `sealed_at`. Operational processing fields may advance from `processing` to `ready`, `catalog_only`, or `processing_failed`, but sealed content references, member roles, hashes, and paths cannot change. Correcting content requires a new revision.

`ResearchAsset.current_revision_id` changes atomically only after a new revision is safely sealed. A failed temporary ingestion does not become a citable revision and cannot replace the current revision.

### AssetContentMember

A revision contains one or more ordered content members.

Required fields:

- `id`;
- `asset_revision_id`, indexed;
- `member_role`;
- `content_mode`;
- `normalized_path`;
- `display_name`;
- `file_format`, nullable;
- `media_type`, nullable;
- `size_bytes`, nullable;
- `sha256`, nullable;
- `managed_source_id`, nullable and indexed;
- `external_reference_ciphertext`, nullable;
- `external_metadata_json`, nullable;
- `external_handoff_json`, nullable;
- `created_at`.

Supported `member_role` values:

- `primary`;
- `package`;
- `index`;
- `metadata`;
- `qc_report`;
- `attachment`;
- `snapshot`.

Supported `content_mode` values:

- `managed`;
- `generated_snapshot`;
- `external_metadata`.

Managed and generated-snapshot members resolve through local controlled storage. External-metadata members contain canonical URL or DOI reference data and no readable local content. Exactly one content reference mode is active for each member.

`managed` and `generated_snapshot` require `managed_source_id` and forbid an external ciphertext. `external_metadata` requires validated external metadata, may include an encrypted sensitive locator for controlled handoff, and forbids `managed_source_id`.

Member paths organize content within a logical asset. They do not create separate Research Assets, policies, grants, or project links.

### Revision and authorization scope

Classification, discovery, stewardship, owning group, project links, and lifecycle remain asset-level facts.

An `AccessPolicy` may optionally name `asset_revision_id`. A null revision means an explicitly configured cross-version policy. Classification baselines continue to apply according to the asset classification.

Every ordinary `AccessRequest` and `AccessGrant` names exactly one revision. A grant never expands automatically to a later revision. Publishing a new revision leaves an existing grant valid for its original revision unless a stronger asset-level deny, classification change, withdrawal, or archival invalidates it.

Revision-specific grants do not remove classification baseline access or an explicitly configured cross-version policy. For example, a Public revision remains available through the Public baseline, while a Confidential revision requires a matching revision grant or explicit cross-version policy.

Agent and human reads always resolve both the asset and revision before content access.

### DataAsset

Required fields:

- `id`;
- `research_asset_id`, unique and indexed;
- `research_object_id`, unique and indexed;
- `data_type`;
- `data_modality`, nullable;
- `scientific_metadata_json`;
- `created_by`;
- `created_at`;
- `updated_at`;

Examples of `scientific_metadata_json` include organism, assay, platform, reference genome, cohort summary, modality, and approved sample-count range. Storage locators and physical file references belong only to revision members.

Generic uploaded assets do not require a `DataAsset` row. Specialized scientific packages do.

### Metadata separation

`catalog_metadata_json` contains sanitized values that may be searched and shown to actors allowed to discover the asset. Examples:

- asset category and semantic subtype;
- current revision number and sanitized member-format summary;
- approved title and description;
- author, publication, or document type;
- organism;
- assay;
- approximate sample count or approved range;
- platform;
- high-level modality;
- approved keywords;
- sanitized abstract.

`protected_metadata_json` contains values that may reveal sensitive operational or contractual information. Examples:

- internal document annotations;
- exact sample identifiers;
- exact sample counts when sensitive;
- collaborator identities;
- checksums;
- detailed cohort definitions;
- instrument run identifiers;
- internal contact details;
- storage information that is not held in the encrypted locator.

The API must use separate response schemas. It must not create a combined dictionary and remove fields after serialization.

The human protected-metadata endpoint requires `content:preview` or `content:download` for the same Research Asset and context. An Agent with only `content:use_in_agent` may receive only the protected fields required for an authorized bounded retrieval through `GovernedContentGateway`; it cannot call the human protected-metadata endpoint.

### Catalog publication

A draft Research Asset is visible only to its steward, owning-group PI, and Admin governance views.

Publishing requires:

- a valid owning group;
- an active steward who belongs to that group;
- an allowed classification;
- non-empty sanitized title, description, and catalog metadata;
- a sealed current revision with a valid member manifest, including metadata-only external-reference manifests;
- a default policy set;
- PI or steward confirmation that catalog metadata contains no protected values.

L4 publication means publication into its restricted hidden catalog, not laboratory-wide discovery. Successful standard uploads publish immediately with minimal catalog metadata and the context-specific default classification defined in the upload section.

### Classification changes

Classification values are:

- `public` for L0;
- `internal` for L1;
- `confidential` for L2;
- `restricted` for L3;
- `top_secret` for L4.

Raising a classification immediately re-evaluates existing grants and revokes grants that no longer meet the new baseline.

Lowering L2, L3, or L4 requires a group PI or Admin governance decision and an audit reason. The catalog is republished only after its metadata is reviewed against the new discovery audience.

## Classification and Default Access Matrix

### L0 Public

- Discoverability: all authenticated laboratory members.
- Catalog metadata: visible.
- Content: preview, download, and Agent use are allowed by default.
- Approval: none.

### L1 Internal

- Discoverability: all laboratory members can see sanitized catalog metadata.
- Same owning group, excluding External Collaborators: default preview and Agent use; download remains policy-controlled.
- Other groups and External Collaborators: request required.
- Approval: Asset Owner.

### L2 Confidential

- Discoverability: all laboratory members can see sanitized catalog metadata.
- Content: no default content access except the steward's management context.
- Approval: Asset Owner or an owning-group PI.
- Result: purpose-bound, project-bound, time-limited grant.

### L3 Restricted

- Discoverability: all laboratory members can see sanitized catalog metadata unless an explicit deny policy narrows discovery.
- Content: request required; any required collaboration agreement must be active.
- Approval: Asset Owner and owning-group PI.
- Separation of duties: the two approvals must come from distinct users. If the Asset Owner is also the only group PI, an Admin governance approver must provide the second decision.
- Result: purpose-bound, project-bound, time-limited grant.

### L4 Top Secret

- Discoverability: hidden by default. Only the steward, owning-group PIs, Admin governance users, and subjects named by an explicit policy or grant may discover it.
- Unauthorized direct lookup, list, count, facet, and autocomplete behavior must not reveal its existence.
- Self-service request: unavailable.
- Grant creation: proactive group PI or Admin governance action with a mandatory reason.
- Agent use: denied by default even when a human has preview or download access. `content:use_in_agent` must be explicitly granted.

## Capabilities

Capabilities are independent:

- `metadata:view`;
- `content:preview`;
- `content:download`;
- `content:use_in_agent`;
- `asset:manage`.

`metadata:view` refers only to catalog metadata. Protected metadata requires an active content capability.

An access request defaults to:

- `content:preview`;
- `content:use_in_agent`.

The requester must explicitly add `content:download`. Approvers can remove requested capabilities but cannot add capabilities that the requester did not request.

`asset:manage` is not requestable through the ordinary content-access flow. It is assigned through stewardship or an explicit management policy.

## Policy Model

### AccessPolicy

Policies express durable allow or deny rules. They do not represent an approved individual request.

Required fields:

- `id`;
- `research_asset_id`, indexed;
- `asset_revision_id`, nullable and indexed;
- `effect`: `allow` or `deny`;
- `subject_type`: `user`, `research_group`, `project`, or `group_role`;
- `subject_id`, nullable according to subject type; for `group_role`, it identifies the research group;
- `group_role`, nullable;
- `required_project_id`, nullable;
- `required_agreement_id`, nullable;
- `capabilities_json`;
- `valid_from`, nullable;
- `valid_until`, nullable;
- `priority`;
- `enabled`;
- `created_by`;
- `created_at`;
- `updated_at`.

V1 uses explicit columns and validated enums. It does not accept executable expressions, arbitrary JSON logic, or user-authored code.

A policy with `asset_revision_id = null` is an explicit cross-version rule. Revision-scoped policy is preferred for content capabilities on Confidential, Restricted, and Top Secret assets.

### DataUseAgreement

Add a lightweight structured agreement record because L3 policies must evaluate collaboration constraints.

Required fields:

- `id`;
- `name`;
- `owning_group_id`;
- `status`: `draft`, `active`, `expired`, or `terminated`;
- `valid_from`;
- `valid_until`;
- `allowed_project_id`, nullable;
- `allowed_research_group_id`, nullable;
- `allowed_capabilities_json`;
- `reference`;
- `created_by`;
- `created_at`;
- `updated_at`.

`reference` is an internal identifier or controlled document reference, not parsed contract text.

An agreement is usable only when its status and dates are active and its project, group, and capability restrictions match the access context.

### Decision order

Every decision evaluates:

1. asset existence, lifecycle, and L4 discovery rules;
2. explicit matching deny policies;
3. classification baseline;
4. matching allow policies;
5. active Data Use Agreement conditions;
6. active Access Grant capabilities, project, purpose, and dates;
7. Agent delegation restrictions;
8. default deny.

An explicit deny always wins. A global platform role does not bypass a deny.

The decision service returns an internal structured result:

- `allowed`;
- `reason_code`;
- `matched_policy_ids`;
- `grant_id`;
- `requestable`;
- `required_approver_types`;
- `effective_capabilities`.

Public API responses expose a safe subset and never return internal policy details that would leak L4 existence or protected conditions.

## Access Request Workflow

### AccessRequest

Required fields:

- `id`;
- `research_asset_id`, indexed;
- `asset_revision_id`, indexed;
- `requester_user_id`, indexed;
- `project_id`, indexed;
- `purpose`;
- `hypothesis_object_id`, nullable and indexed;
- `requested_capabilities_json`;
- `requested_start_at`;
- `requested_end_at`;
- `status`;
- `submitted_at`, nullable;
- `decided_at`, nullable;
- `created_at`;
- `updated_at`.

The requester must be a member of the selected project. The project's group and any required agreement are evaluated when the request is submitted and again when a grant is used.

The purpose is immutable after submission. It may reference a Hypothesis through `hypothesis_object_id`, but a free-text purpose remains required for auditability.

Only one non-terminal request may exist for the same requester, Research Asset revision, project, and capability set.

Changing `ResearchAsset.current_revision_id` does not rewrite a pending request. The request remains bound to the revision selected at submission.

### Request states

Supported states:

- `draft`;
- `submitted`;
- `pending_owner`;
- `pending_pi`;
- `approved`;
- `rejected`;
- `cancelled`;
- `expired`.

The service creates required approval steps at submission:

- L1 cross-group: Asset Owner step.
- L2: one step satisfiable by Asset Owner or owning-group PI.
- L3: distinct Asset Owner and owning-group PI steps.
- L4: ordinary request creation is rejected.

A required rejection immediately sets the request to `rejected`. The requester may cancel before a terminal decision. Expired requests cannot be approved and must be resubmitted.

### ApprovalStep

Required fields:

- `id`;
- `access_request_id`, indexed;
- `step_type`: `asset_owner` or `group_pi`;
- `sequence`;
- `status`: `pending`, `approved`, `rejected`, or `skipped`;
- `eligible_subject_json`;
- `decided_by`, nullable and indexed;
- `decision_comment`, nullable;
- `decided_at`, nullable;
- `created_at`.

Approval transitions must run in a database transaction and lock the request row. Decision endpoints must be idempotent for a repeated decision from the same actor and must reject contradictory second decisions.

## Access Grants

### AccessGrant

An approved request creates one immutable grant. A proactive L4 grant has no request but must include the creator and reason.

Required fields:

- `id`;
- `research_asset_id`, indexed;
- `asset_revision_id`, indexed;
- `grantee_user_id`, indexed;
- `project_id`, indexed;
- `access_request_id`, nullable and indexed;
- `purpose`;
- `hypothesis_object_id`, nullable and indexed;
- `capabilities_json`;
- `valid_from`;
- `valid_until`;
- `granted_by`;
- `grant_reason`;
- `revoked_at`, nullable;
- `revoked_by`, nullable;
- `revocation_reason`, nullable;
- `created_at`.

Grant rows are not updated to change revision, capabilities, or dates. A changed authorization requires revocation and a new grant.

Grant status is derived:

- `scheduled`;
- `active`;
- `expired`;
- `revoked`.

V1 duration limits:

- L1 and L2: at most 90 days;
- L3: at most 30 days;
- L4 proactive grant: at most 30 days.

A revocation or asset archival takes effect on the next content-gateway decision. A running Agent must reauthorize each content fetch and stop at the next denied fetch. Content already supplied to a running model cannot be recalled, so Agent integrations must use bounded retrieval rather than preload an entire governed asset.

## Audit Model

### AccessAuditEvent

Required fields:

- `id`;
- `research_asset_id`, nullable and indexed;
- `asset_revision_id`, nullable and indexed;
- `asset_content_member_id`, nullable and indexed;
- `actor_type`: `human`, `agent`, or `system`;
- `actor_user_id`, nullable and indexed;
- `agent_run_id`, nullable and indexed;
- `project_id`, nullable and indexed;
- `action`;
- `capability`, nullable;
- `decision`: `allow`, `deny`, or `not_applicable`;
- `reason_code`;
- `access_request_id`, nullable and indexed;
- `access_grant_id`, nullable and indexed;
- `context_json`;
- `occurred_at`, indexed.

Audited actions include:

- asset registration, publication, withdrawal, archival, and classification change;
- revision creation, sealing, current-revision change, processing failure, and retry;
- knowledge-index event processing and administrative retry;
- laboratory-global and project-scoped knowledge searches;
- policy creation, update, enable, and disable;
- request submission, approval, rejection, cancellation, and expiry;
- grant creation, expiry detection, and revocation;
- protected metadata view;
- preview, download, and Agent/RAG content reads;
- denied content and hidden-asset probes recorded without exposing them to the caller;
- research-group and project-group membership changes.

Audit events are append-only. The application exposes no update or delete endpoint. `context_json` must contain identifiers and safe decision context, never raw content, protected metadata, credentials, or storage locators.

## Search and Research Object Relations

### Research Explorer

Add server-side, cursor-paginated search over every published, governed `ResearchAsset`, including:

- papers;
- Evidence;
- Data Assets;
- Experiments;
- SOPs;
- reports;
- project outputs;
- research memory;
- private uploads;
- other indexed Research Assets and Research Objects.

The initial implementation uses `ResearchAsset` as the catalog root and enriches results from linked `ResearchObject` and `DataAsset` records. Catalog search does not require content embeddings.

Research Asset search indexes:

- sanitized title and description;
- asset category and semantic subtype;
- approved keywords;
- approved `catalog_metadata_json` fields;
- classification and owning group for filtering.

It must not index:

- `protected_metadata_json`;
- encrypted locators;
- raw content;
- internal policy conditions;
- L4 records outside the actor's discovery scope.

Each Research Asset search result includes:

- asset category and semantic subtype;
- title;
- sanitized summary;
- classification;
- owning group display name;
- access status;
- effective capabilities;
- whether an access request is available;
- a safe approval summary such as "Asset Owner approval" or "Asset Owner and PI approval";
- processing status: `ready`, `catalog_only`, `processing`, or `processing_failed`;
- current revision number, safe revision timestamp, and sanitized member-format summary;
- project-link status.

Possible access statuses:

- `available`;
- `requestable`;
- `pending`;
- `approved`;
- `denied`;
- `not_requestable`.

L4 records are absent rather than returned with `denied`.

Research Explorer returns one result per logical Research Asset, not one result per revision or member. Authorized detail views may list revision history. Without content access, revision history exposes only revision number, safe timestamp, processing state, and sanitized member-format counts.

### Research Object relations

The existing `ResearchObjectRelation` model links Data Assets and other Research Objects to Hypotheses, Evidence, Experiments, SOPs, and other objects.

A relation hint may be shown in catalog-only contexts only when:

- both endpoint objects are discoverable to the actor; and
- the Asset Owner explicitly marks the relation metadata as catalog-visible.

Without content access, an Agent may state:

> A related internal Data Asset exists, but its content cannot be verified with the current authorization.

It must not state that the data supports or contradicts a hypothesis unless it has read authorized evidence sufficient for that conclusion.

### Reference semantics

User-created organizational references may either follow `current_revision_id` or pin a revision explicitly. The resolution mode must be visible to the user.

Evidence claims, generated reports, exported citations, Agent outputs, and RAG citations always pin:

- `research_asset_id`;
- `asset_revision_id`;
- `asset_content_member_id` when content came from a member;
- `chunk_id` when content came from a parsed chunk.

Changing the current revision never rewrites a pinned reference.

## Governed Laboratory Knowledge Foundation

The governance release must establish the storage, indexing, identity, authorization, and event boundaries required for a future laboratory-wide knowledge experience.

The knowledge foundation has three coordinated planes:

### Global metadata index

The global metadata index contains sanitized catalog fields for every published Research Asset that is discoverable under the L0-L4 rules.

- Published L0-L2 assets and L3 assets without a matching explicit metadata deny are discoverable to authenticated laboratory members.
- L4 assets are included only for actors in their discovery scope.
- Draft, withdrawn, archived, and undiscoverable L4 assets do not leak through results, counts, facets, autocomplete, relation hints, or timing-sensitive fallback behavior.
- Metadata search does not require a project.
- A result includes safe access state and a direct access-request action when requestable.

### Governed content index

Every locally managed parseable member of a `ready` revision is chunked and indexed once under a trusted local system-ingestion context.

The system-ingestion context:

- may read local managed content only for validation, parsing, chunking, embedding, and index maintenance;
- is audited as `actor_type = "system"`;
- does not create a user grant;
- cannot answer a user query or bypass `KnowledgeQueryService`;
- follows the local-first and cloud-processing rules for raw content.

Indexing does not wait for a particular user to request access. Approving a grant therefore does not copy, reparse, rechunk, or re-embed content. The next query can use the existing chunks after live authorization succeeds.

Revocation, expiry, classification changes, explicit deny, withdrawal, and archival take effect through live query authorization. Correctness does not depend on deleting or rebuilding vectors. Asynchronous cleanup may remove obsolete vectors but is not an authorization mechanism.

### Research graph

The existing Research Object graph supplies semantic relations among:

- papers;
- Hypotheses;
- Evidence;
- Experiments;
- SOPs and protocols;
- Data Assets;
- reports;
- conclusions;
- other governed research objects.

A graph node or relation may participate in a query only when its catalog-visible endpoints are discoverable. Content-derived relation claims require authorized content sufficient to support the claim.

### Knowledge index events

Add a durable outbox-style `KnowledgeIndexEvent` record.

Required fields:

- `id`;
- `event_type`;
- `research_asset_id`, nullable for relation-only events;
- `asset_revision_id`, nullable;
- `asset_content_member_id`, nullable;
- `research_object_id`, nullable;
- `status`: `pending`, `processing`, `completed`, or `failed`;
- `attempt_count`;
- `last_error_code`, nullable;
- `created_at`;
- `processed_at`, nullable.

At least one of `research_asset_id`, `asset_revision_id`, `asset_content_member_id`, or `research_object_id` is required.

Supported events:

- `catalog_published`;
- `catalog_updated`;
- `revision_ready`;
- `current_revision_changed`;
- `classification_changed`;
- `catalog_withdrawn`;
- `asset_archived`;
- `relation_changed`.

Index events contain identifiers and safe operational state, never raw content, protected metadata, credentials, or storage locators. Business-state changes and their index events are committed in the same database transaction. Workers process events idempotently.

Access-request approval and grant revocation do not emit content reindex events because access is evaluated at query time.

### Query scopes

`KnowledgeQueryService` accepts an explicit query scope:

- `lab_global`: laboratory-wide metadata discovery without a project;
- `project`: metadata, graph, and authorized content retrieval under a selected project and declared purpose.

In `lab_global` scope:

- metadata discovery is available according to classification discovery rules;
- Public content and same-group Internal baseline content may be retrieved when their baseline and policies permit project-less use;
- Confidential, Restricted, and Top Secret content cannot be retrieved;
- a requestable protected result prompts the user to select a project, purpose, duration, capabilities, and revision.

In `project` scope:

- the user must be an active project member;
- content candidates must be project-linked;
- L2-L4 content requires a matching revision grant or explicit revision/cross-version policy;
- Data Use Agreement and Agent delegation conditions are evaluated;
- current or explicitly pinned revision selection is enforced.

### Governed query flow

Every combined knowledge query follows this order:

1. authenticate the user and validate `lab_global` or `project` scope;
2. search sanitized global metadata under live discovery rules;
3. load only discoverable Research Object relation hints;
4. resolve candidate revisions and processing state;
5. compute the user's authorized revision set for the scope, project, purpose, actor type, and time;
6. skip vector search when the authorized set is empty;
7. filter Qdrant by authorized asset, revision, and member identifiers;
8. reauthorize returned members before loading or returning chunk text;
9. merge metadata, graph, and content results with safe access state;
10. audit the query and every allowed or denied content read.

Safe result states are:

- `content_available`;
- `metadata_only`;
- `requestable`;
- `approval_pending`;
- `not_requestable`.

An undiscoverable L4 asset has no result state because it is absent.

Metadata-only results may state that a governed asset exists. They must not state or imply that inaccessible content supports, contradicts, or proves a research claim.

### Future AI Knowledge Layer contract

Future global search, assistants, and Agents must consume `KnowledgeQueryService`; they must not query PostgreSQL chunks, Qdrant, Sources, or Research Object content directly.

The future AI Knowledge Layer may:

- synthesize content from authorized results;
- show metadata-only and requestable results separately;
- pause and guide the user into the access-request workflow;
- resume a query after approval using the already indexed revision;
- produce pinned governed citations.

It may not use metadata-only assets as content evidence or infer hidden content from titles, relations, access state, or model prior knowledge.

## Agent and RAG Enforcement

Agents use delegated authorization:

- no Agent has a standing independent grant;
- each run carries the initiating user, project, purpose, and run identifier;
- the Agent's effective capabilities are the intersection of the user's grant and the run's declared capabilities;
- delegation may narrow permission but never expand it;
- `content:use_in_agent` is mandatory for content or vector retrieval;
- L4 Agent use requires an explicit capability even when the human can preview or download.

Agent flow:

1. read an authorized Hypothesis or task context;
2. search catalog metadata;
3. identify discoverable related Research Assets;
4. resolve the requested or current revision;
5. restrict candidates to assets linked to the current project;
6. call `AssetPolicyService` with `content:use_in_agent` for the initiating user and revision;
7. require revision `processing_state = "ready"`;
8. if allowed, retrieve bounded members through `GovernedContentGateway`;
9. if denied, catalog-only, or failed, use metadata-only wording and never query content vectors;
10. write an audit event with Agent run, initiating user, revision, and member identifiers.

Qdrant and RAG must not become bypasses:

- protected metadata must never be embedded into the catalog index;
- governed content chunks must carry Research Asset, revision, and content-member identifiers;
- retrieval must first intersect the current project's asset links, ready revision state, and the current user's authorized Research Asset revision set;
- Qdrant filters must limit retrieval to that set;
- revision-member and managed-source access checks must still run before returning chunks;
- empty authorization sets must skip content retrieval entirely.

`ProjectAssetLink` expresses project context only. It never grants content permission to other project members. A successful access request automatically links the asset to the selected project. A user may manually link an asset only when they have `content:use_in_agent` for at least one revision of that asset and are a member of the target project.

Session-level revision and member selection may further narrow the project candidate set but cannot expand it. Expiry, revocation, classification changes, or asset archival take effect on the next retrieval authorization check.

## API Design

All endpoints are under `/api/v1`.

### Research groups

- `GET /research-groups`
- `POST /research-groups`
- `GET /research-groups/{group_id}`
- `PUT /research-groups/{group_id}`
- `GET /research-groups/{group_id}/members`
- `POST /research-groups/{group_id}/members`
- `PUT /research-groups/{group_id}/members/{user_id}`
- `DELETE /research-groups/{group_id}/members/{user_id}`

### Research catalog

- `GET /research-explorer/search`
- `GET /research-assets/{research_asset_id}/catalog`
- `GET /research-assets/{research_asset_id}/revisions`
- `GET /research-assets/{research_asset_id}/revisions/{revision_id}`
- `POST /research-assets/{research_asset_id}/revisions`
- `POST /research-assets/{research_asset_id}/revisions/{revision_id}/publish`
- `PUT /research-assets/{research_asset_id}/governance`
- `POST /research-assets/{research_asset_id}/catalog/publish`
- `POST /research-assets/{research_asset_id}/catalog/withdraw`
- `POST /research-assets/{research_asset_id}/archive`

Dataset-specific registration and detail:

- `POST /data-assets`
- `GET /data-assets/{data_asset_id}`
- `PUT /data-assets/{data_asset_id}`

List and detail endpoints use actor-specific schemas. L4 unauthorized access returns 404.

### Policies and agreements

- `GET /research-assets/{research_asset_id}/policies`
- `POST /research-assets/{research_asset_id}/policies`
- `PUT /research-assets/{research_asset_id}/policies/{policy_id}`
- `POST /research-assets/{research_asset_id}/policies/{policy_id}/disable`
- `GET /data-use-agreements`
- `POST /data-use-agreements`
- `PUT /data-use-agreements/{agreement_id}`

### Requests and decisions

- `GET /access-requests`
- `POST /access-requests`
- `GET /access-requests/{request_id}`
- `POST /access-requests/{request_id}/submit`
- `POST /access-requests/{request_id}/cancel`
- `POST /access-requests/{request_id}/decision`

The list endpoint supports `mine`, `pending_my_approval`, and status filters.

### Grants

- `GET /access-grants`
- `POST /access-grants/proactive`
- `POST /access-grants/{grant_id}/revoke`

The proactive endpoint is limited to eligible L4 group PIs and Admin governance users.

### Content

- `GET /research-assets/{research_asset_id}/protected-metadata`
- `GET /research-assets/{research_asset_id}/revisions/{revision_id}/content`
- `GET /research-assets/{research_asset_id}/revisions/{revision_id}/members/{member_id}/content`
- `GET /research-assets/{research_asset_id}/revisions/{revision_id}/members/{member_id}/download`

The content endpoints support controlled preview and bounded Agent/RAG reads. Download uses a server-mediated stream for managed storage. All routes verify that the revision and member belong to the requested Research Asset.

For external storage, an allowed request returns a controlled handoff status and sanitized instructions. It never returns a credential or raw locator.

### Uploads

Existing personal Source, project-session, and laboratory-library upload endpoints remain available but must call one shared upload-validation and parser-routing service. Their responses use a common result schema containing Research Asset ID, revision ID, package or file name, member inspection results, acceptance status, processing state, and safe rejection reason.

### External references

- `POST /research-assets/external-references`
- `POST /research-assets/{research_asset_id}/snapshots`

External-reference registration accepts a URL, DOI, or approved public-publication metadata record and creates a metadata-only revision. It performs no automatic content download. Snapshot creation is an explicit user action that stores local managed content in a new revision.

### Knowledge foundation

- `POST /knowledge/search`
- `GET /admin/knowledge-index/status`
- `POST /admin/knowledge-index/retry`

`POST /knowledge/search` returns governed metadata, relation hints, authorized content snippets, pinned identifiers, and safe access state. It performs no LLM synthesis. It accepts `scope = "lab_global"` or `scope = "project"`; project scope requires project ID and purpose.

The Admin endpoints expose event counts, safe error codes, lag, and retry controls without content or protected metadata.

An LLM-synthesizing `/knowledge/query` endpoint is reserved for the future AI Knowledge Layer and is not part of V1.

### Audit

- `GET /asset-access-audit`

Audit query access is limited to:

- Admin governance users;
- owning-group PIs for their group;
- Asset Owners for their assets;
- individual users for their own request and access history.

### Error semantics

- `400`: invalid state transition, invalid capability, invalid member manifest, or invalid storage configuration.
- `403`: discoverable L0-L3 asset exists but the actor lacks the requested capability.
- `404`: missing asset, revision, or member; mismatched ownership path; or undiscoverable L4 asset.
- `409`: duplicate active request, conflicting decision, revision-number conflict, immutable sealed-content mutation, or concurrent current-revision change.
- `410`: optional content response when a previously issued external handoff has expired.

A safe `403` response may include `requestable`, `request_status`, and required approver types. It must not include protected metadata or policy internals.

## User Experience

### Navigation

Add:

- `Research Explorer`;
- `Access Requests`.

Keep `Lab Library` as the library-management and collection view. Research Explorer is the unified catalog search across all governed laboratory assets.

### Research Explorer

The page provides:

- laboratory-global server-side metadata search;
- filters for asset category, semantic subtype, member format, classification, group, project, processing state, and access status;
- result badges for classification and access state;
- upload and Data Asset registration actions for eligible users;
- safe metadata, relation, and authorized-content result sections from `KnowledgeQueryService`;
- cursor pagination.

All Research Asset results distinguish:

- available;
- requestable;
- pending approval;
- approved with expiry;
- policy-denied and not requestable.

L4 assets are absent unless discoverable.

When a global result requires L2-L4 content access, the UI asks the user to select an eligible project, revision, purpose, duration, and capabilities before submitting the request. Approval refreshes access state; it does not start a reindex job.

### Research Asset detail

The detail view shows:

- sanitized catalog metadata;
- owning group and steward;
- classification and lifecycle;
- safe access state;
- required approvals;
- related discoverable Research Objects;
- current revision, safe revision history, and sanitized member manifest;
- request, preview, download, or Agent-use actions based on effective capabilities.

Dataset results add Data Asset-specific scientific metadata, member roles, and controlled external handoff state.

Protected metadata uses a separate authenticated request and is never embedded in the initial page payload.

### Access request form

Required inputs:

- project;
- target revision;
- purpose;
- optional linked Hypothesis;
- capabilities;
- requested start;
- requested duration.

The form explains:

- which approvals are required;
- whether a collaboration agreement applies;
- that download is separately controlled;
- that Agent use is audited.

### Material creation actions

Eligible users can:

- upload a single file as one Research Asset revision;
- upload a ZIP as one Research Asset revision with multiple members;
- register URL, DOI, or public-publication metadata without fetching content;
- explicitly save a local web snapshot or imported full text as a new revision;
- save a generated project report, literature review, experiment design, or analysis report;
- save a research-memory object;
- explicitly save a conversation summary, note, draft, or conclusion;
- register experimental material or a specialized scientific-data package.

Ordinary conversation messages are not automatically materialized as Research Assets.

### Access Request Center

Tabs:

- Pending My Approval;
- My Requests;
- Active Grants;
- History.

Approvers see the request purpose, project, requester group role, requested capabilities, duration, applicable agreement, and prior approval steps. L3 approval and rejection require a comment. Proactive L4 grants require a separate mandatory grant reason.

### Internationalization

All user-facing strings use i18n keys in `en-US` and `zh-CN`. No new hardcoded UI strings are allowed.

## Upload and Processing Design

### Default governance on upload

Every successfully accepted logical material immediately creates a governed `ResearchAsset` and a sealed initial revision. A single-file upload creates one primary member. A ZIP upload creates one package member plus the validated extracted-member manifest under the same revision.

Default classification:

- personal upload: L3 Restricted;
- project or project-session upload: L2 Confidential;
- laboratory-library upload: L1 Internal.

The new asset inherits its owning group and baseline policy from the project context or explicit group selection. Every ZIP member inherits the single package asset's classification, steward, owning group, and policy because members are not independent assets.

The uploader may select an equal or more restrictive classification. Publishing as L0 requires explicit Asset Owner or PI confirmation that both the source and catalog metadata are public. L4 follows the hidden-catalog rules.

The minimal published catalog metadata contains only:

- sanitized filename or user-supplied title;
- asset type;
- approved description;
- file format;
- sanitized member-format summary;
- current revision number;
- upload time;
- owning group display name.

It excludes extracted text, raw file metadata, storage paths, checksums, and content-derived sensitive values.

### External-reference lifecycle

Registering a URL, DOI, or public-publication metadata record creates an `external_reference` asset with a sealed metadata-only revision. Registration never automatically downloads a webpage, PDF, or remote dataset.

The user may explicitly request:

- `Save web snapshot`;
- `Import full text`;
- `Attach local copy`.

A successful action creates a new revision containing the original external-reference member plus a managed `snapshot` or `primary` member. The prior metadata-only revision remains immutable and citable.

Only a revision with approved locally managed parsed content can enter full-text or vector RAG. A metadata-only external revision remains catalog-searchable but cannot support content claims.

External metadata distinguishes user-supplied fields from locally verified fields. Raw credentials, authenticated URLs, cookies, and remote storage tokens are never stored in catalog metadata or returned to clients.

### Parsed and RAG-ready formats

V1 accepts and parses these formats into bounded text suitable for RAG:

- `.pdf`;
- `.docx`;
- `.pptx`;
- `.txt`;
- `.md`;
- `.csv`;
- `.tsv`;
- `.xlsx`;
- `.json`;
- `.jsonl`.

Parser behavior:

- PDF uses the existing Marker-based path and fallback.
- DOCX extracts paragraphs and tables.
- PPTX extracts slide text and speaker notes.
- TXT and Markdown use bounded text decoding.
- CSV and TSV use streaming row extraction with column and cell limits.
- XLSX uses read-only workbook processing and never evaluates formulas.
- JSON and JSONL enforce nesting, record-count, and size limits before structured text conversion.

### Catalog-only formats

V1 accepts, stores, catalogs, authorizes, downloads, and links these formats to projects but does not automatically parse them for RAG:

- `.png`;
- `.jpg`;
- `.jpeg`;
- `.tif`;
- `.tiff`;
- `.wav`;
- `.mp3`;
- `.flac`;
- `.fasta`;
- `.fa`;
- `.fasta.gz`;
- `.fa.gz`;
- `.fastq`;
- `.fq`;
- `.fastq.gz`;
- `.fq.gz`;
- `.vcf`;
- `.vcf.gz`;
- `.bam`;
- `.bai`;
- `.sam`;
- `.cram`;
- `.crai`;
- `.bcf`;
- `.tbi`;
- `.csi`;
- `.bed`;
- `.gff`;
- `.gff3`;
- `.gtf`;
- `.seq`;
- `.ab1`.

These members use `processing_state = "catalog_only"`. A revision containing only catalog-only members resolves to `catalog_only`. It remains searchable in Research Explorer and may be modeled as a Data Asset, including voice sample libraries, alignment packages, and sequencing datasets.

The format registry is extensible, but V1 never accepts an unregistered extension under a generic binary type. Adding a new professional format requires explicit signature validation, size limits, member-role behavior, and tests.

Registered compound GZIP formats are scientific content members, not general archive uploads. V1 validates their compound extension and GZIP signature, stores them as catalog-only content, and does not recursively unpack them.

### ZIP behavior

ZIP remains supported as a single logical package:

- one accepted ZIP creates one Research Asset and one revision;
- the original ZIP is retained as the protected `package` member for exact reproduction;
- each safely extracted allowlisted file becomes another member of the same revision;
- normalized directory structure is retained only in member paths;
- ZIP directories do not create Collections or independent Research Assets;
- deterministic rules assign `primary`, `index`, `metadata`, `qc_report`, or `attachment` roles, and the final manifest is visible to the uploader before publication;
- nested ZIP files are rejected;
- path traversal, absolute paths, symlinks, duplicate normalized paths, and unsafe filenames are rejected;
- configurable limits apply to entry count, individual uncompressed size, total uncompressed size, and compression ratio;
- an archive-level or member-level validation failure rejects the entire temporary revision;
- no member is silently dropped;
- the API returns one asset/revision result plus safe member inspection results.

### Validation and isolation

The backend validates extension, declared MIME type, and detectable file signature. The frontend `accept` list is usability guidance only.

V1 rejects:

- legacy Office formats `.doc`, `.xls`, and `.ppt`;
- macro-enabled Office formats;
- executable or script containers;
- nested archives;
- unknown extensions;
- malformed files;
- files that exceed configured limits;
- extension, MIME, or signature combinations that indicate format spoofing.

Office container parsing must block macros, formula execution, external links, embedded executable objects, XML entity expansion, and archive bombs.

Files are processed with safe normalized names, non-executable storage permissions, bounded temporary workspace, and cleanup after completion. Client errors never reveal a server path or parser stack trace.

For ZIP, validation of the complete member manifest finishes before any revision is sealed or made current. A rejected package leaves no citable revision.

### Processing states

Supported revision and member processing states:

- `processing`;
- `ready`;
- `catalog_only`;
- `processing_failed`.

`catalog_only` is a successful terminal state, not an error. A revision becomes:

- `processing` while at least one parseable member is pending;
- `ready` when every parseable member is ready and at least one parseable member exists;
- `catalog_only` when no member has an approved parser;
- `processing_failed` when any expected parseable member fails.

`processing_failed` preserves the sealed revision, catalog record, content authorization, and member manifest while preventing that revision from entering RAG. Eligible owners can retry parsing without changing member content.

During compatibility, individual member processing may continue to use the linked Source state. The canonical aggregate state is on `AssetRevision` and is surfaced through the Research Asset response. Generated textual Research Objects resolve as `ready`. Metadata-only external references and unsupported-for-parsing Data Assets resolve as `catalog_only` unless a future approved parser produces governed chunks.

Project RAG uses only `ready` revisions and ready parsed members. A successful upload never implies content access beyond the asset and revision governance decision.

## Security Invariants

- Authorization is server-side and centralized.
- UI state is never an authorization source.
- Every Research Asset is governed; no asset type or origin is exempt.
- Existing Source preview, download, parsing, RAG, Agent, workflow, and chunk APIs must call the Research Asset policy layer.
- All metadata-plus-content search calls pass through `KnowledgeQueryService`; direct Qdrant access is not a supported application interface.
- Every content decision verifies that the requested revision and member belong to the authorized Research Asset.
- Ordinary grants are revision-specific; a new revision does not inherit an older grant.
- Sealed revision content references, member manifests, hashes, and paths are immutable.
- Existing `visibility_scope`, `SourceShare`, and `ProjectAssetLink` records provide migration input or project context only; they are not content-authorization bypasses.
- Search indexes only sanitized catalog metadata.
- Protected metadata, raw content, credentials, and locators never appear in application logs or ordinary error responses.
- Managed storage paths never appear in frontend responses.
- External locators are encrypted at rest using an application-managed encryption facility whose key is provided through environment configuration.
- L4 existence is protected across direct lookup, lists, counts, facets, exports, relation queries, and autocomplete.
- Explicit deny wins over allow.
- Missing allow results in deny.
- Grants are checked at every content fetch.
- Index presence and index-event completion are never treated as authorization evidence.
- Grant approval unlocks live queries and never triggers permission-specific content copies or indexes.
- RAG citations pin Research Asset, revision, member, and chunk identifiers.
- Audit writes do not include source content.
- Asset deletion does not cascade-delete audit history. Governed assets use withdrawal and archival; hard deletion is an Admin-only retention operation outside v1.

## Migration and Backfill

Every existing active `ResearchAsset` is migrated into the common governance model and becomes searchable according to L0-L4 discovery rules. Previously withdrawn assets remain governed and auditable but stay withdrawn from ordinary discovery.

Classification mapping:

- `lab_public` becomes L1 Internal;
- `lab_private` becomes L2 Confidential;
- `project` becomes L2 Confidential;
- `private` becomes L3 Restricted.

The migration does not create L0 or L4 classifications automatically.

For every existing Research Asset:

1. map the existing type to an `asset_category` and preserve the more specific value in `asset_type`;
2. map the existing active state to `catalog_status = "published"` and the existing withdrawn state to `catalog_status = "withdrawn"`;
3. set `lifecycle_status = "active"` unless the asset has been explicitly archived through governance;
4. set `governance_review_status = "pending"`;
5. set `steward_user_id` from the existing owner when valid;
6. infer `owning_group_id` only when the origin project has a configured research group;
7. create sealed revision 1 and a primary member from the existing Source or an immutable snapshot from the existing Research Object;
8. set `current_revision_id` to revision 1 only after its member reference validates;
9. populate catalog metadata from the current title, category, subtype, approved description, and safe timestamps;
10. exclude file content, extracted text, Source metadata, storage path, checksum, and internal processing details;
11. create compatibility policies that reproduce the current content audience without broadening it;
12. retain legacy source, object, visibility, and sharing fields for transitional reads only;
13. add missing group, steward, or content references to an Admin governance-review queue.

When both legacy `source_id` and `research_object_id` exist, revision 1 uses the Source as its primary content member and retains the Research Object as the semantic link. When only a Research Object exists, migration writes an immutable managed snapshot as the primary member.

After revision backfill, create idempotent `catalog_published`, `revision_ready`, and `relation_changed` index events as applicable. Existing vectors may be reused only after their Source, asset, revision, member, and chunk identity mapping validates; otherwise the revision is reindexed once under the system-ingestion context.

Existing type mapping:

- `uploaded_file` becomes `uploaded_material`;
- `external_reference` becomes `external_reference`;
- `generated_doc` and `report` become `generated_document`;
- `research_memory` remains `research_memory`;
- `protocol` becomes `experimental_material`;
- `dataset` becomes `scientific_data`.

Existing `collection` assets are withdrawn from ordinary material discovery. Their Source group and membership records remain available through the Collection UI. They receive no content revision, grant, or RAG eligibility.

Compatibility content policies preserve:

- all authenticated laboratory members for prior `lab_public` assets;
- PI/Admin and already-linked project members for prior `lab_private` assets;
- existing project members for prior `project` assets;
- only the existing owner for prior `private` assets.

For each existing Research Asset with `asset_type = "dataset"`:

1. create or reuse a `ResearchObject` with `type = "data_asset"`;
2. create a linked `DataAsset`;
3. create revision 1 with the existing Source as its primary managed member when valid;
4. otherwise retain the catalog record but require storage repair before content access.

Migrated L0-L3 assets are immediately discoverable with minimal sanitized metadata. Assets missing an owning group cannot gain broader content access or complete a new L3 approval until governance review is complete.

Backfill must be idempotent and record validation failures for Admin review without exposing protected metadata.

## Performance and Operational Requirements

- Explorer search uses cursor pagination.
- Default page size is 20; maximum is 100.
- Search columns and all foreign keys are indexed.
- Revision lookup uses `(research_asset_id, revision_number)` and current-revision indexes.
- Member lookup uses revision, managed-source, format, and role indexes.
- PostgreSQL JSON indexes cover only approved catalog fields.
- Policy decisions for result lists are batched to avoid N+1 queries.
- Knowledge-index workers are idempotent and retry failed events with bounded backoff.
- Index lag and failed-event counts are observable without exposing content.
- Read-path target remains under 200 ms for ordinary local catalog queries.
- Governed `/knowledge/search` performs no LLM call; its latency is bounded by metadata, policy, graph, and vector retrieval.
- Write-path target remains under 500 ms excluding external handoff operations.
- Content streaming does not load an entire file into API memory.
- Audit writes are part of the security event path; an access must fail closed if its required audit event cannot be persisted.
- The system remains functional without internet access.

## Testing Strategy

### Model and migration tests

- all tables, constraints, and indexes are registered;
- revision numbering and current-revision constraints are enforced;
- sealed content manifests are immutable;
- each content member has exactly one valid content mode;
- group membership uniqueness is enforced;
- every existing Research Asset receives governance fields;
- every content-bearing legacy asset receives a sealed revision 1 and correct primary member;
- legacy Collections remain organizational and do not gain content revisions;
- business changes and knowledge-index events commit atomically;
- knowledge-index event processing is idempotent and retryable;
- visibility-to-classification mapping is correct;
- catalog backfill contains only approved minimal fields;
- compatibility policies preserve existing readers without adding readers;
- missing groups enter the review queue without blocking safe discovery;
- dataset assets receive a Data Asset extension;
- backfill is safe and idempotent.

### Policy matrix tests

Cover every classification with:

- steward;
- owning-group PI;
- same-group Postdoc, PhD Student, Assistant, and External Collaborator;
- other-group members;
- project members and non-members;
- Admin governance user;
- valid, expired, and terminated agreements;
- each capability;
- scheduled, active, expired, and revoked grants;
- revision-scoped and explicit cross-version policies;
- a new revision that does not inherit an older grant;
- `lab_global` content behavior for Public, Internal, Confidential, Restricted, and Top Secret assets;
- project-scoped protected-content unlock after approval without a reindex;
- explicit allow and explicit deny.

### Workflow tests

- L1 cross-group Asset Owner approval;
- L2 Asset Owner or PI approval;
- L3 two distinct approvals;
- rejection at each required step;
- concurrent and repeated decisions;
- requester cancellation;
- request expiry;
- duplicate request conflict;
- current-revision change while a request remains bound to its submitted revision;
- proactive L4 grant;
- classification increase and asset archival revocation.

### Leakage and bypass tests

- L4 ID enumeration;
- L4 list, count, facet, relation, and autocomplete leakage;
- protected metadata serialization;
- source preview and download bypass;
- direct chunk and Qdrant retrieval bypass;
- mismatched asset, revision, member, and chunk identifiers;
- direct Qdrant and chunk access outside `KnowledgeQueryService`;
- L4 leakage through knowledge result counts, relation hints, and access-state aggregation;
- Agent use without `content:use_in_agent`;
- locator and path leakage through logs and errors;
- agreement mismatch;
- revoked grants during an Agent run.

### Upload and parser security tests

- every accepted extension and its expected `ready` or `catalog_only` result;
- registered compound scientific GZIP extensions and spoofed GZIP signatures;
- spoofed extension, MIME type, and file signature;
- malformed PDF, Office, JSON, spreadsheet, image, audio, and scientific-data files;
- CSV/TSV cell and row bounds;
- JSON/JSONL depth, record, and size bounds;
- Office macros, external links, formula non-execution, embedded executables, XML entity expansion, and archive bombs;
- ZIP path traversal, absolute paths, symlinks, duplicate normalized paths, nested ZIP, entry count, size, compression ratio, and total expansion limits;
- one ZIP producing exactly one asset, one revision, and a complete member manifest;
- any unsafe or unregistered ZIP member rejecting the entire temporary revision;
- deterministic package-member roles for BAM/BAI, sequencing, metadata, and QC combinations;
- bounded temporary storage and cleanup;
- large-file streaming without loading the entire file into API memory;
- project, personal, and library default governance classifications.

### API and UI tests

- Research Explorer search across every asset category and semantic subtype;
- governed `/knowledge/search` in `lab_global` and `project` scopes;
- metadata-only, requestable, approval-pending, and content-available result states;
- filters, cursor pagination, access badges, revision state, member format, and project-link state;
- revision timeline and sanitized member manifest disclosure;
- explicit save actions for generated documents, research memory, and conversation artifacts;
- redacted detail versus protected detail;
- request form validation;
- approval-center filters and decisions;
- grant expiry and revocation display;
- English and Chinese translation coverage;
- role-appropriate navigation and actions.

### End-to-end acceptance flow

The release is accepted when a test can:

1. create two research groups and representative roles;
2. migrate representative private, project, lab-private, and lab-public assets;
3. discover every migrated L0-L3 asset through sanitized catalog metadata;
4. fail to preview, download, or retrieve chunks for an unauthorized migrated asset;
5. upload DOCX and XLSX files that reach `ready`;
6. upload an audio file that reaches `catalog_only`;
7. upload one ZIP containing BAM, BAI, sample metadata, and a QC report and receive exactly one Data Asset revision with multiple members;
8. register a URL or DOI metadata-only asset and verify that it cannot enter full-text RAG;
9. explicitly save a local snapshot as a new immutable revision;
10. discover an L3 Data Asset as an unauthorized member without seeing protected fields;
11. submit a 30-day preview and Agent-use request for a project, Hypothesis, and specific revision;
12. complete distinct Asset Owner and PI approvals;
13. automatically link the approved asset to the selected project;
14. verify that laboratory-global search returns safe metadata but not L3 content;
15. preview bounded content and use it in a project-session RAG run with a citation that pins asset, revision, member, and chunk;
16. verify that approval reused the existing indexed chunks and created no permission-specific reindex;
17. publish a later revision and verify that the older grant does not authorize it;
18. observe audit events for global search, request, decisions, revision publication, human access, and Agent access;
19. revoke or expire the grant;
20. verify that subsequent human, chunk, RAG, and Agent access is denied without rebuilding the index;
21. verify that an undiscoverable L4 asset cannot be detected.

## Delivery Boundaries

This design is one product release but should be implemented in independently verifiable slices:

1. research groups and classification primitives;
2. material taxonomy, immutable revisions, content members, governance fields, and all-asset migration;
3. centralized revision-aware policy decisions and content gateway;
4. revision-scoped requests, approvals, grants, agreements, and audit;
5. durable knowledge-index events, system-ingestion indexing, and governed query service;
6. secure single-file, single-asset ZIP, external-reference, and parser routing;
7. Research Explorer, revision detail, material-save actions, and request-center UI;
8. project-link, Agent, RAG, Source, revision, member, and knowledge-query enforcement;
9. leakage tests, performance validation, and final end-to-end verification.

No slice is considered complete if a legacy Source or Agent endpoint can bypass the governance layer.
