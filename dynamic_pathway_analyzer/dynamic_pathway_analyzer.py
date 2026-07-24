#!/usr/bin/env python3
"""
Dynamic precision-oncology pathway analyzer.

Input:
    Any JSON case file containing some combination of disease context,
    molecular findings, hypotheses, trial records, sources, or evidence.

Output:
    1. <input>.pathway_analysis.json
    2. <input>.pathway_analysis.md

The pipeline:
    A. Recursively discovers useful case evidence without assuming one fixed schema.
    B. Uses an OpenAI structured-output call to normalize findings and build
       patient-specific pathway hypotheses.
    C. Uses the OpenAI web_search tool for current, focused evidence retrieval.
    D. Uses a final structured-output call to create a safe, reusable report object.
    E. Deterministically renders the report to Markdown.

Set OPENAI_API_KEY in the environment. Never hardcode a production key.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import time
from pathlib import Path
from typing import Any, Iterable, Literal
from urllib.parse import urlparse

from openai import OpenAI
from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# GLOBAL CONFIGURATION
# ---------------------------------------------------------------------------

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

# Current high-capability default. Change through --model or OPENAI_MODEL.
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-5.6")

# A smaller/cheaper model can be supplied independently for normalization.
NORMALIZER_MODEL = os.getenv("OPENAI_NORMALIZER_MODEL", OPENAI_MODEL)

MAX_JSON_CHARS = int(os.getenv("MAX_JSON_CHARS", "180000"))
MAX_FINDINGS = int(os.getenv("MAX_FINDINGS", "40"))
MAX_SOURCE_RECORDS = int(os.getenv("MAX_SOURCE_RECORDS", "40"))
MAX_RESEARCH_PATHWAYS = int(os.getenv("MAX_RESEARCH_PATHWAYS", "5"))

AUTHORITATIVE_RESEARCH_DOMAINS = [
    "clinicaltrials.gov",
    "pubmed.ncbi.nlm.nih.gov",
    "pmc.ncbi.nlm.nih.gov",
    "ncbi.nlm.nih.gov",
    "fda.gov",
    "accessdata.fda.gov",
    "cancer.gov",
    "ema.europa.eu",
    "who.int",
    "panomebio.com",
    "exactsciences.com"
]

GENE_KEY_NAMES = {
    "gene",
    "gene_symbol",
    "gene_or_marker",
    "marker",
    "biomarker",
    "target",
}

ALTERATION_KEY_NAMES = {
    "alteration",
    "alteration_type",
    "variant",
    "mutation",
    "display_label",
    "effect",
    "molecular_change",
}

DISEASE_KEY_NAMES = {
    "disease",
    "disease_name",
    "tumor_type",
    "cancer_type",
    "histology",
    "diagnosis",
}

TRIAL_PATTERN = re.compile(r"\bNCT\d{8}\b", re.IGNORECASE)
GENE_PATTERN = re.compile(r"^[A-Z0-9][A-Z0-9\-]{1,14}$")


# ---------------------------------------------------------------------------
# STRUCTURED MODELS
# ---------------------------------------------------------------------------

class SourcePointer(BaseModel):
    source_id: str | None = None
    title: str | None = None
    url: str | None = None
    source_type: str | None = None
    publication_or_update_date: str | None = None


class NormalizedFinding(BaseModel):
    finding_id: str
    gene_or_marker: str
    display_label: str
    alteration: str
    alteration_type: str
    molecular_layers: list[str] = Field(default_factory=list)
    priority: str | None = None
    confidence: float | None = None
    source_texts: list[str] = Field(default_factory=list)
    source_pages: list[int] = Field(default_factory=list)
    missing_validation: list[str] = Field(default_factory=list)
    contradictions: list[str] = Field(default_factory=list)
    existing_trial_ids: list[str] = Field(default_factory=list)
    evidence_status: Literal[
        "reported",
        "reported_but_unconfirmed",
        "low_confidence",
        "discordant",
        "not_reported",
    ] = "reported"


class CaseContext(BaseModel):
    disease: str | None = None
    histology: str | None = None
    stage: str | None = None
    setting: str | None = None
    specimen_site: str | None = None
    specimen_type: str | None = None
    tumor_percentage: float | None = None
    report_date: str | None = None
    prior_therapies: list[str] = Field(default_factory=list)
    line_of_therapy: str | None = None
    performance_status: str | None = None
    location: str | None = None
    matched_normal_available: bool | None = None
    missing_context: list[str] = Field(default_factory=list)


class PathwayHypothesis(BaseModel):
    pathway_id: str
    title: str
    pathway_type: Literal[
        "signaling",
        "cell_cycle",
        "dna_damage_repair",
        "homologous_recombination",
        "metabolic",
        "epigenetic",
        "immune",
        "apoptosis",
        "angiogenesis",
        "lineage_plasticity",
        "other",
    ]
    involved_findings: list[str] = Field(default_factory=list)
    patient_specific_basis: str
    simplified_pathway: list[str] = Field(
        description="Ordered plain-language steps from alteration to phenotype."
    )
    potential_vulnerabilities: list[str] = Field(default_factory=list)
    potential_bypass_or_escape_routes: list[str] = Field(default_factory=list)
    potential_combination_or_recombination_paths: list[str] = Field(
        default_factory=list,
        description=(
            "Mechanistically plausible combination strategies or, where relevant, "
            "DNA repair/recombination pathway interactions. These are hypotheses, "
            "not treatment recommendations."
        ),
    )
    required_companion_markers: list[str] = Field(default_factory=list)
    confirmation_questions: list[str] = Field(default_factory=list)
    research_queries: list[str] = Field(default_factory=list)
    caution: str


class NormalizedCaseMap(BaseModel):
    case: CaseContext
    findings: list[NormalizedFinding]
    pathway_hypotheses: list[PathwayHypothesis]
    excluded_or_unreliable_sections: list[str] = Field(default_factory=list)
    global_cautions: list[str] = Field(default_factory=list)


class EvidenceItem(BaseModel):
    claim: str
    evidence_tier: Literal[
        "standard_care",
        "guideline_supported",
        "disease_specific_clinical",
        "basket_trial_clinical",
        "early_clinical",
        "preclinical",
        "mechanistic_only",
        "insufficient",
    ]
    source_title: str
    source_url: str
    publication_or_update_date: str | None = None
    population_match: str
    supports: str
    does_not_establish: str


class ConsultedWebSource(BaseModel):
    pathway_id: str
    discovery_lane: Literal["authoritative", "open_web"]
    title: str
    url: str
    domain: str
    source_type: str | None = None


class PathwayReportSection(BaseModel):
    pathway_id: str
    title: str
    executive_interpretation: str
    simplified_pathway: list[str]
    biological_significance: str
    therapeutic_strategies: list[str]
    combination_or_recombination_paths: list[str]
    bypass_or_resistance_paths: list[str]
    required_confirmation: list[str]
    companion_markers_not_reported: list[str]
    evidence: list[EvidenceItem]
    clinical_actionability: str
    bottom_line: str


class FinalReport(BaseModel):
    title: str
    case_summary: str
    overall_interpretation: str
    pathways: list[PathwayReportSection]
    cross_pathway_interactions: list[str]
    missing_information_that_limits_use: list[str]
    no_assumption_statements: list[str]
    final_biological_significance: str
    final_clinical_actionability: str
    final_required_confirmation: str
    disclaimer: str


# ---------------------------------------------------------------------------
# GENERIC JSON DISCOVERY
# ---------------------------------------------------------------------------

def stable_id(prefix: str, value: Any) -> str:
    raw = json.dumps(value, sort_keys=True, default=str).encode("utf-8")
    return f"{prefix}_{hashlib.sha256(raw).hexdigest()[:16]}"


def walk_json(value: Any, path: tuple[str, ...] = ()) -> Iterable[tuple[tuple[str, ...], Any]]:
    yield path, value
    if isinstance(value, dict):
        for key, child in value.items():
            yield from walk_json(child, path + (str(key),))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            yield from walk_json(child, path + (str(index),))


def clean_scalar(value: Any, max_len: int = 1200) -> Any:
    if isinstance(value, str):
        value = " ".join(value.split())
        return value[:max_len]
    return value


def compact_dict(record: dict[str, Any], max_fields: int = 35) -> dict[str, Any]:
    preferred = [
        "finding_id", "gene_or_marker", "gene", "marker", "display_label",
        "alteration", "alteration_type", "variant", "molecular_layers",
        "priority", "reported_category", "clinical_roles", "confidence",
        "needs_human_review", "research_use_only", "source_pages",
        "source_texts", "missing_validation", "contradictions",
        "existing_drug_mentions", "existing_trial_ids",
        "title", "hypothesis_type", "biological_theme",
        "patient_specific_observation", "mechanism_to_validate",
        "therapy_classes_to_research", "confirmatory_questions",
        "critical_cautions", "clinical_question", "search_concepts",
        "url", "source_type", "source_role", "publication_or_update_date",
        "verification_status", "selection_score",
    ]
    output: dict[str, Any] = {}
    for key in preferred:
        if key in record:
            val = record[key]
            if isinstance(val, str):
                output[key] = clean_scalar(val)
            elif isinstance(val, list):
                output[key] = [
                    compact_dict(x) if isinstance(x, dict) else clean_scalar(x)
                    for x in val[:20]
                ]
            elif isinstance(val, dict):
                output[key] = {
                    k: clean_scalar(v)
                    for k, v in list(val.items())[:20]
                    if not isinstance(v, (dict, list))
                }
            else:
                output[key] = val
    if not output:
        for key, val in list(record.items())[:max_fields]:
            if isinstance(val, (str, int, float, bool)) or val is None:
                output[key] = clean_scalar(val)
    return output


def looks_like_finding(record: dict[str, Any]) -> bool:
    keys = {str(k).lower() for k in record}
    has_gene = bool(keys & GENE_KEY_NAMES)
    has_alteration = bool(keys & ALTERATION_KEY_NAMES)
    label = " ".join(str(record.get(k, "")) for k in record if str(k).lower() in GENE_KEY_NAMES)
    likely_gene = any(GENE_PATTERN.match(part) for part in re.findall(r"[A-Za-z0-9\-]+", label.upper()))
    return (has_gene and has_alteration) or (has_gene and likely_gene)


def looks_like_source(record: dict[str, Any]) -> bool:
    return bool(record.get("url")) and bool(
        record.get("title") or record.get("source_title") or record.get("publisher")
    )


def find_case_context(payload: dict[str, Any]) -> dict[str, Any]:
    candidates: list[dict[str, Any]] = []
    for path, value in walk_json(payload):
        if not isinstance(value, dict):
            continue
        keys = {str(k).lower() for k in value}
        score = len(keys & DISEASE_KEY_NAMES)
        score += 2 if "case_id" in keys else 0
        score += 1 if "specimen" in keys else 0
        score += 1 if "missing_context" in keys else 0
        if score:
            candidates.append({"path": ".".join(path), "score": score, "data": compact_dict(value)})
    candidates.sort(key=lambda x: x["score"], reverse=True)
    return candidates[0] if candidates else {"path": "", "score": 0, "data": {}}


def discover_payload(payload: dict[str, Any]) -> dict[str, Any]:
    findings: list[dict[str, Any]] = []
    sources: list[dict[str, Any]] = []
    trials: list[dict[str, Any]] = []
    hypotheses: list[dict[str, Any]] = []
    limitations: list[dict[str, Any]] = []

    seen_findings: set[str] = set()
    seen_sources: set[str] = set()
    seen_trials: set[str] = set()

    for path, value in walk_json(payload):
        if isinstance(value, dict):
            path_text = ".".join(path).lower()

            if looks_like_finding(value):
                compact = compact_dict(value)
                fingerprint = stable_id("finding", compact)
                if fingerprint not in seen_findings:
                    seen_findings.add(fingerprint)
                    findings.append({"json_path": ".".join(path), **compact})

            if looks_like_source(value):
                compact = compact_dict(value)
                fingerprint = str(compact.get("url") or stable_id("source", compact))
                if fingerprint not in seen_sources:
                    seen_sources.add(fingerprint)
                    sources.append({"json_path": ".".join(path), **compact})

            serialized = json.dumps(value, default=str)
            trial_ids = sorted({x.upper() for x in TRIAL_PATTERN.findall(serialized)})
            if trial_ids:
                compact = compact_dict(value)
                fingerprint = "|".join(trial_ids) + "|" + str(compact.get("url", ""))
                if fingerprint not in seen_trials:
                    seen_trials.add(fingerprint)
                    trials.append({
                        "json_path": ".".join(path),
                        "trial_ids": trial_ids,
                        **compact,
                    })

            if "hypoth" in path_text or "mechanism" in path_text or "pathway" in path_text:
                if any(k in value for k in (
                    "title", "hypothesis_type", "biological_theme",
                    "mechanism_to_validate", "patient_specific_observation",
                )):
                    hypotheses.append({"json_path": ".".join(path), **compact_dict(value)})

            if "limitation" in path_text or "warning" in path_text:
                if any(k in value for k in ("description", "clinical_effect", "limitation", "warning")):
                    limitations.append({"json_path": ".".join(path), **compact_dict(value)})

    # Prefer the highest-priority and best-supported findings.
    def finding_rank(x: dict[str, Any]) -> tuple[int, float, int]:
        priority = str(x.get("priority", "")).upper()
        priority_score = {"PRIMARY": 3, "ACTIONABLE": 3, "SECONDARY": 2, "CONTEXT": 1}.get(priority, 0)
        confidence = float(x.get("confidence") or 0)
        support = len(x.get("source_texts") or []) + len(x.get("source_pages") or [])
        return priority_score, confidence, support

    findings.sort(key=finding_rank, reverse=True)
    sources.sort(key=lambda x: float(x.get("selection_score") or 0), reverse=True)

    discovered = {
        "case_candidate": find_case_context(payload),
        "findings": findings[:MAX_FINDINGS],
        "existing_hypotheses_or_pathways": hypotheses[:40],
        "trial_records": trials[:30],
        "source_records": sources[:MAX_SOURCE_RECORDS],
        "technical_limitations": limitations[:30],
        "top_level_keys": list(payload.keys()),
    }

    raw = json.dumps(discovered, ensure_ascii=False)
    if len(raw) > MAX_JSON_CHARS:
        # Deterministic reduction before sending to the API.
        discovered["findings"] = discovered["findings"][:40]
        discovered["existing_hypotheses_or_pathways"] = discovered[
            "existing_hypotheses_or_pathways"
        ][:15]
        discovered["trial_records"] = discovered["trial_records"][:15]
        discovered["source_records"] = discovered["source_records"][:20]
        discovered["technical_limitations"] = discovered["technical_limitations"][:15]

    return discovered


# ---------------------------------------------------------------------------
# OPENAI CALLS
# ---------------------------------------------------------------------------

NORMALIZER_SYSTEM_PROMPT = """
You are a precision-oncology case normalizer.

