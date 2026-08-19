"""In-memory repositories for evidence assertion runs."""

from __future__ import annotations

from dataclasses import dataclass, field

from drilling_knowledge.assertions.domain import AssertionEvidenceLink, AssertionGenerationRun, AssertionValidationLog, EvidenceAssertion
from drilling_knowledge.assertions.repositories.contracts import AssertionGenerationRunRepository
from drilling_knowledge.common.exceptions import ConflictError
from drilling_knowledge.common.ids import EntityId, RunId


@dataclass(frozen=True, slots=True)
class InMemoryAssertionGenerationRunRepository(AssertionGenerationRunRepository):
    runs: tuple[AssertionGenerationRun, ...] = ()
    _runs_by_id: dict[RunId, AssertionGenerationRun] = field(init=False, default_factory=dict)
    _assertions_by_run: dict[RunId, tuple[EvidenceAssertion, ...]] = field(init=False, default_factory=dict)
    _links_by_run: dict[RunId, tuple[AssertionEvidenceLink, ...]] = field(init=False, default_factory=dict)
    _logs_by_run: dict[RunId, tuple[AssertionValidationLog, ...]] = field(init=False, default_factory=dict)
    _assertions_by_id: dict[EntityId, EvidenceAssertion] = field(init=False, default_factory=dict)

    def __post_init__(self) -> None:
        runs_by_id: dict[RunId, AssertionGenerationRun] = {}
        assertions_by_run: dict[RunId, tuple[EvidenceAssertion, ...]] = {}
        links_by_run: dict[RunId, tuple[AssertionEvidenceLink, ...]] = {}
        logs_by_run: dict[RunId, tuple[AssertionValidationLog, ...]] = {}
        assertions_by_id: dict[EntityId, EvidenceAssertion] = {}
        ordered = tuple(sorted(self.runs, key=self._sort_key))
        for run in ordered:
            existing = runs_by_id.get(run.run_id)
            if existing is not None and existing != run:
                raise ConflictError(
                    code="duplicate_assertion_generation_run",
                    message="A different assertion generation run already exists for the same run id",
                    context={"run_id": str(run.run_id)},
                )
            self._validate_references(run)
            runs_by_id[run.run_id] = run
            assertions_by_run[run.run_id] = run.assertions
            links_by_run[run.run_id] = run.evidence_links
            logs_by_run[run.run_id] = run.validation_logs
            for assertion in run.assertions:
                existing_assertion = assertions_by_id.get(assertion.assertion_id)
                if existing_assertion is not None and existing_assertion != assertion:
                    raise ConflictError(
                        code="duplicate_evidence_assertion",
                        message="A different evidence assertion already exists for the same assertion id",
                        context={"assertion_id": str(assertion.assertion_id)},
                    )
                assertions_by_id[assertion.assertion_id] = assertion
            self._validate_lifecycle_graph(assertions_by_id)
        object.__setattr__(self, "runs", ordered)
        object.__setattr__(self, "_runs_by_id", runs_by_id)
        object.__setattr__(self, "_assertions_by_run", assertions_by_run)
        object.__setattr__(self, "_links_by_run", links_by_run)
        object.__setattr__(self, "_logs_by_run", logs_by_run)
        object.__setattr__(self, "_assertions_by_id", assertions_by_id)

    def get_run(self, run_id: RunId) -> AssertionGenerationRun | None:
        return self._runs_by_id.get(run_id)

    def list_runs(self) -> tuple[AssertionGenerationRun, ...]:
        return self.runs

    def list_assertions(self, run_id: RunId) -> tuple[EvidenceAssertion, ...]:
        return self._assertions_by_run.get(run_id, ())

    def list_evidence_links(self, run_id: RunId) -> tuple[AssertionEvidenceLink, ...]:
        return self._links_by_run.get(run_id, ())

    def list_validation_logs(self, run_id: RunId) -> tuple[AssertionValidationLog, ...]:
        return self._logs_by_run.get(run_id, ())

    def get_assertion(self, assertion_id: EntityId) -> EvidenceAssertion | None:
        return self._assertions_by_id.get(assertion_id)

    def append_run(self, run: AssertionGenerationRun) -> "InMemoryAssertionGenerationRunRepository":
        existing = self._runs_by_id.get(run.run_id)
        if existing is not None:
            if existing != run:
                raise ConflictError(
                    code="duplicate_assertion_generation_run",
                    message="A different assertion generation run already exists for the same run id",
                    context={"run_id": str(run.run_id)},
                )
            return self
        return InMemoryAssertionGenerationRunRepository(self.runs + (run,))

    def _validate_references(self, run: AssertionGenerationRun) -> None:
        assertion_ids = {assertion.assertion_id for assertion in run.assertions}
        hypothesis_ids = {assertion.source_hypothesis_id for assertion in run.assertions}
        candidate_ids = {assertion.source_candidate_id for assertion in run.assertions}
        links_by_assertion: dict[EntityId, list[AssertionEvidenceLink]] = {}
        support_ids_by_assertion: dict[EntityId, set[EntityId]] = {}
        support_ids_by_hypothesis: dict[EntityId, set[EntityId]] = {}
        for assertion in run.assertions:
            support_ids = {support.support_id for support in assertion.source_supports}
            support_ids_by_assertion[assertion.assertion_id] = support_ids
            support_ids_by_hypothesis.setdefault(assertion.source_hypothesis_id, set()).update(support_ids)
            if not assertion.evidence_link_ids:
                raise ConflictError(
                    code="assertion_missing_links",
                    message="Evidence assertions must reference at least one evidence link",
                    context={"run_id": str(run.run_id), "assertion_id": str(assertion.assertion_id)},
                )
        for link in run.evidence_links:
            links_by_assertion.setdefault(link.assertion_id, []).append(link)
            if link.assertion_id not in assertion_ids:
                raise ConflictError(
                    code="assertion_link_missing_assertion",
                    message="Assertion evidence link references an unknown assertion id",
                    context={"run_id": str(run.run_id), "assertion_id": str(link.assertion_id)},
                )
            if link.hypothesis_id not in hypothesis_ids:
                raise ConflictError(
                    code="assertion_link_missing_hypothesis",
                    message="Assertion evidence link references an unknown hypothesis id",
                    context={"run_id": str(run.run_id), "hypothesis_id": str(link.hypothesis_id)},
                )
            assertion = self._assertions_by_id.get(link.assertion_id)
            if assertion is None:
                assertion = next((item for item in run.assertions if item.assertion_id == link.assertion_id), None)
            if assertion is None:
                raise ConflictError(
                    code="assertion_link_missing_assertion_context",
                    message="Assertion evidence link could not resolve assertion context",
                    context={"run_id": str(run.run_id), "assertion_id": str(link.assertion_id)},
                )
            if assertion.source_candidate_id not in candidate_ids:
                raise ConflictError(
                    code="assertion_link_missing_candidate",
                    message="Assertion evidence link references an unknown source candidate id",
                    context={"run_id": str(run.run_id), "source_candidate_id": str(assertion.source_candidate_id)},
                )
            if link.support_id not in support_ids_by_hypothesis.get(link.hypothesis_id, set()):
                raise ConflictError(
                    code="assertion_link_missing_support",
                    message="Assertion evidence link references an unknown semantic support id",
                    context={"run_id": str(run.run_id), "support_id": str(link.support_id), "hypothesis_id": str(link.hypothesis_id)},
                )
            if link.support_id not in support_ids_by_assertion.get(link.assertion_id, set()):
                raise ConflictError(
                    code="assertion_link_support_mismatch",
                    message="Assertion evidence link support id does not belong to the linked assertion",
                    context={"run_id": str(run.run_id), "support_id": str(link.support_id), "assertion_id": str(link.assertion_id)},
                )
            if link.document_id is None or link.document_version_id is None or link.fragment_id is None:
                raise ConflictError(
                    code="assertion_link_missing_provenance",
                    message="Assertion evidence links require complete provenance fields",
                    context={"run_id": str(run.run_id), "assertion_id": str(link.assertion_id)},
                )
        for assertion in run.assertions:
            linked = tuple(links_by_assertion.get(assertion.assertion_id, ()))
            if not linked:
                raise ConflictError(
                    code="assertion_missing_persisted_links",
                    message="Evidence assertions cannot be persisted without evidence links",
                    context={"run_id": str(run.run_id), "assertion_id": str(assertion.assertion_id)},
                )
            linked_ids = {link.link_id for link in linked}
            if linked_ids != set(assertion.evidence_link_ids):
                raise ConflictError(
                    code="assertion_link_set_mismatch",
                    message="Evidence assertion link ids must match the persisted evidence links",
                    context={"run_id": str(run.run_id), "assertion_id": str(assertion.assertion_id)},
                )
            if len(linked_ids) != len(linked):
                raise ConflictError(
                    code="duplicate_evidence_link_id",
                    message="Evidence assertion links cannot reuse the same link id",
                    context={"run_id": str(run.run_id), "assertion_id": str(assertion.assertion_id)},
                )
            support_ids = {link.support_id for link in linked}
            if len(support_ids) != len(linked):
                raise ConflictError(
                    code="duplicate_support_id",
                    message="Evidence assertion links cannot reuse the same semantic support id",
                    context={"run_id": str(run.run_id), "assertion_id": str(assertion.assertion_id)},
                )
            expected_document_id, expected_version_id, expected_fragment_id, expected_original, expected_normalized, expected_trace = self._expected_provenance(assertion)
            for link in linked:
                if link.hypothesis_id != assertion.source_hypothesis_id:
                    raise ConflictError(
                        code="assertion_link_hypothesis_mismatch",
                        message="Evidence assertion link hypothesis id must match the owning assertion",
                        context={"run_id": str(run.run_id), "assertion_id": str(assertion.assertion_id), "hypothesis_id": str(link.hypothesis_id)},
                    )
                if (
                    link.document_id != expected_document_id
                    or link.document_version_id != expected_version_id
                    or link.fragment_id != expected_fragment_id
                    or link.original_text != expected_original
                    or link.normalized_text != expected_normalized
                    or link.source_trace != expected_trace
                ):
                    raise ConflictError(
                        code="assertion_link_provenance_mismatch",
                        message="Evidence assertion links must preserve the exact provenance of the source hypothesis",
                        context={"run_id": str(run.run_id), "assertion_id": str(assertion.assertion_id)},
                    )
        for log in run.validation_logs:
            if log.assertion_id not in assertion_ids:
                raise ConflictError(
                    code="assertion_log_missing_assertion",
                    message="Assertion validation log references an unknown assertion id",
                    context={"run_id": str(run.run_id), "assertion_id": str(log.assertion_id)},
                )

    def _validate_lifecycle_graph(self, assertions_by_id: dict[EntityId, EvidenceAssertion]) -> None:
        self._validate_edge_graph(assertions_by_id, edge_name="supersedes")
        self._validate_edge_graph(assertions_by_id, edge_name="invalidates")

    def _validate_edge_graph(self, assertions_by_id: dict[EntityId, EvidenceAssertion], *, edge_name: str) -> None:
        edge_attr = f"{edge_name}_id"
        adjacency: dict[EntityId, EntityId] = {}
        for assertion_id, assertion in assertions_by_id.items():
            target_id = getattr(assertion, edge_attr)
            if target_id is None:
                continue
            if target_id not in assertions_by_id:
                raise ConflictError(
                    code=f"{edge_name}_target_missing",
                    message=f"Assertion {edge_name} references an unknown assertion id",
                    context={"assertion_id": str(assertion_id), f"{edge_name}_id": str(target_id)},
                )
            adjacency[assertion_id] = target_id

        visiting: set[EntityId] = set()
        visited: set[EntityId] = set()

        def visit(node_id: EntityId) -> None:
            if node_id in visited:
                return
            if node_id in visiting:
                raise ConflictError(
                    code=f"{edge_name}_cycle",
                    message=f"Assertion {edge_name} graph cannot contain cycles",
                    context={"assertion_id": str(node_id)},
                )
            visiting.add(node_id)
            next_id = adjacency.get(node_id)
            if next_id is not None:
                visit(next_id)
            visiting.remove(node_id)
            visited.add(node_id)

        for node_id in adjacency:
            visit(node_id)

    def _expected_provenance(self, assertion: EvidenceAssertion) -> tuple[EntityId, EntityId, EntityId, str, str, object]:
        if assertion.source_hypothesis.source_entity_candidate is not None:
            mention = assertion.source_hypothesis.source_entity_candidate.source_mention
            return (
                mention.document_id,
                mention.version_id,
                mention.fragment_id,
                mention.original_text,
                mention.normalized_text,
                mention.source_trace,
            )
        observation = assertion.source_hypothesis.source_relation_candidate.source_observation
        return (
            observation.document_id,
            observation.version_id,
            observation.fragment_id,
            observation.original_text,
            observation.normalized_text,
            observation.source_trace,
        )

    @staticmethod
    def _sort_key(run: AssertionGenerationRun) -> tuple[str, str]:
        return (run.finished_at.isoformat(), str(run.run_id))