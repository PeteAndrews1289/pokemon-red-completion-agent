# ruff: noqa: E402 -- standalone runner is loaded after its script-local imports.

from __future__ import annotations

import hashlib
import json
import runpy
import sys
from contextlib import nullcontext
from pathlib import Path
from types import SimpleNamespace

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_ROOT = PROJECT_ROOT / "scripts"
while str(SCRIPTS_ROOT) in sys.path:
    sys.path.remove(str(SCRIPTS_ROOT))
sys.path.insert(0, str(SCRIPTS_ROOT))

SCRIPT = runpy.run_path(
    str(PROJECT_ROOT / "scripts/run_red_living_dex_dependency_shadow.py"),
    run_name="run_red_living_dex_dependency_shadow_test",
)

from pokemon_red_completion.collection import (
    CollectionLocation,
    CollectionObservation,
    LivingSpecimen,
)
from pokemon_red_completion.goal_manager import GoalKind
from pokemon_red_completion.living_dex_dependency_evaluation_v2 import (
    RootlessDependencyEvaluationDesignV2,
)
from pokemon_red_completion.living_dex_dependency_ranker import (
    DEPENDENCY_RANKER_FEATURE_NAMES,
    DependencyRankerModel,
)
from pokemon_red_completion.private_artifacts import initialize_private_root
from pokemon_red_completion.red_collection import red_species_ref
from pokemon_red_completion.red_goal_context_profile import RedGoalMechanic
from pokemon_red_completion.red_living_dex_dependency_adapter import (
    RedDependencyExecutionFacts,
    adapt_red_living_dex_dependencies,
)
from pokemon_red_completion.red_living_dex_dependency_shadow import (
    PreparedRedDependencyShadow,
    RedDependencyShadowStop,
    prepare_red_dependency_shadow,
)


def _sha(value: str) -> str:
    return hashlib.sha256(value.encode("ascii")).hexdigest()


def _model(weights: tuple[float, ...] = (1.0, -1.0, 0.0, 0.0)) -> DependencyRankerModel:
    return DependencyRankerModel(DEPENDENCY_RANKER_FEATURE_NAMES, weights, _sha("train"))


def _observation() -> CollectionObservation:
    specimens = (
        LivingSpecimen(red_species_ref(147), 30, CollectionLocation.BOX, slot_index=0),
        LivingSpecimen(red_species_ref(148), 30, CollectionLocation.BOX, slot_index=1),
    )
    return CollectionObservation(
        owned_species=frozenset(item.species_ref for item in specimens),
        specimens=specimens,
        party_size=0,
        party_limit=6,
        box_counts=(2,),
        current_box_index=0,
        box_capacity=20,
    )


def _prepared(model: DependencyRankerModel | None = None) -> PreparedRedDependencyShadow:
    model = model or _model()
    precursor = red_species_ref(147)
    result = adapt_red_living_dex_dependencies(
        _observation(),
        execution_facts=RedDependencyExecutionFacts(
            acquirable_precursor_refs=frozenset({precursor})
        ),
    )
    selected = prepare_red_dependency_shadow(
        result,
        design_sha256=SCRIPT["DESIGN_DOCUMENT_SHA256"],
        model_sha256=model.model_sha256,
        context_identity_sha256=_sha("context"),
    )
    assert isinstance(selected, PreparedRedDependencyShadow)
    return selected


class _State:
    status = "absent"


class _Writer:
    def __init__(self, events: list[str]) -> None:
        self.events = events
        self.records: list[tuple[str, dict[str, object], bool]] = []

    def append(self, stream: str, record: dict[str, object], *, durable: bool = False) -> None:
        self.events.append(stream)
        self.records.append((stream, record, durable))

    def complete(self) -> object:
        self.events.append("complete")
        return object()

    def abort(self, reason: str) -> object:
        self.events.append(f"abort:{reason}")
        return object()


class _Store:
    def __init__(self, events: list[str]) -> None:
        self.events = events
        self.writer = _Writer(events)

    def inspect_episode_state(self, episode_id: str) -> _State:
        assert episode_id.startswith("red-shadow-")
        self.events.append("inspect")
        return _State()

    def begin_episode(self, episode_id: str) -> _Writer:
        assert episode_id.startswith("red-shadow-")
        self.events.append("begin")
        return self.writer


