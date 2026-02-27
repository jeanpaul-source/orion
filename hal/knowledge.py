"""pgvector knowledge base — semantic search over homelab docs."""

from datetime import datetime

try:
    import numpy as np
except ModuleNotFoundError:  # pragma: no cover
    np = None

import psycopg2
import psycopg2.extras
from pgvector.psycopg2 import register_vector

from hal.llm import OllamaClient

# Ground-truth docs (LAB_ENVIRONMENT.md, hand-written facts) are more
# authoritative than harvested reference material.  A +0.10 boost is enough
# to prefer them over a reference doc with a slightly better raw cosine score
# without drowning out a reference doc that is genuinely more relevant.
_GROUND_TRUTH_BOOST = 0.10

# Fetch this many extra candidates from the DB before applying the boost.
# Without over-fetch, a ground-truth doc sitting at position top_k+1 by raw
# cosine would never be fetched and therefore never receive the boost — exactly
# the case where the boost matters most.  3× is cheap (one ANN index scan).
_BOOST_FETCH_MULTIPLIER = 3


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

                # Fetch more candidates than needed so the post-fetch boost
                # can surface ground-truth docs that raw cosine ranked just
                # outside top_k.  Final slice back to top_k happens below.
                fetch_k = top_k * _BOOST_FETCH_MULTIPLIER
                params.extend([embedding, fetch_k])
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

        # Post-fetch boost: ground-truth docs get a score bump, then re-sort,
        # then slice back to the caller's requested top_k.
        if boost_ground_truth:
            for r in results:
                if r["doc_tier"] == "ground-truth":
                    r["score"] = min(1.0, r["score"] + _GROUND_TRUTH_BOOST)
            results.sort(key=lambda x: x["score"], reverse=True)

        return results[:top_k]

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

    def remember(self, fact: str) -> None:
        """Embed *fact* and upsert it into pgvector as category='memory'.

        Uses a ``memory://facts/<timestamp>`` path so the record survives
        re-harvests (harvest only clears its own source paths).
        """
        if np is None:
            raise RuntimeError("numpy is required for embeddings")
        embedding = np.array(self.llm.embed(fact))
        ts = datetime.now().strftime("%Y%m%d-%H%M%S")
        file_path = f"memory://facts/{ts}"
        conn = self._connect()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO documents
                        (file_path, file_name, category, file_type,
                         chunk_index, content, embedding, metadata, doc_tier)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (file_path, chunk_index) DO UPDATE SET
                        content   = EXCLUDED.content,
                        embedding = EXCLUDED.embedding,
                        doc_tier  = EXCLUDED.doc_tier
                    """,
                    (
                        file_path,
                        "fact",
                        "memory",
                        "text",
                        0,
                        fact,
                        embedding,
                        psycopg2.extras.Json({"recorded_at": ts}),
                        "memory",
                    ),
                )
            conn.commit()
        finally:
            conn.close()
