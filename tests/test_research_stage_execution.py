"""Scientific stage outputs require evidence rather than template success."""

import json
from pathlib import Path

import pytest

from app.core.config import settings
from app.models.research_object import ResearchObject
from app.models.research_ticket import ResearchTicket
from app.models.source import Chunk, Source
from app.services import research_stage_execution as execution
from app.services.research_asset_service import materialize_research_object_asset, materialize_source_asset
from tests.baseline_fixtures import real_baseline_runtime  # noqa: F401
from tests.research_stage_fixtures import research_stage_runtime, stage_payload  # noqa: F401


@pytest.fixture
def evidence_case(tmp_path):
    (tmp_path / "inputs").mkdir()
    catalog = {
        "paper": {"kind": "literature", "title": "Reference paper", "text": "The baseline mean is 2.0."},
        "object:baseline": {"kind": "baseline_result", "title": "Executed baseline",
                            "text": json.dumps({"metrics": [{"observed_value": 2.0}]}, indent=2)},
    }
    (tmp_path / "inputs/evidence.json").write_text(json.dumps(catalog))
    return tmp_path, catalog, {"skills": []}


@pytest.mark.parametrize("phase", ["proposal", "feasibility", "manuscript"])
def test_valid_stage_result_is_reviewable(evidence_case, phase):
    root, catalog, manifest = evidence_case
    payload = stage_payload(root, phase, catalog)
    result = execution.validate_stage_result(root, phase, payload, manifest, catalog)
    assert result["status"] == "completed"
    assert result["review_required"] is True
    assert result["artifacts"]
    if phase == "manuscript":
        assert result["audit"]["claim_count"] == 2
        assert "experimental validation is not established" in result["manuscript"]


@pytest.mark.parametrize("change", ["number", "leading_decimal", "quotation", "unknown_reference", "basis", "uncited", "markup", "sections"])
def test_manuscript_rejects_unsupported_claims(evidence_case, change):
    root, catalog, manifest = evidence_case
    payload = stage_payload(root, "manuscript", catalog)
    path = root / "outputs/result.json"
    result = json.loads(path.read_text())
    block = result["sections"][0]["blocks"][0]
    if change == "number":
        block["text"] = "The mean is 99.9."
    elif change == "leading_decimal":
        block["text"] = "The observed probability is .05."
    elif change == "quotation":
        block["citations"][0]["quote"] = "An invented supporting quote"
    elif change == "unknown_reference":
        block["citations"][0]["reference_id"] = "ghost-paper"
    elif change == "basis":
        block["basis"] = "empirical_record"
    elif change == "uncited":
        block["citations"] = []
    elif change == "markup":
        block["text"] = "A fact [invented-source]."
    else:
        result["sections"].pop()
    path.write_text(json.dumps(result))
    with pytest.raises(ValueError):
        execution.validate_stage_result(root, "manuscript", payload, manifest, catalog)


def test_numbers_are_compared_numerically(evidence_case):
    root, catalog, manifest = evidence_case
    payload = stage_payload(root, "manuscript", catalog)
    path = root / "outputs/result.json"
    result = json.loads(path.read_text())
    result["sections"][0]["blocks"][0]["text"] = "The recorded mean is 2."
    path.write_text(json.dumps(result))
    assert execution.validate_stage_result(root, "manuscript", payload, manifest, catalog)["status"] == "completed"


@pytest.mark.parametrize("change", ["no_command", "method_quote", "duplicate_checks", "missing_controls", "blank_controls", "missing_script", "symlink"])
def test_feasibility_rejects_missing_execution_or_protocol(evidence_case, change):
    root, catalog, manifest = evidence_case
    payload = stage_payload(root, "feasibility", catalog)
    path = root / "outputs/result.json"
    result = json.loads(path.read_text())
    if change == "no_command":
        payload["raw_events"] = []
    elif change == "method_quote":
        result["checks"][1]["citations"] = result["checks"][0]["citations"]
    elif change == "duplicate_checks":
        result["checks"][1] = result["checks"][0]
    elif change == "missing_controls":
        result["protocol"]["controls"] = []
    elif change == "blank_controls":
        result["protocol"]["controls"] = ["   "]
    elif change == "missing_script":
        (root / "outputs/probe.py").unlink()
    else:
        (root / "outputs/feasibility.md").unlink()
        (root / "outputs/feasibility.md").symlink_to(root / "inputs/evidence.json")
    path.write_text(json.dumps(result))
    with pytest.raises(ValueError):
        execution.validate_stage_result(root, "feasibility", payload, manifest, catalog)


def test_proposal_cannot_invent_baseline_support(evidence_case):
    root, catalog, manifest = evidence_case
    payload = stage_payload(root, "proposal", catalog)
    catalog["object:baseline"]["kind"] = "literature"
    with pytest.raises(ValueError, match="executed baseline"):
        execution.validate_stage_result(root, "proposal", payload, manifest, catalog)


async def make_project(client, db, user, headers):
    response = await client.post("/api/v1/projects", json={"name": "Evidence-led research"}, headers=headers)
    project_id = response.json()["id"]
    source = Source(type="file", name="Baseline method", owner_id=user.id, processing_state="ready")
    db.add(source)
    await db.flush()
    db.add(Chunk(source_id=source.id, text="The baseline mean is 2.0. Data: 1.0, 3.0.", chunk_index=0))
    await materialize_source_asset(db=db, source=source, owner_id=user.id, origin_project_id=project_id,
                                   origin_session_id=None, visibility_scope="project", link_type="reference")
    await db.commit()
    return project_id


async def innovation_ticket(client, db, user, headers):
    project_id = await make_project(client, db, user, headers)
    question = await client.post(f"/api/v1/projects/{project_id}/superagent/questions", headers=headers, json={
        "theme": "Reproducibility", "question": "Can a controlled method improve robustness?",
        "success_criteria": ["Compare held-out error"], "constraints": ["Use local evidence"],
    })
    assert question.status_code == 201, question.text
    baseline_id = question.json()["ticket"]["id"]
    approved = await client.post(f"/api/v1/projects/{project_id}/tickets/{baseline_id}/approve", headers=headers, json={})
    assert approved.status_code == 200, approved.text
    return project_id, approved.json()["next_ticket"]


@pytest.mark.asyncio
async def test_innovation_execution_archives_protocol_and_advances_only_after_review(
    client, db, researcher_user, researcher_headers, research_stage_runtime,
):
    project_id, ticket = await innovation_ticket(client, db, researcher_user, researcher_headers)
    assert ticket["stage"] == "person / answer"
    assert ticket["deliverable"]["stage_execution"]["phase"] == "proposal"
    answer = await client.post(f"/api/v1/projects/{project_id}/tickets/{ticket['id']}/answer", headers=researcher_headers,
                               json={"answer": ticket["attention"]["options"][0]})
    assert answer.status_code == 200, answer.text
    ready = answer.json()
    assert ready["stage"] == "person / review"
    evidence = ready["deliverable"]["stage_execution"]
    assert evidence["feasibility_outcome"] == "supported"
    assert evidence["commands"]
    assert len(evidence["artifacts"]) == 4
    assert ready["deliverable"]["innovation_proposal"]["execution_id"] != evidence["execution_id"]
    approved = await client.post(f"/api/v1/projects/{project_id}/tickets/{ticket['id']}/approve", headers=researcher_headers, json={})
    assert approved.status_code == 200, approved.text
    assert approved.json()["created_objects"][0]["content_json"]["execution"]["execution_id"] == evidence["execution_id"]
    assert approved.json()["next_ticket"]["stage_category"] == "experiment_iteration"


@pytest.mark.asyncio
async def test_unresolved_feasibility_blocks_approval_and_can_be_retried(
    client, db, researcher_user, researcher_headers, research_stage_runtime, monkeypatch,
):
    project_id, ticket = await innovation_ticket(client, db, researcher_user, researcher_headers)

    async def unresolved(*, cwd, **kwargs):
        root = Path(cwd)
        return stage_payload(root, "feasibility", json.loads((root / "inputs/evidence.json").read_text()), assessment="unresolved")

    monkeypatch.setattr(execution, "run_codex_runtime", unresolved)
    answer = await client.post(f"/api/v1/projects/{project_id}/tickets/{ticket['id']}/answer", headers=researcher_headers,
                               json={"answer": ticket["attention"]["options"][0]})
    assert answer.json()["report_state"] == "blocked"
    assert answer.json()["deliverable"]["proposed_objects"] == []
    denied = await client.post(f"/api/v1/projects/{project_id}/tickets/{ticket['id']}/approve", headers=researcher_headers, json={})
    assert denied.status_code == 409
    monkeypatch.setattr(execution, "run_codex_runtime", research_stage_runtime)
    retried = await client.post(f"/api/v1/projects/{project_id}/tickets/{ticket['id']}/retry-stage", headers=researcher_headers)
    assert retried.status_code == 200, retried.text
    assert retried.json()["stage"] == "person / review"


@pytest.mark.asyncio
async def test_innovation_without_executed_baseline_is_blocked(
    client, db, researcher_user, researcher_headers, research_stage_runtime,
):
    project_id = await make_project(client, db, researcher_user, researcher_headers)
    response = await client.post(f"/api/v1/projects/{project_id}/tickets", headers=researcher_headers,
                                 json={"title": "Invent a method", "stage_category": "innovation_feasibility"})
    assert response.status_code == 201, response.text
    assert response.json()["report_state"] == "blocked"
    assert response.json()["attention"] is None