def _readiness(
    events: list[str],
    model: DependencyRankerModel | None = None,
) -> SimpleNamespace:
    model = model or _model()
    return SimpleNamespace(
        gate=SimpleNamespace(
            execution_manifest_sha256=_sha("manifest"),
            public_bindings={
                "source_commit": "a" * 40,
                "source_bundle_sha256": _sha("source"),
                "runner_sha256": _sha("runner"),
            },
        ),
        runtime=SimpleNamespace(sha256=_sha("runtime")),
        authenticated_fit=SimpleNamespace(fit=SimpleNamespace(model=model)),
        store=_Store(events),
    )


def _args(mode: str) -> list[str]:
    return [
        "--mode",
        mode,
        "--execution-manifest",
        "/private/manifest.json",
        "--expected-execution-manifest-sha256",
        _sha("manifest"),
        "--registry-source-commit",
        "a" * 40,
        "--expected-registry-sha256",
        _sha("registry"),
        "--context-catalog",
        "/private/catalog.json",
        "--expected-context-catalog-sha256",
        _sha("catalog"),
        "--context-plan",
        "/private/plan.json",
        "--expected-context-plan-sha256",
        _sha("plan"),
        "--slot-id",
        "goal-train-001",
        "--expected-profile-sha256",
        _sha("profile"),
        "--private-root",
        "/private/root",
        "--rom",
        "/private/red.gb",
    ]


def test_frozen_design_and_fit_pins_match_published_documents() -> None:
    assert (
        hashlib.sha256(
            (
                PROJECT_ROOT / "configs/red-living-dex-dependency-shadow-decision-v1.json"
            ).read_bytes()
        ).hexdigest()
        == SCRIPT["DESIGN_DOCUMENT_SHA256"]
    )
    evaluation_path = PROJECT_ROOT / "configs/rootless-living-dex-dependency-evaluation-v2.json"
    assert (
        hashlib.sha256(evaluation_path.read_bytes()).hexdigest()
        == SCRIPT["EVALUATION_DESIGN_DOCUMENT_SHA256"]
    )
    design = RootlessDependencyEvaluationDesignV2.from_dict(
        json.loads(evaluation_path.read_text(encoding="ascii"))
    )
    assert design.design_sha256 == SCRIPT["EVALUATION_DESIGN_SHA256"]
    assert design.train_revalidation_sha256 == SCRIPT["TRAIN_DATASET_SHA256"]
    shadow = json.loads(
        (PROJECT_ROOT / "configs/red-living-dex-dependency-shadow-decision-v1.json").read_text(
            encoding="ascii"
        )
    )
    assert shadow["binding_contract"]["model_sha256"] == SCRIPT["MODEL_SHA256"]
    assert shadow["binding_contract"]["fit_sha256"] == SCRIPT["FIT_SHA256"]


def test_semantic_manifest_bindings_freeze_context_before_private_read() -> None:
    args = SimpleNamespace(
        slot_id="goal-train-001",
        registry_source_commit="a" * 40,
        expected_context_catalog_sha256=_sha("catalog"),
        expected_context_plan_sha256=_sha("plan"),
        expected_registry_sha256=_sha("registry"),
        expected_profile_sha256=_sha("profile"),
    )
    design = SCRIPT["_read_evaluation_design"]()

    bindings = SCRIPT["_semantic_bindings"](args, design)

    assert bindings["selected_context_slot_sha256"] == SCRIPT["canonical_sha256"](
        {"schema": "pokemon.red.shadow-context-slot.v1", "slot_id": "goal-train-001"}
    )
    assert bindings["selected_profile_sha256"] == _sha("profile")
    assert bindings["context_catalog_document_sha256"] == _sha("catalog")
    assert bindings["context_plan_document_sha256"] == _sha("plan")
    assert all(key.endswith("_sha256") for key in bindings)
    assert "/private" not in json.dumps(bindings)


def test_public_dependency_roster_pins_the_manifest_reader() -> None:
    assert "manifest_core=scripts/rootless_execution_manifest.py" in SCRIPT["DEPENDENCIES"]
    assert "manifest_reader=scripts/public_execution_manifest.py" in SCRIPT["DEPENDENCIES"]


