import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.constants import ROLE_RESEARCHER
from app.core.security import create_access_token, hash_password
from app.models.source import Chunk, Source, SourceShare
from app.models.user import User, Workspace
from app.services.research_asset_service import materialize_source_asset
from tests.baseline_fixtures import real_baseline_runtime  # noqa: F401
from tests.research_stage_fixtures import research_stage_runtime  # noqa: F401

pytestmark = pytest.mark.asyncio


@pytest_asyncio.fixture
async def lab_member(db: AsyncSession) -> User:
    user = User(
        username="wetlab_member",
        display_name="Dr. WetLab",
        hashed_password=hash_password("pass123"),
        role=ROLE_RESEARCHER,
    )
    db.add(user)
    await db.flush()
    db.add(Workspace(researcher_id=user.id))
    await db.commit()
    await db.refresh(user)
    return user


@pytest_asyncio.fixture
async def lab_member_headers(lab_member: User) -> dict:
    return {"Authorization": f"Bearer {create_access_token(lab_member.id)}"}


async def test_five_stage_research_superagent_lifecycle(
    client: AsyncClient,
    db: AsyncSession,
    researcher_user: User,
    researcher_headers: dict,
    lab_member: User,
    lab_member_headers: dict,
    research_stage_runtime,
):
    # 1. Create Project and add a team member
    proj_resp = await client.post(
        "/api/v1/projects",
        json={
            "name": "Selective Antimicrobial Candidate Discovery",
            "description": "End-to-end discovery and wet-lab validation",
            "task_ids": ["amp-design-pack"],
        },
        headers=researcher_headers,
    )
    assert proj_resp.status_code == 201
    project_id = proj_resp.json()["id"]

    add_member_resp = await client.post(
        f"/api/v1/projects/{project_id}/members",
        json={"researcher_id": lab_member.id},
        headers=researcher_headers,
    )
    assert add_member_resp.status_code == 201

    # Seed a literature source shared to the project
    src = Source(
        name="Amphiphilic Helical Motifs Against MDR Acinetobacter (2025)",
        type="file",
        owner_id=researcher_user.id,
        content_path="/tmp/paper1.pdf",
        processing_state="ready",
    )
    db.add(src)
    await db.flush()
    db.add(
        SourceShare(
            source_id=src.id,
            shared_by=researcher_user.id,
            scope="project",
            project_id=project_id,
            permission="read",
        )
    )
    db.add(
        Chunk(
            source_id=src.id,
            text=(
                "We report baseline helical sequence KLLKLLKKLLKLLK with MIC = 16 ug/mL "
                "against E. coli and HC50 = 95 ug/mL, limited by proteolytic degradation. "
                "The baseline mean is 2.0. Data: 1.0, 3.0."
            ),
            chunk_index=0,
        )
    )
    await materialize_source_asset(
        db=db, source=src, owner_id=researcher_user.id, origin_project_id=project_id,
        origin_session_id=None, visibility_scope="project", link_type="reference",
    )
    await db.commit()

    # Check initial Superagent Overview: healthy quiet state (needs_person == [])
    ov0 = await client.get(
        f"/api/v1/projects/{project_id}/superagent/overview",
        headers=researcher_headers,
    )
    assert ov0.status_code == 200
    ov0_data = ov0.json()
    assert ov0_data["needs_person"] == []
    assert len(ov0_data["pipeline_stages"]) == 5
    assert ov0_data["policy"]["accept_mode"] == "auto"

    # 2. Stage 1: PI defines Research Theme, Core Question, and Target Metrics
    q_resp = await client.post(
        f"/api/v1/projects/{project_id}/superagent/questions",
        json={
            "theme": "Low-hemolysis antimicrobial candidates against MDR Gram-negative bacteria",
            "question": "How can we decouple membrane-disruptive potency from mammalian erythrocyte toxicity?",
            "sub_questions": [
                "Which hydrophobic face substitutions reduce hemolysis while keeping MIC <= 4 ug/mL?"
            ],
            "target_metrics": [
                {"metric": "MIC (E. coli)", "target": "<= 4", "unit": "ug/mL"},
                {"metric": "HC50", "target": ">= 200", "unit": "ug/mL"},
            ],
            "constraints": ["Sequence length 12-20 AA", "Standard L-amino acids"],
            "plugin_id": "amp-design-pack",
        },
        headers=researcher_headers,
    )
    assert q_resp.status_code == 201
    q_data = q_resp.json()
    assert q_data["research_object"]["type"] == "research_question"

    # Defining the question automatically triggers Stage 2 (Literature Baseline & Reproduction)
    stage2_ticket = q_data["ticket"]
    assert stage2_ticket is not None
    assert stage2_ticket["short_key"] == "T-1"
    assert stage2_ticket["stage_category"] == "baseline_reproduction"
    assert stage2_ticket["stage"] == "person / review"
    assert stage2_ticket["needs_person"] is True
    assert len(stage2_ticket["deliverable"]["metrics_table"]) >= 1
    assert (
        stage2_ticket["deliverable"]["metrics_table"][0]["source_name"]
        == "Amphiphilic Helical Motifs Against MDR Acinetobacter (2025)"
    )

    # 3. PI reviews & approves Stage 2 Baseline Deliverable ("Research PR")
    approve_s2 = await client.post(
        f"/api/v1/projects/{project_id}/tickets/{stage2_ticket['id']}/approve",
        json={"comment": "Baseline reproduction verified; proceed to innovation."},
        headers=researcher_headers,
    )
    assert approve_s2.status_code == 200
    approve_s2_data = approve_s2.json()
    assert approve_s2_data["ticket"]["status"] == "ended"
    assert approve_s2_data["ticket"]["ended_outcome"] == "merged"

    # Approving Stage 2 automatically spawns Stage 3 (Co-Ideation & Feasibility Gate)
    # which asks 1 concrete decision question (person / answer)
    stage3_ticket = approve_s2_data["next_ticket"]
    assert stage3_ticket is not None
    assert stage3_ticket["short_key"] == "T-2"
    assert stage3_ticket["stage_category"] == "innovation_feasibility"
    assert stage3_ticket["stage"] == "person / answer"
    assert stage3_ticket["attention"]["kind"] == "decision"
    assert len(stage3_ticket["attention"]["options"]) == 3

    # Team member collaborates in the shared thread and answers the Attention question
    ans_s3 = await client.post(
        f"/api/v1/projects/{project_id}/tickets/{stage3_ticket['id']}/answer",
        json={
            "answer": stage3_ticket["attention"]["options"][0],
            "selected_option": stage3_ticket["attention"]["options"][0],
        },
        headers=lab_member_headers,
    )
    assert ans_s3.status_code == 200
    stage3_ready = ans_s3.json()
    assert stage3_ready["stage"] == "person / review"
    assert stage3_ready["deliverable"]["kind"] == "innovation_protocol"

    # Approve Stage 3 Experiment Protocol & 3D Feasibility Report
    approve_s3 = await client.post(
        f"/api/v1/projects/{project_id}/tickets/{stage3_ticket['id']}/approve",
        json={"comment": "Feasibility confirmed; start Round 1 experiments."},
        headers=researcher_headers,
    )
    assert approve_s3.status_code == 200
    stage4_r1 = approve_s3.json()["next_ticket"]
    assert stage4_r1 is not None
    assert stage4_r1["short_key"] == "T-3"
    assert stage4_r1["stage_category"] == "experiment_iteration"
    assert stage4_r1["iteration_round"] == 1
    # Dry-lab completes and pauses in person / wetlab waiting for wet-lab CSV upload
    assert stage4_r1["stage"] == "person / wetlab"
    assert stage4_r1["attention"]["kind"] == "wetlab_upload"
    assert "csv_text" in stage4_r1["attention"]["template_data"]

    # 4. Wet-lab member uploads Round 1 experimental results
    wetlab_r1 = await client.post(
        f"/api/v1/projects/{project_id}/tickets/{stage4_r1['id']}/wetlab-upload",
        json={
            "experiment_note": "Round 1 broth microdilution and RBC hemolysis assay completed.",
            "measurements": [
                {
                    "sample_id": "R1-Cand-01",
                    "condition": "E. coli ATCC 25922",
                    "predicted_value": 2.4,
                    "measured_value": 4.5,
                    "secondary_metric": 240.0,
                    "notes": "Slight salt sensitivity",
                },
                {
                    "sample_id": "R1-Cand-02",
                    "condition": "E. coli ATCC 25922",
                    "predicted_value": 3.1,
                    "measured_value": 3.2,
                    "secondary_metric": 290.0,
                    "notes": "Lead hit exceeding target",
                },
            ],
        },
        headers=lab_member_headers,
    )
    assert wetlab_r1.status_code == 200
    r1_diff = wetlab_r1.json()
    assert r1_diff["stage"] == "person / review"
    assert r1_diff["deliverable"]["kind"] == "iteration_diff"
    assert r1_diff["deliverable"]["diff_summary"]["round"] == 1
    assert r1_diff["deliverable"]["diff_summary"]["best_measured_value"] == 3.2

    # Spawn Round 2 to test multi-round iteration diffing against Round 1
    r2_resp = await client.post(
        f"/api/v1/projects/{project_id}/tickets/{stage4_r1['id']}/next-round",
        json={
            "direction_note": "Optimize R1-Cand-02 salt stability at 150 mM NaCl",
            "assignee_id": lab_member.id,
        },
        headers=researcher_headers,
    )
    assert r2_resp.status_code == 201
    stage4_r2 = r2_resp.json()
    assert stage4_r2["iteration_round"] == 2
    assert stage4_r2["stage"] == "person / wetlab"

    # Upload Round 2 wet-lab results via CSV string
    csv_payload = (
        "sample_id,condition,predicted_value,measured_value,secondary_metric,notes\n"
        "R2-Cand-01,E. coli + 150mM NaCl,1.9,2.0,340,Superior potency and salt stability\n"
    )
    wetlab_r2 = await client.post(
        f"/api/v1/projects/{project_id}/tickets/{stage4_r2['id']}/wetlab-upload",
        json={
            "experiment_note": "Round 2 physiological salt assay verified.",
            "csv_content": csv_payload,
        },
        headers=lab_member_headers,
    )
    assert wetlab_r2.status_code == 200
    r2_diff = wetlab_r2.json()
    assert r2_diff["stage"] == "person / review"
    assert r2_diff["deliverable"]["diff_summary"]["prior_round_best"] == 3.2
    assert r2_diff["deliverable"]["diff_summary"]["best_measured_value"] == 2.0
    assert r2_diff["deliverable"]["diff_summary"]["delta_vs_prior_round"] == -1.2

    # 5. Approve Round 2 with mark_milestone_verified=True -> triggers Stage 5 Manuscript Writing
    approve_r2 = await client.post(
        f"/api/v1/projects/{project_id}/tickets/{stage4_r2['id']}/approve",
        json={
            "comment": "Round 2 lead R2-Cand-01 meets all milestones. Proceed to manuscript.",
            "mark_milestone_verified": True,
        },
        headers=researcher_headers,
    )
    assert approve_r2.status_code == 200
    stage5_ticket = approve_r2.json()["next_ticket"]
    assert stage5_ticket is not None
    assert stage5_ticket["stage_category"] == "manuscript_writing"
    assert stage5_ticket["stage"] == "person / review"
    assert "Manuscript Draft" in stage5_ticket["deliverable"]["markdown_report"]

    # Approve Stage 5 Manuscript Draft
    approve_s5 = await client.post(
        f"/api/v1/projects/{project_id}/tickets/{stage5_ticket['id']}/approve",
        json={"comment": "Manuscript draft approved for team polishing."},
        headers=researcher_headers,
    )
    assert approve_s5.status_code == 200

    # Verify final Superagent Overview: all 5 stages completed, 0 items needing person
    ov_final = await client.get(
        f"/api/v1/projects/{project_id}/superagent/overview",
        headers=researcher_headers,
    )
    assert ov_final.status_code == 200
    final_data = ov_final.json()
    assert final_data["needs_person"] == []
    stage_statuses = {
        s["stage_category"]: s["status"] for s in final_data["pipeline_stages"]
    }
    assert stage_statuses == {
        "problem_framing": "completed",
        "baseline_reproduction": "completed",
        "innovation_feasibility": "completed",
        "experiment_iteration": "completed",
        "manuscript_writing": "completed",
    }
    assert final_data["flow_24h"]["completed"] >= 4

    # Generated Stage 5 manuscript PDF should appear in Project Materials (/assets)
    assets_resp = await client.get(
        f"/api/v1/projects/{project_id}/assets",
        headers=researcher_headers,
    )
    assert assets_resp.status_code == 200
    assert any(
        (item.get("title") or "").endswith(".pdf")
        for item in assets_resp.json()
    )


