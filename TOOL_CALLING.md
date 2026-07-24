You need **two classes of tool calling**:

1. **Local / air-gapped tools** that parse the Translume JSON, resolve evidence IDs, classify biomarkers, assemble report data, and render the PDF.
2. **Connected retrieval tools** that search the internet, fetch URLs, parse studies/trials/articles, and export a sanitized evidence bundle back into the air-gapped system.

OLMo3 7B should **not** be responsible for raw browsing, PDF layout, citation extraction, or clinical-trial parsing. It should receive structured JSON and produce schema-bound summaries.

---

# 1. Minimum tool-calling stack

```text
LOCAL / AIR-GAPPED
──────────────────
1. parse_translume_json
2. resolve_source_evidence
3. classify_findings
4. build_biomarker_axes
5. build_prompt_packets
6. score_patient_fit_from_structured_evidence
7. assemble_report_json
8. render_pdf


CONNECTED / INTERNET
────────────────────
9. web_search
10. fetch_url
11. parse_pubmed_pmc
12. parse_clinicaltrials
13. parse_general_webpage
14. dedupe_and_rank_sources
15. build_evidence_cards
16. export_evidence_bundle
```

The v2 PDF’s required output sections are already clear: executive summary, key findings, cause/effect biology, therapy options, resistance/escape routes, follow-up testing, future phenotypic events, limitations, and reference/trial links.  The JSON also already contains some of the primitives you want, including `treatment_pressure_map`, `likely_escape_routes`, `biomarkers_to_watch`, `preferred_test`, and `retesting_triggers`.  

---

# 2. Local tools: what runs inside the air-gapped system

## Tool 1 — `parse_translume_json`

Purpose: load the Translume JSON and extract all report primitives.

**Input**

```json
{
  "translume_review_packet": "{raw_json}"
}
```

**Output**

```json
{
  "case_metadata": {},
  "chunks": [],
  "molecular_findings": [],
  "decision_brief": {},
  "entities": [],
  "provenance": [],
  "medea_reasoning": {}
}
```

This tool should pull from these JSON keys:

```text
chunks[]
bundle.extraction.molecular_findings[]
bundle.entities.entities[]
bundle.decision_brief
bundle.confirmatory
bundle.narrative.markdown
bundle.medea_reasoning
```

---

## Tool 2 — `resolve_source_evidence`

Purpose: connect each finding back to its source text, page, chunk ID, and bbox.

**Input**

```json
{
  "finding": {
    "gene": "MTAP",
    "source_chunk_id": "chunk_8f414ef539e959a7"
  },
  "chunks": []
}
```

**Output**

```json
{
  "gene": "MTAP",
  "source_text": "MTAP encodes an enzyme involved...",
  "source_page": 3,
  "bbox": {},
  "source_chunk_id": "chunk_8f414ef539e959a7"
}
```

This matters because the report must be traceable. For example, the JSON source text for MTAP says MTAP is involved in polyamine metabolism and methionine/adenine regeneration, is often co-deleted with CDKN2, and that MTAP underexpression/copy-number loss is associated with cancer progression. 

---

## Tool 3 — `classify_findings`

Purpose: separate tumor biology, pharmacogenomics, technical limitations, VUS, and noise.

**Input**

```json
{
  "molecular_findings": []
}
```

**Output**

```json
{
  "tumor_biology_findings": [],
  "therapeutic_biomarkers": [],
  "pharmacogenomic_findings": [],
  "technical_limitations": [],
  "vus_or_uncertain": [],
  "noise_or_bad_entities": []
}
```

Classification rules:

```text
CHEK2 LOF → tumor biology / DDR therapeutic hypothesis
MTAP loss → tumor biology / synthetic-lethal trial hypothesis
CDKN2A loss → tumor suppressor / cell-cycle biology
TAF1 low coverage → technical limitation, not biological finding
TPMT → pharmacogenomics unless linked to cancer therapy in context
UNKNOWN / Accession / CLIA / physician names → noise
```

The report’s key-finding table already follows this logic: CHEK2 is treated as a DDR finding, MTAP as a PRMT5/MAT2A trial-relevant marker, CDKN2A as cell-cycle biology, and TAF1 as a technical limitation. 

