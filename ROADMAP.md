# ROADMAP.md

# Translume Roadmap: From Single-Report Tumor-Behavior Compiler to Longitudinal Adaptive Precision Oncology Foundation

## Executive Summary

Translume should keep its current product exactly where it is strongest: one oncology molecular report becomes one source-backed, clinician-reviewable tumor-behavior intelligence packet. That single-report compiler is the trusted foundation. It extracts and normalizes report findings, connects them to mechanism and evidence, builds a decision brief, surfaces uncertainty, creates validation cards, preserves provenance, and avoids diagnosis, autonomous treatment recommendations, outcome prediction, or unsupported certainty.

The next product step is not to replace that workflow. The next step is to add an adaptive case layer above it. Each report remains an atomic, auditable clinical artifact. The adaptive layer links multiple report packets to a single patient or case timeline, then adds therapy exposure, response and progression events, biomarker trajectories, tumor-state deltas, emerging resistance hypotheses, monitoring logic, and re-testing triggers. This turns Translume from a single-timepoint review compiler into the data and reasoning foundation for adaptive precision oncology.

The target architecture is:

```text
Single report compiler
→ source-backed ReviewPacketExport
→ clinician-validated findings and hypotheses
→ longitudinal case timeline
→ adaptive tumor-behavior profile
→ evolving resistance / monitoring / re-testing model
→ future adaptive precision oncology review surface
```

The key design rule is simple: do not weaken the current MVP by making it more speculative. Keep the current system conservative, source-backed, and human-reviewed. Add longitudinal adaptation as a higher layer that compares validated timepoints and clinical events over time.

---

## Current Baseline to Preserve

The current system already has the right foundation. It processes an uploaded oncology report, extracts source-backed findings, normalizes molecular entities, enriches findings with graph, tool, and literature context, builds molecular phenotype and molecular-fit artifacts, creates treatment-pressure and resistance-oriented reasoning, generates biomarker watch lists and re-testing triggers, compiles an oncologist decision brief, and exposes validation, provenance, ledger, and export workflows.

This must remain the stable contract:

```text
PDF report
→ document extraction
→ section-aware chunks
→ OpenSearch retrieval
→ structured report extraction
→ entity normalization
→ evidence context
→ molecular phenotype
→ molecular-fit matrix
→ current tumor state
→ actionable biology
→ ranked options for review
→ treatment pressure map
→ resistance forecast
→ biomarker watch list
→ re-testing triggers
→ next-test recommendation
→ oncologist decision brief
→ claim cards
→ human validation
→ provenance and ledger export
```

The single-report compiler should continue to be intentionally limited. It should not diagnose disease, choose treatment, predict outcomes, calculate transition probabilities, or make autonomous clinical decisions. Its job is to organize evidence and surface tumor-behavior hypotheses for expert review.

---

## Product Destination

The destination is adaptive tumor-behavior intelligence. This means Translume should help oncology teams understand how a tumor appears to change over time under treatment pressure.

The future product should answer:

```text
What did the tumor look like at baseline?
What treatments or pressures did it experience?
What changed after those pressures?
Which molecular signals persisted, disappeared, or emerged?
Which resistance or escape routes are becoming more plausible?
Which biomarkers should be watched now?
What should trigger re-testing?
What evidence is strong, weak, unresolved, or contradicted?
Is the patient population aligned with the evidence behind each strategy?
Is the therapeutic window known or unresolved?
What validation step should happen next?
```

This is the foundation for adaptive precision oncology because it moves the product from static molecular matching to longitudinal biological interpretation.

---

# Phase 0: Stabilize the Current Single-Report Compiler

## Goal

Before adding longitudinal adaptation, the current one-report workflow must remain stable and trusted. Every new adaptive feature should depend on the current review packet instead of bypassing it.

## Work

Keep `/api/v1/reports/process` as the primary production path. Do not turn it into a longitudinal endpoint. It should continue to process one report and produce one persisted `ReviewPacketExport` and one `OncologistDecisionBrief`.

Keep the current clinical safety posture. The system should continue to fail loudly when required dependencies are missing, when source chunks are unavailable, when structured outputs are invalid, when narrative containment fails, when provenance is missing, or when unsupported clinical claims appear.

