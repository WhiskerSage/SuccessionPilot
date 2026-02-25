from __future__ import annotations

import re

_SUSPECT_CHARS_RE = re.compile(r"[\u0100-\u02FF\u0370-\u04FF]")


def repair_mojibake(text: str) -> str:
    """
    Best-effort fix for common mojibake cases seen in mixed UTF-8/GBK terminals.
    Keep original text when confidence is low.
    """
    raw = str(text or "")
    if not raw:
        return ""

    candidates = [raw]
    segmented = _repair_segments(raw)
    if segmented and segmented not in candidates:
        candidates.append(segmented)
    for fn in (_try_utf8_to_gbk, _try_latin1_to_utf8, _try_cp1252_to_utf8):
        repaired = fn(raw)
        if repaired and repaired not in candidates:
            candidates.append(repaired)

    scored = sorted((( _score_text(item), item) for item in candidates), key=lambda x: x[0], reverse=True)
    best_score, best = scored[0]
    base_score = _score_text(raw)
    if best_score >= base_score + 2:
        return best
    return raw


def clean_line(text: str) -> str:
    value = re.sub(r"\s+", " ", str(text or "")).strip()
    repaired = repair_mojibake(value)
    if not repaired:
        return ""

    # If text still looks like mojibake, strip suspicious runs as a final fallback.
    if is_unreadable_text(repaired):
        compact = _strip_suspect_runs(repaired)
        if compact and not is_unreadable_text(compact):
            return compact
    return repaired


def clean_line_with_fallback(text: str, fallback: str = "") -> str:
    cleaned = clean_line(text)
    if cleaned and not is_unreadable_text(cleaned):
        return cleaned
    fb = clean_line(fallback)
    if fb:
        return fb
    return cleaned


def is_unreadable_text(text: str) -> bool:
    value = str(text or "").strip()
    if not value:
        return False
    if "�" in value:
        return True
    cjk = len(re.findall(r"[\u4e00-\u9fff]", value))
    suspect = len(_SUSPECT_CHARS_RE.findall(value))
    ascii_ok = len(re.findall(r"[A-Za-z0-9_\-:/.@ ]", value))
    total = max(1, len(value))
    suspect_ratio = suspect / total
    # Typical mojibake contains long runs of Greek/Cyrillic-like chars with very low CJK ratio.
    if suspect >= 3 and cjk <= 1 and suspect_ratio >= 0.18:
        return True
    if re.search(r"(?:Ã.|Â.|¤|�)", value):
        return True
    # If almost no meaningful chars exist, treat as unreadable.
    if cjk == 0 and ascii_ok <= 2 and suspect >= 2:
        return True
    return False


def _try_utf8_to_gbk(value: str) -> str:
    # Case like "ʵϰ" -> bytes interpreted as UTF-8, should be GBK.
    try:
        return value.encode("utf-8").decode("gb18030")
    except Exception:
        return ""


def _try_latin1_to_utf8(value: str) -> str:
    # Case like "ä¸­æ" -> "中文".
    try:
        return value.encode("latin1").decode("utf-8")
    except Exception:
        return ""


def _try_cp1252_to_utf8(value: str) -> str:
    try:
        return value.encode("cp1252").decode("utf-8")
    except Exception:
        return ""


def _score_text(value: str) -> float:
    if not value:
        return -999.0
    cjk = len(re.findall(r"[\u4e00-\u9fff]", value))
    replacement = value.count("�")
    greek_cyr = len(re.findall(r"[\u0370-\u04ff]", value))
    mojibake_chunks = len(re.findall(r"(?:Ã.|Â.|¤|�)", value))
    ascii_ok = len(re.findall(r"[A-Za-z0-9_\-:/.@ ]", value))
    return (cjk * 2.2) + (ascii_ok * 0.08) - (replacement * 6.0) - (greek_cyr * 1.2) - (mojibake_chunks * 1.6)


def _repair_segments(value: str) -> str:
    def repl(match: re.Match[str]) -> str:
        seg = match.group(0)
        cand = _try_utf8_to_gbk(seg)
        if not cand:
            return seg
        if _score_text(cand) >= _score_text(seg) + 1:
            return cand
        return seg

    # Typical mojibake runs after GBK<->UTF-8 mismatch.
    return re.sub(r"[\u0100-\u04ff]{2,}", repl, value)


def _strip_suspect_runs(value: str) -> str:
    # Keep CJK/ASCII/punctuation and collapse suspicious runs to a single space.
    cleaned = re.sub(r"[\u0100-\u04ff]{2,}", " ", value)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned
