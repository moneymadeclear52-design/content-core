"""
content_core.rag
================
Semantic retrieval for the Perspective Bank.

WHY THIS EXISTS
---------------
The originality injector previously selected perspectives by channel + a
"least recently used" sort. That guarantees rotation but not RELEVANCE: a
script about emergency funds could receive a perspective about index investing.

This module embeds every perspective once, stores vectors locally, and at
injection time retrieves the perspectives most semantically similar to the
script's topic. Result: injected perspectives that actually fit the content.

DESIGN
------
- Embeddings: sentence-transformers locally (free, no API) with an optional
  OpenAI-embeddings backend. Chosen over a hosted vector DB because the corpus
  is small (hundreds of perspectives, not millions) — a numpy cosine search is
  simpler, faster, and has zero infra cost. Using a heavyweight vector DB here
  would be resume-driven engineering.
- Store: a single .npz + .json pair on disk. Rebuildable at any time from
  Notion; treated as a cache, not a source of truth.

USAGE
-----
    from content_core.rag import PerspectiveIndex

    idx = PerspectiveIndex.load_or_build(perspectives)   # list of {"id","text","type"}
    top = idx.search("emergency fund basics", k=3)
    # → the 3 most semantically relevant perspectives

Optional deps: pip install content-core[rag]
    (sentence-transformers) or set RAG_EMBEDDER=openai with OPENAI_API_KEY.
"""

from __future__ import annotations

import os
import json
import hashlib
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import List, Dict, Optional

logger = logging.getLogger(__name__)

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

DEFAULT_STORE_DIR = Path(os.getenv("RAG_STORE_DIR", ".rag_store"))


# ── Embedding backends (lazy-loaded) ───────────────────────────────────────────

class _LocalEmbedder:
    """sentence-transformers backend — free, offline after first model download."""
    def __init__(self, model_name: str = "all-MiniLM-L6-v2"):
        from sentence_transformers import SentenceTransformer  # lazy import
        self._model = SentenceTransformer(model_name)

    def embed(self, texts: List[str]):
        import numpy as np
        vecs = self._model.encode(texts, normalize_embeddings=True)
        return np.asarray(vecs, dtype="float32")


class _OpenAIEmbedder:
    """OpenAI embeddings backend — for environments without local torch."""
    def __init__(self, model_name: str = "text-embedding-3-small"):
        from openai import OpenAI  # lazy import
        key = os.getenv("OPENAI_API_KEY")
        if not key:
            raise RuntimeError("OPENAI_API_KEY required for RAG_EMBEDDER=openai")
        self._client = OpenAI(api_key=key)
        self._model_name = model_name

    def embed(self, texts: List[str]):
        import numpy as np
        resp = self._client.embeddings.create(model=self._model_name, input=texts)
        vecs = [d.embedding for d in resp.data]
        arr = np.asarray(vecs, dtype="float32")
        # normalize for cosine-by-dot-product
        norms = np.linalg.norm(arr, axis=1, keepdims=True)
        return arr / np.clip(norms, 1e-12, None)


def _get_embedder():
    backend = os.getenv("RAG_EMBEDDER", "local").lower()
    if backend == "openai":
        return _OpenAIEmbedder()
    return _LocalEmbedder()


# ── The index ──────────────────────────────────────────────────────────────────

@dataclass
class SearchHit:
    id: str
    text: str
    type: str
    score: float


