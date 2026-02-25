from __future__ import annotations

import re


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
    return repair_mojibake(value)


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
