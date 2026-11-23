"""Baseline execution must carry real files and runtime command evidence."""

import json
from pathlib import Path

import pytest

from app.core.config import settings
from app.models.source import Chunk, Source
from app.services import baseline_execution
from app.services.research_asset_service import materialize_source_asset
from tests.baseline_fixtures import completed_output, real_baseline_runtime  # noqa: F401


@pytest.fixture
def validation_case(tmp_path):
    payload = completed_output(tmp_path, "source-1")
    manifest = {"skills": []}
    texts = {"source-1": "The baseline mean is 2.0."}
    return tmp_path, payload, manifest, texts


def test_validation_requires_command_evidence(validation_case):
    root, payload, manifest, texts = validation_case
    payload["raw_events"] = []
    with pytest.raises(ValueError, match="No successful runtime command"):
        baseline_execution.validate_result(root, payload, manifest, texts)


def test_mismatch_is_retained(validation_case):
    root, _, manifest, texts = validation_case
    payload = completed_output(root, "source-1", observed=3)
    evidence = baseline_execution.validate_result(root, payload, manifest, texts)
    assert evidence["comparison_outcome"] == "mismatch"
    assert evidence["review_required"] is True


@pytest.mark.parametrize("change", ["missing", "symlink", "traversal", "observations", "quote", "nan", "unknown_skill"])
def test_invalid_evidence_is_rejected(validation_case, change):
    root, payload, manifest, texts = validation_case
    result_path = root / "outputs/result.json"
    result = json.loads(result_path.read_text())
    if change == "missing":
        (root / "outputs/report.md").unlink()
    elif change == "symlink":
        (root / "outputs/report.md").unlink()
        (root / "outside.md").write_text("Not an output")
        (root / "outputs/report.md").symlink_to(root / "outside.md")
    elif change == "traversal":
        result["report_path"] = "outputs/../outside.md"
    elif change == "observations":
        (root / "outputs/observations.json").write_text("[]")
    elif change == "quote":
        texts.clear()
    elif change == "nan":
        result["metrics"][0]["reported_value"] = float("nan")
    else:
        result["selected_skill_ids"] = ["not-enabled"]
    result_path.write_text(json.dumps(result))
    with pytest.raises(ValueError):
        baseline_execution.validate_result(root, payload, manifest, texts)


async def create_inputs(client, db, user, headers, *, governed=True):
    response = await client.post("/api/v1/projects", json={"name": "Baseline execution"}, headers=headers)
    project_id = response.json()["id"]
    source = Source(type="file", name="Baseline methods", owner_id=user.id, processing_state="ready")
    db.add(source)
    await db.flush()
    db.add(Chunk(source_id=source.id, text="The baseline mean is 2.0. Data: 1.0, 3.0.", chunk_index=0))
    if governed:
        await materialize_source_asset(db=db, source=source, owner_id=user.id, origin_project_id=project_id,
                                       origin_session_id=None, visibility_scope="project", link_type="reference")
    await db.commit()
    return project_id, source


async def create_ticket(client, project_id, headers):
    response = await client.post(f"/api/v1/projects/{project_id}/tickets", headers=headers,
                                 json={"title": "Reproduce the mean", "stage_category": "baseline_reproduction"})
    assert response.status_code == 201, response.text
    return response.json()


@pytest.mark.asyncio
async def test_completed_run_archives_evidence_and_can_be_approved(
    client, db, researcher_user, researcher_headers, real_baseline_runtime,
):
    project_id, source = await create_inputs(client, db, researcher_user, researcher_headers)
    ticket = await create_ticket(client, project_id, researcher_headers)
    assert ticket["stage"] == "person / review"
    evidence = ticket["deliverable"]["baseline_execution"]
    assert evidence["comparison_outcome"] == "within_tolerance"
    assert evidence["manifest"]["sources"][0]["source_id"] == source.id
    assert len(ticket["deliverable"]["artifact_asset_ids"]) == 3
    assets = await client.get(f"/api/v1/projects/{project_id}/assets", headers=researcher_headers)
    assert set(ticket["deliverable"]["artifact_asset_ids"]) <= {item["id"] for item in assets.json()}
    approved = await client.post(f"/api/v1/projects/{project_id}/tickets/{ticket['id']}/approve",
                                 headers=researcher_headers, json={})
    assert approved.status_code == 200, approved.text
    assert approved.json()["next_ticket"]["stage_category"] == "innovation_feasibility"
    assert approved.json()["created_objects"][0]["content_json"]["execution"]["execution_id"] == evidence["execution_id"]


@pytest.mark.asyncio
async def test_disabled_runtime_blocks_approval_and_retry_uses_new_workspace(
    client, db, researcher_user, researcher_headers, real_baseline_runtime, monkeypatch,
):
    project_id, _ = await create_inputs(client, db, researcher_user, researcher_headers)
    monkeypatch.setattr(settings, "codex_runtime_enabled", False)
    ticket = await create_ticket(client, project_id, researcher_headers)
    assert ticket["report_state"] == "blocked"
    assert ticket["deliverable"]["proposed_objects"] == []
    approval = await client.post(f"/api/v1/projects/{project_id}/tickets/{ticket['id']}/approve",
                                 headers=researcher_headers, json={})
    assert approval.status_code == 409
    monkeypatch.setattr(settings, "codex_runtime_enabled", True)
    retry = await client.post(f"/api/v1/projects/{project_id}/tickets/{ticket['id']}/retry-baseline", headers=researcher_headers)
    assert retry.status_code == 200, retry.text
    assert retry.json()["stage"] == "person / review"
    assert retry.json()["deliverable"]["baseline_execution"]["execution_id"] != ticket["deliverable"]["baseline_execution"]["execution_id"]