def test_script_import_origin_guard_rejects_a_shadow_module(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setitem(
        sys.modules,
        "public_execution_manifest",
        SimpleNamespace(__file__="/private/shadow/public_execution_manifest.py"),
    )

    with pytest.raises(
        SCRIPT["RedLivingDexDependencyShadowRunError"],
        match="script_import_authentication",
    ):
        SCRIPT["_require_script_import_origins"]()


def test_public_manifest_failure_stops_before_private_read(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    private_calls = 0

    def fail_gate(args: object) -> object:
        del args
        raise RuntimeError("/private/secret.gb")

    def private(*args: object) -> object:
        nonlocal private_calls
        del args
        private_calls += 1
        raise AssertionError("private readiness ran")

    monkeypatch.setitem(SCRIPT["main"].__globals__, "_authenticate_public_gate", fail_gate)
    monkeypatch.setitem(SCRIPT["main"].__globals__, "_prepare_readiness", private)

    assert SCRIPT["main"](_args("preflight")) == 1

    result = json.loads(capsys.readouterr().out)
    assert private_calls == 0
    assert result["failure_stage"] == "public_manifest_authentication"
    assert result["protected_access_status"] == "verified_absent"
    assert "/private" not in json.dumps(result)


def test_execution_facts_require_available_profile_bound_exact_skills() -> None:
    acquisition = SimpleNamespace(
        kind=GoalKind.ACQUIRE_SPECIES,
        mechanic=RedGoalMechanic.WILD_CORRIDOR_CAPTURE,
        parameters={"source_id": "wild:DiglettsCave:grass"},
    )
    evolution = SimpleNamespace(
        kind=GoalKind.EVOLVE_SPECIES,
        mechanic=RedGoalMechanic.DIGLETT_EVOLUTION,
        parameters={},
    )
    profile = SimpleNamespace(providers=(acquisition, evolution))
    bindings = (
        SimpleNamespace(
            kind=GoalKind.ACQUIRE_SPECIES,
            binding_ref="pokemon.red:acquisition:wild:DiglettsCave:grass:profile-a:config-b",
        ),
        SimpleNamespace(
            kind=GoalKind.EVOLVE_SPECIES,
            binding_ref="pokemon.red:evolution:diglett-to-dugtrio:profile-a:config-c",
        ),
    )

    facts, pairs = SCRIPT["_execution_facts"](profile, bindings)

    assert facts.trade_available is False
    assert facts.available_item_refs == frozenset()
    assert pairs == frozenset({(red_species_ref(50), red_species_ref(51))})
    assert red_species_ref(50) in facts.acquirable_precursor_refs


def test_context_plan_selects_exactly_one_frozen_slot() -> None:
    document = {
        "schema": SCRIPT["CONTEXT_PLAN_SCHEMA"],
        "registry_sha256": _sha("registry"),
        "source_commit": "a" * 40,
        "entries": [
            {
                "slot_id": "goal-train-001",
                "state": "/outside/state.bin",
                "envelope": "/outside/envelope.json",
                "profile": "/outside/profile.json",
            },
            {
                "slot_id": "goal-train-002",
                "state": "/outside/state-2.bin",
                "envelope": "/outside/envelope-2.json",
                "profile": "/outside/profile-2.json",
            },
        ],
    }
    payload = SCRIPT["canonical_manifest_line"](document)

    entry = SCRIPT["_context_plan_entry"](
        payload,
        slot_id="goal-train-001",
        registry_sha256=_sha("registry"),
        source_commit="a" * 40,
    )

    assert entry.slot_id == "goal-train-001"
    assert entry.state == Path("/outside/state.bin")


def test_context_plan_duplicate_selected_slot_fails_closed() -> None:
    row = {
        "slot_id": "goal-train-001",
        "state": "/outside/state.bin",
        "envelope": "/outside/envelope.json",
        "profile": "/outside/profile.json",
    }
    payload = SCRIPT["canonical_manifest_line"](
        {
            "schema": SCRIPT["CONTEXT_PLAN_SCHEMA"],
            "registry_sha256": _sha("registry"),
            "source_commit": "a" * 40,
            "entries": [row, row],
        }
    )

    with pytest.raises(SCRIPT["RedLivingDexDependencyShadowRunError"]):
        SCRIPT["_context_plan_entry"](
            payload,
            slot_id="goal-train-001",
            registry_sha256=_sha("registry"),
            source_commit="a" * 40,
        )


def test_external_reader_rejects_symlink_and_protected_inode_alias(tmp_path: Path) -> None:
    payload = tmp_path / "payload.bin"
    payload.write_bytes(b"safe")
    link = tmp_path / "link.bin"
    link.symlink_to(payload)

    with pytest.raises(SCRIPT["RedLivingDexDependencyShadowRunError"]):
        SCRIPT["_read_external_bytes"](link, maximum_bytes=20, forbidden=())
    with pytest.raises(SCRIPT["RedLivingDexDependencyShadowRunError"]):
        SCRIPT["_read_external_bytes"](
            payload,
            maximum_bytes=20,
            forbidden=(payload,),
        )


def test_preflight_checks_both_ledgers_without_claiming_or_scoring(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events: list[str] = []
    readiness = _readiness(events)
    observed = SimpleNamespace(prepared=_prepared())
    monkeypatch.setitem(
        SCRIPT["_preflight"].__globals__,
        "open_fixed_account_claim_registry",
        lambda: Path("/fixed/claims"),
    )
    monkeypatch.setitem(
        SCRIPT["_preflight"].__globals__,
        "fixed_account_claim_registry_lease",
        lambda *args, **kwargs: nullcontext(),
    )
    monkeypatch.setitem(
        SCRIPT["_preflight"].__globals__,
        "_require_fit_claim",
        lambda registry: events.append("fit-claim"),
    )
    monkeypatch.setitem(
        SCRIPT["_preflight"].__globals__,
        "root_claim_is_available",
        lambda *args: _record_available(events),
    )
    monkeypatch.setitem(
        SCRIPT["_preflight"].__globals__,
        "write_root_claim",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("preflight claim")),
    )
    monkeypatch.setitem(
        SCRIPT["_preflight"].__globals__,
        "score_red_dependency_shadow",
        lambda *args: (_ for _ in ()).throw(AssertionError("preflight score")),
    )

    result = SCRIPT["_preflight"](readiness, observed)

    assert result["status"] == "ready_identity_unclaimed"
    assert result["model_predictions"] == 0
    assert result["execution_identity_consumed"] is False
    assert events == ["fit-claim", "global-available", "inspect"]


def _patch_execution_boundary(
    monkeypatch: pytest.MonkeyPatch,
    events: list[str],
) -> None:
    monkeypatch.setitem(
        SCRIPT["_execute_shadow"].__globals__,
        "open_fixed_account_claim_registry",
        lambda: Path("/fixed/claims"),
    )
    monkeypatch.setitem(
        SCRIPT["_execute_shadow"].__globals__,
        "fixed_account_claim_registry_lease",
        lambda *args, **kwargs: nullcontext(),
    )
    monkeypatch.setitem(
        SCRIPT["_execute_shadow"].__globals__,
        "_require_fit_claim",
        lambda registry: events.append("fit-claim"),
    )
    monkeypatch.setitem(
        SCRIPT["_execute_shadow"].__globals__,
        "root_claim_is_available",
        lambda *args: _record_available(events),
    )

    def claim(*args: object, **kwargs: object) -> None:
        del args, kwargs
        events.append("claim")

    monkeypatch.setitem(SCRIPT["_execute_shadow"].__globals__, "write_root_claim", claim)


def _record_available(events: list[str]) -> bool:
    events.append("global-available")
    return True


def test_shadow_claims_globally_and_locally_before_exactly_one_score(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events: list[str] = []
    model = _model()
    readiness = _readiness(events, model)
    prepared = _prepared(model)
    observed = SimpleNamespace(prepared=prepared)
    _patch_execution_boundary(monkeypatch, events)
    real_score = SCRIPT["score_red_dependency_shadow"]
    scores = 0

    def score(preparation: object, candidate_model: object) -> object:
        nonlocal scores
        scores += 1
        events.append("score")
        return real_score(preparation, candidate_model)

    monkeypatch.setitem(SCRIPT["_execute_shadow"].__globals__, "score_red_dependency_shadow", score)

    result = SCRIPT["_execute_shadow"](readiness, observed)

    assert result["model_predictions"] == 1
    assert result["controller_actions"] == 0
    assert result["emulator_frames_advanced"] == 0
    assert scores == 1
    assert events == [
        "fit-claim",
        "global-available",
        "inspect",
        "claim",
        "begin",
        "preregistration",
        "score",
        "decision",
        "terminal",
        "complete",
    ]
    assert readiness.store.writer.records[0][2] is True
    assert readiness.store.writer.records[-1][2] is True


def test_shadow_terminal_round_trips_through_the_real_private_episode_store(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    events: list[str] = []
    private_root = tmp_path / "private"
    private_root.mkdir()
    store = initialize_private_root(
        private_root,
        repository_root=PROJECT_ROOT,
        device_id=lambda path: 2 if path == private_root.resolve() else 1,
        git_worktree_probe=lambda _path: False,
    )
    model = _model()
    readiness = _readiness(events, model)
    readiness.store = store
    prepared = _prepared(model)
    observed = SimpleNamespace(prepared=prepared)
    _patch_execution_boundary(monkeypatch, events)

    result = SCRIPT["_execute_shadow"](readiness, observed)
    _claim, _execution, episode_id = SCRIPT["_execution_identities"](
        readiness,
        prepared,
    )
    episode = store.open_episode(episode_id)

    assert result["model_predictions"] == 1
    assert episode.summary.status == "complete"
    assert episode.stream_names == ("decision", "preregistration", "terminal")
    assert len(tuple(episode.iter_stream("decision"))) == 1
    assert len(tuple(episode.iter_stream("terminal"))) == 1


def test_claim_collision_stops_before_score_and_local_write(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events: list[str] = []
    readiness = _readiness(events)
    observed = SimpleNamespace(prepared=_prepared())
    _patch_execution_boundary(monkeypatch, events)
    monkeypatch.setitem(
        SCRIPT["_execute_shadow"].__globals__,
        "root_claim_is_available",
        lambda *args: False,
    )
    monkeypatch.setitem(
        SCRIPT["_execute_shadow"].__globals__,
        "score_red_dependency_shadow",
        lambda *args: (_ for _ in ()).throw(AssertionError("collision scored")),
    )

    with pytest.raises(SCRIPT["RedLivingDexDependencyShadowRunError"]):
        SCRIPT["_execute_shadow"](readiness, observed)

    assert "claim" not in events
    assert "begin" not in events


def test_postprediction_failure_retains_one_failure_terminal_and_aborts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events: list[str] = []
    readiness = _readiness(events)
    observed = SimpleNamespace(prepared=_prepared())
    _patch_execution_boundary(monkeypatch, events)
    monkeypatch.setitem(
        SCRIPT["_execute_shadow"].__globals__,
        "score_red_dependency_shadow",
        lambda *args: (_ for _ in ()).throw(RuntimeError("/private/model")),
    )

    with pytest.raises(SCRIPT["RedLivingDexDependencyShadowRunError"]):
        SCRIPT["_execute_shadow"](readiness, observed)

    streams = [stream for stream, _record, _durable in readiness.store.writer.records]
    assert streams == ["preregistration", "terminal"]
    assert events[-1] == "abort:shadow_prediction_failed"
    failure = readiness.store.writer.records[-1][1]
    assert failure["first_failure_retained"] is True
    assert failure["failure_phase"] == "model_prediction"
    assert "/private" not in json.dumps(failure)


def test_uncertain_success_terminal_uses_distinct_durable_failure_stream(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events: list[str] = []
    readiness = _readiness(events)
    observed = SimpleNamespace(prepared=_prepared())
    _patch_execution_boundary(monkeypatch, events)
    writer = readiness.store.writer
    original_append = writer.append

    def fail_success_terminal(
        stream: str,
        record: dict[str, object],
        *,
        durable: bool = False,
    ) -> None:
        if stream == "terminal" and record.get("status") == "complete":
            events.append("terminal-write-failed")
            raise OSError("/private/terminal")
        original_append(stream, record, durable=durable)

    monkeypatch.setattr(writer, "append", fail_success_terminal)

    with pytest.raises(SCRIPT["RedLivingDexDependencyShadowRunError"]):
        SCRIPT["_execute_shadow"](readiness, observed)

    assert [stream for stream, _record, _durable in writer.records] == [
        "preregistration",
        "decision",
        "failure",
    ]
    failure = writer.records[-1][1]
    assert failure["failure_phase"] == "terminal_persistence"
    assert failure["model_prediction_completed"] is True
    assert writer.records[-1][2] is True
    assert events[-1] == "abort:shadow_prediction_failed"
    assert "/private" not in json.dumps(failure)


def test_no_eligible_shadow_writes_durable_zero_prediction_terminal(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events: list[str] = []
    readiness = _readiness(events)
    empty_result = adapt_red_living_dex_dependencies(_observation())
    stopped = prepare_red_dependency_shadow(
        empty_result,
        design_sha256=SCRIPT["DESIGN_DOCUMENT_SHA256"],
        model_sha256=SCRIPT["MODEL_SHA256"],
        context_identity_sha256=_sha("context"),
        execution_capable_binding_sha256s=frozenset(),
    )
    assert isinstance(stopped, RedDependencyShadowStop)
    observed = SimpleNamespace(prepared=stopped)
    _patch_execution_boundary(monkeypatch, events)
    monkeypatch.setitem(
        SCRIPT["_execute_shadow"].__globals__,
        "score_red_dependency_shadow",
        lambda *args: (_ for _ in ()).throw(AssertionError("stop scored")),
    )

    result = SCRIPT["_execute_shadow"](readiness, observed)

    assert result["model_predictions"] == 0
    assert [stream for stream, _record, _durable in readiness.store.writer.records] == [
        "preregistration",
        "terminal",
    ]
    assert events[-1] == "complete"


def test_action_free_observation_rejects_any_frame_advance(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class Emulator:
        frame_count = 0
        pressed_buttons: frozenset[str] = frozenset()

        def __enter__(self) -> Emulator:
            return self

        def __exit__(self, *args: object) -> None:
            return None

        def load_state_bytes(self, payload: bytes) -> None:
            assert payload == b"state"

    emulator = Emulator()
    live = SimpleNamespace(collection_observation=_observation(), situation=object())

    def enumerate_changed(observation: object) -> SimpleNamespace:
        del observation
        emulator.frame_count = 1
        return SimpleNamespace(bindings=(), opportunities=())

    runtime = SimpleNamespace(
        adapter=SimpleNamespace(observe=lambda: live),
        enumerator=lambda actions: SimpleNamespace(enumerate=enumerate_changed),
    )
    readiness = SimpleNamespace(
        runtime=SimpleNamespace(sha256=_sha("runtime")),
        rom_path=Path("/private/red.gb"),
        rom=SimpleNamespace(sha256=_sha("rom")),
        capture=SimpleNamespace(state_bytes=b"state"),
        profile=SimpleNamespace(),
        context_identity_sha256=_sha("context"),
        assignment=SimpleNamespace(assignment_id=_sha("assignment")),
        catalog_entry=SimpleNamespace(
            question_sha256=_sha("question"),
            policy_context_sha256=_sha("policy"),
            available_menu_sha256=_sha("menu"),
            binding_manifest_sha256=_sha("bindings"),
            available_goal_kinds=(),
        ),
    )
    monkeypatch.setitem(
        SCRIPT["_observe_read_only"].__globals__, "PyBoyAdapter", lambda *a, **k: emulator
    )
    monkeypatch.setitem(
        SCRIPT["_observe_read_only"].__globals__,
        "require_pyboy_import_origins",
        lambda runtime: None,
    )
    monkeypatch.setitem(
        SCRIPT["_observe_read_only"].__globals__,
        "PokemonRedStateReader",
        lambda emulator: object(),
    )
    monkeypatch.setitem(
        SCRIPT["_observe_read_only"].__globals__,
        "build_red_goal_context_runtime",
        lambda **kwargs: runtime,
    )
    monkeypatch.setitem(
        SCRIPT["_observe_read_only"].__globals__,
        "ordered_goal_manager_question",
        lambda **kwargs: SimpleNamespace(
            ordered_policy_input_sha256=_sha("question"),
            policy_context_sha256=_sha("policy"),
            available_menu_sha256=_sha("menu"),
        ),
    )
    monkeypatch.setitem(
        SCRIPT["_observe_read_only"].__globals__,
        "goal_binding_manifest_sha256",
        lambda bindings: _sha("bindings"),
    )

    with pytest.raises(
        SCRIPT["RedLivingDexDependencyShadowRunError"],
        match="zero_effect_authentication",
    ):
        SCRIPT["_observe_read_only"](readiness)


def test_action_free_observation_rejects_optional_encounter_log_before_emulator(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(SCRIPT["ENCOUNTER_LOG_VARIABLE"], "/private/encounters.jsonl")
    monkeypatch.setitem(
        SCRIPT["_observe_read_only"].__globals__,
        "PyBoyAdapter",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("emulator opened")),
    )

    with pytest.raises(
        SCRIPT["RedLivingDexDependencyShadowRunError"],
        match="zero_effect_environment",
    ):
        SCRIPT["_observe_read_only"](SimpleNamespace())


def test_failure_receipt_never_claims_unknown_live_effects_or_exposes_identity() -> None:
    early = SCRIPT["_failure_receipt"]("public_manifest_authentication")
    late = SCRIPT["_failure_receipt"]("shadow_prediction")

    assert early["effect_status"] == "verified_zero"
    assert early["protected_access_status"] == "verified_absent"
    assert late["effect_status"] == "not_attested"
    assert late["protected_access_status"] == "not_attested"
    assert late["private_path_fields"] == 0
    assert late["private_identity_fields"] == 0
