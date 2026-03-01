from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


@dataclass
class AppConfig:
    timezone: str = "Asia/Shanghai"
    log_level: str = "INFO"
    interval_minutes: int = 15


@dataclass
class XHSConfig:
    command: str = "node"
    args: list[str] | None = None
    browser_path: str = "C:/Program Files/Google/Chrome/Application/chrome.exe"
    account: str = "default"
    account_cookies_dir: str = "~/.xhs-mcp/accounts"
    search_sort: str = "time_descending"
    keyword: str = "继任"
    max_results: int = 20
    max_detail_fetch: int = 5
    detail_workers: int = 3
    login_timeout_seconds: int = 180
    command_timeout_seconds: int = 120


@dataclass
class PipelineConfig:
    min_confidence: float = 0.55
    process_workers: int = 4


@dataclass
class LLMConfig:
    enabled: bool = False
    provider: str = "openai_compatible"
    model: str = "gpt-5-mini"
    parse_model: str = ""
    outreach_model: str = ""
    api_key: str = ""
    api_key_env: str = "OPENAI_API_KEY"
    base_url: str = "https://api.openai.com/v1"
    timeout_seconds: int = 45
    request_timeout_seconds: int = 20
    connect_timeout_seconds: int = 8
    max_retries: int = 1
    retry_backoff_seconds: float = 0.6
    failure_threshold: int = 2
    cooldown_seconds: int = 120
    max_tokens: int = 900
    temperature: float = 0.2
    enabled_for_jobs: bool = True
    enabled_for_summary: bool = True
    enabled_for_filter: bool = True
    enabled_for_outreach: bool = True
    max_job_items: int = 8
    max_summary_items: int = 8
    max_filter_items: int = 20
    single_pass_extract: bool = True
    filter_threshold: float = 0.62
    strict_filter: bool = True


@dataclass
class WeChatServiceConfig:
    enabled: bool = False
    app_id_env: str = "WECHAT_SERVICE_APP_ID"
    app_secret_env: str = "WECHAT_SERVICE_APP_SECRET"
    openids_env: str = "WECHAT_SERVICE_OPENIDS"


@dataclass
class StorageConfig:
    excel_path: str = "data/output.xlsx"
    jobs_csv_path: str = "data/jobs.csv"
    state_path: str = "data/state.json"
    retry_queue_path: str = "data/retry_queue.json"


@dataclass
class ResumeConfig:
    source_txt_path: str = "config/resume.txt"
    resume_text_path: str = "data/resume_text.txt"
    max_chars: int = 6000


@dataclass
class AgentConfig:
    runtime_name: str = "SuccessionPilot"
    mode: str = "auto"
    # new fields
    agent_full_detail_fetch: bool = True
    agent_send_top_n: int = 5
    agent_include_jd_full: bool = True
    # backward-compatible aliases
    smart_full_detail_fetch: bool = True
    smart_send_top_n: int = 3
    smart_include_jd_full: bool = True
    global_memory_path: str = "groups/global/CLAUDE.md"
    main_memory_path: str = "groups/main/CLAUDE.md"
    memory_max_chars: int = 4000


@dataclass
class NotificationConfig:
    mode: str = "digest"  # digest | realtime | off
    digest_interval_minutes: int = 30
    digest_min_new_notes: int = 1
    digest_send_when_no_new: bool = False
    digest_top_summaries: int = 5
    digest_channels: list[str] = field(default_factory=lambda: ["email"])
    realtime_channels: list[str] = field(default_factory=lambda: ["wechat_service", "email"])
    attach_excel: bool = False
    attach_jobs_csv: bool = False


@dataclass
class RetryConfig:
    enabled: bool = True
    worker_interval_seconds: int = 12
    replay_batch_size: int = 3
    fetch_max_attempts: int = 3
    llm_timeout_max_attempts: int = 3
    email_max_attempts: int = 4
    base_backoff_seconds: int = 20
    max_backoff_seconds: int = 1200


