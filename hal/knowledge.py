"""pgvector knowledge base — semantic search over homelab docs."""
import numpy as np
import psycopg2
from pgvector.psycopg2 import register_vector

from hal.llm import OllamaClient


class KnowledgeBase:
    def __init__(self, dsn: str, llm: OllamaClient):
        self.dsn = dsn
        self.llm = llm

    def _connect(self):
        conn = psycopg2.connect(self.dsn)
        register_vector(conn)
        return conn

    def search(
        self, query: str, top_k: int = 5, category: str | None = None
    ) -> list[dict]:
        embedding = np.array(self.llm.embed(query))
        conn = self._connect()
        try:
            with conn.cursor() as cur:
                if category:
                    cur.execute(
                        """
                        SELECT content, file_name, category,
                               1 - (embedding <=> %s) AS score
                        FROM documents
                        WHERE category = %s
                        ORDER BY embedding <=> %s
                        LIMIT %s
                        """,
                        (embedding, category, embedding, top_k),
                    )
                else:
                    cur.execute(
                        """
                        SELECT content, file_name, category,
                               1 - (embedding <=> %s) AS score
                        FROM documents
                        ORDER BY embedding <=> %s
                        LIMIT %s
                        """,
                        (embedding, embedding, top_k),
                    )
                rows = cur.fetchall()
        finally:
            conn.close()

        return [
            {"content": r[0], "file": r[1], "category": r[2], "score": float(r[3])}
            for r in rows
        ]

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
