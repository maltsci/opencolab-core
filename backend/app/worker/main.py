"""Document processing worker.

Runs source ingestion, optional bibliographic enrichment, and an HTTP server
exposing query-time embeddings and health checks on port 8001.
"""

import asyncio
from datetime import UTC, datetime, timedelta
import logging
import signal

import uvicorn
from fastapi import FastAPI
from pydantic import BaseModel
from sqlalchemy import delete, select, update

from app.core.config import settings
from app.core.database import async_session_factory
from app.models.source import Chunk, Source
from app.models.trace import SourceExtraction
from app.services.chunking_service import chunk_text
from app.services.bibliographic_metadata_service import enrich_bibliographic_metadata
from app.services.document_service import parse_document
from app.services.embedding_service import embed_query, embed_texts, preload_provider
from app.services.extraction_service import (
    build_failed_source_extraction_payload,
    build_source_extraction_payload,
    upsert_source_extraction,
)
from app.services.pdf_service import (
    extract_pdf_document_metadata,
    preload_marker_converter,
)
from app.services.runtime_config import get_runtime_value
from app.services.vector_store import delete_vectors_by_source, upsert_vectors

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s"
)
logger = logging.getLogger(__name__)

POLL_INTERVAL = 3  # seconds
STARTUP_DB_RETRIES = 15
STARTUP_DB_RETRY_DELAY_SECONDS = 2
STARTUP_QDRANT_RETRIES = 15
STARTUP_QDRANT_RETRY_DELAY_SECONDS = 2


# ---------------------------------------------------------------------------
# HTTP API (embedding endpoint + health check)
# ---------------------------------------------------------------------------

http_app = FastAPI(title="OpenColab Worker")


class EmbedRequest(BaseModel):
    text: str


class EmbedResponse(BaseModel):
    embedding: list[float]


@http_app.get("/health")
def health():
    return {"status": "ok"}


@http_app.post("/embed", response_model=EmbedResponse)
def embed_endpoint(req: EmbedRequest):
    embedding = embed_query(req.text)
    return EmbedResponse(embedding=embedding)


# ---------------------------------------------------------------------------
# Document processing pipeline (extracted from app.api.sources)
# ---------------------------------------------------------------------------


async def _set_state(
    source_id: str, state: str, progress: int, error: str | None = None
) -> None:
    async with async_session_factory() as db:
        result = await db.execute(select(Source).where(Source.id == source_id))
        src = result.scalar_one_or_none()
        if src is None:
            return
        src.processing_state = state
        src.progress = progress
        src.error_message = error
        await db.commit()


async def _persist_extraction_payload(source_id: str, payload: dict) -> None:
    async with async_session_factory() as db:
        await upsert_source_extraction(db, source_id, payload)
        await db.commit()


async def _get_source_name(source_id: str) -> str | None:
    async with async_session_factory() as db:
        source_result = await db.execute(select(Source).where(Source.id == source_id))
        source = source_result.scalar_one_or_none()
        return source.name if source is not None else None


async def _mark_source_failed(source_id: str, error_message: str) -> None:
    source_name = await _get_source_name(source_id)
    if source_name is not None:
        try:
            await _persist_extraction_payload(
                source_id,
                build_failed_source_extraction_payload(
                    source_name=source_name,
                    error_message=error_message,
                ),
            )
        except Exception:
            logger.exception(
                "Failed to persist failed extraction payload for source %s",
                source_id,
            )

    await _set_state(source_id, "failed", 0, error=error_message)


def build_data_package_index_text(meta_info: dict) -> str:
    """Build searchable index text for a data package from its user-supplied meta info."""
    title = str(meta_info.get("title") or "").strip()
    description = str(meta_info.get("description") or "").strip()
    tags = meta_info.get("tags") or []
    if isinstance(tags, str):
        tags = [t.strip() for t in tags.split(",") if t.strip()]
    filename = str(meta_info.get("filename") or "").strip()

    lines = [f"Title: {title}"]
    if description:
        lines.append(f"Description: {description}")
    if tags:
        lines.append(f"Tags: {', '.join(str(t) for t in tags)}")
    if filename:
        lines.append(f"File: {filename}")
    return "\n".join(lines)


