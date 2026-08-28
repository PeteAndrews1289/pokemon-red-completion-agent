# ruff: noqa: E402 -- standalone runner is loaded after its script-local imports.

from __future__ import annotations

import hashlib
import json
import runpy
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace

import pytest
from test_red_living_dex_option_inventory import _profile
from test_red_living_dex_provider_plan import _root, _roots
from test_red_living_dex_setup_identity import _runtime

from pokemon_red_completion.captured_progress import parse_captured_progress
from pokemon_red_completion.goal_manager_composition_qualification import (
    root_consumption_sha256,
)
from pokemon_red_completion.goal_manager_context_catalog import (
    parse_goal_manager_context_capture,
)
from pokemon_red_completion.living_dex_capture_curriculum import (
    LivingDexCapturePartition,
)
from pokemon_red_completion.private_artifacts import validate_private_record
from pokemon_red_completion.provenance import canonical_sha256

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_ROOT = PROJECT_ROOT / "scripts"
while str(SCRIPTS_ROOT) in sys.path:
    sys.path.remove(str(SCRIPTS_ROOT))
sys.path.insert(0, str(SCRIPTS_ROOT))

SCRIPT_PATH = PROJECT_ROOT / "scripts/freeze_red_living_dex_provider_plan.py"
SCRIPT = runpy.run_path(
    str(SCRIPT_PATH),
    run_name="freeze_red_living_dex_provider_plan_test",
)


def _sha(value: object) -> str:
    return canonical_sha256({"value": value})


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
        "/private/catalog.json",
        "--expected-context-catalog-sha256",
        _sha("catalog"),
        "--context-plan",
        "/private/plan.json",
        "--expected-context-plan-sha256",
        _sha("context-plan"),
        "--private-root",
        "/private/artifacts",
        "--rom",
        "/private/red.gb",
    ]


def _capture(index: int):
    state = f"provider-freezer-state-{index}".encode("ascii")
    envelope = {
        "checkpoint_id": f"provider-freezer-{index:02d}",
        "checkpoint_label": "Provider freezer root",
        "checkpoints_completed": 1,
        "checkpoints_total": 1,
        "schema": "pokemon-private-captured-progress-v1",
        "state_sha256": hashlib.sha256(state).hexdigest(),
        "verified_objective_ids": ["power_on"],
    }
    envelope_bytes = (
        json.dumps(envelope, ensure_ascii=True, sort_keys=True).encode("ascii")
        + b"\n"
    )
    return parse_goal_manager_context_capture(state, envelope_bytes)


def _private_context(index: int, partition: str = "train") -> object:
    capture = _capture(index)
    return SimpleNamespace(
        assignment=SimpleNamespace(
            partition=partition,
            root_lineage_id=f"provider-freezer-lineage-{index:02d}",
        ),
        capture=capture,
        profile=_profile(capture.capture_id),
        root_consumption_sha256=root_consumption_sha256(
            state_sha256=capture.state_sha256,
            envelope_sha256=capture.envelope_sha256,
        ),
        root_available=True,
    )


class _Emulator:
    instances: list[_Emulator] = []
    frame_drift = 0

    def __init__(self, *_args: object, **_kwargs: object) -> None:
        self.frame_count = 0
        self.pressed_buttons: frozenset[str] = frozenset()
        self.loaded: bytes | None = None
        self.instances.append(self)

    def __enter__(self):
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def load_state_bytes(self, payload: bytes) -> None:
        self.loaded = payload
        self.frame_count += self.frame_drift


def test_parser_exposes_only_authenticated_inventory_inputs() -> None:
    parsed = SCRIPT["_parser"]().parse_args(_args())

    assert parsed.expected_source_commit == "a" * 40
    assert parsed.private_root == Path("/private/artifacts")
    assert parsed.supplemental_state == []
    assert parsed.expected_supplemental_physical_root_sha256 == []
    for field in ("watch", "speed", "retry", "seed", "fit", "execute"):
        assert not hasattr(parsed, field)


