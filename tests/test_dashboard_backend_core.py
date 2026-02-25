from __future__ import annotations

from pathlib import Path

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
