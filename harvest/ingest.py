"""Ingest documents into pgvector — chunk, embed, upsert."""
import numpy as np
import psycopg2
import psycopg2.extras
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


STATIC_DOCS_ROOT = "/data/orion/orion-data/documents/raw"


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


def clear_static_docs(conn) -> int:
    """Delete all rows whose file_path lives under the static docs root.

    Ensures that files removed from disk don't leave orphan chunks in the KB.
    Old-pipeline PDFs (under /docker/orion-data/...) are left untouched.
    """
    with conn.cursor() as cur:
        cur.execute(
            "DELETE FROM documents WHERE file_path LIKE %s",
            (STATIC_DOCS_ROOT + "/%",),
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

    stats = {"deleted": 0, "chunks": 0, "docs": 0, "errors": 0}

    if not dry_run:
        n_lab = clear_lab_docs(conn)
        n_static = clear_static_docs(conn)
        stats["deleted"] = n_lab + n_static
        print(f"  cleared {n_lab} existing lab docs, {n_static} static doc chunks")

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
