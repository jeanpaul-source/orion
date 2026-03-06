"""Offline unit tests for custom eval evaluators.

Tests eval/evaluate.py evaluator classes directly — no LLM, no vLLM,
no azure.ai.evaluation needed.  Each test verifies one scoring decision
with a clear pass/fail boundary.
"""

from __future__ import annotations

from eval.evaluate import (
    AutonomyEvaluator,
    HalIdentityEvaluator,
    IntentAccuracyEvaluator,
    NoRawJsonEvaluator,
    NoToolSimulationEvaluator,
    ResponseLengthEvaluator,
    WebToolAccuracyEvaluator,
)

# ── NoRawJsonEvaluator ──────────────────────────────────────────────────────


class TestNoRawJson:
    """Detects raw tool-call JSON leaked as the response text (B1 failure)."""

    def setup_method(self) -> None:
        self.evaluator = NoRawJsonEvaluator()

    def test_clean_prose_scores_1(self) -> None:
        """Normal English response should score 1.0 (no raw JSON)."""
        result = self.evaluator(response="The CPU is at 42% usage.")
        assert result["no_raw_json"] == 1.0

    def test_raw_name_pattern_scores_0(self) -> None:
        """Response containing {"name": ...} pattern should score 0.0."""
        result = self.evaluator(response='{"name": "get_metrics", "arguments": {}}')
        assert result["no_raw_json"] == 0.0

    def test_raw_arguments_pattern_scores_0(self) -> None:
        """Response containing {"arguments": ...} pattern should score 0.0."""
        result = self.evaluator(response='{"arguments": {"query": "hello"}}')
        assert result["no_raw_json"] == 0.0

    def test_function_name_placeholder_scores_0(self) -> None:
        """<function-name> placeholder in response should score 0.0."""
        result = self.evaluator(response='{"name": "<function-name>"}')
        assert result["no_raw_json"] == 0.0


# ── HalIdentityEvaluator ────────────────────────────────────────────────────


class TestHalIdentity:
    """Detects identity override — model claims to be Qwen/Alibaba (B2)."""

    def setup_method(self) -> None:
        self.evaluator = HalIdentityEvaluator()

    def test_hal_identity_scores_1(self) -> None:
        """Response saying 'I am HAL' should pass."""
        result = self.evaluator(response="I'm HAL, your homelab assistant.")
        assert result["hal_identity"] == 1.0

    def test_qwen_identity_scores_0(self) -> None:
        """Response saying 'I'm Qwen' should fail."""
        result = self.evaluator(response="I'm Qwen, created by Alibaba Cloud.")
        assert result["hal_identity"] == 0.0

    def test_alibaba_mention_scores_0(self) -> None:
        """Response mentioning 'Alibaba Cloud' should fail."""
        result = self.evaluator(response="I was created by Alibaba Cloud.")
        assert result["hal_identity"] == 0.0

    def test_case_insensitive(self) -> None:
        """Detection should be case-insensitive."""
        result = self.evaluator(response="I AM QWEN.")
        assert result["hal_identity"] == 0.0


# ── IntentAccuracyEvaluator ─────────────────────────────────────────────────


class TestIntentAccuracy:
    """Checks the intent classifier routed to the expected category."""

    def setup_method(self) -> None:
        self.evaluator = IntentAccuracyEvaluator()

    def test_matching_intent_scores_1(self) -> None:
        """Exact match on intent should score 1.0."""
        result = self.evaluator(intent="health", expected_intent="health")
        assert result["intent_accuracy"] == 1.0

    def test_mismatched_intent_scores_0(self) -> None:
        """Wrong intent should score 0.0."""
        result = self.evaluator(intent="fact", expected_intent="health")
        assert result["intent_accuracy"] == 0.0

    def test_agentic_always_passes(self) -> None:
        """expected_intent='agentic' is the fallback — always pass."""
        result = self.evaluator(intent="health", expected_intent="agentic")
        assert result["intent_accuracy"] == 1.0


# ── WebToolAccuracyEvaluator ────────────────────────────────────────────────


class TestWebToolAccuracy:
    """Checks web_search was called exactly when expected."""

    def setup_method(self) -> None:
        self.evaluator = WebToolAccuracyEvaluator()

    def test_null_expected_passes(self) -> None:
        """Rows without web_search_expected should always pass."""
        result = self.evaluator(tools_called=[], web_search_expected=None)
        assert result["web_tool_accuracy"] == 1.0

    def test_expected_true_with_web_search_scores_1(self) -> None:
        """web_search called when expected should score 1.0."""
        result = self.evaluator(tools_called=["web_search"], web_search_expected=True)
        assert result["web_tool_accuracy"] == 1.0

    def test_expected_true_without_web_search_scores_0(self) -> None:
        """web_search NOT called when expected should score 0.0."""
        result = self.evaluator(tools_called=[], web_search_expected=True)
        assert result["web_tool_accuracy"] == 0.0

    def test_expected_false_with_web_search_scores_0(self) -> None:
        """web_search called when NOT expected should score 0.0."""
        result = self.evaluator(tools_called=["web_search"], web_search_expected=False)
        assert result["web_tool_accuracy"] == 0.0

    def test_string_tools_parsed(self) -> None:
        """tools_called arriving as JSON string should still work."""
        result = self.evaluator(
            tools_called='["web_search", "search_kb"]',
            web_search_expected=True,
        )
        assert result["web_tool_accuracy"] == 1.0


