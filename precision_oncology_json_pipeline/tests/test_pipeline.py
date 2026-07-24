from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

import precision_oncology_pipeline as p

EXAMPLES = Path(__file__).resolve().parents[1] / "examples"


def test_stable_id_is_deterministic_and_content_addressed() -> None:
    first = p.stable_id("hyp", {"b": 2, "a": 1})
    second = p.stable_id("hyp", {"a": 1, "b": 2})
    changed = p.stable_id("hyp", {"a": 1, "b": 3})

    assert first == second
    assert first.startswith("hyp_")
    assert first != changed


def test_url_normalization_and_trial_canonicalization() -> None:
    normalized = p.normalize_url(
        "https://WWW.Example.org:443//article/?utm_source=x&b=2&a=1#section"
    )
    assert normalized == "https://www.example.org/article?a=1&b=2"

    trial_url = p.ensure_source_url(
        {
            "url": "https://clinicaltrials.gov/ct2/show/NCT05094336?utm_source=x",
            "source_type": "trial_record",
            "title": "Example trial",
            "identifiers": {"nct_id": "NCT05094336"},
        }
    )
    assert trial_url == "https://clinicaltrials.gov/study/NCT05094336"


def test_nct_extraction_repairs_common_ocr_letter_o() -> None:
    assert p.extract_nct_ids(
        ["Study NCT05094336", "OCR value NCTO5094336", "duplicate NCT05094336"]
    ) == ["NCT05094336"]


def test_preferred_source_hints_do_not_create_invalid_domains() -> None:
    domains = p.preferred_source_domains(
        [
            "PubMed",
            "ClinicalTrials.gov",
            "primary literature",
            "https://example.org/path",
        ]
    )
    assert domains == (
        "pubmed.ncbi.nlm.nih.gov",
        "clinicaltrials.gov",
        "example.org",
    )


def test_example_input_builds_canonical_actionable_contract() -> None:
    raw = json.loads((EXAMPLES / "minimal_translume_input.example.json").read_text())
    canonical = p.build_canonical_input(raw)

    assert canonical.case.case_id == "case_example"
    assert canonical.case.disease.name == "Example sarcoma"
    assert canonical.case.specimen.tumor_percentage == 70

    primary_by_gene = {
        finding.gene_or_marker: finding for finding in canonical.actionable_findings
    }
    assert "MTAP" in primary_by_gene
    assert primary_by_gene["MTAP"].existing_trial_ids == ["NCT05094336"]

    limitation_labels = {item.label for item in canonical.technical_limitations}
    assert "TAF1 low coverage" in limitation_labels

    trial_mentions = canonical.existing_context.existing_trial_mentions
    assert trial_mentions[0]["url"] == ("https://clinicaltrials.gov/study/NCT05094336")


