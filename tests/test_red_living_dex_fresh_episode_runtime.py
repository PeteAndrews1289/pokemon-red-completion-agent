from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from pokemon_red_completion import red_living_dex_fresh_episode_runtime as runtime
from pokemon_red_completion.bootstrap import DEFAULT_NEW_GAME_TIMING
from pokemon_red_completion.emulator import EmulatorError
from pokemon_red_completion.private_artifacts import (
    PrivateArtifactError,
    initialize_private_root,
)
from pokemon_red_completion.provenance import canonical_sha256
from pokemon_red_completion.red_living_dex_episode_lineage import (
    RedLivingDexFreshEpisodeAssignment,
    build_red_living_dex_fresh_episode_plan,
    compose_red_living_dex_fresh_episode_teacher_execution_sha256,
)
from pokemon_red_completion.red_living_dex_fresh_episode_runtime import (
    RED_LIVING_DEX_FRESH_EPISODE_ASSIGNMENT_CLAIM_SCHEMA,
    RED_LIVING_DEX_POWERED_SUPPLY_ASSIGNMENT_CLAIM_SCHEMA,
    CleanPowerFreshEpisodeEmulator,
    RedLivingDexFreshEpisodeCheckpoint,
    RedLivingDexFreshEpisodeExecutionFailure,
    RedLivingDexFreshEpisodeRuntimeError,
    RedLivingDexFreshEpisodeTargetVerification,
    RedLivingDexPoweredSupplyTargetVerification,
    decode_red_living_dex_fresh_episode_private_root,
    decode_red_living_dex_powered_supply_private_root,
    durably_claim_red_living_dex_fresh_episode_assignment,
    execute_red_living_dex_fresh_episode,
    execute_red_living_dex_powered_supply_episode,
    issue_red_living_dex_fresh_episode_process_authority,
    read_red_living_dex_fresh_episode_assignment_claim,
    read_red_living_dex_powered_supply_assignment_claim,
)
from pokemon_red_completion.red_living_dex_powered_lineage_supply import (
    RedLivingDexPoweredSupplyAssignment,
    build_red_living_dex_powered_supply_plan,
    compose_red_living_dex_powered_supply_generator_sha256,
    compose_red_living_dex_powered_supply_runtime_execution_sha256,
    compose_red_living_dex_powered_supply_teacher_sha256,
    powered_supply_collection_id,
)


def _digest(label: str) -> str:
    return canonical_sha256({"label": label})


def _plan():  # type: ignore[no-untyped-def]
    source = _digest("source")
    generator = _digest("generator")
    return build_red_living_dex_fresh_episode_plan(
        source_commit="a" * 40,
        source_bundle_sha256=source,
        teacher_execution_sha256=(
            compose_red_living_dex_fresh_episode_teacher_execution_sha256(
                source_bundle_sha256=source,
                generator_execution_sha256=generator,
            )
        ),
        generator_execution_sha256=generator,
        capacity_evidence_sha256=_digest("capacity"),
    )


def _powered_plan():  # type: ignore[no-untyped-def]
    source = _digest("powered-source")
    runner = _digest("powered-generator-runner")
    conditioner = _digest("powered-conditioner-runner")
    generator = compose_red_living_dex_powered_supply_generator_sha256(
        source_bundle_sha256=source,
        generator_runner_sha256=runner,
        conditioner_runner_sha256=conditioner,
    )
    return build_red_living_dex_powered_supply_plan(
        source_commit="b" * 40,
        source_bundle_sha256=source,
        teacher_execution_sha256=(
            compose_red_living_dex_powered_supply_teacher_sha256(
                source_bundle_sha256=source,
                generator_execution_sha256=generator,
            )
        ),
        generator_execution_sha256=generator,
        generator_runner_sha256=runner,
        conditioner_runner_sha256=conditioner,
        runtime_identity_sha256=_digest("powered-runtime"),
    )


class _FakeEmulator:
    def __init__(self) -> None:
        self._backend = object()
        self.frame_count = 0
        self.pressed_buttons: frozenset[str] = frozenset()
        self.closed = False
        self.save_calls = 0
        self.events: list[tuple[object, ...]] = []

    def tick(self, frames: int) -> None:
        self.events.append(("tick", frames))
        self.frame_count += frames

    def press(self, button: str) -> None:
        self.events.append(("press", button, self.frame_count))
        self.pressed_buttons = frozenset({button})

    def release(self, button: str) -> None:
        assert button in self.pressed_buttons
        self.events.append(("release", button, self.frame_count))
        self.pressed_buttons = frozenset()

    def save_state_bytes(self) -> bytes:
        self.save_calls += 1
        return f"fake-state-at-{self.frame_count}".encode("ascii")

    def close(self) -> None:
        self.closed = True


