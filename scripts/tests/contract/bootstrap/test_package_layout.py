from __future__ import annotations

from drilling_knowledge import __version__
from drilling_knowledge.common.ids import EntityId
from drilling_knowledge.config.settings import AppSettings


def test_package_can_be_imported() -> None:
    assert __version__ == "0.1.0"


def test_core_types_are_available_for_downstream_modules() -> None:
    entity_id = EntityId.new()
    settings = AppSettings()

    assert entity_id is not None
    assert settings.app_name == "drilling-knowledge-platform"
