from app.core.config import settings


def chunk_text(
    text: str,
    chunk_size: int | None = None,
    chunk_overlap: int | None = None,
) -> list[str]:
    """Split text into overlapping chunks by paragraph, falling back to fixed size."""
    if chunk_size is None:
        chunk_size = settings.chunk_size
    if chunk_overlap is None:
        chunk_overlap = settings.chunk_overlap

    # Try paragraph-based splitting first
    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]

    if not paragraphs:
        return _fixed_size_chunks(text, chunk_size, chunk_overlap)

    chunks = []
    current_chunk = ""

    for para in paragraphs:
        if len(current_chunk) + len(para) + 2 > chunk_size and current_chunk:
            chunks.append(current_chunk.strip())
            # Keep overlap from the end of current chunk
            overlap_text = current_chunk[-chunk_overlap:] if chunk_overlap > 0 else ""
            current_chunk = overlap_text + "\n\n" + para
        else:
            current_chunk = (
                current_chunk + "\n\n" + para if current_chunk else para
            )

    if current_chunk.strip():
        chunks.append(current_chunk.strip())

    # If paragraphs are too long, split them further
    result = []
    for chunk in chunks:
        if len(chunk) > chunk_size * 2:
            result.extend(_fixed_size_chunks(chunk, chunk_size, chunk_overlap))
        else:
            result.append(chunk)

    return result


def _fixed_size_chunks(text: str, chunk_size: int, chunk_overlap: int) -> list[str]:
    chunks = []
    start = 0
    while start < len(text):
        end = start + chunk_size
        chunks.append(text[start:end].strip())
        start = end - chunk_overlap
    return [c for c in chunks if c]
