from __future__ import annotations

from pathlib import Path
import unittest

from drilling_knowledge.documents import DocumentKnowledgeAcquisitionEngine, DocumentMetadata
from drilling_knowledge.extraction import ExtractedEntityType, KnowledgeExtractionEngine


FIXTURES_DIR = Path(__file__).resolve().parents[2] / "fixtures" / "extraction"


class KnowledgeExtractionEngineContractTests(unittest.TestCase):
    def test_extraction_run_is_deterministic_for_same_document_version(self) -> None:
        document_engine = DocumentKnowledgeAcquisitionEngine.create()
        extraction_engine = KnowledgeExtractionEngine.create()
        metadata = DocumentMetadata(
            document_type="manual",
            source="contract_test",
            language="en",
            authority_level="reference",
        )
        snapshot = document_engine.ingest(FIXTURES_DIR / "nov_manual.md", metadata).snapshot

        first_run = extraction_engine.extract(snapshot)
        second_run = extraction_engine.extract(snapshot)

        self.assertEqual(
            [(entity.entity_id, entity.entity_type, entity.original_text, entity.fragment_id, entity.extraction_rule) for entity in first_run.entities],
            [(entity.entity_id, entity.entity_type, entity.original_text, entity.fragment_id, entity.extraction_rule) for entity in second_run.entities],
        )
        self.assertEqual(
            [(observation.observation_id, observation.observation_type, observation.original_text, observation.fragment_id, observation.extraction_rule) for observation in first_run.observations],
            [(observation.observation_id, observation.observation_type, observation.original_text, observation.fragment_id, observation.extraction_rule) for observation in second_run.observations],
        )
        self.assertEqual(first_run.metrics.total_entities, second_run.metrics.total_entities)

    def test_output_order_is_stable_for_same_document_version(self) -> None:
        document_engine = DocumentKnowledgeAcquisitionEngine.create()
        extraction_engine = KnowledgeExtractionEngine.create()
        metadata = DocumentMetadata(
            document_type="manual",
            source="contract_test",
            language="en",
            authority_level="reference",
        )
        snapshot = document_engine.ingest(FIXTURES_DIR / "procedure.md", metadata).snapshot

        first_run = extraction_engine.extract(snapshot)
        second_run = extraction_engine.extract(snapshot)

        self.assertEqual(
            [(entity.entity_type, entity.original_text, entity.source_trace.start_offset, entity.source_trace.end_offset) for entity in first_run.entities],
            [(entity.entity_type, entity.original_text, entity.source_trace.start_offset, entity.source_trace.end_offset) for entity in second_run.entities],
        )

    def test_structural_references_are_extracted_as_separate_entities(self) -> None:
        document_engine = DocumentKnowledgeAcquisitionEngine.create()
        extraction_engine = KnowledgeExtractionEngine.create()
        metadata = DocumentMetadata(
            document_type="manual",
            source="contract_test",
            language="en",
            authority_level="reference",
        )
        snapshot = document_engine.ingest(FIXTURES_DIR / "nov_manual.md", metadata).snapshot
        run = extraction_engine.extract(snapshot)

        self.assertTrue(any(entity.entity_type == ExtractedEntityType.FIGURE_REFERENCE and entity.original_text == "Figure 1" for entity in run.entities))
        self.assertTrue(any(entity.entity_type == ExtractedEntityType.TABLE_REFERENCE and entity.original_text == "Table 1" for entity in run.entities))
        self.assertTrue(any(entity.entity_type == ExtractedEntityType.SECTION_REFERENCE and entity.original_text == "Section 5.1" for entity in run.entities))

    def test_extraction_outputs_only_extraction_confidence(self) -> None:
        document_engine = DocumentKnowledgeAcquisitionEngine.create()
        extraction_engine = KnowledgeExtractionEngine.create()
        metadata = DocumentMetadata(
            document_type="manual",
            source="contract_test",
            language="en",
            authority_level="reference",
        )
        snapshot = document_engine.ingest(FIXTURES_DIR / "explicit_extraction.md", metadata).snapshot

        run = extraction_engine.extract(snapshot)
        tag = next(entity for entity in run.entities if entity.original_text == "Pileta_Gas_Oil_Q1")

        self.assertEqual(tag.extraction_confidence, 1.0)
        self.assertFalse(hasattr(tag, "semantic_confidence"))