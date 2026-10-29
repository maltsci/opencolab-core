# Lab Knowledge OS v1 Security Contract

## Protected data and trust boundaries

Research asset content, protected metadata, access policies, source chunks, and
derived records inherit the authorization requirements of their source asset.
PostgreSQL access-policy records are the authorization authority. API callers,
RAG orchestration, Qdrant, caches, and LLM providers are outside that authority
boundary and must not independently grant access.

## Request-time authorization sequence

Every request that discovers an asset, retrieves content, or sends content to an
agent evaluates the current PostgreSQL policy before returning protected data.
RAG evaluates source access before retrieval and evaluates each returned
candidate asset again immediately before exposing chunk text. A denied asset is
omitted from the response.

## Qdrant is an untrusted candidate index

Qdrant search results are candidates only. Vector metadata and ranking do not
authorize content access. The application maps each candidate source to its
ResearchAsset and filters it through `authorize_asset` at request time while
preserving the vector result order of allowed items.

## Permission revocation and cache invalidation

An enabled policy may be revoked or disabled at any time. The next request must
evaluate the changed policy without reindexing Qdrant and must not return the
revoked content. Permission-result caching is prohibited until a versioned
invalidation design has passed security review. Retrieval-score caching must not
be used to bypass the request-time authorization filter.

## Derived records and safe summaries

Derived records may expose only fields that the caller is authorized to view.
Metadata-only fallbacks must not include raw source content, protected metadata,
or extracted snippets. Local adoption events may record aggregate counters and
authorization-safe identifiers, but exclude raw query text and generated answer
text.

## LLM egress rules

Only chunks that passed the request-time `CONTENT_USE_IN_AGENT` authorization
check may be included in an LLM prompt. Raw PDFs and source files never leave
the local machine. In hybrid mode, only authorized pre-processed text segments
may be sent to a cloud LLM after the user has explicitly opted in.

## Required automated abuse cases

- A vector candidate with no current policy grant returns no chunk or snippet.
- Disabling a grant after an earlier successful query removes that candidate from
  the next identical query without any Qdrant update.
- An explicit deny overrides an otherwise matching grant.
- A source without a governed ResearchAsset is never used as agent content.
- Metadata-only fallback never contains source chunk text.

## Phase 1 entry checklist

- Request-time authorization tests cover discovery, content preview, download,
  and agent use capabilities.
- RAG regression tests cover revocation with unchanged vector candidates.
- Any proposed authorization cache has a documented policy-version key,
  invalidation trigger, bounded lifetime, and security review approval.
- Evaluation fixtures and logs do not commit private benchmark questions, raw
  user queries, or generated answers.
