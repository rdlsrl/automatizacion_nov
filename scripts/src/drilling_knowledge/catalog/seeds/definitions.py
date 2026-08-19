"""Conservative seed definitions for the catalog core and initial IDKB backbone."""

from __future__ import annotations

from dataclasses import dataclass

from drilling_knowledge.catalog.domain import (
    CatalogCode,
    CatalogScope,
    EngineeringUnit,
    EquipmentClass,
    InstrumentClass,
    LocationClass,
    LocalizedName,
    MeasurementPrinciple,
    OperationalContextClass,
    OriginClass,
    PhysicalQuantity,
    ProcessClass,
    PublisherClass,
    QuantityUnitCompatibility,
    SensorClass,
    SubsystemClass,
    SystemClass,
    VariableClassification,
)
from drilling_knowledge.common.ids import EntityId
from drilling_knowledge.idkb.domain import (
    ArticleTemplate,
    CanonicalIdentifierDefinition,
    KnowledgeDomain,
    KnowledgePackManifest,
    MaturityLevel,
)


def _entity_id(kind: str, code: str) -> EntityId:
    return EntityId.from_seed("drilling_knowledge.seed", f"{kind}:{code}")


@dataclass(frozen=True, slots=True)
class CatalogSeedBundle:
    units: tuple[EngineeringUnit, ...] = ()
    quantities: tuple[PhysicalQuantity, ...] = ()
    quantity_unit_compatibilities: tuple[QuantityUnitCompatibility, ...] = ()
    principles: tuple[MeasurementPrinciple, ...] = ()
    classifications: tuple[VariableClassification, ...] = ()
    origins: tuple[OriginClass, ...] = ()
    publishers: tuple[PublisherClass, ...] = ()
    systems: tuple[SystemClass, ...] = ()
    subsystems: tuple[SubsystemClass, ...] = ()
    processes: tuple[ProcessClass, ...] = ()
    operational_contexts: tuple[OperationalContextClass, ...] = ()
    locations: tuple[LocationClass, ...] = ()
    sensors: tuple[SensorClass, ...] = ()
    instruments: tuple[InstrumentClass, ...] = ()
    equipment: tuple[EquipmentClass, ...] = ()


@dataclass(frozen=True, slots=True)
class IdkbSeedBundle:
    domains: tuple[KnowledgeDomain, ...] = ()
    identifier_definitions: tuple[CanonicalIdentifierDefinition, ...] = ()
    article_templates: tuple[ArticleTemplate, ...] = ()
    maturity_levels: tuple[MaturityLevel, ...] = ()
    knowledge_packs: tuple[KnowledgePackManifest, ...] = ()


