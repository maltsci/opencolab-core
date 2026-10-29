import logging
import re
from collections import defaultdict

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.research_asset import ResearchAsset
from app.models.source import Source
from app.models.source import Chunk
from app.models.user import User
from app.core.governance import Capability
from app.services.knowledge_access_service import filter_authorized_asset_ids
from app.services.research_asset_service import can_user_discover_asset
from app.services.llm_service import should_bypass_proxy_for_api_base
from app.services.sharing_service import can_user_use_source_in_agent
from app.services.vector_store import search_vectors

logger = logging.getLogger(__name__)

REFERENCE_MARKER_RE = re.compile(r"(?:\[\d{1,3}\]|\(\d{4}\)|\b(?:19|20)\d{2}\b)")
BRACKET_REFERENCE_RE = re.compile(r"\[\d{1,3}\]")
AUTHOR_INITIAL_RE = re.compile(r"\b[A-Z]\.\s?(?:[A-Z]\.)?\b")
YEAR_VOLUME_PAGE_RE = re.compile(r"\b(?:19|20)\d{2},\s*\d{1,4},\s*\d{1,6}\b")
JOURNAL_CUE_RE = re.compile(
    r"\b(?:Nat\.|Nature|Science|Cell|J\.|Proc\.|ACS|Adv\.|Chem\.|Biomaterials|"
    r"Materials|Med\.|Pharmacol\.|Interfaces|Commun\.|Angew\.)\b",
    re.IGNORECASE,
)
JOURNAL_CUES = (
    "nat.",
    "nature",
    "science",
    "cell",
    "j.",
    "proc.",
    "acs",
    "adv.",
    "chem.",
    "biomaterials",
    "materials",
    "med.",
    "pharmacol.",
    "interfaces",
    "commun.",
    "angew.",
)
OVERVIEW_QUERY_CUES = (
    "说的啥",
    "讲的啥",
    "讲什么",
    "说什么",
    "总结",
    "概括",
    "摘要",
    "主要内容",
    "核心观点",
    "文献说",
    "literature says",
    "summarize",
    "summary",
    "overview",
    "main point",
)
BOILERPLATE_CUES = (
    "references",
    "bibliography",
    "supplementary data",
    "downloaded from",
    "terms and conditions",
    "conflict of interest",
    "acknowledgements",
    "contents lists available",
    "article history",
    "orcid identification",
    "e-mail:",
)
SCIENTIFIC_CONTENT_CUES = (
    "abstract",
    "antimicrobial",
    "peptide",
    "method",
    "result",
    "assay",
    "mic",
    "in vivo",
    "in vitro",
    "infection",
    "mechanism",
    "therapy",
    "治疗",
    "抗菌",
    "肽",
    "实验",
    "结果",
    "方法",
)


async def classify_query_mode(
    query: str,
    model: str | None,
    api_base: str | None,
    api_key: str | None,
) -> str:
    """Temporarily force document chat into RAG mode for better reliability."""
    logger.info("Query classification (forced): %r → rag", query[:60])
    return "rag"


async def _get_all_chunks(source_ids: list[str], db: AsyncSession) -> list[dict]:
    """Return all chunks for the given sources in document order."""
    result = await db.execute(
        select(Chunk)
        .where(Chunk.source_id.in_(source_ids))
        .order_by(Chunk.source_id, Chunk.chunk_index)
    )
    return [
        {"chunk_id": c.id, "source_id": c.source_id, "text": c.text, "score": 1.0}
        for c in result.scalars().all()
    ]


async def _remote_embed_query(query: str) -> list[float]:
    """Request a query embedding from the worker service."""
    async with httpx.AsyncClient(
        trust_env=not should_bypass_proxy_for_api_base(settings.worker_url)
    ) as client:
        resp = await client.post(
            f"{settings.worker_url}/embed",
            json={"text": query},
            timeout=30.0,
        )
        resp.raise_for_status()
        return resp.json()["embedding"]


async def _rag_chunks(
    query: str, source_ids: list[str], db: AsyncSession, top_k: int
) -> list[dict]:
    """Return the top-K most relevant chunks via vector similarity search."""
    query_embedding = await _remote_embed_query(query)
    candidate_limit = max(top_k * 6, top_k)
    vector_results = search_vectors(
        query_embedding,
        source_ids=source_ids,
        top_k=candidate_limit,
    )
    if not vector_results:
        return []

    chunk_ids = [r["chunk_id"] for r in vector_results]
    score_map = {r["chunk_id"]: r["score"] for r in vector_results}
    result = await db.execute(select(Chunk).where(Chunk.id.in_(chunk_ids)))
    candidates = sorted(
        [
            {"chunk_id": c.id, "source_id": c.source_id, "text": c.text,
             "score": score_map.get(c.id, 0)}
            for c in result.scalars().all()
        ],
        key=lambda x: x["score"],
        reverse=True,
    )
    selected = _select_retrieval_candidates(candidates, top_k)
    if _is_overview_query(query):
        front_matter = await _front_matter_chunks(source_ids, db, per_source=2)
        if len(front_matter) >= min(top_k, len(source_ids) * 2):
            return front_matter[:top_k]
        selected = _merge_unique_chunks(front_matter, selected, top_k)
    return selected


