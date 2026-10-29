import asyncio

import pytest

from app.worker import main as worker_main
from app.worker.main import _wait_for_database, _wait_for_dependency

pytestmark = pytest.mark.asyncio


async def test_wait_for_database_retries_until_success(monkeypatch):
    attempts = {"count": 0}
    sleeps: list[float] = []

    async def flaky_check():
        attempts["count"] += 1
        if attempts["count"] < 3:
            raise ConnectionError("database is in recovery mode")

    async def fake_sleep(delay: float):
        sleeps.append(delay)

    monkeypatch.setattr(asyncio, "sleep", fake_sleep)

    await _wait_for_database(flaky_check, retries=3, delay_seconds=0.25)

    assert attempts["count"] == 3
    assert sleeps == [0.25, 0.25]


async def test_wait_for_database_raises_after_final_retry(monkeypatch):
    sleeps: list[float] = []

    async def always_fail():
        raise ConnectionError("database is in recovery mode")

    async def fake_sleep(delay: float):
        sleeps.append(delay)

    monkeypatch.setattr(asyncio, "sleep", fake_sleep)

    with pytest.raises(ConnectionError, match="recovery mode"):
        await _wait_for_database(always_fail, retries=3, delay_seconds=0.5)

    assert sleeps == [0.5, 0.5]


async def test_wait_for_dependency_retries_until_success(monkeypatch):
    attempts = {"count": 0}
    sleeps: list[float] = []

    async def flaky_check():
        attempts["count"] += 1
        if attempts["count"] < 2:
            raise ConnectionError("service warming up")

    async def fake_sleep(delay: float):
        sleeps.append(delay)

    monkeypatch.setattr(asyncio, "sleep", fake_sleep)

    await _wait_for_dependency(
        "Qdrant",
        flaky_check,
        retries=2,
        delay_seconds=0.1,
    )

    assert attempts["count"] == 2
    assert sleeps == [0.1]


async def test_poll_once_does_not_claim_when_concurrency_is_full(monkeypatch):
    semaphore = asyncio.Semaphore(1)
    await semaphore.acquire()
    claimed = False

    async def fake_claim_job():
        nonlocal claimed
        claimed = True
        return None

    monkeypatch.setattr(worker_main, "claim_job", fake_claim_job)

    did_start = await worker_main.poll_once(semaphore)

    assert did_start is False
    assert claimed is False
    semaphore.release()


async def test_poll_once_claims_one_job_when_slot_is_available(monkeypatch):
    semaphore = asyncio.Semaphore(1)
    claimed = 0
    processed: list[tuple[str, str]] = []

    async def fake_claim_job():
        nonlocal claimed
        claimed += 1
        return ("source-1", "/tmp/source.pdf")

    async def fake_process_source(source_id: str, file_path: str):
        processed.append((source_id, file_path))

    monkeypatch.setattr(worker_main, "claim_job", fake_claim_job)
    monkeypatch.setattr(worker_main, "process_source", fake_process_source)

    did_start = await worker_main.poll_once(semaphore)
    await asyncio.sleep(0)

    assert did_start is True
    assert claimed == 1
    assert processed == [("source-1", "/tmp/source.pdf")]
    assert semaphore._value == 1
