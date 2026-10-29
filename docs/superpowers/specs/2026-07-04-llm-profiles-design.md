# OpenColab LLM Profiles Design

Date: 2026-07-04
Status: Draft approved for planning

## Summary

OpenColab's current LLM admin experience exposes the same concepts in two places:

- `LLM API Keys` stores provider credentials and endpoint details.
- `System Settings` stores the active model, API base, selected key, and an optional raw API key.

This creates duplicated fields, unclear precedence, and a fragile mental model. Users are forced to ask which value actually wins:

- the saved key or the raw API key
- the profile API base or the settings API base
- the selected model or the manually typed model

This design replaces the current split with a clearer runtime model:

- `LLM Profiles` represent reusable model instances.
- `System Settings` chooses the active profile.
- the only advanced runtime override kept in the UI is `Model Override`

The design also formalizes two separate validation steps:

1. the endpoint can list models
2. the selected model can actually complete a chat request

That distinction is required because the current LiteLLM and upstream debugging showed a real failure mode:

- `/models` works
- `chat/completions` times out or fails

The UI must surface that difference explicitly.

## Goals

1. Remove duplicate LLM configuration fields from the default admin workflow.
2. Make one profile represent one reusable model instance.
3. Let users fetch supported models from the configured endpoint instead of typing them by hand in the common path.
4. Preserve a minimal advanced override for temporary debugging.
5. Keep compatibility with the existing runtime config and deployment shape while preparing for future project-level profile selection.

## Non-Goals

This change does not include:

- project-level active profile selection in v1 of this redesign
- removal of all runtime fallbacks from backend code on day one
- redesign of embedding configuration
- redesign of non-LLM admin settings
- automatic repair of broken LiteLLM upstream deployments

## Product Model

### LLM Profile

An `LLM Profile` is the unit users create, test, reuse, and activate.

Each profile binds the full model instance required for chat:

- `name`
- `provider`
- `api_base`
- `api_key`
- `model`

Optional metadata is also stored for health and observability:

- `status`
- `last_tested_at`
- `last_test_result`

`name` is a display label only. It must not be treated as the model name.

Examples:

- `Healwrap GLM-5`
- `OpenAI GPT-4o Mini`
- `Local Ollama Llama3`
- `LiteLLM Proxy Default`

### Active Profile

The system chooses one global active profile at runtime.

For now:

- `active_llm_profile_id` is global

For future expansion:

- the design must leave room for project-specific profile overrides without changing the profile abstraction itself

### Advanced Override

The only advanced override retained in `System Settings` is:

- `Model Override`

The purpose is temporary debugging or experimentation:

- try another model on the same provider instance
- compare one model against another without editing the saved profile

The UI will not expose:

- `API Base Override`
- `API Key Override`

Those paths are too easy to misuse and recreate the duplication problem.

## User Experience

### Primary Flow

The common admin flow becomes:

1. Create a profile
2. Fill `provider`, `api_base`, and `api_key`
3. Click `Fetch Models`
4. Choose a model from the returned list
5. Click `Test Model`
6. Save the profile
7. Set it as active

The system should no longer require the user to visit multiple pages and re-enter the same endpoint configuration.

### LLM Profiles List

Replace `LLM API Keys` with `LLM Profiles`.

Columns:

- `Name`
- `Provider`
- `Model`
- `API Base`
- `Status`
- `Last Tested`
- `Actions`

Actions:

- `Create`
- `Edit`
- `Test`
- `Set Active`
- `Delete`

`Set Active` should be available directly from the list so that users do not need a second trip through settings for the normal case.

### Create / Edit Profile Modal

Base fields:

- `Provider`
- `Name`
- `API Base`
- `API Key`

Model fields:

- `Fetch Models`
- `Available Models` dropdown

Advanced section:

- `Manual Model Input`

The common path is explicit and deterministic:

- users first provide connection details
- users then fetch the list
- users finally select one model

Manual model typing remains available only as an escape hatch when the upstream provider cannot list models.

### System Settings > LLM

Default section:

- `Active Profile`

Advanced section:

- `Model Override`

This is the entire default mental model:

- create or edit reusable profiles in one place
- select which one the system runs with in another place

The settings page should not show `API Base URL`, `API Key`, or default `LLM Model` as peer fields in the default experience.

## Validation Model

The UI and backend must distinguish connection success from model usability.

### Test Connection

Purpose:

- verify that the endpoint is reachable
- verify that credentials are accepted
- verify that the endpoint can return a model list

Result states:

- `connection_ok`
- `auth_failed`
- `network_error`
- `timeout`

### Fetch Models

Purpose:

- load supported model identifiers from the configured endpoint

Behavior:

- store the fetched list in UI state
- do not treat "models listed" as proof that a model is healthy for completions

### Test Model

Purpose:

- send a minimal chat completion probe against the selected model

