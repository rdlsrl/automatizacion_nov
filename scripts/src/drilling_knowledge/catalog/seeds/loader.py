"""Idempotent seed loaders for the catalog core and initial IDKB backbone."""

from __future__ import annotations

from dataclasses import dataclass

from drilling_knowledge.catalog.repositories.memory import InMemoryCatalogRepository, InMemoryEntityRepository
from drilling_knowledge.catalog.seeds.definitions import (
    CatalogSeedBundle,
    IdkbSeedBundle,
    default_catalog_seed_bundle,
    default_idkb_seed_bundle,
)
from drilling_knowledge.catalog.validators import CatalogInvariantValidator
from drilling_knowledge.common.validation import ValidationReport
from drilling_knowledge.idkb.repositories import InMemoryIdkbRepository
from drilling_knowledge.idkb.validators import IdkbBackboneValidator


@dataclass(frozen=True, slots=True)
class SeedLoadSnapshot:
    catalog: InMemoryCatalogRepository
    idkb: InMemoryIdkbRepository

    @classmethod
    def empty(cls) -> "SeedLoadSnapshot":
        return cls(catalog=InMemoryCatalogRepository.empty(), idkb=InMemoryIdkbRepository.empty())


@dataclass(frozen=True, slots=True)
class SeedCatalogsAndIdkbBackboneLoader:
    """Loads the conservative Sprint 3 semantic backbone without destructive deduplication."""

    def load(
        self,
        snapshot: SeedLoadSnapshot | None = None,
        *,
        catalog_bundle: CatalogSeedBundle | None = None,
        idkb_bundle: IdkbSeedBundle | None = None,
    ) -> SeedLoadSnapshot:
        base_snapshot = snapshot or SeedLoadSnapshot.empty()
        merged_catalog = self._merge_catalog(base_snapshot.catalog, catalog_bundle or default_catalog_seed_bundle())
        merged_idkb = self._merge_idkb(base_snapshot.idkb, idkb_bundle or default_idkb_seed_bundle())

        report = ValidationReport()
        report.issues.extend(CatalogInvariantValidator(merged_catalog).validate().issues)
        report.issues.extend(IdkbBackboneValidator(merged_idkb).validate().issues)
        report.require_valid(code="seed_load_validation_failed")
        return SeedLoadSnapshot(catalog=merged_catalog, idkb=merged_idkb)

    def _merge_catalog(self, repository: InMemoryCatalogRepository, bundle: CatalogSeedBundle) -> InMemoryCatalogRepository:
        return InMemoryCatalogRepository(
            units=repository.units.merge(bundle.units),
            quantities=repository.quantities.merge(bundle.quantities),
            principles=repository.principles.merge(bundle.principles),
            quantity_unit_compatibilities=repository.quantity_unit_compatibilities.merge(bundle.quantity_unit_compatibilities),
            classifications=repository.classifications.merge(bundle.classifications),
            origins=repository.origins.merge(bundle.origins),
            publishers=repository.publishers.merge(bundle.publishers),
            systems=repository.systems.merge(bundle.systems),
            subsystems=repository.subsystems.merge(bundle.subsystems),
            processes=repository.processes.merge(bundle.processes),
            operational_contexts=repository.operational_contexts.merge(bundle.operational_contexts),
            locations=repository.locations.merge(bundle.locations),
            sensors=repository.sensors.merge(bundle.sensors),
            instruments=repository.instruments.merge(bundle.instruments),
            equipment=repository.equipment.merge(bundle.equipment),
            variables=repository.variables,
        )

    def _merge_idkb(self, repository: InMemoryIdkbRepository, bundle: IdkbSeedBundle) -> InMemoryIdkbRepository:
        return InMemoryIdkbRepository(
            domains=repository.domains.merge(bundle.domains),
            identifier_definitions=repository.identifier_definitions.merge(bundle.identifier_definitions),
            article_templates=repository.article_templates.merge(bundle.article_templates),
            maturity_levels=repository.maturity_levels.merge(bundle.maturity_levels),
            knowledge_packs=repository.knowledge_packs.merge(bundle.knowledge_packs),
        )