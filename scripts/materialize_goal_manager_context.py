#!/usr/bin/env python3
"""Materialize one real, uncounted Red goal-manager mechanic boundary."""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from collections.abc import Callable
from pathlib import Path
from typing import cast

from pokemon_red_completion.actions import MacroAction, MacroActionKind
from pokemon_red_completion.battle_recovery import (
    ProtectedRecoveryError,
    switch_active_battler,
)
from pokemon_red_completion.blaine import (
    CENTER_TO_MART,
    DIGLETT_SPECIES_ID,
    DIGLETTS_CAVE_TRAINING_VENUE,
    MANSION_BALANCED_TEAM_TRAINING_INTENT,
    MANSION_ESCORT_ENEMY_SPECIES,
    MANSION_LEVEL_UP_MOVE_CANCEL_INTERVAL,
    MANSION_MAX_CONSECUTIVE_FLEES,
    MANSION_TRAINING_FLEE_TIMING,
    MANSION_TRAINING_VENUE,
    MANSION_VOLATILE_ENEMY_SPECIES,
    MART_TO_MANSION,
    ROUTE_11_TRAINING_VENUE,
    BlaineChapterError,
    _fly_to_town,
    _heal,
    _move,
    _pulse,
    _require,
    _training_dig_to_cinnabar,
)
from pokemon_red_completion.bootstrap import DEFAULT_NEW_GAME_TIMING
from pokemon_red_completion.captured_progress import (
    CapturedProgressError,
    write_captured_progress,
)
from pokemon_red_completion.celadon import CeladonChapterError
from pokemon_red_completion.celadon import _flee as _timed_flee
from pokemon_red_completion.collection_protocol import working_source_bundle_sha256
from pokemon_red_completion.emulator import EmulatorError, PyBoyAdapter
from pokemon_red_completion.executor import (
    ControllerTiming,
    CountingExecutor,
    FrameSafeExecutor,
)
from pokemon_red_completion.field_recovery import (
    FieldRecoveryError,
    plan_party_recovery,
)
from pokemon_red_completion.gen1_field_moves import DIG_MOVE_ID
from pokemon_red_completion.goal_manager import GoalDecisionOutcome, GoalKind
from pokemon_red_completion.goal_manager_context_catalog import (
    GoalManagerContextCatalogError,
    open_goal_manager_context_capture,
)
from pokemon_red_completion.goal_manager_protocol import (
    GoalManagerProtocolError,
    load_committed_goal_manager_registry,
)
from pokemon_red_completion.goal_manager_state import party_safety_satisfaction
from pokemon_red_completion.hideout import DEFAULT_HIDEOUT_TIMING
from pokemon_red_completion.lavender import (
    DEFAULT_LAVENDER_TIMING,
    _buy_mart_item,
    _close_menus,
    _open_bag,
    _select_bag_item,
)
from pokemon_red_completion.observation import (
    RED_BOX_CAPACITY,
    ItemId,
    MapId,
    PokemonRedStateReader,
    RawGameState,
)
from pokemon_red_completion.provenance import (
    EvaluationIdentityError,
    detect_source_identity,
    require_clean_source,
    require_published_source,
)
from pokemon_red_completion.red_goal_context import (
    _targeted_evolution_index,
    red_team_development_quantum_policy,
)
from pokemon_red_completion.red_goal_manager import (
    PokemonRedGoalStateAdapter,
    RedGoalManagerConfig,
)
from pokemon_red_completion.red_goal_skills import (
    RedMartPurchase,
    RedMartResupplyGoalProvider,
)
from pokemon_red_completion.red_party import (
    BLASTOISE_SPECIES_ID,
    DUGTRIO_SPECIES_ID,
    party_observation_from_raw,
)
from pokemon_red_completion.red_player_observer import (
    CapturedPokemonRedObserver,
    ResumedStateError,
)
from pokemon_red_completion.red_team_training import run_red_team_balancing
from pokemon_red_completion.rom import RomValidationError, resolve_rom_path, verify_rom
from pokemon_red_completion.route import COMPLETION_QUEST
from pokemon_red_completion.route_evidence import rom_adjacent_artifacts
from pokemon_red_completion.surge import (
    DEFAULT_SURGE_TIMING,
    VERMILION_PC_TO_NURSE,
    LiveWildCorridorSurveyExecutor,
    SurgeChapterError,
)
from pokemon_red_completion.surge import (
    _flee as _protected_flee,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
# Catalog admission starts at 0.50, but the fixed completion-first teacher's
# emergency restoration gate is 0.55.  Setup must reach the teacher contract
# rather than merely scrape past the weaker structural threshold.
_ACTIVE_SAFETY_PRESSURE = 0.55
_ACQUISITION_GREAT_BALL_PURCHASE = 12
_CINNABAR_HYPER_POTION_INDEX = 2
_HYPER_POTION_PRICE = 1_500
# With the fixed desired headroom of eight, an active box count of eighteen
# leaves two slots and therefore creates exactly 0.75 storage pressure: the
# completion-first teacher's hard storage gate.  Setup reaches that boundary
# through genuine catches rather than editing box memory.
_STORAGE_TARGET_ACTIVE_BOX_COUNT = 18
_STORAGE_GREAT_BALL_PURCHASE = 48
_STORAGE_MAX_SEEK_STEPS = 4_096
_STORAGE_MAX_ENCOUNTERS = 128
_STORAGE_MAX_LEGS = 512
_STORAGE_CAPTURE_SETTLE_PULSES = 12
_STORAGE_CAPTURE_BATCH = 3
_STORAGE_MANSION_DIRECTIONS = ("up",) * 7
_DAMAGE_SWITCH_LIMIT = 64
_STANDARD_FLY_CENTER_MAPS = frozenset(
    {
        MapId.VIRIDIAN_POKECENTER,
        MapId.PEWTER_POKECENTER,
        MapId.CERULEAN_POKECENTER,
        MapId.VERMILION_POKECENTER,
        MapId.LAVENDER_POKECENTER,
        MapId.FUCHSIA_POKECENTER,
        MapId.CELADON_POKECENTER,
        MapId.SAFFRON_POKECENTER,
        MapId.CINNABAR_POKECENTER,
    }
)
_STANDARD_FLY_OUTDOOR_MAPS = frozenset(
    {
        MapId.VIRIDIAN_CITY,
        MapId.PEWTER_CITY,
        MapId.CERULEAN_CITY,
        MapId.LAVENDER_TOWN,
        MapId.VERMILION_CITY,
        MapId.CELADON_CITY,
        MapId.FUCHSIA_CITY,
        MapId.CINNABAR_ISLAND,
        MapId.SAFFRON_CITY,
    }
)
_DAMAGE_MODES = frozenset(
    {
        "acquisition-damaged",
        "damaged-center",
        "damaged-field",
        "damaged-pc",
    }
)
_MODES = (
    "stable",
    "story-resource-scarce",
    "center",
    "mansion",
    "acquisition-ready",
    "acquisition-damaged",
    "storage-ready",
    "mart",
    "pc",
    "blocked-movement",
    "damaged-field",
    "damaged-center",
    "damaged-pc",
    "evolved-team",
)


class GoalManagerContextMaterializationError(RuntimeError):
    """Raised when a real mechanic boundary cannot be derived safely."""


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=_MODES, required=True)
    parser.add_argument("--context-id", required=True)
    parser.add_argument("--state", type=Path, required=True)
    parser.add_argument("--envelope", type=Path, default=None)
    parser.add_argument("--out-state", type=Path, required=True)
    parser.add_argument("--rom", type=Path, default=None, help="otherwise POKEMON_RED_ROM")
    parser.add_argument(
        "--great-ball-quantity",
        type=int,
        default=None,
        help="positive acquisition reserve override",
    )
    parser.add_argument(
        "--hyper-potion-quantity",
        type=int,
        default=None,
        help="positive exact recovery reserve purchase for field-recovery damage modes",
    )
    parser.add_argument(
        "--target-safety-pressure",
        type=float,
        default=None,
        help="damage target; damage modes only",
    )
    parser.add_argument(
        "--maximum-safety-pressure",
        type=float,
        default=None,
        help="optional closed upper damage bound; damage modes only",
    )
    parser.add_argument("--watch", action="store_true")
    parser.add_argument("--speed", type=int, choices=(1, 2, 4), default=None)
    return parser


