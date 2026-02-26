from __future__ import annotations

import json
import re
import time
from typing import Any

import requests
from requests import exceptions as req_exc

from .config import Settings


class LLMClient:
    def __init__(self, settings: Settings, logger) -> None:
        self.settings = settings
        self.logger = logger
        self._failure_threshold = max(1, int(getattr(settings.llm, "failure_threshold", 2)))
        self._cooldown_seconds = max(30, int(getattr(settings.llm, "cooldown_seconds", 120)))
        self._scope_states: dict[str, dict[str, Any]] = {}
        self._error_counts: dict[str, int] = {}
        self._request_seq = 0

    def is_enabled(self) -> bool:
        return self.settings.llm.enabled

    def is_available(self, scope: str | None = None) -> bool:
        scope_key, state = self._scope_state(scope)
        if not (self.settings.llm.enabled and bool(self.settings.llm_api_key)):
            state["last_error_code"] = "disabled_or_missing_api_key"
            return False
        now = time.monotonic()
        if now < float(state["disabled_until"]):
            state["last_error_code"] = "cooldown_active"
            if not bool(state["degraded_active"]):
                remain = int(float(state["disabled_until"]) - now)
                self.logger.warning(
                    "[LLM降级] scope=%s 进入回退模式，冷却剩余约 %ss",
                    scope_key,
                    max(1, remain),
                )
                state["degraded_active"] = True
            return False
        if bool(state["degraded_active"]):
            self.logger.info("[LLM恢复] scope=%s 冷却结束，恢复 LLM 调用", scope_key)
            state["degraded_active"] = False
        return True

    def last_error_code(self, scope: str | None = None) -> str:
        _, state = self._scope_state(scope)
        return str(state.get("last_error_code", "") or "")

    def error_counts(self) -> dict[str, int]:
        return dict(self._error_counts)

    def clear_error_counts(self) -> None:
        self._error_counts = {}

    def chat_json(
        self,
        system_prompt: str,
        user_prompt: str,
        model: str | None = None,
        scope: str | None = None,
    ) -> dict[str, Any] | None:
        text = self.chat_text(system_prompt=system_prompt, user_prompt=user_prompt, model=model, scope=scope)
        if not text:
            return None

        # Direct parse first.
        try:
            obj = json.loads(text)
            if isinstance(obj, dict):
                return obj
        except Exception:
            pass

        # Fallback: parse first JSON object from response body.
        start = text.find("{")
        end = text.rfind("}")
        if start < 0 or end <= start:
            return None
        snippet = text[start : end + 1]
        try:
            obj = json.loads(snippet)
            if isinstance(obj, dict):
                return obj
        except Exception:
            return None
        return None

    def chat_text(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float | None = None,
        max_tokens: int | None = None,
        model: str | None = None,
        scope: str | None = None,
    ) -> str | None:
        scope_key, _ = self._scope_state(scope)
        if not self.is_available(scope=scope_key):
            return None

        cfg = self.settings.llm
        base = cfg.base_url.rstrip("/")
        url = f"{base}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.settings.llm_api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": (model or "").strip() or cfg.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": cfg.temperature if temperature is None else float(temperature),
            "max_tokens": cfg.max_tokens if max_tokens is None else int(max_tokens),
        }

        # Keep each request bounded, and retry at most once on transient failures.
        read_timeout = max(6, min(int(getattr(cfg, "request_timeout_seconds", cfg.timeout_seconds or 20)), 30))
        connect_timeout = max(2, min(int(getattr(cfg, "connect_timeout_seconds", 8)), 15))
        max_retries = max(0, min(int(getattr(cfg, "max_retries", 1)), 1))
        retry_backoff = max(0.0, min(float(getattr(cfg, "retry_backoff_seconds", 0.6)), 2.0))
        attempts = 1 + max_retries
        self._request_seq += 1
        request_id = self._request_seq
        self.logger.info(
            "[LLM请求] 第%s次 | scope=%s | model=%s | max_tokens=%s | connect=%ss read=%ss",
            request_id,
            scope_key,
            payload.get("model"),
            payload.get("max_tokens"),
            connect_timeout,
            read_timeout,
        )

        for attempt in range(1, attempts + 1):
            try:
                resp = requests.post(
                    url,
                    headers=headers,
                    json=payload,
                    timeout=(connect_timeout, read_timeout),
                )
                resp.raise_for_status()
                data = self._parse_json_payload(resp)
            except Exception as exc:
                code, retryable = self._classify_error(exc)
                if attempt < attempts and retryable:
                    self.logger.info(
                        "[LLM重试] 请求#%s scope=%s attempt=%s/%s code=%s",
                        request_id,
                        scope_key,
                        attempt + 1,
                        attempts,
                        code,
                    )
                    if retry_backoff > 0:
                        time.sleep(retry_backoff * attempt)
                    continue
                self._mark_failure(code=code, scope=scope_key)
                self.logger.warning("[LLM失败] 请求#%s scope=%s code=%s detail=%s", request_id, scope_key, code, exc)
                return None

            content = self._extract_text(data)
            if content is not None:
                self._mark_success(scope=scope_key)
                self.logger.info("[LLM成功] 请求#%s scope=%s 返回长度=%s", request_id, scope_key, len(content))
                return self._strip_code_fence(content)

            code = "empty_content"
            if attempt < attempts:
                self.logger.info(
                    "[LLM重试] 请求#%s scope=%s attempt=%s/%s code=%s",
                    request_id,
                    scope_key,
                    attempt + 1,
                    attempts,
                    code,
                )
                if retry_backoff > 0:
                    time.sleep(retry_backoff * attempt)
                continue
            self._mark_failure(code=code, scope=scope_key)
            self.logger.warning(
                "[LLM失败] 请求#%s scope=%s code=%s payload=%s",
                request_id,
                scope_key,
                code,
                str(data)[:300],
            )
            return None

        self._mark_failure(code="unknown_error", scope=scope_key)
        return None

    @staticmethod
    def _strip_code_fence(text: str) -> str:
        raw = (text or "").strip()
        # Remove markdown code fences if model returns ```json ...```.
        m = re.match(r"^```(?:json)?\s*([\s\S]*?)\s*```$", raw, flags=re.IGNORECASE)
        if m:
            return m.group(1).strip()
        return raw

    @staticmethod
    def _extract_text(data: Any) -> str | None:
        # Standard OpenAI-compatible shape.
        choices = data.get("choices", []) if isinstance(data, dict) else []
        if choices and isinstance(choices[0], dict):
            message = choices[0].get("message", {})
            content = message.get("content")
            if isinstance(content, str):
                return content
            if isinstance(message.get("reasoning_content"), str):
                return message.get("reasoning_content") or ""
            if isinstance(content, list):
                text_parts = []
                for part in content:
                    if isinstance(part, dict):
                        t = part.get("text")
                        if isinstance(t, str):
                            text_parts.append(t)
                if text_parts:
                    return "\n".join(text_parts)
            if isinstance(choices[0].get("text"), str):
                return choices[0].get("text") or ""

        # Fallback for some providers.
        if isinstance(data, dict):
            if isinstance(data.get("output_text"), str):
                return data["output_text"]
            if isinstance(data.get("text"), str):
                return data["text"]
        return None

    @staticmethod
    def _parse_json_payload(resp: requests.Response) -> dict[str, Any]:
        # Prefer strict UTF-8 decoding to avoid provider charset/header mismatches.
        raw = getattr(resp, "content", b"") or b""
        if raw:
            for encoding in ("utf-8", "utf-8-sig", "gb18030"):
                try:
                    text = raw.decode(encoding)
                    data = json.loads(text)
                    if isinstance(data, dict):
                        return data
                except Exception:
                    continue
        data = resp.json()
        if isinstance(data, dict):
            return data
        raise ValueError("llm response json is not an object")

    @staticmethod
    def _classify_error(exc: Exception) -> tuple[str, bool]:
        if isinstance(exc, req_exc.ConnectTimeout):
            return ("connect_timeout", True)
        if isinstance(exc, req_exc.ReadTimeout):
            return ("read_timeout", True)
        if isinstance(exc, req_exc.Timeout):
            return ("timeout", True)
        if isinstance(exc, req_exc.ConnectionError):
            return ("connection_error", True)
        if isinstance(exc, req_exc.HTTPError):
            status = 0
            try:
                status = int(getattr(getattr(exc, "response", None), "status_code", 0) or 0)
            except Exception:
                status = 0
            if status == 429:
                return ("http_429", True)
            if 500 <= status < 600:
                return (f"http_{status}", True)
            if 400 <= status < 500:
                return (f"http_{status}", False)
            return ("http_error", False)
        return ("request_error", False)

    def _scope_state(self, scope: str | None) -> tuple[str, dict[str, Any]]:
        key = str(scope or "default").strip().lower() or "default"
        state = self._scope_states.get(key)
        if state is None:
            state = {
                "consecutive_failures": 0,
                "disabled_until": 0.0,
                "degraded_active": False,
                "last_error_code": "",
            }
            self._scope_states[key] = state
        return key, state

    def _mark_success(self, scope: str | None = None) -> None:
        _, state = self._scope_state(scope)
        state["consecutive_failures"] = 0
        state["last_error_code"] = ""

    def _mark_failure(self, code: str = "unknown_error", scope: str | None = None) -> None:
        scope_key, state = self._scope_state(scope)
        state["consecutive_failures"] = int(state.get("consecutive_failures", 0)) + 1
        state["last_error_code"] = code
        key = str(code or "unknown_error").strip() or "unknown_error"
        self._error_counts[key] = int(self._error_counts.get(key, 0)) + 1
        if int(state["consecutive_failures"]) >= self._failure_threshold:
            state["disabled_until"] = time.monotonic() + self._cooldown_seconds
            self.logger.warning(
                "[LLM降级] scope=%s 连续失败 %s 次，暂停 %ss（last_code=%s）",
                scope_key,
                state["consecutive_failures"],
                self._cooldown_seconds,
                code,
            )
            state["degraded_active"] = False
            state["consecutive_failures"] = 0

