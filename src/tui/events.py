"""Custom Textual events for TUI updates."""

from dataclasses import dataclass
from typing import Optional

from textual.message import Message

from src.agent.parser import AgentDecision


@dataclass
class DecisionMade(Message):
    """Emitted when the agent makes a decision."""

    decision: AgentDecision
    turn: int
    timestamp: float

    def __init__(
        self,
        decision: AgentDecision,
        turn: int,
        timestamp: float,
    ) -> None:
        super().__init__()
        self.decision = decision
        self.turn = turn
        self.timestamp = timestamp


@dataclass
class SkillExecuted(Message):
    """Emitted when a skill finishes executing."""

    skill_name: str
    success: bool
    stopped_reason: str
    actions: int
    turns: int

    def __init__(
        self,
        skill_name: str,
        success: bool,
        stopped_reason: str,
        actions: int,
        turns: int,
    ) -> None:
        super().__init__()
        self.skill_name = skill_name
        self.success = success
        self.stopped_reason = stopped_reason
        self.actions = actions
        self.turns = turns


@dataclass
class GameStateUpdated(Message):
    """Emitted when game state changes."""

    screen: str
    hp: int
    max_hp: int
    turn: int
    dungeon_level: int
    depth: int
    xp_level: int
    score: int
    message: str
    hunger: str
    inventory: Optional[list]

    def __init__(
        self,
        screen: str,
        hp: int,
        max_hp: int,
        turn: int,
        dungeon_level: int,
        depth: int,
        xp_level: int,
        score: int,
        message: str,
        hunger: str,
        inventory: Optional[list] = None,
    ) -> None:
        super().__init__()
        self.screen = screen
        self.hp = hp
        self.max_hp = max_hp
        self.turn = turn
        self.dungeon_level = dungeon_level
        self.depth = depth
        self.xp_level = xp_level
        self.score = score
        self.message = message
        self.hunger = hunger
        self.inventory = inventory  # list[Item], or None if not captured


@dataclass
class AgentStatusChanged(Message):
    """Emitted when agent running/paused/stopped state changes."""

    status: str  # "running", "paused", "stopped", "error"
    error_message: Optional[str] = None

    def __init__(
        self,
        status: str,
        error_message: Optional[str] = None,
    ) -> None:
        super().__init__()
        self.status = status
        self.error_message = error_message


@dataclass
class GameMessages(Message):
    """Emitted with in-game messages recorded since the last GameMessages event."""

    messages: list[str]
    turn: int

    def __init__(self, messages: list[str], turn: int) -> None:
        super().__init__()
        self.messages = messages
        self.turn = turn
