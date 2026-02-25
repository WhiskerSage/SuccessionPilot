from __future__ import annotations

import json
import os
import re
import subprocess
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from .config import XHSConfig
from .models import NoteRecord
from .text_utils import clean_line


class XHSCollectorError(RuntimeError):
    pass


class XHSMcpCliCollector:
    def __init__(self, cfg: XHSConfig, timezone: str, logger) -> None:
        self.cfg = cfg
        self.tz = ZoneInfo(timezone)
        self.logger = logger

    def ensure_logged_in(self) -> None:
        status = self._run_json(["status", "--compact"])
        if status.get("success") and status.get("loggedIn") is True:
            return

        self.logger.warning("xhs status shows not logged in; trying login flow")
        login = self._run_json(["login", "--timeout", str(self.cfg.login_timeout_seconds)])
        if not login.get("success"):
            raise XHSCollectorError(f"xhs login failed: {login}")

        status = self._run_json(["status", "--compact"])
        if not (status.get("success") and status.get("loggedIn") is True):
            raise XHSCollectorError(f"xhs status still not logged in after login: {status}")

    def search_notes(self, run_id: str, keyword: str, max_results: int) -> list[NoteRecord]:
        payload = self._run_search_payload(keyword=keyword, max_results=max_results)
        if not payload.get("success"):
            raise XHSCollectorError(f"xhs search failed: {payload}")

        feeds = payload.get("feeds", [])
        if not isinstance(feeds, list):
            feeds = []

        notes: list[NoteRecord] = []
        for feed in feeds:
            if not isinstance(feed, dict):
                continue
            model_type = str(feed.get("modelType") or feed.get("model_type") or "").strip().lower()
            if model_type != "note":
                continue

            note_id = str(feed.get("id") or "").strip()
            if not note_id:
                continue

            note_card_raw = feed.get("noteCard")
            if not isinstance(note_card_raw, dict):
                note_card_raw = feed.get("note_card")
            note_card = note_card_raw if isinstance(note_card_raw, dict) else {}

            user = note_card.get("user", {}) if isinstance(note_card.get("user"), dict) else {}

            interact_raw = note_card.get("interactInfo")
            if not isinstance(interact_raw, dict):
                interact_raw = note_card.get("interact_info")
            interact = interact_raw if isinstance(interact_raw, dict) else {}

            title = clean_line(str(note_card.get("displayTitle") or note_card.get("display_title") or ""))
            author = clean_line(str(user.get("nickName") or user.get("nick_name") or user.get("nickname") or ""))
            like_count = self._to_int(self._pick(interact, "likedCount", "liked_count"))
            comment_count = self._to_int(self._pick(interact, "commentCount", "comment_count"))
            share_count = self._to_int(self._pick(interact, "sharedCount", "shared_count"))

            publish_text = clean_line(self._extract_publish_time_text(note_card))
            publish_time = self._parse_publish_time(publish_text)

            xsec_token = str(feed.get("xsecToken") or feed.get("xsec_token") or "").strip()
            note_url = f"https://www.xiaohongshu.com/explore/{note_id}"
            if xsec_token:
                note_url = f"{note_url}?xsec_token={xsec_token}&xsec_source=pc_search"

            raw_json = json.dumps(feed, ensure_ascii=False)
            notes.append(
                NoteRecord(
                    run_id=run_id,
                    keyword=keyword,
                    note_id=note_id,
                    title=title,
                    author=author,
                    publish_time=publish_time,
                    publish_time_text=publish_text,
                    like_count=like_count,
                    comment_count=comment_count,
                    share_count=share_count,
                    url=note_url,
                    raw_json=raw_json[:20000],
                    xsec_token=xsec_token,
                )
            )

        notes.sort(key=lambda item: item.publish_time, reverse=True)
        return notes[:max_results]

    def enrich_note_details(self, notes: list[NoteRecord], max_notes: int) -> None:
        script = Path(__file__).resolve().parents[2] / "scripts" / "xhs_detail_fetch.js"
        if not script.exists():
            self.logger.warning("detail script not found: %s", script)
            return

        target_notes = notes[: max(0, max_notes)]
        for note in target_notes:
            if not note.xsec_token:
                continue
            payload = self._run_detail_script(
                script_path=str(script),
                feed_id=note.note_id,
                xsec_token=note.xsec_token,
            )
            if not payload.get("success"):
                continue

            detail_text = self._sanitize_detail_text(str(payload.get("detail_text") or ""))
            comments_preview = self._sanitize_comments_preview(str(payload.get("comments_preview") or ""))
            blocked_by_risk_page = bool(payload.get("blocked_by_risk_page"))

            if detail_text:
                note.detail_text = detail_text[:1500]
            elif blocked_by_risk_page:
                self.logger.info("detail blocked by risk page, note=%s", note.note_id)

            if comments_preview:
                note.comments_preview = comments_preview[:700]

            if note.comment_count <= 0:
                count_text = str(payload.get("comment_count_text") or "").strip()
                parsed = self._to_int_from_text(count_text)
                if parsed > 0:
                    note.comment_count = parsed

    def _run_json(self, tail_args: list[str]) -> dict:
        cmd = [self.cfg.command, *(self.cfg.args or []), *tail_args]
        env = os.environ.copy()
        env["PUPPETEER_EXECUTABLE_PATH"] = self.cfg.browser_path
        env["PUPPETEER_SKIP_DOWNLOAD"] = "true"

        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=self.cfg.command_timeout_seconds,
            env=env,
        )
        output = (proc.stdout or "").strip()
        if not output:
            output = (proc.stderr or "").strip()
        payload = self._parse_json_from_text(output)
        if payload is None:
            raise XHSCollectorError(f"xhs output is not json: {output}")
        return payload

    def _run_search_payload(self, keyword: str, max_results: int) -> dict:
        sort = self._normalize_search_sort(self.cfg.search_sort)
        if sort == "general":
            return self._run_json(["search", "-k", keyword, "--compact"])

        self.logger.info("xhs search with explicit sort=%s", sort)
        payload: dict
        try:
            payload = self._run_search_script(keyword=keyword, sort=sort, max_results=max_results)
        except Exception as exc:
            self.logger.warning(
                "xhs explicit sort=%s request failed (%s), fallback to default search",
                sort,
                exc,
            )
            return self._run_json(["search", "-k", keyword, "--compact"])

        if payload.get("success"):
            return payload

        reason = self._summarize_search_error(payload)
        self.logger.warning(
            "xhs explicit sort=%s failed (%s), fallback to default search",
            sort,
            reason,
        )
        try:
            fallback = self._run_json(["search", "-k", keyword, "--compact"])
            if isinstance(fallback, dict):
                meta = fallback.get("meta")
                if not isinstance(meta, dict):
                    meta = {}
                meta["fallback_from_sort"] = sort
                meta["fallback_reason"] = reason
                fallback["meta"] = meta
            return fallback
        except Exception as exc:
            self.logger.warning("xhs fallback search also failed: %s", exc)
            return payload

    def _run_search_script(self, keyword: str, sort: str, max_results: int) -> dict:
        script = Path(__file__).resolve().parents[2] / "scripts" / "xhs_search_fetch.js"
        if not script.exists():
            raise XHSCollectorError(f"search script not found: {script}")

        cmd = [
            self.cfg.command,
            str(script),
            "--keyword",
            keyword,
            "--browser-path",
            self.cfg.browser_path,
            "--sort",
            sort,
            "--page-size",
            str(max(1, int(max_results))),
            "--timeout-ms",
            str(self.cfg.command_timeout_seconds * 1000),
        ]

        cookies_file = Path.home() / ".xhs-mcp" / "cookies.json"
        if cookies_file.exists():
            cmd.extend(["--cookies-file", str(cookies_file)])

        vendor_dir = self._infer_vendor_dir()
        if vendor_dir:
            cmd.extend(["--vendor-dir", vendor_dir])

        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=self.cfg.command_timeout_seconds + 20,
            env=os.environ.copy(),
        )
        output = (proc.stdout or "").strip()
        if not output:
            output = (proc.stderr or "").strip()
        payload = self._parse_json_from_text(output)
        if payload is None:
            raise XHSCollectorError(f"search script output is not json: {output[:600]}")
        return payload

    def _infer_vendor_dir(self) -> str:
        project_default = Path(__file__).resolve().parents[2] / "vendor" / "xhs-mcp"

        args = self.cfg.args or []
        if args:
            candidate = Path(str(args[0]))
            try:
                if candidate.name.lower() == "xhs-mcp.js" and candidate.parent.name.lower() == "dist":
                    base = candidate.parent.parent
                    if base.exists():
                        return str(base.resolve())
            except Exception:
                pass

        if project_default.exists():
            return str(project_default.resolve())
        return ""

    def _run_detail_script(self, script_path: str, feed_id: str, xsec_token: str) -> dict:
        cmd = [
            self.cfg.command,
            script_path,
            "--feed-id",
            feed_id,
            "--xsec-token",
            xsec_token,
            "--browser-path",
            self.cfg.browser_path,
            "--timeout-ms",
            str(self.cfg.command_timeout_seconds * 1000),
        ]
        cookies_file = Path.home() / ".xhs-mcp" / "cookies.json"
        if cookies_file.exists():
            cmd.extend(["--cookies-file", str(cookies_file)])
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=self.cfg.command_timeout_seconds + 10,
            env=os.environ.copy(),
        )
        output = (proc.stdout or "").strip()
        if not output:
            output = (proc.stderr or "").strip()
        payload = self._parse_json_from_text(output)
        if payload is None:
            return {"success": False, "error": "invalid_detail_output", "raw": output[:300]}
        return payload

    @staticmethod
    def _parse_json_from_text(text: str) -> dict | None:
        if not text:
            return None
        start = text.find("{")
        end = text.rfind("}")
        if start < 0 or end < 0 or end <= start:
            return None
        try:
            return json.loads(text[start : end + 1])
        except json.JSONDecodeError:
            return None

    @staticmethod
    def _summarize_search_error(payload: dict) -> str:
        if not isinstance(payload, dict):
            return "invalid_payload"

        candidates = [
            payload.get("error"),
            payload.get("message"),
            payload.get("code"),
            payload.get("status"),
        ]

        response = payload.get("response")
        if isinstance(response, dict):
            candidates.extend(
                [
                    response.get("msg"),
                    response.get("message"),
                    response.get("code"),
                    response.get("status"),
                ]
            )
            data = response.get("data")
            if isinstance(data, dict):
                candidates.extend([data.get("msg"), data.get("message"), data.get("code")])

        detail = payload.get("detail")
        if isinstance(detail, dict):
            candidates.extend([detail.get("error"), detail.get("message"), detail.get("code")])

        for item in candidates:
            text = str(item or "").strip()
            if text:
                return text[:240]
        return "unknown_error"

    @staticmethod
    def _normalize_search_sort(value: str) -> str:
        raw = str(value or "general").strip().lower()
        alias = {
            "latest": "time_descending",
            "newest": "time_descending",
            "time": "time_descending",
            "hot": "popularity_descending",
            "likes": "popularity_descending",
            "comments": "comment_descending",
            "collects": "collect_descending",
        }
        mapped = alias.get(raw, raw)
        allowed = {
            "general",
            "time_descending",
            "popularity_descending",
            "comment_descending",
            "collect_descending",
        }
        return mapped if mapped in allowed else "general"

    @staticmethod
    def _pick(data: dict, *keys: str):
        for key in keys:
            if key in data and data[key] is not None:
                return data[key]
        return None

    @staticmethod
    def _to_int(value) -> int:
        try:
            if value is None:
                return 0
            text = str(value).strip().replace(",", "")
            if not text:
                return 0
            return int(float(text))
        except Exception:
            return 0

    @staticmethod
    def _to_int_from_text(value: str) -> int:
        m = re.search(r"(\d+)", value or "")
        if not m:
            return 0
        try:
            return int(m.group(1))
        except Exception:
            return 0

    @staticmethod
    def _extract_publish_time_text(note_card: dict) -> str:
        corner = note_card.get("cornerTagInfo")
        if not isinstance(corner, list):
            corner = note_card.get("corner_tag_info", [])
        if isinstance(corner, list):
            for item in corner:
                if not isinstance(item, dict):
                    continue
                if item.get("type") == "publish_time":
                    text = str(item.get("text") or "").strip()
                    if text:
                        return text
        return ""

    @staticmethod
    def _sanitize_detail_text(text: str) -> str:
        value = clean_line(text)
        if not value:
            return ""
        blocked_patterns = [
            r"网络环境存在风险",
            r"访问受限",
            r"返回首页",
            r"请稍后重试",
            r"异常请求",
        ]
        if any(re.search(pat, value, flags=re.IGNORECASE) for pat in blocked_patterns):
            return ""
        return clean_line(value)

    @staticmethod
    def _sanitize_comments_preview(text: str) -> str:
        value = clean_line(text)
        if not value:
            return ""

        parts = [p.strip() for p in value.split("|") if p.strip()]
        cleaned_parts = []
        noise_patterns = [
            r"[©\u00a9]?\s*\d{4}-\d{4}",
            r"漏\s*\d{4}",
            r"行吟信息科技",
            r"琛屽悷淇℃伅绉戞妧",
            r"地址[:：]",
            r"鍦板潃",
            r"电话[:：]",
            r"鐢佃瘽",
            r"创作服务",
            r"鍒涗綔鏈嶅姟",
            r"直播管理",
            r"鐩存挱绠＄悊",
            r"小红书",
            r"灏忕孩涔",
        ]
        for part in parts:
            if len(part) < 3:
                continue
            if re.fullmatch(r"(赞|回复|展开|收起|查看更多)\d*", part):
                continue
            if any(re.search(pat, part, flags=re.IGNORECASE) for pat in noise_patterns):
                continue
            cleaned_parts.append(part)

        uniq = []
        for item in cleaned_parts:
            if item not in uniq:
                uniq.append(item)
        return clean_line(" | ".join(uniq[:8]))

    def _parse_publish_time(self, text: str) -> datetime:
        now = datetime.now(self.tz)
        if not text:
            return now

        # Common CN relative time formats.
        if re.match(r"^(刚刚|刚才)$", text):
            return now

        m = re.match(r"^(\d+)\s*秒前$", text)
        if m:
            return now - timedelta(seconds=int(m.group(1)))

        m = re.match(r"^(\d+)\s*分钟前$", text)
        if m:
            return now - timedelta(minutes=int(m.group(1)))

        m = re.match(r"^(\d+)\s*小时前$", text)
        if m:
            return now - timedelta(hours=int(m.group(1)))

        m = re.match(r"^(\d+)\s*天前$", text)
        if m:
            return now - timedelta(days=int(m.group(1)))

        m = re.match(r"^昨天\s*(\d{1,2}):(\d{2})$", text)
        if m:
            hour = int(m.group(1))
            minute = int(m.group(2))
            yday = now - timedelta(days=1)
            return datetime(yday.year, yday.month, yday.day, hour, minute, tzinfo=self.tz)

        # Backward compatibility for legacy mojibake time text.
        m = re.match(r"^(\d+)\s*澶╁墠$", text)
        if m:
            return now - timedelta(days=int(m.group(1)))

        m = re.match(r"^(\d+)\s*灏忔椂鍓?", text)
        if m:
            return now - timedelta(hours=int(m.group(1)))

        m = re.match(r"^(\d+)\s*鍒嗛挓鍓?", text)
        if m:
            return now - timedelta(minutes=int(m.group(1)))

        m = re.match(r"^(\d{2})-(\d{2})$", text)
        if m:
            month = int(m.group(1))
            day = int(m.group(2))
            year = now.year
            candidate = datetime(year, month, day, tzinfo=self.tz)
            if candidate > now + timedelta(days=1):
                candidate = datetime(year - 1, month, day, tzinfo=self.tz)
            return candidate

        m = re.match(r"^(\d{4})-(\d{2})-(\d{2})$", text)
        if m:
            return datetime(int(m.group(1)), int(m.group(2)), int(m.group(3)), tzinfo=self.tz)

        return now
