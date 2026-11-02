import json
from hashlib import sha256

import pytest
from test_red_post_battle_strategy import episode

from pokemon_red_completion.battle_scenario_capture import (
    build_battle_scenario_capture_payload,
    open_battle_scenario_capture,
)
from pokemon_red_completion.post_battle_strategy import BattleResult
from pokemon_red_completion.provenance import canonical_sha256
from pokemon_red_completion.red_learned_trainer import (
    FROZEN_K_SHA256,
    K_QUALIFICATION_SHA256,
    FrozenTrainerBattler,
    story_battle_authority,
)
from pokemon_red_completion.red_player_battle_history import NativeBattlerHistory
from pokemon_red_completion.red_trainer_practice_log import TrainerPracticeEventLog
from pokemon_red_completion.scenario_lab import ScenarioPartition


def battler(tmp_path):
    return FrozenTrainerBattler(None, None, tmp_path, "a" * 40, "live-root", "b" * 64, {})


def publish(
    b, *, unresolved=False, failed=False, omit_scope=False, wild=False, extra_identity=None
):
    b.calls += 1
    directory = b.output / f"battle-{b.calls:04d}"
    directory.mkdir()
    initial, final = b"initial", b"final"
    (directory / "initial.state").write_bytes(initial)
    (directory / "initial.state.json").write_bytes(
        build_battle_scenario_capture_payload(
            capture_id=f"player-trainer-{b.calls:04d}",
            root_lineage_id=b.root_lineage_id,
            partition=b.source_partition,
            state_bytes=initial,
            initial_observation_sha256="c" * 64,
            source_commit=b.source_commit,
            expected_map=b.train_story_contract.map_id if b.train_story_contract else 1,
            expected_battle_state=1 if wild else 2,
            source_state_sha256=b.source_state_sha256,
        )
    )
    capture = open_battle_scenario_capture(
        directory / "initial.state", directory / "initial.state.json"
    )
    row = episode()
    if wild:
        for decision in row["decisions"]:
            decision["observation"]["features"]["battle"]["kind"] = "wild"
    row.update(capture_id=capture.manifest.capture_id, manifest_sha256=capture.manifest_sha256)
    if unresolved:
        row["stop_reason"] = "decision_cap"
    (directory / "outcome.json").write_text(json.dumps(row))
    (directory / "final.state").write_bytes(final)
    endpoint = dict(
        final_state_sha256=sha256(final).hexdigest(),
        outcome_sha256=canonical_sha256(row),
        model_sha256=b.model_sha256,
        qualification_sha256=b.qualification_sha256,
        actor_returned_win=False,
        outer_goal_verification_required=True,
    )
    (directory / "endpoint.json").write_text(json.dumps(endpoint))
    log = TrainerPracticeEventLog(
        directory / "events",
        run_identity=dict(
            model_sha256=b.model_sha256,
            qualification_sha256=b.qualification_sha256,
            source_commit=b.source_commit,
            root_lineage_id=b.root_lineage_id,
            parent_state_sha256=b.source_state_sha256,
            **({"wild_training": True} if wild else {}),
            **(
                {"train_funding_diagnostic": True}
                if b.train_funding_diagnostic and not omit_scope
                else {}
            ),
            **(
                {
                    "train_story_contract": b._train_story_document(),
                    "authority": story_battle_authority(b.model_sha256, b.qualification_sha256),
                }
                if b.train_story_contract and not omit_scope
                else {}
            ),
            **(
                {
                    "train_risk_story_scope": b.train_risk_story_scope.document(),
                    "allow_status_moves": True,
                    "allow_stranded_accuracy_move": True,
                }
                if b.train_risk_story_scope and not omit_scope
                else {}
            ),
            **(
                {"source_partition": "train", "fit_allowed": False}
                if b.source_partition is ScenarioPartition.TRAIN
                else {}
            ),
            **(extra_identity or {}),
        ),
    )
    if failed:
        log.fail(RuntimeError("require-win loss"))
    else:
        log.finish(endpoint)
    return directory


