"""LAS folder adapter for Industrial Knowledge Loader."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
import hashlib

from drilling_knowledge.common.ids import EntityId
from drilling_knowledge.loader.artifact_registry import LasFileRecord, MnemonicObservation


@dataclass(slots=True)
class LASAdapter:
    def scan(self, folder: str | Path, *, recursive: bool = False) -> tuple[tuple[LasFileRecord, tuple[MnemonicObservation, ...]], ...]:
        root = Path(folder)
        pattern = "**/*.las" if recursive else "*.las"
        records: list[tuple[LasFileRecord, tuple[MnemonicObservation, ...]]] = []
        for file_path in sorted(root.glob(pattern)):
            payload = file_path.read_bytes()
            sha256 = hashlib.sha256(payload).hexdigest()
            parsed_at = datetime.now(UTC)
            lines = file_path.read_text(encoding="utf-8", errors="ignore").splitlines()
            well_name = self._well_value(lines, "WELL")
            service_company = self._well_value(lines, "SRVC")
            record = LasFileRecord(
                las_file_id=EntityId.from_seed("loader.las", f"{file_path}:{sha256}"),
                file_path=str(file_path),
                sha256=sha256,
                well_name=well_name,
                service_company=service_company,
                parsed_at=parsed_at,
            )
            observations = self._curve_observations(record.las_file_id, lines)
            records.append((record, observations))
        return tuple(records)

    def _well_value(self, lines: list[str], key: str) -> str | None:
        prefix = f"{key}."
        for line in lines:
            stripped = line.strip()
            if stripped.upper().startswith(prefix):
                _, _, remainder = stripped.partition(":")
                return remainder.strip() or None
        return None

    def _curve_observations(self, las_file_id: EntityId, lines: list[str]) -> tuple[MnemonicObservation, ...]:
        in_curve = False
        observations: list[MnemonicObservation] = []
        for line in lines:
            stripped = line.strip()
            if not stripped:
                continue
            upper = stripped.upper()
            if upper.startswith("~CURVE") or upper.startswith("~C"):
                in_curve = True
                continue
            if in_curve and upper.startswith("~"):
                break
            if not in_curve or stripped.startswith("#"):
                continue
            left, _, description = stripped.partition(":")
            mnemonic_part, _, unit_part = left.partition(".")
            mnemonic = mnemonic_part.strip().upper()
            if not mnemonic:
                continue
            observations.append(
                MnemonicObservation(
                    las_file_id=las_file_id,
                    mnemonic=mnemonic,
                    unit=unit_part.strip() or None,
                    description=description.strip() or None,
                    depth_curve_flag=mnemonic in {"DEPT", "DEPTH"},
                    count=1,
                )
            )
        return tuple(observations)