Keep human validation as a first-class object. The adaptive layer should treat human-validated findings as stronger than unvalidated findings, but it should still preserve unresolved and rejected claims as part of the audit history.

## Deliverables

The deliverable for this phase is not a new feature. It is a contract. The single-report compiler remains the trusted atomic unit that all adaptive functionality consumes.

## Acceptance Criteria

A single uploaded report still produces the same type of source-backed review packet as before. Existing UI panels still work. Existing claim validation still works. Existing exports still work. Existing safety gates still block unsupported output. No adaptive feature is allowed to weaken these guarantees.

---

# Phase 1: Add Longitudinal Case Identity and Timeline

## Goal

Create a case-level container that can hold multiple single-report review packets over time.

## Problem Being Solved

Right now, each report is treated mostly as a standalone event. That is useful for one-time review, but adaptive precision oncology requires a timeline. The system needs to know which reports belong to the same case, when they occurred, what specimen or disease site they represent, and how they relate to prior reports.

## Core Concept

Add a `LongitudinalCase` model above the existing report session model.

A case should contain:

```text
case_id
patient_alias or de-identified subject key
primary cancer type when known
case-level metadata
report timepoints
clinical events
therapy exposures
biomarker observations
human validation history
adaptive tumor-behavior profile
```

A report timepoint should contain:

```text
timepoint_id
case_id
session_id
source_file_id
report_date
specimen_date if available
specimen type
specimen site
assay type
line of therapy context if known
linked ReviewPacketExport
validation status
```

## Backend Work

Add new schemas for `LongitudinalCase`, `CaseTimepoint`, and `CaseTimeline`. These should live separately from the existing single-report schemas so the one-report compiler does not become overloaded.

Add Postgres persistence for case records and timepoint links. OpenSearch should index case-level summaries and timepoint-level artifacts for retrieval, but Postgres should remain the source of truth for case timeline metadata.

Add API endpoints:

```text
POST /api/v1/cases
GET  /api/v1/cases/{case_id}
POST /api/v1/cases/{case_id}/timepoints/from-report/{session_id}
GET  /api/v1/cases/{case_id}/timeline
```

The endpoint that links a report to a case should not re-run extraction. It should attach an already persisted single-report review packet to the longitudinal timeline.

## UI Work

Add a case timeline panel. It should show each report as a timepoint, with report date, specimen site, assay type, major findings, validation status, and whether the report changed the current tumor-behavior profile.

## Acceptance Criteria

A user can process one report as they do today, create a case, attach that report to the case, process a second report, attach it to the same case, and view both reports on a timeline without losing any single-report provenance.

---

# Phase 2: Add Therapy Exposure Events

## Goal

Represent the treatment pressure the tumor has experienced over time.

## Problem Being Solved

The current system can reason about treatment pressure from a report and evidence context, but it does not yet know what therapies the patient actually received. Without real therapy exposure, the system can only describe possible resistance mechanisms. It cannot compare molecular changes against actual treatment pressure.

## Core Concept

Add a `TherapyExposureEvent` model.

Each therapy event should include:

```text
therapy_event_id
case_id
therapy_name or regimen name
therapy_class
targets or pathways if known
start_date
stop_date if known
line_of_therapy if known
intent if known
best_response if known
reason_stopped if known
dose_reduction_or_interruption if known
toxicity_notes if available
source type: manual entry, EHR import, note extraction, or human validation
provenance
validation status
```

The system should treat therapy exposure as context, not as proof of causality. If a new mutation appears after therapy, the system should say the change is temporally associated with treatment pressure, not that the therapy caused the mutation.

## Backend Work

Add therapy exposure schemas and persistence.

Add API endpoints:

```text
POST /api/v1/cases/{case_id}/therapy-events
GET  /api/v1/cases/{case_id}/therapy-events
PATCH /api/v1/cases/{case_id}/therapy-events/{therapy_event_id}
POST /api/v1/cases/{case_id}/therapy-events/{therapy_event_id}/validation
```

Add a therapy normalization utility that maps therapy names to drug classes, targets, and pathways. This can initially be rule-based plus MIMS/tool-context assisted, but it must preserve uncertainty.

Add a safety rule: the system can say “therapy pressure relevant to EGFR/MAPK/PI3K/etc.” but should not recommend therapy or imply clinical appropriateness.

