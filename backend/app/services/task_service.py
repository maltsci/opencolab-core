from sqlalchemy import String, cast, exists, func, literal, or_, select
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.task_definition import TaskDefinitionRecord
from app.schemas.task import TaskDefinition, TaskDefinitionCreate, TaskDefinitionUpdate
from app.workflows.registry import UnknownWorkflowError, get_workflow_definition


DEFAULT_RESEARCH_TASKS: list[dict] = [
    {
        "id": "project-qa",
        "version": 1,
        "name": "项目问答",
        "description": "针对当前项目的文档和研究记忆提问，获得基于项目上下文的回答。",
        "workflow_id": "literature_synthesizer",
        "input_schema": {
            "type": "object",
            "required": ["query"],
            "properties": {"query": {"type": "string"}},
        },
        "starter_prompts": [
            "请基于当前项目的文档和研究记忆回答我的问题，并说明结论依据。",
        ],
        "project_context_policy": {
            "inherit_project_sources": True,
            "include_research_memory": True,
        },
        "result_presentation": {
            "type": "assistant_message",
            "runtime": "codex",
            "primary_output_key": "answer",
        },
        "is_enabled": True,
        "project_ids": [],
    },
    {
        "id": "literatures-briefs",
        "version": 1,
        "name": "文献综述",
        "description": "阅读当前项目文档，综合已有研究脉络、关键观点、矛盾点和研究空白。",
        "workflow_id": "literature_synthesizer",
        "input_schema": {
            "type": "object",
            "required": ["query"],
            "properties": {"query": {"type": "string"}},
        },
        "starter_prompts": [
            "请基于当前项目文档写一份文献综述，覆盖主要观点、证据、争议和研究空白。",
        ],
        "project_context_policy": {
            "inherit_project_sources": True,
            "include_research_memory": True,
        },
        "result_presentation": {
            "primary_output_key": "overview",
            "sections": ["key_points", "contradictions", "gaps"],
        },
        "is_enabled": True,
        "project_ids": [],
    },
    {
        "id": "core-ideas",
        "version": 1,
        "name": "提炼核心观点",
        "description": "从当前项目材料中提炼核心观点、关键论据和可继续追问的问题。",
        "workflow_id": "literature_synthesizer",
        "input_schema": {
            "type": "object",
            "required": ["query"],
            "properties": {"query": {"type": "string"}},
        },
        "starter_prompts": [
            "请列出当前项目文档的核心观点，并说明每个观点依赖的主要证据。",
        ],
        "project_context_policy": {
            "inherit_project_sources": True,
            "include_research_memory": True,
        },
        "result_presentation": {
            "primary_output_key": "overview",
            "sections": ["key_points", "gaps"],
        },
        "is_enabled": True,
        "project_ids": [],
    },
    {
        "id": "research-gaps",
        "version": 1,
        "name": "发现研究空白",
        "description": "基于当前项目文档寻找尚未解决的问题、证据不足处和潜在选题方向。",
        "workflow_id": "literature_synthesizer",
        "input_schema": {
            "type": "object",
            "required": ["query"],
            "properties": {"query": {"type": "string"}},
        },
        "starter_prompts": [
            "请基于当前项目文档找出值得继续研究的空白、矛盾和可验证问题。",
        ],
        "project_context_policy": {
            "inherit_project_sources": True,
            "include_research_memory": True,
        },
        "result_presentation": {
            "primary_output_key": "gaps",
            "sections": ["overview", "key_points", "contradictions"],
        },
        "is_enabled": True,
        "project_ids": [],
    },
    {
        "id": "hypothesis-generator",
        "version": 1,
        "name": "生成研究假设",
        "description": "把项目文档中的发现和空白转化为可讨论、可验证的研究假设，并区分已观察证据、合理推测和待补变量。",
        "workflow_id": "literature_synthesizer",
        "input_schema": {
            "type": "object",
            "required": ["query"],
            "properties": {"query": {"type": "string"}},
        },
        "starter_prompts": [
            "请根据当前项目文档提出可验证的研究假设。每条假设需区分已观察证据、合理推测、待补变量和验证方案；不要把重复实验直接推断为统计显著，也不要把抗体生成直接推断为抗体验证成功。",
        ],
        "project_context_policy": {
            "inherit_project_sources": True,
            "include_research_memory": True,
        },
        "result_presentation": {
            "primary_output_key": "overview",
            "suggest_memory_type": "hypothesis",
        },
        "is_enabled": True,
        "project_ids": [],
    },
    {
        "id": "experiment-design",
        "version": 1,
        "name": "实验设计建议",
        "description": "围绕项目中的假设或问题，生成实验变量、对照、数据采集和验证思路。",
        "workflow_id": "literature_synthesizer",
        "input_schema": {
            "type": "object",
            "required": ["query"],
            "properties": {"query": {"type": "string"}},
        },
        "starter_prompts": [
            "请基于当前项目文档设计一个可执行的实验方案，包括变量、对照、数据和验证标准。",
        ],
        "project_context_policy": {
            "inherit_project_sources": True,
            "include_research_memory": True,
        },
        "result_presentation": {
            "primary_output_key": "overview",
            "sections": ["key_points", "gaps"],
        },
        "is_enabled": True,
        "project_ids": [],
    },
]