---

## Tool 4 — `build_biomarker_axes`

Purpose: convert individual findings into actionable reasoning axes.

**Input**

```json
{
  "classified_findings": {}
}
```

**Output**

```json
{
  "axes": [
    {
      "axis_id": "axis_mtap_prmt5_mat2a",
      "primary_marker": "MTAP",
      "supporting_markers": ["CDKN2A", "CDKN2B"],
      "domain": "synthetic_lethality_metabolic_dependency",
      "therapy_classes": [
        "MTA-cooperative PRMT5 inhibitors",
        "MAT2A inhibitors",
        "PRMT5 + MAT2A combinations"
      ],
      "required_confirmations": [
        "MTAP IHC",
        "MTAP/CDKN2A/CDKN2B CNV review"
      ]
    }
  ]
}
```

For any NGS report, this is the move from **gene list** to **clinical reasoning domain**.

Examples:

```text
MTAP loss + CDKN2A loss
→ MTAP / PRMT5 / MAT2A axis

CHEK2 LOF
→ DDR / PARP / ATR / WEE1 / DNA-PK axis

CDKN2A loss
→ cell-cycle / CDK4-6 axis, but not standalone standard therapy

TAF1 low coverage
→ technical limitation axis
```

---

## Tool 5 — `extract_treatment_pressure`

Purpose: use `treatment_pressure_map[]` and `likely_escape_routes[]`.

**Input**

```json
{
  "decision_brief": {
    "treatment_pressure_map": []
  }
}
```

**Output**

```json
{
  "pressure_maps": [
    {
      "therapy_name_or_class": "approved_option",
      "target_or_pathway": "CHEK2",
      "why_it_fits": "Splice region variant-LOF in CHEK2",
      "selective_pressure": "CHEK2",
      "likely_escape_routes": [
        "Rescue mechanisms involving alternative splicing pathways",
        "Reversion mutations in other DNA repair genes"
      ],
      "biomarkers_to_watch": ["TPMT", "HLA-C", "RPS15", "MTAP"],
      "confidence": "high"
    }
  ]
}
```

This is the data source for the PDF section **Resistance and Escape Routes**. The v2 report already includes escape routes for DDR-oriented therapies, MTAP-directed therapies, and cell-cycle strategies. 

---

## Tool 6 — `extract_follow_up_tests`

Purpose: use `biomarker_watch_list[]`, especially `preferred_test`.

**Input**

```json
{
  "biomarker_watch_list": []
}
```

**Output**

```json
{
  "follow_up_tests": [
    {
      "biomarker": "MTAP",
      "preferred_test": "IHC",
      "why": "Confirms whether MTAP protein is actually lost."
    }
  ]
}
```

Your JSON has the exact primitive you want: `preferred_test: IHC` for MTAP-related follow-up. 

---

## Tool 7 — `extract_retesting_triggers`

Purpose: use `retesting_triggers[]` to populate **Future Phenotypic Events to Watch For**.

**Input**

```json
{
  "retesting_triggers": []
}
```

**Output**

```json
{
  "future_phenotypic_events": [
    {
      "clinical_event": "radiographic progression",
      "recommended_test": "IHC",
      "rationale": "Radiographic progression may indicate need for biomarker re-evaluation.",
      "what_result_changes": "Could change treatment strategy.",
      "urgency": "high"
    }
  ]
}
```

The v2 PDF has this exact section already, with radiographic progression, mixed response, rapid progression, rising tumor markers, new metastasis, and suspected transformation as triggers. 

---

## Tool 8 — `assemble_report_json`

Purpose: combine everything into a renderer-ready object.

**Output shape**

```json
{
  "report_title": "Precision Oncology Actionable Packet",
  "executive_summary": {},
  "key_findings": [],
  "cause_effect": [],
  "therapy_options": [],
  "resistance_escape_routes": [],
  "follow_up_tests": [],
  "future_phenotypic_events": [],
  "limitations": [],
  "reference_links": [],
  "url_fit_assessments": [],
  "cross_source_synthesis": {}
}
```

---

# 3. Internet tools: what runs outside the air gap

The connected side should produce **evidence cards**, not prose.

## Tool 9 — `search_web`

