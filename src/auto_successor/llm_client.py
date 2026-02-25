from __future__ import annotations

import json
import re
from typing import Any

import requests

from .config import Settings


class LLMClient:
    def __init__(self, settings: Settings, logger) -> None:
        self.settings = settings
        self.logger = logger

    def is_enabled(self) -> bool:
        return self.settings.llm.enabled

    def is_available(self) -> bool:
        return self.settings.llm.enabled and bool(self.settings.llm_api_key)

    def chat_json(self, system_prompt: str, user_prompt: str) -> dict[str, Any] | None:
        text = self.chat_text(system_prompt=system_prompt, user_prompt=user_prompt)
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
    ) -> str | None:
        if not self.is_available():
            return None

        cfg = self.settings.llm
        base = cfg.base_url.rstrip("/")
        url = f"{base}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.settings.llm_api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": cfg.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": cfg.temperature if temperature is None else float(temperature),
            "max_tokens": cfg.max_tokens if max_tokens is None else int(max_tokens),
        }
        try:
            resp = requests.post(url, headers=headers, json=payload, timeout=cfg.timeout_seconds)
            resp.raise_for_status()
            data = resp.json()
        except Exception as exc:
            self.logger.warning("llm request failed: %s", exc)
            return None

        # Standard OpenAI-compatible shape.
        choices = data.get("choices", []) if isinstance(data, dict) else []
        if choices and isinstance(choices[0], dict):
            message = choices[0].get("message", {})
            content = message.get("content")
            if isinstance(content, str):
                return self._strip_code_fence(content)
            if isinstance(message.get("reasoning_content"), str):
                return self._strip_code_fence(message.get("reasoning_content") or "")
            if isinstance(content, list):
                text_parts = []
                for part in content:
                    if isinstance(part, dict):
                        t = part.get("text")
                        if isinstance(t, str):
                            text_parts.append(t)
                if text_parts:
                    return self._strip_code_fence("\n".join(text_parts))
            if isinstance(choices[0].get("text"), str):
                return self._strip_code_fence(choices[0].get("text") or "")

        # Fallback for some providers.
        if isinstance(data, dict):
            if isinstance(data.get("output_text"), str):
                return self._strip_code_fence(data["output_text"])
            if isinstance(data.get("text"), str):
                return self._strip_code_fence(data["text"])

        self.logger.warning("llm response missing content: %s", str(data)[:300])
        return None

    @staticmethod
    def _strip_code_fence(text: str) -> str:
        raw = (text or "").strip()
        # Remove markdown code fences if model returns ```json ...```.
        m = re.match(r"^```(?:json)?\s*([\s\S]*?)\s*```$", raw, flags=re.IGNORECASE)
        if m:
            return m.group(1).strip()
        return raw