async def test_policy_observe_mode_and_shared_thread_messages(
    client: AsyncClient,
    researcher_headers: dict,
):
    proj_resp = await client.post(
        "/api/v1/projects",
        json={"name": "Observe Mode Project"},
        headers=researcher_headers,
    )
    project_id = proj_resp.json()["id"]

    # Switch policy to observe mode
    pol_resp = await client.put(
        f"/api/v1/projects/{project_id}/superagent/policy",
        json={"accept_mode": "observe"},
        headers=researcher_headers,
    )
    assert pol_resp.status_code == 200
    assert pol_resp.json()["accept_mode"] == "observe"
    assert pol_resp.json()["version"] == 2

    # Emit a trigger in observe mode -> disposition is 'observed' and no ticket is created
    trig_resp = await client.post(
        f"/api/v1/projects/{project_id}/superagent/triggers",
        json={
            "source_kind": "source",
            "event_type": "sources_ready",
            "title": "Uploaded 3 new papers",
        },
        headers=researcher_headers,
    )
    assert trig_resp.status_code == 201
    assert trig_resp.json()["trigger"]["disposition"] == "observed"
    assert trig_resp.json()["ticket"] is None

    # Explicit ticket creation still works and supports shared thread messages
    ticket_resp = await client.post(
        f"/api/v1/projects/{project_id}/tickets",
        json={
            "title": "Manual Baseline Check",
            "stage_category": "baseline_reproduction",
            "goal": "Check baseline metrics from newly uploaded papers",
        },
        headers=researcher_headers,
    )
    assert ticket_resp.status_code == 201
    ticket_id = ticket_resp.json()["id"]

    msg_resp = await client.post(
        f"/api/v1/projects/{project_id}/tickets/{ticket_id}/messages",
        json={"content": "Please also compare toxicity at pH 7.4", "invoke_agent": True},
        headers=researcher_headers,
    )
    assert msg_resp.status_code == 200
    assert len(msg_resp.json()["thread_messages"]) >= 3


