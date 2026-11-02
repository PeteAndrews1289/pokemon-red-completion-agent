import hashlib
import json
from types import SimpleNamespace

import pytest

from pokemon_red_completion import red_learned_trainer as learned
from pokemon_red_completion.battle_runtime import BattleIntent, BattleRuntimeTiming
from pokemon_red_completion.red_trainer_practice_log import verify_trainer_practice_event_log


@pytest.mark.parametrize("fault", [None, "won", "active", "other_reason", "untyped"])
def test_unverified_terminal_exception_carries_only_the_exact_exited_outcome(fault):
    from dataclasses import replace

    from pokemon_red_completion.red_trainer_practice_episode import RedTrainerPracticeEpisode

    episode = RedTrainerPracticeEpisode("capture", "a" * 64, "frozen", (), False, 0,
        "battle_exited_without_win", final_enemy_roster_hp=(1304, 0, 0))
    if fault == "won":
        episode = replace(episode, battle_won=True)
    elif fault == "active":
        episode = replace(episode, final_battle_state=2)
    elif fault == "other_reason":
        episode = replace(episode, stop_reason="decision_budget")
    elif fault == "untyped":
        episode = object()
    if fault:
        with pytest.raises(ValueError):
            learned.FrozenTrainerTerminalUnverified(episode)
    else:
        error = learned.FrozenTrainerTerminalUnverified(episode)
        assert error.episode is episode and not error.episode.battle_won


@pytest.mark.parametrize("changed", ["partition", "model", "receipt", "contract", "funding"])
def test_train_story_scope_rejects_other_authority_before_input(tmp_path, changed):
    from pokemon_red_completion.red_story_battle import StoryTrainerContract

    contract = StoryTrainerContract("defeat_misty", "misty", 65, (235, 35, 1), 191, 2079)
    b = learned.FrozenTrainerBattler(None, None, tmp_path, "a" * 40, "train", "b" * 64, {},
        model_sha256=learned.FROZEN_K_SHA256, qualification_sha256=learned.K_QUALIFICATION_SHA256,
        source_partition=learned.ScenarioPartition.TRAIN, train_story_contract=contract)
    assert b.require_train_story_scope() == contract
    if changed == "partition":
        b.source_partition = learned.ScenarioPartition.DEVELOPMENT
    elif changed == "model":
        b.model_sha256 = learned.FROZEN_J_SHA256
    elif changed == "receipt":
        b.qualification_sha256 = "a" * 64
    elif changed == "contract":
        b.train_story_contract = None
    else:
        b.train_funding_diagnostic = True
    with pytest.raises(ValueError):
        b.require_story_identity()
    assert b.calls == 0 and not tuple(tmp_path.iterdir())


def test_train_story_contract_cannot_be_replaced_by_another_trainer(tmp_path):
    from dataclasses import replace

    from pokemon_red_completion.red_story_battle import (
        FrozenStoryBattleController,
        StoryTrainerContract,
    )

    contract = StoryTrainerContract("defeat_misty", "misty", 65, (235, 35, 1), 191, 2079)
    b = learned.FrozenTrainerBattler(None, None, tmp_path, "a" * 40, "train", "b" * 64, {},
        model_sha256=learned.FROZEN_K_SHA256, qualification_sha256=learned.K_QUALIFICATION_SHA256,
        source_partition=learned.ScenarioPartition.TRAIN, train_story_contract=contract)
    FrozenStoryBattleController(b, (contract,))
    with pytest.raises(ValueError, match="differs"):
        FrozenStoryBattleController(b, (replace(contract, trainer_identity=(235, 35, 2)),))
    assert b.calls == 0


