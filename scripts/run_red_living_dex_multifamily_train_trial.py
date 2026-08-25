#!/usr/bin/env python3
"""Execute exactly the first frozen V3 Red multi-family train intervention.

The V3 plan, not a command-line choice or model prediction, selects the physical
root, dependency family, and candidate index.  This runner authenticates that
sealed plan before opening the context inventory, reconstructs both executable
capabilities from the selected reset, durably claims the trial and physical root
before controller input, executes only the frozen candidate, and settles the
terminal from a fresh living-Pokedex observation.

One claimed trial is permanently consumed.  There is no teacher, fallback,
alternate-candidate rescue, scenario substitution, or retry path.
"""

# ruff: noqa: E402 -- pin script/package roots before project imports.

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from collections import Counter
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace
from typing import Literal, Never

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_ROOT = PROJECT_ROOT / "scripts"
SRC_ROOT = PROJECT_ROOT / "src"
for root in (SCRIPTS_ROOT, SRC_ROOT):
    while str(root) in sys.path:
        sys.path.remove(str(root))
    sys.path.insert(0, str(root))

import freeze_red_living_dex_multifamily_pilot as freezer
import freeze_red_living_dex_multifamily_pilot_v3 as freezer_v3
import run_red_dual_capability_preflight as support
from public_execution_manifest import (
    PublicExecutionManifestError,
    read_tracked_public_evidence,
)

from pokemon_red_completion.blaine import (
    DIGLETTS_CAVE_TRAINING_VENUE,
    MANSION_BALANCED_TEAM_TRAINING_INTENT,
    MANSION_ESCORT_ENEMY_SPECIES,
    MANSION_LEVEL_UP_MOVE_CANCEL_INTERVAL,
    MANSION_MAX_CONSECUTIVE_FLEES,
    MANSION_TEAM_POLICY,
    MANSION_TRAINING_FLEE_TIMING,
    MANSION_TRAINING_VENUE,
    MANSION_VOLATILE_ENEMY_SPECIES,
    ROUTE_11_TRAINING_VENUE,
    _flee,
)
from pokemon_red_completion.bootstrap import DEFAULT_NEW_GAME_TIMING
from pokemon_red_completion.collection_protocol import working_source_bundle_sha256
from pokemon_red_completion.constants import POKEMON_RED_US_REV_0
from pokemon_red_completion.emulator import PyBoyAdapter
from pokemon_red_completion.encounters import ENCOUNTER_LOG_VARIABLE
from pokemon_red_completion.executor import (
    CountingExecutor,
    FrameSafeExecutor,
    WindowedFrameBudgetController,
)
from pokemon_red_completion.gen1_field_moves import (
    Gen1FieldMovePort,
    gen1_field_capabilities,
)
from pokemon_red_completion.gen1_route_runtime import (
    Gen1RouteInterruptionHandler,
    Gen1TraversalObserver,
)
from pokemon_red_completion.gen1_trainer_sight import Gen1TrainerSightProjector
from pokemon_red_completion.goal_manager import GoalKind
from pokemon_red_completion.goal_manager_collection_runtime import (
    goal_binding_manifest_sha256,
)
from pokemon_red_completion.goal_manager_composition_qualification import (
    HardCompositionActionLimiter,
    fixed_account_claim_registry_lease,
    open_fixed_account_claim_registry,
    read_root_claim,
    root_claim_is_available,
    write_root_claim,
)
from pokemon_red_completion.goal_manager_trajectory import ordered_goal_manager_question
from pokemon_red_completion.hideout import DEFAULT_HIDEOUT_TIMING
from pokemon_red_completion.observation import (
    ItemId,
    PokemonRedStateReader,
    ReadOnlyCartridgeRam,
)
from pokemon_red_completion.private_artifacts import (
    PrivateArtifactRoot,
    SealedRecordSummary,
    open_private_root,
    validate_private_record,
)
from pokemon_red_completion.provenance import (
    canonical_sha256,
    detect_source_identity,
    require_clean_source,
    require_published_source,
)
from pokemon_red_completion.red_boxed_level_evolution import (
    BoundedEvolutionTrainingResult,
    RedBoxedLevelEvolutionAdapter,
)
from pokemon_red_completion.red_dual_capability_curriculum_runtime import (
    BoundRedDualCapabilityScenario,
    RedSemanticVenueCaptureAdapter,
    SemanticCaptureReadiness,
    SemanticCaptureVenue,
    SemanticVenueAreaExecutor,
    build_red_dual_capability_scenario,
    dependency_specimen_ledger,
)
from pokemon_red_completion.red_goal_context import build_red_goal_context_runtime
from pokemon_red_completion.red_living_dex_dependency_curriculum import (
    DependencySpecimenLedger,
    RedDualCapabilityOutcome,
    red_dual_capability_scenario_specs,
)
from pokemon_red_completion.red_living_dex_multifamily_curriculum import (
    RedMultifamilyContext,
    inventory_red_multifamily_contexts,
)
from pokemon_red_completion.red_team_training import run_red_team_balancing
from pokemon_red_completion.rom import verify_rom
from pokemon_red_completion.runtime_identity import (
    RuntimeIdentity,
    build_runtime_identity,
    require_pyboy_import_origins,
)
from pokemon_red_completion.strategic_navigation_scenario_runtime import (
    StrategicScenarioRouteWorld,
)
from pokemon_red_completion.surge import DEFAULT_SURGE_TIMING, LiveWildEncounterExecutor

LANE_ID = "red-living-dex-multifamily-option-value-curriculum-v3"
RUNNER_RELATIVE = "scripts/run_red_living_dex_multifamily_train_trial.py"
RESULT_SCHEMA = "pokemon.red.living-dex-multifamily-train-trial-result.v1"
FAILURE_SCHEMA = "pokemon.red.living-dex-multifamily-train-trial-failure.v1"
CLAIM_SCHEMA = "pokemon.red.private-living-dex-multifamily-train-trial-claim.v1"
TERMINAL_SCHEMA = "pokemon.red.private-living-dex-multifamily-train-trial-terminal.v1"
CLAIM_KIND = "red-living-dex-multifamily-train-trial-claim-v1"
TERMINAL_KIND = "red-living-dex-multifamily-train-trial-terminal-v1"