def test_supplemental_root_is_hash_bound_and_retains_no_path(
    tmp_path: Path,
) -> None:
    expected = _root(0).root
    state_path = tmp_path / "supplemental.state"
    state_path.write_bytes(expected.state_bytes)
    state_path.with_suffix(".state.json").write_bytes(expected.envelope_bytes)

    supplements = SCRIPT["_authenticate_supplemental_roots"](
        (state_path,),
        (expected.physical_root_sha256,),
    )

    assert len(supplements) == 1
    assert supplements[0].root.state_bytes == expected.state_bytes
    assert supplements[0].root.envelope_bytes == expected.envelope_bytes
    assert supplements[0].root.physical_root_sha256 == expected.physical_root_sha256
    assert "path" not in supplements[0].__dataclass_fields__
    with pytest.raises(
        SCRIPT["ProviderPlanFreezeError"],
        match="supplemental_root_authentication",
    ):
        SCRIPT["_authenticate_supplemental_roots"](
            (state_path,),
            (_sha("another-root"),),
        )


def test_runner_has_no_action_claim_teacher_outcome_or_fit_authority() -> None:
    source = SCRIPT_PATH.read_text(encoding="utf-8")

    for forbidden in (
        "CountingExecutor",
        "write_root_claim",
        "CompletionFirstGoalTeacher",
        "issue_red_living_dex_behavior_commitment",
        "run_red_living_dex_setup_recipe_campaign",
        "fit_red_living_dex",
        ".press(",
        ".tick(",
        ".execute(",
    ):
        assert forbidden not in source


def test_partition_join_uses_the_immutable_ten_plus_five_schedule() -> None:
    rows = SCRIPT["build_partitioned_root_rows"](_roots())

    counts = {partition: 0 for partition in LivingDexCapturePartition}
    for row in rows:
        counts[row.partition] += 1
    assert counts == {
        LivingDexCapturePartition.TRAIN: 10,
        LivingDexCapturePartition.DEVELOPMENT: 5,
    }


