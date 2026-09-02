"""FAISS-backed local retrieval over RAG chunks."""

from __future__ import annotations

from collections.abc import Sequence

import numpy as np

from .embeddings import EmbeddingService
from .schemas import Chunk, RetrievalResult, SourceType

MEMO_TOPIC_QUERIES = {
    "executive_summary": "business overview strategy performance risks recent developments",
    "financial_overview": "revenue profitability margins debt cash flow financial performance",
    "risk_factors": "business risks regulatory risks operational risks financial risks",
    "sentiment_news": "recent developments company announcements important news market sentiment",
    "competitor_comparison": "market position competitors peer comparison industry performance",
}


class Retriever:
    """Build and search a FAISS inner-product index over normalized chunks."""

    def __init__(
        self,
        chunks: Sequence[Chunk],
        *,
        embedding_service: EmbeddingService | None = None,
        embeddings: np.ndarray | None = None,
    ):
        self.chunks = list(chunks)
        self.embedding_service = embedding_service or EmbeddingService()
        if embeddings is not None:
            self.embeddings = np.asarray(embeddings, dtype=np.float32)
        elif self.chunks:
            self.embeddings = self.embedding_service.embed_chunks(self.chunks)
        else:
            self.embeddings = np.empty((0, self.embedding_service.dimension), dtype=np.float32)

        if len(self.chunks) != len(self.embeddings):
            raise ValueError("Number of chunks must match number of embeddings.")

        self.dimension = (
            int(self.embeddings.shape[1])
            if self.embeddings.ndim == 2 and self.embeddings.shape[0] > 0
            else self.embedding_service.dimension
        )
        self.index = self._build_index(self.embeddings)

    @property
    def index_type(self) -> str:
        return "faiss.IndexFlatIP"

    @property
    def metric(self) -> str:
        return "inner_product_on_normalized_vectors"

    def search(
        self,
        query: str,
        *,
        top_k: int = 5,
        ticker: str | None = None,
        source_type: SourceType | None = None,
    ) -> list[RetrievalResult]:
        if top_k <= 0 or not self.chunks:
            return []

        candidate_indices = self._candidate_indices(ticker=ticker, source_type=source_type)
        if not candidate_indices:
            return []

        query_vector = self.embedding_service.embed_query(query).astype(np.float32).reshape(1, -1)
        candidate_vectors = self.embeddings[candidate_indices]
        index = self.index if len(candidate_indices) == len(self.chunks) else self._build_index(candidate_vectors)
        limit = min(top_k, len(candidate_indices))
        scores, local_indices = index.search(query_vector, limit)

        results: list[RetrievalResult] = []
        for rank, (score, local_idx) in enumerate(zip(scores[0], local_indices[0]), start=1):
            if local_idx < 0:
                continue
            original_idx = candidate_indices[int(local_idx)]
            results.append(
                RetrievalResult(
                    chunk=self.chunks[original_idx],
                    score=float(score),
                    rank=rank,
                )
            )
        return results

    def _candidate_indices(
        self,
        *,
        ticker: str | None,
        source_type: SourceType | None,
    ) -> list[int]:
        normalized_ticker = ticker.upper() if ticker else None
        return [
            idx
            for idx, chunk in enumerate(self.chunks)
            if (normalized_ticker is None or chunk.ticker.upper() == normalized_ticker)
            and (source_type is None or chunk.source_type == source_type)
        ]

    def _build_index(self, vectors: np.ndarray):
        try:
            import faiss
        except ImportError as exc:
            raise RuntimeError(
                "faiss-cpu is required for local vector search. "
                "Install with: py -3.10 -m pip install faiss-cpu"
            ) from exc

        index = faiss.IndexFlatIP(self.dimension)
        if vectors.size:
            index.add(np.ascontiguousarray(vectors, dtype=np.float32))
        return index