FREEZE_RECEIPT_PATH = (
    PROJECT_ROOT / "docs/evidence/red-living-dex-multifamily-pilot-freeze-result-v3-2026-08-25.json"
)
FREEZE_RECEIPT_SHA256 = "27a7189902d084e03cdfd9394dbd2ccb9a79c0db6acff8b9278e4fdb5b5fc0e1"
FROZEN_PLAN_SHA256 = "50327b728764affdd08e033c3ccc19f60466c0b3caeb8df44a5dd26c20880947"
FROZEN_PLAN_MANIFEST_SHA256 = "763951ca0d55fba92ae9f7257ded1136d7568865496de6ff19fb464fab2a8a47"
FROZEN_SOURCE_COMMIT = "60710d6b92f9dfc04d87d2302a4e0c96e84df4ba"
FROZEN_SOURCE_BUNDLE_SHA256 = "ae92c1bc710603d9991be52dcc55c8374bef40139a29cc53542bfa5e49bb76fc"
REGISTRY_SOURCE_COMMIT = "74922cc9faa793bae4f9daf03627e8621297b038"
REGISTRY_SHA256 = "7f2208345403e7293d5fe69a8d99b39f7a5e3c5a4ca8675fbc3ffb99acf2db0b"
CONTEXT_CATALOG_SHA256 = "f913158ffc3fd9d9c9cfd89ee42abe819a9bc3139901df603a017182df6f3959"
CONTEXT_PLAN_SHA256 = "09af29ba008ea24e16be75b64a8ff91e69ee4b32abc767bf01a90f937d45ff51"
SELECTED_TRAIN_TRIAL_ORDINAL = 0
FROZEN_SUPPORT_SHA256S = {
    "scripts/freeze_red_living_dex_multifamily_pilot.py": (
        "2baa18c96f80e30b87c3c439865a5cb7f07fa127946d51be14af1be3360633df"
    ),
    "scripts/freeze_red_living_dex_multifamily_pilot_v3.py": (
        "9ebcc196ce283067121582af9f80513a8f9a4fc6b771d0dfe04b495d17477563"
    ),
    "scripts/run_red_dual_capability_preflight.py": (
        "51f544654f9720307f9ce9bc82240b9ff0de21e1f99e9de7cea1fd66a56a33c5"
    ),
}

_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_GIT_COMMIT = re.compile(r"[0-9a-f]{40}\Z")
_CAPABILITY_ORDER = (GoalKind.ACQUIRE_SPECIES, GoalKind.EVOLVE_SPECIES)
_PLAN_KEYS = {
    "schema",
    "lane_id",
    "status",
    "source_commit",
    "source_bundle_sha256",
    "rom_sha256",
    "registry_sha256",
    "context_catalog_sha256",
    "context_plan_sha256",
    "inventory",
    "curriculum",
    "trials",
    "controller_actions",
    "teacher_queries",
    "model_predictions",
    "outcomes_observed",
    "roots_claimed",
    "plan_sha256",
}
_TRIAL_KEYS = {
    "partition",
    "context_identity_sha256",
    "root_consumption_sha256",
    "family_identity_sha256",
    "candidate_index",
    "candidate_rows",
    "mechanics",
}

# The first frozen intervention is acquisition.  Keep its live falsifier tight;
# the unselected evolution capability still has to qualify from the same reset.
_ACQUIRE_MAX_CONTROLLER_ACTIONS = 5_000
_ACQUIRE_MAX_CONTROLLER_FRAMES = 4_000_000
_EVOLVE_MAX_CONTROLLER_ACTIONS = 50_000
_EVOLVE_MAX_CONTROLLER_FRAMES = 20_000_000


class RedMultifamilyTrainTrialError(RuntimeError):
    """One sanitized fail-closed stage for the frozen-trial coordinator."""

    def __init__(self, stage: str) -> None:
        self.stage = stage if re.fullmatch(r"[a-z0-9_]+", stage) else "unexpected_failure"
        super().__init__(self.stage)


class _Parser(argparse.ArgumentParser):
    def error(self, message: str) -> Never:
        del message
        raise RedMultifamilyTrainTrialError("arguments")


class _ClaimGatedController:
    """Make controller dispatch structurally unreachable before durable claim."""

    __slots__ = ("_armed", "_delegate", "attempted_before_claim")

    def __init__(self, delegate: object) -> None:
        if not callable(getattr(delegate, "execute", None)):
            raise TypeError("claim-gated controller needs an executor")
        self._delegate = delegate
        self._armed = False
        self.attempted_before_claim = 0

    def arm(self) -> None:
        if self._armed:
            raise RedMultifamilyTrainTrialError("preaction_claim_authentication")
        self._armed = True

    def execute(self, action: object) -> object:
        if not self._armed:
            self.attempted_before_claim += 1
            raise RedMultifamilyTrainTrialError("controller_input_before_claim")
        return self._delegate.execute(action)


class _ClaimGatedFrames:
    """Make emulator time advancement structurally unreachable before claim."""

    __slots__ = (
        "_armed",
        "_delegate",
        "attempted_buttons_before_claim",
        "attempted_frames_before_claim",
    )

    def __init__(self, delegate: object) -> None:
        if not callable(getattr(delegate, "tick", None)):
            raise TypeError("claim-gated frames need an emulator port")
        self._delegate = delegate
        self._armed = False
        self.attempted_buttons_before_claim = 0
        self.attempted_frames_before_claim = 0

    def arm(self) -> None:
        if self._armed:
            raise RedMultifamilyTrainTrialError("preaction_claim_authentication")
        self._armed = True

    def tick(self, frames: int) -> None:
        if not self._armed:
            if type(frames) is int and frames > 0:  # noqa: E721
                self.attempted_frames_before_claim += frames
            raise RedMultifamilyTrainTrialError("frame_advance_before_claim")
        self._delegate.tick(frames)

    def press(self, button: str) -> None:
        if not self._armed:
            self.attempted_buttons_before_claim += 1
            raise RedMultifamilyTrainTrialError("controller_input_before_claim")
        self._delegate.press(button)

    def release(self, button: str) -> None:
        if not self._armed:
            self.attempted_buttons_before_claim += 1
            raise RedMultifamilyTrainTrialError("controller_input_before_claim")
        self._delegate.release(button)

    def read_cartridge_ram_u8(self, bank: int, address: int) -> int:
        """Preserve bounded read-only storage observation before the claim."""

        reader = getattr(self._delegate, "read_cartridge_ram_u8", None)
        if not callable(reader):
            raise TypeError("claim-gated frames lack cartridge-RAM access")
        value = reader(bank, address)
        if type(value) is not int or not 0 <= value <= 0xFF:  # noqa: E721
            raise TypeError("cartridge-RAM reader returned an invalid byte")
        return value

    def __getattr__(self, name: str) -> object:
        return getattr(self._delegate, name)


