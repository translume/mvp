from __future__ import annotations

from pydantic import Field

from translume_schemas.base import TranslumeBaseModel
from translume_schemas.model_calls import ModelCallRecord


class MedeaSourceReference(TranslumeBaseModel):
    """Real retrieved bibliographic metadata behind an OpenScholar citation."""

    citation_index: int
    source_id: str
    provider: str
    title: str
    url: str
    year: str | None = None
    doi: str | None = None
    pmid: str | None = None
    abstract_sha256: str


class MedeaLiteratureSearch(TranslumeBaseModel):
    """An actual bounded public-literature query, including source failures."""

    provider: str
    query: str
    status: str
    returned_count: int
    hit_count: int | None = None
    error_code: str | None = None


class MedeaPaperJudgement(TranslumeBaseModel):
    """A recorded relevance decision about one actually retrieved abstract."""

    source_id: str
    relevant: bool
    reason: str
    response_id: str | None = None


class MedeaReasoningArtifact(TranslumeBaseModel):
    artifact_id: str
    reasoning_mode: str
    summary: str
    supported_hypotheses: list[str]
    weakened_hypotheses: list[str]
    warnings: list[str] = Field(default_factory=list)
    requires_human_review: bool = True
    decision_support_role: str = "hypothesis_support_only"
    downstream_uses: list[str] = Field(default_factory=list)
    source_references: list[MedeaSourceReference] = Field(default_factory=list)
    literature_searches: list[MedeaLiteratureSearch] = Field(default_factory=list)
    model_call_ids: list[str] = Field(default_factory=list)
    model_provider: str | None = None
    model_name: str | None = None
    model_reasoning_mode: str | None = None
    paper_judgements: list[MedeaPaperJudgement] = Field(default_factory=list)
    model_calls: list[ModelCallRecord] = Field(default_factory=list)
