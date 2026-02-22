"""
Shared file handling utilities for ORION ecosystem.

Provides:
- Safe filename generation
- File hashing for deduplication
- File validation utilities

Consolidates utilities previously scattered in harvester/src/utils.py
and other locations.

Author: ORION Consolidation Initiative
Date: November 17, 2025
"""

import hashlib
import logging
from pathlib import Path
from typing import Optional

from .exceptions import FileOperationError, InvalidFileError

logger = logging.getLogger(__name__)


def sanitize_filename(title: str, max_length: int = 200) -> str:
    """
    Convert title to safe filesystem filename.

    Removes special characters, limits length, and ensures the filename
    is compatible with all major filesystems (Linux, Windows, macOS).

    Args:
        title: Title string (may contain special characters)
        max_length: Maximum filename length (default: 200)

    Returns:
        Safe filename (alphanumeric, spaces, hyphens, underscores only)

    Example:
        >>> sanitize_filename("How to Configure Kubernetes/Docker!")
        'How_to_Configure_Kubernetes_Docker'
        >>> sanitize_filename("RAG System: Best Practices (2024)")
        'RAG_System_Best_Practices_2024'
    """
    # Replace unsafe characters with underscores
    safe = "".join(
        c if c.isalnum() or c in (" ", "-", "_") else "_" for c in title
    )

    # Remove leading/trailing underscores and spaces
    safe = safe.strip("_ ")

    # Collapse multiple underscores
    while "__" in safe:
        safe = safe.replace("__", "_")

    # Limit length
    safe = safe[:max_length]

    # Fallback if completely empty
    if not safe:
        safe = "document"

    logger.debug(f"Sanitized filename: '{title[:50]}' → '{safe}'")
    return safe


def compute_file_hash(
    filepath: Path, algorithm: str = "sha256", chunk_size: int = 8192
) -> str:
    """
    Compute cryptographic hash of file for deduplication.

    Reads file in chunks to handle large files efficiently without
    loading entire file into memory.

    Args:
        filepath: Path to file
        algorithm: Hash algorithm (default: sha256)
                  Supported: md5, sha1, sha256, sha512
        chunk_size: Bytes to read per chunk (default: 8192)

    Returns:
        Hex digest of file hash

    Raises:
        FileNotFoundError: If file doesn't exist
        InvalidFileError: If file cannot be read
        ValueError: If algorithm is not supported

    Example:
        >>> from pathlib import Path
        >>> hash_val = compute_file_hash(Path("paper.pdf"))
        >>> hash_val
        'a1b2c3d4e5f6...'
        >>> # Check if two files are identical
        >>> hash1 = compute_file_hash(Path("file1.pdf"))
        >>> hash2 = compute_file_hash(Path("file2.pdf"))
        >>> are_identical = (hash1 == hash2)
    """
    if not filepath.exists():
        raise FileNotFoundError(f"File not found: {filepath}")

    if not filepath.is_file():
        raise InvalidFileError(f"Not a file: {filepath}")

    try:
        hasher = hashlib.new(algorithm)
    except ValueError as e:
        raise ValueError(f"Unsupported hash algorithm: {algorithm}") from e

    try:
        with open(filepath, "rb") as f:
            # Read in chunks to handle large files
            for chunk in iter(lambda: f.read(chunk_size), b""):
                hasher.update(chunk)
    except IOError as e:
        logger.error(f"Failed to hash {filepath}: {e}")
        raise InvalidFileError(f"Cannot read file: {filepath}") from e

    hex_digest = hasher.hexdigest()
    logger.debug(f"Computed {algorithm} hash for {filepath.name}: {hex_digest[:16]}...")
    return hex_digest


def file_changed(
    filepath: Path, previous_hash: str, algorithm: str = "sha256"
) -> bool:
    """
    Check if file has changed since last hash.

    Useful for detecting file modifications in incremental processing
    pipelines.

    Args:
        filepath: Path to file
        previous_hash: Previous hash value
        algorithm: Hash algorithm (default: sha256)

    Returns:
        True if file has changed, False otherwise

    Example:
        >>> # Store hash during first processing
        >>> old_hash = compute_file_hash(Path("doc.pdf"))
        >>> # Later, check if file was modified
        >>> if file_changed(Path("doc.pdf"), old_hash):
        ...     print("File was updated, reprocess needed")
    """
    try:
        current_hash = compute_file_hash(filepath, algorithm)
        changed = current_hash != previous_hash

        if changed:
            logger.info(f"File changed detected: {filepath.name}")
        else:
            logger.debug(f"File unchanged: {filepath.name}")

        return changed
    except (FileNotFoundError, InvalidFileError) as e:
        logger.warning(f"Cannot check file change for {filepath}: {e}")
        return True  # Assume changed if we can't verify


