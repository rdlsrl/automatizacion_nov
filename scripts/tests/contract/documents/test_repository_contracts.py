from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from drilling_knowledge.documents import DocumentKnowledgeAcquisitionEngine, DocumentMetadata


class DocumentRepositoryContractTests(unittest.TestCase):
    def test_repository_persists_document_version_with_full_traceability(self) -> None:
        engine = DocumentKnowledgeAcquisitionEngine.create()
        metadata = DocumentMetadata(document_type="datasheet", source="contract_test", language="en", authority_level="reference")
        payload = b"# Datasheet\n\nParagraph one.\n\nParagraph two."

        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "datasheet.md"
            path.write_bytes(payload)
            result = engine.ingest(path, metadata)

        self.assertEqual(len(result.repository.documents), 1)
        self.assertEqual(len(result.repository.versions), 1)
        self.assertTrue(all(fragment.trace.document_version_id == result.snapshot.version.entity_id for fragment in result.repository.fragments))
        self.assertTrue(all(fragment.trace.document_id == result.snapshot.document.entity_id for fragment in result.repository.fragments))
        self.assertTrue(all(fragment.content_hash for fragment in result.repository.fragments))