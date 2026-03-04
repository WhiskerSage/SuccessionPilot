from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from auto_successor.agents import (
    CommunicationAgent,
    DigestDispatchResult,
    IntelligenceAgent,
    PlannerAgent,
)
from auto_successor.dashboard_backend import DataBackend
from auto_successor.pipeline import AutoSuccessorPipeline


class TestSplitCompatibility(unittest.TestCase):
    def test_agents_facade_exports(self) -> None:
        self.assertTrue(PlannerAgent.__module__.endswith("agents_planner"))
        self.assertTrue(IntelligenceAgent.__module__.endswith("agents_intelligence"))
        self.assertTrue(CommunicationAgent.__module__.endswith("agents_communication"))
        self.assertEqual(DigestDispatchResult.__name__, "DigestDispatchResult")

    def test_dashboard_backend_facade_keeps_core_methods(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            backend = DataBackend(workspace=Path(tmp))
            for name in (
                "load_summary",
                "load_leads_page",
                "load_runs",
                "load_performance",
                "load_runtime",
                "load_run_detail",
                "run_action",
                "_load_retry_queue",
            ):
                self.assertTrue(callable(getattr(backend, name, None)), msg=f"missing method: {name}")

    def test_pipeline_facade_keeps_mixin_methods(self) -> None:
        # 仅检查类级接口兼容，不实例化重对象。
        for name in (
            "run_once",
            "send_latest_stored",
            "_normalize_mode",
            "_process_retry_queue_once",
            "_load_latest_jobs_from_store",
            "_load_latest_summaries_from_store",
            "_dispatch_batch_with_compat",
            "_jobs_to_summary_records",
        ):
            self.assertTrue(callable(getattr(AutoSuccessorPipeline, name, None)), msg=f"missing method: {name}")


if __name__ == "__main__":
    unittest.main()

