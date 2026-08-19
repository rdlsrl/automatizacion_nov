from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from drilling_knowledge.loader import ArtifactRegistry


class LoaderSchemaContractsTests(unittest.TestCase):
    def test_registry_creates_expected_sqlite_tables(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            registry = ArtifactRegistry.create(Path(temp_dir) / "loader.sqlite")

            self.assertEqual(
                set(registry.list_tables()),
                {
                    "artifact_fingerprints",
                    "dispatch_results",
                    "discovered_documents",
                    "document_lineages",
                    "document_versions",
                    "downloaded_artifacts",
                    "gap_candidates",
                    "las_files",
                    "las_mnemonic_observations",
                    "load_runs",
                    "source_definitions",
                },
            )