@pytest.mark.asyncio
async def test_ungoverned_sources_are_not_exported(
    client, db, researcher_user, researcher_headers, real_baseline_runtime,
):
    project_id, _ = await create_inputs(client, db, researcher_user, researcher_headers, governed=False)
    ticket = await create_ticket(client, project_id, researcher_headers)
    assert ticket["report_state"] == "blocked"
    assert ticket["deliverable"]["baseline_execution"]["manifest"]["sources"] == []


@pytest.mark.asyncio
async def test_runtime_failure_does_not_fabricate_result_or_persist_error_text(
    client, db, researcher_user, researcher_headers, real_baseline_runtime, monkeypatch,
):
    project_id, _ = await create_inputs(client, db, researcher_user, researcher_headers)

    async def failed(**kwargs):
        raise RuntimeError("provider-private-error")

    monkeypatch.setattr(baseline_execution, "run_codex_runtime", failed)
    ticket = await create_ticket(client, project_id, researcher_headers)
    assert ticket["report_state"] == "failed"
    assert ticket["deliverable"]["metrics_table"] == []
    assert "provider-private-error" not in json.dumps(ticket)


@pytest.mark.asyncio
async def test_runtime_blocked_prerequisites_are_visible(
    client, db, researcher_user, researcher_headers, real_baseline_runtime, monkeypatch,
):
    project_id, _ = await create_inputs(client, db, researcher_user, researcher_headers)

    async def blocked(*, cwd, **kwargs):
        (Path(cwd) / "outputs/result.json").write_text(json.dumps({
            "status": "blocked", "summary": "A dataset is missing.", "prerequisites": ["Provide the original dataset"],
        }))
        return {"status": "completed"}

    monkeypatch.setattr(baseline_execution, "run_codex_runtime", blocked)
    ticket = await create_ticket(client, project_id, researcher_headers)
    assert ticket["report_state"] == "blocked"
    assert "Provide the original dataset" in ticket["deliverable"]["markdown_report"]


@pytest.mark.asyncio
async def test_retry_requires_project_access_and_open_baseline(
    client, db, researcher_user, researcher_headers, pi_headers, real_baseline_runtime,
):
    project_id, _ = await create_inputs(client, db, researcher_user, researcher_headers)
    ticket = await create_ticket(client, project_id, researcher_headers)
    denied = await client.post(f"/api/v1/projects/{project_id}/tickets/{ticket['id']}/retry-baseline", headers=pi_headers)
    assert denied.status_code in {403, 404}
    await client.post(f"/api/v1/projects/{project_id}/tickets/{ticket['id']}/stop", headers=researcher_headers)
    stopped = await client.post(f"/api/v1/projects/{project_id}/tickets/{ticket['id']}/retry-baseline", headers=researcher_headers)
    assert stopped.status_code == 409


@pytest.mark.asyncio
async def test_changed_method_is_not_accepted(
    client, db, researcher_user, researcher_headers, real_baseline_runtime, monkeypatch,
):
    project_id, _ = await create_inputs(client, db, researcher_user, researcher_headers)

    async def tampered(*, cwd, **kwargs):
        payload = await real_baseline_runtime(cwd=cwd, **kwargs)
        (Path(cwd) / "inputs/method.md").write_text("Changed after selection")
        return payload

    monkeypatch.setattr(baseline_execution, "run_codex_runtime", tampered)
    ticket = await create_ticket(client, project_id, researcher_headers)
    assert ticket["report_state"] == "failed"
    assert ticket["deliverable"]["proposed_objects"] == []


@pytest.mark.asyncio
@pytest.mark.parametrize("latest_enabled", [True, False])
async def test_only_latest_enabled_project_skill_is_offered(
    client, db, researcher_user, researcher_headers, real_baseline_runtime, monkeypatch, tmp_path,
    latest_enabled,
):
    from app.models.research_ticket import ProjectPolicy
    from app.models.skill_pack import SkillPackRecord

    project_id, _ = await create_inputs(client, db, researcher_user, researcher_headers)
    packs = tmp_path / "packs"
    monkeypatch.setattr(settings, "skill_pack_dir", str(packs))
    for version in (1, 2):
        folder = packs / "baseline-math" / str(version)
        folder.mkdir(parents=True)
        (folder / "SKILL.md").write_text(f"# Calculate a mean, method version {version}")
        db.add(SkillPackRecord(id="baseline-math", version=version, name="Baseline math",
                               description="Reproduce numeric means", storage_path=f"baseline-math/{version}",
                               is_enabled=version == 1 or latest_enabled))
    db.add(SkillPackRecord(id="unselected", version=1, name="Not selected", description="Do not offer",
                           storage_path="unselected/1", is_enabled=True))
    db.add(ProjectPolicy(project_id=project_id, enabled_plugins_json=["baseline-math"]))
    await db.commit()

    async def selected(*, cwd, **kwargs):
        payload = await real_baseline_runtime(cwd=cwd, **kwargs)
        result_path = Path(cwd) / "outputs/result.json"
        result = json.loads(result_path.read_text())
        result["selected_skill_ids"] = ["baseline-math"] if latest_enabled else []
        result_path.write_text(json.dumps(result))
        return payload

    monkeypatch.setattr(baseline_execution, "run_codex_runtime", selected)
    ticket = await create_ticket(client, project_id, researcher_headers)
    evidence = ticket["deliverable"]["baseline_execution"]
    assert ticket["report_state"] == "ready"
    skills = evidence["manifest"]["skills"]
    assert [skill["id"] for skill in skills] == (["baseline-math"] if latest_enabled else [])
    if latest_enabled:
        assert skills[0]["version"] == 2
        assert skills[0]["sha256"]
        assert evidence["selected_skill_ids"] == ["baseline-math"]
