from __future__ import annotations

from datetime import UTC, datetime
import unittest

from drilling_knowledge.common.exceptions import ConflictError
from drilling_knowledge.common.ids import RunId
from drilling_knowledge.workflows import InMemoryWorkflowRunRepository, PipelineRun, PipelineRunStatus, PipelineStepRun, PipelineStepStatus


class WorkflowRepositoryContractsTests(unittest.TestCase):
    def test_append_only_recovery_is_stable(self) -> None:
        run = self._run("contract")
        repository = InMemoryWorkflowRunRepository.empty().append_run(run)

        self.assertEqual(repository.get_run(run.pipeline_run_id), run)
        self.assertEqual(repository.list_runs(), (run,))

    def test_conflicting_run_id_is_rejected(self) -> None:
        first = self._run("contract")
        second = PipelineRun(
            pipeline_run_id=first.pipeline_run_id,
            pipeline_name=first.pipeline_name,
            pipeline_version=first.pipeline_version,
            trigger_type=first.trigger_type,
            status=PipelineRunStatus.FAILED,
            input_ref_json=first.input_ref_json,
            started_at=first.started_at,
            finished_at=first.finished_at,
            created_by=first.created_by,
            step_runs=first.step_runs,
            errors=("boom",),
        )

        with self.assertRaises(ConflictError):
            InMemoryWorkflowRunRepository((first, second))

    def _run(self, seed: str) -> PipelineRun:
        pipeline_run_id = RunId.from_seed("workflow.contract.pipeline", seed)
        timestamp = datetime(2026, 2, 11, 12, 0, tzinfo=UTC)
        step = PipelineStepRun(
            step_run_id=RunId.from_seed("workflow.contract.step", seed),
            pipeline_run_id=pipeline_run_id,
            step_name="document_ingestion",
            step_order=1,
            status=PipelineStepStatus.COMPLETED,
            input_json=(("document_id", seed),),
            output_json=(("fragment_count", 1),),
            error_json=None,
            started_at=timestamp,
            finished_at=timestamp,
            created_by="qa.engineer",
        )
        return PipelineRun(
            pipeline_run_id=pipeline_run_id,
            pipeline_name="document_to_ikc",
            pipeline_version="workflow.v1",
            trigger_type="manual",
            status=PipelineRunStatus.COMPLETED,
            input_ref_json=(("document_id", seed),),
            started_at=timestamp,
            finished_at=timestamp,
            created_by="qa.engineer",
            step_runs=(step,),
        )