def _looks_like_reference_chunk(text: str) -> bool:
    """Detect chunks dominated by bibliography/reference-list content."""
    normalized = " ".join(text.split())
    if len(normalized) < 120:
        return False

    marker_count = len(REFERENCE_MARKER_RE.findall(normalized))
    bracket_reference_count = len(BRACKET_REFERENCE_RE.findall(normalized))
    author_initial_count = len(AUTHOR_INITIAL_RE.findall(normalized))
    year_volume_page_count = len(YEAR_VOLUME_PAGE_RE.findall(normalized))
    journal_count = len(JOURNAL_CUE_RE.findall(normalized))
    if journal_count == 0:
        lower_text = normalized.lower()
        journal_count = sum(1 for cue in JOURNAL_CUES if cue in lower_text)
    comma_count = normalized.count(",")
    separator_count = normalized.count(";") + normalized.count("[")

    return (
        (
            marker_count >= 5
            and journal_count >= 2
            and separator_count >= 4
        )
        or (
            bracket_reference_count >= 2
            and journal_count >= 1
            and author_initial_count >= 6
        )
        or (
            year_volume_page_count >= 1
            and journal_count >= 1
            and author_initial_count >= 8
        )
        or (
            year_volume_page_count >= 1
            and journal_count >= 1
            and (author_initial_count >= 4 or comma_count >= 8)
        )
        or (
            bracket_reference_count >= 1
            and journal_count >= 1
            and comma_count >= 8
        )
    )


def _looks_like_boilerplate_chunk(text: str) -> bool:
    normalized = " ".join(text.split()).lower()
    return (
        _looks_like_reference_chunk(text)
        or any(cue in normalized for cue in BOILERPLATE_CUES)
    )


def _is_overview_query(query: str) -> bool:
    normalized = query.strip().lower()
    return any(cue in normalized for cue in OVERVIEW_QUERY_CUES)


def _front_matter_score(text: str, chunk_index: int) -> int:
    normalized = " ".join(text.split()).lower()
    score = max(0, 8 - chunk_index)
    score += sum(3 for cue in SCIENTIFIC_CONTENT_CUES if cue in normalized)
    if _looks_like_boilerplate_chunk(text):
        score -= 20
    if len(normalized) < 160:
        score -= 3
    return score


async def _front_matter_chunks(
    source_ids: list[str],
    db: AsyncSession,
    per_source: int = 2,
    scan_limit: int = 8,
) -> list[dict]:
    if not source_ids:
        return []

    result = await db.execute(
        select(Chunk)
        .where(
            Chunk.source_id.in_(source_ids),
            Chunk.chunk_index < scan_limit,
        )
        .order_by(Chunk.source_id, Chunk.chunk_index)
    )

    by_source: dict[str, list[Chunk]] = defaultdict(list)
    for chunk in result.scalars().all():
        by_source[chunk.source_id].append(chunk)

    selected: list[dict] = []
    for source_id in source_ids:
        ranked = sorted(
            by_source.get(source_id, []),
            key=lambda chunk: _front_matter_score(chunk.text, chunk.chunk_index),
            reverse=True,
        )
        for chunk in ranked[:per_source]:
            if _front_matter_score(chunk.text, chunk.chunk_index) <= 0:
                continue
            selected.append(
                {
                    "chunk_id": chunk.id,
                    "source_id": chunk.source_id,
                    "text": chunk.text,
                    "score": 1.0,
                }
            )

    return selected


def _merge_unique_chunks(primary: list[dict], secondary: list[dict], top_k: int) -> list[dict]:
    selected: list[dict] = []
    seen: set[str] = set()
    for item in [*primary, *secondary]:
        chunk_id = item["chunk_id"]
        if chunk_id in seen:
            continue
        selected.append(item)
        seen.add(chunk_id)
        if len(selected) >= top_k:
            break
    return selected


def _select_retrieval_candidates(candidates: list[dict], top_k: int) -> list[dict]:
    """Filter low-value chunks and diversify the final prompt context."""
    if len(candidates) <= top_k:
        return candidates

    filtered = [item for item in candidates if not _looks_like_boilerplate_chunk(item["text"])]
    if len(filtered) < top_k:
        logger.info(
            "RAG reference filter kept only %d/%d candidates; falling back to unfiltered results",
            len(filtered),
            len(candidates),
        )
        filtered = candidates

    by_source: dict[str, list[dict]] = defaultdict(list)
    for item in filtered:
        by_source[item["source_id"]].append(item)

    selected: list[dict] = []
    source_ids_by_best_score = sorted(
        by_source.keys(),
        key=lambda source_id: by_source[source_id][0].get("score", 0),
        reverse=True,
    )

    while len(selected) < top_k and source_ids_by_best_score:
        progressed = False
        for source_id in source_ids_by_best_score:
            if by_source[source_id]:
                selected.append(by_source[source_id].pop(0))
                progressed = True
                if len(selected) >= top_k:
                    break
        if not progressed:
            break

    return selected[:top_k]