def _new_external_output(destination: Path, rom_path: Path) -> Path:
    resolved = destination.resolve()
    envelope = Path(f"{resolved}.json")
    if (
        resolved.is_relative_to(PROJECT_ROOT.resolve())
        or resolved.parent == rom_path.resolve().parent
        or not resolved.parent.is_dir()
        or resolved.exists()
        or envelope.exists()
    ):
        raise GoalManagerContextMaterializationError(
            "materialized context must use a new private external path"
        )
    return resolved


def _inverse(directions: tuple[str, ...]) -> tuple[str, ...]:
    opposite = {"up": "down", "right": "left", "down": "up", "left": "right"}
    return tuple(opposite[item] for item in reversed(directions))


def _story_resource_scarce_boundary(
    actions: CountingExecutor,
    reader: PokemonRedStateReader,
    emulator: PyBoyAdapter,
) -> None:
    """Discard one real Poké Ball while preserving an exact story boundary.

    The midgame story skills are available only at their source Pokémon
    Centers.  Relocating those captures to Cinnabar destroys the executable
    story option, while copying a save would duplicate its policy context.
    This bounded cartridge interaction creates one honest resource variant at
    the same frontier without changing story, party, collection, or money.
    """

    before = reader.read()
    before_inventory = dict(before.bag_items or ())
    before_party = party_observation_from_raw(before)
    if (
        before.battle_state
        or before.map_id not in _STANDARD_FLY_CENTER_MAPS
        or (before.player_x, before.player_y) != (3, 3)
        or not reader.read_input_readiness().ready
        or before_inventory.get(int(ItemId.POKE_BALL), 0) != 1
    ):
        raise GoalManagerContextMaterializationError(
            "story resource setup requires one Poké Ball at a stable Center frontier"
        )

    _open_bag(actions, emulator, DEFAULT_LAVENDER_TIMING)
    _select_bag_item(
        actions,
        emulator,
        ItemId.POKE_BALL,
        DEFAULT_LAVENDER_TIMING,
    )
    _pulse(actions, MacroActionKind.CONFIRM, frames=120)
    _pulse(actions, MacroActionKind.MOVE, "down", 120)
    _pulse(actions, MacroActionKind.CONFIRM, frames=120)
    for _ in range(6):
        current_quantity = dict(reader.read().bag_items or ()).get(
            int(ItemId.POKE_BALL),
            0,
        )
        if current_quantity == 0:
            break
        _pulse(actions, MacroActionKind.CONFIRM, frames=120)
    else:
        raise GoalManagerContextMaterializationError(
            "story resource setup did not discard its exact Poké Ball"
        )
    _close_menus(actions, reader, DEFAULT_LAVENDER_TIMING)

    after = reader.read()
    expected_inventory = dict(before_inventory)
    expected_inventory.pop(int(ItemId.POKE_BALL))
    if (
        dict(after.bag_items or ()) != expected_inventory
        or party_observation_from_raw(after) != before_party
        or after.player_money != before.player_money
        or after.map_id != before.map_id
        or (after.player_x, after.player_y) != (before.player_x, before.player_y)
        or after.battle_state
        or not reader.read_input_readiness().ready
    ):
        raise GoalManagerContextMaterializationError(
            "story resource setup changed more than its exact Poké Ball reserve"
        )


def _normalize_cinnabar_nurse(
    actions: CountingExecutor,
    reader: PokemonRedStateReader,
    emulator: PyBoyAdapter,
) -> None:
    raw = reader.read()
    if raw.battle_state or not reader.read_input_readiness().ready:
        raise GoalManagerContextMaterializationError(
            "materialization requires a stable relocation boundary"
        )
    if raw.map_id == MapId.CINNABAR_POKECENTER and (
        raw.player_x,
        raw.player_y,
    ) == (13, 4):
        _move(
            actions,
            reader,
            VERMILION_PC_TO_NURSE,
            "goal-manager Cinnabar PC to nurse",
        )
        raw = reader.read()
    elif raw.map_id in _STANDARD_FLY_CENTER_MAPS and raw.map_id != (
        MapId.CINNABAR_POKECENTER
    ) and (raw.player_x, raw.player_y) == (3, 3):
        _move(
            actions,
            reader,
            ("down",) * 5,
            "goal-manager source Center departure",
        )
        _fly_to_town(
            actions,
            reader,
            emulator,
            MapId.CINNABAR_ISLAND,
            "goal-manager source Center to Cinnabar",
        )
        _move(actions, reader, ("up",) * 5, "goal-manager Cinnabar Center")
        raw = reader.read()
    elif raw.map_id in _STANDARD_FLY_OUTDOOR_MAPS:
        _fly_to_town(
            actions,
            reader,
            emulator,
            MapId.CINNABAR_ISLAND,
            "goal-manager outdoor source to Cinnabar",
        )
        _move(actions, reader, ("up",) * 5, "goal-manager Cinnabar Center")
        raw = reader.read()
    elif raw.map_id == MapId.INDIGO_PLATEAU_LOBBY and (
        raw.player_x,
        raw.player_y,
    ) == (2, 5):
        _move(
            actions,
            reader,
            ("right", "down", "down") + ("right",) * 4 + ("down",) * 5,
            "goal-manager Indigo departure",
        )
        _require(
            reader.read(),
            MapId.INDIGO_PLATEAU,
            (9, 6),
            "goal-manager Indigo field",
        )
        _fly_to_town(
            actions,
            reader,
            emulator,
            MapId.CINNABAR_ISLAND,
            "goal-manager Indigo to Cinnabar",
        )
        _move(actions, reader, ("up",) * 5, "goal-manager Cinnabar Center")
        raw = reader.read()
    if raw.map_id != MapId.CINNABAR_POKECENTER or (
        raw.player_x,
        raw.player_y,
    ) != (3, 3):
        raise GoalManagerContextMaterializationError(
            "materialization did not reach the stable Cinnabar nurse boundary"
        )
    _heal(actions, reader, emulator)


