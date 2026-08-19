from __future__ import annotations

import unittest

from drilling_knowledge.catalog.domain import (
    CatalogCode,
    CatalogScope,
    EngineeringUnit,
    LocalizedName,
    PhysicalQuantity,
    Variable,
    VariableAlias,
)
from drilling_knowledge.common.ids import EntityId


class CatalogDomainEntityTests(unittest.TestCase):
    def test_catalog_code_normalizes_to_lowercase(self) -> None:
        code = CatalogCode(" StandPipe.Pressure ")

        self.assertEqual(str(code), "standpipe.pressure")

    def test_engineering_unit_requires_symbol_and_dimension(self) -> None:
        unit = EngineeringUnit(
            entity_id=EntityId.new(),
            code=CatalogCode("psi"),
            names=LocalizedName(canonical="PSI", spanish="psi"),
            description="Pressure unit pounds per square inch.",
            symbol="psi",
            dimension_code="pressure",
        )

        self.assertEqual(unit.symbol, "psi")
        self.assertEqual(unit.dimension_code, "pressure")

    def test_variable_supports_aliases_scope_and_semantic_classification(self) -> None:
        variable = Variable(
            entity_id=EntityId.new(),
            code=CatalogCode("standpipe_pressure"),
            names=LocalizedName(canonical="Standpipe Pressure", spanish="Presion de standpipe"),
            description="Surface pressure measured at the standpipe manifold.",
            scope=CatalogScope(domain="surface", vendor="generic"),
            physical_quantity_code=CatalogCode("pressure"),
            canonical_unit_code=CatalogCode("psi"),
            classification_codes=(CatalogCode("primary"),),
            origin_codes=(CatalogCode("direct_sensor"),),
            subsystem_codes=(CatalogCode("standpipe_system"),),
            aliases=(VariableAlias(alias="SPP"),),
            evidence_requirement_level="strict",
            ambiguity_level="low",
        )

        self.assertEqual(variable.aliases[0].alias, "SPP")
        self.assertEqual(variable.scope.label(), "surface|vendor=generic")