@pytest.mark.parametrize("omit", [False, True])
def test_train_story_history_requires_exact_contract_in_native_log(tmp_path, omit):
    from pokemon_red_completion.red_story_battle import StoryTrainerContract

    b = battler(tmp_path)
    b.source_partition = ScenarioPartition.TRAIN
    b.model_sha256, b.qualification_sha256 = FROZEN_K_SHA256, K_QUALIFICATION_SHA256
    b.train_story_contract = StoryTrainerContract(
        "defeat_misty", "misty", 65, (235, 35, 1), 191, 2079
    )
    history = NativeBattlerHistory(b)
    publish(b, omit_scope=omit)
    if omit:
        with pytest.raises(ValueError, match="exact lesson scope"):
            history()
    else:
        assert history().result is BattleResult.LOST
        b.train_story_contract = None
        with pytest.raises(ValueError, match="identity"):
            history()


def test_train_source_remains_train_and_identity_is_pinned(tmp_path):
    b = battler(tmp_path)
    b.source_partition = ScenarioPartition.TRAIN
    b.model_sha256, b.qualification_sha256 = FROZEN_K_SHA256, K_QUALIFICATION_SHA256
    b.train_funding_diagnostic = True
    history = NativeBattlerHistory(b)
    directory = publish(b)
    assert history().result is BattleResult.LOST
    capture = open_battle_scenario_capture(
        directory / "initial.state", directory / "initial.state.json"
    )
    assert capture.manifest.partition is ScenarioPartition.TRAIN
    b.source_partition = ScenarioPartition.DEVELOPMENT
    with pytest.raises(ValueError, match="identity"):
        history()


@pytest.mark.parametrize("enabled", [False, True])
def test_train_trainer_history_cannot_invent_funding_scope(tmp_path, enabled):
    b = battler(tmp_path)
    b.source_partition = ScenarioPartition.TRAIN
    b.model_sha256, b.qualification_sha256 = FROZEN_K_SHA256, K_QUALIFICATION_SHA256
    b.train_funding_diagnostic = enabled
    history = NativeBattlerHistory(b)
    publish(b, omit_scope=True)
    with pytest.raises(ValueError):
        history()


def test_newest_battle_replaces_history_and_preserves_reported_loss(tmp_path):
    b = battler(tmp_path)
    history = NativeBattlerHistory(b)
    assert history() is None
    publish(b, failed=True)
    loss = history()
    assert loss.result is BattleResult.LOST
    assert history() == loss  # Healing elsewhere does not rewrite battle history.
    publish(b, unresolved=True)
    assert history().result is BattleResult.UNRESOLVED
    assert len(history.receipts) == 2


def test_new_incomplete_battle_does_not_reuse_old_history(tmp_path):
    b = battler(tmp_path)
    history = NativeBattlerHistory(b)
    publish(b)
    assert history().result is BattleResult.LOST
    b.calls += 1
    with pytest.raises(ValueError):
        history()
    assert len(history.receipts) == 1


@pytest.mark.parametrize("legacy", [False, True])
@pytest.mark.parametrize("fault", [
    None, "identity", "terminal", "win", "outcome", "initial",
    "phase", "selection", "recording", "extra_event", "message",
])
def test_pre_capture_checkpoint_is_closed_no_inference_and_preserves_prefix(
    tmp_path, legacy, fault,
):
    from pokemon_red_completion.battle_runtime_diagnostics import BattleRuntimeDiagnostic
    from pokemon_red_completion.executor import ControllerActionBudgetExhausted

    b = battler(tmp_path)
    history = NativeBattlerHistory(b)
    publish(b)
    previous = history()
    b.calls += 1
    directory = b.output / f"battle-{b.calls:04d}"
    directory.mkdir()
    terminal = sha256(b"entry-terminal").hexdigest()
    (directory / "final.state").write_bytes(b"entry-terminal")
    endpoint = dict(
        final_state_sha256=terminal,
        outcome_sha256=None,
        model_sha256="f" * 64 if fault == "identity" else b.model_sha256,
        qualification_sha256=b.qualification_sha256,
        actor_returned_win=fault == "win",
        outer_goal_verification_required=True,
    )
    (directory / "endpoint.json").write_text(json.dumps(endpoint))
    log = TrainerPracticeEventLog(directory / "events", run_identity=dict(
        model_sha256=b.model_sha256, qualification_sha256=b.qualification_sha256,
        source_commit=b.source_commit, root_lineage_id=b.root_lineage_id,
        parent_state_sha256=b.source_state_sha256,
    ))
    error = (RuntimeError("native lesson action budget exhausted") if legacy
             else ControllerActionBudgetExhausted(maximum_actions=3, attempted_actions=3))
    error.battle_runtime_diagnostic = BattleRuntimeDiagnostic(
        "policy" if fault == "phase" else "entry", 0,
        int(fault == "recording"), {} if fault == "selection" else None, (), (),
    )
    if fault == "extra_event":
        log.emit(dict(event="decision_started"))
    log.fail(error)
    if fault == "outcome":
        (directory / "outcome.json").write_text("{}")
    if fault == "initial":
        (directory / "initial.state").write_bytes(b"partial-capture")
    kwargs = dict(
        terminal_state_sha256="0" * 64 if fault == "terminal" else terminal,
        error_type=type(error).__name__,
    )
    checkpoint = (history.checkpoint_after_legacy_action_budget_stop if legacy
                  else history.checkpoint_after_budget_stop)
    if legacy:
        kwargs["error"] = "other RuntimeError" if fault == "message" else str(error)
    elif fault == "message":
        kwargs["error_type"] = "RuntimeError"
    if fault:
        with pytest.raises(ValueError):
            checkpoint(**kwargs)
    else:
        latest, receipt = checkpoint(**kwargs)
        assert latest == previous and len(history.receipts) == 1
        assert receipt["capture_stage"] == "before_initial_capture"
        assert receipt["manifest_sha256"] is receipt["outcome"] is None
        assert receipt["fresh_inference"] is False
        with pytest.raises(ValueError):
            history()  # normal fresh inference still refuses the newest failure