def test_candidate_observation_isolates_roots_and_remains_zero_effect(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _Emulator.instances = []
    _Emulator.frame_drift = 0
    globals_ = SCRIPT["_observe_candidates"].__globals__
    expected = _root(0)
    monkeypatch.setitem(globals_, "PyBoyAdapter", _Emulator)
    monkeypatch.setitem(globals_, "require_pyboy_import_origins", lambda _runtime: None)
    monkeypatch.setitem(globals_, "root_claim_is_available", lambda *_args: True)
    monkeypatch.setitem(globals_, "PokemonRedStateReader", lambda _emulator: object())
    monkeypatch.setitem(
        globals_,
        "build_red_goal_context_runtime",
        lambda **_kwargs: SimpleNamespace(
            adapter=SimpleNamespace(
                observe=lambda: SimpleNamespace(
                    input_ready=True,
                    raw=SimpleNamespace(battle_state=0),
                    situation=object(),
                )
            )
        ),
    )
    monkeypatch.setitem(
        globals_,
        "Gen1TrainerSightProjector",
        lambda *_args: object(),
    )
    monkeypatch.setitem(
        globals_,
        "Gen1TraversalObserver",
        lambda *_args, **_kwargs: SimpleNamespace(observe=lambda: expected.traversal),
    )
    monkeypatch.setitem(
        globals_,
        "observe_red_living_dex_provider_root_facts",
        lambda _observation: expected.facts,
    )
    monkeypatch.setitem(
        globals_,
        "living_dex_option_context_from_goal_situation",
        lambda _situation: expected.option_context,
    )
    state = SCRIPT["_DiagnosticState"]()
    contexts = (_private_context(1, "train"), _private_context(2, "validation"))

    candidates = SCRIPT["_observe_candidates"](
        contexts,
        rom_path=Path("/private/red.gb"),
        rom_bytes=b"rom",
        runtime=_runtime(),
        claim_registry=Path("/private/claims"),
        state=state,
    )

    assert len(candidates) == 2
    assert len(_Emulator.instances) == 2
    assert _Emulator.instances[0].loaded != _Emulator.instances[1].loaded
    assert state.states_restored == 2
    assert state.observations_completed == 2
    assert state.eligible_root_pool == 2
    assert state.source_train_roots == 1
    assert state.source_validation_roots == 1
    assert state.controller_actions == 0
    assert state.emulator_frames == 0
    assert all(item.prospective_independence_authenticated for item in candidates)


def test_candidate_observation_fails_closed_on_frame_drift(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _Emulator.instances = []
    _Emulator.frame_drift = 1
    globals_ = SCRIPT["_observe_candidates"].__globals__
    expected = _root(0)
    monkeypatch.setitem(globals_, "PyBoyAdapter", _Emulator)
    monkeypatch.setitem(globals_, "require_pyboy_import_origins", lambda _runtime: None)
    monkeypatch.setitem(globals_, "root_claim_is_available", lambda *_args: True)
    monkeypatch.setitem(globals_, "PokemonRedStateReader", lambda _emulator: object())
    monkeypatch.setitem(
        globals_,
        "build_red_goal_context_runtime",
        lambda **_kwargs: SimpleNamespace(
            adapter=SimpleNamespace(
                observe=lambda: SimpleNamespace(
                    input_ready=True,
                    raw=SimpleNamespace(battle_state=0),
                    situation=object(),
                )
            )
        ),
    )
    monkeypatch.setitem(globals_, "Gen1TrainerSightProjector", lambda *_args: object())
    monkeypatch.setitem(
        globals_,
        "Gen1TraversalObserver",
        lambda *_args, **_kwargs: SimpleNamespace(observe=lambda: expected.traversal),
    )
    monkeypatch.setitem(
        globals_,
        "observe_red_living_dex_provider_root_facts",
        lambda _observation: expected.facts,
    )
    monkeypatch.setitem(
        globals_,
        "living_dex_option_context_from_goal_situation",
        lambda _situation: expected.option_context,
    )
    state = SCRIPT["_DiagnosticState"]()

    with pytest.raises(SCRIPT["ProviderPlanFreezeError"], match="zero_effect"):
        SCRIPT["_observe_candidates"](
            (_private_context(1),),
            rom_path=Path("/private/red.gb"),
            rom_bytes=b"rom",
            runtime=_runtime(),
            claim_registry=Path("/private/claims"),
            state=state,
        )
    assert state.emulator_frames == 1
    assert state.controller_actions == 0
    _Emulator.frame_drift = 0


def test_candidate_observation_excludes_non_overworld_control_without_effects(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _Emulator.instances = []
    _Emulator.frame_drift = 0
    globals_ = SCRIPT["_observe_candidates"].__globals__
    expected = _root(0)
    interrupted = SimpleNamespace(
        **{
            name: getattr(expected.traversal, name)
            for name in expected.traversal.__dataclass_fields__
        }
    )
    interrupted.ready = False
    interrupted.interruption = "wild_battle"
    raw = SimpleNamespace(battle_state=1)
    goal_observation = SimpleNamespace(input_ready=False, raw=raw)
    monkeypatch.setitem(globals_, "PyBoyAdapter", _Emulator)
    monkeypatch.setitem(globals_, "require_pyboy_import_origins", lambda _runtime: None)
    monkeypatch.setitem(globals_, "root_claim_is_available", lambda *_args: True)
    monkeypatch.setitem(globals_, "PokemonRedStateReader", lambda _emulator: object())
    monkeypatch.setitem(
        globals_,
        "build_red_goal_context_runtime",
        lambda **_kwargs: SimpleNamespace(
            adapter=SimpleNamespace(observe=lambda: goal_observation)
        ),
    )
    monkeypatch.setitem(globals_, "Gen1TrainerSightProjector", lambda *_args: object())
    monkeypatch.setitem(
        globals_,
        "Gen1TraversalObserver",
        lambda *_args, **_kwargs: SimpleNamespace(observe=lambda: interrupted),
    )
    state = SCRIPT["_DiagnosticState"]()

    candidates = SCRIPT["_observe_candidates"](
        (_private_context(1),),
        rom_path=Path("/private/red.gb"),
        rom_bytes=b"rom",
        runtime=_runtime(),
        claim_registry=Path("/private/claims"),
        state=state,
    )

    assert candidates == ()
    assert state.ineligible_control_contexts == 1
    assert state.emulator_frames == 0
    assert state.controller_actions == 0


def test_supplemental_observation_uses_the_captured_progress_adapter(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _Emulator.instances = []
    _Emulator.frame_drift = 0
    globals_ = SCRIPT["_observe_supplemental_candidates"].__globals__
    expected = _root(0)
    envelope = parse_captured_progress(
        expected.root.envelope_bytes,
        state_bytes=expected.root.state_bytes,
    )
    supplement = SCRIPT["_SupplementalRoot"](
        root=expected.root,
        envelope=envelope,
    )
    goal_observation = SimpleNamespace(
        input_ready=True,
        raw=SimpleNamespace(battle_state=0),
        situation=object(),
    )
    monkeypatch.setitem(globals_, "PyBoyAdapter", _Emulator)
    monkeypatch.setitem(globals_, "require_pyboy_import_origins", lambda _runtime: None)
    monkeypatch.setitem(globals_, "root_claim_is_available", lambda *_args: True)
    monkeypatch.setitem(globals_, "PokemonRedStateReader", lambda _emulator: object())
    monkeypatch.setitem(
        globals_,
        "CapturedPokemonRedObserver",
        lambda *_args: object(),
    )
    monkeypatch.setitem(
        globals_,
        "PokemonRedGoalStateAdapter",
        lambda *_args: SimpleNamespace(observe=lambda: goal_observation),
    )
    monkeypatch.setitem(globals_, "Gen1TrainerSightProjector", lambda *_args: object())
    monkeypatch.setitem(
        globals_,
        "Gen1TraversalObserver",
        lambda *_args, **_kwargs: SimpleNamespace(observe=lambda: expected.traversal),
    )
    monkeypatch.setitem(
        globals_,
        "observe_red_living_dex_provider_root_facts",
        lambda _observation: expected.facts,
    )
    monkeypatch.setitem(
        globals_,
        "living_dex_option_context_from_goal_situation",
        lambda _situation: expected.option_context,
    )
    state = SCRIPT["_DiagnosticState"]()

    candidates = SCRIPT["_observe_supplemental_candidates"](
        (supplement,),
        rom_path=Path("/private/red.gb"),
        rom_bytes=b"rom",
        runtime=_runtime(),
        claim_registry=Path("/private/claims"),
        state=state,
    )

    assert len(candidates) == 1
    assert candidates[0].root == expected.root
    assert candidates[0].traversal == expected.traversal
    assert candidates[0].facts == expected.facts
    assert candidates[0].option_context == expected.option_context
    assert candidates[0].independence_lineage_sha256 is not None
    assert not candidates[0].prospective_independence_authenticated
    assert state.eligible_supplemental_roots == 1
    assert state.eligible_root_pool == 1
    assert state.controller_actions == 0
    assert state.emulator_frames == 0


def test_main_holds_the_shared_claim_lease_through_publication(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    globals_ = SCRIPT["main"].__globals__
    events: list[str] = []
    roots = _roots()
    runtime = _runtime()
    identity = SimpleNamespace(identity_sha256=_sha("identity"))
    frozen = SimpleNamespace(
        plan=SimpleNamespace(execution_identity=identity),
    )

    @contextmanager
    def lease(_registry: Path, *, exclusive: bool) -> Iterator[None]:
        assert exclusive is False
        events.append("lease-enter")
        try:
            yield
        finally:
            events.append("lease-exit")

    monkeypatch.setitem(
        globals_,
        "_authenticate_source",
        lambda _args: ("a" * 40, _sha("source")),
    )
    monkeypatch.setitem(
        globals_,
        "_authenticate_inputs",
        lambda *_args: (
            Path("/private/red.gb"),
            "1" * 64,
            b"rom",
            tuple(range(15)),
            _sha("catalog"),
            _sha("context-plan"),
        ),
    )
    monkeypatch.setitem(globals_, "open_private_root", lambda *_args, **_kwargs: object())
    monkeypatch.setitem(globals_, "build_runtime_identity", lambda: runtime)
    monkeypatch.setitem(globals_, "require_pyboy_import_origins", lambda _runtime: None)
    monkeypatch.setitem(
        globals_,
        "load_strategic_navigation_scenario_registry",
        lambda _root: SimpleNamespace(registry_sha256=_sha("routes")),
    )
    monkeypatch.setitem(
        globals_,
        "StrategicScenarioRouteWorld",
        SimpleNamespace(from_rom=lambda _rom: object()),
    )
    monkeypatch.setitem(globals_, "derive_red_living_dex_provider_corridors", lambda _world: ())
    monkeypatch.setitem(
        globals_,
        "compose_red_living_dex_setup_execution_identity",
        lambda **_kwargs: identity,
    )
    monkeypatch.setitem(globals_, "open_fixed_account_claim_registry", lambda: Path("claims"))
    monkeypatch.setitem(globals_, "fixed_account_claim_registry_lease", lease)
    monkeypatch.setitem(
        globals_,
        "_observe_candidates",
        lambda *_args, **_kwargs: roots,
    )
    monkeypatch.setitem(
        globals_,
        "select_red_living_dex_provider_roots",
        lambda *_args, **_kwargs: roots,
    )
    monkeypatch.setitem(
        globals_,
        "freeze_red_living_dex_provider_plan",
        lambda *_args, **_kwargs: frozen,
    )
    monkeypatch.setitem(globals_, "_require_integrity", lambda *_args, **_kwargs: None)
    monkeypatch.setitem(
        globals_,
        "_private_plan_document",
        lambda **_kwargs: ({"schema": "synthetic"}, _sha("private-plan")),
    )

    def publish(*_args: object, **_kwargs: object) -> dict[str, object]:
        events.append("publish")
        return {"schema": "synthetic", "status": "frozen"}

    monkeypatch.setitem(globals_, "_publish", publish)

    assert SCRIPT["main"](_args()) == 0
    assert events == ["lease-enter", "publish", "lease-exit"]
    assert json.loads(capsys.readouterr().out)["status"] == "frozen"


def test_main_failure_receipt_is_sanitized_and_does_not_publish(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    globals_ = SCRIPT["main"].__globals__
    published = False

    def fail(_args: object) -> tuple[str, str]:
        raise RuntimeError("/private/secret/catalog.json")

    def publish(*_args: object, **_kwargs: object) -> dict[str, object]:
        nonlocal published
        published = True
        return {}

    monkeypatch.setitem(globals_, "_authenticate_source", fail)
    monkeypatch.setitem(globals_, "_publish", publish)

    assert SCRIPT["main"](_args()) == 1
    receipt = json.loads(capsys.readouterr().out)
    assert receipt["status"] == "failed_closed"
    assert receipt["stage"] == "source_authentication"
    assert "/private" not in json.dumps(receipt)
    assert receipt["controller_actions"] == 0
    assert receipt["root_claims"] == 0
    assert not published


def test_private_document_is_path_free_and_binds_plan_and_runtime() -> None:
    identity = SimpleNamespace(
        private_dict=lambda: {"source_commit": "a" * 40},
        identity_sha256=_sha("identity"),
    )
    plan = SimpleNamespace(
        execution_identity=identity,
        private_dict=lambda: {"schema": "synthetic-private-recipe-plan-v1"},
        plan_sha256=_sha("recipe-plan"),
    )
    frozen = SimpleNamespace(
        plan=plan,
        private_dict=lambda: {"schema": "synthetic-private-freeze-v1"},
        freeze_sha256=_sha("freeze"),
    )
    state = SCRIPT["_DiagnosticState"]()

    document, digest = SCRIPT["_private_plan_document"](
        source_commit="a" * 40,
        source_bundle=_sha("source"),
        rom_sha256=_sha("rom"),
        goal_registry_sha256=_sha("goal-registry"),
        catalog_sha256=_sha("catalog"),
        context_plan_sha256=_sha("context-plan"),
        runtime=_runtime(),
        route_registry_sha256=_sha("route-registry"),
        frozen=frozen,
        state=state,
    )

    validate_private_record(document)
    assert document["private_plan_sha256"] == digest
    assert document["execution_identity_sha256"] == identity.identity_sha256
    assert document["recipe_plan_sha256"] == plan.plan_sha256
    assert document["runtime_identity_sha256"] == _runtime().sha256
    assert document["source_catalog_partition_reused_as_prospective_label"] is False
    assert "/" not in json.dumps(document, sort_keys=True)
    for key in (
        "controller_actions",
        "emulator_frames",
        "model_fits",
        "outcomes",
        "provider_executions",
        "root_claims",
        "teacher_queries",
    ):
        assert document[key] == 0
