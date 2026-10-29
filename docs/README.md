# OpenColab documentation

Start with the [project overview](../README.md) and [development history](../CHANGELOG.md). This index separates current operational guides from historical designs. The core source baseline is OpenColab commit `4fa8324`; extraction date: 2026-10-29.

## Start here

| Need | Guide |
|---|---|
| Install, configure or upgrade | [Deployment](deployment.md) |
| Work with projects, materials, tasks and training | [User guide](user-guide.md) |
| Understand services, storage and data flows | [Architecture](architecture.md) |
| Find a module, its dependencies and implementation | [Module guide](modules.md) |
| Develop, test or contribute | [Development](development.md) |

## Access and knowledge governance

- [Sharing and permissions](sharing-and-permissions.md) / [Chinese](sharing-and-permissions.zh-CN.md).
- [Project permissions](project-permissions.md) / [Chinese](project-permissions.zh-CN.md).
- [Project material access](project-material-access.md).
- [Lab knowledge security contract](lab-knowledge-os-v1-security-contract.md).
- [Lab knowledge migration runbook](lab-knowledge-os-v1-migration-runbook.md).

For current authorization behavior, also consult the module guide and security contract: older sharing documents do not describe every later asset-policy extension.

## Repository extraction

[Core extraction and maintenance](core-extraction.md) records the source baseline, excluded modules, database boundary, validation and future synchronization approach.

## API reference

A running FastAPI service exposes Swagger UI at `/docs`, ReDoc at `/redoc`, and its schema at `/openapi.json`. Application routes use `/api/v1`; see [`backend/app/main.py`](../backend/app/main.py) for router registration. Default Compose API address: [http://localhost:8431/docs](http://localhost:8431/docs).

## Design archive

[`superpowers/specs/`](superpowers/specs/) and [`superpowers/plans/`](superpowers/plans/) retain product proposals and implementation plans. They help explain decisions but are not current user or operator instructions. Task handoff and acceptance documents in this directory likewise retain their original scope. Resolve discrepancies against current code, the module guide, and the recorded workflow version of a run.
