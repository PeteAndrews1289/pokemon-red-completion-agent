# ruff: noqa: E402 -- standalone runner is loaded after its script-local imports.

from __future__ import annotations

import hashlib
import json
import runpy
import sys
from copy import deepcopy
from pathlib import Path

import pytest

from pokemon_red_completion.collection import (
    CollectionLocation,
    CollectionObservation,
    LivingSpecimen,
)
from pokemon_red_completion.global_router import MacroGraph
from pokemon_red_completion.local_router import LocalGraph
from pokemon_red_completion.private_artifacts import (
    PrivateArtifactError,
    initialize_private_root,
)
from pokemon_red_completion.red_collection import red_species_ref
from pokemon_red_completion.red_living_dex_dependency_adapter import (
    RedDependencyExecutionFacts,
    adapt_red_living_dex_dependencies,
)
from pokemon_red_completion.red_living_dex_multifamily_curriculum import (
    RedMultifamilyContext,
    freeze_two_family_curriculum,
    inventory_red_multifamily_contexts,
)
from pokemon_red_completion.route_executor import TraversalSnapshot
from pokemon_red_completion.route_plan import plan_route

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_ROOT = PROJECT_ROOT / "scripts"
while str(SCRIPTS_ROOT) in sys.path:
    sys.path.remove(str(SCRIPTS_ROOT))
sys.path.insert(0, str(SCRIPTS_ROOT))

