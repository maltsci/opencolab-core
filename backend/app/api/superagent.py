from typing import Literal
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from pydantic import BaseModel

from app.api.projects import _get_project_for_user
from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.models.research_object import ResearchObject
from app.models.research_ticket import ResearchTicket
from app.models.session import Session
from app.models.user import User
from app.services.activity_service import log_activity
from app.services.manuscript_export_service import (
    render_manuscript_docx,
    render_manuscript_pdf,
)
from app.schemas.superagent import (
    DeepResearchLaunchRequest,
    ProjectPolicyResponse,
    ProjectPolicyUpdateRequest,
    ProjectTriggerResponse,
    ResearchCharterSuggestResponse,
    ResearchQuestionCreateRequest,
    ResearchQuestionCreateResponse,
    ResearchTicketCreateRequest,
    ResearchTicketResponse,
    SuperagentOverviewResponse,
    TicketAnswerRequest,
    TicketApproveRequest,
    TicketApproveResponse,
    TicketNextRoundRequest,
    TicketThreadMessageCreateRequest,
    TicketWetlabUploadRequest,
    TriggerEmitRequest,
    TriggerEmitResponse,
)
from app.services.superagent_service import (
    answer_ticket_attention,
    append_ticket_thread_message,
    approve_ticket_deliverable,
    build_policy_response,
    build_ticket_response,
    create_and_run_ticket,
    define_project_research_question,
    emit_project_trigger,
    get_or_create_project_policy,
    get_project_todos,
    get_superagent_overview,
    launch_academic_deep_research,
    open_or_get_ticket_session,
    precipitate_session_to_ticket,
    spawn_next_experiment_round,
    spawn_rebuttal_validation_ticket,
    suggest_project_research_charter,
    sync_stage_milestones,
    update_project_policy,
    upload_ticket_wetlab_results,
)

router = APIRouter(tags=["superagent"])


async def _load_ticket(
    project_id: str,
    ticket_id: str,
    db: AsyncSession,
) -> ResearchTicket:
    result = await db.execute(
        select(ResearchTicket)
        .options(
            selectinload(ResearchTicket.assignee),
            selectinload(ResearchTicket.creator),
        )
        .where(
            ResearchTicket.id == ticket_id,
            ResearchTicket.project_id == project_id,
        )
    )
    ticket = result.scalar_one_or_none()
    if ticket is None:
        raise HTTPException(status_code=404, detail="Research ticket not found")
    return ticket


