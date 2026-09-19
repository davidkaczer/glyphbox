"""Message log widget showing the history of in-game messages."""

from rich.table import Table
from textual.widgets import RichLog

from ..events import GameMessages


class MessageLog(RichLog):
    """Scrolling log of NetHack messages, newest at the bottom, prefixed with the game turn."""

    DEFAULT_CSS = """
    MessageLog {
        background: $surface;
        border: solid $primary;
        border-title-color: $text;
        padding: 0 1;
        overflow-x: hidden;
        scrollbar-size-vertical: 1;
    }
    """

    def __init__(self, max_lines: int = 1000, **kwargs) -> None:
        # min_width=1 so lines wrap to the widget width instead of RichLog's 78-column default
        super().__init__(
            max_lines=max_lines, min_width=1, wrap=True, markup=False, auto_scroll=True, **kwargs
        )
        self.border_title = "Messages"

    def on_game_messages(self, event: GameMessages) -> None:
        """Append new messages."""
        for message in event.messages:
            # Two columns so wrapped messages stay indented past the turn number
            row = Table.grid(padding=(0, 1))
            row.add_column(style="dim", no_wrap=True, width=6)
            row.add_column()
            row.add_row(f"T{event.turn}", message)
            self.write(row, expand=True)
