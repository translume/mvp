"""Bounded public-literature retrieval with explicit, non-scientific failures."""

from __future__ import annotations

import hashlib
import re
import time
from dataclasses import dataclass
from html.parser import HTMLParser
from typing import Any

import httpx
from translume_schemas.medea import MedeaLiteratureSearch, MedeaSourceReference

from medea_service.vendor_runtime import VendorRuntimeError


@dataclass(frozen=True)
class LiteraturePaper:
    """One actual publication record with nonempty retrieved abstract text."""

    source_id: str
    provider: str
    title: str
    abstract: str
    url: str
    year: str | None = None
    doi: str | None = None
    pmid: str | None = None
    citation_count: int = 0

    def context(self) -> dict[str, Any]:
        """Return the exact fields accepted by upstream OpenScholar."""
        return {
            "paperId": self.source_id,
            "title": self.title,
            "text": self.abstract,
            "abstract": self.abstract,
            "year": self.year,
            "url": self.url,
            "citation_counts": self.citation_count,
            "citationCount": self.citation_count,
        }

    def reference(self, index: int) -> MedeaSourceReference:
        return MedeaSourceReference(
            citation_index=index,
            source_id=self.source_id,
            provider=self.provider,
            title=self.title,
            url=self.url,
            year=self.year,
            doi=self.doi,
            pmid=self.pmid,
            abstract_sha256=hashlib.sha256(self.abstract.encode()).hexdigest(),
        )


@dataclass(frozen=True)
class LiteratureSearchResult:
    papers: tuple[LiteraturePaper, ...]
    searches: tuple[MedeaLiteratureSearch, ...]


class LiteratureSourceError(VendorRuntimeError):
    """A data source failed; this must never be labelled absence of evidence."""

    def __init__(self, code: str):
        self.code = code
        super().__init__(f"literature source request failed ({code})")


def search_queries(disease: str | None, genes: tuple[str, ...]) -> tuple[str, ...]:
    """Build bounded, diagnosis/gene-only queries without transmitting case data.

    Acceptance criteria:
        1. Retain query order and distinct source-derived gene symbols.
        2. Do not send report text, patient identifiers, specimen data or dates.
        3. Quote database syntax characters in disease labels.
        4. Return a clearly bounded set of searches, not an exhaustive-search claim.
    """
    disease_text = re.sub(r"[^\w\s-]", " ", disease or "").strip()
    disease_text = " ".join(disease_text.split())[:200]
    valid_genes = tuple(
        dict.fromkeys(
            gene for gene in genes if re.fullmatch(r"[A-Z0-9][A-Z0-9.-]{0,29}", gene)
        )
    )
    if not disease_text and not valid_genes:
        raise VendorRuntimeError(
            "Medea needs a source-derived disease or gene for literature search"
        )
    condition = f'"{disease_text}"' if disease_text else "cancer"
    queries = [
        f"{condition} AND ({' OR '.join(valid_genes[start : start + 3])})"
        for start in range(0, min(len(valid_genes), 12), 3)
    ]
    return tuple(queries or [condition])


