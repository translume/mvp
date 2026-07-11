#!/usr/bin/env python3
"""
Precision Oncology JSON Pipeline
================================

A production-oriented, resumable Python CLI that:

1. Parses a Translume-style review packet JSON.
2. Builds a compact canonical case input from actionable clinical data.
3. Calls the OpenAI Responses API with Structured Outputs.
4. Uses the hosted web_search tool to discover and inspect fully qualified URLs.
5. Produces a deterministic, renderer-independent JSON representation of the
   same content types and section flow as the 31-page Precision Oncology
   Actionable Packet used to define this workflow.

The design deliberately separates pure transformations from side effects:

- Pure functions: parsing, normalization, deterministic IDs, joins, ranking,
  section assembly, validation, and prompt-variable construction.
- Side effects: OpenAI API calls and atomic filesystem persistence.

This software is educational decision support. It is not a medical device,
does not determine treatment, and does not establish clinical-trial eligibility.
All output must be reviewed by qualified clinicians.
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# STANDARD LIBRARY IMPORTS
# ---------------------------------------------------------------------------
import argparse
import asyncio
import copy
import dataclasses
import datetime as dt
import hashlib
import json
import logging
import os
import random
import re
import tempfile
import time
from collections import defaultdict
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Generic, Literal, TypeVar, cast
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

# ---------------------------------------------------------------------------
# THIRD-PARTY IMPORTS
# ---------------------------------------------------------------------------

try:
    from pydantic import BaseModel, ConfigDict, Field, ValidationError
except ImportError as exc:  # pragma: no cover - dependency failure is explicit
    raise SystemExit(
        "Missing dependency 'pydantic>=2.10'. Install requirements.txt first."
    ) from exc


# ---------------------------------------------------------------------------
# GLOBAL OPENAI CONFIGURATION
# ---------------------------------------------------------------------------
# The API key is intentionally loaded from an environment variable. For a
# one-off local test you may replace the empty fallback with a literal key, but
# never commit or log a real key.
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")

# Current OpenAI model choices (official model IDs as of 2026-07-10).
# Re-check https://developers.openai.com/api/docs/models before deployment.
#
# RECOMMENDED DROP-IN MODELS FOR THIS PIPELINE
# (Responses API + Structured Outputs + hosted web_search):
#   "gpt-5.6-sol"   - latest flagship for highest-quality clinical synthesis.
#   "gpt-5.6"       - alias that currently routes to GPT-5.6 Sol.
#   "gpt-5.6-terra" - latest balanced intelligence/cost choice.
#   "gpt-5.6-luna"  - latest cost-sensitive/high-volume choice; default here.
#
# OTHER CURRENT GENERAL / REASONING OPTIONS
# (available catalog choices; newer frontier models above are preferred):
#   "gpt-5.5"       - professional-work model; also suited to deep research.
#   "gpt-5.5-pro"   - higher-compute GPT-5.5 variant.
#   "gpt-5.4"       - affordable professional-work model.
#   "gpt-5.4-pro"   - higher-compute GPT-5.4 variant.
#   "gpt-5.4-mini"  - strongest current mini model for precise/subagent work.
#   "gpt-5.4-nano"  - cheapest current GPT-5.4-class high-volume model.
#   "gpt-5.2"       - previous frontier professional-work model.
#   "gpt-5.2-pro"   - previous higher-compute GPT-5.2 variant.
#   "gpt-5.1"       - previous coding/agentic general model.
#   "gpt-5"         - previous GPT-5 reasoning model.
#   "gpt-5-pro"     - higher-compute GPT-5 variant.
#   "gpt-5-mini"    - prior cost-sensitive GPT-5 model.
#   "gpt-5-nano"    - prior fastest/lowest-cost GPT-5 model.
#   "o3-pro"        - prior high-compute o-series reasoning model.
#   "o3"            - prior o-series reasoning model.
#   "gpt-4.1"       - current non-reasoning large model.
#   "gpt-4.1-mini"  - current smaller non-reasoning model.
#   "gpt-4o-mini"   - inexpensive legacy multimodal model.
#
# CURRENT SPECIALIST MODEL FAMILIES — NOT DROP-IN REPLACEMENTS FOR THIS
# TEXT/STRUCTURED-OUTPUT PIPELINE, but listed so the model global documents the
# full current model-family menu. The first entry in each family is the latest
# recommended model in that family as of 2026-07-10:
#
# CODING
#   "gpt-5.3-codex"              - latest agentic coding model.
#
# IMAGE GENERATION / EDITING
#   "gpt-image-2"                - latest image generation/editing model.
#
# REALTIME SPEECH / AUDIO
#   "gpt-realtime-2.1"           - latest full realtime reasoning/tool model.
#   "gpt-realtime-2.1-mini"      - latest lower-cost realtime reasoning model.
#   "gpt-realtime-2"             - prior current realtime reasoning model.
#   "gpt-realtime-translate"     - current streaming speech translation.
#   "gpt-realtime-whisper"       - current streaming realtime transcription.
#   "gpt-realtime-1.5"           - current audio-in/audio-out realtime model.
#   "gpt-realtime"               - current general realtime model.
#   "gpt-realtime-mini"          - current cost-efficient realtime model.
#   "gpt-audio-1.5"              - latest Chat Completions audio model.
#   "gpt-audio"                  - current general audio model.
#
# TRANSCRIPTION / SPEECH GENERATION
#   "gpt-4o-transcribe-diarize"  - latest diarized transcription model.
#   "gpt-4o-transcribe"          - current transcription model.
#   "gpt-4o-mini-transcribe"     - current lower-cost transcription model.
#   "tts-1"                      - current speed-optimized text-to-speech model.
#   "tts-1-hd"                   - current quality-optimized text-to-speech model.
#   "whisper-1"                  - current general speech-recognition model.
#
# EMBEDDINGS
#   "text-embedding-3-large"     - latest highest-capability embedding model.
#   "text-embedding-3-small"     - latest lower-cost embedding model.
#   "text-embedding-ada-002"     - older, still-listed embedding model.
#
# MODERATION
#   "omni-moderation-latest"     - latest multimodal moderation model.
#
# OPEN-WEIGHT MODELS (run through supported deployment paths, not this API call)
#   "gpt-oss-120b"               - largest current OpenAI open-weight model.
#   "gpt-oss-20b"                - lower-latency current open-weight model.
#
# VIDEO / DEEP-RESEARCH CATALOG NOTE
#   "sora-2" / "sora-2-pro"      - latest listed video models, now deprecated.
#   "o3-deep-research"           - latest listed large deep-research model,
#                                   now deprecated.
#   "o4-mini-deep-research"      - latest listed mini deep-research model,
#                                   now deprecated.
#
# SPECIALIZED SEARCH-ONLY PATH
#   "gpt-5-search-api"           - search-specific Chat Completions model. This
#                                   tool deliberately uses Responses API plus the
#                                   hosted web_search tool instead, so do not
#                                   select this model for OPENAI_MODEL here.
#
# NOTE: Reasoning-effort values and tool support differ on older/specialist
# models. The CLI validates only the format, not account availability.
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-5.4-mini")

# Reasoning levels supported by current GPT-5.6 frontier models:
# "none", "low", "medium", "high", "xhigh", "max"
OPENAI_REASONING_EFFORT = os.getenv("OPENAI_REASONING_EFFORT", "medium")


# ---------------------------------------------------------------------------
# VERSIONING AND STABLE SECTION IDS
# ---------------------------------------------------------------------------

TOOL_VERSION = "1.0.0"
OUTPUT_SCHEMA_VERSION = "1.0.0"
PROMPT_SET_VERSION = "2026-07-10.1"

SECTION_IDS: dict[str, str] = {
    "cover": "sec_00_cover",
    "executive_summary": "sec_01_executive_summary",
    "key_findings": "sec_02_key_findings",
    "cause_effect": "sec_03_cause_and_effect",
    "therapy_options": "sec_04_therapy_options",
    "resistance_escape": "sec_05_resistance_and_escape",
    "follow_up_tests": "sec_06_follow_up_tests",
    "phenotypic_events": "sec_07_future_phenotypic_events",
    "limitations": "sec_08_limitations_and_confidence",
    "selected_links": "sec_09_selected_reference_and_trial_links",
    "appendix_overview": "sec_10_url_fit_assessments_overview",
    "cross_source_synthesis": "sec_11_cross_source_synthesis",
    "urls_assessed": "sec_12_urls_assessed",
}

DEFAULT_TRUSTED_DOMAINS: tuple[str, ...] = (
    "clinicaltrials.gov",
    "pubmed.ncbi.nlm.nih.gov",
    "pmc.ncbi.nlm.nih.gov",
    "ncbi.nlm.nih.gov",
    "fda.gov",
    "www.fda.gov",
    "cancer.gov",
    "www.cancer.gov",
    "nature.com",
    "www.nature.com",
    "sciencedirect.com",
    "www.sciencedirect.com",
    "aacrjournals.org",
    "ascopubs.org",
    "esmo.org",
    "nejm.org",
    "thelancet.com",
    "cell.com",
    "science.org",
    "civicdb.org",
)

DEFAULT_BLOCKED_DOMAINS: tuple[str, ...] = (
    "wikipedia.org",
    "reddit.com",
    "quora.com",
    "facebook.com",
    "x.com",
    "twitter.com",
    "pinterest.com",
)

TRACKING_QUERY_KEYS: frozenset[str] = frozenset(
    {
        "utm_source",
        "utm_medium",
        "utm_campaign",
        "utm_term",
        "utm_content",
        "gclid",
        "fbclid",
        "mc_cid",
        "mc_eid",
        "ref",
        "source",
    }
)

KNOWN_CONTEXT_ONLY_GENES: frozenset[str] = frozenset(
    {
        "TPMT",
        "DPYD",
        "UGT1A1",
        "CYP2D6",
        "CYP2C19",
        "CYP2C9",
        "NUDT15",
        "HLA-A",
        "HLA-B",
        "HLA-C",
    }
)

KNOWN_NOISE_LABELS: frozenset[str] = frozenset(
    {
        "",
        "UNKNOWN",
        "CLIANUMBER",
        "ACCESSION NO",
        "NO_GENE_SPECIFIED",
        "NOT SPECIFIED IN THE BATCH",
        "RONQIN_REN_MD_PHD",
        "TI PUS XT",
        "CHIP-ASSOCIATED GENES",
        "NO GENE REARRANGEMENTS",
    }
)

# ---------------------------------------------------------------------------
# LOGGING
# ---------------------------------------------------------------------------

LOGGER = logging.getLogger("precision_oncology_pipeline")


def configure_logging(verbose: bool = False) -> None:
    """Configure concise structured-ish logs without printing patient content."""

    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )


# ---------------------------------------------------------------------------
# GENERIC PURE HELPERS
# ---------------------------------------------------------------------------

T = TypeVar("T", bound=BaseModel)


def utc_now_iso() -> str:
    return dt.datetime.now(dt.UTC).replace(microsecond=0).isoformat()


def canonical_json(value: Any) -> str:
    """Return deterministic JSON suitable for hashes and cache keys."""

    if isinstance(value, BaseModel):
        value = value.model_dump(mode="json")
    elif dataclasses.is_dataclass(value):
        value = dataclasses.asdict(cast(Any, value))
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        default=str,
    )


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def stable_id(prefix: str, *parts: Any, length: int = 20) -> str:
    """Generate a deterministic identifier from canonicalized content."""

    digest = sha256_text(canonical_json(parts))[:length]
    return f"{prefix}_{digest}"


def first_nonempty(*values: Any) -> Any:
    for value in values:
        if value not in (None, "", [], {}, ()):
            return value
    return None


def normalize_whitespace(value: str | None) -> str:
    return re.sub(r"\s+", " ", value or "").strip()


def normalize_confidence(value: Any) -> float:
    """Normalize mixed confidence scales to [0, 1]."""

    try:
        number = float(value)
    except (TypeError, ValueError):
        return 0.0
    if number > 1.0:
        number = number / 100.0 if number <= 100.0 else 1.0
    return max(0.0, min(1.0, number))


def unique_preserve_order(values: Iterable[Any]) -> list[Any]:
    seen: set[str] = set()
    result: list[Any] = []
    for value in values:
        marker = canonical_json(value)
        if marker in seen:
            continue
        seen.add(marker)
        result.append(value)
    return result


def deep_get(data: Mapping[str, Any], path: Sequence[str], default: Any = None) -> Any:
    current: Any = data
    for key in path:
        if not isinstance(current, Mapping) or key not in current:
            return default
        current = current[key]
    return current


def normalize_url(url: str | None) -> str:
    """Normalize a URL while preserving a fully qualified, user-visible form."""

    value = normalize_whitespace(url)
    if not value:
        return ""
    if value.startswith("www."):
        value = "https://" + value
    parsed = urlparse(value)
    if parsed.scheme.lower() not in {"http", "https"} or not parsed.netloc:
        return ""

    scheme = parsed.scheme.lower()
    host = parsed.netloc.lower()
    if host.endswith(":80") and scheme == "http":
        host = host[:-3]
    if host.endswith(":443") and scheme == "https":
        host = host[:-4]

    path = re.sub(r"/{2,}", "/", parsed.path or "/")
    if path != "/" and path.endswith("/"):
        path = path[:-1]

    query_pairs = [
        (key, value)
        for key, value in parse_qsl(parsed.query, keep_blank_values=True)
        if key.lower() not in TRACKING_QUERY_KEYS
    ]
    query = urlencode(sorted(query_pairs))
    return urlunparse((scheme, host, path, "", query, ""))


def is_fully_qualified_url(url: str | None) -> bool:
    parsed = urlparse(url or "")
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def hostname(url: str | None) -> str:
    return urlparse(url or "").netloc.lower().removeprefix("www.")


def extract_nct_ids(texts: Iterable[str]) -> list[str]:
    """Extract NCT identifiers, repairing the common OCR NCTO####### form."""

    ids: set[str] = set()
    for text in texts:
        normalized = (text or "").upper()
        ids.update(re.findall(r"\bNCT\d{8}\b", normalized))
        for suffix in re.findall(r"\bNCTO(\d{7})\b", normalized):
            ids.add(f"NCT0{suffix}")
    return sorted(ids)


def extract_pmid(text: str | None) -> str | None:
    match = re.search(r"\bPMID\s*[:#]?\s*(\d{6,9})\b", text or "", flags=re.I)
    return match.group(1) if match else None


def extract_pmcid(text: str | None) -> str | None:
    match = re.search(r"\bPMC\d+\b", text or "", flags=re.I)
    return match.group(0).upper() if match else None


def extract_doi(text: str | None) -> str | None:
    match = re.search(r"\b10\.\d{4,9}/[-._;()/:A-Z0-9]+", text or "", flags=re.I)
    return match.group(0).rstrip(".,;)") if match else None


def canonical_source_key(source: Mapping[str, Any]) -> str:
    identifiers = source.get("identifiers") or {}
    nct_id = normalize_whitespace(identifiers.get("nct_id")).upper()
    doi = normalize_whitespace(identifiers.get("doi")).lower()
    pmid = normalize_whitespace(identifiers.get("pmid"))
    pmcid = normalize_whitespace(identifiers.get("pmcid")).upper()
    if nct_id:
        return f"nct:{nct_id}"
    if doi:
        return f"doi:{doi}"
    if pmid:
        return f"pmid:{pmid}"
    if pmcid:
        return f"pmcid:{pmcid}"
    return f"url:{normalize_url(source.get('canonical_url') or source.get('url'))}"


def ensure_source_url(source: Mapping[str, Any]) -> str:
    """Resolve a canonical fully qualified URL from source identifiers."""

    identifiers = source.get("identifiers") or {}
    raw_existing = normalize_whitespace(
        source.get("canonical_url") or source.get("url")
    )
    existing = normalize_url(raw_existing)
    nct_id = normalize_whitespace(identifiers.get("nct_id")).upper()
    source_type = normalize_whitespace(source.get("source_type")).lower()
    if not nct_id and (
        source_type == "trial_record" or hostname(existing) == "clinicaltrials.gov"
    ):
        nct_matches = extract_nct_ids([raw_existing, source.get("title") or ""])
        nct_id = nct_matches[0] if nct_matches else ""
    # Official trial records always use the stable ClinicalTrials.gov study URL.
    if nct_id:
        return f"https://clinicaltrials.gov/study/{nct_id}"
    if existing:
        return existing
    pmid = normalize_whitespace(identifiers.get("pmid"))
    pmcid = normalize_whitespace(identifiers.get("pmcid")).upper()
    doi = normalize_whitespace(identifiers.get("doi"))
    if pmid:
        return f"https://pubmed.ncbi.nlm.nih.gov/{pmid}"
    if pmcid:
        return f"https://pmc.ncbi.nlm.nih.gov/articles/{pmcid}"
    if doi:
        return f"https://doi.org/{doi}"
    return ""


def atomic_write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(payload, indent=2, ensure_ascii=False, default=str) + "\n"
    with tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        dir=str(path.parent),
        prefix=path.name + ".",
        suffix=".tmp",
        delete=False,
    ) as handle:
        handle.write(text)
        temp_name = handle.name
    os.replace(temp_name, path)


def read_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


# ---------------------------------------------------------------------------
# PYDANTIC BASE MODEL
# ---------------------------------------------------------------------------


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


# ---------------------------------------------------------------------------
# CANONICAL INPUT MODELS
# ---------------------------------------------------------------------------


class DiseaseContext(StrictModel):
    name: str | None = None
    stage: str | None = None
    setting: str | None = None
    histology: str | None = None


class SpecimenContext(StrictModel):
    site: str | None = None
    collection_date: str | None = None
    tumor_percentage: float | None = None
    specimen_type: str | None = None


class CaseContext(StrictModel):
    case_id: str
    session_id: str | None = None
    source_file_id: str | None = None
    report_type: str | None = None
    disease: DiseaseContext
    specimen: SpecimenContext
    prior_therapies: list[str] = Field(default_factory=list)
    line_of_therapy: str | None = None
    performance_status: str | None = None
    organ_function: dict[str, str | float | int | None] = Field(default_factory=dict)
    measurable_disease: bool | None = None
    biopsy_feasibility: bool | None = None
    location: str | None = None
    matched_normal_available: bool | None = None
    validation_status: str | None = None
    report_date: str | None = None
    missing_context: list[str] = Field(default_factory=list)


class CanonicalFinding(StrictModel):
    finding_id: str
    raw_finding_ids: list[str] = Field(default_factory=list)
    gene_or_marker: str
    display_label: str
    alteration: str
    alteration_type: str
    molecular_layers: list[str] = Field(default_factory=list)
    priority: Literal["PRIMARY", "SECONDARY", "CONTEXT", "TECHNICAL"]
    reported_category: str | None = None
    clinical_roles: list[str] = Field(default_factory=list)
    source_pages: list[int] = Field(default_factory=list)
    source_chunk_ids: list[str] = Field(default_factory=list)
    source_texts: list[str] = Field(default_factory=list)
    patient_evidence_ids: list[str] = Field(default_factory=list)
    confidence: float = 0.0
    needs_human_review: bool = True
    research_use_only: bool = False
    related_finding_ids: list[str] = Field(default_factory=list)
    contradictions: list[str] = Field(default_factory=list)
    missing_validation: list[str] = Field(default_factory=list)
    existing_drug_mentions: list[str] = Field(default_factory=list)
    existing_trial_ids: list[str] = Field(default_factory=list)


class TechnicalLimitation(StrictModel):
    limitation_id: str
    label: str
    description: str
    source_pages: list[int] = Field(default_factory=list)
    source_chunk_ids: list[str] = Field(default_factory=list)
    patient_evidence_ids: list[str] = Field(default_factory=list)
    clinical_effect: str
    conditional_follow_up: str | None = None


class PatientEvidence(StrictModel):
    evidence_id: str
    source_kind: Literal["finding", "chunk", "claim", "artifact", "limitation"]
    source_id: str
    page: int | None = None
    text: str


class ExistingContext(StrictModel):
    phenotype_axes: list[dict[str, Any]] = Field(default_factory=list)
    treatment_matrix: list[dict[str, Any]] = Field(default_factory=list)
    confirmatory_tests: list[dict[str, Any]] = Field(default_factory=list)
    must_not_assume: list[Any] = Field(default_factory=list)
    tumor_behavior: dict[str, Any] = Field(default_factory=dict)
    ranked_treatment_hints: list[dict[str, Any]] = Field(default_factory=list)
    treatment_pressure_hints: list[dict[str, Any]] = Field(default_factory=list)
    resistance_hints: list[dict[str, Any]] = Field(default_factory=list)
    biomarker_watch_hints: list[dict[str, Any]] = Field(default_factory=list)
    retesting_triggers: list[dict[str, Any]] = Field(default_factory=list)
    next_test_hints: list[dict[str, Any]] = Field(default_factory=list)
    evidence_limitations: list[Any] = Field(default_factory=list)
    missing_evidence: list[Any] = Field(default_factory=list)
    conflicting_evidence: list[Any] = Field(default_factory=list)
    reasoning_warnings: list[Any] = Field(default_factory=list)
    existing_trial_mentions: list[dict[str, Any]] = Field(default_factory=list)


class ProvenanceInput(StrictModel):
    evidence_sentences: list[dict[str, Any]] = Field(default_factory=list)
    claims: list[dict[str, Any]] = Field(default_factory=list)
    artifact_records: list[dict[str, Any]] = Field(default_factory=list)


class CanonicalInput(StrictModel):
    case: CaseContext
    actionable_findings: list[CanonicalFinding]
    secondary_findings: list[CanonicalFinding] = Field(default_factory=list)
    context_findings: list[CanonicalFinding] = Field(default_factory=list)
    technical_limitations: list[TechnicalLimitation] = Field(default_factory=list)
    negative_findings: list[str] = Field(default_factory=list)
    existing_context: ExistingContext
    patient_evidence: list[PatientEvidence] = Field(default_factory=list)
    provenance: ProvenanceInput


# ---------------------------------------------------------------------------
# HYPOTHESIS AND RESEARCH MODELS
# ---------------------------------------------------------------------------


class Hypothesis(StrictModel):
    hypothesis_id: str
    title: str
    hypothesis_type: str
    primary_finding_ids: list[str]
    supporting_finding_ids: list[str] = Field(default_factory=list)
    technical_limitation_ids: list[str] = Field(default_factory=list)
    biological_theme: str
    patient_specific_observation: str
    mechanism_to_validate: str
    potential_clinical_roles: list[str] = Field(default_factory=list)
    therapy_classes_to_research: list[str] = Field(default_factory=list)
    trial_search_required: bool
    variant_interpretation_required: bool
    confirmatory_questions: list[str] = Field(default_factory=list)
    critical_cautions: list[str] = Field(default_factory=list)
    missing_context: list[str] = Field(default_factory=list)
    research_priority: Literal["high", "medium", "low", "none"]
    patient_evidence_ids: list[str] = Field(default_factory=list)


class HypothesisBuilderOutput(StrictModel):
    hypotheses: list[Hypothesis]


class SearchConcepts(StrictModel):
    disease: list[str] = Field(default_factory=list)
    histology: list[str] = Field(default_factory=list)
    genes_or_markers: list[str] = Field(default_factory=list)
    alterations: list[str] = Field(default_factory=list)
    pathways: list[str] = Field(default_factory=list)
    therapy_classes: list[str] = Field(default_factory=list)
    agents_already_known: list[str] = Field(default_factory=list)
    trial_ids_already_known: list[str] = Field(default_factory=list)


class ResearchJob(StrictModel):
    job_id: str
    hypothesis_id: str
    question_type: Literal[
        "variant",
        "disease",
        "mechanism",
        "regulatory",
        "clinical_evidence",
        "trial",
        "confirmation",
        "population",
        "resistance",
        "monitoring",
    ]
    clinical_question: str
    search_concepts: SearchConcepts
    source_roles_needed: list[str] = Field(default_factory=list)
    preferred_sources: list[str] = Field(default_factory=list)
    minimum_evidence_level: str
    maximum_sources: int = Field(ge=1, le=12)
    required_report_sections: list[str] = Field(default_factory=list)
    stop_condition: str
    priority: Literal["high", "medium", "low"]


class ResearchPlanOutput(StrictModel):
    research_jobs: list[ResearchJob]


# ---------------------------------------------------------------------------
# SOURCE DISCOVERY / EXTRACTION MODELS
# ---------------------------------------------------------------------------


class SourceIdentifiers(StrictModel):
    doi: str | None = None
    pmid: str | None = None
    pmcid: str | None = None
    nct_id: str | None = None


