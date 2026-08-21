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
    str(PROJECT_ROOT / "scripts/run_red_dual_capability_preflight.py"),
    run_name="run_red_dual_capability_preflight_test",
)

from pokemon_red_completion.collection import (
    CollectionLocation,
    CollectionObservation,
    LivingSpecimen,
)
from pokemon_red_completion.global_router import MacroEdge, MacroGraph, MacroTransition
from pokemon_red_completion.goal_manager import GoalKind
from pokemon_red_completion.goal_manager_runtime import (
    ExecutableGoalBinding,
    GoalExecutionReport,
    GoalVerification,
)
from pokemon_red_completion.local_router import LocalEdge, LocalGraph
from pokemon_red_completion.observation import ItemId, MapId
from pokemon_red_completion.red_collection import red_species_ref
from pokemon_red_completion.route_executor import TraversalSnapshot
from pokemon_red_completion.route_plan import plan_route


def _sha(value: str) -> str:
    return hashlib.sha256(value.encode("ascii")).hexdigest()


def _args() -> list[str]:
    return [
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
        "--expected-profile-sha256",
        _sha("profile"),
        "--private-root",
        "/private/root",
        "--rom",
        "/private/red.gb",
    ]


def _route_plan() -> object:
    target = int(MapId.DIGLETTS_CAVE)
    transition = MacroTransition((0, 1), (5, 5), "up")
    macro = MacroGraph({1: (MacroEdge(target, coordinate_transitions=(transition,)),)})
    local = {
        1: LocalGraph({(0, 0): (LocalEdge((0, 1), action="right"),), (0, 1): ()})
    }
    return plan_route(macro, local, 1, (0, 0), target)


def _collection() -> CollectionObservation:
    precursor = red_species_ref(50)
    unrelated = red_species_ref(9)
    specimens = (
        LivingSpecimen(precursor, 20, CollectionLocation.PARTY, slot_index=0),
        LivingSpecimen(unrelated, 20, CollectionLocation.PARTY, slot_index=1),
    )
    return CollectionObservation(
        owned_species=frozenset(item.species_ref for item in specimens),
        specimens=specimens,
        party_size=2,
        party_limit=6,
        box_counts=(0,),
        current_box_index=0,
        box_capacity=20,
    )


def _readiness() -> SimpleNamespace:
    profile_sha256 = _sha("profile")
    evolution_configuration_sha256 = "d" * 64
    return SimpleNamespace(
        gate=SimpleNamespace(
            execution_manifest_sha256=_sha("manifest"),
            public_bindings={
                "source_commit": "b" * 40,
                "source_bundle_sha256": _sha("source"),
                "runner_sha256": _sha("runner"),
            },
        ),
        runtime=SimpleNamespace(sha256=_sha("runtime")),
        rom_path=Path("/private/red.gb"),
        rom=SimpleNamespace(sha256=SCRIPT["POKEMON_RED_US_REV_0"].sha256),
        rom_bytes=b"rom",
        capture=SimpleNamespace(
            state_bytes=b"state",
            state_sha256=_sha("state"),
            envelope_sha256=_sha("envelope"),
        ),
        profile=SimpleNamespace(
            profile_sha256=profile_sha256,
            providers=(
                SimpleNamespace(
                    kind=GoalKind.EVOLVE_SPECIES,
                    configuration_sha256=evolution_configuration_sha256,
                ),
            ),
        ),
        assignment=SimpleNamespace(
            assignment_id=_sha("assignment"),
            root_lineage_id=f"red-goal-root-{_sha('assignment')}",
        ),
        catalog_entry=SimpleNamespace(
            question_sha256=_sha("question"),
            policy_context_sha256=_sha("policy"),
            available_menu_sha256=_sha("menu"),
            binding_manifest_sha256=_sha("bindings"),
            available_goal_kinds=(GoalKind.EVOLVE_SPECIES,),
        ),
        context_identity_sha256=_sha("context"),
        authenticated_fit=SimpleNamespace(model_sha256=SCRIPT["MODEL_SHA256"]),
        store=object(),
    )


