from __future__ import annotations

import json
import time
from datetime import datetime
from pathlib import Path
import csv

from openpyxl import Workbook, load_workbook

from .models import JobRecord, NoteRecord, SendLogRecord, SummaryRecord

RAW_HEADERS = [
    "run_id",
    "keyword",
    "note_id",
    "title",
    "author",
    "publish_time",
    "publish_timestamp",
    "publish_time_text",
    "like_count",
    "comment_count",
    "share_count",
    "url",
    "xsec_token",
    "detail_text",
    "comments_preview",
    "fetched_at",
    "raw_json",
]

SUMMARY_HEADERS = [
    "run_id",
    "note_id",
    "keyword",
    "publish_time",
    "publish_timestamp",
    "title",
    "author",
    "summary",
    "confidence",
    "risk_flags",
    "url",
    "created_at",
]

SEND_HEADERS = [
    "run_id",
    "note_id",
    "channel",
    "send_status",
    "send_response",
    "sent_at",
]

JOB_HEADERS = [
    "run_id",
    "Company",
    "Position",
    "Location",
    "Requirements",
    "Link",
    "PostID",
    "publish_time",
    "comment_count",
    "comments_preview",
    "source_title",
]


class ExcelStore:
    def __init__(self, excel_path: str) -> None:
        self.path = Path(excel_path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def write(
        self,
        raw: list[NoteRecord],
        summaries: list[SummaryRecord],
        send_logs: list[SendLogRecord],
        jobs: list[JobRecord] | None = None,
    ) -> None:
        wb = self._load_or_create()

        raw_rows = self._merge_raw_rows(wb["raw_notes"], raw)
        summary_rows = self._merge_summary_rows(wb["succession_summary"], summaries)
        send_rows = self._merge_send_rows(wb["send_log"], send_logs)
        job_rows = self._merge_job_rows(wb["jobs"], jobs or [])

        self._rewrite_sheet(wb["raw_notes"], RAW_HEADERS, raw_rows)
        self._rewrite_sheet(wb["succession_summary"], SUMMARY_HEADERS, summary_rows)
        self._rewrite_sheet(wb["send_log"], SEND_HEADERS, send_rows)
        self._rewrite_sheet(wb["jobs"], JOB_HEADERS, job_rows)

        try:
            for attempt in range(3):
                try:
                    wb.save(self.path)
                    return
                except PermissionError:
                    if attempt < 2:
                        time.sleep(1.0)
                        continue
                    fallback = self.path.with_name(
                        f"{self.path.stem}.locked-{datetime.now().strftime('%Y%m%d-%H%M%S')}{self.path.suffix}"
                    )
                    wb.save(fallback)
                    return
        finally:
            wb.close()

    def _load_or_create(self):
        if self.path.exists():
            wb = load_workbook(self.path)
            for name, headers in [
                ("raw_notes", RAW_HEADERS),
                ("succession_summary", SUMMARY_HEADERS),
                ("send_log", SEND_HEADERS),
                ("jobs", JOB_HEADERS),
            ]:
                if name not in wb.sheetnames:
                    ws = wb.create_sheet(title=name)
                    ws.append(headers)
            return wb

        wb = Workbook()
        default = wb.active
        wb.remove(default)
        for name, headers in [
            ("raw_notes", RAW_HEADERS),
            ("succession_summary", SUMMARY_HEADERS),
            ("send_log", SEND_HEADERS),
            ("jobs", JOB_HEADERS),
        ]:
            ws = wb.create_sheet(title=name)
            ws.append(headers)
        return wb

    def _rewrite_sheet(self, ws, headers: list[str], rows: list[dict]) -> None:
        ws.delete_rows(1, ws.max_row)
        ws.append(headers)
        for row in rows:
            ws.append([row.get(col, "") for col in headers])

    def _read_sheet_rows(self, ws, headers: list[str]) -> list[dict]:
        rows = []
        for values in ws.iter_rows(min_row=2, values_only=True):
            if not values:
                continue
            row = {headers[i]: values[i] for i in range(min(len(headers), len(values)))}
            rows.append(row)
        return rows

    def _merge_raw_rows(self, ws, raw: list[NoteRecord]) -> list[dict]:
        existing = self._read_sheet_rows(ws, RAW_HEADERS)
        by_note: dict[str, dict] = {str(r.get("note_id") or ""): r for r in existing if r.get("note_id")}

        for note in raw:
            by_note[note.note_id] = {
                "run_id": note.run_id,
                "keyword": note.keyword,
                "note_id": note.note_id,
                "title": note.title,
                "author": note.author,
                "publish_time": note.publish_time.isoformat(),
                "publish_timestamp": int(note.publish_time.timestamp()),
                "publish_time_text": note.publish_time_text,
                "like_count": note.like_count,
                "comment_count": note.comment_count,
                "share_count": note.share_count,
                "url": note.url,
                "xsec_token": note.xsec_token,
                "detail_text": note.detail_text,
                "comments_preview": note.comments_preview,
                "fetched_at": note.fetched_at.isoformat(),
                "raw_json": note.raw_json,
            }

        rows = list(by_note.values())
        rows.sort(key=lambda x: int(x.get("publish_timestamp") or 0), reverse=True)
        return rows

    def _merge_summary_rows(self, ws, summaries: list[SummaryRecord]) -> list[dict]:
        existing = self._read_sheet_rows(ws, SUMMARY_HEADERS)
        by_note: dict[str, dict] = {str(r.get("note_id") or ""): r for r in existing if r.get("note_id")}

        for item in summaries:
            by_note[item.note_id] = {
                "run_id": item.run_id,
                "note_id": item.note_id,
                "keyword": item.keyword,
                "publish_time": item.publish_time.isoformat(),
                "publish_timestamp": int(item.publish_time.timestamp()),
                "title": item.title,
                "author": item.author,
                "summary": item.summary,
                "confidence": round(item.confidence, 4),
                "risk_flags": item.risk_flags,
                "url": item.url,
                "created_at": item.created_at.isoformat(),
            }

        rows = list(by_note.values())
        rows.sort(key=lambda x: int(x.get("publish_timestamp") or 0), reverse=True)
        return rows

    def _merge_send_rows(self, ws, send_logs: list[SendLogRecord]) -> list[dict]:
        existing = self._read_sheet_rows(ws, SEND_HEADERS)
        rows = list(existing)
        for log in send_logs:
            response = log.send_response
            if not isinstance(response, str):
                response = json.dumps(response, ensure_ascii=False)
            rows.append(
                {
                    "run_id": log.run_id,
                    "note_id": log.note_id,
                    "channel": log.channel,
                    "send_status": log.send_status,
                    "send_response": response[:20000],
                    "sent_at": log.sent_at.isoformat(),
                }
            )
        rows.sort(key=lambda x: str(x.get("sent_at") or ""), reverse=True)
        return rows

    def _merge_job_rows(self, ws, jobs: list[JobRecord]) -> list[dict]:
        existing = self._read_sheet_rows(ws, JOB_HEADERS)
        by_post: dict[str, dict] = {str(r.get("PostID") or ""): r for r in existing if r.get("PostID")}
        for job in jobs:
            by_post[job.post_id] = {
                "run_id": job.run_id,
                "Company": job.company,
                "Position": job.position,
                "Location": job.location,
                "Requirements": job.requirements,
                "Link": job.link,
                "PostID": job.post_id,
                "publish_time": job.publish_time.isoformat(),
                "comment_count": job.comment_count,
                "comments_preview": job.comments_preview,
                "source_title": job.source_title,
            }
        rows = list(by_post.values())
        rows.sort(key=lambda x: str(x.get("publish_time") or ""), reverse=True)
        return rows

    def export_jobs_csv(self, csv_path: str) -> None:
        if not self.path.exists():
            return
        wb = load_workbook(self.path, read_only=True)
        try:
            if "jobs" not in wb.sheetnames:
                return
            ws = wb["jobs"]
            rows = self._read_sheet_rows(ws, JOB_HEADERS)
        finally:
            wb.close()

        target = Path(csv_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("w", encoding="utf-8-sig", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["Company", "Position", "Location", "Requirements", "Link", "PostID"])
            for row in rows:
                writer.writerow(
                    [
                        row.get("Company", ""),
                        row.get("Position", ""),
                        row.get("Location", ""),
                        row.get("Requirements", ""),
                        row.get("Link", ""),
                        row.get("PostID", ""),
                    ]
                )
