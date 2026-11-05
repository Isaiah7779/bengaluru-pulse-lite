"""V3 Phase 1: corpus, chunking, ingest and the SQLite retriever (docs/v3/ACCEPTANCE_CRITERIA.md)."""

from __future__ import annotations

import json
import subprocess
from datetime import date, datetime, timedelta, timezone

import pytest
from sqlalchemy import func, select

from assistant import corpus, golden
from assistant.chunking import blocks, chunk_eval_report, chunk_markdown, first_date, pack, split_sections
from assistant.ingest import ingest
from assistant.retrieval import BM25Retriever, build_query, cap_per_document, Hit
from assistant.text import fold
from db.models import RagChunk, RagDocument
from db.session import session_scope


def _git(repo, *args):
    subprocess.run(["git", "-c", "user.email=t@example.test", "-c", "user.name=t", *args],
                   cwd=repo, check=True, capture_output=True)


@pytest.fixture
def tiny_repo(tmp_path):
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "A.md").write_text(
        "# Alpha guide\n\nIntro text.\n\n## Shortcuts\n\nA shortcut is shorter and faster.\n\n"
        "## Retention (measured 2026‑10‑22)\n\nTrips are kept 180 days.\n", encoding="utf-8")
    (tmp_path / "docs" / "B.md").write_text("# Beta\n\n## Weather\n\nOpen-Meteo provides weather.\n", encoding="utf-8")
    _git(tmp_path, "init", "-q")
    _git(tmp_path, "add", ".")
    _git(tmp_path, "commit", "-q", "-m", "init")
    return tmp_path


TINY = (("docs/A.md", "doc"), ("docs/B.md", "doc"))


# --------------------------------------------------------------------------- allowlist and guards


def test_allowlist_matches_the_documented_v0_corpus():
    assert [p for p, _ in corpus.ALLOWLIST] == [
        "docs/ROUTING.md", "docs/TRAFFIC.md", "docs/ML_PIPELINE.md", "docs/RESULTS_AND_LIMITATIONS.md",
        "docs/RESEARCH_MILESTONE_FORECASTING.md", "docs/USER_GUIDE.md", "docs/SECURITY.md", "docs/DATABASE.md",
        "docs/ARCHITECTURE.md", "docs/DEPLOY_FREE_TIER.md",
        "backend/evaluation/v2/segment-speed-ratio.json", "backend/evaluation/v2/research-daily-congestion.json",
    ]


@pytest.mark.parametrize("path", ["docs/v3/eval/golden_v0.jsonl", "backend/.env", ".streamlit/secrets.toml", "x/server.pem"])
def test_forbidden_paths_are_refused(path):
    with pytest.raises(corpus.CorpusError):
        corpus.check_path_allowed(path)


def test_untracked_files_are_refused(tiny_repo):
    (tiny_repo / "docs" / "C.md").write_text("# C\n\nnot committed\n", encoding="utf-8")
    with session_scope() as s, pytest.raises(corpus.CorpusError, match="not tracked"):
        ingest(s, repo=tiny_repo, allowlist=TINY + (("docs/C.md", "doc"),))


def test_design_docs_are_refused_even_if_tracked(tiny_repo):
    (tiny_repo / "docs" / "v3").mkdir()
    (tiny_repo / "docs" / "v3" / "golden.md").write_text("# G\n\nexpected answers\n", encoding="utf-8")
    _git(tiny_repo, "add", ".")
    _git(tiny_repo, "commit", "-q", "-m", "v3")
    with session_scope() as s, pytest.raises(corpus.CorpusError, match="never be indexed"):
        ingest(s, repo=tiny_repo, allowlist=TINY + (("docs/v3/golden.md", "doc"),))


@pytest.mark.parametrize("secret", [
    "TOMTOM_API_KEY=" + "Ab3" * 10,
    "Authorization: Bearer eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.c2lnbmF0dXJlLXZhbHVlLWhlcmU",
    "-----BEGIN PRIVATE KEY-----",
])
def test_files_with_credentials_are_refused(tiny_repo, secret):
    (tiny_repo / "docs" / "A.md").write_text(f"# A\n\n## Config\n\n{secret}\n", encoding="utf-8")
    _git(tiny_repo, "commit", "-q", "-am", "leak")
    with session_scope() as s, pytest.raises(corpus.CorpusError, match="credential"):
        ingest(s, repo=tiny_repo, allowlist=TINY)