async def _get_source_type_and_meta(source_id: str) -> tuple[str | None, dict | None]:
    async with async_session_factory() as db:
        result = await db.execute(select(Source).where(Source.id == source_id))
        source = result.scalar_one_or_none()
        if source is None:
            return None, None
        return source.type, source.meta_info


async def process_source(source_id: str, file_path: str) -> None:
    """Parse -> chunk -> embed -> upsert for a single source."""
    loop = asyncio.get_event_loop()

    try:
        source_type, meta_info = await _get_source_type_and_meta(source_id)

        # Remove leftover chunks/vectors from a previous failed run
        async with async_session_factory() as db:
            await db.execute(delete(Chunk).where(Chunk.source_id == source_id))
            await db.commit()
        await loop.run_in_executor(None, delete_vectors_by_source, source_id)

        await _set_state(source_id, "parsing", 5)
        if source_type == "data_package":
            # Data packages are indexed by their meta info; the ZIP is not parsed
            text = build_data_package_index_text(meta_info or {})
            logger.info(
                "Built data package index text for source %s (%d characters)",
                source_id,
                len(text),
            )
        else:
            logger.info("Parsing source %s", source_id)
            text = await parse_document(file_path, allow_unmanaged_absolute=False)
            logger.info("Parsed source %s (%d characters)", source_id, len(text))
        document_metadata = (
            extract_pdf_document_metadata(file_path)
            if file_path.lower().endswith(".pdf")
            else None
        )
        text = text.replace("\x00", "")
        await _set_state(source_id, "parsing", 25)

        chunks_text = chunk_text(text)
        logger.info("Chunked source %s into %d chunks", source_id, len(chunks_text))
        if not chunks_text:
            if source_type != "data_package":
                source_name = await _get_source_name(source_id)
                if source_name is not None:
                    await _persist_extraction_payload(
                        source_id,
                        build_source_extraction_payload(
                            source_name=source_name,
                            text=text,
                            document_metadata=document_metadata,
                        ),
                    )
            await _set_state(source_id, "ready", 100)
            return

        await _set_state(source_id, "embedding", 25)
        logger.info("Embedding source %s (%d chunks)", source_id, len(chunks_text))

        def progress_cb(done: int, total: int) -> None:
            pct = 25 + int((done / total) * 70)
            asyncio.run_coroutine_threadsafe(
                _set_state(source_id, "embedding", pct), loop
            )

        embeddings = await loop.run_in_executor(
            None, embed_texts, chunks_text, progress_cb
        )

        async with async_session_factory() as db:
            chunk_objects = []
            for i, chunk_text_item in enumerate(chunks_text):
                chunk = Chunk(source_id=source_id, text=chunk_text_item, chunk_index=i)
                db.add(chunk)
                chunk_objects.append(chunk)
            await db.flush()
            chunk_ids = [c.id for c in chunk_objects]
            await db.commit()

        await loop.run_in_executor(
            None,
            upsert_vectors,
            chunk_ids,
            embeddings,
            [source_id] * len(chunk_ids),
        )
        logger.info("Upserted vectors for source %s", source_id)

        source_name = await _get_source_name(source_id)
        if source_type != "data_package":
            try:
                if source_name is not None:
                    await _persist_extraction_payload(
                        source_id,
                        build_source_extraction_payload(
                            source_name=source_name,
                            text=text,
                            document_metadata=document_metadata,
                        ),
                    )
            except Exception:
                logger.exception(
                    "Extraction build failed for source %s; continuing without blocking",
                    source_id,
                )
                if source_name is not None:
                    await _persist_extraction_payload(
                        source_id,
                        build_failed_source_extraction_payload(
                            source_name=source_name,
                            error_message="Extraction build failed",
                        ),
                    )

        await _set_state(source_id, "ready", 100)
        logger.info("Source %s is ready", source_id)
    except Exception as e:
        logger.exception("Processing failed for source %s", source_id)
        try:
            await _mark_source_failed(source_id, str(e))
        except Exception:
            logger.exception("Failed to record failure state for source %s", source_id)


