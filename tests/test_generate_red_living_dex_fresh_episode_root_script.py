from __future__ import annotations

import hashlib
import json
import runpy
from pathlib import Path
from types import SimpleNamespace

import pytest

from pokemon_red_completion.living_dex_option_value import LivingDexOptionKind
from pokemon_red_completion.red_living_dex_capture_plan import (
    build_red_living_dex_prospective_capture_plan,
)
from pokemon_red_completion.red_living_dex_episode_lineage import (
    RedLivingDexFreshEpisodeFailureReceipt,
    build_red_living_dex_fresh_episode_plan,
    compose_red_living_dex_fresh_episode_generator_execution_sha256,
    compose_red_living_dex_fresh_episode_teacher_execution_sha256,
)
from pokemon_red_completion.red_living_dex_fresh_episode_runtime import (
    RedLivingDexFreshEpisodeExecutionFailure,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = (
    PROJECT_ROOT / "scripts/generate_red_living_dex_fresh_episode_root.py"
)
SCRIPT = runpy.run_path(
    str(SCRIPT_PATH),
    run_name="generate_red_living_dex_fresh_episode_root_test",
)


def _digest(label: str) -> str:
    return hashlib.sha256(label.encode("ascii")).hexdigest()


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


def test_cli_is_exactly_one_assignment_and_has_no_learning_or_retry_surface() -> None:
    parser = SCRIPT["_parser"]()
    parsed = parser.parse_args(
        [
            "--plan",
            "/private/plan.json",
            "--expected-plan-sha256",
            "a" * 64,
            "--assignment-id",
            "b" * 64,
            "--expected-source-commit",
            "c" * 40,
            "--expected-source-bundle-sha256",
            "d" * 64,
            "--expected-generator-execution-sha256",
            "e" * 64,
            "--private-root",
            "/private/store",
        ]
    )

    assert parsed.assignment_id == "b" * 64
    for forbidden in (
        "retry",
        "episodes",
        "model",
        "fit",
        "outcome",
        "sealed_red",
        "crystal",
        "load_state",
    ):
        assert not hasattr(parsed, forbidden)


def test_generator_execution_digest_binds_conditioner_and_runner(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    generator = tmp_path / "generator.py"
    conditioner = tmp_path / "conditioner.py"
    generator.write_bytes(b"generator-v1\n")
    conditioner.write_bytes(b"conditioner-v1\n")
    globals_ = SCRIPT["_generator_execution_sha256"].__globals__
    monkeypatch.setitem(globals_, "GENERATOR_PATH", generator)
    monkeypatch.setitem(globals_, "MATERIALIZER_PATH", conditioner)
    source = _digest("source")

    first = SCRIPT["_generator_execution_sha256"](source)
    conditioner.write_bytes(b"conditioner-v2\n")
    second = SCRIPT["_generator_execution_sha256"](source)

    assert first != second
    assert first == compose_red_living_dex_fresh_episode_generator_execution_sha256(
        source_bundle_sha256=source,
        generator_runner_sha256=hashlib.sha256(b"generator-v1\n").hexdigest(),
        conditioner_runner_sha256=hashlib.sha256(
            b"conditioner-v1\n"
        ).hexdigest(),
    )


def test_materializer_executes_only_the_exact_prehashed_bytes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    conditioner = tmp_path / "conditioner.py"
    payload = b"BOUND_VALUE = 17\n"
    conditioner.write_bytes(payload)
    globals_ = SCRIPT["_load_materializer"].__globals__
    monkeypatch.setitem(globals_, "MATERIALIZER_PATH", conditioner)
    monkeypatch.setitem(globals_, "_MATERIALIZER", None)
    monkeypatch.setitem(globals_, "_MATERIALIZER_SHA256", None)

    loaded = SCRIPT["_load_materializer"](hashlib.sha256(payload).hexdigest())
    assert loaded["BOUND_VALUE"] == 17

    monkeypatch.setitem(globals_, "_MATERIALIZER", None)
    monkeypatch.setitem(globals_, "_MATERIALIZER_SHA256", None)
    conditioner.write_bytes(b"BOUND_VALUE = 18\n")
    with pytest.raises(
        SCRIPT["FreshEpisodeGeneratorError"],
        match="conditioner_authentication",
    ):
        SCRIPT["_load_materializer"](hashlib.sha256(payload).hexdigest())


@pytest.mark.parametrize(
    ("assignment_index", "expected_mode", "expected_box_count"),
    ((0, "storage-ready", 17), (12, "story-resource-scarce", None)),
)
def test_target_conditioning_uses_only_the_preregistered_mode(
    assignment_index: int,
    expected_mode: str,
    expected_box_count: int | None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assignment = _plan().assignments[assignment_index]
    calls: list[tuple[str, int | None]] = []

    class _Quest:
        def objective(self, _objective_id: str) -> object:
            return SimpleNamespace(completion_facts=frozenset({"fact"}))

        def completed_ids(self, _state: object) -> frozenset[str]:
            return frozenset({"power_on", "begin_adventure"})

    class _Observer:
        def __init__(self, *_args: object) -> None:
            pass

        def latch_verified_facts(self, _facts: frozenset[str]) -> None:
            pass

        def observe(self) -> object:
            return object()

    class _Reader:
        def __init__(self, _emulator: object) -> None:
            pass

        def read(self) -> object:
            return SimpleNamespace(battle_state=0)

        def read_input_readiness(self) -> object:
            return SimpleNamespace(ready=True)

    class _Emulator:
        pressed_buttons: frozenset[str] = frozenset()

    def apply_mode(mode: str, *_args: object, **kwargs: object) -> None:
        calls.append((mode, kwargs.get("target_active_box_count")))  # type: ignore[arg-type]

    globals_ = SCRIPT["_apply_target_conditioning"].__globals__
    monkeypatch.setitem(globals_, "COMPLETION_QUEST", _Quest())
    monkeypatch.setitem(globals_, "LivePokemonRedObserver", _Observer)
    monkeypatch.setitem(globals_, "PokemonRedStateReader", _Reader)
    monkeypatch.setitem(
        globals_,
        "PokemonRedGoalStateAdapter",
        lambda *_args: object(),
    )
    monkeypatch.setitem(globals_, "FrameSafeExecutor", lambda *_args: object())
    monkeypatch.setitem(globals_, "CountingExecutor", lambda value: value)
    monkeypatch.setitem(globals_, "_MATERIALIZER", {"_apply_mode": apply_mode})

    SCRIPT["_apply_target_conditioning"](
        _Emulator(),
        assignment,
        SimpleNamespace(
            verified_objective_ids=("power_on", "begin_adventure")
        ),
    )

    assert calls == [(expected_mode, expected_box_count)]


def test_template_five_intentionally_uses_zero_ball_resupply_scarcity() -> None:
    slot = build_red_living_dex_prospective_capture_plan().slots[5]

    assert slot.available_option_kinds == (
        LivingDexOptionKind.RESUPPLY,
        LivingDexOptionKind.UNLOCK_ACCESS,
        LivingDexOptionKind.EXPLORE,
    )
    assert LivingDexOptionKind.ACQUIRE not in slot.available_option_kinds


def test_runtime_failure_does_not_falsely_report_zero_effects(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    globals_ = SCRIPT["main"].__globals__
    monkeypatch.setitem(
        globals_,
        "_run",
        lambda _args: (_ for _ in ()).throw(
            SCRIPT["FreshEpisodeGeneratorError"]("fresh_episode_execution")
        ),
    )
    monkeypatch.setitem(
        globals_,
        "_parser",
        lambda: SimpleNamespace(parse_args=lambda _argv: object()),
    )

    assert SCRIPT["main"]([]) == 1
    failure = json.loads(capsys.readouterr().out)

    assert failure["stage"] == "fresh_episode_execution"
    assert failure["effects_unknown"] is True
    assert failure["controller_actions"] is None
    assert failure["model_fits"] is None


def test_generator_preserves_only_reconciled_runtime_effect_counters() -> None:
    known = RedLivingDexFreshEpisodeExecutionFailure(
        "private diagnostic omitted",
        execution_phase="setup_teacher",
        effects_known=True,
        controller_actions=17,
        emulator_frames=2_417,
    )

    assert SCRIPT["_known_runtime_effects"](known) == (True, 17, 2_417)
    assert SCRIPT["_known_runtime_effects"](RuntimeError("unknown")) == (
        False,
        None,
        None,
    )


def test_consumed_runtime_failure_emits_a_terminal_nonretry_disposition(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    plan = _plan()
    assignment = plan.assignments[0]
    terminal = RedLivingDexFreshEpisodeFailureReceipt(
        assignment_id=assignment.assignment_id,
        plan_sha256=plan.plan_sha256,
        source_bundle_sha256=assignment.source_bundle_sha256,
        teacher_execution_sha256=assignment.teacher_execution_sha256,
        generator_execution_sha256=assignment.generator_execution_sha256,
        assignment_claim_sha256=_digest("claim"),
        failure_stage="fresh_episode_execution",
        effects_known=False,
        controller_actions=None,
        emulator_frames=None,
    )
    globals_ = SCRIPT["main"].__globals__
    monkeypatch.setitem(
        globals_,
        "_run",
        lambda _args: (_ for _ in ()).throw(
            SCRIPT["FreshEpisodeGeneratorError"](
                "fresh_episode_execution",
                terminal,
            )
        ),
    )
    monkeypatch.setitem(
        globals_,
        "_parser",
        lambda: SimpleNamespace(parse_args=lambda _argv: object()),
    )

    assert SCRIPT["main"]([]) == 1
    failure = json.loads(capsys.readouterr().out)
    assert failure["assignment_id"] == assignment.assignment_id
    assert failure["attempt_consumed"] is True
    assert failure["retry_allowed"] is False
    assert failure["terminal_root_generated"] is False
    assert failure["effects_known"] is False
