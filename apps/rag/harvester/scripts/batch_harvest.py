#!/usr/bin/env python3
"""
ORION Batch Harvester - Process multiple search terms overnight
Reads config/search_terms.csv and harvests documents from all configured providers

Features:
- Checkpoint/resume capability
- Progress tracking and reporting
- Error classification and summary
- Configurable providers and limits

Usage:
    python scripts/batch_harvest.py                    # Full batch
    python scripts/batch_harvest.py --resume          # Resume from checkpoint
    python scripts/batch_harvest.py --limit 10        # Process only 10 terms
    python scripts/batch_harvest.py --dry-run         # Test without downloading

Created: 2025-11-20
"""
import sys
import csv
import json
import logging
from pathlib import Path
from typing import List, Dict, Set
from dataclasses import dataclass, field
from collections import Counter
from datetime import datetime
import time

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))

from provider_factory import ProviderFactory
from downloader import DocumentDownloader

logger = logging.getLogger(__name__)


@dataclass
class HarvestStats:
    """Track harvesting statistics"""
    total_terms: int = 0
    processed_terms: int = 0
    skipped_terms: int = 0
    total_found: int = 0
    total_downloaded: int = 0
    total_skipped: int = 0
    total_failed: int = 0
    by_category: Dict[str, int] = field(default_factory=dict)
    by_provider: Dict[str, int] = field(default_factory=dict)
    start_time: float = field(default_factory=time.time)
    end_time: float = 0


@dataclass
class ErrorStats:
    """Track and classify errors"""
    errors_by_type: Counter = field(default_factory=Counter)
    errors_by_category: Counter = field(default_factory=Counter)
    sample_errors: Dict[str, List[str]] = field(default_factory=dict)


