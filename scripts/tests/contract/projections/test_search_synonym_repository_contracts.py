from __future__ import annotations

import json
import unittest

from drilling_knowledge.common.exceptions import ConflictError
from drilling_knowledge.common.ids import EntityId
from drilling_knowledge.projections.search import InMemorySearchSynonymRepository, SearchSynonymCatalogLoader, SearchSynonymEntry, SynonymStatus


class SearchSynonymRepositoryContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.catalog = SearchSynonymCatalogLoader.load("/mnt/mariadb/autom_nov/autom_nov/scripts/db/opensearch/synonyms")
        self.first = self.catalog.entries[0]

    def test_append_only_recovery(self) -> None:
        repository = InMemorySearchSynonymRepository().append_entry(self.first)

        self.assertEqual(repository.get_history(self.first.synonym_id), (self.first,))
        self.assertEqual(repository.list_entries(), (self.first,))

    def test_identical_reappend_is_accepted(self) -> None:
        repository = InMemorySearchSynonymRepository().append_entry(self.first)

        self.assertIs(repository.append_entry(self.first), repository)

    def test_revision_collision_is_rejected(self) -> None:
        repository = InMemorySearchSynonymRepository().append_entry(self.first)
        conflicting = SearchSynonymEntry(
            synonym_id=self.first.synonym_id,
            set_name=self.first.set_name,
            revision=self.first.revision,
            status=SynonymStatus.INACTIVE,
            terms=self.first.terms,
            provenance=self.first.provenance,
        )

        with self.assertRaises(ConflictError):
            repository.append_entry(conflicting)

    def test_sequential_revision_history_is_preserved(self) -> None:
        repository = InMemorySearchSynonymRepository().append_entry(
            SearchSynonymEntry(
                synonym_id=EntityId.from_seed("search.synonym.contract", "history"),
                set_name="unit_lexical_variants",
                revision=1,
                status=SynonymStatus.INACTIVE,
                terms=("psi", "pounds per square inch"),
                provenance=("catalog.engineering_unit:unit.psi",),
            )
        )
        second = SearchSynonymEntry(
            synonym_id=EntityId.from_seed("search.synonym.contract", "history"),
            set_name="unit_lexical_variants",
            revision=2,
            status=SynonymStatus.ACTIVE,
            terms=("psi", "pounds per square inch"),
            provenance=("catalog.engineering_unit:unit.psi",),
        )
        repository = repository.append_entry(second)

        self.assertEqual(repository.get_history(second.synonym_id), repository.list_entries())
        self.assertEqual(json.dumps(repository.list_entries()[1].as_serializable(), sort_keys=True), json.dumps(second.as_serializable(), sort_keys=True))