async def retrieve_chunks(
    query: str,
    source_ids: list[str],
    db: AsyncSession,
    mode: str,
    top_k: int = 5,
    *,
    user_id: str | None = None,
    project_id: str | None = None,
    agent_run_id: str | None = None,
) -> list[dict]:
    """Retrieve chunks using the pre-determined mode ('full' or 'rag')."""
    if not source_ids or user_id is None:
        return []

    user = await db.get(User, user_id)
    if user is None:
        return []
    authorized_source_ids = []
    metadata_only_source_ids = []
    for source_id in source_ids:
        if await can_user_use_source_in_agent(
            user=user,
            source_id=source_id,
            project_id=project_id,
            purpose="Retrieve source chunks for RAG",
            agent_run_id=agent_run_id or f"rag:{user_id}",
            db=db,
        ):
            authorized_source_ids.append(source_id)
        else:
            metadata_only_source_ids.append(source_id)

    chunks = (
        await _rag_chunks(query, authorized_source_ids, db, top_k)
        if authorized_source_ids
        else []
    )
    if chunks:
        chunks = await _filter_authorized_rag_chunks(
            chunks,
            db=db,
            user=user,
            project_id=project_id,
            agent_run_id=agent_run_id or f"rag:{user_id}",
        )
    if metadata_only_source_ids and len(chunks) < top_k:
        chunks.extend(
            await _metadata_only_chunks(
                metadata_only_source_ids,
                db,
                user=user,
                remaining=top_k - len(chunks),
            )
        )
    logger.info("RAG mode: returning %d chunks", len(chunks))
    return chunks


async def _filter_authorized_rag_chunks(
    chunks: list[dict],
    *,
    db: AsyncSession,
    user: User,
    project_id: str | None,
    agent_run_id: str,
) -> list[dict]:
    """Remove vector candidates whose backing asset is no longer authorized."""
    source_ids = list(dict.fromkeys(chunk["source_id"] for chunk in chunks))
    source_asset_rows = (
        await db.execute(
            select(ResearchAsset.source_id, ResearchAsset.id).where(
                ResearchAsset.source_id.in_(source_ids)
            )
        )
    ).all()
    asset_id_by_source_id = {
        source_id: asset_id
        for source_id, asset_id in source_asset_rows
        if source_id is not None
    }
    candidate_asset_ids = list(
        dict.fromkeys(
            asset_id_by_source_id[chunk["source_id"]]
            for chunk in chunks
            if chunk["source_id"] in asset_id_by_source_id
        )
    )
    authorized_asset_ids = set(
        await filter_authorized_asset_ids(
            db,
            user=user,
            asset_ids=candidate_asset_ids,
            capability=Capability.CONTENT_USE_IN_AGENT,
            project_id=project_id,
            purpose="Retrieve source chunks for RAG",
            actor_type="agent",
            agent_run_id=agent_run_id,
        )
    )
    return [
        chunk
        for chunk in chunks
        if asset_id_by_source_id.get(chunk["source_id"]) in authorized_asset_ids
    ]


async def _metadata_only_chunks(
    source_ids: list[str],
    db: AsyncSession,
    *,
    user: User,
    remaining: int,
) -> list[dict]:
    if remaining <= 0:
        return []
    rows = (
        await db.execute(
            select(ResearchAsset, Source)
            .join(Source, Source.id == ResearchAsset.source_id)
            .where(ResearchAsset.source_id.in_(source_ids))
        )
    ).all()
    chunks: list[dict] = []
    for asset, source in rows:
        if len(chunks) >= remaining:
            break
        if not await can_user_discover_asset(db, user, asset):
            continue
        metadata = {
            **(asset.catalog_metadata_json or {}),
            **(asset.metadata_json or {}),
        }
        metadata_items = [
            f"title: {asset.title}",
            f"type: {asset.asset_type}",
            f"visibility: {asset.visibility_scope}",
            f"source_name: {source.name}",
        ]
        if asset.description:
            metadata_items.append(f"description: {asset.description}")
        for key, value in metadata.items():
            if key in {"text", "content", "raw_text"}:
                continue
            metadata_items.append(f"{key}: {value}")
        chunks.append(
            {
                "chunk_id": f"metadata:{asset.id}",
                "source_id": source.id,
                "text": "Metadata only; content is not authorized. "
                + "; ".join(metadata_items),
                "score": 0.01,
            }
        )
    return chunks
