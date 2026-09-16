"""ROM-free tests for bounded party-only item evolution capability."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from typing import Any

import pytest

from pokemon_red_completion.actions import MacroAction, MacroActionKind
from pokemon_red_completion.collection import (
    CollectionLocation,
    CollectionObservation,
    LivingSpecimen,
)
from pokemon_red_completion.executor import CountingExecutor
from pokemon_red_completion.gen1_cartridge import Evolution, EvolutionMethod
from pokemon_red_completion.lavender import LavenderChapterError
from pokemon_red_completion.observation import (
    InputReadiness,
    ItemId,
    MenuCursorState,
    RawGameState,
    RedPokedexState,
)
from pokemon_red_completion.red_collection import RED_COLLECTION_GAME_ID, red_species_ref
from pokemon_red_completion.red_party_item_evolution import (
    RedPartyItemEvolutionExecutionError,
    RedPartyItemEvolutionExecutor,
    RedPartyItemEvolutionRequest,
    RedPartyItemEvolutionTimeoutError,
    RedPartyItemEvolutionValidationError,
    RedPartyItemEvolutionVerificationError,
    execute_party_item_evolution,
)
from pokemon_red_completion.red_registration_policy import RedRegistrationPolicy
from pokemon_red_completion.registration_memory import (
    RegistrationSnapshot,
    observation_from_collection,
)

# Canonical National Dex numbers and internal IDs for tests
EEVEE_DEX = 133
EEVEE_INTERNAL = 0x66
JOLTEON_DEX = 135
JOLTEON_INTERNAL = 0x68
VAPOREON_DEX = 134
VAPOREON_INTERNAL = 0x69
GROWLITHE_DEX = 58
GROWLITHE_INTERNAL = 0x8D
ARCANINE_DEX = 59
ARCANINE_INTERNAL = 0x14
WARTORTLE_DEX = 8
WARTORTLE_INTERNAL = 0xB6
BLASTOISE_DEX = 9
BLASTOISE_INTERNAL = 0x1C
KADABRA_DEX = 64
KADABRA_INTERNAL = 0x26
ALAKAZAM_DEX = 65
ALAKAZAM_INTERNAL = 0x95

# Real actual item IDs (Moon 10, Fire 32, Thunder 33, Water 34, Leaf 47)
MOON_STONE = 10
FIRE_STONE = 32
THUNDER_STONE = int(ItemId.THUNDER_STONE)  # 33 (0x21)
WATER_STONE = 34
LEAF_STONE = 47
POTION = int(ItemId.POTION)  # 20 (0x14)

TEST_DEX_MAP = {
    EEVEE_INTERNAL: EEVEE_DEX,
    JOLTEON_INTERNAL: JOLTEON_DEX,
    VAPOREON_INTERNAL: VAPOREON_DEX,
    GROWLITHE_INTERNAL: GROWLITHE_DEX,
    ARCANINE_INTERNAL: ARCANINE_DEX,
    WARTORTLE_INTERNAL: WARTORTLE_DEX,
    BLASTOISE_INTERNAL: BLASTOISE_DEX,
    KADABRA_INTERNAL: KADABRA_DEX,
    ALAKAZAM_INTERNAL: ALAKAZAM_DEX,
}

TEST_GRAPH = {
    EEVEE_DEX: (
        Evolution(EEVEE_DEX, JOLTEON_DEX, EvolutionMethod.STONE, THUNDER_STONE),
        Evolution(EEVEE_DEX, VAPOREON_DEX, EvolutionMethod.STONE, WATER_STONE),
    ),
    GROWLITHE_DEX: (Evolution(GROWLITHE_DEX, ARCANINE_DEX, EvolutionMethod.STONE, FIRE_STONE),),
    WARTORTLE_DEX: (Evolution(WARTORTLE_DEX, BLASTOISE_DEX, EvolutionMethod.LEVEL, 36),),
    KADABRA_DEX: (Evolution(KADABRA_DEX, ALAKAZAM_DEX, EvolutionMethod.TRADE, None),),
}

TEST_ROM = b"test_cartridge_rom_bytes_payload"


class MockChapterExecutor:
    def __init__(self) -> None:
        self.actions: list[MacroAction] = []

    def execute(self, action: MacroAction) -> object:
        self.actions.append(action)
        return None


class MockEmulator:
    def __init__(self) -> None:
        self.frame_count = 100
        self.pressed_buttons: frozenset[str] = frozenset()

    def read_u8(self, address: int) -> int:
        return 0


class MockReader:
    def __init__(
        self,
        raw: RawGameState,
        readiness: InputReadiness | None = None,
        cursor_state: MenuCursorState | None = None,
        pokedex_state: RedPokedexState | None = None,
    ) -> None:
        self.raw = raw
        self.readiness = readiness or InputReadiness(
            joy_ignore=0,
            simulated_joypad_index=0,
            npc_movement_script_table=0,
            player_moving_direction=0,
            status_flags_5=0,
            movement_flags=0,
            walk_counter=0,
        )
        self.cursor_state = cursor_state or MenuCursorState(
            selected_visible_index=0,
            scroll_offset=0,
            maximum_visible_index=5,
            top_x=0,
            top_y=0,
        )
        self.pokedex_state = pokedex_state or RedPokedexState(
            owned_species=frozenset([EEVEE_DEX, GROWLITHE_DEX, WARTORTLE_DEX, KADABRA_DEX]),
            seen_species=frozenset([EEVEE_DEX, GROWLITHE_DEX, WARTORTLE_DEX, KADABRA_DEX]),
        )

    def read(self) -> RawGameState:
        return self.raw

    def read_input_readiness(self) -> InputReadiness:
        return self.readiness

    def read_menu_cursor_state(self) -> MenuCursorState:
        return self.cursor_state

    def read_pokedex_state(self) -> RedPokedexState:
        return self.pokedex_state


def make_raw_state(
    party: tuple[int, ...] = (EEVEE_INTERNAL,),
    bag: tuple[tuple[int, int], ...] = ((THUNDER_STONE, 1),),
    battle_state: int = 0,
    map_id: int = 1,
    player_x: int = 5,
    player_y: int = 5,
    player_money: int = 3000,
    badge_bits: int = 0,
    event_flags: bytes = b"\x00" * 320,
    party_levels: tuple[int, ...] | None = None,
    party_moves: tuple[tuple[int, ...], ...] | None = None,
) -> RawGameState:
    count = len(party)
    levels = party_levels if party_levels is not None else (25,) * count
    moves = party_moves if party_moves is not None else tuple((33, 0, 0, 0) for _ in range(count))
    return RawGameState(
        game_started=True,
        map_id=map_id,
        player_x=player_x,
        player_y=player_y,
        party_count=count,
        battle_state=battle_state,
        badge_bits=badge_bits,
        bag_items=bag,
        event_flags=event_flags,
        party_species_ids=party,
        party_levels=levels,
        party_moves=moves,
        player_money=player_money,
    )


def make_policy_and_collection(
    owned_dex: tuple[int, ...],
    specimens: list[tuple[int, int]],
    protected: dict[str, int] | None = None,
) -> tuple[RedRegistrationPolicy, CollectionObservation]:
    mapping = {red_species_ref(n): n for n in range(1, 152)}
    living_specimens = tuple(
        LivingSpecimen(
            species_ref=red_species_ref(dex),
            level=level,
            location=CollectionLocation.PARTY,
            container_index=0,
            slot_index=i,
        )
        for i, (dex, level) in enumerate(specimens)
    )
    owned_refs = frozenset(red_species_ref(d) for d in owned_dex)
    collection = CollectionObservation(
        owned_species=owned_refs,
        specimens=living_specimens,
        party_size=len(living_specimens),
        party_limit=6,
        box_counts=(0,) * 12,
        current_box_index=0,
        box_capacity=20,
    )
    obs = observation_from_collection(
        collection,
        seen_species=collection.owned_species,
        national_ids=mapping,
        run_id="run_1",
        game_id=RED_COLLECTION_GAME_ID,
        adapter_id="red-v1",
        cartridge_sha256="a" * 64,
        snapshot_sha256="b" * 64,
        sequence=0,
    )
    policy = RedRegistrationPolicy(
        initial_memory=RegistrationSnapshot((obs,)),
        run_id="run_1",
        initial_snapshot_sha256="b" * 64,
        initial_collection=collection,
        protected_counts=protected or {},
    )
    return policy, collection


class EvolutionTestRig:
    """Phase-aware test rig ensuring state mutations occur only on party confirmation,
    not during menu preparation or bag item confirmations."""

    def __init__(
        self,
        reader: MockReader,
        collection: CollectionObservation,
        slot: int = 0,
        target_dex: int = JOLTEON_DEX,
        target_internal: int = JOLTEON_INTERNAL,
        stone_id: int = THUNDER_STONE,
        evolve_on_confirmation: int = 1,
        custom_evolution_fn: Callable[[], None] | None = None,
        custom_close_menus_fn: Callable[[CountingExecutor, Any, Any], None] | None = None,
    ) -> None:
        self.reader = reader
        self.current_collection = collection
        self.slot = slot
        self.target_dex = target_dex
        self.target_internal = target_internal
        self.stone_id = stone_id
        self.evolve_on_confirmation = evolve_on_confirmation
        self.custom_evolution_fn = custom_evolution_fn
        self.custom_close_menus_fn = custom_close_menus_fn
        self.menu_prep_done = False
        self.evolution_confirmations = 0
        self.has_evolved = False

    def fake_open_bag(self, acts: CountingExecutor, emu: Any, tim: Any) -> None:
        acts.execute(MacroAction(MacroActionKind.OPEN_MENU))

    def fake_select_bag_item(self, acts: CountingExecutor, emu: Any, item: int, tim: Any) -> None:
        acts.execute(MacroAction(MacroActionKind.MOVE, "down"))

    def fake_select_cursor(self, acts: CountingExecutor, emu: Any, target: int, tim: Any) -> None:
        acts.execute(MacroAction(MacroActionKind.MOVE, "down"))
        self.reader.cursor_state = replace(self.reader.cursor_state, selected_visible_index=target)
        self.menu_prep_done = True

    def fake_close_menus(self, acts: CountingExecutor, rdr: Any, tim: Any) -> None:
        if self.custom_close_menus_fn is not None:
            self.custom_close_menus_fn(acts, rdr, tim)
        else:
            acts.execute(MacroAction(MacroActionKind.CANCEL))

    def fake_pulse(
        self, acts: CountingExecutor, kind: MacroActionKind, value: Any = None, frames: int = 180
    ) -> None:
        acts.execute(MacroAction(kind, value))
        if kind is MacroActionKind.CONFIRM and self.menu_prep_done:
            self.evolution_confirmations += 1
            if self.evolution_confirmations >= self.evolve_on_confirmation and not self.has_evolved:
                if self.custom_evolution_fn is not None:
                    self.custom_evolution_fn()
                    self.has_evolved = True
                else:
                    self.trigger_default_evolution()

    def trigger_default_evolution(self) -> None:
        self.has_evolved = True
        party_list = list(self.reader.raw.party_species_ids or ())
        if self.slot < len(party_list):
            party_list[self.slot] = self.target_internal
        new_bag = []
        for item, count in self.reader.raw.bag_items or ():
            if item == self.stone_id:
                if count > 1:
                    new_bag.append((item, count - 1))
            else:
                new_bag.append((item, count))
        self.reader.raw = replace(
            self.reader.raw,
            party_species_ids=tuple(party_list),
            bag_items=tuple(new_bag),
        )
        self.reader.pokedex_state = replace(
            self.reader.pokedex_state,
            owned_species=self.reader.pokedex_state.owned_species | frozenset([self.target_dex]),
            seen_species=self.reader.pokedex_state.seen_species | frozenset([self.target_dex]),
        )
        specimens_list = list(self.current_collection.specimens)
        if self.slot < len(specimens_list):
            specimens_list[self.slot] = replace(
                specimens_list[self.slot],
                species_ref=red_species_ref(self.target_dex),
            )
        self.current_collection = replace(
            self.current_collection,
            owned_species=self.current_collection.owned_species
            | frozenset([red_species_ref(self.target_dex)]),
            specimens=tuple(specimens_list),
        )

    def observe(self) -> CollectionObservation:
        return self.current_collection

    def install(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(
            "pokemon_red_completion.red_party_item_evolution._open_bag", self.fake_open_bag
        )
        monkeypatch.setattr(
            "pokemon_red_completion.red_party_item_evolution._select_bag_item",
            self.fake_select_bag_item,
        )
        monkeypatch.setattr(
            "pokemon_red_completion.red_party_item_evolution._select_cursor",
            self.fake_select_cursor,
        )
        monkeypatch.setattr(
            "pokemon_red_completion.red_party_item_evolution._close_menus", self.fake_close_menus
        )
        monkeypatch.setattr(
            "pokemon_red_completion.red_party_item_evolution._pulse", self.fake_pulse
        )


@pytest.fixture(autouse=True)
def patch_cartridge_derivations(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "pokemon_red_completion.red_party_item_evolution.internal_to_dex",
        lambda rom: TEST_DEX_MAP,
    )
    monkeypatch.setattr(
        "pokemon_red_completion.red_party_item_evolution.evolution_graph",
        lambda rom: TEST_GRAPH,
    )


def test_cheapest_falsifier_wrong_item_emits_zero_actions() -> None:
    executor = MockChapterExecutor()
    actions = CountingExecutor(executor)
    reader = MockReader(make_raw_state(party=(EEVEE_INTERNAL,), bag=((FIRE_STONE, 1),)))
    emulator = MockEmulator()
    policy, collection = make_policy_and_collection((EEVEE_DEX,), [(EEVEE_DEX, 25)])

    request = RedPartyItemEvolutionRequest(
        rom=TEST_ROM,
        party_slot=0,
        source_national=EEVEE_DEX,
        target_national=JOLTEON_DEX,
        item_id=FIRE_STONE,  # Wrong stone: Eevee -> Jolteon requires Thunder Stone
    )

    runner = RedPartyItemEvolutionExecutor(reader, emulator, policy, lambda: collection)
    with pytest.raises(RedPartyItemEvolutionValidationError, match="requires exact STONE edge"):
        runner.execute(actions, request)

    assert actions.actions_executed == 0


def test_cheapest_falsifier_level_and_trade_edges_emit_zero_actions() -> None:
    executor = MockChapterExecutor()
    actions = CountingExecutor(executor)
    reader = MockReader(
        make_raw_state(
            party=(WARTORTLE_INTERNAL, KADABRA_INTERNAL),
            bag=((THUNDER_STONE, 1),),
        )
    )
    emulator = MockEmulator()
    policy, collection = make_policy_and_collection(
        (WARTORTLE_DEX, KADABRA_DEX),
        [(WARTORTLE_DEX, 30), (KADABRA_DEX, 30)],
    )

    # Level edge
    level_req = RedPartyItemEvolutionRequest(
        rom=TEST_ROM,
        party_slot=0,
        source_national=WARTORTLE_DEX,
        target_national=BLASTOISE_DEX,
        item_id=THUNDER_STONE,
    )
    runner = RedPartyItemEvolutionExecutor(reader, emulator, policy, lambda: collection)
    with pytest.raises(RedPartyItemEvolutionValidationError, match="requires exact STONE edge"):
        runner.execute(actions, level_req)

    # Trade edge
    trade_req = RedPartyItemEvolutionRequest(
        rom=TEST_ROM,
        party_slot=1,
        source_national=KADABRA_DEX,
        target_national=ALAKAZAM_DEX,
        item_id=THUNDER_STONE,
    )
    with pytest.raises(RedPartyItemEvolutionValidationError, match="requires exact STONE edge"):
        runner.execute(actions, trade_req)

    assert actions.actions_executed == 0


def test_cheapest_falsifier_wrong_slot_or_source_emits_zero_actions() -> None:
    executor = MockChapterExecutor()
    actions = CountingExecutor(executor)
    reader = MockReader(make_raw_state(party=(GROWLITHE_INTERNAL,), bag=((THUNDER_STONE, 1),)))
    emulator = MockEmulator()
    policy, collection = make_policy_and_collection((GROWLITHE_DEX,), [(GROWLITHE_DEX, 25)])

    runner = RedPartyItemEvolutionExecutor(reader, emulator, policy, lambda: collection)

    # Slot points to Growlithe, request claims Eevee
    mismatch_req = RedPartyItemEvolutionRequest(
        rom=TEST_ROM,
        party_slot=0,
        source_national=EEVEE_DEX,
        target_national=JOLTEON_DEX,
        item_id=THUNDER_STONE,
    )
    with pytest.raises(RedPartyItemEvolutionValidationError, match="Party slot 0 holds internal"):
        runner.execute(actions, mismatch_req)

    # Slot index out of party bounds
    out_of_bounds_req = RedPartyItemEvolutionRequest(
        rom=TEST_ROM,
        party_slot=3,
        source_national=EEVEE_DEX,
        target_national=JOLTEON_DEX,
        item_id=THUNDER_STONE,
    )
    with pytest.raises(RedPartyItemEvolutionValidationError, match="exceeds party size"):
        runner.execute(actions, out_of_bounds_req)

    assert actions.actions_executed == 0


def test_cheapest_falsifier_absent_item_emits_zero_actions() -> None:
    executor = MockChapterExecutor()
    actions = CountingExecutor(executor)
    reader = MockReader(make_raw_state(party=(EEVEE_INTERNAL,), bag=((POTION, 5),)))
    emulator = MockEmulator()
    policy, collection = make_policy_and_collection((EEVEE_DEX,), [(EEVEE_DEX, 25)])

    request = RedPartyItemEvolutionRequest(
        rom=TEST_ROM,
        party_slot=0,
        source_national=EEVEE_DEX,
        target_national=JOLTEON_DEX,
        item_id=THUNDER_STONE,
    )
    runner = RedPartyItemEvolutionExecutor(reader, emulator, policy, lambda: collection)
    with pytest.raises(RedPartyItemEvolutionValidationError, match="absent from bag"):
        runner.execute(actions, request)

    assert actions.actions_executed == 0


def test_cheapest_falsifier_battle_or_unready_state_emits_zero_actions() -> None:
    executor = MockChapterExecutor()
    actions = CountingExecutor(executor)
    emulator = MockEmulator()
    policy, collection = make_policy_and_collection((EEVEE_DEX,), [(EEVEE_DEX, 25)])
    request = RedPartyItemEvolutionRequest(
        rom=TEST_ROM,
        party_slot=0,
        source_national=EEVEE_DEX,
        target_national=JOLTEON_DEX,
        item_id=THUNDER_STONE,
    )

    # Battle state != 0
    battle_reader = MockReader(
        make_raw_state(party=(EEVEE_INTERNAL,), bag=((THUNDER_STONE, 1),), battle_state=1)
    )
    runner1 = RedPartyItemEvolutionExecutor(battle_reader, emulator, policy, lambda: collection)
    with pytest.raises(RedPartyItemEvolutionExecutionError, match="in battle state"):
        runner1.execute(actions, request)

    # Unready input
    unready_reader = MockReader(
        make_raw_state(party=(EEVEE_INTERNAL,), bag=((THUNDER_STONE, 1),)),
        readiness=InputReadiness(
            joy_ignore=0xFF,
            simulated_joypad_index=0,
            npc_movement_script_table=0,
            player_moving_direction=0,
            status_flags_5=0,
            movement_flags=0,
            walk_counter=0,
        ),
    )
    runner2 = RedPartyItemEvolutionExecutor(unready_reader, emulator, policy, lambda: collection)
    with pytest.raises(RedPartyItemEvolutionExecutionError, match="not ready"):
        runner2.execute(actions, request)

    assert actions.actions_executed == 0


def test_cheapest_falsifier_reserved_stock_emits_zero_actions() -> None:
    executor = MockChapterExecutor()
    actions = CountingExecutor(executor)
    reader = MockReader(make_raw_state(party=(EEVEE_INTERNAL,), bag=((THUNDER_STONE, 1),)))
    emulator = MockEmulator()
    # 1 Eevee present, but 1 Eevee is reserved in protected_counts
    policy, collection = make_policy_and_collection(
        (EEVEE_DEX,),
        [(EEVEE_DEX, 25)],
        protected={red_species_ref(EEVEE_DEX): 1},
    )

    request = RedPartyItemEvolutionRequest(
        rom=TEST_ROM,
        party_slot=0,
        source_national=EEVEE_DEX,
        target_national=JOLTEON_DEX,
        item_id=THUNDER_STONE,
    )
    runner = RedPartyItemEvolutionExecutor(reader, emulator, policy, lambda: collection)
    with pytest.raises(
        RedPartyItemEvolutionValidationError,
        match="not allowed by registration policy",
    ):
        runner.execute(actions, request)

    assert actions.actions_executed == 0


def test_cheapest_falsifier_already_registered_target_emits_zero_actions() -> None:
    executor = MockChapterExecutor()
    actions = CountingExecutor(executor)
    reader = MockReader(make_raw_state(party=(EEVEE_INTERNAL,), bag=((THUNDER_STONE, 1),)))
    emulator = MockEmulator()
    # Both Eevee and Jolteon already owned
    policy, collection = make_policy_and_collection(
        (EEVEE_DEX, JOLTEON_DEX),
        [(EEVEE_DEX, 25), (JOLTEON_DEX, 25)],
    )

    request = RedPartyItemEvolutionRequest(
        rom=TEST_ROM,
        party_slot=0,
        source_national=EEVEE_DEX,
        target_national=JOLTEON_DEX,
        item_id=THUNDER_STONE,
    )
    runner = RedPartyItemEvolutionExecutor(reader, emulator, policy, lambda: collection)
    with pytest.raises(
        RedPartyItemEvolutionValidationError,
        match="not allowed by registration policy",
    ):
        runner.execute(actions, request)

    assert actions.actions_executed == 0


def test_cheapest_falsifier_invalid_types_and_bools_emit_zero_actions() -> None:
    with pytest.raises(RedPartyItemEvolutionValidationError, match="party_slot must be an integer"):
        RedPartyItemEvolutionRequest(TEST_ROM, True, EEVEE_DEX, JOLTEON_DEX, THUNDER_STONE)  # type: ignore[arg-type]

    with pytest.raises(RedPartyItemEvolutionValidationError, match="party_slot must be an integer"):
        RedPartyItemEvolutionRequest(TEST_ROM, -1, EEVEE_DEX, JOLTEON_DEX, THUNDER_STONE)

    with pytest.raises(RedPartyItemEvolutionValidationError, match="party_slot must be an integer"):
        RedPartyItemEvolutionRequest(TEST_ROM, 6, EEVEE_DEX, JOLTEON_DEX, THUNDER_STONE)

    with pytest.raises(
        RedPartyItemEvolutionValidationError, match="item_id must be a positive integer"
    ):
        RedPartyItemEvolutionRequest(TEST_ROM, 0, EEVEE_DEX, JOLTEON_DEX, False)  # type: ignore[arg-type]

    with pytest.raises(RedPartyItemEvolutionValidationError, match="rom must be non-empty bytes"):
        RedPartyItemEvolutionRequest(b"", 0, EEVEE_DEX, JOLTEON_DEX, THUNDER_STONE)


def test_successful_transfer_party_slot_duplicate_positions_and_stone_quantity(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Transfer test:

    - party slot 3 evolved (not slot 0 or last slot)
    - duplicate positions: two Eevees at slot 1 and slot 3; slot 1 stays Eevee
    - stone quantity: 2 Thunder Stones become 1, other bag items (5 Potions) unchanged
    - real registration policy verified
    """
    initial_party = (GROWLITHE_INTERNAL, EEVEE_INTERNAL, WARTORTLE_INTERNAL, EEVEE_INTERNAL)
    initial_bag = ((THUNDER_STONE, 2), (POTION, 5))

    executor = MockChapterExecutor()
    actions = CountingExecutor(executor)
    reader = MockReader(make_raw_state(party=initial_party, bag=initial_bag))
    emulator = MockEmulator()

    policy, collection_before = make_policy_and_collection(
        (GROWLITHE_DEX, EEVEE_DEX, WARTORTLE_DEX),
        [(GROWLITHE_DEX, 20), (EEVEE_DEX, 25), (WARTORTLE_DEX, 28), (EEVEE_DEX, 25)],
    )

    current_collection = collection_before

    def observe() -> CollectionObservation:
        return current_collection

    # Deterministic fake transition for low-level menu helpers
    def fake_open_bag(acts: CountingExecutor, emu: Any, tim: Any) -> None:
        acts.execute(MacroAction(MacroActionKind.OPEN_MENU))

    def fake_select_bag_item(acts: CountingExecutor, emu: Any, item: int, tim: Any) -> None:
        acts.execute(MacroAction(MacroActionKind.MOVE, "down"))

    def fake_select_cursor(acts: CountingExecutor, emu: Any, target: int, tim: Any) -> None:
        acts.execute(MacroAction(MacroActionKind.MOVE, "down"))
        reader.cursor_state = replace(reader.cursor_state, selected_visible_index=target)

    def fake_close_menus(acts: CountingExecutor, rdr: Any, tim: Any) -> None:
        acts.execute(MacroAction(MacroActionKind.CANCEL))

    monkeypatch.setattr("pokemon_red_completion.red_party_item_evolution._open_bag", fake_open_bag)
    monkeypatch.setattr(
        "pokemon_red_completion.red_party_item_evolution._select_bag_item", fake_select_bag_item
    )
    monkeypatch.setattr(
        "pokemon_red_completion.red_party_item_evolution._select_cursor", fake_select_cursor
    )
    monkeypatch.setattr(
        "pokemon_red_completion.red_party_item_evolution._close_menus", fake_close_menus
    )

    # State transition occurs when confirmation is pulsed on the selected party member
    original_pulse = __import__(
        "pokemon_red_completion.red_party_item_evolution", fromlist=["_pulse"]
    )._pulse

    def fake_pulse(
        acts: CountingExecutor, kind: MacroActionKind, value: Any = None, frames: int = 180
    ) -> None:
        nonlocal current_collection
        original_pulse(acts, kind, value, frames)
        if kind is MacroActionKind.CONFIRM and reader.cursor_state.selected_visible_index == 3:
            # Slot 3 evolves into Jolteon, 1 Thunder Stone is consumed, Potions unchanged
            reader.raw = replace(
                reader.raw,
                party_species_ids=(
                    GROWLITHE_INTERNAL,
                    EEVEE_INTERNAL,
                    WARTORTLE_INTERNAL,
                    JOLTEON_INTERNAL,
                ),
                bag_items=((THUNDER_STONE, 1), (POTION, 5)),
            )
            reader.pokedex_state = replace(
                reader.pokedex_state,
                owned_species=reader.pokedex_state.owned_species | frozenset([JOLTEON_DEX]),
                seen_species=reader.pokedex_state.seen_species | frozenset([JOLTEON_DEX]),
            )
            # Update collection observation for observe_collection callback
            new_specimens = list(collection_before.specimens)
            new_specimens[3] = replace(new_specimens[3], species_ref=red_species_ref(JOLTEON_DEX))
            current_collection = replace(
                collection_before,
                owned_species=collection_before.owned_species
                | frozenset([red_species_ref(JOLTEON_DEX)]),
                specimens=tuple(new_specimens),
            )

    monkeypatch.setattr("pokemon_red_completion.red_party_item_evolution._pulse", fake_pulse)

    request = RedPartyItemEvolutionRequest(
        rom=TEST_ROM,
        party_slot=3,
        source_national=EEVEE_DEX,
        target_national=JOLTEON_DEX,
        item_id=THUNDER_STONE,
    )

    result = execute_party_item_evolution(actions, reader, emulator, policy, observe, request)

    assert result.success is True
    assert result.party_slot == 3
    assert result.source_national == EEVEE_DEX
    assert result.target_national == JOLTEON_DEX
    assert result.before_stone_count == 2
    assert result.after_stone_count == 1
    # Duplicate Eevee at slot 1 preserved, only slot 3 changed
    assert result.after_party_species == (
        GROWLITHE_INTERNAL,
        EEVEE_INTERNAL,
        WARTORTLE_INTERNAL,
        JOLTEON_INTERNAL,
    )
    assert result.actions_executed > 0


