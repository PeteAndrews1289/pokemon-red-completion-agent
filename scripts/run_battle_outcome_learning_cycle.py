#!/usr/bin/env python3
"""Run one prospectively frozen Red battle train/development cycle."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
import stat
import sys
from collections.abc import Callable, Iterator, Mapping
from contextlib import ExitStack, contextmanager, suppress
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from pokemon_red_completion.battle_neural_model import MaskedMLPMoveRanker  # noqa: E402
from pokemon_red_completion.battle_outcome_experiment import (  # noqa: E402
    BattleOutcomeCaptureBinding,
    BattleOutcomeExperimentPlan,
    battle_outcome_controller_timing_sha256,
    battle_outcome_distinct_hidden_embedding_count,
    battle_outcome_hidden_menu_sha256,
    battle_outcome_menu_sha256,
    parse_battle_outcome_experiment_plan,
)
from pokemon_red_completion.battle_outcome_learning import (  # noqa: E402
    BattleOutcomeExample,
    BattleOutcomeLearningCycle,
    BattleOutcomePairedEvaluation,
    BattleOutcomeUpdate,
    adapt_mlp_last_layer_from_outcomes,
    compare_battle_outcome_preferences,
    evaluate_battle_outcome_preferences,
)
from pokemon_red_completion.battle_scenario_capture import (  # noqa: E402
    BattleScenarioCapture,
    open_battle_scenario_capture,
)
from pokemon_red_completion.claim_first_admission import (  # noqa: E402
    ClaimFirstRootPair,
    claim_first_pair_registry,
    read_root_pair_claim,
)
from pokemon_red_completion.collection_protocol import (  # noqa: E402
    working_source_bundle_sha256,
)
from pokemon_red_completion.emulator import PyBoyAdapter  # noqa: E402
from pokemon_red_completion.goal_manager_composition_qualification import (  # noqa: E402
    open_fixed_account_claim_registry,
)
from pokemon_red_completion.goal_manager_context_catalog import (  # noqa: E402
    GoalManagerContextCatalog,
    parse_goal_manager_context_catalog,
)
from pokemon_red_completion.goal_manager_development import (  # noqa: E402
    goal_manager_development_numpy_runtime_sha256,
)
from pokemon_red_completion.goal_manager_protocol import (  # noqa: E402
    GoalManagerCollectionRegistry,
    load_committed_goal_manager_registry_at_revision,
)
from pokemon_red_completion.learned_battle_policy import (  # noqa: E402
    load_battle_model_artifact,
)
from pokemon_red_completion.private_artifacts import open_private_root  # noqa: E402
from pokemon_red_completion.provenance import (  # noqa: E402
    canonical_sha256,
    detect_source_identity,
    require_clean_source,
    require_published_source,
)
from pokemon_red_completion.red_battle_outcome_runtime import (  # noqa: E402
    RedBattleOutcomeCollection,
    collect_red_battle_outcome_example,
    prepare_red_battle_outcome_capture,
)
from pokemon_red_completion.red_battle_scenario import (  # noqa: E402
    PreparedRedBattleScenario,
)
from pokemon_red_completion.rom import resolve_rom_path, verify_rom  # noqa: E402
from pokemon_red_completion.runtime_identity import (  # noqa: E402
    build_runtime_identity,
    require_pyboy_import_origins,
)
from pokemon_red_completion.scenario_lab import ScenarioPartition  # noqa: E402


class BattleOutcomeCycleError(RuntimeError):
    """Raised when a bounded cycle crosses its prospective contract."""


RUNNER_PATH = PROJECT_ROOT / "scripts" / "run_battle_outcome_learning_cycle.py"
MATERIALIZER_PATH = PROJECT_ROOT / "scripts" / "materialize_battle_scenario_capture.py"
_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_MAXIMUM_PLAN_BYTES = 128 * 1024
_MAXIMUM_CONTEXT_CATALOG_BYTES = 4 * 1024 * 1024


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rom", type=Path, default=None, help="otherwise POKEMON_RED_ROM")
    parser.add_argument("--private-root", type=Path, required=True)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--expected-plan-sha256", required=True)
    parser.add_argument("--base-model", type=Path, required=True)
    parser.add_argument("--expected-base-model-sha256", required=True)
    parser.add_argument("--context-catalog", type=Path, required=True)
    parser.add_argument("--train-state", type=Path, required=True)
    parser.add_argument("--train-manifest", type=Path, required=True)
    parser.add_argument("--development-state", type=Path, required=True)
    parser.add_argument("--development-manifest", type=Path, required=True)
    return parser


def _run(args: argparse.Namespace) -> dict[str, object]:
    source = detect_source_identity(PROJECT_ROOT, include_untracked=True)
    require_clean_source(source)
    require_published_source(PROJECT_ROOT, source)
    if source.git_commit is None:  # pragma: no cover - clean source establishes this
        raise AssertionError("clean source identity lacks a commit")

    expected_plan_sha256 = _sha256(args.expected_plan_sha256, "experiment plan")
    plan = _read_experiment_plan(args.plan, expected_plan_sha256)
    if plan.source_commit != source.git_commit:
        raise BattleOutcomeCycleError("experiment plan source differs")
    _require_current_plan_files(plan)
    _require_upstream_plan_bindings(plan, args.context_catalog)

    expected_base_sha256 = _sha256(
        args.expected_base_model_sha256,
        "expected base model",
    )
    if expected_base_sha256 != plan.base_model_sha256:
        raise BattleOutcomeCycleError("base model expectation differs from the plan")
    base_model = load_battle_model_artifact(args.base_model)
    if not isinstance(base_model, MaskedMLPMoveRanker):
        raise BattleOutcomeCycleError(
            "bounded outcome adaptation requires the nonlinear prior"
        )
    base_model_sha256 = _model_sha256(base_model)
    if base_model_sha256 != plan.base_model_sha256:
        raise BattleOutcomeCycleError(
            "base model differs from the prospective experiment"
        )

    runtime = build_runtime_identity()
    require_pyboy_import_origins(runtime)
    if runtime.sha256 != plan.runtime_identity_sha256:
        raise BattleOutcomeCycleError(
            "runtime identity differs from the prospective experiment"
        )
    numpy_runtime_sha256 = goal_manager_development_numpy_runtime_sha256()
    if numpy_runtime_sha256 != plan.numpy_runtime_sha256:
        raise BattleOutcomeCycleError(
            "NumPy runtime differs from the prospective experiment"
        )
    if battle_outcome_controller_timing_sha256() != plan.controller_timing_sha256:
        raise BattleOutcomeCycleError(
            "controller timing differs from the prospective experiment"
        )

    rom_path = resolve_rom_path(args.rom)
    rom = verify_rom(rom_path)
    if rom.sha256 != plan.rom_sha256:
        raise BattleOutcomeCycleError("ROM differs from the prospective experiment")

    # Read-only boundary admission is prospective and outcome-blind.  Development
    # actions, predictions, outcomes, and its root claim remain closed until fit.
    train_capture = open_battle_scenario_capture(args.train_state, args.train_manifest)
    development_capture = open_battle_scenario_capture(
        args.development_state,
        args.development_manifest,
    )
    _require_capture_binding(train_capture, plan.train)
    _require_capture_binding(development_capture, plan.development)
    _require_development_capture(
        train_capture,
        development_capture,
        source_commit=source.git_commit,
    )

    def session_factory():  # type: ignore[no-untyped-def]
        return PyBoyAdapter(rom_path)

    train_prepared = prepare_red_battle_outcome_capture(
        train_capture,
        session_factory=session_factory,
    )
    development_prepared = prepare_red_battle_outcome_capture(
        development_capture,
        session_factory=session_factory,
    )
    _require_prepared_binding(plan.train, train_prepared, base_model)
    _require_prepared_binding(plan.development, development_prepared, base_model)

    private_root = open_private_root(args.private_root, repository_root=PROJECT_ROOT)
    claim_registry = open_fixed_account_claim_registry()
    artifact_id = f"bo-cycle-{plan.plan_sha256}"
    train_pair = _root_pair(plan, plan.train, stage="battle-train")
    development_pair = _root_pair(
        plan,
        plan.development,
        stage="battle-development",
    )

    cycle: BattleOutcomeLearningCycle | None = None
    paired_development: dict[str, object] | None = None
    model_sha256: str | None = None
    development_capture_metadata_opened = True
    development_outcomes_opened = 0
    development_prediction_committed = False
    root_claims_created = 0
    progress = {
        "candidate_claims_created": 0,
        "measured_candidate_outcomes": 0,
    }
    activated_candidate_targets = plan.train.supported_candidate_count
    deferred_unactivated_development_candidates = (
        plan.development.supported_candidate_count
    )
    status = "no_update"
    claim = "insufficient_train_preference_signal"
    candidate_advantage_observed = False
    stage = "train_root_claim"
    writer = None
    terminal_record: dict[str, object] | None = None

    try:
        with ExitStack() as attempt:
            with claim_first_pair_registry(claim_registry) as registry:
                if not registry.available(
                    train_pair.logical_root_sha256,
                    train_pair.physical_root_sha256,
                ) or not registry.available(
                    development_pair.logical_root_sha256,
                    development_pair.physical_root_sha256,
                ):
                    raise BattleOutcomeCycleError(
                        "frozen train/development roots are no longer available"
                    )
                retained_train_pair = registry.claim(train_pair)
                root_claims_created = 1
                writer = attempt.enter_context(
                    private_root.begin_artifact(
                        artifact_id,
                        kind="battle_outcome_cycle",
                    )
                )
                attempt.enter_context(
                    _retain_failure_record(
                        writer,
                        plan_sha256=plan.plan_sha256,
                        snapshot=lambda: {
                            "stage": stage,
                            "root_claims_created": root_claims_created,
                            "candidate_claims_created": progress[
                                "candidate_claims_created"
                            ],
                            "measured_candidate_outcomes": (
                                progress["measured_candidate_outcomes"]
                            ),
                        },
                    )
                )
                writer.append(
                    "assignment",
                    _assignment_record(
                        plan,
                        artifact_id=artifact_id,
                        source=source.public_dict(),
                    ),
                    durable=True,
                )
                writer.append(
                    "root_claims",
                    _root_claim_record(
                        retained_train_pair,
                        split=ScenarioPartition.TRAIN,
                        capture=plan.train,
                    ),
                    durable=True,
                )

            if writer is None:  # pragma: no cover - begin_artifact returned above
                raise AssertionError("train claim did not create a private writer")
            active_writer = writer
            _revalidate_after_claim(args.plan, expected_plan_sha256, plan)

            stage = "train_candidates"
            train_collection, _, _ = (
                _collect_claimed_capture(
                    active_writer,
                    plan=plan,
                    capture_binding=plan.train,
                    capture=train_capture,
                    root_pair=retained_train_pair,
                    base_model=base_model,
                    session_factory=session_factory,
                    prepared_boundary=train_prepared,
                    progress_sink=lambda event: _increment_progress(
                        progress,
                        event,
                    ),
                )
            )
            active_writer.append(
                "outcomes",
                _collection_record(train_collection, split=ScenarioPartition.TRAIN),
                durable=True,
            )

            if not train_collection.example.learner_update_eligible:
                active_writer.append(
                    "evaluation",
                    {
                        "record_type": "battle_outcome_no_update",
                        "status": status,
                        "claim": claim,
                        "train_learner_update_eligible": False,
                        "development_root_claimed": False,
                        "development_capture_metadata_opened": (
                            development_capture_metadata_opened
                        ),
                        "development_outcomes_opened": 0,
                        "activated_candidate_targets": activated_candidate_targets,
                        "deferred_unactivated_development_candidates": (
                            deferred_unactivated_development_candidates
                        ),
                        "promotion_gate_passed": False,
                        "model_written": False,
                    },
                    durable=True,
                )
            else:
                stage = "train_fit"
                update = adapt_mlp_last_layer_from_outcomes(
                    base_model,
                    (train_collection.example,),
                    epochs=plan.epochs,
                    learning_rate=plan.learning_rate,
                    prior_l2=plan.prior_l2,
                )
                _require_update_identity(
                    update,
                    plan=plan,
                    train_example=train_collection.example,
                )
                updated_model = update.model
                model_sha256 = _model_sha256(updated_model)
                active_writer.append(
                    "model",
                    {
                        "record_type": "battle_model_candidate",
                        "model": updated_model.to_dict(),
                        "model_sha256": model_sha256,
                        "base_model_sha256": base_model_sha256,
                        "update_report": update.report.public_dict(),
                        "source": source.public_dict(),
                        "authority": "shadow_only",
                        "development_outcomes_opened_before_fit": 0,
                    },
                    durable=True,
                )

                stage = "development_root_claim"
                with claim_first_pair_registry(claim_registry) as registry:
                    if read_root_pair_claim(
                        claim_registry,
                        retained_train_pair.claim_sha256,
                    ) != retained_train_pair:
                        raise BattleOutcomeCycleError("train root claim changed")
                    retained_development_pair = registry.claim(development_pair)
                    root_claims_created = 2
                    activated_candidate_targets += (
                        plan.development.supported_candidate_count
                    )
                    deferred_unactivated_development_candidates = 0
                    active_writer.append(
                        "root_claims",
                        _root_claim_record(
                            retained_development_pair,
                            split=ScenarioPartition.DEVELOPMENT,
                            capture=plan.development,
                        ),
                        durable=True,
                    )

                _revalidate_after_claim(args.plan, expected_plan_sha256, plan)

                stage = "development_commitment"
                base_choice = base_model.predict(
                    development_prepared.features.candidate_vectors,
                    legal_mask=development_prepared.features.legal_mask,
                    current_pp=development_prepared.features.current_pp,
                )
                updated_choice = updated_model.predict(
                    development_prepared.features.candidate_vectors,
                    legal_mask=development_prepared.features.legal_mask,
                    current_pp=development_prepared.features.current_pp,
                )
                active_writer.append(
                    "prediction_commitment",
                    {
                        "record_type": "battle_development_prediction_commitment",
                        "plan_sha256": plan.plan_sha256,
                        "root_pair_claim_sha256": (
                            retained_development_pair.claim_sha256
                        ),
                        "capture_id": development_capture.manifest.capture_id,
                        "manifest_sha256": development_capture.manifest_sha256,
                        "initial_observation_sha256": (
                            development_prepared.initial_observation_sha256
                        ),
                        "base_model_sha256": base_model_sha256,
                        "base_candidate_index": base_choice,
                        "updated_model_sha256": model_sha256,
                        "updated_candidate_index": updated_choice,
                        "development_outcomes_opened": 0,
                    },
                    durable=True,
                )
                development_prediction_committed = True

                stage = "development_candidates"
                development_collection, _, _ = (
                    _collect_claimed_capture(
                        active_writer,
                        plan=plan,
                        capture_binding=plan.development,
                        capture=development_capture,
                        root_pair=retained_development_pair,
                        base_model=base_model,
                        session_factory=session_factory,
                        prepared_boundary=development_prepared,
                        progress_sink=lambda event: _increment_progress(
                            progress,
                            event,
                        ),
                    )
                )
                development_outcomes_opened = len(
                    tuple(
                        outcome
                        for outcome in development_collection.outcomes
                        if outcome is not None
                    )
                )
                _require_committed_development_choices(
                    base_model,
                    updated_model,
                    development_collection.example,
                    base_choice=base_choice,
                    updated_choice=updated_choice,
                )
                active_writer.append(
                    "outcomes",
                    _collection_record(
                        development_collection,
                        split=ScenarioPartition.DEVELOPMENT,
                    ),
                    durable=True,
                )

                stage = "development_evaluation"
                base_development = evaluate_battle_outcome_preferences(
                    base_model,
                    (development_collection.example,),
                )
                updated_development = evaluate_battle_outcome_preferences(
                    updated_model,
                    (development_collection.example,),
                )
                paired = compare_battle_outcome_preferences(
                    base_model,
                    updated_model,
                    (development_collection.example,),
                )
                _require_evaluation_identity(
                    base_development,
                    updated_development,
                    paired,
                    base_model_sha256=base_model_sha256,
                    updated_model_sha256=model_sha256,
                    development_example=development_collection.example,
                    base_choice=base_choice,
                    updated_choice=updated_choice,
                )
                paired_development = paired.public_dict()
                cycle = BattleOutcomeLearningCycle(
                    update=update,
                    base_development=base_development,
                    updated_development=updated_development,
                )
                if paired.discordant_examples == 0:
                    status = "rejected_no_development_discordance"
                    claim = "no_discordant_development_choice"
                elif paired.updated_wins <= paired.base_wins:
                    status = "rejected_no_development_advantage"
                    claim = "candidate_did_not_beat_frozen_prior"
                else:
                    status = "candidate_advantage_observed"
                    claim = "bounded_descriptive_advantage_only"
                    candidate_advantage_observed = True
                active_writer.append(
                    "evaluation",
                    {
                        "record_type": "battle_outcome_learning_cycle",
                        "status": status,
                        "cycle": cycle.public_dict(),
                        "paired_development": paired_development,
                        "claim": claim,
                        "candidate_advantage_observed": (
                            candidate_advantage_observed
                        ),
                        "historically_untouched_claimed": False,
                        "promotion_gate_passed": False,
                        "reason_promotion_false": "independent_sealed_gate_not_run",
                    },
                    durable=True,
                )
            if (
                progress["candidate_claims_created"] != activated_candidate_targets
                or progress["measured_candidate_outcomes"]
                != activated_candidate_targets
            ):
                raise BattleOutcomeCycleError(
                    "activated candidate targets are not completely measured"
                )
            terminal_record = _terminal_record(
                plan=plan,
                status=status,
                cycle=cycle,
                paired_development=paired_development,
                base_model_sha256=base_model_sha256,
                model_sha256=model_sha256,
                claim=claim,
                candidate_advantage_observed=candidate_advantage_observed,
                root_claims_created=root_claims_created,
                candidate_claims_created=progress["candidate_claims_created"],
                measured_candidate_outcomes=progress[
                    "measured_candidate_outcomes"
                ],
                activated_candidate_targets=activated_candidate_targets,
                deferred_unactivated_development_candidates=(
                    deferred_unactivated_development_candidates
                ),
                development_capture_metadata_opened=(
                    development_capture_metadata_opened
                ),
                development_outcomes_opened=development_outcomes_opened,
                development_prediction_committed=(
                    development_prediction_committed
                ),
            )
            active_writer.append("terminal", terminal_record, durable=True)
    except Exception as error:
        raise BattleOutcomeCycleError(
            "battle outcome cycle stopped; the exact plan may not retry; "
            f"failure type {type(error).__name__}"
        ) from error

    if writer is None or terminal_record is None:  # pragma: no cover - established above
        raise AssertionError("battle cycle completed without a private writer")
    public_terminal = dict(terminal_record)
    del public_terminal["record_type"]
    return {
        "schema": "pokemon-red-battle-outcome-cycle-receipt-v4",
        "artifact": writer.summary.public_dict(),
        **public_terminal,
    }


def _terminal_record(
    *,
    plan: BattleOutcomeExperimentPlan,
    status: str,
    cycle: BattleOutcomeLearningCycle | None,
    paired_development: dict[str, object] | None,
    base_model_sha256: str,
    model_sha256: str | None,
    claim: str,
    candidate_advantage_observed: bool,
    root_claims_created: int,
    candidate_claims_created: int,
    measured_candidate_outcomes: int,
    activated_candidate_targets: int,
    deferred_unactivated_development_candidates: int,
    development_capture_metadata_opened: bool,
    development_outcomes_opened: int,
    development_prediction_committed: bool,
) -> dict[str, object]:
    """Build the durable, path-free source for normal or recovered stdout."""

    return {
        "record_type": "battle_outcome_cycle_terminal",
        "status": status,
        "experiment_id": plan.experiment_id,
        "plan_sha256": plan.plan_sha256,
        "cycle": None if cycle is None else cycle.public_dict(),
        "paired_development": paired_development,
        "base_model_sha256": base_model_sha256,
        "model_sha256": model_sha256,
        "claim": claim,
        "candidate_advantage_observed": candidate_advantage_observed,
        "historically_untouched_claimed": False,
        "root_claims_created": root_claims_created,
        "candidate_claims_created": candidate_claims_created,
        "measured_candidate_outcomes": measured_candidate_outcomes,
        "activated_candidate_targets": activated_candidate_targets,
        "deferred_unactivated_development_candidates": (
            deferred_unactivated_development_candidates
        ),
        "unexecuted_counterfactual_targets": 0,
        "unmeasured_action_targets": 0,
        "development_capture_metadata_opened": (
            development_capture_metadata_opened
        ),
        "development_outcomes_opened": development_outcomes_opened,
        "development_influenced_fit": False,
        "development_predictions_committed_before_outcomes": (
            development_prediction_committed
        ),
        "model_fits": int(cycle is not None),
        "development_comparisons": int(cycle is not None),
        "unseen_comparisons": 0,
        "authority_promoted": False,
        "red_sealed_test_cases_opened": 0,
        "crystal_contexts_opened": 0,
        "teacher_queries": 0,
        "teacher_choice_targets": 0,
        "full_game_replays": 0,
        "materializer_derivation_claimed": False,
        "private_path_fields": 0,
    }


@contextmanager
def _retain_failure_record(
    writer,  # type: ignore[no-untyped-def]
    *,
    plan_sha256: str,
    snapshot: Callable[[], dict[str, object]],
) -> Iterator[None]:
    """Retain a sanitized failure before the writer converts to a failed artifact."""

    try:
        yield
    except BaseException as error:
        state = snapshot()
        with suppress(Exception):
            writer.append(
                "failure",
                {
                    "record_type": "battle_outcome_cycle_failure",
                    "plan_sha256": plan_sha256,
                    "stage": state["stage"],
                    "failure_type": type(error).__name__,
                    "root_claims_created": state["root_claims_created"],
                    "candidate_claims_created": state["candidate_claims_created"],
                    "measured_candidate_outcomes": state[
                        "measured_candidate_outcomes"
                    ],
                    "retry_permitted": False,
                },
                durable=True,
            )
        raise


def _assignment_record(
    plan: BattleOutcomeExperimentPlan,
    *,
    artifact_id: str,
    source: Mapping[str, object],
) -> dict[str, object]:
    return {
        "record_type": "battle_outcome_experiment_assignment",
        "artifact_id": artifact_id,
        "experiment_id": plan.experiment_id,
        "plan_sha256": plan.plan_sha256,
        "source_commit": plan.source_commit,
        "source_bundle_sha256": plan.source_bundle_sha256,
        "runner_sha256": plan.runner_sha256,
        "runtime_identity_sha256": plan.runtime_identity_sha256,
        "numpy_runtime_sha256": plan.numpy_runtime_sha256,
        "rom_sha256": plan.rom_sha256,
        "base_model_sha256": plan.base_model_sha256,
        "objective_id": plan.objective_id,
        "objective_sha256": plan.objective_sha256,
        "train": plan.train.public_dict(),
        "development": plan.development.public_dict(),
        "source": dict(source),
        "development_influences_fit": False,
        "authority": "shadow_only",
    }


def _collection_record(
    collection: RedBattleOutcomeCollection,
    *,
    split: ScenarioPartition,
) -> dict[str, object]:
    return {
        "record_type": "battle_outcome_collection",
        "split": split.value,
        "collection": collection.public_dict(),
        "unexecuted_counterfactual_targets": 0,
        "unmeasured_action_targets": 0,
    }


def _read_experiment_plan(
    path: Path,
    expected_sha256: str,
) -> BattleOutcomeExperimentPlan:
    if not isinstance(path, Path):
        raise TypeError("experiment plan path must be a Path")
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    descriptor = -1
    try:
        named = path.lstat()
        descriptor = os.open(path, flags)
        opened = os.fstat(descriptor)
        if (
            named.st_dev != opened.st_dev
            or named.st_ino != opened.st_ino
            or not stat.S_ISREG(opened.st_mode)
            or opened.st_nlink != 1
            or opened.st_uid != os.getuid()
            or stat.S_IMODE(opened.st_mode) != 0o600
            or not 1 <= opened.st_size <= _MAXIMUM_PLAN_BYTES
        ):
            raise OSError("unsafe experiment plan")
        payload = os.read(descriptor, opened.st_size + 1)
        if len(payload) != opened.st_size:
            raise OSError("experiment plan changed while opening")
    except OSError:
        raise BattleOutcomeCycleError("experiment plan cannot be authenticated") from None
    finally:
        if descriptor >= 0:
            os.close(descriptor)
    if hashlib.sha256(payload).hexdigest() != expected_sha256:
        raise BattleOutcomeCycleError("experiment plan digest differs")
    try:
        return parse_battle_outcome_experiment_plan(payload)
    except ValueError:
        raise BattleOutcomeCycleError("experiment plan cannot be authenticated") from None


def _revalidate_after_claim(
    path: Path,
    expected_sha256: str,
    plan: BattleOutcomeExperimentPlan,
) -> None:
    if _read_experiment_plan(path, expected_sha256) != plan:
        raise BattleOutcomeCycleError("experiment plan changed after root claim")
    _require_current_plan_files(plan)


def _require_current_plan_files(plan: BattleOutcomeExperimentPlan) -> None:
    if (
        working_source_bundle_sha256(PROJECT_ROOT) != plan.source_bundle_sha256
        or _file_sha256(RUNNER_PATH) != plan.runner_sha256
        or _file_sha256(MATERIALIZER_PATH) != plan.materializer_sha256
    ):
        raise BattleOutcomeCycleError("experiment executable source differs")


def _require_upstream_plan_bindings(
    plan: BattleOutcomeExperimentPlan,
    context_catalog_path: Path,
) -> None:
    registry = load_committed_goal_manager_registry_at_revision(
        PROJECT_ROOT,
        plan.registry_source_commit,
    )
    if (
        registry.registry_sha256 != plan.registry_sha256
        or registry.execution.source_bundle_sha256
        != plan.registry_source_bundle_sha256
    ):
        raise BattleOutcomeCycleError("historical goal-manager registry differs")
    payload = _read_bounded_private_file(
        context_catalog_path,
        maximum_bytes=_MAXIMUM_CONTEXT_CATALOG_BYTES,
        subject="context catalog",
    )
    if hashlib.sha256(payload).hexdigest() != plan.context_catalog_sha256:
        raise BattleOutcomeCycleError("context catalog digest differs")
    catalog = parse_goal_manager_context_catalog(payload, registry)
    if catalog.catalog_sha256 != plan.context_catalog_sha256:
        raise BattleOutcomeCycleError("context catalog identity differs")
    _require_catalog_binding(
        plan.train,
        expected_catalog_partition="train",
        catalog=catalog,
        registry=registry,
    )
    _require_catalog_binding(
        plan.development,
        expected_catalog_partition="validation",
        catalog=catalog,
        registry=registry,
    )


def _require_catalog_binding(
    binding: BattleOutcomeCaptureBinding,
    *,
    expected_catalog_partition: str,
    catalog: GoalManagerContextCatalog,
    registry: GoalManagerCollectionRegistry,
) -> None:
    matching = tuple(
        entry
        for entry in catalog.entries
        if entry.state_sha256 == binding.source_state_sha256
    )
    if len(matching) != 1:
        raise BattleOutcomeCycleError("battle plan has no unique catalog root")
    entry = matching[0]
    assignment = registry.assignment(entry.slot_id)
    root_lineage_id = entry.authenticated_root_lineage_id(
        slot_id=entry.slot_id,
        capture_id=entry.capture_id,
        state_sha256=entry.state_sha256,
        envelope_sha256=entry.envelope_sha256,
    )
    if (
        assignment.partition != expected_catalog_partition
        or entry.slot_id != binding.source_slot_id
        or entry.assignment_id != binding.source_assignment_id
        or entry.assignment_id != assignment.assignment_id
        or entry.context_id != binding.source_context_id
        or entry.envelope_sha256 != binding.source_envelope_sha256
        or root_lineage_id != binding.root_lineage_id
    ):
        raise BattleOutcomeCycleError("battle plan differs from its catalog root")


def _require_capture_binding(
    capture: BattleScenarioCapture,
    binding: BattleOutcomeCaptureBinding,
) -> None:
    manifest = capture.manifest
    if (
        manifest.partition is not binding.partition
        or manifest.capture_id != binding.capture_id
        or capture.manifest_sha256 != binding.manifest_sha256
        or manifest.state_sha256 != binding.state_sha256
        or manifest.initial_observation_sha256 != binding.initial_observation_sha256
        or manifest.source_commit != binding.source_commit
        or manifest.source_state_sha256 != binding.source_state_sha256
        or manifest.root_lineage_id != binding.root_lineage_id
        or manifest.expected_map != binding.expected_map
        or manifest.expected_battle_state != binding.expected_battle_state
    ):
        raise BattleOutcomeCycleError("battle capture differs from the frozen plan")


def _require_prepared_binding(
    binding: BattleOutcomeCaptureBinding,
    prepared: PreparedRedBattleScenario,
    base_model: MaskedMLPMoveRanker,
) -> None:
    """Authenticate one learnable menu before any root claim or controller input."""

    if prepared.initial_observation_sha256 != binding.initial_observation_sha256:
        raise BattleOutcomeCycleError("prepared battle observation differs from the plan")
    supported_indices = tuple(
        index
        for index, (legal, pp) in enumerate(
            zip(
                prepared.features.legal_mask,
                prepared.features.current_pp,
                strict=True,
            )
        )
        if legal and pp > 0
    )
    supported_vectors = tuple(
        prepared.features.candidate_vectors[index] for index in supported_indices
    )
    try:
        hidden_digest = battle_outcome_hidden_menu_sha256(
            base_model,
            prepared.features,
        )
        distinct_hidden_count = battle_outcome_distinct_hidden_embedding_count(
            base_model,
            prepared.features,
        )
    except (TypeError, ValueError):
        raise BattleOutcomeCycleError(
            "prepared battle menu differs from the frozen prior schema"
        ) from None
    if (
        battle_outcome_menu_sha256(prepared.features) != binding.menu_sha256
        or len(supported_indices) != binding.supported_candidate_count
        or len(set(supported_vectors)) != binding.distinct_candidate_vector_count
        or hidden_digest != binding.hidden_embedding_sha256
        or distinct_hidden_count != binding.distinct_hidden_embedding_count
    ):
        raise BattleOutcomeCycleError(
            "prepared battle menu differs from the prospective experiment"
        )


def _read_bounded_private_file(
    path: Path,
    *,
    maximum_bytes: int,
    subject: str,
) -> bytes:
    if not isinstance(path, Path):
        raise TypeError(f"{subject} path must be a Path")
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    descriptor = -1
    try:
        named = path.lstat()
        descriptor = os.open(path, flags)
        opened = os.fstat(descriptor)
        if (
            named.st_dev != opened.st_dev
            or named.st_ino != opened.st_ino
            or not stat.S_ISREG(opened.st_mode)
            or opened.st_nlink != 1
            or opened.st_uid != os.getuid()
            or not 1 <= opened.st_size <= maximum_bytes
        ):
            raise OSError(f"unsafe {subject}")
        payload = os.read(descriptor, opened.st_size + 1)
        if len(payload) != opened.st_size:
            raise OSError(f"{subject} changed while opening")
        return payload
    except OSError:
        raise BattleOutcomeCycleError(f"{subject} cannot be authenticated") from None
    finally:
        if descriptor >= 0:
            os.close(descriptor)


def _root_pair(
    plan: BattleOutcomeExperimentPlan,
    capture: BattleOutcomeCaptureBinding,
    *,
    stage: str,
) -> ClaimFirstRootPair:
    execution_identity_sha256 = canonical_sha256(
        {
            "base_model_sha256": plan.base_model_sha256,
            "numpy_runtime_sha256": plan.numpy_runtime_sha256,
            "plan_sha256": plan.plan_sha256,
            "rom_sha256": plan.rom_sha256,
            "runtime_identity_sha256": plan.runtime_identity_sha256,
            "schema": "pokemon.red.battle-outcome-cycle-execution.v1",
        }
    )
    return ClaimFirstRootPair(
        logical_root_sha256=capture.root_consumption_sha256,
        physical_root_sha256=capture.state_sha256,
        stage=stage,
        execution_identity_sha256=execution_identity_sha256,
        plan_sha256=plan.plan_sha256,
        slot_sha256=capture.manifest_sha256,
        runner_sha256=plan.runner_sha256,
        source_commit=plan.source_commit,
    )


def _root_claim_record(
    claim: ClaimFirstRootPair,
    *,
    split: ScenarioPartition,
    capture: BattleOutcomeCaptureBinding,
) -> dict[str, object]:
    return {
        "record_type": "battle_outcome_root_pair_claim",
        "split": split.value,
        "capture_id": capture.capture_id,
        "root_lineage_id": capture.root_lineage_id,
        "root_pair_claim_sha256": claim.claim_sha256,
        **claim.private_dict(),
    }


def _collect_claimed_capture(
    writer,  # type: ignore[no-untyped-def]
    *,
    plan: BattleOutcomeExperimentPlan,
    capture_binding: BattleOutcomeCaptureBinding,
    capture: BattleScenarioCapture,
    root_pair: ClaimFirstRootPair,
    base_model: MaskedMLPMoveRanker,
    session_factory,  # type: ignore[no-untyped-def]
    prepared_boundary: PreparedRedBattleScenario | None = None,
    progress_sink: Callable[[str], None] | None = None,
) -> tuple[RedBattleOutcomeCollection, int, int]:
    claimed: set[int] = set()
    retained: dict[int, str] = {}
    prepared = prepared_boundary or prepare_red_battle_outcome_capture(
        capture,
        session_factory=session_factory,
    )
    _require_prepared_binding(capture_binding, prepared, base_model)
    expected = {
        index
        for index, (legal, pp) in enumerate(
            zip(
                prepared.features.legal_mask,
                prepared.features.current_pp,
                strict=True,
            )
        )
        if legal and pp > 0
    }
    menu_sha256 = battle_outcome_menu_sha256(prepared.features)
    if menu_sha256 != capture_binding.menu_sha256:
        raise BattleOutcomeCycleError("candidate menu differs from the frozen plan")

    def retain_candidate_claim(candidate_index: int) -> None:
        if candidate_index in claimed or candidate_index not in expected:
            raise BattleOutcomeCycleError("candidate claim is duplicated or invalid")
        record = {
            "record_type": "battle_candidate_claim",
            "plan_sha256": plan.plan_sha256,
            "root_pair_claim_sha256": root_pair.claim_sha256,
            "split": capture_binding.partition.value,
            "source_slot_id": capture_binding.source_slot_id,
            "source_assignment_id": capture_binding.source_assignment_id,
            "capture_id": capture_binding.capture_id,
            "root_lineage_id": capture_binding.root_lineage_id,
            "state_sha256": capture_binding.state_sha256,
            "manifest_sha256": capture_binding.manifest_sha256,
            "initial_observation_sha256": capture_binding.initial_observation_sha256,
            "menu_sha256": menu_sha256,
            "candidate_index": candidate_index,
            "input_status_at_claim": "not_yet_sent",
        }
        record["candidate_claim_sha256"] = canonical_sha256(record)
        writer.append("candidate_claims", record, durable=True)
        claimed.add(candidate_index)
        if progress_sink is not None:
            progress_sink("candidate_claim")

    def retain_candidate_outcome(candidate_index, outcome):  # type: ignore[no-untyped-def]
        if candidate_index not in claimed or candidate_index in retained:
            raise BattleOutcomeCycleError("candidate outcome lacks one durable claim")
        outcome_payload = outcome.public_dict()
        writer.append(
            "candidate_outcomes",
            {
                "record_type": "battle_candidate_outcome",
                "plan_sha256": plan.plan_sha256,
                "root_pair_claim_sha256": root_pair.claim_sha256,
                "split": capture_binding.partition.value,
                "capture_id": capture_binding.capture_id,
                "candidate_index": candidate_index,
                "outcome": outcome_payload,
                "teacher_queries": 0,
                "teacher_choice_targets": 0,
            },
            durable=True,
        )
        retained[candidate_index] = canonical_sha256(outcome_payload)
        if progress_sink is not None:
            progress_sink("candidate_outcome")

    collection = collect_red_battle_outcome_example(
        capture,
        session_factory=session_factory,
        candidate_claim_sink=retain_candidate_claim,
        outcome_sink=retain_candidate_outcome,
    )
    measured = {
        index for index, outcome in enumerate(collection.outcomes) if outcome is not None
    }
    returned_outcomes = {
        index: canonical_sha256(outcome.public_dict())
        for index, outcome in enumerate(collection.outcomes)
        if outcome is not None
    }
    if (
        collection.initial_observation_sha256
        != prepared.initial_observation_sha256
        or collection.example.features != prepared.features
        or expected != measured
        or claimed != measured
        or set(retained) != measured
        or retained != returned_outcomes
    ):
        raise BattleOutcomeCycleError(
            "candidate claims and measured outcomes do not cover one exact menu"
        )
    return collection, len(claimed), len(retained)


def _increment_progress(progress: dict[str, int], event: str) -> None:
    if event == "candidate_claim":
        progress["candidate_claims_created"] += 1
    elif event == "candidate_outcome":
        progress["measured_candidate_outcomes"] += 1
    else:  # pragma: no cover - the local callbacks use the two constants above
        raise BattleOutcomeCycleError("battle cycle progress event differs")


def _require_update_identity(
    update: BattleOutcomeUpdate,
    *,
    plan: BattleOutcomeExperimentPlan,
    train_example: BattleOutcomeExample,
) -> None:
    model_sha256 = _model_sha256(update.model)
    report = update.report
    if (
        report.base_model_sha256 != plan.base_model_sha256
        or report.updated_model_sha256 != model_sha256
        or report.training_example_count != 1
        or report.training_root_lineage_ids != (train_example.root_lineage_id,)
        or report.training_state_sha256 != (train_example.initial_state_sha256,)
        or report.epochs != plan.epochs
        or report.learning_rate != plan.learning_rate
        or report.prior_l2 != plan.prior_l2
    ):
        raise BattleOutcomeCycleError("train-only update identity differs")


def _require_evaluation_identity(
    base_evaluation,  # type: ignore[no-untyped-def]
    updated_evaluation,  # type: ignore[no-untyped-def]
    paired: BattleOutcomePairedEvaluation,
    *,
    base_model_sha256: str,
    updated_model_sha256: str,
    development_example: BattleOutcomeExample,
    base_choice: int,
    updated_choice: int,
) -> None:
    expected_roots = (development_example.root_lineage_id,)
    base_outcome = development_example.outcomes[base_choice]
    updated_outcome = development_example.outcomes[updated_choice]
    if base_outcome is None or updated_outcome is None:
        raise BattleOutcomeCycleError("development comparison selected no outcome")
    difference = updated_outcome.utility - base_outcome.utility
    equivalent = math.isclose(difference, 0.0, abs_tol=1e-9)
    expected_updated_wins = int(difference > 0 and not equivalent)
    expected_base_wins = int(difference < 0 and not equivalent)
    expected_equivalent = int(equivalent)
    if (
        base_evaluation.model_sha256 != base_model_sha256
        or updated_evaluation.model_sha256 != updated_model_sha256
        or paired.base_model_sha256 != base_model_sha256
        or paired.updated_model_sha256 != updated_model_sha256
        or base_evaluation.example_count != 1
        or updated_evaluation.example_count != 1
        or paired.example_count != 1
        or base_evaluation.root_lineage_ids != expected_roots
        or updated_evaluation.root_lineage_ids != expected_roots
        or paired.root_lineage_ids != expected_roots
        or paired.updated_wins != expected_updated_wins
        or paired.base_wins != expected_base_wins
        or paired.equivalent_choices != expected_equivalent
        or paired.base_correct_preferences
        != base_evaluation.correct_preferences
        or paired.updated_correct_preferences
        != updated_evaluation.correct_preferences
    ):
        raise BattleOutcomeCycleError("development evaluation identity differs")


def _require_development_capture(
    train_capture: BattleScenarioCapture,
    development_capture: BattleScenarioCapture,
    *,
    source_commit: str,
) -> None:
    train = train_capture.manifest
    development = development_capture.manifest
    if development.partition is not ScenarioPartition.DEVELOPMENT:
        raise BattleOutcomeCycleError("development capture has the wrong partition")
    if development.source_commit != source_commit:
        raise BattleOutcomeCycleError("capture source differs from the published runner")
    if development.source_state_sha256 is None:
        raise BattleOutcomeCycleError(
            "development capture lacks its upstream state binding"
        )
    if (
        train.capture_id == development.capture_id
        or train.root_lineage_id == development.root_lineage_id
        or train.source_state_sha256 == development.source_state_sha256
        or train.state_sha256 == development.state_sha256
        or train.initial_observation_sha256 == development.initial_observation_sha256
    ):
        raise BattleOutcomeCycleError("train and development capture lineages overlap")


def _require_committed_development_choices(
    base_model: MaskedMLPMoveRanker,
    updated_model: MaskedMLPMoveRanker,
    example: BattleOutcomeExample,
    *,
    base_choice: int,
    updated_choice: int,
) -> None:
    candidate_count = len(example.outcomes)
    if base_choice not in range(candidate_count) or updated_choice not in range(
        candidate_count
    ):
        raise BattleOutcomeCycleError(
            "committed development choice is outside the measured menu"
        )
    observed_base_choice = base_model.predict(
        example.features.candidate_vectors,
        legal_mask=example.features.legal_mask,
        current_pp=example.features.current_pp,
    )
    observed_updated_choice = updated_model.predict(
        example.features.candidate_vectors,
        legal_mask=example.features.legal_mask,
        current_pp=example.features.current_pp,
    )
    if observed_base_choice != base_choice or observed_updated_choice != updated_choice:
        raise BattleOutcomeCycleError(
            "development choices differ from their pre-outcome commitment"
        )


def _model_sha256(model: MaskedMLPMoveRanker) -> str:
    return hashlib.sha256(model.to_json().encode("ascii")).hexdigest()


def _file_sha256(path: Path) -> str:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError:
        raise BattleOutcomeCycleError(
            "experiment executable source is unavailable"
        ) from None


def _sha256(value: object, subject: str) -> str:
    if not isinstance(value, str) or _SHA256.fullmatch(value) is None:
        raise BattleOutcomeCycleError(f"{subject} digest is invalid")
    return value


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    print(json.dumps(_run(args), allow_nan=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
