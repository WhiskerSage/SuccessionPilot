from __future__ import annotations

import json
import subprocess
import sys
import threading
from collections import deque
from datetime import datetime
from pathlib import Path
from typing import Any

from openpyxl import load_workbook
import yaml


class RuntimeManager:
    def __init__(self, workspace: Path, config_path: Path) -> None:
        self.workspace = workspace
        self.config_path = config_path
        self._lock = threading.Lock()

        self._job_thread: threading.Thread | None = None
        self._job_proc: subprocess.Popen[str] | None = None
        self._job_logs: deque[str] = deque(maxlen=240)
        self._job_state: dict[str, Any] = {
            "running": False,
            "name": "",
            "started_at": "",
            "finished_at": "",
            "ok": None,
            "exit_code": None,
            "message": "",
            "log_tail": [],
        }

        self._daemon_proc: subprocess.Popen[str] | None = None
        self._daemon_reader: threading.Thread | None = None
        self._daemon_logs: deque[str] = deque(maxlen=360)
        self._daemon_started_at: str = ""
        self._daemon_last_exit: int | None = None
        self._daemon_cmd: list[str] = []

    def _now_iso(self) -> str:
        return datetime.now().isoformat(timespec="seconds")

    def _resolve_python(self) -> str:
        if sys.platform.startswith("win"):
            venv_python = self.workspace / ".venv" / "Scripts" / "python.exe"
        else:
            venv_python = self.workspace / ".venv" / "bin" / "python"
        if venv_python.exists():
            return str(venv_python)
        return sys.executable

    @staticmethod
    def _resolve_powershell() -> str:
        if sys.platform.startswith("win"):
            return "powershell"
        return "pwsh"

    def _build_main_command(
        self,
        *,
        run_once: bool = False,
        daemon: bool = False,
        mode: str | None = None,
        interval_minutes: int | None = None,
        send_latest: int | None = None,
    ) -> list[str]:
        command = [self._resolve_python(), "-m", "auto_successor.main", "--config", str(self.config_path)]
        if run_once:
            command.append("--run-once")
        if daemon:
            command.append("--daemon")
        if mode:
            command.extend(["--mode", mode])
        if interval_minutes and interval_minutes > 0:
            command.extend(["--interval-minutes", str(interval_minutes)])
        if send_latest and send_latest > 0:
            command.extend(["--send-latest", str(send_latest)])
        return command

    def _start_job(self, name: str, command: list[str]) -> dict[str, Any]:
        blocked_message = ""
        with self._lock:
            if self._job_state.get("running"):
                blocked_message = f"已有任务运行中: {self._job_state.get('name')}"
            else:
                self._job_logs.clear()
                self._job_state = {
                    "running": True,
                    "name": name,
                    "started_at": self._now_iso(),
                    "finished_at": "",
                    "ok": None,
                    "exit_code": None,
                    "message": f"{name} 已启动",
                    "log_tail": [],
                }
                self._job_thread = threading.Thread(target=self._run_job, args=(name, command), daemon=True)
                self._job_thread.start()

        if blocked_message:
            return {"ok": False, "message": blocked_message, "runtime": self.status()}

        return {"ok": True, "message": f"{name} 已启动", "runtime": self.status()}

    def _run_job(self, name: str, command: list[str]) -> None:
        ok = False
        exit_code: int | None = None
        message = ""

        try:
            proc = subprocess.Popen(
                command,
                cwd=str(self.workspace),
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
            )
        except Exception as exc:
            with self._lock:
                self._job_logs.append(f"任务启动失败: {exc}")
                self._job_state = {
                    "running": False,
                    "name": name,
                    "started_at": self._job_state.get("started_at", self._now_iso()),
                    "finished_at": self._now_iso(),
                    "ok": False,
                    "exit_code": -1,
                    "message": f"任务启动失败: {exc}",
                    "log_tail": list(self._job_logs),
                }
            return

        with self._lock:
            self._job_proc = proc
            self._job_logs.append("$ " + " ".join(command))
            self._job_state["log_tail"] = list(self._job_logs)

        try:
            if proc.stdout is not None:
                for raw in proc.stdout:
                    line = raw.rstrip()
                    if not line:
                        continue
                    with self._lock:
                        self._job_logs.append(line)
                        self._job_state["log_tail"] = list(self._job_logs)

            exit_code = proc.wait()
            ok = exit_code == 0
            message = "任务完成" if ok else f"任务失败，退出码 {exit_code}"
        except Exception as exc:
            exit_code = -1
            ok = False
            message = f"任务异常: {exc}"
            with self._lock:
                self._job_logs.append(message)
                self._job_state["log_tail"] = list(self._job_logs)
        finally:
            with self._lock:
                self._job_proc = None
                self._job_state = {
                    "running": False,
                    "name": name,
                    "started_at": self._job_state.get("started_at", self._now_iso()),
                    "finished_at": self._now_iso(),
                    "ok": ok,
                    "exit_code": exit_code,
                    "message": message,
                    "log_tail": list(self._job_logs),
                }

    def start_run_once(self, mode: str = "auto") -> dict[str, Any]:
        command = self._build_main_command(run_once=True, mode=mode)
        return self._start_job(name="单次抓取", command=command)

    def start_send_latest(self, limit: int = 5) -> dict[str, Any]:
        limit = max(1, int(limit))
        command = self._build_main_command(send_latest=limit)
        return self._start_job(name=f"发送最新 {limit} 条", command=command)

    def start_xhs_login(self, timeout_seconds: int = 180) -> dict[str, Any]:
        script = self.workspace / "scripts" / "xhs_login.ps1"
        command = [
            self._resolve_powershell(),
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(script),
            "-Timeout",
            str(max(30, int(timeout_seconds))),
        ]
        return self._start_job(name="XHS 扫码登录", command=command)

    def check_xhs_status(self) -> dict[str, Any]:
        script = self.workspace / "scripts" / "xhs_status.ps1"
        command = [
            self._resolve_powershell(),
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(script),
        ]
        try:
            result = subprocess.run(
                command,
                cwd=str(self.workspace),
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=90,
            )
            raw = "\n".join([result.stdout.strip(), result.stderr.strip()]).strip()
            parsed: dict[str, Any] | None = None
            for line in reversed([x for x in raw.splitlines() if x.strip()]):
                text = line.strip()
                if not text.startswith("{"):
                    continue
                try:
                    maybe = json.loads(text)
                except Exception:
                    continue
                if isinstance(maybe, dict):
                    parsed = maybe
                    break
            return {
                "ok": result.returncode == 0,
                "exit_code": result.returncode,
                "message": "状态检查成功" if result.returncode == 0 else f"状态检查失败，退出码 {result.returncode}",
                "status": parsed or {},
                "output": raw[-1200:],
                "runtime": self.status(),
            }
        except Exception as exc:
            return {"ok": False, "message": f"状态检查异常: {exc}", "status": {}, "output": "", "runtime": self.status()}

    def start_daemon(self, mode: str = "auto", interval_minutes: int | None = None) -> dict[str, Any]:
        already_running = False
        with self._lock:
            if self._daemon_proc and self._daemon_proc.poll() is None:
                already_running = True
        if already_running:
            return {"ok": False, "message": "自动运行已在执行", "runtime": self.status()}

        command = self._build_main_command(daemon=True, mode=mode, interval_minutes=interval_minutes)
        try:
            proc = subprocess.Popen(
                command,
                cwd=str(self.workspace),
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
            )
        except Exception as exc:
            return {"ok": False, "message": f"启动自动运行失败: {exc}", "runtime": self.status()}

        with self._lock:
            self._daemon_proc = proc
            self._daemon_started_at = self._now_iso()
            self._daemon_last_exit = None
            self._daemon_cmd = list(command)
            self._daemon_logs.clear()
            self._daemon_logs.append("$ " + " ".join(command))
            self._daemon_reader = threading.Thread(target=self._drain_daemon_output, args=(proc,), daemon=True)
            self._daemon_reader.start()

        return {"ok": True, "message": "自动运行已启动", "runtime": self.status()}

    def _drain_daemon_output(self, proc: subprocess.Popen[str]) -> None:
        if proc.stdout is None:
            return
        for raw in proc.stdout:
            line = raw.rstrip()
            if not line:
                continue
            with self._lock:
                self._daemon_logs.append(line)
        with self._lock:
            if self._daemon_proc is proc:
                self._daemon_last_exit = proc.poll()

    def stop_daemon(self) -> dict[str, Any]:
        no_daemon = False
        with self._lock:
            proc = self._daemon_proc
            if not proc or proc.poll() is not None:
                self._daemon_proc = None
                no_daemon = True
        if no_daemon:
            return {"ok": False, "message": "自动运行未在执行", "runtime": self.status()}

        try:
            proc.terminate()
            proc.wait(timeout=8)
        except Exception:
            try:
                proc.kill()
            except Exception:
                pass

        with self._lock:
            self._daemon_last_exit = proc.poll()
            self._daemon_logs.append(f"[{self._now_iso()}] 自动运行已停止")
            self._daemon_proc = None

        return {"ok": True, "message": "自动运行已停止", "runtime": self.status()}

    def stop_job(self) -> dict[str, Any]:
        no_job = False
        with self._lock:
            proc = self._job_proc
            if not proc or proc.poll() is not None:
                no_job = True
        if no_job:
            return {"ok": False, "message": "当前没有运行中的任务", "runtime": self.status()}

        try:
            proc.terminate()
        except Exception as exc:
            return {"ok": False, "message": f"停止任务失败: {exc}", "runtime": self.status()}
        return {"ok": True, "message": "已请求停止当前任务", "runtime": self.status()}

    def _job_view(self) -> dict[str, Any]:
        with self._lock:
            return dict(self._job_state)

    def _daemon_view(self) -> dict[str, Any]:
        with self._lock:
            proc = self._daemon_proc
            running = bool(proc and proc.poll() is None)
            return {
                "running": running,
                "pid": proc.pid if running else None,
                "started_at": self._daemon_started_at,
                "exit_code": None if running else self._daemon_last_exit,
                "command": list(self._daemon_cmd),
                "log_tail": list(self._daemon_logs),
            }

    def status(self) -> dict[str, Any]:
        return {"job": self._job_view(), "daemon": self._daemon_view(), "updated_at": self._now_iso()}