# ---------------------------------------------------------------------------
# Job polling loop
# ---------------------------------------------------------------------------


async def claim_job() -> tuple[str, str] | None:
    """Atomically claim one pending source for processing.

    Uses SELECT ... FOR UPDATE SKIP LOCKED so multiple workers can run safely.
    """
    async with async_session_factory() as db:
        result = await db.execute(
            select(Source.id, Source.content_path)
            .where(Source.processing_state == "pending")
            .limit(1)
            .with_for_update(skip_locked=True)
        )
        row = result.first()
        if not row:
            return None
        source_id, content_path = row
        await db.execute(
            update(Source)
            .where(Source.id == source_id)
            .values(processing_state="parsing", progress=0)
        )
        await db.commit()
        return source_id, content_path


async def poll_once(semaphore: asyncio.Semaphore) -> bool:
    """Claim and start at most one job when processing capacity is available."""
    if semaphore.locked():
        return False

    await semaphore.acquire()
    try:
        job = await claim_job()
    except Exception:
        semaphore.release()
        raise

    if not job:
        semaphore.release()
        return False

    source_id, content_path = job
    logger.info("Claimed job: source %s (%s)", source_id, content_path)

    async def _run(sid: str, path: str) -> None:
        try:
            await process_source(sid, path)
        finally:
            semaphore.release()

    asyncio.create_task(_run(source_id, content_path))
    return True


async def poll_loop() -> None:
    """Continuously poll for pending jobs and process them."""
    max_concurrent = max(1, settings.worker_max_concurrent)
    semaphore = asyncio.Semaphore(max_concurrent)
    logger.info(
        "Worker poll loop started (interval=%ds, max_concurrent=%d)",
        POLL_INTERVAL,
        max_concurrent,
    )

    while True:
        try:
            did_start = await poll_once(semaphore)
        except Exception:
            logger.exception("Error claiming job, retrying after poll interval")
            await asyncio.sleep(POLL_INTERVAL)
            continue

        if not did_start:
            await asyncio.sleep(POLL_INTERVAL)


def _as_bool(value: str | None) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


async def claim_bibliographic_job(
    db,
) -> tuple[str, str, bool] | None:
    """Claim one durable bibliographic enrichment job."""
    enabled = _as_bool(await get_runtime_value("bibliographic_lookup_enabled", db))
    if not enabled:
        await db.execute(
            update(SourceExtraction)
            .where(SourceExtraction.metadata_status == "pending")
            .values(metadata_status="offline", metadata_error=None)
        )
        return None

    contact_email = await get_runtime_value(
        "bibliographic_lookup_contact_email",
        db,
    )
    if not contact_email:
        await db.execute(
            update(SourceExtraction)
            .where(SourceExtraction.metadata_status.in_(["pending", "offline"]))
            .values(
                metadata_status="failed",
                metadata_error="Bibliographic lookup contact email is not configured",
            )
        )
        return None

    now = datetime.now(UTC)
    extraction = await db.scalar(
        select(SourceExtraction)
        .where(
            SourceExtraction.metadata_status.in_(["pending", "offline"]),
            (
                SourceExtraction.metadata_next_attempt_at.is_(None)
                | (SourceExtraction.metadata_next_attempt_at <= now)
            ),
        )
        .order_by(SourceExtraction.created_at, SourceExtraction.id)
        .limit(1)
        .with_for_update(skip_locked=True)
    )
    if extraction is None:
        return None
    extraction.metadata_status = "resolving"
    auto_apply = _as_bool(
        await get_runtime_value("bibliographic_auto_apply_enabled", db)
    )
    await db.flush()
    return extraction.source_id, contact_email, auto_apply


