"""Repository contracts for conflict resolution runs."""

from __future__ import annotations

from typing import Protocol

from drilling_knowledge.assertions.conflict_resolution.domain import (
    AssertionConflictContext,
    AssertionConflictMember,
    AssertionConflictSet,
    ConflictResolutionRun,
    ConflictReviewQueueItem,
)
from drilling_knowledge.assertions.domain import AssertionEvidenceLink
from drilling_knowledge.common.ids import EntityId, RunId


class ConflictResolutionRunRepository(Protocol):
    def get_run(self, run_id: RunId) -> ConflictResolutionRun | None:
        ...

    def list_runs(self) -> tuple[ConflictResolutionRun, ...]:
        ...

    def list_conflict_sets(self, run_id: RunId) -> tuple[AssertionConflictSet, ...]:
        ...

    def list_members(self, run_id: RunId) -> tuple[AssertionConflictMember, ...]:
        ...

    def list_contexts(self, run_id: RunId) -> tuple[AssertionConflictContext, ...]:
        ...

    def list_review_queue_items(self, run_id: RunId) -> tuple[ConflictReviewQueueItem, ...]:
        ...

    def list_evidence_links(self, run_id: RunId) -> tuple[AssertionEvidenceLink, ...]:
        ...

    def get_conflict_set(self, conflict_set_id: EntityId) -> AssertionConflictSet | None:
        ...

    def append_run(self, run: ConflictResolutionRun) -> "ConflictResolutionRunRepository":
        ...