from dataclasses import replace
from types import SimpleNamespace

import pytest

import pokemon_red_completion.red_trainer_healing as healing
import pokemon_red_completion.red_trainer_survival as survival
from pokemon_red_completion.battle_runtime import (
    BattleIntent,
    BattleRuntimeError,
    BattleRuntimeTiming,
)
from pokemon_red_completion.observation import (
    BattleMenuPhase,
    BattleMenuState,
    RawGameState,
    TrainerDamageObservation,
)
from pokemon_red_completion.red_trainer_damage import incoming_damage_bounds
from pokemon_red_completion.red_trainer_healing import (
    bag_after_full_restores,
    trainer_bag_within_budget,
    use_active_full_restore,
)
from pokemon_red_completion.red_trainer_survival import RedTrainerSurvivalController


def state(active=1, hp=(76, 12)):
    moves, pp = ((57, 58, 66, 70), (89, 45, 91, 28)), ((10, 10, 20, 15), (10, 40, 10, 15))
    return RawGameState(
        game_started=True,
        map_id=245,
        player_x=5,
        player_y=3,
        battle_state=2,
        party_count=2,
        party_species_ids=(28, 118),
        party_levels=(66, 55),
        party_hp=hp,
        party_max_hp=(213, 118),
        party_status=(0, 0),
        party_moves=moves,
        party_pp=pp,
        active_party_index=active,
        active_party_species_id=(28, 118)[active],
        active_party_hp=hp[active],
        active_party_max_hp=(213, 118)[active],
        active_party_moves=moves[active],
        active_party_pp=pp[active],
        enemy_species_id=72,
        enemy_level=56,
        enemy_hp=147,
        bag_items=((16, 4), (53, 3)),
    )


def controller(monkeypatch, raw=None, previous=(2, 4), budget=2):
    reader = SimpleNamespace(raw=raw or state())
    reader.read = lambda: reader.raw
    reader.read_trainer_damage_observation = lambda raw: raw
    monkeypatch.setattr(survival, "incoming_damage_bounds", lambda _: (53, 257))
    return RedTrainerSurvivalController(reader, object(), previous, budget)


def test_threatened_active_cannot_waste_heal_and_low_fraction_reserve_can_survive(monkeypatch):
    subject = controller(monkeypatch)
    choice = subject.decide(subject.reader.raw)
    assert (choice.kind, choice.party_index, choice.incoming_bound) == ("switch", 0, 53)


@pytest.mark.parametrize("hp,expected", [(54, "attack"), (53, "heal"), (1, "heal")])
def test_strict_damage_boundary_replaces_flat_half_hp(monkeypatch, hp, expected):
    subject = controller(monkeypatch, state(active=0, hp=(hp, 12)))
    assert subject.decide(subject.reader.raw).kind == expected


def test_used_item_and_switch_budgets_do_not_reset(monkeypatch):
    subject = controller(monkeypatch, state(active=0, hp=(53, 12)))
    subject.heals_claimed = 2
    with pytest.raises(BattleRuntimeError, match="remaining recovery budget"):
        subject.decide(subject.reader.raw)
    subject = controller(monkeypatch, previous=(2, 4, 1, 2, 1, 2))
    with pytest.raises(BattleRuntimeError, match="remaining recovery budget"):
        subject.decide(subject.reader.raw)


@pytest.mark.parametrize('move,field,hp', [(34, 'enemy_attack', 100), (8, 'enemy_special', 50)])
def test_each_decision_rereads_live_boosted_stats_even_when_raw_is_unchanged(move, field, hp):
    raw = state(active=0, hp=(hp, 12))
    initial = TrainerDamageObservation(
        raw, (move, 97, 0, 0), ('normal',), 100, 100, 100, 100,
        ((150, 150, 150, 150), (50, 50, 50, 50)), (('water',), ('ground',)),
    )
    live = SimpleNamespace(observation=initial, reads=0)

    def observe(observed_raw):
        assert observed_raw is raw
        live.reads += 1
        return live.observation

    reader = SimpleNamespace(read_trainer_damage_observation=observe)
    subject = RedTrainerSurvivalController(reader, object(), (), 0)
    assert subject.decide(raw).kind == 'attack'
    initial_bound = incoming_damage_bounds(initial)[0]
    live.observation = replace(initial, **{field: 600})
    assert incoming_damage_bounds(live.observation)[0] > initial_bound
    with pytest.raises(BattleRuntimeError, match='remaining recovery budget'):
        subject.decide(raw)
    assert live.reads == 2


