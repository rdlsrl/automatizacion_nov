from __future__ import annotations

import io
from contextlib import redirect_stdout
import unittest

from drilling_knowledge.loader.cli import main
from drilling_knowledge.loader.orchestrator import LoadRunSummary
from drilling_knowledge.common.ids import RunId


class LoaderCliTests(unittest.TestCase):
    def test_load_command_delegates_to_orchestrator(self) -> None:
        orchestrator = _StubOrchestrator()
        output = io.StringIO()
        with redirect_stdout(output):
            exit_code = main(["load", "nov", "--limit", "5", "--dry-run", "--resume"], orchestrator=orchestrator)

        self.assertEqual(exit_code, 0)
        self.assertEqual(orchestrator.last_call[0], "source")
        self.assertTrue(orchestrator.last_call[2].resume)
        self.assertIn("target=nov", output.getvalue())

    def test_load_las_command_delegates_to_orchestrator(self) -> None:
        orchestrator = _StubOrchestrator()
        output = io.StringIO()
        with redirect_stdout(output):
            exit_code = main(["load-las", "/tmp/las", "--recursive", "--dry-run"], orchestrator=orchestrator)

        self.assertEqual(exit_code, 0)
        self.assertEqual(orchestrator.last_call[0], "las")
        self.assertIn("gaps_detected=2", output.getvalue())


class _StubOrchestrator:
    def __init__(self) -> None:
        self.last_call = None

    def load_source(self, source_name, policy):
        self.last_call = ("source", source_name, policy)
        return LoadRunSummary(RunId.from_seed("loader.test", "source"), "document", source_name, 1, 0, 0, 0, 0, 0, 0)

    def load_las(self, folder, policy):
        self.last_call = ("las", str(folder), policy)
        return LoadRunSummary(RunId.from_seed("loader.test", "las"), "las", str(folder), 0, 3, 0, 0, 0, 0, 2)