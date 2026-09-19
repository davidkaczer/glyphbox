"""Tests for action execution."""

import pytest

from src.api.actions import ActionExecutor
from src.api.models import Direction, ActionResult


class TestActionExecutorBasic:
    """Basic tests for ActionExecutor that don't require NLE."""

    def test_direction_keys_mapping(self, nle_env):
        """Test that direction key mappings are correct."""
        executor = ActionExecutor(nle_env)

        # Check that vi-keys are mapped
        assert executor._direction_keys[Direction.N] == ord("k")
        assert executor._direction_keys[Direction.S] == ord("j")
        assert executor._direction_keys[Direction.E] == ord("l")
        assert executor._direction_keys[Direction.W] == ord("h")
        assert executor._direction_keys[Direction.NE] == ord("u")
        assert executor._direction_keys[Direction.NW] == ord("y")
        assert executor._direction_keys[Direction.SE] == ord("n")
        assert executor._direction_keys[Direction.SW] == ord("b")


class TestMovement:
    """Tests for movement actions."""

    def test_move_north(self, nle_env):
        """Test moving north."""
        nle_env.reset()
        executor = ActionExecutor(nle_env)

        result = executor.move(Direction.N)

        assert isinstance(result, ActionResult)
        # Result may or may not be successful depending on game state

    def test_move_invalid_direction(self, nle_env):
        """Test moving in UP direction (stairs, not movement)."""
        nle_env.reset()
        executor = ActionExecutor(nle_env)

        # UP/DOWN are for stairs, not movement, but should still work
        result = executor.move(Direction.UP)
        assert isinstance(result, ActionResult)

    def test_wait_action(self, nle_env):
        """Test wait action."""
        nle_env.reset()
        executor = ActionExecutor(nle_env)

        result = executor.wait()

        assert result.success is True
        assert result.turn_elapsed is True

    def test_search_action(self, nle_env):
        """Test search action."""
        nle_env.reset()
        executor = ActionExecutor(nle_env)

        result = executor.search()

        assert result.success is True


class TestCombat:
    """Tests for combat actions."""

    def test_attack_direction(self, nle_env):
        """Test attack in a direction."""
        nle_env.reset()
        executor = ActionExecutor(nle_env)

        # Attack north (may or may not hit anything)
        result = executor.attack(Direction.N)

        assert isinstance(result, ActionResult)

    def test_kick_direction(self, nle_env):
        """Test kick in a direction."""
        nle_env.reset()
        executor = ActionExecutor(nle_env)

        # Kick north
        result = executor.kick(Direction.N)

        assert isinstance(result, ActionResult)


class TestItems:
    """Tests for item actions."""

    def test_pickup(self, nle_env):
        """Test pickup action."""
        nle_env.reset()
        executor = ActionExecutor(nle_env)

        # Pickup (may or may not have items)
        result = executor.pickup()

        assert isinstance(result, ActionResult)

    def test_eat_action(self, nle_env):
        """Test eat action."""
        nle_env.reset()
        executor = ActionExecutor(nle_env)

        # Try to eat (may prompt for food selection)
        result = executor.eat()

        assert isinstance(result, ActionResult)


class TestUtility:
    """Tests for utility actions."""

    def test_look_action(self, nle_env):
        """Test look action."""
        nle_env.reset()
        executor = ActionExecutor(nle_env)

        result = executor.look()

        assert result.success is True

    def test_pray_action(self, nle_env):
        """Test pray action."""
        nle_env.reset()
        executor = ActionExecutor(nle_env)

        result = executor.pray()

        # Pray works, though may have consequences
        assert isinstance(result, ActionResult)

    def test_escape_action(self, nle_env):
        """Test escape key."""
        nle_env.reset()
        executor = ActionExecutor(nle_env)

        result = executor.escape()

        assert isinstance(result, ActionResult)

    def test_space_action(self, nle_env):
        """Test space key (dismiss message)."""
        nle_env.reset()
        executor = ActionExecutor(nle_env)

        result = executor.space()

        assert isinstance(result, ActionResult)


class TestRawActions:
    """Tests for raw action sending."""

    def test_send_keys(self, nle_env):
        """Test sending raw keys."""
        nle_env.reset()
        executor = ActionExecutor(nle_env)

        # Send a wait command
        result = executor.send_keys(".")

        assert result.success is True

    def test_send_action_index(self, nle_env):
        """Test sending raw action index."""
        nle_env.reset()
        executor = ActionExecutor(nle_env)

        # Send action index 0 (whatever that is)
        result = executor.send_action(0)

        assert isinstance(result, ActionResult)


