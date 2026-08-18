"""Root-safe primitives for one fresh goal-manager composition episode.

The module is deliberately smaller than the live runner.  It provides hard in-flight
budgets, a title-neutral collection checkpoint, exact executable-source attestations,
and a fixed-account root-consumption ledger.  Reading readiness never creates a claim;
the live runner must durably claim the fixed-account identity before its private episode
and before any controller input.
"""

from __future__ import annotations

import hashlib
import json
import os
import pwd
import re
import stat
import sys
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from pokemon_red_completion.executor import WindowedFrameBudgetController
from pokemon_red_completion.goal_manager_composition_runtime import (
    FRESH_COMPOSITION_ACTIONS_PER_DECISION,
    FRESH_COMPOSITION_MAX_ACTIONS,
    CompositionBudgetCheckpoint,
    LivingCollectionCheckpoint,
)
from pokemon_red_completion.provenance import canonical_sha256
from pokemon_red_completion.red_acquisition import RED_ACQUISITION_CATALOG
from pokemon_red_completion.red_collection import (
    RED_COLLECTION_GAME_ID,
    RED_SOLO_COLLECTION_CONTRACT,
)
from pokemon_red_completion.red_goal_manager import RedGoalObservation

_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_SKILL_SOURCE_FILES = (
    "src/pokemon_red_completion/executor.py",
    "src/pokemon_red_completion/goal_manager_composition_runtime.py",
    "src/pokemon_red_completion/goal_manager_runtime.py",
    "src/pokemon_red_completion/goal_manager_trajectory.py",
    "src/pokemon_red_completion/red_acquisition.py",
    "src/pokemon_red_completion/red_goal_context.py",
    "src/pokemon_red_completion/red_goal_manager.py",
    "src/pokemon_red_completion/red_goal_skills.py",
    "src/pokemon_red_completion/trajectory_io.py",
)


class FreshCompositionQualificationError(RuntimeError):
    """Raised before the qualified execution boundary can be crossed."""


class ActionExecutor(Protocol):
    def execute(self, action: Any) -> object: ...


class HardCompositionActionLimiter:
    """Reserve each dispatch before delegation and enforce step plus episode caps."""

    __slots__ = (
        "_completed_actions",
        "_delegate",
        "_maximum_actions_per_decision",
        "_maximum_episode_actions",
        "_window_start",
        "attempted_actions",
    )

    def __init__(
        self,
        delegate: ActionExecutor,
        *,
        maximum_actions_per_decision: int = FRESH_COMPOSITION_ACTIONS_PER_DECISION,
        maximum_episode_actions: int = FRESH_COMPOSITION_MAX_ACTIONS,
    ) -> None:
        for name, value in (
            ("maximum_actions_per_decision", maximum_actions_per_decision),
            ("maximum_episode_actions", maximum_episode_actions),
        ):
            if type(value) is not int or value <= 0:  # noqa: E721
                raise ValueError(f"{name} must be a positive integer")
        if maximum_actions_per_decision > maximum_episode_actions:
            raise ValueError("per-decision actions cannot exceed the episode cap")
        self._delegate = delegate
        self._maximum_actions_per_decision = maximum_actions_per_decision
        self._maximum_episode_actions = maximum_episode_actions
        self.attempted_actions = 0
        self._completed_actions = 0
        self._window_start = 0

    @property
    def completed_actions(self) -> int:
        return self._completed_actions

    @property
    def attempted_actions_this_decision(self) -> int:
        return self.attempted_actions - self._window_start

    def begin_decision_window(self) -> None:
        self._window_start = self.attempted_actions

    def execute(self, action: Any) -> object:
        if (
            self.attempted_actions >= self._maximum_episode_actions
            or self.attempted_actions_this_decision
            >= self._maximum_actions_per_decision
        ):
            raise FreshCompositionQualificationError(
                "composition exhausted its hard controller-action budget"
            )
        # Reserve the attempt first.  A partially executed delegate that raises is
        # still an input attempt and can never disappear from independent accounting.
        self.attempted_actions += 1
        result = self._delegate.execute(action)
        self._completed_actions += 1
        return result


