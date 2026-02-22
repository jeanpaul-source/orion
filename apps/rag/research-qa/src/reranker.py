"""
Reranking module for improving retrieval quality with cross-encoder models.

ELI5: Think of vector search as finding "similar-looking" documents quickly (approximate).
Cross-encoder reranking is like carefully reading each candidate to find the BEST match (exact).

Two-stage retrieval:
1. Fast vector search → Get top 20 candidates (100-200ms)
2. Slow cross-encoder reranking → Rerank to top 5 (200-500ms)

Result: 20-30% better relevance at cost of ~500ms latency.

Created: 2025-11-17 (Optimization Phase)
"""

import logging
from typing import List, Tuple, Optional
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class RankedResult:
    """A search result with reranking score."""
    text: str
    score: float
    metadata: dict
    original_rank: int  # Position from vector search


class Reranker:
    """
    Cross-encoder reranker for improving retrieval quality.

    Uses sentence-transformers cross-encoder models to score
    query-document pairs more accurately than vector similarity.
    """

    def __init__(self, model_name: str = "cross-encoder/ms-marco-MiniLM-L-6-v2"):
        """
        Initialize reranker with specified cross-encoder model.

        Args:
            model_name: HuggingFace model name for cross-encoder.
                       Default: ms-marco-MiniLM-L-6-v2 (fast, good quality)

        Alternative models:
            - cross-encoder/ms-marco-MiniLM-L-12-v2 (better quality, slower)
            - cross-encoder/ms-marco-TinyBERT-L-2-v2 (faster, lower quality)
        """
        self.model_name = model_name
        self.model = None
        self._lazy_load_model()

    def _lazy_load_model(self):
        """Lazy load model on first use to avoid startup delay."""
        if self.model is None:
            try:
                from sentence_transformers import CrossEncoder
                logger.info(f"Loading cross-encoder model: {self.model_name}")
                self.model = CrossEncoder(self.model_name)
                logger.info(f"✓ Cross-encoder loaded successfully")
            except ImportError:
                logger.error(
                    "sentence-transformers not installed. "
                    "Install with: pip install sentence-transformers"
                )
                raise
            except Exception as e:
                logger.error(f"Failed to load cross-encoder: {e}")
                raise

    def rerank(
        self,
        query: str,
        candidates: List[dict],
        top_k: int = 5,
        text_key: str = "text"
    ) -> List[RankedResult]:
        """
        Rerank candidates using cross-encoder.

        Args:
            query: User query string
            candidates: List of candidate documents (from vector search)
                       Each must have text_key field and optional metadata
            top_k: Number of top results to return
            text_key: Key name for text content in candidate dict

        Returns:
            List of RankedResult objects sorted by score (descending)

        Example:
            >>> candidates = [
            ...     {"text": "Kubernetes autoscaling guide...", "source": "doc1.pdf"},
            ...     {"text": "Docker container scaling...", "source": "doc2.pdf"},
            ... ]
            >>> reranker = Reranker()
            >>> results = reranker.rerank("kubernetes autoscaling", candidates, top_k=5)
            >>> for r in results:
            ...     print(f"Score: {r.score:.3f} - {r.text[:50]}...")
        """
        if not candidates:
            logger.warning("No candidates provided for reranking")
            return []

        # Ensure model is loaded
        if self.model is None:
            self._lazy_load_model()

        # Extract texts and create query-document pairs
        texts = [c.get(text_key, "") for c in candidates]
        pairs = [(query, text) for text in texts]

        logger.debug(f"Reranking {len(pairs)} candidates with query: {query[:50]}...")

        # Score all pairs
        scores = self.model.predict(pairs)

        # Create ranked results
        results = []
        for idx, (candidate, score) in enumerate(zip(candidates, scores)):
            # Extract metadata (everything except text)
            metadata = {k: v for k, v in candidate.items() if k != text_key}

            results.append(RankedResult(
                text=candidate.get(text_key, ""),
                score=float(score),
                metadata=metadata,
                original_rank=idx
            ))

        # Sort by score (descending) and limit to top_k
        results.sort(key=lambda x: x.score, reverse=True)
        top_results = results[:top_k]

        logger.info(
            f"Reranked {len(candidates)} → {len(top_results)} results. "
            f"Top score: {top_results[0].score:.3f}"
        )

        return top_results

    def rerank_batch(
        self,
        queries: List[str],
        candidates_list: List[List[dict]],
        top_k: int = 5,
        text_key: str = "text"
    ) -> List[List[RankedResult]]:
        """
        Rerank multiple queries in batch.

        Args:
            queries: List of query strings
            candidates_list: List of candidate lists (one per query)
            top_k: Number of top results per query
            text_key: Key name for text content

        Returns:
            List of ranked result lists (one per query)
        """
        results = []
        for query, candidates in zip(queries, candidates_list):
            ranked = self.rerank(query, candidates, top_k, text_key)
            results.append(ranked)
        return results


