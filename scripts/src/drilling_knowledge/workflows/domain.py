"""Workflow orchestration contracts for end-to-end acquisition hardening."""

from __future__ import annotations

from dataclasses import dataclass, fields, is_dataclass
from datetime import datetime
from enum import Enum, StrEnum

from drilling_knowledge.common.ids import EntityId, RunId
from drilling_knowledge.review.domain import ReviewDecisionAction, ReviewTargetType


def _serialize_value(value: object) -> object:
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    if isinstance(value, (EntityId, RunId)):
        return str(value)
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, datetime):
        return value.isoformat()
    if is_dataclass(value):
        return {field.name: _serialize_value(getattr(value, field.name)) for field in fields(value)}
    if isinstance(value, tuple):
        return [_serialize_value(item) for item in value]
    if isinstance(value, list):
        return [_serialize_value(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _serialize_value(item) for key, item in sorted(value.items(), key=lambda item: str(item[0]))}
    return str(value)


class PipelineRunStatus(StrEnum):
    COMPLETED = "completed"
    AWAITING_REVIEW = "awaiting_review"
    FAILED = "failed"


class PipelineStepStatus(StrEnum):
    COMPLETED = "completed"
    SKIPPED = "skipped"
    FAILED = "failed"


@dataclass(frozen=True, slots=True)
class WorkflowHumanDecision:
    target_type: ReviewTargetType
    target_id: EntityId
    action: ReviewDecisionAction
    reason: str
    decided_by: str
    decided_at: datetime
    provenance: tuple[tuple[str, str], ...]

    def __post_init__(self) -> None:
        reason = self.reason.strip()
        decided_by = self.decided_by.strip()
        if not reason:
            raise ValueError("WorkflowHumanDecision.reason cannot be empty")
        if not decided_by:
            raise ValueError("WorkflowHumanDecision.decided_by cannot be empty")
        if not self.provenance:
            raise ValueError("WorkflowHumanDecision.provenance cannot be empty")
        object.__setattr__(self, "reason", reason)
        object.__setattr__(self, "decided_by", decided_by)
        object.__setattr__(self, "provenance", tuple(sorted(self.provenance)))

    def as_serializable(self) -> dict[str, object]:
        return _serialize_value(self)


@dataclass(frozen=True, slots=True)
class PipelineStepRun:
    step_run_id: RunId
    pipeline_run_id: RunId
    step_name: str
    step_order: int
    status: PipelineStepStatus
    input_json: tuple[tuple[str, object], ...]
    output_json: tuple[tuple[str, object], ...]
    error_json: tuple[tuple[str, object], ...] | None
    started_at: datetime
    finished_at: datetime
    created_by: str

    def __post_init__(self) -> None:
        step_name = self.step_name.strip().lower()
        created_by = self.created_by.strip()
        if not step_name:
            raise ValueError("PipelineStepRun.step_name cannot be empty")
        if self.step_order < 1:
            raise ValueError("PipelineStepRun.step_order must be >= 1")
        if self.finished_at < self.started_at:
            raise ValueError("PipelineStepRun.finished_at cannot be before started_at")
        if not created_by:
            raise ValueError("PipelineStepRun.created_by cannot be empty")
        object.__setattr__(self, "step_name", step_name)
        object.__setattr__(self, "created_by", created_by)
        object.__setattr__(self, "input_json", tuple(sorted(self.input_json, key=lambda item: item[0])))
        object.__setattr__(self, "output_json", tuple(sorted(self.output_json, key=lambda item: item[0])))
        if self.error_json is not None:
            object.__setattr__(self, "error_json", tuple(sorted(self.error_json, key=lambda item: item[0])))

    def as_serializable(self) -> dict[str, object]:
        return _serialize_value(self)


@dataclass(frozen=True, slots=True)
class PipelineRun:
    pipeline_run_id: RunId
    pipeline_name: str
    pipeline_version: str
    trigger_type: str
    status: PipelineRunStatus
    input_ref_json: tuple[tuple[str, object], ...]
    started_at: datetime
    finished_at: datetime
    created_by: str
    step_runs: tuple[PipelineStepRun, ...]
    errors: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        pipeline_name = self.pipeline_name.strip().lower()
        pipeline_version = self.pipeline_version.strip()
        trigger_type = self.trigger_type.strip().lower()
        created_by = self.created_by.strip()
        if not pipeline_name:
            raise ValueError("PipelineRun.pipeline_name cannot be empty")
        if not pipeline_version:
            raise ValueError("PipelineRun.pipeline_version cannot be empty")
        if not trigger_type:
            raise ValueError("PipelineRun.trigger_type cannot be empty")
        if self.finished_at < self.started_at:
            raise ValueError("PipelineRun.finished_at cannot be before started_at")
        if not created_by:
            raise ValueError("PipelineRun.created_by cannot be empty")
        if not self.step_runs:
            raise ValueError("PipelineRun.step_runs cannot be empty")
        sequences = tuple(step.step_order for step in self.step_runs)
        expected = tuple(range(1, len(self.step_runs) + 1))
        if sequences != expected:
            raise ValueError("PipelineRun.step_runs must define a contiguous order")
        for step in self.step_runs:
            if step.pipeline_run_id != self.pipeline_run_id:
                raise ValueError("PipelineRun.step_runs must reference pipeline_run_id")
        object.__setattr__(self, "pipeline_name", pipeline_name)
        object.__setattr__(self, "pipeline_version", pipeline_version)
        object.__setattr__(self, "trigger_type", trigger_type)
        object.__setattr__(self, "created_by", created_by)
        object.__setattr__(self, "input_ref_json", tuple(sorted(self.input_ref_json, key=lambda item: item[0])))

    def as_serializable(self) -> dict[str, object]:
        return _serialize_value(self)


@dataclass(frozen=True, slots=True)
class WorkflowAuditReport:
    pipeline_run_id: RunId
    final_status: PipelineRunStatus
    open_review_tasks: int
    completed_steps: int
    failed_steps: int
    errors: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.open_review_tasks < 0:
            raise ValueError("WorkflowAuditReport.open_review_tasks cannot be negative")
        if self.completed_steps < 0:
            raise ValueError("WorkflowAuditReport.completed_steps cannot be negative")
        if self.failed_steps < 0:
            raise ValueError("WorkflowAuditReport.failed_steps cannot be negative")

    def as_serializable(self) -> dict[str, object]:
        return _serialize_value(self)