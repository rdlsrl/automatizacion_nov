from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
import tempfile
import unittest

from drilling_knowledge.common.ids import EntityId
from drilling_knowledge.loader import ArtifactRegistry, DownloadedArtifact, LasFileRecord, MnemonicObservation


class ArtifactRegistryTests(unittest.TestCase):
    def test_deduplicates_by_sha_and_versions_by_lineage(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            database = root / "loader.sqlite"
            registry = ArtifactRegistry.create(database)
            first_path = root / "manual-a.md"
            second_path = root / "manual-b.md"
            first_path.write_text("same", encoding="utf-8")
            second_path.write_text("changed", encoding="utf-8")

            first = DownloadedArtifact(EntityId.from_seed("loader.test", "a"), "nov", "file:///manual-a.md", "file:///manual-a.md", str(first_path), "text/markdown", 4, datetime(2026, 1, 1, tzinfo=UTC))
            second = DownloadedArtifact(EntityId.from_seed("loader.test", "b"), "nov", "file:///manual-a.md", "file:///manual-a.md", str(first_path), "text/markdown", 4, datetime(2026, 1, 2, tzinfo=UTC))
            third = DownloadedArtifact(EntityId.from_seed("loader.test", "c"), "nov", "file:///manual-b.md", "file:///manual-b.md", str(second_path), "text/markdown", 7, datetime(2026, 1, 3, tzinfo=UTC))

            _, first_decision = registry.register_downloaded_artifact(first)
            _, second_decision = registry.register_downloaded_artifact(second)
            _, third_decision = registry.register_downloaded_artifact(third)

            self.assertEqual(first_decision.version_status, "new_document")
            self.assertEqual(second_decision.dedup_status, "duplicate_exact")
            self.assertEqual(third_decision.version_status, "new_document")

    def test_builds_gap_candidates_from_las_observations(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            database = Path(temp_dir) / "loader.sqlite"
            registry = ArtifactRegistry.create(database)
            record = LasFileRecord(EntityId.from_seed("loader.las", "sample"), "/tmp/sample.las", "a" * 64, "Well A", "Pason", datetime(2026, 1, 1, tzinfo=UTC))
            observations = (
                MnemonicObservation(record.las_file_id, "SPP", "psi", "Standpipe Pressure", False, 1),
                MnemonicObservation(record.las_file_id, "SPP", "bar", "Pump Pressure", False, 1),
            )
            registry.register_las_file(record, observations)

            gaps = registry.build_gap_candidates()

            self.assertTrue(any(item.gap_type == "potential_alias" for item in gaps))
            self.assertTrue(any(item.gap_type == "ambiguous_mnemonic" for item in gaps))