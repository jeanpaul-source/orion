"""
E2E tests for App initialization and integration.

Tests that all components wire together correctly on startup.
Validates global keyboard shortcuts and component initialization.
"""

import pytest
from playwright.sync_api import Page, expect

pytestmark = pytest.mark.e2e


class TestAppInitialization:
    """Critical app startup tests."""

    def test_app_loads_successfully(self, page: Page, base_url: str):
        """Test that app initializes without errors."""
        page.goto(f"{base_url}/")

        # Should see main chat interface
        chat_panel = page.locator("#chatPanel")
        expect(chat_panel).to_be_visible(timeout=5000)

        # Should see sidebar
        sidebar = page.locator("#sidebar")
        expect(sidebar).to_be_visible()

        # Should see message input
        message_input = page.locator("#messageInput")
        expect(message_input).to_be_enabled()

    def test_all_components_present(self, page: Page, base_url: str):
        """Test that all major components are present on load."""
        page.goto(f"{base_url}/")

        # Chat components
        expect(page.locator("#messagesContainer")).to_be_visible()
        expect(page.locator("#messageInput")).to_be_visible()
        expect(page.locator("#sendBtn")).to_be_visible()

        # Sidebar components
        expect(page.locator("#sidebar")).to_be_visible()
        expect(page.locator(".status-card").first).to_be_visible(timeout=10000)

        # Quick start hints should be visible initially
        hints = page.locator(".hint-btn")
        assert hints.count() == 4, "Should have 4 quick start hints"

    def test_system_metrics_load(self, page: Page, base_url: str):
        """Test that system metrics are fetched and displayed."""
        page.goto(f"{base_url}/")

        # Wait for sidebar to load data
        status_cards = page.locator(".status-card")
        expect(status_cards.first).to_be_visible(timeout=10000)

        # Should have at least 3 status cards (vLLM, Qdrant, GPU/Disk)
        assert status_cards.count() >= 3, "Not enough status cards loaded"


class TestGlobalKeyboardShortcuts:
    """Global keyboard shortcut tests."""

    def test_cmd_k_opens_command_palette(self, page: Page, base_url: str):
        """Test Cmd+K opens command palette."""
        page.goto(f"{base_url}/")

        # Press Cmd+K
        page.keyboard.press("Meta+k")

        # Command palette should be visible
        palette = page.locator("#commandPalette")
        expect(palette).to_be_visible()

        # Input should be focused
        palette_input = page.locator("#commandPaletteInput")
        expect(palette_input).to_be_focused()

    def test_cmd_l_clears_conversation(self, page: Page, base_url: str):
        """Test Cmd+L clears conversation."""
        page.goto(f"{base_url}/")

        # Send a message first
        message_input = page.locator("#messageInput")
        message_input.fill("Test message")

        send_button = page.locator("#sendBtn")
        send_button.click()

        # Wait for response
        loading = page.locator("#loadingIndicator")
        expect(loading).not_to_be_visible(timeout=30000)

        # Should have messages
        messages = page.locator(".message")
        initial_count = messages.count()
        assert initial_count > 0, "No messages to clear"

        # Press Cmd+L
        page.keyboard.press("Meta+l")

        # Messages should be cleared
        expect(messages).to_have_count(0)

        # Quick start hints should reappear
        hints = page.locator(".hint-btn")
        expect(hints.first).to_be_visible()

    def test_cmd_b_toggles_sidebar(self, page: Page, base_url: str):
        """Test Cmd+B toggles sidebar visibility."""
        page.goto(f"{base_url}/")

        sidebar = page.locator("#sidebar")

        # Sidebar should be visible initially
        expect(sidebar).to_be_visible()

        # Press Cmd+B to hide
        page.keyboard.press("Meta+b")

        # Sidebar should be hidden
        expect(sidebar).to_be_hidden()

        # Press Cmd+B again to show
        page.keyboard.press("Meta+b")

        # Sidebar should be visible again
        expect(sidebar).to_be_visible()


class TestComponentWiring:
    """Test that components communicate correctly."""

    def test_message_input_to_chat_display(self, page: Page, base_url: str):
        """Test message flow: input → send → display."""
        page.goto(f"{base_url}/")

        test_message = "Integration test message"

        # Type message
        message_input = page.locator("#messageInput")
        message_input.fill(test_message)

        # Send
        send_button = page.locator("#sendBtn")
        send_button.click()

        # User message should appear
        user_messages = page.locator(".message.user")
        expect(user_messages.last).to_contain_text(test_message)

        # Assistant response should appear
        assistant_messages = page.locator(".message.assistant")
        expect(assistant_messages.last).to_be_visible(timeout=30000)

    def test_quick_hints_disappear_after_first_message(self, page: Page, base_url: str):
        """Test that quick start hints disappear after first message."""
        page.goto(f"{base_url}/")

        # Hints should be visible
        hints = page.locator(".hint-btn")
        expect(hints.first).to_be_visible()

        # Send a message
        message_input = page.locator("#messageInput")
        message_input.fill("Test")

        send_button = page.locator("#sendBtn")
        send_button.click()

        # Hints should be hidden
        expect(hints.first).to_be_hidden()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
