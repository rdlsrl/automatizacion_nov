"""OpenSearch template, analyzer, and alias contracts for Sprint 14."""

from __future__ import annotations

from dataclasses import dataclass, fields, is_dataclass
from enum import Enum
import json
from pathlib import Path


_DOCUMENTED_TEMPLATE_INDEX_NAMES = frozenset(
    {
        "ikc-variables-v1",
        "ikc-documents-v1",
        "ikc-fragments-v1",
        "ikc-assertions-v1",
        "ikc-facts-v1",
    }
)

_REQUIRED_INDEX_ALIASES = frozenset(
    {
        ("ikc-variables-v1", "ikc-variables-current"),
        ("ikc-documents-v1", "ikc-documents-current"),
        ("ikc-fragments-v1", "ikc-fragments-current"),
        ("ikc-assertions-v1", "ikc-assertions-current"),
        ("ikc-facts-v1", "ikc-facts-current"),
    }
)

_OFFICIAL_REQUIRED_INDEX_NAMES = frozenset(
    {
        "ikc-variables-v1",
        "ikc-assets-v1",
        "ikc-processes-v1",
        "ikc-documents-v1",
        "ikc-fragments-v1",
        "ikc-assertions-v1",
        "ikc-facts-v1",
        "ikc-aliases-v1",
        "ikc-search-suggestions-v1",
    }
)


def _serialize_value(value: object) -> object:
    if isinstance(value, Enum):
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


@dataclass(frozen=True, slots=True)
class OpenSearchIndexAlias:
    index_name: str
    alias_name: str

    def __post_init__(self) -> None:
        index_name = self.index_name.strip()
        alias_name = self.alias_name.strip()
        if not index_name.endswith("-v1"):
            raise ValueError("OpenSearchIndexAlias.index_name must be versioned")
        if not alias_name.endswith("-current"):
            raise ValueError("OpenSearchIndexAlias.alias_name must be a current alias")
        object.__setattr__(self, "index_name", index_name)
        object.__setattr__(self, "alias_name", alias_name)

    def as_serializable(self) -> dict[str, object]:
        return _serialize_value(self)


@dataclass(frozen=True, slots=True)
class OpenSearchIndexTemplate:
    index_name: str
    alias_name: str
    body: dict[str, object]

    def __post_init__(self) -> None:
        index_name = self.index_name.strip()
        alias_name = self.alias_name.strip()
        if index_name not in _DOCUMENTED_TEMPLATE_INDEX_NAMES:
            raise ValueError("OpenSearchIndexTemplate.index_name must be one of the documented Sprint 14 template indices")
        if (index_name, alias_name) not in _REQUIRED_INDEX_ALIASES:
            raise ValueError("OpenSearchIndexTemplate.alias_name must match the documented current alias for the index")
        if "mappings" not in self.body or "properties" not in self.body["mappings"]:
            raise ValueError("OpenSearchIndexTemplate.body must contain mappings.properties")
        if "settings" not in self.body:
            raise ValueError("OpenSearchIndexTemplate.body must contain settings")
        object.__setattr__(self, "index_name", index_name)
        object.__setattr__(self, "alias_name", alias_name)
        object.__setattr__(self, "body", json.loads(json.dumps(self.body, sort_keys=True)))

    def field_names(self) -> tuple[str, ...]:
        properties = self.body["mappings"]["properties"]
        return tuple(sorted(str(field_name) for field_name in properties))

    def as_serializable(self) -> dict[str, object]:
        return _serialize_value(self)


@dataclass(frozen=True, slots=True)
class OpenSearchTemplateBundle:
    analysis_settings: dict[str, object]
    required_indices: tuple[str, ...]
    aliases: tuple[OpenSearchIndexAlias, ...]
    templates: tuple[OpenSearchIndexTemplate, ...]

    def __post_init__(self) -> None:
        required_indices = tuple(sorted(index_name.strip() for index_name in self.required_indices))
        if set(required_indices) != _OFFICIAL_REQUIRED_INDEX_NAMES:
            raise ValueError("OpenSearchTemplateBundle.required_indices must match the official OpenSearch index list")
        aliases = tuple(sorted(tuple(self.aliases), key=lambda alias: alias.index_name))
        templates = tuple(sorted(tuple(self.templates), key=lambda template: template.index_name))
        if {template.index_name for template in templates} != _DOCUMENTED_TEMPLATE_INDEX_NAMES:
            raise ValueError("OpenSearchTemplateBundle.templates must cover the documented Sprint 14 template indices")
        if {(alias.index_name, alias.alias_name) for alias in aliases} != _REQUIRED_INDEX_ALIASES:
            raise ValueError("OpenSearchTemplateBundle.aliases must match the documented current aliases")
        analyzers = self.analysis_settings.get("analyzer", {})
        filters = self.analysis_settings.get("filter", {})
        required_analyzers = {"ikc_text_es_en", "ikc_keyword_folded", "ikc_edge_autocomplete", "ikc_mnemonic_analyzer", "ikc_tag_analyzer"}
        required_filters = {"ikc_synonyms", "ikc_edge"}
        if not required_analyzers.issubset(set(analyzers)):
            raise ValueError("OpenSearchTemplateBundle.analysis_settings must include the documented analyzers")
        if not required_filters.issubset(set(filters)):
            raise ValueError("OpenSearchTemplateBundle.analysis_settings must include the documented token filters")
        object.__setattr__(self, "required_indices", required_indices)
        object.__setattr__(self, "aliases", aliases)
        object.__setattr__(self, "templates", templates)
        object.__setattr__(self, "analysis_settings", json.loads(json.dumps(self.analysis_settings, sort_keys=True)))

    def as_serializable(self) -> dict[str, object]:
        return _serialize_value(self)


class OpenSearchTemplateBundleLoader:
    @classmethod
    def load(cls, root_path: str | Path) -> OpenSearchTemplateBundle:
        root = Path(root_path)
        analysis_settings = json.loads((root / "analyzers" / "shared_analysis.json").read_text())
        manifest = json.loads((root / "templates" / "index_manifest.json").read_text())
        templates = tuple(
            OpenSearchIndexTemplate(
                index_name=index_name,
                alias_name=manifest["current_aliases"][index_name],
                body=json.loads((root / "templates" / f"{index_name}.json").read_text()),
            )
            for index_name in _DOCUMENTED_TEMPLATE_INDEX_NAMES
        )
        aliases = tuple(
            OpenSearchIndexAlias(index_name=index_name, alias_name=alias_name)
            for index_name, alias_name in manifest["current_aliases"].items()
        )
        return OpenSearchTemplateBundle(
            analysis_settings=analysis_settings,
            required_indices=tuple(manifest["required_indices"]),
            aliases=aliases,
            templates=templates,
        )