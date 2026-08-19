from __future__ import annotations

import unittest

from drilling_knowledge.catalog.domain import CatalogCode, CatalogScope, EngineeringUnit, LocalizedName, Variable
from drilling_knowledge.catalog.repositories.memory import InMemoryEntityRepository
from drilling_knowledge.common.exceptions import DuplicateCanonicalCodeError
from drilling_knowledge.common.ids import EntityId


class RepositoryContractTests(unittest.TestCase):
    def test_in_memory_entity_repository_implements_basic_read_contract(self) -> None:
        unit = EngineeringUnit(
            entity_id=EntityId.new(),
            code=CatalogCode("psi"),
            names=LocalizedName(canonical="PSI"),
            description="Pressure unit pounds per square inch.",
            symbol="psi",
            dimension_code="pressure",
        )
        repository = InMemoryEntityRepository((unit,))

        self.assertEqual(repository.get_by_code(CatalogCode("psi")), (unit,))
        self.assertEqual(repository.list_all(), (unit,))

    def test_duplicate_canonical_code_in_same_scope_and_active_version_fails(self) -> None:
        first = EngineeringUnit(
            entity_id=EntityId.new(),
            code=CatalogCode("psi"),
            names=LocalizedName(canonical="PSI"),
            description="Pressure unit pounds per square inch.",
            symbol="psi",
            dimension_code="pressure",
        )
        second = EngineeringUnit(
            entity_id=EntityId.new(),
            code=CatalogCode("psi"),
            names=LocalizedName(canonical="PSI Duplicate"),
            description="Alternative record without valid semantic differentiation.",
            symbol="psi-alt",
            dimension_code="pressure",
        )

        with self.assertRaises(DuplicateCanonicalCodeError):
            InMemoryEntityRepository((first, second))

    def test_list_all_preserves_repeated_valid_records_with_stable_order(self) -> None:
        first = Variable(
            entity_id=EntityId.new(),
            code=CatalogCode("standpipe_pressure"),
            names=LocalizedName(canonical="Standpipe Pressure"),
            description="Observed in document A.",
            scope=CatalogScope(domain="surface", source_document="doc-b", publisher="pae"),
        )
        second = Variable(
            entity_id=EntityId.new(),
            code=CatalogCode("standpipe_pressure"),
            names=LocalizedName(canonical="Standpipe Pressure"),
            description="Observed in document B.",
            scope=CatalogScope(domain="surface", source_document="doc-a", publisher="pae"),
        )
        repository = InMemoryEntityRepository((first, second))

        self.assertEqual(len(repository.get_by_code(CatalogCode("standpipe_pressure"))), 2)
        self.assertEqual(
            [entity.scope.label() for entity in repository.list_all()],
            [
                "surface|publisher=pae|source_document=doc-a",
                "surface|publisher=pae|source_document=doc-b",
            ],
        )
