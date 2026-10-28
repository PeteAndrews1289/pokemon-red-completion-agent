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


@pytest.mark.parametrize("resources", [False, True])
@pytest.mark.parametrize("escape", [False, True])
def test_helper_exclusions_apply_to_combat_escape_and_whole_venue(resources, escape):
    recipient = member(0x6C, 11, 1)
    evolving = member(150, 85, 2)
    stable = member(0x1C, 63, 3)
    enemy = 0x88 if escape else 0x21
    helper = training.collection_escape_escort if escape else training.collection_finisher
    party = PartyObservation((recipient, evolving, stable))
    kwargs = dict(enemy_level=15, enemy_species=enemy, resources=resources)
    assert helper(party, recipient.species_id, POLICY, **kwargs) == evolving
    assert helper(
        party, recipient.species_id, POLICY, **kwargs,
        excluded_helper_species=frozenset({150}),
    ) == stable
    lone = PartyObservation((recipient, evolving))
    assert helper(
        lone, recipient.species_id, POLICY, **kwargs,
        excluded_helper_species=frozenset({150}),
    ) is None
    assert not training.collection_encounter_coverage(
        lone, recipient.species_id, POLICY, [(15, enemy)], resources=resources,
        escape_species=frozenset({enemy}) if escape else frozenset(),
        excluded_helper_species=frozenset({150}),
    )


@pytest.mark.parametrize("invalid", [None, set(), [150], frozenset({True}),
                                     frozenset({0}), frozenset({256})])
@pytest.mark.parametrize("helper", [training.collection_finisher,
                                    training.collection_escape_escort])
def test_helper_exclusions_fail_closed_on_malformed_native_species(invalid, helper):
    with pytest.raises(ValueError, match="helper exclusions"):
        helper(PartyObservation((member(slot=1),)), 0x6C, POLICY, enemy_level=15,
               enemy_species=0x21, excluded_helper_species=invalid)


def test_actual_collection_loop_uses_stable_helper_instead_of_evolving_one(monkeypatch):
    from test_red_team_training import FakeExecutor

    experience_events = []
    monkeypatch.setattr(
        FakeExecutor, "record_diagnostic_event",
        lambda self, kind, payload: experience_events.append((kind, payload)),
        raising=False,
    )

    class Memory(FakeMemory):
        xp = 500

        def _field(self, observed, offset):
            if observed.species == 0x94:
                if offset == MOVES_OFFSET:
                    return 100
                if EXPERIENCE_OFFSET <= offset < EXPERIENCE_OFFSET + 3:
                    return (self.xp >> (8 * (EXPERIENCE_OFFSET + 2 - offset))) & 255
            return super()._field(observed, offset)

    memory = Memory()
    memory.set_party([(0x94, 12), (150, 35), (0x1C, 24)])
    reader = SimpleNamespace(raw=state())
    reader.read = lambda: reader.raw
    reader.read_input_readiness = lambda: SimpleNamespace(ready=True)
    switches, fights = [], []

    def seek(*args):
        reader.raw = state(battle_state=1, enemy_level=15, enemy_species_id=0x21)
        return 1

    def switch(*args, target_index, **kwargs):
        switches.append(target_index)
        reader.raw = replace(reader.raw, active_party_index=target_index)
        return True

    def fight(*args, **kwargs):
        fights.append(reader.raw.active_party_index)
        memory.xp += 123
        reader.raw = state()

    monkeypatch.setattr(training, "switch_active_battler", switch)
    monkeypatch.setattr(training, "run_adaptive_wild_battle", fight)
    venue = replace(_venue(GrindingArea("shared", 9, 15, measured_samples=40)),
                    walk_to_grass=seek,
                    heal_and_return=lambda *args: pytest.fail("safe helper needs no recovery"))
    with pytest.raises(training.EvolutionTrainingPaused) as stopped:
        run(memory, reader, policy=POLICY, venues=[venue],
            evolution_target=(0x94, 0x26), evolution_battle_quantum=1,
            collection_shared_experience=True,
            excluded_collection_helper_species=frozenset({150}),
            collection_encounters={venue.map_id: [(15, 0x21)]})
    assert switches == fights == [2]
    assert memory.xp == 623
    assert len(experience_events) == 1
    assert experience_events[0][0] == "wild_training_experience"
    assert experience_events[0][1]["experience_gained"] == 123
    assert experience_events[0][1]["experience_before"] == 500
    assert experience_events[0][1]["experience_after"] == 623
    assert stopped.value.battles == 1
    assert memory.swaps == []


@pytest.mark.parametrize("resources", [False, True])
def test_guarded_muk_coverage_is_escape_only_not_permission_to_attack(resources):
    recipient = member(0x6C, 11, 1)
    helper = member(0x1C, 80, 2)
    party = PartyObservation((recipient, helper))
    assert not training.training_type_matchup_acceptable(helper.species_id, 0x88)
    assert training.collection_finisher(
        party, 0x6C, POLICY, enemy_level=39, enemy_species=0x88, resources=resources
    ) is None
    assert not training.collection_encounter_coverage(
        party, 0x6C, POLICY, [(39, 0x88)], resources=resources
    )
    assert training.collection_encounter_coverage(
        party, 0x6C, POLICY, [(39, 0x88)], resources=resources,
        escape_species=frozenset({0x88}),
    )


