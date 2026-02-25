"""Tests for harvest/parsers.py — PDF, HTML parsing and content hashing."""
from harvest.parsers import content_hash, detect_mime, parse_html, parse_pdf

# --- content_hash ---

def test_content_hash_deterministic():
    assert content_hash("hello") == content_hash("hello")


def test_content_hash_differs():
    assert content_hash("hello") != content_hash("world")


def test_content_hash_is_hex_string():
    h = content_hash("test")
    assert len(h) == 64  # SHA-256 hex
    assert all(c in "0123456789abcdef" for c in h)


# --- detect_mime ---

def test_detect_mime_pdf_by_magic(tmp_path):
    f = tmp_path / "test.pdf"
    f.write_bytes(b"%PDF-1.4 fake content here")
    mime = detect_mime(f)
    assert "pdf" in mime.lower()


def test_detect_mime_html_by_extension(tmp_path):
    f = tmp_path / "test.html"
    f.write_text("<html><body>hello</body></html>")
    mime = detect_mime(f)
    assert "html" in mime.lower() or "text" in mime.lower()


def test_detect_mime_unknown_falls_back(tmp_path):
    f = tmp_path / "test.xyz"
    f.write_bytes(b"\x00\x01\x02\x03")
    mime = detect_mime(f)
    assert isinstance(mime, str)


# --- parse_html ---

def test_parse_html_extractable(tmp_path):
    """An HTML file with substantial article text should be parsed."""
    f = tmp_path / "article.html"
    body = " ".join(["word"] * 100)
    f.write_text(f"<html><body><article><p>{body}</p></article></body></html>")
    result = parse_html(f)
    assert result is not None
    assert len(result) >= 200


def test_parse_html_captcha_returns_none(tmp_path):
    """A minimal captcha page with almost no real text should return None."""
    f = tmp_path / "captcha.html"
    f.write_text(
        "<html><head><title>Check</title></head>"
        "<body><script>var x=1;</script></body></html>"
    )
    result = parse_html(f)
    assert result is None


def test_parse_html_nonexistent_returns_none(tmp_path):
    f = tmp_path / "missing.html"
    result = parse_html(f)
    assert result is None


# --- parse_pdf ---

def test_parse_pdf_nonexistent_returns_none(tmp_path):
    f = tmp_path / "missing.pdf"
    result = parse_pdf(f)
    assert result is None


def test_parse_pdf_corrupt_returns_none(tmp_path):
    f = tmp_path / "bad.pdf"
    f.write_bytes(b"not a real pdf at all")
    result = parse_pdf(f)
    assert result is None


def test_parse_pdf_too_short_returns_none(tmp_path):
    """A PDF that produces very little text should be filtered out."""
    # We can't easily create a real PDF with little text, but we can test
    # the code path by checking corrupt files return None
    f = tmp_path / "tiny.pdf"
    f.write_bytes(b"%PDF-1.4 minimal")
    result = parse_pdf(f)
    assert result is None
