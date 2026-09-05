from __future__ import annotations

import json
from copy import deepcopy
from dataclasses import replace
from pathlib import Path

import pytest
from test_living_dex_policy_development import _model
from test_red_living_dex_clustered_train_runner import _identity
from test_red_living_dex_development_setup_journal import _fixture
from test_red_living_dex_development_supplement_plan import _plan

from pokemon_red_completion.provenance import canonical_sha256
from pokemon_red_completion.red_living_dex_clustered_development_execution import (
    RedLivingDexClusteredDevelopmentExecutionError,
    preflight_red_living_dex_clustered_development_assignment,
    run_red_living_dex_clustered_development_assignment,
)
from pokemon_red_completion.red_living_dex_clustered_development_runner import (
    RedLivingDexClusteredDevelopmentRunnerError,
    authenticate_red_living_dex_clustered_development_selection,
    authenticate_red_living_dex_development_selection,
    load_red_living_dex_development_selection,
)
from pokemon_red_completion.red_living_dex_development_setup_admission import (
    authenticate_frozen_red_living_dex_development_setup_slot,
)
from pokemon_red_completion.red_living_dex_development_supplement_reader import (
    RedLivingDexDevelopmentSupplementBinding,
    RedLivingDexDevelopmentSupplementReadError,
    load_red_living_dex_development_supplement,
    validate_red_living_dex_development_supplement,
)


def _binding(plan):  # type: ignore[no-untyped-def]
    return RedLivingDexDevelopmentSupplementBinding(
        private_plan_sha256=plan.private_plan_sha256,
        supplement_plan_sha256=plan.supplement.plan_sha256,
        plan_manifest_sha256="1" * 64,
        plan_record_sha256="2" * 64,
        model_sha256=plan.bindings.model_sha256,
        model_record_sha256=plan.bindings.model_record_sha256,
    )


def test_authenticates_real_freezer_output_and_three_exact_rows() -> None:
    plan = _plan()
    binding = _binding(plan)
    assert (
        validate_red_living_dex_development_supplement(plan.private_dict(), binding=binding)
        == plan.supplement
    )
    for ordinal, row in enumerate(plan.assignments):
        selection = authenticate_red_living_dex_development_selection(
            plan.private_dict(), ordinal, binding=binding
        )
        assert selection.plan_kind == "supplement"
        assert selection.train_scenarios == 0
        assert selection.logical_root_sha256 == row.capability.root.root.root_consumption_sha256
        assert selection.recipe_sha256 == row.capability.recipe.recipe_sha256
        assert selection.slot_sha256 == row.capability.slot.slot_sha256
        assert selection.public_dict()["ordinal_within_development"] == ordinal
        assert selection.public_dict()["train_accessible"] is False


@pytest.mark.parametrize("ordinal", [-1, 3, 16, True, 0.0])
def test_out_of_range_and_noninteger_ordinals_are_rejected(ordinal: object) -> None:
    with pytest.raises(RedLivingDexClusteredDevelopmentRunnerError):
        authenticate_red_living_dex_development_selection(
            _plan().private_dict(),
            ordinal,
            binding=_binding(_plan()),  # type: ignore[arg-type]
        )


def test_historical_parser_does_not_accept_supplement() -> None:
    with pytest.raises(TypeError):
        authenticate_red_living_dex_clustered_development_selection(
            _plan().private_dict(),
            0,
            binding=_binding(_plan()),  # type: ignore[arg-type]
        )


def test_sealed_record_reopen_authenticates_manifest_and_bytes(tmp_path: Path) -> None:
    from test_red_living_dex_setup_recipe import _store

    plan = _plan()
    store = _store(tmp_path)
    binding = _binding(plan)
    record = store.publish_sealed_record(
        binding.record_id, kind=binding.record_kind, record=plan.private_dict()
    )
    binding = replace(
        binding,
        plan_manifest_sha256=record.summary.manifest_sha256,
        plan_record_sha256=record.summary.record_sha256,
    )
    selected, document = load_red_living_dex_development_selection(store, 1, binding=binding)
    assert load_red_living_dex_development_supplement(store, binding=binding) == plan.supplement
    assert document == json.loads(json.dumps(plan.private_dict()))
    assert selected.ordinal == 1
    for field in (
        "plan_manifest_sha256",
        "plan_record_sha256",
        "private_plan_sha256",
        "supplement_plan_sha256",
    ):
        with pytest.raises(RedLivingDexClusteredDevelopmentRunnerError):
            load_red_living_dex_development_selection(
                store, 1, binding=replace(binding, **{field: "f" * 64})
            )
        with pytest.raises(RedLivingDexDevelopmentSupplementReadError):
            load_red_living_dex_development_supplement(
                store,
                binding=replace(binding, **{field: "f" * 64}),
            )