## UI Work

Add a treatment timeline under the case timeline. It should display therapies as horizontal bars across dates. Each therapy should show target/pathway pressure, validation status, and whether later molecular changes occurred after that exposure.

## Acceptance Criteria

A clinician can enter prior therapies and dates. The adaptive layer can retrieve therapy events and use them as context when comparing report timepoints. The UI can show report timepoints and therapy exposure on the same timeline.

---

# Phase 3: Add Response, Progression, and Clinical Event Tracking

## Goal

Represent the clinical events that tell the system when the tumor appears stable, responding, progressing, transforming, or showing mixed behavior.

## Problem Being Solved

A molecular report alone does not tell the full adaptive story. Tumor behavior is interpreted through events such as radiographic progression, mixed response, oligoprogression, new metastatic site, rising tumor markers, ctDNA changes, toxicity-driven treatment stops, and suspected transformation.

## Core Concept

Add a `ClinicalEvent` model.

Clinical events should include:

```text
clinical_event_id
case_id
event_type
event_date
description
disease_site if relevant
source type
linked therapy_event_id if relevant
linked timepoint_id if relevant
supporting document or note if available
confidence
validation status
provenance
```

Supported event types should include:

```text
baseline diagnosis or baseline molecular review
therapy start
therapy stop
radiographic response
radiographic stable disease
radiographic progression
mixed response
oligoprogression
new metastatic site
rising tumor marker
falling tumor marker
ctDNA increase
ctDNA decrease
ctDNA-negative progression
suspected histologic transformation
toxicity-limited therapy
pre-next-line decision point
re-biopsy performed
new molecular report available
```

## Backend Work

Add clinical event schemas and persistence.

Add API endpoints:

```text
POST /api/v1/cases/{case_id}/clinical-events
GET  /api/v1/cases/{case_id}/clinical-events
PATCH /api/v1/cases/{case_id}/clinical-events/{clinical_event_id}
POST /api/v1/cases/{case_id}/clinical-events/{clinical_event_id}/validation
```

Add an event classifier later, but do not require it in the first version. Manual entry is acceptable for the first implementation because the primary goal is to create the data model and timeline logic.

## UI Work

Add event markers to the case timeline. Events should be shown in plain English: “progression,” “mixed response,” “new metastatic site,” “ctDNA rising,” or “pre-next-line decision point.”

## Acceptance Criteria

A user can enter progression or response events and link them to a therapy exposure or report timepoint. The adaptive profile can use those events to decide whether a re-testing trigger should fire.

---

# Phase 4: Add Biomarker Trajectories

## Goal

Track biomarkers over time instead of showing them only as a static watch list.

## Problem Being Solved

The current biomarker watch list is useful, but it is mostly static. Adaptive tumor behavior requires trends: what is rising, falling, stable, newly positive, newly negative, persistent, or discordant across tests.

## Core Concept

Add a `BiomarkerObservation` and `BiomarkerTrajectory` model.

A biomarker observation should include:

```text
observation_id
case_id
biomarker name
gene or pathway if applicable
measurement type
value
unit
qualitative result
assay type
sample type
sample date
report or source document
linked timepoint_id if applicable
confidence
validation status
provenance
```

A biomarker trajectory should summarize:

```text
biomarker
observations over time
trend direction
clinical interpretation for review
possible relation to therapy pressure
possible relation to resistance hypothesis
re-testing relevance
uncertainty
source_artifact_ids
```

Initial biomarkers can include:

```text
variant allele fraction
copy-number status
fusion presence or absence
expression signal
IHC protein expression
ctDNA burden
tumor marker values
MSI status
TMB
PD-L1 if present
pathway activation markers when available
```

## Backend Work

Add schemas and persistence for observations and trajectories.

Add API endpoints:

```text
POST /api/v1/cases/{case_id}/biomarker-observations
GET  /api/v1/cases/{case_id}/biomarker-observations
GET  /api/v1/cases/{case_id}/biomarker-trajectories
POST /api/v1/cases/{case_id}/compile-biomarker-trajectories
```

Add extraction logic that can pull biomarker observations from each single-report review packet. For example, if a report contains VAF, copy-number gain/loss, fusion status, RNA expression, or IHC, those values should become structured observations in the case timeline.

