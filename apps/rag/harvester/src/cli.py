"""ORION Harvester CLI - Main entry point."""

import sys
import logging
from pathlib import Path
from typing import Optional

import typer
from typing_extensions import Annotated

# Ensure src/ is in path
sys.path.insert(0, str(Path(__file__).parent.parent))

# Load .env file before importing any modules that use environment variables
try:
    from dotenv import load_dotenv

    env_path = Path(__file__).parent.parent / ".env"
    if env_path.exists():
        load_dotenv(env_path)
        logging.debug(f"Loaded environment from {env_path}")
except ImportError:
    # python-dotenv not installed, will use system environment variables
    pass

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)

app = typer.Typer(
    name="orion",
    help="ORION Harvester: Academic paper collection system",
    add_completion=False,
)


@app.command()
def version():
    """Show ORION version."""
    from src import __version__

    typer.echo(f"ORION Harvester v{__version__}")


@app.command()
def harvest(
    term: Annotated[
        Optional[str],
        typer.Option("--term", "-t", help="Single search term to harvest"),
    ] = None,
    category: Annotated[
        Optional[str],
        typer.Option("--category", "-c", help="Category for the term"),
    ] = None,
    providers: Annotated[
        Optional[str],
        typer.Option("--providers", "-p", help="Comma-separated provider list or 'all'/'academic'"),
    ] = "academic",
    max_docs: Annotated[
        Optional[int],
        typer.Option("--max-docs", help="Maximum documents per term"),
    ] = 50,
    dry_run: Annotated[
        bool,
        typer.Option("--dry-run", help="Show what would be downloaded without downloading"),
    ] = False,
):
    """
    Download research papers from multiple sources.

    Examples:
      orion harvest --term "vector databases"
      orion harvest --term "kubernetes" --providers semantic_scholar,arxiv
      orion harvest --dry-run --providers all
    """
    from src.provider_factory import ProviderFactory
    from src.downloader import DocumentDownloader

    typer.echo("🌾 ORION Harvester v2.0")
    typer.echo("=" * 60)

    if not term:
        typer.echo("❌ ERROR: --term is required", err=True)
        raise typer.Exit(code=1)

    # Parse providers
    factory = ProviderFactory()
    provider_names = factory.resolve_provider_names(
        providers.split(",") if providers else ["academic"]
    )

    # Setup paths
    harvester_dir = Path(__file__).parent.parent
    library_dir = harvester_dir / "data" / "library"
    metadata_path = harvester_dir / "data" / "library_metadata.json"

    typer.echo(f"\n📋 Configuration:")
    typer.echo(f"  Term: {term}")
    typer.echo(f"  Category: {category or 'uncategorized'}")
    typer.echo(f"  Providers: {', '.join(provider_names)}")
    typer.echo(f"  Max docs: {max_docs}")
    typer.echo(f"  Dry run: {dry_run}")
    typer.echo(f"  Library: {library_dir}")

    # Initialize downloader
    downloader = DocumentDownloader(library_dir, metadata_path)

    # Show registry stats
    stats = downloader.get_registry_stats()
    typer.echo(f"\n📚 Library Status:")
    typer.echo(f"  Total downloads: {stats['total_downloads']}")
    typer.echo(f"  Total size: {stats['total_size_mb']:.1f} MB")

    if dry_run:
        typer.echo("\n⚠️  DRY RUN - No files will be downloaded")

    # Create providers and search/download
    total_found = 0
    total_downloaded = 0
    total_skipped = 0
    total_failed = 0

    for provider_name in provider_names:
        try:
            provider = factory.create(provider_name)
            typer.echo(f"\n🔍 Searching {provider_name}...")

            documents = provider.search(term, max_results=max_docs)
            typer.echo(f"  Found {len(documents)} results")
            total_found += len(documents)

            if dry_run:
                # Just display in dry run mode
                for i, doc in enumerate(documents[:5], 1):
                    typer.echo(f"  {i}. {doc.title}")
                    typer.echo(f"     URL: {doc.url}")
                if len(documents) > 5:
                    typer.echo(f"  ... and {len(documents) - 5} more results")
            else:
                # Actually download
                typer.echo(f"  📥 Downloading...")
                download_stats = downloader.download_batch(
                    documents, category=category or "uncategorized", max_downloads=max_docs
                )

                total_downloaded += download_stats["successful"]
                total_skipped += download_stats["skipped"]
                total_failed += download_stats["failed"]

                typer.echo(f"  ✅ Downloaded: {download_stats['successful']}")
                typer.echo(f"  ⏭️  Skipped: {download_stats['skipped']} (already have)")
                typer.echo(f"  ❌ Failed: {download_stats['failed']}")
                typer.echo(f"  📦 Size: {download_stats['bytes_downloaded'] / (1024*1024):.1f} MB")

        except Exception as e:
            typer.echo(f"  ⚠️  Error: {e}", err=True)
            logging.exception(f"Provider {provider_name} failed")

    typer.echo(f"\n{'='*60}")
    typer.echo(f"📊 Summary:")
    typer.echo(f"  Total results found: {total_found}")

    if not dry_run:
        typer.echo(f"  Downloaded: {total_downloaded}")
        typer.echo(f"  Skipped: {total_skipped}")
        typer.echo(f"  Failed: {total_failed}")
        typer.echo(f"\n💾 Files saved to: {library_dir / (category or 'uncategorized')}")
        typer.echo(f"📋 Metadata: {metadata_path}")


@app.command()
def providers():
    """List all available providers."""
    from src.provider_factory import ProviderFactory, PROVIDER_REGISTRY

    factory = ProviderFactory()
    academic = factory.get_all_academic()

    typer.echo("📚 Available Providers:")
    typer.echo("\nAcademic Providers:")
    for name, provider_class in sorted(PROVIDER_REGISTRY.items()):
        if provider_class in [p.__class__ for p in academic]:
            typer.echo(f"  • {name}")

    typer.echo("\nDocumentation Providers:")
    for name, provider_class in sorted(PROVIDER_REGISTRY.items()):
        if provider_class not in [p.__class__ for p in academic]:
            typer.echo(f"  • {name}")

    typer.echo(
        f"\nKeywords: 'all' (all providers), 'academic' ({len(academic)} academic providers)"
    )


@app.command()
def validate():
    """Validate library integrity and configuration."""
    from src.provider_factory import ProviderFactory, PROVIDER_REGISTRY

    typer.echo("🔍 ORION Validation")
    typer.echo("=" * 60)

    # Check provider imports
    typer.echo("\n1. Checking providers...")

    factory = ProviderFactory()
    typer.echo(f"  ✅ {len(PROVIDER_REGISTRY)} providers registered")

    academic = factory.get_all_academic()
    typer.echo(f"  ✅ {len(academic)} academic providers available")

    # Check data directory
    typer.echo("\n2. Checking data directories...")
    from pathlib import Path

    data_dir = Path(__file__).parent.parent / "data" / "library"
    if data_dir.exists():
        pdf_count = len(list(data_dir.rglob("*.pdf")))
        typer.echo(f"  ✅ Data directory exists: {data_dir}")
        typer.echo(f"  📄 {pdf_count} PDFs in library")
    else:
        typer.echo(f"  ⚠️  Data directory not found: {data_dir}")

    typer.echo("\n✅ Validation complete")


def main():
    """Main entry point."""
    app()


if __name__ == "__main__":
    main()
