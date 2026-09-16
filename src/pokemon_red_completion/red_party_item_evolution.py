"""Bounded PARTY-ONLY item/stone evolution executor.

Missing registrations require reusable item/stone evolution, not leveling
everything or species-specific routes. This is a controller capability draft,
not a learned policy, trained model, available boxed executor, or completed
mechanic.

Capability Limitations:
- Party-only scope: operates strictly on active party members (slots 0-5). This
  executor provides no box transport, PC retrieval, deposit, or withdraw logic.
- Precursor and specimen selection: caller remains responsible for selecting a
  safe, unreserved party slot whose evolution is authorized by the active
  registration policy.
- Genuine menu integration limitation: Pokémon Red's RAM does not provide
  explicit semantic fields for intermediate bag menu sub-states (e.g. distinguishing
  the 'USE' cursor from 'TOSS' on an open item window, or detecting live animation
  frames). This draft executes the bounded menu action sequences from lavender
  helpers and validates pre-conditions, cursor targeting, party identity,
  inventory deltas, and field stability directly before and after execution.
  Proof of end-to-end controller menu reliability requires live emulator
  qualification.
- No item purchasing or funding: stones must already be present in the bag.
- Move-learning stone evolution unsupported:
  In Pokémon Red (pokered engine/pokemon/evos_moves.asm:209), LearnMoveFromLevelUp
  is called unconditionally after evolution without a method check, testing the
  evolved species' learnset at its current level. This draft preserves moves
  strictly and does NOT support stone evolutions that trigger move-learning;
  Codex will add safe cartridge-derived admission before live integration.
  Do not add speculative confirmation pulses or weaken move preservation to
  accept arbitrary changes.
- Evolution modal mechanics:
  Evolution in Pokémon Red directly updates the Pokédex owned and seen flags
  in RAM without invoking a ShowPokedexData modal. ItemUseEvoStone removes the
  item from the bag only after TryEvolvingMon returns successfully.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass

from .actions import MacroActionKind
from .collection import CollectionObservation
from .executor import CountingExecutor
from .gen1_cartridge import EvolutionMethod, evolution_graph, internal_to_dex
from .lavender import (
    DEFAULT_LAVENDER_TIMING,
    EmulatorState,
    LavenderChapterError,
    LavenderTiming,
    _close_menus,
    _open_bag,
    _pulse,
    _select_bag_item,
    _select_cursor,
)
from .observation import PokemonRedStateReader, RawGameState
from .red_collection import red_species_ref
from .red_registration_policy import RedRegistrationPolicy


class RedPartyItemEvolutionError(RuntimeError):
    """Base exception for Red party item evolution failures."""


class RedPartyItemEvolutionValidationError(RedPartyItemEvolutionError, ValueError):
    """Raised before any input when request, party slot, item, or policy state is invalid."""


class RedPartyItemEvolutionExecutionError(RedPartyItemEvolutionError):
    """Raised when menu navigation, cursor selection, or confirmation fails."""


class RedPartyItemEvolutionTimeoutError(RedPartyItemEvolutionExecutionError):
    """Raised when evolution does not complete within bounded confirmation pulses."""


class RedPartyItemEvolutionVerificationError(RedPartyItemEvolutionExecutionError):
    """Raised when post-evolution party, bag, pokedex, or policy verification fails."""


@dataclass(frozen=True, slots=True)
class RedPartyItemEvolutionRequest:
    """Request to evolve a specific party slot using a stone/item.

    Attributes:
        rom: Supplied cartridge ROM bytes used to derive evolution graph and dex mappings.
        party_slot: Zero-indexed party slot (0-5) containing the source Pokémon.
        source_national: National Pokédex number of the unevolved party member (1-151).
        target_national: National Pokédex number of the expected evolved species (1-151).
        item_id: Item identifier of the evolution stone (e.g. ItemId.THUNDER_STONE).
    """

    rom: bytes
    party_slot: int
    source_national: int
    target_national: int
    item_id: int

    def __post_init__(self) -> None:
        if (
            type(self.party_slot) is not int
            or isinstance(self.party_slot, bool)
            or not 0 <= self.party_slot < 6
        ):
            raise RedPartyItemEvolutionValidationError(
                f"party_slot must be an integer between 0 and 5, got {self.party_slot!r}"
            )
        if (
            type(self.source_national) is not int
            or isinstance(self.source_national, bool)
            or not 1 <= self.source_national <= 151
        ):
            raise RedPartyItemEvolutionValidationError(
                "source_national must be a National Pokédex "
                f"integer 1..151, got {self.source_national!r}"
            )
        if (
            type(self.target_national) is not int
            or isinstance(self.target_national, bool)
            or not 1 <= self.target_national <= 151
        ):
            raise RedPartyItemEvolutionValidationError(
                "target_national must be a National Pokédex "
                f"integer 1..151, got {self.target_national!r}"
            )
        if type(self.item_id) is not int or isinstance(self.item_id, bool) or self.item_id <= 0:
            raise RedPartyItemEvolutionValidationError(
                f"item_id must be a positive integer, got {self.item_id!r}"
            )
        if not isinstance(self.rom, (bytes, bytearray)) or len(self.rom) == 0:
            raise RedPartyItemEvolutionValidationError("rom must be non-empty bytes")


@dataclass(frozen=True, slots=True)
class RedPartyItemEvolutionResult:
    """Result report from executing an item/stone evolution on a party member."""

    success: bool
    party_slot: int
    source_national: int
    target_national: int
    item_id: int
    actions_executed: int
    before_party_species: tuple[int, ...]
    after_party_species: tuple[int, ...]
    before_stone_count: int
    after_stone_count: int
    before_collection: CollectionObservation
    after_collection: CollectionObservation


def _bag_counts(raw: RawGameState) -> dict[int, int]:
    if raw.bag_items is None:
        return {}
    counts: dict[int, int] = {}
    for item, count in raw.bag_items:
        if item in counts:
            return {}
        counts[item] = count
    return counts


def _bag_matches_evolution(
    before_bag: Mapping[int, int],
    current_bag: Mapping[int, int],
    stone_id: int,
) -> bool:
    before_stone = before_bag.get(stone_id, 0)
    current_stone = current_bag.get(stone_id, 0)
    if current_stone != before_stone - 1:
        return False
    for item, count in before_bag.items():
        if item == stone_id:
            continue
        if current_bag.get(item, 0) != count:
            return False
    for item, count in current_bag.items():
        if item == stone_id:
            continue
        if before_bag.get(item, 0) != count:
            return False
    return True


def _party_matches_evolution(
    before_party: tuple[int, ...],
    after_party: tuple[int, ...],
    slot: int,
    expected_target_internal: int,
) -> bool:
    if len(after_party) != len(before_party):
        return False
    for i, (b, a) in enumerate(zip(before_party, after_party, strict=True)):
        if i == slot:
            if a != expected_target_internal:
                return False
        else:
            if a != b:
                return False
    return True


class RedPartyItemEvolutionExecutor:
    """Bounded party-only item-evolution controller capability."""

    def __init__(
        self,
        reader: PokemonRedStateReader,
        emulator: EmulatorState,
        policy: RedRegistrationPolicy,
        observe_collection: Callable[[], CollectionObservation],
        timing: LavenderTiming = DEFAULT_LAVENDER_TIMING,
        max_evolution_confirmation_pulses: int = 64,
    ) -> None:
        if reader is None:
            raise RedPartyItemEvolutionValidationError("reader cannot be None")
        if emulator is None:
            raise RedPartyItemEvolutionValidationError("emulator cannot be None")
        if policy is None or not isinstance(policy, RedRegistrationPolicy):
            raise RedPartyItemEvolutionValidationError(
                "RedRegistrationPolicy is required and cannot be None"
            )
        if not callable(observe_collection):
            raise RedPartyItemEvolutionValidationError(
                "observe_collection callback is required and cannot be None"
            )
        if not isinstance(timing, LavenderTiming):
            raise RedPartyItemEvolutionValidationError("timing must be a LavenderTiming instance")
        if (
            type(max_evolution_confirmation_pulses) is not int
            or isinstance(max_evolution_confirmation_pulses, bool)
            or not 1 <= max_evolution_confirmation_pulses <= 64
        ):
            raise RedPartyItemEvolutionValidationError(
                "max_evolution_confirmation_pulses must be an integer between 1 and 64"
            )

        self.reader = reader
        self.emulator = emulator
        self.policy = policy
        self.observe_collection = observe_collection
        self.timing = timing
        self.max_evolution_confirmation_pulses = max_evolution_confirmation_pulses

    def execute(
        self,
        actions: CountingExecutor,
        request: RedPartyItemEvolutionRequest,
    ) -> RedPartyItemEvolutionResult:
        if actions is None or not callable(getattr(actions, "execute", None)):
            raise RedPartyItemEvolutionValidationError(
                "actions must provide a callable execute method"
            )
        if not isinstance(request, RedPartyItemEvolutionRequest):
            raise RedPartyItemEvolutionValidationError(
                f"request must be a RedPartyItemEvolutionRequest, got {request!r}"
            )

        start_actions = getattr(actions, "actions_executed", 0)

        # 1. Derive dex mappings and evolution graph from the supplied ROM
        dex_map = internal_to_dex(request.rom)
        graph = evolution_graph(request.rom)

        dex_to_internal = {dex: internal for internal, dex in dex_map.items()}
        if request.target_national not in dex_to_internal:
            raise RedPartyItemEvolutionValidationError(
                f"Target national species {request.target_national} is not in ROM dex mapping"
            )
        target_internal = dex_to_internal[request.target_national]

        edges = graph.get(request.source_national, ())
        matching_target_edges = [e for e in edges if e.to_species == request.target_national]
        if not matching_target_edges:
            raise RedPartyItemEvolutionValidationError(
                f"Species {request.source_national} has no evolution to {request.target_national}"
            )

        matching_stone_edges = [
            e
            for e in matching_target_edges
            if e.method is EvolutionMethod.STONE and e.requirement == request.item_id
        ]
        if not matching_stone_edges:
            found = [f"{e.method.value}({e.requirement})" for e in matching_target_edges]
            raise RedPartyItemEvolutionValidationError(
                f"Evolution {request.source_national} -> {request.target_national} requires exact "
                f"STONE edge with item {request.item_id}; found edges: {found}"
            )

        # 2. Reject battle / unready state before input
        raw_before = self.reader.read()
        if raw_before.battle_state != 0:
            raise RedPartyItemEvolutionExecutionError(
                f"Cannot evolve Pokémon in battle state {raw_before.battle_state}"
            )
        readiness = self.reader.read_input_readiness()
        if not readiness.ready:
            raise RedPartyItemEvolutionExecutionError(
                "Cannot evolve Pokémon when input readiness is not ready"
            )

        # 3. Party member validation before any input
        if raw_before.party_species_ids is None:
            raise RedPartyItemEvolutionValidationError("Party species observation is unavailable")
        before_party = tuple(raw_before.party_species_ids)
        if not before_party:
            raise RedPartyItemEvolutionValidationError("Party is empty")
        if len(before_party) > 6:
            raise RedPartyItemEvolutionValidationError("Party size exceeds maximum of 6")
        if request.party_slot >= len(before_party):
            raise RedPartyItemEvolutionValidationError(
                f"party_slot {request.party_slot} exceeds party size {len(before_party)}"
            )

        source_internal = before_party[request.party_slot]
        source_dex = dex_map.get(source_internal)
        if source_dex != request.source_national:
            raise RedPartyItemEvolutionValidationError(
                f"Party slot {request.party_slot} holds internal species {source_internal} "
                f"(National {source_dex}), expected National {request.source_national}"
            )

        # Reject unknown/truncated party levels before any input
        if raw_before.party_levels is None:
            raise RedPartyItemEvolutionValidationError("Party levels observation is unavailable")
        if len(raw_before.party_levels) != len(before_party):
            raise RedPartyItemEvolutionValidationError(
                f"Party levels count {len(raw_before.party_levels)} "
                f"does not match party size {len(before_party)}"
            )
        before_party_levels = tuple(raw_before.party_levels)

        # Reject unknown/truncated party moves before any input
        if raw_before.party_moves is None:
            raise RedPartyItemEvolutionValidationError("Party moves observation is unavailable")
        if len(raw_before.party_moves) != len(before_party):
            raise RedPartyItemEvolutionValidationError(
                f"Party moves count {len(raw_before.party_moves)} "
                f"does not match party size {len(before_party)}"
            )
        for slot_idx, moves in enumerate(raw_before.party_moves):
            if not isinstance(moves, (tuple, list)) or len(moves) != 4:
                raise RedPartyItemEvolutionValidationError(
                    f"Party moves for slot {slot_idx} must have exactly 4 moves, got {moves!r}"
                )
        before_party_moves = tuple(tuple(m) for m in raw_before.party_moves)

        # 4. Bag items validation: reject unavailable bag or duplicate item rows before any input
        if raw_before.bag_items is None:
            raise RedPartyItemEvolutionValidationError("Bag items observation is unavailable")
        seen_before_bag_items: set[int] = set()
        for item_id, _ in raw_before.bag_items:
            if item_id in seen_before_bag_items:
                raise RedPartyItemEvolutionValidationError(
                    f"Duplicate bag item row detected for item {item_id}"
                )
            seen_before_bag_items.add(item_id)
        before_bag = {item: count for item, count in raw_before.bag_items}
        before_stone_count = before_bag.get(request.item_id, 0)
        if before_stone_count <= 0:
            raise RedPartyItemEvolutionValidationError(f"Item {request.item_id} is absent from bag")

        # 5. Policy check before any input
        before_collection = self.observe_collection()
        if not isinstance(before_collection, CollectionObservation):
            raise RedPartyItemEvolutionValidationError(
                "observe_collection must return a CollectionObservation"
            )

        source_ref = red_species_ref(request.source_national)
        target_ref = red_species_ref(request.target_national)

        if not self.policy.evolution_allowed(before_collection, source_ref, target_ref):
            raise RedPartyItemEvolutionValidationError(
                f"Evolution {source_ref} -> {target_ref} is not allowed by registration policy"
            )

        before_pokedex = self.reader.read_pokedex_state()

        # Capture field facts for pre/post-change invariance assertions
        before_map_id = raw_before.map_id
        before_pos = (raw_before.player_x, raw_before.player_y)
        before_money = raw_before.player_money
        before_badges = raw_before.badge_bits
        before_event_flags = raw_before.event_flags

        # 6. Execute menu interactions
        try:
            _open_bag(actions, self.emulator, self.timing)
            _select_bag_item(actions, self.emulator, request.item_id, self.timing)
            _pulse(actions, MacroActionKind.CONFIRM, frames=self.timing.wait_frames)
            _pulse(actions, MacroActionKind.CONFIRM, frames=240)
            _select_cursor(actions, self.emulator, request.party_slot, self.timing)
        except LavenderChapterError as error:
            raise RedPartyItemEvolutionExecutionError(
                f"Item evolution menu preparation failed: {error}"
            ) from error

        # 7. Strict fresh checks immediately before irreversible confirmation
        cursor_state = self.reader.read_menu_cursor_state()
        if cursor_state.selected_visible_index != request.party_slot:
            raise RedPartyItemEvolutionExecutionError(
                f"Cursor selected slot {cursor_state.selected_visible_index} "
                f"does not match requested party slot {request.party_slot} before confirmation"
            )

        raw_mid = self.reader.read()
        if raw_mid.battle_state != 0:
            raise RedPartyItemEvolutionExecutionError(
                f"Unexpected battle state {raw_mid.battle_state} before irreversible confirmation"
            )
        if raw_mid.map_id != before_map_id or (raw_mid.player_x, raw_mid.player_y) != before_pos:
            raise RedPartyItemEvolutionExecutionError(
                "Map or position changed before irreversible confirmation"
            )
        if raw_mid.player_money != before_money:
            raise RedPartyItemEvolutionExecutionError(
                "Player money changed before irreversible confirmation"
            )
        if raw_mid.badge_bits != before_badges:
            raise RedPartyItemEvolutionExecutionError(
                "Badges changed before irreversible confirmation"
            )
        if (
            before_event_flags is not None
            and raw_mid.event_flags is not None
            and raw_mid.event_flags != before_event_flags
        ):
            raise RedPartyItemEvolutionExecutionError(
                "Story event flags changed before irreversible confirmation"
            )

        if raw_mid.bag_items is None:
            raise RedPartyItemEvolutionExecutionError(
                "Bag items observation is unavailable before irreversible confirmation"
            )
        seen_mid_bag_items: set[int] = set()
        for item_id, _ in raw_mid.bag_items:
            if item_id in seen_mid_bag_items:
                raise RedPartyItemEvolutionExecutionError(
                    "Duplicate bag item row detected for item "
                    f"{item_id} before irreversible confirmation"
                )
            seen_mid_bag_items.add(item_id)
        mid_bag = {item: count for item, count in raw_mid.bag_items}
        if mid_bag.get(request.item_id, 0) != before_stone_count:
            raise RedPartyItemEvolutionExecutionError(
                f"Stone inventory count changed from {before_stone_count} to "
                f"{mid_bag.get(request.item_id, 0)} before irreversible confirmation"
            )

        if raw_mid.party_species_ids is None:
            raise RedPartyItemEvolutionExecutionError(
                "Party species observation is unavailable before irreversible confirmation"
            )
        mid_party = tuple(raw_mid.party_species_ids)
        if len(mid_party) != len(before_party) or request.party_slot >= len(mid_party):
            raise RedPartyItemEvolutionExecutionError(
                "Party size changed before irreversible confirmation"
            )
        if mid_party[request.party_slot] != source_internal:
            raise RedPartyItemEvolutionExecutionError(
                f"Selected party slot {request.party_slot} changed from {source_internal} to "
                f"{mid_party[request.party_slot]} before irreversible confirmation"
            )
        if mid_party != before_party:
            raise RedPartyItemEvolutionExecutionError(
                "Party species composition changed before irreversible confirmation"
            )

        if raw_mid.party_levels is None or len(raw_mid.party_levels) != len(before_party_levels):
            raise RedPartyItemEvolutionExecutionError(
                "Party levels shape changed before irreversible confirmation"
            )
        if tuple(raw_mid.party_levels) != before_party_levels:
            raise RedPartyItemEvolutionExecutionError(
                "Party levels changed before irreversible confirmation"
            )

        if raw_mid.party_moves is None or len(raw_mid.party_moves) != len(before_party_moves):
            raise RedPartyItemEvolutionExecutionError(
                "Party moves shape changed before irreversible confirmation"
            )
        for slot_idx, moves in enumerate(raw_mid.party_moves):
            if not isinstance(moves, (tuple, list)) or len(moves) != 4:
                raise RedPartyItemEvolutionExecutionError(
                    f"Party moves for slot {slot_idx} must have "
                    f"4 moves before confirmation, got {moves!r}"
                )
        if tuple(tuple(m) for m in raw_mid.party_moves) != before_party_moves:
            raise RedPartyItemEvolutionExecutionError(
                "Party moves changed before irreversible confirmation"
            )

        # Pulse confirmation on the selected party member
        _pulse(actions, MacroActionKind.CONFIRM, frames=240)

        # 8. Bounded evolution confirmation loop
        # The final allowed confirmation pulse must receive one final observation before timeout.
        evolved = False
        for _ in range(self.max_evolution_confirmation_pulses):
            current_raw = self.reader.read()
            current_party = tuple(current_raw.party_species_ids or ())
            current_bag = _bag_counts(current_raw)
            if _party_matches_evolution(
                before_party, current_party, request.party_slot, target_internal
            ) and _bag_matches_evolution(before_bag, current_bag, request.item_id):
                evolved = True
                break
            _pulse(actions, MacroActionKind.CONFIRM, frames=240)

        if not evolved:
            # One final observation after the final allowed confirmation pulse
            current_raw = self.reader.read()
            current_party = tuple(current_raw.party_species_ids or ())
            current_bag = _bag_counts(current_raw)
            if _party_matches_evolution(
                before_party, current_party, request.party_slot, target_internal
            ) and _bag_matches_evolution(before_bag, current_bag, request.item_id):
                evolved = True

        if not evolved:
            raise RedPartyItemEvolutionTimeoutError(
                f"Evolution did not complete within {self.max_evolution_confirmation_pulses} pulses"
            )

        try:
            _close_menus(actions, self.reader, self.timing)
        except LavenderChapterError as error:
            raise RedPartyItemEvolutionExecutionError(
                f"Closing menus after evolution failed: {error}"
            ) from error

        # 9. Post-evolution verification
        after_raw = self.reader.read()
        after_readiness = self.reader.read_input_readiness()

        if after_raw.battle_state != 0:
            raise RedPartyItemEvolutionVerificationError(
                f"Unexpected battle state {after_raw.battle_state} after evolution"
            )
        if not after_readiness.ready:
            raise RedPartyItemEvolutionVerificationError(
                "Input readiness is not ready after evolution menu closure"
            )
        if (
            after_raw.map_id != before_map_id
            or (after_raw.player_x, after_raw.player_y) != before_pos
        ):
            raise RedPartyItemEvolutionVerificationError(
                "Map or player position changed after evolution"
            )
        if after_raw.player_money != before_money:
            raise RedPartyItemEvolutionVerificationError("Player money changed after evolution")
        if after_raw.badge_bits != before_badges:
            raise RedPartyItemEvolutionVerificationError("Badge bits changed after evolution")
        if (
            before_event_flags is not None
            and after_raw.event_flags is not None
            and after_raw.event_flags != before_event_flags
        ):
            raise RedPartyItemEvolutionVerificationError(
                "Story event flags changed after evolution"
            )

        if after_raw.party_species_ids is None:
            raise RedPartyItemEvolutionVerificationError(
                "Party species observation is unavailable after evolution"
            )
        after_party = tuple(after_raw.party_species_ids)
        if not _party_matches_evolution(
            before_party, after_party, request.party_slot, target_internal
        ):
            raise RedPartyItemEvolutionVerificationError(
                f"Party after evolution {after_party} does not match expected transformation of "
                f"slot {request.party_slot} to {target_internal}"
            )

        if after_raw.party_levels is None:
            raise RedPartyItemEvolutionVerificationError(
                "Party levels observation is unavailable after evolution"
            )
        if len(after_raw.party_levels) != len(before_party_levels):
            raise RedPartyItemEvolutionVerificationError(
                "Party levels shape changed: expected "
                f"{len(before_party_levels)}, got {len(after_raw.party_levels)}"
            )

        if after_raw.party_moves is None:
            raise RedPartyItemEvolutionVerificationError(
                "Party moves observation is unavailable after evolution"
            )
        if len(after_raw.party_moves) != len(before_party_moves):
            raise RedPartyItemEvolutionVerificationError(
                "Party moves shape changed: expected "
                f"{len(before_party_moves)}, got {len(after_raw.party_moves)}"
            )
        for slot_idx, moves in enumerate(after_raw.party_moves):
            if not isinstance(moves, (tuple, list)) or len(moves) != 4:
                raise RedPartyItemEvolutionVerificationError(
                    f"Party moves for slot {slot_idx} after "
                    f"evolution must have 4 moves, got {moves!r}"
                )

        # Verify complete shapes in postchecks (strict=True, not strict=False hiding truncation)
        # Nontarget party members: unchanged levels and moves
        for i, (b_lvl, a_lvl) in enumerate(
            zip(before_party_levels, after_raw.party_levels, strict=True)
        ):
            if i != request.party_slot and a_lvl != b_lvl:
                raise RedPartyItemEvolutionVerificationError(
                    f"Nontarget party slot {i} level changed from {b_lvl} to {a_lvl}"
                )

        for i, (b_mvs, a_mvs) in enumerate(
            zip(before_party_moves, after_raw.party_moves, strict=True)
        ):
            if i != request.party_slot and tuple(a_mvs) != b_mvs:
                raise RedPartyItemEvolutionVerificationError(
                    f"Nontarget party slot {i} moves changed from {b_mvs} to {tuple(a_mvs)}"
                )

        # Verify target slot: level and moves strictly preserved
        if after_raw.party_levels[request.party_slot] != before_party_levels[request.party_slot]:
            raise RedPartyItemEvolutionVerificationError(
                f"Evolved Pokémon in slot {request.party_slot} changed level from "
                f"{before_party_levels[request.party_slot]} to "
                f"{after_raw.party_levels[request.party_slot]}"
            )
        if (
            tuple(after_raw.party_moves[request.party_slot])
            != before_party_moves[request.party_slot]
        ):
            raise RedPartyItemEvolutionVerificationError(
                f"Evolved Pokémon in slot {request.party_slot} changed moves from "
                f"{before_party_moves[request.party_slot]} to "
                f"{tuple(after_raw.party_moves[request.party_slot])}"
            )

        if after_raw.bag_items is None:
            raise RedPartyItemEvolutionVerificationError(
                "Bag items observation is unavailable after evolution"
            )
        seen_after_bag_items: set[int] = set()
        for item_id, _ in after_raw.bag_items:
            if item_id in seen_after_bag_items:
                raise RedPartyItemEvolutionVerificationError(
                    f"Duplicate bag item row detected for item {item_id} after evolution"
                )
            seen_after_bag_items.add(item_id)
        after_bag = {item: count for item, count in after_raw.bag_items}
        if not _bag_matches_evolution(before_bag, after_bag, request.item_id):
            raise RedPartyItemEvolutionVerificationError(
                f"Bag counts after evolution {after_bag} do not reflect exact one-stone consumption"
            )

        after_pokedex = self.reader.read_pokedex_state()
        if not (before_pokedex.owned_species <= after_pokedex.owned_species):
            raise RedPartyItemEvolutionVerificationError(
                "Pokedex lost previously owned species flags after evolution"
            )
        if request.target_national not in after_pokedex.owned_species:
            raise RedPartyItemEvolutionVerificationError(
                f"Target species {request.target_national} is not marked owned in Pokedex"
            )

        after_collection = self.observe_collection()
        if not isinstance(after_collection, CollectionObservation):
            raise RedPartyItemEvolutionVerificationError(
                "observe_collection must return a CollectionObservation"
            )

        if not self.policy.verify_evolution(
            before_collection, after_collection, source_ref, target_ref
        ):
            raise RedPartyItemEvolutionVerificationError(
                f"Registration policy failed to verify evolution from {source_ref} to {target_ref}"
            )

        end_actions = getattr(actions, "actions_executed", 0)
        after_stone_count = after_bag.get(request.item_id, 0)

        return RedPartyItemEvolutionResult(
            success=True,
            party_slot=request.party_slot,
            source_national=request.source_national,
            target_national=request.target_national,
            item_id=request.item_id,
            actions_executed=end_actions - start_actions,
            before_party_species=before_party,
            after_party_species=after_party,
            before_stone_count=before_stone_count,
            after_stone_count=after_stone_count,
            before_collection=before_collection,
            after_collection=after_collection,
        )


def execute_party_item_evolution(
    actions: CountingExecutor,
    reader: PokemonRedStateReader,
    emulator: EmulatorState,
    policy: RedRegistrationPolicy,
    observe_collection: Callable[[], CollectionObservation],
    request: RedPartyItemEvolutionRequest,
    timing: LavenderTiming = DEFAULT_LAVENDER_TIMING,
    max_evolution_confirmation_pulses: int = 64,
) -> RedPartyItemEvolutionResult:
    executor = RedPartyItemEvolutionExecutor(
        reader=reader,
        emulator=emulator,
        policy=policy,
        observe_collection=observe_collection,
        timing=timing,
        max_evolution_confirmation_pulses=max_evolution_confirmation_pulses,
    )
    return executor.execute(actions, request)


__all__ = [
    "RedPartyItemEvolutionError",
    "RedPartyItemEvolutionValidationError",
    "RedPartyItemEvolutionExecutionError",
    "RedPartyItemEvolutionTimeoutError",
    "RedPartyItemEvolutionVerificationError",
    "RedPartyItemEvolutionRequest",
    "RedPartyItemEvolutionResult",
    "RedPartyItemEvolutionExecutor",
    "execute_party_item_evolution",
]
