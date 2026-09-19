"""Main TUI application for watching the NetHack agent."""

import asyncio
import logging
import signal
from pathlib import Path
from typing import TYPE_CHECKING, Optional

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Container, Horizontal, Vertical
from textual.widgets import Header, Footer

from .events import AgentStatusChanged, DecisionMade, GameMessages, GameStateUpdated, SkillExecuted
from .logging import setup_run_logging, teardown_run_logging, get_log_file
from .runner import TUIAgentRunner
from .widgets import (
    ControlsWidget,
    GameScreenWidget,
    InventoryPanel,
    MessageLog,
    ReasoningPanel,
)

if TYPE_CHECKING:
    from src.agent import NetHackAgent
    from src.api import NetHackAPI

logger = logging.getLogger(__name__)


class NetHackTUI(App):
    """
    Main TUI application for watching the NetHack agent.

    Layout:
    - Left panel: Reasoning panel + Inventory (toggle with I)
    - Right panel (NetHack terminal width): Game screen + Message log
    - Bottom: Control buttons

    Keyboard shortcuts:
    - S: Start agent
    - Space: Pause/Resume
    - I: Show/hide inventory
    - Q: Quit
    """

    TITLE = "NetHack Agent TUI"
    SUB_TITLE = "Watch the AI play NetHack"

    CSS = """
    #main-container {
        layout: horizontal;
        height: 1fr;
    }

    #left-panel {
        width: 1fr;
        height: 100%;
    }

    /* Exactly as wide as the game screen; the reasoning panel takes the rest */
    #right-panel {
        width: 82;
        height: 100%;
    }

    #reasoning-panel {
        height: 1fr;
    }

    #inventory-panel {
        height: auto;
        max-height: 50%;
    }

    /* NetHack terminal size (80x24) plus a 1-cell border on each side */
    #game-screen {
        width: 82;
        height: 26;
    }

    #message-log {
        height: 1fr;
        min-height: 5;
    }
    """

    BINDINGS = [
        Binding("s", "start", "Start", show=True),
        Binding("space", "toggle_pause", "Pause/Resume", show=True),
        Binding("i", "toggle_inventory", "Inventory", show=True),
        Binding("q", "quit", "Quit", show=True),
    ]

    def __init__(
        self,
        agent: "NetHackAgent",
        api: "NetHackAPI",
        **kwargs,
    ) -> None:
        """
        Initialize the TUI.

        Args:
            agent: NetHackAgent instance
            api: NetHackAPI instance
        """
        super().__init__(**kwargs)
        self.agent = agent
        self.api = api
        self.runner: Optional[TUIAgentRunner] = None

    def compose(self) -> ComposeResult:
        """Compose the application layout."""
        yield Header()

        yield Container(
            Horizontal(
                Vertical(
                    ReasoningPanel(id="reasoning-panel"),
                    InventoryPanel(id="inventory-panel"),
                    id="left-panel",
                ),
                Vertical(
                    GameScreenWidget(id="game-screen"),
                    MessageLog(id="message-log"),
                    id="right-panel",
                ),
                id="main-container",
            ),
        )

        yield ControlsWidget(id="controls")
        yield Footer()

    async def on_mount(self) -> None:
        """Called when app is ready."""
        # Set up run-specific logging to a timestamped file
        self._log_file = setup_run_logging()

        # Create the runner
        self.runner = TUIAgentRunner(self.agent, self.api, self)

        # Set up Ctrl+C handler for emergency exit
        def handle_sigint(signum, frame):
            logger.info("SIGINT received, forcing exit")
            # Schedule the quit action on the event loop
            asyncio.get_event_loop().call_soon_threadsafe(
                lambda: asyncio.create_task(self._force_quit())
            )

        signal.signal(signal.SIGINT, handle_sigint)

        logger.info("TUI mounted and ready")
        logger.info(f"Logging to: {self._log_file}")

    # ==================== Event Handlers ====================
    # Forward events from runner to widgets

    def on_decision_made(self, event: DecisionMade) -> None:
        """Forward decision event to widgets."""
        try:
            reasoning_panel = self.query_one("#reasoning-panel", ReasoningPanel)
            reasoning_panel.on_decision_made(event)
        except Exception as e:
            logger.error(f"Error handling DecisionMade: {e}")

    def on_skill_executed(self, event: SkillExecuted) -> None:
        """Handle skill execution event (currently unused)."""
        pass

    def on_game_state_updated(self, event: GameStateUpdated) -> None:
        """Forward game state event to widgets."""
        try:
            game_screen = self.query_one("#game-screen", GameScreenWidget)
            game_screen.on_game_state_updated(event)

            inventory = self.query_one("#inventory-panel", InventoryPanel)
            inventory.on_game_state_updated(event)
        except Exception as e:
            logger.error(f"Error handling GameStateUpdated: {e}")

    def on_game_messages(self, event: GameMessages) -> None:
        """Forward new in-game messages to the message log."""
        try:
            message_log = self.query_one("#message-log", MessageLog)
            message_log.on_game_messages(event)
        except Exception as e:
            logger.error(f"Error handling GameMessages: {e}")

    def on_agent_status_changed(self, event: AgentStatusChanged) -> None:
        """Forward status change event to controls (and errors to the reasoning panel)."""
        try:
            controls = self.query_one("#controls", ControlsWidget)
            controls.on_agent_status_changed(event)
            if event.status == "error" and event.error_message:
                reasoning_panel = self.query_one("#reasoning-panel", ReasoningPanel)
                reasoning_panel.show_error(event.error_message)
        except Exception as e:
            logger.error(f"Error handling AgentStatusChanged: {e}")

    # ==================== Actions ====================

    def action_start(self) -> None:
        """Start the agent."""
        if self.runner and not self.runner.is_running:
            asyncio.create_task(self.runner.start())

    def action_toggle_pause(self) -> None:
        """Toggle pause state."""
        if self.runner and self.runner.is_running:
            if self.runner.is_paused:
                self.runner.resume()
            else:
                self.runner.pause()

    def action_toggle_inventory(self) -> None:
        """Show or hide the inventory panel."""
        panel = self.query_one("#inventory-panel", InventoryPanel)
        panel.display = not panel.display

    def action_stop(self) -> None:
        """Stop the agent."""
        if self.runner and self.runner.is_running:
            asyncio.create_task(self.runner.stop())

    async def action_quit(self) -> None:
        """Stop agent and quit."""
        if self.runner and self.runner.is_running:
            await self.runner.stop()

        # Clean up logging and report log file location
        log_file = get_log_file()
        teardown_run_logging()
        if log_file:
            # This will print after TUI exits
            self._final_log_file = log_file

        self.exit()

    async def _force_quit(self) -> None:
        """Force quit when Ctrl+C is pressed."""
        logger.info("Force quitting...")
        if self.runner and self.runner.is_running:
            # Cancel without waiting
            if self.runner._task:
                self.runner._task.cancel()
            if self.runner._screen_task:
                self.runner._screen_task.cancel()
            self.runner._running = False

        teardown_run_logging()
        self.exit()

    def on_unmount(self) -> None:
        """Called when app is unmounting."""
        teardown_run_logging()
