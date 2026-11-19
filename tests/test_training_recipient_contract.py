"""Counterexamples for guarded direct training and truthful recipient forecasts."""

from dataclasses import replace

import pytest
import test_native_evolution_venue_model as venue_fixtures
from test_native_evolution_venue_model import build, select

from pokemon_red_completion import red_team_training as training
from pokemon_red_completion.party import MoveObservation, PartyMemberObservation, StatusCondition
from pokemon_red_completion.red_party import BLASTOISE_SPECIES_ID
from pokemon_red_completion.team_training import BalancedTeamPolicy

menu_case = venue_fixtures.menu_case


def recipient(**changes):
    return replace(
        PartyMemberObservation(
            1, BLASTOISE_SPECIES_ID, 40, 100, 100, moves=(MoveObservation(33, 35),)
        ),
        **changes,
    )


@pytest.mark.parametrize(
    "fault", [None, "disabled_mode", "hp", "status", "level", "pp", "immune", "risky"]
)
def test_collection_direct_gate_uses_executable_moves_and_retains_safety(fault):
    member = recipient()
    level = 10
    enemy = 0x21
    allowed = True
    if fault == "disabled_mode":
        allowed = False
    if fault == "hp":
        member = recipient(hp=90)
    if fault == "status":
        member = recipient(status=StatusCondition.POISON)
    if fault == "level":
        member = recipient(level=12)
    if fault == "pp":
        member = recipient(moves=(MoveObservation(33, 16),))
    if fault == "immune":
        enemy = 0x19  # Gastly: Normal attacks cannot damage it.
    if fault == "risky":
        member = recipient(moves=(MoveObservation(120, 35),))
    assert training.collection_trainee_should_fight_directly(
        member,
        enemy_level=level,
        enemy_species=enemy,
        policy=BalancedTeamPolicy(
            retreat_hp_ratio=0.9, reserve_total_pp=16, minimum_direct_level_advantage=5
        ),
        allow_direct_evolution=allowed,
    ) is (fault is None)


