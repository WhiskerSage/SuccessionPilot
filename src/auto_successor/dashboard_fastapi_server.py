from __future__ import annotations

from pathlib import Path
from typing import Any

from .api_error import ApiError, error_payload, new_trace_id, status_to_code
from .dashboard_backend import DataBackend

FASTAPI_AVAILABLE = False
_IMPORT_ERROR: Exception | None = None

try:
    from fastapi import Body, FastAPI, File, HTTPException, Request, UploadFile
    from fastapi.middleware.cors import CORSMiddleware
    from fastapi.responses import JSONResponse
    from fastapi.staticfiles import StaticFiles
    import uvicorn

    FASTAPI_AVAILABLE = True
except Exception as exc:  # pragma: no cover - optional dependency
    _IMPORT_ERROR = exc


def is_fastapi_available() -> bool:
    return FASTAPI_AVAILABLE


def import_error_message() -> str:
    if _IMPORT_ERROR is None:
        return ""
    return str(_IMPORT_ERROR)


def create_fastapi_app(backend: DataBackend, web_dir: Path):
    if not FASTAPI_AVAILABLE:  # pragma: no cover - depends on optional deps
        raise RuntimeError(f"FastAPI backend unavailable: {import_error_message()}")

    app = FastAPI(
        title="SuccessionPilot Dashboard API",
        version="0.1.0",
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.exception_handler(ApiError)
    async def api_error_handler(request: Request, exc: ApiError):  # type: ignore[unused-ignore]
        return JSONResponse(status_code=exc.status_code, content=exc.to_payload())

    @app.exception_handler(HTTPException)
    async def http_exception_handler(request: Request, exc: HTTPException):  # type: ignore[unused-ignore]
        trace_id = new_trace_id("api")
        detail = exc.detail
        if isinstance(detail, dict):
            inner = detail.get("error") if isinstance(detail.get("error"), dict) else detail
            if isinstance(inner, dict):
                code = str(inner.get("code") or status_to_code(exc.status_code)).strip().lower()
                message = str(inner.get("message") or inner.get("detail") or "request failed").strip()
                reason = str(inner.get("reason") or message).strip()
                fix_command = str(inner.get("fix_command") or "").strip()
                details = inner.get("details")
                payload = error_payload(
                    status_code=exc.status_code,
                    code=code,
                    message=message,
                    reason=reason,
                    fix_command=fix_command,
                    details=details,
                    trace_id=str(inner.get("trace_id") or trace_id),
                )
                return JSONResponse(status_code=exc.status_code, content=payload)
        payload = error_payload(
            status_code=exc.status_code,
            code=status_to_code(exc.status_code),
            message=str(detail or "request failed"),
            reason=str(detail or "request failed"),
            trace_id=trace_id,
        )
        return JSONResponse(status_code=exc.status_code, content=payload)

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception):  # type: ignore[unused-ignore]
        trace_id = new_trace_id("api")
        payload = error_payload(
            status_code=500,
            code="internal_error",
            message="server error",
            reason=str(exc)[:300],
            trace_id=trace_id,
        )
        return JSONResponse(status_code=500, content=payload)

    @app.get("/api/health")
    async def api_health() -> dict[str, Any]:
        from datetime import datetime

        return {"ok": True, "time": datetime.now().isoformat()}

    @app.get("/api/summary")
    async def api_summary() -> dict[str, Any]:
        return backend.load_summary()

    @app.get("/api/leads")
    async def api_leads(
        limit: int = 30,
        page: int = 1,
        q: str = "",
        view: str = "all",
        status: str = "all",
        dedupe: str = "all",
    ) -> dict[str, Any]:
        try:
            safe_limit = max(1, int(limit))
            safe_page = max(1, int(page))
        except Exception as exc:
            raise HTTPException(status_code=400, detail=f"invalid paging argument: {exc}") from exc
        summary_only = str(view or "").strip().lower() == "summary"
        return backend.load_leads_page(
            page=safe_page,
            page_size=safe_limit,
            q=q,
            summary_only=summary_only,
            status_filter=status,
            dedupe_filter=dedupe,
        )

    @app.get("/api/runs")
    async def api_runs(limit: int = 20) -> dict[str, Any]:
        try:
            safe_limit = max(1, int(limit))
        except Exception as exc:
            raise HTTPException(status_code=400, detail=f"invalid limit: {exc}") from exc
        return {"items": backend.load_runs(limit=safe_limit)}

    @app.get("/api/performance")
    async def api_performance(limit: int = 50) -> dict[str, Any]:
        try:
            safe_limit = max(1, min(int(limit), 300))
        except Exception as exc:
            raise HTTPException(status_code=400, detail=f"invalid limit: {exc}") from exc
        return backend.load_performance(limit=safe_limit)

    @app.get("/api/runs/{run_id}")
    async def api_run_detail(run_id: str) -> dict[str, Any]:
        try:
            return backend.load_run_detail(run_id=run_id)
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except Exception as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc

    @app.get("/api/retry-queue")
    async def api_retry_queue(status: str = "all", queue_type: str = "all", limit: int = 120) -> dict[str, Any]:
        try:
            safe_limit = max(1, min(int(limit), 500))
        except Exception as exc:
            raise HTTPException(status_code=400, detail=f"invalid limit: {exc}") from exc
        return backend.load_retry_queue_view(status=status, queue_type=queue_type, limit=safe_limit)

    @app.post("/api/retry-queue/requeue")
    async def api_retry_requeue(payload: dict[str, Any] = Body(default_factory=dict)) -> dict[str, Any]:
        item_id = str(payload.get("id") or "").strip()
        if not item_id:
            raise HTTPException(status_code=400, detail="missing id")
        try:
            return backend.retry_queue_requeue(item_id=item_id)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except Exception as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc

    @app.post("/api/retry-queue/drop")
    async def api_retry_drop(payload: dict[str, Any] = Body(default_factory=dict)) -> dict[str, Any]:
        item_id = str(payload.get("id") or "").strip()
        if not item_id:
            raise HTTPException(status_code=400, detail="missing id")
        try:
            return backend.retry_queue_drop(item_id=item_id)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except Exception as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc

    @app.post("/api/retry-queue/kick")
    async def api_retry_kick(payload: dict[str, Any] = Body(default_factory=dict)) -> dict[str, Any]:
        queue_type = str(payload.get("queue_type") or "all").strip().lower()
        limit = payload.get("limit", 120)
        try:
            safe_limit = max(1, min(int(limit), 500))
        except Exception as exc:
            raise HTTPException(status_code=400, detail=f"invalid limit: {exc}") from exc
        try:
            return backend.retry_queue_kick(queue_type=queue_type, limit=safe_limit)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except Exception as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc

    @app.get("/api/runtime")
    async def api_runtime() -> dict[str, Any]:
        return backend.load_runtime()

    @app.get("/api/resume")
    async def api_resume() -> dict[str, Any]:
        return backend.load_resume_view()

    @app.post("/api/resume/text")
    async def api_resume_text(payload: dict[str, Any] = Body(default_factory=dict)) -> dict[str, Any]:
        try:
            text = str(payload.get("resume_text") or "")
            return backend.save_resume_text(text)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except Exception as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc

    @app.post("/api/resume/upload")
    async def api_resume_upload(request: Request) -> dict[str, Any]:
        try:
            content_type = str(request.headers.get("content-type") or "").lower()
            if "multipart/form-data" in content_type:
                form = await request.form()
                file = form.get("file")
                if file is None:
                    raise ValueError("file is required")
                filename = str(getattr(file, "filename", "resume.txt") or "resume.txt")
                content = await file.read()
                if not content:
                    raise ValueError("empty file")
                return backend.upload_resume_file(
                    filename=filename,
                    content=content,
                    mime_type=str(getattr(file, "content_type", "") or ""),
                )

            payload = await request.json()
            if not isinstance(payload, dict):
                raise ValueError("JSON body must be an object")
            return backend.upload_resume_base64(
                filename=str(payload.get("filename") or "resume.txt"),
                content_base64=str(payload.get("content_base64") or ""),
                mime_type=str(payload.get("mime_type") or ""),
            )
        except (ValueError, RuntimeError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except Exception as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc

    @app.post("/api/resume/parse")
    async def api_resume_parse(request: Request) -> dict[str, Any]:
        try:
            content_type = str(request.headers.get("content-type") or "").lower()
            if "multipart/form-data" in content_type:
                form = await request.form()
                file = form.get("file")
                if file is None:
                    raise ValueError("file is required")
                filename = str(getattr(file, "filename", "resume.txt") or "resume.txt")
                content = await file.read()
                if not content:
                    raise ValueError("empty file")
                return backend.parse_resume_file(
                    filename=filename,
                    content=content,
                    mime_type=str(getattr(file, "content_type", "") or ""),
                )

            payload = await request.json()
            if not isinstance(payload, dict):
                raise ValueError("JSON body must be an object")
            return backend.parse_resume_base64(
                filename=str(payload.get("filename") or "resume.txt"),
                content_base64=str(payload.get("content_base64") or ""),
                mime_type=str(payload.get("mime_type") or ""),
            )
        except (ValueError, RuntimeError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except Exception as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc

    @app.get("/api/config")
    async def api_config() -> dict[str, Any]:
        return {"config": backend.load_config_view()}

    @app.get("/api/xhs/accounts")
    async def api_xhs_accounts() -> dict[str, Any]:
        return backend.load_xhs_accounts_view()

    @app.get("/api/setup/check")
    async def api_setup_check_get() -> dict[str, Any]:
        return backend.run_setup_check(include_network=True, include_xhs_status=True)

    @app.post("/api/setup/check")
    async def api_setup_check(payload: dict[str, Any] = Body(default_factory=dict)) -> dict[str, Any]:
        include_network = bool(payload.get("include_network", True))
        include_xhs_status = bool(payload.get("include_xhs_status", True))
        return backend.run_setup_check(
            include_network=include_network,
            include_xhs_status=include_xhs_status,
        )

    @app.post("/api/config")
    async def api_save_config(payload: dict[str, Any] = Body(default_factory=dict)) -> dict[str, Any]:
        try:
            config = backend.save_config_view(payload)
            return {"ok": True, "message": "配置已保存", "config": config}
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except Exception as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc

    @app.post("/api/action")
    async def api_action(payload: dict[str, Any] = Body(default_factory=dict)) -> dict[str, Any]:
        action = str(payload.get("action") or "").strip()
        if not action:
            raise HTTPException(status_code=400, detail="missing action")
        try:
            return backend.run_action(action=action, payload=payload)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except Exception as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc

    # Keep this last so API routes have priority.
    app.mount("/", StaticFiles(directory=str(web_dir), html=True), name="web")
    return app


def run_fastapi_dashboard(host: str, port: int, workspace: Path) -> None:
    if not FASTAPI_AVAILABLE:  # pragma: no cover - depends on optional deps
        raise RuntimeError(
            "FastAPI backend unavailable. Install with:\n"
            "  pip install fastapi uvicorn\n"
            f"Import error: {import_error_message()}"
        )

    web_dir = workspace / "web"
    if not web_dir.exists():
        raise FileNotFoundError(f"Web directory not found: {web_dir}")

    backend = DataBackend(workspace=workspace)
    app = create_fastapi_app(backend=backend, web_dir=web_dir)
    print(f"Dashboard running on http://{host}:{port} (fastapi)")
    uvicorn.run(app, host=host, port=port, log_level="info")