class ActionFreeAdmissionExecutor:
    """Refuse an admission-time skill dispatch before it reaches a controller."""

    __slots__ = ("attempted_actions",)

    def __init__(self) -> None:
        self.attempted_actions = 0

    def execute(self, _action: Any) -> object:
        self.attempted_actions += 1
        raise FreshCompositionQualificationError(
            "composition admission cannot dispatch a controller action"
        )


@dataclass(frozen=True, slots=True)
class CompositionIndependentBudgetMeter:
    actions: HardCompositionActionLimiter
    frames: WindowedFrameBudgetController

    def checkpoint(self) -> CompositionBudgetCheckpoint:
        return CompositionBudgetCheckpoint(
            controller_actions=self.actions.attempted_actions,
            emulator_frames=self.frames.frames_executed,
        )

    def begin_decision_window(self) -> None:
        self.actions.begin_decision_window()
        self.frames.begin_window()


def living_collection_checkpoint(
    observation: RedGoalObservation,
) -> LivingCollectionCheckpoint:
    """Project one authenticated Red observation into the title-neutral contract."""

    if not isinstance(observation, RedGoalObservation):
        raise TypeError("observation must be a RedGoalObservation")
    specimens = Counter(
        item.species_ref for item in observation.collection_observation.specimens
    )
    required = RED_ACQUISITION_CATALOG.required_root_acquisitions()
    retained = sum(
        min(required_count, specimens[species])
        for species, required_count in required.items()
    )
    remaining = {
        species: max(0, required_count - specimens[species])
        for species, required_count in required.items()
        if required_count > specimens[species]
    }
    report = observation.collection.collection
    completion_contract_sha256 = canonical_sha256(
        {
            "schema": "pokemon.core.living-collection-contract.v1",
            "game_id": RED_COLLECTION_GAME_ID,
            "registered_target": sorted(RED_SOLO_COLLECTION_CONTRACT.target_species),
            "living_target": sorted(
                RED_SOLO_COLLECTION_CONTRACT.resolved_living_target_species
            ),
            "required_root_acquisitions": dict(sorted(required.items())),
        }
    )
    return LivingCollectionCheckpoint(
        registered_species=report.pokedex_owned_count,
        living_species=report.living_count,
        required_specimens_remaining=sum(remaining.values()),
        retained_captures=retained,
        undeclared_specimen_losses=0,
        completion_contract_sha256=completion_contract_sha256,
        specimen_ledger_sha256=canonical_sha256(
            {
                "schema": "pokemon.core.living-specimen-ledger.v1",
                "specimens": dict(sorted(specimens.items())),
            }
        ),
        required_specimens_sha256=canonical_sha256(
            {
                "schema": "pokemon.core.remaining-required-specimens.v1",
                "remaining": dict(sorted(remaining.items())),
            }
        ),
        specimen_counts=tuple(sorted(specimens.items())),
    )


def root_consumption_sha256(*, state_sha256: str, envelope_sha256: str) -> str:
    """Return the code-version-independent collision key for one exact root."""

    return canonical_sha256(
        {
            "schema": "pokemon.red.fresh-composition-root-consumption.v1",
            "game_id": RED_COLLECTION_GAME_ID,
            "state_sha256": _require_sha256(state_sha256, subject="state"),
            "envelope_sha256": _require_sha256(envelope_sha256, subject="envelope"),
        }
    )


def composition_skill_manifest(repository_root: Path) -> dict[str, object]:
    """Hash the exact policy, skill, verifier, limiter, and durability sources."""

    rows: list[dict[str, object]] = []
    for relative in _SKILL_SOURCE_FILES:
        path = repository_root / relative
        try:
            metadata = path.lstat()
            payload = path.read_bytes()
        except OSError as error:
            raise FreshCompositionQualificationError(
                "composition skill source cannot be authenticated"
            ) from error
        if path.is_symlink() or not stat.S_ISREG(metadata.st_mode):
            raise FreshCompositionQualificationError(
                "composition skill source must be a regular file"
            )
        rows.append(
            {
                "relative_path": relative,
                "sha256": hashlib.sha256(payload).hexdigest(),
                "bytes": len(payload),
            }
        )
    manifest = {
        "schema": "pokemon.red.fresh-composition-skill-manifest.v1",
        "files": rows,
    }
    return {**manifest, "manifest_sha256": canonical_sha256(manifest)}


