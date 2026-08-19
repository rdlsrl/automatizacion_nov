"""Shared JSON serialization helpers for SQLite-backed repositories."""

from __future__ import annotations

from dataclasses import fields, is_dataclass
from datetime import date, datetime
from enum import Enum
import json
from types import UnionType
from typing import Any, get_args, get_origin, get_type_hints

from drilling_knowledge.common.ids import Identifier


def to_primitive(value: object) -> object:
    if isinstance(value, Identifier):
        return str(value)
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if is_dataclass(value):
        return {field.name: to_primitive(getattr(value, field.name)) for field in fields(value)}
    if isinstance(value, tuple):
        return [to_primitive(item) for item in value]
    if isinstance(value, list):
        return [to_primitive(item) for item in value]
    if isinstance(value, dict):
        return {str(key): to_primitive(item) for key, item in value.items()}
    return value


def to_json(value: object) -> str:
    return json.dumps(to_primitive(value), sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def from_json(payload: str, expected_type: type[Any]) -> Any:
    return hydrate(json.loads(payload), expected_type)


def hydrate(value: object, expected_type: object) -> Any:
    if expected_type is Any:
        return value

    origin = get_origin(expected_type)
    args = get_args(expected_type)

    if origin in (UnionType, getattr(__import__("typing"), "Union")):
        non_none = [item for item in args if item is not type(None)]
        if value is None:
            return None
        for candidate in non_none:
            try:
                return hydrate(value, candidate)
            except Exception:
                continue
        raise ValueError(f"Cannot hydrate value for union type {expected_type!r}")

    if value is None:
        return None

    if origin is tuple:
        item_type = args[0] if args else Any
        return tuple(hydrate(item, item_type) for item in value)
    if origin is list:
        item_type = args[0] if args else Any
        return [hydrate(item, item_type) for item in value]
    if origin is dict:
        key_type = args[0] if args else Any
        value_type = args[1] if len(args) > 1 else Any
        return {hydrate(key, key_type): hydrate(item, value_type) for key, item in value.items()}

    if isinstance(expected_type, type):
        if issubclass(expected_type, Identifier):
            return expected_type.from_string(str(value))
        if issubclass(expected_type, Enum):
            return expected_type(value)
        if expected_type is datetime:
            return datetime.fromisoformat(str(value))
        if expected_type is date:
            return date.fromisoformat(str(value))
        if is_dataclass(expected_type):
            hints = get_type_hints(expected_type)
            return expected_type(
                **{
                    field.name: hydrate(value[field.name], hints.get(field.name, Any))
                    for field in fields(expected_type)
                }
            )
        if expected_type in (str, int, float, bool):
            return expected_type(value)

    return value