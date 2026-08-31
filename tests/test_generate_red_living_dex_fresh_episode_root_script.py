from __future__ import annotations

import hashlib
import json
import runpy
from contextlib import nullcontext
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
    encode_red_living_dex_fresh_episode_plan,
)
from pokemon_red_completion.red_living_dex_fresh_episode_runtime import (
    RED_LIVING_DEX_POWERED_SUPPLY_ASSIGNMENT_CLAIM_SCHEMA,
    RedLivingDexFreshEpisodeExecutionFailure,
)
from pokemon_red_completion.red_living_dex_powered_lineage_supply import (
    RedLivingDexPoweredSupplyFailure,
    build_red_living_dex_powered_supply_plan,
    compose_red_living_dex_powered_supply_generator_sha256,
    compose_red_living_dex_powered_supply_runtime_execution_sha256,
    compose_red_living_dex_powered_supply_teacher_sha256,
    encode_red_living_dex_powered_supply_plan,
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
    assert parsed.powered_supply is False
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


def test_cli_selects_v2_without_adding_retry_or_learning_authority() -> None:
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
            "--powered-supply",
        ]
    )

    assert parsed.powered_supply is True
    for forbidden in ("retry", "episodes", "fit", "outcome", "load_state"):
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


def test_powered_generator_execution_digest_binds_conditioner_and_runner(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    generator = tmp_path / "generator.py"
    conditioner = tmp_path / "conditioner.py"
    generator.write_bytes(b"powered-generator-v1\n")
    conditioner.write_bytes(b"powered-conditioner-v1\n")
    globals_ = SCRIPT["_powered_generator_execution_binding"].__globals__
    monkeypatch.setitem(globals_, "GENERATOR_PATH", generator)
    monkeypatch.setitem(globals_, "MATERIALIZER_PATH", conditioner)
    source = _digest("powered-source")

    first, runner, conditioning = SCRIPT["_powered_generator_execution_binding"](
        source
    )
    conditioner.write_bytes(b"powered-conditioner-v2\n")
    second, _runner, _conditioning = SCRIPT[
        "_powered_generator_execution_binding"
    ](source)

    assert first != second
    assert first == compose_red_living_dex_powered_supply_generator_sha256(
        source_bundle_sha256=source,
        generator_runner_sha256=runner,
        conditioner_runner_sha256=conditioning,
    )


def test_powered_post_close_rebuilds_every_published_binding(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    plan = _powered_plan()
    plan_path = tmp_path / "powered-plan.json"
    plan_payload = encode_red_living_dex_powered_supply_plan(plan)
    plan_path.write_bytes(plan_payload)
    rom_path = tmp_path / "red.gb"
    rom_path.write_bytes(b"authenticated-rom-placeholder")
    capacity_path = tmp_path / "powered-capacity.json"
    capacity_path.write_bytes(
        (
            PROJECT_ROOT
            / "docs/evidence/red-living-dex-clustered-powered-v2-capacity-result-v1-2026-08-31.json"
        ).read_bytes()
    )
    callback_box: list[object] = []
    state = {
        "adjacent": ((False, None),) * 3,
        "conditioner": plan.conditioner_runner_sha256,
        "episode_status": "absent",
        "execute_error": False,
        "generator": plan.generator_execution_sha256,
        "runner": plan.generator_runner_sha256,
        "runtime": plan.runtime_identity_sha256,
        "source_bundle": plan.source_bundle_sha256,
        "source_commit": plan.source_commit,
    }

    class _Store:
        def collection_session(self, _collection_id: str):  # type: ignore[no-untyped-def]
            return nullcontext(SimpleNamespace())

        def inspect_episode_state(self, _episode_id: str) -> SimpleNamespace:
            return SimpleNamespace(status=state["episode_status"])

    def generator_binding(_source_bundle: str) -> tuple[str, str, str]:
        return (
            state["generator"],
            state["runner"],
            state["conditioner"],
        )

    def execute(*_args: object, **kwargs: object) -> SimpleNamespace:
        if state["execute_error"]:
            raise RuntimeError("failed before durable claim")
        callback_box.append(kwargs["post_close_verify"])
        return SimpleNamespace(public_dict=lambda: {"status": "captured"})

    globals_ = SCRIPT["_run_powered"].__globals__
    monkeypatch.setitem(globals_, "POWERED_CAPACITY_RESULT_PATH", capacity_path)
    monkeypatch.setitem(
        globals_,
        "detect_source_identity",
        lambda *_args, **_kwargs: SimpleNamespace(git_commit=state["source_commit"]),
    )
    monkeypatch.setitem(globals_, "require_clean_source", lambda _source: None)
    monkeypatch.setitem(
        globals_,
        "require_published_source",
        lambda _root, _source: None,
    )
    monkeypatch.setitem(
        globals_,
        "working_source_bundle_sha256",
        lambda _root: state["source_bundle"],
    )
    monkeypatch.setitem(globals_, "_powered_generator_execution_binding", generator_binding)
    monkeypatch.setitem(globals_, "_load_materializer", lambda _sha256: {})
    monkeypatch.setitem(globals_, "resolve_rom_path", lambda _path: rom_path)
    monkeypatch.setitem(
        globals_,
        "verify_rom_bytes",
        lambda *_args, **_kwargs: SimpleNamespace(
            sha256=globals_["POKEMON_RED_US_REV_0"].sha256
        ),
    )
    monkeypatch.setitem(
        globals_,
        "build_runtime_identity",
        lambda: SimpleNamespace(sha256=state["runtime"]),
    )
    monkeypatch.setitem(globals_, "require_pyboy_import_origins", lambda _identity: None)
    monkeypatch.setitem(
        globals_,
        "StrategicScenarioRouteWorld",
        SimpleNamespace(from_rom=lambda _rom: object()),
    )
    monkeypatch.setitem(
        globals_,
        "derive_red_living_dex_provider_corridors",
        lambda _world: object(),
    )
    monkeypatch.setitem(
        globals_,
        "rom_adjacent_artifacts",
        lambda _rom: state["adjacent"],
    )
    monkeypatch.setitem(globals_, "open_private_root", lambda *_args, **_kwargs: _Store())
    monkeypatch.setitem(
        globals_,
        "open_fixed_account_claim_registry",
        lambda: tmp_path / "claims",
    )
    monkeypatch.setitem(
        globals_,
        "issue_red_living_dex_fresh_episode_process_authority",
        lambda: object(),
    )
    monkeypatch.setitem(globals_, "execute_red_living_dex_powered_supply_episode", execute)
    args = SimpleNamespace(
        speed=None,
        watch=False,
        plan=plan_path,
        expected_plan_sha256=hashlib.sha256(plan_payload).hexdigest(),
        assignment_id=plan.assignments[0].assignment_id,
        expected_source_commit=plan.source_commit,
        expected_source_bundle_sha256=plan.source_bundle_sha256,
        expected_generator_execution_sha256=plan.generator_execution_sha256,
        rom=rom_path,
        private_root=tmp_path / "private",
    )

    assert SCRIPT["_run_powered"](args) == {"status": "captured"}
    assert len(callback_box) == 1
    post_close_verify = callback_box[0]
    assert callable(post_close_verify)
    post_close_verify()

    for key, changed in (
        ("source_commit", "c" * 40),
        ("source_bundle", _digest("changed-source-bundle")),
        ("generator", _digest("changed-generator")),
        ("runner", _digest("changed-runner")),
        ("conditioner", _digest("changed-conditioner")),
        ("runtime", _digest("changed-runtime")),
        ("adjacent", ((True, _digest("sidecar")),) * 3),
    ):
        original = state[key]
        state[key] = changed
        with pytest.raises(
            SCRIPT["FreshEpisodeGeneratorError"],
            match="post_close_authentication",
        ):
            post_close_verify()
        state[key] = original

    plan_path.write_bytes(plan_payload + b" ")
    with pytest.raises(
        SCRIPT["FreshEpisodeGeneratorError"],
        match="post_close_authentication",
    ):
        post_close_verify()
    plan_path.write_bytes(plan_payload)

    capacity_payload = capacity_path.read_bytes()
    capacity_path.write_bytes(capacity_payload + b" ")
    with pytest.raises(
        SCRIPT["FreshEpisodeGeneratorError"],
        match="post_close_authentication",
    ):
        post_close_verify()
    capacity_path.write_bytes(capacity_payload)

    state["execute_error"] = True
    with pytest.raises(
        SCRIPT["FreshEpisodeGeneratorError"],
        match="fresh_episode_preclaim",
    ) as preclaim:
        SCRIPT["_run_powered"](args)
    assert preclaim.value.failure_receipt is None

    registry = tmp_path / "claims"
    registry.mkdir()
    marker = registry / (
        f"fresh-episode-assignment-{plan.assignments[0].assignment_id}.json"
    )
    marker.write_bytes(b'{"schema":"malformed"}\n')
    with pytest.raises(
        SCRIPT["FreshEpisodeGeneratorError"],
        match="fresh_episode_disposition_authentication",
    ) as uncertain:
        SCRIPT["_run_powered"](args)
    assert uncertain.value.failure_receipt is None

    marker.write_bytes(
        json.dumps(
            {
                "assignment_id": plan.assignments[0].assignment_id,
                "execution_identity_sha256": _digest("foreign-execution"),
                "plan_sha256": plan.plan_sha256,
                "runner_sha256": plan.generator_runner_sha256,
                "runtime_identity_sha256": plan.runtime_identity_sha256,
                "schema": RED_LIVING_DEX_POWERED_SUPPLY_ASSIGNMENT_CLAIM_SCHEMA,
                "source_commit": plan.source_commit,
            },
            allow_nan=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("ascii")
        + b"\n"
    )
    marker.chmod(0o600)
    expected_execution = (
        compose_red_living_dex_powered_supply_runtime_execution_sha256(
            assignment_id=plan.assignments[0].assignment_id,
            plan_sha256=plan.plan_sha256,
            source_commit=plan.source_commit,
            generator_execution_sha256=plan.generator_execution_sha256,
            generator_runner_sha256=plan.generator_runner_sha256,
            runtime_identity_sha256=plan.runtime_identity_sha256,
        )
    )
    assert expected_execution != _digest("foreign-execution")
    with pytest.raises(
        SCRIPT["FreshEpisodeGeneratorError"],
        match="fresh_episode_disposition_authentication",
    ) as foreign:
        SCRIPT["_run_powered"](args)
    assert foreign.value.failure_receipt is None

    valid_claim = {
        "assignment_id": plan.assignments[0].assignment_id,
        "execution_identity_sha256": expected_execution,
        "plan_sha256": plan.plan_sha256,
        "runner_sha256": plan.generator_runner_sha256,
        "runtime_identity_sha256": plan.runtime_identity_sha256,
        "schema": RED_LIVING_DEX_POWERED_SUPPLY_ASSIGNMENT_CLAIM_SCHEMA,
        "source_commit": plan.source_commit,
    }
    marker.write_bytes(
        json.dumps(
            valid_claim,
            allow_nan=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("ascii")
        + b"\n"
    )
    marker.chmod(0o600)
    with pytest.raises(SCRIPT["FreshEpisodeGeneratorError"]) as claimed:
        SCRIPT["_run_powered"](args)
    claimed_receipt = claimed.value.failure_receipt
    assert isinstance(claimed_receipt, RedLivingDexPoweredSupplyFailure)
    assert claimed_receipt.assignment_claim_sha256 is not None

    marker.unlink()
    state["episode_status"] = "failed"
    with pytest.raises(SCRIPT["FreshEpisodeGeneratorError"]) as namespace_only:
        SCRIPT["_run_powered"](args)
    namespace_receipt = namespace_only.value.failure_receipt
    assert isinstance(namespace_receipt, RedLivingDexPoweredSupplyFailure)
    assert namespace_receipt.assignment_claim_sha256 is None

    state["episode_status"] = "invalid"
    with pytest.raises(
        SCRIPT["FreshEpisodeGeneratorError"],
        match="fresh_episode_disposition_authentication",
    ) as invalid:
        SCRIPT["_run_powered"](args)
    assert invalid.value.failure_receipt is None


def test_legacy_run_remains_compatible_with_a_v1_plan(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source_bundle = _digest("legacy-source")
    runner_sha256 = _digest("legacy-runner")
    conditioner_sha256 = _digest("legacy-conditioner")
    generator_execution = (
        compose_red_living_dex_fresh_episode_generator_execution_sha256(
            source_bundle_sha256=source_bundle,
            generator_runner_sha256=runner_sha256,
            conditioner_runner_sha256=conditioner_sha256,
        )
    )
    capacity_path = tmp_path / "legacy-capacity.json"
    capacity_path.write_bytes(b'{"status":"legacy-capacity"}\n')
    plan = build_red_living_dex_fresh_episode_plan(
        source_commit="a" * 40,
        source_bundle_sha256=source_bundle,
        teacher_execution_sha256=(
            compose_red_living_dex_fresh_episode_teacher_execution_sha256(
                source_bundle_sha256=source_bundle,
                generator_execution_sha256=generator_execution,
            )
        ),
        generator_execution_sha256=generator_execution,
        capacity_evidence_sha256=hashlib.sha256(capacity_path.read_bytes()).hexdigest(),
    )
    plan_path = tmp_path / "legacy-plan.json"
    plan_payload = encode_red_living_dex_fresh_episode_plan(plan)
    plan_path.write_bytes(plan_payload)
    rom_path = tmp_path / "red.gb"
    rom_path.write_bytes(b"authenticated-rom-placeholder")

    def execute(*_args: object, **kwargs: object) -> SimpleNamespace:
        callback = kwargs["post_close_verify"]
        assert callable(callback)
        callback()
        return SimpleNamespace(public_dict=lambda: {"status": "legacy-v1-ok"})

    globals_ = SCRIPT["_run"].__globals__
    monkeypatch.setitem(globals_, "CAPACITY_EVIDENCE_PATH", capacity_path)
    monkeypatch.setitem(
        globals_,
        "detect_source_identity",
        lambda *_args, **_kwargs: SimpleNamespace(git_commit=plan.source_commit),
    )
    monkeypatch.setitem(globals_, "require_clean_source", lambda _source: None)
    monkeypatch.setitem(
        globals_,
        "require_published_source",
        lambda _root, _source: None,
    )
    monkeypatch.setitem(
        globals_,
        "working_source_bundle_sha256",
        lambda _root: plan.source_bundle_sha256,
    )
    monkeypatch.setitem(
        globals_,
        "_generator_execution_binding",
        lambda _source: (
            plan.generator_execution_sha256,
            runner_sha256,
            conditioner_sha256,
        ),
    )
    monkeypatch.setitem(globals_, "_load_materializer", lambda _sha256: {})
    monkeypatch.setitem(globals_, "resolve_rom_path", lambda _path: rom_path)
    monkeypatch.setitem(
        globals_,
        "verify_rom_bytes",
        lambda *_args, **_kwargs: SimpleNamespace(
            sha256=globals_["POKEMON_RED_US_REV_0"].sha256
        ),
    )
    monkeypatch.setitem(
        globals_,
        "build_runtime_identity",
        lambda: SimpleNamespace(sha256=_digest("legacy-runtime")),
    )
    monkeypatch.setitem(globals_, "require_pyboy_import_origins", lambda _identity: None)
    monkeypatch.setitem(
        globals_,
        "StrategicScenarioRouteWorld",
        SimpleNamespace(from_rom=lambda _rom: object()),
    )
    monkeypatch.setitem(
        globals_,
        "derive_red_living_dex_provider_corridors",
        lambda _world: object(),
    )
    monkeypatch.setitem(
        globals_,
        "rom_adjacent_artifacts",
        lambda _rom: ((False, None),) * 3,
    )
    monkeypatch.setitem(globals_, "open_private_root", lambda *_args, **_kwargs: object())
    monkeypatch.setitem(
        globals_,
        "open_fixed_account_claim_registry",
        lambda: tmp_path / "claims",
    )
    monkeypatch.setitem(
        globals_,
        "issue_red_living_dex_fresh_episode_process_authority",
        lambda: object(),
    )
    monkeypatch.setitem(globals_, "execute_red_living_dex_fresh_episode", execute)
    args = SimpleNamespace(
        speed=None,
        watch=False,
        plan=plan_path,
        expected_plan_sha256=hashlib.sha256(plan_payload).hexdigest(),
        assignment_id=plan.assignments[0].assignment_id,
        expected_source_commit=plan.source_commit,
        expected_source_bundle_sha256=plan.source_bundle_sha256,
        expected_generator_execution_sha256=plan.generator_execution_sha256,
        rom=rom_path,
        private_root=tmp_path / "private",
    )

    assert SCRIPT["_run"](args) == {"status": "legacy-v1-ok"}


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


@pytest.mark.parametrize(
    ("assignment_index", "expected_mode", "expected_box_count"),
    ((0, "acquisition-ready", None), (7, "storage-ready", 19)),
)
def test_powered_conditioning_uses_only_the_frozen_profile(
    assignment_index: int,
    expected_mode: str,
    expected_box_count: int | None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assignment = _powered_plan().assignments[assignment_index]
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

    globals_ = SCRIPT["_apply_powered_target_conditioning"].__globals__
    monkeypatch.setitem(globals_, "COMPLETION_QUEST", _Quest())
    monkeypatch.setitem(globals_, "LivePokemonRedObserver", _Observer)
    monkeypatch.setitem(globals_, "PokemonRedStateReader", _Reader)
    monkeypatch.setitem(globals_, "PokemonRedGoalStateAdapter", lambda *_args: object())
    monkeypatch.setitem(globals_, "FrameSafeExecutor", lambda *_args: object())
    monkeypatch.setitem(globals_, "CountingExecutor", lambda value: value)
    monkeypatch.setitem(globals_, "_MATERIALIZER", {"_apply_mode": apply_mode})

    SCRIPT["_apply_powered_target_conditioning"](
        _Emulator(),
        assignment,
        SimpleNamespace(verified_objective_ids=("power_on", "begin_adventure")),
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


def test_main_routes_powered_supply_to_v2_only(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    calls: list[str] = []
    globals_ = SCRIPT["main"].__globals__
    parsed = SimpleNamespace(powered_supply=True)
    monkeypatch.setitem(
        globals_,
        "_parser",
        lambda: SimpleNamespace(parse_args=lambda _argv: parsed),
    )
    monkeypatch.setitem(
        globals_,
        "_run",
        lambda _args: (_ for _ in ()).throw(AssertionError("V1 must not run")),
    )
    monkeypatch.setitem(
        globals_,
        "_run_powered",
        lambda _args: calls.append("powered") or {"status": "v2-ok"},
    )

    assert SCRIPT["main"]([]) == 0
    assert calls == ["powered"]
    assert json.loads(capsys.readouterr().out)["status"] == "v2-ok"


def test_powered_preclaim_failure_is_v2_but_not_a_consumed_disposition(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    globals_ = SCRIPT["main"].__globals__
    monkeypatch.setitem(
        globals_,
        "_run_powered",
        lambda _args: (_ for _ in ()).throw(
            SCRIPT["FreshEpisodeGeneratorError"]("plan_authentication")
        ),
    )
    monkeypatch.setitem(
        globals_,
        "_parser",
        lambda: SimpleNamespace(
            parse_args=lambda _argv: SimpleNamespace(powered_supply=True)
        ),
    )

    assert SCRIPT["main"]([]) == 1
    failure = json.loads(capsys.readouterr().out)
    assert failure["schema"] == (
        "pokemon.red.living-dex-powered-lineage-supply-command-failure.v1"
    )
    assert failure["stage"] == "plan_authentication"
    assert failure["controller_actions"] == 0
    assert "attempt_consumed" not in failure
    assert "retry_allowed" not in failure


def test_powered_consumed_failure_emits_role_bound_no_retry_disposition(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    plan = _powered_plan()
    assignment = plan.assignments[-1]
    terminal = RedLivingDexPoweredSupplyFailure(
        assignment_id=assignment.assignment_id,
        plan_sha256=plan.plan_sha256,
        role=assignment.role,
        partition=assignment.partition,
        source_bundle_sha256=assignment.source_bundle_sha256,
        teacher_execution_sha256=assignment.teacher_execution_sha256,
        generator_execution_sha256=assignment.generator_execution_sha256,
        assignment_claim_sha256=_digest("powered-claim"),
        failure_stage="fresh_episode_execution",
        effects_known=True,
        controller_actions=71,
        emulator_frames=9_001,
    )
    globals_ = SCRIPT["main"].__globals__
    monkeypatch.setitem(
        globals_,
        "_run_powered",
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
        lambda: SimpleNamespace(
            parse_args=lambda _argv: SimpleNamespace(powered_supply=True)
        ),
    )

    assert SCRIPT["main"]([]) == 1
    failure = json.loads(capsys.readouterr().out)
    assert failure["assignment_id"] == assignment.assignment_id
    assert failure["role"] == "contingency"
    assert failure["partition"] == "development"
    assert failure["attempt_consumed"] is True
    assert failure["retry_allowed"] is False
    assert failure["terminal_root_generated"] is False
