"""In-memory repository for conflict resolution runs."""

from __future__ import annotations

from dataclasses import dataclass, field

from drilling_knowledge.assertions.conflict_resolution.domain import (
    AssertionConflictContext,
    AssertionConflictMember,
    AssertionConflictSet,
    ConflictDecisionType,
    ConflictMemberRole,
    ConflictResolutionRun,
    ConflictReviewQueueItem,
)
from drilling_knowledge.assertions.conflict_resolution.repositories.contracts import ConflictResolutionRunRepository
from drilling_knowledge.assertions.domain import AssertionEvidenceLink
from drilling_knowledge.common.exceptions import ConflictError
from drilling_knowledge.common.ids import EntityId, RunId


@dataclass(frozen=True, slots=True)
class InMemoryConflictResolutionRunRepository(ConflictResolutionRunRepository):
    runs: tuple[ConflictResolutionRun, ...] = ()
    _runs_by_id: dict[RunId, ConflictResolutionRun] = field(init=False, default_factory=dict)
    _sets_by_run: dict[RunId, tuple[AssertionConflictSet, ...]] = field(init=False, default_factory=dict)
    _members_by_run: dict[RunId, tuple[AssertionConflictMember, ...]] = field(init=False, default_factory=dict)
    _contexts_by_run: dict[RunId, tuple[AssertionConflictContext, ...]] = field(init=False, default_factory=dict)
    _review_items_by_run: dict[RunId, tuple[ConflictReviewQueueItem, ...]] = field(init=False, default_factory=dict)
    _links_by_run: dict[RunId, tuple[AssertionEvidenceLink, ...]] = field(init=False, default_factory=dict)
    _sets_by_id: dict[EntityId, AssertionConflictSet] = field(init=False, default_factory=dict)

    def __post_init__(self) -> None:
        runs_by_id: dict[RunId, ConflictResolutionRun] = {}
        sets_by_run: dict[RunId, tuple[AssertionConflictSet, ...]] = {}
        members_by_run: dict[RunId, tuple[AssertionConflictMember, ...]] = {}
        contexts_by_run: dict[RunId, tuple[AssertionConflictContext, ...]] = {}
        review_items_by_run: dict[RunId, tuple[ConflictReviewQueueItem, ...]] = {}
        links_by_run: dict[RunId, tuple[AssertionEvidenceLink, ...]] = {}
        sets_by_id: dict[EntityId, AssertionConflictSet] = {}
        ordered = tuple(sorted(self.runs, key=self._sort_key))
        for run in ordered:
            existing = runs_by_id.get(run.run_id)
            if existing is not None and existing != run:
                raise ConflictError(
                    code="duplicate_conflict_resolution_run",
                    message="A different conflict resolution run already exists for the same run id",
                    context={"run_id": str(run.run_id)},
                )
            self._validate_references(run)
            runs_by_id[run.run_id] = run
            sets_by_run[run.run_id] = run.conflict_sets
            members_by_run[run.run_id] = run.members
            contexts_by_run[run.run_id] = run.contexts
            review_items_by_run[run.run_id] = run.review_queue_items
            links_by_run[run.run_id] = run.evidence_links
            for conflict_set in run.conflict_sets:
                existing_set = sets_by_id.get(conflict_set.conflict_set_id)
                if existing_set is not None and existing_set != conflict_set:
                    raise ConflictError(
                        code="duplicate_assertion_conflict_set",
                        message="A different conflict set already exists for the same conflict_set_id",
                        context={"conflict_set_id": str(conflict_set.conflict_set_id)},
                    )
                sets_by_id[conflict_set.conflict_set_id] = conflict_set
        object.__setattr__(self, "runs", ordered)
        object.__setattr__(self, "_runs_by_id", runs_by_id)
        object.__setattr__(self, "_sets_by_run", sets_by_run)
        object.__setattr__(self, "_members_by_run", members_by_run)
        object.__setattr__(self, "_contexts_by_run", contexts_by_run)
        object.__setattr__(self, "_review_items_by_run", review_items_by_run)
        object.__setattr__(self, "_links_by_run", links_by_run)
        object.__setattr__(self, "_sets_by_id", sets_by_id)

    def get_run(self, run_id: RunId) -> ConflictResolutionRun | None:
        return self._runs_by_id.get(run_id)

    def list_runs(self) -> tuple[ConflictResolutionRun, ...]:
        return self.runs

    def list_conflict_sets(self, run_id: RunId) -> tuple[AssertionConflictSet, ...]:
        return self._sets_by_run.get(run_id, ())

    def list_members(self, run_id: RunId) -> tuple[AssertionConflictMember, ...]:
        return self._members_by_run.get(run_id, ())

    def list_contexts(self, run_id: RunId) -> tuple[AssertionConflictContext, ...]:
        return self._contexts_by_run.get(run_id, ())

    def list_review_queue_items(self, run_id: RunId) -> tuple[ConflictReviewQueueItem, ...]:
        return self._review_items_by_run.get(run_id, ())

    def list_evidence_links(self, run_id: RunId) -> tuple[AssertionEvidenceLink, ...]:
        return self._links_by_run.get(run_id, ())

    def get_conflict_set(self, conflict_set_id: EntityId) -> AssertionConflictSet | None:
        return self._sets_by_id.get(conflict_set_id)

    def append_run(self, run: ConflictResolutionRun) -> "InMemoryConflictResolutionRunRepository":
        existing = self._runs_by_id.get(run.run_id)
        if existing is not None:
            if existing != run:
                raise ConflictError(
                    code="duplicate_conflict_resolution_run",
                    message="A different conflict resolution run already exists for the same run id",
                    context={"run_id": str(run.run_id)},
                )
            return self
        return InMemoryConflictResolutionRunRepository(self.runs + (run,))

    def _validate_references(self, run: ConflictResolutionRun) -> None:
        set_ids = {conflict_set.conflict_set_id for conflict_set in run.conflict_sets}
        member_ids: set[EntityId] = set()
        context_ids: set[EntityId] = set()
        link_ids: set[EntityId] = set()
        review_set_ids = {item.conflict_set_id for item in run.review_queue_items}

        for link in run.evidence_links:
            if link.link_id in link_ids:
                raise ConflictError(
                    code="duplicate_conflict_evidence_link",
                    message="Conflict resolution runs cannot reuse the same evidence link id",
                    context={"link_id": str(link.link_id)},
                )
            link_ids.add(link.link_id)

        for member in run.members:
            if member.member_id in member_ids:
                raise ConflictError(
                    code="duplicate_conflict_member",
                    message="Conflict members cannot reuse the same member_id",
                    context={"member_id": str(member.member_id)},
                )
            member_ids.add(member.member_id)
            if member.conflict_set_id not in set_ids:
                raise ConflictError(
                    code="conflict_member_missing_set",
                    message="Conflict member references an unknown conflict set id",
                    context={"run_id": str(run.run_id), "conflict_set_id": str(member.conflict_set_id)},
                )

        for context in run.contexts:
            if context.context_id in context_ids:
                raise ConflictError(
                    code="duplicate_conflict_context",
                    message="Conflict contexts cannot reuse the same context id",
                    context={"context_id": str(context.context_id)},
                )
            context_ids.add(context.context_id)
            if context.conflict_set_id not in set_ids:
                raise ConflictError(
                    code="conflict_context_missing_set",
                    message="Conflict context references an unknown conflict set id",
                    context={"run_id": str(run.run_id), "conflict_set_id": str(context.conflict_set_id)},
                )
            if not set(context.member_ids).issubset(member_ids):
                raise ConflictError(
                    code="conflict_context_missing_member",
                    message="Conflict context references an unknown member id",
                    context={"run_id": str(run.run_id), "context_id": str(context.context_id)},
                )

        for conflict_set in run.conflict_sets:
            set_member_ids = {member.member_id for member in conflict_set.members}
            actual_member_ids = {member.member_id for member in run.members if member.conflict_set_id == conflict_set.conflict_set_id}
            if set_member_ids != actual_member_ids:
                raise ConflictError(
                    code="conflict_set_member_mismatch",
                    message="Conflict set members must match the persisted member collection",
                    context={"run_id": str(run.run_id), "conflict_set_id": str(conflict_set.conflict_set_id)},
                )
            set_context_ids = {context.context_id for context in conflict_set.contexts}
            actual_context_ids = {context.context_id for context in run.contexts if context.conflict_set_id == conflict_set.conflict_set_id}
            if set_context_ids != actual_context_ids:
                raise ConflictError(
                    code="conflict_set_context_mismatch",
                    message="Conflict set contexts must match the persisted context collection",
                    context={"run_id": str(run.run_id), "conflict_set_id": str(conflict_set.conflict_set_id)},
                )
            if conflict_set.requires_human_review and conflict_set.conflict_set_id not in review_set_ids:
                raise ConflictError(
                    code="conflict_set_missing_review_item",
                    message="Conflict sets requiring review must have a persisted review queue item",
                    context={"run_id": str(run.run_id), "conflict_set_id": str(conflict_set.conflict_set_id)},
                )
            if not conflict_set.requires_human_review and conflict_set.conflict_set_id in review_set_ids:
                raise ConflictError(
                    code="conflict_set_unexpected_review_item",
                    message="Closed conflict sets without review escalation cannot persist a review queue item",
                    context={"run_id": str(run.run_id), "conflict_set_id": str(conflict_set.conflict_set_id)},
                )
            if conflict_set.decision_type == ConflictDecisionType.ACCEPTED_MEMBER:
                if len([member for member in conflict_set.members if member.member_role == ConflictMemberRole.ACCEPTED_MEMBER]) != 1:
                    raise ConflictError(
                        code="accepted_member_resolution_invalid",
                        message="Accepted-member resolutions must persist exactly one accepted member",
                        context={"run_id": str(run.run_id), "conflict_set_id": str(conflict_set.conflict_set_id)},
                    )
            if conflict_set.decision_type == ConflictDecisionType.REJECTED_MEMBER:
                if len([member for member in conflict_set.members if member.member_role == ConflictMemberRole.REJECTED_MEMBER]) < 1:
                    raise ConflictError(
                        code="rejected_member_resolution_invalid",
                        message="Rejected-member resolutions must persist at least one rejected member",
                        context={"run_id": str(run.run_id), "conflict_set_id": str(conflict_set.conflict_set_id)},
                    )

        persisted_links_by_id = {link.link_id: link for link in run.evidence_links}
        for member in run.members:
            link_ids_for_assertion = set(member.source_assertion.evidence_link_ids)
            if not link_ids_for_assertion.issubset(persisted_links_by_id):
                raise ConflictError(
                    code="conflict_member_missing_evidence_link",
                    message="Conflict member assertions must preserve all evidence links in the conflict resolution run",
                    context={"run_id": str(run.run_id), "member_id": str(member.member_id)},
                )

    @staticmethod
    def _sort_key(run: ConflictResolutionRun) -> tuple[str, str]:
        return (run.finished_at.isoformat(), str(run.run_id))