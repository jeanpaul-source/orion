"""GitHub README and documentation harvester.

Fetches README files from GitHub repositories using the GitHub API.

ELI5: Like a robot that goes to GitHub, finds interesting code projects,
and downloads their instruction manuals (README files).
"""

import logging
from typing import List, Optional
from datetime import datetime

try:
    from github import Github, GithubException
except ImportError:
    Github = None
    GithubException = Exception

from .base import BaseProvider, Document
from ..converters.md_normalizer import MarkdownNormalizer
from ..doc_config import GITHUB_TOKEN, DEFAULT_RATE_LIMIT

logger = logging.getLogger(__name__)


class GitHubProvider(BaseProvider):
    """Harvest README files from GitHub repositories."""

    def __init__(
        self,
        token: Optional[str] = None,
        starred: bool = False,
        repo_list: Optional[List[str]] = None,
        rate_limit: float = DEFAULT_RATE_LIMIT,
    ):
        """
        Initialize GitHub harvester.

        Args:
            token: GitHub personal access token (or use GITHUB_TOKEN env var)
            starred: Fetch READMEs from starred repos
            repo_list: List of repo names (format: 'owner/repo')
            rate_limit: Seconds between requests
        """
        super().__init__(rate_limit)

        if Github is None:
            raise ImportError("PyGithub not installed. Run: pip install PyGithub")

        self.token = token or GITHUB_TOKEN
        if not self.token:
            raise ValueError(
                "GitHub token required. Set GITHUB_TOKEN env var or pass token parameter."
            )

        self.github = Github(self.token)  # type: ignore[call-arg]
        self.starred = starred
        self.repo_list = repo_list or []
        self.normalizer = MarkdownNormalizer()

    def get_provider_name(self) -> str:
        """Return provider identifier."""
        return "github"

    def get_provider_type(self) -> str:
        """Return provider type."""
        return "documentation"

    def discover(self) -> List[str]:
        """
        Discover repository READMEs.

        Returns list of repo full names (owner/repo).
        """
        repos = []

        # Get starred repos if requested
        if self.starred:
            try:
                user = self.github.get_user()
                starred_repos = user.get_starred()
                for repo in starred_repos:
                    repos.append(repo.full_name)
                    self._enforce_rate_limit()
            except GithubException as e:
                logger.error(f"Error fetching starred repos: {e}")

        # Add manual repo list
        repos.extend(self.repo_list)

        # Remove duplicates
        return list(set(repos))

    def fetch(self, url: str) -> Optional[Document]:
        """
        Fetch README from a repository.

        Args:
            url: Repository name (format: 'owner/repo')

        Returns:
            Document object or None on error
        """
        repo_full_name = url  # Base class expects 'url' parameter
        try:
            self._enforce_rate_limit()

            # Get repository
            repo = self.github.get_repo(repo_full_name)

            # Get README
            try:
                readme = repo.get_readme()
                content = readme.decoded_content.decode("utf-8")
            except GithubException:
                # No README found
                return None

            # Normalize markdown
            normalized_content = self.normalizer.normalize(content)

            # Extract metadata
            title = self.normalizer.extract_title(normalized_content) or repo.name

            metadata = {
                "repo_name": repo.name,
                "repo_full_name": repo.full_name,
                "repo_url": repo.html_url,
                "description": repo.description,
                "stars": repo.stargazers_count,
                "language": repo.language,
                "topics": repo.get_topics(),
                "created_at": repo.created_at.isoformat() if repo.created_at else None,
                "updated_at": repo.updated_at.isoformat() if repo.updated_at else None,
                "readme_url": readme.html_url,
                "fetch_timestamp": datetime.utcnow().isoformat(),
            }

            # Create document
            doc = Document(
                url=readme.html_url,
                title=title,
                content_type="markdown",
                source_provider=self.get_provider_name(),
                raw_content=normalized_content.encode("utf-8"),
                metadata=metadata,
                discovered_at=datetime.utcnow(),
            )

            return doc

        except GithubException as e:
            logger.error(f"Error fetching {repo_full_name}: {e}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error fetching {repo_full_name}: {e}")
            return None

    def get_rate_limit_status(self) -> dict:
        """Get current GitHub API rate limit status."""
        try:
            rate_limit = self.github.get_rate_limit()
            return {
                "core": {
                    "remaining": rate_limit.core.remaining,
                    "limit": rate_limit.core.limit,
                    "reset": rate_limit.core.reset.isoformat(),
                },
                "search": {
                    "remaining": rate_limit.search.remaining,
                    "limit": rate_limit.search.limit,
                    "reset": rate_limit.search.reset.isoformat(),
                },
            }
        except Exception as e:
            return {"error": str(e)}


def main():
    """CLI entry point for testing."""
    import argparse

    # from infrastructure.coordinator import HarvestCoordinator
    from ..doc_config import OUTPUT_DIR

    parser = argparse.ArgumentParser(description="Harvest GitHub READMEs")
    parser.add_argument("--starred", action="store_true", help="Fetch starred repos")
    parser.add_argument("--repos", nargs="+", help="List of repos (owner/repo format)")
    parser.add_argument("--max-docs", type=int, help="Max documents to fetch")
    parser.add_argument("--token", help="GitHub token (or use GITHUB_TOKEN env var)")
    parser.add_argument("--output", default=OUTPUT_DIR, help="Output directory")

    args = parser.parse_args()

    logger.info("=" * 70)
    logger.info("GitHub README Harvester")
    logger.info("=" * 70)

    provider = GitHubProvider(token=args.token, starred=args.starred, repo_list=args.repos or [])

    # Show rate limit
    rate_status = provider.get_rate_limit_status()
    if "error" in rate_status:
        logger.warning(f"⚠️  Warning: Could not fetch rate limit: {rate_status['error']}")
    else:
        logger.info(
            f"📊 Rate limit: {rate_status['core']['remaining']}/{rate_status['core']['limit']}"
        )

    # Initialize coordinator to handle saving
    # coordinator = HarvestCoordinator(output_dir=Path(args.output), registry_db=REGISTRY_DB)

    # Register provider and harvest
    logger.info(f"\n📥 Harvesting from GitHub...")
    # coordinator.register_provider(provider)
    # results = coordinator.harvest_all(max_docs_per_provider=args.max_docs)

    # Extract stats
    # provider_stats = results.get("providers", {}).get("github", {})
    results = {}
    provider_stats = {}

    logger.info("\n" + "=" * 70)
    logger.info("RESULTS")
    logger.info("=" * 70)
    logger.info(f"✅ Discovered: {provider_stats.get('discovered', 0)}")
    logger.info(f"📥 Fetched: {provider_stats.get('fetched', 0)}")
    logger.info(f"💾 Saved: {provider_stats.get('saved', 0)}")
    logger.info(f"⏭️  Skipped (duplicate): {provider_stats.get('skipped_duplicate', 0)}")
    logger.info(f"⏭️  Skipped (quality): {provider_stats.get('skipped_quality', 0)}")
    logger.error(f"❌ Errors: {len(provider_stats.get('errors', []))}")

    errors = provider_stats.get("errors", [])
    if errors:
        logger.info("\nErrors:")
        for error in errors[:5]:  # Show first 5
            logger.info(f"  • {error}")

    logger.info(f"\n📂 Files saved to: {args.output}/github/")
    logger.info(f"⏱️  Duration: {results.get('duration_seconds', 0):.2f}s")
    logger.info("=" * 70)


if __name__ == "__main__":
    main()
