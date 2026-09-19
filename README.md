# Glyphbox

![Glyphbox](images/screenshot.png)

A NetHack harness that exposes a Python sandbox as the primary interface for LLMs to play NetHack. The LLM receives the full game screen each turn and responds with Python code that executes against a high-level game API.

## How It Works

```
LLM receives game screen each turn
    │
    │  responds with Python code via execute_code tool call
    ▼
Python Sandbox (restricted execution environment)
    │
    │  code calls methods on `nh` (NetHackAPI)
    ▼
NetHackAPI (high-level game interface)
    │
    │  translates to gymnasium actions
    ▼
NetHack Learning Environment (NLE)
    NetHack 3.6.7 simulator
```

Each turn, the LLM sees the full 24x80 ASCII game screen, game messages, and results from its previous actions. It writes Python code that runs in a sandboxed environment with access to `nh` — a NetHackAPI instance that wraps all game interactions into clean method calls.

## Setup

```bash
git clone <repo-url>
cd glyphbox
uv sync
```

Set an API key for your provider:

```bash
# OpenAI (default provider)
export OPENAI_API_KEY="your-key"

# Or OpenRouter (set agent.provider: "openrouter" in config/default.yaml)
export OPENROUTER_API_KEY="your-key"
```

Verify the setup:

```bash
uv run python -m src.cli verify
```

## Usage

```bash
# Watch the agent play in a TUI
uv run python -m src.cli watch

# Use a specific model
uv run python -m src.cli watch --model anthropic/claude-3-haiku-20240307

# Record the session with asciinema
uv run python -m src.cli watch --record

# Play back a recording
asciinema play data/recordings/run_2026-01-19_19-34-49.cast
```

### CLI Options

| Flag | Description |
|---|---|
| `--model`, `-m` | Override the LLM model |
| `--record`, `-r` | Record session with asciinema (saves to `data/recordings/`) |
| `--config`, `-c` | Path to config file (default: `config/default.yaml`) |
| `--log-level`, `-l` | `DEBUG`, `INFO`, `WARNING`, `ERROR` |

### TUI Controls

| Key | Action |
|---|---|
| `S` | Start the agent |
| `Space` | Pause / Resume |
| `Q` | Quit |

## The Sandbox

The LLM interacts with NetHack exclusively through an `execute_code` tool call. The submitted Python code runs in a restricted sandbox with these globals available:

| Name | Type | Description |
|---|---|---|
| `nh` | `NetHackAPI` | Game interface — all actions and queries |
| `Direction` | `Enum` | `N`, `S`, `E`, `W`, `NE`, `NW`, `SE`, `SW`, `UP`, `DOWN`, `SELF` |
| `Position` | `dataclass` | `(x, y)` coordinates with `.distance_to()`, `.direction_to()`, `.adjacent()` |
| `PathResult` | `dataclass` | Pathfinding result with `.path` and `.reason` |
| `PathStopReason` | `Enum` | Why pathfinding stopped |
| `TargetResult` | `dataclass` | Target search result with `.position` and `.success` |
| `HungerState` | `Enum` | `SATIATED`, `NOT_HUNGRY`, `HUNGRY`, `WEAK`, `FAINTING`, `FAINTED` |
| `random` | module | Python `random` module |

Standard builtins (`print`, `len`, `range`, `min`, `max`, `sorted`, `list`, `dict`, etc.) are available. Imports are forbidden — all needed types are pre-loaded.

### Security

Code is validated via AST inspection before execution:
- **Forbidden imports**: `os`, `sys`, `subprocess`, `socket`, `http`, `pickle`, `threading`, `multiprocessing`, etc.
- **Forbidden calls**: `exec`, `eval`, `compile`, `open`, `input`, `__import__`
- **Forbidden attributes**: `__class__`, `__bases__`, `__dict__`, `__globals__`, `__code__`
- **Timeout**: signal-based `SIGALRM` kills runaway code

### Example Code

What the LLM submits each turn:

```python
# Check health and eat if hungry
if nh.is_hungry:
    food = nh.get_food()
    if food:
        nh.eat(food[0].slot)
    else:
        nh.pray()
elif nh.has_adjacent_hostile:
    for monster in nh.get_adjacent_hostiles():
        direction = nh.position.direction_to(monster.position)
        nh.attack(direction)
else:
    nh.autoexplore()
```

## NetHackAPI Reference

All methods are synchronous. Actions consume game turns; queries do not.

### Properties