def _mansion_boundary(
    actions: CountingExecutor,
    reader: PokemonRedStateReader,
    emulator: PyBoyAdapter,
) -> None:
    MANSION_TRAINING_VENUE.heal_and_return(actions, reader, emulator)
    _settle_mansion_boundary(actions, reader, emulator)


def _settle_mansion_boundary(
    actions: CountingExecutor,
    reader: PokemonRedStateReader,
    emulator: PyBoyAdapter,
) -> None:
    """Reach a released, input-ready square inside the Mansion lane."""

    for _ in range(16):
        MANSION_TRAINING_VENUE.walk_to_grass(actions, reader, emulator)
        raw = reader.read()
        if raw.battle_state:
            _protected_flee(emulator, actions, reader, raw)
            raw = reader.read()
        if (
            raw.map_id == MapId.POKEMON_MANSION_1F
            and raw.player_x is not None
            and raw.player_y is not None
            and reader.read_input_readiness().ready
        ):
            return
    raise GoalManagerContextMaterializationError(
        "Mansion context did not reach a stable encounter boundary"
    )


def _acquisition_ready_boundary(
    actions: CountingExecutor,
    reader: PokemonRedStateReader,
    emulator: PyBoyAdapter,
    adapter: PokemonRedGoalStateAdapter,
    *,
    quantity: int = _ACQUISITION_GREAT_BALL_PURCHASE,
) -> None:
    """Buy a proved capture reserve, then enter the real Mansion survey lane."""

    _buy_great_ball_reserve(
        actions,
        reader,
        emulator,
        adapter,
        quantity=quantity,
        purpose="acquisition",
    )
    _move(actions, reader, MART_TO_MANSION, "goal-manager stocked Mansion")
    _require(
        reader.read(),
        MapId.POKEMON_MANSION_1F,
        (5, 27),
        "goal-manager stocked Mansion entry",
    )
    _settle_mansion_boundary(actions, reader, emulator)


def _buy_great_ball_reserve(
    actions: CountingExecutor,
    reader: PokemonRedStateReader,
    emulator: PyBoyAdapter,
    adapter: PokemonRedGoalStateAdapter,
    *,
    quantity: int,
    purpose: str,
) -> None:
    """Use the qualified Mart mechanic and prove its exact persistent delta."""

    if type(quantity) is not int or quantity <= 0:  # noqa: E721
        raise ValueError("Great Ball reserve quantity must be a positive integer")
    if not purpose:
        raise ValueError("Great Ball reserve purpose must not be empty")
    _move(actions, reader, CENTER_TO_MART, f"goal-manager {purpose} Mart")
    _require(
        reader.read(),
        MapId.CINNABAR_MART,
        (3, 7),
        f"goal-manager {purpose} Mart entry",
    )
    _move(actions, reader, ("up", "up", "left"), f"goal-manager {purpose} clerk")
    _pulse(actions, MacroActionKind.MOVE, "left", 120)
    before = reader.read()
    before_inventory = dict(before.bag_items or ())
    before_money = before.player_money
    purchase = RedMartPurchase(
        absolute_index=1,
        item=ItemId.GREAT_BALL,
        quantity=quantity,
        unit_price=600,
    )
    provider = RedMartResupplyGoalProvider(
        map_id=MapId.CINNABAR_MART,
        player_x=2,
        player_y=5,
        interaction_direction="left",
        purchases=(purchase,),
        actions=actions,
        reader=reader,
        emulator=emulator,
        adapter=adapter,
    )
    offer = provider.offer(adapter.observe())
    if offer.binding is None:
        raise GoalManagerContextMaterializationError(
            f"{purpose} setup could not offer its qualified Mart purchase"
        )
    report = offer.binding.execute()
    verification = offer.binding.verify(report)
    after = reader.read()
    after_inventory = dict(after.bag_items or ())
    expected_money = None if before_money is None else before_money - quantity * purchase.unit_price
    if (
        verification.status is not GoalDecisionOutcome.SUCCEEDED
        or after_inventory.get(int(ItemId.GREAT_BALL), 0)
        != before_inventory.get(int(ItemId.GREAT_BALL), 0) + quantity
        or after.player_money != expected_money
        or after.map_id != MapId.CINNABAR_MART
        or (after.player_x, after.player_y) != (2, 5)
        or not reader.read_input_readiness().ready
    ):
        raise GoalManagerContextMaterializationError(
            f"{purpose} setup did not prove its exact ball reserve"
        )