Add trend logic. Start simple: increased, decreased, stable, newly detected, no longer detected, conflicting, unknown. Do not infer precise biological meaning unless evidence supports it.

## UI Work

Add a biomarker trajectory panel. It should show a row per biomarker and columns for timepoints. The user should see whether the signal is rising, falling, newly detected, persistent, or unresolved.

## Acceptance Criteria

When two or more reports are linked to a case, the system can show how key biomarkers changed across reports. If values are missing or incomparable across assays, the UI says that directly instead of pretending there is a trend.

---

# Phase 5: Add Timepoint Delta Analysis

## Goal

Compare reports over time and identify what changed biologically.

## Problem Being Solved

The core adaptive question is not only “what does this report say?” It is “what changed since the last report?” The system needs a deterministic and source-backed comparison layer.

## Core Concept

Add a `TimepointDeltaAnalysis` artifact.

It should compare two or more timepoints and classify changes as:

```text
persistent finding
newly emerged finding
lost or no-longer-detected finding
increased signal
reduced signal
assay-incomparable finding
new evidence limitation
new validation need
new possible resistance signal
new possible target relevance signal
contradicted prior hypothesis
strengthened prior hypothesis
```

## Backend Work

Add a deterministic comparator first. It should compare normalized entities, findings, alteration types, specimen sites, assay types, evidence classes, and validation decisions.

Then add a model-driven synthesis layer that turns the deterministic delta into plain-English clinical review language. The model should not invent new findings. It should only explain the deltas that the deterministic comparator found.

Add API endpoints:

```text
POST /api/v1/cases/{case_id}/compile-delta-analysis
GET  /api/v1/cases/{case_id}/delta-analysis
```

## UI Work

Add a “What changed?” panel. This should be one of the most prominent panels in the adaptive product.

It should show:

```text
New findings
Persistent findings
Lost or no-longer-detected findings
Signals that increased or decreased
Findings that cannot be compared because assays differ
Evidence gaps that changed
Validation needs that changed
```

## Acceptance Criteria

Given two reports for the same case, the system can produce a source-backed delta. It must clearly distinguish true biological change from assay incomparability or missing data.

---

# Phase 6: Add Adaptive Tumor State Model

## Goal

Turn single-timepoint tumor states into an evolving case-level tumor-behavior profile.

## Problem Being Solved

The current tumor-behavior model describes one report context. Adaptive precision oncology requires a state model that evolves over time.

## Core Concept

Add an `AdaptiveTumorBehaviorProfile` artifact.

It should include:

```text
case_id
current_state_summary
state_history
active disease drivers for review
inactive or unsupported drivers
emerging resistance signals
therapy-pressure context
biomarker trajectories
re-testing triggers
validation needs
population-alignment gaps
therapeutic-window gaps
confidence and uncertainty
source timepoints
human validation status
```

Each `TumorStateSnapshot` should include:

```text
timepoint_id
state_label
state_rationale
supporting findings
therapy context before snapshot
clinical event context
biomarker context
resistance context
unresolved evidence
validation status
```

The state model should avoid probabilities. It should classify evidence direction and uncertainty, not predict outcomes.

Suggested state vocabulary:

```text
baseline molecular state
post-treatment monitored state
response-associated state
stable-disease-associated state
progression-associated state
mixed-response state
oligoprogression-associated state
suspected resistant subclone expansion
suspected pathway bypass activation
suspected lineage or histologic shift
assay-incomplete state
unresolved state
```

## Backend Work

Create a compiler that consumes:

```text
case timeline
review packets
timepoint delta analysis
therapy exposure events
clinical events
biomarker trajectories
human validation decisions
```

The compiler should produce the current adaptive profile. It should be deterministic where possible and model-assisted only for synthesis.

Add API endpoints:

```text
POST /api/v1/cases/{case_id}/compile-adaptive-profile
GET  /api/v1/cases/{case_id}/adaptive-profile
```

Add validation rules:

```text
No unsupported state changes.
No outcome prediction.
No treatment recommendation.
No transition probabilities.
Every state must link to timepoints, events, findings, or unresolved evidence.
Every resistance hypothesis must link to therapy pressure, molecular evidence, literature/tool evidence, or state that evidence is unresolved.
```

