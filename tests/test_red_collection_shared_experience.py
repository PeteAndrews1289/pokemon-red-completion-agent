"""Exercise actual collection-mode control, not merely its advertised menu."""

from dataclasses import replace
from types import SimpleNamespace

import pytest
from test_red_team_training import FakeMemory, _venue, run, state

from pokemon_red_completion import red_team_training as training
from pokemon_red_completion.party import (
    MoveObservation,
    PartyMemberObservation,
    PartyObservation,
    StatusCondition,
)
from pokemon_red_completion.red_party import (
    EXPERIENCE_OFFSET,
    MOVES_OFFSET,
    PP_OFFSET,
    PokemonRedPartyReader,
)
from pokemon_red_completion.team_training import BalancedTeamPolicy, GrindingArea


def member(species=0x1C, level=63, slot=2, move=33, pp=20):
    return PartyMemberObservation(
        slot, species, level, 100, 100, moves=(MoveObservation(move, pp),)
    )


POLICY = BalancedTeamPolicy(minimum_direct_level_advantage=5, reserve_total_pp=5)


@pytest.mark.parametrize("initial_recovery", [False, True])
@pytest.mark.parametrize("helper_always_pauses", [False, True])
def test_collection_keeps_direct_combat_failure_evidence_after_healing(
    monkeypatch, initial_recovery, helper_always_pauses
):
    """Real loop: heal, direct damage/escape, heal, then switch for actual XP.

    Recovery restores resources, not a failed matchup forecast. New encounter
    damage may require another heal, but ineffective healing and total budgets
    remain bounded. Both initial states distinguish sentinel and suppression.
    """
    from pokemon_red_completion.battle_runtime import BattleRuntimeError

    class Memory(FakeMemory):
        xp = 1000

        def _field(self, observed, offset):
            if observed.species == 0x6C and EXPERIENCE_OFFSET <= offset < EXPERIENCE_OFFSET + 3:
                return (self.xp >> (8 * (EXPERIENCE_OFFSET + 2 - offset))) & 255
            return super()._field(observed, offset)

    memory = Memory()
    memory.set_party([(0x6C, 19), (0x1C, 65)], hp=100, max_hp=100)
    if initial_recovery:
        memory.party[0].hp = 85
    reader = SimpleNamespace(raw=state(active_party_index=0))
    reader.read = lambda: reader.raw
    reader.read_input_readiness = lambda: SimpleNamespace(ready=True)
    fights, heals, flees = [], [], []

    def seek(*args):
        reader.raw = state(battle_state=1, enemy_level=12, enemy_species_id=0x6C,
                           active_party_index=0)
        return 1

    def switch(*args, target_index, **kwargs):
        reader.raw = replace(reader.raw, active_party_index=target_index)
        return True

    def fight(*args, **kwargs):
        active = reader.raw.active_party_index
        fights.append(active)
        assert active == (0 if len(fights) == 1 else 1)
        if len(fights) == 1 or helper_always_pauses:
            memory.party[active].hp = 85
            raise BattleRuntimeError("live guard") from training._PauseForTeamTrainingRecovery()
        memory.xp += 123
        reader.raw = state(active_party_index=0)

    def heal(*args):
        heals.append(True)
        for mon in memory.party:
            mon.hp = mon.max_hp

    def flee(*args):
        flees.append(True)
        reader.raw = state(active_party_index=0)

    monkeypatch.setattr(training, "switch_active_battler", switch)
    monkeypatch.setattr(training, "run_adaptive_wild_battle", fight)
    venue = replace(_venue(GrindingArea("mixed", 9, 14, measured_samples=40)),
                    heal_and_return=heal, walk_to_grass=seek)
    error = RuntimeError if helper_always_pauses else training.EvolutionTrainingPaused
    with pytest.raises(error) as stopped:
        run(memory, reader,
            policy=replace(POLICY, retreat_hp_ratio=0.9, max_healing_trips=3),
            venues=[venue], flee_func=flee, allow_direct_evolution=True,
            evolution_target=(0x6C, 0x2D), evolution_battle_quantum=1,
            collection_shared_experience=True,
            collection_encounters={venue.map_id: [(12, 0x6C)]})
    if helper_always_pauses:
        assert "required-recovery budget" in str(stopped.value)
        assert len(heals) == 3
        assert memory.xp == 1000
    else:
        assert fights == [0, 1]
        assert len(heals) == 1 + int(initial_recovery)
        assert len(flees) == 1
        assert memory.xp == 1123
        assert stopped.value.battles == 1


