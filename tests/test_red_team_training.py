"""Run the team-training loop without an emulator.

Sixteen defects were found in this module in a single session, and fourteen of
them were code that had simply never been executed: a dataclass field that does
not exist, a ``RamAddress`` symbol that is not a symbol, a Protocol method
nothing implements, ``None`` where a run state belonged, a call site supplying
seven of eighteen arguments.  Every one passed the unit suite, and every one
cost a twenty-five minute emulator run to find.

None of them needed PyBoy.  ``run_red_team_balancing`` is a state machine over
``reader.read()`` and party memory; give it scripted bytes and a menu that
answers back, and it executes for real.  These tests cannot prove the route is
correct — only the emulator does that — but they prove the code *runs*, which
is where nearly all the cost has been.
"""

from __future__ import annotations

import pytest

from pokemon_red_completion.actions import MacroAction, MacroActionKind
from pokemon_red_completion.battle_runtime import BattleIntent
from pokemon_red_completion.observation import (
    BattleMenuPhase,
    BattleMenuState,
    MapId,
    RamAddress,
    RawGameState,
)
from pokemon_red_completion.red_party import (
    BLASTOISE_SPECIES_ID,
    DUGTRIO_SPECIES_ID,
    DUX_SPECIES_ID,
    HITMONLEE_SPECIES_ID,
    HP_OFFSET,
    JOLTEON_SPECIES_ID,
    LEVEL_OFFSET,
    MAX_HP_OFFSET,
    MOVES_OFFSET,
    PARTY_STRUCT_STRIDE,
    PP_OFFSET,
    SNORLAX_SPECIES_ID,
    SPECIES_OFFSET,
    STRUCT_BASE,
    PokemonRedPartyReader,
)
from pokemon_red_completion.red_team_training import (
    ESCORT_LEVEL_CAP,
    VENUE_MISMATCH_FLEES,
    run_red_team_balancing,
)
from pokemon_red_completion.team_training import BalancedTeamPolicy

DIGLETT_SPECIES_ID = 0x3B
TACKLE_MOVE_ID = 0x21
TRAINING_MAP = int(MapId.POKEMON_MANSION_1F)
CENTER_MAP = int(MapId.CINNABAR_POKECENTER)

# The roster the Red adapter's own plan names, in the order it names it.
FINAL_FORM_ROSTER = (
    BLASTOISE_SPECIES_ID,
    DUGTRIO_SPECIES_ID,
    DUX_SPECIES_ID,
    JOLTEON_SPECIES_ID,
    SNORLAX_SPECIES_ID,
    HITMONLEE_SPECIES_ID,
)


class FakeMember:
    def __init__(self, species: int, level: int, hp: int, max_hp: int) -> None:
        self.species = species
        self.level = level
        self.hp = hp
        self.max_hp = max_hp


class FakeMemory:
    """Party memory plus the field menu the training code actually drives.

    A dictionary of canned bytes is not enough here.  ``swap_field_party_slots``
    moves a cursor and then *checks where it landed*; if the fake never moves,
    the code under test raises before reaching anything interesting.  So this
    models the cursor and performs the swap, which means the swap helper is
    genuinely exercised rather than merely called.
    """

    def __init__(self) -> None:
        self.party: list[FakeMember] = []
        self.cursor = 0
        self.stage = "field"
        self.pending_slot: int | None = None
        self.swaps: list[tuple[int, int]] = []

    def set_party(self, members: list[tuple[int, int]], *, hp: int = 80, max_hp: int = 80) -> None:
        """Install ``(species, level)`` pairs as a live party.

        Species are *internal indices*, not Pokedex ordinals — Blastoise is
        0x1C here and 9 in the dex.  Writing the ordinal produces a party of
        entirely different Pokemon that still reads as perfectly valid.
        """

        self.party = [FakeMember(s, level, hp, max_hp) for s, level in members]

    # -- memory ---------------------------------------------------------

    def read_u8(self, address: int) -> int:
        addr = int(address)
        if addr == int(RamAddress.PARTY_COUNT):
            return len(self.party)
        if addr == int(RamAddress.CURRENT_MENU_ITEM):
            return self.cursor
        species_base = int(RamAddress.PARTY_SPECIES)
        if species_base <= addr < species_base + 6:
            index = addr - species_base
            return self.party[index].species if index < len(self.party) else 0
        index, offset = divmod(addr - STRUCT_BASE, PARTY_STRUCT_STRIDE)
        if not 0 <= index < len(self.party):
            return 0
        return self._field(self.party[index], offset)

    def _field(self, member: FakeMember, offset: int) -> int:
        if offset == SPECIES_OFFSET:
            return member.species
        if offset == LEVEL_OFFSET:
            return member.level
        if offset == HP_OFFSET:
            return member.hp >> 8
        if offset == HP_OFFSET + 1:
            return member.hp & 0xFF
        if offset == MAX_HP_OFFSET:
            return member.max_hp >> 8
        if offset == MAX_HP_OFFSET + 1:
            return member.max_hp & 0xFF
        if offset == MOVES_OFFSET:
            return TACKLE_MOVE_ID  # one damaging move, in the first slot
        if offset == PP_OFFSET:
            return 20  # and plenty of power points for it
        return 0

    # -- field menu -----------------------------------------------------

    def apply(self, action: MacroAction) -> None:
        """Advance the menu the way the game would for this input."""

        kind = action.kind
        if kind is MacroActionKind.OPEN_MENU:
            self.stage, self.cursor = "root", 0
        elif kind is MacroActionKind.CANCEL:
            self.stage, self.cursor, self.pending_slot = "field", 0, None
        elif kind is MacroActionKind.MOVE:
            self._move(str(action.value))
        elif kind is MacroActionKind.CONFIRM:
            self._confirm()

    def _move(self, direction: str) -> None:
        if self.stage == "field":
            return
        limit = len(self.party) - 1 if self.stage.startswith("party") else 5
        if direction == "down":
            self.cursor = min(self.cursor + 1, limit)
        elif direction == "up":
            self.cursor = max(self.cursor - 1, 0)

    def _confirm(self) -> None:
        if self.stage == "root" and self.cursor == 1:  # the POKEMON entry
            self.stage, self.cursor = "party", 0
        elif self.stage == "party":
            self.pending_slot, self.stage, self.cursor = self.cursor, "member", 0
        elif self.stage == "member":
            self.stage, self.cursor = "party_target", 0
        elif self.stage == "party_target" and self.pending_slot is not None:
            first, second = self.pending_slot, self.cursor
            self.party[first], self.party[second] = self.party[second], self.party[first]
            self.swaps.append((first, second))
            self.stage, self.cursor, self.pending_slot = "field", 0, None


