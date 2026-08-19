"""Application-level settings for the platform."""

from __future__ import annotations

import os
from dataclasses import dataclass

from drilling_knowledge.common.exceptions import ConfigurationError


@dataclass(frozen=True, slots=True)
class AppSettings:
    """Minimal runtime settings for Sprint 1 foundation code."""

    app_name: str = "drilling-knowledge-platform"
    environment: str = "dev"
    log_level: str = "INFO"
    log_json: bool = False

    @classmethod
    def from_env(cls, prefix: str = "DKP_") -> "AppSettings":
        defaults = cls()
        environment = os.getenv(f"{prefix}ENVIRONMENT", defaults.environment)
        log_level = os.getenv(f"{prefix}LOG_LEVEL", defaults.log_level).upper()
        log_json_raw = os.getenv(f"{prefix}LOG_JSON", "false").strip().lower()
        if log_json_raw not in {"true", "false", "1", "0", "yes", "no"}:
            raise ConfigurationError(
                code="invalid_setting",
                message="DKP_LOG_JSON must be a boolean-like value",
                context={"value": log_json_raw},
            )
        log_json = log_json_raw in {"true", "1", "yes"}
        return cls(environment=environment, log_level=log_level, log_json=log_json)