def _minimal_renderer_state() -> p.PipelineState:
    raw = json.loads((EXAMPLES / "minimal_translume_input.example.json").read_text())
    canonical = p.build_canonical_input(raw)

    source = p.SourceRegistryEntry(
        source_id="src_trial",
        canonical_key="nct:NCT05094336",
        title="Example MTAP-deleted solid-tumor trial",
        url="https://clinicaltrials.gov/study/NCT05094336",
        publisher="ClinicalTrials.gov",
        source_type="trial_record",
        source_role="trial_record",
        publication_or_update_date="2026-07-01",
        identifiers=p.SourceIdentifiers(nct_id="NCT05094336"),
        hypothesis_ids=["hyp_mtap"],
        job_ids=["job_trial"],
        selection_score=9.0,
        verification_status="returned_web_source",
        consulted_urls=["https://clinicaltrials.gov/study/NCT05094336"],
    )

    score = p.FitDimension(score=8, reason="Direct biomarker match.")
    assessment = p.SourceFitAssessment(
        assessment_id="assessment_trial",
        source_id=source.source_id,
        hypothesis_id="hyp_mtap",
        appendix_title="ClinicalTrials.gov - Example trial",
        url=source.url,
        source_type=source.source_type,
        relevant_marker_or_pathway=["MTAP", "PRMT5"],
        opening_assessment="Strong molecular trial-screening lead; investigational.",
        standardized_scores=p.FitDimensions(
            molecular_fit=score,
            population_fit=p.FitDimension(score=5, reason="Histology fit unknown."),
            evidence_maturity=p.FitDimension(score=3, reason="Trial record."),
            standard_care_readiness=p.FitDimension(
                score=1, reason="Investigational only."
            ),
            trial_screening_value=score,
        ),
        bottom_line_score_rows=[
            p.BottomLineScoreRow(
                question="Does the biomarker match?",
                strength_label="Strong",
                score_min=8,
                score_max=8,
                why="The protocol is biomarker directed.",
            )
        ],
        why_the_fit_is_strong=["Biomarker logic aligns."],
        matching_features=["MTAP loss"],
        mismatching_features=[],
        unknown_alignment_fields=["stage", "performance status"],
        what_would_make_the_patient_a_stronger_candidate=[
            "Protocol-acceptable MTAP confirmation."
        ],
        what_weakens_the_case=["Eligibility context is incomplete."],
        my_read_on_this_case="Appropriate for protocol-level screening.",
        clinical_framing_to_use="Consider trial screening after confirmation.",
        do_not_say="The patient is eligible or should receive the drug.",
        say_instead="The biomarker supports a trial-screening discussion.",
        source_specific_follow_up=[
            p.FollowUpAction(
                follow_up="Confirm the biomarker.",
                why="The protocol may require a specific assay.",
                priority="high",
            )
        ],
        source_specific_conclusion=["Trial-screening lead, not standard care."],
        patient_evidence_ids=[],
        external_support_claims=["The trial enrolls biomarker-selected tumors."],
        confidence="moderate",
    )

    trial = p.TrialPrescreen(
        prescreen_id="prescreen_trial",
        source_id=source.source_id,
        nct_id="NCT05094336",
        trial_status="RECRUITING",
        last_update="2026-07-01",
        biomarker_match=p.MatchAssessment(
            status="POSSIBLE_MATCH", reason="Confirmation requirement unresolved."
        ),
        tumor_type_match=p.MatchAssessment(
            status="UNKNOWN", reason="Cohort-level histology fit unresolved."
        ),
        disease_setting_match=p.MatchAssessment(
            status="UNKNOWN", reason="Stage and setting are missing."
        ),
        criterion_assessment=[],
        required_missing_data=["stage", "ECOG", "organ function"],
        site_and_geography=[],
        screening_priority="medium",
        reason="Molecular match warrants review; eligibility is undetermined.",
        not_a_final_eligibility_determination=True,
    )

    report = p.ReportDraft(
        report_draft_id="report_example",
        cover_metadata=p.CoverMetadata(
            title="Precision Oncology Actionable Packet",
            subtitle="Professional summary for clinicians and patients",
            purpose_statements=["Translate actionable findings."],
            source_label="Uploaded review packet",
            report_type="NGS",
            disease_or_tumor_type="Example sarcoma",
            specimen_context="Soft tissue",
            overall_validation_status="Needs Review",
            important_note="Educational support only.",
        ),
        executive_summary=p.ExecutiveSummarySection(
            paragraphs=[],
            top_takeaway="Review the biomarker and trial context.",
            most_trial_relevant_finding="MTAP loss",
            most_likely_to_require_confirmation="MTAP loss",
            most_important_technical_caveat="TAF1 low coverage",
        ),
        key_findings=[],
        other_findings=[],
        cause_effect=[],
        therapy_options=[],
        practical_readout=[],
        resistance_escape=[],
        follow_up_tests=[],
        phenotypic_events=[],
        limitations=["Clinical context is incomplete."],
        selected_links=[
            p.SelectedLinkRow(
                row_id="link_trial",
                source_id=source.source_id,
                title=source.title,
                url=source.url,
                why_it_is_useful="Official current trial record.",
                source_type=source.source_type,
                hypothesis_id="hyp_mtap",
            )
        ],
        bottom_line=["Use for trial screening, not treatment selection."],
        url_fit_appendix=p.URLFitAppendixOverview(
            data_basis_and_rules=["Separate biology from treatment readiness."],
            scoring_guide="9-10 very strong; 1-3 weak or not actionable.",
            source_index=[
                p.AppendixSourceIndexRow(
                    display_order=1,
                    source_id=source.source_id,
                    title=source.title,
                    marker_or_pathway=["MTAP", "PRMT5"],
                    evidence_type="trial_record",
                    url=source.url,
                )
            ],
            source_assessment_ids=[assessment.assessment_id],
        ),
    )

    cross = p.CrossSourceSynthesis(
        synthesis_id="cross_example",
        summary="The source supports trial screening, not standard care.",
        themes=[
            p.CrossSourceTheme(
                theme="MTAP / PRMT5",
                cross_source_conclusion="Confirm the biomarker and review trials.",
                evidence_maturity="investigational",
                clinical_role="trial screening",
            )
        ],
        practical_bottom_line=["Eligibility remains protocol dependent."],
        source_ids=[source.source_id],
    )

    return p.PipelineState(
        run_id="run_example",
        source_input_sha256="0" * 64,
        canonical_input=canonical,
        sources=(source,),
        source_fit_assessments=(assessment,),
        trial_prescreens=(trial,),
        report_draft=report,
        cross_source_synthesis=cross,
    )


