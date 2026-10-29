from typing import Any, NotRequired, TypedDict

from app.services.agents.base import AgentTracePayload, is_chinese_locale

from app.services.citation_service import build_citations

TRACE_RETRIEVAL_SNIPPET_LIMIT = 220


class TraceRetrievedChunk(TypedDict):
    source_id: str
    chunk_id: str
    text: str
    score: NotRequired[float | None]


def _build_retrieval_snippet(text: str, limit: int = TRACE_RETRIEVAL_SNIPPET_LIMIT) -> str:
    cleaned = " ".join(text.split())
    if len(cleaned) <= limit:
        return cleaned
    return cleaned[:limit].rstrip() + "..."


def build_trace_payload(
    query: str,
    source_ids: list[str],
    retrieved_chunks: list[TraceRetrievedChunk],
    locale: str | None = None,
) -> AgentTracePayload:
    citations = build_citations(retrieved_chunks)
    if is_chinese_locale(locale):
        summary_steps = [
            f"已选择 {len(source_ids)} 份文档",
            f"已检索到 {len(retrieved_chunks)} 个相关片段",
            f"已生成答案并附带 {len(citations)} 条引用",
        ]
    else:
        summary_steps = [
            f"selected {len(source_ids)} documents",
            f"retrieved {len(retrieved_chunks)} relevant chunks",
            f"generated answer with {len(citations)} citations",
        ]
    return build_agent_trace_payload(
        inputs={"query": query, "source_ids": source_ids},
        retrieved_chunks=retrieved_chunks,
        summary_steps=summary_steps,
        citations=citations,
    )


def build_agent_trace_payload(
    *,
    inputs: dict[str, Any],
    retrieved_chunks: list[TraceRetrievedChunk],
    summary_steps: list[str],
    citations: list[dict] | None = None,
) -> AgentTracePayload:
    resolved_citations = citations if citations is not None else build_citations(retrieved_chunks)
    return {
        "inputs": inputs,
        "retrieval": [
            {
                "source_id": chunk["source_id"],
                "chunk_id": chunk["chunk_id"],
                "score": chunk.get("score"),
                "snippet": _build_retrieval_snippet(chunk.get("text", "")),
            }
            for chunk in retrieved_chunks
        ],
        "citations": resolved_citations,
        "summary_steps": summary_steps,
    }
