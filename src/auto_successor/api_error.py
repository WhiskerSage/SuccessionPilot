from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any


def new_trace_id(prefix: str = "api") -> str:
    safe = str(prefix or "api").strip().lower() or "api"
    return f"{safe}-{uuid.uuid4().hex[:12]}"


def status_to_code(status_code: int) -> str:
    code = int(status_code or 500)
    if code == 400:
        return "invalid_request"
    if code == 401:
        return "unauthorized"
    if code == 403:
        return "forbidden"
    if code == 404:
        return "not_found"
    if code == 409:
        return "conflict"
    if code == 429:
        return "rate_limited"
    if 500 <= code <= 599:
        return "internal_error"
    return "request_failed"


def error_payload(
    *,
    status_code: int,
    code: str,
    message: str,
    reason: str = "",
    fix_command: str = "",
    details: Any = None,
    trace_id: str = "",
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "ok": False,
        "error": {
            "code": str(code or status_to_code(status_code)).strip().lower(),
            "message": str(message or "request failed").strip(),
            "reason": str(reason or message or "").strip(),
            "fix_command": str(fix_command or "").strip(),
            "trace_id": str(trace_id or new_trace_id("api")),
        },
    }
    if details is not None:
        payload["error"]["details"] = details
    return payload


@dataclass
class ApiError(Exception):
    status_code: int
    code: str
    message: str
    reason: str = ""
    fix_command: str = ""
    details: Any = None
    trace_id: str = ""

    def to_payload(self) -> dict[str, Any]:
        return error_payload(
            status_code=self.status_code,
            code=self.code,
            message=self.message,
            reason=self.reason,
            fix_command=self.fix_command,
            details=self.details,
            trace_id=self.trace_id,
        )

    @classmethod
    def from_status(
        cls,
        *,
        status_code: int,
        message: str,
        code: str = "",
        reason: str = "",
        fix_command: str = "",
        details: Any = None,
        trace_id: str = "",
    ) -> "ApiError":
        return cls(
            status_code=int(status_code or 500),
            code=str(code or status_to_code(status_code)).strip().lower(),
            message=str(message or "request failed"),
            reason=str(reason or message or ""),
            fix_command=str(fix_command or ""),
            details=details,
            trace_id=str(trace_id or ""),
        )