@dataclass(frozen=True, slots=True)
class _PublicGate:
    source_commit: str
    source_bundle_sha256: str
    runner_sha256: str
    runtime: RuntimeIdentity


@dataclass(frozen=True, slots=True)
class _FrozenTrial:
    ordinal: int
    document: Mapping[str, object]
    trial_sha256: str

    @property
    def partition(self) -> str:
        return str(self.document["partition"])

    @property
    def context_identity_sha256(self) -> str:
        return str(self.document["context_identity_sha256"])

    @property
    def root_consumption_sha256(self) -> str:
        return str(self.document["root_consumption_sha256"])

    @property
    def family_identity_sha256(self) -> str:
        return str(self.document["family_identity_sha256"])

    @property
    def candidate_index(self) -> int:
        value = self.document["candidate_index"]
        if type(value) is not int:  # noqa: E721 - reject bool
            raise RedMultifamilyTrainTrialError("frozen_trial_authentication")
        return value

    @property
    def candidate_rows(self) -> tuple[dict[str, int | str], ...]:
        raw = self.document["candidate_rows"]
        if not isinstance(raw, list) or any(not isinstance(row, dict) for row in raw):
            raise RedMultifamilyTrainTrialError("frozen_trial_authentication")
        return tuple(dict(row) for row in raw)  # type: ignore[arg-type]


@dataclass(frozen=True, slots=True)
class _FrozenPlan:
    store: PrivateArtifactRoot
    summary: SealedRecordSummary
    document: Mapping[str, object]
    selected_trial: _FrozenTrial


@dataclass(frozen=True, slots=True)
class _TrialClaim:
    trial_identity_sha256: str
    execution_identity_sha256: str
    record_id: str
    summary: SealedRecordSummary


@dataclass(frozen=True, slots=True)
class _TrialTerminal:
    public: Mapping[str, object]
    settled: bool


def _parser() -> argparse.ArgumentParser:
    parser = _Parser(description=__doc__)
    parser.add_argument("--expected-source-commit", required=True)
    parser.add_argument("--context-catalog", type=Path, required=True)
    parser.add_argument("--context-plan", type=Path, required=True)
    parser.add_argument("--private-root", type=Path, required=True)
    parser.add_argument("--rom", type=Path)
    parser.add_argument("--watch", action="store_true")
    parser.add_argument("--speed", type=int, choices=(1, 2, 4))
    return parser


def main(argv: list[str] | None = None) -> int:
    stage = "arguments"
    try:
        args = _parser().parse_args(argv)
        if args.speed is not None and not args.watch:
            raise RedMultifamilyTrainTrialError("arguments")
        stage = "public_source_authentication"
        gate = _authenticate_public_gate(args)
        stage = "frozen_plan_authentication"
        frozen = _load_frozen_plan(args)
        stage = "selected_context_authentication"
        inputs = _authenticate_frozen_inputs(args, gate, frozen)
        stage = "selected_trial_execution"
        terminal = _execute_selected_trial(args, gate, frozen, inputs)
        print(
            json.dumps(
                terminal.public,
                allow_nan=False,
                separators=(",", ":"),
                sort_keys=True,
            )
        )
        return 0 if terminal.settled else 2
    except RedMultifamilyTrainTrialError as error:
        failure_stage = error.stage
    except BaseException:
        failure_stage = stage
    print(
        json.dumps(
            _failure_receipt(failure_stage),
            allow_nan=False,
            separators=(",", ":"),
            sort_keys=True,
        )
    )
    return 1


def _authenticate_public_gate(args: argparse.Namespace) -> _PublicGate:
    """Authenticate published source and V3 evidence before private access."""

    try:
        support._require_script_import_origins()
        support._require_project_import_origins()
        receipt = read_tracked_public_evidence(
            FREEZE_RECEIPT_PATH,
            repository_root=PROJECT_ROOT,
            expected_sha256=FREEZE_RECEIPT_SHA256,
        )
    except (PublicExecutionManifestError, TypeError, ValueError):
        raise RedMultifamilyTrainTrialError("public_evidence_authentication") from None
    if (
        receipt.get("lane_id") != LANE_ID
        or receipt.get("status") != freezer_v3.PROTOCOL.success_status
        or not isinstance(receipt.get("artifacts"), dict)
        or receipt["artifacts"].get("plan_sha256") != FROZEN_PLAN_SHA256  # type: ignore[union-attr]
        or receipt["artifacts"].get("plan_manifest_sha256")  # type: ignore[union-attr]
        != FROZEN_PLAN_MANIFEST_SHA256
    ):
        raise RedMultifamilyTrainTrialError("public_evidence_authentication")
    source = detect_source_identity(PROJECT_ROOT, include_untracked=True)
    require_clean_source(source)
    require_published_source(PROJECT_ROOT, source)
    expected_commit = _commit(args.expected_source_commit, "source")
    bundle = working_source_bundle_sha256(PROJECT_ROOT)
    runner_sha256 = hashlib.sha256((PROJECT_ROOT / RUNNER_RELATIVE).read_bytes()).hexdigest()
    if (
        source.git_commit != expected_commit
        or bundle != FROZEN_SOURCE_BUNDLE_SHA256
        or any(
            hashlib.sha256((PROJECT_ROOT / relative).read_bytes()).hexdigest() != expected
            for relative, expected in FROZEN_SUPPORT_SHA256S.items()
        )
        or os.environ.get(ENCOUNTER_LOG_VARIABLE, "").strip()
    ):
        raise RedMultifamilyTrainTrialError("public_source_authentication")
    runtime = build_runtime_identity()
    return _PublicGate(expected_commit, bundle, runner_sha256, runtime)


