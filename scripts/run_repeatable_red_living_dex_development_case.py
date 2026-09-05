#!/usr/bin/env python3
"""Run the first available bounded Red development case with a view-only dashboard."""

from __future__ import annotations

import argparse
import json
import re
import sys
import sysconfig
import threading
import time
import webbrowser
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

_ACTIVE_RUNTIME = None
if __name__ == "__main__":
    try:
        from pokemon_red_completion.execution_runtime_closure import (
            activate_authenticated_runtime_stage,
        )

        _runtime_parser = argparse.ArgumentParser(add_help=False)
        _runtime_parser.add_argument("--runtime-site-packages", type=Path)
        _runtime_args, _runtime_unknown = _runtime_parser.parse_known_args()
        _runtime_source = _runtime_args.runtime_site_packages or Path(
            sysconfig.get_path("purelib")
        )
        _ACTIVE_RUNTIME = activate_authenticated_runtime_stage(_runtime_source.resolve(strict=True))
    except BaseException:
        print(
            '{"private_path_fields":0,"schema":"pokemon.red.repeatable-living-dex-development-case-failure.v1",'
            '"stage":"runtime_stage_bootstrap","status":"failed_closed"}',
            flush=True,
        )
        raise SystemExit(2) from None

from pokemon_red_completion.claim_first_admission import (  # noqa: E402
    observe_claim_first_pair_availability,
)
from pokemon_red_completion.collection_protocol import (  # noqa: E402
    working_source_bundle_sha256,
)
from pokemon_red_completion.goal_manager_composition_qualification import (  # noqa: E402
    fixed_account_claim_registry_root,
)
from pokemon_red_completion.private_artifacts import (  # noqa: E402
    PrivateArtifactError,
    PrivateArtifactRoot,
    open_private_root,
)
from pokemon_red_completion.progress_dashboard import (  # noqa: E402
    DashboardFrameObserver,
    DashboardState,
    ProgressDashboardServer,
)
from pokemon_red_completion.provenance import (  # noqa: E402
    detect_source_identity,
    require_clean_source,
    require_published_source,
)
from pokemon_red_completion.red_living_dex_causal_invocation import (  # noqa: E402
    RedLivingDexCausalInvocationError,
    authenticate_red_living_dex_current_consumer,
)
from pokemon_red_completion.red_living_dex_claim_first_invocation import (  # noqa: E402
    RedLivingDexCurrentConsumerBinding,
)
from pokemon_red_completion.red_living_dex_clustered_development_execution import (  # noqa: E402
    RedLivingDexClusteredDevelopmentExecutionError,
    execute_red_living_dex_development_assignment,
)
from pokemon_red_completion.red_living_dex_clustered_development_runner import (  # noqa: E402
    RedLivingDexClusteredDevelopmentRunnerError,
    load_red_living_dex_development_selection,
)
from pokemon_red_completion.red_living_dex_development_batch import (  # noqa: E402
    RedLivingDexDevelopmentBatchAssignment,
    RedLivingDexDevelopmentBatchError,
)
from pokemon_red_completion.red_living_dex_development_dashboard import (  # noqa: E402
    red_living_dex_development_dashboard_snapshot,
)
from pokemon_red_completion.red_living_dex_development_input import (  # noqa: E402
    RED_LIVING_DEX_DEVELOPMENT_INPUT_LABELS,
    RedLivingDexDevelopmentInputError,
    load_red_living_dex_development_batch_assignments,
    source_private_storage_is_separate,
)
from pokemon_red_completion.red_living_dex_development_run_ledger import (  # noqa: E402
    RedLivingDexDevelopmentRunLedgerError,
    find_red_living_dex_development_run_terminal,
    retain_red_living_dex_development_run_terminal,
)
from pokemon_red_completion.red_living_dex_development_supplement_reader import (  # noqa: E402
    FROZEN_RED_LIVING_DEX_DEVELOPMENT_SUPPLEMENT,
)
from pokemon_red_completion.red_living_dex_development_supply import (  # noqa: E402
    RedLivingDexDevelopmentSupplyError,
    load_red_living_dex_development_model,
)
from pokemon_red_completion.red_living_dex_production_runtime import (  # noqa: E402
    RedLivingDexProductionRuntimeLimits,
)
from pokemon_red_completion.red_living_dex_setup_recipe import (  # noqa: E402
    RedLivingDexAuthenticatedSetupRoot,
    RedLivingDexSetupEffectMeter,
)

DEFAULT_PORT = 8769
MAXIMUM_CONTROLLER_ACTIONS = 20_000
MAXIMUM_EMULATOR_FRAMES = 2_000_000
RESULT_SCHEMA = "pokemon.red.repeatable-living-dex-development-case-result.v1"
FAILURE_SCHEMA = "pokemon.red.repeatable-living-dex-development-case-failure.v1"