# ── NoToolSimulationEvaluator ───────────────────────────────────────────────


class TestNoToolSimulation:
    """Detects fenced JSON tool-call blocks narrated in prose."""

    def setup_method(self) -> None:
        self.evaluator = NoToolSimulationEvaluator()

    def test_clean_prose_scores_1(self) -> None:
        """Normal response without fenced tool JSON should pass."""
        result = self.evaluator(response="Everything looks healthy.")
        assert result["no_tool_simulation"] == 1.0

    def test_simulated_tool_call_scores_0(self) -> None:
        """Fenced JSON with name+arguments keys should score 0.0."""
        bad = (
            "Let me check that for you.\n"
            "```json\n"
            '{"name": "get_metrics", "arguments": {}}\n'
            "```\n"
            "Here are the results."
        )
        result = self.evaluator(response=bad)
        assert result["no_tool_simulation"] == 0.0

    def test_real_json_code_block_passes(self) -> None:
        """Fenced JSON without name+arguments keys should pass.

        Real data like metrics or config shown in a code fence is fine.
        """
        ok = '```json\n{"cpu": 42, "mem": 8192}\n```'
        result = self.evaluator(response=ok)
        assert result["no_tool_simulation"] == 1.0

    def test_invalid_json_in_fence_passes(self) -> None:
        """Malformed JSON in a fence should not falsely trigger."""
        ok = "```json\n{not valid json}\n```"
        result = self.evaluator(response=ok)
        assert result["no_tool_simulation"] == 1.0

    def test_bare_json_without_fence_passes(self) -> None:
        """Bare JSON (no ``` fence) is caught by NoRawJson, not this.

        NoToolSimulation only detects fenced blocks.
        """
        bare = '{"name": "run_command", "arguments": {"command": "ls"}}'
        result = self.evaluator(response=bare)
        assert result["no_tool_simulation"] == 1.0


# ── ResponseLengthEvaluator ─────────────────────────────────────────────────


class TestResponseLength:
    """Checks responses are neither too short nor too long."""

    def setup_method(self) -> None:
        self.evaluator = ResponseLengthEvaluator()

    def test_normal_length_scores_1(self) -> None:
        """A 50-char response should pass."""
        result = self.evaluator(
            response="The lab is healthy and all services are running."
        )
        assert result["response_length"] == 1.0

    def test_too_short_scores_0(self) -> None:
        """A 3-char response like 'ok' should fail for non-trivial queries."""
        result = self.evaluator(response="ok")
        assert result["response_length"] == 0.0

    def test_too_long_scores_0(self) -> None:
        """A response exceeding 4000 chars should fail."""
        result = self.evaluator(response="x" * 4001)
        assert result["response_length"] == 0.0

    def test_trivial_skips_min_check(self) -> None:
        """Trivial queries (greetings) should pass even with short responses."""
        result = self.evaluator(response="Hey!", trivial=True)
        assert result["response_length"] == 1.0

    def test_trivial_string_true(self) -> None:
        """trivial='true' (string from JSONL) should behave like bool True."""
        result = self.evaluator(response="Hi!", trivial="true")
        assert result["response_length"] == 1.0

    def test_trivial_still_checks_max(self) -> None:
        """Even trivial queries should fail if response is excessively long."""
        result = self.evaluator(response="x" * 4001, trivial=True)
        assert result["response_length"] == 0.0

    def test_empty_response_scores_0(self) -> None:
        """Empty string should fail for non-trivial queries."""
        result = self.evaluator(response="")
        assert result["response_length"] == 0.0

    def test_exactly_min_passes(self) -> None:
        """Exactly 10 chars should pass (boundary)."""
        result = self.evaluator(response="1234567890")
        assert result["response_length"] == 1.0


# ── AutonomyEvaluator ───────────────────────────────────────────────────────


class TestAutonomyQuality:
    """Validates that autonomy-tagged responses contain specific findings."""

    def setup_method(self) -> None:
        self.evaluator = AutonomyEvaluator()

    def test_non_autonomy_always_passes(self) -> None:
        """Queries not tagged as autonomy should always score 1.0."""
        result = self.evaluator(response="I don't know", failure_case="B1")
        assert result["autonomy_quality"] == 1.0

    def test_autonomy_with_status_word_passes(self) -> None:
        """Autonomy response with 'healthy' should score 1.0."""
        result = self.evaluator(
            response="All components are healthy.",
            failure_case="autonomy",
        )
        assert result["autonomy_quality"] == 1.0

    def test_autonomy_with_component_name_passes(self) -> None:
        """Autonomy response mentioning 'pgvector' should score 1.0."""
        result = self.evaluator(
            response="pgvector is up and responding to queries.",
            failure_case="autonomy",
        )
        assert result["autonomy_quality"] == 1.0

    def test_autonomy_generic_response_fails(self) -> None:
        """Generic non-answer for an autonomy query should score 0.0."""
        result = self.evaluator(
            response="I'll look into that and get back to you.",
            failure_case="autonomy",
        )
        assert result["autonomy_quality"] == 0.0

    def test_autonomy_null_failure_case_passes(self) -> None:
        """None failure_case should pass (not an autonomy query)."""
        result = self.evaluator(
            response="Something vague.",
            failure_case=None,
        )
        assert result["autonomy_quality"] == 1.0