@pytest.mark.parametrize("recipient_species,move", [(0x94, 100), (0x71, 106), (0x7C, 106)])
@pytest.mark.parametrize(
    "finisher_species,level,slot", [(0x1C, 63, 2), (0x40, 55, 3), (0x84, 75, 4)]
)
def test_non_attacking_recipient_does_not_need_damage_or_specific_finisher(
    recipient_species, move, finisher_species, level, slot
):
    recipient = member(recipient_species, 4, 1, move, 0)
    helpers = [member(0xA5, 2, index) for index in range(2, slot)]
    helper = member(finisher_species, level, slot)
    party = PartyObservation((recipient, *helpers, helper))
    assert not training.collection_recipient_needs_recovery(recipient, POLICY)
    assert training.member_is_unsafe_for_team_training(recipient, POLICY)
    assert (
        training.collection_finisher(
            party, recipient_species, POLICY, enemy_level=15, enemy_species=0x21
        )
        == helper
    )


@pytest.mark.parametrize(
    "change",
    [
        {"hp": 0},
        {"hp": 1},
        {"status": StatusCondition.POISON},
        {"level": 19},
        {"moves": (MoveObservation(33, 5),)},
        {"moves": (MoveObservation(100, 40),)},
        {"moves": (MoveObservation(120, 40),)},
        {"moves": (MoveObservation(91, 40),)},
    ],
)
def test_unsafe_or_non_attacking_finisher_is_rejected(change):
    recipient = member(0x94, 12, 1, 100)
    helper = replace(member(), **change)
    assert (
        training.collection_finisher(
            PartyObservation((recipient, helper)),
            recipient.species_id,
            POLICY,
            enemy_level=15,
            enemy_species=0x21,
        )
        is None
    )


def test_structural_readiness_can_restore_pp_but_never_create_an_attack():
    recipient = member(0x94, 12, 1, 100)
    exhausted = replace(member(), hp=1, moves=(MoveObservation(33, 0),))
    party = PartyObservation((recipient, exhausted))
    assert training.collection_finisher(party, 0x94, POLICY, enemy_level=15) is None
    assert (
        training.collection_finisher(party, 0x94, POLICY, enemy_level=15, resources=False)
        == exhausted
    )
    status_only = replace(exhausted, moves=(MoveObservation(106, 0),))
    assert (
        training.collection_finisher(
            PartyObservation((recipient, status_only)),
            0x94,
            POLICY,
            enemy_level=15,
            resources=False,
        )
        is None
    )


def test_encounter_coverage_rejects_level_only_primeape_and_exhausted_backup():
    recipient = member(0x6C, 11, 1)  # Ekans
    fighter = member(0x75, 28, 2)  # Primeape: Psychic-weak despite spare Tackle PP
    backup = member(0x76, 55, 3, pp=0)
    party = PartyObservation((recipient, fighter, backup))
    assert training.collection_finisher(party, 0x6C, POLICY, enemy_level=9) == fighter
    assert not training.collection_encounter_coverage(party, 0x6C, POLICY, [(9, 0x30)])
    assert training.collection_encounter_coverage(
        party, 0x6C, POLICY, [(9, 0x30)], resources=False
    )
    assert not training.collection_encounter_coverage(party, 0x6C, POLICY, [])


def test_each_opponent_may_have_a_different_qualified_helper():
    # Water is unsafe against Electric; Ground is unsafe against Water.
    recipient = member(0x6C, 11, 1)
    water = member(0x1C, 55, 2)
    ground = member(0x76, 55, 3)
    encounters = [(10, 0x54), (10, 0xB1)]  # Pikachu and Squirtle internal IDs
    party = PartyObservation((recipient, water, ground))
    assert training.collection_encounter_coverage(party, 0x6C, POLICY, encounters)
    for helper in (water, ground):
        assert not training.collection_encounter_coverage(
            PartyObservation((recipient, replace(helper, slot=2))), 0x6C, POLICY, encounters
        )


@pytest.mark.parametrize(
    "change", [{"hp": 0}, {"hp": 1}, {"status": StatusCondition.POISON}, {"level": 10}]
)
def test_pp_independent_escape_does_not_waive_defensive_guards(change):
    recipient = member(0x6C, 11, 1)
    exhausted = member(0x76, 55, 2, pp=0)
    assert training.collection_escape_escort(
        PartyObservation((recipient, exhausted)), 0x6C, POLICY,
        enemy_level=9, enemy_species=0x30,
    ) == exhausted
    assert training.collection_escape_escort(
        PartyObservation((recipient, replace(exhausted, **change))), 0x6C, POLICY,
        enemy_level=9, enemy_species=0x30,
    ) is None


