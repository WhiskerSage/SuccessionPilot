from __future__ import annotations

import json
import time

import requests

from .config import Settings
from .models import SendResult


class WeChatServiceSender:
    def __init__(self, settings: Settings, logger) -> None:
        self.settings = settings
        self.logger = logger
        self._access_token = ""
        self._expires_at = 0.0

    def send_text(self, text: str) -> SendResult:
        cfg = self.settings.wechat_service
        if not cfg.enabled:
            return SendResult(status="skipped", response="wechat_service.disabled=true")

        app_id = self.settings.wechat_app_id
        app_secret = self.settings.wechat_app_secret
        openids = self.settings.wechat_openids
        if not app_id or not app_secret:
            return SendResult(status="failed", response="missing app_id/app_secret in env")
        if not openids:
            return SendResult(status="failed", response="missing target openids in env")

        token_result = self._get_access_token(app_id, app_secret)
        if not token_result[0]:
            return SendResult(status="failed", response=token_result[1])
        token = token_result[1]

        message = text[:1800]
        send_details = []
        success_count = 0
        for openid in openids:
            payload = {"touser": openid, "msgtype": "text", "text": {"content": message}}
            url = f"https://api.weixin.qq.com/cgi-bin/message/custom/send?access_token={token}"
            try:
                resp = requests.post(url, json=payload, timeout=15)
                data = resp.json()
            except Exception as exc:
                data = {"errcode": -1, "errmsg": str(exc)}

            if data.get("errcode") == 0:
                success_count += 1
            send_details.append({"openid": openid, "result": data})

        if success_count == len(openids):
            status = "success"
        elif success_count == 0:
            status = "failed"
        else:
            status = "partial"

        return SendResult(status=status, response=json.dumps(send_details, ensure_ascii=False))

    def _get_access_token(self, app_id: str, app_secret: str) -> tuple[bool, str]:
        now = time.time()
        if self._access_token and now < self._expires_at - 30:
            return True, self._access_token

        url = "https://api.weixin.qq.com/cgi-bin/token"
        params = {"grant_type": "client_credential", "appid": app_id, "secret": app_secret}
        try:
            resp = requests.get(url, params=params, timeout=15)
            data = resp.json()
        except Exception as exc:
            return False, f"token request failed: {exc}"

        token = str(data.get("access_token") or "")
        expires = int(data.get("expires_in") or 0)
        if not token:
            return False, f"token response error: {data}"

        self._access_token = token
        self._expires_at = time.time() + expires
        return True, token
