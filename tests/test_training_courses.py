import json
from datetime import UTC, datetime

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.asset_revision import AssetRevision
from app.models.access_policy import AccessPolicy
from app.models.research_asset import ResearchAsset
from app.models.source import Chunk, Source
from app.models.training import (
    TrainingAssignment,
    TrainingCourseVersion,
    TrainingKnowledgePoint,
    TrainingModuleAssignment,
    TrainingUnit,
    TrainingUnitAssessmentAttempt,
)
from app.models.user import User
from app.services.training_service import (
    _normalize_evidence_citations,
    _resolve_evidence_excerpt,
    _validated_evidence_excerpt,
    translate_unit_assessment_content,
)

pytestmark = pytest.mark.asyncio


async def test_normalize_evidence_citations_converts_model_markers() -> None:
    markdown = (
        "Grounded by multiple sources \ue200cite\ue202E1\ue202E4\ue201. "
        "Existing references such as [E2] remain unchanged."
    )

    assert _normalize_evidence_citations(markdown) == (
        "Grounded by multiple sources [E1] [E4]. "
        "Existing references such as [E2] remain unchanged."
    )


async def test_validated_evidence_excerpt_requires_quote_from_selected_chunk() -> None:
    source = (
        "Agents need governed content. Organizations avoid being locked into "
        "a single AI tool or technology. Flexible architecture preserves choice."
    )

    excerpt = _validated_evidence_excerpt(
        source, "Organizations avoid being locked into a single AI tool or technology."
    )

    assert "locked into a single AI tool" in excerpt

    with pytest.raises(ValueError, match="not present"):
        _validated_evidence_excerpt(
            source, "This unrelated claim does not occur anywhere in the source."
        )


async def test_resolve_evidence_excerpt_corrects_the_selected_chunk() -> None:
    evidence_by_id = {
        "E1": {"evidence_id": "E1", "excerpt": "Cover and table of contents."},
        "E2": {
            "evidence_id": "E2",
            "excerpt": "Flexible architecture prevents lock-in to a single AI tool.",
        },
    }

    evidence, excerpt = _resolve_evidence_excerpt(
        evidence_by_id,
        "E1",
        "Flexible architecture prevents lock-in to a single AI tool.",
    )

    assert evidence["evidence_id"] == "E2"
    assert "prevents lock-in" in excerpt

    with pytest.raises(ValueError, match="any available evidence"):
        _resolve_evidence_excerpt(
            evidence_by_id,
            "E1",
            "This sentence was invented by the model.",
        )


