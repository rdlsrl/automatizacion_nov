"""Deterministic candidate resolution over existing catalog concepts."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass

from drilling_knowledge.catalog.domain import EngineeringUnit, KnowledgeEntity, Variable
from drilling_knowledge.catalog.repositories.contracts import CatalogRepository, EntityRepository
from drilling_knowledge.common.ids import EntityId, RunId
from drilling_knowledge.extraction.domain import ExtractedEntity, ExtractedEntityType, ExtractionRun
from drilling_knowledge.normalization.domain import NormalizationCandidateStatus, NormalizationRun, NormalizedEntityCandidate, NormalizedRelationCandidate
from drilling_knowledge.resolution.domain import (
    CandidateConcept,
    CandidateEvidence,
    HypothesisSupport,
    HypothesisSupportKind,
    MentionResolution,
    RuleExecutionLog,
    ResolutionEvidenceType,
    ResolutionRun,
    ResolutionStatus,
    SemanticHypothesis,
    SemanticHypothesisStatus,
    SemanticResolutionRun,
)


@dataclass(frozen=True, slots=True)
class _IndexedCandidate:
    catalog_entity: KnowledgeEntity
    catalog_entity_type: str
    evidence_type: ResolutionEvidenceType
    source_field: str
    matched_text: str
    normalized_key: str


@dataclass(slots=True)
class CandidateResolutionEngine:
    catalog_repository: CatalogRepository

    @classmethod
    def create(cls, catalog_repository: CatalogRepository) -> "CandidateResolutionEngine":
        return cls(catalog_repository=catalog_repository)

    def resolve(self, extraction_run: ExtractionRun) -> ResolutionRun:
        mention_resolutions: list[MentionResolution] = []
        errors: list[str] = []
        indexes = self._build_indexes()

        for mention in extraction_run.entities:
            try:
                mention_resolutions.append(self._resolve_mention(mention, indexes))
            except Exception as exc:  # pragma: no cover - defensive guard
                errors.append(f"mention:{mention.entity_id}:{exc}")
                mention_resolutions.append(
                    MentionResolution(
                        resolution_id=self._resolution_id(mention, ResolutionStatus.UNRESOLVED),
                        mention=mention,
                        status=ResolutionStatus.UNRESOLVED,
                    )
                )

        ordered = tuple(sorted(mention_resolutions, key=self._resolution_sort_key))
        return ResolutionRun(
            run_id=RunId.from_seed(
                "resolution.run",
                f"{extraction_run.run_id}:{extraction_run.document_id}:{extraction_run.version_id}:{'|'.join(str(entity.entity_id) for entity in extraction_run.entities)}",
            ),
            started_at=extraction_run.finished_at,
            finished_at=extraction_run.finished_at,
            mention_resolutions=ordered,
            errors=tuple(errors),
        )

    def _resolve_mention(
        self,
        mention: ExtractedEntity,
        indexes: dict[ExtractedEntityType, dict[str, tuple[_IndexedCandidate, ...]]],
    ) -> MentionResolution:
        index = indexes.get(mention.entity_type)
        if index is None:
            return MentionResolution(
                resolution_id=self._resolution_id(mention, ResolutionStatus.UNRESOLVED),
                mention=mention,
                status=ResolutionStatus.UNRESOLVED,
            )

        candidates = self._rank_candidates(mention, index.get(mention.normalized_text, ()))
        if not candidates:
            status = ResolutionStatus.UNRESOLVED
        elif len(candidates) == 1:
            status = ResolutionStatus.RESOLVED_CANDIDATE
        else:
            status = ResolutionStatus.AMBIGUOUS

        return MentionResolution(
            resolution_id=self._resolution_id(mention, status),
            mention=mention,
            status=status,
            candidates=candidates,
        )

    def _build_indexes(self) -> dict[ExtractedEntityType, dict[str, tuple[_IndexedCandidate, ...]]]:
        indexes: dict[ExtractedEntityType, dict[str, tuple[_IndexedCandidate, ...]]] = {}
        simple_mappings = {
            ExtractedEntityType.VARIABLE: (self.catalog_repository.variables, "Variable"),
            ExtractedEntityType.SENSOR: (self.catalog_repository.sensors, "SensorClass"),
            ExtractedEntityType.INSTRUMENT: (self.catalog_repository.instruments, "InstrumentClass"),
            ExtractedEntityType.EQUIPMENT: (self.catalog_repository.equipment, "EquipmentClass"),
            ExtractedEntityType.SYSTEM: (self.catalog_repository.systems, "SystemClass"),
            ExtractedEntityType.SUBSYSTEM: (self.catalog_repository.subsystems, "SubsystemClass"),
            ExtractedEntityType.PROCESS: (self.catalog_repository.processes, "ProcessClass"),
            ExtractedEntityType.PHYSICAL_QUANTITY: (self.catalog_repository.quantities, "PhysicalQuantity"),
            ExtractedEntityType.ENGINEERING_UNIT: (self.catalog_repository.units, "EngineeringUnit"),
        }
        for mention_type, (repository, catalog_entity_type) in simple_mappings.items():
            indexes[mention_type] = self._index_repository(repository, catalog_entity_type)
        return indexes

    def _index_repository(
        self,
        repository: EntityRepository[KnowledgeEntity],
        catalog_entity_type: str,
    ) -> dict[str, tuple[_IndexedCandidate, ...]]:
        bucket: dict[str, list[_IndexedCandidate]] = defaultdict(list)
        for entity in repository.list_all():
            bucket[self._normalize(entity.canonical_name)].append(
                _IndexedCandidate(
                    catalog_entity=entity,
                    catalog_entity_type=catalog_entity_type,
                    evidence_type=ResolutionEvidenceType.EXACT_NAME,
                    source_field="canonical_name",
                    matched_text=entity.canonical_name,
                    normalized_key=self._normalize(entity.canonical_name),
                )
            )
            bucket[self._normalize(str(entity.code))].append(
                _IndexedCandidate(
                    catalog_entity=entity,
                    catalog_entity_type=catalog_entity_type,
                    evidence_type=ResolutionEvidenceType.EXACT_CODE,
                    source_field="code",
                    matched_text=str(entity.code),
                    normalized_key=self._normalize(str(entity.code)),
                )
            )
            if isinstance(entity, Variable):
                for alias in entity.aliases:
                    bucket[self._normalize(alias.alias)].append(
                        _IndexedCandidate(
                            catalog_entity=entity,
                            catalog_entity_type=catalog_entity_type,
                            evidence_type=ResolutionEvidenceType.EXPLICIT_ALIAS,
                            source_field=f"alias:{alias.alias_type}",
                            matched_text=alias.alias,
                            normalized_key=self._normalize(alias.alias),
                        )
                    )
            if isinstance(entity, EngineeringUnit):
                bucket[self._normalize(entity.symbol)].append(
                    _IndexedCandidate(
                        catalog_entity=entity,
                        catalog_entity_type=catalog_entity_type,
                        evidence_type=ResolutionEvidenceType.EXACT_SYMBOL,
                        source_field="symbol",
                        matched_text=entity.symbol,
                        normalized_key=self._normalize(entity.symbol),
                    )
                )
        return {
            key: tuple(sorted(values, key=self._indexed_candidate_sort_key))
            for key, values in bucket.items()
        }

    def _rank_candidates(
        self,
        mention: ExtractedEntity,
        indexed_candidates: tuple[_IndexedCandidate, ...],
    ) -> tuple[CandidateConcept, ...]:
        grouped: dict[EntityId, list[CandidateEvidence]] = defaultdict(list)
        metadata_by_entity: dict[EntityId, tuple[str, str, str]] = {}
        for indexed in indexed_candidates:
            grouped[indexed.catalog_entity.entity_id].append(
                CandidateEvidence(
                    evidence_type=indexed.evidence_type,
                    matched_text=indexed.matched_text,
                    normalized_matched_text=indexed.normalized_key,
                    source_field=indexed.source_field,
                    explanation=self._explanation_for(
                        indexed.evidence_type,
                        indexed.catalog_entity.canonical_name,
                        indexed.matched_text,
                    ),
                )
            )
            metadata_by_entity[indexed.catalog_entity.entity_id] = (
                indexed.catalog_entity_type,
                str(indexed.catalog_entity.code),
                indexed.catalog_entity.canonical_name,
            )

        ranked = tuple(
            sorted(
                (
                    self._build_candidate(
                        mention,
                        catalog_entity_id,
                        metadata_by_entity[catalog_entity_id],
                        grouped[catalog_entity_id],
                    )
                    for catalog_entity_id in grouped
                ),
                key=self._candidate_sort_key,
            )
        )
        return tuple(
            CandidateConcept(
                candidate_id=candidate.candidate_id,
                catalog_entity_id=candidate.catalog_entity_id,
                catalog_entity_type=candidate.catalog_entity_type,
                catalog_code=candidate.catalog_code,
                canonical_name=candidate.canonical_name,
                rank=index + 1,
                evidence=candidate.evidence,
                supporting_evidences=candidate.supporting_evidences,
            )
            for index, candidate in enumerate(ranked)
        )

    def _build_candidate(
        self,
        mention: ExtractedEntity,
        catalog_entity_id: EntityId,
        metadata: tuple[str, str, str],
        evidences: list[CandidateEvidence],
    ) -> CandidateConcept:
        supporting_evidences = tuple(sorted(self._unique_evidences(evidences), key=self._evidence_sort_key))
        primary = supporting_evidences[0]
        return CandidateConcept(
            candidate_id=EntityId.from_seed(
                "resolution.candidate",
                f"{mention.entity_id}:{catalog_entity_id}:{primary.evidence_type.value}:{primary.source_field}:{primary.matched_text}",
            ),
            catalog_entity_id=catalog_entity_id,
            catalog_entity_type=metadata[0],
            catalog_code=metadata[1],
            canonical_name=metadata[2],
            rank=self._evidence_rank(primary.evidence_type),
            evidence=primary,
            supporting_evidences=supporting_evidences,
        )

    def _resolution_id(self, mention: ExtractedEntity, status: ResolutionStatus) -> EntityId:
        return EntityId.from_seed("resolution.mention", f"{mention.entity_id}:{status.value}")

    def _candidate_sort_key(self, candidate: CandidateConcept) -> tuple[int, str, str, str]:
        return (
            self._evidence_rank(candidate.evidence.evidence_type),
            candidate.canonical_name.casefold(),
            candidate.catalog_code,
            str(candidate.catalog_entity_id),
        )

    def _indexed_candidate_sort_key(self, candidate: _IndexedCandidate) -> tuple[int, str, str, str]:
        return (
            self._evidence_rank(candidate.evidence_type),
            candidate.catalog_entity.canonical_name.casefold(),
            str(candidate.catalog_entity.code),
            str(candidate.catalog_entity.entity_id),
        )

    def _resolution_sort_key(self, resolution: MentionResolution) -> tuple[str, int | None, int | None, str]:
        return (
            str(resolution.mention.fragment_id),
            resolution.mention.source_trace.start_offset,
            resolution.mention.source_trace.end_offset,
            str(resolution.mention.entity_id),
        )

    def _evidence_sort_key(self, evidence: CandidateEvidence) -> tuple[int, str, str, str]:
        return (
            self._evidence_rank(evidence.evidence_type),
            evidence.normalized_matched_text,
            evidence.source_field,
            evidence.explanation,
        )

    def _unique_evidences(self, evidences: list[CandidateEvidence]) -> tuple[CandidateEvidence, ...]:
        unique: dict[tuple[str, str, str, str], CandidateEvidence] = {}
        for evidence in evidences:
            key = (
                evidence.evidence_type.value,
                evidence.normalized_matched_text,
                evidence.source_field,
                evidence.explanation,
            )
            unique.setdefault(key, evidence)
        return tuple(unique.values())

    def _evidence_rank(self, evidence_type: ResolutionEvidenceType) -> int:
        priority = {
            ResolutionEvidenceType.EXACT_NAME: 0,
            ResolutionEvidenceType.EXPLICIT_ALIAS: 1,
            ResolutionEvidenceType.EXACT_CODE: 2,
            ResolutionEvidenceType.EXACT_SYMBOL: 3,
        }
        return priority[evidence_type]

    def _explanation_for(self, evidence_type: ResolutionEvidenceType, canonical_name: str, matched_text: str) -> str:
        if evidence_type == ResolutionEvidenceType.EXACT_NAME:
            return f"Canonical name matched exactly: {canonical_name}"
        if evidence_type == ResolutionEvidenceType.EXPLICIT_ALIAS:
            return f"Explicit alias matched exactly: {matched_text}"
        if evidence_type == ResolutionEvidenceType.EXACT_CODE:
            return f"Catalog code matched exactly: {matched_text}"
        return f"Engineering unit symbol matched exactly: {matched_text}"

    def _normalize(self, text: str) -> str:
        return " ".join(text.split()).strip().lower()


@dataclass(frozen=True, slots=True)
class _RuleSpec:
    code: str
    name: str
    priority: int


@dataclass(frozen=True, slots=True)
class _FilterResult:
    outcome: str
    reason_codes: tuple[str, ...] = ()
    details: tuple[tuple[str, str], ...] = ()


@dataclass(slots=True)
class SemanticResolutionEngine:
    catalog_repository: CatalogRepository
    rule_pack_version: str = "semantic.rules.v1"

    @classmethod
    def create(
        cls,
        catalog_repository: CatalogRepository,
        *,
        rule_pack_version: str = "semantic.rules.v1",
    ) -> "SemanticResolutionEngine":
        return cls(catalog_repository=catalog_repository, rule_pack_version=rule_pack_version)

    def resolve(self, normalization_run: NormalizationRun) -> SemanticResolutionRun:
        hypotheses: list[SemanticHypothesis] = []
        supports: list[HypothesisSupport] = []
        execution_logs: list[RuleExecutionLog] = []
        errors: list[str] = []
        created_at = normalization_run.finished_at

        for candidate in normalization_run.entity_candidates:
            try:
                hypothesis, candidate_supports, candidate_logs = self._resolve_entity_candidate(candidate, created_at)
                hypotheses.append(hypothesis)
                supports.extend(candidate_supports)
                execution_logs.extend(candidate_logs)
            except Exception as exc:  # pragma: no cover - defensive guard
                errors.append(f"entity_candidate:{candidate.candidate_id}:{exc}")
                hypothesis, candidate_supports, candidate_logs = self._entity_fallback_rejection(candidate, created_at, str(exc))
                hypotheses.append(hypothesis)
                supports.extend(candidate_supports)
                execution_logs.extend(candidate_logs)

        for candidate in normalization_run.relation_candidates:
            try:
                hypothesis, candidate_supports, candidate_logs = self._resolve_relation_candidate(candidate, created_at)
                hypotheses.append(hypothesis)
                supports.extend(candidate_supports)
                execution_logs.extend(candidate_logs)
            except Exception as exc:  # pragma: no cover - defensive guard
                errors.append(f"relation_candidate:{candidate.candidate_id}:{exc}")
                hypothesis, candidate_supports, candidate_logs = self._relation_fallback_rejection(candidate, created_at, str(exc))
                hypotheses.append(hypothesis)
                supports.extend(candidate_supports)
                execution_logs.extend(candidate_logs)

        ordered_hypotheses = tuple(sorted(hypotheses, key=self._hypothesis_sort_key))
        ordered_supports = tuple(sorted(supports, key=self._support_sort_key))
        ordered_logs = tuple(sorted(execution_logs, key=self._execution_log_sort_key))
        run_seed = "|".join(
            [
                str(normalization_run.run_id),
                self.rule_pack_version,
                *(str(hypothesis.hypothesis_id) for hypothesis in ordered_hypotheses),
                *(str(support.support_id) for support in ordered_supports),
                *(str(log.execution_id) for log in ordered_logs),
            ]
        )
        return SemanticResolutionRun(
            run_id=RunId.from_seed("semantic.resolution.run", run_seed),
            normalization_run_id=normalization_run.run_id,
            rule_pack_version=self.rule_pack_version,
            started_at=normalization_run.finished_at,
            finished_at=normalization_run.finished_at,
            hypotheses=ordered_hypotheses,
            supports=ordered_supports,
            execution_logs=ordered_logs,
            errors=tuple(errors),
        )

    def _resolve_entity_candidate(
        self,
        candidate: NormalizedEntityCandidate,
        created_at,
    ) -> tuple[SemanticHypothesis, tuple[HypothesisSupport, ...], tuple[RuleExecutionLog, ...]]:
        rule = _RuleSpec("SEM-RULE-001", "entity candidate hypothesis", 10)
        if candidate.matched_id is None:
            reason_codes = ("no_catalog_anchor",)
            hypothesis = self._entity_hypothesis(candidate, created_at, SemanticHypothesisStatus.REJECTED, 0.0, reason_codes)
            supports = (
                self._candidate_support(hypothesis.hypothesis_id, candidate, rule.code, candidate.match_method.value, candidate.evidence.explanation),
                self._rule_support(hypothesis.hypothesis_id, candidate.candidate_id, rule.code, "explicit_rejection", "Candidate remained proposed after normalization"),
            )
            logs = (
                self._execution_log(rule, candidate.candidate_id, "entity_candidate", "rejected", reason_codes, (("status", candidate.status.value),)),
            )
            return hypothesis, supports, logs

        hypothesis = self._entity_hypothesis(candidate, created_at, SemanticHypothesisStatus.SUPPORTED, candidate.normalization_score, ())
        supports = (
            self._candidate_support(hypothesis.hypothesis_id, candidate, rule.code, candidate.match_method.value, candidate.evidence.explanation),
            self._rule_support(hypothesis.hypothesis_id, candidate.candidate_id, rule.code, "candidate_binding", "Normalized candidate enumerated as a semantic hypothesis"),
        )
        logs = (
            self._execution_log(rule, candidate.candidate_id, "entity_candidate", "supported", (), (("status", candidate.status.value),)),
        )
        return hypothesis, supports, logs

    def _resolve_relation_candidate(
        self,
        candidate: NormalizedRelationCandidate,
        created_at,
    ) -> tuple[SemanticHypothesis, tuple[HypothesisSupport, ...], tuple[RuleExecutionLog, ...]]:
        rule = self._relation_rule(candidate)
        base_reasons = tuple(candidate.issues)
        filter_specs = (
            _RuleSpec("SEM-FILTER-001", "quantity-unit hard filter", 30),
            _RuleSpec("SEM-FILTER-002", "domain-range hard filter", 40),
            _RuleSpec("SEM-FILTER-003", "origin-publisher hard filter", 50),
            _RuleSpec("SEM-FILTER-004", "chain compatibility hard filter", 60),
        )
        filter_results = (
            self._apply_quantity_unit_filter(candidate),
            self._apply_domain_range_filter(candidate),
            self._apply_origin_publisher_filter(candidate),
            self._apply_chain_filter(candidate),
        )
        rejected_codes = list(base_reasons)
        supports: list[HypothesisSupport] = [
            self._relation_candidate_support(candidate, rule.code),
            self._rule_support(
                EntityId.from_seed("semantic.hypothesis.placeholder", str(candidate.candidate_id)),
                candidate.candidate_id,
                rule.code,
                "candidate_binding",
                "Normalized relation candidate enumerated for semantic evaluation",
            ),
        ]
        logs: list[RuleExecutionLog] = [
            self._execution_log(rule, candidate.candidate_id, "relation_candidate", "evaluated", base_reasons, (("predicate_code", candidate.predicate_code),)),
        ]
        for filter_rule, result in zip(filter_specs, filter_results, strict=True):
            if result.outcome == "rejected":
                rejected_codes.extend(result.reason_codes)
            logs.append(
                self._execution_log(filter_rule, candidate.candidate_id, "relation_candidate", result.outcome, result.reason_codes, result.details)
            )

        deduped_reasons = tuple(dict.fromkeys(code for code in rejected_codes if code))
        rejected = bool(deduped_reasons) or candidate.status == NormalizationCandidateStatus.PROPOSED
        if rejected and not deduped_reasons:
            deduped_reasons = ("normalization_candidate_proposed",)
        status = SemanticHypothesisStatus.REJECTED if rejected else SemanticHypothesisStatus.SUPPORTED
        score = 0.0 if rejected else candidate.normalization_score
        hypothesis = SemanticHypothesis(
            hypothesis_id=EntityId.from_seed(
                "semantic.hypothesis",
                f"{candidate.candidate_id}:{candidate.predicate_code}:{status.value}:{'|'.join(deduped_reasons) if deduped_reasons else 'supported'}",
            ),
            source_candidate_id=candidate.candidate_id,
            source_candidate_kind="relation_candidate",
            subject_table=candidate.normalized_subject_table,
            subject_id=candidate.normalized_subject_id,
            predicate_code=candidate.predicate_code,
            object_table=candidate.normalized_object_table,
            object_id=candidate.normalized_object_id,
            status=status,
            score=score,
            score_breakdown=(("normalization_score", candidate.normalization_score), ("hard_filter_multiplier", 0.0 if rejected else 1.0)),
            reason_codes=deduped_reasons,
            created_at=created_at,
            source_relation_candidate=candidate,
        )
        supports[1] = self._rule_support(
            hypothesis.hypothesis_id,
            candidate.candidate_id,
            rule.code,
            "candidate_binding",
            "Normalized relation candidate enumerated for semantic evaluation",
        )
        for filter_rule, result in zip(filter_specs, filter_results, strict=True):
            if result.outcome == "skipped":
                continue
            reason_code = result.reason_codes[0] if result.reason_codes else "passed"
            detail = self._detail_text(result.details, default="Hard filter executed deterministically")
            supports.append(self._support(hypothesis.hypothesis_id, HypothesisSupportKind.FILTER, candidate.candidate_id, filter_rule.code, reason_code, detail))
        return hypothesis, tuple(supports), tuple(logs)

    def _entity_hypothesis(
        self,
        candidate: NormalizedEntityCandidate,
        created_at,
        status: SemanticHypothesisStatus,
        score: float,
        reason_codes: tuple[str, ...],
    ) -> SemanticHypothesis:
        return SemanticHypothesis(
            hypothesis_id=EntityId.from_seed(
                "semantic.hypothesis",
                f"{candidate.candidate_id}:denotes_catalog_entity:{status.value}:{'|'.join(reason_codes) if reason_codes else 'supported'}",
            ),
            source_candidate_id=candidate.candidate_id,
            source_candidate_kind="entity_candidate",
            subject_table="extract.candidate_mention",
            subject_id=candidate.candidate_mention_id,
            predicate_code="denotes_catalog_entity",
            object_table=candidate.matched_table,
            object_id=candidate.matched_id,
            status=status,
            score=score,
            score_breakdown=(("normalization_score", candidate.normalization_score), ("hard_filter_multiplier", 0.0 if status == SemanticHypothesisStatus.REJECTED else 1.0)),
            reason_codes=reason_codes,
            created_at=created_at,
            source_entity_candidate=candidate,
        )

    def _relation_rule(self, candidate: NormalizedRelationCandidate) -> _RuleSpec:
        if candidate.predicate_code == "textual_unit_association":
            return _RuleSpec("SEM-RULE-002", "textual unit association hypothesis", 20)
        if candidate.predicate_code == "explicit_scaling":
            return _RuleSpec("SEM-RULE-003", "explicit scaling hypothesis", 25)
        if candidate.predicate_code == "origin_publisher_association":
            return _RuleSpec("SEM-RULE-004", "origin publisher hypothesis", 26)
        if candidate.predicate_code == "measurement_chain_compatibility":
            return _RuleSpec("SEM-RULE-005", "measurement chain compatibility hypothesis", 27)
        return _RuleSpec("SEM-RULE-099", "generic relation hypothesis", 90)

    def _apply_quantity_unit_filter(self, candidate: NormalizedRelationCandidate) -> _FilterResult:
        if candidate.predicate_code != "textual_unit_association":
            return _FilterResult("skipped")
        if "incompatible_unit_quantity" in candidate.issues:
            return _FilterResult(
                "rejected",
                ("quantity_unit_incompatible",),
                (("issue", "incompatible_unit_quantity"),),
            )
        return _FilterResult("passed", ("quantity_unit_compatible",), (("predicate_code", candidate.predicate_code),))

    def _apply_domain_range_filter(self, candidate: NormalizedRelationCandidate) -> _FilterResult:
        allowed_pairs = {
            "textual_unit_association": {
                ("catalog.variable", "catalog.engineering_unit"),
                ("catalog.physical_quantity", "catalog.engineering_unit"),
            },
            "explicit_scaling": {
                ("extract.observation", "catalog.engineering_unit"),
            },
        }
        allowed = allowed_pairs.get(candidate.predicate_code)
        if allowed is None:
            return _FilterResult("skipped")
        pair = (candidate.normalized_subject_table, candidate.normalized_object_table or "")
        if pair not in allowed:
            return _FilterResult(
                "rejected",
                ("domain_range_incompatible",),
                (("subject_table", candidate.normalized_subject_table), ("object_table", candidate.normalized_object_table or "null")),
            )
        return _FilterResult("passed", ("domain_range_valid",), (("predicate_code", candidate.predicate_code),))

    def _apply_origin_publisher_filter(self, candidate: NormalizedRelationCandidate) -> _FilterResult:
        if candidate.predicate_code not in {"origin_publisher_association", "origin_publisher_compatibility"}:
            return _FilterResult("skipped")
        if candidate.normalized_subject_table != "catalog.origin_class" or candidate.normalized_object_table != "catalog.publisher_class":
            return _FilterResult(
                "rejected",
                ("origin_publisher_domain_mismatch",),
                (("subject_table", candidate.normalized_subject_table), ("object_table", candidate.normalized_object_table or "null")),
            )
        return _FilterResult("passed", ("origin_publisher_compatible",), ())

    def _apply_chain_filter(self, candidate: NormalizedRelationCandidate) -> _FilterResult:
        if candidate.predicate_code not in {"measurement_chain_link", "measurement_chain_stage", "measurement_chain_compatibility"}:
            return _FilterResult("skipped")
        allowed_tables = {"catalog.sensor_class", "catalog.instrument_class", "catalog.variable", "catalog.equipment_class"}
        if candidate.normalized_subject_table not in allowed_tables or (candidate.normalized_object_table or "") not in allowed_tables:
            return _FilterResult(
                "rejected",
                ("chain_compatibility_rejected",),
                (("subject_table", candidate.normalized_subject_table), ("object_table", candidate.normalized_object_table or "null")),
            )
        return _FilterResult("passed", ("chain_compatible",), ())

    def _entity_fallback_rejection(
        self,
        candidate: NormalizedEntityCandidate,
        created_at,
        error_text: str,
    ) -> tuple[SemanticHypothesis, tuple[HypothesisSupport, ...], tuple[RuleExecutionLog, ...]]:
        rule = _RuleSpec("SEM-RULE-ERR-ENTITY", "entity candidate fallback rejection", 999)
        hypothesis = self._entity_hypothesis(candidate, created_at, SemanticHypothesisStatus.REJECTED, 0.0, ("semantic_resolution_error",))
        supports = (
            self._candidate_support(hypothesis.hypothesis_id, candidate, rule.code, "semantic_resolution_error", candidate.evidence.explanation),
            self._rule_support(hypothesis.hypothesis_id, candidate.candidate_id, rule.code, "semantic_resolution_error", error_text),
        )
        logs = (
            self._execution_log(
                rule,
                candidate.candidate_id,
                "entity_candidate",
                "error_rejected",
                ("semantic_resolution_error",),
                (("error", error_text),),
                hypothesis.hypothesis_id,
            ),
        )
        return hypothesis, supports, logs

    def _relation_fallback_rejection(
        self,
        candidate: NormalizedRelationCandidate,
        created_at,
        error_text: str,
    ) -> tuple[SemanticHypothesis, tuple[HypothesisSupport, ...], tuple[RuleExecutionLog, ...]]:
        rule = _RuleSpec("SEM-RULE-ERR-REL", "relation candidate fallback rejection", 999)
        hypothesis = SemanticHypothesis(
            hypothesis_id=EntityId.from_seed(
                "semantic.hypothesis",
                f"{candidate.candidate_id}:{candidate.predicate_code}:rejected:semantic_resolution_error",
            ),
            source_candidate_id=candidate.candidate_id,
            source_candidate_kind="relation_candidate",
            subject_table=candidate.normalized_subject_table,
            subject_id=candidate.normalized_subject_id,
            predicate_code=candidate.predicate_code,
            object_table=candidate.normalized_object_table,
            object_id=candidate.normalized_object_id,
            status=SemanticHypothesisStatus.REJECTED,
            score=0.0,
            score_breakdown=(("normalization_score", candidate.normalization_score), ("hard_filter_multiplier", 0.0)),
            reason_codes=("semantic_resolution_error",),
            created_at=created_at,
            source_relation_candidate=candidate,
        )
        supports = (
            self._support(hypothesis.hypothesis_id, HypothesisSupportKind.CANDIDATE, candidate.candidate_id, rule.code, candidate.predicate_code, candidate.source_observation.original_text),
            self._rule_support(hypothesis.hypothesis_id, candidate.candidate_id, rule.code, "semantic_resolution_error", error_text),
        )
        logs = (
            self._execution_log(
                rule,
                candidate.candidate_id,
                "relation_candidate",
                "error_rejected",
                ("semantic_resolution_error",),
                (("error", error_text),),
                hypothesis.hypothesis_id,
            ),
        )
        return hypothesis, supports, logs

    def _candidate_support(
        self,
        hypothesis_id: EntityId,
        candidate: NormalizedEntityCandidate,
        rule_code: str,
        reason_code: str,
        detail: str,
    ) -> HypothesisSupport:
        return self._support(hypothesis_id, HypothesisSupportKind.CANDIDATE, candidate.candidate_id, rule_code, reason_code, detail)

    def _relation_candidate_support(self, candidate: NormalizedRelationCandidate, rule_code: str) -> HypothesisSupport:
        detail = candidate.source_observation.original_text
        return self._support(
            EntityId.from_seed("semantic.hypothesis.placeholder", str(candidate.candidate_id)),
            HypothesisSupportKind.CANDIDATE,
            candidate.candidate_id,
            rule_code,
            candidate.predicate_code,
            detail,
        )

    def _rule_support(
        self,
        hypothesis_id: EntityId,
        source_candidate_id: EntityId,
        rule_code: str,
        reason_code: str,
        detail: str,
    ) -> HypothesisSupport:
        return self._support(hypothesis_id, HypothesisSupportKind.RULE, source_candidate_id, rule_code, reason_code, detail)

    def _support(
        self,
        hypothesis_id: EntityId,
        support_kind: HypothesisSupportKind,
        source_candidate_id: EntityId,
        rule_code: str,
        reason_code: str,
        detail: str,
    ) -> HypothesisSupport:
        return HypothesisSupport(
            support_id=EntityId.from_seed(
                "semantic.hypothesis_support",
                f"{hypothesis_id}:{support_kind.value}:{source_candidate_id}:{rule_code}:{reason_code}:{detail}",
            ),
            hypothesis_id=hypothesis_id,
            support_kind=support_kind,
            source_candidate_id=source_candidate_id,
            rule_code=rule_code,
            reason_code=reason_code,
            detail=detail,
        )

    def _execution_log(
        self,
        rule: _RuleSpec,
        input_candidate_id: EntityId,
        input_candidate_kind: str,
        outcome: str,
        reason_codes: tuple[str, ...],
        details: tuple[tuple[str, str], ...],
        hypothesis_id: EntityId | None = None,
    ) -> RuleExecutionLog:
        return RuleExecutionLog(
            execution_id=EntityId.from_seed(
                "semantic.rule_execution",
                f"{rule.code}:{rule.priority}:{input_candidate_id}:{input_candidate_kind}:{outcome}:{'|'.join(reason_codes)}:{'|'.join(f'{key}={value}' for key, value in details)}",
            ),
            rule_code=rule.code,
            rule_name=rule.name,
            priority=rule.priority,
            input_candidate_id=input_candidate_id,
            input_candidate_kind=input_candidate_kind,
            outcome=outcome,
            reason_codes=reason_codes,
            details=details,
            hypothesis_id=hypothesis_id,
        )

    def _hypothesis_sort_key(self, hypothesis: SemanticHypothesis) -> tuple[int, str, float, str]:
        status_rank = 0 if hypothesis.status == SemanticHypothesisStatus.SUPPORTED else 1
        return (status_rank, hypothesis.predicate_code, -hypothesis.score, str(hypothesis.hypothesis_id))

    def _support_sort_key(self, support: HypothesisSupport) -> tuple[str, str, str, str]:
        return (str(support.hypothesis_id), support.support_kind.value, support.rule_code, str(support.support_id))

    def _execution_log_sort_key(self, log: RuleExecutionLog) -> tuple[int, str, str, str]:
        return (log.priority, log.rule_code, str(log.input_candidate_id), str(log.execution_id))

    def _detail_text(self, details: tuple[tuple[str, str], ...], *, default: str) -> str:
        if not details:
            return default
        return ", ".join(f"{key}={value}" for key, value in details)