from __future__ import annotations

import unittest

from drilling_knowledge.common.types import Result


class ResultTests(unittest.TestCase):
    def test_success_result_unwraps_value(self) -> None:
        result: Result[int, str] = Result.ok(7)

        self.assertTrue(result.is_ok)
        self.assertFalse(result.is_error)
        self.assertEqual(result.unwrap(), 7)

    def test_failed_result_unwraps_error(self) -> None:
        result: Result[int, str] = Result.fail("boom")

        self.assertFalse(result.is_ok)
        self.assertTrue(result.is_error)
        self.assertEqual(result.unwrap_error(), "boom")

    def test_unwrapping_error_result_raises(self) -> None:
        result: Result[int, str] = Result.fail("boom")

        with self.assertRaises(RuntimeError):
            result.unwrap()