def _buy_hyper_potion_reserve(
    actions: CountingExecutor,
    reader: PokemonRedStateReader,
    emulator: PyBoyAdapter,
    adapter: PokemonRedGoalStateAdapter,
    *,
    quantity: int,
) -> None:
    """Buy one exact recovery stack and return to the stable nurse boundary."""

    if type(quantity) is not int or quantity <= 0:  # noqa: E721
        raise ValueError("Hyper Potion reserve quantity must be a positive integer")
    _move(actions, reader, CENTER_TO_MART, "goal-manager recovery Mart")
    _require(
        reader.read(),
        MapId.CINNABAR_MART,
        (3, 7),
        "goal-manager recovery Mart entry",
    )
    _move(actions, reader, ("up", "up", "left"), "goal-manager recovery clerk")
    _pulse(actions, MacroActionKind.MOVE, "left", 120)
    before = reader.read()
    before_inventory = dict(before.bag_items or ())
    before_money = before.player_money
    current_quantity = before_inventory.get(int(ItemId.HYPER_POTION), 0)
    if (
        before_money is None
        or before_money < quantity * _HYPER_POTION_PRICE
        or current_quantity + quantity > 99
        or (
            int(ItemId.HYPER_POTION) not in before_inventory
            and len(before_inventory) >= 20
        )
    ):
        raise GoalManagerContextMaterializationError(
            "recovery setup cannot afford or store its exact Hyper Potion reserve"
        )

    # Reuse the qualified provider's bounded dialogue reader, but bypass its
    # goal-level availability gate: setup may need recovery stock even when a
    # different resource category is the manager's current bottleneck.
    purchase = RedMartPurchase(
        absolute_index=_CINNABAR_HYPER_POTION_INDEX,
        item=ItemId.HYPER_POTION,
        quantity=quantity,
        unit_price=_HYPER_POTION_PRICE,
    )
    provider = RedMartResupplyGoalProvider(
        map_id=MapId.CINNABAR_MART,
        player_x=2,
        player_y=5,
        interaction_direction="left",
        purchases=(purchase,),
        actions=actions,
        reader=reader,
        emulator=emulator,
        adapter=adapter,
    )
    actions.execute(MacroAction(MacroActionKind.MOVE, "left"))
    provider._settle()  # noqa: SLF001 - setup reuses the qualified bounded dialogue gate
    provider._open_buy_list()  # noqa: SLF001
    _buy_mart_item(
        actions,
        emulator,
        DEFAULT_LAVENDER_TIMING,
        absolute_index=purchase.absolute_index,
        item=int(purchase.item),
        quantity=purchase.quantity,
        target_bag_quantity=current_quantity + quantity,
    )
    _close_menus(actions, reader, DEFAULT_LAVENDER_TIMING)
    after = reader.read()
    expected_inventory = dict(before_inventory)
    expected_inventory[int(ItemId.HYPER_POTION)] = current_quantity + quantity
    if (
        dict(after.bag_items or ()) != expected_inventory
        or after.player_money != before_money - quantity * _HYPER_POTION_PRICE
        or after.map_id != MapId.CINNABAR_MART
        or (after.player_x, after.player_y) != (2, 5)
        or not reader.read_input_readiness().ready
    ):
        raise GoalManagerContextMaterializationError(
            "recovery setup did not prove its exact Hyper Potion reserve"
        )

    _move(
        actions,
        reader,
        ("right", "down", "down") + _inverse(CENTER_TO_MART),
        "goal-manager recovery Center return",
    )
    _require(
        reader.read(),
        MapId.CINNABAR_POKECENTER,
        (3, 3),
        "goal-manager recovery nurse return",
    )


def _fill_active_box_with_real_captures(
    area: LiveWildCorridorSurveyExecutor,
    reader: PokemonRedStateReader,
    *,
    settle_capture: Callable[[], None],
    target_count: int,
) -> tuple[int, int, int]:
    """Catch into one active box until its exact pressure boundary is reached."""

    initial = reader.read_all_box_states()
    active_index = initial.current_box_index
    initial_count = initial.counts[active_index]
    if (
        not initial.storage_initialized
        or type(target_count) is not int  # noqa: E721
        or not initial_count < target_count <= RED_BOX_CAPACITY
    ):
        raise GoalManagerContextMaterializationError(
            "storage setup lacks an initialized, partially filled active box"
        )
    initial_other_counts = tuple(
        count for index, count in enumerate(initial.counts) if index != active_index
    )
    seek_steps = 0
    encounters = 0
    captures = 0
    while reader.read_all_box_states().counts[active_index] < target_count:
        encountered = area.encountered_species_ref()
        if encountered is None:
            if seek_steps >= _STORAGE_MAX_SEEK_STEPS:
                raise GoalManagerContextMaterializationError(
                    "storage setup exhausted its bounded encounter steps"
                )
            area.seek_encounter()
            seek_steps += 1
            continue
        if encounters >= _STORAGE_MAX_ENCOUNTERS:
            raise GoalManagerContextMaterializationError(
                "storage setup exhausted its bounded encounters"
            )
        encounters += 1
        before = reader.read_all_box_states()
        before_count = before.counts[active_index]
        before_species = before.boxes[active_index].species_ids
        captured = area.capture_encounter(encountered)
        if type(captured) is not bool:  # noqa: E721
            raise GoalManagerContextMaterializationError(
                "storage setup capture result is not boolean"
            )
        after = reader.read_all_box_states()
        expected_delta = 1 if captured else 0
        if captured and after.counts[active_index] == before_count:
            for _ in range(_STORAGE_CAPTURE_SETTLE_PULSES):
                settle_capture()
                after = reader.read_all_box_states()
                if after.counts[active_index] != before_count:
                    break
        after_count = after.counts[active_index]
        if (
            not after.storage_initialized
            or after.current_box_index != active_index
            or after_count != before_count + expected_delta
            or tuple(count for index, count in enumerate(after.counts) if index != active_index)
            != initial_other_counts
            or after.boxes[active_index].species_ids[expected_delta:] != before_species
        ):
            raise GoalManagerContextMaterializationError(
                "storage setup capture result disagreed with persistent box evidence"
            )
        current_hp = reader.read().party_hp or ()
        if not current_hp or not any(hp > 0 for hp in current_hp):
            raise GoalManagerContextMaterializationError(
                "storage setup lost every living party member"
            )
        captures += expected_delta
    final = reader.read_all_box_states()
    if final.counts[active_index] != target_count or captures != target_count - initial_count:
        raise GoalManagerContextMaterializationError(
            "storage setup missed its exact active-box target"
        )
    return seek_steps, encounters, captures