def test_transfer_growlithe_fire_stone_to_arcanine(monkeypatch: pytest.MonkeyPatch) -> None:
    initial_party = (GROWLITHE_INTERNAL,)
    initial_bag = ((FIRE_STONE, 1),)

    executor = MockChapterExecutor()
    actions = CountingExecutor(executor)
    reader = MockReader(make_raw_state(party=initial_party, bag=initial_bag))
    emulator = MockEmulator()

    policy, collection_before = make_policy_and_collection(
        (GROWLITHE_DEX,),
        [(GROWLITHE_DEX, 25)],
    )

    rig = EvolutionTestRig(
        reader=reader,
        collection=collection_before,
        slot=0,
        target_dex=ARCANINE_DEX,
        target_internal=ARCANINE_INTERNAL,
        stone_id=FIRE_STONE,
    )
    rig.install(monkeypatch)

    request = RedPartyItemEvolutionRequest(
        rom=TEST_ROM,
        party_slot=0,
        source_national=GROWLITHE_DEX,
        target_national=ARCANINE_DEX,
        item_id=FIRE_STONE,
    )
    result = execute_party_item_evolution(actions, reader, emulator, policy, rig.observe, request)
    assert result.success is True
    assert result.after_party_species == (ARCANINE_INTERNAL,)
    assert result.before_stone_count == 1
    assert result.after_stone_count == 0


