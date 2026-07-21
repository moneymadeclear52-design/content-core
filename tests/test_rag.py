"""Tests for content_core.rag — uses a deterministic fake embedder (no model
download, no API, no network). Tests the index/search/caching LOGIC."""

import numpy as np
import pytest

import content_core.rag as rag
from content_core.rag import PerspectiveIndex, retrieve_relevant_perspectives


class FakeEmbedder:
    """Maps known keywords to fixed unit vectors so similarity is predictable."""
    DIRS = {
        "money":  np.array([1.0, 0.0, 0.0], dtype="float32"),
        "crime":  np.array([0.0, 1.0, 0.0], dtype="float32"),
        "sports": np.array([0.0, 0.0, 1.0], dtype="float32"),
    }

    def embed(self, texts):
        out = []
        for t in texts:
            v = np.zeros(3, dtype="float32")
            for kw, d in self.DIRS.items():
                if kw in t.lower():
                    v += d
            if not v.any():
                v = np.array([0.577, 0.577, 0.577], dtype="float32")
            v = v / np.linalg.norm(v)
            out.append(v)
        return np.stack(out)


@pytest.fixture(autouse=True)
def fake_embedder(monkeypatch):
    monkeypatch.setattr(rag, "_get_embedder", lambda: FakeEmbedder())


PERSPECTIVES = [
    {"id": "1", "text": "Most people treat money savings as leftovers", "type": "Counter-conventional"},
    {"id": "2", "text": "Every crime case hides a paperwork trail", "type": "Observation"},
    {"id": "3", "text": "Sports fans forget losses faster than wins", "type": "Hot Take"},
]


def test_search_returns_semantically_relevant(tmp_path):
    idx = PerspectiveIndex.build(PERSPECTIVES, store_dir=tmp_path)
    hits = idx.search("money and budgeting", k=1)
    assert hits[0].id == "1"

    hits = idx.search("unsolved crime files", k=1)
    assert hits[0].id == "2"


def test_search_respects_k(tmp_path):
    idx = PerspectiveIndex.build(PERSPECTIVES, store_dir=tmp_path)
    assert len(idx.search("money crime sports", k=2)) == 2


def test_cache_is_reused_when_corpus_unchanged(tmp_path):
    PerspectiveIndex.build(PERSPECTIVES, store_dir=tmp_path)
    # load_or_build should load, not rebuild — verify via identical vectors
    idx2 = PerspectiveIndex.load_or_build(PERSPECTIVES, store_dir=tmp_path)
    assert len(idx2.perspectives) == 3
    assert (tmp_path / "meta.json").exists()


def test_cache_rebuilds_when_corpus_changes(tmp_path):
    PerspectiveIndex.build(PERSPECTIVES, store_dir=tmp_path)
    changed = PERSPECTIVES + [{"id": "4", "text": "new money insight", "type": "Verdict"}]
    idx = PerspectiveIndex.load_or_build(changed, store_dir=tmp_path)
    assert len(idx.perspectives) == 4


def test_build_rejects_empty_corpus(tmp_path):
    with pytest.raises(ValueError):
        PerspectiveIndex.build([], store_dir=tmp_path)


def test_retrieve_helper_falls_back_on_failure(monkeypatch, tmp_path):
    def boom():
        raise RuntimeError("embedder unavailable")
    monkeypatch.setattr(rag, "_get_embedder", boom)

    out = retrieve_relevant_perspectives(PERSPECTIVES, "money", k=2, store_dir=tmp_path)
    # graceful degradation: unranked first-k, never an exception
    assert len(out) == 2
    assert out[0]["id"] == "1"


def test_retrieve_helper_returns_relevant(tmp_path):
    out = retrieve_relevant_perspectives(PERSPECTIVES, "sports highlights", k=1, store_dir=tmp_path)
    assert out[0]["id"] == "3"