class CandidateSource(StrictModel):
    source_id: str
    hypothesis_id: str
    job_id: str
    url: str
    canonical_url: str
    title: str
    publisher: str
    source_type: Literal[
        "primary_research",
        "clinical_study",
        "trial_record",
        "guideline",
        "regulatory",
        "review",
        "conference",
        "news",
        "sponsor",
        "other",
    ]
    publication_or_update_date: str | None = None
    identifiers: SourceIdentifiers
    source_role: str
    why_candidate: str
    patient_anchor_matched: list[str] = Field(default_factory=list)
    apparent_evidence_level: str
    requires_full_text: bool


class SearchRun(StrictModel):
    query: str
    purpose: str


class SourceDiscoveryOutput(StrictModel):
    job_id: str
    searches_run: list[SearchRun]
    candidate_sources: list[CandidateSource]
    unresolved_questions: list[str] = Field(default_factory=list)


class PopulationExtraction(StrictModel):
    tumor_types: list[str] = Field(default_factory=list)
    histologies: list[str] = Field(default_factory=list)
    disease_setting: list[str] = Field(default_factory=list)
    stage: list[str] = Field(default_factory=list)
    prior_therapy: list[str] = Field(default_factory=list)
    sample_size: int | None = None
    age_requirements: list[str] = Field(default_factory=list)
    performance_status_requirements: list[str] = Field(default_factory=list)
    other_key_criteria: list[str] = Field(default_factory=list)


class BiomarkerDefinition(StrictModel):
    markers: list[str] = Field(default_factory=list)
    required_alterations: list[str] = Field(default_factory=list)
    excluded_alterations: list[str] = Field(default_factory=list)
    assay_requirements: list[str] = Field(default_factory=list)
    thresholds: list[str] = Field(default_factory=list)
    confirmation_methods: list[str] = Field(default_factory=list)


class OutcomeExtraction(StrictModel):
    response: list[str] = Field(default_factory=list)
    pfs: list[str] = Field(default_factory=list)
    os: list[str] = Field(default_factory=list)
    duration_of_response: list[str] = Field(default_factory=list)
    pharmacodynamic: list[str] = Field(default_factory=list)
    toxicity: list[str] = Field(default_factory=list)


class TrialExtraction(StrictModel):
    status: str | None = None
    phase: str | None = None
    locations: list[str] = Field(default_factory=list)
    last_update: str | None = None


class SupportSpan(StrictModel):
    claim: str
    source_location: str
    text_excerpt: str


class SourceIdentity(StrictModel):
    title: str
    url: str
    publisher: str
    source_type: str
    publication_or_update_date: str | None = None
    identifiers: SourceIdentifiers


class SourceExtraction(StrictModel):
    source_id: str
    source_identity: SourceIdentity
    study_design: str
    evidence_level: str
    population: PopulationExtraction
    biomarker_definition: BiomarkerDefinition
    interventions: list[str] = Field(default_factory=list)
    comparators: list[str] = Field(default_factory=list)
    mechanism_claims: list[str] = Field(default_factory=list)
    outcomes: OutcomeExtraction
    trial: TrialExtraction
    resistance_findings: list[str] = Field(default_factory=list)
    monitoring_findings: list[str] = Field(default_factory=list)
    authors_limitations: list[str] = Field(default_factory=list)
    facts_not_reported: list[str] = Field(default_factory=list)
    support_spans: list[SupportSpan] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# SOURCE FIT AND TRIAL MODELS
# ---------------------------------------------------------------------------


class FitDimension(StrictModel):
    score: int = Field(ge=0, le=10)
    reason: str


class FitDimensions(StrictModel):
    molecular_fit: FitDimension
    population_fit: FitDimension
    evidence_maturity: FitDimension
    standard_care_readiness: FitDimension
    trial_screening_value: FitDimension


class BottomLineScoreRow(StrictModel):
    question: str
    strength_label: str
    score_min: int = Field(ge=0, le=10)
    score_max: int = Field(ge=0, le=10)
    why: str


class FollowUpAction(StrictModel):
    follow_up: str
    why: str
    priority: Literal["high", "medium", "low"]


class SourceFitAssessment(StrictModel):
    assessment_id: str
    source_id: str
    hypothesis_id: str
    appendix_title: str
    url: str
    source_type: str
    relevant_marker_or_pathway: list[str] = Field(default_factory=list)
    opening_assessment: str
    standardized_scores: FitDimensions
    bottom_line_score_rows: list[BottomLineScoreRow]
    why_the_fit_is_strong: list[str] = Field(default_factory=list)
    matching_features: list[str] = Field(default_factory=list)
    mismatching_features: list[str] = Field(default_factory=list)
    unknown_alignment_fields: list[str] = Field(default_factory=list)
    what_would_make_the_patient_a_stronger_candidate: list[str] = Field(
        default_factory=list
    )
    what_weakens_the_case: list[str] = Field(default_factory=list)
    my_read_on_this_case: str
    clinical_framing_to_use: str
    do_not_say: str
    say_instead: str
    source_specific_follow_up: list[FollowUpAction] = Field(default_factory=list)
    source_specific_conclusion: list[str] = Field(default_factory=list)
    patient_evidence_ids: list[str] = Field(default_factory=list)
    external_support_claims: list[str] = Field(default_factory=list)
    confidence: Literal["high", "moderate", "low"]


class CriterionAssessment(StrictModel):
    criterion: str
    assessment: Literal[
        "MATCH", "POSSIBLE_MATCH", "MISMATCH", "UNKNOWN", "NOT_ASSESSABLE"
    ]
    patient_evidence: str
    reason: str


class MatchAssessment(StrictModel):
    status: Literal["MATCH", "POSSIBLE_MATCH", "MISMATCH", "UNKNOWN", "NOT_ASSESSABLE"]
    reason: str


class TrialPrescreen(StrictModel):
    prescreen_id: str
    source_id: str
    nct_id: str
    trial_status: str
    last_update: str | None = None
    biomarker_match: MatchAssessment
    tumor_type_match: MatchAssessment
    disease_setting_match: MatchAssessment
    criterion_assessment: list[CriterionAssessment]
    required_missing_data: list[str] = Field(default_factory=list)
    site_and_geography: list[str] = Field(default_factory=list)
    screening_priority: Literal["high", "medium", "low", "not_currently_actionable"]
    reason: str
    not_a_final_eligibility_determination: bool


# ---------------------------------------------------------------------------
# HYPOTHESIS SYNTHESIS MODELS
# ---------------------------------------------------------------------------


class CauseEffectStep(StrictModel):
    step: int = Field(ge=1)
    statement: str
    evidence_type: str
    patient_evidence_ids: list[str] = Field(default_factory=list)
    source_ids: list[str] = Field(default_factory=list)


class TherapyOpportunity(StrictModel):
    therapy_class: str
    example_agents: list[str] = Field(default_factory=list)
    molecular_interaction: str
    clinical_use: Literal[
        "standard",
        "off_label",
        "investigational",
        "biologic_rationale_only",
        "unsupported",
    ]
    population_fit: str
    evidence_level: str
    key_caveats: list[str] = Field(default_factory=list)
    source_ids: list[str] = Field(default_factory=list)


class ConfirmatoryTestSynthesis(StrictModel):
    test: str
    why_it_matters: str
    priority: Literal["high", "medium", "low"]
    source_ids: list[str] = Field(default_factory=list)


class ResistanceEscapeSynthesis(StrictModel):
    escape_route: str
    evidence_status: Literal[
        "observed", "reported", "mechanistically_plausible", "speculative"
    ]
    description: str
    biomarkers_to_monitor: list[str] = Field(default_factory=list)
    source_ids: list[str] = Field(default_factory=list)


class PopulationAlignment(StrictModel):
    matching: list[str] = Field(default_factory=list)
    mismatching: list[str] = Field(default_factory=list)
    unknown: list[str] = Field(default_factory=list)


class ReportClaim(StrictModel):
    claim_id: str
    claim: str
    patient_evidence_ids: list[str] = Field(default_factory=list)
    external_source_ids: list[str] = Field(default_factory=list)
    allowed_strength: str


class HypothesisSynthesis(StrictModel):
    synthesis_id: str
    hypothesis_id: str
    hypothesis_status: Literal[
        "supported",
        "partially_supported",
        "uncertain",
        "not_supported",
        "technical_only",
    ]
    executive_summary_statement: str
    validated_biology: list[str] = Field(default_factory=list)
    cause_effect_chain: list[CauseEffectStep] = Field(default_factory=list)
    plain_english_explanation: str
    therapy_opportunities: list[TherapyOpportunity] = Field(default_factory=list)
    confirmatory_tests: list[ConfirmatoryTestSynthesis] = Field(default_factory=list)
    resistance_and_escape: list[ResistanceEscapeSynthesis] = Field(default_factory=list)
    monitoring_implications: list[str] = Field(default_factory=list)
    active_trial_leads: list[str] = Field(default_factory=list)
    unsupported_or_overstated_options: list[str] = Field(default_factory=list)
    population_alignment: PopulationAlignment
    limitations: list[str] = Field(default_factory=list)
    confidence: Literal["high", "moderate", "low"]
    report_claims: list[ReportClaim] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# FINAL REPORT DRAFT MODELS — CONTENT TYPES MIRROR THE PDF
# ---------------------------------------------------------------------------


class CoverMetadata(StrictModel):
    title: str
    subtitle: str
    purpose_statements: list[str]
    source_label: str
    report_type: str
    disease_or_tumor_type: str
    specimen_context: str
    overall_validation_status: str
    important_note: str


class EvidenceParagraph(StrictModel):
    text: str
    patient_evidence_ids: list[str] = Field(default_factory=list)
    source_ids: list[str] = Field(default_factory=list)


class ExecutiveSummarySection(StrictModel):
    paragraphs: list[EvidenceParagraph]
    top_takeaway: str
    most_trial_relevant_finding: str
    most_likely_to_require_confirmation: str
    most_important_technical_caveat: str


class KeyFindingRow(StrictModel):
    row_id: str
    marker_or_finding: str
    reasoning_domain: str
    what_it_means: str
    why_it_matters: str
    actionability: str
    next_step: str
    patient_evidence_ids: list[str] = Field(default_factory=list)
    source_ids: list[str] = Field(default_factory=list)


class OtherFindingRow(StrictModel):
    row_id: str
    finding: str
    interpretation: str
    patient_evidence_ids: list[str] = Field(default_factory=list)
    source_ids: list[str] = Field(default_factory=list)


class CauseEffectRow(StrictModel):
    row_id: str
    finding: str
    mechanism_chain: str
    plain_english: str
    patient_evidence_ids: list[str] = Field(default_factory=list)
    source_ids: list[str] = Field(default_factory=list)


class TherapyOptionRow(StrictModel):
    row_id: str
    marker_or_target: str
    therapy_class: str
    example_agents: list[str] = Field(default_factory=list)
    molecular_interaction: str
    key_caveats: list[str] = Field(default_factory=list)
    status: str
    patient_evidence_ids: list[str] = Field(default_factory=list)
    source_ids: list[str] = Field(default_factory=list)


class ResistanceEscapeRow(StrictModel):
    row_id: str
    therapy_or_pathway: str
    escape_routes: list[str] = Field(default_factory=list)
    evidence_status: str
    monitoring_markers: list[str] = Field(default_factory=list)
    source_ids: list[str] = Field(default_factory=list)


class FollowUpTestRow(StrictModel):
    row_id: str
    recommended_next_step: str
    why_it_matters: str
    priority: str
    patient_evidence_ids: list[str] = Field(default_factory=list)
    source_ids: list[str] = Field(default_factory=list)


class PhenotypicEventRow(StrictModel):
    row_id: str
    clinical_event: str
    why_it_matters: str
    urgency: Literal["high", "medium", "low"]
    recommended_test: str


class SelectedLinkRow(StrictModel):
    row_id: str
    source_id: str
    title: str
    url: str
    why_it_is_useful: str
    source_type: str
    hypothesis_id: str


class AppendixSourceIndexRow(StrictModel):
    display_order: int
    source_id: str
    title: str
    marker_or_pathway: list[str]
    evidence_type: str
    url: str


class URLFitAppendixOverview(StrictModel):
    data_basis_and_rules: list[str]
    scoring_guide: str
    source_index: list[AppendixSourceIndexRow]
    source_assessment_ids: list[str]


class ReportDraft(StrictModel):
    report_draft_id: str
    cover_metadata: CoverMetadata
    executive_summary: ExecutiveSummarySection
    key_findings: list[KeyFindingRow]
    other_findings: list[OtherFindingRow]
    cause_effect: list[CauseEffectRow]
    therapy_options: list[TherapyOptionRow]
    practical_readout: list[str]
    resistance_escape: list[ResistanceEscapeRow]
    follow_up_tests: list[FollowUpTestRow]
    phenotypic_events: list[PhenotypicEventRow]
    limitations: list[str]
    selected_links: list[SelectedLinkRow]
    bottom_line: list[str]
    url_fit_appendix: URLFitAppendixOverview


class CrossSourceTheme(StrictModel):
    theme: str
    cross_source_conclusion: str
    evidence_maturity: str
    clinical_role: str


class CrossSourceSynthesis(StrictModel):
    synthesis_id: str
    summary: str
    themes: list[CrossSourceTheme]
    practical_bottom_line: list[str]
    source_ids: list[str]


# ---------------------------------------------------------------------------
# VALIDATION MODELS
# ---------------------------------------------------------------------------


class ValidationFinding(StrictModel):
    finding_id: str
    severity: Literal["info", "warning", "error", "blocking"]
    disposition: Literal["PASS", "REVISE", "REMOVE"]
    section_id: str | None = None
    item_id: str | None = None
    statement: str
    reason: str
    suggested_revision: str | None = None
    patient_evidence_ids: list[str] = Field(default_factory=list)
    source_ids: list[str] = Field(default_factory=list)


class ValidationOutput(StrictModel):
    validator_id: str
    validator_type: Literal[
        "claim_grounding",
        "population_alignment",
        "clinical_safety",
        "deterministic_integrity",
    ]
    passed: bool
    findings: list[ValidationFinding]


# ---------------------------------------------------------------------------
# FINAL RENDERER-INDEPENDENT ARTIFACT MODELS
# ---------------------------------------------------------------------------


class SectionEnvelope(StrictModel):
    section_id: str
    section_number: str
    title: str
    content_type: str
    display_order: int
    preferred_page_break_before: bool
    payload: dict[str, Any]


class SourceRegistryEntry(StrictModel):
    source_id: str
    canonical_key: str
    title: str
    url: str
    publisher: str
    source_type: str
    source_role: str
    publication_or_update_date: str | None = None
    identifiers: SourceIdentifiers
    hypothesis_ids: list[str]
    job_ids: list[str]
    selection_score: float
    verification_status: str
    consulted_urls: list[str] = Field(default_factory=list)


class UsageRecord(StrictModel):
    call_id: str
    stage: str
    artifact_id: str
    response_id: str | None = None
    model: str
    usage: dict[str, Any] = Field(default_factory=dict)
    web_source_count: int = 0
    cache_hit: bool = False


class ArtifactEnvelope(StrictModel):
    artifact_id: str
    artifact_type: str
    stage: str
    parent_artifact_ids: list[str]
    created_at: str
    input_hash: str
    prompt_version: str | None = None
    model: str | None = None
    response_id: str | None = None
    payload: dict[str, Any]


class FinalPacket(StrictModel):
    schema_version: str
    tool_version: str
    packet_id: str
    run_id: str
    case_id: str
    generated_at: str
    source_input_sha256: str
    model: str
    reasoning_effort: str
    clinical_disclaimer: str

    # Complete typed pipeline state. These maps make the output independently
    # renderable, auditable, and queryable without replaying API calls.
    canonical_input: CanonicalInput
    hypotheses_by_id: dict[str, Hypothesis]
    research_jobs_by_id: dict[str, ResearchJob]
    sources_by_id: dict[str, SourceRegistryEntry]
    source_extractions_by_id: dict[str, SourceExtraction]
    source_fit_assessments_by_id: dict[str, SourceFitAssessment]
    trial_prescreens_by_id: dict[str, TrialPrescreen]
    hypothesis_syntheses_by_id: dict[str, HypothesisSynthesis]
    report_draft: ReportDraft
    cross_source_synthesis: CrossSourceSynthesis

    # Renderer-facing representation in the same semantic order/content types
    # as the 31-page reference packet.
    document_flow: list[str]
    sections_by_id: dict[str, SectionEnvelope]

    # Provenance, validation, and operational records.
    patient_evidence_by_id: dict[str, PatientEvidence]
    claims_by_id: dict[str, ReportClaim]
    artifacts_by_id: dict[str, ArtifactEnvelope]
    validations: list[ValidationOutput]
    usage_records: list[UsageRecord]
    warnings: list[str]


# ---------------------------------------------------------------------------
# PIPELINE RUNTIME TYPES
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class WebSource:
    url: str
    title: str
    type: str | None = None


@dataclass(frozen=True)
class ModelResult(Generic[T]):
    parsed: T
    response_id: str | None
    model: str
    usage: dict[str, Any]
    web_sources: tuple[WebSource, ...]
    cache_hit: bool


@dataclass(frozen=True)
class PipelineConfig:
    api_key: str
    model: str
    reasoning_effort: str
    output_dir: Path
    max_concurrency: int = 4
    max_attempts: int = 5
    request_timeout_seconds: float = 240.0
    max_research_jobs: int = 24
    max_sources_per_job: int = 5
    max_sources_per_hypothesis: int = 10
    max_sources_total: int = 24
    strict_source_verification: bool = True
    enable_web_search: bool = True
    live_web_access: bool = True
    web_return_token_budget: Literal["default", "unlimited"] = "default"
    resume: bool = True
    store_prompt_payloads: bool = False
    run_llm_validators: bool = True
    allow_blocking_validation: bool = False
    dry_run: bool = False
    stop_after: str | None = None


@dataclass(frozen=True)
class PipelineState:
    run_id: str
    source_input_sha256: str
    canonical_input: CanonicalInput
    hypotheses: tuple[Hypothesis, ...] = ()
    research_jobs: tuple[ResearchJob, ...] = ()
    sources: tuple[SourceRegistryEntry, ...] = ()
    source_extractions: tuple[SourceExtraction, ...] = ()
    source_fit_assessments: tuple[SourceFitAssessment, ...] = ()
    trial_prescreens: tuple[TrialPrescreen, ...] = ()
    hypothesis_syntheses: tuple[HypothesisSynthesis, ...] = ()
    report_draft: ReportDraft | None = None
    cross_source_synthesis: CrossSourceSynthesis | None = None
    validations: tuple[ValidationOutput, ...] = ()
    artifacts: tuple[ArtifactEnvelope, ...] = ()
    usage_records: tuple[UsageRecord, ...] = ()
    warnings: tuple[str, ...] = ()


# ---------------------------------------------------------------------------
# INPUT PARSING AND ACTIONABLE FINDING NORMALIZATION — PURE FUNCTIONS
# ---------------------------------------------------------------------------


def chunks_by_id(raw: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        str(chunk.get("chunk_id")): dict(chunk)
        for chunk in raw.get("chunks", [])
        if isinstance(chunk, Mapping) and chunk.get("chunk_id")
    }


def chunks_by_type(raw: Mapping[str, Any], chunk_type: str) -> list[dict[str, Any]]:
    return [
        dict(chunk)
        for chunk in raw.get("chunks", [])
        if isinstance(chunk, Mapping) and chunk.get("chunk_type") == chunk_type
    ]


def chunks_matching(
    raw: Mapping[str, Any], predicate: Callable[[Mapping[str, Any]], bool]
) -> list[dict[str, Any]]:
    return [
        dict(chunk)
        for chunk in raw.get("chunks", [])
        if isinstance(chunk, Mapping) and predicate(chunk)
    ]


def parse_case_metadata_from_chunks(raw: Mapping[str, Any]) -> dict[str, Any]:
    """Extract conservative case metadata from source chunks without inference."""

    texts = [
        normalize_whitespace(chunk.get("source_text"))
        for chunk in chunks_by_type(raw, "case_metadata")
    ]
    all_text = "\n".join(texts)

    disease: str | None = None
    for pattern in (
        r"Diagnosis\s+(.+?)(?:\s+Accession\s+No|\s+Tumor specimen|$)",
        r"Diagnosis[:\s]+([^\n]+)",
    ):
        match = re.search(pattern, all_text, flags=re.I)
        if match:
            candidate = normalize_whitespace(match.group(1))
            if candidate and len(candidate) <= 200:
                disease = candidate
                break

    specimen: str | None = None
    match = re.search(
        r"Tumor specimen[:\s]+(.+?)(?:\s+Collected\s|\s+Received\s|\s+Tumor Percentage|\s+Diagnosis\s|$)",
        all_text,
        flags=re.I,
    )
    if match:
        specimen = normalize_whitespace(match.group(1))

    tumor_percentage: float | None = None
    match = re.search(r"Tumor Percentage\s*:?\s*(\d+(?:\.\d+)?)%", all_text, flags=re.I)
    if match:
        tumor_percentage = float(match.group(1))

    report_date: str | None = None
    report_texts = [
        normalize_whitespace(chunk.get("source_text"))
        for chunk in raw.get("chunks", [])
        if isinstance(chunk, Mapping)
    ]
    combined = "\n".join(report_texts)
    match = re.search(
        r"(?:Date Signed/Reported|Date Issued|Date issued)\s*'?\s*(\d{2}/\d{2}/\d{4})",
        combined,
        flags=re.I,
    )
    if match:
        report_date = match.group(1)

    no_normal = bool(
        re.search(
            r"No normal sample was received|normal sample was unavailable|without a matched normal",
            combined,
            flags=re.I,
        )
    )

    return {
        "disease": disease,
        "specimen": specimen,
        "tumor_percentage": tumor_percentage,
        "report_date": report_date,
        "matched_normal_available": False if no_normal else None,
    }


def normalized_gene_label(value: str | None) -> str:
    raw = normalize_whitespace(value).upper()
    raw = raw.replace("¢", "C")
    return raw


def is_plausible_gene_or_marker(value: str | None) -> bool:
    label = normalized_gene_label(value)
    if label in KNOWN_NOISE_LABELS:
        return False
    if label in {"TMB", "MSI", "MSI-H", "MSS", "PD-L1", "HRD"}:
        return True
    if "," in label and label.startswith("HLA-"):
        return True
    return bool(re.fullmatch(r"[A-Z][A-Z0-9-]{1,24}", label))


def classify_molecular_layer(
    alteration_type: str, alteration: str, source_text: str
) -> list[str]:
    joined = " ".join((alteration_type, alteration, source_text)).lower()
    layers: list[str] = []
    if any(
        term in joined
        for term in ("rna expression", "overexpress", "underexpress", "transcriptome")
    ):
        layers.append("RNA")
    if any(
        term in joined
        for term in (
            "copy number",
            "snv",
            "indel",
            "deletion",
            "frameshift",
            "splice",
            "missense",
            "fusion",
            "rearrangement",
            "loss of function",
            "lof",
        )
    ):
        layers.append("DNA")
    if any(term in joined for term in ("ihc", "protein loss", "protein expression")):
        layers.append("protein")
    if any(term in joined for term in ("hla", "pd-l1", "immune")):
        layers.append("immune")
    if any(term in joined for term in ("tmb", "msi", "hrd", "genomic signature")):
        layers.append("genomic_signature")
    if "low coverage" in joined or "assay limitation" in joined:
        layers.append("technical")
    return unique_preserve_order(layers or ["unknown"])


def classify_finding_priority(
    finding: Mapping[str, Any],
    source_chunk: Mapping[str, Any] | None,
    decision_actionable_genes: set[str],
    ranked_biomarkers: set[str],
) -> Literal["PRIMARY", "SECONDARY", "CONTEXT", "TECHNICAL"] | None:
    gene = normalized_gene_label(finding.get("gene"))
    alteration = normalize_whitespace(finding.get("alteration"))
    alteration_type = normalize_whitespace(finding.get("alteration_type"))
    source_text = normalize_whitespace(finding.get("source_text"))
    chunk_type = normalize_whitespace((source_chunk or {}).get("chunk_type")).lower()
    section = normalize_whitespace((source_chunk or {}).get("section")).lower()
    joined = " ".join(
        (alteration, alteration_type, source_text, chunk_type, section)
    ).lower()

    if not is_plausible_gene_or_marker(gene):
        return None
    if any(
        term in joined
        for term in (
            "no alteration",
            "no reportable pathogenic variants",
            "no gene rearrangements",
        )
    ):
        return None
    if "low coverage" in joined:
        return "TECHNICAL"
    if gene in KNOWN_CONTEXT_ONLY_GENES or gene.startswith("HLA-"):
        return "CONTEXT"
    if chunk_type == "vus" or "variant of unknown significance" in joined:
        return "CONTEXT"
    if bool(finding.get("research_use_only")):
        return "SECONDARY"
    if gene in decision_actionable_genes or gene in ranked_biomarkers:
        return "PRIMARY"
    if (
        "potentially actionable" in joined
        or "variant_details_potentially_actionable" in section
    ):
        return "PRIMARY"
    if any(
        term in joined
        for term in (
            "loss of function",
            "lof",
            "copy number loss",
            "copy number gain",
            "fusion",
            "rearrangement",
            "overexpress",
            "underexpress",
            "biologically relevant",
            "immunotherapy marker",
        )
    ):
        return "SECONDARY"
    return None


