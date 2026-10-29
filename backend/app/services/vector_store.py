import logging

from qdrant_client import QdrantClient
from qdrant_client.models import Distance, PointStruct, VectorParams

from app.core.config import settings

logger = logging.getLogger(__name__)

_client: QdrantClient | None = None


def _get_client() -> QdrantClient:
    global _client
    if _client is None:
        host = settings.qdrant_host
        port = settings.qdrant_port
        try:
            _client = QdrantClient(host=host, port=port)
            _ensure_collection()
        except Exception as e:
            _client = None
            logger.error(
                "Failed to connect to Qdrant at %s:%s — %s. "
                "Check that the Qdrant service is running and OPENCOLAB_QDRANT_HOST / OPENCOLAB_QDRANT_PORT are correct.",
                host,
                port,
                e,
            )
            raise ConnectionError(
                f"Cannot connect to Qdrant at {host}:{port}. "
                f"Check that the Qdrant service is running and "
                f"OPENCOLAB_QDRANT_HOST / OPENCOLAB_QDRANT_PORT are correct."
            ) from e
    return _client


def _ensure_collection() -> None:
    client = _client
    collections = client.get_collections().collections
    names = [c.name for c in collections]
    if settings.qdrant_collection not in names:
        client.create_collection(
            collection_name=settings.qdrant_collection,
            vectors_config=VectorParams(size=1024, distance=Distance.COSINE),
        )
        logger.info("Created Qdrant collection: %s", settings.qdrant_collection)


def upsert_vectors(
    chunk_ids: list[str],
    embeddings: list[list[float]],
    source_ids: list[str],
) -> None:
    client = _get_client()
    points = [
        PointStruct(
            id=chunk_id,
            vector=embedding,
            payload={"source_id": source_id, "chunk_id": chunk_id},
        )
        for chunk_id, embedding, source_id in zip(chunk_ids, embeddings, source_ids)
    ]
    client.upsert(collection_name=settings.qdrant_collection, points=points)


def search_vectors(
    query_embedding: list[float],
    source_ids: list[str] | None = None,
    top_k: int | None = None,
) -> list[dict]:
    client = _get_client()
    if top_k is None:
        top_k = settings.rag_top_k

    query_filter = None
    if source_ids:
        from qdrant_client.models import FieldCondition, Filter, MatchAny

        query_filter = Filter(
            must=[FieldCondition(key="source_id", match=MatchAny(any=source_ids))]
        )

    results = client.query_points(
        collection_name=settings.qdrant_collection,
        query=query_embedding,
        query_filter=query_filter,
        limit=top_k,
    )
    return [
        {"chunk_id": point.payload["chunk_id"], "score": point.score}
        for point in results.points
    ]


def delete_vectors_by_source(source_id: str) -> None:
    client = _get_client()
    from qdrant_client.models import FieldCondition, Filter, MatchValue

    client.delete(
        collection_name=settings.qdrant_collection,
        points_selector=Filter(
            must=[FieldCondition(key="source_id", match=MatchValue(value=source_id))]
        ),
    )
