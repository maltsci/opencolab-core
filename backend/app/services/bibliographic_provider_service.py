from __future__ import annotations

from datetime import datetime
import re
from typing import Literal
from urllib.parse import quote
from xml.etree import ElementTree

import httpx
from pydantic import BaseModel, Field


class NormalizedIdentifier(BaseModel):
    identifier_type: Literal["doi", "pmid", "pmcid", "arxiv"]
    value: str = Field(min_length=1, max_length=255)


class ProviderRecord(BaseModel):
    provider: Literal["crossref", "pubmed", "pmc", "arxiv"]
    identifier_type: Literal["doi", "pmid", "pmcid", "arxiv"]
    identifier: str
    title: str
    authors: list[str] = Field(default_factory=list)
    container_title: str | None = None
    published_date: str | None = None
    doi: str | None = None
    pmid: str | None = None
    pmcid: str | None = None
    arxiv_id: str | None = None
    record_url: str | None = None


async def lookup_provider_record(
    identifier: NormalizedIdentifier,
    *,
    contact_email: str,
    client: httpx.AsyncClient | None = None,
) -> ProviderRecord | None:
    """Look up one exact public identifier without sending document content."""
    if identifier.identifier_type not in {"doi", "pmid", "pmcid", "arxiv"}:
        raise ValueError(f"Unsupported identifier type: {identifier.identifier_type}")

    owns_client = client is None
    active_client = client or httpx.AsyncClient(
        timeout=httpx.Timeout(10.0, connect=5.0),
        trust_env=False,
        follow_redirects=False,
        headers={"User-Agent": f"OpenColab/1.0 (mailto:{contact_email})"},
    )
    try:
        return await _lookup_with_client(
            identifier,
            contact_email=contact_email,
            client=active_client,
        )
    finally:
        if owns_client:
            await active_client.aclose()


async def _lookup_with_client(
    identifier: NormalizedIdentifier,
    *,
    contact_email: str,
    client: httpx.AsyncClient,
) -> ProviderRecord | None:
    if identifier.identifier_type == "doi":
        response = await client.get(
            f"https://api.crossref.org/works/{quote(identifier.value, safe='')}",
            params={"mailto": contact_email},
        )
        if response.status_code == 404:
            return None
        response.raise_for_status()
        return _parse_crossref_record(identifier, response.json())

    if identifier.identifier_type == "pmid":
        response = await client.get(
            "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi",
            params={
                "db": "pubmed",
                "id": identifier.value,
                "retmode": "json",
                "tool": "OpenColab",
                "email": contact_email,
            },
        )
        if response.status_code == 404:
            return None
        response.raise_for_status()
        return _parse_pubmed_record(identifier, response.json())

    if identifier.identifier_type == "pmcid":
        return await _lookup_pmcid_record(
            identifier,
            contact_email=contact_email,
            client=client,
        )
    return await _lookup_arxiv_record(identifier, client=client)


async def _lookup_pmcid_record(
    identifier: NormalizedIdentifier,
    *,
    contact_email: str,
    client: httpx.AsyncClient,
) -> ProviderRecord | None:
    response = await client.get(
        "https://www.ncbi.nlm.nih.gov/pmc/utils/idconv/v1.0/",
        params={
            "ids": identifier.value,
            "format": "json",
            "tool": "OpenColab",
            "email": contact_email,
        },
    )
    if response.status_code == 404:
        return None
    response.raise_for_status()
    records = response.json().get("records")
    if not isinstance(records, list) or len(records) != 1:
        return None
    mapping = records[0]
    if not isinstance(mapping, dict):
        return None
    returned_pmcid = str(mapping.get("pmcid") or "").upper()
    if returned_pmcid != identifier.value.upper():
        raise ValueError("PMC response identifier does not match request")

    pmid = _first_string(mapping.get("pmid"))
    doi = _first_string(mapping.get("doi"))
    if pmid:
        record = await _lookup_with_client(
            NormalizedIdentifier(identifier_type="pmid", value=pmid),
            contact_email=contact_email,
            client=client,
        )
    elif doi:
        record = await _lookup_with_client(
            NormalizedIdentifier(identifier_type="doi", value=doi.lower()),
            contact_email=contact_email,
            client=client,
        )
    else:
        return None
    if record is None:
        return None
    return record.model_copy(
        update={
            "identifier_type": "pmcid",
            "identifier": returned_pmcid,
            "pmcid": returned_pmcid,
            "pmid": pmid or record.pmid,
            "doi": doi.lower() if doi else record.doi,
        }
    )


async def _lookup_arxiv_record(
    identifier: NormalizedIdentifier,
    *,
    client: httpx.AsyncClient,
) -> ProviderRecord | None:
    base_identifier = re.sub(r"v\d+$", "", identifier.value, flags=re.IGNORECASE)
    response = await client.get(
        "https://export.arxiv.org/api/query",
        params={"id_list": base_identifier},
    )
    if response.status_code == 404:
        return None
    response.raise_for_status()
    if len(response.content) > 1_000_000:
        raise ValueError("arXiv response exceeds size limit")
    try:
        root = ElementTree.fromstring(response.content)
    except ElementTree.ParseError as exc:
        raise ValueError("Invalid arXiv Atom response") from exc

    namespace = {"atom": "http://www.w3.org/2005/Atom"}
    entries = root.findall("atom:entry", namespace)
    if len(entries) != 1:
        return None
    entry = entries[0]
    returned_url = _element_text(entry.find("atom:id", namespace))
    returned_identifier = re.sub(
        r"v\d+$",
        "",
        returned_url.rsplit("/", 1)[-1],
        flags=re.IGNORECASE,
    )
    if returned_identifier.lower() != base_identifier.lower():
        raise ValueError("arXiv response identifier does not match request")
    title = _element_text(entry.find("atom:title", namespace))
    if not title:
        return None
    authors = [
        name
        for author in entry.findall("atom:author", namespace)
        if (name := _element_text(author.find("atom:name", namespace)))
    ]
    published = _element_text(entry.find("atom:published", namespace))
    return ProviderRecord(
        provider="arxiv",
        identifier_type="arxiv",
        identifier=base_identifier.lower(),
        title=title,
        authors=authors,
        published_date=published[:10] if len(published) >= 10 else None,
        arxiv_id=base_identifier.lower(),
        record_url=f"https://arxiv.org/abs/{base_identifier.lower()}",
    )


