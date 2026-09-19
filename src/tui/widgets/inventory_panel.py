"""Inventory panel showing the agent's current inventory, grouped like NetHack's `i` menu."""

from rich.text import Text
from textual.app import ComposeResult
from textual.containers import VerticalScroll
from textual.widgets import Static

from src.api.models import BUCStatus, Item, ObjectClass

from ..events import GameStateUpdated

# NetHack's default pack order and class headings
_CLASS_ORDER = [
    (ObjectClass.COIN, "Coins"),
    (ObjectClass.AMULET, "Amulets"),
    (ObjectClass.WEAPON, "Weapons"),
    (ObjectClass.ARMOR, "Armor"),
    (ObjectClass.FOOD, "Comestibles"),
    (ObjectClass.SCROLL, "Scrolls"),
    (ObjectClass.SPELLBOOK, "Spellbooks"),
    (ObjectClass.POTION, "Potions"),
    (ObjectClass.RING, "Rings"),
    (ObjectClass.WAND, "Wands"),
    (ObjectClass.TOOL, "Tools"),
    (ObjectClass.GEM, "Gems/Stones"),
    (ObjectClass.ROCK, "Boulders/Statues"),
    (ObjectClass.BALL, "Iron Balls"),
    (ObjectClass.CHAIN, "Chains"),
    (ObjectClass.VENOM, "Venoms"),
]

_BUC_STYLES = {BUCStatus.CURSED: "red", BUCStatus.BLESSED: "cyan"}


class InventoryPanel(VerticalScroll):
    """
    Scrollable list of inventory items grouped by class.

    Equipped items are bold; cursed items red, blessed items cyan.
    """

    DEFAULT_CSS = """
    InventoryPanel {
        border: solid $primary;
        border-title-color: $text;
        padding: 0 1;
    }

    #inventory-content {
        width: 100%;
    }
    """

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self.border_title = "Inventory"
        self._last_key: tuple = ()

    def compose(self) -> ComposeResult:
        yield Static("(empty)", id="inventory-content")

    def on_game_state_updated(self, event: GameStateUpdated) -> None:
        """Refresh the list when the inventory changes."""
        if event.inventory is None:
            return
        key = tuple((i.slot, i.quantity, i.name) for i in event.inventory)
        if key == self._last_key:
            return
        self._last_key = key
        self.query_one("#inventory-content", Static).update(self._render_items(event.inventory))

    @staticmethod
    def _render_items(items: list[Item]) -> Text:
        if not items:
            return Text("(empty)", style="dim italic")

        text = Text()
        known = {cls for cls, _ in _CLASS_ORDER}
        groups = [(heading, [i for i in items if i.object_class == cls]) for cls, heading in _CLASS_ORDER]
        groups.append(("Other", [i for i in items if i.object_class not in known]))

        for heading, group in groups:
            if not group:
                continue
            if text:
                text.append("\n")
            text.append(heading, style="bold underline")
            for item in group:
                style = _BUC_STYLES.get(item.buc_status, "")
                if item.equipped:
                    style = f"bold {style}".strip()
                name = f"{item.quantity} {item.name}" if item.quantity > 1 else item.name
                text.append(f"\n{item.slot} - ", style="dim")
                text.append(name, style=style)
        return text
