"""Reasoning panel showing full LLM reasoning for current decision."""

from textual.containers import VerticalScroll
from textual.widgets import Static
from textual.app import ComposeResult
from rich.text import Text
from rich.syntax import Syntax

from ..events import DecisionMade


class ReasoningPanel(VerticalScroll):
    """
    Shows the full LLM reasoning for the current/selected decision.

    Scrollable panel with the complete reasoning text and
    optionally the raw LLM response.
    """

    DEFAULT_CSS = """
    ReasoningPanel {
        border: solid $primary;
        background: $surface;
        padding: 1;
    }

    ReasoningPanel > Static {
        width: 100%;
    }

    #reasoning-label {
        text-style: bold underline;
        margin-bottom: 1;
    }

    #reasoning-content {
        width: 100%;
    }

    #code-label {
        text-style: bold;
        color: $warning;
        margin-top: 1;
    }

    #code-content {
        width: 100%;
        margin-top: 0;
    }
    """

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)

    def compose(self) -> ComposeResult:
        """Compose the panel layout."""
        yield Static("Reasoning", id="reasoning-label")
        yield Static("Waiting for first decision...", id="reasoning-content")
        yield Static("", id="code-label")
        yield Static("", id="code-content")

    def show_error(self, message: str) -> None:
        """Show an agent error (e.g. LLM API failure) in place of the reasoning."""
        content = Text()
        content.append("Agent stopped with error:\n\n", style="red bold")
        content.append(message, style="red")
        self.query_one("#reasoning-content", Static).update(content)

    def on_decision_made(self, event: DecisionMade) -> None:
        """Update with new decision's reasoning."""
        decision = event.decision

        content = Text()

        # Header
        content.append(f"Turn {event.turn}", style="bold")
        content.append(" - ", style="dim")
        content.append(f"{decision.action.value.upper()}", style="bold cyan")
        content.append("\n")

        if decision.skill_name:
            content.append(f"Skill: {decision.skill_name}\n", style="green")

        if decision.params:
            params_str = ", ".join(f"{k}={v}" for k, v in decision.params.items())
            content.append(f"Params: {params_str}\n", style="dim")

        content.append("\n")

        # Main reasoning
        if decision.reasoning:
            content.append(decision.reasoning, style="white")
        else:
            content.append("(no reasoning provided)", style="dim italic")

        # Show validation error if present
        if decision.parse_error:
            content.append("\n\n")
            content.append("Parse Error: ", style="red bold")
            content.append(decision.parse_error, style="red")

        # Update the content widget
        content_widget = self.query_one("#reasoning-content", Static)
        content_widget.update(content)

        # Show code with syntax highlighting
        code_label = self.query_one("#code-label", Static)
        code_widget = self.query_one("#code-content", Static)

        if decision.code:
            code_label.update(Text("Generated Code:", style="yellow bold"))
            # Truncate very long code
            code_preview = decision.code[:2000]
            if len(decision.code) > 2000:
                code_preview += "\n# ... (truncated)"
            syntax = Syntax(
                code_preview,
                "python",
                theme="monokai",
                line_numbers=True,
                word_wrap=True,
            )
            code_widget.update(syntax)
        else:
            code_label.update("")
            code_widget.update("")

        # Scroll to top to see new content
        self.scroll_home()