def infer_missing_validation(
    gene: str,
    alteration: str,
    alteration_type: str,
    matched_normal_available: bool | None,
) -> list[str]:
    joined = f"{alteration} {alteration_type}".lower()
    items: list[str] = []
    if "copy number loss" in joined or alteration_type.lower() == "loss":
        items.extend(
            [
                "confirm absolute copy number",
                "clarify homozygous versus heterozygous loss",
            ]
        )
    if "copy number gain" in joined or alteration_type.lower() == "gain":
        items.append("confirm focality and absolute copy number")
    if any(
        term in joined for term in ("underexpress", "overexpress", "rna expression")
    ):
        items.append(
            "orthogonal protein or pathway-level confirmation if management would change"
        )
    if any(
        term in joined for term in ("splice", "loss of function", "lof", "frameshift")
    ):
        items.extend(
            [
                "confirm transcript and pathogenicity classification",
                "review zygosity or second-hit context when available",
            ]
        )
        if matched_normal_available is False:
            items.append(
                "consider whether germline confirmation is clinically appropriate"
            )
    if "low coverage" in joined:
        items.append(f"orthogonal {gene} testing only if clinically relevant")
    return unique_preserve_order(items)


def make_patient_evidence(
    source_kind: Literal["finding", "chunk", "claim", "artifact", "limitation"],
    source_id: str,
    text: str,
    page: int | None,
) -> PatientEvidence:
    normalized = normalize_whitespace(text)
    evidence_id = stable_id("pev", source_kind, source_id, page, normalized)
    return PatientEvidence(
        evidence_id=evidence_id,
        source_kind=source_kind,
        source_id=source_id,
        page=page,
        text=normalized,
    )


def trial_mention_matches_finding(
    gene: str,
    alteration: str,
    alteration_type: str,
    mention_text: str,
) -> bool:
    """Conservatively match an existing trial mention to a finding direction."""

    text = normalize_whitespace(mention_text).lower()
    if not gene or gene.lower() not in text:
        return False
    finding_text = f"{alteration} {alteration_type}".lower()
    if any(term in finding_text for term in ("overexpress", "gain", "amplification")):
        return any(term in text for term in ("overexpress", "gain", "amplification"))
    if any(
        term in finding_text
        for term in ("underexpress", "copy number loss", "deletion", "loss")
    ):
        return any(
            term in text
            for term in ("underexpress", "deletion", "deleted", "loss", "null")
        )
    if any(
        term in finding_text
        for term in ("splice", "frameshift", "lof", "loss of function")
    ):
        return any(
            term in text
            for term in ("mutation", "variant", "splice", "lof", "loss-of-function")
        )
    return True


def trial_mentions_from_chunks(raw: Mapping[str, Any]) -> list[dict[str, Any]]:
    mentions: list[dict[str, Any]] = []
    for chunk in chunks_matching(
        raw,
        lambda item: (
            item.get("chunk_type") == "clinical_trial_context"
            or "clinical_trials" in normalize_whitespace(item.get("section")).lower()
        ),
    ):
        text = normalize_whitespace(chunk.get("source_text"))
        ids = extract_nct_ids([text])
        for nct_id in ids:
            mentions.append(
                {
                    "trial_id": nct_id,
                    "title_or_context": text,
                    "url": f"https://clinicaltrials.gov/study/{nct_id}",
                    "source_chunk_id": chunk.get("chunk_id"),
                    "source_page": chunk.get("page_start"),
                }
            )
    return unique_preserve_order(mentions)


def group_finding_records(
    records: Sequence[CanonicalFinding],
) -> list[CanonicalFinding]:
    """
    Conservatively merge exact/near duplicate finding records.

    The function intentionally does not merge different genes or opposite
    molecular directions. It does merge multiple evidence layers for a common
    gene when they all represent a loss-like state, mirroring MTAP or CDKN2A
    DNA/RNA evidence in the reference packet.
    """

    groups: dict[tuple[str, str], list[CanonicalFinding]] = defaultdict(list)

    def direction(record: CanonicalFinding) -> str:
        text = f"{record.alteration} {record.alteration_type}".lower()
        if any(term in text for term in ("low coverage", "insufficient coverage")):
            return "technical"
        if any(
            term in text
            for term in (
                "copy number loss",
                "underexpress",
                "loss of function",
                "lof",
                "deletion",
                "frameshift",
            )
        ):
            return "loss"
        if any(
            term in text
            for term in ("copy number gain", "overexpress", "amplification")
        ):
            return "gain"
        if "vus" in text or record.priority == "CONTEXT":
            return f"context:{normalize_whitespace(record.alteration).lower()}"
        return normalize_whitespace(record.alteration_type or record.alteration).lower()

    for record in records:
        groups[(record.gene_or_marker, direction(record))].append(record)

    merged: list[CanonicalFinding] = []
    priority_order = {"PRIMARY": 0, "SECONDARY": 1, "CONTEXT": 2, "TECHNICAL": 3}
    for (gene, bucket), group in sorted(groups.items(), key=lambda item: item[0]):
        ordered = sorted(
            group, key=lambda item: (priority_order[item.priority], item.finding_id)
        )
        first = ordered[0]
        alterations = unique_preserve_order(
            item.alteration for item in ordered if item.alteration
        )
        alteration_types = unique_preserve_order(
            item.alteration_type for item in ordered if item.alteration_type
        )
        display = f"{gene} {' / '.join(alterations)}" if alterations else gene
        if bucket == "loss" and len(ordered) > 1:
            display = (
                f"{gene} loss / underexpression"
                if any("underexpress" in item.alteration.lower() for item in ordered)
                else f"{gene} loss"
            )
        if bucket == "gain" and len(ordered) > 1:
            display = f"{gene} gain / overexpression"

        merged_id = stable_id(
            "finding",
            gene,
            bucket,
            sorted(item.finding_id for item in ordered),
        )
        merged.append(
            CanonicalFinding(
                finding_id=merged_id,
                raw_finding_ids=unique_preserve_order(
                    raw_id
                    for item in ordered
                    for raw_id in (item.raw_finding_ids or [item.finding_id])
                ),
                gene_or_marker=gene,
                display_label=display,
                alteration=" / ".join(alterations),
                alteration_type=" / ".join(alteration_types),
                molecular_layers=unique_preserve_order(
                    layer for item in ordered for layer in item.molecular_layers
                ),
                priority=min(
                    (item.priority for item in ordered),
                    key=lambda value: priority_order[value],
                ),
                reported_category=first.reported_category,
                clinical_roles=unique_preserve_order(
                    role for item in ordered for role in item.clinical_roles
                ),
                source_pages=sorted(
                    set(page for item in ordered for page in item.source_pages)
                ),
                source_chunk_ids=unique_preserve_order(
                    chunk_id for item in ordered for chunk_id in item.source_chunk_ids
                ),
                source_texts=unique_preserve_order(
                    text for item in ordered for text in item.source_texts if text
                ),
                patient_evidence_ids=unique_preserve_order(
                    evidence_id
                    for item in ordered
                    for evidence_id in item.patient_evidence_ids
                ),
                confidence=max(item.confidence for item in ordered),
                needs_human_review=any(item.needs_human_review for item in ordered),
                research_use_only=all(item.research_use_only for item in ordered),
                related_finding_ids=unique_preserve_order(
                    related for item in ordered for related in item.related_finding_ids
                ),
                contradictions=unique_preserve_order(
                    contradiction
                    for item in ordered
                    for contradiction in item.contradictions
                ),
                missing_validation=unique_preserve_order(
                    validation
                    for item in ordered
                    for validation in item.missing_validation
                ),
                existing_drug_mentions=unique_preserve_order(
                    drug for item in ordered for drug in item.existing_drug_mentions
                ),
                existing_trial_ids=unique_preserve_order(
                    trial for item in ordered for trial in item.existing_trial_ids
                ),
            )
        )
    return merged


def adapt_preselected_finding(
    item: Mapping[str, Any], case: CaseContext
) -> CanonicalFinding:
    gene = normalized_gene_label(item.get("gene_or_marker") or item.get("gene"))
    alteration = normalize_whitespace(item.get("alteration"))
    alteration_type = normalize_whitespace(item.get("alteration_type"))
    source_pages = [
        int(value) for value in item.get("source_pages", []) if value is not None
    ]
    if not source_pages and item.get("source_page") is not None:
        source_pages = [int(item["source_page"])]
    source_chunk_ids = list(item.get("source_chunk_ids") or [])
    if not source_chunk_ids and item.get("source_chunk_id"):
        source_chunk_ids = [str(item["source_chunk_id"])]
    source_texts = list(item.get("source_texts") or [])
    if not source_texts and item.get("source_text"):
        source_texts = [normalize_whitespace(item["source_text"])]
    priority = str(item.get("priority") or "PRIMARY").upper()
    if priority not in {"PRIMARY", "SECONDARY", "CONTEXT", "TECHNICAL"}:
        priority = "PRIMARY"
    finding_id = str(
        item.get("finding_id")
        or stable_id("finding", gene, alteration, alteration_type, source_chunk_ids)
    )
    evidence_ids = list(item.get("patient_evidence_ids") or [])
    if not evidence_ids:
        evidence_ids = [
            make_patient_evidence(
                "finding", finding_id, text, source_pages[0] if source_pages else None
            ).evidence_id
            for text in source_texts
        ]
    return CanonicalFinding(
        finding_id=finding_id,
        raw_finding_ids=list(item.get("raw_finding_ids") or [finding_id]),
        gene_or_marker=gene,
        display_label=normalize_whitespace(item.get("display_label"))
        or f"{gene} {alteration}".strip(),
        alteration=alteration,
        alteration_type=alteration_type,
        molecular_layers=list(
            item.get("molecular_layers")
            or item.get("molecular_layer")
            or classify_molecular_layer(
                alteration_type, alteration, " ".join(source_texts)
            )
        ),
        priority=priority,  # type: ignore[arg-type]
        reported_category=item.get("reported_category"),
        clinical_roles=list(item.get("clinical_roles") or []),
        source_pages=source_pages,
        source_chunk_ids=source_chunk_ids,
        source_texts=source_texts,
        patient_evidence_ids=evidence_ids,
        confidence=normalize_confidence(item.get("confidence", 1.0)),
        needs_human_review=bool(item.get("needs_human_review", True)),
        research_use_only=bool(item.get("research_use_only", False)),
        related_finding_ids=list(item.get("related_finding_ids") or []),
        contradictions=list(item.get("contradictions") or []),
        missing_validation=list(
            item.get("missing_validation")
            or infer_missing_validation(
                gene, alteration, alteration_type, case.matched_normal_available
            )
        ),
        existing_drug_mentions=list(item.get("existing_drug_mentions") or []),
        existing_trial_ids=list(item.get("existing_trial_ids") or []),
    )


def build_case_context(
    raw: Mapping[str, Any], overlay: Mapping[str, Any] | None = None
) -> CaseContext:
    bundle = raw.get("bundle") or {}
    extraction = bundle.get("extraction") or {}
    decision_brief = bundle.get("decision_brief") or {}
    fallback = parse_case_metadata_from_chunks(raw)
    overlay = overlay or {}

    disease_overlay = overlay.get("disease") or {}
    specimen_overlay = overlay.get("specimen") or {}
    disease_name = first_nonempty(
        disease_overlay.get("name"),
        overlay.get("disease_name"),
        extraction.get("disease"),
        fallback.get("disease"),
    )
    specimen_site = first_nonempty(
        specimen_overlay.get("site"),
        overlay.get("specimen_site"),
        extraction.get("specimen"),
        fallback.get("specimen"),
    )
    tumor_percentage = first_nonempty(
        specimen_overlay.get("tumor_percentage"),
        overlay.get("tumor_percentage"),
        extraction.get("tumor_percentage"),
        fallback.get("tumor_percentage"),
    )

    provisional = {
        "case_id": str(
            first_nonempty(
                overlay.get("case_id"),
                raw.get("case_id"),
                bundle.get("case_id"),
                stable_id("case", raw),
            )
        ),
        "session_id": first_nonempty(
            overlay.get("session_id"), raw.get("session_id"), bundle.get("session_id")
        ),
        "source_file_id": first_nonempty(
            overlay.get("source_file_id"),
            raw.get("source_file_id"),
            extraction.get("source_file_id"),
        ),
        "report_type": first_nonempty(
            overlay.get("report_type"), extraction.get("report_type"), "NGS"
        ),
        "disease": DiseaseContext(
            name=disease_name,
            stage=first_nonempty(disease_overlay.get("stage"), overlay.get("stage")),
            setting=first_nonempty(
                disease_overlay.get("setting"), overlay.get("disease_setting")
            ),
            histology=first_nonempty(
                disease_overlay.get("histology"), overlay.get("histology"), disease_name
            ),
        ),
        "specimen": SpecimenContext(
            site=specimen_site,
            collection_date=first_nonempty(
                specimen_overlay.get("collection_date"), overlay.get("collection_date")
            ),
            tumor_percentage=float(tumor_percentage)
            if tumor_percentage not in (None, "")
            else None,
            specimen_type=first_nonempty(
                specimen_overlay.get("specimen_type"), overlay.get("specimen_type")
            ),
        ),
        "prior_therapies": list(overlay.get("prior_therapies") or []),
        "line_of_therapy": overlay.get("line_of_therapy"),
        "performance_status": overlay.get("performance_status"),
        "organ_function": dict(overlay.get("organ_function") or {}),
        "measurable_disease": overlay.get("measurable_disease"),
        "biopsy_feasibility": overlay.get("biopsy_feasibility"),
        "location": overlay.get("location"),
        "matched_normal_available": first_nonempty(
            overlay.get("matched_normal_available"),
            fallback.get("matched_normal_available"),
        ),
        "validation_status": first_nonempty(
            overlay.get("validation_status"),
            decision_brief.get("validation_status"),
            "needs_review",
        ),
        "report_date": first_nonempty(
            overlay.get("report_date"), fallback.get("report_date")
        ),
    }

    missing_checks = {
        "disease.name": provisional["disease"].name,
        "disease.stage": provisional["disease"].stage,
        "disease.setting": provisional["disease"].setting,
        "prior_therapies": provisional["prior_therapies"],
        "line_of_therapy": provisional["line_of_therapy"],
        "performance_status": provisional["performance_status"],
        "organ_function": provisional["organ_function"],
        "measurable_disease": provisional["measurable_disease"],
        "biopsy_feasibility": provisional["biopsy_feasibility"],
        "location": provisional["location"],
    }
    provisional["missing_context"] = [
        key for key, value in missing_checks.items() if value in (None, "", [], {})
    ]
    return CaseContext(**provisional)


def auto_pluck_findings(
    raw: Mapping[str, Any], case: CaseContext
) -> tuple[
    list[CanonicalFinding],
    list[CanonicalFinding],
    list[CanonicalFinding],
    list[TechnicalLimitation],
    list[PatientEvidence],
]:
    """
    Conservative default plucker for isolated testing.

    In production, callers may supply a preselected actionable JSON. This
    fallback exists so the provided Translume review packet can be exercised
    end-to-end without an external plucking service.
    """

    bundle = raw.get("bundle") or {}
    extraction = bundle.get("extraction") or {}
    decision_brief = bundle.get("decision_brief") or {}
    chunk_index = chunks_by_id(raw)

    decision_actionable_genes = {
        normalized_gene_label(item.get("alteration_or_marker") or item.get("biology"))
        for item in decision_brief.get("actionable_biology", [])
        if isinstance(item, Mapping)
    }
    # Extract standalone gene tokens from biology prose.
    for item in decision_brief.get("actionable_biology", []):
        text = (
            normalize_whitespace((item or {}).get("biology"))
            if isinstance(item, Mapping)
            else ""
        )
        decision_actionable_genes.update(re.findall(r"\b[A-Z][A-Z0-9-]{1,15}\b", text))

    ranked_biomarkers = {
        normalized_gene_label(gene)
        for item in decision_brief.get("ranked_treatment_options", [])
        if isinstance(item, Mapping)
        for gene in item.get("matched_biomarkers", [])
    }

    trial_mentions = trial_mentions_from_chunks(raw)
    evidence_registry: list[PatientEvidence] = []
    records: list[CanonicalFinding] = []

    for finding in extraction.get("molecular_findings", []):
        if not isinstance(finding, Mapping):
            continue
        source_chunk = chunk_index.get(str(finding.get("source_chunk_id")))
        priority = classify_finding_priority(
            finding,
            source_chunk,
            decision_actionable_genes,
            ranked_biomarkers,
        )
        if priority is None:
            continue

        gene = normalized_gene_label(finding.get("gene"))
        alteration = normalize_whitespace(finding.get("alteration"))
        alteration_type = normalize_whitespace(finding.get("alteration_type"))
        source_text = normalize_whitespace(finding.get("source_text"))
        if not source_text and source_chunk:
            source_text = normalize_whitespace(source_chunk.get("source_text"))
        raw_id = str(
            finding.get("finding_id")
            or stable_id("raw_finding", gene, alteration, source_text)
        )
        page = finding.get("source_page")
        if page is None and source_chunk:
            page = source_chunk.get("page_start")
        page_int = int(page) if isinstance(page, (int, float)) else None
        evidence = make_patient_evidence(
            "finding", raw_id, source_text or f"{gene} {alteration}", page_int
        )
        evidence_registry.append(evidence)

        related_trials = [
            mention["trial_id"]
            for mention in trial_mentions
            if trial_mention_matches_finding(
                gene,
                alteration,
                alteration_type,
                normalize_whitespace(mention.get("title_or_context")),
            )
        ]
        # Existing report-level trial context is a strong actionability signal,
        # but only promote a well-extracted, directionally matching finding.
        if (
            priority == "SECONDARY"
            and related_trials
            and normalize_confidence(finding.get("confidence")) >= 0.75
        ):
            priority = "PRIMARY"
        section = normalize_whitespace((source_chunk or {}).get("section"))
        reported_category = (
            "potentially_actionable"
            if "potentially_actionable" in section.lower()
            or "potentially actionable" in source_text.lower()
            else "biologically_relevant"
            if "biologically_relevant" in section.lower()
            or "biologically relevant" in source_text.lower()
            else "technical_limitation"
            if priority == "TECHNICAL"
            else "context"
            if priority == "CONTEXT"
            else None
        )
        roles = {
            "PRIMARY": ["tumor_biology", "therapeutic_biomarker", "trial_biomarker"],
            "SECONDARY": ["tumor_biology", "exploratory_biomarker"],
            "CONTEXT": ["contextual_biomarker"],
            "TECHNICAL": ["technical_limitation"],
        }[priority]

        records.append(
            CanonicalFinding(
                finding_id=stable_id(
                    "finding", raw_id, gene, alteration, alteration_type
                ),
                raw_finding_ids=[raw_id],
                gene_or_marker=gene,
                display_label=f"{gene} {alteration or alteration_type}".strip(),
                alteration=alteration,
                alteration_type=alteration_type,
                molecular_layers=classify_molecular_layer(
                    alteration_type, alteration, source_text
                ),
                priority=priority,
                reported_category=reported_category,
                clinical_roles=roles,
                source_pages=[page_int] if page_int is not None else [],
                source_chunk_ids=[str(finding.get("source_chunk_id"))]
                if finding.get("source_chunk_id")
                else [],
                source_texts=[source_text] if source_text else [],
                patient_evidence_ids=[evidence.evidence_id],
                confidence=normalize_confidence(finding.get("confidence")),
                needs_human_review=bool(finding.get("needs_human_review", True)),
                research_use_only=bool(finding.get("research_use_only", False)),
                related_finding_ids=[],
                contradictions=[],
                missing_validation=infer_missing_validation(
                    gene, alteration, alteration_type, case.matched_normal_available
                ),
                existing_drug_mentions=[],
                existing_trial_ids=unique_preserve_order(related_trials),
            )
        )

    merged = group_finding_records(records)
    actionable = [item for item in merged if item.priority == "PRIMARY"]
    secondary = [item for item in merged if item.priority == "SECONDARY"]
    context = [item for item in merged if item.priority == "CONTEXT"]
    technical_findings = [item for item in merged if item.priority == "TECHNICAL"]

    technical_limitations: list[TechnicalLimitation] = []
    for item in technical_findings:
        limitation = TechnicalLimitation(
            limitation_id=stable_id("lim", item.finding_id),
            label=item.display_label,
            description="; ".join(item.source_texts) or item.alteration,
            source_pages=item.source_pages,
            source_chunk_ids=item.source_chunk_ids,
            patient_evidence_ids=item.patient_evidence_ids,
            clinical_effect="Do not interpret a non-call or low-coverage region as a true negative.",
            conditional_follow_up=f"Orthogonal testing should be considered only if {item.gene_or_marker} is clinically relevant.",
        )
        technical_limitations.append(limitation)

    for index, limitation_text in enumerate(
        extraction.get("assay_limitations", []), start=1
    ):
        raw_limitation = normalize_whitespace(str(limitation_text))
        referenced_chunk = chunk_index.get(raw_limitation)
        text = (
            normalize_whitespace(referenced_chunk.get("source_text"))
            if referenced_chunk
            else raw_limitation
        )
        raw_page = referenced_chunk.get("page_start") if referenced_chunk else None
        page = int(raw_page) if isinstance(raw_page, (int, float)) else None
        if not text:
            continue
        evidence = make_patient_evidence(
            "limitation", f"assay_limitation_{index}", text, page
        )
        evidence_registry.append(evidence)
        technical_limitations.append(
            TechnicalLimitation(
                limitation_id=stable_id("lim", "assay", index, text),
                label="Assay limitation",
                description=text,
                source_pages=[page] if page is not None else [],
                source_chunk_ids=[raw_limitation] if referenced_chunk else [],
                patient_evidence_ids=[evidence.evidence_id],
                clinical_effect="Preserve this limitation when interpreting negative or uncertain results.",
                conditional_follow_up=None,
            )
        )

    return (
        actionable,
        secondary,
        context,
        unique_preserve_order(technical_limitations),
        unique_preserve_order(evidence_registry),
    )


def build_existing_context(raw: Mapping[str, Any]) -> ExistingContext:
    bundle = raw.get("bundle") or {}
    decision = bundle.get("decision_brief") or {}
    evidence_context = bundle.get("evidence_context") or {}
    confirmatory = bundle.get("confirmatory") or {}
    return ExistingContext(
        phenotype_axes=copy.deepcopy((bundle.get("phenotype") or {}).get("axes", [])),
        treatment_matrix=copy.deepcopy((bundle.get("matrix") or {}).get("rows", [])),
        confirmatory_tests=copy.deepcopy(confirmatory.get("tests", [])),
        must_not_assume=copy.deepcopy(confirmatory.get("must_not_assume", [])),
        tumor_behavior=copy.deepcopy(bundle.get("tumor_behavior") or {}),
        ranked_treatment_hints=copy.deepcopy(
            decision.get("ranked_treatment_options", [])
        ),
        treatment_pressure_hints=copy.deepcopy(
            decision.get("treatment_pressure_map", [])
        ),
        resistance_hints=copy.deepcopy(decision.get("resistance_forecast", [])),
        biomarker_watch_hints=copy.deepcopy(decision.get("biomarker_watch_list", [])),
        retesting_triggers=copy.deepcopy(decision.get("retesting_triggers", [])),
        next_test_hints=copy.deepcopy(decision.get("next_test_recommendations", [])),
        evidence_limitations=copy.deepcopy(decision.get("evidence_limitations", [])),
        missing_evidence=copy.deepcopy(evidence_context.get("missing_evidence", [])),
        conflicting_evidence=copy.deepcopy(
            evidence_context.get("conflicting_evidence", [])
        ),
        reasoning_warnings=copy.deepcopy(
            (evidence_context.get("medea_reasoning") or {}).get("warnings", [])
        ),
        existing_trial_mentions=trial_mentions_from_chunks(raw),
    )


