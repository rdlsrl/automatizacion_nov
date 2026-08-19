from __future__ import annotations

from dataclasses import replace
import unittest

from drilling_knowledge.catalog.seeds import IdkbSeedBundle, SeedCatalogsAndIdkbBackboneLoader, default_idkb_seed_bundle
from drilling_knowledge.catalog.domain import CatalogCode, LocalizedName
from drilling_knowledge.common.exceptions import ValidationError
from drilling_knowledge.common.ids import EntityId
from drilling_knowledge.idkb.domain import KnowledgeDomain


class IdkbBackboneLoaderTests(unittest.TestCase):
    def test_default_backbone_loads_expected_domains_and_maturity_levels(self) -> None:
        snapshot = SeedCatalogsAndIdkbBackboneLoader().load()

        self.assertEqual(len(snapshot.idkb.domains.list_all()), 6)
        self.assertEqual([str(level.code) for level in snapshot.idkb.maturity_levels.list_all()], ["m0", "m1", "m2", "m3", "m4", "m5"])

    def test_domain_cycle_is_rejected(self) -> None:
        bundle = default_idkb_seed_bundle()
        cycle_bundle = replace(
            bundle,
            domains=(
                KnowledgeDomain(
                    entity_id=EntityId.from_seed("test.domain", "alpha"),
                    code=CatalogCode("alpha"),
                    names=LocalizedName(canonical="Alpha"),
                    description="Alpha domain.",
                    volume_code="volume_test",
                    parent_code=CatalogCode("beta"),
                ),
                KnowledgeDomain(
                    entity_id=EntityId.from_seed("test.domain", "beta"),
                    code=CatalogCode("beta"),
                    names=LocalizedName(canonical="Beta"),
                    description="Beta domain.",
                    volume_code="volume_test",
                    parent_code=CatalogCode("alpha"),
                ),
            ),
        )

        with self.assertRaises(ValidationError):
            SeedCatalogsAndIdkbBackboneLoader().load(idkb_bundle=cycle_bundle)