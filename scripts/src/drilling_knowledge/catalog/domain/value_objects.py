"""Value objects for the catalog core domain."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import re

from drilling_knowledge.common.validation import ValidationReport


_CODE_PATTERN = re.compile(r"^[a-z0-9_\-\.]+$")


@dataclass(frozen=True, slots=True)
class CatalogCode:
    """Normalized code used as a stable identifier across catalog entities."""

    value: str

    def __post_init__(self) -> None:
        normalized = self.value.strip().lower()
        if not normalized:
            raise ValueError("CatalogCode cannot be empty")
        if not _CODE_PATTERN.match(normalized):
            raise ValueError(
                "CatalogCode must contain only lowercase letters, digits, underscores, hyphens, or dots"
            )
        object.__setattr__(self, "value", normalized)

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True, slots=True)
class LocalizedName:
    """Canonical multilingual display names."""

    canonical: str
    spanish: str | None = None
    short: str | None = None

    def __post_init__(self) -> None:
        canonical = self.canonical.strip()
        if not canonical:
            raise ValueError("LocalizedName.canonical cannot be empty")
        object.__setattr__(self, "canonical", canonical)
        if self.spanish is not None:
            object.__setattr__(self, "spanish", self.spanish.strip() or None)
        if self.short is not None:
            object.__setattr__(self, "short", self.short.strip() or None)


@dataclass(frozen=True, slots=True)
class CatalogScope:
    """Applicability scope for catalog entries and relationships."""

    domain: str = "global"
    vendor: str | None = None
    model_family: str | None = None
    protocol: str | None = None
    publisher: str | None = None
    subsystem: str | None = None
    rig: str | None = None
    software_version: str | None = None
    firmware_version: str | None = None
    operational_context: str | None = None
    source_document: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "domain", self.domain.strip().lower() or "global")
        if self.vendor is not None:
            object.__setattr__(self, "vendor", self.vendor.strip().lower() or None)
        if self.model_family is not None:
            object.__setattr__(self, "model_family", self.model_family.strip().lower() or None)
        if self.protocol is not None:
            object.__setattr__(self, "protocol", self.protocol.strip().lower() or None)
        if self.publisher is not None:
            object.__setattr__(self, "publisher", self.publisher.strip().lower() or None)
        if self.subsystem is not None:
            object.__setattr__(self, "subsystem", self.subsystem.strip().lower() or None)
        if self.rig is not None:
            object.__setattr__(self, "rig", self.rig.strip().lower() or None)
        if self.software_version is not None:
            object.__setattr__(self, "software_version", self.software_version.strip().lower() or None)
        if self.firmware_version is not None:
            object.__setattr__(self, "firmware_version", self.firmware_version.strip().lower() or None)
        if self.operational_context is not None:
            object.__setattr__(self, "operational_context", self.operational_context.strip().lower() or None)
        if self.source_document is not None:
            object.__setattr__(self, "source_document", self.source_document.strip() or None)

    def merged_with(self, override: "CatalogScope | None") -> "CatalogScope":
        if override is None:
            return self
        return CatalogScope(
            domain=override.domain or self.domain,
            vendor=override.vendor or self.vendor,
            model_family=override.model_family or self.model_family,
            protocol=override.protocol or self.protocol,
            publisher=override.publisher or self.publisher,
            subsystem=override.subsystem or self.subsystem,
            rig=override.rig or self.rig,
            software_version=override.software_version or self.software_version,
            firmware_version=override.firmware_version or self.firmware_version,
            operational_context=override.operational_context or self.operational_context,
            source_document=override.source_document or self.source_document,
        )

    def label(self) -> str:
        parts = [self.domain]
        if self.vendor:
            parts.append(f"vendor={self.vendor}")
        if self.model_family:
            parts.append(f"model_family={self.model_family}")
        if self.protocol:
            parts.append(f"protocol={self.protocol}")
        if self.publisher:
            parts.append(f"publisher={self.publisher}")
        if self.subsystem:
            parts.append(f"subsystem={self.subsystem}")
        if self.rig:
            parts.append(f"rig={self.rig}")
        if self.software_version:
            parts.append(f"software_version={self.software_version}")
        if self.firmware_version:
            parts.append(f"firmware_version={self.firmware_version}")
        if self.operational_context:
            parts.append(f"operational_context={self.operational_context}")
        if self.source_document:
            parts.append(f"source_document={self.source_document}")
        return "|".join(parts)


@dataclass(frozen=True, slots=True)
class CanonicalIdentity:
    """Effective canonical identity subject to uniqueness in the catalog."""

    code: CatalogCode
    scope_label: str
    semantic_version: int
    record_status: str

    def __post_init__(self) -> None:
        scope_label = self.scope_label.strip()
        record_status = self.record_status.strip().lower()
        if not scope_label:
            raise ValueError("CanonicalIdentity.scope_label cannot be empty")
        if self.semantic_version <= 0:
            raise ValueError("CanonicalIdentity.semantic_version must be positive")
        if not record_status:
            raise ValueError("CanonicalIdentity.record_status cannot be empty")
        object.__setattr__(self, "scope_label", scope_label)
        object.__setattr__(self, "record_status", record_status)


@dataclass(frozen=True, slots=True)
class VersionInfo:
    """Semantic validity window for catalog entries."""

    semantic_version: int = 1
    valid_from: datetime | None = None
    valid_to: datetime | None = None
    status: str = "active"

    def __post_init__(self) -> None:
        if self.semantic_version <= 0:
            raise ValueError("semantic_version must be positive")
        if self.valid_from and self.valid_to and self.valid_to <= self.valid_from:
            raise ValueError("valid_to must be greater than valid_from")

    def validate(self) -> ValidationReport:
        report = ValidationReport()
        if self.semantic_version <= 0:
            report.add_error("invalid_semantic_version", "Semantic version must be positive")
        if self.valid_from and self.valid_to and self.valid_to <= self.valid_from:
            report.add_error("invalid_validity_window", "valid_to must be greater than valid_from")
        return report