def fixed_account_claim_registry_root() -> Path:
    account_home = Path(pwd.getpwuid(os.getuid()).pw_dir)
    if sys.platform == "darwin":
        return (
            account_home
            / "Library"
            / "Application Support"
            / "pokemon-red-completion-agent"
            / "fresh-composition-root-claims-v1"
        )
    return (
        account_home
        / ".local"
        / "state"
        / "pokemon-red-completion-agent"
        / "fresh-composition-root-claims-v1"
    )


def open_fixed_account_claim_registry(path: Path | None = None) -> Path:
    """Validate a preprovisioned 0700 account ledger without creating it."""

    root = path or fixed_account_claim_registry_root()
    try:
        metadata = root.lstat()
        resolved = root.resolve(strict=True)
    except OSError as error:
        raise FreshCompositionQualificationError(
            "fresh-composition claim registry must be provisioned before preflight"
        ) from error
    if (
        root.is_symlink()
        or not stat.S_ISDIR(metadata.st_mode)
        or metadata.st_uid != os.getuid()
        or stat.S_IMODE(metadata.st_mode) != 0o700
    ):
        raise FreshCompositionQualificationError(
            "fresh-composition claim registry is invalid"
        )
    return resolved


def root_claim_is_available(registry: Path, root_consumption_sha256: str) -> bool:
    marker = _root_claim_marker(registry, root_consumption_sha256)
    try:
        marker.lstat()
    except FileNotFoundError:
        return True
    except OSError as error:
        raise FreshCompositionQualificationError(
            "fresh-composition claim marker cannot be inspected"
        ) from error
    return False


def write_root_claim(
    registry: Path,
    *,
    root_consumption_sha256: str,
    execution_identity_sha256: str,
    source_commit: str,
    runner_sha256: str,
) -> None:
    """Durably consume one root before a local artifact or controller can start."""

    marker = _root_claim_marker(registry, root_consumption_sha256)
    payload = (
        json.dumps(
            {
                "schema": "pokemon.red.fresh-composition-root-claim.v1",
                "root_consumption_sha256": _require_sha256(
                    root_consumption_sha256,
                    subject="root consumption",
                ),
                "execution_identity_sha256": _require_sha256(
                    execution_identity_sha256,
                    subject="execution identity",
                ),
                "source_commit": source_commit,
                "runner_sha256": _require_sha256(runner_sha256, subject="runner"),
            },
            ensure_ascii=True,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("ascii")
        + b"\n"
    )
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_CLOEXEC"):
        flags |= os.O_CLOEXEC
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    descriptor = -1
    try:
        descriptor = os.open(marker, flags, 0o600)
        offset = 0
        while offset < len(payload):
            written = os.write(descriptor, payload[offset:])
            if written <= 0:
                raise OSError("claim write made no progress")
            offset += written
        os.fsync(descriptor)
        directory = os.open(registry, os.O_RDONLY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    except FileExistsError as error:
        raise FreshCompositionQualificationError(
            "fresh-composition root is already consumed"
        ) from error
    except OSError as error:
        raise FreshCompositionQualificationError(
            "fresh-composition root claim could not be retained"
        ) from error
    finally:
        if descriptor >= 0:
            os.close(descriptor)


def _root_claim_marker(registry: Path, identity: str) -> Path:
    return registry / f"{_require_sha256(identity, subject='root consumption')}.json"


def _require_sha256(value: object, *, subject: str) -> str:
    if not isinstance(value, str) or _SHA256.fullmatch(value) is None:
        raise FreshCompositionQualificationError(f"{subject} digest is invalid")
    return value


__all__ = [
    "CompositionIndependentBudgetMeter",
    "FreshCompositionQualificationError",
    "HardCompositionActionLimiter",
    "composition_skill_manifest",
    "fixed_account_claim_registry_root",
    "living_collection_checkpoint",
    "open_fixed_account_claim_registry",
    "root_claim_is_available",
    "root_consumption_sha256",
    "write_root_claim",
]
