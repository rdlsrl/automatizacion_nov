"""Append-only in-memory repository for governed synonym entries."""

from __future__ import annotations

from dataclasses import dataclass, field

from drilling_knowledge.common.exceptions import ConflictError
from drilling_knowledge.common.ids import EntityId
from drilling_knowledge.projections.search.synonyms import SearchSynonymCatalog, SearchSynonymEntry, SynonymStatus


@dataclass(frozen=True, slots=True)
class InMemorySearchSynonymRepository:
    entries: tuple[SearchSynonymEntry, ...] = ()
    _entries_by_id: dict[EntityId, tuple[SearchSynonymEntry, ...]] = field(init=False, default_factory=dict)

    def __post_init__(self) -> None:
        SearchSynonymCatalog(self.entries)
        grouped: dict[EntityId, list[SearchSynonymEntry]] = {}
        for entry in self.entries:
            revisions = grouped.setdefault(entry.synonym_id, [])
            if any(existing.revision == entry.revision and existing != entry for existing in revisions):
                raise ConflictError(
                    code="duplicate_search_synonym_revision",
                    message="A different synonym entry already exists for the same synonym id and revision",
                    context={"synonym_id": str(entry.synonym_id), "revision": entry.revision},
                )
            revisions.append(entry)
        object.__setattr__(self, "_entries_by_id", {key: tuple(sorted(value, key=lambda item: item.revision)) for key, value in grouped.items()})

    def list_entries(self) -> tuple[SearchSynonymEntry, ...]:
        return tuple(sorted(self.entries, key=lambda entry: (entry.set_name, str(entry.synonym_id), entry.revision)))

    def get_history(self, synonym_id: EntityId) -> tuple[SearchSynonymEntry, ...]:
        return self._entries_by_id.get(synonym_id, ())

    def append_entry(self, entry: SearchSynonymEntry) -> "InMemorySearchSynonymRepository":
        history = self._entries_by_id.get(entry.synonym_id, ())
        if any(existing.revision == entry.revision for existing in history):
            existing = next(existing for existing in history if existing.revision == entry.revision)
            if existing != entry:
                raise ConflictError(
                    code="duplicate_search_synonym_revision",
                    message="A different synonym entry already exists for the same synonym id and revision",
                    context={"synonym_id": str(entry.synonym_id), "revision": entry.revision},
                )
            return self
        if history and entry.revision != history[-1].revision + 1:
            raise ValueError("SearchSynonymEntry revisions must be appended sequentially")
        if entry.status == SynonymStatus.ACTIVE and any(existing.status == SynonymStatus.ACTIVE for existing in history):
            raise ValueError("SearchSynonymRepository cannot append a second active revision for the same synonym id")
        return InMemorySearchSynonymRepository(self.entries + (entry,))