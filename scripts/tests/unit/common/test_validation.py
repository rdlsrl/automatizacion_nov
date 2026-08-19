from __future__ import annotations

import unittest

from drilling_knowledge.common.exceptions import ValidationError
from drilling_knowledge.common.validation import ValidationReport, ValidationSeverity, ensure


class ValidationTests(unittest.TestCase):
    def test_validation_report_tracks_errors_and_warnings(self) -> None:
        report = ValidationReport()
        report.add_error("missing_field", "Name is required", path="name")
        report.add_warning("deprecated_field", "Legacy field present", path="legacy")

        self.assertFalse(report.is_valid)
        self.assertEqual(len(report.errors), 1)
        self.assertEqual(len(report.warnings), 1)
        self.assertEqual(report.warnings[0].severity, ValidationSeverity.WARNING)

    def test_validation_report_raises_on_invalid_state(self) -> None:
        report = ensure(False, code="invalid", message="broken")

        with self.assertRaises(ValidationError):
            report.require_valid()
