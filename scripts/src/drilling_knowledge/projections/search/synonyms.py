"""Deterministic synonym governance contracts for Sprint 14."""

from __future__ import annotations

from dataclasses import dataclass, fields, is_dataclass
from enum import StrEnum
import json
from pathlib import Path

from drilling_knowledge.common.ids import EntityId, Identifier


_OFFICIAL_SYNONYM_SET_NAMES = frozenset(
    {
        "variable_category_synonyms",
        "rig_subsystem_synonyms",
        "measurement_principle_synonyms",
        "unit_lexical_variants",
        "english_spanish_term_variants",
        "vendor_product_family_aliases",
    }
)


def _serialize_value(value: object) -> object:
    if isinstance(value, Identifier):
        return str(value)
    if isinstance(value, StrEnum):
        return value.value
    if is_dataclass(value):
        return {field.name: _serialize_value(getattr(value, field.name)) for field in fields(value)}
    if isinstance(value, tuple):
        return [_serialize_value(item) for item in value]
    if isinstance(value, list):
        return [_serialize_value(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _serialize_value(item) for key, item in sorted(value.items(), key=lambda item: str(item[0]))}
    return value


class SynonymStatus(StrEnum):
    ACTIVE = "active"
    INACTIVE = "inactive"


@dataclass(frozen=True, slots=True)
class SearchSynonymEntry:
    synonym_id: EntityId
    set_name: str
    revision: int
    status: SynonymStatus
    terms: tuple[str, ...]
    provenance: tuple[str, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.synonym_id, EntityId):
            raise ValueError("SearchSynonymEntry.synonym_id must be an EntityId")
        set_name = self.set_name.strip().lower()
        if set_name not in _OFFICIAL_SYNONYM_SET_NAMES:
            raise ValueError("SearchSynonymEntry.set_name must be one of the official synonym sets")
        if self.revision < 1:
            raise ValueError("SearchSynonymEntry.revision must be >= 1")
        normalized_terms = tuple(sorted({term.strip().lower() for term in self.terms if term.strip()}))
        if len(normalized_terms) < 2:
            raise ValueError("SearchSynonymEntry.terms must contain at least two unique normalized terms")
        normalized_provenance = tuple(sorted({item.strip() for item in self.provenance if item.strip()}))
        if not normalized_provenance:
            raise ValueError("SearchSynonymEntry.provenance cannot be empty")
        object.__setattr__(self, "set_name", set_name)
        object.__setattr__(self, "terms", normalized_terms)
        object.__setattr__(self, "provenance", normalized_provenance)

    def as_serializable(self) -> dict[str, object]:
        return _serialize_value(self)


@dataclass(frozen=True, slots=True)
class SearchSynonymCatalog:
    entries: tuple[SearchSynonymEntry, ...]

    def __post_init__(self) -> None:
        entries = tuple(sorted(tuple(self.entries), key=lambda entry: (entry.set_name, str(entry.synonym_id), entry.revision)))
        seen_revision_keys: set[tuple[EntityId, int]] = set()
        active_by_id: dict[EntityId, int] = {}
        active_terms: set[tuple[str, tuple[str, ...]]] = set()
        for entry in entries:
            revision_key = (entry.synonym_id, entry.revision)
            if revision_key in seen_revision_keys:
                raise ValueError("SearchSynonymCatalog.entries cannot contain duplicate synonym revisions")
            seen_revision_keys.add(revision_key)
            if entry.status == SynonymStatus.ACTIVE:
                if entry.synonym_id in active_by_id:
                    raise ValueError("SearchSynonymCatalog cannot contain multiple active revisions for the same synonym id")
                active_by_id[entry.synonym_id] = entry.revision
                active_term_key = (entry.set_name, entry.terms)
                if active_term_key in active_terms:
                    raise ValueError("SearchSynonymCatalog cannot contain duplicate active synonym term sets")
                active_terms.add(active_term_key)
        object.__setattr__(self, "entries", entries)

    def as_serializable(self) -> dict[str, object]:
        return _serialize_value(self)


class SearchSynonymCatalogLoader:
    @classmethod
    def load(cls, root_path: str | Path) -> SearchSynonymCatalog:
        root = Path(root_path)
        entries: list[SearchSynonymEntry] = []
        for file_path in sorted(root.glob("*.json")):
            file_payload = json.loads(file_path.read_text())
            set_name = file_payload["set_name"]
            for item in file_payload["entries"]:
                entries.append(
                    SearchSynonymEntry(
                        synonym_id=EntityId.from_seed("search.synonym", item["stable_key"]),
                        set_name=set_name,
                        revision=item["revision"],
                        status=SynonymStatus(item["status"]),
                        terms=tuple(item["terms"]),
                        provenance=tuple(item["provenance"]),
                    )
                )
        return SearchSynonymCatalog(entries=tuple(entries))