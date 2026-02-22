#!/usr/bin/env python3
"""
ORION Unified CLI - Complete RAG Pipeline Management

Combines harvesting, processing, embedding, and querying into a single unified interface.
Designed to run on host (192.168.5.10) with scheduled update capability.

Usage:
    orion harvest --term "kubernetes" --domain manuals --max-docs 50
    orion process --domain academic --new-only
    orion embed --collection research-papers --new-only
    orion query "What are best practices for GPU passthrough?"
    orion pipeline run --query "kubernetes autoscaling" --domain manuals

Created: 2025-11-17 (Consolidation Phase)
"""

import logging
import sys
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.logging import RichHandler
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.table import Table

# Setup rich console
console = Console()

# Setup logging with Rich
logging.basicConfig(
    level=logging.INFO,
    format="%(message)s",
    datefmt="[%X]",
    handlers=[RichHandler(console=console, rich_tracebacks=True)]
)
logger = logging.getLogger("orion")

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent))

app = typer.Typer(
    name="orion",
    help="ORION Unified RAG Pipeline - Harvest, Process, Embed, Query",
    add_completion=False
)


@app.command()
def harvest(
    term: str = typer.Argument(..., help="Search term to harvest"),
    domain: str = typer.Option("academic", help="Domain: academic, manuals, blogs, github"),
    max_docs: int = typer.Option(50, help="Maximum documents to harvest"),
    new_only: bool = typer.Option(False, help="Skip already harvested documents"),
    dry_run: bool = typer.Option(False, help="Show what would be done without doing it")
):
    """
    Harvest documents from academic and technical sources.

    Examples:
        orion harvest "kubernetes autoscaling" --domain manuals --max-docs 100
        orion harvest "vector databases" --domain academic --new-only
    """
    console.print(f"\n[bold blue]🔍 Harvesting:[/bold blue] '{term}' (domain: {domain})")

    try:
        # Import providers
        from providers.provider_factory import ProviderFactory
        from processing.registry import IngestionRegistry

        # Initialize
        registry = IngestionRegistry()
        factory = ProviderFactory()

        # Get providers for domain
        providers = factory.get_providers_for_domain(domain)
        console.print(f"[dim]Using {len(providers)} providers for domain '{domain}'[/dim]")

        total_harvested = 0
        total_skipped = 0

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console
        ) as progress:
            for provider in providers:
                task = progress.add_task(
                    f"Searching {provider.name}...",
                    total=None
                )

                try:
                    # Search provider
                    docs = provider.search(term, max_results=max_docs)

                    for doc in docs:
                        # Check if already harvested
                        if new_only and registry.is_harvested(doc.url):
                            total_skipped += 1
                            continue

                        if not dry_run:
                            # Download document
                            output_dir = Path(f"data/raw/{domain}")
                            output_dir.mkdir(parents=True, exist_ok=True)

                            doc_path = provider.download(doc, output_dir)
                            if doc_path:
                                registry.mark_harvested(doc.url, str(doc_path))
                                total_harvested += 1
                                logger.debug(f"Downloaded: {doc_path.name}")
                        else:
                            total_harvested += 1

                    progress.update(task, completed=True)

                except Exception as e:
                    logger.error(f"Provider {provider.name} failed: {e}")
                    progress.update(task, completed=True)

        # Summary
        console.print(f"\n[bold green]✓ Harvest complete:[/bold green]")
        console.print(f"  • Harvested: {total_harvested} documents")
        if new_only:
            console.print(f"  • Skipped: {total_skipped} (already harvested)")
        if dry_run:
            console.print(f"  • [yellow]Dry run - no files downloaded[/yellow]")

    except Exception as e:
        console.print(f"[bold red]✗ Harvest failed:[/bold red] {e}")
        logger.exception("Harvest error")
        raise typer.Exit(code=1)


