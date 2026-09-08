from dataclasses import dataclass, field, replace
from types import SimpleNamespace

import pytest

from pokemon_red_completion.actions import MacroAction, MacroActionKind
from pokemon_red_completion.gen1_field_moves import Gen1FieldMoveError, Gen1FieldMovePort
from pokemon_red_completion.observation import (
    OverworldMovementMode,
    PokemonRedStateReader,
    RawGameState,
    RedFlyMenuState,
)


@dataclass
class Memory:
    values: dict[int, int] = field(default_factory=dict)

    def read_u8(self, address):
        return self.values.get(address, 0)


def _screen(name="INDIGO PLATEAU", flags=0x209):
    # Independent cartridge character literals, including the complete blank tail.
    row = [0x93, 0xAE, 0x7F] + [0x7F if c == " " else 128 + ord(c) - 65 for c in name]
    row += [0x7F] * (18 - len(row)) + [0xED, 0xEE]
    return Memory(
        {
            0xD70B: flags & 255,
            0xD70C: flags >> 8,
            **{0xC3A0 + i: tile for i, tile in enumerate(row)},
        }
    )


def test_fly_observation_uses_visit_flags_and_visible_name_not_normal_cursor():
    memory = _screen()
    memory.values[0xCC26] = 200  # ordinary cursor is irrelevant/stale
    reader = PokemonRedStateReader(memory)
    assert reader.read_fly_destinations() == (0, 3, 9)
    assert reader.read_fly_menu_state() == RedFlyMenuState((0, 3, 9), 9)


@pytest.mark.parametrize(
    "address,value",
    [
        (0xC3A0, 0),
        (0xC3A1, 0),
        (0xC3A2, 0),
        (0xC3B2, 0),
        (0xC3B3, 0),
        (0xC3B1, 0),
        (0xD057, 2),
        (0xD70C, 0),
    ],
)
def test_non_fly_partial_or_unvisited_screen_cannot_authorize_confirmation(address, value):
    memory = _screen()
    memory.values[address] = value
    assert PokemonRedStateReader(memory).read_fly_menu_state() is None


def test_visits_do_not_invent_towns_from_unused_bits_or_badges():
    memory = Memory({0xD70B: 0, 0xD70C: 0xF8, 0xD356: 255})
    assert PokemonRedStateReader(memory).read_fly_destinations() == ()
    assert PokemonRedStateReader(_screen("CERULEAN CITY")).read_fly_menu_state().selected_map == 3


@pytest.mark.parametrize(
    "town,map_id",
    [
        ("PALLET TOWN", 0),
        ("VIRIDIAN CITY", 1),
        ("PEWTER CITY", 2),
        ("CERULEAN CITY", 3),
        ("LAVENDER TOWN", 4),
        ("VERMILION CITY", 5),
        ("CELADON CITY", 6),
        ("FUCHSIA CITY", 7),
        ("CINNABAR ISLAND", 8),
        ("INDIGO PLATEAU", 9),
        ("SAFFRON CITY", 10),
    ],
)
def test_every_complete_town_name_has_its_cartridge_map_identity(town, map_id):
    result = PokemonRedStateReader(_screen(town, 1 << map_id)).read_fly_menu_state()
    assert result == RedFlyMenuState((map_id,), map_id)


def _raw():
    return RawGameState(
        game_started=True,
        map_id=36,
        player_x=8,
        player_y=5,
        party_count=3,
        battle_state=0,
        badge_bits=255,
        party_species_ids=(28, 64, 48),
        party_levels=(66, 55, 13),
        party_hp=(200, 110, 34),
        party_max_hp=(213, 120, 34),
        party_status=(0, 0, 0),
        party_moves=((57, 70, 58, 66), (163, 28, 15, 19), (1, 95, 50, 0)),
        party_pp=((15, 15, 10, 25), (20, 15, 30, 15), (35, 20, 20, 0)),
        bag_items=((16, 4),),
        player_money=619,
        event_flags=bytes(320),
    )