class PublicLiteratureSearch:
    """Call real public source APIs without requiring another paid API key."""

    def __init__(self, client: httpx.Client, *, max_papers: int = 16) -> None:
        if not 1 <= max_papers <= 100:
            raise ValueError("max_papers must be between 1 and 100")
        self._client = client
        self._max_papers = max_papers

    def search(self, queries: tuple[str, ...]) -> LiteratureSearchResult:
        """Retrieve abstracts, preserving genuine zero hits and source errors.

        Acceptance criteria:
            1. Every source call has bounded timeout and retry behavior.
            2. At least one successful query is required; all-failed raises.
            3. Papers lacking abstract text are not invented or synthesized.
            4. Deduplicate by DOI, PMID, then source identity.
        """
        papers: dict[str, LiteraturePaper] = {}
        searches: list[MedeaLiteratureSearch] = []
        for query in queries:
            for provider, search in (
                ("EuropePMC", self._europe_pmc),
                ("SemanticScholar", self._semantic_scholar),
            ):
                try:
                    found, hit_count = search(query)
                    searches.append(
                        MedeaLiteratureSearch(
                            provider=provider,
                            query=query,
                            status="succeeded",
                            returned_count=len(found),
                            hit_count=hit_count,
                        )
                    )
                except LiteratureSourceError as error:
                    searches.append(
                        MedeaLiteratureSearch(
                            provider=provider,
                            query=query,
                            status="unavailable",
                            returned_count=0,
                            error_code=error.code,
                        )
                    )
                    continue
                for paper in found:
                    key = (paper.doi or paper.pmid or paper.source_id).casefold()
                    if key not in papers and len(papers) < self._max_papers:
                        papers[key] = paper
        if not any(item.status == "succeeded" for item in searches):
            raise LiteratureSourceError("all_sources_unavailable")
        return LiteratureSearchResult(tuple(papers.values()), tuple(searches))

    def _europe_pmc(self, query: str) -> tuple[list[LiteraturePaper], int]:
        data = self._get_json(
            "https://www.ebi.ac.uk/europepmc/webservices/rest/search",
            {"query": query, "format": "json", "resultType": "core", "pageSize": 8},
        )
        if (
            data.get("errCode")
            or type(data.get("hitCount")) is not int
            or data["hitCount"] < 0
        ):
            raise LiteratureSourceError("europe_pmc_invalid_response")
        result_list = data.get("resultList")
        if not isinstance(result_list, dict):
            raise LiteratureSourceError("europe_pmc_missing_results")
        rows = result_list.get("result")
        if not isinstance(rows, list):
            raise LiteratureSourceError("europe_pmc_missing_results")
        papers = []
        for row in rows:
            if not isinstance(row, dict):
                raise LiteratureSourceError("europe_pmc_invalid_record")
            identifier, source = row.get("id"), row.get("source")
            title = _plain_text(row.get("title"))
            abstract = _plain_text(row.get("abstractText"))
            if not title or not abstract:
                continue
            if not all(
                isinstance(value, str) and re.fullmatch(r"[A-Za-z0-9._-]+", value)
                for value in (source, identifier)
            ):
                raise LiteratureSourceError("europe_pmc_invalid_identifier")
            papers.append(
                LiteraturePaper(
                    source_id=f"epmc:{source}:{identifier}",
                    provider="EuropePMC",
                    title=title,
                    abstract=abstract,
                    url=f"https://europepmc.org/article/{source}/{identifier}",
                    year=_optional_string(row.get("pubYear")),
                    doi=_optional_string(row.get("doi")),
                    pmid=identifier
                    if source == "MED"
                    else _optional_string(row.get("pmid")),
                    citation_count=_citation_count(row.get("citedByCount")),
                )
            )
        return papers, data["hitCount"]

    def _semantic_scholar(self, query: str) -> tuple[list[LiteraturePaper], int]:
        data = self._get_json(
            "https://api.semanticscholar.org/graph/v1/paper/search",
            {
                "query": query,
                "limit": 8,
                "fields": "title,year,abstract,url,externalIds,citationCount",
            },
        )
        if (
            not isinstance(data.get("data"), list)
            or type(data.get("total")) is not int
            or data["total"] < 0
        ):
            raise LiteratureSourceError("semantic_scholar_invalid_response")
        papers = []
        for row in data["data"]:
            if not isinstance(row, dict):
                raise LiteratureSourceError("semantic_scholar_invalid_record")
            title, abstract = (
                _plain_text(row.get("title")),
                _plain_text(row.get("abstract")),
            )
            if not title or not abstract:
                continue
            identifier = row.get("paperId")
            if not isinstance(identifier, str) or not re.fullmatch(
                r"[A-Za-z0-9-]+", identifier
            ):
                raise LiteratureSourceError("semantic_scholar_invalid_identifier")
            external = row.get("externalIds") or {}
            if not isinstance(external, dict):
                raise LiteratureSourceError("semantic_scholar_invalid_identifiers")
            papers.append(
                LiteraturePaper(
                    source_id=f"s2:{identifier}",
                    provider="SemanticScholar",
                    title=title,
                    abstract=abstract,
                    url=f"https://www.semanticscholar.org/paper/{identifier}",
                    year=_optional_string(row.get("year")),
                    doi=_optional_string(external.get("DOI")),
                    pmid=_optional_string(external.get("PubMed")),
                    citation_count=_citation_count(row.get("citationCount")),
                )
            )
        return papers, data["total"]

    def _get_json(self, url: str, params: dict[str, Any]) -> dict[str, Any]:
        for attempt in range(3):
            try:
                response = self._client.get(url, params=params, timeout=30.0)
            except (httpx.TimeoutException, httpx.NetworkError) as error:
                if attempt == 2:
                    raise LiteratureSourceError("network_or_timeout") from error
                time.sleep(2**attempt)
                continue
            if (
                response.status_code == 429 or response.status_code >= 500
            ) and attempt < 2:
                time.sleep(2**attempt)
                continue
            if response.status_code != 200:
                raise LiteratureSourceError(f"http_{response.status_code}")
            try:
                payload = response.json()
            except ValueError as error:
                raise LiteratureSourceError("invalid_json") from error
            if not isinstance(payload, dict):
                raise LiteratureSourceError("invalid_shape")
            return payload
        raise LiteratureSourceError("retry_exhausted")


class _HTMLText(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []

    def handle_data(self, data: str) -> None:
        self.parts.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() in {"p", "div", "br", "section", "title"}:
            self.parts.append(" ")


def _plain_text(value: Any) -> str:
    if not isinstance(value, str):
        return ""
    parser = _HTMLText()
    parser.feed(value)
    return " ".join("".join(parser.parts).split())


def _optional_string(value: Any) -> str | None:
    return (
        str(value).strip()
        if isinstance(value, (str, int)) and str(value).strip()
        else None
    )


def _citation_count(value: Any) -> int:
    if value is None:
        return 0
    if not isinstance(value, (int, str)) or not str(value).isdigit():
        raise LiteratureSourceError("invalid_citation_count")
    return int(value)