def test_cursor_failure_rejects_before_final_confirmation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    executor = MockChapterExecutor()
    actions = CountingExecutor(executor)
    reader = MockReader(
        make_raw_state(party=(GROWLITHE_INTERNAL, EEVEE_INTERNAL), bag=((THUNDER_STONE, 1),))
    )
    emulator = MockEmulator()
    policy, collection = make_policy_and_collection(
        (GROWLITHE_DEX, EEVEE_DEX), [(GROWLITHE_DEX, 20), (EEVEE_DEX, 25)]
    )

    monkeypatch.setattr(
        "pokemon_red_completion.red_party_item_evolution._open_bag", lambda a, e, t: None
    )
    monkeypatch.setattr(
        "pokemon_red_completion.red_party_item_evolution._select_bag_item",
        lambda a, e, i, t: None,
    )

    # Fake select cursor leaves cursor at index 0 instead of intended slot 1
    def broken_select_cursor(acts: CountingExecutor, emu: Any, target: int, tim: Any) -> None:
        reader.cursor_state = replace(reader.cursor_state, selected_visible_index=0)

    monkeypatch.setattr(
        "pokemon_red_completion.red_party_item_evolution._select_cursor",
        broken_select_cursor,
    )

    request = RedPartyItemEvolutionRequest(
        rom=TEST_ROM,
        party_slot=1,
        source_national=EEVEE_DEX,
        target_national=JOLTEON_DEX,
        item_id=THUNDER_STONE,
    )

    runner = RedPartyItemEvolutionExecutor(reader, emulator, policy, lambda: collection)
    with pytest.raises(
        RedPartyItemEvolutionExecutionError,
        match="Cursor selected slot 0 does not match",
    ):
        runner.execute(actions, request)


