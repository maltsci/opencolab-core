# User guide

This guide covers the current workspace. Available navigation and actions depend on your role, project membership, content grants and enabled tasks. The UI supports English and Simplified Chinese.

## First login and project setup

1. An administrator deploys the stack and signs in as `admin` using `OPENCOLAB_ADMIN_PASSWORD`.
2. Configure a working model under `/admin/llm-keys` and review `/admin/settings`. Test connectivity before using research or training generation.
3. Create user accounts and assign the appropriate Researcher, PI or Admin role.
4. Create a project from the home page, add members and describe the project in its instructions. Add plans as needed.
5. Open the project materials page and upload documents or link authorized library resources.

Operators should complete the [offline/data boundary checklist](deployment.md#offline-deployment-and-data-boundaries) before private material is uploaded.

## Manage documents and project materials

Use `/library` to upload and organize documents, inspect processing status, preview resources and manage collections. Supported text-document paths include PDF, DOCX, Markdown and TXT; ZIP and experimental data packages support grouped material workflows. Scanned PDF quality depends on configured OCR.

Set the appropriate classification and visibility during upload. A discoverable catalog entry does not necessarily include permission to read its content. Use the request-access action when offered; the owner/reviewer can grant access. Publishing or linking a resource to a project does not mean unrestricted content access.

Open `/projects/:projectId/assets` to inspect project materials. Check that required sources finished processing before using them as model context. Duplicate-upload guidance can identify an existing resource and explain whether you may reuse it or need permission. Resource previews expose available bibliographic metadata; review proposed metadata before applying it.

See [project material access](project-material-access.md) for the detailed grant model.

## Ask questions and run research tasks

1. Start or open a project session and select the sources relevant to the question.
2. Ask a focused question. Project QA retrieves context from permitted project materials and research memory.
3. Inspect citations and trace/evidence details alongside the answer. A generated answer is not a substitute for reading its supporting material.
4. Launch a recommended task where available, such as literature synthesis, finding gaps or proposing hypotheses. Review progress and result cards in the session/task workspace.
5. Preserve useful findings as research objects or project memory, and link relevant evidence/relations.

Projects can expose different recommended tasks. Administrators control task definitions and available skill packs. Task execution through Codex requires the runtime service and model connection; a working ordinary chat endpoint alone does not prove every task runtime is configured.

## Find laboratory knowledge and expertise

- `/assistant`: explore accessible knowledge and continue into relevant directories.
- `/research`: browse research directions and their linked projects, people and resources.
- `/people`: find expertise, representative resources, responsibilities and recent work.
- `/library`: browse papers, datasets, code repositories, model weights and other catalog resources.

Review resource access guidance before following a link. A GPU/catalog record describes a resource and its contact/access information; it does not allocate a machine.

## Contribute and maintain knowledge

Submit suggestions from supported research objects or knowledge pages. Suggestions can connect a finding/resource to a direction and enter scoped review. Use `/knowledge-governance` to follow your submissions, read decisions, and review items when authorized. PI/Admin and delegated stewards have different scopes.

Use `/maintenance` to find resources, directions and profiles requiring attention. Authorized PI/Admin users can inspect `/knowledge-health` for governance work and freshness indicators. Maintain representative resources and member profiles as research changes; preserve historical context through the supported lifecycle/archive actions.

## Learn from lab materials

Course managers use `/training/courses` to author a course, attach authorized resources, organize modules/units and knowledge points, review generated content, publish a version and assign learners. Generated lessons and assessments depend on the configured model and source evidence.

Learners start at `/training`, open their assigned course/module, read the lesson, ask questions, complete practice and assessments, and follow the next-step guidance. Use the content-language controls where available. PI/Admin users can inspect learner reports at `/training/reports/:traineeId`. Course publication and assignment/version state affect what is editable and which content a learner sees.

## Common issues

| Symptom | First check |
|---|---|
| A source is visible but content cannot be opened | Content grants and project access; request permission where offered |
| A source is absent from answers | Processing state, selected sources and project linkage |
| Chat or lessons fail | Active LLM profile, connectivity probe and API logs |
| Codex task fails | Runtime connectivity, authentication, shared workspace and model API compatibility |
| Knowledge review action is absent | Role or scoped stewardship |

Operators can continue with [deployment troubleshooting](deployment.md#troubleshooting); developers can use the [module map](modules.md) to locate code and regression coverage.