def test_real_loop_heals_instead_of_accepting_species_blind_helper():
    class Memory(FakeMemory):
        def _field(self, observed, offset):
            if observed.species == 0x76 and offset == PP_OFFSET:
                return 0
            return super()._field(observed, offset)

    memory = Memory()
    memory.set_party([(0x6C, 11), (0x75, 28), (0x76, 55)])
    heals = []
    venue = replace(
        _venue(GrindingArea("mixed", 9, 15, measured_samples=40)),
        heal_and_return=lambda *args: heals.append(True),
        walk_to_grass=lambda *args: pytest.fail("Drowzee coverage failed: must not seek"),
    )
    reader = SimpleNamespace(
        read=lambda: state(), read_input_readiness=lambda: SimpleNamespace(ready=True)
    )
    with pytest.raises(RuntimeError, match="recovery repeated"):
        run(memory, reader, policy=POLICY, venues=[venue],
            evolution_target=(0x6C, 0x2D), evolution_battle_quantum=1,
            collection_shared_experience=True, collection_encounters={venue.map_id: [(9, 0x30)]})
    assert heals == [True]
    assert not memory.swaps


def test_no_finisher_battle_uses_escape_not_structural_combat(monkeypatch):
    class Memory(FakeMemory):
        def _field(self, observed, offset):
            if observed.species == 0x76 and offset == PP_OFFSET:
                return 0
            return super()._field(observed, offset)

    memory = Memory()
    memory.set_party([(0x6C, 11), (0x75, 28), (0x76, 55)])
    current = [state(battle_state=1, enemy_level=9, enemy_species_id=0x30)]
    reader = SimpleNamespace(
        read=lambda: current[0], read_input_readiness=lambda: SimpleNamespace(ready=True)
    )
    switches, flees = [], []

    def switch(*args, target_index, **kwargs):
        switches.append(target_index)
        return True

    def flee(*args):
        flees.append(True)
        current[0] = state()

    def recovered(*args):
        raise StopIteration("recovery reached without another battle")

    monkeypatch.setattr(training, "switch_active_battler", switch)
    monkeypatch.setattr(
        training, "run_adaptive_wild_battle", lambda *a, **kw: pytest.fail("must not attack")
    )
    venue = replace(_venue(GrindingArea("mixed", 9, 15, measured_samples=40)),
                    heal_and_return=recovered)
    with pytest.raises(StopIteration, match="recovery reached"):
        run(memory, reader, policy=POLICY, venues=[venue], flee_func=flee,
            evolution_target=(0x6C, 0x2D), evolution_battle_quantum=1,
            collection_shared_experience=True, collection_encounters={venue.map_id: [(9, 0x30)]})
    assert switches == [2]
    assert flees == [True]


@pytest.mark.parametrize("failure", ["no_escort", "faint_on_switch", "no_exit"])
def test_escape_abstains_or_stops_without_issuing_more_inputs(monkeypatch, failure):
    from pokemon_red_completion.actions import MacroAction, MacroActionKind

    memory = FakeMemory()
    memory.set_party([(0x6C, 11), (0x76, 55)])
    if failure == "no_escort":
        memory.party[1].level = 5
    calls = []

    def execute(action):
        calls.append(action)
        if failure == "faint_on_switch":
            memory.party[0].hp = 0

    def switch(actions, *args, **kwargs):
        actions.execute(MacroAction(MacroActionKind.CONFIRM))
        actions.execute(MacroAction(MacroActionKind.WAIT, repeat=12))
        return True

    monkeypatch.setattr(training, "switch_active_battler", switch)
    reader = SimpleNamespace(
        read=lambda: state(battle_state=1, enemy_level=9, enemy_species_id=0x30),
        read_input_readiness=lambda: SimpleNamespace(ready=True),
    )
    with pytest.raises(RuntimeError):
        training.escape_collection_battle(
            SimpleNamespace(execute=execute), reader, memory,
            recipient_species_id=0x6C, policy=POLICY,
            flee_func=lambda *args: None, flee_timing=object(),
        )
    assert len(calls) == {"no_escort": 0, "faint_on_switch": 1, "no_exit": 2}[failure]


