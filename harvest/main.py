#!/usr/bin/env python3
"""Harvest real lab state into pgvector.

Run on the server:  python -m harvest
Dry run:            python -m harvest --dry-run
"""
import argparse
import sys

import hal.config as cfg
from hal.llm import OllamaClient
from harvest.collect import collect_all
from harvest.ingest import ingest


def main() -> None:
    parser = argparse.ArgumentParser(description="Harvest lab state into pgvector")
    parser.add_argument("--dry-run", action="store_true", help="collect and chunk but don't write to DB")
    args = parser.parse_args()

    config = cfg.load()

    print("Orion harvester")
    print(f"  ollama:   {config.ollama_host}  ({config.embed_model})")
    print(f"  pgvector: {config.pgvector_dsn.split('@')[-1]}")
    print()

    # Collect
    print("Collecting lab state...")
    docs = collect_all()
    print(f"  total: {len(docs)} documents\n")

    if not docs:
        print("Nothing to ingest.")
        sys.exit(0)

    # Ingest
    llm = OllamaClient(config.ollama_host, config.ollama_model, config.embed_model)

    if not llm.ping():
        print("ERROR: Ollama not reachable — is it running?")
        sys.exit(1)

    action = "dry-run chunking" if args.dry_run else "embedding + upserting"
    print(f"Ingesting ({action})...")
    stats = ingest(docs, config.pgvector_dsn, llm, dry_run=args.dry_run)

    print()
    print("Done.")
    if args.dry_run:
        print(f"  would write {stats['chunks']} chunks from {len(docs)} documents")
    else:
        print(f"  deleted:  {stats['deleted']} old lab docs")
        print(f"  inserted: {stats['chunks']} chunks from {stats['docs']} documents")
        if stats["errors"]:
            print(f"  errors:   {stats['errors']}")


if __name__ == "__main__":
    main()
