"""Ask pipeline: safety → scope → retrieval → extractive grounded answer → citations.

No LLM (owner decision D2). The answer is built only from sentences copied verbatim
from retrieved chunks plus fixed connective text that contains no numbers, so every
number in an answer is present in a cited passage. `ground_check` verifies that before
anything is returned. Routing, ETAs, traffic and forecasts are never computed here.
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from typing import List, Optional, Sequence

from sqlalchemy.orm import Session

from assistant import safety, scope
from assistant.retrieval import Hit, build_query, get_retriever
from assistant.text import content_tokens
from db.models import RagChunk, RagDocument

MAX_SENTENCES = 3
MAX_CITATIONS = 3
MIN_OVERLAP = 1  # content words a sentence must share with the question

NOT_FOUND = (
    "I could not find this in the Bengaluru Pulse documentation, so I won't guess. "
    "Try rephrasing, or use the Navigate and Traffic pages for live results."
)
LEAD = "From the Bengaluru Pulse documentation:"
DISCLAIMER = (
    "Answers quote project documentation only. Live routes, travel times and traffic come "
    "from the Navigate and Traffic pages, not from the assistant."
)

_SENTENCE = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9*`(])")
_NUMBER = re.compile(r"\d+(?:[.,]\d+)*")


@dataclass
class Citation:
    n: int
    chunk_id: int
    title: str
    source_ref: str
    heading: str
    measured_on: Optional[str]


@dataclass
class AskResult:
    answer: str
    refused: bool
    refusal_code: Optional[str] = None
    reason: Optional[str] = None
    scope: Optional[str] = None
    citations: List[Citation] = field(default_factory=list)
    retriever: Optional[str] = None
    composer: str = "extractive"
    disclaimer: str = DISCLAIMER
    latency_ms: float = 0.0


def _clean(text: str) -> str:
    text = safety.sanitize_passage(text)
    text = re.sub(r"\*\*|`|^#+\s*", "", text, flags=re.MULTILINE)
    text = re.sub(r"(^|\s)[*-]\s+", r"\1", text)  # list markers
    return re.sub(r"\s+", " ", text).strip()


# The product name appears in almost every chunk; it says nothing about relevance.
_NAME = re.compile(r"\b(bengaluru pulse|pulse|bengaluru|bangalore)\b", re.IGNORECASE)


def _sentences(body: str) -> List[str]:
    out = []
    for block in re.split(r"\n\s*\n", body):
        stripped = block.lstrip()
        if stripped.startswith("```") or "-->" in block or stripped.startswith("flowchart"):
            continue  # code and diagrams are not quotable prose
        if stripped.startswith("|"):  # a table row set is one unit
            rows = [r for r in block.splitlines() if r.strip() and not set(r.replace("|", "").strip()) <= set("-: ")]
            out += [_clean(" ".join(c.strip() for c in r.strip("|").split("|"))) for r in rows[1:]]
            continue
        out += [_clean(s) for s in _SENTENCE.split(block.replace("\n", " "))]
    return [s for s in out if 4 <= len(s.split()) <= 80]


def _pick(question_terms: Sequence[str], hits: Sequence[Hit], bodies: dict) -> List[tuple]:
    """Best sentences by overlap with the question; (score, rank, hit, sentence)."""

    terms = set(question_terms)
    scored = []
    for rank, hit in enumerate(hits):
        for s in _sentences(bodies[hit.chunk_id]):
            overlap = len(terms & set(content_tokens(s)))
            if overlap >= MIN_OVERLAP:
                scored.append((overlap, -rank, hit, s))
    scored.sort(key=lambda x: (-x[0], -x[1]))
    chosen, seen = [], set()
    for item in scored:
        if item[3] in seen:
            continue
        seen.add(item[3])
        chosen.append(item)
        if len(chosen) == MAX_SENTENCES:
            break
    return chosen


def ground_check(answer: str, cited_bodies: Sequence[str]) -> bool:
    """Every number in the answer must appear in a cited passage (RAG_SAFETY.md §2 rule 1)."""

    evidence = " ".join(_clean(b) for b in cited_bodies)
    return all(num in evidence for num in _NUMBER.findall(answer))


def ask(session: Session, question: str, k: int = 5) -> AskResult:
    started = time.perf_counter()

    def done(result: AskResult) -> AskResult:
        result.latency_ms = round((time.perf_counter() - started) * 1000, 2)
        return result

    q = safety.clean_question(question or "")
    refusal = safety.check(q)
    if refusal:
        return done(AskResult(refusal.message, True, refusal.code, refusal.reason))

    decision = scope.classify(q)
    if decision.decision != scope.IN_SCOPE:
        return done(AskResult(decision.message, True, decision.decision, f"scope_rule_{decision.rule}",
                              scope=decision.decision))

    retriever = get_retriever(session)
    query = _NAME.sub(" ", q).strip() or q
    hits = retriever.search(query, k=k)
    if not hits:
        return done(AskResult(NOT_FOUND, False, scope=scope.IN_SCOPE, retriever=retriever.name,
                              reason="no_retrieval_hits"))

    bodies = {c.id: c.body for c in session.query(RagChunk).filter(RagChunk.id.in_([h.chunk_id for h in hits]))}
    chosen = _pick(build_query(query).terms, hits, bodies)
    if not chosen:
        return done(AskResult(NOT_FOUND, False, scope=scope.IN_SCOPE, retriever=retriever.name,
                              reason="insufficient_evidence"))

    titles = dict(session.query(RagDocument.source_ref, RagDocument.title)
                  .filter(RagDocument.source_ref.in_({h.source_ref for h in hits})).all())
    numbers: dict = {}
    citations: List[Citation] = []
    lines = [LEAD]
    for _, _, hit, sentence in chosen:
        if hit.chunk_id not in numbers:
            if len(citations) == MAX_CITATIONS:
                continue
            numbers[hit.chunk_id] = len(citations) + 1
            heading = hit.heading_path.split(" › ", 1)[-1]
            citations.append(Citation(numbers[hit.chunk_id], hit.chunk_id, titles.get(hit.source_ref, hit.source_ref),
                                      hit.source_ref, heading,
                                      hit.measured_on.isoformat() if hit.measured_on else None))
        n = numbers[hit.chunk_id]
        cited = citations[n - 1]
        dated = f" (as documented on {cited.measured_on})" if cited.measured_on else ""
        lines.append(f"- {sentence} [{n}]{dated}")
    answer = "\n".join(lines)

    # The date suffix adds digits that are in chunk metadata, not body text; check the body sentences.
    body_only = "\n".join(s for _, _, _, s in chosen)
    if not ground_check(body_only, [bodies[c.chunk_id] for c in citations]):
        return done(AskResult(NOT_FOUND, False, scope=scope.IN_SCOPE, retriever=retriever.name, reason="guard_failed"))
    return done(AskResult(answer, False, scope=scope.IN_SCOPE, citations=citations, retriever=retriever.name))