def build_provenance_input(raw: Mapping[str, Any]) -> ProvenanceInput:
    bundle = raw.get("bundle") or {}
    decision = bundle.get("decision_brief") or {}
    return ProvenanceInput(
        evidence_sentences=copy.deepcopy(decision.get("evidence_sentence_map", [])),
        claims=copy.deepcopy(bundle.get("claims", [])),
        artifact_records=copy.deepcopy(bundle.get("provenance", [])),
    )


def build_canonical_input(
    raw: Mapping[str, Any],
    actionable_override: Mapping[str, Any] | Sequence[Mapping[str, Any]] | None = None,
    clinical_overlay: Mapping[str, Any] | None = None,
) -> CanonicalInput:
    case = build_case_context(raw, clinical_overlay)

    if actionable_override is not None:
        if (
            isinstance(actionable_override, Mapping)
            and "actionable_findings" in actionable_override
        ):
            primary_raw = actionable_override.get("actionable_findings", [])
            secondary_raw = actionable_override.get("secondary_findings", [])
            context_raw = actionable_override.get("context_findings", [])
            technical_raw = actionable_override.get("technical_limitations", [])
        elif isinstance(actionable_override, Sequence) and not isinstance(
            actionable_override, (str, bytes, bytearray)
        ):
            primary_raw = actionable_override
            secondary_raw = []
            context_raw = []
            technical_raw = []
        else:
            raise ValueError(
                "Actionable override must be a list or an object with actionable_findings."
            )

        actionable = [adapt_preselected_finding(item, case) for item in primary_raw]
        secondary = [adapt_preselected_finding(item, case) for item in secondary_raw]
        context = [adapt_preselected_finding(item, case) for item in context_raw]
        technical_limitations: list[TechnicalLimitation] = []
        patient_evidence: list[PatientEvidence] = []
        for finding in actionable + secondary + context:
            source_ids = (
                finding.source_chunk_ids
                or finding.raw_finding_ids
                or [finding.finding_id]
            )
            source_texts = finding.source_texts or [finding.display_label]
            source_pages: list[int | None] = list(finding.source_pages) or [None]
            for index, source_id in enumerate(source_ids):
                text = source_texts[min(index, len(source_texts) - 1)]
                page = source_pages[min(index, len(source_pages) - 1)]
                evidence = make_patient_evidence("finding", source_id, text, page)
                patient_evidence.append(evidence)
        for index, item in enumerate(technical_raw, start=1):
            if isinstance(item, TechnicalLimitation):
                technical_limitations.append(item)
                continue
            description = normalize_whitespace(
                item.get("description") or item.get("label") or str(item)
            )
            limitation_id = str(
                item.get("limitation_id") or stable_id("lim", index, description)
            )
            technical_limitations.append(
                TechnicalLimitation(
                    limitation_id=limitation_id,
                    label=normalize_whitespace(item.get("label"))
                    or "Technical limitation",
                    description=description,
                    source_pages=list(item.get("source_pages") or []),
                    source_chunk_ids=list(item.get("source_chunk_ids") or []),
                    patient_evidence_ids=list(item.get("patient_evidence_ids") or []),
                    clinical_effect=normalize_whitespace(item.get("clinical_effect"))
                    or "Preserve this limitation in interpretation.",
                    conditional_follow_up=item.get("conditional_follow_up"),
                )
            )
    else:
        actionable, secondary, context, technical_limitations, patient_evidence = (
            auto_pluck_findings(raw, case)
        )

    # Add raw claim evidence to the registry without using it as ground truth.
    for claim in deep_get(raw, ("bundle", "claims"), []) or []:
        if not isinstance(claim, Mapping) or not claim.get("claim_id"):
            continue
        patient_evidence.append(
            make_patient_evidence(
                "claim",
                str(claim["claim_id"]),
                normalize_whitespace(claim.get("claim")),
                None,
            )
        )

    return CanonicalInput(
        case=case,
        actionable_findings=actionable,
        secondary_findings=secondary,
        context_findings=context,
        technical_limitations=technical_limitations,
        negative_findings=[
            normalize_whitespace(str(item))
            for item in deep_get(raw, ("bundle", "extraction", "negative_findings"), [])
            or []
        ],
        existing_context=build_existing_context(raw),
        patient_evidence=unique_preserve_order(patient_evidence),
        provenance=build_provenance_input(raw),
    )


def compact_internal_context(context: ExistingContext) -> dict[str, Any]:
    """Prune noisy internal hints before sending them to the model."""

    return {
        "phenotype_axes": context.phenotype_axes[:20],
        "confirmatory_tests": context.confirmatory_tests[:20],
        "must_not_assume": context.must_not_assume[:20],
        "tumor_behavior": context.tumor_behavior,
        "ranked_treatment_hints": context.ranked_treatment_hints[:20],
        "resistance_hints": context.resistance_hints[:20],
        "retesting_triggers": context.retesting_triggers[:20],
        "next_test_hints": context.next_test_hints[:20],
        "evidence_limitations": context.evidence_limitations[:20],
        "missing_evidence": context.missing_evidence[:20],
        "conflicting_evidence": context.conflicting_evidence[:20],
        "reasoning_warnings": context.reasoning_warnings[:20],
        "existing_trial_mentions": context.existing_trial_mentions[:30],
    }


# ---------------------------------------------------------------------------
# VERSIONED PROMPT TEMPLATES
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PromptSpec:
    name: str
    version: str
    system: str
    user_label: str
    max_output_tokens: int
    reasoning_effort: str | None = None


PROMPTS: dict[str, PromptSpec] = {
    "hypothesis_builder": PromptSpec(
        name="hypothesis_builder",
        version=f"{PROMPT_SET_VERSION}.hypothesis",
        max_output_tokens=12_000,
        reasoning_effort="medium",
        user_label="CANONICAL CASE INPUT",
        system="""
You are a precision-oncology biological-hypothesis builder.

The input has already been filtered to retain clinically relevant findings.
Do not repeat broad extraction. Do not search the internet. Do not introduce a
therapy, drug, trial, mechanism, or biomarker that is not justified by the
supplied records.

Group related findings into clinically coherent hypotheses. A hypothesis may
represent oncogenic signaling, tumor-suppressor loss, DNA-damage response,
cell-cycle dysregulation, metabolic vulnerability, immune context, fusion or
rearrangement biology, resistance biology, diagnostic/prognostic biology, or a
technical limitation.

Rules:
- Merge findings only when they represent the same region, molecular state, or
  therapeutic vulnerability.
- Keep DNA, RNA, protein, immune, and technical evidence distinct.
- Technical limitations are not tumor alterations.
- A VUS, expression-only signal, or research-use-only observation is not a
  validated therapeutic biomarker without explicit support.
- Preserve patient evidence IDs from the input.
- Missing stage, line of therapy, organ function, performance status, biopsy
  feasibility, or prior therapy must remain unknown.
- Use conservative clinical language suitable for later clinician review.

Return a response that exactly matches the supplied structured-output schema.
""".strip(),
    ),
    "research_planner": PromptSpec(
        name="research_planner",
        version=f"{PROMPT_SET_VERSION}.research_plan",
        max_output_tokens=14_000,
        reasoning_effort="medium",
        user_label="HYPOTHESES AND CASE CONTEXT",
        system="""
You are a precision-oncology evidence-planning engine.

Generate a bounded research plan needed to build a clinician-facing actionable
packet. Do not perform searches. Do not invent URLs, publications, agents,
trial identifiers, approvals, or guideline statements.

For each hypothesis, select only the questions that can materially affect one
or more report sections: biomarker validity, disease-specific relevance,
mechanism, regulatory/standard-care status, human clinical evidence, current
clinical trials, confirmation requirements, population alignment, resistance,
or monitoring/retesting.

Do not create every question type automatically. Technical-only hypotheses
normally require no external research. A VUS without credible functional or
clinical evidence should not fan out into treatment searches.

Each job must have one focused clinical question, explicit search concepts,
preferred source roles, a bounded source count, and a stop condition. Missing
clinical context must be carried forward rather than inferred.

Return a response that exactly matches the supplied structured-output schema.
""".strip(),
    ),
    "source_discovery": PromptSpec(
        name="source_discovery",
        version=f"{PROMPT_SET_VERSION}.source_discovery",
        max_output_tokens=10_000,
        reasoning_effort="medium",
        user_label="RESEARCH JOB AND MINIMAL PATIENT ANCHOR",
        system="""
You are an evidence-retrieval agent for a precision-oncology reporting system.
Use the web search tool and search only for the supplied research job.

Prioritize, in order:
1. Current authoritative records.
2. Primary human clinical evidence.
3. Primary mechanistic studies.
4. Official current clinical-trial records.
5. Regulatory or guideline evidence.
6. High-quality reviews when primary evidence is insufficient.

Reject sources that merely mention a gene, duplicate the same study, are trial
mirror sites when an official record exists, are unsupported promotional
pages, or cannot contribute to the requested report section. Medical news and
sponsor pages may be secondary context but must not be the sole support for a
treatment claim.

Return fully qualified https:// URLs. Preserve DOI, PMID, PMCID, and NCT IDs
when available. Do not write the patient report, recommend treatment, or infer
trial eligibility. Return only sources that you actually consulted through web
search.

Return a response that exactly matches the supplied structured-output schema.
""".strip(),
    ),
    "source_extractor": PromptSpec(
        name="source_extractor",
        version=f"{PROMPT_SET_VERSION}.source_extractor",
        max_output_tokens=14_000,
        reasoning_effort="low",
        user_label="TARGET SOURCE",
        system="""
You are a clinical-evidence extractor.

Use web search to open and inspect the exact target URL supplied by the user.
Do not substitute a different article or trial record. Extract only what the
source itself reports. Do not compare it with the patient, make treatment
recommendations, or fill absent fields by inference.

Distinguish study design, population, biomarker definition, intervention,
outcomes, toxicity, trial status, mechanism, resistance, monitoring, and author
limitations. For trial records, capture current status, phase, locations, and
important eligibility criteria. For mechanism papers, do not fabricate human
outcomes. For news or sponsor pages, label the evidence level accordingly.

The source_identity.url must be the same fully qualified target URL or its
canonical redirect. When a fact is not reported, add it to facts_not_reported.
Keep support excerpts short and source-specific.

Return a response that exactly matches the supplied structured-output schema.
""".strip(),
    ),
    "source_fit": PromptSpec(
        name="source_fit",
        version=f"{PROMPT_SET_VERSION}.source_fit",
        max_output_tokens=14_000,
        reasoning_effort="medium",
        user_label="PATIENT HYPOTHESIS AND EXTRACTED SOURCE",
        system="""
You are a precision-oncology patient-to-source evidence-fit assessor.

Compare one patient-specific hypothesis with one extracted source. Preserve a
strict boundary between:
- molecular fit;
- disease and population fit;
- evidence maturity;
- standard-care readiness;
- clinical-trial screening value.

A strong molecular match must not inflate clinical actionability. A mechanism
paper cannot establish treatment efficacy. A trial record cannot establish
response. A news article cannot outrank its primary source. Missing patient
fields remain unknown.

Produce the same content types used by the reference PDF's URL-by-URL appendix:
source identity, relevant pathway, opening assessment, question/strength/why
score rows, why the fit is strong, what would strengthen candidacy, what
weakens the case, case-specific readout, safe clinical framing, explicit
language not to use, preferred language, follow-up actions, and final judgment.

All URLs must be fully qualified. Preserve patient evidence IDs and source IDs.
No statement may claim that an investigational therapy is proven or standard
care unless the extracted source explicitly supports that status.

Return a response that exactly matches the supplied structured-output schema.
""".strip(),
    ),
    "trial_prescreen": PromptSpec(
        name="trial_prescreen",
        version=f"{PROMPT_SET_VERSION}.trial_prescreen",
        max_output_tokens=10_000,
        reasoning_effort="medium",
        user_label="PATIENT DATA AND CURRENT TRIAL RECORD",
        system="""
You are a clinical-trial pre-screening engine. This is not a final eligibility
determination.

For each relevant inclusion or exclusion criterion, classify the available
information as MATCH, POSSIBLE_MATCH, MISMATCH, UNKNOWN, or NOT_ASSESSABLE.
Never infer performance status, organ function, measurable disease, washout
periods, prior treatment, biopsy feasibility, reproductive requirements, or
concomitant-therapy restrictions.

Current trial status, last update, biomarker definition, tumor-type fit,
disease-setting fit, missing information, and site/geography must be explicit.
A trial's existence does not establish eligibility or clinical benefit.

Return a response that exactly matches the supplied structured-output schema.
""".strip(),
    ),
    "hypothesis_synthesis": PromptSpec(
        name="hypothesis_synthesis",
        version=f"{PROMPT_SET_VERSION}.hypothesis_synthesis",
        max_output_tokens=18_000,
        reasoning_effort="high",
        user_label="HYPOTHESIS EVIDENCE BUNDLE",
        system="""
You are a precision-oncology evidence synthesizer.

Synthesize all evaluated sources for one patient-specific biological
hypothesis. Weight evidence in this order:
1. Regulatory or guideline evidence.
2. Prospective human clinical trials.
3. Other human clinical evidence.
4. Disease-matched translational evidence.
5. Mechanistic or preclinical evidence.
6. Expert commentary, medical news, or sponsor material.

Do not count duplicate sources as independent confirmation. Do not convert
mechanism into efficacy. Explicitly identify missing population alignment,
conflicting evidence, and evidence gaps. Separate standard care, off-label
rationale, investigational opportunities, biologic rationale only, and
unsupported options.

Resistance without direct evidence must be labeled mechanistically plausible
or speculative. Confirmatory tests must be tied to the patient finding or a
trial's biomarker requirement. Preserve patient evidence IDs and external
source IDs for every report-ready claim.

Return a response that exactly matches the supplied structured-output schema.
""".strip(),
    ),
    "report_compiler": PromptSpec(
        name="report_compiler",
        version=f"{PROMPT_SET_VERSION}.report_compiler",
        max_output_tokens=40_000,
        reasoning_effort="high",
        user_label="VALIDATED REPORT ARTIFACTS",
        system="""
You are the final compiler for a Precision Oncology Actionable Packet.

Use only the supplied patient findings, hypothesis syntheses, source-fit
assessments, trial pre-screens, technical limitations, and selected source
metadata. Do not search. Do not introduce a new therapy, trial, mechanism,
fact, or citation. Do not hide population mismatch. Do not treat a technical
non-call as a negative result. Do not turn investigational rationale into a
treatment recommendation.

Generate the same main-report content types and flow as the reference PDF:
- purpose and case metadata;
- executive summary and four top takeaways;
- key findings table and other findings;
- cause-and-effect chains with plain-English explanations;
- therapy options and clinical rationale;
- practical readout;
- resistance and escape routes;
- follow-up testing;
- future phenotypic events and retesting triggers;
- limitations and confidence boundaries;
- selected fully qualified reference and trial URLs;
- bottom line;
- URL-assessment appendix overview and source index.

Every substantive row or paragraph must carry patient evidence IDs and/or
external source IDs. Preserve uncertainty and clinician-review language. The
output is educational support and not a substitute for physician judgment.

Return a response that exactly matches the supplied structured-output schema.
""".strip(),
    ),
    "cross_source_synthesis": PromptSpec(
        name="cross_source_synthesis",
        version=f"{PROMPT_SET_VERSION}.cross_source",
        max_output_tokens=10_000,
        reasoning_effort="medium",
        user_label="HYPOTHESIS SYNTHESES AND SOURCE ASSESSMENTS",
        system="""
Produce a concise cross-source synthesis for the URL appendix.

Do not introduce new facts or count duplicate sources twice. Rank themes by
clinical significance and evidence maturity. Separate molecular rationale,
trial-screening value, and standard-care readiness. Preserve uncertainty,
confirmatory requirements, and all supporting source IDs.

The content must match the reference PDF's final appendix section: summary,
theme/conclusion/evidence-maturity/clinical-role rows, practical bottom line,
and source IDs.

Return a response that exactly matches the supplied structured-output schema.
""".strip(),
    ),
    "validator_claim_grounding": PromptSpec(
        name="validator_claim_grounding",
        version=f"{PROMPT_SET_VERSION}.validator.claims",
        max_output_tokens=12_000,
        reasoning_effort="high",
        user_label="REPORT, EVIDENCE, AND SOURCE REGISTRY",
        system="""
You are a claim-grounding validator for a precision-oncology report.

For every material claim, verify that its patient evidence IDs and external
source IDs support the exact wording. Flag unsupported causality, stronger
language than evidence permits, missing provenance, or a source that does not
support the statement. Return PASS, REVISE, or REMOVE findings. Do not add new
clinical facts.

Return a response that exactly matches the supplied structured-output schema.
""".strip(),
    ),
    "validator_population": PromptSpec(
        name="validator_population",
        version=f"{PROMPT_SET_VERSION}.validator.population",
        max_output_tokens=10_000,
        reasoning_effort="high",
        user_label="THERAPY/TRIAL STATEMENTS AND PATIENT CONTEXT",
        system="""
You are a patient-population alignment validator.

Review every therapy and trial statement against tumor type, histology,
disease setting, stage, line of therapy, prior treatment, biomarker definition,
assay requirement, performance status, organ function, trial status, and
location. Missing data must remain UNKNOWN. Trial existence must not be
presented as eligibility or benefit. Return PASS, REVISE, or REMOVE findings.
Do not add new clinical facts.

Return a response that exactly matches the supplied structured-output schema.
""".strip(),
    ),
    "validator_safety": PromptSpec(
        name="validator_safety",
        version=f"{PROMPT_SET_VERSION}.validator.safety",
        max_output_tokens=10_000,
        reasoning_effort="high",
        user_label="FULL REPORT ARTIFACT",
        system="""
You are a clinical-safety and contradiction validator.

Detect VUS treated as pathogenic, expression-only signals treated as established
drivers, technical non-calls treated as negatives, pharmacogenomic findings
treated as tumor drivers, mechanism treated as efficacy, trial records treated
as response evidence, closed or historical trials presented as current, news
articles used as sole support, contradictory DNA/RNA/protein evidence, or
recommendations stronger than the evidence permits.

Return PASS, REVISE, or REMOVE findings. Do not add new clinical facts.
Return a response that exactly matches the supplied structured-output schema.
""".strip(),
    ),
}


def prompt_payload(label: str, payload: Mapping[str, Any] | Sequence[Any]) -> str:
    return f"{label}:\n{json.dumps(payload, indent=2, ensure_ascii=False, default=str)}"


# ---------------------------------------------------------------------------
# ARTIFACT STORE AND CACHE — SIDE EFFECT BOUNDARY
# ---------------------------------------------------------------------------


class ArtifactStore:
    def __init__(self, root: Path, run_id: str) -> None:
        self.root = root
        self.run_id = run_id
        self.run_dir = root / run_id
        self.cache_dir = root / "_cache"
        self.artifact_dir = self.run_dir / "artifacts"
        self.call_dir = self.run_dir / "calls"
        self.run_dir.mkdir(parents=True, exist_ok=True)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.artifact_dir.mkdir(parents=True, exist_ok=True)
        self.call_dir.mkdir(parents=True, exist_ok=True)

    def cache_path(self, cache_key: str) -> Path:
        return self.cache_dir / f"{cache_key}.json"

    def load_cache(self, cache_key: str) -> dict[str, Any] | None:
        path = self.cache_path(cache_key)
        return read_json(path) if path.exists() else None

    def save_cache(self, cache_key: str, payload: Mapping[str, Any]) -> None:
        atomic_write_json(self.cache_path(cache_key), dict(payload))

    def save_artifact(self, artifact: ArtifactEnvelope) -> None:
        atomic_write_json(
            self.artifact_dir / f"{artifact.artifact_id}.json",
            artifact.model_dump(mode="json"),
        )

    def save_call_audit(self, call_id: str, payload: Mapping[str, Any]) -> None:
        atomic_write_json(self.call_dir / f"{call_id}.json", dict(payload))

    def save_checkpoint(self, state: PipelineState) -> None:
        atomic_write_json(self.run_dir / "checkpoint.json", serialize_state(state))

    def save_final(self, packet: FinalPacket) -> Path:
        path = self.run_dir / "precision_oncology_packet.json"
        atomic_write_json(path, packet.model_dump(mode="json"))
        return path

    def save_schema(self) -> Path:
        path = self.run_dir / "precision_oncology_packet.schema.json"
        atomic_write_json(path, FinalPacket.model_json_schema())
        return path


# ---------------------------------------------------------------------------
# OPENAI RESPONSES API GATEWAY — SIDE EFFECT BOUNDARY
# ---------------------------------------------------------------------------


def recursive_web_sources(value: Any) -> list[WebSource]:
    """Extract URL/title pairs from SDK response dictionaries defensively."""

    if isinstance(value, BaseModel):
        value = value.model_dump(mode="json")
    elif hasattr(value, "model_dump"):
        try:
            value = value.model_dump(mode="json")
        except Exception:
            value = value.model_dump()

    found: list[WebSource] = []

    def walk(node: Any) -> None:
        if isinstance(node, Mapping):
            url = node.get("url")
            title = node.get("title")
            if is_fully_qualified_url(str(url) if url is not None else None):
                found.append(
                    WebSource(
                        url=normalize_url(str(url)),
                        title=normalize_whitespace(str(title or url)),
                        type=normalize_whitespace(str(node.get("type"))) or None,
                    )
                )
            for child in node.values():
                walk(child)
        elif isinstance(node, Sequence) and not isinstance(
            node, (str, bytes, bytearray)
        ):
            for child in node:
                walk(child)

    walk(value)
    unique: dict[str, WebSource] = {}
    for item in found:
        unique.setdefault(item.url, item)
    return list(unique.values())