@app.command()
def process(
    domain: str = typer.Option("academic", help="Domain to process"),
    max_files: Optional[int] = typer.Option(None, help="Maximum files to process"),
    new_only: bool = typer.Option(False, help="Skip already processed documents"),
    dry_run: bool = typer.Option(False, help="Show what would be done without doing it")
):
    """
    Process raw documents (PDF/HTML/MD) with quality gates and chunking.

    Examples:
        orion process --domain academic --max-files 100
        orion process --domain manuals --new-only
    """
    console.print(f"\n[bold blue]⚙️  Processing:[/bold blue] {domain} documents")

    try:
        from processing.orchestrator import ORIONOrchestrator
        from processing.registry import IngestionRegistry

        # Initialize
        registry = IngestionRegistry()
        orchestrator = ORIONOrchestrator(registry)

        # Get raw documents
        raw_dir = Path(f"data/raw/{domain}")
        if not raw_dir.exists():
            console.print(f"[yellow]Warning:[/yellow] Directory {raw_dir} does not exist")
            return

        # Process documents
        result = orchestrator.run(
            raw_dir,
            max_files=max_files,
            new_only=new_only,
            dry_run=dry_run
        )

        # Summary
        console.print(f"\n[bold green]✓ Processing complete:[/bold green]")
        console.print(f"  • Processed: {result['processed']}")
        console.print(f"  • Accepted: {result['accepted']}")
        console.print(f"  • Rejected: {result['rejected']}")
        console.print(f"  • Acceptance rate: {result['acceptance_rate']:.1%}")
        if dry_run:
            console.print(f"  • [yellow]Dry run - no data modified[/yellow]")

    except Exception as e:
        console.print(f"[bold red]✗ Processing failed:[/bold red] {e}")
        logger.exception("Processing error")
        raise typer.Exit(code=1)


@app.command()
def embed(
    collection: str = typer.Argument(..., help="Qdrant collection name"),
    max_docs: Optional[int] = typer.Option(None, help="Maximum documents to embed"),
    new_only: bool = typer.Option(False, help="Skip already embedded documents"),
    batch_size: int = typer.Option(32, help="Embedding batch size")
):
    """
    Embed processed documents and index to Qdrant.

    Examples:
        orion embed research-papers --max-docs 100
        orion embed technical-docs --new-only --batch-size 64
    """
    console.print(f"\n[bold blue]🧠 Embedding:[/bold blue] {collection}")

    try:
        from processing.orchestrator import ORIONOrchestrator
        from processing.anythingllm_client import AnythingLLMClient
        from qdrant_client import QdrantClient

        # Initialize clients
        qdrant = QdrantClient(url="http://localhost:6333")
        llm_client = AnythingLLMClient()
        orchestrator = ORIONOrchestrator()

        # Embed documents
        result = orchestrator.embed_collection(
            collection,
            max_docs=max_docs,
            new_only=new_only,
            batch_size=batch_size
        )

        # Summary
        console.print(f"\n[bold green]✓ Embedding complete:[/bold green]")
        console.print(f"  • Embedded: {result['embedded']} documents")
        console.print(f"  • Total chunks: {result['chunks']}")
        console.print(f"  • Collection: {collection}")

        # Verify Qdrant
        collection_info = qdrant.get_collection(collection)
        console.print(f"  • Qdrant points: {collection_info.points_count:,}")

    except Exception as e:
        console.print(f"[bold red]✗ Embedding failed:[/bold red] {e}")
        logger.exception("Embedding error")
        raise typer.Exit(code=1)