def rrf_merge(
    vector_results: List[dict],
    keyword_results: List[dict],
    k: int = 60,
    vector_weight: float = 0.7,
    keyword_weight: float = 0.3
) -> List[dict]:
    """
    Merge vector and keyword search results using Reciprocal Rank Fusion (RRF).

    RRF formula: score(d) = Σ 1/(k + rank(d))

    Args:
        vector_results: Results from vector similarity search (ordered by score)
        keyword_results: Results from keyword/BM25 search (ordered by relevance)
        k: RRF parameter (default: 60, from research papers)
        vector_weight: Weight for vector search scores
        keyword_weight: Weight for keyword search scores

    Returns:
        Merged and deduplicated results, sorted by combined RRF score

    Example:
        >>> vector_results = [{"id": "doc1", "text": "..."}, {"id": "doc2", "text": "..."}]
        >>> keyword_results = [{"id": "doc2", "text": "..."}, {"id": "doc3", "text": "..."}]
        >>> merged = rrf_merge(vector_results, keyword_results)
        >>> # doc2 appears in both → higher score
    """
    from collections import defaultdict

    # Calculate RRF scores
    rrf_scores = defaultdict(float)
    doc_map = {}  # Store full document by ID

    # Score vector results
    for rank, doc in enumerate(vector_results, start=1):
        doc_id = doc.get("id") or doc.get("text")  # Use ID or text as key
        rrf_scores[doc_id] += vector_weight * (1.0 / (k + rank))
        if doc_id not in doc_map:
            doc_map[doc_id] = doc

    # Score keyword results
    for rank, doc in enumerate(keyword_results, start=1):
        doc_id = doc.get("id") or doc.get("text")
        rrf_scores[doc_id] += keyword_weight * (1.0 / (k + rank))
        if doc_id not in doc_map:
            doc_map[doc_id] = doc

    # Sort by combined RRF score
    ranked_ids = sorted(rrf_scores.keys(), key=lambda x: rrf_scores[x], reverse=True)

    # Return merged results with scores
    merged = []
    for doc_id in ranked_ids:
        doc = doc_map[doc_id].copy()
        doc["rrf_score"] = rrf_scores[doc_id]
        merged.append(doc)

    logger.info(
        f"RRF merged {len(vector_results)} vector + {len(keyword_results)} keyword "
        f"→ {len(merged)} unique results"
    )

    return merged


# Example usage
if __name__ == "__main__":
    import logging
    logging.basicConfig(level=logging.INFO)

    # Sample candidates from vector search
    candidates = [
        {
            "text": "Kubernetes autoscaling uses Horizontal Pod Autoscaler (HPA) to automatically scale pods based on CPU/memory metrics or custom metrics.",
            "source": "k8s-official-docs.pdf",
            "similarity": 0.89
        },
        {
            "text": "Docker Swarm provides basic container scaling but lacks the sophisticated autoscaling of Kubernetes.",
            "source": "docker-swarm-guide.pdf",
            "similarity": 0.76
        },
        {
            "text": "Autoscaling in cloud platforms like AWS uses Auto Scaling Groups to manage EC2 instances.",
            "source": "aws-autoscaling.pdf",
            "similarity": 0.72
        },
    ]

    # Rerank with cross-encoder
    reranker = Reranker()
    query = "How to configure Kubernetes autoscaling with custom metrics?"

    results = reranker.rerank(query, candidates, top_k=2)

    print("\n" + "="*80)
    print("RERANKING RESULTS")
    print("="*80)
    print(f"Query: {query}\n")

    for i, result in enumerate(results, 1):
        print(f"{i}. Score: {result.score:.4f} (was rank {result.original_rank + 1})")
        print(f"   Source: {result.metadata.get('source', 'unknown')}")
        print(f"   Text: {result.text[:100]}...")
        print()
