"""Split source files into retrievable chunks (docs/v3/RETRIEVAL_FTS.md §2).

Markdown is split by heading (`#`..`###`); each section is packed into windows of
about WINDOW_WORDS words without crossing a section boundary. Tables and fenced
code blocks are kept whole; a table larger than a window is split by rows with
its header repeated. Evaluation reports (JSON) are rendered by fixed templates;
every value is copied from the file, never recomputed.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import date
from typing import Iterable, List, Optional

from assistant.text import normalise, word_count

WINDOW_WORDS = 350
OVERLAP_MAX_WORDS = 50
HEADING_SEP = " › "

_HEADING = re.compile(r"^(#{1,3})\s+(.*?)\s*#*\s*$")
_MONTHS = {m: i for i, m in enumerate(
    ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], 1)}
_ISO_DATE = re.compile(r"\b(20\d\d)[-‐‑](\d\d)[-‐‑](\d\d)(?!\d)")  # also 2026-10-22T04:30
_TEXT_DATE = re.compile(r"\b(\d{1,2}) (Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]* (20\d\d)\b")


@dataclass
class Chunk:
    heading_path: str
    body: str
    measured_on: Optional[date] = None
    meta: dict = field(default_factory=dict)


@dataclass
class Section:
    headings: List[str]
    lines: List[str]


def first_date(text: str) -> Optional[date]:
    """The first explicit calendar date in a section (its measurement date, if any)."""

    found = []
    for m in _ISO_DATE.finditer(text):
        found.append((m.start(), _safe_date(int(m.group(1)), int(m.group(2)), int(m.group(3)))))
    for m in _TEXT_DATE.finditer(text):
        found.append((m.start(), _safe_date(int(m.group(3)), _MONTHS[m.group(2).lower()], int(m.group(1)))))
    found = [f for f in found if f[1] is not None]
    return min(found)[1] if found else None


def _safe_date(y: int, m: int, d: int) -> Optional[date]:
    try:
        return date(y, m, d)
    except ValueError:
        return None


# --------------------------------------------------------------------------- markdown


def split_sections(text: str) -> tuple[str, List[Section]]:
    """Return (title, sections). The H1 is the title; H2/H3 build heading paths."""

    title = ""
    sections: List[Section] = []
    stack: List[str] = []
    current = Section([], [])
    in_fence = False
    for line in text.splitlines():
        if line.lstrip().startswith("```"):
            in_fence = not in_fence
        m = None if in_fence else _HEADING.match(line)
        if m:
            level, heading = len(m.group(1)), normalise(m.group(2))
            if level == 1 and not title:
                title = heading
                continue
            sections.append(current)
            depth = max(level - 2, 0)
            stack = stack[:depth] + [heading]
            current = Section(list(stack), [])
        else:
            current.lines.append(line)
    sections.append(current)
    return title, [s for s in sections if "\n".join(s.lines).strip()]


def blocks(lines: Iterable[str]) -> List[str]:
    """Paragraph-level blocks; fenced code and tables stay whole."""

    out: List[str] = []
    buf: List[str] = []
    kind = None  # None | "fence" | "table" | "text"

    def flush():
        nonlocal buf, kind
        if any(l.strip() for l in buf):
            out.append("\n".join(buf).strip("\n"))
        buf, kind = [], None

    for line in lines:
        stripped = line.strip()
        if kind == "fence":
            buf.append(line)
            if stripped.startswith("```"):
                flush()
            continue
        if stripped.startswith("```"):
            flush()
            kind = "fence"
            buf.append(line)
            continue
        is_row = stripped.startswith("|")
        if is_row and kind != "table":
            flush()
            kind = "table"
        elif not is_row and kind == "table":
            flush()
        if not stripped:
            if kind != "table":
                flush()
            continue
        if kind is None:
            kind = "text"
        buf.append(line)
    flush()
    return out


def _is_table(block: str) -> bool:
    return block.lstrip().startswith("|")


def _split_table(block: str, limit: int) -> List[str]:
    rows = block.splitlines()
    header = rows[:2] if len(rows) > 1 and set(rows[1].replace("|", "").strip()) <= set("-: ") else rows[:1]
    body = rows[len(header):]
    pieces, cur = [], []
    for row in body:
        if cur and word_count("\n".join(header + cur + [row])) > limit:
            pieces.append("\n".join(header + cur))
            cur = []
        cur.append(row)
    if cur or not pieces:
        pieces.append("\n".join(header + cur))
    return pieces


def _split_words(block: str, limit: int) -> List[str]:
    words = block.split()
    return [" ".join(words[i:i + limit]) for i in range(0, len(words), limit)]


def pack(section_blocks: List[str], limit: int = WINDOW_WORDS) -> List[str]:
    """Pack blocks into windows; carry a short last paragraph forward as overlap."""

    units: List[str] = []
    for b in section_blocks:
        if word_count(b) <= limit:
            units.append(b)
        elif _is_table(b):
            units.extend(_split_table(b, limit))
        else:
            units.extend(_split_words(b, limit))

    windows: List[List[str]] = []
    cur: List[str] = []
    for u in units:
        if cur and word_count("\n\n".join(cur + [u])) > limit:
            windows.append(cur)
            tail = cur[-1]
            carry = not _is_table(tail) and not tail.startswith("```") and word_count(tail) <= OVERLAP_MAX_WORDS
            cur = [tail] if carry and word_count(tail + " " + u) <= limit else []
        cur.append(u)
    if cur:
        windows.append(cur)
    return ["\n\n".join(w) for w in windows]


def chunk_markdown(text: str, fallback_title: str) -> tuple[str, List[Chunk]]:
    title, sections = split_sections(text)
    title = title or fallback_title
    chunks: List[Chunk] = []
    for section in sections:
        path = HEADING_SEP.join([title] + section.headings)
        section_text = "\n".join(section.headings + section.lines)
        measured = first_date(section_text)
        for body in pack(blocks(section.lines)):
            chunks.append(Chunk(heading_path=path, body=body, measured_on=measured,
                                meta={"headings": section.headings}))
    return title, chunks


# --------------------------------------------------------------------------- evaluation reports


def _num(value) -> str:
    if isinstance(value, float):
        return f"{value:.3f}".rstrip("0").rstrip(".") if abs(value) < 1e6 else str(value)
    return str(value)


def _scalars(d: dict) -> List[str]:
    return [f"{k.replace('_', ' ')}: {_num(v)}" for k, v in d.items() if isinstance(v, (str, int, float, bool)) and v is not None]


def chunk_eval_report(text: str, path: str) -> tuple[str, List[Chunk]]:
    report = json.loads(text)
    task = report.get("task") or report.get("name") or path
    title = f"Evaluation report {report.get('name', task)}"
    generated = report.get("generated_at", "")
    measured = first_date(generated) if generated else None

    head = [f"Task {task}."]
    head += _scalars({k: report.get(k) for k in ("dataset", "notes", "status", "reason", "series",
                                                  "observations", "span_days", "generated_at") if k in report})
    if report.get("period"):
        head.append(f"period: {report['period'][0]} to {report['period'][-1]}")
    validation = report.get("data_validation") or {}
    head += [f"data validation {line}" for line in _scalars(validation)]
    activation = report.get("activation") or {}
    head += [f"activation {line}" for line in _scalars(activation)]
    chunks = [Chunk(heading_path=f"{title}{HEADING_SEP}Summary", body="\n".join(head), measured_on=measured,
                    meta={"headings": ["Summary"]})]

    for name, h in (report.get("horizons") or {}).items():
        lines = [f"Task {task}, horizon {name}. Metrics rounded to 3 decimals."]
        lines += _scalars({k: h.get(k) for k in ("selected_model", "best_baseline", "test_improvement_vs_best_baseline") if k in h})
        splits = h.get("splits") or {}
        for split in ("train", "validation", "test"):
            if isinstance(splits.get(split), list):
                lines.append(f"{split} period: {splits[split][0]} to {splits[split][-1]}")
        for split in ("test", "validation"):
            for candidate, metrics in (h.get(split) or {}).items():
                if isinstance(metrics, dict):
                    shown = ", ".join(f"{m} {_num(metrics[m])}" for m in ("mae", "rmse", "smape", "r2", "bias", "n") if m in metrics)
                    lines.append(f"{split} {candidate}: {shown}")
        chunks.append(Chunk(heading_path=f"{title}{HEADING_SEP}Horizon {name}", body="\n".join(lines),
                            measured_on=measured, meta={"headings": [f"Horizon {name}"]}))

    legacy = validation.get("legacy_nowcast_check")
    if isinstance(legacy, dict):
        lines = [f"Task {task}: {legacy.get('description', 'legacy same-day estimation check')}."]
        for setting, metrics in legacy.items():
            if isinstance(metrics, dict):
                shown = ", ".join(f"{m} {_num(metrics[m])}" for m in ("mae", "rmse", "r2", "n") if m in metrics)
                lines.append(f"{setting.replace('_', ' ')}: {shown}")
        chunks.append(Chunk(heading_path=f"{title}{HEADING_SEP}Legacy V1 check", body="\n".join(lines),
                            measured_on=measured, meta={"headings": ["Legacy V1 check"]}))
    return title, chunks
