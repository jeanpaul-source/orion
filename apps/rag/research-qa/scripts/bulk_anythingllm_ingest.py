#!/usr/bin/env python3
"""Bulk AnythingLLM ingestion helper.

Orchestrates uploading large batches of documents from the homelab document
archive into the configured AnythingLLM workspaces. Designed to be executed on
the host where `/mnt/nvme1/orion-data` is mounted, but it can run anywhere with
network access to the AnythingLLM API and local access to the source files.

Example usage (dry run + actual import):

    python scripts/bulk_anythingllm_ingest.py --dry-run
    python scripts/bulk_anythingllm_ingest.py --workspace technical-docs

"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Dict, Iterable, List, Sequence

try:
    from src.anythingllm_client import AnythingLLMClient, UploadResult
except ModuleNotFoundError:  # pragma: no cover - fallback for direct execution
    PROJECT_ROOT = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(PROJECT_ROOT))
    from src.anythingllm_client import AnythingLLMClient, UploadResult

DEFAULT_SOURCE_ROOT = Path("/mnt/nvme1/orion-data/documents/raw")
DEFAULT_BASE_URL = os.getenv("ANYTHINGLLM_URL", "http://192.168.5.10:3001")
DEFAULT_API_KEY = os.getenv("ANYTHINGLLM_API_KEY")
DEFAULT_MANIFEST = Path("~/.orion_anythingllm_manifest.json").expanduser()

# Workspace-to-category mapping that mirrors the AnythingLLM workspaces that
# were created during setup.
WORKSPACE_CATEGORY_MAP: Dict[str, Sequence[str]] = {
    "technical-docs": [
        "homelab-infrastructure",
        "homelab-networking-security",
        "container-platforms",
        "virtualization",
        "observability-and-alerting",
        "workflow-automation-n8n",
        "databases",
        "manuals",
        "vendor_pdf",
    ],
    "research-papers": [
        "academic",
        "ai-agents-and-multi-agent-systems",
        "llm-serving-and-inference",
        "rag-and-knowledge-retrieval",
        "vector-databases",
        "self-healing-and-remediation",
    ],
    "code-examples": [
        "github",
        "readthedocs",
        "gpu-and-cuda",
        "gpu-passthrough-and-vgpu",
        "exports",
        "blogs",
    ],
}


def load_manifest(path: Path) -> Dict[str, List[str]]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text())
    except json.JSONDecodeError:
        print(f"[warn] Manifest {path} is corrupt; starting fresh", file=sys.stderr)
        return {}


def save_manifest(path: Path, data: Dict[str, List[str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True))


def iter_category_files(source_root: Path, categories: Iterable[str]) -> List[Path]:
    files: List[Path] = []
    for category in categories:
        category_path = source_root / category
        if not category_path.exists():
            print(f"[warn] Missing category directory: {category_path}")
            continue
        for path in sorted(category_path.iterdir()):
            if path.is_file():
                files.append(path)
    return files


def summarize_plan(source_root: Path, mapping: Dict[str, Sequence[str]]) -> None:
    print("Planned ingestion summary:\n")
    total = 0
    for workspace, categories in mapping.items():
        files = iter_category_files(source_root, categories)
        total += len(files)
        print(f"• {workspace}: {len(files):5d} files from {len(categories)} categories")
        for category in categories:
            category_path = source_root / category
            count = (
                sum(1 for _ in category_path.glob("*")) if category_path.exists() else 0
            )
            print(f"    - {category:35s} {count:5d} files")
        print()
    print(f"Grand total: {total} files")


def upload_files(
    client: AnythingLLMClient,
    workspace: str,
    files: Sequence[Path],
    manifest: Dict[str, List[str]],
    manifest_path: Path,
    limit: int | None,
) -> None:
    processed = set(manifest.get(workspace, []))
    pending_files = [fp for fp in files if fp.name not in processed]
    if not pending_files:
        print(f"[{workspace}] Nothing to do (all files already recorded in manifest)")
        return

    target_total = len(pending_files)
    if limit is not None:
        target_total = min(target_total, limit)

    print(
        f"[{workspace}] Starting upload batch: {target_total} files (limit={limit or '∞'}, "
        f"{len(files)} total in categories)"
    )

    successes = failures = 0

    for idx, file_path in enumerate(pending_files, 1):
        if limit is not None and successes >= limit:
            break

        progress_position = min(idx, target_total)
        print(
            f"[{workspace}] [{progress_position}/{target_total}] "
            f"uploading {file_path.name}...",
            flush=True,
        )

        result: UploadResult = client.upload_document(file_path, workspace)
        status = "✓" if result.success else "✗"
        details = (
            f"{result.chunks_created} chunks"
            if result.success
            else (result.error or "unknown error")
        )

        if result.success:
            successes += 1
            processed.add(file_path.name)
            manifest.setdefault(workspace, []).append(file_path.name)
            save_manifest(manifest_path, manifest)
        else:
            failures += 1

        completed = min(successes + failures, target_total)
        print(
            f"[{workspace}] {status} {file_path.name} :: {details}"
            f" (completed {completed}/{target_total})"
        )

    print(
        f"[{workspace}] Completed: {successes} uploaded, {failures} failed, "
        f"{len(files)} queued"
    )


def filter_mapping(
    mapping: Dict[str, Sequence[str]],
    workspaces: Sequence[str] | None,
    categories: Sequence[str] | None,
) -> Dict[str, Sequence[str]]:
    selected = {}
    for workspace, cats in mapping.items():
        if workspaces and workspace not in workspaces:
            continue
        if categories:
            filtered = [cat for cat in cats if cat in categories]
            if not filtered:
                continue
            selected[workspace] = filtered
        else:
            selected[workspace] = list(cats)
    return selected


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Bulk upload documents into AnythingLLM workspaces"
    )
    parser.add_argument(
        "--base-url", default=DEFAULT_BASE_URL, help="AnythingLLM base URL"
    )
    parser.add_argument(
        "--api-key", default=DEFAULT_API_KEY, help="AnythingLLM API key"
    )
    parser.add_argument(
        "--source-root",
        type=Path,
        default=DEFAULT_SOURCE_ROOT,
        help="Root directory containing category subfolders",
    )
    parser.add_argument(
        "--workspace",
        action="append",
        help="Limit ingestion to one or more workspace slugs",
    )
    parser.add_argument(
        "--category",
        action="append",
        help="Limit ingestion to one or more category folders (names relative to source root)",
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="Show plan but do not upload"
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Maximum successful uploads per workspace (useful for smoke tests)",
    )
    parser.add_argument(
        "--upload-timeout",
        type=int,
        default=120,
        help="Timeout (seconds) for the initial file upload step",
    )
    parser.add_argument(
        "--embed-timeout",
        type=int,
        default=180,
        help="Timeout (seconds) for embedding generation per document",
    )
    parser.add_argument(
        "--embed-retries",
        type=int,
        default=5,
        help="Number of times to retry embedding requests when AnythingLLM is busy",
    )
    parser.add_argument(
        "--embed-retry-delay",
        type=float,
        default=5.0,
        help="Base delay (seconds) between embedding retries (multiplied by attempt)",
    )
    parser.add_argument(
        "--manifest",
        type=Path,
        default=DEFAULT_MANIFEST,
        help="Path to resume manifest (tracks uploaded filenames)",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    mapping = filter_mapping(WORKSPACE_CATEGORY_MAP, args.workspace, args.category)

    if not mapping:
        print("No workspaces/categories selected after filtering.")
        return 1

    if args.dry_run:
        summarize_plan(args.source_root, mapping)
        return 0

    if not args.api_key:
        print("ANYTHINGLLM_API_KEY is required (set env var or pass --api-key)")
        return 1

    manifest = load_manifest(args.manifest)
    client = AnythingLLMClient(
        base_url=args.base_url,
        api_key=args.api_key,
        upload_timeout=args.upload_timeout,
        embed_timeout=args.embed_timeout,
        embed_retries=args.embed_retries,
        embed_retry_backoff=args.embed_retry_delay,
    )

    for workspace, categories in mapping.items():
        files = iter_category_files(args.source_root, categories)
        if not files:
            print(
                f"[{workspace}] No files found for categories: {', '.join(categories)}"
            )
            continue
        upload_files(client, workspace, files, manifest, args.manifest, args.limit)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