Purpose: find relevant URLs from the biomarker axes.

This can use DuckDuckGo, Brave Search, Bing, SerpAPI, or any internal search proxy. DuckDuckGo can work as a free search layer, but you should treat it as a discovery tool, not a source of truth.

**Input**

```json
{
  "query": "MTAP deleted solid tumors PRMT5 MAT2A inhibitor clinical trial",
  "max_results": 10,
  "preferred_domains": [
    "clinicaltrials.gov",
    "pmc.ncbi.nlm.nih.gov",
    "pubmed.ncbi.nlm.nih.gov",
    "nature.com",
    "sciencedirect.com"
  ]
}
```

**Output**

```json
{
  "results": [
    {
      "title": "...",
      "url": "...",
      "snippet": "...",
      "domain": "...",
      "rank": 1
    }
  ]
}
```

Search-query templates:

```text
{gene} {alteration} cancer targeted therapy
{gene} loss clinical trial solid tumor
{gene} deletion synthetic lethality inhibitor
{pathway} inhibitor {gene} loss
{drug_class} {biomarker} clinical trial
{gene} {cancer_type} PubMed
{gene} ClinicalTrials.gov
```

For this case:

```text
MTAP deleted solid tumors PRMT5 inhibitor
MTAP MAT2A inhibitor clinical trial
MTAP CDKN2A co-deletion synthetic lethality
CHEK2 loss of function PARP inhibitor evidence
CHEK2 ATR inhibitor clinical trial
DDR targeted therapeutics CHEK2
```

---

## Tool 10 — `parse_clinicaltrials`

Purpose: parse NCT records into structured trial evidence.

Use the official ClinicalTrials.gov API, especially the v2 API. ClinicalTrials.gov documents its data API and exposes a v2 OpenAPI specification; the migration guide identifies `/api/v2/studies` as the newer studies endpoint. ([ClinicalTrials.gov][1])

**Input**

```json
{
  "nct_id": "NCT05245500"
}
```

**Output**

```json
{
  "url": "https://clinicaltrials.gov/study/NCT05245500",
  "title": "",
  "nct_id": "NCT05245500",
  "source_type": "clinical_trial",
  "phase": "",
  "status": "",
  "conditions": [],
  "interventions": [],
  "biomarkers_required": [],
  "inclusion_criteria_summary": [],
  "exclusion_criteria_summary": [],
  "locations": [],
  "sponsor": "",
  "trial_relevance": ""
}
```

This tool is required for every ClinicalTrials.gov URL because trial status, eligibility, phase, and cohort status can change.

---

## Tool 11 — `parse_pubmed_pmc`

Purpose: parse PubMed/PMC articles into mechanism/clinical evidence cards.

Use NCBI E-utilities. NCBI describes E-utilities as server-side programs that provide a stable interface into Entrez databases, including PubMed and PMC. ([NCBI][2])

**Input**

```json
{
  "url_or_pmid_or_pmcid": "https://pmc.ncbi.nlm.nih.gov/articles/PMC11726016/"
}
```

**Output**

```json
{
  "url": "",
  "title": "",
  "pmid": "",
  "pmcid": "",
  "doi": "",
  "source_type": "peer_reviewed_article",
  "article_type": "mechanistic / clinical / review / preclinical",
  "abstract": "",
  "key_claims": [],
  "drug_names": [],
  "biomarkers": [],
  "tumor_types": [],
  "clinical_outcomes": [],
  "limitations": [],
  "evidence_weight": ""
}
```

For open-access full text, Europe PMC is also useful because its REST service provides access to publication data and related information in Europe PMC. ([Europe PMC][3])

---

## Tool 12 — `parse_crossref_metadata`

Purpose: resolve DOI, title, journal, date, authors, and publication metadata.

Crossref’s REST API exposes bibliographic metadata, abstracts, funder data, license information, ORCID/ROR IDs, and related metadata in JSON. ([www.crossref.org][4])

**Input**

```json
{
  "doi": "10.1021/acs.jmedchem.4c00133"
}
```

**Output**

```json
{
  "doi": "",
  "title": "",
  "journal": "",
  "published_date": "",
  "authors": [],
  "abstract": "",
  "publisher": "",
  "license": "",
  "url": ""
}
```

