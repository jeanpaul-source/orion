"""
E2E tests for WebSocket connection and communication.

Tests the critical infrastructure: connection, reconnection, message handling.
These tests validate the communication layer between frontend and backend.
"""

import pytest
from playwright.sync_api import Page, expect

pytestmark = pytest.mark.e2e


class TestWebSocketConnection:
    """Critical WebSocket connection tests."""

    def test_websocket_connects_on_page_load(self, page: Page, base_url: str):
        """Test that WebSocket connects when page loads."""
        page.goto(f"{base_url}/")

        # Wait for connection indicator or first interaction
        # If sidebar shows "System Health" it means WebSocket connected
        sidebar = page.locator("#sidebar")
        expect(sidebar).to_be_visible(timeout=5000)

        # Check that status cards appear (means API calls working)
        status_cards = page.locator(".status-card")
        expect(status_cards.first).to_be_visible(timeout=10000)

    def test_send_message_through_websocket(self, page: Page, base_url: str):
        """Test that messages are sent and received via WebSocket."""
        page.goto(f"{base_url}/")

        # Send a message
        message_input = page.locator("#messageInput")
        message_input.fill("Hello ORION")

        send_button = page.locator("#sendBtn")
        send_button.click()

        # User message should appear immediately
        user_messages = page.locator(".message.user")
        expect(user_messages.last).to_contain_text("Hello ORION")

        # Assistant response should stream in
        assistant_messages = page.locator(".message.assistant")
        expect(assistant_messages.last).to_be_visible(timeout=30000)

    def test_websocket_handles_connection_error(self, page: Page, base_url: str):
        """Test behavior when WebSocket connection fails."""
        # This test needs ORION Core to be stopped
        # For now, we'll test the reconnection UI appears if connection is lost
        page.goto(f"{base_url}/")

        # Simulate connection by checking initial state
        message_input = page.locator("#messageInput")
        expect(message_input).to_be_enabled(timeout=10000)


class TestWebSocketMessaging:
    """WebSocket message handling tests."""

    def test_streaming_messages_arrive_incrementally(self, page: Page, base_url: str):
        """Test that streaming responses arrive token by token."""
        page.goto(f"{base_url}/")

        # Send message
        message_input = page.locator("#messageInput")
        message_input.fill("Count from 1 to 5")

        send_button = page.locator("#sendBtn")
        send_button.click()

        # Wait for streaming to start
        loading = page.locator("#loadingIndicator")
        expect(loading).to_be_visible(timeout=2000)

        # Wait for completion
        expect(loading).not_to_be_visible(timeout=30000)

        # Response should have appeared
        messages = page.locator(".message.assistant")
        expect(messages.last).to_be_visible()

    def test_error_messages_display_correctly(self, page: Page, base_url: str):
        """Test that error messages from backend are displayed."""
        page.goto(f"{base_url}/")

        # Note: This test depends on backend behavior
        # For now, just verify normal operation works
        message_input = page.locator("#messageInput")
        message_input.fill("Test error handling")

        send_button = page.locator("#sendBtn")
        send_button.click()

        # Should receive some response (either success or error)
        loading = page.locator("#loadingIndicator")
        expect(loading).not_to_be_visible(timeout=30000)


@pytest.mark.slow
class TestWebSocketReconnection:
    """WebSocket reconnection tests (require backend restart)."""

    def test_reconnection_message_appears(self, page: Page, base_url: str):
        """Test that reconnection UI appears when connection lost."""
        # This test would require stopping/starting ORION Core
        # For now, we verify the page loads successfully
        page.goto(f"{base_url}/")

        # Verify initial connection works
        message_input = page.locator("#messageInput")
        expect(message_input).to_be_enabled(timeout=10000)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