def _storage_ready_boundary(
    actions: CountingExecutor,
    reader: PokemonRedStateReader,
    emulator: PyBoyAdapter,
    adapter: PokemonRedGoalStateAdapter,
) -> None:
    """Create real storage pressure, heal, and present the Cinnabar PC."""

    before = reader.read()
    before_party = tuple(before.party_species_ids or ())
    before_boxes = reader.read_all_box_states()
    active_index = before_boxes.current_box_index
    if before.party_count != 6 or len(before_party) != 6:
        raise GoalManagerContextMaterializationError("storage setup requires a full living party")
    _buy_great_ball_reserve(
        actions,
        reader,
        emulator,
        adapter,
        quantity=_STORAGE_GREAT_BALL_PURCHASE,
        purpose="storage",
    )
    _move(actions, reader, MART_TO_MANSION, "goal-manager storage Mansion")
    _require(
        reader.read(),
        MapId.POKEMON_MANSION_1F,
        (5, 27),
        "goal-manager storage Mansion entry",
    )
    _settle_mansion_boundary(actions, reader, emulator)
    settled = reader.read()
    if (settled.player_x, settled.player_y) != (5, 26):
        raise GoalManagerContextMaterializationError(
            "storage setup missed the south endpoint of its Mansion lane"
        )
    while reader.read_all_box_states().counts[active_index] < (_STORAGE_TARGET_ACTIVE_BOX_COUNT):
        batch_start = reader.read_all_box_states().counts[active_index]
        batch_target = min(
            batch_start + _STORAGE_CAPTURE_BATCH,
            _STORAGE_TARGET_ACTIVE_BOX_COUNT,
        )
        area = LiveWildCorridorSurveyExecutor(
            emulator,
            actions,
            reader,
            DEFAULT_SURGE_TIMING,
            label="storage-pressure Mansion capture lane",
            forward_directions=_STORAGE_MANSION_DIRECTIONS,
            starting_endpoint="south",
            max_legs=_STORAGE_MAX_LEGS,
        )
        _fill_active_box_with_real_captures(
            area,
            reader,
            settle_capture=lambda: _pulse(
                actions,
                MacroActionKind.CANCEL,
                frames=180,
            ),
            target_count=batch_target,
        )
        captured_raw = reader.read()
        captured_hp = captured_raw.party_hp or ()
        captured_moves = captured_raw.party_moves or ()
        if (
            tuple(captured_raw.party_species_ids or ()) != before_party
            or len(captured_hp) != len(captured_moves)
            or not any(
                hp > 0 and DIG_MOVE_ID in moves
                for hp, moves in zip(captured_hp, captured_moves, strict=True)
            )
        ):
            raise GoalManagerContextMaterializationError(
                "storage setup changed its party or lost its living Dig holder"
            )
        if batch_target < _STORAGE_TARGET_ACTIVE_BOX_COUNT:
            MANSION_TRAINING_VENUE.heal_and_return(actions, reader, emulator)
            _settle_mansion_boundary(actions, reader, emulator)
            returned = reader.read()
            if (returned.player_x, returned.player_y) != (5, 26):
                raise GoalManagerContextMaterializationError(
                    "storage setup missed its Mansion endpoint after batch recovery"
                )
    captured = reader.read_all_box_states()
    if (
        captured.current_box_index != active_index
        or captured.counts[active_index] != _STORAGE_TARGET_ACTIVE_BOX_COUNT
    ):
        raise GoalManagerContextMaterializationError("storage setup missed its active-box target")
    _training_dig_to_cinnabar(actions, reader, emulator)
    _move(actions, reader, ("up",), "goal-manager storage Center entry")
    _require(
        reader.read(),
        MapId.CINNABAR_POKECENTER,
        (3, 7),
        "goal-manager storage Center",
    )
    _move(actions, reader, ("up",) * 4, "goal-manager storage nurse")
    _heal(actions, reader, emulator)
    _move(
        actions,
        reader,
        _inverse(VERMILION_PC_TO_NURSE),
        "goal-manager storage PC",
    )
    _require(reader.read(), MapId.CINNABAR_POKECENTER, (13, 4), "goal-manager storage PC")
    _pulse(actions, MacroActionKind.MOVE, "up", 60)
    final = reader.read()
    final_boxes = reader.read_all_box_states()
    if (
        final.battle_state
        or final.party_hp != final.party_max_hp
        or tuple(final.party_species_ids or ()) != before_party
        or final_boxes != captured
        or final_boxes.current_box_index != active_index
        or final_boxes.counts[active_index] != _STORAGE_TARGET_ACTIVE_BOX_COUNT
        or not reader.read_input_readiness().ready
    ):
        raise GoalManagerContextMaterializationError(
            "storage setup did not preserve its healed PC decision boundary"
        )


def _damage_party(
    actions: CountingExecutor,
    reader: PokemonRedStateReader,
    emulator: PyBoyAdapter,
    *,
    require_field_recovery: bool,
    target_safety_pressure: float = _ACTIVE_SAFETY_PRESSURE,
    maximum_safety_pressure: float | None = None,
) -> None:
    source = reader.read()
    species = source.party_species_ids or ()
    levels = source.party_levels or ()
    hp = source.party_hp or ()
    maximum = source.party_max_hp or ()
    if not (
        species
        and len(species) == len(levels) == len(hp) == len(maximum)
        and all(
            current > 0 and current == limit for current, limit in zip(hp, maximum, strict=True)
        )
        and _safety_pressure(source) == 0.0
    ):
        raise GoalManagerContextMaterializationError(
            "damage materialization requires a complete healthy party observation"
        )
    _mansion_boundary(actions, reader, emulator)
    _damage_party_at_mansion(
        actions,
        reader,
        emulator,
        require_field_recovery=require_field_recovery,
        target_safety_pressure=target_safety_pressure,
        maximum_safety_pressure=maximum_safety_pressure,
    )