This is the required gate for marking a profile as ready for runtime use.

Result states:

- `model_ready`
- `model_unhealthy`
- `auth_failed`
- `timeout`
- `network_error`

User-facing examples:

- `Ready`
- `Listed but unhealthy`
- `Authentication failed`
- `Request timed out`
- `Network error`

This design is intentionally shaped by the current observed failure mode:

- the endpoint can list `glm-5`
- the endpoint does not successfully return chat completions in the expected window

That should show as `Listed but unhealthy`, not as a generic success.

## Data Model

Add a new `llm_profiles` table.

Suggested fields:

- `id`
- `name`
- `provider`
- `api_base`
- `encrypted_key`
- `model`
- `status`
- `last_tested_at`
- `last_test_result`
- `created_at`
- `updated_at`

Suggested status enum values:

- `unknown`
- `connection_ok`
- `model_ready`
- `model_unhealthy`
- `auth_failed`
- `timeout`
- `network_error`

Runtime config keys:

- `active_llm_profile_id`
- `llm_model_override`

## API Design

Introduce profile-oriented admin APIs.

### CRUD

- `GET /api/v1/admin/llm-profiles`
- `POST /api/v1/admin/llm-profiles`
- `PUT /api/v1/admin/llm-profiles/{id}`
- `DELETE /api/v1/admin/llm-profiles/{id}`

### Actions

- `POST /api/v1/admin/llm-profiles/fetch-models`
- `POST /api/v1/admin/llm-profiles/test-connection`
- `POST /api/v1/admin/llm-profiles/test-model`
- `POST /api/v1/admin/llm-profiles/{id}/activate`

### Config

Keep the existing config API surface, but narrow the LLM-related payload:

- `GET /api/v1/admin/config`
- `PUT /api/v1/admin/config`

Relevant fields after redesign:

- `active_llm_profile_id`
- `llm_model_override`

## Runtime Resolution

The new runtime resolution order should be:

1. `llm_model_override`, if present
2. `active_llm_profile.model`
3. `active_llm_profile.api_base`
4. `active_llm_profile.api_key`
5. existing environment and legacy runtime fallbacks

This keeps compatibility while making the new model the clear default path.

## Migration Strategy

The rollout should avoid breaking working deployments.

### Step 1: Add Profile Storage

- add `llm_profiles`
- keep `llm_keys` and current runtime fields temporarily

### Step 2: Migrate Existing Keys

Each `LLMKey` becomes an `LLMProfile`.

Mapping:

- `name` -> `name`
- `provider` -> `provider`
- `api_base` -> `api_base`
- `encrypted_key` -> `encrypted_key`
- current resolved `llm_model` -> `model`
- `status` -> `unknown`

### Step 3: Migrate Active Runtime Selection

Map:

- `llm_key_id` -> `active_llm_profile_id`

Keep old fields readable by backend fallback logic during the transition period.

### Step 4: Narrow the UI

- replace the `LLM API Keys` page with `LLM Profiles`
- remove duplicated LLM connection fields from the default settings view
- keep only `Active Profile` and advanced `Model Override`

## LiteLLM and Upstream Debugging Implications

The new design does not assume LiteLLM is always the problem or always correct.

It explicitly supports the current observed possibilities:

1. provider config is wrong
2. LiteLLM deployment health evaluation is wrong
3. upstream endpoint lists models but fails on completions
4. credentials are valid for listing but not for generation

The system must therefore persist separate evidence for:

- model listing success
- completion probe success

This makes diagnosis visible in the admin UI instead of requiring backend log inspection for common failure modes.

## Implementation Plan Shape

Recommended delivery order:

1. `Step 1: Information Architecture`
   - rename keys to profiles
   - add model field
   - add active profile concept
   - narrow settings UI

2. `Step 2: Model Discovery and Validation`
   - fetch models
   - test connection
   - test model
   - persist health state

3. `Step 3: Migration and Compatibility`
   - migrate legacy keys
   - support fallback resolution
   - keep existing deployments running during transition

## Risks

1. Some providers will not support consistent model listing.
   - manual model input must remain available in advanced mode

2. A provider may list models but reject completions.
   - this is why `Test Model` is mandatory for trust

3. Existing runtime config fields may still leak into the UI if the migration is incomplete.
   - frontend and backend rollout must be coordinated

4. Users may confuse "active profile" with "default provider for all future projects".
   - copy should state that this is the current global runtime default

## Success Criteria

The redesign is successful when:

1. a user can configure a working LLM without entering the same endpoint details in multiple places
2. the default settings page no longer shows duplicate `model`, `api_base`, and `api_key` concepts
3. the admin UI clearly distinguishes:
   - endpoint reachable
   - models listed
   - model actually usable for chat
4. existing deployments can migrate without losing active runtime behavior
5. future project-level profile selection remains possible without redesigning the profile abstraction