def test_zero_item_mode_never_heals_even_after_a_safe_switch(monkeypatch):
    subject = controller(monkeypatch, budget=0)
    inputs = simulate(monkeypatch, subject)
    # Switch survives, but leaves the member below the next conservative bound.
    # Four Full Restores are present and would otherwise enable healing.
    with pytest.raises(BattleRuntimeError, match='remaining recovery budget'):
        run(subject)
    assert inputs == ['switch'] and subject.switches == [1]
    assert subject.heals_claimed == 0
    assert subject.reader.raw.bag_items == ((16, 4), (53, 3))
    assert [row['kind'] for row in subject.reports] == ['switch']


@pytest.mark.parametrize("change", [{"hp": (0, 12)}, {"hp": (53, 12)}])
def test_no_faint_or_non_surviving_switch_authorized(monkeypatch, change):
    subject = controller(monkeypatch, state(**change))
    with pytest.raises(BattleRuntimeError):
        subject.decide(subject.reader.raw)


def run(subject, policy=lambda _: 1):
    return subject.run(
        subject.reader,
        object(),
        policy,
        expected_map=245,
        intent=BattleIntent("trainer_recovery", "budgeted-survival"),
        timing=BattleRuntimeTiming(),
        label="test recovery",
        consume_battle_start_schedule=False,
        move_decision_guard=lambda _: None,
    )


def simulate(monkeypatch, subject):
    inputs = []

    def battle(reader, _actions, policy, **kwargs):
        kwargs["move_decision_guard"](reader.read())
        try:
            policy(reader.read())
        except survival._RecoveryRequest as request:
            raise BattleRuntimeError("policy boundary") from request
        inputs.append("attack")
        return replace(reader.read(), battle_state=0)

    def switch(_actions, reader, _emulator, index, **_):
        inputs.append("switch")
        assert index == 0
        reader.raw = state(active=0, hp=(46, 12))

    def heal(_actions, reader, _emulator, **kwargs):
        inputs.append("heal")
        assert kwargs["incoming_bound"] == 53
        reader.raw = replace(state(active=0, hp=(170, 12)), bag_items=((16, 3), (53, 3)))
        return reader.raw

    monkeypatch.setattr(survival, "run_adaptive_trainer_battle", battle)
    monkeypatch.setattr(survival, "switch_active_battler", switch)
    monkeypatch.setattr(survival, "use_active_full_restore", heal)
    return inputs


def test_observed_switch_then_one_heal_resumes_without_restarting_battle(monkeypatch):
    subject = controller(monkeypatch)
    inputs = simulate(monkeypatch, subject)
    assert run(subject).battle_state == 0
    assert inputs == ["switch", "heal", "attack"]
    assert subject.previous_switches == (2, 4) and subject.switches == [1]
    assert subject.heals_claimed == 1
    assert [row["kind"] for row in subject.reports] == ["switch", "heal", "attack"]
    with pytest.raises(BattleRuntimeError, match="consumed"):
        run(subject)
    assert inputs == ["switch", "heal", "attack"]