@pytest.mark.parametrize("fault", [None, "identity", "terminal", "win", "outcome", "not_budget",
                                   "message"])
@pytest.mark.parametrize(
    "stop", ["budget", "aggregate_frame", "execution", "protected", "interrupt"]
)
def test_censored_checkpoint_keeps_prefix_but_never_infers_unfinished_outcome(
    tmp_path, fault, stop
):
    from pokemon_red_completion.battle_recovery import ProtectedRecoveryError
    from pokemon_red_completion.battle_runtime import BattleRuntimeError
    from pokemon_red_completion.executor import (
        ControllerFrameBudgetError,
        ControllerWallTimeBudgetExhausted,
    )

    b = battler(tmp_path)
    history = NativeBattlerHistory(b)
    publish(b)
    previous = history()
    b.calls += 1
    directory = b.output / f"battle-{b.calls:04d}"
    directory.mkdir()
    (directory / "initial.state").write_bytes(b"initial")
    (directory / "initial.state.json").write_bytes(
        build_battle_scenario_capture_payload(
            capture_id=f"player-trainer-{b.calls:04d}",
            root_lineage_id=b.root_lineage_id,
            partition=b.source_partition,
            state_bytes=b"initial",
            initial_observation_sha256="c" * 64,
            source_commit=b.source_commit,
            expected_map=1,
            expected_battle_state=1,
            source_state_sha256=b.source_state_sha256,
        )
    )
    terminal = sha256(b"partial").hexdigest()
    (directory / "final.state").write_bytes(b"partial")
    endpoint = dict(
        final_state_sha256=terminal,
        outcome_sha256=None,
        model_sha256="f" * 64 if fault == "identity" else b.model_sha256,
        qualification_sha256=b.qualification_sha256,
        actor_returned_win=fault == "win",
        outer_goal_verification_required=True,
    )
    (directory / "endpoint.json").write_text(json.dumps(endpoint))
    log = TrainerPracticeEventLog(
        directory / "events",
        run_identity=dict(
            model_sha256=b.model_sha256,
            qualification_sha256=b.qualification_sha256,
            source_commit=b.source_commit,
            root_lineage_id=b.root_lineage_id,
            parent_state_sha256=b.source_state_sha256,
        ),
    )
    error = (
        ControllerWallTimeBudgetExhausted(maximum_wall_seconds=1, elapsed_seconds=1.1)
        if stop == "budget"
        else ControllerFrameBudgetError("controller exhausted its hard frame budget")
        if stop == "aggregate_frame"
        else KeyboardInterrupt()
        if stop == "interrupt"
        else ProtectedRecoveryError("retained protected execution failure")
        if stop == "protected"
        else BattleRuntimeError("retained execution failure")
    )
    log.fail(error)
    if fault == "outcome":
        (directory / "outcome.json").write_text("{}")
    kwargs = dict(
        terminal_state_sha256="0" * 64 if fault == "terminal" else terminal,
        error_type="RuntimeError" if fault == "not_budget" else type(error).__name__,
    )
    if stop == "aggregate_frame":
        kwargs["error"] = str(error)
    if fault == "message":
        kwargs["error_type"] = "ControllerFrameBudgetError"
        if stop in {"budget", "aggregate_frame"}:
            kwargs["error"] = "controller frame_count is invalid"
    checkpoint = (
        history.checkpoint_after_budget_stop
        if stop in {"budget", "aggregate_frame"}
        else history.checkpoint_after_execution_failure
    )
    if fault:
        with pytest.raises(ValueError):
            checkpoint(**kwargs)
    else:
        latest, receipt = checkpoint(**kwargs)
        assert latest == previous and len(history.receipts) == 1
        assert receipt["outcome"] is None and receipt["fresh_inference"] is False
        with pytest.raises(FileNotFoundError):
            history()


