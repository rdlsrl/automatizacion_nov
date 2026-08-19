"""Deterministic normalization of extracted evidence against seeded catalogs."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
import re

from drilling_knowledge.catalog.domain import EngineeringUnit, KnowledgeEntity, PhysicalQuantity, QuantityUnitCompatibility, Variable
from drilling_knowledge.catalog.repositories.contracts import CatalogRepository, EntityRepository
from drilling_knowledge.common.ids import EntityId, RunId
from drilling_knowledge.extraction.domain import ExtractedEntity, ExtractedEntityType, ExtractedObservation, ExtractedObservationType, ExtractionRun
from drilling_knowledge.normalization.domain import (
    NormalizationCandidateStatus,
    NormalizationEvidence,
    NormalizationMatchMethod,
    NormalizationRun,
    NormalizationRunStatus,
    NormalizedEntityCandidate,
    NormalizedRelationCandidate,
)


@dataclass(frozen=True, slots=True)
class _IndexedEntity:
    catalog_entity: KnowledgeEntity
    matched_table: str
    match_method: NormalizationMatchMethod
    source_field: str
    matched_text: str
    normalized_key: str


@dataclass(slots=True)
class NormalizationEngine:
    catalog_repository: CatalogRepository
    ontology_version: str = "seeded-catalogs.v1"
    rule_pack_version: str = "normalization.rules.v1"
    _variables_by_id: dict[EntityId, Variable] = field(init=False, repr=False, default_factory=dict)
    _units_by_id: dict[EntityId, EngineeringUnit] = field(init=False, repr=False, default_factory=dict)
    _quantities_by_code: dict[str, PhysicalQuantity] = field(init=False, repr=False, default_factory=dict)
    _compatibility_keys: set[tuple[str, str]] = field(init=False, repr=False, default_factory=set)

    def __post_init__(self) -> None:
        object.__setattr__(self, "_variables_by_id", {entity.entity_id: entity for entity in self.catalog_repository.variables.list_all()})
        object.__setattr__(self, "_units_by_id", {entity.entity_id: entity for entity in self.catalog_repository.units.list_all()})
        object.__setattr__(self, "_quantities_by_code", {str(entity.code): entity for entity in self.catalog_repository.quantities.list_all()})
        object.__setattr__(
            self,
            "_compatibility_keys",
            {
                (str(entity.quantity_code), str(entity.unit_code))
                for entity in self.catalog_repository.quantity_unit_compatibilities.list_all()
            },
        )

    @classmethod
    def create(
        cls,
        catalog_repository: CatalogRepository,
        *,
        ontology_version: str = "seeded-catalogs.v1",
        rule_pack_version: str = "normalization.rules.v1",
    ) -> "NormalizationEngine":
        return cls(
            catalog_repository=catalog_repository,
            ontology_version=ontology_version,
            rule_pack_version=rule_pack_version,
        )

    def normalize(self, extraction_run: ExtractionRun) -> NormalizationRun:
        indexes = self._build_indexes()
        created_at = extraction_run.finished_at
        extraction_run_id = extraction_run.run_id
        entity_candidates_by_mention: dict[EntityId, tuple[NormalizedEntityCandidate, ...]] = {}
        entity_candidates: list[NormalizedEntityCandidate] = []
        relation_candidates: list[NormalizedRelationCandidate] = []
        errors: list[str] = []

        for mention in sorted(extraction_run.entities, key=self._mention_sort_key):
            try:
                candidates = self._normalize_mention(mention, indexes, created_at, extraction_run_id)
                entity_candidates_by_mention[mention.entity_id] = candidates
                entity_candidates.extend(candidates)
            except Exception as exc:  # pragma: no cover - defensive guard
                errors.append(f"mention:{mention.entity_id}:{exc}")
                fallback = self._proposed_entity_candidate(
                    mention,
                    created_at,
                    extraction_run_id,
                    match_method=NormalizationMatchMethod.NO_CATALOG_MATCH,
                    explanation=str(exc),
                )
                entity_candidates_by_mention[mention.entity_id] = (fallback,)
                entity_candidates.append(fallback)

        for observation in sorted(extraction_run.observations, key=self._observation_sort_key):
            try:
                relation_candidates.extend(
                    self._normalize_observation(observation, entity_candidates_by_mention, created_at, indexes, extraction_run_id)
                )
            except Exception as exc:  # pragma: no cover - defensive guard
                errors.append(f"observation:{observation.observation_id}:{exc}")
                relation_candidates.append(self._proposed_observation_candidate(observation, created_at, extraction_run_id, str(exc)))

        ordered_entities = tuple(entity_candidates)
        ordered_relations = tuple(relation_candidates)
        run_seed = "|".join(
            [
                str(extraction_run.run_id),
                self.ontology_version,
                self.rule_pack_version,
                *(str(candidate.candidate_id) for candidate in ordered_entities),
                *(str(candidate.candidate_id) for candidate in ordered_relations),
            ]
        )
        return NormalizationRun(
            run_id=RunId.from_seed("normalization.run", run_seed),
            extraction_run_id=extraction_run.run_id,
            ontology_version=self.ontology_version,
            rule_pack_version=self.rule_pack_version,
            started_at=extraction_run.finished_at,
            finished_at=extraction_run.finished_at,
            status=NormalizationRunStatus.COMPLETED,
            entity_candidates=ordered_entities,
            relation_candidates=ordered_relations,
            errors=tuple(errors),
        )

    def _normalize_mention(
        self,
        mention: ExtractedEntity,
        indexes: dict[ExtractedEntityType, dict[str, tuple[_IndexedEntity, ...]]],
        created_at,
        extraction_run_id: RunId,
    ) -> tuple[NormalizedEntityCandidate, ...]:
        if mention.extraction_rule.startswith("energistics.schema."):
            return (self._document_local_entity_candidate(mention, created_at, extraction_run_id),)
        index = indexes.get(mention.entity_type)
        if index is None:
            return (
                self._proposed_entity_candidate(
                    mention,
                    created_at,
                    extraction_run_id,
                    match_method=NormalizationMatchMethod.UNSUPPORTED_ENTITY_TYPE,
                    explanation=f"No seeded catalog matcher is available for entity type {mention.entity_type.value}",
                ),
            )

        indexed_candidates = self._lookup_indexed_candidates(index, mention)
        if not indexed_candidates:
            return (
                self._proposed_entity_candidate(
                    mention,
                    created_at,
                    extraction_run_id,
                    match_method=NormalizationMatchMethod.NO_CATALOG_MATCH,
                    explanation="No seeded catalog anchor matched the observed text",
                ),
            )

        grouped: dict[EntityId, list[NormalizationEvidence]] = defaultdict(list)
        metadata_by_entity: dict[EntityId, tuple[str, str]] = {}
        method_by_entity: dict[EntityId, NormalizationMatchMethod] = {}
        for indexed in indexed_candidates:
            grouped[indexed.catalog_entity.entity_id].append(
                NormalizationEvidence(
                    matched_text=indexed.matched_text,
                    normalized_matched_text=indexed.normalized_key,
                    source_field=indexed.source_field,
                    explanation=self._explanation_for(indexed.match_method, indexed.catalog_entity.canonical_name, indexed.matched_text),
                )
            )
            metadata_by_entity[indexed.catalog_entity.entity_id] = (indexed.matched_table, indexed.catalog_entity.canonical_name)
            current_method = method_by_entity.get(indexed.catalog_entity.entity_id)
            if current_method is None or self._match_method_rank(indexed.match_method) < self._match_method_rank(current_method):
                method_by_entity[indexed.catalog_entity.entity_id] = indexed.match_method

        ranked = sorted(
            grouped,
            key=lambda entity_id: (
                self._match_method_rank(method_by_entity[entity_id]),
                metadata_by_entity[entity_id][1].casefold(),
                str(entity_id),
            ),
        )
        unique_status = NormalizationCandidateStatus.RESOLVED if len(ranked) == 1 else NormalizationCandidateStatus.ALTERNATIVE
        candidates: list[NormalizedEntityCandidate] = []
        for entity_id in ranked:
            supporting_evidences = tuple(sorted(self._unique_evidences(grouped[entity_id]), key=self._evidence_sort_key))
            primary_evidence = supporting_evidences[0]
            match_method = method_by_entity[entity_id]
            matched_table, canonical_text = metadata_by_entity[entity_id]
            score = min(mention.extraction_confidence, self._base_score(match_method))
            candidates.append(
                NormalizedEntityCandidate(
                    candidate_id=EntityId.from_seed(
                        "normalization.entity_candidate",
                        f"{mention.entity_id}:{entity_id}:{match_method.value}:{primary_evidence.source_field}:{primary_evidence.matched_text}",
                    ),
                    extraction_run_id=extraction_run_id,
                    candidate_mention_id=mention.entity_id,
                    entity_type=mention.entity_type,
                    mention_text=mention.original_text,
                    matched_table=matched_table,
                    matched_id=entity_id,
                    canonical_text=canonical_text,
                    match_method=match_method,
                    normalization_score=score,
                    is_new_concept_proposal=False,
                    status=unique_status,
                    created_at=created_at,
                    source_mention=mention,
                    evidence=primary_evidence,
                    supporting_evidences=supporting_evidences,
                )
            )
        return tuple(candidates)

    def _normalize_observation(
        self,
        observation: ExtractedObservation,
        entity_candidates_by_mention: dict[EntityId, tuple[NormalizedEntityCandidate, ...]],
        created_at,
        indexes: dict[ExtractedEntityType, dict[str, tuple[_IndexedEntity, ...]]],
        extraction_run_id: RunId,
    ) -> tuple[NormalizedRelationCandidate, ...]:
        if observation.observation_type == ExtractedObservationType.TEXTUAL_UNIT_ASSOCIATION:
            return self._normalize_textual_unit_association(observation, entity_candidates_by_mention, created_at, extraction_run_id)
        if observation.observation_type == ExtractedObservationType.EXPLICIT_SCALING:
            return self._normalize_explicit_scaling(observation, created_at, indexes, extraction_run_id)
        if observation.observation_type == ExtractedObservationType.ORIGIN_PUBLISHER_ASSOCIATION:
            return self._normalize_explicit_relation_candidate(
                observation,
                entity_candidates_by_mention,
                created_at,
                extraction_run_id,
                predicate_code="origin_publisher_association",
            )
        if observation.observation_type == ExtractedObservationType.MEASUREMENT_CHAIN_COMPATIBILITY:
            return self._normalize_explicit_relation_candidate(
                observation,
                entity_candidates_by_mention,
                created_at,
                extraction_run_id,
                predicate_code="measurement_chain_compatibility",
            )
        if observation.observation_type in {
            ExtractedObservationType.HAS_PROPERTY,
            ExtractedObservationType.MEASUREMENT_TYPE,
            ExtractedObservationType.DERIVED_FROM,
            ExtractedObservationType.HAS_RELATIONSHIP,
        }:
            return self._normalize_explicit_relation_candidate(
                observation,
                entity_candidates_by_mention,
                created_at,
                extraction_run_id,
                predicate_code=observation.observation_type.value.lower(),
            )
        return (self._proposed_observation_candidate(observation, created_at, extraction_run_id, "Unsupported observation type"),)

    def _normalize_explicit_relation_candidate(
        self,
        observation: ExtractedObservation,
        entity_candidates_by_mention: dict[EntityId, tuple[NormalizedEntityCandidate, ...]],
        created_at,
        extraction_run_id: RunId,
        *,
        predicate_code: str,
    ) -> tuple[NormalizedRelationCandidate, ...]:
        if observation.source_entity_id is None or observation.target_entity_id is None:
            return (self._proposed_observation_candidate(observation, created_at, extraction_run_id, "Missing linked source or target mention"),)

        source_candidates = entity_candidates_by_mention.get(observation.source_entity_id, ())
        target_candidates = entity_candidates_by_mention.get(observation.target_entity_id, ())
        if not source_candidates or not target_candidates:
            return (self._proposed_observation_candidate(observation, created_at, extraction_run_id, "Linked mention candidates were not normalized"),)

        relation_candidates: list[NormalizedRelationCandidate] = []
        for source_candidate in source_candidates:
            for target_candidate in target_candidates:
                status = self._relation_status(source_candidate.status, target_candidate.status, True)
                score = min(
                    observation.extraction_confidence,
                    source_candidate.normalization_score,
                    target_candidate.normalization_score,
                )
                attributes = list(observation.attributes)
                attributes.extend(
                    [
                        ("source_candidate_status", source_candidate.status.value),
                        ("target_candidate_status", target_candidate.status.value),
                        ("source_match_method", source_candidate.match_method.value),
                        ("target_match_method", target_candidate.match_method.value),
                    ]
                )
                relation_candidates.append(
                    NormalizedRelationCandidate(
                        candidate_id=EntityId.from_seed(
                            "normalization.relation_candidate",
                            f"{observation.observation_id}:{source_candidate.candidate_id}:{target_candidate.candidate_id}:{predicate_code}:{status.value}",
                        ),
                        extraction_run_id=extraction_run_id,
                        candidate_relation_id=observation.observation_id,
                        predicate_code=predicate_code,
                        normalized_subject_table=source_candidate.matched_table or "extract.candidate_mention",
                        normalized_subject_id=source_candidate.matched_id or source_candidate.candidate_mention_id,
                        normalized_object_table=target_candidate.matched_table or "extract.candidate_mention",
                        normalized_object_id=target_candidate.matched_id or target_candidate.candidate_mention_id,
                        normalization_score=score,
                        status=status,
                        created_at=created_at,
                        source_observation=observation,
                        attributes=tuple(attributes),
                        issues=(),
                    )
                )
        return tuple(relation_candidates)

    def _normalize_textual_unit_association(
        self,
        observation: ExtractedObservation,
        entity_candidates_by_mention: dict[EntityId, tuple[NormalizedEntityCandidate, ...]],
        created_at,
        extraction_run_id: RunId,
    ) -> tuple[NormalizedRelationCandidate, ...]:
        if observation.source_entity_id is None or observation.target_entity_id is None:
            return (self._proposed_observation_candidate(observation, created_at, extraction_run_id, "Missing linked source or target mention"),)

        source_candidates = entity_candidates_by_mention.get(observation.source_entity_id, ())
        target_candidates = entity_candidates_by_mention.get(observation.target_entity_id, ())
        if not source_candidates or not target_candidates:
            return (self._proposed_observation_candidate(observation, created_at, extraction_run_id, "Linked mention candidates were not normalized"),)

        relation_candidates: list[NormalizedRelationCandidate] = []
        for source_candidate in source_candidates:
            for target_candidate in target_candidates:
                compatible, issues, quantity_code = self._assess_quantity_unit_compatibility(source_candidate, target_candidate)
                method = (
                    NormalizationMatchMethod.COMPATIBLE_QUANTITY_UNIT
                    if compatible
                    else NormalizationMatchMethod.INCOMPATIBLE_QUANTITY_UNIT
                )
                base_score = min(
                    observation.extraction_confidence,
                    source_candidate.normalization_score,
                    target_candidate.normalization_score,
                )
                score = base_score if compatible else max(0.0, round(base_score * 0.5, 5))
                status = self._relation_status(source_candidate.status, target_candidate.status, compatible)
                attributes = list(observation.attributes)
                attributes.extend(
                    [
                        ("source_candidate_status", source_candidate.status.value),
                        ("target_candidate_status", target_candidate.status.value),
                        ("source_match_method", source_candidate.match_method.value),
                        ("target_match_method", target_candidate.match_method.value),
                    ]
                )
                if quantity_code is not None:
                    attributes.append(("quantity_code", quantity_code))
                relation_candidates.append(
                    NormalizedRelationCandidate(
                        candidate_id=EntityId.from_seed(
                            "normalization.relation_candidate",
                            f"{observation.observation_id}:{source_candidate.candidate_id}:{target_candidate.candidate_id}:{method.value}:{status.value}",
                        ),
                        extraction_run_id=extraction_run_id,
                        candidate_relation_id=observation.observation_id,
                        predicate_code="textual_unit_association",
                        normalized_subject_table=source_candidate.matched_table or "extract.candidate_mention",
                        normalized_subject_id=source_candidate.matched_id or source_candidate.candidate_mention_id,
                        normalized_object_table=target_candidate.matched_table or "extract.candidate_mention",
                        normalized_object_id=target_candidate.matched_id or target_candidate.candidate_mention_id,
                        normalization_score=score,
                        status=status,
                        created_at=created_at,
                        source_observation=observation,
                        attributes=tuple(attributes),
                        issues=issues,
                    )
                )
        return tuple(relation_candidates)

    def _normalize_explicit_scaling(
        self,
        observation: ExtractedObservation,
        created_at,
        indexes: dict[ExtractedEntityType, dict[str, tuple[_IndexedEntity, ...]]],
        extraction_run_id: RunId,
    ) -> tuple[NormalizedRelationCandidate, ...]:
        attributes = dict(observation.attributes)
        engineering_unit_text = attributes.get("engineering_unit", "")
        raw_unit_text = attributes.get("raw_unit", "")
        unit_candidates = self._lookup_unit_text(engineering_unit_text, indexes, extraction_run_id, created_at)
        raw_unit_candidates = self._lookup_unit_text(raw_unit_text, indexes, extraction_run_id, created_at)
        preserved_attributes = list(observation.attributes)
        if raw_unit_candidates:
            preserved_attributes.append(("normalized_raw_unit_code", raw_unit_candidates[0].canonical_text))

        if not unit_candidates:
            return (
                NormalizedRelationCandidate(
                    candidate_id=EntityId.from_seed(
                        "normalization.relation_candidate",
                        f"{observation.observation_id}:{NormalizationMatchMethod.EXPLICIT_SCALING_LITERAL.value}:proposed",
                    ),
                    extraction_run_id=extraction_run_id,
                    candidate_relation_id=observation.observation_id,
                    predicate_code="explicit_scaling",
                    normalized_subject_table="extract.observation",
                    normalized_subject_id=observation.observation_id,
                    normalized_object_table=None,
                    normalized_object_id=None,
                    normalization_score=observation.extraction_confidence,
                    status=NormalizationCandidateStatus.PROPOSED,
                    created_at=created_at,
                    source_observation=observation,
                    attributes=tuple(preserved_attributes),
                    issues=("engineering_unit_not_normalized",),
                ),
            )

        status = NormalizationCandidateStatus.RESOLVED if len(unit_candidates) == 1 else NormalizationCandidateStatus.ALTERNATIVE
        candidates: list[NormalizedRelationCandidate] = []
        for unit_candidate in unit_candidates:
            candidates.append(
                NormalizedRelationCandidate(
                    candidate_id=EntityId.from_seed(
                        "normalization.relation_candidate",
                        f"{observation.observation_id}:{unit_candidate.candidate_id}:{NormalizationMatchMethod.EXPLICIT_SCALING_LITERAL.value}:{status.value}",
                    ),
                    extraction_run_id=extraction_run_id,
                    candidate_relation_id=observation.observation_id,
                    predicate_code="explicit_scaling",
                    normalized_subject_table="extract.observation",
                    normalized_subject_id=observation.observation_id,
                    normalized_object_table=unit_candidate.matched_table,
                    normalized_object_id=unit_candidate.matched_id,
                    normalization_score=min(observation.extraction_confidence, unit_candidate.normalization_score),
                    status=status,
                    created_at=created_at,
                    source_observation=observation,
                    attributes=tuple(preserved_attributes + [("normalized_engineering_unit_code", unit_candidate.canonical_text)]),
                )
            )
        return tuple(candidates)

    def _lookup_unit_text(
        self,
        unit_text: str,
        indexes: dict[ExtractedEntityType, dict[str, tuple[_IndexedEntity, ...]]],
        extraction_run_id: RunId,
        created_at,
    ) -> tuple[NormalizedEntityCandidate, ...]:
        normalized = self._normalize(unit_text)
        if not normalized:
            return ()
        unit_index = indexes.get(ExtractedEntityType.ENGINEERING_UNIT, {})
        indexed_candidates = unit_index.get(normalized, ())
        if not indexed_candidates:
            return ()
        pseudo_mention = ExtractedEntity(
            entity_id=EntityId.from_seed("normalization.unit_lookup", normalized),
            entity_type=ExtractedEntityType.ENGINEERING_UNIT,
            original_text=unit_text,
            normalized_text=normalized,
            document_position="fragment=normalization_lookup|page=0|section=lookup|paragraph=0|span=0:0",
            fragment_id=EntityId.from_seed("normalization.fragment", normalized),
            document_id=EntityId.from_seed("normalization.document", normalized),
            version_id=EntityId.from_seed("normalization.version", normalized),
            extraction_confidence=1.0,
            extraction_rule="normalization.unit_lookup",
            source_trace=observation_source_trace(),
            context_window=observation_context_window(unit_text),
        )
        return self._normalize_mention(pseudo_mention, indexes, created_at, extraction_run_id)

    def _assess_quantity_unit_compatibility(
        self,
        source_candidate: NormalizedEntityCandidate,
        target_candidate: NormalizedEntityCandidate,
    ) -> tuple[bool, tuple[str, ...], str | None]:
        if source_candidate.matched_table != "catalog.variable" or target_candidate.matched_table != "catalog.engineering_unit":
            return (True, (), None)
        if source_candidate.matched_id is None or target_candidate.matched_id is None:
            return (True, (), None)
        variable = self._variables_by_id.get(source_candidate.matched_id)
        unit = self._units_by_id.get(target_candidate.matched_id)
        if variable is None or unit is None or variable.physical_quantity_code is None:
            return (True, (), None)
        quantity_code = str(variable.physical_quantity_code)
        if (quantity_code, str(unit.code)) in self._compatibility_keys:
            return (True, (), quantity_code)
        quantity = self._quantities_by_code.get(quantity_code)
        if quantity is not None and quantity.dimension_code == unit.dimension_code:
            return (True, (), quantity_code)
        return (False, ("incompatible_unit_quantity",), quantity_code)

    def _build_indexes(self) -> dict[ExtractedEntityType, dict[str, tuple[_IndexedEntity, ...]]]:
        variable_like_types = {
            ExtractedEntityType.VARIABLE,
            ExtractedEntityType.MNEMONIC,
            ExtractedEntityType.ALIAS,
            ExtractedEntityType.ABBREVIATION,
            ExtractedEntityType.TAG,
            ExtractedEntityType.TAG_TOKEN,
        }
        indexes: dict[ExtractedEntityType, dict[str, tuple[_IndexedEntity, ...]]] = {}
        variable_index = self._index_repository(
            self.catalog_repository.variables,
            "catalog.variable",
            include_aliases=True,
            include_tag_patterns=True,
        )
        for mention_type in variable_like_types:
            indexes[mention_type] = variable_index
        indexes[ExtractedEntityType.PHYSICAL_QUANTITY] = self._index_repository(
            self.catalog_repository.quantities,
            "catalog.physical_quantity",
        )
        indexes[ExtractedEntityType.ENGINEERING_UNIT] = self._index_repository(
            self.catalog_repository.units,
            "catalog.engineering_unit",
            include_symbols=True,
        )
        simple_mappings = {
            ExtractedEntityType.SENSOR: (self.catalog_repository.sensors, "catalog.sensor_class"),
            ExtractedEntityType.INSTRUMENT: (self.catalog_repository.instruments, "catalog.instrument_class"),
            ExtractedEntityType.EQUIPMENT: (self.catalog_repository.equipment, "catalog.equipment_class"),
            ExtractedEntityType.SYSTEM: (self.catalog_repository.systems, "catalog.system_class"),
            ExtractedEntityType.SUBSYSTEM: (self.catalog_repository.subsystems, "catalog.subsystem_class"),
            ExtractedEntityType.PROCESS: (self.catalog_repository.processes, "catalog.process_class"),
            ExtractedEntityType.ORIGIN: (self.catalog_repository.origins, "catalog.origin_class"),
            ExtractedEntityType.PUBLISHER: (self.catalog_repository.publishers, "catalog.publisher_class"),
        }
        for mention_type, (repository, matched_table) in simple_mappings.items():
            indexes[mention_type] = self._index_repository(repository, matched_table)
        scope_targets = (
            (self.catalog_repository.units, "catalog.engineering_unit"),
            (self.catalog_repository.quantities, "catalog.physical_quantity"),
            (self.catalog_repository.principles, "catalog.measurement_principle"),
            (self.catalog_repository.classifications, "catalog.variable_classification"),
            (self.catalog_repository.origins, "catalog.origin_class"),
            (self.catalog_repository.publishers, "catalog.publisher_class"),
            (self.catalog_repository.systems, "catalog.system_class"),
            (self.catalog_repository.subsystems, "catalog.subsystem_class"),
            (self.catalog_repository.processes, "catalog.process_class"),
            (self.catalog_repository.operational_contexts, "catalog.operational_context_class"),
            (self.catalog_repository.locations, "catalog.location_class"),
            (self.catalog_repository.sensors, "catalog.sensor_class"),
            (self.catalog_repository.instruments, "catalog.instrument_class"),
            (self.catalog_repository.equipment, "catalog.equipment_class"),
            (self.catalog_repository.variables, "catalog.variable"),
        )
        indexes[ExtractedEntityType.MODEL] = self._merge_indexes(
            *(self._index_repository(repository, matched_table, include_scope_model=True) for repository, matched_table in scope_targets)
        )
        indexes[ExtractedEntityType.MANUFACTURER] = self._merge_indexes(
            *(self._index_repository(repository, matched_table, include_scope_vendor=True) for repository, matched_table in scope_targets)
        )
        return indexes

    def _index_repository(
        self,
        repository: EntityRepository[KnowledgeEntity],
        matched_table: str,
        *,
        include_aliases: bool = False,
        include_symbols: bool = False,
        include_tag_patterns: bool = False,
        include_scope_model: bool = False,
        include_scope_vendor: bool = False,
    ) -> dict[str, tuple[_IndexedEntity, ...]]:
        bucket: dict[str, list[_IndexedEntity]] = defaultdict(list)
        for entity in repository.list_all():
            bucket[self._normalize(entity.canonical_name)].append(
                _IndexedEntity(
                    catalog_entity=entity,
                    matched_table=matched_table,
                    match_method=NormalizationMatchMethod.EXACT_NAME,
                    source_field="canonical_name",
                    matched_text=entity.canonical_name,
                    normalized_key=self._normalize(entity.canonical_name),
                )
            )
            bucket[self._normalize(str(entity.code))].append(
                _IndexedEntity(
                    catalog_entity=entity,
                    matched_table=matched_table,
                    match_method=NormalizationMatchMethod.EXACT_CODE,
                    source_field="code",
                    matched_text=str(entity.code),
                    normalized_key=self._normalize(str(entity.code)),
                )
            )
            if include_aliases and isinstance(entity, Variable):
                for alias in entity.aliases:
                    alias_method = (
                        NormalizationMatchMethod.MNEMONIC_ALIAS
                        if alias.alias_type == "mnemonic"
                        else NormalizationMatchMethod.EXPLICIT_ALIAS
                    )
                    bucket[self._normalize(alias.alias)].append(
                        _IndexedEntity(
                            catalog_entity=entity,
                            matched_table=matched_table,
                            match_method=alias_method,
                            source_field=f"alias:{alias.alias_type}",
                            matched_text=alias.alias,
                            normalized_key=self._normalize(alias.alias),
                        )
                    )
            if include_symbols and isinstance(entity, EngineeringUnit):
                bucket[self._normalize(entity.symbol)].append(
                    _IndexedEntity(
                        catalog_entity=entity,
                        matched_table=matched_table,
                        match_method=NormalizationMatchMethod.EXACT_SYMBOL,
                        source_field="symbol",
                        matched_text=entity.symbol,
                        normalized_key=self._normalize(entity.symbol),
                    )
                )
            if include_tag_patterns:
                for source_field, source_text in self._tag_pattern_sources(entity):
                    pattern_key = self._tag_pattern(source_text)
                    if not pattern_key:
                        continue
                    bucket[pattern_key].append(
                        _IndexedEntity(
                            catalog_entity=entity,
                            matched_table=matched_table,
                            match_method=NormalizationMatchMethod.TAG_PATTERN,
                            source_field=source_field,
                            matched_text=source_text,
                            normalized_key=pattern_key,
                        )
                    )
            if include_scope_model and entity.scope.model_family:
                normalized_model = self._normalize(entity.scope.model_family)
                bucket[normalized_model].append(
                    _IndexedEntity(
                        catalog_entity=entity,
                        matched_table=matched_table,
                        match_method=NormalizationMatchMethod.MODEL_SCOPE,
                        source_field="scope.model_family",
                        matched_text=entity.scope.model_family,
                        normalized_key=normalized_model,
                    )
                )
            if include_scope_vendor and entity.scope.vendor:
                normalized_vendor = self._normalize(entity.scope.vendor)
                bucket[normalized_vendor].append(
                    _IndexedEntity(
                        catalog_entity=entity,
                        matched_table=matched_table,
                        match_method=NormalizationMatchMethod.VENDOR_SCOPE,
                        source_field="scope.vendor",
                        matched_text=entity.scope.vendor,
                        normalized_key=normalized_vendor,
                    )
                )
        return {key: tuple(sorted(values, key=self._indexed_entity_sort_key)) for key, values in bucket.items()}

    def _merge_indexes(self, *indexes: dict[str, tuple[_IndexedEntity, ...]]) -> dict[str, tuple[_IndexedEntity, ...]]:
        bucket: dict[str, list[_IndexedEntity]] = defaultdict(list)
        for index in indexes:
            for key, values in index.items():
                bucket[key].extend(values)
        return {key: tuple(sorted(values, key=self._indexed_entity_sort_key)) for key, values in bucket.items()}

    def _lookup_indexed_candidates(
        self,
        index: dict[str, tuple[_IndexedEntity, ...]],
        mention: ExtractedEntity,
    ) -> tuple[_IndexedEntity, ...]:
        exact_candidates = index.get(mention.normalized_text, ())
        if exact_candidates:
            return tuple(sorted(exact_candidates, key=self._indexed_entity_sort_key))

        if mention.entity_type in {ExtractedEntityType.TAG, ExtractedEntityType.TAG_TOKEN}:
            pattern_key = self._tag_pattern(mention.original_text)
            if not pattern_key:
                return ()
            tag_pattern_candidates = tuple(
                candidate
                for candidate in index.get(pattern_key, ())
                if candidate.match_method == NormalizationMatchMethod.TAG_PATTERN
            )
            return tuple(sorted(tag_pattern_candidates, key=self._indexed_entity_sort_key))

        deduped: dict[tuple[str, str, str, str, str], _IndexedEntity] = {}
        for key in self._mention_lookup_keys(mention):
            for candidate in index.get(key, ()):
                deduped.setdefault(
                    (
                        str(candidate.catalog_entity.entity_id),
                        candidate.match_method.value,
                        candidate.source_field,
                        candidate.matched_text,
                        candidate.normalized_key,
                    ),
                    candidate,
                )
        return tuple(sorted(deduped.values(), key=self._indexed_entity_sort_key))

    def _mention_lookup_keys(self, mention: ExtractedEntity) -> tuple[str, ...]:
        keys = [mention.normalized_text]
        if mention.entity_type in {ExtractedEntityType.TAG, ExtractedEntityType.TAG_TOKEN}:
            pattern_key = self._tag_pattern(mention.original_text)
            if pattern_key and pattern_key not in keys:
                keys.append(pattern_key)
        return tuple(keys)

    def _tag_pattern_sources(self, entity: KnowledgeEntity) -> tuple[tuple[str, str], ...]:
        sources: list[tuple[str, str]] = [
            ("tag_pattern:canonical_name", entity.canonical_name),
            ("tag_pattern:code", str(entity.code)),
        ]
        if isinstance(entity, Variable):
            for alias in entity.aliases:
                sources.append((f"tag_pattern:alias:{alias.alias_type}", alias.alias))
        return tuple(sources)

    def _proposed_entity_candidate(
        self,
        mention: ExtractedEntity,
        created_at,
        extraction_run_id: RunId,
        *,
        match_method: NormalizationMatchMethod,
        explanation: str,
    ) -> NormalizedEntityCandidate:
        evidence = NormalizationEvidence(
            matched_text=mention.original_text,
            normalized_matched_text=mention.normalized_text,
            source_field="original_text",
            explanation=explanation,
        )
        return NormalizedEntityCandidate(
            candidate_id=EntityId.from_seed(
                "normalization.entity_candidate",
                f"{mention.entity_id}:{match_method.value}:proposal:{mention.normalized_text}",
            ),
            extraction_run_id=extraction_run_id,
            candidate_mention_id=mention.entity_id,
            entity_type=mention.entity_type,
            mention_text=mention.original_text,
            matched_table=None,
            matched_id=None,
            canonical_text=mention.original_text,
            match_method=match_method,
            normalization_score=mention.extraction_confidence,
            is_new_concept_proposal=True,
            status=NormalizationCandidateStatus.PROPOSED,
            created_at=created_at,
            source_mention=mention,
            evidence=evidence,
            supporting_evidences=(evidence,),
        )

    def _proposed_observation_candidate(
        self,
        observation: ExtractedObservation,
        created_at,
        extraction_run_id: RunId,
        reason: str,
    ) -> NormalizedRelationCandidate:
        return NormalizedRelationCandidate(
            candidate_id=EntityId.from_seed(
                "normalization.relation_candidate",
                f"{observation.observation_id}:proposal:{observation.observation_type.value}",
            ),
            extraction_run_id=extraction_run_id,
            candidate_relation_id=observation.observation_id,
            predicate_code=observation.observation_type.value.lower(),
            normalized_subject_table="extract.observation",
            normalized_subject_id=observation.observation_id,
            normalized_object_table=None,
            normalized_object_id=None,
            normalization_score=observation.extraction_confidence,
            status=NormalizationCandidateStatus.PROPOSED,
            created_at=created_at,
            source_observation=observation,
            attributes=observation.attributes,
            issues=(reason,),
        )

    def _document_local_entity_candidate(
        self,
        mention: ExtractedEntity,
        created_at,
        extraction_run_id: RunId,
    ) -> NormalizedEntityCandidate:
        evidence = NormalizationEvidence(
            matched_text=mention.original_text,
            normalized_matched_text=mention.normalized_text,
            source_field="original_text",
            explanation="Document-local Energistics schema anchor resolved deterministically from structural table content",
        )
        matched_id = EntityId.from_seed(
            "normalization.document_local_entity",
            f"{mention.document_id}:{mention.version_id}:{mention.normalized_text}:{mention.extraction_rule}",
        )
        return NormalizedEntityCandidate(
            candidate_id=EntityId.from_seed(
                "normalization.entity_candidate",
                f"{mention.entity_id}:{matched_id}:{NormalizationMatchMethod.EXPLICIT_RELATION.value}:document_local",
            ),
            extraction_run_id=extraction_run_id,
            candidate_mention_id=mention.entity_id,
            entity_type=mention.entity_type,
            mention_text=mention.original_text,
            matched_table="extract.document_local_entity",
            matched_id=matched_id,
            canonical_text=mention.original_text,
            match_method=NormalizationMatchMethod.EXPLICIT_RELATION,
            normalization_score=mention.extraction_confidence,
            is_new_concept_proposal=False,
            status=NormalizationCandidateStatus.RESOLVED,
            created_at=created_at,
            source_mention=mention,
            evidence=evidence,
            supporting_evidences=(evidence,),
        )

    def _relation_status(
        self,
        source_status: NormalizationCandidateStatus,
        target_status: NormalizationCandidateStatus,
        compatible: bool,
    ) -> NormalizationCandidateStatus:
        if source_status == NormalizationCandidateStatus.RESOLVED and target_status == NormalizationCandidateStatus.RESOLVED and compatible:
            return NormalizationCandidateStatus.RESOLVED
        if source_status == NormalizationCandidateStatus.PROPOSED or target_status == NormalizationCandidateStatus.PROPOSED:
            return NormalizationCandidateStatus.PROPOSED
        return NormalizationCandidateStatus.ALTERNATIVE

    def _indexed_entity_sort_key(self, candidate: _IndexedEntity) -> tuple[int, str, str, str]:
        return (
            self._match_method_rank(candidate.match_method),
            candidate.catalog_entity.canonical_name.casefold(),
            str(candidate.catalog_entity.code),
            str(candidate.catalog_entity.entity_id),
        )

    def _entity_candidate_sort_key(self, candidate: NormalizedEntityCandidate) -> tuple[str, int | None, int | None, str, int, str, str]:
        return (
            str(candidate.candidate_mention_id),
            0,
            0,
            candidate.status.value,
            self._match_method_rank(candidate.match_method),
            candidate.canonical_text.casefold(),
            str(candidate.candidate_id),
        )

    def _relation_candidate_sort_key(self, candidate: NormalizedRelationCandidate) -> tuple[str, str, str, str]:
        return (
            str(candidate.candidate_relation_id),
            candidate.status.value,
            candidate.predicate_code,
            str(candidate.candidate_id),
        )

    def _mention_sort_key(self, mention: ExtractedEntity) -> tuple[str, int | None, int | None, str]:
        return (
            -1 if mention.source_trace.start_offset is None else mention.source_trace.start_offset,
            -1 if mention.source_trace.end_offset is None else mention.source_trace.end_offset,
            str(mention.fragment_id),
            str(mention.entity_id),
        )

    def _observation_sort_key(self, observation: ExtractedObservation) -> tuple[str, int | None, int | None, str]:
        return (
            -1 if observation.source_trace.start_offset is None else observation.source_trace.start_offset,
            -1 if observation.source_trace.end_offset is None else observation.source_trace.end_offset,
            str(observation.fragment_id),
            str(observation.observation_id),
        )

    def _evidence_sort_key(self, evidence: NormalizationEvidence) -> tuple[str, str, str, str]:
        return (
            evidence.normalized_matched_text,
            evidence.source_field,
            evidence.explanation,
            evidence.matched_text,
        )

    def _unique_evidences(self, evidences: list[NormalizationEvidence]) -> tuple[NormalizationEvidence, ...]:
        unique: dict[tuple[str, str, str], NormalizationEvidence] = {}
        for evidence in evidences:
            key = (evidence.normalized_matched_text, evidence.source_field, evidence.explanation)
            unique.setdefault(key, evidence)
        return tuple(unique.values())

    def _match_method_rank(self, method: NormalizationMatchMethod) -> int:
        order = {
            NormalizationMatchMethod.EXACT_NAME: 0,
            NormalizationMatchMethod.EXACT_SYMBOL: 1,
            NormalizationMatchMethod.MNEMONIC_ALIAS: 2,
            NormalizationMatchMethod.EXPLICIT_ALIAS: 3,
            NormalizationMatchMethod.EXACT_CODE: 4,
            NormalizationMatchMethod.TAG_PATTERN: 5,
            NormalizationMatchMethod.MODEL_SCOPE: 6,
            NormalizationMatchMethod.VENDOR_SCOPE: 7,
            NormalizationMatchMethod.COMPATIBLE_QUANTITY_UNIT: 8,
            NormalizationMatchMethod.INCOMPATIBLE_QUANTITY_UNIT: 9,
            NormalizationMatchMethod.EXPLICIT_SCALING_LITERAL: 10,
            NormalizationMatchMethod.EXPLICIT_RELATION: 11,
            NormalizationMatchMethod.NO_CATALOG_MATCH: 12,
            NormalizationMatchMethod.UNSUPPORTED_ENTITY_TYPE: 13,
        }
        return order[method]

    def _base_score(self, method: NormalizationMatchMethod) -> float:
        scores = {
            NormalizationMatchMethod.EXACT_NAME: 1.0,
            NormalizationMatchMethod.EXACT_SYMBOL: 1.0,
            NormalizationMatchMethod.MNEMONIC_ALIAS: 0.995,
            NormalizationMatchMethod.EXPLICIT_ALIAS: 0.99,
            NormalizationMatchMethod.EXACT_CODE: 0.98,
            NormalizationMatchMethod.TAG_PATTERN: 0.97,
            NormalizationMatchMethod.MODEL_SCOPE: 0.96,
            NormalizationMatchMethod.VENDOR_SCOPE: 0.96,
            NormalizationMatchMethod.NO_CATALOG_MATCH: 1.0,
            NormalizationMatchMethod.UNSUPPORTED_ENTITY_TYPE: 1.0,
            NormalizationMatchMethod.COMPATIBLE_QUANTITY_UNIT: 1.0,
            NormalizationMatchMethod.INCOMPATIBLE_QUANTITY_UNIT: 0.5,
            NormalizationMatchMethod.EXPLICIT_SCALING_LITERAL: 1.0,
            NormalizationMatchMethod.EXPLICIT_RELATION: 1.0,
        }
        return scores[method]

    def _explanation_for(self, method: NormalizationMatchMethod, canonical_name: str, matched_text: str) -> str:
        if method == NormalizationMatchMethod.EXACT_NAME:
            return f"Canonical name matched exactly: {canonical_name}"
        if method == NormalizationMatchMethod.EXACT_SYMBOL:
            return f"Engineering unit symbol matched exactly: {matched_text}"
        if method == NormalizationMatchMethod.MNEMONIC_ALIAS:
            return f"Mnemonic alias matched exactly: {matched_text}"
        if method == NormalizationMatchMethod.EXPLICIT_ALIAS:
            return f"Explicit alias matched exactly: {matched_text}"
        if method == NormalizationMatchMethod.EXACT_CODE:
            return f"Catalog code matched exactly: {matched_text}"
        if method == NormalizationMatchMethod.TAG_PATTERN:
            return f"Tag pattern matched deterministically: {matched_text}"
        if method == NormalizationMatchMethod.MODEL_SCOPE:
            return f"Catalog scope model family matched exactly: {matched_text}"
        if method == NormalizationMatchMethod.VENDOR_SCOPE:
            return f"Catalog scope vendor matched exactly: {matched_text}"
        return f"Observed evidence matched by {method.value}: {matched_text}"

    def _normalize(self, text: str) -> str:
        return " ".join(text.split()).strip().lower()

    def _tag_pattern(self, text: str) -> str:
        return " ".join(re.sub(r"[^a-z0-9]+", " ", text.lower()).split()).strip()


def observation_source_trace():
    from drilling_knowledge.extraction.domain import ExtractionSourceTrace

    return ExtractionSourceTrace(page_number=0, paragraph_ordinal=0, start_offset=0, end_offset=0)


def observation_context_window(text: str):
    from drilling_knowledge.extraction.domain import ContextWindow

    return ContextWindow(match_text=text)