@pytest.mark.asyncio
async def test_manuscript_is_archived_with_audit_and_honest_empirical_gap(
    client, db, researcher_user, researcher_headers, research_stage_runtime,
):
    project_id = await make_project(client, db, researcher_user, researcher_headers)
    response = await client.post(f"/api/v1/projects/{project_id}/tickets", headers=researcher_headers,
                                 json={"title": "Write a preliminary manuscript", "stage_category": "manuscript_writing"})
    assert response.status_code == 201, response.text
    ticket = response.json()
    assert ticket["stage"] == "person / review"
    evidence = ticket["deliverable"]["stage_execution"]
    assert evidence["audit"]["status"] == "citation_and_number_checks_passed"
    assert len(evidence["artifacts"]) == 4
    assert "experimental validation is not established" in evidence["manuscript"]
    assert "@misc{" in evidence["bibtex"]
    approved = await client.post(f"/api/v1/projects/{project_id}/tickets/{ticket['id']}/approve", headers=researcher_headers, json={})
    assert approved.status_code == 200, approved.text
    assert approved.json()["created_objects"][0]["type"] == "manuscript_draft"


@pytest.mark.asyncio
async def test_legacy_automatic_validation_is_excluded_from_manuscript_evidence(
    client, db, researcher_user, researcher_headers, research_stage_runtime,
):
    project_id = await make_project(client, db, researcher_user, researcher_headers)
    origin = ResearchTicket(project_id=project_id, short_key="OLD-1", title="Legacy validation",
                            stage_category="experiment_iteration", status="ended", ended_outcome="merged", created_by=researcher_user.id)
    db.add(origin)
    await db.flush()
    obj = ResearchObject(type="experiment_iteration", title="Legacy PASS", content="Verified (Pass), baseline 8.2",
                          content_json={"project_id": project_id, "ticket_id": origin.id, "best_measured_value": 8.2}, created_by=researcher_user.id)
    db.add(obj)
    await db.flush()
    await materialize_research_object_asset(db=db, research_object=obj, owner_id=researcher_user.id,
                                            origin_project_id=project_id, origin_session_id=None, visibility_scope="project", link_type="memory")
    await db.commit()
    response = await client.post(f"/api/v1/projects/{project_id}/tickets", headers=researcher_headers,
                                 json={"title": "Write a draft", "stage_category": "manuscript_writing"})
    evidence = response.json()["deliverable"]["stage_execution"]
    assert not any(item["kind"] == "empirical_record" for item in evidence["manifest"]["evidence"])
    assert any(item["object_id"] == obj.id for item in evidence["manifest"]["omitted_objects"])
    assert "8.2" not in evidence["manuscript"]


@pytest.mark.asyncio
async def test_disabled_stage_is_blocked_and_retry_respects_access(
    client, db, researcher_user, researcher_headers, pi_headers, research_stage_runtime, monkeypatch,
):
    project_id = await make_project(client, db, researcher_user, researcher_headers)
    monkeypatch.setattr(settings, "codex_runtime_enabled", False)
    response = await client.post(f"/api/v1/projects/{project_id}/tickets", headers=researcher_headers,
                                 json={"title": "Write a draft", "stage_category": "manuscript_writing"})
    ticket = response.json()
    assert ticket["report_state"] == "blocked"
    denied = await client.post(f"/api/v1/projects/{project_id}/tickets/{ticket['id']}/approve", headers=researcher_headers, json={})
    assert denied.status_code == 409
    denied = await client.post(f"/api/v1/projects/{project_id}/tickets/{ticket['id']}/retry-stage", headers=pi_headers)
    assert denied.status_code in {403, 404}
    monkeypatch.setattr(settings, "codex_runtime_enabled", True)
    retried = await client.post(f"/api/v1/projects/{project_id}/tickets/{ticket['id']}/retry-stage", headers=researcher_headers)
    assert retried.status_code == 200, retried.text
    assert retried.json()["stage"] == "person / review"
    await client.post(f"/api/v1/projects/{project_id}/tickets/{ticket['id']}/stop", headers=researcher_headers)
    closed = await client.post(f"/api/v1/projects/{project_id}/tickets/{ticket['id']}/retry-stage", headers=researcher_headers)
    assert closed.status_code == 409


@pytest.mark.parametrize("quote, claim", [
    ("The value is 0.05.", "The recorded value is .05."),
    ("The count is 1000.", "The recorded count is 1,000."),
    ("The value is 0.002.", "The recorded value is 2e-3."),
    ("The bound is < 2.0.", "The recorded bound is < 2.0."),
])
def test_manuscript_accepts_supported_numeric_formats(evidence_case, quote, claim):
    root, catalog, manifest = evidence_case
    catalog["paper"]["text"] = quote
    payload = stage_payload(root, "manuscript", catalog)
    path = root / "outputs/result.json"
    result = json.loads(path.read_text())
    result["sections"][0]["blocks"][0]["text"] = claim
    path.write_text(json.dumps(result))
    assert execution.validate_stage_result(root, "manuscript", payload, manifest, catalog)["status"] == "completed"