def test_exit_guard_survives_switch_and_heal_controller_restarts(monkeypatch):
    subject = controller(monkeypatch)
    inputs = simulate(monkeypatch, subject)
    adaptive = survival.run_adaptive_trainer_battle
    exits = []
    def battle(*args, **kwargs):
        result = adaptive(*args, **kwargs)
        kwargs['battle_exit_guard'](result)
        return result
    monkeypatch.setattr(survival, 'run_adaptive_trainer_battle', battle)
    result = subject.run(
        subject.reader, object(), lambda _: 1, expected_map=245,
        intent=BattleIntent('champion', 'budgeted-survival'), timing=BattleRuntimeTiming(),
        label='test', consume_battle_start_schedule=False,
        move_decision_guard=lambda _: None, battle_exit_guard=exits.append,
    )
    assert exits == [result] and result.battle_state == 0
    assert inputs == ['switch', 'heal', 'attack']
    assert subject.moves_selected == 1 and subject.heals_claimed == 1
    assert subject.maximum_switches == 6 and subject.switches == [1]


def test_early_recovery_keeps_attacking_then_stops_on_new_unaffordable_threat(monkeypatch):
    subject = controller(monkeypatch, state(active=0, hp=(130, 12)), previous=(), budget=1)
    monkeypatch.setattr(survival, 'incoming_damage_bounds',
                        lambda raw: (80, 257) if raw.enemy_species_id == 72 else (220, 300))
    inputs = []
    ordinary_blocked = []
    def battle(reader, _actions, policy, **kwargs):
        while True:
            raw = reader.read()
            kwargs['move_decision_guard'](raw)
            try:
                policy(raw)
            except survival._RecoveryRequest as request:
                ordinary_blocked.append(survival.trainer_matchup_candidates(
                    survival.party_observation_from_raw(raw),
                    opponent_species=raw.enemy_species_id, opponent_level=raw.enemy_level,
                ))
                raise BattleRuntimeError('decision boundary') from request
            inputs.append('attack')
            if inputs.count('attack') == 1:
                reader.raw = replace(raw, party_hp=(50, 12), active_party_hp=50)
            else:
                reader.raw = replace(raw, enemy_species_id=171, enemy_level=60)
    def heal(_actions, reader, _emulator, **kwargs):
        assert kwargs['incoming_bound'] == 80 and reader.raw.party_hp == (50, 12)
        inputs.append('heal')
        reader.raw = replace(reader.raw, party_hp=(133, 12), active_party_hp=133,
                             bag_items=((16, 3), (53, 3)))
        return reader.raw
    monkeypatch.setattr(survival, 'run_adaptive_trainer_battle', battle)
    monkeypatch.setattr(survival, 'use_active_full_restore', heal)
    with pytest.raises(survival.NoTrainerSurvivalAction):
        run(subject)
    assert ordinary_blocked == [()]  # flat-HP actor has no offensive healthy candidate
    assert inputs == ['attack', 'heal', 'attack']
    assert subject.moves_selected == 2 and subject.heals_claimed == 1
    assert subject.reader.raw.party_hp == (133, 12)
    assert subject.reader.raw.enemy_species_id == 171


def test_failed_item_attempt_retains_claim_no_retry(monkeypatch):
    subject = controller(monkeypatch, state(active=0, hp=(46, 12)))
    inputs = simulate(monkeypatch, subject)

    def failed(*_args, **_kwargs):
        inputs.append("failed_heal")
        raise RuntimeError("item transition failed")

    monkeypatch.setattr(survival, "use_active_full_restore", failed)
    with pytest.raises(RuntimeError, match="transition"):
        run(subject)
    assert inputs == ["failed_heal"] and subject.heals_claimed == 1


def test_missing_durable_decision_receipt_blocks_controller_input(monkeypatch):
    subject = controller(monkeypatch)
    inputs = simulate(monkeypatch, subject)

    def failed(_):
        raise OSError("receipt unavailable")

    subject.decision_sink = failed
    with pytest.raises(OSError):
        run(subject)
    assert not inputs and not subject.switches


def test_recoil_is_masked_and_cannot_be_selected(monkeypatch):
    subject = controller(monkeypatch, state(active=0, hp=(170, 12)))
    simulate(monkeypatch, subject)

    def forbidden(raw):
        assert raw.battler_pp == (10, 10, 0, 15)
        return 3

    with pytest.raises(BattleRuntimeError, match="unsupported attack"):
        run(subject, forbidden)


