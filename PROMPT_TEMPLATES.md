# Implementation-ready workflow

Assumption: your existing code already produces a **clean list of actionable findings** from the larger review-packet JSON. The pipeline below starts from that point and produces:

1. the seven-page clinical summary;
2. selected reference and trial links;
3. one candidate-fit assessment per selected URL;
4. cross-source synthesis;
5. a final render-ready JSON document.

That mirrors the structure of the uploaded PDF: executive summary, key findings, mechanism, therapy options, resistance, follow-up testing, phenotypic triggers, limitations, selected links, source-by-source assessments, and cross-source synthesis. 

The uploaded Translume JSON already exposes useful nested objects under `bundle`, including `extraction`, `phenotype`, `matrix`, `confirmatory`, `tumor_behavior`, `decision_brief`, `claims`, and `provenance`. 

---

# 1. Canonical input contract

Do not pass the full raw JSON into each prompt. Convert it once into a compact canonical object.

```json
{
  "case": {
    "case_id": "case_...",
    "session_id": "session_...",
    "source_file_id": "file_...",
    "report_type": "NGS",
    "disease": {
      "name": "dedifferentiated chondrosarcoma",
      "stage": null,
      "setting": null
    },
    "specimen": {
      "site": "soft tissue, chest wall",
      "collection_date": null,
      "tumor_percentage": 80
    },
    "prior_therapies": [],
    "line_of_therapy": null,
    "performance_status": null,
    "organ_function": null,
    "measurable_disease": null,
    "biopsy_feasibility": null,
    "location": null,
    "validation_status": "needs_review"
  },
  "actionable_findings": [
    {
      "finding_id": "finding_...",
      "gene_or_marker": "MTAP",
      "display_label": "MTAP loss / underexpression",
      "alteration": "copy-number loss",
      "alteration_type": "loss",
      "molecular_layer": ["DNA", "RNA"],
      "priority": "PRIMARY",
      "clinical_roles": [
        "tumor_biology",
        "therapeutic_biomarker",
        "trial_biomarker"
      ],
      "source_page": 3,
      "source_chunk_id": "chunk_...",
      "source_text": "MTAP Copy number loss",
      "confidence": 0.93,
      "needs_human_review": true,
      "research_use_only": false,
      "related_finding_ids": [],
      "contradictions": [],
      "missing_validation": [
        "homozygous deletion status",
        "MTAP protein confirmation"
      ],
      "existing_drug_mentions": [],
      "existing_trial_ids": []
    }
  ],
  "secondary_findings": [],
  "technical_limitations": [
    {
      "limitation_id": "lim_...",
      "label": "TAF1 low coverage",
      "description": "The assay could not reliably evaluate this region.",
      "source_page": 3,
      "source_chunk_id": "chunk_...",
      "clinical_effect": "Do not interpret a non-call as a true negative."
    }
  ],
  "negative_findings": [],
  "existing_context": {
    "phenotype_axes": [],
    "treatment_matrix": [],
    "confirmatory_tests": [],
    "tumor_behavior": {},
    "ranked_treatment_hints": [],
    "treatment_pressure_hints": [],
    "resistance_hints": [],
    "biomarker_watch_hints": [],
    "retesting_triggers": [],
    "next_test_hints": [],
    "evidence_limitations": []
  },
  "provenance": {
    "evidence_sentences": [],
    "claims": [],
    "artifact_records": []
  }
}
```

Your prompts should consume this canonical object, not the entire source packet.

---

# 2. Exact source JSON pathways

These are the relevant paths in the uploaded Translume structure.

## Case metadata

| Canonical field                  | Source JSONPath                              | Notes                                       |
| -------------------------------- | -------------------------------------------- | ------------------------------------------- |
| `case.case_id`                   | `$.case_id`                                  | Also available at `$.bundle.case_id`        |
| `case.session_id`                | `$.session_id`                               | Also available at `$.bundle.session_id`     |
| `case.source_file_id`            | `$.source_file_id`                           |                                             |
| `case.report_type`               | `$.bundle.extraction.report_type`            |                                             |
| `case.disease.name`              | `$.bundle.extraction.disease`                | Use chunk fallback when null                |
| `case.specimen.site`             | `$.bundle.extraction.specimen`               | Use chunk fallback when null                |
| `case.specimen.tumor_percentage` | `$.bundle.extraction.tumor_percentage`       | Use chunk fallback when null                |
| `case.validation_status`         | `$.bundle.decision_brief.validation_status`  | Optional                                    |
| metadata fallback                | `$.chunks[?(@.chunk_type=="case_metadata")]` | Parse diagnosis/specimen from `source_text` |

Because the sample extraction has null disease/specimen fields even though source chunks contain the information, use this fallback order:

```text
bundle.extraction field
→ structured clinical-data object from your own pipeline
→ case_metadata chunks
→ null
```

Never infer missing stage, line of therapy, performance status, organ function, or prior therapy.

## Findings

| Canonical field                   | Source JSONPath                             |
| --------------------------------- | ------------------------------------------- |
| candidate list before your filter | `$.bundle.extraction.molecular_findings[*]` |
| `finding_id`                      | `.finding_id`                               |
| `gene_or_marker`                  | `.gene`                                     |
| `alteration`                      | `.alteration`                               |
| `alteration_type`                 | `.alteration_type`                          |
| `source_page`                     | `.source_page`                              |
| `source_chunk_id`                 | `.source_chunk_id`                          |
| `source_text`                     | `.source_text`                              |
| `confidence`                      | `.confidence`                               |
| `needs_human_review`              | `.needs_human_review`                       |
| `research_use_only`               | `.research_use_only`                        |

Your plucker’s output should replace this raw list:

```text
$.bundle.extraction.molecular_findings[*]
        ↓ your filter/reconciliation
$.actionable_findings[*]
$.secondary_findings[*]
$.technical_limitations[*]
```

## Finding joins

These joins are useful for recovering supporting context.

```text
finding.finding_id
    → $.bundle.entities.entities[
         source_finding_id == finding.finding_id
       ]

finding.finding_id
    → $.bundle.phenotype.axes[
         supporting_finding_ids contains finding.finding_id
       ]

finding.source_chunk_id
    → $.chunks[
         chunk_id == finding.source_chunk_id
       ]

finding.source_chunk_id
    → $.bundle.decision_brief.evidence_sentence_map[
         source_chunk_ids contains finding.source_chunk_id
       ]
```

## Technical limitations and negatives

