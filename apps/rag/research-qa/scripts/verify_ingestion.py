#!/usr/bin/env python3
"""
Verification script for ORION RAG ingestion
Runs before/during/after batch processing to validate state

Usage:
    python verify_ingestion.py
    python verify_ingestion.py --registry-db /path/to/ingestion.db
    python verify_ingestion.py --qdrant-url http://192.168.5.10:6333

Created: 2025-11-20
"""
import os
import sys
import sqlite3
from pathlib import Path
from typing import Dict, Any
import argparse


def check_registry_consistency(registry_db: Path) -> Dict[str, Any]:
    """Verify ingestion registry integrity"""
    results = {
        "total_documents": 0,
        "by_status": {},
        "by_domain": {},
        "by_collection": {},
        "issues": [],
    }

    try:
        conn = sqlite3.connect(registry_db)
        cursor = conn.cursor()

        # Total documents
        cursor.execute("SELECT COUNT(*) FROM documents")
        results["total_documents"] = cursor.fetchone()[0]

        # By status
        cursor.execute("SELECT status, COUNT(*) FROM documents GROUP BY status")
        results["by_status"] = dict(cursor.fetchall())

        # By domain
        cursor.execute(
            "SELECT document_type, COUNT(*) FROM documents GROUP BY document_type"
        )
        results["by_domain"] = dict(cursor.fetchall())

        # By collection
        cursor.execute(
            "SELECT collection_name, COUNT(*) FROM documents GROUP BY collection_name"
        )
        results["by_collection"] = dict(cursor.fetchall())

        # Check for duplicates
        cursor.execute(
            """
            SELECT content_hash, COUNT(*) as cnt
            FROM documents
            WHERE status = 'ingested'
            GROUP BY content_hash
            HAVING cnt > 1
        """
        )
        duplicates = cursor.fetchall()
        if duplicates:
            results["issues"].append(
                f"Found {len(duplicates)} duplicate content hashes"
            )

        conn.close()

    except Exception as e:
        results["issues"].append(f"Registry check failed: {e}")

    return results


def check_qdrant_collections(
    qdrant_url: str = "http://127.0.0.1:6333",
) -> Dict[str, Any]:
    """Verify Qdrant collection state"""
    try:
        import requests
    except ImportError:
        return {
            "collections": {},
            "total_vectors": 0,
            "issues": ["requests library not installed - skipping Qdrant check"],
        }

    results = {"collections": {}, "total_vectors": 0, "issues": []}

    try:
        # List collections
        resp = requests.get(f"{qdrant_url}/collections", timeout=10)
        resp.raise_for_status()

        collections = resp.json()["result"]["collections"]

        for coll in collections:
            coll_name = coll["name"]

            # Get collection info
            resp = requests.get(f"{qdrant_url}/collections/{coll_name}", timeout=10)
            info = resp.json()["result"]

            vector_count = info["vectors_count"]
            indexed_vectors = info.get("indexed_vectors_count", 0)

            results["collections"][coll_name] = {
                "vector_count": vector_count,
                "indexed_count": indexed_vectors,
                "status": info["status"],
            }

            results["total_vectors"] += vector_count

            # Check for indexing lag
            if vector_count - indexed_vectors > 1000:
                results["issues"].append(
                    f"{coll_name}: {vector_count - indexed_vectors} vectors not indexed yet"
                )

    except Exception as e:
        results["issues"].append(f"Qdrant check failed: {e}")

    return results


def print_report(registry_results: Dict, qdrant_results: Dict):
    """Print formatted verification report"""
    print("=" * 70)
    print("ORION RAG INGESTION VERIFICATION")
    print("=" * 70)

    # Registry stats
    print("\n📊 INGESTION REGISTRY")
    print(f"  Total documents: {registry_results['total_documents']}")

    if registry_results["by_status"]:
        print("\n  By Status:")
        for status, count in registry_results["by_status"].items():
            print(f"    {status:12s}: {count:5d}")

    if registry_results["by_domain"]:
        print("\n  By Domain:")
        for domain, count in registry_results["by_domain"].items():
            print(f"    {domain:12s}: {count:5d}")

    if registry_results["by_collection"]:
        print("\n  By Collection:")
        for collection, count in registry_results["by_collection"].items():
            print(f"    {collection:20s}: {count:5d}")

    # Qdrant stats
    print("\n📦 QDRANT VECTOR DATABASE")
    print(f"  Total vectors: {qdrant_results['total_vectors']:,}")

    if qdrant_results["collections"]:
        print("\n  Collections:")
        for coll, info in qdrant_results["collections"].items():
            print(
                f"    {coll:20s}: {info['vector_count']:6d} vectors, "
                f"{info['indexed_count']:6d} indexed ({info['status']})"
            )

    # Issues
    all_issues = registry_results["issues"] + qdrant_results["issues"]
    if all_issues:
        print("\n⚠️  ISSUES DETECTED:")
        for issue in all_issues:
            print(f"  - {issue}")
    else:
        print("\n✅ NO ISSUES DETECTED")

    print("=" * 70)


def main():
    parser = argparse.ArgumentParser(description="Verify ORION RAG ingestion state")
    parser.add_argument(
        "--registry-db",
        type=Path,
        default=Path("/mnt/nvme1/orion-data/documents/metadata/ingestion.db"),
        help="Path to ingestion registry database",
    )
    parser.add_argument(
        "--qdrant-url",
        type=str,
        default=os.getenv("QDRANT_URL", "http://127.0.0.1:6333"),
        help="Qdrant API URL",
    )

    args = parser.parse_args()

    # Check if registry exists
    if not args.registry_db.exists():
        print(f"⚠️  Registry database not found: {args.registry_db}")
        print("   This is expected if no documents have been processed yet.")
        registry_results = {
            "total_documents": 0,
            "by_status": {},
            "by_domain": {},
            "by_collection": {},
            "issues": [],
        }
    else:
        registry_results = check_registry_consistency(args.registry_db)

    qdrant_results = check_qdrant_collections(args.qdrant_url)

    print_report(registry_results, qdrant_results)

    # Exit code: 0 if no issues, 1 if issues found
    has_issues = bool(registry_results["issues"] or qdrant_results["issues"])
    sys.exit(1 if has_issues else 0)


if __name__ == "__main__":
    main()
