import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.research_object import ResearchObject
from app.models.research_ticket import ResearchTicket
from app.models.message import Message
from app.models.user import User

pytestmark = pytest.mark.asyncio


async def test_workspace_linkage_todos_milestones_and_sessions(
    client: AsyncClient,
    db: AsyncSession,
    researcher_user: User,
    researcher_headers: dict,
):
    # 1. Create a project
    proj_resp = await client.post(
        "/api/v1/projects",
        json={
            "name": "Workspace Linkage Integration Project",
            "description": "Verify unified milestones, todos, activity, and session precipitation",
        },
        headers=researcher_headers,
    )
    assert proj_resp.status_code == 201
    project_id = proj_resp.json()["id"]

    # 2. Sync 5-stage milestones (and verify idempotency)
    sync_resp = await client.post(
        f"/api/v1/projects/{project_id}/superagent/plans/sync-milestones",
        headers=researcher_headers,
    )
    assert sync_resp.status_code == 200
    milestones = sync_resp.json()["milestones"]
    assert len(milestones) == 5
    assert {m["stage_category"] for m in milestones} == {
        "problem_framing",
        "baseline_reproduction",
        "innovation_feasibility",
        "experiment_iteration",
        "manuscript_writing",
    }

    sync_again = await client.post(
        f"/api/v1/projects/{project_id}/superagent/plans/sync-milestones",
        headers=researcher_headers,
    )
    assert sync_again.status_code == 200
    assert len(sync_again.json()["milestones"]) == 5

    # 3. Create a ticket in person / answer state so it appears in unified todos
    ticket_resp = await client.post(
        f"/api/v1/projects/{project_id}/tickets",
        json={
            "title": "Select primary selectivity metric",
            "stage_category": "problem_framing",
            "mandate_text": "Decide between SI >= 10 and MIC <= 4 ug/mL",
            "mandate_strength": "explicit",
        },
        headers=researcher_headers,
    )
    assert ticket_resp.status_code == 201
    ticket_id = ticket_resp.json()["id"]

    # Move ticket into person / answer state so it appears in unified todos
    ticket_row = (
        await db.execute(
            select(ResearchTicket).where(ResearchTicket.id == ticket_id)
        )
    ).scalar_one()
    ticket_row.status = "open"
    ticket_row.attention_json = {
        "kind": "decision",
        "prompt": "Confirm target selectivity threshold?",
        "options": ["SI >= 10", "SI >= 20"],
    }
    await db.commit()

    # 4. Fetch unified todos
    todos_resp = await client.get(
        f"/api/v1/projects/{project_id}/superagent/todos",
        headers=researcher_headers,
    )
    assert todos_resp.status_code == 200
    todos_data = todos_resp.json()
    assert todos_data["ticket_todo_count"] >= 1
    assert todos_data["plan_todo_count"] == 5
    assert todos_data["total_count"] == (
        todos_data["ticket_todo_count"] + todos_data["plan_todo_count"]
    )
    assert any(t["ticket_id"] == ticket_id for t in todos_data["ticket_todos"])

    # 5. Open a ticket-linked discussion session (and verify reuse)
    open_sess_resp = await client.post(
        f"/api/v1/projects/{project_id}/tickets/{ticket_id}/open-session",
        headers=researcher_headers,
    )
    assert open_sess_resp.status_code == 200
    session_id = open_sess_resp.json()["session_id"]

    open_sess_again = await client.post(
        f"/api/v1/projects/{project_id}/tickets/{ticket_id}/open-session",
        headers=researcher_headers,
    )
    assert open_sess_again.status_code == 200
    assert open_sess_again.json()["session_id"] == session_id

    # Verify session has linkage metadata
    sess_list_resp = await client.get(
        "/api/v1/sessions",
        params={"project_id": project_id, "include_empty": True},
        headers=researcher_headers,
    )
    assert sess_list_resp.status_code == 200
    linked = [s for s in sess_list_resp.json() if s["id"] == session_id]
    assert len(linked) == 1
    assert linked[0]["ticket_id"] == ticket_id
    assert linked[0]["stage_category"] == "problem_framing"

    # Seed an assistant conclusion message in that session
    db.add(
        Message(
            session_id=session_id,
            role="assistant",
            content="Agreed to lock SI >= 10 as primary selectivity gate.",
        )
    )
    await db.commit()

    # 6. Precipitate session conclusion back to the ticket
    precip_resp = await client.post(
        f"/api/v1/projects/{project_id}/tickets/{ticket_id}/precipitate-session",
        json={
            "session_id": session_id,
            "create_research_object": True,
        },
        headers=researcher_headers,
    )
    assert precip_resp.status_code == 200
    precip_data = precip_resp.json()
    assert precip_data["ticket"]["id"] == ticket_id
    assert precip_data["research_object_id"] is not None

    # Verify ResearchObject provenance
    ro = (
        await db.execute(
            select(ResearchObject).where(
                ResearchObject.id == precip_data["research_object_id"]
            )
        )
    ).scalar_one()
    assert (ro.content_json or {}).get("origin_session_id") == session_id

    # Verify activity timeline recorded ticket_created, attention_requested, session_precipitated
    act_resp = await client.get(
        f"/api/v1/projects/{project_id}/activities",
        headers=researcher_headers,
    )
    assert act_resp.status_code == 200
    actions = {item["action"] for item in act_resp.json()}
    assert "ticket_created" in actions
    assert "session_precipitated" in actions

    # 7. Posting a thread message on a new ticket auto-creates a linked Session in Sessions list
    ticket2_resp = await client.post(
        f"/api/v1/projects/{project_id}/tickets",
        json={
            "title": "Discuss baseline hyperparameters",
            "stage_category": "baseline_reproduction",
            "mandate_text": "Compare batch sizes 32 vs 64",
            "mandate_strength": "explicit",
        },
        headers=researcher_headers,
    )
    assert ticket2_resp.status_code == 201
    ticket2_id = ticket2_resp.json()["id"]

    msg_resp = await client.post(
        f"/api/v1/projects/{project_id}/tickets/{ticket2_id}/messages",
        json={"content": "Should we use batch size 64 for stability?", "invoke_agent": False},
        headers=researcher_headers,
    )
    assert msg_resp.status_code == 200

    sess_after_msg = await client.get(
        "/api/v1/sessions",
        params={"project_id": project_id, "include_empty": True},
        headers=researcher_headers,
    )
    assert sess_after_msg.status_code == 200
    assert any(s.get("ticket_id") == ticket2_id for s in sess_after_msg.json())

    # 8. Critic self-check + rebuttal validation loop from a Stage 5 manuscript ticket
    from app.services.superagent_service import _run_stage_critic_check

    critic = _run_stage_critic_check(
        stage_category="manuscript_writing",
        deliverable={
            "markdown_report": "## 1. Intro\nClaim grounded in [Doc_1_Page_1].\n$$\nx = 1\n$$",
            "proposed_objects": [{"content_json": {"figures": [{"svg": "<svg/>"}]}}],
            "peer_review": {"status": "reviewed", "Weaknesses": ["Needs ablation on window size."]},
        },
        sources_count=1,
    )
    assert critic["status"] == "passed"
    assert critic["passed_count"] == 4

    s5_resp = await client.post(
        f"/api/v1/projects/{project_id}/tickets",
        json={
            "title": "Draft manuscript for rebuttal test",
            "stage_category": "manuscript_writing",
            "mandate_text": "Synthesize manuscript",
            "mandate_strength": "explicit",
        },
        headers=researcher_headers,
    )
    assert s5_resp.status_code == 201
    s5_ticket_id = s5_resp.json()["id"]

    rebuttal_resp = await client.post(
        f"/api/v1/projects/{project_id}/tickets/{s5_ticket_id}/rebuttal-validation",
        json={"focus_comment": "Run ablation on window size = 20 vs 60"},
        headers=researcher_headers,
    )
    assert rebuttal_resp.status_code == 201
    rebuttal_data = rebuttal_resp.json()
    assert rebuttal_data["stage_category"] == "experiment_iteration"
    assert rebuttal_data["parent_ticket_id"] == s5_ticket_id
