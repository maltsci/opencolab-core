from datetime import UTC, datetime

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import settings
from app.core.database import Base
from app.models.access_policy import AccessPolicy
from app.models.message import Message
from app.models.project import Project, ResearcherProject
from app.models.research_asset import ResearchAsset
from app.models.research_object import ResearchObject, ResearchObjectRelation
from app.models.session import Session
from app.models.source import Source
from app.models.trace import SourceExtraction
from app.models.user import Workspace
from app.schemas.extraction import SourceExtractionResponse
from app.schemas.research_object_relation import normalize_relation_metadata
from app.schemas.trace import ResearchTraceResponse
from app.services.extraction_service import (
    build_failed_source_extraction_payload,
    build_source_extraction_payload,
    upsert_source_extraction,
)
from app.services.pdf_service import extract_pdf_document_metadata
from app.services.research_asset_service import materialize_source_asset
from app.worker import main as worker_main


async def _govern_source_for_preview(
    db: AsyncSession,
    *,
    source: Source,
    user_id: str,
) -> None:
    asset = await materialize_source_asset(
        db=db,
        source=source,
        owner_id=user_id,
        origin_project_id=None,
        origin_session_id=None,
        visibility_scope="lab_public",
        link_type="source",
    )
    db.add(
        AccessPolicy(
            research_asset_id=asset.id,
            asset_revision_id=asset.current_revision_id,
            subject_type="user",
            subject_id=user_id,
            capabilities_json=["content:preview"],
            created_by=user_id,
        )
    )


async def _create_session_for_user(db: AsyncSession, researcher_id: str) -> Session:
    workspace_id = await db.scalar(
        select(Workspace.id).where(Workspace.researcher_id == researcher_id)
    )
    session = Session(workspace_id=workspace_id, title="Research Timeline")
    db.add(session)
    await db.flush()
    return session


@pytest.mark.asyncio
async def test_source_thumbnail_returns_pdf_page_count(
    client,
    auth_headers,
    admin_user,
    db: AsyncSession,
    monkeypatch,
    tmp_path,
):
    import fitz

    monkeypatch.setattr(settings, "upload_dir", str(tmp_path))
    relative_path = "preview/two-pages.pdf"
    file_path = tmp_path / relative_path
    file_path.parent.mkdir(parents=True)
    document = fitz.open()
    document.new_page().insert_text((72, 72), "Page one")
    document.new_page().insert_text((72, 72), "Page two")
    document.save(file_path)
    document.close()

    source = Source(
        type="file",
        name="two-pages.pdf",
        owner_id=admin_user.id,
        content_hash="two-pages-preview",
        content_path=relative_path,
    )
    db.add(source)
    await db.flush()
    await _govern_source_for_preview(
        db,
        source=source,
        user_id=admin_user.id,
    )
    await db.commit()

    token_response = await client.get(
        f"/api/v1/sources/{source.id}/preview-token",
        headers=auth_headers,
    )
    assert token_response.status_code == 200

    response = await client.get(
        f"/api/v1/sources/{source.id}/thumbnail",
        params={"token": token_response.json()["token"], "page": 1},
    )

    assert response.status_code == 200
    assert response.headers["content-type"] == "image/png"
    assert response.headers["x-pdf-page-count"] == "2"


def test_source_extraction_response_round_trip():
    payload = {
        "id": "ext-1",
        "source_id": "src-1",
        "status": "ready",
        "document_type": "paper",
        "structured_json": {
            "claims": [{"statement": "A", "evidence": "B", "confidence": 0.8}],
            "methods": ["cnn"],
            "limitations": ["small dataset"],
        },
    }

    result = SourceExtractionResponse.model_validate(payload)

    assert result.source_id == "src-1"
    assert result.structured_json["methods"] == ["cnn"]
    assert result.structured_json["claims"][0]["statement"] == "A"


def test_build_source_extraction_payload_returns_deterministic_thin_structure():
    payload = build_source_extraction_payload(
        source_name="attention-is-all-you-need.pdf",
        text=(
            "Attention Is All You Need\n"
            "We present the Transformer architecture for sequence modeling. "
            "The model uses self-attention to replace recurrence. "
            "Experiments on translation tasks show strong results."
        ),
    )

    assert payload["status"] == "ready"
    assert payload["document_type"] == "paper"
    assert payload["schema_version"] == "v1"
    assert payload["structured_json"]["title"] == "Attention Is All You Need"
    assert payload["structured_json"]["summary"].startswith(
        "We present the Transformer architecture"
    )
    assert payload["structured_json"]["highlights"] == [
        "We present the Transformer architecture for sequence modeling.",
        "The model uses self-attention to replace recurrence.",
        "Experiments on translation tasks show strong results.",
    ]
    assert payload["structured_json"]["claims"] == []
    assert payload["structured_json"]["methods"] == []
    assert payload["structured_json"]["limitations"] == []
    assert payload["structured_json"]["datasets"] == []
    assert payload["rendered_markdown"].startswith("Attention Is All You Need")


async def test_source_text_prefers_preserved_parser_markdown(
    client,
    auth_headers,
    admin_user,
    db: AsyncSession,
):
    source = Source(
        type="file",
        name="structured-paper.pdf",
        owner_id=admin_user.id,
        content_hash="structured-preview-markdown",
    )
    source.extraction = SourceExtraction(
        status="ready",
        document_type="paper",
        structured_json={},
        rendered_markdown="# Methods\n\n| Model | Score |\n| --- | --- |\n| Baseline | 92 |",
    )
    db.add(source)
    await db.flush()
    await _govern_source_for_preview(db, source=source, user_id=admin_user.id)
    await db.commit()

    token_response = await client.get(
        f"/api/v1/sources/{source.id}/preview-token",
        headers=auth_headers,
    )
    assert token_response.status_code == 200

    response = await client.get(
        f"/api/v1/sources/{source.id}/text",
        params={"token": token_response.json()["token"]},
    )

    assert response.status_code == 200
    assert response.text == source.extraction.rendered_markdown


def test_build_source_extraction_payload_prefers_embedded_pdf_title():
    payload = build_source_extraction_payload(
        source_name="opaque-upload-name.pdf",
        text="Fallback first line\nDOI: 10.1000/example",
        document_metadata={"title": "Accurate Embedded Paper Title"},
    )

    bibliographic = payload["structured_json"]["bibliographic"]
    assert payload["structured_json"]["title"] == "Accurate Embedded Paper Title"
    assert bibliographic["local_title_candidate"] == {
        "value": "Accurate Embedded Paper Title",
        "source": "pdf_metadata",
        "confidence": "high",
    }