def _element_text(element: ElementTree.Element | None) -> str:
    if element is None or not element.text:
        return ""
    return " ".join(element.text.split())


def _parse_crossref_record(
    identifier: NormalizedIdentifier,
    payload: dict,
) -> ProviderRecord | None:
    message = payload.get("message")
    if not isinstance(message, dict):
        raise ValueError("Crossref response is missing message")

    returned_doi = _first_string(message.get("DOI"))
    title = _first_string(message.get("title"))
    if not returned_doi or returned_doi.lower() != identifier.value.lower():
        raise ValueError("Crossref response identifier does not match request")
    if not title:
        return None

    authors: list[str] = []
    raw_authors = message.get("author")
    if isinstance(raw_authors, list):
        for raw_author in raw_authors:
            if not isinstance(raw_author, dict):
                continue
            name = " ".join(
                part.strip()
                for part in (
                    str(raw_author.get("given") or ""),
                    str(raw_author.get("family") or ""),
                )
                if part.strip()
            )
            if name:
                authors.append(name)

    normalized_doi = returned_doi.lower()
    return ProviderRecord(
        provider="crossref",
        identifier_type="doi",
        identifier=normalized_doi,
        title=title,
        authors=authors,
        container_title=_first_string(message.get("container-title")),
        published_date=_crossref_date(message),
        doi=normalized_doi,
        record_url=f"https://doi.org/{normalized_doi}",
    )


def _parse_pubmed_record(
    identifier: NormalizedIdentifier,
    payload: dict,
) -> ProviderRecord | None:
    result = payload.get("result")
    if not isinstance(result, dict):
        raise ValueError("PubMed response is missing result")
    record = result.get(identifier.value)
    if not isinstance(record, dict):
        return None
    if str(record.get("uid") or "") != identifier.value:
        raise ValueError("PubMed response identifier does not match request")

    title = _first_string(record.get("title"))
    if not title:
        return None
    authors: list[str] = []
    raw_authors = record.get("authors")
    if isinstance(raw_authors, list):
        for raw_author in raw_authors:
            if not isinstance(raw_author, dict):
                continue
            name = _first_string(raw_author.get("name"))
            if name:
                authors.append(name)

    doi = None
    pmcid = None
    article_ids = record.get("articleids")
    if isinstance(article_ids, list):
        for raw_identifier in article_ids:
            if not isinstance(raw_identifier, dict):
                continue
            identifier_type = str(raw_identifier.get("idtype") or "").lower()
            value = _first_string(raw_identifier.get("value"))
            if identifier_type == "doi" and value:
                doi = value.lower()
            elif identifier_type in {"pmc", "pmcid"} and value:
                pmcid = value.upper()

    return ProviderRecord(
        provider="pubmed",
        identifier_type="pmid",
        identifier=identifier.value,
        title=title,
        authors=authors,
        container_title=_first_string(record.get("fulljournalname")),
        published_date=_parse_pubmed_date(record.get("pubdate")),
        doi=doi,
        pmid=identifier.value,
        pmcid=pmcid,
        record_url=f"https://pubmed.ncbi.nlm.nih.gov/{identifier.value}/",
    )


def _first_string(value: object) -> str | None:
    if isinstance(value, str):
        normalized = " ".join(value.split())
        return normalized or None
    if isinstance(value, list) and value and isinstance(value[0], str):
        normalized = " ".join(value[0].split())
        return normalized or None
    return None


def _crossref_date(message: dict) -> str | None:
    for key in ("published", "published-print", "published-online", "issued"):
        date_container = message.get(key)
        if not isinstance(date_container, dict):
            continue
        date_parts = date_container.get("date-parts")
        if not isinstance(date_parts, list) or not date_parts:
            continue
        parts = date_parts[0]
        if not isinstance(parts, list) or not parts:
            continue
        try:
            year = int(parts[0])
            month = int(parts[1]) if len(parts) > 1 else 1
            day = int(parts[2]) if len(parts) > 2 else 1
        except (TypeError, ValueError):
            continue
        return f"{year:04d}-{month:02d}-{day:02d}"
    return None


def _parse_pubmed_date(value: object) -> str | None:
    raw_value = _first_string(value)
    if not raw_value:
        return None
    for date_format in ("%Y %b %d", "%Y %b", "%Y"):
        try:
            parsed = datetime.strptime(raw_value, date_format)
        except ValueError:
            continue
        if date_format == "%Y":
            return f"{parsed.year:04d}"
        if date_format == "%Y %b":
            return f"{parsed.year:04d}-{parsed.month:02d}"
        return parsed.date().isoformat()
    return None