async def associate_tasks_to_project(
    db: AsyncSession,
    task_ids: list[str],
    project_id: str,
) -> None:
    """Associate task definitions with a project.

    Only tasks with an explicit (non-empty) project scope are updated — global
    tasks (empty project_ids) are already visible in every project. Only
    flushes; the caller commits.
    """
    if not task_ids:
        return
    result = await db.execute(
        select(TaskDefinitionRecord).where(TaskDefinitionRecord.id.in_(task_ids))
    )
    for record in result.scalars().all():
        project_ids = list(record.project_ids or [])
        if project_ids and project_id not in project_ids:
            project_ids.append(project_id)
            record.project_ids = project_ids
    await db.flush()


class UnknownTaskDefinitionError(KeyError):
    pass


class DuplicateTaskDefinitionError(ValueError):
    pass


class BuiltInTaskDefinitionError(ValueError):
    pass


def _record_to_definition(record: TaskDefinitionRecord) -> TaskDefinition:
    definition = TaskDefinition.model_validate(record)
    return definition.model_copy(
        update={"is_builtin": record.id in _default_task_payloads_by_id()}
    )


def _payload_to_definition(payload: dict) -> TaskDefinition:
    return TaskDefinition.model_validate(
        {
            **payload,
            "is_builtin": payload["id"] in _default_task_payloads_by_id(),
        }
    )


def _default_task_payloads_by_id() -> dict[str, dict]:
    return {payload["id"]: payload for payload in DEFAULT_RESEARCH_TASKS}


def _is_global_default_task(payload: dict) -> bool:
    return not payload.get("project_ids")


def _global_project_scope_clause(
    db: AsyncSession,
):
    dialect_name = db.bind.dialect.name if db.bind is not None else ""
    if dialect_name == "postgresql":
        return func.jsonb_array_length(cast(TaskDefinitionRecord.project_ids, JSONB)) == 0
    return TaskDefinitionRecord.project_ids == []


def _project_contains_clause(
    db: AsyncSession,
    project_id: str,
):
    dialect_name = db.bind.dialect.name if db.bind is not None else ""

    if dialect_name == "postgresql":
        return cast(TaskDefinitionRecord.project_ids, JSONB).contains([project_id])

    json_each = func.json_each(TaskDefinitionRecord.project_ids).table_valued("value")
    return exists(
        select(literal(1))
        .select_from(json_each)
        .where(cast(json_each.c.value, String) == project_id)
    )


def _project_scope_clause(
    db: AsyncSession,
    *,
    project_id: str | None,
):
    if project_id is None:
        return _global_project_scope_clause(db)

    return or_(
        _global_project_scope_clause(db),
        _project_contains_clause(db, project_id),
    )


async def list_enabled_task_definitions(
    db: AsyncSession,
    *,
    project_id: str | None = None,
) -> list[TaskDefinition]:
    result = await db.execute(
        select(TaskDefinitionRecord)
        .where(_project_scope_clause(db, project_id=project_id))
        .order_by(TaskDefinitionRecord.id)
    )
    all_records = list(result.scalars().all())
    # A DB record always overrides the code default, even when disabled —
    # otherwise a disabled default task would reappear from DEFAULT_RESEARCH_TASKS.
    record_ids = {record.id for record in all_records}
    records = [
        _record_to_definition(record) for record in all_records if record.is_enabled
    ]
    defaults = [
        _payload_to_definition(payload)
        for payload in DEFAULT_RESEARCH_TASKS
        if payload["id"] not in record_ids
        and payload.get("is_enabled", True)
        and _is_global_default_task(payload)
    ]
    return sorted([*records, *defaults], key=lambda item: item.id)