@dataclass
class AlertThresholdConfig:
    enabled: bool = True
    channels: list[str] = field(default_factory=list)
    cooldown_minutes: int = 60
    # Legacy single-threshold fields (kept for backward compatibility)
    fetch_fail_streak_threshold: int = 2
    llm_timeout_rate_threshold: float = 0.35
    llm_timeout_min_calls: int = 6
    detail_missing_rate_threshold: float = 0.45
    detail_missing_min_samples: int = 6
    # Dual-window fields (short window + long window)
    fetch_fail_streak: dict[str, Any] = field(default_factory=dict)
    llm_timeout_rate: dict[str, Any] = field(default_factory=dict)
    detail_missing_rate: dict[str, Any] = field(default_factory=dict)


@dataclass
class ObservabilityConfig:
    alerts: AlertThresholdConfig = field(default_factory=AlertThresholdConfig)


@dataclass
class EmailConfig:
    enabled: bool = False
    smtp_host: str = "smtp.126.com"
    smtp_port: int = 465
    use_ssl: bool = True
    username_env: str = "EMAIL_SMTP_USERNAME"
    password_env: str = "EMAIL_SMTP_PASSWORD"
    from_env: str = "EMAIL_FROM"
    to_env: str = "EMAIL_TO"


@dataclass
class Settings:
    app: AppConfig
    xhs: XHSConfig
    pipeline: PipelineConfig
    llm: LLMConfig
    wechat_service: WeChatServiceConfig
    email: EmailConfig
    storage: StorageConfig
    resume: ResumeConfig = field(default_factory=ResumeConfig)
    agent: AgentConfig = field(default_factory=AgentConfig)
    notification: NotificationConfig = field(default_factory=NotificationConfig)
    retry: RetryConfig = field(default_factory=RetryConfig)
    observability: ObservabilityConfig = field(default_factory=ObservabilityConfig)

    @property
    def wechat_app_id(self) -> str:
        return (os.getenv(self.wechat_service.app_id_env, "") or "").strip()

    @property
    def wechat_app_secret(self) -> str:
        return (os.getenv(self.wechat_service.app_secret_env, "") or "").strip()

    @property
    def wechat_openids(self) -> list[str]:
        raw = (os.getenv(self.wechat_service.openids_env, "") or "").strip()
        if not raw:
            return []
        return [item.strip() for item in raw.split(",") if item.strip()]

    @property
    def email_username(self) -> str:
        return (os.getenv(self.email.username_env, "") or "").strip()

    @property
    def email_password(self) -> str:
        return (os.getenv(self.email.password_env, "") or "").strip()

    @property
    def email_from(self) -> str:
        return (os.getenv(self.email.from_env, "") or "").strip()

    @property
    def email_to(self) -> list[str]:
        raw = (os.getenv(self.email.to_env, "") or "").strip()
        if not raw:
            return []
        return [item.strip() for item in raw.split(",") if item.strip()]

    @property
    def llm_api_key(self) -> str:
        direct = (self.llm.api_key or "").strip()
        if direct:
            return direct

        env_name = (self.llm.api_key_env or "").strip()
        if not env_name:
            return ""

        # Backward-compatible fallback:
        # if user mistakenly put a literal key in api_key_env, still accept it.
        if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", env_name):
            return (os.getenv(env_name, "") or "").strip()
        return env_name


def _section(data: dict[str, Any], key: str) -> dict[str, Any]:
    value = data.get(key, {})
    return value if isinstance(value, dict) else {}


def _load_env_file(path: Path) -> None:
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        text = line.strip()
        if not text or text.startswith("#") or "=" not in text:
            continue
        name, value = text.split("=", 1)
        name = name.strip()
        value = value.strip().strip("\"'")
        if name and name not in os.environ:
            os.environ[name] = value



def _default_xhs_args() -> list[str]:
    local = Path(__file__).resolve().parents[2] / "vendor" / "xhs-mcp" / "dist" / "xhs-mcp.js"
    if local.exists():
        return [str(local)]
    return ["vendor/xhs-mcp/dist/xhs-mcp.js"]


def _normalize_xhs_args(args: list[str] | None) -> list[str]:
    items = [str(item).strip() for item in (args or []) if str(item).strip()]
    if not items:
        return _default_xhs_args()

    first = Path(items[0])
    if not first.exists():
        local = Path(__file__).resolve().parents[2] / "vendor" / "xhs-mcp" / "dist" / "xhs-mcp.js"
        if local.exists():
            items[0] = str(local)
    return items