@pytest.mark.parametrize("change", [
    {"hp": 0}, {"hp": 1}, {"status": StatusCondition.POISON}, {"level": 40},
    {"species_id": 0x54},  # Pikachu is still vulnerable to incoming Ground.
])
def test_guarded_escape_preserves_live_defensive_checks(change):
    helper = replace(member(0x1C, 80, 2), **change)
    enemy = 0x76 if change.get("species_id") else 0x88
    party = PartyObservation((member(0x6C, 11, 1), helper))
    assert training.collection_escape_escort(
        party, 0x6C, POLICY, enemy_level=39, enemy_species=enemy,
    ) is None


@pytest.mark.parametrize("flee_count", [1, 9, 31, 32])
def test_live_guarded_muk_is_fled_without_attack_or_spurious_nurse(monkeypatch, flee_count):
    memory = FakeMemory()
    memory.set_party([(0x6C, 11), (0x1C, 80)], hp=100, max_hp=100)
    current = [state(battle_state=1, enemy_level=39, enemy_species_id=0x88)]
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

    def seek(*args):
        if len(flees) < flee_count:
            current[0] = state(battle_state=1, enemy_level=39, enemy_species_id=0x88)
            return 1
        raise StopIteration("next encounter sought normally")

    monkeypatch.setattr(training, "switch_active_battler", switch)
    monkeypatch.setattr(training, "run_adaptive_wild_battle",
                        lambda *a, **kw: pytest.fail("excluded Muk must not be fought"))
    venue = replace(_venue(GrindingArea("mixed", 28, 34,
                                     rare_maximum_encounter_level=39, measured_samples=40)),
                    walk_to_grass=seek,
                    heal_and_return=lambda *a: pytest.fail("escape is not PP exhaustion"))
    expected_error = RuntimeError if flee_count == 32 else StopIteration
    message = "Training venue does not match" if flee_count == 32 else "next encounter sought"
    with pytest.raises(expected_error, match=message):
        run(memory, reader, policy=POLICY, venues=[venue], flee_func=flee,
            evolution_target=(0x6C, 0x2D), evolution_battle_quantum=1,
            collection_shared_experience=True, escort_enemy_species=frozenset({0x88}),
            collection_encounters={venue.map_id: [(39, 0x88)]})
    assert switches == [1] * flee_count
    assert flees == [True] * flee_count


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


@pytest.mark.parametrize(
    "change", [{"hp": 0}, {"hp": 1}, {"status": StatusCondition.POISON}, {"level": 10}]
)
def test_support_escape_cannot_bypass_health_status_or_level_guards(change):
    active = member(0x76, 55, 1, pp=0)
    assert training.collection_escape_escort(
        PartyObservation((replace(active, **change),)), None, POLICY,
        enemy_level=9, enemy_species=0x30,
    ) is None