def _load_frozen_plan(args: argparse.Namespace) -> _FrozenPlan:
    """Open only the exact sealed V3 plan and preselect train ordinal zero."""

    store = open_private_root(args.private_root, repository_root=PROJECT_ROOT)
    record = store.find_sealed_record(
        freezer_v3.PLAN_RECORD_ID,
        expected_kind=freezer_v3.PLAN_RECORD_KIND,
    )
    if record is None or record.summary.manifest_sha256 != FROZEN_PLAN_MANIFEST_SHA256:
        raise RedMultifamilyTrainTrialError("frozen_plan_authentication")
    document = record.read()
    _validate_plan_document(document)
    trials = document["trials"]
    assert isinstance(trials, list)  # established by _validate_plan_document
    selected_document = trials[SELECTED_TRAIN_TRIAL_ORDINAL]
    assert isinstance(selected_document, dict)
    selected = _FrozenTrial(
        SELECTED_TRAIN_TRIAL_ORDINAL,
        selected_document,
        canonical_sha256(selected_document),
    )
    if selected.partition != "train" or selected.candidate_index != 0:
        raise RedMultifamilyTrainTrialError("frozen_trial_authentication")
    return _FrozenPlan(store, record.summary, document, selected)


def _validate_plan_document(document: Mapping[str, object]) -> None:
    if set(document) != _PLAN_KEYS:
        raise RedMultifamilyTrainTrialError("frozen_plan_authentication")
    payload = {key: value for key, value in document.items() if key != "plan_sha256"}
    if (
        document.get("schema") != freezer_v3.PLAN_SCHEMA
        or document.get("lane_id") != LANE_ID
        or document.get("status") != "frozen_before_prediction_action_or_outcome"
        or document.get("source_commit") != FROZEN_SOURCE_COMMIT
        or document.get("source_bundle_sha256") != FROZEN_SOURCE_BUNDLE_SHA256
        or document.get("rom_sha256") != POKEMON_RED_US_REV_0.sha256
        or document.get("registry_sha256") != REGISTRY_SHA256
        or document.get("context_catalog_sha256") != CONTEXT_CATALOG_SHA256
        or document.get("context_plan_sha256") != CONTEXT_PLAN_SHA256
        or document.get("plan_sha256") != FROZEN_PLAN_SHA256
        or canonical_sha256(payload) != FROZEN_PLAN_SHA256
        or any(
            document.get(field) != 0
            for field in (
                "controller_actions",
                "teacher_queries",
                "model_predictions",
                "outcomes_observed",
                "roots_claimed",
            )
        )
    ):
        raise RedMultifamilyTrainTrialError("frozen_plan_authentication")
    trials = document.get("trials")
    if not isinstance(trials, list) or len(trials) != 16:
        raise RedMultifamilyTrainTrialError("frozen_plan_authentication")
    allowed_rows = {
        canonical_sha256([dict(row) for row in scenario.policy_rows()])
        for scenario in red_dual_capability_scenario_specs()
    }
    roots: list[str] = []
    contexts: list[str] = []
    families: dict[str, set[str]] = {"train": set(), "development": set()}
    candidates: dict[str, Counter[int]] = {
        "train": Counter(),
        "development": Counter(),
    }
    for ordinal, raw in enumerate(trials):
        if not isinstance(raw, dict) or set(raw) != _TRIAL_KEYS:
            raise RedMultifamilyTrainTrialError("frozen_trial_authentication")
        partition = raw.get("partition")
        expected_partition = "train" if ordinal < 8 else "development"
        index = raw.get("candidate_index")
        rows = raw.get("candidate_rows")
        mechanics = raw.get("mechanics")
        if (
            partition != expected_partition
            or type(index) is not int  # noqa: E721
            or index not in {0, 1}
            or not isinstance(rows, list)
            or len(rows) != 2
            or any(not isinstance(row, dict) for row in rows)
            or canonical_sha256(rows) not in allowed_rows
            or not isinstance(mechanics, dict)
        ):
            raise RedMultifamilyTrainTrialError("frozen_trial_authentication")
        root = _sha(raw.get("root_consumption_sha256"), "frozen root")
        context = _sha(raw.get("context_identity_sha256"), "frozen context")
        family = _sha(raw.get("family_identity_sha256"), "frozen family")
        roots.append(root)
        contexts.append(context)
        families[expected_partition].add(family)
        candidates[expected_partition][index] += 1
    if (
        len(set(roots)) != 16
        or len(set(contexts)) != 16
        or len(families["train"]) != 1
        or len(families["development"]) != 1
        or not families["train"].isdisjoint(families["development"])
        or candidates["train"] != Counter({0: 4, 1: 4})
        or candidates["development"] != Counter({0: 4, 1: 4})
    ):
        raise RedMultifamilyTrainTrialError("frozen_plan_authentication")


def _authenticate_frozen_inputs(
    args: argparse.Namespace,
    gate: _PublicGate,
    frozen: _FrozenPlan,
) -> tuple[Path, str, bytes, tuple[freezer._AuthenticatedContext, ...], str, str]:
    """Authenticate the historical inventory only after trial preselection."""

    if frozen.selected_trial.ordinal != SELECTED_TRAIN_TRIAL_ORDINAL:
        raise RedMultifamilyTrainTrialError("frozen_trial_authentication")
    bound_args = SimpleNamespace(
        rom=args.rom,
        registry_source_commit=REGISTRY_SOURCE_COMMIT,
        expected_registry_sha256=REGISTRY_SHA256,
        context_catalog=args.context_catalog,
        expected_context_catalog_sha256=CONTEXT_CATALOG_SHA256,
        context_plan=args.context_plan,
        expected_context_plan_sha256=CONTEXT_PLAN_SHA256,
    )
    try:
        result = freezer._authenticate_inputs(
            bound_args,
            gate.source_commit,
            gate.source_bundle_sha256,
        )
    except Exception:
        raise RedMultifamilyTrainTrialError("selected_context_authentication") from None
    _rom_path, rom_sha256, _rom_bytes, contexts, catalog_sha256, plan_sha256 = result
    _selected_context(contexts, frozen.selected_trial)
    if (
        rom_sha256 != POKEMON_RED_US_REV_0.sha256
        or catalog_sha256 != CONTEXT_CATALOG_SHA256
        or plan_sha256 != CONTEXT_PLAN_SHA256
    ):
        raise RedMultifamilyTrainTrialError("selected_context_authentication")
    return result


