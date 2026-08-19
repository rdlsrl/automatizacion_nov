from __future__ import annotations

import io
from contextlib import redirect_stdout
from pathlib import Path
import tempfile
import unittest

from drilling_knowledge.loader import LoadOrchestrator, SourceAdapter, SourceDefinition
from drilling_knowledge.loader.cli import main


class LoaderEndToEndTests(unittest.TestCase):
    def test_cli_load_and_cli_load_las_complete_end_to_end(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            document = root / "manual.md"
            document.write_text("# Manual\n\n4 mA = 0 psi\n", encoding="utf-8")
            listing = root / "index.html"
            listing.write_text(f'<html><body><a href="{document.as_uri()}">manual</a></body></html>', encoding="utf-8")
            las = root / "sample.las"
            las.write_text("~Curve\nSPP.PSI : Standpipe Pressure\n~A\n", encoding="utf-8")
            orchestrator = LoadOrchestrator.create_default(database_path=root / "loader.sqlite", workspace_root=root)
            orchestrator.source_adapter = SourceAdapter((SourceDefinition("nov", "NOV", (listing.as_uri(),), ("",), (".md",), "html_listing"),), root)
            orchestrator.artifact_registry.record_source_definition(orchestrator.source_adapter.definition_for("nov"))

            stdout = io.StringIO()
            with redirect_stdout(stdout):
                code_load = main(["load", "nov"], orchestrator=orchestrator)
                code_las = main(["load-las", str(root)], orchestrator=orchestrator)

            self.assertEqual(code_load, 0)
            self.assertEqual(code_las, 0)
            rendered = stdout.getvalue()
            self.assertIn("target=nov", rendered)
            self.assertIn(f"target={root}", rendered)