def validate_file(
    filepath: Path,
    min_size: Optional[int] = None,
    max_size: Optional[int] = None,
    allowed_extensions: Optional[list] = None,
) -> bool:
    """
    Validate file meets basic requirements.

    Args:
        filepath: Path to file
        min_size: Minimum file size in bytes (optional)
        max_size: Maximum file size in bytes (optional)
        allowed_extensions: List of allowed extensions (e.g., ['.pdf', '.txt'])

    Returns:
        True if file passes all validations

    Raises:
        InvalidFileError: If file fails validation

    Example:
        >>> # Validate PDF is between 1KB and 50MB
        >>> validate_file(
        ...     Path("paper.pdf"),
        ...     min_size=1024,
        ...     max_size=50*1024*1024,
        ...     allowed_extensions=['.pdf']
        ... )
        True
    """
    if not filepath.exists():
        raise InvalidFileError(f"File not found: {filepath}")

    if not filepath.is_file():
        raise InvalidFileError(f"Not a file: {filepath}")

    # Check size
    file_size = filepath.stat().st_size

    if min_size is not None and file_size < min_size:
        raise InvalidFileError(
            f"File too small: {filepath.name} ({file_size} bytes < {min_size} bytes)"
        )

    if max_size is not None and file_size > max_size:
        raise InvalidFileError(
            f"File too large: {filepath.name} ({file_size} bytes > {max_size} bytes)"
        )

    # Check extension
    if allowed_extensions is not None:
        ext = filepath.suffix.lower()
        if ext not in allowed_extensions:
            raise InvalidFileError(
                f"Invalid file extension: {filepath.name} (allowed: {allowed_extensions})"
            )

    logger.debug(f"File validation passed: {filepath.name} ({file_size} bytes)")
    return True


def ensure_directory(dirpath: Path, create: bool = True) -> Path:
    """
    Ensure directory exists, optionally creating it.

    Args:
        dirpath: Path to directory
        create: If True, create directory if it doesn't exist (default: True)

    Returns:
        Path object (guaranteed to exist if create=True)

    Raises:
        FileOperationError: If directory cannot be created

    Example:
        >>> output_dir = ensure_directory(Path("/tmp/orion-output"))
        >>> # Directory now exists and can be used
    """
    if dirpath.exists():
        if not dirpath.is_dir():
            raise FileOperationError(f"Path exists but is not a directory: {dirpath}")
        return dirpath

    if create:
        try:
            dirpath.mkdir(parents=True, exist_ok=True)
            logger.debug(f"Created directory: {dirpath}")
        except OSError as e:
            logger.error(f"Failed to create directory {dirpath}: {e}")
            raise FileOperationError(f"Cannot create directory: {dirpath}") from e
    else:
        raise FileOperationError(f"Directory does not exist: {dirpath}")

    return dirpath


def get_file_extension(filepath: Path, lowercase: bool = True) -> str:
    """
    Get file extension.

    Args:
        filepath: Path to file
        lowercase: If True, return lowercase extension (default: True)

    Returns:
        File extension including dot (e.g., '.pdf')

    Example:
        >>> get_file_extension(Path("Document.PDF"))
        '.pdf'
    """
    ext = filepath.suffix
    if lowercase:
        ext = ext.lower()
    return ext


def safe_filename_from_url(url: str, max_length: int = 200) -> str:
    """
    Extract safe filename from URL.

    Args:
        url: URL string
        max_length: Maximum filename length (default: 200)

    Returns:
        Safe filename

    Example:
        >>> safe_filename_from_url("https://arxiv.org/pdf/2301.12345.pdf")
        '2301.12345.pdf'
    """
    from urllib.parse import urlparse

    parsed = urlparse(url)
    filename = Path(parsed.path).name

    if not filename:
        filename = "download"

    return sanitize_filename(filename, max_length)
