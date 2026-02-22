#!/usr/bin/env python3
"""
ORION Complete Ingestion Orchestrator
Integrates harvesting, quality gates, domain routing, and AnythingLLM API

This orchestrator:
1. Scans documents from /mnt/nvme1/orion-data/documents/raw/
2. Applies domain-specific quality gates
3. Routes to appropriate AnythingLLM workspaces
4. Tracks progress in registry
5. Monitors and reports status

Usage:
    python src/orchestrator.py --dry-run  # Test without uploading
    python src/orchestrator.py --full     # Process all documents

Created: 2025-11-09 (Phase 8 - Full Pipeline Integration)
"""

import os
import sys
import logging
import json
from pathlib import Path
from typing import List, Dict, Tuple, Set, Optional
from dataclasses import dataclass, field
from collections import Counter
import time
from datetime import datetime
from tqdm import tqdm

# Import ORION components
from anythingllm_client import AnythingLLMClient
from registry import IngestionRegistry
from domains import get_domain_config, infer_document_type
from ingest import PDFProcessor, HTMLProcessor

# Set up logging
logger = logging.getLogger(__name__)


@dataclass
class OrchestrationStats:
    """Statistics for full orchestration run"""

    total_files: int = 0
    processed: int = 0
    uploaded: int = 0
    failed: int = 0
    skipped: int = 0
    quality_rejected: int = 0
    duplicates: int = 0
    by_domain: Dict[str, int] = field(default_factory=dict)
    start_time: float = field(default_factory=time.time)
    end_time: Optional[float] = None

    def __post_init__(self):
        # dataclass default_factory already initializes maps and start_time but keep guard
        if self.by_domain is None:
            self.by_domain = {}
        if self.start_time is None:
            self.start_time = time.time()


@dataclass
class ErrorStats:
    """Track and classify errors for summary reporting"""

    errors_by_type: Counter = field(default_factory=Counter)
    errors_by_domain: Counter = field(default_factory=Counter)
    sample_errors: Dict[str, List[str]] = field(default_factory=dict)