def default_catalog_seed_bundle() -> CatalogSeedBundle:
    global_scope = CatalogScope()
    units = (
        EngineeringUnit(_entity_id("unit", "psi"), CatalogCode("psi"), LocalizedName("PSI"), "Pressure unit pounds per square inch.", global_scope, symbol="psi", dimension_code="pressure"),
        EngineeringUnit(_entity_id("unit", "kpa"), CatalogCode("kpa"), LocalizedName("kPa"), "Pressure unit kilopascal.", global_scope, symbol="kPa", dimension_code="pressure"),
        EngineeringUnit(_entity_id("unit", "gpm"), CatalogCode("gpm"), LocalizedName("GPM"), "Flow rate unit gallons per minute.", global_scope, symbol="gpm", dimension_code="flow_rate"),
        EngineeringUnit(_entity_id("unit", "lpm"), CatalogCode("lpm"), LocalizedName("LPM"), "Flow rate unit liters per minute.", global_scope, symbol="lpm", dimension_code="flow_rate"),
        EngineeringUnit(_entity_id("unit", "rpm"), CatalogCode("rpm"), LocalizedName("RPM"), "Rotational speed unit revolutions per minute.", global_scope, symbol="rpm", dimension_code="rotational_speed"),
        EngineeringUnit(_entity_id("unit", "ft"), CatalogCode("ft"), LocalizedName("Foot"), "Length unit foot.", global_scope, symbol="ft", dimension_code="length"),
        EngineeringUnit(_entity_id("unit", "m"), CatalogCode("m"), LocalizedName("Meter"), "Length unit meter.", global_scope, symbol="m", dimension_code="length"),
        EngineeringUnit(_entity_id("unit", "klbf"), CatalogCode("klbf"), LocalizedName("kLbf"), "Force unit thousand pounds-force.", global_scope, symbol="klbf", dimension_code="force"),
        EngineeringUnit(_entity_id("unit", "degc"), CatalogCode("degc"), LocalizedName("DegC"), "Temperature unit degrees Celsius.", global_scope, symbol="degC", dimension_code="temperature"),
        EngineeringUnit(_entity_id("unit", "pct"), CatalogCode("pct"), LocalizedName("Percent"), "Dimensionless percentage unit.", global_scope, symbol="%", dimension_code="dimensionless"),
    )
    quantities = (
        PhysicalQuantity(_entity_id("quantity", "pressure"), CatalogCode("pressure"), LocalizedName("Pressure"), "Pressure magnitude.", global_scope, quantity_family="hydraulic", dimension_code="pressure", canonical_unit_code=CatalogCode("psi")),
        PhysicalQuantity(_entity_id("quantity", "flow_rate"), CatalogCode("flow_rate"), LocalizedName("Flow Rate"), "Volumetric flow rate magnitude.", global_scope, quantity_family="hydraulic", dimension_code="flow_rate", canonical_unit_code=CatalogCode("gpm")),
        PhysicalQuantity(_entity_id("quantity", "rotational_speed"), CatalogCode("rotational_speed"), LocalizedName("Rotational Speed"), "Angular speed magnitude.", global_scope, quantity_family="mechanical", dimension_code="rotational_speed", canonical_unit_code=CatalogCode("rpm")),
        PhysicalQuantity(_entity_id("quantity", "length"), CatalogCode("length"), LocalizedName("Length"), "Linear distance magnitude.", global_scope, quantity_family="geometry", dimension_code="length", canonical_unit_code=CatalogCode("ft")),
        PhysicalQuantity(_entity_id("quantity", "force"), CatalogCode("force"), LocalizedName("Force"), "Force magnitude.", global_scope, quantity_family="mechanical", dimension_code="force", canonical_unit_code=CatalogCode("klbf")),
        PhysicalQuantity(_entity_id("quantity", "temperature"), CatalogCode("temperature"), LocalizedName("Temperature"), "Temperature magnitude.", global_scope, quantity_family="thermal", dimension_code="temperature", canonical_unit_code=CatalogCode("degc")),
        PhysicalQuantity(_entity_id("quantity", "dimensionless"), CatalogCode("dimensionless"), LocalizedName("Dimensionless"), "Dimensionless ratio or percentage.", global_scope, quantity_family="generic", dimension_code="dimensionless", canonical_unit_code=CatalogCode("pct")),
    )
    quantity_unit_compatibilities = tuple(
        QuantityUnitCompatibility(
            entity_id=_entity_id("quantity_unit", f"{quantity_code}.{unit_code}"),
            code=CatalogCode(f"{quantity_code}.{unit_code}"),
            names=LocalizedName(canonical=f"{quantity_code} to {unit_code}"),
            description=f"Allowed unit '{unit_code}' for quantity '{quantity_code}'.",
            scope=global_scope,
            quantity_code=CatalogCode(quantity_code),
            unit_code=CatalogCode(unit_code),
        )
        for quantity_code, unit_code in (
            ("pressure", "psi"),
            ("pressure", "kpa"),
            ("flow_rate", "gpm"),
            ("flow_rate", "lpm"),
            ("rotational_speed", "rpm"),
            ("length", "ft"),
            ("length", "m"),
            ("force", "klbf"),
            ("temperature", "degc"),
            ("dimensionless", "pct"),
        )
    )
    principles = (
        MeasurementPrinciple(_entity_id("principle", "direct_pressure_sensor"), CatalogCode("direct_pressure_sensor"), LocalizedName("Direct Pressure Sensor"), "Direct pressure sensing principle.", global_scope, principle_family="pressure", directness_class="direct"),
        MeasurementPrinciple(_entity_id("principle", "differential_pressure"), CatalogCode("differential_pressure"), LocalizedName("Differential Pressure"), "Differential pressure measurement principle.", global_scope, principle_family="pressure", directness_class="direct"),
        MeasurementPrinciple(_entity_id("principle", "turbine_flow"), CatalogCode("turbine_flow"), LocalizedName("Turbine Flow"), "Turbine-based flow measurement principle.", global_scope, principle_family="flow", directness_class="direct"),
        MeasurementPrinciple(_entity_id("principle", "rotary_encoder"), CatalogCode("rotary_encoder"), LocalizedName("Rotary Encoder"), "Encoder-based rotational measurement principle.", global_scope, principle_family="rotation", directness_class="direct"),
        MeasurementPrinciple(_entity_id("principle", "load_cell"), CatalogCode("load_cell"), LocalizedName("Load Cell"), "Load-cell force measurement principle.", global_scope, principle_family="force", directness_class="direct"),
    )
    classifications = (
        VariableClassification(_entity_id("classification", "primary"), CatalogCode("primary"), LocalizedName("Primary"), "Primary operational variable.", global_scope, axis="operational_role"),
        VariableClassification(_entity_id("classification", "derived"), CatalogCode("derived"), LocalizedName("Derived"), "Derived operational variable.", global_scope, axis="operational_role"),
        VariableClassification(_entity_id("classification", "state"), CatalogCode("state"), LocalizedName("State"), "State or mode variable.", global_scope, axis="operational_role"),
        VariableClassification(_entity_id("classification", "diagnostic"), CatalogCode("diagnostic"), LocalizedName("Diagnostic"), "Diagnostic or quality variable.", global_scope, axis="operational_role"),
    )
    origins = (
        OriginClass(_entity_id("origin", "direct_sensor"), CatalogCode("direct_sensor"), LocalizedName("Direct Sensor"), "Originated directly from a sensing element.", global_scope, axis="source_kind"),
        OriginClass(_entity_id("origin", "calculated"), CatalogCode("calculated"), LocalizedName("Calculated"), "Computed from one or more source signals.", global_scope, axis="source_kind"),
        OriginClass(_entity_id("origin", "manual_entry"), CatalogCode("manual_entry"), LocalizedName("Manual Entry"), "Recorded manually by an operator or analyst.", global_scope, axis="source_kind"),
        OriginClass(_entity_id("origin", "imported"), CatalogCode("imported"), LocalizedName("Imported"), "Imported from an external system or historical source.", global_scope, axis="source_kind"),
    )
    publishers = (
        PublisherClass(_entity_id("publisher", "sensor_publisher"), CatalogCode("sensor_publisher"), LocalizedName("Sensor Publisher"), "Direct device-level publisher class.", global_scope),
        PublisherClass(_entity_id("publisher", "plc_publisher"), CatalogCode("plc_publisher"), LocalizedName("PLC Publisher"), "PLC-originated publisher class.", global_scope),
        PublisherClass(_entity_id("publisher", "scada_publisher"), CatalogCode("scada_publisher"), LocalizedName("SCADA Publisher"), "SCADA-originated publisher class.", global_scope),
        PublisherClass(_entity_id("publisher", "edr_publisher"), CatalogCode("edr_publisher"), LocalizedName("EDR Publisher"), "EDR-originated publisher class.", global_scope),
    )
    systems = (
        SystemClass(_entity_id("system", "hoisting"), CatalogCode("hoisting"), LocalizedName("Hoisting"), "Rig hoisting system.", global_scope),
        SystemClass(_entity_id("system", "rotary"), CatalogCode("rotary"), LocalizedName("Rotary"), "Rig rotary system.", global_scope),
        SystemClass(_entity_id("system", "circulation"), CatalogCode("circulation"), LocalizedName("Circulation"), "Rig circulation system.", global_scope),
        SystemClass(_entity_id("system", "well_control"), CatalogCode("well_control"), LocalizedName("Well Control"), "Well control system.", global_scope),
        SystemClass(_entity_id("system", "data_acquisition"), CatalogCode("data_acquisition"), LocalizedName("Data Acquisition"), "Rig data acquisition system.", global_scope),
    )
    subsystems = (
        SubsystemClass(_entity_id("subsystem", "drawworks"), CatalogCode("drawworks"), LocalizedName("Drawworks"), "Hoisting drawworks subsystem.", global_scope, system_code=CatalogCode("hoisting")),
        SubsystemClass(_entity_id("subsystem", "top_drive"), CatalogCode("top_drive"), LocalizedName("Top Drive"), "Rotary top drive subsystem.", global_scope, system_code=CatalogCode("rotary")),
        SubsystemClass(_entity_id("subsystem", "standpipe_system"), CatalogCode("standpipe_system"), LocalizedName("Standpipe System"), "Standpipe circulation subsystem.", global_scope, system_code=CatalogCode("circulation")),
        SubsystemClass(_entity_id("subsystem", "mud_pumps"), CatalogCode("mud_pumps"), LocalizedName("Mud Pumps"), "Mud pump subsystem.", global_scope, system_code=CatalogCode("circulation")),
        SubsystemClass(_entity_id("subsystem", "bop_stack"), CatalogCode("bop_stack"), LocalizedName("BOP Stack"), "Pressure control BOP subsystem.", global_scope, system_code=CatalogCode("well_control")),
        SubsystemClass(_entity_id("subsystem", "rig_edr"), CatalogCode("rig_edr"), LocalizedName("Rig EDR"), "Electronic drilling recorder subsystem.", global_scope, system_code=CatalogCode("data_acquisition")),
    )
    processes = (
        ProcessClass(_entity_id("process", "drilling"), CatalogCode("drilling"), LocalizedName("Drilling"), "Primary drilling process.", global_scope),
        ProcessClass(_entity_id("process", "tripping"), CatalogCode("tripping"), LocalizedName("Tripping"), "Pipe tripping process.", global_scope),
        ProcessClass(_entity_id("process", "circulation_process"), CatalogCode("circulation_process"), LocalizedName("Circulation"), "Fluid circulation process.", global_scope),
        ProcessClass(_entity_id("process", "well_control_process"), CatalogCode("well_control_process"), LocalizedName("Well Control"), "Pressure control process.", global_scope),
        ProcessClass(_entity_id("process", "data_capture"), CatalogCode("data_capture"), LocalizedName("Data Capture"), "Operational data capture process.", global_scope),
    )
    operational_contexts = (
        OperationalContextClass(_entity_id("operational_context", "normal_drilling"), CatalogCode("normal_drilling"), LocalizedName("Normal Drilling"), "Nominal drilling operational context.", global_scope),
        OperationalContextClass(_entity_id("operational_context", "connection"), CatalogCode("connection"), LocalizedName("Connection"), "Pipe connection operational context.", global_scope),
        OperationalContextClass(_entity_id("operational_context", "trip_in"), CatalogCode("trip_in"), LocalizedName("Trip In"), "Trip in operational context.", global_scope),
        OperationalContextClass(_entity_id("operational_context", "trip_out"), CatalogCode("trip_out"), LocalizedName("Trip Out"), "Trip out operational context.", global_scope),
        OperationalContextClass(_entity_id("operational_context", "well_control_event"), CatalogCode("well_control_event"), LocalizedName("Well Control Event"), "Well control event context.", global_scope),
    )
    locations = (
        LocationClass(_entity_id("location", "surface"), CatalogCode("surface"), LocalizedName("Surface"), "Surface location class.", global_scope),
        LocationClass(_entity_id("location", "rig_floor"), CatalogCode("rig_floor"), LocalizedName("Rig Floor"), "Rig floor location class.", global_scope, parent_code=CatalogCode("surface")),
        LocationClass(_entity_id("location", "standpipe_manifold"), CatalogCode("standpipe_manifold"), LocalizedName("Standpipe Manifold"), "Standpipe manifold location class.", global_scope, parent_code=CatalogCode("surface")),
        LocationClass(_entity_id("location", "mud_pit"), CatalogCode("mud_pit"), LocalizedName("Mud Pit"), "Mud pit location class.", global_scope, parent_code=CatalogCode("surface")),
        LocationClass(_entity_id("location", "downhole"), CatalogCode("downhole"), LocalizedName("Downhole"), "Downhole location class.", global_scope),
    )
    sensors = (
        SensorClass(_entity_id("sensor", "pressure_sensor"), CatalogCode("pressure_sensor"), LocalizedName("Pressure Sensor"), "Minimal pressure sensor class.", global_scope),
        SensorClass(_entity_id("sensor", "flow_sensor"), CatalogCode("flow_sensor"), LocalizedName("Flow Sensor"), "Minimal flow sensor class.", global_scope),
        SensorClass(_entity_id("sensor", "rotary_speed_sensor"), CatalogCode("rotary_speed_sensor"), LocalizedName("Rotary Speed Sensor"), "Minimal rotational speed sensor class.", global_scope),
        SensorClass(_entity_id("sensor", "load_sensor"), CatalogCode("load_sensor"), LocalizedName("Load Sensor"), "Minimal load sensor class.", global_scope),
        SensorClass(_entity_id("sensor", "temperature_sensor"), CatalogCode("temperature_sensor"), LocalizedName("Temperature Sensor"), "Minimal temperature sensor class.", global_scope),
    )
    instruments = (
        InstrumentClass(_entity_id("instrument", "pressure_transmitter"), CatalogCode("pressure_transmitter"), LocalizedName("Pressure Transmitter"), "Minimal pressure transmitter class.", global_scope),
        InstrumentClass(_entity_id("instrument", "flow_meter"), CatalogCode("flow_meter"), LocalizedName("Flow Meter"), "Minimal flow meter class.", global_scope),
        InstrumentClass(_entity_id("instrument", "rotary_encoder_instrument"), CatalogCode("rotary_encoder_instrument"), LocalizedName("Rotary Encoder Instrument"), "Minimal encoder instrument class.", global_scope),
        InstrumentClass(_entity_id("instrument", "load_indicator"), CatalogCode("load_indicator"), LocalizedName("Load Indicator"), "Minimal load indicator class.", global_scope),
        InstrumentClass(_entity_id("instrument", "temperature_transmitter"), CatalogCode("temperature_transmitter"), LocalizedName("Temperature Transmitter"), "Minimal temperature transmitter class.", global_scope),
    )
    equipment = (
        EquipmentClass(_entity_id("equipment", "mud_pump"), CatalogCode("mud_pump"), LocalizedName("Mud Pump"), "Minimal mud pump equipment class.", global_scope),
        EquipmentClass(_entity_id("equipment", "top_drive_equipment"), CatalogCode("top_drive_equipment"), LocalizedName("Top Drive"), "Minimal top drive equipment class.", global_scope),
        EquipmentClass(_entity_id("equipment", "drawworks_equipment"), CatalogCode("drawworks_equipment"), LocalizedName("Drawworks"), "Minimal drawworks equipment class.", global_scope),
        EquipmentClass(_entity_id("equipment", "standpipe_manifold_equipment"), CatalogCode("standpipe_manifold_equipment"), LocalizedName("Standpipe Manifold"), "Minimal standpipe manifold equipment class.", global_scope),
        EquipmentClass(_entity_id("equipment", "blowout_preventer"), CatalogCode("blowout_preventer"), LocalizedName("Blowout Preventer"), "Minimal blowout preventer equipment class.", global_scope),
    )
    return CatalogSeedBundle(
        units=units,
        quantities=quantities,
        quantity_unit_compatibilities=quantity_unit_compatibilities,
        principles=principles,
        classifications=classifications,
        origins=origins,
        publishers=publishers,
        systems=systems,
        subsystems=subsystems,
        processes=processes,
        operational_contexts=operational_contexts,
        locations=locations,
        sensors=sensors,
        instruments=instruments,
        equipment=equipment,
    )