## UI Work

Add a “Current Tumor Behavior” panel at the top of the adaptive case view.

It should answer:

```text
What does the tumor appear to be doing now?
What changed since baseline?
What changed since the last report?
What resistance or escape routes are becoming more plausible?
What evidence is strong?
What is unresolved?
What should be validated next?
```

## Acceptance Criteria

Given multiple reports and clinical events, the system can generate a case-level adaptive tumor-behavior profile without making treatment recommendations or unsupported outcome predictions.

---

# Phase 7: Add Resistance and Escape Ledger

## Goal

Track resistance hypotheses over time as evidence accumulates or weakens.

## Problem Being Solved

Resistance is not a one-time output. It is a hypothesis that changes as new reports, biomarkers, therapies, and progression events appear.

## Core Concept

Add a `ResistanceEscapeLedger`.

Each resistance or escape hypothesis should include:

```text
hypothesis_id
case_id
hypothesis label
associated therapy pressure
associated target or pathway
first observed timepoint
current evidence status
supporting findings
contradicting findings
biomarker trajectory support
clinical event support
recommended validation test
monitoring strategy
status history
human validation status
```

Evidence status should be conservative:

```text
unresolved
weakly supported
increasingly supported
supported for review
contradicted
validated by human reviewer
rejected by human reviewer
```

## Backend Work

Promote the current resistance forecast into a longitudinal ledger. Each new report should update existing hypotheses or create new ones.

Add API endpoints:

```text
GET  /api/v1/cases/{case_id}/resistance-ledger
POST /api/v1/cases/{case_id}/compile-resistance-ledger
POST /api/v1/cases/{case_id}/resistance-ledger/{hypothesis_id}/validation
```

## UI Work

Add a resistance ledger panel. It should not look like a one-time forecast. It should look like an evidence tracker.

For each hypothesis, show:

```text
What the hypothesis is
Why it matters
What therapy pressure it may relate to
What evidence supports it
What evidence is missing
What changed over time
What should be tested next
Human review status
```

## Acceptance Criteria

A resistance hypothesis can persist across multiple timepoints and change status as new evidence appears. The system can show whether a resistance hypothesis is becoming stronger, weaker, contradicted, or still unresolved.

---

# Phase 8: Make the Sankey Time-Aware

## Goal

Turn the static therapy-to-escape Sankey into a longitudinal adaptive behavior visualization.

## Problem Being Solved

A static Sankey can show possible therapy pressure and escape routes, but adaptive oncology needs to show when those pressures happened and how the tumor state changed afterward.

## Core Concept

The adaptive Sankey should show:

```text
Therapy exposure
→ target or pathway pressure
→ tumor state before therapy
→ tumor state after therapy or at progression
→ emerging resistance or escape hypothesis
→ biomarker to monitor
→ re-testing trigger
```

It should support timepoint filtering:

```text
baseline only
post-therapy A
progression on therapy A
post-therapy B
latest state
full case timeline
```

## Backend Work

Add an `AdaptiveSankeyPath` model that links therapy events, report timepoints, tumor state snapshots, resistance hypotheses, and biomarker observations.

Do not remove the current Sankey. Keep it for single-report packets. Add a new case-level Sankey for longitudinal views.

Add API endpoints:

```text
GET  /api/v1/cases/{case_id}/adaptive-sankey
POST /api/v1/cases/{case_id}/compile-adaptive-sankey
```

## UI Work

Add a time-aware Sankey panel with filters for timepoint and therapy exposure. Hide IDs and internal artifact names by default. The clinician should see the clinical story, not the implementation details.

## Acceptance Criteria

The Sankey can show how a therapy pressure relates to a target/pathway, how the tumor state changed afterward, what escape path is being watched, and what biomarker or re-test event matters next.

---

# Phase 9: Add Population Alignment Over Time

## Goal

Make patient-population alignment explicit, conservative, and longitudinal.

## Problem Being Solved

A molecular match is not enough. The patient may not resemble the cohort behind the evidence. Evidence can depend on tumor type, disease stage, line of therapy, prior treatments, biomarker definition, assay type, performance status, organ function, and trial eligibility.

## Core Concept

