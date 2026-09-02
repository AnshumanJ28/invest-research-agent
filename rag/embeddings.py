"""Local embedding service for Role 3 retrieval.

Uses sentence-transformers locally. No hosted embedding API is called.
"""

from __future__ import annotations

import os
from collections.abc import Sequence
from pathlib import Path

import numpy as np

from .schemas import Chunk

DEFAULT_MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"


class EmbeddingService:
    """Small wrapper around SentenceTransformer with normalized outputs."""

    def __init__(self, model_name: str = DEFAULT_MODEL_NAME):
        self.model_name = model_name
        self._model = None

    @property
    def model(self):
        if self._model is None:
            cache_dir = Path(__file__).resolve().parent / ".cache" / "huggingface"
            cache_dir.mkdir(parents=True, exist_ok=True)
            os.environ.setdefault("HF_HOME", str(cache_dir))
            os.environ.setdefault("HUGGINGFACE_HUB_CACHE", str(cache_dir / "hub"))
            try:
                from sentence_transformers import SentenceTransformer
            except ImportError as exc:
                raise RuntimeError(
                    "sentence-transformers is required for local embeddings. "
                    "Install with: py -3.10 -m pip install sentence-transformers"
                ) from exc
            model_name_or_path = _local_model_snapshot(cache_dir, self.model_name) or self.model_name
            try:
                self._model = SentenceTransformer(
                    str(model_name_or_path),
                    cache_folder=str(cache_dir),
                    local_files_only=True,
                )
            except Exception:
                self._model = SentenceTransformer(
                    self.model_name,
                    cache_folder=str(cache_dir),
                    local_files_only=False,
                )
        return self._model

    @property
    def dimension(self) -> int:
        dim = self.model.get_sentence_embedding_dimension()
        if dim is None:
            sample = self.embed_texts(["dimension probe"])
            return int(sample.shape[1])
        return int(dim)

    def embed_chunks(self, chunks: Sequence[Chunk]) -> np.ndarray:
        return self.embed_texts([chunk.text for chunk in chunks])

    def embed_query(self, query: str) -> np.ndarray:
        vectors = self.embed_texts([query])
        return vectors[0]

    def embed_texts(self, texts: Sequence[str]) -> np.ndarray:
        if not texts:
            return np.empty((0, self.dimension), dtype=np.float32)

        vectors = self.model.encode(
            list(texts),
            convert_to_numpy=True,
            normalize_embeddings=True,
            show_progress_bar=False,
        )
        return np.asarray(vectors, dtype=np.float32)


def _local_model_snapshot(cache_dir: Path, model_name: str) -> Path | None:
    model_cache_name = "models--" + model_name.replace("/", "--")
    snapshots_dir = cache_dir / "hub" / model_cache_name / "snapshots"
    if not snapshots_dir.exists():
        return None
    for snapshot in snapshots_dir.iterdir():
        if (snapshot / "modules.json").exists() and (snapshot / "config.json").exists():
            return snapshot
    return None