@pytest.mark.parametrize(
    "failure",
    [None, "actor", "budget", "scope", "guard", "k_six", "k_immune", "k_pp",
     "additive", "damage", "wild", "train_wild", "train_funding", "train_story",
     "agatha", "lance", "champion", "train_risk", "preparation"],
)
def test_player_bridge_uses_outer_executor_guard_and_retains_endpoint(
    monkeypatch,
    tmp_path,
    failure,
):
    calls = []
    raw = SimpleNamespace(party_count=6 if failure in {"scope", "k_six", "damage"} else 2)
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
        assert kwargs["train_wild_diagnostic"] is (failure == "train_wild")
        assert kwargs["allow_forced_struggle"] is (failure in {"train_story", "k_pp"})
        assert kwargs["allow_status_moves"] is (
            failure in {"additive", "damage", "agatha", "lance", "champion",
                        "train_risk", "preparation"})
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
    if failure in {"k_six", "k_immune", "k_pp", "wild", "train_wild", "train_funding",
                   "train_story"}:
        battler.model_sha256 = learned.FROZEN_K_SHA256
        battler.qualification_sha256 = learned.K_QUALIFICATION_SHA256
    if failure in {"train_wild", "train_funding", "train_story"}:
        battler.source_partition = learned.ScenarioPartition.TRAIN
    if failure == "train_funding":
        battler.train_funding_diagnostic = True

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
    failed = failure not in {None, "k_six", "k_immune", "k_pp", "additive", "damage", "wild",
                            "train_wild",
                            "train_funding", "train_story", "agatha", "lance", "champion",
                            "train_risk", "preparation"}
    if failure == "train_story":
        from pokemon_red_completion.red_story_battle import StoryTrainerContract

        battler.train_story_contract = StoryTrainerContract("defeat_misty", "misty", 61,
            (235, 35, 1), 191, 2079)
        raw.battle_state, raw.map_id, raw.battler_hp = 2, 61, 10
        reader.read_active_trainer_identity = lambda: (235, 35, 1)
        reader.trainer_switch_prompt_visible = lambda _: False
        reader.read_battle_menu_state = lambda _: SimpleNamespace(
            phase=learned.BattleMenuPhase.MAIN)
        battler.continue_battle(reader, executor, expected_map=61, timing=BattleRuntimeTiming(),
                               decision_guard=guard, story_authority=True)
    elif failure in {"wild", "train_wild", "preparation"}:
        if failure == "preparation":
            from pokemon_red_completion.red_development_preparation_scope import (
                DevelopmentPreparationScope,
            )

            battler.model = SimpleNamespace(to_dict=lambda: {"test": True})
            scope = DevelopmentPreparationScope("b" * 64, "root", "c" * 64,
                learned.canonical_sha256(battler.model.to_dict()), "d" * 64, 61)
            battler.model_sha256 = scope.model_sha256
            battler.qualification_sha256 = scope.identity
            battler.development_preparation_scope = scope
            raw.party_count = 6
        raw.battle_state, raw.map_id = 1, 61
        battler.run_wild_training(reader, executor, expected_map=61,
            timing=BattleRuntimeTiming(), decision_guard=guard)
    elif failure in {"additive", "damage", "agatha", "lance", "champion", "train_risk"}:
        battler.model_sha256 = learned.ADDITIVE_STORY_SHA256
        battler.qualification_sha256 = learned.ADDITIVE_STORY_ADMISSION_SHA256
        if failure in {"damage", "agatha", "lance", "champion", "train_risk"}:
            from test_red_trainer_practice_fit import _target

            from pokemon_red_completion.red_trainer_practice_fit import (
                fit_trainer_practice_three_heads,
            )
            battler.model = fit_trainer_practice_three_heads(
                [_target()], seed=1, epochs=1, require_corpus_floor=False)
            battler.model_sha256 = learned.DAMAGE_STORY_SHA256
            battler.qualification_sha256 = learned.DAMAGE_STORY_ADMISSION_SHA256
            monkeypatch.setattr(learned, "DAMAGE_STORY_MODEL_SHA256",
                                learned.canonical_sha256(battler.model.to_dict()))
        raw.battle_state, raw.map_id, raw.battler_hp = 2, 61, 10
        reader.trainer_switch_prompt_visible = lambda _: False
        reader.read_battle_menu_state = lambda _: SimpleNamespace(
            phase=learned.BattleMenuPhase.MAIN)
        if failure in {"agatha", "lance", "champion"}:
            battler.model_sha256 = learned.AGATHA_STORY_SHA256
            battler.qualification_sha256 = learned.AGATHA_STORY_ADMISSION_SHA256
            battler.source_state_sha256 = learned.AGATHA_STORY_SOURCE_SHA256
            monkeypatch.setattr(learned, "AGATHA_STORY_MODEL_SHA256",
                                learned.canonical_sha256(battler.model.to_dict()))
            raw.map_id = 247
            reader.read_active_trainer_identity = lambda: (246, 46, 1)
        if failure == "lance":
            battler.qualification_sha256 = learned.LANCE_STORY_ADMISSION_SHA256
            battler.source_state_sha256 = learned.LANCE_STORY_SOURCE_SHA256
            raw.map_id = 113
            reader.read_active_trainer_identity = lambda: (247, 47, 1)
        if failure == "champion":
            battler.qualification_sha256 = learned.CHAMPION_STORY_ADMISSION_SHA256
            battler.source_state_sha256 = learned.CHAMPION_STORY_SOURCE_SHA256
            raw.map_id = 120
            reader.read_active_trainer_identity = lambda: (243, 43, 2)
        if failure == "train_risk":
            from pokemon_red_completion.red_story_battle import StoryTrainerContract

            battler.model_sha256 = learned.AGATHA_STORY_SHA256
            battler.qualification_sha256 = learned.TRAIN_RISK_ADMISSION_SHA256
            monkeypatch.setattr(learned, "AGATHA_STORY_MODEL_SHA256",
                                learned.canonical_sha256(battler.model.to_dict()))
            battler.source_partition = learned.ScenarioPartition.TRAIN
            battler.train_story_contract = StoryTrainerContract(
                "defeat_misty", "misty", 61, (235, 35, 1), 191, 2079)
            battler.train_risk_story_scope = learned.TrainRiskStoryScope(
                "c" * 64, battler.source_state_sha256, battler.root_lineage_id,
                battler.train_story_contract)
            reader.read_active_trainer_identity = lambda: (235, 35, 1)
        battler.continue_battle(
            reader, executor, expected_map=raw.map_id, timing=BattleRuntimeTiming(),
            decision_guard=guard, story_authority=True)
    elif failure == "k_pp":
        battler.pp_depleted_switch_screen = True
        raw.battle_state, raw.map_id, raw.battler_hp = 2, 61, 10
        reader.trainer_switch_prompt_visible = lambda _: False
        reader.read_battle_menu_state = lambda _: SimpleNamespace(
            phase=learned.BattleMenuPhase.MAIN)
        battler._play(
            reader, executor, expected_map=61, timing=BattleRuntimeTiming(), label="test",
            decision_guard=guard, resume=True, require_win=False,
            authority="frozen-k-story-development",
        )
        assert policy_arguments[0]["pp_depleted_switch_screen"] is True
        first = json.loads((tmp_path / "battle-0001/events/event-00001.json").read_bytes())
        assert first["payload"]["identity"]["pp_depleted_switch_screen"] is True
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
    if failure == "preparation":
        first = json.loads((directory / "events/event-00001.json").read_bytes())
        identity = first["payload"]["identity"]
        assert identity["authority"] == "scoped-wild-preparation-development"
        assert identity["allow_status_moves"] is True
        assert identity["mechanics_aware_choices"] is True
        assert identity["diagnostic_stay_when_productive"] is False
        assert policy_arguments[0]["mechanics_aware_choices"] is True
    if failure == "damage":
        first = json.loads(sorted((directory / "events").glob("event-*.json"))[0].read_text())
        identity = first["payload"]["identity"]
        assert identity["authority"] == "frozen-damage-story-development"
        assert identity["allow_status_moves"] is True
        assert identity["allow_stranded_accuracy_move"] is False
    if failure == "train_risk":
        first = json.loads(sorted((directory / "events").glob("event-*.json"))[0].read_text())
        identity = first["payload"]["identity"]
        assert identity["authority"] == learned.TRAIN_RISK_AUTHORITY
        assert identity["allow_status_moves"] is identity["allow_stranded_accuracy_move"] is True
        assert identity["source_partition"] == "train" and identity["fit_allowed"] is False
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