def test_build_source_extraction_payload_accepts_markdown_heading_as_title():
    payload = build_source_extraction_payload(
        source_name="opaque-upload-name.pdf",
        text="# Accurate Parsed Paper Title\nAlice Example\nAbstract text.",
    )

    bibliographic = payload["structured_json"]["bibliographic"]
    assert payload["structured_json"]["title"] == "Accurate Parsed Paper Title"
    assert bibliographic["local_title_candidate"] == {
        "value": "Accurate Parsed Paper Title",
        "source": "parsed_heading",
        "confidence": "high",
    }


def test_build_source_extraction_payload_extracts_topics_from_title_and_abstract():
    payload = build_source_extraction_payload(
        source_name="paper.pdf",
        text=(
            "# Neutrophil antimicrobial peptides inhibit Mycoplasma pneumoniae\n"
            "Abstract\n"
            "Mycoplasma pneumoniae infection activates neutrophil responses. "
            "Antimicrobial peptides reduce Mycoplasma pneumoniae growth.\n"
            "Introduction\n"
            "Additional background text."
        ),
    )

    keywords = payload["structured_json"]["bibliographic"]["keywords"]
    assert "mycoplasma pneumoniae" in keywords
    assert "antimicrobial peptides" in keywords


def test_topic_keywords_prefer_academic_phrases_and_ignore_markup_noise():
    payload = build_source_extraction_payload(
        source_name="rank-restoration.pdf",
        text=(
            "# From Rank Estimation to Rank Approximation: "
            "Rank Residual Constraint for Image Restoration\n"
            "<div align=\"center\" style=\"width:100%\">\n"
            "Abstract\n"
            "Low rank matrix approximation is widely used for image restoration. "
            "The proposed RRC model applies a rank residual constraint and "
            "nonconvex minimization to image denoising.\n"
            "</div>\n"
            "Introduction\n"
            "Additional background text."
        ),
    )

    keywords = payload["structured_json"]["bibliographic"]["keywords"]

    assert "rank residual constraint" in keywords
    assert "image restoration" not in keywords
    assert "low rank matrix approximation" not in keywords
    assert "nonconvex minimization" not in keywords
    assert not {
        "image",
        "rank",
        "matrix",
        "rrc model",
        "div",
        "align center",
        "div style",
    }.intersection(keywords)


def test_topic_keywords_prefer_embedded_author_keywords():
    payload = build_source_extraction_payload(
        source_name="rank-restoration.pdf",
        text=(
            "# Rank Residual Constraint for Image Restoration\n"
            "Abstract\n"
            "This paper studies low rank matrix approximation."
        ),
        document_metadata={
            "title": "Rank Residual Constraint for Image Restoration",
            "keywords": (
                "image restoration; low-rank matrix approximation; "
                "rank residual constraint"
            ),
        },
    )

    assert payload["structured_json"]["bibliographic"]["keywords"] == [
        "rank residual constraint",
    ]


def test_topic_keywords_read_wrapped_index_terms_without_abstract_fragments():
    payload = build_source_extraction_payload(
        source_name="rank-restoration.pdf",
        text=(
            "From Rank Estimation to Rank Approximation:\n"
            "Rank Residual Constraint for Image Restoration\n"
            "Abstract—In this paper, we propose a novel approach for the rank "
            "minimization problem, termed rank residual constraint (RRC).\n"
            "Index Terms—Low-rank, rank residual constraint, nuclear\n"
            "norm minimization, nonlocal self-similarity, group-based sparse\n"
            "representation, image restoration.\n"
            "I. INTRODUCTION\n"
            "Low-rank matrix estimation has attracted increasing attention."
        ),
        document_metadata={
            "title": (
                "From Rank Estimation to Rank Approximation: "
                "Rank Residual Constraint for Image Restoration"
            )
        },
    )

    assert payload["structured_json"]["bibliographic"]["keywords"] == [
        "rank residual constraint",
    ]


def test_topic_keywords_replace_broad_index_terms_with_specific_title_phrases():
    payload = build_source_extraction_payload(
        source_name="joint-patch-group.pdf",
        text=(
            "# Image Restoration Using Joint Patch-Group Based Sparse Representation\n"
            "Abstract—We propose a joint patch-group based\n"
            "sparse representation method for image inpainting and image deblocking.\n"
            "Index Terms—Sparse representation, JPG-SR, nonlocal self-similarity, "
            "image restoration, ADMM.\n"
            "I. INTRODUCTION\n"
            "Additional background text."
        ),
    )

    assert payload["structured_json"]["bibliographic"]["keywords"] == [
        "joint patch group based sparse representation",
    ]


def test_topic_keywords_stay_empty_without_title_supported_phrases():
    payload = build_source_extraction_payload(
        source_name="opaque.pdf",
        text=(
            "# A Focused Study of Retinal Imaging\n"
            "Abstract—This report evaluates a clinical workflow.\n"
            "Index Terms—ADMM, sparse representation, image restoration.\n"
            "I. INTRODUCTION\n"
            "Additional background text."
        ),
    )

    assert payload["structured_json"]["bibliographic"]["keywords"] == []


def test_extract_pdf_document_metadata_reads_title_without_page_content(tmp_path):
    import fitz

    path = tmp_path / "paper.pdf"
    document = fitz.open()
    document.new_page().insert_text((72, 72), "Private page content")
    document.set_metadata(
        {
            "title": "Embedded Paper Title",
            "author": "Alice Example",
            "subject": "DOI: 10.1000/example",
        }
    )
    document.save(path)
    document.close()

    assert extract_pdf_document_metadata(str(path)) == {
        "title": "Embedded Paper Title",
        "author": "Alice Example",
        "subject": "DOI: 10.1000/example",
    }


