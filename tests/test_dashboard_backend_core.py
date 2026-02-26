from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

import yaml

from auto_successor.dashboard_backend import DataBackend


def _write_config(path: Path) -> None:
    data = {
        "app": {"interval_minutes": 15},
        "xhs": {
            "keyword": "继任",
            "search_sort": "time_descending",
            "max_results": 20,
            "max_detail_fetch": 5,
        },
        "agent": {"mode": "auto"},
        "notification": {
            "mode": "digest",
            "digest_interval_minutes": 30,
            "digest_top_summaries": 5,
            "digest_send_when_no_new": False,
            "digest_channels": ["email"],
            "realtime_channels": ["wechat_service", "email"],
        },
        "email": {"enabled": True},
        "wechat_service": {"enabled": False},
        "llm": {"enabled": False, "model": "gpt-5-mini", "base_url": "https://api.openai.com/v1"},
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(data, sort_keys=False, allow_unicode=True), encoding="utf-8")


def test_config_roundtrip(tmp_path: Path) -> None:
    workspace = tmp_path
    _write_config(workspace / "config" / "config.yaml")
    backend = DataBackend(workspace=workspace)

    view = backend.load_config_view()
    assert view["xhs"]["keyword"] == "继任"
    assert view["notification"]["digest_interval_minutes"] == 30

    saved = backend.save_config_view(
        {
            "xhs": {"keyword": "继任岗位", "max_results": 18},
            "notification": {"digest_interval_minutes": 60},
            "agent": {"mode": "agent"},
        }
    )
    assert saved["xhs"]["keyword"] == "继任岗位"
    assert saved["xhs"]["max_results"] == 18
    assert saved["notification"]["digest_interval_minutes"] == 60
    assert saved["agent"]["mode"] == "agent"


def test_runtime_no_job_stop_is_safe(tmp_path: Path) -> None:
    workspace = tmp_path
    _write_config(workspace / "config" / "config.yaml")
    backend = DataBackend(workspace=workspace)

    result = backend.run_action("stop_job", {})
    assert result["ok"] is False
    assert "任务" in str(result.get("message", ""))


def test_run_action_invalid(tmp_path: Path) -> None:
    workspace = tmp_path
    _write_config(workspace / "config" / "config.yaml")
    backend = DataBackend(workspace=workspace)

    try:
        backend.run_action("unknown_action", {})
    except ValueError as exc:
        assert "unsupported action" in str(exc)
    else:
        raise AssertionError("expected ValueError")


def test_load_leads_page_empty(tmp_path: Path) -> None:
    workspace = tmp_path
    _write_config(workspace / "config" / "config.yaml")
    backend = DataBackend(workspace=workspace)

    result = backend.load_leads_page(page=1, page_size=20, q="", summary_only=False)
    assert result["items"] == []
    assert result["total"] == 0
    assert result["page"] == 1
    assert result["page_size"] == 20
    assert result["total_pages"] == 1


def test_load_runs_with_stage_observability_from_stats(tmp_path: Path) -> None:
    workspace = tmp_path
    _write_config(workspace / "config" / "config.yaml")
    runs_dir = workspace / "data" / "runs"
    runs_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "run_id": "r-observe",
        "recorded_at": "2026-02-25T12:00:00+00:00",
        "stats": {
            "mode": "agent",
            "notification_mode": "digest",
            "fetched": 9,
            "target_notes": 4,
            "jobs": 3,
            "send_logs": 2,
            "digest_sent": True,
            "stage_total_ms": 4800,
            "stage_avg_ms": 1200,
            "stage_failed_count": 1,
            "stage_top_slow": [
                {"name": "collector.search", "duration_ms": 2600, "status": "success"},
                {"name": "agent.filter", "duration_ms": 1400, "status": "failed"},
            ],
            "llm_error_codes": {"read_timeout": 2},
            "stage_error_codes": {"timeout": 1},
        },
    }
    (runs_dir / "20260225-120000.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    backend = DataBackend(workspace=workspace)

    result = backend.load_runs(limit=10)
    assert len(result) == 1
    item = result[0]
    assert item["mode"] == "agent"
    assert item["notification_mode"] == "digest"
    assert item["stage_total_ms"] == 4800
    assert item["stage_avg_ms"] == 1200
    assert item["stage_failed_count"] == 1
    assert item["slow_stages"][0]["name"] == "collector.search"
    assert item["error_codes"]["read_timeout"] == 2
    assert item["error_codes"]["timeout"] == 1


def test_load_runs_fallback_stage_metrics_from_stage_records(tmp_path: Path) -> None:
    workspace = tmp_path
    _write_config(workspace / "config" / "config.yaml")
    runs_dir = workspace / "data" / "runs"
    runs_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "run_id": "r-stage-fallback",
        "recorded_at": "2026-02-25T12:10:00+00:00",
        "stats": {
            "fetched": 2,
            "target_notes": 1,
            "jobs": 1,
        },
        "stage_records": [
            {"name": "collector.search", "duration_ms": 900, "status": "success"},
            {"name": "agent.filter", "duration_ms": 300, "status": "failed", "error_code": "network_error"},
        ],
    }
    (runs_dir / "20260225-121000.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    backend = DataBackend(workspace=workspace)

    result = backend.load_runs(limit=10)
    assert len(result) == 1
    item = result[0]
    assert item["stage_total_ms"] == 1200
    assert item["stage_avg_ms"] == 600
    assert item["stage_failed_count"] == 1
    assert item["slow_stages"][0]["name"] == "collector.search"
    assert item["error_codes"]["network_error"] == 1


def test_setup_check_offline_mode(tmp_path: Path) -> None:
    workspace = tmp_path
    _write_config(workspace / "config" / "config.yaml")

    cfg_path = workspace / "config" / "config.yaml"
    cfg = yaml.safe_load(cfg_path.read_text(encoding="utf-8")) or {}
    cfg.setdefault("xhs", {})
    cfg["xhs"]["command"] = "python"
    cfg["xhs"]["args"] = ["vendor/xhs-mcp/dist/xhs-mcp.js"]
    cfg.setdefault("email", {})
    cfg["email"]["enabled"] = False
    cfg.setdefault("llm", {})
    cfg["llm"]["enabled"] = False
    cfg_path.write_text(yaml.safe_dump(cfg, sort_keys=False, allow_unicode=True), encoding="utf-8")

    script = workspace / "vendor" / "xhs-mcp" / "dist" / "xhs-mcp.js"
    script.parent.mkdir(parents=True, exist_ok=True)
    script.write_text("// fake script for setup check\n", encoding="utf-8")

    backend = DataBackend(workspace=workspace)
    result = backend.run_setup_check(include_network=False, include_xhs_status=False)
    assert result["ok"] is True
    assert result["summary"]["failed"] == 0
    keys = {item["key"]: item for item in result["items"]}
    assert keys["config_file"]["status"] == "pass"
    assert keys["storage_write"]["status"] == "pass"
    assert keys["xhs_runtime"]["status"] == "pass"
    assert keys["xhs_login"]["status"] == "warn"
    assert keys["email_enabled"]["status"] == "warn"
    assert keys["llm_enabled"]["status"] == "warn"


class TestDashboardBackendCore(unittest.TestCase):
    def test_load_runs_with_stage_observability_from_stats_unittest(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            test_load_runs_with_stage_observability_from_stats(Path(tmp_dir))

    def test_load_runs_fallback_stage_metrics_from_stage_records_unittest(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            test_load_runs_fallback_stage_metrics_from_stage_records(Path(tmp_dir))

    def test_setup_check_offline_mode_unittest(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            test_setup_check_offline_mode(Path(tmp_dir))