class _Emulator:
    frame_count = 77
    pressed_buttons: frozenset[str] = frozenset()

    def __enter__(self) -> _Emulator:
        return self

    def __exit__(self, *args: object) -> None:
        del args

    def load_state_bytes(self, state: bytes) -> None:
        assert state == b"state"


class _Area:
    def __init__(self, observation: CollectionObservation) -> None:
        self.observation = observation

    def read_collection(self) -> CollectionObservation:
        return self.observation

    def read(self) -> SimpleNamespace:
        return SimpleNamespace(
            map_id=1,
            player_x=0,
            player_y=0,
            battle_state=0,
        )

    def encountered_species_ref(self) -> None:
        return None

    def seek_encounter(self) -> None:
        raise AssertionError("zero-action preflight cannot seek")

    def capture_encounter(self, species_ref: str) -> bool:
        del species_ref
        raise AssertionError("zero-action preflight cannot capture")

    def flee_encounter(self) -> None:
        raise AssertionError("zero-action preflight cannot flee")

    def switch_box(self, box_index: int) -> None:
        del box_index
        raise AssertionError("zero-action preflight cannot switch boxes")


def test_public_manifest_failure_stops_before_any_private_read(
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

    assert SCRIPT["main"](_args()) == 1

    result = json.loads(capsys.readouterr().out)
    assert private_calls == 0
    assert result["failure_stage"] == "public_manifest_authentication"
    assert result["protected_access_status"] == "verified_absent"
    assert "/private" not in json.dumps(result)


def test_named_runner_failure_preserves_only_its_safe_stage(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setitem(
        SCRIPT["main"].__globals__,
        "_authenticate_public_gate",
        lambda _args: (_ for _ in ()).throw(
            SCRIPT["RedDualCapabilityPreflightError"]("script_import_authentication")
        ),
    )

    assert SCRIPT["main"](_args()) == 1

    result = json.loads(capsys.readouterr().out)
    assert result["failure_stage"] == "script_import_authentication"
    assert result["protected_access_status"] == "verified_absent"
    assert "/private" not in json.dumps(result)


def test_runner_has_one_frozen_context_and_no_substitution_argument() -> None:
    parser = SCRIPT["_parser"]()
    parsed = parser.parse_args(_args())

    assert SCRIPT["SELECTED_SLOT_ID"] == "red-goal-v1-032-evolve_species-train-05"
    assert not hasattr(parsed, "slot_id")
    assert "write_root_claim" not in SCRIPT


def test_manifest_semantics_bind_exact_design_context_and_fit() -> None:
    args = SimpleNamespace(
        registry_source_commit="a" * 40,
        expected_context_catalog_sha256=_sha("catalog"),
        expected_context_plan_sha256=_sha("plan"),
        expected_registry_sha256=_sha("registry"),
        expected_profile_sha256=_sha("profile"),
    )
    design = SCRIPT["_read_evaluation_design"]()

    bindings = SCRIPT["_semantic_bindings"](args, design)

    assert bindings["selected_context_slot_sha256"] == SCRIPT["canonical_sha256"](
        {
            "schema": "pokemon.red.dual-capability-context-slot.v1",
            "slot_id": SCRIPT["SELECTED_SLOT_ID"],
        }
    )
    assert bindings["model_sha256"] == SCRIPT["MODEL_SHA256"]
    assert bindings["curriculum_design_sha256"] == SCRIPT["canonical_sha256"](
        SCRIPT["red_dual_capability_curriculum_design"]().public_dict()
    )
    assert all(key.endswith("_sha256") for key in bindings)
    assert "/private" not in json.dumps(bindings)


def test_context_plan_accepts_only_one_exact_frozen_slot() -> None:
    row = {
        "slot_id": SCRIPT["SELECTED_SLOT_ID"],
        "state": "/outside/state.bin",
        "envelope": "/outside/envelope.json",
        "profile": "/outside/profile.json",
    }
    payload = SCRIPT["canonical_manifest_line"](
        {
            "schema": SCRIPT["CONTEXT_PLAN_SCHEMA"],
            "registry_sha256": _sha("registry"),
            "source_commit": "a" * 40,
            "entries": [row],
        }
    )

    entry = SCRIPT["_context_plan_entry"](
        payload,
        registry_sha256=_sha("registry"),
        source_commit="a" * 40,
    )
    assert entry.state == Path("/outside/state.bin")

    duplicate = SCRIPT["canonical_manifest_line"](
        {
            "schema": SCRIPT["CONTEXT_PLAN_SCHEMA"],
            "registry_sha256": _sha("registry"),
            "source_commit": "a" * 40,
            "entries": [row, row],
        }
    )
    with pytest.raises(SCRIPT["RedDualCapabilityPreflightError"]):
        SCRIPT["_context_plan_entry"](
            duplicate,
            registry_sha256=_sha("registry"),
            source_commit="a" * 40,
        )


def test_capture_inventory_excludes_master_ball_and_rejects_ambiguous_rows() -> None:
    items = (
        (int(ItemId.POKE_BALL), 2),
        (int(ItemId.GREAT_BALL), 3),
        (int(ItemId.ULTRA_BALL), 4),
        (int(ItemId.MASTER_BALL), 1),
    )

    assert SCRIPT["_ordinary_capture_items"](items) == 9
    invalid = (
        [(int(ItemId.POKE_BALL), 2)],
        ((int(ItemId.POKE_BALL), 2), (int(ItemId.POKE_BALL), 3)),
        ((-1, 2),),
        ((256, 2),),
        ((int(ItemId.POKE_BALL), -1),),
        ((int(ItemId.POKE_BALL), 256),),
        ((True, 2),),
    )
    for raw_items in invalid:
        with pytest.raises(SCRIPT["RedDualCapabilityPreflightError"]):
            SCRIPT["_ordinary_capture_items"](raw_items)


def test_action_free_observation_builds_real_semantic_two_choice_menu(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    readiness = _readiness()
    collection = _collection()
    route_plan = _route_plan()
    calls: list[tuple[str, object]] = []
    evolution = ExecutableGoalBinding(
        binding_ref=(
            "pokemon.red:evolution:diglett-to-dugtrio:"
            f"profile-{readiness.profile.profile_sha256}:config-{'d' * 64}"
        ),
        kind=GoalKind.EVOLVE_SPECIES,
        estimated_effort=0.5,
        estimated_risk=0.2,
        execute=lambda: GoalExecutionReport(1, 1, {"bounded": True}),
        verify=lambda _report: GoalVerification.succeeded(),
    )
    binding_set = SimpleNamespace(bindings=(evolution,), opportunities=(object(),))
    observation = SimpleNamespace(
        situation=object(),
        collection_observation=collection,
        immediate_capture_slots=4,
        input_ready=True,
        raw=SimpleNamespace(
            bag_items=((int(ItemId.GREAT_BALL), 12),),
            battle_state=0,
        ),
    )
    context_runtime = SimpleNamespace(
        adapter=SimpleNamespace(observe=lambda: observation),
        enumerator=lambda _actions: SimpleNamespace(enumerate=lambda _obs: binding_set),
    )
    fake_area = _Area(collection)

    class _World:
        rules = SimpleNamespace(cut_block_swaps=())

        def plan_to_map(self, start: object, goal: int) -> object:
            calls.append(("route", (start, goal)))
            return route_plan

        def replanner(self) -> object:
            return lambda _request: route_plan

    class _Traversal:
        def __init__(self, *args: object, **kwargs: object) -> None:
            del args, kwargs

        def observe(self) -> TraversalSnapshot:
            return TraversalSnapshot(1, (0, 0), True)

    monkeypatch.setitem(
        SCRIPT["_observe_action_free"].__globals__,
        "PyBoyAdapter",
        lambda *args, **kwargs: _Emulator(),
    )
    monkeypatch.setitem(
        SCRIPT["_observe_action_free"].__globals__,
        "require_pyboy_import_origins",
        lambda _runtime: None,
    )
    monkeypatch.setitem(
        SCRIPT["_observe_action_free"].__globals__,
        "StrategicScenarioRouteWorld",
        SimpleNamespace(from_rom=lambda payload: _World()),
    )
    monkeypatch.setitem(
        SCRIPT["_observe_action_free"].__globals__,
        "PokemonRedStateReader",
        lambda _emulator: fake_area,
    )
    monkeypatch.setitem(
        SCRIPT["_observe_action_free"].__globals__,
        "build_red_goal_context_runtime",
        lambda **kwargs: context_runtime,
    )
    monkeypatch.setitem(
        SCRIPT["_observe_action_free"].__globals__,
        "ordered_goal_manager_question",
        lambda **kwargs: SimpleNamespace(
            ordered_policy_input_sha256=_sha("question"),
            policy_context_sha256=_sha("policy"),
            available_menu_sha256=_sha("menu"),
        ),
    )
    monkeypatch.setitem(
        SCRIPT["_observe_action_free"].__globals__,
        "goal_binding_manifest_sha256",
        lambda _bindings: _sha("bindings"),
    )
    monkeypatch.setitem(
        SCRIPT["_observe_action_free"].__globals__,
        "Gen1TraversalObserver",
        _Traversal,
    )
    monkeypatch.setitem(
        SCRIPT["_observe_action_free"].__globals__,
        "Gen1TrainerSightProjector",
        lambda *args: object(),
    )
    monkeypatch.setitem(
        SCRIPT["_observe_action_free"].__globals__,
        "LiveWildEncounterExecutor",
        lambda *args, **kwargs: fake_area,
    )
    monkeypatch.setitem(
        SCRIPT["_observe_action_free"].__globals__,
        "verify_rom",
        lambda _path: SimpleNamespace(sha256=readiness.rom.sha256),
    )

    observed = SCRIPT["_observe_action_free"](readiness)

    assert calls == [("route", (TraversalSnapshot(1, (0, 0), True), int(MapId.DIGLETTS_CAVE)))]
    result = observed.result
    assert result["status"] == "action_free_scenario_qualified_root_unclaimed"
    assert result["scenario"]["candidate_count"] == 2
    assert result["scenario"]["candidate_order"] == ["acquire_species", "evolve_species"]
    assert result["model_predictions"] == 0
    assert result["controller_actions"] == 0
    assert result["emulator_frames_advanced"] == 0
    assert result["identity_claims_written"] == 0
    assert len(result["semantic_scenario_identity_sha256"]) == 64
    assert result["private_species_fields"] == 0
    assert result["private_route_fields"] == 0


def test_source_to_venue_mismatch_fails_before_any_action(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    readiness = _readiness()
    monkeypatch.setitem(
        SCRIPT["_observe_action_free"].__globals__,
        "DIGLETTS_CAVE_SOURCE_ID",
        "wild:Route1:grass",
    )
    monkeypatch.setitem(
        SCRIPT["_observe_action_free"].__globals__,
        "require_pyboy_import_origins",
        lambda _runtime: None,
    )
    monkeypatch.setitem(
        SCRIPT["_observe_action_free"].__globals__,
        "PyBoyAdapter",
        lambda *args, **kwargs: _Emulator(),
    )
    # Stop at the source/catalog join, after all preceding seams return the same
    # controlled values used by the successful integration test.
    monkeypatch.setitem(
        SCRIPT["_observe_action_free"].__globals__,
        "StrategicScenarioRouteWorld",
        SimpleNamespace(from_rom=lambda payload: SimpleNamespace()),
    )

    # A source mismatch is already rejected by the real plan object constructor.
    species = SCRIPT["RedDependencySpeciesBinding"](red_species_ref(50), red_species_ref(51))
    route = SCRIPT["SemanticVenueRouteBinding"](_route_plan(), _sha("planner"))
    with pytest.raises(RuntimeError, match="repeatable wild target"):
        SCRIPT["SemanticVenueCapturePlan"](
            readiness.capture.state_sha256,
            species,
            "wild:Route1:grass",
            route,
            SCRIPT["DIGLETTS_CAVE_TRAINING_VENUE"],
        )


def test_unknown_battle_state_cannot_be_treated_as_action_free_readiness(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    readiness = _readiness()
    collection = _collection()
    observation = SimpleNamespace(
        situation=object(),
        collection_observation=collection,
        immediate_capture_slots=4,
        input_ready=True,
        raw=SimpleNamespace(
            bag_items=((int(ItemId.GREAT_BALL), 12),),
            battle_state=None,
        ),
    )
    evolution = ExecutableGoalBinding(
        binding_ref=(
            "pokemon.red:evolution:diglett-to-dugtrio:"
            f"profile-{readiness.profile.profile_sha256}:config-{'d' * 64}"
        ),
        kind=GoalKind.EVOLVE_SPECIES,
        estimated_effort=0.5,
        estimated_risk=0.2,
        execute=lambda: GoalExecutionReport(1, 1, {"bounded": True}),
        verify=lambda _report: GoalVerification.succeeded(),
    )
    context_runtime = SimpleNamespace(
        adapter=SimpleNamespace(observe=lambda: observation),
        enumerator=lambda _actions: SimpleNamespace(
            enumerate=lambda _obs: SimpleNamespace(
                bindings=(evolution,),
                opportunities=(object(),),
            )
        ),
    )
    monkeypatch.setitem(
        SCRIPT["_observe_action_free"].__globals__,
        "require_pyboy_import_origins",
        lambda _runtime: None,
    )
    monkeypatch.setitem(
        SCRIPT["_observe_action_free"].__globals__,
        "PyBoyAdapter",
        lambda *args, **kwargs: _Emulator(),
    )
    monkeypatch.setitem(
        SCRIPT["_observe_action_free"].__globals__,
        "StrategicScenarioRouteWorld",
        SimpleNamespace(from_rom=lambda payload: SimpleNamespace()),
    )
    monkeypatch.setitem(
        SCRIPT["_observe_action_free"].__globals__,
        "PokemonRedStateReader",
        lambda _emulator: _Area(collection),
    )
    monkeypatch.setitem(
        SCRIPT["_observe_action_free"].__globals__,
        "build_red_goal_context_runtime",
        lambda **kwargs: context_runtime,
    )
    monkeypatch.setitem(
        SCRIPT["_observe_action_free"].__globals__,
        "ordered_goal_manager_question",
        lambda **kwargs: SimpleNamespace(
            ordered_policy_input_sha256=_sha("question"),
            policy_context_sha256=_sha("policy"),
            available_menu_sha256=_sha("menu"),
        ),
    )
    monkeypatch.setitem(
        SCRIPT["_observe_action_free"].__globals__,
        "goal_binding_manifest_sha256",
        lambda _bindings: _sha("bindings"),
    )
    monkeypatch.setitem(
        SCRIPT["_observe_action_free"].__globals__,
        "Gen1TraversalObserver",
        lambda *args, **kwargs: SimpleNamespace(
            observe=lambda: TraversalSnapshot(1, (0, 0), True)
        ),
    )
    monkeypatch.setitem(
        SCRIPT["_observe_action_free"].__globals__,
        "Gen1TrainerSightProjector",
        lambda *args: object(),
    )

    with pytest.raises(
        SCRIPT["RedDualCapabilityPreflightError"],
        match="capture_capability_authentication",
    ):
        SCRIPT["_observe_action_free"](readiness)


def test_preflight_checks_claim_and_episode_without_writing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events: list[str] = []
    readiness = _readiness()
    observed = SimpleNamespace(
        result={"schema": SCRIPT["PREFLIGHT_SCHEMA"], "status": "ready"},
        root_consumption_sha256=_sha("root"),
        controller_actions=0,
        attempted_controller_actions=0,
        emulator_frames_advanced=0,
    )
    monkeypatch.setitem(
        SCRIPT["_preflight_result"].__globals__,
        "open_fixed_account_claim_registry",
        lambda: Path("/fixed/claims"),
    )
    monkeypatch.setitem(
        SCRIPT["_preflight_result"].__globals__,
        "fixed_account_claim_registry_lease",
        lambda *args, **kwargs: nullcontext(),
    )
    monkeypatch.setitem(
        SCRIPT["_preflight_result"].__globals__,
        "_require_fit_claim",
        lambda registry: events.append("fit-claim"),
    )
    monkeypatch.setitem(
        SCRIPT["_preflight_result"].__globals__,
        "root_claim_is_available",
        lambda registry, claim: (events.append(f"claim:{claim}"), True)[1],
    )

    result = SCRIPT["_preflight_result"](readiness, observed)

    assert events == [
        "fit-claim",
        f"claim:{_sha('root')}",
    ]
    assert result["semantic_root_available"] is True
    assert result["semantic_root_consumed"] is False
    assert result["model_fits_added"] == 0
    assert result["unseen_comparisons_added"] == 0


def test_fit_claim_must_match_every_frozen_field(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    expected = {
        "schema": "pokemon.red.fresh-composition-root-claim.v1",
        "root_consumption_sha256": SCRIPT["FIT_CLAIM_SHA256"],
        "execution_identity_sha256": SCRIPT["FIT_EXECUTION_IDENTITY_SHA256"],
        "source_commit": SCRIPT["FIT_SOURCE_COMMIT"],
        "runner_sha256": SCRIPT["FIT_RUNNER_SHA256"],
    }
    monkeypatch.setitem(
        SCRIPT["_require_fit_claim"].__globals__,
        "read_root_claim",
        lambda _registry, _claim: dict(expected),
    )
    SCRIPT["_require_fit_claim"](Path("/fixed/claims"))

    for key in expected:
        changed = dict(expected)
        changed[key] = "changed"
        monkeypatch.setitem(
            SCRIPT["_require_fit_claim"].__globals__,
            "read_root_claim",
            lambda _registry, _claim, changed=changed: changed,
        )
        with pytest.raises(
            SCRIPT["RedDualCapabilityPreflightError"],
            match="fit_claim_authentication",
        ):
            SCRIPT["_require_fit_claim"](Path("/fixed/claims"))


def test_semantic_identity_is_stable_across_public_source_changes() -> None:
    readiness = _readiness()
    scenario = SCRIPT["red_dual_capability_scenario_specs"]()[0]
    species = SCRIPT["RedDependencySpeciesBinding"](
        red_species_ref(50),
        red_species_ref(51),
    )
    first = SCRIPT["_semantic_identities"](readiness, scenario, species)
    changed = SimpleNamespace(
        execution_manifest_sha256=readiness.gate.execution_manifest_sha256,
        public_bindings={
            **readiness.gate.public_bindings,
            "runner_sha256": _sha("other"),
        },
    )
    changed_readiness = SimpleNamespace(**{**vars(readiness), "gate": changed})
    second = SCRIPT["_semantic_identities"](changed_readiness, scenario, species)

    assert first == second
    assert first[0] == SCRIPT["root_consumption_sha256"](
        state_sha256=readiness.capture.state_sha256,
        envelope_sha256=readiness.capture.envelope_sha256,
    )


def test_failure_receipts_never_echo_private_details() -> None:
    result = SCRIPT["_failure_receipt"]("private_readiness_authentication")

    assert result["protected_access_status"] == "not_attested"
    assert result["effect_status"] == "not_attested"
    assert result["context_substitutions"] == 0
    assert "/private" not in json.dumps(result)