SCRIPT_PATH = PROJECT_ROOT / "scripts/freeze_red_living_dex_multifamily_pilot.py"
SCRIPT = runpy.run_path(
    str(SCRIPT_PATH),
    run_name="freeze_red_living_dex_multifamily_pilot_test",
)
V3_SCRIPT_PATH = PROJECT_ROOT / "scripts/freeze_red_living_dex_multifamily_pilot_v3.py"
V3_SCRIPT = runpy.run_path(
    str(V3_SCRIPT_PATH),
    run_name="freeze_red_living_dex_multifamily_pilot_v3_test",
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


def _synthetic_curriculum() -> tuple[object, object, dict[tuple[str, str], object]]:
    precursor_a = red_species_ref(11)
    evolved_a = red_species_ref(12)
    precursor_b = red_species_ref(14)
    evolved_b = red_species_ref(15)
    specimens = tuple(
        LivingSpecimen(
            species,
            4,
            CollectionLocation.BOX,
            container_index=0,
            slot_index=index,
        )
        for index, species in enumerate(
            (precursor_a, precursor_a, precursor_b, precursor_b)
        )
    )
    observation = CollectionObservation(
        owned_species=frozenset({precursor_a, precursor_b}),
        specimens=specimens,
        party_size=0,
        party_limit=6,
        box_counts=(4,),
        current_box_index=0,
        box_capacity=20,
    )
    facts = RedDependencyExecutionFacts(
        acquirable_precursor_refs=frozenset({precursor_a, precursor_b}),
        trainable_evolution_pairs=frozenset(
            {(precursor_a, evolved_a), (precursor_b, evolved_b)}
        ),
    )
    contexts = tuple(
        RedMultifamilyContext(
            _sha(f"context-{index}"),
            _sha(f"root-{index}"),
            "train" if index < 8 else "development",
            observation,
            facts,
            True,
        )
        for index in range(16)
    )
    inventory = inventory_red_multifamily_contexts(contexts)
    family_a = next(
        item.family_identity_sha256
        for item in inventory.opportunities
        if item.context.partition == "train"
        and item.opportunity.binding.precursor_species_ref == precursor_a
    )
    family_b = next(
        item.family_identity_sha256
        for item in inventory.opportunities
        if item.context.partition == "development"
        and item.opportunity.binding.precursor_species_ref == precursor_b
    )
    curriculum = freeze_two_family_curriculum(
        inventory,
        train_family_identity_sha256=family_a,
        development_family_identity_sha256=family_b,
    )

    class SyntheticMechanics:
        def __init__(self, family: str, *, observed_boundary: bool) -> None:
            self.family = family
            self.observed_boundary = observed_boundary

        def private_dict(self) -> dict[str, object]:
            common: dict[str, object] = {
                "family_identity_sha256": self.family,
                "precursor_species_ref": precursor_a,
                "evolved_species_ref": evolved_a,
                "source_id": "wild:synthetic:grass",
                "source_map_id": 1,
                "capture_skill_binding_sha256": _sha("capture-skill"),
                "capture_route_plan_sha256": _sha("capture-route"),
                "capture_route_cost": 3,
                "capture_exit_coordinates": [[1, 1]],
                "evolution_skill_binding_sha256": _sha("evolution-skill"),
                "precursor_internal_species_id": 124,
                "evolved_internal_species_id": 125,
                "current_box_index": 0,
                "precursor_box_slot": 1,
                "deposit_party_slot": 6,
                "deposit_internal_species_id": 28,
                "route_to_training_plan_sha256": _sha("training-route"),
                "route_to_training_cost": 2,
                "training_binding_sha256": _sha("training-binding"),
            }
            if self.observed_boundary:
                common.update(
                    {
                        "pc_access_kind": "observed_semantic_boundary",
                        "pc_boundary_binding_sha256": _sha("pc-boundary"),
                        "pc_boundary_observer_binding_sha256": _sha("pc-observer"),
                        "route_to_pc_cost": 0,
                    }
                )
            else:
                common.update(
                    {
                        "pc_access_kind": "semantic_route",
                        "route_to_pc_plan_sha256": _sha("pc-route"),
                        "route_to_pc_planner_binding_sha256": _sha("pc-planner"),
                        "route_to_pc_cost": 2,
                    }
                )
            return common

    mechanics = {
        (
            trial.opportunity.context.context_identity_sha256,
            trial.opportunity.family_identity_sha256,
        ): SyntheticMechanics(
            trial.opportunity.family_identity_sha256,
            observed_boundary=index % 2 == 1,
        )
        for index, trial in enumerate(
            (*curriculum.train_trials, *curriculum.development_trials)
        )
    }
    return inventory, curriculum, mechanics


def test_parser_requires_every_frozen_input_identity() -> None:
    parsed = SCRIPT["_parser"]().parse_args(_args())

    assert parsed.expected_source_commit == "a" * 40
    assert parsed.registry_source_commit == "b" * 40
    assert parsed.private_root == Path("/protected/artifacts")
    with pytest.raises(SCRIPT["MultifamilyPilotFreezeError"]):
        SCRIPT["_parser"]().parse_args(_args()[:-4])


def test_successor_uses_new_lane_and_private_plan_identities() -> None:
    assert SCRIPT["LANE_ID"] == "red-living-dex-multifamily-option-value-curriculum-v2"
    assert SCRIPT["PLAN_SCHEMA"].endswith(".v2")
    assert SCRIPT["RESULT_SCHEMA"].endswith(".v2")
    assert SCRIPT["FAILURE_SCHEMA"].endswith(".v2")
    assert SCRIPT["PLAN_RECORD_ID"].endswith("-v2")


def test_v3_successor_uses_fresh_protocol_identities_without_semantic_overrides() -> None:
    v2 = SCRIPT["V2_PROTOCOL"]
    v3 = V3_SCRIPT["PROTOCOL"]

    assert v3.lane_id == "red-living-dex-multifamily-option-value-curriculum-v3"
    assert v3.plan_schema.endswith(".v3")
    assert v3.result_schema.endswith(".v3")
    assert v3.failure_schema.endswith(".v3")
    assert v3.success_status.endswith("_v3")
    assert v3.plan_record_id.endswith("-v3")
    assert v3.plan_record_kind == v3.plan_record_id
    assert {
        v3.lane_id,
        v3.plan_schema,
        v3.result_schema,
        v3.failure_schema,
        v3.plan_record_id,
    }.isdisjoint(
        {
            v2.lane_id,
            v2.plan_schema,
            v2.result_schema,
            v2.failure_schema,
            v2.plan_record_id,
        }
    )
    assert V3_SCRIPT_PATH.read_text(encoding="utf-8").count("PROTOCOL =") == 1
    assert "def _inventory" not in V3_SCRIPT_PATH.read_text(encoding="utf-8")
    assert "def _freeze" not in V3_SCRIPT_PATH.read_text(encoding="utf-8")


def test_source_failure_stops_before_private_inputs_and_receipt_is_path_free(
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
            SCRIPT["MultifamilyPilotFreezeError"]("source_authentication")
        ),
    )
    monkeypatch.setitem(SCRIPT["main"].__globals__, "_authenticate_inputs", private)

    assert SCRIPT["main"](_args()) == 1

    result = json.loads(capsys.readouterr().out)
    assert private_calls == 0
    assert result["failure_stage"] == "source_authentication"
    assert result["controller_actions"] == 0
    assert result["roots_claimed"] == 0
    assert "/protected" not in json.dumps(result)