class RepeatableRedLivingDexDevelopmentError(RuntimeError):
    def __init__(self, stage: str) -> None:
        self.stage = stage
        super().__init__(stage)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--private-root", required=True, type=Path)
    parser.add_argument(
        "--development-root",
        action="append",
        required=True,
        metavar="LABEL=STATE",
    )
    parser.add_argument("--rom", required=True, type=Path)
    parser.add_argument("--exact-ci-run", required=True, type=int)
    parser.add_argument("--exact-ci-attempt", default=1, type=int)
    parser.add_argument(
        "--runtime-site-packages",
        type=Path,
        help="reviewed PyBoy dependency closure (defaults to the active environment)",
    )
    parser.add_argument("--port", default=DEFAULT_PORT, type=int)
    parser.add_argument("--no-browser", action="store_true")
    parser.add_argument("--hold-seconds", default=15, type=int)
    return parser


def _parse_roots(values: list[str]) -> dict[str, Path]:
    roots: dict[str, Path] = {}
    try:
        for value in values:
            label, raw_path = value.split("=", 1)
            path = Path(raw_path)
            if (
                label not in RED_LIVING_DEX_DEVELOPMENT_INPUT_LABELS
                or label in roots
                or not path.is_absolute()
            ):
                raise ValueError
            roots[label] = path
    except (AttributeError, TypeError, ValueError):
        raise RepeatableRedLivingDexDevelopmentError("arguments") from None
    if set(roots) != set(RED_LIVING_DEX_DEVELOPMENT_INPUT_LABELS):
        raise RepeatableRedLivingDexDevelopmentError("arguments")
    return roots


def _first_pending(
    store: PrivateArtifactRoot,
    assignments: tuple[RedLivingDexDevelopmentBatchAssignment, ...],
) -> tuple[RedLivingDexDevelopmentBatchAssignment, int, bool]:
    registry = fixed_account_claim_registry_root()
    pending: list[tuple[RedLivingDexDevelopmentBatchAssignment, bool]] = []
    for assignment in assignments:
        selection, _document = load_red_living_dex_development_selection(
            store,
            assignment.ordinal,
            binding=assignment.binding,
        )
        if (
            selection.logical_root_sha256
            != assignment.root.root_consumption_sha256
            or selection.physical_root_sha256 != assignment.root.physical_root_sha256
        ):
            raise RepeatableRedLivingDexDevelopmentError(
                "selected_root_authentication"
            )
        available = observe_claim_first_pair_availability(
            registry,
            selection.logical_root_sha256,
            selection.physical_root_sha256,
        )
        terminal = find_red_living_dex_development_run_terminal(store, assignment)
        if terminal is None:
            pending.append((assignment, not available))
    if not pending:
        raise RepeatableRedLivingDexDevelopmentError("no_available_development_case")
    assignment, recovering = pending[0]
    return assignment, len(pending), recovering


def _root_loader(
    assignment: RedLivingDexDevelopmentBatchAssignment,
):  # type: ignore[no-untyped-def]
    def load(selection: object) -> RedLivingDexAuthenticatedSetupRoot:
        if (
            getattr(selection, "ordinal", None) != assignment.ordinal
            or getattr(selection, "private_plan_sha256", None)
            != assignment.binding.private_plan_sha256
        ):
            raise RedLivingDexDevelopmentBatchError(
                "development runner selected another root"
            )
        return assignment.root

    return load