def _execute_selected_trial(
    args: argparse.Namespace,
    gate: _PublicGate,
    frozen: _FrozenPlan,
    inputs: tuple[Path, str, bytes, tuple[freezer._AuthenticatedContext, ...], str, str],
) -> _TrialTerminal:
    rom_path, rom_sha256, rom_bytes, contexts, _catalog_sha256, _plan_sha256 = inputs
    trial = frozen.selected_trial
    target = _selected_context(contexts, trial)
    require_pyboy_import_origins(gate.runtime)
    route_world = StrategicScenarioRouteWorld.from_rom(rom_bytes)
    maximum_actions, maximum_frames = _selected_limits(trial.candidate_index)
    with PyBoyAdapter(
        rom_path,
        watch=bool(args.watch),
        speed=args.speed,
        expected_rom=POKEMON_RED_US_REV_0,
    ) as emulator:
        require_pyboy_import_origins(gate.runtime)
        emulator.load_state_bytes(target.capture.state_bytes)
        require_pyboy_import_origins(gate.runtime)
        bounded_frames = WindowedFrameBudgetController(
            emulator,
            maximum_frames_per_window=maximum_frames,
            maximum_total_frames=maximum_frames,
        )
        frames = _ClaimGatedFrames(bounded_frames)
        if not isinstance(frames, ReadOnlyCartridgeRam):
            raise RedMultifamilyTrainTrialError("cartridge_ram_observation_port")
        frame_safe = FrameSafeExecutor(
            frames,
            DEFAULT_NEW_GAME_TIMING.controller_timing(),
        )
        limited = HardCompositionActionLimiter(
            frame_safe,
            maximum_actions_per_decision=maximum_actions,
            maximum_episode_actions=maximum_actions,
        )
        controller_gate = _ClaimGatedController(limited)
        actions = CountingExecutor(controller_gate)
        reader = PokemonRedStateReader(frames)
        context_runtime = build_red_goal_context_runtime(
            profile=target.profile,
            capture=target.capture,
            emulator=frames,
            reader=reader,
        )
        observation = context_runtime.adapter.observe()
        _authenticate_historical_replay(target, context_runtime, actions, observation)
        traversal = Gen1TraversalObserver(
            reader,
            hazard_projector=Gen1TrainerSightProjector(rom_bytes, reader),
            capability_projector=lambda raw: gen1_field_capabilities(frames, raw),
        )
        start = traversal.observe()
        facts, mechanics = freezer._context_mechanics(
            observation.collection_observation,
            observation.raw,
            start,
            reader,
            route_world,
            reset_state_sha256=target.capture.state_sha256,
            context_identity_sha256=target.context_identity_sha256,
            rom_sha256=rom_sha256,
            source_bundle=FROZEN_SOURCE_BUNDLE_SHA256,
        )
        mechanic = _selected_mechanic(mechanics, trial)
        context = RedMultifamilyContext(
            target.context_identity_sha256,
            target.root_consumption_sha256,
            "train",
            observation.collection_observation,
            facts,
            True,
        )
        inventory = inventory_red_multifamily_contexts((context,))
        opportunities = tuple(
            item
            for item in inventory.available_opportunities
            if item.family_identity_sha256 == trial.family_identity_sha256
        )
        if len(opportunities) != 1 or opportunities[0].policy_rows() != trial.candidate_rows:
            raise RedMultifamilyTrainTrialError("frozen_menu_authentication")
        before_ledger = dependency_specimen_ledger(observation.collection_observation)
        scenarios = tuple(
            item
            for item in red_dual_capability_scenario_specs()
            if item.before.precursor_count
            == before_ledger.count(mechanic.species_binding.precursor_species_ref)
            and item.before.evolved_count
            == before_ledger.count(mechanic.species_binding.evolved_species_ref)
        )
        if len(scenarios) != 1 or scenarios[0].policy_rows() != trial.candidate_rows:
            raise RedMultifamilyTrainTrialError("frozen_menu_authentication")
        scenario = scenarios[0]
        field_actions = Gen1FieldMovePort(
            actions,
            reader,
            frames,
            cut_block_swaps={swap.before: swap.after for swap in route_world.rules.cut_block_swaps},
        )
        venue = mechanic.capture_plan.venue
        if not isinstance(venue, SemanticCaptureVenue):
            raise RedMultifamilyTrainTrialError("frozen_mechanics_authentication")
        live_capture = LiveWildEncounterExecutor(
            frames,
            actions,
            reader,
            DEFAULT_SURGE_TIMING,
            label="frozen multifamily target capture",
        )
        area = SemanticVenueAreaExecutor(
            delegate=live_capture,
            actions=field_actions,
            reader=reader,
            emulator=frames,
            walker=venue.fresh_walk_to_grass(),
        )
        route_interruptions = Gen1RouteInterruptionHandler(
            field_actions,
            reader,
            maximum_flees=64,
            maximum_trainer_battles=8,
            stabilization_frames=120,
            route_name="frozen multifamily capture route",
        )
        capture_adapter = RedSemanticVenueCaptureAdapter(
            mechanic.capture_plan,
            field_actions,
            traversal,
            area,
            interruption_handler=route_interruptions,
            replanner=route_world.replanner(),
        )
        capture_readiness = SemanticCaptureReadiness(
            reset_state_sha256=target.capture.state_sha256,
            ordinary_capture_items=_ordinary_capture_items(observation.raw.bag_items),
            immediate_capture_slots=observation.immediate_capture_slots,
            input_ready=observation.input_ready,
            battle_active=observation.raw.battle_state != 0,
        )
        acquire = capture_adapter.qualify(scenario, before_ledger, capture_readiness)

        def train_evolution(
            precursor_species_id: int,
            evolved_species_id: int,
        ) -> BoundedEvolutionTrainingResult:
            _report, battles, heals = run_red_team_balancing(
                actions,
                reader,
                frames,
                policy=MANSION_TEAM_POLICY,
                venues=(
                    ROUTE_11_TRAINING_VENUE,
                    DIGLETTS_CAVE_TRAINING_VENUE,
                    MANSION_TRAINING_VENUE,
                ),
                intent=MANSION_BALANCED_TEAM_TRAINING_INTENT,
                flee_timing=MANSION_TRAINING_FLEE_TIMING,
                hideout_timing=DEFAULT_HIDEOUT_TIMING,
                flee_func=_flee,
                volatile_enemy_species=MANSION_VOLATILE_ENEMY_SPECIES,
                escort_enemy_species=MANSION_ESCORT_ENEMY_SPECIES,
                max_consecutive_flees=MANSION_MAX_CONSECUTIVE_FLEES,
                cancel_interval=MANSION_LEVEL_UP_MOVE_CANCEL_INTERVAL,
                evolution_target=(precursor_species_id, evolved_species_id),
                report_label="frozen multifamily bounded evolution",
                checkpoint_count=1,
            )
            return BoundedEvolutionTrainingResult(battles, heals)

        evolution_adapter = RedBoxedLevelEvolutionAdapter(
            mechanic.evolution_plan,
            actions,
            reader,
            traversal,
            lambda: context_runtime.adapter.observe().collection_observation,
            train_evolution,
            replanner=route_world.replanner(),
        )
        evolve = evolution_adapter.qualify(scenario, before_ledger)
        bound = build_red_dual_capability_scenario(
            scenario,
            mechanic.species_binding,
            before_ledger,
            (acquire, evolve),
        )
        if bound.policy_rows() != trial.candidate_rows:
            raise RedMultifamilyTrainTrialError("frozen_menu_authentication")
        if (
            actions.actions_executed != 0
            or limited.attempted_actions != 0
            or frames.frames_executed != 0
            or controller_gate.attempted_before_claim != 0
            or frames.attempted_buttons_before_claim != 0
            or frames.attempted_frames_before_claim != 0
            or emulator.pressed_buttons
        ):
            raise RedMultifamilyTrainTrialError("preclaim_zero_effect_authentication")
        claim = _claim_trial_and_root(gate, frozen, trial)
        frames.arm()
        controller_gate.arm()
        status, interruption_stage, outcome, execution_summary = _run_frozen_intervention(
            bound,
            trial.candidate_index,
            observe_after=lambda: dependency_specimen_ledger(
                context_runtime.adapter.observe().collection_observation
            ),
        )
        terminal = _publish_terminal(
            frozen,
            trial,
            claim,
            status=status,
            interruption_stage=interruption_stage,
            outcome=outcome,
            execution_summary=execution_summary,
            controller_actions=actions.actions_executed,
            attempted_controller_actions=limited.attempted_actions,
            emulator_frames_advanced=frames.frames_executed,
        )
    require_pyboy_import_origins(gate.runtime)
    if verify_rom(rom_path).sha256 != rom_sha256:
        raise RedMultifamilyTrainTrialError("protected_input_integrity")
    post_source = detect_source_identity(PROJECT_ROOT, include_untracked=True)
    require_clean_source(post_source)
    if (
        post_source.git_commit != gate.source_commit
        or working_source_bundle_sha256(PROJECT_ROOT) != gate.source_bundle_sha256
        or hashlib.sha256((PROJECT_ROOT / RUNNER_RELATIVE).read_bytes()).hexdigest()
        != gate.runner_sha256
    ):
        raise RedMultifamilyTrainTrialError("protected_source_integrity")
    return terminal


