import io
import zipfile

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.source import Chunk, Source
from app.worker import main as worker_main
from conftest import test_session_factory

pytestmark = pytest.mark.asyncio


def _make_zip(entries: dict[str, bytes]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as zf:
        for name, content in entries.items():
            zf.writestr(name, content)
    return buffer.getvalue()


async def _create_session(client: AsyncClient, headers) -> str:
    response = await client.post(
        "/api/v1/sessions",
        json={"title": "Data Package Session"},
        headers=headers,
    )
    assert response.status_code == 201
    return response.json()["id"]


async def test_session_upload_data_package_creates_source_with_meta(
    client: AsyncClient,
    researcher_headers,
    db: AsyncSession,
):
    session_id = await _create_session(client, researcher_headers)
    archive = _make_zip({"raw/results.bin": b"\x00\x01\x02"})

    response = await client.post(
        f"/api/v1/sessions/{session_id}/sources",
        data={
            "upload_kind": "data_package",
            "meta_title": "Experiment A raw data",
            "meta_description": "Flow cytometry output",
            "meta_tags": "facs, experiment-a",
        },
        files={"file": ("experiment-a.zip", archive, "application/zip")},
        headers=researcher_headers,
    )

    assert response.status_code == 201
    payload = response.json()
    assert payload["type"] == "data_package"
    assert payload["name"] == "Experiment A raw data"
    assert payload["processing_state"] == "pending"
    assert payload["meta_info"]["title"] == "Experiment A raw data"
    assert payload["meta_info"]["description"] == "Flow cytometry output"
    assert payload["meta_info"]["tags"] == ["facs", "experiment-a"]
    assert payload["meta_info"]["filename"] == "experiment-a.zip"

    source = await db.scalar(select(Source).where(Source.id == payload["id"]))
    assert source.type == "data_package"
    assert source.content_path.endswith(".zip")


async def test_session_upload_data_package_requires_title(
    client: AsyncClient,
    researcher_headers,
):
    session_id = await _create_session(client, researcher_headers)
    archive = _make_zip({"data.bin": b"\x00"})

    response = await client.post(
        f"/api/v1/sessions/{session_id}/sources",
        data={"upload_kind": "data_package"},
        files={"file": ("experiment.zip", archive, "application/zip")},
        headers=researcher_headers,
    )

    assert response.status_code == 400


async def test_session_upload_data_package_requires_zip(
    client: AsyncClient,
    researcher_headers,
):
    session_id = await _create_session(client, researcher_headers)

    response = await client.post(
        f"/api/v1/sessions/{session_id}/sources",
        data={"upload_kind": "data_package", "meta_title": "Not a zip"},
        files={"file": ("notes.txt", b"plain text", "text/plain")},
        headers=researcher_headers,
    )

    assert response.status_code == 400


async def test_worker_indexes_data_package_from_meta(
    monkeypatch,
    db: AsyncSession,
):
    source = Source(
        type="data_package",
        name="Experiment A raw data",
        content_path="ab/fake.zip",
        meta_info={
            "title": "Experiment A raw data",
            "description": "Flow cytometry output",
            "tags": ["facs", "experiment-a"],
            "filename": "experiment-a.zip",
        },
        processing_state="pending",
    )
    db.add(source)
    await db.commit()

    async def fail_parse_document(file_path: str, **kwargs) -> str:
        raise AssertionError("data packages must not be parsed")

    def fake_embed_texts(texts, progress_cb=None):
        return [[0.1, 0.2, 0.3] for _ in texts]

    monkeypatch.setattr(worker_main, "async_session_factory", test_session_factory)
    monkeypatch.setattr(worker_main, "parse_document", fail_parse_document)
    monkeypatch.setattr(worker_main, "embed_texts", fake_embed_texts)
    monkeypatch.setattr(worker_main, "upsert_vectors", lambda *args: None)
    monkeypatch.setattr(worker_main, "delete_vectors_by_source", lambda *args: None)

    await worker_main.process_source(source.id, source.content_path)

    await db.refresh(source)
    assert source.processing_state == "ready"

    chunks = (
        await db.scalars(
            select(Chunk).where(Chunk.source_id == source.id).order_by(Chunk.chunk_index)
        )
    ).all()
    assert chunks
    combined = "\n".join(chunk.text for chunk in chunks)
    assert "Experiment A raw data" in combined
    assert "Flow cytometry output" in combined
    assert "facs" in combined
    assert "experiment-a.zip" in combined


async def test_worker_uses_parse_document_for_regular_files(
    monkeypatch,
    db: AsyncSession,
):
    source = Source(
        type="file",
        name="notes.md",
        content_path="ab/fake.md",
        processing_state="pending",
    )
    db.add(source)
    await db.commit()

    async def fake_parse_document(file_path: str, **kwargs) -> str:
        return "parsed document text"

    def fake_embed_texts(texts, progress_cb=None):
        return [[0.1, 0.2, 0.3] for _ in texts]

    monkeypatch.setattr(worker_main, "async_session_factory", test_session_factory)
    monkeypatch.setattr(worker_main, "parse_document", fake_parse_document)
    monkeypatch.setattr(worker_main, "embed_texts", fake_embed_texts)
    monkeypatch.setattr(worker_main, "upsert_vectors", lambda *args: None)
    monkeypatch.setattr(worker_main, "delete_vectors_by_source", lambda *args: None)

    await worker_main.process_source(source.id, source.content_path)

    await db.refresh(source)
    assert source.processing_state == "ready"

    chunks = (
        await db.scalars(select(Chunk).where(Chunk.source_id == source.id))
    ).all()
    assert chunks
    assert "parsed document text" in "\n".join(chunk.text for chunk in chunks)