def test_documented_placeholders_are_not_mistaken_for_credentials():
    assert corpus.find_secret("returned the full URL including `?key=<TomTom key>`; redacts `key=`, `token=`") is None
    assert corpus.find_secret("TOMTOM_API_KEY= your key (optional)") is None


# --------------------------------------------------------------------------- chunking


def test_sections_keep_heading_paths_and_ignore_hashes_in_code():
    text = "# Title\n\nintro\n\n## One\n\n```bash\n# not a heading\n```\n\n### Sub\n\nx\n\n## Two\n\ny\n"
    title, sections = split_sections(text)
    assert title == "Title"
    assert [s.headings for s in sections] == [[], ["One"], ["One", "Sub"], ["Two"]]


def test_tables_and_code_blocks_stay_whole():
    lines = ["para one", "", "| a | b |", "|---|---|", "| 1 | 2 |", "after table", "", "```", "x", "", "y", "```"]
    assert blocks(lines) == ["para one", "| a | b |\n|---|---|\n| 1 | 2 |", "after table", "```\nx\n\ny\n```"]


def test_large_tables_split_by_rows_with_header_repeated():
    header = ["| name | value |", "|---|---|"]
    rows = [f"| row{i} | " + "word " * 20 + "|" for i in range(40)]
    pieces = pack(["\n".join(header + rows)], limit=120)
    assert len(pieces) > 1
    seen = []
    for piece in pieces:
        lines = piece.splitlines()
        assert lines[:2] == header
        seen += lines[2:]
    assert seen == rows  # every row exactly once, never cut


def test_windows_respect_the_word_limit_and_never_cross_sections():
    para = " ".join(["word"] * 100)
    text = "# T\n\n## A\n\n" + "\n\n".join([para] * 8) + "\n\n## B\n\nshort\n"
    _, chunks = chunk_markdown(text, "T.md")
    a = [c for c in chunks if c.heading_path.endswith("A")]
    assert len(a) >= 3 and all(len(c.body.split()) <= 350 for c in a)
    assert [c.body for c in chunks if c.heading_path.endswith("B")] == ["short"]


def test_measurement_dates_are_read_with_non_breaking_hyphens():
    assert first_date("Status (2026‑10‑22): insufficient") == date(2026, 10, 22)
    assert first_date("measured 22 Oct 2026") == date(2026, 10, 22)
    assert first_date("no date here") is None


def test_eval_reports_copy_values_without_recomputing():
    report = {
        "task": "t", "name": "n", "status": "insufficient_data", "reason": "0.0 days collected",
        "generated_at": "2026-10-22T04:30:29+00:00",
        "horizons": {"1d": {"selected_model": "ridge", "test": {"model:ridge": {"mae": 16.07911337, "n": 1791}}}},
    }
    title, chunks = chunk_eval_report(json.dumps(report), "r.json")
    joined = "\n".join(c.body for c in chunks)
    assert "status: insufficient_data" in joined and "reason: 0.0 days collected" in joined
    assert "test model:ridge: mae 16.079, n 1791" in joined
    assert all(c.measured_on == date(2026, 10, 22) for c in chunks)


# --------------------------------------------------------------------------- ingest


def test_ingest_indexes_exactly_the_allowlist_and_is_idempotent():
    with session_scope() as s:
        first = ingest(s)
    with session_scope() as s:
        refs = set(s.scalars(select(RagDocument.source_ref)))
        n_chunks = s.scalar(select(func.count(RagChunk.id)))
        chunks = s.scalars(select(RagChunk)).all()
        assert refs == {p for p, _ in corpus.ALLOWLIST}
        assert first["documents_added"] == len(corpus.ALLOWLIST) and n_chunks == first["chunks_written"] > 0
        for c in chunks:
            assert c.heading_path and c.content_hash and c.meta["commit_sha"] == first["commit_sha"]
            assert "docs/v3" not in c.meta["source_ref"]
    with session_scope() as s:
        again = ingest(s)
    assert again["documents_unchanged"] == len(corpus.ALLOWLIST)
    assert again["chunks_written"] == 0 and again["documents_added"] == again["documents_updated"] == 0


