import httpx
import pytest
from sqlalchemy import select

from app.models.research_asset import ResearchAsset
from app.models.source import Source
from app.models.trace import SourceExtraction
from app.services.bibliographic_metadata_service import (
    apply_provider_record,
    enrich_bibliographic_metadata,
    lookup_provider_record_cached,
)
from app.services.bibliographic_provider_service import (
    NormalizedIdentifier,
    lookup_provider_record,
)


@pytest.mark.asyncio
async def test_crossref_lookup_sends_only_exact_doi_and_returns_whitelisted_record():
    seen_request: httpx.Request | None = None

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal seen_request
        seen_request = request
        return httpx.Response(
            200,
            json={
                "message": {
                    "DOI": "10.5555/3295222.3295349",
                    "title": ["Attention Is All You Need"],
                    "author": [
                        {"given": "Ashish", "family": "Vaswani"},
                        {"given": "Noam", "family": "Shazeer"},
                    ],
                    "container-title": [
                        "Advances in Neural Information Processing Systems"
                    ],
                    "published": {"date-parts": [[2017, 12, 4]]},
                    "abstract": "This field must not be persisted.",
                }
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        record = await lookup_provider_record(
            NormalizedIdentifier(
                identifier_type="doi",
                value="10.5555/3295222.3295349",
            ),
            contact_email="metadata@example.org",
            client=client,
        )

    assert seen_request is not None
    assert str(seen_request.url).startswith(
        "https://api.crossref.org/works/10.5555%2F3295222.3295349?"
    )
    assert dict(seen_request.url.params) == {"mailto": "metadata@example.org"}
    assert record is not None
    assert record.model_dump(exclude_none=True) == {
        "provider": "crossref",
        "identifier_type": "doi",
        "identifier": "10.5555/3295222.3295349",
        "title": "Attention Is All You Need",
        "authors": ["Ashish Vaswani", "Noam Shazeer"],
        "container_title": "Advances in Neural Information Processing Systems",
        "published_date": "2017-12-04",
        "doi": "10.5555/3295222.3295349",
        "record_url": "https://doi.org/10.5555/3295222.3295349",
    }


@pytest.mark.asyncio
async def test_pubmed_lookup_returns_cross_identifiers_without_abstract():
    seen_request: httpx.Request | None = None

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal seen_request
        seen_request = request
        return httpx.Response(
            200,
            json={
                "result": {
                    "uids": ["12345678"],
                    "12345678": {
                        "uid": "12345678",
                        "title": "A biomedical paper.",
                        "authors": [{"name": "Doe J"}, {"name": "Smith A"}],
                        "fulljournalname": "Journal of Test Medicine",
                        "pubdate": "2025 Jan 15",
                        "articleids": [
                            {"idtype": "doi", "value": "10.1000/test-paper"},
                            {"idtype": "pmc", "value": "PMC7654321"},
                        ],
                        "abstract": "Must not leave the adapter.",
                    },
                }
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        record = await lookup_provider_record(
            NormalizedIdentifier(identifier_type="pmid", value="12345678"),
            contact_email="metadata@example.org",
            client=client,
        )

    assert seen_request is not None
    assert seen_request.url.host == "eutils.ncbi.nlm.nih.gov"
    assert dict(seen_request.url.params) == {
        "db": "pubmed",
        "id": "12345678",
        "retmode": "json",
        "tool": "OpenColab",
        "email": "metadata@example.org",
    }
    assert record is not None
    assert record.model_dump(exclude_none=True) == {
        "provider": "pubmed",
        "identifier_type": "pmid",
        "identifier": "12345678",
        "title": "A biomedical paper.",
        "authors": ["Doe J", "Smith A"],
        "container_title": "Journal of Test Medicine",
        "published_date": "2025-01-15",
        "doi": "10.1000/test-paper",
        "pmid": "12345678",
        "pmcid": "PMC7654321",
        "record_url": "https://pubmed.ncbi.nlm.nih.gov/12345678/",
    }


@pytest.mark.asyncio
async def test_pmcid_lookup_converts_to_pubmed_before_fetching_metadata():
    seen_hosts: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen_hosts.append(request.url.host)
        if request.url.host == "www.ncbi.nlm.nih.gov":
            return httpx.Response(
                200,
                json={
                    "records": [
                        {
                            "pmcid": "PMC7654321",
                            "pmid": "12345678",
                            "doi": "10.1000/test-paper",
                        }
                    ]
                },
            )
        return httpx.Response(
            200,
            json={
                "result": {
                    "uids": ["12345678"],
                    "12345678": {
                        "uid": "12345678",
                        "title": "A biomedical paper.",
                        "authors": [],
                        "fulljournalname": "Journal of Test Medicine",
                        "pubdate": "2025",
                        "articleids": [],
                    },
                }
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        record = await lookup_provider_record(
            NormalizedIdentifier(identifier_type="pmcid", value="PMC7654321"),
            contact_email="metadata@example.org",
            client=client,
        )

    assert seen_hosts == ["www.ncbi.nlm.nih.gov", "eutils.ncbi.nlm.nih.gov"]
    assert record is not None
    assert record.identifier_type == "pmcid"
    assert record.identifier == "PMC7654321"
    assert record.pmid == "12345678"
    assert record.pmcid == "PMC7654321"
    assert record.doi == "10.1000/test-paper"


@pytest.mark.asyncio
async def test_arxiv_lookup_uses_exact_id_list_and_parses_atom_record():
    seen_request: httpx.Request | None = None

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal seen_request
        seen_request = request
        return httpx.Response(
            200,
            text="""<?xml version="1.0" encoding="UTF-8"?>
            <feed xmlns="http://www.w3.org/2005/Atom">
              <entry>
                <id>http://arxiv.org/abs/2401.12345v2</id>
                <updated>2025-01-15T10:00:00Z</updated>
                <published>2024-01-20T10:00:00Z</published>
                <title>  A Reliable Preprint Title  </title>
                <author><name>Alice Example</name></author>
                <author><name>Bob Example</name></author>
              </entry>
            </feed>""",
            headers={"content-type": "application/atom+xml"},
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        record = await lookup_provider_record(
            NormalizedIdentifier(identifier_type="arxiv", value="2401.12345v2"),
            contact_email="metadata@example.org",
            client=client,
        )

    assert seen_request is not None
    assert seen_request.url.host == "export.arxiv.org"
    assert dict(seen_request.url.params) == {"id_list": "2401.12345"}
    assert record is not None
    assert record.model_dump(exclude_none=True) == {
        "provider": "arxiv",
        "identifier_type": "arxiv",
        "identifier": "2401.12345",
        "title": "A Reliable Preprint Title",
        "authors": ["Alice Example", "Bob Example"],
        "published_date": "2024-01-20",
        "arxiv_id": "2401.12345",
        "record_url": "https://arxiv.org/abs/2401.12345",
    }


def test_automatic_metadata_never_overwrites_a_locked_title():
    asset = ResearchAsset(
        asset_type="uploaded_file",
        title="Curator approved title",
        title_source="manual",
        title_locked=True,
        catalog_metadata_json={"title": "Curator approved title"},
        visibility_scope="lab_public",
    )
    record = {
        "provider": "crossref",
        "identifier_type": "doi",
        "identifier": "10.1000/test-paper",
        "title": "Provider title",
        "authors": ["Alice Example"],
        "doi": "10.1000/test-paper",
        "record_url": "https://doi.org/10.1000/test-paper",
    }

    applied = apply_provider_record(asset, record, automatic=True)

    assert applied is False
    assert asset.title == "Curator approved title"
    assert asset.title_source == "manual"
    assert asset.catalog_metadata_json["title"] == "Curator approved title"
    assert asset.catalog_metadata_json["bibliographic"]["source"] == "crossref"
    assert asset.catalog_metadata_json["bibliographic"]["doi"] == "10.1000/test-paper"


def test_provider_metadata_preserves_locally_extracted_topic_keywords():
    asset = ResearchAsset(
        asset_type="uploaded_file",
        title="Local title",
        title_source="parsed_heading",
        catalog_metadata_json={
            "title": "Local title",
            "bibliographic": {
                "keywords": ["mycoplasma pneumoniae", "antimicrobial peptides"]
            },
        },
        visibility_scope="lab_public",
    )
    record = {
        "provider": "crossref",
        "identifier_type": "doi",
        "identifier": "10.1000/test-paper",
        "title": "Provider title",
        "authors": ["Alice Example"],
        "doi": "10.1000/test-paper",
        "record_url": "https://doi.org/10.1000/test-paper",
    }

    apply_provider_record(asset, record, automatic=True)

    assert asset.catalog_metadata_json["bibliographic"]["keywords"] == [
        "mycoplasma pneumoniae",
        "antimicrobial peptides",
    ]


@pytest.mark.asyncio
async def test_enrichment_updates_title_without_blocking_ready_source(db):
    source = Source(
        type="file",
        name="download_123.pdf",
        processing_state="ready",
        progress=100,
    )
    db.add(source)
    await db.flush()
    asset = ResearchAsset(
        asset_type="uploaded_file",
        title=source.name,
        source_id=source.id,
        catalog_metadata_json={"title": source.name},
        visibility_scope="lab_public",
    )
    extraction = SourceExtraction(
        source_id=source.id,
        status="ready",
        document_type="paper",
        schema_version="v1",
        metadata_status="pending",
        structured_json={
            "title": "A Reliable Paper Title",
            "bibliographic": {
                "local_title_candidate": {
                    "value": "A Reliable Paper Title",
                    "source": "parsed_text",
                    "confidence": "medium",
                },
                "identifier_candidates": [
                    {
                        "identifier_type": "doi",
                        "value": "10.1000/reliable-paper",
                        "source": "front_matter",
                        "confidence": "high",
                        "eligible_for_lookup": True,
                    }
                ],
                "provider_candidates": [],
                "resolution": {"status": "pending", "reason_codes": []},
            },
        },
    )
    db.add_all([asset, extraction])
    await db.commit()

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "message": {
                    "DOI": "10.1000/reliable-paper",
                    "title": ["A Reliable Paper Title"],
                    "author": [{"given": "Alice", "family": "Example"}],
                    "container-title": ["Journal of Reliable Tests"],
                    "published": {"date-parts": [[2026, 9, 1]]},
                }
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        status = await enrich_bibliographic_metadata(
            db,
            source_id=source.id,
            contact_email="metadata@example.org",
            auto_apply=True,
            client=client,
        )
    await db.commit()

    reloaded_source = await db.get(Source, source.id)
    reloaded_asset = await db.scalar(
        select(ResearchAsset).where(ResearchAsset.source_id == source.id)
    )
    reloaded_extraction = await db.scalar(
        select(SourceExtraction).where(SourceExtraction.source_id == source.id)
    )
    assert status == "resolved"
    assert reloaded_source is not None
    assert reloaded_source.processing_state == "ready"
    assert reloaded_asset is not None
    assert reloaded_asset.title == "A Reliable Paper Title"
    assert reloaded_asset.title_source == "crossref"
    assert reloaded_extraction is not None
    assert reloaded_extraction.metadata_status == "resolved"
    provider_candidate = reloaded_extraction.structured_json["bibliographic"][
        "provider_candidates"
    ][0]
    assert provider_candidate["doi"] == "10.1000/reliable-paper"
    assert "abstract" not in provider_candidate


@pytest.mark.asyncio
async def test_provider_lookup_reuses_database_cache(db):
    call_count = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal call_count
        call_count += 1
        return httpx.Response(
            200,
            json={
                "message": {
                    "DOI": "10.1000/cached-paper",
                    "title": ["Cached Paper"],
                    "author": [],
                }
            },
        )

    identifier = NormalizedIdentifier(
        identifier_type="doi",
        value="10.1000/cached-paper",
    )
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        first = await lookup_provider_record_cached(
            db,
            identifier=identifier,
            contact_email="metadata@example.org",
            client=client,
        )
        await db.commit()
        second = await lookup_provider_record_cached(
            db,
            identifier=identifier,
            contact_email="metadata@example.org",
            client=client,
        )

    assert call_count == 1
    assert first is not None
    assert second == first
