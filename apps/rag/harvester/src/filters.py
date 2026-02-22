"""
Relevance filtering for ORION Harvester.

Category-aware filtering with required/secondary terms, red flags, venue quality heuristics,
and optional semantic similarity checking.
"""

import re
import logging
from typing import Dict, List, Optional, Tuple, TypedDict

from .constants import (
    GENERAL_RED_FLAGS,
    CATEGORY_REQUIRED_TERMS,
    CATEGORY_SECONDARY_TERMS,
    CATEGORY_EXCLUSION_TERMS,
    VENUE_PREFERENCES,
    LOW_QUALITY_VENUE_KEYWORDS,
    MIN_GITHUB_STARS,
    MIN_SO_SCORE,
    USE_EMBEDDINGS,
    SIMILARITY_THRESHOLD,
)
from .utils import semantic_checker

logger = logging.getLogger(__name__)


class RelevanceDiagnostics(TypedDict):
    """Diagnostics from relevance filtering.
    
    All fields are always present in the returned dict.
    """
    matched_terms: List[str]
    matched_synonyms: List[str]
    triggered_red_flags: List[str]
    triggered_exclusions: List[str]
    semantic_similarity: Optional[float]
    venue: str
    venue_quality: str
    citation_count: int
    doc_type: str
    source: str
    rejection_reason: str  # Present on rejection, empty string on acceptance
    decision: str  # 'accepted' or specific rejection reason


def _normalize_text(value: Optional[str]) -> str:
    """
    Lower-case helper that safely handles missing text.
    
    Args:
        value: Text to normalize
        
    Returns:
        Lowercase stripped text, or empty string if None
    """
    return (value or "").strip().lower()


def _term_matches(term: str, text: str) -> bool:
    """
    Check if term appears in text using word boundaries.
    
    Prevents partial matches (e.g., 'ann' won't match 'annotated').
    Handles multi-word terms (e.g., "tensor core" matches full phrase).
    
    Args:
        term: Search term (single or multi-word)
        text: Text to search within
        
    Returns:
        True if term found with word boundaries, False otherwise
    """
    # Escape special regex chars and use word boundaries
    pattern = r'\b' + re.escape(term) + r'\b'
    return bool(re.search(pattern, text, re.IGNORECASE))