| Canonical field            | Source JSONPath                                                        |
| -------------------------- | ---------------------------------------------------------------------- |
| assay limitations          | `$.bundle.extraction.assay_limitations[*]`                             |
| negative findings          | `$.bundle.extraction.negative_findings[*]`                             |
| must-not-assume statements | `$.bundle.confirmatory.must_not_assume[*]`                             |
| missing evidence           | `$.bundle.evidence_context.missing_evidence[*]`                        |
| conflicting evidence       | `$.bundle.evidence_context.conflicting_evidence[*]`                    |
| reasoning warnings         | `$.bundle.evidence_context.medea_reasoning.warnings[*]`                |
| low-coverage findings      | filtered actionable findings where `alteration_type == "low coverage"` |

## Optional internal hints

These are useful for planning, but because your actionable plucker is already authoritative, use them as hints rather than patient ground truth.

| Context                     | JSONPath                                               |
| --------------------------- | ------------------------------------------------------ |
| phenotype axes              | `$.bundle.phenotype.axes[*]`                           |
| phenotype limitations       | `$.bundle.phenotype.limitations[*]`                    |
| treatment matrix            | `$.bundle.matrix.rows[*]`                              |
| confirmatory tests          | `$.bundle.confirmatory.tests[*]`                       |
| tumor state evidence        | `$.bundle.tumor_behavior.state_evidence[*]`            |
| tumor transition hypotheses | `$.bundle.tumor_behavior.transition_hypotheses[*]`     |
| current tumor state         | `$.bundle.decision_brief.current_tumor_state`          |
| actionable biology hints    | `$.bundle.decision_brief.actionable_biology[*]`        |
| ranked treatment hints      | `$.bundle.decision_brief.ranked_treatment_options[*]`  |
| treatment-pressure hints    | `$.bundle.decision_brief.treatment_pressure_map[*]`    |
| resistance hints            | `$.bundle.decision_brief.resistance_forecast[*]`       |
| biomarker watch list        | `$.bundle.decision_brief.biomarker_watch_list[*]`      |
| retesting triggers          | `$.bundle.decision_brief.retesting_triggers[*]`        |
| next-test recommendations   | `$.bundle.decision_brief.next_test_recommendations[*]` |
| translational assessment    | `$.bundle.decision_brief.translational_assessment`     |
| evidence limitations        | `$.bundle.decision_brief.evidence_limitations[*]`      |

## Provenance

| Canonical field            | Source JSONPath                                    |
| -------------------------- | -------------------------------------------------- |
| patient evidence sentences | `$.bundle.decision_brief.evidence_sentence_map[*]` |
| claim records              | `$.bundle.claims[*]`                               |
| artifact provenance        | `$.bundle.provenance[*]`                           |
| raw chunks                 | `$.chunks[*]`                                      |

---

# 3. Runtime artifact structure

Keep every stage in one run-state object. This gives every prompt variable an exact path.

```json
{
  "input": {},
  "hypotheses": [],
  "research_jobs": [],
  "sources": {},
  "source_extractions": {},
  "source_fit_assessments": {},
  "trial_prescreens": {},
  "hypothesis_syntheses": {},
  "report": {},
  "validation": {},
  "render": {}
}
```

Recommended storage paths:

```text
$.input                         canonical actionable input
$.hypotheses[*]                 Prompt 1 output
$.research_jobs[*]              Prompt 2 output
$.sources.<source_id>           search/fetch output
$.source_extractions.<source_id>
$.source_fit_assessments.<source_id>
$.trial_prescreens.<source_id>
$.hypothesis_syntheses.<hypothesis_id>
$.report                        final compiler output
$.validation                    validation output
```

---

# 4. Workflow

```text
Canonical actionable input
    ↓
1. Build biological hypotheses
    ↓
2. Create research jobs
    ↓
3. Search and select URLs
    ↓
4. Extract each source
    ↓
5. Assess patient-to-source fit
    ↓
6. Pre-screen trial records
    ↓
7. Synthesize evidence by hypothesis
    ↓
8. Compile main report + appendix data
    ↓
9. Validate claims and population alignment
    ↓
10. Render PDF deterministically
```

Prompts 3–6 can run concurrently.

---

# 5. Prompt 1 — Biological hypothesis builder

## Variables

```text
{{case_context}}          = $.input.case
{{actionable_findings}}   = $.input.actionable_findings
{{secondary_findings}}    = $.input.secondary_findings
{{technical_limitations}} = $.input.technical_limitations
{{internal_hints}}        = $.input.existing_context
```

## Prompt

```text
SYSTEM

You are a precision-oncology biological-hypothesis builder.

Your input has already been filtered to contain clinically relevant findings.
Do not repeat the filtering process.
Do not search the internet.
Do not name a drug or therapy unless it is already present in the supplied data.
Do not treat a technical limitation as a tumor alteration.
Do not treat a VUS, expression-only signal, or research-use-only observation
as a validated therapeutic biomarker without explicit support.

Group related findings into clinically coherent hypotheses. Hypotheses may
represent:

- oncogenic-driver signaling;
- tumor-suppressor loss;
- DNA-damage response;
- cell-cycle dysregulation;
- metabolic vulnerability;
- immune context;
- fusion or rearrangement biology;
- resistance biology;
- diagnostic or prognostic biology;
- technical limitations.

A hypothesis may contain more than one finding when the findings describe
the same region, pathway, or therapeutic vulnerability.

USER

CASE CONTEXT:
{{case_context}}

PRIMARY ACTIONABLE FINDINGS:
{{actionable_findings}}

SECONDARY FINDINGS:
{{secondary_findings}}

TECHNICAL LIMITATIONS:
{{technical_limitations}}

OPTIONAL INTERNAL HINTS:
{{internal_hints}}

Return JSON only:

{
  "hypotheses": [
    {
      "hypothesis_id": "",
      "title": "",
      "hypothesis_type": "",
      "primary_finding_ids": [],
      "supporting_finding_ids": [],
      "technical_limitation_ids": [],
      "biological_theme": "",
      "patient_specific_observation": "",
      "mechanism_to_validate": "",
      "potential_clinical_roles": [],
      "therapy_classes_to_research": [],
      "trial_search_required": false,
      "variant_interpretation_required": false,
      "confirmatory_questions": [],
      "critical_cautions": [],
      "missing_context": [],
      "research_priority": "high|medium|low|none",
      "patient_evidence_ids": []
    }
  ]
}
```

## Output

```text
$.hypotheses
```

Use deterministic IDs, for example:

```python
hypothesis_id = sha256(
    "|".join(sorted(primary_finding_ids)) + "|" + biological_theme
).hexdigest()[:16]
```

---

# 6. Prompt 2 — Research planner

