"""Property-based tests for Judge command classification.

Uses Hypothesis to generate thousands of random inputs and verify that
the Judge's pure functions never crash and always return the correct types.

Property-based testing ("PBT") works differently from normal tests:
instead of checking specific examples, it generates random inputs and
verifies that *invariants* (things that must always be true) hold.
For example: "classify_command always returns an int between 0 and 3,
no matter what string you give it."

This catches edge cases that hand-written tests miss — empty strings,
Unicode, extremely long inputs, embedded null bytes, etc.
"""

from __future__ import annotations

from hypothesis import given, settings
from hypothesis.strategies import text

from hal.judge import (
    _canonicalize_path,
    _detect_evasion,
    _is_safe_command,
    _normalize_command,
    classify_command,
    tier_for,
)

# ---------------------------------------------------------------------------
# Strategy: arbitrary strings up to 500 chars.  This covers normal commands,
# Unicode, empty strings, whitespace-only, embedded nulls, etc.
# ---------------------------------------------------------------------------
_CMD = text(min_size=0, max_size=500)


# ---------------------------------------------------------------------------
# classify_command — the main entry point for shell command classification
# ---------------------------------------------------------------------------


@given(cmd=_CMD)
@settings(max_examples=500, deadline=2000)
def test_classify_command_always_returns_valid_tier(cmd: str) -> None:
    """classify_command must always return an int in {0, 1, 2, 3}."""
    tier = classify_command(cmd)
    assert isinstance(tier, int), f"Expected int, got {type(tier)}"
    assert 0 <= tier <= 3, f"Tier {tier} out of range for input: {cmd!r}"


@given(cmd=_CMD)
@settings(max_examples=300, deadline=2000)
def test_classify_command_empty_prefix_safe(cmd: str) -> None:
    """Adding whitespace around a command must not change the tier."""
    bare = classify_command(cmd.strip())
    padded = classify_command(f"  {cmd.strip()}  ")
    assert bare == padded, (
        f"Whitespace changed tier: strip={bare}, padded={padded} for input {cmd!r}"
    )


# ---------------------------------------------------------------------------
# _normalize_command — whitespace cleanup
# ---------------------------------------------------------------------------


@given(cmd=_CMD)
@settings(max_examples=300, deadline=2000)
def test_normalize_command_returns_str(cmd: str) -> None:
    """_normalize_command must always return a string."""
    result = _normalize_command(cmd)
    assert isinstance(result, str)


@given(cmd=_CMD)
@settings(max_examples=300, deadline=2000)
def test_normalize_command_no_leading_trailing_whitespace(cmd: str) -> None:
    """Normalized output has no leading/trailing whitespace."""
    result = _normalize_command(cmd)
    assert result == result.strip()


@given(cmd=_CMD)
@settings(max_examples=300, deadline=2000)
def test_normalize_command_no_double_spaces(cmd: str) -> None:
    """Normalized output has no consecutive spaces."""
    result = _normalize_command(cmd)
    assert "  " not in result


@given(cmd=_CMD)
@settings(max_examples=200, deadline=2000)
def test_normalize_command_idempotent(cmd: str) -> None:
    """Normalizing twice gives the same result as normalizing once.

    Idempotent means 'applying it again changes nothing' — like pressing
    the 'sort' button on an already-sorted list.
    """
    once = _normalize_command(cmd)
    twice = _normalize_command(once)
    assert once == twice


# ---------------------------------------------------------------------------
# _detect_evasion — shell evasion pattern detection
# ---------------------------------------------------------------------------


@given(cmd=_CMD)
@settings(max_examples=500, deadline=2000)
def test_detect_evasion_returns_str_or_none(cmd: str) -> None:
    """_detect_evasion must return either a string (description) or None."""
    result = _detect_evasion(cmd)
    assert result is None or isinstance(result, str)


# ---------------------------------------------------------------------------
# _is_safe_command — read-only allowlist check
# ---------------------------------------------------------------------------


@given(cmd=_CMD)
@settings(max_examples=500, deadline=2000)
def test_is_safe_command_returns_bool(cmd: str) -> None:
    """_is_safe_command must always return a bool."""
    result = _is_safe_command(cmd)
    assert isinstance(result, bool)


def test_is_safe_command_empty_string_is_not_safe() -> None:
    """An empty string should not be classified as safe."""
    assert _is_safe_command("") is False


def test_is_safe_command_whitespace_only_is_not_safe() -> None:
    """Whitespace-only input should not be safe."""
    assert _is_safe_command("   ") is False


# ---------------------------------------------------------------------------
# _canonicalize_path — path expansion and normalization
# ---------------------------------------------------------------------------


@given(path=text(min_size=0, max_size=200))
@settings(max_examples=300, deadline=2000)
def test_canonicalize_path_returns_str(path: str) -> None:
    """_canonicalize_path must always return a string."""
    result = _canonicalize_path(path)
    assert isinstance(result, str)


@given(path=text(min_size=1, max_size=200, alphabet="abcdefghijklmnopqrstuvwxyz/._-~"))
@settings(max_examples=300, deadline=2000)
def test_canonicalize_path_returns_absolute(path: str) -> None:
    """Canonicalized paths are always absolute (start with /)."""
    result = _canonicalize_path(path)
    assert result.startswith("/"), f"Not absolute: {result!r} from {path!r}"


@given(path=text(min_size=1, max_size=200, alphabet="abcdefghijklmnopqrstuvwxyz/._-~"))
@settings(max_examples=200, deadline=2000)
def test_canonicalize_path_no_double_slashes(path: str) -> None:
    """Canonicalized paths have no // sequences (resolved by os.path.realpath)."""
    result = _canonicalize_path(path)
    assert "//" not in result, f"Double slash in: {result!r}"


# ---------------------------------------------------------------------------
# tier_for — the Judge's public dispatch for action types
# ---------------------------------------------------------------------------


@given(detail=_CMD)
@settings(max_examples=300, deadline=2000)
def test_tier_for_run_command_matches_classify(detail: str) -> None:
    """tier_for('run_command', X) must equal classify_command(X).

    This verifies that the dispatch layer doesn't diverge from the
    classification layer.
    """
    assert tier_for("run_command", detail) == classify_command(detail)


@given(detail=text(min_size=0, max_size=200))
@settings(max_examples=300, deadline=2000)
def test_tier_for_always_returns_valid_tier(detail: str) -> None:
    """tier_for must return 0-3 for any action type."""
    for action in ("run_command", "read_file", "list_dir", "write_file", "search_kb"):
        tier = tier_for(action, detail)
        assert isinstance(tier, int)
        assert 0 <= tier <= 3, f"tier_for({action!r}, {detail!r}) = {tier}"


# ---------------------------------------------------------------------------
# Compound invariant: dangerous commands are never tier 0
# ---------------------------------------------------------------------------


def test_known_dangerous_commands_never_tier_0() -> None:
    """Explicit check: known dangerous patterns must classify above tier 0."""
    dangerous = [
        "rm -rf /",
        "mkfs.ext4 /dev/sda",
        "dd if=/dev/zero of=/dev/sda",
        ":(){ :|:& };:",
        "chmod 777 /etc/shadow",
    ]
    for cmd in dangerous:
        tier = classify_command(cmd)
        assert tier > 0, f"{cmd!r} classified as tier {tier} — should be > 0"