@app.command()
def query(
    question: str = typer.Argument(..., help="Question to ask"),
    collection: str = typer.Option("technical-docs", help="Collection to search"),
    top_k: int = typer.Option(5, help="Number of results to return"),
    use_reranking: bool = typer.Option(True, help="Enable cross-encoder reranking"),
    use_hybrid: bool = typer.Option(True, help="Enable hybrid search (vector + keyword)")
):
    """
    Query the knowledge base with hybrid search and reranking.

    Examples:
        orion query "What are Proxmox GPU passthrough best practices?"
        orion query "kubernetes autoscaling" --top-k 10 --no-use-reranking
    """
    console.print(f"\n[bold blue]💬 Query:[/bold blue] '{question}'")
    console.print(f"[dim]Collection: {collection}, Top-K: {top_k}, Reranking: {use_reranking}, Hybrid: {use_hybrid}[/dim]\n")

    try:
        from retrieval.hybrid_search import hybrid_search
        from retrieval.reranker import Reranker
        from processing.anythingllm_client import AnythingLLMClient
        from qdrant_client import QdrantClient

        # Initialize clients
        qdrant = QdrantClient(url="http://localhost:6333")
        llm_client = AnythingLLMClient()

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console
        ) as progress:
            # Step 1: Search
            if use_hybrid:
                task = progress.add_task("Hybrid search (vector + keyword)...", total=None)
                candidates = hybrid_search(
                    qdrant, llm_client,
                    collection_name=collection,
                    query=question,
                    top_k=20 if use_reranking else top_k
                )
                progress.update(task, completed=True)
            else:
                task = progress.add_task("Vector search...", total=None)
                # Simple vector search
                embedding = llm_client.generate_embeddings([question])[0]
                search_results = qdrant.search(
                    collection_name=collection,
                    query_vector=embedding,
                    limit=20 if use_reranking else top_k
                )
                # Convert to SearchResult format
                from retrieval.hybrid_search import SearchResult
                candidates = [
                    SearchResult(
                        text=r.payload.get("text", ""),
                        score=r.score,
                        metadata=r.payload,
                        source="vector"
                    )
                    for r in search_results
                ]
                progress.update(task, completed=True)

            # Step 2: Rerank
            if use_reranking and candidates:
                task = progress.add_task("Reranking with cross-encoder...", total=None)
                reranker = Reranker()
                results = reranker.rerank(question, candidates, top_k=top_k)
                progress.update(task, completed=True)
            else:
                results = candidates[:top_k]

        # Display results
        if not results:
            console.print("[yellow]No results found[/yellow]")
            return

        console.print(f"\n[bold]Found {len(results)} results:[/bold]\n")

        for i, r in enumerate(results, 1):
            # Create result card
            console.print(f"[bold cyan]{i}. Score: {r.score:.3f}[/bold cyan] [dim]({r.source})[/dim]")

            # Show text snippet
            text_preview = r.text[:300] + "..." if len(r.text) > 300 else r.text
            console.print(f"   {text_preview}")

            # Show source metadata
            if r.source_file:
                console.print(f"   [dim]Source: {r.source_file}[/dim]")

            console.print()

    except Exception as e:
        console.print(f"[bold red]✗ Query failed:[/bold red] {e}")
        logger.exception("Query error")
        raise typer.Exit(code=1)


@app.command()
def pipeline(
    query: str = typer.Argument(..., help="Search query"),
    domain: str = typer.Option("academic", help="Domain: academic, manuals, blogs, github"),
    collection: str = typer.Option(None, help="Collection (defaults based on domain)"),
    max_docs: int = typer.Option(50, help="Maximum documents to harvest")
):
    """
    Run complete pipeline: harvest → process → embed.

    Examples:
        orion pipeline "kubernetes autoscaling" --domain manuals
        orion pipeline "vector databases" --domain academic --max-docs 100
    """
    # Default collection based on domain
    if collection is None:
        collection_map = {
            "academic": "research-papers",
            "manuals": "technical-docs",
            "blogs": "technical-docs",
            "github": "code-examples"
        }
        collection = collection_map.get(domain, "technical-docs")

    console.print(f"\n[bold magenta]🚀 Running Pipeline:[/bold magenta] '{query}'")
    console.print(f"[dim]Domain: {domain}, Collection: {collection}[/dim]\n")

    try:
        # Step 1: Harvest
        console.print("[bold]Step 1/3: Harvesting[/bold]")
        harvest(term=query, domain=domain, max_docs=max_docs, new_only=True)

        # Step 2: Process
        console.print("\n[bold]Step 2/3: Processing[/bold]")
        process(domain=domain, new_only=True)

        # Step 3: Embed
        console.print("\n[bold]Step 3/3: Embedding[/bold]")
        embed(collection=collection, new_only=True)

        console.print(f"\n[bold green]✅ Pipeline complete![/bold green]")
        console.print(f"[dim]Query with: orion query '{query}' --collection {collection}[/dim]\n")

    except Exception as e:
        console.print(f"\n[bold red]✗ Pipeline failed:[/bold red] {e}")
        logger.exception("Pipeline error")
        raise typer.Exit(code=1)


