#!/usr/bin/env python3
"""Freeze one lineage-authenticated Red battle train/development pair."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import stat
import sys
from contextlib import suppress
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from pokemon_red_completion.battle_neural_model import (  # noqa: E402
    MaskedMLPMoveRanker,
)
from pokemon_red_completion.battle_outcome_capture_authentication import (  # noqa: E402
    BattleOutcomeCaptureAuthenticationError,
    authenticate_battle_outcome_capture_binding,
)
from pokemon_red_completion.battle_outcome_experiment import (  # noqa: E402
    BattleOutcomeCaptureBinding,
    BattleOutcomeExperimentPlan,
    battle_outcome_controller_timing_sha256,
    build_battle_outcome_experiment_plan_payload,
)
from pokemon_red_completion.battle_scenario_capture import (  # noqa: E402
    BattleScenarioCapture,
    open_battle_scenario_capture,
)
from pokemon_red_completion.claim_first_admission import (  # noqa: E402
    ClaimFirstAdmissionError,
    observe_claim_first_pair_availability,
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
from pokemon_red_completion.provenance import (  # noqa: E402
    detect_source_identity,
    require_clean_source,
    require_published_source,
)
from pokemon_red_completion.red_battle_outcome_runtime import (  # noqa: E402
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

RUNNER_PATH = PROJECT_ROOT / "scripts" / "run_battle_outcome_learning_cycle.py"
MATERIALIZER_PATH = PROJECT_ROOT / "scripts" / "materialize_battle_scenario_capture.py"
_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_GIT_COMMIT = re.compile(r"[0-9a-f]{40}\Z")
_MAXIMUM_CONTEXT_CATALOG_BYTES = 4 * 1024 * 1024


class BattleOutcomeExperimentFreezeError(RuntimeError):
    """Raised before a prospective pair can be published."""


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--experiment-id", required=True)
    parser.add_argument("--expected-source-commit", required=True)
    parser.add_argument("--expected-source-bundle-sha256", required=True)
    parser.add_argument("--registry-source-commit", required=True)
    parser.add_argument("--expected-registry-sha256", required=True)
    parser.add_argument("--context-catalog", type=Path, required=True)
    parser.add_argument("--expected-context-catalog-sha256", required=True)
    parser.add_argument("--base-model", type=Path, required=True)
    parser.add_argument("--expected-base-model-sha256", required=True)
    parser.add_argument("--train-state", type=Path, required=True)
    parser.add_argument("--train-manifest", type=Path, required=True)
    parser.add_argument("--development-state", type=Path, required=True)
    parser.add_argument("--development-manifest", type=Path, required=True)
    parser.add_argument("--out-plan", type=Path, required=True)
    parser.add_argument("--rom", type=Path, default=None, help="otherwise POKEMON_RED_ROM")
    return parser


def _run(args: argparse.Namespace) -> dict[str, object]:
    source = detect_source_identity(PROJECT_ROOT, include_untracked=True)
    require_clean_source(source)
    require_published_source(PROJECT_ROOT, source)
    expected_commit = _commit(args.expected_source_commit, "source")
    expected_bundle = _sha256(args.expected_source_bundle_sha256, "source bundle")
    source_bundle = working_source_bundle_sha256(PROJECT_ROOT)
    if source.git_commit != expected_commit or source_bundle != expected_bundle:
        raise BattleOutcomeExperimentFreezeError("published source identity differs")

    runner_sha256 = _file_sha256(RUNNER_PATH)
    materializer_sha256 = _file_sha256(MATERIALIZER_PATH)
    runtime = build_runtime_identity()
    require_pyboy_import_origins(runtime)
    numpy_runtime_sha256 = goal_manager_development_numpy_runtime_sha256()
    rom_path = resolve_rom_path(args.rom)
    rom = verify_rom(rom_path)

    base_model = load_battle_model_artifact(args.base_model)
    if not isinstance(base_model, MaskedMLPMoveRanker):
        raise BattleOutcomeExperimentFreezeError(
            "battle experiment requires the nonlinear prior"
        )
    base_model_sha256 = hashlib.sha256(
        base_model.to_json().encode("ascii")
    ).hexdigest()
    if base_model_sha256 != _sha256(
        args.expected_base_model_sha256,
        "base model",
    ):
        raise BattleOutcomeExperimentFreezeError("base model differs")

    registry_commit = _commit(args.registry_source_commit, "registry source")
    registry = load_committed_goal_manager_registry_at_revision(
        PROJECT_ROOT,
        registry_commit,
    )
    if registry.registry_sha256 != _sha256(
        args.expected_registry_sha256,
        "registry",
    ):
        raise BattleOutcomeExperimentFreezeError("historical registry differs")
    catalog_payload = _read_bounded_private_file(
        args.context_catalog,
        maximum_bytes=_MAXIMUM_CONTEXT_CATALOG_BYTES,
        subject="context catalog",
    )
    if hashlib.sha256(catalog_payload).hexdigest() != _sha256(
        args.expected_context_catalog_sha256,
        "context catalog",
    ):
        raise BattleOutcomeExperimentFreezeError("context catalog digest differs")
    catalog = parse_goal_manager_context_catalog(catalog_payload, registry)

    train_capture = open_battle_scenario_capture(
        args.train_state,
        args.train_manifest,
    )
    development_capture = open_battle_scenario_capture(
        args.development_state,
        args.development_manifest,
    )

    def session_factory():  # type: ignore[no-untyped-def]
        return PyBoyAdapter(rom_path)

    try:
        prepared_train = prepare_red_battle_outcome_capture(
            train_capture,
            session_factory=session_factory,
        )
        prepared_development = prepare_red_battle_outcome_capture(
            development_capture,
            session_factory=session_factory,
        )
    except (OSError, RuntimeError, ValueError):
        raise BattleOutcomeExperimentFreezeError(
            "battle capture boundary cannot be authenticated read-only"
        ) from None
    bindings = (
        _binding_for_capture(
            train_capture,
            prepared=prepared_train,
            base_model=base_model,
            expected_partition=ScenarioPartition.TRAIN,
            expected_catalog_partition="train",
            source_commit=expected_commit,
            catalog=catalog,
            registry=registry,
        ),
        _binding_for_capture(
            development_capture,
            prepared=prepared_development,
            base_model=base_model,
            expected_partition=ScenarioPartition.DEVELOPMENT,
            expected_catalog_partition="validation",
            source_commit=expected_commit,
            catalog=catalog,
            registry=registry,
        ),
    )
    _require_available_root_pairs(
        bindings,
        registry_path=open_fixed_account_claim_registry(),
    )

    plan = BattleOutcomeExperimentPlan(
        experiment_id=args.experiment_id,
        source_commit=expected_commit,
        source_bundle_sha256=source_bundle,
        runner_sha256=runner_sha256,
        materializer_sha256=materializer_sha256,
        registry_source_commit=registry_commit,
        registry_source_bundle_sha256=registry.execution.source_bundle_sha256,
        registry_sha256=registry.registry_sha256,
        context_catalog_sha256=catalog.catalog_sha256,
        rom_sha256=rom.sha256,
        runtime_identity_sha256=runtime.sha256,
        numpy_runtime_sha256=numpy_runtime_sha256,
        base_model_sha256=base_model_sha256,
        controller_timing_sha256=battle_outcome_controller_timing_sha256(),
        captures=bindings,
    )
    payload = build_battle_outcome_experiment_plan_payload(plan)
    destination = _private_new_plan(args.out_plan, rom_path=rom_path)
    _write_exclusive(destination, payload)
    return {
        "schema": "pokemon-red-battle-outcome-experiment-freeze-receipt-v1",
        "status": "prospective_pair_frozen",
        "experiment_id": plan.experiment_id,
        "plan_sha256": hashlib.sha256(payload).hexdigest(),
        "source_commit": expected_commit,
        "source_bundle_sha256": source_bundle,
        "runtime_identity_sha256": runtime.sha256,
        "numpy_runtime_sha256": numpy_runtime_sha256,
        "rom_sha256": rom.sha256,
        "base_model_sha256": base_model_sha256,
        "train_root_lineages": 1,
        "development_root_lineages": 1,
        "read_only_runtime_preparations": 2,
        "root_claims_created": 0,
        "model_predictions": 0,
        "controller_actions": 0,
        "emulator_frames": 0,
        "outcomes_observed": 0,
        "model_fits": 0,
        "materializer_derivation_claimed": False,
        "teacher_queries": 0,
        "red_sealed_test_cases_opened": 0,
        "crystal_contexts_opened": 0,
        "private_path_fields": 0,
    }


def _require_available_root_pairs(
    bindings: tuple[BattleOutcomeCaptureBinding, BattleOutcomeCaptureBinding],
    *,
    registry_path: Path,
) -> None:
    """Observe upstream-consumption/materialized-state pairs without claiming."""

    try:
        available = all(
            observe_claim_first_pair_availability(
                registry_path,
                binding.logical_root_sha256,
                binding.physical_root_sha256,
            )
            for binding in bindings
        )
    except ClaimFirstAdmissionError:
        raise BattleOutcomeExperimentFreezeError(
            "assigned upstream root pairs cannot be authenticated"
        ) from None
    if not available:
        raise BattleOutcomeExperimentFreezeError(
            "an assigned upstream root pair is already consumed"
        )


def _binding_for_capture(
    capture: BattleScenarioCapture,
    *,
    prepared: PreparedRedBattleScenario,
    base_model: MaskedMLPMoveRanker,
    expected_partition: ScenarioPartition,
    expected_catalog_partition: str,
    source_commit: str,
    catalog: GoalManagerContextCatalog,
    registry: GoalManagerCollectionRegistry,
) -> BattleOutcomeCaptureBinding:
    derived_catalog_partition = (
        "train"
        if expected_partition is ScenarioPartition.TRAIN
        else "validation"
    )
    if expected_catalog_partition != derived_catalog_partition:
        raise BattleOutcomeExperimentFreezeError(
            "battle capture catalog partition differs"
        )
    try:
        return authenticate_battle_outcome_capture_binding(
            capture,
            prepared=prepared,
            base_model=base_model,
            expected_partition=expected_partition,
            source_commit=source_commit,
            catalog=catalog,
            registry=registry,
        )
    except BattleOutcomeCaptureAuthenticationError as error:
        raise BattleOutcomeExperimentFreezeError(str(error)) from None


def _private_new_plan(destination: Path, *, rom_path: Path) -> Path:
    resolved = destination.resolve()
    if resolved.is_relative_to(PROJECT_ROOT.resolve()):
        raise BattleOutcomeExperimentFreezeError("experiment plan must remain private")
    if resolved.parent == rom_path.resolve().parent:
        raise BattleOutcomeExperimentFreezeError(
            "experiment plan cannot be written beside the ROM"
        )
    if not resolved.parent.is_dir() or resolved.exists() or destination.is_symlink():
        raise BattleOutcomeExperimentFreezeError(
            "experiment plan output is unavailable or already exists"
        )
    return resolved


def _write_exclusive(destination: Path, payload: bytes) -> None:
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_CLOEXEC"):
        flags |= os.O_CLOEXEC
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    descriptor = -1
    directory_descriptor = -1
    created = False
    failed = False
    try:
        descriptor = os.open(destination, flags, 0o600)
        created = True
        offset = 0
        while offset < len(payload):
            written = os.write(descriptor, payload[offset:])
            if written <= 0:
                raise OSError("write made no progress")
            offset += written
        os.fsync(descriptor)
        os.close(descriptor)
        descriptor = -1
        directory_flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0)
        directory_flags |= getattr(os, "O_DIRECTORY", 0)
        directory_descriptor = os.open(destination.parent, directory_flags)
        os.fsync(directory_descriptor)
    except OSError:
        failed = True
    finally:
        if descriptor >= 0:
            try:
                os.close(descriptor)
            except OSError:
                failed = True
        if directory_descriptor >= 0:
            try:
                os.close(directory_descriptor)
            except OSError:
                failed = True
    if failed:
        if created:
            with suppress(OSError):
                destination.unlink()
            with suppress(OSError):
                cleanup_descriptor = os.open(
                    destination.parent,
                    os.O_RDONLY
                    | getattr(os, "O_CLOEXEC", 0)
                    | getattr(os, "O_DIRECTORY", 0),
                )
                try:
                    os.fsync(cleanup_descriptor)
                finally:
                    os.close(cleanup_descriptor)
        raise BattleOutcomeExperimentFreezeError(
            "experiment plan could not be retained"
        ) from None


def _file_sha256(path: Path) -> str:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError:
        raise BattleOutcomeExperimentFreezeError("executable source is unavailable") from None


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
        raise BattleOutcomeExperimentFreezeError(
            f"{subject} cannot be authenticated"
        ) from None
    finally:
        if descriptor >= 0:
            os.close(descriptor)


def _sha256(value: object, subject: str) -> str:
    if not isinstance(value, str) or _SHA256.fullmatch(value) is None:
        raise BattleOutcomeExperimentFreezeError(f"{subject} digest is invalid")
    return value


def _commit(value: object, subject: str) -> str:
    if not isinstance(value, str) or _GIT_COMMIT.fullmatch(value) is None:
        raise BattleOutcomeExperimentFreezeError(f"{subject} commit is invalid")
    return value


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    print(json.dumps(_run(args), allow_nan=False, separators=(",", ":"), sort_keys=True))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
