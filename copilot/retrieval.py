"""Runbook retrieval: chunking + a pluggable embedder + an in-memory vector index (cosine similarity).

The default embedder is TF-IDF (no downloads, fully offline). `fastembed` (BAAI/bge-small-en-v1.5)
is used when installed and requested, so the same index supports real dense vector search.
Swap VectorIndex for pgvector when the corpus outgrows memory.
"""
from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import numpy as np

RUNBOOK_DIR = Path(__file__).resolve().parent.parent / "runbooks"


@dataclass(frozen=True)
class Chunk:
    runbook: str   # file stem, used as the label in retrieval evals
    title: str
    section: str
    text: str


def load_chunks(directory: Path = RUNBOOK_DIR) -> list[Chunk]:
    chunks: list[Chunk] = []
    for path in sorted(directory.glob("*.md")):
        raw = path.read_text()
        title = raw.splitlines()[0].lstrip("# ").strip()
        for part in raw.split("\n## ")[1:]:
            section, _, body = part.partition("\n")
            chunks.append(Chunk(path.stem, title, section.strip(), f"{title} - {section.strip()}\n{body.strip()}"))
    return chunks


class TfidfEmbedder:
    name = "tfidf"

    def fit(self, texts: list[str]) -> None:
        from sklearn.feature_extraction.text import TfidfVectorizer
        self.vec = TfidfVectorizer(ngram_range=(1, 2), sublinear_tf=True, stop_words="english")
        self.vec.fit(texts)

    def embed(self, texts: list[str]) -> np.ndarray:
        m = self.vec.transform(texts).toarray().astype("float32")
        return m / (np.linalg.norm(m, axis=1, keepdims=True) + 1e-9)


class FastEmbedEmbedder:
    name = "fastembed"

    def fit(self, texts: list[str]) -> None:
        from fastembed import TextEmbedding  # pip install fastembed
        self.model = TextEmbedding("BAAI/bge-small-en-v1.5")

    def embed(self, texts: list[str]) -> np.ndarray:
        m = np.array(list(self.model.embed(texts)), dtype="float32")
        return m / (np.linalg.norm(m, axis=1, keepdims=True) + 1e-9)


EMBEDDERS = {"tfidf": TfidfEmbedder, "fastembed": FastEmbedEmbedder}


class VectorIndex:
    def __init__(self, chunks: list[Chunk], embedder_name: str = "tfidf"):
        self.chunks = chunks
        self.embedder = EMBEDDERS[embedder_name]()
        self.embedder.fit([c.text for c in chunks])
        self.vectors = self.embedder.embed([c.text for c in chunks])

    def search(self, query: str, k: int = 3) -> list[tuple[Chunk, float]]:
        q = self.embedder.embed([query])[0]
        scores = self.vectors @ q
        top = np.argsort(-scores)[:k]
        return [(self.chunks[i], float(scores[i])) for i in top]


@lru_cache(maxsize=4)
def get_index(embedder_name: str = "tfidf") -> VectorIndex:
    return VectorIndex(load_chunks(), embedder_name)