Use this when PubMed/PMC does not have the source but the article has a DOI.

---

## Tool 13 — `parse_general_webpage`

Purpose: parse company pages, news pages, Panome-style explainers, cancer-center pages, and trial landing pages.

**Input**

```json
{
  "url": "https://panomebio.com/blog/metabolomic-logic-behind-mat2a-prmt5-combinations/"
}
```

**Output**

```json
{
  "url": "",
  "title": "",
  "source_type": "company_page / news / blog / cancer_center / unknown",
  "publisher": "",
  "published_date": "",
  "main_text": "",
  "key_claims": [],
  "drug_names": [],
  "pathways": [],
  "biomarkers": [],
  "evidence_limitations": [],
  "sponsor_bias_warning": true
}
```

Important: for company/blog/news pages, evidence weight should be lower than peer-reviewed clinical papers or ClinicalTrials.gov records.

---

## Tool 14 — `build_evidence_card`

Purpose: normalize every parsed source into one schema.

```json
{
  "evidence_id": "evidence_url_001",
  "url": "",
  "title": "",
  "source_type": "",
  "evidence_weight": "peer_reviewed_clinical | peer_reviewed_preclinical | clinical_trial_record | review | company_pipeline | news | blog",
  "relevant_axis": "axis_mtap_prmt5_mat2a",
  "relevant_markers": ["MTAP", "CDKN2A"],
  "relevant_therapies": ["AMG 193"],
  "mechanism": "",
  "clinical_maturity": "standard_care | guideline_supported | phase3 | phase2 | phase1 | preclinical | mechanistic_only",
  "patient_fit_inputs": {
    "required_biomarker": ["MTAP deletion"],
    "patient_has_biomarker": true,
    "requires_confirmation": ["MTAP IHC"]
  },
  "key_claims": [],
  "limitations": [],
  "citations": []
}
```

This object is what you hand to OLMo.

---

# 4. OLMo sub-prompts

Use OLMo only after deterministic tools have reduced everything to clean JSON.

## Sub-prompt A — Case fact extraction

```text
SYSTEM:
You are a clinical molecular report structuring assistant.
You must return valid JSON only.
Do not make treatment recommendations.
Do not use outside knowledge.
Use only the provided Translume JSON fields.

USER:
Extract a CaseFactPack from this JSON.

Required output schema:
{
  "case_metadata": {},
  "primary_actionable_findings": [],
  "secondary_findings": [],
  "technical_limitations": [],
  "pharmacogenomic_findings": [],
  "assay_limitations": [],
  "source_evidence": [],
  "needs_human_review": []
}

Rules:
- Preserve source_page, source_text, source_chunk_id, confidence, and needs_human_review.
- Classify low coverage as technical limitation, not mutation.
- Classify TPMT as pharmacogenomic unless source text proves tumor relevance.
- Remove obvious noise such as accession numbers, CLIA numbers, physician names, and UNKNOWN genes.

INPUT_JSON:
{translume_json_excerpt}
```

---

## Sub-prompt B — Biomarker axis builder

```text
SYSTEM:
You group molecular findings into clinically meaningful reasoning axes.
Return valid JSON only.

USER:
Build biomarker axes from this CaseFactPack.

Output schema:
{
  "axes": [
    {
      "axis_id": "",
      "axis_name": "",
      "primary_marker": "",
      "supporting_markers": [],
      "domain": "",
      "patient_findings": [],
      "biologic_rationale": "",
      "therapy_classes_to_search": [],
      "confirmation_tests": [],
      "why_actionable_or_not": "",
      "confidence": ""
    }
  ]
}

Rules:
- Do not claim standard-care actionability unless explicitly supported.
- Separate therapeutic biomarkers from pharmacogenomics and technical limitations.
- Include MTAP/CDKN2A as a combined axis when both are present.
- Include CHEK2 as DDR axis if loss-of-function is present.
- Include TAF1 low coverage as a technical axis only.

CASE_FACT_PACK:
{case_fact_pack}
```

---

## Sub-prompt C — Search-plan generator