class ORIONOrchestrator:
    """Master orchestrator for complete document ingestion pipeline"""

    # Domain to workspace mapping
    WORKSPACE_MAPPING = {
        "github": "code-examples",
        "manuals": "technical-docs",
        "blogs": "technical-docs",
        "academic": "research-papers",
        "exports": "technical-docs",
    }

    def __init__(
        self,
        anythingllm_client: AnythingLLMClient,
        registry: IngestionRegistry,
        dry_run: bool = False,
    ) -> None:
        """
        Initialize orchestrator

        Args:
            anythingllm_client: Configured AnythingLLM API client
            registry: Document registry for tracking
            dry_run: If True, don't actually upload, just report what would happen
        """
        self.client = anythingllm_client
        self.registry = registry
        self.dry_run = dry_run
        self.stats = OrchestrationStats()
        self.error_stats = ErrorStats()
        self.processed_files: Set[str] = set()
        self.failed_files: Dict[str, str] = {}

        # Initialize processors
        self.pdf_processor = PDFProcessor(registry=registry)
        self.html_processor = HTMLProcessor(registry=registry)

    def save_checkpoint(self, checkpoint_path: Path):
        """Save current progress to disk for resume capability"""
        checkpoint_data = {
            "processed_files": list(self.processed_files),
            "failed_files": self.failed_files,
            "checkpoint_time": datetime.now().isoformat(),
            "total_files": self.stats.total_files,
            "completed_count": self.stats.processed,
            "stats": {
                "uploaded": self.stats.uploaded,
                "rejected": self.stats.quality_rejected,
                "failed": self.stats.failed,
                "skipped": self.stats.skipped,
                "by_domain": self.stats.by_domain,
            },
        }

        checkpoint_path.parent.mkdir(parents=True, exist_ok=True)
        with open(checkpoint_path, "w") as f:
            json.dump(checkpoint_data, f, indent=2)

        logger.info(
            f"💾 Checkpoint saved: {self.stats.processed}/{self.stats.total_files} files"
        )

    def load_checkpoint(self, checkpoint_path: Path) -> Set[str]:
        """Load previous progress to resume processing"""
        if not checkpoint_path.exists():
            return set()

        try:
            with open(checkpoint_path, "r") as f:
                data = json.load(f)

            processed = set(data.get("processed_files", []))
            self.failed_files = data.get("failed_files", {})

            logger.info(
                f"📂 Loaded checkpoint: {len(processed)} files already processed"
            )
            logger.info(f"   Last checkpoint: {data.get('checkpoint_time')}")

            return processed
        except Exception as e:
            logger.warning(f"⚠️  Failed to load checkpoint: {e}")
            return set()

    def classify_error(self, error_message: str) -> str:
        """Classify error into categories for summary reporting"""
        error_lower = error_message.lower()

        if "duplicate" in error_lower:
            return "duplicate"
        elif "timeout" in error_lower:
            return "timeout"
        elif "connection" in error_lower or "refused" in error_lower:
            return "network_error"
        elif "low_density" in error_lower or "density" in error_lower:
            return "quality_low_density"
        elif "no_text" in error_lower or "insufficient_content" in error_lower:
            return "quality_no_text"
        elif "parse_error" in error_lower:
            return "parse_error"
        elif "upload_failed" in error_lower:
            return "upload_failed"
        else:
            return "other"

    def record_error(self, file_path: Path, error_msg: str, domain: str):
        """Record error with classification"""
        error_type = self.classify_error(error_msg)

        self.error_stats.errors_by_type[error_type] += 1
        self.error_stats.errors_by_domain[domain] += 1

        # Keep first 3 examples of each error type
        if error_type not in self.error_stats.sample_errors:
            self.error_stats.sample_errors[error_type] = []
        if len(self.error_stats.sample_errors[error_type]) < 3:
            self.error_stats.sample_errors[error_type].append(file_path.name)

    def print_error_summary(self):
        """Print categorized error summary"""
        logger.info("=" * 70)
        logger.info("ERROR SUMMARY")
        logger.info("=" * 70)

        if self.error_stats.errors_by_type:
            logger.info("\nErrors by Type:")
            for error_type, count in self.error_stats.errors_by_type.most_common():
                pct = count / max(self.stats.processed, 1) * 100
                logger.info(f"  {error_type:20s}: {count:4d} ({pct:.1f}%)")

                # Show examples
                if error_type in self.error_stats.sample_errors:
                    for example in self.error_stats.sample_errors[error_type][:3]:
                        logger.info(f"    - {example}")

        if self.error_stats.errors_by_domain:
            logger.info("\nErrors by Domain:")
            for domain, count in self.error_stats.errors_by_domain.most_common():
                logger.info(f"  {domain:15s}: {count:4d}")

        logger.info("=" * 70)

    def scan_documents(self, base_path: Path) -> Dict[str, List[Path]]:
        """
        Scan document directory and organize by domain

        Args:
            base_path: Root directory containing documents

        Returns:
            Dict mapping domain -> list of file paths
        """
        documents_by_domain = {}

        # Scan all supported file types
        for pattern in ["**/*.pdf", "**/*.html", "**/*.htm", "**/*.md"]:
            for file_path in base_path.glob(pattern):
                # Infer domain from file path
                domain = infer_document_type(file_path)

                if domain not in documents_by_domain:
                    documents_by_domain[domain] = []

                documents_by_domain[domain].append(file_path)

        return documents_by_domain

    def check_quality(self, file_path: Path, domain: str) -> Tuple[bool, str]:
        """
        Apply domain-specific quality gates

        Args:
            file_path: Path to document
            domain: Document domain type

        Returns:
            (passed, rejection_reason or None)
        """
        # Check if already in registry
        if self.registry.is_processed(file_path):
            return False, "duplicate"

        # Get domain config
        config = get_domain_config(domain)
        if config is None:
            return False, "unknown_domain"

        # Apply quality checks based on file type
        try:
            if file_path.suffix.lower() == ".pdf":
                text, metadata = self.pdf_processor.extract_text(file_path)
                metrics = self.pdf_processor.calculate_quality(
                    text, metadata.get("page_count", 1)
                )

                # Check density threshold
                if metrics.text_density < config.quality_gates.min_text_density:
                    return False, f"low_density_{metrics.text_density:.2f}"

                # Check has text
                if not metrics.has_text:
                    return False, "no_text"

            elif file_path.suffix.lower() in [".html", ".htm"]:
                text, metadata = self.html_processor.extract_text(file_path)

                # Basic HTML quality checks
                if len(text.strip()) < 500:  # Minimum content length
                    return False, "insufficient_content"

            elif file_path.suffix.lower() == ".md":
                # Markdown files: basic quality validation
                with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                    content = f.read()

                # Minimum content length check
                if len(content.strip()) < config.quality_gates.min_length:
                    return False, f"insufficient_content_{len(content)}"

                # Check it's not mostly whitespace/special chars
                text_chars = sum(c.isalnum() or c.isspace() for c in content)
                if text_chars / max(len(content), 1) < 0.5:
                    return False, "low_text_ratio"

            return True, "passed"

        except Exception as e:
            return False, f"parse_error_{str(e)[:50]}"

    def get_workspace_for_domain(self, domain: str) -> str:
        """Map domain to workspace slug"""
        return self.WORKSPACE_MAPPING.get(domain, "technical-docs")

    def process_file(
        self, file_path: Path, domain: str, workspace_slug: str
    ) -> Tuple[bool, str]:
        """
        Process single file: quality check + upload

        Args:
            file_path: Path to document
            domain: Document domain
            workspace_slug: Target workspace

        Returns:
            (success, message)
        """
        # Quality gate
        passed, reason = self.check_quality(file_path, domain)
        if not passed:
            self.stats.quality_rejected += 1
            if reason == "duplicate":
                self.stats.duplicates += 1

            # Record error for summary
            self.record_error(file_path, reason, domain)
            return False, f"quality_rejected: {reason}"

        # Dry run mode
        if self.dry_run:
            return True, "dry_run_success"

        # Upload to AnythingLLM
        result = self.client.upload_document(
            file_path=file_path, workspace_slug=workspace_slug
        )

        if result.success:
            # Register in database
            self.registry.register_document(
                file_path=file_path,
                content_hash=self.registry.compute_file_hash(file_path),
                document_type=domain,
                collection_name=workspace_slug,
                title=file_path.stem,
                chunk_count=result.chunks_created,
                status="ingested",
                error_message=None,
                metadata={"workspace": workspace_slug},
            )

            self.stats.uploaded += 1
            return True, f"uploaded: {result.chunks_created} chunks"
        else:
            self.stats.failed += 1
            return False, f"upload_failed: {result.error}"

    def run(
        self, document_root: Path, checkpoint_path: Optional[Path] = None
    ) -> OrchestrationStats:
        """
        Execute complete ingestion orchestration

        Args:
            document_root: Root directory containing documents
            checkpoint_path: Path to checkpoint file for resume capability (optional)

        Returns:
            OrchestrationStats with results
        """
        # Setup checkpoint
        if checkpoint_path is None:
            checkpoint_path = Path.home() / ".orion_checkpoint.json"

        # Load previous progress
        self.processed_files = self.load_checkpoint(checkpoint_path)
        logger.info("=" * 80)
        logger.info("ORION COMPLETE INGESTION ORCHESTRATION")
        logger.info("=" * 80)
        logger.info(f"Mode: {'DRY RUN' if self.dry_run else 'FULL INGESTION'}")
        logger.info(f"Document root: {document_root}")
        logger.info(f"Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        logger.info("")

        # Scan documents
        logger.info("Scanning documents...")
        documents_by_domain = self.scan_documents(document_root)

        self.stats.total_files = sum(
            len(files) for files in documents_by_domain.values()
        )

        logger.info(
            f"Found {self.stats.total_files} documents across {len(documents_by_domain)} domains:"
        )
        for domain, files in sorted(documents_by_domain.items()):
            logger.info(f"  {domain:15s}: {len(files):5d} files")
        logger.info("")

        # Verify workspaces exist
        logger.info("Verifying workspaces...")
        workspaces = {ws["slug"]: ws for ws in self.client.list_workspaces()}
        required_workspaces = set(self.WORKSPACE_MAPPING.values())

        for ws_slug in required_workspaces:
            if ws_slug in workspaces:
                logger.info(f"  ✓ {ws_slug}")
            else:
                logger.warning(f"  ✗ {ws_slug} - MISSING!")
                if not self.dry_run:
                    logger.info(f"    Creating workspace: {ws_slug}")
                    self.client.create_workspace(
                        name=ws_slug.replace("-", " ").title(), collection_name=ws_slug
                    )
        logger.info("")

        # Process documents by domain
        logger.info("Processing documents...")
        logger.info("")

        for domain, files in sorted(documents_by_domain.items()):
            workspace_slug = self.get_workspace_for_domain(domain)

            logger.info(f"Domain: {domain} → Workspace: {workspace_slug}")
            logger.info(f"Files: {len(files)}")

            success_count = 0
            failed_count = 0

            # Process with progress bar
            with tqdm(files, desc=f"  {domain}", unit="file") as pbar:
                for file_path in pbar:
                    # Skip if already processed (resume capability)
                    if str(file_path) in self.processed_files:
                        self.stats.skipped += 1
                        continue

                    self.stats.processed += 1

                    success, message = self.process_file(
                        file_path, domain, workspace_slug
                    )

                    if success:
                        success_count += 1
                        self.processed_files.add(str(file_path))
                        # Log successful uploads with ✓ marker
                        logger.info(
                            f"✓ [{self.stats.uploaded:4d}] {file_path.name[:60]} → {workspace_slug}"
                        )
                    else:
                        failed_count += 1
                        self.failed_files[str(file_path)] = message
                        # Log failures with ✗ marker
                        logger.error(f"✗ [FAILED] {file_path.name}: {message}")

                    # Update progress bar
                    pbar.set_postfix({"success": success_count, "failed": failed_count})

                    # Save checkpoint every 50 files
                    if self.stats.processed % 50 == 0:
                        self.save_checkpoint(checkpoint_path)

                    # Structured progress report every 100 files
                    if self.stats.processed % 100 == 0:
                        elapsed = time.time() - self.stats.start_time
                        rate = self.stats.processed / elapsed * 60  # docs per minute
                        remaining = self.stats.total_files - self.stats.processed
                        eta_minutes = remaining / (rate / 60) if rate > 0 else 0

                        logger.info("=" * 70)
                        logger.info(
                            f"📊 PROGRESS REPORT - {datetime.now().strftime('%H:%M:%S')}"
                        )
                        logger.info("=" * 70)
                        logger.info(
                            f"Processed:     {self.stats.processed:5d} / {self.stats.total_files:5d} ({self.stats.processed/self.stats.total_files*100:.1f}%)"
                        )
                        logger.info(f"Uploaded:      {self.stats.uploaded:5d}")
                        logger.info(
                            f"Rejected:      {self.stats.quality_rejected:5d} ({self.stats.quality_rejected/max(self.stats.processed,1)*100:.1f}%)"
                        )
                        logger.info(f"Failed:        {self.stats.failed:5d}")
                        logger.info(f"Skipped:       {self.stats.skipped:5d}")
                        logger.info(f"Rate:          {rate:.1f} docs/min")
                        logger.info(f"Elapsed:       {elapsed/60:.1f} minutes")
                        logger.info(
                            f"ETA:           {eta_minutes:.1f} minutes (~{eta_minutes/60:.1f} hours)"
                        )
                        logger.info("")
                        logger.info(
                            f"Current batch: {domain} ({success_count}/{len(files)})"
                        )
                        logger.info("=" * 70)

            self.stats.by_domain[domain] = success_count
            logger.info(f"  ✓ {success_count} uploaded, {failed_count} rejected")
            logger.info("")

        # Final checkpoint save
        self.save_checkpoint(checkpoint_path)

        # Final stats
        self.stats.end_time = time.time()
        duration = self.stats.end_time - self.stats.start_time

        # Print error summary
        if self.stats.quality_rejected > 0 or self.stats.failed > 0:
            logger.info("")
            self.print_error_summary()
            logger.info("")

        logger.info("=" * 80)
        logger.info("ORCHESTRATION COMPLETE")
        logger.info("=" * 80)
        logger.info(f"Duration: {duration/60:.1f} minutes")
        logger.info(f"Total files scanned: {self.stats.total_files}")
        logger.info(f"Processed: {self.stats.processed}")
        logger.info(f"Uploaded: {self.stats.uploaded}")
        logger.info(f"Quality rejected: {self.stats.quality_rejected}")
        logger.info(f"  - Duplicates: {self.stats.duplicates}")
        logger.info(f"Failed uploads: {self.stats.failed}")
        logger.info("")
        logger.info("By domain:")
        for domain, count in sorted(self.stats.by_domain.items()):
            logger.info(f"  {domain:15s}: {count:5d} documents")
        logger.info("")

        if self.stats.uploaded > 0:
            rate = self.stats.uploaded / (duration / 60)
            logger.info(f"Processing rate: {rate:.1f} docs/minute")

        return self.stats


def main():
    """Main entry point"""
    import argparse

    parser = argparse.ArgumentParser(
        description="ORION Complete Ingestion Orchestrator"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Test without actually uploading documents",
    )
    parser.add_argument(
        "--document-root",
        type=Path,
        default=Path(
            os.getenv("ORION_DOCUMENT_ROOT", "/mnt/nvme1/orion-data/documents/raw")
        ),
        help="Root directory containing documents",
    )
    parser.add_argument(
        "--api-key",
        type=str,
        default=os.getenv("ANYTHINGLLM_API_KEY"),
        help="AnythingLLM API key",
    )
    parser.add_argument(
        "--base-url",
        type=str,
        default=os.getenv("ANYTHINGLLM_URL", "http://192.168.5.10:3001"),
        help="AnythingLLM base URL",
    )
    parser.add_argument(
        "--checkpoint",
        type=Path,
        default=None,
        help="Path to checkpoint file for resume capability (default: ~/.orion_checkpoint.json)",
    )

    args = parser.parse_args()

    # Configure logging
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    # Validate
    if not args.api_key:
        logger.error("ERROR: ANYTHINGLLM_API_KEY environment variable not set")
        logger.error("Export it or use --api-key flag")
        sys.exit(1)

    if not args.document_root.exists():
        logger.error(f"ERROR: Document root not found: {args.document_root}")
        sys.exit(1)

    # Initialize components
    logger.info("Initializing ORION orchestrator...")

    client = AnythingLLMClient(base_url=args.base_url, api_key=args.api_key)

    if not client.test_connection():
        logger.error("ERROR: Cannot connect to AnythingLLM API")
        sys.exit(1)

    logger.info("✓ Connected to AnythingLLM")

    registry = IngestionRegistry()
    logger.info("✓ Registry initialized")

    orchestrator = ORIONOrchestrator(
        anythingllm_client=client, registry=registry, dry_run=args.dry_run
    )
    logger.info("")

    # Run orchestration
    try:
        stats = orchestrator.run(args.document_root, checkpoint_path=args.checkpoint)

        # Exit code based on results
        if stats.failed > 0:
            sys.exit(1)
        else:
            sys.exit(0)

    except KeyboardInterrupt:
        logger.warning("\n\nOrchestration interrupted by user")
        sys.exit(130)
    except Exception as e:
        logger.error(f"\n\nFATAL ERROR: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
