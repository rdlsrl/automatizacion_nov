from __future__ import annotations

from datetime import datetime
import unittest

from drilling_knowledge.common.ids import EntityId
from drilling_knowledge.extraction.domain import ExtractionSourceTrace
from drilling_knowledge.technical_knowledge import (
    EvidenceLevel,
    EvidenceStatus,
    InMemoryTechnicalKnowledgeRepository,
    MeasurementKind,
    RawSignalType,
    TechnicalEntityReference,
    TechnicalEntityType,
    TechnicalKnowledgeService,
    TechnicalRelationType,
    WorkingRangeKind,
)


class TechnicalKnowledgeServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.service = TechnicalKnowledgeService.create(InMemoryTechnicalKnowledgeRepository.empty())
        self.trace = ExtractionSourceTrace(page_number=1, paragraph_ordinal=1, start_offset=0, end_offset=10)
        self.created_at = datetime(2026, 1, 1, 12, 0, 0)

    def test_primary_measurement_with_physical_sensor(self) -> None:
        evidence_id = self._evidence("primary")
        variable = self.service.register_variable(
            variable_id=self._id("hook_load"),
            canonical_name="Hook Load",
            family="surface load",
            physical_quantity="force",
            subsystem="hoisting",
            process_context="drilling",
            criticality="high",
            measurement_kind=MeasurementKind.PRIMARY_MEASUREMENT,
            evidence_ids=(evidence_id,),
        )
        sensor = self.service.register_sensor(
            sensor_id=self._id("sensor.load_pin"),
            sensor_type="Load Pin",
            measurement_principle="strain gauge",
            manufacturer="NOV",
            model="LP-200",
            physical_location_typical="deadline anchor",
            physical_location_specific="rig floor anchor",
            installation_context="hoisting",
            accuracy="0.5% FS",
            resolution="0.1 klbf",
            sampling_rate="10 Hz",
            operating_conditions="outdoor",
            evidence_ids=(evidence_id,),
        )

        relation = self.service.register_relation(
            source=variable.as_reference(),
            target=sensor.as_reference(),
            relation_type=TechnicalRelationType.VARIABLE_PRODUCED_BY_SENSOR,
            evidence_ids=(evidence_id,),
            rationale="documented physical measurement",
            source_trace=self.trace,
            created_by="qa.engineer",
            created_at=self.created_at,
        )
        self.assertEqual(relation.target.entity_id, sensor.sensor_id)

    def test_derived_variable_cannot_have_sensor(self) -> None:
        evidence_id = self._evidence("derived")
        source_variable = self._register_primary_variable("flow_in", evidence_id)
        derived = self.service.register_variable(
            variable_id=self._id("flow_delta"),
            canonical_name="Flow Delta",
            family="flow",
            physical_quantity="flow",
            subsystem="mud system",
            process_context="circulation",
            criticality="medium",
            measurement_kind=MeasurementKind.DERIVED_VARIABLE,
            evidence_ids=(evidence_id,),
        )
        self.service.register_derived_variable(
            variable_id=derived.variable_id,
            derivation_type="difference",
            source_variable_ids=(source_variable.variable_id,),
            formula_original="flow_in - flow_out",
            formula_normalized="flow_in-flow_out",
            constants=(),
            input_units=(("flow_in", "gpm"),),
            output_unit="gpm",
            calculation_conditions="steady circulation",
            null_handling="propagate_null",
            filtering_or_averaging="none",
            calculating_equipment_or_software="PLC",
            evidence_ids=(evidence_id,),
        )

        sensor_ref = TechnicalEntityReference(self._id("sensor.delta"), TechnicalEntityType.SENSOR, "Synthetic Sensor")
        self.service.register_sensor(
            sensor_id=sensor_ref.entity_id,
            sensor_type="Virtual Sensor",
            measurement_principle=None,
            manufacturer="Known Vendor",
            model=None,
            physical_location_typical="control room",
            physical_location_specific=None,
            installation_context="software",
            accuracy=None,
            resolution=None,
            sampling_rate=None,
            operating_conditions=None,
            evidence_ids=(evidence_id,),
        )
        with self.assertRaises(ValueError):
            self.service.register_relation(
                source=derived.as_reference(),
                target=sensor_ref,
                relation_type=TechnicalRelationType.VARIABLE_PRODUCED_BY_SENSOR,
                evidence_ids=(evidence_id,),
                rationale="invalid sensor assignment",
                source_trace=self.trace,
                created_by="qa.engineer",
                created_at=self.created_at,
            )

    def test_signal_4_20_ma_with_engineering_scaling(self) -> None:
        evidence_id = self._evidence("signal")
        raw_signal = self.service.register_raw_signal(
            raw_signal_id=self._id("signal.standpipe_pressure"),
            raw_signal_type=RawSignalType.CURRENT,
            raw_min=4.0,
            raw_max=20.0,
            raw_unit="mA",
            protocol=None,
            channel="AI-01",
            scaling_formula="psi=(mA-4)*250",
            evidence_ids=(evidence_id,),
        )
        self.assertEqual(raw_signal.raw_min, 4.0)
        self.assertEqual(raw_signal.raw_max, 20.0)

    def test_nominal_range_and_configured_range_are_distinct(self) -> None:
        evidence_id = self._evidence("range")
        variable = self._register_primary_variable("standpipe_pressure", evidence_id)
        nominal = self.service.register_working_range(
            variable_id=variable.variable_id,
            range_kind=WorkingRangeKind.SENSOR_NOMINAL_RANGE,
            min_value=0.0,
            max_value=5000.0,
            unit="psi",
            status=EvidenceStatus.DOCUMENTED,
            evidence_ids=(evidence_id,),
        )
        configured = self.service.register_working_range(
            variable_id=variable.variable_id,
            range_kind=WorkingRangeKind.CONFIGURED_RANGE,
            min_value=0.0,
            max_value=3500.0,
            unit="psi",
            status=EvidenceStatus.DOCUMENTED,
            evidence_ids=(evidence_id,),
        )
        self.assertNotEqual(nominal.range_kind, configured.range_kind)

    def test_observed_range_is_separate_from_technical_range(self) -> None:
        evidence_id = self._evidence("observed")
        observed_evidence_id = self._evidence("observed_las", level=EvidenceLevel.OBSERVED_IN_LAS)
        variable = self._register_primary_variable("rpm", evidence_id)
        engineering = self.service.register_working_range(
            variable_id=variable.variable_id,
            range_kind=WorkingRangeKind.ENGINEERING_RANGE,
            min_value=0.0,
            max_value=220.0,
            unit="rpm",
            status=EvidenceStatus.DOCUMENTED,
            evidence_ids=(evidence_id,),
        )
        observed = self.service.register_working_range(
            variable_id=variable.variable_id,
            range_kind=WorkingRangeKind.OBSERVED_RANGE,
            min_value=60.0,
            max_value=180.0,
            unit="rpm",
            status=EvidenceStatus.DOCUMENTED,
            evidence_ids=(observed_evidence_id,),
        )
        self.assertNotEqual(engineering.range_kind, observed.range_kind)

    def test_evidence_idempotence_and_level_are_stable(self) -> None:
        evidence_id = self._id("evidence:stable")
        first = self.service.register_evidence(
            evidence_id=evidence_id,
            evidence_level=EvidenceLevel.CUSTOMER_SUPPLIED,
            status=EvidenceStatus.DOCUMENTED,
            source_document_id=self._id("doc"),
            source_version_id=self._id("ver"),
            fragment_id=self._id("fragment:stable"),
            original_text="stable evidence",
            rationale="stable rationale",
            confidence=0.8,
            created_at=self.created_at,
        )
        same = self.service.register_evidence(
            evidence_id=evidence_id,
            evidence_level=EvidenceLevel.CUSTOMER_SUPPLIED,
            status=EvidenceStatus.DOCUMENTED,
            source_document_id=self._id("doc"),
            source_version_id=self._id("ver"),
            fragment_id=self._id("fragment:stable"),
            original_text="stable evidence",
            rationale="stable rationale",
            confidence=0.8,
            created_at=self.created_at,
        )
        self.assertIs(first, same)
        self.assertEqual(len(self.service.repository.list_evidence_history(evidence_id)), 1)

        with self.assertRaises(ValueError):
            self.service.register_evidence(
                evidence_id=evidence_id,
                evidence_level=EvidenceLevel.INDUSTRY_STANDARD,
                status=EvidenceStatus.DOCUMENTED,
                source_document_id=self._id("doc"),
                source_version_id=self._id("ver"),
                fragment_id=self._id("fragment:stable"),
                original_text="stable evidence",
                rationale="stable rationale",
                confidence=0.8,
                created_at=self.created_at,
            )

    def test_raw_signal_type_constraints_are_enforced(self) -> None:
        evidence_id = self._evidence("raw_constraints")
        with self.assertRaises(ValueError):
            self.service.register_raw_signal(
                raw_signal_id=self._id("signal.partial"),
                raw_signal_type=RawSignalType.CURRENT,
                raw_min=4.0,
                raw_max=None,
                raw_unit="mA",
                protocol=None,
                channel="AI-02",
                scaling_formula="x",
                evidence_ids=(evidence_id,),
            )
        with self.assertRaises(ValueError):
            self.service.register_raw_signal(
                raw_signal_id=self._id("signal.digital"),
                raw_signal_type=RawSignalType.DIGITAL,
                raw_min=0.0,
                raw_max=1.0,
                raw_unit=None,
                protocol=None,
                channel="DI-01",
                scaling_formula=None,
                evidence_ids=(evidence_id,),
            )

    def test_engineering_range_requires_documented_unit_match(self) -> None:
        evidence_id = self._evidence("engineering_unit")
        variable = self._register_primary_variable("wob", evidence_id)
        unit_ref = TechnicalEntityReference(self._id("unit.klbf"), TechnicalEntityType.UNIT, "klbf")
        self.service.register_relation(
            source=variable.as_reference(),
            target=unit_ref,
            relation_type=TechnicalRelationType.VARIABLE_USES_UNIT,
            evidence_ids=(evidence_id,),
            rationale="documented unit",
            source_trace=self.trace,
            created_by="qa.engineer",
            created_at=self.created_at,
        )
        with self.assertRaises(ValueError):
            self.service.register_working_range(
                variable_id=variable.variable_id,
                range_kind=WorkingRangeKind.ENGINEERING_RANGE,
                min_value=0.0,
                max_value=40.0,
                unit="psi",
                status=EvidenceStatus.DOCUMENTED,
                evidence_ids=(evidence_id,),
            )

    def test_formula_consistency_and_output_unit_are_enforced(self) -> None:
        evidence_id = self._evidence("formula_rules")
        source = self._register_primary_variable("pump_rate", evidence_id)
        derived = self.service.register_variable(
            variable_id=self._id("pump_rate_avg"),
            canonical_name="Pump Rate Average",
            family="flow",
            physical_quantity="flow",
            subsystem="pumps",
            process_context="analytics",
            criticality="low",
            measurement_kind=MeasurementKind.DERIVED_VARIABLE,
            evidence_ids=(evidence_id,),
        )
        unit_ref = TechnicalEntityReference(self._id("unit.gpm"), TechnicalEntityType.UNIT, "gpm")
        self.service.register_relation(
            source=derived.as_reference(),
            target=unit_ref,
            relation_type=TechnicalRelationType.VARIABLE_USES_UNIT,
            evidence_ids=(evidence_id,),
            rationale="documented output unit",
            source_trace=self.trace,
            created_by="qa.engineer",
            created_at=self.created_at,
        )

        with self.assertRaises(ValueError):
            self.service.register_derived_variable(
                variable_id=derived.variable_id,
                derivation_type="average",
                source_variable_ids=(source.variable_id,),
                formula_original="avg( pump_rate )",
                formula_normalized="sum(pump_rate)",
                constants=(),
                input_units=(("pump_rate", "gpm"),),
                output_unit="gpm",
                calculation_conditions=None,
                null_handling=None,
                filtering_or_averaging=None,
                calculating_equipment_or_software=None,
                evidence_ids=(evidence_id,),
            )

        with self.assertRaises(ValueError):
            self.service.register_derived_variable(
                variable_id=derived.variable_id,
                derivation_type="average",
                source_variable_ids=(source.variable_id,),
                formula_original="avg(pump_rate)",
                formula_normalized="avg(pump_rate)",
                constants=(),
                input_units=(("pump_rate", "gpm"),),
                output_unit="bbl/min",
                calculation_conditions=None,
                null_handling=None,
                filtering_or_averaging=None,
                calculating_equipment_or_software=None,
                evidence_ids=(evidence_id,),
            )

    def test_signal_chain_requires_documented_intermediate_relations(self) -> None:
        evidence_id = self._evidence("signal_chain")
        variable = self._register_primary_variable("exported_wob", evidence_id)
        channel_ref = TechnicalEntityReference(self._id("channel.ai03"), TechnicalEntityType.CHANNEL, "AI-03")
        tag_ref = TechnicalEntityReference(self._id("tag.wob"), TechnicalEntityType.TAG, "WOB")
        sensor = self.service.register_sensor(
            sensor_id=self._id("sensor.wob"),
            sensor_type="Hook Sensor",
            measurement_principle="strain",
            manufacturer=None,
            model=None,
            physical_location_typical=None,
            physical_location_specific=None,
            installation_context=None,
            accuracy=None,
            resolution=None,
            sampling_rate=None,
            operating_conditions=None,
            evidence_ids=(evidence_id,),
        )

        with self.assertRaises(ValueError):
            self.service.register_relation(
                source=tag_ref,
                target=variable.as_reference(),
                relation_type=TechnicalRelationType.TAG_EXPORTED_AS_VARIABLE,
                evidence_ids=(evidence_id,),
                rationale="missing channel relation",
                source_trace=self.trace,
                created_by="qa.engineer",
                created_at=self.created_at,
            )

        self.service.register_relation(
            source=sensor.as_reference(),
            target=channel_ref,
            relation_type=TechnicalRelationType.SENSOR_CONNECTED_TO_CHANNEL,
            evidence_ids=(evidence_id,),
            rationale="sensor wiring",
            source_trace=self.trace,
            created_by="qa.engineer",
            created_at=self.created_at,
        )
        self.service.register_relation(
            source=channel_ref,
            target=tag_ref,
            relation_type=TechnicalRelationType.CHANNEL_EXPOSED_AS_TAG,
            evidence_ids=(evidence_id,),
            rationale="channel mapping",
            source_trace=self.trace,
            created_by="qa.engineer",
            created_at=self.created_at,
        )
        relation = self.service.register_relation(
            source=tag_ref,
            target=variable.as_reference(),
            relation_type=TechnicalRelationType.TAG_EXPORTED_AS_VARIABLE,
            evidence_ids=(evidence_id,),
            rationale="export mapping",
            source_trace=self.trace,
            created_by="qa.engineer",
            created_at=self.created_at,
        )
        self.assertEqual(relation.source.entity_id, tag_ref.entity_id)

    def test_typical_location_is_distinct_from_specific_location(self) -> None:
        evidence_id = self._evidence("location")
        sensor = self.service.register_sensor(
            sensor_id=self._id("sensor.pit"),
            sensor_type="Pit Level Sensor",
            measurement_principle="ultrasonic",
            manufacturer="Acme",
            model="",
            physical_location_typical="mud pit",
            physical_location_specific="active pit 1",
            installation_context="fluid monitoring",
            accuracy=None,
            resolution=None,
            sampling_rate=None,
            operating_conditions=None,
            evidence_ids=(evidence_id,),
        )
        self.assertNotEqual(sensor.physical_location_typical, sensor.physical_location_specific)

    def test_manufacturer_known_model_unknown(self) -> None:
        evidence_id = self._evidence("manufacturer")
        sensor = self.service.register_sensor(
            sensor_id=self._id("sensor.unknown_model"),
            sensor_type="Pressure Sensor",
            measurement_principle="piezoelectric",
            manufacturer="Known Vendor",
            model=None,
            physical_location_typical="standpipe manifold",
            physical_location_specific=None,
            installation_context="pressure monitoring",
            accuracy=None,
            resolution=None,
            sampling_rate=None,
            operating_conditions=None,
            evidence_ids=(evidence_id,),
        )
        self.assertEqual(sensor.manufacturer, "Known Vendor")
        self.assertIsNone(sensor.model)

    def test_documented_derived_formula(self) -> None:
        evidence_id = self._evidence("formula_doc")
        source = self._register_primary_variable("rop", evidence_id)
        derived = self.service.register_variable(
            variable_id=self._id("rop_avg"),
            canonical_name="ROP Average",
            family="rate",
            physical_quantity="velocity",
            subsystem="drilling",
            process_context="performance",
            criticality="medium",
            measurement_kind=MeasurementKind.DERIVED_VARIABLE,
            evidence_ids=(evidence_id,),
        )
        definition = self.service.register_derived_variable(
            variable_id=derived.variable_id,
            derivation_type="moving_average",
            source_variable_ids=(source.variable_id,),
            formula_original="avg(rop,5m)",
            formula_normalized="avg(rop,5m)",
            constants=(("window", "5m"),),
            input_units=(("rop", "ft/h"),),
            output_unit="ft/h",
            calculation_conditions="sliding window",
            null_handling="skip_nulls",
            filtering_or_averaging="moving_average",
            calculating_equipment_or_software="Historian",
            evidence_ids=(evidence_id,),
        )
        self.assertEqual(definition.formula_original, "avg(rop,5m)")

    def test_formula_not_found_and_missing_source_variables(self) -> None:
        missing_formula_evidence = self._evidence("formula_missing", status=EvidenceStatus.NOT_FOUND)
        derived = self.service.register_variable(
            variable_id=self._id("hookload_norm"),
            canonical_name="Hookload Normalized",
            family="load",
            physical_quantity="force",
            subsystem="hoisting",
            process_context="analytics",
            criticality="low",
            measurement_kind=MeasurementKind.DERIVED_VARIABLE,
            evidence_ids=(missing_formula_evidence,),
        )
        with self.assertRaises(ValueError):
            self.service.register_derived_variable(
                variable_id=derived.variable_id,
                derivation_type="normalized",
                source_variable_ids=(self._id("missing_source"),),
                formula_original=None,
                formula_normalized=None,
                constants=(),
                input_units=(),
                output_unit=None,
                calculation_conditions=None,
                null_handling=None,
                filtering_or_averaging=None,
                calculating_equipment_or_software=None,
                evidence_ids=(missing_formula_evidence,),
            )

    def test_conflicting_sources_and_requires_states_are_preserved(self) -> None:
        conflicting = self._evidence("conflict", status=EvidenceStatus.CONFLICTING_SOURCES)
        requires_model = self._evidence("requires_model", status=EvidenceStatus.REQUIRES_EQUIPMENT_MODEL)
        requires_config = self._evidence("requires_config", status=EvidenceStatus.REQUIRES_CONFIGURATION)
        self.assertEqual(self.service.repository.get_latest_evidence(conflicting).status, EvidenceStatus.CONFLICTING_SOURCES)
        self.assertEqual(self.service.repository.get_latest_evidence(requires_model).status, EvidenceStatus.REQUIRES_EQUIPMENT_MODEL)
        self.assertEqual(self.service.repository.get_latest_evidence(requires_config).status, EvidenceStatus.REQUIRES_CONFIGURATION)

    def test_history_idempotence_order_duplicates_and_no_mutation(self) -> None:
        evidence_id = self._evidence("history")
        variable_id = self._id("mud_density")
        first = self.service.register_variable(
            variable_id=variable_id,
            canonical_name="Mud Density",
            family="fluid",
            physical_quantity="density",
            subsystem="mud system",
            process_context="circulation",
            criticality="high",
            measurement_kind=MeasurementKind.PRIMARY_MEASUREMENT,
            evidence_ids=(evidence_id,),
        )
        same = self.service.register_variable(
            variable_id=variable_id,
            canonical_name="Mud Density",
            family="fluid",
            physical_quantity="density",
            subsystem="mud system",
            process_context="circulation",
            criticality="high",
            measurement_kind=MeasurementKind.PRIMARY_MEASUREMENT,
            evidence_ids=(evidence_id,),
        )
        second = self.service.register_variable(
            variable_id=variable_id,
            canonical_name="Mud Density",
            family="fluid",
            physical_quantity="density",
            subsystem="mud system",
            process_context="circulation",
            criticality="medium",
            measurement_kind=MeasurementKind.PRIMARY_MEASUREMENT,
            evidence_ids=(evidence_id,),
        )
        snapshot = (variable_id, evidence_id, self.trace, self.created_at)

        self.assertIs(first, same)
        self.assertEqual([item.revision for item in self.service.list_variable_history(variable_id)], [1, 2])
        self.assertEqual(tuple(sorted(self.service.repository.list_all_variables(), key=lambda item: (str(item.variable_id), item.revision))), self.service.repository.list_all_variables())
        self.assertEqual(snapshot, (variable_id, evidence_id, self.trace, self.created_at))
        self.assertNotEqual(first.criticality, second.criticality)

    def test_no_automatic_inference_is_applied(self) -> None:
        evidence_id = self._evidence("no_inference")
        source = self._register_primary_variable("torque", evidence_id)
        derived = self.service.register_variable(
            variable_id=self._id("torque_avg"),
            canonical_name="Torque Average",
            family="torque",
            physical_quantity="torque",
            subsystem="rotary",
            process_context="analytics",
            criticality="low",
            measurement_kind=MeasurementKind.DERIVED_VARIABLE,
            evidence_ids=(evidence_id,),
        )
        self.service.register_derived_variable(
            variable_id=derived.variable_id,
            derivation_type="moving_average",
            source_variable_ids=(source.variable_id,),
            formula_original="avg(torque,1m)",
            formula_normalized="avg(torque,1m)",
            constants=(),
            input_units=(("torque", "klbf.ft"),),
            output_unit="klbf.ft",
            calculation_conditions=None,
            null_handling=None,
            filtering_or_averaging="moving_average",
            calculating_equipment_or_software="Historian",
            evidence_ids=(evidence_id,),
        )
        self.assertEqual(self.service.list_all_relations(), ())

    def _register_primary_variable(self, seed: str, evidence_id: EntityId):
        return self.service.register_variable(
            variable_id=self._id(seed),
            canonical_name=seed.replace("_", " ").title(),
            family="generic",
            physical_quantity="generic",
            subsystem="generic",
            process_context="generic",
            criticality="medium",
            measurement_kind=MeasurementKind.PRIMARY_MEASUREMENT,
            evidence_ids=(evidence_id,),
        )

    def _evidence(
        self,
        seed: str,
        *,
        status: EvidenceStatus = EvidenceStatus.DOCUMENTED,
        level: EvidenceLevel = EvidenceLevel.CUSTOMER_SUPPLIED,
    ) -> EntityId:
        evidence_id = self._id(f"evidence:{seed}")
        self.service.register_evidence(
            evidence_id=evidence_id,
            evidence_level=level,
            status=status,
            source_document_id=self._id("doc"),
            source_version_id=self._id("ver"),
            fragment_id=self._id(f"fragment:{seed}"),
            original_text=f"evidence for {seed}",
            rationale=f"rationale for {seed}",
            confidence=0.9,
            created_at=self.created_at,
        )
        return evidence_id

    def _id(self, seed: str) -> EntityId:
        return EntityId.from_seed("technical_knowledge.test", seed)