def _selected_context(
    contexts: tuple[freezer._AuthenticatedContext, ...],
    trial: _FrozenTrial,
) -> freezer._AuthenticatedContext:
    matches = tuple(
        item for item in contexts if item.context_identity_sha256 == trial.context_identity_sha256
    )
    if (
        len(matches) != 1
        or matches[0].assignment.partition != "train"
        or matches[0].root_consumption_sha256 != trial.root_consumption_sha256
        or not matches[0].root_available
    ):
        raise RedMultifamilyTrainTrialError("selected_context_authentication")
    return matches[0]


def _selected_mechanic(
    mechanics: tuple[freezer._FamilyMechanics, ...],
    trial: _FrozenTrial,
) -> freezer._FamilyMechanics:
    matches = tuple(
        item for item in mechanics if item.family_identity_sha256 == trial.family_identity_sha256
    )
    if len(matches) != 1 or matches[0].private_dict() != trial.document.get("mechanics"):
        raise RedMultifamilyTrainTrialError("frozen_mechanics_authentication")
    return matches[0]


def _authenticate_historical_replay(
    target: freezer._AuthenticatedContext,
    context_runtime: object,
    actions: CountingExecutor,
    observation: object,
) -> None:
    enumerator = getattr(context_runtime, "enumerator", None)
    if not callable(enumerator):
        raise RedMultifamilyTrainTrialError("historical_context_replay")
    bindings = enumerator(actions).enumerate(observation)
    historical = ordered_goal_manager_question(
        assignment_id=target.assignment.assignment_id,
        decision_index=0,
        situation=observation.situation,
        opportunities=bindings.opportunities,
    )
    if (
        historical.ordered_policy_input_sha256 != target.catalog_entry.question_sha256
        or historical.policy_context_sha256 != target.catalog_entry.policy_context_sha256
        or historical.available_menu_sha256 != target.catalog_entry.available_menu_sha256
        or goal_binding_manifest_sha256(bindings) != target.catalog_entry.binding_manifest_sha256
        or tuple(item.kind for item in bindings.bindings)
        != target.catalog_entry.available_goal_kinds
    ):
        raise RedMultifamilyTrainTrialError("historical_context_replay")


