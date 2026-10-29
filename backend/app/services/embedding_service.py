import logging
from typing import Callable

import httpx
from app.core.config import settings

logger = logging.getLogger(__name__)

_local_model = None

# Batch size for progress-reporting embeddings. Small enough that a large PDF
# still yields several progress updates, big enough not to thrash the model.
_EMBED_BATCH_SIZE = 16


def _provider_model_name(provider: str) -> str:
    if provider == "siliconflow":
        return settings.siliconflow_embedding_model
    if settings.embedding_local_model_path:
        return settings.embedding_local_model_path
    return settings.embedding_model


def _get_local_model():
    global _local_model
    if _local_model is None:
        try:
            from sentence_transformers import SentenceTransformer

            model_path = (
                settings.embedding_local_model_path
                if settings.embedding_local_model_path
                else settings.embedding_model
            )
            _local_model = SentenceTransformer(
                model_path,
                local_files_only=settings.embedding_local_files_only,
            )
            logger.info(
                "Loaded local embedding model: %s (local_files_only=%s)",
                model_path,
                settings.embedding_local_files_only,
            )
        except Exception as e:
            logger.error("Failed to load local embedding model: %s", e)
            raise
    return _local_model


def _embed_with_local(
    texts: list[str],
    progress_cb: Callable[[int, int], None] | None = None,
) -> list[list[float]]:
    if not texts:
        return []
    model = _get_local_model()
    total = len(texts)
    results: list[list[float]] = []
    for start in range(0, total, _EMBED_BATCH_SIZE):
        batch = texts[start : start + _EMBED_BATCH_SIZE]
        embeddings = model.encode(batch, normalize_embeddings=True)
        results.extend(embeddings.tolist())
        if progress_cb is not None:
            try:
                progress_cb(min(start + len(batch), total), total)
            except Exception:
                logger.exception("embedding progress callback failed")
    return results


def _embed_with_siliconflow(
    texts: list[str],
    progress_cb: Callable[[int, int], None] | None = None,
) -> list[list[float]]:
    if not settings.siliconflow_api_key:
        raise ValueError(
            "OPENCOLAB_SILICONFLOW_API_KEY is required when using siliconflow embedding provider."
        )

    base_url = settings.siliconflow_base_url.rstrip("/")
    headers = {
        "Authorization": f"Bearer {settings.siliconflow_api_key}",
        "Content-Type": "application/json",
    }
    total = len(texts)
    results: list[list[float]] = []
    with httpx.Client(timeout=60.0) as client:
        for start in range(0, total, _EMBED_BATCH_SIZE):
            batch = texts[start : start + _EMBED_BATCH_SIZE]
            payload = {
                "model": settings.siliconflow_embedding_model,
                "input": batch if len(batch) > 1 else batch[0],
            }
            response = client.post(f"{base_url}/embeddings", headers=headers, json=payload)
            response.raise_for_status()
            body = response.json()
            data = body.get("data")
            if not isinstance(data, list):
                raise ValueError("Invalid SiliconFlow response: missing data list")
            data_sorted = sorted(
                data,
                key=lambda item: item.get("index", 0)
                if isinstance(item, dict)
                else 0,
            )
            for item in data_sorted:
                embedding = item.get("embedding") if isinstance(item, dict) else None
                if not isinstance(embedding, list):
                    raise ValueError(
                        "Invalid SiliconFlow response: data item missing embedding list"
                    )
                results.append(embedding)
            if progress_cb is not None:
                try:
                    progress_cb(min(start + len(batch), total), total)
                except Exception:
                    logger.exception("embedding progress callback failed")
    return results


def _provider_chain() -> list[str]:
    chain = [settings.embedding_provider]
    fallback = settings.embedding_fallback_provider
    if fallback != "none" and fallback not in chain:
        chain.append(fallback)
    return chain


def preload_provider(provider: str) -> None:
    if provider == "local":
        _get_local_model()
        return
    if provider == "siliconflow":
        if not settings.siliconflow_api_key:
            raise ValueError(
                "OPENCOLAB_SILICONFLOW_API_KEY is required when using siliconflow embedding provider."
            )
        return
    raise ValueError(f"Unsupported embedding provider: {provider}")


def embed_texts(
    texts: list[str],
    progress_cb: Callable[[int, int], None] | None = None,
) -> list[list[float]]:
    """Embed texts, optionally reporting per-batch progress.

    progress_cb is invoked as progress_cb(done, total) after each batch.
    """
    if not texts:
        return []

    chain = _provider_chain()
    last_error: Exception | None = None
    for i, provider in enumerate(chain):
        try:
            if provider == "local":
                return _embed_with_local(texts, progress_cb)
            if provider == "siliconflow":
                return _embed_with_siliconflow(texts, progress_cb)
            raise ValueError(f"Unsupported embedding provider: {provider}")
        except Exception as err:
            last_error = err
            if i < len(chain) - 1:
                logger.warning(
                    "Embedding provider '%s' failed with model '%s'; falling back to '%s'. Error: %s",
                    provider,
                    _provider_model_name(provider),
                    chain[i + 1],
                    err,
                )
                continue
            logger.error(
                "Embedding provider '%s' failed with model '%s' and no further fallback is available.",
                provider,
                _provider_model_name(provider),
            )
            break
    raise RuntimeError("All embedding providers failed") from last_error


def embed_query(query: str) -> list[float]:
    return embed_texts([query])[0]
