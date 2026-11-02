"""Opt-in native Rare Candy revival, excluding move-learning/evolution boundaries.

The caller declares the target. This is mechanic execution, not learned selection.
No memory writes, item creation, general level grinding or automatic fallback.
"""

from dataclasses import replace

from .actions import MacroActionKind
from .collection import CollectionLocation
from .gen1_cartridge import evolution_graph
from .lavender import DEFAULT_LAVENDER_TIMING, _close_menus, _select_bag_item, _select_cursor
from .red_battle_practice_cartridge import RedPracticeCartridge
from .red_faint_recovery import _open_bag
from .red_party import PokemonRedPartyReader, party_observation_from_raw
from .victory_road import _pulse


class RedCandyRecoveryError(ValueError):
    """The declared native item boundary or exact retained effect differs."""


def _require(condition, message):
    if not condition:
        raise RedCandyRecoveryError(message)


def require_candy_target(raw, index, rom):
    party_observation_from_raw(raw)  # validates coherent party arrays
    _require(raw.battle_state == 0 and any(raw.party_hp), "requires a living field party")
    _require(type(index) is int and 0 <= index < raw.party_count, "invalid target slot")
    _require(
        raw.party_hp[index] == 0 and raw.party_status[index] == 0,
        "target is not healthy-status fainted",
    )
    _require(
        raw.bag_items is not None and len(dict(raw.bag_items)) == len(raw.bag_items),
        "invalid inventory",
    )
    _require(dict(raw.bag_items).get(40, 0) == 1, "profile requires one owned Rare Candy")
    _require(
        raw.party_stats is not None and len(raw.party_stats) == raw.party_count,
        "missing party stats",
    )
    level = raw.party_levels[index]
    _require(level < 100, "target is at level cap")
    species = RedPracticeCartridge(rom).species(raw.party_species_ids[index])
    _require(
        not evolution_graph(rom).get(species.national_number), "evolving targets are not admitted"
    )
    _require(
        not any(at == level + 1 for at, _ in species.level_up_moves),
        "new-move boundary is not admitted",
    )
    return species.experience_at_level(level + 1)


def verify_candy_effect(before, after, index):
    """One level and positive native max-HP delta revive; all other slots preserved."""
    _require(type(index) is int and 0 <= index < before.party_count, "invalid target slot")
    _require(
        before.party_hp[index] == 0 and dict(before.bag_items).get(40) == 1, "invalid candy origin"
    )
    expected_bag = tuple(row for row in before.bag_items if row[0] != 40)
    _require(after.bag_items == expected_bag, "exact one-item consumption differs")
    _require(after.bag_item_ids == tuple(item for item, _ in expected_bag), "bag alias differs")
    for name in (
        "game_started",
        "map_id",
        "player_x",
        "player_y",
        "battle_state",
        "player_money",
        "event_flags",
        "badge_bits",
        "party_count",
        "party_species_ids",
        "party_moves",
        "party_pp",
        "party_status",
        "status_flags_1",
        "repel_remaining_steps",
    ):
        _require(getattr(before, name) == getattr(after, name), f"changed protected {name}")
    for slot in range(before.party_count):
        if slot != index:
            for name in ("party_levels", "party_hp", "party_max_hp", "party_stats"):
                _require(
                    getattr(before, name)[slot] == getattr(after, name)[slot],
                    f"changed other {name}",
                )
        else:
            _require(
                after.party_levels[slot] == before.party_levels[slot] + 1, "level effect differs"
            )
            gain = after.party_max_hp[slot] - before.party_max_hp[slot]
            _require(0 < gain <= 10 and after.party_hp[slot] == gain, "native HP delta differs")
            _require(
                all(
                    0 <= new - old <= 10
                    for old, new in zip(
                        before.party_stats[slot], after.party_stats[slot], strict=True
                    )
                ),
                "stat gain exceeds profile",
            )
    for name, values in (
        ("level", "party_levels"),
        ("hp", "party_hp"),
        ("max_hp", "party_max_hp"),
        ("status", "party_status"),
        ("moves", "party_moves"),
        ("pp", "party_pp"),
    ):
        _require(
            getattr(after, "first_party_" + name) == getattr(after, values)[0],
            "party alias differs",
        )


def verify_candy_collection(before, after, index):
    targets = [
        s
        for s in before.specimens
        if (s.location, s.container_index, s.slot_index) == (CollectionLocation.PARTY, 0, index)
    ]
    _require(len(targets) == 1, "collection target is missing or ambiguous")
    expected = replace(
        before,
        specimens=tuple(
            replace(s, level=s.level + 1) if s is targets[0] else s for s in before.specimens
        ),
    )
    _require(after == expected, "collection changed beyond the intended target level")


def use_candy_revival(actions, reader, emulator, adapter, rom, index):
    observation = adapter.observe()
    before = observation.raw
    expected_xp = require_candy_target(before, index, rom)
    _require(
        observation.input_ready
        and not emulator.pressed_buttons
        and not reader.read_bottom_dialogue_box_visible(),
        "field controls are not ready",
    )
    party_reader = PokemonRedPartyReader(emulator)
    members_before = party_reader.read().members
    refs_before = party_reader.preparation_specimen_refs()
    start_actions, start_frames = actions.actions_executed, emulator.frame_count
    timing = DEFAULT_LAVENDER_TIMING
    _open_bag(actions, reader, emulator, timing)
    _select_bag_item(actions, emulator, 40, timing)
    _pulse(actions, MacroActionKind.CONFIRM)
    _pulse(actions, MacroActionKind.CONFIRM, frames=240)
    _select_cursor(actions, emulator, index, timing)
    _pulse(actions, MacroActionKind.CONFIRM)
    for _ in range(24):
        current = reader.read()
        if current.bag_items != before.bag_items:
            # No confirmation after ANY inventory change, including a wrong effect.
            verify_candy_effect(before, current, index)
            _close_menus(actions, reader, timing)
            final = adapter.observe()
            verify_candy_effect(before, final.raw, index)
            _require(
                final.input_ready
                and not emulator.pressed_buttons
                and not reader.read_bottom_dialogue_box_visible(),
                "controls did not settle",
            )
            verify_candy_collection(
                observation.collection_observation, final.collection_observation, index
            )
            _require(
                adapter.graph.completed_ids(final.game_state)
                == adapter.graph.completed_ids(observation.game_state),
                "story changed during candy",
            )
            _require(
                party_reader.preparation_specimen_refs() == refs_before, "specimen identity changed"
            )
            for slot, (old, new) in enumerate(
                zip(members_before, party_reader.read().members, strict=True)
            ):
                if slot == index:
                    _require(new.experience == expected_xp, "level-up XP differs")
                    new = replace(
                        new,
                        level=old.level,
                        hp=old.hp,
                        max_hp=old.max_hp,
                        experience=old.experience,
                    )
                _require(new == old, "unrelated party data changed")
            return dict(
                item_id=40,
                party_index=index,
                before_level=before.party_levels[index],
                after_level=final.raw.party_levels[index],
                before_hp=0,
                after_hp=final.raw.party_hp[index],
                experience=expected_xp,
                actions=actions.actions_executed - start_actions,
                frames=emulator.frame_count - start_frames,
                target_selection="caller_declared_not_learned",
            )
        _pulse(actions, MacroActionKind.CONFIRM)
    raise RedCandyRecoveryError("Rare Candy consumption did not finish within bound")
