from __future__ import annotations

from datetime import UTC, datetime
import unittest

from drilling_knowledge.common.ids import EntityId
from drilling_knowledge.loader import (
    ArtifactDecision,
    ArtifactFingerprint,
    DispatchRequest,
    DispatchResult,
    DiscoveredDocument,
    DownloadedArtifact,
    GapCandidate,
    LasFileRecord,
    LoadPolicy,
    MnemonicAggregate,
    MnemonicObservation,
    SourceDefinition,
)


class LoaderContractTests(unittest.TestCase):
    def test_public_contracts_accept_valid_values(self) -> None:
        definition = SourceDefinition("nov", "NOV", ("https://example.com/",), ("example.com",), (".pdf",), "mixed")
        policy = LoadPolicy(max_documents_per_run=5)
        discovered = DiscoveredDocument("nov", "NOV", "https://example.com/manual.pdf", None, ".pdf", datetime(2026, 1, 1, tzinfo=UTC))
        downloaded = DownloadedArtifact(EntityId.from_seed("loader.artifact", "one"), "nov", discovered.document_url, discovered.document_url, "/tmp/manual.pdf", "application/pdf", 100, datetime(2026, 1, 1, tzinfo=UTC))
        fingerprint = ArtifactFingerprint(downloaded.artifact_id, "a" * 64, discovered.document_url, "manual.pdf")
        decision = ArtifactDecision(downloaded.artifact_id, EntityId.from_seed("loader.lineage", "one"), "new", "new_document", True, "ok")
        request = DispatchRequest(downloaded.artifact_id, "/tmp/manual.pdf", "nov", "NOV", (), (("original_url", discovered.document_url),))
        result = DispatchResult(downloaded.artifact_id, "skipped")
        las = LasFileRecord(EntityId.from_seed("loader.las", "one"), "/tmp/sample.las", "b" * 64, None, None, datetime(2026, 1, 1, tzinfo=UTC))
        observation = MnemonicObservation(las.las_file_id, "SPP", "psi", "Standpipe Pressure", False, 1)
        aggregate = MnemonicAggregate("SPP", ("SPP", "Standpipe Pressure"), ("psi",), 1, ("/tmp/sample.las",))
        gap = GapCandidate(EntityId.from_seed("loader.gap", "one"), "unknown_variable", "SPP", ("SPP",), ("psi",), 1, ("/tmp/sample.las",), True)

        self.assertEqual(definition.source_name, "nov")
        self.assertEqual(policy.max_documents_per_run, 5)
        self.assertEqual(fingerprint.normalized_filename, "manual.pdf")
        self.assertTrue(decision.dispatchable)
        self.assertEqual(request.source_name, "nov")
        self.assertEqual(result.status, "skipped")
        self.assertEqual(observation.mnemonic, "SPP")
        self.assertEqual(aggregate.normalized_mnemonic, "SPP")
        self.assertEqual(gap.gap_type, "unknown_variable")