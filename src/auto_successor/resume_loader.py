from __future__ import annotations

from pathlib import Path

from .config import ResumeConfig


class ResumeLoader:
    """
    Resume context loader.

    Current behavior:
    - reads source TXT resume
    - trims to max_chars
    - writes normalized resume_text cache for LLM reuse

    Extension points for future frontend upload:
    - update_from_upload_bytes(...)
    - parse_pdf_bytes(...)
    """

    def __init__(self, cfg: ResumeConfig, logger) -> None:
        self.cfg = cfg
        self.logger = logger
        self.source_path = Path(cfg.source_txt_path)
        self.resume_text_path = Path(cfg.resume_text_path)
        self.source_path.parent.mkdir(parents=True, exist_ok=True)
        self.resume_text_path.parent.mkdir(parents=True, exist_ok=True)

    def load_resume_text(self) -> str:
        cached = self._read_file(self.resume_text_path)
        if cached:
            return self._trim(cached)

        source = self._read_file(self.source_path)
        if not source:
            return ""

        normalized = self._trim(source)
        self._persist_resume_text(normalized)
        return normalized

    def load_source_text(self) -> str:
        source = self._read_file(self.source_path)
        return self._trim(source)

    def refresh_from_source(self) -> str:
        source = self._read_file(self.source_path)
        normalized = self._trim(source)
        self._persist_resume_text(normalized)
        return normalized

    def save_resume_text(self, resume_text: str) -> str:
        normalized = self._trim(resume_text)
        self._persist_resume_text(normalized)
        return normalized

    def update_from_upload_bytes(self, *, filename: str, content: bytes, mime_type: str = "") -> str:
        text = self.parse_upload_bytes(filename=filename, content=content, mime_type=mime_type)
        return self.save_resume_text(text)

    def parse_upload_bytes(self, *, filename: str, content: bytes, mime_type: str = "") -> str:
        name = str(filename or "").lower()
        mtype = str(mime_type or "").lower()
        if name.endswith(".txt") or "text/plain" in mtype:
            return self._trim(content.decode("utf-8", errors="ignore"))
        if name.endswith(".docx") or "application/vnd.openxmlformats-officedocument.wordprocessingml.document" in mtype:
            return self.parse_docx_bytes(content)
        if name.endswith(".doc") or "application/msword" in mtype:
            raise ValueError("legacy .doc is not supported, please convert to .docx and upload again")
        if name.endswith(".pdf") or "application/pdf" in mtype:
            return self.parse_pdf_bytes(content)
        raise ValueError("unsupported resume file type")

    def parse_docx_bytes(self, content: bytes) -> str:
        try:
            from docx import Document
        except Exception as exc:  # pragma: no cover - optional dependency
            raise RuntimeError("python-docx is required for Word resume parsing") from exc

        import io

        document = Document(io.BytesIO(content))
        lines: list[str] = []
        for paragraph in document.paragraphs:
            text = (paragraph.text or "").strip()
            if text:
                lines.append(text)
        joined = "\n".join(lines)
        return self._trim(joined)

    def parse_pdf_bytes(self, content: bytes) -> str:
        try:
            from pypdf import PdfReader
        except Exception as exc:  # pragma: no cover - optional dependency
            raise RuntimeError("pypdf is required for pdf resume parsing") from exc

        import io

        reader = PdfReader(io.BytesIO(content))
        texts: list[str] = []
        for page in reader.pages:
            try:
                texts.append(page.extract_text() or "")
            except Exception:
                continue
        joined = "\n".join(item.strip() for item in texts if item and item.strip())
        return self._trim(joined)

    def _read_file(self, path: Path) -> str:
        if not path.exists():
            return ""
        try:
            return path.read_text(encoding="utf-8").strip()
        except Exception as exc:
            self.logger.warning("read resume file failed: %s (%s)", path, exc)
            return ""

    def _trim(self, text: str) -> str:
        cleaned = "\n".join(line.rstrip() for line in (text or "").replace("\r\n", "\n").split("\n")).strip()
        return cleaned[: max(500, int(self.cfg.max_chars))]

    def _persist_resume_text(self, normalized: str) -> None:
        self.source_path.write_text(normalized, encoding="utf-8")
        self.resume_text_path.write_text(normalized, encoding="utf-8")
