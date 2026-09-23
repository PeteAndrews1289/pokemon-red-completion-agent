import hashlib
import json
from types import SimpleNamespace

import pytest

from pokemon_red_completion import red_learned_trainer as learned
from pokemon_red_completion.battle_runtime import BattleIntent, BattleRuntimeTiming
from pokemon_red_completion.red_trainer_practice_log import verify_trainer_practice_event_log


@pytest.mark.parametrize(
    "failure", [None, "actor", "budget", "scope", "guard", "k_six", "k_immune", "additive", "wild"],
)
def test_player_bridge_uses_outer_executor_guard_and_retains_endpoint(
    monkeypatch,
    tmp_path,
    failure,
):
    calls = []
    raw = SimpleNamespace(party_count=6 if failure in {"scope", "k_six"} else 2)
    reader = SimpleNamespace(read=lambda: raw)
    session = SimpleNamespace(save_state_bytes=lambda: b"actual earned bytes")
    executor = object()
    capture = SimpleNamespace(manifest=SimpleNamespace(capture_id="capture"))
    monkeypatch.setattr(learned, "advance_battle_to_policy_boundary", lambda *a, **k: None)
    monkeypatch.setattr(
        learned.PokemonRedObservationEncoder,
        "from_state_reader",
        lambda *a, **k: None,
    )
    monkeypatch.setattr(
        learned,
        "prepare_red_battle_scenario",
        lambda *a, **k: SimpleNamespace(
            initial_observation_sha256="a" * 64,
        ),
    )
    monkeypatch.setattr(learned, "build_battle_scenario_capture_payload", lambda **k: b"manifest")
    monkeypatch.setattr(learned, "open_battle_scenario_capture", lambda *a: capture)
    policy_arguments = []
    monkeypatch.setattr(
        learned, "RedTrainerPracticeOutcomePolicy", lambda **k: policy_arguments.append(k),
    )

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
        assert kwargs["allow_status_moves"] is (failure == "additive")
        calls.append("actor")
        if failure == "actor":
            raise RuntimeError("actor failed")
        return SimpleNamespace(
            battle_won=failure != "budget",
            stop_reason="decision_budget",
            public_dict=lambda: {"battle_won": failure != "budget"},
        )

    monkeypatch.setattr(learned, "run_live_red_trainer_practice_episode", episode)
    battler = learned.FrozenTrainerBattler(session, None, tmp_path, "a" * 40, "root", "b" * 64, {})
    if failure in {"k_six", "k_immune", "wild"}:
        battler.model_sha256 = learned.FROZEN_K_SHA256
        battler.qualification_sha256 = learned.K_QUALIFICATION_SHA256

    def teacher(_raw):
        pytest.fail("teacher must never own a decision or fallback")

    kwargs = dict(
        expected_map=61,
        intent=BattleIntent("funding", "ordinary-trainer-funding"),
        timing=BattleRuntimeTiming(),
        label="test",
        consume_battle_start_schedule=False,
        move_decision_guard=guard,
    )
    failed = failure not in {None, "k_six", "k_immune", "additive", "wild"}
    if failure == "wild":
        raw.battle_state, raw.map_id = 1, 61
        battler.run_wild_training(reader, executor, expected_map=61,
            timing=BattleRuntimeTiming(), decision_guard=guard)
    elif failure == "additive":
        battler.model_sha256 = learned.ADDITIVE_STORY_SHA256
        battler.qualification_sha256 = learned.ADDITIVE_STORY_ADMISSION_SHA256
        raw.battle_state, raw.map_id, raw.battler_hp = 2, 61, 10
        reader.trainer_switch_prompt_visible = lambda _: False
        reader.read_battle_menu_state = lambda _: SimpleNamespace(
            phase=learned.BattleMenuPhase.MAIN)
        battler.continue_battle(reader, executor, expected_map=61, timing=BattleRuntimeTiming(),
                               decision_guard=guard, story_authority=True)
    elif failure == "k_immune":
        battler._play(
            reader, executor, expected_map=61, timing=BattleRuntimeTiming(), label="test",
            decision_guard=guard, resume=False, require_win=True,
            authority="frozen-k-league-development", allow_immune_switch_recovery=True,
        )
        assert policy_arguments[0]["allow_immune_switch_recovery"] is True
    elif failed:
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
    assert log["terminal_event"] == ("run_failed" if failed else "run_finished")
    assert endpoint["model_sha256"] == battler.model_sha256
    assert endpoint["qualification_sha256"] == battler.qualification_sha256
    assert ("actor" in calls) == (failure not in {"scope", "guard"})


