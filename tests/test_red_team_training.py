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

from pokemon_red_completion import red_team_training
from pokemon_red_completion.actions import MacroAction, MacroActionKind
from pokemon_red_completion.battle_runtime import BattleIntent, BattleRuntimeError
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
from pokemon_red_completion.team_training import BalancedTeamPolicy, GrindingArea
from pokemon_red_completion.training_venue import TrainingVenue

DIGLETT_SPECIES_ID = 0x3B
TACKLE_MOVE_ID = 0x21
#: The fake gives every member one damaging move and no field moves.
#:
#: The member submenu is ordered moves, STATS, SWITCH, CANCEL -- measured from a
#: captured state, where Blastoise knowing two field moves gave a five-entry
#: submenu whose row three performed the swap. So SWITCH sits at
#: ``field moves + 1``, which is row one here.
FIELD_MOVES_PER_MEMBER = 0
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
        if addr == int(RamAddress.MAX_MENU_ITEM):
            return self._max_menu_item()
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
            self._cancel()
        elif kind is MacroActionKind.MOVE:
            self._move(str(action.value))
        elif kind is MacroActionKind.CONFIRM:
            self._confirm()

    def _cancel(self) -> None:
        """Back out one level, the way the game does.

        Cancelling a member submenu returns to the party list, not to the
        field. The search for the SWITCH row relies on that: a wrong row is
        undone by cancelling and re-entering the source slot. A fake that
        dropped straight to the field made the search look like it gave up
        after one attempt, which is exactly what the run reported.
        """

        if self.stage in {"member", "party_target"}:
            self.stage, self.cursor = "party", 0
        elif self.stage == "party":
            self.stage, self.cursor = "root", 0
        else:
            self.stage, self.cursor = "field", 0
        self.pending_slot = None

    def _max_menu_item(self) -> int:
        """The highest index the menu currently on screen will accept.

        This is the detail an earlier version of this fake got wrong, and the
        omission cost two emulator runs. The member submenu is not the party
        list: it lists the Pokémon's usable field moves, then SWITCH, STATS and
        CANCEL. With Blastoise in front that is five entries against a party of
        six, so a cursor driven past the end of it stops at four — which is
        exactly what the game reported.
        """

        if self.stage in {"party", "party_target"}:
            return len(self.party) - 1
        if self.stage == "member":
            return self._field_move_count() + 2  # moves, then STATS, SWITCH, CANCEL
        return 5

    def _field_move_count(self) -> int:
        """How many field moves the selected member contributes to its submenu."""

        return FIELD_MOVES_PER_MEMBER

    def _move(self, direction: str) -> None:
        if self.stage == "field":
            return
        if direction == "down":
            self.cursor = min(self.cursor + 1, self._max_menu_item())
        elif direction == "up":
            self.cursor = max(self.cursor - 1, 0)

    def _confirm(self) -> None:
        if self.stage == "root" and self.cursor == 1:  # the POKEMON entry
            self.stage, self.cursor = "party", 0
        elif self.stage == "party":
            self.pending_slot, self.stage, self.cursor = self.cursor, "member", 0
        elif self.stage == "member":
            # Only SWITCH leads anywhere. Selecting STATS or a field move by
            # mistake leaves the submenu open, which is what really happened:
            # the run then drove this five-entry menu believing it was choosing
            # a party slot.
            if self.cursor == self._field_move_count() + 1:  # moves, STATS, SWITCH
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


def _venue(band: GrindingArea, map_id: int = TRAINING_MAP) -> TrainingVenue:
    """A venue over a measured band, with navigation the fake can satisfy."""

    return TrainingVenue(
        band=band,
        map_id=map_id,
        walk_to_grass=lambda *_args: 1,
        heal_and_return=lambda *_args: None,
        is_in_center=lambda raw: raw.map_id == CENTER_MAP,
        move_slot=lambda _raw: 1,
    )


