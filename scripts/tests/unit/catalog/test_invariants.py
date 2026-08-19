from __future__ import annotations

import unittest

from drilling_knowledge.catalog.domain import (
    CatalogCode,
    CatalogScope,
    EngineeringUnit,
    LocalizedName,
    OriginClass,
    PhysicalQuantity,
    SubsystemClass,
    SystemClass,
    Variable,
    VariableAlias,
    VariableClassification,
)
from drilling_knowledge.catalog.repositories import InMemoryCatalogRepository
from drilling_knowledge.catalog.repositories.memory import InMemoryEntityRepository
from drilling_knowledge.catalog.validators import CatalogInvariantValidator
from drilling_knowledge.common.ids import EntityId


class CatalogInvariantValidatorTests(unittest.TestCase):
    def test_validator_accepts_consistent_catalog_snapshot(self) -> None:
        repository = build_repository(variable_unit_code="psi")

        report = CatalogInvariantValidator(repository).validate()

        self.assertTrue(report.is_valid)

    def test_validator_detects_unknown_variable_unit(self) -> None:
        repository = build_repository(variable_unit_code="bar")

        report = CatalogInvariantValidator(repository).validate()

        self.assertFalse(report.is_valid)
        self.assertTrue(any(issue.code == "unknown_variable_unit" for issue in report.errors))

    def test_validator_detects_quantity_canonical_unit_mismatch(self) -> None:
        repository = build_repository(variable_unit_code="kpa", include_kpa=True)

        report = CatalogInvariantValidator(repository).validate()

        self.assertFalse(report.is_valid)
        self.assertTrue(any(issue.code == "canonical_unit_mismatch" for issue in report.errors))

    def test_validator_detects_subsystem_without_known_system(self) -> None:
        repository = build_repository(variable_unit_code="psi", subsystem_system_code="unknown_system")

        report = CatalogInvariantValidator(repository).validate()

        self.assertTrue(any(issue.code == "unknown_subsystem_system" for issue in report.errors))

    def test_validator_detects_unit_quantity_dimension_mismatch(self) -> None:
        repository = build_repository(variable_unit_code="psi", quantity_dimension_code="torque")

        report = CatalogInvariantValidator(repository).validate()

        self.assertTrue(any(issue.code == "quantity_unit_dimension_mismatch" for issue in report.errors))

    def test_same_alias_in_distinct_contexts_can_coexist(self) -> None:
        repository = build_repository(
            variable_unit_code="psi",
            variables=(
                build_variable(
                    code="standpipe_pressure",
                    alias="SPP",
                    scope=CatalogScope(domain="surface", vendor="vendor_a"),
                ),
                build_variable(
                    code="standpipe_pressure_vendor_b",
                    alias="SPP",
                    scope=CatalogScope(domain="surface", vendor="vendor_b"),
                ),
            ),
        )

        report = CatalogInvariantValidator(repository).validate()

        self.assertFalse(any(issue.code == "ambiguous_alias_collision" for issue in report.errors))

    def test_same_alias_in_same_context_generates_conflict(self) -> None:
        repository = build_repository(
            variable_unit_code="psi",
            variables=(
                build_variable(code="standpipe_pressure", alias="SPP"),
                build_variable(code="pump_pressure", alias="SPP"),
            ),
        )

        report = CatalogInvariantValidator(repository).validate()

        self.assertTrue(any(issue.code == "ambiguous_alias_collision" for issue in report.errors))


def build_repository(
    *,
    variable_unit_code: str,
    include_kpa: bool = False,
    subsystem_system_code: str = "circulation",
    quantity_dimension_code: str = "pressure",
    variables: tuple[Variable, ...] | None = None,
) -> InMemoryCatalogRepository:
    units = [
        EngineeringUnit(
            entity_id=EntityId.new(),
            code=CatalogCode("psi"),
            names=LocalizedName(canonical="PSI"),
            description="Pressure unit pounds per square inch.",
            symbol="psi",
            dimension_code="pressure",
        )
    ]
    if include_kpa:
        units.append(EngineeringUnit(
            entity_id=EntityId.new(),
            code=CatalogCode("kpa"),
            names=LocalizedName(canonical="kPa"),
            description="Pressure unit kilopascal.",
            symbol="kPa",
            dimension_code="pressure",
        ))

    repository_variables = variables or (build_variable(code="standpipe_pressure", alias=None, unit_code=variable_unit_code),)

    return InMemoryCatalogRepository(
        units=InMemoryEntityRepository(tuple(units)),
        quantities=InMemoryEntityRepository(
            (
                PhysicalQuantity(
                    entity_id=EntityId.new(),
                    code=CatalogCode("pressure"),
                    names=LocalizedName(canonical="Pressure"),
                    description="Hydraulic or gas pressure quantity.",
                    quantity_family="hydraulic",
                    dimension_code=quantity_dimension_code,
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
                    description="Direct sensor origin.",
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
                    description="Standpipe subsystem.",
                    system_code=CatalogCode(subsystem_system_code),
                )
            )
        ),
        variables=InMemoryEntityRepository(repository_variables),
    )


def build_variable(
    *,
    code: str,
    alias: str | None,
    scope: CatalogScope | None = None,
    unit_code: str = "psi",
) -> Variable:
    aliases = () if alias is None else (VariableAlias(alias=alias),)
    return Variable(
        entity_id=EntityId.new(),
        code=CatalogCode(code),
        names=LocalizedName(canonical=code.replace("_", " ").title()),
        description=f"Observed variable {code}.",
        scope=scope or CatalogScope(),
        physical_quantity_code=CatalogCode("pressure"),
        canonical_unit_code=CatalogCode(unit_code),
        classification_codes=(CatalogCode("primary"),),
        origin_codes=(CatalogCode("direct_sensor"),),
        subsystem_codes=(CatalogCode("standpipe_system"),),
        aliases=aliases,
    )
