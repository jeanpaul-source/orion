"""Write persistent facts into pgvector as category='memory'."""

from datetime import datetime

import numpy as np
import psycopg2
import psycopg2.extras
from pgvector.psycopg2 import register_vector

from hal.llm import OllamaClient


def remember(fact: str, dsn: str, llm: OllamaClient) -> None:
    """Embed a fact and upsert it into pgvector. Survives re-harvests."""
    embedding = llm.embed(fact)
    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    file_path = f"memory://facts/{ts}"

    conn = psycopg2.connect(dsn)
    register_vector(conn)
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
                    np.array(embedding),
                    psycopg2.extras.Json({"recorded_at": ts}),
                    "memory",
                ),
            )
        conn.commit()
    finally:
        conn.close()
