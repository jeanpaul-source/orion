"""PDF to text converter with quality detection.

Extracts text from PDFs and flags low-quality scanned documents.

ELI5: Like a photocopier that can read PDFs and turn them into plain text,
but also tells you if the PDF is just a blurry photo of text instead of real text.
"""

from typing import Optional, Tuple
from pathlib import Path
import PyPDF2
import pdfplumber
import re
import logging

# Set up logging
logger = logging.getLogger(__name__)


class PDFConverter:
    """Extract text from PDF files."""

    def __init__(self) -> None:
        """Initialize PDF converter."""
        pass
    
    def convert(self, pdf_path: Path) -> Tuple[str, dict]:
        """
        Extract text from PDF.
        
        Args:
            pdf_path: Path to PDF file
            
        Returns:
            Tuple of (extracted_text, metadata_dict)
        """
        try:
            # Try pdfplumber first (better text extraction)
            text = self._extract_with_pdfplumber(pdf_path)
            if not text or len(text.strip()) < 100:
                # Fallback to PyPDF2
                text = self._extract_with_pypdf2(pdf_path)
        except Exception as e:
            # Final fallback
            logger.warning(f"pdfplumber extraction failed for {pdf_path}: {e}, falling back to PyPDF2")
            text = self._extract_with_pypdf2(pdf_path)
        
        # Extract metadata
        metadata = self._extract_metadata(pdf_path)
        
        # Add quality indicators
        metadata['text_length'] = len(text)
        metadata['is_scanned'] = self._is_likely_scanned(text, metadata)
        metadata['quality_score'] = self._estimate_quality(text)
        
        return text, metadata
    
    def _extract_with_pdfplumber(self, pdf_path: Path) -> str:
        """Extract text using pdfplumber (better for tables/layout)."""
        text_parts = []
        
        with pdfplumber.open(pdf_path) as pdf:
            for page in pdf.pages:
                page_text = page.extract_text()
                if page_text:
                    text_parts.append(page_text)
        
        return '\n\n'.join(text_parts)
    
    def _extract_with_pypdf2(self, pdf_path: Path) -> str:
        """Extract text using PyPDF2 (fallback)."""
        text_parts = []
        
        with open(pdf_path, 'rb') as f:
            pdf_reader = PyPDF2.PdfReader(f)
            for page in pdf_reader.pages:
                text = page.extract_text()
                if text:
                    text_parts.append(text)
        
        return '\n\n'.join(text_parts)
    
    def _extract_metadata(self, pdf_path: Path) -> dict:
        """Extract PDF metadata."""
        metadata = {}
        
        try:
            with open(pdf_path, 'rb') as f:
                pdf_reader = PyPDF2.PdfReader(f)
                
                # Basic info
                metadata['num_pages'] = len(pdf_reader.pages)
                
                # Document info
                if pdf_reader.metadata:
                    info = pdf_reader.metadata
                    metadata['title'] = info.get('/Title', '')
                    metadata['author'] = info.get('/Author', '')
                    metadata['subject'] = info.get('/Subject', '')
                    metadata['creator'] = info.get('/Creator', '')
                    metadata['producer'] = info.get('/Producer', '')
        except Exception as e:
            logger.error(f"Failed to extract PDF metadata from {pdf_path}: {e}")
            metadata['error'] = str(e)

        return metadata
    
    def _is_likely_scanned(self, text: str, metadata: dict) -> bool:
        """
        Detect if PDF is likely a scanned image.
        
        Heuristics:
        - Very little text extracted
        - High page count but low text
        - Contains OCR artifacts
        """
        if not text or len(text.strip()) < 100:
            return True
        
        num_pages = metadata.get('num_pages', 1)
        avg_chars_per_page = len(text) / num_pages
        
        # Less than 100 chars per page suggests scan
        if avg_chars_per_page < 100:
            return True
        
        # Check for OCR artifacts (random characters, bad spacing)
        # This is a simple heuristic
        ocr_patterns = [
            r'[^\x00-\x7F]{5,}',  # Long non-ASCII sequences
            r'\s{5,}',  # Excessive whitespace
            r'[|]{3,}',  # Pipe artifacts
        ]
        
        ocr_matches = sum(1 for pattern in ocr_patterns if re.search(pattern, text[:1000]))
        
        return ocr_matches >= 2
    
    def _estimate_quality(self, text: str) -> float:
        """
        Estimate text extraction quality (0.0 to 1.0).
        
        Higher score = better quality extraction.
        """
        if not text:
            return 0.0
        
        # Factor 1: Length (longer is generally better)
        length_score = min(len(text) / 10000, 1.0)
        
        # Factor 2: Alphanumeric ratio (text vs noise)
        alnum_chars = sum(c.isalnum() for c in text)
        alnum_ratio = alnum_chars / len(text) if len(text) > 0 else 0
        
        # Factor 3: Word-like patterns (spaces, proper capitalization)
        words = text.split()
        avg_word_length = sum(len(w) for w in words) / len(words) if words else 0
        word_score = 1.0 if 3 <= avg_word_length <= 8 else 0.5
        
        # Combined score
        quality = (length_score * 0.3 + alnum_ratio * 0.5 + word_score * 0.2)
        
        return min(quality, 1.0)
    
    def convert_to_markdown(self, pdf_path: Path) -> str:
        """
        Convert PDF to Markdown with basic structure preservation.
        
        Args:
            pdf_path: Path to PDF file
            
        Returns:
            Markdown-formatted text
        """
        text, metadata = self.convert(pdf_path)
        
        # Build markdown with metadata header
        markdown_parts = []
        
        # Title from metadata
        if metadata.get('title'):
            markdown_parts.append(f"# {metadata['title']}\n")
        
        # Metadata section
        if metadata.get('author'):
            markdown_parts.append(f"**Author:** {metadata['author']}\n")
        if metadata.get('subject'):
            markdown_parts.append(f"**Subject:** {metadata['subject']}\n")
        
        markdown_parts.append("\n---\n\n")
        
        # Content
        markdown_parts.append(text)
        
        return ''.join(markdown_parts)
