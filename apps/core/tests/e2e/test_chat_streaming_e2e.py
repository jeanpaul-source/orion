"""
E2E tests for Chat Streaming functionality.

Tests the critical path: user sends message → streaming response received.
Validates token-by-token rendering, progress indicators, and markdown parsing.
"""

import pytest
from playwright.sync_api import Page, expect

pytestmark = pytest.mark.e2e


class TestChatStreaming:
    """Critical chat streaming functionality."""

    def test_send_message_receives_streaming_response(self, page: Page, base_url: str):
        """Test basic streaming: send message → receive tokens."""
        page.goto(f"{base_url}/")

        # Type a simple question
        message_input = page.locator("#messageInput")
        message_input.fill("What is Docker?")

        # Click send
        send_button = page.locator("#sendBtn")
        send_button.click()

        # Should show loading indicator briefly
        loading = page.locator("#loadingIndicator")
        expect(loading).to_be_visible(timeout=1000)

        # Wait for response to appear
        messages = page.locator(".message.assistant")
        expect(messages.last).to_be_visible(timeout=30000)

        # Response should have content
        response_text = messages.last.text_content()
        assert len(response_text) > 10, "Response too short"
        assert "docker" in response_text.lower(), "Response doesn't mention Docker"

    def test_progress_indicators_show_during_streaming(self, page: Page, base_url: str):
        """Test that progress messages appear during processing."""
        page.goto(f"{base_url}/")

        message_input = page.locator("#messageInput")
        message_input.fill("What are Kubernetes best practices?")

        send_button = page.locator("#sendBtn")
        send_button.click()

        # Should see loading indicator
        loading = page.locator("#loadingIndicator")
        expect(loading).to_be_visible(timeout=2000)

        # Wait for streaming to complete
        expect(loading).not_to_be_visible(timeout=30000)

        # Should have received a response
        messages = page.locator(".message.assistant")
        expect(messages.last).to_be_visible()

    def test_markdown_renders_in_response(self, page: Page, base_url: str):
        """Test that markdown in responses is properly rendered."""
        page.goto(f"{base_url}/")

        # Ask for something that typically includes code blocks
        message_input = page.locator("#messageInput")
        message_input.fill("Show me a Python hello world")

        send_button = page.locator("#sendBtn")
        send_button.click()

        # Wait for response
        messages = page.locator(".message.assistant")
        expect(messages.last).to_be_visible(timeout=30000)

        # Check for markdown-rendered elements (code blocks, paragraphs, etc.)
        response = messages.last

        # Should have markdown-rendered content (p tags, code blocks, etc.)
        paragraphs = response.locator("p")
        assert paragraphs.count() > 0, "No paragraphs found - markdown not rendered"

    def test_quick_start_hints_work(self, page: Page, base_url: str):
        """Test that clicking quick start hints sends the message."""
        page.goto(f"{base_url}/")

        # Click a quick start hint button
        hint_button = page.locator(".hint-btn").first
        hint_button.click()

        # Should send the message and show loading
        loading = page.locator("#loadingIndicator")
        expect(loading).to_be_visible(timeout=2000)

        # Should receive response
        messages = page.locator(".message.assistant")
        expect(messages.last).to_be_visible(timeout=30000)

    def test_input_disabled_during_streaming(self, page: Page, base_url: str):
        """Test that input is disabled while waiting for response."""
        page.goto(f"{base_url}/")

        message_input = page.locator("#messageInput")
        send_button = page.locator("#sendBtn")

        # Send message
        message_input.fill("Test message")
        send_button.click()

        # Input should be disabled while waiting
        expect(message_input).to_be_disabled(timeout=2000)
        expect(send_button).to_be_disabled()

        # Wait for response to complete
        loading = page.locator("#loadingIndicator")
        expect(loading).not_to_be_visible(timeout=30000)

        # Input should be enabled again
        expect(message_input).to_be_enabled()


@pytest.mark.slow
class TestChatAdvanced:
    """Advanced chat features (slower tests)."""

    def test_multiple_messages_in_conversation(self, page: Page, base_url: str):
        """Test sending multiple messages in sequence."""
        page.goto(f"{base_url}/")

        message_input = page.locator("#messageInput")
        send_button = page.locator("#sendBtn")

        # Send first message
        message_input.fill("What is Python?")
        send_button.click()

        # Wait for response
        loading = page.locator("#loadingIndicator")
        expect(loading).not_to_be_visible(timeout=30000)

        # Send follow-up message
        message_input.fill("Tell me more")
        send_button.click()

        # Should get second response
        expect(loading).not_to_be_visible(timeout=30000)

        # Should have at least 4 messages (2 user, 2 assistant)
        all_messages = page.locator(".message")
        assert all_messages.count() >= 4, "Not enough messages in conversation"

    def test_clear_conversation(self, page: Page, base_url: str):
        """Test that clear conversation works."""
        page.goto(f"{base_url}/")

        # Send a message
        message_input = page.locator("#messageInput")
        message_input.fill("Test message")

        send_button = page.locator("#sendBtn")
        send_button.click()

        # Wait for response
        loading = page.locator("#loadingIndicator")
        expect(loading).not_to_be_visible(timeout=30000)

        # Clear conversation (via command palette or button)
        page.keyboard.press("Meta+k")
        palette_input = page.locator("#commandPaletteInput")
        palette_input.fill("clear")
        page.keyboard.press("Enter")

        # Messages should be cleared
        messages = page.locator(".message")
        expect(messages).to_have_count(0)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