@pytest.fixture(autouse=True)
def _fresh_process_authority(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(runtime, "_PROCESS_AUTHORITY_ISSUED", False)


def _store(tmp_path: Path):  # type: ignore[no-untyped-def]
    repository = tmp_path / "repository"
    root = tmp_path / "private"
    repository.mkdir()
    root.mkdir()

    def device_id(path: Path) -> int:
        return 2 if path == root.resolve() else 1

    return initialize_private_root(
        root,
        repository_root=repository,
        device_id=device_id,
        git_worktree_probe=lambda _path: False,
    )


def _registry(tmp_path: Path) -> Path:
    registry = tmp_path / "claims"
    registry.mkdir(mode=0o700)
    return registry


def _checkpoint() -> RedLivingDexFreshEpisodeCheckpoint:
    return RedLivingDexFreshEpisodeCheckpoint(
        checkpoint_id="mansion_returned",
        label="Returned safely from Mansion",
        completed=275,
        total=312,
        verified_objective_ids=("power_on", "begin_adventure"),
    )


def _teacher(
    emulator: CleanPowerFreshEpisodeEmulator,
    _assignment: RedLivingDexFreshEpisodeAssignment,
) -> RedLivingDexFreshEpisodeCheckpoint:
    emulator.tick(DEFAULT_NEW_GAME_TIMING.boot_frames)
    emulator.press("a")
    emulator.tick(8)
    emulator.release("a")
    emulator.tick(100)
    return _checkpoint()


def _conditioner(
    emulator: CleanPowerFreshEpisodeEmulator,
    _assignment: RedLivingDexFreshEpisodeAssignment,
) -> None:
    emulator.press("down")
    emulator.tick(8)
    emulator.release("down")
    emulator.tick(16)


def _verifier(
    _emulator,  # type: ignore[no-untyped-def]
    assignment,  # type: ignore[no-untyped-def]
    _root,  # type: ignore[no-untyped-def]
    _envelope,  # type: ignore[no-untyped-def]
) -> RedLivingDexFreshEpisodeTargetVerification:
    return RedLivingDexFreshEpisodeTargetVerification(
        compatible_template_ordinals=(assignment.target_template_ordinal,),
        observed_storage_pressure_millionths=(assignment.target_storage_pressure_millionths),
    )


def _powered_teacher(
    emulator: CleanPowerFreshEpisodeEmulator,
    _assignment: RedLivingDexPoweredSupplyAssignment,
) -> RedLivingDexFreshEpisodeCheckpoint:
    emulator.tick(DEFAULT_NEW_GAME_TIMING.boot_frames)
    emulator.press("a")
    emulator.tick(8)
    emulator.release("a")
    emulator.tick(100)
    return _checkpoint()


def _powered_conditioner(
    emulator: CleanPowerFreshEpisodeEmulator,
    _assignment: RedLivingDexPoweredSupplyAssignment,
) -> None:
    emulator.press("down")
    emulator.tick(8)
    emulator.release("down")
    emulator.tick(16)


def _powered_verifier(
    _emulator,  # type: ignore[no-untyped-def]
    assignment,  # type: ignore[no-untyped-def]
    _root,  # type: ignore[no-untyped-def]
    _envelope,  # type: ignore[no-untyped-def]
) -> RedLivingDexPoweredSupplyTargetVerification:
    return RedLivingDexPoweredSupplyTargetVerification(
        compatible_template_ordinals=(assignment.target_template_ordinal,),
        observed_pressure_millionths=(0, 100_000, 200_000, 300_000, 400_000, 500_000, 600_000),
    )


def _execute(tmp_path: Path, **overrides):  # type: ignore[no-untyped-def]
    plan = _plan()
    assignment = plan.assignments[0]
    fake = _FakeEmulator()
    registry = _registry(tmp_path)
    store = _store(tmp_path)
    arguments = {
        "source_commit": plan.source_commit,
        "source_bundle_sha256": plan.source_bundle_sha256,
        "generator_execution_sha256": plan.generator_execution_sha256,
        "runner_sha256": _digest("runner"),
        "process_authority": (issue_red_living_dex_fresh_episode_process_authority()),
        "private_store": store,
        "claim_registry": registry,
        "emulator_factory": lambda: fake,
        "setup_teacher": _teacher,
        "condition_target": _conditioner,
        "verify_target": _verifier,
        "post_close_verify": lambda: None,
    }
    arguments.update(overrides)
    result = execute_red_living_dex_fresh_episode(
        plan,
        assignment.assignment_id,
        **arguments,
    )
    return plan, assignment, fake, registry, store, result


def test_runtime_claims_before_input_and_retains_one_private_root(
    tmp_path: Path,
) -> None:
    plan = _plan()
    assignment = plan.assignments[0]
    registry = _registry(tmp_path)
    store = _store(tmp_path)
    fake = _FakeEmulator()

    def factory() -> _FakeEmulator:
        claim = read_red_living_dex_fresh_episode_assignment_claim(
            registry,
            assignment.assignment_id,
        )
        assert claim["plan_sha256"] == plan.plan_sha256
        assert fake.events == []
        return fake

    result = execute_red_living_dex_fresh_episode(
        plan,
        assignment.assignment_id,
        source_commit=plan.source_commit,
        source_bundle_sha256=plan.source_bundle_sha256,
        generator_execution_sha256=plan.generator_execution_sha256,
        runner_sha256=_digest("runner"),
        process_authority=issue_red_living_dex_fresh_episode_process_authority(),
        private_store=store,
        claim_registry=registry,
        emulator_factory=factory,
        setup_teacher=_teacher,
        condition_target=_conditioner,
        verify_target=_verifier,
        post_close_verify=lambda: None,
    )

    assert result.receipt.started_from_clean_power is True
    assert result.receipt.save_state_loads == 0
    assert result.receipt.terminal_state_saves == 1
    assert result.receipt.first_controller_input_frame == (
        assignment.initial_wait_frames + DEFAULT_NEW_GAME_TIMING.boot_frames
    )
    assert result.receipt.target_template_ordinal in (result.receipt.compatible_template_ordinals)
    claim = read_red_living_dex_fresh_episode_assignment_claim(
        registry,
        assignment.assignment_id,
    )
    assert result.receipt.plan_sha256 == plan.plan_sha256
    assert result.receipt.assignment_claim_sha256 == canonical_sha256(claim)
    assert result.public_dict()["assignment_claims"] == 1
    assert result.public_dict()["root_consumption_claims"] == 0
    assert result.artifact_summary.status == "complete"
    assert fake.save_calls == 1
    assert fake.closed is True

    episode = store.open_episode(assignment.episode_id)
    records = tuple(episode.iter_stream("root", max_records=1))
    root, receipt = decode_red_living_dex_fresh_episode_private_root(records[0])
    assert root.state_sha256 == result.root.state_sha256
    assert receipt["assignment_id"] == assignment.assignment_id
    assert "/Users/" not in json.dumps(result.public_dict())


def test_guard_rejects_restore_and_unauthorized_or_second_save() -> None:
    assignment = _plan().assignments[0]
    fake = _FakeEmulator()
    guard = CleanPowerFreshEpisodeEmulator(fake, assignment)

    with pytest.raises(
        RedLivingDexFreshEpisodeRuntimeError,
        match="restoration is forbidden",
    ):
        guard.load_state_bytes(b"checkpoint")
    assert guard.save_state_loads == 1

    guard.perform_initial_wait()
    _teacher(guard, assignment)
    guard.seal_teacher_prefix(_checkpoint())
    with pytest.raises(
        RedLivingDexFreshEpisodeRuntimeError,
        match="save authority differs",
    ):
        guard.capture_terminal_state(_token=object())
    with pytest.raises(EmulatorError, match="capture authority differs"):
        guard._port.capture_state_bytes(token=object())
    for leaked_name in (
        "_backend",
        "advance",
        "button_down",
        "button_up",
        "capture_state_bytes",
    ):
        with pytest.raises(AttributeError):
            getattr(guard, leaked_name)
    assert fake.save_calls == 0
    payload = guard.capture_terminal_state(_token=runtime._TERMINAL_SAVE_TOKEN)
    assert payload
    with pytest.raises(
        RedLivingDexFreshEpisodeRuntimeError,
        match="already saved",
    ):
        guard.capture_terminal_state(_token=runtime._TERMINAL_SAVE_TOKEN)


def test_guard_seals_prefix_before_target_specific_conditioning() -> None:
    assignment = _plan().assignments[0]
    guard = CleanPowerFreshEpisodeEmulator(_FakeEmulator(), assignment)
    guard.perform_initial_wait()
    _teacher(guard, assignment)
    before = guard.seal_teacher_prefix(_checkpoint())

    _conditioner(guard, assignment)

    assert guard.teacher_prefix_sha256 == before


def test_guard_enforces_exact_frame_and_controller_bounds(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assignment = _plan().assignments[0]
    fake = _FakeEmulator()
    guard = CleanPowerFreshEpisodeEmulator(fake, assignment)
    frame_limit = assignment.initial_wait_frames + DEFAULT_NEW_GAME_TIMING.boot_frames
    monkeypatch.setattr(
        runtime,
        "RED_LIVING_DEX_SETUP_MAX_EMULATOR_FRAMES",
        frame_limit,
    )
    monkeypatch.setattr(
        runtime,
        "RED_LIVING_DEX_SETUP_MAX_CONTROLLER_ACTIONS",
        1,
    )

    guard.perform_initial_wait()
    guard.tick(DEFAULT_NEW_GAME_TIMING.boot_frames)
    guard.press("a")
    guard.release("a")
    with pytest.raises(
        RedLivingDexFreshEpisodeRuntimeError,
        match="action bound",
    ):
        guard.press("b")
    with pytest.raises(
        RedLivingDexFreshEpisodeRuntimeError,
        match="frame bound",
    ):
        guard.tick(1)

    assert fake.frame_count == frame_limit
    assert guard.controller_actions == 1


def test_first_controller_frame_drift_fails_closed(tmp_path: Path) -> None:
    def late_teacher(
        emulator: CleanPowerFreshEpisodeEmulator,
        _assignment: RedLivingDexFreshEpisodeAssignment,
    ) -> RedLivingDexFreshEpisodeCheckpoint:
        emulator.tick(DEFAULT_NEW_GAME_TIMING.boot_frames + 1)
        emulator.press("a")
        raise AssertionError("unreachable")

    with pytest.raises(
        RedLivingDexFreshEpisodeRuntimeError,
        match="first controller input frame differs",
    ):
        _execute(tmp_path, setup_teacher=late_teacher)


def test_off_target_verification_consumes_attempt_without_publishing_root(
    tmp_path: Path,
) -> None:
    def off_target(
        _emulator,  # type: ignore[no-untyped-def]
        _assignment,  # type: ignore[no-untyped-def]
        _root,  # type: ignore[no-untyped-def]
        _envelope,  # type: ignore[no-untyped-def]
    ) -> RedLivingDexFreshEpisodeTargetVerification:
        return RedLivingDexFreshEpisodeTargetVerification(
            compatible_template_ordinals=(0,),
            observed_storage_pressure_millionths=625_000,
        )

    plan = _plan()
    assignment = plan.assignments[0]
    registry = _registry(tmp_path)
    store = _store(tmp_path)
    with pytest.raises(
        RedLivingDexFreshEpisodeRuntimeError,
        match="missed its declared menu",
    ):
        execute_red_living_dex_fresh_episode(
            plan,
            assignment.assignment_id,
            source_commit=plan.source_commit,
            source_bundle_sha256=plan.source_bundle_sha256,
            generator_execution_sha256=plan.generator_execution_sha256,
            runner_sha256=_digest("runner"),
            process_authority=(issue_red_living_dex_fresh_episode_process_authority()),
            private_store=store,
            claim_registry=registry,
            emulator_factory=_FakeEmulator,
            setup_teacher=_teacher,
            condition_target=_conditioner,
            verify_target=off_target,
            post_close_verify=lambda: None,
        )

    assert store.inspect_episode_state(assignment.episode_id).status == "failed"
    assert (
        read_red_living_dex_fresh_episode_assignment_claim(
            registry,
            assignment.assignment_id,
        )["assignment_id"]
        == assignment.assignment_id
    )


def test_effectful_target_verifier_is_detected_even_through_delegate(
    tmp_path: Path,
) -> None:
    def effectful(
        emulator,  # type: ignore[no-untyped-def]
        assignment,  # type: ignore[no-untyped-def]
        root,  # type: ignore[no-untyped-def]
        envelope,  # type: ignore[no-untyped-def]
    ) -> RedLivingDexFreshEpisodeTargetVerification:
        emulator._port.advance(1)
        return _verifier(emulator, assignment, root, envelope)

    with pytest.raises(
        RedLivingDexFreshEpisodeRuntimeError,
        match="low-level accounting differs",
    ):
        _execute(tmp_path, verify_target=effectful)


@pytest.mark.parametrize("bypass", ("frame", "button", "capture"))
def test_setup_teacher_cannot_hide_a_low_level_port_effect(
    tmp_path: Path,
    bypass: str,
) -> None:
    def bypassing_teacher(
        emulator: CleanPowerFreshEpisodeEmulator,
        assignment: RedLivingDexFreshEpisodeAssignment,
    ) -> RedLivingDexFreshEpisodeCheckpoint:
        checkpoint = _teacher(emulator, assignment)
        if bypass == "frame":
            emulator._port.advance(1)
        elif bypass == "button":
            emulator._port.button_down("b")
        else:
            emulator._port.capture_state_bytes(token=runtime._TERMINAL_SAVE_TOKEN)
        return checkpoint

    with pytest.raises(
        RedLivingDexFreshEpisodeRuntimeError,
        match="low-level accounting differs",
    ):
        _execute(tmp_path, setup_teacher=bypassing_teacher)


def test_post_close_isolation_failure_aborts_private_success(
    tmp_path: Path,
) -> None:
    plan = _plan()
    assignment = plan.assignments[0]
    registry = _registry(tmp_path)
    store = _store(tmp_path)

    def isolation_failure() -> None:
        raise RedLivingDexFreshEpisodeRuntimeError("ROM isolation changed")

    with pytest.raises(
        RedLivingDexFreshEpisodeRuntimeError,
        match="ROM isolation changed",
    ):
        execute_red_living_dex_fresh_episode(
            plan,
            assignment.assignment_id,
            source_commit=plan.source_commit,
            source_bundle_sha256=plan.source_bundle_sha256,
            generator_execution_sha256=plan.generator_execution_sha256,
            runner_sha256=_digest("runner"),
            process_authority=(issue_red_living_dex_fresh_episode_process_authority()),
            private_store=store,
            claim_registry=registry,
            emulator_factory=_FakeEmulator,
            setup_teacher=_teacher,
            condition_target=_conditioner,
            verify_target=_verifier,
            post_close_verify=isolation_failure,
        )

    assert store.inspect_episode_state(assignment.episode_id).status == "failed"


def test_durable_assignment_claim_is_non_retryable(tmp_path: Path) -> None:
    registry = _registry(tmp_path)
    assignment = _plan().assignments[0]
    values = {
        "assignment_id": assignment.assignment_id,
        "execution_identity_sha256": _digest("execution"),
        "plan_sha256": _plan().plan_sha256,
        "source_commit": "a" * 40,
        "runner_sha256": _digest("runner"),
    }

    first = durably_claim_red_living_dex_fresh_episode_assignment(
        registry,
        **values,
    )
    with pytest.raises(
        RedLivingDexFreshEpisodeRuntimeError,
        match="already consumed",
    ):
        durably_claim_red_living_dex_fresh_episode_assignment(
            registry,
            **values,
        )

    assert first == read_red_living_dex_fresh_episode_assignment_claim(
        registry,
        assignment.assignment_id,
    )
    assert set(first) == {
        "assignment_id",
        "execution_identity_sha256",
        "plan_sha256",
        "runner_sha256",
        "schema",
        "source_commit",
    }
    assert first["schema"] == RED_LIVING_DEX_FRESH_EPISODE_ASSIGNMENT_CLAIM_SCHEMA


def test_one_process_cannot_issue_two_episode_authorities() -> None:
    authority = issue_red_living_dex_fresh_episode_process_authority()
    assert authority.pid == os.getpid()

    with pytest.raises(
        RedLivingDexFreshEpisodeRuntimeError,
        match="already issued",
    ):
        issue_red_living_dex_fresh_episode_process_authority()


def test_execution_binding_drift_precedes_private_claim(tmp_path: Path) -> None:
    plan = _plan()
    assignment = plan.assignments[0]
    store = _store(tmp_path)
    registry = _registry(tmp_path)

    with pytest.raises(
        RedLivingDexFreshEpisodeRuntimeError,
        match="published execution binding differs",
    ):
        execute_red_living_dex_fresh_episode(
            plan,
            assignment.assignment_id,
            source_commit=plan.source_commit,
            source_bundle_sha256=plan.source_bundle_sha256,
            generator_execution_sha256=_digest("changed"),
            runner_sha256=_digest("runner"),
            process_authority=(issue_red_living_dex_fresh_episode_process_authority()),
            private_store=store,
            claim_registry=registry,
            emulator_factory=_FakeEmulator,
            setup_teacher=_teacher,
            condition_target=_conditioner,
            verify_target=_verifier,
            post_close_verify=lambda: None,
        )

    assert store.inspect_episode_state(assignment.episode_id).status == "absent"
    assert not tuple(registry.glob("fresh-episode-assignment-*.json"))


def test_private_episode_namespace_blocks_restart_retry(tmp_path: Path) -> None:
    plan = _plan()
    assignment = plan.assignments[0]
    store = _store(tmp_path)
    registry = _registry(tmp_path)

    def crash(
        _emulator: CleanPowerFreshEpisodeEmulator,
        _assignment: RedLivingDexFreshEpisodeAssignment,
    ) -> None:
        raise RuntimeError("power loss")

    with pytest.raises(
        RedLivingDexFreshEpisodeExecutionFailure,
        match="power loss",
    ) as caught:
        execute_red_living_dex_fresh_episode(
            plan,
            assignment.assignment_id,
            source_commit=plan.source_commit,
            source_bundle_sha256=plan.source_bundle_sha256,
            generator_execution_sha256=plan.generator_execution_sha256,
            runner_sha256=_digest("runner"),
            process_authority=(issue_red_living_dex_fresh_episode_process_authority()),
            private_store=store,
            claim_registry=registry,
            emulator_factory=_FakeEmulator,
            setup_teacher=_teacher,
            condition_target=crash,
            verify_target=_verifier,
            post_close_verify=lambda: None,
        )

    assert caught.value.execution_phase == "target_conditioning"
    assert caught.value.effects_known is True
    assert caught.value.controller_actions == 1
    assert caught.value.emulator_frames == (
        assignment.initial_wait_frames + DEFAULT_NEW_GAME_TIMING.boot_frames + 8 + 100
    )
    diagnostic_path = (
        tmp_path
        / "private"
        / f"{assignment.episode_id}.failed.partial"
        / "failure_diagnostic.jsonl"
    )
    diagnostic_text = diagnostic_path.read_text(encoding="ascii")
    diagnostic = json.loads(diagnostic_text)
    assert diagnostic["execution_phase"] == "target_conditioning"
    assert diagnostic["effects_known"] is True
    assert diagnostic["controller_actions"] == 1
    assert diagnostic["pressed_button_count"] == 0
    assert diagnostic["terminal_root_generated"] is False
    assert diagnostic["exception_chain"][0]["exception_name"] == "RuntimeError"
    assert "power loss" not in diagnostic_text
    assert "/" not in diagnostic_text
    runtime._PROCESS_AUTHORITY_ISSUED = False

    with pytest.raises(PrivateArtifactError, match="already present"):
        execute_red_living_dex_fresh_episode(
            plan,
            assignment.assignment_id,
            source_commit=plan.source_commit,
            source_bundle_sha256=plan.source_bundle_sha256,
            generator_execution_sha256=plan.generator_execution_sha256,
            runner_sha256=_digest("runner"),
            process_authority=(issue_red_living_dex_fresh_episode_process_authority()),
            private_store=store,
            claim_registry=registry,
            emulator_factory=_FakeEmulator,
            setup_teacher=_teacher,
            condition_target=_conditioner,
            verify_target=_verifier,
            post_close_verify=lambda: None,
        )


@pytest.mark.parametrize("assignment_index", (0, 3, 11))
def test_powered_supply_runtime_preserves_role_and_partition_without_learning(
    tmp_path: Path,
    assignment_index: int,
) -> None:
    plan = _powered_plan()
    assignment = plan.assignments[assignment_index]
    registry = _registry(tmp_path)
    store = _store(tmp_path)
    fake = _FakeEmulator()

    with store.collection_session(
        powered_supply_collection_id(plan.plan_sha256)
    ) as collection_session:
        result = execute_red_living_dex_powered_supply_episode(
            plan,
            assignment.assignment_id,
            source_commit=plan.source_commit,
            source_bundle_sha256=plan.source_bundle_sha256,
            generator_execution_sha256=plan.generator_execution_sha256,
            runner_sha256=plan.generator_runner_sha256,
            runtime_identity_sha256=plan.runtime_identity_sha256,
            process_authority=issue_red_living_dex_fresh_episode_process_authority(),
            private_store=store,
            collection_session=collection_session,
            claim_registry=registry,
            emulator_factory=lambda: fake,
            setup_teacher=_powered_teacher,
            condition_target=_powered_conditioner,
            verify_target=_powered_verifier,
            post_close_verify=lambda: None,
        )

    assert result.receipt.role == assignment.role
    assert result.receipt.partition == assignment.partition
    assert result.receipt.root_lineage_id == assignment.root_lineage_id
    assert result.receipt.physical_root_sha256 == result.root.physical_root_sha256
    assert result.receipt.root_consumption_sha256 == result.root.root_consumption_sha256
    assert result.receipt.target_template_ordinal in (result.receipt.compatible_template_ordinals)
    assert result.receipt.observed_pressure_millionths == (
        0,
        100_000,
        200_000,
        300_000,
        400_000,
        500_000,
        600_000,
    )
    public = result.public_dict()
    assert public["population_scale_authorized"] is False
    assert public["recensus_required"] is True
    assert public["learner_teacher_queries"] == 0
    assert public["learner_labels"] == 0
    assert public["learner_outcomes"] == 0
    assert public["model_predictions"] == 0
    assert public["model_fits"] == 0
    assert fake.save_calls == 1
    assert fake.closed is True
    claim = read_red_living_dex_powered_supply_assignment_claim(
        registry,
        assignment.assignment_id,
    )
    assert set(claim) == {
        "assignment_id",
        "execution_identity_sha256",
        "plan_sha256",
        "runner_sha256",
        "runtime_identity_sha256",
        "schema",
        "source_commit",
    }
    assert claim["schema"] == RED_LIVING_DEX_POWERED_SUPPLY_ASSIGNMENT_CLAIM_SCHEMA
    assert claim["runtime_identity_sha256"] == plan.runtime_identity_sha256
    assert claim["execution_identity_sha256"] == (
        compose_red_living_dex_powered_supply_runtime_execution_sha256(
            assignment_id=assignment.assignment_id,
            plan_sha256=plan.plan_sha256,
            source_commit=plan.source_commit,
            generator_execution_sha256=plan.generator_execution_sha256,
            generator_runner_sha256=plan.generator_runner_sha256,
            runtime_identity_sha256=plan.runtime_identity_sha256,
        )
    )
    records = tuple(
        store.open_episode(assignment.episode_id).iter_stream(
            "root",
            max_records=1,
        )
    )
    decoded_root, decoded_receipt = (
        decode_red_living_dex_powered_supply_private_root(records[0])
    )
    assert decoded_root.state_sha256 == result.root.state_sha256
    assert decoded_receipt == result.receipt
    with pytest.raises(
        RedLivingDexFreshEpisodeRuntimeError,
        match="private root schema differs",
    ):
        decode_red_living_dex_fresh_episode_private_root(records[0])


def test_powered_private_root_decoder_rejects_receipt_or_byte_drift(
    tmp_path: Path,
) -> None:
    plan = _powered_plan()
    assignment = plan.assignments[0]
    store = _store(tmp_path)
    with store.collection_session(
        powered_supply_collection_id(plan.plan_sha256)
    ) as collection_session:
        result = execute_red_living_dex_powered_supply_episode(
            plan,
            assignment.assignment_id,
            source_commit=plan.source_commit,
            source_bundle_sha256=plan.source_bundle_sha256,
            generator_execution_sha256=plan.generator_execution_sha256,
            runner_sha256=plan.generator_runner_sha256,
            runtime_identity_sha256=plan.runtime_identity_sha256,
            process_authority=issue_red_living_dex_fresh_episode_process_authority(),
            private_store=store,
            collection_session=collection_session,
            claim_registry=_registry(tmp_path),
            emulator_factory=_FakeEmulator,
            setup_teacher=_powered_teacher,
            condition_target=_powered_conditioner,
            verify_target=_powered_verifier,
            post_close_verify=lambda: None,
        )
    record = next(
        store.open_episode(assignment.episode_id).iter_stream(
            "root",
            max_records=1,
        )
    )
    assert decode_red_living_dex_powered_supply_private_root(record)[0] == (
        result.root
    )

    changed_receipt = dict(record)
    changed_receipt["receipt"] = {
        **dict(record["receipt"]),  # type: ignore[arg-type]
        "partition": "development",
    }
    with pytest.raises(
        RedLivingDexFreshEpisodeRuntimeError,
        match="private receipt differs",
    ):
        decode_red_living_dex_powered_supply_private_root(changed_receipt)

    changed_state = dict(record)
    changed_state["state_base64"] = "YQ=="
    with pytest.raises(
        RedLivingDexFreshEpisodeRuntimeError,
        match="root and receipt differ",
    ):
        decode_red_living_dex_powered_supply_private_root(changed_state)


def test_powered_supply_off_target_development_root_is_consumed_and_rejected(
    tmp_path: Path,
) -> None:
    plan = _powered_plan()
    assignment = plan.assignments[3]
    registry = _registry(tmp_path)
    store = _store(tmp_path)

    def wrong_partition(
        _emulator,  # type: ignore[no-untyped-def]
        _assignment,  # type: ignore[no-untyped-def]
        _root,  # type: ignore[no-untyped-def]
        _envelope,  # type: ignore[no-untyped-def]
    ) -> RedLivingDexPoweredSupplyTargetVerification:
        return RedLivingDexPoweredSupplyTargetVerification(
            compatible_template_ordinals=(0,),
            observed_pressure_millionths=(0, 0, 0, 0, 0, 0, 0),
        )

    with (
        store.collection_session(
            powered_supply_collection_id(plan.plan_sha256)
        ) as collection_session,
        pytest.raises(
            RedLivingDexFreshEpisodeRuntimeError,
            match="declared partition menu",
        ),
    ):
        execute_red_living_dex_powered_supply_episode(
            plan,
            assignment.assignment_id,
            source_commit=plan.source_commit,
            source_bundle_sha256=plan.source_bundle_sha256,
            generator_execution_sha256=plan.generator_execution_sha256,
            runner_sha256=plan.generator_runner_sha256,
            runtime_identity_sha256=plan.runtime_identity_sha256,
            process_authority=(issue_red_living_dex_fresh_episode_process_authority()),
            private_store=store,
            collection_session=collection_session,
            claim_registry=registry,
            emulator_factory=_FakeEmulator,
            setup_teacher=_powered_teacher,
            condition_target=_powered_conditioner,
            verify_target=wrong_partition,
            post_close_verify=lambda: None,
        )

    assert store.inspect_episode_state(assignment.episode_id).status == "failed"
    assert (
        read_red_living_dex_powered_supply_assignment_claim(registry, assignment.assignment_id)[
            "assignment_id"
        ]
        == assignment.assignment_id
    )


def test_powered_supply_runtime_rejects_unpublished_runner_before_claim(
    tmp_path: Path,
) -> None:
    plan = _powered_plan()
    assignment = plan.assignments[0]
    registry = _registry(tmp_path)
    store = _store(tmp_path)

    with store.collection_session(
        powered_supply_collection_id(plan.plan_sha256)
    ) as collection_session, pytest.raises(
        RedLivingDexFreshEpisodeRuntimeError,
        match="published execution binding differs",
    ):
        execute_red_living_dex_powered_supply_episode(
            plan,
            assignment.assignment_id,
            source_commit=plan.source_commit,
            source_bundle_sha256=plan.source_bundle_sha256,
            generator_execution_sha256=plan.generator_execution_sha256,
            runner_sha256=_digest("unpublished-runner"),
            runtime_identity_sha256=plan.runtime_identity_sha256,
            process_authority=issue_red_living_dex_fresh_episode_process_authority(),
            private_store=store,
            collection_session=collection_session,
            claim_registry=registry,
            emulator_factory=_FakeEmulator,
            setup_teacher=_powered_teacher,
            condition_target=_powered_conditioner,
            verify_target=_powered_verifier,
            post_close_verify=lambda: None,
        )

    assert store.inspect_episode_state(assignment.episode_id).status == "absent"
    assert not tuple(registry.iterdir())


def test_powered_supply_runtime_rejects_runtime_drift_before_claim(
    tmp_path: Path,
) -> None:
    plan = _powered_plan()
    assignment = plan.assignments[0]
    registry = _registry(tmp_path)
    store = _store(tmp_path)

    with store.collection_session(
        powered_supply_collection_id(plan.plan_sha256)
    ) as collection_session, pytest.raises(
        RedLivingDexFreshEpisodeRuntimeError,
        match="published execution binding differs",
    ):
        execute_red_living_dex_powered_supply_episode(
            plan,
            assignment.assignment_id,
            source_commit=plan.source_commit,
            source_bundle_sha256=plan.source_bundle_sha256,
            generator_execution_sha256=plan.generator_execution_sha256,
            runner_sha256=plan.generator_runner_sha256,
            runtime_identity_sha256=_digest("different-runtime"),
            process_authority=issue_red_living_dex_fresh_episode_process_authority(),
            private_store=store,
            collection_session=collection_session,
            claim_registry=registry,
            emulator_factory=_FakeEmulator,
            setup_teacher=_powered_teacher,
            condition_target=_powered_conditioner,
            verify_target=_powered_verifier,
            post_close_verify=lambda: None,
        )

    assert store.inspect_episode_state(assignment.episode_id).status == "absent"
    assert not tuple(registry.iterdir())


def test_powered_supply_runtime_requires_an_active_plan_scoped_session(
    tmp_path: Path,
) -> None:
    plan = _powered_plan()
    assignment = plan.assignments[0]
    registry = _registry(tmp_path)
    store = _store(tmp_path)
    inactive_session = store.collection_session(
        powered_supply_collection_id(plan.plan_sha256)
    )

    with pytest.raises(PrivateArtifactError, match="session is not active"):
        execute_red_living_dex_powered_supply_episode(
            plan,
            assignment.assignment_id,
            source_commit=plan.source_commit,
            source_bundle_sha256=plan.source_bundle_sha256,
            generator_execution_sha256=plan.generator_execution_sha256,
            runner_sha256=plan.generator_runner_sha256,
            runtime_identity_sha256=plan.runtime_identity_sha256,
            process_authority=issue_red_living_dex_fresh_episode_process_authority(),
            private_store=store,
            collection_session=inactive_session,
            claim_registry=registry,
            emulator_factory=_FakeEmulator,
            setup_teacher=_powered_teacher,
            condition_target=_powered_conditioner,
            verify_target=_powered_verifier,
            post_close_verify=lambda: None,
        )

    assert store.inspect_episode_state(assignment.episode_id).status == "absent"
    assert not tuple(registry.iterdir())
