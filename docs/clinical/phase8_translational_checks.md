# Phase 8: Translational Checks and Tumor-Behavior UI

Phase 8 adds a five-question translational assessment to the oncologist decision brief. The UI now leads with the questions Translume is designed to answer: target relevance, biomarker evidence strength, resistance readiness, patient-population alignment, and evidence/validation resolution.

The backend generates the assessment as its own staged structured-output artifact. The final `OncologistDecisionBrief` copies that staged output and preserves row-level source IDs or unresolved evidence. Patient-population alignment is intentionally conservative: it remains unresolved unless the supplied report/evidence contains explicit disease-setting, biomarker, and treatment-cohort alignment.

The mechanism figure now prioritizes the clinical story. New decision-brief packets render therapy/drug class → molecular target/pathway → tumor behavior state → escape/recombination pathway → when to watch. Legacy packets can still render their older mechanism Sankey for compatibility, but new packets should use the therapy-to-escape flow.

The main UI removes internal IDs from report-facing tables. Technical IDs remain in the raw packet/export for audit, but the clinician-facing report emphasizes context, rationale, uncertainty, monitoring, and next-test triggers.