async def _claim_bibliographic_job() -> tuple[str, str, bool] | None:
    async with async_session_factory() as db:
        job = await claim_bibliographic_job(db)
        await db.commit()
        return job


async def process_bibliographic_job(
    source_id: str,
    contact_email: str,
    auto_apply: bool,
) -> None:
    """Resolve one bibliographic job without changing source readiness."""
    async with async_session_factory() as db:
        try:
            await enrich_bibliographic_metadata(
                db,
                source_id=source_id,
                contact_email=contact_email,
                auto_apply=auto_apply,
            )
            await db.commit()
        except Exception as exc:
            await db.rollback()
            extraction = await db.scalar(
                select(SourceExtraction).where(SourceExtraction.source_id == source_id)
            )
            if extraction is None:
                return
            extraction.metadata_attempts += 1
            extraction.metadata_error = type(exc).__name__
            if extraction.metadata_attempts >= 3:
                extraction.metadata_status = "failed"
                extraction.metadata_next_attempt_at = None
            else:
                extraction.metadata_status = "pending"
                extraction.metadata_next_attempt_at = datetime.now(UTC) + timedelta(
                    seconds=30 * (2 ** (extraction.metadata_attempts - 1))
                )
            await db.commit()
            logger.warning(
                "Bibliographic enrichment failed for source %s (%s)",
                source_id,
                type(exc).__name__,
            )


async def bibliographic_poll_loop() -> None:
    """Continuously process metadata jobs independently from PDF parsing."""
    while True:
        try:
            job = await _claim_bibliographic_job()
            if job is None:
                await asyncio.sleep(POLL_INTERVAL)
                continue
            await process_bibliographic_job(*job)
        except Exception:
            logger.exception(
                "Error processing bibliographic metadata, retrying after poll interval"
            )
            await asyncio.sleep(POLL_INTERVAL)


# ---------------------------------------------------------------------------
# Startup: mark stale sources as failed + pre-load embedding model
# ---------------------------------------------------------------------------


async def mark_stale_sources_pending() -> None:
    """Reset non-terminal sources to pending so the worker re-processes them.

    On worker startup, any source in parsing/embedding state was interrupted
    by the previous worker shutting down — reset to pending for retry.
    """
    async with async_session_factory() as db:
        result = await db.execute(
            select(Source.id).where(
                Source.processing_state.in_(["parsing", "embedding"])
            )
        )
        stale_ids = [row[0] for row in result.all()]
        if not stale_ids:
            return

        await db.execute(
            update(Source)
            .where(Source.id.in_(stale_ids))
            .values(processing_state="pending", progress=0, error_message=None)
        )
        await db.commit()
        logger.warning(
            "Reset %d stale source(s) to pending on worker startup", len(stale_ids)
        )


async def mark_stale_bibliographic_jobs_pending() -> None:
    """Reset interrupted metadata lookups so they can be retried."""
    async with async_session_factory() as db:
        result = await db.execute(
            update(SourceExtraction)
            .where(SourceExtraction.metadata_status == "resolving")
            .values(metadata_status="pending")
        )
        if result.rowcount:
            await db.commit()
            logger.warning(
                "Reset %d stale bibliographic job(s) to pending",
                result.rowcount,
            )


def preload_embedding_model() -> None:
    """Pre-load embedding provider(s) so the first /embed call is fast."""
    primary = settings.embedding_provider
    fallback = settings.embedding_fallback_provider

    logger.info("Pre-loading embedding provider: %s", primary)
    try:
        preload_provider(primary)
        logger.info("Embedding provider ready: %s", primary)
        return
    except Exception:
        logger.exception(
            "Primary embedding provider failed during preload: %s", primary
        )

    if fallback == "none" or fallback == primary:
        raise

    logger.warning(
        "Pre-loading fallback embedding provider: %s (primary=%s)",
        fallback,
        primary,
    )
    preload_provider(fallback)
    logger.info("Fallback embedding provider ready: %s", fallback)