class OpenAIResponsesGateway:
    """Synchronous OpenAI SDK adapter wrapped for async orchestration."""

    def __init__(self, config: PipelineConfig, store: ArtifactStore) -> None:
        self.config = config
        self.store = store
        self._semaphore = asyncio.Semaphore(config.max_concurrency)
        self._client: Any | None = None

    def _get_client(self) -> Any:
        if self._client is not None:
            return self._client
        try:
            from openai import OpenAI
        except ImportError as exc:  # pragma: no cover
            raise RuntimeError(
                "Install the official OpenAI Python SDK: pip install 'openai>=2.0.0'."
            ) from exc
        if not self.config.api_key:
            raise RuntimeError(
                "OPENAI_API_KEY is empty. Set the environment variable or use --api-key."
            )
        self._client = OpenAI(
            api_key=self.config.api_key,
            timeout=self.config.request_timeout_seconds,
            max_retries=0,
        )
        return self._client

    async def structured_call(
        self,
        *,
        stage: str,
        artifact_id: str,
        prompt: PromptSpec,
        payload: Mapping[str, Any] | Sequence[Any],
        response_model: type[T],
        use_web: bool = False,
        allowed_domains: Sequence[str] = (),
        required_web: bool = False,
    ) -> ModelResult[T]:
        request_descriptor = {
            "stage": stage,
            "artifact_id": artifact_id,
            "prompt_name": prompt.name,
            "prompt_version": prompt.version,
            "model": self.config.model,
            "reasoning_effort": prompt.reasoning_effort or self.config.reasoning_effort,
            "payload": payload,
            "response_schema": response_model.__name__,
            "use_web": use_web,
            "allowed_domains": sorted(set(allowed_domains)),
            "required_web": required_web,
            "live_web_access": self.config.live_web_access,
            "web_return_token_budget": self.config.web_return_token_budget,
        }
        cache_key = stable_id("cache", request_descriptor, length=32)
        if self.config.resume:
            cached = self.store.load_cache(cache_key)
            if cached:
                parsed = response_model.model_validate(cached["parsed"])
                web_sources = tuple(
                    WebSource(**item) for item in cached.get("web_sources", [])
                )
                return ModelResult(
                    parsed=parsed,
                    response_id=cached.get("response_id"),
                    model=cached.get("model", self.config.model),
                    usage=cached.get("usage", {}),
                    web_sources=web_sources,
                    cache_hit=True,
                )

        if self.config.dry_run:
            raise RuntimeError(
                f"Dry-run reached model stage '{stage}'. Use --stop-after canonical_input "
                "to inspect parsed values without API calls."
            )

        call_id = stable_id("call", cache_key, stage, artifact_id)
        audit = {
            "call_id": call_id,
            "stage": stage,
            "artifact_id": artifact_id,
            "cache_key": cache_key,
            "prompt_name": prompt.name,
            "prompt_version": prompt.version,
            "model": self.config.model,
            "reasoning_effort": prompt.reasoning_effort or self.config.reasoning_effort,
            "response_schema": response_model.__name__,
            "use_web": use_web,
            "allowed_domains": sorted(set(allowed_domains)),
            "created_at": utc_now_iso(),
            "payload_hash": sha256_text(canonical_json(payload)),
        }
        if self.config.store_prompt_payloads:
            audit["payload"] = payload
        self.store.save_call_audit(call_id, audit)

        async with self._semaphore:
            result = await asyncio.to_thread(
                self._call_with_retry,
                stage,
                prompt,
                payload,
                response_model,
                use_web,
                tuple(allowed_domains),
                required_web,
            )

        self.store.save_cache(
            cache_key,
            {
                "parsed": result.parsed.model_dump(mode="json"),
                "response_id": result.response_id,
                "model": result.model,
                "usage": result.usage,
                "web_sources": [
                    dataclasses.asdict(item) for item in result.web_sources
                ],
                "created_at": utc_now_iso(),
            },
        )
        return result

    def _call_with_retry(
        self,
        stage: str,
        prompt: PromptSpec,
        payload: Mapping[str, Any] | Sequence[Any],
        response_model: type[T],
        use_web: bool,
        allowed_domains: tuple[str, ...],
        required_web: bool,
    ) -> ModelResult[T]:
        last_error: Exception | None = None
        for attempt in range(1, self.config.max_attempts + 1):
            try:
                return self._call_once(
                    stage=stage,
                    prompt=prompt,
                    payload=payload,
                    response_model=response_model,
                    use_web=use_web,
                    allowed_domains=allowed_domains,
                    required_web=required_web,
                )
            except Exception as exc:  # SDK exception classes change over time
                last_error = exc
                status = getattr(exc, "status_code", None)
                retryable = (
                    status in {408, 409, 429, 500, 502, 503, 504} or status is None
                )
                if not retryable or attempt >= self.config.max_attempts:
                    raise
                delay = min(60.0, (2 ** (attempt - 1)) + random.uniform(0.0, 1.0))
                LOGGER.warning(
                    "OpenAI call retry stage=%s attempt=%s/%s status=%s delay=%.2fs error=%s",
                    stage,
                    attempt,
                    self.config.max_attempts,
                    status,
                    delay,
                    exc.__class__.__name__,
                )
                time.sleep(delay)
        assert last_error is not None
        raise last_error

    def _call_once(
        self,
        *,
        stage: str,
        prompt: PromptSpec,
        payload: Mapping[str, Any] | Sequence[Any],
        response_model: type[T],
        use_web: bool,
        allowed_domains: tuple[str, ...],
        required_web: bool,
    ) -> ModelResult[T]:
        client = self._get_client()
        kwargs: dict[str, Any] = {
            "model": self.config.model,
            "input": [
                {"role": "system", "content": prompt.system},
                {
                    "role": "user",
                    "content": prompt_payload(prompt.user_label, payload),
                },
            ],
            "text_format": response_model,
            "reasoning": {
                "effort": prompt.reasoning_effort or self.config.reasoning_effort
            },
            "max_output_tokens": prompt.max_output_tokens,
            "store": False,
            "metadata": {
                "pipeline": "precision-oncology-json",
                "tool_version": TOOL_VERSION,
                "stage": stage[:64],
            },
        }
        if use_web:
            tool: dict[str, Any] = {
                "type": "web_search",
                "external_web_access": self.config.live_web_access,
                "return_token_budget": self.config.web_return_token_budget,
            }
            filtered = [
                domain.removeprefix("www.") for domain in allowed_domains if domain
            ]
            # Apply the blocked-domain policy for every discovery call. Add an
            # allowlist only for exact official-source jobs. OpenAI currently
            # accepts up to 100 domains per list.
            filters: dict[str, Any] = {
                "blocked_domains": list(DEFAULT_BLOCKED_DOMAINS)[:100],
            }
            if filtered:
                filters["allowed_domains"] = unique_preserve_order(filtered)[:100]
            tool["filters"] = filters
            kwargs["tools"] = [tool]
            kwargs["tool_choice"] = "required" if required_web else "auto"
            kwargs["include"] = ["web_search_call.action.sources"]

        response = client.responses.parse(**kwargs)
        parsed = getattr(response, "output_parsed", None)
        if parsed is None:
            refusal = None
            try:
                raw = response.model_dump(mode="json")
                for item in raw.get("output", []):
                    if item.get("type") != "message":
                        continue
                    for content in item.get("content", []):
                        if content.get("type") == "refusal":
                            refusal = content.get("refusal")
            except Exception:
                refusal = None
            raise RuntimeError(
                f"OpenAI returned no parsed output for stage '{stage}'."
                + (f" Refusal: {refusal}" if refusal else "")
            )
        if not isinstance(parsed, response_model):
            parsed = response_model.model_validate(parsed)

        response_dump = (
            response.model_dump(mode="json") if hasattr(response, "model_dump") else {}
        )
        usage = response_dump.get("usage") or {}
        web_sources = tuple(recursive_web_sources(response_dump))
        return ModelResult(
            parsed=parsed,
            response_id=getattr(response, "id", None),
            model=getattr(response, "model", self.config.model) or self.config.model,
            usage=usage,
            web_sources=web_sources,
            cache_hit=False,
        )


# ---------------------------------------------------------------------------
# STATE / ARTIFACT HELPERS — PURE FUNCTIONS
# ---------------------------------------------------------------------------


def serialize_state(state: PipelineState) -> dict[str, Any]:
    return {
        "run_id": state.run_id,
        "source_input_sha256": state.source_input_sha256,
        "canonical_input": state.canonical_input.model_dump(mode="json"),
        "hypotheses": [item.model_dump(mode="json") for item in state.hypotheses],
        "research_jobs": [item.model_dump(mode="json") for item in state.research_jobs],
        "sources": [item.model_dump(mode="json") for item in state.sources],
        "source_extractions": [
            item.model_dump(mode="json") for item in state.source_extractions
        ],
        "source_fit_assessments": [
            item.model_dump(mode="json") for item in state.source_fit_assessments
        ],
        "trial_prescreens": [
            item.model_dump(mode="json") for item in state.trial_prescreens
        ],
        "hypothesis_syntheses": [
            item.model_dump(mode="json") for item in state.hypothesis_syntheses
        ],
        "report_draft": state.report_draft.model_dump(mode="json")
        if state.report_draft
        else None,
        "cross_source_synthesis": state.cross_source_synthesis.model_dump(mode="json")
        if state.cross_source_synthesis
        else None,
        "validations": [item.model_dump(mode="json") for item in state.validations],
        "artifacts": [item.model_dump(mode="json") for item in state.artifacts],
        "usage_records": [item.model_dump(mode="json") for item in state.usage_records],
        "warnings": list(state.warnings),
    }


def artifact_from_payload(
    *,
    artifact_id: str,
    artifact_type: str,
    stage: str,
    payload: BaseModel | Mapping[str, Any] | Sequence[Any],
    parents: Sequence[str],
    input_value: Any,
    prompt: PromptSpec | None = None,
    model: str | None = None,
    response_id: str | None = None,
) -> ArtifactEnvelope:
    if isinstance(payload, BaseModel):
        serialized = payload.model_dump(mode="json")
    elif isinstance(payload, Mapping):
        serialized = dict(payload)
    else:
        serialized = {"items": list(payload)}
    return ArtifactEnvelope(
        artifact_id=artifact_id,
        artifact_type=artifact_type,
        stage=stage,
        parent_artifact_ids=list(parents),
        created_at=utc_now_iso(),
        input_hash=sha256_text(canonical_json(input_value)),
        prompt_version=prompt.version if prompt else None,
        model=model,
        response_id=response_id,
        payload=serialized,
    )


def append_artifact(state: PipelineState, artifact: ArtifactEnvelope) -> PipelineState:
    return dataclasses.replace(state, artifacts=state.artifacts + (artifact,))


def append_usage(
    state: PipelineState,
    *,
    stage: str,
    artifact_id: str,
    result: ModelResult[Any],
) -> PipelineState:
    usage = UsageRecord(
        call_id=stable_id(
            "usage", stage, artifact_id, result.response_id, result.usage
        ),
        stage=stage,
        artifact_id=artifact_id,
        response_id=result.response_id,
        model=result.model,
        usage=result.usage,
        web_source_count=len(result.web_sources),
        cache_hit=result.cache_hit,
    )
    return dataclasses.replace(state, usage_records=state.usage_records + (usage,))


def append_warning(state: PipelineState, message: str) -> PipelineState:
    normalized = normalize_whitespace(message)
    if not normalized or normalized in state.warnings:
        return state
    return dataclasses.replace(state, warnings=state.warnings + (normalized,))


def replace_model_id(model: T, field_name: str, value: str) -> T:
    return model.model_copy(update={field_name: value})


def hypothesis_sort_key(item: Hypothesis) -> tuple[int, str, str]:
    priority = {"high": 0, "medium": 1, "low": 2, "none": 3}
    return (priority[item.research_priority], item.title.lower(), item.hypothesis_id)


def assign_hypothesis_ids(output: HypothesisBuilderOutput) -> tuple[Hypothesis, ...]:
    assigned: list[Hypothesis] = []
    for item in output.hypotheses:
        deterministic = stable_id(
            "hyp",
            sorted(item.primary_finding_ids),
            sorted(item.supporting_finding_ids),
            item.biological_theme.lower(),
            item.hypothesis_type.lower(),
        )
        assigned.append(item.model_copy(update={"hypothesis_id": deterministic}))
    # Collapse exact duplicate hypothesis IDs, preferring the first structured output.
    by_id: dict[str, Hypothesis] = {}
    for item in sorted(assigned, key=hypothesis_sort_key):
        by_id.setdefault(item.hypothesis_id, item)
    return tuple(by_id.values())


def assign_research_job_ids(
    output: ResearchPlanOutput,
    valid_hypothesis_ids: set[str],
    max_jobs: int,
    max_sources_per_job: int,
) -> tuple[ResearchJob, ...]:
    assigned: list[ResearchJob] = []
    priority = {"high": 0, "medium": 1, "low": 2}
    for item in output.research_jobs:
        if item.hypothesis_id not in valid_hypothesis_ids:
            continue
        deterministic = stable_id(
            "job",
            item.hypothesis_id,
            item.question_type,
            item.clinical_question.lower(),
            item.search_concepts.model_dump(mode="json"),
        )
        assigned.append(
            item.model_copy(
                update={
                    "job_id": deterministic,
                    "maximum_sources": min(item.maximum_sources, max_sources_per_job),
                }
            )
        )
    assigned.sort(
        key=lambda item: (
            priority[item.priority],
            item.hypothesis_id,
            item.question_type,
            item.job_id,
        )
    )
    # One deterministic copy of duplicate jobs.
    unique: dict[str, ResearchJob] = {}
    for item in assigned:
        unique.setdefault(item.job_id, item)
    return tuple(list(unique.values())[:max_jobs])


def findings_for_hypothesis(
    canonical: CanonicalInput, hypothesis: Hypothesis
) -> list[CanonicalFinding]:
    identifiers = set(hypothesis.primary_finding_ids) | set(
        hypothesis.supporting_finding_ids
    )
    all_findings = (
        canonical.actionable_findings
        + canonical.secondary_findings
        + canonical.context_findings
    )
    return [item for item in all_findings if item.finding_id in identifiers]


def hypothesis_by_id(state: PipelineState, hypothesis_id: str) -> Hypothesis:
    for item in state.hypotheses:
        if item.hypothesis_id == hypothesis_id:
            return item
    raise KeyError(f"Unknown hypothesis_id: {hypothesis_id}")


def source_by_id(state: PipelineState, source_id: str) -> SourceRegistryEntry:
    for item in state.sources:
        if item.source_id == source_id:
            return item
    raise KeyError(f"Unknown source_id: {source_id}")


def source_extraction_by_id(state: PipelineState, source_id: str) -> SourceExtraction:
    for item in state.source_extractions:
        if item.source_id == source_id:
            return item
    raise KeyError(f"Missing source extraction: {source_id}")


def build_minimal_patient_anchor(
    state: PipelineState, job: ResearchJob
) -> dict[str, Any]:
    hypothesis = hypothesis_by_id(state, job.hypothesis_id)
    relevant = findings_for_hypothesis(state.canonical_input, hypothesis)
    return {
        "case": {
            "disease": state.canonical_input.case.disease.model_dump(mode="json"),
            "specimen": state.canonical_input.case.specimen.model_dump(mode="json"),
            "line_of_therapy": state.canonical_input.case.line_of_therapy,
            "prior_therapies": state.canonical_input.case.prior_therapies,
            "performance_status": state.canonical_input.case.performance_status,
            "location": state.canonical_input.case.location,
            "missing_context": state.canonical_input.case.missing_context,
        },
        "hypothesis": hypothesis.model_dump(mode="json"),
        "relevant_findings": [item.model_dump(mode="json") for item in relevant],
    }


def preferred_source_domains(values: Sequence[str]) -> tuple[str, ...]:
    """Map explicit source hints to valid domains without inventing allowlists.

    Broad literature discovery intentionally remains open-web. Domain allowlists
    are reserved for exact official-record jobs such as ClinicalTrials.gov, FDA,
    and variant-database lookups; otherwise an allowlist can suppress a relevant
    journal, conference, or sponsor source that was not known in advance.
    """

    aliases = {
        "pubmed": "pubmed.ncbi.nlm.nih.gov",
        "pmc": "pmc.ncbi.nlm.nih.gov",
        "pubmed central": "pmc.ncbi.nlm.nih.gov",
        "clinicaltrials.gov": "clinicaltrials.gov",
        "clinical trials": "clinicaltrials.gov",
        "fda": "www.fda.gov",
        "civic": "civicdb.org",
        "nci": "www.cancer.gov",
    }
    domains: list[str] = []
    for value in values:
        cleaned = normalize_whitespace(value).lower()
        if not cleaned:
            continue
        if cleaned in aliases:
            domains.append(aliases[cleaned])
            continue
        candidate = (
            cleaned.removeprefix("https://")
            .removeprefix("http://")
            .split("/", 1)[0]
            .strip(".")
        )
        if "." in candidate and " " not in candidate:
            domains.append(candidate)
    return tuple(unique_preserve_order(domains))


def allowed_domains_for_job(job: ResearchJob) -> tuple[str, ...]:
    preferred = preferred_source_domains(job.preferred_sources)
    official_by_type: dict[str, tuple[str, ...]] = {
        "trial": ("clinicaltrials.gov",),
        "regulatory": ("fda.gov", "www.fda.gov"),
        "variant": (
            "ncbi.nlm.nih.gov",
            "www.ncbi.nlm.nih.gov",
            "pubmed.ncbi.nlm.nih.gov",
            "civicdb.org",
        ),
    }
    required_official = official_by_type.get(job.question_type, ())
    if required_official:
        return tuple(unique_preserve_order([*preferred, *required_official])[:100])
    # No allowlist for broad research jobs. Source quality is handled by prompt
    # policy, returned-source verification, deterministic ranking, and validators.
    return ()


def authority_score(url: str) -> float:
    host = hostname(url)
    if host in {
        "clinicaltrials.gov",
        "pubmed.ncbi.nlm.nih.gov",
        "pmc.ncbi.nlm.nih.gov",
        "ncbi.nlm.nih.gov",
        "fda.gov",
        "cancer.gov",
    }:
        return 2.0
    if any(
        host.endswith(domain)
        for domain in (
            "nature.com",
            "nejm.org",
            "thelancet.com",
            "cell.com",
            "science.org",
            "ascopubs.org",
            "aacrjournals.org",
        )
    ):
        return 1.8
    if host.endswith("esmo.org") or host.endswith("civicdb.org"):
        return 1.6
    return 0.8


def source_type_score(source_type: str) -> float:
    return {
        "regulatory": 2.0,
        "guideline": 2.0,
        "clinical_study": 2.0,
        "trial_record": 1.9,
        "primary_research": 1.7,
        "review": 1.2,
        "conference": 1.0,
        "news": 0.6,
        "sponsor": 0.5,
        "other": 0.4,
    }.get(source_type, 0.4)


def date_currentness_score(value: str | None) -> float:
    if not value:
        return 0.3
    match = re.search(r"(20\d{2})", value)
    if not match:
        return 0.3
    age = max(0, dt.datetime.now().year - int(match.group(1)))
    if age <= 1:
        return 1.0
    if age <= 3:
        return 0.8
    if age <= 5:
        return 0.5
    return 0.2


def candidate_selection_score(
    candidate: CandidateSource, verification_status: str
) -> float:
    matched = min(2.0, 0.5 * len(candidate.patient_anchor_matched))
    evidence = (
        1.0
        if any(
            term in candidate.apparent_evidence_level.lower()
            for term in ("human", "phase", "clinical", "guideline", "regulatory")
        )
        else 0.5
    )
    verified = 1.0 if verification_status == "web_verified" else 0.2
    return round(
        authority_score(candidate.canonical_url or candidate.url)
        + source_type_score(candidate.source_type)
        + matched
        + evidence
        + date_currentness_score(candidate.publication_or_update_date)
        + verified,
        3,
    )


def reconcile_candidate_with_web_sources(
    candidate: CandidateSource,
    web_sources: Sequence[WebSource],
) -> tuple[str, str, list[str]]:
    candidate_url = ensure_source_url(candidate.model_dump(mode="json"))
    if not candidate_url:
        return "", "invalid_url", []
    normalized_web = {normalize_url(item.url): item for item in web_sources}
    if candidate_url in normalized_web:
        exact = normalized_web[candidate_url]
        return candidate_url, "web_verified", [exact.url]

    candidate_host = hostname(candidate_url)
    candidate_path = urlparse(candidate_url).path.rstrip("/")
    approximate = [
        item
        for item in web_sources
        if hostname(item.url) == candidate_host
        and (
            urlparse(item.url).path.rstrip("/") == candidate_path
            or candidate_path in urlparse(item.url).path.rstrip("/")
            or urlparse(item.url).path.rstrip("/") in candidate_path
        )
    ]
    if approximate:
        return (
            normalize_url(approximate[0].url),
            "web_verified",
            [item.url for item in approximate],
        )

    # Stable identifier URLs can be canonicalized safely even if a citation
    # source returns a different publisher URL.
    ids = candidate.identifiers
    if (
        ids.nct_id
        and candidate_url == f"https://clinicaltrials.gov/study/{ids.nct_id.upper()}"
    ):
        return candidate_url, "identifier_verified", []
    if ids.doi or ids.pmid or ids.pmcid:
        return candidate_url, "identifier_verified", []
    return candidate_url, "model_only", []


def source_registry_from_discoveries(
    discoveries: Sequence[
        tuple[ResearchJob, SourceDiscoveryOutput, Sequence[WebSource]]
    ],
    strict_verification: bool,
) -> tuple[SourceRegistryEntry, ...]:
    merged: dict[str, dict[str, Any]] = {}
    for job, output, web_sources in discoveries:
        for candidate in output.candidate_sources:
            url, verification_status, consulted = reconcile_candidate_with_web_sources(
                candidate, web_sources
            )
            if not url:
                continue
            if strict_verification and verification_status == "model_only":
                continue
            candidate_data = candidate.model_dump(mode="json")
            candidate_data["canonical_url"] = url
            candidate_data["url"] = url
            key = canonical_source_key(candidate_data)
            source_id = stable_id("src", key)
            score = candidate_selection_score(
                candidate.model_copy(update={"canonical_url": url, "url": url}),
                verification_status,
            )
            record = merged.get(key)
            if record is None:
                merged[key] = {
                    "source_id": source_id,
                    "canonical_key": key,
                    "title": candidate.title,
                    "url": url,
                    "publisher": candidate.publisher,
                    "source_type": candidate.source_type,
                    "source_role": candidate.source_role,
                    "publication_or_update_date": candidate.publication_or_update_date,
                    "identifiers": candidate.identifiers,
                    "hypothesis_ids": [job.hypothesis_id],
                    "job_ids": [job.job_id],
                    "selection_score": score,
                    "verification_status": verification_status,
                    "consulted_urls": list(consulted),
                }
            else:
                record["hypothesis_ids"] = unique_preserve_order(
                    record["hypothesis_ids"] + [job.hypothesis_id]
                )
                record["job_ids"] = unique_preserve_order(
                    record["job_ids"] + [job.job_id]
                )
                record["selection_score"] = max(record["selection_score"], score)
                record["consulted_urls"] = unique_preserve_order(
                    record["consulted_urls"] + list(consulted)
                )
                # Prefer a primary/official classification over secondary content.
                if source_type_score(candidate.source_type) > source_type_score(
                    record["source_type"]
                ):
                    record["source_type"] = candidate.source_type
                    record["source_role"] = candidate.source_role
                    record["title"] = candidate.title
                    record["publisher"] = candidate.publisher
                    record["publication_or_update_date"] = (
                        candidate.publication_or_update_date
                    )
                    record["identifiers"] = candidate.identifiers

    return tuple(
        SourceRegistryEntry(**record)
        for _, record in sorted(
            merged.items(),
            key=lambda pair: (
                -pair[1]["selection_score"],
                pair[1]["source_type"],
                pair[1]["url"],
            ),
        )
    )


def seed_existing_trial_sources(
    state: PipelineState,
) -> tuple[SourceRegistryEntry, ...]:
    seeds: list[SourceRegistryEntry] = []
    for mention in state.canonical_input.existing_context.existing_trial_mentions:
        nct_id = normalize_whitespace(mention.get("trial_id")).upper()
        if not nct_id:
            continue
        url = f"https://clinicaltrials.gov/study/{nct_id}"
        matching_hypotheses = [
            hypothesis.hypothesis_id
            for hypothesis in state.hypotheses
            if any(
                finding.gene_or_marker.lower()
                in normalize_whitespace(mention.get("title_or_context")).lower()
                for finding in findings_for_hypothesis(
                    state.canonical_input, hypothesis
                )
            )
        ]
        if not matching_hypotheses:
            continue
        key = f"nct:{nct_id}"
        seeds.append(
            SourceRegistryEntry(
                source_id=stable_id("src", key),
                canonical_key=key,
                title=normalize_whitespace(mention.get("title_or_context"))[:300]
                or nct_id,
                url=url,
                publisher="ClinicalTrials.gov",
                source_type="trial_record",
                source_role="existing_report_trial_context",
                publication_or_update_date=None,
                identifiers=SourceIdentifiers(nct_id=nct_id),
                hypothesis_ids=matching_hypotheses,
                job_ids=[],
                selection_score=7.5,
                verification_status="identifier_verified",
                consulted_urls=[],
            )
        )
    return tuple(seeds)


def merge_source_registries(
    *registries: Sequence[SourceRegistryEntry],
) -> tuple[SourceRegistryEntry, ...]:
    merged: dict[str, SourceRegistryEntry] = {}
    for registry in registries:
        for source in registry:
            existing = merged.get(source.canonical_key)
            if existing is None:
                merged[source.canonical_key] = source
                continue
            preferred = (
                source
                if source.selection_score > existing.selection_score
                else existing
            )
            merged[source.canonical_key] = preferred.model_copy(
                update={
                    "hypothesis_ids": unique_preserve_order(
                        existing.hypothesis_ids + source.hypothesis_ids
                    ),
                    "job_ids": unique_preserve_order(existing.job_ids + source.job_ids),
                    "consulted_urls": unique_preserve_order(
                        existing.consulted_urls + source.consulted_urls
                    ),
                    "selection_score": max(
                        existing.selection_score, source.selection_score
                    ),
                }
            )
    return tuple(
        sorted(
            merged.values(),
            key=lambda item: (-item.selection_score, item.source_type, item.url),
        )
    )


def select_sources(
    sources: Sequence[SourceRegistryEntry],
    max_per_hypothesis: int,
    max_total: int,
) -> tuple[SourceRegistryEntry, ...]:
    """Balanced deterministic selection across hypotheses and source roles."""

    by_hypothesis: dict[str, list[SourceRegistryEntry]] = defaultdict(list)
    for source in sources:
        for hypothesis_id in source.hypothesis_ids:
            by_hypothesis[hypothesis_id].append(source)

    selected_ids: set[str] = set()
    selected: list[SourceRegistryEntry] = []
    role_order = (
        "guideline",
        "regulatory",
        "clinical_study",
        "trial_record",
        "primary_research",
        "review",
        "conference",
        "news",
        "sponsor",
        "other",
    )
    for hypothesis_id in sorted(by_hypothesis):
        candidates = sorted(
            by_hypothesis[hypothesis_id],
            key=lambda item: (
                -item.selection_score,
                role_order.index(item.source_type)
                if item.source_type in role_order
                else 99,
                item.url,
            ),
        )
        per_hypothesis: list[SourceRegistryEntry] = []
        # First pass: one top source per type.
        for source_type in role_order:
            match = next(
                (
                    item
                    for item in candidates
                    if item.source_type == source_type
                    and item.source_id not in selected_ids
                ),
                None,
            )
            if match:
                per_hypothesis.append(match)
                selected_ids.add(match.source_id)
                if len(per_hypothesis) >= max_per_hypothesis:
                    break
        # Second pass: fill by score.
        if len(per_hypothesis) < max_per_hypothesis:
            for item in candidates:
                if item.source_id in selected_ids:
                    continue
                per_hypothesis.append(item)
                selected_ids.add(item.source_id)
                if len(per_hypothesis) >= max_per_hypothesis:
                    break
        selected.extend(per_hypothesis)
        if len(selected) >= max_total:
            break
    return tuple(selected[:max_total])