| Property | Type | Description |
|---|---|---|
| `nh.hp` | `int` | Current hit points |
| `nh.max_hp` | `int` | Maximum hit points |
| `nh.position` | `Position` | Current `(x, y)` |
| `nh.dungeon_level` | `int` | Current depth |
| `nh.turn` | `int` | Game turn counter |
| `nh.is_hungry` | `bool` | Hunger >= HUNGRY |
| `nh.is_weak` | `bool` | Hunger is WEAK or FAINTING |
| `nh.has_adjacent_hostile` | `bool` | Hostile monster in adjacent tile |
| `nh.turns_since_last_prayer` | `int` | Turns since last prayer |
| `nh.role` | `str` | Player class (e.g. `"Valkyrie"`) |
| `nh.is_done` | `bool` | Episode has ended |

### State Queries

```python
nh.get_stats()               # Stats: hp, max_hp, pw, ac, xp_level, gold, hunger, etc.
nh.get_position()            # Position (x, y)
nh.get_screen()              # Full 24x80 ASCII screen as string
nh.get_screen_lines()        # List of 24 screen lines
nh.get_local_map(radius=7)   # Cropped view centered on player with coordinate guides

nh.get_message()             # Current top-of-screen message
nh.get_messages(n=10)        # Last n game messages

nh.get_current_level()       # DungeonLevel with parsed Tile grid
nh.get_tile(pos)             # Tile at position
nh.get_adjacent_tiles()      # Dict mapping "N"/"S"/"E"/etc. to tile descriptions

nh.get_visible_monsters()    # All visible monsters
nh.get_adjacent_hostiles()   # Hostile monsters in 8 adjacent tiles
nh.get_hostile_monsters()    # All non-peaceful monsters

nh.get_inventory()           # Inventory items (each has .slot, .name, .quantity)
nh.get_food()                # Food items in inventory
nh.get_weapons()             # Weapons in inventory
nh.get_items_here()          # Items on the ground at current position
nh.get_items_here_glyphs()   # Items at current position (glyph-based, no turn cost)
nh.get_items_on_map()        # All visible items on map with positions

nh.find_stairs()             # (stairs_up_pos, stairs_down_pos)
nh.find_doors()              # List of (Position, is_open)
nh.find_altars()             # List of altar positions
nh.find_nearest_item()       # TargetResult with .position and .success
```

### Actions

All actions return `ActionResult` with `.success`, `.messages`, `.turn_elapsed`.

**Movement:**
```python
nh.move(Direction.E)          # Move one tile east
nh.move(Direction.N, count=5) # Move up to 5 tiles north (auto-stops at walls/monsters)
nh.run(Direction.E)           # Run until wall/intersection/monster
nh.move_to(Position(42, 12))  # Pathfind and walk to position
nh.go_up()                    # Ascend stairs
nh.go_down()                  # Descend stairs
```

**Combat:**
```python
nh.attack(Direction.N)        # Melee attack north
nh.kick(Direction.S)          # Kick south
nh.fire(Direction.E)          # Fire ranged weapon east
nh.throw('a', Direction.W)    # Throw inventory item 'a' west
```

**Items:**
```python
nh.pickup()                   # Pick up all items here
nh.drop('a')                  # Drop item by inventory letter
nh.eat('a')                   # Eat from inventory
nh.eat()                      # Eat from ground
nh.quaff('a')                 # Drink potion
nh.read('a')                  # Read scroll/spellbook
nh.wield('a')                 # Wield weapon
nh.wear('a')                  # Wear armor
nh.take_off('a')              # Remove worn armor
nh.put_on('a')                # Put on ring/amulet/blindfold (rings: hand='right'|'left')
nh.remove('a')                # Remove ring/amulet/blindfold
nh.zap('a', Direction.N)      # Zap wand
nh.apply('a')                 # Use tool/key/horn
```

**Doors and Stairs:**
```python
nh.open_door(Direction.E)     # Open door east
nh.close_door(Direction.W)    # Close door west
```

**Special:**
```python
nh.pray()                     # Pray to deity (has cooldown)
nh.pay()                      # Pay shopkeeper
nh.engrave("Elbereth")        # Write on floor with a finger (in dust)
nh.engrave("Elbereth", 'c')   # Write with a wand/athame (lasting engraving)
nh.cast_spell('a', Direction.N)  # Cast spell
nh.look()                     # Look at current square
nh.send_keys("keys")          # Raw keystrokes (escape hatch)
```