You receive a schema-agnostic discovery bundle produced from an arbitrary JSON
case file. Build a patient-specific map without trusting prior model-generated
treatment rankings or speculative claims.

Requirements:
- Use the user-provided Diagnosis line as population context. Flag genuine
  conflicts with the supplied JSON instead of silently replacing either value.
- Preserve the exact disease, histology, specimen, and clinical context when present.
- Normalize genuine molecular findings across DNA, RNA, protein, immune, and
  other assay layers.
- Do not equate RNA underexpression, copy-number loss, homozygous deletion,
  protein loss, and functional pathway loss.
- Group findings into biologically coherent pathways dynamically. Do not use a
  fixed list of genes.
- Identify interactions among findings: synthetic lethality, pathway convergence,
  parallel dependencies, functional antagonism, DNA repair/recombination effects,
  potential bypass signaling, and potential combination hypotheses.
- A combination or recombination hypothesis must be labeled as mechanistic and
  investigational, never as a treatment recommendation.
- For each pathway, state the companion genes or proteins whose absence from the
  input prevents a conclusion.
- Generate focused research queries. Never combine unrelated genes into one query.
- For a primary metabolic, epigenetic, synthetic-lethal, combination, or
  resistance hypothesis, generate distinct queries for biochemical mechanism,
  metabolomics or pharmacodynamics, disease-specific evidence, combination
  rationale, human evidence, current trials, and high-quality translational
  commentary. Do not assume that useful research is hosted on a government site.