## Variables

```text
{{case_context}}   = $.input.case
{{hypotheses}}     = $.hypotheses
{{missing_context}} = derived in code
```

Build `missing_context` by checking for null or empty values:

```text
case.disease.name
case.disease.stage
case.disease.setting
case.prior_therapies
case.line_of_therapy
case.performance_status
case.organ_function
case.measurable_disease
case.biopsy_feasibility
case.location
finding.missing_validation
```

## Prompt

```text
SYSTEM

You are a precision-oncology evidence-planning engine.

Generate only the research needed to support the requested clinical report.

For each biological hypothesis, decide whether research is needed for:

- exact biomarker or variant interpretation;
- disease-specific relevance;
- molecular mechanism;
- standard-care or regulatory status;
- human clinical evidence;
- current clinical trials;
- biomarker confirmation requirements;
- population alignment;
- resistance and escape;
- monitoring or re-testing.

Do not generate every category automatically.
Do not invent publications, URLs, drugs, trial identifiers, approvals, or
guidelines.
Do not search yet.

USER

CASE CONTEXT:
{{case_context}}

BIOLOGICAL HYPOTHESES:
{{hypotheses}}

KNOWN MISSING CONTEXT:
{{missing_context}}

Return JSON only:

{
  "research_jobs": [
    {
      "job_id": "",
      "hypothesis_id": "",
      "question_type": "variant|disease|mechanism|regulatory|clinical_evidence|trial|confirmation|population|resistance|monitoring",
      "clinical_question": "",
      "search_concepts": {
        "disease": [],
        "histology": [],
        "genes_or_markers": [],
        "alterations": [],
        "pathways": [],
        "therapy_classes": [],
        "agents_already_known": [],
        "trial_ids_already_known": []
      },
      "source_roles_needed": [
        "primary_mechanism",
        "human_clinical",
        "trial_record",
        "guideline_or_regulatory",
        "variant_database",
        "resistance_or_monitoring"
      ],
      "preferred_sources": [],
      "minimum_evidence_level": "",
      "maximum_sources": 5,
      "required_report_sections": [],
      "stop_condition": "",
      "priority": "high|medium|low"
    }
  ]
}
```

## Output

```text
$.research_jobs
```

---

# 7. Prompt 3 — URL discovery and evidence retrieval

This prompt runs once per research job with web-search tools enabled.

## Variables

```text
{{research_job}}          = $.research_jobs[i]
{{minimal_patient_anchor}} = derived from:
    $.input.case
    + the matching $.hypotheses[hypothesis_id]
    + only the relevant findings
```

Do not send unrelated patient findings to each search.

## Minimal patient anchor

```json
{
  "disease": {},
  "relevant_findings": [],
  "hypothesis": {},
  "known_missing_context": []
}
```

## Prompt

```text
SYSTEM

You are an evidence-retrieval agent for a precision-oncology reporting
system.

Search only for the supplied research job.

Prioritize:

1. authoritative current records;
2. primary human clinical evidence;
3. primary mechanistic studies;
4. current clinical-trial records;
5. regulatory or guideline evidence;
6. high-quality reviews when primary evidence is insufficient.

Reject:

- sources that merely mention the gene;
- duplicate reports of the same study;
- trial-mirror websites when an official record exists;
- unsupported promotional content;
- sources that cannot contribute to a required report section;
- sources whose population or biomarker is unrelated to the question.

Do not write the patient report.
Do not determine treatment.
Do not infer trial eligibility.

USER

RESEARCH JOB:
{{research_job}}

MINIMAL PATIENT ANCHOR:
{{minimal_patient_anchor}}

Use available search and browsing tools.

Return JSON only:

{
  "job_id": "",
  "searches_run": [
    {
      "query": "",
      "purpose": ""
    }
  ],
  "candidate_sources": [
    {
      "source_id": "",
      "hypothesis_id": "",
      "job_id": "",
      "url": "",
      "canonical_url": "",
      "title": "",
      "publisher": "",
      "source_type": "primary_research|clinical_study|trial_record|guideline|regulatory|review|conference|news|sponsor",
      "publication_or_update_date": null,
      "identifiers": {
        "doi": null,
        "pmid": null,
        "pmcid": null,
        "nct_id": null
      },
      "source_role": "",
      "why_candidate": "",
      "patient_anchor_matched": [],
      "apparent_evidence_level": "",
      "requires_full_text": true
    }
  ],
  "unresolved_questions": []
}
```

## Output

Merge into:

```text
$.sources.<source_id>
```

---

# 8. Source deduplication in code

Do this without another LLM call.

Canonical key priority:

```python
def canonical_source_key(source: dict) -> str:
    ids = source.get("identifiers", {})

    if ids.get("nct_id"):
        return f"nct:{ids['nct_id'].upper()}"

    if ids.get("doi"):
        return f"doi:{ids['doi'].lower().strip()}"

    if ids.get("pmid"):
        return f"pmid:{ids['pmid']}"

    if ids.get("pmcid"):
        return f"pmcid:{ids['pmcid'].upper()}"

    return f"url:{normalize_url(source['canonical_url'])}"
```

Keep one primary paper over:

* a news summary of the same paper;
* a preprint when a final publication exists;
* a trial mirror when ClinicalTrials.gov exists.

A useful source score:

```text
authority                    0–2
biomarker match              0–2
disease/population match     0–2
clinical maturity            0–2
currentness                  0–1
unique contribution          0–1
```

---

# 9. Prompt 4 — Source extraction

Runs once per selected source.

## Variables

```text
{{retrieved_source}} = $.sources.<source_id>.retrieved_content
{{source_metadata}}  = $.sources.<source_id>
```

## Prompt

```text
SYSTEM

You are a clinical-evidence extractor.

Extract only what the supplied source reports.

Do not compare it with the patient.
Do not make treatment recommendations.
Do not fill absent information by inference.
Distinguish source claims from your interpretation.
When a field is absent, use null or an empty array.

USER

SOURCE METADATA:
{{source_metadata}}

SOURCE CONTENT:
{{retrieved_source}}

Return JSON only:

{
  "source_id": "",
  "source_identity": {
    "title": "",
    "url": "",
    "publisher": "",
    "source_type": "",
    "publication_or_update_date": null,
    "identifiers": {}
  },
  "study_design": "",
  "evidence_level": "",
  "population": {
    "tumor_types": [],
    "histologies": [],
    "disease_setting": [],
    "stage": [],
    "prior_therapy": [],
    "sample_size": null,
    "age_requirements": [],
    "performance_status_requirements": [],
    "other_key_criteria": []
  },
  "biomarker_definition": {
    "markers": [],
    "required_alterations": [],
    "excluded_alterations": [],
    "assay_requirements": [],
    "thresholds": [],
    "confirmation_methods": []
  },
  "interventions": [],
  "comparators": [],
  "mechanism_claims": [],
  "outcomes": {
    "response": [],
    "pfs": [],
    "os": [],
    "duration_of_response": [],
    "pharmacodynamic": [],
    "toxicity": []
  },
  "trial": {
    "status": null,
    "phase": null,
    "locations": [],
    "last_update": null
  },
  "resistance_findings": [],
  "monitoring_findings": [],
  "authors_limitations": [],
  "facts_not_reported": [],
  "support_spans": [
    {
      "claim": "",
      "source_location": "",
      "text_excerpt": ""
    }
  ]
}
```