def _damage_party_at_mansion(
    actions: CountingExecutor,
    reader: PokemonRedStateReader,
    emulator: PyBoyAdapter,
    *,
    require_field_recovery: bool,
    target_safety_pressure: float,
    maximum_safety_pressure: float | None,
) -> None:
    """Create a bounded, living damage state from a stable Mansion lane."""

    _validate_damage_band(target_safety_pressure, maximum_safety_pressure)
    source = reader.read()
    species = source.party_species_ids or ()
    levels = source.party_levels or ()
    hp = source.party_hp or ()
    maximum = source.party_max_hp or ()
    if not (
        source.map_id == MapId.POKEMON_MANSION_1F
        and species
        and len(species) == len(levels) == len(hp) == len(maximum)
        and all(
            current > 0 and current == limit for current, limit in zip(hp, maximum, strict=True)
        )
        and _safety_pressure(source) == 0.0
    ):
        raise GoalManagerContextMaterializationError(
            "Mansion damage setup requires a complete healthy party boundary"
        )
    for _ in range(48):
        raw = reader.read()
        if _damage_context_ready(
            raw,
            require_field_recovery=require_field_recovery,
            target_safety_pressure=target_safety_pressure,
        ):
            if (
                maximum_safety_pressure is not None
                and _safety_pressure(raw) > maximum_safety_pressure
            ):
                raise GoalManagerContextMaterializationError(
                    "damage materialization exceeded its closed safety-pressure band"
                )
            return
        MANSION_TRAINING_VENUE.walk_to_grass(actions, reader, emulator)
        raw = reader.read()
        if raw.battle_state:
            fastest_index = max(
                range(len(levels)),
                key=lambda index: (levels[index], hp[index], -index),
            )
            for _ in range(_DAMAGE_SWITCH_LIMIT):
                raw = reader.read()
                _require_safe_damage_state(raw)
                if _safety_pressure(raw) >= target_safety_pressure:
                    break
                active_index = raw.active_party_index
                if active_index is None:
                    raise GoalManagerContextMaterializationError(
                        "damage materialization lost the active party index"
                    )
                current_hp = raw.party_hp or ()
                if (
                    _safety_pressure(raw) >= max(0.0, target_safety_pressure - 0.05)
                    and active_index != fastest_index
                ):
                    target_index = fastest_index
                else:
                    target_index = max(
                        (index for index in range(len(current_hp)) if index != active_index),
                        key=lambda index: (current_hp[index], levels[index], -index),
                    )
                try:
                    switch_active_battler(
                        actions,
                        reader,
                        emulator,
                        target_index,
                        expected_battle_state=1,
                        label="goal-manager controlled wild damage",
                        wait_frames=120,
                    )
                except ProtectedRecoveryError:
                    # Roar and Teleport can end an ordinary wild battle during
                    # the opponent's switch turn.  That is a legitimate
                    # cartridge exit, not proof that the protected switch
                    # itself failed, provided the battle really ended and the
                    # complete living party still verifies.
                    ended = reader.read()
                    _require_safe_damage_state(ended)
                    if ended.battle_state == 0:
                        break
                    raise
            # A weak encounter may exhaust its bounded switch window before it
            # can create the requested whole-party pressure.  Leave it safely
            # and continue through the already-bounded encounter loop instead
            # of treating one opponent as the entire setup budget.
            raw = reader.read()
            _require_safe_damage_state(raw)
            if raw.battle_state == 0:
                continue
            if raw.active_party_index != fastest_index:
                try:
                    switch_active_battler(
                        actions,
                        reader,
                        emulator,
                        fastest_index,
                        expected_battle_state=1,
                        label="goal-manager safe escape lead",
                        wait_frames=120,
                    )
                except ProtectedRecoveryError:
                    ended = reader.read()
                    _require_safe_damage_state(ended)
                    if ended.battle_state == 0:
                        continue
                    raise
                raw = reader.read()
            _protected_flee(emulator, actions, reader, raw)
        _require_safe_damage_state(reader.read())
    raise GoalManagerContextMaterializationError(
        "bounded wild encounters did not reach active safety pressure"
    )


def _safety_pressure(raw: RawGameState) -> float:
    return float(1.0 - party_safety_satisfaction(party_observation_from_raw(raw)))


def _require_safe_damage_state(raw: RawGameState) -> None:
    current_hp = raw.party_hp or ()
    current_maximum = raw.party_max_hp or ()
    current_status = raw.party_status or ()
    if (
        not current_hp
        or len(current_hp) != len(current_maximum)
        or len(current_hp) != len(current_status)
    ):
        raise GoalManagerContextMaterializationError(
            "damage materialization lost complete party evidence"
        )
    if any(value <= 0 for value in current_hp):
        raise GoalManagerContextMaterializationError(
            "damage materialization allowed a party member to faint"
        )


def _damage_context_ready(
    raw: RawGameState,
    *,
    require_field_recovery: bool,
    target_safety_pressure: float = _ACTIVE_SAFETY_PRESSURE,
) -> bool:
    _require_safe_damage_state(raw)
    _validate_damage_band(target_safety_pressure, None)
    if _safety_pressure(raw) < target_safety_pressure:
        return False
    if not require_field_recovery:
        return True
    try:
        plan = plan_party_recovery(
            tuple(raw.party_hp or ()),
            tuple(raw.party_max_hp or ()),
            tuple(raw.party_status or ()),
        )
    except FieldRecoveryError:
        return False
    inventory = dict(raw.bag_items or ())
    required = Counter(item for _, item in plan)
    return all(inventory.get(int(item), 0) >= quantity for item, quantity in required.items())


def _validate_damage_band(
    target_safety_pressure: float,
    maximum_safety_pressure: float | None,
) -> None:
    if (
        isinstance(target_safety_pressure, bool)
        or not isinstance(target_safety_pressure, (int, float))
        or not 0.0 < float(target_safety_pressure) < 1.0
    ):
        raise GoalManagerContextMaterializationError(
            "damage target must be strictly between zero and one"
        )
    if maximum_safety_pressure is None:
        return
    if (
        isinstance(maximum_safety_pressure, bool)
        or not isinstance(maximum_safety_pressure, (int, float))
        or not float(target_safety_pressure) <= float(maximum_safety_pressure) < 1.0
    ):
        raise GoalManagerContextMaterializationError(
            "damage maximum must contain the target below one"
        )


def _return_damaged_party_to_center(
    actions: CountingExecutor,
    reader: PokemonRedStateReader,
    emulator: PyBoyAdapter,
    *,
    pc_boundary: bool,
) -> None:
    """Leave damage intact while returning through qualified Dig/Fly movement."""

    _training_dig_to_cinnabar(actions, reader, emulator)
    _move(actions, reader, ("up",), "goal-manager damaged Center entry")
    _require(
        reader.read(),
        MapId.CINNABAR_POKECENTER,
        (3, 7),
        "goal-manager damaged Center",
    )
    _move(actions, reader, ("up",) * 4, "goal-manager damaged nurse")
    _require_safe_damage_state(reader.read())
    if not pc_boundary:
        return
    _move(
        actions,
        reader,
        _inverse(VERMILION_PC_TO_NURSE),
        "goal-manager damaged PC",
    )
    _require(reader.read(), MapId.CINNABAR_POKECENTER, (13, 4), "goal-manager damaged PC")
    _pulse(actions, MacroActionKind.MOVE, "up", 60)