def balancing_kwargs(**overrides: object) -> dict[str, object]:
    """Every keyword argument the loop requires.

    Assembling this is half the point.  A call site supplying seven of the
    eighteen arguments shipped and reached the emulator, because nothing else
    ever invoked the function.
    """

    venue_band = overrides.pop(
        "venue_band",
        GrindingArea(
            area_id="test_area",
            minimum_encounter_level=1,
            maximum_encounter_level=10,
            rare_maximum_encounter_level=10,
            measured_samples=100,
        ),
    )
    default_venues = [_venue(venue_band, map_id=overrides.pop("expected_map", TRAINING_MAP))]

    kwargs: dict[str, object] = {
        "policy": BalancedTeamPolicy(minimum_level=55, maximum_level_spread=40, required_size=6),
        "intent": BattleIntent("team_training", "wild_training"),
        "flee_timing": object(),
        "hideout_timing": object(),
        "flee_func": lambda *_args: None,
        "report_label": "harness training",
        "checkpoint_count": 9,
        "venues": overrides.pop("venues", default_venues),
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


def test_an_unrelated_battle_runtime_failure_is_not_misreported_as_pp_exhaustion(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Only the move policy's explicit recovery request may enter the escape path.

    ``BattleRuntimeError`` also reports broken observations, invalid menus, and
    unexpected battle transitions. Treating all of those as exhausted PP hides
    their actual cause and starts an unrelated party-switch sequence.
    """

    memory = FakeMemory()
    memory.set_party(
        [(DIGLETT_SPECIES_ID, 20), (BLASTOISE_SPECIES_ID, ESCORT_LEVEL_CAP - 5)]
        + [(DUGTRIO_SPECIES_ID, 25) for _ in range(4)]
    )
    reader = FakeReader(
        [state(battle_state=1, enemy_level=10, enemy_species_id=0x21)]
    )

    monkeypatch.setattr(red_team_training, "training_attack_pp", lambda _member: 20)

    def fail_battle(*_args: object, **_kwargs: object) -> None:
        raise BattleRuntimeError("semantic battle observation failed")

    monkeypatch.setattr(red_team_training, "run_adaptive_wild_battle", fail_battle)

    with pytest.raises(BattleRuntimeError, match="semantic battle observation failed"):
        run(memory, reader)


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


def test_the_venue_mismatch_stop_names_where_the_trainee_belongs() -> None:
    """A diagnosis that stops short of the answer costs another run to finish.

    "Train them where their own level lives" is true and useless. With measured
    bands in hand the area is computable at the moment of the stop.
    """

    memory = FakeMemory()
    memory.set_party(
        [(DIGLETT_SPECIES_ID, 20), (BLASTOISE_SPECIES_ID, ESCORT_LEVEL_CAP - 5)]
        + [(DUGTRIO_SPECIES_ID, 25) for _ in range(4)],
        hp=30,
    )
    reader = FakeReader([state(battle_state=1, enemy_level=32, enemy_species_id=0x21)])
    venues = (
        GrindingArea(
            area_id="digletts_cave",
            minimum_encounter_level=15,
            maximum_encounter_level=21,
            rare_maximum_encounter_level=31,
            measured_samples=29,
        ),
    )

    with pytest.raises(RuntimeError) as failure:
        run(
            memory,
            reader,
            venues=[
                TrainingVenue(
                    band=venues[0],
                    map_id=TRAINING_MAP,
                    walk_to_grass=lambda *_args: 1,
                    heal_and_return=lambda *_args: None,
                    is_in_center=lambda raw: raw.map_id == CENTER_MAP,
                    move_slot=lambda _raw: 1,
                )
            ],
        )

    message = str(failure.value)
    assert "digletts_cave" in message, f"the stop should name the venue: {message}"
    assert "29 encounters" in message, "and say how well that venue was measured"


def test_a_stop_with_nowhere_to_send_anyone_says_so_plainly() -> None:
    """Silence beats invention when no measured area suits the trainee.

    The venue set is no longer optional -- a run with no venue has nowhere to
    walk and nothing to judge a matchup against, and is refused up front. What
    is still possible is a party too weak for every venue on offer, and the
    stop has to admit that rather than name one anyway.
    """

    memory = FakeMemory()
    # The escort sits at the level floor, so it is not itself a trainee, and
    # nobody else can reach a band starting at 28.
    memory.set_party(
        [(DIGLETT_SPECIES_ID, 20), (BLASTOISE_SPECIES_ID, ESCORT_LEVEL_CAP)]
        + [(DUGTRIO_SPECIES_ID, 25) for _ in range(4)]
    )
    reader = FakeReader([state()])
    too_strong = GrindingArea(
        area_id="pokemon_mansion_1f",
        minimum_encounter_level=28,
        maximum_encounter_level=34,
        rare_maximum_encounter_level=39,
        measured_samples=164,
    )

    with pytest.raises(RuntimeError) as failure:
        run(memory, reader, venues=[_venue(too_strong)])

    message = str(failure.value)
    assert "No measured area suits" in message, f"it should admit it has nowhere: {message}"
    assert "digletts_cave" not in message, "and must not invent a venue it was not given"


def test_a_run_given_no_venue_at_all_is_refused_up_front() -> None:
    """An empty venue list used to be the default, and guaranteed a crash.

    ``current_venue`` stayed None until a trainee was matched to a band, but
    RESTORE_TEAM -- or an unsafe escort -- reaches the healing branch on the
    first iteration and dereferences it. Six call sites did that.
    """

    memory = FakeMemory()
    memory.set_party([(species, 60) for species in FINAL_FORM_ROSTER])

    with pytest.raises(RuntimeError, match="given no venue"):
        run(memory, FakeReader([state()]), venues=[])


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


class MisplacedSwitchMemory(FakeMemory):
    """A fake whose SWITCH row is not where the move list predicts.

    The real game put SWITCH somewhere three separate guesses did not expect.
    This makes the harness able to say so: the row is deliberately moved away
    from ``field_move_count``, so a search that only tries its first guess
    cannot pass.
    """

    #: Two rows further out than the move list predicts.
    EXTRA_FIELD_MOVES = 2

    def _max_menu_item(self) -> int:
        if self.stage == "member":
            return 4
        return super()._max_menu_item()

    def _field_move_count(self) -> int:
        return self.EXTRA_FIELD_MOVES


def test_the_switch_row_is_found_even_when_it_is_not_where_expected() -> None:
    """Three guesses at this row have each cost an emulator run.

    The search tries rows until the cursor can be placed on the slot it needs
    to swap with — a question about the job rather than a claim about the
    menu's shape — so it survives the layout being different from any guess.
    """

    memory = MisplacedSwitchMemory()
    memory.set_party([(species, 60) for species in FINAL_FORM_ROSTER])
    reader = FakeReader([state()])

    result = run(memory, reader)

    assert isinstance(result, tuple)
    assert memory.swaps, "the core restore should still have reordered the party"
    assert memory.party[0].species == BLASTOISE_SPECIES_ID
    assert memory.party[1].species == DUX_SPECIES_ID