class _LiveTimeline:
    def __init__(
        self,
        state: DashboardState,
        meter: RedLivingDexSetupEffectMeter,
        *,
        model_sha256: str,
        ready_cases: int,
    ) -> None:
        self._state = state
        self._meter = meter
        self._model_sha256 = model_sha256
        self._ready_cases = ready_cases
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)

    def __enter__(self) -> _LiveTimeline:
        self._thread.start()
        return self

    def __exit__(self, *_args: object) -> None:
        self._stop.set()
        self._thread.join(timeout=2)

    def _run(self) -> None:
        while not self._stop.wait(0.25):
            checkpoint = self._meter.checkpoint()
            if checkpoint.provider_executions:
                stage = "Executing selected deterministic skill"
                message = (
                    "The model-selected semantic option is under bounded controller execution."
                )
            elif checkpoint.controller_actions:
                stage = "Constructing authenticated Red situation"
                message = "Deterministic setup is running; the teacher remains unavailable."
            elif checkpoint.root_claims:
                stage = "Root claimed durably"
                message = "Recovery identity is durable before any controller input."
            else:
                stage = "Opening one bounded development case"
                message = "Authenticating the fixed-order case before emulator construction."
            self._state.publish(
                red_living_dex_development_dashboard_snapshot(
                    checkpoint=checkpoint,
                    model_sha256=self._model_sha256,
                    stage=stage,
                    message=message,
                    run_status="running",
                    ready_cases=self._ready_cases,
                    events=(
                        "Five-case input catalog authenticated",
                        "First available case selected in frozen order",
                        "Hard action and frame bounds active",
                        "Teacher and fitting interfaces unavailable",
                    ),
                )
            )


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if (
        not args.private_root.is_absolute()
        or not args.rom.is_absolute()
        or args.exact_ci_run <= 0
        or args.exact_ci_attempt <= 0
        or not 1 <= args.port <= 65_535
        or args.hold_seconds < 0
    ):
        raise RepeatableRedLivingDexDevelopmentError("arguments")
    roots = _parse_roots(args.development_root)
    meter = RedLivingDexSetupEffectMeter()
    model_sha256 = FROZEN_RED_LIVING_DEX_DEVELOPMENT_SUPPLEMENT.model_sha256
    state = DashboardState(
        red_living_dex_development_dashboard_snapshot(
            checkpoint=meter.checkpoint(),
            model_sha256=model_sha256,
            stage="Readiness",
            message="Waiting to authenticate the five development cases.",
            run_status="waiting",
            ready_cases=0,
            events=("No ROM, prediction, claim or controller input opened",),
        )
    )
    with ProgressDashboardServer(state, port=args.port) as dashboard:
        _emit(
            {
                "schema": "pokemon.red.repeatable-living-dex-development-dashboard.v1",
                "status": "ready",
                "url": dashboard.url,
                "view_only": True,
            }
        )
        if not args.no_browser:
            webbrowser.open(dashboard.url)
        stage = "source_private_storage_separation"
        receipt = None
        ready_cases = 0
        try:
            if not source_private_storage_is_separate(PROJECT_ROOT, args.private_root):
                raise RepeatableRedLivingDexDevelopmentError(stage)
            stage = "current_source_authentication"
            source = detect_source_identity(PROJECT_ROOT)
            require_clean_source(source)
            require_published_source(PROJECT_ROOT, source)
            if not source.git_commit or re.fullmatch(r"[0-9a-f]{40}", source.git_commit) is None:
                raise RepeatableRedLivingDexDevelopmentError(stage)
            consumer = authenticate_red_living_dex_current_consumer(
                PROJECT_ROOT,
                RedLivingDexCurrentConsumerBinding(
                    source_commit=source.git_commit,
                    source_bundle_sha256=working_source_bundle_sha256(PROJECT_ROOT),
                    exact_ci_run=args.exact_ci_run,
                    exact_ci_attempt=args.exact_ci_attempt,
                ),
            )
            stage = "private_root_authentication"
            store = open_private_root(args.private_root, repository_root=PROJECT_ROOT)
            stage = "selected_root_authentication"
            assignments = load_red_living_dex_development_batch_assignments(
                store,
                private_root=args.private_root,
                roots=roots,
            )
            assignment, ready_cases, recovering = _first_pending(store, assignments)
            stage = "development_model_authentication"
            model_record = load_red_living_dex_development_model(
                store,
                expected_model_sha256=model_sha256,
                expected_model_record_sha256=(
                    FROZEN_RED_LIVING_DEX_DEVELOPMENT_SUPPLEMENT.model_record_sha256
                ),
            )
            state.publish(
                red_living_dex_development_dashboard_snapshot(
                    checkpoint=meter.checkpoint(),
                    model_sha256=model_sha256,
                    stage="Ready for bounded execution",
                    message=(
                        f"{ready_cases} development cases remain; "
                        + (
                            "recovering the first incomplete terminal."
                            if recovering
                            else "opening the first unclaimed case."
                        )
                    ),
                    run_status="running",
                    ready_cases=ready_cases,
                    events=(
                        "Current published source and green CI authenticated",
                        "Private model and all five root pairs authenticated",
                        "Fixed prospective case order retained",
                    ),
                )
            )
            stage = "bounded_development_execution"
            with _LiveTimeline(
                state,
                meter,
                model_sha256=model_sha256,
                ready_cases=ready_cases,
            ):
                receipt = execute_red_living_dex_development_assignment(
                    PROJECT_ROOT,
                    store,
                    consumer=consumer,
                    ordinal=assignment.ordinal,
                    root_loader=_root_loader(assignment),
                    rom_path=args.rom,
                    meter=meter,
                    model_record=model_record,
                    expected_model_sha256=model_sha256,
                    expected_model_record_sha256=(
                        FROZEN_RED_LIVING_DEX_DEVELOPMENT_SUPPLEMENT.model_record_sha256
                    ),
                    binding=assignment.binding,
                    runtime_limits=RedLivingDexProductionRuntimeLimits(
                        maximum_controller_actions=MAXIMUM_CONTROLLER_ACTIONS,
                        maximum_emulator_frames=MAXIMUM_EMULATOR_FRAMES,
                    ),
                    frame_observer=DashboardFrameObserver(state, maximum_fps=12),
                )
                retain_red_living_dex_development_run_terminal(
                    store,
                    assignment,
                    receipt,
                )
        except BaseException as error:
            checkpoint = meter.checkpoint()
            interrupted = isinstance(error, (KeyboardInterrupt, SystemExit))
            failure_stage = (
                error.stage
                if isinstance(error, RedLivingDexCausalInvocationError)
                else stage
            )
            state.publish(
                red_living_dex_development_dashboard_snapshot(
                    checkpoint=checkpoint,
                    model_sha256=model_sha256,
                    stage="Interrupted" if interrupted else "Failed closed",
                    message=(
                        "The case stopped after controller release; recovery may only "
                        "retain its durable terminal."
                        if interrupted and checkpoint.controller_actions
                        else "The bounded case stopped without retry or fallback."
                    ),
                    run_status="paused" if interrupted else "failed",
                    ready_cases=ready_cases,
                    events=(
                        "No teacher fallback used",
                        "No model fitting or training target emitted",
                        "Exact case may not retry after controller input",
                    ),
                )
            )
            _emit(
                {
                    "controller_actions": checkpoint.controller_actions,
                    "emulator_frames": checkpoint.emulator_frames,
                    "exception_type": type(error).__name__,
                    "model_fits": checkpoint.model_fits,
                    "private_path_fields": 0,
                    "schema": FAILURE_SCHEMA,
                    "stage": failure_stage,
                    "status": "interrupted" if interrupted else "failed_closed",
                    "teacher_queries": checkpoint.teacher_queries,
                    "training_targets_emitted": 0,
                }
            )
            _hold(args.hold_seconds)
            return 130 if interrupted else 2
        assert receipt is not None
        checkpoint = meter.checkpoint()
        result = receipt.public_dict()
        model_reached = receipt.development is not None
        state.publish(
            red_living_dex_development_dashboard_snapshot(
                checkpoint=checkpoint,
                model_sha256=model_sha256,
                stage=(
                    "Model-selected terminal retained"
                    if model_reached
                    else "Setup terminal retained"
                ),
                message=(
                    "One bounded model-selected Red case reached a durable factual terminal."
                    if model_reached
                    else "The case retained a typed setup terminal before model scoring."
                ),
                run_status="passed" if model_reached else "blocked",
                ready_cases=ready_cases,
                receipt=receipt,
                events=(
                    (
                        "Model decision committed before controller release"
                        if model_reached
                        else "Setup terminal retained without a model prediction"
                    ),
                    (
                        "Only the selected deterministic skill could execute"
                        if model_reached
                        else "No model-selected skill executed"
                    ),
                    "Factual terminal retained outside the training set",
                    "Stopped after one terminal case for reorientation",
                ),
            )
        )
        _emit(
            {
                "case": result,
                "controller_actions": checkpoint.controller_actions,
                "development_outcomes_opened": int(model_reached),
                "emulator_frames": checkpoint.emulator_frames,
                "model_fits": 0,
                "model_predictions": int(model_reached),
                "private_identity_fields": 0,
                "private_path_fields": 0,
                "ready_cases_before_execution": ready_cases,
                "schema": RESULT_SCHEMA,
                "status": "one_terminal_development_case_retained",
                "teacher_queries": checkpoint.teacher_queries,
                "training_targets_emitted": 0,
            }
        )
        _hold(args.hold_seconds)
        return 0