def test_renderer_sections_match_reference_packet_content_flow() -> None:
    state = _minimal_renderer_state()
    sections = p.build_renderer_sections(state)

    section_ids = [section.section_id for section in sections]
    content_types = [section.content_type for section in sections]

    assert set(p.SECTION_IDS.values()).issubset(section_ids)
    assert "url_candidate_fit_assessment" in content_types
    assert section_ids[0] == p.SECTION_IDS["cover"]
    assert section_ids[-1] == p.SECTION_IDS["urls_assessed"]

    urls_section = next(
        item for item in sections if item.section_id == p.SECTION_IDS["urls_assessed"]
    )
    assert urls_section.payload["urls_assessed"][0]["url"] == (
        "https://clinicaltrials.gov/study/NCT05094336"
    )


def test_deterministic_integrity_validation_accepts_minimal_consistent_state() -> None:
    state = _minimal_renderer_state()
    sections = p.build_renderer_sections(state)
    result = p.deterministic_integrity_validation(state, sections)

    blocking = [item for item in result.findings if item.severity == "blocking"]
    assert blocking == []


def test_final_schema_exposes_renderer_maps_and_document_flow() -> None:
    schema = p.FinalPacket.model_json_schema()
    properties = schema["properties"]

    assert "sections_by_id" in properties
    assert "document_flow" in properties
    assert "source_fit_assessments_by_id" in properties
    assert "trial_prescreens_by_id" in properties
    assert "sources_by_id" in properties


def test_openai_gateway_builds_structured_web_search_request(tmp_path: Path) -> None:
    class Echo(p.StrictModel):
        value: str

    class FakeResponse:
        id = "resp_test"
        model = "gpt-5.6-luna"
        output_parsed = Echo(value="ok")

        def model_dump(self, *, mode: str = "json") -> dict[str, object]:
            del mode
            return {
                "usage": {"input_tokens": 10, "output_tokens": 2},
                "output": [
                    {
                        "type": "web_search_call",
                        "action": {
                            "sources": [
                                {
                                    "url": "https://clinicaltrials.gov/study/NCT05094336",
                                    "title": "Example trial",
                                    "type": "web",
                                }
                            ]
                        },
                    }
                ],
            }

    captured: dict[str, object] = {}

    class FakeResponses:
        def parse(self, **kwargs: object) -> FakeResponse:
            captured.update(kwargs)
            return FakeResponse()

    class FakeClient:
        responses = FakeResponses()

    config = p.PipelineConfig(
        api_key="sk-test",
        model="gpt-5.6-luna",
        reasoning_effort="medium",
        output_dir=tmp_path,
    )
    gateway = p.OpenAIResponsesGateway(
        config,
        p.ArtifactStore(tmp_path, "run_test"),
    )
    gateway._client = FakeClient()

    result = gateway._call_once(
        stage="source_discovery",
        prompt=p.PROMPTS["source_discovery"],
        payload={"job": "test"},
        response_model=Echo,
        use_web=True,
        allowed_domains=("clinicaltrials.gov",),
        required_web=True,
    )

    assert result.parsed.value == "ok"
    assert captured["model"] == "gpt-5.6-luna"
    assert captured["text_format"] is Echo
    assert captured["tool_choice"] == "required"
    assert captured["include"] == ["web_search_call.action.sources"]
    tools = captured["tools"]
    assert isinstance(tools, list)
    web_tool = tools[0]
    assert web_tool["type"] == "web_search"
    assert web_tool["external_web_access"] is True
    assert web_tool["filters"]["allowed_domains"] == ["clinicaltrials.gov"]
    assert "wikipedia.org" in web_tool["filters"]["blocked_domains"]
    assert result.web_sources[0].url == ("https://clinicaltrials.gov/study/NCT05094336")


def test_openai_gateway_accepts_content_level_parsed_output(tmp_path: Path) -> None:
    """Support the parsed location used by Responses API message content."""

    class Echo(p.StrictModel):
        value: str

    parsed = Echo(value="content-level")
    content = type("Content", (), {"parsed": parsed})()
    message = type("Message", (), {"type": "message", "content": [content]})()

    class FakeResponse:
        id = "resp_content"
        model = "gpt-5.4-mini"
        output_parsed = None
        output = [message]
        output_text = ""
        status = "completed"

        def model_dump(self, *, mode: str = "json") -> dict[str, object]:
            del mode
            return {"status": "completed", "usage": {}, "output": []}

    class FakeResponses:
        def parse(self, **kwargs: object) -> FakeResponse:
            del kwargs
            return FakeResponse()

    gateway = p.OpenAIResponsesGateway(
        p.PipelineConfig(
            api_key="sk-test",
            model="gpt-5.4-mini",
            reasoning_effort="medium",
            output_dir=tmp_path,
        ),
        p.ArtifactStore(tmp_path, "run_content"),
    )
    gateway._client = type("Client", (), {"responses": FakeResponses()})()

    result = gateway._call_once(
        stage="hypothesis_synthesis",
        prompt=p.PROMPTS["hypothesis_synthesis"],
        payload={"hypothesis": "test"},
        response_model=Echo,
        use_web=False,
        allowed_domains=(),
        required_web=False,
    )

    assert result.parsed.value == "content-level"


