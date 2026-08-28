"""Runtime-enforced clean-power generation of independent Red setup roots.

The lineage plan is only a promise.  This module turns that promise into one
ordered execution rail:

``durable assignment claim -> clean power -> timing jitter -> teacher ->
checkpoint -> same-episode conditioning -> one terminal save -> verification``.

No state-load method is available on the guarded emulator.  One process may
issue only one execution authority, and an assignment marker is written with
``O_EXCL`` before the first emulator frame so a crash cannot become a retry.
The terminal bytes remain private; the returned receipt is path-free.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import stat
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

from pokemon_red_completion.captured_progress import CapturedProgressEnvelope
from pokemon_red_completion.emulator import OneWayEmulatorPort
from pokemon_red_completion.goal_manager_composition_qualification import (
    fixed_account_claim_registry_lease,
    root_consumption_sha256,
)
from pokemon_red_completion.private_artifacts import (
    EpisodeSummary,
    PrivateArtifactRoot,
)
from pokemon_red_completion.provenance import canonical_sha256
from pokemon_red_completion.red_living_dex_capture_plan import (
    RED_LIVING_DEX_SETUP_MAX_CONTROLLER_ACTIONS,
    RED_LIVING_DEX_SETUP_MAX_EMULATOR_FRAMES,
)
from pokemon_red_completion.red_living_dex_episode_lineage import (
    RED_LIVING_DEX_FRESH_EPISODE_CHECKPOINT_ID,
    RedLivingDexFreshEpisodeAssignment,
    RedLivingDexFreshEpisodePlan,
    RedLivingDexFreshEpisodeReceipt,
    expected_red_living_dex_first_controller_input_frame,
)
from pokemon_red_completion.red_living_dex_setup_recipe import (
    RedLivingDexAuthenticatedSetupRoot,
)

RED_LIVING_DEX_FRESH_EPISODE_ASSIGNMENT_CLAIM_SCHEMA = (
    "pokemon.red.living-dex-fresh-episode-assignment-claim.v1"
)
RED_LIVING_DEX_FRESH_EPISODE_PRIVATE_ROOT_SCHEMA = (
    "pokemon.red.private-living-dex-fresh-episode-root.v1"
)
RED_LIVING_DEX_FRESH_EPISODE_RUNTIME_RESULT_SCHEMA = (
    "pokemon.red.living-dex-fresh-episode-runtime-result.v1"
)

_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_GIT_OID = re.compile(r"(?:[0-9a-f]{40}|[0-9a-f]{64})\Z")
_PROCESS_AUTHORITY_TOKEN = object()
_TERMINAL_SAVE_TOKEN = object()
_PROCESS_AUTHORITY_ISSUED = False
_TRAJECTORY_DOMAIN = b"pokemon-red-living-dex-fresh-trajectory-v1\0"


class RedLivingDexFreshEpisodeRuntimeError(RuntimeError):
    """One fresh episode crossed its one-shot clean-power boundary."""


class FreshEpisodeEmulatorDelegate(Protocol):
    @property
    def frame_count(self) -> int: ...

    @property
    def pressed_buttons(self) -> frozenset[str]: ...

    def tick(self, frames: int) -> None: ...

    def press(self, button: str) -> None: ...

    def release(self, button: str) -> None: ...

    def save_state_bytes(self) -> bytes: ...

    def close(self) -> None: ...


@dataclass(slots=True)
class RedLivingDexFreshEpisodeProcessAuthority:
    """One non-transferable permission to create one emulator in this process."""

    pid: int
    _token: object = field(repr=False)
    _used: bool = field(default=False, init=False, repr=False)

    def __post_init__(self) -> None:
        if self._token is not _PROCESS_AUTHORITY_TOKEN or self.pid != os.getpid():
            raise RedLivingDexFreshEpisodeRuntimeError(
                "fresh-episode process authority differs"
            )

    def consume(self) -> None:
        self.__post_init__()
        if self._used:
            raise RedLivingDexFreshEpisodeRuntimeError(
                "fresh-episode process authority is already consumed"
            )
        self._used = True


def issue_red_living_dex_fresh_episode_process_authority(
) -> RedLivingDexFreshEpisodeProcessAuthority:
    """Issue at most one episode authority during a Python process lifetime."""

    global _PROCESS_AUTHORITY_ISSUED
    if _PROCESS_AUTHORITY_ISSUED:
        raise RedLivingDexFreshEpisodeRuntimeError(
            "fresh-episode process already issued an execution authority"
        )
    _PROCESS_AUTHORITY_ISSUED = True
    return RedLivingDexFreshEpisodeProcessAuthority(
        pid=os.getpid(),
        _token=_PROCESS_AUTHORITY_TOKEN,
    )


@dataclass(frozen=True, slots=True)
class RedLivingDexFreshEpisodeCheckpoint:
    """The exact teacher frontier sealed before target-specific conditioning."""

    checkpoint_id: str
    label: str
    completed: int
    total: int
    verified_objective_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        if self.checkpoint_id != RED_LIVING_DEX_FRESH_EPISODE_CHECKPOINT_ID:
            raise RedLivingDexFreshEpisodeRuntimeError(
                "fresh-episode teacher stopped at another checkpoint"
            )
        if not isinstance(self.label, str) or not self.label:
            raise RedLivingDexFreshEpisodeRuntimeError(
                "fresh-episode checkpoint label is absent"
            )
        if (
            type(self.completed) is not int  # noqa: E721
            or type(self.total) is not int  # noqa: E721
            or not 0 < self.completed <= self.total
        ):
            raise RedLivingDexFreshEpisodeRuntimeError(
                "fresh-episode checkpoint counts differ"
            )
        if (
            not isinstance(self.verified_objective_ids, tuple)
            or len(set(self.verified_objective_ids))
            != len(self.verified_objective_ids)
            or any(
                not isinstance(item, str) or not item
                for item in self.verified_objective_ids
            )
        ):
            raise RedLivingDexFreshEpisodeRuntimeError(
                "fresh-episode verified objectives differ"
            )

    def private_dict(self) -> dict[str, object]:
        return {
            "checkpoint_id": self.checkpoint_id,
            "checkpoint_label": self.label,
            "checkpoints_completed": self.completed,
            "checkpoints_total": self.total,
            "schema": "pokemon.red.private-living-dex-fresh-checkpoint.v1",
            "verified_objective_ids": list(self.verified_objective_ids),
        }


@dataclass(frozen=True, slots=True)
class RedLivingDexFreshEpisodeTargetVerification:
    """Action-free proof that the terminal root reaches its declared menu."""

    compatible_template_ordinals: tuple[int, ...]
    observed_storage_pressure_millionths: int | None

    def verify(self, assignment: RedLivingDexFreshEpisodeAssignment) -> None:
        if not isinstance(assignment, RedLivingDexFreshEpisodeAssignment):
            raise TypeError("fresh target verification needs an assignment")
        if (
            not isinstance(self.compatible_template_ordinals, tuple)
            or tuple(sorted(set(self.compatible_template_ordinals)))
            != self.compatible_template_ordinals
            or any(
                type(item) is not int or not 0 <= item < 10  # noqa: E721
                for item in self.compatible_template_ordinals
            )
            or assignment.target_template_ordinal
            not in self.compatible_template_ordinals
        ):
            raise RedLivingDexFreshEpisodeRuntimeError(
                "fresh-episode terminal root missed its declared menu"
            )
        if self.observed_storage_pressure_millionths != (
            assignment.target_storage_pressure_millionths
        ):
            raise RedLivingDexFreshEpisodeRuntimeError(
                "fresh-episode terminal storage pressure differs"
            )


class CleanPowerFreshEpisodeEmulator:
    """Deny restores, meter every frame/input, and expose one terminal save.

    The runtime authenticates the exact teacher, conditioner, and runner bytes.
    Its two meters detect bypasses through the supported port; they are not a
    claim that same-process hostile Python can be sandboxed by name-mangling.
    """

    __slots__ = (
        "_assignment",
        "_controller_actions",
        "_metered_controller_events",
        "_metered_frames",
        "_port",
        "_first_controller_input_frame",
        "_initial_wait_complete",
        "_save_state_loads",
        "_teacher_prefix_sha256",
        "_terminal_state_saves",
        "_transcript",
    )

    def __init__(
        self,
        delegate: FreshEpisodeEmulatorDelegate,
        assignment: RedLivingDexFreshEpisodeAssignment,
    ) -> None:
        if not isinstance(assignment, RedLivingDexFreshEpisodeAssignment):
            raise TypeError("fresh emulator guard needs an assignment")
        assignment.__post_init__()
        if (
            type(delegate.frame_count) is not int  # noqa: E721
            or delegate.frame_count != 0
            or delegate.pressed_buttons != frozenset()
        ):
            raise RedLivingDexFreshEpisodeRuntimeError(
                "fresh-episode emulator did not begin at clean power"
            )
        self._port = OneWayEmulatorPort(
            delegate,
            capture_token=_TERMINAL_SAVE_TOKEN,
        )
        self._assignment = assignment
        self._controller_actions = 0
        self._metered_controller_events = 0
        self._metered_frames = 0
        self._first_controller_input_frame: int | None = None
        self._initial_wait_complete = False
        self._save_state_loads = 0
        self._teacher_prefix_sha256: str | None = None
        self._terminal_state_saves = 0
        self._transcript = hashlib.sha256(_TRAJECTORY_DOMAIN)

    @property
    def frame_count(self) -> int:
        value = self._port.frame_count
        if type(value) is not int or value < 0:  # noqa: E721
            raise RedLivingDexFreshEpisodeRuntimeError(
                "fresh-episode frame counter differs"
            )
        return value

    @property
    def pressed_buttons(self) -> frozenset[str]:
        value = self._port.pressed_buttons
        if not isinstance(value, frozenset):
            raise RedLivingDexFreshEpisodeRuntimeError(
                "fresh-episode button state differs"
            )
        return value

    @property
    def controller_actions(self) -> int:
        return self._controller_actions

    @property
    def first_controller_input_frame(self) -> int:
        if self._first_controller_input_frame is None:
            raise RedLivingDexFreshEpisodeRuntimeError(
                "fresh-episode teacher used no controller input"
            )
        return self._first_controller_input_frame

    @property
    def save_state_loads(self) -> int:
        return self._save_state_loads

    @property
    def terminal_state_saves(self) -> int:
        return self._terminal_state_saves

    @property
    def fingerprint(self) -> Any:
        return self._port.fingerprint

    @property
    def window_name(self) -> str:
        return self._port.window_name

    @property
    def speed(self) -> int:
        return self._port.speed

    @property
    def pyboy_version(self) -> str:
        return self._port.pyboy_version

    @property
    def teacher_prefix_sha256(self) -> str:
        if self._teacher_prefix_sha256 is None:
            raise RedLivingDexFreshEpisodeRuntimeError(
                "fresh-episode teacher trajectory is not sealed"
            )
        return self._teacher_prefix_sha256

    def perform_initial_wait(self) -> None:
        if self._initial_wait_complete or self.frame_count != 0:
            raise RedLivingDexFreshEpisodeRuntimeError(
                "fresh-episode initial wait was not first"
            )
        if self._assignment.initial_wait_frames > (
            RED_LIVING_DEX_SETUP_MAX_EMULATOR_FRAMES
        ):
            raise RedLivingDexFreshEpisodeRuntimeError(
                "fresh-episode initial wait exceeds its frame bound"
            )
        before = self.frame_count
        self._port.advance(self._assignment.initial_wait_frames)
        after = self.frame_count
        if after - before != self._assignment.initial_wait_frames:
            raise RedLivingDexFreshEpisodeRuntimeError(
                "fresh-episode initial wait advanced another frame count"
            )
        self._record(
            "initial_wait",
            frames=self._assignment.initial_wait_frames,
            frame=after,
        )
        self._metered_frames += after - before
        self._initial_wait_complete = True
        self.reconcile_runtime_accounting()

    def tick(self, frames: int) -> None:
        self._require_running()
        if (
            type(frames) is not int  # noqa: E721
            or frames <= 0
            or self.frame_count + frames
            > RED_LIVING_DEX_SETUP_MAX_EMULATOR_FRAMES
        ):
            raise RedLivingDexFreshEpisodeRuntimeError(
                "fresh-episode tick exceeds its frame bound"
            )
        before = self.frame_count
        try:
            self._port.advance(frames)
        finally:
            after = self.frame_count
            if after < before:
                raise RedLivingDexFreshEpisodeRuntimeError(
                    "fresh-episode frame counter moved backwards"
                )
            delta = after - before
            self._record("tick", frames=delta, frame=after)
            self._metered_frames += delta
            if after > RED_LIVING_DEX_SETUP_MAX_EMULATOR_FRAMES:
                raise RedLivingDexFreshEpisodeRuntimeError(
                    "fresh-episode delegate exceeded its frame bound"
                )
            self.reconcile_runtime_accounting()

    def press(self, button: str) -> None:
        self._require_running()
        if self._controller_actions >= (
            RED_LIVING_DEX_SETUP_MAX_CONTROLLER_ACTIONS
        ):
            raise RedLivingDexFreshEpisodeRuntimeError(
                "fresh-episode controller exceeds its action bound"
            )
        if self._first_controller_input_frame is None:
            expected = expected_red_living_dex_first_controller_input_frame(
                self._assignment.initial_wait_frames
            )
            if self.frame_count != expected:
                raise RedLivingDexFreshEpisodeRuntimeError(
                    "fresh-episode first controller input frame differs"
                )
            self._first_controller_input_frame = self.frame_count
        self._port.button_down(button)
        self._controller_actions += 1
        self._metered_controller_events += 1
        self._record("press", button=button, frame=self.frame_count)
        self.reconcile_runtime_accounting()

    def release(self, button: str) -> None:
        self._require_running()
        self._port.button_up(button)
        self._metered_controller_events += 1
        self._record("release", button=button, frame=self.frame_count)
        self.reconcile_runtime_accounting()

    def seal_teacher_prefix(
        self,
        checkpoint: RedLivingDexFreshEpisodeCheckpoint,
    ) -> str:
        self.reconcile_runtime_accounting()
        checkpoint.__post_init__()
        if self._teacher_prefix_sha256 is not None:
            raise RedLivingDexFreshEpisodeRuntimeError(
                "fresh-episode teacher trajectory was sealed twice"
            )
        if self.pressed_buttons:
            raise RedLivingDexFreshEpisodeRuntimeError(
                "fresh-episode teacher stopped with a pressed controller"
            )
        self._record(
            "teacher_checkpoint",
            checkpoint_id=checkpoint.checkpoint_id,
            frame=self.frame_count,
        )
        self._teacher_prefix_sha256 = self._transcript.hexdigest()
        return self._teacher_prefix_sha256

    def load_state(self, _source: object) -> None:
        self._save_state_loads += 1
        raise RedLivingDexFreshEpisodeRuntimeError(
            "fresh-episode state restoration is forbidden"
        )

    def load_state_bytes(self, _payload: bytes) -> None:
        self._save_state_loads += 1
        raise RedLivingDexFreshEpisodeRuntimeError(
            "fresh-episode state restoration is forbidden"
        )

    def save_state(self, _destination: object) -> None:
        raise RedLivingDexFreshEpisodeRuntimeError(
            "fresh-episode terminal save requires runtime authority"
        )

    def save_state_bytes(self) -> bytes:
        raise RedLivingDexFreshEpisodeRuntimeError(
            "fresh-episode terminal save requires runtime authority"
        )

    def capture_terminal_state(self, *, _token: object) -> bytes:
        if _token is not _TERMINAL_SAVE_TOKEN:
            raise RedLivingDexFreshEpisodeRuntimeError(
                "fresh-episode terminal save authority differs"
            )
        if self._teacher_prefix_sha256 is None or self.pressed_buttons:
            raise RedLivingDexFreshEpisodeRuntimeError(
                "fresh-episode terminal state is not at a released boundary"
            )
        if self._terminal_state_saves:
            raise RedLivingDexFreshEpisodeRuntimeError(
                "fresh-episode terminal state was already saved"
            )
        payload = self._port.capture_state_bytes(token=_token)
        if not isinstance(payload, bytes) or not payload:
            raise RedLivingDexFreshEpisodeRuntimeError(
                "fresh-episode terminal state is absent"
            )
        self._terminal_state_saves = 1
        self.reconcile_runtime_accounting()
        return payload

    def close(self) -> None:
        self._port.close()

    def read_u8(self, address: int) -> int:
        return self._port.read_u8(address)

    def read_wram(self, bank: int, address: int, length: int) -> bytes:
        return self._port.read_wram(bank, address, length)

    def read_cartridge_ram_u8(self, bank: int, address: int) -> int:
        return self._port.read_cartridge_ram_u8(bank, address)

    def read_cartridge_ram(
        self,
        bank: int,
        address: int,
        length: int,
    ) -> bytes:
        return self._port.read_cartridge_ram(bank, address, length)

    def reconcile_runtime_accounting(self) -> None:
        """Reject any port effect that bypassed the metered public surface."""

        if (
            self.frame_count != self._port.advanced_frames
            or self._metered_frames != self._port.advanced_frames
            or self._controller_actions != self._port.controller_actions
            or self._metered_controller_events
            != self._port.controller_events
            or self._terminal_state_saves != self._port.state_captures
        ):
            raise RedLivingDexFreshEpisodeRuntimeError(
                "fresh-episode low-level accounting differs"
            )

    def _require_running(self) -> None:
        if not self._initial_wait_complete:
            raise RedLivingDexFreshEpisodeRuntimeError(
                "fresh-episode controller/runtime started before its timing jitter"
            )
        if self._terminal_state_saves:
            raise RedLivingDexFreshEpisodeRuntimeError(
                "fresh-episode execution continued after its terminal save"
            )

    def _record(self, event: str, **values: object) -> None:
        payload = {
            "event": event,
            **values,
        }
        self._transcript.update(
            json.dumps(
                payload,
                allow_nan=False,
                ensure_ascii=True,
                separators=(",", ":"),
                sort_keys=True,
            ).encode("ascii")
            + b"\n"
        )


@dataclass(frozen=True, slots=True)
class RedLivingDexFreshEpisodeRuntimeResult:
    """One complete private root plus its deliberately path-free receipt."""

    receipt: RedLivingDexFreshEpisodeReceipt
    root: RedLivingDexAuthenticatedSetupRoot = field(repr=False)
    artifact_summary: EpisodeSummary

    def public_dict(self) -> dict[str, object]:
        return {
            **self.receipt.public_dict(),
            "artifact_manifest_sha256": self.artifact_summary.manifest_sha256,
            "private_identity_fields": 0,
            "private_path_fields": 0,
            "root_generation_executions": 1,
            "schema": RED_LIVING_DEX_FRESH_EPISODE_RUNTIME_RESULT_SCHEMA,
            "status": "fresh_train_root_generated_pending_tranche_recensus",
        }


FreshEpisodeEmulatorFactory = Callable[[], FreshEpisodeEmulatorDelegate]
FreshEpisodeTeacher = Callable[
    [CleanPowerFreshEpisodeEmulator, RedLivingDexFreshEpisodeAssignment],
    RedLivingDexFreshEpisodeCheckpoint,
]
FreshEpisodeConditioner = Callable[
    [CleanPowerFreshEpisodeEmulator, RedLivingDexFreshEpisodeAssignment],
    None,
]
FreshEpisodeTargetVerifier = Callable[
    [
        CleanPowerFreshEpisodeEmulator,
        RedLivingDexFreshEpisodeAssignment,
        RedLivingDexAuthenticatedSetupRoot,
        CapturedProgressEnvelope,
    ],
    RedLivingDexFreshEpisodeTargetVerification,
]
FreshEpisodePostCloseVerifier = Callable[[], None]


def execute_red_living_dex_fresh_episode(
    plan: RedLivingDexFreshEpisodePlan,
    assignment_id: str,
    *,
    source_commit: str,
    source_bundle_sha256: str,
    generator_execution_sha256: str,
    runner_sha256: str,
    process_authority: RedLivingDexFreshEpisodeProcessAuthority,
    private_store: PrivateArtifactRoot,
    claim_registry: Path,
    emulator_factory: FreshEpisodeEmulatorFactory,
    setup_teacher: FreshEpisodeTeacher,
    condition_target: FreshEpisodeConditioner,
    verify_target: FreshEpisodeTargetVerifier,
    post_close_verify: FreshEpisodePostCloseVerifier,
) -> RedLivingDexFreshEpisodeRuntimeResult:
    """Execute exactly one precommitted assignment on the one-way runtime rail."""

    if not isinstance(plan, RedLivingDexFreshEpisodePlan):
        raise TypeError("fresh runtime needs a lineage plan")
    plan.__post_init__()
    if (
        source_commit != plan.source_commit
        or source_bundle_sha256 != plan.source_bundle_sha256
        or generator_execution_sha256 != plan.generator_execution_sha256
    ):
        raise RedLivingDexFreshEpisodeRuntimeError(
            "fresh-episode published execution binding differs"
        )
    if _GIT_OID.fullmatch(source_commit) is None:
        raise RedLivingDexFreshEpisodeRuntimeError(
            "fresh-episode source commit differs"
        )
    for value, subject in (
        (source_bundle_sha256, "source bundle"),
        (generator_execution_sha256, "generator execution"),
        (runner_sha256, "generator runner"),
    ):
        _require_sha256(value, subject)
    if not isinstance(process_authority, RedLivingDexFreshEpisodeProcessAuthority):
        raise TypeError("fresh runtime needs process authority")
    if not isinstance(private_store, PrivateArtifactRoot):
        raise TypeError("fresh runtime needs a validated private store")
    for callback, subject in (
        (emulator_factory, "emulator factory"),
        (setup_teacher, "setup teacher"),
        (condition_target, "target conditioner"),
        (verify_target, "target verifier"),
        (post_close_verify, "post-close verifier"),
    ):
        if not callable(callback):
            raise TypeError(f"fresh runtime {subject} differs")
    assignment = plan.assignment(assignment_id)
    process_authority.consume()
    writer = private_store.begin_episode(assignment.episode_id)
    guarded: CleanPowerFreshEpisodeEmulator | None = None
    root: RedLivingDexAuthenticatedSetupRoot | None = None
    receipt: RedLivingDexFreshEpisodeReceipt | None = None

    with writer:
        writer.append("assignment", assignment.public_dict(), durable=True)
        execution_identity_sha256 = canonical_sha256(
            {
                "assignment_id": assignment.assignment_id,
                "generator_execution_sha256": generator_execution_sha256,
                "plan_sha256": plan.plan_sha256,
                "runner_sha256": runner_sha256,
                "schema": "pokemon.red.living-dex-fresh-runtime-identity.v1",
                "source_commit": source_commit,
            }
        )
        with fixed_account_claim_registry_lease(
            claim_registry,
            exclusive=True,
        ):
            claim = durably_claim_red_living_dex_fresh_episode_assignment(
                claim_registry,
                assignment_id=assignment.assignment_id,
                execution_identity_sha256=execution_identity_sha256,
                plan_sha256=plan.plan_sha256,
                source_commit=source_commit,
                runner_sha256=runner_sha256,
            )
        assignment_claim_sha256 = canonical_sha256(claim)
        writer.append("claim", claim, durable=True)
        delegate = emulator_factory()
        guarded = CleanPowerFreshEpisodeEmulator(delegate, assignment)
        try:
            guarded.perform_initial_wait()
            checkpoint = setup_teacher(guarded, assignment)
            guarded.reconcile_runtime_accounting()
            guarded.seal_teacher_prefix(checkpoint)
            writer.append("checkpoint", checkpoint.private_dict(), durable=True)
            condition_target(guarded, assignment)
            guarded.reconcile_runtime_accounting()
            state_bytes = guarded.capture_terminal_state(
                _token=_TERMINAL_SAVE_TOKEN
            )
            envelope = CapturedProgressEnvelope(
                state_sha256=hashlib.sha256(state_bytes).hexdigest(),
                checkpoint_id=checkpoint.checkpoint_id,
                checkpoint_label=checkpoint.label,
                checkpoints_completed=checkpoint.completed,
                checkpoints_total=checkpoint.total,
                verified_objective_ids=checkpoint.verified_objective_ids,
            )
            envelope_bytes = (
                json.dumps(
                    envelope.to_dict(),
                    ensure_ascii=True,
                    sort_keys=True,
                ).encode("ascii")
                + b"\n"
            )
            root = RedLivingDexAuthenticatedSetupRoot(
                root_consumption_sha256=root_consumption_sha256(
                    state_sha256=hashlib.sha256(state_bytes).hexdigest(),
                    envelope_sha256=hashlib.sha256(
                        envelope_bytes
                    ).hexdigest(),
                ),
                state_bytes=state_bytes,
                envelope_bytes=envelope_bytes,
            )
            receipt_frame_before = guarded.frame_count
            receipt_actions_before = guarded.controller_actions
            verification = verify_target(
                guarded,
                assignment,
                root,
                envelope,
            )
            guarded.reconcile_runtime_accounting()
            if (
                guarded.frame_count != receipt_frame_before
                or guarded.controller_actions != receipt_actions_before
                or guarded.save_state_loads != 0
                or guarded.terminal_state_saves != 1
                or guarded.pressed_buttons
            ):
                raise RedLivingDexFreshEpisodeRuntimeError(
                    "fresh-episode target verification crossed an effect"
                )
            if not isinstance(
                verification,
                RedLivingDexFreshEpisodeTargetVerification,
            ):
                raise RedLivingDexFreshEpisodeRuntimeError(
                    "fresh-episode target verifier returned another type"
                )
            verification.verify(assignment)
            receipt = RedLivingDexFreshEpisodeReceipt(
                assignment_id=assignment.assignment_id,
                plan_sha256=plan.plan_sha256,
                assignment_claim_sha256=assignment_claim_sha256,
                root_lineage_id=assignment.root_lineage_id,
                episode_id=assignment.episode_id,
                source_bundle_sha256=assignment.source_bundle_sha256,
                teacher_execution_sha256=assignment.teacher_execution_sha256,
                generator_execution_sha256=(
                    assignment.generator_execution_sha256
                ),
                started_from_clean_power=True,
                distinct_process_episode=True,
                parent_state_sha256=None,
                parent_root_lineage_id=None,
                save_state_loads=guarded.save_state_loads,
                terminal_state_saves=guarded.terminal_state_saves,
                initial_wait_frames=assignment.initial_wait_frames,
                first_controller_input_frame=(
                    guarded.first_controller_input_frame
                ),
                trajectory_prefix_sha256=guarded.teacher_prefix_sha256,
                target_template_ordinal=assignment.target_template_ordinal,
                compatible_template_ordinals=(
                    verification.compatible_template_ordinals
                ),
                observed_storage_pressure_millionths=(
                    verification.observed_storage_pressure_millionths
                ),
                terminal_state_sha256=root.state_sha256,
                terminal_envelope_sha256=root.envelope_sha256,
                terminal_checkpoint_id=checkpoint.checkpoint_id,
                controller_actions=guarded.controller_actions,
                emulator_frames=guarded.frame_count,
                setup_teacher_executions=1,
                learner_teacher_queries=0,
                learner_labels=0,
                learner_outcomes=0,
                model_predictions=0,
                model_fits=0,
            )
            writer.append(
                "root",
                {
                    "envelope_base64": base64.b64encode(envelope_bytes).decode(
                        "ascii"
                    ),
                    "receipt": receipt.public_dict(),
                    "schema": RED_LIVING_DEX_FRESH_EPISODE_PRIVATE_ROOT_SCHEMA,
                    "state_base64": base64.b64encode(state_bytes).decode(
                        "ascii"
                    ),
                },
                durable=True,
            )
        finally:
            if guarded is not None:
                guarded.close()
        post_close_verify()

    if root is None or receipt is None:
        raise RedLivingDexFreshEpisodeRuntimeError(
            "fresh-episode terminal root was not retained"
        )
    return RedLivingDexFreshEpisodeRuntimeResult(
        receipt=receipt,
        root=root,
        artifact_summary=writer.summary,
    )


def durably_claim_red_living_dex_fresh_episode_assignment(
    registry: Path,
    *,
    assignment_id: str,
    execution_identity_sha256: str,
    plan_sha256: str,
    source_commit: str,
    runner_sha256: str,
) -> dict[str, object]:
    """Consume one assignment before execution; any marker blocks every retry."""

    for value, subject in (
        (assignment_id, "assignment"),
        (execution_identity_sha256, "execution identity"),
        (plan_sha256, "plan"),
        (runner_sha256, "runner"),
    ):
        _require_sha256(value, subject)
    if not isinstance(source_commit, str) or _GIT_OID.fullmatch(source_commit) is None:
        raise RedLivingDexFreshEpisodeRuntimeError(
            "fresh-episode claim source commit differs"
        )
    marker = registry / f"fresh-episode-assignment-{assignment_id}.json"
    try:
        marker.lstat()
    except FileNotFoundError:
        pass
    except OSError:
        raise RedLivingDexFreshEpisodeRuntimeError(
            "fresh-episode assignment claim cannot be inspected"
        ) from None
    else:
        raise RedLivingDexFreshEpisodeRuntimeError(
            "fresh-episode assignment is already consumed"
        )
    document: dict[str, object] = {
        "assignment_id": assignment_id,
        "execution_identity_sha256": execution_identity_sha256,
        "plan_sha256": plan_sha256,
        "runner_sha256": runner_sha256,
        "schema": RED_LIVING_DEX_FRESH_EPISODE_ASSIGNMENT_CLAIM_SCHEMA,
        "source_commit": source_commit,
    }
    payload = _canonical_line(document)
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_CLOEXEC"):
        flags |= os.O_CLOEXEC
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    descriptor = -1
    directory_descriptor = -1
    try:
        descriptor = os.open(marker, flags, 0o600)
        os.fchmod(descriptor, 0o600)
        offset = 0
        while offset < len(payload):
            written = os.write(descriptor, payload[offset:])
            if written <= 0:
                raise OSError("assignment claim write made no progress")
            offset += written
        os.fsync(descriptor)
        os.close(descriptor)
        descriptor = -1
        directory_descriptor = os.open(
            registry,
            os.O_RDONLY | getattr(os, "O_DIRECTORY", 0),
        )
        os.fsync(directory_descriptor)
    except FileExistsError:
        raise RedLivingDexFreshEpisodeRuntimeError(
            "fresh-episode assignment is already consumed"
        ) from None
    except OSError:
        # Do not unlink a partially written marker.  Its existence is the
        # durable evidence that an observable one-shot attempt began.
        raise RedLivingDexFreshEpisodeRuntimeError(
            "fresh-episode assignment claim could not be retained"
        ) from None
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        if directory_descriptor >= 0:
            os.close(directory_descriptor)
    return document


def read_red_living_dex_fresh_episode_assignment_claim(
    registry: Path,
    assignment_id: str,
) -> dict[str, object]:
    """Strictly authenticate one durable assignment marker."""

    _require_sha256(assignment_id, "assignment")
    marker = registry / f"fresh-episode-assignment-{assignment_id}.json"
    descriptor = -1
    try:
        named = marker.lstat()
        flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0)
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        descriptor = os.open(marker, flags)
        metadata = os.fstat(descriptor)
        if (
            named.st_dev != metadata.st_dev
            or named.st_ino != metadata.st_ino
            or not stat.S_ISREG(metadata.st_mode)
            or metadata.st_nlink != 1
            or metadata.st_uid != os.getuid()
            or stat.S_IMODE(metadata.st_mode) != 0o600
            or not 1 <= metadata.st_size <= 4096
        ):
            raise OSError("unsafe assignment claim")
        payload = os.read(descriptor, metadata.st_size + 1)
    except OSError:
        raise RedLivingDexFreshEpisodeRuntimeError(
            "fresh-episode assignment claim cannot be authenticated"
        ) from None
    finally:
        if descriptor >= 0:
            os.close(descriptor)
    if len(payload) != metadata.st_size:
        raise RedLivingDexFreshEpisodeRuntimeError(
            "fresh-episode assignment claim cannot be authenticated"
        )
    try:
        document = json.loads(payload.decode("ascii"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise RedLivingDexFreshEpisodeRuntimeError(
            "fresh-episode assignment claim cannot be authenticated"
        ) from None
    if (
        not isinstance(document, dict)
        or set(document)
        != {
            "assignment_id",
            "execution_identity_sha256",
            "plan_sha256",
            "runner_sha256",
            "schema",
            "source_commit",
        }
        or document.get("schema")
        != RED_LIVING_DEX_FRESH_EPISODE_ASSIGNMENT_CLAIM_SCHEMA
        or document.get("assignment_id") != assignment_id
        or _canonical_line(document) != payload
    ):
        raise RedLivingDexFreshEpisodeRuntimeError(
            "fresh-episode assignment claim cannot be authenticated"
        )
    for key in (
        "execution_identity_sha256",
        "plan_sha256",
        "runner_sha256",
    ):
        _require_sha256(document.get(key), key.replace("_", " "))
    source_commit = document.get("source_commit")
    if not isinstance(source_commit, str) or _GIT_OID.fullmatch(source_commit) is None:
        raise RedLivingDexFreshEpisodeRuntimeError(
            "fresh-episode assignment claim cannot be authenticated"
        )
    return document


def decode_red_living_dex_fresh_episode_private_root(
    record: Mapping[str, object],
) -> tuple[RedLivingDexAuthenticatedSetupRoot, Mapping[str, object]]:
    """Authenticate the private JSON record without exposing its store path."""

    if not isinstance(record, Mapping) or set(record) != {
        "envelope_base64",
        "receipt",
        "schema",
        "state_base64",
    }:
        raise RedLivingDexFreshEpisodeRuntimeError(
            "fresh-episode private root record differs"
        )
    if record["schema"] != RED_LIVING_DEX_FRESH_EPISODE_PRIVATE_ROOT_SCHEMA:
        raise RedLivingDexFreshEpisodeRuntimeError(
            "fresh-episode private root schema differs"
        )
    try:
        encoded_state = _text(record["state_base64"], "private state")
        encoded_envelope = _text(
            record["envelope_base64"],
            "private envelope",
        )
        state_bytes = base64.b64decode(
            encoded_state,
            validate=True,
        )
        envelope_bytes = base64.b64decode(
            encoded_envelope,
            validate=True,
        )
    except (ValueError, TypeError):
        raise RedLivingDexFreshEpisodeRuntimeError(
            "fresh-episode private root encoding differs"
        ) from None
    if (
        base64.b64encode(state_bytes).decode("ascii") != encoded_state
        or base64.b64encode(envelope_bytes).decode("ascii")
        != encoded_envelope
    ):
        raise RedLivingDexFreshEpisodeRuntimeError(
            "fresh-episode private root encoding is not canonical"
        )
    root = RedLivingDexAuthenticatedSetupRoot(
        root_consumption_sha256=root_consumption_sha256(
            state_sha256=hashlib.sha256(state_bytes).hexdigest(),
            envelope_sha256=hashlib.sha256(envelope_bytes).hexdigest(),
        ),
        state_bytes=state_bytes,
        envelope_bytes=envelope_bytes,
    )
    receipt = record["receipt"]
    if not isinstance(receipt, Mapping):
        raise RedLivingDexFreshEpisodeRuntimeError(
            "fresh-episode private receipt differs"
        )
    if (
        receipt.get("terminal_state_sha256") != root.state_sha256
        or receipt.get("terminal_envelope_sha256") != root.envelope_sha256
    ):
        raise RedLivingDexFreshEpisodeRuntimeError(
            "fresh-episode private root and receipt differ"
        )
    return root, receipt


def _canonical_line(value: object) -> bytes:
    return (
        json.dumps(
            value,
            allow_nan=False,
            ensure_ascii=True,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("ascii")
        + b"\n"
    )


def _require_sha256(value: object, subject: str) -> str:
    if not isinstance(value, str) or _SHA256.fullmatch(value) is None:
        raise RedLivingDexFreshEpisodeRuntimeError(
            f"fresh-episode {subject} digest differs"
        )
    return value


def _text(value: object, subject: str) -> str:
    if not isinstance(value, str) or not value:
        raise RedLivingDexFreshEpisodeRuntimeError(
            f"fresh-episode {subject} differs"
        )
    return value


__all__ = [
    "CleanPowerFreshEpisodeEmulator",
    "RedLivingDexFreshEpisodeCheckpoint",
    "RedLivingDexFreshEpisodeProcessAuthority",
    "RedLivingDexFreshEpisodeRuntimeError",
    "RedLivingDexFreshEpisodeRuntimeResult",
    "RedLivingDexFreshEpisodeTargetVerification",
    "decode_red_living_dex_fresh_episode_private_root",
    "durably_claim_red_living_dex_fresh_episode_assignment",
    "execute_red_living_dex_fresh_episode",
    "issue_red_living_dex_fresh_episode_process_authority",
    "read_red_living_dex_fresh_episode_assignment_claim",
]
