"""Markdown normalizer for consistent formatting.

Standardizes markdown from different sources (GitHub READMEs, converted HTML, etc.)

ELI5: Like a text formatter that makes sure all documents look similar,
fixing spacing, headings, and links so they follow the same style.
"""

import re
from typing import Optional


class MarkdownNormalizer:
    """Normalize and clean markdown content."""

    def __init__(self) -> None:
        """Initialize normalizer."""
        pass
    
    def normalize(self, markdown: str) -> str:
        """
        Normalize markdown content.
        
        Args:
            markdown: Raw markdown string
            
        Returns:
            Cleaned and normalized markdown
        """
        # Apply all normalization rules
        text = self._fix_headings(markdown)
        text = self._fix_lists(text)
        text = self._fix_links(text)
        text = self._fix_code_blocks(text)
        text = self._fix_whitespace(text)
        text = self._remove_badges(text)
        text = self._fix_tables(text)
        
        return text.strip()
    
    def _fix_headings(self, text: str) -> str:
        """Normalize heading syntax."""
        # Ensure space after # in headings
        text = re.sub(r'^(#{1,6})([^\s#])', r'\1 \2', text, flags=re.MULTILINE)
        
        # Remove trailing # in headings
        text = re.sub(r'^(#{1,6}.*?)\s*#+\s*$', r'\1', text, flags=re.MULTILINE)
        
        # Ensure blank line before headings (except at start)
        text = re.sub(r'(\n)([^\n].*\n)(#{1,6}\s)', r'\1\2\n\3', text)
        
        return text
    
    def _fix_lists(self, text: str) -> str:
        """Normalize list formatting."""
        # Ensure space after list markers (-, *, +)
        text = re.sub(r'^([\-\*\+])([^\s])', r'\1 \2', text, flags=re.MULTILINE)
        
        # Normalize ordered list markers (1., 2., etc.)
        text = re.sub(r'^(\d+\.)([^\s])', r'\1 \2', text, flags=re.MULTILINE)
        
        return text
    
    def _fix_links(self, text: str) -> str:
        """Fix and clean links."""
        # Remove empty links [text]()
        text = re.sub(r'\[([^\]]+)\]\(\s*\)', r'\1', text)
        
        # Fix malformed links with spaces
        text = re.sub(r'\[\s+([^\]]+)\s+\]', r'[\1]', text)
        
        # Remove reference-style links that are unused
        # (This is complex, skip for now)
        
        return text
    
    def _fix_code_blocks(self, text: str) -> str:
        """Normalize code block formatting."""
        # Ensure blank line before/after code blocks
        text = re.sub(r'([^\n])\n(```)', r'\1\n\n\2', text)
        text = re.sub(r'(```[^\n]*\n)', r'\1\n', text)
        
        return text
    
    def _fix_whitespace(self, text: str) -> str:
        """Clean up whitespace issues."""
        # Remove trailing whitespace
        text = re.sub(r'[ \t]+$', '', text, flags=re.MULTILINE)
        
        # Normalize multiple blank lines to max 2
        text = re.sub(r'\n{4,}', '\n\n\n', text)
        
        # Remove spaces before punctuation
        text = re.sub(r'\s+([.,;:!?])', r'\1', text)
        
        return text
    
    def _remove_badges(self, text: str) -> str:
        """Remove common badge images (CI, version, etc.)."""
        # Match badge patterns
        badge_patterns = [
            r'!\[.*?\]\(https?://.*?badge.*?\)',
            r'!\[.*?\]\(https?://img\.shields\.io.*?\)',
            r'!\[.*?\]\(https?://.*?status.*?\.svg\)',
        ]
        
        for pattern in badge_patterns:
            text = re.sub(pattern, '', text)
        
        return text
    
    def _fix_tables(self, text: str) -> str:
        """Normalize table formatting."""
        # Ensure blank line before tables
        text = re.sub(r'([^\n])\n(\|.*\|)', r'\1\n\n\2', text)
        
        return text
    
    def extract_title(self, markdown: str) -> Optional[str]:
        """Extract document title from first heading."""
        match = re.search(r'^#\s+(.+)$', markdown, re.MULTILINE)
        if match:
            return match.group(1).strip()
        return None
    
    def remove_front_matter(self, markdown: str) -> str:
        """Remove YAML front matter if present."""
        # Match Jekyll/Hugo style front matter
        pattern = r'^---\n.*?\n---\n'
        return re.sub(pattern, '', markdown, flags=re.DOTALL)
    
    def estimate_reading_time(self, markdown: str) -> int:
        """
        Estimate reading time in minutes.
        
        Assumes 200 words per minute average reading speed.
        """
        # Remove code blocks (read slower)
        text_no_code = re.sub(r'```.*?```', '', markdown, flags=re.DOTALL)
        
        # Count words
        words = len(text_no_code.split())
        
        # 200 words per minute
        minutes = max(1, round(words / 200))
        
        return minutes