@pytest.mark.parametrize(
    "fault",
    [
        "train",
        "ordinal",
        "template",
        "context",
        "logical_root",
        "recipe_root",
        "schema",
        "provider",
        "unknown",
        "boolean_zero",
        "model",
        "shared_extra",
    ],
)
def test_semantic_corruption_rejected_even_with_recomputed_outer_commitment(fault: str) -> None:
    plan = _plan()
    doc = deepcopy(plan.private_dict())
    rows = doc["assignments"]
    if fault == "train":
        rows[0]["partition"] = "train"
    elif fault == "ordinal":
        rows[0]["ordinal"] = True
    elif fault == "template":
        rows[0]["template_ordinal"] = 0
    elif fault == "context":
        rows[1]["context_identity_sha256"] = rows[0]["context_identity_sha256"]
    elif fault == "logical_root":
        rows[1]["root_consumption_sha256"] = rows[0]["root_consumption_sha256"]
    elif fault == "recipe_root":
        rows[0]["recipe"]["root_state_sha256"] = "f" * 64
        rows[0]["recipe_sha256"] = canonical_sha256(rows[0]["recipe"])
    elif fault == "schema":
        rows[0]["recipe"]["schema"] = "different"
        rows[0]["recipe_sha256"] = canonical_sha256(rows[0]["recipe"])
    elif fault == "provider":
        rows[0]["recipe"]["providers"][0]["option_kind"] = "different"
        rows[0]["recipe_sha256"] = canonical_sha256(rows[0]["recipe"])
    elif fault == "unknown":
        doc["extra"] = 0
    elif fault == "boolean_zero":
        doc["root_claims"] = False
    elif fault == "model":
        doc["model_sha256"] = "f" * 64
    elif fault == "shared_extra":
        doc["supplement"]["extra"] = 0
    doc["private_plan_sha256"] = canonical_sha256(
        {key: value for key, value in doc.items() if key != "private_plan_sha256"}
    )
    binding = replace(_binding(plan), private_plan_sha256=doc["private_plan_sha256"])
    with pytest.raises(RedLivingDexDevelopmentSupplementReadError):
        validate_red_living_dex_development_supplement(doc, binding=binding)


def _admitted(tmp_path: Path, *, successful_setup: bool = False):  # type: ignore[no-untyped-def]
    _old_plan, _cap, _frozen, outer, meter, _resolver, store, registry = _fixture(tmp_path)
    identity = _identity()
    model = _model()
    source = _plan()
    if successful_setup:
        from test_red_living_dex_development_supplement_plan import _inputs
        from test_red_living_dex_setup_recipe import _recipes, _root

        from pokemon_red_completion.red_living_dex_development_supplement_plan import (
            freeze_red_living_dex_development_supplement_plan,
        )

        caps, supply, _contexts, bindings = _inputs()
        recipes = _recipes()
        repaired = []
        for item in caps:
            root = _root(item.template_ordinal)
            repaired.append(
                replace(
                    item,
                    root=replace(
                        item.root,
                        root=root,
                        observed_state_sha256=root.state_sha256,
                    ),
                    recipe=recipes[item.template_ordinal],
                )
            )
        source = freeze_red_living_dex_development_supplement_plan(
            tuple(repaired),
            supply=supply,
            bindings=bindings,
            context_identities={
                item.root.root.root_consumption_sha256: canonical_sha256({"context": index})
                for index, item in enumerate(repaired)
            },
        )
    plan = replace(
        source,
        bindings=replace(
            source.bindings,
            source_commit=identity.source_commit,
            source_bundle_sha256=identity.source_bundle_sha256,
            rom_sha256=identity.rom_sha256,
            route_registry_sha256=identity.route_registry_sha256,
            model_sha256=model.model_sha256,
        ),
    )
    binding = _binding(plan)
    selection = authenticate_red_living_dex_development_selection(
        plan.private_dict(), 0, binding=binding
    )
    cap = plan.assignments[0].capability
    frozen = authenticate_frozen_red_living_dex_development_setup_slot(
        plan.private_dict(),
        selection=selection,
        binding=binding,
        root=cap.root.root,
        producer_execution_identity=identity,
        expected_runtime_identity_sha256=plan.bindings.runtime_identity_sha256,
    )
    outer = replace(
        outer,
        producer_plan_sha256=plan.private_plan_sha256,
        producer_private_plan_sha256=plan.private_plan_sha256,
        producer_manifest_sha256=binding.plan_manifest_sha256,
        slot_sha256=selection.slot_sha256,
        recipe_sha256=selection.recipe_sha256,
        logical_root_sha256=selection.logical_root_sha256,
        physical_root_sha256=selection.physical_root_sha256,
    )
    return plan, cap, frozen, outer, meter, store, registry, model