def test_hypothesis_synthesis_adapts_after_incomplete_response(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Retry an incomplete synthesis with lower reasoning instead of identically."""

    class Echo(p.StrictModel):
        value: str

    calls: list[dict[str, object]] = []

    class FakeResponse:
        def __init__(self, *, complete: bool) -> None:
            self.id = "resp_complete" if complete else "resp_incomplete"
            self.model = "gpt-5.4-mini"
            self.output_parsed = Echo(value="ok") if complete else None
            self.output = []
            self.output_text = ""
            self.status = "completed" if complete else "incomplete"
            self.incomplete_details = (
                None
                if complete
                else type("Incomplete", (), {"reason": "max_output_tokens"})()
            )

        def model_dump(self, *, mode: str = "json") -> dict[str, object]:
            del mode
            return {
                "status": self.status,
                "incomplete_details": (
                    None
                    if self.incomplete_details is None
                    else {"reason": self.incomplete_details.reason}
                ),
                "usage": {
                    "output_tokens": 30_000,
                    "output_tokens_details": {"reasoning_tokens": 29_500},
                },
                "output": [],
            }

    class FakeResponses:
        def parse(self, **kwargs: object) -> FakeResponse:
            calls.append(dict(kwargs))
            return FakeResponse(complete=len(calls) > 1)

    monkeypatch.setattr(p.time, "sleep", lambda _seconds: None)
    gateway = p.OpenAIResponsesGateway(
        p.PipelineConfig(
            api_key="sk-test",
            model="gpt-5.4-mini",
            reasoning_effort="medium",
            output_dir=tmp_path,
            max_attempts=2,
        ),
        p.ArtifactStore(tmp_path, "run_retry"),
    )
    gateway._client = type("Client", (), {"responses": FakeResponses()})()

    result = gateway._call_with_retry(
        "hypothesis_synthesis",
        p.PROMPTS["hypothesis_synthesis"],
        {"hypothesis": "test"},
        Echo,
        False,
        (),
        False,
    )

    assert result.parsed.value == "ok"
    assert calls[0]["reasoning"]["effort"] == "medium"
    assert calls[1]["reasoning"]["effort"] == "low"
    assert calls[1]["max_output_tokens"] == 30_000


def test_report_compiler_uses_stage_timeout_and_compacts_timeout_retry(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Use a longer report timeout and one lower-reasoning compact retry."""

    class Echo(p.StrictModel):
        value: str

    class APITimeoutError(Exception):
        pass

    calls: list[dict[str, object]] = []
    timeouts: list[float] = []

    class FakeResponse:
        id = "resp_report"
        model = "gpt-5.4-mini"
        output_parsed = Echo(value="ok")

        def model_dump(self, *, mode: str = "json") -> dict[str, object]:
            del mode
            return {"usage": {}, "output": []}

    class FakeResponses:
        def parse(self, **kwargs: object) -> FakeResponse:
            calls.append(dict(kwargs))
            if len(calls) == 1:
                raise APITimeoutError("timed out")
            return FakeResponse()

    class FakeClient:
        responses = FakeResponses()

        def with_options(self, *, timeout: float) -> FakeClient:
            timeouts.append(timeout)
            return self

    monkeypatch.setattr(p.time, "sleep", lambda _seconds: None)
    gateway = p.OpenAIResponsesGateway(
        p.PipelineConfig(
            api_key="sk-test",
            model="gpt-5.4-mini",
            reasoning_effort="medium",
            output_dir=tmp_path,
            max_attempts=2,
        ),
        p.ArtifactStore(tmp_path, "run_report_timeout"),
    )
    gateway._client = FakeClient()
    payload = {
        "secondary_findings": list(range(30)),
        "context_findings": list(range(30)),
        "selected_sources": [],
        "appendix_source_assessments": [],
    }

    result = gateway._call_with_retry(
        "report_compiler",
        p.PROMPTS["report_compiler"],
        payload,
        Echo,
        False,
        (),
        False,
    )

    assert result.parsed.value == "ok"
    assert timeouts == [900.0, 900.0]
    assert calls[0]["reasoning"]["effort"] == "medium"
    assert calls[1]["reasoning"]["effort"] == "low"
    retry_text = calls[1]["input"][1]["content"]
    assert "timeout_retry_compaction" in retry_text
    assert payload["secondary_findings"] == list(range(30))


def test_mocked_end_to_end_run_emits_renderable_final_packet(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import asyncio

    input_path = EXAMPLES / "minimal_translume_input.example.json"

    async def fake_structured_call(
        self: p.OpenAIResponsesGateway,
        *,
        stage: str,
        artifact_id: str,
        prompt: p.PromptSpec,
        payload: object,
        response_model: type[p.T],
        use_web: bool = False,
        allowed_domains: tuple[str, ...] = (),
        required_web: bool = False,
    ) -> p.ModelResult[p.T]:
        del self, artifact_id, prompt, use_web, allowed_domains, required_web
        assert isinstance(payload, dict)
        web_sources: tuple[p.WebSource, ...] = ()
        parsed: Any

        if response_model is p.HypothesisBuilderOutput:
            finding = next(
                item
                for item in payload["primary_actionable_findings"]
                if item["gene_or_marker"] == "MTAP"
            )
            parsed = p.HypothesisBuilderOutput(
                hypotheses=[
                    p.Hypothesis(
                        hypothesis_id="model_placeholder",
                        title="MTAP-loss metabolic vulnerability",
                        hypothesis_type="metabolic_vulnerability",
                        primary_finding_ids=[finding["finding_id"]],
                        supporting_finding_ids=[],
                        technical_limitation_ids=[],
                        biological_theme="MTAP loss and PRMT5 pathway dependence",
                        patient_specific_observation="MTAP copy-number loss was reported.",
                        mechanism_to_validate="MTAP loss may create an MTA-dependent PRMT5 vulnerability.",
                        potential_clinical_roles=["trial_biomarker"],
                        therapy_classes_to_research=[
                            "MTA-cooperative PRMT5 inhibitors"
                        ],
                        trial_search_required=True,
                        variant_interpretation_required=False,
                        confirmatory_questions=["Is MTAP loss protocol-confirmed?"],
                        critical_cautions=["Investigational rationale only."],
                        missing_context=["stage", "performance status"],
                        research_priority="high",
                        patient_evidence_ids=finding["patient_evidence_ids"],
                    )
                ]
            )

        elif response_model is p.ResearchPlanOutput:
            hypothesis = payload["biological_hypotheses"][0]
            parsed = p.ResearchPlanOutput(
                research_jobs=[
                    p.ResearchJob(
                        job_id="model_placeholder",
                        hypothesis_id=hypothesis["hypothesis_id"],
                        question_type="trial",
                        clinical_question="Which current MTAP-deleted solid-tumor trials are relevant?",
                        search_concepts=p.SearchConcepts(
                            disease=["solid tumor"],
                            histology=["sarcoma"],
                            genes_or_markers=["MTAP"],
                            alterations=["copy-number loss"],
                            pathways=["PRMT5"],
                            therapy_classes=["MTA-cooperative PRMT5 inhibitor"],
                            agents_already_known=[],
                            trial_ids_already_known=["NCT05094336"],
                        ),
                        source_roles_needed=["trial_record"],
                        preferred_sources=["ClinicalTrials.gov"],
                        minimum_evidence_level="official current trial record",
                        maximum_sources=1,
                        required_report_sections=["selected_links", "url_appendix"],
                        stop_condition="One current official trial record is verified.",
                        priority="high",
                    )
                ]
            )

        elif response_model is p.SourceDiscoveryOutput:
            job = payload["research_job"]
            trial_url = "https://clinicaltrials.gov/study/NCT05094336"
            parsed = p.SourceDiscoveryOutput(
                job_id=job["job_id"],
                searches_run=[
                    p.SearchRun(
                        query="MTAP deleted solid tumors NCT05094336",
                        purpose="Verify current official trial record.",
                    )
                ],
                candidate_sources=[
                    p.CandidateSource(
                        source_id="model_placeholder",
                        hypothesis_id=job["hypothesis_id"],
                        job_id=job["job_id"],
                        url=trial_url,
                        canonical_url=trial_url,
                        title="AMG 193 in MTAP-null solid tumors",
                        publisher="ClinicalTrials.gov",
                        source_type="trial_record",
                        publication_or_update_date="2026-07-01",
                        identifiers=p.SourceIdentifiers(nct_id="NCT05094336"),
                        source_role="trial_record",
                        why_candidate="Official biomarker-directed trial record.",
                        patient_anchor_matched=["MTAP loss"],
                        apparent_evidence_level="official clinical trial record",
                        requires_full_text=True,
                    )
                ],
                unresolved_questions=[],
            )
            web_sources = (
                p.WebSource(
                    url=trial_url,
                    title="AMG 193 in MTAP-null solid tumors",
                    type="web",
                ),
            )

        elif response_model is p.SourceExtraction:
            source = payload["target_source"]
            parsed = p.SourceExtraction(
                source_id=source["source_id"],
                source_identity=p.SourceIdentity(
                    title=source["title"],
                    url=source["url"],
                    publisher=source["publisher"],
                    source_type=source["source_type"],
                    publication_or_update_date="2026-07-01",
                    identifiers=p.SourceIdentifiers(nct_id="NCT05094336"),
                ),
                study_design="Phase 1/2 interventional trial",
                evidence_level="official trial record",
                population=p.PopulationExtraction(
                    tumor_types=["advanced solid tumors"],
                    histologies=[],
                    disease_setting=["advanced"],
                    stage=["advanced or metastatic"],
                    prior_therapy=[],
                    sample_size=None,
                    age_requirements=["adult"],
                    performance_status_requirements=["protocol defined"],
                    other_key_criteria=["MTAP-null tumor"],
                ),
                biomarker_definition=p.BiomarkerDefinition(
                    markers=["MTAP"],
                    required_alterations=["MTAP-null"],
                    excluded_alterations=[],
                    assay_requirements=["protocol-acceptable confirmation"],
                    thresholds=[],
                    confirmation_methods=[],
                ),
                interventions=["AMG 193"],
                comparators=[],
                mechanism_claims=["MTA-cooperative PRMT5 inhibition"],
                outcomes=p.OutcomeExtraction(),
                trial=p.TrialExtraction(
                    status="RECRUITING",
                    phase="Phase 1/2",
                    locations=["United States"],
                    last_update="2026-07-01",
                ),
                resistance_findings=[],
                monitoring_findings=[],
                authors_limitations=["Trial record does not establish benefit."],
                facts_not_reported=["patient-specific eligibility"],
                support_spans=[],
            )
            web_sources = (
                p.WebSource(url=source["url"], title=source["title"], type="web"),
            )

        elif response_model is p.SourceFitAssessment:
            source = payload["source_metadata"]
            hypothesis = payload["patient_hypothesis"]
            evidence_ids = payload["relevant_patient_findings"][0][
                "patient_evidence_ids"
            ]
            parsed = p.SourceFitAssessment(
                assessment_id="model_placeholder",
                source_id=source["source_id"],
                hypothesis_id=hypothesis["hypothesis_id"],
                appendix_title="ClinicalTrials.gov - AMG 193 MTAP-null trial",
                url=source["url"],
                source_type=source["source_type"],
                relevant_marker_or_pathway=["MTAP", "PRMT5", "AMG 193"],
                opening_assessment="Strong molecular trial-screening lead, not standard care.",
                standardized_scores=p.FitDimensions(
                    molecular_fit=p.FitDimension(
                        score=8, reason="The trial is MTAP directed."
                    ),
                    population_fit=p.FitDimension(
                        score=5, reason="Exact histology fit is unresolved."
                    ),
                    evidence_maturity=p.FitDimension(
                        score=3, reason="Official trial record, not efficacy evidence."
                    ),
                    standard_care_readiness=p.FitDimension(
                        score=1, reason="Investigational therapy."
                    ),
                    trial_screening_value=p.FitDimension(
                        score=8, reason="Biomarker-directed protocol."
                    ),
                ),
                bottom_line_score_rows=[
                    p.BottomLineScoreRow(
                        question="Does the tumor biology match the trial biomarker?",
                        strength_label="Strong",
                        score_min=8,
                        score_max=8,
                        why="MTAP loss aligns with the protocol concept.",
                    )
                ],
                why_the_fit_is_strong=["Direct MTAP biomarker logic."],
                matching_features=["MTAP copy-number loss"],
                mismatching_features=[],
                unknown_alignment_fields=["stage", "ECOG", "organ function"],
                what_would_make_the_patient_a_stronger_candidate=[
                    "Protocol-acceptable MTAP confirmation."
                ],
                what_weakens_the_case=["Eligibility context is incomplete."],
                my_read_on_this_case="Appropriate for protocol-level screening if clinically relevant.",
                clinical_framing_to_use="Confirm MTAP loss and review the current protocol.",
                do_not_say="The patient is eligible or should receive AMG 193.",
                say_instead="The biomarker supports a trial-screening discussion.",
                source_specific_follow_up=[
                    p.FollowUpAction(
                        follow_up="Confirm MTAP loss using a protocol-acceptable assay.",
                        why="The trial may require a specific biomarker definition.",
                        priority="high",
                    )
                ],
                source_specific_conclusion=[
                    "Strong trial-screening lead; investigational only."
                ],
                patient_evidence_ids=evidence_ids,
                external_support_claims=[
                    "The official record describes an MTAP-null solid-tumor trial."
                ],
                confidence="moderate",
            )

        elif response_model is p.TrialPrescreen:
            source = payload["source_metadata"]
            parsed = p.TrialPrescreen(
                prescreen_id="model_placeholder",
                source_id=source["source_id"],
                nct_id="NCT05094336",
                trial_status="RECRUITING",
                last_update="2026-07-01",
                biomarker_match=p.MatchAssessment(
                    status="POSSIBLE_MATCH",
                    reason="MTAP loss is reported but protocol confirmation is unresolved.",
                ),
                tumor_type_match=p.MatchAssessment(
                    status="UNKNOWN", reason="Histology cohort fit is unresolved."
                ),
                disease_setting_match=p.MatchAssessment(
                    status="UNKNOWN", reason="Stage and setting are missing."
                ),
                criterion_assessment=[],
                required_missing_data=["stage", "ECOG", "organ function"],
                site_and_geography=["United States"],
                screening_priority="medium",
                reason="Molecular logic warrants review; eligibility is unknown.",
                not_a_final_eligibility_determination=True,
            )

        elif response_model is p.HypothesisSynthesis:
            hypothesis = payload["patient_hypothesis"]
            assessment = payload["source_fit_assessments"][0]
            source_id = assessment["source_id"]
            evidence_ids = payload["relevant_patient_findings"][0][
                "patient_evidence_ids"
            ]
            parsed = p.HypothesisSynthesis(
                synthesis_id="model_placeholder",
                hypothesis_id=hypothesis["hypothesis_id"],
                hypothesis_status="partially_supported",
                executive_summary_statement="MTAP loss supports an investigational PRMT5 trial-screening discussion.",
                validated_biology=["MTAP loss is the patient-specific anchor."],
                cause_effect_chain=[
                    p.CauseEffectStep(
                        step=1,
                        statement="MTAP loss can create an MTA-associated PRMT5 vulnerability.",
                        evidence_type="mechanistic and trial rationale",
                        patient_evidence_ids=evidence_ids,
                        source_ids=[source_id],
                    )
                ],
                plain_english_explanation="The tumor may have a metabolic weak spot studied in clinical trials.",
                therapy_opportunities=[
                    p.TherapyOpportunity(
                        therapy_class="MTA-cooperative PRMT5 inhibitors",
                        example_agents=["AMG 193"],
                        molecular_interaction="Exploit the MTAP-loss/MTA state.",
                        clinical_use="investigational",
                        population_fit="Exact histology and eligibility remain unresolved.",
                        evidence_level="clinical trial record",
                        key_caveats=["Not standard care."],
                        source_ids=[source_id],
                    )
                ],
                confirmatory_tests=[
                    p.ConfirmatoryTestSynthesis(
                        test="Protocol-acceptable MTAP confirmation",
                        why_it_matters="The trial may require a specific biomarker definition.",
                        priority="high",
                        source_ids=[source_id],
                    )
                ],
                resistance_and_escape=[],
                monitoring_implications=[],
                active_trial_leads=["NCT05094336"],
                unsupported_or_overstated_options=[
                    "Do not present AMG 193 as proven standard care."
                ],
                population_alignment=p.PopulationAlignment(
                    matching=["MTAP-directed biomarker concept"],
                    mismatching=[],
                    unknown=["stage", "ECOG", "organ function"],
                ),
                limitations=["Patient eligibility is not established."],
                confidence="moderate",
                report_claims=[
                    p.ReportClaim(
                        claim_id="model_placeholder",
                        claim="MTAP loss supports protocol-level trial screening.",
                        patient_evidence_ids=evidence_ids,
                        external_source_ids=[source_id],
                        allowed_strength="investigational trial-screening rationale",
                    )
                ],
            )

        elif response_model is p.ReportDraft:
            source = payload["selected_sources"][0]
            finding = payload["primary_findings"][0]
            synthesis = payload["hypothesis_syntheses"][0]
            source_id = source["source_id"]
            evidence_ids = finding["patient_evidence_ids"]
            parsed = p.ReportDraft(
                report_draft_id="model_placeholder",
                cover_metadata=p.CoverMetadata(
                    title="Precision Oncology Actionable Packet",
                    subtitle="Professional summary for clinicians and patients",
                    purpose_statements=[
                        "Translate actionable findings into a structured clinical summary."
                    ],
                    source_label="Uploaded review packet",
                    report_type="NGS",
                    disease_or_tumor_type="Example sarcoma",
                    specimen_context="Soft tissue",
                    overall_validation_status="Needs Review",
                    important_note="Educational support only.",
                ),
                executive_summary=p.ExecutiveSummarySection(
                    paragraphs=[
                        p.EvidenceParagraph(
                            text=synthesis["executive_summary_statement"],
                            patient_evidence_ids=evidence_ids,
                            source_ids=[source_id],
                        )
                    ],
                    top_takeaway="Confirm MTAP loss and review investigational trials.",
                    most_trial_relevant_finding="MTAP loss",
                    most_likely_to_require_confirmation="MTAP loss",
                    most_important_technical_caveat="TAF1 low coverage",
                ),
                key_findings=[
                    p.KeyFindingRow(
                        row_id="model_placeholder",
                        marker_or_finding=finding["display_label"],
                        reasoning_domain="Tumor biology / trial biomarker",
                        what_it_means="MTAP loss was reported.",
                        why_it_matters="It can support PRMT5-pathway trial reasoning.",
                        actionability="Investigational trial-screening rationale.",
                        next_step="Confirm the biomarker and review eligibility.",
                        patient_evidence_ids=evidence_ids,
                        source_ids=[source_id],
                    )
                ],
                other_findings=[],
                cause_effect=[
                    p.CauseEffectRow(
                        row_id="model_placeholder",
                        finding="MTAP loss",
                        mechanism_chain="MTAP loss -> MTA-associated state -> PRMT5-pathway vulnerability.",
                        plain_english="The tumor may have a metabolic weak spot studied in trials.",
                        patient_evidence_ids=evidence_ids,
                        source_ids=[source_id],
                    )
                ],
                therapy_options=[
                    p.TherapyOptionRow(
                        row_id="model_placeholder",
                        marker_or_target="MTAP loss",
                        therapy_class="MTA-cooperative PRMT5 inhibitors",
                        example_agents=["AMG 193"],
                        molecular_interaction="Exploit MTAP-loss/MTA biology.",
                        key_caveats=["Investigational; eligibility unresolved."],
                        status="High-interest trial strategy",
                        patient_evidence_ids=evidence_ids,
                        source_ids=[source_id],
                    )
                ],
                practical_readout=[
                    "The strongest opportunity is protocol-level MTAP trial screening."
                ],
                resistance_escape=[],
                follow_up_tests=[
                    p.FollowUpTestRow(
                        row_id="model_placeholder",
                        recommended_next_step="Confirm MTAP loss using an acceptable assay.",
                        why_it_matters="Trial protocols may define the biomarker precisely.",
                        priority="high",
                        patient_evidence_ids=evidence_ids,
                        source_ids=[source_id],
                    )
                ],
                phenotypic_events=[
                    p.PhenotypicEventRow(
                        row_id="model_placeholder",
                        clinical_event="Radiographic progression",
                        why_it_matters="Progression can justify repeat profiling.",
                        urgency="high",
                        recommended_test="Repeat tissue or liquid profiling as clinically appropriate.",
                    )
                ],
                limitations=[
                    "Stage, treatment setting, performance status, and organ function are unresolved."
                ],
                selected_links=[
                    p.SelectedLinkRow(
                        row_id="model_placeholder",
                        source_id=source_id,
                        title=source["title"],
                        url=source["url"],
                        why_it_is_useful="Official current trial record.",
                        source_type=source["source_type"],
                        hypothesis_id=source["hypothesis_ids"][0],
                    )
                ],
                bottom_line=[
                    "This is a trial-screening rationale, not a treatment recommendation."
                ],
                url_fit_appendix=p.URLFitAppendixOverview(
                    data_basis_and_rules=[
                        "Separate molecular rationale from treatment readiness."
                    ],
                    scoring_guide="9-10 very strong; 1-3 weak or not actionable.",
                    source_index=[],
                    source_assessment_ids=[],
                ),
            )

        elif response_model is p.CrossSourceSynthesis:
            source_id = payload["source_assessments"][0]["source_id"]
            parsed = p.CrossSourceSynthesis(
                synthesis_id="model_placeholder",
                summary="MTAP-directed evidence supports trial screening, not standard care.",
                themes=[
                    p.CrossSourceTheme(
                        theme="MTAP / PRMT5",
                        cross_source_conclusion="Confirm MTAP loss and review current trials.",
                        evidence_maturity="investigational",
                        clinical_role="trial screening",
                    )
                ],
                practical_bottom_line=[
                    "Protocol eligibility and patient context remain unresolved."
                ],
                source_ids=[source_id],
            )

        else:  # pragma: no cover - a new stage should make this test fail loudly
            raise AssertionError(f"Unexpected response model: {response_model}")

        assert isinstance(parsed, response_model)
        return p.ModelResult(
            parsed=parsed,
            response_id=f"resp_{stage}",
            model="gpt-5.6-luna",
            usage={"input_tokens": 10, "output_tokens": 10},
            web_sources=web_sources,
            cache_hit=False,
        )

    monkeypatch.setattr(
        p.OpenAIResponsesGateway,
        "structured_call",
        fake_structured_call,
    )

    config = p.PipelineConfig(
        api_key="sk-test",
        model="gpt-5.6-luna",
        reasoning_effort="medium",
        output_dir=tmp_path,
        max_concurrency=2,
        max_research_jobs=2,
        max_sources_per_job=1,
        max_sources_per_hypothesis=2,
        max_sources_total=2,
        strict_source_verification=True,
        run_llm_validators=False,
    )

    result = asyncio.run(
        p.run_pipeline(
            input_path=input_path,
            config=config,
        )
    )
    assert result.final_json_path is not None
    final = json.loads(result.final_json_path.read_text())

    assert final["schema_version"] == p.OUTPUT_SCHEMA_VERSION
    assert final["document_flow"][0] == p.SECTION_IDS["cover"]
    assert final["document_flow"][-1] == p.SECTION_IDS["urls_assessed"]
    assert len(final["sources_by_id"]) == 1
    assert len(final["source_fit_assessments_by_id"]) == 1
    assert len(final["trial_prescreens_by_id"]) == 1
    assert any(
        section["content_type"] == "url_candidate_fit_assessment"
        for section in final["sections_by_id"].values()
    )
    urls = final["sections_by_id"][p.SECTION_IDS["urls_assessed"]]["payload"][
        "urls_assessed"
    ]
    assert urls[0]["url"] == "https://clinicaltrials.gov/study/NCT05094336"