async def test_unified_theme_subquestion_tree_and_ai_charter_suggestion(
    client: AsyncClient,
    researcher_headers: dict,
):
    proj_resp = await client.post(
        "/api/v1/projects",
        json={
            "name": "Reproducible Research Workflow Study",
            "description": "Investigating reproducible scientific pipelines across labs",
        },
        headers=researcher_headers,
    )
    assert proj_resp.status_code == 201
    project_id = proj_resp.json()["id"]

    # 1. Suggest charter / question from project metadata
    suggest_resp = await client.post(
        f"/api/v1/projects/{project_id}/superagent/questions/suggest",
        headers=researcher_headers,
    )
    assert suggest_resp.status_code == 200
    suggestion = suggest_resp.json()
    assert suggestion["theme"] == "Reproducible Research Workflow Study"
    assert len(suggestion["sub_questions"]) >= 1
    assert len(suggestion["success_criteria"]) >= 1

    # 2. Create Q1 with domain-agnostic qualitative/quantitative success_criteria
    q1_resp = await client.post(
        f"/api/v1/projects/{project_id}/superagent/questions",
        json={
            "theme": suggestion["theme"],
            "question": "How can multi-lab computational and experimental workflows remain reproducible?",
            "sub_questions": ["What metadata is required to reproduce baseline figures?"],
            "success_criteria": [
                "Reproduce core workflow from reference literature with consistent conclusions",
                "Cross-lab variance reduced below 5%",
            ],
            "constraints": ["Only open-source tools and shared project documents"],
        },
        headers=researcher_headers,
    )
    assert q1_resp.status_code == 201
    q1_obj = q1_resp.json()["research_object"]
    assert q1_obj["content_json"]["success_criteria"] == [
        "Reproduce core workflow from reference literature with consistent conclusions",
        "Cross-lab variance reduced below 5%",
    ]

    # 3. Inline-append a sub-question to Q1 using question_object_id without creating a duplicate object
    q1_update_resp = await client.post(
        f"/api/v1/projects/{project_id}/superagent/questions",
        json={
            "question_object_id": q1_obj["id"],
            "theme": suggestion["theme"],
            "question": q1_obj["content_json"]["question"],
            "sub_questions": [
                "What metadata is required to reproduce baseline figures?",
                "How do parameter perturbations affect cross-round reproducibility?",
            ],
            "success_criteria": q1_obj["content_json"]["success_criteria"],
            "constraints": q1_obj["content_json"]["constraints"],
        },
        headers=researcher_headers,
    )
    assert q1_update_resp.status_code == 201
    updated_obj = q1_update_resp.json()["research_object"]
    assert updated_obj["id"] == q1_obj["id"]
    assert len(updated_obj["content_json"]["sub_questions"]) == 2