@pytest.mark.parametrize("native_sendout", [False, True])
def test_retained_faint_distinguishes_native_sendout_from_owned_replacement(
    monkeypatch, tmp_path, native_sendout
):
    raw = SimpleNamespace(party_count=2, battler_hp=0, battle_state=2, map_id=61,
        enemy_party_position=255 if native_sendout else 0)
    calls = []
    reader = SimpleNamespace(read=lambda: raw)
    reader.trainer_switch_prompt_visible = lambda _: False
    reader.read_battle_menu_state = lambda _: SimpleNamespace(phase=learned.BattleMenuPhase.MAIN)
    session = SimpleNamespace(save_state_bytes=lambda: b"retained faint")
    encoder = SimpleNamespace(
        snapshot_from_raw=lambda r: SimpleNamespace(
            to_dict=lambda: {"active_hp": r.battler_hp},
        )
    )
    monkeypatch.setattr(
        learned.PokemonRedObservationEncoder, "from_state_reader", lambda *a, **k: encoder
    )

    def forbidden(*a, **k):
        pytest.fail("a forced boundary must not advance to MAIN or prepare an attack")

    def advance(_reader, _executor, **kwargs):
        assert native_sendout and _executor is executor
        assert kwargs["expected_map"] == 61 and kwargs["expected_battle_state"] == 2
        calls.append("native_sendout")
        raw.battler_hp = 8
        raw.enemy_party_position = 0

    def prepare(_encoder, current, **kwargs):
        assert native_sendout and current.battler_hp == 8
        calls.append("prepared_main")
        return SimpleNamespace(
            initial_observation_sha256=learned.canonical_sha256({"active_hp": 8})
        )

    monkeypatch.setattr(
        learned, "advance_battle_to_policy_boundary", advance if native_sendout else forbidden
    )
    monkeypatch.setattr(
        learned, "prepare_red_battle_scenario", prepare if native_sendout else forbidden
    )
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
    assert calls == (["native_sendout", "prepared_main"] if native_sendout else [])
    assert manifests[0]["initial_observation_sha256"] == learned.canonical_sha256(
        {"active_hp": 8 if native_sendout else 0}
    )
    assert (tmp_path / "battle-0001/final.state").read_bytes() == b"retained faint"