def is_relevant_paper(paper: Dict, category: str) -> Tuple[bool, RelevanceDiagnostics]:
    """
    Evaluate whether a document should be considered relevant for a category.
    
    Handles both academic papers and non-paper sources (GitHub, Stack Overflow, blogs, docs).
    
    Filtering pipeline:
    1. Red flags (GENERAL_RED_FLAGS) → immediate rejection
    2. Category-specific exclusions → reject domain-specific noise
    3. Required terms → must match core terminology
    4. Secondary terms → fallback if no required matches
    5. Semantic similarity (optional) → NLP-based relevance
    6. Venue quality (papers only) → conference/journal heuristics
    7. Source-specific gates (GitHub stars, SO score) → quality thresholds
    
    Args:
        paper: Document dict with title, abstract, venue, citation_count, source, doc_type
        category: Target category name
        
    Returns:
        Tuple of (is_relevant: bool, diagnostics: Dict)
        
    Diagnostics dict contains:
        - matched_terms: List of matched required terms
        - matched_synonyms: List of matched secondary terms
        - triggered_red_flags: Red flags found
        - triggered_exclusions: Category exclusions found
        - semantic_similarity: NLP score (0-1) or None
        - venue: Original venue string
        - venue_quality: 'preferred', 'neutral', or 'low'
        - citation_count: Citation/star/score count
        - doc_type: 'paper', 'repo', 'post', 'doc', 'blog'
        - source: Provider name
        - rejection_reason: Explanation if rejected
        - decision: 'accepted' if passed all filters
    """
    title = paper.get("title", "")
    abstract = paper.get("abstract") or ""
    venue = paper.get("venue") or ""
    citation_count = paper.get("citation_count") or 0
    source = paper.get("source", "")
    doc_type = paper.get("doc_type", "paper")

    title_lower = _normalize_text(title)
    abstract_lower = _normalize_text(abstract)
    combined_text = f"{title_lower} {abstract_lower}".strip()

    diagnostics: RelevanceDiagnostics = {
        "matched_terms": [],
        "matched_synonyms": [],
        "triggered_red_flags": [],
        "triggered_exclusions": [],
        "semantic_similarity": None,
        "venue": venue,
        "venue_quality": "unknown",
        "citation_count": citation_count,
        "doc_type": doc_type,
        "source": source,
        "rejection_reason": "",
        "decision": ""
    }

    if not title_lower:
        diagnostics["rejection_reason"] = "missing title"
        return False, diagnostics

    # Red flags that should immediately short circuit.
    triggered_flags = [flag for flag in GENERAL_RED_FLAGS if _term_matches(flag, combined_text)]
    if triggered_flags:
        diagnostics["triggered_red_flags"] = triggered_flags
        diagnostics["rejection_reason"] = f"red flag: {', '.join(triggered_flags)}"
        return False, diagnostics

    # Category-specific exclusions (e.g. medical language in database searches).
    exclusion_terms = CATEGORY_EXCLUSION_TERMS.get(category, set())
    triggered_exclusions = [term for term in exclusion_terms if _term_matches(term, combined_text)]
    if triggered_exclusions:
        diagnostics["triggered_exclusions"] = triggered_exclusions
        diagnostics["rejection_reason"] = (
            f"category exclusion: {', '.join(triggered_exclusions)}"
        )
        return False, diagnostics

    # Required core terminology.
    required_terms = CATEGORY_REQUIRED_TERMS.get(category, set())
    matched_terms = [term for term in required_terms if _term_matches(term, combined_text)]
    diagnostics["matched_terms"] = matched_terms

    if required_terms and not matched_terms:
        synonyms = CATEGORY_SECONDARY_TERMS.get(category, set())
        matched_synonyms = [term for term in synonyms if _term_matches(term, combined_text)]
        diagnostics["matched_synonyms"] = matched_synonyms
        if not matched_synonyms:
            diagnostics["rejection_reason"] = "missing category keywords"
            return False, diagnostics

    # Optional semantic similarity guard using embeddings (title + abstract).
    if USE_EMBEDDINGS:
        semantic_text = title
        if abstract:
            semantic_text = f"{title}. {abstract[:500]}"
        is_semantic, similarity = semantic_checker.check_relevance(semantic_text, category)
        diagnostics["semantic_similarity"] = similarity
        if not is_semantic:
            diagnostics["rejection_reason"] = (
                f"semantic similarity {similarity:.3f} < {SIMILARITY_THRESHOLD}"
            )
            return False, diagnostics
    else:
        diagnostics["semantic_similarity"] = 1.0

    # Venue quality heuristics (only for academic papers).
    if doc_type == "paper":
        venue_lower = _normalize_text(venue)
        if venue_lower:
            preferred = VENUE_PREFERENCES.get(category, set())
            if preferred and any(token in venue_lower for token in preferred):
                diagnostics["venue_quality"] = "preferred"
            elif any(bad in venue_lower for bad in LOW_QUALITY_VENUE_KEYWORDS):
                diagnostics["venue_quality"] = "low"
                if citation_count < 10:
                    diagnostics["rejection_reason"] = f"low quality venue: {venue}"
                    return False, diagnostics
            else:
                diagnostics["venue_quality"] = "neutral"
    
    # Source-specific quality gates
    if source == "github":
        if citation_count < MIN_GITHUB_STARS:
            diagnostics["rejection_reason"] = f"GitHub stars ({citation_count}) < minimum ({MIN_GITHUB_STARS})"
            return False, diagnostics
    elif source == "stackoverflow":
        if citation_count < MIN_SO_SCORE:
            diagnostics["rejection_reason"] = f"SO score ({citation_count}) < minimum ({MIN_SO_SCORE})"
            return False, diagnostics

    diagnostics["decision"] = "accepted"
    return True, diagnostics


def format_relevance_diagnostics(details: Dict[str, object]) -> str:
    """
    Pretty-print relevance diagnostics for debug output.
    
    Args:
        details: Diagnostics dict from is_relevant_paper()
        
    Returns:
        Multi-line formatted string with all diagnostic details
    """
    def _fmt_list(key: str) -> str:
        values = details.get(key) or []
        if isinstance(values, (list, tuple, set)):
            return ", ".join(str(v) for v in values) if values else "(none)"
        return str(values)

    lines = [
        f"    matched_terms: {_fmt_list('matched_terms')}",
        f"    matched_synonyms: {_fmt_list('matched_synonyms')}",
        f"    red_flags: {_fmt_list('triggered_red_flags')}",
        f"    exclusions: {_fmt_list('triggered_exclusions')}",
        f"    semantic_similarity: {details.get('semantic_similarity')}",
        f"    venue_quality: {details.get('venue_quality')}",
        f"    citation_count: {details.get('citation_count')}",
    ]

    if details.get("rejection_reason"):
        lines.append(f"    rejection_reason: {details['rejection_reason']}")

    return "\n".join(lines)


__all__ = [
    "_normalize_text",
    "_term_matches",
    "is_relevant_paper",
    "format_relevance_diagnostics",
]