@pytest.mark.parametrize(
    "field,value",
    [
        ("source_commit", "d" * 40),
        ("source_state_sha256", "e" * 64),
        ("root_lineage_id", "other-root"),
        ("model_sha256", "f" * 64),
        ("qualification_sha256", "1" * 64),
        ("train_funding_diagnostic", True),
        ("pp_depleted_switch_screen", True),
        ("calls", -1),
        ("calls", True),
    ],
)
def test_live_identity_cannot_be_swapped(tmp_path, field, value):
    b = battler(tmp_path)
    history = NativeBattlerHistory(b)
    setattr(b, field, value)
    with pytest.raises(ValueError, match="identity or sequence"):
        history()


@pytest.mark.parametrize(
    "name",
    ["outcome.json", "final.state", "endpoint.json", "initial.state", "events/event-00001.json"],
)
def test_bound_evidence_tamper_is_rejected(tmp_path, name):
    b = battler(tmp_path)
    history = NativeBattlerHistory(b)
    directory = publish(b)
    history()
    (directory / name).write_bytes(b"invalid")
    with pytest.raises(ValueError):
        history()


def test_changed_but_self_consistent_previous_receipt_is_rejected(tmp_path):
    b = battler(tmp_path)
    history = NativeBattlerHistory(b)
    directory = publish(b, failed=True)
    history()
    row = json.loads((directory / "outcome.json").read_bytes())
    row["stop_reason"] = "decision_cap"
    (directory / "outcome.json").write_text(json.dumps(row))
    endpoint = json.loads((directory / "endpoint.json").read_bytes())
    endpoint["outcome_sha256"] = canonical_sha256(row)
    (directory / "endpoint.json").write_text(json.dumps(endpoint))
    with pytest.raises(ValueError, match="previously observed"):
        history()


def test_provider_must_bind_before_first_battle(tmp_path):
    b = battler(tmp_path)
    publish(b)
    with pytest.raises(ValueError, match="fresh live battler"):
        NativeBattlerHistory(b)


def test_declared_league_adapter_screen_matches_execution_scope(tmp_path):
    class DeclaredLeagueBattler(FrozenTrainerBattler):
        def pp_reentry_screen_active(self, authority):
            if authority == "frozen-k-league-development":
                return super().pp_reentry_screen_active("frozen-k-story-development")
            return super().pp_reentry_screen_active(authority)

    b = DeclaredLeagueBattler(None, None, tmp_path, "a" * 40, "live-root", "b" * 64, {})
    b.model_sha256, b.qualification_sha256 = FROZEN_K_SHA256, K_QUALIFICATION_SHA256
    b.pp_depleted_switch_screen = True
    history = NativeBattlerHistory(b)
    publish(
        b,
        failed=True,
        extra_identity={
            "authority": "frozen-k-league-development",
            "pp_depleted_switch_screen": True,
            "source_partition": "development",
            "fit_allowed": False,
        },
    )
    assert history().result is BattleResult.LOST
    assert len(history.receipts) == 1


@pytest.mark.parametrize("authority", ["frozen-k-league-development", "unscoped"])
def test_base_battler_does_not_gain_league_pp_screen_authority(tmp_path, authority):
    b = battler(tmp_path)
    b.model_sha256, b.qualification_sha256 = FROZEN_K_SHA256, K_QUALIFICATION_SHA256
    b.pp_depleted_switch_screen = True
    history = NativeBattlerHistory(b)
    publish(
        b,
        extra_identity={
            "authority": authority,
            "pp_depleted_switch_screen": True,
            "source_partition": "development",
            "fit_allowed": False,
        },
    )
    with pytest.raises(ValueError, match="PP screen scope"):
        history()