def default_idkb_seed_bundle() -> IdkbSeedBundle:
    global_scope = CatalogScope()
    domains = (
        KnowledgeDomain(_entity_id("idkb_domain", "rig_and_system_foundations"), CatalogCode("rig_and_system_foundations"), LocalizedName("Rig And System Foundations"), "Top-level rig and system foundations domain.", global_scope, volume_code="volume_a"),
        KnowledgeDomain(_entity_id("idkb_domain", "mechanical_and_hydraulic_systems"), CatalogCode("mechanical_and_hydraulic_systems"), LocalizedName("Mechanical And Hydraulic Systems"), "Top-level mechanical and hydraulic systems domain.", global_scope, volume_code="volume_b"),
        KnowledgeDomain(_entity_id("idkb_domain", "control_instrumentation_and_data_systems"), CatalogCode("control_instrumentation_and_data_systems"), LocalizedName("Control Instrumentation And Data Systems"), "Top-level control and data systems domain.", global_scope, volume_code="volume_c"),
        KnowledgeDomain(_entity_id("idkb_domain", "directional_and_downhole_domains"), CatalogCode("directional_and_downhole_domains"), LocalizedName("Directional And Downhole Domains"), "Top-level directional and downhole domain.", global_scope, volume_code="volume_d"),
        KnowledgeDomain(_entity_id("idkb_domain", "pressure_control_well_integrity_and_completion_domains"), CatalogCode("pressure_control_well_integrity_and_completion_domains"), LocalizedName("Pressure Control Well Integrity And Completion Domains"), "Top-level well integrity and completion domain.", global_scope, volume_code="volume_e"),
        KnowledgeDomain(_entity_id("idkb_domain", "operational_knowledge_and_expert_interpretation"), CatalogCode("operational_knowledge_and_expert_interpretation"), LocalizedName("Operational Knowledge And Expert Interpretation"), "Top-level operational knowledge domain.", global_scope, volume_code="volume_f"),
    )
    identifier_definitions = (
        CanonicalIdentifierDefinition(_entity_id("idkb_identifier", "domain_article"), CatalogCode("domain_article"), LocalizedName("Domain Article Identifier"), "Canonical identifier pattern for domain articles.", global_scope, namespace="domain", target_kind="domain_article", pattern="idkb.domain.{code}"),
        CanonicalIdentifierDefinition(_entity_id("idkb_identifier", "variable_family_article"), CatalogCode("variable_family_article"), LocalizedName("Variable Family Identifier"), "Canonical identifier pattern for variable family articles.", global_scope, namespace="variable", target_kind="variable_family_article", pattern="idkb.variable.{code}"),
        CanonicalIdentifierDefinition(_entity_id("idkb_identifier", "sensor_family_article"), CatalogCode("sensor_family_article"), LocalizedName("Sensor Family Identifier"), "Canonical identifier pattern for sensor family articles.", global_scope, namespace="sensor", target_kind="sensor_family_article", pattern="idkb.sensor.{code}"),
        CanonicalIdentifierDefinition(_entity_id("idkb_identifier", "equipment_family_article"), CatalogCode("equipment_family_article"), LocalizedName("Equipment Family Identifier"), "Canonical identifier pattern for equipment family articles.", global_scope, namespace="equipment", target_kind="equipment_family_article", pattern="idkb.equipment.{code}"),
    )
    article_templates = (
        ArticleTemplate(_entity_id("idkb_template", "domain_article"), CatalogCode("domain_article"), LocalizedName("Domain Article"), "Template for domain articles.", global_scope, target_kind="domain_article", required_sections=("purpose", "scope", "systems", "subsystems", "variables", "measurement_chains")),
        ArticleTemplate(_entity_id("idkb_template", "variable_family_article"), CatalogCode("variable_family_article"), LocalizedName("Variable Family Article"), "Template for variable family articles.", global_scope, target_kind="variable_family_article", required_sections=("identity", "operational_purpose", "quantities", "units", "contexts", "publishers")),
        ArticleTemplate(_entity_id("idkb_template", "sensor_family_article"), CatalogCode("sensor_family_article"), LocalizedName("Sensor Family Article"), "Template for sensor family articles.", global_scope, target_kind="sensor_family_article", required_sections=("identity", "measurement_principle", "capabilities", "limitations", "failure_modes")),
        ArticleTemplate(_entity_id("idkb_template", "equipment_family_article"), CatalogCode("equipment_family_article"), LocalizedName("Equipment Family Article"), "Template for equipment family articles.", global_scope, target_kind="equipment_family_article", required_sections=("identity", "operational_role", "interfaces", "publishers", "contexts")),
    )
    maturity_levels = (
        MaturityLevel(_entity_id("idkb_maturity", "m0"), CatalogCode("m0"), LocalizedName("M0 Skeleton"), "Article exists with scope defined but no deep knowledge yet.", global_scope, ordinal=0),
        MaturityLevel(_entity_id("idkb_maturity", "m1"), CatalogCode("m1"), LocalizedName("M1 Canonical Core"), "Identity and top-level relations defined.", global_scope, ordinal=1),
        MaturityLevel(_entity_id("idkb_maturity", "m2"), CatalogCode("m2"), LocalizedName("M2 Measurement-Aware"), "Sensors, instruments, principles, and chains defined.", global_scope, ordinal=2),
        MaturityLevel(_entity_id("idkb_maturity", "m3"), CatalogCode("m3"), LocalizedName("M3 Operationally Usable"), "Variables, contexts, restrictions, consumers, and publishers defined.", global_scope, ordinal=3),
        MaturityLevel(_entity_id("idkb_maturity", "m4"), CatalogCode("m4"), LocalizedName("M4 Expert-Grade"), "Failure modes and expert differences documented.", global_scope, ordinal=4),
        MaturityLevel(_entity_id("idkb_maturity", "m5"), CatalogCode("m5"), LocalizedName("M5 Multi-Vendor Mature"), "Cross-vendor and cross-rig differentiation covered.", global_scope, ordinal=5),
    )
    knowledge_packs = (
        KnowledgePackManifest(_entity_id("knowledge_pack", "core_rig_foundations"), CatalogCode("core_rig_foundations"), LocalizedName("Core Rig Foundations"), "Initial backbone pack for rig and system foundations.", global_scope, pack_version="1.0.0", domain_codes=(CatalogCode("rig_and_system_foundations"),), article_template_code=CatalogCode("domain_article"), maturity_level_code=CatalogCode("m0")),
        KnowledgePackManifest(_entity_id("knowledge_pack", "core_surface_systems"), CatalogCode("core_surface_systems"), LocalizedName("Core Surface Systems"), "Initial backbone pack for mechanical and hydraulic systems.", global_scope, pack_version="1.0.0", domain_codes=(CatalogCode("mechanical_and_hydraulic_systems"),), article_template_code=CatalogCode("domain_article"), maturity_level_code=CatalogCode("m0")),
        KnowledgePackManifest(_entity_id("knowledge_pack", "core_data_systems"), CatalogCode("core_data_systems"), LocalizedName("Core Data Systems"), "Initial backbone pack for instrumentation and data systems.", global_scope, pack_version="1.0.0", domain_codes=(CatalogCode("control_instrumentation_and_data_systems"),), article_template_code=CatalogCode("domain_article"), maturity_level_code=CatalogCode("m0")),
    )
    return IdkbSeedBundle(
        domains=domains,
        identifier_definitions=identifier_definitions,
        article_templates=article_templates,
        maturity_levels=maturity_levels,
        knowledge_packs=knowledge_packs,
    )