class BatchHarvester:
    """Batch harvester with checkpoint/resume capability"""

    def __init__(
        self,
        terms_file: Path,
        providers: List[str],
        max_docs_per_term: int,
        dry_run: bool = False
    ):
        self.terms_file = terms_file
        self.providers = providers
        self.max_docs_per_term = max_docs_per_term
        self.dry_run = dry_run

        # Setup paths
        self.harvester_dir = Path(__file__).parent.parent
        self.library_dir = self.harvester_dir / "data" / "library"
        self.metadata_path = self.harvester_dir / "data" / "library_metadata.json"

        # Initialize components
        self.factory = ProviderFactory()
        self.downloader = DocumentDownloader(self.library_dir, self.metadata_path)

        # Stats tracking
        self.stats = HarvestStats()
        self.error_stats = ErrorStats()
        self.processed_terms: Set[str] = set()
        self.failed_terms: Dict[str, str] = {}

    def save_checkpoint(self, checkpoint_path: Path):
        """Save progress to checkpoint file"""
        checkpoint_data = {
            'processed_terms': list(self.processed_terms),
            'failed_terms': self.failed_terms,
            'checkpoint_time': datetime.now().isoformat(),
            'stats': {
                'processed_terms': self.stats.processed_terms,
                'total_found': self.stats.total_found,
                'total_downloaded': self.stats.total_downloaded,
                'total_skipped': self.stats.total_skipped,
                'total_failed': self.stats.total_failed,
                'by_category': self.stats.by_category,
                'by_provider': self.stats.by_provider,
            }
        }

        checkpoint_path.parent.mkdir(parents=True, exist_ok=True)
        with open(checkpoint_path, 'w') as f:
            json.dump(checkpoint_data, f, indent=2)

        logger.info(f"💾 Checkpoint saved: {self.stats.processed_terms}/{self.stats.total_terms} terms")

    def load_checkpoint(self, checkpoint_path: Path) -> Set[str]:
        """Load previous progress"""
        if not checkpoint_path.exists():
            return set()

        try:
            with open(checkpoint_path, 'r') as f:
                data = json.load(f)

            processed = set(data.get('processed_terms', []))
            self.failed_terms = data.get('failed_terms', {})

            logger.info(f"📂 Loaded checkpoint: {len(processed)} terms already processed")
            logger.info(f"   Last checkpoint: {data.get('checkpoint_time')}")

            return processed
        except Exception as e:
            logger.warning(f"⚠️  Failed to load checkpoint: {e}")
            return set()

    def classify_error(self, error_message: str) -> str:
        """Classify error into categories"""
        error_lower = str(error_message).lower()

        if 'no results' in error_lower or 'not found' in error_lower:
            return 'no_results'
        elif 'timeout' in error_lower:
            return 'timeout'
        elif 'connection' in error_lower or 'network' in error_lower:
            return 'network_error'
        elif 'rate limit' in error_lower or '429' in error_lower:
            return 'rate_limit'
        elif 'api' in error_lower or 'auth' in error_lower:
            return 'api_error'
        elif 'download' in error_lower:
            return 'download_failed'
        else:
            return 'other'

    def record_error(self, term: str, category: str, error_msg: str):
        """Record error with classification"""
        error_type = self.classify_error(error_msg)

        self.error_stats.errors_by_type[error_type] += 1
        self.error_stats.errors_by_category[category] += 1

        # Keep first 3 examples of each error type
        if error_type not in self.error_stats.sample_errors:
            self.error_stats.sample_errors[error_type] = []
        if len(self.error_stats.sample_errors[error_type]) < 3:
            self.error_stats.sample_errors[error_type].append(f"{term} ({category})")

    def print_error_summary(self):
        """Print categorized error summary"""
        logger.info("=" * 70)
        logger.info("ERROR SUMMARY")
        logger.info("=" * 70)

        if self.error_stats.errors_by_type:
            logger.info("\nErrors by Type:")
            for error_type, count in self.error_stats.errors_by_type.most_common():
                pct = count / max(self.stats.processed_terms, 1) * 100
                logger.info(f"  {error_type:20s}: {count:4d} ({pct:.1f}%)")

                # Show examples
                if error_type in self.error_stats.sample_errors:
                    for example in self.error_stats.sample_errors[error_type][:3]:
                        logger.info(f"    - {example}")

        if self.error_stats.errors_by_category:
            logger.info("\nErrors by Category:")
            for category, count in self.error_stats.errors_by_category.most_common():
                logger.info(f"  {category:30s}: {count:4d}")

        logger.info("=" * 70)

    def read_search_terms(self) -> List[Dict[str, str]]:
        """Read search terms from CSV file"""
        terms = []

        with open(self.terms_file, 'r') as f:
            reader = csv.DictReader(f)
            for row in reader:
                terms.append({
                    'term': row['term'],
                    'category': row['category']
                })

        return terms

    def harvest_term(self, term_data: Dict[str, str], provider_names: List[str]) -> Dict:
        """Harvest documents for a single search term"""
        term = term_data['term']
        category = term_data['category']

        result = {
            'found': 0,
            'downloaded': 0,
            'skipped': 0,
            'failed': 0,
            'providers': {}
        }

        for provider_name in provider_names:
            try:
                provider = self.factory.create(provider_name)
                logger.info(f"  🔍 {provider_name}...")

                # Search
                documents = provider.search(term, max_results=self.max_docs_per_term)
                result['found'] += len(documents)
                result['providers'][provider_name] = len(documents)

                if self.dry_run:
                    # Just count in dry run
                    result['downloaded'] += len(documents)
                else:
                    # Actually download
                    download_stats = self.downloader.download_batch(
                        documents,
                        category=category,
                        max_downloads=self.max_docs_per_term
                    )

                    result['downloaded'] += download_stats['successful']
                    result['skipped'] += download_stats['skipped']
                    result['failed'] += download_stats['failed']

                    # Track by provider
                    if provider_name not in self.stats.by_provider:
                        self.stats.by_provider[provider_name] = 0
                    self.stats.by_provider[provider_name] += download_stats['successful']

            except Exception as e:
                error_msg = str(e)
                logger.error(f"  ✗ {provider_name}: {error_msg}")
                self.record_error(term, category, error_msg)
                result['failed'] += 1

        return result

    def run(self, checkpoint_path: Path = None, term_limit: int = None):
        """Execute batch harvesting"""
        # Setup checkpoint
        if checkpoint_path is None:
            checkpoint_path = Path.home() / ".orion_harvest_checkpoint.json"

        # Load previous progress
        self.processed_terms = self.load_checkpoint(checkpoint_path)

        logger.info("=" * 80)
        logger.info("ORION BATCH HARVESTER")
        logger.info("=" * 80)
        logger.info(f"Mode: {'DRY RUN' if self.dry_run else 'FULL HARVEST'}")
        logger.info(f"Providers: {', '.join(self.providers)}")
        logger.info(f"Max docs per term: {self.max_docs_per_term}")
        logger.info(f"Library: {self.library_dir}")
        logger.info("")

        # Read search terms
        logger.info("Loading search terms...")
        all_terms = self.read_search_terms()
        self.stats.total_terms = len(all_terms)

        # Apply limit if specified
        if term_limit:
            all_terms = all_terms[:term_limit]
            logger.info(f"Limited to first {term_limit} terms")

        logger.info(f"Total terms: {len(all_terms)}")
        logger.info("")

        # Resolve provider names
        provider_names = self.factory.resolve_provider_names(self.providers)
        logger.info(f"Active providers: {', '.join(provider_names)}")
        logger.info("")

        # Show library status
        registry_stats = self.downloader.get_registry_stats()
        logger.info(f"📚 Library Status:")
        logger.info(f"  Total downloads: {registry_stats['total_downloads']}")
        logger.info(f"  Total size: {registry_stats['total_size_mb']:.1f} MB")
        logger.info("")

        # Process each term
        logger.info("Processing search terms...")
        logger.info("")

        for idx, term_data in enumerate(all_terms, 1):
            term = term_data['term']
            category = term_data['category']

            # Skip if already processed (resume capability)
            term_key = f"{term}|{category}"
            if term_key in self.processed_terms:
                self.stats.skipped_terms += 1
                continue

            self.stats.processed_terms += 1

            logger.info(f"[{idx}/{len(all_terms)}] {term[:60]}")
            logger.info(f"  Category: {category}")

            try:
                # Harvest this term
                result = self.harvest_term(term_data, provider_names)

                self.stats.total_found += result['found']
                self.stats.total_downloaded += result['downloaded']
                self.stats.total_skipped += result['skipped']
                self.stats.total_failed += result['failed']

                # Track by category
                if category not in self.stats.by_category:
                    self.stats.by_category[category] = 0
                self.stats.by_category[category] += result['downloaded']

                # Log result
                if result['found'] > 0:
                    logger.info(f"  ✓ Found: {result['found']}, Downloaded: {result['downloaded']}, Skipped: {result['skipped']}")
                else:
                    logger.info(f"  ⏭️  No results found")

                self.processed_terms.add(term_key)

            except Exception as e:
                error_msg = str(e)
                logger.error(f"  ✗ Failed: {error_msg}")
                self.failed_terms[term_key] = error_msg
                self.record_error(term, category, error_msg)

            # Save checkpoint every 10 terms
            if self.stats.processed_terms % 10 == 0:
                self.save_checkpoint(checkpoint_path)

            # Progress report every 25 terms
            if self.stats.processed_terms % 25 == 0:
                elapsed = time.time() - self.stats.start_time
                rate = self.stats.processed_terms / elapsed * 60  # terms per minute
                remaining = self.stats.total_terms - self.stats.processed_terms
                eta_minutes = remaining / (rate / 60) if rate > 0 else 0

                logger.info("")
                logger.info("=" * 70)
                logger.info(f"📊 PROGRESS REPORT - {datetime.now().strftime('%H:%M:%S')}")
                logger.info("=" * 70)
                logger.info(f"Processed:     {self.stats.processed_terms:5d} / {self.stats.total_terms:5d} ({self.stats.processed_terms/self.stats.total_terms*100:.1f}%)")
                logger.info(f"Found:         {self.stats.total_found:5d}")
                logger.info(f"Downloaded:    {self.stats.total_downloaded:5d}")
                logger.info(f"Skipped:       {self.stats.total_skipped:5d}")
                logger.info(f"Failed:        {self.stats.total_failed:5d}")
                logger.info(f"Rate:          {rate:.1f} terms/min")
                logger.info(f"Elapsed:       {elapsed/60:.1f} minutes")
                logger.info(f"ETA:           {eta_minutes:.1f} minutes (~{eta_minutes/60:.1f} hours)")
                logger.info("=" * 70)
                logger.info("")

        # Final checkpoint
        self.save_checkpoint(checkpoint_path)

        # Final stats
        self.stats.end_time = time.time()
        duration = self.stats.end_time - self.stats.start_time

        # Print error summary if errors occurred
        if self.stats.total_failed > 0:
            logger.info("")
            self.print_error_summary()
            logger.info("")

        logger.info("=" * 80)
        logger.info("BATCH HARVEST COMPLETE")
        logger.info("=" * 80)
        logger.info(f"Duration: {duration/60:.1f} minutes")
        logger.info(f"Terms processed: {self.stats.processed_terms} / {self.stats.total_terms}")
        logger.info(f"Skipped: {self.stats.skipped_terms} (already processed)")
        logger.info(f"Documents found: {self.stats.total_found}")
        logger.info(f"Documents downloaded: {self.stats.total_downloaded}")
        logger.info(f"Documents skipped: {self.stats.total_skipped} (already have)")
        logger.info(f"Failed: {self.stats.total_failed}")
        logger.info("")

        if self.stats.by_category:
            logger.info("By Category:")
            for category, count in sorted(self.stats.by_category.items(), key=lambda x: -x[1]):
                logger.info(f"  {category:35s}: {count:4d} documents")
            logger.info("")

        if self.stats.by_provider:
            logger.info("By Provider:")
            for provider, count in sorted(self.stats.by_provider.items(), key=lambda x: -x[1]):
                logger.info(f"  {provider:20s}: {count:4d} documents")
            logger.info("")

        if self.stats.total_downloaded > 0:
            rate = self.stats.total_downloaded / (duration / 60)
            logger.info(f"Download rate: {rate:.1f} docs/minute")

        # Show library status
        registry_stats = self.downloader.get_registry_stats()
        logger.info("")
        logger.info(f"📚 Final Library Status:")
        logger.info(f"  Total downloads: {registry_stats['total_downloads']}")
        logger.info(f"  Total size: {registry_stats['total_size_mb']:.1f} MB")

        return self.stats


