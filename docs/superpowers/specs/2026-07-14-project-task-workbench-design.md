# OpenColab Project Task Workbench Design

Date: 2026-07-14
Status: Draft approved for planning

## Summary

This design moves OpenColab from an agent- and runtime-shaped product surface toward a project-centered task workbench for everyday researchers.

The current visible product shape is still too close to implementation concepts:

```text
Agent
Skill
Workflow
Run
```

The target visible product shape should instead be:

```text
Project
Task
Task Conversation
Research Memory
```

The core product decision is:

> Ordinary researchers should never need to understand skills, workflows, or agents in order to get value from OpenColab.

Those concepts remain important, but they belong in the admin studio and runtime layer, not in the primary user journey.

## Product Goal

OpenColab is already project-based, document-grounded, and session-capable. The next step is not more admin surfaces. The next step is to make the main user experience feel like:

> "Inside my project, I can describe what I want to do, choose a suggested research task, and collaborate with the system in a task-specific workspace that uses my project materials as context."

This should make the product understandable without training on internal abstractions.

## Product Framing

The user clarified an important product boundary:

> OpenColab is not just a task launcher layered on top of documents. It is a vertical research environment where project materials define the working model context for every research task.

This means the product should be understood as a domain-specific scientific counterpart to Codex:

```text
General Codex
  repo / files / runtime / code changes

OpenColab
  project / documents / research memory / task execution
```

The project is therefore not a navigation convenience. It is the durable scientific environment in which tasks, workflows, and underlying skills operate.

## Primary Users

### Researcher

The researcher:

- works inside a project
- expects project files and prior work to define the working context
- wants to complete concrete tasks
- does not want to configure runtime abstractions

Typical jobs:

- summarize project literature
- draft reviewer responses
- identify gaps or contradictions
- compare selected papers
- answer questions from project materials

### Administrator

The administrator:

- installs or manages skills
- assembles workflows
- publishes task templates
- controls which tasks are available in which projects

The administrator should see the power surface. The researcher should not.

## Product Position

### Visible product

For researchers, OpenColab should present itself as:

```text
OpenColab = project-scoped scientific task workbench
```

### Hidden implementation layer

Internally, task execution may still use:

- skills
- workflows
- runtime step execution
- traces
- research memory writeback

But those concepts should be translated into a simpler user-facing model.

## Core User Model

### Project

A project is the primary working context.

It contains:

- linked documents and files
- project sessions
- project-scoped research memory
- published tasks available to members
- task run history

For the researcher, the project answers:

> "What materials and prior work should the system use while helping me?"

More concretely, the project behaves like a research execution environment:

- uploaded papers define literature context
- linked sources define evidence context
- previous runs define working continuity
- research memory defines durable derived context
- future experiment data will define validation context

This is why project context must stay primary even as the UI becomes more task-oriented.

### Task

A task is the primary user-facing action surface.

A task is not a raw skill and not a raw workflow. A task is a published productized entry point that tells the user:

- what kind of research job this does
- what inputs it expects
- what kind of output it produces
- what project context it uses

Examples:

- Literature Review
- Reviewer Response
- Hypothesis Generation
- Evidence Synthesis
- Compare Papers
- Project Q&A

### Task Conversation

A task conversation is the main execution workspace.

It is a task-shaped conversation tied to:

- one project
- one selected task
- one run history
- optional selected sources

It should feel like a task-oriented assistant rather than a generic chat window.

### Research Memory

Research memory remains the durable state layer.

Task outputs may write into:

- discussions
- hypotheses
- claims
- notes
- relations

But this is not just a persistence layer. It is also the project-scoped research history layer that future runs and conversations should consult by default.

In practice, research memory should capture:

- prior interpretations
- accepted or rejected hypotheses
- evidence-linked findings
- previous task conclusions
- research decisions and their rationale

This makes it function as:

> project-scoped scientific working memory

It is still not the first thing the user sees, but it should be a default part of the hidden context the system uses while helping the user.

## Canonical Relationship Between Skill Pack, Task, Workflow, and Agent Runtime

The product should standardize on the following model.

### Skill Pack

A skill is a user-installable capability package.

This matches the mainstream Codex-style skill mental model:

```text
download skill
install skill
enable it in a project
use it as a task
```

For product language, `skill` should mean this installable package, not a hand-authored internal execution schema.

Examples:

- literature synthesis skill pack
- reviewer response skill pack
- PubMed search skill pack
- data analysis skill pack
- manuscript drafting skill pack

Internally, a skill pack may contain:

- `SKILL.md`
- scripts
- dependencies
- routing metadata
- tool permissions
- output contracts
- one or more task templates

But ordinary users should not have to assemble those pieces manually.

### Workflow

A workflow is an executable composition of steps and referenced capabilities.

It is an admin/runtime abstraction, not a researcher-facing concept.

It answers:

> "How is this task executed?"

### Task

A task is the researcher-facing published wrapper around a skill pack or workflow.

It answers:

> "What kind of job can I do in this project?"

This is the main user-facing abstraction.

In the normal user path, installing a skill pack should result in one or more usable task entries. The product should not require users to first understand workflow assembly.

### Agent

Agent should stop being the primary product abstraction.

In the target model:

```text
Agent = optional compatibility label or legacy wrapper
```

If the term remains at all, it should behave as a behind-the-scenes implementation detail or transition alias.

### Final mapping

The user-facing system should conceptually work like this:

```text
Install Skill Pack -> Enable In Project -> Use Task -> Task Conversation
```

The internal system may still work like this:

```text
Skill Pack
  -> runtime skills / tools / prompts
  -> optional workflow
  -> published task
  -> task conversation
```

Where:

- admins install or approve skill packs
- admins may tune workflows for advanced cases
- admins publish task entries to projects
- researchers use tasks without seeing runtime internals

## UX Direction Chosen

The user explicitly chose the following front-door pattern:

```text
Project page = large input box + recommended tasks
Task page = chat-style task workspace
```

This means the product should not open on a catalog of runtime objects. It should open on work initiation.

## Frontstage vs Backstage

### Researcher frontstage

Researchers should see:

- project overview
- large task prompt box
- recommended task cards
- recent task runs
- research memory
- task conversation pages

Researchers should not be asked to manage:

- skills
- workflows
- runtime config
- execution graphs

### Admin backstage

Admins should see:

- skill installation and registry
- workflow assembly
- task publishing
- project task availability settings
- task and workflow diagnostics

## Information Architecture

## Researcher IA

Top-level concepts:

1. Projects
2. Tasks
3. Runs
4. Research Memory

The project should remain the default home for work.

### Project Home

The project page becomes the main launch surface.

Primary sections:

1. Project header
2. Large task input box
3. Recommended tasks
4. Project materials summary
5. Recent runs
6. Recent memory

The ordering here matters. The user explicitly chose a project-first experience, but also clarified that the project exists in order to support research work on project materials. Therefore:

> Project home should be task-first within a project-first product.

This means the researcher first chooses a project, then immediately sees what research work can be performed in that environment.

### Task Workspace

This is a chat-style task page, not an admin form page.

Primary sections:

1. task header
2. conversation/result stream
3. contextual side panel
4. follow-up input

### Runs

Runs remain visible, but as user work history rather than runtime mechanics.

The user should recognize:

- what task was run
- in what project
- what happened
- whether it finished

### Research Memory

Research memory should continue to surface key derived outputs and relations, but it should connect back to tasks and runs rather than feeling like a separate expert-only subsystem.

## Admin IA

Top-level concepts:

1. Skills
2. Workflows
3. Tasks
4. Project Task Access
5. Runtime / Settings

The current skill and workflow admin work can remain, but it should clearly move under an admin studio mental model.

## Project Home Design

## Core intent

The project home must answer:

> "What can I do in this project right now?"

### First viewport

The first screen should include:

- project name and brief summary
- large prompt box with a task-oriented placeholder
- recommended task cards directly below the prompt
- visible reminder that tasks will use current project materials

Example placeholder:

```text
Describe what you want to do in this project
```

This is intentionally broad. The user can start naturally, then pick a suggested task.

The first viewport should communicate a strong mental model:

```text
You are inside a research environment.
These tasks will run on the materials and history of this project.
```

That context signal is essential. Otherwise the page looks like a generic AI prompt box rather than a project-scoped scientific workspace.

### Recommended task cards

Task cards should be the main structured choice surface.

Each card should show:

- task name
- one-line purpose
- expected output shape
- optional hint about project materials used

Example cards:

- Literature Review
- Reviewer Response
- Hypothesis Generation
- Evidence Synthesis
- Compare Papers
- Project Q&A

These cards are not generic skills. They are project-aware research actions. Their framing should emphasize concrete outcomes such as:

- produce a literature synthesis from project papers
- identify contradictions across selected materials
- draft a reviewer response from project context
- compare evidence and extract research gaps

### Launch patterns

The user explicitly chose:

> Large input box plus user-selected recommended task