def test_changed_and_removed_documents_are_replaced(tiny_repo):
    with session_scope() as s:
        ingest(s, repo=tiny_repo, allowlist=TINY)
    (tiny_repo / "docs" / "A.md").write_text("# Alpha guide\n\n## Shortcuts\n\nRewritten.\n", encoding="utf-8")
    _git(tiny_repo, "commit", "-q", "-am", "edit")
    with session_scope() as s:
        stats = ingest(s, repo=tiny_repo, allowlist=TINY[:1])
        assert stats["documents_updated"] == 1 and stats["documents_removed"] == 1
    with session_scope() as s:
        bodies = list(s.scalars(select(RagChunk.body)))
        assert bodies == ["Rewritten."]


def test_chunks_record_their_section_measurement_date(tiny_repo):
    with session_scope() as s:
        ingest(s, repo=tiny_repo, allowlist=TINY)
        dated = s.scalars(select(RagChunk).where(RagChunk.heading_path.like("%Retention%"))).one()
        assert dated.measured_on == date(2026, 10, 22)


# --------------------------------------------------------------------------- retrieval (SQLite stand-in)


def test_query_processing_rewrites_local_terms_and_expands():
    q = build_query("ETA from KIA to Whitefield on the ORR?")
    assert "airport" in q.terms and "outer" in q.terms and "kia" not in q.terms
    assert "travel" in q.expansions
    assert len(build_query("x" * 900).original) == 500


def test_bm25_finds_the_right_section_and_respects_validity(tiny_repo):
    with session_scope() as s:
        ingest(s, repo=tiny_repo, allowlist=TINY)
        hits = BM25Retriever(s).search("what is a shortcut?")
        assert hits and hits[0].heading_path.endswith("Shortcuts")
        s.query(RagChunk).filter(RagChunk.heading_path.like("%Shortcuts%")).update(
            {RagChunk.valid_until: datetime.now(timezone.utc) - timedelta(minutes=1)}, synchronize_session=False)
        assert all(not h.heading_path.endswith("Shortcuts") for h in BM25Retriever(s).search("what is a shortcut?"))
        assert BM25Retriever(s).search("the of and") == []


def test_no_more_than_two_chunks_per_document():
    hits = [Hit(i, "a.md" if i < 4 else "b.md", "h", 1.0 - i / 10, "", None) for i in range(6)]
    assert [h.chunk_id for h in cap_per_document(hits, 5)] == [0, 1, 4, 5]


# --------------------------------------------------------------------------- evaluation set stays valid


def _sections(path):
    text = (corpus.REPO_ROOT / path).read_text(encoding="utf-8")
    if path.endswith(".json"):
        return {"": text}
    _, sections = split_sections(text)
    return {(s.headings[-1] if s.headings else ""): "\n".join(s.headings + s.lines) for s in sections}


def test_golden_set_is_well_formed_and_its_facts_exist_in_the_cited_sections():
    items = golden.load()
    assert len(items) == 78 and len({i["id"] for i in items}) == 78
    problems = []
    for item in items:
        if item["expected_behavior"] == "refuse" and not item.get("refusal_code"):
            problems.append(f"{item['id']}: refuse without refusal_code")
        texts = []
        for src in item.get("expected_sources", []):
            prefix = fold(src["heading_prefix"])
            hit = [t for h, t in _sections(src["path"]).items() if fold(h).startswith(prefix)]
            if not hit:
                problems.append(f"{item['id']}: no section {src}")
            texts += hit
        joined = fold(" ".join(texts))
        for fact in item.get("must_include", []):
            if item.get("expected_sources") and fold(fact) not in joined:
                problems.append(f"{item['id']}: '{fact}' not in cited sections")
    assert problems == []