def _claim_trial_and_root(
    gate: _PublicGate,
    frozen: _FrozenPlan,
    trial: _FrozenTrial,
) -> _TrialClaim:
    """Durably consume local trial and global physical root before input."""

    trial_identity = canonical_sha256(
        {
            "schema": "pokemon.red.living-dex-multifamily-train-trial-identity.v1",
            "plan_sha256": FROZEN_PLAN_SHA256,
            "trial_ordinal": trial.ordinal,
            "trial_sha256": trial.trial_sha256,
        }
    )
    execution_identity = canonical_sha256(
        {
            "schema": "pokemon.red.living-dex-multifamily-train-trial-execution.v1",
            "lane_id": LANE_ID,
            "source_commit": gate.source_commit,
            "source_bundle_sha256": gate.source_bundle_sha256,
            "runner_sha256": gate.runner_sha256,
            "runtime_sha256": gate.runtime.sha256,
            "plan_sha256": FROZEN_PLAN_SHA256,
            "plan_manifest_sha256": frozen.summary.manifest_sha256,
            "trial_identity_sha256": trial_identity,
            "root_consumption_sha256": trial.root_consumption_sha256,
        }
    )
    record_id = f"red-multifamily-train-claim-{trial_identity[:24]}"
    terminal_id = f"red-multifamily-train-terminal-{trial_identity[:24]}"
    claim_document = {
        "schema": CLAIM_SCHEMA,
        "lane_id": LANE_ID,
        "status": "trial_and_candidate_committed_before_controller_input",
        "source_commit": gate.source_commit,
        "source_bundle_sha256": gate.source_bundle_sha256,
        "runner_sha256": gate.runner_sha256,
        "runtime_sha256": gate.runtime.sha256,
        "plan_sha256": FROZEN_PLAN_SHA256,
        "plan_manifest_sha256": frozen.summary.manifest_sha256,
        "trial_ordinal": trial.ordinal,
        "trial_sha256": trial.trial_sha256,
        "trial_identity_sha256": trial_identity,
        "execution_identity_sha256": execution_identity,
        "partition": trial.partition,
        "context_identity_sha256": trial.context_identity_sha256,
        "root_consumption_sha256": trial.root_consumption_sha256,
        "family_identity_sha256": trial.family_identity_sha256,
        "candidate_index": trial.candidate_index,
        "candidate_rows": [dict(row) for row in trial.candidate_rows],
        "controller_actions": 0,
        "teacher_queries": 0,
        "model_predictions": 0,
        "outcomes_observed": 0,
        "retry_allowed": False,
    }
    validate_private_record(claim_document)
    expected_root_claim = {
        "schema": "pokemon.red.fresh-composition-root-claim.v1",
        "root_consumption_sha256": trial.root_consumption_sha256,
        "execution_identity_sha256": execution_identity,
        "source_commit": gate.source_commit,
        "runner_sha256": gate.runner_sha256,
    }
    registry = open_fixed_account_claim_registry()
    with fixed_account_claim_registry_lease(registry, exclusive=True):
        if (
            frozen.store.inspect_sealed_record_metadata(
                record_id,
                expected_kind=CLAIM_KIND,
            )
            is not None
            or frozen.store.inspect_sealed_record_metadata(
                terminal_id,
                expected_kind=TERMINAL_KIND,
            )
            is not None
        ):
            raise RedMultifamilyTrainTrialError("frozen_trial_already_consumed")
        if not root_claim_is_available(registry, trial.root_consumption_sha256):
            raise RedMultifamilyTrainTrialError("frozen_root_already_consumed")
        claim_record = frozen.store.publish_sealed_record(
            record_id,
            kind=CLAIM_KIND,
            record=claim_document,
        )
        write_root_claim(
            registry,
            root_consumption_sha256=trial.root_consumption_sha256,
            execution_identity_sha256=execution_identity,
            source_commit=gate.source_commit,
            runner_sha256=gate.runner_sha256,
        )
        if (
            read_root_claim(registry, trial.root_consumption_sha256) != expected_root_claim
            or claim_record.read() != claim_document
        ):
            raise RedMultifamilyTrainTrialError("preaction_claim_authentication")
    return _TrialClaim(trial_identity, execution_identity, record_id, claim_record.summary)


def _run_frozen_intervention(
    bound: BoundRedDualCapabilityScenario,
    candidate_index: int,
    *,
    observe_after: object,
) -> tuple[
    Literal["settled", "interrupted"],
    str | None,
    RedDualCapabilityOutcome,
    Mapping[str, object] | None,
]:
    """Execute the bound index once; ordinary failures become censored."""

    if not callable(observe_after):
        raise TypeError("observe_after must be callable")
    selected = bound.bind_selection(candidate_index)
    try:
        report = selected.execute()
    except Exception:
        outcome = bound.verify_outcome(
            selected_kind=_CAPABILITY_ORDER[candidate_index],
            after_ledger=None,
        )
        return "interrupted", "selected_capability_execution", outcome, None
    try:
        after = observe_after()
        if not isinstance(after, DependencySpecimenLedger):
            raise TypeError("independent observer returned no specimen ledger")
        outcome = bound.verify_outcome(
            selected_kind=_CAPABILITY_ORDER[candidate_index],
            after_ledger=after,
        )
    except Exception:
        outcome = bound.verify_outcome(
            selected_kind=_CAPABILITY_ORDER[candidate_index],
            after_ledger=None,
        )
        return "interrupted", "independent_outcome_observation", outcome, None
    # The independently observed ledger settles the causal target.  A report
    # projection is useful diagnostics, but it must never strand an already
    # claimed, valid outcome without its immutable terminal record.
    public = getattr(report, "public_dict", None)
    try:
        projected = public() if callable(public) else None
    except Exception:
        projected = None
    summary = projected if isinstance(projected, dict) else None
    return "settled", None, outcome, summary