def _evolved_team_boundary(
    actions: CountingExecutor,
    reader: PokemonRedStateReader,
    emulator: PyBoyAdapter,
) -> None:
    before = reader.read()
    before_species = tuple(before.party_species_ids or ())
    before_levels = tuple(before.party_levels or ())
    if (
        BLASTOISE_SPECIES_ID not in before_species
        or DIGLETT_SPECIES_ID not in before_species
        or DUGTRIO_SPECIES_ID in before_species
        or len(before_species) != len(before_levels)
    ):
        raise GoalManagerContextMaterializationError(
            "evolved-team setup requires the unevolved qualified party"
        )
    policy = red_team_development_quantum_policy(
        party_observation_from_raw(before),
        RedGoalManagerConfig(),
        kind=GoalKind.EVOLVE_SPECIES,
    )
    run_red_team_balancing(
        actions,
        reader,
        emulator,
        policy=policy,
        venues=(
            ROUTE_11_TRAINING_VENUE,
            DIGLETTS_CAVE_TRAINING_VENUE,
            MANSION_TRAINING_VENUE,
        ),
        intent=MANSION_BALANCED_TEAM_TRAINING_INTENT,
        flee_timing=MANSION_TRAINING_FLEE_TIMING,
        hideout_timing=DEFAULT_HIDEOUT_TIMING,
        flee_func=cast(Callable[..., None], _timed_flee),
        volatile_enemy_species=MANSION_VOLATILE_ENEMY_SPECIES,
        escort_enemy_species=MANSION_ESCORT_ENEMY_SPECIES,
        max_consecutive_flees=MANSION_MAX_CONSECUTIVE_FLEES,
        cancel_interval=MANSION_LEVEL_UP_MOVE_CANCEL_INTERVAL,
        evolution_target=(DIGLETT_SPECIES_ID, DUGTRIO_SPECIES_ID),
        report_label="goal-manager evolved-team setup",
        checkpoint_count=1,
    )
    evolved = reader.read()
    target_index = _targeted_evolution_index(
        before_species,
        tuple(evolved.party_species_ids or ()),
        source_species_id=DIGLETT_SPECIES_ID,
        target_species_id=DUGTRIO_SPECIES_ID,
    )
    evolved_species = tuple(evolved.party_species_ids or ())
    evolved_levels = tuple(evolved.party_levels or ())
    _require_safe_damage_state(evolved)
    if (
        target_index is None
        or len(evolved_levels) != len(before_levels)
        or evolved_levels[target_index] <= before_levels[target_index]
        or evolved.battle_state
        or not reader.read_input_readiness().ready
    ):
        raise GoalManagerContextMaterializationError(
            "evolved-team setup did not reach its exact transformation boundary"
        )
    if evolved.map_id != MapId.CINNABAR_POKECENTER:
        _training_dig_to_cinnabar(actions, reader, emulator)
        _move(actions, reader, ("up",), "evolved-team Center entry")
        _require(
            reader.read(),
            MapId.CINNABAR_POKECENTER,
            (3, 7),
            "evolved-team Center",
        )
    center = reader.read()
    if (center.player_x, center.player_y) != (3, 3):
        _move(actions, reader, ("up",) * 4, "evolved-team nurse")
    _heal(actions, reader, emulator)
    final = reader.read()
    _require_safe_damage_state(final)
    if (
        tuple(final.party_species_ids or ()) != evolved_species
        or tuple(final.party_levels or ()) != evolved_levels
        or final.map_id != MapId.CINNABAR_POKECENTER
        or (final.player_x, final.player_y) != (3, 3)
        or not reader.read_input_readiness().ready
    ):
        raise GoalManagerContextMaterializationError(
            "evolved-team relocation changed the party or missed the stable Center boundary"
        )


def _apply_mode(
    mode: str,
    actions: CountingExecutor,
    reader: PokemonRedStateReader,
    emulator: PyBoyAdapter,
    adapter: PokemonRedGoalStateAdapter,
    *,
    great_ball_quantity: int | None,
    hyper_potion_quantity: int | None,
    target_safety_pressure: float | None,
    maximum_safety_pressure: float | None,
) -> None:
    if great_ball_quantity is not None and (
        mode not in {"acquisition-ready", "acquisition-damaged"}
        or great_ball_quantity <= 0
    ):
        raise GoalManagerContextMaterializationError(
            "Great Ball quantity is valid only for acquisition modes"
        )
    if hyper_potion_quantity is not None and (
        mode not in {"acquisition-damaged", "damaged-field", "damaged-pc"}
        or hyper_potion_quantity <= 0
    ):
        raise GoalManagerContextMaterializationError(
            "Hyper Potion quantity is valid only for field-recovery damage modes"
        )
    if mode not in _DAMAGE_MODES and (
        target_safety_pressure is not None or maximum_safety_pressure is not None
    ):
        raise GoalManagerContextMaterializationError(
            "safety-pressure bounds are valid only for damage modes"
        )
    damage_target = (
        _ACTIVE_SAFETY_PRESSURE
        if target_safety_pressure is None
        else target_safety_pressure
    )
    if mode in _DAMAGE_MODES:
        _validate_damage_band(
            damage_target,
            maximum_safety_pressure,
        )
    if mode == "stable":
        raw = reader.read()
        if raw.battle_state or not reader.read_input_readiness().ready:
            raise GoalManagerContextMaterializationError(
                "stable materialization requires a released overworld boundary"
            )
        actions.execute(MacroAction(MacroActionKind.WAIT))
        return
    if mode == "story-resource-scarce":
        _story_resource_scarce_boundary(actions, reader, emulator)
        return
    _normalize_cinnabar_nurse(actions, reader, emulator)
    if hyper_potion_quantity is not None:
        _buy_hyper_potion_reserve(
            actions,
            reader,
            emulator,
            adapter,
            quantity=hyper_potion_quantity,
        )
    if mode == "center":
        return
    if mode == "mansion":
        _mansion_boundary(actions, reader, emulator)
        return
    if mode == "acquisition-ready":
        _acquisition_ready_boundary(
            actions,
            reader,
            emulator,
            adapter,
            quantity=great_ball_quantity or _ACQUISITION_GREAT_BALL_PURCHASE,
        )
        return
    if mode == "acquisition-damaged":
        _acquisition_ready_boundary(
            actions,
            reader,
            emulator,
            adapter,
            quantity=great_ball_quantity or _ACQUISITION_GREAT_BALL_PURCHASE,
        )
        _damage_party_at_mansion(
            actions,
            reader,
            emulator,
            require_field_recovery=True,
            target_safety_pressure=damage_target,
            maximum_safety_pressure=maximum_safety_pressure,
        )
        return
    if mode == "storage-ready":
        _storage_ready_boundary(actions, reader, emulator, adapter)
        return
    if mode == "mart":
        _move(actions, reader, CENTER_TO_MART, "goal-manager Cinnabar Mart")
        _require(reader.read(), MapId.CINNABAR_MART, (3, 7), "goal-manager Mart entry")
        _move(actions, reader, ("up", "up", "left"), "goal-manager Mart clerk")
        _pulse(actions, MacroActionKind.MOVE, "left", 120)
        return
    if mode == "pc":
        _move(
            actions,
            reader,
            _inverse(VERMILION_PC_TO_NURSE),
            "goal-manager Center PC",
        )
        _require(reader.read(), MapId.CINNABAR_POKECENTER, (13, 4), "goal-manager PC")
        _pulse(actions, MacroActionKind.MOVE, "up", 60)
        return
    if mode == "blocked-movement":
        actions.execute(MacroAction(MacroActionKind.MOVE, "down"))
        if reader.read_input_readiness().ready:
            raise GoalManagerContextMaterializationError(
                "released movement pulse did not create a blocked-control context"
            )
        return
    if mode == "evolved-team":
        _evolved_team_boundary(actions, reader, emulator)
        return
    if mode in {"damaged-field", "damaged-center", "damaged-pc"}:
        boxes_before = reader.read_all_box_states() if mode == "damaged-pc" else None
        _damage_party(
            actions,
            reader,
            emulator,
            require_field_recovery=mode in {"damaged-field", "damaged-pc"},
            target_safety_pressure=damage_target,
            maximum_safety_pressure=maximum_safety_pressure,
        )
        if mode in {"damaged-center", "damaged-pc"}:
            _return_damaged_party_to_center(
                actions,
                reader,
                emulator,
                pc_boundary=mode == "damaged-pc",
            )
        if boxes_before is not None and reader.read_all_box_states() != boxes_before:
            raise GoalManagerContextMaterializationError(
                "PC damage setup changed collection storage"
            )
        return
    raise GoalManagerContextMaterializationError("materialization mode is unsupported")