- Exclude contaminated graph context, unsupported treatment rankings, generic
  resistance language, duplicate artifacts, and claims that analytical sensitivity
  proves clinical actionability.
- Never invent a variant, biomarker value, drug, trial, or disease setting.
- Treat missing values as missing.
"""

RESEARCH_SYSTEM_PROMPT = """
You are a web-grounded precision-oncology research analyst.

Research one supplied patient-specific pathway using the open web. Search
dynamically wherever the relevant evidence is published; do not restrict
discovery to government, trial-registry, or PubMed domains. Focus only on the
pathway actually supported by this case.

Source priority:
1. Official trial registries and protocols.
2. FDA or relevant regulators.
3. Peer-reviewed primary research.
4. Professional guidelines or consensus.
5. Reviews for background.
6. High-quality translational, metabolomics, academic, biotechnology-research,
   conference, medical-news, or sponsor material when it contributes a distinct
   mechanism, development, monitoring, resistance, or trial-discovery insight.

Mandatory rules:
- Treat the user-provided Diagnosis line as the governing population context.
- Prioritize exact-histology evidence first, then the closest biologically
  relevant sarcoma/bone-tumor evidence, then tumor-agnostic evidence.
- Evidence from prostate, breast, lung, ovarian, or another unrelated cancer
  may be used only as indirect pathway, safety, resistance, or negative evidence.
  Label it explicitly as off-disease and do not present its drugs as candidates
  for the declared diagnosis unless independent disease-matched, tumor-agnostic,
  guideline, regulatory, or trial evidence supports that clinical role.
