import pytest

from app.models.research_asset import ResearchAsset
from app.models.source import Chunk, Source
from app.services import rag_service
from app.services.rag_service import (
    _is_overview_query,
    _looks_like_boilerplate_chunk,
    _looks_like_reference_chunk,
    _select_retrieval_candidates,
    retrieve_chunks,
)


def test_reference_chunk_detection_matches_bibliography_text():
    text = (
        "Published online: May 6, 2022 [1] N. Bertozzi, Eur. Rev. Med. "
        "Pharmacol. Sci. 2017, 21, 2572. [2] S. Y. Qin, Biomaterials "
        "2018, 183, 167. [3] M. Zasloff, Nature 2002, 415, 389. "
        "[4] A. P. Blum, J. Am. Chem. Soc. 2014, 136, 15422. "
        "[5] X. An, ACS Appl. Mater. Interfaces 2019, 11, 34663."
    )

    assert _looks_like_reference_chunk(text)


def test_reference_chunk_detection_matches_parsed_bibliography_fragments():
    fragments = [
        (
            "Kain, R. Andrusiak, G. D. Rio, S. Krajewski, C. R. Lombardo, "
            "R. Rao, E. Ruoslahti, D. E. Bredesen, R. Pasqualini, Nat. Med. "
            "1999, 5, 1032. [21] a) Q. Liu, T. X. Zhang, Y."
        ),
        (
            "751. [22] A. P. Blum, J. K. Kammeyer, J. Yin, D. T. Crystal, "
            "A. M. Rush, M. K. Gilson, N. C. Gianneschi, J. Am. Chem. Soc. "
            "2014, 136, 15422. [23] M. Zasloff, Nature 2002, 415, 389."
        ),
    ]

    assert all(_looks_like_reference_chunk(fragment) for fragment in fragments)


def test_reference_chunk_detection_keeps_scientific_content():
    text = (
        "The designed antimicrobial peptide reduced bacterial load in a membrane "
        "disruption assay. The authors compared MIC values, hemolysis, and "
        "stability under serum conditions to evaluate therapeutic potential."
    )

    assert not _looks_like_reference_chunk(text)


def test_boilerplate_detection_matches_download_and_supplementary_text():
    text = (
        "Appendix A. Supplementary data related to this article can be found "
        "at dx.doi.org. Downloaded from Wiley Online Library. See the Terms "
        "and Conditions for rules of use."
    )

    assert _looks_like_boilerplate_chunk(text)


def test_overview_query_detection_matches_broad_chinese_question():
    assert _is_overview_query("现有的文献说的啥")


def test_select_retrieval_candidates_filters_references_and_diversifies_sources():
    candidates = [
        {
            "chunk_id": "ref-1",
            "source_id": "paper-a",
            "score": 0.99,
            "text": (
                "[1] A. Author, Nature 2020, 1, 1. [2] B. Author, Science "
                "2021, 2, 2. [3] C. Author, Cell 2022, 3, 3. [4] D. Author, "
                "J. Med. Chem. 2023, 4, 4. [5] E. Author, ACS Nano 2024, 5, 5."
            ),
        },
        {
            "chunk_id": "a-1",
            "source_id": "paper-a",
            "score": 0.9,
            "text": "This study reports antimicrobial peptide design and in vivo validation.",
        },
        {
            "chunk_id": "a-2",
            "source_id": "paper-a",
            "score": 0.89,
            "text": "The assay compares MIC, hemolysis, and stability outcomes.",
        },
        {
            "chunk_id": "b-1",
            "source_id": "paper-b",
            "score": 0.88,
            "text": "A second paper describes a new peptide family with immune activity.",
        },
    ]

    selected = _select_retrieval_candidates(candidates, top_k=3)

    assert [item["chunk_id"] for item in selected] == ["a-1", "b-1", "a-2"]


@pytest.mark.asyncio
async def test_retrieve_chunks_rechecks_governed_access_before_fetch(
    db,
    admin_user,
    monkeypatch,
):
    async def deny_access(**_kwargs):
        return False

    async def fail_if_fetched(*_args, **_kwargs):
        raise AssertionError("revoked source content must not be fetched")

    monkeypatch.setattr(
        rag_service,
        "can_user_use_source_in_agent",
        deny_access,
    )
    monkeypatch.setattr(rag_service, "_rag_chunks", fail_if_fetched)

    chunks = await retrieve_chunks(
        query="restricted evidence",
        source_ids=["revoked-source"],
        db=db,
        mode="rag",
        user_id=admin_user.id,
        project_id=None,
        agent_run_id="agent-run-1",
    )

    assert chunks == []


@pytest.mark.asyncio
async def test_retrieve_chunks_excludes_revoked_vector_candidate(
    db,
    admin_user,
    monkeypatch,
):
    source = Source(
        type="file",
        name="revoked-candidate.pdf",
        owner_id=admin_user.id,
        processing_state="ready",
        progress=100,
    )
    db.add(source)
    await db.flush()
    asset = ResearchAsset(
        asset_type="paper",
        title="Revoked candidate",
        source_id=source.id,
        owner_id=admin_user.id,
        visibility_scope="lab_private",
        classification="confidential",
        catalog_status="published",
        lifecycle_status="active",
    )
    db.add(asset)
    chunk = Chunk(
        source_id=source.id,
        text="REVOKED CONTENT",
        chunk_index=0,
    )
    db.add(chunk)
    await db.commit()

    policy_state = {"enabled": True}

    async def allow_source_access(**_kwargs):
        return True

    async def fake_embed_query(*_args, **_kwargs):
        return [0.1, 0.2]

    def fake_search_vectors(*_args, **_kwargs):
        return [{"chunk_id": chunk.id, "score": 1.0}]

    async def filter_current_permissions(*_args, asset_ids, **_kwargs):
        return asset_ids if policy_state["enabled"] else []

    monkeypatch.setattr(
        rag_service,
        "can_user_use_source_in_agent",
        allow_source_access,
    )
    monkeypatch.setattr(rag_service, "_remote_embed_query", fake_embed_query)
    monkeypatch.setattr(rag_service, "search_vectors", fake_search_vectors)
    monkeypatch.setattr(
        rag_service,
        "filter_authorized_asset_ids",
        filter_current_permissions,
    )

    before = await retrieve_chunks(
        query="restricted evidence",
        source_ids=[source.id],
        db=db,
        mode="rag",
        user_id=admin_user.id,
        project_id=None,
        agent_run_id="agent-run-2",
    )
    policy_state["enabled"] = False
    after = await retrieve_chunks(
        query="restricted evidence",
        source_ids=[source.id],
        db=db,
        mode="rag",
        user_id=admin_user.id,
        project_id=None,
        agent_run_id="agent-run-2",
    )

    assert before[0]["text"] == "REVOKED CONTENT"
    assert after == []