@router.get(
    "/projects/{project_id}/superagent/overview",
    response_model=SuperagentOverviewResponse,
)
async def get_project_superagent_overview(
    project_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await _get_project_for_user(project_id, user.id, db)
    overview = await get_superagent_overview(db, project_id=project_id)
    await db.commit()
    return overview


@router.get(
    "/projects/{project_id}/superagent/policy",
    response_model=ProjectPolicyResponse,
)
async def get_project_superagent_policy(
    project_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await _get_project_for_user(project_id, user.id, db)
    policy = await get_or_create_project_policy(db, project_id)
    await db.commit()
    return build_policy_response(policy)


@router.put(
    "/projects/{project_id}/superagent/policy",
    response_model=ProjectPolicyResponse,
)
async def put_project_superagent_policy(
    project_id: str,
    body: ProjectPolicyUpdateRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await _get_project_for_user(project_id, user.id, db)
    resp = await update_project_policy(
        db,
        project_id=project_id,
        user=user,
        body=body,
    )
    await db.commit()
    return resp


@router.post(
    "/projects/{project_id}/superagent/questions/suggest",
    response_model=ResearchCharterSuggestResponse,
)
async def post_suggest_project_research_charter(
    project_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await _get_project_for_user(project_id, user.id, db)
    return await suggest_project_research_charter(
        db,
        project_id=project_id,
        user=user,
    )


@router.post(
    "/projects/{project_id}/superagent/questions",
    response_model=ResearchQuestionCreateResponse,
    status_code=status.HTTP_201_CREATED,
)
async def post_project_research_question(
    project_id: str,
    body: ResearchQuestionCreateRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await _get_project_for_user(project_id, user.id, db)
    research_object, ticket = await define_project_research_question(
        db,
        project_id=project_id,
        user=user,
        body=body,
    )
    await db.commit()
    ticket_resp = None
    if ticket is not None:
        loaded = await _load_ticket(project_id, ticket.id, db)
        ticket_resp = build_ticket_response(loaded)
    return ResearchQuestionCreateResponse(
        research_object={
            "id": research_object.id,
            "type": research_object.type,
            "title": research_object.title,
            "content": research_object.content,
            "content_json": research_object.content_json,
            "created_at": (
                research_object.created_at.isoformat()
                if research_object.created_at
                else None
            ),
        },
        ticket=ticket_resp,
    )


@router.post(
    "/projects/{project_id}/superagent/triggers",
    response_model=TriggerEmitResponse,
    status_code=status.HTTP_201_CREATED,
)
async def post_project_trigger(
    project_id: str,
    body: TriggerEmitRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await _get_project_for_user(project_id, user.id, db)
    trigger, ticket = await emit_project_trigger(
        db,
        project_id=project_id,
        user=user,
        source_kind=body.source_kind,
        event_type=body.event_type,
        title=body.title,
        payload=body.payload,
    )
    await db.commit()
    ticket_resp = None
    if ticket is not None:
        loaded = await _load_ticket(project_id, ticket.id, db)
        ticket_resp = build_ticket_response(loaded)
    return TriggerEmitResponse(
        trigger=ProjectTriggerResponse(
            id=trigger.id,
            project_id=trigger.project_id,
            source_kind=trigger.source_kind,
            event_type=trigger.event_type,
            actor_id=trigger.actor_id,
            title=trigger.title,
            payload=trigger.payload_json or {},
            disposition=trigger.disposition,
            decision_reason=trigger.decision_reason,
            matched_rule_id=trigger.matched_rule_id,
            ticket_id=trigger.ticket_id,
            created_at=trigger.created_at,
        ),
        ticket=ticket_resp,
    )


@router.post(
    "/projects/{project_id}/superagent/deep-research",
    response_model=ResearchTicketResponse,
    status_code=status.HTTP_201_CREATED,
)
async def post_launch_deep_research(
    project_id: str,
    body: DeepResearchLaunchRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await _get_project_for_user(project_id, user.id, db)
    ticket = await launch_academic_deep_research(
        db,
        project_id=project_id,
        user=user,
        body=body,
    )
    await db.commit()
    loaded = await _load_ticket(project_id, ticket.id, db)
    return build_ticket_response(loaded)


@router.get(
    "/projects/{project_id}/tickets",
    response_model=list[ResearchTicketResponse],
)
async def list_project_tickets(
    project_id: str,
    stage_category: str | None = Query(default=None),
    ticket_status: str | None = Query(default=None, alias="status"),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await _get_project_for_user(project_id, user.id, db)
    stmt = (
        select(ResearchTicket)
        .options(
            selectinload(ResearchTicket.assignee),
            selectinload(ResearchTicket.creator),
        )
        .where(ResearchTicket.project_id == project_id)
        .order_by(ResearchTicket.updated_at.desc(), ResearchTicket.created_at.desc())
    )
    if stage_category is not None:
        stmt = stmt.where(ResearchTicket.stage_category == stage_category)
    if ticket_status is not None:
        stmt = stmt.where(ResearchTicket.status == ticket_status)
    result = await db.execute(stmt)
    return [build_ticket_response(t) for t in result.scalars().all()]


@router.post(
    "/projects/{project_id}/tickets",
    response_model=ResearchTicketResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_project_ticket(
    project_id: str,
    body: ResearchTicketCreateRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await _get_project_for_user(project_id, user.id, db)
    policy = await get_or_create_project_policy(db, project_id)
    ticket = await create_and_run_ticket(
        db,
        project_id=project_id,
        user=user,
        title=body.title,
        stage_category=body.stage_category,
        mandate={
            "strength": "explicit",
            "policy_version": policy.version,
            "scope": body.goal or body.title,
        },
        iteration_round=body.iteration_round,
        parent_ticket_id=body.parent_ticket_id,
        plugin_id=body.plugin_id
        or (policy.enabled_plugins_json[0] if policy.enabled_plugins_json else None),
        assignee_id=body.assignee_id or user.id,
        initial_message=body.goal,
    )
    await db.commit()
    loaded = await _load_ticket(project_id, ticket.id, db)
    return build_ticket_response(loaded)


@router.get(
    "/projects/{project_id}/tickets/{ticket_id}",
    response_model=ResearchTicketResponse,
)
async def get_project_ticket(
    project_id: str,
    ticket_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await _get_project_for_user(project_id, user.id, db)
    ticket = await _load_ticket(project_id, ticket_id, db)
    return build_ticket_response(ticket)


@router.post(
    "/projects/{project_id}/tickets/{ticket_id}/answer",
    response_model=ResearchTicketResponse,
)
async def post_ticket_answer(
    project_id: str,
    ticket_id: str,
    body: TicketAnswerRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await _get_project_for_user(project_id, user.id, db)
    ticket = await _load_ticket(project_id, ticket_id, db)
    await answer_ticket_attention(
        db,
        ticket=ticket,
        user=user,
        body=body,
    )
    await db.commit()
    loaded = await _load_ticket(project_id, ticket_id, db)
    return build_ticket_response(loaded)


@router.post(
    "/projects/{project_id}/tickets/{ticket_id}/wetlab-upload",
    response_model=ResearchTicketResponse,
)
async def post_ticket_wetlab_upload(
    project_id: str,
    ticket_id: str,
    body: TicketWetlabUploadRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await _get_project_for_user(project_id, user.id, db)
    ticket = await _load_ticket(project_id, ticket_id, db)
    await upload_ticket_wetlab_results(
        db,
        ticket=ticket,
        user=user,
        body=body,
    )
    await db.commit()
    loaded = await _load_ticket(project_id, ticket_id, db)
    return build_ticket_response(loaded)




@router.post(
    "/projects/{project_id}/tickets/{ticket_id}/approve",
    response_model=TicketApproveResponse,
)
async def post_ticket_approve(
    project_id: str,
    ticket_id: str,
    body: TicketApproveRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await _get_project_for_user(project_id, user.id, db)
    ticket = await _load_ticket(project_id, ticket_id, db)
    merged_ticket, created_objects, next_ticket = await approve_ticket_deliverable(
        db,
        ticket=ticket,
        user=user,
        body=body,
    )
    await db.commit()
    loaded_merged = await _load_ticket(project_id, merged_ticket.id, db)
    next_ticket_resp = None
    if next_ticket is not None:
        loaded_next = await _load_ticket(project_id, next_ticket.id, db)
        next_ticket_resp = build_ticket_response(loaded_next)
    return TicketApproveResponse(
        ticket=build_ticket_response(loaded_merged),
        created_objects=[
            {
                "id": obj.id,
                "type": obj.type,
                "title": obj.title,
                "content": obj.content,
                "content_json": obj.content_json,
            }
            for obj in created_objects
        ],
        next_ticket=next_ticket_resp,
    )


@router.post(
    "/projects/{project_id}/tickets/{ticket_id}/next-round",
    response_model=ResearchTicketResponse,
    status_code=status.HTTP_201_CREATED,
)
async def post_ticket_next_round(
    project_id: str,
    ticket_id: str,
    body: TicketNextRoundRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await _get_project_for_user(project_id, user.id, db)
    parent_ticket = await _load_ticket(project_id, ticket_id, db)
    new_ticket = await spawn_next_experiment_round(
        db,
        parent_ticket=parent_ticket,
        user=user,
        body=body,
    )
    await db.commit()
    loaded = await _load_ticket(project_id, new_ticket.id, db)
    return build_ticket_response(loaded)


@router.post(
    "/projects/{project_id}/tickets/{ticket_id}/messages",
    response_model=ResearchTicketResponse,
)
async def post_ticket_thread_message(
    project_id: str,
    ticket_id: str,
    body: TicketThreadMessageCreateRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await _get_project_for_user(project_id, user.id, db)
    ticket = await _load_ticket(project_id, ticket_id, db)
    await append_ticket_thread_message(
        db,
        ticket=ticket,
        user=user,
        body=body,
    )
    await db.commit()
    loaded = await _load_ticket(project_id, ticket_id, db)
    return build_ticket_response(loaded)




@router.post(
    "/projects/{project_id}/tickets/{ticket_id}/stop",
    response_model=ResearchTicketResponse,
)
async def post_ticket_stop(
    project_id: str,
    ticket_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await _get_project_for_user(project_id, user.id, db)
    ticket = await _load_ticket(project_id, ticket_id, db)
    ticket.status = "ended"
    ticket.ended_outcome = "stopped"
    ticket.attention_json = None
    await db.commit()
    loaded = await _load_ticket(project_id, ticket_id, db)
    return build_ticket_response(loaded)


def _extract_figures_from_content_json(
    cjson: dict | None,
) -> list[dict]:
    if not isinstance(cjson, dict):
        return []
    figs = cjson.get("figures")
    if isinstance(figs, list) and figs:
        return [f for f in figs if isinstance(f, dict)]
    chart_svg = cjson.get("chart_svg")
    if isinstance(chart_svg, str) and "<svg" in chart_svg:
        return [{"title": "Figure 1", "svg": chart_svg}]
    return []


def _build_manuscript_export_response(
    *,
    title: str,
    markdown_text: str,
    figures: list[dict],
    export_format: Literal["pdf", "docx"],
    fallback_stem: str,
) -> Response:
    if export_format == "pdf":
        payload = render_manuscript_pdf(
            title=title,
            markdown_text=markdown_text,
            figures=figures,
        )
        media_type = "application/pdf"
        ext = "pdf"
    else:
        payload = render_manuscript_docx(
            title=title,
            markdown_text=markdown_text,
            figures=figures,
        )
        media_type = (
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        )
        ext = "docx"

    safe_stem = "".join(c if c.isalnum() or c in ("-", "_") else "_" for c in fallback_stem)[:64] or "manuscript"
    encoded_name = quote(f"{title[:80]}.{ext}")
    return Response(
        content=payload,
        media_type=media_type,
        headers={
            "Content-Disposition": (
                f'attachment; filename="{safe_stem}.{ext}"; filename*=UTF-8\'\'{encoded_name}'
            )
        },
    )


@router.get("/projects/{project_id}/superagent/manuscripts/{object_id}/export")
async def export_manuscript_object(
    project_id: str,
    object_id: str,
    format: Literal["pdf", "docx"] = Query("pdf"),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await _get_project_for_user(project_id, user.id, db)
    obj = await db.get(ResearchObject, object_id)
    if obj is None:
        raise HTTPException(status_code=404, detail="Manuscript object not found")
    cjson = obj.content_json if isinstance(obj.content_json, dict) else {}
    if cjson.get("project_id") != project_id:
        raise HTTPException(status_code=404, detail="Manuscript object not found")
    markdown_text = (obj.content or "").strip()
    if not markdown_text:
        raise HTTPException(status_code=400, detail="Manuscript content is empty")
    figures = _extract_figures_from_content_json(cjson)
    return _build_manuscript_export_response(
        title=obj.title or "Manuscript Draft",
        markdown_text=markdown_text,
        figures=figures,
        export_format=format,
        fallback_stem=f"manuscript_{obj.id[:8]}",
    )


@router.get("/projects/{project_id}/tickets/{ticket_id}/export")
async def export_ticket_manuscript(
    project_id: str,
    ticket_id: str,
    format: Literal["pdf", "docx"] = Query("pdf"),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await _get_project_for_user(project_id, user.id, db)
    ticket = await _load_ticket(project_id, ticket_id, db)
    deliverable = ticket.deliverable_json if isinstance(ticket.deliverable_json, dict) else {}
    markdown_text = str(deliverable.get("markdown_report") or "").strip()
    if not markdown_text:
        raise HTTPException(status_code=400, detail="Ticket deliverable has no manuscript content")
    proposed = deliverable.get("proposed_objects") or []
    first_cjson = (
        proposed[0].get("content_json")
        if proposed and isinstance(proposed[0], dict)
        else {}
    )
    figures = _extract_figures_from_content_json(first_cjson)
    if not figures:
        figures = _extract_figures_from_content_json(deliverable.get("data_cross_validation"))
    await log_activity(
        db,
        project_id=project_id,
        actor_id=user.id,
        action="manuscript_exported",
        target_type="research_ticket",
        target_id=ticket.id,
        target_title=f"{ticket.short_key} ({format.upper()})",
    )
    await db.commit()
    return _build_manuscript_export_response(
        title=str(deliverable.get("title") or ticket.title or "Manuscript Draft"),
        markdown_text=markdown_text,
        figures=figures,
        export_format=format,
        fallback_stem=f"{ticket.short_key}_manuscript",
    )


class PrecipitateSessionRequest(BaseModel):
    session_id: str
    summary: str | None = None
    create_research_object: bool = True


@router.get("/projects/{project_id}/superagent/todos")
async def get_project_superagent_todos(
    project_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await _get_project_for_user(project_id, user.id, db)
    return await get_project_todos(db, project_id=project_id)


@router.post("/projects/{project_id}/superagent/plans/sync-milestones")
async def post_sync_stage_milestones(
    project_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await _get_project_for_user(project_id, user.id, db)
    milestones = await sync_stage_milestones(
        db,
        project_id=project_id,
        actor_id=user.id,
        only_if_empty=False,
    )
    await db.commit()
    return {"milestones": milestones}


@router.post("/projects/{project_id}/tickets/{ticket_id}/open-session")
async def post_ticket_open_session(
    project_id: str,
    ticket_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await _get_project_for_user(project_id, user.id, db)
    ticket = await _load_ticket(project_id, ticket_id, db)
    session = await open_or_get_ticket_session(
        db,
        project_id=project_id,
        ticket=ticket,
        user=user,
    )
    await db.commit()
    return {
        "session_id": session.id,
        "title": session.title,
        "ticket_id": ticket.id,
        "ticket_short_key": ticket.short_key,
    }


@router.post("/projects/{project_id}/tickets/{ticket_id}/precipitate-session")
async def post_ticket_precipitate_session(
    project_id: str,
    ticket_id: str,
    body: PrecipitateSessionRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await _get_project_for_user(project_id, user.id, db)
    ticket = await _load_ticket(project_id, ticket_id, db)
    session = await db.get(Session, body.session_id)
    if session is None or session.project_id != project_id:
        raise HTTPException(status_code=404, detail="Session not found in project")
    try:
        updated_ticket, created_obj = await precipitate_session_to_ticket(
            db,
            project_id=project_id,
            ticket=ticket,
            session=session,
            user=user,
            summary=body.summary,
            create_research_object=body.create_research_object,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    await db.commit()
    loaded = await _load_ticket(project_id, updated_ticket.id, db)
    return {
        "ticket": build_ticket_response(loaded),
        "research_object_id": created_obj.id if created_obj else None,
    }


class RebuttalValidationRequest(BaseModel):
    focus_comment: str | None = None


@router.post(
    "/projects/{project_id}/tickets/{ticket_id}/rebuttal-validation",
    response_model=ResearchTicketResponse,
    status_code=status.HTTP_201_CREATED,
)
async def post_ticket_rebuttal_validation(
    project_id: str,
    ticket_id: str,
    body: RebuttalValidationRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await _get_project_for_user(project_id, user.id, db)
    parent_ticket = await _load_ticket(project_id, ticket_id, db)
    new_ticket = await spawn_rebuttal_validation_ticket(
        db,
        parent_ticket=parent_ticket,
        user=user,
        focus_comment=body.focus_comment,
    )
    await db.commit()
    loaded = await _load_ticket(project_id, new_ticket.id, db)
    return build_ticket_response(loaded)