## Output

```text
$.source_extractions.<source_id>
```

---

# 10. Prompt 5 — Patient-to-source fit assessment

This output can directly populate the URL appendix.

## Variables

```text
{{patient_hypothesis}} = $.hypotheses[
    hypothesis_id == source.hypothesis_id
]
{{patient_context}}    = $.input.case
{{patient_findings}}   = relevant items from $.input.actionable_findings
{{source_extraction}}  = $.source_extractions.<source_id>
```

## Prompt

```text
SYSTEM

You are a precision-oncology evidence-fit assessor.

Compare one patient-specific hypothesis with one extracted source.

Keep these dimensions separate:

- molecular fit;
- disease and population fit;
- evidence maturity;
- standard-care readiness;
- clinical-trial screening value.

A mechanism paper cannot establish patient benefit.
A trial record cannot establish response.
A news report cannot outrank its underlying primary source.
A strong molecular match must not automatically become a strong treatment
recommendation.
Missing patient fields must remain unknown.

USER

PATIENT CONTEXT:
{{patient_context}}

PATIENT HYPOTHESIS:
{{patient_hypothesis}}

RELEVANT PATIENT FINDINGS:
{{patient_findings}}

SOURCE EXTRACTION:
{{source_extraction}}

Return JSON only:

{
  "source_id": "",
  "hypothesis_id": "",
  "appendix_title": "",
  "url": "",
  "source_type": "",
  "relevant_marker_or_pathway": [],
  "opening_assessment": "",
  "scores": {
    "molecular_fit": {
      "score": 0,
      "reason": ""
    },
    "population_fit": {
      "score": 0,
      "reason": ""
    },
    "evidence_maturity": {
      "score": 0,
      "reason": ""
    },
    "standard_care_readiness": {
      "score": 0,
      "reason": ""
    },
    "trial_screening_value": {
      "score": 0,
      "reason": ""
    }
  },
  "why_the_fit_is_strong": [],
  "matching_features": [],
  "mismatching_features": [],
  "unknown_alignment_fields": [],
  "what_would_make_the_patient_a_stronger_candidate": [],
  "what_weakens_the_case": [],
  "my_read_on_this_case": "",
  "clinical_framing_to_use": "",
  "prohibited_overstatement": "",
  "source_specific_follow_up": [],
  "source_specific_conclusion": "",
  "patient_evidence_ids": [],
  "external_support_claims": [],
  "confidence": "high|moderate|low"
}
```

## Output

```text
$.source_fit_assessments.<source_id>
```

---

# 11. Prompt 6 — Trial pre-screen

Run only when:

```text
source.source_type == "trial_record"
or source.identifiers.nct_id is not null
```

## Variables

```text
{{patient_data}} = {
    case: $.input.case,
    findings: relevant $.input.actionable_findings
}
{{trial_record}} = normalized official trial record
```

## Prompt

```text
SYSTEM

You are a clinical-trial pre-screening engine.

This is not a final eligibility determination.

For every criterion, assign one:

- MATCH
- POSSIBLE_MATCH
- MISMATCH
- UNKNOWN
- NOT_ASSESSABLE

Never infer:

- performance status;
- organ function;
- measurable disease;
- washout periods;
- prior-treatment history;
- biopsy feasibility;
- reproductive requirements;
- prohibited concomitant therapy.

USER

PATIENT DATA:
{{patient_data}}

CURRENT TRIAL RECORD:
{{trial_record}}

Return JSON only:

{
  "source_id": "",
  "nct_id": "",
  "trial_status": "",
  "last_update": null,
  "biomarker_match": {
    "status": "",
    "reason": ""
  },
  "tumor_type_match": {
    "status": "",
    "reason": ""
  },
  "disease_setting_match": {
    "status": "",
    "reason": ""
  },
  "criterion_assessment": [
    {
      "criterion": "",
      "assessment": "MATCH|POSSIBLE_MATCH|MISMATCH|UNKNOWN|NOT_ASSESSABLE",
      "patient_evidence": "",
      "reason": ""
    }
  ],
  "required_missing_data": [],
  "site_and_geography": [],
  "screening_priority": "high|medium|low|not_currently_actionable",
  "reason": "",
  "not_a_final_eligibility_determination": true
}
```

## Output

```text
$.trial_prescreens.<source_id>
```

---

# 12. Prompt 7 — Hypothesis-level synthesis

Run once per hypothesis after all its URLs have been analyzed.

## Variables

```text
{{patient_hypothesis}}     = $.hypotheses[i]
{{source_fit_assessments}} = all $.source_fit_assessments where hypothesis_id matches
{{trial_prescreens}}       = matching $.trial_prescreens
{{technical_limitations}}  = $.input.technical_limitations
{{internal_context}}       = $.input.existing_context
```

## Prompt

