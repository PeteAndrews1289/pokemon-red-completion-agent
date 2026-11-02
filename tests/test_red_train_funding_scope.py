from types import SimpleNamespace

import pytest

from pokemon_red_completion import red_learned_trainer as learned
from pokemon_red_completion import red_routed_trainer_funding as funding


def actor(tmp_path, **changes):
    values = dict(source_partition=learned.ScenarioPartition.TRAIN,
                  model_sha256=learned.FROZEN_K_SHA256,
                  qualification_sha256=learned.K_QUALIFICATION_SHA256,
                  train_funding_diagnostic=True)
    values.update(changes)
    return learned.FrozenTrainerBattler(
        None, None, tmp_path, "a"*40, "train-root", "b"*64, {}, **values)


@pytest.mark.parametrize("changes", [
    {"train_funding_diagnostic": False}, {"train_funding_diagnostic": 1},
    {"source_partition": learned.ScenarioPartition.DEVELOPMENT},
    {"source_partition": "train"}, {"model_sha256": learned.FROZEN_J_SHA256},
    {"qualification_sha256": "c"*64},
])
def test_unqualified_train_funding_fails_before_inputs(tmp_path, changes):
    owner = actor(tmp_path, **changes)
    with pytest.raises(ValueError):
        owner.require_funding_scope()
    assert owner.calls == 0 and not list(tmp_path.iterdir())


@pytest.mark.parametrize("changes", [
    {}, {"source_partition": learned.ScenarioPartition.DEVELOPMENT,
         "train_funding_diagnostic": False},
])
def test_exact_opt_in_and_unchanged_development_scope(tmp_path, changes):
    actor(tmp_path, **changes).require_funding_scope()


@pytest.mark.parametrize("changes", [
    {"resume": True}, {"require_win": False}, {"wild_training": True},
    {"authority": "frozen-k-story-development"}, {"allow_immune_switch_recovery": True},
    {"train_funding_diagnostic": 1},
])
def test_funding_opt_in_cannot_expand_to_other_battle_modes(tmp_path, changes):
    owner = actor(tmp_path)
    args = dict(expected_map=51, timing=None, label="test", decision_guard=None,
                resume=False, require_win=True, train_funding_diagnostic=True)
    args.update(changes)
    with pytest.raises(ValueError):
        owner._play(None, None, **args)
    assert owner.calls == 0 and not list(tmp_path.iterdir())


def test_bare_train_story_call_still_rejected(tmp_path):
    with pytest.raises(ValueError, match="explicit qualified K diagnostic"):
        actor(tmp_path)._play(None, None, expected_map=51, timing=None,
            label="story", decision_guard=None, resume=True, require_win=False)


def test_private_entry_cannot_bypass_strict_opt_in_type(tmp_path):
    owner = actor(tmp_path, train_funding_diagnostic=1)
    with pytest.raises(ValueError, match="must be boolean"):
        owner._play(None, None, expected_map=51, timing=None, label="test",
            decision_guard=None, resume=False, require_win=True,
            train_funding_diagnostic=True)
    assert owner.calls == 0


@pytest.mark.parametrize("enabled", [False, True])
def test_router_rejects_unsupported_actor_before_travel(monkeypatch, tmp_path, enabled):
    import test_red_routed_trainer_funding as fixtures

    router, state, _, bindings, calls = fixtures.fixture(monkeypatch)
    owner = actor(tmp_path, train_funding_diagnostic=enabled)
    router.runtime.trainer_battle_runner = owner.run
    router.runtime.trainer_battle_model_sha256 = owner.model_sha256
    router.runtime.trainer_battle_qualification_sha256 = owner.qualification_sha256
    result = funding.bind_local_trainer_funding(router, bindings, state)
    assert (result is bindings) is not enabled
    assert calls == [] and owner.calls == 0


def test_funding_run_passes_narrow_opt_in_without_teacher(monkeypatch, tmp_path):
    from pokemon_red_completion.battle_runtime import BattleIntent

    owner = actor(tmp_path)
    captured = []
    monkeypatch.setattr(owner, "_play", lambda *a, **kw: captured.append(kw))
    reader = SimpleNamespace(read=lambda: "terminal")
    assert owner.run(reader, None, None, expected_map=51,
        intent=BattleIntent("income", "ordinary-trainer-funding"), timing=None,
        label="test", consume_battle_start_schedule=False,
        move_decision_guard=None) == "terminal"
    assert captured[0]["train_funding_diagnostic"] is True
    assert captured[0]["require_win"] is True and captured[0]["resume"] is False


def test_scope_revocation_after_menu_stops_before_departure(monkeypatch, tmp_path):
    import test_red_routed_trainer_funding as fixtures

    router, state, _, bindings, calls = fixtures.fixture(monkeypatch)
    owner = actor(tmp_path)
    router.runtime.trainer_battle_runner = owner.run
    router.runtime.trainer_battle_model_sha256 = owner.model_sha256
    router.runtime.trainer_battle_qualification_sha256 = owner.qualification_sha256
    binding = funding.bind_local_trainer_funding(router, bindings, state).bindings[-1]
    owner.train_funding_diagnostic = False
    with pytest.raises(ValueError, match="explicit diagnostic"):
        binding.execute()
    assert calls == [] and owner.calls == 0