def _run(args: argparse.Namespace) -> dict[str, object]:
    if args.speed is not None and not args.watch:
        raise GoalManagerContextMaterializationError("--speed requires --watch")
    source = detect_source_identity(PROJECT_ROOT, include_untracked=True)
    require_clean_source(source)
    require_published_source(PROJECT_ROOT, source)
    registry = load_committed_goal_manager_registry(PROJECT_ROOT)
    if (
        source.git_commit != registry.execution.source_commit
        or working_source_bundle_sha256(PROJECT_ROOT) != registry.execution.source_bundle_sha256
    ):
        raise GoalManagerContextMaterializationError(
            "working source differs from the committed goal-manager registry"
        )

    rom_path = resolve_rom_path(args.rom)
    verify_rom(rom_path)
    out_state = _new_external_output(args.out_state, rom_path)
    state_path = args.state.resolve()
    envelope_path = (args.envelope or Path(f"{state_path}.json")).resolve()
    capture = open_goal_manager_context_capture(state_path, envelope_path)
    state_before = hashlib.sha256(state_path.read_bytes()).hexdigest()
    envelope_before = hashlib.sha256(envelope_path.read_bytes()).hexdigest()
    adjacent_before = rom_adjacent_artifacts(rom_path)

    with PyBoyAdapter(rom_path, watch=args.watch, speed=args.speed) as emulator:
        emulator.load_state_bytes(capture.state_bytes)
        reader = PokemonRedStateReader(emulator)
        observer = CapturedPokemonRedObserver(reader, COMPLETION_QUEST, capture.envelope)
        adapter = PokemonRedGoalStateAdapter(reader, observer, COMPLETION_QUEST)
        completed_before = COMPLETION_QUEST.completed_ids(observer.observe())
        timing = (
            ControllerTiming()
            if args.mode == "blocked-movement"
            else DEFAULT_NEW_GAME_TIMING.controller_timing()
        )
        controller = FrameSafeExecutor(emulator, timing)
        actions = CountingExecutor(controller)
        _apply_mode(
            args.mode,
            actions,
            reader,
            emulator,
            adapter,
            great_ball_quantity=args.great_ball_quantity,
            hyper_potion_quantity=args.hyper_potion_quantity,
            target_safety_pressure=args.target_safety_pressure,
            maximum_safety_pressure=args.maximum_safety_pressure,
        )
        final = reader.read()
        completed_after = COMPLETION_QUEST.completed_ids(observer.observe())
        if (
            final.battle_state
            or completed_after != completed_before
            or not emulator.pressed_buttons == frozenset()
        ):
            raise GoalManagerContextMaterializationError(
                "materialization changed story, retained input, or ended in battle"
            )
        if args.mode != "blocked-movement" and not reader.read_input_readiness().ready:
            raise GoalManagerContextMaterializationError(
                "materialization did not end at a stable control boundary"
            )
        final_input_ready = reader.read_input_readiness().ready
        emulator.save_state(out_state)
        output = write_captured_progress(
            Path(f"{out_state}.json"),
            state_path=out_state,
            checkpoint_id=args.context_id,
            checkpoint_label=f"Goal-manager {args.mode} mechanic boundary",
            checkpoints_completed=capture.envelope.checkpoints_completed,
            checkpoints_total=capture.envelope.checkpoints_total,
            verified_objective_ids=capture.envelope.verified_objective_ids,
        )

    if (
        hashlib.sha256(state_path.read_bytes()).hexdigest() != state_before
        or hashlib.sha256(envelope_path.read_bytes()).hexdigest() != envelope_before
        or rom_adjacent_artifacts(rom_path) != adjacent_before
    ):
        raise GoalManagerContextMaterializationError(
            "source capture or ROM-adjacent artifacts changed during materialization"
        )
    return {
        "schema": "pokemon-red-goal-manager-context-materialization-v1",
        "status": "complete",
        "counted": False,
        "episode_created": False,
        "mode": args.mode,
        "capture_id": output.checkpoint_id,
        "state_sha256": output.state_sha256,
        "actions_executed": actions.actions_executed,
        "map_id": int(final.map_id or 0),
        "coordinate": [final.player_x, final.player_y],
        "input_ready": final_input_ready,
        "safety_pressure": _safety_pressure(final),
    }


def main(argv: list[str] | None = None) -> int:
    parser = _parser()
    args = parser.parse_args(argv)
    try:
        summary = _run(args)
    except (
        BlaineChapterError,
        CeladonChapterError,
        CapturedProgressError,
        EmulatorError,
        EvaluationIdentityError,
        FieldRecoveryError,
        GoalManagerContextCatalogError,
        GoalManagerContextMaterializationError,
        GoalManagerProtocolError,
        ProtectedRecoveryError,
        ResumedStateError,
        RomValidationError,
        SurgeChapterError,
        OSError,
    ):
        parser.error("Goal-manager materialization failed closed; private paths were withheld.")
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