So the first version should support two launch flows.

#### Flow A: prompt first, task second

1. user types a freeform request
2. system highlights relevant suggested tasks
3. user chooses one task
4. system opens the task workspace with the prompt carried forward

#### Flow B: task first

1. user clicks a recommended task
2. system opens the task workspace
3. initial prompt box inside the workspace asks for the first request

The system may later add automatic routing, but v1 should not depend on silent task classification.

## Task Workspace Design

## Core intent

The task page should feel like:

> "I am collaborating with a project-aware task specialist."

It should not feel like:

- a raw chat window
- a backend debugger
- a workflow builder

It should feel like a specialist workbench inside the current research environment.

### Main region

The main conversation region should show:

- the initial task prompt
- execution progress and generated outputs
- structured result blocks when useful
- follow-up requests and responses

This region must support both:

- reading a task result
- continuing the task through follow-up prompts

### Right side panel

The side panel should show task context, not admin concepts.

Suggested sections:

- current project
- selected documents or active project materials
- task parameters
- output target
- save to research memory
- execution details link

This keeps operational context visible without overwhelming the main conversation flow.

The side panel exists to answer:

> "What is this task using from my project, and what will happen to the result?"

### Execution visibility

Workflow details should remain secondary.

Researchers may see:

- task status
- concise step progress
- evidence basis

They should not be forced to parse:

- workflow identifiers
- skill identifiers
- raw payloads
- internal runtime graphs

## Task Publishing Model

This design introduces one more explicit product object:

### TaskDefinition

A task definition is the user-facing published wrapper around a workflow.

Minimum fields:

- `id`
- `name`
- `description`
- `workflow_id`
- `input_schema`
- `starter_prompts`
- `project_context_policy`
- `result_presentation`
- `is_enabled`

This is distinct from `WorkflowDefinition`.

Reason:

- workflows answer execution concerns
- tasks answer product and UX concerns

Without `TaskDefinition`, the product will keep leaking runtime abstractions into the UI.

## Project Context Policy

Tasks run inside a project context. That context should be explicit.

Each task should define how it uses project context:

- all project sources by default
- selected sources only
- project research memory included
- previous task conversations included or excluded

This avoids ambiguity around what "project-aware" means.

The user should always understand:

> "This task is using materials from this project."

The longer-term interpretation is broader:

> "This task is running inside a project-scoped scientific model environment."

Today that environment is mostly documents, sessions, and research memory. Later it will also include experiment plans, experimental datasets, comparisons, validations, and manuscript artifacts.

The product language should be ready for that expansion now.

## Research Memory Runtime Role

The user explicitly clarified that research memory should influence both:

1. task and agent execution
2. ordinary day-to-day project conversation

This means research memory is not merely an archive of outputs. It is a default reference layer for the model.

The default runtime behavior should therefore be:

```text
project documents + project research memory + current user request
  -> task execution and project conversation context
```

This allows the system to remember not only source material, but also:

- what the team already considered
- what was rejected and why
- what evidence chains already exist
- what conclusions are tentative versus accepted

Without this layer, the assistant behaves like it has read the files. With this layer, it behaves like it has participated in the research process.

### Default inclusion rule

The user chose the following default:

```text
Research memory is included automatically in task and conversation context by default.
```

Advanced controls may later let the user narrow or disable memory for a specific run, but opt-in should not be required for normal usage.

## Home Page Priority Decision

The user explicitly resolved the project-home priority question as:

```text
Project home inside a selected project:
  1. task panel is primary
  2. document/material context is secondary but always visible
```

This means the page should not default to a materials-management view.

Documents are essential, but they are supporting context for the research workbench. The primary question the page should answer is:

> "What research task do you want to perform in this project?"

The secondary question is:

> "Which project materials will support that task?"

## Skill Installation Direction

The user explicitly wants future support for installing skills from the internet in a Codex-like way.

This means the long-term admin model should be:

1. discover or import skill
2. inspect metadata and trust boundary
3. install locally
4. generate or expose task templates
5. optionally attach to or refine workflow
6. publish as task
7. expose task to selected projects

Important product rule:

> Installing a skill is not the end-user feature. Publishing a usable task is.

This prevents the product from becoming an expert-only toolbox.

### Skill terminology decision

The user chose:

```text
skill = user-installable capability package
```

Therefore, the previously introduced schema-like skill concept should be treated as an internal runtime detail and renamed in implementation/design language when needed:

- `Skill Pack`: user-facing installable capability
- `Runtime Skill`: internal execution unit or prompt/tool bundle
- `Task`: published project action created from a skill pack or workflow

