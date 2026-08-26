# ruff: noqa: E402 -- standalone runner is loaded after its script-local imports.

from __future__ import annotations

import argparse
import hashlib
import json
import runpy
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
from test_red_living_dex_option_adapter import _facts, _snapshot
from test_red_living_dex_option_inventory import (
    _bindings,
    _capture,
    _inventory_scenarios,
    _profile,
)

from pokemon_red_completion.private_artifacts import (
    PrivateArtifactError,
    initialize_private_root,
)
from pokemon_red_completion.red_living_dex_option_inventory import (
    RedLivingDexInventoryObserverBinding,
    freeze_red_living_dex_action_free_inventory,
)
from pokemon_red_completion.red_living_dex_option_materializer import (
    red_living_dex_verified_capture_scenario_identity,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_ROOT = PROJECT_ROOT / "scripts"
while str(SCRIPTS_ROOT) in sys.path:
    sys.path.remove(str(SCRIPTS_ROOT))
sys.path.insert(0, str(SCRIPTS_ROOT))

SCRIPT_PATH = PROJECT_ROOT / "scripts/freeze_red_living_dex_authentic_inventory.py"
SCRIPT = runpy.run_path(
    str(SCRIPT_PATH),
    run_name="freeze_red_living_dex_authentic_inventory_test",
)


def _sha(value: str) -> str:
    return hashlib.sha256(value.encode("ascii")).hexdigest()


def _args() -> list[str]:
    return [
        "--expected-source-commit",
        "a" * 40,
        "--expected-source-bundle-sha256",
        _sha("source"),
        "--registry-source-commit",
        "b" * 40,
        "--expected-registry-sha256",
        _sha("registry"),
        "--context-catalog",
        "/protected/catalog.json",
        "--expected-context-catalog-sha256",
        _sha("catalog"),
        "--context-plan",
        "/protected/plan.json",
        "--expected-context-plan-sha256",
        _sha("plan"),
        "--private-root",
        "/protected/artifacts",
        "--rom",
        "/protected/red.gb",
    ]


def _projected() -> object:
    inventory, plan = freeze_red_living_dex_action_free_inventory(
        _inventory_scenarios()
    )
    rows = {
        scenario.scenario_identity_sha256: {
            "attestation": {"schema": "synthetic-private-attestation-v1"},
            "materialization_identity": scenario.private_identity_dict(),
            "partition": scenario.partition,
        }
        for scenario in plan.scenarios
    }
    return SCRIPT["_ProjectedInventory"](
        inventory,
        plan,
        rows,
        81,
        64,
        {"consumed_physical_root": 17},
        0,
    )


def test_parser_requires_every_authenticated_input_and_has_no_execution_flags() -> None:
    parsed = SCRIPT["_parser"]().parse_args(_args())

    assert parsed.expected_source_commit == "a" * 40
    assert parsed.registry_source_commit == "b" * 40
    assert parsed.private_root == Path("/protected/artifacts")
    assert not hasattr(parsed, "watch")
    assert not hasattr(parsed, "speed")
    with pytest.raises(SCRIPT["RedLivingDexAuthenticInventoryError"]):
        SCRIPT["_parser"]().parse_args(_args()[:-4])


def test_source_failure_stops_before_private_inputs_and_is_path_free(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    private_calls = 0

    def private(*_args: object, **_kwargs: object) -> object:
        nonlocal private_calls
        private_calls += 1
        raise AssertionError("private inputs opened")

    monkeypatch.setitem(
        SCRIPT["main"].__globals__,
        "_authenticate_source",
        lambda _args: (_ for _ in ()).throw(
            SCRIPT["RedLivingDexAuthenticInventoryError"](
                "source_authentication"
            )
        ),
    )
    monkeypatch.setitem(SCRIPT["main"].__globals__, "_authenticate_inputs", private)

    assert SCRIPT["main"](_args()) == 1

    result = json.loads(capsys.readouterr().out)
    assert private_calls == 0
    assert result["failure_stage"] == "source_authentication"
    assert result["behavior_draws"] == 0
    assert result["controller_actions"] == 0
    assert result["root_claims"] == 0
    assert result["outcomes_observed"] == 0
    assert "/protected" not in json.dumps(result)


def test_runner_contains_no_selection_execution_or_learning_authority() -> None:
    source = SCRIPT_PATH.read_text(encoding="utf-8")

    for forbidden in (
        "issue_red_living_dex_behavior_commitment",
        "run_red_living_dex_materialization_plan",
        "score_red_living_dex",
        "CompletionFirstGoalTeacher",
        "write_root_claim",
        ".press(",
        ".tick(",
    ):
        assert forbidden not in source
    assert "_ForbiddenActionPort" in source
    assert "behavior_draws\": 0" in source


def test_unclaimed_materializer_status_matches_private_store(tmp_path: Path) -> None:
    repository = tmp_path / "repository"
    root = tmp_path / "private"
    repository.mkdir()
    root.mkdir()

    def device_id(path: Path) -> int:
        return 2 if path == root.resolve() else 1

    store = initialize_private_root(
        root,
        repository_root=repository,
        device_id=device_id,
        git_worktree_probe=lambda _path: False,
    )

    assert store.inspect_episode_state("redldx-unused-test-root").status == (
        SCRIPT["MATERIALIZER_UNCLAIMED_STATUS"]
    )
    attestation = SCRIPT["_checkpoint_attestation"](
        assignment=SimpleNamespace(assignment_id="assignment"),
        catalog_entry=SimpleNamespace(context_id="context"),
        capture=SimpleNamespace(
            capture_id="capture",
            envelope_sha256=_sha("envelope"),
            state_sha256=_sha("state"),
        ),
        profile=SimpleNamespace(profile_sha256=_sha("profile")),
        physical_root_sha256=_sha("root"),
        partition="train",
    )
    assert attestation["materializer_episode_status"] == "absent"


@pytest.mark.parametrize("status", ("invalid", "unknown", ""))
def test_invalid_materializer_namespace_fails_instead_of_being_excluded(
    status: str,
) -> None:
    store = SimpleNamespace(
        inspect_episode_state=lambda _episode_id: SimpleNamespace(status=status)
    )

    with pytest.raises(
        SCRIPT["RedLivingDexAuthenticInventoryError"],
        match="materializer_episode_authentication",
    ):
        SCRIPT["_materializer_episode_is_unclaimed"](store, "redldx-context")


@pytest.mark.parametrize(
    ("status", "expected"),
    (("absent", True), ("partial", False), ("complete", False), ("failed", False)),
)
def test_valid_materializer_namespace_states_are_classified(
    status: str,
    expected: bool,
) -> None:
    store = SimpleNamespace(
        inspect_episode_state=lambda _episode_id: SimpleNamespace(status=status)
    )

    assert SCRIPT["_materializer_episode_is_unclaimed"](store, "redldx-context") is expected


def test_inventory_admits_only_absent_materializer_episode(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    first_capture = _capture(700)
    second_capture = _capture(701)
    contexts = tuple(
        SimpleNamespace(
            assignment=SimpleNamespace(
                assignment_id=f"assignment-{index}",
                partition=partition,
                slot_id=capture.capture_id,
            ),
            catalog_entry=SimpleNamespace(context_id=f"context-{index}"),
            capture=capture,
            profile=_profile(capture.capture_id),
            root_available=True,
            root_consumption_sha256=f"{90_000 + index:064x}",
        )
        for index, (capture, partition) in enumerate(
            ((first_capture, "train"), (second_capture, "validation"))
        )
    )

    class FakeStore:
        def __init__(self) -> None:
            self.calls = 0

        def inspect_episode_state(self, _episode_id: str) -> object:
            self.calls += 1
            return SimpleNamespace(status="absent" if self.calls == 1 else "complete")

    class FakeEmulator:
        frame_count = 0
        pressed_buttons: tuple[object, ...] = ()

        def __enter__(self) -> FakeEmulator:
            return self

        def __exit__(self, *_args: object) -> None:
            return None

        def load_state_bytes(self, _state: bytes) -> None:
            return None

    observation = SimpleNamespace(
        party=SimpleNamespace(members=(SimpleNamespace(),)),
    )
    admitted: tuple[object, ...] = ()

    def runtime(*, profile: object, **_kwargs: object) -> object:
        return SimpleNamespace(
            adapter=SimpleNamespace(observe=lambda: observation),
            enumerator=lambda _actions: SimpleNamespace(
                enumerate=lambda _observation: _bindings(profile)
            ),
        )

    def before(capture: object, *_args: object, **_kwargs: object) -> object:
        return _snapshot(
            scenario=red_living_dex_verified_capture_scenario_identity(capture),
            actions=0,
            frames=0,
            resource_pool_units=(("red.resource.capture-items", 10),),
        )

    def freeze(scenarios: tuple[object, ...]) -> tuple[object, object]:
        nonlocal admitted
        admitted = scenarios
        return freeze_red_living_dex_action_free_inventory(_inventory_scenarios())

    globals_ = SCRIPT["_inventory"].__globals__
    monkeypatch.setitem(globals_, "build_runtime_identity", lambda: object())
    monkeypatch.setitem(globals_, "require_pyboy_import_origins", lambda _identity: None)
    monkeypatch.setitem(globals_, "open_private_root", lambda *_args, **_kwargs: FakeStore())
    monkeypatch.setitem(globals_, "PyBoyAdapter", lambda *_args, **_kwargs: FakeEmulator())
    monkeypatch.setitem(globals_, "PokemonRedStateReader", lambda _emulator: object())
    monkeypatch.setitem(globals_, "build_red_goal_context_runtime", runtime)
    monkeypatch.setitem(globals_, "_authenticate_historical_menu", lambda *_args: None)
    monkeypatch.setitem(globals_, "_before_snapshot", before)
    monkeypatch.setitem(globals_, "_context_facts", lambda *_args: _facts())
    monkeypatch.setitem(globals_, "_location_ref", lambda _observation: "red.start-map.1")
    monkeypatch.setitem(globals_, "freeze_red_living_dex_action_free_inventory", freeze)

    projected = SCRIPT["_inventory"](
        SimpleNamespace(private_root=Path("/protected/private")),
        rom_path=Path("/protected/red.gb"),
        rom_sha256=_sha("rom"),
        contexts=contexts,
        source_bundle=_sha("source"),
    )

    assert len(admitted) == 1
    assert isinstance(admitted[0].observe_after, RedLivingDexInventoryObserverBinding)
    assert projected.authenticated_contexts == 2
    assert projected.emulator_states_read == 1
    assert projected.excluded_counts == {"existing_materializer_claim": 1}
    assert projected.emulator_frames_advanced == 0


def test_private_plan_encoding_is_exact_and_keeps_every_effect_zero() -> None:
    projected = _projected()
    document, digest = SCRIPT["_private_plan_document"](
        source_commit="a" * 40,
        source_bundle=_sha("source"),
        rom_sha256=_sha("rom"),
        registry_sha256=_sha("registry"),
        catalog_sha256=_sha("catalog"),
        context_plan_sha256=_sha("context-plan"),
        projected=projected,
    )

    assert document["private_plan_sha256"] == digest
    assert document["status"] == (
        "frozen_before_claim_randomization_action_outcome_or_fit"
    )
    assert len(document["scenarios"]) == 12
    assert document["behavior_draws"] == 0
    assert document["controller_actions"] == 0
    assert document["root_claims"] == 0
    assert document["outcomes_observed"] == 0
    assert document["model_fits"] == 0
    assert "/protected" not in json.dumps(document)


def test_publication_is_idempotent_only_for_exact_private_plan(tmp_path: Path) -> None:
    repository = tmp_path / "repository"
    root = tmp_path / "private"
    repository.mkdir()
    root.mkdir()

    def device_id(path: Path) -> int:
        return 2 if path == root.resolve() else 1

    store = initialize_private_root(
        root,
        repository_root=repository,
        device_id=device_id,
        git_worktree_probe=lambda _path: False,
    )
    projected = _projected()
    document, digest = SCRIPT["_private_plan_document"](
        source_commit="a" * 40,
        source_bundle=_sha("source"),
        rom_sha256=_sha("rom"),
        registry_sha256=_sha("registry"),
        catalog_sha256=_sha("catalog"),
        context_plan_sha256=_sha("context-plan"),
        projected=projected,
    )
    args = argparse.Namespace(private_root=root)
    globals_ = SCRIPT["_publish"].__globals__
    original_open = globals_["open_private_root"]
    globals_["open_private_root"] = lambda *_args, **_kwargs: store
    try:
        first = SCRIPT["_publish"](
            args,
            document=document,
            private_plan_sha256=digest,
            projected=projected,
        )
        second = SCRIPT["_publish"](
            args,
            document=document,
            private_plan_sha256=digest,
            projected=projected,
        )
        assert first == second
        assert first["status"] == "authenticated_action_free_8_plus_4_plan_frozen"
        assert first["controller_actions"] == 0
        assert first["private_path_fields"] == 0
        changed = {**document, "status": "changed"}
        with pytest.raises(PrivateArtifactError, match="different content"):
            SCRIPT["_publish"](
                args,
                document=changed,
                private_plan_sha256=digest,
                projected=projected,
            )
    finally:
        globals_["open_private_root"] = original_open


def test_success_path_rechecks_rom_and_source_without_opening_gameplay(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    projected = _projected()
    source = _sha("source")
    rom = _sha("rom")
    document = {"schema": "private-plan-v1"}
    published = {
        "schema": SCRIPT["RESULT_SCHEMA"],
        "status": "authenticated_action_free_8_plus_4_plan_frozen",
    }
    globals_ = SCRIPT["main"].__globals__
    monkeypatch.setitem(globals_, "_authenticate_source", lambda _args: ("a" * 40, source))
    monkeypatch.setitem(
        globals_,
        "_authenticate_inputs",
        lambda *_args: (Path("/protected/red.gb"), rom, b"rom", (), _sha("catalog"), _sha("plan")),
    )
    monkeypatch.setitem(globals_, "_inventory", lambda *_args, **_kwargs: projected)
    monkeypatch.setitem(
        globals_,
        "_private_plan_document",
        lambda **_kwargs: (document, _sha("private-plan")),
    )
    monkeypatch.setitem(globals_, "_publish", lambda *_args, **_kwargs: published)
    monkeypatch.setitem(globals_, "verify_rom", lambda _path: SimpleNamespace(sha256=rom))
    monkeypatch.setitem(globals_, "POKEMON_RED_US_REV_0", SimpleNamespace(sha256=rom))
    monkeypatch.setitem(globals_, "working_source_bundle_sha256", lambda _path: source)

    assert SCRIPT["main"](_args()) == 0
    assert json.loads(capsys.readouterr().out) == published


def test_integrity_drift_stops_before_private_plan_publication(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    projected = _projected()
    source = _sha("source")
    rom = _sha("rom")
    publication_calls = 0

    def publish(*_args: object, **_kwargs: object) -> object:
        nonlocal publication_calls
        publication_calls += 1
        raise AssertionError("drifted plan was published")

    globals_ = SCRIPT["main"].__globals__
    monkeypatch.setitem(globals_, "_authenticate_source", lambda _args: ("a" * 40, source))
    monkeypatch.setitem(
        globals_,
        "_authenticate_inputs",
        lambda *_args: (
            Path("/protected/red.gb"),
            rom,
            b"rom",
            (),
            _sha("catalog"),
            _sha("plan"),
        ),
    )
    monkeypatch.setitem(globals_, "_inventory", lambda *_args, **_kwargs: projected)
    monkeypatch.setitem(
        globals_,
        "_private_plan_document",
        lambda **_kwargs: ({"schema": "private-plan-v1"}, _sha("private-plan")),
    )
    monkeypatch.setitem(globals_, "_publish", publish)
    monkeypatch.setitem(
        globals_,
        "verify_rom",
        lambda _path: SimpleNamespace(sha256=_sha("changed-rom")),
    )
    monkeypatch.setitem(globals_, "POKEMON_RED_US_REV_0", SimpleNamespace(sha256=rom))
    monkeypatch.setitem(globals_, "working_source_bundle_sha256", lambda _path: source)

    assert SCRIPT["main"](_args()) == 1

    result = json.loads(capsys.readouterr().out)
    assert publication_calls == 0
    assert result["failure_stage"] == "protected_input_integrity"
    assert result["root_claims"] == 0