def normalize_source_extraction(
    extraction: SourceExtraction,
    source: SourceRegistryEntry,
) -> SourceExtraction:
    identity = extraction.source_identity.model_copy(
        update={
            "title": extraction.source_identity.title or source.title,
            "url": source.url,
            "publisher": extraction.source_identity.publisher or source.publisher,
            "source_type": source.source_type,
            "identifiers": source.identifiers,
        }
    )
    return extraction.model_copy(
        update={"source_id": source.source_id, "source_identity": identity}
    )


def normalize_source_fit(
    assessment: SourceFitAssessment,
    source: SourceRegistryEntry,
    hypothesis_id: str,
) -> SourceFitAssessment:
    assessment_id = stable_id("fit", source.source_id, hypothesis_id)
    rows = [
        row.model_copy(update={"score_max": max(row.score_min, row.score_max)})
        for row in assessment.bottom_line_score_rows
    ]
    return assessment.model_copy(
        update={
            "assessment_id": assessment_id,
            "source_id": source.source_id,
            "hypothesis_id": hypothesis_id,
            "url": source.url,
            "source_type": source.source_type,
            "bottom_line_score_rows": rows,
        }
    )


def normalize_trial_prescreen(
    prescreen: TrialPrescreen,
    source: SourceRegistryEntry,
) -> TrialPrescreen:
    nct_id = source.identifiers.nct_id or prescreen.nct_id
    return prescreen.model_copy(
        update={
            "prescreen_id": stable_id("trialfit", source.source_id, nct_id),
            "source_id": source.source_id,
            "nct_id": nct_id,
            "not_a_final_eligibility_determination": True,
        }
    )


def normalize_hypothesis_synthesis(
    synthesis: HypothesisSynthesis,
    hypothesis: Hypothesis,
) -> HypothesisSynthesis:
    claims: list[ReportClaim] = []
    for claim in synthesis.report_claims:
        claims.append(
            claim.model_copy(
                update={
                    "claim_id": stable_id(
                        "claim",
                        hypothesis.hypothesis_id,
                        claim.claim,
                        sorted(claim.patient_evidence_ids),
                        sorted(claim.external_source_ids),
                    )
                }
            )
        )
    return synthesis.model_copy(
        update={
            "synthesis_id": stable_id("syn", hypothesis.hypothesis_id),
            "hypothesis_id": hypothesis.hypothesis_id,
            "report_claims": claims,
        }
    )


def assign_report_item_ids(report: ReportDraft) -> ReportDraft:
    def assign(items: Sequence[T], prefix: str, fields: Sequence[str]) -> list[T]:
        output: list[T] = []
        for item in items:
            values = [getattr(item, field) for field in fields]
            output.append(
                item.model_copy(update={"row_id": stable_id(prefix, *values)})
            )
        return output

    source_index = [
        row.model_copy(update={"display_order": index})
        for index, row in enumerate(report.url_fit_appendix.source_index, start=1)
    ]
    appendix = report.url_fit_appendix.model_copy(update={"source_index": source_index})
    return report.model_copy(
        update={
            "report_draft_id": stable_id(
                "report",
                report.cover_metadata.title,
                report.executive_summary.top_takeaway,
            ),
            "key_findings": assign(
                report.key_findings, "kf", ("marker_or_finding", "what_it_means")
            ),
            "other_findings": assign(
                report.other_findings, "of", ("finding", "interpretation")
            ),
            "cause_effect": assign(
                report.cause_effect, "ce", ("finding", "mechanism_chain")
            ),
            "therapy_options": assign(
                report.therapy_options,
                "tx",
                ("marker_or_target", "therapy_class", "status"),
            ),
            "resistance_escape": assign(
                report.resistance_escape,
                "res",
                ("therapy_or_pathway", "evidence_status"),
            ),
            "follow_up_tests": assign(
                report.follow_up_tests,
                "fu",
                ("recommended_next_step", "why_it_matters"),
            ),
            "phenotypic_events": assign(
                report.phenotypic_events, "evt", ("clinical_event", "recommended_test")
            ),
            "selected_links": assign(
                report.selected_links, "link", ("source_id", "url")
            ),
            "url_fit_appendix": appendix,
        }
    )


def normalize_cross_source_synthesis(
    synthesis: CrossSourceSynthesis,
    source_ids: Sequence[str],
) -> CrossSourceSynthesis:
    return synthesis.model_copy(
        update={
            "synthesis_id": stable_id(
                "crosssyn", sorted(source_ids), synthesis.summary
            ),
            "source_ids": unique_preserve_order(source_ids),
        }
    )


# ---------------------------------------------------------------------------
# PIPELINE STAGE VARIABLE BUILDERS — PURE FUNCTIONS
# ---------------------------------------------------------------------------


def hypothesis_builder_payload(canonical: CanonicalInput) -> dict[str, Any]:
    return {
        "case_context": canonical.case.model_dump(mode="json"),
        "primary_actionable_findings": [
            item.model_dump(mode="json") for item in canonical.actionable_findings
        ],
        "secondary_findings": [
            item.model_dump(mode="json") for item in canonical.secondary_findings
        ],
        "context_findings": [
            item.model_dump(mode="json") for item in canonical.context_findings
        ],
        "technical_limitations": [
            item.model_dump(mode="json") for item in canonical.technical_limitations
        ],
        "optional_internal_hints": compact_internal_context(canonical.existing_context),
    }


def research_planner_payload(state: PipelineState) -> dict[str, Any]:
    missing = list(state.canonical_input.case.missing_context)
    for finding in (
        state.canonical_input.actionable_findings
        + state.canonical_input.secondary_findings
    ):
        missing.extend(finding.missing_validation)
    return {
        "case_context": state.canonical_input.case.model_dump(mode="json"),
        "biological_hypotheses": [
            item.model_dump(mode="json") for item in state.hypotheses
        ],
        "known_missing_context": unique_preserve_order(missing),
        "existing_trial_mentions": state.canonical_input.existing_context.existing_trial_mentions,
    }


def source_discovery_payload(state: PipelineState, job: ResearchJob) -> dict[str, Any]:
    return {
        "research_job": job.model_dump(mode="json"),
        "minimal_patient_anchor": build_minimal_patient_anchor(state, job),
        "retrieval_requirements": {
            "fully_qualified_urls": True,
            "prefer_primary_sources": True,
            "return_only_consulted_sources": True,
            "maximum_sources": job.maximum_sources,
        },
    }


def source_extractor_payload(source: SourceRegistryEntry) -> dict[str, Any]:
    return {
        "target_source": source.model_dump(mode="json"),
        "instruction": (
            f"Open and inspect this exact URL: {source.url}. "
            "Do not substitute another source."
        ),
    }


def source_fit_payload(
    state: PipelineState,
    source: SourceRegistryEntry,
    hypothesis: Hypothesis,
) -> dict[str, Any]:
    extraction = source_extraction_by_id(state, source.source_id)
    return {
        "patient_context": state.canonical_input.case.model_dump(mode="json"),
        "patient_hypothesis": hypothesis.model_dump(mode="json"),
        "relevant_patient_findings": [
            item.model_dump(mode="json")
            for item in findings_for_hypothesis(state.canonical_input, hypothesis)
        ],
        "technical_limitations": [
            item.model_dump(mode="json")
            for item in state.canonical_input.technical_limitations
            if set(item.patient_evidence_ids) & set(hypothesis.patient_evidence_ids)
        ],
        "source_metadata": source.model_dump(mode="json"),
        "source_extraction": extraction.model_dump(mode="json"),
    }


def trial_prescreen_payload(
    state: PipelineState, source: SourceRegistryEntry
) -> dict[str, Any]:
    related_findings: list[CanonicalFinding] = []
    for hypothesis_id in source.hypothesis_ids:
        related_findings.extend(
            findings_for_hypothesis(
                state.canonical_input,
                hypothesis_by_id(state, hypothesis_id),
            )
        )
    extraction = source_extraction_by_id(state, source.source_id)
    return {
        "patient_data": {
            "case": state.canonical_input.case.model_dump(mode="json"),
            "findings": [
                item.model_dump(mode="json")
                for item in unique_preserve_order(related_findings)
            ],
        },
        "current_trial_record": extraction.model_dump(mode="json"),
        "source_metadata": source.model_dump(mode="json"),
    }


def hypothesis_synthesis_payload(
    state: PipelineState, hypothesis: Hypothesis
) -> dict[str, Any]:
    assessments = [
        item
        for item in state.source_fit_assessments
        if item.hypothesis_id == hypothesis.hypothesis_id
    ]
    source_ids = {item.source_id for item in assessments}
    prescreens = [
        item for item in state.trial_prescreens if item.source_id in source_ids
    ]
    return {
        "patient_hypothesis": hypothesis.model_dump(mode="json"),
        "relevant_patient_findings": [
            item.model_dump(mode="json")
            for item in findings_for_hypothesis(state.canonical_input, hypothesis)
        ],
        "source_fit_assessments": [
            item.model_dump(mode="json") for item in assessments
        ],
        "trial_prescreens": [item.model_dump(mode="json") for item in prescreens],
        "technical_limitations": [
            item.model_dump(mode="json")
            for item in state.canonical_input.technical_limitations
        ],
        "optional_internal_context": compact_internal_context(
            state.canonical_input.existing_context
        ),
    }


def report_compiler_payload(state: PipelineState) -> dict[str, Any]:
    selected_source_ids = {item.source_id for item in state.sources}
    return {
        "case_summary": state.canonical_input.case.model_dump(mode="json"),
        "primary_findings": [
            item.model_dump(mode="json")
            for item in state.canonical_input.actionable_findings
        ],
        "secondary_findings": [
            item.model_dump(mode="json")
            for item in state.canonical_input.secondary_findings
        ],
        "context_findings": [
            item.model_dump(mode="json")
            for item in state.canonical_input.context_findings
        ],
        "hypothesis_syntheses": [
            item.model_dump(mode="json") for item in state.hypothesis_syntheses
        ],
        "trial_prescreens": [
            item.model_dump(mode="json") for item in state.trial_prescreens
        ],
        "technical_limitations": [
            item.model_dump(mode="json")
            for item in state.canonical_input.technical_limitations
        ],
        "negative_findings": state.canonical_input.negative_findings,
        "retesting_trigger_hints": state.canonical_input.existing_context.retesting_triggers,
        "selected_sources": [
            item.model_dump(mode="json")
            for item in state.sources
            if item.source_id in selected_source_ids
        ],
        "appendix_source_assessments": [
            item.model_dump(mode="json") for item in state.source_fit_assessments
        ],
        "required_content_types": {
            "main_report_sections": [
                "cover_metadata",
                "executive_summary",
                "key_findings",
                "other_findings",
                "cause_effect",
                "therapy_options",
                "practical_readout",
                "resistance_escape",
                "follow_up_tests",
                "phenotypic_events",
                "limitations",
                "selected_links",
                "bottom_line",
            ],
            "appendix_sections": [
                "data_basis_and_rules",
                "scoring_guide",
                "source_index",
            ],
        },
    }


def cross_source_payload(state: PipelineState) -> dict[str, Any]:
    return {
        "hypothesis_syntheses": [
            item.model_dump(mode="json") for item in state.hypothesis_syntheses
        ],
        "source_assessments": [
            item.model_dump(mode="json") for item in state.source_fit_assessments
        ],
    }


def validation_payload(state: PipelineState, validator_type: str) -> dict[str, Any]:
    assert state.report_draft is not None
    base: dict[str, Any] = {
        "case_context": state.canonical_input.case.model_dump(mode="json"),
        "report": state.report_draft.model_dump(mode="json"),
        "cross_source_synthesis": state.cross_source_synthesis.model_dump(mode="json")
        if state.cross_source_synthesis
        else None,
        "patient_evidence_registry": {
            item.evidence_id: item.model_dump(mode="json")
            for item in state.canonical_input.patient_evidence
        },
        "source_registry": {
            item.source_id: item.model_dump(mode="json") for item in state.sources
        },
        "source_extractions": {
            item.source_id: item.model_dump(mode="json")
            for item in state.source_extractions
        },
        "source_fit_assessments": [
            item.model_dump(mode="json") for item in state.source_fit_assessments
        ],
        "trial_prescreens": [
            item.model_dump(mode="json") for item in state.trial_prescreens
        ],
    }
    if validator_type == "population_alignment":
        return {
            "case_context": base["case_context"],
            "therapy_options": base["report"]["therapy_options"],
            "selected_links": base["report"]["selected_links"],
            "trial_prescreens": base["trial_prescreens"],
            "source_fit_assessments": base["source_fit_assessments"],
        }
    if validator_type == "clinical_safety":
        return base
    return base


# ---------------------------------------------------------------------------
# PIPELINE STAGES — EFFECTFUL SHELL AROUND PURE TRANSFORMS
# ---------------------------------------------------------------------------


async def stage_hypotheses(
    state: PipelineState,
    gateway: OpenAIResponsesGateway,
    store: ArtifactStore,
) -> PipelineState:
    payload = hypothesis_builder_payload(state.canonical_input)
    artifact_id = stable_id("artifact", "hypotheses", state.run_id, payload)
    result = await gateway.structured_call(
        stage="hypothesis_builder",
        artifact_id=artifact_id,
        prompt=PROMPTS["hypothesis_builder"],
        payload=payload,
        response_model=HypothesisBuilderOutput,
    )
    hypotheses = assign_hypothesis_ids(result.parsed)
    artifact = artifact_from_payload(
        artifact_id=artifact_id,
        artifact_type="hypothesis_collection",
        stage="hypothesis_builder",
        payload={"hypotheses": [item.model_dump(mode="json") for item in hypotheses]},
        parents=[stable_id("artifact", "canonical_input", state.run_id)],
        input_value=payload,
        prompt=PROMPTS["hypothesis_builder"],
        model=result.model,
        response_id=result.response_id,
    )
    store.save_artifact(artifact)
    next_state = dataclasses.replace(state, hypotheses=hypotheses)
    next_state = append_artifact(next_state, artifact)
    next_state = append_usage(
        next_state, stage="hypothesis_builder", artifact_id=artifact_id, result=result
    )
    return next_state


async def stage_research_plan(
    state: PipelineState,
    gateway: OpenAIResponsesGateway,
    store: ArtifactStore,
    config: PipelineConfig,
) -> PipelineState:
    payload = research_planner_payload(state)
    artifact_id = stable_id("artifact", "research_plan", state.run_id, payload)
    result = await gateway.structured_call(
        stage="research_planner",
        artifact_id=artifact_id,
        prompt=PROMPTS["research_planner"],
        payload=payload,
        response_model=ResearchPlanOutput,
    )
    jobs = assign_research_job_ids(
        result.parsed,
        {item.hypothesis_id for item in state.hypotheses},
        config.max_research_jobs,
        config.max_sources_per_job,
    )
    artifact = artifact_from_payload(
        artifact_id=artifact_id,
        artifact_type="research_plan",
        stage="research_planner",
        payload={"research_jobs": [item.model_dump(mode="json") for item in jobs]},
        parents=[
            stable_id(
                "artifact",
                "hypotheses",
                state.run_id,
                hypothesis_builder_payload(state.canonical_input),
            )
        ],
        input_value=payload,
        prompt=PROMPTS["research_planner"],
        model=result.model,
        response_id=result.response_id,
    )
    store.save_artifact(artifact)
    next_state = dataclasses.replace(state, research_jobs=jobs)
    next_state = append_artifact(next_state, artifact)
    next_state = append_usage(
        next_state, stage="research_planner", artifact_id=artifact_id, result=result
    )
    return next_state


async def stage_source_discovery(
    state: PipelineState,
    gateway: OpenAIResponsesGateway,
    store: ArtifactStore,
    config: PipelineConfig,
) -> PipelineState:
    if not config.enable_web_search:
        return append_warning(
            dataclasses.replace(state, sources=()),
            "External source discovery was disabled; URL enrichment and appendix sources will be empty.",
        )
    if not state.research_jobs:
        seeded = seed_existing_trial_sources(state)
        selected = select_sources(
            seeded,
            config.max_sources_per_hypothesis,
            config.max_sources_total,
        )
        return dataclasses.replace(state, sources=selected)

    async def discover(
        job: ResearchJob,
    ) -> tuple[
        ResearchJob,
        SourceDiscoveryOutput,
        tuple[WebSource, ...],
        ModelResult[SourceDiscoveryOutput],
        ArtifactEnvelope,
    ]:
        payload = source_discovery_payload(state, job)
        artifact_id = stable_id("artifact", "source_discovery", job.job_id, payload)
        result = await gateway.structured_call(
            stage="source_discovery",
            artifact_id=artifact_id,
            prompt=PROMPTS["source_discovery"],
            payload=payload,
            response_model=SourceDiscoveryOutput,
            use_web=True,
            allowed_domains=allowed_domains_for_job(job),
            required_web=True,
        )
        normalized_candidates = [
            candidate.model_copy(
                update={
                    "source_id": stable_id(
                        "src_candidate",
                        job.job_id,
                        ensure_source_url(candidate.model_dump(mode="json")),
                        candidate.title,
                    ),
                    "job_id": job.job_id,
                    "hypothesis_id": job.hypothesis_id,
                    "url": ensure_source_url(candidate.model_dump(mode="json")),
                    "canonical_url": ensure_source_url(
                        candidate.model_dump(mode="json")
                    ),
                }
            )
            for candidate in result.parsed.candidate_sources
            if ensure_source_url(candidate.model_dump(mode="json"))
        ]
        normalized = result.parsed.model_copy(
            update={
                "job_id": job.job_id,
                "candidate_sources": normalized_candidates[: job.maximum_sources],
            }
        )
        artifact = artifact_from_payload(
            artifact_id=artifact_id,
            artifact_type="source_discovery",
            stage="source_discovery",
            payload=normalized,
            parents=[job.job_id],
            input_value=payload,
            prompt=PROMPTS["source_discovery"],
            model=result.model,
            response_id=result.response_id,
        )
        return job, normalized, result.web_sources, result, artifact

    gathered = await asyncio.gather(
        *(discover(job) for job in state.research_jobs),
        return_exceptions=True,
    )
    successful: list[
        tuple[
            ResearchJob,
            SourceDiscoveryOutput,
            tuple[WebSource, ...],
            ModelResult[SourceDiscoveryOutput],
            ArtifactEnvelope,
        ]
    ] = []
    next_state = state
    for job, item in zip(state.research_jobs, gathered, strict=True):
        if isinstance(item, BaseException):
            next_state = append_warning(
                next_state,
                f"Source discovery failed for {job.job_id}: {item.__class__.__name__}.",
            )
            continue
        successful.append(item)

    discoveries = [
        (job, output, web_sources) for job, output, web_sources, _, _ in successful
    ]
    discovered = source_registry_from_discoveries(
        discoveries, config.strict_source_verification
    )
    seeded = seed_existing_trial_sources(state)
    sources = select_sources(
        merge_source_registries(discovered, seeded),
        config.max_sources_per_hypothesis,
        config.max_sources_total,
    )

    next_state = dataclasses.replace(next_state, sources=sources)
    for _, _, _, result, artifact in successful:
        store.save_artifact(artifact)
        next_state = append_artifact(next_state, artifact)
        next_state = append_usage(
            next_state,
            stage="source_discovery",
            artifact_id=artifact.artifact_id,
            result=result,
        )
    registry_artifact = artifact_from_payload(
        artifact_id=stable_id(
            "artifact",
            "source_registry",
            state.run_id,
            [item.model_dump(mode="json") for item in sources],
        ),
        artifact_type="source_registry",
        stage="source_selection",
        payload={"sources": [item.model_dump(mode="json") for item in sources]},
        parents=[artifact.artifact_id for *_, artifact in successful],
        input_value=[item.model_dump(mode="json") for item in discovered],
    )
    store.save_artifact(registry_artifact)
    next_state = append_artifact(next_state, registry_artifact)
    if not sources:
        next_state = append_warning(
            next_state,
            "No externally verifiable sources survived URL discovery and selection.",
        )
    return next_state


async def stage_source_extractions(
    state: PipelineState,
    gateway: OpenAIResponsesGateway,
    store: ArtifactStore,
) -> PipelineState:
    if not state.sources:
        return state

    async def extract(
        source: SourceRegistryEntry,
    ) -> tuple[SourceExtraction, ModelResult[SourceExtraction], ArtifactEnvelope]:
        payload = source_extractor_payload(source)
        artifact_id = stable_id(
            "artifact", "source_extraction", source.source_id, source.url
        )
        result = await gateway.structured_call(
            stage="source_extractor",
            artifact_id=artifact_id,
            prompt=PROMPTS["source_extractor"],
            payload=payload,
            response_model=SourceExtraction,
            use_web=True,
            allowed_domains=(hostname(source.url),),
            required_web=True,
        )
        normalized = normalize_source_extraction(result.parsed, source)
        artifact = artifact_from_payload(
            artifact_id=artifact_id,
            artifact_type="source_extraction",
            stage="source_extractor",
            payload=normalized,
            parents=[source.source_id],
            input_value=payload,
            prompt=PROMPTS["source_extractor"],
            model=result.model,
            response_id=result.response_id,
        )
        return normalized, result, artifact

    gathered = await asyncio.gather(
        *(extract(source) for source in state.sources),
        return_exceptions=True,
    )
    successful: list[
        tuple[SourceExtraction, ModelResult[SourceExtraction], ArtifactEnvelope]
    ] = []
    successful_source_ids: set[str] = set()
    next_state = state
    for source, item in zip(state.sources, gathered, strict=True):
        if isinstance(item, BaseException):
            next_state = append_warning(
                next_state,
                f"Source extraction failed for {source.source_id}: {item.__class__.__name__}; source omitted.",
            )
            continue
        successful.append(item)
        successful_source_ids.add(source.source_id)

    retained_sources = tuple(
        source for source in state.sources if source.source_id in successful_source_ids
    )
    next_state = dataclasses.replace(
        next_state,
        sources=retained_sources,
        source_extractions=tuple(item for item, _, _ in successful),
    )
    for _, result, artifact in successful:
        store.save_artifact(artifact)
        next_state = append_artifact(next_state, artifact)
        next_state = append_usage(
            next_state,
            stage="source_extractor",
            artifact_id=artifact.artifact_id,
            result=result,
        )
    return next_state


