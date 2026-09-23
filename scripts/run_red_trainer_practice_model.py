"""Run one hash-bound three-head battle policy with durable decision telemetry.

TRAIN runs are curriculum evidence. DEVELOPMENT runs are comparisons only; this
script never fits, promotes, relabels, or opens TEST captures.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from collections.abc import Callable, Mapping
from contextlib import contextmanager, suppress
from pathlib import Path
from time import monotonic

from pokemon_red_completion.battle_control_model import BattleControlMLP
from pokemon_red_completion.battle_neural_model import MaskedMLPMoveRanker
from pokemon_red_completion.battle_scenario_capture import (
    OBSERVATION_SCHEMA_V2,
    open_battle_scenario_capture,
)
from pokemon_red_completion.battle_switch_target_model import BattleSwitchTargetMLP
from pokemon_red_completion.emulator import PyBoyAdapter
from pokemon_red_completion.executor import (
    ControllerActionBudgetExhausted,
    ControllerActionLimiter,
    ControllerWallTimeBudgetExhausted,
    FrameBudgetController,
    FrameSafeExecutor,
    MonotonicWallTimeBudgetController,
)
from pokemon_red_completion.provenance import canonical_sha256
from pokemon_red_completion.red_autonomous_player import _record, _write
from pokemon_red_completion.red_battle_practice_cartridge import RedPracticeCartridge
from pokemon_red_completion.red_trainer_practice_ancestry import trainer_origin_cluster
from pokemon_red_completion.red_trainer_practice_episode import run_red_trainer_practice_episode
from pokemon_red_completion.red_trainer_practice_fit import TrainerPracticeThreeHeadModel
from pokemon_red_completion.red_trainer_practice_log import (
    TrainerPracticeEventLog,
    verify_trainer_practice_event_log,
)
from pokemon_red_completion.red_trainer_practice_outcome_policy import (
    RedTrainerPracticeOutcomePolicy,
)
from pokemon_red_completion.red_trainer_practice_policy import RedTrainerPracticeModelPolicy
from pokemon_red_completion.scenario_lab import ScenarioPartition

ROOT = Path(__file__).resolve().parents[1]
SCHEMA = "pokemon.red.trainer-practice-model-plan.v1"
OUTCOME_SCHEMA = "pokemon.red.trainer-practice-outcome-model-plan.v1"
ROM_SHA256 = "5ca7ba01642a3b27b0cc0b5349b52792795b62d3ed977e98a09390659af96b7b"


def _budget_failure(error: BaseException):
    """Find an actual budget exception even when executor cleanup replaced it.

    Inspect exception objects, never message text. Explicit causes and implicit
    cleanup contexts can both retain the original stop; guard against cycles.
    The caller still propagates the outer exception unchanged.
    """
    pending = [error]
    seen: set[int] = set()
    while pending:
        current = pending.pop()
        if id(current) in seen:
            continue
        seen.add(id(current))
        if isinstance(
            current, (ControllerActionBudgetExhausted, ControllerWallTimeBudgetExhausted)
        ):
            return current
        if current.__context__ is not None:
            pending.append(current.__context__)
        if current.__cause__ is not None:
            pending.append(current.__cause__)
    return None


@contextmanager
def retained_session(
    emulator,
    *,
    maximum_frames: int,
    output: Path,
    maximum_controller_actions: int | None = None,
    maximum_wall_seconds: int | None = None,
    monotonic_clock: Callable[[], float] = monotonic,
    action_metadata: Callable[[], Mapping[str, object]] | None = None,
    retention_metadata: dict[str, object] | None = None,
):
    """Export the actual endpoint before emulator close, including failed episodes.

    This snapshot alone is NOT a successful or continuation-qualified outcome.
    A normal episode report must bind it before downstream use.
    """
    if (maximum_controller_actions is None) != (maximum_wall_seconds is None):
        raise ValueError("trainer action and wall budgets must be paired")
    framed_session = FrameBudgetController(emulator, maximum_frames=maximum_frames)
    session = (
        MonotonicWallTimeBudgetController(
            framed_session,
            maximum_wall_seconds=maximum_wall_seconds,
            monotonic_clock=monotonic_clock,
        )
        if maximum_wall_seconds is not None
        else framed_session
    )
    returned = False
    try:
        yield session
        returned = True
    finally:
        pressed_before_cleanup = sorted(session.pressed_buttons)
        budget = dict(action_metadata()) if action_metadata is not None else {}
        if maximum_wall_seconds is not None:
            assert isinstance(session, MonotonicWallTimeBudgetController)
            budget.update(
                {
                    "maximum_controller_actions": maximum_controller_actions,
                    "maximum_wall_seconds": maximum_wall_seconds,
                    "controller_action_unit": "attempted_macro_action_dispatch",
                    "wall_time_measurement": (
                        "retained_session_start_through_endpoint_cleanup_inspection"
                    ),
                    "wall_elapsed_seconds": session.elapsed_seconds,
                }
            )
        latest = {
            "frames": session.frame_count,
            "frame_delta": framed_session.frames_executed,
            "pressed_buttons_before_cleanup": pressed_before_cleanup,
            **budget,
        }
        if retention_metadata is not None:
            retention_metadata.update(latest)
        try:
            for button in pressed_before_cleanup:
                session.release(button)
            payload = session.save_state_bytes()
            if not isinstance(payload, bytes) or not payload:
                raise ValueError("trainer endpoint snapshot is empty")
            # Never replace an endpoint from a previous invocation.
            _write(output / "final.state", payload)
            _record(
                output / "final-state.json",
                {
                    "schema": "pokemon.red.trainer-endpoint.v1",
                    "state_sha256": hashlib.sha256(payload).hexdigest(),
                    "byte_count": len(payload),
                    "frames": session.frame_count,
                    "frame_delta": framed_session.frames_executed,
                    "episode_returned": returned,
                    "pressed_buttons": sorted(session.pressed_buttons),
                    "pressed_buttons_before_cleanup": pressed_before_cleanup,
                    "continuation_qualified": False,
                    **budget,
                },
            )
        finally:
            # Cleanup can partly succeed before release/save/receipt fails. Keep
            # obtainable input state without requiring a persisted endpoint, and
            # never replace the primary failure if inspection itself is unavailable.
            if retention_metadata is not None:
                with suppress(Exception):
                    retention_metadata["pressed_buttons"] = sorted(session.pressed_buttons)


def _bound_file(value: object, label: str) -> bytes:
    if not isinstance(value, dict) or set(value) != {"path", "sha256"}:
        raise ValueError(f"{label} binding differs")
    path, digest = value["path"], value["sha256"]
    if not isinstance(path, str) or not isinstance(digest, str):
        raise ValueError(f"{label} identity differs")
    payload = Path(path).read_bytes()
    if hashlib.sha256(payload).hexdigest() != digest:
        raise ValueError(f"{label} hash differs")
    return payload


def _authenticate(plan: object):
    if not isinstance(plan, dict) or plan.get("schema") not in {SCHEMA, OUTCOME_SCHEMA}:
        raise ValueError("trainer model plan differs")
    _runtime_budgets(plan)
    if subprocess.check_output(["git", "status", "--porcelain"], cwd=ROOT).strip():
        raise ValueError("commit trainer model code before running it")
    revision = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT).decode().strip()
    if plan.get("source_commit") != revision:
        raise ValueError("trainer model source commit differs")
    rom = _bound_file(plan.get("rom"), "ROM")
    if hashlib.sha256(rom).hexdigest() != ROM_SHA256:
        raise ValueError("trainer model Red ROM differs")
    model: (
        TrainerPracticeThreeHeadModel
        | tuple[MaskedMLPMoveRanker, BattleControlMLP, BattleSwitchTargetMLP]
    )
    if plan["schema"] == OUTCOME_SCHEMA:
        model = TrainerPracticeThreeHeadModel.from_dict(
            json.loads(_bound_file(plan.get("outcome_model"), "outcome model"))
        )
    else:
        model = (
            MaskedMLPMoveRanker.from_dict(
                json.loads(_bound_file(plan.get("move_model"), "move model"))
            ),
            BattleControlMLP.from_dict(
                json.loads(_bound_file(plan.get("control_model"), "control model"))
            ),
            BattleSwitchTargetMLP.from_dict(
                json.loads(_bound_file(plan.get("switch_model"), "switch model"))
            ),
        )
    state, manifest = plan.get("capture_state"), plan.get("capture_manifest")
    _bound_file(state, "capture state")
    _bound_file(manifest, "capture manifest")
    assert isinstance(state, dict) and isinstance(manifest, dict)
    capture = open_battle_scenario_capture(Path(state["path"]), Path(manifest["path"]))
    if capture.manifest.partition not in {ScenarioPartition.TRAIN, ScenarioPartition.DEVELOPMENT}:
        raise ValueError("trainer model capture partition is unavailable")
    if (
        plan["schema"] == OUTCOME_SCHEMA
        and capture.manifest.observation_schema != OBSERVATION_SCHEMA_V2
    ):
        raise ValueError("outcome model requires actor-visible battle stats")
    if (
        isinstance(model, TrainerPracticeThreeHeadModel)
        and capture.manifest.partition is ScenarioPartition.DEVELOPMENT
        and trainer_origin_cluster(capture.manifest.root_lineage_id)
        in {trainer_origin_cluster(root) for root in model.train_root_ids}
    ):
        raise ValueError("DEVELOPMENT root overlaps outcome-model training lineage")
    max_decisions, maximum_frames = plan.get("max_decisions"), plan.get("maximum_frames")
    opening_idle_frames = plan.get("opening_idle_frames", 0)
    # Complete TRAIN team fights need room for attacks, prompts and replacements.
    # DEVELOPMENT retains its existing shorter promotion/evaluation boundary.
    decision_cap, frame_cap = (
        (160, 240000) if capture.manifest.partition is ScenarioPartition.TRAIN else (80, 120000)
    )
    if (
        type(max_decisions) is not int
        or not 1 <= max_decisions <= decision_cap
        or type(maximum_frames) is not int
        or not 1 <= maximum_frames <= frame_cap
        or type(opening_idle_frames) is not int
        or not 0 <= opening_idle_frames <= 12
    ):
        raise ValueError("trainer model budget differs")
    output = plan.get("output")
    if not isinstance(output, str) or Path(output).exists():
        raise ValueError("trainer model output must be new")
    return plan, capture, model


def _runtime_budgets(plan: Mapping[str, object]) -> tuple[int, int] | None:
    """Validate the optional pair before artifact reads or output creation."""

    has_actions = "maximum_controller_actions" in plan
    has_wall = "maximum_wall_seconds" in plan
    if not has_actions and not has_wall:
        return None
    actions = plan.get("maximum_controller_actions")
    seconds = plan.get("maximum_wall_seconds")
    if (
        not has_actions
        or not has_wall
        or type(actions) is not int  # noqa: E721
        or not 1 <= actions <= 5000
        or type(seconds) is not int  # noqa: E721
        or not 1 <= seconds <= 180
    ):
        raise ValueError("trainer model action and wall budgets differ")
    return actions, seconds


def run(
    plan_path: Path,
    *,
    check_only: bool = False,
    monotonic_clock: Callable[[], float] = monotonic,
) -> dict[str, object]:
    plan, capture, model = _authenticate(json.loads(plan_path.read_bytes()))
    runtime_budgets = _runtime_budgets(plan)
    if check_only:
        return {
            "status": "action_free_trainer_model_preflight_passed",
            "capture_id": capture.manifest.capture_id,
            "partition": capture.manifest.partition.value,
            "controller_actions": 0,
            "emulator_frames": 0,
            "persistent_artifacts": 0,
        }
    rom = plan["rom"]
    assert isinstance(rom, dict) and isinstance(rom["path"], str)
    maximum_frames = plan["maximum_frames"]
    max_decisions = plan["max_decisions"]
    opening_idle_frames = plan.get("opening_idle_frames", 0)
    assert isinstance(maximum_frames, int) and isinstance(max_decisions, int)
    assert isinstance(opening_idle_frames, int)

    active_session: dict[str, object] = {}
    active_limiter: dict[str, ControllerActionLimiter] = {}
    retention_metadata: dict[str, object] = {}

    def action_metadata() -> dict[str, object]:
        limiter = active_limiter.get("limiter")
        return {
            "controller_actions_attempted": (
                0 if limiter is None else limiter.attempted_actions
            ),
            "controller_actions_completed": (
                0 if limiter is None else limiter.completed_actions
            ),
        }

    class BoundEpisodeActionExecutor:
        def execute(self, action):
            session = active_session.get("session")
            if session is None:
                raise RuntimeError("trainer action executor has no retained session")
            limiter = active_limiter.get("limiter")
            if limiter is None:
                assert runtime_budgets is not None
                maximum_actions, _maximum_seconds = runtime_budgets
                admit = session.check_wall_time_budget
                limiter = ControllerActionLimiter(
                    FrameSafeExecutor(session),
                    maximum_actions=maximum_actions,
                    admit_action=admit,
                )
                active_limiter["limiter"] = limiter
            return limiter.execute(action)

    @contextmanager
    def session_factory():
        maximum_actions = runtime_budgets[0] if runtime_budgets is not None else None
        maximum_seconds = runtime_budgets[1] if runtime_budgets is not None else None
        with (
            PyBoyAdapter(Path(rom["path"]), watch=False, speed=None) as emulator,
            retained_session(
                emulator,
                maximum_frames=maximum_frames,
                output=output,
                maximum_controller_actions=maximum_actions,
                maximum_wall_seconds=maximum_seconds,
                monotonic_clock=monotonic_clock,
                action_metadata=action_metadata if runtime_budgets is not None else None,
                retention_metadata=retention_metadata if runtime_budgets is not None else None,
            ) as session,
        ):
            active_session["session"] = session
            try:
                yield session
                if runtime_budgets is not None:
                    session.check_wall_time_budget()
            finally:
                active_session.pop("session", None)

    policy: RedTrainerPracticeOutcomePolicy | RedTrainerPracticeModelPolicy
    if isinstance(model, TrainerPracticeThreeHeadModel):
        policy = RedTrainerPracticeOutcomePolicy(
            policy_id="three-head-whole-party-outcome-model",
            battle_plan_id=capture.manifest.capture_id,
            model=model,
        )
        model_identity = {"outcome_model_sha256": plan["outcome_model"]["sha256"]}
        public_stats = RedPracticeCartridge(_bound_file(plan["rom"], "ROM")).public_base_stats
    else:
        move_model, control_model, switch_model = model
        policy = RedTrainerPracticeModelPolicy(
            policy_id="three-head-attack-switch-model",
            battle_plan_id=capture.manifest.capture_id,
            move_model=move_model,
            control_model=control_model,
            switch_model=switch_model,
        )
        model_identity = {
            "move_model_sha256": plan["move_model"]["sha256"],
            "control_model_sha256": plan["control_model"]["sha256"],
            "switch_model_sha256": plan["switch_model"]["sha256"],
        }
        public_stats = None
    output_path = plan["output"]
    assert isinstance(output_path, str)
    output = Path(output_path)
    output.mkdir(mode=0o700, parents=True, exist_ok=False)
    budget_identity = (
        {}
        if runtime_budgets is None
        else {
            "maximum_controller_actions": runtime_budgets[0],
            "maximum_wall_seconds": runtime_budgets[1],
            "controller_action_unit": "attempted_macro_action_dispatch",
        }
    )
    _record(
        output / "execution-started.json",
        {
            "source_commit": plan["source_commit"],
            "capture_manifest_sha256": capture.manifest_sha256,
            "policy_id": policy.policy_id,
            "partition": capture.manifest.partition.value,
            "opening_idle_frames": opening_idle_frames,
            **budget_identity,
        },
    )
    log = TrainerPracticeEventLog(
        output / "events",
        run_identity={
            "source_commit": plan["source_commit"],
            "capture_id": capture.manifest.capture_id,
            "root_lineage_id": capture.manifest.root_lineage_id,
            "partition": capture.manifest.partition.value,
            "capture_manifest_sha256": capture.manifest_sha256,
            "policy_id": policy.policy_id,
            **model_identity,
            "max_decisions": max_decisions,
            "maximum_frames": maximum_frames,
            "opening_idle_frames": opening_idle_frames,
            **budget_identity,
        },
    )
    try:
        episode = run_red_trainer_practice_episode(
            capture,
            session_factory=session_factory,
            policy=policy,
            max_decisions=max_decisions,
            opening_idle_frames=opening_idle_frames,
            event_sink=log.emit,
            public_species_base_stats=public_stats,
            action_executor=(BoundEpisodeActionExecutor() if runtime_budgets is not None else None),
            decision_guard=(
                (lambda _raw: active_session["session"].check_wall_time_budget())
                if runtime_budgets is not None
                else None
            ),
        )
        endpoint = json.loads((output / "final-state.json").read_bytes())
        if endpoint["episode_returned"] is not True or endpoint["pressed_buttons"]:
            raise ValueError("trainer endpoint is not released and normally returned")
    except Exception as error:
        budget_error = _budget_failure(error)
        is_budget_failure = isinstance(
            budget_error,
            (ControllerActionBudgetExhausted, ControllerWallTimeBudgetExhausted),
        )
        budget_reason = (
            "controller_action_budget_exhausted"
            if isinstance(budget_error, ControllerActionBudgetExhausted)
            else "controller_wall_time_budget_exhausted"
            if isinstance(budget_error, ControllerWallTimeBudgetExhausted)
            else None
        )
        retained_budget = (
            {
                "error_type": type(budget_error).__name__,
                "error_message": str(budget_error),
                "reason": budget_reason,
            }
            if is_budget_failure
            else None
        )
        if retained_budget is not None and budget_error is not error:
            log.emit(
                {
                    "event": "budget_failure_retained",
                    "budget_failure": retained_budget,
                    "secondary_failure": {
                        "error_type": type(error).__name__,
                        "error_message": str(error),
                    },
                    "accounting": retention_metadata,
                }
            )
        log.fail(error)
        endpoint = (
            json.loads((output / "final-state.json").read_bytes())
            if (output / "final-state.json").exists()
            else {}
        )
        reason = budget_reason or "exception"
        _record(
            output / "failure.json",
            {
                "schema": "pokemon.red.trainer-practice-model-failure.v1",
                "error_type": type(error).__name__,
                "error_message": str(error),
                "reason": reason,
                "partition": capture.manifest.partition.value,
                **budget_identity,
                **({"budget_failure": retained_budget} if retained_budget is not None else {}),
                **(
                    {
                        "secondary_failure": {
                            "error_type": type(error).__name__,
                            "error_message": str(error),
                        }
                    }
                    if retained_budget is not None and budget_error is not error
                    else {}
                ),
                **retention_metadata,
                **{
                    key: endpoint[key]
                    for key in (
                        "controller_actions_attempted",
                        "controller_actions_completed",
                        "wall_elapsed_seconds",
                        "frames",
                        "frame_delta",
                        "pressed_buttons",
                        "pressed_buttons_before_cleanup",
                    )
                    if key in endpoint
                },
            },
        )
        _record(
            output / "event-log-verification.json",
            verify_trainer_practice_event_log(log.directory),
        )
        raise
    report = episode.public_dict()
    report.update(
        {
            "partition": capture.manifest.partition.value,
            "root_lineage_id": capture.manifest.root_lineage_id,
            "source_commit": plan["source_commit"],
            "opening_idle_frames": opening_idle_frames,
            **budget_identity,
            **(action_metadata() if runtime_budgets is not None else {}),
            **(
                {"wall_elapsed_seconds": endpoint["wall_elapsed_seconds"]}
                if runtime_budgets is not None
                else {}
            ),
            "model_updates": 0,
            "authority_promotions": 0,
            "final_state_sha256": endpoint["state_sha256"],
            "final_state_receipt_sha256": canonical_sha256(endpoint),
            **model_identity,
        }
    )
    _record(output / "outcome.json", report)
    log.finish(
        {
            "battle_won": episode.battle_won,
            "stop_reason": episode.stop_reason,
            "decision_count": len(episode.decisions),
            "elapsed_ns": episode.elapsed_ns,
            "outcome_sha256": canonical_sha256(report),
        }
    )
    _record(
        output / "event-log-verification.json",
        verify_trainer_practice_event_log(log.directory),
    )
    return {
        "status": "trainer_model_episode_recorded",
        "partition": capture.manifest.partition.value,
        "capture_id": capture.manifest.capture_id,
        "battle_won": episode.battle_won,
        "stop_reason": episode.stop_reason,
        "decision_count": len(episode.decisions),
        "metrics": report["metrics"],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("plan", type=Path)
    parser.add_argument("--check-only", action="store_true")
    args = parser.parse_args()
    print(json.dumps(run(args.plan, check_only=args.check_only), sort_keys=True))


if __name__ == "__main__":
    main()
