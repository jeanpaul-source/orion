"""
End-to-End tests for Command Palette UI feature.

Uses Playwright to test the command palette in a real browser.
Tests keyboard shortcuts, fuzzy search, navigation, and action execution.
"""

import pytest
from playwright.sync_api import Page, expect

pytestmark = pytest.mark.e2e  # Mark all tests in this module as e2e


@pytest.fixture(scope="session")
def base_url():
    """Base URL for the ORION Core application."""
    return "http://localhost:5000"


class TestCommandPalette:
    """Test suite for Command Palette feature."""

    def test_command_palette_opens_with_cmd_k(self, page: Page, base_url: str):
        """Test that Cmd+K opens the command palette."""
        page.goto(f"{base_url}/")

        # Press Cmd+K (or Ctrl+K on Linux)
        page.keyboard.press("Meta+k")  # Use "Control+k" on Linux if needed

        # Command palette should be visible
        palette = page.locator(".command-palette-overlay")
        expect(palette).to_be_visible()

        # Input should be focused
        search_input = page.locator("#commandPaletteInput")
        expect(search_input).to_be_focused()

    def test_command_palette_shows_16_actions(self, page: Page, base_url: str):
        """Test that palette displays all 16 predefined actions."""
        page.goto(f"{base_url}/")
        page.keyboard.press("Meta+k")

        # Wait for actions to render
        actions = page.locator(".command-palette-action")
        expect(actions).to_have_count(16)

    def test_command_palette_fuzzy_search(self, page: Page, base_url: str):
        """Test fuzzy search filtering."""
        page.goto(f"{base_url}/")
        page.keyboard.press("Meta+k")

        # Type "status" in search
        search_input = page.locator("#commandPaletteInput")
        search_input.fill("status")

        # Should filter to actions containing "status"
        visible_actions = page.locator(".command-palette-action:visible")
        expect(visible_actions).to_have_count(1)  # Only "View system status"
        expect(visible_actions.first).to_contain_text("status")

    def test_command_palette_keyboard_navigation(self, page: Page, base_url: str):
        """Test arrow key navigation through actions."""
        page.goto(f"{base_url}/")
        page.keyboard.press("Meta+k")

        # First action should be selected by default
        first_action = page.locator(".command-palette-action.selected")
        expect(first_action).to_be_visible()

        # Press ArrowDown to move to next action
        page.keyboard.press("ArrowDown")

        # Second action should now be selected
        selected_actions = page.locator(".command-palette-action.selected")
        expect(selected_actions).to_have_count(1)

    def test_command_palette_closes_with_escape(self, page: Page, base_url: str):
        """Test that Escape key closes the palette."""
        page.goto(f"{base_url}/")
        page.keyboard.press("Meta+k")

        # Palette should be open
        palette = page.locator(".command-palette-overlay")
        expect(palette).to_be_visible()

        # Press Escape
        page.keyboard.press("Escape")

        # Palette should be closed
        expect(palette).not_to_be_visible()

    def test_command_palette_closes_on_outside_click(self, page: Page, base_url: str):
        """Test that clicking outside closes the palette."""
        page.goto(f"{base_url}/")
        page.keyboard.press("Meta+k")

        # Click outside the modal (on the overlay)
        overlay = page.locator(".command-palette-overlay")
        overlay.click(position={"x": 10, "y": 10})

        # Palette should be closed
        expect(overlay).not_to_be_visible()

    def test_command_palette_categories(self, page: Page, base_url: str):
        """Test that actions are grouped by category."""
        page.goto(f"{base_url}/")
        page.keyboard.press("Meta+k")

        # Should have 4 category headers
        categories = page.locator(".command-palette-category")
        expect(categories).to_have_count(4)

        # Check category names
        expect(categories.nth(0)).to_contain_text("Chat")
        expect(categories.nth(1)).to_contain_text("System")
        expect(categories.nth(2)).to_contain_text("Navigation")
        expect(categories.nth(3)).to_contain_text("Debug")


@pytest.mark.slow
class TestCommandPaletteActions:
    """Test actual action execution (requires full app context)."""

    def test_new_conversation_action(self, page: Page, base_url: str):
        """Test that 'New conversation' action works."""
        page.goto(f"{base_url}/")

        # Type a message first
        message_input = page.locator("#messageInput")
        message_input.fill("Test message")

        # Open palette and select "New conversation"
        page.keyboard.press("Meta+k")
        search_input = page.locator("#commandPaletteInput")
        search_input.fill("new conversation")
        page.keyboard.press("Enter")

        # Message input should be cleared
        expect(message_input).to_be_empty()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