def _publish_terminal(
    frozen: _FrozenPlan,
    trial: _FrozenTrial,
    claim: _TrialClaim,
    *,
    status: Literal["settled", "interrupted"],
    interruption_stage: str | None,
    outcome: RedDualCapabilityOutcome,
    execution_summary: Mapping[str, object] | None,
    controller_actions: int,
    attempted_controller_actions: int,
    emulator_frames_advanced: int,
) -> _TrialTerminal:
    if status == "settled" and interruption_stage is not None:
        raise RedMultifamilyTrainTrialError("terminal_authentication")
    if status == "interrupted" and interruption_stage not in {
        "selected_capability_execution",
        "independent_outcome_observation",
    }:
        raise RedMultifamilyTrainTrialError("terminal_authentication")
    terminal_document = {
        "schema": TERMINAL_SCHEMA,
        "lane_id": LANE_ID,
        "status": status,
        "interruption_stage": interruption_stage,
        "plan_sha256": FROZEN_PLAN_SHA256,
        "plan_manifest_sha256": frozen.summary.manifest_sha256,
        "trial_ordinal": trial.ordinal,
        "trial_sha256": trial.trial_sha256,
        "trial_identity_sha256": claim.trial_identity_sha256,
        "execution_identity_sha256": claim.execution_identity_sha256,
        "claim_record_manifest_sha256": claim.summary.manifest_sha256,
        "partition": trial.partition,
        "context_identity_sha256": trial.context_identity_sha256,
        "root_consumption_sha256": trial.root_consumption_sha256,
        "family_identity_sha256": trial.family_identity_sha256,
        "candidate_index": trial.candidate_index,
        "candidate_rows": [dict(row) for row in trial.candidate_rows],
        "outcome": outcome.private_dict(),
        "execution_summary": (None if execution_summary is None else dict(execution_summary)),
        "controller_actions": controller_actions,
        "attempted_controller_actions": attempted_controller_actions,
        "emulator_frames_advanced": emulator_frames_advanced,
        "selected_capabilities_started": 1,
        "teacher_queries": 0,
        "model_predictions": 0,
        "retry_allowed": False,
    }
    validate_private_record(terminal_document)
    terminal_id = f"red-multifamily-train-terminal-{claim.trial_identity_sha256[:24]}"
    terminal_record = frozen.store.publish_sealed_record(
        terminal_id,
        kind=TERMINAL_KIND,
        record=terminal_document,
    )
    public = {
        "schema": RESULT_SCHEMA,
        "status": (
            "frozen_train_intervention_settled_and_independently_verified"
            if status == "settled"
            else "frozen_train_intervention_interrupted_and_censored"
        ),
        "partition": "train",
        "trial_ordinal": trial.ordinal,
        "candidate_count": 2,
        "intervention_candidate_index": trial.candidate_index,
        "candidate_rows": [dict(row) for row in trial.candidate_rows],
        "outcome": outcome.public_dict(),
        "interruption_stage": interruption_stage,
        "selected_capabilities_started": 1,
        "selected_capabilities_executed": 1 if status == "settled" else 0,
        "independent_post_transition_observation": status == "settled",
        "controller_actions": controller_actions,
        "attempted_controller_actions": attempted_controller_actions,
        "emulator_frames_advanced": emulator_frames_advanced,
        "model_predictions": 0,
        "teacher_queries": 0,
        "semantic_root_consumed": True,
        "trial_consumed": True,
        "retry_allowed": False,
        "durability": {
            "trial_claim_committed_before_controller_input": True,
            "physical_root_claim_committed_before_controller_input": True,
            "claim_manifest_sha256": claim.summary.manifest_sha256,
            "terminal_manifest_sha256": terminal_record.summary.manifest_sha256,
            "private_record_identifiers_published": 0,
        },
        "causal_train_examples_added": 1 if status == "settled" else 0,
        "verified_development_outcomes_added": 0,
        "model_fits_added": 0,
        "unseen_comparisons_added": 0,
        "authority_promotions_added": 0,
        "transfer_results_added": 0,
        "private_path_fields": 0,
        "private_identity_fields": 0,
        "private_species_fields": 0,
        "private_route_fields": 0,
        "claim_boundary": (
            "one causal train intervention for option-value fitting; no model-quality, "
            "promotion, completion, or transfer claim"
        ),
    }
    return _TrialTerminal(public, status == "settled")


def _selected_limits(candidate_index: int) -> tuple[int, int]:
    if candidate_index == 0:
        return _ACQUIRE_MAX_CONTROLLER_ACTIONS, _ACQUIRE_MAX_CONTROLLER_FRAMES
    if candidate_index == 1:
        return _EVOLVE_MAX_CONTROLLER_ACTIONS, _EVOLVE_MAX_CONTROLLER_FRAMES
    raise RedMultifamilyTrainTrialError("frozen_trial_authentication")


def _ordinary_capture_items(value: object) -> int:
    if not isinstance(value, tuple):
        raise RedMultifamilyTrainTrialError("capture_capability_authentication")
    inventory: dict[int, int] = {}
    for row in value:
        if (
            not isinstance(row, tuple)
            or len(row) != 2
            or any(type(item) is not int for item in row)  # noqa: E721
        ):
            raise RedMultifamilyTrainTrialError("capture_capability_authentication")
        item_id, quantity = row
        if not 0 <= item_id <= 0xFF or not 0 <= quantity <= 0xFF or item_id in inventory:
            raise RedMultifamilyTrainTrialError("capture_capability_authentication")
        inventory[item_id] = quantity
    return sum(
        inventory.get(int(item), 0)
        for item in (ItemId.POKE_BALL, ItemId.GREAT_BALL, ItemId.ULTRA_BALL)
    )


def _failure_receipt(stage: str) -> dict[str, object]:
    safe = stage if re.fullmatch(r"[a-z0-9_]+", stage) else "unexpected_failure"
    return {
        "schema": FAILURE_SCHEMA,
        "status": "failed_closed",
        "failure_stage": safe,
        "claim_state": "inspect_private_trial_and_global_root_registry_before_any_retry",
        "retry_policy": "never_retry_a_claimed_trial; never_substitute_the_frozen_scenario",
        "teacher_queries": 0,
        "authority_promotions_added": 0,
        "transfer_results_added": 0,
        "private_path_fields": 0,
        "private_identity_fields": 0,
    }


def _sha(value: object, subject: str) -> str:
    if not isinstance(value, str) or _SHA256.fullmatch(value) is None:
        raise RedMultifamilyTrainTrialError(f"{subject.replace(' ', '_')}_authentication")
    return value


def _commit(value: object, subject: str) -> str:
    if not isinstance(value, str) or _GIT_COMMIT.fullmatch(value) is None:
        raise RedMultifamilyTrainTrialError(f"{subject.replace(' ', '_')}_authentication")
    return value


if __name__ == "__main__":
    raise SystemExit(main())