async def stage_source_fit_assessments(
    state: PipelineState,
    gateway: OpenAIResponsesGateway,
    store: ArtifactStore,
) -> PipelineState:
    tasks: list[tuple[SourceRegistryEntry, Hypothesis]] = []
    for source in state.sources:
        for hypothesis_id in source.hypothesis_ids:
            tasks.append((source, hypothesis_by_id(state, hypothesis_id)))
    if not tasks:
        return state

    async def assess(
        source: SourceRegistryEntry,
        hypothesis: Hypothesis,
    ) -> tuple[
        SourceFitAssessment,
        ModelResult[SourceFitAssessment],
        ArtifactEnvelope,
    ]:
        payload = source_fit_payload(state, source, hypothesis)
        artifact_id = stable_id(
            "artifact", "source_fit", source.source_id, hypothesis.hypothesis_id
        )
        result = await gateway.structured_call(
            stage="source_fit",
            artifact_id=artifact_id,
            prompt=PROMPTS["source_fit"],
            payload=payload,
            response_model=SourceFitAssessment,
        )
        normalized = normalize_source_fit(
            result.parsed, source, hypothesis.hypothesis_id
        )
        artifact = artifact_from_payload(
            artifact_id=artifact_id,
            artifact_type="source_fit_assessment",
            stage="source_fit",
            payload=normalized,
            parents=[source.source_id, hypothesis.hypothesis_id],
            input_value=payload,
            prompt=PROMPTS["source_fit"],
            model=result.model,
            response_id=result.response_id,
        )
        return normalized, result, artifact

    gathered = await asyncio.gather(
        *(assess(source, hypothesis) for source, hypothesis in tasks),
        return_exceptions=True,
    )
    successful: list[
        tuple[SourceFitAssessment, ModelResult[SourceFitAssessment], ArtifactEnvelope]
    ] = []
    next_state = state
    for (source, hypothesis), item in zip(tasks, gathered, strict=True):
        if isinstance(item, BaseException):
            next_state = append_warning(
                next_state,
                f"Source-fit assessment failed for {source.source_id}/{hypothesis.hypothesis_id}: {item.__class__.__name__}.",
            )
            continue
        successful.append(item)

    assessed_source_ids = {item.source_id for item, _, _ in successful}
    retained_sources = tuple(
        source for source in state.sources if source.source_id in assessed_source_ids
    )
    retained_extractions = tuple(
        extraction
        for extraction in state.source_extractions
        if extraction.source_id in assessed_source_ids
    )
    next_state = dataclasses.replace(
        next_state,
        sources=retained_sources,
        source_extractions=retained_extractions,
        source_fit_assessments=tuple(item for item, _, _ in successful),
    )
    for _, result, artifact in successful:
        store.save_artifact(artifact)
        next_state = append_artifact(next_state, artifact)
        next_state = append_usage(
            next_state,
            stage="source_fit",
            artifact_id=artifact.artifact_id,
            result=result,
        )
    return next_state


async def stage_trial_prescreens(
    state: PipelineState,
    gateway: OpenAIResponsesGateway,
    store: ArtifactStore,
) -> PipelineState:
    trial_sources = [
        source
        for source in state.sources
        if source.source_type == "trial_record" or source.identifiers.nct_id
    ]
    if not trial_sources:
        return state

    async def prescreen(
        source: SourceRegistryEntry,
    ) -> tuple[TrialPrescreen, ModelResult[TrialPrescreen], ArtifactEnvelope]:
        payload = trial_prescreen_payload(state, source)
        artifact_id = stable_id("artifact", "trial_prescreen", source.source_id)
        result = await gateway.structured_call(
            stage="trial_prescreen",
            artifact_id=artifact_id,
            prompt=PROMPTS["trial_prescreen"],
            payload=payload,
            response_model=TrialPrescreen,
        )
        normalized = normalize_trial_prescreen(result.parsed, source)
        artifact = artifact_from_payload(
            artifact_id=artifact_id,
            artifact_type="trial_prescreen",
            stage="trial_prescreen",
            payload=normalized,
            parents=[source.source_id],
            input_value=payload,
            prompt=PROMPTS["trial_prescreen"],
            model=result.model,
            response_id=result.response_id,
        )
        return normalized, result, artifact

    gathered = await asyncio.gather(
        *(prescreen(source) for source in trial_sources),
        return_exceptions=True,
    )
    successful: list[
        tuple[TrialPrescreen, ModelResult[TrialPrescreen], ArtifactEnvelope]
    ] = []
    next_state = state
    for source, item in zip(trial_sources, gathered, strict=True):
        if isinstance(item, BaseException):
            next_state = append_warning(
                next_state,
                f"Trial pre-screen failed for {source.source_id}: {item.__class__.__name__}.",
            )
            continue
        successful.append(item)
    next_state = dataclasses.replace(
        next_state,
        trial_prescreens=tuple(item for item, _, _ in successful),
    )
    for _, result, artifact in successful:
        store.save_artifact(artifact)
        next_state = append_artifact(next_state, artifact)
        next_state = append_usage(
            next_state,
            stage="trial_prescreen",
            artifact_id=artifact.artifact_id,
            result=result,
        )
    return next_state


async def stage_hypothesis_syntheses(
    state: PipelineState,
    gateway: OpenAIResponsesGateway,
    store: ArtifactStore,
) -> PipelineState:
    async def synthesize(
        hypothesis: Hypothesis,
    ) -> tuple[HypothesisSynthesis, ModelResult[HypothesisSynthesis], ArtifactEnvelope]:
        payload = hypothesis_synthesis_payload(state, hypothesis)
        artifact_id = stable_id(
            "artifact", "hypothesis_synthesis", hypothesis.hypothesis_id
        )
        result = await gateway.structured_call(
            stage="hypothesis_synthesis",
            artifact_id=artifact_id,
            prompt=PROMPTS["hypothesis_synthesis"],
            payload=payload,
            response_model=HypothesisSynthesis,
        )
        normalized = normalize_hypothesis_synthesis(result.parsed, hypothesis)
        artifact = artifact_from_payload(
            artifact_id=artifact_id,
            artifact_type="hypothesis_synthesis",
            stage="hypothesis_synthesis",
            payload=normalized,
            parents=[hypothesis.hypothesis_id]
            + [
                item.assessment_id
                for item in state.source_fit_assessments
                if item.hypothesis_id == hypothesis.hypothesis_id
            ],
            input_value=payload,
            prompt=PROMPTS["hypothesis_synthesis"],
            model=result.model,
            response_id=result.response_id,
        )
        return normalized, result, artifact

    results = await asyncio.gather(*(synthesize(item) for item in state.hypotheses))
    syntheses = tuple(
        sorted((item for item, _, _ in results), key=lambda item: item.hypothesis_id)
    )
    next_state = dataclasses.replace(state, hypothesis_syntheses=syntheses)
    for _, result, artifact in results:
        store.save_artifact(artifact)
        next_state = append_artifact(next_state, artifact)
        next_state = append_usage(
            next_state,
            stage="hypothesis_synthesis",
            artifact_id=artifact.artifact_id,
            result=result,
        )
    return next_state


async def stage_report_compiler(
    state: PipelineState,
    gateway: OpenAIResponsesGateway,
    store: ArtifactStore,
) -> PipelineState:
    payload = report_compiler_payload(state)
    artifact_id = stable_id("artifact", "report_draft", state.run_id, payload)
    result = await gateway.structured_call(
        stage="report_compiler",
        artifact_id=artifact_id,
        prompt=PROMPTS["report_compiler"],
        payload=payload,
        response_model=ReportDraft,
    )
    normalized = assign_report_item_ids(result.parsed)
    # Enforce source registry URLs/IDs and remove hallucinated selected links.
    source_map = {item.source_id: item for item in state.sources}
    links: list[SelectedLinkRow] = []
    for link in normalized.selected_links:
        source = source_map.get(link.source_id)
        if source is None:
            continue
        links.append(
            link.model_copy(
                update={
                    "url": source.url,
                    "title": source.title,
                    "source_type": source.source_type,
                    "hypothesis_id": source.hypothesis_ids[0]
                    if source.hypothesis_ids
                    else link.hypothesis_id,
                    "row_id": stable_id("link", source.source_id, source.url),
                }
            )
        )
    source_index: list[AppendixSourceIndexRow] = []
    assessments_by_source: dict[str, SourceFitAssessment] = {}
    for fit_assessment in state.source_fit_assessments:
        assessments_by_source.setdefault(fit_assessment.source_id, fit_assessment)
    for index, source in enumerate(state.sources, start=1):
        source_assessment = assessments_by_source.get(source.source_id)
        source_index.append(
            AppendixSourceIndexRow(
                display_order=index,
                source_id=source.source_id,
                title=source.title,
                marker_or_pathway=(
                    source_assessment.relevant_marker_or_pathway
                    if source_assessment
                    else []
                ),
                evidence_type=source.source_type,
                url=source.url,
            )
        )
    appendix = normalized.url_fit_appendix.model_copy(
        update={
            "source_index": source_index,
            "source_assessment_ids": [
                item.assessment_id for item in state.source_fit_assessments
            ],
        }
    )
    normalized = normalized.model_copy(
        update={
            "selected_links": links,
            "url_fit_appendix": appendix,
        }
    )
    artifact = artifact_from_payload(
        artifact_id=artifact_id,
        artifact_type="report_draft",
        stage="report_compiler",
        payload=normalized,
        parents=[item.synthesis_id for item in state.hypothesis_syntheses],
        input_value=payload,
        prompt=PROMPTS["report_compiler"],
        model=result.model,
        response_id=result.response_id,
    )
    store.save_artifact(artifact)
    next_state = dataclasses.replace(state, report_draft=normalized)
    next_state = append_artifact(next_state, artifact)
    next_state = append_usage(
        next_state, stage="report_compiler", artifact_id=artifact_id, result=result
    )
    return next_state


async def stage_cross_source_synthesis(
    state: PipelineState,
    gateway: OpenAIResponsesGateway,
    store: ArtifactStore,
) -> PipelineState:
    payload = cross_source_payload(state)
    artifact_id = stable_id("artifact", "cross_source_synthesis", state.run_id, payload)
    result = await gateway.structured_call(
        stage="cross_source_synthesis",
        artifact_id=artifact_id,
        prompt=PROMPTS["cross_source_synthesis"],
        payload=payload,
        response_model=CrossSourceSynthesis,
    )
    normalized = normalize_cross_source_synthesis(
        result.parsed,
        [item.source_id for item in state.sources],
    )
    artifact = artifact_from_payload(
        artifact_id=artifact_id,
        artifact_type="cross_source_synthesis",
        stage="cross_source_synthesis",
        payload=normalized,
        parents=[item.synthesis_id for item in state.hypothesis_syntheses]
        + [item.assessment_id for item in state.source_fit_assessments],
        input_value=payload,
        prompt=PROMPTS["cross_source_synthesis"],
        model=result.model,
        response_id=result.response_id,
    )
    store.save_artifact(artifact)
    next_state = dataclasses.replace(state, cross_source_synthesis=normalized)
    next_state = append_artifact(next_state, artifact)
    next_state = append_usage(
        next_state,
        stage="cross_source_synthesis",
        artifact_id=artifact_id,
        result=result,
    )
    return next_state


async def stage_llm_validations(
    state: PipelineState,
    gateway: OpenAIResponsesGateway,
    store: ArtifactStore,
    config: PipelineConfig,
) -> PipelineState:
    if not config.run_llm_validators:
        return state
    specs = (
        ("claim_grounding", "validator_claim_grounding"),
        ("population_alignment", "validator_population"),
        ("clinical_safety", "validator_safety"),
    )

    async def validate(
        validator_type: str,
        prompt_key: str,
    ) -> tuple[ValidationOutput, ModelResult[ValidationOutput], ArtifactEnvelope]:
        payload = validation_payload(state, validator_type)
        artifact_id = stable_id(
            "artifact", "validation", validator_type, state.run_id, payload
        )
        result = await gateway.structured_call(
            stage=prompt_key,
            artifact_id=artifact_id,
            prompt=PROMPTS[prompt_key],
            payload=payload,
            response_model=ValidationOutput,
        )
        findings = [
            item.model_copy(
                update={
                    "finding_id": stable_id(
                        "val",
                        validator_type,
                        item.section_id,
                        item.item_id,
                        item.statement,
                        item.reason,
                    )
                }
            )
            for item in result.parsed.findings
        ]
        normalized = result.parsed.model_copy(
            update={
                "validator_id": stable_id("validator", validator_type, state.run_id),
                "validator_type": validator_type,
                "passed": not any(
                    item.severity in {"error", "blocking"} for item in findings
                ),
                "findings": findings,
            }
        )
        artifact = artifact_from_payload(
            artifact_id=artifact_id,
            artifact_type="validation_output",
            stage=prompt_key,
            payload=normalized,
            parents=[state.report_draft.report_draft_id if state.report_draft else ""],
            input_value=payload,
            prompt=PROMPTS[prompt_key],
            model=result.model,
            response_id=result.response_id,
        )
        return normalized, result, artifact

    gathered = await asyncio.gather(
        *(validate(*spec) for spec in specs),
        return_exceptions=True,
    )
    successful: list[
        tuple[ValidationOutput, ModelResult[ValidationOutput], ArtifactEnvelope]
    ] = []
    next_state = state
    for (validator_type, _), item in zip(specs, gathered, strict=True):
        if isinstance(item, BaseException):
            next_state = append_warning(
                next_state,
                f"LLM validator {validator_type} failed: {item.__class__.__name__}.",
            )
            continue
        successful.append(item)
    next_state = dataclasses.replace(
        next_state,
        validations=tuple(item for item, _, _ in successful),
    )
    for _, result, artifact in successful:
        store.save_artifact(artifact)
        next_state = append_artifact(next_state, artifact)
        next_state = append_usage(
            next_state,
            stage=artifact.stage,
            artifact_id=artifact.artifact_id,
            result=result,
        )
    return next_state


# ---------------------------------------------------------------------------
# DETERMINISTIC VALIDATION AND RENDERER SECTION ASSEMBLY — PURE FUNCTIONS
# ---------------------------------------------------------------------------


def map_by_id(items: Iterable[T], field_name: str) -> dict[str, T]:
    """Return a deterministic map keyed by a model identifier field."""

    result: dict[str, T] = {}
    for item in items:
        key = str(getattr(item, field_name))
        if key in result and canonical_json(result[key]) != canonical_json(item):
            raise ValueError(f"Conflicting duplicate {field_name}: {key}")
        result[key] = item
    return dict(sorted(result.items()))


def all_report_claims(state: PipelineState) -> tuple[ReportClaim, ...]:
    claims: dict[str, ReportClaim] = {}
    for synthesis in state.hypothesis_syntheses:
        for claim in synthesis.report_claims:
            claims.setdefault(claim.claim_id, claim)
    return tuple(claims[key] for key in sorted(claims))


def recursively_collect_named_ids(
    value: Any, field_names: set[str]
) -> dict[str, set[str]]:
    """Collect string/list identifiers from nested Pydantic/dict/list values."""

    collected: dict[str, set[str]] = {name: set() for name in field_names}

    def walk(node: Any) -> None:
        if isinstance(node, BaseModel):
            node = node.model_dump(mode="json")
        if isinstance(node, Mapping):
            for key, child in node.items():
                if key in field_names:
                    if isinstance(child, str) and child:
                        collected[key].add(child)
                    elif isinstance(child, Sequence) and not isinstance(
                        child, (str, bytes, bytearray)
                    ):
                        collected[key].update(
                            str(item)
                            for item in child
                            if isinstance(item, str) and item
                        )
                walk(child)
        elif isinstance(node, Sequence) and not isinstance(
            node, (str, bytes, bytearray)
        ):
            for child in node:
                walk(child)

    walk(value)
    return collected


def make_section(
    *,
    section_id: str,
    section_number: str,
    title: str,
    content_type: str,
    display_order: int,
    payload: BaseModel | Mapping[str, Any] | Sequence[Any],
    page_break: bool = False,
) -> SectionEnvelope:
    if isinstance(payload, BaseModel):
        serialized: dict[str, Any] = payload.model_dump(mode="json")
    elif isinstance(payload, Mapping):
        serialized = copy.deepcopy(dict(payload))
    else:
        serialized = {"items": copy.deepcopy(list(payload))}
    return SectionEnvelope(
        section_id=section_id,
        section_number=section_number,
        title=title,
        content_type=content_type,
        display_order=display_order,
        preferred_page_break_before=page_break,
        payload=serialized,
    )


def build_renderer_sections(state: PipelineState) -> tuple[SectionEnvelope, ...]:
    """
    Convert the typed report state into the same semantic flow as the 31-page
    reference PDF. Layout engines can render these payloads to PDF, HTML, DOCX,
    a web UI, or another medium without additional model calls.
    """

    if state.report_draft is None:
        raise ValueError("Cannot assemble sections without a report draft.")
    if state.cross_source_synthesis is None:
        raise ValueError("Cannot assemble sections without cross-source synthesis.")

    report = state.report_draft
    sections: list[SectionEnvelope] = []
    order = 0

    def add(
        section_id: str,
        number: str,
        title: str,
        content_type: str,
        payload: BaseModel | Mapping[str, Any] | Sequence[Any],
        *,
        page_break: bool = False,
    ) -> None:
        nonlocal order
        order += 1
        sections.append(
            make_section(
                section_id=section_id,
                section_number=number,
                title=title,
                content_type=content_type,
                display_order=order,
                payload=payload,
                page_break=page_break,
            )
        )

    add(
        SECTION_IDS["cover"],
        "0",
        report.cover_metadata.title,
        "cover_and_purpose_metadata",
        report.cover_metadata,
    )
    add(
        SECTION_IDS["executive_summary"],
        "1",
        "Executive Summary",
        "executive_summary_with_key_takeaways",
        report.executive_summary,
    )
    add(
        SECTION_IDS["key_findings"],
        "2",
        "Key Findings at a Glance",
        "key_findings_and_other_findings_tables",
        {
            "key_findings": [
                item.model_dump(mode="json") for item in report.key_findings
            ],
            "other_findings": [
                item.model_dump(mode="json") for item in report.other_findings
            ],
        },
        page_break=True,
    )
    add(
        SECTION_IDS["cause_effect"],
        "3",
        "Cause and Effect: Why These Findings Matter",
        "cause_effect_chains_and_plain_english",
        {
            "cause_effect": [
                item.model_dump(mode="json") for item in report.cause_effect
            ]
        },
    )
    add(
        SECTION_IDS["therapy_options"],
        "4",
        "Therapy Options and Clinical Rationale",
        "therapy_options_table_and_practical_readout",
        {
            "therapy_options": [
                item.model_dump(mode="json") for item in report.therapy_options
            ],
            "practical_readout": report.practical_readout,
        },
        page_break=True,
    )
    add(
        SECTION_IDS["resistance_escape"],
        "5",
        "Resistance and Escape Routes",
        "resistance_escape_and_monitoring",
        {
            "resistance_escape": [
                item.model_dump(mode="json") for item in report.resistance_escape
            ]
        },
    )
    add(
        SECTION_IDS["follow_up_tests"],
        "6",
        "Follow-up Tests for Precision Oncology",
        "follow_up_tests_table",
        {
            "follow_up_tests": [
                item.model_dump(mode="json") for item in report.follow_up_tests
            ]
        },
    )
    add(
        SECTION_IDS["phenotypic_events"],
        "7",
        "Future Phenotypic Events to Watch For",
        "phenotypic_event_retesting_triggers_table",
        {
            "phenotypic_events": [
                item.model_dump(mode="json") for item in report.phenotypic_events
            ]
        },
        page_break=True,
    )
    add(
        SECTION_IDS["limitations"],
        "8",
        "Limitations and Confidence Boundaries",
        "limitations_and_confidence_boundaries",
        {"limitations": report.limitations},
    )
    add(
        SECTION_IDS["selected_links"],
        "9",
        "Selected Reference and Trial Links",
        "selected_reference_trial_links_and_bottom_line",
        {
            "selected_links": [
                item.model_dump(mode="json") for item in report.selected_links
            ],
            "bottom_line": report.bottom_line,
        },
    )
    add(
        SECTION_IDS["appendix_overview"],
        "10",
        "URL-by-URL Candidate Fit Assessments",
        "url_fit_appendix_overview_and_source_index",
        report.url_fit_appendix,
        page_break=True,
    )

    source_map = map_by_id(state.sources, "source_id")
    trial_map = {item.source_id: item for item in state.trial_prescreens}
    assessments = sorted(
        state.source_fit_assessments,
        key=lambda item: (
            next(
                (
                    row.display_order
                    for row in report.url_fit_appendix.source_index
                    if row.source_id == item.source_id
                ),
                10_000,
            ),
            item.hypothesis_id,
            item.assessment_id,
        ),
    )
    # A source can be relevant to more than one hypothesis. Preserve every
    # source/hypothesis fit as its own deterministic appendix section.
    for index, assessment in enumerate(assessments, start=1):
        source = source_map.get(assessment.source_id)
        section_id = stable_id(
            "sec_10_source",
            index,
            assessment.source_id,
            assessment.hypothesis_id,
        )
        add(
            section_id,
            f"10.{index}",
            assessment.appendix_title,
            "url_candidate_fit_assessment",
            {
                "source": source.model_dump(mode="json") if source else None,
                "assessment": assessment.model_dump(mode="json"),
                "trial_prescreen": (
                    trial_map[assessment.source_id].model_dump(mode="json")
                    if assessment.source_id in trial_map
                    else None
                ),
            },
            page_break=True,
        )

    add(
        SECTION_IDS["cross_source_synthesis"],
        "11",
        "Cross-Source Synthesis",
        "cross_source_synthesis",
        state.cross_source_synthesis,
        page_break=True,
    )
    add(
        SECTION_IDS["urls_assessed"],
        "12",
        "URLs Assessed in This Appendix",
        "fully_qualified_urls_assessed_table",
        {
            "urls_assessed": [
                {
                    "display_order": index,
                    "source_id": source.source_id,
                    "title": source.title,
                    "url": source.url,
                    "publisher": source.publisher,
                    "source_type": source.source_type,
                    "identifiers": source.identifiers.model_dump(mode="json"),
                }
                for index, source in enumerate(state.sources, start=1)
            ]
        },
    )
    return tuple(sections)