def test_source_extraction_separates_front_matter_and_reference_identifiers():
    payload = build_source_extraction_payload(
        source_name="attention-is-all-you-need.pdf",
        text=(
            "Attention Is All You Need\n"
            "Ashish Vaswani et al.\n"
            "doi: 10.5555/3295222.3295349\n"
            "PMID: 12345678\n"
            "We present the Transformer architecture.\n"
            "References\n"
            "Related work. https://doi.org/10.1000/reference-only\n"
        ),
    )

    bibliographic = payload["structured_json"]["bibliographic"]
    assert bibliographic["local_title_candidate"] == {
        "value": "Attention Is All You Need",
        "source": "parsed_text",
        "confidence": "medium",
    }
    assert {
        "identifier_type": "doi",
        "value": "10.5555/3295222.3295349",
        "source": "front_matter",
        "confidence": "high",
        "eligible_for_lookup": True,
    } in bibliographic["identifier_candidates"]
    assert {
        "identifier_type": "pmid",
        "value": "12345678",
        "source": "front_matter",
        "confidence": "high",
        "eligible_for_lookup": True,
    } in bibliographic["identifier_candidates"]
    assert {
        "identifier_type": "doi",
        "value": "10.1000/reference-only",
        "source": "references",
        "confidence": "low",
        "eligible_for_lookup": False,
    } in bibliographic["identifier_candidates"]
    assert bibliographic["resolution"] == {
        "status": "pending",
        "reason_codes": [],
    }


def test_source_extraction_only_marks_pre_abstract_arxiv_id_as_primary():
    payload = build_source_extraction_payload(
        source_name="rank-restoration.pdf",
        text=(
            "Rank Residual Constraint for Image Restoration\n"
            "arXiv: 1803.06795v1\n"
            "Abstract\n"
            "We compare arXiv: 1703.09912 and arXiv: 1009.5055.\n"
            "References\n"
            "arXiv: 1709.01841\n"
            "arXiv: 1508.03498\n"
        ),
    )

    candidates = payload["structured_json"]["bibliographic"][
        "identifier_candidates"
    ]
    eligible_values = [
        candidate["value"]
        for candidate in candidates
        if candidate["eligible_for_lookup"]
    ]

    assert eligible_values == ["1803.06795v1"]
    assert {
        candidate["value"]
        for candidate in candidates
        if candidate["source"] == "body"
    } == {"1703.09912", "1009.5055"}
    assert {
        candidate["value"]
        for candidate in candidates
        if candidate["source"] == "references"
    } == {"1709.01841", "1508.03498"}


def test_build_failed_source_extraction_payload_returns_terminal_failure():
    payload = build_failed_source_extraction_payload(
        source_name="failed-paper.pdf",
        error_message="builder blew up",
    )

    assert payload["status"] == "failed"
    assert payload["document_type"] == "paper"
    assert payload["schema_version"] == "v1"
    assert payload["error_message"] == "builder blew up"
    assert payload["structured_json"]["title"] == "failed paper"
    assert payload["structured_json"]["summary"] == ""
    assert payload["structured_json"]["highlights"] == []
    assert payload["structured_json"]["claims"] == []
    assert payload["structured_json"]["methods"] == []
    assert payload["structured_json"]["limitations"] == []
    assert payload["structured_json"]["datasets"] == []


def test_research_trace_response_maps_json_fields():
    payload = {
        "id": "trace-1",
        "session_id": "session-1",
        "message_id": "message-1",
        "inputs_json": {"question": "What changed?"},
        "retrieval_json": [{"source_id": "src-1"}],
        "citations_json": [{"source_id": "src-1", "quote": "A"}],
        "summary_steps_json": ["collect", "compare"],
        "created_at": datetime(2026, 6, 26, tzinfo=UTC),
    }

    result = ResearchTraceResponse.model_validate(payload)

    assert result.inputs == {"question": "What changed?"}
    assert result.retrieval == [{"source_id": "src-1"}]
    assert result.citations[0]["quote"] == "A"
    assert result.summary_steps == ["collect", "compare"]


@pytest.mark.asyncio
async def test_model_tables_are_registered_and_created(db: AsyncSession):
    result = await db.execute(text("SELECT name FROM sqlite_master WHERE type='table'"))
    table_names = {name for (name,) in result.all()}

    expected_tables = {
        "source_extractions",
        "research_traces",
        "research_objects",
        "research_object_relations",
    }

    assert expected_tables.issubset(Base.metadata.tables.keys())
    assert expected_tables.issubset(table_names)


@pytest.mark.asyncio
async def test_research_object_relation_wires_bidirectional_relationships(
    db: AsyncSession,
):
    source_object = ResearchObject(type="hypothesis", title="H1")
    target_object = ResearchObject(type="finding", title="F1")
    relation = ResearchObjectRelation(
        source_object=source_object,
        target_object=target_object,
        relation_type="supports",
    )

    db.add_all([source_object, target_object, relation])
    await db.commit()

    source_result = await db.execute(
        select(ResearchObject)
        .options(selectinload(ResearchObject.outgoing_relations))
        .where(ResearchObject.id == source_object.id)
    )
    loaded_source = source_result.scalar_one()

    target_result = await db.execute(
        select(ResearchObject)
        .options(selectinload(ResearchObject.incoming_relations))
        .where(ResearchObject.id == target_object.id)
    )
    loaded_target = target_result.scalar_one()

    assert len(loaded_source.outgoing_relations) == 1
    assert loaded_source.outgoing_relations[0].target_object_id == target_object.id
    assert len(loaded_target.incoming_relations) == 1
    assert loaded_target.incoming_relations[0].source_object_id == source_object.id


@pytest.mark.asyncio
async def test_research_object_relation_enforces_unique_constraint(db: AsyncSession):
    source_object = ResearchObject(type="hypothesis", title="H1")
    target_object = ResearchObject(type="finding", title="F1")
    db.add_all([source_object, target_object])
    await db.flush()

    db.add(
        ResearchObjectRelation(
            source_object_id=source_object.id,
            target_object_id=target_object.id,
            relation_type="supports",
        )
    )
    await db.flush()

    db.add(
        ResearchObjectRelation(
            source_object_id=source_object.id,
            target_object_id=target_object.id,
            relation_type="supports",
        )
    )

    with pytest.raises(IntegrityError):
        await db.flush()


@pytest.mark.asyncio
async def test_research_object_delete_cascades_relations(db: AsyncSession):
    source_object = ResearchObject(type="hypothesis", title="H1")
    target_object = ResearchObject(type="finding", title="F1")
    relation = ResearchObjectRelation(
        source_object=source_object,
        target_object=target_object,
        relation_type="supports",
    )

    db.add_all([source_object, target_object, relation])
    await db.commit()

    relation_count = await db.scalar(
        text("SELECT COUNT(*) FROM research_object_relations")
    )
    assert relation_count == 1

    await db.delete(source_object)
    await db.commit()

    remaining_relation_count = await db.scalar(
        text("SELECT COUNT(*) FROM research_object_relations")
    )
    remaining_object_count = await db.scalar(
        text("SELECT COUNT(*) FROM research_objects")
    )

    assert remaining_relation_count == 0
    assert remaining_object_count == 1