async def list_all_task_definitions(db: AsyncSession) -> list[TaskDefinition]:
    result = await db.execute(
        select(TaskDefinitionRecord).order_by(TaskDefinitionRecord.id)
    )
    records = [_record_to_definition(record) for record in result.scalars().all()]
    record_ids = {record.id for record in records}
    defaults = [
        _payload_to_definition(payload)
        for payload in DEFAULT_RESEARCH_TASKS
        if payload["id"] not in record_ids
    ]
    return sorted([*records, *defaults], key=lambda item: item.id)


async def seed_default_task_definitions(db: AsyncSession) -> None:
    """Ensure the default user-facing research tasks exist."""
    for payload in DEFAULT_RESEARCH_TASKS:
        record = await db.scalar(
            select(TaskDefinitionRecord).where(TaskDefinitionRecord.id == payload["id"])
        )
        if record is None:
            db.add(TaskDefinitionRecord(**payload))
            continue

        if not record.starter_prompts:
            record.starter_prompts = payload["starter_prompts"]
        if not record.project_context_policy:
            record.project_context_policy = payload["project_context_policy"]
        if not record.result_presentation:
            record.result_presentation = payload["result_presentation"]
        if not record.input_schema:
            record.input_schema = payload["input_schema"]

    await db.commit()


async def get_task_definition(
    task_id: str,
    db: AsyncSession,
    *,
    include_disabled: bool = False,
    project_id: str | None = None,
) -> TaskDefinition:
    stmt = select(TaskDefinitionRecord).where(TaskDefinitionRecord.id == task_id)
    stmt = stmt.where(_project_scope_clause(db, project_id=project_id))
    result = await db.execute(stmt)
    record = result.scalar_one_or_none()
    if record is not None:
        # A DB record always overrides the code default, even when disabled.
        if not record.is_enabled and not include_disabled:
            raise UnknownTaskDefinitionError(task_id)
        return _record_to_definition(record)

    default_payload = _default_task_payloads_by_id().get(task_id)
    if (
        default_payload is not None
        and (include_disabled or default_payload.get("is_enabled", True))
        and (
            project_id is not None
            or _is_global_default_task(default_payload)
        )
    ):
        return _payload_to_definition(default_payload)

    raise UnknownTaskDefinitionError(task_id)


async def create_task_definition(
    body: TaskDefinitionCreate,
    db: AsyncSession,
) -> TaskDefinition:
    existing = await db.execute(
        select(TaskDefinitionRecord.id).where(TaskDefinitionRecord.id == body.id)
    )
    if existing.scalar_one_or_none() is not None or body.id in _default_task_payloads_by_id():
        raise DuplicateTaskDefinitionError(body.id)

    try:
        await get_workflow_definition(body.workflow_id, db)
    except UnknownWorkflowError as exc:
        raise ValueError(f"Referenced workflow not found: {body.workflow_id}") from exc

    record = TaskDefinitionRecord(**body.model_dump())
    db.add(record)
    await db.commit()
    await db.refresh(record)
    return _record_to_definition(record)


async def update_task_definition(
    task_id: str,
    body: TaskDefinitionUpdate,
    db: AsyncSession,
) -> TaskDefinition:
    result = await db.execute(
        select(TaskDefinitionRecord).where(TaskDefinitionRecord.id == task_id)
    )
    record = result.scalar_one_or_none()
    if record is None:
        raise UnknownTaskDefinitionError(task_id)

    update_data = body.model_dump(exclude_unset=True, exclude_none=True)
    if "workflow_id" in update_data:
        try:
            await get_workflow_definition(update_data["workflow_id"], db)
        except UnknownWorkflowError as exc:
            raise ValueError(f"Referenced workflow not found: {update_data['workflow_id']}") from exc

    for key, value in update_data.items():
        setattr(record, key, value)

    await db.commit()
    await db.refresh(record)
    return _record_to_definition(record)


async def delete_task_definition(
    task_id: str,
    db: AsyncSession,
) -> None:
    if task_id in _default_task_payloads_by_id():
        raise BuiltInTaskDefinitionError(task_id)

    result = await db.execute(
        select(TaskDefinitionRecord).where(TaskDefinitionRecord.id == task_id)
    )
    record = result.scalar_one_or_none()
    if record is None:
        raise UnknownTaskDefinitionError(task_id)

    await db.delete(record)
    await db.commit()