@pytest.mark.asyncio
async def test_previous_manuscripts_do_not_become_primary_evidence(
    client, db, researcher_user, researcher_headers, research_stage_runtime,
):
    project_id = await make_project(client, db, researcher_user, researcher_headers)
    created = await client.post(f"/api/v1/projects/{project_id}/tickets", headers=researcher_headers,
                                json={"title": "Write a draft", "stage_category": "manuscript_writing"})
    ticket = created.json()
    first = ticket["deliverable"]["stage_execution"]
    retried = await client.post(f"/api/v1/projects/{project_id}/tickets/{ticket['id']}/retry-stage", headers=researcher_headers)
    assert retried.status_code == 200, retried.text
    second = retried.json()["deliverable"]["stage_execution"]
    assert first["execution_id"] != second["execution_id"]
    assert {item["id"] for item in first["manifest"]["evidence"]} == {item["id"] for item in second["manifest"]["evidence"]}
    assert second["manifest"]["excluded_output_source_ids"]


@pytest.mark.asyncio
async def test_baseline_with_withdrawn_source_cannot_ground_innovation(
    client, db, researcher_user, researcher_headers, research_stage_runtime,
):
    from sqlalchemy import select
    from app.models.research_asset import ResearchAsset

    project_id, ticket = await innovation_ticket(client, db, researcher_user, researcher_headers)
    source = await db.scalar(select(Source).where(Source.name == "Baseline method"))
    asset = await db.scalar(select(ResearchAsset).where(ResearchAsset.source_id == source.id))
    asset.publication_status = "withdrawn"
    await db.commit()
    retried = await client.post(f"/api/v1/projects/{project_id}/tickets/{ticket['id']}/retry-stage", headers=researcher_headers)
    assert retried.status_code == 200, retried.text
    assert retried.json()["report_state"] == "blocked"
    assert retried.json()["deliverable"]["proposed_objects"] == []


@pytest.mark.asyncio
async def test_only_human_upload_values_are_admitted_as_empirical_evidence(
    client, db, researcher_user, researcher_headers, research_stage_runtime, monkeypatch,
):
    project_id, ticket = await innovation_ticket(client, db, researcher_user, researcher_headers)
    answered = await client.post(f"/api/v1/projects/{project_id}/tickets/{ticket['id']}/answer", headers=researcher_headers,
                                 json={"answer": ticket["attention"]["options"][0]})
    assert answered.json()["report_state"] == "ready"
    approved = await client.post(f"/api/v1/projects/{project_id}/tickets/{ticket['id']}/approve", headers=researcher_headers, json={})
    experiment = approved.json()["next_ticket"]
    upload = await client.post(f"/api/v1/projects/{project_id}/tickets/{experiment['id']}/wetlab-upload", headers=researcher_headers,
                               json={"experiment_note": "Human-entered observation, not independently validated",
                                     "measurements": [{"sample_id": "SAMPLE-A", "condition": "Recorded assay condition",
                                                       "measured_value": 2.0}]})
    assert upload.status_code == 200, upload.text

    async def writer(*, cwd, **kwargs):
        root = Path(cwd)
        catalog = json.loads((root / "inputs/evidence.json").read_text())
        payload = stage_payload(root, "manuscript", catalog)
        empirical = next(key for key, item in catalog.items() if item["kind"] == "empirical_record")
        assert '"measured_value": 2.0' in catalog[empirical]["text"]
        assert '"baseline_value"' not in catalog[empirical]["text"]
        path = root / "outputs/result.json"
        result = json.loads(path.read_text())
        result["sections"][2]["blocks"] = [{"kind": "claim", "basis": "empirical_record",
            "text": "A user-uploaded observation reports 2.0.",
            "citations": [{"reference_id": empirical, "quote": '"measured_value": 2.0'}]}]
        path.write_text(json.dumps(result))
        return payload

    monkeypatch.setattr(execution, "run_codex_runtime", writer)
    result = await client.post(f"/api/v1/projects/{project_id}/tickets/{experiment['id']}/approve", headers=researcher_headers,
                               json={"mark_milestone_verified": True})
    assert result.status_code == 200, result.text
    manuscript = result.json()["next_ticket"]["deliverable"]["stage_execution"]
    assert manuscript["status"] == "completed", manuscript
    assert any(item["kind"] == "empirical_record" for item in manuscript["manifest"]["evidence"])
    assert "user-uploaded observation reports 2.0" in manuscript["manuscript"]
    assert "baseline 8.2" not in manuscript["manuscript"]