Add a `PopulationAlignmentAssessment` that can be evaluated at each decision point.

It should include:

```text
strategy or evidence item
patient/case attributes available
attributes required by evidence
matched attributes
missing attributes
mismatched attributes
alignment status
why unresolved
source evidence
human validation status
```

Alignment statuses should be:

```text
aligned for review
partially aligned
not aligned
unresolved due to missing patient context
unresolved due to missing evidence context
```

## Backend Work

Create an evidence-item-level population extraction step. For each treatment or strategy evidence item, extract the cohort context when available.

Create a patient-context model. Initially this can be manually entered or extracted from reports when present.

Add validation: if required patient context or evidence population context is missing, alignment must remain unresolved.

Add API endpoints:

```text
POST /api/v1/cases/{case_id}/patient-context
GET  /api/v1/cases/{case_id}/population-alignment
POST /api/v1/cases/{case_id}/compile-population-alignment
```

## UI Work

Add a population alignment panel. It should say plainly whether the evidence population appears aligned, partially aligned, not aligned, or unresolved.

## Acceptance Criteria

The system does not imply population fit unless there is evidence. When evidence is missing, the UI says what information is needed to resolve alignment.

---

# Phase 10: Add Therapeutic Window Assessment

## Goal

Represent whether a biologically interesting target can plausibly be acted on within clinical constraints, while keeping unresolved status when evidence is insufficient.

## Problem Being Solved

Precision oncology often fails when a target is biologically interesting but not clinically reachable. Dose, toxicity, tissue exposure, patient condition, drug availability, and evidence strength matter.

## Core Concept

Add a `TherapeuticWindowAssessment`.

It should include:

```text
target or pathway
strategy or drug class
known efficacy context
known toxicity context
tissue exposure context
dose feasibility context
patient-specific constraints if available
evidence strength
unresolved gaps
status
source evidence
human validation status
```

Statuses should be:

```text
supported for review
limited by toxicity evidence
limited by exposure evidence
limited by patient context
preclinical only
unresolved
not enough evidence
```

## Backend Work

Add ToolUniverse or literature workflows focused on toxicity, dose feasibility, tissue exposure, and clinical evidence context. Keep this separate from treatment recommendations.

Add strict wording rules. The system can say “therapeutic window unresolved” or “toxicity may limit feasibility based on supplied evidence.” It should not say “use this drug” or “this therapy is safe for this patient.”

Add API endpoints:

```text
GET  /api/v1/cases/{case_id}/therapeutic-window
POST /api/v1/cases/{case_id}/compile-therapeutic-window
```

## UI Work

Add a therapeutic window panel. Most rows will likely be unresolved early on. That is acceptable and clinically safer than false confidence.

## Acceptance Criteria

The system can distinguish biological target relevance from clinical feasibility. It does not imply that a target is actionable simply because it is molecularly interesting.

---

# Phase 11: Build the Adaptive Case Review Brief

## Goal

Create the case-level report that oncologists actually read.

## Problem Being Solved

The current decision brief is one-report centered. The adaptive product needs a longitudinal brief that summarizes tumor evolution, therapy pressure, biomarker trends, resistance hypotheses, population fit, therapeutic-window limits, and validation needs.

## Core Concept

Add an `AdaptiveCaseReviewBrief`.

It should answer:

```text
What is the current tumor-behavior interpretation?
What changed since the prior report?
What changed since baseline?
What therapy pressure has the tumor experienced?
Which resistance or escape routes are emerging?
Which biomarkers should be monitored?
What should trigger re-testing?
Is the patient aligned with the evidence population?
Is the therapeutic window known or unresolved?
What is strong, weak, contradicted, or unresolved?
What needs validation next?
```

## Backend Work

Compile the adaptive brief from existing case-level artifacts:

```text
case timeline
therapy exposure events
clinical events
review packets
timepoint delta analysis
biomarker trajectories
adaptive tumor-behavior profile
resistance ledger
adaptive sankey
population alignment
therapeutic window assessment
human validation decisions
```

Run containment validation similar to the current narrative containment. The adaptive brief must not introduce unsupported genes, therapies, events, dates, or claims.

Add API endpoints:

```text
POST /api/v1/cases/{case_id}/compile-adaptive-brief
GET  /api/v1/cases/{case_id}/adaptive-brief
GET  /api/v1/cases/{case_id}/export
```

