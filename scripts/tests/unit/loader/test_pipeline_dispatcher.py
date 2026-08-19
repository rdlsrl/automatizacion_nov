from __future__ import annotations

import unittest

from drilling_knowledge.common.ids import EntityId, RunId
from drilling_knowledge.loader import DispatchRequest, PipelineDispatcher


class PipelineDispatcherTests(unittest.TestCase):
    def test_dispatch_returns_public_result(self) -> None:
        dispatcher = PipelineDispatcher(workflow=_StubWorkflow())
        request = DispatchRequest(
            artifact_id=EntityId.from_seed("loader.artifact", "one"),
            file_path="/tmp/manual.md",
            source_name="nov",
            manufacturer_name="NOV",
            document_metadata=(("document_type", "manual"),),
            provenance=(("original_url", "file:///tmp/manual.md"),),
        )

        result = dispatcher.dispatch(request)

        self.assertEqual(result.status, "dispatched")
        self.assertIsNotNone(result.document_id)
        self.assertIsNotNone(result.workflow_run_id)


class _StubWorkflow:
    def run(self, **kwargs):
        return _StubWorkflowResult()


class _StubWorkflowResult:
    def __init__(self) -> None:
        self.document = type("Document", (), {"entity_id": EntityId.from_seed("loader.document", "one")})()
        self.pipeline_run = type("PipelineRun", (), {"pipeline_run_id": RunId.from_seed("loader.run", "one")})()