def deterministic_integrity_validation(
    state: PipelineState,
    sections: Sequence[SectionEnvelope],
) -> ValidationOutput:
    """Validate identifiers, provenance, URLs, and PDF content-type coverage."""

    findings: list[ValidationFinding] = []

    def record(
        *,
        severity: Literal["info", "warning", "error", "blocking"],
        disposition: Literal["PASS", "REVISE", "REMOVE"],
        statement: str,
        reason: str,
        section_id: str | None = None,
        item_id: str | None = None,
        suggested_revision: str | None = None,
        patient_evidence_ids: Sequence[str] = (),
        source_ids: Sequence[str] = (),
    ) -> None:
        findings.append(
            ValidationFinding(
                finding_id=stable_id(
                    "val",
                    "deterministic_integrity",
                    severity,
                    section_id,
                    item_id,
                    statement,
                    reason,
                ),
                severity=severity,
                disposition=disposition,
                section_id=section_id,
                item_id=item_id,
                statement=statement,
                reason=reason,
                suggested_revision=suggested_revision,
                patient_evidence_ids=list(patient_evidence_ids),
                source_ids=list(source_ids),
            )
        )

    required_section_ids = set(SECTION_IDS.values())
    actual_section_ids = {item.section_id for item in sections}
    missing_sections = sorted(required_section_ids - actual_section_ids)
    if missing_sections:
        record(
            severity="blocking",
            disposition="REVISE",
            statement="Required reference-PDF section types are missing.",
            reason=f"Missing section IDs: {', '.join(missing_sections)}",
        )

    if len(actual_section_ids) != len(sections):
        record(
            severity="blocking",
            disposition="REVISE",
            statement="Section identifiers are not unique.",
            reason="A renderer cannot safely address duplicate section IDs.",
        )

    source_map = map_by_id(state.sources, "source_id")
    evidence_map = map_by_id(state.canonical_input.patient_evidence, "evidence_id")
    claim_map = map_by_id(all_report_claims(state), "claim_id")

    for source in state.sources:
        if not is_fully_qualified_url(source.url) or not source.url.startswith(
            "https://"
        ):
            record(
                severity="blocking",
                disposition="REMOVE",
                item_id=source.source_id,
                statement=f"Source URL is not a fully qualified HTTPS URL: {source.url}",
                reason="The output contract requires fully qualified URLs.",
                source_ids=[source.source_id],
            )
        normalized = normalize_url(source.url)
        if normalized != source.url:
            record(
                severity="warning",
                disposition="REVISE",
                item_id=source.source_id,
                statement="Source URL is not in canonical normalized form.",
                reason=f"Stored={source.url}; canonical={normalized}",
                suggested_revision=normalized,
                source_ids=[source.source_id],
            )
        if source.verification_status == "model_only":
            record(
                severity="warning",
                disposition="REVISE",
                item_id=source.source_id,
                statement="Source was proposed by the model but not verified in returned web-search source metadata.",
                reason="Use --strict-source-verification for production or manually verify the URL.",
                source_ids=[source.source_id],
            )
        if source.identifiers.nct_id:
            expected = (
                f"https://clinicaltrials.gov/study/{source.identifiers.nct_id.upper()}"
            )
            if normalize_url(source.url) != normalize_url(expected):
                record(
                    severity="error",
                    disposition="REVISE",
                    item_id=source.source_id,
                    statement="ClinicalTrials.gov source does not use the official canonical trial URL.",
                    reason=f"Expected {expected}",
                    suggested_revision=expected,
                    source_ids=[source.source_id],
                )

    for extraction in state.source_extractions:
        extraction_source = source_map.get(extraction.source_id)
        if extraction_source is None:
            record(
                severity="error",
                disposition="REMOVE",
                item_id=extraction.source_id,
                statement="Source extraction references an unknown source.",
                reason="The source registry contains no matching source ID.",
            )
        elif normalize_url(extraction.source_identity.url) != normalize_url(
            extraction_source.url
        ):
            record(
                severity="error",
                disposition="REVISE",
                item_id=extraction.source_id,
                statement="Source extraction URL differs from the registered source URL.",
                reason="The exact target URL must be preserved through extraction.",
                suggested_revision=extraction_source.url,
                source_ids=[extraction_source.source_id],
            )

    for assessment in state.source_fit_assessments:
        assessment_source = source_map.get(assessment.source_id)
        if assessment_source is None:
            record(
                severity="blocking",
                disposition="REMOVE",
                item_id=assessment.assessment_id,
                statement="URL-fit assessment references an unknown source.",
                reason=f"Unknown source ID: {assessment.source_id}",
            )
        elif normalize_url(assessment.url) != normalize_url(assessment_source.url):
            record(
                severity="error",
                disposition="REVISE",
                item_id=assessment.assessment_id,
                statement="URL-fit assessment URL differs from its source registry URL.",
                reason="The appendix must use the fully qualified registered URL.",
                suggested_revision=assessment_source.url,
                source_ids=[assessment.source_id],
            )
        for score_row in assessment.bottom_line_score_rows:
            if score_row.score_min > score_row.score_max:
                record(
                    severity="error",
                    disposition="REVISE",
                    item_id=assessment.assessment_id,
                    statement="Bottom-line score range is reversed.",
                    reason=f"{score_row.score_min}>{score_row.score_max}",
                    source_ids=[assessment.source_id],
                )

    if state.report_draft is not None:
        registry_ids = set(source_map)
        for link in state.report_draft.selected_links:
            link_source = source_map.get(link.source_id)
            if link_source is None:
                record(
                    severity="blocking",
                    disposition="REMOVE",
                    section_id=SECTION_IDS["selected_links"],
                    item_id=link.row_id,
                    statement="Selected link references an unknown source.",
                    reason=f"Unknown source ID: {link.source_id}",
                )
            elif normalize_url(link.url) != normalize_url(link_source.url):
                record(
                    severity="error",
                    disposition="REVISE",
                    section_id=SECTION_IDS["selected_links"],
                    item_id=link.row_id,
                    statement="Selected link URL does not match the source registry.",
                    reason="Registered source URLs are authoritative for rendering.",
                    suggested_revision=link_source.url,
                    source_ids=[link.source_id],
                )
        report_refs = recursively_collect_named_ids(
            state.report_draft,
            {"patient_evidence_ids", "source_ids", "source_id"},
        )
        unknown_sources = sorted(
            (report_refs["source_ids"] | report_refs["source_id"]) - registry_ids
        )
        if unknown_sources:
            record(
                severity="error",
                disposition="REVISE",
                statement="Report draft contains unknown source references.",
                reason=", ".join(unknown_sources),
                source_ids=unknown_sources,
            )
        unknown_evidence = sorted(
            report_refs["patient_evidence_ids"] - set(evidence_map)
        )
        if unknown_evidence:
            record(
                severity="error",
                disposition="REVISE",
                statement="Report draft contains unknown patient-evidence references.",
                reason=", ".join(unknown_evidence),
                patient_evidence_ids=unknown_evidence,
            )

    for claim in claim_map.values():
        unknown_sources = sorted(set(claim.external_source_ids) - set(source_map))
        unknown_evidence = sorted(set(claim.patient_evidence_ids) - set(evidence_map))
        if unknown_sources or unknown_evidence:
            record(
                severity="error",
                disposition="REVISE",
                item_id=claim.claim_id,
                statement="Claim provenance references unknown identifiers.",
                reason=(
                    f"Unknown sources={unknown_sources}; unknown patient evidence={unknown_evidence}"
                ),
                patient_evidence_ids=unknown_evidence,
                source_ids=unknown_sources,
            )

    if state.report_draft is not None and not state.report_draft.selected_links:
        record(
            severity="warning",
            disposition="PASS",
            section_id=SECTION_IDS["selected_links"],
            statement="No selected reference or trial links were produced.",
            reason="This can be valid for a non-actionable case, but it differs from the reference packet's enriched appendix.",
        )

    passed = not any(item.severity in {"error", "blocking"} for item in findings)
    return ValidationOutput(
        validator_id=stable_id(
            "validator",
            "deterministic_integrity",
            state.run_id,
            [item.finding_id for item in findings],
        ),
        validator_type="deterministic_integrity",
        passed=passed,
        findings=findings,
    )


def derive_packet_warnings(
    state: PipelineState,
    validations: Sequence[ValidationOutput],
) -> list[str]:
    warnings = list(state.warnings)
    if state.canonical_input.case.missing_context:
        warnings.append(
            "Missing clinical context: "
            + ", ".join(state.canonical_input.case.missing_context)
        )
    if not state.sources:
        warnings.append(
            "No external sources were selected; report evidence is internally limited."
        )
    for source in state.sources:
        if source.verification_status != "web_verified":
            warnings.append(
                f"Source {source.source_id} verification status: {source.verification_status}."
            )
    for validation in validations:
        for finding in validation.findings:
            if finding.severity in {"warning", "error", "blocking"}:
                warnings.append(
                    f"{validation.validator_type}/{finding.severity}: {finding.statement}"
                )
    return unique_preserve_order(warnings)


def assemble_final_packet(
    state: PipelineState,
    config: PipelineConfig,
    sections: Sequence[SectionEnvelope],
    validations: Sequence[ValidationOutput],
) -> FinalPacket:
    if state.report_draft is None or state.cross_source_synthesis is None:
        raise ValueError(
            "Final packet assembly requires report and cross-source synthesis."
        )

    claims = all_report_claims(state)
    packet_id = stable_id(
        "packet",
        state.run_id,
        state.report_draft.report_draft_id,
        state.cross_source_synthesis.synthesis_id,
        [item.section_id for item in sections],
    )
    sections_by_id = {item.section_id: item for item in sections}
    return FinalPacket(
        schema_version=OUTPUT_SCHEMA_VERSION,
        tool_version=TOOL_VERSION,
        packet_id=packet_id,
        run_id=state.run_id,
        case_id=state.canonical_input.case.case_id,
        generated_at=utc_now_iso(),
        source_input_sha256=state.source_input_sha256,
        model=config.model,
        reasoning_effort=config.reasoning_effort,
        clinical_disclaimer=(
            "Educational precision-oncology decision support only. This JSON does not "
            "diagnose disease, recommend treatment, or determine clinical-trial "
            "eligibility. Qualified clinicians must verify patient data, source "
            "evidence, current trial status, and all clinical decisions."
        ),
        canonical_input=state.canonical_input,
        hypotheses_by_id=map_by_id(state.hypotheses, "hypothesis_id"),
        research_jobs_by_id=map_by_id(state.research_jobs, "job_id"),
        sources_by_id=map_by_id(state.sources, "source_id"),
        source_extractions_by_id=map_by_id(state.source_extractions, "source_id"),
        source_fit_assessments_by_id=map_by_id(
            state.source_fit_assessments, "assessment_id"
        ),
        trial_prescreens_by_id=map_by_id(state.trial_prescreens, "prescreen_id"),
        hypothesis_syntheses_by_id=map_by_id(
            state.hypothesis_syntheses, "hypothesis_id"
        ),
        report_draft=state.report_draft,
        cross_source_synthesis=state.cross_source_synthesis,
        document_flow=[item.section_id for item in sections],
        sections_by_id=sections_by_id,
        patient_evidence_by_id=map_by_id(
            state.canonical_input.patient_evidence, "evidence_id"
        ),
        claims_by_id=map_by_id(claims, "claim_id"),
        artifacts_by_id=map_by_id(state.artifacts, "artifact_id"),
        validations=list(validations),
        usage_records=list(state.usage_records),
        warnings=derive_packet_warnings(state, validations),
    )


# ---------------------------------------------------------------------------
# CHECKPOINT / STOP CONTROL
# ---------------------------------------------------------------------------


PIPELINE_STAGES: tuple[str, ...] = (
    "canonical_input",
    "hypotheses",
    "research_plan",
    "sources",
    "source_extractions",
    "source_fit_assessments",
    "trial_prescreens",
    "hypothesis_syntheses",
    "report_draft",
    "cross_source_synthesis",
    "validations",
    "final_packet",
)


def should_stop(config: PipelineConfig, stage: str) -> bool:
    return config.stop_after == stage


def save_stage_checkpoint(
    store: ArtifactStore,
    state: PipelineState,
    stage: str,
) -> Path:
    store.save_checkpoint(state)
    path = store.run_dir / f"state_after_{stage}.json"
    atomic_write_json(path, serialize_state(state))
    return path


def save_canonical_preview(store: ArtifactStore, canonical: CanonicalInput) -> Path:
    path = store.run_dir / "canonical_input.json"
    atomic_write_json(path, canonical.model_dump(mode="json"))
    atomic_write_json(
        store.run_dir / "canonical_input.schema.json",
        CanonicalInput.model_json_schema(),
    )
    return path


# ---------------------------------------------------------------------------
# END-TO-END ORCHESTRATION — EFFECTFUL SHELL
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PipelineRunResult:
    run_id: str
    run_dir: Path
    final_json_path: Path | None
    schema_path: Path | None
    stopped_after: str


def build_initial_state(
    raw: Mapping[str, Any],
    source_bytes: bytes,
    config: PipelineConfig,
    actionable_override: Mapping[str, Any] | Sequence[Mapping[str, Any]] | None,
    clinical_overlay: Mapping[str, Any] | None,
) -> PipelineState:
    canonical = build_canonical_input(
        raw,
        actionable_override=actionable_override,
        clinical_overlay=clinical_overlay,
    )
    source_hash = hashlib.sha256(source_bytes).hexdigest()
    canonical_hash = sha256_text(canonical_json(canonical))
    run_id = stable_id(
        "run",
        canonical.case.case_id,
        source_hash,
        canonical_hash,
        config.model,
        config.reasoning_effort,
        config.enable_web_search,
        config.live_web_access,
        config.strict_source_verification,
        TOOL_VERSION,
        PROMPT_SET_VERSION,
        OUTPUT_SCHEMA_VERSION,
        length=28,
    )
    return PipelineState(
        run_id=run_id,
        source_input_sha256=source_hash,
        canonical_input=canonical,
    )


async def run_pipeline(
    *,
    input_path: Path,
    config: PipelineConfig,
    actionable_override_path: Path | None = None,
    clinical_overlay_path: Path | None = None,
) -> PipelineRunResult:
    source_bytes = input_path.read_bytes()
    raw = json.loads(source_bytes.decode("utf-8"))
    if not isinstance(raw, Mapping):
        raise ValueError("Input JSON root must be an object.")

    actionable_override = (
        read_json(actionable_override_path) if actionable_override_path else None
    )
    clinical_overlay = (
        read_json(clinical_overlay_path) if clinical_overlay_path else None
    )

    state = build_initial_state(
        raw,
        source_bytes,
        config,
        actionable_override,
        clinical_overlay,
    )
    store = ArtifactStore(config.output_dir, state.run_id)
    save_canonical_preview(store, state.canonical_input)

    canonical_artifact = artifact_from_payload(
        artifact_id=stable_id("artifact", "canonical_input", state.run_id),
        artifact_type="canonical_input",
        stage="canonical_input",
        payload=state.canonical_input,
        parents=[],
        input_value={
            "source_input_sha256": state.source_input_sha256,
            "actionable_override": actionable_override,
            "clinical_overlay": clinical_overlay,
        },
    )
    store.save_artifact(canonical_artifact)
    state = append_artifact(state, canonical_artifact)
    save_stage_checkpoint(store, state, "canonical_input")

    if config.dry_run or should_stop(config, "canonical_input"):
        return PipelineRunResult(
            run_id=state.run_id,
            run_dir=store.run_dir,
            final_json_path=None,
            schema_path=None,
            stopped_after="canonical_input",
        )

    gateway = OpenAIResponsesGateway(config, store)

    state = await stage_hypotheses(state, gateway, store)
    save_stage_checkpoint(store, state, "hypotheses")
    if should_stop(config, "hypotheses"):
        return PipelineRunResult(state.run_id, store.run_dir, None, None, "hypotheses")

    state = await stage_research_plan(state, gateway, store, config)
    save_stage_checkpoint(store, state, "research_plan")
    if should_stop(config, "research_plan"):
        return PipelineRunResult(
            state.run_id, store.run_dir, None, None, "research_plan"
        )

    state = await stage_source_discovery(state, gateway, store, config)
    save_stage_checkpoint(store, state, "sources")
    if should_stop(config, "sources"):
        return PipelineRunResult(state.run_id, store.run_dir, None, None, "sources")

    state = await stage_source_extractions(state, gateway, store)
    save_stage_checkpoint(store, state, "source_extractions")
    if should_stop(config, "source_extractions"):
        return PipelineRunResult(
            state.run_id, store.run_dir, None, None, "source_extractions"
        )

    state = await stage_source_fit_assessments(state, gateway, store)
    save_stage_checkpoint(store, state, "source_fit_assessments")
    if should_stop(config, "source_fit_assessments"):
        return PipelineRunResult(
            state.run_id, store.run_dir, None, None, "source_fit_assessments"
        )

    state = await stage_trial_prescreens(state, gateway, store)
    save_stage_checkpoint(store, state, "trial_prescreens")
    if should_stop(config, "trial_prescreens"):
        return PipelineRunResult(
            state.run_id, store.run_dir, None, None, "trial_prescreens"
        )

    state = await stage_hypothesis_syntheses(state, gateway, store)
    save_stage_checkpoint(store, state, "hypothesis_syntheses")
    if should_stop(config, "hypothesis_syntheses"):
        return PipelineRunResult(
            state.run_id, store.run_dir, None, None, "hypothesis_syntheses"
        )

    state = await stage_report_compiler(state, gateway, store)
    save_stage_checkpoint(store, state, "report_draft")
    if should_stop(config, "report_draft"):
        return PipelineRunResult(
            state.run_id, store.run_dir, None, None, "report_draft"
        )

    state = await stage_cross_source_synthesis(state, gateway, store)
    save_stage_checkpoint(store, state, "cross_source_synthesis")
    if should_stop(config, "cross_source_synthesis"):
        return PipelineRunResult(
            state.run_id, store.run_dir, None, None, "cross_source_synthesis"
        )

    state = await stage_llm_validations(state, gateway, store, config)
    sections = build_renderer_sections(state)
    deterministic_validation = deterministic_integrity_validation(state, sections)
    validations = state.validations + (deterministic_validation,)
    state = dataclasses.replace(state, validations=validations)

    validation_artifact = artifact_from_payload(
        artifact_id=stable_id(
            "artifact",
            "deterministic_integrity_validation",
            state.run_id,
            deterministic_validation.validator_id,
        ),
        artifact_type="validation_output",
        stage="deterministic_integrity",
        payload=deterministic_validation,
        parents=[
            state.report_draft.report_draft_id if state.report_draft else "",
            state.cross_source_synthesis.synthesis_id
            if state.cross_source_synthesis
            else "",
        ],
        input_value={
            "sections": [item.model_dump(mode="json") for item in sections],
            "state_hash": sha256_text(canonical_json(serialize_state(state))),
        },
    )
    store.save_artifact(validation_artifact)
    state = append_artifact(state, validation_artifact)
    save_stage_checkpoint(store, state, "validations")

    if should_stop(config, "validations"):
        return PipelineRunResult(state.run_id, store.run_dir, None, None, "validations")

    blocking = [
        finding
        for validation in validations
        for finding in validation.findings
        if finding.severity == "blocking"
    ]
    if blocking and not config.allow_blocking_validation:
        atomic_write_json(
            store.run_dir / "blocking_validation_findings.json",
            [item.model_dump(mode="json") for item in blocking],
        )
        raise RuntimeError(
            f"Final packet blocked by {len(blocking)} validation finding(s). "
            "Review blocking_validation_findings.json or rerun with "
            "--allow-blocking-validation for diagnostic output."
        )

    packet = assemble_final_packet(state, config, sections, validations)
    final_path = store.save_final(packet)
    schema_path = store.save_schema()
    atomic_write_json(
        store.run_dir / "run_manifest.json",
        {
            "run_id": state.run_id,
            "packet_id": packet.packet_id,
            "tool_version": TOOL_VERSION,
            "schema_version": OUTPUT_SCHEMA_VERSION,
            "prompt_set_version": PROMPT_SET_VERSION,
            "model": config.model,
            "reasoning_effort": config.reasoning_effort,
            "input_path": str(input_path.resolve()),
            "source_input_sha256": state.source_input_sha256,
            "final_json": str(final_path),
            "schema": str(schema_path),
            "generated_at": packet.generated_at,
            "counts": {
                "actionable_findings": len(state.canonical_input.actionable_findings),
                "secondary_findings": len(state.canonical_input.secondary_findings),
                "hypotheses": len(state.hypotheses),
                "research_jobs": len(state.research_jobs),
                "sources": len(state.sources),
                "source_fit_assessments": len(state.source_fit_assessments),
                "trial_prescreens": len(state.trial_prescreens),
                "sections": len(sections),
                "api_calls": len(state.usage_records),
            },
        },
    )
    return PipelineRunResult(
        run_id=state.run_id,
        run_dir=store.run_dir,
        final_json_path=final_path,
        schema_path=schema_path,
        stopped_after="final_packet",
    )


# ---------------------------------------------------------------------------
# COMMAND-LINE INTERFACE
# ---------------------------------------------------------------------------


def build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="precision-oncology-pipeline",
        description=(
            "Parse a Translume-style clinical JSON packet, enrich actionable "
            "findings with OpenAI Responses API web research, and emit a "
            "renderer-independent JSON representation of the 31-page "
            "Precision Oncology Actionable Packet content model."
        ),
    )
    parser.add_argument("--input", type=Path, help="Input clinical review-packet JSON.")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("precision_oncology_outputs"),
        help="Root output/cache directory (default: %(default)s).",
    )
    parser.add_argument(
        "--actionable-json",
        type=Path,
        help=(
            "Optional pre-plucked actionable findings JSON. Accepts either a list "
            "or an object with actionable_findings/secondary_findings/"
            "context_findings/technical_limitations."
        ),
    )
    parser.add_argument(
        "--clinical-overlay",
        type=Path,
        help=(
            "Optional JSON object providing known stage, setting, prior therapies, "
            "performance status, organ function, location, and other context."
        ),
    )
    parser.add_argument(
        "--api-key",
        default=OPENAI_API_KEY,
        help="OpenAI API key. Prefer OPENAI_API_KEY; value is never logged.",
    )
    parser.add_argument(
        "--model",
        default=OPENAI_MODEL,
        help="OpenAI model ID (default from OPENAI_MODEL: %(default)s).",
    )
    parser.add_argument(
        "--reasoning-effort",
        default=OPENAI_REASONING_EFFORT,
        choices=("none", "low", "medium", "high", "xhigh", "max"),
        help="Default reasoning effort for stages without a prompt-specific override.",
    )
    parser.add_argument("--max-concurrency", type=int, default=4)
    parser.add_argument("--max-attempts", type=int, default=5)
    parser.add_argument("--request-timeout", type=float, default=240.0)
    parser.add_argument("--max-research-jobs", type=int, default=24)
    parser.add_argument("--max-sources-per-job", type=int, default=5)
    parser.add_argument("--max-sources-per-hypothesis", type=int, default=10)
    parser.add_argument("--max-sources-total", type=int, default=24)
    parser.add_argument(
        "--no-strict-source-verification",
        action="store_true",
        help="Allow model-proposed URLs not present in returned web-source metadata.",
    )
    parser.add_argument(
        "--no-web",
        action="store_true",
        help="Disable external source discovery. Intended for pipeline-shape testing.",
    )
    parser.add_argument(
        "--offline-web-cache",
        action="store_true",
        help="Use web_search with external_web_access=false (indexed/cache-only).",
    )
    parser.add_argument(
        "--unlimited-web-context",
        action="store_true",
        help="Set web_search return_token_budget=unlimited; higher latency/cost.",
    )
    parser.add_argument(
        "--no-resume",
        action="store_true",
        help="Ignore the deterministic API response cache.",
    )
    parser.add_argument(
        "--store-prompt-payloads",
        action="store_true",
        help=(
            "Store complete prompt payloads in call audit files. These may contain "
            "protected health information; off by default."
        ),
    )
    parser.add_argument(
        "--skip-llm-validators",
        action="store_true",
        help="Skip the three model-based validation passes; deterministic checks remain.",
    )
    parser.add_argument(
        "--allow-blocking-validation",
        action="store_true",
        help="Write diagnostic output even when blocking validation findings exist.",
    )
    parser.add_argument(
        "--quick-test",
        action="store_true",
        help=(
            "Cost-controlled integration test: 6 research jobs, 2 sources/job, "
            "8 sources total, and model validators disabled."
        ),
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Parse and write canonical_input.json without making API calls.",
    )
    parser.add_argument(
        "--stop-after",
        choices=PIPELINE_STAGES,
        help="Stop after a named stage and persist the checkpoint.",
    )
    parser.add_argument(
        "--emit-schema-only",
        action="store_true",
        help="Write the final JSON Schema and exit; --input is not required.",
    )
    parser.add_argument("--verbose", action="store_true")
    return parser


def config_from_arguments(args: argparse.Namespace) -> PipelineConfig:
    quick = bool(args.quick_test)
    return PipelineConfig(
        api_key=str(args.api_key or ""),
        model=str(args.model),
        reasoning_effort=str(args.reasoning_effort),
        output_dir=args.output_dir,
        max_concurrency=max(1, int(args.max_concurrency)),
        max_attempts=max(1, int(args.max_attempts)),
        request_timeout_seconds=max(30.0, float(args.request_timeout)),
        max_research_jobs=6 if quick else max(1, int(args.max_research_jobs)),
        max_sources_per_job=2 if quick else max(1, int(args.max_sources_per_job)),
        max_sources_per_hypothesis=(
            4 if quick else max(1, int(args.max_sources_per_hypothesis))
        ),
        max_sources_total=8 if quick else max(1, int(args.max_sources_total)),
        strict_source_verification=not bool(args.no_strict_source_verification),
        enable_web_search=not bool(args.no_web),
        live_web_access=not bool(args.offline_web_cache),
        web_return_token_budget=(
            "unlimited" if args.unlimited_web_context else "default"
        ),
        resume=not bool(args.no_resume),
        store_prompt_payloads=bool(args.store_prompt_payloads),
        run_llm_validators=(not bool(args.skip_llm_validators)) and not quick,
        allow_blocking_validation=bool(args.allow_blocking_validation),
        dry_run=bool(args.dry_run),
        stop_after=args.stop_after,
    )


def emit_schema_only(output_dir: Path) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / "precision_oncology_packet.schema.json"
    atomic_write_json(path, FinalPacket.model_json_schema())
    return path


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_argument_parser()
    args = parser.parse_args(argv)
    configure_logging(args.verbose)

    if args.emit_schema_only:
        path = emit_schema_only(args.output_dir)
        print(path)
        return 0

    if args.input is None:
        parser.error("--input is required unless --emit-schema-only is used.")
    if not args.input.exists():
        parser.error(f"Input file does not exist: {args.input}")
    if args.actionable_json and not args.actionable_json.exists():
        parser.error(f"Actionable JSON does not exist: {args.actionable_json}")
    if args.clinical_overlay and not args.clinical_overlay.exists():
        parser.error(f"Clinical overlay JSON does not exist: {args.clinical_overlay}")

    config = config_from_arguments(args)
    if (
        not config.dry_run
        and config.stop_after != "canonical_input"
        and not config.api_key
    ):
        parser.error(
            "OPENAI_API_KEY is empty. Set it, use --api-key, or run --dry-run."
        )

    try:
        result = asyncio.run(
            run_pipeline(
                input_path=args.input,
                config=config,
                actionable_override_path=args.actionable_json,
                clinical_overlay_path=args.clinical_overlay,
            )
        )
    except KeyboardInterrupt:
        LOGGER.error("Interrupted; completed artifacts remain in the run directory.")
        return 130
    except (ValidationError, ValueError, RuntimeError, json.JSONDecodeError) as exc:
        # Do not dump prompt payloads or source JSON into logs.
        LOGGER.error("Pipeline failed: %s", normalize_whitespace(str(exc)))
        return 1

    print(f"run_id={result.run_id}")
    print(f"run_dir={result.run_dir}")
    print(f"stopped_after={result.stopped_after}")
    if result.final_json_path:
        print(f"final_json={result.final_json_path}")
    if result.schema_path:
        print(f"schema={result.schema_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