class DataBackend:
    def __init__(self, workspace: Path) -> None:
        self.workspace = workspace
        self.data_dir = workspace / "data"
        self.runs_dir = self.data_dir / "runs"
        self.excel_path = self.data_dir / "output.xlsx"
        self.config_path = workspace / "config" / "config.yaml"
        self.runtime = RuntimeManager(workspace=workspace, config_path=self.config_path)

    def load_summary(self) -> dict[str, Any]:
        rows = self._load_workbook_rows()
        raw = rows.get("raw_notes", [])
        summaries = rows.get("succession_summary", [])
        jobs = rows.get("jobs", [])
        sends = rows.get("send_log", [])
        runs = self._load_runs(limit=1)

        latest_run_id = runs[0]["run_id"] if runs else ""
        latest_run_time = runs[0]["recorded_at"] if runs else ""

        return {
            "raw_count": len(raw),
            "summary_count": len(summaries),
            "jobs_count": len(jobs),
            "send_count": len(sends),
            "latest_run_id": latest_run_id,
            "latest_run_time": latest_run_time,
            "digest_interval_minutes": self._read_digest_interval(),
        }

    def _build_merged_leads(self, q: str = "", summary_only: bool = False) -> list[dict[str, Any]]:
        rows = self._load_workbook_rows()
        raw = rows.get("raw_notes", [])
        summaries = rows.get("succession_summary", [])
        jobs = rows.get("jobs", [])

        by_summary = {str(x.get("note_id") or ""): x for x in summaries}
        by_job = {str(x.get("PostID") or ""): x for x in jobs}

        merged: list[dict[str, Any]] = []
        for item in raw:
            note_id = str(item.get("note_id") or "")
            if not note_id:
                continue

            summary = by_summary.get(note_id, {})
            job = by_job.get(note_id, {})

            like_count = self._to_int(item.get("like_count"))
            comment_count = self._to_int(item.get("comment_count"))
            publish_ts = self._to_int(item.get("publish_timestamp"))
            status = self._resolve_status(
                like_count=like_count,
                comment_count=comment_count,
                has_summary=bool(summary),
                has_job=bool(job),
            )

            merged.append(
                {
                    "note_id": note_id,
                    "publish_time": str(item.get("publish_time") or ""),
                    "publish_time_text": str(item.get("publish_time_text") or ""),
                    "publish_timestamp": publish_ts,
                    "title": str(item.get("title") or ""),
                    "author": str(item.get("author") or ""),
                    "like_count": like_count,
                    "comment_count": comment_count,
                    "share_count": self._to_int(item.get("share_count")),
                    "url": str(item.get("url") or ""),
                    "detail_text": str(item.get("detail_text") or ""),
                    "comments_preview": str(item.get("comments_preview") or ""),
                    "summary": str(summary.get("summary") or ""),
                    "risk_flags": str(summary.get("risk_flags") or ""),
                    "company": str(job.get("Company") or ""),
                    "position": str(job.get("Position") or ""),
                    "location": str(job.get("Location") or ""),
                    "requirements": str(job.get("Requirements") or ""),
                    "status": status,
                }
            )

        merged.sort(key=lambda x: int(x.get("publish_timestamp") or 0), reverse=True)

        if summary_only:
            merged = [row for row in merged if str(row.get("summary") or "").strip()]

        if q:
            key = q.strip().lower()
            merged = [
                row
                for row in merged
                if key
                in " ".join(
                    [
                        str(row.get("title") or ""),
                        str(row.get("author") or ""),
                        str(row.get("summary") or ""),
                        str(row.get("company") or ""),
                        str(row.get("position") or ""),
                        str(row.get("location") or ""),
                    ]
                ).lower()
            ]

        return merged

    def load_leads_page(
        self,
        *,
        page: int = 1,
        page_size: int = 30,
        q: str = "",
        summary_only: bool = False,
    ) -> dict[str, Any]:
        page = max(1, int(page))
        page_size = max(1, min(int(page_size), 200))

        merged = self._build_merged_leads(q=q, summary_only=summary_only)
        total = len(merged)
        total_pages = max(1, (total + page_size - 1) // page_size)
        safe_page = min(page, total_pages)

        start = (safe_page - 1) * page_size
        end = start + page_size
        items = merged[start:end]

        return {
            "items": items,
            "total": total,
            "page": safe_page,
            "page_size": page_size,
            "total_pages": total_pages,
        }

    # Backward compatibility for existing callers.
    def load_leads(self, limit: int = 200, q: str = "") -> list[dict[str, Any]]:
        merged = self._build_merged_leads(q=q, summary_only=False)
        return merged[: max(1, int(limit))]

    def load_runs(self, limit: int = 20) -> list[dict[str, Any]]:
        return self._load_runs(limit=limit)

    def load_runtime(self) -> dict[str, Any]:
        return self.runtime.status()

    def load_config_view(self) -> dict[str, Any]:
        config = self._read_config_data()
        app = self._ensure_section(config, "app")
        xhs = self._ensure_section(config, "xhs")
        agent = self._ensure_section(config, "agent")
        notification = self._ensure_section(config, "notification")
        email = self._ensure_section(config, "email")
        wechat = self._ensure_section(config, "wechat_service")
        llm = self._ensure_section(config, "llm")

        return {
            "app": {"interval_minutes": self._coerce_int(app.get("interval_minutes"), 15, minimum=1)},
            "xhs": {
                "keyword": str(xhs.get("keyword") or "继任"),
                "search_sort": str(xhs.get("search_sort") or "time_descending"),
                "max_results": self._coerce_int(xhs.get("max_results"), 20, minimum=1),
                "max_detail_fetch": self._coerce_int(xhs.get("max_detail_fetch"), 5, minimum=1),
            },
            "agent": {"mode": self._normalize_mode(str(agent.get("mode") or "auto"))},
            "notification": {
                "mode": self._normalize_notify_mode(str(notification.get("mode") or "digest")),
                "digest_interval_minutes": self._coerce_int(notification.get("digest_interval_minutes"), 30, minimum=1),
                "digest_top_summaries": self._coerce_int(notification.get("digest_top_summaries"), 5, minimum=1),
                "digest_send_when_no_new": bool(notification.get("digest_send_when_no_new", False)),
                "digest_channels": self._to_name_list(notification.get("digest_channels"), default=["email"]),
                "realtime_channels": self._to_name_list(notification.get("realtime_channels"), default=["wechat_service", "email"]),
            },
            "email": {"enabled": bool(email.get("enabled", False))},
            "wechat_service": {"enabled": bool(wechat.get("enabled", False))},
            "llm": {
                "enabled": bool(llm.get("enabled", False)),
                "model": str(llm.get("model") or ""),
                "base_url": str(llm.get("base_url") or ""),
            },
        }

    def save_config_view(self, payload: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(payload, dict):
            raise ValueError("config payload must be an object")

        config = self._read_config_data()
        app = self._ensure_section(config, "app")
        xhs = self._ensure_section(config, "xhs")
        agent = self._ensure_section(config, "agent")
        notification = self._ensure_section(config, "notification")
        email = self._ensure_section(config, "email")
        wechat = self._ensure_section(config, "wechat_service")
        llm = self._ensure_section(config, "llm")

        app_in = payload.get("app")
        if isinstance(app_in, dict):
            app["interval_minutes"] = self._coerce_int(app_in.get("interval_minutes"), app.get("interval_minutes", 15), minimum=1)

        xhs_in = payload.get("xhs")
        if isinstance(xhs_in, dict):
            keyword = str(xhs_in.get("keyword") or xhs.get("keyword") or "继任").strip()
            xhs["keyword"] = keyword or "继任"
            xhs["search_sort"] = str(xhs_in.get("search_sort") or xhs.get("search_sort") or "time_descending").strip() or "time_descending"
            xhs["max_results"] = self._coerce_int(xhs_in.get("max_results"), xhs.get("max_results", 20), minimum=1)
            xhs["max_detail_fetch"] = self._coerce_int(xhs_in.get("max_detail_fetch"), xhs.get("max_detail_fetch", 5), minimum=1)

        agent_in = payload.get("agent")
        if isinstance(agent_in, dict):
            agent["mode"] = self._normalize_mode(str(agent_in.get("mode") or agent.get("mode") or "auto"))

        notify_in = payload.get("notification")
        if isinstance(notify_in, dict):
            notification["mode"] = self._normalize_notify_mode(str(notify_in.get("mode") or notification.get("mode") or "digest"))
            notification["digest_interval_minutes"] = self._coerce_int(
                notify_in.get("digest_interval_minutes"),
                notification.get("digest_interval_minutes", 30),
                minimum=1,
            )
            notification["digest_top_summaries"] = self._coerce_int(
                notify_in.get("digest_top_summaries"),
                notification.get("digest_top_summaries", 5),
                minimum=1,
            )
            notification["digest_send_when_no_new"] = bool(notify_in.get("digest_send_when_no_new", False))
            if "digest_channels" in notify_in:
                notification["digest_channels"] = self._to_name_list(notify_in.get("digest_channels"), default=["email"])
            if "realtime_channels" in notify_in:
                notification["realtime_channels"] = self._to_name_list(
                    notify_in.get("realtime_channels"),
                    default=["wechat_service", "email"],
                )

        email_in = payload.get("email")
        if isinstance(email_in, dict) and "enabled" in email_in:
            email["enabled"] = bool(email_in.get("enabled"))

        wechat_in = payload.get("wechat_service")
        if isinstance(wechat_in, dict) and "enabled" in wechat_in:
            wechat["enabled"] = bool(wechat_in.get("enabled"))

        llm_in = payload.get("llm")
        if isinstance(llm_in, dict):
            if "enabled" in llm_in:
                llm["enabled"] = bool(llm_in.get("enabled"))
            if "model" in llm_in:
                llm["model"] = str(llm_in.get("model") or "").strip()
            if "base_url" in llm_in:
                llm["base_url"] = str(llm_in.get("base_url") or "").strip()

        self._write_config_data(config)
        return self.load_config_view()

    def run_action(self, action: str, payload: dict[str, Any]) -> dict[str, Any]:
        value = str(action or "").strip().lower()
        if value == "run_once":
            mode = self._normalize_mode(str(payload.get("mode") or "auto"))
            return self.runtime.start_run_once(mode=mode)
        if value == "send_latest":
            limit = self._coerce_int(payload.get("limit"), 5, minimum=1)
            return self.runtime.start_send_latest(limit=limit)
        if value == "xhs_login":
            timeout_seconds = self._coerce_int(payload.get("timeout_seconds"), 180, minimum=30)
            return self.runtime.start_xhs_login(timeout_seconds=timeout_seconds)
        if value == "xhs_status":
            return self.runtime.check_xhs_status()
        if value == "start_daemon":
            mode = self._normalize_mode(str(payload.get("mode") or "auto"))
            interval = self._coerce_int(payload.get("interval_minutes"), 0, minimum=1)
            interval_arg = interval if interval > 0 else None
            return self.runtime.start_daemon(mode=mode, interval_minutes=interval_arg)
        if value == "stop_daemon":
            return self.runtime.stop_daemon()
        if value == "stop_job":
            return self.runtime.stop_job()
        raise ValueError(f"unsupported action: {action}")

    def _load_runs(self, limit: int) -> list[dict[str, Any]]:
        if not self.runs_dir.exists():
            return []

        out: list[dict[str, Any]] = []
        files = sorted(self.runs_dir.glob("*.json"), reverse=True)
        for file in files[: max(1, limit)]:
            try:
                payload = json.loads(file.read_text(encoding="utf-8"))
            except Exception:
                continue
            out.append(
                {
                    "run_id": str(payload.get("run_id") or file.stem),
                    "recorded_at": str(payload.get("recorded_at") or ""),
                    "fetched": self._to_int(payload.get("fetched")),
                    "target_notes": self._to_int(payload.get("target_notes")),
                    "jobs": self._to_int(payload.get("jobs")),
                    "send_logs": self._to_int(payload.get("send_logs")),
                    "digest_sent": bool(payload.get("digest_sent")),
                }
            )
        return out

    def _load_workbook_rows(self) -> dict[str, list[dict[str, Any]]]:
        if not self.excel_path.exists():
            return {"raw_notes": [], "succession_summary": [], "jobs": [], "send_log": []}

        wb = load_workbook(self.excel_path, read_only=True)
        try:
            out: dict[str, list[dict[str, Any]]] = {}
            for name in ("raw_notes", "succession_summary", "jobs", "send_log"):
                if name not in wb.sheetnames:
                    out[name] = []
                    continue
                out[name] = self._read_sheet_rows(wb[name])
            return out
        finally:
            wb.close()

    @staticmethod
    def _read_sheet_rows(ws) -> list[dict[str, Any]]:
        iterator = ws.iter_rows(values_only=True)
        try:
            headers_row = next(iterator)
        except StopIteration:
            return []
        headers = [str(x or "").strip() for x in headers_row]
        rows: list[dict[str, Any]] = []
        for values in iterator:
            if not values:
                continue
            row: dict[str, Any] = {}
            for idx, value in enumerate(values):
                if idx >= len(headers):
                    break
                key = headers[idx]
                if key:
                    row[key] = value
            rows.append(row)
        return rows

    @staticmethod
    def _resolve_status(like_count: int, comment_count: int, has_summary: bool, has_job: bool) -> str:
        score = like_count + comment_count * 2
        if has_job and score >= 20:
            return "高优先级"
        if has_job:
            return "可推进"
        if has_summary:
            return "待复核"
        return "新线索"

    @staticmethod
    def _to_int(value: Any) -> int:
        try:
            if value is None:
                return 0
            text = str(value).strip().replace(",", "")
            if not text:
                return 0
            return int(float(text))
        except Exception:
            return 0

    def _read_digest_interval(self) -> int:
        if not self.config_path.exists():
            return 60
        try:
            data = yaml.safe_load(self.config_path.read_text(encoding="utf-8")) or {}
            notification = data.get("notification", {}) if isinstance(data, dict) else {}
            raw = notification.get("digest_interval_minutes", 60)
            return max(1, int(raw))
        except Exception:
            return 60

    def _read_config_data(self) -> dict[str, Any]:
        if not self.config_path.exists():
            return {}
        data = yaml.safe_load(self.config_path.read_text(encoding="utf-8")) or {}
        if isinstance(data, dict):
            return data
        return {}

    def _write_config_data(self, data: dict[str, Any]) -> None:
        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        text = yaml.safe_dump(data, sort_keys=False, allow_unicode=True)
        self.config_path.write_text(text, encoding="utf-8")

    @staticmethod
    def _ensure_section(root: dict[str, Any], key: str) -> dict[str, Any]:
        item = root.get(key)
        if not isinstance(item, dict):
            item = {}
            root[key] = item
        return item

    @staticmethod
    def _coerce_int(value: Any, default: int, minimum: int = 0) -> int:
        try:
            parsed = int(str(value).strip())
        except Exception:
            parsed = int(default)
        return max(minimum, parsed)

    @staticmethod
    def _normalize_mode(value: str) -> str:
        mode = (value or "auto").strip().lower()
        if mode == "smart":
            mode = "agent"
        if mode not in {"auto", "agent"}:
            return "auto"
        return mode

    @staticmethod
    def _normalize_notify_mode(value: str) -> str:
        mode = (value or "digest").strip().lower()
        if mode not in {"digest", "realtime", "off"}:
            return "digest"
        return mode

    @staticmethod
    def _to_name_list(value: Any, default: list[str]) -> list[str]:
        if isinstance(value, list):
            items = [str(item).strip() for item in value if str(item).strip()]
            return items or list(default)
        if isinstance(value, str):
            items = [x.strip() for x in value.split(",") if x.strip()]
            return items or list(default)
        return list(default)
