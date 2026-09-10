"""Exercise recovery's actual serialized proposal interface, without a ROM."""

import json
import runpy
from pathlib import Path
from types import SimpleNamespace

import pytest

from pokemon_red_completion.goal_manager import GoalKind
from pokemon_red_completion.red_goal_context_profile import (
    RedGoalMechanic,
    build_red_goal_context_profile_payload,
    parse_red_goal_context_profile,
)


@pytest.mark.parametrize('extra', [
    {'maximum_critical_exposures': True},
    {'maximum_critical_exposures': 3},
    {'maximum_critical_exposures': 1},
    {'maximum_critical_exposures': 1, 'finish_trainer_funding': True,
     'maximum_full_restores': 1},
    {'maximum_critical_exposures': 1, 'finish_trainer_funding': True,
     'zero_item_survival': True},
    {'maximum_critical_exposures': 1, 'finish_trainer_funding': True,
     'finish_scripted_trainer': 'lance'},
])
def test_risk_authority_is_explicit_and_cannot_be_combined_with_item_authority(extra):
    module = runpy.run_path(
        str(Path(__file__).resolve().parents[1] / 'scripts/recover_red_player_failure.py')
    )
    with pytest.raises(ValueError, match='critical exposure'):
        module['run'](SimpleNamespace(**extra))


@pytest.mark.parametrize('extra', [
    {'admit_settled_field': 1},
    {'admit_settled_field': True, 'finish_trainer_funding': True},
    {'admit_settled_field': True, 'maximum_full_restores': 1},
    {'admit_settled_field': True, 'prior_switches': [0]},
])
def test_settled_admission_rejects_mixed_authority_before_prepare(extra):
    module = runpy.run_path(
        str(Path(__file__).resolve().parents[1] / 'scripts/recover_red_player_failure.py')
    )
    with pytest.raises(ValueError, match='exclusive zero-controller'):
        module['run'](SimpleNamespace(**extra))


def test_risk_intents_remain_consumed_across_failed_recovery_ancestry(monkeypatch):
    module = runpy.run_path(
        str(Path(__file__).resolve().parents[1] / 'scripts/recover_red_player_failure.py')
    )

    def episode(key):
        parent = {'child': 'bridge', 'bridge': 'origin'}.get(key)
        metadata = ({'schema': 'pokemon.red.forced-recovery-header.v1',
                     'recovery': {'failure_episode_id': parent}} if parent else {})
        rows = ([{'kind': 'attack'}] if key == 'bridge' else
                [{'kind': 'risk_attack', 'move_executed': False, 'pp_spent': 0},
                 {'kind': 'attack'}, {'kind': 'heal'}])
        return SimpleNamespace(read_header=lambda: {'metadata': metadata},
                               stream_names=('trainer_recovery_decisions',),
                               iter_stream=lambda _: iter(rows))

    store = SimpleNamespace(open_failed_episode=episode)
    observe = module['observed_failed_trainer_risk_claims']
    assert observe(store, 'origin') == observe(store, 'bridge') == 1
    assert observe(store, 'child') == 2
    with pytest.raises(ValueError, match='ancestry'):
        observe(store, 'child', depth=8)
    monkeypatch.setitem(module['run'].__globals__, 'prepare',
                        lambda _: (SimpleNamespace(private_root=store), {}))
    with pytest.raises(ValueError, match='refresh already claimed critical'):
        module['run'](SimpleNamespace(finish_trainer_funding=True,
                                      maximum_critical_exposures=1, failed_episode='child'))


@pytest.mark.parametrize('extra', [
    {'zero_item_survival': 1},
    {'zero_item_survival': True},
    {'zero_item_survival': True, 'finish_trainer_funding': True,
     'maximum_full_restores': 1},
    {'zero_item_survival': True, 'finish_trainer_funding': True,
     'finish_scripted_trainer': 'lance'},
])
def test_zero_item_survival_is_explicit_and_does_not_borrow_healing_authority(extra):
    module = runpy.run_path(
        str(Path(__file__).resolve().parents[1] / 'scripts/recover_red_player_failure.py')
    )
    with pytest.raises(ValueError, match='zero-item survival'):
        module['run'](SimpleNamespace(**extra))


def test_zero_item_survival_validates_recorded_switch_history_before_loading(monkeypatch):
    module = runpy.run_path(
        str(Path(__file__).resolve().parents[1] / 'scripts/recover_red_player_failure.py')
    )
    # Reach the real mode/history gate, but no ROM/emulator is available to this test.
    namespace = module['run'].__globals__
    monkeypatch.setitem(namespace, 'prepare', lambda _: (SimpleNamespace(private_root='store'), {}))
    monkeypatch.setitem(namespace, 'remaining_trainer_heal_budget', lambda *_: 0)
    monkeypatch.setitem(namespace, 'observed_failed_trainer_switches', lambda *_: (2, 4))
    with pytest.raises(ValueError, match='prior switches differ'):
        module['run'](SimpleNamespace(zero_item_survival=True, finish_trainer_funding=True,
                                      failed_episode='retained', prior_switches=[2]))