@pytest.mark.asyncio
async def test_create_research_object_from_session_message(
    client: AsyncClient,
    researcher_headers: dict,
    researcher_user,
    db: AsyncSession,
):
    workspace_id = await db.scalar(
        select(Workspace.id).where(Workspace.researcher_id == researcher_user.id)
    )
    session = Session(workspace_id=workspace_id, title="Research Timeline")
    db.add(session)
    await db.flush()

    assistant_message = Message(
        session_id=session.id,
        role="assistant",
        content="A working hypothesis from the answer",
    )
    db.add(assistant_message)
    await db.commit()

    response = await client.post(
        "/api/v1/research-objects",
        headers=researcher_headers,
        json={
            "session_id": session.id,
            "message_id": assistant_message.id,
            "type": "hypothesis",
            "title": "Draft hypothesis",
            "content": "A working hypothesis from the answer",
            "content_json": {
                "origin": "assistant_message",
                "source_ids": ["source-1"],
            },
        },
    )

    assert response.status_code == 201
    payload = response.json()
    assert payload["type"] == "hypothesis"
    assert payload["session_id"] == session.id
    assert payload["message_id"] == assistant_message.id
    assert payload["content_json"]["origin"] == "assistant_message"
    assert payload["content_json"]["source_ids"] == ["source-1"]
    assert payload["content_json"]["project_id"] is None
    assert payload["content_json"]["source_session_id"] == session.id


@pytest.mark.asyncio
async def test_project_research_objects_survive_session_deletion(
    client: AsyncClient,
    researcher_headers: dict,
    researcher_user,
    db: AsyncSession,
):
    workspace_id = await db.scalar(
        select(Workspace.id).where(Workspace.researcher_id == researcher_user.id)
    )
    project = Project(name="Long Memory Project")
    db.add(project)
    await db.flush()
    db.add(
        ResearcherProject(
            researcher_id=researcher_user.id,
            project_id=project.id,
            role="owner",
        )
    )
    session = Session(
        workspace_id=workspace_id,
        project_id=project.id,
        title="Disposable Session",
    )
    db.add(session)
    await db.flush()
    assistant_message = Message(
        session_id=session.id,
        role="assistant",
        content="A saved project-level finding",
    )
    db.add(assistant_message)
    await db.commit()

    create_response = await client.post(
        "/api/v1/research-objects",
        headers=researcher_headers,
        json={
            "session_id": session.id,
            "message_id": assistant_message.id,
            "type": "discussion",
            "title": "Project finding",
            "content": "A saved project-level finding",
            "content_json": {"origin": "assistant_message"},
        },
    )
    assert create_response.status_code == 201
    research_object_id = create_response.json()["id"]

    delete_response = await client.delete(
        f"/api/v1/sessions/{session.id}",
        headers=researcher_headers,
    )
    assert delete_response.status_code == 204

    project_memory_response = await client.get(
        f"/api/v1/research-objects/projects/{project.id}",
        headers=researcher_headers,
    )

    assert project_memory_response.status_code == 200
    payload = project_memory_response.json()
    assert [item["id"] for item in payload] == [research_object_id]
    assert payload[0]["session_id"] == session.id
    assert payload[0]["content_json"]["project_id"] == project.id
    assert payload[0]["content_json"]["source_session_deleted"] is True


@pytest.mark.asyncio
async def test_list_session_research_objects_returns_newest_first(
    client: AsyncClient,
    researcher_headers: dict,
    researcher_user,
    db: AsyncSession,
):
    workspace_id = await db.scalar(
        select(Workspace.id).where(Workspace.researcher_id == researcher_user.id)
    )
    session = Session(workspace_id=workspace_id, title="Research Timeline")
    db.add(session)
    await db.flush()

    older_message = Message(
        session_id=session.id,
        role="assistant",
        content="Older answer",
    )
    newer_message = Message(
        session_id=session.id,
        role="assistant",
        content="Newer answer",
    )
    db.add_all([older_message, newer_message])
    await db.flush()

    older_object = ResearchObject(
        type="discussion",
        title="Older discussion",
        content="Older discussion body",
        content_json={
            "session_id": session.id,
            "source_message_id": older_message.id,
            "origin": "assistant_message",
        },
        created_by=researcher_user.id,
        created_at=datetime(2026, 7, 8, 10, 0, 0, tzinfo=UTC),
    )
    newer_object = ResearchObject(
        type="hypothesis",
        title="Newer hypothesis",
        content="Newer hypothesis body",
        content_json={
            "session_id": session.id,
            "source_message_id": newer_message.id,
            "origin": "assistant_message",
        },
        created_by=researcher_user.id,
        created_at=datetime(2026, 7, 8, 10, 0, 1, tzinfo=UTC),
    )
    db.add_all([older_object, newer_object])
    await db.commit()

    response = await client.get(
        f"/api/v1/sessions/{session.id}/research-objects",
        headers=researcher_headers,
    )

    assert response.status_code == 200
    payload = response.json()
    assert [item["id"] for item in payload] == [newer_object.id, older_object.id]
    assert payload[0]["message_id"] == newer_message.id
    assert payload[1]["message_id"] == older_message.id