@dataclass
class FlyWorld:
    raw: RawGameState = field(default_factory=_raw)
    available: tuple[int, ...] = (0, 3, 9)
    selected: int = 0
    stage: str = "field"
    cursor: int = 0
    actions: list[MacroAction] = field(default_factory=list)
    menu_steps: list[tuple[str, int]] = field(default_factory=list)
    fault: str = ""
    flight_confirms: int = 0
    transitions: dict[tuple[str, int], int] = field(
        default_factory=lambda: {
            ("up", 0): 3,
            ("up", 3): 9,
            ("up", 9): 0,
            ("down", 0): 9,
            ("down", 9): 3,
            ("down", 3): 0,
        }
    )

    def read(self):
        return self.raw

    def read_u8(self, address):
        return {0xCC26: self.cursor, 0xCC28: 5}.get(address, 0)

    def read_input_readiness(self):
        return SimpleNamespace(ready=self.stage in {"field", "landed"})

    def read_overworld_movement_mode(self):
        if self.stage == "landed" and self.fault == "wrong_locomotion":
            return OverworldMovementMode.SURFING
        return OverworldMovementMode.WALKING

    def read_bottom_dialogue_box_visible(self):
        return False

    def read_pending_trainer_battle_identity(self):
        return None

    def read_fly_destinations(self):
        return self.available

    def read_fly_menu_state(self):
        if self.stage != "fly" or self.fault == "no_menu":
            return None
        return RedFlyMenuState(self.available, self.selected)

    def execute(self, action):
        self.actions.append(action)
        if action.kind is MacroActionKind.WAIT:
            return
        if action.kind is MacroActionKind.OPEN_MENU:
            self.stage, self.cursor = "start", 0
        elif action.kind is MacroActionKind.MOVE:
            if self.stage == "fly":
                if self.fault == "stuck":
                    return
                if self.fault == "different_menu":
                    self.available = (0, 9)
                # An explicit three-town emulator transition table, not the selector algorithm.
                self.selected = self.transitions[(action.value, self.selected)]
            else:
                self.cursor += 1 if action.value == "down" else -1
        elif action.kind is MacroActionKind.CONFIRM:
            if self.stage == "fly":
                self.flight_confirms += 1
                if self.fault == "never_lands":
                    return
                self.stage = "landed"
                self.raw = replace(
                    self.raw,
                    map_id=3 if self.fault == "wrong_landing" else self.selected,
                    player_x=9,
                    player_y=6,
                )
                if self.fault == "specimen_change":
                    self.raw = replace(self.raw, party_species_ids=(28, 64, 49))
                if self.fault == "money_change":
                    self.raw = replace(self.raw, player_money=600)
                if self.fault == "missing_position":
                    self.raw = replace(self.raw, player_x=None)
                if self.fault == "unstarted":
                    self.raw = replace(self.raw, game_started=False)
            else:
                self.menu_steps.append((self.stage, self.cursor))
                self.stage = {"start": "party", "party": "submenu", "submenu": "fly"}[self.stage]
                self.cursor = 0


def _port(world):
    return Gen1FieldMovePort(world, world, world)  # type: ignore[arg-type]


def test_observed_fly_selects_holder_and_destination_and_confirms_only_once():
    world = FlyWorld()
    receipt = _port(world).execute(MacroAction(MacroActionKind.FIELD_MOVE, "fly:indigo_plateau"))
    assert world.menu_steps == [("start", 1), ("party", 1), ("submenu", 1)]
    assert receipt.observed_destinations == (0, 9)
    assert receipt.source_map == 36 and receipt.destination_map == 9
    assert world.flight_confirms == 1
    assert world.raw.party_species_ids == (28, 64, 48)


def test_reordered_holder_and_changed_field_move_row_are_observed():
    raw = _raw()
    world = FlyWorld(raw=replace(raw, party_moves=((19, 0, 0, 0), *raw.party_moves[1:])))
    _port(world).execute(MacroAction(MacroActionKind.FIELD_MOVE, "fly:indigo_plateau"))
    assert world.menu_steps == [("start", 1), ("party", 0), ("submenu", 0)]


def test_multiple_cursor_steps_use_a_different_visit_set_and_target():
    world = FlyWorld(
        available=(0, 1, 2, 3, 9),
        transitions={
            ("down", 0): 9,
            ("down", 9): 3,
        },
    )
    receipt = _port(world).execute(MacroAction(MacroActionKind.FIELD_MOVE, "fly:cerulean_city"))
    assert receipt.observed_destinations == (0, 9, 3)
    assert world.flight_confirms == 1 and world.raw.map_id == 3


def test_already_selected_only_destination_requires_no_cursor_input():
    world = FlyWorld(available=(9,), selected=9, transitions={})
    receipt = _port(world).execute(MacroAction(MacroActionKind.FIELD_MOVE, "fly:indigo_plateau"))
    assert receipt.observed_destinations == (9,)
    assert world.flight_confirms == 1


@pytest.mark.parametrize("fault", ["no_menu", "stuck", "different_menu"])
def test_wrong_menu_or_unacknowledged_selection_never_confirms_flight(fault):
    world = FlyWorld(fault=fault)
    with pytest.raises(Gen1FieldMoveError):
        _port(world).execute(MacroAction(MacroActionKind.FIELD_MOVE, "fly:indigo_plateau"))
    assert world.flight_confirms == 0


@pytest.mark.parametrize(
    "fault",
    [
        "wrong_landing",
        "never_lands",
        "specimen_change",
        "money_change",
        "wrong_locomotion",
        "missing_position",
        "unstarted",
    ],
)
def test_failed_landing_is_retained_without_another_flight(fault):
    world = FlyWorld(fault=fault)
    with pytest.raises(Gen1FieldMoveError):
        _port(world).execute(MacroAction(MacroActionKind.FIELD_MOVE, "fly:indigo_plateau"))
    assert world.flight_confirms == 1
    assert len(world.actions) < 100


@pytest.mark.parametrize(
    "change",
    [
        {"badge_bits": 0},
        {"battle_state": 2},
        {"map_id": 174},
        {"party_hp": (200, 0, 34)},
        {"party_moves": ((1,), (1,), (1,))},
        {"party_species_ids": None},
        {"player_money": None},
    ],
)
def test_invalid_departure_fails_before_any_input(change):
    world = FlyWorld(raw=replace(_raw(), **change))
    with pytest.raises(Gen1FieldMoveError):
        _port(world).execute(MacroAction(MacroActionKind.FIELD_MOVE, "fly:indigo_plateau"))
    assert world.actions == []


def test_unvisited_destination_fails_before_opening_menu():
    world = FlyWorld(available=(0, 3))
    with pytest.raises(Gen1FieldMoveError, match="not observed as visited"):
        _port(world).execute(MacroAction(MacroActionKind.FIELD_MOVE, "fly:indigo_plateau"))
    assert world.actions == []