```text
SYSTEM

You are a precision-oncology evidence synthesizer.

Synthesize all evaluated sources for one patient-specific biological
hypothesis.

Weight evidence in this order:

1. regulatory or guideline evidence;
2. prospective human clinical trials;
3. other human clinical evidence;
4. disease-matched translational evidence;
5. mechanistic or preclinical evidence;
6. expert commentary or medical news.

Do not count duplicate sources as independent confirmation.
Do not convert mechanism into efficacy.
Explicitly identify missing population alignment.
Clearly separate standard care, off-label rationale, and investigational
options.
Resistance without direct evidence must be labeled hypothesis-generating.

USER

PATIENT HYPOTHESIS:
{{patient_hypothesis}}

SOURCE FIT ASSESSMENTS:
{{source_fit_assessments}}

TRIAL PRE-SCREENS:
{{trial_prescreens}}

TECHNICAL LIMITATIONS:
{{technical_limitations}}

OPTIONAL INTERNAL CONTEXT:
{{internal_context}}

Return JSON only:

{
  "hypothesis_id": "",
  "hypothesis_status": "supported|partially_supported|uncertain|not_supported|technical_only",
  "executive_summary_statement": "",
  "validated_biology": [],
  "cause_effect_chain": [
    {
      "step": 1,
      "statement": "",
      "evidence_type": "",
      "patient_evidence_ids": [],
      "source_ids": []
    }
  ],
  "plain_english_explanation": "",
  "therapy_opportunities": [
    {
      "therapy_class": "",
      "example_agents": [],
      "molecular_interaction": "",
      "clinical_use": "standard|off_label|investigational|biologic_rationale_only|unsupported",
      "population_fit": "",
      "evidence_level": "",
      "key_caveats": [],
      "source_ids": []
    }
  ],
  "confirmatory_tests": [
    {
      "test": "",
      "why_it_matters": "",
      "priority": "high|medium|low",
      "source_ids": []
    }
  ],
  "resistance_and_escape": [
    {
      "escape_route": "",
      "evidence_status": "observed|reported|mechanistically_plausible|speculative",
      "description": "",
      "biomarkers_to_monitor": [],
      "source_ids": []
    }
  ],
  "monitoring_implications": [],
  "active_trial_leads": [],
  "unsupported_or_overstated_options": [],
  "population_alignment": {
    "matching": [],
    "mismatching": [],
    "unknown": []
  },
  "limitations": [],
  "confidence": "high|moderate|low",
  "report_claims": [
    {
      "claim_id": "",
      "claim": "",
      "patient_evidence_ids": [],
      "external_source_ids": [],
      "allowed_strength": ""
    }
  ]
}
```

## Output

```text
$.hypothesis_syntheses.<hypothesis_id>
```

---

# 13. Prompt 8 — Final report compiler

The compiler writes the main seven-page report and prepares the appendix index. It does not re-analyze sources.

## Variables

```text
{{case_summary}}          = $.input.case
{{primary_findings}}      = $.input.actionable_findings
{{secondary_findings}}    = $.input.secondary_findings
{{hypothesis_syntheses}}  = values($.hypothesis_syntheses)
{{trial_prescreens}}      = values($.trial_prescreens)
{{technical_limitations}} = $.input.technical_limitations
{{negative_findings}}     = $.input.negative_findings
{{retesting_triggers}}    = $.input.existing_context.retesting_triggers
{{selected_sources}}      = selected metadata from $.sources
{{appendix_assessments}}  = values($.source_fit_assessments)
```

## Prompt

```text
SYSTEM

You are the final compiler for a precision-oncology actionable packet.

Use only the supplied validated artifacts.

Do not:

- search;
- introduce new therapies;
- introduce new mechanisms;
- introduce new trials;
- create new citations;
- convert investigational rationale into a treatment recommendation;
- hide unresolved population mismatch;
- interpret a technical non-call as a negative result.

Every substantive statement must include patient evidence IDs and/or external
source IDs.

The report is educational decision support and not a substitute for physician
judgment.

USER

CASE SUMMARY:
{{case_summary}}

PRIMARY FINDINGS:
{{primary_findings}}

SECONDARY FINDINGS:
{{secondary_findings}}

HYPOTHESIS SYNTHESES:
{{hypothesis_syntheses}}

TRIAL PRE-SCREENS:
{{trial_prescreens}}

TECHNICAL LIMITATIONS:
{{technical_limitations}}

NEGATIVE FINDINGS:
{{negative_findings}}

RETESTING TRIGGERS:
{{retesting_triggers}}

SELECTED SOURCES:
{{selected_sources}}

APPENDIX SOURCE ASSESSMENTS:
{{appendix_assessments}}

Return JSON only:

{
  "cover_metadata": {
    "title": "Precision Oncology Actionable Packet",
    "subtitle": "Professional summary for clinicians and patients",
    "purpose_statements": [],
    "source_label": "",
    "report_type": "",
    "disease_or_tumor_type": "",
    "specimen_context": "",
    "overall_validation_status": "",
    "important_note": ""
  },
  "executive_summary": {
    "paragraphs": [
      {
        "text": "",
        "patient_evidence_ids": [],
        "source_ids": []
      }
    ],
    "top_takeaway": "",
    "most_trial_relevant_finding": "",
    "most_likely_to_require_confirmation": "",
    "most_important_technical_caveat": ""
  },
  "key_findings": [
    {
      "marker_or_finding": "",
      "reasoning_domain": "",
      "what_it_means": "",
      "why_it_matters": "",
      "actionability": "",
      "next_step": "",
      "patient_evidence_ids": [],
      "source_ids": []
    }
  ],
  "other_findings": [
    {
      "finding": "",
      "interpretation": "",
      "patient_evidence_ids": [],
      "source_ids": []
    }
  ],
  "cause_effect": [
    {
      "finding": "",
      "mechanism_chain": "",
      "plain_english": "",
      "patient_evidence_ids": [],
      "source_ids": []
    }
  ],
  "therapy_options": [
    {
      "marker_or_target": "",
      "therapy_class": "",
      "example_agents": [],
      "molecular_interaction": "",
      "key_caveats": [],
      "status": "",
      "patient_evidence_ids": [],
      "source_ids": []
    }
  ],
  "practical_readout": [],
  "resistance_escape": [
    {
      "therapy_or_pathway": "",
      "escape_routes": [],
      "evidence_status": "",
      "monitoring_markers": [],
      "source_ids": []
    }
  ],
  "follow_up_tests": [
    {
      "recommended_next_step": "",
      "why_it_matters": "",
      "priority": "",
      "patient_evidence_ids": [],
      "source_ids": []
    }
  ],
  "phenotypic_events": [
    {
      "clinical_event": "",
      "why_it_matters": "",
      "urgency": "high|medium|low",
      "recommended_test": ""
    }
  ],
  "limitations": [],
  "selected_links": [
    {
      "source_id": "",
      "title": "",
      "url": "",
      "why_it_is_useful": "",
      "source_type": "",
      "hypothesis_id": ""
    }
  ],
  "bottom_line": [],
  "url_fit_appendix": {
    "data_basis_and_rules": [],
    "scoring_guide": "",
    "source_index": [],
    "source_assessment_ids": [],
    "cross_source_synthesis_placeholder": true
  }
}
```

## Output

```text
$.report
```

---

# 14. Cross-source synthesis

You can derive this directly from `hypothesis_syntheses`, but a small final synthesis prompt is useful when several hypotheses overlap.

## Variables

```text
{{hypothesis_syntheses}} = values($.hypothesis_syntheses)
{{source_assessments}}   = values($.source_fit_assessments)
```

