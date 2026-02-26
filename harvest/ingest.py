"""Ingest documents into pgvector — chunk, embed, upsert."""

import logging

import numpy as np
import psycopg2
import psycopg2.extras
from pgvector.psycopg2 import register_vector

from hal.llm import OllamaClient
from harvest.parsers import content_hash

log = logging.getLogger(__name__)

CHUNK_SIZE = 800  # characters
CHUNK_OVERLAP = 100
LAB_CATEGORIES = {"lab-infrastructure", "lab-state"}
GROUND_TRUTH_CATEGORIES = {"ground-truth"}


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


def ensure_doc_tier_column(conn) -> None:
    """Add doc_tier column if missing and backfill existing rows (idempotent)."""
    with conn.cursor() as cur:
        cur.execute(
            "ALTER TABLE documents ADD COLUMN IF NOT EXISTS doc_tier TEXT DEFAULT 'reference'"
        )
        cur.execute(
            "UPDATE documents SET doc_tier = 'live-state' "
            "WHERE category = ANY(%s) AND (doc_tier IS NULL OR doc_tier = 'reference')",
            (list(LAB_CATEGORIES),),
        )
        cur.execute(
            "UPDATE documents SET doc_tier = 'memory' "
            "WHERE category = 'memory' AND (doc_tier IS NULL OR doc_tier = 'reference')",
        )
    conn.commit()


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


def clear_ground_truth(conn) -> int:
    """Delete all ground-truth rows before re-harvest."""
    with conn.cursor() as cur:
        cur.execute(
            "DELETE FROM documents WHERE category = ANY(%s)",
            (list(GROUND_TRUTH_CATEGORIES),),
        )
        deleted = cur.rowcount
    conn.commit()
    return deleted


# --- Incremental ingestion helpers ---


def _file_needs_update(cur, file_path: str, new_chunks: list[str]) -> bool:
    """Return True if this file's chunks have changed since last ingestion."""
    cur.execute(
        "SELECT chunk_index, metadata->>'content_hash' AS hash "
        "FROM documents WHERE file_path = %s ORDER BY chunk_index",
        (file_path,),
    )
    existing = {row[0]: row[1] for row in cur.fetchall()}

    if len(existing) != len(new_chunks):
        return True  # chunk count changed

    for i, chunk in enumerate(new_chunks):
        if existing.get(i) != content_hash(chunk):
            return True  # content changed

    return False  # identical


def _delete_file_chunks(cur, file_path: str) -> int:
    """Delete all chunks for a given file_path."""
    cur.execute("DELETE FROM documents WHERE file_path = %s", (file_path,))
    return cur.rowcount


def _clean_orphan_static_docs(cur, current_file_paths: set[str]) -> int:
    """Delete rows for reference docs whose source files no longer exist on disk."""
    cur.execute(
        "SELECT DISTINCT file_path FROM documents WHERE file_path LIKE %s",
        (STATIC_DOCS_ROOT + "/%",),
    )
    db_paths = {row[0] for row in cur.fetchall()}
    orphans = db_paths - current_file_paths
    if not orphans:
        return 0
    cur.execute(
        "DELETE FROM documents WHERE file_path = ANY(%s)",
        (list(orphans),),
    )
    return cur.rowcount


def upsert_doc(
    cur,
    file_path: str,
    file_name: str,
    category: str,
    chunk_index: int,
    content: str,
    embedding: list[float],
    metadata: dict,
    doc_tier: str = "reference",
) -> None:
    cur.execute(
        """
        INSERT INTO documents
            (file_path, file_name, category, file_type, chunk_index, content, embedding, metadata, doc_tier)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (file_path, chunk_index)
        DO UPDATE SET
            content   = EXCLUDED.content,
            embedding = EXCLUDED.embedding,
            file_name = EXCLUDED.file_name,
            category  = EXCLUDED.category,
            metadata  = EXCLUDED.metadata,
            doc_tier  = EXCLUDED.doc_tier
        """,
        (
            file_path,
            file_name,
            category,
            "text",
            chunk_index,
            content,
            np.array(embedding),
            psycopg2.extras.Json(metadata),
            doc_tier,
        ),
    )


def ingest(
    docs: list[dict], dsn: str, llm: OllamaClient, dry_run: bool = False
) -> dict:
    conn = psycopg2.connect(dsn)
    register_vector(conn)

    stats = {"deleted": 0, "chunks": 0, "docs": 0, "errors": 0, "skipped": 0}

    try:
        if not dry_run:
            ensure_doc_tier_column(conn)
            # Always clear and re-ingest lab state + ground truth (small, change often)
            n_lab = clear_lab_docs(conn)
            n_gt = clear_ground_truth(conn)
            stats["deleted"] = n_lab + n_gt
            print(f"  cleared {n_lab} lab, {n_gt} ground-truth docs")
            # Reference docs use incremental mode — no bulk clear

        # Track reference doc file_paths for orphan cleanup
        reference_file_paths: set[str] = set()

        with conn.cursor() as cur:
            for doc in docs:
                chunks = _chunk(doc["content"])
                doc_tier = doc.get("doc_tier", "reference")

                if doc_tier == "reference":
                    reference_file_paths.add(doc["file_path"])

                # Incremental: skip unchanged reference docs
                if not dry_run and doc_tier == "reference":
                    if not _file_needs_update(cur, doc["file_path"], chunks):
                        stats["skipped"] += 1
                        stats["docs"] += 1
                        continue
                    # Changed — delete old chunks first
                    n_del = _delete_file_chunks(cur, doc["file_path"])
                    if n_del:
                        stats["deleted"] += n_del

                doc_errors = 0
                for i, chunk in enumerate(chunks):
                    if dry_run:
                        print(
                            f"  [dry-run] {doc['file_path']} chunk {i}: {len(chunk)} chars"
                        )
                        stats["chunks"] += 1
                        continue
                    try:
                        embedding = llm.embed(chunk)
                        meta = {
                            **doc.get("metadata", {}),
                            "content_hash": content_hash(chunk),
                        }
                        upsert_doc(
                            cur,
                            file_path=doc["file_path"],
                            file_name=doc["file_name"],
                            category=doc["category"],
                            chunk_index=i,
                            content=chunk,
                            embedding=embedding,
                            metadata=meta,
                            doc_tier=doc_tier,
                        )
                        stats["chunks"] += 1
                    except Exception as e:
                        print(f"  ERROR embedding {doc['file_path']} chunk {i}: {e}")
                        doc_errors += 1
                        stats["errors"] += 1

                if doc_errors == 0:
                    stats["docs"] += 1

            # Orphan cleanup: delete DB rows for reference docs no longer on disk
            if not dry_run and reference_file_paths:
                n_orphans = _clean_orphan_static_docs(cur, reference_file_paths)
                if n_orphans:
                    stats["deleted"] += n_orphans
                    print(f"  cleaned {n_orphans} orphan static doc chunks")

            if not dry_run:
                conn.commit()
    finally:
        conn.close()

    if stats["skipped"]:
        print(f"  skipped {stats['skipped']} unchanged reference docs")

    return stats
