from __future__ import annotations

import os
import unittest
from unittest.mock import patch

from drilling_knowledge.common.exceptions import ConfigurationError
from drilling_knowledge.config.settings import AppSettings


class AppSettingsTests(unittest.TestCase):
    def test_settings_are_loaded_from_environment(self) -> None:
        env = {
            "DKP_ENVIRONMENT": "test",
            "DKP_LOG_LEVEL": "debug",
            "DKP_LOG_JSON": "true",
        }
        with patch.dict(os.environ, env, clear=False):
            settings = AppSettings.from_env()

        self.assertEqual(settings.environment, "test")
        self.assertEqual(settings.log_level, "DEBUG")
        self.assertTrue(settings.log_json)

    def test_invalid_boolean_setting_raises_configuration_error(self) -> None:
        with patch.dict(os.environ, {"DKP_LOG_JSON": "maybe"}, clear=False):
            with self.assertRaises(ConfigurationError):
                AppSettings.from_env()