@pytest.mark.parametrize("enabled,authority", [(1, "frozen-k-league-development"), (True, None)])
def test_immune_recovery_cannot_expand_ordinary_player_scope(tmp_path, enabled, authority):
    battler = learned.FrozenTrainerBattler(None, None, tmp_path, "a" * 40, "root", "b" * 64, {})
    with pytest.raises(ValueError, match="explicit qualified K"):
        battler._play(
            None, None, expected_map=61, timing=BattleRuntimeTiming(), label="test",
            decision_guard=lambda _: None, resume=False, require_win=True,
            authority=authority, allow_immune_switch_recovery=enabled,
        )
    assert not tuple(tmp_path.iterdir())


@pytest.mark.parametrize(
    "sha,receipt,limit",
    [
        (learned.FROZEN_J_SHA256, None, 3),
        (learned.FROZEN_K_SHA256, learned.K_QUALIFICATION_SHA256, 6),
        (learned.FROZEN_K_SHA256, None, 0),
        (learned.FROZEN_K_SHA256, "0" * 64, 0),
        ("0" * 64, learned.K_QUALIFICATION_SHA256, 0),
        (None, None, 0),
    ],
)
def test_qualified_party_scope_requires_exact_model_and_k_receipt(sha, receipt, limit):
    assert learned.qualified_party_limit(sha, receipt) == limit


def test_k_without_receipt_or_with_changed_model_cannot_load():
    for receipt in (None, b"{}"):
        with pytest.raises(ValueError):
            learned.load_frozen_trainer_model(b"{}", learned.FROZEN_K_SHA256, qualification=receipt)


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


def test_unsupported_party_is_not_offered_a_learned_funding_route(monkeypatch):
    import test_red_routed_trainer_funding as fixtures

    from pokemon_red_completion import red_routed_trainer_funding as funding

    router, state, _, bindings, calls = fixtures.fixture(monkeypatch)
    router.runtime.trainer_battle_runner = object()
    router.runtime.trainer_battle_model_sha256 = learned.FROZEN_J_SHA256
    state.party = SimpleNamespace(size=4)
    from dataclasses import replace

    state.raw = replace(state.raw, party_count=4, party_hp=(20, 20, 20, 20))
    assert funding.bind_local_trainer_funding(router, bindings, state) is bindings
    assert calls == []


def test_retained_faint_reaches_model_without_advancing_to_main(monkeypatch, tmp_path):
    raw = SimpleNamespace(party_count=2, battler_hp=0, battle_state=2, map_id=61)
    reader = SimpleNamespace(read=lambda: raw)
    session = SimpleNamespace(save_state_bytes=lambda: b"retained faint")
    encoder = SimpleNamespace(
        snapshot_from_raw=lambda r: SimpleNamespace(
            to_dict=lambda: {"active_hp": 0},
        )
    )
    monkeypatch.setattr(
        learned.PokemonRedObservationEncoder, "from_state_reader", lambda *a, **k: encoder
    )

    def forbidden(*a, **k):
        pytest.fail("a forced boundary must not advance to MAIN or prepare an attack")

    monkeypatch.setattr(learned, "advance_battle_to_policy_boundary", forbidden)
    monkeypatch.setattr(learned, "prepare_red_battle_scenario", forbidden)
    manifests = []

    def manifest(**kwargs):
        manifests.append(kwargs)
        return b"manifest"

    monkeypatch.setattr(learned, "build_battle_scenario_capture_payload", manifest)
    capture = SimpleNamespace(manifest=SimpleNamespace(capture_id="forced"))
    monkeypatch.setattr(learned, "open_battle_scenario_capture", lambda *a: capture)
    monkeypatch.setattr(learned, "RedTrainerPracticeOutcomePolicy", lambda **k: None)
    result = SimpleNamespace(
        battle_won=False, stop_reason="party_defeated", public_dict=lambda: {"battle_won": False}
    )
    executor = object()

    def episode(_capture, **kwargs):
        assert kwargs["action_executor"] is executor
        kwargs["decision_guard"](raw)
        return result

    monkeypatch.setattr(learned, "run_live_red_trainer_practice_episode", episode)
    checks = []
    battler = learned.FrozenTrainerBattler(session, None, tmp_path, "a" * 40, "root", "b" * 64, {})
    assert (
        battler.continue_battle(
            reader,
            executor,
            expected_map=61,
            timing=BattleRuntimeTiming(),
            decision_guard=lambda state: checks.append(state),
        )
        is result
    )
    assert checks == [raw, raw]
    assert manifests[0]["initial_observation_sha256"] == learned.canonical_sha256({"active_hp": 0})
    assert (tmp_path / "battle-0001/final.state").read_bytes() == b"retained faint"
