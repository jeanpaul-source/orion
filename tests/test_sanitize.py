"""Tests for hal/sanitize.py — tool-call artifact detection and CJK language-leak handling.

Covers:
- is_tool_call_artifact() — existing, tested here for completeness.
- has_excessive_cjk() — Qwen Chinese token leakage detection.
- strip_cjk_lines() — per-line CJK cleanup preserving English content.

All tests are offline — no external services needed.
Run with: pytest tests/test_sanitize.py -v
"""

import pytest

from hal.sanitize import (
    has_excessive_cjk,
    is_tool_call_artifact,
    strip_cjk_lines,
    strip_tool_call_artifacts,
)

# ---------------------------------------------------------------------------
# is_tool_call_artifact — existing behavior
# ---------------------------------------------------------------------------


class TestIsToolCallArtifact:
    """Verify detection of tool-call JSON leaked into prose."""

    def test_bare_tool_call_json(self):
        """Bare JSON with "name" + "arguments" keys is a tool-call artifact."""
        text = '{"name": "get_metrics", "arguments": {}}'
        assert is_tool_call_artifact(text) is True

    def test_fenced_tool_call(self):
        """```json fenced tool call is detected."""
        text = '```json\n{"name": "run_command", "arguments": {"command": "ls"}}\n```'
        assert is_tool_call_artifact(text) is True

    def test_normal_json_not_flagged(self):
        """JSON without tool-call structure is not flagged."""
        assert is_tool_call_artifact('{"status": "ok", "code": 200}') is False

    def test_plain_english_not_flagged(self):
        """Normal English prose is not flagged."""
        assert is_tool_call_artifact("The CPU is at 40% usage.") is False

    def test_empty_string(self):
        assert is_tool_call_artifact("") is False


# ---------------------------------------------------------------------------
# strip_tool_call_artifacts — existing behavior
# ---------------------------------------------------------------------------


class TestStripToolCallArtifacts:
    """Verify removal of tool-call artifacts from mixed text."""

    def test_strips_bare_artifact(self):
        text = 'Here is the info: {"name": "get_metrics", "arguments": {}}'
        result = strip_tool_call_artifacts(text)
        assert "get_metrics" not in result
        assert "Here is the info:" in result

    def test_preserves_normal_json(self):
        text = 'Status: {"status": "ok", "code": 200}'
        result = strip_tool_call_artifacts(text)
        assert '"status": "ok"' in result

    def test_clean_text_unchanged(self):
        text = "Everything looks fine."
        assert strip_tool_call_artifacts(text) == text


# ---------------------------------------------------------------------------
# has_excessive_cjk — CJK language leak detection
# ---------------------------------------------------------------------------


# Sample strings for parametrized tests.
# Default threshold is 0.15 (15% of non-whitespace characters are CJK).
CJK_POSITIVE = [
    # Pure Chinese text — 100% CJK ratio
    "这是一段完全中文的文本，用来测试检测功能。",
    # Mixed text where Chinese dominates (~60% CJK)
    "The lab is 运行正常。所有服务都在线。CPU使用率为35%。内存使用稳定。",
    # Short burst of Chinese with minimal English
    "好的，我来检查一下。",
]

CJK_NEGATIVE = [
    # Pure English
    "The CPU is running at 40% usage. Everything looks fine.",
    # Empty string
    "",
    # English with a single quoted CJK term (well under 15%)
    "The process name is 'kubectl' (命令 means command).",
    # Technical text with no CJK
    "systemctl status vllm.service\n● vllm.service - vLLM\n   Active: active (running)",
    # JSON data (no CJK)
    '{"status": "ok", "uptime": "3 days"}',
]


class TestHasExcessiveCJK:
    """Verify CJK detection with the default 15% threshold."""

    @pytest.mark.parametrize("text", CJK_POSITIVE)
    def test_detects_cjk_heavy_text(self, text: str):
        """Text with >15% CJK characters should be flagged."""
        assert has_excessive_cjk(text) is True, f"Expected CJK-positive: {text!r}"

    @pytest.mark.parametrize("text", CJK_NEGATIVE)
    def test_passes_english_text(self, text: str):
        """English text (or empty) should not be flagged."""
        assert has_excessive_cjk(text) is False, f"False positive: {text!r}"

    def test_custom_threshold(self):
        """Custom threshold changes detection sensitivity."""
        # Text with ~20% CJK
        text = "Hello world 你好世界"
        # Very strict threshold (5%) should flag it
        assert has_excessive_cjk(text, threshold=0.05) is True
        # Very lenient threshold (90%) should not
        assert has_excessive_cjk(text, threshold=0.90) is False

    def test_whitespace_only(self):
        """Whitespace-only string should not trigger (no characters to measure)."""
        assert has_excessive_cjk("   \n\t  ") is False

    def test_cjk_punctuation_counted(self):
        """Fullwidth CJK punctuation (like ，。) counts toward the CJK ratio.

        This matters because Qwen leaks Chinese punctuation alongside ideographs.
        """
        # All fullwidth punctuation
        text = "，。、；：「」"
        assert has_excessive_cjk(text) is True


# ---------------------------------------------------------------------------
# strip_cjk_lines — per-line cleanup
# ---------------------------------------------------------------------------


class TestStripCJKLines:
    """Verify line-level CJK cleanup preserves English content."""

    def test_removes_pure_chinese_lines(self):
        """Lines that are fully Chinese should be removed."""
        text = "Lab status is OK.\n这是中文行。\nCPU at 35%."
        result = strip_cjk_lines(text)
        assert "Lab status is OK." in result
        assert "CPU at 35%." in result
        assert "中文" not in result

    def test_preserves_english_lines(self):
        """Pure English text should pass through unchanged."""
        text = "Everything looks fine.\nNo issues detected."
        assert strip_cjk_lines(text) == text

    def test_mixed_line_kept_if_mostly_english(self):
        """A line with <50% CJK characters is kept (e.g., one quoted term)."""
        text = "The service is running (命令 means command) on port 8000."
        result = strip_cjk_lines(text)
        assert "service is running" in result

    def test_collapses_blank_lines_after_removal(self):
        """Removing CJK lines shouldn't leave triple-blank-line gaps."""
        text = "Line one.\n\n这是中文。\n\n\n另一行中文。\n\nLine two."
        result = strip_cjk_lines(text)
        assert "\n\n\n" not in result
        assert "Line one." in result
        assert "Line two." in result

    def test_all_cjk_returns_empty(self):
        """If every line is CJK, result should be empty."""
        text = "这是第一行。\n这是第二行。\n这是第三行。"
        result = strip_cjk_lines(text)
        assert result == ""

    def test_empty_string(self):
        assert strip_cjk_lines("") == ""

    def test_real_world_mixed_response(self):
        """Simulates a real Qwen mixed-language response.

        The LLM starts in English, switches to Chinese mid-response, then
        occasionally returns to English.  strip_cjk_lines should keep the
        English parts and drop the Chinese parts.
        """
        text = (
            "The lab is running normally.\n"
            "所有服务都在线运行。\n"
            "CPU usage is at 35%.\n"
            "内存使用率为45%，在正常范围内。\n"
            "Disk usage: root 62%, docker 45%.\n"
            "没有发现安全警告。"
        )
        result = strip_cjk_lines(text)
        assert "The lab is running normally." in result
        assert "CPU usage is at 35%." in result
        assert "Disk usage:" in result
        # CJK lines should be gone
        assert "所有服务" not in result
        assert "内存使用率" not in result
        assert "没有发现" not in result
