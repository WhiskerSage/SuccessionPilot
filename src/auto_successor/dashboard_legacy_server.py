from __future__ import annotations

import json
from datetime import datetime
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

from .dashboard_backend import DataBackend


def make_handler(backend: DataBackend, web_dir: Path):
    class DashboardHandler(SimpleHTTPRequestHandler):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, directory=str(web_dir), **kwargs)

        def do_GET(self) -> None:
            parsed = urlparse(self.path)
            path = parsed.path
            if path.startswith("/api/"):
                self._handle_api(path=path, query=parse_qs(parsed.query))
                return
            if path == "/":
                self.path = "/index.html"
            return super().do_GET()

        def _handle_api(self, path: str, query: dict[str, list[str]]) -> None:
            try:
                if path == "/api/health":
                    self._json({"ok": True, "time": datetime.now().isoformat()})
                    return

                if path == "/api/summary":
                    self._json(backend.load_summary())
                    return

                if path == "/api/leads":
                    limit = int((query.get("limit") or ["30"])[0])
                    page = int((query.get("page") or ["1"])[0])
                    q = (query.get("q") or [""])[0]
                    view = str((query.get("view") or ["all"])[0]).strip().lower()
                    summary_only = view == "summary"
                    self._json(
                        backend.load_leads_page(
                            page=page,
                            page_size=limit,
                            q=q,
                            summary_only=summary_only,
                        )
                    )
                    return

                if path == "/api/runs":
                    limit = int((query.get("limit") or ["20"])[0])
                    self._json({"items": backend.load_runs(limit=limit)})
                    return

                if path == "/api/runtime":
                    self._json(backend.load_runtime())
                    return

                if path == "/api/resume":
                    self._json(backend.load_resume_view())
                    return

                if path == "/api/config":
                    self._json({"config": backend.load_config_view()})
                    return

                if path == "/api/setup/check":
                    self._json(backend.run_setup_check(include_network=True, include_xhs_status=True))
                    return

                self._json({"error": "not_found", "path": path}, status=HTTPStatus.NOT_FOUND)
            except Exception as exc:
                self._json(
                    {"error": "server_error", "message": str(exc)},
                    status=HTTPStatus.INTERNAL_SERVER_ERROR,
                )

        def do_POST(self) -> None:
            parsed = urlparse(self.path)
            path = parsed.path
            if not path.startswith("/api/"):
                self._json({"error": "not_found", "path": path}, status=HTTPStatus.NOT_FOUND)
                return
            try:
                payload = self._read_json_body()
                if path == "/api/config":
                    config = backend.save_config_view(payload)
                    self._json({"ok": True, "message": "配置已保存", "config": config})
                    return
                if path == "/api/setup/check":
                    include_network = bool(payload.get("include_network", True))
                    include_xhs_status = bool(payload.get("include_xhs_status", True))
                    self._json(
                        backend.run_setup_check(
                            include_network=include_network,
                            include_xhs_status=include_xhs_status,
                        )
                    )
                    return
                if path == "/api/resume/text":
                    text = str(payload.get("resume_text") or "")
                    self._json(backend.save_resume_text(text))
                    return
                if path == "/api/resume/upload":
                    filename = str(payload.get("filename") or "resume.txt")
                    mime_type = str(payload.get("mime_type") or "")
                    content_base64 = str(payload.get("content_base64") or "")
                    self._json(
                        backend.upload_resume_base64(
                            filename=filename,
                            content_base64=content_base64,
                            mime_type=mime_type,
                        )
                    )
                    return
                if path == "/api/resume/parse":
                    filename = str(payload.get("filename") or "resume.txt")
                    mime_type = str(payload.get("mime_type") or "")
                    content_base64 = str(payload.get("content_base64") or "")
                    self._json(
                        backend.parse_resume_base64(
                            filename=filename,
                            content_base64=content_base64,
                            mime_type=mime_type,
                        )
                    )
                    return
                if path == "/api/action":
                    action = str(payload.get("action") or "").strip()
                    result = backend.run_action(action=action, payload=payload)
                    self._json(result)
                    return
                self._json({"error": "not_found", "path": path}, status=HTTPStatus.NOT_FOUND)
            except Exception as exc:
                self._json(
                    {"error": "server_error", "message": str(exc)},
                    status=HTTPStatus.INTERNAL_SERVER_ERROR,
                )

        def _read_json_body(self) -> dict[str, Any]:
            raw_len = self.headers.get("Content-Length", "0")
            try:
                length = int(raw_len)
            except Exception:
                length = 0
            if length <= 0:
                return {}
            raw = self.rfile.read(length).decode("utf-8", errors="replace")
            if not raw.strip():
                return {}
            payload = json.loads(raw)
            if not isinstance(payload, dict):
                raise ValueError("JSON body must be an object")
            return payload

        def _json(self, payload: Any, status: HTTPStatus = HTTPStatus.OK) -> None:
            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self.send_response(status.value)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
            self.send_header("Access-Control-Allow-Headers", "Content-Type, Accept")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_OPTIONS(self) -> None:
            self.send_response(HTTPStatus.NO_CONTENT.value)
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
            self.send_header("Access-Control-Allow-Headers", "Content-Type, Accept")
            self.end_headers()

    return DashboardHandler


def run_legacy_dashboard(host: str, port: int, workspace: Path) -> None:
    web_dir = workspace / "web"
    if not web_dir.exists():
        raise FileNotFoundError(f"Web directory not found: {web_dir}")

    backend = DataBackend(workspace=workspace)
    handler = make_handler(backend=backend, web_dir=web_dir)
    server = ThreadingHTTPServer((host, port), handler)
    print(f"Dashboard running on http://{host}:{port} (legacy)")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
