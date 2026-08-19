from __future__ import annotations

from dataclasses import replace
import unittest

from drilling_knowledge.catalog.domain import CatalogCode, CatalogScope, LocalizedName, SubsystemClass, Variable
from drilling_knowledge.catalog.repositories import InMemoryCatalogRepository
from drilling_knowledge.catalog.repositories.memory import InMemoryEntityRepository
from drilling_knowledge.catalog.seeds import (
    CatalogSeedBundle,
    SeedCatalogsAndIdkbBackboneLoader,
    SeedLoadSnapshot,
    default_catalog_seed_bundle,
)
from drilling_knowledge.catalog.domain import QuantityUnitCompatibility
from drilling_knowledge.common.exceptions import ValidationError
from drilling_knowledge.common.ids import EntityId


class SeedLoaderTests(unittest.TestCase):
    def test_seed_loader_is_idempotent(self) -> None:
        loader = SeedCatalogsAndIdkbBackboneLoader()

        first = loader.load()
        second = loader.load(first)

        self.assertEqual(first.catalog.units.list_all(), second.catalog.units.list_all())
        self.assertEqual(first.catalog.quantities.list_all(), second.catalog.quantities.list_all())
        self.assertEqual(first.idkb.domains.list_all(), second.idkb.domains.list_all())
        self.assertEqual(first.idkb.knowledge_packs.list_all(), second.idkb.knowledge_packs.list_all())

    def test_seed_loader_preserves_contextual_coexistence(self) -> None:
        preserved_variables = InMemoryEntityRepository(
            (
                Variable(
                    entity_id=EntityId.from_seed("test.variable", "doc_a"),
                    code=CatalogCode("standpipe_pressure"),
                    names=LocalizedName(canonical="Standpipe Pressure"),
                    description="Observed in document A.",
                    scope=CatalogScope(domain="surface", publisher="publisher_a", source_document="doc_a"),
                ),
                Variable(
                    entity_id=EntityId.from_seed("test.variable", "doc_b"),
                    code=CatalogCode("standpipe_pressure"),
                    names=LocalizedName(canonical="Standpipe Pressure"),
                    description="Observed in document B.",
                    scope=CatalogScope(domain="surface", publisher="publisher_b", source_document="doc_b"),
                ),
            )
        )
        base_snapshot = SeedLoadSnapshot(
            catalog=InMemoryCatalogRepository.empty(),
            idkb=loader_idkb_empty(),
        )
        base_snapshot.catalog.variables = preserved_variables
        loader = SeedCatalogsAndIdkbBackboneLoader()

        loaded = loader.load(base_snapshot)

        self.assertEqual(len(loaded.catalog.variables.get_by_code(CatalogCode("standpipe_pressure"))), 2)

    def test_seed_loader_rejects_broken_subsystem_reference(self) -> None:
        loader = SeedCatalogsAndIdkbBackboneLoader()
        bundle = default_catalog_seed_bundle()
        invalid_bundle = replace(
            bundle,
            subsystems=bundle.subsystems + (
                SubsystemClass(
                    entity_id=EntityId.from_seed("test.subsystem", "invalid"),
                    code=CatalogCode("invalid_subsystem"),
                    names=LocalizedName(canonical="Invalid Subsystem"),
                    description="Invalid subsystem with unknown system.",
                    system_code=CatalogCode("missing_system"),
                ),
            ),
        )

        with self.assertRaises(ValidationError):
            loader.load(catalog_bundle=invalid_bundle)

    def test_seed_loader_rejects_incompatible_quantity_unit(self) -> None:
        loader = SeedCatalogsAndIdkbBackboneLoader()
        bundle = default_catalog_seed_bundle()
        invalid_bundle = replace(
            bundle,
            quantity_unit_compatibilities=bundle.quantity_unit_compatibilities + (
                QuantityUnitCompatibility(
                    entity_id=EntityId.from_seed("test.compatibility", "invalid"),
                    code=CatalogCode("pressure.rpm"),
                    names=LocalizedName(canonical="pressure to rpm"),
                    description="Invalid compatibility mapping.",
                    quantity_code=CatalogCode("pressure"),
                    unit_code=CatalogCode("rpm"),
                ),
            ),
        )

        with self.assertRaises(ValidationError):
            loader.load(catalog_bundle=invalid_bundle)


def loader_idkb_empty():
    from drilling_knowledge.idkb import InMemoryIdkbRepository

    return InMemoryIdkbRepository.empty()