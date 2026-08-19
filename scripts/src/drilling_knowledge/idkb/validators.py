"""Validation for the initial IDKB backbone."""

from __future__ import annotations

from dataclasses import dataclass

from drilling_knowledge.idkb.repositories import IdkbRepository
from drilling_knowledge.common.validation import ValidationReport


@dataclass(frozen=True, slots=True)
class IdkbBackboneValidator:
    repository: IdkbRepository

    def validate(self) -> ValidationReport:
        report = ValidationReport()
        domain_codes = {domain.code for domain in self.repository.domains.list_all()}
        template_codes = {template.code for template in self.repository.article_templates.list_all()}
        maturity_codes = {level.code for level in self.repository.maturity_levels.list_all()}

        for domain in self.repository.domains.list_all():
            report.issues.extend(domain.validate().issues)
            if domain.parent_code and domain.parent_code not in domain_codes:
                report.add_error(
                    "unknown_domain_parent",
                    f"Knowledge domain '{domain.code}' references unknown parent domain '{domain.parent_code}'",
                )

        self._validate_cycles(
            report=report,
            label="knowledge_domain",
            edges={domain.code: domain.parent_code for domain in self.repository.domains.list_all() if domain.parent_code},
        )

        for template in self.repository.article_templates.list_all():
            report.issues.extend(template.validate().issues)

        for level in self.repository.maturity_levels.list_all():
            report.issues.extend(level.validate().issues)

        for identifier in self.repository.identifier_definitions.list_all():
            report.issues.extend(identifier.validate().issues)

        for pack in self.repository.knowledge_packs.list_all():
            report.issues.extend(pack.validate().issues)
            for domain_code in pack.domain_codes:
                if domain_code not in domain_codes:
                    report.add_error(
                        "unknown_knowledge_pack_domain",
                        f"Knowledge pack '{pack.code}' references unknown domain '{domain_code}'",
                    )
            if pack.article_template_code not in template_codes:
                report.add_error(
                    "unknown_knowledge_pack_template",
                    f"Knowledge pack '{pack.code}' references unknown article template '{pack.article_template_code}'",
                )
            if pack.maturity_level_code not in maturity_codes:
                report.add_error(
                    "unknown_knowledge_pack_maturity",
                    f"Knowledge pack '{pack.code}' references unknown maturity level '{pack.maturity_level_code}'",
                )
        return report

    def _validate_cycles(self, *, report: ValidationReport, label: str, edges: dict[object, object]) -> None:
        visited: set[object] = set()
        active: set[object] = set()

        def visit(node: object) -> None:
            if node in active:
                report.add_error("hierarchy_cycle_detected", f"Cycle detected in {label} hierarchy at '{node}'")
                return
            if node in visited:
                return
            visited.add(node)
            active.add(node)
            parent = edges.get(node)
            if parent is not None:
                visit(parent)
            active.remove(node)

        for node in edges:
            visit(node)