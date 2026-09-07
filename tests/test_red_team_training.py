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

import json
from collections.abc import Callable

import pytest

from pokemon_red_completion import red_team_training
from pokemon_red_completion.actions import MacroAction, MacroActionKind
from pokemon_red_completion.battle_runtime import (
    BattleIntent,
    BattleRuntimeError,
    BattleRuntimeTiming,
)
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
    FixedPartyTrainingDose,
    TeamTrainingExecutionSummary,
    run_red_team_balancing,
    switch_active_battler,
)
from pokemon_red_completion.team_training import (
    BalancedTeamPolicy,
    GrindingArea,
    TeamTrainingProgress,
)
from pokemon_red_completion.training_candidate_rank import (
    TrainingCandidateDecision,
    TrainingChoiceKind,
)
from pokemon_red_completion.training_control import TrainingControlAction, TrainingControlDecision
from pokemon_red_completion.training_venue import TrainingVenue, WarpSafeVenueWalker

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
        if addr == int(RamAddress.TOP_MENU_ITEM_X):
            return self._menu_top()[0]
        if addr == int(RamAddress.TOP_MENU_ITEM_Y):
            return self._menu_top()[1]
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
        if kind is MacroActionKind.OPEN_MENU and self.stage == "field":
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

    def _menu_top(self) -> tuple[int, int]:
        if self.stage == "root":
            return (11, 2)
        if self.stage in {"party", "party_target"}:
            return (0, 1)
        if self.stage == "member":
            return (10, 8)
        return (0, 0)

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


def test_verified_battle_switch_survives_a_delayed_menu_cursor_signature() -> None:
    class SwitchMemory:
        def __init__(self) -> None:
            self.player_reads = 0
            self.cursor_reads = 0

        def read_u8(self, address: int) -> int:
            address = int(address)
            if address == int(RamAddress.PLAYER_MON_NUMBER):
                self.player_reads += 1
                return 0 if self.player_reads == 1 else 1
            if address == int(RamAddress.CURRENT_MENU_ITEM):
                self.cursor_reads += 1
                return 1 if self.cursor_reads == 1 else 0
            if address == int(RamAddress.PARTY_COUNT):
                return 2
            hp_base = int(RamAddress.PARTY_MON_1_HP)
            if address in {hp_base, hp_base + PARTY_STRUCT_STRIDE}:
                return 0
            if address in {hp_base + 1, hp_base + PARTY_STRUCT_STRIDE + 1}:
                return 80
            return 0

    class SwitchReader:
        def __init__(self) -> None:
            self.menu_reads = 0

        def read(self) -> RawGameState:
            return state(
                battle_state=1,
                party_count=2,
                party_species_ids=(DUGTRIO_SPECIES_ID, BLASTOISE_SPECIES_ID),
            )

        def read_battle_menu_state(self, raw: RawGameState) -> BattleMenuState:
            self.menu_reads += 1
            if self.menu_reads <= 2:
                return BattleMenuState(
                    BattleMenuPhase.MAIN,
                    selected_main_command=2,
                )
            return BattleMenuState(BattleMenuPhase.UNKNOWN)

    class SwitchActions:
        def __init__(self) -> None:
            self.actions: list[MacroAction] = []

        def execute(self, action: MacroAction) -> None:
            self.actions.append(action)

    memory = SwitchMemory()
    reader = SwitchReader()
    actions = SwitchActions()

    switched = switch_active_battler(
        actions,
        reader,  # type: ignore[arg-type]
        memory,  # type: ignore[arg-type]
        target_index=1,
        label="Blastoise escort",
    )

    assert switched
    assert memory.player_reads == 2
    assert reader.menu_reads == 50


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


@pytest.mark.parametrize("quantum", [0, -1, True, "1", 5])
def test_evolution_quantum_rejects_invalid_or_over_budget_values(quantum):
    memory = FakeMemory()
    with pytest.raises(ValueError, match="quantum exceeds"):
        run(
            memory,
            FakeReader([state()]),
            policy=BalancedTeamPolicy(max_battles=4),
            evolution_target=(DIGLETT_SPECIES_ID, DUGTRIO_SPECIES_ID),
            evolution_battle_quantum=quantum,
        )


@pytest.mark.parametrize(
    "options", [{"allow_direct_evolution": True}, {"evolution_battle_quantum": 1}]
)
def test_evolution_controls_cannot_change_non_evolution_training(options):
    with pytest.raises(ValueError, match="require an evolution target"):
        run(FakeMemory(), FakeReader([state()]), **options)


def test_direct_evolution_completes_one_battle_and_pauses_with_capped_escort(monkeypatch):
    from types import SimpleNamespace

    memory = FakeMemory()
    memory.set_party(
        [
            (DIGLETT_SPECIES_ID, 30),
            (BLASTOISE_SPECIES_ID, 63),
            (DUX_SPECIES_ID, 40),
            (JOLTEON_SPECIES_ID, 40),
            (SNORLAX_SPECIES_ID, 40),
            (HITMONLEE_SPECIES_ID, 40),
        ]
    )

    class Reader:
        raw = state(battle_state=1, enemy_level=10, enemy_species_id=0x21)

        def read(self):
            return self.raw

        def read_input_readiness(self):
            return SimpleNamespace(ready=True)

    reader = Reader()
    fights = []

    def battle(*args, **kwargs):
        fights.append(PokemonRedPartyReader(memory).read().lead.species_id)
        reader.raw = state()

    monkeypatch.setattr(red_team_training, "training_attack_pp", lambda member: 40)
    monkeypatch.setattr(red_team_training, "run_adaptive_wild_battle", battle)
    with pytest.raises(red_team_training.EvolutionTrainingPaused) as paused:
        run(
            memory,
            reader,
            evolution_target=(DIGLETT_SPECIES_ID, DUGTRIO_SPECIES_ID),
            allow_direct_evolution=True,
            evolution_battle_quantum=1,
        )
    assert fights == [DIGLETT_SPECIES_ID]
    assert paused.value.battles == 1
    assert paused.value.healing_trips == 0
    assert not memory.swaps


