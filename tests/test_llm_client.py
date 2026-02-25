from __future__ import annotations

import unittest
from unittest.mock import patch

from requests import exceptions as req_exc

from auto_successor.config import (
    AppConfig,
    EmailConfig,
    LLMConfig,
    PipelineConfig,
    Settings,
    StorageConfig,
    WeChatServiceConfig,
    XHSConfig,
)
from auto_successor.llm_client import LLMClient


class _NullLogger:
    def info(self, *args, **kwargs):
        return None

    def warning(self, *args, **kwargs):
        return None


class _Resp:
    def __init__(self, payload: dict, status_code: int = 200):
        self._payload = payload
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            raise req_exc.HTTPError(response=self)

    def json(self):
        return self._payload


def _settings() -> Settings:
    return Settings(
        app=AppConfig(),
        xhs=XHSConfig(),
        pipeline=PipelineConfig(),
        llm=LLMConfig(
            enabled=True,
            api_key="test-key",
            base_url="https://example.invalid/v1",
            request_timeout_seconds=5,
            max_retries=1,
            retry_backoff_seconds=0,
            failure_threshold=5,
            cooldown_seconds=60,
        ),
        wechat_service=WeChatServiceConfig(),
        email=EmailConfig(),
        storage=StorageConfig(),
    )


class TestLLMClientRetry(unittest.TestCase):
    def test_retry_once_on_timeout_then_success(self):
        client = LLMClient(settings=_settings(), logger=_NullLogger())

        calls = {"n": 0}

        def _fake_post(*args, **kwargs):
            calls["n"] += 1
            if calls["n"] == 1:
                raise req_exc.ReadTimeout("timeout")
            return _Resp({"choices": [{"message": {"content": "中文OK"}}]})

        with patch("auto_successor.llm_client.requests.post", side_effect=_fake_post):
            text = client.chat_text(system_prompt="s", user_prompt="u")

        self.assertEqual(calls["n"], 2)
        self.assertEqual(text, "中文OK")
        self.assertEqual(client.last_error_code(), "")

    def test_retry_stops_after_one_and_exposes_reason_code(self):
        client = LLMClient(settings=_settings(), logger=_NullLogger())

        calls = {"n": 0}

        def _fake_post(*args, **kwargs):
            calls["n"] += 1
            raise req_exc.ReadTimeout("timeout")

        with patch("auto_successor.llm_client.requests.post", side_effect=_fake_post):
            text = client.chat_text(system_prompt="s", user_prompt="u")

        self.assertEqual(calls["n"], 2)
        self.assertIsNone(text)
        self.assertEqual(client.last_error_code(), "read_timeout")


if __name__ == "__main__":
    unittest.main()