def _emit(value: dict[str, object]) -> None:
    print(
        json.dumps(
            value,
            allow_nan=False,
            ensure_ascii=True,
            separators=(",", ":"),
            sort_keys=True,
        ),
        flush=True,
    )


def _hold(seconds: int) -> None:
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        try:
            time.sleep(min(0.25, deadline - time.monotonic()))
        except KeyboardInterrupt:
            break


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (PrivateArtifactError, RedLivingDexClusteredDevelopmentRunnerError):
        _emit(
            {
                "private_path_fields": 0,
                "schema": FAILURE_SCHEMA,
                "stage": "private_input_authentication",
                "status": "failed_closed",
            }
        )
        raise SystemExit(2) from None
    except (
        RedLivingDexClusteredDevelopmentExecutionError,
        RedLivingDexDevelopmentBatchError,
        RedLivingDexDevelopmentInputError,
        RedLivingDexDevelopmentRunLedgerError,
        RedLivingDexDevelopmentSupplyError,
        RepeatableRedLivingDexDevelopmentError,
    ) as error:
        _emit(
            {
                "private_path_fields": 0,
                "schema": FAILURE_SCHEMA,
                "stage": getattr(error, "stage", "development_execution"),
                "status": "failed_closed",
            }
        )
        raise SystemExit(2) from None
    finally:
        if _ACTIVE_RUNTIME is not None:
            _ACTIVE_RUNTIME.close()