def test_supplement_admission_and_preflight_have_zero_effects(tmp_path: Path) -> None:
    plan, cap, frozen, outer, meter, _store, registry, model = _admitted(tmp_path)
    before = meter.checkpoint()
    assert frozen.template_ordinal == cap.template_ordinal
    frozen.reauthenticate(plan.private_dict(), root=cap.root.root)
    frozen.require_resolved_recipe(cap.recipe)
    result = preflight_red_living_dex_clustered_development_assignment(
        selection=frozen.selection,
        binding=frozen.binding,
        plan_document=plan.private_dict(),
        root=cap.root.root,
        producer_execution_identity=frozen.producer_execution_identity(),
        outer_execution_identity=outer,
        meter=meter,
        claim_registry=registry,
        model=model,
        expected_model_sha256=model.model_sha256,
    )
    assert result.public_dict()["claim_available"] is True
    assert result.public_dict()["model_predictions"] == 0
    assert meter.checkpoint() == before
    assert tuple(registry.glob("claim-pair-v1-*.json")) == ()


def test_self_consistent_substitute_model_cannot_replace_frozen_model(tmp_path: Path) -> None:
    plan, cap, frozen, outer, meter, _store, registry, model = _admitted(tmp_path)
    binding = replace(frozen.binding, model_sha256="f" * 64)
    with pytest.raises(RedLivingDexClusteredDevelopmentExecutionError, match="model identity"):
        preflight_red_living_dex_clustered_development_assignment(
            selection=frozen.selection,
            binding=binding,
            plan_document=plan.private_dict(),
            root=cap.root.root,
            producer_execution_identity=frozen.producer_execution_identity(),
            outer_execution_identity=outer,
            meter=meter,
            claim_registry=registry,
            model=model,
            expected_model_sha256=model.model_sha256,
        )
    assert tuple(registry.iterdir()) == ()


def test_supplement_uses_existing_terminal_journal_without_retry(tmp_path: Path) -> None:
    from test_red_living_dex_clustered_train_runner import _ArmFactory, _Resolver

    plan, cap, frozen, outer, meter, store, registry, model = _admitted(tmp_path)
    identity = frozen.producer_execution_identity()
    resolver = _Resolver(cap.recipe, identity, _ArmFactory(identity, meter))
    kwargs = dict(
        selection=frozen.selection,
        binding=frozen.binding,
        store=store,
        plan_loader=lambda: plan.private_dict(),
        root=cap.root.root,
        producer_execution_identity=identity,
        outer_execution_identity=outer,
        resolver=resolver,
        meter=meter,
        claim_registry=registry,
        model=model,
        expected_model_sha256=model.model_sha256,
    )
    result = run_red_living_dex_clustered_development_assignment(**kwargs)
    assert resolver.calls == 1
    assert result.development is None  # Fixture intentionally fails setup.
    again = run_red_living_dex_clustered_development_assignment(**kwargs)
    assert resolver.calls == 1
    assert again.public_dict()["training_targets_emitted"] == 0


def test_successful_supplement_setup_reaches_actual_model_choice_and_terminal(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from test_red_living_dex_clustered_train_runner import _ArmFactory, _Resolver
    from test_red_living_dex_setup_recipe import _Reader

    from pokemon_red_completion.observation import ItemId, RedCurrentBoxState
    from pokemon_red_completion.red_collection import red_internal_species_id

    original_boxes = _Reader.read_all_box_states

    def occupied_box(reader):  # type: ignore[no-untyped-def]
        boxes = original_boxes(reader)
        if boxes.boxes[0].species_ids:
            return boxes
        # A real storage choice needs greater headroom in the target box.
        current = RedCurrentBoxState(0, (red_internal_species_id(25),), (10,))
        return replace(boxes, boxes=(current, *boxes.boxes[1:]), storage_initialized=True)

    monkeypatch.setattr(_Reader, "read_all_box_states", occupied_box)
    original_read = _Reader.read

    def scarce_balls(reader):  # type: ignore[no-untyped-def]
        return replace(
            original_read(reader),
            bag_items=((int(ItemId.POKE_BALL), 1), (int(ItemId.HYPER_POTION), 20)),
        )

    monkeypatch.setattr(_Reader, "read", scarce_balls)

    plan, cap, frozen, outer, meter, store, registry, model = _admitted(
        tmp_path, successful_setup=True
    )
    identity = frozen.producer_execution_identity()
    resolver = _Resolver(cap.recipe, identity, _ArmFactory(identity, meter))
    kwargs = dict(
        selection=frozen.selection,
        binding=frozen.binding,
        store=store,
        plan_loader=plan.private_dict,
        root=cap.root.root,
        producer_execution_identity=identity,
        outer_execution_identity=outer,
        resolver=resolver,
        meter=meter,
        claim_registry=registry,
        model=model,
        expected_model_sha256=model.model_sha256,
    )
    result = run_red_living_dex_clustered_development_assignment(**kwargs)
    assert result.setup.terminal.status.value == "complete"
    assert result.development is not None
    assert result.development.result is not None
    assert result.development.terminal.status.value == "complete"
    assert meter.provider_executions == 1
    assert result.public_dict()["model_predictions"] > 0
    assert result.public_dict()["training_targets_emitted"] == 0
    calls = resolver.calls
    recovered = run_red_living_dex_clustered_development_assignment(**kwargs)
    assert recovered.development is not None
    assert recovered.development.result == result.development.result
    assert meter.provider_executions == 1
    assert resolver.calls == calls