async def test_assessment_translation_is_cached_without_changing_answer_keys(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    questions = [{
        "id": "Q1",
        "question_type": "single_choice",
        "prompt": "Which record is required?",
        "options": [
            {"id": "A", "text": "Chain of custody"},
            {"id": "B", "text": "Lunch menu"},
        ],
        "correct_option_id": "A",
        "reference_answer": None,
        "evidence_ids": ["E1"],
    }, {
        "id": "Q2",
        "question_type": "short_answer",
        "prompt": "Explain why the record matters.",
        "options": None,
        "correct_option_id": None,
        "reference_answer": "It preserves traceability.",
        "evidence_ids": ["E1"],
    }]
    attempt = TrainingUnitAssessmentAttempt(
        module_assignment_id="assignment-1",
        unit_id="unit-1",
        attempt_number=1,
        questions_json=questions,
        translations_json={},
    )

    class FakeDb:
        commits = 0

        async def commit(self) -> None:
            self.commits += 1

    fake_db = FakeDb()
    completion_calls = 0

    async def fake_runtime(*_args, **_kwargs) -> str:
        return "test"

    async def fake_completion(*_args, **_kwargs) -> str:
        nonlocal completion_calls
        completion_calls += 1
        if completion_calls == 1:
            return "not valid JSON"
        return json.dumps({
            "questions": [{
                **questions[0],
                "prompt": "必须记录哪一项？",
                "options": [
                    {"id": "A", "text": "监管链记录"},
                    {"id": "B", "text": "午餐菜单"},
                ],
            }, {
                **questions[1],
                "prompt": "说明该记录为何重要。",
                "reference_answer": "它确保样本可追溯。",
            }],
            "feedback": None,
        }, ensure_ascii=False)

    monkeypatch.setattr(
        "app.services.training_service.get_runtime_value", fake_runtime
    )
    monkeypatch.setattr(
        "app.services.training_service.get_runtime_llm_api_key", fake_runtime
    )
    monkeypatch.setattr(
        "app.services.training_service.llm_service.complete_llm_response",
        fake_completion,
    )

    translated, _ = await translate_unit_assessment_content(
        fake_db,
        attempt=attempt,
        questions=questions,
        feedback=None,
        target_language="zh-CN",
    )
    cached, _ = await translate_unit_assessment_content(
        fake_db,
        attempt=attempt,
        questions=questions,
        feedback=None,
        target_language="zh-CN",
    )

    assert translated == cached
    assert completion_calls == 2
    assert fake_db.commits == 1
    assert translated[0]["correct_option_id"] == "A"
    assert [option["id"] for option in translated[0]["options"]] == ["A", "B"]
    assert translated[0]["evidence_ids"] == ["E1"]


async def test_admin_can_choose_course_content_language(
    client: AsyncClient,
    auth_headers: dict,
) -> None:
    response = await client.post(
        "/api/v1/training/courses",
        json={"name": "Chinese onboarding", "content_language": "zh-CN"},
        headers=auth_headers,
    )

    assert response.status_code == 201
    assert response.json()["content_language"] == "zh-CN"


async def test_course_update_preserves_content_language_when_omitted(
    client: AsyncClient,
    auth_headers: dict,
) -> None:
    created = await client.post(
        "/api/v1/training/courses",
        json={"name": "Chinese onboarding", "content_language": "zh-CN"},
        headers=auth_headers,
    )

    response = await client.put(
        f"/api/v1/training/courses/{created.json()['id']}",
        json={"name": "Updated onboarding"},
        headers=auth_headers,
    )

    assert response.status_code == 200
    assert response.json()["content_language"] == "zh-CN"


async def test_admin_can_publish_a_course_and_assign_it(
    client: AsyncClient,
    auth_headers: dict,
    researcher_headers: dict,
    admin_user: User,
    researcher_user: User,
    db: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = Source(
        type="file",
        name="onboarding-notes.pdf",
        owner_id=admin_user.id,
        processing_state="ready",
    )
    db.add(source)
    await db.flush()
    db.add(Chunk(source_id=source.id, chunk_index=0, text="Record each sample handoff in the chain of custody."))
    await db.flush()
    asset = ResearchAsset(
        asset_type="uploaded_file",
        title="Lab onboarding notes",
        source_id=source.id,
        owner_id=admin_user.id,
        steward_user_id=admin_user.id,
        classification="internal",
        catalog_status="published",
        lifecycle_status="active",
        visibility_scope="lab_public",
    )
    db.add(asset)
    await db.flush()
    revision = AssetRevision(
        research_asset_id=asset.id,
        revision_number=1,
        processing_state="ready",
        manifest_sha256="c" * 64,
        created_by=admin_user.id,
        sealed_at=datetime.now(UTC),
    )
    db.add(revision)
    await db.flush()
    asset.current_revision_id = revision.id
    await db.commit()

    training_grant = await client.post(
        f"/api/v1/research-assets/{asset.id}/training-grants",
        json={"user_ids": [researcher_user.id], "duration_days": 90},
        headers=auth_headers,
    )
    assert training_grant.status_code == 204

    created = await client.post(
        "/api/v1/training/courses",
        json={
            "name": "Lab onboarding",
            "description": "Core lab practices",
            "content_language": "zh-CN",
        },
        headers=auth_headers,
    )
    assert created.status_code == 201
    course = created.json()

    with_asset = await client.post(
        f"/api/v1/training/courses/{course['id']}/assets",
        json={"research_asset_ids": [asset.id]},
        headers=auth_headers,
    )
    assert with_asset.status_code == 200
    course_asset_id = with_asset.json()["version"]["assets"][0]["id"]

    removed_asset = await client.delete(
        f"/api/v1/training/courses/{course['id']}/assets/{course_asset_id}",
        headers=auth_headers,
    )
    assert removed_asset.status_code == 200
    assert removed_asset.json()["version"]["assets"] == []

    rebound_asset = await client.post(
        f"/api/v1/training/courses/{course['id']}/assets",
        json={"research_asset_ids": [asset.id]},
        headers=auth_headers,
    )
    assert rebound_asset.status_code == 200
    course_asset_id = rebound_asset.json()["version"]["assets"][0]["id"]

    completion_prompts: list[str] = []

    async def fake_completion(messages, **_kwargs) -> str:
        assert any(
            "Write all generated training content in Simplified Chinese." in message["content"]
            for message in messages
        )
        completion_prompts.append(messages[-1]["content"])
        if "lesson_markdown" in messages[-1]["content"]:
            return json.dumps({
                "outline": ["Chain of custody", "Recording handoffs"],
                "lesson_markdown": (
                    "# Chain of custody\n"
                    "Record every sample handoff \ue200cite\ue202E1\ue201."
                ),
                "evidence_ids": ["E1"],
                "visuals": [{
                    "kind": "concept_diagram",
                    "title": "Sample traceability flow",
                    "caption": "AI-generated diagram grounded in E1.",
                    "evidence_id": "E1",
                    "nodes": [
                        {"id": "N1", "label": "Sample handoff"},
                        {"id": "N2", "label": "Custody record"},
                    ],
                    "connections": [{"from": "N1", "to": "N2"}],
                }],
                "knowledge_points": [
                    {
                        "title": "Chain of custody",
                        "description": "Understand why every handoff must be recorded.",
                        "evidence_id": "E1",
                        "supporting_quote": "Record each sample handoff in the chain of custody.",
                        "assessment_question": {
                            "id": "Q1",
                            "question_type": "single_choice",
                            "prompt": "What should be recorded?",
                            "options": [
                                {"id": "A", "text": "Every sample handoff"},
                                {"id": "B", "text": "Only final storage"},
                            ],
                            "correct_option_id": "A",
                            "evidence_ids": ["E1"],
                        },
                    },
                    {
                        "title": "Traceability",
                        "description": "Explain how handoff records preserve traceability.",
                        "evidence_id": "E9",
                        "supporting_quote": "Record each sample handoff in the chain of custody.",
                        "assessment_question": {
                            "id": "Q2",
                            "question_type": "short_answer",
                            "prompt": "Why are handoffs recorded?",
                            "reference_answer": "They preserve traceability.",
                            "evidence_ids": ["E9"],
                        },
                    },
                ],
            })
        if "knowledge_points" in messages[-1]["content"]:
            return json.dumps({
                "knowledge_points": [{
                    "title": "Sample handling",
                    "description": "Track every transfer so samples remain traceable.",
                    "evidence_id": "E1",
                    "supporting_quote": "Record each sample handoff in the chain of custody.",
                }],
            })
        if "Answer the learner" in messages[-1]["content"]:
            return json.dumps({
                "answer": "Record every sample handoff in the chain of custody.",
                "evidence_ids": ["E1"],
            })
        if "Create a unit assessment" in messages[-1]["content"]:
            return json.dumps({
                "questions": [
                    {
                        "id": "Q1",
                        "question_type": "single_choice",
                        "prompt": "What should be recorded?",
                        "options": [
                            {"id": "A", "text": "Every sample handoff"},
                            {"id": "B", "text": "Only final storage"},
                            {"id": "C", "text": "Only the sample name"},
                            {"id": "D", "text": "Nothing"},
                        ],
                        "correct_option_id": "A",
                        "evidence_ids": ["E1"],
                    },
                    {
                        "id": "Q2",
                        "question_type": "short_answer",
                        "prompt": "Explain why handoffs are recorded.",
                        "reference_answer": "They preserve traceability.",
                        "evidence_ids": ["E1"],
                    },
                ],
            })
        if "Grade the learner" in messages[-1]["content"]:
            return json.dumps({"scores": {"Q2": 80}, "feedback": "Good explanation."})
        if "Create one question" in messages[-1]["content"]:
            return json.dumps({
                "question_type": "single_choice",
                "question_text": "What must be recorded for sample traceability?",
                "options": [
                    {"id": "A", "text": "Every sample handoff"},
                    {"id": "B", "text": "Only the final storage location"},
                    {"id": "C", "text": "Only the sample name"},
                    {"id": "D", "text": "Nothing after collection"},
                ],
                "correct_option_id": "A",
            })
        return json.dumps({
            "verdict": "partial",
            "score": 70,
            "feedback": "You identified the handoff, but explain how it is recorded.",
        })

    monkeypatch.setattr("app.services.llm_service.complete_llm_response", fake_completion)
    module_response = await client.post(
        f"/api/v1/training/courses/{course['id']}/modules",
        json={"title": "Sample operations"},
        headers=auth_headers,
    )
    module_id = module_response.json()["id"]
    unit_response = await client.post(
        f"/api/v1/training/courses/{course['id']}/modules/{module_id}/units",
        json={"title": "Sample custody"},
        headers=auth_headers,
    )
    unit_id = unit_response.json()["id"]
    bound_unit = await client.post(
        f"/api/v1/training/courses/{course['id']}/modules/{module_id}/units/{unit_id}/assets",
        json={"course_asset_ids": [course_asset_id]},
        headers=auth_headers,
    )
    assert bound_unit.status_code == 200
    cleared_unit_assets = await client.put(
        f"/api/v1/training/courses/{course['id']}/modules/{module_id}/units/{unit_id}/assets",
        json={"course_asset_ids": []},
        headers=auth_headers,
    )
    assert cleared_unit_assets.status_code == 200
    assert cleared_unit_assets.json()["course_asset_ids"] == []
    rebound_unit = await client.put(
        f"/api/v1/training/courses/{course['id']}/modules/{module_id}/units/{unit_id}/assets",
        json={"course_asset_ids": [course_asset_id]},
        headers=auth_headers,
    )
    assert rebound_unit.status_code == 200
    generated_lesson = await client.post(
        f"/api/v1/training/courses/{course['id']}/modules/{module_id}/units/{unit_id}/lesson/generate",
        headers=auth_headers,
    )
    assert generated_lesson.status_code == 200
    assert generated_lesson.json()["lesson"]["status"] == "pending"
    assert generated_lesson.json()["lesson"]["outline"] == ["Chain of custody", "Recording handoffs"]
    assert generated_lesson.json()["lesson"]["lesson_markdown"] == (
        "# Chain of custody\nRecord every sample handoff [E1]."
    )
    assert generated_lesson.json()["lesson"]["visuals"][0]["kind"] == "concept_diagram"
    assert generated_lesson.json()["lesson"]["evidence"][0]["source_id"] == source.id
    assert generated_lesson.json()["lesson"]["evidence"][0]["source_title"] == "Lab onboarding notes"
    generated_unit_points = generated_lesson.json()["knowledge_points"]
    assert [point["title"] for point in generated_unit_points] == [
        "Chain of custody",
        "Traceability",
    ]
    assert [point["assessment_question"]["question_type"] for point in generated_unit_points] == [
        "single_choice",
        "short_answer",
    ]
    assert all(point["unit_id"] == unit_id for point in generated_unit_points)
    edited_lesson_markdown = (
        "# Chain of custody\n"
        "Record every handoff immediately so the sample remains traceable [E1]."
    )
    edited_lesson = await client.put(
        f"/api/v1/training/courses/{course['id']}/modules/{module_id}/units/{unit_id}/lesson",
        json={"lesson_markdown": edited_lesson_markdown},
        headers=auth_headers,
    )
    assert edited_lesson.status_code == 200
    assert edited_lesson.json()["lesson"]["status"] == "pending"
    assert edited_lesson.json()["lesson"]["lesson_markdown"] == edited_lesson_markdown
    assert edited_lesson.json()["lesson"]["evidence"] == generated_lesson.json()["lesson"]["evidence"]
    forbidden_lesson_edit = await client.put(
        f"/api/v1/training/courses/{course['id']}/modules/{module_id}/units/{unit_id}/lesson",
        json={"lesson_markdown": "Unauthorized edit"},
        headers=researcher_headers,
    )
    assert forbidden_lesson_edit.status_code == 403
    approved_lesson = await client.post(
        f"/api/v1/training/courses/{course['id']}/modules/{module_id}/units/{unit_id}/lesson/approve",
        headers=auth_headers,
    )
    assert approved_lesson.status_code == 200
    assert approved_lesson.json()["status"] == "approved"
    approved_lesson_edit = await client.put(
        f"/api/v1/training/courses/{course['id']}/modules/{module_id}/units/{unit_id}/lesson",
        json={"lesson_markdown": "Late edit"},
        headers=auth_headers,
    )
    assert approved_lesson_edit.status_code == 409
    extracted = await client.post(
        f"/api/v1/training/courses/{course['id']}/knowledge-points/extract",
        headers=auth_headers,
    )
    assert extracted.status_code == 200
    generated_point = next(
        point
        for point in extracted.json()["version"]["knowledge_points"]
        if point["unit_id"] is None
    )
    assert generated_point["review_status"] == "pending"
    assert generated_point["course_asset_id"] == course_asset_id
    updated = await client.put(
        f"/api/v1/training/courses/{course['id']}/knowledge-points/{generated_point['id']}",
        json={"title": "Sample custody", "description": "Record every transfer to preserve traceability."},
        headers=auth_headers,
    )
    assert updated.status_code == 200
    generated_point = next(
        point
        for point in updated.json()["version"]["knowledge_points"]
        if point["id"] == generated_point["id"]
    )
    assert generated_point["title"] == "Sample custody"
    approved = await client.post(
        f"/api/v1/training/courses/{course['id']}/knowledge-points/{generated_point['id']}/approve",
        headers=auth_headers,
    )
    assert approved.status_code == 200
    approved_point = next(
        point
        for point in approved.json()["version"]["knowledge_points"]
        if point["id"] == generated_point["id"]
    )
    assert approved_point["review_status"] == "approved"

    published = await client.post(
        f"/api/v1/training/courses/{course['id']}/publish",
        headers=auth_headers,
    )
    assert published.status_code == 200
    assert published.json()["version"]["status"] == "published"

    assigned = await client.post(
        f"/api/v1/training/courses/{course['id']}/assignments",
        json={"trainee_id": researcher_user.id},
        headers=auth_headers,
    )
    assert assigned.status_code == 201

    assigned_module = await client.post(
        f"/api/v1/training/courses/{course['id']}/modules/{module_id}/assignments",
        json={"trainee_ids": [researcher_user.id]},
        headers=auth_headers,
    )
    assert assigned_module.status_code == 200

    my_modules = await client.get(
        "/api/v1/training/module-assignments/me", headers=researcher_headers
    )
    assert my_modules.status_code == 200
    assert my_modules.json()[0] == {
        "id": my_modules.json()[0]["id"],
        "course_id": course["id"],
        "course_name": "Lab onboarding",
        "module_id": module_id,
        "module_title": "Sample operations",
        "status": "not_started",
        "requires_retraining": False,
        "latest_unit_assessment_score": None,
        "assigned_at": my_modules.json()[0]["assigned_at"],
    }
    training_overview = await client.get(
        "/api/v1/training/me", headers=researcher_headers
    )
    assert training_overview.status_code == 200
    assert len(training_overview.json()) == 1
    assert training_overview.json()[0] == {
        "course_id": course["id"],
        "course_name": "Lab onboarding",
        "course_assignment_id": assigned.json()["id"],
        "status": "not_started",
        "due_at": None,
        "next_kind": "module",
        "next_assignment_id": my_modules.json()[0]["id"],
        "modules": [{
            "assignment_id": my_modules.json()[0]["id"],
            "module_id": module_id,
            "module_title": "Sample operations",
            "status": "not_started",
            "requires_retraining": False,
            "latest_unit_assessment_score": None,
        }],
    }
    module_learning = await client.get(
        f"/api/v1/training/module-assignments/{my_modules.json()[0]['id']}/learning",
        headers=researcher_headers,
    )
    assert module_learning.status_code == 200
    assert module_learning.json()["course_name"] == "Lab onboarding"
    assert module_learning.json()["module_title"] == "Sample operations"
    assert module_learning.json()["units"][0]["title"] == "Sample custody"
    assert module_learning.json()["units"][0]["lesson"]["status"] == "approved"
    assert module_learning.json()["units"][0]["lesson"]["lesson_markdown"] == edited_lesson_markdown
    unit_answer = await client.post(
        f"/api/v1/training/module-assignments/{my_modules.json()[0]['id']}/units/{unit_id}/ask",
        json={"question": "How do I keep a sample traceable?"},
        headers=researcher_headers,
    )
    assert unit_answer.status_code == 200
    assert unit_answer.json()["answer"] == "Record every sample handoff in the chain of custody."
    assert unit_answer.json()["evidence"][0]["chunk_index"] == 0
    assert [item["role"] for item in unit_answer.json()["history"]] == ["user", "assistant"]
    assessment = await client.post(
        f"/api/v1/training/module-assignments/{my_modules.json()[0]['id']}/units/{unit_id}/assessment",
        headers=researcher_headers,
    )
    assert assessment.status_code == 201
    assert assessment.json()["pass_score"] == 80
    assert assessment.json()["questions"][0]["question_type"] == "single_choice"
    assert "correct_option_id" not in assessment.json()["questions"][0]
    assert not any("Create a unit assessment" in prompt for prompt in completion_prompts)
    assessed = await client.post(
        f"/api/v1/training/unit-assessments/{assessment.json()['id']}/answer",
        json={"answers": {"Q1": "A", "Q2": "To preserve traceability."}},
        headers=researcher_headers,
    )
    assert assessed.status_code == 200
    assert assessed.json()["score"] == 90
    assert assessed.json()["passed"] is True

    completed_modules = await client.get(
        "/api/v1/training/module-assignments/me", headers=researcher_headers
    )
    assert completed_modules.status_code == 200
    assert completed_modules.json()[0]["status"] == "completed"
    assert completed_modules.json()[0]["latest_unit_assessment_score"] == 90
    completed_overview = await client.get(
        "/api/v1/training/me", headers=researcher_headers
    )
    assert completed_overview.status_code == 200
    assert completed_overview.json()[0]["status"] == "in_progress"
    assert completed_overview.json()[0]["next_kind"] == "course"
    assert completed_overview.json()[0]["next_assignment_id"] == assigned.json()["id"]
    assert completed_overview.json()[0]["modules"][0]["status"] == "completed"
    assert completed_overview.json()[0]["modules"][0]["latest_unit_assessment_score"] == 90

    courses = await client.get("/api/v1/training/courses", headers=auth_headers)
    assert courses.status_code == 200
    assert courses.json()[0]["version"]["assignees"] == [{
        "user_id": researcher_user.id,
        "display_name": researcher_user.display_name or researcher_user.username,
        "status": "not_started",
    }]

    mine = await client.get("/api/v1/training/assignments/me", headers=researcher_headers)
    assert mine.status_code == 200
    assert mine.json() == [
        {
            "id": assigned.json()["id"],
            "course_id": course["id"],
            "course_name": "Lab onboarding",
            "course_version_id": course["version"]["id"],
            "status": "not_started",
            "due_at": None,
            "assigned_at": assigned.json()["assigned_at"],
        }
    ]

    learning = await client.get(
        f"/api/v1/training/assignments/{assigned.json()['id']}/learning",
        headers=researcher_headers,
    )
    assert learning.status_code == 200
    assert learning.json()["name"] == "Lab onboarding"
    learning_point = next(
        point
        for point in learning.json()["version"]["knowledge_points"]
        if point["id"] == generated_point["id"]
    )
    assert learning_point == {
        "id": generated_point["id"],
        "unit_id": None,
        "title": "Sample custody",
        "description": "Record every transfer to preserve traceability.",
        "review_status": "approved",
        "evidence_excerpt": "Record each sample handoff in the chain of custody.",
        "course_asset_id": course_asset_id,
        "origin_chunk_ref": learning_point["origin_chunk_ref"],
        "assessment_question": None,
    }

    for unit_point in generated_unit_points:
        unit_topic_practice = await client.post(
            f"/api/v1/training/assignments/{assigned.json()['id']}/practice",
            json={"knowledge_point_id": unit_point["id"]},
            headers=researcher_headers,
        )
        assert unit_topic_practice.status_code == 201
        unit_topic_answer = await client.post(
            f"/api/v1/training/practice/{unit_topic_practice.json()['id']}/answer",
            json={"answer_text": "A"},
            headers=researcher_headers,
        )
        assert unit_topic_answer.status_code == 200
        assert unit_topic_answer.json()["verdict"] == "correct"

    locked_assessment = await client.post(
        f"/api/v1/training/assignments/{assigned.json()['id']}/final-assessment",
        headers=researcher_headers,
    )
    assert locked_assessment.status_code == 409
    assert locked_assessment.json()["detail"] == "Complete all topic practices first"

    practice = await client.post(
        f"/api/v1/training/assignments/{assigned.json()['id']}/practice",
        json={"knowledge_point_id": generated_point["id"]},
        headers=researcher_headers,
    )
    assert practice.status_code == 201
    assert practice.json()["status"] == "pending"
    assert practice.json()["question_type"] == "single_choice"
    assert practice.json()["options"][0]["id"] == "A"
    answered = await client.post(
        f"/api/v1/training/practice/{practice.json()['id']}/answer",
        json={"answer_text": "A"},
        headers=researcher_headers,
    )
    assert answered.status_code == 200
    assert answered.json()["verdict"] == "correct"
    assert answered.json()["score"] == 100
    next_step = await client.get(
        f"/api/v1/training/assignments/{assigned.json()['id']}/next-step",
        headers=researcher_headers,
    )
    assert next_step.status_code == 200
    assert next_step.json() == {
        "knowledge_point_id": None,
        "reason": "complete",
    }

    final_assessment = await client.post(
        f"/api/v1/training/assignments/{assigned.json()['id']}/final-assessment",
        headers=researcher_headers,
    )
    assert final_assessment.status_code == 201
    assert final_assessment.json()["question_text"].startswith("请综合说明")
    assert "Sample custody" in final_assessment.json()["question_text"]
    final_answer = await client.post(
        f"/api/v1/training/final-assessments/{final_assessment.json()['id']}/answer",
        json={"answer_text": "I would record every handoff in the chain of custody."},
        headers=researcher_headers,
    )
    assert final_answer.status_code == 200
    assert final_answer.json()["status"] == "evaluated"
    assert final_answer.json()["score"] == 70

    report = await client.get(f"/api/v1/training/reports/{researcher_user.id}", headers=auth_headers)
    assert report.status_code == 200
    assert report.json()["trainee_id"] == researcher_user.id
    assert report.json()["courses"] == [{
        "course_id": course["id"],
        "course_name": "Lab onboarding",
        "assignment_status": "in_progress",
        "assigned_at": assigned.json()["assigned_at"],
        "total_topics": 3,
        "completed_topics": 3,
        "practice_average_score": 100.0,
        "final_assessment_status": "evaluated",
        "final_assessment_score": 70,
        "last_answered_at": report.json()["courses"][0]["last_answered_at"],
    }]
    denied_report = await client.get(f"/api/v1/training/reports/{researcher_user.id}", headers=researcher_headers)
    assert denied_report.status_code == 403

    db.add(
        AccessPolicy(
            research_asset_id=asset.id,
            asset_revision_id=revision.id,
            subject_type="user",
            subject_id=researcher_user.id,
            capabilities_json=["content:use_in_agent"],
            effect="deny",
            created_by=admin_user.id,
        )
    )
    await db.commit()
    revoked = await client.get(
        f"/api/v1/training/assignments/{assigned.json()['id']}/learning",
        headers=researcher_headers,
    )
    assert revoked.status_code == 403


async def test_manager_can_discard_pending_point_and_assign_multiple_members(
    client: AsyncClient,
    auth_headers: dict,
    admin_user: User,
    researcher_user: User,
    db: AsyncSession,
) -> None:
    created = await client.post("/api/v1/training/courses", json={"name": "Batch course"}, headers=auth_headers)
    assert created.status_code == 201
    course = created.json()
    version = course["version"]
    point = TrainingKnowledgePoint(
        course_version_id=version["id"], title="Discard me", description="Candidate", review_status="pending", created_by=admin_user.id,
    )
    db.add(point)
    await db.commit()
    discarded = await client.delete(
        f"/api/v1/training/courses/{course['id']}/knowledge-points/{point.id}", headers=auth_headers,
    )
    assert discarded.status_code == 204

    version_record = await db.get(TrainingCourseVersion, version["id"])
    assert version_record is not None
    version_record.status = "published"
    first = TrainingAssignment(course_version_id=version["id"], trainee_id=researcher_user.id, assigned_by=admin_user.id)
    db.add(first)
    await db.commit()
    assigned = await client.post(
        f"/api/v1/training/courses/{course['id']}/assignments/batch",
        json={"trainee_ids": [researcher_user.id, admin_user.id]},
        headers=auth_headers,
    )
    assert assigned.status_code == 201
    assert [item["id"] for item in assigned.json()["assignments"]]
    assert assigned.json()["skipped_trainee_ids"] == [researcher_user.id]


async def test_assignee_can_practice_a_published_knowledge_point(
    client: AsyncClient,
    researcher_headers: dict,
) -> None:
    create_response = await client.post(
        "/api/v1/training/courses",
        json={"name": "Researcher course"},
        headers=researcher_headers,
    )
    assert create_response.status_code == 403
    response = await client.post(
        "/api/v1/training/assignments/missing/practice",
        json={"knowledge_point_id": "missing"},
        headers=researcher_headers,
    )
    assert response.status_code == 404


async def test_admin_can_structure_course_into_ordered_modules_and_units(
    client: AsyncClient,
    auth_headers: dict,
    researcher_headers: dict,
    researcher_user: User,
) -> None:
    created = await client.post(
        "/api/v1/training/courses",
        json={"name": "Research onboarding"},
        headers=auth_headers,
    )
    assert created.status_code == 201
    course_id = created.json()["id"]

    updated_course = await client.put(
        f"/api/v1/training/courses/{course_id}",
        json={
            "name": "Research methods onboarding",
            "description": "Updated course description.",
            "content_language": "en-US",
        },
        headers=auth_headers,
    )
    assert updated_course.status_code == 200
    assert updated_course.json()["name"] == "Research methods onboarding"
    assert updated_course.json()["description"] == "Updated course description."
    assert updated_course.json()["content_language"] == "en-US"

    forbidden_update = await client.put(
        f"/api/v1/training/courses/{course_id}",
        json={"name": "Researcher edit attempt"},
        headers=researcher_headers,
    )
    assert forbidden_update.status_code == 403

    blank_name = await client.put(
        f"/api/v1/training/courses/{course_id}",
        json={"name": "   "},
        headers=auth_headers,
    )
    assert blank_name.status_code == 422

    module_response = await client.post(
        f"/api/v1/training/courses/{course_id}/modules",
        json={"title": "Evidence foundations", "description": "Read and question evidence."},
        headers=auth_headers,
    )
    assert module_response.status_code == 201
    module_id = module_response.json()["id"]

    unit_response = await client.post(
        f"/api/v1/training/courses/{course_id}/modules/{module_id}/units",
        json={"title": "Source evaluation", "description": "Evaluate source reliability."},
        headers=auth_headers,
    )
    assert unit_response.status_code == 201

    detail = await client.get(f"/api/v1/training/courses/{course_id}", headers=auth_headers)
    assert detail.status_code == 200
    assert detail.json()["version"]["modules"] == [{
        "id": module_id,
        "title": "Evidence foundations",
        "description": "Read and question evidence.",
        "position": 0,
        "status": "draft",
        "revision_number": 1,
        "assignees": [],
        "units": [{
            "id": unit_response.json()["id"],
            "title": "Source evaluation",
            "description": "Evaluate source reliability.",
                "position": 0,
                "status": "draft",
                "pass_score": 80,
                "course_asset_ids": [],
                "knowledge_points": [],
            "lesson": None,
        }],
    }]

    forbidden = await client.post(
        f"/api/v1/training/courses/{course_id}/modules",
        json={"title": "Forbidden"},
        headers=researcher_headers,
    )
    assert forbidden.status_code == 403

    assigned_module = await client.post(
        f"/api/v1/training/courses/{course_id}/modules/{module_id}/assignments",
        json={"trainee_ids": [researcher_user.id]},
        headers=auth_headers,
    )
    assert assigned_module.status_code == 200
    assert assigned_module.json()["assignees"][0]["user_id"] == researcher_user.id


async def test_manager_can_extend_and_revise_a_published_module(
    client: AsyncClient,
    auth_headers: dict,
    researcher_headers: dict,
    researcher_user: User,
    db: AsyncSession,
) -> None:
    created = await client.post(
        "/api/v1/training/courses",
        json={"name": "Published course"},
        headers=auth_headers,
    )
    assert created.status_code == 201
    course = created.json()
    module_response = await client.post(
        f"/api/v1/training/courses/{course['id']}/modules",
        json={"title": "Original module"},
        headers=auth_headers,
    )
    assert module_response.status_code == 201
    module_id = module_response.json()["id"]

    version = await db.get(TrainingCourseVersion, course["version"]["id"])
    assert version is not None
    version.status = "published"
    await db.commit()
    assigned = await client.post(
        f"/api/v1/training/courses/{course['id']}/modules/{module_id}/assignments",
        json={"trainee_ids": [researcher_user.id]},
        headers=auth_headers,
    )
    assert assigned.status_code == 200
    assignment = await db.scalar(
        select(TrainingModuleAssignment).where(
            TrainingModuleAssignment.module_id == module_id,
            TrainingModuleAssignment.trainee_id == researcher_user.id,
        )
    )
    assert assignment is not None
    assignment.status = "completed"
    old_unit = TrainingUnit(
        module_id=module_id,
        title="Previously completed unit",
        position=0,
        status="approved",
        created_by=assignment.assigned_by,
    )
    db.add(old_unit)
    await db.flush()
    db.add(TrainingUnitAssessmentAttempt(
        module_assignment_id=assignment.id,
        unit_id=old_unit.id,
        attempt_number=1,
        questions_json=[],
        status="evaluated",
        score=90,
        passed=True,
    ))
    await db.commit()

    revised = await client.put(
        f"/api/v1/training/courses/{course['id']}/modules/{module_id}",
        json={"title": "Revised module", "description": "New required content"},
        headers=auth_headers,
    )
    assert revised.status_code == 200
    assert revised.json()["title"] == "Revised module"
    assert revised.json()["revision_number"] == 2
    assert revised.json()["assignees"] == [{
        "user_id": researcher_user.id,
        "display_name": researcher_user.display_name or researcher_user.username,
        "status": "not_started",
        "requires_retraining": True,
    }]
    retraining = await client.get(
        "/api/v1/training/module-assignments/me",
        headers=researcher_headers,
    )
    assert retraining.status_code == 200
    assert retraining.json()[0]["status"] == "not_started"
    assert retraining.json()[0]["requires_retraining"] is True
    assert retraining.json()[0]["latest_unit_assessment_score"] is None

    added_unit = await client.post(
        f"/api/v1/training/courses/{course['id']}/modules/{module_id}/units",
        json={"title": "New required unit", "pass_score": 85},
        headers=auth_headers,
    )
    assert added_unit.status_code == 201
    assert added_unit.json()["title"] == "New required unit"

    appended = await client.post(
        f"/api/v1/training/courses/{course['id']}/modules",
        json={"title": "New published module"},
        headers=auth_headers,
    )
    assert appended.status_code == 201
    assert appended.json()["revision_number"] == 1


async def test_manager_can_generate_modules_from_source_chapters(
    client: AsyncClient,
    auth_headers: dict,
    admin_user: User,
    db: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = Source(
        type="file",
        name="safety-handbook.pdf",
        owner_id=admin_user.id,
        processing_state="ready",
    )
    db.add(source)
    await db.flush()
    db.add(Chunk(
        source_id=source.id,
        chunk_index=0,
        text="Chapter 1 Safety foundations. Section 1.1 Personal protective equipment.",
    ))
    asset = ResearchAsset(
        asset_type="uploaded_file",
        title="Safety handbook",
        source_id=source.id,
        owner_id=admin_user.id,
        steward_user_id=admin_user.id,
        classification="internal",
        catalog_status="published",
        lifecycle_status="active",
        visibility_scope="private",
    )
    db.add(asset)
    await db.flush()
    revision = AssetRevision(
        research_asset_id=asset.id,
        revision_number=1,
        processing_state="ready",
        manifest_sha256="s" * 64,
        created_by=admin_user.id,
        sealed_at=datetime.now(UTC),
    )
    db.add(revision)
    await db.flush()
    asset.current_revision_id = revision.id
    db.add(AccessPolicy(
        research_asset_id=asset.id,
        asset_revision_id=revision.id,
        subject_type="user",
        subject_id=admin_user.id,
        capabilities_json=["content:preview"],
        created_by=admin_user.id,
    ))
    await db.commit()

    grant = await client.post(
        f"/api/v1/research-assets/{asset.id}/training-grants",
        json={"user_ids": [admin_user.id], "duration_days": 30},
        headers=auth_headers,
    )
    assert grant.status_code == 204

    course_response = await client.post(
        "/api/v1/training/courses",
        json={"name": "Safety training", "content_language": "zh-CN"},
        headers=auth_headers,
    )
    assert course_response.status_code == 201
    course = course_response.json()
    bound = await client.post(
        f"/api/v1/training/courses/{course['id']}/assets",
        json={"research_asset_ids": [asset.id]},
        headers=auth_headers,
    )
    assert bound.status_code == 200
    course_asset_id = bound.json()["version"]["assets"][0]["id"]
    version = await db.get(TrainingCourseVersion, course["version"]["id"])
    assert version is not None
    version.status = "published"
    await db.commit()

    async def fake_structure_completion(messages, **_kwargs) -> str:
        assert "Write all generated training content in Simplified Chinese." in messages[0]["content"]
        assert "Chapter 1 Safety foundations" in messages[-1]["content"]
        return json.dumps({
            "modules": [{
                "title": "Safety foundations",
                "description": "Core laboratory safety practices.",
                "units": [{
                    "title": "Personal protective equipment",
                    "description": "Select and use required protective equipment.",
                    "evidence_ids": ["E1"],
                }],
            }],
        })

    monkeypatch.setattr(
        "app.services.training_service.llm_service.complete_llm_response",
        fake_structure_completion,
    )
    generated = await client.post(
        f"/api/v1/training/courses/{course['id']}/modules/generate",
        headers=auth_headers,
    )
    assert generated.status_code == 200
    module = generated.json()["version"]["modules"][0]
    assert module["title"] == "Safety foundations"
    assert module["status"] == "draft"
    assert module["revision_number"] == 1
    assert module["units"] == [{
        "id": module["units"][0]["id"],
        "title": "Personal protective equipment",
        "description": "Select and use required protective equipment.",
        "position": 0,
        "status": "draft",
        "pass_score": 80,
        "course_asset_ids": [course_asset_id],
        "knowledge_points": [],
        "lesson": None,
    }]