class PerspectiveIndex:
    """
    A tiny on-disk vector index over the Perspective Bank.

    The corpus fingerprint (hash of all texts) is stored alongside vectors, so
    load_or_build() automatically rebuilds when perspectives change in Notion.
    """

    def __init__(self, perspectives: List[Dict], vectors, store_dir: Path = DEFAULT_STORE_DIR):
        self.perspectives = perspectives
        self.vectors = vectors  # np.ndarray [n, d], L2-normalized
        self.store_dir = Path(store_dir)

    # ── build / persist ────────────────────────────────────────────────────────

    @staticmethod
    def _fingerprint(perspectives: List[Dict]) -> str:
        joined = "\n".join(p["text"] for p in perspectives)
        return hashlib.sha256(joined.encode("utf-8")).hexdigest()[:16]

    @classmethod
    def build(cls, perspectives: List[Dict], store_dir: Path = DEFAULT_STORE_DIR) -> "PerspectiveIndex":
        if not perspectives:
            raise ValueError("Cannot build an index over zero perspectives")
        embedder = _get_embedder()
        logger.info("RAG: embedding %d perspectives…", len(perspectives))
        vectors = embedder.embed([p["text"] for p in perspectives])
        idx = cls(perspectives, vectors, store_dir)
        idx.save()
        return idx

    def save(self):
        import numpy as np
        self.store_dir.mkdir(parents=True, exist_ok=True)
        np.savez_compressed(self.store_dir / "vectors.npz", vectors=self.vectors)
        meta = {
            "fingerprint": self._fingerprint(self.perspectives),
            "perspectives": self.perspectives,
        }
        (self.store_dir / "meta.json").write_text(json.dumps(meta), encoding="utf-8")
        logger.info("RAG: index saved to %s (%d items)", self.store_dir, len(self.perspectives))

    @classmethod
    def load_or_build(cls, perspectives: List[Dict], store_dir: Path = DEFAULT_STORE_DIR) -> "PerspectiveIndex":
        """Load the cached index if it matches the current corpus; else rebuild."""
        import numpy as np
        store_dir = Path(store_dir)
        meta_path = store_dir / "meta.json"
        vec_path = store_dir / "vectors.npz"
        if meta_path.exists() and vec_path.exists():
            try:
                meta = json.loads(meta_path.read_text(encoding="utf-8"))
                if meta.get("fingerprint") == cls._fingerprint(perspectives):
                    vectors = np.load(vec_path)["vectors"]
                    logger.info("RAG: loaded cached index (%d items)", len(perspectives))
                    return cls(meta["perspectives"], vectors, store_dir)
                logger.info("RAG: corpus changed — rebuilding index")
            except Exception as e:  # cache corruption → rebuild
                logger.warning("RAG: cache unreadable (%s) — rebuilding", e)
        return cls.build(perspectives, store_dir)

    # ── search ─────────────────────────────────────────────────────────────────

    def search(self, query: str, k: int = 3, min_score: float = 0.25) -> List[SearchHit]:
        """Return the k most semantically similar perspectives to the query."""
        import numpy as np
        qvec = _get_embedder().embed([query])[0]
        scores = self.vectors @ qvec  # cosine similarity (both normalized)
        order = np.argsort(-scores)[:k]
        hits = []
        for i in order:
            s = float(scores[i])
            if s < min_score:
                continue
            p = self.perspectives[int(i)]
            hits.append(SearchHit(id=p["id"], text=p["text"], type=p.get("type", "Unknown"), score=s))
        return hits


# ── Integration helper for the originality injector ────────────────────────────

def retrieve_relevant_perspectives(
    all_perspectives: List[Dict],
    topic: str,
    k: int = 3,
    store_dir: Optional[Path] = None,
) -> List[Dict]:
    """
    Drop-in enhancement for the injector: given the channel's full perspective
    list (from Notion) and the script topic, return the k most relevant ones.
    Falls back to the first k on any RAG failure — retrieval quality is an
    enhancement, never a point of failure.
    """
    try:
        idx = PerspectiveIndex.load_or_build(
            all_perspectives, store_dir or DEFAULT_STORE_DIR
        )
        hits = idx.search(topic, k=k)
        if hits:
            return [{"id": h.id, "text": h.text, "type": h.type} for h in hits]
    except Exception as e:  # noqa: BLE001 — graceful degradation by design
        logger.warning("RAG retrieval failed (%s) — falling back to unranked perspectives", e)
    return all_perspectives[:k]