class FakeReader:
    """Replays scripted states, repeating the last once the script runs out."""

    def __init__(self, states: list[RawGameState]) -> None:
        self.states = states
        self.reads = 0

    def read(self) -> RawGameState:
        state = self.states[min(self.reads, len(self.states) - 1)]
        self.reads += 1
        return state

    def read_battle_menu_state(self, raw: RawGameState) -> BattleMenuState:
        if raw.battle_state == 1:
            return BattleMenuState(BattleMenuPhase.MAIN, selected_main_command=0)
        return BattleMenuState(BattleMenuPhase.UNKNOWN)

    def read_input_readiness(self) -> object:
        return type("Readiness", (), {"ready": True})()


class FakeExecutor:
    """Feeds every executed action back into the fake game."""

    def __init__(self, memory: FakeMemory) -> None:
        self.memory = memory
        self.actions: list[MacroAction] = []
        self.actions_executed = 0

    def execute(self, action: MacroAction) -> None:
        self.actions.append(action)
        self.actions_executed += 1
        self.memory.apply(action)


def state(**changes: object) -> RawGameState:
    values: dict[str, object] = {
        "game_started": True,
        "map_id": TRAINING_MAP,
        "player_x": 5,
        "player_y": 27,
        "party_count": 6,
        "battle_state": 0,
    }
    values.update(changes)
    return RawGameState(**values)  # type: ignore[arg-type]


def balancing_kwargs(**overrides: object) -> dict[str, object]:
    """Every keyword argument the loop requires.

    Assembling this is half the point.  A call site supplying seven of the
    eighteen arguments shipped and reached the emulator, because nothing else
    ever invoked the function.
    """

    kwargs: dict[str, object] = {
        "policy": BalancedTeamPolicy(minimum_level=55, maximum_level_spread=40, required_size=6),
        "expected_map": TRAINING_MAP,
        "intent": BattleIntent("team_training", "wild_training"),
        "flee_timing": object(),
        "hideout_timing": object(),
        "flee_func": lambda *_args: None,
        "heal_and_return": lambda *_args: None,
        "is_in_center": lambda raw: raw.map_id == CENTER_MAP,
        "is_in_map": lambda raw: raw.map_id == TRAINING_MAP,
        "walk_to_grass": lambda *_args: 1,
        "move_slot": lambda _raw: 1,
        "report_label": "harness training",
        "checkpoint_count": 9,
    }
    kwargs.update(overrides)
    return kwargs


def run(memory: FakeMemory, reader: FakeReader, **overrides: object) -> object:
    return run_red_team_balancing(
        FakeExecutor(memory),  # type: ignore[arg-type]
        reader,  # type: ignore[arg-type]
        memory,  # type: ignore[arg-type]
        **balancing_kwargs(**overrides),  # type: ignore[arg-type]
    )


def test_a_finished_team_runs_the_loop_to_its_exit() -> None:
    """The whole point: execute the loop, so unexecuted code cannot ship."""

    memory = FakeMemory()
    memory.set_party([(species, 60) for species in FINAL_FORM_ROSTER])
    reader = FakeReader([state()])

    result = run(memory, reader)

    assert isinstance(result, tuple) and len(result) == 3
    report, battles, _healing = result
    assert battles == 0
    assert report is not None and report.passed
    # The exit path restores the qualified core, so the swap helper really ran.
    assert memory.swaps, "restoring the training core should have moved the party"
    assert memory.party[0].species == BLASTOISE_SPECIES_ID
    assert memory.party[1].species == DUX_SPECIES_ID
    assert memory.party[2].species == DUGTRIO_SPECIES_ID