def test_support_escape_can_reuse_safe_active_member_without_a_training_recipient():
    active = member(0x76, 55, 1, pp=0)
    assert training.collection_escape_escort(
        PartyObservation((active,)), None, POLICY,
        enemy_level=9, enemy_species=0x30,
    ) == active
    assert training.collection_escape_escort(
        PartyObservation((active,)), active.species_id, POLICY,
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
@pytest.mark.parametrize("gain", [-1, 0, 137])
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
    error = training.EvolutionTrainingPaused if gain > 0 else RuntimeError
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
    attempts = 8 if gain == 0 else 1
    assert switches == [1] * attempts
    assert fights == [1] * attempts
    assert heals == []
    assert PokemonRedPartyReader(memory).read().lead.experience == 500 + gain
    assert memory.swaps == []  # no legacy party-core reorder after a collection quantum
    if gain > 0:
        assert stopped.value.battles == 1
        assert stopped.value.healing_trips == 0
    elif gain < 0:
        assert "no verified recipient XP" in str(stopped.value)
    else:
        assert "8 flees and no win" in str(stopped.value)


@pytest.mark.parametrize("stronger_is_safe", [False, True])
def test_collection_evolution_prefers_stronger_band_only_after_coverage_check(
    monkeypatch, stronger_is_safe,
):
    """Exercise venue binding in the real loop, including its safety filter."""
    memory = FakeMemory()
    memory.set_party([(0x94, 12), (0x1C, 40)])
    reader = SimpleNamespace(read=lambda: state(),
                             read_input_readiness=lambda: SimpleNamespace(ready=True))
    visits = []

    class ReachedVenue(Exception):
        pass

    def walk(name):
        def execute(*args):
            visits.append(name)
            raise ReachedVenue
        return execute

    weak = replace(_venue(GrindingArea("weak", 9, 15, measured_samples=40)),
                   map_id=11, is_in_center=lambda raw: True,
                   walk_to_grass=walk("weak"), heal_and_return=walk("weak"))
    strong = replace(_venue(GrindingArea("strong", 15, 21, measured_samples=40)),
                     map_id=12, is_in_center=lambda raw: True,
                     walk_to_grass=walk("strong"), heal_and_return=walk("strong"))
    monkeypatch.setattr(training, "collection_encounter_coverage",
                        lambda party, species, policy, encounters, **kwargs:
                        encounters[0][0] == 15 or stronger_is_safe)
    with pytest.raises(ReachedVenue):
        run(memory, reader, policy=POLICY, venues=[weak, strong],
            evolution_target=(0x94, 0x26), evolution_battle_quantum=1,
            collection_shared_experience=True,
            collection_encounters={11: [(15, 0x21)], 12: [(21, 0x3B)]})
    assert visits == ["strong" if stronger_is_safe else "weak"]



@pytest.mark.parametrize("unsafe", [None, "input", "faint", "unknown_hp", "battle"])
def test_real_no_win_bound_is_a_partial_only_after_safe_settlement(monkeypatch, unsafe):
    """Run all 32 excluded exits; unsafe state still raises the original error."""
    from test_red_team_training import FakeExecutor

    memory = FakeMemory()
    memory.set_party([(0x6C, 11), (0x1C, 80)], hp=100, max_hp=100)
    raw = state(party_count=2, party_hp=(100, 100), battle_state=1,
                enemy_level=39, enemy_species_id=0x88)
    current, flees, events = [raw], [], []
    reader = SimpleNamespace(
        read=lambda: current[0],
        read_input_readiness=lambda: SimpleNamespace(
            ready=not (unsafe == "input" and len(flees) == 32)),
    )

    def flee(*args):
        flees.append(True)
        current[0] = replace(raw, battle_state=1 if unsafe == "battle" else 0,
                            party_hp=None if unsafe == "unknown_hp" else
                            (100, 0) if unsafe == "faint" else (100, 100))

    def seek(*args):
        current[0] = raw
        return 1

    monkeypatch.setattr(training, "switch_active_battler", lambda *a, **kw: True)
    monkeypatch.setattr(training, "run_adaptive_wild_battle",
                        lambda *a, **kw: pytest.fail("excluded encounter must not be fought"))
    monkeypatch.setattr(FakeExecutor, "record_diagnostic_event",
                        lambda self, kind, payload: events.append((kind, payload)), raising=False)
    venue = replace(_venue(GrindingArea("mixed", 28, 34,
                                      rare_maximum_encounter_level=39, measured_samples=40)),
                    walk_to_grass=seek,
                    heal_and_return=lambda *a: pytest.fail("excluded exit needs no nurse"))
    error = RuntimeError if unsafe else training.EvolutionVenueExhausted
    with pytest.raises(error) as stopped:
        run(memory, reader, policy=POLICY, venues=[venue], flee_func=flee,
            evolution_target=(0x6C, 0x2D), evolution_battle_quantum=1,
            collection_shared_experience=True, escort_enemy_species=frozenset({0x88}),
            collection_encounters={venue.map_id: [(39, 0x88)]})
    assert len(flees) == 32
    exhausted = [payload for kind, payload in events if kind == "wild_training_venue_exhausted"]
    if unsafe:
        assert type(stopped.value) is RuntimeError
        assert "Training venue does not match" in str(stopped.value)
        assert exhausted == []
    else:
        assert stopped.value.battles == stopped.value.healing_trips == 0
        assert len(exhausted) == 1
        assert exhausted[0]["consecutive_flees"] == exhausted[0]["mismatch_limit"] == 32
        assert exhausted[0]["observed_nonexcluded_encounter_levels"] == []
        assert exhausted[0]["no_verified_win"] is True


@pytest.mark.parametrize("change", [
    {"collection_shared_experience": False}, {"collection_encounters": None},
    {"evolution_target": None}, {"battles": 1},
])
def test_venue_pause_does_not_soften_other_training_failures(change):
    def forbidden():
        pytest.fail("legacy/non-evolution/winning caller must not inspect a new boundary")
    options = dict(collection_shared_experience=True, collection_encounters={165: [(39, 0x88)]},
                   evolution_target=(0x6C, 0x2D), battles=0, healing_trips=2)
    options.update(change)
    assert training._bounded_no_win_evolution_pause(SimpleNamespace(read=forbidden), **options) is None


@pytest.mark.parametrize("ready", [None, False, 1, "ready"])
def test_venue_pause_requires_exact_observed_input_readiness(ready):
    reader = SimpleNamespace(read=lambda: state(party_hp=(100, 100)),
                             read_input_readiness=lambda: SimpleNamespace(ready=ready))
    assert training._bounded_no_win_evolution_pause(
        reader, collection_shared_experience=True, collection_encounters={165: [(39, 0x88)]},
        evolution_target=(0x6C, 0x2D), battles=0, healing_trips=2) is None
