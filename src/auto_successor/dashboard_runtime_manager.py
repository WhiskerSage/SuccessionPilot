from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import threading
from collections import deque
from datetime import datetime
from pathlib import Path
from typing import Any

from .config import load_settings
from .text_utils import repair_mojibake


class RuntimeManager:
    _PROGRESS_RE = re.compile(r"\[\s*([#\-]{6,})\s*\]\s*(\d{1,3})%\s*\|\s*(.+)$")
    _RUN_ID_RE = re.compile(r"\brun=([A-Za-z0-9._:-]+)")

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

    @staticmethod
    def _build_subprocess_env() -> dict[str, str]:
        env = os.environ.copy()
        env.setdefault("PYTHONIOENCODING", "utf-8")
        return env

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

    def _read_xhs_account_settings(self) -> tuple[str, str]:
        try:
            settings = load_settings(str(self.config_path))
            account = str(getattr(settings.xhs, "account", "default") or "default").strip() or "default"
            account_dir = (
                str(getattr(settings.xhs, "account_cookies_dir", "~/.xhs-mcp/accounts") or "~/.xhs-mcp/accounts").strip()
                or "~/.xhs-mcp/accounts"
            )
            return account, account_dir
        except Exception:
            return "default", "~/.xhs-mcp/accounts"

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
                env=self._build_subprocess_env(),
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
                    line = repair_mojibake(raw.rstrip())
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
        account, account_dir = self._read_xhs_account_settings()
        command = [
            self._resolve_powershell(),
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(script),
            "-Timeout",
            str(max(30, int(timeout_seconds))),
            "-Account",
            account,
            "-AccountCookiesDir",
            account_dir,
        ]
        return self._start_job(name="XHS 扫码登录", command=command)

    def check_xhs_status(self) -> dict[str, Any]:
        script = self.workspace / "scripts" / "xhs_status.ps1"
        account, account_dir = self._read_xhs_account_settings()
        command = [
            self._resolve_powershell(),
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(script),
            "-Account",
            account,
            "-AccountCookiesDir",
            account_dir,
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
                env=self._build_subprocess_env(),
            )
            raw_lines = [repair_mojibake(x.strip()) for x in [result.stdout, result.stderr] if str(x or "").strip()]
            raw = "\n".join(raw_lines).strip()
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
                env=self._build_subprocess_env(),
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
            line = repair_mojibake(raw.rstrip())
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

    @classmethod
    def _extract_progress(cls, logs: list[Any]) -> dict[str, Any]:
        if not isinstance(logs, list):
            return {}
        for raw in reversed(logs):
            line = str(raw or "").strip()
            if not line:
                continue
            match = cls._PROGRESS_RE.search(line)
            if not match:
                continue
            try:
                percent = max(0, min(100, int(match.group(2))))
            except Exception:
                percent = 0
            message = str(match.group(3) or "").strip()
            run_match = cls._RUN_ID_RE.search(line)
            run_id = str(run_match.group(1) if run_match else "").strip()
            return {
                "percent": percent,
                "message": message,
                "run_id": run_id,
                "raw_line": line,
            }
        return {}

    def _job_view(self) -> dict[str, Any]:
        with self._lock:
            out = dict(self._job_state)
            logs = out.get("log_tail")
            out["progress"] = self._extract_progress(logs if isinstance(logs, list) else [])
            return out

    def _daemon_view(self) -> dict[str, Any]:
        with self._lock:
            proc = self._daemon_proc
            running = bool(proc and proc.poll() is None)
            out = {
                "running": running,
                "pid": proc.pid if running else None,
                "started_at": self._daemon_started_at,
                "exit_code": None if running else self._daemon_last_exit,
                "command": list(self._daemon_cmd),
                "log_tail": list(self._daemon_logs),
            }
            out["progress"] = self._extract_progress(out["log_tail"])
            return out

    def status(self) -> dict[str, Any]:
        return {"job": self._job_view(), "daemon": self._daemon_view(), "updated_at": self._now_iso()}
