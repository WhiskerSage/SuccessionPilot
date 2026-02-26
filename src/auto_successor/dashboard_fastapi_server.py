from __future__ import annotations

from pathlib import Path
from typing import Any

from .dashboard_backend import DataBackend

FASTAPI_AVAILABLE = False
_IMPORT_ERROR: Exception | None = None

try:
    from fastapi import Body, FastAPI, File, HTTPException, Request, UploadFile
    from fastapi.middleware.cors import CORSMiddleware
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

    @app.get("/api/health")
    async def api_health() -> dict[str, Any]:
        from datetime import datetime

        return {"ok": True, "time": datetime.now().isoformat()}

    @app.get("/api/summary")
    async def api_summary() -> dict[str, Any]:
        return backend.load_summary()

    @app.get("/api/leads")
    async def api_leads(limit: int = 30, page: int = 1, q: str = "", view: str = "all") -> dict[str, Any]:
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
        )

    @app.get("/api/runs")
    async def api_runs(limit: int = 20) -> dict[str, Any]:
        try:
            safe_limit = max(1, int(limit))
        except Exception as exc:
            raise HTTPException(status_code=400, detail=f"invalid limit: {exc}") from exc
        return {"items": backend.load_runs(limit=safe_limit)}

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
