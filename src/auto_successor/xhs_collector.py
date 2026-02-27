from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
import json
import os
import re
import shutil
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
        self._sync_selected_account_to_active()
        status = self._run_json(["status", "--compact"])
        if status.get("success") and status.get("loggedIn") is True:
            self._sync_active_to_selected_account()
            return

        self.logger.warning("XHS 登录状态异常：未登录，开始尝试登录流程")
        login = self._run_json(["login", "--timeout", str(self.cfg.login_timeout_seconds)])
        if not login.get("success"):
            raise XHSCollectorError(f"xhs login failed: {login}")

        status = self._run_json(["status", "--compact"])
        if not (status.get("success") and status.get("loggedIn") is True):
            raise XHSCollectorError(f"xhs status still not logged in after login: {status}")
        self._sync_active_to_selected_account()

    def search_notes(self, run_id: str, keyword: str, max_results: int) -> list[NoteRecord]:
        payload = self._run_search_payload(keyword=keyword, max_results=max_results)
        if not payload.get("success"):
            raise XHSCollectorError(f"xhs search failed: {payload}")

        feeds = payload.get("feeds", [])
        if not isinstance(feeds, list):
            feeds = []

        notes: list[NoteRecord] = []
        for index, feed in enumerate(feeds):
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
            prefill_detail = self._extract_prefill_detail(note_card=note_card, title=title)

            publish_text = clean_line(self._extract_publish_time_text(note_card))
            publish_time, publish_time_quality = self._parse_publish_time_with_quality(publish_text)
            if publish_time_quality != "parsed":
                # Keep source list order for notes with unparsed time text.
                publish_time = publish_time - timedelta(seconds=max(0, int(index)))

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
                    publish_time_quality=publish_time_quality,
                    like_count=like_count,
                    comment_count=comment_count,
                    share_count=share_count,
                    url=note_url,
                    raw_json=raw_json[:20000],
                    xsec_token=xsec_token,
                    detail_text=prefill_detail[:1500] if prefill_detail else "",
                )
            )

        notes.sort(key=lambda item: (item.publish_time, item.note_id), reverse=True)
        return notes[:max_results]

    def enrich_note_details(self, notes: list[NoteRecord], max_notes: int) -> dict[str, int]:
        script = Path(__file__).resolve().parents[2] / "scripts" / "xhs_detail_fetch.js"
        if not script.exists():
            self.logger.warning("详情抓取脚本不存在：%s", script)
            return {
                "target_notes": 0,
                "attempted": 0,
                "success": 0,
                "failed": 0,
                "skipped_no_token": 0,
                "detail_filled": 0,
                "detail_missing": 0,
                "blocked": 0,
            }

        target_notes = notes[: max(0, max_notes)]
        stats = {
            "target_notes": len(target_notes),
            "attempted": 0,
            "success": 0,
            "failed": 0,
            "skipped_no_token": 0,
            "detail_filled": 0,
            "detail_missing": 0,
            "blocked": 0,
        }
        fetch_candidates: list[NoteRecord] = []
        for note in target_notes:
            if str(note.xsec_token or "").strip():
                fetch_candidates.append(note)
            else:
                stats["skipped_no_token"] += 1

        stats["attempted"] = len(fetch_candidates)
        detail_workers = self._effective_detail_workers(
            configured_workers=getattr(self.cfg, "detail_workers", 1),
            total=len(fetch_candidates),
        )
        self.logger.info(
            "详情抓取开始 | target=%s | attempted=%s | skipped_no_token=%s | workers=%s",
            len(target_notes),
            len(fetch_candidates),
            stats["skipped_no_token"],
            detail_workers,
        )

        if detail_workers <= 1:
            for note in fetch_candidates:
                try:
                    payload = self._run_detail_script(
                        script_path=str(script),
                        feed_id=note.note_id,
                        xsec_token=note.xsec_token,
                    )
                except Exception as exc:
                    payload = {"success": False, "error": f"detail_exception:{exc}"}
                self._apply_detail_payload(note=note, payload=payload, stats=stats)
        else:
            with ThreadPoolExecutor(max_workers=detail_workers, thread_name_prefix="xhs-detail") as executor:
                future_map = {
                    executor.submit(
                        self._run_detail_script,
                        script_path=str(script),
                        feed_id=note.note_id,
                        xsec_token=note.xsec_token,
                    ): note
                    for note in fetch_candidates
                }
                done = 0
                total = len(fetch_candidates)
                progress_step = max(1, total // 5) if total > 0 else 1
                for future in as_completed(future_map):
                    note = future_map[future]
                    try:
                        payload = future.result()
                    except Exception as exc:
                        payload = {"success": False, "error": f"detail_exception:{exc}"}
                    self._apply_detail_payload(note=note, payload=payload, stats=stats)
                    done += 1
                    if done == total or done % progress_step == 0:
                        pct = int(round(done * 100 / max(1, total)))
                        self.logger.info("[阶段进度] 正文抓取 %s/%s (%s%%)", done, total, pct)

        self.logger.info(
            "详情抓取完成 | attempted=%s | success=%s | failed=%s | blocked=%s | detail_filled=%s",
            stats["attempted"],
            stats["success"],
            stats["failed"],
            stats["blocked"],
            stats["detail_filled"],
        )
        stats["detail_missing"] = sum(1 for item in target_notes if not str(item.detail_text or "").strip())
        return stats

    @staticmethod
    def _effective_detail_workers(configured_workers: int, total: int) -> int:
        if total <= 1:
            return 1
        workers = max(1, int(configured_workers or 1))
        workers = min(workers, 8)
        return min(workers, total)

    def _apply_detail_payload(self, *, note: NoteRecord, payload: dict, stats: dict[str, int]) -> None:
        if not isinstance(payload, dict) or not payload.get("success"):
            stats["failed"] += 1
            self.logger.info(
                "详情抓取失败 | note=%s | error=%s",
                note.note_id,
                str((payload or {}).get("error") or (payload or {}).get("message") or "unknown"),
            )
            return

        stats["success"] += 1
        detail_text = self._sanitize_detail_text(str(payload.get("detail_text") or ""))
        comments_preview = self._sanitize_comments_preview(
            str(payload.get("poster_comments_preview") or payload.get("comments_preview") or "")
        )
        blocked_by_risk_page = bool(payload.get("blocked_by_risk_page"))

        if detail_text:
            note.detail_text = detail_text[:1500]
            stats["detail_filled"] += 1
        elif blocked_by_risk_page:
            stats["blocked"] += 1
            self.logger.info("详情抓取被风控页拦截：note=%s", note.note_id)
        elif not str(note.detail_text or "").strip():
            fallback = self._sanitize_detail_fallback(str(payload.get("title") or note.title or ""))
            if fallback:
                note.detail_text = fallback[:1500]
                stats["detail_filled"] += 1

        if comments_preview:
            note.comments_preview = comments_preview[:700]

        if note.comment_count <= 0:
            count_text = str(payload.get("comment_count_text") or "").strip()
            parsed = self._to_int_from_text(count_text)
            if parsed > 0:
                note.comment_count = parsed

    def probe_status_diagnostics(self) -> dict:
        cookies_file = self._resolve_cookies_file()
        script_path = self._resolve_cli_script_path()
        command = str(self.cfg.command or "").strip() or "node"
        cli_present = shutil.which(command) is not None
        diagnostics = {
            "checked_at": datetime.utcnow().isoformat(timespec="seconds") + "Z",
            "command": command,
            "args": list(self.cfg.args or []),
            "cli_present": cli_present,
            "script_path": str(script_path) if script_path else "",
            "script_exists": bool(script_path and script_path.exists()),
            "cookies_file": str(cookies_file),
            "cookie_file_ready": cookies_file.exists(),
            "mcp_connect": False,
            "login_status": False,
            "reason": "",
            "raw_status": {},
        }
        if not cli_present:
            diagnostics["reason"] = "xhs command not found"
            return diagnostics

        try:
            status = self._run_json(["status", "--compact"])
        except Exception as exc:
            diagnostics["reason"] = str(exc)[:280]
            return diagnostics

        diagnostics["mcp_connect"] = True
        diagnostics["raw_status"] = status if isinstance(status, dict) else {}
        logged_in = bool(
            status.get("loggedIn")
            or status.get("logged_in")
            or status.get("isLogin")
            or status.get("is_login")
        )
        diagnostics["login_status"] = logged_in
        if not logged_in:
            diagnostics["reason"] = "not_logged_in"
        return diagnostics

    def _run_json(self, tail_args: list[str]) -> dict:
        cmd = [self.cfg.command, *(self.cfg.args or []), *tail_args]
        env = os.environ.copy()
        env["PUPPETEER_EXECUTABLE_PATH"] = self.cfg.browser_path
        env["PUPPETEER_SKIP_DOWNLOAD"] = "true"

        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=False,
            timeout=self.cfg.command_timeout_seconds,
            env=env,
        )
        output = self._decode_json_output(proc.stdout or b"").strip()
        if not output:
            output = self._decode_json_output(proc.stderr or b"").strip()
        payload = self._parse_json_from_text(output)
        if payload is None:
            raise XHSCollectorError(f"xhs output is not json: {output}")
        return payload

    def _run_search_payload(self, keyword: str, max_results: int) -> dict:
        sort = self._normalize_search_sort(self.cfg.search_sort)
        if sort == "general":
            return self._run_json(["search", "-k", keyword, "--compact"])

        self.logger.info("XHS 搜索：使用显式排序参数 sort=%s", sort)
        payload: dict
        try:
            payload = self._run_search_script(keyword=keyword, sort=sort, max_results=max_results)
        except Exception as exc:
            self.logger.warning(
                "XHS 显式排序请求失败 sort=%s（%s），回退默认搜索",
                sort,
                exc,
            )
            return self._run_json(["search", "-k", keyword, "--compact"])

        if payload.get("success"):
            return payload

        reason = self._summarize_search_error(payload)
        self.logger.warning(
            "XHS 显式排序失败 sort=%s（%s），回退默认搜索",
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
            self.logger.warning("XHS 默认搜索回退也失败：%s", exc)
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

        cookies_file = self._resolve_cookies_file()
        if cookies_file.exists():
            cmd.extend(["--cookies-file", str(cookies_file)])

        vendor_dir = self._infer_vendor_dir()
        if vendor_dir:
            cmd.extend(["--vendor-dir", vendor_dir])

        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=False,
            timeout=self.cfg.command_timeout_seconds + 20,
            env=os.environ.copy(),
        )
        output = self._decode_json_output(proc.stdout or b"").strip()
        if not output:
            output = self._decode_json_output(proc.stderr or b"").strip()
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
        cookies_file = self._resolve_cookies_file()
        if cookies_file.exists():
            cmd.extend(["--cookies-file", str(cookies_file)])
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=False,
            timeout=self.cfg.command_timeout_seconds + 10,
            env=os.environ.copy(),
        )
        output = self._decode_json_output(proc.stdout or b"").strip()
        if not output:
            output = self._decode_json_output(proc.stderr or b"").strip()
        payload = self._parse_json_from_text(output)
        if payload is None:
            return {"success": False, "error": "invalid_detail_output", "raw": output[:300]}
        return payload

    def _active_cookies_file(self) -> Path:
        return Path.home() / ".xhs-mcp" / "cookies.json"

    def _resolve_cookies_file(self) -> Path:
        account = str(getattr(self.cfg, "account", "") or "").strip()
        if not account or account.lower() == "default":
            return self._active_cookies_file()

        base_dir = Path(str(getattr(self.cfg, "account_cookies_dir", "~/.xhs-mcp/accounts"))).expanduser()
        if account.lower().endswith(".json"):
            flat = base_dir / account
            nested = base_dir / account[: -len(".json")] / "cookies.json"
        else:
            flat = base_dir / f"{account}.json"
            nested = base_dir / account / "cookies.json"

        if flat.exists():
            return flat
        if nested.exists():
            return nested
        return flat

    def _sync_selected_account_to_active(self) -> None:
        selected = self._resolve_cookies_file()
        active = self._active_cookies_file()
        try:
            if selected.resolve() == active.resolve():
                return
        except Exception:
            pass
        if not selected.exists():
            return
        active.parent.mkdir(parents=True, exist_ok=True)
        try:
            shutil.copyfile(selected, active)
        except Exception as exc:
            self.logger.warning("同步账号 cookies 到 active 失败：%s", exc)

    def _sync_active_to_selected_account(self) -> None:
        selected = self._resolve_cookies_file()
        active = self._active_cookies_file()
        try:
            if selected.resolve() == active.resolve():
                return
        except Exception:
            pass
        if not active.exists():
            return
        selected.parent.mkdir(parents=True, exist_ok=True)
        try:
            shutil.copyfile(active, selected)
        except Exception as exc:
            self.logger.warning("同步 active cookies 到账号文件失败：%s", exc)

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

    @classmethod
    def _decode_json_output(cls, raw: bytes) -> str:
        if not raw:
            return ""
        for encoding in ("utf-8", "utf-8-sig", "gb18030"):
            try:
                text = raw.decode(encoding)
            except Exception:
                continue
            if cls._parse_json_from_text(text) is not None:
                return text
        return raw.decode("utf-8", errors="replace")

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
        if XHSMcpCliCollector._is_link_noise_text(value):
            return ""
        value = XHSMcpCliCollector._remove_inline_urls(value)
        if len(value) < 6:
            return ""
        return clean_line(value)

    @staticmethod
    def _sanitize_detail_fallback(text: str) -> str:
        value = clean_line(text)
        if not value:
            return ""
        if XHSMcpCliCollector._is_link_noise_text(value):
            return ""
        value = XHSMcpCliCollector._remove_inline_urls(value)
        if len(value) < 4:
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
            if XHSMcpCliCollector._is_link_noise_text(part):
                continue
            if any(re.search(pat, part, flags=re.IGNORECASE) for pat in noise_patterns):
                continue
            cleaned_parts.append(part)

        uniq = []
        for item in cleaned_parts:
            if item not in uniq:
                uniq.append(item)
        return clean_line(" | ".join(uniq[:8]))

    @staticmethod
    def _remove_inline_urls(text: str) -> str:
        value = str(text or "")
        value = re.sub(r"!\[[^\]]*\]\(\s*https?://[^)]+\)", " ", value, flags=re.IGNORECASE)
        value = re.sub(r"https?://[^\s|]+", " ", value, flags=re.IGNORECASE)
        value = re.sub(r"\s+", " ", value).strip()
        return value

    @staticmethod
    def _is_link_noise_text(text: str) -> bool:
        value = str(text or "").strip()
        if not value:
            return True
        if re.fullmatch(r"!\[[^\]]*\]\(\s*https?://[^)]+\)", value, flags=re.IGNORECASE):
            return True
        if re.fullmatch(r"(?:https?://\S+\s*[|,，;；/]?\s*)+", value, flags=re.IGNORECASE):
            return True
        urls = re.findall(r"https?://[^\s|]+", value, flags=re.IGNORECASE)
        if not urls:
            return False
        non_url = re.sub(r"https?://[^\s|]+", " ", value, flags=re.IGNORECASE)
        cjk = len(re.findall(r"[\u4e00-\u9fff]", non_url))
        alpha_num = len(re.findall(r"[A-Za-z0-9]", non_url))
        image_link_count = 0
        for url in urls:
            if re.search(r"\.(?:png|jpe?g|gif|webp|bmp|heic|svg)(?:\?|$)", url, flags=re.IGNORECASE):
                image_link_count += 1
            elif re.search(r"(xhscdn|xhslink|sns-webpic|imageView2)", url, flags=re.IGNORECASE):
                image_link_count += 1
        if image_link_count > 0 and (cjk + alpha_num) < 12:
            return True
        if len(urls) >= 1 and (cjk + alpha_num) < 6:
            return True
        return False

    @classmethod
    def _extract_prefill_detail(cls, *, note_card: dict, title: str) -> str:
        if not isinstance(note_card, dict):
            return cls._sanitize_detail_fallback(title)

        candidates: list[str] = []

        def push(value: object) -> None:
            text = clean_line(str(value or ""))
            if text:
                candidates.append(text)

        direct_keys = (
            "desc",
            "description",
            "content",
            "noteText",
            "note_text",
            "displayTitle",
            "display_title",
            "title",
        )
        for key in direct_keys:
            push(note_card.get(key))

        queue: list[tuple[str, object, int]] = [("root", note_card, 0)]
        visited = 0
        while queue and visited < 300:
            path, value, depth = queue.pop(0)
            visited += 1
            if value is None:
                continue
            if isinstance(value, str):
                if re.search(r"(desc|content|text|note|caption|body|title)", path, flags=re.IGNORECASE):
                    push(value)
                continue
            if depth >= 2:
                continue
            if isinstance(value, dict):
                for key, nested in value.items():
                    queue.append((f"{path}.{key}", nested, depth + 1))
            elif isinstance(value, list):
                for idx, nested in enumerate(value[:20]):
                    queue.append((f"{path}[{idx}]", nested, depth + 1))

        for item in candidates:
            normalized = cls._sanitize_detail_text(item)
            if normalized:
                return normalized
        for item in candidates:
            normalized = cls._sanitize_detail_fallback(item)
            if normalized:
                return normalized
        return cls._sanitize_detail_fallback(title)

    def _resolve_cli_script_path(self) -> Path | None:
        args = self.cfg.args or []
        if not args:
            return None
        raw = str(args[0] or "").strip()
        if not raw:
            return None
        p = Path(raw)
        if not p.is_absolute():
            p = (Path(__file__).resolve().parents[2] / p).resolve()
        return p

    def _parse_publish_time(self, text: str) -> datetime:
        value, _ = self._parse_publish_time_with_quality(text)
        return value

    def _parse_publish_time_with_quality(
        self,
        text: str,
        reference: datetime | None = None,
    ) -> tuple[datetime, str]:
        now = reference.astimezone(self.tz) if isinstance(reference, datetime) else datetime.now(self.tz)
        raw = clean_line(text)
        if not raw:
            return now, "fallback"

        normalized = self._normalize_publish_time_text(raw)
        if not normalized:
            return now, "fallback"

        if re.match(r"^(刚刚|刚才)$", normalized):
            return now, "parsed"

        m = re.match(r"^(\d+)\s*秒前$", normalized)
        if m:
            return now - timedelta(seconds=int(m.group(1))), "parsed"

        m = re.match(r"^(\d+)\s*分钟前$", normalized)
        if m:
            return now - timedelta(minutes=int(m.group(1))), "parsed"

        m = re.match(r"^(\d+)\s*小时前$", normalized)
        if m:
            return now - timedelta(hours=int(m.group(1))), "parsed"

        m = re.match(r"^(\d+)\s*天前$", normalized)
        if m:
            return now - timedelta(days=int(m.group(1))), "parsed"

        # Backward compatibility for legacy mojibake time text.
        m = re.match(r"^(\d+)\s*澶╁墠$", normalized)
        if m:
            return now - timedelta(days=int(m.group(1))), "parsed"

        m = re.match(r"^(\d+)\s*灏忔椂鍓?", normalized)
        if m:
            return now - timedelta(hours=int(m.group(1))), "parsed"

        m = re.match(r"^(\d+)\s*鍒嗛挓鍓?", normalized)
        if m:
            return now - timedelta(minutes=int(m.group(1))), "parsed"

        m = re.match(r"^今天\s*(\d{1,2}):(\d{2})$", normalized)
        if m:
            candidate = self._build_datetime(now.year, now.month, now.day, int(m.group(1)), int(m.group(2)))
            if candidate is not None:
                return candidate, "parsed"

        m = re.match(r"^昨天\s*(\d{1,2}):(\d{2})$", normalized)
        if m:
            yday = now - timedelta(days=1)
            candidate = self._build_datetime(yday.year, yday.month, yday.day, int(m.group(1)), int(m.group(2)))
            if candidate is not None:
                return candidate, "parsed"

        m = re.match(r"^前天\s*(\d{1,2}):(\d{2})$", normalized)
        if m:
            d2 = now - timedelta(days=2)
            candidate = self._build_datetime(d2.year, d2.month, d2.day, int(m.group(1)), int(m.group(2)))
            if candidate is not None:
                return candidate, "parsed"

        # yyyy-mm-dd[ HH:MM]
        m = re.search(
            r"(\d{4})\s*[-/.年]\s*(\d{1,2})\s*[-/.月]\s*(\d{1,2})(?:日)?(?:\s+(\d{1,2}):(\d{2}))?",
            normalized,
        )
        if m:
            year = int(m.group(1))
            month = int(m.group(2))
            day = int(m.group(3))
            hour = int(m.group(4)) if m.group(4) else 0
            minute = int(m.group(5)) if m.group(5) else 0
            candidate = self._build_datetime(year, month, day, hour, minute)
            if candidate is not None:
                return candidate, "parsed"

        # mm-dd[ HH:MM], mm/dd[ HH:MM], mm.dd[ HH:MM], m月d日[ HH:MM]
        m = re.search(
            r"(?<!\d)(\d{1,2})\s*[-/.月]\s*(\d{1,2})(?:日)?(?:\s+(\d{1,2}):(\d{2}))?(?!\d)",
            normalized,
        )
        if m:
            month = int(m.group(1))
            day = int(m.group(2))
            hour = int(m.group(3)) if m.group(3) else 0
            minute = int(m.group(4)) if m.group(4) else 0
            candidate = self._build_datetime(now.year, month, day, hour, minute)
            if candidate is not None:
                if candidate > now + timedelta(days=1):
                    candidate = self._build_datetime(now.year - 1, month, day, hour, minute)
                if candidate is not None:
                    return candidate, "parsed"

        return now, "fallback"

    @staticmethod
    def _normalize_publish_time_text(text: str) -> str:
        value = clean_line(text)
        if not value:
            return ""

        value = value.replace("：", ":")
        value = value.replace("／", "/")
        value = value.replace("．", ".")
        value = value.replace("—", "-")
        value = value.replace("–", "-")
        value = value.replace("·", " ")
        value = value.replace("|", " ")

        # Remove common prefixes.
        value = re.sub(r"^(发布于|发表于|更新于|编辑于|发布|更新)\s*", "", value, flags=re.IGNORECASE)
        value = re.sub(r"\s+", " ", value)
        return value.strip()

    def _build_datetime(
        self,
        year: int,
        month: int,
        day: int,
        hour: int = 0,
        minute: int = 0,
    ) -> datetime | None:
        try:
            return datetime(year, month, day, hour, minute, tzinfo=self.tz)
        except Exception:
            return None
