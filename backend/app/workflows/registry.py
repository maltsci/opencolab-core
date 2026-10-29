from collections.abc import Awaitable

from sqlalchemy.ext.asyncio import AsyncSession

from app.schemas.workflow import WorkflowDefinition
from app.workflows.builtin import BUILTIN_WORKFLOW_DEFINITIONS


class UnknownWorkflowError(KeyError):
    pass


def _build_registry(
    definitions: list[WorkflowDefinition],
) -> dict[str, WorkflowDefinition]:
    registry: dict[str, WorkflowDefinition] = {}
    for definition in definitions:
        if definition.id in registry:
            raise ValueError(f"duplicate workflow definition id: {definition.id}")
        registry[definition.id] = definition
    return registry


_WORKFLOW_DEFINITIONS = _build_registry(BUILTIN_WORKFLOW_DEFINITIONS)


def _copy_definition(definition: WorkflowDefinition) -> WorkflowDefinition:
    return definition.model_copy(deep=True)


def has_builtin_workflow_definition(id: str) -> bool:
    return id in _WORKFLOW_DEFINITIONS


def list_workflow_definitions(
    db: AsyncSession | None = None,
) -> list[WorkflowDefinition] | Awaitable[list[WorkflowDefinition]]:
    # The db parameter is kept for caller compatibility; only the code-builtin
    # registry is served.
    if db is None:
        return [
            _copy_definition(definition)
            for definition in _WORKFLOW_DEFINITIONS.values()
        ]

    async def _load() -> list[WorkflowDefinition]:
        return [
            _copy_definition(definition)
            for definition in _WORKFLOW_DEFINITIONS.values()
        ]

    return _load()


def get_workflow_definition(
    id: str,
    db: AsyncSession | None = None,
) -> WorkflowDefinition | Awaitable[WorkflowDefinition]:
    # The db parameter is kept for caller compatibility; only the code-builtin
    # registry is served.
    if db is None:
        try:
            return _copy_definition(_WORKFLOW_DEFINITIONS[id])
        except KeyError as exc:
            raise UnknownWorkflowError(id) from exc

    async def _load() -> WorkflowDefinition:
        try:
            return _copy_definition(_WORKFLOW_DEFINITIONS[id])
        except KeyError as exc:
            raise UnknownWorkflowError(id) from exc

    return _load()