This avoids making OpenColab feel harder to use than mainstream Codex skill installation.

## Agent Runtime Selection

The user asked whether the `malt-be` Codex runtime approach can be used in OpenColab.

Decision:

```text
OpenColab should adopt the malt-be style Codex delegated runtime for v1/v1.5 execution,
while keeping research state and product abstractions in OpenColab core.
```

The inspected `malt-be` implementation uses:

- API-side OpenAI Agents SDK
- Codex MCP over HTTP
- a sandbox sidecar that proxies to local Codex stdio MCP
- `SKILL.md` skill packs synced into the sandbox runtime
- per-session workspaces
- streamed Codex events
- artifact registration
- forced cwd and execution policy

This is a good fit for OpenColab's early local/team edition because it can quickly cover:

- document worker tasks
- file generation
- Python and shell execution
- data analysis
- report generation
- skill pack execution
- streamed execution traces

### Boundary

Codex runtime should be a delegated execution worker, not the platform brain.

OpenColab core must continue to own:

- Project
- Documents
- Task
- Research Memory
- ResearchObject
- Evidence
- Hypothesis
- WorkflowRun
- Permission
- Audit
- Writeback policy

Codex runtime may own:

- executing an approved task prompt
- invoking installed skill packs
- reading and writing task workspace files
- running scripts
- producing artifacts
- returning structured execution summaries
- streaming progress events

### Runtime contract

The preferred contract is:

```text
OpenColab Core
  -> run_task({
       project_context,
       document_context,
       research_memory_snapshot,
       task_spec,
       skill_pack_policy,
       allowed_tools,
       output_schema,
       writeback_contract
     })

Codex Runtime Worker
  -> {
       result,
       artifacts,
       evidence,
       proposed_memory_writebacks,
       execution_events,
       usage
     }

OpenColab Core
  -> validate, persist, audit, and write back
```

This keeps the scientific object graph and long-term memory under OpenColab control.

### Sandbox backend evolution

For the first local/team version, the malt-be style Codex sandbox sidecar is a practical runtime backend.

For stricter multi-tenant or production SaaS deployments, the sandbox layer should evolve toward per-task isolation. CubeSandbox remains a good candidate for this later sandbox backend layer, but it should not replace OpenColab's research runtime or memory model.

## Scope for the Next Major Iteration

### In scope

- Reframe the primary user journey around tasks
- Add a project home with large prompt plus recommended tasks
- Make the project home task-first while keeping project context primary
- Add a chat-style task workspace
- Introduce `TaskDefinition` as a product-layer object
- Keep skill/workflow configuration in admin surfaces
- Let task workspaces trigger workflow runs
- Show project context and recent runs in user language

### Out of scope

- Full skill marketplace UX
- One-click internet skill install
- Automatic task routing without user confirmation
- Visual workflow builder for ordinary users
- Exposing skills or workflows in the researcher navigation
- Replacing all legacy session behavior at once

## Migration Strategy

The product should migrate in layers instead of rewriting everything at once.

### Phase 1: Product-language transition

- introduce task language in the UI
- keep current runtime underneath
- add recommended tasks on the project page
- keep sessions functioning

### Phase 2: Task-backed workspaces

- task click launches a task-shaped conversation page
- workflow execution happens from the task page
- runs are shown as task runs

### Phase 3: Admin publishing model

- admin defines task wrappers around workflows
- project-level task availability is configurable
- researcher sees only published tasks

### Phase 4: Skill ecosystem expansion

- support imported skills
- improve workflow assembly
- add safer install and review flows

## Success Criteria

This direction is successful when:

- a researcher can start useful work from a project page without learning skill or workflow concepts
- the first decision is "what task do I want to do?" rather than "which runtime abstraction should I choose?"
- project materials clearly act as the task context
- the project feels like a scientific working environment rather than a document bucket
- task results remain traceable and can still write into research memory
- admins retain control over capabilities without exposing implementation complexity to everyday users

## Open Questions Resolved

The following decisions are now fixed for the next version:

- primary audience: ordinary researchers
- front-door pattern: large input box plus recommended tasks
- task page mode: chat-style workspace
- admin-only concepts: skills and workflows
- project role: default task context container

## Recommended Next Deliverables

1. A frontend information architecture plan for the researcher-facing surfaces
2. A `TaskDefinition` backend and API design
3. A project-home UI implementation plan with task-first layout and materials-as-context
4. A task-workspace UI implementation plan
5. An admin publishing flow that binds workflow to task and task to project
