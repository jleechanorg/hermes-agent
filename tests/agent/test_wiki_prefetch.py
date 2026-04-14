from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from agent.wiki_prefetch import _query_terms, prefetch_wiki_context


def test_query_terms_dedupes_and_limits():
    q = "OpenClaw openclaw memory mem0 gateway gateway"
    terms = _query_terms(q, max_terms=5)
    assert "openclaw" in terms
    assert terms.count("openclaw") == 1
    assert len(terms) <= 5


def test_prefetch_wiki_context_empty_query(tmp_path: Path):
    wiki = tmp_path / "wiki"
    wiki.mkdir()
    assert prefetch_wiki_context("", wiki) == ""


@pytest.mark.skipif(not shutil.which("rg"), reason="ripgrep (rg) not installed")
def test_prefetch_wiki_context_finds_markdown(tmp_path: Path):
    wiki = tmp_path / "wiki"
    wiki.mkdir()
    (wiki / "sources").mkdir()
    (wiki / "sources" / "openclaw-note.md").write_text(
        "# OpenClaw\n\nGateway port 18789 for testing.\n", encoding="utf-8"
    )

    out = prefetch_wiki_context(
        "What port does OpenClaw gateway use?",
        wiki,
        max_chars=8000,
        max_files=5,
        timeout_sec=6.0,
    )
    assert "18789" in out or "openclaw" in out.lower()