## Prompt

```text
SYSTEM

Produce a concise cross-source synthesis.

Do not introduce new facts.
Do not count duplicate sources twice.
Rank themes by clinical significance and evidence maturity.
Separate trial-screening value from standard-care readiness.

USER

HYPOTHESIS SYNTHESES:
{{hypothesis_syntheses}}

SOURCE ASSESSMENTS:
{{source_assessments}}

Return JSON only:

{
  "summary": "",
  "themes": [
    {
      "theme": "",
      "cross_source_conclusion": "",
      "evidence_maturity": "",
      "clinical_role": ""
    }
  ],
  "practical_bottom_line": [],
  "source_ids": []
}
```

Store at:

```text
$.report.url_fit_appendix.cross_source_synthesis
```

---

# 15. Prompt-variable mapping matrix

| Template variable            | Runtime JSONPath                                        |
| ---------------------------- | ------------------------------------------------------- |
| `{{case_context}}`           | `$.input.case`                                          |
| `{{case_summary}}`           | `$.input.case`                                          |
| `{{actionable_findings}}`    | `$.input.actionable_findings`                           |
| `{{primary_findings}}`       | `$.input.actionable_findings`                           |
| `{{secondary_findings}}`     | `$.input.secondary_findings`                            |
| `{{technical_limitations}}`  | `$.input.technical_limitations`                         |
| `{{negative_findings}}`      | `$.input.negative_findings`                             |
| `{{internal_hints}}`         | `$.input.existing_context`                              |
| `{{internal_context}}`       | `$.input.existing_context`                              |
| `{{hypotheses}}`             | `$.hypotheses`                                          |
| `{{patient_hypothesis}}`     | `$.hypotheses[?(@.hypothesis_id=="<id>")]`              |
| `{{missing_context}}`        | code-derived from `$.input.case` and findings           |
| `{{research_job}}`           | `$.research_jobs[i]`                                    |
| `{{minimal_patient_anchor}}` | code-derived from relevant case + hypothesis + findings |
| `{{retrieved_source}}`       | `$.sources.<source_id>.retrieved_content`               |
| `{{source_metadata}}`        | `$.sources.<source_id>`                                 |
| `{{source_extraction}}`      | `$.source_extractions.<source_id>`                      |
| `{{patient_findings}}`       | relevant subset of `$.input.actionable_findings`        |
| `{{patient_data}}`           | `{"case": $.input.case, "findings": [...]}`             |
| `{{trial_record}}`           | `$.sources.<source_id>.normalized_trial_record`         |
| `{{source_fit_assessments}}` | matching values from `$.source_fit_assessments`         |
| `{{trial_prescreens}}`       | matching values from `$.trial_prescreens`               |
| `{{hypothesis_syntheses}}`   | `values($.hypothesis_syntheses)`                        |
| `{{retesting_triggers}}`     | `$.input.existing_context.retesting_triggers`           |
| `{{selected_sources}}`       | selected metadata from `$.sources`                      |
| `{{appendix_assessments}}`   | `values($.source_fit_assessments)`                      |

---

# 16. PDF section mappings

| PDF section              | Render from                                        |
| ------------------------ | -------------------------------------------------- |
| Cover information        | `$.report.cover_metadata`                          |
| Executive Summary        | `$.report.executive_summary`                       |
| Key Findings             | `$.report.key_findings`                            |
| Other Findings           | `$.report.other_findings`                          |
| Cause and Effect         | `$.report.cause_effect`                            |
| Therapy Options          | `$.report.therapy_options`                         |
| Practical Readout        | `$.report.practical_readout`                       |
| Resistance and Escape    | `$.report.resistance_escape`                       |
| Follow-up Tests          | `$.report.follow_up_tests`                         |
| Future Phenotypic Events | `$.report.phenotypic_events`                       |
| Limitations              | `$.report.limitations`                             |
| Selected Links           | `$.report.selected_links`                          |
| Appendix Index           | `$.report.url_fit_appendix.source_index`           |
| Each URL assessment      | `$.source_fit_assessments.<source_id>`             |
| Trial eligibility detail | `$.trial_prescreens.<source_id>`                   |
| Cross-source synthesis   | `$.report.url_fit_appendix.cross_source_synthesis` |
| URLs assessed            | selected entries in `$.sources`                    |

No additional LLM call should be necessary for rendering an appendix entry. The fit-assessment JSON already contains all headings and text blocks.

---

# 17. Python adapter