```text
SYSTEM:
You generate search tasks for a retrieval system.
Return valid JSON only.
Do not summarize evidence.

USER:
Create a RetrievalPlan for each biomarker axis.

Output schema:
{
  "search_tasks": [
    {
      "axis_id": "",
      "query": "",
      "intent": "",
      "preferred_domains": [],
      "source_priority": [],
      "max_results": 10
    }
  ],
  "direct_url_tasks": [],
  "clinical_trial_tasks": [],
  "pubmed_tasks": []
}

Rules:
- Search clinical trials, peer-reviewed literature, and mechanism reviews.
- Prefer primary sources: ClinicalTrials.gov, PubMed, PMC, Europe PMC, peer-reviewed journals.
- Include company/news/blog pages only as secondary evidence.
- For MTAP loss, search PRMT5/MAT2A terms.
- For CHEK2 LOF, search DDR/PARP/ATR/WEE1/DNA-PK terms.

BIOMARKER_AXES:
{axes}
```

---

## Sub-prompt D — URL-specific candidate fit section

This produces the appendix section.

```text
SYSTEM:
You generate one URL-specific candidate-fit section for a precision oncology report.
Return valid JSON only.
Use patient-specific facts only from the CaseFactPack.
Use external claims only from EvidenceCard.
Separate biologic rationale from treatment readiness.
Do not claim that a therapy is standard care unless EvidenceCard says it is standard care.

USER:
Generate a UrlFitAssessment.

Output schema:
{
  "section_title": "",
  "url": "",
  "source_type": "",
  "role_in_packet": "",
  "opening_judgment": "",
  "bottom_line_score": [
    {
      "question": "",
      "strength": "",
      "why": ""
    }
  ],
  "why_fit_is_strong": [],
  "what_would_make_stronger_candidate": [],
  "what_weakens_case": [],
  "clinical_framing": {
    "do_not_say": [],
    "say_instead": []
  },
  "what_should_be_ordered_or_checked_next": [
    {
      "follow_up": "",
      "why": ""
    }
  ],
  "final_judgment": []
}

Required style:
- Match the PDF format.
- Include a bottom-line score table.
- Include "Why the fit is strong".
- Include "What would make him a strong candidate".
- Include "What weakens the case".
- Include "My read on this case".
- Include "What should have been ordered or checked next".
- Include "Final judgment".

CASE_FACT_PACK:
{case_fact_pack}

BIOMARKER_AXIS:
{axis}

EVIDENCE_CARD:
{evidence_card}
```

---

## Sub-prompt E — Cross-source synthesis

```text
SYSTEM:
You synthesize all URL-specific assessments into a concise cross-source conclusion.
Return valid JSON only.

USER:
Build the cross-source synthesis section.

Output schema:
{
  "cross_source_summary": "",
  "themes": [
    {
      "theme": "",
      "cross_source_conclusion": ""
    }
  ],
  "practical_bottom_line": []
}

Rules:
- Separate strongest actionable axis from secondary axes.
- Explicitly distinguish trial-screening strength from standard-care readiness.
- Mention confirmatory testing when needed.
- Preserve uncertainty about tumor type, stage, line of therapy, prior therapies, and eligibility.

URL_FIT_ASSESSMENTS:
{url_fit_assessments}
```

---

# 5. Tool-calling router

Here is the operational flow.