async def test_four_agent_academic_deep_research_network_with_hitl_checkpoints(
    client: AsyncClient,
    db: AsyncSession,
    researcher_user: User,
    researcher_headers: dict,
    research_stage_runtime,
):
    proj_resp = await client.post(
        "/api/v1/projects",
        json={
            "name": "Graph Neural Network Benchmark & Empirical Comparison",
            "description": "Comparing internal GNN experimental results against 2024 mainstream models",
        },
        headers=researcher_headers,
    )
    assert proj_resp.status_code == 201
    project_id = proj_resp.json()["id"]

    # Seed a local RAG source with Marker-parsed chunk
    src = Source(
        name="Equivariant Graph Attention Baselines on OGB-MolHIV (2024)",
        type="file",
        owner_id=researcher_user.id,
        content_path="/tmp/gnn_2024.pdf",
        processing_state="ready",
    )
    db.add(src)
    await db.flush()
    db.add(
        SourceShare(
            source_id=src.id,
            shared_by=researcher_user.id,
            scope="project",
            project_id=project_id,
            permission="read",
        )
    )
    db.add(
        Chunk(
            source_id=src.id,
            text="Baseline EquiGAT achieves ROC-AUC = 81.4% on OGB-MolHIV with F1 = 78.2%.",
            chunk_index=0,
        )
    )
    await materialize_source_asset(
        db=db, source=src, owner_id=researcher_user.id, origin_project_id=project_id,
        origin_session_id=None, visibility_scope="project", link_type="reference",
    )
    await db.commit()

    # 1. Launch 4-Agent Academic Deep Research with HITL Checkpoints enabled
    dr_resp = await client.post(
        f"/api/v1/projects/{project_id}/superagent/deep-research",
        json={
            "instruction": "Analyze differences between our latest experimental results and 2024 mainstream GNN models",
            "citation_style": "IEEE",
            "allow_external_search": True,
            "enable_hitl_checkpoints": True,
        },
        headers=researcher_headers,
    )
    assert dr_resp.status_code == 201
    c1_ticket = dr_resp.json()
    assert c1_ticket["stage"] == "person / answer"
    assert c1_ticket["deliverable"]["checkpoint_stage"] == "checkpoint_1_literature_outline"
    assert c1_ticket["deliverable"]["planner_plan"]["agent_role"] == "Planner Agent"
    cards = c1_ticket["deliverable"]["literature_memory_cards"]
    assert len(cards) >= 2
    assert cards[0]["source_id"] == "Doc_1_Page_1"
    assert cards[0]["word_count"] <= 500
    assert "baseline" in cards[0]["experimental_setup"]

    # 2. Researcher confirms HITL Checkpoint 1 (Literature Outline & 500w Memory Cards)
    c2_resp = await client.post(
        f"/api/v1/projects/{project_id}/tickets/{c1_ticket['id']}/answer",
        json={
            "answer": c1_ticket["attention"]["options"][0],
            "selected_option": c1_ticket["attention"]["options"][0],
        },
        headers=researcher_headers,
    )
    assert c2_resp.status_code == 200
    c2_ticket = c2_resp.json()
    # Pauses at HITL Checkpoint 2 after Data Agent executes Python cross-validation & SVG chart
    assert c2_ticket["stage"] == "person / answer"
    assert c2_ticket["deliverable"]["checkpoint_stage"] == "checkpoint_2_data_validation"
    cross_val = c2_ticket["deliverable"]["data_cross_validation"]
    assert cross_val is not None
    assert "import pandas as pd" in cross_val["python_script"]
    assert "<svg" in cross_val["chart_svg"]
    assert len(cross_val["alignment_table"]) >= 2

    # 3. Researcher confirms HITL Checkpoint 2 (Internal Data vs External Baseline Cross-Validation)
    final_resp = await client.post(
        f"/api/v1/projects/{project_id}/tickets/{c1_ticket['id']}/answer",
        json={
            "answer": c2_ticket["attention"]["options"][0],
            "selected_option": c2_ticket["attention"]["options"][0],
        },
        headers=researcher_headers,
    )
    assert final_resp.status_code == 200
    final_ticket = final_resp.json()
    # Both writer entry points use the same authorized claim ledger.
    assert final_ticket["stage"] == "person / review"
    assert final_ticket["deliverable"]["checkpoint_stage"] == "completed"
    writer_out = final_ticket["deliverable"]["writer_output"]
    assert writer_out is not None
    assert f"[{src.id}]" in writer_out["manuscript_draft"]
    assert "@misc{" in writer_out["bibtex"]
    audit = writer_out["provenance_audit"]
    assert audit["status"] == "citation_and_number_checks_passed"
    assert audit["claim_count"] >= 1
    assert audit["review_required"] is True
    assert "Doc_1_Page_1" not in writer_out["manuscript_draft"]
    assert "experimental validation is not established" in writer_out["manuscript_draft"]

    # 4. Approve the Deep Research Manuscript into Project State
    approve_resp = await client.post(
        f"/api/v1/projects/{project_id}/tickets/{c1_ticket['id']}/approve",
        json={"comment": "Approve multi-agent manuscript and BibTeX into project assets."},
        headers=researcher_headers,
    )
    assert approve_resp.status_code == 200
    assert approve_resp.json()["ticket"]["status"] == "ended"
    created_types = {obj["type"] for obj in approve_resp.json()["created_objects"]}
    assert "manuscript_draft" in created_types
    assert "baseline_scheme" not in created_types


