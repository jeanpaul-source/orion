"""pgvector knowledge base — semantic search over homelab docs."""

try:
    import numpy as np
except ModuleNotFoundError:  # pragma: no cover
    np = None

import psycopg2
from pgvector.psycopg2 import register_vector

from hal.llm import OllamaClient

_GROUND_TRUTH_BOOST = 0.10


class KnowledgeBase:
    def __init__(self, dsn: str, llm: OllamaClient):
        self.dsn = dsn
        self.llm = llm

    def _connect(self):
        conn = psycopg2.connect(self.dsn)
        register_vector(conn)
        return conn

    def search(
        self,
        query: str,
        top_k: int = 5,
        category: str | None = None,
        doc_tier: str | None = None,
        boost_ground_truth: bool = True,
    ) -> list[dict]:
        if np is None:
            raise RuntimeError("numpy is required for embeddings")
        embedding = np.array(self.llm.embed(query))
        conn = self._connect()
        try:
            with conn.cursor() as cur:
                conditions = []
                params: list = [embedding]
                if category:
                    conditions.append("category = %s")
                    params.append(category)
                if doc_tier:
                    conditions.append("doc_tier = %s")
                    params.append(doc_tier)

                where = ""
                if conditions:
                    where = "WHERE " + " AND ".join(conditions)

                params.extend([embedding, top_k])
                cur.execute(
                    f"""
                    SELECT content, file_name, category,
                           1 - (embedding <=> %s) AS score,
                           COALESCE(doc_tier, 'reference') AS doc_tier
                    FROM documents
                    {where}
                    ORDER BY embedding <=> %s
                    LIMIT %s
                    """,
                    params,
                )
                rows = cur.fetchall()
        finally:
            conn.close()

        results = [
            {
                "content": r[0],
                "file": r[1],
                "category": r[2],
                "score": float(r[3]),
                "doc_tier": r[4],
            }
            for r in rows
        ]

        # Post-fetch boost: ground-truth docs get a score bump
        if boost_ground_truth:
            for r in results:
                if r["doc_tier"] == "ground-truth":
                    r["score"] = min(1.0, r["score"] + _GROUND_TRUTH_BOOST)
            results.sort(key=lambda x: x["score"], reverse=True)

        return results

    def categories(self) -> list[tuple[str, int]]:
        conn = self._connect()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT category, count(*) FROM documents GROUP BY category ORDER BY count DESC"
                )
                return cur.fetchall()
        finally:
            conn.close()
