from __future__ import annotations

import hashlib
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .models import JobRecord, NoteRecord, SummaryRecord
from .pipeline_repository import PipelineRepositoryMixin


class PipelineServiceMixin(PipelineRepositoryMixin):
    @staticmethod
    def _normalize_mode(mode: str) -> str:
        value = (mode or "auto").strip().lower()
        if value == "smart":
            value = "agent"
        if value not in {"auto", "agent"}:
            return "auto"
        return value

    @staticmethod
    def _normalize_notification_mode(mode: str) -> str:
        value = (mode or "digest").strip().lower()
        if value not in {"digest", "realtime", "off"}:
            return "digest"
        return value

    def _collect_digest_attachments(self) -> list[str]:
        paths: list[str] = []
        if self.settings.notification.attach_excel:
            excel = Path(self.settings.storage.excel_path)
            if excel.exists():
                paths.append(str(excel))
        if self.settings.notification.attach_jobs_csv:
            jobs_csv = Path(self.settings.storage.jobs_csv_path)
            if jobs_csv.exists():
                paths.append(str(jobs_csv))
        return paths

    def _is_digest_due(self, now: datetime) -> bool:
        interval = int(self.settings.notification.digest_interval_minutes)
        if hasattr(self.state, "is_digest_due"):
            return bool(self.state.is_digest_due(now, interval))
        return True

    def _mark_digest_sent(self, now: datetime, run_id: str) -> None:
        if hasattr(self.state, "mark_digest_sent"):
            self.state.mark_digest_sent(now, run_id)

    @staticmethod
    def _sum_timeout_error_counts(llm_error_codes: dict[str, int] | None) -> int:
        timeout_keys = {"connect_timeout", "read_timeout", "timeout"}
        total = 0
        if not isinstance(llm_error_codes, dict):
            return 0
        for code, count in llm_error_codes.items():
            key = str(code or "").strip().lower()
            if key not in timeout_keys:
                continue
            total += max(0, int(count or 0))
        return total

    @staticmethod
    def _normalize_rate_threshold(value: Any, *, default: float) -> float:
        try:
            parsed = float(value)
        except Exception:
            return float(default)
        if parsed > 1.0 and parsed <= 100.0:
            parsed = parsed / 100.0
        if parsed < 0:
            return 0.0
        if parsed > 1.0:
            return 1.0
        return parsed

    @staticmethod
    def _normalize_numeric_threshold(value: Any, *, default: float, minimum: float = 0.0) -> float:
        try:
            parsed = float(value)
        except Exception:
            parsed = float(default)
        if parsed < float(minimum):
            parsed = float(minimum)
        return parsed

    @staticmethod
    def _normalize_window_runs(value: Any, *, default: int) -> int:
        try:
            parsed = int(value)
        except Exception:
            parsed = int(default)
        return max(1, parsed)

    @staticmethod
    def _normalize_min_samples(value: Any, *, default: int) -> int:
        try:
            parsed = int(value)
        except Exception:
            parsed = int(default)
        return max(1, parsed)

    @staticmethod
    def _aggregate_window_fetch(window_stats: list[dict[str, Any]]) -> dict[str, Any]:
        values: list[float] = []
        for item in window_stats:
            try:
                values.append(max(0.0, float(item.get("fetch_fail_streak", 0) or 0)))
            except Exception:
                values.append(0.0)
        if not values:
            return {"runs": 0, "max": 0.0, "avg": 0.0}
        return {
            "runs": len(values),
            "max": max(values),
            "avg": float(sum(values)) / float(len(values)),
        }

    @staticmethod
    def _aggregate_window_rate(
        window_stats: list[dict[str, Any]],
        *,
        numerator_key: str,
        denominator_key: str,
    ) -> dict[str, Any]:
        numerator = 0
        denominator = 0
        for item in window_stats:
            numerator += max(0, int(item.get(numerator_key, 0) or 0))
            denominator += max(0, int(item.get(denominator_key, 0) or 0))
        rate = float(numerator) / float(denominator) if denominator > 0 else 0.0
        return {
            "runs": len(window_stats),
            "numerator": numerator,
            "denominator": denominator,
            "rate": rate,
        }

    def _evaluate_threshold_alerts(self, *, run_id: str, stats: dict[str, Any]) -> dict[str, Any]:
        cfg = getattr(getattr(self.settings, "observability", None), "alerts", None)
        if cfg is None or not bool(getattr(cfg, "enabled", True)):
            return {"enabled": False, "thresholds": {}, "triggered": []}

        # Legacy single-threshold values are kept as fallback defaults.
        legacy_fetch_threshold = max(1, int(getattr(cfg, "fetch_fail_streak_threshold", 2) or 2))
        legacy_llm_rate_threshold = self._normalize_rate_threshold(
            getattr(cfg, "llm_timeout_rate_threshold", 0.35),
            default=0.35,
        )
        legacy_llm_min_calls = max(1, int(getattr(cfg, "llm_timeout_min_calls", 6) or 6))
        legacy_detail_rate_threshold = self._normalize_rate_threshold(
            getattr(cfg, "detail_missing_rate_threshold", 0.45),
            default=0.45,
        )
        legacy_detail_min_samples = max(1, int(getattr(cfg, "detail_missing_min_samples", 6) or 6))

        fetch_cfg = getattr(cfg, "fetch_fail_streak", {}) or {}
        llm_cfg = getattr(cfg, "llm_timeout_rate", {}) or {}
        detail_cfg = getattr(cfg, "detail_missing_rate", {}) or {}
        if not isinstance(fetch_cfg, dict):
            fetch_cfg = {}
        if not isinstance(llm_cfg, dict):
            llm_cfg = {}
        if not isinstance(detail_cfg, dict):
            detail_cfg = {}

        fetch_short_window_runs = self._normalize_window_runs(fetch_cfg.get("short_window_runs"), default=1)
        fetch_short_threshold = self._normalize_numeric_threshold(
            fetch_cfg.get("short_threshold"),
            default=float(legacy_fetch_threshold),
            minimum=1.0,
        )
        fetch_short_min_runs = self._normalize_min_samples(fetch_cfg.get("short_min_runs"), default=1)
        fetch_long_window_runs = self._normalize_window_runs(fetch_cfg.get("long_window_runs"), default=6)
        fetch_long_threshold = self._normalize_numeric_threshold(
            fetch_cfg.get("long_threshold"),
            default=max(1.0, float(legacy_fetch_threshold) * 0.6),
            minimum=1.0,
        )
        fetch_long_min_runs = self._normalize_min_samples(fetch_cfg.get("long_min_runs"), default=3)

        llm_short_window_runs = self._normalize_window_runs(llm_cfg.get("short_window_runs"), default=1)
        llm_short_threshold = self._normalize_rate_threshold(
            llm_cfg.get("short_threshold"),
            default=legacy_llm_rate_threshold,
        )
        llm_short_min_calls = self._normalize_min_samples(
            llm_cfg.get("short_min_samples"),
            default=legacy_llm_min_calls,
        )
        llm_long_window_runs = self._normalize_window_runs(llm_cfg.get("long_window_runs"), default=8)
        llm_long_threshold = self._normalize_rate_threshold(
            llm_cfg.get("long_threshold"),
            default=min(1.0, max(0.0, legacy_llm_rate_threshold * 0.7)),
        )
        llm_long_min_calls = self._normalize_min_samples(
            llm_cfg.get("long_min_samples"),
            default=max(12, legacy_llm_min_calls * 3),
        )

        detail_short_window_runs = self._normalize_window_runs(detail_cfg.get("short_window_runs"), default=1)
        detail_short_threshold = self._normalize_rate_threshold(
            detail_cfg.get("short_threshold"),
            default=legacy_detail_rate_threshold,
        )
        detail_short_min_samples = self._normalize_min_samples(
            detail_cfg.get("short_min_samples"),
            default=legacy_detail_min_samples,
        )
        detail_long_window_runs = self._normalize_window_runs(detail_cfg.get("long_window_runs"), default=8)
        detail_long_threshold = self._normalize_rate_threshold(
            detail_cfg.get("long_threshold"),
            default=min(1.0, max(0.0, legacy_detail_rate_threshold * 0.7)),
        )
        detail_long_min_samples = self._normalize_min_samples(
            detail_cfg.get("long_min_samples"),
            default=max(12, legacy_detail_min_samples * 3),
        )

        max_window_runs = max(
            fetch_short_window_runs,
            fetch_long_window_runs,
            llm_short_window_runs,
            llm_long_window_runs,
            detail_short_window_runs,
            detail_long_window_runs,
        )
        historical_stats = self._load_recent_alert_stats(
            limit=max(0, max_window_runs - 1),
            exclude_run_id=run_id,
        )
        run_stats_window = [stats] + historical_stats

        thresholds = {
            "fetch_fail_streak": {
                "short_window_runs": fetch_short_window_runs,
                "short_threshold": fetch_short_threshold,
                "short_min_runs": fetch_short_min_runs,
                "long_window_runs": fetch_long_window_runs,
                "long_threshold": fetch_long_threshold,
                "long_min_runs": fetch_long_min_runs,
            },
            "llm_timeout_rate": {
                "short_window_runs": llm_short_window_runs,
                "short_threshold": llm_short_threshold,
                "short_min_samples": llm_short_min_calls,
                "long_window_runs": llm_long_window_runs,
                "long_threshold": llm_long_threshold,
                "long_min_samples": llm_long_min_calls,
            },
            "llm_timeout_spike": {
                "min_calls": max(2, min(llm_short_min_calls, 4)),
                "count_threshold": max(2, min(llm_short_min_calls, 3)),
                "rate_threshold": max(0.5, llm_short_threshold),
            },
            "detail_missing_rate": {
                "short_window_runs": detail_short_window_runs,
                "short_threshold": detail_short_threshold,
                "short_min_samples": detail_short_min_samples,
                "long_window_runs": detail_long_window_runs,
                "long_threshold": detail_long_threshold,
                "long_min_samples": detail_long_min_samples,
            },
            "history_sample_runs": len(run_stats_window),
            "resume_missing": {
                "threshold": 1,
            },
            "retry_backlog": {
                "pending_total_threshold": max(3, int(getattr(self.settings.retry, "replay_batch_size", 3) or 3) * 2),
            },
            "xhs_failure": {
                "enabled": True,
            },
        }
        triggered: list[dict[str, Any]] = []

        fetch_short = self._aggregate_window_fetch(run_stats_window[:fetch_short_window_runs])
        fetch_long = self._aggregate_window_fetch(run_stats_window[:fetch_long_window_runs])
        fetch_ready = (
            int(fetch_short.get("runs", 0)) >= fetch_short_min_runs
            and int(fetch_long.get("runs", 0)) >= fetch_long_min_runs
        )
        fetch_short_value = float(fetch_short.get("max", 0.0))
        fetch_long_value = float(fetch_long.get("avg", 0.0))
        if fetch_ready and fetch_short_value >= fetch_short_threshold and fetch_long_value >= fetch_long_threshold:
            triggered.append(
                {
                    "code": "fetch_fail_streak",
                    "level": "critical",
                    "metric": "fetch_fail_streak",
                    "value": fetch_short_value,
                    "threshold": fetch_short_threshold,
                    "sample_size": int(fetch_short.get("runs", 0)),
                    "window_short": {
                        "runs": int(fetch_short.get("runs", 0)),
                        "value": fetch_short_value,
                        "threshold": fetch_short_threshold,
                        "mode": "max",
                    },
                    "window_long": {
                        "runs": int(fetch_long.get("runs", 0)),
                        "value": fetch_long_value,
                        "threshold": fetch_long_threshold,
                        "mode": "avg",
                    },
                    "reason": (
                        f"fetch_fail_streak 短窗max={fetch_short_value:.2f}/{fetch_short_threshold:.2f}，"
                        f"长窗avg={fetch_long_value:.2f}/{fetch_long_threshold:.2f}"
                    ),
                }
            )

        llm_short = self._aggregate_window_rate(
            run_stats_window[:llm_short_window_runs],
            numerator_key="llm_timeout_count",
            denominator_key="llm_calls",
        )
        llm_long = self._aggregate_window_rate(
            run_stats_window[:llm_long_window_runs],
            numerator_key="llm_timeout_count",
            denominator_key="llm_calls",
        )
        llm_short_calls = int(llm_short.get("denominator", 0))
        llm_short_timeout_count = int(llm_short.get("numerator", 0))
        llm_short_rate = float(llm_short.get("rate", 0.0))
        llm_long_calls = int(llm_long.get("denominator", 0))
        llm_long_timeout_count = int(llm_long.get("numerator", 0))
        llm_long_rate = float(llm_long.get("rate", 0.0))
        llm_spike_cfg = thresholds.get("llm_timeout_spike", {}) if isinstance(thresholds.get("llm_timeout_spike"), dict) else {}
        llm_spike_min_calls = max(2, int(llm_spike_cfg.get("min_calls", 4) or 4))
        llm_spike_count_threshold = max(2, int(llm_spike_cfg.get("count_threshold", 3) or 3))
        llm_spike_rate_threshold = self._normalize_rate_threshold(
            llm_spike_cfg.get("rate_threshold"),
            default=max(0.5, llm_short_threshold),
        )
        llm_current_calls = max(0, int(stats.get("llm_calls", 0) or 0))
        llm_current_timeout_count = max(0, int(stats.get("llm_timeout_count", 0) or 0))
        llm_current_timeout_rate = (
            float(llm_current_timeout_count) / float(llm_current_calls) if llm_current_calls > 0 else 0.0
        )
        llm_error_codes = stats.get("llm_error_codes") if isinstance(stats.get("llm_error_codes"), dict) else {}
        timeout_error_codes = {
            str(code): max(0, int(count or 0))
            for code, count in llm_error_codes.items()
            if max(0, int(count or 0)) > 0 and str(code or "").strip().lower() in {"connect_timeout", "read_timeout", "timeout"}
        }
        if (
            llm_current_calls >= llm_spike_min_calls
            and llm_current_timeout_count >= llm_spike_count_threshold
            and llm_current_timeout_rate >= llm_spike_rate_threshold
        ):
            triggered.append(
                {
                    "code": "llm_timeout_spike",
                    "level": "critical",
                    "metric": "llm_timeout_count",
                    "value": llm_current_timeout_count,
                    "threshold": llm_spike_count_threshold,
                    "sample_size": llm_current_calls,
                    "timeout_rate": llm_current_timeout_rate,
                    "rate_threshold": llm_spike_rate_threshold,
                    "error_codes": timeout_error_codes,
                    "reason": (
                        f"?? LLM ?? {llm_current_timeout_count}/{llm_current_calls}"
                        f" ({llm_current_timeout_rate:.1%})??????????"
                        f" count>={llm_spike_count_threshold} ? rate>={llm_spike_rate_threshold:.1%}?"
                        f" timeout_codes={timeout_error_codes or '-'}"
                    ),
                }
            )
        if (
            llm_short_calls >= llm_short_min_calls
            and llm_long_calls >= llm_long_min_calls
            and llm_short_rate >= llm_short_threshold
            and llm_long_rate >= llm_long_threshold
        ):
            triggered.append(
                {
                    "code": "llm_timeout_rate",
                    "level": "warning",
                    "metric": "llm_timeout_rate",
                    "value": llm_short_rate,
                    "threshold": llm_short_threshold,
                    "sample_size": llm_short_calls,
                    "window_short": {
                        "runs": int(llm_short.get("runs", 0)),
                        "value": llm_short_rate,
                        "threshold": llm_short_threshold,
                        "numerator": llm_short_timeout_count,
                        "denominator": llm_short_calls,
                    },
                    "window_long": {
                        "runs": int(llm_long.get("runs", 0)),
                        "value": llm_long_rate,
                        "threshold": llm_long_threshold,
                        "numerator": llm_long_timeout_count,
                        "denominator": llm_long_calls,
                    },
                    "reason": (
                        f"LLM 超时率短窗 {llm_short_rate:.1%}（{llm_short_timeout_count}/{llm_short_calls}）/"
                        f"{llm_short_threshold:.1%}，长窗 {llm_long_rate:.1%}（{llm_long_timeout_count}/{llm_long_calls}）/"
                        f"{llm_long_threshold:.1%}"
                    ),
                }
            )

        detail_short = self._aggregate_window_rate(
            run_stats_window[:detail_short_window_runs],
            numerator_key="detail_missing",
            denominator_key="detail_target_notes",
        )
        detail_long = self._aggregate_window_rate(
            run_stats_window[:detail_long_window_runs],
            numerator_key="detail_missing",
            denominator_key="detail_target_notes",
        )
        detail_short_target = int(detail_short.get("denominator", 0))
        detail_short_missing = int(detail_short.get("numerator", 0))
        detail_short_rate = float(detail_short.get("rate", 0.0))
        detail_long_target = int(detail_long.get("denominator", 0))
        detail_long_missing = int(detail_long.get("numerator", 0))
        detail_long_rate = float(detail_long.get("rate", 0.0))
        if (
            detail_short_target >= detail_short_min_samples
            and detail_long_target >= detail_long_min_samples
            and detail_short_rate >= detail_short_threshold
            and detail_long_rate >= detail_long_threshold
        ):
            triggered.append(
                {
                    "code": "detail_missing_rate",
                    "level": "warning",
                    "metric": "detail_missing_rate",
                    "value": detail_short_rate,
                    "threshold": detail_short_threshold,
                    "sample_size": detail_short_target,
                    "window_short": {
                        "runs": int(detail_short.get("runs", 0)),
                        "value": detail_short_rate,
                        "threshold": detail_short_threshold,
                        "numerator": detail_short_missing,
                        "denominator": detail_short_target,
                    },
                    "window_long": {
                        "runs": int(detail_long.get("runs", 0)),
                        "value": detail_long_rate,
                        "threshold": detail_long_threshold,
                        "numerator": detail_long_missing,
                        "denominator": detail_long_target,
                    },
                    "reason": (
                        f"详情缺失率短窗 {detail_short_rate:.1%}（{detail_short_missing}/{detail_short_target}）/"
                        f"{detail_short_threshold:.1%}，长窗 {detail_long_rate:.1%}（{detail_long_missing}/{detail_long_target}）/"
                        f"{detail_long_threshold:.1%}"
                    ),
                }
            )

        resume_chars = max(0, int(stats.get("resume_chars") or 0))
        resume_relevant = max(0, int(stats.get("target_notes") or 0)) > 0 or max(0, int(stats.get("jobs") or 0)) > 0
        if resume_relevant and resume_chars <= 0:
            triggered.append(
                {
                    "code": "resume_missing",
                    "level": "warning",
                    "metric": "resume_chars",
                    "value": resume_chars,
                    "threshold": 1,
                    "sample_size": 1,
                    "reason": (
                        "简历文本为空，匹配分与套磁文案会退化为无简历上下文。"
                        "请检查 config/resume.txt 或 resume.source_txt_path。"
                    ),
                }
            )

        diagnosis = stats.get("xhs_diagnosis") if isinstance(stats.get("xhs_diagnosis"), dict) else {}
        xhs_failure_category = str(diagnosis.get("failure_category") or "").strip().lower()
        xhs_failure_map = {
            "not_logged_in": "xhs_not_logged_in",
            "mcp_unreachable": "xhs_mcp_unreachable",
            "risk_control": "xhs_risk_control",
        }
        xhs_alert_code = xhs_failure_map.get(xhs_failure_category, "")
        if xhs_alert_code:
            triggered.append(
                {
                    "code": xhs_alert_code,
                    "level": "critical" if xhs_failure_category in {"mcp_unreachable", "not_logged_in"} else "warning",
                    "metric": "xhs_failure_category",
                    "value": xhs_failure_category,
                    "threshold": 1,
                    "sample_size": 1,
                    "reason": str(diagnosis.get("reason") or xhs_failure_category or "XHS 诊断失败"),
                }
            )

        retry_pending = stats.get("retry_pending") if isinstance(stats.get("retry_pending"), dict) else {}
        retry_pending_total = sum(max(0, int(value or 0)) for value in retry_pending.values())
        retry_backlog_threshold = int(thresholds.get("retry_backlog", {}).get("pending_total_threshold", 3) or 3)
        if retry_pending_total >= retry_backlog_threshold:
            triggered.append(
                {
                    "code": "retry_backlog",
                    "level": "warning",
                    "metric": "retry_pending_total",
                    "value": retry_pending_total,
                    "threshold": retry_backlog_threshold,
                    "sample_size": retry_pending_total,
                    "queue_breakdown": dict(retry_pending),
                    "reason": (
                        f"重试队列待处理任务积压 {retry_pending_total} 条，阈值 {retry_backlog_threshold} 条。"
                        f" pending={retry_pending}"
                    ),
                }
            )

        if triggered:
            codes = ",".join(str(item.get("code") or "") for item in triggered)
            self.logger.warning("阈值告警命中 | run=%s | count=%s | codes=%s", run_id, len(triggered), codes)
        return {"enabled": True, "thresholds": thresholds, "triggered": triggered}

    def _resolve_alert_channels(self) -> list[str]:
        cfg = getattr(getattr(self.settings, "observability", None), "alerts", None)
        configured = list(getattr(cfg, "channels", []) or [])
        channels = [str(item).strip() for item in configured if str(item).strip()]
        if channels:
            return channels
        fallback = [str(item).strip() for item in (self.settings.notification.digest_channels or []) if str(item).strip()]
        return fallback or ["email"]

    def _is_alert_due(self, alert_code: str, now: datetime, cooldown_minutes: int) -> bool:
        if hasattr(self.state, "is_alert_due"):
            return bool(self.state.is_alert_due(alert_code, now, cooldown_minutes))
        return True

    def _mark_alert_sent(self, alert_code: str, now: datetime) -> None:
        if hasattr(self.state, "mark_alert_sent"):
            self.state.mark_alert_sent(alert_code, now)

    def _build_threshold_alert_message(
        self,
        *,
        run_id: str,
        mode: str,
        stats: dict[str, Any],
        alerts: list[dict[str, Any]],
    ) -> str:
        lines = [
            "SuccessionPilot 阈值告警",
            "====================",
            "",
            f"Run ID: {run_id}",
            f"Mode: {mode}",
            f"Keyword: {self.settings.xhs.keyword}",
            f"Triggered: {len(alerts)}",
            "",
            "告警详情：",
        ]
        for index, item in enumerate(alerts, start=1):
            code = str(item.get("code") or "unknown")
            reason = str(item.get("reason") or "").strip()
            value = item.get("value")
            threshold = item.get("threshold")
            sample = int(item.get("sample_size") or 0)
            if isinstance(value, float):
                value_text = f"{value:.1%}" if "rate" in code else f"{value:.4f}"
            else:
                value_text = str(value)
            if isinstance(threshold, float):
                threshold_text = f"{threshold:.1%}" if "rate" in code else f"{threshold:.4f}"
            else:
                threshold_text = str(threshold)
            short_window = item.get("window_short") if isinstance(item.get("window_short"), dict) else {}
            long_window = item.get("window_long") if isinstance(item.get("window_long"), dict) else {}
            lines.extend(
                [
                    f"{index}. {code}",
                    f"   - value: {value_text}",
                    f"   - threshold: {threshold_text}",
                    f"   - sample_size: {sample}",
                    (
                        f"   - short_window: runs={int(short_window.get('runs', 0))} "
                        f"value={short_window.get('value')} threshold={short_window.get('threshold')}"
                    )
                    if short_window
                    else "   - short_window: -",
                    (
                        f"   - long_window: runs={int(long_window.get('runs', 0))} "
                        f"value={long_window.get('value')} threshold={long_window.get('threshold')}"
                    )
                    if long_window
                    else "   - long_window: -",
                    f"   - reason: {reason or '-'}",
                ]
            )
        diagnosis = stats.get("xhs_diagnosis")
        if isinstance(diagnosis, dict) and diagnosis:
            lines.extend(
                [
                    "",
                    "XHS 诊断：",
                    f"- category: {diagnosis.get('failure_category') or '-'}",
                    f"- reason: {diagnosis.get('reason') or '-'}",
                    f"- mcp_connect: {diagnosis.get('mcp_connect')}",
                    f"- login_status: {diagnosis.get('login_status')}",
                    f"- cookie_file_ready: {diagnosis.get('cookie_file_ready')}",
                ]
            )
        lines.extend(
            [
                "",
                "关键指标：",
                f"- fetch_fail_streak: {int(stats.get('fetch_fail_streak', 0))}",
                (
                    f"- llm_timeout_rate: {float(stats.get('llm_timeout_rate', 0.0) or 0.0):.1%}"
                    f" ({int(stats.get('llm_timeout_count', 0))}/{int(stats.get('llm_calls', 0))})"
                ),
                (
                    f"- detail_missing_rate: {float(stats.get('detail_missing_rate', 0.0) or 0.0):.1%}"
                    f" ({int(stats.get('detail_missing', 0))}/{int(stats.get('detail_target_notes', 0))})"
                ),
                "",
                "可在控制中心查看 run 详情与重试队列定位问题。",
            ]
        )
        return "\n".join(lines).strip()

    def _dispatch_threshold_alerts(
        self,
        *,
        run_id: str,
        mode: str,
        stats: dict[str, Any],
        triggered_alerts: list[dict[str, Any]],
    ) -> dict[str, Any]:
        if not triggered_alerts:
            return {
                "notified_codes": [],
                "suppressed_codes": [],
                "failed_codes": [],
                "channels": [],
                "send_logs_count": 0,
            }
        cfg = getattr(getattr(self.settings, "observability", None), "alerts", None)
        cooldown_minutes = max(1, int(getattr(cfg, "cooldown_minutes", 60) or 60))
        now = datetime.now(timezone.utc)
        due_alerts: list[dict[str, Any]] = []
        suppressed_codes: list[str] = []
        for item in triggered_alerts:
            code = str(item.get("code") or "").strip().lower()
            if not code:
                continue
            if self._is_alert_due(code, now, cooldown_minutes):
                due_alerts.append(item)
            else:
                suppressed_codes.append(code)

        if not due_alerts:
            if suppressed_codes:
                self.logger.info(
                    "阈值告警命中但处于冷却期 | run=%s | cooldown=%smin | codes=%s",
                    run_id,
                    cooldown_minutes,
                    ",".join(sorted(set(suppressed_codes))),
                )
            return {
                "notified_codes": [],
                "suppressed_codes": sorted(set(suppressed_codes)),
                "failed_codes": [],
                "channels": self._resolve_alert_channels(),
                "send_logs_count": 0,
            }

        channels = self._resolve_alert_channels()
        subject = f"SuccessionPilot | 阈值告警 | {run_id} | {len(due_alerts)}项"
        text = self._build_threshold_alert_message(run_id=run_id, mode=mode, stats=stats, alerts=due_alerts)
        logs = self.router.dispatch_digest(
            run_id=f"alert:{run_id}",
            subject=subject,
            text=text,
            attachments=[],
            channel_names=channels,
        )
        dispatched_ok = any(str(getattr(log, "send_status", "")).strip().lower() == "success" for log in logs)
        due_codes = sorted({str(item.get("code") or "").strip().lower() for item in due_alerts if str(item.get("code") or "").strip()})
        failed_codes: list[str] = []
        notified_codes: list[str] = []
        if dispatched_ok:
            for code in due_codes:
                self._mark_alert_sent(code, now)
            try:
                self.state.save()
            except Exception as exc:
                self.logger.warning("告警冷却状态保存失败 | run=%s | error=%s", run_id, exc)
            notified_codes = due_codes
            self.logger.warning(
                "阈值告警已发送 | run=%s | channels=%s | codes=%s",
                run_id,
                ",".join(channels),
                ",".join(notified_codes),
            )
        else:
            failed_codes = due_codes
            self.logger.warning(
                "阈值告警发送失败 | run=%s | channels=%s | codes=%s",
                run_id,
                ",".join(channels),
                ",".join(failed_codes),
            )

        dispatch_result = {
            "subject": subject,
            "body": text,
            "channels": channels,
            "attachments": [],
        }
        self._enqueue_failed_email_dispatch(run_id=run_id, send_logs=logs, dispatch_result=dispatch_result)
        return {
            "notified_codes": notified_codes,
            "suppressed_codes": sorted(set(suppressed_codes)),
            "failed_codes": failed_codes,
            "channels": channels,
            "send_logs_count": len(logs),
        }

    def _dispatch_batch_with_compat(
        self,
        *,
        run_id: str,
        mode: str,
        jobs: list[JobRecord],
        top_n: int,
        resume_text: str,
        channel_names: list[str],
        attachments: list[str],
        digest_style: bool,
    ) -> dict:
        if hasattr(self.communication, "dispatch_batch"):
            result = self.communication.dispatch_batch(
                run_id=run_id,
                mode=mode,
                jobs=jobs,
                resume_text=resume_text,
                channel_names=channel_names,
                attachments=attachments,
            )
            return {
                "logs": result.logs,
                "subject": result.subject,
                "body": result.body,
                "attachments": list(attachments),
                "channels": list(channel_names),
            }

        realtime_jobs = jobs
        if not digest_style and mode == "agent":
            realtime_jobs = sorted(jobs, key=lambda item: float(item.match_score), reverse=True)[: max(1, int(top_n))]
        summaries = self._jobs_to_summary_records(run_id=run_id, jobs=realtime_jobs)
        if digest_style:
            result = self.communication.dispatch_digest(
                run_id=run_id,
                mode=mode,
                new_notes=[],
                target_notes=[],
                summaries=summaries,
                attachments=attachments,
                channel_names=channel_names,
            )
            return {
                "logs": result.logs,
                "subject": result.subject,
                "body": result.body,
                "attachments": list(attachments),
                "channels": list(channel_names),
            }

        logs = self.communication.dispatch_realtime(
            run_id=run_id,
            summaries=summaries,
            channel_names=channel_names,
        )
        body = "\n\n".join(str(item.summary or "").strip() for item in summaries if str(item.summary or "").strip())
        return {
            "logs": logs,
            "subject": f"SuccessionPilot | realtime | {run_id}",
            "body": body,
            "attachments": list(attachments),
            "channels": list(channel_names),
        }

    def _retry_worker_loop(self) -> None:
        self.logger.info("重试队列后台线程已启动 | interval=%ss | batch=%s", self._retry_worker_interval, self._retry_batch_size)
        while not self._retry_stop.wait(self._retry_worker_interval):
            try:
                self._process_retry_queue_once(limit=self._retry_batch_size)
            except Exception as exc:
                self.logger.warning("重试队列处理异常：%s", exc)

    def _process_retry_queue_once(self, *, limit: int) -> None:
        if not self._retry_enabled:
            return
        if self.lock.path.exists():
            return
        items = self.retry_queue.pop_due(limit=max(1, int(limit)))
        if not items:
            return
        for item in items:
            item_id = str(item.get("id") or "")
            queue_type = str(item.get("queue_type") or "").strip().lower()
            action = str(item.get("action") or "").strip().lower()
            attempt = max(0, int(item.get("attempt") or 0)) + 1
            trace_id = f"rq-{item_id[:8]}-a{attempt}" if item_id else f"rq-unknown-a{attempt}"
            started = time.perf_counter()
            self.logger.info(
                "重试执行开始 | trace=%s | queue=%s | action=%s | id=%s | attempt=%s/%s",
                trace_id,
                queue_type,
                action,
                item_id,
                attempt,
                int(item.get("max_attempts") or 0),
            )
            try:
                self._handle_retry_item(item)
                duration_ms = int((time.perf_counter() - started) * 1000)
                self.retry_queue.mark_success(item_id, result="ok", duration_ms=duration_ms, trace_id=trace_id)
                self.logger.info(
                    "重试成功 | trace=%s | queue=%s | action=%s | id=%s | duration_ms=%s",
                    trace_id,
                    queue_type,
                    action,
                    item_id,
                    duration_ms,
                )
            except Exception as exc:
                duration_ms = int((time.perf_counter() - started) * 1000)
                error_code = self._classify_retry_error_code(exc)
                self.retry_queue.mark_retry(
                    item_id,
                    error=str(exc),
                    duration_ms=duration_ms,
                    trace_id=trace_id,
                    error_code=error_code,
                )
                self.logger.warning(
                    "重试失败，已回退重排 | trace=%s | queue=%s | action=%s | id=%s | code=%s | duration_ms=%s | error=%s",
                    trace_id,
                    queue_type,
                    action,
                    item_id,
                    error_code,
                    duration_ms,
                    exc,
                )

    def _handle_retry_item(self, item: dict[str, Any]) -> None:
        queue_type = str(item.get("queue_type") or "").strip().lower()
        if queue_type == "fetch":
            self._handle_retry_fetch(item)
            return
        if queue_type == "llm_timeout":
            self._handle_retry_llm_timeout(item)
            return
        if queue_type == "email":
            self._handle_retry_email(item)
            return
        raise ValueError(f"unsupported queue type: {queue_type}")

    def _handle_retry_fetch(self, item: dict[str, Any]) -> None:
        payload = item.get("payload") if isinstance(item.get("payload"), dict) else {}
        action = str(item.get("action") or "").strip().lower()
        if action == "ensure_logged_in":
            self.collector.ensure_logged_in()
            return
        if action == "search_notes":
            keyword = str(payload.get("keyword") or self.settings.xhs.keyword).strip() or self.settings.xhs.keyword
            max_results = max(1, int(payload.get("max_results") or self.settings.xhs.max_results))
            self.collector.search_notes(
                run_id=f"retry-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}",
                keyword=keyword,
                max_results=max_results,
            )
            return
        if action == "enrich_note_detail":
            note_id = str(payload.get("note_id") or "").strip()
            xsec_token = str(payload.get("xsec_token") or "").strip()
            if not note_id or not xsec_token:
                raise ValueError("missing note_id/xsec_token")
            note = NoteRecord(
                run_id=f"retry-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}",
                keyword=self.settings.xhs.keyword,
                note_id=note_id,
                title="",
                author="",
                publish_time=datetime.now(timezone.utc),
                publish_time_text="",
                like_count=0,
                comment_count=0,
                share_count=0,
                url=f"https://www.xiaohongshu.com/explore/{note_id}",
                raw_json="{}",
                xsec_token=xsec_token,
            )
            self.collector.enrich_note_details([note], max_notes=1)
            return
        raise ValueError(f"unsupported fetch action: {action}")

    def _handle_retry_llm_timeout(self, item: dict[str, Any]) -> None:
        payload = item.get("payload") if isinstance(item.get("payload"), dict) else {}
        error_code = str(payload.get("error_code") or "timeout").strip().lower()
        scope = str(payload.get("scope") or "retry_llm_timeout").strip() or "retry_llm_timeout"
        result = self.llm_client.chat_text(
            system_prompt="You are a health checker. Reply with: ok",
            user_prompt=f"llm timeout replay probe, code={error_code}",
            temperature=0.0,
            max_tokens=8,
            scope=scope,
        )
        if not result:
            raise RuntimeError(f"llm unavailable: {self.llm_client.last_error_code(scope=scope)}")

    def _handle_retry_email(self, item: dict[str, Any]) -> None:
        payload = item.get("payload") if isinstance(item.get("payload"), dict) else {}
        action = str(item.get("action") or "").strip().lower()
        if action != "dispatch_digest":
            raise ValueError(f"unsupported email action: {action}")
        subject = str(payload.get("subject") or "").strip() or "SuccessionPilot | retry"
        text = str(payload.get("body") or payload.get("text") or "").strip()
        if not text:
            raise ValueError("missing email body")
        channels = payload.get("channels") if isinstance(payload.get("channels"), list) else ["email"]
        attachments = payload.get("attachments") if isinstance(payload.get("attachments"), list) else []
        idempotency_key = str(payload.get("idempotency_key") or item.get("idempotency_key") or "").strip()
        if not idempotency_key:
            idempotency_key = self._build_email_idempotency_key(subject=subject, body=text, channels=channels)

        if self.retry_queue.has_completed_idempotency(queue_type="email", idempotency_key=idempotency_key):
            self.logger.info("重试邮件幂等跳过 | key=%s | action=%s", idempotency_key[:48], action)
            return

        logs = self.router.dispatch_digest(
            run_id=f"retry:{item.get('id')}",
            subject=subject,
            text=text,
            attachments=[str(x) for x in attachments if str(x).strip()],
            channel_names=[str(x) for x in channels if str(x).strip()],
        )
        failed = [
            log
            for log in logs
            if str(getattr(log, "channel", "")).strip().lower() == "email"
            and str(getattr(log, "send_status", "")).strip().lower() != "success"
        ]
        if failed:
            errors = "; ".join(str(getattr(log, "send_response", "") or "") for log in failed)
            raise RuntimeError(errors or "email retry failed")

    def _enqueue_retry(
        self,
        *,
        queue_type: str,
        action: str,
        run_id: str,
        error: str,
        payload: dict[str, Any] | None = None,
        dedupe_key: str = "",
        idempotency_key: str = "",
    ) -> None:
        if not self._retry_enabled:
            return
        try:
            item = self.retry_queue.enqueue(
                queue_type=queue_type,
                action=action,
                payload=payload or {},
                run_id=run_id,
                error=error,
                dedupe_key=dedupe_key,
                idempotency_key=idempotency_key,
            )
            self.logger.info(
                "重试入队 | queue=%s | action=%s | id=%s | run=%s",
                queue_type,
                action,
                item.get("id"),
                run_id,
            )
        except Exception as exc:
            self.logger.warning("重试入队失败 | queue=%s | action=%s | run=%s | error=%s", queue_type, action, run_id, exc)

    def _enqueue_failed_email_dispatch(
        self,
        *,
        run_id: str,
        send_logs: list[Any],
        dispatch_result: dict[str, Any],
    ) -> None:
        if not self._retry_enabled:
            return
        if not send_logs:
            return
        failed_email = [
            log
            for log in send_logs
            if str(getattr(log, "channel", "")).strip().lower() == "email"
            and str(getattr(log, "send_status", "")).strip().lower() != "success"
        ]
        if not failed_email:
            return
        subject = str(dispatch_result.get("subject") or "").strip()
        body = str(dispatch_result.get("body") or "").strip()
        if not subject or not body:
            return
        channels = sorted(
            {
                str(getattr(log, "channel", "")).strip()
                for log in failed_email
                if str(getattr(log, "channel", "")).strip()
            }
        )
        attachments = dispatch_result.get("attachments")
        idempotency_key = self._build_email_idempotency_key(subject=subject, body=body, channels=channels or ["email"])
        payload = {
            "subject": subject,
            "body": body,
            "channels": channels or ["email"],
            "attachments": [str(x) for x in (attachments or []) if str(x).strip()],
            "idempotency_key": idempotency_key,
        }
        self._enqueue_retry(
            queue_type="email",
            action="dispatch_digest",
            run_id=run_id,
            error="email_send_failed",
            payload=payload,
            dedupe_key=f"email-failed:{run_id}:{subject[:80]}",
            idempotency_key=idempotency_key,
        )

    def _enqueue_llm_timeout_retries(self, *, run_id: str, llm_error_codes: dict[str, int]) -> None:
        if not self._retry_enabled:
            return
        timeout_keys = {"connect_timeout", "read_timeout", "timeout"}
        for code, count in (llm_error_codes or {}).items():
            key = str(code or "").strip().lower()
            num = max(0, int(count or 0))
            if key not in timeout_keys or num <= 0:
                continue
            self._enqueue_retry(
                queue_type="llm_timeout",
                action="probe",
                run_id=run_id,
                error=f"llm_{key}:{num}",
                payload={"error_code": key, "count": num, "scope": "retry_llm_timeout"},
                dedupe_key=f"llm-timeout:{run_id}:{key}",
                idempotency_key=f"llm-timeout:{run_id}:{key}",
            )

    @staticmethod
    def _classify_retry_error_code(exc: Exception) -> str:
        text = str(exc or "").strip().lower()
        if not text:
            return "retry_failed"
        if "timeout" in text:
            return "timeout"
        if "not found" in text or "404" in text:
            return "not_found"
        if "permission" in text or "denied" in text:
            return "permission_denied"
        if "auth" in text or "login" in text or "token" in text:
            return "auth_failed"
        if "network" in text or "connection" in text or "connect" in text:
            return "network_error"
        if "smtp" in text:
            return "smtp_error"
        return "retry_failed"

    @staticmethod
    def _build_email_idempotency_key(*, subject: str, body: str, channels: list[str]) -> str:
        joined_channels = ",".join(sorted(str(x or "").strip().lower() for x in channels if str(x or "").strip()))
        source = f"{subject.strip()}|{joined_channels}|{body.strip()}"
        digest = hashlib.sha1(source.encode("utf-8", errors="ignore")).hexdigest()
        return f"email:{digest}"

    def _probe_xhs_fetch_failure(self, *, run_id: str, fetch_fail_events: list[dict[str, str]]) -> dict[str, Any]:
        try:
            diagnosis = self.collector.probe_status_diagnostics()
            joined_errors = " | ".join(str(item.get("error") or "") for item in (fetch_fail_events or []))
            category = "unknown_fetch_failure"
            if any(k in joined_errors.lower() for k in ("risk", "风控", "访问受限", "网络环境")):
                category = "risk_control"
            elif not diagnosis.get("mcp_connect"):
                category = "mcp_unreachable"
            elif not diagnosis.get("login_status"):
                category = "not_logged_in"
            diagnosis["run_id"] = run_id
            diagnosis["fetch_fail_streak"] = int(self._fetch_fail_streak)
            diagnosis["fetch_fail_events"] = list(fetch_fail_events or [])
            diagnosis["failure_category"] = category
            self.logger.warning(
                "XHS 失败诊断 | run=%s | streak=%s | category=%s | mcp=%s | login=%s | cookie=%s | reason=%s",
                run_id,
                self._fetch_fail_streak,
                category,
                diagnosis.get("mcp_connect"),
                diagnosis.get("login_status"),
                diagnosis.get("cookie_file_ready"),
                diagnosis.get("reason"),
            )
            return diagnosis
        except Exception as exc:
            self.logger.warning("XHS 失败诊断执行异常 | run=%s | error=%s", run_id, exc)
            return {
                "run_id": run_id,
                "fetch_fail_streak": int(self._fetch_fail_streak),
                "fetch_fail_events": list(fetch_fail_events or []),
                "error": str(exc)[:280],
            }

    def _build_retry_dispatch_fallback(
        self,
        *,
        run_id: str,
        mode: str,
        jobs: list[JobRecord],
        channels: list[str],
        attachments: list[str],
        reason: str,
    ) -> dict[str, Any]:
        subject = ""
        body = ""
        builder = getattr(self.communication, "build_retry_fallback_message", None)
        if callable(builder):
            try:
                built_subject, built_body = builder(
                    run_id=run_id,
                    mode=mode,
                    jobs=jobs,
                    attachments=attachments,
                    reason=reason,
                )
                subject = str(built_subject or "").strip()
                body = str(built_body or "").strip()
            except Exception:
                subject = ""
                body = ""

        if not subject:
            subject = f"SuccessionPilot | notification retry | {run_id}"
        if not body:
            lines = [
                "SuccessionPilot 通知重试回退",
                "========================================",
                f"运行ID：{run_id}",
                f"运行模式：{mode}",
                f"岗位数量：{len(jobs)}",
                f"原因：{reason}",
            ]
            body = "\n".join(lines)
        return {
            "logs": [],
            "subject": subject,
            "body": body,
            "attachments": list(attachments),
            "channels": list(channels),
        }

    def _jobs_to_summary_records(self, run_id: str, jobs: list[JobRecord]) -> list[SummaryRecord]:
        output: list[SummaryRecord] = []
        for item in jobs:
            requirements = (item.requirements or "").strip()
            original_text = self._build_original_text_summary(item)
            summary_text = (
                f"公司：{item.company}\n"
                f"岗位：{item.position}\n"
                f"地点：{item.location}\n"
                f"岗位要求：{requirements or '未提取到明确要求'}\n"
                f"到岗时间：{item.arrival_time}\n"
                f"投递方式：{item.application_method}\n"
                f"风险等级：{item.risk_line}\n"
                f"简历匹配度：{item.match_score:.2f}\n"
                f"原文：{original_text}"
            )
            output.append(
                SummaryRecord(
                    run_id=run_id,
                    note_id=item.post_id,
                    keyword=self.settings.xhs.keyword,
                    publish_time=item.publish_time,
                    title=item.source_title or item.position,
                    author=item.author,
                    summary=summary_text,
                    confidence=1.0,
                    risk_flags=item.risk_line,
                    url=item.link,
                )
            )
        return output

    @classmethod
    def _build_original_text_summary(cls, item: JobRecord) -> str:
        original_text = str(item.original_text or "").strip()
        requirements = str(item.requirements or "").strip()
        if original_text:
            if cls._is_duplicate_text(original_text, requirements):
                return "原文与岗位要求高度重合，建议查看原帖链接获取完整上下文。"
            return original_text

        fallbacks: list[str] = []
        title = str(item.source_title or "").strip()
        comments = str(item.comments_preview or "").strip()
        if title:
            fallbacks.append(f"标题：{title}")
        if comments:
            fallbacks.append(f"评论线索：{comments}")
        if fallbacks:
            return "；".join(fallbacks)[:700]
        return "未抓取到可用原文摘要，请查看原帖链接/图片。"

    @staticmethod
    def _is_duplicate_text(a: str, b: str) -> bool:
        left = PipelineServiceMixin._normalize_compare_text(a)
        right = PipelineServiceMixin._normalize_compare_text(b)
        if not left or not right:
            return False
        if left == right:
            return True
        short, long = (left, right) if len(left) <= len(right) else (right, left)
        if len(short) >= 24 and short in long:
            overlap = len(short) / max(1, len(long))
            return overlap >= 0.7
        return False

    @staticmethod
    def _normalize_compare_text(text: str) -> str:
        value = str(text or "").lower().strip()
        if not value:
            return ""
        value = "".join(ch for ch in value if ch.isalnum() or "\u4e00" <= ch <= "\u9fff")
        return value

    def _summaries_to_jobs(self, summaries: list[SummaryRecord]) -> list[JobRecord]:
        jobs: list[JobRecord] = []
        for item in summaries:
            jobs.append(
                JobRecord(
                    run_id=item.run_id,
                    post_id=item.note_id,
                    company="",
                    position=item.title or "",
                    location="",
                    requirements=item.summary or "",
                    link=item.url,
                    publish_time=item.publish_time,
                    source_title=item.title,
                    comment_count=0,
                    comments_preview="",
                    original_text=item.summary or "",
                    author=item.author,
                    risk_line=item.risk_flags or "low",
                    match_score=0.0,
                    mode=self._normalize_mode(self.settings.agent.mode or "auto"),
                )
            )
        return jobs

    @staticmethod
    def _summarize_stage_timing(stage_records: list[dict[str, Any]]) -> dict[str, Any]:
        normalized: list[dict[str, Any]] = []
        failed_count = 0
        total_ms = 0

        for item in stage_records or []:
            name = str(item.get("name") or "").strip()
            status = str(item.get("status") or "").strip().lower()
            try:
                duration_ms = int(item.get("duration_ms") or 0)
            except Exception:
                duration_ms = 0
            duration_ms = max(0, duration_ms)
            total_ms += duration_ms
            if status == "failed":
                failed_count += 1
            normalized.append(
                {
                    "name": name,
                    "duration_ms": duration_ms,
                    "status": status or "success",
                }
            )

        count = len(normalized)
        avg_ms = int(total_ms / count) if count > 0 else 0
        top = sorted(normalized, key=lambda x: int(x.get("duration_ms") or 0), reverse=True)[:3]
        slowest = top[0] if top else {"name": "", "duration_ms": 0, "status": ""}

        return {
            "total_ms": total_ms,
            "avg_ms": avg_ms,
            "failed_count": failed_count,
            "slowest": slowest,
            "top_slow": top,
        }

    @staticmethod
    def _collect_stage_error_codes(stage_records: list[dict[str, Any]]) -> dict[str, int]:
        counters: dict[str, int] = {}
        for item in stage_records or []:
            status = str(item.get("status") or "").strip().lower()
            if status != "failed":
                continue
            code = str(item.get("error_code") or "").strip().lower() or "stage_failed"
            counters[code] = int(counters.get(code, 0)) + 1
        return counters
