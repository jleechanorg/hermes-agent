"""Keyword recall from the Karpathy-style LLM wiki for per-turn prefetch.

Merged into the same injection path as mem0/Honcho prefetch (see run_agent)
without registering a second external MemoryProvider.
"""

from __future__ import annotations

import logging
import os
import re
import shutil
import subprocess
from pathlib import Path

logger = logging.getLogger(__name__)

_MAX_FILE_BYTES = 2_000_000


def _query_terms(query: str, *, max_terms: int = 10) -> list[str]:
    words = re.findall(r"[a-zA-Z][a-zA-Z0-9_./+-]{2,}", query)
    out: list[str] = []
    seen: set[str] = set()
    for w in words:
        low = w.lower()
        if low in seen or len(low) < 3:
            continue
        seen.add(low)
        out.append(low)
        if len(out) >= max_terms:
            break
    return out


def _rg_files_with_matches(terms: list[str], root: Path, *, timeout: float) -> list[Path]:
    rg = shutil.which("rg")
    if not rg or not terms:
        return []
    args = [
        rg,
        "-i",
        "--files-with-matches",
        "-g",
        "*.md",
        "-g",
        "!.obsidian/**",
        "--max-depth",
        "30",
    ]
    for t in terms:
        args.extend(["-e", t])
    args.append(".")
    try:
        proc = subprocess.run(
            args,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=str(root),
        )
    except (subprocess.TimeoutExpired, OSError) as e:
        logger.debug("wiki prefetch rg failed: %s", e)
        return []
    if proc.returncode not in (0, 1):
        return []
    root_resolved = root.resolve()
    paths: list[Path] = []
    for line in (proc.stdout or "").splitlines():
        p = line.strip()
        if not p:
            continue
        try:
            fp = (root_resolved / p).resolve() if not os.path.isabs(p) else Path(p).resolve()
            fp.relative_to(root_resolved)
            paths.append(fp)
        except Exception:
            continue
    return paths


def _read_excerpt(path: Path, *, per_file_cap: int) -> str:
    try:
        st = path.stat()
    except OSError:
        return ""
    if st.st_size > _MAX_FILE_BYTES:
        return ""
    try:
        raw = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""
    raw = raw.strip()
    if len(raw) > per_file_cap:
        raw = raw[:per_file_cap] + "\n…"
    return raw


def prefetch_wiki_context(
    query: str,
    wiki_root: Path,
    *,
    max_chars: int = 8000,
    max_files: int = 12,
    timeout_sec: float = 4.0,
) -> str:
    """Return markdown for injection under <memory-context>, or ""."""
    query = (query or "").strip()
    if not query or not wiki_root.is_dir():
        return ""
    terms = _query_terms(query)
    if not terms:
        return ""
    timeout = min(max(timeout_sec, 0.5), 12.0)
    paths = _rg_files_with_matches(terms, wiki_root, timeout=timeout)
    if not paths:
        return ""
    root_resolved = wiki_root.resolve()
    n_scan = min(len(paths), max_files)
    per_file = max(400, min(3500, max_chars // max(1, n_scan)))

    header = (
        "## LLM Wiki (keyword recall)\n\n"
        "_Auto-selected excerpts; confirm facts with direct file reads if needed._\n\n"
    )
    parts: list[str] = [header]
    total = len(header)
    shown = 0
    for path in paths:
        if shown >= max_files:
            break
        try:
            rel = path.relative_to(root_resolved)
        except ValueError:
            continue
        excerpt = _read_excerpt(path, per_file_cap=per_file)
        if not excerpt:
            continue
        block = f"### `{rel}`\n\n{excerpt}\n\n"
        if total + len(block) > max_chars:
            budget = max_chars - total - 80
            if budget < 120:
                break
            excerpt = excerpt[:budget] + "\n…"
            block = f"### `{rel}`\n\n{excerpt}\n\n"
            if total + len(block) > max_chars:
                break
        parts.append(block)
        total += len(block)
        shown += 1
    if shown == 0:
        return ""
    return "".join(parts).strip()
