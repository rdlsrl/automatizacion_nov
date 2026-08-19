from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from drilling_knowledge.documents import DocumentKnowledgeAcquisitionEngine, DocumentMetadata
from drilling_knowledge.extraction import ExtractedEntityType, ExtractedObservationType, KnowledgeExtractionEngine


FIXTURES_DIR = Path(__file__).resolve().parents[2] / "fixtures" / "extraction"


class KnowledgeExtractionEngineTests(unittest.TestCase):
    def setUp(self) -> None:
        self.document_engine = DocumentKnowledgeAcquisitionEngine.create()
        self.extraction_engine = KnowledgeExtractionEngine.create()

    def test_extracts_required_entity_types_from_realistic_fixture_set(self) -> None:
        snapshots = [
            self._ingest("nov_manual.md", source="nov_manual"),
            self._ingest("instrumentation_manual.md", source="instrumentation_manual"),
            self._ingest("witsml_manual.md", source="witsml_manual"),
            self._ingest("datasheet.md", source="datasheet"),
            self._ingest("procedure.md", source="procedure"),
            self._ingest("explicit_extraction.md", source="explicit_extraction"),
        ]

        runs = [self.extraction_engine.extract(snapshot) for snapshot in snapshots]
        extracted_types = {entity.entity_type for run in runs for entity in run.entities}

        self.assertTrue({
            ExtractedEntityType.VARIABLE,
            ExtractedEntityType.MNEMONIC,
            ExtractedEntityType.SENSOR,
            ExtractedEntityType.INSTRUMENT,
            ExtractedEntityType.EQUIPMENT,
            ExtractedEntityType.SYSTEM,
            ExtractedEntityType.SUBSYSTEM,
            ExtractedEntityType.PROCESS,
            ExtractedEntityType.PHYSICAL_QUANTITY,
            ExtractedEntityType.ENGINEERING_UNIT,
            ExtractedEntityType.MANUFACTURER,
            ExtractedEntityType.MODEL,
            ExtractedEntityType.STANDARD,
            ExtractedEntityType.ALIAS,
            ExtractedEntityType.ABBREVIATION,
            ExtractedEntityType.TAG,
            ExtractedEntityType.TAG_TOKEN,
            ExtractedEntityType.DOCUMENT_REFERENCE,
            ExtractedEntityType.TABLE_REFERENCE,
            ExtractedEntityType.FIGURE_REFERENCE,
            ExtractedEntityType.SECTION_REFERENCE,
            ExtractedEntityType.NUMBER,
            ExtractedEntityType.RANGE,
            ExtractedEntityType.RAW_SIGNAL,
            ExtractedEntityType.FORMULA,
            ExtractedEntityType.IDENTIFIER,
        }.issubset(extracted_types))

    def test_does_not_unify_distinct_explicit_mentions(self) -> None:
        snapshot = self._ingest("explicit_extraction.md", source="explicit_extraction")
        run = self.extraction_engine.extract(snapshot)

        variable_texts = [entity.original_text for entity in run.entities if entity.entity_type == ExtractedEntityType.VARIABLE]
        mnemonic_texts = [entity.original_text for entity in run.entities if entity.entity_type == ExtractedEntityType.MNEMONIC]

        self.assertIn("Hook Load", variable_texts)
        self.assertIn("Peso Gancho", variable_texts)
        self.assertIn("HKLD", mnemonic_texts)

    def test_metrics_report_entities_by_type_rule_document_time_and_errors(self) -> None:
        snapshot = self._ingest("datasheet.md", source="datasheet")
        run = self.extraction_engine.extract(snapshot)

        self.assertGreater(run.metrics.total_entities, 0)
        self.assertIn("MANUFACTURER", run.metrics.entity_counts_by_type)
        self.assertTrue(any(record.extraction_rule for record in run.metrics.records))
        self.assertIn(str(snapshot.document.entity_id), run.metrics.document_counts)
        self.assertGreaterEqual(run.metrics.duration_ms, 0)
        self.assertEqual(run.metrics.errors, ())

    def test_entities_preserve_requested_trace_fields(self) -> None:
        snapshot = self._ingest("nov_manual.md", source="nov_manual")
        run = self.extraction_engine.extract(snapshot)
        entity = next(entity for entity in run.entities if entity.original_text == "HKLD")
        source_fragment = next(fragment for fragment in snapshot.fragments if fragment.entity_id == entity.fragment_id)

        self.assertEqual(entity.document_id, snapshot.document.entity_id)
        self.assertEqual(entity.version_id, snapshot.version.entity_id)
        self.assertIsNotNone(entity.fragment_id)
        self.assertTrue(entity.document_position.startswith("fragment="))
        self.assertEqual(entity.context_window.match_text, "HKLD")
        self.assertEqual(entity.source_trace.paragraph_ordinal, source_fragment.trace.paragraph_ordinal)

    def test_extracts_from_tables_and_preserves_textual_unit_observation(self) -> None:
        snapshot = self._ingest("nov_manual.md", source="nov_manual")
        run = self.extraction_engine.extract(snapshot)

        self.assertTrue(any(entity.original_text == "HKLD" and entity.entity_type == ExtractedEntityType.MNEMONIC for entity in run.entities))
        self.assertTrue(any(entity.original_text == "Hook Load" and entity.entity_type == ExtractedEntityType.VARIABLE for entity in run.entities))
        self.assertTrue(any(observation.observation_type == ExtractedObservationType.TEXTUAL_UNIT_ASSOCIATION and "klbf" in observation.original_text for observation in run.observations))

    def test_extracts_energistics_schema_relations_from_html_tables(self) -> None:
        html = b'''<!DOCTYPE html><html><head><meta name="DC.Title" content="SurfaceEquipment"></meta><title>SurfaceEquipment</title></head><body><table><caption><span>Attributes</span></caption><tr><th><p>Name</p></th><th><p>Type</p></th><th><p>Notes</p></th></tr><tr><td><p>IdStandpipe</p></td><td><p>LengthMeasure</p></td><td><p>Inner diameter of the standpipe.</p></td></tr></table></body></html>'''
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "WITSML-SurfaceEquipment.html"
            path.write_bytes(html)
            metadata = DocumentMetadata(document_type="reference", source="energistics", language="en", authority_level="reference")
            snapshot = self.document_engine.ingest(path, metadata).snapshot

        run = self.extraction_engine.extract(snapshot)

        self.assertTrue(any(entity.original_text == "SurfaceEquipment" for entity in run.entities))
        self.assertTrue(any(entity.original_text == "IdStandpipe" for entity in run.entities))
        self.assertTrue(any(entity.original_text == "LengthMeasure" for entity in run.entities))
        self.assertTrue(any(observation.observation_type == ExtractedObservationType.HAS_PROPERTY for observation in run.observations))
        self.assertTrue(any(observation.observation_type == ExtractedObservationType.MEASUREMENT_TYPE for observation in run.observations))

    def test_extracts_from_glossaries(self) -> None:
        snapshot = self._ingest("explicit_extraction.md", source="explicit_extraction")
        run = self.extraction_engine.extract(snapshot)

        self.assertTrue(any(entity.original_text == "Peso Gancho" and entity.entity_type == ExtractedEntityType.VARIABLE for entity in run.entities))
        self.assertTrue(any(entity.original_text == "HKLD" and entity.fragment_id in {term.entity_id for term in snapshot.glossary_terms} for entity in run.entities))

    def test_extracts_tags_mnemonics_and_tag_tokens_without_resolving_meaning(self) -> None:
        snapshot = self._ingest("explicit_extraction.md", source="explicit_extraction")
        run = self.extraction_engine.extract(snapshot)

        self.assertTrue(any(entity.original_text == "Pileta_Gas_Oil_Q1" and entity.entity_type == ExtractedEntityType.TAG for entity in run.entities))
        token_texts = [entity.original_text for entity in run.entities if entity.entity_type == ExtractedEntityType.TAG_TOKEN]
        self.assertIn("Pileta", token_texts)
        self.assertIn("Gas", token_texts)
        self.assertIn("Oil", token_texts)
        self.assertIn("Q1", token_texts)
        self.assertFalse(any(entity.original_text == "Q1" and entity.entity_type == ExtractedEntityType.SUBSYSTEM for entity in run.entities))

    def test_extracts_sensors_and_instruments(self) -> None:
        snapshot = self._ingest("instrumentation_manual.md", source="instrumentation_manual")
        run = self.extraction_engine.extract(snapshot)

        self.assertTrue(any(entity.original_text == "Pressure Sensor" and entity.entity_type == ExtractedEntityType.SENSOR for entity in run.entities))
        self.assertTrue(any(entity.original_text == "Pressure Transmitter" and entity.entity_type == ExtractedEntityType.INSTRUMENT for entity in run.entities))

    def test_extracts_ranges_raw_signals_scaling_and_formulas(self) -> None:
        snapshot = self._ingest("explicit_extraction.md", source="explicit_extraction")
        run = self.extraction_engine.extract(snapshot)

        self.assertTrue(any(entity.original_text == "0-5000 psi" and entity.entity_type == ExtractedEntityType.RANGE for entity in run.entities))
        self.assertTrue(any(entity.original_text == "4-20 mA" and entity.entity_type == ExtractedEntityType.RAW_SIGNAL for entity in run.entities))
        self.assertTrue(any(entity.original_text == "0-10 V" and entity.entity_type == ExtractedEntityType.RAW_SIGNAL for entity in run.entities))
        self.assertTrue(any(entity.original_text == "1024 counts" and entity.entity_type == ExtractedEntityType.RAW_SIGNAL for entity in run.entities))
        self.assertTrue(any(entity.original_text == "30 pulses" and entity.entity_type == ExtractedEntityType.RAW_SIGNAL for entity in run.entities))
        self.assertTrue(any(entity.original_text == "ROP = Depth / Time" and entity.entity_type == ExtractedEntityType.FORMULA for entity in run.entities))
        scaling = [observation for observation in run.observations if observation.observation_type == ExtractedObservationType.EXPLICIT_SCALING]
        self.assertTrue(any(observation.original_text == "4 mA = 0 psi" for observation in scaling))
        self.assertTrue(any(observation.original_text == "20 mA = 5000 psi" for observation in scaling))

    def test_preserves_exact_original_text_and_provenance(self) -> None:
        snapshot = self._ingest("explicit_extraction.md", source="explicit_extraction")
        run = self.extraction_engine.extract(snapshot)
        tag = next(entity for entity in run.entities if entity.original_text == "Pileta_Gas_Oil_Q1")
        scaling = next(observation for observation in run.observations if observation.original_text == "4 mA = 0 psi")

        self.assertEqual(tag.normalized_text, "pileta_gas_oil_q1")
        self.assertEqual(scaling.context_window.match_text, "4 mA = 0 psi")
        self.assertEqual(scaling.document_id, snapshot.document.entity_id)
        self.assertEqual(scaling.version_id, snapshot.version.entity_id)
        self.assertTrue(scaling.document_position.startswith("fragment="))

    def test_uses_extraction_confidence_and_never_semantic_confidence(self) -> None:
        snapshot = self._ingest("explicit_extraction.md", source="explicit_extraction")
        run = self.extraction_engine.extract(snapshot)

        tag = next(entity for entity in run.entities if entity.original_text == "Pileta_Gas_Oil_Q1")
        self.assertEqual(tag.extraction_confidence, 1.0)
        self.assertFalse(hasattr(tag, "semantic_confidence"))

        scaling = next(observation for observation in run.observations if observation.original_text == "4 mA = 0 psi")
        self.assertEqual(scaling.extraction_confidence, 1.0)
        self.assertFalse(hasattr(scaling, "semantic_confidence"))

    def test_tag_tokens_remain_lexical_artifacts_without_semantic_assertion(self) -> None:
        snapshot = self._ingest("explicit_extraction.md", source="explicit_extraction")
        run = self.extraction_engine.extract(snapshot)

        q1_tokens = [entity for entity in run.entities if entity.original_text == "Q1"]
        self.assertTrue(q1_tokens)
        self.assertTrue(all(entity.entity_type == ExtractedEntityType.TAG_TOKEN for entity in q1_tokens))
        self.assertFalse(any(entity.original_text == "Q1" and entity.entity_type in {ExtractedEntityType.SYSTEM, ExtractedEntityType.SUBSYSTEM, ExtractedEntityType.SENSOR, ExtractedEntityType.INSTRUMENT} for entity in run.entities))

    def test_unresolved_structural_reference_keeps_structural_type(self) -> None:
        snapshot = self._ingest("witsml_manual.md", source="witsml_manual")
        run = self.extraction_engine.extract(snapshot)

        table_reference = next(entity for entity in run.entities if entity.original_text == "Table 2")
        self.assertEqual(table_reference.entity_type, ExtractedEntityType.TABLE_REFERENCE)
        self.assertTrue(any(entity.original_text == "API RP 13D" for entity in run.entities if entity.entity_type == ExtractedEntityType.DOCUMENT_REFERENCE))

    def test_overlapping_numeric_noise_is_suppressed(self) -> None:
        snapshot = self._ingest("datasheet.md", source="datasheet")
        run = self.extraction_engine.extract(snapshot)

        tag_entities = [entity for entity in run.entities if entity.original_text == "PT-700-01"]
        self.assertEqual(len(tag_entities), 1)
        self.assertFalse(any(entity.original_text == "700-01" for entity in run.entities if entity.entity_type == ExtractedEntityType.RANGE))

        range_entity = next(entity for entity in run.entities if entity.original_text == "10 to 150 psi")
        self.assertEqual(range_entity.entity_type, ExtractedEntityType.RANGE)
        self.assertFalse(
            any(
                entity.entity_type == ExtractedEntityType.NUMBER
                and entity.fragment_id == range_entity.fragment_id
                and entity.source_trace.start_offset is not None
                and entity.source_trace.end_offset is not None
                and range_entity.source_trace.start_offset is not None
                and range_entity.source_trace.end_offset is not None
                and entity.source_trace.start_offset >= range_entity.source_trace.start_offset
                and entity.source_trace.end_offset <= range_entity.source_trace.end_offset
                for entity in run.entities
            )
        )

    def test_partial_errors_are_isolated_without_losing_other_entities(self) -> None:
        snapshot = self._ingest("instrumentation_manual.md", source="instrumentation_manual")

        class FaultyExtractionEngine(KnowledgeExtractionEngine):
            def _extract_from_fragment(self, snapshot, fragment):  # type: ignore[override]
                if "Pressure Sensor" in fragment.text_content:
                    raise RuntimeError("simulated extraction failure")
                return super()._extract_from_fragment(snapshot, fragment)

        run = FaultyExtractionEngine.create().extract(snapshot)

        self.assertEqual(run.status.value, "failed")
        self.assertTrue(run.metrics.errors)
        self.assertTrue(any(entity.original_text == "Emerson" for entity in run.entities))
        self.assertTrue(any("simulated extraction failure" in error for error in run.metrics.errors))

    def test_offsets_are_assigned_to_repeated_structural_references(self) -> None:
        markdown = b"# Repeat Refs\n\nSee Figure 1. See Figure 1 again.\n\n![Figure 1](fig.png)"
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "repeat.md"
            path.write_bytes(markdown)
            metadata = DocumentMetadata(document_type="manual", source="repeat_refs", language="en", authority_level="reference")
            snapshot = self.document_engine.ingest(path, metadata).snapshot

        run = self.extraction_engine.extract(snapshot)
        figure_refs = [entity for entity in run.entities if entity.entity_type == ExtractedEntityType.FIGURE_REFERENCE]

        self.assertEqual(len(figure_refs), 2)
        self.assertNotEqual(figure_refs[0].source_trace.start_offset, figure_refs[1].source_trace.start_offset)
        self.assertTrue(all(entity.source_trace.end_offset is not None for entity in figure_refs))

    def test_output_is_deterministic_for_entities_and_observations(self) -> None:
        snapshot = self._ingest("explicit_extraction.md", source="explicit_extraction")
        first_run = self.extraction_engine.extract(snapshot)
        second_run = self.extraction_engine.extract(snapshot)

        self.assertEqual(
            [(entity.entity_type, entity.original_text, entity.source_trace.start_offset, entity.source_trace.end_offset) for entity in first_run.entities],
            [(entity.entity_type, entity.original_text, entity.source_trace.start_offset, entity.source_trace.end_offset) for entity in second_run.entities],
        )
        self.assertEqual(
            [(observation.observation_type, observation.original_text, observation.source_trace.start_offset, observation.source_trace.end_offset) for observation in first_run.observations],
            [(observation.observation_type, observation.original_text, observation.source_trace.start_offset, observation.source_trace.end_offset) for observation in second_run.observations],
        )

    def _ingest(self, fixture_name: str, *, source: str):
        metadata = DocumentMetadata(
            author="Test Author",
            manufacturer="Fixture Manufacturer",
            model="Fixture Model",
            version_label="1.0",
            language="en",
            authority_level="reference",
            document_type="manual",
            source=source,
            license_name="internal-test",
        )
        return self.document_engine.ingest(FIXTURES_DIR / fixture_name, metadata).snapshot