from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from math import floor

from .job_processor import normalize_job_record, to_job_record
from .llm_enricher import LLMEnricher
from .models import JobRecord, NoteRecord
from .agents_types import ExtractOutcome, FilterOutcome, NoteAgentResult, NoteAgentTask


URGENT_TOKENS = ["急招", "尽快到岗", "马上到岗", "asap", "urgent", "立即入职"]

class IntelligenceAgent:
    def __init__(self, llm_enricher: LLMEnricher, logger) -> None:
        self.llm_enricher = llm_enricher
        self.logger = logger

    def filter_target_notes(self, notes: list[NoteRecord], max_filter_items: int, workers: int = 1) -> FilterOutcome:
        targets: list[NoteRecord] = []
        filtered_out: list[dict] = []
        scores: dict[str, float] = {}
        total = len(notes)
        llm_budget = max(0, int(max_filter_items))
        worker_count = self._effective_workers(workers=workers, total=total)
        progress_step = max(1, total // 5) if total > 0 else 1
        self.logger.info("[阶段] 目标筛选开始：总条数=%s，LLM配额=%s，并行=%s", total, llm_budget, worker_count)

        results: list[tuple[NoteRecord, object] | None] = [None] * total
        if worker_count <= 1:
            for idx, note in enumerate(notes):
                allow_llm = idx < llm_budget
                decision = self.llm_enricher.classify_target(note, allow_llm=allow_llm)
                results[idx] = (note, decision)
                current = idx + 1
                if current == total or current % progress_step == 0:
                    pct = int(round(current * 100 / max(1, total)))
                    self.logger.info("[阶段进度] 目标筛选 %s/%s (%s%%)", current, total, pct)
        else:
            with ThreadPoolExecutor(max_workers=worker_count, thread_name_prefix="filter") as executor:
                future_map = {}
                for idx, note in enumerate(notes):
                    allow_llm = idx < llm_budget
                    future = executor.submit(self.llm_enricher.classify_target, note, allow_llm)
                    future_map[future] = (idx, note)

                completed = 0
                for future in as_completed(future_map):
                    idx, note = future_map[future]
                    try:
                        decision = future.result()
                    except Exception as exc:
                        self.logger.warning("并行筛选异常，回退规则 | note=%s | error=%s", note.note_id, exc)
                        decision = self.llm_enricher.classify_target(note, allow_llm=False)
                    results[idx] = (note, decision)
                    completed += 1
                    if completed == total or completed % progress_step == 0:
                        pct = int(round(completed * 100 / max(1, total)))
                        self.logger.info("[阶段进度] 目标筛选 %s/%s (%s%%)", completed, total, pct)

        for result in results:
            if not result:
                continue
            note, decision = result
            scores[note.note_id] = float(getattr(decision, "score", 0.0))
            if bool(getattr(decision, "is_target", False)):
                targets.append(note)
                continue
            filtered_out.append(
                {
                    "note_id": note.note_id,
                    "title": note.title[:100],
                    "score": round(float(getattr(decision, "score", 0.0)), 4),
                    "reason": str(getattr(decision, "reason", "") or ""),
                    "source": str(getattr(decision, "source", "") or ""),
                }
            )
            self.logger.info(
                "过滤帖子 | note=%s | score=%.2f | source=%s | reason=%s",
                note.note_id,
                float(getattr(decision, "score", 0.0)),
                str(getattr(decision, "source", "") or ""),
                str(getattr(decision, "reason", "") or ""),
            )

        self.logger.info(
            "[阶段进度] 目标筛选完成 %s/%s (100%%) | 命中=%s | 过滤=%s",
            total,
            total,
            len(targets),
            len(filtered_out),
        )

        return FilterOutcome(targets=targets, filtered_out=filtered_out, scores=scores)

    def build_jobs(
        self,
        notes: list[NoteRecord],
        max_job_items: int,
        resume_text: str,
        mode: str,
        workers: int = 1,
    ) -> list[JobRecord]:
        _ = max_job_items  # deprecated: extraction no longer uses per-run LLM budget
        jobs: list[JobRecord] = []
        total = len(notes)
        worker_count = self._effective_workers(workers=workers, total=total)
        progress_step = max(1, total // 5) if total > 0 else 1
        self.logger.info("[阶段] 岗位结构化开始：总条数=%s，LLM=全量尝试，并行=%s", total, worker_count)

        results: list[JobRecord | None] = [None] * total
        if worker_count <= 1:
            for idx, note in enumerate(notes):
                job = to_job_record(note)
                job.mode = mode
                job = self.llm_enricher.enrich_job(note, job, resume_text=resume_text, mode=mode)
                results[idx] = normalize_job_record(job)
                current = idx + 1
                if current == total or current % progress_step == 0:
                    pct = int(round(current * 100 / max(1, total)))
                    self.logger.info("[阶段进度] 岗位结构化 %s/%s (%s%%)", current, total, pct)
        else:
            def _worker(idx: int, note: NoteRecord) -> tuple[int, JobRecord]:
                job = to_job_record(note)
                job.mode = mode
                job = self.llm_enricher.enrich_job(note, job, resume_text=resume_text, mode=mode)
                return idx, normalize_job_record(job)

            with ThreadPoolExecutor(max_workers=worker_count, thread_name_prefix="job") as executor:
                future_map = {executor.submit(_worker, idx, note): (idx, note) for idx, note in enumerate(notes)}
                completed = 0
                for future in as_completed(future_map):
                    idx, note = future_map[future]
                    try:
                        target_idx, job = future.result()
                    except Exception as exc:
                        self.logger.warning("并行岗位提取异常，回退规则 | note=%s | error=%s", note.note_id, exc)
                        fallback_job = normalize_job_record(to_job_record(note))
                        fallback_job.mode = mode
                        target_idx, job = idx, fallback_job
                    results[target_idx] = job
                    completed += 1
                    if completed == total or completed % progress_step == 0:
                        pct = int(round(completed * 100 / max(1, total)))
                        self.logger.info("[阶段进度] 岗位结构化 %s/%s (%s%%)", completed, total, pct)

        jobs = [item for item in results if item is not None]
        jobs.sort(key=lambda item: item.publish_time, reverse=True)
        return jobs

    def extract_target_jobs(
        self,
        notes: list[NoteRecord],
        max_job_items: int,
        resume_text: str,
        mode: str,
        workers: int = 1,
    ) -> ExtractOutcome:
        """
        Backward-compatible wrapper for the per-note NoteAgent model.
        """
        _ = max_job_items  # deprecated: extraction no longer uses per-run LLM budget
        return self.process_notes_with_agents(
            notes=notes,
            resume_text=resume_text,
            mode=mode,
            workers=workers,
        )

    def process_notes_with_agents(
        self,
        *,
        notes: list[NoteRecord],
        resume_text: str,
        mode: str,
        workers: int = 1,
    ) -> ExtractOutcome:
        """
        NoteAgent model:
        - one task per note
        - each task decides target + extracts structured job fields
        - tasks run concurrently with bounded workers
        """
        targets: list[NoteRecord] = []
        jobs: list[JobRecord] = []
        filtered_out: list[dict] = []
        scores: dict[str, float] = {}

        total = len(notes)
        worker_count = self._effective_workers(workers=workers, total=total)
        progress_step = max(1, total // 5) if total > 0 else 1

        tasks = [NoteAgentTask(index=idx, note=note, allow_llm=True) for idx, note in enumerate(notes)]
        results: list[NoteAgentResult | None] = [None] * total

        self.logger.info(
            "[阶段] NoteAgent处理开始：总条数=%s，LLM=全量尝试，并行=%s",
            total,
            worker_count,
        )

        def _run_task(task: NoteAgentTask) -> NoteAgentResult:
            decision, job = self.llm_enricher.extract_target_job(
                task.note,
                resume_text=resume_text,
                mode=mode,
                allow_llm=task.allow_llm,
            )
            return NoteAgentResult(
                index=task.index,
                note=task.note,
                decision=decision,
                job=normalize_job_record(job),
                allow_llm=task.allow_llm,
            )

        if worker_count <= 1:
            for idx, task in enumerate(tasks):
                worker_fallback = False
                worker_error = ""
                try:
                    result = _run_task(task)
                except Exception as exc:
                    worker_fallback = True
                    worker_error = str(exc)
                    self.logger.warning("NoteAgent任务异常，回退规则 | note=%s | error=%s", task.note.note_id, exc)
                    decision, job = self.llm_enricher.extract_target_job(
                        task.note,
                        resume_text=resume_text,
                        mode=mode,
                        allow_llm=False,
                    )
                    result = NoteAgentResult(
                        index=task.index,
                        note=task.note,
                        decision=decision,
                        job=normalize_job_record(job),
                        allow_llm=task.allow_llm,
                        worker_fallback=worker_fallback,
                        error=worker_error,
                    )
                results[idx] = result
                current = idx + 1
                if current == total or current % progress_step == 0:
                    pct = int(round(current * 100 / max(1, total)))
                    self.logger.info("[阶段进度] NoteAgent处理 %s/%s (%s%%)", current, total, pct)
        else:
            with ThreadPoolExecutor(max_workers=worker_count, thread_name_prefix="note-agent") as executor:
                future_map = {executor.submit(_run_task, task): task for task in tasks}
                completed = 0
                for future in as_completed(future_map):
                    task = future_map[future]
                    try:
                        result = future.result()
                    except Exception as exc:
                        self.logger.warning("NoteAgent任务异常，回退规则 | note=%s | error=%s", task.note.note_id, exc)
                        decision, job = self.llm_enricher.extract_target_job(
                            task.note,
                            resume_text=resume_text,
                            mode=mode,
                            allow_llm=False,
                        )
                        result = NoteAgentResult(
                            index=task.index,
                            note=task.note,
                            decision=decision,
                            job=normalize_job_record(job),
                            allow_llm=task.allow_llm,
                            worker_fallback=True,
                            error=str(exc),
                        )
                    results[result.index] = result
                    completed += 1
                    if completed == total or completed % progress_step == 0:
                        pct = int(round(completed * 100 / max(1, total)))
                        self.logger.info("[阶段进度] NoteAgent处理 %s/%s (%s%%)", completed, total, pct)

        note_agent_details: list[dict[str, object]] = []
        note_agent_worker_fallback = 0
        note_agent_errors = 0
        for result in results:
            if result is None:
                continue
            note = result.note
            decision = result.decision
            job = result.job
            score = float(getattr(decision, "score", 0.0))
            source = str(getattr(decision, "source", "") or "")
            reason = str(getattr(decision, "reason", "") or "")

            scores[note.note_id] = score
            if bool(getattr(decision, "is_target", False)):
                targets.append(note)
                jobs.append(normalize_job_record(job))
            else:
                filtered_out.append(
                    {
                        "note_id": note.note_id,
                        "title": note.title[:100],
                        "score": round(score, 4),
                        "reason": reason,
                        "source": source,
                    }
                )
                self.logger.info(
                    "过滤帖子 | note=%s | score=%.2f | source=%s | reason=%s",
                    note.note_id,
                    score,
                    source,
                    reason,
                )

            if result.worker_fallback:
                note_agent_worker_fallback += 1
            if result.error:
                note_agent_errors += 1

            note_agent_details.append(
                {
                    "index": int(result.index),
                    "note_id": note.note_id,
                    "allow_llm": bool(result.allow_llm),
                    "is_target": bool(getattr(decision, "is_target", False)),
                    "score": round(score, 4),
                    "decision_source": source or "unknown",
                    "parse_source": str(getattr(job, "parse_source", "") or ""),
                    "worker_fallback": bool(result.worker_fallback),
                    "error": result.error[:300],
                }
            )

        note_agent_stats = {
            "total": total,
            "llm_budgeted": total,
            "rule_budgeted": 0,
            "worker_fallback": note_agent_worker_fallback,
            "errors": note_agent_errors,
        }
        self.logger.info(
            "[阶段进度] NoteAgent处理完成 %s/%s (100%%) | 命中=%s | 过滤=%s | worker_fallback=%s",
            total,
            total,
            len(targets),
            len(filtered_out),
            note_agent_worker_fallback,
        )

        jobs.sort(key=lambda item: item.publish_time, reverse=True)
        return ExtractOutcome(
            targets=targets,
            jobs=jobs,
            filtered_out=filtered_out,
            scores=scores,
            note_agent_stats=note_agent_stats,
            note_agent_details=note_agent_details,
        )

    @staticmethod
    def _effective_workers(*, workers: int, total: int) -> int:
        if total <= 1:
            return 1
        value = max(1, int(workers or 1))
        return min(value, total)

    def mark_opportunities(self, jobs: list[JobRecord]) -> list[JobRecord]:
        if not jobs:
            return jobs

        max_score = max(float(item.match_score or 0.0) for item in jobs)
        if max_score <= 0.0:
            for job in jobs:
                job.opportunity_point = False
            return jobs

        limit = max(1, min(len(jobs), floor(len(jobs) * 0.3)))

        for job in jobs:
            job.opportunity_point = False

        ranked = sorted(
            jobs,
            key=lambda item: (
                self._is_urgent(item),
                float(item.match_score),
            ),
            reverse=True,
        )

        selected = ranked[:limit]
        if selected:
            selected[0].opportunity_point = True
        for item in selected:
            item.opportunity_point = True
        return jobs

    def attach_outreach_messages(self, jobs: list[JobRecord], resume_text: str) -> list[JobRecord]:
        opp_total = sum(1 for item in jobs if item.opportunity_point)
        enabled_for_outreach = bool(getattr(self.llm_enricher.settings.llm, "enabled_for_outreach", True))
        if not enabled_for_outreach:
            self.logger.info("[阶段] 套磁生成已关闭：enabled_for_outreach=false")
            for job in jobs:
                job.outreach_message = ""
            return jobs
        self.logger.info("[阶段] 套磁生成开始：机会点岗位=%s", opp_total)
        for job in jobs:
            if not job.opportunity_point:
                job.outreach_message = ""
                continue
            job.outreach_message = self.llm_enricher.build_outreach_message(job, resume_text=resume_text)
        return jobs

    @staticmethod
    def rank_targets(targets: list[NoteRecord], scores: dict[str, float], top_n: int) -> list[NoteRecord]:
        if not targets:
            return []
        ranked = sorted(
            targets,
            key=lambda n: (
                float(scores.get(n.note_id, 0.0)),
                int(n.comment_count),
                int(n.like_count),
                n.publish_time,
            ),
            reverse=True,
        )
        return ranked[: max(1, int(top_n))]

    @staticmethod
    def _is_urgent(job: JobRecord) -> int:
        text = "\n".join([job.source_title or "", job.requirements or "", job.arrival_time or ""]).lower()
        return int(any(token in text for token in URGENT_TOKENS))

__all__ = ["URGENT_TOKENS", "IntelligenceAgent"]
