"""Provider factory for creating and managing all harvester providers.

Central registry of all available providers with factory methods.
"""

from typing import Dict, List, Optional, Type
import logging

# NOTE:
# Import paths here use explicit relative imports so packaging works when installed.
# Previously this file used top-level imports like `from providers.semantic_scholar ...`
# which failed after editable install because `providers` isn't a top-level package; `src` is.
# Using relative imports keeps IDE friendliness and runtime correctness.

from .providers.base import BaseProvider

# Academic providers
from .providers.semantic_scholar import SemanticScholarProvider
from .providers.arxiv import ArxivProvider
from .providers.openalex import OpenAlexProvider
from .providers.core import COREProvider
from .providers.crossref import CrossrefProvider
from .providers.zenodo import ZenodoProvider
from .providers.dblp import DBLPProvider
from .providers.biorxiv import BiorxivProvider
from .providers.medrxiv import MedrxivProvider
from .providers.pubmed import PubMedProvider
from .providers.hal import HALProvider

# Doc providers
from .providers.github import GitHubProvider
from .providers.readthedocs import ReadTheDocsProvider
from .providers.blog import BlogProvider
from .providers.vendor_pdf import VendorPDFProvider

logger = logging.getLogger(__name__)


# Provider registry mapping names to classes
PROVIDER_REGISTRY: Dict[str, Type[BaseProvider]] = {
    # Academic providers (search-based)
    "semantic_scholar": SemanticScholarProvider,
    "arxiv": ArxivProvider,
    "openalex": OpenAlexProvider,
    "core": COREProvider,
    "crossref": CrossrefProvider,
    "zenodo": ZenodoProvider,
    "dblp": DBLPProvider,
    "biorxiv": BiorxivProvider,
    "medrxiv": MedrxivProvider,
    "pubmed": PubMedProvider,
    "hal": HALProvider,
    # Doc providers (discovery-based)
    "github": GitHubProvider,
    "readthedocs": ReadTheDocsProvider,
    "blog": BlogProvider,
    "vendor_pdf": VendorPDFProvider,
}


# Provider groups for convenience
ACADEMIC_PROVIDERS = [
    "semantic_scholar",
    "arxiv",
    "openalex",
    "core",
    "crossref",
    "zenodo",
    "dblp",
    "biorxiv",
    "medrxiv",
    "pubmed",
    "hal",
]

DOC_PROVIDERS = ["github", "readthedocs", "blog", "vendor_pdf"]

# Default cascade order for academic search (quality-first)
DEFAULT_ACADEMIC_CASCADE = [
    "semantic_scholar",  # Best quality, citation data
    "openalex",  # Large coverage, good metadata
    "arxiv",  # Preprints, direct PDFs
    "core",  # 250M+ open access
    "crossref",  # DOI metadata + Unpaywall
    "dblp",  # Computer science focus
    "pubmed",  # Biomedical
    "biorxiv",  # Biology preprints
    "medrxiv",  # Medical preprints
    "zenodo",  # CERN repository
    "hal",  # French archive
]


class ProviderFactory:
    """Factory for creating and managing providers."""

    @staticmethod
    def create(provider_name: str, **kwargs) -> BaseProvider:
        """
        Create a provider instance by name.

        Args:
            provider_name: Name of provider (e.g., 'semantic_scholar')
            **kwargs: Arguments passed to provider constructor

        Returns:
            Provider instance

        Raises:
            ValueError: If provider name not recognized
        """
        provider_class = PROVIDER_REGISTRY.get(provider_name.lower())
        if not provider_class:
            raise ValueError(
                f"Unknown provider: {provider_name}. "
                f"Available: {', '.join(PROVIDER_REGISTRY.keys())}"
            )

        return provider_class(**kwargs)

    @staticmethod
    def create_multiple(provider_names: List[str], **kwargs) -> List[BaseProvider]:
        """
        Create multiple provider instances.

        Args:
            provider_names: List of provider names
            **kwargs: Arguments passed to each provider constructor

        Returns:
            List of provider instances
        """
        providers = []
        for name in provider_names:
            try:
                provider = ProviderFactory.create(name, **kwargs)
                providers.append(provider)
            except ValueError as e:
                logger.warning(f"Skipping invalid provider: {e}")

        return providers

    @staticmethod
    def get_all_academic() -> List[BaseProvider]:
        """Get all academic providers in quality-first order."""
        return ProviderFactory.create_multiple(DEFAULT_ACADEMIC_CASCADE)

    @staticmethod
    def get_all_doc() -> List[BaseProvider]:
        """Get all documentation providers."""
        return ProviderFactory.create_multiple(DOC_PROVIDERS)

    @staticmethod
    def get_all() -> List[BaseProvider]:
        """Get ALL providers (academic + doc)."""
        return ProviderFactory.create_multiple(DEFAULT_ACADEMIC_CASCADE + DOC_PROVIDERS)

    @staticmethod
    def resolve_provider_names(names: Optional[List[str]] = None) -> List[str]:
        """
        Resolve provider names, handling special keywords.

        Args:
            names: List of provider names or keywords ('all', 'academic', 'docs')

        Returns:
            Resolved list of provider names
        """
        if not names or "all" in names:
            return DEFAULT_ACADEMIC_CASCADE + DOC_PROVIDERS

        resolved = []
        for name in names:
            name_lower = name.lower().strip()

            # Handle keywords
            if name_lower in ("academic", "papers"):
                resolved.extend(DEFAULT_ACADEMIC_CASCADE)
            elif name_lower in ("docs", "documentation"):
                resolved.extend(DOC_PROVIDERS)
            elif name_lower == "github":
                resolved.append("github")
            else:
                # Assume it's a direct provider name
                if name_lower in PROVIDER_REGISTRY:
                    resolved.append(name_lower)
                else:
                    logger.warning(f"Unknown provider: {name}")

        # Remove duplicates while preserving order
        seen = set()
        unique = []
        for p in resolved:
            if p not in seen:
                seen.add(p)
                unique.append(p)

        return unique

    @staticmethod
    def list_providers() -> Dict[str, List[str]]:
        """List all available providers by category."""
        return {
            "academic": ACADEMIC_PROVIDERS,
            "documentation": DOC_PROVIDERS,
        }


def get_provider(name: str, **kwargs) -> BaseProvider:
    """Convenience function to create a provider."""
    return ProviderFactory.create(name, **kwargs)