def preload_pdf_parser() -> None:
    """Pre-load marker PDF models so source jobs do not sit at 5% during model init."""
    if not settings.pdf_marker_enabled:
        logger.info("Marker PDF parser disabled; using basic PDF text extraction")
        return
    if not settings.pdf_marker_preload_enabled:
        logger.info("Marker PDF model preload disabled")
        return
    logger.info("Pre-loading marker PDF models")
    try:
        preload_marker_converter()
        logger.info("Marker PDF models ready")
    except Exception:
        logger.exception(
            "Marker PDF model preload failed; PDF jobs will use fallback if needed"
        )


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

_shutdown_event = asyncio.Event()


def _handle_signal() -> None:
    logger.info("Shutdown signal received")
    _shutdown_event.set()


async def _check_dependencies() -> None:
    """Verify that required external services are reachable before starting."""
    from app.core.database import check_db_connection
    from app.services.vector_store import _get_client

    # Check PostgreSQL
    await _wait_for_database(
        check_db_connection,
        retries=STARTUP_DB_RETRIES,
        delay_seconds=STARTUP_DB_RETRY_DELAY_SECONDS,
    )
    logger.info(
        "PostgreSQL connection OK (%s:%s)",
        settings.postgres_host,
        settings.postgres_port,
    )

    # Check Qdrant
    loop = asyncio.get_event_loop()

    async def check_qdrant_connection() -> None:
        await loop.run_in_executor(None, _get_client)

    await _wait_for_dependency(
        "Qdrant",
        check_qdrant_connection,
        retries=STARTUP_QDRANT_RETRIES,
        delay_seconds=STARTUP_QDRANT_RETRY_DELAY_SECONDS,
    )
    logger.info(
        "Qdrant connection OK (%s:%s)",
        settings.qdrant_host,
        settings.qdrant_port,
    )


async def _wait_for_dependency(
    dependency_name: str,
    check_connection,
    retries: int = STARTUP_DB_RETRIES,
    delay_seconds: float = STARTUP_DB_RETRY_DELAY_SECONDS,
) -> None:
    """Retry transient startup dependency failures before giving up."""
    for attempt in range(1, retries + 1):
        try:
            await check_connection()
            return
        except ConnectionError:
            if attempt == retries:
                raise

            logger.warning(
                "%s not ready yet; retrying in %ss (%s/%s)",
                dependency_name,
                delay_seconds,
                attempt,
                retries,
            )
            await asyncio.sleep(delay_seconds)


async def _wait_for_database(
    check_connection,
    retries: int = STARTUP_DB_RETRIES,
    delay_seconds: float = STARTUP_DB_RETRY_DELAY_SECONDS,
) -> None:
    """Retry transient startup database failures before giving up."""
    await _wait_for_dependency(
        "PostgreSQL",
        check_connection,
        retries=retries,
        delay_seconds=delay_seconds,
    )


async def main() -> None:
    loop = asyncio.get_event_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, _handle_signal)

    # Verify external dependencies before doing any real work
    await _check_dependencies()

    # Startup tasks
    await mark_stale_sources_pending()
    await mark_stale_bibliographic_jobs_pending()
    await loop.run_in_executor(None, preload_embedding_model)
    await loop.run_in_executor(None, preload_pdf_parser)

    # Start HTTP server and poll loop concurrently
    config = uvicorn.Config(http_app, host="0.0.0.0", port=8001, log_level="info")
    server = uvicorn.Server(config)

    poll_task = asyncio.create_task(poll_loop())
    bibliographic_poll_task = asyncio.create_task(bibliographic_poll_loop())
    server_task = asyncio.create_task(server.serve())

    # Wait for shutdown signal, then cancel tasks
    await _shutdown_event.wait()
    poll_task.cancel()
    bibliographic_poll_task.cancel()
    server.should_exit = True
    await server_task


if __name__ == "__main__":
    asyncio.run(main())