def _autofix_browser_path(path_text: str) -> str:
    configured = str(path_text or "").strip()
    if configured and Path(configured).exists():
        return configured

    candidates = [
        os.getenv("CHROME_PATH", "").strip(),
        "C:/Program Files/Google/Chrome/Application/chrome.exe",
        "C:/Program Files (x86)/Google/Chrome/Application/chrome.exe",
        "C:/Program Files/Microsoft/Edge/Application/msedge.exe",
        "C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe",
    ]
    for item in candidates:
        if item and Path(item).exists():
            return item
    return configured or "C:/Program Files/Google/Chrome/Application/chrome.exe"


def _as_int(value: Any, default: int, *, minimum: int | None = None) -> int:
    try:
        parsed = int(value)
    except Exception:
        parsed = int(default)
    if minimum is not None:
        parsed = max(int(minimum), parsed)
    return parsed


def _as_rate(value: Any, default: float) -> float:
    try:
        parsed = float(value)
    except Exception:
        parsed = float(default)
    if parsed > 1.0 and parsed <= 100.0:
        parsed = parsed / 100.0
    if parsed < 0.0:
        return 0.0
    if parsed > 1.0:
        return 1.0
    return parsed


def _as_float(value: Any, default: float, *, minimum: float | None = None) -> float:
    try:
        parsed = float(value)
    except Exception:
        parsed = float(default)
    if minimum is not None:
        parsed = max(float(minimum), parsed)
    return parsed


def _load_fetch_dual_window(raw: dict[str, Any], *, legacy_threshold: int) -> dict[str, Any]:
    short_threshold_default = max(1, int(legacy_threshold))
    long_threshold_default = max(1.0, float(short_threshold_default) * 0.6)
    return {
        "short_window_runs": _as_int(raw.get("short_window_runs"), 1, minimum=1),
        "short_threshold": _as_int(raw.get("short_threshold"), short_threshold_default, minimum=1),
        "short_min_runs": _as_int(raw.get("short_min_runs"), 1, minimum=1),
        "long_window_runs": _as_int(raw.get("long_window_runs"), 6, minimum=1),
        "long_threshold": _as_float(raw.get("long_threshold"), long_threshold_default, minimum=1.0),
        "long_min_runs": _as_int(raw.get("long_min_runs"), 3, minimum=1),
    }


def _load_rate_dual_window(
    raw: dict[str, Any],
    *,
    legacy_threshold: float,
    legacy_min_samples: int,
    default_long_window_runs: int,
) -> dict[str, Any]:
    short_threshold_default = _as_rate(legacy_threshold, legacy_threshold)
    long_threshold_default = _as_rate(short_threshold_default * 0.7, short_threshold_default)
    short_min_samples_default = max(1, int(legacy_min_samples))
    long_min_samples_default = max(12, short_min_samples_default * 3)
    return {
        "short_window_runs": _as_int(raw.get("short_window_runs"), 1, minimum=1),
        "short_threshold": _as_rate(raw.get("short_threshold"), short_threshold_default),
        "short_min_samples": _as_int(raw.get("short_min_samples"), short_min_samples_default, minimum=1),
        "long_window_runs": _as_int(raw.get("long_window_runs"), default_long_window_runs, minimum=1),
        "long_threshold": _as_rate(raw.get("long_threshold"), long_threshold_default),
        "long_min_samples": _as_int(raw.get("long_min_samples"), long_min_samples_default, minimum=1),
    }