def test_menu_navigation_error_wrapped(monkeypatch: pytest.MonkeyPatch) -> None:
    executor = MockChapterExecutor()
    actions = CountingExecutor(executor)
    reader = MockReader(make_raw_state(party=(EEVEE_INTERNAL,), bag=((THUNDER_STONE, 1),)))
    emulator = MockEmulator()
    policy, collection = make_policy_and_collection((EEVEE_DEX,), [(EEVEE_DEX, 25)])

    def failing_open_bag(acts: CountingExecutor, emu: Any, tim: Any) -> None:
        raise LavenderChapterError("Menu did not open")

    monkeypatch.setattr(
        "pokemon_red_completion.red_party_item_evolution._open_bag", failing_open_bag
    )

    request = RedPartyItemEvolutionRequest(
        rom=TEST_ROM,
        party_slot=0,
        source_national=EEVEE_DEX,
        target_national=JOLTEON_DEX,
        item_id=THUNDER_STONE,
    )
    runner = RedPartyItemEvolutionExecutor(reader, emulator, policy, lambda: collection)
    with pytest.raises(
        RedPartyItemEvolutionExecutionError,
        match="Item evolution menu preparation failed",
    ):
        runner.execute(actions, request)


def test_evolution_confirmation_timeout_raises_named_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    executor = MockChapterExecutor()
    actions = CountingExecutor(executor)
    reader = MockReader(make_raw_state(party=(EEVEE_INTERNAL,), bag=((THUNDER_STONE, 1),)))
    emulator = MockEmulator()
    policy, collection = make_policy_and_collection((EEVEE_DEX,), [(EEVEE_DEX, 25)])

    monkeypatch.setattr(
        "pokemon_red_completion.red_party_item_evolution._open_bag", lambda a, e, t: None
    )
    monkeypatch.setattr(
        "pokemon_red_completion.red_party_item_evolution._select_bag_item",
        lambda a, e, i, t: None,
    )
    monkeypatch.setattr(
        "pokemon_red_completion.red_party_item_evolution._select_cursor",
        lambda a, e, target, t: None,
    )
    reader.cursor_state = replace(reader.cursor_state, selected_visible_index=0)

    # No state change occurs during pulses
    request = RedPartyItemEvolutionRequest(
        rom=TEST_ROM,
        party_slot=0,
        source_national=EEVEE_DEX,
        target_national=JOLTEON_DEX,
        item_id=THUNDER_STONE,
    )
    runner = RedPartyItemEvolutionExecutor(
        reader, emulator, policy, lambda: collection, max_evolution_confirmation_pulses=3
    )

    with pytest.raises(
        RedPartyItemEvolutionTimeoutError,
        match="Evolution did not complete within 3 pulses",
    ):
        runner.execute(actions, request)


def test_verification_rejects_wrong_target_species(monkeypatch: pytest.MonkeyPatch) -> None:
    executor = MockChapterExecutor()
    actions = CountingExecutor(executor)
    reader = MockReader(make_raw_state(party=(EEVEE_INTERNAL,), bag=((THUNDER_STONE, 1),)))
    emulator = MockEmulator()
    policy, collection = make_policy_and_collection((EEVEE_DEX,), [(EEVEE_DEX, 25)])

    # During evolution, the slot becomes Vaporeon instead of Jolteon
    def evolve_to_wrong_species() -> None:
        reader.raw = replace(
            reader.raw,
            party_species_ids=(VAPOREON_INTERNAL,),
            bag_items=(),
        )

    rig = EvolutionTestRig(
        reader=reader,
        collection=collection,
        custom_evolution_fn=evolve_to_wrong_species,
    )
    rig.install(monkeypatch)

    request = RedPartyItemEvolutionRequest(
        rom=TEST_ROM,
        party_slot=0,
        source_national=EEVEE_DEX,
        target_national=JOLTEON_DEX,
        item_id=THUNDER_STONE,
    )
    runner = RedPartyItemEvolutionExecutor(
        reader, emulator, policy, lambda: collection, max_evolution_confirmation_pulses=2
    )

    # Loop times out because party does not match expected target Jolteon
    with pytest.raises(RedPartyItemEvolutionTimeoutError):
        runner.execute(actions, request)


def test_verification_rejects_lost_unrelated_stock(monkeypatch: pytest.MonkeyPatch) -> None:
    executor = MockChapterExecutor()
    actions = CountingExecutor(executor)
    reader = MockReader(
        make_raw_state(
            party=(EEVEE_INTERNAL, GROWLITHE_INTERNAL),
            bag=((THUNDER_STONE, 1),),
        )
    )
    emulator = MockEmulator()
    policy, collection = make_policy_and_collection(
        (EEVEE_DEX, GROWLITHE_DEX),
        [(EEVEE_DEX, 25), (GROWLITHE_DEX, 25)],
    )

    # Evolve slot 0, but slot 1 (Growlithe) mysteriously disappears after close menus
    def corrupted_close(acts: CountingExecutor, rdr: Any, tim: Any) -> None:
        acts.execute(MacroAction(MacroActionKind.CANCEL))
        reader.raw = replace(
            reader.raw,
            party_species_ids=(JOLTEON_INTERNAL,),  # Growlithe lost
            party_levels=(25,),
            party_moves=((33, 0, 0, 0),),
        )

    rig = EvolutionTestRig(
        reader=reader,
        collection=collection,
        slot=0,
        target_dex=JOLTEON_DEX,
        target_internal=JOLTEON_INTERNAL,
        stone_id=THUNDER_STONE,
        custom_close_menus_fn=corrupted_close,
    )
    rig.install(monkeypatch)

    request = RedPartyItemEvolutionRequest(
        rom=TEST_ROM,
        party_slot=0,
        source_national=EEVEE_DEX,
        target_national=JOLTEON_DEX,
        item_id=THUNDER_STONE,
    )
    runner = RedPartyItemEvolutionExecutor(reader, emulator, policy, rig.observe)

    with pytest.raises(RedPartyItemEvolutionVerificationError, match="Party after evolution"):
        runner.execute(actions, request)


