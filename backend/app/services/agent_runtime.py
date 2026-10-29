from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.agents.base import (
    AgentDefinition,
    AgentExecutionResult,
    AgentInputPayload,
)
from app.services.agents.literature_synthesizer import run_literature_synthesizer
from app.services.agents.reviewer_assistant import run_reviewer_assistant

AGENT_REGISTRY: dict[str, AgentDefinition] = {}
BUILTIN_AGENT_DEFINITIONS = (
    AgentDefinition(
        name="literature_synthesizer",
        runner=run_literature_synthesizer,
    ),
    AgentDefinition(
        name="reviewer_assistant",
        runner=run_reviewer_assistant,
    ),
)


class UnknownAgentError(KeyError):
    """Raised when a requested agent name is not registered."""


class DuplicateAgentRegistrationError(ValueError):
    """Raised when an agent definition is registered more than once."""


def register_agent_definition(definition: AgentDefinition) -> None:
    if definition.name in AGENT_REGISTRY:
        raise DuplicateAgentRegistrationError(
            f"Agent already registered: {definition.name}"
        )
    AGENT_REGISTRY[definition.name] = definition


def get_agent_definition(agent_name: str) -> AgentDefinition:
    definition = AGENT_REGISTRY.get(agent_name)
    if definition is None:
        raise UnknownAgentError(f"Unknown agent: {agent_name}")
    return definition


def ensure_builtin_agents_registered() -> None:
    for definition in BUILTIN_AGENT_DEFINITIONS:
        AGENT_REGISTRY[definition.name] = definition


async def run_agent_definition(
    *,
    agent_name: str,
    source_ids: list[str],
    agent_input: AgentInputPayload,
    db: AsyncSession | None,
    llm_model: str | None,
    llm_api_base: str | None,
    llm_api_key: str | None,
    access_user_id: str | None = None,
    access_project_id: str | None = None,
    access_agent_run_id: str | None = None,
) -> AgentExecutionResult:
    ensure_builtin_agents_registered()
    definition = get_agent_definition(agent_name)
    return await definition.runner(
        source_ids=source_ids,
        agent_input=agent_input,
        db=db,
        llm_model=llm_model,
        llm_api_base=llm_api_base,
        llm_api_key=llm_api_key,
        access_user_id=access_user_id,
        access_project_id=access_project_id,
        access_agent_run_id=access_agent_run_id,
    )


ensure_builtin_agents_registered()