**Utility:**
```python
nh.wait(count=10)             # Rest for turns (auto-interrupts on attack)
nh.search(count=20)           # Search for secrets (auto-interrupts on danger)
```

**Prompt responses** (when the game asks `[ynq]` or `[yn]`):
```python
nh.confirm()                  # Send 'y'
nh.deny()                     # Send 'n'
nh.escape()                   # Send ESC
nh.space()                    # Send space (dismiss --More--)
```

### Navigation

```python
nh.autoexplore(max_steps=500) # Explore automatically
# Returns AutoexploreResult with .stop_reason:
#   "fully_explored", "hostile", "low_hp", "hungry", "blocked"

nh.move_to(Position(42, 12))  # Pathfind to specific position
# Interrupts on: hunger change, HP < 30%

nh.find_unexplored()          # Find nearest unexplored tile
# Returns TargetResult with .position
```

### Reminders and Notes

```python
nh.add_reminder(turns=50, msg="Check corpse")  # One-time alert after N turns
nh.add_note(turns=0, msg="Wand has 5 charges") # Persistent note (0 = permanent)
nh.remove_note(note_id)                         # Remove a note
nh.get_active_notes()                            # List (id, message) tuples
```

## LLM Context

Each turn, the agent receives a system prompt (once) and a decision prompt (every turn).

**System prompt** contains:
- The full NetHackAPI reference documentation
- Available tool descriptions
- Strategic advice for NetHack play

**Decision prompt** contains:
```
=== CURRENT GAME VIEW ===
Your position: (40, 12)
{24x80 ASCII game screen}

Adjacent tiles:
  N: wall |
  S: floor .
  E: goblin d
  ...

Hostile Monsters:
  - goblin 'd' [E, adjacent]

Inventory:
  a: long sword (wielded)
  b: leather armor (worn)
  c: 3 food rations

Items on map:
  - gold coin at (38, 11)

Stairs:
  - Stairs down (>) at (35, 10)

Last Result:
game_messages:
  - You hit the goblin!
actions:
  - attack(E) ok

Study the map. What do you observe, and what action will you take?
```

The context is configurable. Sections like inventory, adjacent tiles, items on map, and hostile monsters can each be toggled on or off. Old turns are compressed to save tokens — maps are stripped from history and old tool call arguments are compacted.

## Configuration

All settings live in `config/default.yaml`. Every setting can also be overridden via environment variables.

### Agent

| Setting | Default | Description |
|---|---|---|
| `agent.provider` | `"openai"` | LLM provider: `"openai"`, `"openrouter"` or `"anthropic"` |
| `agent.model` | `"gpt-5.2"` | Model identifier in the provider's format (e.g. `gpt-5.2` for OpenAI, `openai/gpt-5.2` for OpenRouter) |
| `agent.base_url` | `""` | API endpoint; empty uses the provider's standard URL. Set it to use any OpenAI-compatible server |
| `agent.openai_api` | `"responses"` | OpenAI provider only: `"responses"` (Responses API) or `"chat"` (Chat Completions, for compatible servers without `/v1/responses`) |
| `agent.temperature` | `0.1` | Sampling temperature (0.0 = deterministic, 1.0 = creative) |
| `agent.reasoning` | `"high"` | Extended thinking effort: `none`, `minimal`, `low`, `medium`, `high`, `xhigh` |
| `agent.max_turns` | `100000` | Maximum turns per episode |
| `agent.max_consecutive_errors` | `5` | Errors before auto-quit |
| `agent.decision_timeout` | `60.0` | Seconds to wait for LLM response |
| `agent.skill_timeout` | `30.0` | Seconds to wait for skill execution |
| `agent.hp_flee_threshold` | `0.3` | Flee when HP drops below this fraction |
| `agent.skills_enabled` | `false` | Enable `write_skill`/`invoke_skill` tools |
| `agent.auto_save_skills` | `true` | Auto-save successful skills |
| `agent.log_decisions` | `true` | Log LLM decisions |

### Context Management

These settings control what the LLM sees each turn and how much history is retained.

| Setting | Default | Description |
|---|---|---|
| `agent.max_history_turns` | `1000` | How many turns to keep. `0` = unlimited (compress old turns) |
| `agent.maps_in_history` | `0` | Recent turns that keep the full map. `0` = only current turn |
| `agent.tool_calls_in_history` | `10` | Recent turns that keep full tool call args. Older ones show `[compacted]` |
| `agent.show_inventory` | `true` | Include inventory in each turn's context |
| `agent.show_adjacent_tiles` | `true` | Show tile descriptions for all 8 directions |
| `agent.show_items_on_map` | `true` | List visible items with positions |
| `agent.local_map_mode` | `false` | Show cropped local view instead of full map |
| `agent.local_map_radius` | `7` | Radius of local view (7 = 15x15 area) |

