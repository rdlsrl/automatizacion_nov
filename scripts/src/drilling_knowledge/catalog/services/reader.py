"""Read services for the catalog core."""

from __future__ import annotations

from dataclasses import dataclass

from drilling_knowledge.catalog.domain import EngineeringUnit, PhysicalQuantity, Variable
from drilling_knowledge.catalog.domain.value_objects import CatalogCode
from drilling_knowledge.catalog.repositories.contracts import CatalogRepository
from drilling_knowledge.common.exceptions import ConflictError, NotFoundError


@dataclass(frozen=True, slots=True)
class CatalogReader:
    """Thin query service over the read-only catalog repository contract."""

    repository: CatalogRepository

    def get_variable(self, code: str) -> Variable:
        matches = self.repository.variables.get_by_code(CatalogCode(code))
        if not matches:
            raise NotFoundError(code="variable_not_found", message="Variable not found", context={"code": code})
        if len(matches) > 1:
            raise ConflictError(
                code="ambiguous_variable_code",
                message="Multiple canonical variables match the requested code; scope or version disambiguation is required",
                context={"code": code, "matches": [entity.scope.label() for entity in matches]},
            )
        return matches[0]

    def get_quantity(self, code: str) -> PhysicalQuantity:
        matches = self.repository.quantities.get_by_code(CatalogCode(code))
        if not matches:
            raise NotFoundError(code="quantity_not_found", message="Physical quantity not found", context={"code": code})
        if len(matches) > 1:
            raise ConflictError(
                code="ambiguous_quantity_code",
                message="Multiple canonical quantities match the requested code; scope or version disambiguation is required",
                context={"code": code, "matches": [entity.scope.label() for entity in matches]},
            )
        return matches[0]

    def get_unit(self, code: str) -> EngineeringUnit:
        matches = self.repository.units.get_by_code(CatalogCode(code))
        if not matches:
            raise NotFoundError(code="unit_not_found", message="Engineering unit not found", context={"code": code})
        if len(matches) > 1:
            raise ConflictError(
                code="ambiguous_unit_code",
                message="Multiple canonical units match the requested code; scope or version disambiguation is required",
                context={"code": code, "matches": [entity.scope.label() for entity in matches]},
            )
        return matches[0]

    def resolve_variable_alias(self, alias: str) -> Variable | None:
        normalized = alias.strip().lower()
        match: Variable | None = None
        for variable in self.repository.variables.list_all():
            for variable_alias in variable.aliases:
                if variable_alias.normalized_alias != normalized:
                    continue
                if match is None:
                    match = variable
                    continue
                raise ConflictError(
                    code="ambiguous_variable_alias",
                    message="Alias resolves to multiple canonical variables across different contexts",
                    context={"alias": alias, "matches": [match.scope.label(), variable.scope.label()]},
                )
        return match

    def list_variables_by_subsystem(self, subsystem_code: str) -> tuple[Variable, ...]:
        code = CatalogCode(subsystem_code)
        matched: list[Variable] = []
        for variable in self.repository.variables.list_all():
            if code in variable.subsystem_codes:
                matched.append(variable)
        return tuple(matched)