def test_verification_rejects_wrong_stone_delta_or_lost_unrelated_item(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    executor = MockChapterExecutor()
    actions = CountingExecutor(executor)
    reader = MockReader(
        make_raw_state(
            party=(EEVEE_INTERNAL,),
            bag=((THUNDER_STONE, 2), (POTION, 5)),
        )
    )
    emulator = MockEmulator()
    policy, collection = make_policy_and_collection((EEVEE_DEX,), [(EEVEE_DEX, 25)])

    # 2 Thunder Stones were in bag, but both disappeared (delta = 2 instead of 1)
    def broken_bag_evolution() -> None:
        reader.raw = replace(
            reader.raw,
            party_species_ids=(JOLTEON_INTERNAL,),
            bag_items=((POTION, 5),),  # count became 0 instead of 1
        )

    rig = EvolutionTestRig(
        reader=reader,
        collection=collection,
        custom_evolution_fn=broken_bag_evolution,
    )
    rig.install(monkeypatch)

    request = RedPartyItemEvolutionRequest(
        rom=TEST_ROM,
        party_slot=0,
        source_national=EEVEE_DEX,
        target_national=JOLTEON_DEX,
        item_id=THUNDER_STONE,
    )
    runner = RedPartyItemEvolutionExecutor(
        reader, emulator, policy, lambda: collection, max_evolution_confirmation_pulses=2
    )

    with pytest.raises(RedPartyItemEvolutionTimeoutError):
        runner.execute(actions, request)


def test_verification_rejects_failed_registration_policy_verification(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    executor = MockChapterExecutor()
    actions = CountingExecutor(executor)
    reader = MockReader(make_raw_state(party=(EEVEE_INTERNAL,), bag=((THUNDER_STONE, 1),)))
    emulator = MockEmulator()
    policy, collection_before = make_policy_and_collection((EEVEE_DEX,), [(EEVEE_DEX, 25)])

    rig = EvolutionTestRig(
        reader=reader,
        collection=collection_before,
        slot=0,
        target_dex=JOLTEON_DEX,
        target_internal=JOLTEON_INTERNAL,
        stone_id=THUNDER_STONE,
    )
    rig.install(monkeypatch)

    # observe_collection returns unchanged collection_before (target specimen was NOT added)
    request = RedPartyItemEvolutionRequest(
        rom=TEST_ROM,
        party_slot=0,
        source_national=EEVEE_DEX,
        target_national=JOLTEON_DEX,
        item_id=THUNDER_STONE,
    )
    runner = RedPartyItemEvolutionExecutor(reader, emulator, policy, lambda: collection_before)

    with pytest.raises(
        RedPartyItemEvolutionVerificationError,
        match="Registration policy failed to verify evolution",
    ):
        runner.execute(actions, request)


def test_none_policy_or_observer_bypass_forbidden() -> None:
    reader = MockReader(make_raw_state())
    emulator = MockEmulator()
    policy, collection = make_policy_and_collection((EEVEE_DEX,), [(EEVEE_DEX, 25)])

    with pytest.raises(
        RedPartyItemEvolutionValidationError,
        match="RedRegistrationPolicy is required and cannot be None",
    ):
        RedPartyItemEvolutionExecutor(
            reader=reader,
            emulator=emulator,
            policy=None,  # type: ignore[arg-type]
            observe_collection=lambda: collection,
        )

    with pytest.raises(
        RedPartyItemEvolutionValidationError,
        match="observe_collection callback is required and cannot be None",
    ):
        RedPartyItemEvolutionExecutor(
            reader=reader,
            emulator=emulator,
            policy=policy,
            observe_collection=None,  # type: ignore[arg-type]
        )


def test_preconfirmation_rejects_party_species_change(monkeypatch: pytest.MonkeyPatch) -> None:
    executor = MockChapterExecutor()
    actions = CountingExecutor(executor)
    reader = MockReader(
        make_raw_state(
            party=(GROWLITHE_INTERNAL, EEVEE_INTERNAL),
            bag=((THUNDER_STONE, 1),),
        )
    )
    emulator = MockEmulator()
    policy, collection = make_policy_and_collection(
        (GROWLITHE_DEX, EEVEE_DEX),
        [(GROWLITHE_DEX, 20), (EEVEE_DEX, 25)],
    )

    monkeypatch.setattr(
        "pokemon_red_completion.red_party_item_evolution._open_bag", lambda a, e, t: None
    )
    monkeypatch.setattr(
        "pokemon_red_completion.red_party_item_evolution._select_bag_item",
        lambda a, e, i, t: None,
    )

    def mutating_select_cursor(acts: CountingExecutor, emu: Any, target: int, tim: Any) -> None:
        reader.cursor_state = replace(reader.cursor_state, selected_visible_index=target)
        # Precursor unexpectedly mutated before final confirmation
        reader.raw = replace(
            reader.raw,
            party_species_ids=(GROWLITHE_INTERNAL, GROWLITHE_INTERNAL),
        )

    monkeypatch.setattr(
        "pokemon_red_completion.red_party_item_evolution._select_cursor",
        mutating_select_cursor,
    )

    request = RedPartyItemEvolutionRequest(
        rom=TEST_ROM,
        party_slot=1,
        source_national=EEVEE_DEX,
        target_national=JOLTEON_DEX,
        item_id=THUNDER_STONE,
    )

    runner = RedPartyItemEvolutionExecutor(reader, emulator, policy, lambda: collection)
    with pytest.raises(
        RedPartyItemEvolutionExecutionError,
        match="Selected party slot 1 changed from",
    ):
        runner.execute(actions, request)


def test_preconfirmation_rejects_party_levels_or_moves_change(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    executor = MockChapterExecutor()
    actions = CountingExecutor(executor)
    reader = MockReader(
        make_raw_state(
            party=(EEVEE_INTERNAL,),
            bag=((THUNDER_STONE, 1),),
            party_levels=(25,),
            party_moves=((33, 0, 0, 0),),
        )
    )
    emulator = MockEmulator()
    policy, collection = make_policy_and_collection((EEVEE_DEX,), [(EEVEE_DEX, 25)])

    monkeypatch.setattr(
        "pokemon_red_completion.red_party_item_evolution._open_bag", lambda a, e, t: None
    )
    monkeypatch.setattr(
        "pokemon_red_completion.red_party_item_evolution._select_bag_item",
        lambda a, e, i, t: None,
    )

    def mutating_select_cursor(acts: CountingExecutor, emu: Any, target: int, tim: Any) -> None:
        reader.cursor_state = replace(reader.cursor_state, selected_visible_index=target)
        reader.raw = replace(reader.raw, party_levels=(99,))

    monkeypatch.setattr(
        "pokemon_red_completion.red_party_item_evolution._select_cursor",
        mutating_select_cursor,
    )

    request = RedPartyItemEvolutionRequest(
        rom=TEST_ROM,
        party_slot=0,
        source_national=EEVEE_DEX,
        target_national=JOLTEON_DEX,
        item_id=THUNDER_STONE,
    )

    runner = RedPartyItemEvolutionExecutor(reader, emulator, policy, lambda: collection)
    with pytest.raises(
        RedPartyItemEvolutionExecutionError,
        match="Party levels changed before irreversible confirmation",
    ):
        runner.execute(actions, request)


def test_preconfirmation_rejects_stone_count_change(monkeypatch: pytest.MonkeyPatch) -> None:
    executor = MockChapterExecutor()
    actions = CountingExecutor(executor)
    reader = MockReader(make_raw_state(party=(EEVEE_INTERNAL,), bag=((THUNDER_STONE, 1),)))
    emulator = MockEmulator()
    policy, collection = make_policy_and_collection((EEVEE_DEX,), [(EEVEE_DEX, 25)])

    monkeypatch.setattr(
        "pokemon_red_completion.red_party_item_evolution._open_bag", lambda a, e, t: None
    )
    monkeypatch.setattr(
        "pokemon_red_completion.red_party_item_evolution._select_bag_item",
        lambda a, e, i, t: None,
    )

    def mutating_select_cursor(acts: CountingExecutor, emu: Any, target: int, tim: Any) -> None:
        reader.cursor_state = replace(reader.cursor_state, selected_visible_index=target)
        reader.raw = replace(reader.raw, bag_items=())

    monkeypatch.setattr(
        "pokemon_red_completion.red_party_item_evolution._select_cursor",
        mutating_select_cursor,
    )

    request = RedPartyItemEvolutionRequest(
        rom=TEST_ROM,
        party_slot=0,
        source_national=EEVEE_DEX,
        target_national=JOLTEON_DEX,
        item_id=THUNDER_STONE,
    )

    runner = RedPartyItemEvolutionExecutor(reader, emulator, policy, lambda: collection)
    with pytest.raises(
        RedPartyItemEvolutionExecutionError,
        match="Stone inventory count changed from 1 to 0",
    ):
        runner.execute(actions, request)


def test_preconfirmation_rejects_battle_state(monkeypatch: pytest.MonkeyPatch) -> None:
    executor = MockChapterExecutor()
    actions = CountingExecutor(executor)
    reader = MockReader(make_raw_state(party=(EEVEE_INTERNAL,), bag=((THUNDER_STONE, 1),)))
    emulator = MockEmulator()
    policy, collection = make_policy_and_collection((EEVEE_DEX,), [(EEVEE_DEX, 25)])

    monkeypatch.setattr(
        "pokemon_red_completion.red_party_item_evolution._open_bag", lambda a, e, t: None
    )
    monkeypatch.setattr(
        "pokemon_red_completion.red_party_item_evolution._select_bag_item",
        lambda a, e, i, t: None,
    )

    def mutating_select_cursor(acts: CountingExecutor, emu: Any, target: int, tim: Any) -> None:
        reader.cursor_state = replace(reader.cursor_state, selected_visible_index=target)
        reader.raw = replace(reader.raw, battle_state=1)

    monkeypatch.setattr(
        "pokemon_red_completion.red_party_item_evolution._select_cursor",
        mutating_select_cursor,
    )

    request = RedPartyItemEvolutionRequest(
        rom=TEST_ROM,
        party_slot=0,
        source_national=EEVEE_DEX,
        target_national=JOLTEON_DEX,
        item_id=THUNDER_STONE,
    )

    runner = RedPartyItemEvolutionExecutor(reader, emulator, policy, lambda: collection)
    with pytest.raises(
        RedPartyItemEvolutionExecutionError,
        match="Unexpected battle state 1 before irreversible confirmation",
    ):
        runner.execute(actions, request)


def test_preconfirmation_rejects_map_or_position_change(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    executor = MockChapterExecutor()
    actions = CountingExecutor(executor)
    reader = MockReader(make_raw_state(party=(EEVEE_INTERNAL,), bag=((THUNDER_STONE, 1),)))
    emulator = MockEmulator()
    policy, collection = make_policy_and_collection((EEVEE_DEX,), [(EEVEE_DEX, 25)])

    monkeypatch.setattr(
        "pokemon_red_completion.red_party_item_evolution._open_bag", lambda a, e, t: None
    )
    monkeypatch.setattr(
        "pokemon_red_completion.red_party_item_evolution._select_bag_item",
        lambda a, e, i, t: None,
    )

    def mutating_select_cursor(acts: CountingExecutor, emu: Any, target: int, tim: Any) -> None:
        reader.cursor_state = replace(reader.cursor_state, selected_visible_index=target)
        reader.raw = replace(reader.raw, player_x=99)

    monkeypatch.setattr(
        "pokemon_red_completion.red_party_item_evolution._select_cursor",
        mutating_select_cursor,
    )

    request = RedPartyItemEvolutionRequest(
        rom=TEST_ROM,
        party_slot=0,
        source_national=EEVEE_DEX,
        target_national=JOLTEON_DEX,
        item_id=THUNDER_STONE,
    )

    runner = RedPartyItemEvolutionExecutor(reader, emulator, policy, lambda: collection)
    with pytest.raises(
        RedPartyItemEvolutionExecutionError,
        match="Map or position changed before irreversible confirmation",
    ):
        runner.execute(actions, request)


def test_preconfirmation_rejects_money_or_badges_change(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    executor = MockChapterExecutor()
    actions = CountingExecutor(executor)
    reader = MockReader(
        make_raw_state(
            party=(EEVEE_INTERNAL,),
            bag=((THUNDER_STONE, 1),),
            player_money=3000,
        )
    )
    emulator = MockEmulator()
    policy, collection = make_policy_and_collection((EEVEE_DEX,), [(EEVEE_DEX, 25)])

    monkeypatch.setattr(
        "pokemon_red_completion.red_party_item_evolution._open_bag", lambda a, e, t: None
    )
    monkeypatch.setattr(
        "pokemon_red_completion.red_party_item_evolution._select_bag_item",
        lambda a, e, i, t: None,
    )

    def mutating_select_cursor(acts: CountingExecutor, emu: Any, target: int, tim: Any) -> None:
        reader.cursor_state = replace(reader.cursor_state, selected_visible_index=target)
        reader.raw = replace(reader.raw, player_money=100)

    monkeypatch.setattr(
        "pokemon_red_completion.red_party_item_evolution._select_cursor",
        mutating_select_cursor,
    )

    request = RedPartyItemEvolutionRequest(
        rom=TEST_ROM,
        party_slot=0,
        source_national=EEVEE_DEX,
        target_national=JOLTEON_DEX,
        item_id=THUNDER_STONE,
    )

    runner = RedPartyItemEvolutionExecutor(reader, emulator, policy, lambda: collection)
    with pytest.raises(
        RedPartyItemEvolutionExecutionError,
        match="Player money changed before irreversible confirmation",
    ):
        runner.execute(actions, request)


def test_preconfirmation_rejects_story_event_flags_change(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    executor = MockChapterExecutor()
    actions = CountingExecutor(executor)
    reader = MockReader(
        make_raw_state(
            party=(EEVEE_INTERNAL,),
            bag=((THUNDER_STONE, 1),),
            event_flags=b"\x00" * 320,
        )
    )
    emulator = MockEmulator()
    policy, collection = make_policy_and_collection((EEVEE_DEX,), [(EEVEE_DEX, 25)])

    monkeypatch.setattr(
        "pokemon_red_completion.red_party_item_evolution._open_bag", lambda a, e, t: None
    )
    monkeypatch.setattr(
        "pokemon_red_completion.red_party_item_evolution._select_bag_item",
        lambda a, e, i, t: None,
    )

    def mutating_select_cursor(acts: CountingExecutor, emu: Any, target: int, tim: Any) -> None:
        reader.cursor_state = replace(reader.cursor_state, selected_visible_index=target)
        reader.raw = replace(reader.raw, event_flags=b"\xff" * 320)

    monkeypatch.setattr(
        "pokemon_red_completion.red_party_item_evolution._select_cursor",
        mutating_select_cursor,
    )

    request = RedPartyItemEvolutionRequest(
        rom=TEST_ROM,
        party_slot=0,
        source_national=EEVEE_DEX,
        target_national=JOLTEON_DEX,
        item_id=THUNDER_STONE,
    )

    runner = RedPartyItemEvolutionExecutor(reader, emulator, policy, lambda: collection)
    with pytest.raises(
        RedPartyItemEvolutionExecutionError,
        match="Story event flags changed before irreversible confirmation",
    ):
        runner.execute(actions, request)


def test_post_verification_rejects_unready_input(monkeypatch: pytest.MonkeyPatch) -> None:
    executor = MockChapterExecutor()
    actions = CountingExecutor(executor)
    reader = MockReader(make_raw_state(party=(EEVEE_INTERNAL,), bag=((THUNDER_STONE, 1),)))
    emulator = MockEmulator()
    policy, collection_before = make_policy_and_collection((EEVEE_DEX,), [(EEVEE_DEX, 25)])

    def unready_close(acts: CountingExecutor, rdr: Any, tim: Any) -> None:
        acts.execute(MacroAction(MacroActionKind.CANCEL))
        reader.readiness = InputReadiness(
            joy_ignore=0xFF,
            simulated_joypad_index=0,
            npc_movement_script_table=0,
            player_moving_direction=0,
            status_flags_5=0,
            movement_flags=0,
            walk_counter=0,
        )

    rig = EvolutionTestRig(
        reader=reader,
        collection=collection_before,
        custom_close_menus_fn=unready_close,
    )
    rig.install(monkeypatch)

    request = RedPartyItemEvolutionRequest(
        rom=TEST_ROM,
        party_slot=0,
        source_national=EEVEE_DEX,
        target_national=JOLTEON_DEX,
        item_id=THUNDER_STONE,
    )
    runner = RedPartyItemEvolutionExecutor(reader, emulator, policy, rig.observe)

    with pytest.raises(
        RedPartyItemEvolutionVerificationError,
        match="Input readiness is not ready after evolution menu closure",
    ):
        runner.execute(actions, request)


def test_post_verification_rejects_post_battle_state(monkeypatch: pytest.MonkeyPatch) -> None:
    executor = MockChapterExecutor()
    actions = CountingExecutor(executor)
    reader = MockReader(make_raw_state(party=(EEVEE_INTERNAL,), bag=((THUNDER_STONE, 1),)))
    emulator = MockEmulator()
    policy, collection_before = make_policy_and_collection((EEVEE_DEX,), [(EEVEE_DEX, 25)])

    def battle_close(acts: CountingExecutor, rdr: Any, tim: Any) -> None:
        acts.execute(MacroAction(MacroActionKind.CANCEL))
        reader.raw = replace(reader.raw, battle_state=1)

    rig = EvolutionTestRig(
        reader=reader,
        collection=collection_before,
        custom_close_menus_fn=battle_close,
    )
    rig.install(monkeypatch)

    request = RedPartyItemEvolutionRequest(
        rom=TEST_ROM,
        party_slot=0,
        source_national=EEVEE_DEX,
        target_national=JOLTEON_DEX,
        item_id=THUNDER_STONE,
    )
    runner = RedPartyItemEvolutionExecutor(reader, emulator, policy, rig.observe)

    with pytest.raises(
        RedPartyItemEvolutionVerificationError,
        match="Unexpected battle state 1 after evolution",
    ):
        runner.execute(actions, request)


def test_post_verification_rejects_position_or_map_drift(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    executor = MockChapterExecutor()
    actions = CountingExecutor(executor)
    reader = MockReader(
        make_raw_state(
            party=(EEVEE_INTERNAL,),
            bag=((THUNDER_STONE, 1),),
            map_id=1,
            player_x=5,
            player_y=5,
        )
    )
    emulator = MockEmulator()
    policy, collection_before = make_policy_and_collection((EEVEE_DEX,), [(EEVEE_DEX, 25)])

    def map_drift_close(acts: CountingExecutor, rdr: Any, tim: Any) -> None:
        acts.execute(MacroAction(MacroActionKind.CANCEL))
        reader.raw = replace(reader.raw, map_id=40)

    rig = EvolutionTestRig(
        reader=reader,
        collection=collection_before,
        custom_close_menus_fn=map_drift_close,
    )
    rig.install(monkeypatch)

    request = RedPartyItemEvolutionRequest(
        rom=TEST_ROM,
        party_slot=0,
        source_national=EEVEE_DEX,
        target_national=JOLTEON_DEX,
        item_id=THUNDER_STONE,
    )
    runner = RedPartyItemEvolutionExecutor(reader, emulator, policy, rig.observe)

    with pytest.raises(
        RedPartyItemEvolutionVerificationError,
        match="Map or player position changed after evolution",
    ):
        runner.execute(actions, request)


def test_post_verification_rejects_money_or_badge_drift(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    executor = MockChapterExecutor()
    actions = CountingExecutor(executor)
    reader = MockReader(
        make_raw_state(
            party=(EEVEE_INTERNAL,),
            bag=((THUNDER_STONE, 1),),
            player_money=3000,
        )
    )
    emulator = MockEmulator()
    policy, collection_before = make_policy_and_collection((EEVEE_DEX,), [(EEVEE_DEX, 25)])

    def money_drift_close(acts: CountingExecutor, rdr: Any, tim: Any) -> None:
        acts.execute(MacroAction(MacroActionKind.CANCEL))
        reader.raw = replace(reader.raw, player_money=2500)

    rig = EvolutionTestRig(
        reader=reader,
        collection=collection_before,
        custom_close_menus_fn=money_drift_close,
    )
    rig.install(monkeypatch)

    request = RedPartyItemEvolutionRequest(
        rom=TEST_ROM,
        party_slot=0,
        source_national=EEVEE_DEX,
        target_national=JOLTEON_DEX,
        item_id=THUNDER_STONE,
    )
    runner = RedPartyItemEvolutionExecutor(reader, emulator, policy, rig.observe)

    with pytest.raises(
        RedPartyItemEvolutionVerificationError,
        match="Player money changed after evolution",
    ):
        runner.execute(actions, request)


def test_post_verification_rejects_unrelated_party_level_or_moves_drift(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    executor = MockChapterExecutor()
    actions = CountingExecutor(executor)
    reader = MockReader(
        make_raw_state(
            party=(EEVEE_INTERNAL, GROWLITHE_INTERNAL),
            bag=((THUNDER_STONE, 1),),
            party_levels=(25, 20),
            party_moves=((33, 0, 0, 0), (52, 0, 0, 0)),
        )
    )
    emulator = MockEmulator()
    policy, collection_before = make_policy_and_collection(
        (EEVEE_DEX, GROWLITHE_DEX),
        [(EEVEE_DEX, 25), (GROWLITHE_DEX, 20)],
    )

    def evolve_with_nontarget_drift() -> None:
        reader.raw = replace(
            reader.raw,
            party_species_ids=(JOLTEON_INTERNAL, GROWLITHE_INTERNAL),
            party_levels=(25, 21),  # Nontarget Growlithe level changed from 20 to 21
            bag_items=(),
        )
        reader.pokedex_state = replace(
            reader.pokedex_state,
            owned_species=reader.pokedex_state.owned_species | frozenset([JOLTEON_DEX]),
            seen_species=reader.pokedex_state.seen_species | frozenset([JOLTEON_DEX]),
        )

    rig = EvolutionTestRig(
        reader=reader,
        collection=collection_before,
        custom_evolution_fn=evolve_with_nontarget_drift,
    )
    rig.install(monkeypatch)

    target_obs = replace(
        collection_before,
        owned_species=collection_before.owned_species | frozenset([red_species_ref(JOLTEON_DEX)]),
        specimens=(
            replace(collection_before.specimens[0], species_ref=red_species_ref(JOLTEON_DEX)),
            collection_before.specimens[1],
        ),
    )

    request = RedPartyItemEvolutionRequest(
        rom=TEST_ROM,
        party_slot=0,
        source_national=EEVEE_DEX,
        target_national=JOLTEON_DEX,
        item_id=THUNDER_STONE,
    )
    runner = RedPartyItemEvolutionExecutor(
        reader,
        emulator,
        policy,
        lambda: target_obs if rig.has_evolved else collection_before,
    )

    with pytest.raises(
        RedPartyItemEvolutionVerificationError,
        match="Nontarget party slot 1 level changed from 20 to 21",
    ):
        runner.execute(actions, request)


def test_post_verification_rejects_target_level_or_moves_drift(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    executor = MockChapterExecutor()
    actions = CountingExecutor(executor)
    reader = MockReader(
        make_raw_state(
            party=(EEVEE_INTERNAL,),
            bag=((THUNDER_STONE, 1),),
            party_levels=(25,),
            party_moves=((33, 0, 0, 0),),
        )
    )
    emulator = MockEmulator()
    policy, collection_before = make_policy_and_collection((EEVEE_DEX,), [(EEVEE_DEX, 25)])

    def evolve_with_target_level_drift() -> None:
        reader.raw = replace(
            reader.raw,
            party_species_ids=(JOLTEON_INTERNAL,),
            party_levels=(50,),  # Evolved Pokémon level changed from 25 to 50
            bag_items=(),
        )
        reader.pokedex_state = replace(
            reader.pokedex_state,
            owned_species=reader.pokedex_state.owned_species | frozenset([JOLTEON_DEX]),
            seen_species=reader.pokedex_state.seen_species | frozenset([JOLTEON_DEX]),
        )

    rig = EvolutionTestRig(
        reader=reader,
        collection=collection_before,
        custom_evolution_fn=evolve_with_target_level_drift,
    )
    rig.install(monkeypatch)

    target_obs = replace(
        collection_before,
        owned_species=collection_before.owned_species | frozenset([red_species_ref(JOLTEON_DEX)]),
        specimens=(
            replace(collection_before.specimens[0], species_ref=red_species_ref(JOLTEON_DEX)),
        ),
    )

    request = RedPartyItemEvolutionRequest(
        rom=TEST_ROM,
        party_slot=0,
        source_national=EEVEE_DEX,
        target_national=JOLTEON_DEX,
        item_id=THUNDER_STONE,
    )
    runner = RedPartyItemEvolutionExecutor(
        reader,
        emulator,
        policy,
        lambda: target_obs if rig.has_evolved else collection_before,
    )

    with pytest.raises(
        RedPartyItemEvolutionVerificationError,
        match="Evolved Pokémon in slot 0 changed level from 25 to 50",
    ):
        runner.execute(actions, request)


def test_post_verification_rejects_lost_pokedex_owned_flag(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    executor = MockChapterExecutor()
    actions = CountingExecutor(executor)
    reader = MockReader(
        make_raw_state(
            party=(EEVEE_INTERNAL,),
            bag=((THUNDER_STONE, 1),),
        ),
        pokedex_state=RedPokedexState(
            owned_species=frozenset([EEVEE_DEX]),
            seen_species=frozenset([EEVEE_DEX]),
        ),
    )
    emulator = MockEmulator()
    policy, collection_before = make_policy_and_collection((EEVEE_DEX,), [(EEVEE_DEX, 25)])

    def evolve_with_lost_pokedex_flag() -> None:
        reader.raw = replace(
            reader.raw,
            party_species_ids=(JOLTEON_INTERNAL,),
            bag_items=(),
        )
        reader.pokedex_state = RedPokedexState(
            owned_species=frozenset([JOLTEON_DEX]),
            seen_species=frozenset([EEVEE_DEX, JOLTEON_DEX]),
        )

    rig = EvolutionTestRig(
        reader=reader,
        collection=collection_before,
        custom_evolution_fn=evolve_with_lost_pokedex_flag,
    )
    rig.install(monkeypatch)

    target_obs = replace(
        collection_before,
        owned_species=collection_before.owned_species | frozenset([red_species_ref(JOLTEON_DEX)]),
        specimens=(
            replace(collection_before.specimens[0], species_ref=red_species_ref(JOLTEON_DEX)),
        ),
    )

    request = RedPartyItemEvolutionRequest(
        rom=TEST_ROM,
        party_slot=0,
        source_national=EEVEE_DEX,
        target_national=JOLTEON_DEX,
        item_id=THUNDER_STONE,
    )
    runner = RedPartyItemEvolutionExecutor(
        reader,
        emulator,
        policy,
        lambda: target_obs if rig.has_evolved else collection_before,
    )

    with pytest.raises(
        RedPartyItemEvolutionVerificationError,
        match="Pokedex lost previously owned species flags after evolution",
    ):
        runner.execute(actions, request)


def test_loop_defect_evolution_on_final_allowed_pulse_succeeds(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Evolution completes on the final allowed loop confirmation pulse.
    Without the final observation before timeout, this would fail with timeout.
    With the repair, it succeeds."""
    executor = MockChapterExecutor()
    actions = CountingExecutor(executor)
    reader = MockReader(make_raw_state(party=(EEVEE_INTERNAL,), bag=((THUNDER_STONE, 1),)))
    emulator = MockEmulator()
    policy, collection_before = make_policy_and_collection((EEVEE_DEX,), [(EEVEE_DEX, 25)])

    # max pulses = 3:
    # Confirmation 1: party slot confirmation (line 425)
    # Confirmation 2: loop pulse 1
    # Confirmation 3: loop pulse 2
    # Confirmation 4: loop pulse 3 (final allowed confirmation pulse) -> evolve!
    rig = EvolutionTestRig(
        reader=reader,
        collection=collection_before,
        slot=0,
        target_dex=JOLTEON_DEX,
        target_internal=JOLTEON_INTERNAL,
        stone_id=THUNDER_STONE,
        evolve_on_confirmation=4,
    )
    rig.install(monkeypatch)

    request = RedPartyItemEvolutionRequest(
        rom=TEST_ROM,
        party_slot=0,
        source_national=EEVEE_DEX,
        target_national=JOLTEON_DEX,
        item_id=THUNDER_STONE,
    )
    result = execute_party_item_evolution(
        actions,
        reader,
        emulator,
        policy,
        rig.observe,
        request,
        max_evolution_confirmation_pulses=3,
    )

    assert result.success is True
    assert result.after_party_species == (JOLTEON_INTERNAL,)
    # Exactly 4 confirmation pulses occurred after menu preparation (1 on party slot + 3 in loop)
    confirm_actions = [a for a in executor.actions if a.kind is MacroActionKind.CONFIRM]
    # Menu prep has 2 confirms (select item, select USE); evolution has 4 confirms
    assert len(confirm_actions) == 6
    assert rig.evolution_confirmations == 4


def test_timeout_counts_exact_allowed_confirmations_excluding_menu_prep(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Timeout test verifying exactly allowed confirmations (excluding menu prep) are issued."""
    executor = MockChapterExecutor()
    actions = CountingExecutor(executor)
    reader = MockReader(make_raw_state(party=(EEVEE_INTERNAL,), bag=((THUNDER_STONE, 1),)))
    emulator = MockEmulator()
    policy, collection = make_policy_and_collection((EEVEE_DEX,), [(EEVEE_DEX, 25)])

    # Evolution never triggers (evolve_on_confirmation=999)
    rig = EvolutionTestRig(
        reader=reader,
        collection=collection,
        evolve_on_confirmation=999,
    )
    rig.install(monkeypatch)

    request = RedPartyItemEvolutionRequest(
        rom=TEST_ROM,
        party_slot=0,
        source_national=EEVEE_DEX,
        target_national=JOLTEON_DEX,
        item_id=THUNDER_STONE,
    )
    runner = RedPartyItemEvolutionExecutor(
        reader, emulator, policy, lambda: collection, max_evolution_confirmation_pulses=3
    )

    with pytest.raises(
        RedPartyItemEvolutionTimeoutError, match="Evolution did not complete within 3 pulses"
    ):
        runner.execute(actions, request)

    # Exactly 4 confirmation pulses after menu preparation: 1 on party member + 3 in loop
    assert rig.evolution_confirmations == 4
    confirm_actions = [a for a in executor.actions if a.kind is MacroActionKind.CONFIRM]
    assert len(confirm_actions) == 6  # 2 menu prep + 4 evolution confirmations


def test_max_evolution_confirmation_pulses_finite_upper_cap_validation() -> None:
    reader = MockReader(make_raw_state())
    emulator = MockEmulator()
    policy, collection = make_policy_and_collection((EEVEE_DEX,), [(EEVEE_DEX, 25)])

    # Out of 1..64 bounds
    for invalid_cap in (0, -1, 65, 100, True, "64"):
        with pytest.raises(
            RedPartyItemEvolutionValidationError,
            match="max_evolution_confirmation_pulses must be an integer between 1 and 64",
        ):
            RedPartyItemEvolutionExecutor(
                reader=reader,
                emulator=emulator,
                policy=policy,
                observe_collection=lambda: collection,
                max_evolution_confirmation_pulses=invalid_cap,  # type: ignore[arg-type]
            )

    # Boundary values 1 and 64 are valid
    e1 = RedPartyItemEvolutionExecutor(
        reader=reader,
        emulator=emulator,
        policy=policy,
        observe_collection=lambda: collection,
        max_evolution_confirmation_pulses=1,
    )
    assert e1.max_evolution_confirmation_pulses == 1

    e64 = RedPartyItemEvolutionExecutor(
        reader=reader,
        emulator=emulator,
        policy=policy,
        observe_collection=lambda: collection,
        max_evolution_confirmation_pulses=64,
    )
    assert e64.max_evolution_confirmation_pulses == 64


def test_rejects_unavailable_and_duplicate_bag_items_before_input() -> None:
    executor = MockChapterExecutor()
    actions = CountingExecutor(executor)
    emulator = MockEmulator()
    policy, collection = make_policy_and_collection((EEVEE_DEX,), [(EEVEE_DEX, 25)])
    request = RedPartyItemEvolutionRequest(
        rom=TEST_ROM,
        party_slot=0,
        source_national=EEVEE_DEX,
        target_national=JOLTEON_DEX,
        item_id=THUNDER_STONE,
    )

    # Unavailable bag items
    unavail_raw = replace(make_raw_state(), bag_items=None)
    runner1 = RedPartyItemEvolutionExecutor(
        MockReader(unavail_raw), emulator, policy, lambda: collection
    )
    with pytest.raises(
        RedPartyItemEvolutionValidationError, match="Bag items observation is unavailable"
    ):
        runner1.execute(actions, request)
    assert actions.actions_executed == 0

    # Duplicate bag item rows
    dup_raw = replace(make_raw_state(), bag_items=((THUNDER_STONE, 1), (THUNDER_STONE, 1)))
    runner2 = RedPartyItemEvolutionExecutor(
        MockReader(dup_raw), emulator, policy, lambda: collection
    )
    with pytest.raises(
        RedPartyItemEvolutionValidationError, match="Duplicate bag item row detected"
    ):
        runner2.execute(actions, request)
    assert actions.actions_executed == 0


def test_rejects_unavailable_and_truncated_party_levels_before_input() -> None:
    executor = MockChapterExecutor()
    actions = CountingExecutor(executor)
    emulator = MockEmulator()
    policy, collection = make_policy_and_collection(
        (EEVEE_DEX, GROWLITHE_DEX), [(EEVEE_DEX, 25), (GROWLITHE_DEX, 20)]
    )
    request = RedPartyItemEvolutionRequest(
        rom=TEST_ROM,
        party_slot=0,
        source_national=EEVEE_DEX,
        target_national=JOLTEON_DEX,
        item_id=THUNDER_STONE,
    )

    # Unavailable party levels
    unavail_raw = replace(
        make_raw_state(party=(EEVEE_INTERNAL, GROWLITHE_INTERNAL)), party_levels=None
    )
    runner1 = RedPartyItemEvolutionExecutor(
        MockReader(unavail_raw), emulator, policy, lambda: collection
    )
    with pytest.raises(
        RedPartyItemEvolutionValidationError, match="Party levels observation is unavailable"
    ):
        runner1.execute(actions, request)
    assert actions.actions_executed == 0

    # Truncated party levels (party size 2, levels length 1)
    trunc_raw = replace(
        make_raw_state(party=(EEVEE_INTERNAL, GROWLITHE_INTERNAL)),
        party_levels=(25,),
    )
    runner2 = RedPartyItemEvolutionExecutor(
        MockReader(trunc_raw), emulator, policy, lambda: collection
    )
    with pytest.raises(
        RedPartyItemEvolutionValidationError,
        match="Party levels count 1 does not match party size 2",
    ):
        runner2.execute(actions, request)
    assert actions.actions_executed == 0


def test_rejects_unavailable_and_truncated_party_moves_before_input() -> None:
    executor = MockChapterExecutor()
    actions = CountingExecutor(executor)
    emulator = MockEmulator()
    policy, collection = make_policy_and_collection(
        (EEVEE_DEX, GROWLITHE_DEX), [(EEVEE_DEX, 25), (GROWLITHE_DEX, 20)]
    )
    request = RedPartyItemEvolutionRequest(
        rom=TEST_ROM,
        party_slot=0,
        source_national=EEVEE_DEX,
        target_national=JOLTEON_DEX,
        item_id=THUNDER_STONE,
    )

    # Unavailable party moves
    unavail_raw = replace(
        make_raw_state(party=(EEVEE_INTERNAL, GROWLITHE_INTERNAL)), party_moves=None
    )
    runner1 = RedPartyItemEvolutionExecutor(
        MockReader(unavail_raw), emulator, policy, lambda: collection
    )
    with pytest.raises(
        RedPartyItemEvolutionValidationError, match="Party moves observation is unavailable"
    ):
        runner1.execute(actions, request)
    assert actions.actions_executed == 0

    # Truncated party moves count
    trunc_raw = replace(
        make_raw_state(party=(EEVEE_INTERNAL, GROWLITHE_INTERNAL)),
        party_moves=((33, 0, 0, 0),),
    )
    runner2 = RedPartyItemEvolutionExecutor(
        MockReader(trunc_raw), emulator, policy, lambda: collection
    )
    with pytest.raises(
        RedPartyItemEvolutionValidationError,
        match="Party moves count 1 does not match party size 2",
    ):
        runner2.execute(actions, request)
    assert actions.actions_executed == 0

    # Move slots within entry not 4
    bad_slot_moves = replace(
        make_raw_state(party=(EEVEE_INTERNAL,)),
        party_moves=((33, 0, 0),),
    )
    runner3 = RedPartyItemEvolutionExecutor(
        MockReader(bad_slot_moves), emulator, policy, lambda: collection
    )
    with pytest.raises(RedPartyItemEvolutionValidationError, match="must have exactly 4 moves"):
        runner3.execute(actions, request)
    assert actions.actions_executed == 0


def test_post_verification_rejects_truncated_shapes_strict(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Post-verification rejects truncated levels/moves using complete shapes."""
    executor = MockChapterExecutor()
    actions = CountingExecutor(executor)
    reader = MockReader(
        make_raw_state(
            party=(EEVEE_INTERNAL, GROWLITHE_INTERNAL),
            bag=((THUNDER_STONE, 1),),
            party_levels=(25, 20),
            party_moves=((33, 0, 0, 0), (52, 0, 0, 0)),
        )
    )
    emulator = MockEmulator()
    policy, collection = make_policy_and_collection(
        (EEVEE_DEX, GROWLITHE_DEX), [(EEVEE_DEX, 25), (GROWLITHE_DEX, 20)]
    )

    # Corrupt party_levels to be truncated after evolution
    def corrupt_levels_close(acts: CountingExecutor, rdr: Any, tim: Any) -> None:
        acts.execute(MacroAction(MacroActionKind.CANCEL))
        reader.raw = replace(
            reader.raw,
            party_levels=(25,),  # Truncated to 1 item
        )

    rig1 = EvolutionTestRig(
        reader=reader,
        collection=collection,
        custom_close_menus_fn=corrupt_levels_close,
    )
    rig1.install(monkeypatch)

    request = RedPartyItemEvolutionRequest(
        rom=TEST_ROM,
        party_slot=0,
        source_national=EEVEE_DEX,
        target_national=JOLTEON_DEX,
        item_id=THUNDER_STONE,
    )
    runner1 = RedPartyItemEvolutionExecutor(reader, emulator, policy, rig1.observe)
    with pytest.raises(RedPartyItemEvolutionVerificationError, match="Party levels shape changed"):
        runner1.execute(actions, request)

    # Corrupt party_moves to be truncated after evolution
    reader2 = MockReader(
        make_raw_state(
            party=(EEVEE_INTERNAL, GROWLITHE_INTERNAL),
            bag=((THUNDER_STONE, 1),),
            party_levels=(25, 20),
            party_moves=((33, 0, 0, 0), (52, 0, 0, 0)),
        )
    )
    policy2, collection2 = make_policy_and_collection(
        (EEVEE_DEX, GROWLITHE_DEX), [(EEVEE_DEX, 25), (GROWLITHE_DEX, 20)]
    )

    def corrupt_moves_close(acts: CountingExecutor, rdr: Any, tim: Any) -> None:
        acts.execute(MacroAction(MacroActionKind.CANCEL))
        reader2.raw = replace(
            reader2.raw,
            party_moves=((33, 0, 0, 0),),  # Truncated to 1 item
        )

    rig2 = EvolutionTestRig(
        reader=reader2,
        collection=collection2,
        custom_close_menus_fn=corrupt_moves_close,
    )
    rig2.install(monkeypatch)

    runner2 = RedPartyItemEvolutionExecutor(reader2, emulator, policy2, rig2.observe)
    with pytest.raises(RedPartyItemEvolutionVerificationError, match="Party moves shape changed"):
        runner2.execute(actions, request)


def test_real_item_ids_and_assertions() -> None:
    """Assert against real ItemId.THUNDER_STONE and literal values for stones."""
    assert MOON_STONE == 10
    assert FIRE_STONE == 32
    assert THUNDER_STONE == 33
    assert int(ItemId.THUNDER_STONE) == THUNDER_STONE
    assert WATER_STONE == 34
    assert LEAF_STONE == 47
    assert POTION == 20
    assert int(ItemId.POTION) == POTION