When `local_map_mode` is enabled, the LLM also gets a `view_full_map` tool to request the entire dungeon level when needed.

### Environment

| Setting | Default | Description |
|---|---|---|
| `environment.name` | `"NetHackChallenge-v0"` | NLE environment name |
| `environment.max_episode_steps` | `1000000` | NLE step limit per episode |
| `environment.render_mode` | `null` | `null`, `"human"`, or `"ansi"` |
| `environment.character` | `"random"` | `"random"` or specific like `"val-hum-law-fem"` |

### Skills

| Setting | Default | Description |
|---|---|---|
| `skills.library_path` | `"./skills"` | Directory for saved skills |
| `skills.auto_save` | `true` | Auto-save successful skills |
| `skills.min_success_rate_to_save` | `0.3` | Minimum success rate to persist a skill |
| `skills.max_actions_per_skill` | `500` | Action limit per skill execution |

### Logging

| Setting | Default | Description |
|---|---|---|
| `logging.level` | `"INFO"` | `DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL` |
| `logging.file` | `"./data/agent.log"` | Log file path |
| `logging.log_llm` | `true` | Log LLM prompts and responses |
| `logging.log_actions` | `true` | Log game actions |

### Environment Variables

| Variable | Description |
|---|---|
| `OPENAI_API_KEY` | API key for OpenAI (default provider) |
| `OPENROUTER_API_KEY` (or `OPENROUTER_KEY`) | API key for OpenRouter |
| `ANTHROPIC_API_KEY` | API key for direct Anthropic access |
| `NETHACK_AGENT_MODEL` | Override model |
| `NETHACK_AGENT_PROVIDER` | Override provider |
| `NETHACK_AGENT_BASE_URL` | Override API endpoint |
| `NETHACK_AGENT_LOG_LEVEL` | Override log level |

## Project Structure

```
src/
├── cli.py                    # Entry point (watch, verify)
├── config.py                 # Configuration loading
├── agent/
│   ├── agent.py              # Main orchestration loop
│   ├── llm_client.py         # LLM API client (OpenAI/OpenRouter/Anthropic)
│   ├── parser.py             # LLM response parsing
│   └── prompts.py            # System and decision prompt templates
├── api/
│   ├── nethack_api.py        # High-level game API (the `nh` object)
│   ├── environment.py        # NLE gymnasium wrapper
│   ├── actions.py            # Action execution
│   ├── queries.py            # Map and state queries
│   ├── pathfinding.py        # A* pathfinding
│   ├── models.py             # Position, Stats, Monster, Item, Tile, etc.
│   ├── glyphs.py             # Glyph identification
│   └── knowledge.py          # Monster/item knowledge base
├── sandbox/
│   ├── manager.py            # Sandbox execution engine + API call tracking
│   ├── validation.py         # AST-based code security validation
│   └── exceptions.py         # Sandbox error types
├── memory/
│   ├── episode.py            # Episode-level memory coordination
│   ├── dungeon.py            # Dungeon level map tracking
│   ├── working.py            # Working memory (current session)
│   └── manager.py            # SQLite persistence
├── skills/
│   ├── executor.py           # Skill execution
│   ├── library.py            # Skill file management
│   ├── models.py             # Skill data structures
│   └── statistics.py         # Skill performance tracking
├── scoring/
│   └── progress.py           # Game progress scoring
└── tui/
    ├── app.py                # Textual TUI application
    ├── runner.py             # Agent runner for TUI
    ├── events.py             # Event system
    ├── logging.py            # TUI logging
    └── widgets/              # Stats bar, game screen, decision log, etc.
```

## Development

```bash
# Run tests (unit tests only by default)
uv run pytest

# Run a specific test file
uv run pytest tests/test_nethack_api.py -v

# Run integration tests (requires API key)
uv run pytest -m integration

# Lint
uv run ruff check src/ tests/
uv run ruff format src/ tests/
```

## Logs and Recordings

Logs are written to `data/logs/` with filenames like `run_2026-01-19_19-34-49.log`. They include LLM requests/responses, game state, agent decisions, and API call results.

Recordings (when using `--record`) are saved to `data/recordings/` as `.cast` files playable with `asciinema play`.

## License

MIT