@pytest.mark.asyncio
async def test_update_research_object_updates_title_and_content(
    client: AsyncClient,
    researcher_headers: dict,
    researcher_user,
    db: AsyncSession,
):
    research_object = ResearchObject(
        type="hypothesis",
        title="Old hypothesis",
        content="Old content",
        content_json={"session_id": "session-1", "origin": "assistant_message"},
        created_by=researcher_user.id,
    )
    db.add(research_object)
    await db.commit()

    response = await client.put(
        f"/api/v1/research-objects/{research_object.id}",
        headers=researcher_headers,
        json={
            "title": "Updated hypothesis",
            "content": "Updated content",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["title"] == "Updated hypothesis"
    assert payload["content"] == "Updated content"


@pytest.mark.asyncio
async def test_delete_research_object_removes_item(
    client: AsyncClient,
    researcher_headers: dict,
    researcher_user,
    db: AsyncSession,
):
    research_object = ResearchObject(
        type="discussion",
        title="To delete",
        content="Delete me",
        content_json={"session_id": "session-1", "origin": "assistant_message"},
        created_by=researcher_user.id,
    )
    db.add(research_object)
    await db.commit()

    response = await client.delete(
        f"/api/v1/research-objects/{research_object.id}",
        headers=researcher_headers,
    )

    assert response.status_code == 204

    result = await db.execute(
        select(ResearchObject).where(ResearchObject.id == research_object.id)
    )
    assert result.scalar_one_or_none() is None


def test_research_object_relation_persists_metadata_shape():
    relation = ResearchObjectRelation(
        relation_type="supports",
        metadata_json={
            "confidence": 0.8,
            "evidence": {
                "citations": [],
                "note": "matches cited claim",
            },
        },
        created_by="user-1",
        created_by_type="human",
    )

    assert relation.metadata_json["confidence"] == 0.8
    assert relation.metadata_json["evidence"]["note"] == "matches cited claim"
    assert relation.created_by == "user-1"
    assert relation.created_by_type == "human"


@pytest.mark.asyncio
async def test_list_research_object_relations_returns_outgoing_relations(
    client: AsyncClient,
    researcher_headers: dict,
    researcher_user,
    db: AsyncSession,
):
    session = await _create_session_for_user(db, researcher_user.id)
    source_object = ResearchObject(
        type="hypothesis",
        title="Source",
        content_json={"session_id": session.id},
        created_by=researcher_user.id,
    )
    target_object = ResearchObject(
        type="discussion",
        title="Target",
        content_json={"session_id": session.id},
        created_by=researcher_user.id,
    )
    relation = ResearchObjectRelation(
        source_object=source_object,
        target_object=target_object,
        relation_type="supports",
        metadata_json={"confidence": 0.8},
        created_by=researcher_user.id,
        created_by_type="human",
    )
    db.add_all([source_object, target_object, relation])
    await db.commit()

    response = await client.get(
        f"/api/v1/research-objects/{source_object.id}/relations",
        headers=researcher_headers,
    )

    assert response.status_code == 200
    payload = response.json()
    assert len(payload) == 1
    assert payload[0]["relation_type"] == "supports"
    assert payload[0]["target_object"]["id"] == target_object.id
    assert payload[0]["metadata_json"]["confidence"] == 0.8


@pytest.mark.asyncio
async def test_list_research_object_relations_migrates_legacy_reason_into_evidence_note(
    client: AsyncClient,
    researcher_headers: dict,
    researcher_user,
    db: AsyncSession,
):
    session = await _create_session_for_user(db, researcher_user.id)
    source_object = ResearchObject(
        type="hypothesis",
        title="Source",
        content_json={"session_id": session.id},
        created_by=researcher_user.id,
    )
    target_object = ResearchObject(
        type="discussion",
        title="Target",
        content_json={"session_id": session.id},
        created_by=researcher_user.id,
    )
    relation = ResearchObjectRelation(
        source_object=source_object,
        target_object=target_object,
        relation_type="supports",
        metadata_json={"confidence": 0.8, "reason": "Legacy rationale"},
        created_by=researcher_user.id,
        created_by_type="human",
    )
    db.add_all([source_object, target_object, relation])
    await db.commit()

    response = await client.get(
        f"/api/v1/research-objects/{source_object.id}/relations",
        headers=researcher_headers,
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload[0]["metadata_json"]["evidence"]["note"] == "Legacy rationale"
    assert payload[0]["metadata_json"]["evidence"]["citations"] == []


@pytest.mark.asyncio
async def test_list_research_object_relations_tolerates_malformed_stored_metadata(
    client: AsyncClient,
    researcher_headers: dict,
    researcher_user,
    db: AsyncSession,
):
    session = await _create_session_for_user(db, researcher_user.id)
    source_object = ResearchObject(
        type="hypothesis",
        title="Source",
        content_json={"session_id": session.id},
        created_by=researcher_user.id,
    )
    target_object = ResearchObject(
        type="discussion",
        title="Target",
        content_json={"session_id": session.id},
        created_by=researcher_user.id,
    )
    relation = ResearchObjectRelation(
        source_object=source_object,
        target_object=target_object,
        relation_type="supports",
        metadata_json={
            "confidence": "not-a-number",
            "evidence": {
                "trace_id": 123,
                "citations": "not-a-list",
                "note": {"bad": "shape"},
            },
        },
        created_by=researcher_user.id,
        created_by_type="human",
    )
    db.add_all([source_object, target_object, relation])
    await db.commit()

    response = await client.get(
        f"/api/v1/research-objects/{source_object.id}/relations",
        headers=researcher_headers,
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload[0]["metadata_json"] == {
        "confidence": 0.0,
        "evidence": {
            "trace_id": None,
            "citations": [],
            "note": None,
        },
    }


@pytest.mark.asyncio
async def test_research_object_relation_direction_is_outgoing_only(
    client: AsyncClient,
    researcher_headers: dict,
    researcher_user,
    db: AsyncSession,
):
    session = await _create_session_for_user(db, researcher_user.id)
    source_object = ResearchObject(
        type="hypothesis",
        title="Source",
        content_json={"session_id": session.id},
        created_by=researcher_user.id,
    )
    target_object = ResearchObject(
        type="discussion",
        title="Target",
        content_json={"session_id": session.id},
        created_by=researcher_user.id,
    )
    relation = ResearchObjectRelation(
        source_object=source_object,
        target_object=target_object,
        relation_type="supports",
        metadata_json={"confidence": 0.8},
        created_by=researcher_user.id,
        created_by_type="human",
    )
    db.add_all([source_object, target_object, relation])
    await db.commit()

    response = await client.get(
        f"/api/v1/research-objects/{target_object.id}/relations",
        headers=researcher_headers,
    )

    assert response.status_code == 200
    assert response.json() == []


@pytest.mark.asyncio
async def test_create_research_object_relation_persists_metadata_and_creator(
    client: AsyncClient,
    researcher_headers: dict,
    researcher_user,
    db: AsyncSession,
):
    session = await _create_session_for_user(db, researcher_user.id)
    source_object = ResearchObject(
        type="hypothesis",
        title="Source",
        content_json={"session_id": session.id},
        created_by=researcher_user.id,
    )
    target_object = ResearchObject(
        type="discussion",
        title="Target",
        content_json={"session_id": session.id},
        created_by=researcher_user.id,
    )
    db.add_all([source_object, target_object])
    await db.commit()

    response = await client.post(
        f"/api/v1/research-objects/{source_object.id}/relations",
        headers=researcher_headers,
        json={
            "relation_type": "supports",
            "target_object_id": target_object.id,
            "metadata_json": {
                "confidence": 0.8,
                "evidence": {
                    "citations": [],
                    "note": "matches cited claim",
                },
            },
        },
    )

    assert response.status_code == 201
    payload = response.json()
    assert payload["target_object"]["id"] == target_object.id
    assert payload["metadata_json"]["confidence"] == 0.8
    assert payload["metadata_json"]["evidence"]["citations"] == []
    assert payload["metadata_json"]["evidence"]["note"] == "matches cited claim"
    assert payload["created_by"] == researcher_user.id
    assert payload["created_by_type"] == "human"


@pytest.mark.asyncio
async def test_create_research_object_relation_persists_nested_evidence_payload(
    client: AsyncClient,
    researcher_headers: dict,
    researcher_user,
    db: AsyncSession,
):
    session = await _create_session_for_user(db, researcher_user.id)
    source_object = ResearchObject(
        type="hypothesis",
        title="Source",
        content_json={"session_id": session.id},
        created_by=researcher_user.id,
    )
    target_object = ResearchObject(
        type="discussion",
        title="Target",
        content_json={"session_id": session.id},
        created_by=researcher_user.id,
    )
    db.add_all([source_object, target_object])
    await db.commit()

    response = await client.post(
        f"/api/v1/research-objects/{source_object.id}/relations",
        headers=researcher_headers,
        json={
            "relation_type": "supports",
            "target_object_id": target_object.id,
            "metadata_json": {
                "confidence": 0.8,
                "evidence": {
                    "trace_id": "trace-123",
                    "citations": [
                        {
                            "source_id": "source-1",
                            "snippet": "quoted support",
                        }
                    ],
                    "note": "User confirmed the rationale",
                },
            },
        },
    )

    assert response.status_code == 201
    payload = response.json()
    assert payload["metadata_json"]["confidence"] == 0.8
    assert payload["metadata_json"]["evidence"]["trace_id"] == "trace-123"
    assert payload["metadata_json"]["evidence"]["citations"] == [
        {
            "source_id": "source-1",
            "chunk_id": None,
            "snippet": "quoted support",
            "score": None,
        }
    ]
    assert (
        payload["metadata_json"]["evidence"]["note"] == "User confirmed the rationale"
    )


def test_normalize_relation_metadata_defaults_missing_and_malformed_evidence():
    normalized = normalize_relation_metadata(
        {
            "confidence": "0.7",
            "evidence": "invalid",
        }
    )

    assert normalized == {
        "confidence": 0.7,
        "evidence": {
            "trace_id": None,
            "citations": [],
            "note": None,
        },
    }


@pytest.mark.asyncio
async def test_create_research_object_relation_rejects_self_relation(
    client: AsyncClient,
    researcher_headers: dict,
    researcher_user,
    db: AsyncSession,
):
    session = await _create_session_for_user(db, researcher_user.id)
    source_object = ResearchObject(
        type="hypothesis",
        title="Source",
        content_json={"session_id": session.id},
        created_by=researcher_user.id,
    )
    db.add(source_object)
    await db.commit()

    response = await client.post(
        f"/api/v1/research-objects/{source_object.id}/relations",
        headers=researcher_headers,
        json={
            "relation_type": "supports",
            "target_object_id": source_object.id,
            "metadata_json": {"confidence": 0.8},
        },
    )

    assert response.status_code == 400


@pytest.mark.asyncio
async def test_create_research_object_relation_rejects_duplicate(
    client: AsyncClient,
    researcher_headers: dict,
    researcher_user,
    db: AsyncSession,
):
    session = await _create_session_for_user(db, researcher_user.id)
    source_object = ResearchObject(
        type="hypothesis",
        title="Source",
        content_json={"session_id": session.id},
        created_by=researcher_user.id,
    )
    target_object = ResearchObject(
        type="discussion",
        title="Target",
        content_json={"session_id": session.id},
        created_by=researcher_user.id,
    )
    relation = ResearchObjectRelation(
        source_object=source_object,
        target_object=target_object,
        relation_type="supports",
        metadata_json={"confidence": 0.8},
        created_by=researcher_user.id,
        created_by_type="human",
    )
    db.add_all([source_object, target_object, relation])
    await db.commit()

    response = await client.post(
        f"/api/v1/research-objects/{source_object.id}/relations",
        headers=researcher_headers,
        json={
            "relation_type": "supports",
            "target_object_id": target_object.id,
            "metadata_json": {"confidence": 0.8},
        },
    )

    assert response.status_code == 409


@pytest.mark.asyncio
async def test_create_research_object_relation_returns_409_on_insert_race(
    client: AsyncClient,
    researcher_headers: dict,
    researcher_user,
    db: AsyncSession,
    monkeypatch,
):
    session = await _create_session_for_user(db, researcher_user.id)
    source_object = ResearchObject(
        type="hypothesis",
        title="Source",
        content_json={"session_id": session.id},
        created_by=researcher_user.id,
    )
    target_object = ResearchObject(
        type="discussion",
        title="Target",
        content_json={"session_id": session.id},
        created_by=researcher_user.id,
    )
    db.add_all([source_object, target_object])
    await db.commit()

    original_commit = AsyncSession.commit

    async def fake_commit(self):
        if any(isinstance(item, ResearchObjectRelation) for item in self.new):
            raise IntegrityError("INSERT", {}, Exception("uq_research_object_relation"))
        await original_commit(self)

    monkeypatch.setattr(AsyncSession, "commit", fake_commit)

    response = await client.post(
        f"/api/v1/research-objects/{source_object.id}/relations",
        headers=researcher_headers,
        json={
            "relation_type": "supports",
            "target_object_id": target_object.id,
            "metadata_json": {"confidence": 0.8},
        },
    )

    assert response.status_code == 409
    assert response.json()["detail"] == "Research relation already exists"


@pytest.mark.asyncio
async def test_delete_research_object_relation_returns_403_for_non_owner(
    client: AsyncClient,
    researcher_headers: dict,
    researcher_user,
    admin_user,
    db: AsyncSession,
):
    session = await _create_session_for_user(db, admin_user.id)
    source_object = ResearchObject(
        type="hypothesis",
        title="Source",
        content_json={"session_id": session.id},
        created_by=admin_user.id,
    )
    target_object = ResearchObject(
        type="discussion",
        title="Target",
        content_json={"session_id": session.id},
        created_by=admin_user.id,
    )
    relation = ResearchObjectRelation(
        source_object=source_object,
        target_object=target_object,
        relation_type="supports",
        metadata_json={"confidence": 0.8},
        created_by=admin_user.id,
        created_by_type="human",
    )
    db.add_all([source_object, target_object, relation])
    await db.commit()

    response = await client.delete(
        f"/api/v1/research-object-relations/{relation.id}",
        headers=researcher_headers,
    )

    assert response.status_code == 403


@pytest.mark.asyncio
async def test_delete_research_object_relation_returns_404_for_missing_relation(
    client: AsyncClient,
    researcher_headers: dict,
):
    response = await client.delete(
        "/api/v1/research-object-relations/missing-relation",
        headers=researcher_headers,
    )

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_source_extraction_relationship_persists_round_trip(db: AsyncSession):
    source = Source(type="file", name="paper.pdf")
    source.extraction = SourceExtraction(
        status="ready",
        document_type="paper",
        structured_json={"methods": ["cnn"]},
    )

    db.add(source)
    await db.commit()
    result = await db.execute(
        select(Source)
        .options(selectinload(Source.extraction))
        .where(Source.id == source.id)
    )
    reloaded = result.scalar_one()

    assert reloaded is not None
    assert reloaded.extraction is not None
    assert reloaded.extraction.source_id == source.id
    assert reloaded.extraction.structured_json["methods"] == ["cnn"]


@pytest.mark.asyncio
async def test_upsert_source_extraction_persists_terminal_failed_state(
    db: AsyncSession,
):
    source = Source(type="file", name="paper.pdf")
    db.add(source)
    await db.flush()

    payload = build_failed_source_extraction_payload(
        source_name=source.name,
        error_message="parse timeout",
    )
    await upsert_source_extraction(db, source.id, payload)
    await db.commit()

    result = await db.execute(
        select(SourceExtraction).where(SourceExtraction.source_id == source.id)
    )
    extraction = result.scalar_one()

    assert extraction.status == "failed"
    assert extraction.error_message == "parse timeout"
    assert extraction.schema_version == "v1"


@pytest.mark.asyncio
async def test_upsert_source_extraction_queues_bibliographic_lookup(
    db: AsyncSession,
):
    source = Source(type="file", name="paper.pdf")
    db.add(source)
    await db.flush()

    payload = build_source_extraction_payload(
        source_name=source.name,
        text="Paper Title\ndoi: 10.5555/12345678\nAbstract text.",
    )
    await upsert_source_extraction(db, source.id, payload)
    await db.commit()

    extraction = await db.scalar(
        select(SourceExtraction).where(SourceExtraction.source_id == source.id)
    )

    assert extraction is not None
    assert extraction.metadata_status == "pending"
    assert extraction.metadata_attempts == 0
    assert extraction.metadata_error is None


@pytest.mark.asyncio
async def test_upsert_source_extraction_applies_high_confidence_local_title(
    db: AsyncSession,
):
    source = Source(type="file", name="opaque-upload-name.pdf")
    db.add(source)
    await db.flush()
    asset = ResearchAsset(
        asset_type="uploaded_file",
        title=source.name,
        title_source="filename",
        title_locked=False,
        source_id=source.id,
        catalog_metadata_json={"title": source.name},
        visibility_scope="lab_public",
    )
    db.add(asset)
    await db.flush()

    payload = build_source_extraction_payload(
        source_name=source.name,
        text="Fallback first line",
        document_metadata={"title": "Accurate Embedded Paper Title"},
    )
    await upsert_source_extraction(db, source.id, payload)
    await db.commit()

    reloaded_asset = await db.get(ResearchAsset, asset.id)
    assert reloaded_asset is not None
    assert reloaded_asset.title == "Accurate Embedded Paper Title"
    assert reloaded_asset.title_source == "pdf_metadata"
    assert reloaded_asset.title_locked is False
    assert reloaded_asset.catalog_metadata_json["title"] == (
        "Accurate Embedded Paper Title"
    )


@pytest.mark.asyncio
async def test_upsert_source_extraction_persists_topic_keywords_on_asset(
    db: AsyncSession,
):
    source = Source(type="file", name="paper.pdf")
    db.add(source)
    await db.flush()
    asset = ResearchAsset(
        asset_type="uploaded_file",
        title=source.name,
        source_id=source.id,
        catalog_metadata_json={"title": source.name},
        visibility_scope="lab_public",
    )
    db.add(asset)
    await db.flush()

    payload = build_source_extraction_payload(
        source_name=source.name,
        text=(
            "# Antimicrobial peptides against Mycoplasma pneumoniae\n"
            "Abstract\n"
            "Antimicrobial peptides inhibit Mycoplasma pneumoniae growth."
        ),
    )
    await upsert_source_extraction(db, source.id, payload)
    await db.commit()

    reloaded_asset = await db.get(ResearchAsset, asset.id)
    assert reloaded_asset is not None
    assert (
        "antimicrobial peptides"
        in (reloaded_asset.catalog_metadata_json["bibliographic"]["keywords"])
    )


@pytest.mark.asyncio
async def test_disabled_bibliographic_lookup_marks_pending_jobs_offline(
    db: AsyncSession,
):
    source = Source(type="file", name="paper.pdf")
    db.add(source)
    await db.flush()
    extraction = SourceExtraction(
        source_id=source.id,
        status="ready",
        document_type="paper",
        schema_version="v1",
        structured_json={},
        metadata_status="pending",
    )
    db.add(extraction)
    await db.commit()

    job = await worker_main.claim_bibliographic_job(db)
    await db.commit()

    assert job is None
    await db.refresh(extraction)
    assert extraction.metadata_status == "offline"


@pytest.mark.asyncio
async def test_enabling_bibliographic_lookup_claims_offline_jobs(
    db: AsyncSession,
    monkeypatch,
):
    source = Source(type="file", name="paper.pdf")
    db.add(source)
    await db.flush()
    extraction = SourceExtraction(
        source_id=source.id,
        status="ready",
        document_type="paper",
        schema_version="v1",
        structured_json={},
        metadata_status="offline",
    )
    db.add(extraction)
    await db.commit()

    async def fake_runtime_value(key: str, _db: AsyncSession) -> str | None:
        return {
            "bibliographic_lookup_enabled": "true",
            "bibliographic_lookup_contact_email": "metadata@example.org",
            "bibliographic_auto_apply_enabled": "false",
        }.get(key)

    monkeypatch.setattr(worker_main, "get_runtime_value", fake_runtime_value)

    job = await worker_main.claim_bibliographic_job(db)

    assert job == (source.id, "metadata@example.org", False)
    assert extraction.metadata_status == "resolving"


@pytest.mark.asyncio
async def test_mark_source_failed_still_sets_processing_state_when_extraction_persist_fails(
    monkeypatch,
):
    calls: list[tuple] = []

    async def fake_get_source_name(source_id: str) -> str | None:
        calls.append(("get_source_name", source_id))
        return "paper.pdf"

    async def fake_persist_extraction_payload(source_id: str, payload: dict) -> None:
        calls.append(("persist", source_id, payload["status"]))
        raise RuntimeError("db write failed")

    async def fake_set_state(
        source_id: str,
        state: str,
        progress: int,
        error: str | None = None,
    ) -> None:
        calls.append(("set_state", source_id, state, progress, error))

    monkeypatch.setattr(worker_main, "_get_source_name", fake_get_source_name)
    monkeypatch.setattr(
        worker_main,
        "_persist_extraction_payload",
        fake_persist_extraction_payload,
    )
    monkeypatch.setattr(worker_main, "_set_state", fake_set_state)

    await worker_main._mark_source_failed("src-1", "pipeline crashed")

    assert ("get_source_name", "src-1") in calls
    assert ("persist", "src-1", "failed") in calls
    assert ("set_state", "src-1", "failed", 0, "pipeline crashed") in calls


@pytest.mark.asyncio
async def test_get_source_extraction_endpoint_returns_extraction(
    client,
    auth_headers,
    admin_user,
    db: AsyncSession,
):
    source = Source(type="file", name="paper.pdf", owner_id=admin_user.id)
    source.extraction = SourceExtraction(
        status="ready",
        document_type="paper",
        schema_version="v0",
        structured_json={"title": "Paper", "summary": "Thin payload"},
    )
    db.add(source)
    await db.flush()
    await _govern_source_for_preview(
        db,
        source=source,
        user_id=admin_user.id,
    )
    await db.commit()

    response = await client.get(
        f"/api/v1/sources/{source.id}/extraction",
        headers=auth_headers,
    )

    assert response.status_code == 200
    body = response.json()
    assert body["source_id"] == source.id
    assert body["status"] == "ready"
    assert body["schema_version"] == "v0"
    assert body["structured_json"]["title"] == "Paper"


@pytest.mark.asyncio
async def test_get_source_and_session_sources_include_extraction_status(
    client,
    auth_headers,
    admin_user,
    db: AsyncSession,
):
    source = Source(type="file", name="paper.pdf", owner_id=admin_user.id)
    source.extraction = SourceExtraction(
        status="ready",
        document_type="paper",
        schema_version="v0",
        structured_json={"title": "Paper"},
    )
    db.add(source)
    await db.flush()
    await _govern_source_for_preview(
        db,
        source=source,
        user_id=admin_user.id,
    )
    workspace_id = await db.scalar(
        text("SELECT id FROM workspaces WHERE researcher_id = :researcher_id"),
        {"researcher_id": admin_user.id},
    )

    await db.execute(
        text(
            """
            INSERT INTO sessions (id, workspace_id, title)
            VALUES (:id, :workspace_id, :title)
            """
        ),
        {
            "id": "session-1",
            "workspace_id": workspace_id,
            "title": "Session 1",
        },
    )
    await db.execute(
        text(
            """
            INSERT INTO session_sources (id, session_id, source_id, display_name)
            VALUES (:id, :session_id, :source_id, :display_name)
            """
        ),
        {
            "id": "session-source-1",
            "session_id": "session-1",
            "source_id": source.id,
            "display_name": "Alias",
        },
    )
    await db.commit()

    source_response = await client.get(
        f"/api/v1/sources/{source.id}",
        headers=auth_headers,
    )
    assert source_response.status_code == 200
    assert source_response.json()["extraction_status"] == "ready"

    session_sources_response = await client.get(
        "/api/v1/sessions/session-1/sources",
        headers=auth_headers,
    )
    assert session_sources_response.status_code == 200
    body = session_sources_response.json()
    assert len(body) == 1
    assert body[0]["name"] == "Alias"
    assert body[0]["extraction_status"] == "ready"


@pytest.mark.asyncio
async def test_list_sources_populates_extraction_status_for_multiple_items(
    client,
    auth_headers,
    admin_user,
    db: AsyncSession,
):
    workspace_id = await db.scalar(
        text("SELECT id FROM workspaces WHERE researcher_id = :researcher_id"),
        {"researcher_id": admin_user.id},
    )

    ready_source = Source(type="file", name="ready.pdf", owner_id=admin_user.id)
    failed_source = Source(type="file", name="failed.pdf", owner_id=admin_user.id)
    db.add_all([ready_source, failed_source])
    await db.flush()

    await db.execute(
        text(
            """
            INSERT INTO workspace_sources (id, workspace_id, source_id)
            VALUES (:id1, :workspace_id, :source_id1),
                   (:id2, :workspace_id, :source_id2)
            """
        ),
        {
            "id1": "ws-source-1",
            "id2": "ws-source-2",
            "workspace_id": workspace_id,
            "source_id1": ready_source.id,
            "source_id2": failed_source.id,
        },
    )

    await upsert_source_extraction(
        db,
        ready_source.id,
        build_source_extraction_payload(
            source_name=ready_source.name,
            text="Ready Title\nA concise ready summary.",
        ),
    )
    await upsert_source_extraction(
        db,
        failed_source.id,
        build_failed_source_extraction_payload(
            source_name=failed_source.name,
            error_message="extraction builder failed",
        ),
    )
    await db.commit()

    response = await client.get("/api/v1/sources", headers=auth_headers)

    assert response.status_code == 200
    by_id = {item["id"]: item for item in response.json()}
    assert by_id[ready_source.id]["extraction_status"] == "ready"
    assert by_id[failed_source.id]["extraction_status"] == "failed"