def test_training_without_the_escort_fails_before_the_first_step() -> None:
    """Checked up front, not after twenty-five minutes of walking.

    A later check inside the loop would also raise, and would also mention the
    escort — so the assertion is that *nothing was pressed first*.
    """

    memory = FakeMemory()
    memory.set_party([(DUGTRIO_SPECIES_ID, 30) for _ in range(6)])
    executor = FakeExecutor(memory)

    with pytest.raises(RuntimeError, match="lacks its qualified Blastoise escort"):
        run_red_team_balancing(
            executor,  # type: ignore[arg-type]
            FakeReader([state()]),  # type: ignore[arg-type]
            memory,  # type: ignore[arg-type]
            **balancing_kwargs(),  # type: ignore[arg-type]
        )

    assert executor.actions_executed == 0, "the escort check must precede any input"


def test_a_wrong_venue_stops_early_and_names_the_band() -> None:
    """The Mansion deadlock, reproduced in milliseconds instead of 25 minutes.

    A level-20 trainee against a level-32 wild cannot fight and cannot win, so
    the run flees forever.  The real run burned thirty-three flees and zero
    battles before anyone knew.  Here it takes eight, and the numbers survive
    into the message.
    """

    memory = FakeMemory()
    memory.set_party(
        [(DIGLETT_SPECIES_ID, 20), (BLASTOISE_SPECIES_ID, ESCORT_LEVEL_CAP - 5)]
        + [(DUGTRIO_SPECIES_ID, 25) for _ in range(4)],
        hp=30,  # below the retreat ratio, so every matchup reads as unsafe
    )
    reader = FakeReader([state(battle_state=1, enemy_level=32, enemy_species_id=0x21)])
    flees = 0

    def count_flee(*_args: object) -> None:
        nonlocal flees
        flees += 1

    with pytest.raises(RuntimeError) as failure:
        run(memory, reader, flee_func=count_flee)

    # The bound that matters is the early one, and it has to be the bound that
    # fires. The generic consecutive-flee cap would also stop this eventually —
    # four times later, which is the run we already paid for. Comparing against
    # VENUE_MISMATCH_FLEES itself would prove nothing: raise the constant and
    # the comparison rises with it.
    message = str(failure.value)
    assert "Training venue does not match" in message, f"the wrong bound fired: {message}"
    assert flees <= 10, f"gave up after {flees} flees, which is a run half wasted"
    assert "32" in message, f"the encounter band must survive into the report: {message}"
    assert "20" in message, f"our own levels must survive into the report: {message}"


def test_a_run_that_never_finds_a_battle_is_reported_as_unfinished() -> None:
    """Exhausting the step budget has to be loud; a quiet stop wastes a run."""

    memory = FakeMemory()
    memory.set_party(
        [(BLASTOISE_SPECIES_ID, 20), (DUX_SPECIES_ID, 20), (DUGTRIO_SPECIES_ID, 20)]
        + [(JOLTEON_SPECIES_ID, 20) for _ in range(3)]
    )
    policy = BalancedTeamPolicy(
        minimum_level=55, maximum_level_spread=40, required_size=6, max_steps=64
    )

    with pytest.raises(RuntimeError, match="stopped before readiness"):
        run(memory, FakeReader([state()]), policy=policy)


def test_the_venue_bound_is_far_below_the_flee_bound() -> None:
    """Eight encounters is enough to see a mismatch; thirty-three is a lost run."""

    assert VENUE_MISMATCH_FLEES < 32


def test_the_party_reader_sees_what_the_harness_wrote() -> None:
    """Guards the fixture itself: a wrong offset would silently fake a party."""

    memory = FakeMemory()
    memory.set_party([(BLASTOISE_SPECIES_ID, 60), (DIGLETT_SPECIES_ID, 20)], hp=40)
    observed = PokemonRedPartyReader(memory).read()  # type: ignore[arg-type]

    assert observed.size == 2
    assert observed.species_ids() == (BLASTOISE_SPECIES_ID, DIGLETT_SPECIES_ID)
    assert observed.levels == (60, 20)
    assert observed.minimum_level == 20
    assert observed.members[0].hp == 40
    assert observed.members[0].max_hp == 80
    assert all(not member.is_fainted for member in observed.members)


def test_internal_indices_are_not_pokedex_ordinals() -> None:
    """Blastoise is 0x1C internally and 9 in the dex; mixing them is silent.

    An earlier version of this file wrote species 9 and labelled it Blastoise.
    Both of its tests passed, because neither looked at anything.
    """

    memory = FakeMemory()
    memory.set_party([(9, 60)])  # the dex ordinal, written as though internal
    observed = PokemonRedPartyReader(memory).read()  # type: ignore[arg-type]

    assert observed.species_ids() == (9,)
    assert observed.species_ids() != (BLASTOISE_SPECIES_ID,)
