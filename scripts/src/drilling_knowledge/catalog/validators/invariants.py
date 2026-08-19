"""Invariant validators for the catalog core."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass

from drilling_knowledge.catalog.domain import KnowledgeEntity, Variable, VariableAlias
from drilling_knowledge.catalog.repositories.contracts import CatalogRepository
from drilling_knowledge.common.validation import ValidationReport


@dataclass(frozen=True, slots=True)
class CatalogInvariantValidator:
    """Checks core IKC invariants on a read-only catalog snapshot."""

    repository: CatalogRepository

    def validate(self) -> ValidationReport:
        report = ValidationReport()
        unit_codes = {unit.code for unit in self.repository.units.list_all()}
        unit_dimensions = {unit.code: unit.dimension_code for unit in self.repository.units.list_all()}
        quantity_codes = {quantity.code for quantity in self.repository.quantities.list_all()}
        systems = {system.code for system in self.repository.systems.list_all()}
        quantities = {quantity.code: quantity for quantity in self.repository.quantities.list_all()}
        classification_codes = {classification.code for classification in self.repository.classifications.list_all()}
        origin_codes = {origin.code for origin in self.repository.origins.list_all()}
        subsystem_codes = {subsystem.code for subsystem in self.repository.subsystems.list_all()}
        alias_registry: dict[tuple[str, str], list[tuple[Variable, VariableAlias]]] = defaultdict(list)

        for unit in self.repository.units.list_all():
            report.issues.extend(unit.validate().issues)

        for quantity in self.repository.quantities.list_all():
            report.issues.extend(quantity.validate().issues)
            if quantity.canonical_unit_code and quantity.canonical_unit_code not in unit_codes:
                report.add_error(
                    "missing_quantity_canonical_unit",
                    f"Quantity '{quantity.code}' references unknown canonical unit '{quantity.canonical_unit_code}'",
                )
            if quantity.canonical_unit_code and quantity.canonical_unit_code in unit_dimensions:
                if unit_dimensions[quantity.canonical_unit_code] != quantity.dimension_code:
                    report.add_error(
                        "quantity_unit_dimension_mismatch",
                        (
                            f"Quantity '{quantity.code}' dimension '{quantity.dimension_code}' does not match "
                            f"unit '{quantity.canonical_unit_code}' dimension '{unit_dimensions[quantity.canonical_unit_code]}'"
                        ),
                    )

        for classification in self.repository.classifications.list_all():
            report.issues.extend(classification.validate().issues)

        for origin in self.repository.origins.list_all():
            report.issues.extend(origin.validate().issues)

        for principle in self.repository.principles.list_all():
            report.issues.extend(principle.validate().issues)

        for compatibility in self.repository.quantity_unit_compatibilities.list_all():
            report.issues.extend(compatibility.validate().issues)
            if compatibility.quantity_code not in quantity_codes:
                report.add_error(
                    "unknown_compatibility_quantity",
                    f"Compatibility '{compatibility.code}' references unknown quantity '{compatibility.quantity_code}'",
                )
            if compatibility.unit_code not in unit_codes:
                report.add_error(
                    "unknown_compatibility_unit",
                    f"Compatibility '{compatibility.code}' references unknown unit '{compatibility.unit_code}'",
                )
            if compatibility.quantity_code in quantities and compatibility.unit_code in unit_dimensions:
                quantity = quantities[compatibility.quantity_code]
                if unit_dimensions[compatibility.unit_code] != quantity.dimension_code:
                    report.add_error(
                        "incompatible_quantity_unit_dimension",
                        (
                            f"Compatibility '{compatibility.code}' links quantity '{quantity.code}' dimension "
                            f"'{quantity.dimension_code}' with unit '{compatibility.unit_code}' dimension "
                            f"'{unit_dimensions[compatibility.unit_code]}'"
                        ),
                    )

        for subsystem in self.repository.subsystems.list_all():
            report.issues.extend(subsystem.validate().issues)
            if subsystem.system_code not in systems:
                report.add_error(
                    "unknown_subsystem_system",
                    f"Subsystem '{subsystem.code}' references unknown system '{subsystem.system_code}'",
                )

        self._validate_hierarchy(
            report=report,
            label="system",
            entities=self.repository.systems.list_all(),
            parent_lookup=lambda entity: entity.parent_code,
        )
        self._validate_hierarchy(
            report=report,
            label="subsystem",
            entities=self.repository.subsystems.list_all(),
            parent_lookup=lambda entity: entity.parent_subsystem_code,
        )
        self._validate_hierarchy(
            report=report,
            label="variable_classification",
            entities=self.repository.classifications.list_all(),
            parent_lookup=lambda entity: entity.parent_code,
        )
        self._validate_hierarchy(
            report=report,
            label="origin_class",
            entities=self.repository.origins.list_all(),
            parent_lookup=lambda entity: entity.parent_code,
        )
        self._validate_hierarchy(
            report=report,
            label="publisher_class",
            entities=self.repository.publishers.list_all(),
            parent_lookup=lambda entity: entity.parent_code,
        )
        self._validate_hierarchy(
            report=report,
            label="process_class",
            entities=self.repository.processes.list_all(),
            parent_lookup=lambda entity: entity.parent_code,
        )
        self._validate_hierarchy(
            report=report,
            label="operational_context_class",
            entities=self.repository.operational_contexts.list_all(),
            parent_lookup=lambda entity: entity.parent_code,
        )
        self._validate_hierarchy(
            report=report,
            label="location_class",
            entities=self.repository.locations.list_all(),
            parent_lookup=lambda entity: entity.parent_code,
        )
        self._validate_hierarchy(
            report=report,
            label="sensor_class",
            entities=self.repository.sensors.list_all(),
            parent_lookup=lambda entity: entity.parent_code,
        )
        self._validate_hierarchy(
            report=report,
            label="instrument_class",
            entities=self.repository.instruments.list_all(),
            parent_lookup=lambda entity: entity.parent_code,
        )
        self._validate_hierarchy(
            report=report,
            label="equipment_class",
            entities=self.repository.equipment.list_all(),
            parent_lookup=lambda entity: entity.parent_code,
        )

        for variable in self.repository.variables.list_all():
            report.issues.extend(variable.validate().issues)
            if variable.physical_quantity_code and variable.physical_quantity_code not in quantity_codes:
                report.add_error(
                    "unknown_variable_quantity",
                    f"Variable '{variable.code}' references unknown quantity '{variable.physical_quantity_code}'",
                )
            if variable.canonical_unit_code and variable.canonical_unit_code not in unit_codes:
                report.add_error(
                    "unknown_variable_unit",
                    f"Variable '{variable.code}' references unknown unit '{variable.canonical_unit_code}'",
                )
            if variable.physical_quantity_code and variable.canonical_unit_code:
                matching_quantities = quantities.get(variable.physical_quantity_code)
                if matching_quantities and matching_quantities.canonical_unit_code and matching_quantities.canonical_unit_code != variable.canonical_unit_code:
                    report.add_error(
                        "canonical_unit_mismatch",
                        (
                            f"Variable '{variable.code}' canonical unit '{variable.canonical_unit_code}' "
                            f"does not match quantity '{matching_quantities.code}' canonical unit '{matching_quantities.canonical_unit_code}'"
                        ),
                    )
                if (
                    matching_quantities
                    and variable.canonical_unit_code in unit_dimensions
                    and unit_dimensions[variable.canonical_unit_code] != matching_quantities.dimension_code
                ):
                    report.add_error(
                        "variable_unit_dimension_mismatch",
                        (
                            f"Variable '{variable.code}' canonical unit '{variable.canonical_unit_code}' dimension "
                            f"'{unit_dimensions[variable.canonical_unit_code]}' does not match quantity "
                            f"'{matching_quantities.code}' dimension '{matching_quantities.dimension_code}'"
                        ),
                    )
            for classification_code in variable.classification_codes:
                if classification_code not in classification_codes:
                    report.add_error(
                        "unknown_variable_classification",
                        f"Variable '{variable.code}' references unknown classification '{classification_code}'",
                    )
            for origin_code in variable.origin_codes:
                if origin_code not in origin_codes:
                    report.add_error(
                        "unknown_variable_origin",
                        f"Variable '{variable.code}' references unknown origin '{origin_code}'",
                    )
            for subsystem_code in variable.subsystem_codes:
                if subsystem_code not in subsystem_codes:
                    report.add_error(
                        "unknown_variable_subsystem",
                        f"Variable '{variable.code}' references unknown subsystem '{subsystem_code}'",
                    )
            for alias in variable.aliases:
                effective_scope = variable.scope.merged_with(alias.scope)
                alias_registry[(alias.normalized_alias, effective_scope.label())].append((variable, alias))

        for (alias_value, scope_label), bindings in alias_registry.items():
            if len(bindings) <= 1:
                continue
            codes = {binding[0].canonical_identity for binding in bindings}
            if len(codes) == 1:
                report.add_error(
                    "duplicate_alias_binding",
                    f"Alias '{alias_value}' is duplicated within scope '{scope_label}' for the same canonical variable",
                )
                continue
            report.add_error(
                "ambiguous_alias_collision",
                (
                    f"Alias '{alias_value}' is ambiguous within scope '{scope_label}' across "
                    f"{len(codes)} canonical variables"
                ),
            )
        return report

    def _validate_hierarchy(
        self,
        *,
        report: ValidationReport,
        label: str,
        entities: tuple[KnowledgeEntity, ...],
        parent_lookup,
    ) -> None:
        codes = {entity.code for entity in entities}
        edges: dict[object, object] = {}
        for entity in entities:
            parent_code = parent_lookup(entity)
            if parent_code is None:
                continue
            if parent_code not in codes:
                report.add_error(
                    f"unknown_{label}_parent",
                    f"{label.replace('_', ' ').title()} '{entity.code}' references unknown parent '{parent_code}'",
                )
                continue
            edges[entity.code] = parent_code

        visited: set[object] = set()
        active: set[object] = set()

        def visit(code: object) -> None:
            if code in active:
                report.add_error("hierarchy_cycle_detected", f"Cycle detected in {label} hierarchy at '{code}'")
                return
            if code in visited:
                return
            visited.add(code)
            active.add(code)
            parent = edges.get(code)
            if parent is not None:
                visit(parent)
            active.remove(code)

        for code in edges:
            visit(code)