def main():
    import argparse

    parser = argparse.ArgumentParser(
        description='ORION Batch Harvester - Process multiple search terms'
    )
    parser.add_argument(
        '--terms-file',
        type=Path,
        default=Path(__file__).parent.parent / 'config' / 'search_terms.csv',
        help='Path to search terms CSV file'
    )
    parser.add_argument(
        '--providers',
        type=str,
        default='academic',
        help='Comma-separated provider list or "all"/"academic"'
    )
    parser.add_argument(
        '--max-docs',
        type=int,
        default=50,
        help='Maximum documents per search term'
    )
    parser.add_argument(
        '--limit',
        type=int,
        default=None,
        help='Limit number of terms to process (for testing)'
    )
    parser.add_argument(
        '--checkpoint',
        type=Path,
        default=None,
        help='Path to checkpoint file (default: ~/.orion_harvest_checkpoint.json)'
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Test without actually downloading'
    )
    parser.add_argument(
        '--resume',
        action='store_true',
        help='Resume from last checkpoint'
    )

    args = parser.parse_args()

    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )

    # Validate terms file
    if not args.terms_file.exists():
        logger.error(f"Terms file not found: {args.terms_file}")
        sys.exit(1)

    # Parse providers
    providers = args.providers.split(',')

    # Initialize harvester
    harvester = BatchHarvester(
        terms_file=args.terms_file,
        providers=providers,
        max_docs_per_term=args.max_docs,
        dry_run=args.dry_run
    )

    # Run batch harvest
    try:
        stats = harvester.run(
            checkpoint_path=args.checkpoint,
            term_limit=args.limit
        )

        # Exit code based on results
        if stats.total_failed > stats.total_downloaded / 2:
            # More than 50% failure rate
            sys.exit(1)
        else:
            sys.exit(0)

    except KeyboardInterrupt:
        logger.warning("\n\nHarvesting interrupted by user")
        sys.exit(130)
    except Exception as e:
        logger.error(f"\n\nFATAL ERROR: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
