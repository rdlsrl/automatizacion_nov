from __future__ import annotations

import unittest

from drilling_knowledge.catalog.domain import (
    CatalogCode,
    CatalogScope,
    EngineeringUnit,
    LocalizedName,
    PhysicalQuantity,
    SubsystemClass,
    SystemClass,
    Variable,
    VariableAlias,
    VariableClassification,
    OriginClass,
)
from drilling_knowledge.catalog.repositories import InMemoryCatalogRepository
from drilling_knowledge.catalog.repositories.memory import InMemoryEntityRepository
from drilling_knowledge.catalog.services import CatalogReader
from drilling_knowledge.common.exceptions import ConflictError, NotFoundError
from drilling_knowledge.common.ids import EntityId


class CatalogReaderTests(unittest.TestCase):
    def setUp(self) -> None:
        self.repository = InMemoryCatalogRepository(
            units=InMemoryEntityRepository(
                (
                    EngineeringUnit(
                        entity_id=EntityId.new(),
                        code=CatalogCode("psi"),
                        names=LocalizedName(canonical="PSI"),
                        description="Pressure unit pounds per square inch.",
                        symbol="psi",
                        dimension_code="pressure",
                    )
                )
            ),
            quantities=InMemoryEntityRepository(
                (
                    PhysicalQuantity(
                        entity_id=EntityId.new(),
                        code=CatalogCode("pressure"),
                        names=LocalizedName(canonical="Pressure", spanish="Presion"),
                        description="Hydraulic or gas pressure quantity.",
                        quantity_family="hydraulic",
                        dimension_code="pressure",
                        canonical_unit_code=CatalogCode("psi"),
                    )
                )
            ),
            principles=InMemoryEntityRepository(()),
            classifications=InMemoryEntityRepository(
                (
                    VariableClassification(
                        entity_id=EntityId.new(),
                        code=CatalogCode("primary"),
                        names=LocalizedName(canonical="Primary"),
                        description="Primary observational variable.",
                        axis="operational_role",
                    )
                )
            ),
            origins=InMemoryEntityRepository(
                (
                    OriginClass(
                        entity_id=EntityId.new(),
                        code=CatalogCode("direct_sensor"),
                        names=LocalizedName(canonical="Direct Sensor"),
                        description="Directly observed from a sensing element.",
                        axis="source_kind",
                    )
                )
            ),
            systems=InMemoryEntityRepository(
                (
                    SystemClass(
                        entity_id=EntityId.new(),
                        code=CatalogCode("circulation"),
                        names=LocalizedName(canonical="Circulation"),
                        description="Rig circulation system.",
                    )
                )
            ),
            subsystems=InMemoryEntityRepository(
                (
                    SubsystemClass(
                        entity_id=EntityId.new(),
                        code=CatalogCode("standpipe_system"),
                        names=LocalizedName(canonical="Standpipe System"),
                        description="High-pressure standpipe delivery subsystem.",
                        system_code=CatalogCode("circulation"),
                    )
                )
            ),
            variables=InMemoryEntityRepository(
                (
                    Variable(
                        entity_id=EntityId.new(),
                        code=CatalogCode("standpipe_pressure"),
                        names=LocalizedName(canonical="Standpipe Pressure", spanish="Presion de standpipe"),
                        description="Surface pressure measured at the standpipe manifold.",
                        physical_quantity_code=CatalogCode("pressure"),
                        canonical_unit_code=CatalogCode("psi"),
                        classification_codes=(CatalogCode("primary"),),
                        origin_codes=(CatalogCode("direct_sensor"),),
                        subsystem_codes=(CatalogCode("standpipe_system"),),
                        aliases=(VariableAlias(alias="SPP"),),
                        ambiguity_level="low",
                    )
                )
            ),
        )
        self.reader = CatalogReader(self.repository)

    def test_get_variable_returns_known_variable(self) -> None:
        variable = self.reader.get_variable("standpipe_pressure")

        self.assertEqual(variable.canonical_name, "Standpipe Pressure")

    def test_resolve_variable_alias_returns_matching_variable(self) -> None:
        variable = self.reader.resolve_variable_alias("spp")

        self.assertIsNotNone(variable)
        assert variable is not None
        self.assertEqual(str(variable.code), "standpipe_pressure")

    def test_list_variables_by_subsystem_filters_correctly(self) -> None:
        variables = self.reader.list_variables_by_subsystem("standpipe_system")

        self.assertEqual(len(variables), 1)
        self.assertEqual(str(variables[0].code), "standpipe_pressure")

    def test_get_variable_raises_for_unknown_code(self) -> None:
        with self.assertRaises(NotFoundError):
            self.reader.get_variable("unknown_variable")

    def test_get_variable_raises_for_ambiguous_code(self) -> None:
        repository = InMemoryCatalogRepository(
            units=self.repository.units,
            quantities=self.repository.quantities,
            principles=self.repository.principles,
            classifications=self.repository.classifications,
            origins=self.repository.origins,
            systems=self.repository.systems,
            subsystems=self.repository.subsystems,
            variables=InMemoryEntityRepository(
                (
                    self.repository.variables.list_all()[0],
                    Variable(
                        entity_id=EntityId.new(),
                        code=CatalogCode("standpipe_pressure"),
                        names=LocalizedName(canonical="Standpipe Pressure"),
                        description="Same canonical variable published by a different vendor.",
                        scope=CatalogScope(domain="surface", vendor="vendor_b"),
                        physical_quantity_code=CatalogCode("pressure"),
                        canonical_unit_code=CatalogCode("psi"),
                    ),
                )
            ),
        )

        with self.assertRaises(ConflictError):
            CatalogReader(repository).get_variable("standpipe_pressure")