## UI Work

Make the adaptive brief the top-level case view. The clinician should not have to inspect raw artifacts to understand the case.

Suggested UI order:

```text
1. Current tumor behavior
2. What changed since last review
3. Therapy pressure timeline
4. Emerging resistance / escape ledger
5. Biomarker trajectories
6. Re-testing triggers
7. Population alignment
8. Therapeutic window status
9. Validation needs
10. Evidence and provenance
```

## Acceptance Criteria

A case with multiple reports, therapy exposures, and progression events can produce a source-backed adaptive review brief that is clinically readable and audit-ready.

---

# Phase 12: Add Evaluation and Demo Cases

## Goal

Prove the adaptive layer works on realistic longitudinal cases.

## Problem Being Solved

Single-report validation is not enough. The adaptive layer must be tested against multi-timepoint cases with known report changes, therapy exposures, and progression events.

## Work

Create synthetic but realistic longitudinal test cases. These should not claim to represent real patients unless properly de-identified and authorized.

Each demo case should include:

```text
baseline report
therapy exposure
response or progression event
follow-up report
biomarker changes
new or persistent findings
resistance hypothesis
re-testing trigger
human validation decisions
```

Add evaluation tests for:

```text
case creation
timepoint linking
therapy event persistence
clinical event persistence
biomarker trajectory compilation
delta analysis correctness
adaptive tumor-state compilation
resistance ledger updates
adaptive Sankey paths
population alignment unresolved behavior
therapeutic window unresolved behavior
adaptive brief containment
export correctness
```

## Acceptance Criteria

The integration runner can process a longitudinal demo case end to end. It should validate the single-report path, case timeline, adaptive profile, UI rendering, validation workflow, and export.

---

# Data Model Summary

The adaptive layer should add these new primary objects:

```text
LongitudinalCase
CaseTimepoint
CaseTimeline
TherapyExposureEvent
ClinicalEvent
BiomarkerObservation
BiomarkerTrajectory
TimepointDeltaAnalysis
TumorStateSnapshot
AdaptiveTumorBehaviorProfile
ResistanceEscapeLedger
AdaptiveSankeyPath
PopulationAlignmentAssessment
TherapeuticWindowAssessment
AdaptiveCaseReviewBrief
```

The key relationship is:

```text
LongitudinalCase
  contains CaseTimepoints
  each CaseTimepoint links to a ReviewPacketExport
  contains TherapyExposureEvents
  contains ClinicalEvents
  contains BiomarkerObservations
  compiles BiomarkerTrajectories
  compiles TimepointDeltaAnalysis
  compiles AdaptiveTumorBehaviorProfile
  compiles ResistanceEscapeLedger
  compiles AdaptiveCaseReviewBrief
```

---

# Safety Rules for Adaptive Precision Oncology Foundation

The adaptive layer must remain conservative. It should support expert review, not autonomous clinical decision-making.

Hard rules:

```text
Do not diagnose.
Do not recommend treatment.
Do not predict outcomes.
Do not assign response or survival probabilities.
Do not claim causality from therapy to resistance unless externally validated.
Do not imply population alignment when patient or evidence context is missing.
Do not imply therapeutic feasibility when toxicity, exposure, dose, or patient context is missing.
Do not hide assay incomparability.
Do not collapse weak evidence into strong evidence.
Do not remove provenance.
Do not bypass human validation.
```

Preferred language:

```text
consistent with
may support
requires validation
unresolved
limited evidence
not assessable from available data
temporally associated
possible escape route for review
monitoring consideration for expert review
```

Avoid language:

```text
will respond
will progress
should receive
best treatment
caused resistance
clinically proven for this patient
safe and effective
predicts survival
```

---

# Implementation Order

The recommended build order is:

```text
1. Preserve and freeze the single-report compiler contract.
2. Add LongitudinalCase and CaseTimepoint.
3. Add therapy exposure events.
4. Add response/progression clinical events.
5. Extract and store biomarker observations from review packets.
6. Compile biomarker trajectories.
7. Compile timepoint delta analysis.
8. Compile adaptive tumor-behavior profile.
9. Build resistance and escape ledger.
10. Add time-aware adaptive Sankey.
11. Add population alignment.
12. Add therapeutic window assessment.
13. Compile adaptive case review brief.
14. Add longitudinal UI panels.
15. Add end-to-end demo cases and integration validation.
```

