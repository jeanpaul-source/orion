"""Ingest documents into pgvector — chunk, embed, upsert."""
import numpy as np
import psycopg2
from pgvector.psycopg2 import register_vector

from hal.llm import OllamaClient

CHUNK_SIZE = 800   # characters
CHUNK_OVERLAP = 100
LAB_CATEGORIES = {"lab-infrastructure", "lab-state"}


def _chunk(text: str) -> list[str]:
    """Split text into overlapping chunks at line boundaries."""
    if len(text) <= CHUNK_SIZE:
        return [text]

    chunks = []
    lines = text.splitlines(keepends=True)
    current = ""

    for line in lines:
        if len(current) + len(line) > CHUNK_SIZE and current:
            chunks.append(current.strip())
            # overlap: keep last CHUNK_OVERLAP chars
            current = current[-CHUNK_OVERLAP:] + line
        else:
            current += line

    if current.strip():
        chunks.append(current.strip())

    return chunks or [text]


def clear_lab_docs(conn) -> int:
    """Delete all existing lab-infrastructure and lab-state rows before re-harvest."""
    with conn.cursor() as cur:
        cur.execute(
            "DELETE FROM documents WHERE category = ANY(%s)",
            (list(LAB_CATEGORIES),),
        )
        deleted = cur.rowcount
    conn.commit()
    return deleted


def upsert_doc(cur, file_path: str, file_name: str, category: str,
               chunk_index: int, content: str, embedding: list[float],
               metadata: dict) -> None:
    cur.execute(
        """
        INSERT INTO documents
            (file_path, file_name, category, file_type, chunk_index, content, embedding, metadata)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (file_path, chunk_index)
        DO UPDATE SET
            content   = EXCLUDED.content,
            embedding = EXCLUDED.embedding,
            file_name = EXCLUDED.file_name,
            category  = EXCLUDED.category,
            metadata  = EXCLUDED.metadata
        """,
        (
            file_path, file_name, category, "text",
            chunk_index, content,
            np.array(embedding),
            psycopg2.extras.Json(metadata),
        ),
    )


def ingest(docs: list[dict], dsn: str, llm: OllamaClient, dry_run: bool = False) -> dict:
    conn = psycopg2.connect(dsn)
    register_vector(conn)
    psycopg2.extras  # ensure Json is available

    stats = {"deleted": 0, "chunks": 0, "docs": 0, "errors": 0}

    if not dry_run:
        stats["deleted"] = clear_lab_docs(conn)
        print(f"  cleared {stats['deleted']} existing lab docs")

    with conn.cursor() as cur:
        for doc in docs:
            chunks = _chunk(doc["content"])
            doc_errors = 0
            for i, chunk in enumerate(chunks):
                if dry_run:
                    print(f"  [dry-run] {doc['file_path']} chunk {i}: {len(chunk)} chars")
                    stats["chunks"] += 1
                    continue
                try:
                    embedding = llm.embed(chunk)
                    upsert_doc(
                        cur,
                        file_path=doc["file_path"],
                        file_name=doc["file_name"],
                        category=doc["category"],
                        chunk_index=i,
                        content=chunk,
                        embedding=embedding,
                        metadata=doc.get("metadata", {}),
                    )
                    stats["chunks"] += 1
                except Exception as e:
                    print(f"  ERROR embedding {doc['file_path']} chunk {i}: {e}")
                    doc_errors += 1
                    stats["errors"] += 1

            if doc_errors == 0:
                stats["docs"] += 1

        if not dry_run:
            conn.commit()

    conn.close()
    return stats
