"""Deterministic extraction rules for explicit technical mentions."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
import re

from drilling_knowledge.extraction.domain import ExtractedEntityType


class RuleKind(StrEnum):
    REGEX = "regex"
    LEXICON = "lexicon"


@dataclass(frozen=True, slots=True)
class RuleMatch:
    entity_type: ExtractedEntityType
    text: str
    start_offset: int
    end_offset: int
    extraction_rule: str
    extraction_confidence: float


@dataclass(frozen=True, slots=True)
class RegexRuleDefinition:
    entity_type: ExtractedEntityType
    rule_code: str
    pattern: re.Pattern[str]
    extraction_confidence: float
    group_name: str | None = None


@dataclass(frozen=True, slots=True)
class LexiconRuleDefinition:
    entity_type: ExtractedEntityType
    rule_code: str
    terms: tuple[str, ...]
    extraction_confidence: float


LEXICON_RULES: tuple[LexiconRuleDefinition, ...] = (
    LexiconRuleDefinition(
        entity_type=ExtractedEntityType.MANUFACTURER,
        rule_code="manufacturer.lexicon.v1",
        terms=("National Oilwell Varco", "NOV", "Emerson", "Honeywell", "ABB", "Siemens", "Rockwell"),
        extraction_confidence=1.0,
    ),
    LexiconRuleDefinition(
        entity_type=ExtractedEntityType.VARIABLE,
        rule_code="variable.lexicon.v2",
        terms=(
            "Hook Load",
            "Hookload",
            "Peso Gancho",
            "Standpipe Pressure",
            "Weight on Bit",
            "Rate of Penetration",
            "Flow In",
            "Flow Out",
        ),
        extraction_confidence=0.99,
    ),
    LexiconRuleDefinition(
        entity_type=ExtractedEntityType.PHYSICAL_QUANTITY,
        rule_code="quantity.lexicon.v2",
        terms=(
            "Flow Rate",
            "Temperature",
            "Pressure",
            "Torque",
            "Depth",
            "Rotary Speed",
        ),
        extraction_confidence=0.98,
    ),
    LexiconRuleDefinition(
        entity_type=ExtractedEntityType.SYSTEM,
        rule_code="system.lexicon.v1",
        terms=("Top Drive System", "Mud Circulation System", "Hydraulic System", "Control System", "Hoisting System"),
        extraction_confidence=0.98,
    ),
    LexiconRuleDefinition(
        entity_type=ExtractedEntityType.SUBSYSTEM,
        rule_code="subsystem.lexicon.v1",
        terms=("Brake Subsystem", "Lubrication Subsystem", "Cooling Subsystem", "Hoisting Subsystem", "Pump Subsystem"),
        extraction_confidence=0.98,
    ),
    LexiconRuleDefinition(
        entity_type=ExtractedEntityType.EQUIPMENT,
        rule_code="equipment.lexicon.v1",
        terms=("Top Drive", "Mud Pump", "Drawworks", "Standpipe Manifold", "Trip Tank", "Rotary Table"),
        extraction_confidence=0.97,
    ),
    LexiconRuleDefinition(
        entity_type=ExtractedEntityType.SENSOR,
        rule_code="sensor.lexicon.v1",
        terms=("Load Pin Sensor", "Pressure Sensor", "Temperature Sensor", "Flow Sensor", "Torque Sensor"),
        extraction_confidence=0.97,
    ),
    LexiconRuleDefinition(
        entity_type=ExtractedEntityType.INSTRUMENT,
        rule_code="instrument.lexicon.v1",
        terms=("Pressure Transmitter", "Flowmeter", "Gauge", "Indicator", "Controller", "PLC", "HMI"),
        extraction_confidence=0.97,
    ),
    LexiconRuleDefinition(
        entity_type=ExtractedEntityType.PROCESS,
        rule_code="process.lexicon.v1",
        terms=("Drilling", "Circulating", "Tripping", "Reaming", "Cementing", "Connections"),
        extraction_confidence=0.96,
    ),
    LexiconRuleDefinition(
        entity_type=ExtractedEntityType.ENGINEERING_UNIT,
        rule_code="unit.lexicon.v1",
        terms=("klbf", "psi", "rpm", "gpm", "ft", "in", "m", "degC", "degF", "mA", "A", "V", "%", "counts", "pulses"),
        extraction_confidence=1.0,
    ),
    LexiconRuleDefinition(
        entity_type=ExtractedEntityType.MNEMONIC,
        rule_code="mnemonic.lexicon.v1",
        terms=("HKLD", "SPP", "WOB", "ROP", "FLOWIN", "FLOWOUT", "RPM", "TQA"),
        extraction_confidence=0.95,
    ),
)


REGEX_RULES: tuple[RegexRuleDefinition, ...] = (
    RegexRuleDefinition(
        entity_type=ExtractedEntityType.STANDARD,
        rule_code="standard.regex.v1",
        pattern=re.compile(r"\b(?:WITSML(?:\s+\d+(?:\.\d+)*)?|API\s+(?:RP|Spec|STD)\s*\d+[A-Z-]*|ISO\s+\d+(?:-\d+)?|IEC\s+\d+(?:-\d+)*)\b", re.IGNORECASE),
        extraction_confidence=1.0,
    ),
    RegexRuleDefinition(
        entity_type=ExtractedEntityType.MODEL,
        rule_code="model.regex.v1",
        pattern=re.compile(r"\b(?:Model|Modelo)\s*[:\-]?\s*(?P<value>[A-Z0-9][A-Z0-9./_-]{1,40})\b"),
        extraction_confidence=0.99,
        group_name="value",
    ),
    RegexRuleDefinition(
        entity_type=ExtractedEntityType.ALIAS,
        rule_code="alias.regex.v1",
        pattern=re.compile(r"\b(?:alias|aka|also called|also referred to as)\s+(?P<value>[A-Za-z0-9][A-Za-z0-9 ./_-]{1,60})", re.IGNORECASE),
        extraction_confidence=0.94,
        group_name="value",
    ),
    RegexRuleDefinition(
        entity_type=ExtractedEntityType.ABBREVIATION,
        rule_code="abbreviation.regex.v1",
        pattern=re.compile(r"\b[A-Za-z][A-Za-z ]{2,60}\((?P<value>[A-Z]{2,12})\)"),
        extraction_confidence=0.95,
        group_name="value",
    ),
    RegexRuleDefinition(
        entity_type=ExtractedEntityType.TAG,
        rule_code="tag.regex.v2",
        pattern=re.compile(r"\b[A-Za-z][A-Za-z0-9]*(?:[-_][A-Za-z0-9]+){1,6}\b"),
        extraction_confidence=1.0,
    ),
    RegexRuleDefinition(
        entity_type=ExtractedEntityType.IDENTIFIER,
        rule_code="identifier.regex.v1",
        pattern=re.compile(r"\b(?:ID|Identifier|Identificador)\s*[:#-]?\s*(?P<value>[A-Z0-9][A-Z0-9._/-]{2,40})\b", re.IGNORECASE),
        extraction_confidence=0.96,
        group_name="value",
    ),
    RegexRuleDefinition(
        entity_type=ExtractedEntityType.RANGE,
        rule_code="range.regex.v1",
        pattern=re.compile(r"\b\d+(?:\.\d+)?\s*(?:to|-|–)\s*\d+(?:\.\d+)?(?:\s*(?:klbf|psi|rpm|gpm|ft|in|m|degC|degF|mA|A|V|%))?\b", re.IGNORECASE),
        extraction_confidence=0.99,
    ),
    RegexRuleDefinition(
        entity_type=ExtractedEntityType.RAW_SIGNAL,
        rule_code="raw_signal.regex.v1",
        pattern=re.compile(r"\b(?:4\s*(?:-|–|to)\s*20\s*mA|0\s*(?:-|–|to)\s*10\s*V|\d+\s*counts?|\d+\s*pulses?)\b", re.IGNORECASE),
        extraction_confidence=1.0,
    ),
    RegexRuleDefinition(
        entity_type=ExtractedEntityType.FORMULA,
        rule_code="formula.regex.v1",
        pattern=re.compile(r"\b(?:Formula|Equation|Ecuacion|Ecuación)\s*:\s*(?P<value>[A-Za-z][A-Za-z0-9_ ]{0,30}\s*=\s*[A-Za-z0-9_ ()+\-*/.]+)", re.IGNORECASE),
        extraction_confidence=0.99,
        group_name="value",
    ),
    RegexRuleDefinition(
        entity_type=ExtractedEntityType.NUMBER,
        rule_code="number.regex.v1",
        pattern=re.compile(r"\b\d+(?:\.\d+)?\b"),
        extraction_confidence=0.9,
    ),
    RegexRuleDefinition(
        entity_type=ExtractedEntityType.DOCUMENT_REFERENCE,
        rule_code="document_reference.regex.v1",
        pattern=re.compile(
            r"\b(?:Document|Doc\.)\s+(?P<value>(?:[A-Z]{2,10}(?:\s+(?:RP|Spec|STD))?\s*\d+[A-Z-]*|[A-Z]{2,10}-\d{2,6}|[A-Za-z0-9._/-]{3,40}))\b",
            re.IGNORECASE,
        ),
        extraction_confidence=0.96,
        group_name="value",
    ),
)


def apply_lexicon_rules(text: str) -> list[RuleMatch]:
    matches: list[RuleMatch] = []
    for rule in LEXICON_RULES:
        for term in sorted(rule.terms, key=len, reverse=True):
            pattern = re.compile(rf"(?<![A-Za-z0-9]){re.escape(term)}(?![A-Za-z0-9])", re.IGNORECASE)
            for match in pattern.finditer(text):
                if _is_nested_match(matches, match.start(), match.end(), rule.entity_type):
                    continue
                matches.append(
                    RuleMatch(
                        entity_type=rule.entity_type,
                        text=match.group(0),
                        start_offset=match.start(),
                        end_offset=match.end(),
                        extraction_rule=rule.rule_code,
                        extraction_confidence=rule.extraction_confidence,
                    )
                )
    return matches


def apply_regex_rules(text: str) -> list[RuleMatch]:
    matches: list[RuleMatch] = []
    for rule in REGEX_RULES:
        for match in rule.pattern.finditer(text):
            span_text = match.group(rule.group_name) if rule.group_name else match.group(0)
            start_offset, end_offset = match.span(rule.group_name) if rule.group_name else match.span(0)
            matches.append(
                RuleMatch(
                    entity_type=rule.entity_type,
                    text=span_text,
                    start_offset=start_offset,
                    end_offset=end_offset,
                    extraction_rule=rule.rule_code,
                    extraction_confidence=rule.extraction_confidence,
                )
            )
    return matches


def _is_nested_match(existing_matches: list[RuleMatch], start_offset: int, end_offset: int, entity_type: ExtractedEntityType) -> bool:
    return any(
        existing.entity_type == entity_type
        and start_offset >= existing.start_offset
        and end_offset <= existing.end_offset
        for existing in existing_matches
    )