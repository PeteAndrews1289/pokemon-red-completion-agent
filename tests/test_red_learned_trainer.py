import hashlib
import json
from types import SimpleNamespace

import pytest

from pokemon_red_completion import red_learned_trainer as learned
from pokemon_red_completion.battle_runtime import BattleIntent, BattleRuntimeTiming
from pokemon_red_completion.red_trainer_practice_log import verify_trainer_practice_event_log


@pytest.mark.parametrize("failure", [None, "actor", "budget", "scope", "guard"])
def test_player_bridge_uses_outer_executor_guard_and_retains_endpoint(
    monkeypatch, tmp_path, failure,
):
    calls = []
    raw = SimpleNamespace(party_count=6 if failure == "scope" else 2)
    reader = SimpleNamespace(read=lambda: raw)
    session = SimpleNamespace(save_state_bytes=lambda: b"actual earned bytes")
    executor = object()
    capture = SimpleNamespace(manifest=SimpleNamespace(capture_id="capture"))
    monkeypatch.setattr(learned, "advance_battle_to_policy_boundary", lambda *a, **k: None)
    monkeypatch.setattr(
        learned.PokemonRedObservationEncoder, "from_state_reader", lambda *a, **k: None,
    )
    monkeypatch.setattr(learned, "prepare_red_battle_scenario", lambda *a, **k: SimpleNamespace(
        initial_observation_sha256="a" * 64,
    ))
    monkeypatch.setattr(learned, "build_battle_scenario_capture_payload", lambda **k: b"manifest")
    monkeypatch.setattr(learned, "open_battle_scenario_capture", lambda *a: capture)
    monkeypatch.setattr(learned, "RedTrainerPracticeOutcomePolicy", lambda **k: None)

    def guard(current):
        assert current is raw
        calls.append("guard")
        if failure == "guard":
            raise RuntimeError("preservation failure")

    def episode(_capture, **kwargs):
        assert _capture is capture
        assert kwargs["action_executor"] is executor
        assert kwargs["decision_guard"] is guard
        assert kwargs["session"] is session
        calls.append("actor")
        if failure == "actor":
            raise RuntimeError("actor failed")
        return SimpleNamespace(
            battle_won=failure != "budget", stop_reason="decision_budget",
            public_dict=lambda: {"battle_won": failure != "budget"},
        )

    monkeypatch.setattr(learned, "run_live_red_trainer_practice_episode", episode)
    battler = learned.FrozenTrainerBattler(session, None, tmp_path, "a" * 40, "root", "b" * 64, {})

    def teacher(_raw):
        pytest.fail("teacher must never own a decision or fallback")

    kwargs = dict(expected_map=61, intent=BattleIntent("funding", "ordinary-trainer-funding"),
                  timing=BattleRuntimeTiming(), label="test", consume_battle_start_schedule=False,
                  move_decision_guard=guard)
    if failure:
        with pytest.raises((ValueError, RuntimeError)):
            battler.run(reader, executor, teacher, **kwargs)
    else:
        assert battler.run(reader, executor, teacher, **kwargs) is raw
    directory = tmp_path / "battle-0001"
    assert (directory / "final.state").read_bytes() == b"actual earned bytes"
    endpoint = json.loads((directory / "endpoint.json").read_bytes())
    assert endpoint["final_state_sha256"] == hashlib.sha256(b"actual earned bytes").hexdigest()
    assert endpoint["outer_goal_verification_required"]
    log = verify_trainer_practice_event_log(directory / "events")
    assert log["terminal_event"] == ("run_failed" if failure else "run_finished")
    assert ("actor" in calls) == (failure not in {"scope", "guard"})


def test_unqualified_or_modified_model_fails_before_opening_game():
    with pytest.raises(ValueError, match="frozen J"):
        learned.load_frozen_trainer_model(b"{}", hashlib.sha256(b"{}").hexdigest())
    with pytest.raises(ValueError, match="frozen J"):
        learned.load_frozen_trainer_model(b"{}", learned.FROZEN_J_SHA256)


def test_routed_funding_passes_explicit_runtime_override(monkeypatch):
    import test_red_routed_trainer_funding as fixtures

    from pokemon_red_completion import red_routed_trainer_funding as funding

    router, state, _, bindings, _ = fixtures.fixture(monkeypatch)
    bound_before = funding.bind_local_trainer_funding(router, bindings, state).bindings[-1]
    def override(*a, **k):
        return None
    router.runtime.trainer_battle_runner = override
    router.runtime.trainer_battle_model_sha256 = learned.FROZEN_J_SHA256
    import pokemon_red_completion.red_trainer_funding_battle as outer
    original = outer.run_prepared_trainer_funding

    def checked(*a, **k):
        assert k["battle_runner_override"] is override
        return original(*a, **k)

    monkeypatch.setattr(outer, "run_prepared_trainer_funding", checked)
    bound = funding.bind_local_trainer_funding(router, bindings, state).bindings[-1]
    assert bound.binding_ref != bound_before.binding_ref
    report = bound.execute()
    assert report.evidence["battle_authority"] == "frozen_learned_trainer"
    assert report.evidence["battle_model_sha256"] == learned.FROZEN_J_SHA256
    assert bound.verify(report).status.value == "succeeded"