@app.command()
def status():
    """
    Show system status and statistics.
    """
    console.print("\n[bold]ORION System Status[/bold]\n")

    try:
        from processing.registry import IngestionRegistry
        from qdrant_client import QdrantClient

        # Registry stats
        console.print("[bold cyan]📊 Registry Statistics:[/bold cyan]")
        registry = IngestionRegistry()
        stats = registry.get_stats()

        table = Table(show_header=True, header_style="bold")
        table.add_column("Domain")
        table.add_column("Status")
        table.add_column("Count", justify="right")
        table.add_column("Chunks", justify="right")

        for row in stats:
            table.add_row(
                row['domain'],
                row['status'],
                str(row['count']),
                str(row.get('chunks', 0))
            )

        console.print(table)

        # Qdrant collections
        console.print("\n[bold cyan]🗄️  Qdrant Collections:[/bold cyan]")
        qdrant = QdrantClient(url="http://localhost:6333")
        collections = qdrant.get_collections()

        table = Table(show_header=True, header_style="bold")
        table.add_column("Collection")
        table.add_column("Points", justify="right")
        table.add_column("Dimension", justify="right")

        for coll in collections.collections:
            info = qdrant.get_collection(coll.name)
            table.add_row(
                coll.name,
                f"{info.points_count:,}",
                str(info.config.params.vectors.size)
            )

        console.print(table)
        console.print()

    except Exception as e:
        console.print(f"[bold red]✗ Status check failed:[/bold red] {e}")
        logger.exception("Status error")
        raise typer.Exit(code=1)


@app.command()
def info():
    """
    Show ORION configuration and environment info.
    """
    console.print("\n[bold]ORION Configuration[/bold]\n")

    try:
        import os
        from domains import DOMAINS

        # Show domains configuration
        console.print("[bold cyan]📋 Domain Configuration:[/bold cyan]")

        table = Table(show_header=True, header_style="bold")
        table.add_column("Domain")
        table.add_column("Chunk Size", justify="right")
        table.add_column("Overlap", justify="right")
        table.add_column("Quality Gate", justify="right")

        for name, config in DOMAINS.items():
            table.add_row(
                name,
                f"{config.chunk_size} tokens",
                f"{config.chunk_overlap} tokens",
                f"{config.quality_gates.get('min_text_density', 'N/A')}"
            )

        console.print(table)

        # Environment
        console.print("\n[bold cyan]🌍 Environment:[/bold cyan]")
        env_vars = {
            "ANYTHINGLLM_URL": os.getenv("ANYTHINGLLM_URL", "http://localhost:3001"),
            "QDRANT_URL": os.getenv("QDRANT_URL", "http://localhost:6333"),
            "VLLM_URL": os.getenv("VLLM_URL", "http://localhost:8000"),
        }

        for key, value in env_vars.items():
            console.print(f"  • {key}: {value}")

        console.print()

    except Exception as e:
        console.print(f"[bold red]✗ Info failed:[/bold red] {e}")
        logger.exception("Info error")
        raise typer.Exit(code=1)


def main():
    """CLI entry point"""
    app()


if __name__ == "__main__":
    main()
