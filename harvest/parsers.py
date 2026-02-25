"""Document parsers — extract plain text from HTML and PDF files."""

import hashlib
import logging
import re
from pathlib import Path

log = logging.getLogger(__name__)

# Minimum extracted text length to consider a parse successful.
# Below this, the file is likely a captcha page, paywall, or corrupt PDF.
_MIN_TEXT_LENGTH = 200

# Extension-based MIME fallback (used when python-magic is unavailable)
_EXT_MIME = {
    ".pdf": "application/pdf",
    ".html": "text/html",
    ".htm": "text/html",
    ".md": "text/markdown",
    ".txt": "text/plain",
}


def detect_mime(file_path: Path) -> str:
    """Return MIME type from magic bytes, falling back to extension."""
    try:
        import magic

        return magic.from_file(str(file_path), mime=True)
    except Exception:
        return _EXT_MIME.get(file_path.suffix.lower(), "application/octet-stream")


def parse_pdf(file_path: Path) -> str | None:
    """Extract text from a PDF using pymupdf. Returns None on failure."""
    try:
        import fitz  # pymupdf
    except ImportError:
        log.warning("pymupdf not installed — cannot parse %s", file_path)
        return None

    try:
        doc = fitz.open(str(file_path))
        pages = []
        for page in doc:
            text = page.get_text()
            if text.strip():
                pages.append(text.strip())
        doc.close()
        combined = "\n\n".join(pages)
        if len(combined) < _MIN_TEXT_LENGTH:
            log.debug(
                "PDF too short after extraction (%d chars): %s",
                len(combined),
                file_path,
            )
            return None
        return combined
    except Exception as e:
        log.warning("PDF parse failed for %s: %s", file_path, e)
        return None


def parse_html(file_path: Path) -> str | None:
    """Extract article text from an HTML file.

    Primary: trafilatura (strips nav, ads, scripts).
    Fallback: regex tag stripping.
    Returns None if extraction produces too little text.
    """
    try:
        raw = file_path.read_text(encoding="utf-8", errors="replace")
    except OSError as e:
        log.warning("Cannot read HTML file %s: %s", file_path, e)
        return None

    # Primary: trafilatura
    try:
        import trafilatura

        text = trafilatura.extract(raw)
        if text and len(text) >= _MIN_TEXT_LENGTH:
            return text
    except Exception as e:
        log.debug("trafilatura failed for %s: %s", file_path, e)

    # Fallback: strip all tags
    try:
        text = re.sub(r"<[^>]+>", " ", raw)
        text = re.sub(r"\s+", " ", text).strip()
        if len(text) >= _MIN_TEXT_LENGTH:
            return text
    except Exception:
        pass

    log.debug("HTML extraction produced too little text: %s", file_path)
    return None


def content_hash(text: str) -> str:
    """Return a stable SHA-256 hex digest of the text content."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()
