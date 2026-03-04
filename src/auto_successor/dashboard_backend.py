from __future__ import annotations

from pathlib import Path

from .dashboard_runtime_manager import RuntimeManager
from .dashboard_service import DashboardService
from .resume_loader import ResumeLoader


class DataBackend(DashboardService):
    def __init__(self, workspace: Path) -> None:
        self.workspace = workspace
        self.data_dir = workspace / "data"
        self.runs_dir = self.data_dir / "runs"
        self.excel_path = self.data_dir / "output.xlsx"
        self.config_path = workspace / "config" / "config.yaml"
        self.retry_queue_path = self._resolve_retry_queue_path()
        self.runtime = RuntimeManager(workspace=workspace, config_path=self.config_path)
        self._resume_loader: ResumeLoader | None = None
        self._resume_source_path = workspace / "config" / "resume.txt"
        self._resume_text_path = workspace / "data" / "resume_text.txt"