@pytest.mark.parametrize('extra', [
    {'finish_scripted_trainer': 'champion'},
    {'finish_scripted_trainer': 'lance', 'finish_trainer_funding': True},
    {'finish_scripted_trainer': 'lance', 'maximum_full_restores': 1},
    {'finish_scripted_trainer': 'lance', 'prior_switches': [2]},
])
def test_scripted_recovery_does_not_borrow_active_battle_or_healing_authority(extra):
    module = runpy.run_path(
        str(Path(__file__).resolve().parents[1] / 'scripts/recover_red_player_failure.py')
    )
    with pytest.raises(ValueError, match='separate zero-item'):
        module['run'](SimpleNamespace(**extra))


def test_switch_history_comes_from_actual_battle_transitions_and_retains_ancestry():
    module = runpy.run_path(
        str(Path(__file__).resolve().parents[1] / "scripts/recover_red_player_failure.py")
    )

    def snapshot(key, active, kind="trainer"):
        return {
            "snapshot_sha256": key,
            "snapshot": {
                "features": {
                    "party": {"active_index": active},
                    "battle": {"kind": kind},
                }
            },
        }

    def episode(prior=None):
        metadata = (
            {
                "schema": "pokemon.red.forced-recovery-header.v1",
                "recovery": {"failure_episode_id": prior},
            }
            if prior
            else {}
        )
        streams = {
            "snapshots": [
                snapshot("a", 0, "field"),
                snapshot("b", 1, "field"),
                snapshot("c", 1),
                snapshot("d", 3),
                snapshot("e", 0),
            ],
            "executions": [
                {"before_sha256": "a", "after_sha256": "b"},
                {"before_sha256": "c", "after_sha256": "d"},
                {"before_sha256": "d", "after_sha256": "d"},
                {"before_sha256": "d", "after_sha256": "e"},
            ],
        }
        return SimpleNamespace(
            read_header=lambda: {"metadata": metadata}, iter_stream=lambda name: iter(streams[name])
        )

    store = SimpleNamespace(
        open_failed_episode=lambda key: episode("parent" if key == "child" else None),
    )
    assert module["observed_failed_trainer_switches"](store, "parent") == (4, 1)
    assert module["observed_failed_trainer_switches"](store, "child") == (4, 1, 4, 1)


def test_failed_recovery_item_claims_carry_across_ancestry_without_refund():
    module = runpy.run_path(
        str(Path(__file__).resolve().parents[1] / "scripts/recover_red_player_failure.py")
    )

    def episode(key):
        metadata = (
            {}
            if key == "origin"
            else {
                "schema": "pokemon.red.forced-recovery-header.v1",
                "recovery": {"failure_episode_id": "origin" if key == "first" else "first"},
            }
        )
        rows = [] if key == "origin" else [{"kind": "attack"}, {"kind": "heal"}]
        return SimpleNamespace(
            read_header=lambda: {"metadata": metadata},
            stream_names=() if key == "origin" else ("trainer_recovery_decisions",),
            iter_stream=lambda _: iter(rows),
        )

    store = SimpleNamespace(open_failed_episode=episode)
    budget = module["remaining_trainer_heal_budget"]
    assert budget(store, "first", 1) == 1
    assert budget(store, "second", 0) == 2
    for episode_id, requested in (("first", 2), ("second", 1), ("first", True)):
        with pytest.raises(ValueError, match="refresh"):
            budget(store, episode_id, requested)
    with pytest.raises(ValueError, match="ancestry"):
        module["observed_failed_trainer_heal_claims"](store, "first", depth=8)


def test_recovery_restores_canonical_existing_proposal_without_resampling():
    module = runpy.run_path(
        str(Path(__file__).resolve().parents[1] / "scripts/recover_red_player_failure.py")
    )
    payload = build_red_goal_context_profile_payload(
        profile_id="recovery-test",
        providers=(
            (GoalKind.ADVANCE_STORY, RedGoalMechanic.MIDGAME_STORY, {}),
            (GoalKind.DEVELOP_TEAM, RedGoalMechanic.BALANCED_TEAM, {}),
            (GoalKind.RESTORE_TEAM, RedGoalMechanic.FIELD_RESTORE, {}),
        ),
    )
    original = parse_red_goal_context_profile(payload)
    document = {"profile": json.loads(payload), "profile_sha256": original.profile_sha256}
    assert module["restored_proposal_profile"](document) == original
    assert document["profile"] == json.loads(payload)
    with pytest.raises(ValueError, match="identity differs"):
        module["restored_proposal_profile"]({**document, "profile_sha256": "f" * 64})