```python
def generate_precision_oncology_packet(translume_json, ngs_pdf=None):
    # Local
    parsed = parse_translume_json(translume_json)
    resolved = resolve_source_evidence(parsed)
    classified = classify_findings(resolved)

    # OLMo local prompt
    case_fact_pack = olmo_case_fact_prompt(classified)

    # OLMo local prompt
    axes = olmo_axis_builder_prompt(case_fact_pack)

    # OLMo local prompt
    retrieval_plan = olmo_search_plan_prompt(axes)

    # Connected sidecar
    raw_results = []
    for task in retrieval_plan["search_tasks"]:
        raw_results.extend(search_web(task))

    direct_urls = dedupe_urls(raw_results + retrieval_plan["direct_url_tasks"])

    evidence_cards = []
    for url in direct_urls:
        if "clinicaltrials.gov" in url:
            parsed_url = parse_clinicaltrials(url)
        elif "pubmed.ncbi.nlm.nih.gov" in url or "pmc.ncbi.nlm.nih.gov" in url:
            parsed_url = parse_pubmed_pmc(url)
        elif "doi.org" in url:
            parsed_url = parse_crossref_metadata(url)
        else:
            parsed_url = parse_general_webpage(url)

        evidence_cards.append(build_evidence_card(parsed_url, axes))

    # Air-gap export/import boundary
    evidence_bundle = export_evidence_bundle(evidence_cards)

    # OLMo local prompt per URL
    url_sections = []
    for card in evidence_bundle["evidence_cards"]:
        matching_axis = match_card_to_axis(card, axes)
        url_sections.append(
            olmo_url_fit_prompt(case_fact_pack, matching_axis, card)
        )

    # OLMo local prompt
    cross_source = olmo_cross_source_prompt(url_sections)

    # Local deterministic assembly
    report_json = assemble_report_json(
        case_fact_pack=case_fact_pack,
        axes=axes,
        url_fit_assessments=url_sections,
        cross_source_synthesis=cross_source
    )

    # Local deterministic rendering
    return render_pdf(report_json)
```

---

# 6. Evidence-ranking rules

Your tool layer should assign evidence weight before OLMo sees it.

```text
Highest weight
──────────────
1. FDA label / guideline / NCCN/ESMO where licensed
2. ClinicalTrials.gov active trial record
3. Peer-reviewed clinical trial paper
4. Peer-reviewed translational/mechanistic paper
5. Peer-reviewed review
6. Cancer-center trial page
7. Company press release / pipeline page
8. News article
9. Blog / explainer
10. Search-result snippet only
```

For each URL, store:

```json
{
  "evidence_weight": "clinical_trial_record",
  "clinical_maturity": "phase1",
  "bias_warning": "sponsor-generated" 
}
```

OLMo should never decide evidence maturity from prose alone; it should be given the maturity label.

---

# 7. What the connected retrieval side should search

For each biomarker axis:

## MTAP / PRMT5 / MAT2A

```text
MTAP deleted solid tumors PRMT5 inhibitor clinical trial
MTAP deletion MAT2A inhibitor IDE397 AG-270 S095033
MTA-cooperative PRMT5 inhibitor AMG 193 MRTX1719 TNG908 TNG462
MTAP CDKN2A co-deletion PRMT5 MAT2A synthetic lethality
MTAP deleted advanced solid tumors clinicaltrials.gov
```

## CHEK2 / DDR

```text
CHEK2 loss of function PARP inhibitor cancer
CHEK2 mutation DNA damage response ATR inhibitor
CHEK2 loss of function synthetic lethality DDR targeted therapy
PARP ATR WEE1 DNA-PK inhibitors DNA damage response review
CHEK2 clinical trial ATR PARP solid tumor
```

The DDR search should cover PARP, ATR/ATM, WEE1, and DNA-PK because the DDR notes you uploaded describe those classes and mechanisms. 

## CDKN2A / CDKN2B

```text
CDKN2A loss CDK4/6 inhibitor solid tumors
CDKN2A deletion cell cycle cancer trial
CDKN2A MTAP co-deletion 9p21 cancer
```

## AKT2 / PI3K-AKT

```text
AKT2 overexpression cancer PI3K AKT inhibitor
AKT2 amplification targeted therapy solid tumor
```

## Technical limitation

No broad therapy search needed.

```text
TAF1 low coverage NGS interpretation
low coverage gene sequencing clinical report interpretation
```

---

# 8. Final report sections generated from tools

Your final `ReportJSON` should render to the same PDF format:

```json
{
  "sections": [
    "Purpose of this packet",
    "Case metadata",
    "Executive Summary",
    "Key Findings at a Glance",
    "Other Findings Worth Noting",
    "Cause and Effect",
    "Therapy Options and Clinical Rationale",
    "Practical Readout",
    "Resistance and Escape Routes",
    "Follow-up Tests for Precision Oncology",
    "Future Phenotypic Events to Watch For",
    "Limitations and Confidence Boundaries",
    "Selected Reference and Trial Links",
    "URL-by-URL Candidate Fit Assessments",
    "Cross-Source Synthesis"
  ]
}
```

