#!/usr/bin/env python3
"""Search academic papers via the OpenAlex Works API."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

import httpx


def _load_env_file_if_needed() -> None:
    """Load .env into os.environ without exposing values if key is not already set."""
    if os.environ.get("OPENCOLAB_OPENALEX_KEY"):
        return
    env_path = Path(__file__).resolve().parent.parent / ".env"
    if not env_path.is_file():
        return
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        key = key.strip()
        val = val.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = val


def search_openalex_works(
    query: str,
    *,
    limit: int = 20,
    sort: str | None = None,
) -> list[dict[str, Any]]:
    """Query OpenAlex /works endpoint using OPENCOLAB_OPENALEX_KEY from environment."""
    _load_env_file_if_needed()
    api_key = os.environ.get("OPENCOLAB_OPENALEX_KEY", "").strip()
    if not api_key:
        raise RuntimeError("OPENCOLAB_OPENALEX_KEY is not set in environment")

    params: dict[str, str | int] = {
        "search": query,
        "per-page": max(1, min(limit, 200)),
        "api_key": api_key,
    }
    if sort:
        params["sort"] = sort

    with httpx.Client(timeout=30.0) as client:
        resp = client.get("https://api.openalex.org/works", params=params)
        if resp.status_code != 200:
            raise RuntimeError(f"OpenAlex API returned HTTP {resp.status_code}")
        payload = resp.json()

    results: list[dict[str, Any]] = []
    for work in payload.get("results") or []:
        authorships = work.get("authorships") or []
        authors = [
            (a.get("author") or {}).get("display_name")
            for a in authorships
            if (a.get("author") or {}).get("display_name")
        ]
        primary_loc = work.get("primary_location") or {}
        source = primary_loc.get("source") or {}
        results.append(
            {
                "title": work.get("title") or "N/A",
                "authors": authors,
                "year": work.get("publication_year"),
                "journal": source.get("display_name") or "N/A",
                "cited_by_count": work.get("cited_by_count") or 0,
                "doi": work.get("doi") or "N/A",
            }
        )
    return results


def main() -> int:
    parser = argparse.ArgumentParser(description="Search OpenAlex papers")
    parser.add_argument("query", help="Search query string")
    parser.add_argument("--limit", type=int, default=20, help="Number of results (1-200)")
    parser.add_argument("--sort", default=None, help="Optional OpenAlex sort expression")
    parser.add_argument("--json", action="store_true", help="Output raw JSON")
    args = parser.parse_args()

    try:
        papers = search_openalex_works(args.query, limit=args.limit, sort=args.sort)
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    if args.json:
        print(json.dumps(papers, ensure_ascii=False, indent=2))
        return 0

    for idx, p in enumerate(papers, start=1):
        authors_str = ", ".join(p["authors"][:5])
        if len(p["authors"]) > 5:
            authors_str += f" (+{len(p['authors']) - 5})"
        print(f"{idx}. {p['title']}")
        print(f"   Authors: {authors_str or 'N/A'}")
        print(f"   Year: {p['year'] or 'N/A'} | Journal: {p['journal']} | Citations: {p['cited_by_count']}")
        print(f"   DOI: {p['doi']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
