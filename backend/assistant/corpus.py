"""The corpus allowlist and how source files are read.

Only files tracked by git are read, and they are read from a commit (`git show
<rev>:<path>`), so every chunk records exactly which content it came from.
Adding a source is a reviewed change to ALLOWLIST (docs/v3/RETRIEVAL_FTS.md §1).
"""

from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import List

REPO_ROOT = Path(__file__).resolve().parent.parent.parent

# (repository path, source type)
ALLOWLIST = (
    ("docs/ROUTING.md", "doc"),
    ("docs/TRAFFIC.md", "doc"),
    ("docs/ML_PIPELINE.md", "doc"),
    ("docs/RESULTS_AND_LIMITATIONS.md", "doc"),
    ("docs/RESEARCH_MILESTONE_FORECASTING.md", "doc"),
    ("docs/USER_GUIDE.md", "doc"),
    ("docs/SECURITY.md", "doc"),
    ("docs/DATABASE.md", "doc"),
    ("docs/ARCHITECTURE.md", "doc"),
    ("docs/DEPLOY_FREE_TIER.md", "doc"),
    ("backend/evaluation/v2/segment-speed-ratio.json", "eval_report"),
    ("backend/evaluation/v2/research-daily-congestion.json", "eval_report"),
)

# Never indexed, even if someone adds them to the allowlist by mistake.
_FORBIDDEN_PREFIXES = ("docs/v3/",)
_FORBIDDEN_NAMES = re.compile(r"(^|/)(\.env[^/]*|secrets\.toml|.*\.(pem|key|p12|jks|keystore))$", re.IGNORECASE)

# Values that look like real credentials. Placeholders such as `key=<TomTom key>` or
# `key=***` in the docs do not match (they need 20+ token characters).
_SECRET_VALUE = [
    # No leading \b: in TOMTOM_API_KEY the underscore is a word character.
    re.compile(r"(?i)(?:api[_-]?key|apikey|access[_-]?token|secret|password|token|key)\s*[=:]\s*[\"']?[A-Za-z0-9_\-]{20,}"),
    re.compile(r"\beyJ[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}"),  # JWT
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    re.compile(r"\bAIza[0-9A-Za-z_\-]{30,}"),  # Google API key
    re.compile(r"\bgh[pousr]_[A-Za-z0-9]{30,}"),  # GitHub token
]


class CorpusError(RuntimeError):
    pass


@dataclass(frozen=True)
class SourceFile:
    path: str
    source_type: str
    text: str


def git(*args: str, repo: Path = REPO_ROOT) -> str:
    try:
        out = subprocess.run(["git", *args], cwd=repo, capture_output=True, text=True, encoding="utf-8", check=True)
    except FileNotFoundError as exc:
        raise CorpusError("git is required to ingest the corpus") from exc
    except subprocess.CalledProcessError as exc:
        raise CorpusError(f"git {' '.join(args)} failed: {exc.stderr.strip()[:300]}") from exc
    return out.stdout


def resolve_commit(rev: str = "HEAD", repo: Path = REPO_ROOT) -> str:
    return git("rev-parse", "--verify", f"{rev}^{{commit}}", repo=repo).strip()


def check_path_allowed(path: str) -> None:
    if path.startswith(_FORBIDDEN_PREFIXES) or _FORBIDDEN_NAMES.search(path):
        raise CorpusError(f"{path} may never be indexed")


def find_secret(text: str) -> str | None:
    for pattern in _SECRET_VALUE:
        match = pattern.search(text)
        if match:
            return pattern.pattern[:40]
    return None


def load_sources(commit: str, repo: Path = REPO_ROOT, allowlist=ALLOWLIST) -> List[SourceFile]:
    tracked = set(git("ls-tree", "-r", "--name-only", commit, repo=repo).splitlines())
    sources = []
    for path, source_type in allowlist:
        check_path_allowed(path)
        if path not in tracked:
            raise CorpusError(f"{path} is not tracked at {commit[:12]}")
        text = git("show", f"{commit}:{path}", repo=repo)
        hit = find_secret(text)
        if hit:
            raise CorpusError(f"{path} contains a value that looks like a credential ({hit}); refusing to ingest")
        sources.append(SourceFile(path, source_type, text))
    return sources
