"""Deterministic services for explicit equivalence decisions."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from drilling_knowledge.common.ids import EntityId
from drilling_knowledge.equivalence.domain import EquivalenceDecision, EquivalenceDecisionStatus
from drilling_knowledge.equivalence.repositories.contracts import EquivalenceDecisionRepository
from drilling_knowledge.extraction.domain import ExtractionSourceTrace


@dataclass(slots=True)
class EquivalenceDecisionService:
    repository: EquivalenceDecisionRepository

    @classmethod
    def create(cls, repository: EquivalenceDecisionRepository) -> "EquivalenceDecisionService":
        return cls(repository=repository)

    def record(
        self,
        *,
        mention_id: EntityId,
        catalog_entity_id: EntityId,
        status: EquivalenceDecisionStatus,
        evidence: str,
        rationale: str,
        decided_by: str,
        decided_at: datetime,
        source_trace: ExtractionSourceTrace,
    ) -> EquivalenceDecision:
        active = self.repository.get_active(mention_id, catalog_entity_id)
        if active is not None and self._matches(active, status, evidence, rationale, decided_by, decided_at, source_trace):
            return active

        revision = 1 if active is None else active.revision + 1
        decision = EquivalenceDecision(
            decision_id=self._decision_id(
                mention_id,
                catalog_entity_id,
                revision,
                status,
                evidence,
                rationale,
                decided_by,
                decided_at,
                source_trace,
            ),
            mention_id=mention_id,
            catalog_entity_id=catalog_entity_id,
            status=status,
            evidence=evidence,
            rationale=rationale,
            decided_by=decided_by,
            decided_at=decided_at,
            source_trace=source_trace,
            revision=revision,
        )
        self.repository = self.repository.append(decision)
        return decision

    def get_active(self, mention_id: EntityId, catalog_entity_id: EntityId) -> EquivalenceDecision | None:
        return self.repository.get_active(mention_id, catalog_entity_id)

    def list_history(self, mention_id: EntityId, catalog_entity_id: EntityId) -> tuple[EquivalenceDecision, ...]:
        return self.repository.list_history(mention_id, catalog_entity_id)

    def list_all(self) -> tuple[EquivalenceDecision, ...]:
        return self.repository.list_all()

    def _decision_id(
        self,
        mention_id: EntityId,
        catalog_entity_id: EntityId,
        revision: int,
        status: EquivalenceDecisionStatus,
        evidence: str,
        rationale: str,
        decided_by: str,
        decided_at: datetime,
        source_trace: ExtractionSourceTrace,
    ) -> EntityId:
        return EntityId.from_seed(
            "equivalence.decision",
            "|".join(
                (
                    str(mention_id),
                    str(catalog_entity_id),
                    str(revision),
                    status.value,
                    evidence.strip(),
                    rationale.strip(),
                    decided_by.strip(),
                    decided_at.isoformat(),
                    self._source_trace_key(source_trace),
                )
            ),
        )

    def _matches(
        self,
        decision: EquivalenceDecision,
        status: EquivalenceDecisionStatus,
        evidence: str,
        rationale: str,
        decided_by: str,
        decided_at: datetime,
        source_trace: ExtractionSourceTrace,
    ) -> bool:
        return (
            decision.status == status
            and decision.evidence == evidence.strip()
            and decision.rationale == rationale.strip()
            and decision.decided_by == decided_by.strip()
            and decision.decided_at == decided_at
            and decision.source_trace == source_trace
        )

    def _source_trace_key(self, source_trace: ExtractionSourceTrace) -> str:
        return "|".join(
            (
                str(source_trace.page_number),
                str(source_trace.section_id),
                str(source_trace.table_id),
                str(source_trace.figure_id),
                str(source_trace.paragraph_ordinal),
                str(source_trace.start_offset),
                str(source_trace.end_offset),
            )
        )
