"""Deterministic equivalence decision domain over mention-concept pairs."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from drilling_knowledge.common.ids import EntityId
from drilling_knowledge.extraction.domain import ExtractionSourceTrace


class EquivalenceDecisionStatus(StrEnum):
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    PENDING = "PENDING"


@dataclass(frozen=True, slots=True)
class EquivalenceDecision:
    decision_id: EntityId
    mention_id: EntityId
    catalog_entity_id: EntityId
    status: EquivalenceDecisionStatus
    evidence: str
    rationale: str
    decided_by: str
    decided_at: datetime
    source_trace: ExtractionSourceTrace
    revision: int

    def __post_init__(self) -> None:
        evidence = self.evidence.strip()
        rationale = self.rationale.strip()
        decided_by = self.decided_by.strip()
        if not evidence:
            raise ValueError("EquivalenceDecision.evidence cannot be empty")
        if not rationale:
            raise ValueError("EquivalenceDecision.rationale cannot be empty")
        if not decided_by:
            raise ValueError("EquivalenceDecision.decided_by cannot be empty")
        if self.revision < 1:
            raise ValueError("EquivalenceDecision.revision must be >= 1")
        object.__setattr__(self, "evidence", evidence)
        object.__setattr__(self, "rationale", rationale)
        object.__setattr__(self, "decided_by", decided_by)