- Search each pathway separately.
- Distinguish disease-specific evidence from pan-cancer evidence.
- Verify current trial status, biomarker definitions, agent aliases, and regulatory status.
- Be moderately thorough rather than exhaustive. Prioritize only evidence that
  can materially change mechanism interpretation, confirmation, treatment or
  trial discussion, or resistance monitoring. Do not search every possible
  subtopic for every pathway.
- Look for high-quality explanatory or translational sources outside government
  sites. Do not omit a source merely because it is a journal-publisher,
  university, biotechnology-research, metabolomics, conference, medical-news,
  or sponsor domain.
- Label every source by role. A commentary, explainer, news article, or sponsor
  page may support mechanism interpretation or discovery, but cannot by itself
  establish efficacy, safety, approval, standard care, or patient eligibility.
- Corroborate material claims from commentary or sponsor sources with primary,
  regulatory, guideline, or official trial evidence whenever available.
- Do not imply that trial eligibility is established when clinical context is missing.
- Do not equate orphan designation with approval.
- Do not present a mechanistic combination hypothesis as safe, effective, or clinically usable.
- Explain possible bypass, escape, synthetic-lethal, combination, and DNA
  repair/recombination pathways when evidence supports them.
- Include full source URLs in the research memo.
- Use cautious language suitable for a molecular tumor board.
"""

FINALIZER_SYSTEM_PROMPT = """
You are a precision-oncology clinical narrative compiler.

