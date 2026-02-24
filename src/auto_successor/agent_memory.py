from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass
class AgentMemory:
    global_instructions: str
    main_instructions: str

    def as_system_prefix(self) -> str:
        chunks = []
        if self.global_instructions:
            chunks.append(f"[Global Instructions]\n{self.global_instructions}")
        if self.main_instructions:
            chunks.append(f"[Main Instructions]\n{self.main_instructions}")
        return "\n\n".join(chunks).strip()


class AgentMemoryLoader:
    def __init__(self, global_path: str, main_path: str, max_chars: int = 4000) -> None:
        self.global_path = Path(global_path)
        self.main_path = Path(main_path)
        self.max_chars = max(500, int(max_chars))

    def load(self) -> AgentMemory:
        return AgentMemory(
            global_instructions=self._read_trimmed(self.global_path),
            main_instructions=self._read_trimmed(self.main_path),
        )

    def _read_trimmed(self, path: Path) -> str:
        if not path.exists():
            return ""
        try:
            text = path.read_text(encoding="utf-8")
        except Exception:
            return ""
        text = text.strip()
        return text[: self.max_chars]