This order matters because adaptive intelligence depends on timeline integrity. Do not build the adaptive brief first. Build case identity, timepoints, therapy events, clinical events, biomarker observations, and deltas first. The brief should be the final synthesis, not the first artifact.

---

# MVP-to-Adaptive Architecture

The architecture should evolve as follows:

```text
Current MVP:
One report → ReviewPacketExport → OncologistDecisionBrief

Adaptive Layer:
Multiple ReviewPacketExports + therapy events + clinical events + biomarkers
→ CaseTimeline
→ TimepointDeltaAnalysis
→ AdaptiveTumorBehaviorProfile
→ ResistanceEscapeLedger
→ AdaptiveCaseReviewBrief

Future Adaptive Precision Oncology Foundation:
AdaptiveCaseReviewBriefs across many cases
→ cohort learning
→ evidence feedback
→ biomarker strategy refinement
→ trial matching support for expert review
→ research workflow acceleration
```

The current MVP should remain the source-backed evidence compiler. The adaptive layer should become the longitudinal interpretation engine. The future adaptive precision oncology layer should only be built after the case-level adaptive profile is reliable, auditable, and validated.

---

# Near-Term Stories

## Story 1: Create LongitudinalCase Schema and Persistence

Add case-level schemas, Postgres tables, and API endpoints for creating and retrieving a longitudinal case.

## Story 2: Link ReviewPacketExport to CaseTimepoint

Allow an existing report-processing session to be attached to a case as a timepoint without re-running extraction.

## Story 3: Render Case Timeline in UI

Show all reports attached to a case with report date, specimen type, assay type, major findings, and validation status.

## Story 4: Add TherapyExposureEvent

Add therapy exposure schemas, persistence, API endpoints, validation status, and UI timeline rendering.

## Story 5: Add ClinicalEvent

Add response, progression, mixed response, new lesion, ctDNA change, and pre-next-line event tracking.

## Story 6: Extract BiomarkerObservations from Review Packets

Promote VAFs, CNVs, fusions, expression signals, IHC, tumor markers, and ctDNA values into structured case-level observations.

## Story 7: Compile BiomarkerTrajectory

Create trend logic for persistent, increased, decreased, newly detected, no longer detected, conflicting, missing, and assay-incomparable biomarkers.

## Story 8: Compile TimepointDeltaAnalysis

Compare report timepoints and show what changed, what persisted, what is no longer detected, and what cannot be compared.

## Story 9: Compile AdaptiveTumorBehaviorProfile

Create the first case-level tumor-state model using timepoints, deltas, therapy pressure, clinical events, and biomarker trajectories.

## Story 10: Compile AdaptiveCaseReviewBrief

Create the top-level longitudinal report that answers what changed, what is emerging, what needs monitoring, and what needs validation next.

---

# Definition of Done for Adaptive Layer v1

Adaptive Layer v1 is done when Translume can:

```text
Process at least two molecular reports for one case.
Attach both reports to a longitudinal case timeline.
Record at least one therapy exposure.
Record at least one response or progression event.
Extract biomarker observations from both reports.
Show biomarker changes over time.
Generate a source-backed timepoint delta.
Generate an adaptive tumor-behavior profile.
Track at least one resistance or escape hypothesis over time.
Surface at least one re-testing trigger tied to a real event or unresolved evidence gap.
Generate a clinician-readable adaptive case brief.
Preserve provenance for every claim.
Allow human validation of case-level claims.
Export the longitudinal case packet.
Avoid treatment recommendations, diagnosis, outcome prediction, and unsupported certainty.
```

---

# Final Product Principle

The product should not become “AI recommends cancer treatment.” That is the wrong story and the wrong safety posture.

The correct story is:

```text
Translume turns molecular oncology reports and clinical events into a source-backed, longitudinal tumor-behavior intelligence layer that helps expert teams understand how the tumor is changing, what evidence supports that interpretation, what remains unresolved, and what should be validated next.
```

That is the bridge from the current trusted single-report compiler to adaptive precision oncology.