Convert the normalized patient map and web-grounded research memo into the
required structured report.

Rules:
- Treat the user-provided Diagnosis line as authoritative and state it in the case
  summary and each population-fit assessment where relevant.
- Rank exact-diagnosis evidence above other sarcomas, other solid tumors, and
  unrelated cancers.
- Do not promote a drug into therapeutic strategies merely because it is used
  in prostate or another unrelated cancer. Such evidence must be labeled
  off-disease and may support only mechanism, caution, resistance, safety, or
  evidence-boundary discussion unless a separate source establishes relevance
  to the declared diagnosis or a genuinely tumor-agnostic indication.
- Every therapeutic, efficacy, trial-status, and regulatory statement must be
  supported by a source URL from the research memo.
- Preserve uncertainty and state when evidence is preclinical, basket-trial,
  early clinical, disease-specific, or insufficient.
- Use plain-language ordered pathway steps.
- Separate combination hypotheses from DNA repair/recombination biology when applicable.
- List potential bypass or resistance paths only when biologically grounded.
- Do not recommend a regimen.
- Do not claim that tumor-suppressor loss can be reversed in routine care.
- Do not infer intact RB, TP53, homologous-recombination deficiency, or any
  unreported companion marker.
- State "not reported in the supplied data" when necessary.
- End with biological significance, clinical actionability, and required confirmation.
"""


def with_retries(fn, attempts: int = 4, base_delay: float = 2.0):
    last_error: Exception | None = None
    for attempt in range(attempts):
        try:
            return fn()
        except Exception as exc:  # SDK/network/API errors
            last_error = exc
            if attempt == attempts - 1:
                break
            time.sleep(base_delay * (2 ** attempt))
    raise RuntimeError(f"OpenAI request failed after {attempts} attempts: {last_error}") from last_error


def normalize_case(
    client: OpenAI,
    discovered: dict[str, Any],
    model: str,
    diagnosis: str,
) -> NormalizedCaseMap:
    response = with_retries(
        lambda: client.responses.parse(
            model=model,
            input=[
                {"role": "system", "content": NORMALIZER_SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": (
                        f"Diagnosis: {diagnosis}\n\n"
                        "Normalize this discovered JSON evidence bundle:\n\n"
                        + json.dumps(discovered, ensure_ascii=False)
                    ),
                },
            ],
            text_format=NormalizedCaseMap,
        )
    )
    if response.output_parsed is None:
        raise RuntimeError("Normalizer returned no structured output.")
    result: NormalizedCaseMap = response.output_parsed
    result.pathway_hypotheses = result.pathway_hypotheses[:MAX_RESEARCH_PATHWAYS]
    return result


def extract_consulted_web_sources(
    response: Any,
    pathway_id: str,
    discovery_lane: Literal["authoritative", "open_web"],
) -> list[ConsultedWebSource]:
    """Extract the complete source list returned by hosted web search."""

    if hasattr(response, "model_dump"):
        payload = response.model_dump(mode="json")
    else:
        payload = response

    found: dict[str, ConsultedWebSource] = {}

    def walk(node: Any) -> None:
        if isinstance(node, dict):
            url = node.get("url")
            if isinstance(url, str) and url.startswith(("https://", "http://")):
                normalized = url.strip()
                found.setdefault(
                    normalized,
                    ConsultedWebSource(
                        pathway_id=pathway_id,
                        discovery_lane=discovery_lane,
                        title=str(node.get("title") or normalized),
                        url=normalized,
                        domain=(urlparse(normalized).hostname or "").lower(),
                        source_type=(
                            str(node.get("type")) if node.get("type") is not None else None
                        ),
                    ),
                )
            for child in node.values():
                walk(child)
        elif isinstance(node, list):
            for child in node:
                walk(child)

    walk(payload)
    return list(found.values())


def run_research_lane(
    client: OpenAI,
    model: str,
    prompt: dict[str, Any],
    lane: Literal["authoritative", "open_web"],
    diagnosis: str,
) -> tuple[str, list[ConsultedWebSource]]:
    """Run one bounded search lane and retain every consulted URL."""

    web_tool: dict[str, Any] = {
        "type": "web_search",
        "search_context_size": "medium",
    }
    if lane == "authoritative":
        web_tool["filters"] = {
            "allowed_domains": AUTHORITATIVE_RESEARCH_DOMAINS,
        }

    lane_instruction = (
        "Use authoritative medical sources: official trial registries, PubMed/PMC, "
        "regulators, government cancer resources, and professional evidence records."
        if lane == "authoritative"
        else
        "Search the unrestricted open web for distinctive, highly relevant sources "
        "that authoritative indexes may miss: journal publishers, academic groups, "
        "conference material, translational or metabolomics commentary, biotechnology "
        "research, medical news, and sponsor research. Avoid duplicating routine "
        "registry results unless needed for corroboration."
    )
    lane_prompt = dict(prompt)
    lane_prompt["search_lane"] = lane
    lane_prompt["lane_instruction"] = lane_instruction

    response = with_retries(
        lambda: client.responses.create(
            model=model,
            reasoning={"effort": "medium"},
            tools=[web_tool],
            tool_choice="required",
            include=["web_search_call.action.sources"],
            input=[
                {"role": "system", "content": RESEARCH_SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": (
                        f"Diagnosis: {diagnosis}\n\n"
                        + json.dumps(lane_prompt, ensure_ascii=False)
                    ),
                },
            ],
        )
    )
    if not response.output_text:
        raise RuntimeError(f"Research call returned no text for {lane} lane.")
    return response.output_text, extract_consulted_web_sources(
        response,
        "batched_priority_pathways",
        lane,
    )


def research_case(
    client: OpenAI,
    case_map: NormalizedCaseMap,
    model: str,
    diagnosis: str,
) -> tuple[str, list[ConsultedWebSource]]:
    """Run moderate authoritative and open-web searches across priority pathways."""

    pathways = case_map.pathway_hypotheses[:MAX_RESEARCH_PATHWAYS]
    if not pathways:
        raise RuntimeError("No pathway hypotheses were available for web research.")

    research_plan = []
    for pathway in pathways:
        research_plan.append({
            "pathway_id": pathway.pathway_id,
            "title": pathway.title,
            "patient_specific_basis": pathway.patient_specific_basis,
            "queries": pathway.research_queries[:3],
            "confirmation_questions": pathway.confirmation_questions[:4],
            "combination_or_recombination_paths": (
                pathway.potential_combination_or_recombination_paths[:4]
            ),
        })

    prompt = {
        "case_context": case_map.case.model_dump(),
        "priority_pathways": research_plan,
        "research_depth": "moderately thorough, highly relevant, not exhaustive",
        "source_budget": "Follow the lane-specific budget; retain only highly relevant sources.",
        "priorities": [
            "patient-specific mechanism and disease fit",
            "clinically meaningful human evidence or current trials",
            "confirmation requirements",
            "one high-value translational or mechanistic source when it adds distinct value",
            "important combination or resistance insight only when well supported",
        ],
        "requested_output": {
            "format": "concise pathway-organized research memo",
            "requirements": [
                "include only highly relevant sources",
                "name and classify every source used",
                "include full source URLs",
                "state what each source supports and does not establish",
                "separate mechanism value from clinical actionability",
                "avoid repetitive sources and marginally relevant background",
            ],
        },
    }

    authoritative_prompt = dict(prompt)
    authoritative_prompt["source_budget"] = {
        "target_sources": "6-10 total",
        "selection": "Best authoritative source per material claim; avoid redundant records.",
    }
    open_web_prompt = dict(prompt)
    open_web_prompt["source_budget"] = {
        "target_sources": "3-6 total",
        "selection": "Only distinctive sources that add mechanism, metabolomics, combination, resistance, or emerging-development value.",
    }

    authoritative_memo, authoritative_sources = run_research_lane(
        client, model, authoritative_prompt, "authoritative", diagnosis
    )
    open_web_memo, open_web_sources = run_research_lane(
        client, model, open_web_prompt, "open_web", diagnosis
    )

    source_map: dict[str, ConsultedWebSource] = {}
    for source in [*authoritative_sources, *open_web_sources]:
        source_map.setdefault(source.url, source)
    sources = list(source_map.values())
    memo = "\n".join([
        "# Moderately thorough hybrid pathway research",
        "",
        "## Authoritative medical and trial research",
        "",
        authoritative_memo,
        "",
        "## Open-web translational discovery",
        "",
        open_web_memo,
        "",
        "## All consulted web sources",
        "",
        *[
            f"- [{source.title}]({source.url}) — {source.discovery_lane}"
            for source in sources
        ],
        "",
    ])
    return memo, sources


def finalize_report(
    client: OpenAI,
    case_map: NormalizedCaseMap,
    research_memo: str,
    model: str,
    diagnosis: str,
) -> FinalReport:
    payload = {
        "normalized_case_map": case_map.model_dump(),
        "research_memo": research_memo,
    }
    response = with_retries(
        lambda: client.responses.parse(
            model=model,
            input=[
                {"role": "system", "content": FINALIZER_SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": (
                        f"Diagnosis: {diagnosis}\n\n"
                        + json.dumps(payload, ensure_ascii=False)
                    ),
                },
            ],
            text_format=FinalReport,
        )
    )
    if response.output_parsed is None:
        raise RuntimeError("Finalizer returned no structured output.")
    return response.output_parsed


# ---------------------------------------------------------------------------
# OUTPUT RENDERING
# ---------------------------------------------------------------------------

def render_markdown(report: FinalReport) -> str:
    lines: list[str] = [
        f"# {report.title}",
        "",
        "## Case summary",
        "",
        report.case_summary,
        "",
        "## Overall interpretation",
        "",
        report.overall_interpretation,
        "",
    ]

    for index, pathway in enumerate(report.pathways, start=1):
        lines.extend([
            f"## {index}. {pathway.title}",
            "",
            pathway.executive_interpretation,
            "",
            "### Simplified pathway",
            "",
            "```text",
        ])
        for step_index, step in enumerate(pathway.simplified_pathway):
            prefix = "" if step_index == 0 else "   ↓\n"
            lines.append(prefix + step)
        lines.extend(["```", "", "### Biological significance", "", pathway.biological_significance, ""])

        if pathway.therapeutic_strategies:
            lines.extend(["### Therapeutic strategies to investigate", ""])
            lines.extend(f"- {x}" for x in pathway.therapeutic_strategies)
            lines.append("")

        if pathway.combination_or_recombination_paths:
            lines.extend(["### Potential combination or recombination pathways", ""])
            lines.extend(f"- {x}" for x in pathway.combination_or_recombination_paths)
            lines.append("")

        if pathway.bypass_or_resistance_paths:
            lines.extend(["### Potential bypass or resistance pathways", ""])
            lines.extend(f"- {x}" for x in pathway.bypass_or_resistance_paths)
            lines.append("")

        if pathway.required_confirmation:
            lines.extend(["### Required confirmation", ""])
            lines.extend(f"- {x}" for x in pathway.required_confirmation)
            lines.append("")

        if pathway.companion_markers_not_reported:
            lines.extend(["### Companion markers not reported", ""])
            lines.extend(f"- {x}" for x in pathway.companion_markers_not_reported)
            lines.append("")

        if pathway.evidence:
            lines.extend(["### Evidence", ""])
            for evidence in pathway.evidence:
                lines.extend([
                    f"**{evidence.source_title}** — `{evidence.evidence_tier}`",
                    "",
                    f"{evidence.claim}",
                    "",
                    f"- Population fit: {evidence.population_match}",
                    f"- Supports: {evidence.supports}",
                    f"- Does not establish: {evidence.does_not_establish}",
                    f"- Source: {evidence.source_url}",
                    "",
                ])

        lines.extend([
            "### Clinical actionability",
            "",
            pathway.clinical_actionability,
            "",
            "### Bottom line",
            "",
            pathway.bottom_line,
            "",
        ])

    if report.cross_pathway_interactions:
        lines.extend(["## Cross-pathway interactions", ""])
        lines.extend(f"- {x}" for x in report.cross_pathway_interactions)
        lines.append("")

    if report.missing_information_that_limits_use:
        lines.extend(["## Missing information that limits clinical use", ""])
        lines.extend(f"- {x}" for x in report.missing_information_that_limits_use)
        lines.append("")

    if report.no_assumption_statements:
        lines.extend(["## Must not assume", ""])
        lines.extend(f"- {x}" for x in report.no_assumption_statements)
        lines.append("")

    lines.extend([
        "## Biological significance",
        "",
        report.final_biological_significance,
        "",
        "## Clinical actionability",
        "",
        report.final_clinical_actionability,
        "",
        "## Required confirmation",
        "",
        report.final_required_confirmation,
        "",
        "## Clinical-use notice",
        "",
        report.disclaimer,
        "",
    ])
    return "\n".join(lines)


def analyze_file(
    input_path: Path,
    output_dir: Path,
    model: str,
    normalizer_model: str,
    diagnosis: str,
) -> tuple[Path, Path]:
    if not OPENAI_API_KEY:
        raise RuntimeError(
            "OPENAI_API_KEY is not set. Export it before running:\n"
            "  export OPENAI_API_KEY='sk-proj-...'"
        )

    try:
        payload = json.loads(input_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Invalid JSON in {input_path}: {exc}") from exc

    if not isinstance(payload, dict):
        payload = {"input": payload}

    output_dir.mkdir(parents=True, exist_ok=True)
    client = OpenAI(api_key=OPENAI_API_KEY)

    discovered = discover_payload(payload)
    print("[1/4] Normalizing case and diagnosis...", flush=True)
    case_map = normalize_case(client, discovered, normalizer_model, diagnosis)
    print("[2/4–3/4] Running authoritative and open-web research...", flush=True)
    research_memo, consulted_sources = research_case(
        client, case_map, model, diagnosis
    )
    print("[4/4] Compiling diagnosis-aligned report...", flush=True)
    report = finalize_report(client, case_map, research_memo, model, diagnosis)

    stem = input_path.stem
    json_path = output_dir / f"{stem}.pathway_analysis.json"
    md_path = output_dir / f"{stem}.pathway_analysis.md"
    debug_path = output_dir / f"{stem}.normalized_case_map.json"
    research_path = output_dir / f"{stem}.research_memo.md"
    sources_path = output_dir / f"{stem}.research_sources.json"

    json_path.write_text(
        json.dumps(report.model_dump(), indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    md_path.write_text(render_markdown(report), encoding="utf-8")
    debug_path.write_text(
        json.dumps(case_map.model_dump(), indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    research_path.write_text(research_memo, encoding="utf-8")
    sources_path.write_text(
        json.dumps(
            [source.model_dump() for source in consulted_sources],
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    return json_path, md_path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate a dynamic pathway and combination/recombination analysis from any oncology JSON."
    )
    parser.add_argument("input_json", type=Path)
    parser.add_argument("--output-dir", type=Path, default=Path("./pathway_output"))
    parser.add_argument("--model", default=OPENAI_MODEL)
    parser.add_argument("--normalizer-model", default=NORMALIZER_MODEL)
    parser.add_argument(
        "--diagnosis",
        required=True,
        help="User-defined diagnosis appended to every model prompt.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        json_path, md_path = analyze_file(
            input_path=args.input_json,
            output_dir=args.output_dir,
            model=args.model,
            normalizer_model=args.normalizer_model,
            diagnosis=args.diagnosis,
        )
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    print(f"Structured JSON: {json_path}")
    print(f"Markdown report: {md_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