```python
from __future__ import annotations

import re
from collections.abc import Iterable
from typing import Any


def first_nonempty(*values: Any) -> Any:
    for value in values:
        if value not in (None, "", [], {}):
            return value
    return None


def chunks_by_type(raw: dict[str, Any], chunk_type: str) -> list[dict[str, Any]]:
    return [
        chunk
        for chunk in raw.get("chunks", [])
        if chunk.get("chunk_type") == chunk_type
    ]


def chunks_by_id(raw: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        chunk["chunk_id"]: chunk
        for chunk in raw.get("chunks", [])
        if chunk.get("chunk_id")
    }


def extract_nct_ids(texts: Iterable[str]) -> list[str]:
    ids: set[str] = set()

    for text in texts:
        ids.update(
            match.upper()
            for match in re.findall(r"\bNCT\d{8}\b", text or "", flags=re.I)
        )

    return sorted(ids)


def build_actionable_input(
    raw: dict[str, Any],
    actionable_findings: list[dict[str, Any]],
    secondary_findings: list[dict[str, Any]] | None = None,
    technical_findings: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """
    Build the compact input used by all downstream prompts.

    `actionable_findings`, `secondary_findings`, and `technical_findings`
    are assumed to have already passed your existing filtering logic.
    """
    bundle = raw.get("bundle", {})
    extraction = bundle.get("extraction", {})
    decision_brief = bundle.get("decision_brief", {})
    evidence_context = bundle.get("evidence_context", {})
    confirmatory = bundle.get("confirmatory", {})

    metadata_chunks = chunks_by_type(raw, "case_metadata")
    metadata_texts = [
        chunk.get("source_text", "")
        for chunk in metadata_chunks
    ]

    clinical_trial_chunks = chunks_by_type(raw, "clinical_trial_context")
    existing_trial_ids = extract_nct_ids(
        chunk.get("source_text", "")
        for chunk in clinical_trial_chunks
    )

    # Keep raw metadata snippets available to your own parser.
    metadata_fallback = {
        "source_texts": metadata_texts,
        "source_chunk_ids": [
            chunk.get("chunk_id")
            for chunk in metadata_chunks
            if chunk.get("chunk_id")
        ],
    }

    technical_limitations = [
        {
            "limitation_id": f"assay_{index}",
            "label": "Assay limitation",
            "description": limitation,
            "source_page": None,
            "source_chunk_id": None,
            "clinical_effect": "Preserve this limitation in interpretation.",
        }
        for index, limitation in enumerate(
            extraction.get("assay_limitations", []),
            start=1,
        )
    ]

    for item in technical_findings or []:
        technical_limitations.append(item)

    return {
        "case": {
            "case_id": raw.get("case_id") or bundle.get("case_id"),
            "session_id": raw.get("session_id") or bundle.get("session_id"),
            "source_file_id": raw.get("source_file_id"),
            "report_type": extraction.get("report_type"),
            "disease": {
                "name": extraction.get("disease"),
                "stage": None,
                "setting": None,
            },
            "specimen": {
                "site": extraction.get("specimen"),
                "collection_date": None,
                "tumor_percentage": extraction.get("tumor_percentage"),
            },
            "prior_therapies": [],
            "line_of_therapy": None,
            "performance_status": None,
            "organ_function": None,
            "measurable_disease": None,
            "biopsy_feasibility": None,
            "location": None,
            "validation_status": decision_brief.get("validation_status"),
            "metadata_fallback": metadata_fallback,
        },
        "actionable_findings": actionable_findings,
        "secondary_findings": secondary_findings or [],
        "technical_limitations": technical_limitations,
        "negative_findings": extraction.get("negative_findings", []),
        "existing_trial_mentions": existing_trial_ids,
        "existing_context": {
            "phenotype_axes": bundle.get("phenotype", {}).get("axes", []),
            "treatment_matrix": bundle.get("matrix", {}).get("rows", []),
            "confirmatory_tests": confirmatory.get("tests", []),
            "must_not_assume": confirmatory.get("must_not_assume", []),
            "tumor_behavior": bundle.get("tumor_behavior", {}),
            "ranked_treatment_hints": decision_brief.get(
                "ranked_treatment_options", []
            ),
            "treatment_pressure_hints": decision_brief.get(
                "treatment_pressure_map", []
            ),
            "resistance_hints": decision_brief.get(
                "resistance_forecast", []
            ),
            "biomarker_watch_hints": decision_brief.get(
                "biomarker_watch_list", []
            ),
            "retesting_triggers": decision_brief.get(
                "retesting_triggers", []
            ),
            "next_test_hints": decision_brief.get(
                "next_test_recommendations", []
            ),
            "evidence_limitations": decision_brief.get(
                "evidence_limitations", []
            ),
            "missing_evidence": evidence_context.get(
                "missing_evidence", []
            ),
            "conflicting_evidence": evidence_context.get(
                "conflicting_evidence", []
            ),
            "reasoning_warnings": evidence_context.get(
                "medea_reasoning", {}
            ).get("warnings", []),
        },
        "provenance": {
            "evidence_sentences": decision_brief.get(
                "evidence_sentence_map", []
            ),
            "claims": bundle.get("claims", []),
            "artifact_records": bundle.get("provenance", []),
        },
    }
```

---

# 18. Prompt-variable builder functions

```python
from typing import Any


def missing_case_context(case: dict[str, Any]) -> list[str]:
    checks = {
        "disease.name": case.get("disease", {}).get("name"),
        "disease.stage": case.get("disease", {}).get("stage"),
        "disease.setting": case.get("disease", {}).get("setting"),
        "prior_therapies": case.get("prior_therapies"),
        "line_of_therapy": case.get("line_of_therapy"),
        "performance_status": case.get("performance_status"),
        "organ_function": case.get("organ_function"),
        "measurable_disease": case.get("measurable_disease"),
        "biopsy_feasibility": case.get("biopsy_feasibility"),
        "location": case.get("location"),
    }

    return [
        key
        for key, value in checks.items()
        if value in (None, "", [], {})
    ]


def hypothesis_prompt_vars(state: dict[str, Any]) -> dict[str, Any]:
    return {
        "case_context": state["input"]["case"],
        "actionable_findings": state["input"]["actionable_findings"],
        "secondary_findings": state["input"]["secondary_findings"],
        "technical_limitations": state["input"]["technical_limitations"],
        "internal_hints": state["input"]["existing_context"],
    }


def research_plan_prompt_vars(state: dict[str, Any]) -> dict[str, Any]:
    missing = missing_case_context(state["input"]["case"])

    for finding in state["input"]["actionable_findings"]:
        missing.extend(finding.get("missing_validation", []))

    return {
        "case_context": state["input"]["case"],
        "hypotheses": state["hypotheses"],
        "missing_context": sorted(set(missing)),
    }


def relevant_findings(
    state: dict[str, Any],
    hypothesis: dict[str, Any],
) -> list[dict[str, Any]]:
    ids = set(hypothesis.get("primary_finding_ids", []))
    ids.update(hypothesis.get("supporting_finding_ids", []))

    all_findings = (
        state["input"]["actionable_findings"]
        + state["input"]["secondary_findings"]
    )

    return [
        finding
        for finding in all_findings
        if finding.get("finding_id") in ids
    ]


def source_fit_prompt_vars(
    state: dict[str, Any],
    source_id: str,
) -> dict[str, Any]:
    source = state["sources"][source_id]
    hypothesis_id = source["hypothesis_id"]

    hypothesis = next(
        item
        for item in state["hypotheses"]
        if item["hypothesis_id"] == hypothesis_id
    )

    return {
        "patient_context": state["input"]["case"],
        "patient_hypothesis": hypothesis,
        "patient_findings": relevant_findings(state, hypothesis),
        "source_extraction": state["source_extractions"][source_id],
    }
```

---

# 19. Orchestration skeleton