@pytest.mark.parametrize("direct", [False, True])
def test_direct_evolution_flag_does_not_bypass_matchup_or_pp(monkeypatch, direct):
    memory = FakeMemory()
    memory.set_party([(DIGLETT_SPECIES_ID, 30), (BLASTOISE_SPECIES_ID, 63)])
    trainee = PokemonRedPartyReader(memory).read().lead
    policy = BalancedTeamPolicy(minimum_direct_level_advantage=5)
    monkeypatch.setattr(red_team_training, "training_attack_pp", lambda member: 40)
    assert (
        red_team_training.trainee_should_fight_directly(
            trainee,
            enemy_level=10,
            enemy_species=0x21,
            policy=policy,
            participation_only=not direct,
        )
        is direct
    )
    assert not red_team_training.trainee_should_fight_directly(
        trainee, enemy_level=40, enemy_species=0x21, policy=policy, participation_only=not direct
    )
    monkeypatch.setattr(red_team_training, "training_attack_pp", lambda member: 0)
    assert not red_team_training.trainee_should_fight_directly(
        trainee, enemy_level=10, enemy_species=0x21, policy=policy, participation_only=not direct
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


def test_targeted_evolution_honors_callers_smaller_step_bound(monkeypatch):
    monkeypatch.setattr(red_team_training, "training_attack_pp", lambda _member: 40)
    memory = FakeMemory()
    memory.set_party(
        [
            (DIGLETT_SPECIES_ID, 30),
            (BLASTOISE_SPECIES_ID, 50),
            (DUX_SPECIES_ID, 40),
            (JOLTEON_SPECIES_ID, 40),
            (SNORLAX_SPECIES_ID, 40),
            (HITMONLEE_SPECIES_ID, 40),
        ]
    )
    with pytest.raises(RuntimeError, match="Targeted evolution exhausted its bounded training"):
        run(
            memory,
            FakeReader([state()]),
            policy=BalancedTeamPolicy(
                minimum_level=55, maximum_level_spread=40, required_size=6, max_steps=1
            ),
            evolution_target=(DIGLETT_SPECIES_ID, DUGTRIO_SPECIES_ID),
        )


def test_finished_team_emits_exact_outcome_counters_after_cleanup() -> None:
    memory = FakeMemory()
    memory.set_party([(species, 60) for species in FINAL_FORM_ROSTER])
    summaries: list[TeamTrainingExecutionSummary] = []

    run(
        memory,
        FakeReader([state()]),
        execution_summary_sink=summaries.append,
    )

    assert len(summaries) == 1
    assert summaries[0].public_dict() == {
        "battles_completed": 0,
        "steps_taken": 0,
        "healing_trips": 1,
        "venue_transition_trips": 0,
        "required_recovery_trips": 0,
        "optional_recovery_trips": 0,
        "cleanup_trips": 1,
        "faints": 0,
        "rotations_executed": 1,
        "traversal_instrumented_walkers": 0,
        "traversal_movement_attempts": 0,
        "traversal_successful_steps": 0,
        "traversal_blocked_attempts": 0,
        "traversal_excluded_transition_skips": 0,
        "traversal_no_progress_cycles": 0,
    }


def test_fixed_party_training_dose_runs_exact_battles_without_reselecting(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    memory = FakeMemory()
    memory.set_party(
        [
            (BLASTOISE_SPECIES_ID, 50),
            (DUX_SPECIES_ID, 20),
            (DIGLETT_SPECIES_ID, 22),
            (JOLTEON_SPECIES_ID, 30),
            (SNORLAX_SPECIES_ID, 25),
            (HITMONLEE_SPECIES_ID, 30),
        ]
    )
    monkeypatch.setattr(red_team_training, "training_attack_pp", lambda _member: 20)
    battles: list[str] = []
    monkeypatch.setattr(
        red_team_training,
        "run_adaptive_wild_battle",
        lambda *_args, **_kwargs: battles.append("complete"),
    )
    summaries: list[TeamTrainingExecutionSummary] = []
    candidate_decisions: list[TrainingCandidateDecision] = []

    report, completed, healing = run(
        memory,
        FakeReader(
            [
                state(
                    battle_state=1,
                    enemy_level=10,
                    enemy_species_id=0x21,
                )
            ]
        ),
        policy=BalancedTeamPolicy(
            minimum_level=60,
            maximum_level_spread=50,
            required_size=6,
            max_battles=4,
            max_steps=100,
            max_healing_trips=3,
            max_faints=0,
        ),
        fixed_dose=FixedPartyTrainingDose(
            trainee_species_lineage=(BLASTOISE_SPECIES_ID,),
            venue_identity=GrindingArea(
                area_id="test_area",
                minimum_encounter_level=1,
                maximum_encounter_level=10,
                rare_maximum_encounter_level=10,
                measured_samples=100,
            ).identity,
            completed_battles=4,
        ),
        candidate_decision_sink=candidate_decisions.append,
        execution_summary_sink=summaries.append,
    )

    assert report is not None and not report.passed
    assert completed == 4
    assert healing == 1
    assert battles == ["complete"] * 4
    assert candidate_decisions == []
    assert memory.swaps == []
    assert summaries[0].progress.battles_completed == 4
    assert summaries[0].cleanup_trips == 1


def test_targeted_party_development_trains_the_bound_species_not_the_weakest(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    memory = FakeMemory()
    memory.set_party(
        [
            (DUX_SPECIES_ID, 20),
            (BLASTOISE_SPECIES_ID, 50),
            (DIGLETT_SPECIES_ID, 10),
            (JOLTEON_SPECIES_ID, 30),
            (SNORLAX_SPECIES_ID, 25),
            (HITMONLEE_SPECIES_ID, 30),
        ]
    )
    monkeypatch.setattr(red_team_training, "training_attack_pp", lambda _member: 20)

    def complete_battle(*_args: object, **_kwargs: object) -> None:
        target = next(member for member in memory.party if member.species == DUX_SPECIES_ID)
        target.level += 1

    monkeypatch.setattr(
        red_team_training,
        "run_adaptive_wild_battle",
        complete_battle,
    )

    report, completed, _healing = run(
        memory,
        FakeReader([state(battle_state=1, enemy_level=10, enemy_species_id=0x21)]),
        policy=BalancedTeamPolicy(
            minimum_level=21,
            maximum_level_spread=50,
            required_size=6,
            max_battles=2,
            max_steps=100,
            max_healing_trips=3,
            max_faints=0,
        ),
        development_target_species_id=DUX_SPECIES_ID,
    )

    levels = {member.species: member.level for member in memory.party}
    assert report is None
    assert completed == 1
    assert levels[DUX_SPECIES_ID] == 21
    assert levels[DIGLETT_SPECIES_ID] == 10


def test_fixed_dose_does_not_exceed_its_recovery_budget_for_cleanup(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    memory = FakeMemory()
    memory.set_party(
        [(BLASTOISE_SPECIES_ID, 50)]
        + [(species, 30) for species in FINAL_FORM_ROSTER if species != BLASTOISE_SPECIES_ID]
    )
    monkeypatch.setattr(red_team_training, "training_attack_pp", lambda _member: 20)
    monkeypatch.setattr(
        red_team_training,
        "run_adaptive_wild_battle",
        lambda *_args, **_kwargs: None,
    )
    summaries: list[TeamTrainingExecutionSummary] = []

    _report, completed, healing = run(
        memory,
        FakeReader([state(battle_state=1, enemy_level=10, enemy_species_id=0x21)]),
        policy=BalancedTeamPolicy(
            minimum_level=60,
            maximum_level_spread=50,
            required_size=6,
            max_battles=1,
            max_steps=100,
            max_healing_trips=0,
            max_faints=0,
        ),
        fixed_dose=FixedPartyTrainingDose(
            trainee_species_lineage=(BLASTOISE_SPECIES_ID,),
            venue_identity=GrindingArea(
                area_id="test_area",
                minimum_encounter_level=1,
                maximum_encounter_level=10,
                rare_maximum_encounter_level=10,
                measured_samples=100,
            ).identity,
            completed_battles=1,
        ),
        execution_summary_sink=summaries.append,
    )

    assert completed == 1
    assert healing == 0
    assert summaries[0].cleanup_trips == 0
    assert summaries[0].progress.healing_trips == 0


def test_fixed_party_training_dose_rejects_an_ambiguous_trainee_before_input() -> None:
    memory = FakeMemory()
    memory.set_party(
        [
            (BLASTOISE_SPECIES_ID, 50),
            (DUGTRIO_SPECIES_ID, 20),
            (DIGLETT_SPECIES_ID, 22),
            (JOLTEON_SPECIES_ID, 30),
            (SNORLAX_SPECIES_ID, 25),
            (HITMONLEE_SPECIES_ID, 30),
        ]
    )
    executor = FakeExecutor(memory)

    with pytest.raises(RuntimeError, match="trainee is not uniquely bound"):
        run_red_team_balancing(
            executor,  # type: ignore[arg-type]
            FakeReader([state()]),  # type: ignore[arg-type]
            memory,  # type: ignore[arg-type]
            **balancing_kwargs(
                fixed_dose=FixedPartyTrainingDose(
                    trainee_species_lineage=(DIGLETT_SPECIES_ID, DUGTRIO_SPECIES_ID),
                    venue_identity=GrindingArea(
                        area_id="test_area",
                        minimum_encounter_level=1,
                        maximum_encounter_level=10,
                        rare_maximum_encounter_level=10,
                        measured_samples=100,
                    ).identity,
                    completed_battles=4,
                )
            ),  # type: ignore[arg-type]
        )

    assert executor.actions_executed == 0


def test_fixed_party_training_dose_rejects_a_nonexistent_venue_before_input() -> None:
    memory = FakeMemory()
    memory.set_party([(species, 50) for species in FINAL_FORM_ROSTER])
    executor = FakeExecutor(memory)

    with pytest.raises(RuntimeError, match="venue is not uniquely executable"):
        run_red_team_balancing(
            executor,  # type: ignore[arg-type]
            FakeReader([state()]),  # type: ignore[arg-type]
            memory,  # type: ignore[arg-type]
            **balancing_kwargs(
                fixed_dose=FixedPartyTrainingDose(
                    trainee_species_lineage=(BLASTOISE_SPECIES_ID,),
                    venue_identity=("not-a-real-venue", ()),
                    completed_battles=4,
                )
            ),  # type: ignore[arg-type]
        )

    assert executor.actions_executed == 0


@pytest.mark.parametrize(
    "dose",
    [
        ((1, 1), ("venue", ()), 4),
        ((0,), ("venue", ()), 4),
        ((1,), ("", ()), 4),
        ((1,), ("venue", ()), 0),
    ],
)
def test_fixed_party_training_dose_rejects_invalid_bindings(
    dose: tuple[tuple[int, ...], tuple[str, tuple[str, ...]], int],
) -> None:
    with pytest.raises(ValueError, match="fixed training dose"):
        FixedPartyTrainingDose(*dose)


def test_execution_summary_rejects_an_incomplete_healing_phase_breakdown() -> None:
    with pytest.raises(ValueError, match="phases are incomplete"):
        TeamTrainingExecutionSummary(
            progress=TeamTrainingProgress(healing_trips=1),
            rotations_executed=0,
            venue_transition_trips=0,
            required_recovery_trips=0,
            optional_recovery_trips=0,
            cleanup_trips=0,
        )


def test_execution_summary_rejects_incomplete_traversal_attempts() -> None:
    with pytest.raises(ValueError, match="traversal attempts are incomplete"):
        TeamTrainingExecutionSummary(
            progress=TeamTrainingProgress(),
            rotations_executed=0,
            venue_transition_trips=0,
            required_recovery_trips=0,
            optional_recovery_trips=0,
            cleanup_trips=0,
            traversal_instrumented_walkers=1,
            traversal_movement_attempts=2,
            traversal_successful_steps=1,
            traversal_blocked_attempts=0,
        )


def test_venue_transition_cannot_bypass_the_healing_budget(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(red_team_training, "training_attack_pp", lambda _member: 20)
    memory = FakeMemory()
    memory.set_party(
        [
            (BLASTOISE_SPECIES_ID, 48),
            (DUX_SPECIES_ID, 20),
            (DIGLETT_SPECIES_ID, 22),
            (JOLTEON_SPECIES_ID, 30),
            (SNORLAX_SPECIES_ID, 25),
            (HITMONLEE_SPECIES_ID, 30),
        ]
    )

    with pytest.raises(RuntimeError, match="venue-transition budget"):
        run(
            memory,
            FakeReader([state(map_id=CENTER_MAP, player_x=3, player_y=3)]),
            policy=BalancedTeamPolicy(
                minimum_level=55,
                maximum_level_spread=40,
                required_size=6,
                minimum_direct_level_advantage=5,
                max_healing_trips=0,
            ),
            evolution_target=(DIGLETT_SPECIES_ID, DUGTRIO_SPECIES_ID),
        )


def test_a_finished_team_emits_stop_supervision_before_cleanup() -> None:
    memory = FakeMemory()
    memory.set_party([(species, 60) for species in FINAL_FORM_ROSTER])
    decisions = []

    run(
        memory,
        FakeReader([state()]),
        decision_sink=decisions.append,
    )

    assert [decision.action for decision in decisions] == [TrainingControlAction.STOP]
    assert decisions[0].decision_index == 0
    assert decisions[0].observation.phase.value == "overworld"
    assert decisions[0].observation.candidate_actions == (TrainingControlAction.STOP,)


def test_overworld_authority_must_stop_at_verified_readiness() -> None:
    memory = FakeMemory()
    memory.set_party([(species, 60) for species in FINAL_FORM_ROSTER])
    decisions: list[TrainingControlDecision] = []

    with pytest.raises(RuntimeError, match="illegal phase action"):
        run(
            memory,
            FakeReader([state()]),
            decision_sink=decisions.append,
            decision_authority=lambda _decision: TrainingControlAction.SEEK,
        )
    assert decisions[0].observation.candidate_actions == (TrainingControlAction.STOP,)


def test_overworld_authority_cannot_skip_required_recovery() -> None:
    memory = FakeMemory()
    memory.set_party(
        [(species, 54 if index == 1 else 55) for index, species in enumerate(FINAL_FORM_ROSTER)],
        hp=1,
        max_hp=80,
    )
    decisions: list[TrainingControlDecision] = []

    with pytest.raises(RuntimeError, match="illegal phase action"):
        run(
            memory,
            FakeReader([state()]),
            decision_sink=decisions.append,
            decision_authority=lambda _decision: TrainingControlAction.SEEK,
        )
    assert decisions[0].observation.candidate_actions == (TrainingControlAction.HEAL,)


def test_model_selected_optional_heal_executes_and_pays_its_budget(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    memory = FakeMemory()
    memory.set_party(
        [(species, 54 if index == 1 else 55) for index, species in enumerate(FINAL_FORM_ROSTER)]
    )
    calls = {"heal": 0, "walk": 0}

    def heal(*_args: object) -> None:
        calls["heal"] += 1

    def walk(*_args: object) -> int:
        calls["walk"] += 1
        return 1

    monkeypatch.setattr(red_team_training, "training_attack_pp", lambda _member: 20)
    band = GrindingArea("test_area", 45, 55, rare_maximum_encounter_level=55, measured_samples=100)
    venue = TrainingVenue(
        band=band,
        map_id=TRAINING_MAP,
        walk_to_grass=walk,
        heal_and_return=heal,
        is_in_center=lambda raw: raw.map_id == CENTER_MAP,
        move_slot=lambda _raw: 1,
    )
    chose_optional_heal = False

    def authority(decision: TrainingControlDecision) -> TrainingControlAction:
        nonlocal chose_optional_heal
        if (
            not chose_optional_heal
            and decision.reason == "seek a bounded encounter in the selected venue"
        ):
            assert decision.observation.candidate_actions == (
                TrainingControlAction.SEEK,
                TrainingControlAction.HEAL,
            )
            chose_optional_heal = True
            return TrainingControlAction.HEAL
        return decision.action

    with pytest.raises(RuntimeError, match="step budget exhausted"):
        run(
            memory,
            FakeReader([state()]),
            policy=BalancedTeamPolicy(
                minimum_level=55,
                maximum_level_spread=40,
                required_size=6,
                max_steps=1,
                max_healing_trips=10,
            ),
            venues=[venue],
            decision_authority=authority,
        )

    assert chose_optional_heal
    assert calls == {"heal": 1, "walk": 1}


def test_balancer_uses_one_fresh_venue_walker_per_run(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A candidate clone cannot inherit pacing direction from an earlier clone."""

    memory = FakeMemory()
    memory.set_party(
        [(species, 54 if index == 1 else 55) for index, species in enumerate(FINAL_FORM_ROSTER)]
    )
    monkeypatch.setattr(red_team_training, "training_attack_pp", lambda _member: 20)
    calls = {"factory": 0, "fresh": 0, "legacy": 0}

    def legacy(*_args: object) -> int:
        calls["legacy"] += 1
        return 1

    def factory() -> Callable[[object, object, object], int]:
        calls["factory"] += 1

        def fresh(*_args: object) -> int:
            calls["fresh"] += 1
            return 1

        return fresh

    venue = TrainingVenue(
        band=GrindingArea(
            "run-local-walker",
            45,
            55,
            rare_maximum_encounter_level=55,
            measured_samples=100,
        ),
        map_id=TRAINING_MAP,
        walk_to_grass=legacy,
        heal_and_return=lambda *_args: None,
        is_in_center=lambda raw: raw.map_id == CENTER_MAP,
        move_slot=lambda _raw: 1,
        walk_to_grass_factory=factory,
    )

    with pytest.raises(RuntimeError, match="step budget exhausted"):
        run(
            memory,
            FakeReader([state()]),
            policy=BalancedTeamPolicy(
                minimum_level=55,
                maximum_level_spread=40,
                required_size=6,
                max_steps=1,
            ),
            venues=[venue],
        )

    assert calls == {"factory": 1, "fresh": 1, "legacy": 0}


def test_balancer_retains_identity_free_traversal_reliability_counters(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    memory = FakeMemory()
    memory.set_party(
        [(species, 54 if index == 1 else 55) for index, species in enumerate(FINAL_FORM_ROSTER)]
    )
    monkeypatch.setattr(red_team_training, "training_attack_pp", lambda _member: 20)
    summaries: list[TeamTrainingExecutionSummary] = []

    class CompletingWalker(WarpSafeVenueWalker):
        def __call__(self, actions: object, reader: object, emulator: object) -> int:
            del actions, reader
            assert isinstance(emulator, FakeMemory)
            self.movement_attempts += 2
            self.successful_steps += 1
            self.blocked_attempts += 1
            self.excluded_transition_skips += 1
            next(
                member for member in emulator.party if member.species == DUGTRIO_SPECIES_ID
            ).level = 55
            return 1

    walker = CompletingWalker(
        expected_map_id=TRAINING_MAP,
        excluded_coordinates=frozenset({(4, 4)}),
    )
    venue = TrainingVenue(
        band=GrindingArea(
            "instrumented-venue",
            45,
            55,
            rare_maximum_encounter_level=55,
            measured_samples=100,
        ),
        map_id=TRAINING_MAP,
        walk_to_grass=lambda *_args: 1,
        heal_and_return=lambda *_args: None,
        is_in_center=lambda raw: raw.map_id == CENTER_MAP,
        move_slot=lambda _raw: 1,
        walk_to_grass_factory=lambda: walker,
    )

    report, battles, _heals = run(
        memory,
        FakeReader([state()]),
        policy=BalancedTeamPolicy(
            minimum_level=55,
            maximum_level_spread=40,
            required_size=6,
        ),
        venues=[venue],
        execution_summary_sink=summaries.append,
    )

    assert report is not None and report.passed
    assert battles == 0
    assert len(summaries) == 1
    assert summaries[0].public_dict() == {
        "battles_completed": 0,
        "steps_taken": 1,
        "healing_trips": 1,
        "venue_transition_trips": 0,
        "required_recovery_trips": 0,
        "optional_recovery_trips": 0,
        "cleanup_trips": 1,
        "faints": 0,
        "rotations_executed": 3,
        "traversal_instrumented_walkers": 1,
        "traversal_movement_attempts": 2,
        "traversal_successful_steps": 1,
        "traversal_blocked_attempts": 1,
        "traversal_excluded_transition_skips": 1,
        "traversal_no_progress_cycles": 0,
    }


def test_balancing_emits_identity_free_trainee_and_venue_choices() -> None:
    memory = FakeMemory()
    memory.set_party(
        [
            (
                species,
                20 if species == DUX_SPECIES_ID else 40 if species == BLASTOISE_SPECIES_ID else 30,
            )
            for species in FINAL_FORM_ROSTER
        ]
    )
    candidate_decisions: list[TrainingCandidateDecision] = []

    with pytest.raises(RuntimeError, match="stopped before readiness"):
        run(
            memory,
            FakeReader([state()]),
            policy=BalancedTeamPolicy(
                minimum_level=55,
                maximum_level_spread=40,
                required_size=6,
                max_steps=1,
            ),
            candidate_decision_sink=candidate_decisions.append,
        )

    assert [decision.decision_index for decision in candidate_decisions] == list(
        range(len(candidate_decisions))
    )
    assert candidate_decisions
    assert {decision.observation.kind.value for decision in candidate_decisions} == {"trainee"}
    serialized = json.dumps(
        [decision.public_dict() for decision in candidate_decisions], sort_keys=True
    )
    assert "species" not in serialized
    assert "area_id" not in serialized
    assert "map" not in serialized


def test_candidate_authority_executes_an_alternate_trainee_binding(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    memory = FakeMemory()
    memory.set_party(
        [
            (
                species,
                20 if species == DUX_SPECIES_ID else 40 if species == BLASTOISE_SPECIES_ID else 30,
            )
            for species in FINAL_FORM_ROSTER
        ]
    )
    monkeypatch.setattr(red_team_training, "training_attack_pp", lambda _member: 20)
    chose_alternate = False

    def authority(decision: TrainingCandidateDecision) -> int:
        nonlocal chose_alternate
        if decision.observation.kind is TrainingChoiceKind.TRAINEE and not chose_alternate:
            chose_alternate = True
            assert decision.selected_candidate_index == 2
            return 1
        return decision.selected_candidate_index

    with pytest.raises(RuntimeError, match="stopped before readiness"):
        run(
            memory,
            FakeReader([state()]),
            policy=BalancedTeamPolicy(
                minimum_level=55,
                maximum_level_spread=40,
                required_size=6,
                max_steps=1,
            ),
            candidate_decision_authority=authority,
        )

    assert chose_alternate
    assert (0, 1) in memory.swaps, memory.swaps


def test_candidate_authority_agreement_is_behaviorally_a_no_op(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Merely installing authority cannot change the teacher's mechanic path."""

    monkeypatch.setattr(
        red_team_training,
        "member_is_unsafe_for_team_training",
        lambda _member, _policy: True,
    )
    monkeypatch.setattr(red_team_training, "training_attack_pp", lambda _member: 20)

    def exercise(*, authority: bool) -> tuple[list[tuple[int, int]], dict[str, int], list[str]]:
        memory = FakeMemory()
        memory.set_party(
            [
                (
                    species,
                    20
                    if species == DUGTRIO_SPECIES_ID
                    else 40
                    if species == BLASTOISE_SPECIES_ID
                    else 30,
                )
                for species in FINAL_FORM_ROSTER
            ]
        )
        calls = {"walk": 0, "heal": 0}
        kinds: list[str] = []

        def walk(*_args: object) -> int:
            calls["walk"] += 1
            return 1

        def heal(*_args: object) -> None:
            calls["heal"] += 1

        venue = TrainingVenue(
            band=GrindingArea(
                "agreement-venue",
                1,
                10,
                rare_maximum_encounter_level=10,
                measured_samples=100,
            ),
            map_id=TRAINING_MAP,
            walk_to_grass=walk,
            heal_and_return=heal,
            is_in_center=lambda raw: raw.map_id == CENTER_MAP,
            move_slot=lambda _raw: 1,
        )
        ineligible_venue = TrainingVenue(
            band=GrindingArea(
                "ineligible-agreement-venue",
                50,
                60,
                rare_maximum_encounter_level=60,
                measured_samples=100,
            ),
            map_id=TRAINING_MAP,
            walk_to_grass=lambda *_args: 1,
            heal_and_return=lambda *_args: None,
            is_in_center=lambda raw: raw.map_id == CENTER_MAP,
            move_slot=lambda _raw: 1,
        )

        def agree(decision: TrainingCandidateDecision) -> int:
            kinds.append(decision.observation.kind.value)
            return decision.selected_candidate_index

        with pytest.raises(RuntimeError, match="step budget exhausted"):
            run(
                memory,
                FakeReader([state()]),
                policy=BalancedTeamPolicy(
                    minimum_level=55,
                    maximum_level_spread=40,
                    required_size=6,
                    max_steps=1,
                    max_healing_trips=1,
                ),
                venues=[venue, ineligible_venue],
                candidate_decision_authority=agree if authority else None,
            )
        return memory.swaps, calls, kinds

    teacher_swaps, teacher_calls, teacher_kinds = exercise(authority=False)
    authority_swaps, authority_calls, authority_kinds = exercise(authority=True)

    assert teacher_kinds == []
    assert authority_kinds and set(authority_kinds) == {"trainee"}
    assert authority_swaps == teacher_swaps
    assert authority_calls == teacher_calls == {"walk": 1, "heal": 0}


def test_venue_compatible_trainee_rebinds_the_global_weaklings_restore_directive(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A temporarily untrainable weakling cannot force an infinite heal loop.

    The global planner selects the level-10 second member and asks to restore it.
    The measured venue cannot train that member, so the executor selects the
    level-25 third member instead. The directive must follow that executable
    choice; otherwise every recovery returns to this unchanged decision and no
    encounter-seeking step is ever taken.
    """

    memory = FakeMemory()
    memory.set_party(
        [
            (BLASTOISE_SPECIES_ID, 44),
            (DUGTRIO_SPECIES_ID, 10),
            (DUX_SPECIES_ID, 25),
            (JOLTEON_SPECIES_ID, 30),
            (SNORLAX_SPECIES_ID, 30),
            (HITMONLEE_SPECIES_ID, 30),
        ]
    )
    memory.party[1].hp = 20
    monkeypatch.setattr(red_team_training, "training_attack_pp", lambda _member: 20)
    calls = {"walk": 0, "heal": 0}

    def walk(*_args: object) -> int:
        calls["walk"] += 1
        return 1

    def heal(*_args: object) -> None:
        calls["heal"] += 1

    compatible = TrainingVenue(
        band=GrindingArea(
            "level-20-band",
            20,
            20,
            rare_maximum_encounter_level=20,
            measured_samples=100,
        ),
        map_id=TRAINING_MAP,
        walk_to_grass=walk,
        heal_and_return=heal,
        is_in_center=lambda raw: raw.map_id == CENTER_MAP,
        move_slot=lambda _raw: 1,
    )

    with pytest.raises(RuntimeError, match="step budget exhausted"):
        run(
            memory,
            FakeReader([state()]),
            policy=BalancedTeamPolicy(
                minimum_level=55,
                maximum_level_spread=50,
                required_size=6,
                minimum_direct_level_advantage=5,
                max_steps=1,
                max_healing_trips=1,
            ),
            venues=[compatible],
        )

    assert calls == {"walk": 1, "heal": 0}


def test_candidate_authority_executes_an_alternate_venue_binding(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    memory = FakeMemory()
    memory.set_party(
        [
            (
                species,
                20 if species == DUX_SPECIES_ID else 40 if species == BLASTOISE_SPECIES_ID else 30,
            )
            for species in FINAL_FORM_ROSTER
        ]
    )
    monkeypatch.setattr(red_team_training, "training_attack_pp", lambda _member: 20)
    walks = {"lower": 0, "higher": 0}

    def venue(name: str, minimum: int, maximum: int) -> TrainingVenue:
        def walk(*_args: object) -> int:
            walks[name] += 1
            return 1

        return TrainingVenue(
            band=GrindingArea(
                name,
                minimum,
                maximum,
                rare_maximum_encounter_level=maximum,
                measured_samples=100,
            ),
            map_id=TRAINING_MAP,
            walk_to_grass=walk,
            heal_and_return=lambda *_args: None,
            is_in_center=lambda raw: raw.map_id == CENTER_MAP,
            move_slot=lambda _raw: 1,
        )

    def authority(decision: TrainingCandidateDecision) -> int:
        if decision.observation.kind is TrainingChoiceKind.VENUE:
            assert decision.selected_candidate_index == 1
            return 0
        return decision.selected_candidate_index

    with pytest.raises(RuntimeError, match="stopped before readiness"):
        run(
            memory,
            FakeReader([state()]),
            policy=BalancedTeamPolicy(
                minimum_level=55,
                maximum_level_spread=40,
                required_size=6,
                max_steps=1,
            ),
            venues=[venue("lower", 1, 10), venue("higher", 5, 12)],
            candidate_decision_authority=authority,
        )

    assert walks == {"lower": 1, "higher": 0}, memory.swaps


def test_targeted_evolution_authority_executes_an_alternate_venue_binding(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    memory = FakeMemory()
    memory.set_party(
        [
            (BLASTOISE_SPECIES_ID, 48),
            (DUX_SPECIES_ID, 20),
            (DIGLETT_SPECIES_ID, 22),
            (JOLTEON_SPECIES_ID, 30),
            (SNORLAX_SPECIES_ID, 25),
            (HITMONLEE_SPECIES_ID, 30),
        ]
    )
    monkeypatch.setattr(red_team_training, "training_attack_pp", lambda _member: 20)
    transitions = {"lower": 0, "higher": 0}
    decisions: list[TrainingCandidateDecision] = []

    def venue(name: str, minimum: int, maximum: int, map_id: int) -> TrainingVenue:
        def heal_and_return(*_args: object) -> None:
            transitions[name] += 1

        return TrainingVenue(
            band=GrindingArea(
                name,
                minimum,
                maximum,
                rare_maximum_encounter_level=maximum,
                measured_samples=100,
            ),
            map_id=map_id,
            walk_to_grass=lambda *_args: 1,
            heal_and_return=heal_and_return,
            is_in_center=lambda raw: raw.map_id == CENTER_MAP,
            move_slot=lambda _raw: 1,
        )

    def authority(decision: TrainingCandidateDecision) -> int:
        decisions.append(decision)
        assert decision.observation.kind is TrainingChoiceKind.VENUE
        assert len(decision.observation.candidates) == 2
        assert decision.selected_candidate_index == 1
        return 0

    with pytest.raises(RuntimeError, match="venue-transition budget"):
        run(
            memory,
            FakeReader([state(map_id=int(MapId.PALLET_TOWN))]),
            policy=BalancedTeamPolicy(
                minimum_level=55,
                maximum_level_spread=40,
                required_size=6,
                minimum_direct_level_advantage=5,
                max_healing_trips=1,
            ),
            venues=[
                venue("lower", 1, 10, CENTER_MAP),
                venue("higher", 5, 12, TRAINING_MAP),
            ],
            evolution_target=(DIGLETT_SPECIES_ID, DUGTRIO_SPECIES_ID),
            candidate_decision_authority=authority,
        )

    assert decisions
    assert transitions == {"lower": 1, "higher": 0}


@pytest.mark.parametrize("include_ineligible_venue", [False, True])
def test_targeted_evolution_does_not_publish_a_singleton_venue_choice(
    include_ineligible_venue: bool,
) -> None:
    memory = FakeMemory()
    memory.set_party(
        [
            (BLASTOISE_SPECIES_ID, 48),
            (DUX_SPECIES_ID, 20),
            (DIGLETT_SPECIES_ID, 22),
            (JOLTEON_SPECIES_ID, 30),
            (SNORLAX_SPECIES_ID, 25),
            (HITMONLEE_SPECIES_ID, 30),
        ]
    )
    candidate_decisions: list[TrainingCandidateDecision] = []
    venues = [
        _venue(
            GrindingArea(
                "eligible-evolution-venue",
                1,
                10,
                rare_maximum_encounter_level=10,
                measured_samples=100,
            )
        )
    ]
    if include_ineligible_venue:
        venues.append(
            _venue(
                GrindingArea(
                    "ineligible-evolution-venue",
                    50,
                    60,
                    rare_maximum_encounter_level=60,
                    measured_samples=100,
                )
            )
        )

    with pytest.raises(RuntimeError, match="budget"):
        run(
            memory,
            FakeReader([state(map_id=CENTER_MAP, player_x=3, player_y=3)]),
            policy=BalancedTeamPolicy(
                minimum_level=55,
                maximum_level_spread=40,
                required_size=6,
                minimum_direct_level_advantage=5,
                max_healing_trips=0,
            ),
            venues=venues,
            evolution_target=(DIGLETT_SPECIES_ID, DUGTRIO_SPECIES_ID),
            candidate_decision_sink=candidate_decisions.append,
        )

    assert candidate_decisions == []


@pytest.mark.parametrize("selected", [True, -1, 99])
def test_candidate_authority_fails_closed_on_an_invalid_index(selected: object) -> None:
    memory = FakeMemory()
    memory.set_party(
        [
            (
                species,
                20 if species == DUX_SPECIES_ID else 40 if species == BLASTOISE_SPECIES_ID else 30,
            )
            for species in FINAL_FORM_ROSTER
        ]
    )

    with pytest.raises(RuntimeError, match="invalid candidate index"):
        run(
            memory,
            FakeReader([state()]),
            candidate_decision_authority=lambda _decision: selected,
        )


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


def test_battle_authority_masks_fight_and_rejects_an_illegal_override() -> None:
    memory = FakeMemory()
    memory.set_party(
        [(DIGLETT_SPECIES_ID, 20), (BLASTOISE_SPECIES_ID, ESCORT_LEVEL_CAP - 5)]
        + [(DUGTRIO_SPECIES_ID, 25) for _ in range(4)],
        hp=30,
    )
    reader = FakeReader([state(battle_state=1, enemy_level=10, enemy_species_id=0x21)])

    observed_candidates: list[tuple[TrainingControlAction, ...]] = []

    def illegal_override(decision: TrainingControlDecision) -> TrainingControlAction:
        observed_candidates.append(decision.observation.candidate_actions)
        return TrainingControlAction.FIGHT

    with pytest.raises(RuntimeError, match="selected an illegal phase action"):
        run(
            memory,
            reader,
            decision_authority=illegal_override,
        )

    assert observed_candidates == [(TrainingControlAction.FLEE,)]


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
    reader = FakeReader([state(battle_state=1, enemy_level=10, enemy_species_id=0x21)])

    monkeypatch.setattr(red_team_training, "training_attack_pp", lambda _member: 20)

    observed_timing: list[BattleRuntimeTiming] = []

    def fail_battle(*_args: object, **kwargs: object) -> None:
        timing = kwargs.get("timing")
        assert isinstance(timing, BattleRuntimeTiming)
        observed_timing.append(timing)
        raise BattleRuntimeError("semantic battle observation failed")

    monkeypatch.setattr(red_team_training, "run_adaptive_wild_battle", fail_battle)
    route_sleep_timing = BattleRuntimeTiming(max_sleep_reapplications=4)
    training_venue = TrainingVenue(
        band=GrindingArea(
            area_id="route_11",
            minimum_encounter_level=9,
            maximum_encounter_level=15,
            rare_maximum_encounter_level=17,
            measured_samples=81,
        ),
        map_id=TRAINING_MAP,
        walk_to_grass=lambda *_args: 1,
        heal_and_return=lambda *_args: None,
        is_in_center=lambda raw: raw.map_id == CENTER_MAP,
        move_slot=lambda _raw: 1,
        battle_timing=route_sleep_timing,
    )

    with pytest.raises(BattleRuntimeError, match="semantic battle observation failed"):
        run(memory, reader, venues=(training_venue,))

    assert observed_timing == [route_sleep_timing]


def test_live_direct_failure_uses_the_escort_on_the_next_encounter(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    memory = FakeMemory()
    memory.set_party(
        [(DIGLETT_SPECIES_ID, 22), (BLASTOISE_SPECIES_ID, 44)]
        + [(DUGTRIO_SPECIES_ID, 30) for _ in range(4)]
    )
    reader = FakeReader([state(battle_state=1, enemy_level=10, enemy_species_id=0x21)])
    monkeypatch.setattr(red_team_training, "training_attack_pp", lambda _member: 20)
    switches: list[str] = []

    def switch(*_args: object, **kwargs: object) -> bool:
        switches.append(str(kwargs["label"]))
        return True

    monkeypatch.setattr(red_team_training, "switch_active_battler", switch)
    battle_attempts = 0

    def battle(*_args: object, **_kwargs: object) -> None:
        nonlocal battle_attempts
        battle_attempts += 1
        if battle_attempts == 1:
            try:
                raise red_team_training._PauseForTeamTrainingRecovery
            except red_team_training._PauseForTeamTrainingRecovery as cause:
                raise BattleRuntimeError("live qualified moves unavailable") from cause

    monkeypatch.setattr(red_team_training, "run_adaptive_wild_battle", battle)
    flees: list[str] = []

    _report, completed, _healing = run(
        memory,
        reader,
        policy=BalancedTeamPolicy(
            minimum_level=60,
            maximum_level_spread=50,
            required_size=6,
            minimum_direct_level_advantage=5,
            max_battles=1,
            max_steps=100,
            max_healing_trips=1,
            max_faints=0,
        ),
        fixed_dose=FixedPartyTrainingDose(
            trainee_species_lineage=(DIGLETT_SPECIES_ID,),
            venue_identity=GrindingArea(
                area_id="test_area",
                minimum_encounter_level=1,
                maximum_encounter_level=10,
                rare_maximum_encounter_level=10,
                measured_samples=100,
            ).identity,
            completed_battles=1,
        ),
        flee_func=lambda *_args: flees.append("flee"),
    )

    assert completed == 1
    assert battle_attempts == 2
    assert flees == ["flee"]
    assert switches == [
        "Blastoise PP-exhaustion escape escort",
        "Blastoise escort",
    ]


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


def test_the_venue_bound_is_far_below_the_feature_saturation_horizon() -> None:
    """A true no-win venue mismatch must fail before the flee feature saturates."""

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


@pytest.mark.parametrize("frames", [1, 120, 180])
def test_training_pulse_advances_the_declared_wait_through_real_executor(frames):
    from test_executor import RecordingController

    from pokemon_red_completion.executor import ControllerTiming, FrameSafeExecutor

    controller = RecordingController()
    executor = FrameSafeExecutor(
        controller, ControllerTiming(press_frames=2, release_frames=3, wait_frames=1)
    )
    red_team_training.pulse(executor, MacroActionKind.CONFIRM, frames=frames)
    assert controller.frame_count == 5 + frames
    assert controller.events[-1] == ("tick", frames)


@pytest.mark.parametrize("attack_pp,status_pp,expected", [(0, 70, 0), (5, 70, 5), (5, 0, 5)])
def test_unlisted_trainee_attack_capacity_excludes_status_move_pp(attack_pp, status_pp, expected):
    from dataclasses import replace

    from pokemon_red_completion.party import MoveObservation

    memory = FakeMemory()
    memory.set_party([(163, 36)])
    member = PokemonRedPartyReader(memory).read().lead
    member = replace(
        member,
        moves=(
            MoveObservation(move_id=52, current_pp=attack_pp),
            MoveObservation(move_id=39, current_pp=min(status_pp, 30)),
            MoveObservation(move_id=45, current_pp=max(0, status_pp - 30)),
        ),
    )
    assert red_team_training.training_attack_pp(member) == expected


class DelayedFieldMenuMemory(FakeMemory):
    """Menu transitions become observable only after a real wait duration."""

    remaining = 0

    def apply(self, action):
        if action.kind is MacroActionKind.WAIT:
            self.remaining = max(0, self.remaining - action.repeat)
            return
        if self.remaining:
            return
        super().apply(action)
        if action.kind in {MacroActionKind.OPEN_MENU, MacroActionKind.CONFIRM}:
            self.remaining = 90


@pytest.mark.parametrize("first,second", [(0, 1), (0, 5), (3, 1), (5, 0)])
def test_party_swap_waits_for_delayed_menu_transitions_across_roster_slots(first, second):
    memory = DelayedFieldMenuMemory()
    memory.set_party([(species, 50) for species in FINAL_FORM_ROSTER])
    expected = list(FINAL_FORM_ROSTER)
    expected[first], expected[second] = expected[second], expected[first]
    red_team_training.swap_field_party_slots(
        FakeExecutor(memory),
        FakeReader([state()]),
        memory,
        first_index=first,
        second_index=second,
        label="delayed semantic swap",
        hideout_timing=None,
    )
    assert tuple(m.species for m in memory.party) == tuple(expected)
    assert memory.swaps == [(first, second)]


class FrozenTargetCursorMemory(FakeMemory):
    def _move(self, direction):
        if self.stage != "party_target":
            super()._move(direction)


def test_party_swap_does_not_confirm_a_destination_that_was_not_reached():
    memory = FrozenTargetCursorMemory()
    memory.set_party([(species, 50) for species in FINAL_FORM_ROSTER])
    with pytest.raises(RuntimeError, match="party destination slot"):
        red_team_training.swap_field_party_slots(
            FakeExecutor(memory),
            FakeReader([state()]),
            memory,
            first_index=0,
            second_index=5,
            label="stuck destination",
            hideout_timing=None,
        )
    assert not memory.swaps
    assert tuple(m.species for m in memory.party) == FINAL_FORM_ROSTER


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


class DelayedPartyConfirmMemory(FakeMemory):
    """Ignore the first attempt to open a selected member's submenu."""

    def __init__(self) -> None:
        super().__init__()
        self.ignored_party_confirms = 0

    def _confirm(self) -> None:
        if self.stage == "party" and self.ignored_party_confirms == 0:
            self.ignored_party_confirms += 1
            return
        super()._confirm()


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


def test_a_party_swap_closes_a_residual_member_submenu_before_opening_start() -> None:
    """Input readiness can remain true while a party submenu is still visible."""

    memory = FakeMemory()
    memory.set_party([(species, 60) for species in FINAL_FORM_ROSTER])
    memory.stage = "member"
    memory.cursor = 2

    red_team_training.swap_field_party_slots(
        FakeExecutor(memory),  # type: ignore[arg-type]
        FakeReader([state()]),  # type: ignore[arg-type]
        memory,  # type: ignore[arg-type]
        first_index=0,
        second_index=1,
        label="residual-menu swap",
        hideout_timing=None,
    )

    assert memory.party[0].species == DUGTRIO_SPECIES_ID
    assert memory.party[1].species == BLASTOISE_SPECIES_ID


def test_a_party_swap_observes_a_delayed_member_submenu_transition() -> None:
    """A dropped confirm must not turn a party slot into a supposed SWITCH row."""

    memory = DelayedPartyConfirmMemory()
    memory.set_party([(species, 60) for species in FINAL_FORM_ROSTER])

    red_team_training.swap_field_party_slots(
        FakeExecutor(memory),  # type: ignore[arg-type]
        FakeReader([state()]),  # type: ignore[arg-type]
        memory,  # type: ignore[arg-type]
        first_index=0,
        second_index=2,
        label="delayed-submenu swap",
        hideout_timing=None,
    )

    assert memory.ignored_party_confirms == 1
    assert memory.party[0].species == DUX_SPECIES_ID
    assert memory.party[2].species == BLASTOISE_SPECIES_ID