def load_settings(config_path: str) -> Settings:
    path = Path(config_path)
    if not path.exists():
        raise FileNotFoundError(f"Config not found: {path}")

    _load_env_file(Path(".env"))
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        raise ValueError("Config root must be a mapping")

    app = AppConfig(**_section(data, "app"))
    xhs_raw = _section(data, "xhs")
    xhs = XHSConfig(**xhs_raw)
    xhs.args = _normalize_xhs_args(xhs.args)
    xhs.browser_path = _autofix_browser_path(xhs.browser_path)
    xhs.account = str(xhs.account or "default").strip() or "default"
    xhs.account_cookies_dir = str(xhs.account_cookies_dir or "~/.xhs-mcp/accounts").strip() or "~/.xhs-mcp/accounts"

    pipeline = PipelineConfig(**_section(data, "pipeline"))
    llm = LLMConfig(**_section(data, "llm"))
    wechat = WeChatServiceConfig(**_section(data, "wechat_service"))
    email = EmailConfig(**_section(data, "email"))
    storage = StorageConfig(**_section(data, "storage"))
    resume = ResumeConfig(**_section(data, "resume"))
    agent = AgentConfig(**_section(data, "agent"))
    notification = NotificationConfig(**_section(data, "notification"))
    retry = RetryConfig(**_section(data, "retry"))
    observability_raw = _section(data, "observability")
    alerts_raw = _section(observability_raw, "alerts")
    fetch_fail_streak_threshold = _as_int(alerts_raw.get("fetch_fail_streak_threshold"), 2, minimum=1)
    llm_timeout_rate_threshold = _as_rate(alerts_raw.get("llm_timeout_rate_threshold"), 0.35)
    llm_timeout_min_calls = _as_int(alerts_raw.get("llm_timeout_min_calls"), 6, minimum=1)
    detail_missing_rate_threshold = _as_rate(alerts_raw.get("detail_missing_rate_threshold"), 0.45)
    detail_missing_min_samples = _as_int(alerts_raw.get("detail_missing_min_samples"), 6, minimum=1)
    observability = ObservabilityConfig(
        alerts=AlertThresholdConfig(
            enabled=bool(alerts_raw.get("enabled", True)),
            channels=_as_name_list(alerts_raw.get("channels"), default=[]),
            cooldown_minutes=_as_int(alerts_raw.get("cooldown_minutes"), 60, minimum=1),
            fetch_fail_streak_threshold=fetch_fail_streak_threshold,
            llm_timeout_rate_threshold=llm_timeout_rate_threshold,
            llm_timeout_min_calls=llm_timeout_min_calls,
            detail_missing_rate_threshold=detail_missing_rate_threshold,
            detail_missing_min_samples=detail_missing_min_samples,
            fetch_fail_streak=_load_fetch_dual_window(
                _section(alerts_raw, "fetch_fail_streak"),
                legacy_threshold=fetch_fail_streak_threshold,
            ),
            llm_timeout_rate=_load_rate_dual_window(
                _section(alerts_raw, "llm_timeout_rate"),
                legacy_threshold=llm_timeout_rate_threshold,
                legacy_min_samples=llm_timeout_min_calls,
                default_long_window_runs=8,
            ),
            detail_missing_rate=_load_rate_dual_window(
                _section(alerts_raw, "detail_missing_rate"),
                legacy_threshold=detail_missing_rate_threshold,
                legacy_min_samples=detail_missing_min_samples,
                default_long_window_runs=8,
            ),
        )
    )
    notification.digest_channels = _as_name_list(notification.digest_channels, default=["email"])
    notification.realtime_channels = _as_name_list(notification.realtime_channels, default=["wechat_service", "email"])
    observability.alerts.channels = _as_name_list(observability.alerts.channels, default=[])

    # Backward-compatible mode aliases.
    agent.mode = (agent.mode or "auto").strip().lower()
    if agent.mode == "smart":
        agent.mode = "agent"
    if agent.mode not in {"auto", "agent"}:
        agent.mode = "auto"

    # Backward-compatible field aliases.
    if "agent_full_detail_fetch" not in _section(data, "agent"):
        agent.agent_full_detail_fetch = bool(agent.smart_full_detail_fetch)
    if "agent_send_top_n" not in _section(data, "agent"):
        agent.agent_send_top_n = int(agent.smart_send_top_n)
    if "agent_include_jd_full" not in _section(data, "agent"):
        agent.agent_include_jd_full = bool(agent.smart_include_jd_full)

    return Settings(
        app=app,
        xhs=xhs,
        pipeline=pipeline,
        llm=llm,
        wechat_service=wechat,
        email=email,
        storage=storage,
        resume=resume,
        agent=agent,
        notification=notification,
        retry=retry,
        observability=observability,
    )


def _as_name_list(value, default: list[str]) -> list[str]:
    if isinstance(value, list):
        items = [str(item).strip() for item in value if str(item).strip()]
        return items or list(default)
    if isinstance(value, str) and value.strip():
        parts = [part.strip() for part in value.split(",") if part.strip()]
        return parts or list(default)
    return list(default)