@pytest.mark.parametrize("enemy_level,enemy_species", [(None, 0x21), (100, 0x21), (15, 0x19)])
def test_finisher_checks_actual_enemy_including_damage_immunity(enemy_level, enemy_species):
    # Tackle cannot hurt Gastly (internal25); unknown/excessive levels abstain.
    party = PartyObservation((member(0x94, 12, 1, 100), member()))
    assert (
        training.collection_finisher(
            party, 0x94, POLICY, enemy_level=enemy_level, enemy_species=enemy_species
        )
        is None
    )


@pytest.mark.parametrize(
    "options",
    [
        {"collection_shared_experience": "yes"},
        {"collection_shared_experience": True},
        {"collection_shared_experience": True, "evolution_target": (0x94, 0x26)},
    ],
)
def test_shared_experience_cannot_leak_into_unbounded_or_legacy_modes(options):
    with pytest.raises(ValueError):
        run(FakeMemory(), SimpleNamespace(), **options)


def test_collection_stops_after_one_ineffective_recovery():
    memory = FakeMemory()
    memory.set_party([(0x94, 12), (0x40, 55)])
    memory.party[1].hp = 1
    heals = []
    venue = replace(
        _venue(GrindingArea("recovery", 9, 15, measured_samples=40)),
        heal_and_return=lambda *args: heals.append(True),
        walk_to_grass=lambda *args: pytest.fail("unsafe helper must not seek an encounter"),
    )
    reader = SimpleNamespace(
        read=lambda: state(), read_input_readiness=lambda: SimpleNamespace(ready=True)
    )
    with pytest.raises(RuntimeError, match="recovery repeated"):
        run(
            memory,
            reader,
            policy=POLICY,
            venues=[venue],
            evolution_target=(0x94, 0x26),
            evolution_battle_quantum=1,
            collection_shared_experience=True,
        )
    assert heals == [True]
    assert memory.swaps == []


@pytest.mark.parametrize("recipient_species,move,target", [(0x94, 100, 0x26), (0x71, 106, 0x7D)])
@pytest.mark.parametrize("helper_species,level", [(0x1C, 63), (0x40, 55)])
@pytest.mark.parametrize("gain", [0, 137])
def test_actual_loop_switches_finishes_and_requires_recipient_xp(
    monkeypatch, recipient_species, move, target, helper_species, level, gain
):
    class Memory(FakeMemory):
        xp = 500

        def _field(self, observed, offset):
            if observed.species == recipient_species:
                if offset == MOVES_OFFSET:
                    return move
                if EXPERIENCE_OFFSET <= offset < EXPERIENCE_OFFSET + 3:
                    return (self.xp >> (8 * (EXPERIENCE_OFFSET + 2 - offset))) & 255
            return super()._field(observed, offset)

    memory = Memory()
    memory.set_party([(recipient_species, 12), (helper_species, level)])

    class Reader:
        raw = state()

        def read(self):
            return self.raw

        def read_input_readiness(self):
            return SimpleNamespace(ready=True)

    reader = Reader()
    switches, fights, heals = [], [], []

    def seek(*args):
        reader.raw = state(battle_state=1, enemy_level=15, enemy_species_id=0x21)
        return 1

    def switch(*args, target_index, **kwargs):
        switches.append(target_index)
        reader.raw = replace(reader.raw, active_party_index=target_index)
        return True

    def fight(*args, **kwargs):
        fights.append(reader.raw.active_party_index)
        assert reader.raw.active_party_index == 1
        memory.xp += gain
        reader.raw = state()

    monkeypatch.setattr(training, "switch_active_battler", switch)
    monkeypatch.setattr(training, "run_adaptive_wild_battle", fight)
    venue = replace(
        _venue(GrindingArea("shared", 9, 15, rare_maximum_encounter_level=17, measured_samples=40)),
        walk_to_grass=seek,
        heal_and_return=lambda *args: heals.append(True),
    )
    error = training.EvolutionTrainingPaused if gain else RuntimeError
    with pytest.raises(error) as stopped:
        run(
            memory,
            reader,
            policy=POLICY,
            venues=[venue],
            evolution_target=(recipient_species, target),
            evolution_battle_quantum=1,
            collection_shared_experience=True,
        )
    assert switches == [1]
    assert fights == [1]
    assert heals == []
    assert PokemonRedPartyReader(memory).read().lead.experience == 500 + gain
    assert memory.swaps == []  # no legacy party-core reorder after a collection quantum
    if gain:
        assert stopped.value.battles == 1
        assert stopped.value.healing_trips == 0
    else:
        assert "no verified recipient XP" in str(stopped.value)