class TestMultiStepActions:
    """Tests for actions that require multiple keypresses."""

    def test_open_door_direction(self, nle_env):
        """Test open door action."""
        nle_env.reset()
        executor = ActionExecutor(nle_env)

        # Try to open door north (may or may not have door)
        result = executor.open_door(Direction.N)

        assert isinstance(result, ActionResult)

    def test_close_door_direction(self, nle_env):
        """Test close door action."""
        nle_env.reset()
        executor = ActionExecutor(nle_env)

        result = executor.close_door(Direction.N)

        assert isinstance(result, ActionResult)

    def test_drop_item(self, nle_env):
        """Test drop item action."""
        nle_env.reset()
        executor = ActionExecutor(nle_env)

        # Try to drop item 'a' (may or may not exist)
        result = executor.drop("a")

        assert isinstance(result, ActionResult)

    def test_throw_item(self, nle_env):
        """Test throw item action."""
        nle_env.reset()
        executor = ActionExecutor(nle_env)

        # Try to throw item 'a' north
        result = executor.throw("a", Direction.N)

        assert isinstance(result, ActionResult)


@pytest.fixture
def wizard_api():
    """A wizard starts with rings, potions, scrolls and a wand to exercise item commands."""
    from src.api.nethack_api import NetHackAPI

    api = NetHackAPI(character="wiz-elf-cha-mal", max_episode_steps=1000)
    api.reset()
    yield api
    api.close()


class TestJewelry:
    """Tests for putting on and removing jewelry/accessories."""

    @staticmethod
    def _rings(api):
        return [i for i in api.get_inventory() if i.object_class.value == "ring"]

    @staticmethod
    def _item(api, slot):
        return next((i for i in api.get_inventory() if i.slot == slot), None)

    def test_put_on_ring_each_hand_then_remove(self, wizard_api):
        """Rings go on the requested hand and come back off."""
        first, second = self._rings(wizard_api)[:2]

        assert wizard_api.put_on(first.slot).success
        assert wizard_api.put_on(second.slot, hand="left").success

        assert "on right hand" in self._item(wizard_api, first.slot).name
        assert "on left hand" in self._item(wizard_api, second.slot).name
        assert self._item(wizard_api, first.slot).equipped

        assert wizard_api.remove(first.slot).success
        assert wizard_api.remove(second.slot).success
        assert not self._item(wizard_api, first.slot).equipped
        assert not self._item(wizard_api, second.slot).equipped

    def test_invalid_hand_rejected(self, wizard_api):
        """An unusable hand fails before any key is sent."""
        ring = self._rings(wizard_api)[0]

        result = wizard_api.put_on(ring.slot, hand="sideways")

        assert not result.success
        assert not self._item(wizard_api, ring.slot).equipped

    def test_remove_item_not_worn_fails(self, wizard_api):
        """Removing something that isn't worn is reported as a failure."""
        ring = self._rings(wizard_api)[0]

        result = wizard_api.remove(ring.slot)

        assert not result.success

    def test_put_on_does_not_leak_keystroke(self, wizard_api):
        """With nothing left to put on, the slot letter must not start another command."""
        for ring in self._rings(wizard_api)[:2]:
            wizard_api.put_on(ring.slot)
        # 'z' would be read as the zap command if it leaked past the refusal
        result = wizard_api.put_on("z")

        assert not result.success
        assert not any("zap" in msg for msg in result.messages)


class TestItemCommandRefusals:
    """A refused item command must not leave its slot letter to be read as the next command."""

    @staticmethod
    def _slot(api, object_class):
        return next(i.slot for i in api.get_inventory() if i.object_class.value == object_class)

    @pytest.mark.parametrize(
        "command",
        [
            lambda api: api.quaff("z"),
            lambda api: api.read("z"),
            lambda api: api.wear("z"),
            lambda api: api.wield("z"),
            lambda api: api.apply("z"),
            lambda api: api.drop("z"),
            lambda api: api.eat("z"),
            lambda api: api.take_off("z"),
            lambda api: api.zap("z", Direction.E),
            lambda api: api.throw("z", Direction.E),
            lambda api: api.cast_spell("z", Direction.E),
        ],
    )
    def test_refusal_is_reported_and_leaves_no_pending_prompt(self, wizard_api, command):
        """The command fails, the player stays put, and the game is ready for the next command."""
        before = wizard_api.position

        result = command(wizard_api)

        assert not result.success
        assert wizard_api.position == before
        assert not wizard_api._actions.env.last_observation.in_any_prompt

    def test_zap_still_works_with_a_valid_wand(self, wizard_api):
        """The gating must not break the normal path: a real wand loses a charge."""
        wand = self._slot(wizard_api, "wand")
        charges = lambda: next(i.name for i in wizard_api.get_inventory() if i.slot == wand)
        before = charges()

        result = wizard_api.zap(wand, Direction.E)

        assert result.success
        assert charges() != before

    def test_cast_known_spell_succeeds(self, wizard_api):
        """Wizards start knowing force bolt in slot a."""
        result = wizard_api.cast_spell("a", Direction.E)

        assert result.success
