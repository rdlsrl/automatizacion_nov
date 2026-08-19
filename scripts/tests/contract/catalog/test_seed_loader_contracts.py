from __future__ import annotations

from dataclasses import replace
import unittest

from drilling_knowledge.catalog.domain import CatalogCode, EngineeringUnit, LocalizedName
from drilling_knowledge.catalog.seeds import SeedCatalogsAndIdkbBackboneLoader, default_catalog_seed_bundle
from drilling_knowledge.common.exceptions import DuplicateCanonicalCodeError
from drilling_knowledge.common.ids import EntityId


class SeedLoaderContractTests(unittest.TestCase):
    def test_repeated_load_does_not_duplicate_structural_records(self) -> None:
        loader = SeedCatalogsAndIdkbBackboneLoader()

        first = loader.load()
        second = loader.load(first)

        self.assertEqual(len(first.catalog.units.list_all()), len(second.catalog.units.list_all()))
        self.assertEqual(len(first.catalog.systems.list_all()), len(second.catalog.systems.list_all()))
        self.assertEqual(len(first.idkb.knowledge_packs.list_all()), len(second.idkb.knowledge_packs.list_all()))

    def test_invalid_canonical_collision_raises(self) -> None:
        bundle = default_catalog_seed_bundle()
        conflicting_bundle = replace(
            bundle,
            units=bundle.units
            + (
                EngineeringUnit(
                    entity_id=EntityId.from_seed("test.unit", "psi_conflict"),
                    code=CatalogCode("psi"),
                    names=LocalizedName(canonical="PSI Conflict"),
                    description="Conflicting duplicate of psi in same scope.",
                    symbol="psi_conflict",
                    dimension_code="pressure",
                ),
            ),
        )

        with self.assertRaises(DuplicateCanonicalCodeError):
            SeedCatalogsAndIdkbBackboneLoader().load(catalog_bundle=conflicting_bundle)

    def test_golden_seed_snapshot_is_stable(self) -> None:
        snapshot = SeedCatalogsAndIdkbBackboneLoader().load()

        self.assertEqual(
            [str(unit.code) for unit in snapshot.catalog.units.list_all()],
            ["degc", "ft", "gpm", "klbf", "kpa", "lpm", "m", "pct", "psi", "rpm"],
        )
        self.assertEqual(
            [str(domain.code) for domain in snapshot.idkb.domains.list_all()],
            [
                "control_instrumentation_and_data_systems",
                "directional_and_downhole_domains",
                "mechanical_and_hydraulic_systems",
                "operational_knowledge_and_expert_interpretation",
                "pressure_control_well_integrity_and_completion_domains",
                "rig_and_system_foundations",
            ],
        )