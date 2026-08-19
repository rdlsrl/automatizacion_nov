"""Validation primitives shared by all domain modules."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum

from drilling_knowledge.common.exceptions import ValidationError


class ValidationSeverity(StrEnum):
    ERROR = "error"
    WARNING = "warning"


@dataclass(frozen=True, slots=True)
class ValidationIssue:
    code: str
    message: str
    path: str | None = None
    severity: ValidationSeverity = ValidationSeverity.ERROR


@dataclass(slots=True)
class ValidationReport:
    issues: list[ValidationIssue] = field(default_factory=list)

    def add_issue(self, issue: ValidationIssue) -> None:
        self.issues.append(issue)

    def add_error(self, code: str, message: str, path: str | None = None) -> None:
        self.add_issue(ValidationIssue(code=code, message=message, path=path))

    def add_warning(self, code: str, message: str, path: str | None = None) -> None:
        self.add_issue(
            ValidationIssue(
                code=code,
                message=message,
                path=path,
                severity=ValidationSeverity.WARNING,
            )
        )

    @property
    def is_valid(self) -> bool:
        return not any(issue.severity == ValidationSeverity.ERROR for issue in self.issues)

    @property
    def errors(self) -> list[ValidationIssue]:
        return [issue for issue in self.issues if issue.severity == ValidationSeverity.ERROR]

    @property
    def warnings(self) -> list[ValidationIssue]:
        return [issue for issue in self.issues if issue.severity == ValidationSeverity.WARNING]

    def require_valid(self, code: str = "validation_failed") -> None:
        if self.is_valid:
            return
        raise ValidationError(
            code=code,
            message="Validation report contains one or more errors",
            context={
                "errors": [issue.message for issue in self.errors],
                "warnings": [issue.message for issue in self.warnings],
            },
        )


def ensure(condition: bool, code: str, message: str, path: str | None = None) -> ValidationReport:
    report = ValidationReport()
    if not condition:
        report.add_error(code=code, message=message, path=path)
    return report