```python
import asyncio
from typing import Any


async def build_precision_oncology_packet(
    raw_json: dict[str, Any],
    actionable_findings: list[dict[str, Any]],
    model_client: Any,
    web_client: Any,
    renderer: Any,
) -> bytes:
    state: dict[str, Any] = {
        "input": build_actionable_input(
            raw_json,
            actionable_findings=actionable_findings,
        ),
        "hypotheses": [],
        "research_jobs": [],
        "sources": {},
        "source_extractions": {},
        "source_fit_assessments": {},
        "trial_prescreens": {},
        "hypothesis_syntheses": {},
        "report": {},
        "validation": {},
        "render": {},
    }

    # 1. Build hypotheses.
    hypothesis_result = await model_client.json_call(
        prompt_name="hypothesis_builder_v1",
        variables=hypothesis_prompt_vars(state),
        response_schema="HypothesisBuilderOutput",
    )
    state["hypotheses"] = hypothesis_result["hypotheses"]

    # 2. Plan research.
    plan_result = await model_client.json_call(
        prompt_name="research_planner_v1",
        variables=research_plan_prompt_vars(state),
        response_schema="ResearchPlanOutput",
    )
    state["research_jobs"] = plan_result["research_jobs"]

    # 3. Discover sources in parallel.
    discovery_results = await asyncio.gather(
        *[
            web_client.discover_sources(
                research_job=job,
                patient_anchor=build_minimal_patient_anchor(state, job),
            )
            for job in state["research_jobs"]
        ]
    )

    state["sources"] = deduplicate_and_rank_sources(discovery_results)

    selected_source_ids = select_sources_for_analysis(state["sources"])

    # 4. Fetch and extract selected sources in parallel.
    source_contents = await asyncio.gather(
        *[
            web_client.fetch_source(state["sources"][source_id])
            for source_id in selected_source_ids
        ]
    )

    for source_id, content in zip(
        selected_source_ids,
        source_contents,
        strict=True,
    ):
        state["sources"][source_id]["retrieved_content"] = content

    extraction_results = await asyncio.gather(
        *[
            model_client.json_call(
                prompt_name="source_extractor_v1",
                variables={
                    "source_metadata": state["sources"][source_id],
                    "retrieved_source": state["sources"][source_id][
                        "retrieved_content"
                    ],
                },
                response_schema="SourceExtraction",
            )
            for source_id in selected_source_ids
        ]
    )

    for source_id, result in zip(
        selected_source_ids,
        extraction_results,
        strict=True,
    ):
        state["source_extractions"][source_id] = result

    # 5. Patient-source fit in parallel.
    fit_results = await asyncio.gather(
        *[
            model_client.json_call(
                prompt_name="patient_source_fit_v1",
                variables=source_fit_prompt_vars(state, source_id),
                response_schema="SourceFitAssessment",
            )
            for source_id in selected_source_ids
        ]
    )

    for source_id, result in zip(
        selected_source_ids,
        fit_results,
        strict=True,
    ):
        state["source_fit_assessments"][source_id] = result

    # 6. Trial pre-screen in parallel.
    trial_ids = [
        source_id
        for source_id in selected_source_ids
        if is_trial_source(state["sources"][source_id])
    ]

    trial_results = await asyncio.gather(
        *[
            model_client.json_call(
                prompt_name="trial_prescreen_v1",
                variables=trial_prescreen_vars(state, source_id),
                response_schema="TrialPrescreen",
            )
            for source_id in trial_ids
        ]
    )

    for source_id, result in zip(trial_ids, trial_results, strict=True):
        state["trial_prescreens"][source_id] = result

    # 7. Synthesize each hypothesis in parallel.
    synthesis_results = await asyncio.gather(
        *[
            model_client.json_call(
                prompt_name="hypothesis_synthesis_v1",
                variables=hypothesis_synthesis_vars(
                    state,
                    hypothesis["hypothesis_id"],
                ),
                response_schema="HypothesisSynthesis",
            )
            for hypothesis in state["hypotheses"]
        ]
    )

    for hypothesis, result in zip(
        state["hypotheses"],
        synthesis_results,
        strict=True,
    ):
        state["hypothesis_syntheses"][
            hypothesis["hypothesis_id"]
        ] = result

    # 8. Compile report.
    state["report"] = await model_client.json_call(
        prompt_name="report_compiler_v1",
        variables=report_compiler_vars(state),
        response_schema="PrecisionOncologyReport",
    )

    # 9. Cross-source synthesis.
    state["report"]["url_fit_appendix"][
        "cross_source_synthesis"
    ] = await model_client.json_call(
        prompt_name="cross_source_synthesis_v1",
        variables={
            "hypothesis_syntheses": list(
                state["hypothesis_syntheses"].values()
            ),
            "source_assessments": list(
                state["source_fit_assessments"].values()
            ),
        },
        response_schema="CrossSourceSynthesis",
    )

    # 10. Validate.
    state["validation"] = await run_all_validators(
        model_client=model_client,
        state=state,
    )

    apply_validation_corrections(state)

    # 11. Render with no new clinical reasoning.
    return renderer.render_pdf(
        report=state["report"],
        source_assessments=state["source_fit_assessments"],
        trial_prescreens=state["trial_prescreens"],
    )
```

---

# 20. Final validators

Use three independent checks.

## Claim grounding

```text
SYSTEM

Verify every report claim against its listed patient evidence IDs and external
source IDs.

Return PASS, REVISE, or REMOVE for every claim.

Flag:
- unsupported causality;
- stronger wording than the evidence;
- missing citation IDs;
- a source that does not support the exact statement.
```

## Population alignment

```text
SYSTEM

Review every therapy and trial statement.

Verify:
- disease and histology;
- stage and disease setting;
- line of therapy;
- prior treatment;
- biomarker definition;
- assay threshold;
- performance status;
- organ function;
- trial status and location.

Missing data must remain UNKNOWN.
Trial existence must not be presented as eligibility.
```

## Clinical safety and contradiction review

```text
SYSTEM

Detect:

- VUS treated as pathogenic;
- expression-only signals treated as established drivers;
- technical non-calls treated as negative findings;
- pharmacogenomic findings treated as tumor drivers;
- mechanism treated as clinical efficacy;
- trial records treated as response evidence;
- closed or historical trials treated as current options;
- news articles used as sole support;
- contradictory DNA, RNA, or protein evidence;
- treatment recommendations stronger than the supplied evidence.
```

Only render when there are no unhandled `REMOVE` findings and no high-severity validation failures.

---

# 21. Practical implementation rules

Cache the stable system prompts and schemas. Run research jobs, source extraction, source fit, trial pre-screening, and hypothesis synthesis concurrently. Store all outputs by deterministic IDs. Validate every model response against JSON Schema, Pydantic, or Zod before advancing.

Use the LLM for:

```text
hypothesis formation
research planning
source extraction
patient-source comparison
evidence synthesis
clinical prose
```

Use code for:

```text
JSON selection
joining records
URL canonicalization
deduplication
source scoring
trial API retrieval
missing-field detection
schema validation
citation indexing
pagination
table layout
PDF rendering
```

The most important integration boundary is:

```text
raw Translume JSON
    → your actionable plucker
    → canonical actionable input
    → prompt workflow
    → render-ready report JSON
    → deterministic PDF renderer
```

That separation makes the system reusable for arbitrary NGS reports while keeping the report format stable.