def test_v3_source_failure_uses_only_v3_receipt_and_stops_before_private_inputs(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    private_calls = 0
    runner_globals = V3_SCRIPT["_run_freeze"].__globals__

    def private(*_args: object, **_kwargs: object) -> object:
        nonlocal private_calls
        private_calls += 1
        raise AssertionError("private inputs opened")

    monkeypatch.setitem(
        runner_globals,
        "_authenticate_source",
        lambda _args: (_ for _ in ()).throw(
            runner_globals["MultifamilyPilotFreezeError"]("source_authentication")
        ),
    )
    monkeypatch.setitem(runner_globals, "_authenticate_inputs", private)

    assert V3_SCRIPT["main"](_args()) == 1

    result = json.loads(capsys.readouterr().out)
    assert private_calls == 0
    assert result["schema"] == V3_SCRIPT["FAILURE_SCHEMA"]
    assert result["failure_stage"] == "source_authentication"
    assert result["controller_actions"] == 0
    assert result["roots_claimed"] == 0
    assert "/protected" not in json.dumps(result)


def test_freezer_has_no_controller_or_model_execution_seam() -> None:
    source = SCRIPT_PATH.read_text(encoding="utf-8")

    assert "CountingExecutor" not in source
    assert "execute_route" not in source
    assert "score_red_living_dex_option" not in source
    assert "write_root_claim" not in source


def test_only_repeatable_item_free_level_evolutions_enter_boxed_inventory() -> None:
    catalog = SCRIPT["RED_ACQUISITION_CATALOG"]

    level_method = catalog.method_for("pokemon:national:012")
    item_method = catalog.method_for("pokemon:national:031")
    trade_method = catalog.method_for("pokemon:national:124")

    assert SCRIPT["_supported_level_evolution"](level_method)
    assert not SCRIPT["_supported_level_evolution"](item_method)
    assert not SCRIPT["_supported_level_evolution"](trade_method)


def test_freezer_family_key_is_the_adapters_complete_transformation_identity() -> None:
    method = SCRIPT["RED_ACQUISITION_CATALOG"].method_for("pokemon:national:012")
    precursor = red_species_ref(11)
    evolved = red_species_ref(12)
    specimens = (
        LivingSpecimen(
            precursor,
            4,
            CollectionLocation.BOX,
            container_index=0,
            slot_index=0,
        ),
        LivingSpecimen(
            precursor,
            4,
            CollectionLocation.BOX,
            container_index=0,
            slot_index=1,
        ),
    )
    observation = CollectionObservation(
        owned_species=frozenset({precursor}),
        specimens=specimens,
        party_size=0,
        party_limit=6,
        box_counts=(2,),
        current_box_index=0,
        box_capacity=20,
    )
    adapted = adapt_red_living_dex_dependencies(
        observation,
        execution_facts=RedDependencyExecutionFacts(
            acquirable_precursor_refs=frozenset({precursor}),
            trainable_evolution_pairs=frozenset({(precursor, evolved)}),
        ),
    )
    opportunity = next(
        item
        for item in adapted.opportunities
        if item.binding.precursor_species_ref == precursor
        and item.binding.evolved_species_ref == evolved
    )

    assert SCRIPT["_family_identity"](method) == opportunity.binding.binding_sha256
    assert (
        SCRIPT["_family_identity"](method)
        != SCRIPT["RedDependencySpeciesBinding"](precursor, evolved).binding_sha256
    )


def test_exact_pc_start_binds_an_observation_instead_of_a_fake_route() -> None:
    map_id = 1
    at_pc = SCRIPT["PC_GOAL_YX"]
    graph = LocalGraph({at_pc: ()})
    plan = plan_route(
        MacroGraph({map_id: ()}),
        {map_id: graph},
        map_id,
        at_pc,
        map_id,
        goal_at=at_pc,
    )
    start = TraversalSnapshot(map_id, at_pc, True)

    access = SCRIPT["_pc_access_binding"](
        start,
        plan,
        rom_sha256=_sha("rom"),
        source_bundle=_sha("source"),
        context_identity_sha256=_sha("context"),
    )

    assert isinstance(access, SCRIPT["ObservedSemanticBoundaryBinding"])
    assert access.public_dict()["route_steps"] == 0
    assert access.public_dict()["controller_actions"] == 0
    assert not plan.steps


def test_zero_step_plan_outside_pc_is_not_relabelled_as_an_observed_boundary() -> None:
    map_id = 1
    elsewhere = (3, 3)
    graph = LocalGraph({elsewhere: ()})
    plan = plan_route(
        MacroGraph({map_id: ()}),
        {map_id: graph},
        map_id,
        elsewhere,
        map_id,
        goal_at=elsewhere,
    )

    with pytest.raises(
        SCRIPT["MultifamilyPilotFreezeError"],
        match="observed_pc_boundary_authentication",
    ):
        SCRIPT["_pc_access_binding"](
            TraversalSnapshot(map_id, elsewhere, True),
            plan,
            rom_sha256=_sha("rom"),
            source_bundle=_sha("source"),
            context_identity_sha256=_sha("context"),
        )


@pytest.mark.parametrize(
    ("protocol", "record_id", "record_kind", "result_schema", "success_status"),
    (
        (
            SCRIPT["V2_PROTOCOL"],
            SCRIPT["PLAN_RECORD_ID"],
            SCRIPT["PLAN_RECORD_KIND"],
            SCRIPT["RESULT_SCHEMA"],
            "two_family_root_disjoint_pilot_frozen_v2",
        ),
        (
            V3_SCRIPT["PROTOCOL"],
            V3_SCRIPT["PLAN_RECORD_ID"],
            V3_SCRIPT["PLAN_RECORD_KIND"],
            V3_SCRIPT["RESULT_SCHEMA"],
            "two_family_root_disjoint_pilot_frozen_v3",
        ),
    ),
)
def test_full_synthetic_plan_round_trips_through_exact_sealed_publication(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    protocol: object,
    record_id: str,
    record_kind: str,
    result_schema: str,
    success_status: str,
) -> None:
    inventory, curriculum, mechanics = _synthetic_curriculum()
    document, plan_sha256 = SCRIPT["_private_plan_document"](
        protocol=protocol,
        source_commit="a" * 40,
        source_bundle=_sha("source"),
        rom_sha256=_sha("rom"),
        registry_sha256=_sha("registry"),
        catalog_sha256=_sha("catalog"),
        context_plan_sha256=_sha("context-plan"),
        inventory=inventory,
        curriculum=curriculum,
        mechanics=mechanics,
    )

    counts = document["curriculum"]
    assert isinstance(counts, dict)
    assert counts["train_candidate_counts"] == {"0": 4, "1": 4}
    assert counts["development_candidate_counts"] == {"0": 4, "1": 4}
    assert len(document["trials"]) == 16  # type: ignore[arg-type]
    access_kinds = {
        trial["mechanics"]["pc_access_kind"]  # type: ignore[index]
        for trial in document["trials"]  # type: ignore[union-attr]
    }
    assert access_kinds == {"semantic_route", "observed_semantic_boundary"}

    private_root = tmp_path / "private"
    private_root.mkdir(mode=0o700)
    store = initialize_private_root(
        private_root,
        repository_root=PROJECT_ROOT,
        allow_same_device=True,
    )
    monkeypatch.setitem(
        SCRIPT["_publish"].__globals__,
        "open_private_root",
        lambda *_args, **_kwargs: store,
    )
    parsed = SCRIPT["_parser"]().parse_args(_args())
    result = SCRIPT["_publish"](
        parsed,
        protocol=protocol,
        document=document,
        plan_sha256=plan_sha256,
        inventory=inventory,
        curriculum=curriculum,
        emulator_frames_advanced=0,
    )
    reopened = store.find_sealed_record(
        record_id,
        expected_kind=record_kind,
    )

    assert reopened is not None
    assert reopened.read() == document
    assert result["plan_sha256"] == plan_sha256
    assert result["schema"] == result_schema
    assert result["status"] == success_status
    assert result["lane_id"] == protocol.lane_id  # type: ignore[attr-defined]
    assert result["plan_manifest_sha256"] == reopened.summary.manifest_sha256
    assert result["private_paths_published"] == 0
    assert str(tmp_path) not in json.dumps(result, sort_keys=True)
    if record_id == V3_SCRIPT["PLAN_RECORD_ID"]:
        assert (
            store.find_sealed_record(
                SCRIPT["PLAN_RECORD_ID"],
                expected_kind=SCRIPT["PLAN_RECORD_KIND"],
            )
            is None
        )


@pytest.mark.parametrize(
    "field",
    ("train_candidate_counts", "development_candidate_counts"),
)
def test_strict_sealed_publication_rejects_original_integer_key_mutation(
    tmp_path: Path,
    field: str,
) -> None:
    inventory, curriculum, mechanics = _synthetic_curriculum()
    document, _plan_sha256 = SCRIPT["_private_plan_document"](
        source_commit="a" * 40,
        source_bundle=_sha("source"),
        rom_sha256=_sha("rom"),
        registry_sha256=_sha("registry"),
        catalog_sha256=_sha("catalog"),
        context_plan_sha256=_sha("context-plan"),
        inventory=inventory,
        curriculum=curriculum,
        mechanics=mechanics,
    )
    mutated = deepcopy(document)
    curriculum_document = mutated["curriculum"]
    assert isinstance(curriculum_document, dict)
    curriculum_document[field] = {0: 4, 1: 4}
    private_root = tmp_path / "private"
    private_root.mkdir(mode=0o700)
    store = initialize_private_root(
        private_root,
        repository_root=PROJECT_ROOT,
        allow_same_device=True,
    )

    with pytest.raises(PrivateArtifactError, match="keys must be strings"):
        store.publish_sealed_record(
            f"integer-key-{field.replace('_', '-')}",
            kind="synthetic-multifamily-plan",
            record=mutated,
        )

    assert (
        store.find_sealed_record(
            f"integer-key-{field.replace('_', '-')}",
            expected_kind="synthetic-multifamily-plan",
        )
        is None
    )


def test_main_distinguishes_private_encoding_failure_from_publication(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    inventory, curriculum, mechanics = _synthetic_curriculum()
    publication_calls = 0

    class IntegerKeyCurriculum:
        train_trials = curriculum.train_trials
        development_trials = curriculum.development_trials

        @staticmethod
        def public_dict() -> dict[str, object]:
            document = curriculum.public_dict()
            document["train_candidate_counts"] = {0: 4, 1: 4}
            return document

    monkeypatch.setitem(
        SCRIPT["main"].__globals__,
        "_authenticate_source",
        lambda _args: ("a" * 40, _sha("source")),
    )
    monkeypatch.setitem(
        SCRIPT["main"].__globals__,
        "_authenticate_inputs",
        lambda *_args: (
            Path("red.gb"),
            _sha("rom"),
            b"rom",
            (),
            _sha("catalog"),
            _sha("context-plan"),
        ),
    )
    monkeypatch.setitem(
        SCRIPT["main"].__globals__,
        "_inventory",
        lambda *_args: (inventory, mechanics, 0),
    )
    monkeypatch.setitem(
        SCRIPT["main"].__globals__,
        "_freeze",
        lambda *_args: IntegerKeyCurriculum(),
    )

    def publish(*_args: object, **_kwargs: object) -> object:
        nonlocal publication_calls
        publication_calls += 1
        raise AssertionError("publication must not begin")

    monkeypatch.setitem(SCRIPT["main"].__globals__, "_publish", publish)

    assert SCRIPT["main"](_args()) == 1

    failure = json.loads(capsys.readouterr().out)
    assert failure["failure_stage"] == "private_plan_encoding"
    assert failure["controller_actions"] == 0
    assert failure["roots_claimed"] == 0
    assert publication_calls == 0