def test_shadow_learner_never_receives_authority(monkeypatch):
    subject = controller(monkeypatch)
    inputs = simulate(monkeypatch, subject)
    monkeypatch.setattr(survival, "battle_policy_override_active", lambda: True)
    with pytest.raises(BattleRuntimeError, match="authority"):
        run(subject)
    assert not inputs


def test_item_budget_is_exact_and_keeps_all_other_stock():
    initial = ((4, 7), (16, 2), (53, 3))
    assert bag_after_full_restores(initial, 1) == ((4, 7), (16, 1), (53, 3))
    assert bag_after_full_restores(initial, 2) == ((4, 7), (53, 3))
    before = replace(state(), bag_items=initial)
    assert trainer_bag_within_budget(before, replace(before, bag_items=((4, 7), (53, 3))), 2)
    assert not trainer_bag_within_budget(before, replace(before, bag_items=((4, 6), (53, 3))), 2)
    assert not trainer_bag_within_budget(before, replace(before, bag_items=((4, 7), (53, 3))), 1)
    with pytest.raises(ValueError):
        bag_after_full_restores(initial, 3)


def item_simulation(monkeypatch, change=None, settled=True):
    before = state(active=1, hp=(76, 20))
    after = replace(state(active=1, hp=(76, 90)), bag_items=((16, 3), (53, 3)))
    if change:
        after = replace(after, **change)
    world = SimpleNamespace(raw=before, pulses=0)
    world.read = lambda: world.raw
    world.read_battle_menu_state = lambda _: BattleMenuState(
        BattleMenuPhase.MAIN if settled or world.pulses < 3 else BattleMenuPhase.UNKNOWN
    )
    targets = []
    monkeypatch.setattr(healing, "_select_battle_main_command", lambda *_: targets.append("item"))
    monkeypatch.setattr(healing, "_select_bag_item", lambda *_: targets.append("Full Restore"))
    monkeypatch.setattr(healing, "_select_cursor", lambda _a, _e, slot, _w: targets.append(slot))

    def pulse(*_a, **_k):
        world.pulses += 1
        if world.pulses == 3:
            world.raw = after

    monkeypatch.setattr(healing, "_pulse", pulse)
    return world, before, targets


def test_item_executor_targets_actual_active_slot_and_verifies_single_spend(monkeypatch):
    world, before, targets = item_simulation(monkeypatch)
    result = use_active_full_restore(object(), world, object(), expected=before, incoming_bound=30)
    assert result.party_hp == (76, 90) and world.pulses == 3
    assert targets == ["item", "Full Restore", 1]


@pytest.mark.parametrize(
    "change",
    [
        {"bag_items": ((16, 2), (53, 3))},
        {"bag_items": ((16, 3), (53, 2))},
        {"party_hp": (76, 87)},
        {"party_hp": (75, 90)},
        {"party_hp": (76, 0)},
        {"party_pp": ((0, 0, 0, 0), (0, 0, 0, 0))},
        {"active_party_index": 0},
    ],
)
def test_failed_item_proof_never_retries(monkeypatch, change):
    world, before, _ = item_simulation(monkeypatch, change)
    with pytest.raises(healing.ProtectedRecoveryError):
        use_active_full_restore(object(), world, object(), expected=before, incoming_bound=30)
    assert world.pulses == 3


def test_item_settlement_is_bounded(monkeypatch):
    world, before, _ = item_simulation(monkeypatch, settled=False)
    with pytest.raises(healing.ProtectedRecoveryError, match="within its bound"):
        use_active_full_restore(object(), world, object(), expected=before, incoming_bound=30)
    assert world.pulses == 51


def test_stale_heal_or_insufficient_survival_blocks_all_input(monkeypatch):
    world, before, targets = item_simulation(monkeypatch)
    with pytest.raises(healing.ProtectedRecoveryError):
        use_active_full_restore(object(), world, object(), expected=before, incoming_bound=118)
    with pytest.raises(healing.ProtectedRecoveryError):
        use_active_full_restore(
            object(), world, object(), expected=replace(before, enemy_hp=1), incoming_bound=30
        )
    assert not targets and world.pulses == 0
