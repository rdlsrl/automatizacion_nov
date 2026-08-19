from __future__ import annotations

from pathlib import Path
import json
import unittest

from drilling_knowledge.common.ids import EntityId
from drilling_knowledge.projections.search import SearchSynonymCatalog, SearchSynonymCatalogLoader, SearchSynonymEntry, SynonymStatus


class SearchSynonymGovernanceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.root = Path("/mnt/mariadb/autom_nov/autom_nov/scripts/db/opensearch/synonyms")

    def test_catalog_loads_documented_synonym_sets(self) -> None:
        catalog = SearchSynonymCatalogLoader.load(self.root)

        self.assertEqual(
            {entry.set_name for entry in catalog.entries},
            {
                "variable_category_synonyms",
                "rig_subsystem_synonyms",
                "measurement_principle_synonyms",
                "unit_lexical_variants",
                "english_spanish_term_variants",
                "vendor_product_family_aliases",
            },
        )

    def test_duplicate_active_term_sets_are_rejected(self) -> None:
        synonym_id = EntityId.from_seed("search.synonym.test", "duplicate")
        entry = SearchSynonymEntry(
            synonym_id=synonym_id,
            set_name="unit_lexical_variants",
            revision=1,
            status=SynonymStatus.ACTIVE,
            terms=("psi", "pounds per square inch"),
            provenance=("catalog.engineering_unit:unit.psi",),
        )
        duplicate_terms = SearchSynonymEntry(
            synonym_id=EntityId.from_seed("search.synonym.test", "duplicate-2"),
            set_name="unit_lexical_variants",
            revision=1,
            status=SynonymStatus.ACTIVE,
            terms=("pounds per square inch", "psi"),
            provenance=("catalog.engineering_unit:unit.psi",),
        )

        with self.assertRaises(ValueError):
            SearchSynonymCatalog((entry, duplicate_terms))

    def test_catalog_serialization_is_stable(self) -> None:
        first = SearchSynonymCatalogLoader.load(self.root)
        second = SearchSynonymCatalogLoader.load(self.root)

        self.assertEqual(json.dumps(first.as_serializable(), sort_keys=True), json.dumps(second.as_serializable(), sort_keys=True))