The report should include follow-up testing because the v2 PDF explicitly has a **Follow-up Tests for Precision Oncology** table, including MTAP IHC/CNV confirmation, CDKN2A/p16 review, CHEK2 clarification, repeat profiling, and TAF1 orthogonal testing only if clinically relevant. 

---

# 9. Key guardrails for OLMo3 7B

Use these as system rules for every medical prompt:

```text
1. Use only provided JSON and evidence cards.
2. Do not invent drugs, URLs, trial status, response rates, or approvals.
3. Separate:
   - biologic rationale
   - clinical trial readiness
   - standard-care readiness
4. Do not call a therapy standard of care unless evidence_card.clinical_maturity == "standard_care".
5. Treat low coverage as unknown biology, not normal biology.
6. Treat pharmacogenomics separately from tumor targeting.
7. Treat company/blog/news pages as lower-weight evidence.
8. Every claim must map to either:
   - patient_json_evidence_id
   - evidence_card_id
   - report limitation
9. If Medea timed out, use it only as a limitation.
10. Always output valid JSON.
```

The Medea result in your uploaded notes says literature reasoning was unavailable/unusable and downstream claims must remain `needs_review`; it also warns that DepMap evidence is exploratory and requires human review. 

---

# 10. The exact tool types you need

Here is the clean list.

| Tool type                     |   Required? | Runs where        | Purpose                                        |
| ----------------------------- | ----------: | ----------------- | ---------------------------------------------- |
| JSON parser                   |         Yes | Air-gapped        | Load Translume packet                          |
| Schema validator              |         Yes | Air-gapped        | Ensure required keys exist                     |
| Source evidence resolver      |         Yes | Air-gapped        | Join findings to chunks/pages/bboxes           |
| Finding classifier            |         Yes | Air-gapped        | Tumor biology vs PGx vs technical vs noise     |
| Biomarker-axis builder        |         Yes | Air-gapped / OLMo | Convert genes into pathway hypotheses          |
| Treatment-pressure extractor  |         Yes | Air-gapped        | Use `treatment_pressure_map` and escape routes |
| Follow-up test extractor      |         Yes | Air-gapped        | Use `preferred_test`, IHC/CNV, etc.            |
| Retesting-trigger extractor   |         Yes | Air-gapped        | Use `retesting_triggers[]`                     |
| Search-query generator        |         Yes | Air-gapped / OLMo | Build internet search plan                     |
| DuckDuckGo/web search         |         Yes | Connected         | Discover relevant URLs                         |
| PubMed/PMC parser             |         Yes | Connected         | Parse papers                                   |
| ClinicalTrials.gov parser     |         Yes | Connected         | Parse NCT status/criteria/phase                |
| DOI/Crossref parser           | Recommended | Connected         | Resolve metadata                               |
| Europe PMC parser             | Recommended | Connected         | Open-access full text / abstracts              |
| General webpage parser        |         Yes | Connected         | Company/news/blog/cancer-center pages          |
| Evidence-card normalizer      |         Yes | Connected         | Convert every URL into same JSON shape         |
| Evidence ranker               |         Yes | Connected/local   | Weight source types                            |
| URL-fit assessment prompt     |         Yes | Air-gapped / OLMo | Generate section per URL                       |
| Cross-source synthesis prompt |         Yes | Air-gapped / OLMo | Summarize all evidence                         |
| PDF renderer                  |         Yes | Air-gapped        | Generate final packet                          |

That is the full architecture. The most important implementation choice is this:

```text
Do not let OLMo browse and summarize raw URLs.

Instead:

URL → parser → EvidenceCard JSON → OLMo summary
```

That is what will make the output reproducible for **any NGS**, not just this case.

[1]: https://clinicaltrials.gov/data-api/api?utm_source=chatgpt.com "ClinicalTrials.gov API"
[2]: https://www.ncbi.nlm.nih.gov/books/NBK25501/?utm_source=chatgpt.com "Entrez® Programming Utilities Help - NCBI Bookshelf - NIH"
[3]: https://europepmc.org/RestfulWebService?utm_source=chatgpt.com "Articles RESTful API"
[4]: https://www.crossref.org/documentation/retrieve-metadata/rest-api/?utm_source=chatgpt.com "Documentation - Metadata Retrieval - REST API"
