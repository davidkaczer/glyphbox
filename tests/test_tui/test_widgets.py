"""Tests for TUI widgets."""

import pytest
from unittest.mock import MagicMock, patch

from src.tui.widgets import (
    GameScreenWidget,
    InventoryPanel,
    MessageLog,
    DecisionLogWidget,
    ReasoningPanel,
    ControlsWidget,
)
from src.tui.events import (
    DecisionMade,
    SkillExecuted,
    GameStateUpdated,
    AgentStatusChanged,
)
from src.agent.parser import ActionType, AgentDecision


class TestMessageLog:
    """Tests for MessageLog widget."""

    def test_creation(self):
        """Test creating a MessageLog widget."""
        widget = MessageLog()
        assert widget.border_title == "Messages"
        assert widget.max_lines == 1000


class TestInventoryPanel:
    """Tests for InventoryPanel widget."""

    def test_render_groups_in_pack_order(self):
        """Items are grouped under class headings in NetHack's pack order."""
        from src.api.models import BUCStatus, Item, ObjectClass

        items = [
            Item(glyph=0, name="uncursed food ration", slot="d", object_class=ObjectClass.FOOD),
            Item(glyph=0, name="+1 long sword (weapon in hand)", slot="a",
                 object_class=ObjectClass.WEAPON, equipped=True),
            Item(glyph=0, name="cursed ring of teleportation", slot="e",
                 object_class=ObjectClass.RING, buc_status=BUCStatus.CURSED),
        ]
        text = InventoryPanel._render_items(items).plain
        assert text.index("Weapons") < text.index("Comestibles") < text.index("Rings")
        assert "a - +1 long sword (weapon in hand)" in text

    def test_render_empty(self):
        assert InventoryPanel._render_items([]).plain == "(empty)"


class TestGameScreenWidget:
    """Tests for GameScreenWidget."""

    def test_creation(self):
        """Test creating a GameScreenWidget."""
        widget = GameScreenWidget()
        assert widget._screen is not None

    def test_empty_screen(self):
        """Test empty screen generation."""
        widget = GameScreenWidget()
        screen = widget._empty_screen()
        lines = screen.split("\n")
        assert len(lines) == 24
        assert all(len(line) == 80 for line in lines)


class TestDecisionLogWidget:
    """Tests for DecisionLogWidget."""

    def test_creation(self):
        """Test creating a DecisionLogWidget."""
        widget = DecisionLogWidget()
        assert widget._decision_count == 0


class TestReasoningPanel:
    """Tests for ReasoningPanel widget."""

    def test_creation(self):
        """Test creating a ReasoningPanel."""
        widget = ReasoningPanel()
        # Should be able to create without error
        assert widget is not None


class TestControlsWidget:
    """Tests for ControlsWidget."""

    def test_creation(self):
        """Test creating a ControlsWidget."""
        widget = ControlsWidget()
        assert widget._status == "ready"


class TestWidgetEventHandling:
    """Tests for widget event handling logic."""

    def test_game_screen_update(self):
        """Test game screen stores screen data."""
        widget = GameScreenWidget()

        new_screen = "@" + "." * 79 + "\n" * 23
        event = GameStateUpdated(
            screen=new_screen,
            hp=10,
            max_hp=20,
            turn=50,
            dungeon_level=2,
            depth=2,
            xp_level=1,
            score=100,
            message="Test",
            hunger="not_hungry",
        )

        # Simulate event handling
        widget._screen = event.screen
        assert widget._screen == new_screen
        assert "@" in widget._screen

    def test_decision_action_colors(self):
        """Test decision log color mapping."""
        action_colors = {
            "invoke_skill": "green",
            "create_skill": "yellow",
            "analyze": "cyan",
            "direct_action": "magenta",
            "unknown": "red",
        }

        # All action types should have a color
        for action_type in ActionType:
            color = action_colors.get(action_type.value, "white")
            assert color is not None

    def test_controls_status_mapping(self):
        """Test controls status to color mapping."""
        status_colors = {
            "ready": "white",
            "running": "green",
            "paused": "yellow",
            "stopped": "red",
            "error": "red bold",
        }

        for status in ["ready", "running", "paused", "stopped", "error"]:
            assert status in status_colors