def test_direct_forecast_follows_each_encounter_gate_and_exact_xp_floor(menu_case, monkeypatch):
    calls = []

    def gate(member, *, enemy_level, enemy_species, policy, allow_direct_evolution):
        calls.append((enemy_level, allow_direct_evolution))
        return allow_direct_evolution and enemy_level == 14

    monkeypatch.setattr(training, "collection_trainee_should_fight_directly", gate)
    legacy = build(menu_case)
    direct = build(menu_case, allow_direct_evolution=True)
    rows = [
        dict(zip(direct.candidate_set.feature_names, c.features, strict=True))
        for c in direct.candidate_set.candidates
    ]
    assert (
        rows[0]["venue.expected_recipient_xp_per_encounter"] == (101 * 14 // 7) * 205 / 256 / 100000
    )
    assert rows[1]["venue.expected_recipient_xp_per_encounter"] == ((101 // 2) * 30 // 7) / 100000
    assert legacy.semantic_snapshot_sha256 != direct.semantic_snapshot_sha256
    assert (14, True) in calls and (30, True) in calls


def test_retained_venue_choice_cannot_silently_change_training_mode(menu_case):
    from types import SimpleNamespace

    from pokemon_red_completion import red_goal_context as context

    state = {}
    select(menu_case, SimpleNamespace(predict=lambda _: 0), state, [], allow_direct_evolution=False)
    with pytest.raises(context.RedGoalContextError, match="another action"):
        select(
            menu_case, SimpleNamespace(predict=lambda _: 0), state, [], allow_direct_evolution=True
        )


def test_live_collection_keeps_safe_tackle_trainee_in_battle(monkeypatch):
    from types import SimpleNamespace

    from test_red_team_training import FakeMemory, _venue, run, state

    from pokemon_red_completion.red_party import EXPERIENCE_OFFSET, MOVES_OFFSET, PP_OFFSET
    from pokemon_red_completion.team_training import GrindingArea

    class Memory(FakeMemory):
        xp = 500

        def _field(self, observed, offset):
            if observed.species == BLASTOISE_SPECIES_ID:
                if offset == MOVES_OFFSET:
                    return 33
                if offset == PP_OFFSET:
                    return 35
                if EXPERIENCE_OFFSET <= offset < EXPERIENCE_OFFSET + 3:
                    return (self.xp >> (8 * (EXPERIENCE_OFFSET + 2 - offset))) & 255
            return super()._field(observed, offset)

    memory = Memory()
    memory.set_party([(BLASTOISE_SPECIES_ID, 40), (0xA6, 60)])
    reader = SimpleNamespace(raw=state())
    reader.read = lambda: reader.raw
    reader.read_input_readiness = lambda: SimpleNamespace(ready=True)
    switches = []
    fights = []

    def seek(*args):
        reader.raw = state(
            battle_state=1, enemy_level=10, enemy_species_id=0x21, active_party_index=0
        )
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
    venue = replace(
        _venue(GrindingArea("shared", 9, 15, measured_samples=40)),
        walk_to_grass=seek,
        heal_and_return=lambda *args: pytest.fail("healthy trainee/helper need no recovery"),
    )
    with pytest.raises(training.EvolutionTrainingPaused) as stopped:
        run(
            memory,
            reader,
            policy=BalancedTeamPolicy(minimum_direct_level_advantage=5, reserve_total_pp=16),
            venues=[venue],
            evolution_target=(BLASTOISE_SPECIES_ID, 0x59),
            evolution_battle_quantum=1,
            allow_direct_evolution=True,
            collection_shared_experience=True,
            collection_encounters={venue.map_id: [(10, 0x21)]},
        )
    assert switches == []
    assert fights == [0] and memory.xp == 623 and stopped.value.battles == 1


@pytest.mark.parametrize("transient", [False, True, "health"])
def test_collection_retries_recovered_health_and_transient_disable(monkeypatch, transient):
    from types import SimpleNamespace

    from test_red_team_training import FakeMemory, _venue, run, state

    from pokemon_red_completion.battle_runtime import BattleRuntimeError
    from pokemon_red_completion.red_party import EXPERIENCE_OFFSET, MOVES_OFFSET, PP_OFFSET
    from pokemon_red_completion.team_training import GrindingArea

    class Memory(FakeMemory):
        xp = 500

        def _field(self, observed, offset):
            if observed.species == BLASTOISE_SPECIES_ID:
                if offset == MOVES_OFFSET:
                    return 33
                if offset == PP_OFFSET:
                    return 35
                if EXPERIENCE_OFFSET <= offset < EXPERIENCE_OFFSET + 3:
                    return (self.xp >> (8 * (EXPERIENCE_OFFSET + 2 - offset))) & 255
            return super()._field(observed, offset)

    memory = Memory()
    memory.set_party([(BLASTOISE_SPECIES_ID, 40), (0xA6, 60)], hp=100, max_hp=100)
    reader = SimpleNamespace(raw=state())
    reader.read = lambda: reader.raw
    reader.read_input_readiness = lambda: SimpleNamespace(ready=True)
    fights = []
    heals = []

    def seek(*args):
        reader.raw = state(
            battle_state=1, enemy_level=10, enemy_species_id=0x21, active_party_index=0
        )
        return 1

    def switch(*args, target_index, **kwargs):
        reader.raw = replace(reader.raw, active_party_index=target_index)
        return True

    def fight(*args, **kwargs):
        fights.append(reader.raw.active_party_index)
        if len(fights) == 1:
            if transient is not True:
                memory.party[0].hp = 85
            cause = (
                training._PauseForTrainingDisable()
                if transient is True
                else training._PauseForTrainingHealth()
                if transient == "health"
                else training._PauseForTeamTrainingRecovery()
            )
            raise BattleRuntimeError("guard") from cause
        memory.xp += 123
        reader.raw = state()

    def flee(*args):
        reader.raw = state()

    def heal(*args):
        heals.append(True)
        for mon in memory.party:
            mon.hp = mon.max_hp

    monkeypatch.setattr(training, "switch_active_battler", switch)
    monkeypatch.setattr(training, "run_adaptive_wild_battle", fight)
    venue = replace(
        _venue(GrindingArea("shared", 9, 15, measured_samples=40)),
        walk_to_grass=seek,
        heal_and_return=heal,
    )
    with pytest.raises(training.EvolutionTrainingPaused) as stopped:
        run(
            memory,
            reader,
            policy=BalancedTeamPolicy(
                retreat_hp_ratio=0.9,
                reserve_total_pp=16,
                minimum_direct_level_advantage=5,
                max_healing_trips=3,
            ),
            venues=[venue],
            flee_func=flee,
            evolution_target=(BLASTOISE_SPECIES_ID, 0x59),
            evolution_battle_quantum=1,
            allow_direct_evolution=True,
            collection_shared_experience=True,
            collection_encounters={venue.map_id: [(10, 0x21)]},
        )
    assert fights == [0, 0 if transient else 1]
    assert (
        len(heals) == int(transient is not True) and memory.xp == 623 and stopped.value.battles == 1
    )


@pytest.mark.parametrize(
    "disabled,enemy,expected", [(1, 0x21, "transient"), (0, 0x21, "none"), (1, 0x19, "persistent")]
)
def test_native_move_selector_distinguishes_disable_from_no_effective_attack(
    disabled, enemy, expected
):
    from pokemon_red_completion.observation import RawGameState
    from pokemon_red_completion.red_native_boxed_evolution import native_training_move_slot

    raw = RawGameState(
        game_started=True,
        map_id=22,
        player_x=0,
        player_y=0,
        party_count=1,
        battle_state=1,
        active_party_species_id=BLASTOISE_SPECIES_ID,
        enemy_species_id=enemy,
        active_party_moves=(33, 0, 0, 0),
        active_party_pp=(35, 0, 0, 0),
        player_disabled_move_slot=disabled,
    )
    if expected == "none":
        assert native_training_move_slot(raw) == 1
    else:
        with pytest.raises(training._PauseForTeamTrainingRecovery) as paused:
            native_training_move_slot(raw)
        assert isinstance(paused.value, training._PauseForTrainingDisable) is (
            expected == "transient"
        )


@pytest.mark.parametrize(
    "hp,maximum,expected",
    [(90, 100, "health"), (91, 100, "ready"), (None, 100, "unknown"), (90, 0, "unknown")],
)
def test_native_health_retry_keeps_exact_retreat_threshold(hp, maximum, expected):
    from pokemon_red_completion.observation import RawGameState
    from pokemon_red_completion.red_native_boxed_evolution import native_training_move_guard

    raw = RawGameState(
        game_started=True,
        map_id=22,
        player_x=0,
        player_y=0,
        party_count=1,
        battle_state=1,
        active_party_species_id=BLASTOISE_SPECIES_ID,
        enemy_species_id=0x21,
        active_party_hp=hp,
        active_party_max_hp=maximum,
        active_party_moves=(33, 0, 0, 0),
        active_party_pp=(35, 0, 0, 0),
    )
    if expected == "ready":
        assert native_training_move_guard(raw) is None
    else:
        with pytest.raises(training._PauseForTeamTrainingRecovery) as paused:
            native_training_move_guard(raw)
        assert isinstance(paused.value, training._PauseForTrainingHealth) is (expected == "health")


@pytest.mark.parametrize("hp,pp,disabled,expected",[(40,10,None,4),(41,10,None,3),(40,0,None,3),(40,10,4,3),(None,10,None,3)])
def test_native_constant_finisher_uses_observed_hp_and_live_pp(hp,pp,disabled,expected):
    from pokemon_red_completion.observation import RawGameState
    from pokemon_red_completion.red_native_boxed_evolution import native_training_move_slot
    raw=RawGameState(game_started=True,map_id=197,player_x=0,player_y=0,party_count=1,
        battle_state=1,active_party_species_id=89,enemy_species_id=59,enemy_hp=hp,
        active_party_moves=(86,97,21,82),active_party_pp=(20,30,20,pp),player_disabled_move_slot=disabled)
    assert native_training_move_slot(raw)==expected


def test_dragon_rage_remains_counted_toward_unchanged_pp_reserve():
    member=recipient(species_id=89,moves=(MoveObservation(21,20),MoveObservation(82,10)))
    assert training.collection_damage_pp(member,59)==30
    assert training.collection_damage_pp(replace(member,moves=(MoveObservation(21,6),MoveObservation(82,10))),59)==16
