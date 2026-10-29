def build_citations(chunks: list[dict]) -> list[dict]:
    return [
        {
            "source_id": chunk["source_id"],
            "chunk_id": chunk["chunk_id"],
            "snippet": chunk["text"][:280],
            "score": chunk.get("score"),
        }
        for chunk in chunks
    ]
