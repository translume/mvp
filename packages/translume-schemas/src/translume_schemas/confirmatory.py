from __future__ import annotations

from translume_schemas.base import TranslumeBaseModel


class ConfirmatoryTest(TranslumeBaseModel):
    test_id: str
    question: str
    why_it_matters: str
    positive_interpretation: str
    negative_interpretation: str
    priority: str
    evidence_gap: str
    source_claim_ids: list[str] = []


class ConfirmatoryTestingOutput(TranslumeBaseModel):
    artifact_id: str
    tests: list[ConfirmatoryTest]
    must_not_assume: list[str] = []
